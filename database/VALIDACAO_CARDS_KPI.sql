-- ============================================================================
-- VALIDACAO DOS CARDS DE KPI DO DASHBOARD - WatcherDB Intelligence
-- ============================================================================
-- Execute estas queries no database WatcherDB_Intelligence para validar
-- os valores exibidos em cada card do dashboard
-- ============================================================================

USE WatcherDB_Intelligence
GO

PRINT '============================================================================'
PRINT 'SECAO: DISPONIBILIDADE'
PRINT '============================================================================'

-- ----------------------------------------------------------------------------
-- CARD: DB Not Availability (Unavailable Count) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: DB Not Availability'
SELECT COUNT(*) AS [DB_Not_Availability]
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK)
WHERE [State] <> 'RESTORING'
  AND [State] <> 'ONLINE'

-- ----------------------------------------------------------------------------
-- CARD: DB Availability (Total Count) - Esperado: 1.98K (1980)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: DB Availability (Total)'
SELECT COUNT(DISTINCT Instance + '|' + [Database]) AS [DB_Availability_Total]
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)

-- ----------------------------------------------------------------------------
-- CARD: Instances OK (Available Count) - Esperado: 80
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Instances OK'
SELECT COUNT(DISTINCT Instance) AS [Instances_OK]
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 1

-- ----------------------------------------------------------------------------
-- CARD: Instances Off (Offline Count) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Instances Off'
SELECT COUNT(DISTINCT Instance) AS [Instances_Off]
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 0

-- ----------------------------------------------------------------------------
-- CARD: SQL Services Down (Services Stopped) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: SQL Services Down'
SELECT ISNULL(SUM(Services_Down_Count), 0) AS [SQL_Services_Down]
FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0

PRINT ''
PRINT '============================================================================'
PRINT 'SECAO: PERFORMANCE'
PRINT '============================================================================'

-- ----------------------------------------------------------------------------
-- CARD: Blocked Sessions (Session Count) - Esperado: 4
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Blocked Sessions'
SELECT COUNT(*) AS [Instancias_Com_Bloqueios],
       ISNULL(SUM(Cnt), 0) AS [Total_Sessoes_Bloqueadas]
FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0

-- ----------------------------------------------------------------------------
-- CARD: Blocked Users (User Count) - Esperado: 4
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Blocked Users (ultimos 15 min)'
SELECT COUNT(DISTINCT [User]) AS [Blocked_Users]
FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
  AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())

-- Sem filtro de tempo (para comparacao)
PRINT '>> CARD: Blocked Users (sem filtro de tempo)'
SELECT COUNT(DISTINCT [User]) AS [Blocked_Users_Total]
FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0

-- ----------------------------------------------------------------------------
-- CARD: Processes Alarm (Processes Alarm Count) - Esperado: 5
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Processes Alarm'
SELECT COUNT(*) AS [Processes_Alarm]
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
WHERE [State] IN ('WARNING', 'CRITICAL')

-- ----------------------------------------------------------------------------
-- CARD: CPU Critico (CPU >= 95% sustentado) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: CPU Critico'
-- Nota: Verificar se existe tabela KPI_MSSQL_CPU_USAGE ou similar
SELECT 'Verificar tabela de CPU - pode nao existir ainda' AS [Nota]

-- ----------------------------------------------------------------------------
-- CARD: Memoria Critico (Mem >= 95% + Page Fault) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Memoria Critico'
-- Nota: Verificar se existe tabela KPI_MSSQL_MEMORY_USAGE ou similar
SELECT 'Verificar tabela de Memoria - pode nao existir ainda' AS [Nota]

PRINT ''
PRINT '============================================================================'
PRINT 'SECAO: ESPACO'
PRINT '============================================================================'

-- ----------------------------------------------------------------------------
-- CARD: Transaction Logs Critical - Esperado: 37
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Transaction Logs Critical'
SELECT COUNT(*) AS [Instancias_TLog_Critical],
       ISNULL(SUM(Critical), 0) AS [Total_TLogs_Critical]
FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0

-- ----------------------------------------------------------------------------
-- CARD: Transaction Logs Warning - Esperado: 12
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Transaction Logs Warning'
SELECT COUNT(*) AS [Instancias_TLog_Warning],
       ISNULL(SUM(Warning), 0) AS [Total_TLogs_Warning]
FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Warning > 0 AND Critical = 0

-- Total Warning (incluindo os que tambem sao critical)
SELECT ISNULL(SUM(Warning), 0) AS [Total_TLogs_Warning_Todos]
FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Warning > 0

-- ----------------------------------------------------------------------------
-- CARD: Disk File System Critical - Esperado: 8
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Disk File System Critical'
SELECT COUNT(*) AS [Instancias_Disk_Critical],
       ISNULL(SUM(Critical), 0) AS [Total_Disks_Critical]
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0

-- ----------------------------------------------------------------------------
-- CARD: Disk File System Warning - Esperado: 63
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Disk File System Warning'
SELECT COUNT(*) AS [Instancias_Disk_Warning],
       ISNULL(SUM(Warning), 0) AS [Total_Disks_Warning]
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Warning > 0

-- ----------------------------------------------------------------------------
-- CARD: FileGroups Usage Critical - Esperado: 59 instancias, 278 FGs
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: FileGroups Usage Critical (>= 98%)'
SELECT
    COUNT(DISTINCT Instance) AS [Instancias_FG_Critical],
    SUM(Critical) AS [Total_FileGroups_Critical]
FROM (
    SELECT
        f.Instance,
        SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical
    FROM dbo.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
    GROUP BY f.Instance
    HAVING SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) > 0
) AS subq

-- ----------------------------------------------------------------------------
-- CARD: FileGroups Usage Warning - Esperado: 38 instancias, 103 FGs
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: FileGroups Usage Warning (>= 95% e < 98%)'
SELECT
    COUNT(DISTINCT Instance) AS [Instancias_FG_Warning],
    SUM(Warning) AS [Total_FileGroups_Warning]
FROM (
    SELECT
        f.Instance,
        SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning
    FROM dbo.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
    GROUP BY f.Instance
    HAVING SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) > 0
) AS subq

-- ----------------------------------------------------------------------------
-- CARD: Backup Failed (Failed Count) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Backup Failed'
-- FULL: > 168h (7 dias), DIFF: > 30h, LOG: > 2h
SELECT
    COUNT(CASE WHEN Backup_Type IN ('FULL', 'D') AND Hours_Since_Backup > 168 THEN 1 END) AS [Backup_FULL_Failed],
    COUNT(CASE WHEN Backup_Type IN ('DIFF', 'I') AND Hours_Since_Backup > 30 THEN 1 END) AS [Backup_DIFF_Failed],
    COUNT(CASE WHEN Backup_Type IN ('LOG', 'L') AND Hours_Since_Backup > 2 THEN 1 END) AS [Backup_LOG_Failed]
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)

-- Total Failed
SELECT COUNT(*) AS [Total_Backup_Failed]
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
WHERE (Backup_Type IN ('FULL', 'D') AND Hours_Since_Backup > 168)
   OR (Backup_Type IN ('DIFF', 'I') AND Hours_Since_Backup > 30)
   OR (Backup_Type IN ('LOG', 'L') AND Hours_Since_Backup > 2)

-- ----------------------------------------------------------------------------
-- CARD: Backup Delayed (Delayed Count) - Esperado: 0
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Backup Delayed'
-- FULL: 120-168h, DIFF: 24-30h, LOG: 1-2h
SELECT
    COUNT(CASE WHEN Backup_Type IN ('FULL', 'D') AND Hours_Since_Backup > 120 AND Hours_Since_Backup <= 168 THEN 1 END) AS [Backup_FULL_Delayed],
    COUNT(CASE WHEN Backup_Type IN ('DIFF', 'I') AND Hours_Since_Backup > 24 AND Hours_Since_Backup <= 30 THEN 1 END) AS [Backup_DIFF_Delayed],
    COUNT(CASE WHEN Backup_Type IN ('LOG', 'L') AND Hours_Since_Backup > 1 AND Hours_Since_Backup <= 2 THEN 1 END) AS [Backup_LOG_Delayed]
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)

-- ----------------------------------------------------------------------------
-- CARD: TempDB Disk Critical - Esperado: 5
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: TempDB Disk Critical'
-- Usa a mesma view de Disk Usage
SELECT COUNT(*) AS [TempDB_Disk_Critical]
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0

-- ----------------------------------------------------------------------------
-- CARD: TempDB Disk Warning - Esperado: 21
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: TempDB Disk Warning'
SELECT COUNT(*) AS [TempDB_Disk_Warning]
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Warning > 0 AND Critical = 0

PRINT ''
PRINT '============================================================================'
PRINT 'SECAO: ALTA DISPONIBILIDADE'
PRINT '============================================================================'

-- ----------------------------------------------------------------------------
-- CARD: Always On UnHealthy - Esperado: 0 (apos correcao)
-- ----------------------------------------------------------------------------
PRINT ''
PRINT '>> CARD: Always On UnHealthy (CORRIGIDO - exclui strings vazias)'
SELECT COUNT(DISTINCT AgName) AS [Always_On_UnHealthy]
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
WHERE (
    -- Health nao saudavel (exclui strings vazias)
    (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
    OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
    -- State nao sincronizado (exclui strings vazias)
    OR (Pri_Synch_State <> 'SYNCHRONIZED' AND Pri_Synch_State IS NOT NULL AND Pri_Synch_State <> 'UNKNOWN' AND Pri_Synch_State <> '')
    OR (Sec_Synch_State <> 'SYNCHRONIZED' AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State <> 'UNKNOWN' AND Sec_Synch_State <> '')
    -- Suspenso
    OR Pri_Is_Suspended = 1
    OR Sec_Is_Suspended = 1
)

-- Query ANTIGA (para comparacao - pode mostrar falsos positivos)
PRINT ''
PRINT '>> CARD: Always On UnHealthy (ANTIGA - pode ter falsos positivos)'
SELECT COUNT(DISTINCT AgName) AS [Always_On_UnHealthy_OLD]
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
WHERE (
    (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL)
    OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL)
    OR (Pri_Synch_State <> 'SYNCHRONIZED' AND Pri_Synch_State IS NOT NULL AND Pri_Synch_State <> 'UNKNOWN')
    OR (Sec_Synch_State <> 'SYNCHRONIZED' AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State <> 'UNKNOWN')
    OR Pri_Is_Suspended = 1
    OR Sec_Is_Suspended = 1
)

-- Ver dados brutos para debug
PRINT ''
PRINT '>> DEBUG: Dados AlwaysOn STG (ultimos 50 registros)'
SELECT TOP 50
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

PRINT ''
PRINT '============================================================================'
PRINT 'RESUMO CONSOLIDADO - COMPARAR COM DASHBOARD'
PRINT '============================================================================'

SELECT 'DISPONIBILIDADE' AS Secao, 'DB Not Availability' AS Card,
       (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK) WHERE [State] <> 'RESTORING' AND [State] <> 'ONLINE') AS Valor
UNION ALL
SELECT 'DISPONIBILIDADE', 'DB Availability (Total)',
       (SELECT COUNT(DISTINCT Instance + '|' + [Database]) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK))
UNION ALL
SELECT 'DISPONIBILIDADE', 'Instances OK',
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Is_Available = 1)
UNION ALL
SELECT 'DISPONIBILIDADE', 'Instances Off',
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Is_Available = 0)
UNION ALL
SELECT 'DISPONIBILIDADE', 'SQL Services Down',
       (SELECT ISNULL(SUM(Services_Down_Count), 0) FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK) WHERE Services_Down_Count > 0)
UNION ALL
SELECT 'PERFORMANCE', 'Blocked Sessions',
       (SELECT COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK) WHERE Cnt > 0)
UNION ALL
SELECT 'PERFORMANCE', 'Blocked Users',
       (SELECT COUNT(DISTINCT [User]) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) WHERE Blocked_Count > 0)
UNION ALL
SELECT 'PERFORMANCE', 'Processes Alarm',
       (SELECT COUNT(*) FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK) WHERE [State] IN ('WARNING', 'CRITICAL'))
UNION ALL
SELECT 'ESPACO', 'Transaction Logs Critical',
       (SELECT ISNULL(SUM(Critical), 0) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK))
UNION ALL
SELECT 'ESPACO', 'Transaction Logs Warning',
       (SELECT ISNULL(SUM(Warning), 0) FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK))
UNION ALL
SELECT 'ESPACO', 'Disk File System Critical',
       (SELECT ISNULL(SUM(Critical), 0) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK))
UNION ALL
SELECT 'ESPACO', 'Disk File System Warning',
       (SELECT ISNULL(SUM(Warning), 0) FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK))
UNION ALL
SELECT 'ESPACO', 'FileGroups Critical (instancias)',
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) WHERE Percent_Used >= 98)
UNION ALL
SELECT 'ESPACO', 'FileGroups Warning (instancias)',
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) WHERE Percent_Used >= 95 AND Percent_Used < 98)
UNION ALL
SELECT 'ALTA DISPONIBILIDADE', 'Always On UnHealthy (CORRIGIDO)',
       (SELECT COUNT(DISTINCT AgName) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
        WHERE (
            (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
            OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
            OR (Pri_Synch_State <> 'SYNCHRONIZED' AND Pri_Synch_State IS NOT NULL AND Pri_Synch_State <> 'UNKNOWN' AND Pri_Synch_State <> '')
            OR (Sec_Synch_State <> 'SYNCHRONIZED' AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State <> 'UNKNOWN' AND Sec_Synch_State <> '')
            OR Pri_Is_Suspended = 1
            OR Sec_Is_Suspended = 1
        ))
ORDER BY Secao, Card

PRINT ''
PRINT '============================================================================'
PRINT 'FIM DA VALIDACAO'
PRINT '============================================================================'
