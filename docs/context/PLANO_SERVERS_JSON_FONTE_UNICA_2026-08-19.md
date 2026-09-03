# PLANO — `servers.json` como fonte única de verdade dos servidores (e das suas databases)

Data: 2026-08-19 | Autor: Claude (orquestrador) | Estado: **PLANO — zero código alterado**
Gates consultados: `sql-deep-reviewer` (modelo de dados, parecer recebido) · `watcherdb-v1-intel-specialist` (veto holder da infra partilhada — parecer na secção 11)
Levantamento: 2 agentes Explore (V3.3 + V1 Intelligence), leitura directa dos 3 `servers.json`, `sync_servers_from_json.py`, `reconcile_inst_envs.py`, `ServerManager`, canonical `INSTALACAO_COMPLETA_UNIFICADA.sql`, `DESIGN_RECONCILE_INST_ENVS_2026-07-23.md`, CONTEXT.md (entradas 23/07 → 18/08).

> **Premissa do pedido, assumida literalmente:** `servers.json` é a ÚNICA fonte de verdade para servidores e para as suas "tabelas". No ficheiro real a única sub-lista por servidor é `databases[]` (não existe chave `tables`). Este plano trata **"tabelas" = `databases[]`** (ver Q1 em §12 — se o owner quiser dizer outra coisa, o modelo acomoda, mas a semântica de coleta muda).

---

## 0. Resumo executivo

**Problema medido.** Hoje a lista de servidores monitorizados vive em **≥ 10 sítios que não concordam entre si**: **4** cópias físicas de `servers.json` (V1 raiz 63 / V1 serviço DEPRECATED / V3.3 62 com `databases[]` / **V6**, com chaves de cifra diferentes), `sql_servers.json` (95, gerado de Excel em 2025-11, **ainda lido por 2 collectors V1** e por 4 módulos V3.3), `alwayson_inventory.json` (42), `config.yaml` do collector (`inventory.environments.server_count` 50/21/13), `[metadata].[server_config]` (BD, escrita pelo sync diário, lida por zero código V3.3), `KPI_MSSQL_INST_ENVS` (BD, driving table de ~40 JOINs do portal, povoada por 5 caminhos), `KPI_MSSQL_DISK_USAGE_STG` usada como inventário por 1 collector, tabelas-fantasma `dbo.servers` / `dbo.SERVER_INVENTORY` / `metadata.servers` (sem DDL), **9 env_maps + 2 inferências por nome** para decidir o *ambiente*, listas hardcoded em `watcherdb_main.py` (4×), `_query_jobs_from_servers` que corta a frota a `servers[:20]`, e um bug latente (`collect_kpi` QA→`'qa'` — collector desactivado no YAML, sem impacto em produção). O drift já produziu incidentes reais (SS301 12 dias, SQLHDSQLT301 "servidor não encontrado", 85 rows Env fora da convenção, "1 OFF" permanente). **Facto que muda o desenho:** `databases[]` não tem hoje nenhum consumidor na coleta — os KPIs per-DB enumeram `sys.databases` ao vivo dentro do T-SQL.

**Solução.** Um único `servers.json` canónico (o da raiz do collector V1), lido por **um único loader validado** (`InventoryProvider`, evolução do `ServerManager`), que a cada ciclo calcula um hash, carrega staging e chama **uma sproc set-based idempotente** (`metadata.usp_sync_monitored_servers`) que mantém 2 tabelas novas de inventário (`metadata.monitored_server`, `metadata.monitored_server_database`) + 2 de metadados (`server_sync_run`, `server_sync_audit`), projecta para as tabelas legadas (`server_config` row base, `KPI_MSSQL_INST_ENVS`) durante a transição, e deixa a remoção física ao `usp_reconcile_inst_envs` existente (guarda 30 d). **Todos os collectors consomem o mesmo snapshot validado que foi para a BD** (mesmo `run_id`), e **o portal V3.3 lê o inventário da BD** (deixa de ter inventário próprio; fica só com credenciais locais). As fontes legadas são desligadas por *feature flag* + período de sombra com comparação diária, nunca por corte a seco.

**Porque não é trivial.** (1) A BD é partilhada e tem veto do V1 — **exercido** num ponto: `databases[]` **não** pode tornar-se scope da coleta (fica catálogo autoritativo de inventário; a coleta per-DB continua ao vivo; exclusões via `WDB_KPI_MUTE`) — o owner decide se aceita o consenso ou reabre (Q2); (2) há 4 cifras de credenciais distintas — o inventário pode ser partilhado, o segredo não (V3.3/V6 ligam directamente aos monitorizados → mirror local de credenciais regenerado pela sync); (3) `INST_ENVS` está em ~40 JOINs e numa driving table — tem de continuar tabela física; (4) trocar 7+ pontos de leitura pelo provider é a maior superfície de regressão → wave própria, depois de a sync queimar sozinha; (5) há dois installers/canonical a actualizar (fresh-install repair em curso).

**Custo/ordem.** 8 etapas (§13), as 4 primeiras sem risco operacional (contrato + DDL novo + sync em *dry-run* + sombra). Ponto de não-retorno só na etapa 5 (collectors passam a ler o provider) — em wave própria. Rollback por flag em todas. Gates: `sql-deep-reviewer` (modelo adoptado) e `watcherdb-v1-intel-specialist` (GO-COM-CONDIÇÕES, 5 bloqueantes pre-ship, 1 VETO em Q2).

---

## 1. Levantamento — onde servidores/databases são definidos, duplicados ou consumidos

### 1.1 As três cópias de `servers.json` (medido 2026-08-19)

| Cópia | Servidores | `databases[]` | Cifra | Estado |
|---|---|---|---|---|
| `WATCHERDB INTELLIGENCE V1/config/servers.json` | 63 (OATXP01 só aqui) | **não** | `EncryptionManager` (`.encryption_key`) | **canónico do collector** (fix 24/07 + D1 05/08) |
| `V1/services/collector_service/config/servers.json.DEPRECATED_20260805` | 95 (stale) | não | idem | renomeado, deixou de ser lido |
| `WATCHERDB_V3.3/config/servers.json` | 62 | **sim** (discovery V3.3, 2026-08-18) | `services/secrets.py` DPAPI | gitignored; lida por 9 leitores V3.3 |

Diferenças estruturais: V1 tem `_enabled_note`/`_port_note`; V3.3 tem `databases[]`, `databases_discovered_at`, `database_count`, `sql_servername_alias` (1 entry, **nenhum .py lê**). Ids iguais (62 ∩ 62), sem duplicados em nenhuma. `enabled=false`: 0 em ambas hoje. Driver legacy `"SQL Server"` em 62/62 no V3.3 (inerte — `connection_pool` usa `settings.odbc_driver`).

### 1.2 V1 Intelligence (collector) — quem define/lê

| Onde | O quê |
|---|---|
| `watcherdb_intelligence/collectors/server_manager.py:46-202` | `ServerManager` — único loader estruturado; **não valida schema, não detecta duplicados, `use_windows_auth` default `True` se a chave faltar (:154), `environment` default `'production'` (:153), `enabled` default `True` (:156 — só 2/63 entradas têm a chave)**; aceita `id`/`server_id` e `host`/`server`; decripta Fernet (`EncryptionManager`, `.encryption_key` na raiz, **gera chave nova se ausente** `server_collector.py:53-58`); **sem cache/singleton — 33 instanciações re-lêem o ficheiro** (30 fora de testes). |
| `scripts/collectors/base_collector.py:184-218` | **Caminho dominante**: `get_servers(environment)` → `server_manager.get_servers(enabled_only=True)` + `env_map {PRD→production, QA→quality, TST→test, ALL}` + `FILTER_ALWAYSON_ONLY` (4 collectors AG). ~39 collectors herdam daqui (os 50 ficheiros em `services/collector_service/collectors/` são adapters finos que importam `scripts/collectors/*.py`). `priority` **nunca** é usado. `:593-595` swap com `@servers_collected=len(df)` (linhas, não servidores). |
| `scripts/collectors/collect_os_cpu.py:60-66`, `collect_os_disk.py:93-97`, `collect_os_disk_perf.py:60-66`, `collect_os_memory.py:60-66`, `collect_deadlocks.py:95-100`, `collect_errorlog.py:190-202`, `collect_db_security_map.py:343` | 6+1 collectors com `get_servers()` **próprio** — reimplementam o mesmo `env_map` (7 cópias em Python). |
| `scripts/collectors/collect_disk_unallocated.py:635-665` | lista de servidores derivada **da BD** (`SELECT DISTINCT Instance FROM KPI_MSSQL_DISK_USAGE_STG`) com ambiente inferido por `LIKE '%PRD%'` — coleta servidores já removidos do JSON enquanto houver linhas na STG; `:64-95` decrypt próprio com **key path errado**. |
| `services/collector_service/collectors/collect_kpi.py:147-152` | `env_mapping` mapeia `'QA'→'qa'` mas o JSON usa `'quality'` → seleccionaria 0 dos 15 servidores de qualidade. **CORRECÇÃO (verificado 19/08 tarde):** as 3 tasks `collect_kpi_*` estão `enabled: false` no `config.yaml:65-109` ("duplicado com estrutura de banco incompatível") — é **bug latente em código desactivado**, sem perda de dados em produção. Fix de 1 linha mantém-se (para não ressuscitar partido), sem Restart necessário. |
| `watcherdb_intelligence/storage/servers_repository.py:30-199` + `api/v1/servers.py` | INSERT/SELECT em `[metadata].[servers]`/`[metadata].[agents]` — **sem DDL em lado nenhum** (código morto/não instalado). |
| `config/SERVIDORES_DESABILITADOS.md` | lista de servidores desactivados mantida em **Markdown**; o JSON tem 0 `enabled:false`. |
| `config/servers.json` (raiz) | **nenhum processo automático escreve** (0 discovery; `databases[]` 0/63); 4 escritores manuais/one-shot (`update_servers_alwayson.py` ← Excel, `configurar_sql_auth_todos_servidores.py`, `fix_master_auth.py`, `credential_manager_v2._scrub_servers_json_for`). `environment` ∈ {production 42, quality 15, test 6}; `priority`=1 em todos (campo morto). |
| `scripts/sync_servers_from_json.py` | JSON → `[metadata].[server_config]` (upsert row-a-row + desactiva ausentes :185-202) → `KPI_MSSQL_INST_ENVS` (UPDATE/INSERT, mapping PRD/QLT/TST/DEV :211-247). |
| `services/collector_service/collectors/reconcile_inst_envs.py` | adapter hourly com date-gate ≥03h (1×/dia): chama o sync acima + `EXEC dbo.usp_reconcile_inst_envs @GraceDays=30, @DryRun=0` (flip 27/07). `DRY_RUN` hardcoded no .py (:49). |
| `dbo.usp_reconcile_inst_envs` | dedupa `server_config` (ROW_NUMBER), UPDATE/INSERT/DELETE-com-guarda em INST_ENVS; **não está em `database/*.sql` do V3.3** (só no design doc). |
| `collectors/collect_kpi.py:129-163` | lê raiz directamente (`json.load`), filtra `environment`+`enabled`, `env_mapping` local PRD/QA/QLT/TST. |
| `collectors/collect_server_ping.py:340-348, 448` | lê raiz + porta aprendida `WDB_INSTANCE_TCP_PORT`. |
| `collectors/collect_agent_jobs.py:165-174, 276` e `collect_2pc_transactions.py:117-126, 239` | **lêem `config/sql_servers.json` (95, Excel 2025-11)** via `config.yaml inventory.sql_servers_file` para a lista de servidores e `servers.json` só para credenciais master. |
| `collectors/collect_disk_unallocated.py:28,49` | `get_servers(environment)` importado do pacote (lista própria). |
| `service.py:519-541` | poller "Run now": master via `ServerManager()` (FIND-108 já corrigido). |
| `services/collector_service/config.yaml:1691-1705` | `inventory.servers_file`, `sql_servers_file`, `environments.{PRD,QA,TST}.server_count` (50/21/13 — lista paralela de contagens). |
| `config/config.yaml:15-27` | bloco `database.sqlserver` com **password em claro** (achado colateral, fora de scope mas a registar). |
| `watcherdb_intelligence/collectors/async_data_collector.py:350,508,639` e `data_collector.py` | coleta por database via `sys.databases` **ao vivo** (backups, DB availability/mirroring, lista de DBs) — não há filtro por `databases[]`. |
| `database/INSTALACAO_COMPLETA_UNIFICADA.sql` (V1, 16.9k linhas) | :366-382 `server_config` DDL; :1748-1757 `DROP`+`CREATE` INST_ENVS; :6272-6300 seed INST_ENVS ← `server_config` com mapping **divergente** (`PROD/TEST` vs `PRD/TST` do sync); :15860-16040 `usp_reconcile_inst_envs`; :15552-15600 `WDB_COLLECTION_SCHEDULE_META`; :16290-16357 `WDB_INSTANCE_TCP_PORT`/`HOST_IP_CACHE`; `#ServersToCollect` de `dbo.SERVER_INVENTORY` (sem DDL). **INST_ENVS é povoada por 5 caminhos**: sync, seed, reconcile, `CORRIGIR_AMBIENTES_INST_ENVS.sql` (pattern do nome), `POPULAR_INST_ENVS_COMPLETO.sql` (varre tabelas KPI). `collector_run_requests`/`collector_manual_runs` usadas por `service.py` **sem DDL**. |
| `services/collector_service/config.yaml` | **132 tasks** com `environment` literal (44 PRD / 40 QA / 40 TST / 7 ALL) — o ambiente é partição da task, não vem do JSON (aceitável: não define servidores, só filtra). |
| `scripts/install_windows_service.ps1:10-11,57`, `collect/setup_all_tasks.ps1`, `collect/run_*.ps1` | Task Scheduler paralelo com `$ProjectPath` **hardcoded para caminho obsoleto**; ~30 tarefas `WatcherDB - <KPI> <ENV>` com `$ENVIRONMENT` literal. |
| Testes V1 | **zero testes** de `ServerManager`, `sync_servers_from_json`, `base_collector.get_servers()`, `server_config`; `test_credential_manager_v2.py:567-586` testa explicitamente a existência de **2** servers.json; `test_2pc_collector.py:62` usa `sql_servers.json`. |

### 1.3 V3.3 portal — quem define/lê (relatório Explore, 73 tool-uses)

- **9 leitores independentes de `servers.json`**; 8 usam `Path("config/servers.json")` relativo ao CWD (quebra como Windows Service) e só `watcherdb_main.py:110` usa o resolver 3-tier: `watcherdb_main.py:1130-1187` (`/api/v3/servers`, sidebar, precisa de `databases[]`), `:3405-3433` (`/api/servers`), `api/connection_pool.py:200,408-479` (cache de credenciais por mtime), `api/routers/intelligence/helpers.py:470-481` e `intelligence_kpis.py:511-522` (**cópia literal** `_load_monitored_servers`), `network_diagnostics.py:35-48`, `modules/monitoring/monitoring.py:765-787`, `modules/monitoring/watcherdb_alwayson_check.py:123-145`, `services/database_discovery_service.py:56,194-198`, `watcherdb_intelligence.py:1847-1872` (legacy).
- **Escritores**: `database_discovery_service.py:257-271` (injecta `databases[]`), `watcherdb_main.py:1266-1345` (sync `sql_servers.json → servers.json` no `POST /api/config/sql-servers`, fail-open, sem testes), `deploy/farm_inventory_parser.py:358-372` (gera canónico no install), `watcherdb/core/paths.py:84-105` (skeleton).
- **Listas paralelas**: `sql_servers.json` (95; `watcherdb_main.py:173` arranca o `SQLServerMonitoring` **com este ficheiro**, não com `servers.json`), `alwayson_inventory.json` (42), 9 backups divergentes em `config/`, hardcoded `watcherdb_main.py:4450-4451, 4690-4906` (4× lista de 3 instâncias), `alembic/env.py:40` + `watcherdb/api/routers/space.py:37` (`INTELLIGENCE_SERVER` default hardcoded), `modules/collector_health/config_loader.py:28-30` (path absoluto da máquina do dev).
- **BD**: `server_config` (**zero leitores Python no V3.3**), `KPI_MSSQL_INST_ENVS` (driving table `live_monitoring.py:963,1271-1275`; ~40 LEFT JOINs em `helpers.py`), `dbo.servers` em `api/routers/htmx.py:35-40` (**tabela sem DDL, router registado**), `WDB_INSTANCE_TCP_PORT`/`WDB_HOST_IP_CACHE` (`connection_pool.py:558,568`), `OVERVIEW_INSTANCE_SNAPSHOT`.
- **Ambiente decidido por 5 mecanismos**: campo JSON; `INST_ENVS.Env`; `_infer_env_from_instance()` por substring do hostname (`helpers.py:379-390`, duplicado em `intelligence_kpis.py:505-508` e em SQL `helpers.py:2423`); `env_map` só em `intelligence_kpis.py:682`; `CASE` SQL `helpers.py:974-985`.
- **Caches**: `_creds_cache` (mtime), `_DATABASES_CACHE`, `app.state.sql_servers_config` (congelado no arranque).
- **Jobs**: `_query_jobs_from_servers` (`intelligence_kpis.py:659-675`) **corta a `servers[:20]`**; `_background_prewarm` reescreve os 2 JSONs 5 min após o arranque.
- **Testes**: zero cobrem o sync sql→servers, `_update_json_files()` ou `_load_credentials_cache()`.

### 1.4 Mapa de duplicação (quem é fonte de quê, hoje)

```
Excel TAP_SQL_Server_Inventory.xlsx ──► sql_servers.json (V1 e V3.3) ──► collect_agent_jobs / collect_2pc (V1)
                                                                       └► SQLServerMonitoring arranque (V3.3:173), alwayson.py
CSV cliente ──► farm_inventory_parser ──► servers.json (install)
servers.json V1 raiz ──► ServerManager ──► collect_kpi / ping / reconcile ──► server_config ──► INST_ENVS ──► portal (40 JOINs)
servers.json V3.3 ◄── discovery V3.3 (databases[]) ──► /api/v3/servers, connection_pool creds, 7 outros leitores
config.yaml inventory.environments.server_count ──► (contagens paralelas, ninguém reconcilia)
hardcoded (watcherdb_main 4×, alembic, space.py) ──► endpoints específicos
```

---

## 2. Arquitectura proposta

```
            ┌────────────────────────────────────────────────────────────────┐
            │  config/servers.json  (V1 raiz — ÚNICO ficheiro canónico)       │
            │  master_server + monitored_servers[{..., databases[]}]          │
            └───────────────┬────────────────────────────────────────────────┘
                            │ lê + valida (schema, dups, defaults explícitos)
                            ▼
            ┌────────────────────────────────────────────────────────────────┐
            │  InventoryProvider (evolução do ServerManager, 1 classe)        │
            │  · snapshot imutável {servers, databases, source_hash, mtime}  │
            │  · credenciais resolvidas localmente (nunca vão à BD)          │
            │  · erros de validação → REJECT por item (nunca aborta tudo)    │
            └──────┬────────────────────────────────┬────────────────────────┘
                   │ a cada ciclo (5-15 min)         │ mesmo snapshot (run_id)
                   ▼                                 ▼
   ┌───────────────────────────────┐      ┌──────────────────────────────────┐
   │ InventorySync (adapter)       │      │ Collectors (kpi, ping, jobs, 2pc,│
   │ hash == última run OK? → SKIP │      │ disk, alwayson, async collector) │
   │ senão: staging(run_id) +      │      │ iteram provider.servers(enabled) │
   │ EXEC usp_sync_monitored_servers│     │ + provider.databases(server)     │
   └──────────────┬────────────────┘      └──────────────────────────────────┘
                  ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ WatcherDB_Intelligence                                                  │
   │  metadata.monitored_server ──1:N── metadata.monitored_server_database   │
   │  metadata.server_sync_run  ──1:N── metadata.server_sync_audit           │
   │  projecções (transição): server_config row-base · KPI_MSSQL_INST_ENVS   │
   │  usp_reconcile_inst_envs (existente) apaga INST_ENVS com removed_at>30d │
   └──────────────┬─────────────────────────────────────────────────────────┘
                  ▼  SELECT (sql_monitoring)
   ┌────────────────────────────────────────────────────────────────────────┐
   │ V3.3 portal: /api/v3/servers, sidebar, creds lookup por instance_id,   │
   │ discovery (escreve para o canónico partilhado OU deixa de escrever)    │
   └────────────────────────────────────────────────────────────────────────┘
```

Princípios: (1) **um ficheiro, um loader, uma sproc**; (2) inventário na BD, **segredo nunca** (3 cifras distintas, backups da Intelligence, leitores V5/V6); (3) BD é *projecção* do JSON — nunca se edita inventário na BD à mão (a sync repõe); (4) remoção é sempre soft (`is_active=0, removed_at`) e a remoção física fica com o reconcile existente; (5) legado morre por flag + sombra + prova, não por corte.

---

## 3. Modelo de dados (BD `WatcherDB_Intelligence`, schema `metadata`)

Parecer `sql-deep-reviewer` adoptado integralmente; ajustes meus marcados ⚑.

| Tabela | Chave | Campos principais | Índices | Notas |
|---|---|---|---|---|
| `metadata.monitored_server` | PK `server_id INT IDENTITY`; UQ `(tenant_id, instance_id VARCHAR(64))` | host, instance_name, port, environment (CHECK production/quality/test/development), priority, description, **enabled** (flag do JSON), **is_active** (presente na fonte), auth_mode (SQL/WINDOWS), login_name (**sem password**), driver, has_alwayson, ag_name, ag_listener, sql_servername_alias, **source_hash CHAR(64)**, first_seen_at, last_seen_in_source_at, removed_at, last_sync_run_id, updated_at | `IX_monitored_server_active (is_active, environment) INCLUDE (instance_id, host, port, enabled)` | `instance_id` 64 (=PK de INST_ENVS; >64 = REJECT, nunca truncar). CHECK `(is_active=1 AND removed_at IS NULL) OR is_active=0`. |
| `metadata.monitored_server_database` | PK clustered `(server_id, database_name NVARCHAR(128))`; FK server | database_id (atributo, muda em restore), state, recovery_model, is_read_only, is_accessible, compatibility_level, is_active, first_seen_at, last_seen_in_source_at, removed_at, updated_at | `IX_msd_database_name (database_name) INCLUDE (is_active, state)`; filtrado `IX_msd_removed (removed_at) WHERE removed_at IS NOT NULL` | Collation default da BD (CI, igual às KPI_*); colisão de caixa em instância CS → REJECT `CASE_COLLISION`. |
| `metadata.server_sync_run` | PK `run_id BIGINT IDENTITY` | started_at, finished_at, **last_checked_at** (avançado pelos SKIP, sem row nova), source_path, source_hash, source_mtime, contadores (servers_in_source/inserted/updated/deactivated/reactivated/rejected; dbs_*), status (RUNNING/OK/PARTIAL/FAILED/SKIPPED_UNCHANGED), error_message, host_name, pid, dry_run | `IX_ssr_status_started (status, started_at DESC) INCLUDE (source_hash)` | Retenção 180 d. |
| `metadata.server_sync_audit` | PK `audit_id`; FK run | entity_type (SERVER/DATABASE), entity_key, action (INSERT/UPDATE/DEACTIVATE/REACTIVATE/REJECT), changed_cols, before_json/after_json (**só SERVER+UPDATE**), reason, logged_at | `(run_id, entity_type)`; `(entity_type, entity_key, logged_at DESC)` | Retenção 90 d; DATABASE só action+reason (volume 100×). |
| `metadata.monitored_server_stg` / `_database_stg` | PK `(run_id, instance_id[, database_name])` | colunas espelho, `instance_id VARCHAR(200)` de propósito (validação de tamanho na sproc) | — | Keyed por `run_id`, **sem TRUNCATE** (sem ALTER permission, sem contenção); carga via `pyodbc fast_executemany`; limpeza `run_id < @RunId` dentro da sproc. |
| `metadata.usp_sync_monitored_servers` | `@RunId, @DryRun=1, @AllowMassDeactivatePct=20, @MinServersInSource=1, @ProjectToServerConfig=1, @RetentionRunDays=180, @RetentionAuditDays=90` | set-based FULL OUTER JOIN staging×alvo → #srv/#db com acção; guarda staging vazia → FAILED sem mutar; guarda frota → PARTIAL (salta DEACTIVATE); transacção curta só-DML + `sp_getapplock 'WDB_SYNC_MONITORED_SERVERS'` + `DEADLOCK_PRIORITY LOW`; projecção INST_ENVS (UPDATE/INSERT, **sem DELETE**) e `server_config` row base (`config_key IS NULL`); purge em lotes TOP(5000) | — | DDL draft completo no parecer (anexo A). ⚑ Piso da casa é SQL 2014+: substituir `CREATE OR ALTER` por `IF OBJECT_ID … DROP` + `CREATE`, e `FOR JSON PATH` (2016+) por concatenação/`STUFF` ou confirmar versão do host `SQLHDSTST505\I01` antes do DDL. |

Relação com o legado:
- `[metadata].[server_config]` **mantém-se** (EAV legítimo: `cross_server_correlation.py:212-228` lê `config_key IN ('storage_lun','network_switch','datacenter','availability_zone')`); a sync escreve-lhe a row base como projecção enquanto houver leitores (`collect_data_async`, `apply_grants_all_servers.py`, reconcile). A UQ `(tenant_id, instance_id, config_key)` com NULL único já garante 1 row base/instância — **não mexer**.
- `KPI_MSSQL_INST_ENVS` **continua tabela física** (não view): 40 LEFT JOINs + driving table + lida durante o swap BLUE/GREEN — uma view acoplaria a janela de escrita da sync ao swap. `usp_reconcile_inst_envs` passa a ler `monitored_server (is_active, removed_at)` em vez de dedupar `server_config` (o CTE ROW_NUMBER cai) — 1 alteração à sproc existente.
- Mapeamento de ambiente **num único CASE** (production→PRD, quality→QLT, test→TST, development→DEV; **desconhecido = REJECT**, não default PRD).
- Zero FK para `KPI_*`/HIST. Soft-delete em ambos; purge físico de databases opcional >365 d.
- Identidade: a **mesma** que hoje faz INSERT/UPDATE/DELETE em `server_config` e executa swap/reconcile — as credenciais `master_server` do `servers.json` canónico do collector (gate V1 #6). GRANT SELECT/INSERT/UPDATE/DELETE nas `metadata.*` novas + EXECUTE na sproc a esse login; nos servidores monitorizados `sql_monitoring` continua SELECT-only (inalterado). Login dedicado fica para a Frente 2 (Q6).

---

## 4. Leitura e validação do `servers.json`

Ponto único: `InventoryProvider.load(path) -> InventorySnapshot` (substitui `ServerManager._load_config` e TODAS as leituras `json.load` directas).

| Regra | Comportamento | Registo |
|---|---|---|
| Ficheiro ausente / JSON inválido / top-level sem `monitored_servers` lista | **snapshot inválido** → sync não corre (run `FAILED`, `error_message`), coleta usa **último snapshot válido em memória** (ver §6 modo de falha); se não houver nenhum (arranque), serviço arranca em modo degradado e re-tenta a cada ciclo | `[INVENTORY_INVALID]` ERROR + contador |
| `master_server` sem `use_windows_auth:false` + username/password | inválido (Regra de Ouro #2; já é `raise` no sync e no poller) | `[INVENTORY_INVALID]` |
| Campos obrigatórios por servidor: `id`, `host`, `environment`, `enabled` (**explícito**), `port` | item sem `id`/`host` → REJECT `MISSING_REQUIRED`; `enabled` em falta → REJECT `ENABLED_NOT_EXPLICIT` (hoje default `True` silencioso é a causa do "1 OFF" permanente — o plano exige explicitação; período de transição: o provider aceita default `True` mas **emite WARN por item** durante N dias, depois vira REJECT por flag) | audit `REJECT` + reason |
| `environment` fora de {production, quality, test, development} | REJECT `BAD_ENV` (nada de default `production`) | idem |
| `id` com >64 chars, com `\`, espaços ou minúsculas | REJECT `ID_TOO_LONG` / `ID_FORMAT` (convenção `HOST_INST`, upper; hoje `\`→`_` é normalizado — manter a normalização mas **avisar**) | idem |
| `id` duplicado | fica a 1.ª ocorrência, 2.ª REJECT `DUP_ID` (a PK da staging rebentaria — validar antes) | idem |
| `host+instance` duplicados com ids diferentes (alias) | REJECT `DUP_HOST_INSTANCE` (evita duas coletas à mesma instância) | idem |
| `port` não inteiro ou fora 1-65535; `priority` não inteiro | REJECT `BAD_PORT` / `BAD_PRIORITY` | idem |
| `password` sem prefixo `encrypted:` | WARN `PLAINTEXT_SECRET` (não rejeita — mas conta como achado de segurança) | log |
| `databases[]` ausente | servidor válido, 0 databases (**comportamento durante a transição**: ver Q2 — coleta por DB não restringe) | — |
| `databases[]` com `name` duplicado (CI) | 2.ª REJECT `DUP_DB` / `CASE_COLLISION` | audit |
| `databases[].name` vazio ou >128 | REJECT `BAD_DB_NAME` | audit |
| Chaves desconhecidas (`_enabled_note`, `location`…) | ignoradas, **listadas 1× por run** em WARN (detecta typos como `enable:`) | log |
| Voláteis (`databases_discovered_at`, `database_count`, notas `_*`) | **excluídos do hash** (senão a discovery diária invalida o SKIP) | — |

Implementação: dataclasses + validação manual (evitar dependência nova `pydantic` no collector — confirmar se já existe no requirements do V1; se existir, usar). Schema JSON formal (`config/servers.schema.json`) versionado no repo e usado pelos testes e pelo `farm_inventory_parser` do installer V3.3 (mesmo contrato nas duas pontas).

---

## 5. Sincronização idempotente JSON → BD

Algoritmo por ciclo (adapter `inventory_sync`, §6.1):

1. `snap = provider.load()`; se inválido → run FAILED (sem staging), **fim**.
2. `h = sha256(canonical_json(snap))` (sort_keys, sem voláteis). `SELECT TOP 1 source_hash FROM server_sync_run WHERE status IN ('OK','PARTIAL') ORDER BY run_id DESC`. Se igual **e** última run completa há <24 h → `UPDATE last_checked_at` nessa run, `SKIPPED_UNCHANGED`, **fim** (não insere row, não toca staging).
3. `INSERT server_sync_run (status='RUNNING', source_path, source_hash, source_mtime, host_name, pid, dry_run)` → `run_id`.
4. `fast_executemany` para `monitored_server_stg` e `monitored_server_database_stg` com `run_id` (só itens válidos; os REJECT do Python vão directo ao audit com `run_id`).
5. `EXEC metadata.usp_sync_monitored_servers @RunId, @DryRun=<flag>, @AllowMassDeactivatePct=20` — a sproc:
   - classifica SERVER: INSERT / UPDATE (hash diferente) / REACTIVATE (is_active=0 e presente) / DEACTIVATE (activo e **ausente desta run**) / NOOP / REJECT (>64, BAD_ENV);
   - **guarda de frota**: se DEACTIVATE > 20 % dos activos → aplica INSERT/UPDATE, **salta** as desactivações, status PARTIAL + reason `MASS_DEACTIVATE_GUARD` (protege contra JSON parcialmente editado);
   - classifica DATABASE por `(server_id, database_name)` com a mesma lógica; DEACTIVATE só para servidores **presentes** na run (servidor ausente → as suas DBs herdam `removed_at` do servidor, não são reavaliadas);
   - `@DryRun=1` → devolve contagens + candidatos e **sai sem lock nem transacção**;
   - execução: `BEGIN TRAN` + applock + UPDATE/REACTIVATE/INSERT/DEACTIVATE/NOOP(last_seen) + projecções INST_ENVS (UPDATE/INSERT) e `server_config` row base + audit (before/after só UPDATE de SERVER) + contadores + `COMMIT`; purge em lotes **só na run das 03 h** (não em todas).
6. Python lê os 2 result sets e loga integralmente (audit trail no `collectors.log`) + actualiza heartbeat (`WDB_COLLECTION_SCHEDULE_META`, padrão D4).
7. **Run completa forçada 1×/24 h** mesmo com hash igual (cura edições manuais na BD e `last_seen_in_source_at`).

Idempotência: 2.ª execução consecutiva = 0/0/0 (teste obrigatório). Regra escrita na sproc e nos testes: **desactivação só por "ausente da run processada", nunca por idade de `last_seen_in_source_at`** (um período de SKIPs nunca pode desactivar a frota).

Auditoria/erros: `server_sync_run` (1 row por run real), `server_sync_audit` (1 row por acção), log estruturado `[INVENTORY_SYNC] run_id=… status=… ins/upd/deact/react/rej=…`, WARN por REJECT com reason, ERROR em FAILED. Consulta típica de suporte: "porque desapareceu X do portal ontem?" → `SELECT … FROM server_sync_audit WHERE entity_key='X' ORDER BY logged_at DESC`.

---

## 6. Alterações no fluxo de coleta

### 6.1 Collector service (V1)
- **Novo collector leve** `collectors/sync_monitored_servers.py` (`SyncMonitoredServers(BaseCollector)`, nome alinhado com o parecer V1), `config.yaml`: `interval_minutes: 10`, `executor: default`, `environment: ALL`, `dry_run: true` no arranque (**no YAML, não hardcoded** — finding do gate 27/07), `full_run_hour: 3`, **heartbeat em `WDB_COLLECTION_SCHEDULE_META`** (seed `('metadata.monitored_server','sync_monitored_servers',10,'HEARTBEAT')`, padrão try/except-warn de `reconcile_inst_envs.py:128-140` — condição 4 do gate). O `reconcile_inst_envs.py` **deixa de chamar** `sync_servers_to_database()` e fica só com o EXEC da reconcile (1×/dia, como hoje); a reconcile lê `removed_at`.
- **Ordem vs swap BLUE/GREEN**: `metadata.monitored_server*` está fora de `KPI_STG_ACTIVE_TABLE`/BLUE-GREEN → **zero overlap de lock** (gate V1 #3); a projecção INST_ENVS é ≤63 rows numa transacção curta. Staggering do 1.º disparo (já é o padrão do scheduler) chega como boa prática.
- **Contrato de consumo**: `InventoryProvider.current()` devolve o **mesmo snapshot** que foi (ou tentou ir) para a BD, com `run_id` e `synced: bool`. Métodos: `servers(enabled_only=True, environment=None)`, `databases(server_id, active_only=True)`, `master()`, `credentials(server_id)` (resolve localmente; nunca na BD). Cache por `mtime`+hash; thread-safe; recarrega só quando o ficheiro muda.
- **Substituições** (wave própria E5, depois de E3/E4 queimarem — condição do gate #4; todas passam pelo provider, zero `json.load` de inventário fora dele): **ponto de estrangulamento** `scripts/collectors/base_collector.py:184-218` (`get_servers` — cobre ~39 collectors de uma vez, `env_map` único); os 6+1 `get_servers()` próprios (`collect_os_cpu/os_disk/os_disk_perf/os_memory/deadlocks/errorlog/db_security_map`) passam a delegar na base; `collect_kpi.py:129-163` (remove `env_mapping` local e o bug `QA→'qa'`), `collect_server_ping.py:340-366`, `collect_agent_jobs.py:165-174` e `collect_2pc_transactions.py:117-126` (**deixam `sql_servers.json`** — só após diff 95 vs 63, condição #3), `collect_disk_unallocated.py:635-665` (deixa de derivar a frota da STG) e `:64-95` (decrypt próprio com key path errado → provider), `collect_inst_availability.py:244`, `AsyncServerCollector`/`collect_data_async.py:349`, `collect_alwayson.py:370`, `reconcile_inst_envs.py`, `check_availability_coverage_gap.py`, `collect_scheduled_tasks_audit.py`, `service.py:528` (master), `credential_manager_v2.py:462-511` (lista `servers_json_paths` → 1 path). Testar **collector a collector** pós-corte (risco residual do gate).
- **Coleta por database** (sprocs `usp_Collect_Backups/DB_Availability/Filegroup_Usage/TLog_Usage` + `async_data_collector.py:350,508,639`): **VETO do veto holder** a `databases[]` como scope (§11.2 #2). Plano consensual: `databases[]` é **catálogo autoritativo de inventário** (BD + UI), a coleta per-DB continua por `sys.databases` ao vivo; exclusões per-DB, se precisas, via `WDB_KPI_MUTE` + coluna `Database` (opt-out). O collector apenas **compara** o que viu ao vivo com o catálogo e loga `[DB_NOT_IN_CATALOG]`/`[DB_CATALOG_STALE]` (1 linha por servidor/ciclo) — sinal para a discovery, zero efeito na coleta. Ramo alternativo (leitura literal do enunciado, só com novo GO do veto holder): filtro no store Python + flag `strict_database_scope`, re-plumb de 4+ sprocs partilhadas.
- **Modo de falha**: fail-open — se a sync à BD falhar, a coleta continua com o snapshot **validado** do JSON (a fonte de verdade continua a ser o ficheiro) + ERROR `[INVENTORY_SYNC_FAILED]` + heartbeat não avança → Collector Health mostra a tarefa atrasada. Fail-closed só para JSON inválido sem snapshot anterior (arranque).
- **Discovery de databases**: passa a ser um adapter do collector V1 (`discover_databases`, 1×/dia, `sys.databases` por servidor activo) que **escreve no canónico** `servers.json` (atomic write: temp + rename, backup rotativo, sem alterar outras chaves, preserva ordem) → a próxima sync apanha. É a única escrita automática no JSON (ver Q3).

### 6.2 Portal V3.3
- `/api/v3/servers`, `/api/servers`, `_load_monitored_servers` (×2), `network_diagnostics`, `monitoring.py`, `watcherdb_alwayson_check.py`, `database_discovery_service` → **um** `services/inventory_repo.py` que lê `metadata.monitored_server`(+`_database`) via `execute_on_intelligence()` (cache 60 s, fallback ao ficheiro local **só por flag de transição**).
- `connection_pool._load_credentials_cache` mantém o ficheiro local **apenas para credenciais** keyed por `instance_id` (o V3.3 continua sem poder decifrar Fernet do V1 — D1 05/08); inventário (host/instance/port/enabled) vem da BD + `WDB_INSTANCE_TCP_PORT` como hoje.
- Hardcoded `watcherdb_main.py:4450-4451, 4690-4906` e `_query_jobs_from_servers[:20]` → provider (sem corte; se há razão de carga, paginar por ambiente).
- `POST /api/config/sql-servers` (sync sql→servers, `watcherdb_main.py:1266-1345`): **descontinuar** (a edição passa a ser no JSON canónico; o portal Std não edita inventário — confirmar com `v33-feature-matrix-checker`).
- Ambiente: `_infer_env_from_instance` fica **só como fallback de último recurso** com WARN; fonte = `INST_ENVS.Env` (que vem da sync).

---

## 7. Migração das fontes legadas (sem quebrar coletas)

| Fase | Fonte legada | Acção | Guarda |
|---|---|---|---|
| M0 | `servers.json` V1 serviço DEPRECATED, 9 backups V3.3, `servers_27072026.json`, `sql_servers_new.json` | mover para `config/_archive/` (owner), `.gitignore` mantém | — |
| M1 | `sql_servers.json` (V1 + V3.3) | V1: `collect_agent_jobs`/`collect_2pc` → provider (flag `inventory.use_provider`); V3.3: `watcherdb_main.py:173` → repo BD; `alwayson.py` resolução de AG → `has_alwayson/ag_name/ag_listener` do inventário | sombra 7 dias: job compara `sql_servers.json` vs `monitored_server` e loga diff diária; só remove ficheiro após 0 diffs úteis |
| M2 | `config.yaml inventory.environments.server_count` | apagar chave; se algum código a lê (grep 0 no collector?) → provider | — |
| M3 | `server_config` como **leitura** (`collect_data_async`, `apply_grants_all_servers.py`, V5/V6?) | manter projecção `@ProjectToServerConfig=1` até migrar leitores; depois `=0` e `server_config` fica só EAV | grep cross-repo V5/V6 antes do flip |
| M4 | `sync_servers_from_json.py` | passa a *wrapper* manual que chama o provider + sproc (`--dry-run`), deixa de ter SQL próprio | — |
| M5 | Hardcoded V3.3 (4 listas, alembic/space default, htmx `dbo.servers`) | provider/BD; `htmx.py` endpoint → tabela nova ou remover router | — |
| M6 | `_infer_env_from_instance` + `env_map` + CASE SQL | fallback único com WARN; remover duplicados | teste de contrato: toda a instância activa tem Env na BD |
| M7 | Installer: bloco canonical `:6250-6280` ("[13/13] Inserindo 5 Servidores": `DELETE server_config` + INSERT com `PROD/TEST` divergente) + seed 13.6 INST_ENVS, `farm_inventory_parser` | bloco → "primeira run da sync" (`--full --no-dry-run`); parser gera JSON conforme `servers.schema.json` | fresh-install repair inclui 6 objectos novos na ordem tenants→server→database→run→audit→stg→sproc; guard `IF NOT EXISTS` partilhado por fresh-install e upgrade-in-place |
| M8 | Cópias V3.3 **e V6** de `servers.json` | reduzem-se a **mirror de credenciais regenerado pela sync** (`monitored_servers[{id, username, password}]` + `master_server`) — nunca editadas à mão; inventário = BD; router V6 `servers_inventory.py` passa a ler `server_sync_run` ou é removido | flag `inventory.source = db|file` (default `file` → `db` após sombra); bloqueante #1 do gate (cifra) resolvido antes |

Sem *big bang*: cada fase é uma flag, com a fonte antiga ainda no disco até à prova da sombra.

---

## 8. Plano de testes

| Nível | Casos (mínimo) |
|---|---|
| **Unitários — provider/validação** | JSON válido (63) → 63 servidores, 0 REJECT; ficheiro ausente / JSON partido / `monitored_servers` não-lista → snapshot inválido; cada regra da tabela §4 (id ausente, dup id, dup host+instance, BAD_ENV, enabled implícito, porta inválida, id >64, DB dup/CI, chave desconhecida → WARN); hash estável a reordenações e a voláteis (`databases_discovered_at`); `use_windows_auth` default **não** é True; master sem SQL auth → inválido. |
| **Unitários — sproc (pytest + BD de teste ou `tSQLt`-like em T-SQL standalone)** | 1.ª run: tudo INSERT; 2.ª run igual: 0/0/0 (idempotência); remover 1 servidor → DEACTIVATE + `removed_at`; repor → REACTIVATE com `removed_at NULL`; remover 30 % → PARTIAL + `MASS_DEACTIVATE_GUARD`, INSERT/UPDATE aplicados; staging vazia → FAILED sem mutação; DryRun não muta e devolve candidatos; DB removida/reposta; servidor ausente → DBs não reavaliadas; projecção INST_ENVS Env/Description; `server_config` row base 1 por instância; audit before/after só UPDATE SERVER; purge respeita retenção; applock timeout → erro limpo. |
| **Integração (collector)** | adapter `inventory_sync` em `dry_run` sobre cópia real do JSON → contagens esperadas; `collect_kpi`/`ping`/`agent_jobs`/`2pc` iteram exactamente `provider.servers(enabled=True)` (mock do provider); `databases[]` scope: filtro no store remove rows fora do scope e emite `[DB_OUT_OF_SCOPE]`; falha de BD na sync → coleta continua + `[INVENTORY_SYNC_FAILED]`; heartbeat SCHEDULE_META actualizado. |
| **Integração (V3.3)** | `/api/v3/servers` devolve o mesmo conjunto que `monitored_server WHERE is_active=1 AND enabled=1`, com `databases` da tabela nova; `connection_pool` resolve creds por `instance_id` com inventário da BD; sidebar (D3) com fallback quando query falha; `live_monitoring` inalterado (INST_ENVS física). |
| **Migração** | script de comparação (sombra) `sql_servers.json` ∪ `servers.json` V3.3 ∪ `server_config` vs `monitored_server` → diff zero antes de cada flip; `usp_reconcile_inst_envs` alterada: DryRun sobre dados reais = mesmas contagens que a versão actual. |
| **Compatibilidade** | V5/V6 leitores de `server_config`/INST_ENVS (grep cross-repo) continuam a obter as mesmas rows (projecção); installer fresh-install em BD vazia cria tudo na ordem; SQL 2014 (sem `CREATE OR ALTER`/`FOR JSON`) se for o piso real. |
| **Falha/cenários adversos** | JSON com 1 servidor (guarda frota → PARTIAL, nada desactivado); JSON trocado por outra frota (hash novo, ≥80 % DEACTIVATE → PARTIAL, alarme); 2 syncs concorrentes (applock: 2.ª espera/aborta limpa); sync durante swap (timeouts curtos, sem bloquear o swap — medir); rename de id (DEACTIVATE+INSERT, baseline reset documentado); ficheiro substituído a meio da leitura (atomic write na discovery + retry do loader). |
| **Regressão V3.3 existente** | suíte 6-níveis (`watcherdb-qa-specialist`), `test_kpi_env_breakdown_20260818` (Env continua a existir para toda a instância activa), contrato `databases[]` da sidebar (finding 27/07: "contrato databases[] sem teste"). |

---

## 9. Rollout, observabilidade, rollback

**Rollout (ordem = §13):** DDL novo (sem tocar nada existente) → sync em `dry_run: true` ~1 semana (logs + `server_sync_run` mostram o que faria) → flip `dry_run: false` com `@ProjectToServerConfig=1` → sombra de consumidores (provider lê JSON, compara com BD, loga) → collectors passam ao provider por flag (V1) → V3.3 `inventory.source=db` → desligar legado fase a fase (§7) → fechar Wave (5 surfaces, skill `wave-close`).

**Observabilidade:**
- Logs estruturados: `[INVENTORY_LOAD]` (n servidores, n DBs, n REJECT, hash), `[INVENTORY_SYNC]` (run_id, status, contadores), `[INVENTORY_SYNC_FAILED]`, `[INVENTORY_INVALID]`, `[DB_OUT_OF_SCOPE]`, `[INVENTORY_SHADOW_DIFF]` (sombra) — **zero superfície de alarme nova no portal** (regra do owner 05/08: tudo em log interno), excepto o que já existe: Collector Health (heartbeat da tarefa `inventory_sync` via `WDB_COLLECTION_SCHEDULE_META`, `Expected_Interval_Minutes=10`).
- Métricas consultáveis (SQL): última run OK e idade; runs FAILED/PARTIAL nas 24 h; REJECT por reason; servidores `is_active=0` últimos 7 d; DBs removidas últimos 7 d; diff sombra = 0.
- Opcional Std (decidir com `v33-feature-matrix-checker`): painel read-only "Inventário" no Collectors modal (última sync, contagens) — sem edição.

**Rollback por etapa:**
- DDL novo: `DROP` das 6 tabelas + sproc (nada depende delas até à etapa 5).
- Sync activa: `dry_run: true` no YAML (1 linha) + Restart-Service; dados: backup `SELECT * INTO *_BAK_<data>` de `server_config` e INST_ENVS antes do 1.º flip (padrão do reconcile); restauro = re-INSERT do BAK.
- Collectors no provider: flag `inventory.use_provider: false` → leituras antigas (código mantido até M-fases fecharem).
- V3.3: `inventory.source=file` → volta ao ficheiro local.
- Guarda automática: `MASS_DEACTIVATE_GUARD` + `@MinServersInSource` evitam o pior caso sem intervenção.

---

## 10. Ficheiros, módulos, serviços, jobs e tabelas a alterar (provável)

**V1 Intelligence** (`WATCHERDB INTELLIGENCE V1/`)
- `watcherdb_intelligence/collectors/server_manager.py` (→ `inventory_provider.py`, `ServerManager` mantido como fachada compatível), `collectors/__init__.py` (exports), `collectors/async_data_collector.py` + `data_collector.py` (filtro de scope no store), `collectors/server_collector.py` (EncryptionManager — sem mudança de cifra).
- `services/collector_service/collectors/inventory_sync.py` (**novo**), `discover_databases.py` (**novo**), `reconcile_inst_envs.py` (retira o sync), `collect_kpi.py`, `collect_server_ping.py`, `collect_agent_jobs.py`, `collect_2pc_transactions.py`, `collect_disk_unallocated.py`, `check_availability_coverage_gap.py`, `collect_scheduled_tasks_audit.py`, `service.py` (master via provider), `collectors_base.py` (heartbeat já existe), `config.yaml` (tarefas novas + remoção `inventory.sql_servers_file`/`environments.server_count` + flags `inventory.use_provider`, `strict_database_scope`).
- `scripts/sync_servers_from_json.py` (wrapper manual), `scripts/apply_grants_all_servers.py` (grep: lê `server_config`?), `config/servers.json` (ganha `databases[]` + `enabled` explícito em 63 entries), `config/servers.schema.json` (**novo**), `config/sql_servers.json` (remover pós-sombra), `config/config.yaml:15-27` (password em claro — separado).
- `database/INSTALACAO_COMPLETA_UNIFICADA.sql` (SECAO nova: 6 objectos + sproc + GRANTs; step [12/13]; `usp_reconcile_inst_envs` alterada — SECAO 17), standalone `database/INVENTORY_SYNC_COMPONENT.sql` (**novo**), `database/SETUP_ENVIRONMENT_TABLES.sql` (se semeia INST_ENVS), `CHANGELOG`.
- Tabelas BD: **novas** `metadata.monitored_server`, `metadata.monitored_server_database`, `metadata.server_sync_run`, `metadata.server_sync_audit`, `metadata.monitored_server_stg`, `metadata.monitored_server_database_stg`; **alteradas (só DML/uso)** `metadata.server_config`, `dbo.KPI_MSSQL_INST_ENVS`, `dbo.WDB_COLLECTION_SCHEDULE_META` (seed da tarefa nova); **sproc alterada** `dbo.usp_reconcile_inst_envs`; **nova** `metadata.usp_sync_monitored_servers`.
- Jobs/serviço: `WatcherDBCollector` (Restart-Service após cada edit — class cache), Task Scheduler `WatcherDB_Intelligence_Collector` (se ainda activo).

**V3.3** (`WATCHERDB_V3.3/`)
- `services/inventory_repo.py` (**novo**), `watcherdb_main.py` (:110 path, :173 arranque, :1130 `/api/v3/servers`, :1266-1345 sync sql→servers, :3405 `/api/servers`, :4450-4906 hardcoded, lifespan prewarm), `api/connection_pool.py` (creds-only), `api/routers/intelligence/helpers.py` (`_load_monitored_servers`, `_infer_env_from_instance`), `api/routers/intelligence_kpis.py` (cópia + `[:20]` + `env_map`), `api/routers/network_diagnostics.py`, `api/routers/alwayson.py` (AG do inventário), `api/routers/htmx.py` (`dbo.servers`), `api/routers/database_discovery.py` + `services/database_discovery_service.py` (deixa de escrever no JSON local ou escreve no canónico — Q3), `modules/monitoring/monitoring.py`, `modules/monitoring/watcherdb_alwayson_check.py`, `services/job_failures_collector.py`, `watcherdb/core/paths.py` (bootstrap skeleton → só creds), `watcherdb/api/routers/space.py:37` + `alembic/env.py:40` (default), `deploy/farm_inventory_parser.py` + `deploy/install_orchestrator.py` (schema), `config/servers.json.template`, `database/INSTALACAO_COMPLETA_UNIFICADA.sql` (cópia canonical espelho), `docs/FEATURE_MATRIX.md` (inventário = Std), `docs/guides/referencia_tecnica.md`, `README.md`, testes novos em `tests/unit/` + `tests/integration/`.
- Portal `templates/watcherdb_portal.html`: sidebar (consome `/api/v3/servers` — contrato mantido), eventual painel Inventário.

**V6** (propagação, regra 3/4 explicada): herda via BD (tabelas novas + projecções) + backend `inventory_repo` equivalente (portal V6 é subset; grep anchors primeiro).

---

## 11. Pareceres dos specialists

### 11.1 `sql-deep-reviewer` — modelo de dados (recebido, adoptado)
Resumo em §3; DDL draft em anexo A (parecer íntegro guardado nesta sessão). Riscos ordenados do parecer: (1) **dupla fonte de `databases[]`** (discovery escreve na cópia V3.3, não no canónico) — bloqueante antes do DDL; (2) credenciais **fora** da BD; (3) deactivation nunca por idade; (4) interacção com swap BLUE/GREEN (handoff V1); (5) rename de id = DEACTIVATE+INSERT (sem alias; backlog); (6) collation CI assumida — verificar `DATABASEPROPERTYEX`; (7) `server_config.host VARCHAR(100)` vs 255 → `LEFT` explícito + REJECT; (8) concorrência sync×reconcile (applocks distintos, DEADLOCK_PRIORITY LOW ambas, retry 1× Python); (9) purge só 1×/dia; (10) installer/fresh-install com os 6 objectos na ordem certa.

### 11.2 `watcherdb-v1-intel-specialist` — veto holder (recebido; verificou V1 + V3.3 + V6 na fonte)

Duas correcções materiais aos factos: (i) existe uma **4.ª cópia** de `servers.json` em `WATCHERDB_V6/config/servers.json`, com router próprio de drift-check contra `server_config` (`V6 api/routers/servers_inventory.py:10,77-85,142-162`); (ii) `databases[]` **não tem nenhum consumidor** no pipeline de coleta V1 — os KPIs per-database (`usp_Collect_Backups`, `usp_Collect_DB_Availability`, `usp_Collect_Filegroup_Usage`, `usp_Collect_TLog_Usage`) enumeram `sys.databases`/`sys.master_files` **ao vivo dentro do T-SQL** no servidor monitorizado (canonical `:4488,4679,4740,4812,5032`); `ServerConfig` nem tem campo `databases`.

| # | Pergunta | Veredicto | Condições |
|---|---|---|---|
| 1 | Canónico = V1 raiz; V3.3 lê BD | **GO-COM-CONDIÇÕES** | V3.3 **liga directamente** aos monitorizados (`connection_pool.py:190-483`, `network_diagnostics.py:35-38`: plan_analyzer, mirroring) com credenciais do ficheiro local (DPAPI) → precisa de ficheiro local **de credenciais** (mirror regenerado, nunca editado à mão) ou unificação de chave Fernet/DPAPI antes de apontar ao raiz. Para `databases[]` rejeita (a)(b)(c) e propõe **(d): discovery continua no V3.3 mas escreve directamente em `metadata.monitored_server_database`**, sem passar pelo JSON. |
| 2 | `databases[]` scope autoritativo da coleta | **VETO** | Mudança de semântica sem necessidade demonstrada; exigiria re-plumb de 4+ sprocs partilhados por V3.3+V5+V6 (TVP/dynamic SQL em `usp_Collect_All_KPIs`); risco concreto: discovery vazia/bug apaga silenciosamente a coleta per-DB de uma instância. `databases[]` fica **descritivo/observado** (catálogo para UI). Exclusão per-DB, se precisa, = estender `WDB_KPI_MUTE` (coluna `Database` opcional, **opt-out**). |
| 3 | Onde vive a sync | **GO** | `reconcile_inst_envs.py` mantém-se para o reconcile diário; collector **novo e leve** `sync_monitored_servers` (5-15 min, executor default) só chama a sproc com SKIP por hash; burn-in `@DryRun=1` → GO explícito do owner após logs (precedente 27/07). `metadata.monitored_server*` está fora de `KPI_STG_ACTIVE_TABLE`/BLUE-GREEN → **zero overlap de lock** com o swap; staggering é boa prática, não requisito. |
| 4 | Contrato único (InventoryProvider) + fail-open | **GO-COM-CONDIÇÕES** | Valor real (mata 3 fallbacks hardcoded em agent_jobs/2pc e o `parent.parent.parent.parent` repetido), mas **não bundlar na mesma wave da sync** — a tabela + sync queimam sozinhas em produção primeiro. Fail-open só sobre o **último snapshot válido cacheado**, nunca sobre ficheiro a meio de escrita; reaproveitar o guard "nunca desactivar a frota com JSON vazio" (`sync_servers_from_json.py:191`). |
| 5 | Limpeza legado + validação | **GO-COM-CONDIÇÕES** | **Diff 95 vs 63 antes de apagar `sql_servers.json`** (servidores só na lista de 95 cegariam agent_jobs/2pc); validação = warn+skip por entrada (padrão `server_manager.py:112-123`), **nunca abortar o load inteiro**; `use_windows_auth` passa a **obrigatório explícito** (gap real da Regra de Ouro #2). |
| 6 | Installer/canonical | **GO-COM-CONDIÇÕES** | Bloco real `:6250-6280`, label **"[13/13] Inserindo 5 Servidores"** (não [12/13]); tem `PROD/TEST` divergente → mais um argumento para "primeira run da sync"; identidade de escrita = a mesma que hoje faz INSERT/UPDATE/DELETE em `server_config` (credenciais `master_server` do collector); fresh-install e upgrade-in-place partilham o guard `IF NOT EXISTS`. |

**Condições bloqueantes pre-ship (veto holder):** (1) resolver cifra V3.3 vs V1 — mirror sincronizado ou chave unificada — antes de o V3.3 largar o inventário próprio de ligação directa; (2) `databases[]` NÃO autoritativo (VETO) — descritivo; exclusão via `WDB_KPI_MUTE`; (3) diff `sql_servers.json` 95 vs 63 antes de remover; (4) heartbeat `WDB_COLLECTION_SCHEDULE_META` para o collector novo (senão NEVER_RAN falso); (5) `use_windows_auth` obrigatório no schema.
**Riscos residuais:** 4.ª cópia V6 sem destino decidido; provider único = maior superfície de regressão (testar collector a collector); projecção `server_config` é dependência silenciosa de V5/V6 (`servers_inventory.py:142-162`, `network_diagnostics.py`).

### 11.3 Consenso aplicado ao plano
- **Q2 passa a decisão central do owner** (§12): o veto holder não aceita `databases[]` como scope de coleta. O plano segue o consenso — `databases[]` sincronizado para a BD como **catálogo autoritativo de inventário/UI** (é a "fonte de verdade" do *que existe*), enquanto os KPIs per-DB continuam a enumerar `sys.databases` ao vivo (o que *é coletado*). Se o owner mantiver a leitura literal ("só coleta o que está no JSON"), é preciso **novo handshake com o veto holder** e a wave cresce em 4+ sprocs partilhadas — está assinalado como ramo alternativo, não como plano.
- Q3: duas rotas para `databases[]` chegar à BD — **(a)** discovery no V1 escreve no canónico → sync (coerente com "JSON única fonte"); **(d)** discovery do V3.3 escreve direto na tabela (parecer V1; evita cifra e JSON inchado, mas a BD passa a ter um escritor que não é o JSON). Recomendo **(a)** por coerência com o enunciado; (d) é o fallback se a discovery no V1 atrasar.
- E5 (collectors → provider) separa-se em wave própria, **depois** de E3/E4 queimarem sozinhas.

---

## 12. Riscos, decisões em aberto e perguntas ao owner

**Riscos principais**
1. (Só no ramo alternativo de Q2) scope `databases[]`: DB criada entre discoveries fica cega; discovery vazia apaga a coleta per-DB de uma instância — razão do VETO. No plano consensual este risco **não existe**.
2. Escrita na infra partilhada a cada 10 min (INST_ENVS projecção) — pequena e fora do BLUE/GREEN (gate V1: zero overlap de lock); SKIP por hash faz com que na prática só escreva quando o JSON muda ou às 03 h.
3. Segredos: **4 cifras/estados** distintos (V1 EncryptionManager, V3.3 DPAPI, V6, `config.yaml` em claro). O plano **não** unifica cifra — V3.3/V6 ficam com mirror local de credenciais regenerado pela sync (condição #1 do gate). Deriva de *credenciais* (não de inventário) permanece até unificar chave.
3b. Regressão nos collectors ao trocar 7+ pontos de leitura pelo provider — maior superfície da wave (gate): wave própria, collector a collector, `sql_servers.json` só removido após diff 95 vs 63.
3c. `collect_kpi` QA→`'qa'`: bug latente em collector **desactivado** (`config.yaml:65-109`, `enabled:false`) — corrigido por higiene, zero impacto operacional; **não** é quick win de produção (correcção ao achado da manhã).
4. Fresh-install repair em curso (PLANO_WAVE_FRESH_INSTALL_REPAIR) — colisão de canonical; coordenar a SECAO nova com esse plano.
5. Rename de `id` (SS301) continua destrutivo para baselines — documentar; `aliases[]` fica backlog.
6. V5/V6 como leitores de `server_config`/INST_ENVS — projecção cobre, mas o flip `@ProjectToServerConfig=0` exige grep cross-repo primeiro.
7. Piso SQL Server 2014 vs sintaxe 2016+ no draft — verificar versão do host da Intelligence antes do DDL.
8. Carga do `server_sync_audit` com DATABASE (5-10 k rows/run se tudo mudar) — só em mudanças reais; retenção 90 d.

**Decisões em aberto (com recomendação)**
- **Q1 — "Tabelas" = `databases[]`?** Recomendo sim (única sub-lista do JSON). Alternativa (tabelas KPI alvo por collector = `config.yaml tasks[].tables`) é outro eixo (catálogo de collectors), não pertence ao `servers.json`.
- **Q2 — `databases[]` é scope da coleta ou catálogo? (DECISÃO CENTRAL)** O veto holder **VETOU** o scope (§11.2 #2). Plano consensual: **catálogo autoritativo** (BD/UI = o que existe), coleta per-DB continua ao vivo (= o que é coletado), exclusões via `WDB_KPI_MUTE.Database`. Se o owner quiser a leitura literal do enunciado, é novo handshake com o V1 e +4 sprocs partilhadas na wave — custo e risco (discovery vazia cega uma instância) assinalados.
- **Q3 — Quem escreve `databases[]`?** (a) discovery **no collector V1** escreve no canónico (atomic write, 1×/dia) → sync leva à BD — coerente com "JSON única fonte" (**recomendo**); (d) discovery do V3.3 escreve **directamente** em `metadata.monitored_server_database` (parecer V1 — evita cifra e JSON inchado, mas a BD ganha um escritor que não é o JSON). Rejeitado: V3.3 a escrever num ficheiro partilhado (dois escritores, duas cifras).
- **Q4 — Qual ficheiro é o canónico?** Recomendo o da **raiz V1** (já é o do collector; OATXP01 só existe aí). O V3.3 deixa de ter *inventário* próprio; a cópia V3.3 reduz-se a **mirror de credenciais regenerado pela sync** (nunca editado à mão) até haver chave unificada — condição bloqueante #1 do gate (V3.3 liga directamente aos monitorizados para plan_analyzer/mirroring). Requer: OATXP01 ganhar credenciais V3.3 ou `enabled:false`. **A 4.ª cópia (V6)** segue o mesmo destino do V3.3 (consumidor read-only da BD + mirror de credenciais); o router `servers_inventory.py` de drift-check do V6 torna-se redundante (ou passa a ler `server_sync_run`).
- **Q5 — Frequência da sync**: 10 min com SKIP por hash (barato) + run completa 03 h. Alternativa: só diária (como hoje) — mas então "durante as coletas" do enunciado não se cumpre.
- **Q6 — Identidade**: mesmo login escritor do V1 (precedente swap/reconcile) vs login dedicado `svc_inventory_sync` (least-privilege, alinha com Frente 2). Recomendo o existente agora, dedicado quando a Frente 2 (collector em servidor) avançar.
- **Q7 — Portal Std edita inventário?** Recomendo **não** (edição = JSON + PR/backup; portal só lê). `POST /api/config/sql-servers` descontinuado. Confirmar com `v33-feature-matrix-checker`.
- **Q8 — `enabled` explícito obrigatório?** Recomendo sim (causa raiz do "1 OFF"), com N dias de WARN antes de REJECT.
- **Q9 — Nome "watcherdb"** no pedido = `WatcherDB_Intelligence` (assumido; não existe outra BD).

---

## 13. Plano em etapas ordenadas (com critérios de aceite)

```
E0 ░░░░ Decisões Q1-Q9 pelo owner (Q2 central) ─── gate V1: GO-COM-CONDIÇÕES recebido (5 bloqueantes em §11.2) ; higiene: fix collect_kpi QA→'quality' (collector desactivado)
E1 ░░░░ Contrato: servers.schema.json + InventoryProvider (validação warn+skip, use_windows_auth/enabled explícitos) + testes ─── sem BD
E2 ░░░░ DDL novo (6 objectos + sproc + GRANTs) canonical+standalone, aplicado pelo owner (SSMS) ─── zero consumidores
E3 ░░░░ Collector sync_monitored_servers dry_run=true (10 min, heartbeat) + discovery (Q3: V1→JSON ou V3.3→BD) ─── 1 semana de logs
E4 ░░░░ Flip dry_run=false + reconcile lê removed_at + projecções ligadas + sombra de consumidores (diff diário) + diff sql_servers 95 vs 63
E5 ░░░░ [WAVE PRÓPRIA] Collectors V1 → provider (base_collector + 6 próprios + kpi/ping/jobs/2pc/disk_unallocated), collector a collector
E6 ░░░░ V3.3 (e V6) → inventory_repo (inventory.source=db) ; mirror local de credenciais regenerado ; hardcoded/[:20]/env inferência → fallback
E7 ░░░░ Desligar legado (M0-M8), @ProjectToServerConfig=0 quando V5/V6 migrarem ; WDB_KPI_MUTE.Database se houver pedido de exclusão per-DB
E8 ░░░░ Fecho de Wave: canonical + memória schema + CHANGELOG + specialists + bibliotecas + prompt V6 explicado
```

| Etapa | Critério de aceite (mensurável) |
|---|---|
| E1 | 100 % das regras §4 com teste; `provider.load()` sobre o JSON real = 63 servidores, 0 REJECT (após `enabled` explícito); hash estável. |
| E2 | `EXEC usp_sync_monitored_servers @DryRun=1` sobre staging de teste devolve candidatos coerentes; 2.ª run 0/0/0; objectos no canonical e no standalone; GRANTs verificados via `sql_monitoring`. |
| E3 | 7 dias de runs: ≥1 run OK/dia, 0 FAILED não explicado, contadores de dry-run = diferença real JSON↔BD revista pelo owner; `databases[]` presente em 100 % dos servidores activos do canónico. |
| E4 | `monitored_server WHERE is_active=1` = ids `enabled` do JSON (diff 0); INST_ENVS Env = mapeamento único (0 rows fora de PRD/QLT/TST/DEV); reconcile DryRun = mesmas contagens que a versão anterior; audit regista todas as acções. |
| E5 | grep `json.load` de inventário nos collectors = 0 fora do provider; `sql_servers.json` sem leitores V1 (diff 95 vs 63 fechado); coleta de jobs/2pc cobre a frota canónica; `collect_disk_unallocated` não deriva frota da STG; `[DB_NOT_IN_CATALOG]` a 0 após discovery; cada collector validado isoladamente (1 ciclo limpo por collector). |
| E6 | `/api/v3/servers` ≡ BD; portal sidebar/modais sem regressão (browser test); `[:20]` removido; 9 leitores → 1 repo; Windows Service sem dependência de CWD. |
| E7 | ficheiros legados arquivados; flags em estado final; V5/V6 validados; fresh-install cria tudo. |
| E8 | 5 surfaces actualizadas; CONTEXT.md com ponteiro; memória schema catalog com as 6 tabelas. |

Panorama (actualizado 2026-08-21, CORRECÇÃO pós-parecer da sessão V6): `[█████████░] ~90 %` — E0-E8 executadas e validadas MAS o fecho a 100 % foi OVERCLAIM: **E6c PENDENTE** — 5 itens do próprio plano (M1 + §E6 linhas "watcherdb_main:173 → repo", "POST /api/config/sql-servers descontinuar", "hardcoded → provider") ficaram por fazer no V3.3. Verificado na fonte 21/08: (1) boot `SQLServerMonitoring` (`watcherdb_main.py:107,172-188`) ainda abre `config/sql_servers.json` — **95 servidores, Excel 2025-11** — e alimenta monitor_all/alertas críticos/Space Analysis/tempo real (a mesma classe de fantasmas eliminada no V1 continua viva no caminho realtime do V3.3); (2) `alwayson.py:756-885` fallback ao ficheiro com matching heurístico; (3) `POST /api/config/sql-servers` (`watcherdb/api/routers/config.py:53`) ainda escreve o ficheiro; (4) Excel/jobs + 4× listas de 3 instâncias hardcoded (`watcherdb_main.py:4450,4690+`); (5) job de sombra 7 dias nunca escrito (funcionalmente substituído pelo diff manual E4c — 0 diffs + 2 casos reais — mas a condição "remover ficheiro só após 0 diffs" nunca foi executada do lado V3.3, e o ficheiro não foi arquivado no E7 exactamente porque ainda tinha consumidores). **E6c definida como 1.º item da sessão mini-wave** (código V3.3 puro, zero DDL): boot→inventory_repo; alwayson→campos has_alwayson/ag_name/ag_listener do inventário; POST→descontinuar (parecer feature-matrix); hardcoded→repo; sombra→dispensada com justificação; SÓ DEPOIS arquivar `config/sql_servers.json` V3.3. O V6 NÃO copia o buraco (adenda no prompt de propagação). Histórico do fecho anterior mantido abaixo para auditoria — E0-E4 + E6a/E6b completas e validadas; **E5 FECHADA e validada em produção 20/08 08:54** (PRD 42/42 OK 0 failed — antes 11 falhas fantasma/ciclo; zero Trusted_Connection; commit 1d172c5), falta E7 (arquivos+órfãos STG), E8 (fecho de wave) — **E0 FECHADO** (owner GO a todas as recomendações Q1-Q9) · **E1 FEITO** (consenso v1-intel sem veto, 3 ajustes aplicados: hash inclui ciphertext da password; `sql_servername_alias_reason` na allowlist; teste de schema = contrato de estado final, não paridade com REJECT): `watcherdb_intelligence/collectors/inventory_provider.py` (InventoryProvider + dataclasses + validação warn+skip + hash + cache mtime-safe), `config/servers.schema.json`, `tests/unit/test_inventory_provider.py` (**66 passed**; frota real 63 → 0 REJECT, 61 WARN `enabled` implícito); higiene `collect_kpi.py` QA→'quality' (collector desactivado) · **E2 ESCRITO** (GO owner 19/08 fim de tarde): `V1/database/INVENTORY_SYNC_COMPONENT.sql` (standalone) + SECAO 34 no canonical (espelho, 699 linhas): 6 tabelas `metadata.*` + `usp_sync_monitored_servers` completa (guardas, applock, audit FOR JSON, projecções INST_ENVS/server_config com `is_active=1 AND enabled=1`, purge só com `@Purge=1`) + seed heartbeat + GRANTs. **Revisão sql-deep-reviewer (3.ª tentativa, bounded) = PRECISA CORRECÇÕES → todas aplicadas**: guarda de re-execução do mesmo `@RunId` já finalizado; FK a `tenants` idempotente fora do IF; `@c_rej` exclui os saltados pela guarda de frota; applock falhado vai directo ao CATCH (sem UPDATE duplo); `INCLUDE_NULL_VALUES` no FOR JSON (diff before/after estável); `DELETE TOP (2000)` (abaixo do limiar de lock escalation); `SET LOCK_TIMEOUT 3000`; contrato documentado "`databases: []` explícito ≡ ausente (não desactiva DBs)". Veredicto pós-correcções: PRONTO para E3 em dry-run. **E2 APLICADA pelo owner 19/08 12:28** (7 objectos + seed confirmados; commit 21f642e) · **E3 ESCRITA**: `services/collector_service/collectors/sync_monitored_servers.py` + task YAML (10 min, `dry_run: true`, `full_run_hour: 3`, guardas no YAML) + export no package + 11 testes (77 no total E1+E3) + CHANGELOG V1 2.28.0 + memória schema catalog; Restart 12:58, 1.º DRYRUN 12:59:59 (63/63/0/0, 1,3 s), 2.º ciclo 13:09:58 SKIPPED_UNCHANGED (hash c6e3c084), `last_checked_at` a avançar — **E3 validada, em burn-in** · **E3b ESCRITA**: `collectors/discover_databases.py` (sys.databases → `databases[]` no JSON canónico; atomic write + backup rotativo; só entradas com mudança; falha não apaga) + task YAML (60 min, `run_after_hour: 2`, `dry_run: true`) + 8 testes (85 total) + CHANGELOG; discovery validada (DRY_RUN 14:06: 62/63, 1627 DBs) → **flip `dry_run=false` com GO do owner (commit f77004d)** → 1.ª escrita real 14:40:52 (62/63 com `databases[]`, 1626 DBs, backup `config/_backup/servers.json.20260819-144052`, segredos intactos) → sync run 3 DRYRUN 14:42:24 com `Dbs_In_Source=1626 / Db_Would_Insert=1626` — pipeline fechado em dry-run → **E4a: owner deu GO no mesmo dia** (contra a minha recomendação de esperar a run das 03h; registado) → BAK INST_ENVS/server_config → `sync_monitored_servers.dry_run=false` → run 4 EXECUTE 17:11:25: **63 servidores + 1626 DBs inseridos, 0 rejeitados, INST_ENVS 0 linhas alteradas vs BAK** — a BD passa a ser alimentada pelo `servers.json`. **E4b feita** (SECAO 17: reconcile lê `monitored_server`, fallback `server_config`, fail-safe fonte vazia; adapter sem o sync legado → um escritor só; DryRun = paridade exacta; commit 745883c). Pendente E4c (diff `sql_servers` 95 vs 63). **E6a ESCRITA (GO owner 'siga o recomendado')**: `services/inventory_repo.py` (BD → formato servers.json, cache 60 s, `inventory_source db|file`, fallback ficheiro, `has_credentials` cruzado com o ficheiro local), `/api/v3/servers` + `/api/servers` + `_load_monitored_servers` (×2) → repo; parecer v33 CORRIGIR→corrigido (OATXP01 sem creds oculto até provisionar); 8 testes; **validada em produção 19:39 (commit 062421a): `/api/v3/servers -> 62 servers (source=db)`, OATXP01 oculto por falta de creds locais**. **E6b escrita**: monitoring.py → repo; network_diagnostics path via `config_dir()` (creds → ficheiro mantido); discovery V3.3 deixa de escrever os JSON locais com `inventory_source=db`; **fim do `servers[:20]`** nos jobs (todos os servidores, 16 workers). connection_pool fica (sem ganho) e alwayson_check (lookup de creds) fica. 129 testes OK; **validada em produção 20/08 07:57 (commit ec87b31): monitoring.py 'Loaded 62 physical servers from inventory (source=db)'**. Nota de processo: 2 agentes de revisão anteriores bloquearam >60 min sem output — pedidos bounded (≤3 tool calls) resolvem em 2 min.

---

## Anexo A — DDL draft (parecer sql-deep-reviewer, para revisão; não executar)

Transcrito em [PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19_ANEXO_DDL.sql](PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19_ANEXO_DDL.sql): 6 tabelas (`monitored_server`, `monitored_server_database`, `server_sync_run`, `server_sync_audit`, 2 staging) + esqueleto `metadata.usp_sync_monitored_servers` + GRANTs comentados + colaterais. Cabeçalho marca explicitamente "NÃO EXECUTAR" e a nota de piso SQL 2014.
