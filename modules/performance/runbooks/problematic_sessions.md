# Runbook — Problematic Sessions

## Passo 1: Identificar o tipo de problema
Sessoes problematicas sao de 3 tipos:
- CPU alto sustentado (cpu_time > 60s)
- Memoria alta (memory_usage > 100MB)
- Duracao longa (> 10min)

## Passo 2: CPU alto — investigar query activa
Ver sql_text + wait_type. Normalmente e uma query legitima pesada ou
um plano mau (ver runbook cpu_queries).

## Passo 3: Memoria alta — memory grants
Ver sys.dm_exec_query_memory_grants. Grants > 100MB sem uso real (used_mb
muito menor que granted_mb) indicam optimizer a sobrestimar.
Solucao: UPDATE STATISTICS ou hint OPTION (MIN_GRANT_PERCENT=N).

## Passo 4: Duracao longa — investigar wait
Long sessions com wait_type:
- ASYNC_NETWORK_IO: cliente lento (nao e problema de DB)
- PAGEIOLATCH: I/O storage lento
- LCK_*: a ser bloqueada (ver runbook blocking_chains)
- CXPACKET: paralelismo excessivo (ajustar MAXDOP)

## Passo 5: KILL com cuidado
Apenas se: sessao zombie (host morto), transacao aberta sem progresso, ou
ticket autorizado. Sempre registar em action_history.

## Referencias
- sys.dm_exec_sessions + sys.dm_exec_requests JOIN
- sys.dm_exec_connections: protocolo e encryption
