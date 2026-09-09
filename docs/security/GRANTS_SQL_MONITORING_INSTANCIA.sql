-- =============================================================================
-- GRANTS_SQL_MONITORING_INSTANCIA.sql  (canonico das instancias monitorizadas; WatcherDB V3.4, 2026-09-08)
-- Completa as permissoes minimas do login EXISTENTE `sql_monitoring` em cada
-- instancia. Derivado de docs/security/LEAST_PRIVILEGE_SETUP.sql (tier STANDARD),
-- sem CREATE LOGIN, sem placeholders <DOMAIN>, sem a parte da WatcherDB_Intelligence
-- (essa so' existe no servidor master).
--
-- COMO CORRER NAS 63 DE UMA VEZ (SSMS, sem codigo):
--   1. View > Registered Servers > Local Server Groups > botao direito > Import...
--      -> ficheiro .regsrvr gerado por scripts/qa/runtime/gera_regsrvr.py (fica em %TEMP%)
--   2. Botao direito no grupo "WatcherDB-63" > New Query  (a barra da query fica ROSA =
--      multi-servidor; a autenticacao e' a da tua sessao SSMS, conta de administracao)
--   3. Colar este ficheiro inteiro > Execute. O resultado final e' UMA LINHA POR SERVIDOR
--      com as 9 verificacoes; o SSMS acrescenta a coluna "Server Name".
--   4. Repetir o pre-flight: py scripts/qa/runtime/p2_preflight_permissoes.py  -> tudo a 1.
--
-- IDEMPOTENTE: GRANT repetido e' no-op; CREATE USER e ADD MEMBER guardados por IF NOT EXISTS.
-- Se o login nao existir na instancia, o script pára nessa instancia com erro (nao cria).
-- ROLLBACK (por instancia): REVOKE das mesmas permissoes / ALTER ROLE ... DROP MEMBER.
-- Gaps medidos em 2026-09-08 (pre-flight): VIEW ANY DEFINITION em 6 instancias; SELECT
-- msdb.dbo.sysjobs e xp_readerrorlog em 1; SQLAgentReaderRole em 63. As restantes ja' estavam.
-- =============================================================================
SET NOCOUNT ON;

USE master;
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'sql_monitoring')
BEGIN
    RAISERROR('sql_monitoring: login NAO existe nesta instancia -- nada feito', 16, 1);
    RETURN;
END

-- ---- servidor -----------------------------------------------------------------
GRANT VIEW SERVER STATE   TO [sql_monitoring];
GRANT VIEW ANY DEFINITION TO [sql_monitoring];
GRANT VIEW ANY DATABASE   TO [sql_monitoring];

-- ---- master: user + xp_readerrorlog + SHOWPLAN (GAP 1 e GAP 3 do audit 2026-08-20) ----
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'sql_monitoring')
    CREATE USER [sql_monitoring] FOR LOGIN [sql_monitoring];
GRANT EXECUTE ON sys.xp_readerrorlog TO [sql_monitoring];
GRANT SHOWPLAN TO [sql_monitoring];
GO

-- ---- msdb: backups, jobs, SQLAgentReaderRole -----------------------------------
USE msdb;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'sql_monitoring')
    CREATE USER [sql_monitoring] FOR LOGIN [sql_monitoring];
GRANT SELECT ON dbo.backupset          TO [sql_monitoring];
GRANT SELECT ON dbo.backupmediafamily  TO [sql_monitoring];
GRANT SELECT ON dbo.backupmediaset     TO [sql_monitoring];
GRANT SELECT ON dbo.backupfile         TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobs            TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobhistory      TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobsteps        TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobschedules    TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobservers      TO [sql_monitoring];
GRANT SELECT ON dbo.sysoperators       TO [sql_monitoring];
GRANT SELECT ON dbo.sysschedules       TO [sql_monitoring];
GRANT SELECT ON dbo.syscategories      TO [sql_monitoring];
GRANT EXECUTE ON dbo.sp_help_jobactivity TO [sql_monitoring];
IF NOT EXISTS (
    SELECT 1
    FROM sys.database_role_members rm
    JOIN sys.database_principals r ON r.principal_id = rm.role_principal_id
    JOIN sys.database_principals m ON m.principal_id = rm.member_principal_id
    WHERE r.name = N'SQLAgentReaderRole' AND m.name = N'sql_monitoring'
)
    -- sp_addrolemember e' aceite em 2005..2022; ALTER ROLE ... ADD MEMBER so' existe a partir de 2012
    -- e o PARSER rejeita o lote inteiro em 2008/2005 (erro de sintaxe medido em 1 instancia, 2026-09-08).
    EXEC sp_addrolemember N'SQLAgentReaderRole', N'sql_monitoring';
GO

-- ---- verificacao: 1 linha por servidor, como o sql_monitoring veria ---------------
USE master;
EXECUTE AS LOGIN = N'sql_monitoring';
SELECT SUSER_SNAME()                                                     AS login_efectivo,
       IS_SRVROLEMEMBER('sysadmin')                                      AS sysadmin,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE')                AS view_server_state,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW ANY DEFINITION')              AS view_any_definition,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW ANY DATABASE')                AS view_any_database,
       HAS_PERMS_BY_NAME('msdb', 'DATABASE', 'CONNECT')                  AS msdb_connect,
       HAS_PERMS_BY_NAME('msdb.dbo.backupset', 'OBJECT', 'SELECT')       AS msdb_backupset,
       HAS_PERMS_BY_NAME('msdb.dbo.sysjobs', 'OBJECT', 'SELECT')         AS msdb_sysjobs,
       HAS_PERMS_BY_NAME('master.dbo.xp_readerrorlog', 'OBJECT', 'EXECUTE') AS xp_readerrorlog;
REVERT;
GO
