# 01 — Mapa das 3 telas até às fontes (Explore, 2026-09-15)

Autor: agente Explore (very thorough), só leitura. Caminhos relativos à raiz do WATCHERDB_V3.4.
Verificação do orquestrador: ver 00_INDICE.md (pontos confirmados e correcções).

## Resumo
- **Gestão (A):** edita o `config/sql_servers.json`, que tem 95 entradas. Esse ficheiro não alimenta nem a sidebar nem o dashboard.
- **Sidebar (B):** conta as instâncias activas e habilitadas da BD (`metadata.monitored_server`) que também têm credenciais no `config/servers.json` local.
- **Dashboard (C):** o total vem de duas contagens em vistas KPI (online + offline). Não vem de nenhuma lista de inventário.
- **Logs:** no log de hoje o backend devolve **63 servidores** à sidebar, não 62. A diferença relatada não se explica por este ambiente.

---

## (A) Configurações → "Gerenciar Servidores (sql_servers.json)"

| Camada | Detalhe | ficheiro:linha |
|---|---|---|
| Botão | `openSettingsModal()`, com `data-dba-gated="1"` | `templates/watcherdb_portal.html:4306`, `:5226` |
| JS de carga | `window.openSettingsModal` faz `fetch('/api/config/sql-servers')` e mostra o JSON num textarea | `portal.html:47289-47313`, `:47353-47355` |
| JS de gravação | `saveSqlServersConfig()`: valida o JSON e se `servers` é lista, depois faz **POST** | `portal.html:47782-47808` |
| JS de recarga | `reloadSqlServersConfig()` faz GET | `portal.html:47860-47870` |
| Leitura | `GET /api/config/sql-servers` → `get_sql_servers_config`. Só exige autenticação (middleware), qualquer papel lê | `watcherdb_main.py:1208-1225`, `:686-716` |
| Gravação | `POST /api/config/sql-servers` → `save_sql_servers_config`, com `_require_dba` (dba ou admin) | `watcherdb_main.py:1227-1235` |
| Fonte | `SQL_SERVERS_CONFIG_PATH = config_dir()/sql_servers.json` | `watcherdb_main.py:103,107`; `watcherdb/core/paths.py:54-56` |
| Não há PUT nem DELETE | — | — |

**Como a gravação funciona**
- **Backup:** `shutil.copy2` para `sql_servers.json.backup`. É um único ficheiro, substituído a cada gravação (`:1244-1248`).
- **Escrita:** não é atómica. Faz `open(config_path,'w')` directamente, sem ficheiro temporário nem `os.replace`, e sem lock (`:1251-1252`).
- **Auditoria:** `_log_auth(... "SQL_SERVERS_CONFIG_SAVED")`; se falhar, é ignorada (`:1259-1267`).

**Sincronização para `servers.json`** (`watcherdb_main.py:1269-1361`)
- Só corre se o `servers.json` já existir (`:1283`). A chave de identidade é o `id` exacto, sem upper nem strip (`:1288`).
- **DELETE:** remove do `servers.json` os ids que já não estão no `sql_servers.json` (`:1290-1297`).
- **UPDATE:** actualiza só `description`, `environment`, `priority` e `enabled`; a porta fica de fora de propósito (`:1300-1317`).
- **INSERT:** acrescenta os ids novos com `use_windows_auth: True` e `password: ''` (`:1319-1345`).
- **Escrita:** só grava se houve mudanças, com backup `.json.backup_pre_sync`, também não atómica (`:1347-1354`).
- **Se falhar:** fica só um `logger.warning` e o POST devolve `success: True` na mesma (`:1359-1360`).

**Problemas encontrados**
1. **`except json.JSONEncodeError` (`:1370`) não existe.** `hasattr(json,'JSONEncodeError')` é `False`. Qualquer excepção no try, incluindo o 400 de `:1241` ou um erro de escrita, gera `AttributeError` ao avaliar essa cláusula. O resultado é um 500 genérico, sem o `detail` esperado.
2. **Invalidação de cache após gravar: nenhuma.**
   - O `InventoryRepo` não tem método de invalidação e ninguém chama `servers(force=True)`; só expira pelo TTL de 60s.
   - `app.state.sql_servers_config` é lido **só no arranque** (`watcherdb_main.py:172-185`). Por isso a UI pede para reiniciar o serviço (`portal.html:47368`).
   - A cache de credenciais do `connection_pool` recarrega quando muda a data do ficheiro, mas usa um caminho relativo `"config/servers.json"` (`api/connection_pool.py:200,440-447`).
3. **Risco se alguém gravar hoje:**
   - O `sql_servers.json` tem 95 entradas e o `servers.json` tem 63. Há 33 ids só no `sql_servers.json` e 1 só no `servers.json` (`SQLHDSSQLT301_I01`).
   - Ao gravar, o sync **apaga** `SQLHDSSQLT301_I01` do `servers.json`.
   - E **insere 33** entradas com `use_windows_auth=True`. Como `_local_credential_ids` aceita `password OR use_windows_auth` (`services/inventory_repo.py:161`), esses 33 passam a contar como "com credenciais".
   - Em modo BD aparecem na sidebar se estiverem activos na BD; em modo ficheiro aparecem logo.
4. **Mensagens inconsistentes:** a UI diz "Apenas administradores" (`portal.html:47815`), mas o backend aceita dba (`watcherdb_main.py:1234`). O runbook diz que o `sql_servers.json` está "ARQUIVADO — nenhum código o lê" (`docs/guides/RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md:105`), o que é falso (ver secção de consumidores).
5. **A gestão não chega à fonte da sidebar nem do dashboard.** A BD é alimentada pelo `servers.json` canónico do V1 (`knowledge_base/architecture/cross_cutting/inventario_servers_json_fonte_unica.md:10-24`; runbook `:3-7`).

---

## (B) Sidebar "SERVIDORES (N)"

| Camada | Detalhe | ficheiro:linha |
|---|---|---|
| Contador | `#sidebarCount` = `filteredServers.length` | `portal.html:4822`, `:6459-6465` |
| JS | `loadServers()` faz `fetch('/api/v3/servers')`; num 401 ou erro tenta de novo uma vez após 3s | `portal.html:6331-6423`; chamadas em `:5081-5084`, `:5436-5440`, `:6101` |
| Render | uma linha por item, sem limite nem dedup | `portal.html:6428-6457` |
| Endpoint | **GET `/api/v3/servers`** → `get_servers_list` | `watcherdb_main.py:1138-1206` |
| Serviço | `get_inventory_repo().servers(enabled_only=False, require_credentials=True)` | `watcherdb_main.py:1151-1155` |
| Escolha da fonte | `settings.inventory_source` (por defeito `"db"`, env `INVENTORY_SOURCE`) | `watcherdb/core/settings.py:60-62`; `inventory_repo.py:127-132` |
| Fonte BD | `metadata.monitored_server WHERE tenant_id='default' AND is_active=1`, mais as bases com `d.is_active=1` | `inventory_repo.py:37-53`, `:169-186` |
| Fallback | `config/servers.json` (`monitored_servers`), quando a BD falha **ou vem vazia** | `inventory_repo.py:172-173`, `:236-254`, `:188-206` |

**Cache**
- Em memória no processo: um único `InventoryRepo`, chave única (a lista toda), protegido por `RLock` (`inventory_repo.py:108-117`, `:257-267`).
- TTL de `inventory_cache_seconds`, 60s por defeito (`:134-139`, `:213`).
- Se a BD e o ficheiro falharem ao mesmo tempo, mantém a cache anterior (`:249-253`).
- No JS não há cache da lista; o `localStorage` só guarda a ordenação (`serverSortOrder`, `:6378`) e a frequência de uso.

**Identidade e normalização**
- O `id` é `monitored_server.instance_id`, no formato `HOST_INST` (`inventory_repo.py:88`).
- Ids com credenciais no ficheiro local: `id.strip().upper().replace("\\","_")` (`:162`).
- Lado da BD: só `upper()`, sem strip nem troca de `\` (`:179`).
- Não há dedup no código. Na BD existe `UNIQUE (tenant_id, instance_id)`, segundo a DDL draft (`docs/context/PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19_ANEXO_DDL.sql:41`).
- Nome mostrado: `host\instance` ou só `host` (`watcherdb_main.py:1175-1178`). A sidebar conta **entradas de instância**, não hosts.

**Condições de exclusão no caminho `/api/v3/servers`**
1. Na SQL: `tenant_id <> 'default'` ou `is_active = 0` (`inventory_repo.py:42`).
2. Sem credenciais locais: o id da BD não aparece entre os ids do `servers.json` com `password` ou `use_windows_auth` (`:176-182`, filtro em `:218-219`).
   - É fail-open: se o ficheiro estiver ilegível, `cred_ids` é None e todos passam (`:179`).
   - Os excluídos ficam no log `[INVENTORY_REPO] ... ocultos na sidebar` (`:183-185`).
3. `enabled` falso (`watcherdb_main.py:1164-1165`).
4. `id` vazio ou None (`:1167-1169`). Em modo ficheiro, o id cai para `server_id` (`inventory_repo.py:198`).
5. Qualquer excepção ao montar um item faz saltar esse item em silêncio (`:1199-1200`).
6. No JS: a pesquisa com 2 ou mais caracteres filtra a lista e muda o contador (`portal.html:7029-7036`, `:7114`).
- Não há RBAC por servidor nem filtro de ambiente na sidebar; o middleware só exige token.

**O que os dados locais mostram (sem segredos)**
- `config/servers.json`: 63 entradas, todas habilitadas, todas com password, sem ids duplicados.
- São 58 hosts distintos para 63 instâncias. Há hosts com várias instâncias: SQLHDSQLT105 ×4, SQLHDSQLT103 ×2, SQLHDSQLT301 ×2.
- 1 entrada tem id diferente de host_instância: `SQLHDSSQLT301_I01` (host `SQLHDSQLT301`), com `sql_servername_alias`.
- No log de hoje, `logs/service_stderr.log`, está `[DEBUG] /api/v3/servers -> 63 servers (source=db)`. Em `service_stderr.log.1` há 482 ocorrências, todas de 63.

---

## (C) Dashboard: "Resumo Executivo → Instâncias" e cartão "Disponibilidade"

Não existe nenhum rótulo "configuradas" no portal nem na API. O total aparece em dois sítios:
- **"Instâncias"** no Resumo Executivo, `_repExecCard` (`portal.html:36828-36837`), montado no dashboard em `:37052` e no relatório em `:37115`.
- As linhas **Online / Offline** do cartão Disponibilidade (`portal.html:36901`, `:36907-36911`).

| Camada | Detalhe | ficheiro:linha |
|---|---|---|
| JS | `renderDashboardCardsContent` → `detectKpiEndpoint()` → `fetch(endpoint)`, guarda em `window.dashboardData` | `portal.html:37250-37263`, `:35393-35428` |
| Endpoint | `GET /api/server-info` devolve `kpi_endpoint`; depois **GET `/api/intelligence-kpis/dashboard`** | `watcherdb_main.py:1130-1136`; `api/routers/intelligence_kpis.py:940-969` |
| Recolha | `_do_collect_and_cache_dashboard`, fase 1 com `asyncio.gather` | `intelligence_kpis.py:852-914` |
| Serviço | `collect_instance_availability` e `collect_service_status` | `api/routers/intelligence/helpers.py:1224-1344`, `:1883-1948` |

**Fórmula efectiva** (sem filtro de ambiente)

```
Instâncias = ok_count + off_count                                   (portal.html:36832)

ok_count  = SELECT COUNT(DISTINCT Instance)
            FROM KPI_MSSQL_INST_AVAILABILITY_ACTIVE WHERE Is_Available = 1      (helpers.py:1228-1234)

off_count = SELECT COUNT(DISTINCT Instance)
            FROM KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WHERE Ping_OK = 0        (helpers.py:1238-1244, :1335)
          + nº de linhas de KPI_MSSQL_SERVICE_STATUS_AGG_VIEW com Services_Down_Count>0,
            dentro da janela de frescura, cuja Instance ainda não esteja na lista offline  (helpers.py:1889-1943)

Disponibilidade % = ok / (ok + off)                                 (portal.html:36833)
```

- **Com filtro de ambiente** (`_kpiAdvFilter.env`), soma `ok_by_env[e]` e `off_by_env[e]` (`portal.html:36831`).
  - `ok_by_env` vem de um LEFT JOIN com `KPI_MSSQL_INST_ENVS` (`helpers.py:1258-1272`).
  - `off_by_env` usa `_count_by_env` (`helpers.py:400-415`).
  - O bucket `Undefined` nunca entra na soma filtrada.
- **O denominador não é contagem de inventário.** Não usa `monitored_server`, `servers.json` nem o total da BD. São duas contagens em vistas KPI escritas pelo colector V1.

**Cache do dashboard**
- Em memória em `helpers._dashboard_cache`, TTL 60s, chave única (`helpers.py:41-67`). É preenchida em `format_dashboard_response` (`:2653`).
- Snapshot em disco `cache_dir()/dashboard_snapshot.json`, escrito de forma atómica, com validade máxima de 24h (`helpers.py:79-110`).
  - Com a cache fria, é servido com `stale=True` e dispara um refresh em background (`intelligence_kpis.py:961-965`).
- Pré-carregamento no arranque (`watcherdb_main.py:209-211`).
- **`POST /api/intelligence-kpis/refresh` limpa outra cache:** mexe no `TTLCache` local de `intelligence_kpis.py:41`, com chaves `data`/`timestamp` (`:1123-1125`), e não na de `helpers`. Não invalida o que o dashboard lê.
- JS:
  - retry do snapshot stale a cada 30s, até 8 vezes (`portal.html:33902-33905`, `:37350-37351`);
  - `cachedKpiEndpoint` (`:35395`);
  - `localStorage` com `kpiRefreshInterval` e `kpi-env-filter` (`:47663`, `:36882`). Este último não repõe `_kpiAdvFilter.env`, que começa vazio (`:36873`).

**Problemas no cálculo**
- **Mistura de unidades.** O offline conta `Server_Name` dos eventos, que segundo o comentário A1 são **hosts**, enquanto o inventário conta **instâncias** (`docs/context/A1_P1_P2_P3_2026-09-14.sql:242-244`; vista em `:262-313`; canónico antigo `database/INSTALACAO_COMPLETA_UNIFICADA.sql:9194-9250`). O online conta `Instance` (`HOST_INST`).
- **Sem dedup entre online e offline.** Uma instância pode entrar nos dois conjuntos. Isto é hipótese; na vista A1 só se excluem instâncias recolhidas nos últimos 10 min (`A1...sql:277-281,308`).
- **Condição de corrida.** `collect_instance_availability` e `collect_service_status` correm em paralelo (`intelligence_kpis.py:904,906`). O segundo soma `extra_off` a `instance_availability`, e o primeiro reescreve `off_count`/`instances` (`helpers.py:1335-1337`). O `off_count` final depende da ordem em que terminam.
- `ok_instances` é calculado e nunca usado (`helpers.py:1318-1333`).

---

## Consumidores de `sql_servers.json`

| ficheiro:linha | Uso | L/E | Em runtime? |
|---|---|---|---|
| `watcherdb_main.py:172-185` | arranque: carrega para `app.state.sql_servers_config` | L | sim |
| `watcherdb_main.py:1208-1225` | GET `/api/config/sql-servers` | L | sim (UI) |
| `watcherdb_main.py:1227-1375` | POST: grava e sincroniza `servers.json` | E | sim (UI) |
| `watcherdb_main.py:1944-1970` | `/api/monitoring/test-connection/{hostname}` (via app.state) | L | sim, mas não chamado pelo portal |
| `watcherdb_main.py:2297-2298`, `:2332-2333` | `/api/monitoring/space/dashboard` e `/alerts` (app.state) | L | sim |
| `watcherdb_main.py:2465-2466` | `/api/monitoring/backup/summary` (app.state) | L | sim |
| `watcherdb_main.py:3480-3499` | `/api/servers`: fallback se o inventário vier vazio | L | sim |
| `watcherdb_main.py:5390`, `:5430` | segundas definições das rotas space dashboard/alerts (`:5355`, `:5400`) | L | hipótese: rotas sombra, o FastAPI usa as primeiras (`:2285`, `:2318`) |
| `api/routers/alwayson.py:756-910` | `/instance-by-ag/{ag}`: fallback depois do `alwayson_inventory`; caminho **relativo** `Path("config/sql_servers.json")` | L | sim |
| `services/database_discovery_service.py:57`, `:286-302` | actualiza `databases[]` | E | só com `inventory_source=file` (retorna antes em `:267-270`) |
| `watcherdb/core/paths.py:96` | `bootstrap_config`: cria esqueleto se faltar | E | sim, idempotente |
| `watcherdb/api/routers/config.py:25-87` | GET/POST alternativos, caminho relativo, escrita não atómica | L/E | **não incluído** em `watcherdb_main.py` (sem `include_router`) |
| `watcherdb/api/health_router.py:178-188` | `_load_server_configs` relativo | L | só exportado em `watcherdb/api/__init__.py:7`; não incluído no main |
| `watcherdb_intelligence.py:1870`, `:2407-2546`, `:3015`, `:5796`, `:5836` | cópia antiga do main | L/E | legado, removido do build (`deploy/build.py:99`) |
| `scripts/initialize_configs.py:287-314` | gera a partir de Excel | E | script manual |
| `config/config.yaml:259` | `sql_servers_config` | ref. | não encontrei leitor desta chave |
| `deploy/build.py:423`, `deploy/watcherdb.spec:89` | excluído do bundle | — | build |
| `REGISTRO_IGAC/**`, `templates/legacy/**` | cópias de arquivo | — | não |

- `agent_jobs`, 2PC e colectores V1 **não estão neste repositório** (fazem parte do V1); não há referências a `sql_servers.json` em `collectors/` nem em `api/routers/collectors.py`.

---

## Host, instância, alias e listener

- **Instância:** `id = HOST_INST` (runbook `:43`); nome mostrado `HOST\INST` (`watcherdb_main.py:1176`).
  - Formato `HOST,porta`: não é usado em lado nenhum. A porta é só um campo, e o sync não a actualiza (`:1300-1303`).
- **Host físico:** a coluna `host` existe (`inventory_repo.py:89`). Nem a sidebar nem o dashboard agregam por host, com excepção do offline, que é por `Server_Name` (host).
- **Alias:** `sql_servername_alias` é lido (`inventory_repo.py:40,99`), mas **não é usado em nenhum match** em runtime. O caso `SQLHDSSQLT301_I01` tem a identidade partida entre dois nomes (`docs/context/PROMPT_V1_NOME_CORROMPIDO_SQLHDSSQLT301_2026-08-31.md:12-60`), incluindo duas linhas em `KPI_MSSQL_INST_ENVS`.
- **Listener AlwaysOn:**
  - `config/alwayson_inventory.json` tem `ag_servers` com 42 entradas (`ag_name`, `instance`, `listener`, `server`, `server_instance`) e é usado em `api/routers/alwayson.py:706-752`.
  - `has_alwayson`/`ag_name`/`ag_listener` vêm do inventário (`inventory_repo.py:96-98`).
  - Nenhum destes entra na contagem da sidebar nem do dashboard.

---

## Dúvidas e o que não encontrei

1. **Definição de `KPI_MSSQL_INST_AVAILABILITY_ACTIVE`:** não está no repositório. Só há a descrição "view UNION dos 6 BLUE/GREEN" em `docs/context/DESIGN_RECONCILE_INST_ENVS_2026-07-23.md:24-25`.
2. **Versão da vista `SERVER_OFFLINE_GROUPED_VIEW` em produção:** não sei se é a A1 (sem janela de 15 min, exclui recolhidas há ≤10 min) ou a do canónico (janela de 15 min). Isso muda o `off_count`.
3. **Os 62 da sidebar:** não se reproduzem neste ambiente, onde o log de hoje dá 63. Hipóteses a confirmar: (a) outro ambiente ou versão; (b) uma pesquisa activa; (c) na BD desse ambiente, uma instância com `enabled=0` ou `is_active=0`, ou sem credenciais locais (procurar no log a linha `[INVENTORY_REPO] N servidor(es) na BD sem credenciais`).
4. **Os 63 do dashboard:** é hipótese que venham de `ok + off` com unidades misturadas (host vs instância), ou de nomes duplicados como o SQLHDSSQLT301 com um e dois S. Não é inventário. Os logs de arranque mostram `Instances OK` a variar entre 50, 54, 62 e 63.
5. **Dados antigos na ACTIVE:** não verificado se a ACTIVE inclui instâncias desactivadas no canónico V1 cujas linhas ainda não foram truncadas no swap.
6. **Caminhos relativos em serviço Windows:** `connection_pool.py:200` e `alwayson.py:758` usam caminhos relativos, e não há `os.chdir` no código. Com CWD em System32 podem falhar em silêncio. Hipótese, depende de como o serviço é lançado.
