# PROPAGAÇÃO V6 — lote 17/08/2026 (2): layout "Diagnóstico" + análise do plano de execução

> Para a AI do V6. Regras + contratos explicados. Origem: V3.3, plano
> `docs/context/PLANO_DIAGNOSTICO_LAYOUT_2026-08-17.md`. **Portal V6 não é superset — grep das
> âncoras antes.** BD partilhada: **zero DDL**.

## 1. Módulo Performance partilhado (`modules/performance/`) — ATENÇÃO, é código partilhado com V5/V6

- `base.py`: `Recommendation` ganha `effort: str = ''` ('low'|'medium'|'high'; mapa fixo por tipo) e `problem_ids: List[str]`; novo `DetectedProblem` (id, title_pt, evidence_pt, impact_pt, severity, source dmv|plan_estimated|plan_actual|history, confidence measured|heuristic, icon, object_name, recommendation_ids); `InvestigationResult.problems: List[DetectedProblem]` (vazio = portal sintetiza a partir de `root_cause_pt`+baselines; nunca inventa). Tudo com defaults → backward-compatible.
- 8 investigators passam `effort=` em cada `Recommendation(`.
- `heavy_queries.py`: projecta `query_plan_hash, plan_handle, sql_handle, statement_start_offset, statement_end_offset`; `total_grant_kb` com **gate SQL 2014** (`PARSENAME(ProductVersion,4) < 13` → `CAST(0 AS BIGINT)`; antes a query inteira rebentava em 2014 e o investigator ficava vazio em silêncio). `slow_queries.py`: + `query_plan_hash`, offsets.
- Novo `plan_analyzer.py` (puro Python; ver §3).

Se o V6 tem cópia própria destes ficheiros → aplicar o mesmo diff. Se importa os do V3.3 → herda.

## 2. Componente `renderDiagnosisLayout(spec, idPrefix)` (portal)

Nomes de bloco fixos: **O que se passa** (veredicto + stat-cards) → **Porquê** (problemas: evidência, origem, frescura, chip "heurística") → **O que fazer** (ordenado impacto desc/esforço asc; badges Impacto colorido ▲, Esforço neutro ●; botão Copiar T-SQL) → **Evidência técnica** (colapsado) → **Dados brutos** (colapsado). Cor só por severidade (`--sev-*`), CSS `.diag-*` no `<style nonce>` existente, função no `<script nonce>` existente logo após `getSevTokens` (não criar blocos novos — CSP). Interacção por delegação (data-attributes; sem onclick com JSON): clique num problema filtra recomendações (`aria-pressed`, chip "Filtro: … ×", Esc limpa), "Ver mais", copiar (`diagCopyText`, clipboard + fallback textarea para HTTP LAN). Contrato em `PLANO_DIAGNOSTICO_LAYOUT_2026-08-17.md §2`. i18n `diag.*` (116 chaves ×3 locales, PT pós-AO90).

## 3. Pilotos

- **Performance**: `perfRenderResult(r)` = botão "Copiar para ticket" + banner correlação + `renderDiagnosisLayout(perfBuildDiagnosisSpec(r))` + runbook. **L1–L5 saem do ecrã** (nomes acima). `perfShowInvestigationModal`: `.inv-modal` com `role="dialog" aria-modal="true" aria-labelledby="inv-title"`. Tabelas de evidência com coluna `query_hash` ganham botão **Plano** (`data-perf-plan-tid/row`) → `openDiagnoseQueryModalWithCtx(instance, ctx)`; `window._perfCurrentInstance` guardado em `perfOpenInvestigation`.
- **SQL Diag** (`renderDiagnoseResults`): o render legado passa a "Evidência técnica"; `_diagnoseBuildLayoutHtml(data, legacyHtml)` constrói o spec (estatísticas/missing indexes/HEAP/diagnosis[] → problemas e acções; comandos SEMPRE comentados via `_diagnoseCommentSql`). Modal: `role=dialog`; novo `<details id="diagnosePlanDetails">` com `textarea#diagnosePlanXml`; `openDiagnoseQueryModal(serverId, ctx)` retro-compatível; `executeDiagnoseQuery` chama em paralelo `POST /api/queries/plan-analysis/{server}` quando há XML colado ou `ctx.query_hash`, e junta `data.plan_analysis` ao spec.
- **Jobs**: conteúdo da secção "Recomendações" = layout com problemas/acções derivados de `maintenance_recommendations` (legado em Evidência técnica). Backup/Space/Disk/AlwaysOn: **não** (decisão DBA persona).

## 4. Análise do plano — backend

- `modules/performance/plan_analyzer.py`: `parse_plan_xml` (namespace `.../2004/07/showplan`; rejeita `<!DOCTYPE`/`<!ENTITY`; cap 5 MB / 20k nós / 2k RelOps; devolve `ParsedPlan`), `build_findings` (regras → summary/problems/recommendations/side_rows; determinístico vs `confidence:'heuristic'`; DDL só comentado), `analyze_plan_xml`.
- `api/routers/queries/plan_analysis.py`: `POST /api/queries/plan-analysis/{server_id}` body `{query_hash?, plan_handle?, statement_start_offset?, statement_end_offset?, database_name?, plan_xml?, include_xml, include_qs}` (hex validado; identificadores validados). Passos: A) planos por `query_hash` (`dm_exec_query_stats` agrupado por `query_plan_hash`; veredicto honesto; robustez min/max); B) Query Store 2016+ (gate por versão; `HAS_DBACCESS`; READ_ONLY; forced plans; regressão 30d); C) XML statement-level (`dm_exec_text_query_plan(plan_handle, so, eo)`, cap server-side); D) missing index do plano × DMV. Nunca `CROSS APPLY dm_exec_query_plan` sobre a DMV inteira. Registado em `api/routers/queries/__init__.py`.
- Regra de produto: **"é o melhor plano?" só vs planos observados**; texto diz sempre a base ("N planos", "1 plano", "QS off", "não está em cache"). Sem comparação cross-instância (Pro).

## 5. Verificar no V6 antes

```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6"
Select-String -Path templates\*.html -Pattern 'function perfRenderResult|function renderDiagnoseResults|function getSevTokens|inv-modal-overlay|diagnoseQueryModal' | Select-Object Path,LineNumber,Line
Get-ChildItem -Recurse -Filter plan_analyzer.py; Get-ChildItem -Recurse -Filter base.py | Where-Object FullName -like '*performance*'
Select-String -Path api\routers\queries\__init__.py -Pattern 'tempdb_router'
```

## 6. Testes

`tests/unit/test_diagnosis_layout_wave_20260817.py` (12): parser (factos, findings, guardas, cap), endpoint offline + validações, `_verdict_from_cache` (textos), base.py, investigators com effort, âncoras do portal (incl. role=dialog, sem L1–L5, todos os `<script>` inline com nonce), i18n diag.* ×3.

## 7. Drill-down de Mirroring (acrescento 17/08, tarde)

Owner: o card do KPI "Mirroring nao saudavel" saltava para a aba AlwaysOn; agora abre um drill-down no layout Diagnostico.
- Backend novo `api/routers/queries/mirroring_diagnosis.py`: `GET /api/queries/mirroring-diagnosis/{server_id}?database=&partner=`. No PRINCIPAL: `sys.database_mirroring`+`sys.databases` (estado, role, safety, witness, `log_reuse_wait_desc`, tamanho do log), `DBCC SQLPERF(LOGSPACE)`, contadores Database Mirroring (send/redo queue), `xp_readerrorlog` 'mirror'/'suspend' (degrada com nota se sem permissao), auto page repair. No MIRROR (partner_instance -> server_id underscore): estado visto de la, errorlog, volumes da DB (`dm_os_volume_stats`). Regras: log do principal a nao truncar (DATABASE_MIRRORING) = incendio real; causa no mirror (1453/823/824/9002/suspend, disco baixo); RESUME comentado; rebuild comentado se re-suspender; nota de legado (mirroring deprecated). Cada bloco falha isoladamente (nunca 500 por um bloco). Registado em `queries/__init__.py`.
- Portal: no branch `kpiType === 'mirroring'` do modal do KPI, o link "abrir no SQL Diagnostics" passou a `data-mirror-diag-*` -> `openMirroringDiagnosis(principal, db, partner)`; modal singleton `#mirror-diag-overlay` (classes `.inv-modal*`, z-index 100001, role=dialog, refresh/close/Esc, cache 60 s) que renderiza `renderDiagnosisLayout(spec, 'diag-mirror')` + Evidencia tecnica (contadores, discos do mirror, errorlogs, page repair) + Dados brutos. i18n `diag.mirror.*` (11 chaves x3) + `ui.refresh`.
- KPI "Fila de CPU": rotulo do card e ajuda renomeados; FIND-104 (collector V1 `COALESCE(r.status, s.status)`, commit 7635f7c) — herda via BD; V6 so' precisa do rotulo/help se tiver o card.
- Teste: `test_mirroring_diagnosis_endpoint_with_mocked_db` (mock de `async_execute_on_server`).
