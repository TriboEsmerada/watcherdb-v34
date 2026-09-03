/*
================================================================================
    WATCHERDB STANDARD EDITION - PERFORMANCE INDEXES
    Version: 1.0.0
    Date: 2025-12-15

    This script creates performance indexes for WatcherDB Standard.
    Execute after 00_WATCHERDB_MASTER_DEPLOY.sql

    Index Naming Convention:
    - IX_TableName_Column1_Column2  (regular index)
    - UX_TableName_Column1          (unique index)
    - CIX_TableName_Column1         (clustered columnstore for analytics)
================================================================================
*/

USE [WatcherDB]
GO

PRINT '============================================================'
PRINT 'WATCHERDB STANDARD - PERFORMANCE INDEXES'
PRINT '============================================================'
PRINT ''

-- ============================================================================
-- SECTION 1: KPI SNAPSHOT INDEXES
-- ============================================================================
PRINT 'Creating indexes on kpi.KPISnapshot...'

-- Primary lookup: by server and time
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPISnapshot_ServerTime_Covering')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_KPISnapshot_ServerTime_Covering]
    ON [kpi].[KPISnapshot] ([ServerID_Formatted], [SnapshotTime] DESC)
    INCLUDE ([CPU_Percent], [Memory_Available_MB], [Memory_Page_Life_Expectancy], [Connections_Total], [Connections_Blocked])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_KPISnapshot_ServerTime_Covering'
END

-- Time-based queries (dashboard, trending)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPISnapshot_SnapshotTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_KPISnapshot_SnapshotTime]
    ON [kpi].[KPISnapshot] ([SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [CPU_Percent])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_KPISnapshot_SnapshotTime'
END

-- High CPU servers lookup
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPISnapshot_CPU')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_KPISnapshot_CPU]
    ON [kpi].[KPISnapshot] ([CPU_Percent] DESC, [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted])
    WHERE [CPU_Percent] > 80
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_KPISnapshot_CPU (filtered)'
END

-- Low memory servers lookup
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPISnapshot_Memory')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_KPISnapshot_Memory]
    ON [kpi].[KPISnapshot] ([Memory_Page_Life_Expectancy], [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [Memory_Available_MB])
    WHERE [Memory_Page_Life_Expectancy] < 300
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_KPISnapshot_Memory (filtered)'
END
GO

-- ============================================================================
-- SECTION 2: DATABASE SPACE INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on kpi.DatabaseSpace...'

-- Primary lookup: by server, database, and time
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DatabaseSpace_ServerDBTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_DatabaseSpace_ServerDBTime]
    ON [kpi].[DatabaseSpace] ([ServerID_Formatted], [DatabaseName], [SnapshotTime] DESC)
    INCLUDE ([FileGroupName], [TotalSize_MB], [FreeSpace_MB], [FreeSpace_Percent])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_DatabaseSpace_ServerDBTime'
END

-- Low space lookup (critical for alerting)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DatabaseSpace_LowSpace')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_DatabaseSpace_LowSpace]
    ON [kpi].[DatabaseSpace] ([FreeSpace_Percent], [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [DatabaseName], [FileGroupName], [FreeSpace_MB])
    WHERE [FreeSpace_Percent] < 20
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_DatabaseSpace_LowSpace (filtered)'
END

-- Drive space lookup
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DatabaseSpace_DriveSpace')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_DatabaseSpace_DriveSpace]
    ON [kpi].[DatabaseSpace] ([ServerID_Formatted], [DriveLetter], [SnapshotTime] DESC)
    INCLUDE ([DriveTotal_GB], [DriveFree_GB], [DriveFree_Percent])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_DatabaseSpace_DriveSpace'
END
GO

-- ============================================================================
-- SECTION 3: JOBS STATUS INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on kpi.JobsStatus...'

-- Primary lookup: by server and job
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_JobsStatus_ServerJobTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_JobsStatus_ServerJobTime]
    ON [kpi].[JobsStatus] ([ServerID_Formatted], [JobName], [SnapshotTime] DESC)
    INCLUDE ([LastRunStatus], [LastRunDate], [IsEnabled])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_JobsStatus_ServerJobTime'
END

-- Failed jobs lookup (critical for alerting)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_JobsStatus_Failed')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_JobsStatus_Failed]
    ON [kpi].[JobsStatus] ([LastRunStatus], [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [JobName], [LastRunDate])
    WHERE [LastRunStatus] = 'Failed'
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_JobsStatus_Failed (filtered)'
END
GO

-- ============================================================================
-- SECTION 4: HA STATUS INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on kpi.HAStatus...'

-- Primary lookup
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HAStatus_ServerDBTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_HAStatus_ServerDBTime]
    ON [kpi].[HAStatus] ([ServerID_Formatted], [DatabaseName], [SnapshotTime] DESC)
    INCLUDE ([HAType], [Role], [SyncState], [SyncHealth])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_HAStatus_ServerDBTime'
END

-- Unhealthy replicas lookup
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HAStatus_Unhealthy')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_HAStatus_Unhealthy]
    ON [kpi].[HAStatus] ([SyncHealth], [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [DatabaseName], [AGName], [SyncState])
    WHERE [SyncHealth] <> 'Healthy'
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_HAStatus_Unhealthy (filtered)'
END

-- Lag monitoring
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HAStatus_Lag')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_HAStatus_Lag]
    ON [kpi].[HAStatus] ([EstimatedLag_Seconds] DESC, [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [DatabaseName], [AGName])
    WHERE [EstimatedLag_Seconds] > 0
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_HAStatus_Lag (filtered)'
END
GO

-- ============================================================================
-- SECTION 5: BLOCKING SESSIONS INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on kpi.BlockingSessions...'

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BlockingSessions_ServerTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_BlockingSessions_ServerTime]
    ON [kpi].[BlockingSessions] ([ServerID_Formatted], [SnapshotTime] DESC)
    INCLUDE ([BlockerSessionID], [BlockedSessionCount], [BlockerWaitTime_Ms])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_BlockingSessions_ServerTime'
END
GO

-- ============================================================================
-- SECTION 6: LONG RUNNING QUERIES INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on kpi.LongRunningQueries...'

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LongRunningQueries_ServerTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_LongRunningQueries_ServerTime]
    ON [kpi].[LongRunningQueries] ([ServerID_Formatted], [SnapshotTime] DESC)
    INCLUDE ([SessionID], [Duration_Seconds], [DatabaseName])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_LongRunningQueries_ServerTime'
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LongRunningQueries_Duration')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_LongRunningQueries_Duration]
    ON [kpi].[LongRunningQueries] ([Duration_Seconds] DESC, [SnapshotTime] DESC)
    INCLUDE ([ServerID_Formatted], [SessionID], [DatabaseName])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_LongRunningQueries_Duration'
END
GO

-- ============================================================================
-- SECTION 7: ALERTS INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on monitoring.Alerts...'

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Alerts_ServerTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_Alerts_ServerTime]
    ON [monitoring].[Alerts] ([ServerID_Formatted], [AlertTime] DESC)
    INCLUDE ([AlertType], [Severity], [IsResolved])
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_Alerts_ServerTime'
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Alerts_ActiveBySeverity')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_Alerts_ActiveBySeverity]
    ON [monitoring].[Alerts] ([Severity], [AlertTime] DESC)
    INCLUDE ([ServerID_Formatted], [AlertType], [Message])
    WHERE [IsResolved] = 0
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_Alerts_ActiveBySeverity (filtered)'
END
GO

-- ============================================================================
-- SECTION 8: HISTORY INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on history tables...'

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPISnapshotHistory_ServerTime')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_KPISnapshotHistory_ServerTime]
    ON [history].[KPISnapshotHistory] ([ServerID_Formatted], [SnapshotTime] DESC)
    WITH (DATA_COMPRESSION = PAGE)

    PRINT '  Created IX_KPISnapshotHistory_ServerTime'
END
GO

-- ============================================================================
-- SECTION 9: SERVER INVENTORY INDEXES
-- ============================================================================
PRINT ''
PRINT 'Creating indexes on config.ServerInventory...'

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ServerInventory_Environment')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_ServerInventory_Environment]
    ON [config].[ServerInventory] ([Environment], [IsActive])
    INCLUDE ([ServerID_Formatted], [Criticality], [Application])

    PRINT '  Created IX_ServerInventory_Environment'
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ServerInventory_Active')
BEGIN
    CREATE NONCLUSTERED INDEX [IX_ServerInventory_Active]
    ON [config].[ServerInventory] ([IsActive], [IsMonitored])
    INCLUDE ([ServerID_Formatted], [CollectionIntervalMinutes], [LastCollectionTime])

    PRINT '  Created IX_ServerInventory_Active'
END
GO

-- ============================================================================
-- INDEX MAINTENANCE SUMMARY
-- ============================================================================
PRINT ''
PRINT '============================================================'
PRINT 'INDEX CREATION SUMMARY'
PRINT '============================================================'

SELECT
    SCHEMA_NAME(t.schema_id) + '.' + t.name AS TableName,
    i.name AS IndexName,
    i.type_desc AS IndexType,
    i.has_filter AS IsFiltered,
    CASE WHEN p.data_compression > 0 THEN 'PAGE' ELSE 'NONE' END AS Compression
FROM sys.indexes i
JOIN sys.tables t ON i.object_id = t.object_id
LEFT JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
WHERE t.is_ms_shipped = 0
AND i.name IS NOT NULL
AND i.type > 0
ORDER BY TableName, IndexName
GO

PRINT ''
PRINT 'Index creation completed successfully!'
PRINT '============================================================'
GO
