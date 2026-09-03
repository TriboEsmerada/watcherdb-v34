---
version: cross-cutting
component: shared
canonical_path: n/a
last_validated: 2026-05-20
owner_specialist: core-librarian
license: INTERNAL
references:
  - cross_cutting/intelligence_db_schema.md
  - modules/backups.md
  - v_specific/v6/banking_ga/compliance_extras.md
---

# KPI Category: Backup Status

<!-- LICENSE: INTERNAL -->

## Fase 2 Backup Failed (2026-08-21) — Resolved_By_Success_TS no collector

Council 21/08 + v1-intel GO-com-condicoes. Source 1 (sysjobhistory) grava
`Database=NULL` (falha job-level) — o check R+13 por-database nunca disparava e
a falha so' saia do KPI por idade (janela 7d), nunca por verificacao (job
quinzenal falhado desaparecia sem recuperar). Fase 1 (b13a7e2) verificava no
consumidor via `AGENT_JOBS_STG` (so' ULTIMO run). Fase 2 move a verificacao
para o collector V1: coluna `Resolved_By_Success_TS DATETIME2 NULL` preenchida
via OUTER APPLY (MIN do 1o sucesso `step_id=0`/`run_status=1` posterior a
falha; historico completo); janela Source 1 7d→30d (alinha is_damaged).
Consumidor V3.3 simplifica para `Resolved_By_Success_TS IS NULL` (fail-open
mantido). Migration: `MIGRATION_F2_RESOLVED_BY_SUCCESS_TS.sql` (V1). NOTA
semantica: padrao falha→sucesso→falha diverge da Fase 1 legitimamente (Fase 2
resolve a falha antiga; e' a semantica correcta). Escrita real do collector:
BLUE/GREEN full-swap por ciclo — NAO "append 14d/48h" (doc drift Wave D1
corrigido 21/08 na library central).

## Wave M (2026-05-20) — AG-aware consolidation, supersedes Wave J filter

**Problema detectado em produção 2026-05-20**: failover do AG `SQLMDMPRDAG03`
overnight provocou flaw arquitectural: `msdb` e' local a cada no AG (NAO
replicado). O novo primary tinha dados velhos no msdb local; o ex-primary
(agora secondary) tinha os backups frescos mas Wave J (2026-05-19) filtrava-os
do KPI. KPI dashboard mostrou 30 DBs como "Backup Delayed FULL 55d" — falsos
positivos por arquitectura.

**Solucao Wave M**: collector colecta backups de TODOS os nos AG (primary E
secondary). Nova VIEW `vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE` consolida via
`MAX(Last_Backup_Date)` por `(AgName, Database, Type)` usando
`KPI_MSSQL_ALWAYSON_STATUS_STG` como topology map. Standalone DBs passthrough.

### Schema delta

| Tabela | Mudanca |
|---|---|
| `KPI_MSSQL_BACKUPS_STG` (+ 8 fisicas BLUE/GREEN/PRD/QA/TST) | + `Ag_Role VARCHAR(16) NULL` (PRIMARY/SECONDARY/NULL) |
| `vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE` (NOVA) | View de consolidacao AG-aware com coluna `Source` (AG_CONSOLIDATED/STANDALONE) |

### Collector changes

| Ficheiro | Mudanca |
|---|---|
| `scripts/collectors/collect_backups.py` | Wave J filter REMOVIDO; coluna `Ag_Role` ADICIONADA via correlated subquery `sys.dm_hadr_database_replica_states + dm_hadr_availability_replica_states` |
| `scripts/collectors/collect_backup_failures.py` | Wave J filter REMOVIDO nas 2 UNION ALL (Sources 2+3); sem Ag_Role (failures sao eventos, nao state) |
| `watcherdb_intelligence/collectors/async_data_collector.py` | Idem `collect_backups.py` (parity rule FIND-20260507-001) |

### Consumer changes

V3.3 `api/routers/intelligence/helpers.py:1245` (Tile Backup Delayed):
- Antes: `FROM KPI_MSSQL_BACKUPS_STG` (per-instance, sofre flaw post-failover)
- Depois: `FROM vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE` (AG-consolidated)

Pro tiers (V5/V5.5/V6) podem optar entre VIEW (consolidacao) ou tabela base
(per-instance detail). Coluna `Ag_Role` em tabela base e `Source` em view sao
additive (NULL/STANDALONE por defeito), zero breaking change.

### Cross-tier impact

- V3.3: redirect aplicado. Wave J completamente substituida por Wave M.
- V5/V5.5/V6 Pro: tabela base inalterada (so additive). VIEW disponivel opt-in.
- BLUE/GREEN swap: inalterado (Ag_Role e column add, swap via TRUNCATE+INSERT).

### Limitacoes conhecidas

- `Backup_Duration_Sec` e NULL no path AG_CONSOLIDATED (MAX agregaria sem
  significado). Pro tiers que precisam de duration por backup individual devem
  consumir tabela base.
- Coluna `Ag_Role` populada na proxima ciclo do collector (~15min apos deploy).
  Backfill nao necessario.

### Wave J status

Wave J (2026-05-19) **DEPRECATED por Wave M**. Filtro `NOT IN ... SECONDARY`
era correcto para evitar false positives pre-failover mas criava blind spot
pos-failover. Substituida por Wave M arquitectural fix. Codigo legacy do
filter foi removido de todos os collectors em 2026-05-20.

---

## Wave D (2026-05-14) — 3-tile semantic split — supersedes Wave A5

**Decisao DBA Lead 2026-05-13**: A semantica Wave A5 (gap-based "Failed=DIFF/LOG,
Delayed=FULL") era conceptualmente incorrecta -- misturava 2 conceitos diferentes.
Edge case que motivou: job de backup posto disabled e esquecido NAO gera failure
em sysjobhistory mas gera gap RPO. Wave D separa em 3 tiles distintos.

| Tile | Source | Semantic | Order |
|---|---|---|---|
| **Backup Failed** | `KPI_MSSQL_BACKUP_EXEC_FAILURES_STG` | Execution failures REAIS: sysjobhistory.run_status IN (0,2,3) + backupset.is_damaged=1 + has_backup_checksum=0 | 1 |
| **Backup Delayed** | `KPI_MSSQL_BACKUPS_STG` (Hours_Since_Backup) | Gap RPO com severity warning/critical per tipo, janela 48h | 2 |
| **Backup Jobs Disabled** (NOVO) | `KPI_MSSQL_BACKUP_JOBS_DISABLED_STG` | SQL Agent backup jobs enabled=0 -- causa raiz comum de gap RPO | 3 |

### Threshold matrix Wave D (Delayed tile)

| Tipo | warning_h | critical_h |
|---|---|---|
| FULL | 120 | 168 |
| DIFF | 24 | 30 |
| LOG | 1 | 2 |

Janela 48h sobre `Update_TS` (frescura collector). `Delayed_Severity` per row =
`'warning'` ou `'critical'` para frontend filter/coloring.

### Agregacao de criticos no dashboard (2026-08-06, tile sincronizado 2026-08-31)

A categoria **Backups** do Resumo Executivo / Por Categoria (JS
`KPI_REPORT_GROUPS`, portal `~:34757`) soma:

    criticos = failed_count (FULL+DIFF+OTHER) + log_failed_count
             + delayed_critical_count          <- gap RPO acima de critical_h
    avisos   = delayed_warning_count

Desde 2026-08-31 o tile Backups expoe o mesmo split em rows proprias — "Em
atraso (critico)" a vermelho e "Em atraso (aviso)" a amarelo (antes: um total
unico amarelo, e com filtro CRITICOS o tile mostrava so "Log falhou" enquanto
o painel dizia 365 — incoerencia diagnosticada no screenshot do owner 31/08).
Ambas as rows abrem a mesma modal `backup-delayed` (sem filtro de severidade;
os pseudo-ids `backup-delayed-critical/-warning` existem so para a aritmetica
do painel). Granularidade de delayed_critical = (Instance, Database, TIPO) —
uma base com FULL+DIFF+LOG parados conta 3; revisao de dedupe e' decisao de
semantica executiva em aberto (FIND, sessao propria).
`no_checksum`/`is_damaged` NAO entram nesta soma (fora do grupo desde
2026-07-28; estado de configuracao, nao evento).

### Commits cross-tier

- V1 DDL: `fa653dd` (feat/v1-wave-D) -- 2 tabelas novas BLUE/GREEN (EXEC_FAILURES) + snapshot (JOBS_DISABLED)
- V1 collectors: `599ddd7` (feat/v1-wave-D) -- 4 collectors Python (sync + async para cada)
- V3.3 backend: `4905076` (feat/v3.3-wave-D) -- `helpers.py:collect_backup_status()` em 3 try/except + `intelligence_kpis.py` em 3 elif branches
- V3.3 frontend: `efb2511` (feat/v3.3-wave-D) -- tile config + KPI_METADATA + i18n + maps
- V6 backend: `d47924c` (feat/v6-wave-D) -- monolitico, mesmo refactor inline
- V6 frontend: `6d09648` (feat/v6-wave-D) -- mirror D5 minus B1 UX (paused)

### Retrocompat

Campos legacy `failed_count`, `delayed_count`, `instances` (failed + delayed
agregados) mantidos. `failed_by_type` derivado de `failed_by_source` para
preservar shape Wave A5 frontend nao migrado.

---

## Wave A5 (2026-05-13) — semantica deprecated (mantida abaixo para referencia historica)

Backup KPIs detect gaps in the FULL / DIFF / LOG backup chain using a
schedule-based gap detection approach (not fixed hour windows). V1 collects via
`msdb.dbo.backupset` into BLUE/GREEN STG tables with a 90-day lookback window
(widened from 24 h in commit `0b2df9f`). V3.3 has a dual-path architecture:
dashboard cards read STG, while the Backup Analysis module queries msdb directly.
V6 extends with RPO compliance scoring and PCI-DSS angle.

## Tabela comparativa tri-coluna

| KPI / Card | Query origem (V1 collector) | V3.3 display rule | V6 display + AI extension | Threshold | Bugs históricos |
|---|---|---|---|---|---|
| **Backup Status Card** | `KPI_MSSQL_BACKUPS_STG` — `msdb.dbo.backupset` 90-day window; BLUE/GREEN swap; 15 min PRD cadence. `KPI_MSSQL_BACKUP_STATUS_STG` (derived status per DB — FULL/DIFF/LOG last timestamps) | Dashboard card reads `KPI_MSSQL_BACKUPS_STG` directly via `api/routers/intelligence_kpis.py`; shows per-DB backup status badge; schedule-based gap detection (docs: `BACKUP_SCHEDULE_BASED_GAP_DETECTION.md`) | BackupExpert gap_analysis perspective: classifies each DB as COMPLIANT / AT_RISK / GAP based on backup chain completeness; flags dormant DBs (no backup ever or > 90 days) | **FAILED**: DIFF > 30 h (janela 48 h Update_TS); LOG > 2 h (janela 48 h Update_TS). **DELAYED**: FULL > 168 h (7 d) — sem janela temporal. Zona intermédia ELIMINADA (DIFF 24-30 h, LOG 1-2 h, FULL 120-168 h — não aparecem em nenhum card). Orphan/offline exclude via INNER JOIN DB_AVAILABILITY_STG. | V1 commit `0b2df9f` P1 RESOLVED (24 h→90 d window). FIND-KPI-BACKUP-TEMPORAL P1 RESOLVED 2026-05-13 (isoformat bug + zona intermédia + ORPHAN exclude). |
| **FULL Backup Analysis** | Same STG (90-day window enables full gap exposure) | `/api/queries/backup-full/{server_id}?days=N` — `modules/monitoring/backup_analysis.py` version `2026-01-16_PARAMS_FIX_V2`; queries `msdb.dbo.backupset` directly (bypass STG for analysis module); TTL cache `_tdp_unavailable_cache` 30 min | BackupExpert gap_analysis; cross-talks disk_full (insufficient space for backup) and alwayson_issue (replica backup redirect) | FULL gap > 168 h → CRITICAL; > 120 h → WARNING | — |
| **DIFF Backup Analysis** | Same STG | `/api/queries/backup-diff/{server_id}?days=N` — same `backup_analysis.py` module | BackupExpert gap_analysis; cross-talks tlog_growth (no DIFF → LOG chain growing) | DIFF gap > 30 h → CRITICAL; > 24 h → WARNING | — |
| **LOG Backup Analysis** | Same STG; LOG backup presence indicates FULL recovery model | `/api/queries/backup-log/{server_id}?days=N` — filters SIMPLE recovery model DBs automatically (SIMPLE LOG backups are expected absent — not a gap); endpoint key in commit `da8fb4a` (SIMPLE recovery LOG exclusion) | BackupExpert rpo_compliance perspective: calculates effective RPO from LOG chain frequency; composite CRITICAL pattern: backup gap + log backup issue = confidence 0.95 | LOG gap > 2 h → CRITICAL; > 1 h → WARNING; SIMPLE recovery exclusion: not flagged | — |
| **Backup Summary / Statistics** | `KPI_MSSQL_BACKUP_STATUS_STG` (derived aggregate) | `/api/queries/backup-summary/{server_id}` and `/api/queries/backup-statistics/{server_id}` — aggregates size, duration, success rate | BackupExpert performance_impact perspective: large backup windows overlapping with peak hours → resource contention; cross-talks cpu_high and disk_io | — | — |
| **Recovery Readiness** | Not a V1 KPI — derived in upper layers | Not a standalone V3.3 card — implicit in gap detection status | BackupExpert recovery_readiness perspective: estimates restore time from chain (FULL size + DIFF + LOG count); PCI-DSS Req 9.5 compliance angle (Sprint B deferred item in `banking_ga_polish.md`) | recovery_readiness < threshold → WARNING (V6 Pro-only) | — |

## Notes V1 → V3.3 → V6 evolution

- V3.3 dual-path is by design: the **dashboard card** needs low-latency reads from STG (pre-aggregated, BLUE/GREEN), while the **Backup Analysis module** needs the full msdb history that STG may not fully represent (edge cases: very large msdb, replication, AG backup redirect).
- The 90-day window expansion (commit `0b2df9f`) was a P1 fix: 24-hour window produced false "no backup gap" for databases that had been restored and never backed up again (dormant DBs).
- `_tdp_unavailable_cache` (TTL 30 min) in `backup_analysis.py` prevents repeated failed connection attempts to unavailable servers from flooding the connection pool.
- SIMPLE recovery model LOG exclusion (commit `da8fb4a`): the modal backup filter was incorrectly flagging SIMPLE recovery DBs for missing LOG backups. Fixed by checking recovery model before evaluating LOG chain.
- V6 BackupExpert composite CRITICAL pattern (backup gap + log issue = confidence 0.95) is the highest-confidence pre-defined pattern in the Expert Swarm for storage domain.
- PCI-DSS Req 9.5 compliance angle is a Sprint B deferred item for V6 Banking GA — not present in V3.3.

## Campos Update_TS vs Hours_Since_Backup — distinção crítica

| Campo | Origem | Semântica |
|-------|--------|-----------|
| `Update_TS` | Collector V1 — timestamp em que o collector escreveu a row na STG | Usado como proxy de frescor do collector. Se `Update_TS < NOW - 48h`, a row é ignorada para cálculo de FAILED (DIFF/LOG). Não reflecte quando o backup ocorreu. |
| `Hours_Since_Backup` | `DATEDIFF(HOUR, last_backup_finish_date, GETDATE())` calculado pela query msdb do V1 | Reflecte a idade real do último backup. Usado como valor de threshold. |

**Gotcha**: se o collector V1 ficar parado >48h, todas as rows de DIFF/LOG saem da janela de
frescor e `failed_count` cai para 0 silenciosamente. Isso é comportamento intencional (evitar
alarmes falsos por dados stale), mas pode mascarar falhas reais se o collector estiver down.
Monitorizar uptime do collector V1 é prerequisito para confiar no card Backup Failed.

## Scope: gap-based detection vs execution-failure detection

**O que o card Backup Failed FAZ**: mede idade do último backup conhecido
(`backup_finish_date` em `msdb.dbo.backupset`) — uma forma de RPO gap detection.

**O que o card NÃO FAZ** (limitações documentadas):

| Cenário | Detectado pelo card actual? | Onde detectar |
|---------|---------------------------|---------------|
| SQL Agent job de backup falhou (`sysjobhistory.run_status=0`) | ⚠️ Indirectamente — só após threshold (30h DIFF / 2h LOG) | `msdb.dbo.sysjobhistory` + `sysjobs` directly |
| TDP/TSM run-time failure | ⚠️ Idem — TDP não regista em `backupset` em caso de falha | Consola TDP / IBM Spectrum Protect |
| Commvault/NetBackup/Veeam run-time failure | ⚠️ Idem | Consola própria da tool |
| Backup completou mas ficou damaged (`is_damaged=1`) | ❌ Não — `backupset` regista como completed | Query directa em `backupset.is_damaged` |
| Backup sem checksum (silent corruption risk) | ❌ Não | Query directa em `backupset.has_backup_checksum=0` |
| Backup com size anómalo (ex: ratio 10× off) | ❌ Não | Heurística sobre `compressed_backup_size` histórico |
| `msdb.dbo.backuperror` entries | ❌ Não | Query directa nessa tabela |

### Janela de detecção típica para falha de execução

Cenário: TDP corre todos os dias às 02:00. No Dia N falha (rede/espaço/credencial).
- Dia N 02:00 — TDP falha. `backupset` NÃO recebe linha nova. `Hours_Since_Backup`
  para o último backup (Dia N-1) começa a contar.
- Dia N 10:00 — `Hours_Since_Backup ≈ 8h` para DIFF, `≈ 32h` para FULL (se FULL).
  Para DIFF, o card mostra OK ainda (threshold 30h).
- Dia N 14:00 — `Hours_Since_Backup ≈ 12h` (DIFF) → ainda OK.
- Dia N+1 08:00 — `Hours_Since_Backup ≈ 30h+` (DIFF) → AGORA aparece em Failed.

**Latência típica de detecção em modo gap-based**: ~30h após horário expected
do backup (DIFF) ou ~2h (LOG). FULL detecta após 7d (~168h).

### Por que aceitamos esta limitação em V3.3 Std

- **Schedule-agnostic**: funciona para qualquer tool (SQL Agent, TDP, TSM,
  Commvault, NetBackup, Veeam, scripts custom) sem integração específica.
- **Threshold é margin sobre cadência típica** (LOG 2h vs 15-30min cadência; DIFF
  30h vs 24h cadência) — não detecta na hora, mas detecta antes de RPO crítico.
- **FEATURE_MATRIX.md:70** define como "schedule-based gap detection" — alinhado.

### Roadmap V6 Pro / banking GA

Para clientes banking com TDP/TSM e auditoria SOX/HIPAA/ISO 27001, V6 deveria
adicionar:

1. **`is_damaged` detection** — query `msdb.dbo.backupset WHERE is_damaged=1` no
   collector V1 → card novo "Damaged Backups" (Std-eligible)
2. **`has_backup_checksum=0` detection** — silent corruption risk (Std-eligible)
3. **SQL Agent job failure cross-check** — `sysjobhistory.run_status=0` para jobs
   com pattern `%backup%` ou via job category. Cobre instalações sem TDP.
4. **`msdb.dbo.backuperror` integration** — errors during backup operation (mesmo
   se eventualmente bem sucedido em retry).
5. **Schedule-expected window** — overlay de calendário expected por DB
   (`expected_full_cadence_hours`, `expected_diff_cadence_hours`, etc.) para
   detecção early antes do threshold absoluto.
6. **TDP/TSM API integration** (Pro+ tier) — query directa à consola da tool
   para detecção em tempo real.

Estas evoluções ficam fora de scope V3.3 Std.

## Implicação banking/healthcare — invisibilidade silenciosa

O bug `FIND-20260513-101` (isoformat datetime) causou `failed_count = 0` durante ~48h em
ambientes PRD banking/healthcare com 25-400 falhas reais de backup activas. Em contexto
regulado (SOX, HIPAA, ISO 27001), um card KPI a 0 quando deveria ser >0 é equivalente a um
falso negativo num controlo de segurança.

**Implicações operacionais:**
- DBAs podem dispensar monitorização manual de backup assumindo que o card KPI é fiável.
- Auditorias de conformidade que usem screenshots do dashboard como evidência capturarão o
  valor incorrecto.
- O comportamento é silencioso — sem erro visível, sem log WARNING no dashboard.

**Mitigação recomendada (pós-fix):** validar periodicamente que `failed_count` no endpoint
`/api/v1/instances/backup-failed` é consistente com uma query directa a `KPI_MSSQL_BACKUPS_STG`
com os mesmos thresholds. Golden set sugerido: 1 DB com DIFF intencional >30h em TST.

## Cross-references

- `cross_cutting/intelligence_db_schema.md` — `KPI_MSSQL_BACKUPS_STG` BLUE/GREEN schema + `execute_intelligence_query` datetime→isoformat gotcha
- `modules/backups.md` — full cross-version module reference
- `v_specific/v6/banking_ga/compliance_extras.md` — PCI-DSS Req 9.5 (Sprint B)
- `v_specific/v3_3/feature_matrix_std.md` — Backup Analysis is Std; Recovery Readiness AI scoring is Pro-only
- `docs/features/BACKUP_SCHEDULE_BASED_GAP_DETECTION.md` (V3.3 local) — schedule-based gap logic
