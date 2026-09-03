# Propagacao V6 — Modais Diff/Log Failed: toggle de recuperadas + terminologia + painel Tipo (2026-09-02)

Para a AI do V6. Contexto explicado (regras + contratos), nao so diff. Origem: V3.3
branch wave-b-indexacao-dmv, 02/09 (owner: "paineis mostram 21, tile mostra 1 — ta estranho").

## AVISO PREVIO (nao assumir paridade)
O portal V6 NAO e' superset do V3.3 (memoria feedback_v6_portal_not_superset). ANTES de
aplicar qualquer coisa, grep no portal V6 por estes anchors:
- `isRecoverySplitModal` / `still_missing` / `kpi_modal.recovered_count` / `_kpiBackupRecoveredHtml`
- Se ZERO hits: o V6 nao tem a Fase 1/2 de recuperacao de 21/08 nas modais — aplicar
  primeiro PROMPT_PROPAGACAO_V6_BACKUP_RECUPERADO_2026-08-21.md, depois este.
- Se ha' hits: aplicar as 4 mudancas abaixo.

## Decisoes do owner (contratos, validos tambem para V6)
1. **Default = so' nao-recuperadas.** Tile, lista da modal e paineis contam o MESMO
   numero (falhas com Resolved_By_Success_TS NULL). Recuperadas nunca desaparecem em
   silencio (principio council 21/08 mantido): chip "mostrar N recuperada(s)" no header
   da modal revela-as com o selo verde; "ocultar N recuperada(s)" volta a esconder.
   Reset do toggle ao abrir cada modal.
2. **Terminologia**: "ainda em falta" e' ERRADO para falhas de backup (confunde com
   backup em atraso/ausente). Termo canonico: "NAO RECUPERADA" (selo) / "nao
   recuperada(s)" (contagens). EN: NOT RECOVERED / not recovered. ES: NO RECUPERADA /
   no recuperada(s).
3. **Painel "Backups por Tipo" nao existe** nas modais backup-failed (pre-filtrada
   DIFF) e backup-log-failed (so' LOG): barra unica e' ruido, o tipo ja' esta no nome
   do KPI. Painel de Ambiente ocupa o espaco (no V3.3 o layout condicional resolveu
   sozinho; verificar o equivalente V6).
4. **Regra "numeros nao se contradizem" (owner 27/07)**: qualquer total de painel tem
   de bater com o header da mesma modal na mesma unidade, ou dizer explicitamente que
   unidade soma.

## Implementacao V3.3 (referencia, adaptar aos anchors V6)
Tudo client-side — ZERO mudanca de backend (endpoint continua a devolver Recovered=0/1
por linha; e' isso que permite o chip sem re-query).
- Estado: `window._showRecoveredRows=false` + `toggleRecoveredRows()` (re-corre o motor
  de filtros); reset ao abrir modal junto dos outros filtros.
- Motor de filtros (applyAllBackupFiltersWithMultiselect no V3.3):
  `recoveredMatch = !isRecoverySplitModal || _showRecoveredRows || dataset.recovered!=='1'`.
  ARMADILHA: contar o split visibleOpen/visibleRecovered com base em
  `otherFiltersMatch` (todos os filtros MENOS o toggle) — se contar so' nas linhas
  visiveis, o chip nunca sabe quantas recuperadas ha' com o toggle fechado.
- Barras do painel Ambiente: no V3.3 eram ESTATICAS nestas modais (somavam sempre o
  render inicial, com recuperadas) — recontadas de `_envBarCounts` (padrao
  cross-filter: todos os filtros excepto o proprio env; respeita o toggle). Sem isto
  cria-se um novo "21 vs 12" bars-vs-total.
- Chip no summary do header: `Total: <nOpen> nao recuperada(s) · mostrar/ocultar <nRec>
  recuperada(s)` — onclick simples sem argumentos (sem hazard de quoting).
- Tooltip "?" (BACKUP_KPI_INFO) actualizado nas 2 entradas (PT hardcoded; debt i18n
  pre-existente, nao resolvida aqui).

## i18n (3 locales obrigatorios)
Renomeadas: `kpi_modal.still_missing` -> `not_recovered`; `still_missing_count` ->
`not_recovered_count`. Novas (interpolacao {n}): `show_recovered_toggle`,
`hide_recovered_toggle`. Mantida: `recovered_count` (orfa no V3.3 apos a mudanca — nao
apagada por precaucao). Valores exactos em static/i18n/{pt,en,es}.json:869-874 do V3.3.

## Validacao (mesma bateria do V3.3)
- Modal Diff Failed: lista+painel Ambiente = numero do tile; chip revela recuperadas e
  bars/Total acompanham; painel Tipo ausente. Idem Log Failed.
- Toggle reseta ao reabrir a modal; filtros env/instancia recontam com toggle ON e OFF.
- Regressao: modais delayed/tlog/integrity intactas (ramos else-if mutuamente exclusivos).
- Browser test do clique do chip (regra 2026-06-01 event handlers pre-ship).
