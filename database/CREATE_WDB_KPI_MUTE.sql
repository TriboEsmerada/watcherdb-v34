/*
==============================================================================
Wave R+10 (2026-05-25) -- Smart Defaults Initiative

CRIAR TABELA WDB_KPI_MUTE
==============================================================================
Universal mute list para silenciar KPIs por instance. Camada 1 do
priority chain definido em docs/architecture/SMART_DEFAULTS_PRINCIPLE.md.

Caracteristicas chave:
  - Universal: 1 table partilhada por todos KPIs (kpi_type discriminator)
  - Instance-level only (per-DB seria config sprawl)
  - Expiry MANDATORY (no permanent mutes -- forca review periodico)
  - Reason MANDATORY (audit trail)
  - Created_By tracking
  - Soft idempotent (PK garante 1 row per kpi+instance)

Aplicar em: WatcherDB_Intelligence (shared infra)
Idempotente: sim (IF NOT EXISTS check + ALTER)
==============================================================================
*/

USE WatcherDB_Intelligence;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WDB_KPI_MUTE')
BEGIN
    CREATE TABLE dbo.WDB_KPI_MUTE (
        Kpi_Type    NVARCHAR(40)    NOT NULL,    -- 'backup-failed', 'disk-usage', etc
        Instance    NVARCHAR(128)   NOT NULL,
        Reason      NVARCHAR(500)   NOT NULL,    -- audit-friendly justificacao
        Created_By  NVARCHAR(128)   NOT NULL,    -- admin username
        Created_At  DATETIME2       NOT NULL DEFAULT GETDATE(),
        Mute_Until  DATETIME2       NOT NULL,    -- expiry mandatory
        CONSTRAINT PK_WDB_KPI_MUTE PRIMARY KEY CLUSTERED (Kpi_Type, Instance)
    );
    PRINT '[OK] Tabela WDB_KPI_MUTE criada';
END
ELSE
BEGIN
    PRINT '[INFO] Tabela WDB_KPI_MUTE ja existe';
END
GO

-- Index para query "active mutes only" (Mute_Until > GETDATE())
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WDB_KPI_MUTE_ACTIVE' AND object_id = OBJECT_ID('dbo.WDB_KPI_MUTE'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_WDB_KPI_MUTE_ACTIVE
        ON dbo.WDB_KPI_MUTE (Mute_Until)
        INCLUDE (Kpi_Type, Instance, Reason)
        WHERE Mute_Until > '2026-01-01';  -- filtered index (efficient lookups)
    PRINT '[OK] Index IX_WDB_KPI_MUTE_ACTIVE criado';
END
GO

-- Grant SELECT to sql_monitoring (read for KPI alert filtering)
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'sql_monitoring')
BEGIN
    GRANT SELECT ON dbo.WDB_KPI_MUTE TO sql_monitoring;
    PRINT '[OK] GRANT SELECT WDB_KPI_MUTE TO sql_monitoring';
END
GO

-- Validacao
SELECT
    t.name AS table_name,
    c.name AS column_name,
    ty.name AS data_type,
    c.is_nullable
FROM sys.tables t
INNER JOIN sys.columns c ON c.object_id = t.object_id
INNER JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.name = 'WDB_KPI_MUTE'
ORDER BY c.column_id;
