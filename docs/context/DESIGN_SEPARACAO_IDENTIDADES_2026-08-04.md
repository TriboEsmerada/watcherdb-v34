# DESIGN — Separação de identidades na WatcherDB_Intelligence

Data: 2026-08-04 · Owner + Claude · Origem: FIND-20260804-104 (P1 security)
Checkpoint de rollback: tag `checkpoint-pre-thresholds-20260804` (código);
BD sem alterações desta wave até o owner executar.
Estado: **DESIGN COMPLETO + DIFERIDO (decisão owner 04/08).** 4 pareceres
convergentes. **O db_owner de `sql_monitoring` é INTENCIONAL e mantém-se
até ao fim do desenvolvimento da aplicação** — é trade-off consciente do
owner (menos atrito de permissões durante o dev), não descuido. Esta wave
executa-se na fase de **hardening pré-produção/pré-1º-cliente**; o design
abaixo fica pronto a correr nessa altura. Zero DDL/código aplicado. Ver
FIND-20260804-104 (status: deferred).

---

## 1. O problema (verificado na BD viva, 2026-08-04)

`sql_monitoring` — definida no CLAUDE.md (Regra de Ouro #2) como "única
conta autorizada a ligar a DBs, e só faz CONSULTAS" — é na realidade
membro de **db_owner + db_datareader + db_datawriter** na
WatcherDB_Intelligence. Pode dropar tabelas. Os GRANTs granulares do
canonical são teatro enquanto o db_owner existir. Finding de primeira
página numa auditoria banking.

## 2. Facto-chave confirmado (muda/valida o desenho)

**Autenticação é SQL Auth, não Windows Auth** (`config/servers.json`:
`use_windows_auth: false`, `username: sql_monitoring`). Logo a separação
por logins SQL é viável — a "login" não é uma conta AD partilhada.

**Dois papéis distintos do `sql_monitoring` hoje** (mesma credencial):
- **A) Ler DMVs nos 62 servidores monitorizados** — aí é leitura pura
  (VIEW SERVER STATE); o problema P1 NÃO está aqui.
- **B) Escrever na Intelligence master** — aqui é db_owner. É este o alvo.

Só o papel B precisa de cirurgia. A separação natural: a credencial que
escreve na master ≠ a que lê DMVs remotas ≠ a que o portal usa.

## 3. Inventário de escritas na Intelligence (papel B) — mapeado por mim

### 3.1 Portal V3.3 (api/routers) — tabelas de controlo/app, NUNCA STG
| Ficheiro | Tabelas | Operações |
|---|---|---|
| `kpi_mute.py` | `WDB_KPI_MUTE` | MERGE, DELETE |
| `auth_compat.py` | `WatcherDB_Users`, `WatcherDB_Token_Blacklist` | INSERT/UPDATE/DELETE |
| `collectors.py` | `collector_task_overrides`, `collector_toggle_audit`, `collector_run_requests`, `collector_manual_runs` | MERGE/INSERT/DELETE |
| `performance.py` | `performance_investigations`, `performance_action_history` | INSERT |
| `auth_service.py` | `WatcherDB_User_Preferences`, `WatcherDB_Auth_Log`, `WatcherDB_System_Config` | INSERT/UPDATE |
| (futuro) | `WDB_KPI_THRESHOLDS` (Fase 1) | INSERT/UPDATE |

→ conjunto FECHADO de ~13 tabelas `WDB_*`/app. Candidato a login
**`watcherdb_app`**.

**CORRECÇÃO do 3º parecer (gotcha que quebra a separação limpa):** o
portal NÃO é 100% control-plane — `services/job_failures_collector.py`
corre DENTRO do processo FastAPI (task periódica) e escreve directo em
`KPI_MSSQL_JOB_FAILURES_STG`. Logo `watcherdb_app` precisa também de
INSERT nessa STG, senão migrar o portal parte a coleta live de falhas de
job **em silêncio**. As 4 tabelas `collector_*` são partilhadas entre
`watcherdb_app` (escreve o pedido) e `watcherdb_collector` (lê/actualiza
estado) — ambos os roles precisam de grant.

**Nota do 3º parecer:** `tribunal_*` e `WDB_COLLECTION_SCHEDULE_META` NÃO
existem no V3.3 (grep=0) — não conceder grants especulativos; o
SCHEDULE_META só é escrito pelo reconciliador V1.

### 3.2 Colector V1 — mapeado pelo gate V1 (parecer 2026-08-04)

**3 gerações de código VIVAS em produção, todas a escrever com
`sql_monitoring`** (não é um único code path — testar as três):
- **A) Legada monolítica** (`scripts/collect_data.py` + `_async.py` via
  `storage.py::DataStorage`): INSERT em `[timeseries].[metrics]`, vários
  `EXEC usp_*`, TRUNCATE das STG, e **CREATE TABLE/INDEX runtime** em
  `storage.py:1268-1287` (self-heal do offline-events em timeout do
  master) — **o único DDL genuíno no caminho normal de escrita**.
- **B) Modular por-KPI** (`scripts/collectors/*` via
  `BaseCollector.store`): `sp_getapplock` + `fn_get_kpi_collection_
  target_env` (EXECUTE) + TRUNCATE/INSERT no slot + `EXEC
  usp_swap_kpi_stg_tables`; especiais `usp_OS_*_Upsert` (MERGE),
  `usp_DetectStorageAnomalies`, `usp_Purge_Deadlocks`,
  `usp_compute_kpi_baseline`.
- **C) Windows Service** (`services/collector_service/collectors/*`):
  INSERT/MERGE próprios + reconciliador (`reconcile_inst_envs.py`, escreve
  em `[metadata].server_config` E `dbo.KPI_MSSQL_INST_ENVS` + `EXEC
  usp_reconcile_inst_envs`) + heartbeat em `WDB_COLLECTION_SCHEDULE_META`.

**Boas notícias do gate (reduzem o risco):**
- `usp_swap_kpi_stg_tables` = **DML puro** (UPDATE da bandeira em
  `KPI_STG_ACTIVE_TABLE` + UPDLOCK/applock). NÃO faz sp_rename/DROP/CREATE.
  Grant mínimo: EXECUTE na proc + SELECT/UPDATE na tabela de controlo.
  **Zero necessidade de ALTER/db_ddladmin.**
- `usp_setup_environment_tables` é DDL real MAS **sem chamadores em runtime
  Python** (só instalação/migração) → fora do grant do writer.
- `usp_purge_kpi_history` já corre por **identidade separada** (SQL Agent,
  não a ligação Python) — precedente do princípio que esta wave generaliza.

**Grants do writer (3 schemas!):** `dbo` (STG/HIST/controlo) + `metadata`
(server_config) + `timeseries` (se path A continuar vivo) — SELECT/INSERT/
UPDATE/DELETE + EXECUTE nas ~10 procs + na função. Candidato:
**`watcherdb_collector`**.

**Credencial:** singleton `master_server` em `config/servers.json`
(password Fernet, chave em `.encryption_key`), consumido por **27
ficheiros** via `get_master_server()` — trocar username/password no JSON
propaga a todos sem tocar código. **ARMADILHA:** existe cópia separada em
`services/collector_service/config/servers.json` — confirmar se é o mesmo
ficheiro ou cópia divergente antes do rollout (senão o Windows Service
fica com credencial velha).

### 3.3 Condições do gate V1 (mandatórias)
1. Confirmar se os dois `servers.json` (raiz + serviço) são o mesmo
   artefacto ou cópias a sincronizar.
2. Resolver o DDL runtime `storage.py:1268` ANTES de apertar grants —
   **recomendação do gate: consolidar `KPI_MSSQL_SERVER_OFFLINE_EVENTS`
   no canonical e remover o self-heal** (mesma dívida do WDB_KPI_MUTE),
   em vez de dar CREATE TABLE ao writer.
3. `usp_setup_environment_tables` fica FORA do grant do writer.
4. Testar os **3** geradores (A legado + B modular + C serviço) antes de
   revogar db_owner.
5. Path A (`collect_data.py` sync) ainda vivo e com assimetria histórica
   face ao async (2026-07-21) — "colector" não é singular.

Veredicto do gate: **GO-com-condições, sem VETO** (a swap ser DML puro
tira o risco de DDL que se temia).

## 4. Modelo de logins-alvo (3 logins — painel convergente)

| Login | Papel | Grants mínimos |
|---|---|---|
| `sql_monitoring` | LEITURA (dashboards V3.3 + DMVs remotas nos 62 servers) | `db_datareader` apenas. **Remover** `db_owner` + `db_datawriter`. |
| `watcherdb_collector` | ESCRITA da coleta V1 (3 gerações A/B/C + baseline) | `SELECT`+`INSERT`+`ALTER` nas ~150+ STG (via SCRIPT DINÂMICO, não lista estática) nos schemas `dbo`+`metadata`+`timeseries` + `EXECUTE` nas ~10 procs/função. **NÃO** `usp_setup_environment_tables`. |
| `watcherdb_app` | ESCRITA do portal V3.3 (control-plane) | `SELECT/INSERT/UPDATE/DELETE` num conjunto FECHADO de ~10 tabelas `WDB_*`/app. |

**Porque o `ALTER` do collector é EVITÁVEL (refinamento do 3º parecer):**
o único "DDL-like" no caminho é o `TRUNCATE TABLE`. Mas (a) o
`base_collector.py:store` já tem **fallback `DELETE`** funcional quando o
TRUNCATE falha por falta de ALTER (confirmado no código), e (b) existe
prior art órfã `usp_truncate_stg_tables` (`WITH EXECUTE AS OWNER`,
`CRIAR_PROCEDURE_TRUNCATE_STG_SIMPLIFICADO.sql`) que dá TRUNCATE-speed
scoped ao allowlist SEM ALTER directo. **Preferência: reactivar essa
sproc (EXECUTE) ou aceitar o DELETE — evitar conceder ALTER de todo.** A
swap sproc é DML puro. O `CREATE TABLE` runtime (`storage.py:1268`)
resolve-se consolidando a tabela no canonical (condição, não grant).
→ `watcherdb_app` precisa também de INSERT em `KPI_MSSQL_JOB_FAILURES_STG`
(gotcha §3.1).

**Porque script DINÂMICO e não lista:** o security-auditor confirmou ~150+
tabelas físicas STG (13 famílias não-particionadas + 24 ×3 ambientes); os
grants estáticos do canonical cobriam ~9 — os GRANTs já eram "teatro" por
construção, o db_owner é que disfarçou. Grant tem de varrer `sys.tables` e
auto-embutir-se no DDL de cada família nova, ou volta a divergir.

Cada login nova ⇒ secret próprio (mesma master key DPAPI, zero cripto
nova): V3.3 `WATCHERDB_APP_SQL_PASSWORD` no `.env` (services/secrets.py já
suporta N entradas); V1 decisão em `credential_manager_v2.py` (role-
namespaced vs stopgap — deploy-architect).

## 5. Sequência de migração — 6 fases, 100% aditiva até à Fase 4

Princípio: **conceder antes de revogar**; a única fase que revoga é a 4, e
o seu rollback são 2 linhas. Deploy em TST primeiro (a BD já é particionada
PRD/QA/TST — vantagem real, PRD intocado até validar).

- **Fase 0 (prep, risco zero):** snapshot de `fn_my_permissions` +
  `sys.database_role_members` do `sql_monitoring` actual → **baseline de
  rollback E evidência de auditoria** (guardar em
  `docs/context/auditorias/`). Enumerar o universo real de STG via
  `sys.tables`. **VERIFICAR `TRUSTWORTHY` OFF + ausência de cross-db
  ownership chaining na instância** (3º parecer: se TRUSTWORTHY=ON,
  db_owner nesta BD pode significar mais do que esta BD — muda o risco).
  Confirmar que auth mode live em cada `.env` PRD/QA/TST é SQL Auth.
  **Confirmar se V5/V6 ligam com a MESMA `sql_monitoring`** (bloqueia o
  revoke da Fase 4 se sim). Criar os 2 logins novos (sem uso). 2 secrets.
- **Fase 1:** grant script DINÂMICO a `watcherdb_collector` +
  `watcherdb_app`. `sql_monitoring` intocado.
- **Fase 2 (código):** V1 = troca de credencial no(s) `servers.json`
  (storage já parametriza). V3.3 = **2ª classe de connection pool** em
  `api/connection_pool.py` (o pool actual é singleton com 1 credencial —
  não dá para 2 identidades no mesmo pool sem risco de leak sob
  concorrência). Deploy TST.
- **Fase 3 (cutover, reversível):** repontar collector→collector-writer,
  portal→app. `sql_monitoring` MANTÉM db_owner como rede. Validar 24-48h:
  1 ciclo de coleta por ambiente + cada router de escrita do portal +
  **forçar 1 ciclo do baseline engine (03h00)** — este motor já morreu
  9 dias em silêncio uma vez (2026-06-12); não repetir a cegueira.
- **Fase 3.5 (caça aos consumidores esquecidos):** antes do revoke,
  monitorizar `sys.dm_exec_sessions.login_name` durante a soak para apanhar
  scripts ainda a usar `sql_monitoring` — o 3º parecer nomeou utilitários
  standalone na raiz de V1 (`execute_manual_swap.py`, `swap_and_archive.py`,
  `fix_hist_and_archive.py`, `create_historical_table.py`). Migrar/aposentar.
- **Fase 4 (a ÚNICA que revoga — a testável):** `ALTER ROLE db_owner DROP
  MEMBER sql_monitoring` + idem db_datawriter. **Rollback = 2 linhas**
  (`ADD MEMBER`), guardado ao lado. Re-verificar `fn_my_permissions` +
  smoke de leitura no portal imediatamente. NÃO executar sem a Fase 0
  confirmar que V5/V6 não dependem desta login.
- **Fase 5 (close-out):** 3-login model no canonical (senão cada cliente
  novo nasce com db_owner outra vez) + `LEAST_PRIVILEGE_SETUP.sql`
  apertado + **CLAUDE.md Regra de Ouro #2 actualizada** (os 2 logins
  passam de violação a modelo correcto) + change record de auditoria.

## 6. Rollback por fase (exigência do owner — TESTÁVEL)

| Fase | Se falhar aqui, reverter assim |
|---|---|
| 0 | Apagar os 2 logins novos (`DROP LOGIN`/`DROP USER`) — sem uso, sem resíduo. |
| 1 | `REVOKE` dos grants novos — `sql_monitoring` nunca foi tocado. |
| 2 | Reverter código (`git`, tag `checkpoint-pre-thresholds-20260804`) + repor credencial `sql_monitoring` no `servers.json`. |
| 3 | Repontar connection strings de volta a `sql_monitoring` (que AINDA tem db_owner) — coleta e portal voltam ao estado actual sem downtime. |
| 4 | **2 linhas**: `ALTER ROLE db_owner ADD MEMBER sql_monitoring;` + `ALTER ROLE db_datawriter ADD MEMBER sql_monitoring;` — restaura exactamente o snapshot da Fase 0. |
| 5 | Documental/canonical — reverter commit. |

O snapshot da Fase 0 é o ground-truth do "estado a que voltamos". Nenhuma
fase antes da 4 altera o `sql_monitoring`.

## 7. GATE DO OWNER — decisões antes de qualquer execução

1. **Abrir a wave agora?** É P1 security e a minha recomendação é ser a
   PRÓXIMA prioridade técnica (antes do 1º cliente — é finding de primeira
   página em auditoria banking). Alternativa: agendar para janela própria.
2. **3 logins (recomendado) vs 2** (colapsar app+collector — pior least-
   privilege, não recomendado).
3. **Credencial V1**: role-namespaced no `CredentialManagerV2` (correcto,
   mais esforço) vs stopgap. → sub-decisão que posso delegar ao
   `watcherdb-deploy-architect` quando abrires.
4. **Pré-requisito a resolver primeiro** (condição do gate V1): confirmar
   se os dois `servers.json` (raiz + serviço) são o mesmo ficheiro ou
   cópias divergentes — afeta se a credencial se troca num sítio ou dois.

**CONFIRMADO (2026-08-04, grep V6):** o **V6 liga à mesma
`WatcherDB_Intelligence` com a mesma `INTELLIGENCE_SQL_USER`**
(`WATCHERDB_V6/migrate.py:40-47`, `setup_watcherdb.py`,
`watcherdb_main.py:2456`). Logo a Fase 4 (revoke) **não pode** executar
antes de o V6 migrar para uma login apropriada (leitura via
`sql_monitoring` reduzido, ou uma `watcherdb_app` própria se escrever).
Isto torna a wave **cross-produto** — coordenar com a sessão V6 é
mandatório antes do revoke. V5/V5.5: confirmar no mesmo padrão.

**Nada será executado sem a tua confirmação.** Quando deres GO, a Fase 0
(snapshot + criar logins sem uso) é risco zero e posso preparar-te os
blocos DDL para SSMS.

## 7-bis. Achados do 4º parecer (inventário exaustivo — reforçam o plano)

- **41 famílias STG confirmadas** no padrão BLUE/GREEN via
  `base_collector.store()` (lista completa no task) + ~15 escritas fora do
  padrão (`WDB_INSTANCE_TCP_PORT`, `WDB_HOST_IP_CACHE`,
  `WDB_PING_RESOLVER_BREAKER`, `WDB_SCHEDULED_WORK_AUDIT`, `Monitor_2PC_*`,
  `usp_reconcile_inst_envs`, upserts OS, purge deadlocks). Confirma o
  "grant por script dinâmico, não lista" — 41 famílias × BLUE/GREEN ×
  ambientes = as ~150+ tabelas.
- **DOIS `CREATE TABLE` em runtime** (não um): `storage.py:1268`
  (offline-events, caminho legado) **e** `auth_service.py:282`
  (`WatcherDB_System_Config`, dentro de try/except que só faz
  `logger.debug`). Ambos passam hoje por db_owner; após o downgrade falham
  **em silêncio** numa instalação nova/DR. **Condição pré-revoke:
  consolidar as DUAS no canonical + subir o log de `auth_service.py:282`
  para warning.**
- **V6 ESCREVE, não só lê** — partilhadas (`WatcherDB_Users`,
  `WatcherDB_System_Config`, `WDB_KPI_MUTE`) E próprias
  (`WatcherDB_Narrative_Cache`, `Metrics_Snapshots`,
  `meta_cognition_outcomes`, e collector out-of-band
  `tempdb_collector_agent` → `KPI_MSSQL_TEMPDB_CONTENTION_STG` via MERGE).
  Logo o V6 precisa da **sua própria** `watcherdb_app`-equivalente com
  grants próprios ANTES da Fase 4 — não basta leitura. Coordenação V6 é
  bloqueante, confirmada.
- **`collector_run_requests`/`collector_manual_runs`**: escrita cruzada de
  DUAS identidades — V3.3 INSERT (portal), V1 Service UPDATE. Ambos os
  roles novos precisam de grant nestas duas.
- **Terceira identidade já existe**: jobs SQL Agent correm sob `sa` (job
  owner), não `sql_monitoring` — manutenção/purge/archive não dependem do
  db_owner que vamos revogar. Não bloqueia.
- Pendente de confirmação DBA: se `collect_data_async.py` (motor
  `storage.py` legado) ainda corre em produção — se sim, duplica a
  superfície de grant.

## 8. O que esta wave NÃO resolve (para não confundir)
- A exposição "uma master key DPAPI protege todos os secrets" (risco
  diferente — VC-4; leak de `key.key` expõe muitos credenciais). Esta wave
  reduz o blast-radius de UMA login, não o da chave.
- O achado paralelo de `performance.py` a usar `use_windows_auth=True`
  contra a Regra #2 (bulletin 2026-07-21) — não replicar; corrigir no seu
  próprio lote.

## Anexo — pareceres do painel (condensados; transcrição completa nos
## tasks da sessão 2026-08-04)

**gate `watcherdb-v1-intel-specialist` — GO-com-condições, sem VETO:**
SQL Auth confirmado; swap sproc DML puro; setup_environment_tables sem
callers runtime; 3 gerações de colector vivas (A legado / B modular / C
serviço); credencial singleton em 27 ficheiros; armadilha dos 2
`servers.json`; recomenda consolidar o CREATE TABLE runtime no canonical.

**`watcherdb-security-auditor` — STRIDE + plano 6 fases:** Tampering
CRITICAL (db_owner reescreve procs/apaga auditoria); ~150+ STG reais vs ~9
com grant (grants eram teatro); 2ª classe de pool obrigatória em V3.3;
validar baseline 03h00; compliance ISO A.9.2.3 / SOC2 CC6.1 / PCI Req 7-8;
evidência de auditoria = snapshot Fase 0 + verificação Fase 4.

**design-agent (3º parecer, ~2h) — refinamentos que corrigem o modelo:**
(1) portal NÃO é só control-plane — `job_failures_collector.py` escreve
`KPI_MSSQL_JOB_FAILURES_STG` de dentro do processo FastAPI → app precisa
desse grant STG; (2) evitar ALTER no collector via `usp_truncate_stg_tables`
(EXECUTE AS OWNER, órfã) ou fallback DELETE já testado; (3) inventário do
portal ampliado (User_Preferences, Auth_Log, System_Config); (4) Passo 0
tem de verificar TRUSTWORTHY/cross-db chaining e se V5/V6 partilham a login;
(5) não conceder grants a `tribunal_*`/`SCHEDULE_META` (não existem em
V3.3); (6) caçar scripts standalone órfãos de V1 antes do revoke;
(7) o `Trusted_Connection=yes` do `performance.py`/servidores monitorizados
é finding SEPARADO — não misturar. 2 pendências: v1-intel confirmar os 4
scripts órfãos; v5-specialist confirmar se V5/V6 usam a mesma login.
