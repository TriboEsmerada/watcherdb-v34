-- =============================================================================
-- WatcherDB V5 — Collector Health Monitoring Schema
-- Base de dados: WatcherDB_Intelligence em SQLHDSTST505\I01
-- Data: 2026-04-16
-- Idempotente: pode ser executado multiplas vezes em seguranca
-- =============================================================================

USE WatcherDB_Intelligence;
GO

SET NOCOUNT ON;
GO

-- -----------------------------------------------------------------------------
-- 1. collector_manual_runs — audit log de execucoes manuais
-- -----------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables
               WHERE name = 'collector_manual_runs' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.collector_manual_runs (
        run_id           INT           IDENTITY(1,1) PRIMARY KEY,
        task_name        VARCHAR(100)  NOT NULL,
        triggered_at     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        triggered_by     VARCHAR(100)  NOT NULL,
        source_ip        VARCHAR(45)   NULL,
        duration_ms      INT           NULL,
        success          BIT           NULL,
        rows_collected   INT           NULL,
        error_message    NVARCHAR(MAX) NULL,
        metadata_json    NVARCHAR(MAX) NULL
    );
    PRINT '[CREATED] dbo.collector_manual_runs';
END
ELSE
    PRINT '[SKIP] dbo.collector_manual_runs ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_manual_runs_task_time'
                 AND object_id = OBJECT_ID('dbo.collector_manual_runs'))
    CREATE INDEX IX_manual_runs_task_time
        ON dbo.collector_manual_runs(task_name, triggered_at DESC);
GO

-- -----------------------------------------------------------------------------
-- 2. collector_run_requests — fila de pedidos PENDING/RUNNING/DONE/FAILED
-- -----------------------------------------------------------------------------
-- Opcao B da arquitectura (ver PROMPT): o portal insere PENDING aqui e o
-- WatcherDBCollector service faz poll para executar out-of-band. Evita
-- conflitos de lock com o scheduler normal.
IF NOT EXISTS (SELECT 1 FROM sys.tables
               WHERE name = 'collector_run_requests' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.collector_run_requests (
        request_id     INT           IDENTITY(1,1) PRIMARY KEY,
        task_name      VARCHAR(100)  NOT NULL,
        requested_at   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        requested_by   VARCHAR(100)  NOT NULL,
        status         VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
            -- PENDING | RUNNING | DONE | FAILED | CANCELLED
        started_at     DATETIME2     NULL,
        completed_at   DATETIME2     NULL,
        duration_ms    INT           NULL,
        error_message  NVARCHAR(MAX) NULL,
        result_json    NVARCHAR(MAX) NULL,
        metadata_json  NVARCHAR(MAX) NULL,
        CONSTRAINT CK_collector_run_requests_status
            CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED', 'CANCELLED'))
    );
    PRINT '[CREATED] dbo.collector_run_requests';
END
ELSE
    PRINT '[SKIP] dbo.collector_run_requests ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_run_requests_status_time'
                 AND object_id = OBJECT_ID('dbo.collector_run_requests'))
    CREATE INDEX IX_run_requests_status_time
        ON dbo.collector_run_requests(status, requested_at DESC);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_run_requests_task_time'
                 AND object_id = OBJECT_ID('dbo.collector_run_requests'))
    CREATE INDEX IX_run_requests_task_time
        ON dbo.collector_run_requests(task_name, requested_at DESC);
GO

-- -----------------------------------------------------------------------------
-- VIEWS DE AUDITORIA (validadas em PRD com poller V1 operacional a 10s)
-- -----------------------------------------------------------------------------
IF OBJECT_ID('dbo.vw_collector_recent_runs', 'V') IS NOT NULL
    DROP VIEW dbo.vw_collector_recent_runs;
GO
CREATE VIEW dbo.vw_collector_recent_runs AS
SELECT TOP 100
    request_id, task_name, status, requested_at, started_at, completed_at,
    duration_ms, error_message, requested_by,
    DATEDIFF(SECOND, requested_at, ISNULL(completed_at, SYSUTCDATETIME())) AS wait_seconds,
    DATEDIFF(SECOND, requested_at, ISNULL(started_at, SYSUTCDATETIME())) AS pickup_lag_seconds
FROM dbo.collector_run_requests
ORDER BY requested_at DESC;
GO
PRINT '[CREATED] dbo.vw_collector_recent_runs';
GO

IF OBJECT_ID('dbo.vw_collector_success_rate_24h', 'V') IS NOT NULL
    DROP VIEW dbo.vw_collector_success_rate_24h;
GO
CREATE VIEW dbo.vw_collector_success_rate_24h AS
SELECT
    SUM(CASE WHEN status = 'DONE'    THEN 1 ELSE 0 END) AS ok,
    SUM(CASE WHEN status = 'FAILED'  THEN 1 ELSE 0 END) AS fail,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
    SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) AS running,
    COUNT(*)                                             AS total,
    CAST(
        100.0 * SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) /
        NULLIF(SUM(CASE WHEN status IN ('DONE','FAILED') THEN 1 ELSE 0 END), 0)
    AS DECIMAL(5,2))                                     AS success_rate_pct,
    AVG(CAST(duration_ms AS BIGINT))                     AS avg_duration_ms,
    MAX(duration_ms)                                     AS max_duration_ms
FROM dbo.collector_run_requests
WHERE requested_at > DATEADD(HOUR, -24, SYSUTCDATETIME());
GO
PRINT '[CREATED] dbo.vw_collector_success_rate_24h';
GO

PRINT '';
PRINT '========================================================================';
PRINT 'Collector Health Schema aplicado com sucesso';
PRINT '2 tabelas: collector_manual_runs, collector_run_requests';
PRINT '2 views:   vw_collector_recent_runs, vw_collector_success_rate_24h';
PRINT '';
PRINT 'Fase 2 VALIDADA: WatcherDBCollector service (V1) tem _manual_run_poller';
PRINT 'operacional (10s interval). Teste real 16/04: request_id=1 pickup <3s,';
PRINT 'execucao 5.4s (14 rows, 6 servers TST).';
PRINT '========================================================================';
GO
