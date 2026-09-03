"""
Users Analysis Router
Handles all user security monitoring endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
import logging
import re
import pyodbc

_AD_SAM_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._$\-]{1,64}$")
_AD_GROUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._ \-]{1,128}$")

from api.connection_pool import SQLServerConnectionPool
from api.dependencies import get_pool
from api.error_helpers import safe_http_error
from api.models import GenericResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/users",
    tags=["users-analysis"],
    responses={404: {"description": "Not found"}},
)


def get_pooled_connection(server_id: str, pool: SQLServerConnectionPool, database: str = "master"):
    """
    Obtém conexão do pool (injected via FastAPI Depends).

    Args:
        server_id: Server identifier (HOST_INSTANCE or HOST\\INSTANCE)
        pool: Connection pool instance (from DI)
        database: Database to connect (default: master)

    Returns:
        Tuple of (connection, pool) - caller must return connection to pool when done
    """
    conn = pool.get_connection(server_id, database)
    if conn is None:
        raise HTTPException(status_code=500, detail=f"Não foi possível conectar ao servidor {server_id}")
    return conn, pool


@router.get("/server/{server_id}", response_model=GenericResponse)
async def get_users_analysis(server_id: str, pool: SQLServerConnectionPool = Depends(get_pool)):
    """
    Get complete users security analysis for a server

    Returns:
    - orphaned_users: Usuários órfãos (sem login correspondente)
    - excessive_permissions: Usuários com permissões excessivas
    - inactive_users: Usuários inativos (30+ dias)
    - weak_passwords: Logins com políticas de senha fracas
    - critical_roles: Membros de roles críticos
    - total_users: Total de usuários/logins no servidor
    """
    conn = None
    try:
        logger.info(f"Users analysis requested for server: {server_id}")

        conn, pool = get_pooled_connection(server_id, pool)
        cursor = conn.cursor()

        # 1. USUÁRIOS ÓRFÃOS
        orphaned_query = """
        DECLARE @orphaned TABLE (
            database_name NVARCHAR(128),
            user_name NVARCHAR(128),
            user_sid VARBINARY(85),
            user_type_desc NVARCHAR(60)
        )

        DECLARE @sql NVARCHAR(MAX)
        DECLARE @db_name NVARCHAR(128)

        DECLARE db_cursor CURSOR FOR
        SELECT name
        FROM sys.databases
        WHERE state_desc = 'ONLINE'
            AND database_id > 4  -- Excluir system databases
            AND name NOT IN ('master', 'tempdb', 'model', 'msdb')

        OPEN db_cursor
        FETCH NEXT FROM db_cursor INTO @db_name

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @sql = N'USE [' + @db_name + N'];
            INSERT INTO @orphaned (database_name, user_name, user_sid, user_type_desc)
            SELECT
                ''' + @db_name + N''' AS database_name,
                dp.name AS user_name,
                dp.sid AS user_sid,
                dp.type_desc AS user_type_desc
            FROM sys.database_principals dp
            LEFT JOIN sys.server_principals sp ON dp.sid = sp.sid
            WHERE dp.type IN (''S'', ''U'', ''G'')  -- SQL User, Windows User, Windows Group
                AND dp.sid IS NOT NULL
                AND dp.sid NOT IN (0x00, 0x01)  -- Excluir public e guest
                AND dp.name NOT IN (''dbo'', ''guest'', ''INFORMATION_SCHEMA'', ''sys'')
                AND sp.sid IS NULL  -- Não tem login correspondente
                AND dp.authentication_type_desc = ''INSTANCE''  -- Apenas usuários autenticados por instância
            '

            BEGIN TRY
                EXEC sp_executesql @sql
            END TRY
            BEGIN CATCH
                -- Silently skip databases with errors
            END CATCH

            FETCH NEXT FROM db_cursor INTO @db_name
        END

        CLOSE db_cursor
        DEALLOCATE db_cursor

        SELECT
            database_name,
            user_name,
            CONVERT(VARCHAR(MAX), user_sid, 1) AS user_sid,
            user_type_desc
        FROM @orphaned
        ORDER BY database_name, user_name
        """

        cursor.execute(orphaned_query)
        orphaned_users = []
        for row in cursor.fetchall():
            orphaned_users.append({
                'database_name': row.database_name,
                'user_name': row.user_name,
                'user_sid': row.user_sid,
                'user_type_desc': row.user_type_desc
            })

        # 2. PERMISSÕES EXCESSIVAS
        excessive_query = """
        -- Server-level (sysadmin, securityadmin, serveradmin)
        SELECT
            sp.name AS login_name,
            NULL AS database_name,
            sr.name AS role_name,
            NULL AS permission,
            'Server-level critical role' AS reason
        FROM sys.server_role_members srm
        JOIN sys.server_principals sp ON srm.member_principal_id = sp.principal_id
        JOIN sys.server_principals sr ON srm.role_principal_id = sr.principal_id
        WHERE sr.name IN ('sysadmin', 'securityadmin', 'serveradmin')
            AND sp.name NOT LIKE 'NT SERVICE%'
            AND sp.name NOT LIKE 'NT AUTHORITY%'
            AND sp.name NOT IN ('sa')

        UNION ALL

        -- CONTROL SERVER permissions
        SELECT
            sp.name AS login_name,
            NULL AS database_name,
            NULL AS role_name,
            spe.permission_name AS permission,
            'CONTROL SERVER permission' AS reason
        FROM sys.server_permissions spe
        JOIN sys.server_principals sp ON spe.grantee_principal_id = sp.principal_id
        WHERE spe.permission_name = 'CONTROL SERVER'
            AND spe.state_desc = 'GRANT'
            AND sp.name NOT IN ('sa')
        """

        cursor.execute(excessive_query)
        excessive_permissions = []
        for row in cursor.fetchall():
            excessive_permissions.append({
                'login_name': row.login_name,
                'database_name': row.database_name,
                'role_name': row.role_name,
                'permission': row.permission,
                'reason': row.reason
            })

        # Database-level excessive permissions (db_owner em user databases)
        db_excessive_query = """
        DECLARE @excessive TABLE (
            database_name NVARCHAR(128),
            user_name NVARCHAR(128),
            role_name NVARCHAR(128),
            reason NVARCHAR(200)
        )

        DECLARE @sql NVARCHAR(MAX)
        DECLARE @db_name NVARCHAR(128)

        DECLARE db_cursor CURSOR FOR
        SELECT name
        FROM sys.databases
        WHERE state_desc = 'ONLINE'
            AND database_id > 4
            AND name NOT IN ('master', 'tempdb', 'model', 'msdb')

        OPEN db_cursor
        FETCH NEXT FROM db_cursor INTO @db_name

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @sql = N'USE [' + @db_name + N'];
            INSERT INTO @excessive (database_name, user_name, role_name, reason)
            SELECT
                ''' + @db_name + N''' AS database_name,
                dp.name AS user_name,
                dr.name AS role_name,
                ''Database-level critical role'' AS reason
            FROM sys.database_role_members drm
            JOIN sys.database_principals dp ON drm.member_principal_id = dp.principal_id
            JOIN sys.database_principals dr ON drm.role_principal_id = dr.principal_id
            WHERE dr.name IN (''db_owner'', ''db_securityadmin'', ''db_ddladmin'')
                AND dp.name NOT IN (''dbo'')
            '

            BEGIN TRY
                EXEC sp_executesql @sql
            END TRY
            BEGIN CATCH
                -- Silently skip
            END CATCH

            FETCH NEXT FROM db_cursor INTO @db_name
        END

        CLOSE db_cursor
        DEALLOCATE db_cursor

        SELECT database_name, user_name, role_name, reason
        FROM @excessive
        ORDER BY database_name, user_name
        """

        cursor.execute(db_excessive_query)
        for row in cursor.fetchall():
            excessive_permissions.append({
                'login_name': None,
                'user_name': row.user_name,
                'database_name': row.database_name,
                'role_name': row.role_name,
                'permission': None,
                'reason': row.reason
            })

        # 3. USUÁRIOS INATIVOS
        inactive_query = """
        SELECT
            sp.name AS login_name,
            sp.create_date,
            l.last_login_time AS last_login_date,
            DATEDIFF(DAY, ISNULL(l.last_login_time, sp.create_date), GETDATE()) AS days_inactive,
            sp.is_disabled
        FROM sys.server_principals sp
        LEFT JOIN (
            SELECT
                login_name,
                MAX(login_time) AS last_login_time
            FROM sys.dm_exec_sessions
            GROUP BY login_name
        ) l ON sp.name = l.login_name
        WHERE sp.type IN ('S', 'U', 'G')  -- SQL, Windows User, Windows Group
            AND sp.name NOT LIKE 'NT %'
            AND sp.name NOT IN ('sa')
            AND (
                l.last_login_time IS NULL  -- Nunca fez login
                OR DATEDIFF(DAY, l.last_login_time, GETDATE()) > 30  -- Inativo por 30+ dias
            )
        ORDER BY days_inactive DESC
        """

        cursor.execute(inactive_query)
        inactive_users = []
        for row in cursor.fetchall():
            inactive_users.append({
                'login_name': row.login_name,
                'create_date': row.create_date.isoformat() if row.create_date else None,
                'last_login_date': row.last_login_date.isoformat() if row.last_login_date else None,
                'days_inactive': row.days_inactive,
                'is_disabled': row.is_disabled
            })

        # 4. SENHAS FRACAS (Políticas desabilitadas)
        weak_pwd_query = """
        SELECT
            name AS login_name,
            is_policy_checked,
            is_expiration_checked,
            is_disabled,
            modify_date AS password_last_set
        FROM sys.sql_logins
        WHERE (is_policy_checked = 0 OR is_expiration_checked = 0)
            AND name NOT IN ('sa', '##MS_PolicyEventProcessingLogin##', '##MS_PolicyTsqlExecutionLogin##')
        ORDER BY is_policy_checked, is_expiration_checked
        """

        cursor.execute(weak_pwd_query)
        weak_passwords = []
        for row in cursor.fetchall():
            weak_passwords.append({
                'login_name': row.login_name,
                'is_policy_checked': row.is_policy_checked,
                'is_expiration_checked': row.is_expiration_checked,
                'is_disabled': row.is_disabled,
                'password_last_set': row.password_last_set.isoformat() if row.password_last_set else None
            })

        # 5. ROLES CRÍTICOS (Auditoria completa)
        critical_roles_query = """
        -- Server-level critical roles
        SELECT
            sp.name AS member_name,
            NULL AS database_name,
            sr.name AS role_name,
            sp.type_desc AS member_type
        FROM sys.server_role_members srm
        JOIN sys.server_principals sp ON srm.member_principal_id = sp.principal_id
        JOIN sys.server_principals sr ON srm.role_principal_id = sr.principal_id
        WHERE sr.name IN ('sysadmin', 'securityadmin', 'serveradmin', 'processadmin', 'setupadmin', 'bulkadmin', 'diskadmin', 'dbcreator')
            AND sp.name NOT LIKE 'NT %'
        ORDER BY sr.name, sp.name
        """

        cursor.execute(critical_roles_query)
        critical_roles = []
        for row in cursor.fetchall():
            critical_roles.append({
                'member_name': row.member_name,
                'database_name': row.database_name,
                'role_name': row.role_name,
                'member_type': row.member_type
            })

        # Database-level critical roles
        db_critical_query = """
        DECLARE @critical TABLE (
            database_name NVARCHAR(128),
            member_name NVARCHAR(128),
            role_name NVARCHAR(128),
            member_type NVARCHAR(60)
        )

        DECLARE @sql NVARCHAR(MAX)
        DECLARE @db_name NVARCHAR(128)

        DECLARE db_cursor CURSOR FOR
        SELECT name
        FROM sys.databases
        WHERE state_desc = 'ONLINE'
            AND database_id > 4

        OPEN db_cursor
        FETCH NEXT FROM db_cursor INTO @db_name

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @sql = N'USE [' + @db_name + N'];
            INSERT INTO @critical (database_name, member_name, role_name, member_type)
            SELECT
                ''' + @db_name + N''' AS database_name,
                dp.name AS member_name,
                dr.name AS role_name,
                dp.type_desc AS member_type
            FROM sys.database_role_members drm
            JOIN sys.database_principals dp ON drm.member_principal_id = dp.principal_id
            JOIN sys.database_principals dr ON drm.role_principal_id = dr.principal_id
            WHERE dr.name IN (''db_owner'', ''db_securityadmin'', ''db_accessadmin'', ''db_ddladmin'', ''db_backupoperator'')
            '

            BEGIN TRY
                EXEC sp_executesql @sql
            END TRY
            BEGIN CATCH
                -- Skip
            END CATCH

            FETCH NEXT FROM db_cursor INTO @db_name
        END

        CLOSE db_cursor
        DEALLOCATE db_cursor

        SELECT database_name, member_name, role_name, member_type
        FROM @critical
        ORDER BY database_name, role_name, member_name
        """

        cursor.execute(db_critical_query)
        for row in cursor.fetchall():
            critical_roles.append({
                'member_name': row.member_name,
                'database_name': row.database_name,
                'role_name': row.role_name,
                'member_type': row.member_type
            })

        # 6. TOTAL DE USUÁRIOS
        total_query = """
        SELECT COUNT(*) AS total
        FROM sys.server_principals
        WHERE type IN ('S', 'U', 'G')
            AND name NOT LIKE 'NT %'
        """

        cursor.execute(total_query)
        total_users = cursor.fetchone().total

        # Montar resposta
        result = {
            'orphaned_users': orphaned_users,
            'excessive_permissions': excessive_permissions,
            'inactive_users': inactive_users,
            'weak_passwords': weak_passwords,
            'critical_roles': critical_roles,
            'total_users': total_users
        }

        logger.info(f"Users analysis completed for {server_id}: {len(orphaned_users)} orphaned, {len(excessive_permissions)} excessive, {len(inactive_users)} inactive, {len(weak_passwords)} weak passwords, {len(critical_roles)} critical roles")

        return result

    except pyodbc.Error as e:
        raise safe_http_error(500, e, f"database error fetching users analysis for {server_id}")

    except Exception as e:
        raise safe_http_error(500, e, f"fetching users analysis for {server_id}")

    finally:
        if conn and pool:
            pool.return_connection(server_id, conn)


@router.get("/server/{server_id}/login/{login_name}", response_model=GenericResponse)
async def get_login_details(server_id: str, login_name: str, pool: SQLServerConnectionPool = Depends(get_pool)):
    """
    Get detailed information about a specific login
    """
    conn = None
    try:
        logger.info(f"Login details requested for {login_name} on server: {server_id}")

        conn, pool = get_pooled_connection(server_id, pool)
        cursor = conn.cursor()

        # OPTIMIZED: Queries 1-3 combined into a single query (was 3 separate roundtrips).
        # Combines login info (sys.server_principals) + password policy (sys.sql_logins)
        # + server roles (sys.server_role_members) using LEFT JOINs.
        # Query 4 (mapped databases) remains separate because it uses dynamic SQL
        # with a cursor across all databases — cannot be combined with server-level DMVs.
        combined_query = """
        -- Login info + password policy + server roles in one roundtrip
        SELECT
            sp.name AS login_name,
            sp.type_desc AS login_type,
            sp.is_disabled,
            sp.create_date,
            sp.modify_date,
            sp.default_database_name,
            sp.default_language_name,
            CASE WHEN sp.type = 'S' THEN 1 ELSE 0 END AS is_sql_login,
            -- Password policy columns (NULL for non-SQL logins)
            sl.is_policy_checked,
            sl.is_expiration_checked,
            LOGINPROPERTY(sp.name, 'PasswordLastSetTime') AS password_last_set,
            LOGINPROPERTY(sp.name, 'DaysUntilExpiration') AS days_until_expiration,
            LOGINPROPERTY(sp.name, 'IsExpired') AS is_expired,
            LOGINPROPERTY(sp.name, 'IsLocked') AS is_locked,
            LOGINPROPERTY(sp.name, 'IsMustChange') AS must_change_password,
            LOGINPROPERTY(sp.name, 'BadPasswordCount') AS bad_password_count,
            LOGINPROPERTY(sp.name, 'LockoutTime') AS lockout_time,
            -- Server roles (comma-separated, NULL if no roles)
            STUFF((
                SELECT ',' + sr.name
                FROM sys.server_role_members srm2
                JOIN sys.server_principals sr ON srm2.role_principal_id = sr.principal_id
                WHERE srm2.member_principal_id = sp.principal_id
                ORDER BY sr.name
                FOR XML PATH(''), TYPE
            ).value('.', 'NVARCHAR(MAX)'), 1, 1, '') AS server_roles_csv
        FROM sys.server_principals sp
        LEFT JOIN sys.sql_logins sl ON sp.sid = sl.sid
        WHERE sp.name = ?
        """

        cursor.execute(combined_query, login_name)
        row = cursor.fetchone()

        if not row:
            return {
                'exists': False,
                'login_name': login_name,
                'message': 'Login não encontrado no servidor'
            }

        result = {
            'exists': True,
            'login_name': row.login_name,
            'login_type': row.login_type,
            'is_disabled': row.is_disabled,
            'create_date': row.create_date.isoformat() if row.create_date else None,
            'modify_date': row.modify_date.isoformat() if row.modify_date else None,
            'default_database': row.default_database_name,
            'default_language': row.default_language_name,
            'is_sql_login': row.is_sql_login
        }

        # Extract password policy from the combined result (only for SQL logins)
        if row.is_sql_login and row.is_policy_checked is not None:
            result['password_policy'] = {
                'is_policy_checked': row.is_policy_checked,
                'is_expiration_checked': row.is_expiration_checked,
                'password_last_set': str(row.password_last_set) if row.password_last_set else None,
                'days_until_expiration': row.days_until_expiration,
                'is_expired': row.is_expired,
                'is_locked': row.is_locked,
                'must_change_password': row.must_change_password,
                'bad_password_count': row.bad_password_count,
                'lockout_time': str(row.lockout_time) if row.lockout_time else None
            }

        # Extract server roles from the combined result
        result['server_roles'] = row.server_roles_csv.split(',') if row.server_roles_csv else []

        # 4. Databases mapeados
        # OPTIMIZED: Replaced cursor-based approach with a single dynamic SQL batch.
        # Builds one UNION ALL query across all ONLINE databases, reducing N roundtrips
        # (one per database) to a single sp_executesql call.
        mapped_query = """
        DECLARE @sql NVARCHAR(MAX) = N''
        DECLARE @login_name NVARCHAR(128) = ?

        SELECT @sql = @sql + N'
          SELECT ' + QUOTENAME(name, '''') + N' AS database_name,
                 dp.name AS user_name,
                 dp.default_schema_name AS default_schema,
                 dp.type_desc AS user_type
          FROM ' + QUOTENAME(name) + N'.sys.database_principals dp
          JOIN sys.server_principals sp ON dp.sid = sp.sid
          WHERE sp.name = @p_login
          UNION ALL'
        FROM sys.databases
        WHERE state_desc = 'ONLINE'

        IF LEN(@sql) > 10
        BEGIN
            SET @sql = LEFT(@sql, LEN(@sql) - 10)  -- Remove trailing UNION ALL
            SET @sql = @sql + N' ORDER BY database_name'
            EXEC sp_executesql @sql, N'@p_login NVARCHAR(128)', @p_login = @login_name
        END
        """

        cursor.execute(mapped_query, login_name)
        result['mapped_databases'] = []
        for r in cursor.fetchall():
            result['mapped_databases'].append({
                'database_name': r.database_name,
                'user_name': r.user_name,
                'default_schema': r.default_schema,
                'user_type': r.user_type
            })

        logger.info(f"Login details completed for {login_name}: exists={result['exists']}, roles={len(result['server_roles'])}, mapped_dbs={len(result['mapped_databases'])}")

        return result

    except pyodbc.Error as e:
        raise safe_http_error(500, e, f"database error fetching login details for {login_name} on {server_id}")

    except Exception as e:
        raise safe_http_error(500, e, f"fetching login details for {login_name} on {server_id}")

    finally:
        if conn and pool:
            pool.return_connection(server_id, conn)


@router.get("/server/{server_id}/search", response_model=GenericResponse)
async def search_login_or_user(server_id: str, name: str, pool: SQLServerConnectionPool = Depends(get_pool)):
    """
    Search for a login/user across the server and all databases
    """
    conn = None
    try:
        logger.info(f"Search requested for '{name}' on server: {server_id}")

        conn, pool = get_pooled_connection(server_id, pool)
        cursor = conn.cursor()

        # 1. Buscar logins no servidor
        logins_query = """
        SELECT
            sp.name AS login_name,
            sp.type_desc AS login_type,
            sp.is_disabled,
            sp.create_date,
            sp.default_database_name
        FROM sys.server_principals sp
        WHERE sp.name LIKE '%' + ? + '%'
            AND sp.type IN ('S', 'U', 'G', 'C', 'K')
        ORDER BY sp.name
        """

        cursor.execute(logins_query, name)
        logins = []
        for row in cursor.fetchall():
            logins.append({
                'login_name': row.login_name,
                'login_type': row.login_type,
                'is_disabled': row.is_disabled,
                'create_date': row.create_date.isoformat() if row.create_date else None,
                'default_database': row.default_database_name
            })

        # 2. Buscar usuários em todos os databases
        users_query = """
        DECLARE @users TABLE (
            database_name NVARCHAR(128),
            user_name NVARCHAR(128),
            user_type NVARCHAR(60),
            default_schema NVARCHAR(128),
            mapped_login NVARCHAR(128)
        )

        DECLARE @sql NVARCHAR(MAX)
        DECLARE @db_name NVARCHAR(128)
        DECLARE @search NVARCHAR(128) = ?

        DECLARE db_cursor CURSOR FOR
        SELECT name
        FROM sys.databases
        WHERE state_desc = 'ONLINE'

        OPEN db_cursor
        FETCH NEXT FROM db_cursor INTO @db_name

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @sql = N'USE [' + @db_name + N'];
            INSERT INTO @users (database_name, user_name, user_type, default_schema, mapped_login)
            SELECT
                ''' + @db_name + N''' AS database_name,
                dp.name AS user_name,
                dp.type_desc AS user_type,
                dp.default_schema_name,
                sp.name AS mapped_login
            FROM sys.database_principals dp
            LEFT JOIN sys.server_principals sp ON dp.sid = sp.sid
            WHERE dp.name LIKE ''%' + REPLACE(@search, '''', '''''') + N'%''
                AND dp.type IN (''S'', ''U'', ''G'', ''C'', ''K'')
                AND dp.name NOT IN (''dbo'', ''guest'', ''INFORMATION_SCHEMA'', ''sys'', ''public'')
            '

            BEGIN TRY
                EXEC sp_executesql @sql
            END TRY
            BEGIN CATCH
            END CATCH

            FETCH NEXT FROM db_cursor INTO @db_name
        END

        CLOSE db_cursor
        DEALLOCATE db_cursor

        SELECT database_name, user_name, user_type, default_schema, mapped_login
        FROM @users
        ORDER BY database_name, user_name
        """

        cursor.execute(users_query, name)
        users = []
        for row in cursor.fetchall():
            users.append({
                'database_name': row.database_name,
                'user_name': row.user_name,
                'user_type': row.user_type,
                'default_schema': row.default_schema,
                'mapped_login': row.mapped_login
            })

        result = {
            'search_term': name,
            'logins_found': len(logins),
            'users_found': len(users),
            'logins': logins,
            'users': users
        }

        logger.info(f"Search completed for '{name}' on {server_id}: {len(logins)} logins, {len(users)} users")

        return result

    except pyodbc.Error as e:
        raise safe_http_error(500, e, f"database error searching for {name} on {server_id}")

    except Exception as e:
        raise safe_http_error(500, e, f"searching for {name} on {server_id}")

    finally:
        if conn and pool:
            pool.return_connection(server_id, conn)


@router.get("/ad-user/{username}/details", response_model=GenericResponse)
async def get_ad_user_details(username: str):
    """
    Consulta Active Directory para obter detalhes de um utilizador Windows.
    Usa PowerShell Get-ADUser para consultar o AD.
    """
    import asyncio
    import subprocess
    import json as json_mod

    logger.info(f"AD lookup requested for: {username}")

    # Extrair samAccountName do formato DOMAIN\\user
    sam_name = username
    if '\\' in username:
        _, sam_name = username.split('\\', 1)

    # Allowlist defense-in-depth: rejeitar samAccountName com qualquer char fora do set AD valido.
    # Bloqueia command injection mesmo em contextos onde aspas pudessem ser concat em double-quoted PS.
    if not _AD_SAM_NAME_PATTERN.match(sam_name):
        logger.warning(f"AD lookup rejected — invalid samAccountName shape: {sam_name!r}")
        raise HTTPException(status_code=400, detail="Invalid samAccountName format")

    # Belt-and-suspenders: escape aspas simples em PowerShell ('' = ' escaped dentro de single-quoted string).
    sam_name = sam_name.replace("'", "''")

    # PowerShell script — evitar if inline dentro de hashtable (causa erro de sintaxe)
    ps_script = f"""
try {{
    Import-Module ActiveDirectory -ErrorAction Stop

    $user = Get-ADUser -Identity '{sam_name}' -Properties DisplayName, EmailAddress, Department, Title, Manager, Enabled, LockedOut, AccountExpirationDate, LastLogonDate, WhenCreated, WhenChanged, Description, Office, Company, MemberOf, PasswordLastSet, PasswordExpired, PasswordNeverExpires, BadLogonCount, LastBadPasswordAttempt -ErrorAction Stop

    # Resolver datas como strings (evitar if dentro de hashtable)
    $acctExp = $null; if ($user.AccountExpirationDate) {{ $acctExp = $user.AccountExpirationDate.ToString('yyyy-MM-ddTHH:mm:ss') }}
    $lastLogon = $null; if ($user.LastLogonDate) {{ $lastLogon = $user.LastLogonDate.ToString('yyyy-MM-ddTHH:mm:ss') }}
    $created = $null; if ($user.WhenCreated) {{ $created = $user.WhenCreated.ToString('yyyy-MM-ddTHH:mm:ss') }}
    $modified = $null; if ($user.WhenChanged) {{ $modified = $user.WhenChanged.ToString('yyyy-MM-ddTHH:mm:ss') }}
    $pwdSet = $null; if ($user.PasswordLastSet) {{ $pwdSet = $user.PasswordLastSet.ToString('yyyy-MM-ddTHH:mm:ss') }}
    $lastBadPwd = $null; if ($user.LastBadPasswordAttempt) {{ $lastBadPwd = $user.LastBadPasswordAttempt.ToString('yyyy-MM-ddTHH:mm:ss') }}

    # Resolver manager
    $managerName = ''
    if ($user.Manager) {{
        try {{
            $mgr = Get-ADUser $user.Manager -Properties DisplayName -ErrorAction SilentlyContinue
            if ($mgr.DisplayName) {{ $managerName = $mgr.DisplayName }}
            else {{ $managerName = $user.Manager -replace '^CN=([^,]+).*', '$1' }}
        }} catch {{
            $managerName = $user.Manager -replace '^CN=([^,]+).*', '$1'
        }}
    }}

    # Resolver grupos
    $groups = @()
    if ($user.MemberOf) {{
        foreach ($g in $user.MemberOf) {{
            try {{
                $grp = Get-ADGroup $g -ErrorAction SilentlyContinue
                if ($grp) {{ $groups += $grp.Name }}
                else {{ $groups += ($g -replace '^CN=([^,]+).*', '$1') }}
            }} catch {{
                $groups += ($g -replace '^CN=([^,]+).*', '$1')
            }}
        }}
    }}

    # Montar resultado com variaveis pre-calculadas
    $result = @{{
        success = $true
        sam_account_name = [string]$user.SamAccountName
        display_name = [string]$user.DisplayName
        email = [string]$user.EmailAddress
        department = [string]$user.Department
        title = [string]$user.Title
        manager = $managerName
        enabled = [bool]$user.Enabled
        locked_out = [bool]$user.LockedOut
        account_expires = $acctExp
        last_logon = $lastLogon
        created = $created
        modified = $modified
        description = [string]$user.Description
        office = [string]$user.Office
        company = [string]$user.Company
        groups = $groups
        password_last_set = $pwdSet
        password_expired = [bool]$user.PasswordExpired
        password_never_expires = [bool]$user.PasswordNeverExpires
        bad_logon_count = [int]$user.BadLogonCount
        last_bad_password = $lastBadPwd
    }}
    $result | ConvertTo-Json -Depth 3 -Compress
}} catch {{
    @{{ success = $false; error = $_.Exception.Message; username = '{sam_name}' }} | ConvertTo-Json -Compress
}}
"""

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
            capture_output=True, text=True, timeout=20
        ))

        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()

        logger.info(f"AD PS result for {username}: rc={result.returncode}, stdout_len={len(stdout)}, stderr_len={len(stderr)}")

        if stdout:
            try:
                data = json_mod.loads(stdout)
                if data.get('success'):
                    logger.info(f"AD lookup success for {username}: {data.get('display_name', 'N/A')}")
                    return data
                else:
                    logger.warning(f"AD lookup failed for {username}: {data.get('error', 'Unknown')}")
                    return {
                        'success': False,
                        'username': username,
                        'login_type': 'WINDOWS_LOGIN',
                        'error': data.get('error', 'Utilizador nao encontrado no Active Directory'),
                        'status': 'not_found'
                    }
            except json_mod.JSONDecodeError as je:
                logger.error(f"AD JSON parse error for {username}: {je}, stdout={stdout[:300]}")
                return {
                    'success': False,
                    'username': username,
                    'login_type': 'WINDOWS_LOGIN',
                    'error': f'Erro ao processar resposta do AD: {stdout[:200]}',
                    'status': 'parse_error'
                }
        else:
            logger.warning(f"AD PowerShell empty output for {username}: stderr={stderr[:300]}")
            return {
                'success': False,
                'username': username,
                'login_type': 'WINDOWS_LOGIN',
                'error': f'Sem resposta do AD. Stderr: {stderr[:200]}' if stderr else 'PowerShell nao retornou dados do AD',
                'status': 'error'
            }

    except subprocess.TimeoutExpired:
        logger.error(f"AD lookup timeout for {username}")
        return {
            'success': False,
            'username': username,
            'error': 'Timeout ao consultar Active Directory (>20s)',
            'status': 'timeout'
        }
    except Exception as e:
        logger.error(f"AD lookup error for {username}: {e}", exc_info=True)
        return {
            'success': False,
            'username': username,
            'error': str(e),
            'status': 'error'
        }


# =============================================
# AD Group Members Endpoint
# =============================================
@router.get("/ad-group/{groupname}/members", response_model=GenericResponse)
async def get_ad_group_members(groupname: str):
    """Consulta membros de um grupo do Active Directory via PowerShell Get-ADGroupMember"""
    import subprocess
    import json as json_mod

    logger.info(f"AD group lookup requested for: {groupname}")

    # Extrair nome do grupo (remover dominio se presente)
    if '\\' in groupname:
        group_name = groupname.split('\\', 1)[1]
    else:
        group_name = groupname

    # Allowlist defense-in-depth: nome de grupo AD permite letras, digitos, ponto, underscore, hifen, espaco.
    # Rejeita qualquer char metachar de PowerShell (quotes, backtick, $, |, &, ;, parenteses, etc.).
    if not _AD_GROUP_NAME_PATTERN.match(group_name):
        logger.warning(f"AD group lookup rejected — invalid group name shape: {group_name!r}")
        return {'success': False, 'error': 'Nome do grupo invalido', 'total_members': 0}

    # Belt-and-suspenders: escape aspas simples em PowerShell single-quoted.
    safe_name = group_name.replace("'", "''")

    ps_script = f"""
Import-Module ActiveDirectory -ErrorAction SilentlyContinue

try {{
    $group = Get-ADGroup -Identity '{safe_name}' -Properties Description, ManagedBy, WhenCreated, WhenChanged -ErrorAction Stop

    $members = @()
    $nestedGroups = @()

    try {{
        $rawMembers = Get-ADGroupMember -Identity '{safe_name}' -ErrorAction Stop

        foreach ($m in $rawMembers) {{
            if ($m.objectClass -eq 'group') {{
                $nestedGroups += @{{
                    'name' = $m.Name
                    'sam_account_name' = $m.SamAccountName
                    'object_class' = 'group'
                }}
            }} else {{
                try {{
                    $u = Get-ADUser -Identity $m.SamAccountName -Properties DisplayName, EmailAddress, Department, Title, Enabled, LastLogonDate -ErrorAction SilentlyContinue
                    if ($u) {{
                        $lastLogon = if ($u.LastLogonDate) {{ $u.LastLogonDate.ToString('yyyy-MM-ddTHH:mm:ss') }} else {{ $null }}
                        $members += @{{
                            'name' = $u.Name
                            'display_name' = if ($u.DisplayName) {{ $u.DisplayName }} else {{ $u.Name }}
                            'sam_account_name' = $u.SamAccountName
                            'email' = if ($u.EmailAddress) {{ $u.EmailAddress }} else {{ '' }}
                            'department' = if ($u.Department) {{ $u.Department }} else {{ '' }}
                            'title' = if ($u.Title) {{ $u.Title }} else {{ '' }}
                            'enabled' = $u.Enabled
                            'last_logon' = $lastLogon
                            'object_class' = 'user'
                        }}
                    }} else {{
                        $members += @{{
                            'name' = $m.Name
                            'display_name' = $m.Name
                            'sam_account_name' = $m.SamAccountName
                            'email' = ''
                            'department' = ''
                            'title' = ''
                            'enabled' = $true
                            'last_logon' = $null
                            'object_class' = 'user'
                        }}
                    }}
                }} catch {{
                    $members += @{{
                        'name' = $m.Name
                        'display_name' = $m.Name
                        'sam_account_name' = $m.SamAccountName
                        'email' = ''
                        'department' = ''
                        'title' = ''
                        'enabled' = $true
                        'last_logon' = $null
                        'object_class' = 'user'
                    }}
                }}
            }}
        }}
    }} catch {{
        # Grupo pode nao ter membros ou acesso negado
    }}

    $managedByName = ''
    if ($group.ManagedBy) {{
        try {{
            $mgr = Get-ADUser -Identity $group.ManagedBy -Properties DisplayName -ErrorAction SilentlyContinue
            if ($mgr) {{ $managedByName = if ($mgr.DisplayName) {{ $mgr.DisplayName }} else {{ $mgr.Name }} }}
        }} catch {{ }}
    }}

    $result = @{{
        'success' = $true
        'group_name' = $group.Name
        'description' = if ($group.Description) {{ $group.Description }} else {{ '' }}
        'managed_by' = $managedByName
        'created' = if ($group.WhenCreated) {{ $group.WhenCreated.ToString('yyyy-MM-ddTHH:mm:ss') }} else {{ '' }}
        'modified' = if ($group.WhenChanged) {{ $group.WhenChanged.ToString('yyyy-MM-ddTHH:mm:ss') }} else {{ '' }}
        'members' = $members
        'nested_groups' = $nestedGroups
        'total_members' = $members.Count
        'total_nested_groups' = $nestedGroups.Count
    }}

    $result | ConvertTo-Json -Depth 4 -Compress
}} catch {{
    @{{ 'success' = $false; 'error' = $_.Exception.Message }} | ConvertTo-Json -Compress
}}
"""

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=30
        )

        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()

        if stdout:
            try:
                data = json_mod.loads(stdout)
                if data.get('success'):
                    logger.info(f"AD group {groupname}: {data.get('total_members', 0)} members found")
                    return data
                else:
                    logger.warning(f"AD group lookup failed for {groupname}: {data.get('error')}")
                    return {
                        'success': False,
                        'group_name': groupname,
                        'error': data.get('error', 'Grupo nao encontrado no Active Directory'),
                        'total_members': 0
                    }
            except json_mod.JSONDecodeError as je:
                logger.error(f"AD group JSON parse error for {groupname}: {je}, stdout={stdout[:300]}")
                return {
                    'success': False,
                    'group_name': groupname,
                    'error': f'Erro ao processar resposta do AD: {stdout[:200]}',
                    'total_members': 0
                }
        else:
            logger.warning(f"AD group PowerShell empty output for {groupname}: stderr={stderr[:300]}")
            return {
                'success': False,
                'group_name': groupname,
                'error': f'Sem resposta do AD. {stderr[:200]}' if stderr else 'PowerShell nao retornou dados do AD',
                'total_members': 0
            }

    except subprocess.TimeoutExpired:
        logger.error(f"AD group lookup timeout for {groupname}")
        return {
            'success': False,
            'group_name': groupname,
            'error': 'Timeout ao consultar Active Directory (>30s)',
            'total_members': 0
        }
    except Exception as e:
        logger.error(f"AD group lookup error for {groupname}: {e}", exc_info=True)
        return {
            'success': False,
            'group_name': groupname,
            'error': str(e),
            'total_members': 0
        }
