-- =============================================
-- Backup Schedule Queries
-- Extrai schedules reais dos SQL Agent Jobs de backup
-- =============================================
--
-- Wave R+8 (2026-05-25) -- Smart Defaults Initiative NOTE:
-- Este ficheiro contem apenas queries para schedule detection via msdb.sysjobs
-- + sysschedules. Cobre apenas backups feitos por SQL Agent jobs nativos.
--
-- Wave R+8 ADICIONA segunda fonte: pattern detection from msdb.backupset
-- HISTORY. NAO requer nova SQL query aqui -- reutiliza dados ja obtidos por
-- `_get_backup_history` (modules/monitoring/backup_pattern_analysis.py linha 185+).
--
-- Priority chain pos-R+8:
--   1. sysjobs schedule (este ficheiro) -- cobre jobs nativos
--   2. msdb.backupset history pattern (R+8, no novo SQL aqui) -- cobre TSM/Commvault
--   3. inferred pattern (fallback) -- comportamento original
--
-- Ver: docs/architecture/SMART_DEFAULTS_PRINCIPLE.md + docs/features/BACKUP_SCHEDULE_BASED_GAP_DETECTION.md
--

-- Query principal: schedules de todos os jobs de backup
WITH BackupJobs AS (
    SELECT DISTINCT
        j.job_id,
        j.name AS job_name,
        j.enabled AS is_enabled,
        js.step_id,
        js.command,
        -- Extrair database name do comando
        CASE
            WHEN js.command LIKE '%DATABASE = %' THEN
                SUBSTRING(
                    js.command,
                    CHARINDEX('DATABASE = ', js.command) + 11,
                    CHARINDEX(',', js.command, CHARINDEX('DATABASE = ', js.command)) - CHARINDEX('DATABASE = ', js.command) - 11
                )
            WHEN js.command LIKE '%BACKUP DATABASE [[]%' THEN
                SUBSTRING(
                    js.command,
                    CHARINDEX('BACKUP DATABASE [', js.command) + 16,
                    CHARINDEX(']', js.command, CHARINDEX('BACKUP DATABASE [', js.command)) - CHARINDEX('BACKUP DATABASE [', js.command) - 16
                )
            WHEN js.command LIKE '%BACKUP LOG [[]%' THEN
                SUBSTRING(
                    js.command,
                    CHARINDEX('BACKUP LOG [', js.command) + 12,
                    CHARINDEX(']', js.command, CHARINDEX('BACKUP LOG [', js.command)) - CHARINDEX('BACKUP LOG [', js.command) - 12
                )
            ELSE NULL
        END AS database_name,
        -- Identificar tipo de backup
        CASE
            WHEN js.command LIKE '%BACKUP LOG%' THEN 'LOG'
            WHEN js.command LIKE '%DIFFERENTIAL%' OR js.command LIKE '%TYPE = DIFFERENTIAL%' THEN 'DIFF'
            WHEN js.command LIKE '%BACKUP DATABASE%' THEN 'FULL'
            ELSE 'UNKNOWN'
        END AS backup_type
    FROM msdb.dbo.sysjobs j WITH(NOLOCK)
    INNER JOIN msdb.dbo.sysjobsteps js WITH(NOLOCK) ON j.job_id = js.job_id
    WHERE (
        js.command LIKE '%BACKUP DATABASE%'
        OR js.command LIKE '%BACKUP LOG%'
    )
    AND j.enabled = 1
),
JobSchedules AS (
    SELECT
        bj.job_id,
        bj.job_name,
        bj.database_name,
        bj.backup_type,
        bj.is_enabled,
        s.schedule_id,
        s.name AS schedule_name,
        s.enabled AS schedule_enabled,
        -- Freq type: 1=Once, 4=Daily, 8=Weekly, 16=Monthly, 32=Monthly relative
        s.freq_type,
        -- Freq interval: depends on freq_type
        s.freq_interval,
        -- Subday freq: 1=At time, 2=Seconds, 4=Minutes, 8=Hours
        s.freq_subday_type,
        s.freq_subday_interval,
        -- Time format: HHMMSS (ex: 190000 = 19:00:00)
        s.active_start_time,
        s.active_end_time,
        s.active_start_date,
        s.active_end_date
    FROM BackupJobs bj
    INNER JOIN msdb.dbo.sysjobschedules js WITH(NOLOCK) ON bj.job_id = js.job_id
    INNER JOIN msdb.dbo.sysschedules s WITH(NOLOCK) ON js.schedule_id = s.schedule_id
    WHERE s.enabled = 1
)
SELECT
    database_name,
    backup_type,
    job_name,
    schedule_name,
    -- Interpretar freq_type
    CASE freq_type
        WHEN 1 THEN 'Once'
        WHEN 4 THEN 'Daily'
        WHEN 8 THEN 'Weekly'
        WHEN 16 THEN 'Monthly'
        WHEN 32 THEN 'Monthly Relative'
        WHEN 64 THEN 'When SQL Server Agent starts'
        WHEN 128 THEN 'When computer is idle'
        ELSE 'Unknown (' + CAST(freq_type AS VARCHAR) + ')'
    END AS frequency_type,
    -- Calcular intervalo esperado em horas
    CASE
        -- Daily with subday interval in hours
        WHEN freq_type = 4 AND freq_subday_type = 8 THEN freq_subday_interval
        -- Daily with subday interval in minutes
        WHEN freq_type = 4 AND freq_subday_type = 4 THEN CAST(freq_subday_interval AS FLOAT) / 60.0
        -- Daily once per day
        WHEN freq_type = 4 AND freq_subday_type = 1 THEN 24
        -- Weekly
        WHEN freq_type = 8 THEN 24 * 7 / (
            -- Count bits set in freq_interval (days of week)
            (freq_interval & 1) + ((freq_interval & 2) / 2) + ((freq_interval & 4) / 4) +
            ((freq_interval & 8) / 8) + ((freq_interval & 16) / 16) + ((freq_interval & 32) / 32) +
            ((freq_interval & 64) / 64)
        )
        -- Monthly
        WHEN freq_type = 16 THEN 24 * 30
        ELSE NULL
    END AS expected_interval_hours,
    -- Hora específica do dia (formato HH:MM:SS)
    STUFF(STUFF(RIGHT('000000' + CAST(active_start_time AS VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':') AS scheduled_time,
    -- Detalhes adicionais
    freq_interval,
    freq_subday_type,
    freq_subday_interval,
    active_start_time,
    is_enabled,
    schedule_enabled
FROM JobSchedules
WHERE database_name IS NOT NULL
ORDER BY database_name, backup_type, expected_interval_hours;
