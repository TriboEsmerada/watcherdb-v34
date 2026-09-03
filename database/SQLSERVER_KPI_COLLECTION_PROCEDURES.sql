-- ============================================================================
-- WATCHERDB INTELLIGENCE V2 - SQL SERVER KPI COLLECTION PROCEDURES
-- ============================================================================
-- Stored Procedures para coleta de dados KPI SQL Server
--
-- COMPONENTES:
--   - 11 Procedures de coleta (um para cada KPI)
--   - 1 Procedure master (executa todos)
--   - SQL Agent Job para execução automática
--
-- AUTOR: WatcherDB Team
-- DATA: 2025-11-27
-- VERSÃO: 1.0.0
-- ============================================================================

USE [WatcherDB_Intelligence_V2];
GO

PRINT '============================================================================';
PRINT 'WATCHERDB INTELLIGENCE V2 - PROCEDURES DE COLETA KPI';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
GO

-- ============================================================================
-- PROCEDURE 1: COLETA ALWAYS ON STATUS
-- ============================================================================

PRINT '';
PRINT '-- [1/12] Criando procedure: usp_Collect_AlwaysOn_Status...';
GO

IF OBJECT_ID('dbo.usp_Collect_AlwaysOn_Status', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_AlwaysOn_Status;
GO

CREATE PROCEDURE dbo.usp_Collect_AlwaysOn_Status
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG;

        -- Coletar status Always On
        INSERT INTO dbo.KPI_MSSQL_ALWAYSON_STATUS_STG (
            AgName, Instance, [Database],
            Pri_Synch_State, Pri_Synch_Health, Pri_Is_Suspended,
            Sec_Synch_State, Sec_Synch_Health, Sec_Is_Suspended,
            Commit_Diff_Secs, Update_TS
        )
        SELECT
            ag.name AS AgName,
            @@SERVERNAME AS Instance,
            db.database_name AS [Database],
            -- Primary replica
            ISNULL(ars1.synchronization_state_desc, 'UNKNOWN') AS Pri_Synch_State,
            ISNULL(ars1.synchronization_health_desc, 'UNKNOWN') AS Pri_Synch_Health,
            ISNULL(ars1.is_suspended, 0) AS Pri_Is_Suspended,
            -- Secondary replica
            ISNULL(ars2.synchronization_state_desc, 'UNKNOWN') AS Sec_Synch_State,
            ISNULL(ars2.synchronization_health_desc, 'UNKNOWN') AS Sec_Synch_Health,
            ISNULL(ars2.is_suspended, 0) AS Sec_Is_Suspended,
            -- Lag
            ISNULL(DATEDIFF(SECOND, ars1.last_commit_time, ars2.last_commit_time), 0) AS Commit_Diff_Secs,
            GETDATE() AS Update_TS
        FROM sys.availability_groups ag
        INNER JOIN sys.dm_hadr_availability_replica_states ars1
            ON ag.group_id = ars1.group_id AND ars1.role_desc = 'PRIMARY'
        INNER JOIN sys.availability_databases_cluster db
            ON ag.group_id = db.group_id
        LEFT JOIN sys.dm_hadr_availability_replica_states ars2
            ON ag.group_id = ars2.group_id AND ars2.role_desc = 'SECONDARY'
        WHERE ag.name IS NOT NULL;

        PRINT '  [OK] AlwaysOn Status coletado: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] AlwaysOn Status: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_AlwaysOn_Status criada';
GO

-- ============================================================================
-- PROCEDURE 2: COLETA BACKUPS
-- ============================================================================

PRINT '';
PRINT '-- [2/12] Criando procedure: usp_Collect_Backups...';
GO

IF OBJECT_ID('dbo.usp_Collect_Backups', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Backups;
GO

CREATE PROCEDURE dbo.usp_Collect_Backups
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_BACKUPS_STG;

        -- Coletar histórico de backups
        INSERT INTO dbo.KPI_MSSQL_BACKUPS_STG (
            Instance, [Database], Backup_Type,
            Last_Backup_Date, Hours_Since_Backup,
            Backup_Size_MB, Backup_Duration_Sec, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            d.name AS [Database],
            CASE b.type
                WHEN 'D' THEN 'FULL'
                WHEN 'I' THEN 'DIFF'
                WHEN 'L' THEN 'LOG'
            END AS Backup_Type,
            b.backup_finish_date AS Last_Backup_Date,
            DATEDIFF(HOUR, b.backup_finish_date, GETDATE()) AS Hours_Since_Backup,
            CAST(b.backup_size / 1024.0 / 1024.0 AS DECIMAL(18,2)) AS Backup_Size_MB,
            DATEDIFF(SECOND, b.backup_start_date, b.backup_finish_date) AS Backup_Duration_Sec,
            GETDATE() AS Update_TS
        FROM sys.databases d
        CROSS APPLY (
            SELECT TOP 1
                bs.type,
                bs.backup_start_date,
                bs.backup_finish_date,
                bs.backup_size
            FROM msdb.dbo.backupset bs
            WHERE bs.database_name = d.name
            ORDER BY bs.backup_finish_date DESC
        ) b
        WHERE d.name NOT IN ('tempdb')
          AND d.state_desc = 'ONLINE';

        PRINT '  [OK] Backups coletados: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Backups: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Backups criada';
GO

-- ============================================================================
-- PROCEDURE 3: COLETA BLOCKED SESSIONS
-- ============================================================================

PRINT '';
PRINT '-- [3/12] Criando procedure: usp_Collect_Blocked_Sessions...';
GO

IF OBJECT_ID('dbo.usp_Collect_Blocked_Sessions', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Blocked_Sessions;
GO

CREATE PROCEDURE dbo.usp_Collect_Blocked_Sessions
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG;

        -- Coletar sessões bloqueadas
        INSERT INTO dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG (
            Instance, Session_Id, Blocked_By, Wait_Time_Sec,
            Wait_Type, [Database], [Status], Command,
            Blocking_Level, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            r.session_id AS Session_Id,
            r.blocking_session_id AS Blocked_By,
            r.wait_time / 1000 AS Wait_Time_Sec,
            r.wait_type AS Wait_Type,
            DB_NAME(r.database_id) AS [Database],
            r.status AS [Status],
            r.command AS Command,
            0 AS Blocking_Level, -- Será calculado depois
            GETDATE() AS Update_TS
        FROM sys.dm_exec_requests r
        WHERE r.blocking_session_id <> 0
          AND r.session_id <> @@SPID;

        PRINT '  [OK] Blocked Sessions coletadas: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Blocked Sessions: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Blocked_Sessions criada';
GO

-- ============================================================================
-- PROCEDURE 4: COLETA DATABASE AVAILABILITY
-- ============================================================================

PRINT '';
PRINT '-- [4/12] Criando procedure: usp_Collect_DB_Availability...';
GO

IF OBJECT_ID('dbo.usp_Collect_DB_Availability', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_DB_Availability;
GO

CREATE PROCEDURE dbo.usp_Collect_DB_Availability
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG;

        -- Coletar disponibilidade de databases com mirroring_role
        INSERT INTO dbo.KPI_MSSQL_DB_AVAILABILITY_STG (
            Instance, [Database], [State], Is_Available,
            Recovery_Model, Mirroring_Role, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            db.name AS [Database],
            db.state_desc AS [State],
            CASE WHEN db.state_desc = 'ONLINE' THEN 1 ELSE 0 END AS Is_Available,
            db.recovery_model_desc AS Recovery_Model,
            m.mirroring_role_desc AS Mirroring_Role,
            GETDATE() AS Update_TS
        FROM sys.databases db WITH(NOLOCK)
        LEFT OUTER JOIN sys.database_mirroring m WITH(NOLOCK) 
            ON db.database_id = m.database_id
        WHERE db.name NOT IN ('tempdb');

        -- Inserir dados em histórico
        INSERT INTO dbo.KPI_MSSQL_DB_AVAILABILITY_HIST (
            Instance, [Database], [State], Is_Available,
            Recovery_Model, Mirroring_Role, Update_TS
        )
        SELECT
            Instance, [Database], [State], Is_Available,
            Recovery_Model, Mirroring_Role, Update_TS
        FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG;

        PRINT '  [OK] DB Availability coletada: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] DB Availability: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_DB_Availability criada';
GO

-- ============================================================================
-- PROCEDURE 5: COLETA DISK USAGE
-- ============================================================================

PRINT '';
PRINT '-- [5/12] Criando procedure: usp_Collect_Disk_Usage...';
GO

IF OBJECT_ID('dbo.usp_Collect_Disk_Usage', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Disk_Usage;
GO

CREATE PROCEDURE dbo.usp_Collect_Disk_Usage
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_DISK_USAGE_STG;

        -- Coletar uso de disco
        INSERT INTO dbo.KPI_MSSQL_DISK_USAGE_STG (
            Instance, Drive, Total_MB, Free_MB, Used_MB,
            Percent_Free, Update_TS
        )
        SELECT DISTINCT
            @@SERVERNAME AS Instance,
            vs.volume_mount_point AS Drive,
            CAST(vs.total_bytes / 1024.0 / 1024.0 AS DECIMAL(18,2)) AS Total_MB,
            CAST(vs.available_bytes / 1024.0 / 1024.0 AS DECIMAL(18,2)) AS Free_MB,
            CAST((vs.total_bytes - vs.available_bytes) / 1024.0 / 1024.0 AS DECIMAL(18,2)) AS Used_MB,
            CAST(vs.available_bytes * 100.0 / vs.total_bytes AS DECIMAL(5,2)) AS Percent_Free,
            GETDATE() AS Update_TS
        FROM sys.master_files mf
        CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs;

        -- Inserir dados em histórico
        INSERT INTO dbo.KPI_MSSQL_DISK_USAGE_HIST (
            Instance, Drive, Total_MB, Free_MB, Used_MB,
            Percent_Free, Update_TS
        )
        SELECT
            Instance, Drive, Total_MB, Free_MB, Used_MB,
            Percent_Free, Update_TS
        FROM dbo.KPI_MSSQL_DISK_USAGE_STG;

        PRINT '  [OK] Disk Usage coletado: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Disk Usage: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Disk_Usage criada';
GO

-- ============================================================================
-- PROCEDURE 6: COLETA FILEGROUP USAGE
-- ============================================================================

PRINT '';
PRINT '-- [6/12] Criando procedure: usp_Collect_Filegroup_Usage...';
GO

IF OBJECT_ID('dbo.usp_Collect_Filegroup_Usage', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Filegroup_Usage;
GO

CREATE PROCEDURE dbo.usp_Collect_Filegroup_Usage
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_FG_USAGE_STG;

        -- Coletar uso de filegroups
        INSERT INTO dbo.KPI_MSSQL_FG_USAGE_STG (
            Instance, [Database], Filegroup, Total_MB, Used_MB,
            Free_MB, Percent_Used, Max_Size_MB, Growth_Type, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            DB_NAME(mf.database_id) AS [Database],
            fg.name AS Filegroup,
            CAST(SUM(mf.size) * 8.0 / 1024 AS DECIMAL(18,2)) AS Total_MB,
            CAST(SUM(ISNULL(FILEPROPERTY(mf.name, 'SpaceUsed'), 0)) * 8.0 / 1024 AS DECIMAL(18,2)) AS Used_MB,
            CAST(SUM(mf.size - ISNULL(FILEPROPERTY(mf.name, 'SpaceUsed'), 0)) * 8.0 / 1024 AS DECIMAL(18,2)) AS Free_MB,
            CASE
                WHEN SUM(mf.size) > 0 THEN
                    CAST(SUM(ISNULL(FILEPROPERTY(mf.name, 'SpaceUsed'), 0)) * 100.0 / SUM(mf.size) AS DECIMAL(5,2))
                ELSE 0
            END AS Percent_Used,
            CASE
                WHEN MAX(mf.max_size) = -1 THEN 999999999
                ELSE CAST(MAX(mf.max_size) * 8.0 / 1024 AS DECIMAL(18,2))
            END AS Max_Size_MB,
            CASE MAX(mf.is_percent_growth)
                WHEN 1 THEN 'PERCENT'
                ELSE 'MB'
            END AS Growth_Type,
            GETDATE() AS Update_TS
        FROM sys.master_files mf
        INNER JOIN sys.filegroups fg
            ON mf.data_space_id = fg.data_space_id
        WHERE mf.type_desc = 'ROWS'
        GROUP BY mf.database_id, fg.name;

        PRINT '  [OK] Filegroup Usage coletado: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Filegroup Usage: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Filegroup_Usage criada';
GO

-- ============================================================================
-- PROCEDURE 7: COLETA INSTANCE AVAILABILITY
-- ============================================================================

PRINT '';
PRINT '-- [7/12] Criando procedure: usp_Collect_Instance_Availability...';
GO

IF OBJECT_ID('dbo.usp_Collect_Instance_Availability', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Instance_Availability;
GO

CREATE PROCEDURE dbo.usp_Collect_Instance_Availability
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_INST_AVAILABILITY_STG;

        -- Coletar disponibilidade da instância
        INSERT INTO dbo.KPI_MSSQL_INST_AVAILABILITY_STG (
            Instance, Is_Available, Uptime_Hours,
            [Version], Edition, Collation, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            1 AS Is_Available,
            DATEDIFF(HOUR, sqlserver_start_time, GETDATE()) AS Uptime_Hours,
            CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(64)) AS [Version],
            CAST(SERVERPROPERTY('Edition') AS VARCHAR(64)) AS Edition,
            CAST(SERVERPROPERTY('Collation') AS VARCHAR(128)) AS Collation,
            GETDATE() AS Update_TS
        FROM sys.dm_os_sys_info;

        PRINT '  [OK] Instance Availability coletada: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Instance Availability: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Instance_Availability criada';
GO

-- ============================================================================
-- PROCEDURE 8: COLETA LONG LOCKS
-- ============================================================================

PRINT '';
PRINT '-- [8/12] Criando procedure: usp_Collect_Long_Locks...';
GO

IF OBJECT_ID('dbo.usp_Collect_Long_Locks', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Long_Locks;
GO

CREATE PROCEDURE dbo.usp_Collect_Long_Locks
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_LONG_LOCKS_STG;

        -- Coletar locks de longa duração (> 60 segundos)
        INSERT INTO dbo.KPI_MSSQL_LONG_LOCKS_STG (
            Instance, Session_Id, Lock_Type, Lock_Mode,
            Resource_Type, Resource_Desc, Duration_Sec,
            [Database], Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            tl.request_session_id AS Session_Id,
            tl.resource_type AS Lock_Type,
            tl.request_mode AS Lock_Mode,
            tl.resource_type AS Resource_Type,
            tl.resource_description AS Resource_Desc,
            DATEDIFF(SECOND, t.transaction_begin_time, GETDATE()) AS Duration_Sec,
            DB_NAME(tl.resource_database_id) AS [Database],
            GETDATE() AS Update_TS
        FROM sys.dm_tran_locks tl
        INNER JOIN sys.dm_tran_active_transactions t
            ON tl.request_owner_id = t.transaction_id
        WHERE DATEDIFF(SECOND, t.transaction_begin_time, GETDATE()) >= 60
          AND tl.request_session_id <> @@SPID;

        PRINT '  [OK] Long Locks coletados: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Long Locks: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Long_Locks criada';
GO

-- ============================================================================
-- PROCEDURE 9: COLETA PROCESSES
-- ============================================================================

PRINT '';
PRINT '-- [9/12] Criando procedure: usp_Collect_Processes...';
GO

IF OBJECT_ID('dbo.usp_Collect_Processes', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Processes;
GO

CREATE PROCEDURE dbo.usp_Collect_Processes
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_PROCESSES_STG;

        -- Coletar processos/sessões ativas
        INSERT INTO dbo.KPI_MSSQL_PROCESSES_STG (
            Instance, Session_Id, [Status], Command,
            [Database], [User], CPU_Time_MS, Total_Elapsed_Time,
            Reads, Writes, Wait_Type, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            s.session_id AS Session_Id,
            s.status AS [Status],
            ISNULL(r.command, 'AWAITING COMMAND') AS Command,
            DB_NAME(s.database_id) AS [Database],
            s.login_name AS [User],
            ISNULL(r.cpu_time, 0) AS CPU_Time_MS,
            ISNULL(r.total_elapsed_time, 0) AS Total_Elapsed_Time,
            ISNULL(r.reads, 0) AS Reads,
            ISNULL(r.writes, 0) AS Writes,
            r.wait_type AS Wait_Type,
            GETDATE() AS Update_TS
        FROM sys.dm_exec_sessions s
        LEFT JOIN sys.dm_exec_requests r
            ON s.session_id = r.session_id
        WHERE s.session_id <> @@SPID
          AND s.is_user_process = 1;

        PRINT '  [OK] Processes coletados: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Processes: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Processes criada';
GO

-- ============================================================================
-- PROCEDURE 10: COLETA TRANSACTION LOG USAGE
-- ============================================================================

PRINT '';
PRINT '-- [10/12] Criando procedure: usp_Collect_TLog_Usage...';
GO

IF OBJECT_ID('dbo.usp_Collect_TLog_Usage', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_TLog_Usage;
GO

CREATE PROCEDURE dbo.usp_Collect_TLog_Usage
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_TLOG_USAGE_STG;

        -- Coletar uso de transaction logs
        INSERT INTO dbo.KPI_MSSQL_TLOG_USAGE_STG (
            Instance, [Database], Current_MB, Used_MB,
            Max_Available_MB, Percent_Used, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            DB_NAME(database_id) AS [Database],
            CAST(SUM(size) * 8.0 / 1024 AS DECIMAL(18,2)) AS Current_MB,
            CAST(SUM(ISNULL(FILEPROPERTY(name, 'SpaceUsed'), 0)) * 8.0 / 1024 AS DECIMAL(18,2)) AS Used_MB,
            CASE
                WHEN MAX(max_size) = -1 THEN 999999999
                ELSE CAST(MAX(max_size) * 8.0 / 1024 AS DECIMAL(18,2))
            END AS Max_Available_MB,
            CASE
                WHEN SUM(size) > 0 THEN
                    CAST(SUM(ISNULL(FILEPROPERTY(name, 'SpaceUsed'), 0)) * 100.0 / SUM(size) AS DECIMAL(5,2))
                ELSE 0
            END AS Percent_Used,
            GETDATE() AS Update_TS
        FROM sys.master_files
        WHERE type_desc = 'LOG'
        GROUP BY database_id;

        -- Inserir dados em histórico
        INSERT INTO dbo.KPI_MSSQL_TLOG_USAGE_HIST (
            Instance, [Database], Current_MB, Used_MB,
            Max_Available_MB, Percent_Used, Update_TS
        )
        SELECT
            Instance, [Database], Current_MB, Used_MB,
            Max_Available_MB, Percent_Used, Update_TS
        FROM dbo.KPI_MSSQL_TLOG_USAGE_STG;

        PRINT '  [OK] TLog Usage coletado: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] TLog Usage: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_TLog_Usage criada';
GO

-- ============================================================================
-- PROCEDURE 11: COLETA BLOCKED USERS (AGREGADO)
-- ============================================================================

PRINT '';
PRINT '-- [11/12] Criando procedure: usp_Collect_Blocked_Users...';
GO

IF OBJECT_ID('dbo.usp_Collect_Blocked_Users', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Blocked_Users;
GO

CREATE PROCEDURE dbo.usp_Collect_Blocked_Users
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_BLOCKED_USERS_STG;

        -- Coletar usuários bloqueados (agregado por usuário)
        INSERT INTO dbo.KPI_MSSQL_BLOCKED_USERS_STG (
            Instance, [User], [Database], Blocked_Count,
            Max_Wait_Time_Sec, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            s.login_name AS [User],
            DB_NAME(r.database_id) AS [Database],
            COUNT(*) AS Blocked_Count,
            MAX(r.wait_time / 1000) AS Max_Wait_Time_Sec,
            GETDATE() AS Update_TS
        FROM sys.dm_exec_requests r
        INNER JOIN sys.dm_exec_sessions s
            ON r.session_id = s.session_id
        WHERE r.blocking_session_id <> 0
          AND r.session_id <> @@SPID
        GROUP BY s.login_name, r.database_id;

        PRINT '  [OK] Blocked Users coletados: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Blocked Users: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Blocked_Users criada';
GO

-- ============================================================================
-- PROCEDURE MASTER: EXECUTA TODAS AS COLETAS
-- ============================================================================

PRINT '';
PRINT '-- [12/12] Criando procedure MASTER: usp_Collect_All_KPIs...';
GO

IF OBJECT_ID('dbo.usp_Collect_All_KPIs', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_All_KPIs;
GO

CREATE PROCEDURE dbo.usp_Collect_All_KPIs
    @Debug BIT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @StartTime DATETIME2 = GETDATE();
    DECLARE @ErrorCount INT = 0;
    DECLARE @SuccessCount INT = 0;

    PRINT '';
    PRINT '============================================================================';
    PRINT 'WATCHERDB INTELLIGENCE V2 - COLETA COMPLETA DE KPIs';
    PRINT '============================================================================';
    PRINT 'Início: ' + CONVERT(VARCHAR(23), @StartTime, 121);
    PRINT 'Servidor: ' + @@SERVERNAME;
    PRINT '';

    -- 1. AlwaysOn Status
    BEGIN TRY
        IF @Debug = 1 PRINT '[1/11] Coletando AlwaysOn Status...';
        EXEC dbo.usp_Collect_AlwaysOn_Status;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] AlwaysOn Status: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 2. Backups
    BEGIN TRY
        IF @Debug = 1 PRINT '[2/11] Coletando Backups...';
        EXEC dbo.usp_Collect_Backups;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Backups: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 3. Blocked Sessions
    BEGIN TRY
        IF @Debug = 1 PRINT '[3/11] Coletando Blocked Sessions...';
        EXEC dbo.usp_Collect_Blocked_Sessions;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Blocked Sessions: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 4. Blocked Users
    BEGIN TRY
        IF @Debug = 1 PRINT '[4/11] Coletando Blocked Users...';
        EXEC dbo.usp_Collect_Blocked_Users;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Blocked Users: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 5. Database Availability
    BEGIN TRY
        IF @Debug = 1 PRINT '[5/11] Coletando DB Availability...';
        EXEC dbo.usp_Collect_DB_Availability;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] DB Availability: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 6. Disk Usage
    BEGIN TRY
        IF @Debug = 1 PRINT '[6/11] Coletando Disk Usage...';
        EXEC dbo.usp_Collect_Disk_Usage;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Disk Usage: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 7. Filegroup Usage
    BEGIN TRY
        IF @Debug = 1 PRINT '[7/11] Coletando Filegroup Usage...';
        EXEC dbo.usp_Collect_Filegroup_Usage;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Filegroup Usage: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 8. Instance Availability
    BEGIN TRY
        IF @Debug = 1 PRINT '[8/11] Coletando Instance Availability...';
        EXEC dbo.usp_Collect_Instance_Availability;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Instance Availability: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 9. Long Locks
    BEGIN TRY
        IF @Debug = 1 PRINT '[9/11] Coletando Long Locks...';
        EXEC dbo.usp_Collect_Long_Locks;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Long Locks: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 10. Processes
    BEGIN TRY
        IF @Debug = 1 PRINT '[10/11] Coletando Processes...';
        EXEC dbo.usp_Collect_Processes;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Processes: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 11. Transaction Log Usage
    BEGIN TRY
        IF @Debug = 1 PRINT '[11/11] Coletando TLog Usage...';
        EXEC dbo.usp_Collect_TLog_Usage;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] TLog Usage: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- Resumo
    DECLARE @Duration INT = DATEDIFF(SECOND, @StartTime, GETDATE());

    PRINT '';
    PRINT '============================================================================';
    PRINT 'RESUMO DA COLETA';
    PRINT '============================================================================';
    PRINT 'Sucesso: ' + CAST(@SuccessCount AS VARCHAR(10)) + ' / 11';
    PRINT 'Erros: ' + CAST(@ErrorCount AS VARCHAR(10));
    PRINT 'Duração: ' + CAST(@Duration AS VARCHAR(10)) + ' segundos';
    PRINT 'Término: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
    PRINT '============================================================================';
    PRINT '';

    -- Retornar código de erro se houver falhas
    IF @ErrorCount > 0
        RETURN 1;
    ELSE
        RETURN 0;
END;
GO

PRINT '  [OK] Procedure usp_Collect_All_KPIs criada';
GO

-- ============================================================================
-- RESUMO FINAL
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'PROCEDURES CRIADAS COM SUCESSO';
PRINT '============================================================================';
PRINT '  [OK] 11 Procedures de coleta individual';
PRINT '  [OK] 1 Procedure master (usp_Collect_All_KPIs)';
PRINT '';
PRINT 'Total: 12 procedures criadas';
PRINT '';
PRINT 'TESTE RÁPIDO:';
PRINT '  EXEC dbo.usp_Collect_All_KPIs @Debug = 1;';
PRINT '';
PRINT 'VERIFICAR DADOS:';
PRINT '  SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;';
PRINT '  SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;';
PRINT '';
PRINT 'PRÓXIMO: Executar script de SQL Agent Job (SQLSERVER_KPI_AGENT_JOBS.sql)';
PRINT '============================================================================';
PRINT 'Concluído em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
GO
