/* ============================================================================
   Atribuicao de query a aplicacao - SQL do plano PLANO_ATRIBUICAO_APP_2026-09-24.md
   Revisto por sql-deep-reviewer (2026-09-24). T-SQL 2014+ (sem STRING_AGG/STRING_SPLIT).

   IDENTIDADE: sql_monitoring (login SQL). NUNCA a conta AD. NUNCA via docs/context/sql/_run.py
   (liga so' a Intelligence e recusa WAITFOR/DECLARE/EXEC - correcto, nao relaxar).
   ONDE: SSMS ligado a instancia monitorizada, base master; ou sampler Python via execute_on_server (pool).
   PERMISSOES: VIEW SERVER STATE (+ VIEW ANY DATABASE em Q3; VIEW DATABASE STATE por base para o estado do QS).
   IMPACTO: so' leitura de DMVs, excepto Q4 (SO' QLT) que cria ~2000 planos ad hoc de proposito.
   ROLLBACK: n/a (Q1-Q3, L1b, TOP_SLOW, L2c); Q4 = eviction natural (sql_monitoring nao pode FREEPROCCACHE).
   RESULTADOS de Q1/Q2 tem logins e hosts: ficam no scratchpad, nunca no repo.
   ============================================================================ */


/* ---------------------------------------------------------------------------
   Q1 - AMOSTRA (modo B recomendado: correr este SELECT a cada 10 s durante 60 min
        a partir do cliente, gravar CSV incremental; agregar em Python com a
        mesma logica da "Q1 - AGREGACAO"). ~5-20 ms, sem locks.
   --------------------------------------------------------------------------- */
SELECT SYSDATETIME() AS sample_at,
       s.session_id, s.login_time, s.login_name, s.host_name, s.program_name,
       s.cpu_time AS cpu_ms, s.reads, s.writes,
       CASE WHEN r.session_id IS NULL THEN 0 ELSE 1 END AS req_active
FROM sys.dm_exec_sessions s WITH (NOLOCK)
LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK) ON r.session_id = s.session_id
WHERE s.is_user_process = 1
  AND s.session_id <> @@SPID;


/* ---------------------------------------------------------------------------
   Q1 - MODO A (SSMS, so' se o owner preferir). Sessao presa 60 min em WAITFOR:
   aparece como pedido longo no LIVE e no PROCESSES_STG do V1; se a VPN cair
   perde-se tudo (incidente 21/09). INSERT so' em #temp.
   --------------------------------------------------------------------------- */
SET NOCOUNT ON; SET LOCK_TIMEOUT 2000;
IF OBJECT_ID('tempdb..#amostra') IS NOT NULL DROP TABLE #amostra;
CREATE TABLE #amostra (sample_at datetime2(0), session_id int, login_time datetime,
    login_name nvarchar(128), host_name nvarchar(128), program_name nvarchar(128),
    cpu_ms bigint, reads bigint, writes bigint, req_active bit);
DECLARE @until datetime2(0) = DATEADD(MINUTE, 60, SYSDATETIME());
WHILE SYSDATETIME() < @until
BEGIN
    INSERT #amostra
    SELECT SYSDATETIME(), s.session_id, s.login_time, s.login_name, s.host_name, s.program_name,
           s.cpu_time, s.reads, s.writes, CASE WHEN r.session_id IS NULL THEN 0 ELSE 1 END
    FROM sys.dm_exec_sessions s WITH (NOLOCK)
    LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK) ON r.session_id = s.session_id
    WHERE s.is_user_process = 1 AND s.session_id <> @@SPID;
    WAITFOR DELAY '00:00:10';
END


/* ---------------------------------------------------------------------------
   Q1 - AGREGACAO (sobre #amostra; em modo B a mesma logica em pandas).
   Metrica: delta de dm_exec_sessions.cpu_time por (session_id, login_time) com LAG.
   Vies declarado: sessoes < 10 s sem pooling contam 0 (gate conservador).
   Gate: pct_cpu de 'generic' >= 60 -> L1 completo com guia; < 30 -> L1 so' agregacao.
   --------------------------------------------------------------------------- */
;WITH d AS (
    SELECT session_id, login_time, login_name, host_name, program_name, cpu_ms,
           cpu_ms - LAG(cpu_ms) OVER (PARTITION BY session_id, login_time ORDER BY sample_at) AS delta_raw
    FROM #amostra
), c AS (
    SELECT *,
           CASE WHEN delta_raw IS NULL THEN 0 WHEN delta_raw < 0 THEN cpu_ms ELSE delta_raw END AS delta_ms,
           CASE
             WHEN program_name IS NULL OR LTRIM(RTRIM(program_name)) = '' THEN 'unknown'
             WHEN program_name LIKE 'SQLAgent - %' THEN 'agent'
             WHEN program_name COLLATE Latin1_General_CI_AI LIKE '%SqlClient Data Provider%'
               OR program_name COLLATE Latin1_General_CI_AI LIKE 'Microsoft JDBC Driver%'
               OR program_name COLLATE Latin1_General_CI_AI LIKE 'Microsoft SQL Server JDBC Driver%'
               OR program_name COLLATE Latin1_General_CI_AI LIKE 'ODBC Driver % for SQL Server'
               OR program_name COLLATE Latin1_General_CI_AI LIKE 'Microsoft SQL Server Management Studio%'
               OR program_name COLLATE Latin1_General_CI_AI LIKE 'Microsoft% Windows% Operating System'
               OR program_name COLLATE Latin1_General_CI_AI LIKE '%.exe'
               OR program_name COLLATE Latin1_General_CI_AI IN ('python','pyodbc','sqlcmd','osql','Microsoft SQL Server',
                                                                'OLEDB','Ole DB','DatabaseMail','Report Server')
             THEN 'generic'
             ELSE 'named'
           END AS classe
    FROM d
)
SELECT classe,
       SUM(delta_ms) AS cpu_ms,
       CAST(100.0 * SUM(delta_ms) / NULLIF(SUM(SUM(delta_ms)) OVER (), 0) AS decimal(5,1)) AS pct_cpu,
       COUNT(DISTINCT CAST(session_id AS varchar(10)) + '|' + CONVERT(varchar(23), login_time, 121)) AS sessoes,
       COUNT(DISTINCT program_name) AS programas
FROM c
GROUP BY classe
ORDER BY cpu_ms DESC;


/* ---------------------------------------------------------------------------
   Q2 - CARDINALIDADE login x programa x host (sobre os samples de Q1, nao foto).
   --------------------------------------------------------------------------- */
SELECT login_name, COUNT(DISTINCT program_name) AS programas, COUNT(DISTINCT host_name) AS hosts,
       MAX(program_name) AS exemplo_programa
FROM #amostra
GROUP BY login_name
ORDER BY programas DESC, login_name;
-- Fallback sem samples: trocar #amostra por sys.dm_exec_sessions WHERE is_user_process = 1.


/* ---------------------------------------------------------------------------
   Q3 - QUERY STORE por instancia (sobrevive a 2014: is_query_store_on nao existe
        antes de 2016 e rebenta o batch inteiro mesmo dentro de IF nao executado).
   --------------------------------------------------------------------------- */
SET NOCOUNT ON;
DECLARE @major int = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)), 4) AS int);
SELECT @@SERVERNAME AS instancia, @major AS major, SERVERPROPERTY('ProductVersion') AS versao;
IF @major < 13
    SELECT 'n/a (< 2016): Query Store inexistente' AS resumo;
ELSE
BEGIN
    EXEC sp_executesql N'
      SELECT COUNT(*) AS bases_online,
             SUM(CASE WHEN is_query_store_on = 1 THEN 1 ELSE 0 END) AS bases_qs_on
      FROM sys.databases WHERE state = 0 AND database_id > 4;';
    DECLARE @db sysname, @sql nvarchar(max);
    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT name FROM sys.databases WHERE state = 0 AND database_id > 4 AND HAS_DBACCESS(name) = 1;
    OPEN cur; FETCH NEXT FROM cur INTO @db;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @sql = N'SELECT ' + QUOTENAME(@db, '''') + N' AS base, actual_state_desc, readonly_reason,
                     current_storage_size_mb, max_storage_size_mb, query_capture_mode_desc
                     FROM ' + QUOTENAME(@db) + N'.sys.database_query_store_options;';
        BEGIN TRY EXEC sp_executesql @sql; END TRY
        BEGIN CATCH SELECT @db AS base, 'erro ' + CAST(ERROR_NUMBER() AS varchar(10)) + ' (sem permissao/AG secundaria?)' AS actual_state_desc; END CATCH
        FETCH NEXT FROM cur INTO @db;
    END
    CLOSE cur; DEALLOCATE cur;
END


/* ---------------------------------------------------------------------------
   Q4 - SINTETICO de poluicao do plan cache. SO' QLT. Base master (sem Query Store).
   IMPACTO: +~2000 planos ad hoc/prepared (~20-40 MB; ~0,4 MB se optimize for ad hoc = 1),
   ficam ate' eviction natural. sql_monitoring NAO pode FREEPROCCACHE. NAO pedir
   FREESYSTEMCACHE('SQL Plans') (tempestade de compilacoes). Aparecem no LIVE > Plan Cache
   da QLT: e' a demo do L1b, nao um defeito. NAO CORRER EM PRD.
   --------------------------------------------------------------------------- */
SET NOCOUNT ON;
SELECT name, value_in_use FROM sys.configurations WHERE name = 'optimize for ad hoc workloads';  -- muda a leitura (stubs)
SELECT 'antes' AS fase, COUNT(*) AS planos_adhoc, SUM(CAST(size_in_bytes AS bigint))/1024 AS kb,
       SUM(CASE WHEN usecounts = 1 THEN 1 ELSE 0 END) AS single_use
FROM sys.dm_exec_cached_plans WITH (NOLOCK) WHERE objtype = 'Adhoc';
SELECT 'antes' AS fase, RTRIM(counter_name) AS contador, cntr_value
FROM sys.dm_os_performance_counters WHERE object_name LIKE '%:SQL Statistics%'
  AND counter_name IN ('SQL Compilations/sec','Batch Requests/sec');   -- cumulativos: interessa o delta

DECLARE @i int = 0, @sql4 nvarchar(400);
-- A: 1000x texto IDENTICO (comentario estatico) -> esperado 1 plano, usecounts 1000, ~1 compilacao
SET @i = 0;
WHILE @i < 1000 BEGIN
    EXEC (N'SELECT TOP (1) name FROM sys.objects /* watcherdb_poc static route=''/checkout'' */');
    SET @i += 1;
END
-- B: 1000x comentario UNICO (traceparent) em batch ad hoc -> esperado ~1000 planos/stubs, ~1000 compilacoes
SET @i = 0;
WHILE @i < 1000 BEGIN
    SET @sql4 = N'SELECT TOP (1) name FROM sys.objects /* watcherdb_poc adhoc traceparent=''00-'
              + REPLACE(CONVERT(char(36), NEWID()), '-', '') + N'-01'' */';
    EXEC (@sql4);
    SET @i += 1;
END
-- C: 1000x comentario UNICO dentro do @stmt de sp_executesql (Prepared) -> tambem ~1000 planos
SET @i = 0;
WHILE @i < 1000 BEGIN
    SET @sql4 = N'SELECT TOP (1) name FROM sys.objects WHERE object_id > @p /* watcherdb_poc prepared traceparent=''00-'
              + REPLACE(CONVERT(char(36), NEWID()), '-', '') + N'-01'' */';
    EXEC sp_executesql @sql4, N'@p int', @p = 0;
    SET @i += 1;
END

SELECT 'depois' AS fase, COUNT(*) AS planos_adhoc, SUM(CAST(size_in_bytes AS bigint))/1024 AS kb,
       SUM(CASE WHEN usecounts = 1 THEN 1 ELSE 0 END) AS single_use
FROM sys.dm_exec_cached_plans WITH (NOLOCK) WHERE objtype = 'Adhoc';
SELECT 'depois' AS fase, RTRIM(counter_name) AS contador, cntr_value
FROM sys.dm_os_performance_counters WHERE object_name LIKE '%:SQL Statistics%'
  AND counter_name IN ('SQL Compilations/sec','Batch Requests/sec');
-- medicao exacta pelo marcador (1 scan do cache com texto: aceitavel em QLT, uma vez)
SELECT CASE WHEN t.text LIKE '%watcherdb_poc static%' THEN 'A_static'
            WHEN t.text LIKE '%watcherdb_poc adhoc%'  THEN 'B_adhoc_unique'
            ELSE 'C_prepared_unique' END AS variante,
       cp.objtype, cp.cacheobjtype, COUNT(*) AS planos, SUM(cp.usecounts) AS usecounts,
       SUM(CAST(cp.size_in_bytes AS bigint))/1024 AS kb
FROM sys.dm_exec_cached_plans cp WITH (NOLOCK)
CROSS APPLY sys.dm_exec_sql_text(cp.plan_handle) t
WHERE t.text LIKE '%watcherdb_poc%'
GROUP BY CASE WHEN t.text LIKE '%watcherdb_poc static%' THEN 'A_static'
              WHEN t.text LIKE '%watcherdb_poc adhoc%'  THEN 'B_adhoc_unique'
              ELSE 'C_prepared_unique' END, cp.objtype, cp.cacheobjtype
ORDER BY variante;
-- Leitura: A = 1 plano/1000 usecounts; B e C = ~1000 planos (ou 1000 'Compiled Plan Stub' com optimize for ad hoc = 1);
-- delta 'SQL Compilations/sec' ~ 2001. Numero para calibrar o alarme L1b.


/* ---------------------------------------------------------------------------
   L1b - SINAL BARATO (cada refresh; delta dos contadores cumulativos em Python).
   Regra: (dCompilations/dBatches) > 0,10 OU adhoc_single_use > 50 % de planos_adhoc
          OU sqlcp_kb a subir -> abrir a drill.
   --------------------------------------------------------------------------- */
SELECT GETDATE() AS sampled_at,
       mc.sqlcp_kb, mc.objcp_kb,
       cp.planos_adhoc, cp.adhoc_single_use, cp.adhoc_single_use_kb,
       pc.compilations_total, pc.recompilations_total, pc.batches_total
FROM (SELECT SUM(CASE WHEN type = 'CACHESTORE_SQLCP' THEN pages_kb ELSE 0 END) AS sqlcp_kb,
             SUM(CASE WHEN type = 'CACHESTORE_OBJCP' THEN pages_kb ELSE 0 END) AS objcp_kb
      FROM sys.dm_os_memory_clerks WITH (NOLOCK) WHERE type IN ('CACHESTORE_SQLCP','CACHESTORE_OBJCP')) mc
CROSS JOIN (SELECT COUNT(*) AS planos_adhoc,
                   SUM(CASE WHEN usecounts = 1 THEN 1 ELSE 0 END) AS adhoc_single_use,
                   SUM(CASE WHEN usecounts = 1 THEN CAST(size_in_bytes AS bigint) ELSE 0 END)/1024 AS adhoc_single_use_kb
            FROM sys.dm_exec_cached_plans WITH (NOLOCK) WHERE objtype = 'Adhoc') cp
CROSS JOIN (SELECT MAX(CASE WHEN counter_name LIKE 'SQL Compilations/sec%'    THEN cntr_value END) AS compilations_total,
                   MAX(CASE WHEN counter_name LIKE 'SQL Re-Compilations/sec%' THEN cntr_value END) AS recompilations_total,
                   MAX(CASE WHEN counter_name LIKE 'Batch Requests/sec%'      THEN cntr_value END) AS batches_total
            FROM sys.dm_os_performance_counters WITH (NOLOCK) WHERE object_name LIKE '%:SQL Statistics%') pc;


/* ---------------------------------------------------------------------------
   L1b - DRILL "variantes por query_hash" (so' ao clique; 1 scan; texto so' nas 20).
   query_hash 0x0 excluido (ganharia sempre); janela creation_time 60 min (0 = cache inteiro).
   Limiares iniciais: 100 info / 1000 warning / 10000 critical com execs_per_variant < 2.
   --------------------------------------------------------------------------- */
SET NOCOUNT ON;
DECLARE @min int = 100, @janela_min int = 60;
;WITH q AS (
    SELECT qs.query_hash, qs.sql_handle, qs.statement_start_offset, qs.statement_end_offset,
           qs.execution_count, qs.total_worker_time, qs.creation_time
    FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
    WHERE qs.query_hash <> 0x0000000000000000
      AND (@janela_min = 0 OR qs.creation_time >= DATEADD(MINUTE, -@janela_min, GETDATE()))
), w AS (
    SELECT q.*,
           DENSE_RANK() OVER (PARTITION BY query_hash ORDER BY sql_handle) AS dr,
           ROW_NUMBER() OVER (PARTITION BY query_hash ORDER BY total_worker_time DESC, sql_handle) AS rn,
           SUM(execution_count)   OVER (PARTITION BY query_hash) AS execs,
           SUM(total_worker_time) OVER (PARTITION BY query_hash) AS cpu_us,
           MIN(creation_time)     OVER (PARTITION BY query_hash) AS first_seen,
           MAX(creation_time)     OVER (PARTITION BY query_hash) AS last_seen
    FROM q
), v AS (
    SELECT w.*, MAX(dr) OVER (PARTITION BY query_hash) AS variants FROM w
), top20 AS (
    SELECT TOP 20 * FROM v WHERE rn = 1 AND variants >= @min ORDER BY variants DESC, cpu_us DESC
)
SELECT t.query_hash, t.variants, t.execs,
       CAST(t.execs AS float) / t.variants AS execs_per_variant,      -- < 2 = nao parametrizado
       t.cpu_us / 1000 AS total_cpu_ms, t.first_seen, t.last_seen,
       NULLIF(DATEDIFF(MINUTE, t.first_seen, t.last_seen), 0) AS span_min,
       DB_NAME(qt.dbid) AS database_name, OBJECT_NAME(qt.objectid, qt.dbid) AS object_name,
       SUBSTRING(qt.text, (t.statement_start_offset/2)+1,
           ((CASE t.statement_end_offset WHEN -1 THEN DATALENGTH(qt.text)
             ELSE t.statement_end_offset END - t.statement_start_offset)/2)+1) AS sample_text
FROM top20 t
CROSS APPLY sys.dm_exec_sql_text(t.sql_handle) qt
ORDER BY t.variants DESC, t.cpu_us DESC;


/* ---------------------------------------------------------------------------
   L1-SQL 1b - TOP_SLOW_QUERIES_DETAILED reescrita (modules/monitoring/queries.py:747-787).
   Semantica mantida: login = sessao com pedido ACTIVO neste plan_handle (mais recente), senao 'N/A'.
   2.a fonte removida: pa.attribute = 'session_id' NAO EXISTE em dm_exec_plan_attributes -> era sempre NULL
   e pagava um scan de cached_plans + plan_attributes por linha.
   Padrao TOP -> APPLY: texto, plano XML e sessao so' nas 20 vencedoras. Colunas antigas mantem nome; novas aditivas.
   --------------------------------------------------------------------------- */
;WITH top20 AS (
    SELECT TOP 20
        qs.sql_handle, qs.plan_handle, qs.statement_start_offset, qs.statement_end_offset,
        qs.execution_count, qs.total_elapsed_time, qs.total_worker_time,
        qs.total_logical_reads, qs.total_physical_reads, qs.creation_time, qs.last_execution_time
    FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
    WHERE qs.total_elapsed_time > 5000000
    ORDER BY qs.total_elapsed_time DESC
)
SELECT
    t.execution_count,
    t.total_elapsed_time / 1000000.0                                AS total_elapsed_seconds,
    t.total_elapsed_time / NULLIF(t.execution_count, 0) / 1000000.0 AS avg_elapsed_seconds,
    t.total_worker_time / 1000000.0                                 AS total_cpu_seconds,
    t.total_worker_time / NULLIF(t.execution_count, 0) / 1000000.0  AS avg_cpu_seconds,
    t.total_logical_reads,
    t.total_logical_reads / NULLIF(t.execution_count, 0)            AS avg_logical_reads,
    t.total_physical_reads,
    t.creation_time,
    t.last_execution_time,
    COALESCE(DB_NAME(st.dbid), DB_NAME(CAST(pa.value AS int)))      AS database_name,   -- F9: dbid NULL em ad hoc
    COALESCE(ses.login_name, 'N/A')                                 AS login_name,
    ses.host_name,
    ses.program_name,
    CASE WHEN ses.session_id IS NULL THEN 'none' ELSE 'active_request' END AS attribution_source,
    OBJECT_NAME(st.objectid, st.dbid)                               AS object_name,     -- proc: atribuicao real e gratis
    SUBSTRING(st.text, (t.statement_start_offset/2)+1,
        (CASE WHEN t.statement_end_offset = -1
              THEN LEN(CONVERT(nvarchar(max), st.text)) * 2
              ELSE t.statement_end_offset END - t.statement_start_offset)/2)  AS statement_text,
    qp.query_plan                                                   AS query_plan
FROM top20 t
CROSS APPLY sys.dm_exec_sql_text(t.sql_handle) st
OUTER APPLY sys.dm_exec_query_plan(t.plan_handle) qp                -- OUTER: plano expulso nao apaga a linha
OUTER APPLY (SELECT TOP 1 value FROM sys.dm_exec_plan_attributes(t.plan_handle) WHERE attribute = 'dbid') pa
OUTER APPLY (
    SELECT TOP 1 s.session_id, s.login_name, s.host_name, s.program_name
    FROM sys.dm_exec_requests r WITH (NOLOCK)
    INNER JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON s.session_id = r.session_id
    WHERE r.plan_handle = t.plan_handle
      AND s.login_name IS NOT NULL
    ORDER BY r.start_time DESC
) ses
ORDER BY t.total_elapsed_time DESC;


/* ---------------------------------------------------------------------------
   L2c (PRO-ONLY, V6) - CPU por rota: TOP 20 hashes x top 5 variantes, 1 scan.
   GROUP BY query_hash sozinho colapsa rotas (mesmo hash de /checkout e /cart = 2 sql_handle).
   Python: parse head/tail por variante -> soma CPU por rota dentro do hash;
   hash_cpu_ms - soma(variantes lidas) = 'outras variantes'. query_hash chega como bytes -> .hex().
   Rotulo: 'x % das linhas, y % do CPU do TOP 20 amostrado'.
   # PRO-ONLY - nao propagar para V3.4 sem decisao DBA Lead
   --------------------------------------------------------------------------- */
SET NOCOUNT ON;
DECLARE @n int = 20, @k int = 5;
;WITH q AS (
    SELECT qs.query_hash, qs.sql_handle, qs.statement_start_offset, qs.statement_end_offset,
           qs.execution_count, qs.total_worker_time, qs.last_execution_time
    FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
    WHERE qs.query_hash <> 0x0000000000000000
), w AS (
    SELECT q.*,
           SUM(total_worker_time) OVER (PARTITION BY query_hash) AS hash_cpu_us,
           SUM(execution_count)   OVER (PARTITION BY query_hash) AS hash_execs,
           COUNT(*)               OVER (PARTITION BY query_hash) AS hash_rows,
           ROW_NUMBER() OVER (PARTITION BY query_hash ORDER BY total_worker_time DESC, sql_handle) AS rn
    FROM q
), w2 AS (
    SELECT w.*, DENSE_RANK() OVER (ORDER BY hash_cpu_us DESC, query_hash) AS hash_rank FROM w
), sel AS (
    SELECT * FROM w2 WHERE hash_rank <= @n AND rn <= @k          -- filtro ANTES do APPLY
)
SELECT v.hash_rank, v.query_hash,
       v.hash_cpu_us / 1000 AS hash_cpu_ms, v.hash_execs, v.hash_rows,
       v.rn AS variant_rank, v.total_worker_time / 1000 AS variant_cpu_ms, v.execution_count AS variant_execs,
       v.last_execution_time,
       DB_NAME(qt.dbid) AS database_name, OBJECT_NAME(qt.objectid, qt.dbid) AS object_name,
       LEFT(qt.text, 600)  AS text_head,     -- EF TagWith (apos o bloco '(@p...)' do sp_executesql)
       RIGHT(qt.text, 600) AS text_tail,     -- sqlcommenter
       SUBSTRING(qt.text, (v.statement_start_offset/2)+1,
           ((CASE v.statement_end_offset WHEN -1 THEN DATALENGTH(qt.text)
             ELSE v.statement_end_offset END - v.statement_start_offset)/2)+1) AS sql_text
FROM sel v
CROSS APPLY sys.dm_exec_sql_text(v.sql_handle) qt
ORDER BY v.hash_rank, v.rn;
