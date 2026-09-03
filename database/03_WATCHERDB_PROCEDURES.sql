/*
================================================================================
    WATCHERDB STANDARD EDITION - STORED PROCEDURES
    Version: 1.0.0
    Date: 2025-12-15

    This script creates the stored procedures for WatcherDB Standard.
    Execute after 02_WATCHERDB_INDEXES.sql

    Procedures Created:
    - Collection procedures (called by Python collector)
    - Maintenance procedures (cleanup, archiving)
    - Dashboard procedures (summary data)
    - Alerting procedures
================================================================================
*/

USE [WatcherDB]
GO

PRINT '============================================================'
PRINT 'WATCHERDB STANDARD - STORED PROCEDURES'
PRINT '============================================================'
PRINT ''

-- ============================================================================
-- SECTION 1: UTILITY PROCEDURES
-- ============================================================================
PRINT 'Creating utility procedures...'

-- Get setting value
IF OBJECT_ID('config.usp_GetSetting', 'P') IS NOT NULL
    DROP PROCEDURE [config].[usp_GetSetting]
GO

CREATE PROCEDURE [config].[usp_GetSetting]
    @SettingName NVARCHAR(256),
    @DefaultValue NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT COALESCE(SettingValue, @DefaultValue) AS SettingValue
    FROM [config].[Settings]
    WHERE SettingName = @SettingName;

    IF @@ROWCOUNT = 0
        SELECT @DefaultValue AS SettingValue;
END
GO

PRINT '  Created config.usp_GetSetting'

-- Set setting value
IF OBJECT_ID('config.usp_SetSetting', 'P') IS NOT NULL
    DROP PROCEDURE [config].[usp_SetSetting]
GO

CREATE PROCEDURE [config].[usp_SetSetting]
    @SettingName NVARCHAR(256),
    @SettingValue NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE [config].[Settings]
    SET SettingValue = @SettingValue,
        ModifiedDate = GETDATE()
    WHERE SettingName = @SettingName;

    IF @@ROWCOUNT = 0
    BEGIN
        INSERT INTO [config].[Settings] (SettingName, SettingValue)
        VALUES (@SettingName, @SettingValue);
    END
END
GO

PRINT '  Created config.usp_SetSetting'
GO

-- ============================================================================
-- SECTION 2: DATA INSERTION PROCEDURES
-- ============================================================================
PRINT ''
PRINT 'Creating data insertion procedures...'

-- Insert KPI Snapshot
IF OBJECT_ID('kpi.usp_InsertKPISnapshot', 'P') IS NOT NULL
    DROP PROCEDURE [kpi].[usp_InsertKPISnapshot]
GO

CREATE PROCEDURE [kpi].[usp_InsertKPISnapshot]
    @ServerID_Formatted NVARCHAR(256),
    @CPU_Percent DECIMAL(5,2) = NULL,
    @CPU_SQL_Percent DECIMAL(5,2) = NULL,
    @Memory_Total_MB BIGINT = NULL,
    @Memory_Available_MB BIGINT = NULL,
    @Memory_SQL_Used_MB BIGINT = NULL,
    @Memory_Buffer_Cache_Hit_Ratio DECIMAL(5,2) = NULL,
    @Memory_Page_Life_Expectancy INT = NULL,
    @Memory_Lazy_Writes_Sec BIGINT = NULL,
    @Storage_Data_Used_GB DECIMAL(18,2) = NULL,
    @Storage_Log_Used_GB DECIMAL(18,2) = NULL,
    @Storage_Data_Free_GB DECIMAL(18,2) = NULL,
    @Storage_Log_Free_GB DECIMAL(18,2) = NULL,
    @Connections_Total INT = NULL,
    @Connections_Active INT = NULL,
    @Connections_Sleeping INT = NULL,
    @Connections_Blocked INT = NULL,
    @Batch_Requests_Sec BIGINT = NULL,
    @Compilations_Sec BIGINT = NULL,
    @Recompilations_Sec BIGINT = NULL,
    @IO_Read_MB_Sec DECIMAL(18,2) = NULL,
    @IO_Write_MB_Sec DECIMAL(18,2) = NULL,
    @CollectionDurationMs INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [kpi].[KPISnapshot] (
        ServerID_Formatted, SnapshotTime, CollectionDurationMs,
        CPU_Percent, CPU_SQL_Percent, CPU_Other_Percent,
        Memory_Total_MB, Memory_Available_MB, Memory_SQL_Used_MB,
        Memory_Buffer_Cache_Hit_Ratio, Memory_Page_Life_Expectancy, Memory_Lazy_Writes_Sec,
        Storage_Data_Used_GB, Storage_Log_Used_GB, Storage_Data_Free_GB, Storage_Log_Free_GB,
        Connections_Total, Connections_Active, Connections_Sleeping, Connections_Blocked,
        Batch_Requests_Sec, Compilations_Sec, Recompilations_Sec,
        IO_Read_MB_Sec, IO_Write_MB_Sec
    )
    VALUES (
        @ServerID_Formatted, GETDATE(), @CollectionDurationMs,
        @CPU_Percent, @CPU_SQL_Percent, @CPU_Percent - ISNULL(@CPU_SQL_Percent, 0),
        @Memory_Total_MB, @Memory_Available_MB, @Memory_SQL_Used_MB,
        @Memory_Buffer_Cache_Hit_Ratio, @Memory_Page_Life_Expectancy, @Memory_Lazy_Writes_Sec,
        @Storage_Data_Used_GB, @Storage_Log_Used_GB, @Storage_Data_Free_GB, @Storage_Log_Free_GB,
        @Connections_Total, @Connections_Active, @Connections_Sleeping, @Connections_Blocked,
        @Batch_Requests_Sec, @Compilations_Sec, @Recompilations_Sec,
        @IO_Read_MB_Sec, @IO_Write_MB_Sec
    );

    -- Update last collection time in inventory
    UPDATE [config].[ServerInventory]
    SET LastCollectionTime = GETDATE(),
        LastCollectionStatus = 'Success'
    WHERE ServerID_Formatted = @ServerID_Formatted;

    SELECT SCOPE_IDENTITY() AS SnapshotID;
END
GO

PRINT '  Created kpi.usp_InsertKPISnapshot'

-- Insert Database Space
IF OBJECT_ID('kpi.usp_InsertDatabaseSpace', 'P') IS NOT NULL
    DROP PROCEDURE [kpi].[usp_InsertDatabaseSpace]
GO

CREATE PROCEDURE [kpi].[usp_InsertDatabaseSpace]
    @ServerID_Formatted NVARCHAR(256),
    @DatabaseName NVARCHAR(128),
    @FileGroupName NVARCHAR(128) = NULL,
    @LogicalFileName NVARCHAR(128) = NULL,
    @PhysicalPath NVARCHAR(500) = NULL,
    @FileType NVARCHAR(20) = NULL,
    @TotalSize_MB DECIMAL(18,2) = NULL,
    @UsedSpace_MB DECIMAL(18,2) = NULL,
    @FreeSpace_MB DECIMAL(18,2) = NULL,
    @MaxSize_MB DECIMAL(18,2) = NULL,
    @GrowthType NVARCHAR(20) = NULL,
    @GrowthValue DECIMAL(18,2) = NULL,
    @IsAutoGrowthEnabled BIT = NULL,
    @DriveLetter CHAR(1) = NULL,
    @DriveTotal_GB DECIMAL(18,2) = NULL,
    @DriveFree_GB DECIMAL(18,2) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @FreeSpace_Percent DECIMAL(5,2) = NULL;
    DECLARE @DriveFree_Percent DECIMAL(5,2) = NULL;

    IF @TotalSize_MB > 0
        SET @FreeSpace_Percent = (@FreeSpace_MB / @TotalSize_MB) * 100;

    IF @DriveTotal_GB > 0
        SET @DriveFree_Percent = (@DriveFree_GB / @DriveTotal_GB) * 100;

    INSERT INTO [kpi].[DatabaseSpace] (
        ServerID_Formatted, DatabaseName, SnapshotTime,
        FileGroupName, LogicalFileName, PhysicalPath, FileType,
        TotalSize_MB, UsedSpace_MB, FreeSpace_MB, FreeSpace_Percent,
        MaxSize_MB, GrowthType, GrowthValue, IsAutoGrowthEnabled,
        DriveLetter, DriveTotal_GB, DriveFree_GB, DriveFree_Percent
    )
    VALUES (
        @ServerID_Formatted, @DatabaseName, GETDATE(),
        @FileGroupName, @LogicalFileName, @PhysicalPath, @FileType,
        @TotalSize_MB, @UsedSpace_MB, @FreeSpace_MB, @FreeSpace_Percent,
        @MaxSize_MB, @GrowthType, @GrowthValue, @IsAutoGrowthEnabled,
        @DriveLetter, @DriveTotal_GB, @DriveFree_GB, @DriveFree_Percent
    );

    SELECT SCOPE_IDENTITY() AS SpaceID;
END
GO

PRINT '  Created kpi.usp_InsertDatabaseSpace'

-- Insert Alert
IF OBJECT_ID('monitoring.usp_InsertAlert', 'P') IS NOT NULL
    DROP PROCEDURE [monitoring].[usp_InsertAlert]
GO

CREATE PROCEDURE [monitoring].[usp_InsertAlert]
    @ServerID_Formatted NVARCHAR(256),
    @AlertType NVARCHAR(100),
    @Severity NVARCHAR(20),
    @MetricName NVARCHAR(256) = NULL,
    @MetricValue NVARCHAR(256) = NULL,
    @ThresholdValue NVARCHAR(256) = NULL,
    @Message NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Check if similar alert already exists and is not resolved
    IF NOT EXISTS (
        SELECT 1 FROM [monitoring].[Alerts]
        WHERE ServerID_Formatted = @ServerID_Formatted
        AND AlertType = @AlertType
        AND MetricName = @MetricName
        AND IsResolved = 0
        AND AlertTime > DATEADD(HOUR, -1, GETDATE())
    )
    BEGIN
        INSERT INTO [monitoring].[Alerts] (
            ServerID_Formatted, AlertTime, AlertType, Severity,
            MetricName, MetricValue, ThresholdValue, Message
        )
        VALUES (
            @ServerID_Formatted, GETDATE(), @AlertType, @Severity,
            @MetricName, @MetricValue, @ThresholdValue, @Message
        );

        SELECT SCOPE_IDENTITY() AS AlertID;
    END
    ELSE
    BEGIN
        SELECT -1 AS AlertID;  -- Alert already exists
    END
END
GO

PRINT '  Created monitoring.usp_InsertAlert'
GO

-- ============================================================================
-- SECTION 3: DATA RETRIEVAL PROCEDURES
-- ============================================================================
PRINT ''
PRINT 'Creating data retrieval procedures...'

-- Get latest KPI for all servers
IF OBJECT_ID('kpi.usp_GetLatestKPIAllServers', 'P') IS NOT NULL
    DROP PROCEDURE [kpi].[usp_GetLatestKPIAllServers]
GO

CREATE PROCEDURE [kpi].[usp_GetLatestKPIAllServers]
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH LatestKPI AS (
        SELECT
            k.ServerID_Formatted,
            k.SnapshotTime,
            k.CPU_Percent,
            k.Memory_Available_MB,
            k.Memory_Page_Life_Expectancy,
            k.Connections_Total,
            k.Connections_Blocked,
            k.Batch_Requests_Sec,
            ROW_NUMBER() OVER (PARTITION BY k.ServerID_Formatted ORDER BY k.SnapshotTime DESC) AS RowNum
        FROM [kpi].[KPISnapshot] k
        WHERE k.SnapshotTime > DATEADD(HOUR, -1, GETDATE())
    )
    SELECT
        s.ServerID_Formatted,
        s.ServerName,
        s.InstanceName,
        s.Environment,
        s.Criticality,
        s.Application,
        k.SnapshotTime,
        k.CPU_Percent,
        k.Memory_Available_MB,
        k.Memory_Page_Life_Expectancy,
        k.Connections_Total,
        k.Connections_Blocked,
        k.Batch_Requests_Sec,
        DATEDIFF(MINUTE, k.SnapshotTime, GETDATE()) AS MinutesSinceLastCollection
    FROM [config].[ServerInventory] s
    LEFT JOIN LatestKPI k ON s.ServerID_Formatted = k.ServerID_Formatted AND k.RowNum = 1
    WHERE s.IsActive = 1
    ORDER BY s.Environment, s.Criticality DESC, s.ServerName;
END
GO

PRINT '  Created kpi.usp_GetLatestKPIAllServers'

-- Get KPI history for a server
IF OBJECT_ID('kpi.usp_GetKPIHistory', 'P') IS NOT NULL
    DROP PROCEDURE [kpi].[usp_GetKPIHistory]
GO

CREATE PROCEDURE [kpi].[usp_GetKPIHistory]
    @ServerID_Formatted NVARCHAR(256),
    @HoursBack INT = 24
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        SnapshotTime,
        CPU_Percent,
        CPU_SQL_Percent,
        Memory_Available_MB,
        Memory_Page_Life_Expectancy,
        Memory_Buffer_Cache_Hit_Ratio,
        Connections_Total,
        Connections_Active,
        Connections_Blocked,
        Batch_Requests_Sec,
        IO_Read_MB_Sec,
        IO_Write_MB_Sec
    FROM [kpi].[KPISnapshot]
    WHERE ServerID_Formatted = @ServerID_Formatted
    AND SnapshotTime > DATEADD(HOUR, -@HoursBack, GETDATE())
    ORDER BY SnapshotTime DESC;
END
GO

PRINT '  Created kpi.usp_GetKPIHistory'

-- Get database space summary
IF OBJECT_ID('kpi.usp_GetDatabaseSpaceSummary', 'P') IS NOT NULL
    DROP PROCEDURE [kpi].[usp_GetDatabaseSpaceSummary]
GO

CREATE PROCEDURE [kpi].[usp_GetDatabaseSpaceSummary]
    @ServerID_Formatted NVARCHAR(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH LatestSpace AS (
        SELECT
            ServerID_Formatted,
            DatabaseName,
            FileGroupName,
            TotalSize_MB,
            UsedSpace_MB,
            FreeSpace_MB,
            FreeSpace_Percent,
            DriveLetter,
            DriveFree_GB,
            DriveFree_Percent,
            ROW_NUMBER() OVER (
                PARTITION BY ServerID_Formatted, DatabaseName, FileGroupName
                ORDER BY SnapshotTime DESC
            ) AS RowNum
        FROM [kpi].[DatabaseSpace]
        WHERE (@ServerID_Formatted IS NULL OR ServerID_Formatted = @ServerID_Formatted)
        AND SnapshotTime > DATEADD(DAY, -1, GETDATE())
    )
    SELECT
        ServerID_Formatted,
        DatabaseName,
        FileGroupName,
        TotalSize_MB,
        UsedSpace_MB,
        FreeSpace_MB,
        FreeSpace_Percent,
        DriveLetter,
        DriveFree_GB,
        DriveFree_Percent,
        CASE
            WHEN FreeSpace_Percent < 10 THEN 'Critical'
            WHEN FreeSpace_Percent < 20 THEN 'Warning'
            ELSE 'Normal'
        END AS SpaceStatus
    FROM LatestSpace
    WHERE RowNum = 1
    ORDER BY FreeSpace_Percent ASC;
END
GO

PRINT '  Created kpi.usp_GetDatabaseSpaceSummary'

-- Get active alerts
IF OBJECT_ID('monitoring.usp_GetActiveAlerts', 'P') IS NOT NULL
    DROP PROCEDURE [monitoring].[usp_GetActiveAlerts]
GO

CREATE PROCEDURE [monitoring].[usp_GetActiveAlerts]
    @ServerID_Formatted NVARCHAR(256) = NULL,
    @Severity NVARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;

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
        AcknowledgedDate
    FROM [monitoring].[Alerts]
    WHERE IsResolved = 0
    AND (@ServerID_Formatted IS NULL OR ServerID_Formatted = @ServerID_Formatted)
    AND (@Severity IS NULL OR Severity = @Severity)
    ORDER BY
        CASE Severity
            WHEN 'Critical' THEN 1
            WHEN 'Warning' THEN 2
            ELSE 3
        END,
        AlertTime DESC;
END
GO

PRINT '  Created monitoring.usp_GetActiveAlerts'
GO

-- ============================================================================
-- SECTION 4: MAINTENANCE PROCEDURES
-- ============================================================================
PRINT ''
PRINT 'Creating maintenance procedures...'

-- Purge old data
IF OBJECT_ID('monitoring.usp_PurgeOldData', 'P') IS NOT NULL
    DROP PROCEDURE [monitoring].[usp_PurgeOldData]
GO

CREATE PROCEDURE [monitoring].[usp_PurgeOldData]
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @RetentionDays_KPI INT;
    DECLARE @RetentionDays_History INT;
    DECLARE @RetentionDays_Logs INT;
    DECLARE @DeletedRows INT = 0;
    DECLARE @TotalDeleted INT = 0;

    -- Get retention settings
    SELECT @RetentionDays_KPI = CAST(SettingValue AS INT) FROM [config].[Settings] WHERE SettingName = 'RetentionDays_KPI';
    SELECT @RetentionDays_History = CAST(SettingValue AS INT) FROM [config].[Settings] WHERE SettingName = 'RetentionDays_History';
    SELECT @RetentionDays_Logs = CAST(SettingValue AS INT) FROM [config].[Settings] WHERE SettingName = 'RetentionDays_Logs';

    -- Default values if not set
    SET @RetentionDays_KPI = ISNULL(@RetentionDays_KPI, 30);
    SET @RetentionDays_History = ISNULL(@RetentionDays_History, 365);
    SET @RetentionDays_Logs = ISNULL(@RetentionDays_Logs, 7);

    PRINT 'Starting data purge...';
    PRINT 'KPI retention: ' + CAST(@RetentionDays_KPI AS VARCHAR) + ' days';
    PRINT 'History retention: ' + CAST(@RetentionDays_History AS VARCHAR) + ' days';
    PRINT 'Logs retention: ' + CAST(@RetentionDays_Logs AS VARCHAR) + ' days';

    -- Archive KPI data before purging
    INSERT INTO [history].[KPISnapshotHistory] (
        SnapshotID, ServerID_Formatted, SnapshotTime,
        CPU_Percent, Memory_Available_MB, Memory_Page_Life_Expectancy,
        Connections_Total, Connections_Blocked, Batch_Requests_Sec
    )
    SELECT
        SnapshotID, ServerID_Formatted, SnapshotTime,
        CPU_Percent, Memory_Available_MB, Memory_Page_Life_Expectancy,
        Connections_Total, Connections_Blocked, Batch_Requests_Sec
    FROM [kpi].[KPISnapshot]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE())
    AND NOT EXISTS (
        SELECT 1 FROM [history].[KPISnapshotHistory] h
        WHERE h.SnapshotID = [kpi].[KPISnapshot].SnapshotID
    );

    SET @DeletedRows = @@ROWCOUNT;
    PRINT 'Archived ' + CAST(@DeletedRows AS VARCHAR) + ' KPI snapshots';

    -- Purge KPI snapshots
    DELETE FROM [kpi].[KPISnapshot]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from kpi.KPISnapshot';

    -- Purge database space data
    DELETE FROM [kpi].[DatabaseSpace]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from kpi.DatabaseSpace';

    -- Purge jobs status
    DELETE FROM [kpi].[JobsStatus]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from kpi.JobsStatus';

    -- Purge HA status
    DELETE FROM [kpi].[HAStatus]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from kpi.HAStatus';

    -- Purge blocking sessions
    DELETE FROM [kpi].[BlockingSessions]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from kpi.BlockingSessions';

    -- Purge long running queries
    DELETE FROM [kpi].[LongRunningQueries]
    WHERE SnapshotTime < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from kpi.LongRunningQueries';

    -- Purge resolved alerts
    DELETE FROM [monitoring].[Alerts]
    WHERE IsResolved = 1
    AND ResolvedDate < DATEADD(DAY, -@RetentionDays_KPI, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from monitoring.Alerts (resolved)';

    -- Purge collection logs
    DELETE FROM [monitoring].[CollectionLog]
    WHERE CollectionTime < DATEADD(DAY, -@RetentionDays_Logs, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from monitoring.CollectionLog';

    -- Purge old history
    DELETE FROM [history].[KPISnapshotHistory]
    WHERE ArchivedDate < DATEADD(DAY, -@RetentionDays_History, GETDATE());
    SET @DeletedRows = @@ROWCOUNT;
    SET @TotalDeleted = @TotalDeleted + @DeletedRows;
    PRINT 'Purged ' + CAST(@DeletedRows AS VARCHAR) + ' from history.KPISnapshotHistory';

    PRINT '';
    PRINT 'Data purge completed. Total rows deleted: ' + CAST(@TotalDeleted AS VARCHAR);
END
GO

PRINT '  Created monitoring.usp_PurgeOldData'

-- Check and generate alerts
IF OBJECT_ID('monitoring.usp_CheckThresholdsAndAlert', 'P') IS NOT NULL
    DROP PROCEDURE [monitoring].[usp_CheckThresholdsAndAlert]
GO

CREATE PROCEDURE [monitoring].[usp_CheckThresholdsAndAlert]
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @AlertsGenerated INT = 0;

    -- Get latest KPI for each server
    ;WITH LatestKPI AS (
        SELECT
            k.*,
            ROW_NUMBER() OVER (PARTITION BY k.ServerID_Formatted ORDER BY k.SnapshotTime DESC) AS RowNum
        FROM [kpi].[KPISnapshot] k
        WHERE k.SnapshotTime > DATEADD(MINUTE, -15, GETDATE())
    )
    -- Check CPU threshold
    INSERT INTO [monitoring].[Alerts] (ServerID_Formatted, AlertType, Severity, MetricName, MetricValue, ThresholdValue, Message)
    SELECT
        k.ServerID_Formatted,
        'CPU',
        CASE
            WHEN k.CPU_Percent >= t_crit.CriticalThreshold THEN 'Critical'
            ELSE 'Warning'
        END,
        'CPU_Percent',
        CAST(k.CPU_Percent AS NVARCHAR(50)),
        CASE
            WHEN k.CPU_Percent >= t_crit.CriticalThreshold THEN CAST(t_crit.CriticalThreshold AS NVARCHAR(50))
            ELSE CAST(t_warn.WarningThreshold AS NVARCHAR(50))
        END,
        'CPU utilization at ' + CAST(k.CPU_Percent AS NVARCHAR(10)) + '%'
    FROM LatestKPI k
    CROSS JOIN [monitoring].[AlertThresholds] t_warn
    CROSS JOIN [monitoring].[AlertThresholds] t_crit
    WHERE k.RowNum = 1
    AND t_warn.MetricName = 'CPU_Percent'
    AND t_crit.MetricName = 'CPU_Percent'
    AND k.CPU_Percent >= t_warn.WarningThreshold
    AND NOT EXISTS (
        SELECT 1 FROM [monitoring].[Alerts] a
        WHERE a.ServerID_Formatted = k.ServerID_Formatted
        AND a.AlertType = 'CPU'
        AND a.IsResolved = 0
        AND a.AlertTime > DATEADD(HOUR, -1, GETDATE())
    );

    SET @AlertsGenerated = @AlertsGenerated + @@ROWCOUNT;

    -- Check Memory PLE threshold
    ;WITH LatestKPI AS (
        SELECT
            k.*,
            ROW_NUMBER() OVER (PARTITION BY k.ServerID_Formatted ORDER BY k.SnapshotTime DESC) AS RowNum
        FROM [kpi].[KPISnapshot] k
        WHERE k.SnapshotTime > DATEADD(MINUTE, -15, GETDATE())
    )
    INSERT INTO [monitoring].[Alerts] (ServerID_Formatted, AlertType, Severity, MetricName, MetricValue, ThresholdValue, Message)
    SELECT
        k.ServerID_Formatted,
        'Memory',
        CASE
            WHEN k.Memory_Page_Life_Expectancy <= t.CriticalThreshold THEN 'Critical'
            ELSE 'Warning'
        END,
        'Memory_Page_Life_Expectancy',
        CAST(k.Memory_Page_Life_Expectancy AS NVARCHAR(50)),
        CASE
            WHEN k.Memory_Page_Life_Expectancy <= t.CriticalThreshold THEN CAST(t.CriticalThreshold AS NVARCHAR(50))
            ELSE CAST(t.WarningThreshold AS NVARCHAR(50))
        END,
        'Page Life Expectancy at ' + CAST(k.Memory_Page_Life_Expectancy AS NVARCHAR(10)) + ' seconds'
    FROM LatestKPI k
    CROSS JOIN [monitoring].[AlertThresholds] t
    WHERE k.RowNum = 1
    AND t.MetricName = 'Memory_Page_Life_Expectancy'
    AND k.Memory_Page_Life_Expectancy <= t.WarningThreshold
    AND NOT EXISTS (
        SELECT 1 FROM [monitoring].[Alerts] a
        WHERE a.ServerID_Formatted = k.ServerID_Formatted
        AND a.AlertType = 'Memory'
        AND a.IsResolved = 0
        AND a.AlertTime > DATEADD(HOUR, -1, GETDATE())
    );

    SET @AlertsGenerated = @AlertsGenerated + @@ROWCOUNT;

    -- Auto-resolve old alerts if conditions are normal
    UPDATE [monitoring].[Alerts]
    SET IsResolved = 1,
        ResolvedDate = GETDATE()
    WHERE IsResolved = 0
    AND AlertTime < DATEADD(HOUR, -4, GETDATE());

    SELECT @AlertsGenerated AS AlertsGenerated;
END
GO

PRINT '  Created monitoring.usp_CheckThresholdsAndAlert'
GO

-- ============================================================================
-- SECTION 5: DASHBOARD PROCEDURES
-- ============================================================================
PRINT ''
PRINT 'Creating dashboard procedures...'

-- Get overall health summary
IF OBJECT_ID('monitoring.usp_GetHealthSummary', 'P') IS NOT NULL
    DROP PROCEDURE [monitoring].[usp_GetHealthSummary]
GO

CREATE PROCEDURE [monitoring].[usp_GetHealthSummary]
AS
BEGIN
    SET NOCOUNT ON;

    -- Server counts
    SELECT
        COUNT(*) AS TotalServers,
        SUM(CASE WHEN IsActive = 1 THEN 1 ELSE 0 END) AS ActiveServers,
        SUM(CASE WHEN IsMonitored = 1 THEN 1 ELSE 0 END) AS MonitoredServers,
        SUM(CASE WHEN LastCollectionStatus = 'Success' AND LastCollectionTime > DATEADD(MINUTE, -15, GETDATE()) THEN 1 ELSE 0 END) AS HealthyServers
    FROM [config].[ServerInventory];

    -- Alert counts
    SELECT
        SUM(CASE WHEN Severity = 'Critical' AND IsResolved = 0 THEN 1 ELSE 0 END) AS CriticalAlerts,
        SUM(CASE WHEN Severity = 'Warning' AND IsResolved = 0 THEN 1 ELSE 0 END) AS WarningAlerts,
        SUM(CASE WHEN IsResolved = 0 THEN 1 ELSE 0 END) AS TotalActiveAlerts
    FROM [monitoring].[Alerts];

    -- Recent collection stats
    SELECT
        COUNT(*) AS CollectionsLast24h,
        SUM(CASE WHEN Status = 'Success' THEN 1 ELSE 0 END) AS SuccessfulCollections,
        SUM(CASE WHEN Status = 'Failed' THEN 1 ELSE 0 END) AS FailedCollections,
        AVG(DurationMs) AS AvgDurationMs
    FROM [monitoring].[CollectionLog]
    WHERE CollectionTime > DATEADD(HOUR, -24, GETDATE());
END
GO

PRINT '  Created monitoring.usp_GetHealthSummary'
GO

-- ============================================================================
-- DEPLOYMENT SUMMARY
-- ============================================================================
PRINT ''
PRINT '============================================================'
PRINT 'STORED PROCEDURES DEPLOYMENT SUMMARY'
PRINT '============================================================'
PRINT ''

SELECT
    SCHEMA_NAME(schema_id) + '.' + name AS ProcedureName,
    create_date AS CreatedDate,
    modify_date AS ModifiedDate
FROM sys.procedures
WHERE is_ms_shipped = 0
ORDER BY SCHEMA_NAME(schema_id), name
GO

PRINT ''
PRINT 'Stored procedures deployment completed successfully!'
PRINT '============================================================'
GO
