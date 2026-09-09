"""
WatcherDB SQL Queries
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
    -- Query corrigida para detectar QUALQUER certificado TDE (não apenas 'TDECert_TAP')
    -- Busca por certificados com 'TDE' no nome OU que estejam sendo usados para criptografia
    -- Exclui certificados de sistema (##MS_...)
    SELECT CONVERT(CHAR(100), SERVERPROPERTY('Servername')) AS Server,
        name as certificate,
        pvt_key_encryption_type_desc,
        issuer_name,
        subject,
        expiry_date,
        start_date
    FROM sys.certificates WITH(NOLOCK)
    WHERE name NOT LIKE '##%'  -- Excluir certificados de sistema
      AND (
          name LIKE '%TDE%'
          OR EXISTS (
              SELECT 1
              FROM sys.dm_database_encryption_keys dek
              WHERE dek.encryptor_thumbprint = sys.certificates.thumbprint
          )
      )
    """
    
    TDE_DATABASE_STATUS = """
    -- Query para verificar status de TDE por database
    SELECT
        d.name AS database_name,
        d.is_encrypted AS is_encrypted,
        CASE
            WHEN d.is_encrypted = 1 THEN 'Sim'
            ELSE 'Nao'
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
                (SELECT TOP 1
                    CASE dek.encryption_state
                        WHEN 0 THEN 'Nenhum'
                        WHEN 1 THEN 'Nao criptografado'
                        WHEN 2 THEN 'Criptografia em progresso'
                        WHEN 3 THEN 'Criptografado'
                        WHEN 4 THEN 'Alteracao de chave em progresso'
                        WHEN 5 THEN 'Descriptografia em progresso'
                        WHEN 6 THEN 'Alteracao de protecao em progresso'
                        ELSE 'Desconhecido'
                    END
                 FROM sys.dm_database_encryption_keys dek
                 WHERE dek.database_id = d.database_id)
            ELSE NULL
        END AS encryption_state,
        (SELECT TOP 1 dek.key_algorithm + '_' + CAST(dek.key_length AS VARCHAR(10))
         FROM sys.dm_database_encryption_keys dek
         WHERE dek.database_id = d.database_id) AS encryption_algorithm,
        (SELECT TOP 1 dek.encryption_state
         FROM sys.dm_database_encryption_keys dek
         WHERE dek.database_id = d.database_id) AS encryption_state_id
    FROM sys.databases d WITH(NOLOCK)
    WHERE d.database_id > 4  -- Excluir system databases
    AND d.state = 0  -- Apenas databases ONLINE
    ORDER BY d.is_encrypted DESC, d.name
    """

    LOG_SPACE_USAGE = """
    -- Analise de espaco recuperavel por database (DATA + LOG) com drive letter
    -- Usa dynamic SQL batch unico com USE [db] + FILEPROPERTY
    -- Constroi todos os INSERTs em uma unica string e executa com um unico sp_executesql
    -- Assim pyodbc so ve o result set do SELECT final (sem intermediarios)
    SET NOCOUNT ON;

    IF OBJECT_ID('tempdb..#DBSpace') IS NOT NULL DROP TABLE #DBSpace;

    CREATE TABLE #DBSpace (
        database_name SYSNAME,
        file_type VARCHAR(4),
        drive_letter NVARCHAR(3),
        total_MB DECIMAL(12,2),
        used_MB DECIMAL(12,2),
        free_MB DECIMAL(12,2)
    );

    DECLARE @sql NVARCHAR(MAX) = N'';

    SELECT @sql = @sql + N'
    BEGIN TRY
        USE ' + QUOTENAME(name) + N';
        INSERT INTO #DBSpace
        SELECT DB_NAME(),
            CASE type WHEN 0 THEN ''DATA'' ELSE ''LOG'' END,
            UPPER(LEFT(physical_name, 2)),
            CAST(SUM(size) * 8.0 / 1024 AS DECIMAL(12,2)),
            CAST(SUM(FILEPROPERTY(name, ''SpaceUsed'')) * 8.0 / 1024 AS DECIMAL(12,2)),
            CAST(SUM(size - FILEPROPERTY(name, ''SpaceUsed'')) * 8.0 / 1024 AS DECIMAL(12,2))
        FROM sys.database_files
        GROUP BY type, UPPER(LEFT(physical_name, 2));
    END TRY
    BEGIN CATCH END CATCH;
    '
    FROM sys.databases
    WHERE state = 0
      -- 2026-08-05 (consenso sql-deep-reviewer, provado no PRD213): guard canonica
      -- HAS_DBACCESS(name)=1 -- cobre secundarias AG nao-legiveis (erro 976) E
      -- bases sem acesso do sql_monitoring (erro 916: model, DBA_RESOURCE_DB), que
      -- rebentam o USE na COMPILACAO do sub-batch (o TRY/CATCH deste batch unico
      -- nao apanha). Substitui o NOT EXISTS is_primary_replica, que tinha o gap 916
      -- E cegava as secundarias AG LEGIVEIS (readable) -- essas ocupam disco real e
      -- DEVEM aparecer. Mesmo fix na FILE_SPACE_DETAIL (mesmo padrao) e na
      -- LOG_SPACE_USAGE do V6.
      AND HAS_DBACCESS(name) = 1;

    EXEC sp_executesql @sql;

    SELECT
        s.database_name,
        s.file_type,
        s.drive_letter,
        s.total_MB AS total_mb,
        s.used_MB AS used_mb,
        s.free_MB AS free_mb,
        CAST(s.free_MB * 100.0 / NULLIF(s.total_MB, 0) AS DECIMAL(5,2)) AS free_pct,
        d.recovery_model_desc AS recovery_model,
        ISNULL(d.log_reuse_wait_desc, 'NOTHING') AS log_reuse_wait,
        CASE
            WHEN s.database_name = 'tempdb' THEN 'OK'  -- TempDB: never recommend shrink
            WHEN CAST(s.free_MB * 100.0 / NULLIF(s.total_MB, 0) AS DECIMAL(5,2)) > 50 THEN 'HIGH'
            WHEN CAST(s.free_MB * 100.0 / NULLIF(s.total_MB, 0) AS DECIMAL(5,2)) > 25 THEN 'MEDIUM'
            ELSE 'OK'
        END AS shrink_recommendation
    FROM #DBSpace s
    LEFT JOIN sys.databases d ON s.database_name = d.name
    ORDER BY s.free_MB DESC;

    DROP TABLE #DBSpace;
    """

    FILE_SPACE_DETAIL = """
    -- Detalhe por ficheiro individual com SIZE, MAXSIZE, GROWTH e sugestoes
    -- Retorna info para gerar recomendacoes de redimensionamento sem shrink
    SET NOCOUNT ON;

    IF OBJECT_ID('tempdb..#FileDetail') IS NOT NULL DROP TABLE #FileDetail;

    CREATE TABLE #FileDetail (
        database_name SYSNAME,
        logical_name SYSNAME,
        file_type VARCHAR(4),
        physical_name NVARCHAR(512),
        drive_letter NVARCHAR(3),
        size_mb DECIMAL(12,2),
        used_mb DECIMAL(12,2),
        free_mb DECIMAL(12,2),
        max_size_pages INT,
        growth_pages INT,
        is_percent_growth BIT
    );

    DECLARE @sql NVARCHAR(MAX) = N'';

    SELECT @sql = @sql + N'
    BEGIN TRY
        USE ' + QUOTENAME(name) + N';
        INSERT INTO #FileDetail
        SELECT DB_NAME(),
            name,
            CASE type WHEN 0 THEN ''DATA'' ELSE ''LOG'' END,
            physical_name,
            UPPER(LEFT(physical_name, 2)),
            CAST(size * 8.0 / 1024 AS DECIMAL(12,2)),
            CAST(FILEPROPERTY(name, ''SpaceUsed'') * 8.0 / 1024 AS DECIMAL(12,2)),
            CAST((size - FILEPROPERTY(name, ''SpaceUsed'')) * 8.0 / 1024 AS DECIMAL(12,2)),
            max_size,
            growth,
            is_percent_growth
        FROM sys.database_files;
    END TRY
    BEGIN CATCH END CATCH;
    '
    FROM sys.databases
    WHERE state = 0
      -- 2026-07-31: DB em AG com data movement suspenso passa em state=0 mas o
      -- USE rebenta na COMPILACAO do sub-bloco (erro 976), que o TRY/CATCH do
      -- proprio batch nao apanha -- derrubava o endpoint inteiro (500 no
      -- SQLHDSPRD213 por causa da MAP_SampleDB).
      -- 2026-08-05 (provado na BD viva do PRD213, 15 bases state=0): a guarda
      -- CANONICA e' HAS_DBACCESS(name)=1 -- devolve 0 tanto para secundarias AG
      -- nao-legiveis (erro 976) COMO para bases sem permissao do sql_monitoring
      -- (erro 916: model, DBA_RESOURCE_DB), que rebentam o USE pelo MESMO
      -- mecanismo. Substitui e supera as duas tentativas anteriores:
      --   * DATABASEPROPERTYEX(Collation) IS NOT NULL -> a collation vem da
      --     metadata do master, devolvida na mesma para secundarias -> NAO exclui.
      --   * NOT EXISTS is_primary_replica -> cobre as AG mas deixa passar a model
      --     e a DBA_RESOURCE_DB (sem acesso, nao-AG) -> 916. (era o fix do V6.)
      -- No PRD213: das 15 state=0, so 3 (master/tempdb/msdb) tem HAS_DBACCESS=1;
      -- as outras 12 (10 AG + model + DBA_RESOURCE_DB) sairiam.
      -- SEMANTICA P/ A UI: a ausencia de uma DB no resultado nao e' "sem
      -- ficheiros" nem "saudavel" -- e' "nao mensuravel agora".
      AND HAS_DBACCESS(name) = 1;

    EXEC sp_executesql @sql;

    SELECT
        f.database_name,
        f.logical_name,
        f.file_type,
        f.physical_name,
        f.drive_letter,
        f.size_mb,
        f.used_mb,
        f.free_mb,
        CAST(CASE WHEN f.used_mb > 0 THEN f.used_mb * 100.0 / f.size_mb ELSE 0 END AS DECIMAL(5,1)) AS used_pct,
        CASE WHEN f.max_size_pages = -1 THEN -1
             WHEN f.max_size_pages = 0 THEN 0
             ELSE CAST(f.max_size_pages * 8.0 / 1024 AS DECIMAL(12,2))
        END AS max_size_mb,
        CASE WHEN f.is_percent_growth = 1 THEN f.growth_pages
             ELSE CAST(f.growth_pages * 8.0 / 1024 AS DECIMAL(12,2))
        END AS growth_value,
        f.is_percent_growth,
        -- Sugestao: usado + 20% margem (minimo 64 MB)
        CAST(CASE WHEN f.used_mb * 1.2 < 64 THEN 64 ELSE f.used_mb * 1.2 END AS DECIMAL(12,2)) AS suggested_size_mb,
        -- Espaco libertavel reduzindo SIZE (sem shrink)
        CAST(CASE WHEN f.size_mb > (CASE WHEN f.used_mb * 1.2 < 64 THEN 64 ELSE f.used_mb * 1.2 END)
             THEN f.size_mb - (CASE WHEN f.used_mb * 1.2 < 64 THEN 64 ELSE f.used_mb * 1.2 END)
             ELSE 0 END AS DECIMAL(12,2)) AS saveable_mb,
        d.recovery_model_desc AS recovery_model
    FROM #FileDetail f
    LEFT JOIN sys.databases d ON f.database_name = d.name
    ORDER BY f.drive_letter, f.free_mb DESC;

    DROP TABLE #FileDetail;
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
    -- Query otimizada alinhada com KPI canónico: conta sessões bloqueadas onde login_name, host_name ou program_name não são nulos
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
    SELECT TOP 50
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
        INNER JOIN sys.databases db WITH(NOLOCK)
            ON ips.database_id = db.database_id
        INNER JOIN sys.indexes si WITH(NOLOCK)
            ON ips.object_id = si.object_id AND ips.index_id = si.index_id
        INNER JOIN sys.tables st WITH(NOLOCK)
            ON ips.object_id = st.object_id
        INNER JOIN sys.schemas ss WITH(NOLOCK)
            ON st.schema_id = ss.schema_id
        WHERE db.state_desc = 'ONLINE'  -- Excluir databases em RESTORING, OFFLINE, etc.
        AND db.is_read_only = 0  -- Excluir databases read-only
        AND ips.avg_fragmentation_in_percent > 10  -- Filtrar apenas >= 10%
        AND ips.page_count > 500  -- Filtrar indices pequenos (>4MB)
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
    -- Query alinhada com a lógica do KPI canónico: KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
    -- A view canónica filtra por PRI_SYNCH_HEALTH <> 'HEALTHY' or SEC_SYNCH_HEALTH <> 'HEALTHY'
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
    -- Query alinhada com a lógica do KPI canónico: conta sessões bloqueadas onde login_name, host_name ou program_name não são nulos
    -- A view canónica KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW conta: count(1) from KPI_MSSQL_BLOCKED_SESSIONS
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
        AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)  -- Alinhado com KPI canónico
        
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
        AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)  -- Alinhado com KPI canónico
        
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
        AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)  -- Alinhado com KPI canónico
    )
    SELECT
        abs.session_id,
        abs.blocking_session_id,
        abs.wait_type,
        abs.wait_time,
        CAST(abs.wait_time / 1000.0 AS DECIMAL(18,2)) as WaitTimeSec,
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
    WHERE ((abs.blocking_session_id > 0 AND abs.blocking_session_id <> abs.session_id)  -- Excluir sessões bloqueando a si mesmas
       OR (abs.wait_type LIKE 'LCK_%' AND (abs.blocking_session_id IS NULL OR abs.blocking_session_id = 0 OR abs.blocking_session_id <> abs.session_id)))
      AND abs.wait_time >= 45000  -- Threshold: ignorar locks < 45 segundos (contenção normal)
    ORDER BY abs.wait_time DESC, abs.blocking_session_id, abs.session_id
    """
    
    DEADLOCKS_ANALYSIS = """
    -- Análise de Deadlocks
    -- Busca informações de deadlocks do Extended Events ou Error Log
    -- SQL Server 2012+ usa Extended Events, versões anteriores usam Error Log
    
    -- 1. Deadlocks do Extended Events (SQL Server 2012+)
    IF EXISTS (SELECT * FROM sys.dm_xe_sessions WHERE name = 'system_health')
    BEGIN
        SELECT 
            CAST(xed.value('(event/@timestamp)[1]', 'datetime2') AS datetime) AS deadlock_time,
            CAST(xed.value('(event/data[@name="database_id"]/value)[1]', 'int') AS int) AS database_id,
            DB_NAME(CAST(xed.value('(event/data[@name="database_id"]/value)[1]', 'int') AS int)) AS database_name,
            CAST(xed.value('(event/data[@name="lock_mode"]/text)[1]', 'nvarchar(50)') AS nvarchar(50)) AS lock_mode,
            CAST(xed.value('(event/data[@name="resource_owner_type"]/text)[1]', 'nvarchar(50)') AS nvarchar(50)) AS resource_owner_type,
            CAST(xed.value('(event/data[@name="deadlock_chain_id"]/value)[1]', 'int') AS int) AS deadlock_chain_id,
            CAST(xed.value('(event/data[@name="process_id"]/value)[1]', 'int') AS int) AS process_id,
            CAST(xed.value('(event/data[@name="waiter_type"]/text)[1]', 'nvarchar(50)') AS nvarchar(50)) AS waiter_type,
            CAST(xed.value('(event/action[@name="client_app_name"]/value)[1]', 'nvarchar(255)') AS nvarchar(255)) AS client_app_name,
            CAST(xed.value('(event/action[@name="client_hostname"]/value)[1]', 'nvarchar(255)') AS nvarchar(255)) AS client_hostname,
            CAST(xed.value('(event/action[@name="username"]/value)[1]', 'nvarchar(255)') AS nvarchar(255)) AS username,
            CAST(xed.value('(event/action[@name="sql_text"]/value)[1]', 'nvarchar(max)') AS nvarchar(max)) AS sql_text,
            CAST(xed.query('(event/data[@name="xml_report"]/value/deadlock)[1]') AS xml) AS deadlock_xml,
            'Extended Events' AS source
        FROM (
            SELECT CAST(target_data AS XML) AS target_data
            FROM sys.dm_xe_session_targets st
            INNER JOIN sys.dm_xe_sessions s ON s.address = st.event_session_address
            WHERE s.name = 'system_health'
            AND st.target_name = 'ring_buffer'
        ) AS data
        CROSS APPLY target_data.nodes('//RingBufferTarget/event') AS xed(xed)
        WHERE xed.value('@name', 'nvarchar(50)') = 'xml_deadlock_report'
        AND CAST(xed.value('(event/@timestamp)[1]', 'datetime2') AS datetime) >= DATEADD(HOUR, -24, GETDATE())
        ORDER BY deadlock_time DESC
    END
    ELSE
    BEGIN
        -- 2. Deadlocks do Error Log (SQL Server 2008/2008 R2 ou quando Extended Events não disponível)
        -- Nota: Error Log não tem informações estruturadas de deadlock, apenas mensagens de texto
        SELECT 
            GETDATE() AS deadlock_time,
            NULL AS database_id,
            'N/A' AS database_name,
            'N/A' AS lock_mode,
            'N/A' AS resource_owner_type,
            NULL AS deadlock_chain_id,
            NULL AS process_id,
            'N/A' AS waiter_type,
            'N/A' AS client_app_name,
            'N/A' AS client_hostname,
            'N/A' AS username,
            'Deadlock information not available from Error Log. Enable Extended Events for detailed deadlock analysis.' AS sql_text,
            NULL AS deadlock_xml,
            'Error Log' AS source
        WHERE 1=0  -- Retornar vazio se não houver Extended Events
    END
    -- FIND-20260612-103 (Wave W+1): removido UNION ALL orfao + ORDER BY orfao apos
    -- o bloco IF/ELSE — erro de sintaxe que fazia o batch NUNCA compilar (endpoint
    -- /api/queries/deadlocks 500 em todas as execucoes). ORDER BY movido para
    -- dentro do branch Extended Events (o ELSE devolve 0 rows via WHERE 1=0).
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
    -- Query UNIVERSAL para monitoramento de Transaction Log - TODAS as databases
    -- Compativel com SQL Server 2008+ usando DBCC SQLPERF
    -- Ordena por consumo de log (percentual e MB usado) para identificar problemas rapidamente
    -- AG-aware: ignora databases em secundaria AG inacessivel
    SET NOCOUNT ON;

    -- Criar tabela temporaria para armazenar resultado do DBCC SQLPERF
    IF OBJECT_ID('tempdb..#LogSpace') IS NOT NULL DROP TABLE #LogSpace;
    CREATE TABLE #LogSpace (
        DatabaseName NVARCHAR(128),
        LogSizeMB DECIMAL(18,2),
        LogSpaceUsedPercent DECIMAL(5,2),
        Status INT
    );

    -- Inserir dados do DBCC SQLPERF com protecao contra AGs inacessiveis
    BEGIN TRY
        INSERT INTO #LogSpace
        EXEC('DBCC SQLPERF(LOGSPACE)');
    END TRY
    BEGIN CATCH
        -- DBCC SQLPERF falhou (ex: database em AG secundaria inacessivel)
        -- Fallback: inserir apenas databases acessiveis com dados de sys.master_files
        INSERT INTO #LogSpace (DatabaseName, LogSizeMB, LogSpaceUsedPercent, Status)
        SELECT
            d.name,
            CAST(SUM(mf.size) * 8.0 / 1024 AS DECIMAL(18,2)),
            0.0,
            1
        FROM sys.databases d WITH(NOLOCK)
        INNER JOIN sys.master_files mf WITH(NOLOCK) ON d.database_id = mf.database_id AND mf.type = 1
        WHERE d.state = 0
          AND HAS_DBACCESS(d.name) = 1
        GROUP BY d.name;
    END CATCH

    -- Selecionar e calcular metricas
    -- Excluir databases em AG onde esta instancia e a secundaria (nao acessiveis)
    SELECT
        ls.DatabaseName as database_name,
        ls.LogSizeMB as total_log_mb,
        CAST(ls.LogSizeMB * ls.LogSpaceUsedPercent / 100.0 AS DECIMAL(12,2)) as used_log_mb,
        CAST(ls.LogSizeMB * (100.0 - ls.LogSpaceUsedPercent) / 100.0 AS DECIMAL(12,2)) as free_log_mb,
        ls.LogSpaceUsedPercent as log_used_percent,
        ISNULL(d.log_reuse_wait_desc, 'NOTHING') as log_reuse_wait_desc,
        CASE
            WHEN ls.LogSpaceUsedPercent > 90 THEN 'CRITICAL'
            WHEN ls.LogSpaceUsedPercent > 75 THEN 'HIGH'
            WHEN ls.LogSpaceUsedPercent > 60 THEN 'MEDIUM'
            ELSE 'OK'
        END as alert_level,
        CASE
            WHEN ISNULL(d.log_reuse_wait_desc, 'NOTHING') != 'NOTHING'
            THEN 'Log reuse wait: ' + d.log_reuse_wait_desc
            ELSE 'Normal'
        END as reuse_status
    FROM #LogSpace ls
    LEFT JOIN sys.databases d WITH(NOLOCK) ON ls.DatabaseName = d.name
    WHERE ls.LogSizeMB > 0  -- Apenas databases com log configurado
      AND (d.state IS NULL OR d.state = 0)  -- ONLINE ou sem match no JOIN
      -- Excluir databases em AG secundaria inacessivel nesta instancia
      AND NOT EXISTS (
          SELECT 1 FROM sys.dm_hadr_database_replica_states drs WITH(NOLOCK)
          WHERE drs.database_id = d.database_id
            AND drs.is_local = 1
            AND ISNULL(drs.is_primary_replica, 1) = 0
      )
    ORDER BY
        ls.LogSpaceUsedPercent DESC,
        used_log_mb DESC;

    DROP TABLE #LogSpace;
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
    -- =============================================================================
    -- TempDB Monitoring - Overview + Vilões (Consumidores)
    -- v2.6 - Adicionado file_size_on_disk_mb e disk_free_mb para monitorar disco
    -- =============================================================================

    -- Parte 1: Visão geral do TempDB
    -- IMPORTANTE: Mostra DOIS tipos de métricas:
    --   1. Espaço INTERNO do arquivo (usado vs livre dentro do .mdf/.ndf)
    --   2. Espaço do ARQUIVO em disco (tamanho real do arquivo)
    -- O arquivo pode estar enorme (ex: 300GB) mas internamente vazio!
    SELECT
        'TempDB_Overview' as metric_type,
        -- Espaço INTERNO do TempDB (dentro do arquivo)
        CAST(SUM(fsu.total_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as total_mb,
        CAST(SUM(fsu.total_page_count - fsu.unallocated_extent_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as used_mb,
        CAST(SUM(fsu.unallocated_extent_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as free_mb,
        CAST(SUM(fsu.total_page_count - fsu.unallocated_extent_page_count) * 100.0 /
             NULLIF(SUM(fsu.total_page_count), 0) AS DECIMAL(5,2)) as used_percent,
        -- Tamanho do ARQUIVO em disco (database_files.size)
        (SELECT CAST(SUM(size) * 8.0 / 1024 AS DECIMAL(12,2)) FROM tempdb.sys.database_files WHERE type_desc = 'ROWS') as file_size_on_disk_mb,
        -- Espaço LIVRE no drive onde está o TempDB
        (SELECT CAST(available_bytes / 1024.0 / 1024 AS DECIMAL(12,2))
         FROM sys.dm_os_volume_stats(2, 1)) as disk_free_mb,
        -- Tamanho total do drive
        (SELECT CAST(total_bytes / 1024.0 / 1024 AS DECIMAL(12,2))
         FROM sys.dm_os_volume_stats(2, 1)) as disk_total_mb,
        NULL as session_id,
        NULL as login_name,
        NULL as host_name,
        NULL as program_name,
        NULL as database_name,
        NULL as login_time,
        NULL as last_request_start_time,
        NULL as last_request_end_time,
        NULL as idle_time_minutes,
        NULL as user_objects_mb,
        NULL as internal_objects_mb,
        0 as total_pages_used,
        NULL as space_used_mb,
        NULL as percent_of_tempdb,
        NULL as status,
        NULL as command,
        NULL as wait_type,
        NULL as wait_time_ms,
        NULL as cpu_time_ms,
        NULL as query_text,
        0 as sort_order
    FROM tempdb.sys.dm_db_file_space_usage fsu WITH(NOLOCK)

    UNION ALL

    -- Parte 2: Vilões do TempDB - Sessões que mais consomem
    -- Usa valores LÍQUIDOS (alloc - dealloc) para mostrar uso real atual
    -- idle_time_minutes: tempo desde a última requisição terminar (para sleeping)
    SELECT
        'TempDB_Villain' as metric_type,
        NULL as total_mb,
        NULL as used_mb,
        NULL as free_mb,
        NULL as used_percent,
        NULL as file_size_on_disk_mb,
        NULL as disk_free_mb,
        NULL as disk_total_mb,
        su.session_id,
        es.login_name,
        es.host_name,
        es.program_name,
        d.name as database_name,
        es.login_time,
        es.last_request_start_time,
        es.last_request_end_time,
        -- Tempo idle em minutos (só faz sentido para sleeping)
        CASE
            WHEN es.status = 'sleeping' AND es.last_request_end_time IS NOT NULL
            THEN DATEDIFF(MINUTE, es.last_request_end_time, GETDATE())
            ELSE NULL
        END as idle_time_minutes,
        -- Uso líquido (alocado - desalocado) em MB
        CAST((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as user_objects_mb,
        CAST((su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as internal_objects_mb,
        ((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) +
         (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count)) as total_pages_used,
        CAST(((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) +
              (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count)) * 8.0 / 1024 AS DECIMAL(12,2)) as space_used_mb,
        CAST(((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) +
              (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count)) * 100.0 /
            NULLIF((SELECT SUM(size) FROM tempdb.sys.database_files WHERE type_desc = 'ROWS'), 0) AS DECIMAL(5,2)) as percent_of_tempdb,
        COALESCE(r.status, es.status) as status,
        r.command,
        r.wait_type,
        r.wait_time as wait_time_ms,
        r.cpu_time as cpu_time_ms,
        CASE
            WHEN r.sql_handle IS NOT NULL THEN
                SUBSTRING(t.text, (r.statement_start_offset/2) + 1,
                    ((CASE r.statement_end_offset
                        WHEN -1 THEN DATALENGTH(t.text)
                        ELSE r.statement_end_offset
                    END - r.statement_start_offset)/2) + 1)
            ELSE t2.text
        END as query_text,
        1 as sort_order
    FROM tempdb.sys.dm_db_session_space_usage su WITH(NOLOCK)
    INNER JOIN sys.dm_exec_sessions es WITH(NOLOCK) ON su.session_id = es.session_id
    LEFT JOIN sys.databases d WITH(NOLOCK) ON es.database_id = d.database_id
    LEFT JOIN sys.dm_exec_requests r WITH(NOLOCK) ON su.session_id = r.session_id
    LEFT JOIN sys.dm_exec_connections ec WITH(NOLOCK) ON su.session_id = ec.session_id
    OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
    OUTER APPLY sys.dm_exec_sql_text(ec.most_recent_sql_handle) t2
    WHERE ((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) +
           (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count)) > 0
      AND su.session_id > 50
    ORDER BY sort_order ASC, total_pages_used DESC, last_request_start_time DESC
    """

    TEMPDB_GROWTH_ANALYSIS = """
    -- =============================================================================
    -- TempDB Growth Analysis - Análise de Crescimento e Configuração
    -- v1.5 - MinimumSize = SpaceUsed (até onde SHRINK consegue reduzir)
    -- ATUAL = tamanho do arquivo após auto-growths
    -- MIN SIZE = espaço usado (último extent alocado) - limite do SHRINK
    -- =============================================================================

    -- Configuração atual dos arquivos do TempDB
    SELECT
        'TempDB_Config' as analysis_type,
        mf.file_id,
        mf.name as file_name,
        mf.type_desc as file_type,
        mf.physical_name,
        -- Tamanho ATUAL do arquivo em disco (após auto-growths)
        CAST(mf.size * 8.0 / 1024 AS DECIMAL(12,2)) as current_size_mb,
        CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(12,2)) as current_size_gb,
        -- =====================================================================
        -- MINIMUM SIZE = Espaço usado dentro do arquivo (SpaceUsed)
        -- Este é o MÍNIMO até onde DBCC SHRINKFILE consegue reduzir!
        -- SHRINK não pode reduzir abaixo do último extent alocado.
        -- Se MinSize ≈ CurrentSize, SHRINK não vai reduzir nada significativo.
        -- =====================================================================
        CAST(FILEPROPERTY(mf.name, 'SpaceUsed') * 8.0 / 1024 AS DECIMAL(12,2)) as minimum_size_mb,
        -- Uso interno real (o que está REALMENTE sendo usado dentro do arquivo)
        ISNULL(CAST((fsu.user_object_reserved_page_count +
                     fsu.internal_object_reserved_page_count +
                     fsu.version_store_reserved_page_count +
                     fsu.mixed_extent_page_count) * 8.0 / 1024 AS DECIMAL(12,2)), 0) as real_used_mb,
        -- Espaço livre DENTRO do arquivo (pode ser reutilizado, mas não liberado para o disco)
        ISNULL(CAST(fsu.unallocated_extent_page_count * 8.0 / 1024 AS DECIMAL(12,2)), 0) as internal_free_mb,
        -- Potencial de SHRINK = Atual - MinSize (quanto SHRINK pode recuperar)
        CAST(
            CASE
                WHEN mf.size * 8.0 / 1024 > FILEPROPERTY(mf.name, 'SpaceUsed') * 8.0 / 1024
                THEN (mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) * 8.0 / 1024
                ELSE 0
            END AS DECIMAL(12,2)
        ) as shrink_potential_mb,
        -- Para referência: tamanho do Model (tamanho inicial padrão do TempDB)
        (SELECT CAST(size * 8.0 / 1024 AS DECIMAL(12,2))
         FROM sys.master_files WHERE database_id = 3 AND type = 0) as model_size_mb,
        -- Tamanho máximo configurado
        CASE
            WHEN mf.max_size = -1 THEN 'UNLIMITED'
            WHEN mf.max_size = 0 THEN 'NO GROWTH'
            ELSE CAST(CAST(mf.max_size * 8.0 / 1024 / 1024 AS DECIMAL(12,2)) AS VARCHAR(20)) + ' GB'
        END as max_size,
        -- Configuração de crescimento
        CASE
            WHEN mf.growth = 0 THEN 'NO GROWTH'
            WHEN mf.is_percent_growth = 1 THEN CAST(mf.growth AS VARCHAR(10)) + '%'
            ELSE CAST(CAST(mf.growth * 8.0 / 1024 AS DECIMAL(12,2)) AS VARCHAR(20)) + ' MB'
        END as growth_increment,
        mf.is_percent_growth,
        -- Uso interno (para compatibilidade)
        ISNULL(CAST(fsu.total_page_count * 8.0 / 1024 AS DECIMAL(12,2)), CAST(mf.size * 8.0 / 1024 AS DECIMAL(12,2))) as internal_total_mb,
        -- Uso real (user + internal + version store)
        ISNULL(CAST((fsu.user_object_reserved_page_count +
                     fsu.internal_object_reserved_page_count +
                     fsu.version_store_reserved_page_count) * 8.0 / 1024 AS DECIMAL(12,2)), 0) as internal_used_mb,
        -- % de uso real dentro do arquivo
        CAST(
            CASE
                WHEN fsu.total_page_count > 0 THEN
                    ((fsu.user_object_reserved_page_count +
                      fsu.internal_object_reserved_page_count +
                      fsu.version_store_reserved_page_count) * 100.0 / fsu.total_page_count)
                ELSE 0
            END AS DECIMAL(5,2)
        ) as usage_percent,
        -- % livre dentro do arquivo (espaço que pode ser reutilizado)
        CAST(
            CASE
                WHEN fsu.total_page_count > 0 THEN
                    (fsu.unallocated_extent_page_count * 100.0 / fsu.total_page_count)
                ELSE 0
            END AS DECIMAL(5,2)
        ) as shrinkable_percent,
        -- Informações do disco
        ISNULL(vs.volume_mount_point, LEFT(mf.physical_name, 3)) as drive,
        COALESCE(CAST(vs.total_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(12,2)), 0) as drive_total_gb,
        COALESCE(CAST(vs.available_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(12,2)), 0) as drive_free_gb,
        COALESCE(CAST((vs.total_bytes - vs.available_bytes) * 100.0 / NULLIF(vs.total_bytes, 0) AS DECIMAL(5,2)), 0) as drive_used_percent,
        NULL as event_time,
        NULL as event_description,
        NULL as growth_mb,
        NULL as duration_ms
    FROM sys.master_files mf WITH(NOLOCK)
    LEFT JOIN tempdb.sys.dm_db_file_space_usage fsu WITH(NOLOCK) ON mf.file_id = fsu.file_id
    OUTER APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    WHERE mf.database_id = 2  -- TempDB
      AND mf.type_desc = 'ROWS'
    ORDER BY mf.file_id
    """

    TEMPDB_GROWTH_EVENTS = """
    -- =============================================================================
    -- TempDB Growth Events - Histórico de Auto-Growth do Default Trace
    -- v1.2 - Inclui mais detalhes: LoginName, HostName, ApplicationName, SPID
    -- IMPORTANTE: Default Trace captura QUEM estava executando no momento do growth
    -- =============================================================================
    SELECT TOP 100
        'TempDB_Growth_Event' as analysis_type,
        StartTime as event_time,
        CASE EventClass
            WHEN 92 THEN 'Data File Auto Grow'
            WHEN 93 THEN 'Log File Auto Grow'
            WHEN 94 THEN 'Data File Auto Shrink'
            WHEN 95 THEN 'Log File Auto Shrink'
        END as event_description,
        FileName as file_name,
        CAST(IntegerData * 8.0 / 1024 AS DECIMAL(12,2)) as growth_mb,
        Duration / 1000 as duration_ms,
        -- QUEM causou o crescimento (capturado no momento do evento)
        LoginName as login_name,
        HostName as host_name,
        ApplicationName as application_name,
        SPID as session_id,
        -- TextData pode conter a query que estava executando
        TextData as query_text
    FROM ::fn_trace_gettable(
        (SELECT REVERSE(SUBSTRING(REVERSE(path),
            CHARINDEX('\\', REVERSE(path)), 256)) + 'log.trc'
         FROM sys.traces WHERE is_default = 1), DEFAULT
    )
    WHERE DatabaseName = 'tempdb'
      AND EventClass IN (92, 93, 94, 95)
    ORDER BY StartTime DESC
    """

    TEMPDB_SIZING_ANALYSIS = """
    -- =============================================================================
    -- TempDB Sizing Analysis - Análise para dimensionamento correto
    -- v1.0 - Calcula tamanho mínimo recomendado baseado no uso real
    -- =============================================================================

    -- Uso atual detalhado por categoria
    SELECT
        'Current_Usage' as analysis_type,
        SUM(user_object_reserved_page_count) * 8.0 / 1024 AS user_objects_mb,
        SUM(internal_object_reserved_page_count) * 8.0 / 1024 AS internal_objects_mb,
        SUM(version_store_reserved_page_count) * 8.0 / 1024 AS version_store_mb,
        SUM(unallocated_extent_page_count) * 8.0 / 1024 AS free_space_mb,
        SUM(total_page_count) * 8.0 / 1024 AS total_tempdb_mb,
        -- Uso efetivo (tudo menos free)
        (SUM(total_page_count) - SUM(unallocated_extent_page_count)) * 8.0 / 1024 AS used_mb,
        -- Percentual de uso
        CAST((SUM(total_page_count) - SUM(unallocated_extent_page_count)) * 100.0 /
             NULLIF(SUM(total_page_count), 0) AS DECIMAL(5,2)) AS used_percent,
        NULL as file_count,
        NULL as max_file_size_mb,
        NULL as contention_waits,
        NULL as sql_server_start_time
    FROM tempdb.sys.dm_db_file_space_usage WITH(NOLOCK)

    UNION ALL

    -- Pico histórico (tamanho atual dos arquivos = máximo desde o restart)
    SELECT
        'Peak_Since_Restart' as analysis_type,
        NULL as user_objects_mb,
        NULL as internal_objects_mb,
        NULL as version_store_mb,
        NULL as free_space_mb,
        SUM(size) * 8.0 / 1024 AS total_tempdb_mb,
        NULL as used_mb,
        NULL as used_percent,
        COUNT(*) as file_count,
        MAX(size) * 8.0 / 1024 AS max_file_size_mb,
        NULL as contention_waits,
        (SELECT sqlserver_start_time FROM sys.dm_os_sys_info) as sql_server_start_time
    FROM sys.master_files WITH(NOLOCK)
    WHERE database_id = 2 AND type_desc = 'ROWS'

    UNION ALL

    -- Contenção (indica subdimensionamento)
    SELECT
        'Contention_Check' as analysis_type,
        NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
        SUM(waiting_tasks_count) as contention_waits,
        NULL as sql_server_start_time
    FROM sys.dm_os_wait_stats WITH(NOLOCK)
    WHERE wait_type IN ('PAGELATCH_UP', 'PAGELATCH_EX', 'PAGELATCH_SH')
    """

    TEMPDB_HEAVY_CONSUMERS_HISTORY = """
    -- =============================================================================
    -- TempDB Heavy Consumers - Queries que mais usaram TempDB (Plan Cache)
    -- v1.0 - Analisa o Plan Cache para encontrar queries com alto uso de TempDB
    -- NOTA: Não é histórico real, mas mostra queries conhecidas por usar TempDB
    -- =============================================================================

    -- Parte 1: Queries com maiores spills (hash/sort spills para TempDB)
    SELECT TOP 20
        'Heavy_Spill_Query' as analysis_type,
        qs.creation_time as plan_created,
        qs.last_execution_time,
        qs.execution_count,
        -- Métricas de spill (indicam uso de TempDB)
        CAST(qs.total_spills / NULLIF(qs.execution_count, 0) AS DECIMAL(12,2)) as avg_spills_per_exec,
        qs.total_spills,
        qs.max_spills,
        -- Outras métricas
        CAST(qs.total_worker_time / 1000.0 / NULLIF(qs.execution_count, 0) AS DECIMAL(12,2)) as avg_cpu_ms,
        CAST(qs.total_logical_reads / NULLIF(qs.execution_count, 0) AS DECIMAL(12,0)) as avg_logical_reads,
        CAST(qs.total_elapsed_time / 1000.0 / NULLIF(qs.execution_count, 0) AS DECIMAL(12,2)) as avg_elapsed_ms,
        -- Texto da query
        SUBSTRING(qt.text, (qs.statement_start_offset/2) + 1,
            ((CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(qt.text)
                ELSE qs.statement_end_offset
            END - qs.statement_start_offset)/2) + 1) as query_text,
        -- Identificação
        DB_NAME(qt.dbid) as database_name,
        OBJECT_NAME(qt.objectid, qt.dbid) as object_name
    FROM sys.dm_exec_query_stats qs WITH(NOLOCK)
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
    WHERE qs.total_spills > 0  -- Apenas queries com spills
    ORDER BY qs.total_spills DESC

    UNION ALL

    -- Parte 2: Sessões com maior uso histórico de TempDB (desde restart)
    SELECT TOP 20
        'Session_Cumulative_Usage' as analysis_type,
        es.login_time as plan_created,
        es.last_request_end_time as last_execution_time,
        NULL as execution_count,
        NULL as avg_spills_per_exec,
        NULL as total_spills,
        NULL as max_spills,
        NULL as avg_cpu_ms,
        NULL as avg_logical_reads,
        NULL as avg_elapsed_ms,
        NULL as query_text,
        d.name as database_name,
        es.program_name as object_name
    FROM tempdb.sys.dm_db_session_space_usage su WITH(NOLOCK)
    INNER JOIN sys.dm_exec_sessions es WITH(NOLOCK) ON su.session_id = es.session_id
    LEFT JOIN sys.databases d WITH(NOLOCK) ON es.database_id = d.database_id
    WHERE su.session_id > 50
      AND (su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) > 1000  -- Mais de ~8MB alocados total
    ORDER BY (su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) DESC
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
    -- Query ENHANCED para estatísticas desatualizadas (v1.4.9)
    -- Itera sobre todas as databases do usuário
    -- Fornece script SQL pronto e priorização por score

    IF OBJECT_ID('tempdb..#OutdatedStats') IS NOT NULL DROP TABLE #OutdatedStats;

    CREATE TABLE #OutdatedStats (
        database_name NVARCHAR(128),
        schema_name NVARCHAR(128),
        table_name NVARCHAR(128),
        stats_name NVARCHAR(128),
        stats_type NVARCHAR(50),
        last_updated DATETIME,
        days_since_update INT,
        hours_since_update INT,
        table_rows BIGINT,
        modifications BIGINT,
        modification_percent DECIMAL(5,2),
        urgency_level NVARCHAR(20),
        priority INT,
        priority_score INT,
        update_script NVARCHAR(MAX)
    );

    -- Cursor explicito para iterar databases (substitui sp_MSforeachdb)
    DECLARE @dbname NVARCHAR(128);
    DECLARE @sql NVARCHAR(MAX);

    DECLARE db_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT name FROM sys.databases WITH(NOLOCK)
        WHERE database_id > 4
          AND name NOT IN ('master', 'tempdb', 'model', 'msdb')
          AND state_desc = 'ONLINE'
          AND DATABASEPROPERTYEX(name, 'Updateability') = 'READ_WRITE';

    OPEN db_cursor;
    FETCH NEXT FROM db_cursor INTO @dbname;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        BEGIN TRY
            SET @sql = N'
            USE ' + QUOTENAME(@dbname) + N';
            INSERT INTO #OutdatedStats
            SELECT
                DB_NAME() as database_name,
                schema_name,
                table_name,
                stats_name,
                stats_type,
                last_updated,
                days_since_update,
                hours_since_update,
                table_rows,
                modification_counter as modifications,
                modification_percent,
                urgency_level,
                priority,
                priority_score,
                ''USE ['' + DB_NAME() + '']; UPDATE STATISTICS ['' + schema_name + ''].['' + table_name + ''] ['' + stats_name + '']'' +
                CASE
                    WHEN days_since_update > 7 OR modification_percent > 15 THEN '' WITH FULLSCAN;''
                    WHEN days_since_update > 3 OR modification_percent > 5 THEN '' WITH SAMPLE 25 PERCENT;''
                    ELSE '';''
                END as update_script
            FROM (
                SELECT
                    OBJECT_SCHEMA_NAME(s.object_id) as schema_name,
                    OBJECT_NAME(s.object_id) as table_name,
                    s.name as stats_name,
                    sp.last_updated,
                    sp.rows as table_rows,
                    sp.modification_counter,
                    CASE
                        WHEN s.auto_created = 1 THEN ''AUTO_CREATED''
                        WHEN s.user_created = 1 THEN ''USER_CREATED''
                        WHEN EXISTS (SELECT 1 FROM sys.indexes i WITH(NOLOCK) WHERE i.object_id = s.object_id AND i.name = s.name) THEN ''INDEX_STATS''
                        ELSE ''COLUMN_STATS''
                    END as stats_type,
                    CASE WHEN sp.rows > 0 THEN CAST((sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2)) ELSE 0 END as modification_percent,
                    CASE WHEN sp.last_updated IS NOT NULL THEN DATEDIFF(day, sp.last_updated, GETDATE()) ELSE NULL END as days_since_update,
                    CASE WHEN sp.last_updated IS NOT NULL THEN DATEDIFF(hour, sp.last_updated, GETDATE()) ELSE NULL END as hours_since_update,
                    CASE
                        WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 14 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 20 THEN ''URGENT''
                        WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 7 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 10 THEN ''HIGH''
                        WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 3 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 5 THEN ''MEDIUM''
                        ELSE ''OK''
                    END as urgency_level,
                    CASE
                        WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 14 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 20 THEN 1
                        WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 7 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 10 THEN 2
                        WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 3 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 5 THEN 3
                        ELSE 4
                    END as priority,
                    (
                        (CASE WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 14 THEN 30
                              WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 7 THEN 20
                              WHEN DATEDIFF(day, sp.last_updated, GETDATE()) > 3 THEN 10
                              ELSE COALESCE(DATEDIFF(day, sp.last_updated, GETDATE()), 0) END) +
                        (CASE WHEN (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 25 THEN 25
                              WHEN (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 15 THEN 15
                              WHEN (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) > 5 THEN 10
                              ELSE COALESCE(CAST((sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) AS INT), 0) END) +
                        (CASE WHEN sp.rows > 100000 THEN 15 WHEN sp.rows > 10000 THEN 10 WHEN sp.rows > 1000 THEN 5 ELSE 0 END)
                    ) as priority_score
                FROM sys.stats s WITH(NOLOCK)
                CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
                WHERE OBJECTPROPERTY(s.object_id, ''IsUserTable'') = 1
                AND sp.rows >= 100
                AND sp.last_updated IS NOT NULL
            ) AS StatsData
            WHERE days_since_update >= 3 OR modification_percent >= 5 OR priority_score > 5;
            ';

            EXEC sp_executesql @sql;
        END TRY
        BEGIN CATCH
            -- Erro na database individual nao impede as restantes
            PRINT 'Erro ao processar database [' + @dbname + ']: ' + ERROR_MESSAGE();
        END CATCH

        FETCH NEXT FROM db_cursor INTO @dbname;
    END

    CLOSE db_cursor;
    DEALLOCATE db_cursor;

    SELECT TOP 100
        database_name,
        schema_name,
        table_name,
        stats_name,
        stats_type,
        last_updated,
        days_since_update,
        hours_since_update,
        FORMAT(table_rows, 'N0') as table_rows,
        FORMAT(modifications, 'N0') as modifications,
        modification_percent,
        urgency_level,
        priority,
        priority_score,
        update_script
    FROM #OutdatedStats
    ORDER BY priority ASC, priority_score DESC, modification_percent DESC;

    DROP TABLE #OutdatedStats;
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
    """
    
    DATABASE_IO_STATS = """
    -- Estatísticas de I/O por Database
    -- Identifica databases read-heavy ou write-heavy para otimização
    SELECT 
        DB_NAME(database_id) AS database_name,
        database_id,
        SUM(num_of_reads) AS total_reads,
        SUM(num_of_writes) AS total_writes,
        SUM(num_of_reads + num_of_writes) AS total_io,
        CASE 
            WHEN SUM(num_of_reads + num_of_writes) > 0 
            THEN CAST(SUM(num_of_reads) * 100.0 / SUM(num_of_reads + num_of_writes) AS DECIMAL(5,2))
            ELSE 0 
        END AS reads_percent,
        CASE 
            WHEN SUM(num_of_reads + num_of_writes) > 0 
            THEN CAST(SUM(num_of_writes) * 100.0 / SUM(num_of_reads + num_of_writes) AS DECIMAL(5,2))
            ELSE 0 
        END AS writes_percent,
        SUM(io_stall_read_ms) AS total_read_stall_ms,
        SUM(io_stall_write_ms) AS total_write_stall_ms,
        SUM(io_stall_read_ms + io_stall_write_ms) AS total_stall_ms,
        CASE 
            WHEN SUM(num_of_reads) > 0 
            THEN CAST(SUM(io_stall_read_ms) * 1.0 / SUM(num_of_reads) AS DECIMAL(10,2))
            ELSE 0 
        END AS avg_read_latency_ms,
        CASE 
            WHEN SUM(num_of_writes) > 0 
            THEN CAST(SUM(io_stall_write_ms) * 1.0 / SUM(num_of_writes) AS DECIMAL(10,2))
            ELSE 0 
        END AS avg_write_latency_ms,
        CASE 
            WHEN SUM(num_of_reads) * 100.0 / NULLIF(SUM(num_of_reads + num_of_writes), 0) > 70 THEN 'READ-HEAVY'
            WHEN SUM(num_of_writes) * 100.0 / NULLIF(SUM(num_of_reads + num_of_writes), 0) > 70 THEN 'WRITE-HEAVY'
            ELSE 'BALANCED'
        END AS io_profile
    FROM sys.dm_io_virtual_file_stats(NULL, NULL) WITH(NOLOCK)
    WHERE database_id > 4  -- Excluir system databases
    GROUP BY database_id
    HAVING SUM(num_of_reads + num_of_writes) > 0
    ORDER BY total_io DESC
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
        ELSE CAST((AvailableSpaceMB / AvgMonthlyGrowthMB) AS BIGINT)
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
        ELSE CAST((AvailableSpaceMB / AvgMonthlyGrowthMB) AS BIGINT)
    END ASC,
    DatabaseName
"""

    BACKUP_HISTORY_ANALYSIS = """
-- Query ENHANCED para análise de backups (v1.4.8.3)
-- Detecta databases sem backup e considera Always On AG
-- NOVO: Detecta quando backup LOG não rodou porque havia FULL/DIFF em execução
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
        -- NOVO: Verificar se havia FULL/DIFF rodando quando LOG deveria rodar
        -- Busca FULL/DIFF que estava em execução no período desde o último LOG
        (SELECT TOP 1 
            CASE 
                WHEN bs.type = 'D' THEN 'FULL'
                WHEN bs.type = 'I' THEN 'DIFF'
                ELSE NULL
            END
         FROM msdb.dbo.backupset bs
         CROSS APPLY (
             SELECT TOP 1 bs2.backup_finish_date AS last_log_finish
             FROM msdb.dbo.backupset bs2
             WHERE bs2.database_name = d.name
             AND bs2.type = 'L'
             ORDER BY bs2.backup_finish_date DESC
         ) last_log
         WHERE bs.database_name = d.name
         AND bs.type IN ('D', 'I')
         -- FULL/DIFF que estava rodando quando LOG deveria ter rodado
         -- (começou antes ou durante o período esperado do LOG e terminou depois)
         AND bs.backup_start_date <= DATEADD(HOUR, 2, last_log.last_log_finish)
         AND bs.backup_finish_date >= last_log.last_log_finish
         ORDER BY bs.backup_start_date DESC) AS BlockingBackupType,
        -- NOVO: Horário de início do FULL/DIFF que pode ter bloqueado o LOG
        (SELECT TOP 1 bs.backup_start_date
         FROM msdb.dbo.backupset bs
         CROSS APPLY (
             SELECT TOP 1 bs2.backup_finish_date AS last_log_finish
             FROM msdb.dbo.backupset bs2
             WHERE bs2.database_name = d.name
             AND bs2.type = 'L'
             ORDER BY bs2.backup_finish_date DESC
         ) last_log
         WHERE bs.database_name = d.name
         AND bs.type IN ('D', 'I')
         AND bs.backup_start_date <= DATEADD(HOUR, 2, last_log.last_log_finish)
         AND bs.backup_finish_date >= last_log.last_log_finish
         ORDER BY bs.backup_start_date DESC) AS BlockingBackupStart,
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
    -- NOVO: Informações sobre bloqueio de LOG
    BlockingBackupType, BlockingBackupStart,
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
    -- NOVO: Motivo do LOG não ter rodado (se aplicável)
    CASE
        WHEN RecoveryModel <> 'SIMPLE' 
         AND LastLogBackup IS NOT NULL
         AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 2 
         AND BlockingBackupType IS NOT NULL 
         AND BlockingBackupStart IS NOT NULL
         -- Verificar se o FULL/DIFF estava rodando quando o LOG deveria ter rodado
         AND BlockingBackupStart <= DATEADD(HOUR, 2, LastLogBackup)
         AND EXISTS (
             SELECT 1 FROM msdb.dbo.backupset bs 
             WHERE bs.database_name = DatabaseName
             AND bs.type IN ('D', 'I')
             AND bs.backup_start_date = BlockingBackupStart
             AND bs.backup_finish_date >= LastLogBackup
         )
        THEN 'LOG_BLOCKED_BY_' + BlockingBackupType
        WHEN RecoveryModel <> 'SIMPLE' 
         AND LastLogBackup IS NOT NULL
         AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 2 
         AND BlockingBackupType IS NOT NULL
        THEN 'LOG_POSSIBLY_BLOCKED_BY_' + BlockingBackupType
        ELSE NULL
    END AS LogBackupIssue,
    -- Classificação de risco (ajustada para considerar bloqueio)
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
        -- LOG backup bloqueado por FULL/DIFF (reduzir severidade)
        WHEN RecoveryModel <> 'SIMPLE' 
         AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 6 
         AND BlockingBackupType IS NOT NULL 
         AND BlockingBackupStart <= DATEADD(HOUR, -DATEDIFF(HOUR, LastLogBackup, GETDATE()), GETDATE())
        THEN 'MEDIUM'  -- Reduzido de HIGH para MEDIUM se foi bloqueado
        -- LOG backup muito antigo (>6 horas) sem bloqueio
        WHEN RecoveryModel <> 'SIMPLE' AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 6 THEN 'HIGH'
        -- LOG backup antigo (>2 horas) sem bloqueio
        WHEN RecoveryModel <> 'SIMPLE' AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 2 THEN 'MEDIUM'
        ELSE 'OK'
    END AS RiskLevel,
    -- Status Always On
    CASE
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 1 THEN 'AG_PRIMARY'
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 0 THEN 'AG_SECONDARY'
        ELSE 'STANDALONE'
    END AS AlwaysOnStatus,
    -- Recomendação (ajustada para considerar bloqueio de LOG)
    CASE
        WHEN IsAlwaysOnAG = 1 AND IsPrimaryReplica = 0
            THEN 'Réplica secundária - backup gerenciado pela primária'
        WHEN LastFullBackup IS NULL
            THEN 'URGENTE: Configurar backup FULL imediatamente'
        WHEN DATEDIFF(DAY, LastFullBackup, GETDATE()) > 7
            THEN 'URGENTE: Executar backup FULL (>7 dias sem backup)'
        -- NOVO: Recomendação específica para LOG bloqueado
        -- FIND-20260612-103 (Wave W+1): LogBackupIssue e' alias deste MESMO SELECT
        -- (Msg 207 — query nunca compilava). Predicados da primeira WHEN do CASE
        -- LogBackupIssue inlined abaixo — manter sincronizado com esse CASE acima.
        WHEN RecoveryModel <> 'SIMPLE'
         AND LastLogBackup IS NOT NULL
         AND DATEDIFF(HOUR, LastLogBackup, GETDATE()) > 2
         AND BlockingBackupType IS NOT NULL
         AND BlockingBackupStart IS NOT NULL
         AND BlockingBackupStart <= DATEADD(HOUR, 2, LastLogBackup)
         AND EXISTS (
             SELECT 1 FROM msdb.dbo.backupset bs
             WHERE bs.database_name = DatabaseName
             AND bs.type IN ('D', 'I')
             AND bs.backup_start_date = BlockingBackupStart
             AND bs.backup_finish_date >= LastLogBackup
         )
        THEN 'Backup LOG não rodou porque havia backup ' + BlockingBackupType + ' em execução. Considere ajustar horários dos backups para evitar conflitos.'
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

    # ============================================================================
    # BACKUP GAPS ANALYSIS (v1.5.0)
    # ============================================================================
    
    BACKUP_FULL_GAPS_ANALYSIS = """
-- Análise de gaps em backup FULL (últimas 24 horas)
DECLARE @DaysToAnalyze INT = 1;

WITH FullBackupsWithGaps AS (
    SELECT
        bs.database_name,
        bs.backup_finish_date AS BackupTime,
        LEAD(bs.backup_finish_date) OVER (
            PARTITION BY bs.database_name 
            ORDER BY bs.backup_finish_date
        ) AS NextBackupTime,
        DATEDIFF(DAY, 
            bs.backup_finish_date, 
            LEAD(bs.backup_finish_date) OVER (
                PARTITION BY bs.database_name 
                ORDER BY bs.backup_finish_date
            )
        ) AS GapDays
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    WHERE bs.type = 'D'
    AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
),
SignificantFullGaps AS (
    SELECT 
        database_name,
        BackupTime,
        NextBackupTime,
        GapDays
    FROM FullBackupsWithGaps
    WHERE GapDays > 7
    OR NextBackupTime IS NULL
)
SELECT
    database_name AS DatabaseName,
    BackupTime AS LastFullBackup,
    NextBackupTime AS NextFullBackup,
    ISNULL(GapDays, DATEDIFF(DAY, BackupTime, GETDATE())) AS GapDays,
    CASE
        WHEN NextBackupTime IS NULL AND DATEDIFF(DAY, BackupTime, GETDATE()) > 7
            THEN 'CRITICO - Sem FULL backup ha ' + CAST(DATEDIFF(DAY, BackupTime, GETDATE()) AS VARCHAR) + ' dias'
        WHEN NextBackupTime IS NULL
            THEN 'OK - Ultimo FULL recente'
        WHEN GapDays > 30
            THEN 'CRITICO - Gap de ' + CAST(GapDays AS VARCHAR) + ' dias'
        WHEN GapDays > 14
            THEN 'ALTO - Gap de ' + CAST(GapDays AS VARCHAR) + ' dias'
        WHEN GapDays > 7
            THEN 'MEDIO - Gap de ' + CAST(GapDays AS VARCHAR) + ' dias'
        ELSE 'OK'
    END AS Status,
    CASE
        WHEN NextBackupTime IS NULL AND DATEDIFF(DAY, BackupTime, GETDATE()) > 7 THEN 'CRITICAL'
        WHEN GapDays > 30 THEN 'CRITICAL'
        WHEN GapDays > 14 THEN 'HIGH'
        WHEN GapDays > 7 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS Severity
FROM SignificantFullGaps
ORDER BY GapDays DESC
"""

    BACKUP_DIFF_GAPS_ANALYSIS = """
-- Análise de gaps em backup DIFF (últimas 24 horas)
DECLARE @DaysToAnalyze INT = 1;

WITH DiffBackupsWithGaps AS (
    SELECT
        bs.database_name,
        bs.backup_finish_date AS BackupTime,
        LEAD(bs.backup_finish_date) OVER (
            PARTITION BY bs.database_name 
            ORDER BY bs.backup_finish_date
        ) AS NextBackupTime,
        DATEDIFF(DAY, 
            bs.backup_finish_date, 
            LEAD(bs.backup_finish_date) OVER (
                PARTITION BY bs.database_name 
                ORDER BY bs.backup_finish_date
            )
        ) AS GapDays
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    WHERE bs.type = 'I'
    AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
),
SignificantDiffGaps AS (
    SELECT 
        database_name,
        BackupTime,
        NextBackupTime,
        GapDays
    FROM DiffBackupsWithGaps
    WHERE GapDays > 2
    OR NextBackupTime IS NULL
)
SELECT
    database_name AS DatabaseName,
    BackupTime AS LastDiffBackup,
    NextBackupTime AS NextDiffBackup,
    ISNULL(GapDays, DATEDIFF(DAY, BackupTime, GETDATE())) AS GapDays,
    CASE
        WHEN NextBackupTime IS NULL AND DATEDIFF(DAY, BackupTime, GETDATE()) > 7
            THEN 'ALTO - Sem DIFF backup ha ' + CAST(DATEDIFF(DAY, BackupTime, GETDATE()) AS VARCHAR) + ' dias'
        WHEN NextBackupTime IS NULL
            THEN 'OK - Ultimo DIFF recente'
        WHEN GapDays > 7
            THEN 'ALTO - Gap de ' + CAST(GapDays AS VARCHAR) + ' dias'
        WHEN GapDays > 3
            THEN 'MEDIO - Gap de ' + CAST(GapDays AS VARCHAR) + ' dias'
        ELSE 'BAIXO'
    END AS Status,
    CASE
        WHEN GapDays > 7 THEN 'HIGH'
        WHEN GapDays > 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS Severity
FROM SignificantDiffGaps
ORDER BY GapDays DESC
"""

    BACKUP_LOG_GAPS_ANALYSIS = """
SET NOCOUNT ON;
-- Análise de gaps em backup LOG com detecção de bloqueio (últimas 24 horas)
-- OTIMIZADO v3.0: Removido EXISTS subquery pesado + limitado resultado
-- NOTA: Valor 1 dia hardcoded (DECLARE removido para compatibilidade com pyodbc)

WITH DatabasesWithLogBackup AS (
    SELECT
        d.name AS database_name,
        d.recovery_model_desc
    FROM sys.databases d WITH(NOLOCK)
    WHERE d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
    AND d.state = 0
),
LogBackupsWithGaps AS (
    SELECT
        bs.database_name,
        bs.backup_finish_date AS LogBackupTime,
        LEAD(bs.backup_finish_date) OVER (
            PARTITION BY bs.database_name
            ORDER BY bs.backup_finish_date
        ) AS NextLogBackupTime,
        DATEDIFF(HOUR,
            bs.backup_finish_date,
            LEAD(bs.backup_finish_date) OVER (
                PARTITION BY bs.database_name
                ORDER BY bs.backup_finish_date
            )
        ) AS GapHours
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    INNER JOIN DatabasesWithLogBackup dwl ON bs.database_name = dwl.database_name
    WHERE bs.type = 'L'
    AND bs.backup_finish_date >= DATEADD(DAY, -1, GETDATE())
),
-- Wave I (2026-05-19): DBs FULL/BULK_LOGGED sem NENHUM LOG na janela de analise.
-- Bug original: o INNER JOIN entre backupset e DatabasesWithLogBackup acima exclui
-- silenciosamente DBs sem registo L na janela de 1 dia. CTE emite row sintetica
-- com GapHours calculado contra o ULTIMO L historico (LEFT JOIN sem window filter)
-- para que SignificantLogGaps abaixo as inclua via UNION ALL.
MissingLogChainDatabases AS (
    SELECT
        dwl.database_name,
        NULL AS LogBackupTime,
        NULL AS NextLogBackupTime,
        ISNULL(
            DATEDIFF(HOUR,
                (SELECT MAX(bs2.backup_finish_date)
                 FROM msdb.dbo.backupset bs2 WITH(NOLOCK)
                 WHERE bs2.database_name = dwl.database_name
                   AND bs2.type = 'L'),
                GETDATE()
            ),
            99999  -- nunca teve L backup — RPO ilimitado
        ) AS GapHours
    FROM DatabasesWithLogBackup dwl
    WHERE NOT EXISTS (
        SELECT 1
        FROM msdb.dbo.backupset bs WITH(NOLOCK)
        WHERE bs.database_name = dwl.database_name
          AND bs.type = 'L'
          AND bs.backup_finish_date >= DATEADD(DAY, -1, GETDATE())
    )
),
-- Pré-calcular todos os FULL/DIFF backups do período para evitar subqueries repetidas
FullDiffBackups AS (
    SELECT
        bs.database_name,
        bs.type,
        bs.backup_start_date,
        bs.backup_finish_date,
        DATEDIFF(MINUTE, bs.backup_start_date, bs.backup_finish_date) AS duration_minutes,
        CASE bs.type WHEN 'D' THEN 'FULL' WHEN 'I' THEN 'DIFF' END AS backup_type_name
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    WHERE bs.type IN ('D', 'I')
    AND bs.backup_finish_date >= DATEADD(DAY, -1, GETDATE())
),
SignificantLogGaps AS (
    SELECT
        lg.database_name,
        lg.LogBackupTime,
        lg.NextLogBackupTime,
        lg.GapHours,
        ISNULL(lg.NextLogBackupTime, GETDATE()) AS GapEndTime
    FROM LogBackupsWithGaps lg
    WHERE lg.GapHours > 2
    OR lg.NextLogBackupTime IS NULL
    UNION ALL
    -- Wave I (2026-05-19): DBs sem nenhum L na janela (chain quebrada / nunca existiu)
    SELECT
        ml.database_name,
        ml.LogBackupTime,
        ml.NextLogBackupTime,
        ml.GapHours,
        GETDATE() AS GapEndTime
    FROM MissingLogChainDatabases ml
),
-- CTE que calcula o blocking backup UMA ÚNICA VEZ por gap (antes eram 15+ subqueries)
GapsWithBlockingInfo AS (
    SELECT
        sg.database_name,
        sg.LogBackupTime,
        sg.NextLogBackupTime,
        sg.GapHours,
        sg.GapEndTime,
        fb.backup_type_name AS BlockingBackupType,
        fb.backup_start_date AS BlockingBackupStart,
        fb.backup_finish_date AS BlockingBackupFinish,
        fb.duration_minutes AS BlockingBackupDuration,
        ROW_NUMBER() OVER (
            PARTITION BY sg.database_name, sg.LogBackupTime
            ORDER BY fb.backup_start_date ASC
        ) AS rn
    FROM SignificantLogGaps sg
    LEFT JOIN FullDiffBackups fb
        ON fb.database_name = sg.database_name
        AND fb.backup_start_date > sg.LogBackupTime
        AND fb.backup_start_date < sg.GapEndTime
        AND fb.backup_finish_date > sg.LogBackupTime
),
-- Filtrar apenas o primeiro blocking backup por gap
FinalGaps AS (
    SELECT
        database_name,
        LogBackupTime,
        NextLogBackupTime,
        GapHours,
        GapEndTime,
        BlockingBackupType,
        BlockingBackupStart,
        BlockingBackupFinish,
        BlockingBackupDuration,
        ISNULL(GapHours, DATEDIFF(HOUR, LogBackupTime, GETDATE())) AS EffectiveGapHours
    FROM GapsWithBlockingInfo
    WHERE rn = 1 OR BlockingBackupType IS NULL
)
SELECT TOP 200
    fg.database_name AS DatabaseName,
    fg.LogBackupTime AS LastLogBackup,
    fg.NextLogBackupTime AS NextLogBackup,
    fg.EffectiveGapHours AS GapHours,
    fg.LogBackupTime AS GapStartTime,
    fg.GapEndTime AS GapEndTime,
    fg.BlockingBackupType,
    fg.BlockingBackupStart,
    fg.BlockingBackupFinish,
    fg.BlockingBackupDuration,
    -- Status simplificado usando dados pré-calculados
    CASE
        WHEN fg.NextLogBackupTime IS NULL AND fg.BlockingBackupType IS NOT NULL
            THEN 'GAP ATUAL entre ' +
                 CONVERT(VARCHAR, fg.LogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.LogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.LogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' e ' + CONVERT(VARCHAR, GETDATE(), 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, GETDATE()) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, GETDATE()) AS VARCHAR), 2) + 'min' +
                 ' - Bloqueado por ' + fg.BlockingBackupType +
                 ' (' + CAST(fg.BlockingBackupDuration AS VARCHAR) + ' min)'
        WHEN fg.NextLogBackupTime IS NULL AND fg.EffectiveGapHours > 6
            THEN 'CRITICO - Gap atual de ' + CAST(fg.EffectiveGapHours AS VARCHAR) +
                 'h entre ' + CONVERT(VARCHAR, fg.LogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.LogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.LogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' e ' + CONVERT(VARCHAR, GETDATE(), 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, GETDATE()) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, GETDATE()) AS VARCHAR), 2) + 'min' +
                 ' sem justificativa'
        WHEN fg.NextLogBackupTime IS NULL
            THEN 'OK - Ultimo LOG recente'
        WHEN fg.BlockingBackupType IS NOT NULL
            THEN 'Gap justificado entre ' +
                 CONVERT(VARCHAR, fg.LogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.LogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.LogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' e ' + CONVERT(VARCHAR, fg.NextLogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.NextLogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.NextLogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' - ' + fg.BlockingBackupType + ' rodando (' + CAST(fg.BlockingBackupDuration AS VARCHAR) + ' min)'
        WHEN fg.GapHours > 12
            THEN 'CRITICO - Gap de ' + CAST(fg.GapHours AS VARCHAR) + 'h entre ' +
                 CONVERT(VARCHAR, fg.LogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.LogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.LogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' e ' + CONVERT(VARCHAR, fg.NextLogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.NextLogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.NextLogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' sem justificativa'
        WHEN fg.GapHours > 6
            THEN 'ALTO - Gap de ' + CAST(fg.GapHours AS VARCHAR) + 'h entre ' +
                 CONVERT(VARCHAR, fg.LogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.LogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.LogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' e ' + CONVERT(VARCHAR, fg.NextLogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.NextLogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.NextLogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' sem justificativa'
        ELSE 'MEDIO - Monitorar entre ' +
                 CONVERT(VARCHAR, fg.LogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.LogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.LogBackupTime) AS VARCHAR), 2) + 'min' +
                 ' e ' + CONVERT(VARCHAR, fg.NextLogBackupTime, 103) + ' ' +
                 RIGHT('0' + CAST(DATEPART(HOUR, fg.NextLogBackupTime) AS VARCHAR), 2) + 'h' +
                 RIGHT('0' + CAST(DATEPART(MINUTE, fg.NextLogBackupTime) AS VARCHAR), 2) + 'min'
    END AS Status,
    -- Severity simplificada usando dados pré-calculados
    -- FIND-20260612-102: usar EffectiveGapHours (GapHours raw e' NULL para o gap
    -- ABERTO ultimo-backup->agora; com raw, gaps abertos caiam sempre em 'LOW')
    CASE
        WHEN fg.NextLogBackupTime IS NULL AND fg.BlockingBackupType IS NULL AND fg.EffectiveGapHours > 6 THEN 'CRITICAL'
        WHEN fg.BlockingBackupType IS NOT NULL THEN 'INFO'
        WHEN fg.EffectiveGapHours > 12 THEN 'CRITICAL'
        WHEN fg.EffectiveGapHours > 6 THEN 'HIGH'
        WHEN fg.EffectiveGapHours > 2 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS Severity
FROM FinalGaps fg
-- FIND-20260612-102: ORDER BY referenciava fg.LastLogBackupTime (coluna inexistente
-- na CTE FinalGaps — o nome real e' LogBackupTime; LastLogBackup e' so' alias de
-- output). Msg 207 em TODAS as execucoes desde d1e645e (2026-04-21); o frontend
-- mascarava o 500 como "Nenhum gap significativo" (verde falso).
ORDER BY
    fg.LogBackupTime DESC,
    fg.EffectiveGapHours DESC
"""

    BACKUP_GAPS_SUMMARY = """
SET NOCOUNT ON;
-- Resumo consolidado de gaps por database (últimas 24 horas)
DECLARE @DaysToAnalyze INT = 1;

WITH AllGaps AS (
    SELECT 
        bs.database_name,
        'FULL' AS BackupType,
        DATEDIFF(DAY, MAX(bs.backup_finish_date), GETDATE()) AS DaysSinceLastBackup,
        COUNT(*) AS BackupCount
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    WHERE bs.type = 'D'
    AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
    GROUP BY bs.database_name
    UNION ALL
    SELECT 
        bs.database_name,
        'DIFF' AS BackupType,
        DATEDIFF(DAY, MAX(bs.backup_finish_date), GETDATE()) AS DaysSinceLastBackup,
        COUNT(*) AS BackupCount
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    WHERE bs.type = 'I'
    AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
    GROUP BY bs.database_name
    UNION ALL
    SELECT 
        bs.database_name,
        'LOG' AS BackupType,
        DATEDIFF(HOUR, MAX(bs.backup_finish_date), GETDATE()) AS DaysSinceLastBackup,
        COUNT(*) AS BackupCount
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    INNER JOIN sys.databases d ON bs.database_name = d.name
    WHERE bs.type = 'L'
    AND d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
    AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
    GROUP BY bs.database_name
)
SELECT
    d.name AS DatabaseName,
    d.recovery_model_desc AS RecoveryModel,
    ISNULL((SELECT TOP 1 DaysSinceLastBackup FROM AllGaps WHERE database_name = d.name AND BackupType = 'FULL'), 999) AS DaysSinceFull,
    ISNULL((SELECT TOP 1 BackupCount FROM AllGaps WHERE database_name = d.name AND BackupType = 'FULL'), 0) AS FullCount,
    ISNULL((SELECT TOP 1 DaysSinceLastBackup FROM AllGaps WHERE database_name = d.name AND BackupType = 'DIFF'), 999) AS DaysSinceDiff,
    ISNULL((SELECT TOP 1 BackupCount FROM AllGaps WHERE database_name = d.name AND BackupType = 'DIFF'), 0) AS DiffCount,
    CASE 
        WHEN d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
        THEN ISNULL((SELECT TOP 1 DaysSinceLastBackup FROM AllGaps WHERE database_name = d.name AND BackupType = 'LOG'), 999)
        ELSE NULL
    END AS HoursSinceLog,
    CASE 
        WHEN d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
        THEN ISNULL((SELECT TOP 1 BackupCount FROM AllGaps WHERE database_name = d.name AND BackupType = 'LOG'), 0)
        ELSE NULL
    END AS LogCount,
    CASE
        WHEN NOT EXISTS (SELECT 1 FROM AllGaps WHERE database_name = d.name AND BackupType = 'FULL')
            THEN 'CRITICO - SEM BACKUP FULL'
        WHEN (SELECT TOP 1 DaysSinceLastBackup FROM AllGaps WHERE database_name = d.name AND BackupType = 'FULL') > 7
            THEN 'CRITICO - FULL > 7 dias'
        WHEN d.recovery_model_desc IN ('FULL', 'BULK_LOGGED') 
         AND NOT EXISTS (SELECT 1 FROM AllGaps WHERE database_name = d.name AND BackupType = 'LOG')
            THEN 'CRITICO - SEM BACKUP LOG'
        WHEN d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
         AND (SELECT TOP 1 DaysSinceLastBackup FROM AllGaps WHERE database_name = d.name AND BackupType = 'LOG') > 6
            THEN 'ALTO - LOG > 6 horas'
        WHEN (SELECT TOP 1 DaysSinceLastBackup FROM AllGaps WHERE database_name = d.name AND BackupType = 'FULL') > 3
            THEN 'MEDIO - FULL > 3 dias'
        ELSE 'OK'
    END AS OverallStatus
FROM sys.databases d WITH(NOLOCK)
WHERE d.state = 0
ORDER BY OverallStatus DESC, DaysSinceFull DESC
"""

    CPU_WAIT_STATS = """
    -- Wait Stats relacionados a CPU e paralelismo
    SELECT 
        wait_type AS WaitType,
        wait_time_ms / 1000.0 AS WaitTimeSec,
        waiting_tasks_count AS WaitCount,
        signal_wait_time_ms / 1000.0 AS SignalWaitTimeSec,
        100.0 * wait_time_ms / SUM(wait_time_ms) OVER() AS Percentage
    FROM sys.dm_os_wait_stats WITH(NOLOCK)
    WHERE wait_type IN (
        'CXPACKET',           -- Paralelismo
        'CXCONSUMER',          -- Paralelismo (SQL 2016+)
        'SOS_SCHEDULER_YIELD', -- CPU pressure
        'THREADPOOL',          -- Thread starvation
        'RESOURCE_SEMAPHORE',  -- Memory grants
        'RESOURCE_SEMAPHORE_QUERY_COMPILE' -- Compilação
    )
    AND wait_time_ms > 0
    ORDER BY wait_time_ms DESC
    """
    
    CPU_ACTIVE_QUERIES = """
    -- Queries ativas consumindo mais CPU
    SELECT TOP 10
        r.session_id,
        s.login_name,
        s.host_name,
        s.program_name,
        DB_NAME(r.database_id) AS database_name,
        r.cpu_time / 1000.0 AS cpu_time_sec,
        r.total_elapsed_time / 1000.0 AS elapsed_time_sec,
        r.logical_reads,
        r.reads,
        r.writes,
        r.wait_type,
        r.wait_time / 1000.0 AS wait_time_sec,
        SUBSTRING(
            ISNULL(st.text, ''),
            (r.statement_start_offset/2)+1,
            (CASE WHEN r.statement_end_offset = -1 
             THEN LEN(CONVERT(nvarchar(max), ISNULL(st.text, ''))) * 2 
             ELSE r.statement_end_offset 
             END - r.statement_start_offset)/2
        ) AS sql_text
    FROM sys.dm_exec_requests r WITH(NOLOCK)
    INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON r.session_id = s.session_id
    OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st
    WHERE r.session_id > 50
    AND r.status = 'running'
    AND r.cpu_time > 0
    ORDER BY r.cpu_time DESC
    """
    
    CPU_COMPILATIONS = """
    -- Estatísticas de compilação/recompilação (consomem CPU)
    SELECT 
        cntr_value AS Compilations,
        cntr_value / 60.0 AS CompilationsPerMinute
    FROM sys.dm_os_performance_counters WITH(NOLOCK)
    WHERE counter_name = 'SQL Compilations/sec'
    AND instance_name = ''
    """
    
    MEMORY_BUFFER_POOL_BY_DB = """
    -- Buffer Pool breakdown por database
    SELECT 
        DB_NAME(database_id) AS database_name,
        COUNT(*) * 8 / 1024.0 AS buffer_pool_mb,
        COUNT(*) * 8 / 1024.0 / 1024.0 AS buffer_pool_gb,
        100.0 * COUNT(*) * 8 / 1024.0 / 
            (SELECT SUM(CAST(cntr_value AS BIGINT)) / 1024.0 
             FROM sys.dm_os_performance_counters WITH(NOLOCK)
             WHERE counter_name = 'Total Server Memory (KB)') AS percentage
    FROM sys.dm_os_buffer_descriptors WITH(NOLOCK)
    WHERE database_id > 4  -- Excluir system databases
    GROUP BY database_id
    HAVING COUNT(*) * 8 / 1024.0 > 10  -- Apenas databases com mais de 10MB
    ORDER BY buffer_pool_mb DESC
    """
    
    MEMORY_PAGE_LIFE_EXPECTANCY = """
    -- Page Life Expectancy (PLE) - indicador crítico de memória
    SELECT 
        cntr_value AS PageLifeExpectancy,
        CASE 
            WHEN cntr_value < 300 THEN 'CRITICAL'
            WHEN cntr_value < 600 THEN 'WARNING'
            ELSE 'HEALTHY'
        END AS Status
    FROM sys.dm_os_performance_counters WITH(NOLOCK)
    WHERE counter_name = 'Page life expectancy'
    AND instance_name = ''
    """
    
    MEMORY_GRANTS = """
    -- Memory Grants (pendentes e concedidos)
    SELECT 
        COUNT(*) AS TotalGrants,
        SUM(CASE WHEN grant_time IS NULL THEN 1 ELSE 0 END) AS PendingGrants,
        SUM(CASE WHEN grant_time IS NOT NULL THEN 1 ELSE 0 END) AS GrantedGrants,
        SUM(requested_memory_kb) / 1024.0 AS TotalRequestedMB,
        SUM(granted_memory_kb) / 1024.0 AS TotalGrantedMB,
        MAX(requested_memory_kb) / 1024.0 AS MaxRequestedMB,
        MAX(granted_memory_kb) / 1024.0 AS MaxGrantedMB
    FROM sys.dm_exec_query_memory_grants WITH(NOLOCK)
    """
    
    MEMORY_PLAN_CACHE = """
    -- Tamanho do Plan Cache
    SELECT 
        COUNT(*) AS PlanCount,
        SUM(CAST(size_in_bytes AS BIGINT)) / 1024.0 / 1024.0 AS PlanCacheSizeMB,
        SUM(CASE WHEN usecounts = 1 THEN CAST(size_in_bytes AS BIGINT) ELSE 0 END) / 1024.0 / 1024.0 AS SingleUsePlansMB,
        SUM(CASE WHEN usecounts > 1 THEN CAST(size_in_bytes AS BIGINT) ELSE 0 END) / 1024.0 / 1024.0 AS MultiUsePlansMB,
        100.0 * SUM(CASE WHEN usecounts = 1 THEN CAST(size_in_bytes AS BIGINT) ELSE 0 END) / NULLIF(SUM(CAST(size_in_bytes AS BIGINT)), 0) AS SingleUsePercentage
    FROM sys.dm_exec_cached_plans WITH(NOLOCK)
    """
    
    BACKUP_GAPS_STATISTICS = """
SET NOCOUNT ON;
-- Estatísticas consolidadas de gaps em backup LOG (últimas 24 horas)
-- Retorna estatísticas agregadas e lista de gaps com justificativa
DECLARE @DaysToAnalyze INT = 1;

WITH DatabasesWithLogBackup AS (
    SELECT 
        d.name AS database_name,
        d.recovery_model_desc
    FROM sys.databases d WITH(NOLOCK)
    WHERE d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
    AND d.state = 0
),
LogBackupsWithGaps AS (
    SELECT
        bs.database_name,
        bs.backup_finish_date AS LogBackupTime,
        LEAD(bs.backup_finish_date) OVER (
            PARTITION BY bs.database_name 
            ORDER BY bs.backup_finish_date
        ) AS NextLogBackupTime,
        DATEDIFF(HOUR, 
            bs.backup_finish_date, 
            LEAD(bs.backup_finish_date) OVER (
                PARTITION BY bs.database_name 
                ORDER BY bs.backup_finish_date
            )
        ) AS GapHours
    FROM msdb.dbo.backupset bs WITH(NOLOCK)
    INNER JOIN DatabasesWithLogBackup dwl ON bs.database_name = dwl.database_name
    WHERE bs.type = 'L'
    AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
),
-- Wave I (2026-05-19): mesma logica do site #1 (BACKUP_LOG_GAPS_ANALYSIS L2186)
-- DBs FULL/BULK_LOGGED sem NENHUM L na janela @DaysToAnalyze.
MissingLogChainDatabases AS (
    SELECT
        dwl.database_name,
        NULL AS LogBackupTime,
        NULL AS NextLogBackupTime,
        ISNULL(
            DATEDIFF(HOUR,
                (SELECT MAX(bs2.backup_finish_date)
                 FROM msdb.dbo.backupset bs2 WITH(NOLOCK)
                 WHERE bs2.database_name = dwl.database_name
                   AND bs2.type = 'L'),
                GETDATE()
            ),
            99999
        ) AS GapHours
    FROM DatabasesWithLogBackup dwl
    WHERE NOT EXISTS (
        SELECT 1
        FROM msdb.dbo.backupset bs WITH(NOLOCK)
        WHERE bs.database_name = dwl.database_name
          AND bs.type = 'L'
          AND bs.backup_finish_date >= DATEADD(DAY, -@DaysToAnalyze, GETDATE())
    )
),
SignificantLogGaps AS (
    SELECT
        database_name,
        LogBackupTime,
        NextLogBackupTime,
        GapHours
    FROM LogBackupsWithGaps
    WHERE GapHours > 2
    OR NextLogBackupTime IS NULL
    -- Incluir gaps menores se houver FULL/DIFF bloqueando
    OR EXISTS (
        SELECT 1
        FROM msdb.dbo.backupset bs WITH(NOLOCK)
        WHERE bs.database_name = LogBackupsWithGaps.database_name
        AND bs.type IN ('D', 'I')
        AND bs.backup_start_date > LogBackupsWithGaps.LogBackupTime
        AND bs.backup_start_date < ISNULL(LogBackupsWithGaps.NextLogBackupTime, GETDATE())
        AND bs.backup_finish_date > LogBackupsWithGaps.LogBackupTime
        AND (bs.backup_finish_date < ISNULL(LogBackupsWithGaps.NextLogBackupTime, GETDATE()) OR LogBackupsWithGaps.NextLogBackupTime IS NULL)
    )
    UNION ALL
    -- Wave I: DBs sem nenhum L na janela
    SELECT
        ml.database_name,
        ml.LogBackupTime,
        ml.NextLogBackupTime,
        ml.GapHours
    FROM MissingLogChainDatabases ml
),
GapsWithJustification AS (
    SELECT
        sg.database_name AS DatabaseName,
        ISNULL(sg.GapHours, DATEDIFF(HOUR, sg.LogBackupTime, GETDATE())) AS GapHours,
               CASE
                   WHEN (SELECT TOP 1 bs.type FROM msdb.dbo.backupset bs WITH(NOLOCK) 
                         WHERE bs.database_name = sg.database_name 
                         AND bs.type IN ('D', 'I') 
                         AND bs.backup_start_date > sg.LogBackupTime
                         AND bs.backup_start_date < ISNULL(sg.NextLogBackupTime, GETDATE()) 
                         AND bs.backup_finish_date > sg.LogBackupTime
                         AND (bs.backup_finish_date < ISNULL(sg.NextLogBackupTime, GETDATE()) OR sg.NextLogBackupTime IS NULL)
                         ORDER BY bs.backup_start_date ASC) IS NOT NULL 
                   THEN 1
                   ELSE 0
               END AS IsJustified,
               (SELECT TOP 1 
                   CASE bs.type 
                       WHEN 'D' THEN 'FULL'
                       WHEN 'I' THEN 'DIFF'
                   END
                FROM msdb.dbo.backupset bs WITH(NOLOCK)
                WHERE bs.database_name = sg.database_name
                AND bs.type IN ('D', 'I')
                AND bs.backup_start_date > sg.LogBackupTime
                AND bs.backup_start_date < ISNULL(sg.NextLogBackupTime, GETDATE())
                AND bs.backup_finish_date > sg.LogBackupTime
                AND (bs.backup_finish_date < ISNULL(sg.NextLogBackupTime, GETDATE()) OR sg.NextLogBackupTime IS NULL)
                ORDER BY bs.backup_start_date ASC) AS BlockingBackupType,
        sg.LogBackupTime AS GapStartTime,
        ISNULL(sg.NextLogBackupTime, GETDATE()) AS GapEndTime
    FROM SignificantLogGaps sg
),
GapStatistics AS (
    SELECT
        COUNT(DISTINCT DatabaseName) AS TotalDatabases,
        COUNT(*) AS TotalGaps,
        SUM(IsJustified) AS JustifiedGaps,
        COUNT(*) - SUM(IsJustified) AS UnjustifiedGaps,
        CASE
            WHEN COUNT(*) > 0
            THEN CAST((SUM(IsJustified) * 100.0 / COUNT(*)) AS DECIMAL(5,2))
            ELSE 0
        END AS PercentJustified,
        CASE
            WHEN COUNT(*) > 0 
            THEN CAST(AVG(CAST(GapHours AS FLOAT)) AS DECIMAL(10,2))
            ELSE 0
        END AS AvgGapHours,
        MAX(GapHours) AS MaxGapHours
    FROM GapsWithJustification
)
SELECT
    s.TotalDatabases AS TotalDatabasesMonitoradas,
    s.TotalGaps AS TotalGapsDetectados,
    s.JustifiedGaps AS GapsJustificados,
    s.UnjustifiedGaps AS GapsSEMJustificativa,
    s.PercentJustified AS PercentGapsJustificados,
    s.AvgGapHours AS GapMedioGlobalHoras,
    s.MaxGapHours AS MaiorGapGlobalHoras,
    -- Lista de gaps detalhados
    (SELECT 
        DatabaseName,
        GapHours,
        IsJustified,
        BlockingBackupType,
        GapStartTime,
        GapEndTime
     FROM GapsWithJustification
     ORDER BY GapHours DESC
     FOR JSON PATH
    ) AS GapsDetalhados
FROM GapStatistics s
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

    # ============================================================
    # DIAGNOSTICO DE I/O DE DISCO
    # ============================================================

    DISK_IO_DIAGNOSTICS = """
SET NOCOUNT ON;
-- Diagnostico de I/O por arquivo de banco de dados
-- Mostra latencia, IOPS e throughput por arquivo (MDF, LDF, NDF)
SELECT TOP 50
    DB_NAME(vfs.database_id) AS [Database],
    mf.name AS [FileName],
    mf.type_desc AS [FileType],
    CASE mf.type_desc
        WHEN 'ROWS' THEN 'Dados (MDF/NDF)'
        WHEN 'LOG' THEN 'Log (LDF)'
        ELSE mf.type_desc
    END AS [FileTypeDesc],
    CAST(mf.physical_name AS NVARCHAR(260)) AS [PhysicalPath],
    -- Tamanho do arquivo
    CAST(mf.size * 8.0 / 1024 AS DECIMAL(12,1)) AS [FileSizeMB],
    -- Latencia de leitura (ms por operacao)
    CASE WHEN vfs.num_of_reads > 0
        THEN CAST(vfs.io_stall_read_ms * 1.0 / vfs.num_of_reads AS DECIMAL(12,1))
        ELSE 0
    END AS [ReadLatencyMs],
    -- Latencia de escrita (ms por operacao)
    CASE WHEN vfs.num_of_writes > 0
        THEN CAST(vfs.io_stall_write_ms * 1.0 / vfs.num_of_writes AS DECIMAL(12,1))
        ELSE 0
    END AS [WriteLatencyMs],
    -- IOPS
    vfs.num_of_reads AS [TotalReads],
    vfs.num_of_writes AS [TotalWrites],
    -- Throughput
    CAST(vfs.num_of_bytes_read / 1048576.0 AS DECIMAL(12,1)) AS [ReadMB],
    CAST(vfs.num_of_bytes_written / 1048576.0 AS DECIMAL(12,1)) AS [WriteMB],
    -- Stall total
    vfs.io_stall_read_ms AS [TotalReadStallMs],
    vfs.io_stall_write_ms AS [TotalWriteStallMs],
    -- Extensao do arquivo
    UPPER(RIGHT(mf.physical_name, CHARINDEX('.', REVERSE(mf.physical_name)) - 1)) AS [FileExtension],
    -- Severidade
    CASE
        WHEN (CASE WHEN vfs.num_of_reads > 0 THEN vfs.io_stall_read_ms * 1.0 / vfs.num_of_reads ELSE 0 END) >= 50
          OR (CASE WHEN vfs.num_of_writes > 0 THEN vfs.io_stall_write_ms * 1.0 / vfs.num_of_writes ELSE 0 END) >= 50
        THEN 'CRITICAL'
        WHEN (CASE WHEN vfs.num_of_reads > 0 THEN vfs.io_stall_read_ms * 1.0 / vfs.num_of_reads ELSE 0 END) >= 20
          OR (CASE WHEN vfs.num_of_writes > 0 THEN vfs.io_stall_write_ms * 1.0 / vfs.num_of_writes ELSE 0 END) >= 20
        THEN 'WARNING'
        ELSE 'OK'
    END AS [Severity]
FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs
INNER JOIN sys.master_files mf WITH(NOLOCK)
    ON vfs.database_id = mf.database_id AND vfs.file_id = mf.file_id
WHERE vfs.num_of_reads + vfs.num_of_writes > 0
ORDER BY
    CASE
        WHEN (CASE WHEN vfs.num_of_reads > 0 THEN vfs.io_stall_read_ms * 1.0 / vfs.num_of_reads ELSE 0 END) >= 50
          OR (CASE WHEN vfs.num_of_writes > 0 THEN vfs.io_stall_write_ms * 1.0 / vfs.num_of_writes ELSE 0 END) >= 50
        THEN 1
        WHEN (CASE WHEN vfs.num_of_reads > 0 THEN vfs.io_stall_read_ms * 1.0 / vfs.num_of_reads ELSE 0 END) >= 20
          OR (CASE WHEN vfs.num_of_writes > 0 THEN vfs.io_stall_write_ms * 1.0 / vfs.num_of_writes ELSE 0 END) >= 20
        THEN 2
        ELSE 3
    END,
    (vfs.io_stall_read_ms + vfs.io_stall_write_ms) DESC
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


# =============================================================================
# QUERIES PARA ESPACO NAO ALOCADO (DISK UNALLOCATED)
# =============================================================================

class DiskUnallocatedQueries:
    """
    Queries para consulta de espaco nao alocado em discos fisicos.
    Os dados sao coletados via WMI/PowerShell e armazenados no banco central.
    """

    # Resumo de espaco nao alocado por servidor (query direta sem view)
    UNALLOCATED_SUMMARY = """
    WITH LatestPerDisk AS (
        SELECT Instance, Disk_Number, MAX(Collection_Time) AS Max_Collection
        FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
        GROUP BY Instance, Disk_Number
    )
    SELECT
        u.Instance AS Servidor,
        CASE
            WHEN u.Instance LIKE '%PRD%' OR u.Instance LIKE '%PROD%' THEN 'PRD'
            WHEN u.Instance LIKE '%QLT%' THEN 'QLT'
            WHEN u.Instance LIKE '%QA%' OR u.Instance LIKE '%HML%' THEN 'QA'
            WHEN u.Instance LIKE '%TST%' OR u.Instance LIKE '%DEV%' THEN 'TST'
            ELSE 'Outros'
        END AS Ambiente,
        COUNT(DISTINCT u.Disk_Number) AS Qtd_Discos,
        SUM(u.Disk_Size_GB) AS Total_Discos_GB,
        SUM(u.Allocated_GB) AS Total_Alocado_GB,
        SUM(u.Unallocated_GB) AS Total_Nao_Alocado_GB,
        CAST(SUM(u.Unallocated_GB) * 100.0 / NULLIF(SUM(u.Disk_Size_GB), 0) AS DECIMAL(5,2)) AS Percent_Nao_Alocado,
        SUM(CASE WHEN u.Can_Expand = 1 THEN 1 ELSE 0 END) AS Discos_Expandiveis,
        MAX(u.Collection_Time) AS Ultima_Coleta
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
    INNER JOIN LatestPerDisk lpd
        ON u.Instance = lpd.Instance
        AND u.Disk_Number = lpd.Disk_Number
        AND u.Collection_Time = lpd.Max_Collection
    GROUP BY u.Instance
    ORDER BY SUM(u.Unallocated_GB) DESC
    """

    # Detalhes de um servidor especifico (busca ultimo registro por disco)
    SERVER_UNALLOCATED_DETAIL = """
    WITH LatestPerDisk AS (
        SELECT Instance, Disk_Number, MAX(Collection_Time) AS Max_Collection
        FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
        WHERE Instance = ?
        GROUP BY Instance, Disk_Number
    )
    SELECT
        u.Instance AS Servidor,
        u.Disk_Number AS Disco,
        NULL AS Modelo,
        NULL AS Tipo_Midia,
        NULL AS Barramento,
        NULL AS Saude,
        u.Disk_Size_GB AS Tamanho_GB,
        u.Allocated_GB AS Alocado_GB,
        u.Unallocated_GB AS Nao_Alocado_GB,
        u.Percent_Unallocated AS Percent_Livre,
        u.Can_Expand AS Pode_Expandir,
        u.Adjacent_Drive AS Drive_Adjacente,
        u.Collection_Time AS Coleta
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
    INNER JOIN LatestPerDisk lpd
        ON u.Instance = lpd.Instance
        AND u.Disk_Number = lpd.Disk_Number
        AND u.Collection_Time = lpd.Max_Collection
    ORDER BY u.Disk_Number
    """

    # Particoes de um servidor
    # FIND-20260612-103 (Wave W+1): a versao anterior tinha subquery auto-referente
    # (Instance = Instance da MESMA tabela interior -> sempre true) que usava o
    # MAX(Collection_Time) GLOBAL — servidores com coleccao mais antiga que o maximo
    # global devolviam 0 particoes silenciosamente. Alem disso o collector V1
    # (collect_disk_unallocated.py) insere row-a-row com GETDATE() por statement,
    # logo Collection_Time difere por ms dentro da mesma coleccao — equality estrita
    # devolveria apenas 1 row. Fix: janela 10min ancorada no MAX per-instance +
    # ROW_NUMBER dedupe por (Disk, Partition).
    SERVER_PARTITIONS = """
    WITH LatestRows AS (
        SELECT
            p.Instance, p.Disk_Number, p.Partition_Number, p.Drive_Letter,
            p.Volume_Label, p.Partition_Size_GB, p.File_System, p.Is_Boot,
            p.Partition_Type, p.Collection_Time,
            ROW_NUMBER() OVER (
                PARTITION BY p.Disk_Number, p.Partition_Number
                ORDER BY p.Collection_Time DESC
            ) AS rn
        FROM dbo.KPI_OS_DISK_PARTITION_STG p WITH (NOLOCK)
        WHERE p.Instance = ?
          AND p.Collection_Time >= DATEADD(MINUTE, -10, (
              SELECT MAX(p2.Collection_Time)
              FROM dbo.KPI_OS_DISK_PARTITION_STG p2 WITH (NOLOCK)
              WHERE p2.Instance = p.Instance
          ))
    )
    SELECT
        Instance AS Servidor,
        Disk_Number AS Disco,
        Partition_Number AS Particao,
        Drive_Letter AS Drive,
        Volume_Label AS Label,
        Partition_Size_GB AS Tamanho_GB,
        File_System AS FileSystem,
        Is_Boot AS Boot,
        Partition_Type AS Tipo,
        Collection_Time AS Coleta
    FROM LatestRows
    WHERE rn = 1
    ORDER BY Disk_Number, Partition_Number
    """

    # Oportunidades de expansao (query direta sem view)
    EXPANSION_OPPORTUNITIES = """
    WITH LatestCollection AS (
        SELECT Instance, Disk_Number, MAX(Collection_Time) AS Max_Collection
        FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
        GROUP BY Instance, Disk_Number
    )
    SELECT
        u.Instance AS Servidor,
        CASE
            WHEN u.Instance LIKE '%PRD%' OR u.Instance LIKE '%PROD%' THEN 'PRD'
            WHEN u.Instance LIKE '%QLT%' THEN 'QLT'
            WHEN u.Instance LIKE '%QA%' OR u.Instance LIKE '%HML%' THEN 'QA'
            WHEN u.Instance LIKE '%TST%' OR u.Instance LIKE '%DEV%' THEN 'TST'
            ELSE 'Outros'
        END AS Ambiente,
        u.Disk_Number AS Disco,
        NULL AS Modelo_Disco,
        NULL AS Tipo_Midia,
        u.Disk_Size_GB AS Tamanho_Disco_GB,
        u.Unallocated_GB AS Nao_Alocado_GB,
        u.Percent_Unallocated AS Percent_Nao_Alocado,
        u.Adjacent_Drive AS Drive_Adjacente,
        u.Can_Expand AS Pode_Expandir,
        CASE
            WHEN u.Unallocated_GB >= 100 THEN 'Alta'
            WHEN u.Unallocated_GB >= 50 THEN 'Media'
            WHEN u.Unallocated_GB >= 10 THEN 'Baixa'
            ELSE 'Minima'
        END AS Prioridade_Expansao,
        u.Collection_Time AS Ultima_Coleta
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
    INNER JOIN LatestCollection lc
        ON u.Instance = lc.Instance
        AND u.Disk_Number = lc.Disk_Number
        AND u.Collection_Time = lc.Max_Collection
    WHERE u.Can_Expand = 1
      AND u.Unallocated_GB >= ?  -- Minimo de GB para considerar
    ORDER BY
        CASE
            WHEN u.Unallocated_GB >= 100 THEN 1
            WHEN u.Unallocated_GB >= 50 THEN 2
            WHEN u.Unallocated_GB >= 10 THEN 3
            ELSE 4
        END,
        u.Unallocated_GB DESC
    """

    # Historico de espaco nao alocado (para tendencia)
    UNALLOCATED_HISTORY = """
    SELECT
        Instance AS Servidor,
        Disk_Number AS Disco,
        Disk_Size_GB AS Tamanho_GB,
        Allocated_GB AS Alocado_GB,
        Unallocated_GB AS Nao_Alocado_GB,
        Percent_Unallocated AS Percent_Livre,
        Collect_Date AS Data,
        Collect_TS AS Timestamp
    FROM dbo.KPI_OS_DISK_UNALLOCATED_HIST
    WHERE Instance = ?
      AND Collect_Date >= DATEADD(DAY, -?, GETDATE())  -- Ultimos N dias
    ORDER BY Collect_Date DESC
    """

    # Estatisticas globais (query direta sem view)
    GLOBAL_STATS = """
    WITH LatestPerDisk AS (
        SELECT Instance, Disk_Number, MAX(Collection_Time) AS Max_Collection
        FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
        GROUP BY Instance, Disk_Number
    )
    SELECT
        COUNT(DISTINCT u.Instance) AS Total_Servidores,
        COUNT(*) AS Total_Discos,
        CAST(SUM(u.Disk_Size_GB) AS DECIMAL(18,2)) AS Total_Capacidade_GB,
        CAST(SUM(u.Unallocated_GB) AS DECIMAL(18,2)) AS Total_Nao_Alocado_GB,
        CAST(SUM(u.Unallocated_GB) * 100.0 / NULLIF(SUM(u.Disk_Size_GB), 0) AS DECIMAL(5,2)) AS Percent_Nao_Alocado_Global,
        SUM(CASE WHEN u.Can_Expand = 1 THEN 1 ELSE 0 END) AS Total_Discos_Expandiveis,
        MAX(u.Collection_Time) AS Ultima_Coleta
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
    INNER JOIN LatestPerDisk lpd
        ON u.Instance = lpd.Instance
        AND u.Disk_Number = lpd.Disk_Number
        AND u.Collection_Time = lpd.Max_Collection
    """

    # Estatisticas por ambiente (query direta sem view)
    STATS_BY_ENVIRONMENT = """
    WITH LatestPerDisk AS (
        SELECT Instance, Disk_Number, MAX(Collection_Time) AS Max_Collection
        FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
        GROUP BY Instance, Disk_Number
    ),
    ServerData AS (
        SELECT
            u.Instance,
            CASE
                WHEN u.Instance LIKE '%PRD%' OR u.Instance LIKE '%PROD%' THEN 'PRD'
                WHEN u.Instance LIKE '%QLT%' THEN 'QLT'
                WHEN u.Instance LIKE '%QA%' OR u.Instance LIKE '%HML%' THEN 'QA'
                WHEN u.Instance LIKE '%TST%' OR u.Instance LIKE '%DEV%' THEN 'TST'
                ELSE 'Outros'
            END AS Ambiente,
            u.Disk_Size_GB,
            u.Unallocated_GB,
            u.Can_Expand
        FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
        INNER JOIN LatestPerDisk lpd
            ON u.Instance = lpd.Instance
            AND u.Disk_Number = lpd.Disk_Number
            AND u.Collection_Time = lpd.Max_Collection
    )
    SELECT
        Ambiente,
        COUNT(DISTINCT Instance) AS Servidores,
        COUNT(*) AS Discos,
        CAST(SUM(Disk_Size_GB) AS DECIMAL(18,2)) AS Capacidade_GB,
        CAST(SUM(Unallocated_GB) AS DECIMAL(18,2)) AS Nao_Alocado_GB,
        CAST(SUM(Unallocated_GB) * 100.0 / NULLIF(SUM(Disk_Size_GB), 0) AS DECIMAL(5,2)) AS Percent_Livre,
        SUM(CASE WHEN Can_Expand = 1 THEN 1 ELSE 0 END) AS Expandiveis
    FROM ServerData
    GROUP BY Ambiente
    ORDER BY
        CASE Ambiente
            WHEN 'PRD' THEN 1
            WHEN 'QLT' THEN 2
            WHEN 'QA' THEN 3
            WHEN 'TST' THEN 4
            ELSE 5
        END
    """

    # Inserir dados de disco fisico
    INSERT_PHYSICAL_DISK = """
    INSERT INTO dbo.KPI_OS_DISK_PHYSICAL_STG
        (Instance, Disk_Number, Disk_Model, Disk_Size_GB, Partition_Style,
         Is_System_Disk, Is_Boot_Disk, Health_Status, Operational_Status,
         Bus_Type, Media_Type, Collection_Method)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # Inserir dados de particao
    INSERT_PARTITION = """
    INSERT INTO dbo.KPI_OS_DISK_PARTITION_STG
        (Instance, Disk_Number, Partition_Number, Drive_Letter, Volume_Label,
         Partition_Size_GB, File_System, Is_Active, Is_Boot, Partition_Type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # Inserir dados de espaco nao alocado
    INSERT_UNALLOCATED = """
    INSERT INTO dbo.KPI_OS_DISK_UNALLOCATED_STG
        (Instance, Disk_Number, Disk_Size_GB, Allocated_GB, Unallocated_GB,
         Percent_Unallocated, Can_Expand, Adjacent_Drive)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """