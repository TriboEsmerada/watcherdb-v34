# Censo de Paridade Cartão↔Modal — Dashboard KPI V3.3 (2026-08-11)

Autor: watcherdb-frontend-specialist (dispatch pós-FIND-20260811-101/102).
Protocolo por par: mesma fonte? mesmo momento? mesmo método de Env? mesma janela
de frescura? **26 pares reais + 8 órfãos + 1 bug bónus.** Read-only — nada alterado.

Âncoras: cards Vista Avançada `templates/watcherdb_portal.html` (KPI_REPORT_GROUPS
34006-34028, _advCard/_advRow 34147-34164, renderKpiAdvanced 34294-34429);
KPI_METADATA 32438-33134; TOAST_CRITICAL_CHECKS 5943-6028; payload
`api/routers/intelligence/helpers.py` collect_* 601-2623 (cache TTL 60s :39-58 +
poll ~30s ⇒ card até ~90s atrás; modal é sempre live); drilldowns
`api/routers/intelligence_kpis.py` 1155-2449, FRESHNESS_WINDOWS 67-73.
DDL viva da GROUPED_VIEW: `database/FIX_SERVER_OFFLINE_VIEWS_LATEST_STATE.sql:144-201`
(janela real 15 min — o comentário "7 dias" em helpers.py:1153 está desactualizado).

## Achados de topo (por severidade)

1. **Card "Instancias c/ servicos em baixo" cablado à fonte ERRADA** (portal 34325):
   o card conta pela `KPI_MSSQL_SERVICE_STATUS_AGG_VIEW`, mas o clique abre
   kpiType `sql-services-down` que lê `KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW
   WHERE Diagnosis='sql_down'` — collector/tabela totalmente diferentes. O endpoint
   correcto (`service-status`, intelligence_kpis.py:1423) existe e nunca é chamado.
   Fix = 1 argumento no `_advRow`. → FIND-20260811-103
2. **Linha "Drives c/ latencia em aviso" abre a modal CRÍTICA** (portal 34379):
   kpiType `disk-latency-critical` em vez de `disk-latency-warning` (que existe,
   :2310). O DBA clica em "aviso" e vê 0 ou só críticos. → FIND-20260811-104
3. **Toast "Instancias Offline" parte ao clicar** (portal 5948): usa kpiType
   `instance-availability-off` que NÃO existe no backend → HTTP 400. É o toast
   mais urgente do produto. → FIND-20260811-105
4. **Padrão sistémico de frescura assimétrica (5 pares)**: disk-file-system
   crit/warn, transaction-logs-critical, tempdb crit/warn — o CARD não filtra
   frescura nenhuma, a MODAL filtra 24h (`FRESHNESS_WINDOWS['capacity']`).
   Se um collector parar, o card mantém o número velho indefinidamente e a modal
   esvazia — contradição garantida. Remédio único: `is_data_fresh(...)` nas 2
   funções `collect_disk_and_tlog` (helpers 759-801) e `collect_tempdb_status`
   (1970-2048). Beneficia 5 pares numa edição.
5. **integrity-p3 TOP 300** (intelligence_kpis 1886-1931): card conta total real
   (histórico: 1195 P3), modal trunca a 300 e o `count` devolvido é o truncado.
   Remédio: "300 de N" explícito ou subir cap.
6. **memory-critical**: card exclui `offline_hostnames`, modal não — conjuntos
   diferem quando há servidor em baixo (o pior momento). Copiar padrão de
   helpers 2175-2199 para o ramo modal 2215-2306.
7. **cpu-critical**: modal com `>= 95` hardcoded vs card via `_th()` — como
   `cpu_critical` é configurável F1, um override do cliente diverge o par.
   Mesmo fix-padrão do backup-delayed 2026-08-06 (`_thr()`).

## Resumo por classe (26 pares)

- FONTE-DIFERENTE: 3 (#3 services-down, #11 latency-aviso mal cablada, #5 memory)
- MESMA-FONTE-MOMENTO-DIFERENTE limpos: ~14 (always-on, mirroring, blocked-*,
  deadlocks, processes, backups, integrity-p1/p4/unm, filegroups, cpu borderline)
- MESMA-FONTE com assimetria de frescura/filtro (na prática divergem): ~8
  (#2 offline=FIND-101, disk crit/warn, tlog-crit, tempdb crit/warn, p3-TOP300)
- FONTE-DIFERENTE só na dimensão Env: 1 (#1 Instances OK = FIND-102)

## Recomendação de remédio para o FIND-101 (par Offline)

(iii) timestamp visível nos dois lados como 1ª camada (infra `stale`/`snapshot_at`
já existe, helpers 81-99) + (ii) card refetch ao abrir a modal como 2ª camada.
NÃO (i): a modal live é a feature certa num incidente — não sacrificar.

## Batches de correcção (mesma edição)

- B1 (routing, 2 linhas de template): FIND-103 + FIND-104.
- B2 (frescura simétrica, 2 funções): 5 pares disk/tlog/tempdb.
- B3 (Env por INST_ENVS no drilldown OK): FIND-102 (padrão helpers 1174-1188).
- B4 (exclusão offline na modal): memory-critical (+ disk-latency-critical, mesma classe).
- B5 (threshold via _thr no cpu-critical): padrão do fix backup-delayed 06/08.
- B6 (toast): kpiType válido no TOAST_CRITICAL_CHECKS[0] (FIND-105).
- FIND-101 (par Offline): decisão de UX (iii)+(ii) — consultar frontend specialist
  no diff.

## Órfãos (endpoint vivo sem clique, ou card sem endpoint)

- `jobs-failed`/`jobs-collisions`: grupo existe em KPI_REPORT_GROUPS mas
  renderKpiAdvanced nunca cria card Jobs; `transaction-logs-warning` sem _advRow.
- `db-availability`: só alcançável via toast desde a remoção do modo Simples
  (2026-06-17). `backup-jobs-disabled`, `backup-no-checksum` (removido 28/07,
  superfície alternativa não verificada), `lock-count`, `error-log` (dados
  coletados, nunca exibidos), `db_io_stats` (morto nas duas pontas).
- Card sem modal: "Backup danificado" (deliberado, falta endpoint is_damaged).

## Nota de higiene

Comentário em helpers.py:1153 diz que a GROUPED_VIEW filtra 7 dias; a DDL viva
filtra 15 minutos. Corrigir o comentário quando se tocar no ficheiro.
