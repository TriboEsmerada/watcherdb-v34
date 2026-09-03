# DESIGN — Accordion de detalhe nos cards das modais KPI (todas)

**Data:** 2026-07-23 | **Estado:** APROVADO pelo owner ("aprovo a sua sugestão, e quero
dessa forma em todas as modais") | **Implementação:** próxima sessão, item #1 de UI.

## Decisão

Separar as duas ações que hoje estão coladas no card das modais de drill-down KPI:

1. **Clique no corpo do card** → EXPANDE detalhe in-place (accordion) dentro do próprio
   card. Segundo clique colapsa. NÃO abre modal-sobre-modal (anti-padrão: briga com
   maximize, ESC ambíguo, z-index, perde contexto da lista/filtros/gráficos).
2. **Clique no link "Clique para abrir..."** (`.kpi-drill-hint`) → única porta de
   navegação para a instância (comportamento actual do card inteiro passa só para o link;
   requer `event.stopPropagation()` no link OU mover o onclick do card para handler que
   distingue o alvo).

Vantagem-chave vs modal nova (proposta original do owner, melhorada em conversa):
expansão traz conteúdo NOVO (breakdown por drive/DB), não repete o card; permite expandir
2-3 cards e comparar; mantém filtros de ambiente/veredicto e gráficos visíveis.

## Âncoras técnicas (V3.3, 2026-07-23)

- Card: `templates/watcherdb_portal.html` ~36628 (`.instance-item`, onclick
  `selectInstanceFromModal` — hoje no card inteiro).
- Link: `.kpi-drill-hint` ~36658 (hoje sem onclick próprio).
- Motor de filtros: `applyAllBackupFiltersWithMultiselect()` (~40710 versão viva;
  `_applyAllBackupFilters_LEGacy_UNUSED` ~40474 é morta — NÃO editar essa).
  Accordion expandido deve colapsar-se (ou manter?) quando o filtro esconde o card.
- Renderer por KPI: switch `metricsHtml` em showProblematicInstances (~36400-36600).

## Endpoint de detalhe

Padrão: `GET /api/intelligence-kpis/instances/{kpi_type}/detail/{instance}` (novo, em
intelligence_kpis.py; identidade sql_monitoring SELECT-only; TOP N + ORDER BY severidade).
Lazy-load no primeiro expand (spinner no card), cache client-side por instância enquanto
a modal está aberta.

## Fontes de detalhe por KPI (rollout faseado)

| Fase | KPI modal | Detalhe no expand | Fonte |
|---|---|---|---|
| 1 | Disco (db-disk-*) | por drive: Free%, GB, classe (regra <30%), barra | KPI_MSSQL_DISK_USAGE (por Instance) |
| 1 | Integridade (integrity*) | por DB: Verdict, Last_CheckDB, porque-falhou (já existe no card 1-DB; expand útil qd agregado) | INTEGRITY_VERDICT_VIEW |
| 2 | Backups (failed/delayed/disabled/no-checksum) | por DB: último backup por tipo, gap | BACKUPS/BACKUP_EXEC_FAILURES |
| 2 | TLog | por DB: log used%, VLFs se disponível | TLOG_USAGE |
| 3 | Bloqueios/Deadlocks | cadeia head-blocker / últimos eventos | BLOCKED_SESSIONS/DEADLOCKS_HIST |
| 3 | Jobs | últimas execuções + mensagem de erro | JOB_DURATION/AGENT_JOBS |
| 3 | CPU/Memória/AlwaysOn/Mirroring/FG | métricas por objecto conforme fonte | respectivas STG/HIST |

Nota fase 1 Disco: NÃO recriar — a tab Disco já tem drilldown por ficheiro com sort+filtros
(diskDrillState/buildDiskDrillHtml); avaliar reutilizar o builder com container próprio.

## Restrições (gates antes de "shipped")

- i18n completo PT/EN/ES (zero hardcoded) — v33-i18n-coverage.
- Compatível com maximize das modais e com filtros combinados (env+verdict+instância).
- Browser test manual antes de declarar shipped (memória: incident onclick 2026-06-01).
- Tier check (v33-feature-matrix-checker): detalhe é dado bruto client-rendered ⇒ Std;
  qualquer heurística/score no expand → verificar fronteira.
- Propagação V6 (nota: portal V6 NÃO é superset — grep anchors V6 primeiro).
- Aria: card ganha `role="button" aria-expanded` no corpo; link mantém semântica própria.

## Fora de scope

- Modal-sobre-modal (rejeitado).
- Editar a função legacy de filtros.
- Detalhe server-side agregado com IA/score (Pro; não entra aqui).
