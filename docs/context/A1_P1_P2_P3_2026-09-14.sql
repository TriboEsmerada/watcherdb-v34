/* =============================================================================
   A1 -- o cartao de Disponibilidade deixa de dizer "Offline 0" com servidores em baixo
   Data: 2026-09-14 | Correr na WatcherDB_Intelligence da 8434 (SSMS, tu -- regra 5)
   Parecer: watcherdb-v1-intel-specialist. GO nas 4 pecas, zero vetos, condicoes incorporadas.

   MEDIDO a 14/09 12:22 (nao assumido):
     - 5 eventos abertos, TODOS fora da janela de 15 min: 3x 06/05, 1x 08/05, 1x 24/07
     - os 5 sao ORFAOS: os servidores nao existem em KPI_MSSQL_INST_ENVS
     - a GROUPED_VIEW devolve 0 linhas; a frota esta 63/63 online e 63/63 recolhida
     - a tabela de eventos NAO tem coluna para a hora de inicio

   ESTE SCRIPT FAZ P1a, P2 e P3. Fica para lote proprio: o auto-resolve continuo no
   recolhedor (P1b) e o Is_Available=0 (P4, derivado de SERVER_OFFLINE_EVENTS e nao de um
   timeout cru -- condicao do guardiao para nao amplificar tempestades de DNS).

   REVERSIVEL: as 3 vistas voltam do canonico; a coluna sai com DROP COLUMN; os eventos
   fechados voltam com UPDATE Is_Resolved=0 (os Event_ID ficam no output do passo P1a).
   ============================================================================= */
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() <> 'WatcherDB_Intelligence'
BEGIN
    RAISERROR('PARA: liga-te a WatcherDB_Intelligence antes de correr isto.', 16, 1);
    SET NOEXEC ON;
END
GO

PRINT '=== P1a. Fechar eventos orfaos (fora do inventario E com mais de 24h) ===';
-- Condicao do guardiao: a idade evita fechar um evento genuino cujo servidor caiu do
-- inventario ha minutos por reconciliacao em curso. Resolved_By distinto, para auditoria.
IF OBJECT_ID('tempdb..#orfaos') IS NOT NULL DROP TABLE #orfaos;
SELECT e.Event_ID, e.Server_Name, e.Event_Time, e.Diagnosis
INTO #orfaos
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS e
WHERE e.Is_Resolved = 0
  AND e.Event_Time < DATEADD(HOUR, -24, GETDATE())
  AND NOT EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_INST_ENVS i
                  WHERE i.Instance = e.Server_Name
                     OR i.Instance LIKE e.Server_Name + '[_]%');

SELECT 'vao ser fechados' AS passo, * FROM #orfaos;   -- GUARDA ISTO: e o teu rollback

UPDATE e SET Is_Resolved = 1, Resolved_Time = GETDATE(), Resolved_By = 'auto-orphan-cleanup'
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS e
JOIN #orfaos o ON o.Event_ID = e.Event_ID;
PRINT '  fechados: ' + CAST(@@ROWCOUNT AS VARCHAR(10));
GO

PRINT '=== P2. Coluna para a hora de inicio (aditiva) ===';
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS')
                 AND name = 'First_Event_Time')
BEGIN
    ALTER TABLE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS ADD First_Event_Time DATETIME2 NULL;
    PRINT '  coluna First_Event_Time criada';
END
ELSE PRINT '  coluna ja existia';
-- SEM backfill: datar eventos antigos com um valor inventado e pior do que deixar NULL.
-- As vistas resolvem com COALESCE(First_Event_Time, Event_Time).
GO

PRINT '=== P2b. O MERGE grava a hora de inicio, e so no INSERT ===';
GO
ALTER PROCEDURE dbo.usp_MSSQL_Server_Offline_Upsert
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

    -- A1 2026-09-14: Event_Time continua a ser reescrito a cada ciclo (e a ULTIMA
    -- confirmacao, e e assim que o auto-resolve e a frescura funcionam). O que muda:
    -- First_Event_Time e gravado UMA vez, no INSERT, e nunca mais tocado. Sem isto o
    -- "desde" da modal mostrava 1 minuto num servidor em baixo ha 6 horas.
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
                Service_Check_Attempted, Service_Check_Method, Event_Time, First_Event_Time, Is_Resolved)
        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down,
                @Service_Check_Attempted, @Service_Check_Method, GETDATE(), GETDATE(), 0);
END;
GO
PRINT '  procedure actualizada';
GO

PRINT '=== P3. As TRES vistas perdem a janela de 15 min ===';
-- Condicao do guardiao: as 3 juntas. Tinham a mesma CTE copy-pasted; mudar so a GROUPED
-- faria o cartao e a modal discordarem, a classe de bug ja censada a 11/08.
-- Corpo gerado a partir da definicao VIVA (sys.sql_modules), nao do canonico: regra de 31/08.
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
PRINT '  recriada: KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW';
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
PRINT '  recriada: KPI_MSSQL_SERVER_OFFLINE_DET_VIEW';
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
PRINT '  recriada: KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW';
GO

PRINT '=== Verificacao ===';
SELECT 'eventos abertos' AS metrica, COUNT(*) AS valor
  FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WHERE Is_Resolved = 0
UNION ALL SELECT 'linhas na GROUPED_VIEW', COUNT(*) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW
UNION ALL SELECT 'Servers_Offline na AGG_VIEW', Servers_Offline FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW
UNION ALL SELECT 'linhas na DET_VIEW', COUNT(*) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
-- Esperado com a frota toda de pe: 0, 0, 0, 0. Se algum vier maior que 0 depois do P1a,
-- PARA e diz-me: ou ha um servidor mesmo em baixo, ou sobrou um orfao fora da regra das 24h.
GO

/* =============================================================================
   ENSAIO (recomendado pelo guardiao, em vez de parar um servico real)
   Prova P2 e P3 em minutos, sem tocar em nenhuma instancia monitorizada.
   ============================================================================= */
/*
EXEC dbo.usp_MSSQL_Server_Offline_Upsert
     @Server_Name = 'ZZZ_TEST_OFFLINE_SIM', @Diagnosis = 'offline', @Ping_OK = 0,
     @Ping_Message = 'ensaio A1 2026-09-14';

-- envelhece o evento para la dos 15 min: antes do A1 desaparecia da vista, agora fica
UPDATE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
   SET Event_Time = DATEADD(MINUTE, -20, GETDATE())
 WHERE Server_Name = 'ZZZ_TEST_OFFLINE_SIM' AND Is_Resolved = 0;

SELECT Server_Name, First_Event_Time, Last_Seen_Time,
       Minutes_Since_First_Event, Minutes_Since_Last_Seen
  FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WHERE Server_Name = 'ZZZ_TEST_OFFLINE_SIM';
-- Esperado: 1 linha, Minutes_Since_First_Event perto de 0 (a hora de inicio ficou) e
-- Minutes_Since_Last_Seen perto de 20 (a ultima confirmacao envelheceu). Antes do A1: 0 linhas.

DELETE FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WHERE Server_Name = 'ZZZ_TEST_OFFLINE_SIM';
*/
