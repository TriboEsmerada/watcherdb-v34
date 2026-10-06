# PLANO - Atribuicao de query a aplicacao (V3.4 Standard + V6 Pro)

Data: 2026-09-24. Estado: AGUARDA GO do owner (lote a lote).
Origem: docs/context/SQLCOMMENTER_PARECER_2026-09-24.md (6 especialistas, 6/6 contra sqlcommenter literal).
Revisao do rascunho: sql-deep-reviewer (16 objeccoes), watcherdb-v33-specialist (8), watcherdb-v5-specialist (11),
watcherdb-qa-specialist (8). Todas integradas abaixo; as que contradiziam o codigo foram verificadas pelo orquestrador.
SQL: docs/context/sql/atribuicao_app_2026-09-24.sql (PoC Q1-Q4, L1b drill+sinal, TOP_SLOW reescrita, L2c).

Produtos: V3.4 = Standard (8434). V6 = Pro (C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6,
branch wave-propagacao-v33-20260819, 131 ficheiros por commitar, sem remoto, sem gate de tier em runtime).

## Ordem

  P0 (V3.4 e V6, seguranca) -> L0 PoC -> L1-SQL -> L1-UI -> L1b -> FEATURE_MATRIX (DBA Lead) ->
  propagar L1/L1b ao V6 -> P0b V6 (query_store_monitor) -> L2a -> L2b -> L2c -> piloto 30 d -> barra -> L3 decisao

Cada lote = 1 apply script docs/context/<LOTE>_2026-MM-DD_apply.py com --check/--preview/--repo, testes na copia,
prova real no servico reiniciado pelo owner, commit unico (rollback = git revert desse commit).

## P0 - Seguranca (ANTES de tudo; cross-tier; achado desta revisao)

Facto verificado (V3.4 e V6): api/routers/performance.py (prefixo /api/v1/performance, 10 endpoints) nao tem
NENHUM Depends de role; a redaccao por role (_redact_node/_RoleRedactingRoute) existe so' em
api/routers/live_monitoring.py:100-167 e cobre so' /api/v1/live. Qualquer utilizador autenticado, incluindo viewer,
le sql_text cru dos investigators (Heavy/CPU/Slow/Blocking/Deadlocks). No V6 o LIVE ja' exige _require_dba
(live_monitoring.py:79-83, viewer recebe 403); o Performance e' o buraco nos dois produtos.
- P0-V3.4: aplicar Depends(_require_dba) (auth_compat.py:266) ao router performance OU route_class de redaccao
  igual ao LIVE. Recomendado: redaccao por role (viewer ve hash estavel, como no LIVE) para nao tirar o modulo ao viewer.
  Teste: tests/unit/test_performance_role_gate_20260924.py (viewer -> sql_text redigido; dba -> integral).
- P0-V6: mesmo gate/redaccao em api/routers/performance.py; portar _redact_node para live_monitoring.py do V6
  (paridade), sem tocar sql_queries.py/ops_dashboard.py (routers separados; opt-in explicito).
- Nao entra neste plano mas fica registado: parecer do security-auditor para a lista completa de routers sem role.

## L0 - PoC de 1 dia (owner corre; sql_monitoring; so' SELECT + #temp)

Onde correr: SSMS com login SQL sql_monitoring (nunca conta AD) OU sampler Python via execute_on_server (pool).
NAO usar docs/context/sql/_run.py: liga so' a Intelligence e a guarda recusa WAITFOR/DECLARE/EXEC (correcto; nao relaxar).
- Q1 amostra: SELECT curto sobre dm_exec_sessions x dm_exec_requests, session_id <> @@SPID, a cada 10 s por 60 min.
  Modo B recomendado (sampler do lado do cliente, CSV incremental): a VPN caiu a 21/09 e um WAITFOR de 1 h
  perde tudo e aparece como pedido longo no LIVE e no V1. Metrica: delta de dm_exec_sessions.cpu_time por
  (session_id, login_time) com LAG; classes unknown/agent/generic/named por padroes LIKE (nao igualdades).
  Gate: generic >= 60 % do CPU -> L1 completo com guia; < 30 % -> L1 so' agregacao.
- Q2 cardinalidade login x programa x host: sobre os samples de Q1 (nao foto "agora"). Resultado tem logins/hosts
  -> fica no scratchpad, nunca no repo.
- Q3 Query Store: sp_executesql atras de ProductMajorVersion >= 13 (is_query_store_on rebenta o batch em 2014);
  estado real por base (READ_ONLY, tamanho) com cursor + TRY/CATCH + HAS_DBACCESS (VIEW DATABASE STATE pode faltar).
- Q4 sintetico SO' QLT, base master (sem QS): 1000x texto identico (A) / 1000x comentario unico ad hoc (B) /
  1000x comentario unico dentro de sp_executesql (C), marcador watcherdb_poc. Ler optimize for ad hoc ANTES
  (muda a leitura: stubs). sql_monitoring NAO limpa cache (ALTER SERVER STATE) -> os ~2000 planos ficam ate'
  eviction natural (20-40 MB); nao pedir FREESYSTEMCACHE. Aparecem no LIVE > Plan Cache da QLT: e' a demo do L1b.
- Registo: docs/context/sql/poc_atribuicao_app_RESULTADOS_2026-MM-DD.md so' com agregados (sem logins/hosts).
Instancias: SQLHDSPRD405\I01 (Q1-Q3) + 1 QLT (Q1-Q4).

## L1-SQL - Std (V3.4): atribuicao por program_name/host/login no backend (sem V1, sem DDL)

Factos corrigidos pela revisao: heavy_queries.py e slow_queries.py NAO tem nenhum dos 3 campos (0 ocorrencias);
cpu_queries.py:104-109 tem via LEFT JOIN a dm_exec_requests, que so' cobre o que esta' A CORRER no instante.
queries.py:747-787 (TOP_SLOW_QUERIES_DETAILED) e' do SQL Diagnostics legado (/api/queries/*), nao do Performance
Module: sao dois subsistemas; este lote toca os dois de proposito.
- 1a modules/performance/app_attribution.py (novo, puro Python): classify(program_name) -> named|generic|unknown|agent
  por tabela de padroes (SqlClient Data Provider, Core Microsoft SqlClient Data Provider, Microsoft JDBC Driver,
  ODBC Driver N for SQL Server, SSMS x3 variantes, *.exe, python/pyodbc/sqlcmd/osql, Microsoft SQL Server,
  DatabaseMail, Report Server, 'Microsoft Windows Operating System'); 'SQLAgent - %' -> agent; NULL/''/espacos -> unknown.
- 1b TOP_SLOW_QUERIES_DETAILED reescrita (SQL no ficheiro): CTE TOP 20 primeiro e APPLY depois (hoje materializa
  texto + XML de plano de todas as candidatas > 5 s); a 2.a fonte COALESCE usa pa.attribute = 'session_id', atributo
  que NAO EXISTE em dm_exec_plan_attributes -> caia sempre em 'N/A' pagando um scan por linha: removida;
  OUTER APPLY devolve login/host/program da sessao com pedido activo no plan_handle; colunas novas aditivas:
  host_name, program_name, attribution_source ('active_request'|'none'), object_name (proc = atribuicao real e
  gratis, cobre o caso "procs dominam"); OUTER APPLY dm_exec_query_plan (plano expulso nao apaga a linha);
  NULLIF(execution_count,0); database_name com fallback dbid do plano (fix F9 do PLANCACHE_SQL).
- 1c Investigators: cpu_queries.py mantem o LEFT JOIN (rotulo "sessao activa no momento"); heavy_queries.py
  (steps :90-151, :161-188, :198-215) e slow_queries.py (:77-97, :107-126) ganham object_name (gratis) e o
  step_3_active_now de slow_queries (:136-150) ganha LEFT JOIN dm_exec_sessions (login/host/program). NAO juntar
  sessions aos steps de plan cache agregado (seria NULL na maioria das linhas). Padrao TOP -> APPLY preservado.
- 1d Testes: tests/unit/test_app_attribution_20260924.py (classify: named/generic/unknown/agent, NULL, '', espacos,
  SSIS/CmdExec/PowerShell JobStep); tests/unit/test_top_slow_queries_program_host_20260924.py (SQL contem
  program_name/host_name/object_name; nao contem 'session_id' em plan_attributes; mock rows login NULL);
  medicao manual N=20 antes/depois de /api/queries/slow (nao ha' baseline de duration_ms persistida: cpu_queries.py:115
  grava por pedido, efemero) -> mediana e max no scratchpad, gate +10 %.
- Prova real: endpoint 200 com as colunas novas em SQLHDSPRD405\I01; investigators CPU/Heavy/Slow 200; 0 regressao
  em pytest tests/unit.

## L1-UI - Std (V3.4): agregacao por aplicacao no LIVE e colunas no Performance Module

- 1e /api/v1/live/{inst}/connections (CONNECTIONS_SQL :812-834 ja' devolve login/client_host/program para TOP 50 por CPU):
  by_app calculado em Python sobre o array connections (sessions, total_cpu_ms, reads, writes, classe). Rotulo
  obrigatorio "amostra TOP 50 por CPU" (pools idle ficam sub-representados) e teste que prova sum(sessions) <= 50.
  Contador unnamed = generic+unknown / total da amostra.
- 1f Redaccao (decisao de produto, 2 opcoes; recomendada a 1.a): (1) by_app some para viewer, fica so' o contador
  unnamed/total; (2) program_name dentro de by_app recebe hash estavel como sql_text (_APP_FIELDS novo). Hoje
  _IDENTITY_FIELDS (:110-112) colapsaria N linhas no mesmo literal "[oculto]" -> tabela inutil. Teste
  tests/unit/test_live_redact_by_app_20260924.py fixa a opcao escolhida.
- 1g Portal: _liveRenderConnections (templates/watcherdb_portal.html:53363-53380; ja' tem coluna Program :53372)
  ganha mini-tabela "por aplicacao" + contador. Performance Module: perfRenderStepTable/_perfOrderCols
  (:57558-57568) renderiza Object.keys(rows[0]) -> as colunas novas do L1-SQL aparecem sozinhas, com cabecalho
  = nome do campo cru (as 8 tabelas nao passam por i18n; help_text_pt e display_name_pt sao PT fixo, :57092-57272).
  NAO criar perf.* (prefixo inexistente em pt.json) nem mecanismo de traducao de cabecalho neste lote.
- 1h i18n: chaves no padrao existente live.col_app, live.connections_by_app, live.connections_unnamed,
  live.connections_sample_note via _kpiT com fallback PT (padrao CONTEXT.md 18/09); pt/en/es; guarda
  tests/unit/test_i18n_texto_a_mao_20260918.py (745/268, ratchet: nunca sobe; docstring diz 886/294, drift a corrigir
  de passagem) e test_i18n_parity nao regridem.
- 1i Runbook Std modules/performance/runbooks/app_attribution.md: Application Name= (ADO.NET), applicationName=
  (JDBC), APP= (ODBC), FireDAC ApplicationName (Delphi); pacotes fechados = so' connection string; o que "sessao
  activa no momento" significa; procs = object_name.
- Teste de contrato: tests/unit/test_connections_by_app_20260924.py (shape: campos antigos inalterados + by_app;
  delta de payload < 8 KB). Prova real: page.route sobre copia do template (script de sessao no scratchpad, como
  desde 18/09) + servico 8434 reiniciado pelo owner + auditor de contraste do scratchpad 0 nos 3 temas [MANUAL
  se o auditor nao correr] + 0 erros JS. e2e: exportar WATCHERDB_BASE_URL=https://localhost:8434 (tests/e2e/
  conftest.py:41 ainda tem 8433 por omissao -> PR separada); isolar antes os 2 testes sempre-vermelhos de
  test_ux_fixes_e2e.py:26-38 com xfail(strict=True).

## L1b - Std (V3.4): "plan cache poluido" (variantes de texto por query_hash)

- Investigator novo modules/performance/investigators/plan_cache_pollution.py (9.o; 1 ficheiro + 1 linha no tuplo de
  __init__.py:16-34 ANTES de ProblematicSessionsInvestigator, que fica ultimo; engines correlator/baseline/runbook/
  ticket sao genericos; RunbookEngine.attach degrada sem markdown). Limiares como CONSTANTES DE CLASSE (padrao dos
  investigators; api/kpi_thresholds_registry.py e' so' dos 13 KPIs do dashboard e nao tem consumidores em modules/
  performance -> nao migrar aqui). Sem KPI card novo (decisao A3 mantem-se; teste confirma a lista dos 13).
- Sinal barato (cada refresh, ~0 ms): dm_os_memory_clerks CACHESTORE_SQLCP/OBJCP + dm_exec_cached_plans Adhoc
  usecounts=1 + contadores cumulativos SQL Compilations/sec, Re-Compilations, Batch Requests (delta em Python
  entre refreshes). Regra: compilacoes/batches > 10 % OU adhoc single-use > 50 % OU SQLCP a crescer -> abre a drill.
- Drill (so' ao clique, nunca no ciclo do Fleet; timeout 10 s): 1 scan de dm_exec_query_stats com funcoes de
  janela (DENSE_RANK por sql_handle dentro do query_hash), query_hash <> 0x0 excluido, janela creation_time 60 min,
  TOP 20 -> CROSS APPLY texto so' nas 20. execs_per_variant < 2 = nao parametrizado.
- Limiares iniciais: 100 variantes/60 min info, 1.000 warning, 10.000 critical, com execs_per_variant < 2.
  Calibrar com Q4 (QLT) e uma leitura na PRD405 antes de fixar. Medir duracao da drill em PRD grande: > 2 s ->
  cache de N min, nunca live no refresh.
- LIVE > Plan Cache (PLANCACHE_SQL :1040-1058) ganha o sinal + botao para a drill. Runbook plan_cache_pollution.md.
- Testes: tests/unit/test_plan_cache_pollution_20260924.py (mock rows 1/99/100/101 variantes; regra do sinal;
  lista dos 13 KPIs inalterada). Prova: Q4 na QLT faz o alarme disparar (B e C), A nao.

## FEATURE_MATRIX - sign-off do DBA Lead (antes do commit de L1, nao depois)

docs/FEATURE_MATRIX.md e' STUB (linha 3), titulado V3.3 (linha 1) e diz (:21-22) que sem entrada explicita a decisao
escala ao DBA Lead / Customer Success. Aplica-se a L1/L1b tanto como a L2. Proposta de entrada (seccao Performance Module):
  | Atribuicao por program_name/host/login/object_name + guia Application Name | Std + Pro |
  | Alerta de plan cache poluido (variantes por query_hash) | Std + Pro |
  | Atribuicao por rota (sqlcommenter / EF TagWith, tags estaticas, sem traceparent) | Pro (V6-only) |
  | Historico de CPU por rota via STG dedicada | Pro, NEEDS_DECISION |
Marcacao anti-propagacao-inversa (V6 nao tem gate de tier em runtime; deploy/license_cli.py:81 e' so' na licenca;
o "gate C" do ADR_V6_REINTEGRACAO esta' em proposta, nao instalado): cabecalho
"# PRO-ONLY - nao propagar para V3.4 sem decisao DBA Lead" em sql_app_tags.py e nos blocos SQL de L2.

## Propagacao V6 (antes de L2): PROMPT_PROPAGACAO_V6_ATRIBUICAO_APP

Por intencao, nao por diff: investigators do V6 divergem (cpu 260 vs 338 linhas, heavy 337/343, slow 237/250);
TOP_SLOW_QUERIES_DETAILED no V6 esta' em modules/monitoring/queries.py:571-599 com o mesmo defeito (so' login,
2.a fonte inexistente). Template V6 55.859 linhas; perfRenderStepTable :54631-54691 tambem generico; LIVE
Connections em _liveRenderConnections :47078-47104 (as linhas :47099/:47186 sao LIVE, nao Heavy Queries).
i18n V6: 6 ficheiros static/i18n/{en,es,pt,pt-PT,pt-BR,en-US}.json, 54 chaves cada (sem guarda 745/268).
CI do V6: pytest tests/ --cov=api --cov=services --cov=hybrid; modules/ FORA de cobertura, lint e bandit;
zero testes de investigators/live_monitoring/query_store. Pre-requisito de L2: modules nos paths de CI +
testes parse-only dos 3 investigators.

## P0b - V6: services/query_store_monitor.py esta' ligado a base errada

Facto (v5-specialist, confirmado por leitura): os 4 metodos (:92-324) correm sys.query_store_* via
execute_on_intelligence() (api/connection_pool.py:945) = WatcherDB_Intelligence, nao a instancia alvo; instance/
database sao ignorados; _get_from_staging (:326-328) e' stub return []. /api/v1/query-store/* nunca devolve
dados reais hoje. Correccao antes de L2c: async_execute_on_server(instance, ...) por instancia (padrao dos
investigators), com gate ProductMajorVersion >= 13 e HAS_DBACCESS. Bug independente deste plano; entra por ser
pre-requisito do historico por rota sem tabela nova.

## L2a - Pro (V6): parser (puro Python, shippable isolado)

modules/performance/sql_app_tags.py: cauda sqlcommenter /*k='v',k2='v2'*/ (urldecode; aspas '' escapadas) + cabeca
EF Core TagWith '-- tag'. sp_executesql: o texto de dm_exec_sql_text comeca por '(@p0 int,@p1 nvarchar(4000))' ->
strip do prefixo ^\((?:[^()]|\([^()]*\))*\)\s* (parenteses aninhados de decimal(18,2)) antes de procurar '-- ';
cauda vem limpa. A tag e' do BATCH, nao do statement: head/tail do texto do batch; atribui-se a todos os statements;
head e tail diferentes -> ganha a cauda, app_source='mixed'. Allowlist route/controller/action/application/framework/
db_driver; traceparent/tracestate SEMPRE descartados; cap 200 chars/valor; ordem deterministica; tag_truncated
quando a cauda tem '*/' sem '/*'. Valores sao texto de terceiros: escape no portal (XSS) e redaccao viewer (P0).
Fixtures obrigatorias (tests/unit/test_sql_app_tags_parser_20260924.py): (1) cauda simples; (2) multiplas chaves;
(3) traceparent presente -> descartado; (4) aspas '' no valor; (5) quebra de linha no comentario; (6) unicode;
(7) TagWith na cabeca, com e sem prefixo (@p...); (8) sem tag -> app_source='none'; (9) mixed; (10) truncado.

## L2b - Pro (V6): investigators + RUNNING_QUERIES_SQL

10 blocos SQL (cpu :81,:106,:131,:157; heavy :134,:169,:196; slow :83,:111,:135) + RUNNING_QUERIES_SQL (:176-210):
+ LEFT(qt.text,600) text_head, RIGHT(qt.text,600) text_tail (custo nulo depois do TOP; 400 cortava rotas longas),
+ object_name. Campos de saida app_route/app_controller/app_action/app_source, aditivos; perfRenderStepTable mostra-os
sozinho. Redaccao viewer via P0. Testes payload com/sem tag; sp_executesql com amostra real capturada de
dm_exec_sql_text (documentar no runbook Pro, nao assumir).

## L2c - Pro (V6): "CPU por rota" + historico via Query Store

- GROUP BY query_hash sozinho COLAPSA rotas (mesmo hash chamado de /checkout e /cart = 2 sql_handle): consulta de
  1 scan com TOP 20 hashes por CPU x top 5 variantes por hash (<= 100 textos hidratados; SQL no ficheiro); Python
  soma CPU por rota dentro do hash; resto do hash = "outras variantes". Rotulo "x % das linhas, y % do CPU do
  TOP 20 amostrado", nunca "% da CPU do servidor". Painel ausente a cobertura 0. query_hash chega como bytes -> .hex().
- Historico: apos P0b, query_store_monitor le query_sql_text por query_id + runtime_stats_interval -> serie por
  rota SEM tabela nova (so' bases com QS ON, 2016+; 2014 = skip gracioso com teste).
- UI: unico trabalho de template genuino (painel novo) + i18n nos 6 locales do V6. Runbook Pro "modo seguro":
  tags estaticas, rotas por template, sem traceparent; apontar para o alarme L1b (portado).
- Piloto 30 dias em 2 instancias: nao ha' persistencia -> captura diaria scripted desde o dia 1 (scratchpad/CSV):
  % do total_worker_time do TOP 20 com app_route; delta de compilacoes; SQLCP kb; estado do QS. App de teste:
  nao existe app instrumentada na frota -> script Python/pyodbc que injecta tags estaticas na QLT.
- Barra (parecer): >= 50 % do worker_time do TOP 20 atribuido; compilacoes e plan cache +-10 %; QS nunca READ_ONLY.
  < 30 % -> L2 fica desligado por omissao. Feature flag com teste "desligar nao deixa app_route fantasma".

## L3 - Pro, NEEDS_DECISION: historico por rota com STG nova (V1)

NO-GO ate' L2c provar que o Query Store nao chega (< 30 % de cobertura por QS). Se avancar: 4 condicoes do guardiao
(familia de tabelas dedicada; cardinalidade medida no piloto; sem Sample_Text na 1.a versao; consulta ao guardiao
antes do DDL). Tabela nova limpa, NAO reaproveitar query_performance_log / performance_query_baselines (canonico
:14315, :15238, schema morto desenhado para outro fim) -> depreciar em lote proprio.

## Riscos e guardas transversais

- Sem baseline de duration_ms: medir N=20 antes/depois por endpoint tocado, mediana e max, gate +10 %.
- 333 testes leem o template hoje (contagem recalculada em cada lote, nao fixada).
- Prova por page.route sobre copia do template e auditor de contraste sao scripts de sessao (scratchpad), nao do repo:
  o gate marca-os [MANUAL] quando nao correm.
- Resultados do PoC com logins/hosts nunca entram no repo.
- Achados laterais para lotes proprios: performance router sem role (P0, security-auditor), query_store_monitor V6
  (P0b), conftest e2e 8433, docstring 886/294 vs 745/268, modules/ fora do CI do V6.
