# PROMPT PROPAGACAO V6 — drill-downs que o V3.3 tem e o V6 não

Data: 2026-08-31 | Origem: levantamento comparativo pedido pelo owner
Regra: portal V6 **não** é superset do V3.3 — grep antes, e o inverso também é verdade
(há 7 drill-downs que só o V6 tem; ver fim).

## Achado que enquadra tudo

Três primitivas existem **só no V3.3**, e explicam quase todas as lacunas:

| primitiva | V3.3 | V6 |
|---|---|---|
| `renderDiagnosisLayout` (motor do layout "Diagnóstico") | `:34931` + CSS `:1393`, 4 consumidores | **0** |
| `card-expand` / `toggleCardExpand` (painel dentro do cartão) | `:42887`, 13 cartões | **0** |
| `.kpi-drill-hint` + `_applyDrilldownAvailability` | `:47979`, 11 sítios | **0** |

Nos links de cartão o V6 está bem: tem **10 dos 11** (com estilo inline em vez da classe).
Falta um — o de Mirroring. O buraco a sério são os **8 drill-downs de 2.º nível**, onde o
V6 tem zero.

**Contagem: V3.3 tem 19; V6 tem 13; faltam 9.**

## Ordem recomendada — o item que desbloqueia três

### Primeiro: portar `renderDiagnosisLayout` (barato, só frontend)

Componente JS de ~100 linhas mais CSS. É **pré-requisito de três** drill-downs:
layout Diagnóstico nas Recomendações de Jobs (`:13989`), no resultado do Analisar Query
(`_diagnoseBuildLayoutHtml` `:42137`) e na Perf Investigation (`perfBuildDiagnosisSpec`
`:54009`). O backend dos três **já existe no V6** (`/api/v1/performance/investigate` e
`diagnose-query` estão lá). Uma peça, três resultados.

### Segundo: `card-expand` + `_fgOpenInSpace` (barato, só frontend)

Painel que expande dentro do cartão do modal, com os filegroups em problema e link para o
Space. O endpoint **já existe no V6** — `api/routers/intelligence_kpis.py:2763`
(`/detail/filegroup-usage/{instance}`), e já é chamado em `:23610`. Só falta a UI.

### Depois, os caros (exigem backend novo)

| item | V3.3 | esforço |
|---|---|---|
| `openMirroringDiagnosis` | `api/routers/queries/mirroring_diagnosis.py` (321 linhas) + JS `:35127` | porte de módulo |
| `plan-analysis` | `api/routers/queries/plan_analysis.py` (433 linhas) + `ctx` no `openDiagnoseQueryModal` | porte de módulo |
| `openDriveDetailModal` (Log Space por drive) | `api/routers/queries/space.py:40` + constante SQL `FILE_SPACE_DETAIL` (**não existe no V6**) | endpoint curto, constante a portar |
| ponte Perf→"Plano" (`data-perf-plan-tid`) | delegação `:54355` | JS barato, **inútil sem o `plan-analysis`** |

## Bloqueio LEVANTADO (actualização 2026-08-31, sessão V3.3)

O porte do **`openMirroringDiagnosis` está desbloqueado**. O teste vermelho
(`test_mirroring_diagnosis_endpoint_with_mocked_db`) não era divergência de contrato:
o endpoint PRODUZ `mirror_errorlog` (`mirroring_diagnosis.py:261`); o mock tinha data
literal '2026-08-17' e o filtro de errorlog é janela de 7 dias — o teste "expirou" a
24/08. Mock corrigido para data relativa; 13/13 verdes. Nem o endpoint nem o teste
estavam conceptualmente errados — portar com confiança.
Ver `PROMPT_V33_SUITE_TESTES_2026-08-31.md` (revisto), ponto 2.

**Nota de atraso:** este é o 3.º pedido do mesmo porte de `renderDiagnosisLayout`
(`PROMPT_PROPAGACAO_V6_DIAGNOSTICO_2026-08-17.md`, `PEDIDO_SESSAO_V6_PROPAGACAO_2026-08-18.md:19`,
e este doc) — 14 dias em fila. Priorizar.

## Obstáculo estrutural em qualquer porte caro — com recomendação

O V3.3 tem `api/routers/queries/` como **pacote** (`backup.py`, `space.py`, `performance.py`,
`plan_analysis.py`, `mirroring_diagnosis.py`, `tempdb.py`, `_diagnostics_legacy.py`).
O V6 tem tudo achatado em `api/routers/sql_queries.py`, com **38 rotas**. Qualquer porte
obriga a decidir: criar o pacote no V6, ou engordar mais aquele ficheiro. Decisão do
owner antes de começar — fazê-la por omissão é como se chega a 38 rotas num ficheiro.

**Recomendação (sessão V3.3, com precedente):** criar o pacote. O V3.3 já viveu este
problema exacto — `sql_queries.py` com 3901 LOC foi decomposto em 7 sub-módulos na
remediação da auditoria V3.2 (`docs/audit/AUDIT_REMEDIATION_V3.2_COMPLETE.md:79`,
item 13, -89% LOC). Repetir a decisão que já se provou, em vez de repetir o problema.

## O sentido inverso (não são regressões, mas convém saber)

Sete drill-downs existem **só no V6**: Jornal/NYT (tendência 7 dias, detalhe da notícia),
AI Evidence por categoria, Memory right-sizing, Root-cause analysis, Wait analysis. São
features exclusivas do V6, não buracos do V3.3.

Uma excepção que vale a pena saber: o detalhe de **servidores offline** existe no V6 e foi
**removido do V3.3 de propósito** — o comentário do owner está no código
(`templates/watcherdb_portal.html:33469-33471`). Não repropagar sem falar com ele.
