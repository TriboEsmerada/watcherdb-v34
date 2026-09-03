-- ============================================================================
-- VALIDACAO COMPLETA DOS CARDS DE KPI DO DASHBOARD - WatcherDB Intelligence
-- ============================================================================
-- Use este script para validar TODOS os dados exibidos nos cards do dashboard
-- Execute no banco: WatcherDB_Intelligence
-- Data: 2025-12-29
-- ============================================================================

USE WatcherDB_Intelligence;
GO

PRINT '============================================================================'
PRINT 'VALIDACAO COMPLETA DOS CARDS DE KPI DO DASHBOARD'
PRINT '============================================================================'
PRINT ''

-- ============================================================================
-- SECAO 1: DISPONIBILIDADE
-- ============================================================================

PRINT '>>> SECAO 1: DISPONIBILIDADE'
PRINT ''

-- ----------------------------------------------------------------------------
-- 1.1 CARD: INSTANCE AVAILABILITY (Instancias OK / Off)
-- ----------------------------------------------------------------------------
PRINT '--- 1.1 INSTANCE AVAILABILITY ---'

SELECT
    'INSTANCE AVAILABILITY' AS Card,
    SUM(CASE WHEN Is_Available = 1 THEN 1 ELSE 0 END) AS Instances_OK,
    SUM(CASE WHEN Is_Available = 0 THEN 1 ELSE 0 END) AS Instances_Off,
    COUNT(DISTINCT Instance) AS Total_Instances
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK);

-- Por ambiente
SELECT
    'Por Ambiente' AS Info,
    ISNULL(e.Env, 'Undefined') AS Ambiente,
    SUM(CASE WHEN i.Is_Available = 1 THEN 1 ELSE 0 END) AS [OK],
    SUM(CASE WHEN i.Is_Available = 0 THEN 1 ELSE 0 END) AS [Off]
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG AS i WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK) ON e.Instance = i.Instance
GROUP BY e.Env;

-- ----------------------------------------------------------------------------
-- 1.2 CARD: DB AVAILABILITY (Databases Online/Offline)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 1.2 DB AVAILABILITY ---'

SELECT
    'DB AVAILABILITY' AS Card,
    SUM(CASE WHEN [State] = 'ONLINE' THEN 1 ELSE 0 END) AS Databases_Online,
    SUM(CASE WHEN [State] <> 'ONLINE' AND [State] <> 'RESTORING' THEN 1 ELSE 0 END) AS Databases_Problem,
    SUM(CASE WHEN [State] = 'RESTORING' THEN 1 ELSE 0 END) AS Databases_Restoring,
    COUNT(*) AS Total_Databases
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK);

-- Databases com problema (exceto RESTORING)
SELECT
    'Databases com Problema' AS Info,
    Instance,
    [Database],
    [State],
    Update_TS
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
WHERE [State] <> 'ONLINE' AND [State] <> 'RESTORING'
ORDER BY Instance, [Database];

-- Analise de databases em RESTORING
-- Verifica se pertencem a um AG e qual o modo de sincronizacao
PRINT ''
PRINT '--- 1.2.1 ANALISE DE DATABASES EM RESTORING ---'

-- Resumo: RESTORING em AG vs fora de AG
SELECT
    'RESTORING - Resumo' AS Info,
    SUM(CASE WHEN ag.AgName IS NOT NULL THEN 1 ELSE 0 END) AS Em_AlwaysOn_AG,
    SUM(CASE WHEN ag.AgName IS NULL THEN 1 ELSE 0 END) AS Provavél_Mirroring
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG AS db WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_ALWAYSON_STATUS_STG AS ag WITH (NOLOCK)
    ON ag.Instance = db.Instance
WHERE db.[State] = 'RESTORING';

-- Detalhes dos RESTORING em AG (normal - replicas secundarias)
-- Nota: RESTORING em replica secundaria e comportamento normal do AlwaysOn
SELECT
    'RESTORING em AG (Normal)' AS Info,
    db.Instance,
    db.[Database],
    ag.AgName,
    ag.Pri_Synch_State,
    ag.Sec_Synch_State,
    CASE
        WHEN ag.Sec_Synch_State = 'SYNCHRONIZED' THEN 'Sync OK'
        WHEN ag.Sec_Synch_State = 'SYNCHRONIZING' THEN 'Sincronizando'
        WHEN ag.Sec_Synch_State = 'NOT SYNCHRONIZING' THEN 'NAO Sincronizando - VERIFICAR'
        ELSE ISNULL(ag.Sec_Synch_State, 'N/A')
    END AS Status_Replica,
    ag.Problem_Reason,
    db.Update_TS
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG AS db WITH (NOLOCK)
INNER JOIN dbo.KPI_MSSQL_ALWAYSON_STATUS_STG AS ag WITH (NOLOCK)
    ON ag.Instance = db.Instance
WHERE db.[State] = 'RESTORING'
ORDER BY ag.AgName, db.Instance, db.[Database];

-- ALERTA: RESTORING fora de AG (possivel problema!)
SELECT
    'RESTORING sem AG - VERIFICAR!' AS Info,
    db.Instance,
    db.[Database],
    db.[State],
    db.Update_TS
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG AS db WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_ALWAYSON_STATUS_STG AS ag WITH (NOLOCK)
    ON ag.Instance = db.Instance
WHERE db.[State] = 'RESTORING'
  AND ag.AgName IS NULL
ORDER BY db.Instance, db.[Database];

-- ----------------------------------------------------------------------------
-- 1.3 CARD: SERVER OFFLINE
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 1.3 SERVER OFFLINE ---'

SELECT
    'SERVER OFFLINE' AS Card,
    COUNT(*) AS Servers_Offline
FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK);

SELECT * FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK);

-- ----------------------------------------------------------------------------
-- 1.4 CARD: SERVICE STATUS (Servicos SQL Parados)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 1.4 SERVICE STATUS ---'

SELECT
    'SERVICE STATUS' AS Card,
    COUNT(*) AS Instances_Com_Servicos_Parados,
    SUM(Services_Down_Count) AS Total_Servicos_Parados
FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0;

SELECT * FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0;

-- ============================================================================
-- SECAO 2: PERFORMANCE / BLOQUEIOS
-- ============================================================================

PRINT ''
PRINT '>>> SECAO 2: PERFORMANCE / BLOQUEIOS'
PRINT ''

-- ----------------------------------------------------------------------------
-- 2.1 CARD: BLOCKED SESSIONS (Sessoes Bloqueadas)
-- ----------------------------------------------------------------------------
PRINT '--- 2.1 BLOCKED SESSIONS ---'

SELECT
    'BLOCKED SESSIONS' AS Card,
    COUNT(*) AS Instances_Com_Bloqueios,
    SUM(Cnt) AS Total_Sessoes_Bloqueadas
FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0;

SELECT * FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0;

-- ----------------------------------------------------------------------------
-- 2.2 CARD: BLOCKED USERS (Usuarios Bloqueados - ultimos 15 min)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 2.2 BLOCKED USERS ---'

SELECT
    'BLOCKED USERS (15 min)' AS Card,
    COUNT(DISTINCT [User]) AS Usuarios_Bloqueados
FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
  AND Update_TS >= DATEADD(MINUTE, -15, GETDATE());

SELECT * FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
  AND Update_TS >= DATEADD(MINUTE, -15, GETDATE());

-- ----------------------------------------------------------------------------
-- 2.3 CARD: DEADLOCKS
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 2.3 DEADLOCKS ---'

SELECT
    'DEADLOCKS' AS Card,
    COUNT(*) AS Instances_Com_Deadlocks,
    SUM(Deadlock_Count) AS Total_Deadlocks
FROM dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Deadlock_Count > 0;

SELECT * FROM dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Deadlock_Count > 0;

-- ----------------------------------------------------------------------------
-- 2.4 CARD: LONG LOCKS (Locks de Longa Duracao)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 2.4 LONG LOCKS ---'

SELECT
    'LONG LOCKS' AS Card,
    COUNT(*) AS Instances_Com_Long_Locks,
    SUM(Cnt) AS Total_Long_Locks,
    SUM(CASE WHEN [State] = 'CRITICAL' THEN 1 ELSE 0 END) AS Critical,
    SUM(CASE WHEN [State] = 'WARNING' THEN 1 ELSE 0 END) AS Warning
FROM dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0;

SELECT * FROM dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0;

-- ----------------------------------------------------------------------------
-- 2.5 CARD: PROCESSES (Processos em Warning/Critical)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 2.5 PROCESSES ---'

SELECT
    'PROCESSES' AS Card,
    SUM(CASE WHEN [State] = 'CRITICAL' THEN 1 ELSE 0 END) AS Critical,
    SUM(CASE WHEN [State] = 'WARNING' THEN 1 ELSE 0 END) AS Warning
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
WHERE [State] IN ('WARNING', 'CRITICAL');

SELECT * FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
WHERE [State] IN ('WARNING', 'CRITICAL');

-- ============================================================================
-- SECAO 3: ESPACO / CAPACIDADE
-- ============================================================================

PRINT ''
PRINT '>>> SECAO 3: ESPACO / CAPACIDADE'
PRINT ''

-- ----------------------------------------------------------------------------
-- 3.1 CARD: DISK FILE SYSTEM (Uso de Disco)
-- Thresholds: Critical <= 5% livre, Warning <= 10% livre
-- ----------------------------------------------------------------------------
PRINT '--- 3.1 DISK FILE SYSTEM ---'

SELECT
    'DISK FILE SYSTEM' AS Card,
    COUNT(*) AS Instances_Com_Alertas,
    SUM(Critical) AS Total_Discos_Critical,
    SUM(Warning) AS Total_Discos_Warning
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0;

SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
ORDER BY Critical DESC, Warning DESC;

-- ----------------------------------------------------------------------------
-- 3.2 CARD: TRANSACTION LOGS (Uso de Transaction Log)
-- Thresholds: Critical >= 90%, Warning >= 75%
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 3.2 TRANSACTION LOGS ---'

SELECT
    'TRANSACTION LOGS' AS Card,
    COUNT(*) AS Instances_Com_Alertas,
    SUM(Critical) AS Total_TLogs_Critical,
    SUM(Warning) AS Total_TLogs_Warning
FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0;

SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
ORDER BY Critical DESC, Warning DESC;

-- ----------------------------------------------------------------------------
-- 3.3 CARD: FILEGROUP USAGE (Uso de FileGroups)
-- Thresholds: Critical >= 98%, Warning >= 95%, Attention >= 90%
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '--- 3.3 FILEGROUP USAGE ---'

-- Resumo por nivel de alerta
SELECT
    'FILEGROUP USAGE' AS Card,
    COUNT(DISTINCT CASE WHEN Critical > 0 THEN Instance END) AS Instancias_Critical,
    COUNT(DISTINCT CASE WHEN Warning > 0 THEN Instance END) AS Instancias_Warning,
    COUNT(DISTINCT CASE WHEN Attention > 0 THEN Instance END) AS Instancias_Attention,
    SUM(Critical) AS Total_FGs_Critical,
    SUM(Warning) AS Total_FGs_Warning,
    SUM(Attention) AS Total_FGs_Attention
FROM (
    SELECT
        f.Instance,
        SUM(CASE WHEN f.Percent_Used >= 90 AND f.Percent_Used < 95 THEN 1 ELSE 0 END) AS Attention,
        SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning,
        SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical
    FROM dbo.KPI_MSSQL_FG_USAGE_STG AS f WITH (NOLOCK)
    GROUP BY f.Instance
    HAVING SUM(CASE WHEN f.Percent_Used >= 90 THEN 1 ELSE 0 END) > 0
) AS subq;

-- Detalhes por instancia
SELECT
    f.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    SUM(CASE WHEN f.Percent_Used >= 90 AND f.Percent_Used < 95 THEN 1 ELSE 0 END) AS Attention,
    SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical
FROM dbo.KPI_MSSQL_FG_USAGE_STG AS f WITH (NOLOCK)
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS AS e ON e.Instance = f.Instance
GROUP BY f.Instance, e.Env
HAVING SUM(CASE WHEN f.Percent_Used >= 90 THEN 1 ELSE 0 END) > 0
ORDER BY
    SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) DESC,
    SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) DESC;

-- ============================================================================
-- SECAO 4: ALTA DISPONIBILIDADE
-- ============================================================================

PRINT ''
PRINT '>>> SECAO 4: ALTA DISPONIBILIDADE'
PRINT ''

-- ----------------------------------------------------------------------------
-- 4.1 CARD: ALWAYS ON (Availability Groups)
-- CORRIGIDO: Exclui strings vazias para evitar falsos positivos
-- ----------------------------------------------------------------------------
PRINT '--- 4.1 ALWAYS ON ---'

-- Contagem de AGs com problema (query corrigida)
SELECT
    'ALWAYS ON' AS Card,
    COUNT(DISTINCT AgName) AS AGs_Unhealthy
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
WHERE (
    -- Health nao saudavel - EXCLUI strings vazias
    (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
    OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
    -- State nao sincronizado - EXCLUI strings vazias e UNKNOWN
    OR (Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Pri_Synch_State IS NOT NULL)
    OR (Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Sec_Synch_State IS NOT NULL)
    -- Suspenso
    OR Pri_Is_Suspended = 1
    OR Sec_Is_Suspended = 1
);

-- Detalhes via view agregada
SELECT * FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Unhealthy > 0;

-- Total de AGs monitorados
SELECT
    'Total AGs Monitorados' AS Info,
    COUNT(DISTINCT AgName) AS Total_AGs
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK);

-- ============================================================================
-- SECAO 5: BACKUP
-- ============================================================================

PRINT ''
PRINT '>>> SECAO 5: BACKUP'
PRINT ''

-- ----------------------------------------------------------------------------
-- 5.1 CARD: BACKUP STATUS
-- Thresholds:
--   FULL: Failed > 168h (7 dias), Delayed > 120h (5 dias)
--   DIFF: Failed > 30h, Delayed > 24h
--   LOG:  Failed > 2h, Delayed > 1h
-- ----------------------------------------------------------------------------
PRINT '--- 5.1 BACKUP STATUS ---'

-- Resumo por tipo de backup
SELECT
    'BACKUP STATUS' AS Card,
    Backup_Type,
    COUNT(*) AS Total,
    SUM(CASE
        WHEN Backup_Type IN ('FULL', 'D') AND Hours_Since_Backup > 168 THEN 1
        WHEN Backup_Type IN ('DIFF', 'I') AND Hours_Since_Backup > 30 THEN 1
        WHEN Backup_Type IN ('LOG', 'L') AND Hours_Since_Backup > 2 THEN 1
        ELSE 0
    END) AS Failed,
    SUM(CASE
        WHEN Backup_Type IN ('FULL', 'D') AND Hours_Since_Backup > 120 AND Hours_Since_Backup <= 168 THEN 1
        WHEN Backup_Type IN ('DIFF', 'I') AND Hours_Since_Backup > 24 AND Hours_Since_Backup <= 30 THEN 1
        WHEN Backup_Type IN ('LOG', 'L') AND Hours_Since_Backup > 1 AND Hours_Since_Backup <= 2 THEN 1
        ELSE 0
    END) AS Delayed
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
GROUP BY Backup_Type;

-- Backups FULL com problema (> 7 dias)
SELECT
    'Backups FULL Atrasados (>7 dias)' AS Info,
    Instance,
    [Database],
    Backup_Type,
    Hours_Since_Backup,
    Last_Backup_Date,
    Update_TS
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
WHERE Backup_Type IN ('FULL', 'D')
  AND Hours_Since_Backup > 168
ORDER BY Hours_Since_Backup DESC;

-- ============================================================================
-- SECAO 6: RESUMO CONSOLIDADO
-- ============================================================================

PRINT ''
PRINT '>>> SECAO 6: RESUMO CONSOLIDADO'
PRINT ''

-- ----------------------------------------------------------------------------
-- 6.1 RESUMO DE TODOS OS CARDS EM UMA UNICA TABELA
-- ----------------------------------------------------------------------------
PRINT '--- 6.1 RESUMO CONSOLIDADO ---'

SELECT 'Instances OK' AS Card, CAST(COUNT(DISTINCT Instance) AS VARCHAR(20)) AS Valor FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Is_Available = 1
UNION ALL
SELECT 'Instances Off', CAST(COUNT(DISTINCT Instance) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Is_Available = 0
UNION ALL
SELECT 'Databases Online', CAST(SUM(CASE WHEN [State] = 'ONLINE' THEN 1 ELSE 0 END) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
UNION ALL
SELECT 'Databases Problem', CAST(SUM(CASE WHEN [State] <> 'ONLINE' AND [State] <> 'RESTORING' THEN 1 ELSE 0 END) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
UNION ALL
SELECT 'Servers Offline', CAST(COUNT(*) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK)
UNION ALL
SELECT 'Services Down', CAST(ISNULL(SUM(Services_Down_Count), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK) WHERE Services_Down_Count > 0
UNION ALL
SELECT 'Blocked Sessions', CAST(ISNULL(SUM(Cnt), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK) WHERE Cnt > 0
UNION ALL
SELECT 'Blocked Users (15min)', CAST(COUNT(DISTINCT [User]) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) WHERE Blocked_Count > 0 AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())
UNION ALL
SELECT 'Deadlocks', CAST(ISNULL(SUM(Deadlock_Count), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW WITH (NOLOCK) WHERE Deadlock_Count > 0
UNION ALL
SELECT 'Long Locks', CAST(ISNULL(SUM(Cnt), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK) WHERE Cnt > 0
UNION ALL
SELECT 'Disk Critical', CAST(ISNULL(SUM(Critical), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
UNION ALL
SELECT 'Disk Warning', CAST(ISNULL(SUM(Warning), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
UNION ALL
SELECT 'TLog Critical', CAST(ISNULL(SUM(Critical), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
UNION ALL
SELECT 'TLog Warning', CAST(ISNULL(SUM(Warning), 0) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
UNION ALL
SELECT 'FileGroup Critical (Inst)', CAST(COUNT(DISTINCT CASE WHEN c > 0 THEN i END) AS VARCHAR(20)) FROM (SELECT Instance AS i, SUM(CASE WHEN Percent_Used >= 98 THEN 1 ELSE 0 END) AS c FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) GROUP BY Instance) AS x
UNION ALL
SELECT 'FileGroup Warning (Inst)', CAST(COUNT(DISTINCT CASE WHEN w > 0 THEN i END) AS VARCHAR(20)) FROM (SELECT Instance AS i, SUM(CASE WHEN Percent_Used >= 95 AND Percent_Used < 98 THEN 1 ELSE 0 END) AS w FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) GROUP BY Instance) AS x
UNION ALL
SELECT 'AlwaysOn Unhealthy', CAST(COUNT(DISTINCT AgName) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE ((Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '') OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '') OR (Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Pri_Synch_State IS NOT NULL) OR (Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Sec_Synch_State IS NOT NULL) OR Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1)
UNION ALL
SELECT 'Backup FULL Failed (>7d)', CAST(COUNT(*) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK) WHERE Backup_Type IN ('FULL', 'D') AND Hours_Since_Backup > 168;

-- ============================================================================
-- SECAO 7: VERIFICACAO DE FRESCOR DOS DADOS
-- ============================================================================

PRINT ''
PRINT '>>> SECAO 7: VERIFICACAO DE FRESCOR DOS DADOS'
PRINT ''

-- ----------------------------------------------------------------------------
-- 7.1 Ultima atualizacao de cada tabela STG
-- ----------------------------------------------------------------------------
PRINT '--- 7.1 FRESCOR DOS DADOS ---'

SELECT 'KPI_MSSQL_INST_AVAILABILITY_STG' AS Tabela, MAX(Update_TS) AS Ultima_Atualizacao, DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) AS Minutos_Atras FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
UNION ALL
SELECT 'KPI_MSSQL_DB_AVAILABILITY_STG', MAX(Update_TS), DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
UNION ALL
SELECT 'KPI_MSSQL_FG_USAGE_STG', MAX(Update_TS), DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK)
UNION ALL
SELECT 'KPI_MSSQL_ALWAYSON_STATUS_STG', MAX(Update_TS), DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
UNION ALL
SELECT 'KPI_MSSQL_BACKUPS_STG', MAX(Update_TS), DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
UNION ALL
SELECT 'KPI_MSSQL_BLOCKED_USERS_STG', MAX(Update_TS), DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
ORDER BY Minutos_Atras;

-- ============================================================================
-- JANELAS DE FRESCOR APLICADAS PELO CODIGO PYTHON
-- ============================================================================
-- services:   15 min  - Services e Instance Availability
-- real_time:   5 min  - Blocked Sessions, Deadlocks, Long Locks, AlwaysOn
-- capacity:   60 min  - Filegroups, Disk, TLogs
-- backup:    1440 min (24h) - Backups
-- ============================================================================

PRINT ''
PRINT '============================================================================'
PRINT 'FIM DA VALIDACAO'
PRINT '============================================================================'
GO
