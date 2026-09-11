# Achados da 1.ª corrida do TestSukita v1 (11/09, 14:16–14:49, 8434, HEAD 0ce813e)

72 casos medidos (smoke 34, semântico 7, interações 30, API 2 × 150 endpoints), 36 saltados (admin sem conta),
qa-externo 5/5. Evidência em docs/qa/externo/2026-09-11/council/ (pytest.log, cases/*.json, service_log_window.log,
RATCHET.md). Classificação: **P** = portal (achado), **R** = runner (corrigido no PASSO 3), **O** = operação.

| # | Tipo | Achado | Evidência | Hipótese / correção |
|---|---|---|---|---|
| 1 | P2 | `/api/sqlserver-kpis/dashboard`, `/disk-usage`, `/filegroup-usage`, `/statistics-outdated`, `/tempdb-usage` devolvem 500 nos dois perfis | log: `TypeError: Object of type Decimal is not JSON serializable` ×16, em api/routers/sqlserver_kpis.py:122 (get_kpi_dashboard) e :220 (get_disk_usage) | Router legado sem consumidor no portal (0 referências a `/api/sqlserver-kpis` no template). Ou serializar Decimal (jsonable_encoder) ou desmontar o router. Decisão de produto |
| 2 | P2 | `/api/queries/database-io-stats/{id}` e `/api/queries/tempdb-growth-analysis/{id}` devolvem 500 | log: `TypeError: SQLServerMonitoring.execute_query() got an unexpected keyword argument 'params'` em modules/monitoring/backup_pattern_analysis.py:220 (`execute_query(server_id, query, params=[database_name])`); a assinatura em monitoring.py:865 é `(server_id, query, database=None)` | Chamada com kwarg que a função não aceita: o endpoint nunca funcionou por este caminho. Corrigir a chamada (parametrizar a query) e cobrir com teste |
| 3 | P2 | `/api/monitoring/security/server/{id}/critical` devolve 500 | log: `AttributeError: 'JSONResponse' object has no attribute 'get'` em watcherdb/api/routers/security.py:177 | `get_server_security_analysis` devolve JSONResponse e o chamador trata-o como dict. Devolver o dict e deixar o FastAPI serializar |
| 4 | P2 | `[AUTH] Query error: Invalid column name 'must_change_password'` a cada login | log linhas 20 e 527; auth_compat.py:335 faz SELECT da coluna; o canónico tem-na (3 referências) | Coluna em falta na WatcherDB_Users da 8434: migração por aplicar (o owner corre o SQL). Não é fatal, mas é um erro por login |
| 5 | P2 | `/api/queries/active-sessions/SQLHDSPRD405_I01` devolve 500 (pedido do browser do owner, 10.89.0.60, durante a corrida) | log: `pyodbc.ProgrammingError 42000 ... The target database, 'CitrixCVAD7SLogging', is participating in an availability group` | Mesma classe do fix de 05/08 (HAS_DBACCESS): a query de sessões toca numa base secundária não legível. Guardar com HAS_DBACCESS ou excluir na origem |
| 6 | P3 | `/api/admin/health` devolve 200 ao viewer | api_smoke viewer; watcherdb/api/routers/admin_metrics.py:281 sem dependência de role | Expõe só contadores de uso. Se é público por desenho, mover para fora de `/admin`; senão gatear. Whitelisted no runner até decisão |
| 7 | P3 | Lentidão: `/api/queries/deadlocks/{id}` e `/api/users/server/{id}` sem resposta em 20 s; `/api/sqlserver-kpis/alwayson-status` 18,7 s; `/api/diagnostics/network-test/{id}` 15,4 s | api_smoke viewer e dba, instância TST | deadlocks e users em TST com >20 s é anómalo; alwayson-status é do router legado (#1); network-test é sonda por desenho (excluída do smoke) |
| 8 | P3 | 125 tracebacks `ConnectionResetError 10054` em 33 min | service_log_window.log | Cancelamentos de pedidos pelo browser (troca de aba) a ir para o log como traceback completo. Higiene: apanhar e registar em uma linha |
| 9 | O | Serviço parou e arrancou a meio da corrida | log: "Shutting down" → "Started server process [25468]" → "Application startup complete"; Event 7039 às 14:20:22; smoke disk/space e interações disk com ERR_CONNECTION_REFUSED e Page.goto timeout | Paragem graciosa (não crash). Confirmar com o owner se foi restart manual. O runner passa a rotular esta assinatura como "serviço em baixo durante a corrida" |
| 10 | R | `[viewer] dashboard sem cartoes` no drill-down | semântico viewer; `_espera_dashboard` passou e a leitura seguinte veio vazia | Re-render do dashboard (refresh 30 s) entre a espera e a leitura. PASSO 3: até 3 leituras com 700 ms |
| 11 | R | Hipótese errada no ratchet para tab_disk | RATCHET.md classificou ERR_CONNECTION_REFUSED como "instância lenta" | PASSO 3: assinatura nova → "serviço em baixo/reiniciado" |

## O que o v1 provou

- Os cinco primeiros achados são 500 reais em endpoints que o portal ou o cliente da API podem chamar; nenhum tinha sido
  visto pelo smoke, pelo qa-externo ou pelo TestSprite, porque nenhum deles percorria o OpenAPI.
- O achado 5 veio do log do serviço da janela da corrida, sem o runner o ter pedido: a correlação teste↔serviço paga-se.
- O ratchet já distingue regressão (tab_disk, por causa do restart) de novas (api_smoke) e dá hipótese em cada uma.

## Para o findings-inbox (formato compacto)

```
FIND-20260911-1xx | P2 | 5 endpoints /api/sqlserver-kpis/* 500: Decimal nao serializavel (router legado sem consumidor no portal) | TestSukita api_smoke
FIND-20260911-1xx | P2 | database-io-stats + tempdb-growth-analysis 500: execute_query(params=) nao existe (backup_pattern_analysis.py:220) | TestSukita api_smoke
FIND-20260911-1xx | P2 | security/server/{id}/critical 500: JSONResponse.get (security.py:177) | TestSukita api_smoke
FIND-20260911-1xx | P2 | coluna must_change_password em falta na WatcherDB_Users da 8434 (erro por login) | service_log_window
FIND-20260911-1xx | P2 | active-sessions/{id} 500 em base AG secundaria nao legivel (falta HAS_DBACCESS) | service_log_window (browser do owner)
FIND-20260911-1xx | P3 | /api/admin/health publico; deadlocks e users/server >20s em TST; 125 tracebacks 10054 por cancelamentos | TestSukita
```
