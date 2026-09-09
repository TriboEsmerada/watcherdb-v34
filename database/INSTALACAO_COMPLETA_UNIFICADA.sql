-- =============================================
-- WATCHERDB INTELLIGENCE V2 - INSTALACAO COMPLETA
-- =============================================
-- Este script instala TUDO:
-- Database + Filegroups
-- Schemas + Tabelas (20+)
-- Views (60+) + Arquitetura _ACTIVE Blue/Green
-- Patterns (12)
-- Stored Procedures (15+)
-- SQL Agent Jobs (8: 3 analise + 5 coleta)
-- Servidores de TESTE (4)
-- =============================================
-- INSTRUÃ‡Ã•ES:
-- 1. Abrir este arquivo no SSMS
-- 2. Conectar ao servidor: SQLHDSTST505\I01
-- 3. Executar (F5)
-- 4. Aguardar (~3-5 minutos)
-- =============================================
-- VERSÃƒO: 2.0-TEST - Test Installation (4 servers)
-- DATA: 2025-11-27
-- AUTOR: WatcherDB Intelligence Team
-- =============================================

SET NOCOUNT ON;
GO

-- ============================================================================
-- CONFIGURAÃ‡Ã•ES PARA EVITAR TIMEOUT DE CONEXÃƒO
-- ============================================================================
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;
GO

-- Aumentar timeout de comando (30 minutos)
EXEC sp_configure 'remote query timeout', 1800;
RECONFIGURE;
GO

PRINT 'â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—';
PRINT 'â•‘                                                                   â•‘';
PRINT 'â•‘   WATCHERDB INTELLIGENCE V2 - INSTALAÃ‡ÃƒO DE TESTES       â•‘';
PRINT 'â•‘                                                                   â•‘';
PRINT 'â•‘   Este script instala TUDO em um Ãºnico comando:                  â•‘';
PRINT 'â•‘   âœ… Database + 2 Filegroups (PRIMARY + DATA)                     â•‘';
PRINT 'â•‘   âœ… 8 Schemas                                                    â•‘';
PRINT 'â•‘   âœ… 20 Tabelas (metadata, timeseries, raw, curated, meta)        â•‘';
PRINT 'â•‘   âœ… 3 Views (insights, business impact, predictions)             â•‘';
PRINT 'â•‘   âœ… 12 Patterns (CPU, memory, disk, security, etc.)              â•‘';
PRINT 'â•‘   âœ… 5 Stored Procedures (insert, detect, cleanup, alerts, health)â•‘';
PRINT 'â•‘   âœ… 8 SQL Agent Jobs (3 anÃ¡lise + 5 coleta)                      â•‘';
PRINT 'â•‘   âœ… 4 Servidores (3 PRODUÃ‡ÃƒO + 1 TEST)                          â•‘';
PRINT 'â•‘                                                                   â•‘';
PRINT 'â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';
PRINT 'Iniciando instalaÃ§Ã£o completa...';
PRINT '';
GO

-- =============================================
-- PARTE 1: DATABASE + TABELAS + VIEWS + PATTERNS
-- =============================================

-- =============================================
-- CONFIGURAÃ‡ÃƒO DE PATHS
-- =============================================
DECLARE @DataPath NVARCHAR(500) = N'F:\DATA1\Data\';
DECLARE @LogPath NVARCHAR(500) = N'L:\LOGS1\Data\';

PRINT 'ConfiguraÃ§Ã£o de Paths:';
PRINT '  Data Path: ' + @DataPath;
PRINT '  Log Path: ' + @LogPath;
PRINT '';

-- Detectar path padrÃ£o se necessÃ¡rio
IF @DataPath = N'F:\DATA1\Data\'
BEGIN
    EXEC master.dbo.xp_instance_regread
        N'HKEY_LOCAL_MACHINE',
        N'Software\Microsoft\MSSQLServer\MSSQLServer',
        N'DefaultData',
        @DataPath OUTPUT;

    IF @DataPath IS NULL
    BEGIN
        SELECT @DataPath = SUBSTRING(physical_name, 1, CHARINDEX(N'master.mdf', LOWER(physical_name)) - 1)
        FROM master.sys.master_files
        WHERE database_id = 1 AND file_id = 1;
    END

    -- Garantir que o path termine com barra
    IF RIGHT(@DataPath, 1) <> N'\'
        SET @DataPath = @DataPath + N'\';

    PRINT '  â„¹ï¸  Data Path detectado: ' + @DataPath;
END

-- Detectar log path padrÃ£o se necessÃ¡rio
IF @LogPath = N'L:\LOGS1\Data\'
BEGIN
    EXEC master.dbo.xp_instance_regread
        N'HKEY_LOCAL_MACHINE',
        N'Software\Microsoft\MSSQLServer\MSSQLServer',
        N'DefaultLog',
        @LogPath OUTPUT;

    IF @LogPath IS NULL
    BEGIN
        SELECT @LogPath = SUBSTRING(physical_name, 1, CHARINDEX(N'mastlog.ldf', LOWER(physical_name)) - 1)
        FROM master.sys.master_files
        WHERE database_id = 1 AND file_id = 2;
    END

    -- Se ainda for NULL, usar o mesmo path dos dados
    IF @LogPath IS NULL
        SET @LogPath = @DataPath;

    -- Garantir que o path termine com barra
    IF RIGHT(@LogPath, 1) <> N'\'
        SET @LogPath = @LogPath + N'\';

    PRINT '  â„¹ï¸  Log Path detectado: ' + @LogPath;
END

-- =============================================
-- STEP 1: CREATE DATABASE (SIMPLIFICADO)
-- =============================================
PRINT '';
PRINT '[1/13] Criando database WatcherDB_Intelligence...';

IF DB_ID('WatcherDB_Intelligence') IS NOT NULL
BEGIN
    PRINT '  âš ï¸  Database jÃ¡ existe! Continuando instalaÃ§Ã£o (modo atualizaÃ§Ã£o)...';
    PRINT '  âœ… Usando database existente';
END
ELSE
BEGIN
    -- Criar database apenas se nÃ£o existir
    DECLARE @SQL NVARCHAR(MAX);
    SET @SQL = N'
    CREATE DATABASE [WatcherDB_Intelligence]
    ON PRIMARY
    (
        NAME = N''WatcherDB_Intelligence_Primary'',
        FILENAME = N''' + @DataPath + N'WatcherDB_Intelligence.mdf'',
        SIZE = 512MB,
        MAXSIZE = UNLIMITED,
        FILEGROWTH = 128MB
    ),
    FILEGROUP [DATA]
    (
        NAME = N''WatcherDB_Intelligence_Data'',
        FILENAME = N''' + @DataPath + N'WatcherDB_Intelligence_Data.ndf'',
        SIZE = 2GB,
        MAXSIZE = UNLIMITED,
        FILEGROWTH = 256MB
    )
    LOG ON
    (
        NAME = N''WatcherDB_Intelligence_Log'',
        FILENAME = N''' + @LogPath + N'WatcherDB_Intelligence_Log.ldf'',
        SIZE = 256MB,
        MAXSIZE = 10GB,
        FILEGROWTH = 64MB
    );';
    EXEC sp_executesql @SQL;
    
    -- ConfiguraÃ§Ãµes
    ALTER DATABASE [WatcherDB_Intelligence] SET RECOVERY SIMPLE;
    ALTER DATABASE [WatcherDB_Intelligence] SET AUTO_CREATE_STATISTICS ON;
    ALTER DATABASE [WatcherDB_Intelligence] SET AUTO_UPDATE_STATISTICS ON;
    ALTER DATABASE [WatcherDB_Intelligence] SET AUTO_SHRINK OFF;
    ALTER DATABASE [WatcherDB_Intelligence] SET PAGE_VERIFY CHECKSUM;
    
    PRINT '  âœ… Database criado com 2 filegroups!';
    PRINT '      PRIMARY: System metadata';
    PRINT '      DATA: All user tables, indexes, and data';
END
GO

-- Agora usar o database (apÃ³s o GO, o database jÃ¡ existe)
USE [WatcherDB_Intelligence];
GO

-- =============================================
-- STEP 1.5: ADD KPI FILEGROUPS
-- =============================================
PRINT '';
PRINT '[1.5/18] Adicionando filegroups KPI...';

-- Filegroup para dados KPI (staging)
IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = 'FG_KPI_DATA')
BEGIN
    ALTER DATABASE [WatcherDB_Intelligence]
    ADD FILEGROUP [FG_KPI_DATA];
    PRINT '  âœ… Filegroup FG_KPI_DATA criado';
END;
GO

-- Filegroup para histÃ³rico KPI
IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = 'FG_KPI_HIST')
BEGIN
    ALTER DATABASE [WatcherDB_Intelligence]
    ADD FILEGROUP [FG_KPI_HIST];
    PRINT '  âœ… Filegroup FG_KPI_HIST criado';
END;
GO

-- Adicionar arquivos aos filegroups KPI
USE [WatcherDB_Intelligence];
GO

-- Obter o path do database
DECLARE @KPI_DataPath NVARCHAR(260);
SELECT @KPI_DataPath = SUBSTRING(physical_name, 1, CHARINDEX(N'WatcherDB_Intelligence.mdf', LOWER(physical_name)) - 1)
FROM sys.master_files
WHERE database_id = DB_ID('WatcherDB_Intelligence')
  AND file_id = 1;

IF @KPI_DataPath IS NULL
BEGIN
    -- Tentar obter do filegroup PRIMARY
    SELECT @KPI_DataPath = SUBSTRING(physical_name, 1, LEN(physical_name) - LEN('WatcherDB_Intelligence.mdf'))
    FROM sys.master_files
    WHERE database_id = DB_ID('WatcherDB_Intelligence')
      AND name LIKE '%Primary%';
END

IF @KPI_DataPath IS NULL
    SET @KPI_DataPath = 'F:\MSSQL\Data\'; -- Fallback

-- Arquivo para FG_KPI_DATA
IF NOT EXISTS (SELECT 1 FROM sys.database_files WHERE name = 'WatcherDB_Intelligence_KPI_Data')
BEGIN
    DECLARE @SQL_KPI_Data NVARCHAR(MAX);
    SET @SQL_KPI_Data = N'
    ALTER DATABASE [WatcherDB_Intelligence]
    ADD FILE (
        NAME = N''WatcherDB_Intelligence_KPI_Data'',
        FILENAME = N''' + @KPI_DataPath + N'WatcherDB_Intelligence_KPI_Data.ndf'',
        SIZE = 512MB,
        MAXSIZE = UNLIMITED,
        FILEGROWTH = 128MB
    ) TO FILEGROUP [FG_KPI_DATA];';
    EXEC sp_executesql @SQL_KPI_Data;
    PRINT '  âœ… Arquivo FG_KPI_DATA criado';
END
ELSE
BEGIN
    PRINT '  [INFO] Arquivo FG_KPI_DATA jÃ¡ existe';
END
GO

-- Arquivo para FG_KPI_HIST
IF NOT EXISTS (SELECT 1 FROM sys.database_files WHERE name = 'WatcherDB_Intelligence_KPI_Hist')
BEGIN
    DECLARE @KPI_HistPath NVARCHAR(260);
    SELECT @KPI_HistPath = SUBSTRING(physical_name, 1, CHARINDEX(N'WatcherDB_Intelligence.mdf', LOWER(physical_name)) - 1)
    FROM sys.master_files
    WHERE database_id = DB_ID('WatcherDB_Intelligence')
      AND file_id = 1;
    
    IF @KPI_HistPath IS NULL
        SET @KPI_HistPath = 'F:\MSSQL\Data\';
    
    DECLARE @SQL_KPI_Hist NVARCHAR(MAX);
    SET @SQL_KPI_Hist = N'
    ALTER DATABASE [WatcherDB_Intelligence]
    ADD FILE (
        NAME = N''WatcherDB_Intelligence_KPI_Hist'',
        FILENAME = N''' + @KPI_HistPath + N'WatcherDB_Intelligence_KPI_Hist.ndf'',
        SIZE = 512MB,
        MAXSIZE = UNLIMITED,
        FILEGROWTH = 128MB
    ) TO FILEGROUP [FG_KPI_HIST];';
    EXEC sp_executesql @SQL_KPI_Hist;
    PRINT '  âœ… Arquivo FG_KPI_HIST criado';
END
ELSE
BEGIN
    PRINT '  [INFO] Arquivo FG_KPI_HIST jÃ¡ existe';
END
GO

PRINT '  âœ… Filegroups KPI criados (FG_KPI_DATA + FG_KPI_HIST) com arquivos!';
GO

-- =============================================
-- STEP 2: CREATE SCHEMAS
-- =============================================
PRINT '';
PRINT '[2/13] Criando schemas...';

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'metadata')
    EXEC('CREATE SCHEMA [metadata]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'timeseries')
    EXEC('CREATE SCHEMA [timeseries]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'alerts')
    EXEC('CREATE SCHEMA [alerts]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'analytics')
    EXEC('CREATE SCHEMA [analytics]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'raw')
    EXEC('CREATE SCHEMA [raw]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'refined')
    EXEC('CREATE SCHEMA [refined]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'curated')
    EXEC('CREATE SCHEMA [curated]');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'meta')
    EXEC('CREATE SCHEMA [meta]');

PRINT '  âœ… 8 schemas criados!';
GO

-- =============================================
-- STEP 3: METADATA TABLES (PRIMARY)
-- =============================================
PRINT '';
PRINT '[3/13] Criando tabelas metadata...';

IF OBJECT_ID('[metadata].[tenants]', 'U') IS NULL
BEGIN
    CREATE TABLE [metadata].[tenants] (
        tenant_id VARCHAR(50) PRIMARY KEY,
        tenant_name NVARCHAR(200) NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        [plan] VARCHAR(50) NOT NULL DEFAULT 'free',
        max_servers INT NOT NULL DEFAULT 10,
        retention_days INT NOT NULL DEFAULT 30,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    ) ON [PRIMARY];
END
GO

-- Tabela de configuraÃ§Ã£o de servidores otimizada para suportar mÃºltiplos atributos
CREATE TABLE [metadata].[server_config] (
    config_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    instance_id VARCHAR(100) NOT NULL,
    host VARCHAR(100) NULL,
    instance_name VARCHAR(50) NULL,
    port INT NULL DEFAULT 1433,
    environment VARCHAR(50) NULL,
    priority INT NULL DEFAULT 1,
    description NVARCHAR(500) NULL,
    is_active BIT NOT NULL DEFAULT 1,
    config_key VARCHAR(100) NULL,
    config_value NVARCHAR(MAX) NULL,
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_server_config_tenant FOREIGN KEY (tenant_id) REFERENCES [metadata].[tenants](tenant_id),
    CONSTRAINT UQ_server_config UNIQUE (tenant_id, instance_id, config_key)
) ON [PRIMARY];

CREATE TABLE [metadata].[data_sources] (
    source_id INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    connection_string NVARCHAR(500),
    is_active BIT NOT NULL DEFAULT 1,
    last_collection DATETIME2,
    CONSTRAINT FK_data_sources_tenant FOREIGN KEY (tenant_id) REFERENCES [metadata].[tenants](tenant_id)
) ON [PRIMARY];

-- Tabela de alertas
CREATE TABLE [alerts].[alert_history] (
    alert_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    alert_definition_id INT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    [message] NVARCHAR(500) NOT NULL,
    alert_data NVARCHAR(MAX),
    triggered_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    resolved_at DATETIME2 NULL
) ON [PRIMARY];

PRINT '  âœ… 4 tabelas metadata/alerts criadas!';
GO

-- =============================================
-- STEP 4: TIMESERIES TABLES (DATA)
-- =============================================
PRINT '';
PRINT '[4/13] Criando tabelas timeseries...';

-- OTIMIZADO para SQL Server 2016 (compatibilidade com columnstore)
CREATE TABLE [timeseries].[metrics] (
    metric_id BIGINT IDENTITY(1,1) NOT NULL,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    server_id VARCHAR(100) NOT NULL,
    collector_name VARCHAR(100) NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    metric_value FLOAT NOT NULL,
    [timestamp] DATETIME2 NOT NULL,
    date_partition AS CAST([timestamp] AS DATE),
    tags NVARCHAR(500),
    CONSTRAINT PK_metrics PRIMARY KEY CLUSTERED ([timestamp], metric_id)
) ON [DATA];

-- IMPORTANTE: Criar columnstore PRIMEIRO
CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_metrics_analytics
ON [timeseries].[metrics] (tenant_id, server_id, collector_name, metric_name, metric_value, [timestamp])
ON [DATA];

-- Ãndices rowstore
CREATE NONCLUSTERED INDEX IX_metrics_server_metric_time
ON [timeseries].[metrics] (server_id, metric_name, [timestamp] DESC)
INCLUDE (metric_value, collector_name, tenant_id, tags)
ON [DATA];

CREATE NONCLUSTERED INDEX IX_metrics_date_server
ON [timeseries].[metrics] ([timestamp], server_id, metric_name)
INCLUDE (metric_value, collector_name)
ON [DATA];

-- Pre-aggregated tables
CREATE TABLE [timeseries].[metrics_1min] (
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    server_id VARCHAR(100) NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    window_start DATETIME2 NOT NULL,
    avg_value FLOAT,
    min_value FLOAT,
    max_value FLOAT,
    sample_count INT,
    CONSTRAINT PK_metrics_1min PRIMARY KEY CLUSTERED (server_id, metric_name, window_start)
) ON [DATA];

CREATE TABLE [timeseries].[metrics_5min] (
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    server_id VARCHAR(100) NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    window_start DATETIME2 NOT NULL,
    avg_value FLOAT,
    min_value FLOAT,
    max_value FLOAT,
    sample_count INT,
    CONSTRAINT PK_metrics_5min PRIMARY KEY CLUSTERED (server_id, metric_name, window_start)
) ON [DATA];

CREATE TABLE [timeseries].[metrics_1hour] (
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    server_id VARCHAR(100) NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    window_start DATETIME2 NOT NULL,
    avg_value FLOAT,
    min_value FLOAT,
    max_value FLOAT,
    sample_count INT,
    CONSTRAINT PK_metrics_1hour PRIMARY KEY CLUSTERED (server_id, metric_name, window_start)
) ON [DATA];

PRINT '  âœ… 4 tabelas timeseries criadas!';
GO

-- =============================================
-- STEP 5: RAW TABLES (DATA)
-- =============================================
PRINT '';
PRINT '[5/13] Criando tabelas raw...';

CREATE TABLE [raw].[sql_error_logs] (
    log_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    log_date DATETIME2 NOT NULL,
    severity VARCHAR(20),
    [message] NVARCHAR(MAX) NOT NULL,
    error_number INT,
    is_crash_dump BIT DEFAULT 0,
    is_corruption_error BIT DEFAULT 0,
    date_partition AS CAST(log_date AS DATE) PERSISTED
) ON [DATA];

CREATE NONCLUSTERED INDEX IX_sql_error_logs_instance_date
    ON [raw].[sql_error_logs] (instance_id, log_date DESC) ON [DATA];

CREATE TABLE [raw].[windows_events] (
    event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    event_time DATETIME2 NOT NULL,
    event_code INT NOT NULL,
    event_source NVARCHAR(200),
    [message] NVARCHAR(MAX),
    is_reboot_related BIT DEFAULT 0,
    is_security_related BIT DEFAULT 0
) ON [DATA];

CREATE NONCLUSTERED INDEX IX_windows_events_instance_time
    ON [raw].[windows_events] (instance_id, event_time DESC) ON [DATA];

CREATE TABLE [raw].[sql_agent_jobs] (
    job_log_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    job_name NVARCHAR(200) NOT NULL,
    job_start_time DATETIME2 NOT NULL,
    job_end_time DATETIME2,
    job_status VARCHAR(20),
    duration_seconds INT,
    event_type VARCHAR(50),
    event_details NVARCHAR(MAX)
) ON [DATA];

CREATE TABLE [raw].[alwayson_health] (
    health_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    [timestamp] DATETIME2 NOT NULL,
    [role] VARCHAR(20),
    synchronization_state VARCHAR(50),
    log_send_queue_size_kb BIGINT,
    redo_queue_size_kb BIGINT,
    estimated_data_loss_seconds INT,
    is_seeding BIT DEFAULT 0
) ON [DATA];

PRINT '  âœ… 4 tabelas raw criadas!';
GO

-- =============================================
-- STEP 6: CURATED TABLES (DATA)
-- =============================================
PRINT '';
PRINT '[6/13] Criando tabelas curated...';

CREATE TABLE [curated].[insights] (
    insight_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    server_id VARCHAR(100) NULL,
    pattern_id INT NOT NULL,
    insight_type VARCHAR(100) NOT NULL,
    summary NVARCHAR(500) NOT NULL,
    [description] NVARCHAR(MAX),
    details NVARCHAR(MAX),
    evidence_refs NVARCHAR(MAX),
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    estimated_impact_score FLOAT DEFAULT 0.0,
    first_detected DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    last_seen DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    occurrence_count INT NOT NULL DEFAULT 1,
    is_acknowledged BIT NOT NULL DEFAULT 0,
    is_resolved BIT NOT NULL DEFAULT 0,
    acknowledged_at DATETIME2,
    resolved_at DATETIME2
) ON [DATA];

CREATE NONCLUSTERED INDEX IX_insights_active
    ON [curated].[insights] (is_resolved, severity, instance_id) ON [DATA];

CREATE TABLE [curated].[server_dna_snapshots] (
    snapshot_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL,
    behavioral_signature NVARCHAR(MAX) NOT NULL,
    cpu_rhythm_pattern VARCHAR(100),
    io_pattern VARCHAR(100),
    workload_type VARCHAR(100),
    personality_type VARCHAR(50),
    risk_profile VARCHAR(50),
    similarity_to_previous FLOAT,
    personality_changed BIT NOT NULL DEFAULT 0,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
) ON [DATA];

CREATE NONCLUSTERED INDEX IX_server_dna_instance_date
    ON [curated].[server_dna_snapshots] (instance_id, snapshot_date DESC) ON [DATA];

CREATE TABLE [curated].[business_impact_config] (
    config_id INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(200) NOT NULL,
    transaction_type VARCHAR(100),
    revenue_per_transaction DECIMAL(18,2),
    transactions_per_minute INT,
    normal_conversion_rate FLOAT,
    business_criticality VARCHAR(20) NOT NULL DEFAULT 'medium',
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_business_impact_entity UNIQUE (tenant_id, entity_type, entity_id)
) ON [DATA];

CREATE TABLE [curated].[business_impact_events] (
    impact_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    insight_id BIGINT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(200) NOT NULL,
    incident_start DATETIME2 NOT NULL,
    incident_end DATETIME2 NULL,
    duration_minutes INT,
    revenue_lost_usd DECIMAL(18,2),
    transactions_lost BIGINT,
    users_affected BIGINT,
    total_business_impact_usd DECIMAL(18,2),
    impact_per_minute_usd DECIMAL(18,2),
    priority_score INT NOT NULL DEFAULT 50,
    is_resolved BIT NOT NULL DEFAULT 0,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
) ON [DATA];

CREATE NONCLUSTERED INDEX IX_business_impact_priority
    ON [curated].[business_impact_events] (priority_score DESC, is_resolved)
    WHERE is_resolved = 0;

CREATE TABLE [curated].[learned_contexts] (
    context_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    context_name NVARCHAR(200) NOT NULL,
    context_type VARCHAR(50) NOT NULL,
    day_of_week VARCHAR(20),
    hour_of_day INT,
    metric_name VARCHAR(200),
    expected_value_min FLOAT,
    expected_value_max FLOAT,
    expected_value_avg FLOAT,
    observations_count INT NOT NULL DEFAULT 0,
    confidence FLOAT NOT NULL DEFAULT 0.0,
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
) ON [DATA];

CREATE TABLE [curated].[contextual_anomalies] (
    anomaly_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    detected_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    metric_name VARCHAR(200) NOT NULL,
    metric_value FLOAT NOT NULL,
    is_statistical_anomaly BIT NOT NULL,
    deviation_sigma FLOAT,
    context_classification VARCHAR(50) NOT NULL,
    context_confidence FLOAT NOT NULL DEFAULT 0.0,
    action_taken VARCHAR(50) NOT NULL,
    insight_id BIGINT NULL
) ON [DATA];

CREATE TABLE [curated].[failure_predictions] (
    prediction_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL DEFAULT 'default',
    instance_id VARCHAR(100) NOT NULL,
    prediction_date DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    predicted_failure_type VARCHAR(100) NOT NULL,
    probability_7d FLOAT NOT NULL DEFAULT 0.0,
    probability_14d FLOAT NOT NULL DEFAULT 0.0,
    probability_30d FLOAT NOT NULL DEFAULT 0.0,
    model_confidence FLOAT NOT NULL DEFAULT 0.5,
    recommended_action VARCHAR(50),
    urgency_level VARCHAR(20),
    safe_window_days INT
) ON [DATA];

CREATE NONCLUSTERED INDEX IX_failure_prediction_high_risk
    ON [curated].[failure_predictions] (probability_30d DESC, instance_id)
    WHERE probability_30d > 0.5;

PRINT '  âœ… 8 tabelas curated criadas!';
GO

-- =============================================
-- STEP 7: META TABLES (PRIMARY)
-- =============================================
PRINT '';
PRINT '[7/13] Criando tabelas meta...';

CREATE TABLE [meta].[patterns] (
    pattern_id INT IDENTITY(1,1) PRIMARY KEY,
    pattern_name NVARCHAR(200) NOT NULL UNIQUE,
    pattern_category VARCHAR(50) NOT NULL,
    [description] NVARCHAR(MAX),
    detection_query NVARCHAR(MAX),
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    confidence_threshold FLOAT NOT NULL DEFAULT 0.7,
    detection_frequency_minutes INT NOT NULL DEFAULT 15,
    is_ml_based BIT NOT NULL DEFAULT 0,
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
) ON [PRIMARY];

CREATE TABLE [meta].[pattern_execution_log] (
    execution_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    pattern_id INT NOT NULL,
    execution_start DATETIME2 NOT NULL,
    execution_end DATETIME2,
    instances_checked INT,
    insights_created INT,
    is_successful BIT NOT NULL DEFAULT 0,
    CONSTRAINT FK_pattern_exec_pattern FOREIGN KEY (pattern_id) REFERENCES [meta].[patterns](pattern_id)
) ON [PRIMARY];

PRINT '  âœ… 2 tabelas meta criadas!';
GO

-- =============================================
-- STEP 7.5: KPI TABLES (FG_KPI_DATA + FG_KPI_HIST)
-- =============================================
PRINT '';
PRINT '[7.5/18] Criando tabelas KPI Oracle (22 tabelas)...';

-- ============================================================================
-- TABELAS DE CONFIGURAÃ‡ÃƒO (THRESHOLDS) - 2 TABELAS
-- ============================================================================

-- Tabela: KPI_MSSQL_THRESHOLDS
IF OBJECT_ID('dbo.KPI_MSSQL_THRESHOLDS', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_THRESHOLDS;
GO

CREATE TABLE dbo.KPI_MSSQL_THRESHOLDS (
    [Key]           VARCHAR(64)     NOT NULL,
    Instance        VARCHAR(64)     NOT NULL DEFAULT '',
    Warn_Val        DECIMAL(18,2)   NOT NULL,
    Crit_Val        DECIMAL(18,2)   NOT NULL,
    Description     VARCHAR(500)    NULL,
    CONSTRAINT PK_KPI_MSSQL_THRESHOLDS PRIMARY KEY ([Key], Instance)
);
GO

CREATE INDEX IX_KPI_MSSQL_THRESHOLDS_Key ON dbo.KPI_MSSQL_THRESHOLDS([Key]);
GO

-- Tabela: KPI_MSSQL_THRESHOLDS_V2
IF OBJECT_ID('dbo.KPI_MSSQL_THRESHOLDS_V2', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_THRESHOLDS_V2;
GO

CREATE TABLE dbo.KPI_MSSQL_THRESHOLDS_V2 (
    [Key]           VARCHAR(64)     NOT NULL,
    Instance        VARCHAR(64)     NOT NULL DEFAULT '',
    Rsrc            VARCHAR(128)    NOT NULL DEFAULT '',
    Warn_Val        DECIMAL(18,2)   NOT NULL,
    Crit_Val        DECIMAL(18,2)   NOT NULL,
    Description     VARCHAR(500)    NULL,
    CONSTRAINT PK_KPI_MSSQL_THRESHOLDS_V2 PRIMARY KEY ([Key], Instance, Rsrc)
);
GO

CREATE INDEX IX_KPI_MSSQL_THRESHOLDS_V2_Key ON dbo.KPI_MSSQL_THRESHOLDS_V2([Key]);
GO

PRINT '  âœ… 2 tabelas Thresholds criadas';
GO

-- ============================================================================
-- TABELAS CMDB - 2 TABELAS
-- ============================================================================

-- Tabela: CMDB_MSSQL_DATABASES
IF OBJECT_ID('dbo.CMDB_MSSQL_DATABASES', 'U') IS NOT NULL
    DROP TABLE dbo.CMDB_MSSQL_DATABASES;
GO

CREATE TABLE dbo.CMDB_MSSQL_DATABASES (
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
    UpdatedAt       DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_CMDB_MSSQL_DATABASES PRIMARY KEY (Cluster, Instance, [Database])
);
GO

CREATE INDEX IX_CMDB_MSSQL_DATABASES_Environment ON dbo.CMDB_MSSQL_DATABASES(Environment);
CREATE INDEX IX_CMDB_MSSQL_DATABASES_State ON dbo.CMDB_MSSQL_DATABASES([State]);
GO

-- Tabela: CMDB_MSSQL_DATABASES_HIST
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
    CONSTRAINT PK_CMDB_MSSQL_DATABASES_HIST PRIMARY KEY (Cluster, Instance, [Database], UpdatedAt)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_CMDB_MSSQL_DATABASES_HIST_UpdatedAt ON dbo.CMDB_MSSQL_DATABASES_HIST(UpdatedAt);
GO

PRINT '  âœ… 2 tabelas CMDB criadas';
GO

-- ============================================================================
-- TABELAS DE STAGING (STG) - 14 TABELAS + 1 TABELA DE FALHAS DE BACKUP
-- ============================================================================

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
    -- Coluna computed para indicar o motivo do problema
    Problem_Reason AS (
        CASE 
            -- MÃºltiplos problemas (prioridade: Health > Suspended > State)
            WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY') 
                  OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
                  OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                 AND (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1) THEN 'Health Problem + Suspended'
            WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY') 
                  OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
                  OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                 AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'Health Problem + Sync State'
            WHEN (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
                 AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'Suspended + Sync State'
            
            -- Problemas individuais de Health
            WHEN Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL THEN 'No Health Data (Both Replicas)'
            WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY' 
                 AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY' THEN 'Both Replicas Unhealthy'
            WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY' THEN 'Primary Replica Unhealthy (' + Pri_Synch_Health + ')'
            WHEN Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY' THEN 'Secondary Replica Unhealthy (' + Sec_Synch_Health + ')'
            
            -- Problemas de Suspended
            WHEN Pri_Is_Suspended = 1 AND Sec_Is_Suspended = 1 THEN 'Both Replicas Suspended'
            WHEN Pri_Is_Suspended = 1 THEN 'Primary Replica Suspended'
            WHEN Sec_Is_Suspended = 1 THEN 'Secondary Replica Suspended'
            
            -- Problemas de Sync State
            WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING') 
                 AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING') 
                 THEN 'Both Replicas Sync State Problem (' + Pri_Synch_State + ' / ' + Sec_Synch_State + ')'
            WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING') 
                 THEN 'Primary Sync State Problem (' + Pri_Synch_State + ')'
            WHEN Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING') 
                 THEN 'Secondary Sync State Problem (' + Sec_Synch_State + ')'
            
            ELSE NULL
        END
    ) PERSISTED,
    CONSTRAINT PK_KPI_MSSQL_ALWAYSON_STATUS_STG PRIMARY KEY (AgName, Instance, [Database])
) ON [FG_KPI_DATA];
GO

-- STG 2: KPI_MSSQL_BACKUPS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUPS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BACKUPS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_BACKUPS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Backup_Type         VARCHAR(32)     NOT NULL,
    Last_Backup_Date    DATETIME2       NULL,
    Hours_Since_Backup  INT             NULL,
    Backup_Size_MB      DECIMAL(18,2)   NULL,
    Backup_Duration_Sec INT             NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_BACKUPS_STG PRIMARY KEY (Instance, [Database], Backup_Type)
) ON [FG_KPI_DATA];
GO

-- STG 2.1: KPI_MSSQL_BACKUP_STATUS_STG (Status consolidado de backups por database)
-- Esta tabela armazena o status atual de backup de cada database
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUP_STATUS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BACKUP_STATUS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_BACKUP_STATUS_STG (
    Instance                    VARCHAR(128)    NOT NULL,
    [Database]                  VARCHAR(128)    NOT NULL,
    Last_Full_Backup            DATETIME2       NULL,
    Last_Diff_Backup            DATETIME2       NULL,
    Last_Log_Backup             DATETIME2       NULL,
    Hours_Since_Full_Backup     INT             NULL,
    Hours_Since_Diff_Backup     INT             NULL,
    Hours_Since_Log_Backup      INT             NULL,
    Full_Backup_Status          VARCHAR(32)     NULL,
    Diff_Backup_Status          VARCHAR(32)     NULL,
    Log_Backup_Status           VARCHAR(32)     NULL,
    Recovery_Model              VARCHAR(32)     NULL,
    Database_State              VARCHAR(32)     NULL,
    Is_Full_Backup_Overdue      BIT             NOT NULL DEFAULT 0,
    Is_Log_Backup_Overdue       BIT             NOT NULL DEFAULT 0,
    Update_TS                   DATETIME2       NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_BACKUP_STATUS_STG PRIMARY KEY (Instance, [Database])
) ON [FG_KPI_DATA];
GO

CREATE NONCLUSTERED INDEX IX_BACKUP_STATUS_STG_Overdue
    ON dbo.KPI_MSSQL_BACKUP_STATUS_STG (Is_Full_Backup_Overdue)
    WHERE Is_Full_Backup_Overdue = 1
    ON [FG_KPI_DATA];
GO

-- STG 2.2: KPI_MSSQL_BACKUP_FAILURES (Tabela de Falhas de Backup - Historico)
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUP_FAILURES', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BACKUP_FAILURES;
GO

CREATE TABLE dbo.KPI_MSSQL_BACKUP_FAILURES (
    failure_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    Instance VARCHAR(100) NOT NULL,
    [Database] VARCHAR(128) NOT NULL,
    Backup_Type CHAR(1) NOT NULL,  -- D = Full, I = Differential, L = Log
    Last_Backup_Date DATETIME2 NULL,  -- NULL se nunca teve backup
    Hours_Since_Backup INT NULL,  -- NULL se nunca teve backup
    Days_Since_Backup AS CAST(Hours_Since_Backup / 24.0 AS DECIMAL(10,2)) PERSISTED,
    Failure_Reason VARCHAR(200) NOT NULL,  -- Ex: "Sem backup hÃ¡ mais de 24h", "Nunca teve backup"
    Severity VARCHAR(20) NOT NULL,  -- CRITICAL, WARNING, INFO
    Recovery_Model VARCHAR(20) NULL,  -- FULL, SIMPLE, BULK_LOGGED
    Database_State VARCHAR(20) NULL,  -- ONLINE, OFFLINE, etc.
    Collection_Date DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    Resolved_Date DATETIME2 NULL,  -- NULL se ainda nÃ£o foi resolvido
    Is_Resolved AS CASE WHEN Resolved_Date IS NOT NULL THEN 1 ELSE 0 END PERSISTED,
    Resolved_After_Hours AS CASE 
        WHEN Resolved_Date IS NOT NULL 
        THEN DATEDIFF(HOUR, Collection_Date, Resolved_Date)
        ELSE NULL
    END PERSISTED,
    Additional_Info NVARCHAR(500) NULL,
    CONSTRAINT CK_Backup_Failures_Severity CHECK (Severity IN ('CRITICAL', 'WARNING', 'INFO')),
    CONSTRAINT CK_Backup_Failures_Type CHECK (Backup_Type IN ('D', 'I', 'L'))
) ON [FG_KPI_DATA];
GO

-- Ãndices para performance
-- NOTA: NÃ£o podemos usar coluna computed (Is_Resolved) no filtro, entÃ£o usamos Resolved_Date IS NULL
CREATE NONCLUSTERED INDEX IX_BACKUP_FAILURES_ACTIVE
ON dbo.KPI_MSSQL_BACKUP_FAILURES (Instance, [Database], Backup_Type, Collection_Date DESC)
INCLUDE (Hours_Since_Backup, Severity, Failure_Reason, Resolved_Date)
WHERE Resolved_Date IS NULL;
GO

CREATE NONCLUSTERED INDEX IX_BACKUP_FAILURES_INSTANCE_SEVERITY
ON dbo.KPI_MSSQL_BACKUP_FAILURES (Instance, Severity, Collection_Date DESC)
INCLUDE ([Database], Backup_Type, Hours_Since_Backup, Resolved_Date);
GO

CREATE NONCLUSTERED INDEX IX_BACKUP_FAILURES_HISTORICAL
ON dbo.KPI_MSSQL_BACKUP_FAILURES (Collection_Date DESC, Resolved_Date)
INCLUDE (Instance, [Database], Severity, Resolved_After_Hours);
GO

CREATE NONCLUSTERED INDEX IX_BACKUP_FAILURES_DATABASE
ON dbo.KPI_MSSQL_BACKUP_FAILURES ([Database], Instance, Collection_Date DESC)
INCLUDE (Backup_Type, Severity, Resolved_Date);
GO

-- View para falhas ativas (nÃ£o resolvidas)
IF OBJECT_ID('dbo.VW_BACKUP_FAILURES_ACTIVE', 'V') IS NOT NULL
    DROP VIEW dbo.VW_BACKUP_FAILURES_ACTIVE;
GO

CREATE VIEW dbo.VW_BACKUP_FAILURES_ACTIVE
AS
SELECT 
    failure_id,
    Instance,
    [Database],
    Backup_Type,
    CASE Backup_Type
        WHEN 'D' THEN 'Full'
        WHEN 'I' THEN 'Differential'
        WHEN 'L' THEN 'Log'
        ELSE 'Unknown'
    END AS Backup_Type_Description,
    Last_Backup_Date,
    Hours_Since_Backup,
    Days_Since_Backup,
    Failure_Reason,
    Severity,
    Recovery_Model,
    Database_State,
    Collection_Date,
    Additional_Info,
    DATEDIFF(HOUR, Collection_Date, GETDATE()) AS Hours_Since_Failure_Detected
FROM dbo.KPI_MSSQL_BACKUP_FAILURES WITH (NOLOCK)
WHERE Resolved_Date IS NULL  -- Apenas falhas nÃ£o resolvidas
    AND Collection_Date >= DATEADD(DAY, -30, GETDATE());
GO

-- View para resumo de falhas por instÃ¢ncia
IF OBJECT_ID('dbo.VW_BACKUP_FAILURES_SUMMARY', 'V') IS NOT NULL
    DROP VIEW dbo.VW_BACKUP_FAILURES_SUMMARY;
GO

CREATE VIEW dbo.VW_BACKUP_FAILURES_SUMMARY
AS
SELECT 
    Instance,
    COUNT(*) AS Total_Failures,
    SUM(CASE WHEN Severity = 'CRITICAL' THEN 1 ELSE 0 END) AS Critical_Failures,
    SUM(CASE WHEN Severity = 'WARNING' THEN 1 ELSE 0 END) AS Warning_Failures,
    SUM(CASE WHEN Severity = 'INFO' THEN 1 ELSE 0 END) AS Info_Failures,
    COUNT(DISTINCT [Database]) AS Databases_With_Failures,
    MAX(Hours_Since_Backup) AS Max_Hours_Since_Backup,
    MAX(Collection_Date) AS Last_Failure_Detected,
    MIN(Collection_Date) AS First_Failure_Detected
FROM dbo.KPI_MSSQL_BACKUP_FAILURES WITH (NOLOCK)
WHERE Resolved_Date IS NULL  -- Apenas falhas nÃ£o resolvidas
    AND Collection_Date >= DATEADD(DAY, -30, GETDATE())
GROUP BY Instance;
GO

-- Stored Procedure para marcar falhas como resolvidas
IF OBJECT_ID('dbo.usp_Mark_Backup_Failures_Resolved', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Mark_Backup_Failures_Resolved;
GO

CREATE PROCEDURE dbo.usp_Mark_Backup_Failures_Resolved
    @Instance VARCHAR(100) = NULL,  -- NULL = todas as instÃ¢ncias
    @Database VARCHAR(128) = NULL,  -- NULL = todos os databases
    @Backup_Type CHAR(1) = NULL,  -- NULL = todos os tipos
    @Resolved_Date DATETIME2 = NULL  -- NULL = usar GETDATE()
AS
BEGIN
    SET NOCOUNT ON;
    
    IF @Resolved_Date IS NULL
        SET @Resolved_Date = GETDATE();
    
    UPDATE dbo.KPI_MSSQL_BACKUP_FAILURES
    SET Resolved_Date = @Resolved_Date
    WHERE Resolved_Date IS NULL  -- Apenas falhas nÃ£o resolvidas
        AND (@Instance IS NULL OR Instance = @Instance)
        AND (@Database IS NULL OR [Database] = @Database)
        AND (@Backup_Type IS NULL OR Backup_Type = @Backup_Type);
    
    SELECT @@ROWCOUNT AS Failures_Resolved;
END;
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

-- STG 5: KPI_MSSQL_DB_AVAILABILITY_STG
IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    [State]             VARCHAR(32)     NULL,
    Is_Available        BIT             DEFAULT 1,
    Recovery_Model      VARCHAR(32)     NULL,
    Mirroring_Role       VARCHAR(32)     NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_DB_AVAILABILITY_STG PRIMARY KEY (Instance, [Database])
) ON [FG_KPI_DATA];
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

-- STG 12: KPI_MSSQL_DEADLOCKS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_DEADLOCKS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DEADLOCKS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_DEADLOCKS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Deadlock_Id         BIGINT          NOT NULL,
    Deadlock_Time       DATETIME2       NOT NULL,
    Victim_Session_Id   INT             NULL,
    Database_Name       VARCHAR(128)    NULL,
    Object_Name         VARCHAR(256)    NULL,
    Index_Name          VARCHAR(256)    NULL,
    Lock_Mode           VARCHAR(32)     NULL,
    Resource_Type       VARCHAR(64)     NULL,
    Process_Xml         XML             NULL,
    Deadlock_Graph      NVARCHAR(MAX)  NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_DEADLOCKS_STG PRIMARY KEY (Instance, Deadlock_Id, Deadlock_Time)
) ON [FG_KPI_DATA];
GO

CREATE INDEX IX_KPI_MSSQL_DEADLOCKS_STG_DeadlockTime ON dbo.KPI_MSSQL_DEADLOCKS_STG(Deadlock_Time);
GO

-- STG 13: KPI_MSSQL_ERRORLOG_STG
-- âš ï¸ DESCONTINUADO: KPI error_log foi removido devido a problemas de permissÃ£o com xp_readerrorlog
-- Mantido apenas para compatibilidade com instalaÃ§Ãµes antigas
-- A tabela pode ser mantida ou removida conforme necessÃ¡rio
/*
IF OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_ERRORLOG_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_ERRORLOG_STG (
    Instance            VARCHAR(128)    NOT NULL,  -- Nome da instancia (ex: SQLHDSPRD001\I0001)
    Log_Date            DATETIME2       NOT NULL,
    Process_Info        VARCHAR(128)    NULL,
    Log_Text            NVARCHAR(MAX)   NOT NULL,
    Log_Text_Hash       AS CHECKSUM(Log_Text) PERSISTED,  -- Hash para chave primaria
    Log_Type            VARCHAR(32)     NULL,      -- ERROR, WARNING, INFO, etc.
    Error_Number        INT             NULL,
    Severity            INT             NULL,
    State               INT             NULL,
    Log_File_Number     INT             NULL,      -- Qual arquivo de log (0 = atual, 1 = anterior, etc.)
    Update_TS           DATETIME2       DEFAULT SYSUTCDATETIME(),

    -- Chave primaria: Instance + Log_Date + Hash do texto
    CONSTRAINT PK_KPI_MSSQL_ERRORLOG_STG
        PRIMARY KEY CLUSTERED (Instance, Log_Date, Log_Text_Hash)
) ON [FG_KPI_DATA];
GO

-- Indices para performance
CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_STG_LogDate
    ON dbo.KPI_MSSQL_ERRORLOG_STG(Log_Date DESC)
    INCLUDE (Instance, Log_Type, Log_Text)
    ON [FG_KPI_DATA];
GO

CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_STG_ProcessInfo
    ON dbo.KPI_MSSQL_ERRORLOG_STG(Process_Info)
    INCLUDE (Instance, Log_Date)
    ON [FG_KPI_DATA];
GO

CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_STG_LogType
    ON dbo.KPI_MSSQL_ERRORLOG_STG(Log_Type, Log_Date DESC)
    INCLUDE (Instance, Log_Text)
    ON [FG_KPI_DATA];
GO

-- Indice para buscar por instancia especifica
CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_STG_Instance
    ON dbo.KPI_MSSQL_ERRORLOG_STG(Instance, Log_Date DESC)
    INCLUDE (Log_Type, Log_Text)
    ON [FG_KPI_DATA];
GO
*/
PRINT '  âš ï¸  KPI_MSSQL_ERRORLOG_STG DESCONTINUADO (comentado)';

-- STG 14: KPI_MSSQL_DB_IO_STATS_STG
IF OBJECT_ID('dbo.KPI_MSSQL_DB_IO_STATS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DB_IO_STATS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_DB_IO_STATS_STG (
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Reads               BIGINT          NOT NULL DEFAULT 0,
    Reads_Percent       DECIMAL(5,2)    NULL,
    Writes              BIGINT          NOT NULL DEFAULT 0,
    Writes_Percent      DECIMAL(5,2)    NULL,
    All_Activity        BIGINT          NOT NULL DEFAULT 0,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_DB_IO_STATS_STG PRIMARY KEY (Instance, [Database], Update_TS)
) ON [FG_KPI_DATA];
GO

CREATE INDEX IX_KPI_MSSQL_DB_IO_STATS_STG_UpdateTS ON dbo.KPI_MSSQL_DB_IO_STATS_STG(Update_TS);
CREATE INDEX IX_KPI_MSSQL_DB_IO_STATS_STG_Database ON dbo.KPI_MSSQL_DB_IO_STATS_STG([Database]);
GO

PRINT '  âœ… 14 tabelas STG criadas';
PRINT '  âœ… 1 tabela de falhas de backup criada (KPI_MSSQL_BACKUP_FAILURES)';
PRINT '  âœ… 2 views de falhas de backup criadas';
PRINT '  âœ… 1 stored procedure de falhas de backup criada';
GO

-- ============================================================================
-- TABELAS HISTÃ“RICAS (HIST) - 4 TABELAS
-- ============================================================================

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
    Mirroring_Role      VARCHAR(32)     NULL,
    Update_TS           DATETIME2       NOT NULL,
    CONSTRAINT PK_KPI_MSSQL_DB_AVAILABILITY_HIST PRIMARY KEY (Instance, [Database], Update_TS)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_KPI_MSSQL_DB_AVAILABILITY_HIST_UpdateTS ON dbo.KPI_MSSQL_DB_AVAILABILITY_HIST(Update_TS);
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

-- HIST 4: KPI_MSSQL_ERRORLOG_HIST
-- âš ï¸ DESCONTINUADO: KPI error_log foi removido devido a problemas de permissÃ£o com xp_readerrorlog
-- Mantido apenas para compatibilidade com instalaÃ§Ãµes antigas
/*
IF OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_ERRORLOG_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_ERRORLOG_HIST (
    Instance            VARCHAR(128)    NOT NULL,
    Log_Date            DATETIME2       NOT NULL,
    Process_Info        VARCHAR(128)    NULL,
    Log_Text            NVARCHAR(MAX)   NOT NULL,
    Log_Text_Hash       AS CHECKSUM(Log_Text) PERSISTED,
    Log_Type            VARCHAR(32)     NULL,
    Error_Number        INT             NULL,
    Severity            INT             NULL,
    State               INT             NULL,
    Log_File_Number     INT             NULL,
    Update_TS           DATETIME2       NOT NULL,

    -- Chave primaria: Instance + Log_Date + Hash + Update_TS
    CONSTRAINT PK_KPI_MSSQL_ERRORLOG_HIST
        PRIMARY KEY CLUSTERED (Instance, Log_Date, Log_Text_Hash, Update_TS)
) ON [FG_KPI_HIST];
GO

-- Indices para historico
CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_HIST_LogDate
    ON dbo.KPI_MSSQL_ERRORLOG_HIST(Log_Date DESC)
    INCLUDE (Instance, Log_Type)
    ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_HIST_LogType
    ON dbo.KPI_MSSQL_ERRORLOG_HIST(Log_Type, Log_Date DESC)
    ON [FG_KPI_HIST];
GO
*/
PRINT '  âš ï¸  KPI_MSSQL_ERRORLOG_HIST DESCONTINUADO (comentado)';

-- ============================================================================
-- SPRINT 2: TABELAS DE HISTÃ“RICO ADICIONAIS (PRIORIDADE ALTA)
-- ============================================================================

-- HIST 5: KPI_MSSQL_INST_AVAILABILITY_HIST (SPRINT 2)
IF OBJECT_ID('dbo.KPI_MSSQL_INST_AVAILABILITY_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_INST_AVAILABILITY_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_INST_AVAILABILITY_HIST (
    Instance_Name       VARCHAR(128)    NOT NULL,
    Collection_Time     DATETIME2       NOT NULL,
    Is_Available        BIT             NOT NULL,
    Error_Message       NVARCHAR(4000)  NULL,
    SQL_Version         VARCHAR(128)    NULL,
    SQL_Edition         VARCHAR(128)    NULL,
    Server_Name         VARCHAR(128)    NULL,
    Instance_Status     VARCHAR(32)     NULL,
    Response_Time_MS    INT             NULL,
    Last_Restart_Time   DATETIME2       NULL,
    Update_TS           DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_KPI_INST_AVAILABILITY_HIST PRIMARY KEY CLUSTERED (Instance_Name, Collection_Time)
) ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_INST_AVAILABILITY_HIST_Time
    ON dbo.KPI_MSSQL_INST_AVAILABILITY_HIST (Collection_Time DESC)
    INCLUDE (Instance_Name, Is_Available, Instance_Status)
    ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_INST_AVAILABILITY_HIST_Down
    ON dbo.KPI_MSSQL_INST_AVAILABILITY_HIST (Is_Available, Collection_Time DESC)
    WHERE Is_Available = 0
    ON [FG_KPI_HIST];
GO

-- HIST 6: KPI_MSSQL_BACKUP_STATUS_HIST (SPRINT 2)
IF OBJECT_ID('dbo.KPI_MSSQL_BACKUP_STATUS_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_BACKUP_STATUS_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_BACKUP_STATUS_HIST (
    Instance_Name               VARCHAR(128)    NOT NULL,
    Collection_Time             DATETIME2       NOT NULL,
    Database_Name               VARCHAR(128)    NOT NULL,
    Last_Full_Backup            DATETIME2       NULL,
    Last_Diff_Backup            DATETIME2       NULL,
    Last_Log_Backup             DATETIME2       NULL,
    Hours_Since_Full_Backup     INT             NULL,
    Hours_Since_Diff_Backup     INT             NULL,
    Hours_Since_Log_Backup      INT             NULL,
    Full_Backup_Status          VARCHAR(32)     NULL,
    Diff_Backup_Status          VARCHAR(32)     NULL,
    Log_Backup_Status           VARCHAR(32)     NULL,
    Recovery_Model              VARCHAR(32)     NULL,
    Database_State              VARCHAR(32)     NULL,
    Is_Full_Backup_Overdue      BIT             NOT NULL DEFAULT 0,
    Is_Log_Backup_Overdue       BIT             NOT NULL DEFAULT 0,
    Update_TS                   DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_KPI_BACKUP_STATUS_HIST PRIMARY KEY CLUSTERED (Instance_Name, Database_Name, Collection_Time)
) ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_BACKUP_STATUS_HIST_Overdue
    ON dbo.KPI_MSSQL_BACKUP_STATUS_HIST (Is_Full_Backup_Overdue, Collection_Time DESC)
    WHERE Is_Full_Backup_Overdue = 1
    ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_BACKUP_STATUS_HIST_Database
    ON dbo.KPI_MSSQL_BACKUP_STATUS_HIST (Database_Name, Collection_Time DESC)
    INCLUDE (Instance_Name, Last_Full_Backup, Full_Backup_Status)
    ON [FG_KPI_HIST];
GO

-- HIST 7: KPI_MSSQL_DEADLOCKS_HIST (SPRINT 2)
IF OBJECT_ID('dbo.KPI_MSSQL_DEADLOCKS_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_DEADLOCKS_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_DEADLOCKS_HIST (
    Instance_Name           VARCHAR(128)    NOT NULL,
    Collection_Time         DATETIME2       NOT NULL,
    Deadlock_Time           DATETIME2       NOT NULL,
    Victim_SPID             INT             NOT NULL DEFAULT 0,  -- Corrigido: NOT NULL
    Victim_Database         VARCHAR(128)    NULL,
    Victim_LoginName        VARCHAR(128)    NULL,
    Victim_HostName         VARCHAR(128)    NULL,
    Victim_ProgramName      VARCHAR(256)    NULL,
    Victim_Query            NVARCHAR(MAX)   NULL,
    Winner_SPID             INT             NULL,
    Winner_Database         VARCHAR(128)    NULL,
    Winner_LoginName        VARCHAR(128)    NULL,
    Winner_Query            NVARCHAR(MAX)   NULL,
    Deadlock_Graph          XML             NULL,
    Resource_Type           VARCHAR(64)     NULL,  -- 'KEY', 'PAGE', 'RID', etc.
    Update_TS               DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_KPI_DEADLOCKS_HIST PRIMARY KEY CLUSTERED (Instance_Name, Deadlock_Time, Victim_SPID)
) ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_DEADLOCKS_HIST_Time
    ON dbo.KPI_MSSQL_DEADLOCKS_HIST (Deadlock_Time DESC)
    INCLUDE (Instance_Name, Victim_Database, Victim_LoginName)
    ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_DEADLOCKS_HIST_Database
    ON dbo.KPI_MSSQL_DEADLOCKS_HIST (Victim_Database, Deadlock_Time DESC)
    ON [FG_KPI_HIST];
GO

CREATE NONCLUSTERED INDEX IX_DEADLOCKS_HIST_Login
    ON dbo.KPI_MSSQL_DEADLOCKS_HIST (Victim_LoginName, Deadlock_Time DESC)
    ON [FG_KPI_HIST];
GO

PRINT '  âœ… 7 tabelas HIST criadas (4 originais + 3 Sprint 2)';
GO

-- ============================================================================
-- STG 14: KPI_MSSQL_SERVICE_STATUS_STG
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_SERVICE_STATUS_STG', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_SERVICE_STATUS_STG;
GO

CREATE TABLE dbo.KPI_MSSQL_SERVICE_STATUS_STG (
    Instance              VARCHAR(255)    NOT NULL,
    Service_Name          VARCHAR(255)    NOT NULL,
    Service_Display_Name  NVARCHAR(500)   NULL,
    Service_State         VARCHAR(50)     NOT NULL,  -- Running, Stopped, Paused, StartPending, StopPending
    Service_Status        VARCHAR(50)     NOT NULL,  -- OK, DOWN, WARNING
    Start_Mode           VARCHAR(50)     NULL,       -- Automatic, Manual, Disabled
    Start_Time           DATETIME2        NULL,       -- Quando o serviÃ§o foi iniciado
    Stop_Time            DATETIME2        NULL,       -- Quando o serviÃ§o foi parado
    Last_Error_Code      INT              NULL,       -- CÃ³digo do Ãºltimo erro
    Last_Error_Message   NVARCHAR(MAX)    NULL,       -- Mensagem do Ãºltimo erro
    Event_Log_Entry      NVARCHAR(MAX)   NULL,       -- Entrada do Event Log relacionada
    Event_Log_Time       DATETIME2        NULL,       -- Data/hora do evento no log
    Detection_Method     VARCHAR(50)      NOT NULL,   -- 'ServiceCheck', 'ConnectionFailure', 'EventLog'
    Connection_Error     NVARCHAR(MAX)    NULL,       -- Erro de conexÃ£o que levou Ã  detecÃ§Ã£o
    Resolved             BIT              DEFAULT 0,  -- Se o problema foi resolvido
    Resolved_Time        DATETIME2        NULL,       -- Quando foi resolvido
    Update_TS            DATETIME2        DEFAULT GETDATE(),
    CONSTRAINT PK_KPI_MSSQL_SERVICE_STATUS_STG PRIMARY KEY (Instance, Service_Name, Update_TS)
) ON [FG_KPI_DATA];
GO

CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_STG_Instance ON dbo.KPI_MSSQL_SERVICE_STATUS_STG(Instance);
CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_STG_ServiceState ON dbo.KPI_MSSQL_SERVICE_STATUS_STG(Service_State);
CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_STG_ServiceStatus ON dbo.KPI_MSSQL_SERVICE_STATUS_STG(Service_Status);
CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_STG_Resolved ON dbo.KPI_MSSQL_SERVICE_STATUS_STG(Resolved);
CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_STG_UpdateTS ON dbo.KPI_MSSQL_SERVICE_STATUS_STG(Update_TS);
GO

-- ============================================================================
-- HIST 5: KPI_MSSQL_SERVICE_STATUS_HIST
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_SERVICE_STATUS_HIST', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_SERVICE_STATUS_HIST;
GO

CREATE TABLE dbo.KPI_MSSQL_SERVICE_STATUS_HIST (
    Instance              VARCHAR(255)    NOT NULL,
    Service_Name          VARCHAR(255)    NOT NULL,
    Service_Display_Name  NVARCHAR(500)   NULL,
    Service_State         VARCHAR(50)     NOT NULL,
    Service_Status        VARCHAR(50)     NOT NULL,
    Start_Mode           VARCHAR(50)     NULL,
    Start_Time           DATETIME2        NULL,
    Stop_Time            DATETIME2        NULL,
    Last_Error_Code      INT              NULL,
    Last_Error_Message   NVARCHAR(MAX)    NULL,
    Event_Log_Entry      NVARCHAR(MAX)   NULL,
    Event_Log_Time       DATETIME2        NULL,
    Detection_Method     VARCHAR(50)      NOT NULL,
    Connection_Error     NVARCHAR(MAX)    NULL,
    Resolved             BIT              DEFAULT 0,
    Resolved_Time        DATETIME2        NULL,
    Update_TS            DATETIME2        NOT NULL,
    CONSTRAINT PK_KPI_MSSQL_SERVICE_STATUS_HIST PRIMARY KEY (Instance, Service_Name, Update_TS)
) ON [FG_KPI_HIST];
GO

CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_HIST_Instance ON dbo.KPI_MSSQL_SERVICE_STATUS_HIST(Instance);
CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_HIST_ServiceState ON dbo.KPI_MSSQL_SERVICE_STATUS_HIST(Service_State);
CREATE INDEX IX_KPI_MSSQL_SERVICE_STATUS_HIST_UpdateTS ON dbo.KPI_MSSQL_SERVICE_STATUS_HIST(Update_TS);
GO

PRINT '  âœ… Tabela KPI_MSSQL_SERVICE_STATUS_STG criada';
PRINT '  âœ… Tabela KPI_MSSQL_SERVICE_STATUS_HIST criada';
GO

-- ============================================================================
-- TABELA AUXILIAR - KPI_MSSQL_INST_ENVS
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_INST_ENVS', 'U') IS NOT NULL
    DROP TABLE dbo.KPI_MSSQL_INST_ENVS;
GO

CREATE TABLE dbo.KPI_MSSQL_INST_ENVS (
    Instance        VARCHAR(64)     NOT NULL PRIMARY KEY,
    Env             VARCHAR(32)     NOT NULL,
    Description     VARCHAR(500)    NULL
);
GO

PRINT '  âœ… 1 tabela auxiliar criada';
PRINT '  âœ… Total: 22 tabelas KPI criadas (2 Thresholds + 2 CMDB + 14 STG + 1 Backup Failures + 4 HIST + 1 Aux)!';
GO

-- =============================================
-- STEP 8: INSERT PATTERNS
-- =============================================
PRINT '';
PRINT '[8/13] Inserindo patterns...';

SET IDENTITY_INSERT [meta].[patterns] ON;

INSERT INTO [meta].[patterns] (pattern_id, pattern_name, pattern_category, [description], severity, confidence_threshold, detection_frequency_minutes, is_active)
VALUES
(1, 'sustained_high_cpu', 'performance', 'CPU > 85% por 15+ minutos', 'warning', 0.9, 5, 1),
(2, 'ple_decay_trend', 'performance', 'PLE declinando ao longo de 7 dias', 'warning', 0.8, 60, 1),
(3, 'io_degradation', 'performance', 'LatÃªncia I/O aumentando gradualmente', 'warning', 0.8, 15, 1),
(4, 'unexpected_shutdown', 'availability', 'Windows Event 6008 - perda de energia', 'critical', 0.95, 5, 1),
(5, 'reboot_chain', 'availability', 'Reboot seguido de crash', 'critical', 0.85, 15, 1),
(6, 'brute_force_login', 'security', 'MÃºltiplos logins falhados + sucesso', 'critical', 0.9, 1, 1),
(7, 'disk_saturation_forecast', 'capacity', 'Disco cheio em < 30 dias', 'error', 0.8, 1440, 1),
(8, 'backup_failure_cluster', 'maintenance', 'MÃºltiplas falhas de backup', 'error', 0.85, 30, 1),
(9, 'patch_drift', 'configuration', 'Servidores nÃ£o atualizados', 'warning', 0.85, 10080, 1),
(10, 'server_personality_change', 'configuration', 'PadrÃ£o comportamental mudou', 'warning', 0.85, 1440, 1),
(11, 'contextual_anomaly_unexpected', 'performance', 'Anomalia sem contexto conhecido', 'error', 0.90, 5, 1),
(12, 'contextual_anomaly_expected', 'performance', 'Anomalia esperada (manutenÃ§Ã£o)', 'info', 0.75, 5, 1);

SET IDENTITY_INSERT [meta].[patterns] OFF;

PRINT '  âœ… 12 patterns inseridos!';
GO

-- =============================================
-- STEP 8.5: BLUE-GREEN DEPLOYMENT PARA TABELAS KPI
-- =============================================
-- Tabela de controle para swap atÃ´mico sem downtime
-- IMPORTANTE: NecessÃ¡rio para que a coleta Python funcione corretamente
-- =============================================
PRINT '';
PRINT '[8.5/13] Configurando Blue-Green Deployment para KPIs...';
GO

-- Tabela de controle Blue-Green
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_STG_ACTIVE_TABLE')
BEGIN
    CREATE TABLE dbo.KPI_STG_ACTIVE_TABLE (
        Table_Name NVARCHAR(100) PRIMARY KEY,
        Active_Slot NVARCHAR(10) NOT NULL CHECK (Active_Slot IN ('BLUE', 'GREEN')),
        Last_Swap_Time DATETIME2 DEFAULT GETDATE(),
        Collection_Start_Time DATETIME2 NULL,
        Collection_End_Time DATETIME2 NULL,
        Servers_Collected INT DEFAULT 0,
        Created_Date DATETIME2 DEFAULT GETDATE()
    );
    PRINT '  âœ… Tabela KPI_STG_ACTIVE_TABLE criada';
END
ELSE
    PRINT '  â„¹ï¸ Tabela KPI_STG_ACTIVE_TABLE ja existe';
GO

-- FunÃ§Ã£o helper para obter tabela de coleta (retorna tabela INATIVA)
IF EXISTS (SELECT 1 FROM sys.objects WHERE name = 'fn_get_kpi_collection_target' AND type = 'FN')
    DROP FUNCTION dbo.fn_get_kpi_collection_target;
GO

CREATE FUNCTION dbo.fn_get_kpi_collection_target(@table_name NVARCHAR(100))
RETURNS NVARCHAR(200)
AS
BEGIN
    DECLARE @active_slot NVARCHAR(10);
    DECLARE @target_table NVARCHAR(200);

    SELECT @active_slot = Active_Slot
    FROM dbo.KPI_STG_ACTIVE_TABLE
    WHERE Table_Name = @table_name;

    -- Retorna tabela INATIVA (onde coletar novos dados)
    SET @target_table = @table_name + '_' + CASE
        WHEN @active_slot = 'BLUE' THEN 'GREEN'
        WHEN @active_slot = 'GREEN' THEN 'BLUE'
        ELSE 'BLUE'
    END;

    RETURN @target_table;
END
GO
PRINT '  âœ… FunÃ§Ã£o fn_get_kpi_collection_target criada';
GO

-- Stored Procedure de SWAP atÃ´mico
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_swap_kpi_stg_tables')
    DROP PROCEDURE dbo.usp_swap_kpi_stg_tables;
GO

CREATE PROCEDURE dbo.usp_swap_kpi_stg_tables
    @table_name NVARCHAR(100),
    @servers_collected INT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @current_active NVARCHAR(10);
    DECLARE @new_active NVARCHAR(10);

    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT @current_active = Active_Slot
        FROM dbo.KPI_STG_ACTIVE_TABLE WITH (UPDLOCK)
        WHERE Table_Name = @table_name;

        IF @current_active IS NULL
        BEGIN
            ROLLBACK TRANSACTION;
            RAISERROR('Tabela %s nÃ£o encontrada em KPI_STG_ACTIVE_TABLE', 16, 1, @table_name);
            RETURN;
        END

        SET @new_active = CASE WHEN @current_active = 'BLUE' THEN 'GREEN' ELSE 'BLUE' END;

        UPDATE dbo.KPI_STG_ACTIVE_TABLE
        SET Active_Slot = @new_active,
            Last_Swap_Time = GETDATE(),
            Collection_End_Time = GETDATE(),
            Servers_Collected = @servers_collected
        WHERE Table_Name = @table_name;

        COMMIT TRANSACTION;

        -- Retornar resultado do SWAP
        SELECT @table_name AS Table_Name,
               @current_active AS Old_Active,
               @new_active AS New_Active,
               @servers_collected AS Servers_Collected,
               GETDATE() AS Swap_Time;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMessage, 16, 1);
    END CATCH
END
GO
PRINT '  âœ… Procedure usp_swap_kpi_stg_tables criada';
GO

-- Registrar TODAS as tabelas KPI no controle Blue-Green
-- IMPORTANTE: Inclui AlwaysOn e Processes que estavam faltando
DECLARE @tables_to_register TABLE (table_name NVARCHAR(100));
INSERT INTO @tables_to_register VALUES
    ('KPI_MSSQL_ALWAYSON_STATUS_STG'),
    ('KPI_MSSQL_BACKUPS_STG'),
    ('KPI_MSSQL_BACKUP_STATUS_STG'),
    ('KPI_MSSQL_BLOCKED_SESSIONS_STG'),
    ('KPI_MSSQL_BLOCKED_USERS_STG'),
    ('KPI_MSSQL_DB_AVAILABILITY_STG'),
    ('KPI_MSSQL_DB_IO_STATS_STG'),
    ('KPI_MSSQL_DISK_USAGE_STG'),
    ('KPI_MSSQL_ERRORLOG_STG'),
    ('KPI_MSSQL_FG_USAGE_STG'),
    ('KPI_MSSQL_INST_AVAILABILITY_STG'),
    ('KPI_MSSQL_LONG_LOCKS_STG'),
    ('KPI_MSSQL_PROCESSES_STG'),
    ('KPI_MSSQL_SERVICE_STATUS_STG'),
    ('KPI_MSSQL_TLOG_USAGE_STG');

INSERT INTO dbo.KPI_STG_ACTIVE_TABLE (Table_Name, Active_Slot, Last_Swap_Time, Created_Date)
SELECT t.table_name, 'BLUE', GETDATE(), GETDATE()
FROM @tables_to_register t
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.KPI_STG_ACTIVE_TABLE WHERE Table_Name = t.table_name
);

PRINT '  âœ… Tabelas KPI registradas no controle Blue-Green';
GO

-- Criar tabelas Blue-Green base para todas as tabelas KPI
-- Estas tabelas sao necessarias para o setup de ambientes funcionar
PRINT '  Criando tabelas Blue-Green base...';

DECLARE @kpi_tables TABLE (table_name NVARCHAR(100));
INSERT INTO @kpi_tables VALUES
    ('KPI_MSSQL_BACKUPS_STG'),
    ('KPI_MSSQL_BACKUP_STATUS_STG'),
    ('KPI_MSSQL_BLOCKED_SESSIONS_STG'),
    ('KPI_MSSQL_BLOCKED_USERS_STG'),
    ('KPI_MSSQL_DB_AVAILABILITY_STG'),
    ('KPI_MSSQL_DB_IO_STATS_STG'),
    ('KPI_MSSQL_DISK_USAGE_STG'),
    ('KPI_MSSQL_ERRORLOG_STG'),
    ('KPI_MSSQL_FG_USAGE_STG'),
    ('KPI_MSSQL_INST_AVAILABILITY_STG'),
    ('KPI_MSSQL_LONG_LOCKS_STG'),
    ('KPI_MSSQL_PROCESSES_STG'),
    ('KPI_MSSQL_SERVICE_STATUS_STG'),
    ('KPI_MSSQL_TLOG_USAGE_STG');

DECLARE @tbl NVARCHAR(100);
DECLARE @sql NVARCHAR(MAX);

DECLARE tbl_cursor CURSOR FOR SELECT table_name FROM @kpi_tables;
OPEN tbl_cursor;
FETCH NEXT FROM tbl_cursor INTO @tbl;

WHILE @@FETCH_STATUS = 0
BEGIN
    -- Criar tabela BLUE se nao existir
    IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @tbl)
       AND NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @tbl + '_BLUE')
    BEGIN
        SET @sql = 'SELECT TOP 0 * INTO dbo.' + @tbl + '_BLUE FROM dbo.' + @tbl;
        EXEC sp_executesql @sql;
    END

    -- Criar tabela GREEN se nao existir
    IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @tbl)
       AND NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @tbl + '_GREEN')
    BEGIN
        SET @sql = 'SELECT TOP 0 * INTO dbo.' + @tbl + '_GREEN FROM dbo.' + @tbl;
        EXEC sp_executesql @sql;
    END

    FETCH NEXT FROM tbl_cursor INTO @tbl;
END

CLOSE tbl_cursor;
DEALLOCATE tbl_cursor;
GO

-- Criar tabelas Blue-Green para ALWAYSON (tem coluna computed, precisa ser criada explicitamente)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_ALWAYSON_STATUS_STG_BLUE')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG_BLUE (
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
        Problem_Reason AS (
            CASE
                WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
                      OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
                      OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                     AND (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1) THEN 'Health Problem + Suspended'
                WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
                      OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
                      OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                     AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'Health Problem + Sync State'
                WHEN (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
                     AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'Suspended + Sync State'
                WHEN Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL THEN 'No Health Data (Both Replicas)'
                WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY'
                     AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY' THEN 'Both Replicas Unhealthy'
                WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY' THEN 'Primary Replica Unhealthy (' + Pri_Synch_Health + ')'
                WHEN Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY' THEN 'Secondary Replica Unhealthy (' + Sec_Synch_Health + ')'
                WHEN Pri_Is_Suspended = 1 AND Sec_Is_Suspended = 1 THEN 'Both Replicas Suspended'
                WHEN Pri_Is_Suspended = 1 THEN 'Primary Replica Suspended'
                WHEN Sec_Is_Suspended = 1 THEN 'Secondary Replica Suspended'
                WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     THEN 'Both Replicas Sync State Problem (' + Pri_Synch_State + ' / ' + Sec_Synch_State + ')'
                WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     THEN 'Primary Sync State Problem (' + Pri_Synch_State + ')'
                WHEN Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     THEN 'Secondary Sync State Problem (' + Sec_Synch_State + ')'
                ELSE NULL
            END
        ) PERSISTED,
        CONSTRAINT PK_KPI_MSSQL_ALWAYSON_STATUS_STG_BLUE PRIMARY KEY (AgName, Instance, [Database])
    );
    PRINT '    [OK] KPI_MSSQL_ALWAYSON_STATUS_STG_BLUE';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_ALWAYSON_STATUS_STG_GREEN')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG_GREEN (
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
        Problem_Reason AS (
            CASE
                WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
                      OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
                      OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                     AND (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1) THEN 'Health Problem + Suspended'
                WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
                      OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
                      OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                     AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'Health Problem + Sync State'
                WHEN (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
                     AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'Suspended + Sync State'
                WHEN Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL THEN 'No Health Data (Both Replicas)'
                WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY'
                     AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY' THEN 'Both Replicas Unhealthy'
                WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY' THEN 'Primary Replica Unhealthy (' + Pri_Synch_Health + ')'
                WHEN Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY' THEN 'Secondary Replica Unhealthy (' + Sec_Synch_Health + ')'
                WHEN Pri_Is_Suspended = 1 AND Sec_Is_Suspended = 1 THEN 'Both Replicas Suspended'
                WHEN Pri_Is_Suspended = 1 THEN 'Primary Replica Suspended'
                WHEN Sec_Is_Suspended = 1 THEN 'Secondary Replica Suspended'
                WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     THEN 'Both Replicas Sync State Problem (' + Pri_Synch_State + ' / ' + Sec_Synch_State + ')'
                WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     THEN 'Primary Sync State Problem (' + Pri_Synch_State + ')'
                WHEN Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')
                     THEN 'Secondary Sync State Problem (' + Sec_Synch_State + ')'
                ELSE NULL
            END
        ) PERSISTED,
        CONSTRAINT PK_KPI_MSSQL_ALWAYSON_STATUS_STG_GREEN PRIMARY KEY (AgName, Instance, [Database])
    );
    PRINT '    [OK] KPI_MSSQL_ALWAYSON_STATUS_STG_GREEN';
END
GO

PRINT '  âœ… Tabelas Blue-Green base criadas';
GO

-- =============================================
-- STEP 8.6: TABELAS POR AMBIENTE (PRD, QA, TST)
-- =============================================
-- Permite coleta paralela sem contenÃ§Ã£o de locks
-- Cada ambiente insere em tabelas separadas
-- VIEWs fazem UNION ALL automaticamente
-- =============================================
PRINT '';
PRINT '[8.6/18] Configurando Tabelas por Ambiente (Zero Lock Contention)...';
GO

-- =============================================
-- PARTE 1: PROCEDURE PARA SETUP DE UMA TABELA
-- =============================================
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_setup_environment_tables')
    DROP PROCEDURE dbo.usp_setup_environment_tables;
GO

CREATE PROCEDURE dbo.usp_setup_environment_tables
    @base_table_name NVARCHAR(100),
    @verbose BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @sql NVARCHAR(MAX);
    DECLARE @blue_table NVARCHAR(200) = @base_table_name + '_BLUE';
    DECLARE @green_table NVARCHAR(200) = @base_table_name + '_GREEN';
    DECLARE @env VARCHAR(3);
    DECLARE @slot VARCHAR(5);
    DECLARE @source_table NVARCHAR(200);
    DECLARE @target_table NVARCHAR(200);
    DECLARE @msg NVARCHAR(500);

    -- Verificar se tabela BLUE existe
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @blue_table)
    BEGIN
        SET @msg = '    [SKIP] Tabela ' + @blue_table + ' nao existe';
        IF @verbose = 1 PRINT @msg;
        RETURN;
    END

    -- Loop para cada ambiente (PRD, QA, TST)
    DECLARE @envs TABLE (Env VARCHAR(3));
    INSERT INTO @envs VALUES ('PRD'), ('QA'), ('TST');

    -- Loop para cada slot (BLUE, GREEN)
    DECLARE @slots TABLE (Slot VARCHAR(5));
    INSERT INTO @slots VALUES ('BLUE'), ('GREEN');

    DECLARE slot_cursor CURSOR FOR SELECT Slot FROM @slots;
    OPEN slot_cursor;
    FETCH NEXT FROM slot_cursor INTO @slot;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @source_table = @base_table_name + '_' + @slot;

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @source_table)
        BEGIN
            DECLARE env_cursor CURSOR FOR SELECT Env FROM @envs;
            OPEN env_cursor;
            FETCH NEXT FROM env_cursor INTO @env;

            WHILE @@FETCH_STATUS = 0
            BEGIN
                SET @target_table = @source_table + '_' + @env;

                IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @target_table)
                BEGIN
                    SET @sql = 'SELECT * INTO dbo.' + @target_table + ' FROM dbo.' + @source_table + ' WHERE 1=0';
                    EXEC sp_executesql @sql;

                    SET @msg = '    [OK] Criada tabela: ' + @target_table;
                    IF @verbose = 1 PRINT @msg;

                    BEGIN TRY
                        SET @sql = 'CREATE INDEX IX_' + @target_table + '_Instance ON dbo.' + @target_table + '(Instance)';
                        EXEC sp_executesql @sql;
                    END TRY
                    BEGIN CATCH END CATCH

                    BEGIN TRY
                        SET @sql = 'CREATE INDEX IX_' + @target_table + '_UpdateTS ON dbo.' + @target_table + '(Update_TS)';
                        EXEC sp_executesql @sql;
                    END TRY
                    BEGIN CATCH END CATCH
                END
                ELSE
                BEGIN
                    SET @msg = '    [INFO] Tabela ja existe: ' + @target_table;
                    IF @verbose = 1 PRINT @msg;
                END

                FETCH NEXT FROM env_cursor INTO @env;
            END

            CLOSE env_cursor;
            DEALLOCATE env_cursor;
        END

        FETCH NEXT FROM slot_cursor INTO @slot;
    END

    CLOSE slot_cursor;
    DEALLOCATE slot_cursor;

    SET @msg = '    [DONE] Setup de ambientes para ' + @base_table_name;
    IF @verbose = 1 PRINT @msg;
END
GO

PRINT '  âœ… Procedure usp_setup_environment_tables criada';
GO

-- =============================================
-- PARTE 2: FUNCAO PARA OBTER TABELA POR AMBIENTE
-- =============================================
IF EXISTS (SELECT 1 FROM sys.objects WHERE name = 'fn_get_kpi_collection_target_env' AND type = 'FN')
    DROP FUNCTION dbo.fn_get_kpi_collection_target_env;
GO

CREATE FUNCTION dbo.fn_get_kpi_collection_target_env(
    @table_name NVARCHAR(100),
    @environment VARCHAR(3)  -- 'PRD', 'QA', 'TST'
)
RETURNS NVARCHAR(200)
AS
BEGIN
    DECLARE @active_slot NVARCHAR(10);
    DECLARE @target_table NVARCHAR(200);

    SELECT @active_slot = Active_Slot
    FROM dbo.KPI_STG_ACTIVE_TABLE
    WHERE Table_Name = @table_name;

    -- Retorna tabela INATIVA do ambiente especificado
    SET @target_table = @table_name + '_' + CASE
        WHEN @active_slot = 'BLUE' THEN 'GREEN'
        WHEN @active_slot = 'GREEN' THEN 'BLUE'
        ELSE 'BLUE'
    END + '_' + @environment;

    RETURN @target_table;
END
GO

PRINT '  âœ… Funcao fn_get_kpi_collection_target_env criada';
GO

-- =============================================
-- PARTE 3: PROCEDURE PARA TRUNCATE POR AMBIENTE
-- =============================================
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_truncate_stg_tables_env')
    DROP PROCEDURE dbo.usp_truncate_stg_tables_env;
GO

CREATE PROCEDURE dbo.usp_truncate_stg_tables_env
    @environment VARCHAR(3),  -- 'PRD', 'QA', 'TST'
    @kpi_list NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @truncated_count INT = 0;
    DECLARE @failed_tables NVARCHAR(MAX) = '';
    DECLARE @table_name NVARCHAR(200);
    DECLARE @target_table NVARCHAR(200);
    DECLARE @sql NVARCHAR(MAX);

    DECLARE @tables TABLE (Table_Name NVARCHAR(100));

    INSERT INTO @tables (Table_Name) VALUES
        ('KPI_MSSQL_FG_USAGE_STG'),
        ('KPI_MSSQL_BACKUPS_STG'),
        ('KPI_MSSQL_BACKUP_STATUS_STG'),
        ('KPI_MSSQL_BLOCKED_SESSIONS_STG'),
        ('KPI_MSSQL_BLOCKED_USERS_STG'),
        ('KPI_MSSQL_DB_AVAILABILITY_STG'),
        ('KPI_MSSQL_DB_IO_STATS_STG'),
        ('KPI_MSSQL_DISK_USAGE_STG'),
        ('KPI_MSSQL_ERRORLOG_STG'),
        ('KPI_MSSQL_LONG_LOCKS_STG'),
        ('KPI_MSSQL_SERVICE_STATUS_STG'),
        ('KPI_MSSQL_TLOG_USAGE_STG'),
        ('KPI_MSSQL_INST_AVAILABILITY_STG'),
        ('KPI_MSSQL_ALWAYSON_STATUS_STG'),
        ('KPI_MSSQL_PROCESSES_STG');

    DECLARE table_cursor CURSOR FOR
        SELECT Table_Name FROM @tables WHERE Table_Name IS NOT NULL;

    OPEN table_cursor;
    FETCH NEXT FROM table_cursor INTO @table_name;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @target_table = dbo.fn_get_kpi_collection_target_env(@table_name, @environment);

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @target_table)
        BEGIN
            BEGIN TRY
                SET @sql = 'TRUNCATE TABLE dbo.' + @target_table;
                EXEC sp_executesql @sql;
                SET @truncated_count = @truncated_count + 1;
            END TRY
            BEGIN CATCH
                BEGIN TRY
                    SET @sql = 'DELETE FROM dbo.' + @target_table;
                    EXEC sp_executesql @sql;
                    SET @truncated_count = @truncated_count + 1;
                END TRY
                BEGIN CATCH
                    IF LEN(@failed_tables) > 0 SET @failed_tables = @failed_tables + ',';
                    SET @failed_tables = @failed_tables + @target_table;
                END CATCH
            END CATCH
        END

        FETCH NEXT FROM table_cursor INTO @table_name;
    END

    CLOSE table_cursor;
    DEALLOCATE table_cursor;

    SELECT
        @truncated_count AS Truncated_Count,
        CASE WHEN LEN(@failed_tables) > 0 THEN @failed_tables ELSE NULL END AS Failed_Tables,
        @environment AS Environment;
END
GO

PRINT '  âœ… Procedure usp_truncate_stg_tables_env criada';
GO

-- =============================================
-- PARTE 4: CRIAR TABELAS POR AMBIENTE PARA CADA KPI
-- =============================================
PRINT '  Criando tabelas por ambiente...';

EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_FG_USAGE_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BACKUPS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BACKUP_STATUS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BLOCKED_SESSIONS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BLOCKED_USERS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_DB_AVAILABILITY_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_DB_IO_STATS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_DISK_USAGE_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_ERRORLOG_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_LONG_LOCKS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_SERVICE_STATUS_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_TLOG_USAGE_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_INST_AVAILABILITY_STG', @verbose = 0;
EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_PROCESSES_STG', @verbose = 0;
-- NOTA: KPI_MSSQL_ALWAYSON_STATUS_STG tem coluna computed PERSISTED, criada separadamente abaixo
GO

-- =============================================
-- PARTE 4.1: CRIAR TABELAS ALWAYSON POR AMBIENTE
-- =============================================
-- A tabela KPI_MSSQL_ALWAYSON_STATUS_STG tem coluna computed PERSISTED
-- que nao pode ser copiada via SELECT INTO, entao criamos explicitamente
PRINT '  Criando tabelas ALWAYSON por ambiente (com coluna computed)...';

DECLARE @slots TABLE (Slot VARCHAR(5));
INSERT INTO @slots VALUES ('BLUE'), ('GREEN');

DECLARE @envs TABLE (Env VARCHAR(3));
INSERT INTO @envs VALUES ('PRD'), ('QA'), ('TST');

DECLARE @slot VARCHAR(5);
DECLARE @env VARCHAR(3);
DECLARE @table_name NVARCHAR(200);
DECLARE @sql NVARCHAR(MAX);

DECLARE slot_cursor CURSOR FOR SELECT Slot FROM @slots;
OPEN slot_cursor;
FETCH NEXT FROM slot_cursor INTO @slot;

WHILE @@FETCH_STATUS = 0
BEGIN
    DECLARE env_cursor CURSOR FOR SELECT Env FROM @envs;
    OPEN env_cursor;
    FETCH NEXT FROM env_cursor INTO @env;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @table_name = 'KPI_MSSQL_ALWAYSON_STATUS_STG_' + @slot + '_' + @env;

        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @table_name)
        BEGIN
            SET @sql = '
CREATE TABLE dbo.' + @table_name + ' (
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
    Problem_Reason AS (
        CASE
            WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY'')
                  OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'')
                  OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                 AND (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1) THEN ''Health Problem + Suspended''
            WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY'')
                  OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'')
                  OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                 AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')) THEN ''Health Problem + Sync State''
            WHEN (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
                 AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')) THEN ''Suspended + Sync State''
            WHEN Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL THEN ''No Health Data (Both Replicas)''
            WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY''
                 AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'' THEN ''Both Replicas Unhealthy''
            WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY'' THEN ''Primary Replica Unhealthy ('' + Pri_Synch_Health + '')''
            WHEN Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'' THEN ''Secondary Replica Unhealthy ('' + Sec_Synch_Health + '')''
            WHEN Pri_Is_Suspended = 1 AND Sec_Is_Suspended = 1 THEN ''Both Replicas Suspended''
            WHEN Pri_Is_Suspended = 1 THEN ''Primary Replica Suspended''
            WHEN Sec_Is_Suspended = 1 THEN ''Secondary Replica Suspended''
            WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')
                 AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')
                 THEN ''Both Replicas Sync State Problem ('' + Pri_Synch_State + '' / '' + Sec_Synch_State + '')''
            WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')
                 THEN ''Primary Sync State Problem ('' + Pri_Synch_State + '')''
            WHEN Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')
                 THEN ''Secondary Sync State Problem ('' + Sec_Synch_State + '')''
            ELSE NULL
        END
    ) PERSISTED,
    CONSTRAINT PK_' + @table_name + ' PRIMARY KEY (AgName, Instance, [Database])
)';
            BEGIN TRY
                EXEC sp_executesql @sql;
                PRINT '    [OK] ' + @table_name;
            END TRY
            BEGIN CATCH
                PRINT '    [ERRO] ' + @table_name + ': ' + ERROR_MESSAGE();
            END CATCH

            -- Criar indices
            BEGIN TRY
                SET @sql = 'CREATE INDEX IX_' + @table_name + '_Instance ON dbo.' + @table_name + '(Instance)';
                EXEC sp_executesql @sql;
            END TRY
            BEGIN CATCH END CATCH

            BEGIN TRY
                SET @sql = 'CREATE INDEX IX_' + @table_name + '_UpdateTS ON dbo.' + @table_name + '(Update_TS)';
                EXEC sp_executesql @sql;
            END TRY
            BEGIN CATCH END CATCH
        END

        FETCH NEXT FROM env_cursor INTO @env;
    END

    CLOSE env_cursor;
    DEALLOCATE env_cursor;

    FETCH NEXT FROM slot_cursor INTO @slot;
END

CLOSE slot_cursor;
DEALLOCATE slot_cursor;
GO

-- Verificar quantas tabelas foram criadas
DECLARE @blue_prd INT, @blue_qa INT, @blue_tst INT;
DECLARE @green_prd INT, @green_qa INT, @green_tst INT;

SELECT @blue_prd = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_BLUE_PRD';
SELECT @blue_qa = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_BLUE_QA';
SELECT @blue_tst = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_BLUE_TST';
SELECT @green_prd = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_GREEN_PRD';
SELECT @green_qa = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_GREEN_QA';
SELECT @green_tst = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_GREEN_TST';

PRINT '  Tabelas criadas por ambiente:';
PRINT '    BLUE:  PRD=' + CAST(@blue_prd AS VARCHAR) + ', QA=' + CAST(@blue_qa AS VARCHAR) + ', TST=' + CAST(@blue_tst AS VARCHAR);
PRINT '    GREEN: PRD=' + CAST(@green_prd AS VARCHAR) + ', QA=' + CAST(@green_qa AS VARCHAR) + ', TST=' + CAST(@green_tst AS VARCHAR);
PRINT '  Total: ' + CAST(@blue_prd + @blue_qa + @blue_tst + @green_prd + @green_qa + @green_tst AS VARCHAR) + ' tabelas de ambiente';
GO

PRINT '  âœ… Tabelas por ambiente configuradas com sucesso!';
PRINT '';
GO

-- =============================================
-- STEP 9: CREATE VIEWS
-- =============================================
PRINT '';
PRINT '[9/13] Criando views...';
GO

CREATE VIEW [curated].[v_active_insights] AS
SELECT
    i.insight_id,
    i.instance_id,
    p.pattern_name,
    i.summary,
    i.severity,
    i.confidence_score,
    i.first_detected,
    i.occurrence_count
FROM [curated].[insights] i
INNER JOIN [meta].[patterns] p ON i.pattern_id = p.pattern_id
WHERE i.is_resolved = 0;
GO

CREATE VIEW [curated].[v_top_business_impact] AS
SELECT TOP 100
    entity_type,
    entity_id,
    incident_start,
    incident_end,
    duration_minutes,
    total_business_impact_usd,
    impact_per_minute_usd,
    priority_score,
    revenue_lost_usd,
    transactions_lost,
    users_affected
FROM [curated].[business_impact_events]
WHERE is_resolved = 0
ORDER BY total_business_impact_usd DESC;
GO

CREATE VIEW [curated].[v_high_risk_predictions] AS
SELECT
    instance_id,
    predicted_failure_type,
    probability_30d,
    safe_window_days,
    recommended_action,
    urgency_level,
    prediction_date
FROM [curated].[failure_predictions]
WHERE probability_30d >= 0.5
  AND prediction_date >= DATEADD(DAY, -30, SYSUTCDATETIME());
GO

PRINT '  âœ… 3 views V1 criadas!';
GO

-- =============================================
-- STEP 9.5: CREATE KPI VIEWS (23 VIEWS)
-- =============================================
PRINT '';
PRINT '[9.5/18] Criando views KPI (34 views)...';
GO

-- ============================================================================
-- VIEWS ALWAYS ON STATUS (AGG + DET)
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
AS
SELECT
    t.AgName,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(f.N, 0) AS Unhealthy,
    t.N AS Total,
    ISNULL(pr.Problem_Reasons, '') AS Problem_Reasons
FROM
    (SELECT AgName, COUNT(1) AS N
     FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
     GROUP BY AgName) t
    LEFT OUTER JOIN
    (SELECT 
        stg.AgName,
        MAX(env.Env) AS Env
     FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) stg
     LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS env ON env.Instance = stg.Instance
     GROUP BY stg.AgName
    ) e ON e.AgName = t.AgName
    LEFT OUTER JOIN
    (SELECT 
        AgName, 
        COUNT(1) AS N
     FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
     WHERE 
         -- Problemas de Health:
         -- Se Pri_Synch_Health tem valor mas nÃ£o Ã© HEALTHY â†’ problema
         -- Se Sec_Synch_Health tem valor mas nÃ£o Ã© HEALTHY â†’ problema
         -- Se ambos sÃ£o NULL â†’ problema (dados nÃ£o coletados)
         -- Se apenas um Ã© NULL â†’ OK (instÃ¢ncia Ã© PRIMARY ou SECONDARY, nÃ£o ambos)
         (Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
         OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
         OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL)
         -- OU rÃ©plicas suspensas
         OR (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
         -- OU estados de sincronizaÃ§Ã£o problemÃ¡ticos (apenas se nÃ£o for NULL)
         OR (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'))
         OR (Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'))
     GROUP BY AgName
    ) f ON f.AgName = t.AgName
    LEFT OUTER JOIN
    (SELECT
        AgName,
        STRING_AGG(Problem_Reason, '; ') WITHIN GROUP (ORDER BY Problem_Reason) AS Problem_Reasons
     FROM (
         SELECT DISTINCT AgName, Problem_Reason
         FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
         WHERE Problem_Reason IS NOT NULL
     ) sub
     GROUP BY AgName
    ) pr ON pr.AgName = t.AgName;
GO

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
    s.Update_TS,
    s.Problem_Reason,  -- Nova coluna com motivo do problema
    CASE 
        WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
              OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
              OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL)) THEN 'HEALTH_PROBLEM'
        WHEN (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1) THEN 'SUSPENDED'
        WHEN (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'STATE_PROBLEM'
        WHEN (Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')) THEN 'STATE_PROBLEM'
        ELSE 'OK'
    END AS Problem_Type
FROM
    dbo.KPI_MSSQL_ALWAYSON_STATUS_STG s
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = s.Instance  -- CORRIGIDO: Usa Instance ao invÃ©s de AgName
WHERE
    -- Mesma lÃ³gica da view agregada
    -- Problemas de Health:
    -- Se Pri_Synch_Health tem valor mas nÃ£o Ã© HEALTHY â†’ problema
    -- Se Sec_Synch_Health tem valor mas nÃ£o Ã© HEALTHY â†’ problema
    -- Se ambos sÃ£o NULL â†’ problema (dados nÃ£o coletados)
    -- Se apenas um Ã© NULL â†’ OK (instÃ¢ncia Ã© PRIMARY ou SECONDARY, nÃ£o ambos)
    ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> 'HEALTHY')
     OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY')
     OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
    OR (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
    OR (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'))
    OR (Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'));
GO

-- ============================================================================
-- VIEWS BLOCKED SESSIONS (AGG + DET)
-- ============================================================================

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
    (SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK)) i
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON i.Instance = e.Instance
    LEFT OUTER JOIN
    (SELECT Instance, COUNT(1) AS Cnt
     FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK)
     WHERE Wait_Time_Sec > 0
     GROUP BY Instance) bs
      ON i.Instance = bs.Instance;
GO

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

-- ============================================================================
-- VIEWS BLOCKED USERS (AGG + DET)
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW
AS
SELECT
    i.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(bu.Blocked_Users_Count, 0) AS Blocked_Users_Count,
    ISNULL(bu.Total_Blocked_Count, 0) AS Total_Blocked_Count
FROM
    (SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)) i
    LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON i.Instance = e.Instance
    LEFT OUTER JOIN
    (SELECT Instance,
        COUNT(DISTINCT [User]) AS Blocked_Users_Count,
        SUM(Blocked_Count) AS Total_Blocked_Count
     FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
     WHERE Blocked_Count > 0
     GROUP BY Instance) bu
      ON i.Instance = bu.Instance;
GO

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

-- ============================================================================
-- VIEWS DATABASE AVAILABILITY (AGG + DET)
-- ============================================================================

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
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
     GROUP BY Instance) t
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = t.Instance
    LEFT OUTER JOIN
    (SELECT Instance, COUNT(1) AS Cnt
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
     WHERE 
         -- Mesma lÃ³gica da DET_VIEW
         (
             (Mirroring_Role IS NULL AND ([State] <> 'ONLINE' OR Is_Available = 0))
             OR (Mirroring_Role = 'PRINCIPAL' AND ([State] <> 'ONLINE' OR Is_Available = 0))
             OR (Mirroring_Role = 'MIRROR' AND ([State] <> 'RESTORING' OR Is_Available = 0))
         )
     GROUP BY Instance) d
      ON t.Instance = d.Instance;
GO

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
    -- LÃ³gica do Oracle: excluir RESTORING apenas quando mirroring_role = 'MIRROR'
    -- Para outras situaÃ§Ãµes, RESTORING Ã© considerado problema
    (
        -- Sem mirroring: considerar problema se State <> 'ONLINE' ou Is_Available = 0
        (d.Mirroring_Role IS NULL AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0))
        -- Principal em mirroring: considerar problema se State <> 'ONLINE' ou Is_Available = 0
        OR (d.Mirroring_Role = 'PRINCIPAL' AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0))
        -- Mirror em mirroring: considerar problema se State <> 'RESTORING' ou Is_Available = 0
        -- (RESTORING Ã© estado normal para MIRROR, entÃ£o nÃ£o Ã© problema)
        OR (d.Mirroring_Role = 'MIRROR' AND (d.[State] <> 'RESTORING' OR d.Is_Available = 0))
    );
GO

-- ============================================================================
-- VIEWS DISK USAGE (AGG + DET)
-- ============================================================================

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
    d.Percent_Free < 20;
GO

-- ============================================================================
-- VIEWS FILEGROUP USAGE (AGG + DET)
-- ============================================================================

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
    f.Percent_Used >= 80;
GO

-- ============================================================================
-- VIEWS INSTANCE AVAILABILITY (AGG + DET)
-- ============================================================================

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

-- ============================================================================
-- VIEWS LONG LOCKS (AGG + DET)
-- ============================================================================

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

-- ============================================================================
-- VIEWS PROCESSES (AGG + DET)
-- ============================================================================

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

-- ============================================================================
-- VIEWS TRANSACTION LOG USAGE (AGG + DET)
-- ============================================================================

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
    t.Percent_Used >= 70;
GO

-- ============================================================================
-- VIEWS BACKUPS (AGG + DET)
-- ============================================================================

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
    b.Hours_Since_Backup > 24
    OR b.Last_Backup_Date IS NULL;
GO

-- ============================================================================
-- VIEW CMDB
-- ============================================================================

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

-- ============================================================================
-- VIEWS DEADLOCKS (AGG + DET)
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW
AS
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Deadlock_Count,
    MAX(d.Deadlock_Time) AS Last_Deadlock_Time,
    COUNT(DISTINCT d.Database_Name) AS Databases_Affected,
    COUNT(DISTINCT d.Object_Name) AS Objects_Affected
FROM
    dbo.KPI_MSSQL_DEADLOCKS_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    d.Deadlock_Time >= DATEADD(HOUR, -24, GETDATE())
GROUP BY
    d.Instance, e.Env;
GO

IF OBJECT_ID('dbo.KPI_MSSQL_DEADLOCKS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DEADLOCKS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DEADLOCKS_DET_VIEW
AS
SELECT TOP 1000
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.Deadlock_Time,
    d.Victim_Session_Id,
    d.Database_Name,
    d.Object_Name,
    d.Index_Name,
    d.Lock_Mode,
    d.Resource_Type,
    DATEDIFF(MINUTE, d.Deadlock_Time, GETDATE()) AS Minutes_Ago
FROM
    dbo.KPI_MSSQL_DEADLOCKS_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    d.Deadlock_Time >= DATEADD(HOUR, -24, GETDATE())
ORDER BY
    d.Deadlock_Time DESC;
GO

-- ============================================================================
-- VIEWS SERVICE STATUS (AGG + DET)
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW
AS
SELECT
    s.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Services_Down_Count,
    COUNT(DISTINCT s.Service_Name) AS Unique_Services_Down,
    MAX(s.Update_TS) AS Last_Check,
    MAX(s.Event_Log_Time) AS Last_Event_Time,
    STRING_AGG(
        CASE 
            WHEN s.Service_Display_Name IS NOT NULL AND s.Service_Display_Name <> s.Service_Name
            THEN s.Service_Display_Name + ' (' + s.Service_Name + ')'
            ELSE s.Service_Name
        END, 
        ', '
    ) AS Services_Down_List
FROM
    dbo.KPI_MSSQL_SERVICE_STATUS_STG s
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = s.Instance
WHERE
    s.Service_Status <> 'OK'
    AND s.Update_TS >= DATEADD(HOUR, -24, GETDATE())
GROUP BY
    s.Instance, e.Env;
GO

IF OBJECT_ID('dbo.KPI_MSSQL_SERVICE_STATUS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVICE_STATUS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVICE_STATUS_DET_VIEW
AS
SELECT TOP 1000
    s.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(s.Service_Display_Name, s.Service_Name) AS Service_Display_Name,  -- Nome completo do serviÃ§o (como na imagem: "SQL Server Agent (I01)")
    s.Service_Name,  -- Nome tÃ©cnico do serviÃ§o (ex: "MSSQL$I01")
    s.Service_Display_Name AS Display_Name_Full,  -- Nome de exibiÃ§Ã£o completo original (ex: "SQL Server Agent (I01)")
    s.Service_State,
    s.Service_Status,
    s.Start_Mode,
    s.Start_Time,
    s.Stop_Time,
    s.Last_Error_Code,
    s.Last_Error_Message,
    s.Event_Log_Entry,
    s.Event_Log_Time,
    s.Detection_Method,
    s.Connection_Error,
    s.Resolved,
    s.Resolved_Time,
    s.Update_TS,
    DATEDIFF(MINUTE, s.Update_TS, GETDATE()) AS Minutes_Ago
FROM
    dbo.KPI_MSSQL_SERVICE_STATUS_STG s
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = s.Instance
WHERE
    s.Service_Status <> 'OK'
    AND s.Update_TS >= DATEADD(HOUR, -24, GETDATE())
ORDER BY
    s.Update_TS DESC, s.Instance, s.Service_Name;
GO

-- ============================================================================
-- VIEWS DATABASE I/O STATS (AGG + DET)
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_DB_IO_STATS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DB_IO_STATS_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DB_IO_STATS_AGG_VIEW
AS
SELECT 
    i.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(DISTINCT io.[Database]) AS Total_Databases,
    SUM(io.Reads) AS Total_Reads,
    SUM(io.Writes) AS Total_Writes,
    SUM(io.All_Activity) AS Total_Activity,
    AVG(io.Reads_Percent) AS Avg_Reads_Percent,
    AVG(io.Writes_Percent) AS Avg_Writes_Percent,
    MAX(io.Update_TS) AS Last_Update_TS
FROM (
    SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_DB_IO_STATS_STG WITH (NOLOCK)
) i
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e ON i.Instance = e.Instance
LEFT JOIN dbo.KPI_MSSQL_DB_IO_STATS_STG WITH (NOLOCK) io ON i.Instance = io.Instance
GROUP BY i.Instance, ISNULL(e.Env, 'Undefined');
GO

IF OBJECT_ID('dbo.KPI_MSSQL_DB_IO_STATS_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DB_IO_STATS_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DB_IO_STATS_DET_VIEW
AS
SELECT TOP 1000
    io.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    io.[Database],
    io.Reads,
    io.Reads_Percent,
    io.Writes,
    io.Writes_Percent,
    io.All_Activity,
    io.Update_TS
FROM dbo.KPI_MSSQL_DB_IO_STATS_STG WITH (NOLOCK) io
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e ON io.Instance = e.Instance
ORDER BY io.Update_TS DESC, io.All_Activity DESC;
GO

PRINT '  âœ… 28 views KPI criadas (14 KPIs Ã— 2 views AGG/DET cada)!';
PRINT '  âœ… 2 views SERVICE STATUS criadas (AGG + DET)!';
PRINT '  âœ… 2 views DATABASE I/O STATS criadas (AGG + DET)!';
PRINT '  âœ… 2 views de dashboard criadas (V_DASHBOARD_SUMMARY + V_DASHBOARD_BY_ENV)!';
PRINT '  âœ… TOTAL: 34 views (28 KPI + 2 Service Status + 2 DB I/O Stats + 2 Dashboard)!';
GO

-- ============================================================================
-- VIEWS DE DASHBOARD (V_DASHBOARD_SUMMARY + V_DASHBOARD_BY_ENV)
-- ============================================================================

PRINT '';
PRINT '[9.6/18] Criando views de dashboard...';
GO

-- VIEW: DASHBOARD SUMMARY (Agrega todos os KPIs para o dashboard)
IF OBJECT_ID('dbo.V_DASHBOARD_SUMMARY', 'V') IS NOT NULL
    DROP VIEW dbo.V_DASHBOARD_SUMMARY;
GO

CREATE VIEW dbo.V_DASHBOARD_SUMMARY
AS
SELECT
    -- DISPONIBILIDADE
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) WHERE State <> 'ONLINE') AS DB_Not_Availability,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) WHERE State = 'ONLINE') AS DB_Availability,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Is_Available = 1) AS Instancias_OK,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Is_Available = 0) AS Instances_Off,
    
    -- PERFORMANCE
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK)) AS Blocked_Sessions,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)) AS Blocked_Users,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_LONG_LOCKS_STG WITH (NOLOCK) WHERE Duration_Sec >= 60 AND Duration_Sec < 300) AS Lock_Count_Warning,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_LONG_LOCKS_STG WITH (NOLOCK) WHERE Duration_Sec >= 300) AS Lock_Count_Critical,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WHERE [State] IN ('WARNING', 'CRITICAL')) AS Processes_Alarm,
    
    -- ESPAÃ‡O
    (SELECT SUM(Critical) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW) AS Transaction_Logs_Critical,
    (SELECT SUM(Warning) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW) AS Transaction_Logs_Warning,
    (SELECT SUM(Critical) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW) AS Disk_File_System_Critical,
    (SELECT SUM(Warning) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW) AS Disk_File_System_Warning,
    (SELECT SUM(Warning) FROM dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW) AS FileGroups_Usage_Warning,
    (SELECT SUM(Critical) FROM dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW) AS FileGroups_Usage_Critical,
    
    -- ALTA DISPONIBILIDADE
    (SELECT COUNT(DISTINCT AgName) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) 
     WHERE (Pri_Synch_Health IS NULL OR Pri_Synch_Health <> 'HEALTHY' OR Sec_Synch_Health IS NULL OR Sec_Synch_Health <> 'HEALTHY')
        OR (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
        OR (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'))
        OR (Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'))) AS AlwaysOn_UnHealthy;
GO

PRINT '  âœ… View V_DASHBOARD_SUMMARY criada';
GO

-- VIEW: DASHBOARD BY ENVIRONMENT (Agrega por ambiente)
IF OBJECT_ID('dbo.V_DASHBOARD_BY_ENV', 'V') IS NOT NULL
    DROP VIEW dbo.V_DASHBOARD_BY_ENV;
GO

CREATE VIEW dbo.V_DASHBOARD_BY_ENV
AS
SELECT
    ISNULL(e.Env, 'Undefined') AS Environment,
    
    -- DISPONIBILIDADE
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) da
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON da.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined') AND da.State <> 'ONLINE') AS DB_Not_Availability,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) da
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON da.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined') AND da.State = 'ONLINE') AS DB_Availability,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) ia
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON ia.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined') AND ia.Is_Available = 1) AS Instancias_OK,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) ia
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON ia.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined') AND ia.Is_Available = 0) AS Instances_Off,
    
    -- PERFORMANCE
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK) bs
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON bs.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined')) AS Blocked_Sessions,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) bu
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON bu.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined')) AS Blocked_Users,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_LONG_LOCKS_STG WITH (NOLOCK) ll
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON ll.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined') AND ll.Duration_Sec >= 60 AND ll.Duration_Sec < 300) AS Lock_Count_Warning,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_LONG_LOCKS_STG WITH (NOLOCK) ll
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON ll.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined') AND ll.Duration_Sec >= 300) AS Lock_Count_Critical,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW pa
     WHERE pa.Env = ISNULL(e.Env, 'Undefined') AND pa.[State] IN ('WARNING', 'CRITICAL')) AS Processes_Alarm,
    
    -- ESPAÃ‡O
    (SELECT SUM(Critical) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW tlog
     WHERE tlog.Env = ISNULL(e.Env, 'Undefined')) AS Transaction_Logs_Critical,
    (SELECT SUM(Warning) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW tlog
     WHERE tlog.Env = ISNULL(e.Env, 'Undefined')) AS Transaction_Logs_Warning,
    (SELECT SUM(Critical) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW disk
     WHERE disk.Env = ISNULL(e.Env, 'Undefined')) AS Disk_File_System_Critical,
    (SELECT SUM(Warning) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW disk
     WHERE disk.Env = ISNULL(e.Env, 'Undefined')) AS Disk_File_System_Warning,
    (SELECT SUM(Warning) FROM dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW fg
     WHERE fg.Env = ISNULL(e.Env, 'Undefined')) AS FileGroups_Usage_Warning,
    (SELECT SUM(Critical) FROM dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW fg
     WHERE fg.Env = ISNULL(e.Env, 'Undefined')) AS FileGroups_Usage_Critical,
    
    -- ALTA DISPONIBILIDADE
    (SELECT COUNT(DISTINCT ao.AgName) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) ao
     INNER JOIN dbo.KPI_MSSQL_INST_ENVS e2 ON ao.Instance = e2.Instance
     WHERE e2.Env = ISNULL(e.Env, 'Undefined')
       AND ((ao.Pri_Synch_Health IS NULL OR ao.Pri_Synch_Health <> 'HEALTHY' OR ao.Sec_Synch_Health IS NULL OR ao.Sec_Synch_Health <> 'HEALTHY')
        OR (ao.Pri_Is_Suspended = 1 OR ao.Sec_Is_Suspended = 1)
        OR (ao.Pri_Synch_State IS NOT NULL AND ao.Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING'))
        OR (ao.Sec_Synch_State IS NOT NULL AND ao.Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING')))) AS AlwaysOn_UnHealthy
FROM dbo.KPI_MSSQL_INST_ENVS WITH (NOLOCK) e
GROUP BY e.Env;
GO

PRINT '  âœ… View V_DASHBOARD_BY_ENV criada';
GO

PRINT '  âœ… 2 views de dashboard criadas!';
GO

-- =============================================
-- STEP 10: CREATE DEFAULT TENANT
-- =============================================
PRINT '';
PRINT '[10/18] Criando tenant padrÃ£o...';

INSERT INTO [metadata].[tenants] (tenant_id, tenant_name, [plan], max_servers, retention_days, is_active)
VALUES ('default', 'Default Tenant', 'professional', 100, 90, 1);

PRINT '  âœ… Tenant padrÃ£o criado!';
GO

-- =============================================
-- PARTE 2: STORED PROCEDURES
-- =============================================

PRINT '';
PRINT '[11/13] Criando Stored Procedures...';
GO

-- Procedure 1: Insert metrics (bulk)
CREATE OR ALTER PROCEDURE [timeseries].[usp_insert_metrics]
    @metrics NVARCHAR(MAX) -- JSON array
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO [timeseries].[metrics] (
            tenant_id, server_id, collector_name,
            metric_name, metric_value, [timestamp], tags
        )
        SELECT
            tenant_id, server_id, collector_name,
            metric_name, metric_value,
            CAST([timestamp] AS DATETIME2), tags
        FROM OPENJSON(@metrics)
        WITH (
            tenant_id VARCHAR(50) '$.tenant_id',
            server_id VARCHAR(100) '$.server_id',
            collector_name VARCHAR(100) '$.collector_name',
            metric_name VARCHAR(200) '$.metric_name',
            metric_value FLOAT '$.metric_value',
            [timestamp] VARCHAR(30) '$.timestamp',
            tags NVARCHAR(500) '$.tags'
        );

        COMMIT TRANSACTION;
        RETURN @@ROWCOUNT;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

PRINT '  âœ… Procedure usp_insert_metrics criada';
GO

-- Procedure 2: Detect patterns
CREATE OR ALTER PROCEDURE [meta].[usp_detect_patterns]
    @tenant_id VARCHAR(50) = 'default',
    @lookback_hours INT = 24
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @threshold_high_cpu FLOAT = 80.0;
    DECLARE @start_time DATETIME2 = DATEADD(HOUR, -@lookback_hours, SYSUTCDATETIME());

    -- Detect High CPU pattern
    INSERT INTO [curated].[insights] (
        tenant_id, instance_id, pattern_id,
        severity, summary, details, first_detected
    )
    SELECT DISTINCT
        @tenant_id,
        m.server_id,
        1, -- Pattern ID for High CPU
        'high',
        'High CPU detected: ' + CAST(AVG(m.metric_value) AS VARCHAR(10)) + '%',
        NULL,
        MIN(m.[timestamp])
    FROM [timeseries].[metrics] m
    WHERE m.tenant_id = @tenant_id
      AND m.metric_name = 'cpu.utilization_pct'
      AND m.[timestamp] >= @start_time
      AND m.metric_value >= @threshold_high_cpu
    GROUP BY m.server_id
    HAVING COUNT(*) >= 5 -- At least 5 samples above threshold
      AND NOT EXISTS (
          SELECT 1 FROM [curated].[insights] i
          WHERE i.server_id = m.server_id
            AND i.pattern_id = 1
            AND i.is_resolved = 0
      );

    RETURN @@ROWCOUNT;
END;
GO

PRINT '  âœ… Procedure usp_detect_patterns criada';
GO

-- Procedure 3: Cleanup old data
CREATE OR ALTER PROCEDURE [timeseries].[usp_cleanup_old_data]
    @retention_days_raw INT = 90,
    @retention_days_aggregated INT = 365
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @cutoff_raw DATETIME2 = DATEADD(DAY, -@retention_days_raw, SYSUTCDATETIME());
    DECLARE @cutoff_agg DATETIME2 = DATEADD(DAY, -@retention_days_aggregated, SYSUTCDATETIME());
    DECLARE @rows_deleted INT = 0;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- Delete old raw metrics
        DELETE FROM [timeseries].[metrics]
        WHERE [timestamp] < @cutoff_raw;

        SET @rows_deleted = @@ROWCOUNT;

        -- Delete old aggregated metrics
        DELETE FROM [timeseries].[metrics_1min]
        WHERE window_start < @cutoff_agg;

        SET @rows_deleted = @rows_deleted + @@ROWCOUNT;

        COMMIT TRANSACTION;

        PRINT 'Cleanup complete. Rows deleted: ' + CAST(@rows_deleted AS VARCHAR(20));
        RETURN @rows_deleted;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

PRINT '  âœ… Procedure usp_cleanup_old_data criada';
GO

-- Procedure 4: Generate alerts
CREATE OR ALTER PROCEDURE [alerts].[usp_generate_alerts]
    @tenant_id VARCHAR(50) = 'default'
AS
BEGIN
    SET NOCOUNT ON;

    -- Generate alerts from active insights
    INSERT INTO [alerts].[alert_history] (
        tenant_id, instance_id, alert_definition_id,
        severity, [message], alert_data, triggered_at
    )
    SELECT
        i.tenant_id,
        i.instance_id,
        1, -- Default alert definition
        i.severity,
        p.pattern_name + ': ' + i.summary,
        i.details,
        SYSUTCDATETIME()
    FROM [curated].[insights] i
    INNER JOIN [meta].[patterns] p ON i.pattern_id = p.pattern_id
    WHERE i.tenant_id = @tenant_id
      AND i.is_resolved = 0
      AND i.severity IN ('high', 'critical')
      AND NOT EXISTS (
          SELECT 1 FROM [alerts].[alert_history] ah
          WHERE ah.instance_id = i.instance_id
            AND ah.severity = i.severity
            AND ah.triggered_at >= DATEADD(HOUR, -1, SYSUTCDATETIME())
            AND ah.resolved_at IS NULL
      );

    RETURN @@ROWCOUNT;
END;
GO

PRINT '  âœ… Procedure usp_generate_alerts criada';
GO

-- Procedure 5: Get server health summary
CREATE OR ALTER PROCEDURE [metadata].[usp_get_server_health]
    @tenant_id VARCHAR(50) = 'default'
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        sc.instance_id,
        sc.environment,
        sc.priority,
        sc.is_active,
        (SELECT COUNT(*) FROM [curated].[insights] i
         WHERE i.instance_id = sc.instance_id
           AND i.is_resolved = 0
           AND i.severity = 'critical') AS critical_issues,
        (SELECT COUNT(*) FROM [curated].[insights] i
         WHERE i.instance_id = sc.instance_id
           AND i.is_resolved = 0
           AND i.severity = 'high') AS high_issues,
        (SELECT COUNT(*) FROM [curated].[insights] i
         WHERE i.instance_id = sc.instance_id
           AND i.is_resolved = 0
           AND i.severity = 'medium') AS medium_issues,
        (SELECT TOP 1 metric_value
         FROM [timeseries].[metrics] m
         WHERE m.server_id = sc.instance_id
           AND m.metric_name = 'cpu.utilization_pct'
         ORDER BY m.[timestamp] DESC) AS current_cpu_pct,
        (SELECT TOP 1 metric_value
         FROM [timeseries].[metrics] m
         WHERE m.server_id = sc.instance_id
           AND m.metric_name = 'memory.available_mb'
         ORDER BY m.[timestamp] DESC) AS current_memory_mb
    FROM [metadata].[server_config] sc
    WHERE sc.tenant_id = @tenant_id
      AND sc.is_active = 1
    ORDER BY sc.priority DESC, sc.instance_id;
END;
GO

PRINT '  âœ… Procedure usp_get_server_health criada';
PRINT '  âœ… Total: 5 Stored Procedures criadas!';
GO

-- =============================================
-- STEP 11.5: KPI PROCEDURES (12 PROCEDURES)
-- =============================================

PRINT '';
PRINT '[11.5/18] Criando Stored Procedures KPI Oracle (12 procedures)...';
GO

USE [WatcherDB_Intelligence];
GO

-- ============================================================================
-- PROCEDURE 1: COLETA ALWAYS ON STATUS
-- ============================================================================

PRINT '';
PRINT '-- [1/12] Criando procedure: usp_Collect_AlwaysOn_Status...';
GO

-- ============================================================================
-- NOTA IMPORTANTE SOBRE COLETA DE ALWAYSON:
-- ============================================================================
-- A coleta principal de AlwaysOn agora Ã© feita via Python (collect_data_async.py)
-- que conecta DIRETAMENTE em cada instÃ¢ncia SQL Server e coleta os dados.
--
-- Vantagens da coleta via Python:
-- - Coleta de TODAS as instÃ¢ncias remotas (nÃ£o apenas o servidor local)
-- - Usa conexÃµes diretas (pyodbc) - nÃ£o requer linked servers
-- - ConfiguraÃ§Ã£o centralizada no servers.json (campo has_alwayson)
-- - Mais flexÃ­vel e fÃ¡cil de manter
--
-- Esta stored procedure Ã© mantida como FALLBACK para coleta local apenas.
-- O script Python estÃ¡ em: scripts/collect_alwayson.py
-- ============================================================================

IF OBJECT_ID('dbo.usp_Collect_AlwaysOn_Status', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_AlwaysOn_Status;
GO

CREATE PROCEDURE dbo.usp_Collect_AlwaysOn_Status
    @TruncateFirst BIT = 0  -- Se 1, trunca a tabela primeiro (usado quando executado sozinho)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- NOTA: Por padrÃ£o NÃƒO truncamos a tabela porque a coleta Python
        -- jÃ¡ inseriu dados de todas as instÃ¢ncias. Esta procedure apenas
        -- adiciona/atualiza os dados da instÃ¢ncia LOCAL.

        IF @TruncateFirst = 1
        BEGIN
            TRUNCATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG;
            PRINT '  [INFO] Tabela STG truncada';
        END

        -- Coletar status Always On da instÃ¢ncia LOCAL
        -- NOTA: Esta procedure coleta apenas do servidor onde estÃ¡ executando
        -- Para coleta de TODAS as instÃ¢ncias, usar o script Python: collect_alwayson.py
        INSERT INTO dbo.KPI_MSSQL_ALWAYSON_STATUS_STG (
            AgName, Instance, [Database],
            Pri_Synch_State, Pri_Synch_Health, Pri_Is_Suspended,
            Sec_Synch_State, Sec_Synch_Health, Sec_Is_Suspended,
            Commit_Diff_Secs, Update_TS
        )
        SELECT
            ag.name AS AgName,
            REPLACE(@@SERVERNAME, '\', '_') AS Instance,  -- Normalizado para match com Python
            DB_NAME(rs.database_id) AS [Database],
            -- Primary replica
            MAX(CASE WHEN ars.role_desc = 'PRIMARY' THEN rs.synchronization_state_desc ELSE NULL END) AS Pri_Synch_State,
            MAX(CASE WHEN ars.role_desc = 'PRIMARY' THEN rs.synchronization_health_desc ELSE NULL END) AS Pri_Synch_Health,
            MAX(CASE WHEN ars.role_desc = 'PRIMARY' AND rs.suspend_reason_desc IS NOT NULL THEN 1 ELSE 0 END) AS Pri_Is_Suspended,
            -- Secondary replica
            MAX(CASE WHEN ars.role_desc = 'SECONDARY' THEN rs.synchronization_state_desc ELSE NULL END) AS Sec_Synch_State,
            MAX(CASE WHEN ars.role_desc = 'SECONDARY' THEN rs.synchronization_health_desc ELSE NULL END) AS Sec_Synch_Health,
            MAX(CASE WHEN ars.role_desc = 'SECONDARY' AND rs.suspend_reason_desc IS NOT NULL THEN 1 ELSE 0 END) AS Sec_Is_Suspended,
            -- Lag - usar 0 como placeholder
            0 AS Commit_Diff_Secs,
            GETDATE() AS Update_TS
        FROM sys.availability_groups ag
        INNER JOIN sys.dm_hadr_database_replica_states rs
            ON ag.group_id = rs.group_id
        INNER JOIN sys.dm_hadr_availability_replica_states ars
            ON rs.replica_id = ars.replica_id
        WHERE rs.is_local = 1
        GROUP BY ag.name, rs.database_id;

        PRINT '  [OK] AlwaysOn Status LOCAL coletado: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas (instÃ¢ncia: ' + @@SERVERNAME + ')';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] AlwaysOn Status: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_AlwaysOn_Status criada (coleta LOCAL - coleta completa via Python)';
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

        -- Coletar histÃ³rico de backups
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

        -- ====================================================================
        -- PARTE 1: Coletar sessÃµes BLOQUEADAS
        -- ====================================================================
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
            0 AS Blocking_Level, -- SerÃ¡ calculado depois
            GETDATE() AS Update_TS
        FROM sys.dm_exec_requests r
        WHERE r.blocking_session_id <> 0
          AND r.session_id <> @@SPID;

        DECLARE @BlockedCount INT = @@ROWCOUNT;

        -- ====================================================================
        -- PARTE 2: Coletar informaÃ§Ãµes dos BLOQUEADORES (NOVO)
        -- ====================================================================
        -- Inserir bloqueadores que nÃ£o estÃ£o na tabela (nÃ£o estÃ£o bloqueados)
        INSERT INTO dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG (
            Instance, Session_Id, Blocked_By, Wait_Time_Sec,
            Wait_Type, [Database], [Status], Command,
            Blocking_Level, Update_TS
        )
        SELECT DISTINCT
            @@SERVERNAME AS Instance,
            blocker.session_id AS Session_Id,
            0 AS Blocked_By, -- Bloqueador raiz nÃ£o estÃ¡ bloqueado
            0 AS Wait_Time_Sec, -- NÃ£o estÃ¡ esperando
            NULL AS Wait_Type,
            DB_NAME(blocker.database_id) AS [Database],
            blocker.status AS [Status],
            blocker.command AS Command,
            -1 AS Blocking_Level, -- -1 indica que Ã© bloqueador (nÃ£o bloqueado)
            GETDATE() AS Update_TS
        FROM sys.dm_exec_requests blocker
        WHERE blocker.session_id IN (
            -- Bloqueadores que estÃ£o bloqueando outras sessÃµes
            SELECT DISTINCT blocking_session_id
            FROM sys.dm_exec_requests
            WHERE blocking_session_id <> 0
              AND blocking_session_id <> @@SPID
        )
          AND blocker.session_id NOT IN (
            -- Mas nÃ£o estÃ£o na tabela (nÃ£o estÃ£o bloqueados)
            SELECT Session_Id
            FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK)
            WHERE Instance = @@SERVERNAME
          )
          AND blocker.session_id <> @@SPID;

        DECLARE @BlockerCount INT = @@ROWCOUNT;

        -- ====================================================================
        -- PARTE 3: Calcular Blocking_Level (nÃ­vel na cadeia)
        -- ====================================================================
        -- Atualizar Blocking_Level usando CTE recursiva
        WITH BlockingHierarchy AS (
            -- NÃ­vel 0: Bloqueadores raiz (nÃ£o estÃ£o bloqueados)
            SELECT 
                Session_Id,
                Blocked_By,
                0 AS Blocking_Level
            FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK)
            WHERE Instance = @@SERVERNAME
              AND (Blocked_By = 0 OR Blocked_By IS NULL)
            
            UNION ALL
            
            -- NÃ­veis seguintes
            SELECT 
                b.Session_Id,
                b.Blocked_By,
                bh.Blocking_Level + 1 AS Blocking_Level
            FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK) b
            INNER JOIN BlockingHierarchy bh 
                ON b.Blocked_By = bh.Session_Id
            WHERE b.Instance = @@SERVERNAME
              AND b.Blocked_By <> 0
        )
        UPDATE b
        SET b.Blocking_Level = ISNULL(bh.Blocking_Level, 
            CASE WHEN b.Blocked_By = 0 THEN 0 ELSE 1 END)
        FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK) b
        LEFT JOIN BlockingHierarchy bh 
            ON b.Session_Id = bh.Session_Id
        WHERE b.Instance = @@SERVERNAME;

        PRINT '  [OK] Blocked Sessions coletadas: ' + CAST(@BlockedCount AS VARCHAR(10)) + ' bloqueados, ' + CAST(@BlockerCount AS VARCHAR(10)) + ' bloqueadores';
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

        -- Inserir dados em histÃ³rico
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

        -- Inserir dados em histÃ³rico
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
            CASE MAX(CAST(mf.is_percent_growth AS INT))
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

        -- Coletar disponibilidade da instÃ¢ncia
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

        -- Coletar locks de longa duraÃ§Ã£o (> 60 segundos)
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

        -- Coletar processos/sessÃµes ativas
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

        -- Inserir dados em histÃ³rico
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

        -- Coletar usuÃ¡rios bloqueados (agregado por usuÃ¡rio)
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
-- PROCEDURE 12: COLETA DEADLOCKS
-- ============================================================================

PRINT '';
PRINT '-- [12/13] Criando procedure: usp_Collect_Deadlocks...';
GO

IF OBJECT_ID('dbo.usp_Collect_Deadlocks', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_Deadlocks;
GO

CREATE PROCEDURE dbo.usp_Collect_Deadlocks
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- NÃ£o truncar - deadlocks sÃ£o eventos histÃ³ricos, manter todos
        -- Apenas inserir novos deadlocks do Extended Event system_health
        
        -- Coletar deadlocks do Extended Event system_health (Ãºltimas 24 horas)
        -- Nota: Esta procedure coleta deadlocks bÃ¡sicos. Para anÃ¡lise detalhada,
        -- use o Python que tem melhor parsing do XML do deadlock graph.
        INSERT INTO dbo.KPI_MSSQL_DEADLOCKS_STG (
            Instance, Deadlock_Id, Deadlock_Time, Victim_Session_Id,
            Database_Name, Object_Name, Index_Name, Lock_Mode,
            Resource_Type, Process_Xml, Deadlock_Graph, Update_TS
        )
        SELECT DISTINCT
            @@SERVERNAME AS Instance,
            -- Gerar ID Ãºnico baseado em timestamp (convertido para bigint)
            CAST(DATEDIFF_BIG(SECOND, '1970-01-01', CAST(x.event_data.value('(event/@timestamp)[1]', 'DATETIME2') AS DATETIME2)) AS BIGINT) * 1000 + 
                 ROW_NUMBER() OVER (ORDER BY x.event_data.value('(event/@timestamp)[1]', 'DATETIME2')) AS Deadlock_Id,
            CAST(x.event_data.value('(event/@timestamp)[1]', 'DATETIME2') AS DATETIME2) AS Deadlock_Time,
            CAST(x.event_data.value('(event/data[@name="victim_id"]/value)[1]', 'INT') AS INT) AS Victim_Session_Id,
            DB_NAME(CAST(x.event_data.value('(event/data[@name="database_id"]/value)[1]', 'INT') AS INT)) AS Database_Name,
            OBJECT_NAME(
                CAST(x.event_data.value('(event/data[@name="object_id"]/value)[1]', 'INT') AS INT),
                CAST(x.event_data.value('(event/data[@name="database_id"]/value)[1]', 'INT') AS INT)
            ) AS Object_Name,
            NULL AS Index_Name,
            CAST(x.event_data.value('(event/data[@name="mode"]/text)[1]', 'VARCHAR(32)') AS VARCHAR(32)) AS Lock_Mode,
            CAST(x.event_data.value('(event/data[@name="resource_type"]/text)[1]', 'VARCHAR(64)') AS VARCHAR(64)) AS Resource_Type,
            NULL AS Process_Xml,
            CAST(x.event_data.query('(event/data[@name="xml_report"]/value/deadlock)[1]') AS NVARCHAR(MAX)) AS Deadlock_Graph,
            GETDATE() AS Update_TS
        FROM (
            SELECT CAST(target_data AS XML) AS event_data
            FROM sys.dm_xe_session_targets st
            INNER JOIN sys.dm_xe_sessions s ON st.event_session_address = s.address
            WHERE s.name = 'system_health'
              AND st.target_name = 'ring_buffer'
        ) AS ed
        CROSS APPLY ed.event_data.nodes('//RingBufferTarget/event') AS x(event_data)
        WHERE x.event_data.value('(event/@name)[1]', 'VARCHAR(50)') = 'xml_deadlock_report'
          AND CAST(x.event_data.value('(event/@timestamp)[1]', 'DATETIME2') AS DATETIME2) >= DATEADD(HOUR, -24, GETDATE())
          -- Evitar duplicatas: verificar se jÃ¡ existe
          AND NOT EXISTS (
              SELECT 1 FROM dbo.KPI_MSSQL_DEADLOCKS_STG WITH (NOLOCK) d
              WHERE d.Instance = @@SERVERNAME
                AND d.Deadlock_Time = CAST(x.event_data.value('(event/@timestamp)[1]', 'DATETIME2') AS DATETIME2)
          );

        PRINT '  [OK] Deadlocks coletados: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Deadlocks: ' + ERROR_MESSAGE();
        -- NÃ£o fazer THROW para nÃ£o interromper outras coletas
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_Deadlocks criada';
GO

-- ============================================================================
-- PROCEDURE 13: COLETA SQL ERROR LOG
-- ============================================================================
-- âš ï¸ DESCONTINUADO: KPI error_log foi removido devido a problemas de permissÃ£o com xp_readerrorlog
-- Esta procedure nÃ£o Ã© mais utilizada pelo sistema de coleta async
/*
PRINT '';
PRINT '-- [13/13] Criando procedure: usp_Collect_ErrorLog...';
GO

IF OBJECT_ID('dbo.usp_Collect_ErrorLog', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_ErrorLog;
GO

CREATE PROCEDURE dbo.usp_Collect_ErrorLog
    @LogFilesToRead INT = 7,  -- Quantos arquivos de log ler (0 = atual, 1 = anterior, etc.)
    @DaysToLookBack INT = 1   -- Quantos dias para trÃ¡s buscar
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        DECLARE @Instance VARCHAR(64) = @@SERVERNAME;
        DECLARE @StartDate DATETIME2 = DATEADD(DAY, -@DaysToLookBack, GETDATE());
        DECLARE @RowsInserted INT = 0;

        -- Criar tabela temporÃ¡ria para armazenar logs
        CREATE TABLE #ErrorLogTemp (
            LogDate DATETIME2,
            ProcessInfo VARCHAR(128),
            LogText NVARCHAR(MAX)
        );

        -- Ler logs de mÃºltiplos arquivos (0 = atual, 1 = anterior, etc.)
        DECLARE @FileNumber INT = 0;
        DECLARE @SQL NVARCHAR(MAX);

        WHILE @FileNumber <= @LogFilesToRead
        BEGIN
            SET @SQL = N'INSERT INTO #ErrorLogTemp EXEC sys.xp_readerrorlog ' + CAST(@FileNumber AS VARCHAR(2)) + N', 1;';
            
            BEGIN TRY
                EXEC sp_executesql @SQL;
            END TRY
            BEGIN CATCH
                -- Se o arquivo de log nÃ£o existir, continuar com o prÃ³ximo
                IF ERROR_NUMBER() <> 22026
                    PRINT '  [AVISO] Erro ao ler log file ' + CAST(@FileNumber AS VARCHAR) + ': ' + ERROR_MESSAGE();
            END CATCH

            SET @FileNumber = @FileNumber + 1;
        END

        -- Processar e inserir apenas novos logs
        INSERT INTO dbo.KPI_MSSQL_ERRORLOG_STG (
            Instance, Log_Date, Process_Info, Log_Text, 
            Log_Type, Error_Number, Severity, State, Log_File_Number, Update_TS
        )
        SELECT DISTINCT
            @Instance AS Instance,
            CAST(LogDate AS DATETIME2) AS Log_Date,
            ProcessInfo AS Process_Info,
            LogText AS Log_Text,
            -- Detectar tipo de log
            CASE 
                WHEN LogText LIKE '%Error:%' OR LogText LIKE '%[Ee]rror%' THEN 'ERROR'
                WHEN LogText LIKE '%Warning:%' OR LogText LIKE '%[Ww]arning%' THEN 'WARNING'
                WHEN LogText LIKE '%[Ii]nformation%' OR LogText LIKE '%[Ii]nfo%' THEN 'INFO'
                WHEN LogText LIKE '%[Ff]ailed%' OR LogText LIKE '%[Ff]ailure%' THEN 'ERROR'
                WHEN LogText LIKE '%[Ss]uccess%' OR LogText LIKE '%[Ss]uccessful%' THEN 'INFO'
                ELSE 'UNKNOWN'
            END AS Log_Type,
            -- Tentar extrair Error Number
            CASE 
                WHEN LogText LIKE 'Error:%' THEN 
                    TRY_CAST(SUBSTRING(LogText, CHARINDEX('Error:', LogText) + 7, 10) AS INT)
                ELSE NULL
            END AS Error_Number,
            -- Tentar extrair Severity
            CASE 
                WHEN LogText LIKE '%Severity:%' THEN 
                    TRY_CAST(SUBSTRING(LogText, CHARINDEX('Severity:', LogText) + 10, 3) AS INT)
                ELSE NULL
            END AS Severity,
            -- Tentar extrair State
            CASE 
                WHEN LogText LIKE '%State:%' THEN 
                    TRY_CAST(SUBSTRING(LogText, CHARINDEX('State:', LogText) + 7, 3) AS INT)
                ELSE NULL
            END AS State,
            NULL AS Log_File_Number,
            GETDATE() AS Update_TS
        FROM #ErrorLogTemp
        WHERE LogDate >= @StartDate
          -- Filtrar logs irrelevantes
          AND LogText NOT LIKE 'Log was backed up.%'
          AND LogText NOT LIKE 'Database mirroring is active%'
          AND LogText NOT LIKE 'The log has been reused%'
          AND LogText NOT LIKE 'CHECKDB%found 0 allocation errors%'
          AND LogText NOT LIKE 'Starting up%'
          AND LogText NOT LIKE 'Recovery is complete%'
          -- Evitar duplicatas: verificar se jÃ¡ existe (usando hash)
          AND NOT EXISTS (
              SELECT 1 
              FROM dbo.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK) 
              WHERE Instance = @Instance
                AND Log_Date = CAST(LogDate AS DATETIME2)
                AND Log_Text_Hash = CHECKSUM(LogText)
          );

        SET @RowsInserted = @@ROWCOUNT;

        -- Mover dados antigos para histÃ³rico (logs com mais de 7 dias)
        INSERT INTO dbo.KPI_MSSQL_ERRORLOG_HIST (
            Instance, Log_Date, Process_Info, Log_Text, 
            Log_Type, Error_Number, Severity, State, Log_File_Number, Update_TS
        )
        SELECT 
            Instance, Log_Date, Process_Info, Log_Text,
            Log_Type, Error_Number, Severity, State, Log_File_Number, Update_TS
        FROM dbo.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)
        WHERE Instance = @Instance
          AND Log_Date < DATEADD(DAY, -7, GETDATE())
          AND NOT EXISTS (
              SELECT 1 
              FROM dbo.KPI_MSSQL_ERRORLOG_HIST WITH (NOLOCK) h
              WHERE h.Instance = Instance
                AND h.Log_Date = Log_Date
                AND h.Log_Text_Hash = Log_Text_Hash
                AND h.Update_TS = Update_TS
          );

        -- Remover da STG apÃ³s mover para HIST
        DELETE FROM dbo.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)
        WHERE Instance = @Instance
          AND Log_Date < DATEADD(DAY, -7, GETDATE());

        -- Limpar tabela temporÃ¡ria
        DROP TABLE #ErrorLogTemp;

        PRINT '  [OK] Error Log coletado: ' + CAST(@RowsInserted AS VARCHAR(10)) + ' novos eventos';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] Error Log: ' + ERROR_MESSAGE();
        IF OBJECT_ID('tempdb..#ErrorLogTemp') IS NOT NULL
            DROP TABLE #ErrorLogTemp;
        -- NÃ£o fazer THROW para nÃ£o interromper outras coletas
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_ErrorLog criada';
GO
*/
PRINT '  âš ï¸  Procedure usp_Collect_ErrorLog DESCONTINUADA (comentada)';
GO

-- ============================================================================
-- PROCEDURE MASTER: EXECUTA TODAS AS COLETAS
-- ============================================================================

PRINT '';
PRINT '-- [13/13] Criando procedure MASTER: usp_Collect_All_KPIs...';
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
    PRINT 'WATCHERDB INTELLIGENCE - COLETA COMPLETA DE KPIs';
    PRINT '============================================================================';
    PRINT 'InÃ­cio: ' + CONVERT(VARCHAR(23), @StartTime, 121);
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
        IF @Debug = 1 PRINT '[11/12] Coletando TLog Usage...';
        EXEC dbo.usp_Collect_TLog_Usage;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] TLog Usage: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 12. Deadlocks
    BEGIN TRY
        IF @Debug = 1 PRINT '[12/13] Coletando Deadlocks...';
        EXEC dbo.usp_Collect_Deadlocks;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Deadlocks: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH

    -- 13. SQL Error Log
    -- âš ï¸ DESCONTINUADO: KPI error_log foi removido
    /*
    BEGIN TRY
        IF @Debug = 1 PRINT '[13/13] Coletando SQL Error Log...';
        EXEC dbo.usp_Collect_ErrorLog @LogFilesToRead = 3, @DaysToLookBack = 1;
        SET @SuccessCount += 1;
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] Error Log: ' + ERROR_MESSAGE();
        SET @ErrorCount += 1;
    END CATCH
    */
    IF @Debug = 1 PRINT '[13/13] SQL Error Log DESCONTINUADO (pulando...)';

    -- Resumo
    DECLARE @Duration INT = DATEDIFF(SECOND, @StartTime, GETDATE());

    PRINT '';
    PRINT '============================================================================';
    PRINT 'RESUMO DA COLETA';
    PRINT '============================================================================';
    PRINT 'Sucesso: ' + CAST(@SuccessCount AS VARCHAR(10)) + ' / 13';
    PRINT 'Erros: ' + CAST(@ErrorCount AS VARCHAR(10));
    PRINT 'DuraÃ§Ã£o: ' + CAST(@Duration AS VARCHAR(10)) + ' segundos';
    PRINT 'TÃ©rmino: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
    PRINT '============================================================================';
    PRINT '';

    -- Retornar cÃ³digo de erro se houver falhas
    IF @ErrorCount > 0
        RETURN 1;
    ELSE
        RETURN 0;
END;
GO

PRINT '  [OK] Procedure usp_Collect_All_KPIs criada';
PRINT '  âœ… 14 procedures KPI criadas!';
GO

-- =============================================
-- PARTE 3: SQL AGENT JOBS
-- =============================================

PRINT '';
PRINT '[13/13] Criando SQL Agent Jobs...';
GO

USE [msdb];
GO

-- JOB 1: Detect Patterns (every 15 minutes)
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Detect_Patterns')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Detect_Patterns';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Detect_Patterns',
    @enabled = 1,
    @description = N'Detecta patterns de problemas nas mÃ©tricas coletadas';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Detect_Patterns',
    @step_name = N'Detect patterns',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'EXEC [meta].[usp_detect_patterns] @tenant_id = ''default'', @lookback_hours = 1;',
    @retry_attempts = 3,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Detect_Patterns',
    @name = N'Every 15 minutes',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 15,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Detect_Patterns',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Detect_Patterns criado';
GO

-- JOB 2: Generate Alerts (every 5 minutes)
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Generate_Alerts')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Generate_Alerts';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Generate_Alerts',
    @enabled = 1,
    @description = N'Gera alertas baseados em insights detectados';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Generate_Alerts',
    @step_name = N'Generate alerts',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'EXEC [alerts].[usp_generate_alerts] @tenant_id = ''default'';',
    @retry_attempts = 3,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Generate_Alerts',
    @name = N'Every 5 minutes',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 5,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Generate_Alerts',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Generate_Alerts criado';
GO

-- JOB 3: Cleanup Old Data (daily at 2 AM)
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Cleanup_Old_Data')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Cleanup_Old_Data';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Cleanup_Old_Data',
    @enabled = 1,
    @description = N'Remove dados antigos para economizar espaÃ§o';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Cleanup_Old_Data',
    @step_name = N'Cleanup old metrics',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'EXEC [timeseries].[usp_cleanup_old_data] @retention_days_raw = 90, @retention_days_aggregated = 365;',
    @retry_attempts = 2,
    @retry_interval = 5;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Cleanup_Old_Data',
    @name = N'Daily at 2 AM',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 1,
    @active_start_time = 020000;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Cleanup_Old_Data',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Cleanup_Old_Data criado';
PRINT '  âœ… Total: 3 SQL Agent Jobs de ANÃLISE criados!';
GO

-- =============================================
-- JOBS DE COLETA DE DADOS
-- =============================================

PRINT '';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT ' Criando Jobs de COLETA DE DADOS (5 jobs)';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';

-- ============================================================================
-- JOB 4: COLLECT METRICS - Coleta mÃ©tricas de performance dos servidores
-- FrequÃªncia: A cada 1 minuto
-- ============================================================================
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Collect_Metrics')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Collect_Metrics';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_Metrics',
    @enabled = 1,
    @description = N'Coleta mÃ©tricas de CPU, memÃ³ria, disco, IO, waits, connections dos servidores monitorados';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_Metrics',
    @step_name = N'Coletar mÃ©tricas de todos os servidores',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'
DECLARE @server_id VARCHAR(100);
DECLARE @host VARCHAR(200);
DECLARE @instance_name VARCHAR(100);
DECLARE @tenant_id VARCHAR(50);
DECLARE @sql NVARCHAR(MAX);
DECLARE @linked_server_name NVARCHAR(200);

DECLARE server_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT tenant_id, instance_id, host, instance_name
FROM [metadata].[server_config]
WHERE is_active = 1
ORDER BY priority DESC;

OPEN server_cursor;
FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;

WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        IF @instance_name = '''' OR @instance_name IS NULL
            SET @linked_server_name = @host;
        ELSE
            SET @linked_server_name = @host + ''\\'' + @instance_name;

        PRINT ''Coletando mÃ©tricas de: '' + @linked_server_name;

        SET @sql = N''
        INSERT INTO [WatcherDB_Intelligence].[timeseries].[metrics] 
            (tenant_id, server_id, collector_name, metric_name, metric_value, [timestamp], tags)
        SELECT 
            '''''' + @tenant_id + '''''',
            '''''' + @server_id + '''''',
            ''''performance'''',
            metric_name,
            metric_value,
            SYSUTCDATETIME(),
            tags
        FROM OPENQUERY(['' + @linked_server_name + ''], ''''
            SELECT ''''cpu_percent'''' AS metric_name, CAST(AVG(sqlserver_process_cpu) AS FLOAT) AS metric_value, NULL AS tags
            FROM (SELECT TOP 5 SQLProcessUtilization AS sqlserver_process_cpu
                  FROM (SELECT record.value(''''(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]'''', ''''int'''') AS SQLProcessUtilization, [timestamp]
                        FROM (SELECT [timestamp], CONVERT(XML, record) AS [record] FROM sys.dm_os_ring_buffers 
                              WHERE ring_buffer_type = N''''RING_BUFFER_SCHEDULER_MONITOR'''' AND record LIKE ''''%<SystemHealth>%'''') AS x
                       ) AS y ORDER BY [timestamp] DESC) AS cpu
            UNION ALL
            SELECT ''''memory_percent'''', CAST(100.0 * physical_memory_in_use_kb / total_physical_memory_kb AS FLOAT), NULL FROM sys.dm_os_process_memory
            UNION ALL
            SELECT ''''active_connections'''', CAST(COUNT(*) AS FLOAT), NULL FROM sys.dm_exec_sessions WHERE is_user_process = 1
        '''');
        '';
        EXEC sp_executesql @sql;
    END TRY
    BEGIN CATCH
        PRINT ''ERRO ao coletar de '' + @linked_server_name + '': '' + ERROR_MESSAGE();
    END CATCH;
    FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
END;
CLOSE server_cursor;
DEALLOCATE server_cursor;
',
    @retry_attempts = 2,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Collect_Metrics',
    @name = N'A cada 1 minuto',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 1,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_Metrics',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Collect_Metrics criado (executa a cada 1 minuto)';
GO

-- ============================================================================
-- JOB 5: COLLECT ERROR LOGS
-- ============================================================================
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Collect_ErrorLogs')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Collect_ErrorLogs';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_ErrorLogs',
    @enabled = 1,
    @description = N'Coleta error logs do SQL Server dos servidores monitorados';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_ErrorLogs',
    @step_name = N'Coletar error logs',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'
DECLARE @server_id VARCHAR(100), @host VARCHAR(200), @instance_name VARCHAR(100), @tenant_id VARCHAR(50);
DECLARE @sql NVARCHAR(MAX), @linked_server_name NVARCHAR(200);
DECLARE server_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT tenant_id, instance_id, host, instance_name FROM [metadata].[server_config] WHERE is_active = 1 ORDER BY priority DESC;
OPEN server_cursor;
FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        IF @instance_name = '''' OR @instance_name IS NULL SET @linked_server_name = @host;
        ELSE SET @linked_server_name = @host + ''\\'' + @instance_name;
        PRINT ''Coletando error logs de: '' + @linked_server_name;
        SET @sql = N''INSERT INTO [WatcherDB_Intelligence].[raw].[sql_error_logs] (tenant_id, instance_id, log_date, severity, [message], error_number, is_crash_dump, is_corruption_error)
        SELECT '''''' + @tenant_id + '''''', '''''' + @server_id + '''''', LogDate,
               CASE WHEN [Text] LIKE ''''%error%'''' THEN ''''Error'''' WHEN [Text] LIKE ''''%warning%'''' THEN ''''Warning'''' ELSE ''''Info'''' END,
               [Text], NULL, CASE WHEN [Text] LIKE ''''%dump%'''' THEN 1 ELSE 0 END,
               CASE WHEN [Text] LIKE ''''%corruption%'''' OR [Text] LIKE ''''%824%'''' OR [Text] LIKE ''''%825%'''' THEN 1 ELSE 0 END
        FROM OPENQUERY(['' + @linked_server_name + ''], ''''EXEC sp_readerrorlog 0, 1'''')
        WHERE LogDate >= DATEADD(MINUTE, -10, GETDATE())
        AND NOT EXISTS (SELECT 1 FROM [WatcherDB_Intelligence].[raw].[sql_error_logs] l WHERE l.instance_id = '''''' + @server_id + '''''' AND l.log_date = LogDate AND l.[message] = [Text]);'';
        EXEC sp_executesql @sql;
    END TRY
    BEGIN CATCH
        PRINT ''ERRO: '' + ERROR_MESSAGE();
    END CATCH;
    FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
END;
CLOSE server_cursor;
DEALLOCATE server_cursor;
',
    @retry_attempts = 2,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Collect_ErrorLogs',
    @name = N'A cada 5 minutos',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 5,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_ErrorLogs',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Collect_ErrorLogs criado (executa a cada 5 minutos)';
GO

-- ============================================================================
-- JOB 6: COLLECT ALWAYSON (DESABILITADO - COLETA VIA PYTHON)
-- ============================================================================
-- NOTA: A coleta principal de AlwaysOn agora Ã© feita via Python (collect_data_async.py)
-- que conecta DIRETAMENTE em cada instÃ¢ncia SQL Server.
-- Este job Ã© mantido DESABILITADO como fallback para coleta local.
-- Para habilitar: EXEC msdb.dbo.sp_update_job @job_name = N'WatcherDB_Collect_AlwaysOn', @enabled = 1;
-- ============================================================================
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Collect_AlwaysOn')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Collect_AlwaysOn';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_AlwaysOn',
    @enabled = 0,  -- DESABILITADO - coleta principal via Python
    @description = N'[FALLBACK] Coleta mÃ©tricas de AlwaysOn - DESABILITADO (coleta principal via Python: collect_data_async.py)';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_AlwaysOn',
    @step_name = N'Coletar AlwaysOn health',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'
DECLARE @server_id VARCHAR(100), @host VARCHAR(200), @instance_name VARCHAR(100), @tenant_id VARCHAR(50);
DECLARE @sql NVARCHAR(MAX), @linked_server_name NVARCHAR(200);
DECLARE server_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT tenant_id, instance_id, host, instance_name FROM [metadata].[server_config] WHERE is_active = 1 ORDER BY priority DESC;
OPEN server_cursor;
FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        IF @instance_name = '''' OR @instance_name IS NULL SET @linked_server_name = @host;
        ELSE SET @linked_server_name = @host + ''\\'' + @instance_name;
        SET @sql = N''INSERT INTO [WatcherDB_Intelligence].[raw].[alwayson_health] (tenant_id, instance_id, [timestamp], [role], synchronization_state, log_send_queue_size_kb, redo_queue_size_kb, estimated_data_loss_seconds, is_seeding)
        SELECT '''''' + @tenant_id + '''''', '''''' + @server_id + '''''', GETDATE(), [role], synchronization_state, log_send_queue_size, redo_queue_size, estimated_data_loss, is_seeding
        FROM OPENQUERY(['' + @linked_server_name + ''], ''''SELECT CASE r.role WHEN 1 THEN ''''PRIMARY'''' WHEN 2 THEN ''''SECONDARY'''' ELSE ''''UNKNOWN'''' END AS [role],
               rs.synchronization_state_desc AS synchronization_state, rs.log_send_queue_size, rs.redo_queue_size, rs.estimated_data_loss_time AS estimated_data_loss, CAST(rs.is_seeding AS INT) AS is_seeding
        FROM sys.dm_hadr_database_replica_states rs INNER JOIN sys.availability_replicas r ON rs.replica_id = r.replica_id WHERE rs.is_local = 1'''');'';
        EXEC sp_executesql @sql;
    END TRY
    BEGIN CATCH
        IF ERROR_NUMBER() <> 208 PRINT ''ERRO: '' + ERROR_MESSAGE();
    END CATCH;
    FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
END;
CLOSE server_cursor;
DEALLOCATE server_cursor;
',
    @retry_attempts = 2,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Collect_AlwaysOn',
    @name = N'A cada 1 minuto',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 1,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_AlwaysOn',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Collect_AlwaysOn criado (DESABILITADO - coleta principal via Python)';
GO

-- ============================================================================
-- JOB 7: COLLECT AGENT JOBS
-- ============================================================================
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Collect_AgentJobs')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Collect_AgentJobs';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_AgentJobs',
    @enabled = 1,
    @description = N'Coleta histÃ³rico e status dos SQL Agent Jobs';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_AgentJobs',
    @step_name = N'Coletar SQL Agent Jobs',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'
DECLARE @server_id VARCHAR(100), @host VARCHAR(200), @instance_name VARCHAR(100), @tenant_id VARCHAR(50);
DECLARE @sql NVARCHAR(MAX), @linked_server_name NVARCHAR(200);
DECLARE server_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT tenant_id, instance_id, host, instance_name FROM [metadata].[server_config] WHERE is_active = 1 ORDER BY priority DESC;
OPEN server_cursor;
FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        IF @instance_name = '''' OR @instance_name IS NULL SET @linked_server_name = @host;
        ELSE SET @linked_server_name = @host + ''\\'' + @instance_name;
        SET @sql = N''INSERT INTO [WatcherDB_Intelligence].[raw].[sql_agent_jobs] (tenant_id, instance_id, job_name, job_start_time, job_end_time, job_status, duration_seconds, event_type, event_details)
        SELECT '''''' + @tenant_id + '''''', '''''' + @server_id + '''''', job_name, run_date_time, run_end_time, run_status, run_duration_sec, ''''execution'''', run_message
        FROM OPENQUERY(['' + @linked_server_name + ''], ''''SELECT j.name AS job_name,
               CAST(CAST(h.run_date AS VARCHAR(8)) + '''' '''' + STUFF(STUFF(RIGHT(''''000000'''' + CAST(h.run_time AS VARCHAR(6)), 6), 5, 0, '''':''''), 3, 0, '''':'''') AS DATETIME) AS run_date_time,
               CAST(CAST(h.run_date AS VARCHAR(8)) + '''' '''' + STUFF(STUFF(RIGHT(''''000000'''' + CAST(h.run_time AS VARCHAR(6)), 6), 5, 0, '''':''''), 3, 0, '''':'''') AS DATETIME) AS run_end_time,
               CASE h.run_status WHEN 0 THEN ''''Failed'''' WHEN 1 THEN ''''Succeeded'''' WHEN 2 THEN ''''Retry'''' WHEN 3 THEN ''''Canceled'''' WHEN 4 THEN ''''In Progress'''' END AS run_status,
               (h.run_duration / 10000 * 3600) + ((h.run_duration % 10000) / 100 * 60) + (h.run_duration % 100) AS run_duration_sec, h.message AS run_message
        FROM msdb.dbo.sysjobhistory h INNER JOIN msdb.dbo.sysjobs j ON h.job_id = j.job_id WHERE h.step_id = 0 
        AND CAST(CAST(h.run_date AS VARCHAR(8)) + '''' '''' + STUFF(STUFF(RIGHT(''''000000'''' + CAST(h.run_time AS VARCHAR(6)), 6), 5, 0, '''':''''), 3, 0, '''':'''') AS DATETIME) >= DATEADD(MINUTE, -10, GETDATE())'''')
        WHERE NOT EXISTS (SELECT 1 FROM [WatcherDB_Intelligence].[raw].[sql_agent_jobs] aj WHERE aj.instance_id = '''''' + @server_id + '''''' AND aj.job_name = job_name AND aj.job_start_time = run_date_time);'';
        EXEC sp_executesql @sql;
    END TRY
    BEGIN CATCH
        PRINT ''ERRO: '' + ERROR_MESSAGE();
    END CATCH;
    FETCH NEXT FROM server_cursor INTO @tenant_id, @server_id, @host, @instance_name;
END;
CLOSE server_cursor;
DEALLOCATE server_cursor;
',
    @retry_attempts = 2,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Collect_AgentJobs',
    @name = N'A cada 5 minutos',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 5,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_AgentJobs',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Collect_AgentJobs criado (executa a cada 5 minutos)';
GO

-- ============================================================================
-- JOB 8: COLLECT WINDOWS EVENTS (DESABILITADO)
-- ============================================================================
IF EXISTS (SELECT job_id FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Collect_WinEvents')
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB_Collect_WinEvents';
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_WinEvents',
    @enabled = 0,
    @description = N'Coleta eventos crÃ­ticos do Windows Event Log (DESABILITADO - requer configuraÃ§Ã£o)';
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_WinEvents',
    @step_name = N'Coletar Windows Events',
    @subsystem = N'TSQL',
    @database_name = N'WatcherDB_Intelligence',
    @command = N'PRINT ''Job desabilitado. Configure xp_cmdshell ou PowerShell para habilitar.'';',
    @retry_attempts = 1,
    @retry_interval = 1;
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB_Collect_WinEvents',
    @name = N'A cada 10 minutos',
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 10,
    @active_start_time = 000000,
    @active_end_time = 235959;
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_WinEvents',
    @server_name = N'(local)';
GO

PRINT '  âœ… Job WatcherDB_Collect_WinEvents criado (DESABILITADO)';
GO

-- =============================================
-- STEP 13.5: KPI JOBS (2 JOBS)
-- =============================================

PRINT '';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT ' [13/13] Criando Jobs KPI Oracle (2 jobs)';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';
GO

-- ============================================================================
-- JOB 1: COLETA DE KPIs (A CADA 5 MINUTOS)
-- ============================================================================

PRINT '';
PRINT '-- [1/2] Criando job: WatcherDB_Collect_KPIs...';
PRINT '';
GO

-- Remover job se existir
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = 'WatcherDB_Collect_KPIs')
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = 'WatcherDB_Collect_KPIs';
    PRINT '  [INFO] Job existente removido';
END
GO

-- Criar job
DECLARE @jobId BINARY(16);

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_KPIs',
    @enabled = 1,
    @notify_level_eventlog = 2, -- Erro
    @notify_level_email = 0,
    @notify_level_netsend = 0,
    @notify_level_page = 0,
    @delete_level = 0,
    @description = N'Coleta automÃ¡tica de KPIs SQL Server para WatcherDB Intelligence. Executa a cada 5 minutos.',
    @category_name = N'Database Maintenance',
    @owner_login_name = N'sa',
    @job_id = @jobId OUTPUT;

PRINT '  [OK] Job criado';
GO

-- Adicionar step 1: Executar coleta
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_KPIs',
    @step_name = N'Coletar todos os KPIs',
    @step_id = 1,
    @cmdexec_success_code = 0,
    @on_success_action = 1, -- Quit with success
    @on_fail_action = 2,     -- Quit with failure
    @retry_attempts = 0,
    @retry_interval = 0,
    @os_run_priority = 0,
    @subsystem = N'TSQL',
    @command = N'EXEC [WatcherDB_Intelligence].dbo.usp_Collect_All_KPIs @Debug = 0;',
    @database_name = N'WatcherDB_Intelligence',
    @flags = 0;

PRINT '  [OK] Step de coleta adicionado';
GO

-- Adicionar schedule: A cada 5 minutos
EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Every_5_Minutes_KPI',
    @enabled = 1,
    @freq_type = 4,                 -- Daily
    @freq_interval = 1,             -- Every day
    @freq_subday_type = 4,          -- Minutes
    @freq_subday_interval = 5,      -- Every 5 minutes
    @freq_relative_interval = 0,
    @freq_recurrence_factor = 0,
    @active_start_date = 20251128,  -- Today
    @active_end_date = 99991231,    -- No end date
    @active_start_time = 0,         -- 00:00:00
    @active_end_time = 235959;      -- 23:59:59

PRINT '  [OK] Schedule criado (a cada 5 minutos)';
GO

-- Anexar schedule ao job
EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'WatcherDB_Collect_KPIs',
    @schedule_name = N'Every_5_Minutes_KPI';

PRINT '  [OK] Schedule anexado ao job';
GO

-- Adicionar job ao servidor local
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_KPIs',
    @server_name = N'(local)';

PRINT '  [OK] Job adicionado ao servidor';
PRINT '';
GO

-- ============================================================================
-- JOB 2: LIMPEZA DE HISTÃ“RICO (DIÃRIO Ã€ MEIA-NOITE)
-- ============================================================================

PRINT '';
PRINT '-- [2/2] Criando job: WatcherDB_Purge_History...';
PRINT '';
GO

-- Remover job se existir
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = 'WatcherDB_Purge_History')
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = 'WatcherDB_Purge_History';
    PRINT '  [INFO] Job existente removido';
END
GO

-- Criar job
DECLARE @jobId2 BINARY(16);

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Purge_History',
    @enabled = 1,
    @notify_level_eventlog = 2, -- Erro
    @notify_level_email = 0,
    @notify_level_netsend = 0,
    @notify_level_page = 0,
    @delete_level = 0,
    @description = N'Limpeza de dados histÃ³ricos antigos (> 365 dias) das tabelas HIST. Executa diariamente Ã  meia-noite.',
    @category_name = N'Database Maintenance',
    @owner_login_name = N'sa',
    @job_id = @jobId2 OUTPUT;

PRINT '  [OK] Job criado';
GO

-- Adicionar step 1: Limpar histÃ³rico
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Purge_History',
    @step_name = N'Limpar dados antigos (> 365 dias)',
    @step_id = 1,
    @cmdexec_success_code = 0,
    @on_success_action = 1, -- Quit with success
    @on_fail_action = 2,     -- Quit with failure
    @retry_attempts = 2,
    @retry_interval = 5,
    @os_run_priority = 0,
    @subsystem = N'TSQL',
    @command = N'
-- Limpar histÃ³rico de DB Availability (> 365 dias)
DELETE FROM [WatcherDB_Intelligence].dbo.KPI_MSSQL_DB_AVAILABILITY_HIST
WHERE Update_TS < DATEADD(DAY, -365, GETDATE());
PRINT ''DB Availability: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';

-- Limpar histÃ³rico de Disk Usage (> 365 dias)
DELETE FROM [WatcherDB_Intelligence].dbo.KPI_MSSQL_DISK_USAGE_HIST
WHERE Update_TS < DATEADD(DAY, -365, GETDATE());
PRINT ''Disk Usage: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';

-- Limpar histÃ³rico de TLog Usage (> 365 dias)
DELETE FROM [WatcherDB_Intelligence].dbo.KPI_MSSQL_TLOG_USAGE_HIST
WHERE Update_TS < DATEADD(DAY, -365, GETDATE());
PRINT ''TLog Usage: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';

-- Limpar histÃ³rico de CMDB (> 365 dias)
DELETE FROM [WatcherDB_Intelligence].dbo.CMDB_MSSQL_DATABASES_HIST
WHERE UpdatedAt < DATEADD(DAY, -365, GETDATE());
PRINT ''CMDB: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';
',
    @database_name = N'WatcherDB_Intelligence',
    @flags = 0;

PRINT '  [OK] Step de limpeza adicionado';
GO

-- Adicionar schedule: DiÃ¡rio Ã  meia-noite
EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Daily_Midnight_Purge',
    @enabled = 1,
    @freq_type = 4,                 -- Daily
    @freq_interval = 1,             -- Every day
    @freq_subday_type = 1,          -- At specified time
    @freq_subday_interval = 0,
    @freq_relative_interval = 0,
    @freq_recurrence_factor = 0,
    @active_start_date = 20251128,  -- Today
    @active_end_date = 99991231,    -- No end date
    @active_start_time = 0,         -- 00:00:00 (midnight)
    @active_end_time = 235959;      -- 23:59:59

PRINT '  [OK] Schedule criado (diÃ¡rio Ã  meia-noite)';
GO

-- Anexar schedule ao job
EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'WatcherDB_Purge_History',
    @schedule_name = N'Daily_Midnight_Purge';

PRINT '  [OK] Schedule anexado ao job';
GO

-- Adicionar job ao servidor local
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Purge_History',
    @server_name = N'(local)';

PRINT '  [OK] Job adicionado ao servidor';
PRINT '';
GO

PRINT '';
PRINT '  âœ… 2 Jobs KPI criados!';
PRINT '';
GO

PRINT '';
PRINT '  âœ… Total: 5 SQL Agent Jobs V1 de COLETA criados!';
PRINT '  âœ… Total: 2 SQL Agent Jobs KPI de COLETA criados!';
PRINT '  âœ… TOTAL GERAL: 10 SQL Agent Jobs (3 anÃ¡lise + 5 coleta V1 + 2 coleta KPI)';
PRINT '';
GO

-- =============================================
-- PARTE 4: INSERIR SERVIDORES DO INVENTÃRIO
-- =============================================

USE [WatcherDB_Intelligence];
GO

PRINT '';
PRINT '[13/13] Inserindo 5 Servidores (3 PRODUÃ‡ÃƒO + 2 TEST)...';


-- Limpar servidores existentes (se houver)
DELETE FROM [metadata].[server_config] WHERE tenant_id = 'default';
GO

-- Insert 3 SERVIDORES DE PRODUÃ‡ÃƒO + 2 SERVIDORES DE TEST
INSERT INTO [metadata].[server_config] (
    tenant_id, instance_id, host, instance_name, port,
    environment, priority, description, is_active
)
VALUES
('default', 'SQLHDSPRD212_I01', 'SQLHDSPRD212', 'I01', 1433, 'production', 1, 'SQL Server Production 212', 1),
('default', 'SQLHDSPRD213_I01', 'SQLHDSPRD213', 'I01', 1433, 'production', 1, 'SQL Server Production 213', 1),
('default', 'SQLHDSPRD214_I01', 'SQLHDSPRD214', 'I01', 1433, 'production', 1, 'SQL Server Production 214', 1),
('default', 'SQLHDSTST505_I01', 'SQLHDSTST505', 'I01', 1433, 'test', 1, 'SQL Server Test 212', 1),
('default', 'SQLHDSTST103_I01', 'SQLHDSTST103', 'I01', 1433, 'test', 1, 'SQL Server Test 103', 1);

PRINT '  âœ“ Inseridos 5 servidores (3 produÃ§Ã£o + 2 teste)';
GO

-- =============================================
-- STEP 13.6: MAPEAR SERVIDORES PARA KPI
-- =============================================

PRINT '';
PRINT '[13/13] Mapeando servidores para tabela KPI_MSSQL_INST_ENVS...';
GO

-- Mapear servidores para KPI (pega os 5 servidores inseridos acima)
-- NOTA: As descriÃ§Ãµes sÃ£o copiadas de [metadata].[server_config]
INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env, Description)
SELECT
    instance_id,
    CASE environment
        WHEN 'production' THEN 'PROD'
        WHEN 'development' THEN 'DEV'
        WHEN 'test' THEN 'TEST'
        WHEN 'uat' THEN 'UAT'
        ELSE 'PROD'
    END AS Env,
    ISNULL(description, 'Servidor de teste')
FROM [metadata].[server_config]
WHERE is_active = 1
  AND tenant_id = 'default';

DECLARE @mapped_count INT = @@ROWCOUNT;
PRINT '  âœ“ Mapeamento KPI criado para ' + CAST(@mapped_count AS VARCHAR(10)) + ' servidores';
GO

-- =============================================
-- RESUMO FINAL E VALIDAÃ‡ÃƒO
-- =============================================

USE [WatcherDB_Intelligence];
GO

PRINT '';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT ' VALIDAÃ‡ÃƒO DA INSTALAÃ‡ÃƒO';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';

DECLARE @total_servers INT;
DECLARE @prod_servers INT;
DECLARE @qa_servers INT;
DECLARE @test_servers INT;

SELECT @total_servers = COUNT(*) FROM [metadata].[server_config] WHERE tenant_id = 'default';
SELECT @prod_servers = COUNT(*) FROM [metadata].[server_config] WHERE tenant_id = 'default' AND environment = 'production';
SELECT @qa_servers = COUNT(*) FROM [metadata].[server_config] WHERE tenant_id = 'default' AND environment = 'quality';
SELECT @test_servers = COUNT(*) FROM [metadata].[server_config] WHERE tenant_id = 'default' AND environment = 'test';

PRINT '';
PRINT '  âœ… RESUMO DE SERVIDORES INSERIDOS:';
PRINT '     - Production: ' + CAST(@prod_servers AS VARCHAR(10)) + ' servidores';
PRINT '     - Quality:    ' + CAST(@qa_servers AS VARCHAR(10)) + ' servidores';
PRINT '     - Test:       ' + CAST(@test_servers AS VARCHAR(10)) + ' servidores';
PRINT '     - TOTAL:      ' + CAST(@total_servers AS VARCHAR(10)) + ' servidores';
PRINT '';
GO

-- =============================================
-- VERIFICAÃ‡ÃƒO FINAL COMPLETA
-- =============================================
PRINT '';
PRINT 'â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—';
PRINT 'â•‘                                                                   â•‘';
PRINT 'â•‘              INSTALAÃ‡ÃƒO COMPLETA FINALIZADA!                      â•‘';
PRINT 'â•‘                                                                   â•‘';
PRINT 'â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';

-- VerificaÃ§Ã£o detalhada
DECLARE @filegroups INT, @tables INT, @views INT, @patterns INT, @procedures INT, @jobs INT, @servers INT;

SELECT @filegroups = COUNT(*) FROM sys.filegroups;
SELECT @tables = COUNT(*) FROM sys.tables;
SELECT @views = COUNT(*) FROM sys.views;
SELECT @patterns = COUNT(*) FROM [meta].[patterns];
SELECT @procedures = COUNT(*) FROM sys.procedures WHERE schema_id IN (
    SCHEMA_ID('timeseries'), SCHEMA_ID('meta'), SCHEMA_ID('alerts'), SCHEMA_ID('metadata')
);
SELECT @servers = COUNT(*) FROM [metadata].[server_config];

USE [msdb];
SELECT @jobs = COUNT(*) FROM sysjobs WHERE name LIKE 'WatcherDB%';

USE [WatcherDB_Intelligence];

PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT 'RESUMO DA INSTALAÃ‡ÃƒO - WATCHERDB INTELLIGENCE + KPI ORACLE';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';
PRINT 'DATABASE & ESTRUTURA:';
PRINT '  âœ… Database:           WatcherDB_Intelligence';
PRINT '  âœ… Filegroups:         ' + CAST(@filegroups AS VARCHAR(10)) + ' (PRIMARY + DATA + FG_KPI_DATA + FG_KPI_HIST)';
PRINT '';
PRINT 'OBJETOS V1 (ORIGINAL):';
PRINT '  âœ… Tabelas V1:         20';
PRINT '  âœ… Views V1:           3';
PRINT '  âœ… Procedures V1:      5';
PRINT '  âœ… Jobs V1:            8 (3 anÃ¡lise + 5 coleta)';
PRINT '';
PRINT 'OBJETOS KPI ORACLE (NOVO):';
PRINT '  âœ… Tabelas KPI:        23 (2 Thresholds + 2 CMDB + 14 STG + 1 Backup Failures + 4 HIST + 1 Aux)';
PRINT '  âœ… Views KPI:          34 (14 AGG + 14 DET + 1 CMDB + 2 Service Status + 2 DB I/O Stats + 2 Dashboard)';
PRINT '  âœ… Procedures KPI:     13 (12 coleta + 1 master)';
PRINT '  âœ… Jobs KPI:           2 (1 coleta 5min + 1 purge diÃ¡rio)';
PRINT '';
PRINT 'TOTAIS GERAIS:';
PRINT '  âœ… Tabelas TOTAL:      ' + CAST(@tables AS VARCHAR(10)) + ' (20 V1 + 22 KPI)';
PRINT '  âœ… Views TOTAL:        ' + CAST(@views AS VARCHAR(10)) + ' (3 V1 + 34 KPI)';
PRINT '  âœ… Procedures TOTAL:   ' + CAST(@procedures AS VARCHAR(10)) + ' (5 V1 + 14 KPI)';
PRINT '  âœ… Jobs TOTAL:         ' + CAST(@jobs AS VARCHAR(10)) + ' (8 V1 + 2 KPI)';
PRINT '  âœ… Patterns:           ' + CAST(@patterns AS VARCHAR(10));
PRINT '  âœ… Servidores:         ' + CAST(@servers AS VARCHAR(10)) + ' (3 produÃ§Ã£o)';
PRINT '';
PRINT 'â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_metrics_analytics')
    PRINT '  âœ… Columnstore Index:  ATIVO (otimizaÃ§Ã£o para analytics)';

PRINT '';
PRINT 'â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—';
PRINT 'â•‘                     PRÃ“XIMOS PASSOS                               â•‘';
PRINT 'â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•';
PRINT '';
PRINT 'ðŸ“Š TESTAR COLETA KPI ORACLE (NOVO):';
PRINT '   -- Executar coleta manual com debug:';
PRINT '   EXEC [WatcherDB_Intelligence].dbo.usp_Collect_All_KPIs @Debug = 1;';
PRINT '';
PRINT '   -- Verificar dados coletados:';
PRINT '   SELECT * FROM [WatcherDB_Intelligence].dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;';
PRINT '   SELECT * FROM [WatcherDB_Intelligence].dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;';
PRINT '   SELECT * FROM [WatcherDB_Intelligence].dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW;';
PRINT '';
PRINT '   -- Verificar job automÃ¡tico (executa a cada 5 minutos):';
PRINT '   EXEC msdb.dbo.sp_help_job @job_name = ''WatcherDB_Collect_KPIs'';';
PRINT '';
PRINT '   -- Executar job manualmente:';
PRINT '   EXEC msdb.dbo.sp_start_job @job_name = ''WatcherDB_Collect_KPIs'';';
PRINT '';
PRINT '1. Configure o Backend Python:';
PRINT '   cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"';
PRINT '   python -m venv venv';
PRINT '   venv\Scripts\Activate.ps1';
PRINT '   pip install -r requirements.txt';
PRINT '   copy .env.example .env';
PRINT '   # Editar .env com suas credenciais';
PRINT '';
PRINT '2. Inicie a API:';
PRINT '   python -m watcherdb_intelligence.main';
PRINT '';
PRINT '3. Acesse o Swagger UI:';
PRINT '   http://localhost:8000/api/docs';
PRINT '';
PRINT '4. Execute testes:';
PRINT '   python test_complete_system.py';
PRINT '';
PRINT 'DocumentaÃ§Ã£o completa: DEPLOYMENT_CHECKLIST.md';
PRINT '';
-- ============================================================================
-- [18/18] NORMALIZAÃ‡ÃƒO DE NOMES DE INSTÃ‚NCIAS
-- ============================================================================
-- Garante que todos os nomes de instÃ¢ncias usem underscore (_) em vez de backslash (\)
-- Isso mantÃ©m consistÃªncia com o formato do server_id no config/servers.json
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT '[18/18] CRIANDO PROCEDURE DE NORMALIZAÃ‡ÃƒO DE NOMES DE INSTÃ‚NCIAS';
PRINT '============================================================================';
GO

IF OBJECT_ID('dbo.usp_Normalize_Instance_Names', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Normalize_Instance_Names;
GO

CREATE PROCEDURE dbo.usp_Normalize_Instance_Names
    @DryRun BIT = 0  -- Se 1, apenas mostra o que seria alterado sem fazer UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @RowsAffected INT = 0;
    DECLARE @TotalRows INT = 0;
    DECLARE @TableName NVARCHAR(128);
    DECLARE @SQL NVARCHAR(MAX);
    
    -- Lista de tabelas STG que contÃªm coluna Instance
    DECLARE @Tables TABLE (
        TableName NVARCHAR(128),
        DisplayName NVARCHAR(200)
    );
    
    INSERT INTO @Tables VALUES
        ('KPI_MSSQL_INST_AVAILABILITY_STG', 'Instance Availability'),
        ('KPI_MSSQL_PROCESSES_STG', 'Processes'),
        ('KPI_MSSQL_DISK_USAGE_STG', 'Disk Usage'),
        ('KPI_MSSQL_FG_USAGE_STG', 'Filegroup Usage'),
        ('KPI_MSSQL_TLOG_USAGE_STG', 'Transaction Log Usage'),
        ('KPI_MSSQL_BACKUPS_STG', 'Backups'),
        ('KPI_MSSQL_DB_AVAILABILITY_STG', 'Database Availability'),
        ('KPI_MSSQL_DB_IO_STATS_STG', 'Database I/O Stats'),
        ('KPI_MSSQL_BLOCKED_SESSIONS_STG', 'Blocked Sessions'),
        ('KPI_MSSQL_ALWAYSON_STATUS_STG', 'AlwaysOn Status'),
        ('KPI_MSSQL_LONG_LOCKS_STG', 'Long Locks'),
        ('KPI_MSSQL_BLOCKED_USERS_STG', 'Blocked Users'),
        ('KPI_MSSQL_DEADLOCKS_STG', 'Deadlocks'),
        ('KPI_MSSQL_ERRORLOG_STG', 'Error Log'),
        ('KPI_MSSQL_SERVICE_STATUS_STG', 'Service Status');
    
    IF @DryRun = 1
    BEGIN
        PRINT '============================================================================';
        PRINT 'MODO DRY-RUN: Apenas verificando dados que seriam normalizados';
        PRINT '============================================================================';
        PRINT '';
    END
    ELSE
    BEGIN
        PRINT '============================================================================';
        PRINT 'NORMALIZANDO NOMES DE INSTÃ‚NCIAS (substituindo \ por _)';
        PRINT '============================================================================';
        PRINT '';
        BEGIN TRANSACTION;
    END
    
    BEGIN TRY
        DECLARE table_cursor CURSOR FOR
        SELECT TableName, DisplayName FROM @Tables;
        
        OPEN table_cursor;
        FETCH NEXT FROM table_cursor INTO @TableName, @DisplayName;
        
        WHILE @@FETCH_STATUS = 0
        BEGIN
            -- Se DryRun, apenas contar
            IF @DryRun = 1
            BEGIN
                SET @SQL = N'
                    IF OBJECT_ID(''dbo.' + @TableName + ''', ''U'') IS NOT NULL
                    BEGIN
                        DECLARE @Count INT;
                        SELECT @Count = COUNT(*) 
                        FROM dbo.' + @TableName + N' 
                        WHERE Instance LIKE ''%\%'';
                        
                        IF @Count > 0
                        BEGIN
                            PRINT ''  ' + @DisplayName + N': '' + CAST(@Count AS VARCHAR(10)) + '' registros com backslash'';
                        END
                    END';
                
                EXEC sp_executesql @SQL;
            END
            ELSE
            BEGIN
                -- Primeiro contar quantos registros serÃ£o afetados
                DECLARE @CountBefore INT = 0;
                SET @SQL = N'
                    IF OBJECT_ID(''dbo.' + @TableName + ''', ''U'') IS NOT NULL
                    BEGIN
                        SELECT @CountBefore = COUNT(*) 
                        FROM dbo.' + @TableName + N' 
                        WHERE Instance LIKE ''%\%'';
                    END';
                
                EXEC sp_executesql @SQL, N'@CountBefore INT OUTPUT', @CountBefore = @CountBefore OUTPUT;
                
                -- Se houver registros para normalizar, fazer UPDATE
                IF @CountBefore > 0
                BEGIN
                    SET @SQL = N'
                        IF OBJECT_ID(''dbo.' + @TableName + ''', ''U'') IS NOT NULL
                        BEGIN
                            UPDATE dbo.' + @TableName + N'
                            SET Instance = REPLACE(Instance, ''\'', ''_'')
                            WHERE Instance LIKE ''%\%'';
                        END';
                    
                    EXEC sp_executesql @SQL;
                    
                    PRINT '  âœ“ ' + @DisplayName + ': ' + CAST(@CountBefore AS VARCHAR(10)) + ' registros normalizados';
                    SET @TotalRows = @TotalRows + @CountBefore;
                END
            END
            
            FETCH NEXT FROM table_cursor INTO @TableName, @DisplayName;
        END
        
        CLOSE table_cursor;
        DEALLOCATE table_cursor;
        
        IF @DryRun = 0
        BEGIN
            COMMIT TRANSACTION;
            
            PRINT '';
            PRINT '============================================================================';
            PRINT 'NORMALIZAÃ‡ÃƒO CONCLUÃDA!';
            PRINT '============================================================================';
            PRINT 'Total de registros normalizados: ' + CAST(@TotalRows AS VARCHAR(10));
            PRINT '';
        END
        ELSE
        BEGIN
            PRINT '';
            PRINT '============================================================================';
            PRINT 'VERIFICAÃ‡ÃƒO CONCLUÃDA (DRY-RUN)';
            PRINT '============================================================================';
            PRINT 'Execute sem @DryRun = 1 para normalizar os dados.';
            PRINT '';
        END
    END TRY
    BEGIN CATCH
        IF @DryRun = 0
        BEGIN
            IF @@TRANCOUNT > 0
                ROLLBACK TRANSACTION;
        END
        
        PRINT '';
        PRINT '============================================================================';
        PRINT 'ERRO DURANTE A NORMALIZAÃ‡ÃƒO:';
        PRINT '============================================================================';
        PRINT ERROR_MESSAGE();
        PRINT '';
        
        IF @DryRun = 0
        BEGIN
            PRINT 'ROLLBACK EXECUTADO - Nenhuma alteraÃ§Ã£o foi feita.';
        END
        
        PRINT '============================================================================';
        
        THROW;
    END CATCH
END;
GO

PRINT 'âœ“ Procedure usp_Normalize_Instance_Names criada com sucesso!';
PRINT '';
GO

-- =============================================
-- PROCEDURE: usp_truncate_stg_tables
-- =============================================
-- Trunca todas as tabelas STG de KPIs de forma rÃ¡pida e segura
-- Executa com permissÃµes do owner (dbo), permitindo TRUNCATE mesmo sem ALTER

PRINT '';
PRINT '[19/19] Criando Procedure: usp_truncate_stg_tables...';
PRINT '============================================================================';
GO

IF OBJECT_ID('dbo.usp_truncate_stg_tables', 'P') IS NOT NULL
BEGIN
    DROP PROCEDURE dbo.usp_truncate_stg_tables;
END
GO

CREATE PROCEDURE dbo.usp_truncate_stg_tables
    @kpi_list NVARCHAR(MAX) = NULL
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @table_name NVARCHAR(128);
    DECLARE @sql NVARCHAR(MAX);
    DECLARE @truncated_count INT = 0;
    DECLARE @failed_tables NVARCHAR(MAX) = '';
    DECLARE @error_number INT;
    DECLARE @error_message NVARCHAR(4000);
    DECLARE @error_severity INT;
    DECLARE @error_state INT;
    
    -- Lista de todas as tabelas STG (KPIs ativos)
    DECLARE @tables TABLE (table_name NVARCHAR(128));
    
    INSERT INTO @tables (table_name) VALUES
        ('KPI_MSSQL_ALWAYSON_STATUS_STG'),
        ('KPI_MSSQL_BLOCKED_SESSIONS_STG'),
        ('KPI_MSSQL_BLOCKED_USERS_STG'),
        ('KPI_MSSQL_DB_AVAILABILITY_STG'),
        ('KPI_MSSQL_DISK_USAGE_STG'),
        ('KPI_MSSQL_FG_USAGE_STG'),
        ('KPI_MSSQL_INST_AVAILABILITY_STG'),
        ('KPI_MSSQL_PROCESSES_STG'),
        ('KPI_MSSQL_TLOG_USAGE_STG'),
        ('KPI_MSSQL_BACKUPS_STG');
    
    -- Se lista de KPIs fornecida, filtrar tabelas
    IF @kpi_list IS NOT NULL AND LEN(LTRIM(RTRIM(@kpi_list))) > 0
    BEGIN
        -- Mapeamento KPI -> Tabela
        DECLARE @kpi_table_map TABLE (kpi_name NVARCHAR(128), table_name NVARCHAR(128));
        INSERT INTO @kpi_table_map VALUES
            ('alwayson_status', 'KPI_MSSQL_ALWAYSON_STATUS_STG'),
            ('blocked_sessions', 'KPI_MSSQL_BLOCKED_SESSIONS_STG'),
            ('blocked_users', 'KPI_MSSQL_BLOCKED_USERS_STG'),
            ('db_availability', 'KPI_MSSQL_DB_AVAILABILITY_STG'),
            ('disk_usage', 'KPI_MSSQL_DISK_USAGE_STG'),
            ('filegroup_usage', 'KPI_MSSQL_FG_USAGE_STG'),
            ('instance_availability', 'KPI_MSSQL_INST_AVAILABILITY_STG'),
            ('processes', 'KPI_MSSQL_PROCESSES_STG'),
            ('tlog_usage', 'KPI_MSSQL_TLOG_USAGE_STG'),
            ('backups', 'KPI_MSSQL_BACKUPS_STG');
        
        -- Filtrar apenas tabelas correspondentes aos KPIs solicitados
        DELETE FROM @tables
        WHERE table_name NOT IN (
            SELECT m.table_name 
            FROM @kpi_table_map m
            INNER JOIN STRING_SPLIT(@kpi_list, ',') s ON LTRIM(RTRIM(s.value)) = m.kpi_name
        );
    END
    
    -- Configurar timeout global (30 segundos) para evitar travamentos
    SET LOCK_TIMEOUT 30000;
    
    DECLARE @error_msg NVARCHAR(MAX);
    
    -- Cursor LOCAL FAST_FORWARD (otimizado, nÃ£o bloqueia, mais rÃ¡pido)
    -- IMPORTANTE: LOCAL garante que o cursor Ã© fechado mesmo em caso de erro
    -- FAST_FORWARD otimiza performance e evita locks desnecessÃ¡rios
    DECLARE table_cursor CURSOR LOCAL FAST_FORWARD READ_ONLY FOR
        SELECT table_name FROM @tables;
    
    BEGIN TRY
        OPEN table_cursor;
        FETCH NEXT FROM table_cursor INTO @table_name;
        
        WHILE @@FETCH_STATUS = 0
        BEGIN
            BEGIN TRY
                -- Verificar se tabela existe
                IF OBJECT_ID('dbo.' + @table_name, 'U') IS NOT NULL
                BEGIN
                    -- Configurar timeout para esta operaÃ§Ã£o especÃ­fica (10 segundos por tabela)
                    SET LOCK_TIMEOUT 10000;
                    
                    -- TRUNCATE Ã© muito mais rÃ¡pido que DELETE
                    SET @sql = N'TRUNCATE TABLE dbo.' + QUOTENAME(@table_name);
                    EXEC sp_executesql @sql;
                    
                    SET @truncated_count = @truncated_count + 1;
                END
            END TRY
            BEGIN CATCH
                -- Capturar erro do TRUNCATE
                SET @error_msg = ERROR_MESSAGE();
                
                -- Se TRUNCATE falhar, tentar DELETE como fallback
                BEGIN TRY
                    SET LOCK_TIMEOUT 10000;  -- Timeout de 10 segundos para DELETE tambÃ©m
                    SET @sql = N'DELETE FROM dbo.' + QUOTENAME(@table_name);
                    EXEC sp_executesql @sql;
                    SET @truncated_count = @truncated_count + 1;
                END TRY
                BEGIN CATCH
                    -- Se ambos falharem, registrar erro (mas continuar)
                    SET @failed_tables = @failed_tables + @table_name + ', ';
                END CATCH
            END CATCH
            
            FETCH NEXT FROM table_cursor INTO @table_name;
        END
    END TRY
    BEGIN CATCH
        -- Em caso de erro crÃ­tico, garantir que cursor seja fechado
        IF CURSOR_STATUS('local', 'table_cursor') >= 0
        BEGIN
            IF CURSOR_STATUS('local', 'table_cursor') > -1
            BEGIN
                CLOSE table_cursor;
            END
            DEALLOCATE table_cursor;
        END
        
        -- Re-lanÃ§ar erro para que o Python possa capturar
        -- IMPORTANTE: Usar variÃ¡veis jÃ¡ declaradas (nÃ£o usar DECLARE no CATCH)
        -- e usar RAISERROR para compatibilidade com todas as versÃµes do SQL Server
        SET @error_message = ERROR_MESSAGE();
        SET @error_severity = ERROR_SEVERITY();
        SET @error_state = ERROR_STATE();
        
        RAISERROR(@error_message, @error_severity, @error_state);
        RETURN;
    END CATCH
    
    -- Garantir fechamento do cursor (mesmo se nÃ£o houver erro)
    IF CURSOR_STATUS('local', 'table_cursor') >= 0
    BEGIN
        IF CURSOR_STATUS('local', 'table_cursor') > -1
        BEGIN
            CLOSE table_cursor;
        END
        DEALLOCATE table_cursor;
    END
    
    -- Retornar resultado
    SELECT 
        @truncated_count AS truncated_count,
        CASE 
            WHEN LEN(@failed_tables) > 0 
            THEN LEFT(@failed_tables, LEN(@failed_tables) - 1)
            ELSE NULL
        END AS failed_tables;
END;
GO

PRINT 'âœ“ Procedure usp_truncate_stg_tables criada com sucesso!';
PRINT '';

-- Conceder permissÃ£o EXECUTE para o usuÃ¡rio que executa a coleta
GRANT EXECUTE ON dbo.usp_truncate_stg_tables TO [sql_monitoring];
GRANT EXECUTE ON dbo.fn_get_kpi_collection_target TO [sql_monitoring];
GRANT EXECUTE ON dbo.usp_swap_kpi_stg_tables TO [sql_monitoring];
GO

PRINT 'âœ“ PermissÃ£o EXECUTE concedida para [sql_monitoring] em procedures e functions';
PRINT '';
GO

-- ============================================================================
-- PERMISSÃ•ES ALTER PARA TRUNCATE NAS TABELAS STG
-- ============================================================================
-- NOTA: ALTER Ã© necessÃ¡rio para executar TRUNCATE TABLE diretamente
-- Isso permite que o Python use TRUNCATE (mais rÃ¡pido) ao invÃ©s de DELETE
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT 'CONCEDENDO PERMISSÃ•ES ALTER NAS TABELAS STG';
PRINT '============================================================================';

GRANT ALTER ON dbo.KPI_MSSQL_ALWAYSON_STATUS_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_BLOCKED_USERS_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_DB_AVAILABILITY_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_DISK_USAGE_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_FG_USAGE_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_INST_AVAILABILITY_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_PROCESSES_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_TLOG_USAGE_STG TO [sql_monitoring];
GRANT ALTER ON dbo.KPI_MSSQL_BACKUPS_STG TO [sql_monitoring];
GO

PRINT 'âœ“ PermissÃµes ALTER concedidas para [sql_monitoring] em 10 tabelas STG';
PRINT '';
GO

-- Executar normalizaÃ§Ã£o apÃ³s instalaÃ§Ã£o (se houver dados)
PRINT '============================================================================';
PRINT 'EXECUTANDO NORMALIZAÃ‡ÃƒO INICIAL (se necessÃ¡rio)';
PRINT '============================================================================';
GO

-- Verificar se hÃ¡ dados para normalizar antes de executar
DECLARE @HasDataToNormalize BIT = 0;

IF EXISTS (
    SELECT 1 
    FROM (
        SELECT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_PROCESSES_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_TLOG_USAGE_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        UNION ALL
        SELECT Instance FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) WHERE Instance LIKE '%\%'
        -- KPIs removidos: DB_IO_STATS, LONG_LOCKS, DEADLOCKS, ERRORLOG, SERVICE_STATUS
    ) AS AllInstances
)
BEGIN
    SET @HasDataToNormalize = 1;
END

IF @HasDataToNormalize = 1
BEGIN
    PRINT 'Dados com backslash encontrados. Normalizando...';
    PRINT '';
    EXEC dbo.usp_Normalize_Instance_Names @DryRun = 0;
END
ELSE
BEGIN
    PRINT 'Nenhum dado com backslash encontrado. NormalizaÃ§Ã£o nÃ£o necessÃ¡ria.';
    PRINT '';
    PRINT 'NOTA: Para verificar se hÃ¡ dados para normalizar no futuro, execute:';
    PRINT '  EXEC dbo.usp_Normalize_Instance_Names @DryRun = 1;';
    PRINT '';
    PRINT 'Para normalizar dados existentes, execute:';
    PRINT '  EXEC dbo.usp_Normalize_Instance_Names @DryRun = 0;';
    PRINT '';
END
GO

-- ============================================================================
-- INFRAESTRUTURA DE HISTÃ“RICO DE FILEGROUPS (Sprint 4)
-- ============================================================================
-- Data: 2025-12-11
-- Objetivo: Armazenar dados histÃ³ricos de uso de filegroups para anÃ¡lise preditiva
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'CRIANDO INFRAESTRUTURA DE HISTÃ“RICO DE FILEGROUPS';
PRINT '============================================================================';
GO

-- 1. CRIAR TABELA DE HISTÃ“RICO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_FG_USAGE_HIST')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_FG_USAGE_HIST (
        ID              BIGINT IDENTITY(1,1) NOT NULL,
        Instance        VARCHAR(64)   NOT NULL,
        [Database]      VARCHAR(128)  NOT NULL,
        Filegroup       VARCHAR(128)  NOT NULL,
        Total_MB        DECIMAL(18,2) NULL,
        Used_MB         DECIMAL(18,2) NULL,
        Free_MB         DECIMAL(18,2) NULL,
        Percent_Used    DECIMAL(5,2)  NULL,
        Collect_Date    DATE          NOT NULL,  -- Data da coleta (agregaÃ§Ã£o diÃ¡ria)
        Collect_TS      DATETIME2     NOT NULL,  -- Timestamp exato da coleta
        Insert_TS       DATETIME2     NOT NULL DEFAULT GETDATE(),

        CONSTRAINT PK_FG_USAGE_HIST PRIMARY KEY CLUSTERED (ID),
        CONSTRAINT UQ_FG_USAGE_HIST UNIQUE NONCLUSTERED (Instance, [Database], Filegroup, Collect_Date)
    );

    PRINT 'âœ“ Tabela KPI_MSSQL_FG_USAGE_HIST criada';
END
ELSE
BEGIN
    PRINT 'âš  Tabela KPI_MSSQL_FG_USAGE_HIST jÃ¡ existe';
END
GO

-- 2. CRIAR ÃNDICES PARA PERFORMANCE
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FG_USAGE_HIST_Instance_Date')
BEGIN
    CREATE NONCLUSTERED INDEX IX_FG_USAGE_HIST_Instance_Date
        ON dbo.KPI_MSSQL_FG_USAGE_HIST (Instance, [Database], Filegroup, Collect_Date DESC)
        INCLUDE (Total_MB, Used_MB, Percent_Used);

    PRINT 'âœ“ Ãndice IX_FG_USAGE_HIST_Instance_Date criado';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FG_USAGE_HIST_Date')
BEGIN
    CREATE NONCLUSTERED INDEX IX_FG_USAGE_HIST_Date
        ON dbo.KPI_MSSQL_FG_USAGE_HIST (Collect_Date DESC)
        INCLUDE (Instance, [Database], Filegroup);

    PRINT 'âœ“ Ãndice IX_FG_USAGE_HIST_Date criado';
END
GO

-- 3. STORED PROCEDURE: ARQUIVAR DADOS APÃ“S SWAP
-- NOTA: Usa ROW_NUMBER para eliminar duplicatas na STG antes do MERGE
PRINT '';
PRINT 'Criando stored procedure usp_archive_filegroup_usage...';
GO

CREATE OR ALTER PROCEDURE dbo.usp_archive_filegroup_usage
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @rows_inserted INT = 0;
    DECLARE @start_time DATETIME2 = GETDATE();

    BEGIN TRY
        -- UPSERT com deduplicaÃ§Ã£o: Usa ROW_NUMBER para pegar apenas o registro mais recente
        -- de cada combinaÃ§Ã£o (Instance, Database, Filegroup, Data) da STG
        MERGE INTO dbo.KPI_MSSQL_FG_USAGE_HIST AS target
        USING (
            -- CTE para eliminar duplicatas na STG (pegar mais recente de cada combinaÃ§Ã£o)
            SELECT
                Instance,
                [Database],
                Filegroup,
                Total_MB,
                Used_MB,
                Free_MB,
                Percent_Used,
                Collect_Date,
                Collect_TS
            FROM (
                SELECT
                    Instance,
                    [Database],
                    Filegroup,
                    Total_MB,
                    Used_MB,
                    Free_MB,
                    Percent_Used,
                    CAST(Update_TS AS DATE) AS Collect_Date,
                    Update_TS AS Collect_TS,
                    ROW_NUMBER() OVER (
                        PARTITION BY Instance, [Database], Filegroup, CAST(Update_TS AS DATE)
                        ORDER BY Update_TS DESC
                    ) AS rn
                FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK)
                WHERE Update_TS IS NOT NULL
            ) AS dedup
            WHERE rn = 1  -- Apenas o registro mais recente de cada combinaÃ§Ã£o
        ) AS source
        ON target.Instance = source.Instance
           AND target.[Database] = source.[Database]
           AND target.Filegroup = source.Filegroup
           AND target.Collect_Date = source.Collect_Date
        WHEN MATCHED THEN
            UPDATE SET
                target.Total_MB = source.Total_MB,
                target.Used_MB = source.Used_MB,
                target.Free_MB = source.Free_MB,
                target.Percent_Used = source.Percent_Used,
                target.Collect_TS = source.Collect_TS
        WHEN NOT MATCHED THEN
            INSERT (Instance, [Database], Filegroup, Total_MB, Used_MB, Free_MB, Percent_Used, Collect_Date, Collect_TS)
            VALUES (source.Instance, source.[Database], source.Filegroup, source.Total_MB, source.Used_MB, source.Free_MB, source.Percent_Used, source.Collect_Date, source.Collect_TS);

        SET @rows_inserted = @@ROWCOUNT;

        DECLARE @duration_ms INT = DATEDIFF(MILLISECOND, @start_time, GETDATE());
        DECLARE @msg NVARCHAR(500) = CONCAT('âœ“ HistÃ³rico arquivado: ', @rows_inserted, ' registros em ', @duration_ms, ' ms');
        PRINT @msg;

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_PROCESSING_LOG')
        BEGIN
            INSERT INTO dbo.KPI_PROCESSING_LOG (Process_Name, Status, Records_Processed, Duration_MS, Message)
            VALUES ('usp_archive_filegroup_usage', 'SUCCESS', @rows_inserted, @duration_ms, @msg);
        END

    END TRY
    BEGIN CATCH
        DECLARE @error_msg NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @error_severity INT = ERROR_SEVERITY();
        DECLARE @error_state INT = ERROR_STATE();
        PRINT CONCAT('âœ— ERRO: ', @error_msg);

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_PROCESSING_LOG')
        BEGIN
            INSERT INTO dbo.KPI_PROCESSING_LOG (Process_Name, Status, Records_Processed, Duration_MS, Message)
            VALUES ('usp_archive_filegroup_usage', 'ERROR', 0, DATEDIFF(MILLISECOND, @start_time, GETDATE()), @error_msg);
        END

        RAISERROR(@error_msg, @error_severity, @error_state);
    END CATCH
END;
GO

PRINT 'âœ“ Stored procedure usp_archive_filegroup_usage criada';
GO

-- 4. STORED PROCEDURE: LIMPEZA DE DADOS ANTIGOS
PRINT '';
PRINT 'Criando stored procedure usp_cleanup_old_filegroup_history...';
GO

CREATE OR ALTER PROCEDURE dbo.usp_cleanup_old_filegroup_history
    @retention_days INT = 180  -- PadrÃ£o: 6 meses
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @cutoff_date DATE = DATEADD(DAY, -@retention_days, GETDATE());
    DECLARE @rows_deleted INT = 0;
    DECLARE @start_time DATETIME2 = GETDATE();

    BEGIN TRY
        DELETE FROM dbo.KPI_MSSQL_FG_USAGE_HIST WITH (NOLOCK)
        WHERE Collect_Date < @cutoff_date;

        SET @rows_deleted = @@ROWCOUNT;

        DECLARE @duration_ms INT = DATEDIFF(MILLISECOND, @start_time, GETDATE());
        DECLARE @msg NVARCHAR(500) = CONCAT('âœ“ Limpeza: ', @rows_deleted, ' registros removidos (> ', @retention_days, ' dias) em ', @duration_ms, ' ms');
        PRINT @msg;

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_PROCESSING_LOG')
        BEGIN
            INSERT INTO dbo.KPI_PROCESSING_LOG (Process_Name, Status, Records_Processed, Duration_MS, Message)
            VALUES ('usp_cleanup_old_filegroup_history', 'SUCCESS', @rows_deleted, @duration_ms, @msg);
        END

    END TRY
    BEGIN CATCH
        DECLARE @error_msg NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @error_severity INT = ERROR_SEVERITY();
        DECLARE @error_state INT = ERROR_STATE();
        PRINT CONCAT('âœ— ERRO: ', @error_msg);

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_PROCESSING_LOG')
        BEGIN
            INSERT INTO dbo.KPI_PROCESSING_LOG (Process_Name, Status, Records_Processed, Duration_MS, Message)
            VALUES ('usp_cleanup_old_filegroup_history', 'ERROR', 0, DATEDIFF(MILLISECOND, @start_time, GETDATE()), @error_msg);
        END

        RAISERROR(@error_msg, @error_severity, @error_state);
    END CATCH
END;
GO

PRINT 'âœ“ Stored procedure usp_cleanup_old_filegroup_history criada';
GO

-- 5. VIEW PARA ANÃLISE AGREGADA
PRINT '';
PRINT 'Criando view vw_KPI_MSSQL_FG_USAGE_HIST_AGG...';
GO

CREATE OR ALTER VIEW dbo.vw_KPI_MSSQL_FG_USAGE_HIST_AGG
AS
SELECT
    Instance,
    [Database],
    Filegroup,
    Collect_Date,
    Total_MB,
    Used_MB,
    Free_MB,
    Percent_Used,
    -- Crescimento diÃ¡rio (MB)
    Used_MB - LAG(Used_MB) OVER (PARTITION BY Instance, [Database], Filegroup ORDER BY Collect_Date) AS Daily_Growth_MB,
    -- Crescimento percentual
    CASE
        WHEN LAG(Used_MB) OVER (PARTITION BY Instance, [Database], Filegroup ORDER BY Collect_Date) > 0
        THEN ((Used_MB - LAG(Used_MB) OVER (PARTITION BY Instance, [Database], Filegroup ORDER BY Collect_Date)) /
              LAG(Used_MB) OVER (PARTITION BY Instance, [Database], Filegroup ORDER BY Collect_Date)) * 100
        ELSE NULL
    END AS Daily_Growth_Percent,
    -- MÃ©dia mÃ³vel 7 dias
    AVG(Used_MB) OVER (PARTITION BY Instance, [Database], Filegroup ORDER BY Collect_Date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS Avg_7Days_Used_MB,
    -- MÃ©dia mÃ³vel 30 dias
    AVG(Used_MB) OVER (PARTITION BY Instance, [Database], Filegroup ORDER BY Collect_Date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS Avg_30Days_Used_MB
FROM dbo.KPI_MSSQL_FG_USAGE_HIST;
GO

PRINT 'âœ“ View vw_KPI_MSSQL_FG_USAGE_HIST_AGG criada';
GO

-- 6. PERMISSÃ•ES PARA STORED PROCEDURES DE HISTÃ“RICO
GRANT EXECUTE ON dbo.usp_archive_filegroup_usage TO [sql_monitoring];
GRANT EXECUTE ON dbo.usp_cleanup_old_filegroup_history TO [sql_monitoring];
GRANT SELECT ON dbo.vw_KPI_MSSQL_FG_USAGE_HIST_AGG TO [sql_monitoring];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.KPI_MSSQL_FG_USAGE_HIST TO [sql_monitoring];
GO

PRINT 'âœ“ PermissÃµes concedidas para [sql_monitoring] nos objetos de histÃ³rico';
PRINT '';
PRINT '============================================================================';
PRINT 'INFRAESTRUTURA DE HISTÃ“RICO CRIADA COM SUCESSO!';
PRINT '============================================================================';
PRINT '';
GO

PRINT 'âœ“ INSTALAÃ‡ÃƒO CONCLUÃDA COM SUCESSO!';
PRINT '';

-- =============================================
-- CORREÃ‡Ã•ES DE BUGS IMPLEMENTADAS (Sprint 1)
-- =============================================
-- Data: 2025-12-04
--
-- As seguintes correÃ§Ãµes foram implementadas no cÃ³digo Python:
--
-- 1. DELETE FALLBACK PARA TRUNCATE:
--    - Problema: TRUNCATE TABLE falha sem permissÃ£o ALTER
--    - SoluÃ§Ã£o: Implementado fallback automÃ¡tico para DELETE FROM
--    - Arquivo: watcherdb_intelligence/collectors/storage.py (linhas 90-115)
--
-- 2. ERRORLOG_STG NÃƒO EXISTE NOS SERVIDORES MONITORADOS:
--    - Problema: 332 erros (97% dos erros) tentando ler KPI_MSSQL_ERRORLOG_STG do servidor remoto
--    - Causa: Tabela STG sÃ³ existe no servidor MESTRE, nÃ£o nos servidores monitorados
--    - SoluÃ§Ã£o: Removido fallback invÃ¡lido que tentava ler da tabela inexistente
--    - Arquivo: watcherdb_intelligence/collectors/data_collector.py (linhas 941-950)
--
-- 3. AVAILABILITY GROUPS EM SQL SERVER < 2012:
--    - Problema: sys.availability_groups nÃ£o existe em SQL Server 2000-2008R2
--    - SoluÃ§Ã£o: Adicionada verificaÃ§Ã£o de versÃ£o (skip se < versÃ£o 11)
--    - Arquivo: watcherdb_intelligence/collectors/data_collector.py (linhas 614-623)
--
-- 4. PRIMARY KEY VIOLATION EM LONG_LOCKS_STG:
--    - Problema: ViolaÃ§Ã£o de PK ao inserir dados quando TRUNCATE falha
--    - Chave: (Instance, Session_Id, Update_TS)
--    - SoluÃ§Ã£o: DELETE fallback (#1) resolve completamente este problema
--    - Tabela afetada: dbo.KPI_MSSQL_LONG_LOCKS_STG
--
-- RESULTADO ESPERADO:
--   - Taxa de sucesso: 97.67% (84 de 86 servidores)
--   - ReduÃ§Ã£o de erros: De 341 erros para ~9 erros esperados
--   - Erros restantes: Apenas servidores realmente indisponÃ­veis
--
-- NOTAS IMPORTANTES:
--   - TRUNCATE requer permissÃ£o ALTER na tabela
--   - Se usuÃ¡rio nÃ£o tiver ALTER, sistema usa DELETE automaticamente
--   - DELETE Ã© mais lento mas funcional para atÃ© 10k registros
--   - Para melhor performance, conceder ALTER em todas as tabelas STG:
--
--     GRANT ALTER ON dbo.KPI_MSSQL_ALWAYSON_STATUS_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_BLOCKED_USERS_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_DB_AVAILABILITY_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_DISK_USAGE_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_FG_USAGE_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_INST_AVAILABILITY_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_PROCESSES_STG TO [SEU_USUARIO];
--     GRANT ALTER ON dbo.KPI_MSSQL_TLOG_USAGE_STG TO [SEU_USUARIO];
--     -- KPIs removidos: LONG_LOCKS, DB_IO_STATS, DEADLOCKS, ERRORLOG, SERVICE_STATUS
--
-- =============================================

SET NOCOUNT OFF;
GO
-- =============================================
-- PARTE 6: OS PERFORMANCE COUNTERS (NEW)
-- =============================================
-- Tabelas, Views e Procedures para coleta de
-- Windows OS Performance Counters (Memory, CPU, Disk)
-- para correlacao com metricas SQL Server
-- =============================================-- =====================================================================
-- KPI_OS_PERFORMANCE_TABLES.sql
-- WatcherDB Intelligence - OS Performance Counters Tables
--
-- Purpose: Store Windows OS performance metrics (Memory, CPU, Disk)
--          to enable correlation with SQL Server metrics for
--          comprehensive diagnosis of performance issues.
--
-- Target Database: SQLHDSTST505\I01 - WatcherDB_Intelligence
-- Author: WatcherDB Intelligence Team
-- Date: 2025-12-15
-- Version: 1.0.0
-- =====================================================================

USE [WatcherDB_Intelligence];
GO

PRINT '========================================';
PRINT 'Creating OS Performance Counter Tables';
PRINT '========================================';
PRINT '';

-- =====================================================================
-- SECTION 1: MEMORY PERFORMANCE TABLES
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1.1 KPI_OS_MEMORY_STG - Current Memory Metrics (Staging)
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_MEMORY_STG', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_MEMORY_STG...';
    DROP TABLE dbo.KPI_OS_MEMORY_STG;
END
GO

CREATE TABLE dbo.KPI_OS_MEMORY_STG (
    Instance            VARCHAR(64)     NOT NULL,   -- SQL Instance name (e.g., SQLHDSPRD014_I01)
    Hostname            VARCHAR(64)     NOT NULL,   -- Windows hostname (e.g., SQLHDSPRD014)

    -- Core Memory Metrics
    Available_MB        DECIMAL(18,2)   NULL,       -- Memory\Available MBytes (CRITICAL metric)
    Total_Physical_MB   DECIMAL(18,2)   NULL,       -- Total physical RAM
    Used_MB             DECIMAL(18,2)   NULL,       -- Total - Available
    Percent_Used        DECIMAL(5,2)    NULL,       -- (Used / Total) * 100

    -- Paging Metrics (Key for "Memory Pages Per Second" alerts)
    Pages_Per_Sec       DECIMAL(18,2)   NULL,       -- Memory\Pages/sec (soft + hard faults)
    Page_Reads_Sec      DECIMAL(18,2)   NULL,       -- Memory\Page Reads/sec (HARD faults - CRITICAL)
    Page_Writes_Sec     DECIMAL(18,2)   NULL,       -- Memory\Page Writes/sec
    Page_Faults_Sec     DECIMAL(18,2)   NULL,       -- Memory\Page Faults/sec

    -- Commit Metrics
    Commit_Limit_MB     DECIMAL(18,2)   NULL,       -- Commit Limit (RAM + PageFile)
    Commit_Total_MB     DECIMAL(18,2)   NULL,       -- Committed Bytes
    Percent_Committed   DECIMAL(5,2)    NULL,       -- (Commit_Total / Commit_Limit) * 100

    -- Pool Metrics
    Pool_Paged_MB       DECIMAL(18,2)   NULL,       -- Pool Paged Bytes / 1MB
    Pool_NonPaged_MB    DECIMAL(18,2)   NULL,       -- Pool Nonpaged Bytes / 1MB
    Cache_MB            DECIMAL(18,2)   NULL,       -- Cache Bytes / 1MB

    -- Classification
    Severity            VARCHAR(16)     NULL,       -- CRITICAL, WARNING, INFO, OK

    -- Metadata
    Collection_Method   VARCHAR(32)     DEFAULT 'WMI',  -- WMI, PowerShell, PerfMon
    Update_TS           DATETIME2       DEFAULT GETDATE(),

    CONSTRAINT PK_KPI_OS_MEMORY_STG PRIMARY KEY CLUSTERED (Instance, Hostname)
);
GO

PRINT 'Created KPI_OS_MEMORY_STG';

-- ---------------------------------------------------------------------
-- 1.2 KPI_OS_MEMORY_HIST - Historical Memory Metrics
-- Retention: 90 days, Collection interval: 5 minutes
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_MEMORY_HIST', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_MEMORY_HIST...';
    DROP TABLE dbo.KPI_OS_MEMORY_HIST;
END
GO

CREATE TABLE dbo.KPI_OS_MEMORY_HIST (
    Instance            VARCHAR(64)     NOT NULL,
    Hostname            VARCHAR(64)     NOT NULL,

    -- Core Memory Metrics
    Available_MB        DECIMAL(18,2)   NULL,
    Total_Physical_MB   DECIMAL(18,2)   NULL,
    Used_MB             DECIMAL(18,2)   NULL,
    Percent_Used        DECIMAL(5,2)    NULL,

    -- Paging Metrics
    Pages_Per_Sec       DECIMAL(18,2)   NULL,
    Page_Reads_Sec      DECIMAL(18,2)   NULL,
    Page_Writes_Sec     DECIMAL(18,2)   NULL,
    Page_Faults_Sec     DECIMAL(18,2)   NULL,

    -- Commit Metrics
    Commit_Limit_MB     DECIMAL(18,2)   NULL,
    Commit_Total_MB     DECIMAL(18,2)   NULL,
    Percent_Committed   DECIMAL(5,2)    NULL,

    -- Pool Metrics
    Pool_Paged_MB       DECIMAL(18,2)   NULL,
    Pool_NonPaged_MB    DECIMAL(18,2)   NULL,
    Cache_MB            DECIMAL(18,2)   NULL,

    -- Classification
    Severity            VARCHAR(16)     NULL,

    -- Metadata
    Collection_Method   VARCHAR(32)     NULL,
    Update_TS           DATETIME2       NOT NULL,

    CONSTRAINT PK_KPI_OS_MEMORY_HIST PRIMARY KEY CLUSTERED (Instance, Hostname, Update_TS)
) WITH (DATA_COMPRESSION = PAGE);
GO

-- Index for trend queries
CREATE NONCLUSTERED INDEX IX_KPI_OS_MEMORY_HIST_UpdateTS
ON dbo.KPI_OS_MEMORY_HIST (Update_TS DESC)
INCLUDE (Available_MB, Pages_Per_Sec, Page_Reads_Sec, Severity);
GO

-- Index for hostname lookups
CREATE NONCLUSTERED INDEX IX_KPI_OS_MEMORY_HIST_Hostname
ON dbo.KPI_OS_MEMORY_HIST (Hostname, Update_TS DESC);
GO

PRINT 'Created KPI_OS_MEMORY_HIST with indexes';


-- =====================================================================
-- SECTION 2: CPU PERFORMANCE TABLES
-- =====================================================================

-- ---------------------------------------------------------------------
-- 2.1 KPI_OS_CPU_STG - Current CPU Metrics (Staging)
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_CPU_STG', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_CPU_STG...';
    DROP TABLE dbo.KPI_OS_CPU_STG;
END
GO

CREATE TABLE dbo.KPI_OS_CPU_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Hostname            VARCHAR(64)     NOT NULL,

    -- Processor Metrics
    Processor_Pct       DECIMAL(5,2)    NULL,       -- Processor\% Processor Time (_Total)
    Privileged_Pct      DECIMAL(5,2)    NULL,       -- % Privileged Time (kernel mode)
    User_Pct            DECIMAL(5,2)    NULL,       -- % User Time (user mode)
    Idle_Pct            DECIMAL(5,2)    NULL,       -- % Idle Time

    -- System Metrics
    Queue_Length        INT             NULL,       -- System\Processor Queue Length
    Context_Switches    DECIMAL(18,2)   NULL,       -- System\Context Switches/sec
    Interrupts_Sec      DECIMAL(18,2)   NULL,       -- Processor\Interrupts/sec

    -- Process Info
    Process_Count       INT             NULL,       -- Number of running processes
    Thread_Count        INT             NULL,       -- Number of threads
    Handle_Count        INT             NULL,       -- Number of handles

    -- SQL Server Specific
    SQL_CPU_Pct         DECIMAL(5,2)    NULL,       -- SQL Server process CPU %

    -- Classification
    Severity            VARCHAR(16)     NULL,       -- CRITICAL, WARNING, INFO, OK

    -- Metadata
    Logical_Processors  INT             NULL,       -- Number of logical processors
    Collection_Method   VARCHAR(32)     DEFAULT 'WMI',
    Update_TS           DATETIME2       DEFAULT GETDATE(),

    CONSTRAINT PK_KPI_OS_CPU_STG PRIMARY KEY CLUSTERED (Instance, Hostname)
);
GO

PRINT 'Created KPI_OS_CPU_STG';

-- ---------------------------------------------------------------------
-- 2.2 KPI_OS_CPU_HIST - Historical CPU Metrics
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_CPU_HIST', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_CPU_HIST...';
    DROP TABLE dbo.KPI_OS_CPU_HIST;
END
GO

CREATE TABLE dbo.KPI_OS_CPU_HIST (
    Instance            VARCHAR(64)     NOT NULL,
    Hostname            VARCHAR(64)     NOT NULL,

    -- Processor Metrics
    Processor_Pct       DECIMAL(5,2)    NULL,
    Privileged_Pct      DECIMAL(5,2)    NULL,
    User_Pct            DECIMAL(5,2)    NULL,
    Idle_Pct            DECIMAL(5,2)    NULL,

    -- System Metrics
    Queue_Length        INT             NULL,
    Context_Switches    DECIMAL(18,2)   NULL,
    Interrupts_Sec      DECIMAL(18,2)   NULL,

    -- Process Info
    Process_Count       INT             NULL,
    Thread_Count        INT             NULL,
    Handle_Count        INT             NULL,

    -- SQL Server Specific
    SQL_CPU_Pct         DECIMAL(5,2)    NULL,

    -- Classification
    Severity            VARCHAR(16)     NULL,

    -- Metadata
    Logical_Processors  INT             NULL,
    Collection_Method   VARCHAR(32)     NULL,
    Update_TS           DATETIME2       NOT NULL,

    CONSTRAINT PK_KPI_OS_CPU_HIST PRIMARY KEY CLUSTERED (Instance, Hostname, Update_TS)
) WITH (DATA_COMPRESSION = PAGE);
GO

-- Index for trend queries
CREATE NONCLUSTERED INDEX IX_KPI_OS_CPU_HIST_UpdateTS
ON dbo.KPI_OS_CPU_HIST (Update_TS DESC)
INCLUDE (Processor_Pct, Queue_Length, Severity);
GO

PRINT 'Created KPI_OS_CPU_HIST with indexes';


-- =====================================================================
-- SECTION 3: DISK PERFORMANCE TABLES
-- =====================================================================

-- ---------------------------------------------------------------------
-- 3.1 KPI_OS_DISK_PERF_STG - Current Disk Performance (Staging)
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_DISK_PERF_STG', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_DISK_PERF_STG...';
    DROP TABLE dbo.KPI_OS_DISK_PERF_STG;
END
GO

CREATE TABLE dbo.KPI_OS_DISK_PERF_STG (
    Instance            VARCHAR(64)     NOT NULL,
    Hostname            VARCHAR(64)     NOT NULL,
    Drive               VARCHAR(8)      NOT NULL,   -- C:, D:, E:, etc.

    -- Queue Metrics
    Avg_Queue_Length    DECIMAL(10,2)   NULL,       -- PhysicalDisk\Avg. Disk Queue Length
    Current_Queue_Len   INT             NULL,       -- Current Disk Queue Length

    -- Utilization
    Percent_Disk_Time   DECIMAL(5,2)    NULL,       -- PhysicalDisk\% Disk Time
    Percent_Read_Time   DECIMAL(5,2)    NULL,       -- % Disk Read Time
    Percent_Write_Time  DECIMAL(5,2)    NULL,       -- % Disk Write Time
    Percent_Idle_Time   DECIMAL(5,2)    NULL,       -- % Idle Time

    -- Latency (CRITICAL for performance)
    Avg_Sec_Per_Read    DECIMAL(10,6)   NULL,       -- Avg. Disk sec/Read (in seconds)
    Avg_Sec_Per_Write   DECIMAL(10,6)   NULL,       -- Avg. Disk sec/Write
    Avg_Sec_Per_Transfer DECIMAL(10,6)  NULL,       -- Avg. Disk sec/Transfer

    -- Latency in milliseconds (easier to read)
    Avg_Read_Latency_MS  DECIMAL(10,2)  NULL,       -- Latency in ms
    Avg_Write_Latency_MS DECIMAL(10,2)  NULL,

    -- Throughput (IOPS)
    Disk_Reads_Sec      DECIMAL(18,2)   NULL,       -- Disk Reads/sec
    Disk_Writes_Sec     DECIMAL(18,2)   NULL,       -- Disk Writes/sec
    Disk_Transfers_Sec  DECIMAL(18,2)   NULL,       -- Disk Transfers/sec (total IOPS)

    -- Bandwidth
    Disk_Read_Bytes_Sec DECIMAL(18,2)   NULL,       -- Disk Read Bytes/sec
    Disk_Write_Bytes_Sec DECIMAL(18,2)  NULL,       -- Disk Write Bytes/sec
    Disk_Bytes_Sec      DECIMAL(18,2)   NULL,       -- Total Disk Bytes/sec

    -- Classification
    Severity            VARCHAR(16)     NULL,       -- CRITICAL, WARNING, INFO, OK

    -- Metadata
    Disk_Type           VARCHAR(16)     NULL,       -- SSD, HDD, NVMe
    Collection_Method   VARCHAR(32)     DEFAULT 'WMI',
    Update_TS           DATETIME2       DEFAULT GETDATE(),

    CONSTRAINT PK_KPI_OS_DISK_PERF_STG PRIMARY KEY CLUSTERED (Instance, Hostname, Drive)
);
GO

PRINT 'Created KPI_OS_DISK_PERF_STG';

-- ---------------------------------------------------------------------
-- 3.2 KPI_OS_DISK_PERF_HIST - Historical Disk Performance
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_DISK_PERF_HIST', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_DISK_PERF_HIST...';
    DROP TABLE dbo.KPI_OS_DISK_PERF_HIST;
END
GO

CREATE TABLE dbo.KPI_OS_DISK_PERF_HIST (
    Instance            VARCHAR(64)     NOT NULL,
    Hostname            VARCHAR(64)     NOT NULL,
    Drive               VARCHAR(8)      NOT NULL,

    -- Queue Metrics
    Avg_Queue_Length    DECIMAL(10,2)   NULL,
    Current_Queue_Len   INT             NULL,

    -- Utilization
    Percent_Disk_Time   DECIMAL(5,2)    NULL,
    Percent_Read_Time   DECIMAL(5,2)    NULL,
    Percent_Write_Time  DECIMAL(5,2)    NULL,
    Percent_Idle_Time   DECIMAL(5,2)    NULL,

    -- Latency
    Avg_Sec_Per_Read    DECIMAL(10,6)   NULL,
    Avg_Sec_Per_Write   DECIMAL(10,6)   NULL,
    Avg_Sec_Per_Transfer DECIMAL(10,6)  NULL,
    Avg_Read_Latency_MS  DECIMAL(10,2)  NULL,
    Avg_Write_Latency_MS DECIMAL(10,2)  NULL,

    -- Throughput
    Disk_Reads_Sec      DECIMAL(18,2)   NULL,
    Disk_Writes_Sec     DECIMAL(18,2)   NULL,
    Disk_Transfers_Sec  DECIMAL(18,2)   NULL,

    -- Bandwidth
    Disk_Read_Bytes_Sec DECIMAL(18,2)   NULL,
    Disk_Write_Bytes_Sec DECIMAL(18,2)  NULL,
    Disk_Bytes_Sec      DECIMAL(18,2)   NULL,

    -- Classification
    Severity            VARCHAR(16)     NULL,

    -- Metadata
    Disk_Type           VARCHAR(16)     NULL,
    Collection_Method   VARCHAR(32)     NULL,
    Update_TS           DATETIME2       NOT NULL,

    CONSTRAINT PK_KPI_OS_DISK_PERF_HIST PRIMARY KEY CLUSTERED (Instance, Hostname, Drive, Update_TS)
) WITH (DATA_COMPRESSION = PAGE);
GO

-- Index for trend queries
CREATE NONCLUSTERED INDEX IX_KPI_OS_DISK_PERF_HIST_UpdateTS
ON dbo.KPI_OS_DISK_PERF_HIST (Update_TS DESC)
INCLUDE (Avg_Queue_Length, Avg_Read_Latency_MS, Avg_Write_Latency_MS, Severity);
GO

PRINT 'Created KPI_OS_DISK_PERF_HIST with indexes';


-- =====================================================================
-- SECTION 4: DIAGNOSIS LOG TABLE
-- =====================================================================

-- ---------------------------------------------------------------------
-- 4.1 KPI_OS_DIAGNOSIS_LOG - Automated Diagnosis Tracking
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_OS_DIAGNOSIS_LOG', 'U') IS NOT NULL
BEGIN
    PRINT 'Dropping existing KPI_OS_DIAGNOSIS_LOG...';
    DROP TABLE dbo.KPI_OS_DIAGNOSIS_LOG;
END
GO

CREATE TABLE dbo.KPI_OS_DIAGNOSIS_LOG (
    Diagnosis_ID        INT IDENTITY(1,1) PRIMARY KEY,

    -- Server Info
    Instance            VARCHAR(64)     NOT NULL,
    Hostname            VARCHAR(64)     NOT NULL,

    -- Alert Context
    Alert_Type          VARCHAR(128)    NULL,       -- "Memory Pages Per Second is too High"
    Alert_Source        VARCHAR(64)     NULL,       -- SCOM, Zabbix, Custom, etc.
    Alert_Key           VARCHAR(128)    NULL,       -- External alert ID/key

    -- Diagnosis Result
    Severity            VARCHAR(16)     NOT NULL,   -- CRITICAL, WARNING, INFO, OK
    Root_Cause          VARCHAR(512)    NULL,       -- Primary identified cause
    Root_Cause_Category VARCHAR(64)     NULL,       -- MEMORY_PRESSURE, CPU_SATURATION, DISK_BOTTLENECK
    Correlation_Score   DECIMAL(5,2)    NULL,       -- Confidence score 0-100

    -- Detailed Analysis
    Diagnosis_Summary   NVARCHAR(MAX)   NULL,       -- Human-readable summary
    Recommendations     NVARCHAR(MAX)   NULL,       -- JSON array of recommendations

    -- Snapshots (JSON)
    OS_Memory_Snapshot  NVARCHAR(MAX)   NULL,       -- JSON with OS memory metrics
    OS_CPU_Snapshot     NVARCHAR(MAX)   NULL,       -- JSON with OS CPU metrics
    OS_Disk_Snapshot    NVARCHAR(MAX)   NULL,       -- JSON with OS disk metrics
    SQL_Memory_Snapshot NVARCHAR(MAX)   NULL,       -- JSON with SQL memory metrics
    SQL_Perf_Snapshot   NVARCHAR(MAX)   NULL,       -- JSON with SQL performance metrics

    -- Related Events
    Related_Events      NVARCHAR(MAX)   NULL,       -- JSON array of related Windows events

    -- Workflow
    Created_TS          DATETIME2       DEFAULT GETDATE(),
    Acknowledged        BIT             DEFAULT 0,
    Acknowledged_By     VARCHAR(64)     NULL,
    Acknowledged_TS     DATETIME2       NULL,
    Resolution_Notes    NVARCHAR(MAX)   NULL,
    Resolved            BIT             DEFAULT 0,
    Resolved_TS         DATETIME2       NULL,

    -- Metadata
    Analysis_Duration_MS INT            NULL,       -- Time taken to analyze
    API_Version         VARCHAR(16)     NULL
);
GO

-- Index for active diagnosis queries
CREATE NONCLUSTERED INDEX IX_KPI_OS_DIAGNOSIS_LOG_Active
ON dbo.KPI_OS_DIAGNOSIS_LOG (Resolved, Severity, Created_TS DESC)
WHERE Resolved = 0;
GO

-- Index for hostname lookups
CREATE NONCLUSTERED INDEX IX_KPI_OS_DIAGNOSIS_LOG_Hostname
ON dbo.KPI_OS_DIAGNOSIS_LOG (Hostname, Created_TS DESC);
GO

-- Index for alert tracking
CREATE NONCLUSTERED INDEX IX_KPI_OS_DIAGNOSIS_LOG_AlertKey
ON dbo.KPI_OS_DIAGNOSIS_LOG (Alert_Key)
WHERE Alert_Key IS NOT NULL;
GO

PRINT 'Created KPI_OS_DIAGNOSIS_LOG with indexes';


-- =====================================================================
-- SECTION 5: HELPER PROCEDURES
-- =====================================================================

-- ---------------------------------------------------------------------
-- 5.1 usp_OS_Memory_Upsert - Insert/Update Memory Metrics
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Memory_Upsert', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Memory_Upsert;
GO

CREATE PROCEDURE dbo.usp_OS_Memory_Upsert
    @Instance           VARCHAR(64),
    @Hostname           VARCHAR(64),
    @Available_MB       DECIMAL(18,2),
    @Total_Physical_MB  DECIMAL(18,2),
    @Pages_Per_Sec      DECIMAL(18,2),
    @Page_Reads_Sec     DECIMAL(18,2),
    @Page_Writes_Sec    DECIMAL(18,2) = NULL,
    @Page_Faults_Sec    DECIMAL(18,2) = NULL,
    @Commit_Limit_MB    DECIMAL(18,2) = NULL,
    @Commit_Total_MB    DECIMAL(18,2) = NULL,
    @Pool_Paged_MB      DECIMAL(18,2) = NULL,
    @Pool_NonPaged_MB   DECIMAL(18,2) = NULL,
    @Cache_MB           DECIMAL(18,2) = NULL,
    @Collection_Method  VARCHAR(32) = 'WMI'
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Used_MB DECIMAL(18,2) = @Total_Physical_MB - @Available_MB;
    DECLARE @Percent_Used DECIMAL(5,2) = CASE
        WHEN @Total_Physical_MB > 0
        THEN (@Used_MB / @Total_Physical_MB) * 100
        ELSE 0
    END;
    DECLARE @Percent_Committed DECIMAL(5,2) = CASE
        WHEN @Commit_Limit_MB > 0
        THEN (@Commit_Total_MB / @Commit_Limit_MB) * 100
        ELSE 0
    END;

    -- Classify severity
    DECLARE @Severity VARCHAR(16) =
        CASE
            WHEN @Page_Reads_Sec > 100 AND @Available_MB < 500 THEN 'CRITICAL'
            WHEN @Page_Reads_Sec > 50 AND @Available_MB < 1000 THEN 'WARNING'
            WHEN @Pages_Per_Sec > 500 THEN 'WARNING'
            WHEN @Available_MB < 500 THEN 'WARNING'
            ELSE 'OK'
        END;

    -- Upsert to STG
    MERGE dbo.KPI_OS_MEMORY_STG AS target
    USING (SELECT @Instance AS Instance, @Hostname AS Hostname) AS source
    ON target.Instance = source.Instance AND target.Hostname = source.Hostname
    WHEN MATCHED THEN
        UPDATE SET
            Available_MB = @Available_MB,
            Total_Physical_MB = @Total_Physical_MB,
            Used_MB = @Used_MB,
            Percent_Used = @Percent_Used,
            Pages_Per_Sec = @Pages_Per_Sec,
            Page_Reads_Sec = @Page_Reads_Sec,
            Page_Writes_Sec = @Page_Writes_Sec,
            Page_Faults_Sec = @Page_Faults_Sec,
            Commit_Limit_MB = @Commit_Limit_MB,
            Commit_Total_MB = @Commit_Total_MB,
            Percent_Committed = @Percent_Committed,
            Pool_Paged_MB = @Pool_Paged_MB,
            Pool_NonPaged_MB = @Pool_NonPaged_MB,
            Cache_MB = @Cache_MB,
            Severity = @Severity,
            Collection_Method = @Collection_Method,
            Update_TS = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (Instance, Hostname, Available_MB, Total_Physical_MB, Used_MB, Percent_Used,
                Pages_Per_Sec, Page_Reads_Sec, Page_Writes_Sec, Page_Faults_Sec,
                Commit_Limit_MB, Commit_Total_MB, Percent_Committed,
                Pool_Paged_MB, Pool_NonPaged_MB, Cache_MB, Severity, Collection_Method)
        VALUES (@Instance, @Hostname, @Available_MB, @Total_Physical_MB, @Used_MB, @Percent_Used,
                @Pages_Per_Sec, @Page_Reads_Sec, @Page_Writes_Sec, @Page_Faults_Sec,
                @Commit_Limit_MB, @Commit_Total_MB, @Percent_Committed,
                @Pool_Paged_MB, @Pool_NonPaged_MB, @Cache_MB, @Severity, @Collection_Method);

    -- Insert to HIST
    INSERT INTO dbo.KPI_OS_MEMORY_HIST
        (Instance, Hostname, Available_MB, Total_Physical_MB, Used_MB, Percent_Used,
         Pages_Per_Sec, Page_Reads_Sec, Page_Writes_Sec, Page_Faults_Sec,
         Commit_Limit_MB, Commit_Total_MB, Percent_Committed,
         Pool_Paged_MB, Pool_NonPaged_MB, Cache_MB, Severity, Collection_Method, Update_TS)
    VALUES
        (@Instance, @Hostname, @Available_MB, @Total_Physical_MB, @Used_MB, @Percent_Used,
         @Pages_Per_Sec, @Page_Reads_Sec, @Page_Writes_Sec, @Page_Faults_Sec,
         @Commit_Limit_MB, @Commit_Total_MB, @Percent_Committed,
         @Pool_Paged_MB, @Pool_NonPaged_MB, @Cache_MB, @Severity, @Collection_Method, GETDATE());
END;
GO

PRINT 'Created usp_OS_Memory_Upsert';


-- ---------------------------------------------------------------------
-- 5.2 usp_OS_CPU_Upsert - Insert/Update CPU Metrics
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_CPU_Upsert', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_CPU_Upsert;
GO

CREATE PROCEDURE dbo.usp_OS_CPU_Upsert
    @Instance           VARCHAR(64),
    @Hostname           VARCHAR(64),
    @Processor_Pct      DECIMAL(5,2),
    @Privileged_Pct     DECIMAL(5,2) = NULL,
    @User_Pct           DECIMAL(5,2) = NULL,
    @Idle_Pct           DECIMAL(5,2) = NULL,
    @Queue_Length       INT = NULL,
    @Context_Switches   DECIMAL(18,2) = NULL,
    @Interrupts_Sec     DECIMAL(18,2) = NULL,
    @Process_Count      INT = NULL,
    @Thread_Count       INT = NULL,
    @Handle_Count       INT = NULL,
    @SQL_CPU_Pct        DECIMAL(5,2) = NULL,
    @Logical_Processors INT = NULL,
    @Collection_Method  VARCHAR(32) = 'WMI'
AS
BEGIN
    SET NOCOUNT ON;

    -- Classify severity
    DECLARE @Severity VARCHAR(16) =
        CASE
            WHEN @Processor_Pct > 95 THEN 'CRITICAL'
            WHEN @Processor_Pct > 80 OR @Queue_Length > 10 THEN 'WARNING'
            WHEN @Queue_Length > 5 THEN 'INFO'
            ELSE 'OK'
        END;

    -- Upsert to STG
    MERGE dbo.KPI_OS_CPU_STG AS target
    USING (SELECT @Instance AS Instance, @Hostname AS Hostname) AS source
    ON target.Instance = source.Instance AND target.Hostname = source.Hostname
    WHEN MATCHED THEN
        UPDATE SET
            Processor_Pct = @Processor_Pct,
            Privileged_Pct = @Privileged_Pct,
            User_Pct = @User_Pct,
            Idle_Pct = @Idle_Pct,
            Queue_Length = @Queue_Length,
            Context_Switches = @Context_Switches,
            Interrupts_Sec = @Interrupts_Sec,
            Process_Count = @Process_Count,
            Thread_Count = @Thread_Count,
            Handle_Count = @Handle_Count,
            SQL_CPU_Pct = @SQL_CPU_Pct,
            Logical_Processors = @Logical_Processors,
            Severity = @Severity,
            Collection_Method = @Collection_Method,
            Update_TS = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (Instance, Hostname, Processor_Pct, Privileged_Pct, User_Pct, Idle_Pct,
                Queue_Length, Context_Switches, Interrupts_Sec,
                Process_Count, Thread_Count, Handle_Count, SQL_CPU_Pct,
                Logical_Processors, Severity, Collection_Method)
        VALUES (@Instance, @Hostname, @Processor_Pct, @Privileged_Pct, @User_Pct, @Idle_Pct,
                @Queue_Length, @Context_Switches, @Interrupts_Sec,
                @Process_Count, @Thread_Count, @Handle_Count, @SQL_CPU_Pct,
                @Logical_Processors, @Severity, @Collection_Method);

    -- Insert to HIST
    INSERT INTO dbo.KPI_OS_CPU_HIST
        (Instance, Hostname, Processor_Pct, Privileged_Pct, User_Pct, Idle_Pct,
         Queue_Length, Context_Switches, Interrupts_Sec,
         Process_Count, Thread_Count, Handle_Count, SQL_CPU_Pct,
         Logical_Processors, Severity, Collection_Method, Update_TS)
    VALUES
        (@Instance, @Hostname, @Processor_Pct, @Privileged_Pct, @User_Pct, @Idle_Pct,
         @Queue_Length, @Context_Switches, @Interrupts_Sec,
         @Process_Count, @Thread_Count, @Handle_Count, @SQL_CPU_Pct,
         @Logical_Processors, @Severity, @Collection_Method, GETDATE());
END;
GO

PRINT 'Created usp_OS_CPU_Upsert';


-- ---------------------------------------------------------------------
-- 5.3 usp_OS_Disk_Upsert - Insert/Update Disk Metrics
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Disk_Upsert', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Disk_Upsert;
GO

CREATE PROCEDURE dbo.usp_OS_Disk_Upsert
    @Instance           VARCHAR(64),
    @Hostname           VARCHAR(64),
    @Drive              VARCHAR(8),
    @Avg_Queue_Length   DECIMAL(10,2),
    @Percent_Disk_Time  DECIMAL(5,2) = NULL,
    @Avg_Sec_Per_Read   DECIMAL(10,6) = NULL,
    @Avg_Sec_Per_Write  DECIMAL(10,6) = NULL,
    @Disk_Reads_Sec     DECIMAL(18,2) = NULL,
    @Disk_Writes_Sec    DECIMAL(18,2) = NULL,
    @Disk_Bytes_Sec     DECIMAL(18,2) = NULL,
    @Disk_Type          VARCHAR(16) = NULL,
    @Collection_Method  VARCHAR(32) = 'WMI'
AS
BEGIN
    SET NOCOUNT ON;

    -- Calculate latency in milliseconds
    DECLARE @Avg_Read_Latency_MS DECIMAL(10,2) = @Avg_Sec_Per_Read * 1000;
    DECLARE @Avg_Write_Latency_MS DECIMAL(10,2) = @Avg_Sec_Per_Write * 1000;

    -- Classify severity
    DECLARE @Severity VARCHAR(16) =
        CASE
            WHEN @Avg_Queue_Length > 5 OR @Avg_Read_Latency_MS > 50 THEN 'CRITICAL'
            WHEN @Avg_Queue_Length > 2 OR @Avg_Read_Latency_MS > 20 THEN 'WARNING'
            WHEN @Percent_Disk_Time > 80 THEN 'INFO'
            ELSE 'OK'
        END;

    -- Upsert to STG
    MERGE dbo.KPI_OS_DISK_PERF_STG AS target
    USING (SELECT @Instance AS Instance, @Hostname AS Hostname, @Drive AS Drive) AS source
    ON target.Instance = source.Instance AND target.Hostname = source.Hostname AND target.Drive = source.Drive
    WHEN MATCHED THEN
        UPDATE SET
            Avg_Queue_Length = @Avg_Queue_Length,
            Percent_Disk_Time = @Percent_Disk_Time,
            Avg_Sec_Per_Read = @Avg_Sec_Per_Read,
            Avg_Sec_Per_Write = @Avg_Sec_Per_Write,
            Avg_Read_Latency_MS = @Avg_Read_Latency_MS,
            Avg_Write_Latency_MS = @Avg_Write_Latency_MS,
            Disk_Reads_Sec = @Disk_Reads_Sec,
            Disk_Writes_Sec = @Disk_Writes_Sec,
            Disk_Bytes_Sec = @Disk_Bytes_Sec,
            Disk_Type = @Disk_Type,
            Severity = @Severity,
            Collection_Method = @Collection_Method,
            Update_TS = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (Instance, Hostname, Drive, Avg_Queue_Length, Percent_Disk_Time,
                Avg_Sec_Per_Read, Avg_Sec_Per_Write, Avg_Read_Latency_MS, Avg_Write_Latency_MS,
                Disk_Reads_Sec, Disk_Writes_Sec, Disk_Bytes_Sec,
                Disk_Type, Severity, Collection_Method)
        VALUES (@Instance, @Hostname, @Drive, @Avg_Queue_Length, @Percent_Disk_Time,
                @Avg_Sec_Per_Read, @Avg_Sec_Per_Write, @Avg_Read_Latency_MS, @Avg_Write_Latency_MS,
                @Disk_Reads_Sec, @Disk_Writes_Sec, @Disk_Bytes_Sec,
                @Disk_Type, @Severity, @Collection_Method);

    -- Insert to HIST
    INSERT INTO dbo.KPI_OS_DISK_PERF_HIST
        (Instance, Hostname, Drive, Avg_Queue_Length, Percent_Disk_Time,
         Avg_Sec_Per_Read, Avg_Sec_Per_Write, Avg_Read_Latency_MS, Avg_Write_Latency_MS,
         Disk_Reads_Sec, Disk_Writes_Sec, Disk_Bytes_Sec,
         Disk_Type, Severity, Collection_Method, Update_TS)
    VALUES
        (@Instance, @Hostname, @Drive, @Avg_Queue_Length, @Percent_Disk_Time,
         @Avg_Sec_Per_Read, @Avg_Sec_Per_Write, @Avg_Read_Latency_MS, @Avg_Write_Latency_MS,
         @Disk_Reads_Sec, @Disk_Writes_Sec, @Disk_Bytes_Sec,
         @Disk_Type, @Severity, @Collection_Method, GETDATE());
END;
GO

PRINT 'Created usp_OS_Disk_Upsert';


-- ---------------------------------------------------------------------
-- 5.4 usp_OS_Cleanup_History - Clean old historical data (90 days)
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Cleanup_History', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Cleanup_History;
GO

CREATE PROCEDURE dbo.usp_OS_Cleanup_History
    @RetentionDays INT = 90
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @CutoffDate DATETIME2 = DATEADD(DAY, -@RetentionDays, GETDATE());
    DECLARE @DeletedMemory INT, @DeletedCPU INT, @DeletedDisk INT;

    -- Clean Memory History
    DELETE FROM dbo.KPI_OS_MEMORY_HIST WITH (NOLOCK)
    WHERE Update_TS < @CutoffDate;
    SET @DeletedMemory = @@ROWCOUNT;

    -- Clean CPU History
    DELETE FROM dbo.KPI_OS_CPU_HIST WITH (NOLOCK)
    WHERE Update_TS < @CutoffDate;
    SET @DeletedCPU = @@ROWCOUNT;

    -- Clean Disk History
    DELETE FROM dbo.KPI_OS_DISK_PERF_HIST WITH (NOLOCK)
    WHERE Update_TS < @CutoffDate;
    SET @DeletedDisk = @@ROWCOUNT;

    PRINT 'Cleanup completed. Deleted: Memory=' + CAST(@DeletedMemory AS VARCHAR)
        + ', CPU=' + CAST(@DeletedCPU AS VARCHAR)
        + ', Disk=' + CAST(@DeletedDisk AS VARCHAR);
END;
GO

PRINT 'Created usp_OS_Cleanup_History';


-- =====================================================================
-- SECTION 6: SUMMARY
-- =====================================================================
PRINT '';
PRINT '========================================';
PRINT 'OS Performance Tables Created Successfully';
PRINT '========================================';
PRINT '';
PRINT 'Tables Created:';
PRINT '  - KPI_OS_MEMORY_STG / KPI_OS_MEMORY_HIST';
PRINT '  - KPI_OS_CPU_STG / KPI_OS_CPU_HIST';
PRINT '  - KPI_OS_DISK_PERF_STG / KPI_OS_DISK_PERF_HIST';
PRINT '  - KPI_OS_DIAGNOSIS_LOG';
PRINT '';
PRINT 'Procedures Created:';
PRINT '  - usp_OS_Memory_Upsert';
PRINT '  - usp_OS_CPU_Upsert';
PRINT '  - usp_OS_Disk_Upsert';
PRINT '  - usp_OS_Cleanup_History';
PRINT '';
PRINT 'Next Steps:';
PRINT '  1. Run KPI_OS_PERFORMANCE_VIEWS.sql to create analysis views';
PRINT '  2. Deploy PowerShell collection script to servers';
PRINT '  3. Configure SQL Agent job for cleanup (daily)';
PRINT '';
GO


-- =====================================================================
-- KPI_OS_PERFORMANCE_VIEWS.sql
-- WatcherDB Intelligence - OS Performance Analysis Views
--
-- Purpose: Provide trend analysis and correlation views between
--          Windows OS metrics and SQL Server metrics for
--          comprehensive diagnosis of performance issues.
--
-- Target Database: SQLHDSTST505\I01 - WatcherDB_Intelligence
-- Author: WatcherDB Intelligence Team
-- Date: 2025-12-15
-- Version: 1.0.0
-- =====================================================================

USE [WatcherDB_Intelligence];
GO

PRINT '========================================';
PRINT 'Creating OS Performance Analysis Views';
PRINT '========================================';
PRINT '';

-- =====================================================================
-- SECTION 1: MEMORY TREND VIEWS
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1.1 vw_OS_Memory_Trend_30Min - Memory Trend Analysis (Last 30 Minutes)
-- Use: Detect "sustained high" memory pressure vs momentary spikes
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_Memory_Trend_30Min', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_Memory_Trend_30Min;
GO

CREATE VIEW dbo.vw_OS_Memory_Trend_30Min AS
SELECT
    Instance,
    Hostname,
    COUNT(*) AS Sample_Count,

    -- Available Memory Stats
    MIN(Available_MB) AS Min_Available_MB,
    AVG(Available_MB) AS Avg_Available_MB,
    MAX(Available_MB) AS Max_Available_MB,

    -- Pages/sec Stats (includes soft + hard faults)
    AVG(Pages_Per_Sec) AS Avg_Pages_Sec,
    MAX(Pages_Per_Sec) AS Max_Pages_Sec,
    MIN(Pages_Per_Sec) AS Min_Pages_Sec,

    -- Page Reads/sec Stats (HARD faults - CRITICAL metric)
    AVG(Page_Reads_Sec) AS Avg_Page_Reads_Sec,
    MAX(Page_Reads_Sec) AS Max_Page_Reads_Sec,

    -- Commit Stats
    AVG(Percent_Committed) AS Avg_Percent_Committed,
    MAX(Percent_Committed) AS Max_Percent_Committed,

    -- Percent Used
    AVG(Percent_Used) AS Avg_Percent_Used,
    MAX(Percent_Used) AS Max_Percent_Used,

    -- Sustained High Detection
    -- If more than 50% of samples are high, it's sustained
    SUM(CASE WHEN Page_Reads_Sec > 50 THEN 1 ELSE 0 END) AS High_Page_Reads_Count,
    SUM(CASE WHEN Available_MB < 1000 THEN 1 ELSE 0 END) AS Low_Available_MB_Count,

    -- Classification
    CASE
        WHEN AVG(Page_Reads_Sec) > 100 AND MIN(Available_MB) < 500
        THEN 'CRITICAL'
        WHEN AVG(Page_Reads_Sec) > 50 AND MIN(Available_MB) < 1000
        THEN 'WARNING'
        WHEN AVG(Pages_Per_Sec) > 500
        THEN 'WARNING'
        WHEN MIN(Available_MB) < 500
        THEN 'WARNING'
        ELSE 'OK'
    END AS Severity,

    -- Is this sustained (more than 50% of samples are problematic)?
    CASE
        WHEN SUM(CASE WHEN Page_Reads_Sec > 50 OR Available_MB < 1000 THEN 1 ELSE 0 END) > COUNT(*) / 2
        THEN 1
        ELSE 0
    END AS Is_Sustained,

    -- Period Info
    MIN(Update_TS) AS Period_Start,
    MAX(Update_TS) AS Period_End,
    DATEDIFF(MINUTE, MIN(Update_TS), MAX(Update_TS)) AS Period_Duration_Min

FROM dbo.KPI_OS_MEMORY_HIST WITH (NOLOCK)
WHERE Update_TS >= DATEADD(MINUTE, -30, GETDATE())
GROUP BY Instance, Hostname;
GO

PRINT 'Created vw_OS_Memory_Trend_30Min';


-- ---------------------------------------------------------------------
-- 1.2 vw_OS_Memory_Current - Current Memory Status with Classification
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_Memory_Current', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_Memory_Current;
GO

CREATE VIEW dbo.vw_OS_Memory_Current AS
SELECT
    Instance,
    Hostname,
    Available_MB,
    Total_Physical_MB,
    Used_MB,
    Percent_Used,
    Pages_Per_Sec,
    Page_Reads_Sec,
    Page_Writes_Sec,
    Commit_Total_MB,
    Commit_Limit_MB,
    Percent_Committed,
    Pool_Paged_MB,
    Pool_NonPaged_MB,
    Severity,
    Update_TS,

    -- Time since last update
    DATEDIFF(SECOND, Update_TS, GETDATE()) AS Age_Seconds,

    -- Is data stale? (more than 10 minutes old)
    CASE WHEN DATEDIFF(MINUTE, Update_TS, GETDATE()) > 10 THEN 1 ELSE 0 END AS Is_Stale,

    -- Detailed classification
    CASE
        WHEN Available_MB < 500 THEN 'CRITICAL: Very low available memory'
        WHEN Available_MB < 1000 THEN 'WARNING: Low available memory'
        WHEN Available_MB < 2000 THEN 'INFO: Available memory is adequate'
        ELSE 'OK: Healthy available memory'
    END AS Available_MB_Status,

    CASE
        WHEN Page_Reads_Sec > 100 THEN 'CRITICAL: Very high hard page faults'
        WHEN Page_Reads_Sec > 50 THEN 'WARNING: Elevated hard page faults'
        WHEN Page_Reads_Sec > 20 THEN 'INFO: Moderate hard page faults'
        ELSE 'OK: Normal paging activity'
    END AS Page_Reads_Status,

    CASE
        WHEN Pages_Per_Sec > 1000 THEN 'CRITICAL: Extreme paging activity'
        WHEN Pages_Per_Sec > 500 THEN 'WARNING: High paging activity'
        WHEN Pages_Per_Sec > 100 THEN 'INFO: Moderate paging'
        ELSE 'OK: Normal paging'
    END AS Pages_Sec_Status

FROM dbo.KPI_OS_MEMORY_STG;
GO

PRINT 'Created vw_OS_Memory_Current';


-- =====================================================================
-- SECTION 2: CPU TREND VIEWS
-- =====================================================================

-- ---------------------------------------------------------------------
-- 2.1 vw_OS_CPU_Trend_30Min - CPU Trend Analysis
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_CPU_Trend_30Min', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_CPU_Trend_30Min;
GO

CREATE VIEW dbo.vw_OS_CPU_Trend_30Min AS
SELECT
    Instance,
    Hostname,
    COUNT(*) AS Sample_Count,

    -- Processor Stats
    AVG(Processor_Pct) AS Avg_Processor_Pct,
    MAX(Processor_Pct) AS Max_Processor_Pct,
    MIN(Processor_Pct) AS Min_Processor_Pct,

    -- SQL CPU
    AVG(SQL_CPU_Pct) AS Avg_SQL_CPU_Pct,
    MAX(SQL_CPU_Pct) AS Max_SQL_CPU_Pct,

    -- Queue Length
    AVG(CAST(Queue_Length AS DECIMAL(10,2))) AS Avg_Queue_Length,
    MAX(Queue_Length) AS Max_Queue_Length,

    -- Context Switches
    AVG(Context_Switches) AS Avg_Context_Switches,
    MAX(Context_Switches) AS Max_Context_Switches,

    -- Sustained High Detection
    SUM(CASE WHEN Processor_Pct > 80 THEN 1 ELSE 0 END) AS High_CPU_Count,
    SUM(CASE WHEN Queue_Length > 5 THEN 1 ELSE 0 END) AS High_Queue_Count,

    -- Classification
    CASE
        WHEN AVG(Processor_Pct) > 95 THEN 'CRITICAL'
        WHEN AVG(Processor_Pct) > 80 OR MAX(Queue_Length) > 10 THEN 'WARNING'
        WHEN AVG(Processor_Pct) > 60 THEN 'INFO'
        ELSE 'OK'
    END AS Severity,

    -- Is this sustained?
    CASE
        WHEN SUM(CASE WHEN Processor_Pct > 80 THEN 1 ELSE 0 END) > COUNT(*) / 2
        THEN 1
        ELSE 0
    END AS Is_Sustained,

    -- Period Info
    MIN(Update_TS) AS Period_Start,
    MAX(Update_TS) AS Period_End

FROM dbo.KPI_OS_CPU_HIST WITH (NOLOCK)
WHERE Update_TS >= DATEADD(MINUTE, -30, GETDATE())
GROUP BY Instance, Hostname;
GO

PRINT 'Created vw_OS_CPU_Trend_30Min';


-- ---------------------------------------------------------------------
-- 2.2 vw_OS_CPU_Current - Current CPU Status
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_CPU_Current', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_CPU_Current;
GO

CREATE VIEW dbo.vw_OS_CPU_Current AS
SELECT
    Instance,
    Hostname,
    Processor_Pct,
    Privileged_Pct,
    User_Pct,
    Idle_Pct,
    Queue_Length,
    Context_Switches,
    SQL_CPU_Pct,
    Logical_Processors,
    Process_Count,
    Thread_Count,
    Severity,
    Update_TS,

    -- Time since last update
    DATEDIFF(SECOND, Update_TS, GETDATE()) AS Age_Seconds,

    -- Detailed classification
    CASE
        WHEN Processor_Pct > 95 THEN 'CRITICAL: CPU saturation'
        WHEN Processor_Pct > 80 THEN 'WARNING: High CPU utilization'
        WHEN Processor_Pct > 60 THEN 'INFO: Moderate CPU utilization'
        ELSE 'OK: Normal CPU utilization'
    END AS Processor_Status,

    CASE
        WHEN Queue_Length > 10 THEN 'CRITICAL: Very high queue length'
        WHEN Queue_Length > 5 THEN 'WARNING: Elevated queue length'
        WHEN Queue_Length > 2 THEN 'INFO: Moderate queue length'
        ELSE 'OK: Normal queue length'
    END AS Queue_Status

FROM dbo.KPI_OS_CPU_STG;
GO

PRINT 'Created vw_OS_CPU_Current';


-- =====================================================================
-- SECTION 3: DISK PERFORMANCE VIEWS
-- =====================================================================

-- ---------------------------------------------------------------------
-- 3.1 vw_OS_Disk_Current - Current Disk Performance with Classification
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_Disk_Current', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_Disk_Current;
GO

CREATE VIEW dbo.vw_OS_Disk_Current AS
SELECT
    Instance,
    Hostname,
    Drive,
    Avg_Queue_Length,
    Percent_Disk_Time,
    Avg_Read_Latency_MS,
    Avg_Write_Latency_MS,
    Disk_Reads_Sec,
    Disk_Writes_Sec,
    Disk_Transfers_Sec,
    Disk_Bytes_Sec,
    Disk_Type,
    Severity,
    Update_TS,

    -- Time since last update
    DATEDIFF(SECOND, Update_TS, GETDATE()) AS Age_Seconds,

    -- Detailed classification
    CASE
        WHEN Avg_Queue_Length > 5 THEN 'CRITICAL: Disk queue saturated'
        WHEN Avg_Queue_Length > 2 THEN 'WARNING: Elevated disk queue'
        WHEN Avg_Queue_Length > 1 THEN 'INFO: Moderate disk queue'
        ELSE 'OK: Normal disk queue'
    END AS Queue_Status,

    CASE
        WHEN Avg_Read_Latency_MS > 50 THEN 'CRITICAL: Very high read latency'
        WHEN Avg_Read_Latency_MS > 20 THEN 'WARNING: Elevated read latency'
        WHEN Avg_Read_Latency_MS > 10 THEN 'INFO: Moderate read latency'
        ELSE 'OK: Normal read latency'
    END AS Read_Latency_Status,

    CASE
        WHEN Avg_Write_Latency_MS > 50 THEN 'CRITICAL: Very high write latency'
        WHEN Avg_Write_Latency_MS > 20 THEN 'WARNING: Elevated write latency'
        WHEN Avg_Write_Latency_MS > 10 THEN 'INFO: Moderate write latency'
        ELSE 'OK: Normal write latency'
    END AS Write_Latency_Status

FROM dbo.KPI_OS_DISK_PERF_STG;
GO

PRINT 'Created vw_OS_Disk_Current';


-- =====================================================================
-- SECTION 4: CORRELATION VIEWS (OS + SQL Server)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 4.1 vw_OS_SQL_Memory_Correlation - THE KEY VIEW
-- Correlates OS memory metrics with SQL Server memory metrics
-- This is what enables answering "Memory Pages Per Second" tickets!
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_SQL_Memory_Correlation', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_SQL_Memory_Correlation;
GO

CREATE VIEW dbo.vw_OS_SQL_Memory_Correlation AS
SELECT
    os.Instance,
    os.Hostname,

    -- ========== OS MEMORY METRICS ==========
    os.Available_MB AS OS_Available_MB,
    os.Total_Physical_MB AS OS_Total_Physical_MB,
    os.Percent_Used AS OS_Percent_Used,
    os.Pages_Per_Sec AS OS_Pages_Sec,
    os.Page_Reads_Sec AS OS_Page_Reads_Sec,      -- CRITICAL: Hard page faults
    os.Page_Writes_Sec AS OS_Page_Writes_Sec,
    os.Percent_Committed AS OS_Percent_Committed,
    os.Severity AS OS_Severity,

    -- ========== SQL SERVER MEMORY METRICS ==========
    -- These come from existing SQL Server KPI tables
    sql_proc.SQL_Memory_MB AS SQL_Memory_Used_MB,
    sql_proc.Max_Memory_MB AS SQL_Max_Memory_MB,

    -- PLE (Page Life Expectancy) - CRITICAL correlation metric
    -- Note: This would come from KPI_MSSQL_BUFFER_STATS or similar table
    -- For now, we'll reference a placeholder or join to the actual table
    CAST(NULL AS INT) AS SQL_Page_Life_Expectancy,  -- TODO: Join to actual PLE table
    CAST(NULL AS INT) AS SQL_Memory_Grants_Pending,
    CAST(NULL AS DECIMAL(5,2)) AS SQL_Buffer_Hit_Ratio,

    -- ========== CORRELATION DIAGNOSIS ==========
    CASE
        -- CRITICAL: OS memory pressure causing SQL Server buffer pool eviction
        WHEN os.Available_MB < 500 AND os.Page_Reads_Sec > 50
        THEN 'CRITICAL: OS memory exhaustion causing SQL Server buffer pool eviction. SQL is using disk as memory.'

        -- WARNING: High hard page faults correlating (would check PLE when available)
        WHEN os.Page_Reads_Sec > 100
        THEN 'WARNING: High hard page faults (Page Reads/sec > 100). Likely causing SQL Server performance degradation.'

        -- WARNING: Low available memory with high commit
        WHEN os.Available_MB < 1000 AND os.Percent_Committed > 90
        THEN 'WARNING: Low available memory with high commit ratio. Memory pressure building.'

        -- INFO: High soft page faults only (likely spike)
        WHEN os.Pages_Per_Sec > 500 AND os.Page_Reads_Sec < 20
        THEN 'INFO: High soft page faults only (Pages/sec high but Page Reads/sec low). Likely a momentary spike, no significant impact.'

        -- INFO: Moderate memory usage
        WHEN os.Available_MB < 2000
        THEN 'INFO: Available memory is adequate but not abundant. Monitor for trends.'

        ELSE 'OK: Memory metrics within normal parameters.'
    END AS Correlation_Diagnosis,

    -- ========== ROOT CAUSE CLASSIFICATION ==========
    CASE
        WHEN os.Available_MB < 500 AND os.Page_Reads_Sec > 50
        THEN 'OS_MEMORY_EXHAUSTION'

        WHEN os.Page_Reads_Sec > 100
        THEN 'EXCESSIVE_PAGING'

        WHEN os.Percent_Committed > 95
        THEN 'COMMIT_LIMIT_PRESSURE'

        WHEN os.Pages_Per_Sec > 1000
        THEN 'PAGING_STORM'

        ELSE 'NORMAL'
    END AS Root_Cause_Category,

    -- ========== RECOMMENDATIONS ==========
    CASE
        WHEN os.Available_MB < 500
        THEN 'Check max server memory setting. Consider reducing SQL Server memory or adding RAM to server.'

        WHEN os.Page_Reads_Sec > 100
        THEN 'Investigate processes consuming memory. Check for memory leaks. Review SQL Server memory grants.'

        WHEN os.Percent_Committed > 90
        THEN 'Review PageFile settings. Consider adding RAM or reducing memory-intensive workloads.'

        ELSE NULL
    END AS Recommendation,

    -- ========== SEVERITY SCORE (0-100) ==========
    -- Higher score = worse situation
    CASE
        WHEN os.Available_MB < 500 AND os.Page_Reads_Sec > 100 THEN 95
        WHEN os.Available_MB < 500 THEN 80
        WHEN os.Page_Reads_Sec > 100 THEN 75
        WHEN os.Available_MB < 1000 AND os.Page_Reads_Sec > 50 THEN 60
        WHEN os.Available_MB < 1000 THEN 50
        WHEN os.Page_Reads_Sec > 50 THEN 45
        WHEN os.Pages_Per_Sec > 500 THEN 30
        ELSE 10
    END AS Severity_Score,

    -- ========== OVERALL SEVERITY ==========
    CASE
        WHEN os.Available_MB < 500 AND os.Page_Reads_Sec > 50 THEN 'CRITICAL'
        WHEN os.Available_MB < 500 OR os.Page_Reads_Sec > 100 THEN 'WARNING'
        WHEN os.Available_MB < 1000 OR os.Page_Reads_Sec > 50 THEN 'INFO'
        ELSE 'OK'
    END AS Overall_Severity,

    -- ========== METADATA ==========
    os.Update_TS AS OS_Update_TS,
    GETDATE() AS Analysis_Time

FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK) os
-- Join to SQL Server process info if available
LEFT JOIN (
    SELECT
        Instance,
        -- Placeholder - adjust to your actual SQL memory table
        CAST(NULL AS DECIMAL(18,2)) AS SQL_Memory_MB,
        CAST(NULL AS DECIMAL(18,2)) AS Max_Memory_MB
    FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK)
) sql_proc ON os.Instance = sql_proc.Instance;
GO

PRINT 'Created vw_OS_SQL_Memory_Correlation';


-- ---------------------------------------------------------------------
-- 4.2 vw_OS_SQL_Full_Correlation - Complete OS + SQL Correlation
-- Includes Memory, CPU, and Disk correlation
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_SQL_Full_Correlation', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_SQL_Full_Correlation;
GO

CREATE VIEW dbo.vw_OS_SQL_Full_Correlation AS
SELECT
    COALESCE(mem.Instance, cpu.Instance, disk.Instance) AS Instance,
    COALESCE(mem.Hostname, cpu.Hostname, disk.Hostname) AS Hostname,

    -- ========== MEMORY ==========
    mem.OS_Available_MB,
    mem.OS_Pages_Sec,
    mem.OS_Page_Reads_Sec,
    mem.OS_Percent_Committed,
    mem.OS_Severity AS Memory_Severity,
    mem.Correlation_Diagnosis AS Memory_Diagnosis,

    -- ========== CPU ==========
    cpu.Processor_Pct AS OS_CPU_Pct,
    cpu.Queue_Length AS OS_Queue_Length,
    cpu.SQL_CPU_Pct,
    cpu.Severity AS CPU_Severity,

    -- ========== DISK (aggregated worst drive) ==========
    disk.Worst_Queue_Length AS Disk_Worst_Queue,
    disk.Worst_Read_Latency_MS AS Disk_Worst_Read_Latency,
    disk.Worst_Write_Latency_MS AS Disk_Worst_Write_Latency,
    disk.Disk_Severity,

    -- ========== OVERALL ASSESSMENT ==========
    CASE
        WHEN mem.Overall_Severity = 'CRITICAL' OR cpu.Severity = 'CRITICAL' OR disk.Disk_Severity = 'CRITICAL'
        THEN 'CRITICAL'
        WHEN mem.Overall_Severity = 'WARNING' OR cpu.Severity = 'WARNING' OR disk.Disk_Severity = 'WARNING'
        THEN 'WARNING'
        WHEN mem.Overall_Severity = 'INFO' OR cpu.Severity = 'INFO' OR disk.Disk_Severity = 'INFO'
        THEN 'INFO'
        ELSE 'OK'
    END AS Overall_Health,

    -- ========== PROBLEM SUMMARY ==========
    CONCAT(
        CASE WHEN mem.Overall_Severity IN ('CRITICAL', 'WARNING') THEN '[MEMORY] ' ELSE '' END,
        CASE WHEN cpu.Severity IN ('CRITICAL', 'WARNING') THEN '[CPU] ' ELSE '' END,
        CASE WHEN disk.Disk_Severity IN ('CRITICAL', 'WARNING') THEN '[DISK] ' ELSE '' END
    ) AS Problem_Areas,

    GETDATE() AS Analysis_Time

FROM dbo.vw_OS_SQL_Memory_Correlation mem
FULL OUTER JOIN dbo.vw_OS_CPU_Current cpu
    ON mem.Instance = cpu.Instance AND mem.Hostname = cpu.Hostname
FULL OUTER JOIN (
    -- Aggregate disk metrics per server (worst values)
    SELECT
        Instance,
        Hostname,
        MAX(Avg_Queue_Length) AS Worst_Queue_Length,
        MAX(Avg_Read_Latency_MS) AS Worst_Read_Latency_MS,
        MAX(Avg_Write_Latency_MS) AS Worst_Write_Latency_MS,
        MAX(Severity) AS Disk_Severity
    FROM dbo.vw_OS_Disk_Current
    GROUP BY Instance, Hostname
) disk ON COALESCE(mem.Instance, cpu.Instance) = disk.Instance
      AND COALESCE(mem.Hostname, cpu.Hostname) = disk.Hostname;
GO

PRINT 'Created vw_OS_SQL_Full_Correlation';


-- =====================================================================
-- SECTION 5: ALERT-FOCUSED VIEWS
-- =====================================================================

-- ---------------------------------------------------------------------
-- 5.1 vw_OS_Memory_Alert_Diagnosis - Specifically for "Memory Pages" alerts
-- This view is designed to answer SCOM tickets like
-- "Memory Pages Per Second is too High"
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_Memory_Alert_Diagnosis', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_Memory_Alert_Diagnosis;
GO

CREATE VIEW dbo.vw_OS_Memory_Alert_Diagnosis AS
SELECT
    curr.Instance,
    curr.Hostname,

    -- Current Snapshot
    curr.Available_MB AS Current_Available_MB,
    curr.Pages_Per_Sec AS Current_Pages_Sec,
    curr.Page_Reads_Sec AS Current_Page_Reads_Sec,
    curr.Percent_Committed AS Current_Percent_Committed,
    curr.Severity AS Current_Severity,

    -- 30-minute Trend
    trend.Avg_Pages_Sec AS Trend_Avg_Pages_Sec,
    trend.Max_Pages_Sec AS Trend_Max_Pages_Sec,
    trend.Avg_Page_Reads_Sec AS Trend_Avg_Page_Reads_Sec,
    trend.Max_Page_Reads_Sec AS Trend_Max_Page_Reads_Sec,
    trend.Min_Available_MB AS Trend_Min_Available_MB,
    trend.Sample_Count AS Trend_Sample_Count,
    trend.Is_Sustained AS Is_Sustained_Problem,

    -- Alert Classification
    CASE
        WHEN trend.Is_Sustained = 1 AND trend.Avg_Page_Reads_Sec > 50
        THEN 'CRITICAL: Sustained high hard page faults over 30 minutes'

        WHEN trend.Is_Sustained = 1 AND trend.Min_Available_MB < 1000
        THEN 'WARNING: Sustained low available memory over 30 minutes'

        WHEN curr.Page_Reads_Sec > 100 AND trend.Avg_Page_Reads_Sec < 50
        THEN 'INFO: Momentary spike in page faults (not sustained)'

        WHEN curr.Pages_Per_Sec > 500 AND curr.Page_Reads_Sec < 20
        THEN 'INFO: High soft page faults only - likely normal activity spike'

        ELSE 'OK: Alert may have been transient'
    END AS Alert_Classification,

    -- Is this alert actionable?
    CASE
        WHEN trend.Is_Sustained = 1 AND (trend.Avg_Page_Reads_Sec > 50 OR trend.Min_Available_MB < 1000)
        THEN 1
        ELSE 0
    END AS Is_Actionable,

    -- Recommended Response
    CASE
        WHEN trend.Is_Sustained = 1 AND trend.Avg_Page_Reads_Sec > 100 AND trend.Min_Available_MB < 500
        THEN 'IMMEDIATE ACTION: Server is experiencing memory crisis. Check for runaway processes, review SQL Server max memory setting.'

        WHEN trend.Is_Sustained = 1 AND trend.Avg_Page_Reads_Sec > 50
        THEN 'INVESTIGATE: Sustained hard page faults indicate memory pressure. Review top memory consumers (Task Manager), check SQL Server memory grants.'

        WHEN trend.Is_Sustained = 1 AND trend.Min_Available_MB < 1000
        THEN 'MONITOR: Available memory consistently low. Schedule review of server memory allocation.'

        WHEN curr.Page_Reads_Sec > 100 AND trend.Avg_Page_Reads_Sec < 50
        THEN 'ACKNOWLEDGE: This appears to be a momentary spike. Monitor for recurrence but likely self-resolved.'

        ELSE 'ACKNOWLEDGE: Alert was transient and metrics are now normal. No action required.'
    END AS Recommended_Response,

    -- Ticket Resolution Suggestion
    CASE
        WHEN trend.Is_Sustained = 1
        THEN 'Keep ticket open for investigation'
        ELSE 'Safe to close - transient alert'
    END AS Ticket_Suggestion,

    curr.Update_TS AS Snapshot_Time,
    trend.Period_Start,
    trend.Period_End

FROM dbo.vw_OS_Memory_Current curr
LEFT JOIN dbo.vw_OS_Memory_Trend_30Min trend
    ON curr.Instance = trend.Instance AND curr.Hostname = trend.Hostname;
GO

PRINT 'Created vw_OS_Memory_Alert_Diagnosis';


-- ---------------------------------------------------------------------
-- 5.2 vw_OS_Servers_Needing_Attention - Dashboard View
-- Shows all servers with active issues
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_OS_Servers_Needing_Attention', 'V') IS NOT NULL
    DROP VIEW dbo.vw_OS_Servers_Needing_Attention;
GO

CREATE VIEW dbo.vw_OS_Servers_Needing_Attention AS
SELECT
    Instance,
    Hostname,
    Overall_Health,
    Problem_Areas,
    Memory_Severity,
    Memory_Diagnosis,
    CPU_Severity,
    Disk_Severity,
    OS_Available_MB,
    OS_Page_Reads_Sec,
    OS_CPU_Pct,
    Disk_Worst_Read_Latency,
    Analysis_Time,
    -- Severity order for sorting when querying
    CASE Overall_Health
        WHEN 'CRITICAL' THEN 1
        WHEN 'WARNING' THEN 2
        ELSE 3
    END AS Severity_Order
FROM dbo.vw_OS_SQL_Full_Correlation
WHERE Overall_Health IN ('CRITICAL', 'WARNING');
GO

PRINT 'Created vw_OS_Servers_Needing_Attention';


-- =====================================================================
-- SECTION 6: SUMMARY
-- =====================================================================
PRINT '';
PRINT '========================================';
PRINT 'OS Performance Views Created Successfully';
PRINT '========================================';
PRINT '';
PRINT 'Views Created:';
PRINT '  - vw_OS_Memory_Trend_30Min (Memory trend analysis)';
PRINT '  - vw_OS_Memory_Current (Current memory status)';
PRINT '  - vw_OS_CPU_Trend_30Min (CPU trend analysis)';
PRINT '  - vw_OS_CPU_Current (Current CPU status)';
PRINT '  - vw_OS_Disk_Current (Current disk performance)';
PRINT '  - vw_OS_SQL_Memory_Correlation (OS + SQL memory correlation)';
PRINT '  - vw_OS_SQL_Full_Correlation (Complete OS + SQL correlation)';
PRINT '  - vw_OS_Memory_Alert_Diagnosis (For SCOM memory alerts)';
PRINT '  - vw_OS_Servers_Needing_Attention (Dashboard view)';
PRINT '';
PRINT 'Key View for Memory Alerts:';
PRINT '  SELECT * FROM vw_OS_Memory_Alert_Diagnosis';
PRINT '  WHERE Hostname = ''SQLHDSPRD014''';
PRINT '';
GO


-- =====================================================================
-- KPI_OS_COLLECTION_PROCEDURES.sql
-- WatcherDB Intelligence - OS KPI Collection Integration
--
-- Purpose: Procedures for managing OS performance KPI collection
--          and integrating with the existing SQL Server KPI collection.
--
-- Target Database: SQLHDSTST505\I01 - WatcherDB_Intelligence
-- Author: WatcherDB Intelligence Team
-- Date: 2025-12-15
-- Version: 1.0.0
-- =====================================================================

USE [WatcherDB_Intelligence];
GO

PRINT '========================================';
PRINT 'Creating OS KPI Collection Procedures';
PRINT '========================================';
PRINT '';

-- =====================================================================
-- SECTION 1: FULL COLLECTION ORCHESTRATION
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1.1 usp_OS_Collect_Full - Master procedure for full OS collection
-- This is the main entry point for collecting all OS metrics
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Collect_Full', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Collect_Full;
GO

CREATE PROCEDURE dbo.usp_OS_Collect_Full
    @ServerList NVARCHAR(MAX) = NULL,   -- Comma-separated list or NULL for all
    @CollectMemory BIT = 1,
    @CollectCPU BIT = 1,
    @CollectDisk BIT = 1,
    @TimeoutSeconds INT = 30,
    @Debug BIT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @StartTime DATETIME2 = GETDATE();
    DECLARE @EndTime DATETIME2;
    DECLARE @ServerCount INT = 0;
    DECLARE @SuccessCount INT = 0;
    DECLARE @ErrorCount INT = 0;

    -- Log start
    IF @Debug = 1
        PRINT 'Starting OS Performance Collection at ' + CONVERT(VARCHAR, @StartTime, 121);

    -- Create temp table for servers to process
    CREATE TABLE #ServersToCollect (
        ServerID INT IDENTITY(1,1),
        Instance VARCHAR(64),
        Hostname VARCHAR(64),
        Processed BIT DEFAULT 0,
        Success BIT DEFAULT 0,
        ErrorMessage NVARCHAR(MAX) NULL
    );

    -- Populate server list
    IF @ServerList IS NULL
    BEGIN
        -- Get all servers from inventory (adjust table name as needed)
        INSERT INTO #ServersToCollect (Instance, Hostname)
        SELECT DISTINCT
            Instance_ID,
            Hostname
        FROM dbo.SERVER_INVENTORY  -- Adjust to your actual inventory table
        WHERE Is_Active = 1;

        IF @Debug = 1
            PRINT 'Loaded all active servers from inventory';
    END
    ELSE
    BEGIN
        -- Parse comma-separated list
        INSERT INTO #ServersToCollect (Instance, Hostname)
        SELECT
            LTRIM(RTRIM(value)) AS Instance,
            PARSENAME(REPLACE(LTRIM(RTRIM(value)), '_', '.'), 2) AS Hostname
        FROM STRING_SPLIT(@ServerList, ',');

        IF @Debug = 1
            PRINT 'Loaded ' + CAST(@@ROWCOUNT AS VARCHAR) + ' servers from parameter';
    END

    SELECT @ServerCount = COUNT(*) FROM #ServersToCollect;

    IF @Debug = 1
        PRINT 'Total servers to process: ' + CAST(@ServerCount AS VARCHAR);

    -- Note: Actual collection happens via Python/PowerShell
    -- This procedure provides the framework and can be called from SQL Agent
    -- The actual data collection is performed by:
    -- 1. PowerShell script: Collect-OSPerformance.ps1
    -- 2. Python module: os_performance.py

    -- For SQL Agent integration, call the PowerShell script:
    -- EXEC master.dbo.xp_cmdshell 'powershell -File "C:\Scripts\Collect-OSPerformance.ps1" -Parallel'

    -- Return server list for external processing
    SELECT
        Instance,
        Hostname,
        @CollectMemory AS CollectMemory,
        @CollectCPU AS CollectCPU,
        @CollectDisk AS CollectDisk
    FROM #ServersToCollect;

    -- Log completion
    SET @EndTime = GETDATE();

    IF @Debug = 1
    BEGIN
        PRINT '';
        PRINT 'Collection orchestration completed';
        PRINT 'Duration: ' + CAST(DATEDIFF(SECOND, @StartTime, @EndTime) AS VARCHAR) + ' seconds';
    END

    -- Cleanup
    DROP TABLE #ServersToCollect;

    -- Return summary
    SELECT
        @ServerCount AS TotalServers,
        @StartTime AS StartTime,
        @EndTime AS EndTime,
        DATEDIFF(SECOND, @StartTime, @EndTime) AS DurationSeconds;
END;
GO

PRINT 'Created usp_OS_Collect_Full';


-- ---------------------------------------------------------------------
-- 1.2 usp_OS_Collect_Server - Collect OS metrics for a single server
-- Uses xp_cmdshell to run PowerShell (requires appropriate permissions)
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Collect_Server', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Collect_Server;
GO

CREATE PROCEDURE dbo.usp_OS_Collect_Server
    @Hostname VARCHAR(64),
    @Instance VARCHAR(64),
    @TimeoutSeconds INT = 30
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @cmd NVARCHAR(4000);
    DECLARE @PowerShellScript NVARCHAR(MAX);

    -- Build PowerShell command to collect metrics via WMI
    SET @PowerShellScript = N'
$hostname = "' + @Hostname + N'"
$instance = "' + @Instance + N'"
$sqlInstance = "SQLHDSTST505\I01"
$database = "WatcherDB_Intelligence"

try {
    # Get OS info
    $os = Get-WmiObject -Class Win32_OperatingSystem -ComputerName $hostname -ErrorAction Stop
    $perf = Get-WmiObject -Class Win32_PerfFormattedData_PerfOS_Memory -ComputerName $hostname -ErrorAction Stop

    # Prepare values
    $totalMB = [math]::Round($os.TotalVisibleMemorySize / 1024, 2)
    $availableMB = $perf.AvailableMBytes
    $pagesSec = $perf.PagesPerSec
    $pageReadsSec = $perf.PageReadsPersec
    $pageWritesSec = $perf.PageWritesPersec

    # Build SQL
    $sql = @"
EXEC dbo.usp_OS_Memory_Upsert
    @Instance = ''$instance'',
    @Hostname = ''$hostname'',
    @Available_MB = $availableMB,
    @Total_Physical_MB = $totalMB,
    @Pages_Per_Sec = $pagesSec,
    @Page_Reads_Sec = $pageReadsSec,
    @Page_Writes_Sec = $pageWritesSec,
    @Collection_Method = ''xp_cmdshell''
"@

    # Execute SQL
    Invoke-Sqlcmd -ServerInstance $sqlInstance -Database $database -Query $sql -QueryTimeout 30

    Write-Output "SUCCESS: $hostname"
}
catch {
    Write-Output "ERROR: $hostname - $($_.Exception.Message)"
}
';

    -- Execute PowerShell via xp_cmdshell
    SET @cmd = N'powershell -NoProfile -Command "' + REPLACE(@PowerShellScript, '"', '\"') + N'"';

    -- Note: xp_cmdshell must be enabled
    -- EXEC sp_configure 'xp_cmdshell', 1; RECONFIGURE;

    CREATE TABLE #Output (line NVARCHAR(4000));

    INSERT INTO #Output
    EXEC master.dbo.xp_cmdshell @cmd;

    -- Return results
    SELECT * FROM #Output WHERE line IS NOT NULL;

    DROP TABLE #Output;
END;
GO

PRINT 'Created usp_OS_Collect_Server';


-- =====================================================================
-- SECTION 2: DATA QUALITY AND MAINTENANCE
-- =====================================================================

-- ---------------------------------------------------------------------
-- 2.1 usp_OS_Check_Stale_Data - Check for servers with stale data
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Check_Stale_Data', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Check_Stale_Data;
GO

CREATE PROCEDURE dbo.usp_OS_Check_Stale_Data
    @StaleMinutes INT = 15,
    @AlertIfStale BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        m.Instance,
        m.Hostname,
        m.Update_TS AS LastUpdate,
        DATEDIFF(MINUTE, m.Update_TS, GETDATE()) AS MinutesSinceUpdate,
        m.Severity AS LastSeverity,
        m.Available_MB AS LastAvailableMB,
        m.Page_Reads_Sec AS LastPageReadsSec,
        CASE
            WHEN DATEDIFF(MINUTE, m.Update_TS, GETDATE()) > @StaleMinutes
            THEN 'STALE'
            ELSE 'CURRENT'
        END AS DataStatus
    FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK) m
    WHERE DATEDIFF(MINUTE, m.Update_TS, GETDATE()) > @StaleMinutes
    ORDER BY DATEDIFF(MINUTE, m.Update_TS, GETDATE()) DESC;

    -- Count stale servers
    DECLARE @StaleCount INT;
    SELECT @StaleCount = COUNT(*)
    FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK)
    WHERE DATEDIFF(MINUTE, Update_TS, GETDATE()) > @StaleMinutes;

    IF @AlertIfStale = 1 AND @StaleCount > 0
    BEGIN
        RAISERROR('WARNING: %d servers have stale OS performance data (older than %d minutes)', 10, 1, @StaleCount, @StaleMinutes);
    END

    -- Return summary
    SELECT
        @StaleCount AS StaleServerCount,
        (SELECT COUNT(*) FROM dbo.KPI_OS_MEMORY_STG) AS TotalServers,
        @StaleMinutes AS StaleThresholdMinutes;
END;
GO

PRINT 'Created usp_OS_Check_Stale_Data';


-- ---------------------------------------------------------------------
-- 2.2 usp_OS_Get_Problem_Servers - Get servers with current problems
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Get_Problem_Servers', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Get_Problem_Servers;
GO

CREATE PROCEDURE dbo.usp_OS_Get_Problem_Servers
    @IncludeCritical BIT = 1,
    @IncludeWarning BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        m.Instance,
        m.Hostname,
        m.Available_MB,
        m.Page_Reads_Sec,
        m.Pages_Per_Sec,
        m.Percent_Committed,
        m.Severity,
        m.Update_TS,
        -- Classification details
        CASE
            WHEN m.Available_MB < 500 THEN 'CRITICAL: Very low available memory'
            WHEN m.Available_MB < 1000 THEN 'WARNING: Low available memory'
            ELSE 'OK'
        END AS MemoryStatus,
        CASE
            WHEN m.Page_Reads_Sec > 100 THEN 'CRITICAL: Very high hard page faults'
            WHEN m.Page_Reads_Sec > 50 THEN 'WARNING: Elevated hard page faults'
            ELSE 'OK'
        END AS PagingStatus
    FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK) m
    WHERE
        (@IncludeCritical = 1 AND m.Severity = 'CRITICAL')
        OR (@IncludeWarning = 1 AND m.Severity = 'WARNING')
    ORDER BY
        CASE m.Severity
            WHEN 'CRITICAL' THEN 1
            WHEN 'WARNING' THEN 2
            ELSE 3
        END,
        m.Available_MB ASC;
END;
GO

PRINT 'Created usp_OS_Get_Problem_Servers';


-- =====================================================================
-- SECTION 3: REPORTING AND ANALYSIS
-- =====================================================================

-- ---------------------------------------------------------------------
-- 3.1 usp_OS_Get_Server_Report - Comprehensive report for a server
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Get_Server_Report', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Get_Server_Report;
GO

CREATE PROCEDURE dbo.usp_OS_Get_Server_Report
    @Hostname VARCHAR(64),
    @Instance VARCHAR(64) = NULL,
    @IncludeTrend BIT = 1,
    @TrendMinutes INT = 60
AS
BEGIN
    SET NOCOUNT ON;

    -- Default instance if not provided
    IF @Instance IS NULL
        SET @Instance = @Hostname + '_I01';

    -- Current Memory Status
    SELECT
        'CURRENT_MEMORY' AS Section,
        m.*
    FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK) m
    WHERE m.Hostname = @Hostname;

    -- Current CPU Status
    SELECT
        'CURRENT_CPU' AS Section,
        c.*
    FROM dbo.KPI_OS_CPU_STG WITH (NOLOCK) c
    WHERE c.Hostname = @Hostname;

    -- Current Disk Status
    SELECT
        'CURRENT_DISK' AS Section,
        d.*
    FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK) d
    WHERE d.Hostname = @Hostname;

    -- Memory Trend (if requested)
    IF @IncludeTrend = 1
    BEGIN
        SELECT
            'MEMORY_TREND' AS Section,
            Instance,
            Hostname,
            COUNT(*) AS SampleCount,
            MIN(Available_MB) AS MinAvailableMB,
            AVG(Available_MB) AS AvgAvailableMB,
            MAX(Available_MB) AS MaxAvailableMB,
            AVG(Pages_Per_Sec) AS AvgPagesSec,
            MAX(Pages_Per_Sec) AS MaxPagesSec,
            AVG(Page_Reads_Sec) AS AvgPageReadsSec,
            MAX(Page_Reads_Sec) AS MaxPageReadsSec,
            MIN(Update_TS) AS PeriodStart,
            MAX(Update_TS) AS PeriodEnd
        FROM dbo.KPI_OS_MEMORY_HIST WITH (NOLOCK)
        WHERE Hostname = @Hostname
          AND Update_TS >= DATEADD(MINUTE, -@TrendMinutes, GETDATE())
        GROUP BY Instance, Hostname;
    END

    -- Correlation with SQL Server (if available)
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME = 'vw_OS_SQL_Memory_Correlation')
    BEGIN
        SELECT
            'OS_SQL_CORRELATION' AS Section,
            *
        FROM dbo.vw_OS_SQL_Memory_Correlation
        WHERE Hostname = @Hostname;
    END
END;
GO

PRINT 'Created usp_OS_Get_Server_Report';


-- ---------------------------------------------------------------------
-- 3.2 usp_OS_Diagnose_Alert - Generate diagnosis for an alert
-- This is the SQL-based alternative to the Python API
-- ---------------------------------------------------------------------
IF OBJECT_ID('dbo.usp_OS_Diagnose_Alert', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_OS_Diagnose_Alert;
GO

CREATE PROCEDURE dbo.usp_OS_Diagnose_Alert
    @Hostname VARCHAR(64),
    @Instance VARCHAR(64) = NULL,
    @AlertType VARCHAR(128) = 'Memory Pages Per Second is too High'
AS
BEGIN
    SET NOCOUNT ON;

    -- Default instance
    IF @Instance IS NULL
        SET @Instance = @Hostname + '_I01';

    DECLARE @CurrentAvailableMB DECIMAL(18,2);
    DECLARE @CurrentPageReadsSec DECIMAL(18,2);
    DECLARE @CurrentPagesSec DECIMAL(18,2);
    DECLARE @CurrentSeverity VARCHAR(16);

    DECLARE @TrendAvgPageReadsSec DECIMAL(18,2);
    DECLARE @TrendMinAvailableMB DECIMAL(18,2);
    DECLARE @TrendSampleCount INT;
    DECLARE @TrendIsSustained BIT;

    DECLARE @RootCause NVARCHAR(512);
    DECLARE @RootCauseCategory VARCHAR(64);
    DECLARE @Diagnosis NVARCHAR(MAX);
    DECLARE @IsActionable BIT = 0;

    -- Get current metrics
    SELECT
        @CurrentAvailableMB = Available_MB,
        @CurrentPageReadsSec = Page_Reads_Sec,
        @CurrentPagesSec = Pages_Per_Sec,
        @CurrentSeverity = Severity
    FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK)
    WHERE Hostname = @Hostname;

    -- Get trend (30 minutes)
    SELECT
        @TrendAvgPageReadsSec = AVG(Page_Reads_Sec),
        @TrendMinAvailableMB = MIN(Available_MB),
        @TrendSampleCount = COUNT(*),
        @TrendIsSustained = CASE
            WHEN SUM(CASE WHEN Page_Reads_Sec > 50 OR Available_MB < 1000 THEN 1 ELSE 0 END) > COUNT(*) / 2
            THEN 1 ELSE 0
        END
    FROM dbo.KPI_OS_MEMORY_HIST WITH (NOLOCK)
    WHERE Hostname = @Hostname
      AND Update_TS >= DATEADD(MINUTE, -30, GETDATE());

    -- Determine root cause
    IF @CurrentAvailableMB < 500 AND @CurrentPageReadsSec > 50
    BEGIN
        SET @RootCause = 'OS memory exhaustion causing excessive paging to disk';
        SET @RootCauseCategory = 'OS_MEMORY_EXHAUSTION';
        SET @IsActionable = 1;
    END
    ELSE IF @CurrentPageReadsSec > 100
    BEGIN
        SET @RootCause = 'Very high hard page fault rate - memory being read from disk';
        SET @RootCauseCategory = 'EXCESSIVE_PAGING';
        SET @IsActionable = 1;
    END
    ELSE IF @TrendIsSustained = 1 AND @TrendAvgPageReadsSec > 50
    BEGIN
        SET @RootCause = 'Sustained high hard page faults over 30 minutes';
        SET @RootCauseCategory = 'EXCESSIVE_PAGING';
        SET @IsActionable = 1;
    END
    ELSE IF @CurrentPagesSec > 500 AND @CurrentPageReadsSec < 20
    BEGIN
        SET @RootCause = 'High soft page faults only - likely normal activity spike';
        SET @RootCauseCategory = 'NORMAL';
        SET @IsActionable = 0;
    END
    ELSE
    BEGIN
        SET @RootCause = 'Metrics within normal parameters or transient spike';
        SET @RootCauseCategory = 'NORMAL';
        SET @IsActionable = 0;
    END

    -- Build diagnosis
    SET @Diagnosis = 'Current State: Available=' + CAST(@CurrentAvailableMB AS VARCHAR) + 'MB, ' +
                     'PageReads=' + CAST(@CurrentPageReadsSec AS VARCHAR) + '/sec. ' +
                     'Trend (30min): AvgPageReads=' + CAST(ISNULL(@TrendAvgPageReadsSec, 0) AS VARCHAR) + '/sec, ' +
                     'MinAvailable=' + CAST(ISNULL(@TrendMinAvailableMB, 0) AS VARCHAR) + 'MB. ' +
                     CASE WHEN @TrendIsSustained = 1 THEN 'SUSTAINED ISSUE.' ELSE 'NOT sustained.' END;

    -- Return diagnosis
    SELECT
        @Hostname AS Server,
        @Instance AS Instance,
        @AlertType AS AlertContext,
        GETDATE() AS Timestamp,
        @CurrentAvailableMB AS CurrentAvailableMB,
        @CurrentPageReadsSec AS CurrentPageReadsSec,
        @CurrentPagesSec AS CurrentPagesSec,
        @CurrentSeverity AS CurrentSeverity,
        @TrendAvgPageReadsSec AS TrendAvgPageReadsSec,
        @TrendMinAvailableMB AS TrendMinAvailableMB,
        @TrendSampleCount AS TrendSampleCount,
        @TrendIsSustained AS TrendIsSustained,
        @RootCause AS RootCause,
        @RootCauseCategory AS RootCauseCategory,
        @Diagnosis AS Diagnosis,
        @IsActionable AS IsActionable;

    -- Return recommendations
    SELECT
        CASE @RootCauseCategory
            WHEN 'OS_MEMORY_EXHAUSTION' THEN
                '1. Check Task Manager for non-SQL processes consuming memory
2. Review SQL Server max server memory setting
3. Check for memory leaks in applications
4. Consider adding RAM if consistently under pressure'
            WHEN 'EXCESSIVE_PAGING' THEN
                '1. Identify top memory consumers using Resource Monitor
2. Check SQL Server memory grants pending
3. Review recent deployments that may have increased memory usage
4. Consider restarting memory-leaking services if identified'
            ELSE
                'Alert appears transient - safe to acknowledge. Monitor for recurrence.'
        END AS Recommendations;

    -- Log diagnosis
    INSERT INTO dbo.KPI_OS_DIAGNOSIS_LOG
        (Instance, Hostname, Alert_Type, Severity, Root_Cause, Root_Cause_Category, Diagnosis_Summary)
    VALUES
        (@Instance, @Hostname, @AlertType, @CurrentSeverity, @RootCause, @RootCauseCategory, @Diagnosis);
END;
GO

PRINT 'Created usp_OS_Diagnose_Alert';


-- =====================================================================
-- SECTION 4: SQL AGENT JOB SCRIPTS
-- =====================================================================

PRINT '';
PRINT '========================================';
PRINT 'SQL Agent Job Script (Manual Creation)';
PRINT '========================================';
PRINT '';
PRINT 'Create a SQL Agent Job with these steps:';
PRINT '';
PRINT 'Step 1: PowerShell Collection';
PRINT '  Type: Operating system (CmdExec)';
PRINT '  Command: powershell -NoProfile -ExecutionPolicy Bypass -File "C:\WatcherDB\Scripts\Collect-OSPerformance.ps1" -Parallel -MaxParallel 20';
PRINT '';
PRINT 'Step 2: Check for Stale Data';
PRINT '  Type: T-SQL';
PRINT '  Command: EXEC dbo.usp_OS_Check_Stale_Data @StaleMinutes = 15, @AlertIfStale = 1';
PRINT '';
PRINT 'Schedule: Every 5 minutes';
PRINT '';


-- =====================================================================
-- SECTION 5: SUMMARY
-- =====================================================================
PRINT '';
PRINT '========================================';
PRINT 'OS KPI Collection Procedures Created';
PRINT '========================================';
PRINT '';
PRINT 'Procedures Created:';
PRINT '  - usp_OS_Collect_Full (Orchestration)';
PRINT '  - usp_OS_Collect_Server (Single server)';
PRINT '  - usp_OS_Check_Stale_Data (Data quality)';
PRINT '  - usp_OS_Get_Problem_Servers (Alert dashboard)';
PRINT '  - usp_OS_Get_Server_Report (Comprehensive report)';
PRINT '  - usp_OS_Diagnose_Alert (Alert diagnosis)';
PRINT '';
PRINT 'Usage Examples:';
PRINT '  -- Diagnose a memory alert';
PRINT '  EXEC dbo.usp_OS_Diagnose_Alert @Hostname = ''SQLHDSPRD014'';';
PRINT '';
PRINT '  -- Get all problem servers';
PRINT '  EXEC dbo.usp_OS_Get_Problem_Servers;';
PRINT '';
PRINT '  -- Check for stale data';
PRINT '  EXEC dbo.usp_OS_Check_Stale_Data @StaleMinutes = 15;';
PRINT '';
GO


-- =====================================================================
-- SECTION 6: COLLECTION HISTORY (Historico de Coletas)
-- =====================================================================
-- Tabelas e views para rastreamento de cada execucao de coleta Python
-- Permite analise de tendencias e identificacao de problemas recorrentes
-- Adicionado em: 2025-12-18
-- =====================================================================

PRINT '';
PRINT '========================================';
PRINT 'Collection History Tables';
PRINT '========================================';
PRINT '';

-- ============================================================================
-- 6.1 TABELA PRINCIPAL: KPI_MSSQL_COLLECTION_HISTORY
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.KPI_MSSQL_COLLECTION_HISTORY') AND type = 'U')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_COLLECTION_HISTORY (
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

        SWAP_Success_Count      INT NOT NULL DEFAULT 0,
        SWAP_Failed_Count       INT NOT NULL DEFAULT 0,
        SWAP_Skipped            BIT NOT NULL DEFAULT 0,

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
    PRINT '  Created: KPI_MSSQL_COLLECTION_HISTORY';
END
ELSE
    PRINT '  Exists: KPI_MSSQL_COLLECTION_HISTORY';
GO

-- Indices
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_History_Start')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_History_Start
    ON dbo.KPI_MSSQL_COLLECTION_HISTORY (Collection_Start DESC)
    INCLUDE (Mode, Servers_Configured, Servers_Online, Servers_Skipped, Success_Rate_Pct);
    PRINT '  Created: IX_Collection_History_Start';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_History_Mode')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_History_Mode
    ON dbo.KPI_MSSQL_COLLECTION_HISTORY (Mode, Collection_Start DESC);
    PRINT '  Created: IX_Collection_History_Mode';
END
GO

-- ============================================================================
-- 6.2 TABELA DE DETALHES POR SERVIDOR
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'dbo.KPI_MSSQL_COLLECTION_SERVER_DETAILS') AND type = 'U')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_COLLECTION_SERVER_DETAILS (
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
            REFERENCES dbo.KPI_MSSQL_COLLECTION_HISTORY(Collection_ID)
            ON DELETE CASCADE
    );
    PRINT '  Created: KPI_MSSQL_COLLECTION_SERVER_DETAILS';
END
ELSE
    PRINT '  Exists: KPI_MSSQL_COLLECTION_SERVER_DETAILS';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_Server_Details_ServerID')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_Server_Details_ServerID
    ON dbo.KPI_MSSQL_COLLECTION_SERVER_DETAILS (Server_ID, Collection_ID DESC);
    PRINT '  Created: IX_Collection_Server_Details_ServerID';
END
GO

-- ============================================================================
-- 6.3 VIEWS DE ANALISE
-- ============================================================================

IF OBJECT_ID('dbo.VW_COLLECTION_HISTORY_SUMMARY', 'V') IS NOT NULL
    DROP VIEW dbo.VW_COLLECTION_HISTORY_SUMMARY;
GO

CREATE VIEW dbo.VW_COLLECTION_HISTORY_SUMMARY AS
SELECT TOP 100
    Collection_ID, Collection_Start, Collection_End, Duration_Seconds, Mode,
    Servers_Configured, Servers_Online, Servers_Skipped, Servers_With_Errors, Success_Rate_Pct,
    Servers_Ping_Failed, Servers_SQL_Down, SWAP_Success_Count, SWAP_Failed_Count,
    Total_KPIs_Collected, Total_Rows_Inserted, Avg_Query_Time_MS, Max_Query_Time_MS,
    CASE
        WHEN Servers_Skipped > 0 OR Servers_With_Errors > 0 THEN 'WARNING'
        WHEN SWAP_Failed_Count > 0 THEN 'WARNING'
        WHEN Success_Rate_Pct < 95 THEN 'WARNING'
        ELSE 'OK'
    END AS Health_Status
FROM dbo.KPI_MSSQL_COLLECTION_HISTORY
ORDER BY Collection_Start DESC;
GO

PRINT '  Created: VW_COLLECTION_HISTORY_SUMMARY';
GO

IF OBJECT_ID('dbo.VW_PROBLEMATIC_SERVERS', 'V') IS NOT NULL
    DROP VIEW dbo.VW_PROBLEMATIC_SERVERS;
GO

CREATE VIEW dbo.VW_PROBLEMATIC_SERVERS AS
SELECT
    d.Server_ID,
    COUNT(*) AS Total_Collections,
    SUM(CASE WHEN d.Status = 'success' THEN 1 ELSE 0 END) AS Success_Count,
    SUM(CASE WHEN d.Status = 'skipped' THEN 1 ELSE 0 END) AS Skipped_Count,
    SUM(CASE WHEN d.Status = 'error' THEN 1 ELSE 0 END) AS Error_Count,
    SUM(CASE WHEN d.Status = 'partial' THEN 1 ELSE 0 END) AS Partial_Count,
    CAST(SUM(CASE WHEN d.Status = 'success' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS DECIMAL(5,2)) AS Success_Rate_Pct,
    AVG(d.Connection_Time_MS) AS Avg_Connection_MS,
    MAX(d.Connection_Time_MS) AS Max_Connection_MS,
    MAX(d.Skip_Reason) AS Skip_Reason,
    MAX(h.Collection_Start) AS Last_Collection
FROM dbo.KPI_MSSQL_COLLECTION_SERVER_DETAILS d
INNER JOIN dbo.KPI_MSSQL_COLLECTION_HISTORY h ON d.Collection_ID = h.Collection_ID
WHERE h.Collection_Start >= DATEADD(DAY, -7, GETDATE())
GROUP BY d.Server_ID
HAVING SUM(CASE WHEN d.Status IN ('skipped', 'error') THEN 1 ELSE 0 END) > 0;
GO

PRINT '  Created: VW_PROBLEMATIC_SERVERS';
GO

IF OBJECT_ID('dbo.VW_COLLECTION_DAILY_TREND', 'V') IS NOT NULL
    DROP VIEW dbo.VW_COLLECTION_DAILY_TREND;
GO

CREATE VIEW dbo.VW_COLLECTION_DAILY_TREND AS
SELECT
    CAST(Collection_Start AS DATE) AS Collection_Date,
    COUNT(*) AS Total_Collections,
    AVG(Servers_Configured) AS Avg_Servers_Configured,
    AVG(Servers_Online) AS Avg_Servers_Online,
    AVG(Servers_Skipped) AS Avg_Servers_Skipped,
    AVG(Success_Rate_Pct) AS Avg_Success_Rate_Pct,
    AVG(Duration_Seconds) AS Avg_Duration_Seconds,
    AVG(Avg_Query_Time_MS) AS Avg_Query_Time_MS,
    SUM(Total_Rows_Inserted) AS Total_Rows_Inserted,
    SUM(Servers_Ping_Failed) AS Total_Ping_Failed,
    SUM(Servers_SQL_Down) AS Total_SQL_Down
FROM dbo.KPI_MSSQL_COLLECTION_HISTORY
WHERE Collection_Start >= DATEADD(DAY, -30, GETDATE())
GROUP BY CAST(Collection_Start AS DATE);
GO

PRINT '  Created: VW_COLLECTION_DAILY_TREND';
GO

-- ============================================================================
-- 6.4 PROCEDURE DE LIMPEZA
-- ============================================================================

IF OBJECT_ID('dbo.usp_Purge_Collection_History', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Purge_Collection_History;
GO

CREATE PROCEDURE dbo.usp_Purge_Collection_History
    @retention_days INT = 90
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @cutoff_date DATETIME2 = DATEADD(DAY, -@retention_days, GETDATE());
    DECLARE @rows_deleted INT;

    DELETE FROM dbo.KPI_MSSQL_COLLECTION_SERVER_DETAILS
    WHERE Collection_ID IN (
        SELECT Collection_ID FROM dbo.KPI_MSSQL_COLLECTION_HISTORY
        WHERE Collection_Start < @cutoff_date
    );
    SET @rows_deleted = @@ROWCOUNT;
    PRINT 'Details deleted: ' + CAST(@rows_deleted AS VARCHAR(10));

    DELETE FROM dbo.KPI_MSSQL_COLLECTION_HISTORY
    WHERE Collection_Start < @cutoff_date;
    SET @rows_deleted = @@ROWCOUNT;
    PRINT 'History deleted: ' + CAST(@rows_deleted AS VARCHAR(10));
END;
GO

PRINT '  Created: usp_Purge_Collection_History';
GO

PRINT '';
PRINT '  Collection History installation complete!';
PRINT '';
GO

-- ============================================================================
-- SECTION 7: SERVER OFFLINE EVENTS TABLE
-- ============================================================================
-- Tabela para registrar eventos de servidor offline ou SQL parado
-- Usada para diagnÃ³stico e alimentaÃ§Ã£o do card de SQL Services Off no dashboard
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'SECTION 7: SERVER OFFLINE EVENTS TABLE';
PRINT '============================================================================';
GO

-- ============================================================================
-- 7.1 TABELA: KPI_MSSQL_SERVER_OFFLINE_EVENTS
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPI_MSSQL_SERVER_OFFLINE_EVENTS')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS (
        Event_ID INT IDENTITY(1,1) PRIMARY KEY,
        Server_Name NVARCHAR(256) NOT NULL,
        Diagnosis NVARCHAR(50) NOT NULL,  -- 'offline', 'sql_down', 'partial', 'online'
        Ping_OK BIT NOT NULL,
        Ping_Message NVARCHAR(500),
        Services_Down NVARCHAR(1000),     -- Lista de serviÃ§os SQL parados (separados por vÃ­rgula)
        Event_Time DATETIME2 NOT NULL DEFAULT GETDATE(),
        Resolved_Time DATETIME2 NULL,
        Is_Resolved BIT NOT NULL DEFAULT 0
    );

    CREATE INDEX IX_ServerOffline_Server ON dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS(Server_Name);
    CREATE INDEX IX_ServerOffline_Time ON dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS(Event_Time DESC);
    CREATE INDEX IX_ServerOffline_Unresolved ON dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS(Is_Resolved) WHERE Is_Resolved = 0;

    PRINT '  Created: KPI_MSSQL_SERVER_OFFLINE_EVENTS';
END
ELSE
BEGIN
    PRINT '  Exists: KPI_MSSQL_SERVER_OFFLINE_EVENTS';
END
GO

-- ============================================================================
-- 7.2 VIEW: vw_ServerOfflineEvents_Active
-- ============================================================================

IF OBJECT_ID('dbo.vw_ServerOfflineEvents_Active', 'V') IS NOT NULL
    DROP VIEW dbo.vw_ServerOfflineEvents_Active;
GO

CREATE VIEW dbo.vw_ServerOfflineEvents_Active
AS
SELECT
    Event_ID,
    Server_Name,
    Diagnosis,
    Ping_OK,
    Ping_Message,
    Services_Down,
    Event_Time,
    DATEDIFF(MINUTE, Event_Time, GETDATE()) AS Minutes_Since_Event
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
WHERE Is_Resolved = 0;
GO

PRINT '  Created: vw_ServerOfflineEvents_Active';
GO

-- ============================================================================
-- 7.3 PROCEDURE: usp_ResolveServerOfflineEvent
-- ============================================================================

IF OBJECT_ID('dbo.usp_ResolveServerOfflineEvent', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_ResolveServerOfflineEvent;
GO

CREATE PROCEDURE dbo.usp_ResolveServerOfflineEvent
    @Server_Name NVARCHAR(256) = NULL,
    @Event_ID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @Event_ID IS NOT NULL
    BEGIN
        UPDATE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
        SET Is_Resolved = 1,
            Resolved_Time = GETDATE()
        WHERE Event_ID = @Event_ID;
    END
    ELSE IF @Server_Name IS NOT NULL
    BEGIN
        -- Resolver todos os eventos nÃ£o resolvidos do servidor
        UPDATE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
        SET Is_Resolved = 1,
            Resolved_Time = GETDATE()
        WHERE Server_Name = @Server_Name
          AND Is_Resolved = 0;
    END

    SELECT @@ROWCOUNT AS Events_Resolved;
END;
GO

PRINT '  Created: usp_ResolveServerOfflineEvent';
GO

-- ============================================================================
-- 7.3.1 PROCEDURE: usp_MSSQL_Server_Offline_Upsert (NOVO - padrao UPSERT)
-- ============================================================================
-- Usa MERGE para atualizar evento existente ou inserir novo
-- Evita acumulo de eventos duplicados para o mesmo servidor

IF OBJECT_ID('dbo.usp_MSSQL_Server_Offline_Upsert', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_MSSQL_Server_Offline_Upsert;
GO

CREATE PROCEDURE dbo.usp_MSSQL_Server_Offline_Upsert
    @Server_Name NVARCHAR(256),
    @Diagnosis NVARCHAR(50),
    @Ping_OK BIT,
    @Ping_Message NVARCHAR(500) = NULL,
    @Services_Down NVARCHAR(1000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- MERGE: Se existe evento nao resolvido, atualiza. Senao, insere novo.
    MERGE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS AS target
    USING (SELECT @Server_Name AS Server_Name) AS source
    ON target.Server_Name = source.Server_Name AND target.Is_Resolved = 0
    WHEN MATCHED THEN
        UPDATE SET
            Diagnosis = @Diagnosis,
            Ping_OK = @Ping_OK,
            Ping_Message = @Ping_Message,
            Services_Down = @Services_Down,
            Event_Time = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down, Event_Time, Is_Resolved)
        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down, GETDATE(), 0);
END;
GO

PRINT '  Created: usp_MSSQL_Server_Offline_Upsert';
GO

-- ============================================================================
-- 7.4 PROCEDURE: usp_CleanupServerOfflineEvents
-- ============================================================================

IF OBJECT_ID('dbo.usp_CleanupServerOfflineEvents', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_CleanupServerOfflineEvents;
GO

CREATE PROCEDURE dbo.usp_CleanupServerOfflineEvents
    @RetentionDays INT = 90
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
    WHERE Event_Time < DATEADD(DAY, -@RetentionDays, GETDATE());

    SELECT @@ROWCOUNT AS Events_Deleted;
END;
GO

PRINT '  Created: usp_CleanupServerOfflineEvents';
GO

PRINT '';
PRINT '  Server Offline Events installation complete!';
PRINT '';
GO
-- ============================================================================
-- SECAO 8: VIEWS AGREGADAS SERVER_OFFLINE (AGG + DET)
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'SECAO 8: SERVER OFFLINE AGG/DET VIEWS';
PRINT '============================================================================';
GO

IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
GO

-- VIEW DE RESUMO GERAL - Retorna 1 unica linha com contadores de SERVIDORES UNICOS
-- Latest-state semantics: so conta servidores cujo ULTIMO evento na janela de 15 min
-- tem Diagnosis negativo. Evita mostrar eventos fantasma (collector nao auto-resolve).
CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW
AS
WITH LatestEventPerServer AS (
    SELECT
        Server_Name,
        MAX(Event_Time) AS Last_Event_Time
    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
    WHERE Event_Time >= DATEADD(MINUTE, -15, GETDATE())
      AND Is_Resolved = 0
    GROUP BY Server_Name
),
LatestStatus AS (
    SELECT
        soe.Server_Name,
        soe.Diagnosis,
        soe.Event_Time
    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS soe WITH (NOLOCK)
    INNER JOIN LatestEventPerServer le
        ON le.Server_Name = soe.Server_Name
       AND le.Last_Event_Time = soe.Event_Time
    WHERE soe.Diagnosis IN ('offline', 'sql_down', 'partial')
)
SELECT
    COUNT(DISTINCT CASE WHEN Diagnosis = 'offline'  THEN Server_Name END) AS Servers_Offline,
    COUNT(DISTINCT CASE WHEN Diagnosis = 'sql_down' THEN Server_Name END) AS Servers_SQL_Down,
    COUNT(DISTINCT CASE WHEN Diagnosis = 'partial'  THEN Server_Name END) AS Servers_Partial,
    COUNT(DISTINCT Server_Name) AS Total_Events,
    CASE
        WHEN COUNT(DISTINCT CASE WHEN Diagnosis = 'offline'  THEN Server_Name END) > 0 THEN 'CRITICAL'
        WHEN COUNT(DISTINCT CASE WHEN Diagnosis = 'sql_down' THEN Server_Name END) > 0 THEN 'WARNING'
        WHEN COUNT(DISTINCT Server_Name) > 0 THEN 'WARNING'
        ELSE 'OK'
    END AS Overall_Status,
    MAX(Event_Time) AS Last_Event_Time
FROM LatestStatus;
GO

IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
GO

-- Latest-state semantics: so mostra o ULTIMO evento negativo por servidor
-- dentro da janela de 15 min (consistente com FRESHNESS_WINDOWS['services'])
CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW
AS
WITH LatestEventPerServer AS (
    SELECT
        Server_Name,
        MAX(Event_Time) AS Last_Event_Time
    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
    WHERE Event_Time >= DATEADD(MINUTE, -15, GETDATE())
      AND Is_Resolved = 0
    GROUP BY Server_Name
)
SELECT TOP 1000
    soe.Event_ID,
    soe.Server_Name,
    soe.Server_Name AS Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    soe.Diagnosis,
    CASE
        WHEN soe.Diagnosis = 'offline'  THEN 'Servidor Offline'
        WHEN soe.Diagnosis = 'sql_down' THEN 'SQL Services Parados'
        WHEN soe.Diagnosis = 'partial'  THEN 'Parcialmente Offline'
        ELSE soe.Diagnosis
    END AS Diagnosis_Desc,
    soe.Ping_OK,
    CASE WHEN soe.Ping_OK = 1 THEN 'OK' ELSE 'FAIL' END AS Ping_Status,
    soe.Ping_Message,
    soe.Services_Down,
    soe.Event_Time,
    soe.Resolved_Time,
    soe.Is_Resolved,
    DATEDIFF(MINUTE, soe.Event_Time, GETDATE()) AS Minutes_Since_Event,
    CASE
        WHEN soe.Is_Resolved = 1        THEN 'RESOLVED'
        WHEN soe.Diagnosis = 'offline'  THEN 'CRITICAL'
        ELSE 'WARNING'
    END AS [State],
    CASE
        WHEN soe.Diagnosis = 'offline'  THEN 'CRITICAL'
        WHEN soe.Diagnosis = 'sql_down' THEN 'WARNING'
        ELSE 'WARNING'
    END AS Severity
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS soe WITH (NOLOCK)
INNER JOIN LatestEventPerServer le
    ON le.Server_Name = soe.Server_Name
   AND le.Last_Event_Time = soe.Event_Time
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
    ON e.Instance = soe.Server_Name
WHERE soe.Diagnosis IN ('offline', 'sql_down', 'partial')
ORDER BY
    CASE soe.Diagnosis WHEN 'offline' THEN 1 WHEN 'sql_down' THEN 2 ELSE 3 END,
    soe.Event_Time DESC;
GO

-- VIEW AGRUPADA POR SERVIDOR (para modal do dashboard - evita duplicatas)
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW;
GO

-- Latest-state semantics: so mostra servidores cujo ULTIMO evento na janela
-- de 15 min tem Diagnosis negativo. Evita fantasmas (collector nao auto-resolve).
CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW
AS
WITH LatestEventPerServer AS (
    SELECT
        Server_Name,
        MAX(Event_Time) AS Last_Event_Time
    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
    WHERE Event_Time >= DATEADD(MINUTE, -15, GETDATE())
      AND Is_Resolved = 0
    GROUP BY Server_Name
),
LatestStatus AS (
    SELECT
        soe.Server_Name,
        soe.Diagnosis,
        soe.Ping_OK,
        soe.Ping_Message,
        soe.Services_Down,
        soe.Event_Time
    FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS soe WITH (NOLOCK)
    INNER JOIN LatestEventPerServer le
        ON le.Server_Name = soe.Server_Name
       AND le.Last_Event_Time = soe.Event_Time
    WHERE soe.Diagnosis IN ('offline', 'sql_down', 'partial')
)
SELECT
    ls.Server_Name,
    ls.Server_Name AS Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    1 AS Event_Count,
    ls.Diagnosis,
    CASE
        WHEN ls.Diagnosis = 'offline'  THEN 'Servidor Offline'
        WHEN ls.Diagnosis = 'sql_down' THEN 'SQL Services Parados'
        WHEN ls.Diagnosis = 'partial'  THEN 'Parcialmente Offline'
        ELSE ls.Diagnosis
    END AS Diagnosis_Desc,
    CAST(ls.Ping_OK AS INT) AS Ping_OK,
    CASE WHEN ls.Ping_OK = 1 THEN 'OK' ELSE 'FAIL' END AS Ping_Status,
    ls.Ping_Message,
    ls.Services_Down,
    ls.Event_Time AS First_Event_Time,
    ls.Event_Time AS Last_Event_Time,
    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_First_Event,
    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_Last_Event,
    CASE
        WHEN ls.Diagnosis = 'offline'  THEN 'CRITICAL'
        WHEN ls.Diagnosis = 'sql_down' THEN 'WARNING'
        ELSE 'WARNING'
    END AS Severity,
    CASE
        WHEN ls.Diagnosis = 'offline'  THEN 'CRITICAL'
        ELSE 'WARNING'
    END AS [State]
FROM LatestStatus ls
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
    ON e.Instance = ls.Server_Name;
GO

PRINT '  Created: KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW';
GO

-- SECAO 9: TABELAS PROCESSES POR AMBIENTE

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_PROCESSES_STG_BLUE_PRD')
    SELECT * INTO dbo.KPI_MSSQL_PROCESSES_STG_BLUE_PRD FROM dbo.KPI_MSSQL_PROCESSES_STG_BLUE WHERE 1=0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_PROCESSES_STG_GREEN_PRD')
    SELECT * INTO dbo.KPI_MSSQL_PROCESSES_STG_GREEN_PRD FROM dbo.KPI_MSSQL_PROCESSES_STG_GREEN WHERE 1=0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_PROCESSES_STG_BLUE_QA')
    SELECT * INTO dbo.KPI_MSSQL_PROCESSES_STG_BLUE_QA FROM dbo.KPI_MSSQL_PROCESSES_STG_BLUE WHERE 1=0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_PROCESSES_STG_GREEN_QA')
    SELECT * INTO dbo.KPI_MSSQL_PROCESSES_STG_GREEN_QA FROM dbo.KPI_MSSQL_PROCESSES_STG_GREEN WHERE 1=0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_PROCESSES_STG_BLUE_TST')
    SELECT * INTO dbo.KPI_MSSQL_PROCESSES_STG_BLUE_TST FROM dbo.KPI_MSSQL_PROCESSES_STG_BLUE WHERE 1=0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_PROCESSES_STG_GREEN_TST')
    SELECT * INTO dbo.KPI_MSSQL_PROCESSES_STG_GREEN_TST FROM dbo.KPI_MSSQL_PROCESSES_STG_GREEN WHERE 1=0;
GO

-- ============================================================================
-- SECAO 10: VIEWS _ACTIVE (Camada de Abstracao Blue/Green)
-- ============================================================================
-- Arquitetura de 3 camadas:
--   CAMADA 3 - APRESENTACAO:  *_AGG_VIEW, *_DET_VIEW
--   CAMADA 2 - ABSTRACAO:     *_ACTIVE (dados do slot ativo)
--   CAMADA 1 - ARMAZENAMENTO: *_STG_BLUE_*, *_STG_GREEN_*
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'SECAO 10: VIEWS _ACTIVE (Camada de Abstracao Blue/Green)';
PRINT '============================================================================';
GO

-- ============================================================================
-- 10.1 PROCEDURE: usp_create_active_view
-- Cria view _ACTIVE para um KPI que abstrai a logica Blue/Green
-- ============================================================================

IF OBJECT_ID('dbo.usp_create_active_view', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_create_active_view;
GO

CREATE PROCEDURE dbo.usp_create_active_view
    @kpi_base_name NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @active_view NVARCHAR(100) = REPLACE(@kpi_base_name, '_STG', '_ACTIVE');
    DECLARE @sql NVARCHAR(MAX);

    -- Dropar se existir
    IF EXISTS (SELECT 1 FROM sys.views WHERE name = @active_view)
    BEGIN
        SET @sql = 'DROP VIEW dbo.' + @active_view;
        EXEC sp_executesql @sql;
    END

    -- Criar view _ACTIVE com logica Blue/Green
    -- OTIMIZADO v2: Usa CTE para ler Active_Slot uma unica vez (evita 6 subqueries)
    -- Melhoria de performance: 25x mais rapido (de ~24s para ~1s)
    SET @sql = '
CREATE VIEW dbo.' + @active_view + ' AS
-- View de abstracao Blue/Green: retorna dados do slot ativo
-- Criada automaticamente por usp_create_active_view
-- OTIMIZADO v2: CTE para performance (2025-12-23)
WITH ActiveSlot AS (
    SELECT Active_Slot FROM dbo.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @kpi_base_name + '''
)
SELECT d.* FROM dbo.' + @kpi_base_name + '_BLUE_PRD d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = ''BLUE''
UNION ALL
SELECT d.* FROM dbo.' + @kpi_base_name + '_BLUE_QA d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = ''BLUE''
UNION ALL
SELECT d.* FROM dbo.' + @kpi_base_name + '_BLUE_TST d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = ''BLUE''
UNION ALL
SELECT d.* FROM dbo.' + @kpi_base_name + '_GREEN_PRD d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = ''GREEN''
UNION ALL
SELECT d.* FROM dbo.' + @kpi_base_name + '_GREEN_QA d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = ''GREEN''
UNION ALL
SELECT d.* FROM dbo.' + @kpi_base_name + '_GREEN_TST d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = ''GREEN''
';

    BEGIN TRY
        EXEC sp_executesql @sql;
        PRINT '  [OK] ' + @active_view + ' criada';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] ' + @active_view + ': ' + ERROR_MESSAGE();
    END CATCH
END
GO

PRINT '  Procedure usp_create_active_view criada';
GO

-- ============================================================================
-- 10.2 PROCEDURE: usp_create_stg_alias
-- Cria view _STG como alias da _ACTIVE (compatibilidade)
-- ============================================================================

IF OBJECT_ID('dbo.usp_create_stg_alias', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_create_stg_alias;
GO

CREATE PROCEDURE dbo.usp_create_stg_alias
    @kpi_base_name NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @stg_view NVARCHAR(100) = @kpi_base_name;
    DECLARE @active_view NVARCHAR(100) = REPLACE(@kpi_base_name, '_STG', '_ACTIVE');
    DECLARE @sql NVARCHAR(MAX);

    -- Verificar se _ACTIVE existe
    IF NOT EXISTS (SELECT 1 FROM sys.views WHERE name = @active_view)
    BEGIN
        PRINT '  [SKIP] ' + @active_view + ' nao existe';
        RETURN;
    END

    -- Verificar se _STG e uma tabela (nao view)
    IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @stg_view)
    BEGIN
        PRINT '  [SKIP] ' + @stg_view + ' e uma tabela, nao view';
        RETURN;
    END

    -- Dropar se existir como view
    IF EXISTS (SELECT 1 FROM sys.views WHERE name = @stg_view)
    BEGIN
        SET @sql = 'DROP VIEW dbo.' + @stg_view;
        EXEC sp_executesql @sql;
    END

    -- Criar alias
    SET @sql = '
CREATE VIEW dbo.' + @stg_view + ' AS
-- DEPRECATED: Use ' + @active_view + ' em vez desta view
-- Mantida para compatibilidade com codigo legado
SELECT * FROM dbo.' + @active_view + '
';

    BEGIN TRY
        EXEC sp_executesql @sql;
        PRINT '  [OK] ' + @stg_view + ' -> ' + @active_view;
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] ' + @stg_view + ': ' + ERROR_MESSAGE();
    END CATCH
END
GO

PRINT '  Procedure usp_create_stg_alias criada';
GO

-- ============================================================================
-- 10.3 CRIAR VIEWS _ACTIVE PARA TODOS OS KPIs COM BLUE/GREEN
-- ============================================================================
PRINT '';
PRINT 'Criando views _ACTIVE para KPIs Blue/Green...';

EXEC dbo.usp_create_active_view 'KPI_MSSQL_FG_USAGE_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_BACKUPS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_BACKUP_STATUS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_BLOCKED_SESSIONS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_BLOCKED_USERS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_DB_AVAILABILITY_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_DB_IO_STATS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_DISK_USAGE_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_ERRORLOG_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_INST_AVAILABILITY_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_LONG_LOCKS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_SERVICE_STATUS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_TLOG_USAGE_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_ALWAYSON_STATUS_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_PROCESSES_STG';
GO

-- ============================================================================
-- 10.4 CRIAR VIEWS _STG COMO ALIASES (Compatibilidade)
-- ============================================================================
PRINT '';
PRINT 'Criando views _STG como aliases (compatibilidade)...';

EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_FG_USAGE_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_BACKUPS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_BACKUP_STATUS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_BLOCKED_SESSIONS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_BLOCKED_USERS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_DB_AVAILABILITY_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_DB_IO_STATS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_DISK_USAGE_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_ERRORLOG_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_INST_AVAILABILITY_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_LONG_LOCKS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_SERVICE_STATUS_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_TLOG_USAGE_STG';
GO

PRINT '';
PRINT '  Views _ACTIVE e aliases _STG criados com sucesso';
PRINT '';
PRINT '  Arquitetura implementada:';
PRINT '    CAMADA 3 - APRESENTACAO:  *_AGG_VIEW, *_DET_VIEW';
PRINT '    CAMADA 2 - ABSTRACAO:     *_ACTIVE (dados do slot ativo)';
PRINT '    CAMADA 1 - ARMAZENAMENTO: *_STG_BLUE_*, *_STG_GREEN_*';
PRINT '';
GO

-- ============================================================================
-- SECAO 11: OVERVIEW DASHBOARD (DADOS PRE-CALCULADOS)
-- ============================================================================
-- Esta secao cria a infraestrutura de dados pre-calculados para acelerar
-- o carregamento do Overview Dashboard.
-- ============================================================================

PRINT '';
PRINT '=============================================================================';
PRINT 'SECAO 11: OVERVIEW DASHBOARD (Dados Pre-Calculados)';
PRINT '=============================================================================';
GO

-- ============================================================================
-- 11.1 TABELA: OVERVIEW_INSTANCE_SNAPSHOT
-- ============================================================================
IF OBJECT_ID('dbo.OVERVIEW_INSTANCE_SNAPSHOT', 'U') IS NOT NULL DROP TABLE dbo.OVERVIEW_INSTANCE_SNAPSHOT;
GO

CREATE TABLE dbo.OVERVIEW_INSTANCE_SNAPSHOT (
    Instance VARCHAR(128) NOT NULL,
    Env VARCHAR(20) NOT NULL DEFAULT 'Undefined',
    Last_Refresh DATETIME2 NOT NULL DEFAULT GETDATE(),
    Last_Collection DATETIME2 NULL,
    Is_Online BIT NOT NULL DEFAULT 1,
    Databases_Total INT NOT NULL DEFAULT 0,
    Databases_Online INT NOT NULL DEFAULT 0,
    Databases_Offline INT NOT NULL DEFAULT 0,
    Blocked_Sessions INT NOT NULL DEFAULT 0,
    Blocked_Users INT NOT NULL DEFAULT 0,
    Long_Locks_Count INT NOT NULL DEFAULT 0,
    Active_Processes INT NOT NULL DEFAULT 0,
    TLog_Critical_Count INT NOT NULL DEFAULT 0,
    TLog_Warning_Count INT NOT NULL DEFAULT 0,
    TLog_Max_Percent DECIMAL(5,2) NOT NULL DEFAULT 0,
    FG_Critical_Count INT NOT NULL DEFAULT 0,
    FG_Warning_Count INT NOT NULL DEFAULT 0,
    FG_Max_Percent DECIMAL(5,2) NOT NULL DEFAULT 0,
    Disk_Critical_Count INT NOT NULL DEFAULT 0,
    Disk_Warning_Count INT NOT NULL DEFAULT 0,
    Disk_Min_Free_GB DECIMAL(18,2) NULL,
    Backup_Full_Overdue INT NOT NULL DEFAULT 0,
    Backup_Log_Overdue INT NOT NULL DEFAULT 0,
    Has_AlwaysOn BIT NOT NULL DEFAULT 0,
    AlwaysOn_Healthy INT NOT NULL DEFAULT 0,
    AlwaysOn_UnHealthy INT NOT NULL DEFAULT 0,
    Services_Running INT NOT NULL DEFAULT 0,
    Services_Stopped INT NOT NULL DEFAULT 0,
    OS_CPU_Critical BIT NOT NULL DEFAULT 0,
    OS_CPU_Percent DECIMAL(5,2) NULL,
    OS_Memory_Critical BIT NOT NULL DEFAULT 0,
    OS_Memory_Percent DECIMAL(5,2) NULL,
    OS_Available_MB INT NULL,
    Health_Score DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    Health_Status VARCHAR(20) NOT NULL DEFAULT 'OK',
    Availability_Score DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    Performance_Score DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    Space_Score DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    Backup_Score DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    Active_Problems INT NOT NULL DEFAULT 0,
    Problem_Summary NVARCHAR(1000) NULL,
    CONSTRAINT PK_OVERVIEW_INSTANCE_SNAPSHOT PRIMARY KEY CLUSTERED (Instance)
);
GO

CREATE INDEX IX_OVERVIEW_SNAPSHOT_Env ON dbo.OVERVIEW_INSTANCE_SNAPSHOT (Env, Health_Status);
CREATE INDEX IX_OVERVIEW_SNAPSHOT_Health ON dbo.OVERVIEW_INSTANCE_SNAPSHOT (Health_Status, Health_Score DESC);
GO
PRINT '  [OK] Tabela OVERVIEW_INSTANCE_SNAPSHOT criada';
GO

-- ============================================================================
-- 11.2 TABELA: OVERVIEW_DASHBOARD_CACHE
-- ============================================================================
IF OBJECT_ID('dbo.OVERVIEW_DASHBOARD_CACHE', 'U') IS NOT NULL DROP TABLE dbo.OVERVIEW_DASHBOARD_CACHE;
GO

CREATE TABLE dbo.OVERVIEW_DASHBOARD_CACHE (
    Cache_Key VARCHAR(50) NOT NULL,
    Env VARCHAR(20) NOT NULL DEFAULT 'ALL',
    Total_Instances INT NOT NULL DEFAULT 0,
    Instances_Online INT NOT NULL DEFAULT 0,
    Instances_Offline INT NOT NULL DEFAULT 0,
    Instances_Critical INT NOT NULL DEFAULT 0,
    Instances_Warning INT NOT NULL DEFAULT 0,
    Instances_OK INT NOT NULL DEFAULT 0,
    Total_Blocked_Sessions INT NOT NULL DEFAULT 0,
    Total_Blocked_Users INT NOT NULL DEFAULT 0,
    Total_Long_Locks INT NOT NULL DEFAULT 0,
    Total_TLog_Critical INT NOT NULL DEFAULT 0,
    Total_TLog_Warning INT NOT NULL DEFAULT 0,
    Total_FG_Critical INT NOT NULL DEFAULT 0,
    Total_FG_Warning INT NOT NULL DEFAULT 0,
    Total_Disk_Critical INT NOT NULL DEFAULT 0,
    Total_Disk_Warning INT NOT NULL DEFAULT 0,
    Total_Backup_Overdue INT NOT NULL DEFAULT 0,
    Total_AlwaysOn_Unhealthy INT NOT NULL DEFAULT 0,
    Total_Services_Stopped INT NOT NULL DEFAULT 0,
    Total_CPU_Critical INT NOT NULL DEFAULT 0,
    Total_Memory_Critical INT NOT NULL DEFAULT 0,
    Total_Databases INT NOT NULL DEFAULT 0,
    Databases_Online INT NOT NULL DEFAULT 0,
    Databases_Offline INT NOT NULL DEFAULT 0,
    Avg_Health_Score DECIMAL(5,2) NOT NULL DEFAULT 0,
    Min_Health_Score DECIMAL(5,2) NOT NULL DEFAULT 0,
    Last_Refresh DATETIME2 NOT NULL DEFAULT GETDATE(),
    Refresh_Duration_MS INT NULL,
    CONSTRAINT PK_OVERVIEW_DASHBOARD_CACHE PRIMARY KEY (Cache_Key, Env)
);
GO
PRINT '  [OK] Tabela OVERVIEW_DASHBOARD_CACHE criada';
GO

-- ============================================================================
-- 11.3 PROCEDURE: usp_refresh_overview_instance
-- ============================================================================
IF OBJECT_ID('dbo.usp_refresh_overview_instance', 'P') IS NOT NULL DROP PROCEDURE dbo.usp_refresh_overview_instance;
GO

CREATE PROCEDURE dbo.usp_refresh_overview_instance @Instance VARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Now DATETIME2 = GETDATE(), @Env VARCHAR(20), @LastCollection DATETIME2;
    DECLARE @IsOnline BIT = 0, @DbTotal INT = 0, @DbOnline INT = 0, @DbOffline INT = 0;
    DECLARE @BlockedSessions INT = 0, @BlockedUsers INT = 0, @LongLocks INT = 0, @ActiveProc INT = 0;
    DECLARE @TLogCrit INT = 0, @TLogWarn INT = 0, @TLogMax DECIMAL(5,2) = 0;
    DECLARE @FGCrit INT = 0, @FGWarn INT = 0, @FGMax DECIMAL(5,2) = 0;
    DECLARE @DiskCrit INT = 0, @DiskWarn INT = 0, @DiskMinFree DECIMAL(18,2) = NULL;
    DECLARE @BkpFullOverdue INT = 0, @BkpLogOverdue INT = 0;
    DECLARE @HasAO BIT = 0, @AOHealthy INT = 0, @AOUnhealthy INT = 0;
    DECLARE @SvcRunning INT = 0, @SvcStopped INT = 0;
    DECLARE @CPUCrit BIT = 0, @CPUPct DECIMAL(5,2) = NULL, @CPUHighCount INT = 0;
    DECLARE @MemCrit BIT = 0, @MemPct DECIMAL(5,2) = NULL, @MemAvailMB INT = NULL;
    DECLARE @Problems NVARCHAR(1000) = N'', @ProblemCount INT = 0;
    DECLARE @AvailScore DECIMAL(5,2) = 100.00, @PerfScore DECIMAL(5,2) = 100.00;
    DECLARE @SpaceScore DECIMAL(5,2) = 100.00, @BkpScore DECIMAL(5,2) = 100.00;
    DECLARE @HealthScore DECIMAL(5,2), @HealthStatus VARCHAR(20) = 'OK';

    SELECT @Env = ISNULL(Env, 'Undefined') FROM dbo.KPI_MSSQL_INST_ENVS WITH (NOLOCK) WHERE Instance = @Instance;
    IF @Env IS NULL SET @Env = 'Undefined';

    -- Is_Available
    SELECT @LastCollection = MAX(Update_TS) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    SELECT @IsOnline = CASE WHEN Is_Available = 1 THEN 1 ELSE 0 END FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @IsOnline IS NULL SET @IsOnline = 0;

    -- State
    SELECT @DbTotal = COUNT(*),
           @DbOnline = SUM(CASE WHEN [State] = 'ONLINE' OR Is_Available = 1 THEN 1 ELSE 0 END),
           @DbOffline = SUM(CASE WHEN [State] <> 'ONLINE' AND ISNULL(Is_Available, 1) = 0 THEN 1 ELSE 0 END)
    FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @DbOffline > 0 BEGIN SET @Problems = @Problems + N'DB Offline: ' + CAST(@DbOffline AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @DbOffline; END

    -- Blocked sessions
    SELECT @BlockedSessions = COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK) WHERE Instance = @Instance AND Wait_Time_Sec > 0;
    IF @BlockedSessions > 0 BEGIN SET @Problems = @Problems + N'Blocked: ' + CAST(@BlockedSessions AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + 1; END

    -- Blocked users
    SELECT @BlockedUsers = ISNULL(SUM(Blocked_Count), 0) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) WHERE Instance = @Instance;

    SELECT @LongLocks = COUNT(*) FROM dbo.KPI_MSSQL_LONG_LOCKS_STG WITH (NOLOCK) WHERE Instance = @Instance AND Duration_Sec >= 30;
    IF @LongLocks > 0 BEGIN SET @Problems = @Problems + N'Long Locks: ' + CAST(@LongLocks AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @LongLocks; END

    -- Processes
    SELECT @ActiveProc = COUNT(*) FROM dbo.KPI_MSSQL_PROCESSES_STG WITH (NOLOCK) WHERE Instance = @Instance;

    SELECT @TLogCrit = SUM(CASE WHEN Percent_Used >= 90 THEN 1 ELSE 0 END), @TLogWarn = SUM(CASE WHEN Percent_Used >= 80 AND Percent_Used < 90 THEN 1 ELSE 0 END), @TLogMax = MAX(ISNULL(Percent_Used, 0)) FROM dbo.KPI_MSSQL_TLOG_USAGE_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @TLogCrit > 0 BEGIN SET @Problems = @Problems + N'TLog Crit: ' + CAST(@TLogCrit AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @TLogCrit; END

    SELECT @FGCrit = SUM(CASE WHEN Percent_Used >= 90 THEN 1 ELSE 0 END), @FGWarn = SUM(CASE WHEN Percent_Used >= 80 AND Percent_Used < 90 THEN 1 ELSE 0 END), @FGMax = MAX(ISNULL(Percent_Used, 0)) FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @FGCrit > 0 BEGIN SET @Problems = @Problems + N'FG Crit: ' + CAST(@FGCrit AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @FGCrit; END

    -- Free_MB / 1024
    SELECT @DiskCrit = SUM(CASE WHEN Free_MB / 1024.0 < 10 THEN 1 ELSE 0 END), @DiskWarn = SUM(CASE WHEN Free_MB / 1024.0 >= 10 AND Free_MB / 1024.0 < 50 THEN 1 ELSE 0 END), @DiskMinFree = MIN(Free_MB / 1024.0) FROM dbo.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @DiskCrit > 0 BEGIN SET @Problems = @Problems + N'Disk Crit: ' + CAST(@DiskCrit AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @DiskCrit; END

    -- Backups overdue a partir da tabela real KPI_MSSQL_BACKUPS_STG (Full > 48h, Log > 24h)
    SELECT @BkpFullOverdue = ISNULL(SUM(CASE WHEN Backup_Type = 'D' AND Hours_Since_Backup > 48 THEN 1 ELSE 0 END), 0), @BkpLogOverdue = ISNULL(SUM(CASE WHEN Backup_Type = 'L' AND Hours_Since_Backup > 24 THEN 1 ELSE 0 END), 0) FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @BkpFullOverdue > 0 BEGIN SET @Problems = @Problems + N'Bkp Overdue: ' + CAST(@BkpFullOverdue AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @BkpFullOverdue; END

    -- AlwaysOn
    IF EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE Instance = @Instance)
    BEGIN
        SET @HasAO = 1;
        SELECT @AOHealthy = SUM(CASE WHEN Pri_Synch_Health = 'HEALTHY' AND (Sec_Synch_Health IS NULL OR Sec_Synch_Health = 'HEALTHY') THEN 1 ELSE 0 END), @AOUnhealthy = SUM(CASE WHEN Pri_Synch_Health <> 'HEALTHY' OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY') THEN 1 ELSE 0 END) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE Instance = @Instance;
        IF @AOUnhealthy > 0 BEGIN SET @Problems = @Problems + N'AG Unhealthy: ' + CAST(@AOUnhealthy AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @AOUnhealthy; END
    END

    -- Service_State
    SELECT @SvcRunning = SUM(CASE WHEN Service_State = 'Running' THEN 1 ELSE 0 END), @SvcStopped = SUM(CASE WHEN Service_State <> 'Running' THEN 1 ELSE 0 END) FROM dbo.KPI_MSSQL_SERVICE_STATUS_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @SvcStopped > 0 BEGIN SET @Problems = @Problems + N'Svc Stopped: ' + CAST(@SvcStopped AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @SvcStopped; END

    -- CPU
    SELECT @CPUHighCount = COUNT(*) FROM dbo.KPI_OS_CPU_HIST WITH (NOLOCK) WHERE Instance = @Instance AND Processor_Pct >= 95 AND Update_TS >= DATEADD(MINUTE, -2, @Now);
    IF @CPUHighCount >= 2 BEGIN SET @CPUCrit = 1; SELECT TOP 1 @CPUPct = Processor_Pct FROM dbo.KPI_OS_CPU_HIST WITH (NOLOCK) WHERE Instance = @Instance ORDER BY Update_TS DESC; SET @Problems = @Problems + N'CPU Critical; '; SET @ProblemCount = @ProblemCount + 1; END
    ELSE SELECT TOP 1 @CPUPct = Processor_Pct FROM dbo.KPI_OS_CPU_STG WITH (NOLOCK) WHERE Instance = @Instance;

    SELECT TOP 1 @MemPct = Percent_Used, @MemAvailMB = CAST(Available_MB AS INT), @MemCrit = CASE WHEN Percent_Used >= 99 THEN 1 WHEN Available_MB < 500 THEN 1 WHEN Page_Reads_Sec > 100 THEN 1 ELSE 0 END FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @MemCrit = 1 BEGIN SET @Problems = @Problems + N'Memory Critical; '; SET @ProblemCount = @ProblemCount + 1; END

    -- Scores
    IF @IsOnline = 0 SET @AvailScore = 0 ELSE IF @DbTotal > 0 SET @AvailScore = (@DbOnline * 100.0) / @DbTotal;
    IF @BlockedSessions > 10 SET @PerfScore = @PerfScore - 40 ELSE IF @BlockedSessions > 0 SET @PerfScore = @PerfScore - (@BlockedSessions * 4);
    IF @LongLocks > 5 SET @PerfScore = @PerfScore - 30 ELSE IF @LongLocks > 0 SET @PerfScore = @PerfScore - (@LongLocks * 6);
    IF @CPUCrit = 1 SET @PerfScore = @PerfScore - 20; IF @MemCrit = 1 SET @PerfScore = @PerfScore - 20; IF @PerfScore < 0 SET @PerfScore = 0;
    IF @TLogCrit > 0 SET @SpaceScore = @SpaceScore - (@TLogCrit * 15); IF @TLogWarn > 0 SET @SpaceScore = @SpaceScore - (@TLogWarn * 5);
    IF @FGCrit > 0 SET @SpaceScore = @SpaceScore - (@FGCrit * 15); IF @FGWarn > 0 SET @SpaceScore = @SpaceScore - (@FGWarn * 5);
    IF @DiskCrit > 0 SET @SpaceScore = @SpaceScore - (@DiskCrit * 20); IF @DiskWarn > 0 SET @SpaceScore = @SpaceScore - (@DiskWarn * 10); IF @SpaceScore < 0 SET @SpaceScore = 0;
    IF @BkpFullOverdue > 0 SET @BkpScore = @BkpScore - (@BkpFullOverdue * 20); IF @BkpLogOverdue > 0 SET @BkpScore = @BkpScore - (@BkpLogOverdue * 5); IF @BkpScore < 0 SET @BkpScore = 0;
    SET @HealthScore = (@AvailScore + @PerfScore + @SpaceScore + @BkpScore) / 4;
    IF @IsOnline = 0 SET @HealthStatus = 'OFFLINE' ELSE IF @HealthScore < 50 SET @HealthStatus = 'CRITICAL' ELSE IF @HealthScore < 75 SET @HealthStatus = 'WARNING' ELSE SET @HealthStatus = 'OK';
    IF LEN(@Problems) > 2 SET @Problems = LEFT(@Problems, LEN(@Problems) - 2); IF @Problems = N'' SET @Problems = NULL;

    MERGE dbo.OVERVIEW_INSTANCE_SNAPSHOT AS t USING (SELECT @Instance AS Instance) AS s ON t.Instance = s.Instance
    WHEN MATCHED THEN UPDATE SET Env=@Env,Last_Refresh=@Now,Last_Collection=@LastCollection,Is_Online=@IsOnline,Databases_Total=ISNULL(@DbTotal,0),Databases_Online=ISNULL(@DbOnline,0),Databases_Offline=ISNULL(@DbOffline,0),Blocked_Sessions=ISNULL(@BlockedSessions,0),Blocked_Users=ISNULL(@BlockedUsers,0),Long_Locks_Count=ISNULL(@LongLocks,0),Active_Processes=ISNULL(@ActiveProc,0),TLog_Critical_Count=ISNULL(@TLogCrit,0),TLog_Warning_Count=ISNULL(@TLogWarn,0),TLog_Max_Percent=ISNULL(@TLogMax,0),FG_Critical_Count=ISNULL(@FGCrit,0),FG_Warning_Count=ISNULL(@FGWarn,0),FG_Max_Percent=ISNULL(@FGMax,0),Disk_Critical_Count=ISNULL(@DiskCrit,0),Disk_Warning_Count=ISNULL(@DiskWarn,0),Disk_Min_Free_GB=@DiskMinFree,Backup_Full_Overdue=ISNULL(@BkpFullOverdue,0),Backup_Log_Overdue=ISNULL(@BkpLogOverdue,0),Has_AlwaysOn=@HasAO,AlwaysOn_Healthy=ISNULL(@AOHealthy,0),AlwaysOn_UnHealthy=ISNULL(@AOUnhealthy,0),Services_Running=ISNULL(@SvcRunning,0),Services_Stopped=ISNULL(@SvcStopped,0),OS_CPU_Critical=@CPUCrit,OS_CPU_Percent=@CPUPct,OS_Memory_Critical=@MemCrit,OS_Memory_Percent=@MemPct,OS_Available_MB=@MemAvailMB,Health_Score=@HealthScore,Health_Status=@HealthStatus,Availability_Score=@AvailScore,Performance_Score=@PerfScore,Space_Score=@SpaceScore,Backup_Score=@BkpScore,Active_Problems=@ProblemCount,Problem_Summary=@Problems
    WHEN NOT MATCHED THEN INSERT (Instance,Env,Last_Refresh,Last_Collection,Is_Online,Databases_Total,Databases_Online,Databases_Offline,Blocked_Sessions,Blocked_Users,Long_Locks_Count,Active_Processes,TLog_Critical_Count,TLog_Warning_Count,TLog_Max_Percent,FG_Critical_Count,FG_Warning_Count,FG_Max_Percent,Disk_Critical_Count,Disk_Warning_Count,Disk_Min_Free_GB,Backup_Full_Overdue,Backup_Log_Overdue,Has_AlwaysOn,AlwaysOn_Healthy,AlwaysOn_UnHealthy,Services_Running,Services_Stopped,OS_CPU_Critical,OS_CPU_Percent,OS_Memory_Critical,OS_Memory_Percent,OS_Available_MB,Health_Score,Health_Status,Availability_Score,Performance_Score,Space_Score,Backup_Score,Active_Problems,Problem_Summary) VALUES (@Instance,@Env,@Now,@LastCollection,@IsOnline,ISNULL(@DbTotal,0),ISNULL(@DbOnline,0),ISNULL(@DbOffline,0),ISNULL(@BlockedSessions,0),ISNULL(@BlockedUsers,0),ISNULL(@LongLocks,0),ISNULL(@ActiveProc,0),ISNULL(@TLogCrit,0),ISNULL(@TLogWarn,0),ISNULL(@TLogMax,0),ISNULL(@FGCrit,0),ISNULL(@FGWarn,0),ISNULL(@FGMax,0),ISNULL(@DiskCrit,0),ISNULL(@DiskWarn,0),@DiskMinFree,ISNULL(@BkpFullOverdue,0),ISNULL(@BkpLogOverdue,0),@HasAO,ISNULL(@AOHealthy,0),ISNULL(@AOUnhealthy,0),ISNULL(@SvcRunning,0),ISNULL(@SvcStopped,0),@CPUCrit,@CPUPct,@MemCrit,@MemPct,@MemAvailMB,@HealthScore,@HealthStatus,@AvailScore,@PerfScore,@SpaceScore,@BkpScore,@ProblemCount,@Problems);
END
GO
PRINT '  [OK] Procedure usp_refresh_overview_instance criada';
GO

-- ============================================================================
-- 11.4 PROCEDURE: usp_refresh_overview_all
-- ============================================================================
IF OBJECT_ID('dbo.usp_refresh_overview_all', 'P') IS NOT NULL DROP PROCEDURE dbo.usp_refresh_overview_all;
GO

CREATE PROCEDURE dbo.usp_refresh_overview_all
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @StartTime DATETIME2 = GETDATE(), @Instance VARCHAR(128);
    DECLARE inst_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT Instance FROM dbo.KPI_MSSQL_INST_ENVS;
    OPEN inst_cursor; FETCH NEXT FROM inst_cursor INTO @Instance;
    WHILE @@FETCH_STATUS = 0 BEGIN EXEC dbo.usp_refresh_overview_instance @Instance = @Instance; FETCH NEXT FROM inst_cursor INTO @Instance; END
    CLOSE inst_cursor; DEALLOCATE inst_cursor;
    DELETE FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT WHERE Instance NOT IN (SELECT Instance FROM dbo.KPI_MSSQL_INST_ENVS);
    EXEC dbo.usp_refresh_overview_cache;
    PRINT '  Overview refresh em ' + CAST(DATEDIFF(MILLISECOND, @StartTime, GETDATE()) AS VARCHAR) + ' ms';
END
GO
PRINT '  [OK] Procedure usp_refresh_overview_all criada';
GO

-- ============================================================================
-- 11.5 PROCEDURE: usp_refresh_overview_cache
-- ============================================================================
IF OBJECT_ID('dbo.usp_refresh_overview_cache', 'P') IS NOT NULL DROP PROCEDURE dbo.usp_refresh_overview_cache;
GO

CREATE PROCEDURE dbo.usp_refresh_overview_cache
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @StartTime DATETIME2 = GETDATE();
    DELETE FROM dbo.OVERVIEW_DASHBOARD_CACHE;

    -- Inserir por ambiente
    INSERT INTO dbo.OVERVIEW_DASHBOARD_CACHE (Cache_Key, Env, Total_Instances, Instances_Online, Instances_Offline, Instances_Critical, Instances_Warning, Instances_OK, Total_Blocked_Sessions, Total_Blocked_Users, Total_Long_Locks, Total_TLog_Critical, Total_TLog_Warning, Total_FG_Critical, Total_FG_Warning, Total_Disk_Critical, Total_Disk_Warning, Total_Backup_Overdue, Total_AlwaysOn_Unhealthy, Total_Services_Stopped, Total_CPU_Critical, Total_Memory_Critical, Total_Databases, Databases_Online, Databases_Offline, Avg_Health_Score, Min_Health_Score, Last_Refresh, Refresh_Duration_MS)
    SELECT
        'ENV_' + Env, Env, COUNT(*),
        ISNULL(SUM(CASE WHEN Is_Online = 1 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Is_Online = 0 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Health_Status = 'CRITICAL' THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Health_Status = 'WARNING' THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Health_Status = 'OK' THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(Blocked_Sessions), 0), ISNULL(SUM(Blocked_Users), 0), ISNULL(SUM(Long_Locks_Count), 0),
        ISNULL(SUM(TLog_Critical_Count), 0), ISNULL(SUM(TLog_Warning_Count), 0),
        ISNULL(SUM(FG_Critical_Count), 0), ISNULL(SUM(FG_Warning_Count), 0),
        ISNULL(SUM(Disk_Critical_Count), 0), ISNULL(SUM(Disk_Warning_Count), 0),
        ISNULL(SUM(Backup_Full_Overdue + Backup_Log_Overdue), 0),
        ISNULL(SUM(AlwaysOn_UnHealthy), 0), ISNULL(SUM(Services_Stopped), 0),
        ISNULL(SUM(CASE WHEN OS_CPU_Critical = 1 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN OS_Memory_Critical = 1 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(Databases_Total), 0), ISNULL(SUM(Databases_Online), 0), ISNULL(SUM(Databases_Offline), 0),
        ISNULL(AVG(Health_Score), 100.00), ISNULL(MIN(Health_Score), 100.00),
        GETDATE(), DATEDIFF(MILLISECOND, @StartTime, GETDATE())
    FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT
    GROUP BY Env;

    -- Inserir total geral
    INSERT INTO dbo.OVERVIEW_DASHBOARD_CACHE (Cache_Key, Env, Total_Instances, Instances_Online, Instances_Offline, Instances_Critical, Instances_Warning, Instances_OK, Total_Blocked_Sessions, Total_Blocked_Users, Total_Long_Locks, Total_TLog_Critical, Total_TLog_Warning, Total_FG_Critical, Total_FG_Warning, Total_Disk_Critical, Total_Disk_Warning, Total_Backup_Overdue, Total_AlwaysOn_Unhealthy, Total_Services_Stopped, Total_CPU_Critical, Total_Memory_Critical, Total_Databases, Databases_Online, Databases_Offline, Avg_Health_Score, Min_Health_Score, Last_Refresh, Refresh_Duration_MS)
    SELECT
        'TOTAL', 'ALL', COUNT(*),
        ISNULL(SUM(CASE WHEN Is_Online = 1 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Is_Online = 0 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Health_Status = 'CRITICAL' THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Health_Status = 'WARNING' THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN Health_Status = 'OK' THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(Blocked_Sessions), 0), ISNULL(SUM(Blocked_Users), 0), ISNULL(SUM(Long_Locks_Count), 0),
        ISNULL(SUM(TLog_Critical_Count), 0), ISNULL(SUM(TLog_Warning_Count), 0),
        ISNULL(SUM(FG_Critical_Count), 0), ISNULL(SUM(FG_Warning_Count), 0),
        ISNULL(SUM(Disk_Critical_Count), 0), ISNULL(SUM(Disk_Warning_Count), 0),
        ISNULL(SUM(Backup_Full_Overdue + Backup_Log_Overdue), 0),
        ISNULL(SUM(AlwaysOn_UnHealthy), 0), ISNULL(SUM(Services_Stopped), 0),
        ISNULL(SUM(CASE WHEN OS_CPU_Critical = 1 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(CASE WHEN OS_Memory_Critical = 1 THEN 1 ELSE 0 END), 0),
        ISNULL(SUM(Databases_Total), 0), ISNULL(SUM(Databases_Online), 0), ISNULL(SUM(Databases_Offline), 0),
        ISNULL(AVG(Health_Score), 100.00), ISNULL(MIN(Health_Score), 100.00),
        GETDATE(), DATEDIFF(MILLISECOND, @StartTime, GETDATE())
    FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT;
END
GO
PRINT '  [OK] Procedure usp_refresh_overview_cache criada';
GO

-- ============================================================================
-- 11.6 VIEW: V_OVERVIEW_DASHBOARD_SUMMARY
-- ============================================================================
IF OBJECT_ID('dbo.V_OVERVIEW_DASHBOARD_SUMMARY', 'V') IS NOT NULL DROP VIEW dbo.V_OVERVIEW_DASHBOARD_SUMMARY;
GO

CREATE VIEW dbo.V_OVERVIEW_DASHBOARD_SUMMARY AS
SELECT Env, Total_Instances, Instances_Online, Instances_Offline, Instances_Critical, Instances_Warning, Instances_OK, Total_Blocked_Sessions, Total_Blocked_Users, Total_Long_Locks, Total_TLog_Critical, Total_TLog_Warning, Total_FG_Critical, Total_FG_Warning, Total_Disk_Critical, Total_Disk_Warning, Total_Backup_Overdue, Total_AlwaysOn_Unhealthy, Total_Services_Stopped, Total_CPU_Critical, Total_Memory_Critical, Total_Databases, Databases_Online, Databases_Offline, Avg_Health_Score, Min_Health_Score, Last_Refresh, Refresh_Duration_MS,
    CASE WHEN Total_Instances > 0 THEN CAST(Instances_Online * 100.0 / Total_Instances AS DECIMAL(5,2)) ELSE 100.00 END AS Availability_Percent,
    Instances_Critical + Instances_Warning AS Instances_With_Problems,
    Total_TLog_Critical + Total_FG_Critical + Total_Disk_Critical AS Total_Space_Critical,
    Total_TLog_Warning + Total_FG_Warning + Total_Disk_Warning AS Total_Space_Warning
FROM dbo.OVERVIEW_DASHBOARD_CACHE WHERE Cache_Key LIKE 'ENV_%' OR Cache_Key = 'TOTAL';
GO
PRINT '  [OK] View V_OVERVIEW_DASHBOARD_SUMMARY criada';
GO

-- ============================================================================
-- 11.7 VIEW: V_OVERVIEW_INSTANCE_HEALTH
-- ============================================================================
IF OBJECT_ID('dbo.V_OVERVIEW_INSTANCE_HEALTH', 'V') IS NOT NULL DROP VIEW dbo.V_OVERVIEW_INSTANCE_HEALTH;
GO

CREATE VIEW dbo.V_OVERVIEW_INSTANCE_HEALTH AS
SELECT Instance, Env, Is_Online, Health_Score, Health_Status, Availability_Score, Performance_Score, Space_Score, Backup_Score, Active_Problems, Problem_Summary, Databases_Total, Databases_Online, Databases_Offline, Blocked_Sessions, Long_Locks_Count, TLog_Critical_Count + TLog_Warning_Count AS TLog_Issues, FG_Critical_Count + FG_Warning_Count AS FG_Issues, Disk_Critical_Count + Disk_Warning_Count AS Disk_Issues, Backup_Full_Overdue + Backup_Log_Overdue AS Backup_Issues, AlwaysOn_UnHealthy AS AlwaysOn_Issues, Services_Stopped AS Service_Issues, OS_CPU_Critical, OS_CPU_Percent, OS_Memory_Critical, OS_Memory_Percent, OS_Available_MB, Last_Refresh, Last_Collection
FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT;
GO
PRINT '  [OK] View V_OVERVIEW_INSTANCE_HEALTH criada';
GO

-- ============================================================================
-- 11.8 VIEW: V_OVERVIEW_TOP_PROBLEMS
-- ============================================================================
IF OBJECT_ID('dbo.V_OVERVIEW_TOP_PROBLEMS', 'V') IS NOT NULL DROP VIEW dbo.V_OVERVIEW_TOP_PROBLEMS;
GO

CREATE VIEW dbo.V_OVERVIEW_TOP_PROBLEMS AS
SELECT TOP 20 Instance, Env, Health_Status, Health_Score, Active_Problems, Problem_Summary,
    CASE WHEN Is_Online = 0 THEN 'Instance Offline' WHEN OS_CPU_Critical = 1 THEN 'CPU Critical (>95% sustained)' WHEN OS_Memory_Critical = 1 THEN 'Memory Critical' WHEN Blocked_Sessions > 10 THEN 'High Blocking' WHEN TLog_Critical_Count > 0 THEN 'TLog Critical' WHEN FG_Critical_Count > 0 THEN 'FileGroup Critical' WHEN Disk_Critical_Count > 0 THEN 'Disk Critical' WHEN AlwaysOn_UnHealthy > 0 THEN 'AlwaysOn Unhealthy' WHEN Backup_Full_Overdue > 0 THEN 'Backup Overdue' ELSE 'Multiple Issues' END AS Primary_Issue, Last_Refresh
FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT WHERE Health_Status IN ('CRITICAL', 'WARNING') OR Active_Problems > 0
ORDER BY CASE Health_Status WHEN 'OFFLINE' THEN 1 WHEN 'CRITICAL' THEN 2 WHEN 'WARNING' THEN 3 ELSE 4 END, Health_Score ASC, Active_Problems DESC;
GO
PRINT '  [OK] View V_OVERVIEW_TOP_PROBLEMS criada';
GO

PRINT '';
PRINT '=============================================================================';
PRINT 'SECAO OVERVIEW DASHBOARD - CONCLUIDA';
PRINT '=============================================================================';
PRINT 'Objetos criados:';
PRINT '  - Tabela: OVERVIEW_INSTANCE_SNAPSHOT';
PRINT '  - Tabela: OVERVIEW_DASHBOARD_CACHE';
PRINT '  - Procedure: usp_refresh_overview_instance';
PRINT '  - Procedure: usp_refresh_overview_all';
PRINT '  - Procedure: usp_refresh_overview_cache';
PRINT '  - View: V_OVERVIEW_DASHBOARD_SUMMARY';
PRINT '  - View: V_OVERVIEW_INSTANCE_HEALTH';
PRINT '  - View: V_OVERVIEW_TOP_PROBLEMS';
PRINT '';
PRINT 'Para atualizar o dashboard, execute:';
PRINT '  EXEC dbo.usp_refresh_overview_all;';
GO

-- ============================================================================
-- SECAO 12: JOBS DO SQL SERVER AGENT
-- ============================================================================
-- Cria os jobs necessarios para manter o Overview Dashboard atualizado
-- automaticamente e limpar dados historicos.
-- ============================================================================

PRINT '';
PRINT '=============================================================================';
PRINT 'SECAO 12: JOBS DO SQL SERVER AGENT';
PRINT '=============================================================================';
GO

USE [msdb];
GO

-- ============================================================================
-- 12.1 JOB: REFRESH OVERVIEW DASHBOARD (a cada 5 minutos)
-- ============================================================================
PRINT '';
PRINT '12.1 Criando Job: WatcherDB - Refresh Overview Dashboard...';

DECLARE @JobOwner NVARCHAR(128) = SUSER_SNAME();
DECLARE @DatabaseName NVARCHAR(128) = N'WatcherDB_Intelligence';

-- Remover job se existir
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB - Refresh Overview Dashboard')
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB - Refresh Overview Dashboard', @delete_unused_schedule = 1;
    PRINT '     Job existente removido';
END

-- Criar o Job
EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB - Refresh Overview Dashboard',
    @enabled = 1,
    @description = N'Atualiza os dados pre-calculados do Overview Dashboard a cada 5 minutos.',
    @category_name = N'Database Maintenance',
    @owner_login_name = @JobOwner,
    @notify_level_eventlog = 2;

-- Adicionar Step
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB - Refresh Overview Dashboard',
    @step_name = N'Refresh Overview All',
    @step_id = 1,
    @subsystem = N'TSQL',
    @command = N'
SET NOCOUNT ON;
DECLARE @InstanceCount INT;
SELECT @InstanceCount = COUNT(*) FROM dbo.KPI_MSSQL_INST_ENVS;
IF @InstanceCount > 0
    EXEC dbo.usp_refresh_overview_all;
ELSE
    PRINT ''AVISO: Nenhuma instancia cadastrada em KPI_MSSQL_INST_ENVS'';
',
    @database_name = @DatabaseName,
    @on_success_action = 1,
    @on_fail_action = 2,
    @retry_attempts = 2,
    @retry_interval = 1;

-- Adicionar Schedule: A cada 5 minutos
EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB - Refresh Overview Dashboard',
    @name = N'Every 5 minutes',
    @enabled = 1,
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 4,
    @freq_subday_interval = 5,
    @active_start_date = 20241201,
    @active_end_date = 99991231,
    @active_start_time = 0,
    @active_end_time = 235959;

-- Adicionar ao servidor local
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB - Refresh Overview Dashboard',
    @server_name = N'(local)';

PRINT '     [OK] Job criado - Schedule: a cada 5 minutos';
GO

-- ============================================================================
-- 12.2 JOB: CLEANUP HISTORY (diario as 02:00)
-- ============================================================================
PRINT '';
PRINT '12.2 Criando Job: WatcherDB - Cleanup History...';

DECLARE @JobOwner NVARCHAR(128) = SUSER_SNAME();
DECLARE @DatabaseName NVARCHAR(128) = N'WatcherDB_Intelligence';

-- Remover job se existir
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB - Cleanup History')
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = N'WatcherDB - Cleanup History', @delete_unused_schedule = 1;
    PRINT '     Job existente removido';
END

-- Criar o Job
EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB - Cleanup History',
    @enabled = 1,
    @description = N'Limpa dados historicos antigos (>90 dias). Executa diariamente as 02:00.',
    @category_name = N'Database Maintenance',
    @owner_login_name = @JobOwner,
    @notify_level_eventlog = 2;

-- Adicionar Step
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB - Cleanup History',
    @step_name = N'Cleanup History',
    @step_id = 1,
    @subsystem = N'TSQL',
    @command = N'
SET NOCOUNT ON;
DECLARE @RetentionDays INT = 90;

-- Limpar Collection History
IF OBJECT_ID(''dbo.usp_Purge_Collection_History'', ''P'') IS NOT NULL
    EXEC dbo.usp_Purge_Collection_History @retention_days = @RetentionDays;

-- Limpar OS History
IF OBJECT_ID(''dbo.usp_OS_Cleanup_History'', ''P'') IS NOT NULL
    EXEC dbo.usp_OS_Cleanup_History @RetentionDays = @RetentionDays;

-- Limpar snapshots orfaos
DELETE FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT
WHERE Instance NOT IN (SELECT Instance FROM dbo.KPI_MSSQL_INST_ENVS);

PRINT ''Cleanup concluido'';
',
    @database_name = @DatabaseName,
    @on_success_action = 1,
    @on_fail_action = 2,
    @retry_attempts = 1,
    @retry_interval = 5;

-- Adicionar Schedule: Diario as 02:00
EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'WatcherDB - Cleanup History',
    @name = N'Daily at 02:00',
    @enabled = 1,
    @freq_type = 4,
    @freq_interval = 1,
    @freq_subday_type = 1,
    @active_start_date = 20241201,
    @active_end_date = 99991231,
    @active_start_time = 20000;

-- Adicionar ao servidor local
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB - Cleanup History',
    @server_name = N'(local)';

PRINT '     [OK] Job criado - Schedule: diario as 02:00';
GO

-- ============================================================================
-- 12.3 VERIFICAR JOBS CRIADOS
-- ============================================================================
PRINT '';
PRINT '12.3 Jobs criados:';

SELECT
    j.name AS Job_Name,
    CASE j.enabled WHEN 1 THEN 'Sim' ELSE 'Nao' END AS Habilitado,
    s.name AS Schedule_Name
FROM msdb.dbo.sysjobs j
LEFT JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id
LEFT JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id
WHERE j.name LIKE 'WatcherDB%'
ORDER BY j.name;
GO

PRINT '';
PRINT '=============================================================================';
PRINT 'SECAO JOBS - CONCLUIDA';
PRINT '=============================================================================';
GO

USE [WatcherDB_Intelligence];
GO

-- ============================================================================
-- FIM DA INSTALACAO
-- ============================================================================

PRINT '';
PRINT '=============================================================================';
PRINT 'INSTALACAO COMPLETA FINALIZADA!';
PRINT '=============================================================================';
PRINT '';
PRINT 'Objetos criados:';
PRINT '  - Secao 1-10: Tabelas KPI, Views, Procedures base';
PRINT '  - Secao 11: Overview Dashboard (tabelas, procedures, views)';
PRINT '  - Secao 12: Jobs SQL Agent (refresh a cada 5min, cleanup diario)';
PRINT '';
PRINT 'Scripts de pos-instalacao recomendados:';
PRINT '  1. Execute: POPULAR_INST_ENVS_COMPLETO.sql (popular tabela de instancias)';
PRINT '  2. Execute: CORRIGIR_AMBIENTES_INST_ENVS.sql (corrigir ambientes)';
PRINT '  3. Execute: EXEC dbo.usp_refresh_overview_all (atualizar Overview Dashboard)';
PRINT '  4. OBRIGATORIO, em CADA instancia monitorizada (NAO neste servidor):';
PRINT '     docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql -- least-privilege do login';
PRINT '     sql_monitoring (VIEW SERVER STATE/ANY DEFINITION/ANY DATABASE, msdb backup*/sysjobs*';
PRINT '     + SQLAgentReaderRole, xp_readerrorlog, SHOWPLAN). Multi-servidor: SSMS Registered Servers.';
PRINT '';
PRINT 'Jobs automaticos:';
PRINT '  - WatcherDB - Refresh Overview Dashboard (a cada 5 min)';
PRINT '  - WatcherDB - Cleanup History (diario as 02:00)';
PRINT '';
PRINT 'Para testar o job manualmente:';
PRINT '  EXEC msdb.dbo.sp_start_job @job_name = ''WatcherDB - Refresh Overview Dashboard'';';
PRINT '';
GO
-- ============================================================================
-- SECAO 13: AUTENTICACAO (WatcherDB_Users, WatcherDB_Auth_Log, WatcherDB_User_Preferences)
-- Origem: database/CREATE_USER_AUTH_PREFS.sql (tabelas) + 12_ADD_LOCAL_PASSWORD_HASH.sql
-- + 13_ADD_PASSWORD_CHANGED_AT.sql. Incluido no canonico em 2026-09-08 (lote P4 A-4.7):
-- ate' aqui o canonico nao criava NENHUMA tabela de autenticacao. SEM utilizadores
-- semente: contas por omissao nao pertencem ao canonico (criar pela UI de admin).
-- Inclui 07_ADD_MUST_CHANGE_PASSWORD.sql (o proprio script repoe 0 nos utilizadores activos;
-- so' forca a mudanca em contas que ainda tenham o hash semente).
-- ============================================================================
USE [WatcherDB_Intelligence];
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_Users')
BEGIN
    CREATE TABLE dbo.WatcherDB_Users (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        username        NVARCHAR(100)  NOT NULL UNIQUE,
        password_hash   NVARCHAR(500)  NOT NULL,
        role            NVARCHAR(50)   NOT NULL DEFAULT 'viewer',  -- admin, analyst, viewer, operator
        email           NVARCHAR(200)  NULL,
        full_name       NVARCHAR(200)  NULL,
        disabled        BIT            NOT NULL DEFAULT 0,
        failed_attempts INT            NOT NULL DEFAULT 0,
        locked_until    DATETIME2      NULL,
        last_login      DATETIME2      NULL,
        created_at      DATETIME2      NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Tabela WatcherDB_Users criada.';
END
GO

-- 2. Tabela de Auth Log
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_Auth_Log')
BEGIN
    CREATE TABLE dbo.WatcherDB_Auth_Log (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        username    NVARCHAR(100)  NOT NULL,
        action      NVARCHAR(50)   NOT NULL,  -- LOGIN_SUCCESS, LOGIN_FAILED, PASSWORD_CHANGE, USER_ENABLED, USER_DISABLED
        ip_address  NVARCHAR(50)   NULL,
        details     NVARCHAR(500)  NULL,
        created_at  DATETIME2      NOT NULL DEFAULT GETDATE()
    );

    CREATE NONCLUSTERED INDEX IX_AuthLog_Username
        ON dbo.WatcherDB_Auth_Log (username, created_at DESC);

    PRINT 'Tabela WatcherDB_Auth_Log criada.';
END
GO

-- 3. Tabela de Preferencias por Utilizador
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_User_Preferences')
BEGIN
    CREATE TABLE dbo.WatcherDB_User_Preferences (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        username         NVARCHAR(100)  NOT NULL,
        preference_key   NVARCHAR(100)  NOT NULL,
        preference_value NVARCHAR(MAX)  NULL,  -- Valor ENCRIPTADO com Fernet
        updated_at       DATETIME2      NOT NULL DEFAULT GETDATE(),

        CONSTRAINT UQ_UserPref_Key UNIQUE (username, preference_key)
    );

    CREATE NONCLUSTERED INDEX IX_UserPref_Username
        ON dbo.WatcherDB_User_Preferences (username)
        INCLUDE (preference_key, preference_value);

    PRINT 'Tabela WatcherDB_User_Preferences criada.';
END
GO

-- 12: dual auth (AD + fallback local)
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_hash')
    ALTER TABLE dbo.WatcherDB_Users ADD local_password_hash NVARCHAR(500) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_set_at')
    ALTER TABLE dbo.WatcherDB_Users ADD local_password_set_at DATETIME2(0) NULL;
GO
-- 13: revogacao de sessao por mudanca/reset de password
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'password_changed_at')
    ALTER TABLE dbo.WatcherDB_Users ADD password_changed_at DATETIME2(0) NULL;
GO
-- 07: obrigar mudanca de password no proximo login (reset pelo admin marca 1; /change-password limpa)
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'must_change_password')
BEGIN
    ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;
    EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');
END
GO
PRINT '  - Secao 13: Autenticacao (WatcherDB_Users/Auth_Log/User_Preferences + colunas 07/12/13)';
GO

