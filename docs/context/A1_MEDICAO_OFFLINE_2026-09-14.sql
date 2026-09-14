/* =============================================================================
   A1 — medição das causas do "Offline 0" (bloco A do plano de 14/09)
   Correr na WatcherDB_Intelligence da 8434. SÓ LEITURA: nenhum INSERT/UPDATE/DDL.
   Objectivo: quantificar cada uma das quatro causas antes de propor a correcção,
   em vez de as assumir a partir do episódio de 10/09.
   ============================================================================= */
SET NOCOUNT ON;

PRINT '=== 0. Contexto ===';
SELECT DB_NAME() AS base, @@SERVERNAME AS servidor, GETDATE() AS agora;
-- Esperado: base = WatcherDB_Intelligence. Se não for, PARA aqui.

PRINT '=== 1. Quantos eventos abertos a janela de 15 min esconde ===';
SELECT
    COUNT(*)                                                                        AS abertos_total,
    SUM(CASE WHEN Event_Time >= DATEADD(MINUTE, -15, GETDATE()) THEN 1 ELSE 0 END)  AS visiveis_na_vista,
    SUM(CASE WHEN Event_Time <  DATEADD(MINUTE, -15, GETDATE()) THEN 1 ELSE 0 END)  AS escondidos_pela_janela,
    MIN(Event_Time)                                                                 AS evento_mais_antigo,
    MAX(Event_Time)                                                                 AS evento_mais_recente
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
WHERE Is_Resolved = 0;
-- Causa (a): tudo o que cair em "escondidos_pela_janela" é um servidor em baixo
-- que o cartão conta como zero. Se der 0, a janela não está a esconder nada AGORA,
-- e a causa só se manifesta quando o recolhedor salta ciclos.

PRINT '=== 2. Detalhe dos eventos abertos ===';
SELECT TOP 40
    Server_Name,
    Event_Time,
    DATEDIFF(MINUTE, Event_Time, GETDATE()) AS minutos_desde_ultima_confirmacao,
    CASE WHEN Event_Time >= DATEADD(MINUTE, -15, GETDATE()) THEN 'VISIVEL' ELSE 'ESCONDIDO' END AS na_vista,
    Diagnosis
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
WHERE Is_Resolved = 0
ORDER BY Event_Time DESC;
-- Causa (b): "minutos_desde_ultima_confirmacao" NÃO é há quanto tempo o servidor
-- caiu. O MERGE reescreve Event_Time a cada ciclo, portanto a hora de início
-- perde-se. Um servidor em baixo há 6 horas aparece aqui com 1 ou 2 minutos.

PRINT '=== 3. A tabela já tem onde guardar a hora de inicio? ===';
SELECT c.name AS coluna, t.name AS tipo, c.is_nullable
FROM sys.columns c
JOIN sys.types t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS')
ORDER BY c.column_id;
-- Decide se a correcção precisa de coluna nova (First_Event_Time / Last_Seen_Time)
-- ou se já existe uma que o MERGE está a ignorar. Muda o âmbito do DDL.

PRINT '=== 4. O que a vista devolve neste momento ===';
SELECT COUNT(*) AS linhas_na_vista FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK);
SELECT TOP 20 * FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK);
-- Comparar com o ponto 1: a diferença é exactamente o que o cartão deixa de contar.

PRINT '=== 5. Cobertura da recolha de disponibilidade (causa do 61+0 <> 63) ===';
WITH Recolhidas AS (
    SELECT Instance, Is_Available, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD  WITH (NOLOCK)
    UNION ALL SELECT Instance, Is_Available, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA   WITH (NOLOCK)
    UNION ALL SELECT Instance, Is_Available, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST  WITH (NOLOCK)
    UNION ALL SELECT Instance, Is_Available, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION ALL SELECT Instance, Is_Available, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION ALL SELECT Instance, Is_Available, Update_TS FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
)
SELECT
    COUNT(DISTINCT Instance)                                                                     AS instancias_com_linha,
    COUNT(DISTINCT CASE WHEN Update_TS >= DATEADD(MINUTE, -15, GETDATE()) THEN Instance END)     AS recolhidas_ha_menos_de_15min,
    COUNT(DISTINCT CASE WHEN Is_Available = 1 THEN Instance END)                                 AS marcadas_online,
    COUNT(DISTINCT CASE WHEN Is_Available = 0 THEN Instance END)                                 AS marcadas_offline,
    MAX(Update_TS)                                                                               AS recolha_mais_recente
FROM Recolhidas;
-- Causa (d): se "marcadas_offline" for 0 e "instancias_com_linha" for menor que o
-- inventário (63), as que faltam não estão offline: estão SEM RECOLHA, e hoje não
-- existe linha nenhuma no cartão para elas. Somar online + offline nunca dá 63.

PRINT '=== 6. Ambiente por instancia: quantas caem em Undefined ===';
WITH Recolhidas AS (
    SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD  WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA   WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST  WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
)
SELECT
    COUNT(*)                                              AS instancias,
    SUM(CASE WHEN e.Instance IS NULL THEN 1 ELSE 0 END)   AS sem_ambiente_definido
FROM Recolhidas r
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK) ON e.Instance = r.Instance;

SELECT TOP 20 r.Instance AS instancia_sem_ambiente
FROM (
    SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_PRD  WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_QA   WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_BLUE_TST  WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_PRD WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_QA  WITH (NOLOCK)
    UNION SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG_GREEN_TST WITH (NOLOCK)
) r
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK) ON e.Instance = r.Instance
WHERE e.Instance IS NULL;
-- Causa (c): uma instância sem ambiente cai em "Undefined" e o filtro de ambiente
-- do portal esconde-a. Se a lista vier vazia, esta causa não está activa hoje.

PRINT '=== FIM. Cola os 6 resultados. ===';
