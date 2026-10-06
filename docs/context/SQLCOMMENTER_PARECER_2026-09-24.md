# sqlcommenter no WatcherDB - parecer do council (2026-09-24)

Colocacao avaliada: "o WatcherDB nao sabe qual endpoint disparou a query; a ponte
padrao de mercado e' o sqlcommenter (comentario route/controller/traceparent no texto
da query); o WatcherDB leria route/controller e juntava a waits e Query Store: 'essa
query que come 40% da CPU vem do /checkout'. Isso vende pra banco."

Especialistas: sql-deep-reviewer, architecture-advisor, watcherdb-marketing-strategist
(com web), watcherdb-v1-intel-specialist (guardiao), challenger, customer-success-persona.

## Veredicto (6/6): NAO como proposto. Versao reduzida, em lotes, sem tocar na app.

### Tres factos que matam a versao literal

1. **traceparent no texto rebenta o plan cache e cega o produto.** Em SQL Server a
   chave do plano ad hoc e do sp_executesql(@stmt) e' o texto exacto, comentarios
   incluidos (query_hash NAO inclui o comentario; o plano sim). Um id unico por pedido
   = compilacao e plano novo por execucao; Query Store enche e passa a READ_ONLY ou,
   em AUTO, deixa de captar a query quente. Os investigators classificam POR LINHA do
   plan cache sem GROUP BY query_hash (heavy_queries.py:105-150, cpu_queries.py:85-110,
   slow_queries.py:78-96, live_monitoring.py:1040-1058): a query de 40% espalha-se por
   milhares de linhas com execution_count=1 e sai de todos os TOP 20. Forced
   parameterization e optimize for ad hoc nao colapsam comentarios.
2. **Stored procedures nao herdam o comentario.** O sql_handle dos statements caros
   aponta para a definicao da proc; o comentario fica na linha barata do EXEC. Em
   banco, procs/SSIS/batch/core fechado dominam o CPU -> cobertura historica zero
   onde mais interessa.
3. **Nao ha substrato historico.** O V1 nao persiste texto de query nem program_name/
   host_name (PROCESSES_STG e BLOCKED_SESSIONS_STG so tem Command = tipo da DMV;
   INSTALACAO_COMPLETA_UNIFICADA.sql:1069-1081, 1202-1216; unica excepcao
   DEADLOCKS.Deadlock_Graph). Tudo o que e' texto de query e' read-path live do portal.
   "Rota ao longo do tempo" exigiria familia STG nova + colector novo (guardiao: GO
   com 4 condicoes, nunca coluna numa STG existente).

### Mercado (fontes no handback do marketing)

- Nenhum vendor puro de SQL Server (Redgate, Idera, dbWatch, Quest standalone) faz
  correlacao app->query. Quem faz (Datadog, Dynatrace, New Relic, SolarWinds) tem
  agente APM proprio dentro da app; Datadog em SQL Server usa SET context_info via
  tracer .NET/Java, nao comentario sqlcommenter.
- open-telemetry/opentelemetry-sqlcommenter arquivado (2025-11-17); enable_commenter
  no OTel so' para MySQL/psycopg/SQLAlchemy; sem lib para ADO.NET/EF6/JDBC directo;
  OTel sqlserverreceiver com issue aberta (2026-05) a admitir que nao captura metadata.
- Persona DBA: das 30-40 apps criticas de um banco, 2-5 sao instrumentaveis; nenhuma
  e' o core. Ecra com 95% "sem atribuicao" e' pior do que nao ter a feature.

### Correccao a um parecer

O challenger afirmou "o produto nao le Query Store". Errado: plan_analysis.py:152-180
consulta sys.query_store_query/plan/runtime_stats por query_hash (2016+).

## Recomendacao (consenso)

- **PoC de 1 dia antes de qualquer lote** (sql_monitoring, so' SELECT, 1 PRD + 1 QLT):
  (1) amostrar dm_exec_requests x dm_exec_sessions 10 s / 1 h -> % do CPU sob
  program_name generico (>=60% = lacuna real; <30% = e' so' agregacao de portal);
  (2) program_name distintos por login em 24 h; (3) bases com Query Store ON;
  (4) sintetico em QLT: 1000 execucoes com comentario unico vs sem -> contagem em
  dm_exec_cached_plans (script do sql-deep-reviewer no handback).
- **Lote 1 (Std, portal, sem V1):** agregacao de queries pesadas/blocking/waits/
  tempdb por program_name + host_name + login_name ja' lidos e ja' redigidos por role
  (cpu_queries.py:95-97, live_monitoring.py:107-112, 285-287); acrescentar
  program_name/host_name a TOP_SLOW_QUERIES_DETAILED (queries.py:747-787, so' tem
  login); KPI "aplicacoes sem nome" (drivers genericos); guia de 1 pagina
  Application Name= / applicationName= / APP= na connection string (funciona em
  Delphi e pacotes fechados, sem codigo).
- **Lote 1b (Std, vendavel por si):** alarme "N variantes de texto para o mesmo
  query_hash em X min" = poluicao do plan cache por SQL nao parametrizado. Dor real
  do DBA (persona) e protege contra um cliente que ligue traceparent.
- **Lote 2 (opcional, so' apos piloto):** parser no read-path (helper partilhado)
  para sqlcommenter `/*k='v'*/` na cauda E EF Core TagWith `-- tag` na cabeca; chaves
  estaticas (route/controller/action/application), traceparent descartado sempre;
  texto via RIGHT/LEFT(t.text,400) antes do LEFT(...,500) de live_monitoring.py:295;
  agregacao por query_hash somando CPU por tag, rotulada "quota do TOP N amostrado",
  nunca "% da CPU do servidor"; invisivel a 0% de cobertura; runbook Std com os dois
  niveis. Tier: parser Std, historico por rota Pro (FEATURE_MATRIX sem entrada ->
  DBA Lead).
- **Nao fazer:** traceparent no texto; coluna nova em STG existente; XE por
  client_app_name (NEEDS_DECISION, Pro-leaning, DDL na instancia do cliente).
- **Propagacao V6:** lotes 1/2 sao modulo do portal; nada para V1; nota
  PROMPT_PROPAGACAO_V6 quando houver codigo.

## Barra medivel para reabrir "vende pra banco"

- 2 instancias piloto, 30 dias: >= 50% do total_worker_time do TOP 20 com atribuicao
  (app_route ou program_name nao generico); < 30% mata a feature no Std.
- SQL Compilations/sec e tamanho do plan cache (CACHESTORE_SQLCP/OBJCP) dentro de
  +-10% da semana anterior; Query Store nunca em READ_ONLY.
- 3 incidentes reais de CPU: "que equipa e'" em < 5 min no portal.

Frase de posicionamento (marketing + persona): "sem tocar numa linha da tua app
legada, o WatcherDB diz-te que servico e que login dispararam a query" - o valor
que o Director de IT compra e' menos dependencia da equipa de dev, nao mais.

## Notas laterais

- CONTEXT.md com 537 linhas (limite 300) -> /manutencao-contexto.
- query_performance_log e performance_query_baselines no canonico V1 (:14315, :15238)
  sao schema morto (zero writers); reaproveitar ou depreciar antes de criar 3.a tabela
  de query_hash.
- Bulletin Nestor: post P3 do marketing dirigido ao v1-intel com o quick-win do
  program_name em TOP_SLOW_QUERIES_DETAILED.
