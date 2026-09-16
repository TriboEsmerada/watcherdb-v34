# 05 — Arquitectura e plano (architecture-advisor, Fase 2, 2026-09-15)

Autor: architecture-advisor, só leitura, a partir dos relatórios 00–04. **[F]** = facto verificado; **[H]** = hipótese.
Verificação do orquestrador: `api/connection_pool.py:760-790` confirmado — id fora do `sql_auth_rollout` ou com credenciais incompletas → `Trusted_Connection=yes`; `:546-549` confirmado — lookup por host sozinho.

---

## 1. Papéis de cada fonte, hoje e depois

| Artefacto | Hoje | Depois |
|---|---|---|
| `V1/config/servers.json` (EncryptionManager) | Canónico; lido só pelo `InventoryProvider` [F 02 §1]; editado à mão ou por `discover_databases` (atómico, `discover_databases.py:115-137`) | **Único sítio onde se escreve o inventário.** Só o processo do collector escreve. A gestão no portal pede alterações e nunca escreve directamente (veto (a)) |
| `metadata.monitored_server` (+ `_database`) | Projecção da sync de 10 min (`config.yaml:1671-1682`); `enabled` = intenção; `is_active` = presente na fonte (`INVENTORY_SYNC_COMPONENT.sql:91-92`) | **Única projecção lida pelo portal.** Contrato (§2) calculado daqui. Portal nunca escreve (veto (b)) |
| `metadata.server_config` | Projecção secundária, coverage gap (`CHECK_AVAILABILITY_COVERAGE_GAP.sql:74-75`) | Igual; portal não usa |
| `KPI_MSSQL_INST_ENVS` | Reconciliada de hora a hora; ambiente no dashboard (`helpers.py:1258-1266`) e Live Monitoring (`live_monitoring.py:1155`) | Deixa de dar ambiente ao dashboard (passa a `monitored_server.environment`). Live Monitoring continua até lote próprio. Até 1 h de atraso |
| `InventoryRepo` (60 s) | Só expira por tempo [F `inventory_repo.py:209-214`] | Ganha `invalidate()`, vista admin separada e `inventory_version` |
| `_dashboard_cache` (60 s) + snapshot (24 h) | Bloco de disponibilidade depende da ordem de conclusão | Bloco `fleet` calculado depois do gather; snapshot antigo recalcula ao vivo ou marca `stale` |
| `WATCHERDB_V3.4/config/servers.json` (DPAPI) | Espelho de credenciais + fallback + alvo do sync do POST [F `watcherdb_main.py:1269-1361`] | **Só config local de ligação** (credenciais, porta, `connection_pool`) e fallback só leitura. Nada do portal lhe escreve em runtime |
| `config/sql_auth_rollout.json` (62) | Allowlist SQL Auth; fora → Trusted [F `connection_pool.py:766-784`] | Só modo de autenticação, nunca elegibilidade; entra no estado de ligação (§2) |
| `WATCHERDB_V3.4/config/sql_servers.json` (95) | Editado pela gestão; lido no boot, fallback AlwaysOn, space/backup (`watcherdb_main.py:2298,2333,2466`) | **Legado.** Com E6c fechada ninguém lê. POST atrás de flag; arquivado por renomeação após 1 release sem leituras |

## 2. Contrato partilhado (`services/inventory_contract.py`, puro)

### 2.1 Identidade
- `norm(x) = x.strip().replace("\\", "_").upper()`; vazio/espaços rejeitado. Igual ao provider V1 (`inventory_provider.py:273-286`) [F]. BD única por `(tenant_id, instance_id)` (`INVENTORY_SYNC_COMPONENT.sql:107`) [F].
- **Chave canónica** = `instance_id`; nunca agrupar por host.
- **Índice de match KPI→inventário** (cada chave → um único `instance_id`): `norm(instance_id)`; `norm(host_instance)` ou `norm(host)` sem instância; `norm(sql_servername_alias)`. Chave com 2 ids → **sem correspondência** e registada; nunca funde. Resolve SS301 sem juntar instâncias legítimas.
- **Host:** índice separado `norm(host) → [instance_ids]` só para sinais de host (ping por `Server_Name` [F 01 §C]); ping falhado marca cada instância do host.
- **Nunca procurar por host sozinho** para credenciais/identidade — hoje `connection_pool.py:546-549` faz isso [F].
- **Listener:** `ag_listener` não entra no índice; linha KPI com nome de listener → `unmatched` motivo `LISTENER`.

### 2.2 Elegibilidade
- `eligible = tenant_id == settings.tenant_id AND is_active = 1 AND enabled = 1`.
- Filtro de ambiente depois, pela mesma função, com `monitored_server.environment`.
- Credenciais **não** afectam elegibilidade.
- **Vista admin:** todas as linhas do tenant; `enabled=0` → `DESACTIVADO`; `is_active=0` → `REMOVIDO_DA_FONTE`. Consulta nova sem `is_active=1` (`inventory_repo.py:42` filtra) [F].

### 2.3 Estados
Estado principal (primeiro que se aplica):

| # | Estado | Fonte | Notas |
|---|---|---|---|
| 1 | `REMOVIDO_DA_FONTE` | `is_active=0` | só admin |
| 2 | `DESACTIVADO` | `enabled=0` | só admin |
| 3 | `OFFLINE` | `SERVER_OFFLINE_GROUPED_VIEW` `Ping_OK=0` (host ou instância), ou `INST_AVAILABILITY_ACTIVE` `Is_Available=0` | — |
| 4 | `SEM_COLETA` | sem linha em `INST_AVAILABILITY_ACTIVE` ou fora da janela de frescura | motivos `NUNCA_RECOLHIDA` / `RECOLHA_PARADA` |
| 5 | `DEGRADADO` | `SERVICE_STATUS_AGG_VIEW` `Services_Down_Count>0` e fresco | recolhedor de serviços parado → `SERVICOS_SEM_DADOS`, nunca verde |
| 6 | `OK` | `Is_Available=1` e fresco | — |

[H] Com o P4 da A1 por fazer, instância em baixo sem evento fica `SEM_COLETA` (honesto, não `OFFLINE`).

Estado de ligação do portal (independente):
- `OK`: entrada local com `username`+`password`, `use_windows_auth` falso, id em `sql_auth_rollout`.
- `SEM_CREDENCIAIS`: sem entrada ou password vazia.
- `SO_TRUSTED`: fora do rollout → hoje o portal liga com Trusted [F `connection_pool.py:778-784`], proibido pela Regra de Ouro #2.
- A regra `password OR use_windows_auth` (`inventory_repo.py:161`) deixa de valer.

### 2.4 Sidebar deixa de esconder
- `/api/v3/servers` devolve todos os elegíveis, sem `require_credentials=True` (`watcherdb_main.py:1155`).
- Campos novos: `availability`, `reasons[]`, `portal_conn`; `inventory_version` no topo. `status: 'ACTIVE'` fixo (`:1193`) passa a estado real.
- Item com `portal_conn != OK` abre painel explicativo e **não chama drill-down** (evita fallback Trusted).
- Outros consumidores de `load_monitored_servers()` mantêm `require_credentials=True` (`inventory_repo.py:270-275`).

## 3. Caminho de escrita da gestão

### O0 (mínima): gestão só leitura + runbook
- Modal passa a tabela de `/api/v3/servers?view=admin` com Activos (defeito) / Todos.
- POST legado atrás de `legacy_sql_servers_config` (desligada → 410 explicativo).
- Runbook corrigido (`RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md:105` diz "nenhum código o lê" — falso).
- Custo 2–3 dias, só portal. Risco baixo. Cumpre mesmo conjunto, consulta de inactivos, estados. Não cumpre incluir/editar/desactivar/reactivar pela UI.
- Convergência após edição manual: sync ≤10 min + cache ≤60 s + sidebar ≤60 s = **≤12 min**.

### O1 (recomendada): pedidos de alteração aplicados pelo collector
- **Portal:** `POST /api/inventory/requests` (`_require_dba`, CSRF, auditoria), grava atómico `inventory_requests/pending/<request_id>.json` com `actor`, `ops[]` (`add|update|disable|enable|restore`), `instance_id`, `patch` (campos permitidos), `expected{}` (valores actuais de `monitored_server`). Sem `remove` (runbook). Sem segredos; credencial de instância nova resolvida no collector ([H] `credential_backend`, `credential_manager_v2.py:1019-1044`, validar com guardião).
- **Collector:** tarefa `apply_inventory_requests` (1 min): (1) lock partilhado com `discover_databases` — hoje relê e grava sem lock (`discover_databases.py:176-187`) [F]; (2) relê canónico; (3) compara `expected` → `CONFLITO`; (4) aplica patch preservando chaves desconhecidas, credenciais, porta, topologia AG; (5) `parse_inventory` strict nos ids tocados → `REJECT:<motivo>` sem gravar; (6) `atomic_write_json` com backup rotativo; (7) sync imediata; (8) ciclo de vida em `metadata.inventory_change_request` (só o collector escreve; DDL aditivo, guardião).
- **Estados visíveis:** `PENDENTE`, `APLICADO` (nome do backup), `SINCRONIZADO` (confirmado lendo `monitored_server`), `FALHOU` (`CONFLITO`/`REJECT`/`IO`/`LOCK_TIMEOUT`), `EXPIRADO` (>15 min, com heartbeat do collector).
- **Convergência:** meta ≤4 min; limite ≤12 min.
- Custo 6–9 dias (V1 + DDL + portal); guardião.
- **Pressuposto [H]:** portal e collector na mesma máquina ou pasta partilhada com ACL — **pergunta ao owner**. Se separados: tabela de pedidos via procedure com EXEC mínimo — quebra "portal só leitura" → **decisão do owner**.

### O2: portal escreve o canónico via módulo V1 importado
- Cai no veto (a); ACL de escrita na pasta V1, acoplamento de empacotamento (PyArmor), lock entre processos, falha com máquinas separadas. Argumento das cifras não se aplica a edições sem segredos, mas lock/ACL/empacotamento mantêm o veto. **Não contestado.**

**Recomendação: O0 já (depois da E6c), O1 a seguir.**

## 4. Dashboard

- `build_fleet_state(inventory, avail_rows, offline_rows, svc_rows, svc_fresh)` → `fleet`: `inventory_version`, `scope`, `total`, `by_state{}`, `by_env{}`, `instances[]`, `unmatched[]`.
- **Invariante:** `OK + DEGRADADO + OFFLINE + SEM_COLETA == total` (partição por `instance_id`).
- **Fim da corrida:** `collect_service_status` deixa de mexer em `instance_availability` (sai `helpers.py:1910-1945`); `collect_*` devolvem linhas; `build_fleet_state` corre após o gather (`intelligence_kpis.py:897-914`) e antes de `build_offline_hostnames` (`:917`).
- **Denominadores:** `Instâncias = fleet.total`; `Online = OK (+DEGRADADO?)`; `Offline = OFFLINE`; `SEM_COLETA` à parte. Decisões do owner: (a) serviço em baixo conta online (assinalado) — hoje conta offline (`helpers.py:1941`); (b) `Disponibilidade % = Online/total` (recomendado) ou `Online/(total−SEM_COLETA)`.
- **Ambiente:** `by_env` do inventário (PRD/QLT/TST/DEV), sem `Undefined`. Conflito com decisão de 07/08 (cartão "Por Ambiente" conta só quem responde, `portal.html:36803-36807`) → nova decisão; proposta: total por ambiente com segmento online.
- **Compatibilidade:** `ok_count/off_count/ok_by_env/off_by_env` derivam de `fleet` com flag `fleet_contract_v2`; JS (`portal.html:36776,36832,36901`) usa `fleet` se existir. Aviso `instances_offline` (A2/A3) lê `off_count` → reprovar em Node.
- **Caches:** snapshot >60 s sai com `fleet` recalculado ou `fleet.stale=true`; corrigir `/refresh` que limpa a cache errada (`intelligence_kpis.py:1123-1125`).

## 5. Plano em etapas (aditivas, com flag; V1/DDL → guardião)

| Etapa | Bloco | Ficheiros/funções | Depende | Resultado | Validação | Rollback |
|---|---|---|---|---|---|---|
| U0 | evidência | Owner: Q1–Q5 como `sql_monitoring`, GET autenticado ×3, data do relato | — | Explica 62/63 | Q4 sem linhas inesperadas | — |
| U1 | contrato | `services/inventory_contract.py`: `norm`, `build_identity_index`, `is_eligible`, `resolve_state`, `portal_conn_state` | — | Contrato puro | `tests/unit/test_inventory_contract.py` (alias em colisão, listener, host multi-instância, ordem de estados, `use_windows_auth` não conta) | apagar |
| U2 | E6c | boot `watcherdb_main.py:172-188` → repo; `alwayson.py:756-910` → repo; `:2298/:2333/:2466` → repo; `:4493-4496` + Excel `~4700` → repo por `ag_name`; POST `:1227` com flag; `except json.JSONEncodeError` (`:1370`,`:1453`) → `TypeError/ValueError`; retirar sync para servers.json local | U1 (`norm`) | Ninguém lê `sql_servers.json` | Testes boot, fallback AlwaysOn, POST 410/flag; contador de leituras do GET legado | `legacy_sql_servers_config=true` |
| U3 | projecção+caches | `InventoryRepo`: `servers_admin()`, `invalidate()`, `version`, `portal_conn`; poll `run_id` de `metadata.server_sync_run` 30 s | U1 | Repo sabe quando mudou | extensões a `test_inventory_repo.py` | poll off = só TTL |
| U4 | contrato dashboard | `services/fleet_state.py` (`build_fleet_state` + cache 30–60 s, `to_thread`) | U1,U3 | Mesmo conjunto para 2 telas | caso H1 ≠ 2; ordens de conclusão → igual | sem uso |
| U5 | dashboard | `intelligence_kpis.py:897-937`, `helpers.py:1224-1344,1883-1948`, `portal.html:36776,36832,36901`, cartão ambiente | U4 + decisões §4 | Instâncias = conjunto | pytest + Node A2/A3 + i18n | `fleet_contract_v2=false` |
| U6 | sidebar | `watcherdb_main.py:1138-1206` (elegíveis, estado, `?view=admin` `_require_dba`); `portal.html:6331-6465` (distintivos, painel, refresh 60 s + `visibilitychange`, `inventory_version`); i18n | U4 | Sidebar mostra sem-credenciais com estado | contrato; Node: clique sem creds não faz fetch | `sidebar_show_uncredentialed=false` |
| U7 | gestão O0 | `portal.html:47289-47878` → tabela só leitura Activos/Todos; runbook | U6 | 3 telas, mesmo conjunto | `v33-modal-auth-gate-checker`, i18n | flag textarea |
| U8 | escrita O1 (V1) | migration 015 `metadata.inventory_change_request` + canónico; `apply_inventory_requests`; lock com `discover_databases`; sync imediata | U2, guardião, co-localização | Collector aplica pedidos | pytest V1 (atómico, backup, lock, CONFLITO, chaves desconhecidas, credenciais intactas, idempotência, REJECT sem gravar); PARSEONLY | tarefa `enabled:false` |
| U9 | escrita O1 (portal) | `POST/GET /api/inventory/requests`; UI estados | U8 | Incluir/editar/desactivar/reactivar na UI | contrato + TestSukita | `inventory_write_enabled=false` |
| U10 | migração | reconciliador só relatório (projecção vs servers.json local vs sql_servers.json 95 vs rollout 62, CSV); `sql_servers.json` → `.ARCHIVED_<data>` pelo owner | U2,U7 | Sem exclusões automáticas | diff revisto pelo owner | renomear de volta |
| U11 | validação | pytest; TestSukita e2e viewer/dba: `set(sidebar) == set(fleet.instances)`, `totI == len`, convergência; TestSprite só laboratório; prompt V6 | todas | Gate de release | `/release-check` | — |

## 6. Riscos e pendências

Riscos:
1. Avisos críticos (`instances_offline`, A2/A3) mudam de comportamento — flag + prova Node.
2. Mostrar sem-credenciais pode activar Trusted_Connection em drill-down [F `connection_pool.py:778-784`] — bloquear frontend e backend.
3. Perda de alterações no canónico (3 escritores) — lock + `expected` + hash antes do `os.replace`; edição manual fora do lock (runbook avisa).
4. Portal e collector em máquinas diferentes no cliente [H] — excepção na BD (decisão owner) ou O0 permanente.
5. Nomes que não casam (alias, listener) → falso `SEM_COLETA` — `unmatched[]` visível + Q4 antes de U5.
- Também: snapshot 24 h com conjunto antigo; Live Monitoring até 1 h atrás.

Pendências do owner:
- Evidência: Q1–Q5; GET autenticado ×3; data/ambiente/captura do relato.
- Decisões: (a) serviço em baixo online/offline; (b) denominador da %; (c) cartão "Por Ambiente"; (d) topologia portal/collector e excepção de escrita na BD; (e) defeito da flag do POST legado em release comercial; (f) credencial de instâncias novas via `credential_backend`.
- Tier: Std + Pro.
