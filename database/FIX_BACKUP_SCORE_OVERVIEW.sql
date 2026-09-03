/*
===============================================================================
FIX: Backup Score no Overview Dashboard
===============================================================================
PROBLEMA: A procedure usp_refresh_overview_instance consultava a tabela
          KPI_MSSQL_BACKUP_STATUS_STG que esta VAZIA (nunca populada).
          Resultado: Backup_Score = 100 para todas as instancias (falso positivo).

SOLUCAO:  Usar KPI_MSSQL_BACKUPS_STG (tabela real com 1000+ registos).
          Logica de overdue derivada de Backup_Type e Hours_Since_Backup:
          - Full Backup (D) overdue: Hours_Since_Backup > 48h
          - Log Backup (L) overdue: Hours_Since_Backup > 24h

DATA: 2026-02-14
===============================================================================
*/

USE [WatcherDB_Intelligence];
GO

-- =============================================================================
-- PASSO 1: ALTER PROCEDURE usp_refresh_overview_instance
-- =============================================================================
PRINT 'Alterando usp_refresh_overview_instance para usar KPI_MSSQL_BACKUPS_STG...';
GO

ALTER PROCEDURE dbo.usp_refresh_overview_instance @Instance VARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Now DATETIME2 = GETDATE(), @Env VARCHAR(20), @LastCollection DATETIME2;
    DECLARE @IsOnline BIT = 0, @DbTotal INT = 0, @DbOnline INT = 0, @DbOffline INT = 0;
    DECLARE @BlockedSessions INT = 0, @BlockedUsers INT = 0, @LongLocks INT = 0, @ActiveProc INT = 0;
    DECLARE @TLogCrit INT = 0, @TLogWarn INT = 0, @TLogMax DECIMAL(5,2) = 0;
    DECLARE @FGCrit INT = 0, @FGWarn INT = 0, @FGMax DECIMAL(5,2) = 0;
    DECLARE @DiskCrit INT = 0, @DiskWarn INT = 0, @DiskMinFree DECIMAL(18,2) = NULL;
    DECLARE @BkpFullOverdue INT = 0, @BkpLogOverdue INT = 0;
    DECLARE @HasAO BIT = 0, @AOHealthy INT = 0, @AOUnhealthy INT = 0;
    DECLARE @SvcRunning INT = 0, @SvcStopped INT = 0;
    DECLARE @CPUCrit BIT = 0, @CPUPct DECIMAL(5,2) = NULL, @CPUHighCount INT = 0;
    DECLARE @MemCrit BIT = 0, @MemPct DECIMAL(5,2) = NULL, @MemAvailMB INT = NULL;
    DECLARE @Problems NVARCHAR(1000) = N'', @ProblemCount INT = 0;
    DECLARE @AvailScore DECIMAL(5,2) = 100.00, @PerfScore DECIMAL(5,2) = 100.00;
    DECLARE @SpaceScore DECIMAL(5,2) = 100.00, @BkpScore DECIMAL(5,2) = 100.00;
    DECLARE @HealthScore DECIMAL(5,2), @HealthStatus VARCHAR(20) = 'OK';

    SELECT @Env = ISNULL(Env, 'Undefined') FROM dbo.KPI_MSSQL_INST_ENVS WHERE Instance = @Instance;
    IF @Env IS NULL SET @Env = 'Undefined';

    -- Is_Available
    SELECT @LastCollection = MAX(Update_TS) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    SELECT @IsOnline = CASE WHEN Is_Available = 1 THEN 1 ELSE 0 END FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @IsOnline IS NULL SET @IsOnline = 0;

    -- Databases
    SELECT @DbTotal = COUNT(*),
           @DbOnline = SUM(CASE WHEN [State] = 'ONLINE' OR Is_Available = 1 THEN 1 ELSE 0 END),
           @DbOffline = SUM(CASE WHEN [State] <> 'ONLINE' AND ISNULL(Is_Available, 1) = 0 THEN 1 ELSE 0 END)
    FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @DbOffline > 0 BEGIN SET @Problems = @Problems + N'DB Offline: ' + CAST(@DbOffline AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @DbOffline; END

    -- Blocked sessions
    SELECT @BlockedSessions = COUNT(*) FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK) WHERE Instance = @Instance AND Wait_Time_Sec > 0;
    IF @BlockedSessions > 0 BEGIN SET @Problems = @Problems + N'Blocked: ' + CAST(@BlockedSessions AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + 1; END

    -- Blocked users
    SELECT @BlockedUsers = ISNULL(SUM(Blocked_Count), 0) FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) WHERE Instance = @Instance;

    -- Long locks
    SELECT @LongLocks = COUNT(*) FROM dbo.KPI_MSSQL_LONG_LOCKS_STG WITH (NOLOCK) WHERE Instance = @Instance AND Duration_Sec >= 30;
    IF @LongLocks > 0 BEGIN SET @Problems = @Problems + N'Long Locks: ' + CAST(@LongLocks AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @LongLocks; END

    -- Processes
    SELECT @ActiveProc = COUNT(*) FROM dbo.KPI_MSSQL_PROCESSES_STG WITH (NOLOCK) WHERE Instance = @Instance;

    -- TLog
    SELECT @TLogCrit = SUM(CASE WHEN Percent_Used >= 90 THEN 1 ELSE 0 END), @TLogWarn = SUM(CASE WHEN Percent_Used >= 80 AND Percent_Used < 90 THEN 1 ELSE 0 END), @TLogMax = MAX(ISNULL(Percent_Used, 0)) FROM dbo.KPI_MSSQL_TLOG_USAGE_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @TLogCrit > 0 BEGIN SET @Problems = @Problems + N'TLog Crit: ' + CAST(@TLogCrit AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @TLogCrit; END

    -- Filegroups
    SELECT @FGCrit = SUM(CASE WHEN Percent_Used >= 90 THEN 1 ELSE 0 END), @FGWarn = SUM(CASE WHEN Percent_Used >= 80 AND Percent_Used < 90 THEN 1 ELSE 0 END), @FGMax = MAX(ISNULL(Percent_Used, 0)) FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @FGCrit > 0 BEGIN SET @Problems = @Problems + N'FG Crit: ' + CAST(@FGCrit AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @FGCrit; END

    -- Disk
    SELECT @DiskCrit = SUM(CASE WHEN Free_MB / 1024.0 < 10 THEN 1 ELSE 0 END), @DiskWarn = SUM(CASE WHEN Free_MB / 1024.0 >= 10 AND Free_MB / 1024.0 < 50 THEN 1 ELSE 0 END), @DiskMinFree = MIN(Free_MB / 1024.0) FROM dbo.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @DiskCrit > 0 BEGIN SET @Problems = @Problems + N'Disk Crit: ' + CAST(@DiskCrit AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @DiskCrit; END

    -- Backups overdue a partir da tabela real KPI_MSSQL_BACKUPS_STG (Full > 48h, Log > 24h)
    SELECT @BkpFullOverdue = ISNULL(SUM(CASE WHEN Backup_Type = 'D' AND Hours_Since_Backup > 48 THEN 1 ELSE 0 END), 0), @BkpLogOverdue = ISNULL(SUM(CASE WHEN Backup_Type = 'L' AND Hours_Since_Backup > 24 THEN 1 ELSE 0 END), 0) FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @BkpFullOverdue > 0 BEGIN SET @Problems = @Problems + N'Bkp Overdue: ' + CAST(@BkpFullOverdue AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @BkpFullOverdue; END

    -- AlwaysOn
    IF EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE Instance = @Instance)
    BEGIN
        SET @HasAO = 1;
        SELECT @AOHealthy = SUM(CASE WHEN Pri_Synch_Health = 'HEALTHY' AND (Sec_Synch_Health IS NULL OR Sec_Synch_Health = 'HEALTHY') THEN 1 ELSE 0 END), @AOUnhealthy = SUM(CASE WHEN Pri_Synch_Health <> 'HEALTHY' OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> 'HEALTHY') THEN 1 ELSE 0 END) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE Instance = @Instance;
        IF @AOUnhealthy > 0 BEGIN SET @Problems = @Problems + N'AG Unhealthy: ' + CAST(@AOUnhealthy AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @AOUnhealthy; END
    END

    -- Services
    SELECT @SvcRunning = SUM(CASE WHEN Service_State = 'Running' THEN 1 ELSE 0 END), @SvcStopped = SUM(CASE WHEN Service_State <> 'Running' THEN 1 ELSE 0 END) FROM dbo.KPI_MSSQL_SERVICE_STATUS_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @SvcStopped > 0 BEGIN SET @Problems = @Problems + N'Svc Stopped: ' + CAST(@SvcStopped AS VARCHAR) + N'; '; SET @ProblemCount = @ProblemCount + @SvcStopped; END

    -- CPU
    SELECT @CPUHighCount = COUNT(*) FROM dbo.KPI_OS_CPU_HIST WITH (NOLOCK) WHERE Instance = @Instance AND Processor_Pct >= 95 AND Update_TS >= DATEADD(MINUTE, -2, @Now);
    IF @CPUHighCount >= 2 BEGIN SET @CPUCrit = 1; SELECT TOP 1 @CPUPct = Processor_Pct FROM dbo.KPI_OS_CPU_HIST WITH (NOLOCK) WHERE Instance = @Instance ORDER BY Update_TS DESC; SET @Problems = @Problems + N'CPU Critical; '; SET @ProblemCount = @ProblemCount + 1; END
    ELSE SELECT TOP 1 @CPUPct = Processor_Pct FROM dbo.KPI_OS_CPU_STG WITH (NOLOCK) WHERE Instance = @Instance;

    -- Memory
    SELECT TOP 1 @MemPct = Percent_Used, @MemAvailMB = CAST(Available_MB AS INT), @MemCrit = CASE WHEN Percent_Used >= 99 THEN 1 WHEN Available_MB < 500 THEN 1 WHEN Page_Reads_Sec > 100 THEN 1 ELSE 0 END FROM dbo.KPI_OS_MEMORY_STG WITH (NOLOCK) WHERE Instance = @Instance;
    IF @MemCrit = 1 BEGIN SET @Problems = @Problems + N'Memory Critical; '; SET @ProblemCount = @ProblemCount + 1; END

    -- Scores
    IF @IsOnline = 0 SET @AvailScore = 0 ELSE IF @DbTotal > 0 SET @AvailScore = (@DbOnline * 100.0) / @DbTotal;
    IF @BlockedSessions > 10 SET @PerfScore = @PerfScore - 40 ELSE IF @BlockedSessions > 0 SET @PerfScore = @PerfScore - (@BlockedSessions * 4);
    IF @LongLocks > 5 SET @PerfScore = @PerfScore - 30 ELSE IF @LongLocks > 0 SET @PerfScore = @PerfScore - (@LongLocks * 6);
    IF @CPUCrit = 1 SET @PerfScore = @PerfScore - 20; IF @MemCrit = 1 SET @PerfScore = @PerfScore - 20; IF @PerfScore < 0 SET @PerfScore = 0;
    IF @TLogCrit > 0 SET @SpaceScore = @SpaceScore - (@TLogCrit * 15); IF @TLogWarn > 0 SET @SpaceScore = @SpaceScore - (@TLogWarn * 5);
    IF @FGCrit > 0 SET @SpaceScore = @SpaceScore - (@FGCrit * 15); IF @FGWarn > 0 SET @SpaceScore = @SpaceScore - (@FGWarn * 5);
    IF @DiskCrit > 0 SET @SpaceScore = @SpaceScore - (@DiskCrit * 20); IF @DiskWarn > 0 SET @SpaceScore = @SpaceScore - (@DiskWarn * 10); IF @SpaceScore < 0 SET @SpaceScore = 0;
    IF @BkpFullOverdue > 0 SET @BkpScore = @BkpScore - (@BkpFullOverdue * 20); IF @BkpLogOverdue > 0 SET @BkpScore = @BkpScore - (@BkpLogOverdue * 5); IF @BkpScore < 0 SET @BkpScore = 0;
    SET @HealthScore = (@AvailScore + @PerfScore + @SpaceScore + @BkpScore) / 4;
    IF @IsOnline = 0 SET @HealthStatus = 'OFFLINE' ELSE IF @HealthScore < 50 SET @HealthStatus = 'CRITICAL' ELSE IF @HealthScore < 75 SET @HealthStatus = 'WARNING' ELSE SET @HealthStatus = 'OK';
    IF LEN(@Problems) > 2 SET @Problems = LEFT(@Problems, LEN(@Problems) - 2); IF @Problems = N'' SET @Problems = NULL;

    MERGE dbo.OVERVIEW_INSTANCE_SNAPSHOT AS t USING (SELECT @Instance AS Instance) AS s ON t.Instance = s.Instance
    WHEN MATCHED THEN UPDATE SET Env=@Env,Last_Refresh=@Now,Last_Collection=@LastCollection,Is_Online=@IsOnline,Databases_Total=ISNULL(@DbTotal,0),Databases_Online=ISNULL(@DbOnline,0),Databases_Offline=ISNULL(@DbOffline,0),Blocked_Sessions=ISNULL(@BlockedSessions,0),Blocked_Users=ISNULL(@BlockedUsers,0),Long_Locks_Count=ISNULL(@LongLocks,0),Active_Processes=ISNULL(@ActiveProc,0),TLog_Critical_Count=ISNULL(@TLogCrit,0),TLog_Warning_Count=ISNULL(@TLogWarn,0),TLog_Max_Percent=ISNULL(@TLogMax,0),FG_Critical_Count=ISNULL(@FGCrit,0),FG_Warning_Count=ISNULL(@FGWarn,0),FG_Max_Percent=ISNULL(@FGMax,0),Disk_Critical_Count=ISNULL(@DiskCrit,0),Disk_Warning_Count=ISNULL(@DiskWarn,0),Disk_Min_Free_GB=@DiskMinFree,Backup_Full_Overdue=ISNULL(@BkpFullOverdue,0),Backup_Log_Overdue=ISNULL(@BkpLogOverdue,0),Has_AlwaysOn=@HasAO,AlwaysOn_Healthy=ISNULL(@AOHealthy,0),AlwaysOn_UnHealthy=ISNULL(@AOUnhealthy,0),Services_Running=ISNULL(@SvcRunning,0),Services_Stopped=ISNULL(@SvcStopped,0),OS_CPU_Critical=@CPUCrit,OS_CPU_Percent=@CPUPct,OS_Memory_Critical=@MemCrit,OS_Memory_Percent=@MemPct,OS_Available_MB=@MemAvailMB,Health_Score=@HealthScore,Health_Status=@HealthStatus,Availability_Score=@AvailScore,Performance_Score=@PerfScore,Space_Score=@SpaceScore,Backup_Score=@BkpScore,Active_Problems=@ProblemCount,Problem_Summary=@Problems
    WHEN NOT MATCHED THEN INSERT (Instance,Env,Last_Refresh,Last_Collection,Is_Online,Databases_Total,Databases_Online,Databases_Offline,Blocked_Sessions,Blocked_Users,Long_Locks_Count,Active_Processes,TLog_Critical_Count,TLog_Warning_Count,TLog_Max_Percent,FG_Critical_Count,FG_Warning_Count,FG_Max_Percent,Disk_Critical_Count,Disk_Warning_Count,Disk_Min_Free_GB,Backup_Full_Overdue,Backup_Log_Overdue,Has_AlwaysOn,AlwaysOn_Healthy,AlwaysOn_UnHealthy,Services_Running,Services_Stopped,OS_CPU_Critical,OS_CPU_Percent,OS_Memory_Critical,OS_Memory_Percent,OS_Available_MB,Health_Score,Health_Status,Availability_Score,Performance_Score,Space_Score,Backup_Score,Active_Problems,Problem_Summary) VALUES (@Instance,@Env,@Now,@LastCollection,@IsOnline,ISNULL(@DbTotal,0),ISNULL(@DbOnline,0),ISNULL(@DbOffline,0),ISNULL(@BlockedSessions,0),ISNULL(@BlockedUsers,0),ISNULL(@LongLocks,0),ISNULL(@ActiveProc,0),ISNULL(@TLogCrit,0),ISNULL(@TLogWarn,0),ISNULL(@TLogMax,0),ISNULL(@FGCrit,0),ISNULL(@FGWarn,0),ISNULL(@FGMax,0),ISNULL(@DiskCrit,0),ISNULL(@DiskWarn,0),@DiskMinFree,ISNULL(@BkpFullOverdue,0),ISNULL(@BkpLogOverdue,0),@HasAO,ISNULL(@AOHealthy,0),ISNULL(@AOUnhealthy,0),ISNULL(@SvcRunning,0),ISNULL(@SvcStopped,0),@CPUCrit,@CPUPct,@MemCrit,@MemPct,@MemAvailMB,@HealthScore,@HealthStatus,@AvailScore,@PerfScore,@SpaceScore,@BkpScore,@ProblemCount,@Problems);
END
GO
PRINT '  [OK] Procedure usp_refresh_overview_instance alterada - agora usa KPI_MSSQL_BACKUPS_STG';
GO

-- =============================================================================
-- PASSO 2: Executar refresh de todas as instancias
-- =============================================================================
PRINT '';
PRINT 'Executando refresh do overview para todas as instancias...';
GO
EXEC dbo.usp_refresh_overview_all;
GO
PRINT '  [OK] Refresh completo';
GO

-- =============================================================================
-- PASSO 3: Verificar resultados
-- =============================================================================
PRINT '';
PRINT 'Verificando scores de backup...';
PRINT '';
GO

-- Mostrar instancias com backups overdue (devem aparecer agora)
SELECT
    Instance,
    Backup_Full_Overdue,
    Backup_Log_Overdue,
    Backup_Score,
    Health_Score,
    Health_Status,
    Problem_Summary
FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT
ORDER BY Backup_Score ASC, Instance;
GO

-- Resumo por score
PRINT '';
PRINT 'Resumo de Backup Scores:';
SELECT
    CASE
        WHEN Backup_Score = 100 THEN '100 (Sem problemas)'
        WHEN Backup_Score >= 80 THEN '80-99 (Aviso)'
        WHEN Backup_Score >= 50 THEN '50-79 (Atencao)'
        ELSE '0-49 (Critico)'
    END AS Score_Range,
    COUNT(*) AS Instancias
FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT
GROUP BY
    CASE
        WHEN Backup_Score = 100 THEN '100 (Sem problemas)'
        WHEN Backup_Score >= 80 THEN '80-99 (Aviso)'
        WHEN Backup_Score >= 50 THEN '50-79 (Atencao)'
        ELSE '0-49 (Critico)'
    END
ORDER BY 1;
GO

-- Verificar dados na tabela real de backups (amostra)
PRINT '';
PRINT 'Dados na KPI_MSSQL_BACKUPS_STG (overdue):';
SELECT TOP 20
    Instance,
    [Database],
    Backup_Type,
    Hours_Since_Backup,
    Last_Backup_Date,
    CASE
        WHEN Backup_Type = 'D' AND Hours_Since_Backup > 48 THEN 'FULL OVERDUE'
        WHEN Backup_Type = 'L' AND Hours_Since_Backup > 24 THEN 'LOG OVERDUE'
        ELSE 'OK'
    END AS Status
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
WHERE (Backup_Type = 'D' AND Hours_Since_Backup > 48)
   OR (Backup_Type = 'L' AND Hours_Since_Backup > 24)
ORDER BY Hours_Since_Backup DESC;
GO

PRINT '';
PRINT '=============================================================================';
PRINT 'FIX COMPLETO: Backup Score agora usa KPI_MSSQL_BACKUPS_STG (tabela real)';
PRINT '=============================================================================';
GO
