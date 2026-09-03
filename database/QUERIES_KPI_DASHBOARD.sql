-- ============================================================================
-- QUERIES DOS CARDS DE KPI DO DASHBOARD - WatcherDB Intelligence
-- ============================================================================
-- Use estas queries para validar os dados exibidos nos cards do dashboard
-- Database: WatcherDB_Intelligence
-- Schema: dbo
-- ============================================================================

-- ============================================================================
-- 1. DB AVAILABILITY (Databases Online/Offline)
-- ============================================================================

-- 1.1 Card: DB Not Availability (Databases com problema)
-- Mostra databases que NAO estao ONLINE (exceto RESTORING que e normal em mirroring)
SELECT COUNT(*) AS "DBs com problema"
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW WITH (NOLOCK);

-- Nota: O codigo aplica filtro de frescor de 24 horas (1440 min)

-- 1.2 Card: Total de Databases
SELECT COUNT(*) AS "Total databases"
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK);

-- 1.3 Card: Databases OK
SELECT 
    SUM(TotalCnt) AS Total_Databases
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WITH (NOLOCK);

-- 1.4 Databases por Ambiente
SELECT Instance, Env, TotalCnt
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WITH (NOLOCK);

-- ============================================================================
-- 2. INSTANCE AVAILABILITY (Instancias Online/Offline)
-- ============================================================================

-- 2.1 Card: Instances OK
SELECT COUNT(DISTINCT Instance) AS Instancias_OK
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 1

-- 2.2 Card: Instances Off
SELECT COUNT(DISTINCT Instance) AS Instances_Off
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 0

-- 2.3 Instances OK por Ambiente
SELECT
    CASE
        WHEN Instance LIKE '%PRD%' OR Instance LIKE '%PROD%' THEN 'PRD'
        WHEN Instance LIKE '%QLT%' OR Instance LIKE '%QUAL%' THEN 'QLT'
        WHEN Instance LIKE '%TST%' OR Instance LIKE '%TEST%' OR Instance LIKE '%DEV%' THEN 'TST'
        ELSE 'Undefined'
    END as Env,
    COUNT(DISTINCT Instance) as Cnt
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 1
GROUP BY
    CASE
        WHEN Instance LIKE '%PRD%' OR Instance LIKE '%PROD%' THEN 'PRD'
        WHEN Instance LIKE '%QLT%' OR Instance LIKE '%QUAL%' THEN 'QLT'
        WHEN Instance LIKE '%TST%' OR Instance LIKE '%TEST%' OR Instance LIKE '%DEV%' THEN 'TST'
        ELSE 'Undefined'
    END

-- ============================================================================
-- 3. DISK FILE SYSTEM (Uso de Disco)
-- ============================================================================

-- 3.1 Card: Discos com Critical/Warning
-- Critical: disco com <= 5% livre, Warning: disco com <= 10% livre
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
-- Nota: O codigo aplica filtro de frescor de 24 horas (1440 min)

-- 3.2 Contagem total de Critical e Warning
SELECT
    SUM(Critical) AS Total_Critical,
    SUM(Warning) AS Total_Warning
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0

-- ============================================================================
-- 4. TRANSACTION LOGS (Uso de Transaction Log)
-- ============================================================================

-- 4.1 Card: TLogs com Critical/Warning
-- Critical: log >= 90%, Warning: log >= 75%
SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
-- Nota: O codigo aplica filtro de frescor de 24 horas (1440 min)

-- 4.2 Contagem total de Critical e Warning
SELECT
    SUM(Critical) AS Total_Critical,
    SUM(Warning) AS Total_Warning
FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0

-- ============================================================================
-- 5. ALWAYS ON (Availability Groups)
-- ============================================================================

-- 5.1 Card: AGs com problema (Unhealthy)
-- CORRIGIDO: Exclui strings vazias para evitar falsos positivos
SELECT COUNT(DISTINCT AgName) AS Always_On_UnHealthy
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
WHERE (
    -- Health nao saudavel (primaria ou secundaria) - exclui strings vazias
    (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
    OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
    -- State nao sincronizado (primaria ou secundaria) - exclui strings vazias
    OR (Pri_Synch_State <> 'SYNCHRONIZED' AND Pri_Synch_State IS NOT NULL AND Pri_Synch_State <> 'UNKNOWN' AND Pri_Synch_State <> '')
    OR (Sec_Synch_State <> 'SYNCHRONIZED' AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State <> 'UNKNOWN' AND Sec_Synch_State <> '')
    -- Suspenso (primaria ou secundaria)
    OR Pri_Is_Suspended = 1
    OR Sec_Is_Suspended = 1
)

-- 5.2 Modal: Detalhes dos AGs com problema
SELECT * FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Unhealthy > 0
-- Nota: O codigo aplica filtro de frescor de 5 minutos

-- 5.3 Debug: Ver dados brutos da STG
SELECT TOP 100
    AgName,
    Pri_Synch_Health,
    Sec_Synch_Health,
    Pri_Synch_State,
    Sec_Synch_State,
    Pri_Is_Suspended,
    Sec_Is_Suspended,
    Update_TS
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
ORDER BY Update_TS DESC

-- ============================================================================
-- 6. FILEGROUP USAGE (Uso de FileGroups)
-- ============================================================================

-- 6.1 Card: FileGroups por nivel de alerta
-- Thresholds: Critical >= 98%, Warning >= 95%, Attention >= 90%
SELECT
    f.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    SUM(CASE WHEN f.Percent_Used >= 90 AND f.Percent_Used < 95 THEN 1 ELSE 0 END) AS Attention,
    SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical
FROM dbo.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = f.Instance
GROUP BY f.Instance, e.Env
HAVING SUM(CASE WHEN f.Percent_Used >= 90 THEN 1 ELSE 0 END) > 0

-- 6.2 Totais de Instancias com alertas
SELECT
    COUNT(DISTINCT CASE WHEN Critical > 0 THEN Instance END) AS Instancias_Critical,
    COUNT(DISTINCT CASE WHEN Warning > 0 THEN Instance END) AS Instancias_Warning,
    COUNT(DISTINCT CASE WHEN Attention > 0 THEN Instance END) AS Instancias_Attention,
    SUM(Critical) AS Total_FileGroups_Critical,
    SUM(Warning) AS Total_FileGroups_Warning,
    SUM(Attention) AS Total_FileGroups_Attention
FROM (
    SELECT
        f.Instance,
        SUM(CASE WHEN f.Percent_Used >= 90 AND f.Percent_Used < 95 THEN 1 ELSE 0 END) AS Attention,
        SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning,
        SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical
    FROM dbo.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
    GROUP BY f.Instance
    HAVING SUM(CASE WHEN f.Percent_Used >= 90 THEN 1 ELSE 0 END) > 0
) AS subq

-- 6.3 Detalhes de uma instancia especifica (exemplo)
SELECT *
FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK)
WHERE Instance = 'SQLHDSQLT105_I05'
ORDER BY Percent_Used DESC

-- ============================================================================
-- 7. BLOCKED SESSIONS (Sessoes Bloqueadas)
-- ============================================================================

-- 7.1 Card: Instancias com sessoes bloqueadas
SELECT * FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0
-- Nota: O codigo aplica filtro de frescor de 5 minutos

-- 7.2 Contagem de instancias com bloqueios
SELECT COUNT(*) AS Instancias_Com_Bloqueios
FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0

-- ============================================================================
-- 8. BLOCKED USERS (Usuarios Bloqueados)
-- ============================================================================

-- 8.1 Card: Usuarios bloqueados (ultimos 15 minutos)
SELECT COUNT(DISTINCT [User]) AS Blocked_Users
FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
    AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())

-- 8.2 Detalhes dos usuarios bloqueados
SELECT * FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
    AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())

-- ============================================================================
-- 9. BACKUP STATUS
-- ============================================================================

-- 9.1 Card: Backups atrasados/falhos
-- Thresholds por tipo:
-- FULL: Failed > 168h (7 dias), Delayed > 120h (5 dias)
-- DIFF: Failed > 30h, Delayed > 24h
-- LOG:  Failed > 2h, Delayed > 1h
SELECT b.*, ISNULL(e.Env, 'Undefined') AS Env
FROM dbo.KPI_MSSQL_BACKUPS_STG AS b WITH (NOLOCK)
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
    ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(b.Instance)))
-- Nota: O codigo aplica filtro de frescor de 24 horas (1440 min)

-- 9.2 Backups FULL atrasados (exemplo)
SELECT *
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
WHERE Backup_Type IN ('FULL', 'D')
  AND Hours_Since_Backup > 168  -- > 7 dias

-- ============================================================================
-- 10. DEADLOCKS
-- ============================================================================

-- 10.1 Card: Deadlocks recentes
SELECT * FROM dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Deadlock_Count > 0
-- Nota: O codigo aplica filtro de frescor de 5 minutos

-- 10.2 Total de deadlocks
SELECT SUM(Deadlock_Count) AS Total_Deadlocks
FROM dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Deadlock_Count > 0

-- ============================================================================
-- 11. SERVICE STATUS (Servicos SQL)
-- ============================================================================

-- 11.1 Card: Servicos parados
SELECT * FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0
-- Nota: O codigo aplica filtro de frescor de 15 minutos

-- 11.2 Total de servicos parados
SELECT SUM(Services_Down_Count) AS Total_Services_Down
FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0

-- ============================================================================
-- 12. LONG LOCKS (Locks de longa duracao)
-- ============================================================================

-- 12.1 Card: Locks longos
-- Critical: > 600 segundos (10 min), Warning: 60-600 segundos
SELECT * FROM dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0
-- Nota: O codigo aplica filtro de frescor de 5 minutos

-- 12.2 Separar Critical e Warning
SELECT
    COUNT(CASE WHEN Duration_Sec > 600 THEN 1 END) AS Locks_Critical,
    COUNT(CASE WHEN Duration_Sec > 60 AND Duration_Sec <= 600 THEN 1 END) AS Locks_Warning
FROM dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0

-- ============================================================================
-- 13. PROCESSES (Processos em Warning/Critical)
-- ============================================================================

-- 13.1 Card: Processos com alarme
SELECT * FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
WHERE [State] IN ('WARNING', 'CRITICAL')
-- Nota: O codigo aplica filtro de frescor de 24 horas (1440 min)

-- ============================================================================
-- 14. SERVER OFFLINE STATUS
-- ============================================================================

-- 14.1 Card: Servidores offline
SELECT * FROM dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK)

-- ============================================================================
-- 15. TABELAS DE SUPORTE/LOOKUP
-- ============================================================================

-- 15.1 Ambientes das instancias
SELECT * FROM dbo.KPI_MSSQL_INST_ENVS WITH (NOLOCK)

-- 15.2 Verificar quantidade de registros nas tabelas STG
SELECT 'KPI_MSSQL_DB_AVAILABILITY_STG' AS Tabela, COUNT(*) AS Registros FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) UNION ALL
SELECT 'KPI_MSSQL_INST_AVAILABILITY_STG', COUNT(*) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) UNION ALL
SELECT 'KPI_MSSQL_FG_USAGE_STG', COUNT(*) FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) UNION ALL
SELECT 'KPI_MSSQL_ALWAYSON_STATUS_STG', COUNT(*) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) UNION ALL
SELECT 'KPI_MSSQL_BACKUPS_STG', COUNT(*) FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK) UNION ALL
SELECT 'KPI_MSSQL_BLOCKED_SESSIONS_STG', COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK) UNION ALL
SELECT 'KPI_MSSQL_BLOCKED_USERS_STG', COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)

-- ============================================================================
-- FRESHNESS WINDOWS (Janelas de Frescor dos Dados)
-- ============================================================================
-- O codigo Python aplica filtros de frescor para garantir que apenas dados
-- recentes sejam considerados. As janelas sao:
--
-- services:   15 min  - Services e Instance Availability
-- real_time:   5 min  - Blocked Sessions, Deadlocks, Long Locks
-- capacity:   24h     - Filegroups, Disk, DB I/O, capacity metrics
-- backup:     24h     - Backups (coleta menos frequente)
-- alwayson:    5 min  - AlwaysOn status (coleta a cada 1 min)
-- ============================================================================
