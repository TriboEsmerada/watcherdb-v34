# Runbook — Slow Queries

## Passo 1: Identificar a query dominante
No L4 do modal ver "Top 20 by total_worker_time" — as top 3-5 queries
geralmente concentram >80% do impacto. Focar nessas primeiro.

## Passo 2: Verificar plan cache e query plan
Em SSMS: `SELECT * FROM sys.dm_exec_query_plan(plan_handle)`. Procurar:
- Table Scans em tabelas grandes
- Hash/Sort operators que derramam para tempdb
- Missing Index hints do optimizer

## Passo 3: Decisao — Index vs Query rewrite vs Plan guide
- Missing index com priority > 1M: testar CREATE INDEX em TST
- Plan instavel com variancia de reads > 10x: parameter sniffing — OPTION (RECOMPILE)
- Query gerada por ORM: considerar hints ou procedure dedicada

## Passo 4: Validar em TST antes de aplicar em PRD
Reproduzir a query com mesmos parametros. Medir antes/depois. Documentar
no L3 do modal via endpoint /action-history.

## Passo 5: Monitorizar regressao
Baselines sao actualizadas diariamente. Se a query aparecer de novo com
mesma query_hash, o fix nao resolveu a causa raiz.

## Referencias
- sys.dm_exec_query_stats (cumulativo desde ultimo restart)
- sys.query_store_runtime_stats (se Query Store activo — recomendado)
