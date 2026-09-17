# PROPAGAÇÃO V6 — lotes de 16 e 17 de Setembro (V3.4 `61f712d` → `b8f6723`; V1 `a29791b`, `8a427ed`)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** A origem de cada lote é o script `docs/context/*_apply.py`
> do V3.4 indicado em cada secção — traz o código integral, os testes e o motivo. Antes de escrever este prompt
> mediu-se o V6 (`WATCHERDB_V6`, ramo `wave-propagacao-v33-20260819`, último commit 9c2ca13 de 03/09) com grep; o
> resultado está em cada secção como "No V6". O V6 tem 131 ficheiros por commitar (incl. `api/routers/htmx.py`,
> `services/ai_assistant_service.py`, `requirements.txt`): commitar ou guardar esse trabalho antes de portar.
>
> Ordem recomendada: 1 → 2 → 3 (segurança), depois 4 → 7 (defeitos visíveis), depois 8 → 9 (idioma). Os lotes 10 e 11
> são do V1 e não têm código a portar — só o efeito na base partilhada.

## 1. Sementes `admin123`/`viewer123` e o primeiro administrador — CRITICAL

Origem: `BOOTSTRAP_ADMIN_2026-09-16_apply.py` (V3.4 046b52d) e, no V1, `SEMENTES_V1_2026-09-16_apply.py` (a29791b).
Achado do agente de segurança: os instaladores semeavam três administradores com `admin123` e os guias publicavam a
password. Ordem imposta: **bootstrap primeiro, sementes depois, nunca ao contrário.**

No V6: `database/AUTH_USERS_TABLE.sql` (4 ocorrências) e `database/CREATE_USER_AUTHENTICATION_SYSTEM.sql` (6) ainda
semeiam; `docs/V16_1_COLAB_EXECUTION_RUNBOOK.md` e `V16_3_TRAINING_RUNBOOK.md` citam a password; não existe
`tools/bootstrap_admin.py`. Portar: o utilitário interactivo (getpass, recusa se já houver admin — exit 3 —, recusa
nomes previsíveis, política `validate_strong_password`, bcrypt 12, `must_change_password=1`, auditoria
`BOOTSTRAP_ADMIN`), o Passo 3 do `deploy/setup_database.ps1` com `-SkipBootstrap`, e o teste de guarda
`tests/unit/test_sem_credenciais_semente_20260916.py` (nenhum hash bcrypt completo, nenhuma semente fora de comentário
em `database/`, `deploy/`, `docs/guides/`, `tools/`). Verificar se o V6 partilha a tabela de utilizadores com o V3.4
(mesma `WatcherDB_Intelligence`): se sim, a base já não tem contas com esse hash e o risco é só em instalações novas.

## 2. `must_change_password` imposta pelo servidor

Origem: `MUST_CHANGE_PASSWORD_2026-09-16_apply.py` (9694380: coluna criada pelo `database/14_ADD_MUST_CHANGE_PASSWORD.sql`
— o script 07 abortava com erro 207 porque o UPDATE à coluna nova estava no mesmo lote do ALTER) e
`TROCA_OBRIGATORIA_2026-09-16_apply.py` (a19585b: claim `mcp` no token só quando `auth_method == "local"`, middleware
devolve 403 `{"code":"MUST_CHANGE_PASSWORD"}` fora de `/api/auth/change-password|me|logout|validate`, ecrã de troca
sem botão de fechar, `location.reload()` depois da troca).

No V6: a única referência a `must_change_password` é `LOGINPROPERTY(name,'IsMustChange')` em `api/routers/users.py:494`
(logins SQL, outro assunto); não há `_AUTH_MCP_ALLOWED` nem `_mcpForcarTroca`. Se a tabela é partilhada, a coluna já
existe (script 14 corrido pelo owner a 16/09); falta a imposição. Testes: `test_troca_obrigatoria_20260916.py`.

## 3. Reset por administrador não converte conta de domínio em local

Origem: `RESET_CONTA_AD_2026-09-16_apply.py` (c9049c4). `auth_service.e_conta_de_dominio(user_row)`; para contas AD o
`change_password` escreve `local_password_hash`/`local_password_set_at` e devolve `conta_de_dominio: True`; o
self-service verifica contra o hash local ou responde 400 "Conta de domínio: a password muda-se no AD"; o reset não
marca `must_change_password`. No V6: `e_conta_de_dominio` não existe em `services/auth_service.py`. Verificar primeiro
como o V6 marca contas AD (no V3.4 é o marcador `ad_auth:` no `password_hash`).

## 4. Regra de Ouro #2 — fim dos `Trusted_Connection=yes` fora do pool (lotes A e B)

Origem: `REGRA_OURO_2_LOTE_A_2026-09-16_apply.py` (e8e6495) e `REGRA_OURO_2_LOTE_B_2026-09-16_apply.py` (85de22b).
Lote A: os literais directos (jobs em `intelligence_kpis` via string do pool com `Connection Timeout=4`, `helpers`,
`network_diagnostics`, `memory_analysis`, `service_monitor`, `os_performance`, `space.py` via `execute_on_intelligence`).
Lote B: `ConnectionInfo.get_connection_string()` pergunta ao pool (`_sql_auth_enabled_for` + `_resolve_credentials`)
quando `use_windows_auth=True` — cobre os 5 sítios legados (LIVE/Overview/helpers/service_monitor) de uma vez;
fail-open para Windows fora da allowlist. Default trace desligado por `DEFAULT_TRACE_ENABLED = False`
(`fn_trace_gettable` exige ALTER TRACE que o `sql_monitoring` não tem, e rotulava EventClass 46/47 como Server
Start/Stop). Teste de guarda: `test_regra_ouro_2_trusted_20260916.py` (allowlist de 4 ficheiros).

No V6: **27 literais em 16 ficheiros** (`api/connection_pool.py` 4, `setup_watcherdb.py` 3, `tools/migrations/
apply_sprint32_ddl.py` 4, `monitoring.py` 2, `memory_analysis`, `service_monitor`, `space.py`, `jobs.py`,
`network_diagnostics`, `os_performance_service`, `services/async_db.py`, `watcherdb/models/server.py`, `migrate.py`,
mais testes). **Atenção:** o pool do V6 diz de si próprio "este pool não lê servers.json (não tem
`_resolve_credentials`)" (`api/connection_pool.py:545,564`) — o lote B tal como está **não porta**: no V6 é preciso
primeiro saber de onde vêm as credenciais SQL Auth por servidor. Não inventar: perguntar ao owner. O lote
`CONFIG_ABSOLUTO_2026-09-16_apply.py` (00542d6 — `servers.json`/`sql_auth_rollout.json` por caminho absoluto via
`watcherdb.core.paths.config_dir()`, aviso `[CONFIG]` no arranque) só se aplica se o V6 vier a ler esses ficheiros.

## 5. Disk Latency — um disco = uma linha

Origem: `DISK_LATENCY_POR_DISCO_2026-09-16_apply.py` (40bb4c1) e `DISK_POR_DISCO_TODOS_2026-09-17_apply.py` (b566aef).
O recolhedor de disco (WMI) corre por instância e grava `Instance`: hosts com 2–4 instâncias têm 2–4 linhas iguais
por disco em `KPI_OS_DISK_PERF_STG` (519 linhas para 468 discos). `helpers._uma_linha_por_disco(rows)` (mais recente por
(Hostname, Drive), `Instances`/`Instances_On_Host` anotados) no dashboard e na modal `/instances/{kpi_type}`;
`get_disk_by_drive` idem; `get_disk_latency_summary` agrega sobre `ROW_NUMBER() OVER (PARTITION BY Hostname, Drive
ORDER BY Update_TS DESC)`. Teste que varre os ficheiros e falha se houver leitor da tabela sem a regra.

No V6: **4 leitores** — `api/routers/intelligence_kpis.py:2846` e `:4539`, `services/os_performance_service.py:442`,
e um que o V3.4 não tem: `services/report_service.py:757`. Aplicar a regra aos quatro e estender o teste de varrimento
ao `report_service`.

## 6. Aba Log — o erro do errorlog traz a sua mensagem

Origem: `LOG_ERRORLOG_CONTEXTO_2026-09-16_apply.py` (b9affc1). O SQL Server escreve cada erro em duas linhas
(`Error: N, Severity: S, State: T.` + mensagem) no mesmo spid; o endpoint filtrava por palavras e a continuação caía
no `NOT LIKE '%This is an informational message%'`. Fix: `#errorlog` com `Seq IDENTITY`, CTE com `LAG(Text) OVER
(PARTITION BY ProcessInfo ORDER BY Seq)` a trazer a linha seguinte a um cabeçalho, `ORDER BY Seq`, exclusão das
informativas retirada do SQL; `api/errorlog_pairs.py` (puro, 9 testes) emparelha, extrai `database 'X'`, nível INFO
quando a mensagem é informativa; no ecrã `classifySqlLevel` honra o INFO do servidor antes do número da severidade e
o filtro Nível nasce em ERRO.

No V6: endpoint em `watcherdb_main.py:6730` (`api_sql_errors`) com a mesma exclusão. Verificar se o V6 tem o mesmo
`classifySqlLevel` e `_logColFilter` (o grep não os encontrou no template — a aba Log do V6 pode ser outra); se for
outra, portar só o endpoint e o módulo puro.

## 7. Collector Health — estado por (tabela, ambiente)

Origem: `COLL_HEALTH_AMBIENTE_2026-09-16_apply.py` (dac44db). `KPI_STG_ACTIVE_TABLE` tem uma linha por ambiente para a
mesma tabela; o calculador indexava só por `Table_Name` e ficava com a última a chegar — as tarefas PRD de Always On,
AG queues e Mirroring apareciam STALE há 158 dias (a data do TST). `_indexar_por_ambiente` / `_linha_do_ambiente`;
`_best_active_row` escolhe o ambiente da tarefa; `WDB_COLLECTION_SCHEDULE_META` indexada por `Collector_Name`.

No V6: `modules/collector_health/health_calculator.py:135` e `:163` têm exactamente o `dict` por `Table_Name`. Porta
directa; testes `test_coll_health_ambiente_20260916.py` (6).

## 8. Collector Health em quatro idiomas (5 lotes + revisão AO90)

Origem: `COLL_I18N_MODAL`, `COLL_I18N_BARRA`, `COLL_I18N_MUTE`, `COLL_I18N_DETALHE`, `COLL_I18N_ACCOES` e
`COLL_I18N_REVISAO` (fbf72e7, 9ebf403, e6936bd, 3cfde2b, d940e3c). Grupo `coll` com 194 chaves por idioma, `_collT`
(recurso em português) e `_collTp` (placeholders `{n}`), plural real (`active_one/active_many`), e dois defeitos que só
a tradução destapa: separador escolhido pelo texto visível (agora `data-tab`) e rótulo de coluna usado como chave dos
dados (agora `col.lbl` separado de `col.k`).

No V6: o ecrã existe no template (27 ocorrências de `collSwitchTab`/`coll-tab`), **sem** `_collT` e **sem** grupo
`coll` nos locales — e os locales do V6 chamam-se `pt-PT.json`/`en-US.json` além de `pt.json`/`en.json`: perceber
primeiro qual é o ficheiro vivo antes de inserir 194 chaves no errado. Aplicar também a revisão AO90 (lista explícita
`actualiz→atualiz`, `activ→ativ`, `acção→ação`, …) e os termos da casa `frota/fleet/flota`.

## 9. Cartão de Disk Latency em quatro idiomas

Origem: `DLAT_I18N_2026-09-17_apply.py` (999a222). Grupo `dlat` (21 chaves; 6 no overlay pt-BR); as dicas em strings de
aspas simples passam a concatenação com `t()` — e a dica "Disco muito ocupado (${pct}%)" **nunca interpolava** (o
`${}` estava dentro de aspas simples). No V6: `templates/watcherdb_portal.html:35991` tem o mesmo "Possiveis causas e
diagnostico" escrito à mão — o mesmo defeito do `${}` está lá.

## 10. V1 — sem código a portar, efeito na base partilhada

- `AUDIT_V5_PACKAGE_2026-09-16_apply.py` (8a427ed): o audit de tarefas deixa de gravar achados HIGH `V5_NAO_CARREGADO`
  falsos (importava o package `collectors` da raiz). O Collector Health do V6 deixa de os mostrar sem fazer nada.
- `SEMENTES_V1` (ver 1). Os instaladores do V1 já não semeiam contas.

## 11. Decisões e pendentes que o V6 deve conhecer

- `sql_monitoring` é db_owner de propósito até ao fecho do projecto (inventariar grants reais; Extended Events).
- QUIET "sem alvo" no Collector Health **não foi feito**: a evidência (0 servidores/0 linhas para QA/TST) só existe nos
  logs por família do V1. Proposta: `Last_Success_TS` em `WDB_COLLECTION_SCHEDULE_META` também com 0 linhas.
- O recolhedor de disco corre 4× por host onde há 4 instâncias (optimização V1, veto do guardião).

## Testes a portar (V3.4 `tests/unit/`)

`test_sem_credenciais_semente_20260916.py`, `test_bootstrap_admin_20260916.py`, `test_troca_obrigatoria_20260916.py`,
`test_reset_conta_ad_20260916.py`, `test_regra_ouro_2_trusted_20260916.py`, `test_regra_ouro_2_lote_b_20260916.py`,
`test_disk_latency_por_disco_20260916.py`, `test_disk_por_disco_todos_20260917.py`, `test_errorlog_pairs_20260916.py`,
`test_coll_health_ambiente_20260916.py`, `test_coll_i18n_*_20260916.py`, `test_dlat_i18n_20260917.py`,
`test_config_absoluto_20260916.py` (só se o lote 4/CONFIG se aplicar).
