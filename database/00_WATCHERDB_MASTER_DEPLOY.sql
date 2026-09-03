/*
================================================================================
    WATCHERDB STANDARD EDITION - MASTER DEPLOY SCRIPT
    Version: 1.0.0
    Date: 2025-12-15

    This script creates all necessary database objects for WatcherDB Standard.
    Execute this on a Central SQL Server that will collect KPIs from all monitored servers.

    Objects Created:
    - Database: WatcherDB (if not exists)
    - Schemas: kpi, history, monitoring
    - Tables: Server inventory, KPI data, history tables
    - Procedures: Collection and maintenance procedures
    - Views: Dashboard views
    - Indexes: Performance indexes
    - Jobs: Automated collection jobs

    EXECUTION ORDER:
    1. 00_WATCHERDB_MASTER_DEPLOY.sql (this file - creates database and schemas)
    2. 01_WATCHERDB_TABLES.sql (creates all tables)
    3. 02_WATCHERDB_INDEXES.sql (creates performance indexes)
    4. 03_WATCHERDB_PROCEDURES.sql (creates stored procedures)
    5. 04_WATCHERDB_VIEWS.sql (creates monitoring views)
    6. 05_WATCHERDB_JOBS.sql (creates SQL Agent jobs)
================================================================================
*/

USE [master]
GO

-- ============================================================================
-- SECTION 1: CREATE DATABASE
-- ============================================================================
PRINT '============================================================'
PRINT 'WATCHERDB STANDARD - MASTER DEPLOY'
PRINT '============================================================'
PRINT ''

IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'WatcherDB')
BEGIN
    PRINT 'Creating WatcherDB database...'

    CREATE DATABASE [WatcherDB]
    ON PRIMARY
    (
        NAME = N'WatcherDB_Data',
        FILENAME = N'D:\SQLData\WatcherDB_Data.mdf',  -- ADJUST PATH AS NEEDED
        SIZE = 512MB,
        MAXSIZE = UNLIMITED,
        FILEGROWTH = 256MB
    )
    LOG ON
    (
        NAME = N'WatcherDB_Log',
        FILENAME = N'D:\SQLLog\WatcherDB_Log.ldf',    -- ADJUST PATH AS NEEDED
        SIZE = 128MB,
        MAXSIZE = 8GB,
        FILEGROWTH = 128MB
    )

    PRINT 'Database WatcherDB created successfully.'
END
ELSE
BEGIN
    PRINT 'Database WatcherDB already exists.'
END
GO

-- Configure database options
ALTER DATABASE [WatcherDB] SET RECOVERY SIMPLE
ALTER DATABASE [WatcherDB] SET AUTO_CLOSE OFF
ALTER DATABASE [WatcherDB] SET AUTO_SHRINK OFF
ALTER DATABASE [WatcherDB] SET READ_COMMITTED_SNAPSHOT ON
GO

USE [WatcherDB]
GO

-- ============================================================================
-- SECTION 2: CREATE SCHEMAS
-- ============================================================================
PRINT ''
PRINT 'Creating schemas...'

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'kpi')
    EXEC('CREATE SCHEMA [kpi]')

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'history')
    EXEC('CREATE SCHEMA [history]')

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'monitoring')
    EXEC('CREATE SCHEMA [monitoring]')

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'config')
    EXEC('CREATE SCHEMA [config]')

PRINT 'Schemas created: kpi, history, monitoring, config'
GO

-- ============================================================================
-- SECTION 3: SERVER INVENTORY TABLE
-- ============================================================================
PRINT ''
PRINT 'Creating server inventory tables...'

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'ServerInventory' AND schema_id = SCHEMA_ID('config'))
BEGIN
    CREATE TABLE [config].[ServerInventory] (
        [ServerID] INT IDENTITY(1,1) PRIMARY KEY,
        [ServerName] NVARCHAR(128) NOT NULL,
        [InstanceName] NVARCHAR(128) NULL,
        [ServerID_Formatted] AS (
            CASE
                WHEN [InstanceName] IS NULL OR [InstanceName] = ''
                THEN [ServerName]
                ELSE [ServerName] + '_' + [InstanceName]
            END
        ) PERSISTED,
        [ConnectionString] NVARCHAR(500) NULL,
        [Environment] NVARCHAR(50) NOT NULL DEFAULT 'Production',  -- Production, Development, QA, DR
        [Criticality] NVARCHAR(20) NOT NULL DEFAULT 'Medium',      -- Critical, High, Medium, Low
        [Owner] NVARCHAR(128) NULL,
        [Application] NVARCHAR(256) NULL,
        [IsActive] BIT NOT NULL DEFAULT 1,
        [IsMonitored] BIT NOT NULL DEFAULT 1,
        [CollectionIntervalMinutes] INT NOT NULL DEFAULT 5,
        [LastCollectionTime] DATETIME2 NULL,
        [LastCollectionStatus] NVARCHAR(50) NULL,
        [Notes] NVARCHAR(MAX) NULL,
        [CreatedDate] DATETIME2 NOT NULL DEFAULT GETDATE(),
        [ModifiedDate] DATETIME2 NOT NULL DEFAULT GETDATE(),

        CONSTRAINT [UQ_ServerInventory_ServerInstance] UNIQUE ([ServerName], [InstanceName])
    )

    PRINT 'Table config.ServerInventory created.'
END
GO

-- Create index on ServerID_Formatted
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ServerInventory_ServerID_Formatted')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_ServerInventory_ServerID_Formatted]
    ON [config].[ServerInventory] ([ServerID_Formatted])
    INCLUDE ([IsActive], [IsMonitored])
END
GO

-- ============================================================================
-- SECTION 4: KPI TABLES
-- ============================================================================
PRINT ''
PRINT 'Creating KPI tables...'

-- Main KPI Snapshot Table
IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'KPISnapshot' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE [kpi].[KPISnapshot] (
        [SnapshotID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL DEFAULT GETDATE(),
        [CollectionDurationMs] INT NULL,

        -- CPU Metrics
        [CPU_Percent] DECIMAL(5,2) NULL,
        [CPU_SQL_Percent] DECIMAL(5,2) NULL,
        [CPU_Other_Percent] DECIMAL(5,2) NULL,

        -- Memory Metrics
        [Memory_Total_MB] BIGINT NULL,
        [Memory_Available_MB] BIGINT NULL,
        [Memory_SQL_Used_MB] BIGINT NULL,
        [Memory_Buffer_Cache_Hit_Ratio] DECIMAL(5,2) NULL,
        [Memory_Page_Life_Expectancy] INT NULL,
        [Memory_Lazy_Writes_Sec] BIGINT NULL,

        -- Storage Metrics
        [Storage_Data_Used_GB] DECIMAL(18,2) NULL,
        [Storage_Log_Used_GB] DECIMAL(18,2) NULL,
        [Storage_Data_Free_GB] DECIMAL(18,2) NULL,
        [Storage_Log_Free_GB] DECIMAL(18,2) NULL,

        -- Connection Metrics
        [Connections_Total] INT NULL,
        [Connections_Active] INT NULL,
        [Connections_Sleeping] INT NULL,
        [Connections_Blocked] INT NULL,

        -- Wait Stats Metrics
        [Waits_CPU_Ms] BIGINT NULL,
        [Waits_IO_Ms] BIGINT NULL,
        [Waits_Lock_Ms] BIGINT NULL,
        [Waits_Memory_Ms] BIGINT NULL,

        -- Batch Metrics
        [Batch_Requests_Sec] BIGINT NULL,
        [Compilations_Sec] BIGINT NULL,
        [Recompilations_Sec] BIGINT NULL,

        -- IO Metrics
        [IO_Read_MB_Sec] DECIMAL(18,2) NULL,
        [IO_Write_MB_Sec] DECIMAL(18,2) NULL,
        [IO_Stall_Read_Ms] BIGINT NULL,
        [IO_Stall_Write_Ms] BIGINT NULL,

        INDEX [IX_KPISnapshot_ServerTime] NONCLUSTERED ([ServerID_Formatted], [SnapshotTime] DESC)
    )

    PRINT 'Table kpi.KPISnapshot created.'
END
GO

-- Database Space Table
IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'DatabaseSpace' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE [kpi].[DatabaseSpace] (
        [SpaceID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [DatabaseName] NVARCHAR(128) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL DEFAULT GETDATE(),

        -- File Information
        [FileGroupName] NVARCHAR(128) NULL,
        [LogicalFileName] NVARCHAR(128) NULL,
        [PhysicalPath] NVARCHAR(500) NULL,
        [FileType] NVARCHAR(20) NULL,  -- DATA, LOG

        -- Size Information
        [TotalSize_MB] DECIMAL(18,2) NULL,
        [UsedSpace_MB] DECIMAL(18,2) NULL,
        [FreeSpace_MB] DECIMAL(18,2) NULL,
        [FreeSpace_Percent] DECIMAL(5,2) NULL,

        -- Growth Settings
        [MaxSize_MB] DECIMAL(18,2) NULL,
        [GrowthType] NVARCHAR(20) NULL,  -- PERCENT, MB
        [GrowthValue] DECIMAL(18,2) NULL,
        [IsAutoGrowthEnabled] BIT NULL,

        -- Drive Information
        [DriveLetter] CHAR(1) NULL,
        [DriveTotal_GB] DECIMAL(18,2) NULL,
        [DriveFree_GB] DECIMAL(18,2) NULL,
        [DriveFree_Percent] DECIMAL(5,2) NULL,

        INDEX [IX_DatabaseSpace_ServerDB] NONCLUSTERED ([ServerID_Formatted], [DatabaseName], [SnapshotTime] DESC)
    )

    PRINT 'Table kpi.DatabaseSpace created.'
END
GO

-- Jobs Status Table
IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'JobsStatus' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE [kpi].[JobsStatus] (
        [JobStatusID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL DEFAULT GETDATE(),

        -- Job Information
        [JobID] UNIQUEIDENTIFIER NULL,
        [JobName] NVARCHAR(256) NOT NULL,
        [JobCategory] NVARCHAR(128) NULL,
        [JobOwner] NVARCHAR(128) NULL,
        [IsEnabled] BIT NULL,

        -- Last Run Information
        [LastRunDate] DATETIME2 NULL,
        [LastRunDuration_Seconds] INT NULL,
        [LastRunStatus] NVARCHAR(50) NULL,  -- Succeeded, Failed, Canceled, Running
        [LastRunMessage] NVARCHAR(MAX) NULL,

        -- Next Run Information
        [NextRunDate] DATETIME2 NULL,

        -- Schedule Information
        [ScheduleDescription] NVARCHAR(500) NULL,

        INDEX [IX_JobsStatus_ServerJob] NONCLUSTERED ([ServerID_Formatted], [JobName], [SnapshotTime] DESC)
    )

    PRINT 'Table kpi.JobsStatus created.'
END
GO

-- AlwaysOn/Mirroring Status Table
IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'HAStatus' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE [kpi].[HAStatus] (
        [HAStatusID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL DEFAULT GETDATE(),

        -- AG Information
        [AGName] NVARCHAR(128) NULL,
        [DatabaseName] NVARCHAR(128) NOT NULL,
        [ReplicaServer] NVARCHAR(256) NULL,

        -- Status
        [HAType] NVARCHAR(50) NOT NULL,  -- AlwaysOn, Mirroring, LogShipping
        [Role] NVARCHAR(50) NULL,         -- Primary, Secondary, Principal, Mirror
        [SyncState] NVARCHAR(50) NULL,    -- Synchronized, Synchronizing, NotSynchronizing
        [SyncHealth] NVARCHAR(50) NULL,   -- Healthy, PartiallyHealthy, NotHealthy

        -- Lag Information
        [SendQueueSize_KB] BIGINT NULL,
        [RedoQueueSize_KB] BIGINT NULL,
        [LastCommitTime] DATETIME2 NULL,
        [LastRedoneTime] DATETIME2 NULL,
        [EstimatedLag_Seconds] INT NULL,

        INDEX [IX_HAStatus_ServerDB] NONCLUSTERED ([ServerID_Formatted], [DatabaseName], [SnapshotTime] DESC)
    )

    PRINT 'Table kpi.HAStatus created.'
END
GO

-- Blocking Sessions Table
IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'BlockingSessions' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE [kpi].[BlockingSessions] (
        [BlockingID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL DEFAULT GETDATE(),

        -- Session Information
        [BlockerSessionID] INT NULL,
        [BlockerLoginName] NVARCHAR(128) NULL,
        [BlockerHostName] NVARCHAR(128) NULL,
        [BlockerProgram] NVARCHAR(256) NULL,
        [BlockerDatabase] NVARCHAR(128) NULL,
        [BlockerCommand] NVARCHAR(MAX) NULL,
        [BlockerWaitTime_Ms] BIGINT NULL,

        -- Blocked Sessions
        [BlockedSessionCount] INT NULL,
        [BlockedSessionIDs] NVARCHAR(MAX) NULL,
        [TotalBlockedWaitTime_Ms] BIGINT NULL,

        INDEX [IX_BlockingSessions_Server] NONCLUSTERED ([ServerID_Formatted], [SnapshotTime] DESC)
    )

    PRINT 'Table kpi.BlockingSessions created.'
END
GO

-- Long Running Queries Table
IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'LongRunningQueries' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE [kpi].[LongRunningQueries] (
        [QueryID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL DEFAULT GETDATE(),

        -- Session Information
        [SessionID] INT NULL,
        [LoginName] NVARCHAR(128) NULL,
        [HostName] NVARCHAR(128) NULL,
        [ProgramName] NVARCHAR(256) NULL,
        [DatabaseName] NVARCHAR(128) NULL,

        -- Query Information
        [QueryText] NVARCHAR(MAX) NULL,
        [QueryHash] BINARY(8) NULL,
        [QueryPlanHash] BINARY(8) NULL,

        -- Execution Information
        [StartTime] DATETIME2 NULL,
        [Duration_Seconds] INT NULL,
        [CPU_Ms] BIGINT NULL,
        [Reads] BIGINT NULL,
        [Writes] BIGINT NULL,
        [LogicalReads] BIGINT NULL,

        -- Wait Information
        [WaitType] NVARCHAR(128) NULL,
        [WaitTime_Ms] BIGINT NULL,

        INDEX [IX_LongRunningQueries_Server] NONCLUSTERED ([ServerID_Formatted], [SnapshotTime] DESC)
    )

    PRINT 'Table kpi.LongRunningQueries created.'
END
GO

-- ============================================================================
-- SECTION 5: HISTORY TABLES (for data retention)
-- ============================================================================
PRINT ''
PRINT 'Creating history tables...'

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'KPISnapshotHistory' AND schema_id = SCHEMA_ID('history'))
BEGIN
    CREATE TABLE [history].[KPISnapshotHistory] (
        [SnapshotID] BIGINT NOT NULL,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [SnapshotTime] DATETIME2 NOT NULL,
        [CPU_Percent] DECIMAL(5,2) NULL,
        [Memory_Available_MB] BIGINT NULL,
        [Memory_Page_Life_Expectancy] INT NULL,
        [Connections_Total] INT NULL,
        [Connections_Blocked] INT NULL,
        [Batch_Requests_Sec] BIGINT NULL,
        [ArchivedDate] DATETIME2 NOT NULL DEFAULT GETDATE(),

        INDEX [IX_KPISnapshotHistory_ServerTime] NONCLUSTERED ([ServerID_Formatted], [SnapshotTime] DESC)
    )

    PRINT 'Table history.KPISnapshotHistory created.'
END
GO

-- ============================================================================
-- SECTION 6: MONITORING/ALERTING TABLES
-- ============================================================================
PRINT ''
PRINT 'Creating monitoring tables...'

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'Alerts' AND schema_id = SCHEMA_ID('monitoring'))
BEGIN
    CREATE TABLE [monitoring].[Alerts] (
        [AlertID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [AlertTime] DATETIME2 NOT NULL DEFAULT GETDATE(),
        [AlertType] NVARCHAR(100) NOT NULL,         -- CPU, Memory, Storage, Blocking, JobFailed, etc.
        [Severity] NVARCHAR(20) NOT NULL,           -- Critical, Warning, Information
        [MetricName] NVARCHAR(256) NULL,
        [MetricValue] NVARCHAR(256) NULL,
        [ThresholdValue] NVARCHAR(256) NULL,
        [Message] NVARCHAR(MAX) NULL,
        [IsAcknowledged] BIT NOT NULL DEFAULT 0,
        [AcknowledgedBy] NVARCHAR(128) NULL,
        [AcknowledgedDate] DATETIME2 NULL,
        [IsResolved] BIT NOT NULL DEFAULT 0,
        [ResolvedDate] DATETIME2 NULL,

        INDEX [IX_Alerts_Server] NONCLUSTERED ([ServerID_Formatted], [AlertTime] DESC),
        INDEX [IX_Alerts_Active] NONCLUSTERED ([IsResolved], [Severity], [AlertTime] DESC)
    )

    PRINT 'Table monitoring.Alerts created.'
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'AlertThresholds' AND schema_id = SCHEMA_ID('monitoring'))
BEGIN
    CREATE TABLE [monitoring].[AlertThresholds] (
        [ThresholdID] INT IDENTITY(1,1) PRIMARY KEY,
        [MetricName] NVARCHAR(256) NOT NULL,
        [WarningThreshold] DECIMAL(18,2) NULL,
        [CriticalThreshold] DECIMAL(18,2) NULL,
        [ComparisonOperator] NVARCHAR(10) NOT NULL DEFAULT '>',  -- >, <, >=, <=, =
        [IsEnabled] BIT NOT NULL DEFAULT 1,
        [Description] NVARCHAR(500) NULL,

        CONSTRAINT [UQ_AlertThresholds_MetricName] UNIQUE ([MetricName])
    )

    -- Insert default thresholds
    INSERT INTO [monitoring].[AlertThresholds] ([MetricName], [WarningThreshold], [CriticalThreshold], [ComparisonOperator], [Description])
    VALUES
        ('CPU_Percent', 80, 95, '>', 'CPU utilization percentage'),
        ('Memory_Available_MB', 2048, 512, '<', 'Available memory in MB'),
        ('Memory_Page_Life_Expectancy', 300, 60, '<', 'Page Life Expectancy in seconds'),
        ('Storage_Data_Free_Percent', 20, 10, '<', 'Data file free space percentage'),
        ('Storage_Log_Free_Percent', 25, 10, '<', 'Log file free space percentage'),
        ('Connections_Blocked', 5, 20, '>', 'Number of blocked connections'),
        ('IO_Stall_Read_Ms', 20, 50, '>', 'Average read stall in ms'),
        ('IO_Stall_Write_Ms', 20, 50, '>', 'Average write stall in ms')

    PRINT 'Table monitoring.AlertThresholds created with default values.'
END
GO

-- ============================================================================
-- SECTION 7: COLLECTION LOG TABLE
-- ============================================================================
PRINT ''
PRINT 'Creating collection log table...'

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'CollectionLog' AND schema_id = SCHEMA_ID('monitoring'))
BEGIN
    CREATE TABLE [monitoring].[CollectionLog] (
        [LogID] BIGINT IDENTITY(1,1) PRIMARY KEY,
        [ServerID_Formatted] NVARCHAR(256) NOT NULL,
        [CollectionTime] DATETIME2 NOT NULL DEFAULT GETDATE(),
        [CollectionType] NVARCHAR(100) NOT NULL,   -- KPI, Space, Jobs, HA, etc.
        [Status] NVARCHAR(50) NOT NULL,            -- Success, Failed, Partial
        [RowsCollected] INT NULL,
        [DurationMs] INT NULL,
        [ErrorMessage] NVARCHAR(MAX) NULL,

        INDEX [IX_CollectionLog_Server] NONCLUSTERED ([ServerID_Formatted], [CollectionTime] DESC)
    )

    PRINT 'Table monitoring.CollectionLog created.'
END
GO

-- ============================================================================
-- SECTION 8: CONFIGURATION TABLES
-- ============================================================================
PRINT ''
PRINT 'Creating configuration tables...'

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'Settings' AND schema_id = SCHEMA_ID('config'))
BEGIN
    CREATE TABLE [config].[Settings] (
        [SettingID] INT IDENTITY(1,1) PRIMARY KEY,
        [SettingName] NVARCHAR(256) NOT NULL,
        [SettingValue] NVARCHAR(MAX) NULL,
        [DataType] NVARCHAR(50) NOT NULL DEFAULT 'string',  -- string, int, bool, json
        [Description] NVARCHAR(500) NULL,
        [ModifiedDate] DATETIME2 NOT NULL DEFAULT GETDATE(),

        CONSTRAINT [UQ_Settings_Name] UNIQUE ([SettingName])
    )

    -- Insert default settings
    INSERT INTO [config].[Settings] ([SettingName], [SettingValue], [DataType], [Description])
    VALUES
        ('RetentionDays_KPI', '30', 'int', 'Days to keep KPI data before archiving'),
        ('RetentionDays_History', '365', 'int', 'Days to keep history data before purging'),
        ('RetentionDays_Logs', '7', 'int', 'Days to keep collection logs'),
        ('CollectionInterval_Minutes', '5', 'int', 'Default collection interval in minutes'),
        ('AlertEmail_Recipients', '', 'string', 'Email addresses for alerts (comma-separated)'),
        ('AlertEmail_Enabled', 'false', 'bool', 'Enable email alerts'),
        ('Version', '1.0.0', 'string', 'WatcherDB version'),
        ('Edition', 'Standard', 'string', 'WatcherDB edition')

    PRINT 'Table config.Settings created with default values.'
END
GO

-- ============================================================================
-- DEPLOYMENT SUMMARY
-- ============================================================================
PRINT ''
PRINT '============================================================'
PRINT 'WATCHERDB STANDARD - DEPLOYMENT SUMMARY'
PRINT '============================================================'
PRINT ''
PRINT 'Database: WatcherDB'
PRINT ''
PRINT 'Schemas created:'
PRINT '  - config     (configuration and inventory)'
PRINT '  - kpi        (KPI data tables)'
PRINT '  - history    (historical/archived data)'
PRINT '  - monitoring (alerts and logs)'
PRINT ''
PRINT 'Tables created:'
PRINT '  - config.ServerInventory'
PRINT '  - config.Settings'
PRINT '  - kpi.KPISnapshot'
PRINT '  - kpi.DatabaseSpace'
PRINT '  - kpi.JobsStatus'
PRINT '  - kpi.HAStatus'
PRINT '  - kpi.BlockingSessions'
PRINT '  - kpi.LongRunningQueries'
PRINT '  - history.KPISnapshotHistory'
PRINT '  - monitoring.Alerts'
PRINT '  - monitoring.AlertThresholds'
PRINT '  - monitoring.CollectionLog'
PRINT ''
PRINT 'NEXT STEPS:'
PRINT '1. Execute 01_WATCHERDB_TABLES.sql (if additional tables needed)'
PRINT '2. Execute 02_WATCHERDB_INDEXES.sql (performance indexes)'
PRINT '3. Execute 03_WATCHERDB_PROCEDURES.sql (collection procedures)'
PRINT '4. Execute 04_WATCHERDB_VIEWS.sql (dashboard views)'
PRINT '5. Execute 05_WATCHERDB_JOBS.sql (SQL Agent jobs)'
PRINT '6. Add servers to config.ServerInventory'
PRINT ''
PRINT 'Master deploy completed successfully!'
PRINT '============================================================'
GO

-- =====================================================================
-- SECTION: COLLECTION HISTORY (Historico de Coletas)
-- =====================================================================
-- Tabelas e views para rastreamento de cada execucao de coleta Python
-- Permite analise de tendencias e identificacao de problemas recorrentes
-- Adicionado em: 2025-12-18
-- =====================================================================

USE [WatcherDB]
GO

PRINT '';
PRINT '========================================';
PRINT 'Collection History Tables';
PRINT '========================================';
PRINT '';

-- ============================================================================
-- TABELA PRINCIPAL: kpi.Collection_History
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'kpi.Collection_History') AND type = 'U')
BEGIN
    CREATE TABLE kpi.Collection_History (
        Collection_ID           INT IDENTITY(1,1) PRIMARY KEY,
        Collection_Start        DATETIME2 NOT NULL,
        Collection_End          DATETIME2 NULL,
        Duration_Seconds        INT NULL,
        Mode                    VARCHAR(20) NOT NULL,

        Servers_Configured      INT NOT NULL DEFAULT 0,
        Servers_Online          INT NOT NULL DEFAULT 0,
        Servers_Skipped         INT NOT NULL DEFAULT 0,
        Servers_With_Errors     INT NOT NULL DEFAULT 0,
        Success_Rate_Pct        DECIMAL(5,2) NULL,

        Servers_Ping_Failed     INT NOT NULL DEFAULT 0,
        Servers_SQL_Down        INT NOT NULL DEFAULT 0,
        Servers_Auth_Error      INT NOT NULL DEFAULT 0,
        Servers_Timeout         INT NOT NULL DEFAULT 0,
        Servers_Query_Error     INT NOT NULL DEFAULT 0,

        Total_KPIs_Collected    INT NOT NULL DEFAULT 0,
        Total_Rows_Inserted     INT NOT NULL DEFAULT 0,
        KPIs_With_Errors        INT NOT NULL DEFAULT 0,

        Avg_Connection_Time_MS  FLOAT NULL,
        Max_Connection_Time_MS  FLOAT NULL,
        Avg_Query_Time_MS       FLOAT NULL,
        Max_Query_Time_MS       FLOAT NULL,
        Total_Queries_Executed  INT NOT NULL DEFAULT 0,

        Servers_Failed_JSON     NVARCHAR(MAX) NULL,
        Queries_Failed_JSON     NVARCHAR(MAX) NULL,
        Warnings_JSON           NVARCHAR(MAX) NULL,
        Summary_Text            NVARCHAR(MAX) NULL,

        Hostname                VARCHAR(255) NULL,
        Script_Version          VARCHAR(50) NULL,
        Python_Version          VARCHAR(50) NULL,
        Created_At              DATETIME2 NOT NULL DEFAULT GETDATE(),

        CONSTRAINT CK_Collection_Mode CHECK (Mode IN ('all', 'kpi-only', 'kpi-fast', 'full-no-kpi', 'locks-only', 'alwayson-only', 'kpi-prd', 'kpi-qa', 'kpi-tst'))
    );
    PRINT '  Created: kpi.Collection_History';
END
ELSE
    PRINT '  Exists: kpi.Collection_History';
GO

-- Indices
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_History_Start')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_History_Start
    ON kpi.Collection_History (Collection_Start DESC)
    INCLUDE (Mode, Servers_Configured, Servers_Online, Servers_Skipped, Success_Rate_Pct);
    PRINT '  Created: IX_Collection_History_Start';
END
GO

-- ============================================================================
-- TABELA DE DETALHES POR SERVIDOR
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'kpi.Collection_Server_Details') AND type = 'U')
BEGIN
    CREATE TABLE kpi.Collection_Server_Details (
        Detail_ID               INT IDENTITY(1,1) PRIMARY KEY,
        Collection_ID           INT NOT NULL,
        Server_ID               VARCHAR(255) NOT NULL,
        Status                  VARCHAR(20) NOT NULL,
        Skip_Reason             VARCHAR(50) NULL,
        Error_Message           NVARCHAR(MAX) NULL,
        Connection_Time_MS      FLOAT NULL,
        Total_Query_Time_MS     FLOAT NULL,
        Queries_Executed        INT NOT NULL DEFAULT 0,
        Queries_Failed          INT NOT NULL DEFAULT 0,
        Rows_Collected          INT NOT NULL DEFAULT 0,
        KPIs_Collected          VARCHAR(500) NULL,
        KPIs_Failed             VARCHAR(500) NULL,
        Services_Checked        BIT NOT NULL DEFAULT 0,
        Services_Down_Count     INT NOT NULL DEFAULT 0,
        Services_Down_List      VARCHAR(500) NULL,
        Start_Time              DATETIME2 NULL,
        End_Time                DATETIME2 NULL,
        CONSTRAINT FK_Collection_Server_Details_History
            FOREIGN KEY (Collection_ID)
            REFERENCES kpi.Collection_History(Collection_ID)
            ON DELETE CASCADE
    );
    PRINT '  Created: kpi.Collection_Server_Details';
END
ELSE
    PRINT '  Exists: kpi.Collection_Server_Details';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_Server_Details_ServerID')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_Server_Details_ServerID
    ON kpi.Collection_Server_Details (Server_ID, Collection_ID DESC);
    PRINT '  Created: IX_Collection_Server_Details_ServerID';
END
GO

-- ============================================================================
-- VIEWS DE ANALISE
-- ============================================================================

IF OBJECT_ID('monitoring.VW_Collection_Summary', 'V') IS NOT NULL
    DROP VIEW monitoring.VW_Collection_Summary;
GO

CREATE VIEW monitoring.VW_Collection_Summary AS
SELECT TOP 100
    Collection_ID, Collection_Start, Collection_End, Duration_Seconds, Mode,
    Servers_Configured, Servers_Online, Servers_Skipped, Servers_With_Errors, Success_Rate_Pct,
    Servers_Ping_Failed, Servers_SQL_Down,
    Total_KPIs_Collected, Total_Rows_Inserted, Avg_Query_Time_MS, Max_Query_Time_MS,
    CASE
        WHEN Servers_Skipped > 0 OR Servers_With_Errors > 0 THEN 'WARNING'
        WHEN Success_Rate_Pct < 95 THEN 'WARNING'
        ELSE 'OK'
    END AS Health_Status
FROM kpi.Collection_History
ORDER BY Collection_Start DESC;
GO

PRINT '  Created: monitoring.VW_Collection_Summary';
GO

IF OBJECT_ID('monitoring.VW_Problematic_Servers', 'V') IS NOT NULL
    DROP VIEW monitoring.VW_Problematic_Servers;
GO

CREATE VIEW monitoring.VW_Problematic_Servers AS
SELECT
    d.Server_ID,
    COUNT(*) AS Total_Collections,
    SUM(CASE WHEN d.Status = 'success' THEN 1 ELSE 0 END) AS Success_Count,
    SUM(CASE WHEN d.Status = 'skipped' THEN 1 ELSE 0 END) AS Skipped_Count,
    SUM(CASE WHEN d.Status = 'error' THEN 1 ELSE 0 END) AS Error_Count,
    CAST(SUM(CASE WHEN d.Status = 'success' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS DECIMAL(5,2)) AS Success_Rate_Pct,
    AVG(d.Connection_Time_MS) AS Avg_Connection_MS,
    MAX(d.Skip_Reason) AS Skip_Reason,
    MAX(h.Collection_Start) AS Last_Collection
FROM kpi.Collection_Server_Details d
INNER JOIN kpi.Collection_History h ON d.Collection_ID = h.Collection_ID
WHERE h.Collection_Start >= DATEADD(DAY, -7, GETDATE())
GROUP BY d.Server_ID
HAVING SUM(CASE WHEN d.Status IN ('skipped', 'error') THEN 1 ELSE 0 END) > 0;
GO

PRINT '  Created: monitoring.VW_Problematic_Servers';
GO

-- ============================================================================
-- PROCEDURE DE LIMPEZA
-- ============================================================================

IF OBJECT_ID('monitoring.usp_Purge_Collection_History', 'P') IS NOT NULL
    DROP PROCEDURE monitoring.usp_Purge_Collection_History;
GO

CREATE PROCEDURE monitoring.usp_Purge_Collection_History
    @retention_days INT = 90
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @cutoff_date DATETIME2 = DATEADD(DAY, -@retention_days, GETDATE());
    DECLARE @rows_deleted INT;

    DELETE FROM kpi.Collection_Server_Details
    WHERE Collection_ID IN (
        SELECT Collection_ID FROM kpi.Collection_History
        WHERE Collection_Start < @cutoff_date
    );
    SET @rows_deleted = @@ROWCOUNT;
    PRINT 'Details deleted: ' + CAST(@rows_deleted AS VARCHAR(10));

    DELETE FROM kpi.Collection_History
    WHERE Collection_Start < @cutoff_date;
    SET @rows_deleted = @@ROWCOUNT;
    PRINT 'History deleted: ' + CAST(@rows_deleted AS VARCHAR(10));
END;
GO

PRINT '  Created: monitoring.usp_Purge_Collection_History';
GO

PRINT '';
PRINT '  Collection History installation complete!';
PRINT '';
GO
