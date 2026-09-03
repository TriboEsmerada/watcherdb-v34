-- ============================================================================
-- FIX: KPI "SQL Services Down" mostra instancias fantasma (ja recuperadas)
-- ============================================================================
-- Causa raiz:
--   - Tabela KPI_MSSQL_SERVER_OFFLINE_EVENTS e append-only
--   - Flag Is_Resolved nunca e actualizada pelo collector V1 Intelligence
--   - usp_ResolveServerOfflineEvent so corre em trigger manual (botao UI)
--   - As 3 views filtravam "WHERE Is_Resolved = 0 AND Event_Time >= 7 dias",
--     logo qualquer evento sql_down dos ultimos 7 dias aparece eternamente
--
-- Fix (sem tocar no collector):
--   - Redesenhar as views para olharem apenas para o ULTIMO evento recente
--     de cada servidor (janela 15 min, alinhada com FRESHNESS_WINDOWS['services'])
--   - Se o ultimo evento na janela for offline/sql_down/partial -> aparece
--   - Se nao ha evento recente -> servidor esta OK agora
--
-- Aplicar em: WatcherDB_Intelligence (SQLHDSTST505\I01)
-- Idempotente: pode ser re-executado
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '=== FIX: Server Offline Views (latest-state semantics) ===';
GO

-- ----------------------------------------------------------------------------
-- 1) AGG_VIEW — contadores summary (usada em helpers.py:1545 query_agg)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
GO

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

PRINT '  Recreated: KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW';
GO

-- ----------------------------------------------------------------------------
-- 2) DET_VIEW — lista detalhada (usada em helpers.py:1557 query_det)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
GO

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

PRINT '  Recreated: KPI_MSSQL_SERVER_OFFLINE_DET_VIEW';
GO

-- ----------------------------------------------------------------------------
-- 3) GROUPED_VIEW — modal do dashboard (intelligence_kpis.py:1606 sql-services-down)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW;
GO

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
    1 AS Event_Count,                        -- 1 evento recente (por desenho)
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

PRINT '  Recreated: KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW';
GO

-- ----------------------------------------------------------------------------
-- 4) Sweep: marcar como resolvidos todos os eventos antigos (> 15 min)
--    — apenas para manter a tabela limpa e reduzir o working set
-- ----------------------------------------------------------------------------
UPDATE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
SET Is_Resolved = 1,
    Resolved_Time = COALESCE(Resolved_Time, GETDATE())
WHERE Is_Resolved = 0
  AND Event_Time < DATEADD(MINUTE, -15, GETDATE());

PRINT '';
PRINT CONCAT('  Sweep: ', @@ROWCOUNT, ' eventos stale marcados como resolvidos');
GO

-- ----------------------------------------------------------------------------
-- 5) Validacao
-- ----------------------------------------------------------------------------
PRINT '';
PRINT '=== Validacao ===';

SELECT 'AGG_VIEW' AS View_Name, * FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
SELECT 'GROUPED_VIEW' AS View_Name, COUNT(*) AS Rows_Returned FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW;
SELECT 'DET_VIEW' AS View_Name, COUNT(*) AS Rows_Returned FROM dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;

PRINT '';
PRINT '=== FIX completo ===';
GO
