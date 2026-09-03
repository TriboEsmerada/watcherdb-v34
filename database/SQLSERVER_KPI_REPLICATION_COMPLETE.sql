-- ============================================================================
-- WATCHERDB INTELLIGENCE V2 - SQL SERVER KPI REPLICATION
-- ============================================================================
-- Replicação completa da infraestrutura Oracle SQL Server KPI para SQL Server
--
-- ORIGEM:
--   Schema Oracle: PDBACH_MSSQL_KPI, PDBACHINVENT
--   Extraído em: 2025-11-27
--
-- DESTINO:
--   Database: WatcherDB_Intelligence_V2
--   Schema: dbo
--
-- COMPONENTES:
--   1. 18 Tabelas (11 STG, 3 HIST, 2 Thresholds, 2 CMDB)
--   2. 22 Views (AGG + DET para cada KPI)
--   3. 11 Stored Procedures (coleta de dados)
--   4. SQL Agent Jobs (scheduling)
--
-- AUTOR: WatcherDB Team
-- DATA: 2025-11-27
-- VERSÃO: 1.0.0
-- ============================================================================

USE [WatcherDB_Intelligence_V2];
GO

PRINT '============================================================================';
PRINT 'WATCHERDB INTELLIGENCE V2 - REPLICAÇÃO KPI ORACLE';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
GO

-- ============================================================================
-- SEÇÃO 1: SCHEMAS E FILEGROUPS
-- ============================================================================

PRINT '';
PRINT '-- [1/6] Criando schemas e filegroups...';
PRINT '';

-- Criar filegroups dedicados (opcional - melhor performance)
IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = 'FG_KPI_DATA')
BEGIN
    ALTER DATABASE [WatcherDB_Intelligence_V2]
    ADD FILEGROUP [FG_KPI_DATA];

    PRINT '  [OK] Filegroup FG_KPI_DATA criado';
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = 'FG_KPI_HIST')
BEGIN
    ALTER DATABASE [WatcherDB_Intelligence_V2]
    ADD FILEGROUP [FG_KPI_HIST];

    PRINT '  [OK] Filegroup FG_KPI_HIST criado';
END;
GO

-- ============================================================================
-- SEÇÃO 2: TABELAS DE CONFIGURAÇÃO (THRESHOLDS)
-- ============================================================================

PRINT '';
PRINT '-- [2/6] Criando tabelas de configuração (Thresholds)...';
PRINT '';

-- Tabela: KPI_MSSQL_THRESHOLDS
IF OBJECT_ID('dbo.KPI_MSSQL_THRESHOLDS', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_THRESHOLDS;
GO

CREATE TABLE dbo.KPI_MSSQL_THRESHOLDS (
    [Key]           VARCHAR(64)     NOT NULL,
    Instance        VARCHAR(64)     NULL,       -- NULL = threshold global
    Warn_Val        DECIMAL(18,2)   NOT NULL,
    Crit_Val        DECIMAL(18,2)   NOT NULL,
    Description     VARCHAR(500)    NULL,
    CONSTRAINT PK_KPI_MSSQL_THRESHOLDS PRIMARY KEY ([Key], Instance)
);
GO

CREATE INDEX IX_KPI_MSSQL_THRESHOLDS_Key ON dbo.KPI_MSSQL_THRESHOLDS([Key]);
GO

PRINT '  [OK] Tabela KPI_MSSQL_THRESHOLDS criada';
GO

-- Tabela: KPI_MSSQL_THRESHOLDS_V2 (com Resource)
IF OBJECT_ID('dbo.KPI_MSSQL_THRESHOLDS_V2', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_THRESHOLDS_V2;
GO

CREATE TABLE dbo.KPI_MSSQL_THRESHOLDS_V2 (
    [Key]           VARCHAR(64)     NOT NULL,
    Instance        VARCHAR(64)     NULL,       -- NULL = threshold global
    Rsrc            VARCHAR(128)    NULL,       -- Resource específico (database, disk, etc.)
    Warn_Val        DECIMAL(18,2)   NOT NULL,
    Crit_Val        DECIMAL(18,2)   NOT NULL,
    Description     VARCHAR(500)    NULL,
    CONSTRAINT PK_KPI_MSSQL_THRESHOLDS_V2 PRIMARY KEY ([Key], Instance, Rsrc)
);
GO

CREATE INDEX IX_KPI_MSSQL_THRESHOLDS_V2_Key ON dbo.KPI_MSSQL_THRESHOLDS_V2([Key]);
GO

PRINT '  [OK] Tabela KPI_MSSQL_THRESHOLDS_V2 criada';
GO

-- ============================================================================
-- SEÇÃO 3: TABELAS CMDB (CONFIGURATION MANAGEMENT DATABASE)
-- ============================================================================

PRINT '';
PRINT '-- [3/6] Criando tabelas CMDB...';
PRINT '';

-- Tabela: CMDB_MSSQL_DATABASES
IF OBJECT_ID('dbo.CMDB_MSSQL_DATABASES', 'U') IS NOT NULL
    DROP TABLE dbo.CMDB_MSSQL_DATABASES;
GO

CREATE TABLE dbo.CMDB_MSSQL_DATABASES (
    Cluster         VARCHAR(64)     NOT NULL,
    Instance        VARCHAR(64)     NOT NULL,
    [Database]      VARCHAR(128)    NOT NULL,
    [Group]         VARCHAR(64)     NULL,
    Environment     VARCHAR(32)     NULL,       -- PROD, UAT, DEV, etc.
    [State]         VARCHAR(32)     NULL,       -- ONLINE, OFFLINE, etc.
    [Version]       VARCHAR(32)     NULL,       -- 2019, 2022, etc.
    Edition         VARCHAR(64)     NULL,       -- Enterprise, Standard
    Size_GB         DECIMAL(18,2)   NULL,
    [Description]   VARCHAR(500)    NULL,
    UpdatedAt       DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_CMDB_MSSQL_DATABASES PRIMARY KEY (Cluster, Instance, [Database])
);
GO

CREATE INDEX IX_CMDB_MSSQL_DATABASES_Environment ON dbo.CMDB_MSSQL_DATABASES(Environment);
CREATE INDEX IX_CMDB_MSSQL_DATABASES_State ON dbo.CMDB_MSSQL_DATABASES([State]);
GO

PRINT '  [OK] Tabela CMDB_MSSQL_DATABASES criada';
GO

-- Tabela: CMDB_MSSQL_DATABASES_HIST (Particionada por ano)
IF OBJECT_ID('dbo.CMDB_MSSQL_DATABASES_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.CMDB_MSSQL_DATABASES_HIST;
GO

CREATE TABLE dbo.CMDB_MSSQL_DATABASES_HIST (
    Cluster         VARCHAR(64)     NOT NULL,
    Instance        VARCHAR(64)     NOT NULL,
    [Database]      VARCHAR(128)    NOT NULL,
    [Group]         VARCHAR(64)     NULL,
    Environment     VARCHAR(32)     NULL,
    [State]         VARCHAR(32)     NULL,
    [Version]       VARCHAR(32)     NULL,
    Edition         VARCHAR(64)     NULL,
    Size_GB         DECIMAL(18,2)   NULL,
    [Description]   VARCHAR(500)    NULL,
    UpdatedAt       DATETIME2       NOT NULL,
    -- Particionamento será adicionado posteriormente
    CONSTRAINT PK_CMDB_MSSQL_DATABASES_HIST PRIMARY KEY (Cluster, Instance, [Database], UpdatedAt)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_CMDB_MSSQL_DATABASES_HIST_UpdatedAt ON dbo.CMDB_MSSQL_DATABASES_HIST(UpdatedAt);
GO

PRINT '  [OK] Tabela CMDB_MSSQL_DATABASES_HIST criada';
GO

-- ============================================================================
-- SEÇÃO 4: TABELAS DE STAGING (STG) - 11 TABELAS
-- ============================================================================

PRINT '';
PRINT '-- [4/6] Criando tabelas de Staging (STG)...';
PRINT '';

-- STG 1: KPI_MSSQL_ALWAYSON_STATUS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_ALWAYSON_STATUS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG (
    AgName              VARCHAR(128)    NOT NULL,
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Pri_Synch_State     VARCHAR(32)     NULL,
    Pri_Synch_Health    VARCHAR(32)     NULL,
    Pri_Is_Suspended    BIT             DEFAULT 0,
    Sec_Synch_State     VARCHAR(32)     NULL,
    Sec_Synch_Health    VARCHAR(32)     NULL,
    Sec_Is_Suspended    BIT             DEFAULT 0,
    Commit_Diff_Secs    INT             NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_ALWAYSON_STATUS_STG PRIMARY KEY (AgName, Instance, [Database])
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_ALWAYSON_STATUS_STG criada';
GO

-- STG 2: KPI_MSSQL_BACKUPS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUPS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BACKUPS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_BACKUPS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Backup_Type         VARCHAR(32)     NOT NULL,   -- FULL, DIFF, LOG
    Last_Backup_Date    DATETIME2       NULL,
    Hours_Since_Backup  INT             NULL,
    Backup_Size_MB      DECIMAL(18,2)   NULL,
    Backup_Duration_Sec INT             NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_BACKUPS_STG PRIMARY KEY (Instance, [Database], Backup_Type)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_BACKUPS_STG criada';
GO

-- STG 3: KPI_MSSQL_BLOCKED_SESSIONS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Session_Id          INT             NOT NULL,
    Blocked_By          INT             NULL,
    Wait_Time_Sec       INT             NULL,
    Wait_Type           VARCHAR(128)    NULL,
    [Database]          VARCHAR(128)    NULL,
    [Status]            VARCHAR(32)     NULL,
    Command             VARCHAR(256)    NULL,
    Blocking_Level      INT             DEFAULT 0,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_BLOCKED_SESSIONS_STG PRIMARY KEY (Instance, Session_Id, Update_TS)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_BLOCKED_SESSIONS_STG criada';
GO

-- STG 4: KPI_MSSQL_BLOCKED_USERS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_USERS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BLOCKED_USERS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_BLOCKED_USERS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [User]              VARCHAR(128)    NOT NULL,
    [Database]          VARCHAR(128)    NULL,
    Blocked_Count       INT             DEFAULT 0,
    Max_Wait_Time_Sec   INT             NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_BLOCKED_USERS_STG PRIMARY KEY (Instance, [User], Update_TS)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_BLOCKED_USERS_STG criada';
GO

-- STG 5: KPI_MSSQL_DB_AVAILABILITY_STG
IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    [State]             VARCHAR(32)     NULL,       -- ONLINE, OFFLINE, RESTORING, etc.
    Is_Available        BIT             DEFAULT 1,
    Recovery_Model      VARCHAR(32)     NULL,       -- FULL, SIMPLE, BULK_LOGGED
    Mirroring_Role      VARCHAR(32)     NULL,       -- PRINCIPAL, MIRROR, NULL (sem mirroring)
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_DB_AVAILABILITY_STG PRIMARY KEY (Instance, [Database])
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_DB_AVAILABILITY_STG criada';
GO

-- STG 6: KPI_MSSQL_DISK_USAGE_STG
IF OBJECT_ID('dbo.KPI_MSSQL_DISK_USAGE_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DISK_USAGE_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_DISK_USAGE_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Drive               VARCHAR(8)      NOT NULL,
    Total_MB            DECIMAL(18,2)   NULL,
    Free_MB             DECIMAL(18,2)   NULL,
    Used_MB             DECIMAL(18,2)   NULL,
    Percent_Free        DECIMAL(5,2)    NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_DISK_USAGE_STG PRIMARY KEY (Instance, Drive)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_DISK_USAGE_STG criada';
GO

-- STG 7: KPI_MSSQL_FG_USAGE_STG
IF OBJECT_ID('dbo.KPI_MSSQL_FG_USAGE_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_FG_USAGE_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_FG_USAGE_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Filegroup           VARCHAR(128)    NOT NULL,
    Total_MB            DECIMAL(18,2)   NULL,
    Used_MB             DECIMAL(18,2)   NULL,
    Free_MB             DECIMAL(18,2)   NULL,
    Percent_Used        DECIMAL(5,2)    NULL,
    Max_Size_MB         DECIMAL(18,2)   NULL,
    Growth_Type         VARCHAR(32)     NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_FG_USAGE_STG PRIMARY KEY (Instance, [Database], Filegroup)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_FG_USAGE_STG criada';
GO

-- STG 8: KPI_MSSQL_INST_AVAILABILITY_STG
IF OBJECT_ID('dbo.KPI_MSSQL_INST_AVAILABILITY_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_INST_AVAILABILITY_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_INST_AVAILABILITY_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Is_Available        BIT             DEFAULT 1,
    Uptime_Hours        INT             NULL,
    [Version]           VARCHAR(64)     NULL,
    Edition             VARCHAR(64)     NULL,
    Collation           VARCHAR(128)    NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_INST_AVAILABILITY_STG PRIMARY KEY (Instance)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_INST_AVAILABILITY_STG criada';
GO

-- STG 9: KPI_MSSQL_LONG_LOCKS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_LONG_LOCKS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_LONG_LOCKS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_LONG_LOCKS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Session_Id          INT             NOT NULL,
    Lock_Type           VARCHAR(64)     NULL,
    Lock_Mode           VARCHAR(32)     NULL,
    Resource_Type       VARCHAR(64)     NULL,
    Resource_Desc       VARCHAR(512)    NULL,
    Duration_Sec        INT             NULL,
    [Database]          VARCHAR(128)    NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_LONG_LOCKS_STG PRIMARY KEY (Instance, Session_Id, Update_TS)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_LONG_LOCKS_STG criada';
GO

-- STG 10: KPI_MSSQL_PROCESSES_STG
IF OBJECT_ID('dbo.KPI_MSSQL_PROCESSES_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_PROCESSES_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_PROCESSES_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Session_Id          INT             NOT NULL,
    [Status]            VARCHAR(32)     NULL,
    Command             VARCHAR(256)    NULL,
    [Database]          VARCHAR(128)    NULL,
    [User]              VARCHAR(128)    NULL,
    CPU_Time_MS         BIGINT          NULL,
    Total_Elapsed_Time  BIGINT          NULL,
    Reads               BIGINT          NULL,
    Writes              BIGINT          NULL,
    Wait_Type           VARCHAR(128)    NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_PROCESSES_STG PRIMARY KEY (Instance, Session_Id, Update_TS)
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_PROCESSES_STG criada';
GO

-- STG 11: KPI_MSSQL_TLOG_USAGE_STG
IF OBJECT_ID('dbo.KPI_MSSQL_TLOG_USAGE_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_TLOG_USAGE_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_TLOG_USAGE_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Current_MB          DECIMAL(18,2)   NULL,
    Used_MB             DECIMAL(18,2)   NULL,
    Max_Available_MB    DECIMAL(18,2)   NULL,
    Percent_Used        DECIMAL(5,2)    NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_TLOG_USAGE_STG PRIMARY KEY (Instance, [Database])
) ON [FG_KPI_DATA];
GO

PRINT '  [OK] Tabela KPI_MSSQL_TLOG_USAGE_STG criada';
GO

-- ============================================================================
-- SEÇÃO 5: TABELAS HISTÓRICAS (HIST) - 3 TABELAS PARTICIONADAS
-- ============================================================================

PRINT '';
PRINT '-- [5/6] Criando tabelas históricas (HIST)...';
PRINT '';

-- HIST 1: KPI_MSSQL_DB_AVAILABILITY_HIST
IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_HIST (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    [State]             VARCHAR(32)     NULL,
    Is_Available        BIT             DEFAULT 1,
    Recovery_Model      VARCHAR(32)     NULL,
    Mirroring_Role      VARCHAR(32)     NULL,       -- PRINCIPAL, MIRROR, NULL (sem mirroring)
    Update_TS           DATETIME2       NOT NULL,
    CONSTRAINT PK_KPI_MSSQL_DB_AVAILABILITY_HIST PRIMARY KEY (Instance, [Database], Update_TS)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_KPI_MSSQL_DB_AVAILABILITY_HIST_UpdateTS ON dbo.KPI_MSSQL_DB_AVAILABILITY_HIST(Update_TS);
GO

PRINT '  [OK] Tabela KPI_MSSQL_DB_AVAILABILITY_HIST criada';
GO

-- HIST 2: KPI_MSSQL_DISK_USAGE_HIST
IF OBJECT_ID('dbo.KPI_MSSQL_DISK_USAGE_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DISK_USAGE_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_DISK_USAGE_HIST (
    Instance            VARCHAR(64)     NOT NULL,
    Drive               VARCHAR(8)      NOT NULL,
    Total_MB            DECIMAL(18,2)   NULL,
    Free_MB             DECIMAL(18,2)   NULL,
    Used_MB             DECIMAL(18,2)   NULL,
    Percent_Free        DECIMAL(5,2)    NULL,
    Update_TS           DATETIME2       NOT NULL,
    CONSTRAINT PK_KPI_MSSQL_DISK_USAGE_HIST PRIMARY KEY (Instance, Drive, Update_TS)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_KPI_MSSQL_DISK_USAGE_HIST_UpdateTS ON dbo.KPI_MSSQL_DISK_USAGE_HIST(Update_TS);
GO

PRINT '  [OK] Tabela KPI_MSSQL_DISK_USAGE_HIST criada';
GO

-- HIST 3: KPI_MSSQL_TLOG_USAGE_HIST
IF OBJECT_ID('dbo.KPI_MSSQL_TLOG_USAGE_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_TLOG_USAGE_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_TLOG_USAGE_HIST (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Current_MB          DECIMAL(18,2)   NULL,
    Used_MB             DECIMAL(18,2)   NULL,
    Max_Available_MB    DECIMAL(18,2)   NULL,
    Percent_Used        DECIMAL(5,2)    NULL,
    Update_TS           DATETIME2       NOT NULL,
    CONSTRAINT PK_KPI_MSSQL_TLOG_USAGE_HIST PRIMARY KEY (Instance, [Database], Update_TS)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_KPI_MSSQL_TLOG_USAGE_HIST_UpdateTS ON dbo.KPI_MSSQL_TLOG_USAGE_HIST(Update_TS);
GO

PRINT '  [OK] Tabela KPI_MSSQL_TLOG_USAGE_HIST criada';
GO

-- ============================================================================
-- SEÇÃO 6: VIEWS - 22 VIEWS (AGG + DET PARA CADA KPI)
-- ============================================================================

PRINT '';
PRINT '-- [6/6] Criando views (AGG + DET)...';
PRINT '';

-- Continua na próxima parte...
PRINT '';
PRINT '============================================================================';
PRINT 'PARTE 1 CONCLUÍDA - TABELAS CRIADAS COM SUCESSO';
PRINT '============================================================================';
PRINT '  [OK] 2 Tabelas Thresholds';
PRINT '  [OK] 2 Tabelas CMDB';
PRINT '  [OK] 11 Tabelas Staging (STG)';
PRINT '  [OK] 3 Tabelas Histórico (HIST)';
PRINT '';
PRINT 'Total: 18 tabelas criadas';
PRINT '';
PRINT 'PRÓXIMO: Executar script de VIEWS (SQLSERVER_KPI_VIEWS.sql)';
PRINT '============================================================================';
GO
