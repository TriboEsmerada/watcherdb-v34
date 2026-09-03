"""
TapOS SQL Queries
Queries SQL organizadas por categoria
Todas otimizadas com NOLOCK para performance
"""

class SQLQueries:
    """
    Biblioteca de queries SQL Server para monitoramento
    Organizadas por categoria
    """
    
    HEALTH_OVERVIEW = """
    SELECT 'Server Info' AS Category,
           @@SERVERNAME AS Metric,
           CAST(@@VERSION AS VARCHAR(MAX)) COLLATE DATABASE_DEFAULT AS Value,
           GETDATE() AS Timestamp
    UNION ALL
    SELECT 'Uptime' AS Category,
           'Days' AS Metric,
           CAST(DATEDIFF(DAY, sqlserver_start_time, GETDATE()) AS VARCHAR) COLLATE DATABASE_DEFAULT AS Value,
           GETDATE() AS Timestamp
    FROM sys.dm_os_sys_info WITH(NOLOCK)
    UNION ALL
    SELECT 'CPU Usage' AS Category,
           'SQL Process %' AS Metric,
           CAST(SQLProcessUtilization AS VARCHAR) COLLATE DATABASE_DEFAULT AS Value,
           GETDATE() AS Timestamp
    FROM (
        SELECT TOP 1 SQLProcessUtilization
        FROM (
            SELECT
                record.value('(./Record/@id)[1]', 'int') AS record_id,
                record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS SQLProcessUtilization
            FROM (
                SELECT CAST(record AS XML) AS record
                FROM sys.dm_os_ring_buffers WITH(NOLOCK)
                WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
                AND record LIKE '%<SystemHealth>%'
            ) AS x
        ) AS y
        ORDER BY record_id DESC
    ) AS z
    UNION ALL
    SELECT 'Memory' AS Category,
           'Total Server Memory (MB)' AS Metric,
           CAST(CAST(cntr_value/1024.0 AS DECIMAL(18,2)) AS VARCHAR) COLLATE DATABASE_DEFAULT AS Value,
           GETDATE() AS Timestamp
    FROM sys.dm_os_performance_counters WITH(NOLOCK)
    WHERE counter_name = 'Total Server Memory (KB)'
    UNION ALL
    -- Informações de Criptografia TDE
    SELECT 'TDE Encryption' AS Category,
           'Status' AS Metric,
           CASE WHEN COUNT(*) > 0 THEN 'Encrypted' ELSE 'Not Encrypted' END COLLATE DATABASE_DEFAULT AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    UNION ALL
    SELECT 'TDE Encryption' AS Category,
           'Certificate Name' AS Metric,
           ISNULL(MAX(name) COLLATE DATABASE_DEFAULT, 'N/A') AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    UNION ALL
    SELECT 'TDE Encryption' AS Category,
           'Key Encryption Type' AS Metric,
           ISNULL(MAX(pvt_key_encryption_type_desc) COLLATE DATABASE_DEFAULT, 'N/A') AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    UNION ALL
    SELECT 'TDE Encryption' AS Category,
           'Issuer' AS Metric,
           ISNULL(MAX(issuer_name) COLLATE DATABASE_DEFAULT, 'N/A') AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    UNION ALL
    SELECT 'TDE Encryption' AS Category,
           'Subject' AS Metric,
           ISNULL(MAX(subject) COLLATE DATABASE_DEFAULT, 'N/A') AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    UNION ALL
    SELECT 'TDE Encryption' AS Category,
           'Start Date' AS Metric,
           ISNULL(CONVERT(VARCHAR, MAX(start_date), 120) COLLATE DATABASE_DEFAULT, 'N/A') AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    UNION ALL
    SELECT 'TDE Encryption' AS Category,
           'Expiry Date' AS Metric,
           ISNULL(CONVERT(VARCHAR, MAX(expiry_date), 120) COLLATE DATABASE_DEFAULT, 'N/A') AS Value,
           GETDATE() AS Timestamp
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    """
    
    TDE_STATUS = """
    SELECT CONVERT(CHAR(100), SERVERPROPERTY('Servername')) AS Server,
        name as certificate, 
        pvt_key_encryption_type_desc, 
        issuer_name, 
        subject,
        expiry_date,
        start_date
    FROM sys.certificates WITH(NOLOCK)
    WHERE name = 'TDECert_TAP'
    """
    
    TDE_DATABASE_STATUS = """
    -- Query para verificar status de TDE por database
    SELECT 
        d.name AS database_name,
        d.is_encrypted AS is_encrypted,
        CASE 
            WHEN d.is_encrypted = 1 THEN 'Sim'
            ELSE 'Não'
        END AS encryption_status,
        CASE 
            WHEN d.is_encrypted = 1 THEN 
                (SELECT TOP 1 c.name 
                 FROM sys.dm_database_encryption_keys dek
                 INNER JOIN sys.certificates c ON dek.encryptor_thumbprint = c.thumbprint
                 WHERE dek.database_id = d.database_id)
            ELSE NULL
        END AS encryption_certificate,
        CASE 
            WHEN d.is_encrypted = 1 THEN 
                (SELECT TOP 1 dek.encryption_state_desc 
                 FROM sys.dm_database_encryption_keys dek
                 WHERE dek.database_id = d.database_id)
            ELSE NULL
        END AS encryption_state
    FROM sys.databases d WITH(NOLOCK)
    WHERE d.database_id > 4  -- Excluir system databases
    AND d.state = 0  -- Apenas databases ONLINE
    ORDER BY d.is_encrypted, d.name
    """
    
    FILEGROUPS_SPACE = """
    SELECT 
        DB_NAME(f.database_id) AS DatabaseName,
        fg.name AS FileGroupName,
        f.name AS FileName,
        f.physical_name AS FilePath,
        LEFT(f.physical_name, 1) AS Volume,
        CAST(f.size * 8.0 / 1024 AS DECIMAL(18,2)) AS CurrentMB,
        CAST(f.size * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS CurrentGB,
        CAST((f.size - FILEPROPERTY(f.name, 'SpaceUsed')) * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS FreeGB,
        CAST(((f.size - FILEPROPERTY(f.name, 'SpaceUsed')) * 100.0 / f.size) AS DECIMAL(5,2)) AS FreePercent
    FROM sys.master_files f WITH(NOLOCK)
    LEFT JOIN sys.filegroups fg WITH(NOLOCK) ON f.data_space_id = fg.data_space_id
    WHERE f.type_desc = 'ROWS'
    ORDER BY DatabaseName, FileGroupName
    """
    
    TOP_SLOW_QUERIES = """
    SELECT TOP 50
        DB_NAME(qt.dbid) AS DatabaseName,
        SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
            ((CASE qs.statement_end_offset WHEN -1 THEN DATALENGTH(qt.text)
            ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1) AS QueryText,
        qs.execution_count AS ExecutionCount,
        CAST(qs.total_elapsed_time / 1000.0 / qs.execution_count AS DECIMAL(18,2)) AS AvgElapsedMs
    FROM sys.dm_exec_query_stats qs WITH(NOLOCK)
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
    ORDER BY qs.total_elapsed_time DESC
    """
    
    ACTIVE_PROCESSES = """
    SELECT 
        s.session_id AS SessionID,
        s.login_name AS LoginName,
        DB_NAME(s.database_id) AS DatabaseName,
        s.status AS Status,
        r.blocking_session_id AS BlockedBy
    FROM sys.dm_exec_sessions s WITH(NOLOCK)
    LEFT JOIN sys.dm_exec_requests r WITH(NOLOCK) ON s.session_id = r.session_id
    WHERE s.is_user_process = 1 AND s.session_id <> @@SPID
    """
    
    BLOCKING_CHAINS = """
    -- Query otimizada alinhada com Oracle KPI: conta sessões bloqueadas onde login_name, host_name ou program_name não são nulos
    -- Versão simplificada focando apenas em bloqueios reais ativos
    WITH BlockedSessions AS (
        SELECT DISTINCT
            r.session_id AS BlockedSPID,
            r.blocking_session_id AS BlockingSPID,
            DB_NAME(r.database_id) AS DatabaseName,
            r.wait_type AS WaitType,
            r.wait_time / 1000.0 AS WaitTimeSec,
            s.login_name,
            s.program_name,
            s.host_name,
            s.status as session_status
        FROM sys.dm_exec_requests r WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON r.session_id = s.session_id
        WHERE r.blocking_session_id > 0
          AND r.blocking_session_id <> r.session_id
          AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)
    )
    SELECT
        bs.BlockedSPID,
        bs.BlockingSPID,
        bs.DatabaseName,
        bs.WaitType,
        bs.WaitTimeSec,
        bs.login_name,
        bs.program_name,
        bs.host_name,
        bs.session_status,
        (SELECT COUNT(DISTINCT login_name) FROM BlockedSessions WHERE login_name IS NOT NULL) as total_blocked_users
    FROM BlockedSessions bs
    ORDER BY bs.WaitTimeSec DESC, bs.BlockedSPID
    """
    
    BACKUP_STATUS = """
    SELECT TOP 100
        bs.database_name AS DatabaseName,
        CASE bs.type WHEN 'D' THEN 'Full' WHEN 'I' THEN 'Differential' WHEN 'L' THEN 'Log' END AS BackupType,
        bs.backup_start_date AS BackupStartDate,
        bs.backup_finish_date AS BackupFinishDate,
        CAST(bs.backup_size / 1024.0 / 1024 / 1024 AS DECIMAL(18,2)) AS BackupSizeGB
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    WHERE bs.backup_finish_date >= DATEADD(DAY, -30, GETDATE())
    ORDER BY bs.backup_finish_date DESC
    """
    
    WAIT_STATS = """
    SELECT TOP 20
        wait_type AS WaitType,
        wait_time_ms / 1000.0 AS WaitTimeSec,
        waiting_tasks_count AS WaitCount,
        100.0 * wait_time_ms / SUM(wait_time_ms) OVER() AS Percentage
    FROM sys.dm_os_wait_stats WITH(NOLOCK)
    WHERE wait_time_ms > 0
    ORDER BY wait_time_ms DESC
    """
    
    INDEX_FRAGMENTATION = """
    -- Query ENHANCED para fragmentação de índices (v1.4.8.1)
    -- Fornece ação recomendada (REBUILD vs REORGANIZE) e scripts SQL prontos
    -- Usa QUOTENAME para maior segurança e suporta HEAPs (tabelas sem índice clusterizado)
    WITH IndexFragmentation AS (
        SELECT
            DB_NAME(ips.database_id) as DatabaseName,
            ss.name as SchemaName,
            OBJECT_NAME(ips.object_id, ips.database_id) as TableName,
            si.name as IndexName,
            si.type_desc as IndexType,
            ips.avg_fragmentation_in_percent as FragmentationPercent,
            ips.page_count,
            CAST(ips.page_count * 8.0 / 1024 AS DECIMAL(12,2)) as IndexSizeMB,
            ips.record_count,

            -- Ação recomendada baseada em melhores práticas Microsoft
            CASE
                WHEN ips.avg_fragmentation_in_percent > 30 AND ips.page_count > 1000 THEN 'REBUILD'
                WHEN ips.avg_fragmentation_in_percent > 10 AND ips.page_count > 1000 THEN 'REORGANIZE'
                ELSE 'OK'
            END as MaintenanceAction,

            -- Prioridade (1=Crítico, 2=Alto, 3=Médio, 4=Baixo)
            CASE
                WHEN ips.avg_fragmentation_in_percent > 50 THEN 1
                WHEN ips.avg_fragmentation_in_percent > 30 THEN 2
                WHEN ips.avg_fragmentation_in_percent > 10 THEN 3
                ELSE 4
            END as Priority,

            -- Script REBUILD/REORGANIZE de ÍNDICE (usando QUOTENAME - mais seguro)
            CASE
                WHEN ips.avg_fragmentation_in_percent > 30 AND ips.page_count > 1000 THEN
                    'ALTER INDEX ' + QUOTENAME(si.name) + ' ON ' +
                    QUOTENAME(ss.name) + '.' + QUOTENAME(OBJECT_NAME(ips.object_id, ips.database_id)) +
                    ' REBUILD WITH (ONLINE = ON);'
                WHEN ips.avg_fragmentation_in_percent > 10 AND ips.page_count > 1000 THEN
                    'ALTER INDEX ' + QUOTENAME(si.name) + ' ON ' +
                    QUOTENAME(ss.name) + '.' + QUOTENAME(OBJECT_NAME(ips.object_id, ips.database_id)) +
                    ' REORGANIZE;'
                ELSE NULL
            END as RebuildIndexScript,

            -- Script REBUILD de TABELA (para HEAPs - tabelas sem índice clusterizado)
            CASE
                WHEN si.type_desc = 'HEAP' AND ips.avg_fragmentation_in_percent > 10 THEN
                    'ALTER TABLE ' + QUOTENAME(ss.name) + '.' +
                    QUOTENAME(OBJECT_NAME(ips.object_id, ips.database_id)) + ' REBUILD;'
                ELSE NULL
            END as RebuildTableScript

        FROM sys.dm_db_index_physical_stats(NULL, NULL, NULL, NULL, 'LIMITED') ips
        INNER JOIN sys.indexes si WITH(NOLOCK)
            ON ips.object_id = si.object_id AND ips.index_id = si.index_id
        INNER JOIN sys.tables st WITH(NOLOCK)
            ON ips.object_id = st.object_id
        INNER JOIN sys.schemas ss WITH(NOLOCK)
            ON st.schema_id = ss.schema_id
        WHERE ips.avg_fragmentation_in_percent > 10  -- Filtrar apenas >= 10%
        AND ips.page_count > 100  -- Filtrar índices pequenos
        AND si.name IS NOT NULL  -- Excluir heaps sem nome
        AND si.is_disabled = 0  -- Excluir índices desabilitados
        AND si.is_hypothetical = 0  -- Excluir índices hipotéticos
        AND ips.index_level = 0  -- Apenas leaf level
    )
    SELECT TOP 100
        DatabaseName, SchemaName, TableName, IndexName, IndexType,
        CAST(FragmentationPercent AS DECIMAL(5,2)) as FragmentationPercent,
        page_count as PageCount, IndexSizeMB, record_count as RecordCount,
        MaintenanceAction, Priority,
        RebuildIndexScript,
        RebuildTableScript  -- Script para HEAPs (tabelas sem índice clusterizado)
    FROM IndexFragmentation
    ORDER BY Priority ASC, FragmentationPercent DESC
    """
    
    AVAILABILITY_GROUPS = """
    -- Query alinhada com a lógica do Oracle KPI: KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
    -- A view Oracle filtra por PRI_SYNCH_HEALTH <> 'HEALTHY' or SEC_SYNCH_HEALTH <> 'HEALTHY'
    -- Esta query retorna informações detalhadas de Always On para análise
    SELECT 
        ag.name AS AGName,
        ar.replica_server_name AS ReplicaServer,
        ars.role_desc AS CurrentRole,
        ars.synchronization_health_desc AS SyncHealth,
        ars.operational_state_desc AS OperationalState,
        ars.connected_state_desc AS ConnectedState,
        CASE 
            WHEN ars.synchronization_health_desc <> 'HEALTHY' THEN 'UNHEALTHY'
            ELSE 'HEALTHY'
        END AS HealthStatus
    FROM sys.availability_groups ag WITH(NOLOCK)
    INNER JOIN sys.availability_replicas ar WITH(NOLOCK) ON ag.group_id = ar.group_id
    INNER JOIN sys.dm_hadr_availability_replica_states ars WITH(NOLOCK) ON ar.replica_id = ars.replica_id
    """
    
    SQL_AGENT_JOBS = """
    SELECT 
        j.name AS JobName,
        j.enabled AS IsEnabled,
        CASE jh.run_status WHEN 0 THEN 'Failed' WHEN 1 THEN 'Succeeded' ELSE 'Other' END AS Status,
        CONVERT(DATETIME, CAST(jh.run_date AS VARCHAR(8))) AS LastRunDate
    FROM msdb.dbo.sysjobs j WITH(NOLOCK)
    LEFT JOIN msdb.dbo.sysjobhistory jh WITH(NOLOCK) ON j.job_id = jh.job_id AND jh.step_id = 0
    """
    
    # ===================================
    # QUERIES ADICIONAIS - TROUBLESHOOTING E MANUTENÇÃO
    # ===================================
    
    BLOCKING_HIERARCHY = """
    -- Query alinhada com a lógica do Oracle KPI: conta sessões bloqueadas onde login_name, host_name ou program_name não são nulos
    -- A view Oracle KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW conta: count(1) from KPI_MSSQL_BLOCKED_SESSIONS 
    -- where login_name is not null or host_name is not null or program_name is not null
    WITH AllBlockedSessions AS (
        -- 1. Sessões bloqueadas com requisições ativas (blocking_session_id)
        SELECT DISTINCT
            r.session_id,
            r.blocking_session_id,
            r.wait_type,
            r.wait_time,
            r.wait_resource,
            r.database_id,
            r.sql_handle,
            r.statement_start_offset,
            r.statement_end_offset,
            r.start_time,
            s.login_name,
            s.program_name,
            s.host_name,
            s.status as session_status,
            'BLOCKED_BY_SESSION' as block_type
        FROM sys.dm_exec_requests r WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON r.session_id = s.session_id
        WHERE r.blocking_session_id > 0
        AND r.blocking_session_id <> r.session_id  -- Excluir sessões bloqueando a si mesmas
        AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)  -- Alinhado com Oracle KPI
        
        UNION ALL
        
        -- 2. Sessões esperando por locks (wait_type LIKE 'LCK_%') - mesmo que não tenham blocking_session_id
        SELECT DISTINCT
            r.session_id,
            COALESCE(r.blocking_session_id, 0) as blocking_session_id,
            r.wait_type,
            r.wait_time,
            r.wait_resource,
            r.database_id,
            r.sql_handle,
            r.statement_start_offset,
            r.statement_end_offset,
            r.start_time,
            s.login_name,
            s.program_name,
            s.host_name,
            s.status as session_status,
            'LOCK_WAIT' as block_type
        FROM sys.dm_exec_requests r WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON r.session_id = s.session_id
        WHERE r.wait_type LIKE 'LCK_%'
        AND (r.blocking_session_id IS NULL OR r.blocking_session_id = 0 OR r.blocking_session_id <> r.session_id)  -- Excluir sessões bloqueando a si mesmas
        AND r.session_id NOT IN (SELECT session_id FROM sys.dm_exec_requests WITH(NOLOCK) WHERE blocking_session_id > 0 AND blocking_session_id <> session_id)
        AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)  -- Alinhado com Oracle KPI
        
        UNION ALL
        
        -- 3. Sessões esperando em sys.dm_os_waiting_tasks (bloqueios diversos, incluindo locks)
        SELECT DISTINCT
            wt.session_id,
            wt.blocking_session_id,
            wt.wait_type,
            wt.wait_duration_ms as wait_time,
            wt.resource_description as wait_resource,
            s.database_id,
            NULL as sql_handle,
            NULL as statement_start_offset,
            NULL as statement_end_offset,
            r.start_time,  -- Tentar obter start_time da requisição se existir
            s.login_name,
            s.program_name,
            s.host_name,
            s.status as session_status,
            CASE 
                WHEN wt.wait_type LIKE 'LCK_%' THEN 'LOCK_WAIT'
                ELSE 'WAITING_TASK'
            END as block_type
        FROM sys.dm_os_waiting_tasks wt WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON wt.session_id = s.session_id
        LEFT JOIN sys.dm_exec_requests r WITH(NOLOCK) ON wt.session_id = r.session_id
        WHERE ((wt.blocking_session_id IS NOT NULL AND wt.blocking_session_id > 0 AND wt.blocking_session_id <> wt.session_id)
           OR (wt.wait_type LIKE 'LCK_%' AND (wt.blocking_session_id IS NULL OR wt.blocking_session_id = 0 OR wt.blocking_session_id <> wt.session_id)))
        AND wt.session_id NOT IN (
            SELECT session_id FROM sys.dm_exec_requests WITH(NOLOCK) WHERE blocking_session_id > 0 AND blocking_session_id <> session_id
        )
        AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)  -- Alinhado com Oracle KPI
    )
    SELECT 
        abs.session_id,
        abs.blocking_session_id,
        abs.wait_type,
        abs.wait_time,
        abs.wait_resource,
        abs.login_name,
        abs.program_name,
        abs.host_name,
        abs.session_status,
        COALESCE(DB_NAME(abs.database_id), DB_NAME(s.database_id)) as database_name,
        CASE 
            WHEN abs.sql_handle IS NOT NULL THEN
                SUBSTRING(st.text, (abs.statement_start_offset/2)+1, 
                    (CASE WHEN abs.statement_end_offset = -1 
                     THEN LEN(CONVERT(nvarchar(max), st.text)) * 2 
                     ELSE abs.statement_end_offset 
                     END - abs.statement_start_offset)/2)
            ELSE NULL
        END as current_statement,
        abs.block_type,
        -- Informação adicional sobre o bloqueador
        blocker_s.login_name as blocker_login_name,
        blocker_s.program_name as blocker_program_name,
        blocker_s.host_name as blocker_host_name,
        -- Tempo de execução desde o início da requisição
        CASE 
            WHEN abs.start_time IS NOT NULL THEN
                DATEDIFF(MINUTE, abs.start_time, GETDATE())
            ELSE NULL
        END AS execution_duration_minutes,
        abs.start_time
    FROM AllBlockedSessions abs
    INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON abs.session_id = s.session_id
    LEFT JOIN sys.dm_exec_sessions blocker_s WITH(NOLOCK) ON abs.blocking_session_id = blocker_s.session_id
    OUTER APPLY sys.dm_exec_sql_text(abs.sql_handle) st
    WHERE (abs.blocking_session_id > 0 AND abs.blocking_session_id <> abs.session_id)  -- Excluir sessões bloqueando a si mesmas
       OR (abs.wait_type LIKE 'LCK_%' AND (abs.blocking_session_id IS NULL OR abs.blocking_session_id = 0 OR abs.blocking_session_id <> abs.session_id))
    ORDER BY abs.blocking_session_id, abs.session_id
    """
    
    TOP_SLOW_QUERIES_DETAILED = """
    SELECT TOP 20
        qs.execution_count,
        qs.total_elapsed_time / 1000000.0 as total_elapsed_seconds,
        qs.total_elapsed_time / qs.execution_count / 1000000.0 as avg_elapsed_seconds,
        qs.total_worker_time / 1000000.0 as total_cpu_seconds,
        qs.total_worker_time / qs.execution_count / 1000000.0 as avg_cpu_seconds,
        qs.total_logical_reads,
        qs.total_logical_reads / qs.execution_count as avg_logical_reads,
        qs.total_physical_reads,
        qs.creation_time,
        qs.last_execution_time,
        DB_NAME(st.dbid) as database_name,
        COALESCE(
            (SELECT TOP 1 s.login_name 
             FROM sys.dm_exec_sessions s WITH(NOLOCK)
             INNER JOIN sys.dm_exec_requests r WITH(NOLOCK) ON s.session_id = r.session_id
             WHERE r.plan_handle = qs.plan_handle
               AND s.login_name IS NOT NULL
             ORDER BY r.start_time DESC),
            (SELECT TOP 1 s.login_name
             FROM sys.dm_exec_cached_plans cp WITH(NOLOCK)
             CROSS APPLY sys.dm_exec_plan_attributes(cp.plan_handle) pa
             INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON CAST(pa.value AS INT) = s.session_id
             WHERE cp.plan_handle = qs.plan_handle
               AND pa.attribute = 'session_id'
               AND s.login_name IS NOT NULL),
            'N/A'
        ) as login_name,
        SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
            (CASE WHEN qs.statement_end_offset = -1 
             THEN LEN(CONVERT(nvarchar(max), st.text)) * 2 
             ELSE qs.statement_end_offset 
             END - qs.statement_start_offset)/2) as statement_text,
        CAST(qp.query_plan AS XML) as query_plan
    FROM sys.dm_exec_query_stats qs WITH(NOLOCK)
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
    CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
    WHERE qs.total_elapsed_time > 5000000
    ORDER BY qs.total_elapsed_time DESC
    """
    
    LOG_SPACE_MONITORING = """
    -- Query alinhada com a lógica do Oracle KPI: KPI_MSSQL_TLOG_USAGE_AGG_VIEW
    -- A view Oracle usa funções KPI_MSSQL_WARN_THRESHOLD_V2_FN e KPI_MSSQL_CRIT_THRESHOLD_V2_FN
    -- que calculam thresholds baseados em percentual de uso do log e MB livres
    -- NOTA: Os thresholds abaixo são aproximações. O Oracle pode usar lógica mais complexa.
    WITH LogSpaceInfo AS (
        SELECT 
            DB_NAME(lsu.database_id) as database_name,
            CAST(total_log_size_in_bytes / 1024.0 / 1024.0 AS DECIMAL(12,2)) as total_log_mb,
            CAST(used_log_space_in_bytes / 1024.0 / 1024.0 AS DECIMAL(12,2)) as used_log_mb,
            CAST((total_log_size_in_bytes - used_log_space_in_bytes) / 1024.0 / 1024.0 AS DECIMAL(12,2)) as free_log_mb,
            CAST((CAST(used_log_space_in_bytes AS FLOAT) / total_log_size_in_bytes) * 100 AS DECIMAL(5,2)) as log_used_percent,
            log_reuse_wait_desc
        FROM sys.dm_db_log_space_usage lsu WITH(NOLOCK)
        INNER JOIN sys.databases d WITH(NOLOCK) ON lsu.database_id = d.database_id
        WHERE d.state = 0
    )
    SELECT 
        database_name,
        total_log_mb,
        used_log_mb,
        free_log_mb,
        log_used_percent,
        log_reuse_wait_desc,
        CASE 
            WHEN log_used_percent > 90 THEN 'CRITICAL'
            WHEN log_used_percent > 75 THEN 'HIGH'
            WHEN log_used_percent > 60 THEN 'MEDIUM'
            ELSE 'OK'
        END as alert_level,
        CASE 
            WHEN log_reuse_wait_desc != 'NOTHING' 
            THEN 'Log reuse wait: ' + log_reuse_wait_desc
            ELSE 'Normal'
        END as reuse_status
    FROM LogSpaceInfo
    WHERE log_used_percent > 0
    ORDER BY log_used_percent DESC
    """
    
    SQL_AGENT_JOBS_FAILING = """
    SELECT 
        j.name as job_name,
        j.enabled,
        js.step_name,
        jh.run_date,
        jh.run_time,
        jh.run_status,
        CASE jh.run_status
            WHEN 0 THEN 'Failed'
            WHEN 1 THEN 'Succeeded'  
            WHEN 2 THEN 'Retry'
            WHEN 3 THEN 'Canceled'
            WHEN 4 THEN 'In Progress'
        END as status_desc,
        jh.run_duration,
        jh.message,
        CASE 
            WHEN jh.run_date > 0 
            THEN CONVERT(DATETIME, 
                    CAST(jh.run_date as CHAR(8)) + ' ' + 
                    STUFF(STUFF(RIGHT('000000' + CAST(jh.run_time as VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':'))
            ELSE NULL
        END as run_datetime
    FROM msdb.dbo.sysjobs j WITH(NOLOCK)
    INNER JOIN msdb.dbo.sysjobsteps js WITH(NOLOCK) ON j.job_id = js.job_id
    INNER JOIN msdb.dbo.sysjobhistory jh WITH(NOLOCK) ON js.job_id = jh.job_id AND js.step_id = jh.step_id
    WHERE jh.run_status = 0
    AND jh.run_date >= CONVERT(INT, CONVERT(VARCHAR, GETDATE()-7, 112))
    ORDER BY jh.run_date DESC, jh.run_time DESC
    """
    
    PROBLEMATIC_SESSIONS = """
    SELECT 
        s.session_id,
        s.login_name,
        s.host_name,
        s.program_name,
        s.status,
        s.cpu_time,
        s.memory_usage * 8 as memory_usage_kb,
        s.total_scheduled_time,
        s.total_elapsed_time,
        s.reads,
        s.writes,
        s.logical_reads,
        r.wait_type,
        r.wait_time,
        r.blocking_session_id,
        DB_NAME(COALESCE(r.database_id, s.database_id)) as current_database,
        CASE 
            WHEN s.cpu_time > 10000 THEN 'HIGH_CPU'
            WHEN s.memory_usage > 1000 THEN 'HIGH_MEMORY'
            WHEN r.wait_time > 30000 THEN 'LONG_WAIT'
            WHEN r.blocking_session_id > 0 THEN 'BLOCKED'
            ELSE 'NORMAL'
        END as session_status,
        CASE 
            WHEN r.sql_handle IS NOT NULL THEN
                SUBSTRING(ISNULL(st.text, ''), (r.statement_start_offset/2)+1,
                    (CASE WHEN r.statement_end_offset = -1 
                     THEN LEN(CONVERT(nvarchar(max), ISNULL(st.text, ''))) * 2 
                     ELSE r.statement_end_offset 
                     END - r.statement_start_offset)/2)
            ELSE NULL
        END as current_sql
    FROM sys.dm_exec_sessions s WITH(NOLOCK)
    LEFT JOIN sys.dm_exec_requests r WITH(NOLOCK) ON s.session_id = r.session_id
    OUTER APPLY (
        SELECT text 
        FROM sys.dm_exec_sql_text(r.sql_handle) 
        WHERE r.sql_handle IS NOT NULL
    ) st
    WHERE s.session_id > 50
    AND (
        s.cpu_time > 10000 OR
        s.memory_usage > 1000 OR
        r.wait_time > 30000 OR
        r.blocking_session_id > 0
    )
    ORDER BY s.cpu_time DESC
    """
    
    INDEX_FRAGMENTATION_DETAILED = """
    WITH IndexFragmentation AS (
        SELECT 
            DB_NAME(ips.database_id) as database_name,
            OBJECT_SCHEMA_NAME(ips.object_id, ips.database_id) as schema_name,
            OBJECT_NAME(ips.object_id, ips.database_id) as table_name,
            i.name as index_name,
            i.type_desc as index_type,
            ips.index_level,
            ips.avg_fragmentation_in_percent,
            ips.page_count,
            CAST(ips.page_count * 8.0 / 1024 AS DECIMAL(12,2)) as index_size_mb,
            ips.record_count
        FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'SAMPLED') ips
        INNER JOIN sys.indexes i WITH(NOLOCK) ON ips.object_id = i.object_id AND ips.index_id = i.index_id
        WHERE ips.index_level = 0
        AND ips.page_count > 100
        AND ips.avg_fragmentation_in_percent > 10
    )
    SELECT 
        database_name,
        schema_name,
        table_name,
        index_name,
        index_type,
        CAST(avg_fragmentation_in_percent AS DECIMAL(5,2)) as fragmentation_percent,
        page_count,
        index_size_mb,
        record_count,
        CASE 
            WHEN avg_fragmentation_in_percent > 30 
            THEN 'ALTER INDEX [' + index_name + '] ON [' + schema_name + '].[' + table_name + '] REBUILD'
            WHEN avg_fragmentation_in_percent > 10 
            THEN 'ALTER INDEX [' + index_name + '] ON [' + schema_name + '].[' + table_name + '] REORGANIZE'
            ELSE 'NO ACTION NEEDED'
        END as maintenance_recommendation
    FROM IndexFragmentation
    ORDER BY avg_fragmentation_in_percent DESC
    """
    
    TEMPDB_MONITORING = """
    SELECT 
        'TempDB Usage' as metric_type,
        CAST(SUM(total_pages * 8.0 / 1024) AS DECIMAL(12,2)) as total_mb,
        CAST(SUM(used_pages * 8.0 / 1024) AS DECIMAL(12,2)) as used_mb,
        CAST(SUM((total_pages - used_pages) * 8.0 / 1024) AS DECIMAL(12,2)) as free_mb,
        CAST((SUM(used_pages) * 100.0 / SUM(total_pages)) AS DECIMAL(5,2)) as used_percent,
        NULL as session_info,
        NULL as user_objects_mb
    FROM tempdb.sys.allocation_units WITH(NOLOCK)
    UNION ALL
    SELECT 
        'TempDB Top Sessions' as metric_type,
        NULL as total_mb,
        NULL as used_mb,
        NULL as free_mb,
        NULL as used_percent,
        CAST(session_id AS VARCHAR) as session_info,
        CAST(((user_objects_alloc_page_count - user_objects_dealloc_page_count) * 8.0 / 1024) AS DECIMAL(12,2)) as user_objects_mb
    FROM sys.dm_db_session_space_usage WITH(NOLOCK)
    WHERE (user_objects_alloc_page_count - user_objects_dealloc_page_count) > 1000
    ORDER BY user_objects_mb DESC
    """
    
    FILE_GROWTH_MONITORING = """
    SELECT 
        DB_NAME() as database_name,
        f.name as file_name,
        f.type_desc as file_type,
        fg.name as filegroup_name,
        f.physical_name,
        CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2)) as current_size_mb,
        CASE 
            WHEN f.max_size = -1 THEN 'Unlimited'
            WHEN f.max_size = 268435456 THEN '2TB (Default Max)'
            ELSE CAST(f.max_size * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
        END as max_size,
        CASE 
            WHEN f.is_percent_growth = 1 
            THEN CAST(f.growth AS VARCHAR(10)) + '%'
            ELSE CAST(f.growth * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
        END as growth_increment,
        CASE 
            WHEN f.is_percent_growth = 1 AND f.growth >= 10 
            THEN 'WARNING: Percent growth >= 10%'
            WHEN f.is_percent_growth = 0 AND (f.growth * 8.0 / 1024) < 100 
            THEN 'WARNING: Fixed growth < 100MB'
            ELSE 'OK'
        END as growth_recommendation
    FROM sys.database_files f WITH(NOLOCK)
    LEFT JOIN sys.filegroups fg WITH(NOLOCK) ON f.data_space_id = fg.data_space_id
    ORDER BY f.type, f.file_id
    """
    
    STATISTICS_OUTDATED = """
    -- Query ENHANCED para estatísticas desatualizadas (v1.4.8)
    -- Fornece script SQL pronto e priorização por score
    WITH StatisticsInfo AS (
        SELECT
            OBJECT_SCHEMA_NAME(s.object_id) as schema_name,
            OBJECT_NAME(s.object_id) as table_name,
            s.name as stats_name,
            sp.last_updated,
            sp.rows as table_rows,
            sp.rows_sampled,
            sp.modification_counter,
            sp.steps as histogram_steps,
            -- Tipo de estatística
            CASE
                WHEN s.auto_created = 1 THEN 'AUTO_CREATED'
                WHEN s.user_created = 1 THEN 'USER_CREATED'
                WHEN EXISTS (SELECT 1 FROM sys.indexes i
                             WHERE i.object_id = s.object_id AND i.name = s.name)
                    THEN 'INDEX_STATS'
                ELSE 'COLUMN_STATS'
            END as stats_type,
            -- Percentual de modificação
            CASE
                WHEN sp.rows > 0
                THEN CAST((sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2))
                ELSE 0
            END as modification_percent,
            -- Dias desde última atualização
            CASE
                WHEN sp.last_updated IS NOT NULL
                THEN DATEDIFF(day, sp.last_updated, GETDATE())
                ELSE NULL
            END as days_since_update,
            -- Horas desde última atualização
            CASE
                WHEN sp.last_updated IS NOT NULL
                THEN DATEDIFF(hour, sp.last_updated, GETDATE())
                ELSE NULL
            END as hours_since_update
        FROM sys.stats s WITH(NOLOCK)
        CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
        WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
        AND sp.rows >= 100  -- Reduzido de 1000 para 100
        AND sp.last_updated IS NOT NULL  -- Eliminar stats nunca atualizadas
    ),
    PrioritizedStats AS (
        SELECT *,
            -- Score de priorização
            (
                (CASE WHEN days_since_update > 14 THEN 30
                      WHEN days_since_update > 7 THEN 20
                      WHEN days_since_update > 3 THEN 10
                      ELSE COALESCE(days_since_update, 0) END) +
                (CASE WHEN modification_percent > 25 THEN 25
                      WHEN modification_percent > 15 THEN 15
                      WHEN modification_percent > 5 THEN 10
                      ELSE modification_percent END) +
                (CASE WHEN table_rows > 100000 THEN 15
                      WHEN table_rows > 10000 THEN 10
                      WHEN table_rows > 1000 THEN 5
                      ELSE 0 END)
            ) as priority_score,
            -- Classificação de urgência
            CASE
                WHEN days_since_update > 14 OR modification_percent > 20 THEN 'URGENT'
                WHEN days_since_update > 7 OR modification_percent > 10 THEN 'HIGH'
                WHEN days_since_update > 3 OR modification_percent > 5 THEN 'MEDIUM'
                ELSE 'OK'
            END as urgency_level,
            -- Script de atualização
            'UPDATE STATISTICS [' + schema_name + '].[' + table_name + '] [' + stats_name + ']' +
            CASE
                WHEN days_since_update > 7 OR modification_percent > 15
                    THEN ' WITH FULLSCAN;'
                WHEN days_since_update > 3 OR modification_percent > 5
                    THEN ' WITH SAMPLE 25 PERCENT;'
                ELSE ';'
            END as update_script,
            -- Prioridade numérica
            CASE
                WHEN days_since_update > 14 OR modification_percent > 20 THEN 1
                WHEN days_since_update > 7 OR modification_percent > 10 THEN 2
                WHEN days_since_update > 3 OR modification_percent > 5 THEN 3
                ELSE 4
            END as priority
        FROM StatisticsInfo
    )
    SELECT TOP 100
        schema_name,
        table_name,
        stats_name,
        stats_type,
        last_updated,
        days_since_update,
        hours_since_update,
        FORMAT(table_rows, 'N0') as table_rows,
        FORMAT(modification_counter, 'N0') as modifications,
        modification_percent,
        urgency_level,
        priority,
        priority_score,
        update_script
    FROM PrioritizedStats
    WHERE days_since_update >= 3
       OR modification_percent >= 5
       OR priority_score > 5
    ORDER BY priority ASC, priority_score DESC, modification_percent DESC
    """
    
    MIRRORING_LOGSHIPPING_STATUS = """
    SELECT 
        'Database Mirroring' as availability_type,
        db.name as database_name,
        m.mirroring_role_desc,
        m.mirroring_state_desc,
        m.mirroring_safety_level_desc,
        m.mirroring_witness_name,
        m.mirroring_witness_state_desc,
        CASE 
            WHEN m.mirroring_state_desc != 'SYNCHRONIZED' 
            AND m.mirroring_state_desc != 'SYNCHRONIZING'
            THEN 'ALERT'
            ELSE 'OK'
        END as status
    FROM sys.database_mirroring m WITH(NOLOCK)
    INNER JOIN sys.databases db WITH(NOLOCK) ON m.database_id = db.database_id
    WHERE m.mirroring_guid IS NOT NULL
    
    UNION ALL
    
    SELECT 
        'Log Shipping' as availability_type,
        primary_database as database_name,
        'PRIMARY' as role_desc,
        NULL as state_desc,
        NULL as safety_level,
        NULL as witness_name,
        NULL as witness_state,
        CASE 
            WHEN DATEDIFF(minute, last_backup_date, GETDATE()) > 60
            THEN 'BACKUP_DELAY'
            ELSE 'OK'
        END as status
    FROM msdb.dbo.log_shipping_primary_databases WITH(NOLOCK)
    WHERE enabled = 1
    """
    
    DATABASE_CONNECTIONS = """
    SELECT
        DB_NAME(s.database_id) AS DatabaseName,
        COUNT(s.database_id) AS NumberOfConnections
    FROM sys.dm_exec_sessions s WITH(NOLOCK)
    WHERE s.database_id > 0
    AND s.is_user_process = 1
    GROUP BY s.database_id
    ORDER BY NumberOfConnections DESC
    """

    FILEGROUP_GROWTH_HISTORY = """
-- Query para histórico de crescimento de filegroups (v1.4.8)
-- Analisa crescimento dos últimos 12 meses usando histórico de backups
WITH FileGroupGrowth AS (
    SELECT
        d.name AS DatabaseName,
        fg.name AS FileGroupName,
        f.name AS LogicalFileName,
        f.type_desc AS FileType,
        CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2)) AS CurrentSizeMB,
        CAST(f.max_size * 8.0 / 1024 AS DECIMAL(12,2)) AS MaxSizeMB,
        f.growth AS GrowthPages,
        CASE
            WHEN f.is_percent_growth = 1 THEN CAST(f.growth AS VARCHAR(10)) + '%'
            ELSE CAST(f.growth * 8.0 / 1024 AS VARCHAR(10)) + ' MB'
        END AS GrowthSetting,
        -- Histórico de 12 meses via backup
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -12, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size12MonthsAgoMB,
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -6, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size6MonthsAgoMB,
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -3, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size3MonthsAgoMB,
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -1, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size1MonthAgoMB
    FROM sys.databases d WITH(NOLOCK)
    INNER JOIN sys.master_files f WITH(NOLOCK) ON d.database_id = f.database_id
    INNER JOIN sys.filegroups fg WITH(NOLOCK) ON f.data_space_id = fg.data_space_id
    WHERE d.state = 0  -- ONLINE
    AND d.database_id > 4  -- Excluir system databases
)
SELECT
    DatabaseName, FileGroupName, LogicalFileName, FileType,
    CurrentSizeMB,
    Size1MonthAgoMB, Size3MonthsAgoMB, Size6MonthsAgoMB, Size12MonthsAgoMB,
    -- Crescimento calculado
    CASE WHEN Size1MonthAgoMB IS NOT NULL
         THEN CAST((CurrentSizeMB - Size1MonthAgoMB) AS DECIMAL(12,2))
         ELSE NULL END AS Growth1MonthMB,
    CASE WHEN Size3MonthsAgoMB IS NOT NULL
         THEN CAST((CurrentSizeMB - Size3MonthsAgoMB) AS DECIMAL(12,2))
         ELSE NULL END AS Growth3MonthsMB,
    CASE WHEN Size6MonthsAgoMB IS NOT NULL
         THEN CAST((CurrentSizeMB - Size6MonthsAgoMB) AS DECIMAL(12,2))
         ELSE NULL END AS Growth6MonthsMB,
    CASE WHEN Size12MonthsAgoMB IS NOT NULL
         THEN CAST((CurrentSizeMB - Size12MonthsAgoMB) AS DECIMAL(12,2))
         ELSE NULL END AS Growth12MonthsMB,
    -- Taxa de crescimento mensal média
    CASE WHEN Size12MonthsAgoMB IS NOT NULL AND Size12MonthsAgoMB > 0
         THEN CAST(((CurrentSizeMB - Size12MonthsAgoMB) / 12.0) AS DECIMAL(12,2))
         WHEN Size6MonthsAgoMB IS NOT NULL AND Size6MonthsAgoMB > 0
         THEN CAST(((CurrentSizeMB - Size6MonthsAgoMB) / 6.0) AS DECIMAL(12,2))
         WHEN Size3MonthsAgoMB IS NOT NULL AND Size3MonthsAgoMB > 0
         THEN CAST(((CurrentSizeMB - Size3MonthsAgoMB) / 3.0) AS DECIMAL(12,2))
         ELSE NULL END AS AvgMonthlyGrowthMB,
    MaxSizeMB, GrowthSetting
FROM FileGroupGrowth
WHERE Size1MonthAgoMB IS NOT NULL
   OR Size3MonthsAgoMB IS NOT NULL
   OR Size6MonthsAgoMB IS NOT NULL
   OR Size12MonthsAgoMB IS NOT NULL
ORDER BY DatabaseName, FileGroupName
"""
    
    FILEGROUP_GROWTH_FORECAST = """
-- Query para projeção de crescimento de filegroups (v1.4.8)
-- Calcula MonthsUntilFull baseado em histórico e crescimento médio
WITH FileGroupStats AS (
    SELECT
        d.name AS DatabaseName,
        fg.name AS FileGroupName,
        f.name AS LogicalFileName,
        CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2)) AS CurrentSizeMB,
        CASE
            WHEN f.max_size = -1 THEN 999999999  -- Unlimited
            WHEN f.max_size = 0 THEN CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2))
            ELSE CAST(f.max_size * 8.0 / 1024 AS DECIMAL(12,2))
        END AS MaxSizeMB,
        -- Tamanho há 12 meses
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -12, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size12MonthsAgoMB,
        -- Tamanho há 6 meses
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -6, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size6MonthsAgoMB,
        -- Tamanho há 3 meses
        (SELECT TOP 1 CAST(backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         AND bs.backup_finish_date >= DATEADD(MONTH, -3, GETDATE())
         ORDER BY bs.backup_finish_date ASC) AS Size3MonthsAgoMB
    FROM sys.databases d WITH(NOLOCK)
    INNER JOIN sys.master_files f WITH(NOLOCK) ON d.database_id = f.database_id
    INNER JOIN sys.filegroups fg WITH(NOLOCK) ON f.data_space_id = fg.data_space_id
    WHERE d.state = 0  -- ONLINE
    AND d.database_id > 4  -- Excluir system databases
),
GrowthCalculations AS (
    SELECT
        DatabaseName, FileGroupName, LogicalFileName,
        CurrentSizeMB, MaxSizeMB,
        -- Crescimento médio mensal (prioriza 12 meses, depois 6, depois 3)
        CASE
            WHEN Size12MonthsAgoMB IS NOT NULL AND Size12MonthsAgoMB > 0
                THEN (CurrentSizeMB - Size12MonthsAgoMB) / 12.0
            WHEN Size6MonthsAgoMB IS NOT NULL AND Size6MonthsAgoMB > 0
                THEN (CurrentSizeMB - Size6MonthsAgoMB) / 6.0
            WHEN Size3MonthsAgoMB IS NOT NULL AND Size3MonthsAgoMB > 0
                THEN (CurrentSizeMB - Size3MonthsAgoMB) / 3.0
            ELSE NULL
        END AS AvgMonthlyGrowthMB,
        -- Espaço disponível
        CASE
            WHEN MaxSizeMB = 999999999 THEN NULL  -- Unlimited
            ELSE MaxSizeMB - CurrentSizeMB
        END AS AvailableSpaceMB
    FROM FileGroupStats
)
SELECT
    DatabaseName, FileGroupName, LogicalFileName,
    CurrentSizeMB, MaxSizeMB,
    CAST(AvgMonthlyGrowthMB AS DECIMAL(12,2)) AS AvgMonthlyGrowthMB,
    CAST(AvailableSpaceMB AS DECIMAL(12,2)) AS AvailableSpaceMB,
    -- Percentual usado
    CASE
        WHEN MaxSizeMB > 0 AND MaxSizeMB <> 999999999
        THEN CAST((CurrentSizeMB * 100.0 / MaxSizeMB) AS DECIMAL(5,2))
        ELSE NULL
    END AS UsedPercent,
    -- Meses até ficar cheio (MonthsUntilFull)
    CASE
        WHEN MaxSizeMB = 999999999 THEN 999999  -- Unlimited
        WHEN AvgMonthlyGrowthMB IS NULL OR AvgMonthlyGrowthMB <= 0 THEN NULL
        WHEN AvailableSpaceMB IS NULL OR AvailableSpaceMB <= 0 THEN 0
        ELSE CAST((AvailableSpaceMB / AvgMonthlyGrowthMB) AS INT)
    END AS MonthsUntilFull,
    -- Data estimada de lotação
    CASE
        WHEN MaxSizeMB = 999999999 THEN NULL
        WHEN AvgMonthlyGrowthMB IS NULL OR AvgMonthlyGrowthMB <= 0 THEN NULL
        WHEN AvailableSpaceMB IS NULL OR AvailableSpaceMB <= 0
            THEN CONVERT(VARCHAR(10), GETDATE(), 120)
        ELSE CONVERT(VARCHAR(10),
            DATEADD(MONTH, CAST((AvailableSpaceMB / AvgMonthlyGrowthMB) AS INT), GETDATE()), 120)
    END AS EstimatedFullDate,
    -- Classificação de risco
    CASE
        WHEN MaxSizeMB = 999999999 THEN 'OK'
        WHEN AvailableSpaceMB IS NULL OR AvailableSpaceMB <= 0 THEN 'CRITICAL'
        WHEN AvgMonthlyGrowthMB IS NULL OR AvgMonthlyGrowthMB <= 0 THEN 'NO_DATA'
        WHEN (AvailableSpaceMB / AvgMonthlyGrowthMB) < 3 THEN 'CRITICAL'
        WHEN (AvailableSpaceMB / AvgMonthlyGrowthMB) < 6 THEN 'HIGH'
        WHEN (AvailableSpaceMB / AvgMonthlyGrowthMB) < 12 THEN 'MEDIUM'
        ELSE 'OK'
    END AS RiskLevel
FROM GrowthCalculations
WHERE AvgMonthlyGrowthMB IS NOT NULL
ORDER BY
    CASE
        WHEN MaxSizeMB = 999999999 THEN 99999
        WHEN AvailableSpaceMB IS NULL OR AvailableSpaceMB <= 0 THEN 0
        WHEN AvgMonthlyGrowthMB IS NULL OR AvgMonthlyGrowthMB <= 0 THEN 99998
        ELSE CAST((AvailableSpaceMB / AvgMonthlyGrowthMB) AS INT)
    END ASC,
    DatabaseName
"""

    BACKUP_HISTORY_ANALYSIS = """
-- Query ENHANCED para análise de backups (v1.4.8)
-- Detecta databases sem backup e considera Always On AG
WITH BackupInfo AS (
    SELECT
        d.name AS DatabaseName,
        d.recovery_model_desc AS RecoveryModel,
        d.state_desc AS DatabaseState,
        -- Último backup FULL
        (SELECT TOP 1 bs.backup_finish_date
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         ORDER BY bs.backup_finish_date DESC) AS LastFullBackup,
        -- Último backup DIFF
        (SELECT TOP 1 bs.backup_finish_date
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'I'
         ORDER BY bs.backup_finish_date DESC) AS LastDiffBackup,
        -- Último backup LOG
        (SELECT TOP 1 bs.backup_finish_date
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'L'
         ORDER BY bs.backup_finish_date DESC) AS LastLogBackup,
        -- Tamanho do último backup FULL
        (SELECT TOP 1 CAST(bs.backup_size / 1024.0 / 1024.0 AS DECIMAL(12,2))
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         ORDER BY bs.backup_finish_date DESC) AS LastFullBackupSizeMB,
        -- Duração do último backup FULL (segundos)
        (SELECT TOP 1 DATEDIFF(SECOND, bs.backup_start_date, bs.backup_finish_date)
         FROM msdb.dbo.backupset bs
         WHERE bs.database_name = d.name
         AND bs.type = 'D'
         ORDER BY bs.backup_finish_date DESC) AS LastFullBackupDurationSec,
        -- Verificar se está em Always On AG
        CASE
            WHEN EXISTS (
                SELECT 1 FROM sys.dm_hadr_database_replica_states hdrs
                WHERE hdrs.database_id = d.database_id
            ) THEN 1
            ELSE 0
        END AS IsAlwaysOnAG,
        -- Verificar se é réplica primária
        CASE
            WHEN EXISTS (
                SELECT 1 FROM sys.dm_hadr_database_replica_states hdrs
                INNER JOIN sys.availability_replicas ar ON hdrs.replica_id = ar.replica_id
                WHERE hdrs.database_id = d.database_id
                AND ar.replica_server_name = @@SERVERNAME
                AND hdrs.is_primary_replica = 1
            ) THEN 1
            ELSE 0
        END AS IsPrimaryReplica
    FROM sys.databases d WITH(NOLOCK)
    WHERE d.database_id > 4  -- Excluir system databases
    AND d.state = 0  -- ONLINE
    AND d.name NOT IN ('tempdb')
)
SELECT
    DatabaseName, RecoveryModel, DatabaseState,
    LastFullBackup, LastDiffBackup, LastLogBackup,
    -- Dias sem backup
    CASE
        WHEN LastFullBackup IS NULL THEN 999
        ELSE DATEDIFF(DAY, LastFullBackup, GETDATE())
    END AS DaysSinceLastFullBackup,
    CASE
        WHEN RecoveryModel <> 'SIMPLE' AND LastLogBackup IS NULL THEN 999
        WHEN RecoveryModel <> 'SIMPLE' THEN DATEDIFF(HOUR, LastLogBackup, GETDATE())
        ELSE NULL
    END AS HoursSinceLastLogBackup,
    LastFullBackupSizeMB, LastFullBackupDurationSec,
    -- Classificação de risco
    CASE
        -- Always On: apenas primária precisa de backup
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 0 THEN 'AG_SECONDARY'
        -- Sem backup FULL
        WHEN LastFullBackup IS NULL THEN 'CRITICAL'
        -- FULL backup muito antigo (>7 dias)
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 7 THEN 'CRITICAL'
        -- FULL backup antigo (>3 dias)
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 3 THEN 'HIGH'
        -- FULL backup (>1 dia)
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 1 THEN 'MEDIUM'
        -- LOG backup: FULL/BULK_LOGGED sem backup de log
        WHEN RecoveryModel <> 'SIMPLE' AND LastLogBackup IS NULL THEN 'HIGH'
        -- LOG backup muito antigo (>6 horas)
        WHEN RecoveryModel <> 'SIMPLE' AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 6 THEN 'HIGH'
        -- LOG backup antigo (>2 horas)
        WHEN RecoveryModel <> 'SIMPLE' AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 2 THEN 'MEDIUM'
        ELSE 'OK'
    END AS RiskLevel,
    -- Status Always On
    CASE
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 1 THEN 'AG_PRIMARY'
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 0 THEN 'AG_SECONDARY'
        ELSE 'STANDALONE'
    END AS AlwaysOnStatus,
    -- Recomendação
    CASE
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 0
            THEN 'Réplica secundária - backup gerenciado pela primária'
        WHEN LastFullBackup IS NULL
            THEN 'URGENTE: Configurar backup FULL imediatamente'
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 7
            THEN 'URGENTE: Executar backup FULL (>7 dias sem backup)'
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 3
            THEN 'Executar backup FULL em breve (>3 dias)'
        WHEN RecoveryModel <> 'SIMPLE' AND LastLogBackup IS NULL
            THEN 'URGENTE: Configurar backup de LOG'
        WHEN RecoveryModel <> 'SIMPLE' AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 6
            THEN 'Verificar backup de LOG (>6 horas)'
        ELSE 'Backups em dia'
    END AS Recommendation
FROM BackupInfo
WHERE
    -- Excluir réplicas secundárias OK
    NOT (IsAlwaysOnAG = 1 AND IsPrimaryReplica = 0)
    -- Mostrar apenas problemas ou avisos
    AND (
        LastFullBackup IS NULL
        OR DATEDIFF(DAY, LastFullBackup, GETDATE()) > 1
        OR (RecoveryModel <> 'SIMPLE' AND
            (LastLogBackup IS NULL OR DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 2))
    )
ORDER BY
    CASE
        WHEN LastFullBackup IS NULL THEN 1
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 7 THEN 2
        WHEN RecoveryModel <> 'SIMPLE' AND LastLogBackup IS NULL THEN 3
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 3 THEN 4
        ELSE 5
    END,
    DatabaseName
"""

    MISSING_INDEX_ANALYSIS = """
-- Query ENHANCED para análise de índices faltantes (v1.4.8.1)
-- Identifica índices com alto impacto usando DMVs de missing indexes
-- CORRIGIDO: Busca em TODAS as databases (não apenas a database atual)
WITH MissingIndexInfo AS (
    SELECT
        DB_NAME(mid.database_id) AS DatabaseName,
        OBJECT_SCHEMA_NAME(mid.object_id, mid.database_id) AS SchemaName,
        OBJECT_NAME(mid.object_id, mid.database_id) AS TableName,
        migs.avg_total_user_cost AS AvgQueryCost,
        migs.avg_user_impact AS AvgImpactPercent,
        migs.user_seeks AS UserSeeks,
        migs.user_scans AS UserScans,
        migs.last_user_seek AS LastUserSeek,
        migs.last_user_scan AS LastUserScan,
        mid.equality_columns AS EqualityColumns,
        mid.inequality_columns AS InequalityColumns,
        mid.included_columns AS IncludedColumns,
        mid.statement AS TableFullName,
        -- Cálculo de improvement_measure (métrica do SQL Server)
        (migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) AS ImprovementMeasure,
        -- Score personalizado
        (
            (migs.avg_user_impact / 10.0) +  -- Impacto médio (0-10)
            (CASE WHEN migs.user_seeks + migs.user_scans > 1000 THEN 10
                  WHEN migs.user_seeks + migs.user_scans > 500 THEN 7
                  WHEN migs.user_seeks + migs.user_scans > 100 THEN 5
                  WHEN migs.user_seeks + migs.user_scans > 10 THEN 3
                  ELSE 1 END) +  -- Frequência de uso (1-10)
            (CASE WHEN migs.avg_total_user_cost > 100 THEN 10
                  WHEN migs.avg_total_user_cost > 50 THEN 7
                  WHEN migs.avg_total_user_cost > 10 THEN 5
                  ELSE 2 END)  -- Custo da query (2-10)
        ) AS CustomScore
    FROM sys.dm_db_missing_index_details mid WITH(NOLOCK)
    INNER JOIN sys.dm_db_missing_index_groups mig WITH(NOLOCK)
        ON mid.index_handle = mig.index_handle
    INNER JOIN sys.dm_db_missing_index_group_stats migs WITH(NOLOCK)
        ON mig.index_group_handle = migs.group_handle
    WHERE DB_NAME(mid.database_id) IS NOT NULL  -- CORRIGIDO: busca em TODAS as databases
    AND mid.database_id > 4  -- Excluir system databases
    AND OBJECT_NAME(mid.object_id, mid.database_id) IS NOT NULL
),
RankedIndexes AS (
    SELECT
        DatabaseName, SchemaName, TableName,
        CAST(AvgQueryCost AS DECIMAL(12,2)) AS AvgQueryCost,
        CAST(AvgImpactPercent AS DECIMAL(5,2)) AS AvgImpactPercent,
        UserSeeks, UserScans,
        UserSeeks + UserScans AS TotalReads,
        LastUserSeek, LastUserScan,
        EqualityColumns, InequalityColumns, IncludedColumns,
        CAST(ImprovementMeasure AS DECIMAL(18,2)) AS ImprovementMeasure,
        CAST(CustomScore AS DECIMAL(8,2)) AS CustomScore,
        -- Classificação de prioridade
        CASE
            WHEN ImprovementMeasure > 100000 THEN 'CRITICAL'
            WHEN ImprovementMeasure > 50000 THEN 'HIGH'
            WHEN ImprovementMeasure > 10000 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS Priority,
        -- Script CREATE INDEX sugerido
        'CREATE NONCLUSTERED INDEX [IX_' + TableName + '_' +
        REPLACE(REPLACE(REPLACE(
            COALESCE(EqualityColumns, '') +
            CASE WHEN EqualityColumns IS NOT NULL AND InequalityColumns IS NOT NULL
                 THEN '_' ELSE '' END +
            COALESCE(InequalityColumns, ''),
        '[', ''), ']', ''), ', ', '_') +
        '] ON [' + SchemaName + '].[' + TableName + '] (' +
        CASE
            WHEN EqualityColumns IS NOT NULL AND InequalityColumns IS NOT NULL
                THEN EqualityColumns + ', ' + InequalityColumns
            WHEN EqualityColumns IS NOT NULL
                THEN EqualityColumns
            ELSE InequalityColumns
        END + ')' +
        CASE
            WHEN IncludedColumns IS NOT NULL
                THEN ' INCLUDE (' + IncludedColumns + ')'
            ELSE ''
        END +
        ' WITH (ONLINE = ON, FILLFACTOR = 90);' AS CreateIndexScript
    FROM MissingIndexInfo
)
SELECT TOP 50
    DatabaseName, SchemaName, TableName,
    AvgQueryCost, AvgImpactPercent,
    UserSeeks, UserScans, TotalReads,
    LastUserSeek, LastUserScan,
    ImprovementMeasure, CustomScore, Priority,
    EqualityColumns, InequalityColumns, IncludedColumns,
    CreateIndexScript
FROM RankedIndexes
WHERE ImprovementMeasure > 1000  -- Filtrar apenas índices com impacto significativo
ORDER BY ImprovementMeasure DESC, CustomScore DESC
"""

    @staticmethod
    def get_missing_index_analysis_filtered(database_name: str = None):
        """
        Retorna query MISSING_INDEX_ANALYSIS com filtro opcional de database

        Args:
            database_name: Nome da database para filtrar (None = todas)
        """
        base_query = SQLQueries.MISSING_INDEX_ANALYSIS

        if database_name and database_name.upper() != 'ALL':
            # Adicionar filtro de database na CTE MissingIndexInfo
            # Usar QUOTENAME para segurança
            safe_db_name = database_name.replace(']', ']]')  # Escape ]
            filter_clause = f"\n    AND DB_NAME(mid.database_id) = '{safe_db_name}'"

            # Inserir o filtro após "AND mid.database_id > 4"
            base_query = base_query.replace(
                "AND mid.database_id > 4  -- Excluir system databases\n    AND OBJECT_NAME",
                f"AND mid.database_id > 4  -- Excluir system databases{filter_clause}\n    AND OBJECT_NAME"
            )

        return base_query

    @staticmethod
    def get_filegroup_growth_history_filtered(database_name: str = None):
        """
        Retorna query FILEGROUP_GROWTH_HISTORY com filtro opcional de database

        Args:
            database_name: Nome da database para filtrar (None = todas)
        """
        base_query = SQLQueries.FILEGROUP_GROWTH_HISTORY

        if database_name and database_name.upper() != 'ALL':
            safe_db_name = database_name.replace(']', ']]')
            filter_clause = f"\nAND d.name = '{safe_db_name}'"

            # Inserir filtro após "WHERE d.database_id > 4"
            base_query = base_query.replace(
                "WHERE d.database_id > 4  -- Excluir system databases\nORDER BY",
                f"WHERE d.database_id > 4  -- Excluir system databases{filter_clause}\nORDER BY"
            )

        return base_query

    @staticmethod
    def get_filegroup_growth_forecast_filtered(database_name: str = None):
        """
        Retorna query FILEGROUP_GROWTH_FORECAST com filtro opcional de database

        Args:
            database_name: Nome da database para filtrar (None = todas)
        """
        base_query = SQLQueries.FILEGROUP_GROWTH_FORECAST

        if database_name and database_name.upper() != 'ALL':
            safe_db_name = database_name.replace(']', ']]')
            filter_clause = f"\n    AND d.name = '{safe_db_name}'"

            # Inserir filtro após "AND d.database_id > 4"
            base_query = base_query.replace(
                "WHERE d.state = 0  -- ONLINE\n    AND d.database_id > 4  -- Excluir system databases\n),",
                f"WHERE d.state = 0  -- ONLINE\n    AND d.database_id > 4  -- Excluir system databases{filter_clause}\n),"
            )

        return base_query