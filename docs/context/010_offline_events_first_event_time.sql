-- ============================================================================
-- Migration 010: hora de inicio verdadeira + fim do falso "Offline 0"
-- ----------------------------------------------------------------------------
-- Data: 2026-09-14 | Gate: watcherdb-v1-intel-specialist, GO nas 4 pecas, zero vetos
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring)
--
-- CONTEXTO (medido na base viva, nao assumido):
--   O cartao de Disponibilidade mostrou "Online 61 / Offline 0" a 10/09 com o SQLHDSPRD407
--   em baixo ha 6h30. Tres defeitos juntos:
--   1. As 3 vistas so contavam eventos com Event_Time nos ultimos 15 min. O MERGE reescreve
--      Event_Time a cada ciclo; quando o recolhedor salta ciclos, o evento ABERTO envelhece
--      e sai da vista.
--   2. Nao havia onde guardar a hora de inicio: a GROUPED_VIEW expunha Event_Time com o alias
--      First_Event_Time, logo o "desde" da modal mostrava a ultima confirmacao.
--   3. Eventos por HOST (SQLHDSPRD213) cruzados por igualdade com o inventario por INSTANCIA
--      (SQLHDSPRD213_I01): o Env saia Undefined e o filtro de ambiente do portal escondia-o.
--
-- ORDEM OBRIGATORIA: esta migracao corre DEPOIS da 008/008b. A 008b faz CREATE PROCEDURE com
-- o corpo inteiro e SEM First_Event_Time: se a correres depois desta, perdes a hora de
-- inicio em silencio. Por isso a proc abaixo e gerada conforme as colunas da 008 existam
-- ou nao -- funciona nas bases que receberam a 008 e nas que nao receberam.
--
-- PRE-CONDICAO: fechar eventos orfaos ANTES das vistas (passo 1). Sem isso, eventos de
-- servidores desactivados passam a contar como offline (medido: 5 orfaos de Maio e Julho).
--
-- Idempotente. Aditiva na tabela. Rollback: vistas voltam do canonico anterior,
-- DROP COLUMN First_Event_Time, e os Event_ID fechados ficam no output do passo 1.
-- ============================================================================
USE WatcherDB_Intelligence;
GO
SET NOCOUNT ON;
GO

PRINT '1/5 Fechar eventos orfaos (fora do inventario E com mais de 24h)';
SELECT e.Event_ID, e.Server_Name, e.Event_Time
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS e
WHERE e.Is_Resolved = 0
  AND e.Event_Time < DATEADD(HOUR, -24, GETDATE())
  AND NOT EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_INST_ENVS i
                  WHERE i.Instance = e.Server_Name
                     OR i.Instance LIKE e.Server_Name + '[_]%');   -- guarda: e o rollback

UPDATE e SET Is_Resolved = 1, Resolved_Time = GETDATE(), Resolved_By = 'auto-orphan-cleanup'
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS e
WHERE e.Is_Resolved = 0
  AND e.Event_Time < DATEADD(HOUR, -24, GETDATE())
  AND NOT EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_INST_ENVS i
                  WHERE i.Instance = e.Server_Name
                     OR i.Instance LIKE e.Server_Name + '[_]%');
PRINT '   fechados: ' + CAST(@@ROWCOUNT AS VARCHAR(10));
GO

PRINT '2/5 Coluna First_Event_Time';
IF COL_LENGTH('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS', 'First_Event_Time') IS NULL
BEGIN
    ALTER TABLE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS ADD First_Event_Time DATETIME2 NULL;
    PRINT '   criada (sem backfill: NULL e mais honesto do que uma data inventada)';
END
ELSE PRINT '   ja existe - skip';
GO

PRINT '3/5 usp_MSSQL_Server_Offline_Upsert grava First_Event_Time (so no INSERT)';
DECLARE @sql NVARCHAR(MAX);
IF COL_LENGTH('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS', 'Service_Check_Attempted') IS NOT NULL
BEGIN
    SET @sql = N'ALTER PROCEDURE dbo.usp_MSSQL_Server_Offline_Upsert
    @Server_Name NVARCHAR(256),
    @Diagnosis NVARCHAR(50),
    @Ping_OK BIT,
    @Ping_Message NVARCHAR(500) = NULL,
    @Services_Down NVARCHAR(1000) = NULL,
    @Service_Check_Attempted BIT = 0,
    @Service_Check_Method NVARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- Migration 010 (A1, 2026-09-14): First_Event_Time gravado UMA vez, no INSERT.
    -- Event_Time continua a ser a ultima confirmacao (auto-resolve e frescura dependem dela).
    MERGE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS AS target
    USING (SELECT @Server_Name AS Server_Name) AS source
    ON target.Server_Name = source.Server_Name AND target.Is_Resolved = 0
    WHEN MATCHED THEN
        UPDATE SET
            Diagnosis = @Diagnosis,
            Ping_OK = @Ping_OK,
            Ping_Message = @Ping_Message,
            Services_Down = @Services_Down,
            Service_Check_Attempted = @Service_Check_Attempted,
            Service_Check_Method = @Service_Check_Method,
            Event_Time = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down,
                Service_Check_Attempted, Service_Check_Method,
                Event_Time, First_Event_Time, Is_Resolved)
        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down,
                @Service_Check_Attempted, @Service_Check_Method,
                GETDATE(), GETDATE(), 0);
END;';
    PRINT '   base COM a migracao 008: proc de 7 parametros';
END
ELSE
BEGIN
    SET @sql = N'ALTER PROCEDURE dbo.usp_MSSQL_Server_Offline_Upsert
    @Server_Name NVARCHAR(256),
    @Diagnosis NVARCHAR(50),
    @Ping_OK BIT,
    @Ping_Message NVARCHAR(500) = NULL,
    @Services_Down NVARCHAR(1000) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- Migration 010 (A1, 2026-09-14): First_Event_Time gravado UMA vez, no INSERT.
    -- Event_Time continua a ser a ultima confirmacao (auto-resolve e frescura dependem dela).
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
        INSERT (Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down,
                Event_Time, First_Event_Time, Is_Resolved)
        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down,
                GETDATE(), GETDATE(), 0);
END;';
    PRINT '   base SEM a migracao 008: proc de 5 parametros';
END
EXEC sp_executesql @sql;
GO

IF OBJECT_DEFINITION(OBJECT_ID('dbo.usp_MSSQL_Server_Offline_Upsert')) NOT LIKE '%First_Event_Time%'
    RAISERROR('3/5 FALHOU: a proc nao grava First_Event_Time. Nao prossigas.', 16, 1);
ELSE PRINT '   verificado';
GO

PRINT '4/5 As TRES vistas sem janela de 15 min (mudam juntas: CTE copy-pasted)';
GO
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW', 'V') IS NOT NULL DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
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
    -- A1 2026-09-14: a janela de 15 min saiu. Um evento ABERTO deixa de desaparecer do
    -- cartao so' porque o recolhedor saltou ciclos (episodio de 10/09: 6h30 em baixo com
    -- Offline=0). A frescura passa a ser sinal, nao filtro. Depende de P1 (orfaos fechados),
    -- senao eventos de servidores desactivados voltariam como falsos positivos.
    WHERE Is_Resolved = 0
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
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW', 'V') IS NOT NULL DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
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
    -- A1 2026-09-14: a janela de 15 min saiu. Um evento ABERTO deixa de desaparecer do
    -- cartao so' porque o recolhedor saltou ciclos (episodio de 10/09: 6h30 em baixo com
    -- Offline=0). A frescura passa a ser sinal, nao filtro. Depende de P1 (orfaos fechados),
    -- senao eventos de servidores desactivados voltariam como falsos positivos.
    WHERE Is_Resolved = 0
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
-- A1 2026-09-14: os eventos sao por HOST (SQLHDSPRD213) e o inventario e' por INSTANCIA
-- (SQLHDSPRD213_I01), logo a igualdade exacta nunca casa e o Env saía 'Undefined'. Como o
-- portal filtra por ambiente, um servidor em baixo podia desaparecer do cartao mesmo dentro
-- da janela. OUTER APPLY com TOP 1 em vez de JOIN: aceita o prefixo sem multiplicar linhas
-- quando o host tem varias instancias, e prefere sempre a correspondencia exacta.
OUTER APPLY (SELECT TOP 1 i.Env FROM dbo.KPI_MSSQL_INST_ENVS i WITH (NOLOCK)
             WHERE i.Instance = soe.Server_Name
                OR i.Instance LIKE soe.Server_Name + '[_]%'
             ORDER BY CASE WHEN i.Instance = soe.Server_Name THEN 0 ELSE 1 END, i.Instance) e
WHERE soe.Diagnosis IN ('offline', 'sql_down', 'partial')
  AND REPLACE(soe.Server_Name, '\', '_') NOT IN (SELECT Instance FROM RecentlyCollectedDistinct)
ORDER BY
    CASE soe.Diagnosis WHEN 'offline' THEN 1 WHEN 'sql_down' THEN 2 ELSE 3 END,
    soe.Event_Time DESC;
GO
IF OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW', 'V') IS NOT NULL DROP VIEW dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW;
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
    -- A1 2026-09-14: a janela de 15 min saiu. Um evento ABERTO deixa de desaparecer do
    -- cartao so' porque o recolhedor saltou ciclos (episodio de 10/09: 6h30 em baixo com
    -- Offline=0). A frescura passa a ser sinal, nao filtro. Depende de P1 (orfaos fechados),
    -- senao eventos de servidores desactivados voltariam como falsos positivos.
    WHERE Is_Resolved = 0
    GROUP BY Server_Name
),
LatestStatus AS (
    SELECT
        soe.Server_Name,
        soe.Diagnosis,
        soe.Ping_OK,
        soe.Ping_Message,
        soe.Services_Down,
        soe.Event_Time,
        soe.First_Event_Time
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
    -- A1 2026-09-14: First_Event_Time deixa de ser um alias de Event_Time. Event_Time e'
    -- reescrito pelo MERGE a cada ciclo, logo o 'desde' da modal mentia (6h30 em baixo
    -- aparecia como 1 min). COALESCE cobre as linhas anteriores a migracao, sem backfill
    -- inventado. Last_Seen mantem a semantica de 'ultima confirmacao'.
    COALESCE(ls.First_Event_Time, ls.Event_Time) AS First_Event_Time,
    ls.Event_Time AS Last_Event_Time,
    ls.Event_Time AS Last_Seen_Time,
    DATEDIFF(MINUTE, COALESCE(ls.First_Event_Time, ls.Event_Time), GETDATE()) AS Minutes_Since_First_Event,
    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_Last_Event,
    DATEDIFF(MINUTE, ls.Event_Time, GETDATE()) AS Minutes_Since_Last_Seen,
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
-- A1 2026-09-14: os eventos sao por HOST (SQLHDSPRD213) e o inventario e' por INSTANCIA
-- (SQLHDSPRD213_I01), logo a igualdade exacta nunca casa e o Env saía 'Undefined'. Como o
-- portal filtra por ambiente, um servidor em baixo podia desaparecer do cartao mesmo dentro
-- da janela. OUTER APPLY com TOP 1 em vez de JOIN: aceita o prefixo sem multiplicar linhas
-- quando o host tem varias instancias, e prefere sempre a correspondencia exacta.
OUTER APPLY (SELECT TOP 1 i.Env FROM dbo.KPI_MSSQL_INST_ENVS i WITH (NOLOCK)
             WHERE i.Instance = ls.Server_Name
                OR i.Instance LIKE ls.Server_Name + '[_]%'
             ORDER BY CASE WHEN i.Instance = ls.Server_Name THEN 0 ELSE 1 END, i.Instance) e;
GO

PRINT '5/5 Verificacao';
SELECT
    (SELECT COUNT(*) FROM sys.sql_modules
      WHERE object_id IN (OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW'),
                          OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW'),
                          OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW'))
        AND definition LIKE '%DATEADD(MINUTE, -15%')                       AS vistas_com_janela_esperado_0,
    CASE WHEN COL_LENGTH('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS','First_Event_Time') IS NULL
         THEN 0 ELSE 1 END                                                  AS coluna_esperado_1,
    CASE WHEN OBJECT_DEFINITION(OBJECT_ID('dbo.usp_MSSQL_Server_Offline_Upsert'))
              LIKE '%First_Event_Time%' THEN 1 ELSE 0 END                   AS proc_esperado_1;
GO
PRINT 'Migration 010 concluida.';
GO
