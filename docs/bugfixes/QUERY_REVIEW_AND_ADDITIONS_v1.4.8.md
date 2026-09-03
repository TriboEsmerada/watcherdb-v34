# Revisão de Queries e Adições ao SQL Diag - v1.4.8
**Data:** 2025-11-15
**Componente:** modules/monitoring/queries.py e SQL Diag

## Resumo Executivo

Revisão completa das queries de fragmentação de índices e estatísticas desatualizadas, com análise de 15+ queries fornecidas pelo usuário para potencial inclusão no SQL Diag.

---

## 1. QUERIES ATUAIS - ANÁLISE E MELHORIAS

### 1.1 INDEX_FRAGMENTATION (Linha 215-229)

**Query Atual:**
```sql
SELECT TOP 100
    DB_NAME(ps.database_id) AS DatabaseName,
    OBJECT_NAME(ps.object_id, ps.database_id) AS TableName,
    i.name AS IndexName,
    ps.avg_fragmentation_in_percent AS FragmentationPercent,
    CAST(ps.page_count * 8.0 / 1024 AS DECIMAL(18,2)) AS IndexSizeMB
FROM sys.dm_db_index_physical_stats(NULL, NULL, NULL, NULL, 'LIMITED') ps
INNER JOIN sys.indexes i WITH(NOLOCK) ON ps.object_id = i.object_id AND ps.index_id = i.index_id
WHERE ps.avg_fragmentation_in_percent > 10 AND ps.page_count > 1000
ORDER BY ps.avg_fragmentation_in_percent DESC
```

**Problemas Identificados:**
1. ❌ Não fornece ação recomendada (REBUILD vs REORGANIZE)
2. ❌ Não considera tipo de índice (CLUSTERED vs NONCLUSTERED)
3. ❌ Não filtra índices desabilitados
4. ❌ Não calcula prioridade
5. ⚠️ Usa 'LIMITED' mode (rápido mas menos preciso)

**Query Melhorada Proposta:**
```sql
-- INDEX_FRAGMENTATION - ENHANCED VERSION
WITH IndexFragmentation AS (
    SELECT
        DB_NAME(ips.database_id) as DatabaseName,
        OBJECT_SCHEMA_NAME(ips.object_id, ips.database_id) as SchemaName,
        OBJECT_NAME(ips.object_id, ips.database_id) as TableName,
        i.name as IndexName,
        i.type_desc as IndexType,
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
        -- Prioridade
        CASE
            WHEN ips.avg_fragmentation_in_percent > 50 THEN 1
            WHEN ips.avg_fragmentation_in_percent > 30 THEN 2
            WHEN ips.avg_fragmentation_in_percent > 10 THEN 3
            ELSE 4
        END as Priority,
        -- Script de manutenção
        CASE
            WHEN ips.avg_fragmentation_in_percent > 30 AND ips.page_count > 1000 THEN
                'ALTER INDEX [' + i.name + '] ON [' +
                OBJECT_SCHEMA_NAME(ips.object_id, ips.database_id) + '].[' +
                OBJECT_NAME(ips.object_id, ips.database_id) + '] REBUILD WITH (ONLINE = ON);'
            WHEN ips.avg_fragmentation_in_percent > 10 AND ips.page_count > 1000 THEN
                'ALTER INDEX [' + i.name + '] ON [' +
                OBJECT_SCHEMA_NAME(ips.object_id, ips.database_id) + '].[' +
                OBJECT_NAME(ips.object_id, ips.database_id) + '] REORGANIZE;'
            ELSE NULL
        END as MaintenanceScript
    FROM sys.dm_db_index_physical_stats(NULL, NULL, NULL, NULL, 'LIMITED') ips
    INNER JOIN sys.indexes i WITH(NOLOCK)
        ON ips.object_id = i.object_id AND ips.index_id = i.index_id
    WHERE ips.avg_fragmentation_in_percent > 10
    AND ips.page_count > 100  -- Reduzido de 1000 para capturar mais índices
    AND i.name IS NOT NULL     -- Excluir heaps
    AND i.is_disabled = 0      -- Excluir índices desabilitados
    AND i.is_hypothetical = 0  -- Excluir índices hipotéticos
    AND ips.index_level = 0    -- Apenas leaf level
)
SELECT TOP 100
    DatabaseName,
    SchemaName,
    TableName,
    IndexName,
    IndexType,
    CAST(FragmentationPercent AS DECIMAL(5,2)) as FragmentationPercent,
    page_count as PageCount,
    IndexSizeMB,
    record_count as RecordCount,
    MaintenanceAction,
    Priority,
    MaintenanceScript
FROM IndexFragmentation
ORDER BY Priority ASC, FragmentationPercent DESC
```

**Benefícios:**
- ✅ Fornece script de manutenção pronto para executar
- ✅ Priorização clara (1=Crítico, 2=Alto, 3=Médio, 4=Baixo)
- ✅ Filtra índices desabilitados e hipotéticos
- ✅ Diferencia REBUILD (>30%) de REORGANIZE (10-30%)
- ✅ Reduz threshold de pages para 100 (captura mais casos)

---

### 1.2 INDEX_FRAGMENTATION_DETAILED (Linha 557-605)

**Query Atual:**
Já é mais completa que INDEX_FRAGMENTATION, mas pode ser melhorada.

**Problemas:**
1. ⚠️ Usa 'SAMPLED' mode (mais lento)
2. ❌ Não fornece script de manutenção
3. ❌ Duplica funcionalidade de INDEX_FRAGMENTATION

**Recomendação:**
- **REMOVER** INDEX_FRAGMENTATION simples (linha 215-229)
- **SUBSTITUIR** por versão enhanced acima
- **MANTER** INDEX_FRAGMENTATION_DETAILED como opção para análise aprofundada

---

### 1.3 STATISTICS_OUTDATED (Linha 651-693)

**Query Atual:**
```sql
WITH StatisticsInfo AS (
    SELECT
        OBJECT_SCHEMA_NAME(s.object_id) as schema_name,
        OBJECT_NAME(s.object_id) as table_name,
        s.name as stats_name,
        sp.last_updated,
        sp.rows as table_rows,
        sp.rows_sampled,
        sp.modification_counter,
        CASE
            WHEN sp.rows > 0
            THEN CAST((sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2))
            ELSE 0
        END as modification_percent
    FROM sys.stats s WITH(NOLOCK)
    CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
    WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
    AND sp.rows > 1000
)
SELECT
    schema_name,
    table_name,
    stats_name,
    last_updated,
    table_rows,
    modification_counter,
    modification_percent,
    DATEDIFF(day, last_updated, GETDATE()) as days_since_update,
    CASE
        WHEN DATEDIFF(day, last_updated, GETDATE()) > 7
        AND modification_percent > 20
        THEN 'CRITICAL: UPDATE STATISTICS [' + schema_name + '].[' + table_name + ']'
        WHEN DATEDIFF(day, last_updated, GETDATE()) > 3
        AND modification_percent > 10
        THEN 'HIGH: Consider updating statistics'
        ELSE 'OK'
    END as recommendation
FROM StatisticsInfo
WHERE DATEDIFF(day, last_updated, GETDATE()) > 1
OR modification_percent > 10
ORDER BY modification_percent DESC, days_since_update DESC
```

**Problemas Identificados:**
1. ❌ Recomendação genérica (não fornece script SQL)
2. ❌ Não classifica por tipo de estatística (AUTO vs USER vs INDEX)
3. ❌ Threshold muito alto (sp.rows > 1000) - pode perder tabelas importantes
4. ❌ Não trata valores NULL em sp.last_updated
5. ❌ Não fornece priorização numérica

**Query Melhorada Proposta:**
```sql
-- STATISTICS_OUTDATED - ENHANCED VERSION
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
```

**Benefícios:**
- ✅ Script SQL pronto para executar
- ✅ Priorização por score (considera dias + % modificação + tamanho tabela)
- ✅ Classificação por tipo de estatística
- ✅ Threshold reduzido (100 rows vs 1000)
- ✅ Tratamento de NULL em last_updated
- ✅ Diferencia FULLSCAN vs SAMPLE 25%

---

## 2. NOVAS QUERIES PARA ADICIONAR AO SQL DIAG

Após análise das 15+ queries fornecidas, recomendo adicionar as seguintes:

### 2.1 BACKUP_HISTORY_ANALYSIS ⭐⭐⭐ (ALTA PRIORIDADE)

**Fonte:** Query fornecida pelo usuário
**Justificativa:** Essencial para monitorar backups em ambiente de produção

```python
BACKUP_HISTORY_ANALYSIS = """
-- Análise completa de histórico de backups (últimos 7 dias)
SET NOCOUNT ON;

WITH DatabasesInAG AS (
    -- Identificar databases em Always On
    SELECT DISTINCT
        d.name as database_name,
        COALESCE(ag.name, 'STANDALONE') as ag_name,
        COALESCE(ars.role_desc, 'STANDALONE') as role_desc
    FROM sys.databases d
    LEFT JOIN sys.dm_hadr_database_replica_states drs
        ON d.database_id = drs.database_id
    LEFT JOIN sys.availability_groups ag
        ON drs.group_id = ag.group_id
    LEFT JOIN sys.dm_hadr_availability_replica_states ars
        ON drs.replica_id = ars.replica_id
    WHERE d.database_id > 4
    AND d.state = 0
),
RecentBackups AS (
    SELECT
        database_name,
        MAX(CASE WHEN type = 'D' THEN backup_finish_date END) as last_full,
        MAX(CASE WHEN type = 'I' THEN backup_finish_date END) as last_diff,
        MAX(CASE WHEN type = 'L' THEN backup_finish_date END) as last_log,
        SUM(CASE WHEN type = 'D' AND backup_finish_date >= DATEADD(day, -7, GETDATE())
                THEN 1 ELSE 0 END) as full_count_7d,
        SUM(CASE WHEN type = 'L' AND backup_finish_date >= DATEADD(day, -1, GETDATE())
                THEN 1 ELSE 0 END) as log_count_1d,
        MAX(CASE WHEN type = 'D' THEN backup_size / 1024.0 / 1024.0 / 1024.0 END) as last_full_size_gb
    FROM msdb.dbo.backupset
    WHERE backup_finish_date >= DATEADD(day, -30, GETDATE())
    GROUP BY database_name
)
SELECT
    dag.database_name,
    dag.ag_name,
    dag.role_desc,
    rb.last_full,
    DATEDIFF(hour, rb.last_full, GETDATE()) as hours_since_full,
    rb.last_diff,
    rb.last_log,
    DATEDIFF(minute, rb.last_log, GETDATE()) as minutes_since_log,
    rb.full_count_7d,
    rb.log_count_1d,
    CAST(rb.last_full_size_gb AS DECIMAL(10,2)) as last_full_size_gb,
    -- Compliance baseado em boas práticas
    CASE
        WHEN rb.last_full IS NULL THEN 'CRITICAL: NEVER FULL BACKUP'
        WHEN rb.last_full < DATEADD(day, -7, GETDATE()) THEN 'CRITICAL: FULL BACKUP > 7 DAYS'
        WHEN rb.last_log IS NULL AND dag.role_desc = 'PRIMARY' THEN 'CRITICAL: NEVER LOG BACKUP'
        WHEN rb.last_log < DATEADD(hour, -2, GETDATE()) AND dag.role_desc = 'PRIMARY' THEN 'WARNING: LOG BACKUP > 2 HOURS'
        WHEN rb.full_count_7d < 1 THEN 'WARNING: < 1 FULL BACKUP IN 7 DAYS'
        ELSE 'OK'
    END as backup_compliance,
    -- Solução sugerida
    CASE
        WHEN rb.last_full IS NULL THEN
            'SOLUTION: BACKUP DATABASE [' + dag.database_name + '] TO DISK = ''C:\\Backup\\' + dag.database_name + '_Full.bak'' WITH COMPRESSION;'
        WHEN rb.last_full < DATEADD(day, -7, GETDATE()) THEN
            'SOLUTION: Schedule weekly full backup job via SQL Agent'
        WHEN rb.last_log IS NULL AND dag.role_desc = 'PRIMARY' THEN
            'SOLUTION: BACKUP LOG [' + dag.database_name + '] TO DISK = ''C:\\Backup\\' + dag.database_name + '_Log.trn'' WITH COMPRESSION;'
        WHEN rb.last_log < DATEADD(hour, -2, GETDATE()) AND dag.role_desc = 'PRIMARY' THEN
            'SOLUTION: Schedule log backup job every 15-30 minutes'
        ELSE 'No action needed'
    END as backup_solution,
    -- Prioridade
    CASE
        WHEN rb.last_full IS NULL THEN 1
        WHEN rb.last_full < DATEADD(day, -7, GETDATE()) THEN 1
        WHEN rb.last_log IS NULL AND dag.role_desc = 'PRIMARY' THEN 1
        WHEN rb.last_log < DATEADD(hour, -2, GETDATE()) AND dag.role_desc = 'PRIMARY' THEN 2
        ELSE 3
    END as priority
FROM DatabasesInAG dag
LEFT JOIN RecentBackups rb ON dag.database_name = rb.database_name
ORDER BY priority ASC, dag.ag_name, dag.database_name
"""
```

**Benefícios:**
- ✅ Detecta databases sem backup há muito tempo
- ✅ Considera Always On (não alerta para secundárias)
- ✅ Fornece scripts de solução prontos
- ✅ Priorização clara (1=Crítico, 2=Warning, 3=OK)

---

### 2.2 MISSING_INDEX_ANALYSIS ⭐⭐⭐ (ALTA PRIORIDADE)

**Fonte:** Get-EnhancedMissingIndexAnalysis.sql fornecida
**Justificativa:** Identifica índices ausentes que podem melhorar performance significativamente

```python
MISSING_INDEX_ANALYSIS = """
-- Análise de índices ausentes com maior impacto
SET NOCOUNT ON;

WITH MissingIndexAnalysis AS (
    SELECT
        s.avg_total_user_cost,
        s.avg_user_impact,
        s.user_seeks,
        s.user_scans,
        d.statement as table_name,
        d.equality_columns,
        d.inequality_columns,
        d.included_columns,
        ROUND(s.avg_total_user_cost * s.avg_user_impact * (s.user_seeks + s.user_scans), 0) AS improvement_measure,
        -- CREATE INDEX statement
        'CREATE NONCLUSTERED INDEX [IX_Missing_' +
        CAST(ROW_NUMBER() OVER(ORDER BY s.avg_total_user_cost * s.avg_user_impact * (s.user_seeks + s.user_scans) DESC) AS VARCHAR(3)) +
        '] ON ' + d.statement +
        ' (' + ISNULL(d.equality_columns, '') +
        CASE WHEN d.equality_columns IS NOT NULL AND d.inequality_columns IS NOT NULL THEN ', ' ELSE '' END +
        ISNULL(d.inequality_columns, '') + ')' +
        ISNULL(' INCLUDE (' + d.included_columns + ')', '') +
        ' WITH (FILLFACTOR = 90, PAD_INDEX = ON);' AS create_index_statement,
        -- Classificação de impacto
        CASE
            WHEN s.avg_user_impact > 90 THEN 'CRITICAL'
            WHEN s.avg_user_impact > 70 THEN 'HIGH'
            WHEN s.avg_user_impact > 50 THEN 'MEDIUM'
            ELSE 'LOW'
        END as impact_classification,
        -- Prioridade
        CASE
            WHEN s.avg_user_impact > 85 AND (s.user_seeks + s.user_scans) > 1000 THEN 1
            WHEN s.avg_user_impact > 70 AND (s.user_seeks + s.user_scans) > 500 THEN 2
            WHEN s.avg_user_impact > 50 AND (s.user_seeks + s.user_scans) > 100 THEN 3
            ELSE 4
        END as implementation_priority,
        (s.user_seeks + s.user_scans) as total_usage
    FROM sys.dm_db_missing_index_group_stats s
    INNER JOIN sys.dm_db_missing_index_groups g ON s.group_handle = g.index_group_handle
    INNER JOIN sys.dm_db_missing_index_details d ON g.index_handle = d.index_handle
    WHERE s.avg_user_impact > 50
    AND (s.user_seeks + s.user_scans) > 50
)
SELECT TOP 20
    table_name,
    equality_columns,
    inequality_columns,
    included_columns,
    CAST(avg_user_impact AS DECIMAL(5,2)) as avg_user_impact,
    total_usage,
    improvement_measure,
    impact_classification,
    implementation_priority,
    create_index_statement
FROM MissingIndexAnalysis
ORDER BY implementation_priority ASC, improvement_measure DESC
"""
```

---

### 2.3 QUERY_PERFORMANCE_ANALYSIS ⭐⭐ (MÉDIA PRIORIDADE)

**Fonte:** Get-QueryPerformance.sql fornecida (versão melhorada)
**Justificativa:** Identifica queries lentas que consomem muitos recursos

```python
QUERY_PERFORMANCE_ANALYSIS = """
-- Análise de performance de queries com critérios realísticos
SET NOCOUNT ON;

SELECT TOP 50
    LEFT(st.text, 200) as query_text,
    qs.execution_count,
    qs.total_worker_time/1000 as total_cpu_ms,
    (qs.total_worker_time/qs.execution_count)/1000 as avg_cpu_ms,
    qs.total_logical_reads,
    qs.total_logical_reads/qs.execution_count as avg_logical_reads,
    qs.total_physical_reads,
    qs.total_logical_writes,
    qs.last_execution_time,
    qs.total_elapsed_time/1000 as total_elapsed_ms,
    (qs.total_elapsed_time/qs.execution_count)/1000 as avg_elapsed_ms,
    -- Score de impacto
    CAST((qs.total_worker_time * qs.execution_count) / 1000000.0 AS DECIMAL(15,2)) as impact_score,
    -- Classificação
    CASE
        WHEN (qs.total_worker_time/qs.execution_count)/1000 > 1000 THEN 'SLOW_QUERY'
        WHEN (qs.total_worker_time/qs.execution_count)/1000 > 500 THEN 'MEDIUM_SLOW'
        WHEN (qs.total_worker_time/qs.execution_count)/1000 > 100 THEN 'ATTENTION_NEEDED'
        WHEN qs.total_logical_reads/qs.execution_count > 10000 THEN 'HIGH_IO'
        WHEN qs.execution_count > 1000 AND (qs.total_worker_time/qs.execution_count)/1000 > 50 THEN 'FREQUENT_SLOW'
        ELSE 'NORMAL'
    END as problem_category,
    -- Prioridade
    CASE
        WHEN (qs.total_worker_time/qs.execution_count)/1000 > 1000 THEN 1
        WHEN (qs.total_worker_time/qs.execution_count)/1000 > 500 THEN 2
        WHEN qs.total_logical_reads/qs.execution_count > 10000 THEN 2
        WHEN qs.execution_count > 1000 AND (qs.total_worker_time/qs.execution_count)/1000 > 50 THEN 3
        ELSE 4
    END as priority_level,
    -- Percentual de CPU
    CAST(qs.total_worker_time * 100.0 / (SELECT SUM(total_worker_time) FROM sys.dm_exec_query_stats) AS DECIMAL(5,2)) as cpu_percent
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
WHERE st.text NOT LIKE '%sys.%'
    AND st.text NOT LIKE '%INFORMATION_SCHEMA%'
    AND st.text IS NOT NULL
    AND qs.execution_count >= 5
    AND qs.last_execution_time >= DATEADD(day, -7, GETDATE())
    AND (
        (qs.total_worker_time/qs.execution_count)/1000 > 50
        OR qs.total_logical_reads/qs.execution_count > 1000
        OR qs.total_worker_time/1000 > 5000
    )
ORDER BY priority_level ASC, qs.total_worker_time DESC
"""
```

---

### 2.4 DUPLICATE_INDEXES_ANALYSIS ⭐ (BAIXA PRIORIDADE)

**Fonte:** Get-DuplicateIndexesAnalysis.sql fornecida
**Justificativa:** Identifica índices duplicados que desperdiçam espaço e recursos

```python
DUPLICATE_INDEXES_ANALYSIS = """
-- Análise de índices duplicados
SET NOCOUNT ON;

WITH IndexColumns AS (
    SELECT
        i.object_id,
        i.index_id,
        i.name as index_name,
        i.type_desc,
        STUFF((
            SELECT ', ' + c.name + CASE WHEN ic.is_descending_key = 1 THEN ' DESC' ELSE ' ASC' END
            FROM sys.index_columns ic
            INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE ic.object_id = i.object_id
              AND ic.index_id = i.index_id
              AND ic.is_included_column = 0
            ORDER BY ic.key_ordinal
            FOR XML PATH('')
        ), 1, 2, '') as key_columns,
        STUFF((
            SELECT ', ' + c.name
            FROM sys.index_columns ic
            INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE ic.object_id = i.object_id
              AND ic.index_id = i.index_id
              AND ic.is_included_column = 1
            ORDER BY ic.key_ordinal
            FOR XML PATH('')
        ), 1, 2, '') as included_columns,
        (
            SELECT SUM(ps.used_page_count) * 8.0 / 1024
            FROM sys.dm_db_partition_stats ps
            WHERE ps.object_id = i.object_id AND ps.index_id = i.index_id
        ) as size_mb
    FROM sys.indexes i
    INNER JOIN sys.objects o ON i.object_id = o.object_id
    WHERE o.type = 'U'
      AND i.type_desc IN ('CLUSTERED', 'NONCLUSTERED')
      AND i.is_disabled = 0
)
SELECT TOP 50
    DB_NAME() as database_name,
    OBJECT_SCHEMA_NAME(ic1.object_id) as schema_name,
    OBJECT_NAME(ic1.object_id) as table_name,
    ic1.index_name as index_name_1,
    ic2.index_name as index_name_2,
    ic1.key_columns,
    ISNULL(ic1.included_columns, '') as included_columns_1,
    ISNULL(ic2.included_columns, '') as included_columns_2,
    CAST(ic1.size_mb AS DECIMAL(10,2)) as size_mb_1,
    CAST(ic2.size_mb AS DECIMAL(10,2)) as size_mb_2,
    ic1.type_desc as type_desc_1,
    ic2.type_desc as type_desc_2,
    -- Recomendação
    'DROP INDEX [' + ic2.index_name + '] ON [' +
    OBJECT_SCHEMA_NAME(ic2.object_id) + '].[' + OBJECT_NAME(ic2.object_id) + '];' as drop_script,
    -- Prioridade baseada em tamanho
    CASE
        WHEN ic2.size_mb > 100 THEN 1
        WHEN ic2.size_mb > 10 THEN 2
        ELSE 3
    END as priority
FROM IndexColumns ic1
INNER JOIN IndexColumns ic2 ON ic1.object_id = ic2.object_id
    AND ic1.index_id < ic2.index_id
    AND ic1.key_columns = ic2.key_columns
WHERE ic1.key_columns IS NOT NULL
  AND ic2.key_columns IS NOT NULL
ORDER BY priority ASC, ic2.size_mb DESC
"""
```

---

### 2.5 WAIT_STATISTICS_ANALYSIS ⭐⭐ (MÉDIA PRIORIDADE)

**Fonte:** Get-EnhancedWaitStatistics.sql fornecida
**Justificativa:** Já existe WAIT_STATS em queries.py, mas esta versão é melhorada

```python
# Esta query já existe, mas pode ser melhorada com análise de impacto:

WAIT_STATISTICS_ENHANCED = """
-- Análise aprimorada de wait statistics
SET NOCOUNT ON;

WITH WaitStats AS (
    SELECT
        wait_type,
        waiting_tasks_count,
        wait_time_ms,
        max_wait_time_ms,
        signal_wait_time_ms,
        wait_time_ms - signal_wait_time_ms as resource_wait_time_ms,
        CAST(100.0 * wait_time_ms / SUM(wait_time_ms) OVER() AS DECIMAL(5,2)) as wait_time_percent,
        CAST(100.0 * signal_wait_time_ms / NULLIF(wait_time_ms, 0) AS DECIMAL(5,2)) as signal_wait_percent
    FROM sys.dm_os_wait_stats
    WHERE wait_type NOT IN (
        'CLR_SEMAPHORE', 'LAZYWRITER_SLEEP', 'RESOURCE_QUEUE', 'SLEEP_TASK',
        'SLEEP_SYSTEMTASK', 'SQLTRACE_BUFFER_FLUSH', 'WAITFOR', 'LOGMGR_QUEUE',
        'CHECKPOINT_QUEUE', 'REQUEST_FOR_DEADLOCK_SEARCH', 'XE_TIMER_EVENT',
        'BROKER_TO_FLUSH', 'BROKER_TASK_STOP', 'CLR_MANUAL_EVENT', 'CLR_AUTO_EVENT',
        'HADR_WORK_QUEUE', 'HADR_NOTIFICATION_DEQUEUE', 'VDI_CLIENT_OTHER', 'SOS_WORK_DISPATCHER'
    )
    AND wait_time_ms > 0
)
SELECT TOP 20
    wait_type,
    waiting_tasks_count,
    CAST(wait_time_ms / 1000.0 AS DECIMAL(12,2)) as wait_time_seconds,
    CAST(max_wait_time_ms / 1000.0 AS DECIMAL(12,2)) as max_wait_seconds,
    CAST(signal_wait_time_ms / 1000.0 AS DECIMAL(12,2)) as signal_wait_seconds,
    CAST(resource_wait_time_ms / 1000.0 AS DECIMAL(12,2)) as resource_wait_seconds,
    wait_time_percent,
    signal_wait_percent,
    CAST(wait_time_ms / NULLIF(waiting_tasks_count, 0) AS DECIMAL(12,2)) as avg_wait_time_ms,
    -- Classificação de impacto
    CASE
        WHEN wait_type LIKE 'PAGEIOLATCH%' THEN 'DISK I/O ISSUE'
        WHEN wait_type LIKE 'WRITELOG%' THEN 'LOG WRITE ISSUE'
        WHEN wait_type LIKE 'LCK%' THEN 'BLOCKING/LOCKING'
        WHEN wait_type LIKE 'PAGELATCH%' THEN 'MEMORY CONTENTION'
        WHEN wait_type LIKE 'CXPACKET%' THEN 'PARALLELISM'
        WHEN wait_type LIKE 'SOS_SCHEDULER_YIELD' THEN 'CPU PRESSURE'
        ELSE 'OTHER'
    END as wait_category,
    -- Recomendação
    CASE
        WHEN wait_type LIKE 'PAGEIOLATCH%' AND wait_time_percent > 10 THEN 'Check disk I/O performance'
        WHEN wait_type LIKE 'WRITELOG%' AND wait_time_percent > 10 THEN 'Check transaction log disk'
        WHEN wait_type LIKE 'LCK%' AND wait_time_percent > 10 THEN 'Investigate blocking queries'
        WHEN wait_type LIKE 'CXPACKET%' AND wait_time_percent > 25 THEN 'Review MAXDOP settings'
        WHEN wait_type = 'SOS_SCHEDULER_YIELD' AND wait_time_percent > 10 THEN 'CPU pressure - check queries'
        ELSE 'Monitor'
    END as recommendation
FROM WaitStats
ORDER BY wait_time_percent DESC
"""
```

---

## 3. QUERIES QUE NÃO DEVEM SER ADICIONADAS

### 3.1 Get-BasicPerformanceAnalysis-WaitStats.sql
**Motivo:** Duplica funcionalidade de WAIT_STATS existente

### 3.2 Get-DetailedResourcePressureAnalysis.sql
**Motivo:** Query sintética com dados mockados (não usa DMVs reais)

### 3.3 Get-CriticalDatafilesAnalysis.sql
**Motivo:** Muito simplificada, falta análise real de filegroups

### 3.4 Get-IndexMaintenance-Optimized.sql e Get-IndexMaintenance.sql
**Motivo:** Duplicam INDEX_FRAGMENTATION que já existe e será melhorada

### 3.5 Análise completa de performance (script muito longo)
**Motivo:** Muitas queries em um único script, melhor quebrar em componentes

---

## 4. SUMMARY - RECOMENDAÇÕES FINAIS

### Queries a SUBSTITUIR:
1. ✅ **INDEX_FRAGMENTATION** (linha 215-229) → Substituir por versão enhanced
2. ✅ **STATISTICS_OUTDATED** (linha 651-693) → Substituir por versão enhanced

### Queries a ADICIONAR:
1. ⭐⭐⭐ **BACKUP_HISTORY_ANALYSIS** - Alta prioridade
2. ⭐⭐⭐ **MISSING_INDEX_ANALYSIS** - Alta prioridade
3. ⭐⭐ **QUERY_PERFORMANCE_ANALYSIS** - Média prioridade
4. ⭐⭐ **WAIT_STATISTICS_ENHANCED** - Média prioridade (melhorar existente)
5. ⭐ **DUPLICATE_INDEXES_ANALYSIS** - Baixa prioridade

### Queries a REMOVER:
- Nenhuma (manter compatibilidade)

### Buttons SQL Diag a ADICIONAR:
```python
# No SQL Diag interface, adicionar:
- "Análise de Backups" → BACKUP_HISTORY_ANALYSIS
- "Índices Ausentes" → MISSING_INDEX_ANALYSIS
- "Queries Lentas" → QUERY_PERFORMANCE_ANALYSIS
- "Índices Duplicados" → DUPLICATE_INDEXES_ANALYSIS
```

---

## 5. PRÓXIMOS PASSOS

1. ✅ Atualizar INDEX_FRAGMENTATION em queries.py
2. ✅ Atualizar STATISTICS_OUTDATED em queries.py
3. ⏳ Adicionar 4 novas queries em queries.py
4. ⏳ Atualizar interface SQL Diag com novos buttons
5. ⏳ Testar todas as queries em ambiente de produção
6. ⏳ Documentar no README.md

**Próxima ação:** Implementar alterações em queries.py

---

**Status:** ✅ ANÁLISE COMPLETA - PRONTO PARA IMPLEMENTAÇÃO
