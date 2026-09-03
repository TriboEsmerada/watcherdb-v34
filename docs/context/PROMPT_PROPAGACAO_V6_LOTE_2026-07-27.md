# PROMPT — Propagação V6 do lote V3.3 de 2026-07-27

Cola isto numa sessão com o repo V6 (WATCHERDB_V6 — git PRÓPRIO local-only;
criar branch dedicada, ex: wave-propagacao-v33-20260727). Trabalha em OODA,
modo consultor + GO por lote. REGRA DE OURO da propagação: **o portal V6 NÃO é
superset do V3.3 — grep dos anchors PRIMEIRO; adaptar ao idioma do V6 (strings
PT hardcoded, sem t(); i18n via pares nytLocalize EN/ES specific-first);
baseline de validação = 10/10 script blocks + py ast.**

Fonte da verdade do lote: WATCHERDB_V3.3/docs/context/CONTEXT.md (entradas
2026-07-27) e RELATORIO_SESSAO_2026-07-27_ANTES_DEPOIS.md.

## A. HERDA VIA BD/serviço partilhado — NÃO reimplementar, só VERIFICAR

A BD WatcherDB_Intelligence e o serviço WatcherDBCollector são partilhados;
estes itens já estão em produção para o V6 sem tocar no repo dele:
1. Auto-resolve server-offline (patch collect_server_ping + Resolved_By
   granular) — validado 28→1 eventos.
2. Migração 009 (coluna Resolved_By + usp_ResolveServerOfflineEvent com
   @Resolved_By default) + canonical SECAO 7 sincronizado (drift 008/008b).
3. Seed WDB_COLLECTION_SCHEDULE_META: row KPI_MSSQL_INST_ENVS/1440/HEARTBEAT
   + heartbeat do adapter reconcile.
4. Fix id SS301 (servers.json V1: SQLHDSSQLT301_I01) + flip DRY_RUN do
   reconcile + fix metadata collect_storage_* (config.yaml V1).
Verificação: nenhum consumidor V6 assume a proc de resolve com 2 params
(a 009 é backward-compatible, mas confirmar por grep usp_ResolveServerOfflineEvent).

## B. PROPAGAR — backend V6 (obrigatório, risco de regressão se ficar)

1. **FileGroups Opção A (CRÍTICO — condição do gate v1-intel):** o gate
   identificou 4 sites em WATCHERDB_V6/api/routers/intelligence_kpis.py
   (~1198-1222, 2558-2604, 2960-2985, 4104-4117) com o MESMO CASE morto
   (Max_Size_MB vs Total_MB nunca diverge — collector grava clone). Aplicar a
   mesma correção do V3.3: `Growth_Type='UNLIMITED'` sai do crítico-por-alocado
   (ver diffs aplicados em WATCHERDB_V3.3/api/routers/intelligence/helpers.py
   collect_filegroup_usage + intelligence_kpis.py detail/filegroup-usage e
   drill genérico). ATENÇÃO: verificar também
   services/ai_assistant_service.py (_evidence_filegroup_specific) e
   services/morning_briefing.py (herdam Effective_Pct) + catálogo
   docs/catalog/09_filegroup_usage.md (Q014 threshold cru).
2. **FileGroups Fase 2 disk-bound (decisão owner: LIMITED=Σmax; UNLIMITED=
   disco):** ramo DATAFILES_STG (Is_Unlimited + Volume_Free_MB; ≤5GB crit /
   ≤10GB aviso; **0 = AVISO "sem visibilidade"**, nunca crítico nem excluído)
   — replicar nos aggregates/drills V6 equivalentes.
3. **Deadlocks com nomes:** drill deadlocks ganha Databases_List/Objects_List
   (STUFF/FOR XML da DET_VIEW, piso 2014) — replicar no branch V6 (grep
   KPI_MSSQL_DEADLOCKS_AGG_VIEW).
4. **Resolved_By nos endpoints de resolve:** V6 tem os mesmos
   /server-offline/resolve* — passar username do admin com fallback se a proc
   antiga (padrão aplicado no V3.3 intelligence_kpis.py).
5. **Collector Health (SE o V6 tiver o módulo — grep modules/collector_health):**
   fallback HEARTBEAT via SCHEDULE_META (usa Expected_Interval_Minutes como
   cadência real) — o disabled_reason vem do config.yaml partilhado (grátis).

## C. PROPAGAR — portal V6 (grep-first; adaptar, não copiar)

Para cada item: grep anchor no portal V6; se a feature-base não existir,
marcar N/A justificado (não construir do zero sem decisão do owner).
1. **Remoção do KPI "SQL Não Respondeu"** da frota (se existir no V6: card,
   doc, grupos de relatório) + row "SQL em baixo"; manter service_status.
2. **Painel "Eventos do collector"** na página Collector do V6 (se a página
   existir): badge, tabela 7d, Resolver, "antigo — confirmar" >24h, instância
   clicável→aba por diagnóstico, auto-refresh 60s.
3. **Aba Log interativa** (se o V6 tiver a aba Log com a mesma estrutura
   loadLogAnalysis): chips de categoria (6, taxonomia persona; backup/cluster
   opt-in via ?categories=), filtros por coluna (input+datalist), cards
   Windows/SQL como toggles de fonte. Backend logs_collector: entry 'memory'
   no category_map (se o V6 usa o mesmo módulo — provável partilhado, verificar).
4. **Modal UX FileGroups:** barra do env chart na cor da SEVERIDADE do modal
   (não trocar paleta de ambiente — foi testada e REJEITADA), badge por
   contexto (-warning => WARNING), Total com unidade "(filegroups)", card
   conta items_total, accordion F2 com NOMES filtrados por severidade + links
   →Space (se o V6 tiver navigateToSpaceFilegroup; incluir scroll retry
   400ms/1.5s/3.2s + flash).
5. **Docs KPIs:** entries backup-log-failed/backup-no-checksum + reescrita do
   backup-failed + 3 bullets Integridade (2571/P4-aviso/Tipo de Falha) —
   adaptar ao formato de docs do V6 (pares nytLocalize EN/ES).
6. **Regra "nome, não número"** e **Collector Health maximizar/Motivo** — se
   as superfícies equivalentes existirem.

## D. Armadilhas conhecidas
- V6 = repo git próprio; parent projetosPython NÃO faz tracking dele (incidente
  98c18ed) — git status NO diretório V6.
- Portal V6 sem t(): strings PT diretas; EN/ES via nytLocalize specific-first.
- Baseline de blocks do V6 = 10/10 (não 12/12).
- KPI_REPORT_GROUPS/vista avançada do V6 têm estrutura própria — mapear antes.
- CHANGELOG V6 próprio; commit só de paths da wave.

## E. Fecho
- Bulletin aos counterparts (condição 6 do gate auto-resolve): V5/V6 herdam a
  BD — avisar da 009/Resolved_By, do fix FileGroups (CASE morto neles também)
  e da semântica 0=aviso.
- Validação: 10/10 blocks + py ast + browser test owner; actualizar
  PROPAGACAO_V6_PENDENTE.md (estado por item) e CONTEXT.md do V3.3 com 1 linha
  + ponteiro.
