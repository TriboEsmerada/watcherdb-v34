-- =============================================================================
-- WatcherDB V5 — Performance Module Schema (MVP Fase 1)
-- Base de dados: WatcherDB_Intelligence em SQLHDSTST505\I01
-- Data: 2026-04-15
-- Idempotente: pode ser executado multiplas vezes em seguranca
-- =============================================================================

USE WatcherDB_Intelligence;
GO

SET NOCOUNT ON;
GO

-- -----------------------------------------------------------------------------
-- 1. performance_investigations — audit trail de investigacoes executadas
-- -----------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'performance_investigations' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.performance_investigations (
        investigation_id    VARCHAR(64)   NOT NULL PRIMARY KEY,
        investigator_id     VARCHAR(50)   NOT NULL,   -- 'slow_queries', 'deadlocks', ...
        instance            VARCHAR(255)  NOT NULL,
        database_name       VARCHAR(255)  NULL,
        severity            VARCHAR(20)   NOT NULL,
        triggered_at        DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        triggered_by        VARCHAR(50)   NOT NULL,   -- 'manual' | 'scheduler' | 'threshold'
        duration_ms         INT           NULL,
        root_cause_pt       NVARCHAR(MAX) NULL,
        confidence_score    FLOAT         NULL,
        executive_summary   NVARCHAR(MAX) NULL,
        result_json         NVARCHAR(MAX) NULL,       -- InvestigationResult serializado
        incident_id         INT           NULL,       -- FK para performance_incidents
        resolved_at         DATETIME2     NULL,
        resolved_by         VARCHAR(255)  NULL
    );
    PRINT '[CREATED] dbo.performance_investigations';
END
ELSE
    PRINT '[SKIP] dbo.performance_investigations ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_perf_inv_triggered_at' AND object_id = OBJECT_ID('dbo.performance_investigations'))
    CREATE INDEX IX_perf_inv_triggered_at ON dbo.performance_investigations(triggered_at DESC);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_perf_inv_instance_time' AND object_id = OBJECT_ID('dbo.performance_investigations'))
    CREATE INDEX IX_perf_inv_instance_time ON dbo.performance_investigations(instance, triggered_at DESC);
GO

-- -----------------------------------------------------------------------------
-- 2. performance_incidents — agregacao de investigacoes relacionadas
-- -----------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'performance_incidents' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.performance_incidents (
        incident_id         INT           IDENTITY(1,1) PRIMARY KEY,
        created_at          DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        resolved_at         DATETIME2     NULL,
        instance            VARCHAR(255)  NOT NULL,
        investigation_ids   NVARCHAR(MAX) NULL,       -- JSON array de ids
        root_cause_pt       NVARCHAR(MAX) NULL,
        severity            VARCHAR(20)   NOT NULL,
        ticket_url          VARCHAR(500)  NULL
    );
    PRINT '[CREATED] dbo.performance_incidents';
END
ELSE
    PRINT '[SKIP] dbo.performance_incidents ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_perf_inc_instance_created' AND object_id = OBJECT_ID('dbo.performance_incidents'))
    CREATE INDEX IX_perf_inc_instance_created ON dbo.performance_incidents(instance, created_at DESC);
GO

-- -----------------------------------------------------------------------------
-- 3. performance_query_baselines — baselines 7d/30d para regressao silenciosa
-- -----------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'performance_query_baselines' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.performance_query_baselines (
        query_hash             BINARY(8)    NOT NULL,
        instance               VARCHAR(255) NOT NULL,
        database_name          VARCHAR(255) NOT NULL,
        avg_elapsed_ms_7d      FLOAT        NULL,
        avg_elapsed_ms_30d     FLOAT        NULL,
        avg_worker_ms_7d       FLOAT        NULL,
        avg_worker_ms_30d      FLOAT        NULL,
        avg_logical_reads_7d   BIGINT       NULL,
        avg_logical_reads_30d  BIGINT       NULL,
        executions_per_hour_7d FLOAT        NULL,
        last_updated           DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
        PRIMARY KEY (query_hash, instance, database_name)
    );
    PRINT '[CREATED] dbo.performance_query_baselines';
END
ELSE
    PRINT '[SKIP] dbo.performance_query_baselines ja existe';
GO

-- -----------------------------------------------------------------------------
-- 4. performance_action_history — historico de accoes aplicadas pelo DBA
-- -----------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'performance_action_history' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.performance_action_history (
        action_id           INT           IDENTITY(1,1) PRIMARY KEY,
        instance            VARCHAR(255)  NOT NULL,
        database_name       VARCHAR(255)  NULL,
        object_name         VARCHAR(500)  NULL,
        action_type         VARCHAR(50)   NOT NULL,   -- 'CREATE_INDEX' | 'UPDATE_STATS' | ...
        action_sql          NVARCHAR(MAX) NULL,
        applied_at          DATETIME2     NOT NULL,
        applied_by          VARCHAR(255)  NOT NULL,
        outcome_metric      VARCHAR(100)  NULL,       -- 'avg_duration_ms'
        outcome_before      FLOAT         NULL,
        outcome_after       FLOAT         NULL,
        notes_pt            NVARCHAR(MAX) NULL,
        investigation_id    VARCHAR(64)   NULL        -- FK para performance_investigations
    );
    PRINT '[CREATED] dbo.performance_action_history';
END
ELSE
    PRINT '[SKIP] dbo.performance_action_history ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_action_hist_instance_obj' AND object_id = OBJECT_ID('dbo.performance_action_history'))
    CREATE INDEX IX_action_hist_instance_obj ON dbo.performance_action_history(instance, object_name);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_action_hist_applied_at' AND object_id = OBJECT_ID('dbo.performance_action_history'))
    CREATE INDEX IX_action_hist_applied_at ON dbo.performance_action_history(applied_at DESC);
GO

PRINT '';
PRINT '========================================================================';
PRINT 'Performance Module Schema aplicado com sucesso';
PRINT '4 tabelas prontas: investigations, incidents, query_baselines, action_history';
PRINT '========================================================================';
GO
