-- ============================================================================
-- WATCHERDB INTELLIGENCE V2 - SQL SERVER KPI VIEWS
-- ============================================================================
-- Views para agregação e detalhamento dos KPIs SQL Server
--
-- ORIGEM: Oracle PDBACH_MSSQL_KPI schema
-- DESTINO: SQL Server WatcherDB_Intelligence_V2
--
-- COMPONENTES:
--   - 1 Tabela auxiliar (KPI_MSSQL_INST_ENVS)
--   - 22 Views (11 AGG + 11 DET)
--
-- AUTOR: WatcherDB Team
-- DATA: 2025-11-27
-- VERSÃO: 1.0.0
-- ============================================================================

USE [WatcherDB_Intelligence_V2];
GO

PRINT '============================================================================';
PRINT 'WATCHERDB INTELLIGENCE V2 - CRIAÇÃO DE VIEWS KPI';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
GO

-- ============================================================================
-- TABELA AUXILIAR: KPI_MSSQL_INST_ENVS
-- ============================================================================
-- Esta tabela mapeia instâncias SQL Server para ambientes (PROD, UAT, DEV, etc.)

PRINT '';
PRINT '-- [1/12] Criando tabela auxiliar KPI_MSSQL_INST_ENVS...';
PRINT '';

IF OBJECT_ID('dbo.KPI_MSSQL_INST_ENVS', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_INST_ENVS;
GO

CREATE TABLE dbo.KPI_MSSQL_INST_ENVS (
    Instance        VARCHAR(64)     NOT NULL PRIMARY KEY,
    Env             VARCHAR(32)     NOT NULL,   -- PROD, UAT, DEV, TEST, etc.
    Description     VARCHAR(500)    NULL
);
GO

PRINT '  [OK] Tabela KPI_MSSQL_INST_ENVS criada';
PRINT '  [INFO] Popule esta tabela com: INSERT INTO KPI_MSSQL_INST_ENVS VALUES (''SERVIDOR\INSTANCIA'', ''PROD'', ''Descrição'')';
GO

-- ============================================================================
-- VIEWS: ALWAYS ON STATUS (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [2/12] Criando views Always On Status...';
PRINT '';

-- View agregada - AlwaysOn
IF OBJECT_ID('dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
AS
SELECT
    t.AgName,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(f.N, 0) AS Unhealthy,
    t.N AS Total
FROM
    (SELECT AgName, COUNT(1) AS N
     FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG
     GROUP BY AgName) t
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = t.AgName
    LEFT OUTER JOIN
    (SELECT AgName, COUNT(1) AS N
     FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG
     WHERE Pri_Synch_Health <> 'HEALTHY' OR Sec_Synch_Health <> 'HEALTHY'
     GROUP BY AgName) f
      ON f.AgName = t.AgName;
GO

-- View detalhada - AlwaysOn
IF OBJECT_ID('dbo.KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW
AS
SELECT
    s.AgName,
    ISNULL(e.Env, 'Undefined') AS Env,
    s.Instance,
    s.[Database],
    s.Pri_Synch_State,
    s.Pri_Synch_Health,
    s.Pri_Is_Suspended,
    s.Sec_Synch_State,
    s.Sec_Synch_Health,
    s.Sec_Is_Suspended,
    s.Commit_Diff_Secs,
    s.Update_TS
FROM
    dbo.KPI_MSSQL_ALWAYSON_STATUS_STG s
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = s.AgName
WHERE
    s.Pri_Synch_Health <> 'HEALTHY' OR s.Sec_Synch_Health <> 'HEALTHY';
GO

PRINT '  [OK] Views Always On criadas';
GO

-- ============================================================================
-- VIEWS: BLOCKED SESSIONS (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [3/12] Criando views Blocked Sessions...';
PRINT '';

-- View agregada - Blocked Sessions
IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW
AS
SELECT
    i.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(bs.Cnt, 0) AS Cnt
FROM
    (SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG) i
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON i.Instance = e.Instance
    LEFT OUTER JOIN
    (SELECT Instance, COUNT(1) AS Cnt
     FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG
     WHERE Wait_Time_Sec > 0
     GROUP BY Instance) bs
      ON i.Instance = bs.Instance;
GO

-- View detalhada - Blocked Sessions
IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_SESSIONS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BLOCKED_SESSIONS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BLOCKED_SESSIONS_DET_VIEW
AS
SELECT
    bs.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    bs.Session_Id,
    bs.Blocked_By,
    bs.Wait_Time_Sec,
    bs.Wait_Type,
    bs.[Database],
    bs.[Status],
    bs.Command,
    bs.Update_TS
FROM
    dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG bs
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON bs.Instance = e.Instance
WHERE
    bs.Wait_Time_Sec > 0;
GO

PRINT '  [OK] Views Blocked Sessions criadas';
GO

-- ============================================================================
-- VIEWS: DATABASE AVAILABILITY (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [4/12] Criando views Database Availability...';
PRINT '';

-- View agregada - Database Availability
IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
AS
SELECT
    t.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    t.Total AS TotalCnt,
    ISNULL(d.Cnt, 0) AS AbnormalCnt
FROM
    (SELECT Instance, COUNT(1) AS Total
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
     GROUP BY Instance) t
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = t.Instance
    LEFT OUTER JOIN
    (SELECT Instance, COUNT(1) AS Cnt
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
     WHERE 
         -- Lógica do Oracle: excluir RESTORING apenas quando mirroring_role = 'MIRROR'
         -- IMPORTANTE: Se Mirroring_Role for NULL e State for RESTORING, também excluir
         (
             (Mirroring_Role IS NULL AND ([State] <> 'ONLINE' OR Is_Available = 0) AND [State] <> 'RESTORING')
             OR (Mirroring_Role = 'PRINCIPAL' AND ([State] <> 'ONLINE' OR Is_Available = 0))
             OR (Mirroring_Role = 'MIRROR' AND ([State] <> 'RESTORING' OR Is_Available = 0))
         )
     GROUP BY Instance) d
      ON t.Instance = d.Instance;
GO

-- View detalhada - Database Availability
IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
AS
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.[Database],
    d.[State],
    d.Is_Available,
    d.Recovery_Model,
    d.Mirroring_Role,
    d.Update_TS
FROM
    dbo.KPI_MSSQL_DB_AVAILABILITY_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    -- Lógica do Oracle: excluir RESTORING apenas quando mirroring_role = 'MIRROR'
    -- Para outras situações, RESTORING é considerado problema
    -- IMPORTANTE: Se Mirroring_Role for NULL e State for RESTORING, também excluir
    -- (pode ser mirroring não detectado pela coleta)
    (
        -- Sem mirroring: considerar problema se State <> 'ONLINE' ou Is_Available = 0
        -- Mas excluir RESTORING mesmo sem mirroring_role (pode ser mirroring não detectado)
        (d.Mirroring_Role IS NULL AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0) AND d.[State] <> 'RESTORING')
        -- Principal em mirroring: considerar problema se State <> 'ONLINE' ou Is_Available = 0
        OR (d.Mirroring_Role = 'PRINCIPAL' AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0))
        -- Mirror em mirroring: considerar problema se State <> 'RESTORING' ou Is_Available = 0
        -- (RESTORING é estado normal para MIRROR, então não é problema)
        OR (d.Mirroring_Role = 'MIRROR' AND (d.[State] <> 'RESTORING' OR d.Is_Available = 0))
    );
GO

PRINT '  [OK] Views Database Availability criadas';
GO

-- ============================================================================
-- VIEWS: DISK USAGE (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [5/12] Criando views Disk Usage...';
PRINT '';

-- View agregada - Disk Usage
IF OBJECT_ID('dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW
AS
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    SUM(CASE WHEN d.Percent_Free >= 20 THEN 1 ELSE 0 END) AS Normal,
    SUM(CASE WHEN d.Percent_Free < 20 AND d.Percent_Free >= 10 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN d.Percent_Free < 10 THEN 1 ELSE 0 END) AS Critical
FROM
    dbo.KPI_MSSQL_DISK_USAGE_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
GROUP BY
    d.Instance, e.Env;
GO

-- View detalhada - Disk Usage
IF OBJECT_ID('dbo.KPI_MSSQL_DISK_USAGE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DISK_USAGE_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DISK_USAGE_DET_VIEW
AS
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.Drive,
    d.Percent_Free AS [Available%],
    CAST(d.Free_MB / 1024.0 AS DECIMAL(12,2)) AS Available_GB,
    100 - d.Percent_Free AS [Used%],
    CASE
        WHEN d.Percent_Free >= 20 THEN 'NORMAL'
        WHEN d.Percent_Free >= 10 THEN 'WARNING'
        ELSE 'CRITICAL'
    END AS [Status],
    d.Update_TS
FROM
    dbo.KPI_MSSQL_DISK_USAGE_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    d.Percent_Free < 20;  -- Mostrar apenas discos com warning ou critical
GO

PRINT '  [OK] Views Disk Usage criadas';
GO

-- ============================================================================
-- VIEWS: FILEGROUP USAGE (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [6/12] Criando views Filegroup Usage...';
PRINT '';

-- View agregada - Filegroup Usage
IF OBJECT_ID('dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW
AS
SELECT
    f.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    SUM(CASE WHEN f.Percent_Used >= 80 AND f.Percent_Used < 90 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN f.Percent_Used >= 90 THEN 1 ELSE 0 END) AS Critical
FROM
    dbo.KPI_MSSQL_FG_USAGE_STG f
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = f.Instance
GROUP BY
    f.Instance, e.Env;
GO

-- View detalhada - Filegroup Usage
IF OBJECT_ID('dbo.KPI_MSSQL_FG_USAGE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
AS
SELECT
    f.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    f.[Database],
    f.Filegroup,
    f.Used_MB,
    f.Total_MB AS Current_MB,
    ISNULL(f.Max_Size_MB - f.Total_MB, 0) AS Extendable_MB,
    f.Percent_Used AS [Used%],
    CASE
        WHEN f.Percent_Used < 80 THEN 'NORMAL'
        WHEN f.Percent_Used < 90 THEN 'WARNING'
        ELSE 'CRITICAL'
    END AS [State],
    f.Update_TS
FROM
    dbo.KPI_MSSQL_FG_USAGE_STG f
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = f.Instance
WHERE
    f.Percent_Used >= 80;  -- Mostrar apenas filegroups com warning ou critical
GO

PRINT '  [OK] Views Filegroup Usage criadas';
GO

-- ============================================================================
-- VIEWS: INSTANCE AVAILABILITY (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [7/12] Criando views Instance Availability...';
PRINT '';

-- View agregada - Instance Availability
IF OBJECT_ID('dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW
AS
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    CASE WHEN i.Is_Available = 1 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END AS [State],
    COUNT(1) AS [Count]
FROM
    dbo.KPI_MSSQL_INST_AVAILABILITY_STG i
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = i.Instance
GROUP BY
    e.Env, i.Is_Available;
GO

-- View detalhada - Instance Availability
IF OBJECT_ID('dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW
AS
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    i.Instance,
    CASE WHEN i.Is_Available = 1 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END AS [State],
    i.Uptime_Hours,
    i.[Version],
    i.Edition,
    i.Update_TS
FROM
    dbo.KPI_MSSQL_INST_AVAILABILITY_STG i
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = i.Instance;
GO

PRINT '  [OK] Views Instance Availability criadas';
GO

-- ============================================================================
-- VIEWS: LONG LOCKS (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [8/12] Criando views Long Locks...';
PRINT '';

-- View agregada - Long Locks
IF OBJECT_ID('dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW
AS
SELECT
    l.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(1) AS Cnt,
    CASE
        WHEN MAX(l.Duration_Sec) >= 300 THEN 'CRITICAL'
        WHEN MAX(l.Duration_Sec) >= 60 THEN 'WARNING'
        ELSE 'NORMAL'
    END AS [State]
FROM
    dbo.KPI_MSSQL_LONG_LOCKS_STG l
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = l.Instance
WHERE
    l.Duration_Sec >= 60
GROUP BY
    l.Instance, e.Env;
GO

-- View detalhada - Long Locks
IF OBJECT_ID('dbo.KPI_MSSQL_LONG_LOCKS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_LONG_LOCKS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_LONG_LOCKS_DET_VIEW
AS
SELECT
    l.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    l.[Database],
    l.Session_Id AS SPID,
    l.Lock_Type,
    l.Lock_Mode,
    l.Resource_Type,
    l.Resource_Desc,
    l.Duration_Sec,
    l.Update_TS
FROM
    dbo.KPI_MSSQL_LONG_LOCKS_STG l
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = l.Instance
WHERE
    l.Duration_Sec >= 60;
GO

PRINT '  [OK] Views Long Locks criadas';
GO

-- ============================================================================
-- VIEWS: PROCESSES (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [9/12] Criando views Processes...';
PRINT '';

-- View agregada - Processes
IF OBJECT_ID('dbo.KPI_MSSQL_PROCESSES_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_PROCESSES_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
AS
SELECT
    p.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(DISTINCT p.Session_Id) AS Processes,
    CASE
        WHEN COUNT(DISTINCT p.Session_Id) >= 1000 THEN 'CRITICAL'
        WHEN COUNT(DISTINCT p.Session_Id) >= 500 THEN 'WARNING'
        ELSE 'NORMAL'
    END AS [State]
FROM
    dbo.KPI_MSSQL_PROCESSES_STG p
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = p.Instance
GROUP BY
    p.Instance, e.Env;
GO

-- View detalhada - Processes
IF OBJECT_ID('dbo.KPI_MSSQL_PROCESSES_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_PROCESSES_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_PROCESSES_DET_VIEW
AS
SELECT
    p.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    p.[User] AS Login_Name,
    p.[Database],
    p.[Status],
    p.Command,
    COUNT(1) AS Current_Count,
    MAX(p.Update_TS) AS Last_Update
FROM
    dbo.KPI_MSSQL_PROCESSES_STG p
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = p.Instance
GROUP BY
    p.Instance, e.Env, p.[User], p.[Database], p.[Status], p.Command;
GO

PRINT '  [OK] Views Processes criadas';
GO

-- ============================================================================
-- VIEWS: TRANSACTION LOG USAGE (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [10/12] Criando views Transaction Log Usage...';
PRINT '';

-- View agregada - Transaction Log Usage
IF OBJECT_ID('dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW
AS
SELECT
    t.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    SUM(CASE WHEN t.Percent_Used < 70 THEN 1 ELSE 0 END) AS Normal,
    SUM(CASE WHEN t.Percent_Used >= 70 AND t.Percent_Used < 90 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN t.Percent_Used >= 90 THEN 1 ELSE 0 END) AS Critical
FROM
    dbo.KPI_MSSQL_TLOG_USAGE_STG t
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = t.Instance
GROUP BY
    t.Instance, e.Env;
GO

-- View detalhada - Transaction Log Usage
IF OBJECT_ID('dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW
AS
SELECT
    t.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    t.[Database],
    100 - t.Percent_Used AS [Available%],
    CAST((t.Current_MB - t.Used_MB) / 1024.0 AS DECIMAL(12,2)) AS Available_GB,
    t.Percent_Used AS [Used%],
    CASE
        WHEN t.Percent_Used < 70 THEN 'NORMAL'
        WHEN t.Percent_Used < 90 THEN 'WARNING'
        ELSE 'CRITICAL'
    END AS [Status],
    t.Update_TS
FROM
    dbo.KPI_MSSQL_TLOG_USAGE_STG t
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = t.Instance
WHERE
    t.Percent_Used >= 70;  -- Mostrar apenas logs com warning ou critical
GO

PRINT '  [OK] Views Transaction Log Usage criadas';
GO

-- ============================================================================
-- VIEWS: BACKUPS (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '-- [11/12] Criando views Backups...';
PRINT '';

-- View agregada - Backups
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUPS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BACKUPS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BACKUPS_AGG_VIEW
AS
SELECT
    b.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    b.Backup_Type,
    COUNT(1) AS Total_Databases,
    SUM(CASE WHEN b.Hours_Since_Backup > 48 THEN 1 ELSE 0 END) AS Critical,
    SUM(CASE WHEN b.Hours_Since_Backup > 24 AND b.Hours_Since_Backup <= 48 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN b.Hours_Since_Backup <= 24 THEN 1 ELSE 0 END) AS Normal
FROM
    dbo.KPI_MSSQL_BACKUPS_STG b
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = b.Instance
GROUP BY
    b.Instance, e.Env, b.Backup_Type;
GO

-- View detalhada - Backups
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUPS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BACKUPS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BACKUPS_DET_VIEW
AS
SELECT
    b.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    b.[Database],
    b.Backup_Type,
    b.Last_Backup_Date,
    b.Hours_Since_Backup,
    CAST(b.Backup_Size_MB / 1024.0 AS DECIMAL(12,2)) AS Backup_Size_GB,
    CASE
        WHEN b.Hours_Since_Backup > 48 THEN 'CRITICAL'
        WHEN b.Hours_Since_Backup > 24 THEN 'WARNING'
        ELSE 'NORMAL'
    END AS [Status],
    b.Update_TS
FROM
    dbo.KPI_MSSQL_BACKUPS_STG b
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = b.Instance
WHERE
    b.Hours_Since_Backup > 24  -- Mostrar apenas backups atrasados
    OR b.Last_Backup_Date IS NULL;
GO

PRINT '  [OK] Views Backups criadas';
GO

-- ============================================================================
-- VIEWS: BLOCKED USERS (AGG + DET) - ADICIONADO 2025-12-21
-- ============================================================================

PRINT '';
PRINT '-- [12/14] Criando views Blocked Users...';
PRINT '';

-- View agregada - Blocked Users
IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW
AS
SELECT
    i.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(bu.Blocked_Users_Count, 0) AS Blocked_Users_Count,
    ISNULL(bu.Total_Blocked_Count, 0) AS Total_Blocked_Count,
    bu.Last_Check
FROM
    (SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG) i
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON i.Instance = e.Instance
    LEFT OUTER JOIN
    (SELECT Instance,
        COUNT(DISTINCT [User]) AS Blocked_Users_Count,
        SUM(Blocked_Count) AS Total_Blocked_Count,
        MAX(Update_TS) AS Last_Check
     FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG
     WHERE Blocked_Count > 0
     GROUP BY Instance) bu
      ON i.Instance = bu.Instance;
GO

-- View detalhada - Blocked Users
IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_USERS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BLOCKED_USERS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BLOCKED_USERS_DET_VIEW
AS
SELECT
    bu.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    bu.[User],
    bu.[Database],
    bu.Blocked_Count,
    bu.Max_Wait_Time_Sec,
    bu.Update_TS
FROM
    dbo.KPI_MSSQL_BLOCKED_USERS_STG bu
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON bu.Instance = e.Instance
WHERE
    bu.Blocked_Count > 0;
GO

PRINT '  [OK] Views Blocked Users criadas';
GO

-- ============================================================================
-- VIEWS: TEMPDB STATUS (AGG + DET) - ADICIONADO 2025-12-21
-- ============================================================================
-- NOTA: Esta view usa DISK_USAGE como proxy até que uma tabela específica
--       KPI_MSSQL_TEMPDB_STATUS_STG seja criada e populada pela coleta Python.
-- ============================================================================

PRINT '';
PRINT '-- [13/14] Criando views TempDB Status...';
PRINT '';

-- View agregada - TempDB Status (usa Disk Usage como proxy)
IF OBJECT_ID('dbo.KPI_MSSQL_TEMPDB_STATUS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_TEMPDB_STATUS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_TEMPDB_STATUS_AGG_VIEW
AS
-- Usa Disk Usage como proxy para TempDB
-- Discos críticos/warning afetam o TempDB
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    SUM(CASE WHEN d.Percent_Free < 10 THEN 1 ELSE 0 END) AS Critical,
    SUM(CASE WHEN d.Percent_Free >= 10 AND d.Percent_Free < 20 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN d.Percent_Free >= 20 THEN 1 ELSE 0 END) AS Normal,
    MIN(d.Percent_Free) AS Min_Percent_Free,
    MAX(d.Update_TS) AS Last_Check
FROM
    dbo.KPI_MSSQL_DISK_USAGE_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
GROUP BY
    d.Instance, e.Env;
GO

-- View detalhada - TempDB Status (mostra discos com problema)
IF OBJECT_ID('dbo.KPI_MSSQL_TEMPDB_STATUS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_TEMPDB_STATUS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_TEMPDB_STATUS_DET_VIEW
AS
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.Drive,
    d.Percent_Free AS [Available%],
    CAST(d.Free_MB / 1024.0 AS DECIMAL(12,2)) AS Available_GB,
    100 - d.Percent_Free AS [Used%],
    CASE
        WHEN d.Percent_Free < 10 THEN 'CRITICAL'
        WHEN d.Percent_Free < 20 THEN 'WARNING'
        ELSE 'NORMAL'
    END AS [Status],
    d.Update_TS
FROM
    dbo.KPI_MSSQL_DISK_USAGE_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    d.Percent_Free < 20;  -- Mostrar apenas discos com warning ou critical
GO

PRINT '  [OK] Views TempDB Status criadas (proxy de Disk Usage)';
GO

-- ============================================================================
-- VIEWS: SERVER OFFLINE (AGG + DET) - ADICIONADO 2025-12-21
-- ============================================================================
-- NOTA: Usa a tabela KPI_MSSQL_SERVER_OFFLINE_EVENTS criada para rastrear
--       servidores offline/down detectados pelo monitoramento.
-- ============================================================================

PRINT '';
PRINT '-- [14/14] Criando views Server Offline...';
PRINT '';

-- View agregada - Server Offline (eventos não resolvidos por diagnóstico)
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW
AS
SELECT
    COUNT(*) AS total_events,
    SUM(CASE WHEN Diagnosis = 'offline' THEN 1 ELSE 0 END) AS servers_offline,
    SUM(CASE WHEN Diagnosis = 'sql_down' THEN 1 ELSE 0 END) AS sql_services_down,
    SUM(CASE WHEN Diagnosis = 'partial' THEN 1 ELSE 0 END) AS partial_services,
    MAX(Event_Time) AS last_event_time
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
WHERE Is_Resolved = 0;
GO

-- View detalhada - Server Offline (lista de eventos não resolvidos)
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW
AS
SELECT
    Event_ID,
    Server_Name,
    Diagnosis,
    CASE Diagnosis
        WHEN 'offline' THEN 'Server Offline'
        WHEN 'sql_down' THEN 'SQL Services Down'
        WHEN 'partial' THEN 'Partial Services'
        ELSE Diagnosis
    END AS Diagnosis_Desc,
    Ping_OK,
    Ping_Message,
    Services_Down,
    Event_Time,
    DATEDIFF(MINUTE, Event_Time, GETDATE()) AS Minutes_Since_Event,
    CASE
        WHEN DATEDIFF(MINUTE, Event_Time, GETDATE()) < 5 THEN 'RECENT'
        WHEN DATEDIFF(MINUTE, Event_Time, GETDATE()) < 30 THEN 'ONGOING'
        ELSE 'PROLONGED'
    END AS Event_Status
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
WHERE Is_Resolved = 0;
GO

PRINT '  [OK] Views Server Offline criadas';
GO

-- ============================================================================
-- VIEWS CMDB
-- ============================================================================

PRINT '';
PRINT '-- [12/12] Criando views CMDB...';
PRINT '';

-- View CMDB - Databases
IF OBJECT_ID('dbo.CMDB_MSSQL_DATABASES_VW', 'V') IS NOT NULL
    DROP VIEW dbo.CMDB_MSSQL_DATABASES_VW;
GO

CREATE VIEW dbo.CMDB_MSSQL_DATABASES_VW
AS
SELECT
    d.Cluster + '.' + d.Instance + '.' + d.[Database] AS ID,
    d.Cluster,
    d.Instance + '.' + d.[Database] AS [Database],
    d.[Group],
    'Microsoft' AS Provider,
    d.Environment,
    d.[State],
    d.[Version],
    d.Edition,
    d.Size_GB,
    d.[Description],
    d.UpdatedAt
FROM
    dbo.CMDB_MSSQL_DATABASES d;
GO

PRINT '  [OK] Views CMDB criadas';
GO

-- ============================================================================
-- RESUMO FINAL
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'VIEWS CRIADAS COM SUCESSO';
PRINT '============================================================================';
PRINT '  [OK] 1 Tabela auxiliar (KPI_MSSQL_INST_ENVS)';
PRINT '  [OK] 22 Views de KPI (11 AGG + 11 DET)';
PRINT '  [OK] 1 View CMDB';
PRINT '';
PRINT 'Total: 24 objetos criados';
PRINT '';
PRINT 'IMPORTANTE:';
PRINT '  Popule a tabela KPI_MSSQL_INST_ENVS com os mapeamentos Instance -> Environment';
PRINT '';
PRINT '  Exemplo:';
PRINT '    INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env) VALUES (''SQLHDSPRD213\I01'', ''PROD'');';
PRINT '';
PRINT 'PRÓXIMO: Executar script de PROCEDURES (SQLSERVER_KPI_PROCEDURES.sql)';
PRINT '============================================================================';
PRINT 'Concluído em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
GO
