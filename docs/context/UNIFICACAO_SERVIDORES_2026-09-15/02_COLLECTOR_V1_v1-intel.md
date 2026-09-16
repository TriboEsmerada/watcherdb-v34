# 02 — Collector V1 e servers.json canónico (watcherdb-v1-intel-specialist, 2026-09-15)

Autor: watcherdb-v1-intel-specialist (guardião da infra partilhada, direito de veto), só leitura.
Verificação do orquestrador: ver 00_INDICE.md. **Correcção já verificada:** a rota viva `POST /api/config/sql-servers` está em `watcherdb_main.py:1227`; `watcherdb/api/routers/config.py` é código morto (não registado). As referências a `config.py:53,62` abaixo ficam como no original, mas estão erradas quanto ao ficheiro.

Caminhos: collector V1 em `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB INTELLIGENCE V1\`, portal em `...\WATCHERDB_V3.4\`. O plano `PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md` já foi executado (E0–E8, 19–21/08/2026); o que segue é o estado verificado a 15/09.

---

## 1. `servers.json` canónico

**FACTO.** Canónico = `WATCHERDB INTELLIGENCE V1/config/servers.json` (raiz do collector). Hoje: **63 servidores**, todos `enabled` explícito (0 desabilitados). Lido por `watcherdb_intelligence/collectors/inventory_provider.py` (`InventoryProvider.load()`, `:478`), leitor único desde E1. Cifra: `EncryptionManager` (`.encryption_key` na raiz).

Cópias:
- `V1/services/collector_service/config/servers.json.DEPRECATED_20260805` — renomeada, sem leitores (D1 05/08).
- `V1/config/sql_servers.json` (95, Excel 2025-11) — **arquivada** pelo owner no E7 (20/08). O V3.4 tem o seu próprio `config/sql_servers.json` (ficheiro diferente).
- `WATCHERDB_V3.4/config/servers.json` — 63 entradas, inclui OATXP01. Já não é inventário próprio; é **mirror de credenciais** (`services/inventory_repo.py:7-17`: "config/servers.json fica para credenciais (connection_pool) e como fallback"; `settings.inventory_source` default `"db"`). Gitignored (`.gitignore:212-213`).
- `WATCHERDB_V6/config/servers.json` — **4.ª cópia**, com router próprio de drift-check (`V6 api/routers/servers_inventory.py:10,77-85,142-162`). **Não resolvida.**
- `WATCHERDB_V3.4/config/sql_servers.json` — ainda existe; `.gitignore:193` cobre-o.

Cifra: V1 = `EncryptionManager`; V3.4 = `services/secrets.py` DPAPI (não unificadas; condição bloqueante #1 do parecer de 19/08, §11.2).

## 2. Quem popula `metadata.monitored_server` / `_database`

**FACTO** (`V1/database/INVENTORY_SYNC_COMPONENT.sql:52-748`): escritor único = collector `services/collector_service/collectors/sync_monitored_servers.py`, ciclo 10 min, chama `metadata.usp_sync_monitored_servers` via staging keyed por `run_id` (`monitored_server_stg`/`_database_stg`, sem TRUNCATE). A sproc classifica por FULL OUTER JOIN staging×alvo (`:324-550`): **INSERT / UPDATE (hash diferente) / REACTIVATE / DEACTIVATE (ausente da run) / NOOP**. Desactivação **sempre soft** (`removed_at`, `is_active=0`) e **só por ausência na run processada** (nunca por idade de `last_seen_in_source_at`). Guarda de frota: se DEACTIVATE > 20% dos activos, salta as desactivações e devolve `PARTIAL` (`MASS_DEACTIVATE_GUARD`).

**O portal (V3.4) não escreve nestas tabelas** — `services/inventory_repo.py` é só-leitura (`execute_on_intelligence`, cache 60s).

**Split-brain residual:** o portal ainda tem `POST /api/config/sql-servers` que escreve em `config/sql_servers.json` (V3.4). Esse ficheiro alimenta o boot `SQLServerMonitoring` (`watcherdb_main.py:107,172-188`) e o fallback de `alwayson.py:756-908`. A sidebar (`/api/v3/servers`) lê a BD e não vê estas edições.
**[PROACTIVE FINDING] data-integrity | high** — dois caminhos de escrita/leitura de inventário coexistem no V3.4 (BD via sidebar vs sql_servers.json via boot/alwayson/POST config), sem sincronização nem aviso; é o item E6c de 21/08, não fechado. Sugestão: fechar E6c antes de trabalho novo de unificação.

## 3. `InventoryProvider`

**FACTO** — `V1/watcherdb_intelligence/collectors/inventory_provider.py`:
- `ENV_ALIASES` (`:53-58`): `PRD/PROD/PRODUCTION→production`, `QA/QLT/QUALITY→quality`, `TST/TEST→test`, `DEV/DEVELOPMENT→development`.
- `enabled` obrigatório (Q8, 19/08): `REQUIRED_SERVER_KEYS` inclui `enabled` e `use_windows_auth` (`:60`); ausência → `Rejection("SERVER", sid, "ENABLED_NOT_EXPLICIT")` **só em modo strict** — hoje em modo WARN (`:304-310`). Com os 63 actuais com `enabled` explícito, o WARN não dispara, mas o strict continua desligado.
- Chave de identidade: `id` (`ServerEntry.id`, `:106`) = `instance_id` na BD (≤64 chars, mapeia 1:1 para `KPI_MSSQL_INST_ENVS.Instance`). Validação contra duplicados por `host+instance` (`DUP_HOST_INSTANCE`, plano §4).
- `class InventoryProvider` em `:461-539`, `load()` em `:478`.

## 4. Host / instância / alias / listener

**FACTO** (`INVENTORY_SYNC_COMPONENT.sql:81-112`): `metadata.monitored_server` tem colunas separadas `host`, `instance_name`, `sql_servername_alias`, `has_alwayson` (BIT), `ag_name`, `ag_listener`. Não há linha própria para o listener AG (é atributo de uma instância). No `sql_servers.json` legado de 95, ids de listener/farm apareciam como servidores autónomos (diff E4c, `CONTEXT.md:301`, 20/08: dos 33 só no sql_servers.json, vários eram "SITECORE farm/listeners AG/AS/SharePoint2010") e ficaram fora do canónico.

**Dedup**: `DUP_ID` e `DUP_HOST_INSTANCE` são REJECT no provider antes da BD (plano §4, linhas 163-164); 0 REJECT na frota real.

`is_active`/`enabled` (`:91-92`): `enabled` = intenção do operador (flag do JSON); `is_active` = presença na fonte (estado observado pela sync). `enabled=1` com `is_active=0` é possível e desenhado.

## 5. Denominador do dashboard

- `api/routers/live_monitoring.py:1155` — query "fleet" usa `FROM dbo.KPI_MSSQL_INST_ENVS` como driving table, cruzada com perf/avail/disk.
- `api/routers/live_monitoring.py:1167` — offline de `dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WHERE Ping_OK = 0`.
- `dbo.usp_check_availability_coverage_gap` (`V1/database/CHECK_AVAILABILITY_COVERAGE_GAP.sql:52-97`) — `Configured_Total` lê `[metadata].[server_config]` (`:74-75`, `tenant_id='default' AND is_active=1`), hoje **projecção** da sync (`@ProjectToServerConfig=1`). Dependência indirecta nunca actualizada para `monitored_server`.

Nota do orquestrador: o cartão "Instâncias" do dashboard principal usa `ok_count + off_count` de `helpers.py` (ver 01 e 04), não `live_monitoring.py`. Este último é o módulo Live Monitoring.

63 ≠ 62 já apareceu (`CONTEXT.md:304-307`, 20/08): "quem reporta" vs "quem está inventariado" (PRD214 porta dinâmica, OATXP01 SQL 2005). **Não foi corrido SELECT ao vivo** — lacuna de verificação.

## 6. Consumidores V1 de `sql_servers.json`

**RESOLVIDO** (`CONTEXT.md:303`, E5, 20/08, commit `1d172c5`): `collect_agent_jobs.py` e `collect_2pc_transactions.py` usam `sql_monitoring` via provider. PRD 42/42 OK. `V1/config/sql_servers.json` arquivado no E7. Sem consumidores V1 vivos (só `test_2pc_collector.py` referencia o nome).

## 7. Fonte autoritativa de escrita — veredicto

O collector V1 é o único escritor (JSON canónico e BD via sync); o portal só lê a BD.

- **(a) Portal escreve directo no `servers.json` canónico — VETO.** Duas cifras (DPAPI vs EncryptionManager) tornam credenciais intransportáveis; escrever sem hash/validação/staging reabre a classe "1 OFF permanente" / `enabled` implícito.
- **(b) Portal escreve em `metadata.monitored_server` e collector passa a ler da BD — VETO.** Inverteria dono/projecção; o próximo ciclo da sync (10 min) reverteria silenciosamente a escrita do portal.
- **(c) Portal chama endpoint/comando do collector** — modelo mais seguro, **não implementado**. Hoje é manual (editar o JSON canónico, ou `discover_databases.py`, que já escreve `databases[]` de forma atómica com backup rotativo). Recomendação: endpoint que escreve no JSON canónico via atomic-write (padrão `discover_databases.py`), nunca directo na BD.

**Pré-requisito:** fechar E6c primeiro. **Convergência:** sync 10 min (SKIP por hash) + run completa às 03h; portal cache 60s → pior caso ~11 min.

**VEREDICTO: GO-com-coordenação**, condicionado a fechar E6c antes.

## Estado E0–E8

| Etapa | Estado | Evidência |
|---|---|---|
| E0-E4 | FECHADAS | `INVENTORY_SYNC_COMPONENT.sql` aplicado; `sync_monitored_servers.py` corre |
| E5 | FECHADA | `inventory_provider.py` leitor único V1; agent_jobs/2pc migrados |
| E6a/E6b | FECHADAS | `services/inventory_repo.py`; `/api/v3/servers` fonte `db` |
| **E6c** | **PENDENTE** | `watcherdb_main.py:172-188`, `api/routers/alwayson.py:756-908`, POST `/api/config/sql-servers` (rota viva em `watcherdb_main.py:1227`) |
| E7 | Parcial | V1 arquivado; V3.4 mantém o seu |
| E8 | Feito para V1; V6 (4.ª cópia) não verificada |

Ficheiros citados: V1 `config/servers.json`, `watcherdb_intelligence/collectors/inventory_provider.py`, `database/INVENTORY_SYNC_COMPONENT.sql`, `database/CHECK_AVAILABILITY_COVERAGE_GAP.sql`, `services/collector_service/collectors/sync_monitored_servers.py`, `collectors/discover_databases.py`; V3.4 `services/inventory_repo.py`, `watcherdb_main.py:96-188`, `api/routers/alwayson.py:676-952`, `api/routers/live_monitoring.py:1130-1174`, `docs/context/PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md`, `docs/context/CONTEXT.md` (287-311, 392-395).
