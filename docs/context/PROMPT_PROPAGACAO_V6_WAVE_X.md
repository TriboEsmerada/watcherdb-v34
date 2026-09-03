# PROMPT — Propagação Wave X (KPI Integridade) para o V6

> Colar numa sessão de trabalho no repo WATCHERDB_V6 (git próprio, local-only).
> Origem: WATCHERDB_V3.3 branch wave-X-integridade, CHANGELOG [2.11.0], 2026-07-19.
> Referência de código V3.3: commits da wave (helpers.py, intelligence_kpis.py, watcherdb_portal.html, i18n).

---

## Contexto (lê primeiro)

A Wave X criou o **KPI Integridade** (detecção de corrupção) no V3.3. A camada de dados é
**partilhada** — a view `KPI_MSSQL_INTEGRITY_VERDICT_VIEW` já está criada e validada na
WatcherDB_Intelligence (SECAO 16 do canonical V1; custo <1s para 1.276 DBs). **O V6 herda a
view de graça — só falta o lado consumidor.**

Semântica da view (1 row por database):
- `Verdict`: **P1** = suspect pages registadas (corrupção confirmada) / **P3** = nunca validado
  por CHECKDB (inclui data-sentinela `0001-01-01`/`Days_Since_CheckDB < 0` do collector) /
  **P4** = CHECKDB > 30d / **P5** = ok
- Higiene: `Needs_PageVerify_Fix` (PAGE_VERIFY != CHECKSUM), `Is_Auto_Shrink`,
  `NoChecksum_Events_Recent_LTE7d`
- **P2 (erros I/O 823/824/825): colunas existem mas são NULL de propósito** (fase 2 da wave).
  Indisponível NUNCA se apresenta como "0 problemas". Não "corrigir" isto no V6.

Filosofia aprovada pelo owner: **report & prescribe** — o KPI reporta e indica a solução
(SQL pronto), nunca executa nada.

## O que implementar no V6 (por ordem)

Regra de ouro: **V6 portal NÃO é superset do V3.3** — grep dos anchors primeiro; adapta ao
que existe, não assumas paridade de estrutura.

### 1. Backend
- `collect_integrity(results)` — copiar do V3.3 `api/routers/intelligence/helpers.py` (final
  do ficheiro): SELECT à view + LEFT JOIN `KPI_MSSQL_INST_ENVS` (igualdade simples — NÃO usar
  LTRIM/RTRIM/UPPER, é não-sargável), contagens P1/P3/P4/pageverify + `p1_by_env`.
  **Fail-open honesto**: view ausente => `available: False` e contagens None — o card mostra
  N/D, nunca "0" falso.
- Registar no gather do dashboard (Phase 1 / equivalente V6).
- Drill-down: `kpi_type` `integrity` + variantes `integrity-p1` / `-p3` / `-p4` (WHERE por
  veredicto via dict) — cada linha do card abre o modal JÁ filtrado. `SELECT TOP 300` com
  prioridade `P1 > P4 > higiene > P3` e tiebreak determinístico (`Instance, Database_Name`).
  Razão do cap: P3=1195 na frota real — sem cap afoga o DOM; sem prioridade, o sinal
  accionável fica enterrado (memória: KPI signal vs noise).

### 2. Portal (grep primeiro: `renderKpiAdvanced`, `KPI_REPORT_GROUPS`, `_advCard`)
- A Vista Avançada do V3.3 foi **portada DO V6** (2026-06-17), portanto os anchors devem
  existir com nomes iguais ou próximos.
- Grupo em `KPI_REPORT_GROUPS`: `{ key: 'integrity', icon: 'fa-file-shield', crit: ['integrity'], warn: [], link: 'integrity' }`
  (alimenta o gráfico "Por Categoria" e o Relatório Técnico).
- Card `_advCard` "Integridade" (subtítulo "Corrupcao e CHECKDB") com 3 rows clicáveis:
  Corrompidas (suspect pages) -> `integrity-p1` [crítico se >0], Nunca validadas -> `integrity-p3`,
  CHECKDB > 30 dias -> `integrity-p4`; rodapé: PAGE_VERIFY != CHECKSUM + DBs avaliadas.
  Valores `N/D` quando `available === false`.
- **ARMADILHA (custou 1 iteração no V3.3):** se o V6 ainda renderizar a grelha clássica
  `KPI_METADATA`, adicionar o card lá também; se só tiver Vista Avançada, o KPI_METADATA
  entry continua necessário para modalTitle/kpiType do grupo. Verificar qual é a superfície
  VISÍVEL antes de declarar shipped.
- Branch do modal (`metricsHtml`): match por prefixo `kpiType.indexOf('integrity') === 0`.
  Mostrar: Database, Veredicto+motivo colorido, páginas suspeitas (nº erros + último evento),
  Último CHECKDB ("Nunca" quando sentinela), PAGE_VERIFY, AUTO_SHRINK, Recovery/Estado, e o
  bloco **"Solucao recomendada"** por caso (copiar prescrições do V3.3 — comandos SQL
  parametrizados com o nome da DB, `user-select: all`).
  **FRONTEIRA DE TIER (fixar em comentário):** prescrição = texto ESTÁTICO client-side => Std.
  Se um dia for gerada por LLM/heurística, migra para Pro-only (FEATURE_MATRIX 4.1).
- Layout: no V3.3 fundiu-se o card "Servicos & Servidores" no card "Disponibilidade" para a
  grelha fechar 4+4 com o Integridade. **No V6 avaliar a grelha própria** — o objectivo é não
  deixar card órfão em fila sozinha (feedback estético do owner), não copiar cegamente.
- UX fix que veio na wave: "Deadlocks 24h" duplicado (rodapé Performance + card Bloqueios) —
  se o V6 tiver o mesmo duplicado, remover do rodapé.

### 3. Documentação + i18n
- Entrada `KPI_DOCUMENTATION['integrity']` (categoria Disponibilidade) — copiar do V3.3,
  PT/EN/ES, incluindo a linha "reporta e prescreve, nunca executa" e a nota do cap TOP 300.
- Chaves i18n nos 3 locales: `kpi.integrity`, `kpi.integrity_subtitle`, `kpi.integrity_modal`,
  `kpi_report.cat_integrity`.

### 4. Freshness guard
- Se o V6 já consome `KPI_MSSQL_COLLECTION_FRESHNESS_VIEW`: adicionar mappings
  `KPI_MSSQL_DBCC_HISTORY_STG` e `KPI_MSSQL_DB_SETTINGS_STG` -> grupo `integrity` e aplicar o
  **fix do OR-combine** no loop (bug latente V3.3: com 2+ fontes no mesmo grupo, a última row
  sobrescrevia o stale da primeira; minutos = pior caso). Os seeds na META já estão aplicados
  (SECAO 16) — nada a correr na DB.

### 5. Validação antes de declarar shipped
- `python -c "import ast; ast.parse(...)"` nos .py alterados; node `new Function` em TODOS os
  blocos de script do portal (contar antes/depois — têm de bater).
- Browser smoke com dados reais: card com P1 vermelho, cada row abre modal filtrado
  (Corrompidas=3 => 3 rows), prescrição visível, `?` docs com a entrada nova.
- Números de referência da frota (19/07): P1=3 / P3=1195 / P4=78 / total=1276 / PAGE_VERIFY=22.

## Armadilhas conhecidas (todas custaram iterações no V3.3)
1. Data-sentinela `0001-01-01`/Days=-1 => P3, nunca P5 (a view já trata; não "simplificar").
2. Superfície visível do dashboard pode não ser a grelha `KPI_METADATA` (ver 2 acima).
3. Modal pesado: sem TOP 300 + prioridade, 1.276 rows no DOM.
4. Join a `KPI_MSSQL_INST_ENVS` por igualdade simples.
5. `available=false` => N/D. Zero silencioso é a classe de bug que o freshness guard existe
   para matar — não regredir.
6. P2 NULL é decisão de design com parecer, não bug.

## Fora de scope desta propagação (fase 2 da wave, feita primeiro no V1)
- Parse regex de `Error_Number` + `KPI_MSSQL_ERRORLOG_IO_EVENTS_HIST` (P2 vivo).
- Parse das linhas de conclusão de CHECKDB no errorlog (mata a dependência do DBCC DBINFO e
  resolve AlwaysOn/lastknowngood).
- `Collection_Status` no collector de DBCC (CATCH nunca mais engole erro como "nunca").
- Incluir system DBs no universo (caso "Check Database master" invisível).
