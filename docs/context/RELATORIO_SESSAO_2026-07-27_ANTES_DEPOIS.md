# Relatório de Sessão 2026-07-27 — ANTES vs DEPOIS

Sessão-maratona V3.3 (+V1). 3 gates v1-intel (D3, auto-resolve, FileGroups),
2 sweeps, ~30 lotes de edição. Validação em todos os lotes: node 12/12 script
blocks + py ast + yaml/json. Estados: **APLICADO** (código no working tree),
**EXECUTADO** (owner correu em produção), **PROPOSTO/PENDENTE**.

## A. Aba Log

| # | Item | ANTES | DEPOIS | Estado |
|---|------|-------|--------|--------|
| A1 | Chips de categoria | Backend classificava eventos (category/event_type) e a UI descartava; categorias cluster/csv/backup opt-in nunca chamadas | 6 chips (SQL Server, Always On, Cluster/Storage, Reinícios, Disco, Backup) com contadores, refetch on-demand c/ dedupe e "clica p/ buscar"; taxonomia validada por persona (2 vetos incorporados); i18n 11 chaves ×3 | APLICADO |
| A2 | Categoria memory | Código morto: MEMORY_EVENT_IDS classificado mas sem entry no category_map (nunca coletado) — achado 2× independente | Entry `memory` opt-in no category_map (logs_collector.py) | APLICADO |
| A3 | Filtros por coluna | Colunas só ordenavam | Input+datalist por coluna (valores encontrados ordenados por tipo + escrita livre, debounce, patch só do tbody); Mensagem = escrita livre | APLICADO |
| A4 | Cards Eventos Windows / Erros SQL | Estáticos | Toggles de fonte (clique filtra, re-clique volta a Todos; ring, aria, sincroniza seletor Tipo; re-render local sem refetch; chip incompatível limpo) | APLICADO |

## B. Monitoria do collector (decisão: auto-monitoria sai da frota)

| # | Item | ANTES | DEPOIS | Estado |
|---|------|-------|--------|--------|
| B1 | KPI "SQL Não Respondeu" | Card na frota media eventos do collector central (timeout+SQL down) — confundia auto-monitoria com frota | Removido do dashboard (modal custom 258 linhas, card, doc, grupo Rel.Técnico, row "SQL em baixo", linha FEATURE_MATRIX); row "Serviços em baixo" (SERVICE_STATUS dos servidores do JSON) mantida via sql-services-down; endpoints backend preservados | APLICADO |
| B2 | Painel "Eventos do collector" | Eventos sem UI própria (só o KPI removido) | Painel colapsável na página Collector: badge ativos, tabela 7d, Resolver, "antigo — confirmar" >24h, Instância clicável→aba por diagnóstico (sql_down→Services, offline→Overview), auto-refresh 60s | APLICADO + validado browser |
| B3 | Auto-resolve (V1) | 28 eventos "ativos" presos desde 08:11 (skip-branch dynamic-port nunca fechava sql_down; collect_data_async era código morto — correção ao parecer de 21/07) | Skip-branch resolve via availability cross-ref; Resolved_By granular (icmp/tcp/availability-crossref) c/ fallback deploy-order-safe; **provado em produção: 28→1** (resta 1 órfão p/ backfill seletivo) | APLICADO + EXECUTADO |
| B4 | Migração 009 + canonical | Tabela sem Resolved_By; canonical SECAO 7 com drift antigo (proc upsert 5-param vs 7 em produção desde a 008b — fresh install nasceria partido) | 009 (coluna+proc c/ default) criada e EXECUTADA pelo owner; canonical sincronizado (tabela +3 cols, upsert 7-param, resolve c/ auditoria); endpoints V3.3 gravam username do admin no resolve manual | APLICADO + EXECUTADO |

## C. Collector Health

| # | Item | ANTES | DEPOIS | Estado |
|---|------|-------|--------|--------|
| C1 | 4 tasks NEVER_RAN | Falsos alarmes: collect_storage_* com module inexistente + tabela KPI_MSSQL_STORAGE_STG que nunca existiu; reconcile sem fonte de frescura (INST_ENVS sem swap/timestamp) | storage: module+tables corrigidos no config.yaml; reconcile: heartbeat no adapter (padrão D4) + seed INST_ENVS/1440/HEARTBEAT (guard standalone re-executado pelo owner + canonical SECAO 15) + fallback HEARTBEAT no health_calculator (usa Expected_Interval_Minutes como cadência real). **NEVER_RAN 0/129 validado browser** | APLICADO + EXECUTADO |
| C2 | 11 DISABLED "motivo não documentado" | Motivos existiam só em comentários YAML que a UI não lê | disabled_reason preenchido nas 12 tasks (campo já suportado pelo calculator) — UI mostra motivos reais; 3 classes: duplicados/legacy, QA sem AG, por implementar/pesados | APLICADO + validado browser |
| C3 | Modal Collector UX | Sem maximizar; Motivo truncado a 80c/260px | Botão expand/compress (padrão do programa, 98vw×96vh) + Motivo 280-560px com wrap completo | APLICADO |

## D. Reconcile / SS301 / D3

| # | Item | ANTES | DEPOIS | Estado |
|---|------|-------|--------|--------|
| D1 | DRY_RUN reconcile | True desde 23/07 (INST_ENVS congelada desde purga 24/07) | False (logs 24-27 revistos: 0 deletes; 48 updates = convergência pós-2.25.1); 1º ciclo real ≥03h de 28/07 a validar | APLICADO; validação PENDENTE (sessão nova) |
| D2 | Typo SS301 | JSON id SQLHDSQLT301_I01 vs @@SERVERNAME SQLHDSSQLT301 (typo histórico no server, fix bloqueado por restart) — row órfã em grace, drilldown falharia | id do JSON alinhado ao @@SERVERNAME (I01; host mantém DNS; I02 intocado — sem sintoma); pipeline migra no próximo ciclo real | APLICADO |
| D3 | Sidebar → INST_ENVS | /api/v3/servers lê servers.json local (3ª cópia diverge) | Parecer v1-intel GO-com-condições: HÍBRIDO obrigatório (INST_ENVS=membership; JSON=enrichment/databases[]/enabled; fallback) — substituição 1:1 quebraria pesquisa por database. Pré-requisitos (SS301+flip) cumpridos | PROPOSTO (implementar pós-validação do ciclo) |

## E. Modais / regra "nome, não número"

| # | Item | ANTES | DEPOIS | Estado |
|---|------|-------|--------|--------|
| E1 | Modal Deadlocks | "Databases: 1, Objects: 1" (contagens sem ação possível) | Drill ganha Databases_List/Objects_List (nomes distintos da DET_VIEW, STUFF/FOR XML piso 2014); card mostra nomes truncados+title, contagem só quando >1; REGRA GERAL registada (audit das restantes modais = próxima sessão) | APLICADO |

## F. FileGroups (a saga do dia — modelo do owner implementado ponta a ponta)

| # | Item | ANTES | DEPOIS | Estado |
|---|------|-------|--------|--------|
| F1 | Ruído do KPI | 8 "critical" no 014 / 31 no 302, todos MAXSIZE 0.00 — collector grava Max_Size_MB=clone de Total_MB p/ unlimited ⇒ ramo maxsize-aware MORTO em 8 sites (V3.3+V5+V6); tocar o collector sem ship coordenado = falso-negativo Pro (gate evitou) | Opção A (V3.3-only via Growth_Type já gravado): 3 sites corrigidos (aggregate, drill, detail); UNLIMITED sai do crítico-por-alocado; ligado ao handoff V6 de junho | APLICADO |
| F2 | Modelo LIMITED/UNLIMITED (owner) | KPI só olhava % do alocado | LIMITED: capacidade=Σmaxsize (já era o Percent_Used); UNLIMITED: teto=disco — ramo disk-bound novo lendo DATAFILES_STG (drives por instância, ≤5GB crit/≤10GB aviso, absoluto — STG sem Volume_Total) nas 3 superfícies | APLICADO |
| F3 | Volume_Free_MB=0 | Conflate "desconhecido" com "0 livre" (6 drives/4 instâncias; provado 408 F:\ tem 683GB — mount points + SQL antigo) | Decisão owner calibrada: 0 = AVISO "SEM VISIBILIDADE — verificar no host" (não crítico); fix real na wave collector (CROSS APPLY por ficheiro + xp_fixeddrives + sentinela -1); teste de aceitação: query MIN/MAX do owner diverge pós-fix | APLICADO; wave collector PROPOSTA |
| F4 | Card "Filegroups críticos" | Label dizia filegroups, valor contava instâncias | Valor = items_total (filegroups/drives), alinhado ao label e ao env chart do modal | APLICADO |
| F5 | Modal: unidades/cores | Total trocava para instâncias ao filtrar ("PRD 3/Total 2"); barras PRD vermelhas na modal Warning; badge CRITICAL na modal Warning | Total mantém unidade (mapa instância→itens) + "(filegroups)"; barra = cor da severidade do modal; badge = severidade do contexto; paleta ambiente experimentada (roxo/azul/verde-escuro) e REVERTIDA ao clássico no mesmo dia | APLICADO |
| F6 | Accordion | Contagens Attention/Warning/Critical sem nomes | F2 lazy: fetch /detail no expand → NOMES (Database+Filegroup+%+Status; filtrado por severidade do modal: Critical→CRITICAL; Warning→WARNING+ATTENTION); cada FG é DEEP-LINK → abre aba Space da instância, expande db+filegroup, scroll com retry (400ms/1.5s/3.2s) + flash | APLICADO + validado browser |
| F7 | Relatório de Espaço | Query enlatada SPC001 rebentava (database_id não existe em sys.database_files); 0.0% pintado vermelho enquanto contava 0; tabela sem filtros | Query frota-wide via master_files (maxsize+growth travado) + versão per-DB; cor segue a CLASSIFICAÇÃO (autogrow → cinza c/ tooltip); filtros Database/FileGroup (datalist+vírgula=vários, AND) + sort em todas as colunas | APLICADO |

## G. Sweeps e diagnósticos (sem edição)

| # | Item | Resultado | Estado |
|---|------|-----------|--------|
| G1 | Sweep backend→UI | 12 campos coletados nunca renderizados (brute-force AD, calculation_method, hard paging, Sessions idle c/ transação, backup preditivo…) + módulos inteiros sem UI (/api/os/* 12 rotas, sqlserver-kpis redundante 17 rotas, overview frota, alert routing) + 2 BUGS (?includeSystem= ignorado; cluster.py nunca registado). Relatório: auditorias/SWEEP_BACKEND_RICO_UI_POBRE_2026-07-27.md | ENTREGUE; consumo por waves pequenas |
| G2 | OATXP01 | Enabled no V1, ausente do JSON V3.3; SQL 2005 SP4 < piso — recomendação: manter fora do portal | DECISÃO OWNER PENDENTE |
| G3 | Órfã KPI_OS_DISK_STG | 3 tasks vivas + DDL fora do canonical (CREATE_OS_DISK_TABLES.sql); dados alimentam vw_OS_* do Rel.Técnico — recomendação: incluir no canonical (gate v1-intel) | DECISÃO OWNER PENDENTE |
| G4 | Obs. ops | Drives de LOG apertados: QLT023 L:\ 3.6GB, TST023 L:\ 8.1GB (fora do scope ROWS) | ENTREGUE ao owner |

## H. Handoffs para a sessão seguinte

- Pacote aba Space (6 pedidos, fim de sessão): spec completa em
  PROMPT_SESSAO_SPACE_2026-07-28.md — inclui matriz do growth decidida com o
  owner e o X falso da checklist de loading. NADA implementado desta lista.
- Prompt geral: PROMPT_SESSAO_V33_2026-07-28.md (Space + validação reconcile +
  D3 + wave collector + audit nome-não-número + propagação V6/bulletin + leves).

## Pendências do owner no fecho

1. Commits (2 blocos: V3.3 + V1 — na conversa; incluir os 2 PROMPT_SESSAO novos
   e este relatório no git add do commit V3.3).
2. Browser tests finos restantes (chips/filtros/toggles Log; card FileGroups
   1 crítico + 9 avisos... nota: valores mudam com a frota).
3. Decisões G2/G3.

Restarts e DDLs (009 + freshness guard) foram EXECUTADOS pelo owner durante a
sessão; auto-resolve, NEVER_RAN=0 e F2/deep-link validados em browser real.
