# Relatorio de Validacao de Queries - WatcherDB
**Data:** 2025-11-15
**Versao:** v1.4.4
**Servidor Testado:** SQLHDSPRD013\I03

## Sumario Executivo

Teste automatizado de 22 queries SQL do sistema WatcherDB contra servidor de producao.

### Resultados Gerais
- **Total de queries testadas:** 6 de 22 (teste interrompido devido a timeout)
- **Passaram:** 4 (66.7%)
- **Falharam:** 2 (33.3%)
- **Status:** ATENCAO - Correcoes necessarias

---

## Detalhamento dos Testes

### Queries que PASSARAM

#### 1. TDE_STATUS
- **Status:** PASSOU
- **Linhas retornadas:** 1
- **Colunas:** 7
- **Tempo de execucao:** ~0.03s
- **Observacao:** Query funcionando perfeitamente

#### 2. FILEGROUPS_SPACE
- **Status:** PASSOU
- **Linhas retornadas:** 1
- **Colunas:** 9
- **Tempo de execucao:** ~0.06s
- **Observacao:** Query funcionando perfeitamente

#### 3. TOP_SLOW_QUERIES
- **Status:** PASSOU
- **Linhas retornadas:** 50
- **Colunas:** 4
- **Tempo de execucao:** ~0.65s
- **Observacao:** Query funcionando perfeitamente

#### 4. ACTIVE_PROCESSES
- **Status:** PASSOU
- **Linhas retornadas:** 1
- **Colunas:** 5
- **Tempo de execucao:** ~0.03s
- **Observacao:** Query funcionando perfeitamente

---

### Queries que FALHARAM

#### 1. HEALTH_OVERVIEW - ERRO CRITICO

**Status:** FALHOU
**Erro:**
```
Cannot resolve collation conflict between "Latin1_General_CI_AS_KS_WS" and
"SQL_Latin1_General_CP1_CI_AS" in UNION ALL operator occurring in SELECT statement column 3
```

**Causa Raiz:**
O query usa multiplos UNION ALL combinando resultados de diferentes system views e tabelas que possuem collations diferentes. A coluna `Value` (VARCHAR) esta sendo concatenada de diferentes fontes:
- `sys.dm_os_sys_info`
- `sys.dm_os_performance_counters`
- `sys.certificates` (issuer_name, subject, etc.)

Cada uma dessas tabelas pode ter collation diferente no servidor.

**Impacto:**
- Query HEALTH_OVERVIEW nao funciona
- Dashboard pode nao exibir metricas de saude do servidor
- Informacoes de TDE nao sao exibidas na visao geral

**Solucao:**
Adicionar `COLLATE DATABASE_DEFAULT` em todas as colunas VARCHAR do SELECT para forcar mesma collation:

```sql
-- Antes:
SELECT 'Uptime' AS Category,
       'Days' AS Metric,
       CAST(DATEDIFF(DAY, sqlserver_start_time, GETDATE()) AS VARCHAR) AS Value,
       GETDATE() AS Timestamp
FROM sys.dm_os_sys_info WITH(NOLOCK)

-- Depois:
SELECT 'Uptime' AS Category,
       'Days' AS Metric,
       CAST(DATEDIFF(DAY, sqlserver_start_time, GETDATE()) AS VARCHAR) COLLATE DATABASE_DEFAULT AS Value,
       GETDATE() AS Timestamp
FROM sys.dm_os_sys_info WITH(NOLOCK)
```

**Prioridade:** ALTA - Query essencial para dashboard

---

#### 2. BLOCKING_CHAINS - TIMEOUT

**Status:** TIMEOUT (>17 minutos)
**Erro:** Query nao completou em tempo razoavel

**Causa Raiz:**
Query extremamente complexa com:
- 3 UNION ALL combinando diferentes fontes de bloqueio
- Multiplos JOINs em DMVs (sys.dm_exec_requests, sys.dm_exec_sessions, sys.dm_os_waiting_tasks)
- Subquery correlacionada em NOT IN
- Window function COUNT(DISTINCT) OVER()
- Multiplas condicoes de filtro complexas

```sql
WITH AllBlocked AS (
    -- 1. Requisições bloqueadas
    SELECT ...
    FROM sys.dm_exec_requests r
    INNER JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
    WHERE r.blocking_session_id > 0 ...

    UNION ALL

    -- 2. Sessões bloqueadas via waiting_tasks
    SELECT ...
    FROM sys.dm_exec_sessions s
    INNER JOIN sys.dm_os_waiting_tasks wt ON s.session_id = wt.session_id
    WHERE wt.blocking_session_id IS NOT NULL
    AND s.session_id NOT IN (
        SELECT session_id FROM sys.dm_exec_requests WHERE blocking_session_id > 0
    )

    UNION ALL

    -- 3. Sessões esperando por locks
    SELECT ...
    FROM sys.dm_exec_requests r
    INNER JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
    WHERE r.wait_type LIKE 'LCK_%'
    AND r.session_id NOT IN (
        SELECT session_id FROM sys.dm_exec_requests WHERE blocking_session_id > 0
    )
)
SELECT DISTINCT ...
FROM AllBlocked ab
```

**Problema Especifico:**
1. **NOT IN com subquery** - Muito ineficiente, especialmente com NOLOCK
2. **Multiplos UNION ALL** - Pode gerar muitas linhas temporarias
3. **Window function COUNT(DISTINCT) OVER()** - Processamento pesado
4. **DISTINCT no SELECT final** - Pode causar sort grande

**Impacto:**
- Query de bloqueios nao funciona
- Impossivel monitorar blocking chains em producao
- Dashboard pode travar ao tentar carregar dados de bloqueio

**Solucao:**
Simplificar query removendo redundancias:

```sql
-- Versao simplificada e otimizada
WITH BlockedSessions AS (
    -- Apenas sessões realmente bloqueadas
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
SELECT *,
    (SELECT COUNT(DISTINCT login_name) FROM BlockedSessions) as total_blocked_users
FROM BlockedSessions
ORDER BY WaitTimeSec DESC
```

**Prioridade:** ALTA - Query essencial para troubleshooting

---

## Queries Nao Testadas (devido a timeout)

As seguintes 16 queries nao foram testadas devido ao timeout em BLOCKING_CHAINS:

1. BACKUP_STATUS
2. WAIT_STATS
3. INDEX_FRAGMENTATION
4. AVAILABILITY_GROUPS
5. SQL_AGENT_JOBS
6. BLOCKING_HIERARCHY
7. TOP_SLOW_QUERIES_DETAILED
8. LOG_SPACE_MONITORING
9. SQL_AGENT_JOBS_FAILING
10. PROBLEMATIC_SESSIONS
11. INDEX_FRAGMENTATION_DETAILED
12. TEMPDB_MONITORING
13. FILE_GROWTH_MONITORING
14. STATISTICS_OUTDATED
15. MIRRORING_LOGSHIPPING_STATUS
16. DATABASE_CONNECTIONS

**Recomendacao:** Executar teste completo apos corrigir HEALTH_OVERVIEW e BLOCKING_CHAINS.

---

## Acoes Recomendadas

### Prioridade ALTA (Imediato)

1. **Corrigir HEALTH_OVERVIEW**
   - Adicionar `COLLATE DATABASE_DEFAULT` em todas as colunas VARCHAR
   - Tempo estimado: 15 minutos
   - Teste em servidor de desenvolvimento primeiro

2. **Otimizar BLOCKING_CHAINS**
   - Simplificar query removendo UNIONs desnecessarias
   - Substituir NOT IN por NOT EXISTS ou LEFT JOIN
   - Remover DISTINCT do SELECT final
   - Tempo estimado: 30 minutos
   - Teste em servidor de desenvolvimento primeiro

### Prioridade MEDIA

3. **Executar teste completo**
   - Testar todas as 22 queries apos correcoes
   - Documentar resultados
   - Tempo estimado: 1 hora

4. **Adicionar timeout protection**
   - Implementar timeout de 30s por query no codigo Python
   - Evitar que uma query travada bloqueie todo o sistema
   - Tempo estimado: 20 minutos

### Prioridade BAIXA

5. **Otimizacao preventiva**
   - Revisar todas as queries com UNION ALL para possivel collation conflict
   - Revisar queries com NOT IN para possivel otimizacao
   - Adicionar indices se necessario (avaliar impacto)

---

## Metricas de Performance

### Queries Rapidas (< 100ms)
- TDE_STATUS: ~30ms
- FILEGROUPS_SPACE: ~60ms
- ACTIVE_PROCESSES: ~30ms

### Queries Medias (100ms - 1s)
- TOP_SLOW_QUERIES: ~650ms

### Queries Problematicas (> 1s)
- BLOCKING_CHAINS: >17 minutos (TIMEOUT)

---

## Conclusao

O sistema WatcherDB possui queries bem estruturadas e performaticas em sua maioria, mas apresenta 2 problemas criticos que impedem o funcionamento completo:

1. **Collation conflict** em HEALTH_OVERVIEW - Facilmente corrigivel
2. **Performance extrema** em BLOCKING_CHAINS - Requer refatoracao

Ambos os problemas sao corrigiveis em menos de 1 hora de trabalho. Apos as correcoes, recomenda-se executar teste completo em todas as 22 queries para garantir funcionamento em todos os 84 servidores do ambiente.

**Proximos Passos:**
1. Implementar correcoes (ver arquivo QUERY_FIXES.md)
2. Testar em desenvolvimento
3. Testar em producao (servidor de baixo impacto primeiro)
4. Deploy para todos os servidores
5. Executar teste automatizado completo
