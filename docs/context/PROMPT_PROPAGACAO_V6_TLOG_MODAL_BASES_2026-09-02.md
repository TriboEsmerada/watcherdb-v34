# Propagação V3.3 → V6: modal Transaction Logs por base (2026-09-02)

Para a AI do repositório V6. Não é só um diff: são as REGRAS e os CONTRATOS
que o V3.3 passou a garantir. O portal V6 é um subset (não superset) do V3.3 —
faz grep pelos anchors antes de assumir que o bloco existe.

## O que mudou no V3.3 (commit: ver `git log --oneline -3` no V3.3)

| Ficheiro | Mudança |
|---|---|
| `api/routers/intelligence/tlog_usage_classes.py` (NOVO) | `TLOG_BASE_QUERY` (1 linha por base, AG-aware, sem WHERE por threshold) + `classify_tlog()` (função pura) |
| `api/routers/intelligence/helpers.py::collect_disk_and_tlog` | tile lê `cls["per_instance"]` (forma legada) + `*_bases_count`, `*_bases_by_env`, `reconciliation` |
| `api/routers/intelligence_kpis.py` ramo `transaction-logs*` | payload por BASE: `-critical` → `cls["critical"]`, `-warning` → `cls["warning"]` |
| `api/kpi_thresholds_registry.py` `tlog_usage` | `surfaces`/`note` actualizados (classificação partilhada) |
| `templates/watcherdb_portal.html` | helpers `_isTlogModal`/`_isBaseListModal`; sort `Percent_Used DESC`; sumário em bases; 2.º chart "idade do último backup de log"; combobox; card por base; `data-bkptype` = `Log_Backup_Age` no TLOG; cross-filter + relabel de totais; drilldown pré-preenche `#log-space-filter`; metadata "?" PT/EN/ES; **ramo morto `kpiType === 'transaction-logs'` removido** |
| `static/i18n/{pt,en,es}.json` | `chart.tlog_by_log_backup_age` + 15 chaves `kpi_modal.*` (ver lista abaixo) |
| `tests/unit/test_tlog_usage_classes_20260902.py` (NOVO), `tests/unit/test_template_modal_escaping.py` | contrato + ajuste do threshold (4→2) |

## Regras (o que o V6 tem de respeitar, não só copiar)

1. **Uma classificação, dois consumidores.** Tile e modal chamam a MESMA
   função pura (`classify_tlog`). Thresholds do registry + overrides
   (`_th('tlog_usage', ...)`), frescura (1440 min) DENTRO da função.
   Nunca reclassificar em SQL numa view: a `KPI_MSSQL_TLOG_USAGE_AGG_VIEW` e a
   `DET_VIEW` classificam a 85/95 hardcoded e ignoram overrides — continuam a
   existir para o report Pro, mas NÃO alimentam o card/modal.
2. **Modal mostra NOMES, não números** (regra owner 2026-07-27). Cada card é
   uma base: `Database` à cabeça, instância em segundo plano. O tile continua a
   contar INSTÂNCIAS (label diz "Instâncias c/ t-log crítico" — decisão owner
   02/09); o cabeçalho do modal diz "M base(s) críticas em N instância(s)" e os
   totais dos charts contam bases. Os dois números reconciliam via
   `reconciliation.instances_critical == len({r.Instance for r in critical})`.
3. **Último backup de LOG é AG-aware.** O msdb é local a cada nó; o backup de
   log de uma base AG costuma correr no secundário; o collector de TLOG só
   escreve o nó onde a base está activa. Lookup: MAX(Last_Backup_Date) em
   QUALQUER nó do mesmo AG (via `KPI_MSSQL_ALWAYSON_STATUS_STG`), fallback ao
   próprio nó. JOIN directo por `Instance` a `KPI_MSSQL_BACKUPS_*` reintroduz o
   bug que a Wave M.2 corrigiu no Backup Delayed.
4. **Recovery model manda.** `Recovery_Model = 'SIMPLE'` → `Log_Backup_Age =
   SIMPLE` (neutro, NUNCA vermelho por "sem log backup"). `Recovery_Model`
   NULL e sem backup → `UNKNOWN` (neutro). Só FULL/BULK_LOGGED sem registo é
   `NEVER` (crítico). `LATE` usa o limiar do registry `backup_delay_log`
   (`warning`) — não criar constante nova (já havia 5 "verdades" de TLOG na
   base de código).
5. **NULL nunca vira 0.** `Hours_Since_Log_Backup` é derivado de `now -
   Last_Log_Backup_Date` em Python (o `Hours_Since_Backup` da STG vem
   congelado pelo collector); sem data = `None`. Relógio adiantado → 0.0.
6. **Payload por base NÃO leva `Critical`/`Warning`/`Total_Databases`** — o
   card genérico do portal infere o badge por esses campos e o
   `_kpiNoiseFields` esconde-os; por base, mostraria contagem em vez do nome.
7. **Sem tier creep.** Nada de shrink, "comando", previsão de crescimento ou
   `log_reuse_wait`/VLF/runway (esses vêm da Fase 2, collector V1, Wave
   própria com veto do v1-intel-specialist e canonical).

## Contratos

### `classify_tlog(rows, thresholds, now=None, fresh_minutes=1440, log_late_hours=None)` → dict
- `critical`, `warning`: listas de bases anotadas, ordenadas `Percent_Used DESC, Instance, Database`.
  Campos por base: `Instance, Database, Env (normalizado), Percent_Used, Used_MB,
  Current_MB, Max_Available_MB, Update_TS, Last_Check (=Update_TS),
  Recovery_Model, Last_Log_Backup_Date, Hours_Since_Log_Backup (float|None),
  Log_Backup_Age (NEVER|LATE|OK|SIMPLE|UNKNOWN), Severity (CRITICAL|WARNING),
  Instance_Severity, Base_Key ("INSTANCE|DATABASE" upper), Threshold_Warning,
  Threshold_Critical`.
- `per_instance`: forma LEGADA `{Instance, Env, Total_Databases, Critical,
  Warning, Normal, Last_Check=MAX(Update_TS)}` — igual à agregação SQL antiga.
- `bases_critical_count`, `bases_warning_count`, `bases_critical_by_env`,
  `bases_warning_by_env` (PRD/QLT/TST/Undefined), `reconciliation`
  `{rows_fresh, critical, warning, normal, instances_critical, instances_warning_only}`.
- Semântica estrita: `> crit` CRITICAL; `> warn and <= crit` WARNING.
- Frescura fail-open: linha SEM coluna `Update_TS` passa (mesmo critério do card).

### Dashboard `db_transaction_logs` (inalterado + novo)
Mantidos: `critical_count`, `warning_count` (instâncias), `critical_items_total`,
`warning_items_total`, `instances[]` (per_instance com problema), `critical_by_env`,
`warning_by_env`. Novos: `critical_bases_count`, `warning_bases_count`,
`critical_bases_by_env`, `warning_bases_by_env`, `reconciliation`.

### UI "modal lista por base" (padrão a replicar, gate por helper)
- `_isTlogModal(k)` = `k.startsWith('transaction-logs')`; `_isBaseListModal(k)` = 5 kpiTypes de backup ∪ TLOG.
- Gates tocados: combobox de instâncias, pós-render (`buildInstanceCombobox` +
  `applyAllBackupFiltersWithMultiselect`), sumário dinâmico, cross-filter
  (`_modalKpiType === 'backup-delayed' || _isTlogModal(...)`), relabel de totais.
- 2.º chart reutiliza o MECANISMO do chart de tipo (ids `typeChartContainer`,
  `.bkptype-bar-row`, `data-bkptype`, `filterByBackupType`, `typeChartTotalValue`)
  com tokens `NEVER/LATE/OK/SIMPLE/UNKNOWN`; cores só via `getSevTokens`
  (NEVER=CRITICAL, LATE=WARNING, OK=OK, SIMPLE=INFO, UNKNOWN=disabled).
  Semântica dupla de `data-bkptype` documentada; filtros são reset ao abrir modal.
- Card: `data-database`, `data-basekey` (= `Base_Key`), `data-instance-name`
  (instância, para combobox/motor). Drilldown `selectInstanceFromModal(inst,
  kpiType, database)` → SQL Diagnostics `log-space` + poll de `#log-space-filter`
  (até 20 s) para pré-preencher a base.
- Chaves i18n (PT/EN/ES, mesmas linhas): `chart.tlog_by_log_backup_age`,
  `kpi_modal.bases_in_instances` ("{bases} base(s) {sev} em {instances}
  instância(s)"), `total_bases_suffix`, `click_log_backup_age_filter`,
  `log_backup_age_never|late|ok|simple|unknown`, `log_used_pct`,
  `log_max_available`, `last_log_backup`, `no_log_backup_record`,
  `recovery_simple_na`, `recovery_model`, `open_log_space_db`.

## Não copiar
- O ramo morto `kpiType === 'transaction-logs'` (sub-fetch live a
  `/api/queries/log-space` por instância, thresholds 90/75/60 hardcoded, texto
  "Oracle"). Se o V6 o tiver, remover.
- Classificação na AGG_VIEW/DET_VIEW como fonte do card/modal.
- Rótulos PT hardcoded nos totais dos charts (usar `kpi_modal.total_bases_suffix`).

## Verificação no V6
1. `pytest tests/unit/test_tlog_usage_classes_*.py` (copiar o teste; contrato acima).
2. SELECT de controlo (sql_monitoring): `COUNT(DISTINCT Instance)` com
   `Percent_Used > crit` == tile; `COUNT(*)` == cabeçalho do modal.
3. Browser: modal crítico e aviso; clique ambiente → chart idade reconta e
   vice-versa; combobox; cabeçalho = Total(env) = Total(idade); expand;
   drilldown com base pré-filtrada; temas claro/escuro; 1366×768; regressão
   do modal backup-delayed (combobox/cross-filter/números iguais).

## Addendum 02/09 (tarde): drill-down "Diagnóstico de Transaction Log" por base

| Ficheiro | Mudança |
|---|---|
| `api/routers/queries/tlog_diagnosis.py` (NOVO) | `GET /api/queries/tlog-diagnosis/{server_id}?database=&snapshot_pct=&snapshot_ts=&snapshot_age=` — 9 blocos live + motor de regras + spec `diagnosis` (contrato do layout Diagnóstico, igual ao mirroring) |
| `api/routers/queries/__init__.py` | include do router |
| `api/connection_pool.py::execute_on_server`, `api/async_db.py::async_execute_on_server` | `timeout_s: int = 0` opcional (command timeout; reposto a 0 antes de devolver ao pool) |
| `api/kpi_thresholds_registry.py` | entrada documental `tlog_diagnosis` (configurable_f1 False) |
| `templates/watcherdb_portal.html` | casca `_tlogDiagModal`/`openTlogDiagnosis`/`_tlogDiagTechnicalHtml` + delegação `[data-tlog-diag-instance]`; o card por base do modal TLOG emite o hint com `data-tlog-diag-*` em vez do `selectInstanceFromModal` |
| `static/i18n/*.json` | bloco `diag.tlog` (34 chaves) antes de `diag.mirror` |
| `tests/unit/test_tlog_diagnosis_20260902.py` | 10 cenários com `async_execute_on_server` mockado |

Regras (além das 7 acima):
8. **Permissões reais do `sql_monitoring`** (VIEW SERVER STATE + VIEW ANY
   DEFINITION + VIEW DATABASE STATE + SELECT msdb): sem `DBCC LOGINFO`, `DBCC
   OPENTRAN`, `fn_trace_gettable` (ALTER TRACE). VLFs só via
   `sys.dm_db_log_stats`/`dm_db_log_info` (gate por `OBJECT_ID` no q0; em
   2012/2014 = nota "correr no SSMS"). `xp_readerrorlog` corre em ÚLTIMO com
   timeout próprio e degrada com nota (Msg 229 sem GRANT explícito).
9. **msdb**: filtrar SEMPRE por `backup_finish_date` (índice `backupsetDate`);
   `backup_start_date`/`database_name` não têm índice → scan de 1M linhas.
10. **`dm_exec_requests.database_id` é o CONTEXTO** da sessão: BACKUP/RESTORE
    correm de master/msdb → trazer todos e filtrar pelo texto do statement.
11. **9002 ocupa duas linhas** no errorlog: pesquisar pelo nome da base entre
    apóstrofes (`N'''db'''`), classificar em Python (`is full due to` / localizado).
12. **Mapeamento explícito `log_reuse_wait_desc` → recomendação** (tabela
    `_REASON_TEXT`): nunca uma recomendação genérica para causas diferentes.
13. **Runway declara a sua incerteza**: média 7d via msdb; quando < 6 de 7 dias
    têm backup de log, a evidência diz "estimativa pode estar subavaliada".
14. Textos analíticos (problems/recs) são PT no backend, como no mirroring;
    header/tiles/labels da casca vêm de `t()`.

Verificação no V6: `pytest tests/unit/test_tlog_diagnosis_*.py`; sonda viva num
PRD (q9 = 229 ou linhas) e numa instância 2012/2014 (fallback sem excepção).

Bug colateral descoberto e NÃO corrigido aqui (registar no V6 também):
`mirroring_diagnosis.py:75` `log_unlimited` só testa `max_size = -1`; um LOG
com `MAXSIZE UNLIMITED` fica gravado como 268435456 (2 TB) → o side row diz
"max_size definido". Correcção: `IN (-1, 268435456)` (já aplicada no q1 do TLOG).

## Fase 2 (fora deste handoff)
Collector V1 `collect_tlog_usage.py` + colunas STG/HIST (`Log_Reuse_Wait`,
`VLF_Count`, `Active_VLFs`, `Drive_Free_MB`, `Runway_Days`, `Motivos`) a partir
do pacote T-Log (01-Coletor.sql); canonical `INSTALACAO_COMPLETA_UNIFICADA.sql`
+ docs no mesmo bloco; veto `watcherdb-v1-intel-specialist`. Só então o modal
ganha "motivo de retenção" e "runway". `comando`/shrink ficam fora de Std.
