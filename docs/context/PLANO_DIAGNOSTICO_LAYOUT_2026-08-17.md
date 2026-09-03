# Plano — Layout "Diagnóstico" (Performance / SQL Diag / Jobs) + análise do plano de execução

> Owner 17/08/2026: adoptar o layout do mock (resumo / problemas / recomendações com impacto-esforço /
> painel + próximo passo) na aba Performance e noutras; substituir a nomenclatura L1–L5; e **analisar o
> plano de execução, dizendo se o plano executado é o melhor**. GO dado. Debate: frontend, UX,
> DBA persona, v33, sql-deep-reviewer (planos). Estado: **EM IMPLEMENTAÇÃO**.

## 1. Decisões (consenso)

| Tema | Decisão |
|---|---|
| Nomenclatura | Fora "L1–L5" do ecrã. Cinco blocos, sempre com os mesmos nomes em todos os módulos: **O que se passa** (veredicto + stat-cards) → **Porquê** (problemas detectados com evidência + origem + frescura) → **O que fazer** (recomendações ordenadas, badges Impacto/Esforço) → **Evidência técnica** (colapsado; tabelas DMV/plano) → **Dados brutos** (colapsado, discreto). |
| Componente | UM `renderDiagnosisLayout(spec, idPrefix)` global (bloco `<script nonce>` existente, junto a `getSevTokens`), CSS `.diag-*` no `<style nonce>` existente. Nunca blocos novos (CSP). |
| Cor | Só escala de severidade (`--sev-*`/`getSevTokens`); zero cor decorativa (roxo/laranja fora); títulos neutros; badges em tint (`.gap-pill`): Impacto = severidade colorida com ▲; Esforço = neutro com ●. Números do resumo neutros salvo severidade. |
| Ordem das recomendações | impacto desc, empate → esforço asc; legenda de 1 linha; sem mapa 2×2; score só com fórmula visível (tooltip). |
| Evidência | cada problema: objecto real, número, origem (`dmv` / `plan_estimated` / `plan_actual` / `history`), timestamp; heurística marcada "não confirmado". Nunca "considere rever índices". |
| Próximo passo | T-SQL de verificação **read-only** copiável (data-attributes + delegação, sem onclick JSON); DDL só comentado (`-- CREATE INDEX ...`). |
| Onde SIM | Performance (modal do investigator: componente substitui L2+L3; L4/L5 = Evidência técnica / Dados brutos), SQL Diag "Diagnóstico de Query Lenta", Jobs (recomendações de manutenção/colisões). |
| Onde NÃO | Backup (checklist de conformidade), Space/Disk (séries), AlwaysOn (topologia) — DBA persona. |
| Tier | Standard: regras determinísticas; só "Recomendações/Causa-raiz AI-powered" são Pro (FEATURE_MATRIX:136-137). Sem comparação cross-instância (Baseline/Instance Compare = Pro :141,147). |
| A11y | `role="dialog" aria-modal` nos 2 modais-alvo (gap P0 pré-existente), `<ol role=list>`, badges com texto, foco visível, aside cai < 1200px. |
| Falso positivo | "Marcar como não-problema" só visual (estado do render), com motivo — sem escrita em BD. |
| Plano de execução | Fase B: `modules/performance/plan_analyzer.py` (puro Python; namespace `showplan/2004/07`; sem `defusedxml` nas deps → rejeitar `<!DOCTYPE`/`<!ENTITY` + caps tamanho/nós), endpoint `POST /api/v1/performance/analyze-plan`; regras fáceis (MissingIndexes, Warnings NoJoinPredicate/PlanAffectingConvert/SpillToTempDb/ColumnsWithNoStatistics, HEAP, custo por operador, Sort/Hash, Parallelism, MemoryGrant) vs heurísticas `confidence:low` (CTE re-lida, função em coluna). "É o melhor plano?" = respostas honestas: comparação com outros planos do mesmo `query_hash` no cache / Query Store quando activo; senão "sem base de comparação". Detalhe T-SQL: parecer do sql-deep-reviewer (§4). |

## 2. Contrato `spec`

```
{ header:{title,subtitle,context,verdict:'critical'|'warning'|'info'|'ok'},
  summary:[{label,value,sub,icon,severity}],
  problems:[{id,title,evidence,impact,icon,severity,source,ts,recIds[],confidence:'measured'|'heuristic'}],
  recommendations:[{id,title,desc,impact:'very_high'|'high'|'medium'|'low',effort:'low'|'medium'|'high',problemIds[],sqlCheck}],
  side:{title,rows:[{k,v}]}, nextStep:{text,sqlCheck},
  technical:{html}   // opcional: Evidência técnica já renderizada (L4)
  raw:{obj}          // opcional: Dados brutos }
```

## 3. Fases (1 commit cada)

```
D0 base.py: Recommendation.effort (default '') + effort nos investigators      ░
D1 componente renderDiagnosisLayout + CSS .diag-* + i18n diag.* + nomes novos  ░
D2 piloto Performance: perfRenderResult usa componente (mapa InvestigationResult) ░
   + role=dialog no inv-modal-overlay; L4/L5 -> Evidencia tecnica / Dados brutos
D3 piloto SQL Diag: renderDiagnoseResults -> componente + role=dialog           ░
D4 plan_analyzer.py + endpoint + "melhor plano?" (query_hash/QS) + UI colar XML  ░
D5 Jobs: adapter maintenance_recommendations/colisoes -> componente             ░
D6 QA (pytest, i18n, tier), CONTEXT.md, prompt V6                               ░
```

Handoff: `modules/performance/base.py` é partilhado com V5 (nota no bulletin pelo v33).

## 4. "É o melhor plano?" — desenho (sql-deep-reviewer) e o que ficou implementado

**Honestidade:** "melhor plano" não é decidível (o optimizador não enumera o espaço). O produto responde só a perguntas decidíveis, e diz qual:

| # | Verificação | Fonte | Versão | Confiança |
|---|---|---|---|---|
| A1 | Há plano mais barato **em cache** para o mesmo `query_hash` (outros `query_plan_hash`)? ratio CPU/reads/elapsed vs melhor (≥3 exec.); robusto se `min` do actual > `max` do melhor | `dm_exec_query_stats` | 2014+ | medido (viés de parâmetros anotado) |
| A2 | Spread min/max no mesmo plano (>100×) → sniffing | idem | 2014+ | medido (sinal) |
| B | Query Store: ligado? READ_ONLY? regressão vs melhor plano 30d, planos forçados com falhas | `sys.query_store_*` (por DB, `HAS_DBACCESS`) | 2016+ (gate por versão) | medido |
| C | XML do plano actual, **statement-level** (`dm_exec_text_query_plan` por plan_handle+offsets, cap 5 MB): missing indexes, warnings (NoJoinPredicate/PlanAffectingConvert/SpillToTempDb/ColumnsWithNoStatistics/MemoryGrant/UnmatchedIndexes), HEAP scans, operadores caros, estimativa vs actual (só plano actual), mesma tabela lida N× (heurística), UDF/CONVERT_IMPLICIT em predicados (heurística) | plan XML | 2014+ | determinístico / heurístico marcado |
| D | Missing index do plano cruzado com `dm_db_missing_index_*` (confirma seeks/impacto) | DMV | 2014+ | medido |

**Veredictos (texto exacto):** "Plano actual é o mais barato entre N planos observados… não garante que seja óptimo" / "Há um plano ~X× mais barato em {métrica} observado entre … e … (N exec.). Diferença robusta | Pode reflectir parâmetros diferentes" / "Sem base de comparação: 1 plano em cache" / "Plano já não está em cache" / "Análise do XML colado: sem comparação (sem query_hash)". Query Store acrescenta "confirma plano ~X× mais caro na janela de 30 dias".

**Implementado:** `modules/performance/plan_analyzer.py` (parser + findings; guardas DOCTYPE/ENTITY, 5 MB, 20k nós/2k RelOps; namespace `showplan/2004/07`), `api/routers/queries/plan_analysis.py` (`POST /api/queries/plan-analysis/{server_id}`; body `query_hash|plan_handle|offsets|database_name|plan_xml`; A/B/C/D; nunca `CROSS APPLY dm_exec_query_plan` sobre a DMV inteira; ≤2 planos por pedido; parse em `anyio.to_thread`), portal: campo "Plano de execução (XML, opcional)" no modal SQL Diag + contexto oculto (`openDiagnoseQueryModal(serverId, ctx)`) + botão **Plano** nas tabelas de evidência da Performance com `query_hash` (delegação por data-attributes). `heavy_queries.py`/`slow_queries.py` passam a projectar `query_plan_hash`, `plan_handle`, offsets; `total_grant_kb` com gate SQL 2014 (achado do sql-deep-reviewer: antes a query rebentava em 2014).

**Não feito (por decisão):** `defusedxml` (nova dep — em vez disso rejeição de DOCTYPE/ENTITY + caps); 2019+ `dm_exec_query_plan_stats`/`missing_index_group_stats_query` (fase 4, opcional); QS waits 2017+ (fase 3b); persistir planos (= começar Query Store próprio, sem decisão de produto).

## 5. Estado (17/08 fim de sessão)

```
D0 ██████████ base.py effort/DetectedProblem + 8 investigators + hash/offsets + gate 2014
D1 ██████████ renderDiagnosisLayout + CSS .diag-* + 116 chaves diag.* x3
D2 ██████████ Performance: perfRenderResult -> layout (L4/L5 = Evidencia tecnica / Dados brutos), role=dialog
D3 ██████████ SQL Diag: wrapper _diagnoseBuildLayoutHtml (legado = Evidencia tecnica), role=dialog
D4 ██████████ plan_analyzer + /plan-analysis + XML/contexto no modal + botao Plano na Performance
D5 ██████████ Jobs: recomendacoes de manutencao no layout (legado = Evidencia tecnica)
D6 ████████░░ testes 12/12 novos, suite unit verde (5 higiene pre-existentes), tier checker (a correr), CONTEXT.md, prompt V6, commit owner
```
Pende do owner: commit + Restart-Service + browser test (Performance → Heavy Queries → modal; SQL Diag → colar XML; Jobs → Recomendações), e a decisão P3/V1 anterior.
