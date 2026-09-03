/*
================================================================================
    WATCHERDB STANDARD EDITION - VIEWS
    Version: 1.0.0
    Date: 2025-12-15

    This script creates dashboard and reporting views for WatcherDB Standard.
    Execute after 03_WATCHERDB_PROCEDURES.sql
================================================================================
*/

USE [WatcherDB]
GO

PRINT '============================================================'
PRINT 'WATCHERDB STANDARD - VIEWS'
PRINT '============================================================'
PRINT ''

-- ============================================================================
-- SECTION 1: DASHBOARD VIEWS
-- ============================================================================
PRINT 'Creating dashboard views...'

-- Latest KPI per server view
IF OBJECT_ID('kpi.vw_LatestKPI', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_LatestKPI]
GO

CREATE VIEW [kpi].[vw_LatestKPI]
AS
WITH LatestSnapshot AS (
    SELECT
        ServerID_Formatted,
        SnapshotTime,
        CPU_Percent,
        CPU_SQL_Percent,
        Memory_Total_MB,
        Memory_Available_MB,
        Memory_SQL_Used_MB,
        Memory_Buffer_Cache_Hit_Ratio,
        Memory_Page_Life_Expectancy,
        Connections_Total,
        Connections_Active,
        Connections_Sleeping,
        Connections_Blocked,
        Batch_Requests_Sec,
        IO_Read_MB_Sec,
        IO_Write_MB_Sec,
        ROW_NUMBER() OVER (PARTITION BY ServerID_Formatted ORDER BY SnapshotTime DESC) AS RowNum
    FROM [kpi].[KPISnapshot]
    WHERE SnapshotTime > DATEADD(HOUR, -2, GETDATE())
)
SELECT
    s.ServerID,
    s.ServerName,
    s.InstanceName,
    s.ServerID_Formatted,
    s.Environment,
    s.Criticality,
    s.Application,
    s.Owner,
    k.SnapshotTime,
    k.CPU_Percent,
    k.CPU_SQL_Percent,
    k.Memory_Total_MB,
    k.Memory_Available_MB,
    k.Memory_SQL_Used_MB,
    k.Memory_Buffer_Cache_Hit_Ratio,
    k.Memory_Page_Life_Expectancy,
    k.Connections_Total,
    k.Connections_Active,
    k.Connections_Sleeping,
    k.Connections_Blocked,
    k.Batch_Requests_Sec,
    k.IO_Read_MB_Sec,
    k.IO_Write_MB_Sec,
    DATEDIFF(MINUTE, k.SnapshotTime, GETDATE()) AS MinutesSinceLastCollection,
    CASE
        WHEN k.SnapshotTime IS NULL THEN 'No Data'
        WHEN DATEDIFF(MINUTE, k.SnapshotTime, GETDATE()) > 15 THEN 'Stale'
        WHEN k.CPU_Percent >= 95 OR k.Memory_Page_Life_Expectancy < 60 THEN 'Critical'
        WHEN k.CPU_Percent >= 80 OR k.Memory_Page_Life_Expectancy < 300 THEN 'Warning'
        ELSE 'Healthy'
    END AS HealthStatus,
    1 AS Severity_Order  -- For ordering
FROM [config].[ServerInventory] s
LEFT JOIN LatestSnapshot k ON s.ServerID_Formatted = k.ServerID_Formatted AND k.RowNum = 1
WHERE s.IsActive = 1 AND s.IsMonitored = 1
GO

PRINT '  Created kpi.vw_LatestKPI'

-- Server health summary view
IF OBJECT_ID('monitoring.vw_ServerHealth', 'V') IS NOT NULL
    DROP VIEW [monitoring].[vw_ServerHealth]
GO

CREATE VIEW [monitoring].[vw_ServerHealth]
AS
SELECT
    ServerID_Formatted,
    ServerName,
    InstanceName,
    Environment,
    Criticality,
    HealthStatus,
    CPU_Percent,
    Memory_Page_Life_Expectancy,
    Connections_Blocked,
    MinutesSinceLastCollection,
    CASE HealthStatus
        WHEN 'Critical' THEN 1
        WHEN 'Warning' THEN 2
        WHEN 'Healthy' THEN 3
        WHEN 'Stale' THEN 4
        ELSE 5
    END AS Health_Order
FROM [kpi].[vw_LatestKPI]
GO

PRINT '  Created monitoring.vw_ServerHealth'

-- ============================================================================
-- SECTION 2: SPACE ANALYSIS VIEWS
-- ============================================================================
PRINT ''
PRINT 'Creating space analysis views...'

-- Latest database space view
IF OBJECT_ID('kpi.vw_LatestDatabaseSpace', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_LatestDatabaseSpace]
GO

CREATE VIEW [kpi].[vw_LatestDatabaseSpace]
AS
WITH LatestSpace AS (
    SELECT
        ServerID_Formatted,
        DatabaseName,
        FileGroupName,
        LogicalFileName,
        PhysicalPath,
        FileType,
        TotalSize_MB,
        UsedSpace_MB,
        FreeSpace_MB,
        FreeSpace_Percent,
        MaxSize_MB,
        GrowthType,
        GrowthValue,
        IsAutoGrowthEnabled,
        DriveLetter,
        DriveTotal_GB,
        DriveFree_GB,
        DriveFree_Percent,
        SnapshotTime,
        ROW_NUMBER() OVER (
            PARTITION BY ServerID_Formatted, DatabaseName, LogicalFileName
            ORDER BY SnapshotTime DESC
        ) AS RowNum
    FROM [kpi].[DatabaseSpace]
    WHERE SnapshotTime > DATEADD(DAY, -1, GETDATE())
)
SELECT
    ServerID_Formatted,
    DatabaseName,
    FileGroupName,
    LogicalFileName,
    PhysicalPath,
    FileType,
    TotalSize_MB,
    UsedSpace_MB,
    FreeSpace_MB,
    FreeSpace_Percent,
    MaxSize_MB,
    GrowthType,
    GrowthValue,
    IsAutoGrowthEnabled,
    DriveLetter,
    DriveTotal_GB,
    DriveFree_GB,
    DriveFree_Percent,
    SnapshotTime,
    CASE
        WHEN FreeSpace_Percent < 5 THEN 'Critical'
        WHEN FreeSpace_Percent < 10 THEN 'Warning'
        WHEN FreeSpace_Percent < 20 THEN 'Low'
        ELSE 'Normal'
    END AS SpaceStatus,
    CASE
        WHEN DriveFree_Percent < 5 THEN 'Critical'
        WHEN DriveFree_Percent < 10 THEN 'Warning'
        WHEN DriveFree_Percent < 20 THEN 'Low'
        ELSE 'Normal'
    END AS DriveStatus
FROM LatestSpace
WHERE RowNum = 1
GO

PRINT '  Created kpi.vw_LatestDatabaseSpace'

-- Critical space summary view
IF OBJECT_ID('kpi.vw_CriticalSpace', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_CriticalSpace]
GO

CREATE VIEW [kpi].[vw_CriticalSpace]
AS
SELECT
    ServerID_Formatted,
    DatabaseName,
    FileGroupName,
    LogicalFileName,
    FileType,
    TotalSize_MB,
    FreeSpace_MB,
    FreeSpace_Percent,
    DriveLetter,
    DriveFree_GB,
    DriveFree_Percent,
    SpaceStatus,
    DriveStatus
FROM [kpi].[vw_LatestDatabaseSpace]
WHERE SpaceStatus IN ('Critical', 'Warning')
OR DriveStatus IN ('Critical', 'Warning')
GO

PRINT '  Created kpi.vw_CriticalSpace'

-- ============================================================================
-- SECTION 3: JOBS ANALYSIS VIEWS
-- ============================================================================
PRINT ''
PRINT 'Creating jobs analysis views...'

-- Latest job status view
IF OBJECT_ID('kpi.vw_LatestJobStatus', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_LatestJobStatus]
GO

CREATE VIEW [kpi].[vw_LatestJobStatus]
AS
WITH LatestJobs AS (
    SELECT
        ServerID_Formatted,
        JobID,
        JobName,
        JobCategory,
        JobOwner,
        IsEnabled,
        LastRunDate,
        LastRunDuration_Seconds,
        LastRunStatus,
        LastRunMessage,
        NextRunDate,
        ScheduleDescription,
        SnapshotTime,
        ROW_NUMBER() OVER (
            PARTITION BY ServerID_Formatted, JobName
            ORDER BY SnapshotTime DESC
        ) AS RowNum
    FROM [kpi].[JobsStatus]
    WHERE SnapshotTime > DATEADD(DAY, -1, GETDATE())
)
SELECT
    ServerID_Formatted,
    JobID,
    JobName,
    JobCategory,
    JobOwner,
    IsEnabled,
    LastRunDate,
    LastRunDuration_Seconds,
    LastRunStatus,
    LastRunMessage,
    NextRunDate,
    ScheduleDescription,
    SnapshotTime,
    CASE
        WHEN LastRunStatus = 'Failed' THEN 'Failed'
        WHEN IsEnabled = 0 THEN 'Disabled'
        WHEN LastRunStatus = 'Running' THEN 'Running'
        WHEN LastRunStatus = 'Succeeded' THEN 'OK'
        ELSE 'Unknown'
    END AS JobHealth
FROM LatestJobs
WHERE RowNum = 1
GO

PRINT '  Created kpi.vw_LatestJobStatus'

-- Failed jobs view
IF OBJECT_ID('kpi.vw_FailedJobs', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_FailedJobs]
GO

CREATE VIEW [kpi].[vw_FailedJobs]
AS
SELECT
    ServerID_Formatted,
    JobName,
    JobCategory,
    LastRunDate,
    LastRunDuration_Seconds,
    LastRunMessage,
    NextRunDate,
    SnapshotTime
FROM [kpi].[vw_LatestJobStatus]
WHERE LastRunStatus = 'Failed'
GO

PRINT '  Created kpi.vw_FailedJobs'

-- ============================================================================
-- SECTION 4: HA/AG VIEWS
-- ============================================================================
PRINT ''
PRINT 'Creating HA/AG views...'

-- Latest HA status view
IF OBJECT_ID('kpi.vw_LatestHAStatus', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_LatestHAStatus]
GO

CREATE VIEW [kpi].[vw_LatestHAStatus]
AS
WITH LatestHA AS (
    SELECT
        ServerID_Formatted,
        AGName,
        DatabaseName,
        ReplicaServer,
        HAType,
        Role,
        SyncState,
        SyncHealth,
        SendQueueSize_KB,
        RedoQueueSize_KB,
        LastCommitTime,
        LastRedoneTime,
        EstimatedLag_Seconds,
        SnapshotTime,
        ROW_NUMBER() OVER (
            PARTITION BY ServerID_Formatted, DatabaseName, ReplicaServer
            ORDER BY SnapshotTime DESC
        ) AS RowNum
    FROM [kpi].[HAStatus]
    WHERE SnapshotTime > DATEADD(HOUR, -2, GETDATE())
)
SELECT
    ServerID_Formatted,
    AGName,
    DatabaseName,
    ReplicaServer,
    HAType,
    Role,
    SyncState,
    SyncHealth,
    SendQueueSize_KB,
    RedoQueueSize_KB,
    LastCommitTime,
    LastRedoneTime,
    EstimatedLag_Seconds,
    SnapshotTime,
    CASE
        WHEN SyncHealth = 'NotHealthy' THEN 'Critical'
        WHEN SyncHealth = 'PartiallyHealthy' THEN 'Warning'
        WHEN SyncState = 'NotSynchronizing' THEN 'Critical'
        WHEN EstimatedLag_Seconds > 60 THEN 'Warning'
        WHEN SyncHealth = 'Healthy' AND SyncState = 'Synchronized' THEN 'Healthy'
        ELSE 'Unknown'
    END AS HAHealth
FROM LatestHA
WHERE RowNum = 1
GO

PRINT '  Created kpi.vw_LatestHAStatus'

-- Unhealthy replicas view
IF OBJECT_ID('kpi.vw_UnhealthyReplicas', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_UnhealthyReplicas]
GO

CREATE VIEW [kpi].[vw_UnhealthyReplicas]
AS
SELECT
    ServerID_Formatted,
    AGName,
    DatabaseName,
    ReplicaServer,
    HAType,
    Role,
    SyncState,
    SyncHealth,
    EstimatedLag_Seconds,
    HAHealth,
    SnapshotTime
FROM [kpi].[vw_LatestHAStatus]
WHERE HAHealth IN ('Critical', 'Warning')
GO

PRINT '  Created kpi.vw_UnhealthyReplicas'

-- ============================================================================
-- SECTION 5: ALERTS VIEWS
-- ============================================================================
PRINT ''
PRINT 'Creating alerts views...'

-- Active alerts view
IF OBJECT_ID('monitoring.vw_ActiveAlerts', 'V') IS NOT NULL
    DROP VIEW [monitoring].[vw_ActiveAlerts]
GO

CREATE VIEW [monitoring].[vw_ActiveAlerts]
AS
SELECT
    AlertID,
    ServerID_Formatted,
    AlertTime,
    AlertType,
    Severity,
    MetricName,
    MetricValue,
    ThresholdValue,
    Message,
    IsAcknowledged,
    AcknowledgedBy,
    AcknowledgedDate,
    DATEDIFF(MINUTE, AlertTime, GETDATE()) AS MinutesActive,
    CASE Severity
        WHEN 'Critical' THEN 1
        WHEN 'Warning' THEN 2
        ELSE 3
    END AS Severity_Order
FROM [monitoring].[Alerts]
WHERE IsResolved = 0
GO

PRINT '  Created monitoring.vw_ActiveAlerts'

-- Alert summary by server view
IF OBJECT_ID('monitoring.vw_AlertSummaryByServer', 'V') IS NOT NULL
    DROP VIEW [monitoring].[vw_AlertSummaryByServer]
GO

CREATE VIEW [monitoring].[vw_AlertSummaryByServer]
AS
SELECT
    ServerID_Formatted,
    COUNT(*) AS TotalActiveAlerts,
    SUM(CASE WHEN Severity = 'Critical' THEN 1 ELSE 0 END) AS CriticalAlerts,
    SUM(CASE WHEN Severity = 'Warning' THEN 1 ELSE 0 END) AS WarningAlerts,
    MIN(AlertTime) AS OldestAlertTime,
    MAX(AlertTime) AS NewestAlertTime
FROM [monitoring].[Alerts]
WHERE IsResolved = 0
GROUP BY ServerID_Formatted
GO

PRINT '  Created monitoring.vw_AlertSummaryByServer'

-- ============================================================================
-- SECTION 6: INVENTORY VIEWS
-- ============================================================================
PRINT ''
PRINT 'Creating inventory views...'

-- Active servers inventory view
IF OBJECT_ID('config.vw_ActiveServers', 'V') IS NOT NULL
    DROP VIEW [config].[vw_ActiveServers]
GO

CREATE VIEW [config].[vw_ActiveServers]
AS
SELECT
    ServerID,
    ServerName,
    InstanceName,
    ServerID_Formatted,
    ConnectionString,
    Environment,
    Criticality,
    Owner,
    Application,
    IsActive,
    IsMonitored,
    CollectionIntervalMinutes,
    LastCollectionTime,
    LastCollectionStatus,
    DATEDIFF(MINUTE, LastCollectionTime, GETDATE()) AS MinutesSinceLastCollection,
    CASE
        WHEN LastCollectionTime IS NULL THEN 'Never Collected'
        WHEN DATEDIFF(MINUTE, LastCollectionTime, GETDATE()) > CollectionIntervalMinutes * 3 THEN 'Collection Failed'
        WHEN DATEDIFF(MINUTE, LastCollectionTime, GETDATE()) > CollectionIntervalMinutes * 2 THEN 'Collection Delayed'
        ELSE 'Collection OK'
    END AS CollectionHealth,
    Notes,
    CreatedDate,
    ModifiedDate
FROM [config].[ServerInventory]
WHERE IsActive = 1
GO

PRINT '  Created config.vw_ActiveServers'

-- Server count by environment view
IF OBJECT_ID('config.vw_ServerCountByEnvironment', 'V') IS NOT NULL
    DROP VIEW [config].[vw_ServerCountByEnvironment]
GO

CREATE VIEW [config].[vw_ServerCountByEnvironment]
AS
SELECT
    Environment,
    COUNT(*) AS TotalServers,
    SUM(CASE WHEN IsActive = 1 THEN 1 ELSE 0 END) AS ActiveServers,
    SUM(CASE WHEN IsMonitored = 1 THEN 1 ELSE 0 END) AS MonitoredServers,
    SUM(CASE WHEN Criticality = 'Critical' THEN 1 ELSE 0 END) AS CriticalServers,
    SUM(CASE WHEN Criticality = 'High' THEN 1 ELSE 0 END) AS HighPriorityServers
FROM [config].[ServerInventory]
GROUP BY Environment
GO

PRINT '  Created config.vw_ServerCountByEnvironment'

-- ============================================================================
-- SECTION 7: BLOCKING VIEWS
-- ============================================================================
PRINT ''
PRINT 'Creating blocking views...'

-- Current blocking view
IF OBJECT_ID('kpi.vw_CurrentBlocking', 'V') IS NOT NULL
    DROP VIEW [kpi].[vw_CurrentBlocking]
GO

CREATE VIEW [kpi].[vw_CurrentBlocking]
AS
WITH LatestBlocking AS (
    SELECT
        ServerID_Formatted,
        BlockerSessionID,
        BlockerLoginName,
        BlockerHostName,
        BlockerProgram,
        BlockerDatabase,
        BlockerCommand,
        BlockerWaitTime_Ms,
        BlockedSessionCount,
        BlockedSessionIDs,
        TotalBlockedWaitTime_Ms,
        SnapshotTime,
        ROW_NUMBER() OVER (PARTITION BY ServerID_Formatted ORDER BY SnapshotTime DESC) AS RowNum
    FROM [kpi].[BlockingSessions]
    WHERE SnapshotTime > DATEADD(MINUTE, -15, GETDATE())
)
SELECT
    ServerID_Formatted,
    BlockerSessionID,
    BlockerLoginName,
    BlockerHostName,
    BlockerProgram,
    BlockerDatabase,
    BlockerCommand,
    BlockerWaitTime_Ms,
    BlockedSessionCount,
    BlockedSessionIDs,
    TotalBlockedWaitTime_Ms,
    SnapshotTime
FROM LatestBlocking
WHERE RowNum = 1
AND BlockedSessionCount > 0
GO

PRINT '  Created kpi.vw_CurrentBlocking'

-- ============================================================================
-- DEPLOYMENT SUMMARY
-- ============================================================================
PRINT ''
PRINT '============================================================'
PRINT 'VIEWS DEPLOYMENT SUMMARY'
PRINT '============================================================'
PRINT ''

SELECT
    SCHEMA_NAME(schema_id) + '.' + name AS ViewName,
    create_date AS CreatedDate,
    modify_date AS ModifiedDate
FROM sys.views
WHERE is_ms_shipped = 0
ORDER BY SCHEMA_NAME(schema_id), name
GO

PRINT ''
PRINT 'Views deployment completed successfully!'
PRINT '============================================================'
GO
