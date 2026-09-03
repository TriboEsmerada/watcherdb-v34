# RELATÓRIO DE SESSÃO 2026-07-23 → 25 — ANTES / DEPOIS

Sessão "coletor v3 + reconcile + Integridade v3.1 + UI". 16 commits (14 projetosPython + n/a; 6 V6 repo próprio). Gates: 4 pareceres v1-intel (todos GO-com-condições, condições cumpridas em bundle) + 1 sql-deep-reviewer.

| # | Item | ANTES | DEPOIS | Estado / commits |
|---|------|-------|--------|------------------|
| 1 | Coletor DBCC v3 (erro 2571) | ~965 DBs NOT_MEASURABLE (75%); ticket de grants aberto | DATABASEPROPERTYEX set-based + fallback <2016SP2: **270** NOT_MEASURABLE (-72%), residual = 7 instâncias SQL 2012/2014/2016SP1 por desenho; ticket morto | ✅ validado BD · 354489d |
| 2 | Reconcile diário inst. | INST_ENVS append-only (101 rows, 37 fantasmas desde 25/03); 2 configs V1 divergentes; sync manual nunca corria | usp_reconcile_inst_envs (applock, DryRun, guarda 30d) + sync 3b deactivate-absent + task diária 03h; INST_ENVS **101→64**; purge manual validado | ✅ dry-run em observação ~1 sem · 354489d, a67af9f |
| 3 | servers.json limpo | 95 entradas (32 disabled mortas) | 63 activos; snapshot servers_24072026.json preserva histórico+motivos | ✅ · 354489d |
| 4 | Ping + Trusted_Connection | Ping lia config local do serviço (SQLHDSTST014 sem `enabled` → "1 OFF" eterno; master `use_windows_auth:true` = Trusted_Connection VIVO, Regra Ouro #2) | Ping lê SEMPRE canonical raiz (SQL auth Fernet); 1 OFF sumiu; disponibilidade 100% | ✅ validado browser · 354489d |
| 5 | Wave Integridade v3.1 | suspect_pages sem datafile, filtro 1-3, sem guard cap; zero visibilidade de auto page repair; bug empty-skip-swap latente | +Physical_Name (LUN causa-raiz) + lifecycle 1-7 + guard cap 800 + família nova AUTO_PAGE_REPAIR (AG/mirroring) + CTE susp filtrada IN(1,2,3) + flag ALWAYS_SWAP_ON_EMPTY | ✅ DDL executado (P1=1 real: DW_ODS_TAP, CHECKDB 2017!) · 55e7c6f |
| 6 | Always On UI | Botão "Buscar do Primário" rebentava; link primário → Overview | Botão removido; link + "Ver Detalhes" abrem tab Always On do primário | ✅ V3.3 9c23ab7 + V6 55c1abd |
| 7 | Copy 2571 | "User sql_monitoring does not have permission..." + "resolve-se com GRANT (ticket)" | Texto de plataforma (SQL <2016SP2 sem DATABASEPROPERTYEX; upgrade/GRANT excepção) pt/en/es; bucket "Versão SQL antiga" | ✅ 9c23ab7, bdd5910 + V6 487c066 |
| 8 | Modal Não Mensurável | Gráfico Veredicto redundante (sempre P3) + "Distribuição por Tipo de Falha" em baixo | Veredicto sai; **"Tipo de Falha"** assume o slot | ✅ bdd5910 (V6 = F3 pendente) |
| 9 | Hotfix Env PRD/TST | Sync gravava PROD/TEST (bug latente activado 24/07; 85 rows fora da convenção; dashboards Por Ambiente só QLT) | CASEs corrigidos (sync + sproc + canonical + standalone) + UPDATE dados; buckets PRD/QLT/TST restaurados | ✅ validado owner · 2ddde3a (2.25.1) |
| 10 | Fontes vivas Relatório Técnico | vw_OS_CPU/Memory/Disk_Current sem filtro de idade: 9/10 "CPU críticos" eram fantasmas de Março a 100% | Filtro 30 min (GETDATE validado empiricamente: TS em hora local) + Correlation via Memory_Current (cascata V5/V6 auto-cura) | ⏳ DDL FIX_OS_CURRENT_VIEWS pendente SSMS · f6a2bd1 (2.25.2) |
| 11 | Sort Resumo por Categoria | Ordem fixa | Críticos ↓, avisos ↓, 0/0 no fim | ⏳ validar browser · 7418f19 + V6 b6fc1e3 |
| 12 | Filtro severidade nos cards | Filtro Críticos só escondia cards inteiros; rows warn/zeros ficavam visíveis | _advRow respeita o filtro: CRITICAL só rows crit activas; WARNING só warn activas | ⏳ validar browser · fb6da23 + V6 91c85a3 |
| 13 | Opção B avisos Integridade | Assimetria: laranjas Backups contavam como avisos, laranjas Integridade não | P4 (CHECKDB>30d, 384) conta como aviso via pseudo-id; P3/NOT_MEASURABLE deliberadamente fora; avisos ~2020→~2404 | ⏳ validar browser · (commit desta ronda) + V6 |
| 14 | Memórias + processo | — | 4 memórias owner (panorama sempre; canonical+docs no acto; commit+plano V6; antes/depois no fecho) + 2 propostas (validate-canonical-vs-live; DATABASEPROPERTYEX>grants) | ✅ |

## Pendentes / decisões abertas
- **Owner**: correr `FIX_OS_CURRENT_VIEWS_FRESHNESS_2026-07-25.sql` (SSMS) → CPU críticos ~9→0-2; restarts portais + browser-test (checklist A/B/D + itens 11-13); flip `DRY_RUN=False` do reconcile após ~1 semana; higiene DELETE >30d nas tabelas OS_* (opcional).
- **Backlog**: accordion drill-down nas modais do Relatório Técnico (fase seguinte rollout F1 — item #1 próxima sessão UI); OATXP01 (activo no canonical — manter/remover); typo SS301 (JSON 1-S vs @@SERVERNAME 2-S); D3 sidebar (89 → ler da INST_ENVS); tables: órfã KPI_OS_DISK_STG no config.yaml; P2 errorlog 823/824/825 (fast-follow Wave X — cobriria o incidente DBA_RESOURCE_DB@PRD013).

## Plano V6 (secção F desta sessão — actualizado 2026-07-27)

### Checklist de replicação V6 (estado por item)
| Item | V6 | Como |
|---|---|---|
| Coletor DBCC v3, reconcile+sync, Wave v3.1 backend, hotfix Env, fontes vivas vw_OS_* (+fix Msg 102) | ✅ herda | BD partilhada, zero código V6 |
| Always On → tab alwayson (sem Buscar do Primário) | ✅ aplicado | 55c1abd |
| Copy 2571 (texto de versão) | ✅ aplicado | 487c066 |
| Sort Resumo por Categoria (crit↓, warn↓, 0/0 fim) | ✅ aplicado | b6fc1e3 |
| Filtro severidade dentro dos cards (_advRow) | ✅ aplicado | 91c85a3 |
| Opção B: P4 como aviso Integridade (pseudo-id) | ✅ aplicado | 68da4b0 |
| Modal unmeasurable: Tipo de Falha no slot do Veredicto + 3 gráficos + drilldown + i18n | ✅ aplicado 2026-07-27 | 3e4e818 (drilldown+strip já vinham de bec19bf): gráfico "Tipo de Falha" interativo com design revisto (SEM gráfico Veredicto), filtro Error_Number combinável com env via applyV6BackupFilters, data-errnum no item, 8 pares nytLocalize EN/ES + card Reboot SO no Overview (grid 4→5) com endpoint /api/v1/overview/os-boot |
| servers.json local limpo (99→62 no V3.3) | ✅ aplicado 2026-07-27 | V6 tinha 100 entradas (38 descomissionadas, 27 ainda enabled) → 62, mesmas ids do V3.3; backup servers.json.bak_decom_20260727_propagacao; edição no disco FORA do commit (nota: no repo V6 o ficheiro está tracked, gitignorar = decisão owner) |
| Browser-test V6 (Always On, 2571, sort, filtro, aviso P4, modal Tipo de Falha, card Reboot) | ⏳ owner | pós-restart do serviço V6 (porta 8660) + Ctrl+F5 |


- **Herda via BD partilhada (zero código V6)**: coletor v3, reconcile+sync, Wave v3.1 backend (STG/views/sproc), hotfix Env, fontes vivas vw_OS_*.
- **Aplicado no portal V6** (espelhos commitados no repo próprio, branch wave-X-integridade): Always On tab-nav (55c1abd), copy 2571 (487c066), sort categorias (b6fc1e3), filtro severidade nos cards (91c85a3), opção B avisos (commit desta ronda).
- **Pendente F3** (portal V6 não-superset): 3 gráficos do modal unmeasurable com o design novo (Tipo de Falha no lugar do Veredicto) + drilldown + i18n.
- Nota: branch V6 wave-X-integridade local-only; merge a main = decisão do maintainer V6 (precedente wave-T).
