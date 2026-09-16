# Unificação do inventário de servidores — relatórios da Fase 1 (2026-09-15)

Pedido do owner: diagnóstico + plano para que Configurações → Gerenciar servidores, barra lateral e dashboard usem a mesma identidade e regra de elegibilidade. Divergência relatada: 63 instâncias no resumo vs 62 na barra lateral. Sem alterações de código, config ou dados.

## Relatórios

| # | Ficheiro | Especialista | Eixo |
|---|---|---|---|
| 01 | [01_MAPA_TELAS_explore.md](01_MAPA_TELAS_explore.md) | Explore | 3 telas → endpoints → serviços → fontes → filtros → caches; fórmula do total; consumidores de sql_servers.json |
| 02 | [02_COLLECTOR_V1_v1-intel.md](02_COLLECTOR_V1_v1-intel.md) | watcherdb-v1-intel-specialist | servers.json canónico, sync para metadata.monitored_server, modelo host/instância/alias/listener, vetos de escrita |
| 03 | [03_PLANO_0819_vs_IMPLEMENTADO_v33.md](03_PLANO_0819_vs_IMPLEMENTADO_v33.md) | watcherdb-v33-specialist | PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19 vs código; E6c; gestão; testes |
| 04 | [04_CONJUNTOS_IDS_qa-externo.md](04_CONJUNTOS_IDS_qa-externo.md) | qa-externo | conjuntos de IDs por fonte, hipóteses 62/63, SELECTs pendentes |
| 05 | [05_ARQUITETURA_architecture-advisor.md](05_ARQUITETURA_architecture-advisor.md) | architecture-advisor (Fase 2) | papéis, contrato, opções O0/O1/O2, dashboard como partição, etapas U0-U11 |
| 06 | [06_CASO_CONTRA_challenger.md](06_CASO_CONTRA_challenger.md) | challenger (Fase 2) | caso contra, hipóteses ordenadas, testes T0-T2, critérios C1-C8, ranking A/B/C |
| **Plano** | [plano_unificacao_servidores.md](plano_unificacao_servidores.md) | orquestrador (síntese) | entrega final: diagnóstico, arquitetura, etapas, riscos, validação, rollback, decisões, pendências |

Os 4 especialistas da Fase 1 confirmaram receção sem correcções factuais (v1-intel aceitou a correcção da rota viva).

Entradas de /recall usadas: SOLUCOES.md 2026-09-10 (61+0≠63), 2026-08-20 (sidebar 62 vs 61), 2026-08-21 (fecho de wave com consumidores legado), 2026-08-19 (≥10 fontes), 2026-08-05 (alias SS301).
Ficheiro `unificaservers.md` não existe no disco; `AGENTS.md` do WatcherDB não existe (TestSprite rejeitado para PRD por soberania — `PLANO_TESTSUKITA_2026-09-09.md:3,54`; equivalente interno = TestSukita).

## Verificação do orquestrador (código lido directamente)

Confirmado:
- Rota viva `POST /api/config/sql-servers` = `watcherdb_main.py:1227`; GET em `:1208`. `watcherdb/api/routers/config.py` sem `include_router` (morto). **Corrige o relatório 02**, que apontava `config.py:53,62`.
- Sync para `servers.json` é fail-open: `except Exception as sync_err: logger.warning(...)` e devolve `success: True` (`watcherdb_main.py:1359-1368`).
- `except json.JSONEncodeError` em `watcherdb_main.py:1370` **e** `:1453` — atributo inexistente no módulo `json`.
- `/api/v3/servers`: `repo.servers(enabled_only=False, require_credentials=True)` + salta `enabled` falso e id vazio (`watcherdb_main.py:1155-1170`).
- `_local_credential_ids` aceita `password OR use_windows_auth` (`services/inventory_repo.py:161`); lado BD compara só `upper()` (`:179`).
- Total do dashboard `totI = online + off` (`templates/watcherdb_portal.html:36776,36832,36901`); `ok_count`/`off_count` de vistas KPI (`api/routers/intelligence/helpers.py:1228-1244`); `collect_service_status` soma `extra_off` (`:1935-1941`); ambas no mesmo `asyncio.gather` (`api/routers/intelligence_kpis.py:897-913`).

Evidência adicional (orquestrador):
- **Existe um conjunto real de 62:** `config/sql_auth_rollout.json` → `sql_auth_servers` com 62 ids = `servers.json` menos `OATXP01` (verificado por diff de ids; lido por `api/connection_pool.py:215,553`). Decisão do owner 09/09 (`CONTEXT.md:394-395`). É um conjunto de *modo de autenticação*, não de elegibilidade — mas é um candidato natural a origem do "62" se algum ecrã/relato o usou.
- **A modal não foi gravada desde 29/04:** `config/sql_servers.json.backup` data de 2026-04-29 e não existe `servers.json.backup_pre_sync` (V3.4 e V3.3). Logo, o risco "gravar apaga `SQLHDSSQLT301_I01` do servers.json local → sem credenciais → sidebar 62" é **latente, não a causa observada**.
- **Estado de 20/08** (`SOLUCOES.md` 2026-08-20): OATXP01 `enabled:false` → sidebar 62. Hoje OATXP01 está `enabled: true` no canónico V1 (mtime 2026-09-15 13:41) e no `servers.json` local. Relato 62/63 pode ser desse período — **por confirmar** (data do relato não conhecida).
- Logs V3.4 (484 ocorrências) e V3.3 (18): `/api/v3/servers -> 63 servers (source=db)`, nunca 62.

Contradições entre relatórios, resolvidas:
- "servers.json local todos enabled" (01) vs "chave enabled ausente em 61" (04): compatíveis — ausente = default `True` no código do portal. No canónico V1 (02) a chave é explícita nos 63.
- Denominador do dashboard `KPI_MSSQL_INST_ENVS` (02) vs `ok+off` (01/04): o cartão "Instâncias" do dashboard principal é `ok+off` (helpers.py); `INST_ENVS` é a driving table do módulo Live Monitoring (`live_monitoring.py:1155`) — são ecrãs diferentes.

## Pendências de evidência (bloqueiam a atribuição da causa ao registo)
1. Q1–Q5 do relatório 04, corridas pelo owner como `sql_monitoring`.
2. GET autenticado (conta viewer/dba) a `/api/v3/servers` e `/api/intelligence-kpis/dashboard`, 3 repetições.
3. Data/ambiente/captura do relato "63 vs 62" (dashboard em que cartão? sidebar com pesquisa activa?).
