-- ============================================================================
-- FIX: SQL Nao Respondeu mostra fantasmas (collection foi SUCCESS depois)
-- ============================================================================
-- Cenario: KPI_MSSQL_SERVER_OFFLINE_EVENTS tem evento sql_down dum timeout
-- ha 5-15 min, mas o ciclo seguinte do collector ja correu com SUCCESS para
-- esse mesmo servidor — listener responde OK, dados foram inseridos noutras
-- KPI_*_STG.
--
-- Como a flag Is_Resolved nao e actualizada e o collector so chama o
-- helper _resolve_server_offline_events em ciclos com TIMEOUT (nao em
-- ciclos normais), eventos historicos ficavam visiveis na janela 15 min.
--
-- Sinal de recuperacao: usar KPI_MSSQL_INST_AVAILABILITY_STG_* — esta tabela
-- tem 1 row por instancia colectada com sucesso, e populada apenas quando
-- o listener SQL responde. Distribuida em 6 fisicas (BLUE/GREEN x PRD/QA/TST)
-- por causa do swap blue/green; UNION ALL cobre as 6.
--
-- IMPORTANTE: este filtro distingue Windows service Running vs SQL listener
-- responding. So escondem do card servidores onde o collector REALMENTE
-- conseguiu colectar dados via listener — Windows service Running sozinho
-- nao e prova de listener OK (caso real: server X tem instancia I01 com
-- listener bloqueado e I02 com listener aberto; aba Services mostra ambos
-- como RUNNING mas collector so consegue I02).
--
-- Nota de formato: INST_AVAILABILITY.Instance usa underscore (HOST_INST),
-- OFFLINE_EVENTS.Server_Name usa backslash (HOST\INST). JOIN faz REPLACE.
--
-- Aplicar em: WatcherDB_Intelligence (SQLHDSTST505\I01)
-- Idempotente — re-executavel
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '=== FIX: Server Offline Views (reconcile com INST_AVAILABILITY) ===';
GO

-- ----------------------------------------------------------------------------
-- 1) AGG_VIEW
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW
AS
WITH RecentlyCollected AS (
    -- Instancias com colecta successful nos ultimos 10 min
    -- UNION ALL das 6 fisicas BLUE/GREEN x PRD/QA/TST.
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA  WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
),
RecentlyCollectedDistinct AS (
    SELECT DISTINCT Instance
    FROM RecentlyCollected
    WHERE Update_TS >= DATEADD(MINUTE, -10, GETDATE())
),
LatestEventPerServer AS (
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
      -- Reconciliacao: excluir se collector colectou dados desta instancia recentemente
      AND REPLACE(soe.Server_Name, '\', '_') NOT IN (SELECT Instance FROM RecentlyCollectedDistinct)
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

PRINT '  Recreated: KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW (com INST_AVAILABILITY reconcile)';
GO

-- ----------------------------------------------------------------------------
-- 2) DET_VIEW
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW
AS
WITH RecentlyCollected AS (
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA  WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
),
RecentlyCollectedDistinct AS (
    SELECT DISTINCT Instance
    FROM RecentlyCollected
    WHERE Update_TS >= DATEADD(MINUTE, -10, GETDATE())
),
LatestEventPerServer AS (
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
        WHEN soe.Diagnosis = 'sql_down' THEN 'SQL Nao Respondeu (collector central)'
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
  AND REPLACE(soe.Server_Name, '\', '_') NOT IN (SELECT Instance FROM RecentlyCollectedDistinct)
ORDER BY
    CASE soe.Diagnosis WHEN 'offline' THEN 1 WHEN 'sql_down' THEN 2 ELSE 3 END,
    soe.Event_Time DESC;
GO

PRINT '  Recreated: KPI_MSSQL_SERVER_OFFLINE_DET_VIEW (com INST_AVAILABILITY reconcile)';
GO

-- ----------------------------------------------------------------------------
-- 3) GROUPED_VIEW (a usada pelo modal do card)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW
AS
WITH RecentlyCollected AS (
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA  WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION ALL
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
),
RecentlyCollectedDistinct AS (
    SELECT DISTINCT Instance
    FROM RecentlyCollected
    WHERE Update_TS >= DATEADD(MINUTE, -10, GETDATE())
),
LatestEventPerServer AS (
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
      AND REPLACE(soe.Server_Name, '\', '_') NOT IN (SELECT Instance FROM RecentlyCollectedDistinct)
)
SELECT
    ls.Server_Name,
    ls.Server_Name AS Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    1 AS Event_Count,
    ls.Diagnosis,
    CASE
        WHEN ls.Diagnosis = 'offline'  THEN 'Servidor Offline'
        WHEN ls.Diagnosis = 'sql_down' THEN 'SQL Nao Respondeu (collector central)'
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

PRINT '  Recreated: KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW (com INST_AVAILABILITY reconcile)';
GO

-- ----------------------------------------------------------------------------
-- 4) Validacao
-- ----------------------------------------------------------------------------
PRINT '';
PRINT '=== Validacao ===';

SELECT 'Total eventos abertos (15 min)' AS Metric, COUNT(*) AS Cnt
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
WHERE Event_Time >= DATEADD(MINUTE, -15, GETDATE())
  AND Is_Resolved = 0
  AND Diagnosis IN ('offline','sql_down','partial');

WITH AllAvailability AS (
    SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD WITH (NOLOCK)
    UNION ALL SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA  WITH (NOLOCK)
    UNION ALL SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST WITH (NOLOCK)
    UNION ALL SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION ALL SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION ALL SELECT Instance, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
)
SELECT 'Instancias com colecta recente (10 min)' AS Metric, COUNT(DISTINCT Instance) AS Cnt
FROM AllAvailability
WHERE Update_TS >= DATEADD(MINUTE, -10, GETDATE());

SELECT 'GROUPED_VIEW depois de reconcile' AS Metric, COUNT(*) AS Cnt
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW;

SELECT * FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;

PRINT '';
PRINT '=== FIX completo ===';
GO
