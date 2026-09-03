# KPI Catalog V3.3 (seed)

Catálogo dos KPI cards do dashboard V3.3 Standard Edition.

**Status:** SEED — extraído de `api/routers/kpis_metadata.py` (modos de coleta) e
`MEMORY.md/project_kpi_rules.md`. Cobre os principais KPIs core; thresholds são
indicativos (verificar config cliente).

**Owner:** `watcherdb-v33-specialist`
**Reviewers:** `watcherdb-customer-success-persona`, DBA Lead

---

## 1. Estrutura

Cada KPI card no `templates/watcherdb_portal.html` SPA tem:

- **Source:** view ou tabela em `WatcherDB_Intelligence` BD partilhada
- **Coletor:** alimentado pelo V1 collector (Windows Task Scheduler)
- **Threshold:** crítico / warning configurável
- **Tier:** Std (presente em V3.3) / Pro-only (não entra em V3.3)

## 2. Modos de coleta (canónicos)

Definidos em `api/routers/kpis_metadata.py:KPI_MODES`.

| Modo | KPIs incluídos | Cadence |
|---|---|---|
| `kpi-fast` | 13 KPIs principais (blocked, tlog, alwayson, instance, processes, db_avail, backups, io, disk, filegroup, cpu_critical, memory_critical, plus 1 derived) | 5 min |
| `kpi-only` | `kpi-fast` + `long_locks` + `deadlocks` + `service_status` | 10-15 min |
| `locks-only` | `long_locks`, `deadlocks` (apenas) | sob demanda |

## 3. KPI cards (Std, presentes em V3.3)

### Disponibilidade

| KPI | Source | Threshold | Notes |
|---|---|---|---|
| **Instance Availability** | `KPI_MSSQL_INSTANCE_AVAILABILITY_AGG` | service down → critical | Ping TCP + sp_who |
| **DB Availability** | `KPI_MSSQL_DB_AVAILABILITY_AGG` | DB offline → critical | per-database state |
| **AlwaysOn Status** | `KPI_MSSQL_ALWAYSON_STATUS_AGG` | sync_state != HEALTHY → warning | + `KPI_MSSQL_ALWAYSON_FAILOVERS_HIST` para failovers histórico |
| **SQL Não Respondeu** | reconcile via `INST_AVAILABILITY` | TCP timeout 15s → flag | Renomeado em `7a9355a` (era "SQL Services Down"). Reconcile bug fixes em `33c2fed` + `9e967c6` |

### Lock / Concurrency

| KPI | Source | Threshold | Notes |
|---|---|---|---|
| **Blocked Sessions** | `KPI_MSSQL_BLOCKED_SESSIONS_AGG` | > 5 simultaneous → warning, > 20 → critical | Lead/blocker chain |
| **Blocked Users** | derived from blocked_sessions | distinct user count | UI surface |
| **Long Locks** | `KPI_MSSQL_LONG_LOCKS_AGG` | wait > 60s → warning | XE event-based |
| **Deadlocks** | `KPI_MSSQL_DEADLOCKS_AGG_VIEW` | > 0 nos últimos 5min → critical | Shred XML via system_health XE; pre-flight check em `step_6_source` (`modules/performance/investigators/deadlocks.py`) |

### Performance / IO

| KPI | Source | Threshold | Notes |
|---|---|---|---|
| **DB IO Stats** | `KPI_MSSQL_DB_IO_STATS_AGG` | latency > 20ms read / 100ms write → warning | sys.dm_io_virtual_file_stats delta |
| **Processes Alarm** | `KPI_MSSQL_PROCESSES_ALARM_AGG` | wait_type específico → flag | Ver `docs/features/EXPLICACAO_PROCESSES_ALARM.md` |
| **CPU Critical** | `KPI_MSSQL_OS_PERF_AGG` (CPU%) | **>= 95% sustentado** → critical | OS-level perf counter |
| **Memory Critical** | `KPI_MSSQL_OS_PERF_AGG` (Memory%) | **>= 99% com page faults / swap** → critical | Both conditions required |

### Disk / Storage

| KPI | Source | Threshold | Notes |
|---|---|---|---|
| **DB Disk File System** | `KPI_MSSQL_DB_DISK_FILE_SYSTEM_AGG` | < 10% free → warning, < 5% free → critical | OS disk + DB filegroup blend |
| **Filegroup Usage** | `KPI_MSSQL_FILEGROUP_USAGE_AGG` | autogrowth events recentes ou > 90% used → warning | Ver `docs/features/AJUSTE_CARDS_KPI.md` |
| **DB Transaction Logs (TLOG)** | `KPI_MSSQL_DB_TRANSACTION_LOGS_AGG` | log usage > 80% → warning, > 95% → critical | `tlog_usage` na config |

### Backup

| KPI | Source | Threshold | Notes |
|---|---|---|---|
| **Backup Status** | `KPI_MSSQL_BACKUP_STATUS_AGG` | Schedule-based gap detection (não horas fixas) | Ver `docs/features/BACKUP_SCHEDULE_BASED_GAP_DETECTION.md` |

### Jobs / Schedule

| KPI | Source | Threshold | Notes |
|---|---|---|---|
| **Service Status** | `KPI_MSSQL_SERVICE_STATUS_AGG` | service down → critical | SQL Server services + dependencies |

## 4. Padrões de query / gotchas

### Normalização de instance name

Views podem ter `\` ou `_` no nome de instance. Filtrar **sempre**:

```sql
WHERE UPPER(REPLACE(Instance, CHAR(92), '_'))
    = UPPER(REPLACE(@instance, CHAR(92), '_'))
```

`CHAR(92)` em vez de `'\\'` literal — evita escape hell Python↔T-SQL.

### Fallback AGG → DET

Quando AGG_VIEW vem vazia mas DET tem dados (formatos divergentes), calcular
counts da DET. Common pattern em `intelligence_kpis.py`.

### DMV varbinary

`query_hash`, `plan_handle` vêm como `bytes` em pyodbc. Usar `_json_safe` em
`modules/performance/base.py` antes de serializar.

### Pool decoding

`api/connection_pool.py` faz `setdecoding(SQL_WCHAR, encoding='utf-16-le')` +
`setdecoding(SQL_CHAR, encoding='cp1252')` para servers monitorizados (DMVs com
collation Latin1).

## 5. Features Pro-only (NÃO presentes em V3.3)

Lista canónica em `docs/FEATURE_MATRIX.md`. Resumo do que **não** entra em V3.3:

- AI/ML cards (Risk Scores, Latent Risk, Health Score Engine)
- Capacity Planning, SLA Calculator
- Anomaly Detection ML-powered
- Knowledge Graph, Times/Newspaper
- Autonomous Agent, Cascade Intelligence, Silent Degradation
- Recomendações AI, Análise Causa Raiz AI
- Executive Report, Gravity Map, Stress Test
- SSIS Executions, 2PC monitoring, cluster advanced

Se algum destes aparecer em V3.3 → `[PROACTIVE FINDING] tiering | <path:linha> | high`.

## 6. References

- `api/routers/kpis_metadata.py` — KPI_MODES + thresholds
- `api/routers/intelligence_kpis.py` — endpoints `/api/v1/intelligence/*`
- `api/routers/intelligence/helpers.py` — collect_* helpers
- `api/routers/queries/` — SQL queries por KPI
- `templates/watcherdb_portal.html` — SPA com cards
- `docs/features/AJUSTE_CARDS_KPI.md` — design decisions
- `docs/features/EXPLICACAO_PROCESSES_ALARM.md` — processes alarm rationale
- `docs/features/BACKUP_SCHEDULE_BASED_GAP_DETECTION.md` — backup logic
- `MEMORY.md/project_kpi_rules.md` — rules canonical (cross-session memory)
- ~/.nestor-library/watcherdb-family/pipeline_maps/V3.3_PIPELINE_MAP.md — KPI flow canonical (se existir; senão ver `docs/architecture/`)

## Próxima iteração

- [ ] Validar threshold crítico vs warning de cada card contra config cliente actual
- [ ] Adicionar query SQL de exemplo por KPI (read-only, pra debug)
- [ ] Cross-link com `runbooks/` (Performance Module — investigators)
