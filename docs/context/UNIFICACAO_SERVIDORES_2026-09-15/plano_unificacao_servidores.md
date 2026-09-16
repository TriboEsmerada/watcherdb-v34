# Plano de unificação do inventário de servidores — WatcherDB V3.4

Data: 2026-09-15 · Estado: **diagnóstico + plano, nada implementado** · Tier: Std (+Pro por herança)
Orquestrador + council: Explore, watcherdb-v1-intel-specialist (guardião, veto), watcherdb-v33-specialist, qa-externo, architecture-advisor, challenger.
Relatórios de suporte (mesma pasta): `00_INDICE.md` (verificação cruzada), `01`–`06`.
Legenda: **[F]** facto verificado no código/ficheiros/logs · **[H]** hipótese · **[P]** pendente de evidência do ambiente.

Notas de entrada: `unificaservers.md` não existe no disco — o requisito usado é o texto do pedido do owner. `AGENTS.md` do WatcherDB não existe; o TestSprite está rejeitado para PRD por soberania (`docs/context/PLANO_TESTSUKITA_2026-09-09.md:3,54`), por isso a validação usa o TestSukita e o TestSprite só em laboratório.

---

## 1. Diagnóstico

### 1.1 Resposta curta
- **A divergência 63 vs 62 não está provada como defeito de inventário.** Nos logs do V3.4 (484 linhas) e do V3.3 (18), a barra lateral devolveu sempre `63 servers (source=db)` [F]. Os números que aparecem são outros:
  - o "Online"/"Instances OK" do dashboard deu 62 com 1 Off, o que faz um total de 63 (`logs/service_stderr.log.1:55205-55207`, `:94064-94066`) [F];
  - a 20/08 existiu a forma exacta "dashboard 63 / sidebar 62" (OATXP01 sem credenciais locais antes do `provision_oatxp01_v33`, `CONTEXT.md:307-309`) [F].
  - A causa **concreta do relato fica pendente** de T0/T1 (§8) [P].
- **Existem defeitos estruturais reais e verificados**, independentes do relato:
  1. o total do dashboard é **soma** de duas contagens de vistas KPI, não o conjunto do inventário, e tem **condição de corrida**;
  2. a gestão edita um ficheiro que **não chega** à barra lateral nem ao dashboard;
  3. ainda há um **terceiro conjunto vivo de 95 ids** (Space/Backup);
  4. há um caminho para **Trusted_Connection** que viola a Regra de Ouro #2.

### 1.2 As três telas (detalhe em `01`)

| Tela | JS | Endpoint | Serviço | Fonte | Filtros | Cache |
|---|---|---|---|---|---|---|
| **Gerenciar servidores** | `openSettingsModal` / `saveSqlServersConfig` (`portal.html:47289-47313`, `:47782-47857`) | `GET/POST /api/config/sql-servers` (`watcherdb_main.py:1208`, `:1227`; `_require_dba`) | — (código inline) | `config/sql_servers.json` (**95**) + sync para `config/servers.json` local | nenhum (JSON bruto num textarea) | nenhuma; `app.state.sql_servers_config` só no arranque (`:172-185`) |
| **Barra lateral** | `loadServers` (`portal.html:6331-6465`) | `GET /api/v3/servers` (`watcherdb_main.py:1138-1206`) | `InventoryRepo.servers(enabled_only=False, require_credentials=True)` (`:1155`) | `metadata.monitored_server` (`tenant_id='default' AND is_active=1`, `inventory_repo.py:42`); fallback `config/servers.json` | sem credenciais locais (`inventory_repo.py:176-182`); `enabled` falso (`watcherdb_main.py:1164`); id vazio (`:1168`); excepção salta item (`:1199`); pesquisa ≥2 car. (`portal.html:7029`) | repo 60 s, só TTL (`inventory_repo.py:134-139`) |
| **Dashboard ("Instâncias" / Disponibilidade)** | `portal.html:36776`, `:36832`, `:36901` | `GET /api/intelligence-kpis/dashboard` (`intelligence_kpis.py:940-969`) | `collect_instance_availability` + `collect_service_status` (`helpers.py:1224-1344`, `:1883-1948`) no mesmo `asyncio.gather` (`intelligence_kpis.py:897-913`) | `KPI_MSSQL_INST_AVAILABILITY_ACTIVE`, `KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW`, `KPI_MSSQL_SERVICE_STATUS_AGG_VIEW` — **nenhuma é inventário** | filtro de ambiente soma `ok_by_env`/`off_by_env`, `Undefined` fica fora (`portal.html:36831`) | `_dashboard_cache` 60 s + snapshot em disco 24 h (`helpers.py:41-110`); `/refresh` limpa outra cache (`intelligence_kpis.py:1123-1125`) |

**Fórmula efectiva do total** [F]:
```
Instâncias = ok_count + off_count                                 (portal.html:36776/36832/36901)
ok_count   = COUNT(DISTINCT Instance) INST_AVAILABILITY_ACTIVE WHERE Is_Available=1   (helpers.py:1228-1234)
off_count  = COUNT(DISTINCT Instance) SERVER_OFFLINE_GROUPED_VIEW WHERE Ping_OK=0     (helpers.py:1238-1244)
           + instâncias com Services_Down_Count>0 não presentes na lista offline      (helpers.py:1935-1941)
```
- **Soma, não união.** Uma instância com `Is_Available=1` e serviço em baixo conta nas duas parcelas.
- **Mistura unidades.** O offline é por `Server_Name` (host); o online é por `Instance`.
- **Corrida.** `helpers.py:1335` reescreve `off_count`. O resultado depende de qual das duas funções do gather termina primeiro.

### 1.3 Fontes, escritores e projecções (detalhe em `02`/`03`)

| Artefacto | Papel real hoje | Quem escreve |
|---|---|---|
| `WATCHERDB INTELLIGENCE V1/config/servers.json` (63, `enabled` explícito, EncryptionManager) | **Canónico** do collector, lido por `InventoryProvider.load()` (`inventory_provider.py:478`) | à mão pelo runbook; `discover_databases.py` (atómico, **sem lock**, `:176-187`) |
| `metadata.monitored_server` / `_database` | Projecção; sync de 10 min via `usp_sync_monitored_servers` (INSERT/UPDATE/REACTIVATE/DEACTIVATE soft, guarda de 20%) (`INVENTORY_SYNC_COMPONENT.sql:52-748`) | só o collector |
| `metadata.server_config` | Projecção secundária (coverage gap, `CHECK_AVAILABILITY_COVERAGE_GAP.sql:74-75`) | sync |
| `WATCHERDB_V3.4/config/servers.json` (63, DPAPI, gitignored) | Espelho de credenciais do `connection_pool` + fallback do repo | POST da gestão (sync UPSERT+DELETE) |
| `WATCHERDB_V3.4/config/sql_servers.json` (95, sem `enabled`, sem credenciais; inclui listeners/farms) | Legado **ainda lido**: arranque, Space/Backup, fallback AlwaysOn, `/api/servers` fallback | POST da gestão |
| `config/sql_auth_rollout.json` (62 = servers.json − OATXP01) | Allowlist de SQL Auth; fora dela o pool usa Trusted (`connection_pool.py:766-784`) | owner |
| `config/alwayson_inventory.json` (42) | Mapa AG ↔ instância (`alwayson.py:706-752`) | — |
| `WATCHERDB_V6/config/servers.json` | 4.ª cópia, drift-check próprio | não verificado |

### 1.4 Identidade: host, instância, alias, listener
- **Instância** = `instance_id` no formato `HOST_INST`, único por `(tenant_id, instance_id)` na BD [F]. A sidebar conta instâncias.
  - São 63 instâncias para 58 hosts [F].
  - Hosts com várias instâncias: SQLHDSQLT105 ×4, SQLHDSQLT103 ×2, SQLHDSQLT301 ×2.
- **Host** = coluna `host`. Só o offline agrega por host.
- **Alias** = `sql_servername_alias`. É lido mas **não é usado em nenhum match** [F].
  - Caso `SQLHDSSQLT301_I01` (host `SQLHDSQLT301`): a identidade está partida entre dois nomes, com duas linhas em `INST_ENVS` (`PROMPT_V1_NOME_CORROMPIDO_SQLHDSSQLT301_2026-08-31.md`).
- **Listener AG** = atributo `ag_listener` de uma instância, sem linha própria [F]. O `sql_servers.json` de 95 tinha listeners e farms como "servidores" (`CONTEXT.md:301`).

**Normalização inconsistente** [F]:

| Onde | Regra aplicada |
|---|---|
| Credenciais locais | `strip().upper().replace("\\","_")` (`inventory_repo.py:162`) |
| Lado BD | só `upper()` (`:179`) |
| Sync da gestão | id exacto (`watcherdb_main.py:1288`) |
| `collect_service_status` | comparação exacta (`helpers.py:1921-1926`) |
| `connection_pool` | procura por **host sozinho** (`connection_pool.py:546-549`), que é ambígua em hosts com várias instâncias |

### 1.5 Comparação dos conjuntos (ficheiros locais; BD e runtime autenticado pendentes)

| Conjunto | N | Observação |
|---|---|---|
| canónico V1 | 63 | `enabled` explícito nos 63 |
| `config/servers.json` V3.4 | 63 | `enabled` ausente em 61 (default True), 0 falsos, 0 sem credenciais |
| simulação `/api/v3/servers` pelo ficheiro | 63 | 0 excluídos |
| logs `/api/v3/servers` (db) | 63 | nunca 62 |
| `sql_servers.json` | 95 | 33 ids só aqui (32 host\instância; 12 test / 11 prod / 10 quality) |
| interseção por id `servers.json` ∩ `sql_servers.json` | 62 | falta `SQLHDSSQLT301_I01`, que em `sql_servers.json` tem id com um "S" |
| `sql_auth_rollout.json` | 62 | = servers.json − OATXP01 |
| dashboard "Instances OK" (arranques) | 50 / 54 / 62 / 63 | varia com a recolha |
| BD `metadata.monitored_server` | [P] | Q1 (§8) |

**Registos presentes só num conjunto, com motivo** [F salvo indicação]:
- `SQLHDSSQLT301_I01`: está em servers.json e não em sql_servers.json, por causa da divergência de alias.
  - **Risco latente:** gravar hoje a modal apaga-o do servers.json local → fica sem credenciais → sai da sidebar (63→62).
  - A modal não é gravada desde 29/04 (`sql_servers.json.backup` com essa data; não existe `.backup_pre_sync`), por isso **não é a causa observada**.
- **33 ids** só em sql_servers.json: fora do inventário. Mesmo assim são **iterados** pelo Space dashboard (`watcherdb_main.py:2295-2298`) e pelo Backup summary (`:2465-2466`). Não têm credenciais nem allowlist, o que aponta para Trusted [F no código; H quanto a execução efectiva].
  - Gravar a modal inseri-los-ia no servers.json local com `use_windows_auth: True  # default seguro` (`:1334`), e o repo passaria a contá-los "com credenciais" (`inventory_repo.py:161`).
- **OATXP01**: está em tudo excepto no rollout (fica em Trusted por decisão de 09/09, `CONTEXT.md:394-395`).

### 1.6 Hipóteses para o relato (detalhe em `06` §1)

| # | Hipótese | Probabilidade | Discriminante |
|---|---|---|---|
| H-A | O "62" era o Online/Instances OK do dashboard e não o contador da sidebar | Alta | T0 (qual rótulo) |
| H-0820 | Relato da janela de 20/08 (OATXP01 sem credenciais locais) | Média | T0 (data) |
| H1 | Dupla contagem OK + serviço em baixo | Média como defeito | T1 / T2 |
| H-search | Pesquisa activa na sidebar | Baixa | T0 |
| H-rollout | Confusão com os 62 do rollout / GRANTs | Baixa | T0 |

### 1.7 Outros defeitos verificados (entram no plano)
- **Gravação da gestão:**
  - não é atómica;
  - usa um único backup, sobrescrito a cada gravação;
  - não tem lock;
  - o sync é fail-open com `success: True` (`watcherdb_main.py:1359-1368`).
- `except json.JSONEncodeError` não existe no módulo `json` (`watcherdb_main.py:1370`, `:1453`). Mascara o 400 e devolve 500.
- A UI diz "Apenas administradores" (`portal.html:47815`), mas o backend aceita dba (`:1234`).
- O runbook diz que "nenhum código lê" o `sql_servers.json` (`RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md:105`). É falso.
- Leitores que contornam o repo sem necessidade:
  - `database_discovery_service.discover_all` (`:194-198`);
  - `watcherdb_alwayson_check.py:126`;
  - hardcoded `watcherdb_main.py:4493-4496`;
  - Excel em `~4700`.
- **E6c** (5 itens do plano de 19/08) está aberto desde 21/08 (`03` §1).

---

## 2. Decisão de arquitetura

### 2.1 Papéis
- **Fonte autoritativa de escrita:** o `servers.json` **canónico do V1**, escrito só pelo lado do collector.
  - O requisito "persistir em servers.json" cumpre-se **neste** ficheiro.
  - O `config/servers.json` do portal **não é canónico**; é configuração local de ligação.
- **Projecção de leitura única do portal:** `metadata.monitored_server`, via `InventoryRepo`. O portal nunca escreve nela.
- **Caches:** `InventoryRepo` (60 s) e `_dashboard_cache` + snapshot. Passam a ser invalidadas por evento (novo `run_id` da sync), não só por TTL.
- **Configuração local de ligação:** `config/servers.json` local (credenciais DPAPI, porta) e `sql_auth_rollout.json` (modo de autenticação). **Nunca** definem elegibilidade.
- **Legado:** `sql_servers.json`. Deixa de ser lido e é arquivado depois de uma release sem leituras.

**Vetos do guardião mantidos** (sem evidência nova contra):
- (a) o portal escrever directamente no canónico;
- (b) o portal escrever em `metadata.monitored_server`.

### 2.2 Contrato partilhado (`services/inventory_contract.py`, puro)
- **Identidade.**
  - `norm(x) = x.strip().replace("\\","_").upper()`, a mesma regra do provider V1.
  - Chave = `instance_id`.
  - Índice de match KPI → inventário: `instance_id`, `host_instance` e `sql_servername_alias`.
  - Uma chave que aponte para dois ids fica em `unmatched`, **nunca se funde**.
  - Listener não entra no índice (`unmatched`, motivo `LISTENER`).
  - Índice por host só para sinais ao nível do host, como o ping.
- **Elegibilidade:** `tenant_id='default' AND is_active=1 AND enabled=1`.
  - Credenciais e recolha **não** afectam a elegibilidade.
  - O filtro de ambiente é aplicado depois, com `monitored_server.environment`.
- **Estado de disponibilidade** (precedência):
  1. `OFFLINE`;
  2. `SEM_COLETA` (`NUNCA_RECOLHIDA` / `RECOLHA_PARADA`);
  3. `DEGRADADO` (serviço em baixo; sem dados de serviços → `SERVICOS_SEM_DADOS`, nunca verde);
  4. `OK`.
- **Visão administrativa** acrescenta `DESACTIVADO` (`enabled=0`) e `REMOVIDO_DA_FONTE` (`is_active=0`).
- **Estado global de recolha.** Se o heartbeat do collector estiver velho ou mais de X% das instâncias ficarem sem recolha ao mesmo tempo:
  - estado único `RECOLHA_PARADA`;
  - % = "—";
  - sem alertas por instância (evita o vermelho falso do incidente DNS de 15/09).
- **Estado de ligação do portal** (independente do anterior):
  - `OK`: tem username + password, `use_windows_auth=false` e está no rollout;
  - `SEM_CREDENCIAIS`;
  - `SO_TRUSTED`.
  - `use_windows_auth=True` **deixa de contar como credencial**.
  - `portal_conn != OK` ⇒ nenhum drill-down constrói connection string (Regra de Ouro #2).

### 2.3 Caminho de escrita — recomendação faseada
Os dois pareceres divergem na etapa final; **esta é a minha recomendação**:

1. **Agora — gestão só de leitura (E6c-3).**
   - Tabela a partir do contrato: visão padrão **Activos** = conjunto da sidebar e do dashboard; visão **Todos** (dba/admin) com inactivos identificados.
   - POST legado atrás de flag (410 explicativo).
   - "Reactivar" nesta fase = instrução guiada para o runbook/CLI, não um botão que escreve.
2. **A seguir — CLI de provisionamento no V1**, corrida pelo DBA na máquina do collector:
   - operações `add | update | disable | enable`;
   - dry-run com diff e escrita atómica (tmp + `os.replace`) com backup rotativo;
   - lock partilhado com `discover_databases` e compare-and-swap por hash;
   - preserva chaves desconhecidas, credenciais, porta e topologia;
   - trata as 3 peças fora do canónico: espelho DPAPI, rollout e aviso de GRANTs;
   - sync imediata.
   - Cumpre "incluir/editar/desactivar/reactivar reflectem nas três telas em ≤12 min sem restart", sem superfície de rede nem credenciais no browser.
3. **Condicional — pedidos de alteração pelo portal, aplicados pelo collector** (O1 do `05`). **Só** com decisão do owner sobre:
   - (i) procura real;
   - (ii) topologia portal/collector (mesma máquina? pasta partilhada com ACL?);
   - (iii) entrada na FEATURE_MATRIX;
   - (iv) auditoria de segurança (credenciais nunca pelo browser).

**Porquê:**
- Nenhum fluxo de adição fica completo dentro do portal (os GRANTs exigem sempre SSMS).
- A frequência de mudança é baixa.
- O transporte portal→collector não existe.
- O valor da opção 3 tem tecto; o risco não (`06` §2).

**Contra-argumento registado:** a UI de escrita é pedida explicitamente. Se o owner a mantiver como obrigatória, a opção 3 é a única compatível com os vetos.

### 2.4 Dashboard
- `build_fleet_state(...)` corre **depois** do `gather` e produz uma **partição por `instance_id`** do conjunto elegível:
  - campos: `inventory_version`, `total`, `by_state`, `by_env`, `instances[]`, `unmatched[]`;
  - invariante: `OK + DEGRADADO + OFFLINE + SEM_COLETA == total`.
- `collect_service_status` deixa de alterar `instance_availability` (acaba a corrida).
- `ok_count`/`off_count` são mantidos por compatibilidade, derivados de `fleet`, com a flag `fleet_contract_v2`.
- Os rótulos passam a distinguir **instâncias** de **hosts**.

---

## 3. Etapas de implementação

Todas são aditivas, atrás de flag, com rollback por flag. Tudo o que tocar no V1 ou em DDL passa pelo guardião (veto). As mudanças de BD seguem a regra 2 (canónico `INSTALACAO_COMPLETA_UNIFICADA.sql` + docs). Cada etapa fecha com commit e prompt de propagação ao V6.

| # | Bloco do requisito | Ficheiros / funções | Depende | Resultado esperado | Validação | Rollback |
|---|---|---|---|---|---|---|
| **U0** | Evidência | owner: T0, T1, Q1–Q5 como `sql_monitoring` (§8) | — | Causa do relato atribuída ou descartada | Q4 interpretada | — |
| **U1** | Contrato + identidade/elegibilidade | novo `services/inventory_contract.py` (`norm`, `build_identity_index`, `is_eligible`, `resolve_state`, `portal_conn_state`, `collection_health`) | — | Regras numa só função pura | `tests/unit/test_inventory_contract.py`: alias em colisão (SS301), listener, host com 4 instâncias, precedência dos estados, `use_windows_auth` não conta, `RECOLHA_PARADA` | apagar ficheiro (sem consumidores) |
| **U2** | Integração: dashboard | `api/routers/intelligence_kpis.py:897-937`; `helpers.py:1224-1344`, `:1883-1948` (retirar `:1910-1945`); novo `services/fleet_state.py`; `portal.html:36776`, `:36832`, `:36901`; cartão por ambiente; corrigir `/refresh` (`intelligence_kpis.py:1123-1125`) | U1 + decisões D2–D4 | `Instâncias` = conjunto partilhado; sem dupla contagem; determinístico | T2 (duas ordens do gather → payload igual); caso H1 ≠ 2; prova Node do aviso `instances_offline` (A2/A3); i18n pt/en/es + pt-BR | `fleet_contract_v2=false` |
| **U3** | Integração: sidebar | `watcherdb_main.py:1138-1206` (elegíveis + estado; array aditivo `unavailable[]`; `?view=admin` com `_require_dba`); `services/inventory_repo.py:151-186` (nova regra de credencial); `portal.html:6331-6465` (distintivo de estado, painel explicativo, item sem ligação não clicável, refresh 60 s + `visibilitychange`); bloqueio no backend antes de `_build_connection_string` para `portal_conn != OK` (`api/connection_pool.py:750-790`) | U1 | Sidebar mostra todas as elegíveis, com estado; nenhuma escondida | contrato do endpoint; `tests/test_functional_acceptance.py:127-275` verde; C6 (sem Trusted); Node: clique sem credenciais não faz fetch | `sidebar_show_unavailable=false` |
| **U4** | Caminho único de gestão (leitura) + E6c-3 | `portal.html:47289-47878` → tabela Activos/Todos a partir de `?view=admin`; `watcherdb_main.py:1227-1375` POST atrás de `legacy_sql_servers_config` (410); corrigir `except json.JSONEncodeError` (`:1370`, `:1453`) → `(TypeError, ValueError)`; retirar o sync para o servers.json local; texto dba/admin coerente; corrigir `RUNBOOK_ADICIONAR_REMOVER_SERVIDOR.md:105` | U3 | Gestão (Activos) = sidebar = dashboard; inactivos consultáveis e marcados | `v33-modal-auth-gate-checker`; teste do POST 410/flag; C1 | flag volta a textarea + POST |
| **U5** | Compatibilidade/migração dos consumidores de `sql_servers.json` (E6c-1/2/4) | arranque `watcherdb_main.py:172-188`; Space `:2295-2298`, `:2332-2333`; Backup `:2465-2466`; test-connection `:1944-1970`; `/api/servers` fallback `:3480-3499`; `api/routers/alwayson.py:756-910` (+ caminho relativo); hardcoded `:4493-4496`; Excel `~4700`; `services/database_discovery_service.py:194-198`; `modules/monitoring/watcherdb_alwayson_check.py:126`; rotas sombra `:5355`, `:5400` | U1 | Nenhum leitor de `sql_servers.json` em runtime; Space/Backup passam de 95 para o conjunto elegível (**mudança visível, anotar no CHANGELOG**) | grep de consumidores = 0 (regra de fecho de 21/08); testes novos de arranque, fallback AlwaysOn e Space; contador de leituras do legado a 0 numa release | `legacy_sql_servers_config=true` repõe as leituras |
| **U6** | Projecção na BD + invalidação de caches | `InventoryRepo`: `servers_admin()` (consulta sem `is_active=1`), `invalidate()`, `version`; poll de `metadata.server_sync_run.run_id` a cada 30 s → invalida repo + `fleet`; `portal.html`: comparar `inventory_version` entre sidebar e dashboard | U1 | Convergência por evento; prazo observável | extensões a `tests/unit/test_inventory_repo.py`; C4 (≤12 min p95, sem restart) | poll desligado = só TTL |
| **U7** | Persistência (escrita) — CLI V1 | repo V1: `tools/inventory_cli.py` (nome a acordar) com `add/update/disable/enable`, `--dry-run` diff, `atomic_write_json` + backup rotativo com timestamp, lock partilhado com `collectors/discover_databases.py`, CAS por hash, `parse_inventory` strict nos ids tocados, preservação de chaves desconhecidas/credenciais/porta/AG, espelho DPAPI V3.4 + rollout + aviso de GRANTs, sync imediata; erro → exit≠0 com mensagem, nada gravado | U5, guardião | Incluir/editar/desactivar/reactivar reflectem nas 3 telas em ≤12 min | pytest V1: atomicidade (kill a meio), backup, lock/concorrência, CONFLITO, REJECT sem gravar, chaves desconhecidas preservadas, credenciais intactas, idempotência; C4 com instância de teste | não usar a CLI; restaurar backup |
| **U8** | Persistência pela UI (condicional, O1) | só após D1: `POST/GET /api/inventory/requests`; tarefa V1 `apply_inventory_requests` reutiliza o núcleo do U7; `metadata.inventory_change_request` (DDL aditivo + canónico); estados PENDENTE/APLICADO/SINCRONIZADO/FALHOU/EXPIRADO visíveis ao operador | U7, D1, guardião, auditoria de segurança | Gestão pela UI sem disputa com o collector | contrato + TestSukita + testes V1 do U7 | `inventory_write_enabled=false`; tarefa `enabled:false` |
| **U9** | Migração reversível + reconciliação | script **só de relatório** (CSV): projecção vs servers.json local vs `sql_servers.json` (95) vs rollout (62) vs `alwayson_inventory` (42), com motivo por id; owner decide caso a caso (33 ids: listener/farm/descomissionado/em falta); `sql_servers.json` → `.ARCHIVED_<data>` pelo owner; SS301: decidir com o guardião (alias vs rename no V1) | U5, U4 | Nenhuma exclusão automática; histórico KPI intacto | diff revisto pelo owner | renomear de volta; flag legado |
| **U10** | Validação + release | pytest (contrato, fleet, repo, endpoints, POST legado); TestSukita e2e com conta viewer/dba (C1–C8); TestSprite só em laboratório fora da TAP, sem upload de código; `/release-check`; prompt V6 (4.ª cópia do inventário); CHANGELOG (mudança da base da %) | todas | Gate GO/NO-GO | §5 | — |

**Ordem recomendada:** U0 → U1 → U2 → U3 → U4 → U5 → U6 → U7 → (U8 se D1) → U9 → U10. U2 e U3 não dependem de E6c; U5 é condição para declarar "inventário unificado".

---

## 4. Riscos

| # | Risco | Mitigação |
|---|---|---|
| R1 | O aviso crítico `instances_offline` (A2/A3) muda de comportamento com a partição honesta | flag; prova Node antes de ligar; `RECOLHA_PARADA` suprime alertas por instância |
| R2 | Mostrar instâncias sem ligação dispara drill-down em Trusted_Connection (Regra de Ouro #2) | não clicáveis + bloqueio no backend + teste C6 |
| R3 | Perda de alterações no canónico (runbook, `discover_databases`, CLI) | lock + CAS por hash; runbook avisa para não editar à mão durante a CLI |
| R4 | Alias/listener não casam → `SEM_COLETA` falso permanente (SS301) | `unmatched[]` visível; Q4 antes do U2 |
| R5 | Space/Backup mudam de 95 para o conjunto elegível; relatórios mensais deixam de ser comparáveis (base da %) | CHANGELOG + nota ao cliente; decisão D3 |
| R6 | Portal e collector em máquinas diferentes no cliente (bloqueia U8 por ficheiro) | U7 não depende disso; U8 só após D1 |
| R7 | Snapshot 24 h mostra um conjunto antigo; Live Monitoring (`INST_ENVS`) até 1 h atrás | `fleet.stale`; lote próprio para o Live Monitoring |
| R8 | Fechar E6c sem testes (arranque/alwayson sem cobertura) | testes novos no U5 antes de mexer; restart + prova em browser |

---

## 5. Validação — critérios de aceite mensuráveis

Ids normalizados `UPPER(REPLACE(LTRIM(RTRIM(x)),'\','_'))`. **INV** = `metadata.monitored_server` com `tenant_id='default' AND is_active=1 AND enabled=1`, lido como `sql_monitoring`.

| # | Critério | Prova | Falha |
|---|---|---|---|
| C1 | `ids(sidebar.servers ∪ sidebar.unavailable) = ids(gestão[Activos]) = ids(fleet.instances) = INV`, com diferença simétrica vazia no mesmo escopo | teste de contrato + query ao vivo + TestSukita | qualquer id a mais/menos (totais iguais com ids trocados também é falha) |
| C2 | Partição disjunta; soma dos estados = \|INV\|; ids reportados fora do INV só em `unmatched` | Q4 sem `in_ok=1 AND (in_off=1 OR in_svc_down=1)`; unitário OK + serviço em baixo | `total` > \|INV\| |
| C3 | Determinismo | duas ordens de conclusão do gather → payload igual; 5 amostras espaçadas >60 s sem mudança → igual | variação |
| C4 | Convergência ≤12 min p95 após add/edit/disable/enable, sem restart | instância de teste pela CLI; T(sync) → T(3 telas) | >15 min ou restart |
| C5 | Falha do collector não é saudável nem vermelho em massa | DEV: heartbeat parado + 30% sem recolha → `RECOLHA_PARADA`, % "—", 0 alertas por instância | alerta por instância ou % calculada |
| C6 | Regra de Ouro #2 | clique em instância sem ligação não chama `_build_connection_string`; 0 `Trusted_Connection` nos logs do ensaio | qualquer tentativa |
| C7 | Retrocompatibilidade | `tests/test_functional_acceptance.py:127-275` e `tests/unit/test_inventory_repo.py` verdes; `ok_count/off_count` mantidos; campos aditivos | contrato alterado |
| C8 | Filtro por ambiente fecha | soma dos ambientes (+ sem ambiente) = total sem filtro | diferença ≠ 0 |
| C9 | Filtros de visualização não alteram o cadastro | pesquisa/ambiente/visão só GET; hash do canónico e `monitored_server` inalterados | qualquer escrita |
| C10 | Persistência preserva dados | CLI: chaves desconhecidas, credenciais, porta e AG iguais antes/depois (diff); kill a meio → ficheiro íntegro + backup | perda de campo ou ficheiro truncado |

**TestSukita (e2e, 8434, conta viewer/dba):** C1, C3, C4, C8 e C9, e estados sem métricas nunca verdes. TC-012/TC-013 isolados **não** comprovam este requisito.
**TestSprite:** só em laboratório (C1/C8), conforme `PLANO_TESTSUKITA_2026-09-09.md:54`.

---

## 6. Rollback e recuperação

- **Portal (U2–U6):** cada etapa tem flag. Desligar a flag repõe o comportamento actual sem migração de dados. `ok_count/off_count` e `/api/v3/servers.servers[]` continuam presentes.
- **Legado (U4/U5/U9):**
  - `legacy_sql_servers_config=true` repõe as leituras e o POST;
  - o arquivo é por renomeação (`.ARCHIVED_<data>`), reversível;
  - nenhuma linha de `metadata.*` ou do histórico KPI é apagada.
- **Canónico (U7/U8):** backup rotativo com timestamp antes de cada escrita. Para restaurar:
  1. copiar o backup para `servers.json`;
  2. correr a sync;
  3. confirmar `monitored_server` com Q1.
  - A sync só desactiva em soft (`is_active=0`) e tem a guarda de 20%, por isso um ficheiro errado não apaga histórico.
- **BD (U8):** DDL aditivo (tabela nova). O rollback é desligar a tarefa; a tabela fica sem uso. Sem DROP automático.
- **Falha de persistência:** a CLI sai com código ≠0 e nada gravado. A UI (U8) mostra `FALHOU:<motivo>`. Nunca fail-open.

---

## 7. Decisões do owner (com recomendação)

| # | Decisão | Recomendação |
|---|---|---|
| D1 | Gestão com escrita pela UI (U8) ou só leitura + CLI | **Só leitura + CLI agora**; U8 apenas com procura provada, topologia confirmada, entrada na FEATURE_MATRIX e auditoria de segurança |
| D2 | Serviço em baixo conta como online ou offline | **Online com estado DEGRADADO** (hoje conta offline, `helpers.py:1941`) |
| D3 | Denominador da disponibilidade % | **Online / total elegível** (conservador); `SEM_COLETA` mostrado à parte |
| D4 | Cartão "Por Ambiente" (decisão de 07/08: só quem responde) | total por ambiente com segmento online |
| D5 | SS301: alias no inventário vs corrigir o nome no V1 | decidir com o guardião; até lá, match por alias no contrato |
| D6 | Destino dos 33 ids só em `sql_servers.json` | revisão caso a caso no relatório U9; sem inclusão automática |
| D7 | OATXP01 fora do rollout (Trusted) com instâncias sem ligação bloqueadas | manter fora; aparece com `portal_conn=SO_TRUSTED`, não clicável |
| D8 | Valor por omissão da flag do POST legado numa release comercial | desligado (410) |

---

## 8. Pendências de evidência (antes de U2)

1. **T0 (owner, custo zero):** data, hora e porta do relato; qual rótulo mostrava 62 (`SERVIDORES (N)` ou "Online"); pesquisa vazia? Captura, se houver.
2. **T1 / Q1–Q5 (owner, `sql_monitoring`, só leitura):** SELECTs em `04_CONJUNTOS_IDS_qa-externo.md` §5. Leitura: `in_ok=1` com `in_off=1` ou `in_svc_down=1` ⇒ H1 activa hoje; `in_inv=0` com `in_ok=1` ⇒ nome que não casa (alias).
3. **Runtime autenticado:** GET a `/api/v3/servers` e `/api/intelligence-kpis/dashboard` com conta viewer/dba, amostras espaçadas >60 s (a cache é de 60 s).
4. **Definições instaladas** de `SERVER_OFFLINE_GROUPED_VIEW` e `INST_AVAILABILITY_ACTIVE` (Q5): A1 vs canónico antigo.
5. **Topologia no cliente:** portal e collector na mesma máquina? (só relevante para D1/U8)
6. **4.ª cópia V6:** estado não verificado.
