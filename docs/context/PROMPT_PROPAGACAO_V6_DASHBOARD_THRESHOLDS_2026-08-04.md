# PROMPT — Propagação V3.3 → V6 · Dashboard + Thresholds (04/08)

Para a sessão AI do V6. Origem: sessão V3.3 de 04/08 (branch
`wave-b-indexacao-dmv`, monorepo projetosPython). Regras:
`v33-v6-propagation-rule` e `v6-portal-not-superset` (**grep anchors no V6
primeiro** — portal V6 é subset).

**Há TRÊS lotes de 04/08 — não confundir:**
- `PROMPT_PROPAGACAO_V6_LOTE_2026-08-04.md` — migração do baseline (infra/BD).
- `PROMPT_PROPAGACAO_V6_THRESHOLDS_2026-08-04.md` — thresholds configuráveis (F1/F2/F3).
- **este** — 4 fixes de dashboard + índice.

Commits V3.3: `981daa3` `deeea61` `5330535` `d0a5d51` (dashboard);
`3cb0cb0` `3858b54` `faf3ab4` (thresholds).

---

## A. Fixes de dashboard — PROPAGAR (anchors confirmados no V6)

Grep no V6 (`templates/watcherdb_portal.html`) confirmou os 4 bugs:
`_kpiGroupCritEnv` existe mas `_kpiGroupWarnEnv` NÃO (33204); `envOrder =
[...].filter(e => envAgg[e])` (33165); `by_environment_t` = 'Por Ambiente'
sem "(Críticos)" (33260). Todos presentes.

### A.1 Avisos ignoram o filtro de ambiente (FIND-105 / `981daa3`)
`critOf` filtra por ambiente via `_kpiGroupCritEnv`, mas o warn usa
`_kpiGroupWarn` (sempre global) → ao filtrar um ambiente, os Avisos ficam
no total da frota.
- Criar `_kpiGroupWarnEnv(g, data)` (espelho de `_kpiGroupCritEnv` sobre
  `g.warn`).
- Nos sítios com `critOf` (≈2-3: `_repFilData`, `_repTopCards`), criar
  `warnOf` análogo e usar `warn: warnOf(g)`.

### A.2 Integridade sem dimensão de ambiente (opção A / `deeea61`)
Sem `p4_by_env`, a integridade contribui 0 sob filtro → "todos os
ambientes" ≠ "sem filtro" (diferença ≈ P4 CHECKDB>30d).
- Backend V6 (grep `collect_integrity`/`p1_by_env`): expor `p3_by_env` e
  `p4_by_env` (os rows já têm `Env` via JOIN INST_ENVS — só agregar
  `_count_by_env(p3_rows)`/`p4_rows`).
- Frontend: em `_kpiDefEnv`, caso especial pseudo-id `integrity-p4` →
  `data.integrity.p4_by_env` (não está em KPI_METADATA).

### A.3 "Por Ambiente" esconde ambientes sem críticos (opção A / `5330535`)
PRD/QLT/TST devem aparecer sempre (um ambiente "desaparecer" parece
avaria). Nos ~3 sítios de `envOrder`:
`.filter(e => (e==='PRD'||e==='QLT'||e==='TST') || envAgg[e])`.

### A.4 Rótulo "Por Ambiente" não diz que são críticos (`d0a5d51`)
O card mostra críticos mas o título não o diz (ao contrário de "Por
Categoria (Críticos)"). Locales `static/i18n/{pt,en,es}.json` chave
`by_environment_t` → "Por Ambiente (Críticos)" / "By Environment
(Critical)" / "Por Entorno (Críticos)" + fallback no template.

**Validação A:** filtrar um ambiente → os Avisos mudam; a integridade
entra no total; TST aparece a 0; o card diz "(Críticos)".

## B. Thresholds → doc dedicado

Ver `PROMPT_PROPAGACAO_V6_THRESHOLDS_2026-08-04.md`. Resumo: o V6 herda as
tabelas+dados (BD partilhada), replica a **F1** (registry +
`threshold_overrides.py` + router + `_th=resolve` + modal editável) e
constrói **F2** (UI scope + audit; precedência já no `resolve()`) e **F3**
(baseline sugere) como **Pro**. Tier owner: F1=Std, F2/F3=Pro. Golden
test: tabela vazia ⇒ byte-idêntico.

## C. Contexto sem fix de código (não propaga, mas saber)

**FIND-20260804-106 — disponibilidade pode mentir sob staleness.** A
coleta de availability corre pelo serviço `WatcherDBCollector` (cadência
2/3/5 min); quando emperra (processos Python presos), o card mostra 100%
do último valor sem sinalizar staleness. Infra partilhada — o V6 lê a
mesma `KPI_MSSQL_INST_AVAILABILITY_ACTIVE`. O card sinalizar staleness é
follow-up aberto (não feito). Se o V6 mostrar 100% com poucas instâncias
frescas, é staleness. Sub-achado: 4 servidores PRD bloqueiam 60s/ciclo
(`SQLIDSPRD03`, `SQLMDMPRD02`, `SQLHDSGENPRD02`, `OATXP01`).

## D. Findings do lote

`findings-inbox.md`: -101 (manual, fixed), -103 (drift tempdb view
70/85/95 vs backend 60/80 — **open**, decisão do owner pendente sobre qual
é a verdade; view partilhada → afecta V6), -104 (identidades, deferred),
-105 (avisos-by-env, fixed), -106 (disponibilidade stale, fixed).

## E. Validação V6

- Restart do serviço V6 (código Python cacheado).
- Bloco A: 4 fixes visíveis no browser.
- Bloco B: F1 editável; golden verde; F2/F3 gated a Pro.
- CHANGELOG V6 + FEATURE_MATRIX antes do commit.
