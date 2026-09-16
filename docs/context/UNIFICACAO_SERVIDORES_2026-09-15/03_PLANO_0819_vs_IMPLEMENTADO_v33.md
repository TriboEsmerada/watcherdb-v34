# 03 — Plano 19/08 (servers.json fonte única) vs implementado (watcherdb-v33-specialist, 2026-09-15)

Autor: watcherdb-v33-specialist, só leitura. Verificação do orquestrador: ver 00_INDICE.md.

## 1. Etapa a etapa — planeado → implementado

| Etapa | Estado | Evidência | Falta |
|---|---|---|---|
| E0 (decisões Q1-Q9) | Sim | `docs/context/CONTEXT.md:17` (GO owner a todas) | — |
| E1 (InventoryProvider + schema, V1) | Sim (fora deste repo) | CONTEXT.md:18-19 (66→85 testes) | — |
| E2 (DDL `metadata.*` + sproc) | Sim | CONTEXT.md:19 "E2 APLICADA... commit 21f642e" | — |
| E3/E3b (sync + discovery, V1) | Sim | CONTEXT.md:20-21 | — |
| E4a/b/c (flip real, reconcile, diff sql_servers 95 vs 63) | Sim | CONTEXT.md:21-22,25 | — |
| E5 (collectors V1 → provider) | Sim | CONTEXT.md:26 "E5 FECHADA... 08-20" | — |
| E6a (portal lê BD) | Sim | `services/inventory_repo.py` + `watcherdb_main.py:1150-1152` | — |
| E6b (monitoring.py, jobs sem `[:20]`) | Sim | `modules/monitoring/monitoring.py:771-772`; `intelligence_kpis.py:662` | — |
| E7/E8 (arquivar legado, fecho) | **Parcial** — declarado fechado a 20/08, revertido a "~90%" a 21/08 | CONTEXT.md:27,29 | ver E6c |
| **E6c (mini-wave, 5 itens)** | **NÃO** | abaixo | todos |

**E6c item a item** (nenhum commit do repo V3.4 toca estes pontos):
1. Boot `SQLServerMonitoring` lê `sql_servers.json` — `watcherdb_main.py:107-110,172-188`. **Não corrigido.**
2. `alwayson.py` fallback a `sql_servers.json` — `api/routers/alwayson.py:756-761`; mensagem de erro ~952 ainda cita o ficheiro. **Não corrigido.**
3. `POST /api/config/sql-servers` — **não descontinuado** (plano §Q7/M5); vivo em `watcherdb_main.py:1227-1375`, com sync UPSERT+DELETE `sql_servers.json → servers.json` local que não estava no plano. `watcherdb/api/routers/config.py:53` **não é importado** — código morto.
4. Hardcoded: `watcherdb_main.py:4493-4496` (`servers_list = ["SQLIDSPRD03\\I01", "SQLIDSPRD04\\I01"]` em `/api/monitoring/memory/alwayson/{ag_name}`) e `~4700+` (`get_memory_servers` lê `TAP_SQL_Server_Inventory.xlsx`). **Não corrigido.**
5. Sombra 7 dias — dispensada com justificação (diff manual E4c). **Não é gap.**

## 2. `services/inventory_repo.py` (InventoryRepo)

API pública (`:108-275`): `servers(enabled_only, environment, force, require_credentials)`, `get(server_id)`, `source` (property), `load_monitored_servers()` / `get_inventory_repo()`.

- **Fonte**: `settings.inventory_source` (`watcherdb/core/settings.py:56-60`), default `"db"`; `"file"` = rollback.
- **Fallback**: `_refresh()` (`:236-254`) tenta BD; se falhar/vazia, `config/servers.json` local; se ambos falharem, mantém cache anterior.
- **Cache**: memória, `RLock`, TTL `inventory_cache_seconds` (60s), invalidado só por `force=True` ou expiração — **sem invalidação por evento**.
- **Credenciais**: nunca devolvidas; `has_credentials` por cruzamento com `config/servers.json` local (`_local_credential_ids()`).

**Usam o repo**: `api/routers/intelligence/helpers.py:479-480`, `api/routers/intelligence_kpis.py:516-517,662`, `modules/monitoring/monitoring.py:771-772`, `watcherdb_main.py:1151-1152` (`/api/v3/servers`) e `:3462-3463` (`/api/servers`).

**Bypassam o repo**:
- `watcherdb_main.py:107-188` (boot) — `sql_servers.json`.
- `watcherdb_main.py:4493-4496` e `~4700+` — hardcoded / Excel.
- `api/routers/alwayson.py:758-761,952` — fallback `sql_servers.json`.
- `api/connection_pool.py:200,408-479` — `servers.json` local (**intencional**, credenciais).
- `api/routers/network_diagnostics.py:42-44` — `servers.json` local (**intencional**, precisa de creds).
- `modules/monitoring/watcherdb_alwayson_check.py:126` — `Path('config/servers.json')` directo, **não migrado** (listado no plano §6.2).
- `services/database_discovery_service.py:194-198` (`discover_all`) — lista de servidores a descobrir lida do `servers.json` local, independentemente de `inventory_source`; só a escrita (`:264-272`) é gated. **Achado novo.**
- `watcherdb_main.py:1227-1375` (POST) — lê/escreve `sql_servers.json` e sincroniza `servers.json` local.
- `watcherdb/api/routers/config.py` — não registado (morto).
- `watcherdb_intelligence.py:1848,2489,2513,5796,5836` — legado não importado (morto).

## 3. Gestão de servidores

- **SPA**: `templates/watcherdb_portal.html:47289-47878`. Botão `data-dba-gated="1"` (4306). `GET /api/config/sql-servers` (47309) põe o JSON completo num `<textarea>`; `saveSqlServersConfig()` (47782-47857) faz POST do JSON inteiro; `reloadSqlServersConfig()` (47860).
- **Onde grava**: `watcherdb_main.py:1227-1375` → **`sql_servers.json`**. Sync `sql_servers.json → servers.json` (1266-1358): INSERT com defaults Windows Auth + username/password vazios; UPDATE só `description/environment/priority/enabled`, preservando `password/username/use_windows_auth/has_alwayson/ag_name/ag_listener/databases`; DELETE quando id sai de `sql_servers.json`; `port` fora do UPDATE.
- **Falha**: fail-open — `except Exception as sync_err: logger.warning(...)` (1359-1360); erro **não reportado ao utilizador**.
- **Atomicidade/backup/concorrência**: não atómica (`open(config_path,'w')`); backup único `.json.backup` sobrescrito; `servers.json` com `.json.backup_pre_sync` único; **sem lock** (perda de alteração com 2 admins — HIPÓTESE).
- **Protecção**: `_require_dba` (decisão owner 2026-08-16), auditoria `SQL_SERVERS_CONFIG_SAVED`, CSRF por `SameOriginMiddleware` (`0999245`).
- **ACHADO NOVO (FACTO)**: com `inventory_source=db`, a sidebar lê a BD. A modal grava `sql_servers.json` e sincroniza o `servers.json` **local**, que só alimenta a sidebar em modo `file`. **Hoje, editar a modal não altera o inventário mostrado no portal** — só o mirror de credenciais/fallback (lido por `connection_pool`, `network_diagnostics`, `watcherdb_alwayson_check`). A modal opera sobre um 3.º ficheiro desligado da fonte canónica V1 e da BD.

## 4. Ver/reactivar inactivos — bate com a sidebar?

**Não.** A modal mostra o `sql_servers.json` bruto; reactivar editando o JSON só chega ao `servers.json` local, que não é a fonte da sidebar em modo `db`. A sidebar filtra `enabled` a partir de `metadata.monitored_server`, que só muda com a sync do collector V1 a partir do JSON canónico.

## 5. Tier

`docs/FEATURE_MATRIX.md` não menciona inventário/gestão de servidores. Pelo framework das 4 perguntas é infra de configuração indispensável → **Std + Pro**. Nenhuma parte do plano cai em Pro-only.

## 6. Testes e riscos de regressão

- `tests/unit/test_inventory_repo.py` — `rows_to_entries`, `InventoryRepo` (cache, fallback, `require_credentials`).
- `tests/test_functional_acceptance.py:127,137,241-242,257-258,274-275` — `/api/v3/servers` contra ambiente real.
- `tests/unit/test_connection_pool.py`, `test_farm_inventory_parser.py`, `test_install_orchestrator.py` — `servers.json` noutro escopo.
- **Sem teste** para: POST `/api/config/sql-servers` (sync, backup, fail-open), boot `SQLServerMonitoring`, fallback `alwayson.py`, hardcoded, `database_discovery_service.discover_all()`.
- Risco: fechar E6c sem testes depende de restart manual + browser test.
