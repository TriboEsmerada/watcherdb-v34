-- ============================================================================
-- WATCHERDB INTELLIGENCE V2 - SQL SERVER AGENT JOBS
-- ============================================================================
-- SQL Agent Jobs para coleta automática de KPIs
--
-- COMPONENTES:
--   - 1 Job de coleta (executa a cada 5 minutos)
--   - 1 Job de limpeza histórico (executa diariamente)
--
-- AUTOR: WatcherDB Team
-- DATA: 2025-11-27
-- VERSÃO: 1.0.0
-- ============================================================================

USE [msdb];
GO

PRINT '============================================================================';
PRINT 'WATCHERDB INTELLIGENCE V2 - SQL AGENT JOBS';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
GO

-- ============================================================================
-- PRÉ-REQUISITOS
-- ============================================================================

-- Verificar se SQL Agent está rodando
IF (SELECT CASE WHEN dbo.fn_sysjobserverisrunning(DEFAULT) = 1 THEN 'Running' ELSE 'Stopped' END) = 'Stopped'
BEGIN
    PRINT '⚠️ AVISO: SQL Server Agent não está rodando!';
    PRINT '  Execute: NET START SQLSERVERAGENT';
    PRINT '';
END
ELSE
BEGIN
    PRINT '✓ SQL Server Agent está rodando';
    PRINT '';
END
GO

-- ============================================================================
-- JOB 1: COLETA DE KPIs (A CADA 5 MINUTOS)
-- ============================================================================

PRINT '';
PRINT '-- [1/2] Criando job: WatcherDB_Collect_KPIs...';
PRINT '';

-- Remover job se existir
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = 'WatcherDB_Collect_KPIs')
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = 'WatcherDB_Collect_KPIs';
    PRINT '  [INFO] Job existente removido';
END
GO

-- Criar job
DECLARE @jobId BINARY(16);

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Collect_KPIs',
    @enabled = 1,
    @notify_level_eventlog = 2, -- Erro
    @notify_level_email = 0,
    @notify_level_netsend = 0,
    @notify_level_page = 0,
    @delete_level = 0,
    @description = N'Coleta automática de KPIs SQL Server para WatcherDB Intelligence V2. Executa a cada 5 minutos.',
    @category_name = N'Database Maintenance',
    @owner_login_name = N'sa',
    @job_id = @jobId OUTPUT;

PRINT '  [OK] Job criado';
GO

-- Adicionar step 1: Executar coleta
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Collect_KPIs',
    @step_name = N'Coletar todos os KPIs',
    @step_id = 1,
    @cmdexec_success_code = 0,
    @on_success_action = 1, -- Quit with success
    @on_fail_action = 2,     -- Quit with failure
    @retry_attempts = 0,
    @retry_interval = 0,
    @os_run_priority = 0,
    @subsystem = N'TSQL',
    @command = N'EXEC [WatcherDB_Intelligence_V2].dbo.usp_Collect_All_KPIs @Debug = 0;',
    @database_name = N'WatcherDB_Intelligence_V2',
    @flags = 0;

PRINT '  [OK] Step de coleta adicionado';
GO

-- Adicionar schedule: A cada 5 minutos
EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Every_5_Minutes',
    @enabled = 1,
    @freq_type = 4,                 -- Daily
    @freq_interval = 1,             -- Every day
    @freq_subday_type = 4,          -- Minutes
    @freq_subday_interval = 5,      -- Every 5 minutes
    @freq_relative_interval = 0,
    @freq_recurrence_factor = 0,
    @active_start_date = 20251127,  -- Today
    @active_end_date = 99991231,    -- No end date
    @active_start_time = 0,         -- 00:00:00
    @active_end_time = 235959;      -- 23:59:59

PRINT '  [OK] Schedule criado (a cada 5 minutos)';
GO

-- Anexar schedule ao job
EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'WatcherDB_Collect_KPIs',
    @schedule_name = N'Every_5_Minutes';

PRINT '  [OK] Schedule anexado ao job';
GO

-- Adicionar job ao servidor local
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Collect_KPIs',
    @server_name = N'(local)';

PRINT '  [OK] Job adicionado ao servidor';
PRINT '';
GO

-- ============================================================================
-- JOB 2: LIMPEZA DE HISTÓRICO (DIÁRIO À MEIA-NOITE)
-- ============================================================================

PRINT '';
PRINT '-- [2/2] Criando job: WatcherDB_Purge_History...';
PRINT '';

-- Remover job se existir
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = 'WatcherDB_Purge_History')
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = 'WatcherDB_Purge_History';
    PRINT '  [INFO] Job existente removido';
END
GO

-- Criar job
DECLARE @jobId2 BINARY(16);

EXEC msdb.dbo.sp_add_job
    @job_name = N'WatcherDB_Purge_History',
    @enabled = 1,
    @notify_level_eventlog = 2, -- Erro
    @notify_level_email = 0,
    @notify_level_netsend = 0,
    @notify_level_page = 0,
    @delete_level = 0,
    @description = N'Limpeza de dados históricos antigos (> 365 dias) das tabelas HIST. Executa diariamente à meia-noite.',
    @category_name = N'Database Maintenance',
    @owner_login_name = N'sa',
    @job_id = @jobId2 OUTPUT;

PRINT '  [OK] Job criado';
GO

-- Adicionar step 1: Limpar histórico
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'WatcherDB_Purge_History',
    @step_name = N'Limpar dados antigos (> 365 dias)',
    @step_id = 1,
    @cmdexec_success_code = 0,
    @on_success_action = 1, -- Quit with success
    @on_fail_action = 2,     -- Quit with failure
    @retry_attempts = 2,
    @retry_interval = 5,
    @os_run_priority = 0,
    @subsystem = N'TSQL',
    @command = N'
-- Limpar histórico de DB Availability (> 365 dias)
DELETE FROM [WatcherDB_Intelligence_V2].dbo.KPI_MSSQL_DB_AVAILABILITY_HIST
WHERE Update_TS < DATEADD(DAY, -365, GETDATE());
PRINT ''DB Availability: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';

-- Limpar histórico de Disk Usage (> 365 dias)
DELETE FROM [WatcherDB_Intelligence_V2].dbo.KPI_MSSQL_DISK_USAGE_HIST
WHERE Update_TS < DATEADD(DAY, -365, GETDATE());
PRINT ''Disk Usage: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';

-- Limpar histórico de TLog Usage (> 365 dias)
DELETE FROM [WatcherDB_Intelligence_V2].dbo.KPI_MSSQL_TLOG_USAGE_HIST
WHERE Update_TS < DATEADD(DAY, -365, GETDATE());
PRINT ''TLog Usage: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';

-- Limpar histórico de CMDB (> 365 dias)
DELETE FROM [WatcherDB_Intelligence_V2].dbo.CMDB_MSSQL_DATABASES_HIST
WHERE UpdatedAt < DATEADD(DAY, -365, GETDATE());
PRINT ''CMDB: '' + CAST(@@ROWCOUNT AS VARCHAR(10)) + '' linhas removidas'';
',
    @database_name = N'WatcherDB_Intelligence_V2',
    @flags = 0;

PRINT '  [OK] Step de limpeza adicionado';
GO

-- Adicionar schedule: Diário à meia-noite
EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Daily_Midnight',
    @enabled = 1,
    @freq_type = 4,                 -- Daily
    @freq_interval = 1,             -- Every day
    @freq_subday_type = 1,          -- At specified time
    @freq_subday_interval = 0,
    @freq_relative_interval = 0,
    @freq_recurrence_factor = 0,
    @active_start_date = 20251127,  -- Today
    @active_end_date = 99991231,    -- No end date
    @active_start_time = 0,         -- 00:00:00 (midnight)
    @active_end_time = 235959;      -- 23:59:59

PRINT '  [OK] Schedule criado (diário à meia-noite)';
GO

-- Anexar schedule ao job
EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'WatcherDB_Purge_History',
    @schedule_name = N'Daily_Midnight';

PRINT '  [OK] Schedule anexado ao job';
GO

-- Adicionar job ao servidor local
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'WatcherDB_Purge_History',
    @server_name = N'(local)';

PRINT '  [OK] Job adicionado ao servidor';
PRINT '';
GO

-- ============================================================================
-- LISTAR JOBS CRIADOS
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT 'JOBS CRIADOS COM SUCESSO';
PRINT '============================================================================';
PRINT '';

SELECT
    j.name AS Job_Name,
    CASE j.enabled WHEN 1 THEN 'Enabled' ELSE 'Disabled' END AS Status,
    s.name AS Schedule_Name,
    CASE s.freq_type
        WHEN 4 THEN 'Daily'
        ELSE 'Other'
    END AS Frequency,
    CASE s.freq_subday_type
        WHEN 1 THEN 'At specified time'
        WHEN 4 THEN 'Every ' + CAST(s.freq_subday_interval AS VARCHAR(10)) + ' minutes'
        ELSE 'Other'
    END AS Subday_Frequency,
    STUFF(STUFF(RIGHT('000000' + CAST(s.active_start_time AS VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':') AS Start_Time,
    CASE
        WHEN jh.run_date IS NOT NULL THEN
            CONVERT(VARCHAR(23),
                CAST(CAST(jh.run_date AS VARCHAR(8)) + ' ' +
                STUFF(STUFF(RIGHT('000000' + CAST(jh.run_time AS VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':')
                AS DATETIME2), 121)
        ELSE 'Never'
    END AS Last_Run,
    CASE
        WHEN jh.run_status = 1 THEN 'Success'
        WHEN jh.run_status = 0 THEN 'Failed'
        ELSE 'Other'
    END AS Last_Run_Status
FROM msdb.dbo.sysjobs j
LEFT JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id
LEFT JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id
LEFT JOIN (
    SELECT job_id, run_date, run_time, run_status,
           ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY run_date DESC, run_time DESC) AS rn
    FROM msdb.dbo.sysjobhistory
    WHERE step_id = 0
) jh ON j.job_id = jh.job_id AND jh.rn = 1
WHERE j.name LIKE 'WatcherDB%'
ORDER BY j.name;

PRINT '';
PRINT '============================================================================';
PRINT 'COMANDOS ÚTEIS';
PRINT '============================================================================';
PRINT '';
PRINT '-- Executar job manualmente:';
PRINT '   EXEC msdb.dbo.sp_start_job @job_name = ''WatcherDB_Collect_KPIs'';';
PRINT '';
PRINT '-- Verificar status do job:';
PRINT '   EXEC msdb.dbo.sp_help_job @job_name = ''WatcherDB_Collect_KPIs'';';
PRINT '';
PRINT '-- Ver histórico de execuções:';
PRINT '   SELECT TOP 20';
PRINT '       j.name AS Job_Name,';
PRINT '       CONVERT(VARCHAR(23), CAST(CAST(h.run_date AS VARCHAR(8)) + '' '' +';
PRINT '           STUFF(STUFF(RIGHT(''000000'' + CAST(h.run_time AS VARCHAR(6)), 6), 5, 0, '':''), 3, 0, '':'')';
PRINT '           AS DATETIME2), 121) AS Run_DateTime,';
PRINT '       CASE h.run_status';
PRINT '           WHEN 0 THEN ''Failed''';
PRINT '           WHEN 1 THEN ''Succeeded''';
PRINT '           WHEN 2 THEN ''Retry''';
PRINT '           WHEN 3 THEN ''Canceled''';
PRINT '       END AS Status,';
PRINT '       h.run_duration AS Duration_Sec,';
PRINT '       h.message';
PRINT '   FROM msdb.dbo.sysjobs j';
PRINT '   INNER JOIN msdb.dbo.sysjobhistory h ON j.job_id = h.job_id';
PRINT '   WHERE j.name LIKE ''WatcherDB%''';
PRINT '     AND h.step_id = 0';
PRINT '   ORDER BY h.run_date DESC, h.run_time DESC;';
PRINT '';
PRINT '-- Desabilitar job:';
PRINT '   EXEC msdb.dbo.sp_update_job @job_name = ''WatcherDB_Collect_KPIs'', @enabled = 0;';
PRINT '';
PRINT '-- Habilitar job:';
PRINT '   EXEC msdb.dbo.sp_update_job @job_name = ''WatcherDB_Collect_KPIs'', @enabled = 1;';
PRINT '';
PRINT '-- Remover job:';
PRINT '   EXEC msdb.dbo.sp_delete_job @job_name = ''WatcherDB_Collect_KPIs'';';
PRINT '';
PRINT '============================================================================';
PRINT 'TESTE IMEDIATO';
PRINT '============================================================================';
PRINT '';
PRINT '-- Executar coleta AGORA (teste manual):';
PRINT '   USE [WatcherDB_Intelligence_V2];';
PRINT '   EXEC dbo.usp_Collect_All_KPIs @Debug = 1;';
PRINT '';
PRINT '-- Verificar dados coletados:';
PRINT '   SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;';
PRINT '   SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;';
PRINT '   SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW;';
PRINT '';
PRINT '-- Executar job via SQL Agent:';
PRINT '   EXEC msdb.dbo.sp_start_job @job_name = ''WatcherDB_Collect_KPIs'';';
PRINT '';
PRINT '============================================================================';
PRINT 'Concluído em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '============================================================================';
GO
