---
version: cross-cutting
component: shared
canonical_path: n/a
last_validated: 2026-05-14
owner_specialist: watcherdb-v1-intel-specialist
references:
  - shared_infra_db.md
  - v_specific/v1/README.md
  - modules/backups.md
  - kpis/backups_kpis.md
---

<!-- LICENSE: INTERNAL — proprietary WatcherDB family knowledge. Not for external distribution. -->

# WatcherDB_Intelligence — Database Schema Reference

**Owner**: watcherdb-v1-intel-specialist
**Cross-reference**: `shared_infra_db.md` for ownership rules and veto protocol.

This file documents the physical table structure of `WatcherDB_Intelligence`. It is a
read reference — the authoritative DDL lives in V1's `database/` directory.

---

## Wave D (2026-05-14) — 2 tabelas adicionadas

V1 commit `fa653dd` (feat/v1-wave-D) adicionou 2 tabelas para suportar
o 3-tile semantic split de Wave D:

| # | Logical name | Tipo | Retention | Refs |
|---|---|---|---|---|
| 14 | `KPI_MSSQL_BACKUP_EXEC_FAILURES_STG` | BLUE/GREEN | 14 dias | sysjobhistory.run_status IN (0,2,3) + backupset.is_damaged=1 + has_backup_checksum=0 |
| 15 | `KPI_MSSQL_BACKUP_JOBS_DISABLED_STG` | Snapshot (replace inactive per ciclo) | N/A | sysjobs.enabled=0 WHERE categoria backup OR nome `%backup%`/`%bkp%` |

Total agora: 15 KPI table pairs (era 13). Collectors em V1 `services/collector_service/collectors/`:
`collect_backup_failures.py` + `collect_backup_jobs_disabled.py` (commit 599ddd7).

Frequencia: 15 min PRD, 30 min QA-TST. Consumo: V3.3 (4905076 + efb2511) e V6
(d47924c + 6d09648).

---

## 13 KPI BLUE/GREEN Table Pairs

Each entry has two physical tables: `<NAME>_BLUE` and `<NAME>_GREEN`. The active table
is determined at runtime by `KPI_STG_ACTIVE_TABLE`. The inactive table is written by the
collector while the active one serves reads.

| # | Logical name (STG base) | Physical tables | Swap applies |
|---|------------------------|-----------------|--------------|
| 1 | `KPI_MSSQL_FG_USAGE_STG` | `_BLUE` / `_GREEN` | Yes |
| 2 | `KPI_MSSQL_BACKUPS_STG` | `_BLUE` / `_GREEN` | Yes |
| 3 | `KPI_MSSQL_BACKUP_STATUS_STG` | `_BLUE` / `_GREEN` | Yes |
| 4 | `KPI_MSSQL_BLOCKED_SESSIONS_STG` | `_BLUE` / `_GREEN` | Yes |
| 5 | `KPI_MSSQL_BLOCKED_USERS_STG` | `_BLUE` / `_GREEN` | Yes |
| 6 | `KPI_MSSQL_DB_AVAILABILITY_STG` | `_BLUE` / `_GREEN` | Yes |
| 7 | `KPI_MSSQL_DB_IO_STATS_STG` | `_BLUE` / `_GREEN` | Yes |
| 8 | `KPI_MSSQL_DISK_USAGE_STG` | `_BLUE` / `_GREEN` | Yes |
| 9 | `KPI_MSSQL_ERRORLOG_STG` | `_BLUE` / `_GREEN` | Yes |
| 10 | `KPI_MSSQL_LONG_LOCKS_STG` | `_BLUE` / `_GREEN` | Yes |
| 11 | `KPI_MSSQL_SERVICE_STATUS_STG` | `_BLUE` / `_GREEN` | Yes |
| 12 | `KPI_MSSQL_TLOG_USAGE_STG` | `_BLUE` / `_GREEN` | Yes |
| 13 | `KPI_MSSQL_INST_AVAILABILITY_STG` | `_BLUE` / `_GREEN` x PRD/QA/TST = **6 physical tables** | Yes |

> Table #13 (`INST_AVAILABILITY`) is the only one with environment-segmented physical tables.
> Physical count for #13: `_PRD_BLUE`, `_PRD_GREEN`, `_QA_BLUE`, `_QA_GREEN`, `_TST_BLUE`, `_TST_GREEN`.

---

## Exception Tables (no swap)

| Table | Status | Notes |
|-------|--------|-------|
| `KPI_MSSQL_DEADLOCKS_STG` | Permanent exception | Append-only event log. Direct query model. Ref: `SETUP_BLUE_GREEN_COMPLETO.sql:21`. |
| `KPI_MSSQL_AGENT_JOBS_STG` | Exception (OPEN finding) | Added post-setup. Currently no swap. FIND-20260506-001 V1 P1 OPEN — decision pending. |

---

## Control Table

| Table | Role |
|-------|------|
| `KPI_STG_ACTIVE_TABLE` | One row per KPI table pair. Controls which physical table (`BLUE` or `GREEN`) is currently active for reads. |

The swap proc (`usp_swap_kpi_stg_tables`) acquires `UPDLOCK` on the relevant row in `KPI_STG_ACTIVE_TABLE` before flipping the pointer. See `shared_infra_db.md` for swap protocol details.

---

## Canonical Consumer Views

V3.3 and V6 consume data exclusively through these views. Direct table access is forbidden.

| View file | Purpose |
|-----------|---------|
| `CREATE_SERVICE_STATUS_VIEWS.sql` | Service status aggregates |
| `CREATE_SERVER_OFFLINE_VIEWS.sql` | Server offline / availability state |
| `CREATE_DASHBOARD_VIEWS.sql` | Dashboard KPI summaries |

All files reside in `<drive>:\...\WATCHERDB INTELLIGENCE V1\database\`.

---

## Key Stored Procedures

| Procedure | Location in DDL | Purpose |
|-----------|----------------|---------|
| `usp_swap_kpi_stg_tables` | `SETUP_BLUE_GREEN_COMPLETO.sql:97-139` | Atomic BLUE/GREEN pointer swap with `UPDLOCK` + TRY/CATCH + ROLLBACK on error |

---

## Physical Table Count Summary

| Category | Count |
|----------|-------|
| BLUE/GREEN pairs (standard, 2 tables each) | 12 pairs = 24 tables |
| BLUE/GREEN pairs with env segmentation (#13) | 1 pair x 3 envs = 6 tables |
| Exception tables (no swap) | 2 tables |
| Control table | 1 table |
| **Total physical tables** | **33** |

> Note: view count is separate and tracked per DDL file in V1's `database/` directory.

---

## execute_intelligence_query — Gotcha datetime→isoformat

**Localização**: `api/routers/intelligence/helpers.py:182-186` (V3.3); função equivalente
presente em todos os routers que consomem `WatcherDB_Intelligence`.

### Comportamento documentado

```python
# helpers.py:183-186
if isinstance(value, Decimal):
    value = float(value)
elif isinstance(value, datetime):
    value = value.isoformat()   # <-- todos os datetime tornam-se str
row_dict[col] = value
```

Todos os campos `datetime` retornados por queries ODBC são convertidos para `str` ISO 8601
**antes** de chegarem ao caller. Não há datetimes nativos no dict de retorno.

### Gotcha — isinstance falha silenciosamente downstream

Qualquer código que faça:

```python
if isinstance(update_ts, datetime):   # retorna False — update_ts é str
    in_window = update_ts >= cutoff
```

retorna `False` sempre, sem erro, sem log. O resultado é que a condição nunca é satisfeita
e o KPI fica a 0 silenciosamente.

**FIND-20260513-101 (P1, RESOLVED 2026-05-13)**: este padrão errado estava em
`collect_backup_status()` em dois sítios. Causou `failed_count = 0` durante ~48h em PRD.

### Padrão correcto

```python
# Aceitar str OR datetime — normalizar antes de comparar
if isinstance(update_ts, datetime):
    in_window = update_ts >= cutoff_48h
elif isinstance(update_ts, str) and update_ts:
    try:
        in_window = datetime.fromisoformat(update_ts) >= cutoff_48h
    except ValueError:
        in_window = False
```

Ou, alternativa defensiva para novos KPIs:

```python
def parse_ts(val) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    return None
```

### Audit recomendado — outros KPIs afectados

Este padrão aplica-se a **todos os KPIs** que recebam campos datetime de
`execute_intelligence_query` / `execute_intelligence_query_async` e façam comparações
temporais downstream. KPIs a auditar prioritariamente:

| KPI / função | Ficheiro | Campo datetime a verificar |
|---|---|---|
| `collect_blocked_sessions()` | `helpers.py` | `Block_Start_Time`, `Login_Time` |
| `collect_long_locks()` | `helpers.py` | `Lock_Start_Time` |
| `collect_alwayson_status()` | `helpers.py` | `Last_Failover_Time` |
| `collect_agent_jobs()` | `helpers.py` | `Last_Run_Date`, `Next_Run_Date` |
| Qualquer novo KPI com janela temporal | qualquer router | campo `*_TS`, `*_Time`, `*_Date` |

**Acção requerida antes de merge de qualquer novo KPI com janela temporal**: confirmar
que comparações de datetime usam o padrão correcto acima ou utilitário `parse_ts()`.

---

## Wave B (2026-07-29) — Indexação: o que os DMV mostraram

Auditoria de indexação feita com `sys.dm_db_missing_index_details`,
`sys.dm_db_index_usage_stats`, `sys.dm_db_index_physical_stats` e
`sys.dm_db_stats_properties`. Registado aqui porque **contraria a intuição** e uma sessão
futura tenderá a repetir o mesmo caminho.

### O que NÃO é problema nesta base (verificado, não assumido)

| Hipótese comum | Realidade medida (2026-07-29) |
|---|---|
| Fragmentação de índices | Apenas **2** índices acima de 5% em ~3 GB (`IX_Anomaly_Instance` 5,60%, `PK_KPI_OS_CPU_HIST` 5,18%). Rebuild não tem trabalho útil |
| Estatísticas desactualizadas | `auto_update_stats` ligado e a funcionar. As estatísticas com `last_updated NULL` pertencem todas a tabelas **vazias** |
| `page_verify` mal configurado | Já em `CHECKSUM`; `msdb.dbo.suspect_pages` vazia |
| Cobertura de índices em falta | A cobertura base existe — 227 declarações de índice no canonical |

### O que É problema

1. **`DBCC CHECKDB` nunca correu** até 2026-07-29 (`dbi_dbccLastKnownGood = 1900-01-01`,
   base criada em 2026-04-06). Corrigido nesta wave.
2. **~250 índices sem uma única leitura**, com custo de escrita real. Piores casos:
   `kg_relations` (4 índices × ~4,99M escritas, 32k linhas) e `kg_entities`
   (3 × ~4,63M). Duplicados confirmados: `IX_ALWAYSON_Instance_Database` +
   `IX_STG_BLUE_PRD_InstDB`, e `IX_DB_State` + `IX_DB_AVAIL_BLUE_State` (mais pares GREEN).
   **Não dropar sem** `sqlserver_start_time` (os contadores zeram no restart) **e sem**
   parecer do `watcherdb-v1-intel-specialist` — a maioria é schema V5/V6.
3. **Dois índices em falta**, ambos servindo consumo **V5/V6** e não V3.3:
   `IX_ANOMALY_DETECTION_Abertas` (filtrado `resolved_at IS NULL`) e
   `IX_ALWAYSON_FAILOVER_HIST_TS_Source`. Criados nesta wave.

### Regra de índices no canonical — armadilha confirmada

> Índices declarados **dentro** do bloco `IF NOT EXISTS (SELECT 1 FROM sys.tables ...)`
> **só chegam a fresh installs**. O bloco não reentra quando a tabela já existe, logo
> qualquer instalação corrente fica sem eles, sem aviso.

Índice novo em tabela existente vai **sempre** fora do bloco da tabela, com guard próprio:

```sql
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = '<nome>' AND object_id = OBJECT_ID('dbo.<tabela>'))
BEGIN
    CREATE NONCLUSTERED INDEX <nome> ON dbo.<tabela> (...);
    PRINT '  [OK] Index <nome> criado (Wave <X>)';
END
ELSE PRINT '  [SKIP] Index <nome> ja existe';
GO
```

Referência do padrão correcto no canonical: linhas 1943, 2003, 6818.
Ocorrências corrigidas nesta wave: secções 23.1 e 31.1.

### Manutenção — postura decidida

- **Tabelas `*_STG*` ficam de fora** de qualquer manutenção de índices: são reescritas a
  cada ciclo de coleta (BLUE/GREEN com troca atómica), a fragmentação regressa no ciclo
  seguinte e o rebuild concorre com o `usp_swap_kpi_stg_tables` (que usa `WITH UPDLOCK`).
- **Janela de manutenção** sai de `KPI_MSSQL_COLLECTION_HISTORY`, nunca de um horário
  arbitrário.
- **No cliente não se instala motor de manutenção.** A `WatcherDB_Intelligence` entra na
  solução que o cliente já tem; a entrega é runbook. O produto lê, não altera.

### Índice filtrado — restrição que viaja com ele

`IX_ANOMALY_DETECTION_Abertas` é filtrado. Qualquer sessão que faça INSERT/UPDATE/DELETE
em `KPI_MSSQL_ANOMALY_DETECTION` precisa de `ANSI_NULLS` e `QUOTED_IDENTIFIER` a `ON`,
ou a operação falha. O ODBC cumpre por omissão — mas se aparecerem falhas de insert de
anomalias, procurar aqui primeiro.

---

## Schema Change Protocol

Any schema change must:

1. Be proposed via a cross-product review ticket.
2. Dispatch `watcherdb-v1-intel-specialist` for mandatory review (veto rights apply).
3. Update canonical DDL in V1 project ONLY — no shadow DDL in V3.3 or V6.
4. Update this file (`intelligence_db_schema.md`) in the same wave.
5. Update `index.json` with new SHA-256 hash for this file.
6. If adding a new STG table: decide swap / no-swap at design time and register here before merge.
