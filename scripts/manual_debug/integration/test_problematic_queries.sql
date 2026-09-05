-- ============================================================================
-- Teste das Queries Problemáticas v1.4.8
-- ============================================================================

-- Query 1: BACKUP_HISTORY_ANALYSIS (remover filtro de problema para ver TODOS)
-- ============================================================================
PRINT '=== BACKUP_HISTORY_ANALYSIS (TODOS OS DATABASES) ==='
GO

WITH BackupInfo AS (
    SELECT
        d.name AS DatabaseName,
        d.recovery_model_desc AS RecoveryModel,
        d.state_desc AS DatabaseState,
        (SELECT TOP 1 bs.backup_finish_date
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         ORDER BY bs.backup_finish_date DESC) AS LastFullBackup,
        (SELECT TOP 1 bs.backup_finish_date
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'I'
         ORDER BY bs.backup_finish_date DESC) AS LastDiffBackup,
        (SELECT TOP 1 bs.backup_finish_date
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'L'
         ORDER BY bs.backup_finish_date DESC) AS LastLogBackup
    FROM sys.databases d WITH(NOLOCK)
    WHERE d.database_id > 4
    AND d.state = 0
    AND d.name NOT IN ('tempdb')
)
SELECT TOP 10
    DatabaseName, RecoveryModel, DatabaseState,
    LastFullBackup, LastDiffBackup, LastLogBackup,
    CASE
        WHEN LastFullBackup IS NULL THEN 999
        ELSE DATEDIFF(DAY, LastFullBackup, GETDATE())
    END AS DaysSinceLastFullBackup
FROM BackupInfo
ORDER BY DaysSinceLastFullBackup DESC
GO

-- Query 2: MISSING_INDEX_ANALYSIS (CORRIGIDA - buscar em TODAS as databases)
-- ============================================================================
PRINT '=== MISSING_INDEX_ANALYSIS (TODAS AS DATABASES) ==='
GO

SELECT TOP 20
    DB_NAME(mid.database_id) AS DatabaseName,
    OBJECT_SCHEMA_NAME(mid.object_id, mid.database_id) AS SchemaName,
    OBJECT_NAME(mid.object_id, mid.database_id) AS TableName,
    CAST(migs.avg_total_user_cost AS DECIMAL(12,2)) AS AvgQueryCost,
    CAST(migs.avg_user_impact AS DECIMAL(5,2)) AS AvgImpactPercent,
    migs.user_seeks AS UserSeeks,
    migs.user_scans AS UserScans,
    migs.user_seeks + migs.user_scans AS TotalReads,
    CAST((migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) AS DECIMAL(18,2)) AS ImprovementMeasure,
    mid.equality_columns AS EqualityColumns,
    mid.inequality_columns AS InequalityColumns,
    mid.included_columns AS IncludedColumns
FROM sys.dm_db_missing_index_details mid WITH(NOLOCK)
INNER JOIN sys.dm_db_missing_index_groups mig WITH(NOLOCK)
    ON mid.index_handle = mig.index_handle
INNER JOIN sys.dm_db_missing_index_group_stats migs WITH(NOLOCK)
    ON mig.index_group_handle = migs.group_handle
WHERE DB_NAME(mid.database_id) IS NOT NULL  -- CORRIGIDO: buscar em todas as databases
AND OBJECT_NAME(mid.object_id, mid.database_id) IS NOT NULL
AND (migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) > 1000
ORDER BY (migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) DESC
GO

PRINT '=== FIM DOS TESTES ==='
GO
