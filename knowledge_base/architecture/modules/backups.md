---
version: cross-cutting
component: shared
canonical_path: n/a
last_validated: 2026-05-20
owner_specialist: core-librarian
license: INTERNAL
references:
  - cross_cutting/tier_matrix.md
  - cross_cutting/shared_infra_db.md
  - cross_cutting/intelligence_db_schema.md
  - modules/collector_pipeline.md
  - modules/alwayson.md
---

<!-- LICENSE: INTERNAL — proprietary WatcherDB family knowledge. Not for external distribution. -->

# Module: Backups

Cross-version reference for backup monitoring: V1 collects from `msdb` into BLUE/GREEN STG; V3.3 provides dual-path (KPI dashboard cards via STG + direct-msdb gap analysis); V6 adds AI Expert Swarm with compound evidence and AG-context cross-talk.

## Wave M (2026-05-20) — AG-aware consolidation (msdb-per-node flaw resolution)

`msdb` e' local a cada no AlwaysOn (NAO replicado). KPI per-instance falhava
pos-failover: novo primary mostrava dados velhos, ex-primary (agora secondary)
tinha frescos mas Wave J filtrava. Solucao Wave M: collector colecta de TODOS
os nos + nova view `vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE` consolida via MAX por
(AgName, Database, Type) usando `KPI_MSSQL_ALWAYSON_STATUS_STG` topology.

Schema: + `Ag_Role VARCHAR(16) NULL` em `KPI_MSSQL_BACKUPS_STG` (PRIMARY/SECONDARY/NULL).
Collectors: Wave J filter REMOVIDO em 3 ficheiros (collect_backups, collect_backup_failures, async_data_collector).
V3.3 consumer: `helpers.py:1245` redirected para nova view.

Detalhes completos: `kpis/backups_kpis.md` seccao Wave M.

Wave J (2026-05-19) DEPRECATED por Wave M — filtro criava blind spot pos-failover.

## Wave D (2026-05-14) — 3-tile semantic split

3 KPIs distintos substituem o modelo gap-only Wave A5:

| Tile | Source Table | Causa Raiz Detectada |
|---|---|---|
| Backup Failed | `KPI_MSSQL_BACKUP_EXEC_FAILURES_STG` | Execution failure REAL (sysjobhistory run_status IN 0,2,3 + backupset.is_damaged + has_backup_checksum=0) |
| Backup Delayed | `KPI_MSSQL_BACKUPS_STG` | Gap RPO com severity warning/critical, janela 48h |
| Backup Jobs Disabled (NOVO) | `KPI_MSSQL_BACKUP_JOBS_DISABLED_STG` | SQL Agent jobs enabled=0 (silent gap cause) |

Detalhes completos: ver `kpis/backups_kpis.md` seccao Wave D.

Cross-tier propagation:
- V1: DDL fa653dd + collectors 599ddd7
- V3.3: backend 4905076 + frontend efb2511
- V6: backend d47924c + frontend 6d09648 (D6-min, sem B1 UX)

## Status por versão (Wave 2.B — 2026-05-06)

| Versão | Estado | Owner files representativos | Last update |
|--------|--------|----------------------------|-------------|
| V1 | ACTIVE — commit `0b2df9f` widened msdb window 24h→90d (breaking change for dormant DBs) | `services/collector_service/collectors/collect_backups.py` | 2026-05-06 |
| V3.3 | ACTIVE — dual-path; dashboard KPI via STG + direct-msdb for gap analysis | `api/routers/queries/backup.py`, `modules/monitoring/backup_analysis.py`, `api/routers/intelligence_kpis.py` | 2026-05-06 |
| V6 | ACTIVE — STG consumer via Expert Swarm; compound evidence + AG context cross-talk | `services/expert_agents/backup_expert.py`, `services/ai_assistant_service.py` | 2026-05-06 |

---

## V1 (Intelligence Collector)

**Canonical path**: `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\services\collector_service\collectors\`

**Owner files**:
- `collect_backups.py` — adapter wraps `scripts/collectors/collect_backups.py` (`BackupsCollector`)

**Role**: collector source

**DB tables touched**:

| Table | Write pattern | Notes |
|-------|---------------|-------|
| `KPI_MSSQL_BACKUPS_STG` | BLUE/GREEN swap | Canonical pattern; swap protects consumers |

**KPIs emitted**: backup history and status per instance and database; type, datetime, size, result.

**Collection frequencies**:
- PRD: 15 min
- QA/TST: 30 min

**V1-specific notes**:
- Pipeline: `asyncio.run(collector.collect_all(env))` → transform → validate → store.
- Schedule-based gap detection is consumer-side (V3.3 / V6 responsibility, not V1).
- Commit `0b2df9f` widened the `msdb` query window from 24 h to 90 d. This is a **breaking change** for environments with databases that have had no backup in the last 90 days — previously invisible dormant gaps now appear in STG and surface to V3.3/V6 consumers.

---

## V3.3 Standard

**Canonical path**: `c:/Users/ue_e-snetto/Documents/projetosPython/WATCHERDB_V3.3/api/routers/queries/backup.py`

**Owner files**:
- `api/routers/queries/backup.py` — backup query router
- `modules/monitoring/backup_analysis.py` — `BackupAnalysisEngine`; schedule-based gap detection; queries `msdb.dbo.backupset` directly; `ThreadPoolExecutor` for TDP log; version `2026-01-16_PARAMS_FIX_V2`
- `api/routers/intelligence_kpis.py` — dashboard KPI backup cards read `KPI_MSSQL_BACKUPS_STG`

**Role**: consumer (Intelligence DB for KPI dashboard) + own implementation (direct-msdb queries for gap analysis).

Dual-path architecture:
- Dashboard KPI cards → `KPI_MSSQL_BACKUPS_STG` (BLUE/GREEN, V1-written)
- Backup analysis module → direct `msdb` queries per request

**Routes / endpoints**:

| Endpoint | Notes |
|----------|-------|
| `GET /queries/backup/{server_id}` | Live msdb backup status |
| `GET /queries/backup-history-analysis/{server_id}` | Full history; AG-aware |
| `GET /queries/backup-gaps-{full,diff,log,summary,statistics}/{server_id}?days=N` | Gap variants |
| `GET /queries/tde-status/{server_id}` | TDE certificate status |
| `GET /queries/tde-database-status/{server_id}` | Per-database TDE status |

**Dashboard thresholds** (semântica pós-refactor FIND-KPI-BACKUP-TEMPORAL, commit 2026-05-13):

| Type | FAILED threshold | FAILED scope | DELAYED threshold | DELAYED scope |
|------|-----------------|--------------|-------------------|---------------|
| FULL | n/a | n/a | > 168 h (7 d) | Todas as instâncias (sem janela temporal) |
| DIFF | > 30 h | Update_TS >= NOW - 48 h | n/a | — |
| LOG  | > 2 h  | Update_TS >= NOW - 48 h | n/a | — |

> Zona intermédia removida (2026-05-13): os limiares DIFF 24-30h, LOG 1-2h e FULL 120-168h
> (antes classificados como DELAYED/WARNING) foram eliminados. Esses casos não aparecem
> em nenhum KPI card. Se necessário reintroduzir, requer alteração de helpers.py e
> intelligence_kpis.py em simultâneo.

**Orphan/offline DB exclusion (pós-refactor):**

O endpoint `/instances/backup-failed` e `collect_backup_status()` excluem bases de dados
sem par em `KPI_MSSQL_DB_AVAILABILITY_STG` (`av.Is_Available = 1`) via INNER JOIN.
Consequência: DBs orphan (dropped no servidor mas com linha residual em STG de backups)
ou DBs offline não geram falsos positivos no card Backup Failed.
Atenção: se o collector de DB_AVAILABILITY_STG tiver gap de colecção, DBs genuinamente
online podem ser excluídas transitoriamente — monitorizar `Update_TS` desta STG em paralelo.

**V3.3-specific notes**:
- `backup_analysis.py` has a 30-minute TTL cache (`_tdp_unavailable_cache`).
- TDP error logs processed via `_io_executor` (4 workers).
- Direct-msdb endpoints (`/queries/backup/*`) were never affected by the V1 24 h window bug; only the dashboard KPI path (via STG) was affected until V1 commit `0b2df9f`.
- FIND-20260506-001 V3.3 RESOLVED — that finding was about modal SQL Não Respondeu lookup (server-list), not backup-specific.

---

## V6 Banking GA

**Canonical path**: `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6\`

**Owner files**:
- `services/expert_agents/backup_expert.py` — Expert Swarm agent; 4 perspectives: `gap_analysis`, `rpo_compliance`, `performance_impact`, `recovery_readiness`
- `services/ai_assistant_service.py` — intent `"backup"` → `_evidence_backup()`; reads `KPI_MSSQL_BACKUPS_STG`

**Role**: consumer — reads `KPI_MSSQL_BACKUPS_STG` (V1 BLUE/GREEN swap; window widened 24 h→90 d via commit `0b2df9f`).

**Routes / endpoints**: consumed via `POST /api/ai-assistant/ask` (intent `backup`); surfaced in main SPA (port 8660).

**Expert Swarm cross-talks**:
- `disk_full` — backup failure attributed to disk exhaustion
- `alwayson_issue` — log backup in AG context; secondary replicas
- `tlog_growth` — missing log backup identified as root cause

**Compound evidence pattern (V6-exclusive)**:
- Backup gap + log backup issue together → emits `CRITICAL Evidence` (`source="ExpertSwarm:backup_expert"`, `confidence=0.95`). This composite pattern is absent in V3.3.

**V6-specific notes**:
- Schedule-based gap detection inherited from V3.3; V6 extends it with compound evidence and AG context cross-talk.
- PCI-DSS Req 9.5 compliance angle is a Sprint B documentation item; `backup_expert.py` does NOT yet emit compliance-tagged evidence.
- `audit_log_v6` integration: Sprint B pending (FIND-20260430-013).
- V1 commit `0b2df9f` (dormant-gap blindspot fix) resolved the upstream blindspot that affected V6 STG reads.

---

## Bugs históricos críticos cross-version

| Finding | Severity | Status | Versions affected | Description |
|---------|----------|--------|-------------------|-------------|
| V1 window 24h→90d (`0b2df9f`) | P1 | RESOLVED V1-side | V1 (fix), V3.3 STG path (was affected), V6 (was affected) | V1 msdb query window widened from 24 h to 90 d. Dormant DB gaps (no backup >24 h) were invisible before fix; now visible in STG. Breaking change: environments with long-dormant databases now see new gap rows surface immediately after V1 upgrade. Direct-msdb endpoints in V3.3 were unaffected throughout. |
| FIND-KPI-BACKUP-TEMPORAL (2026-05-11/2026-05-13) | P1 | RESOLVED 2026-05-13 | V3.3 STG path (dashboard KPI card) | Refactor temporal: semântica Failed/Delayed separada por tipo + janela 48h para LOG/DIFF. Fix isoformat: `execute_intelligence_query()` converte datetime→str ISO 8601; isinstance(x, datetime) downstream retornava False → failed_count=0 em produção ~48h. Fix: aceitar str ISO via `datetime.fromisoformat()`. Zona intermédia anterior removida. |

---

## Cross-references

- `cross_cutting/intelligence_db_schema.md` — `KPI_MSSQL_BACKUPS_STG` schema; BLUE/GREEN swap protocol
- `cross_cutting/shared_infra_db.md` — V1 write-authority rules
- `cross_cutting/tier_matrix.md` — tier and edition matrix
- `modules/collector_pipeline.md` — full pipeline architecture; BLUE/GREEN protocol
- `modules/alwayson.md` — log backup in AG context (cross-talk)
