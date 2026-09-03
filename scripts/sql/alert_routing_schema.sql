-- =============================================================================
-- WatcherDB V3.3 Standard Edition — Alert Routing dispatch log schema
-- =============================================================================
-- Audit 2026-04-22 / S3-14 C1 — scaffold inicial de alert routing.
-- Persiste historico de dispatches (cada send individual, nao agregado).
-- Idempotente: re-executar e seguro (IF NOT EXISTS guard).
-- =============================================================================
-- Aplicavel a: WatcherDB_Intelligence (BD partilhada V1 Intel + V3.3 + V5).
-- Ownership: V3.3 escreve, V1 Intel poderá ler futuramente para correlacao
-- com KPI thresholds (follow-up).
-- =============================================================================

USE WatcherDB_Intelligence;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE name = 'alert_dispatch_log' AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TABLE dbo.alert_dispatch_log (
        dispatch_id      BIGINT IDENTITY(1,1) NOT NULL
                         CONSTRAINT PK_alert_dispatch_log PRIMARY KEY,
        alert_id         VARCHAR(128)   NOT NULL,   -- dedup key
        alert_source     VARCHAR(50)    NOT NULL,   -- 'kpi' | 'performance' | 'manual' | 'test'
        severity         VARCHAR(20)    NOT NULL,   -- 'info' | 'warning' | 'critical'
        title            NVARCHAR(255)  NOT NULL,
        body             NVARCHAR(MAX)  NULL,
        server_id        VARCHAR(255)   NULL,
        channels_target  NVARCHAR(500)  NOT NULL,   -- JSON array ['email','teams']
        channels_sent    NVARCHAR(500)  NULL,       -- JSON array — sucesso
        channels_failed  NVARCHAR(500)  NULL,       -- JSON array — falha
        error_detail     NVARCHAR(MAX)  NULL,
        triggered_by     VARCHAR(50)    NOT NULL,   -- 'manual' | 'threshold' | 'test'
        triggered_at     DATETIME2      NOT NULL
                         CONSTRAINT DF_alert_dispatch_log_triggered_at
                         DEFAULT SYSUTCDATETIME(),
        sent_at          DATETIME2      NULL
    );

    CREATE INDEX IX_alert_dispatch_log_alert_id
        ON dbo.alert_dispatch_log (alert_id, triggered_at DESC);

    CREATE INDEX IX_alert_dispatch_log_severity
        ON dbo.alert_dispatch_log (severity, triggered_at DESC);

    PRINT '[CREATED] dbo.alert_dispatch_log';
END
ELSE
    PRINT '[SKIP] dbo.alert_dispatch_log ja existe';
GO
