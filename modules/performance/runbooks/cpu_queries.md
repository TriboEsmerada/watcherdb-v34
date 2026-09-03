# Runbook — CPU Queries

## Passo 1: Identificar as top queries por total_worker_time
No plan cache, a soma de CPU acumulada desde o ultimo restart. Top 5
concentram tipicamente 70-90% do CPU.

## Passo 2: Detectar Parameter Sniffing
No L3 do modal, secao "Parameter Sniffing Detection": queries com mesmo
plan_handle e variancia de logical_reads > 10x entre execucoes.
Solucao: OPTION (RECOMPILE), OPTIMIZE FOR UNKNOWN, ou plan guide.

## Passo 3: Verificar Recompiles excessivas
Queries com > 20 recompiles/dia tem problema estrutural:
- Stats desactualizadas -> UPDATE STATISTICS
- Tabelas temporarias sem indice -> considerar table type
- Triggers que forcam recompile

## Passo 4: Avaliar Resource Governor (opcional)
Em instancias com workloads mistas (OLTP + reports), considerar Resource
Governor para limitar CPU de reports.

## Passo 5: Escalar CPU como ultimo recurso
Se o tuning nao resolver: MAXDOP, cost threshold for parallelism, ou
mais vCPUs. Nao comecar por aqui.

## Referencias
- sys.dm_exec_query_stats: stats cumulativas
- sys.dm_exec_query_memory_grants: se e pressao de memoria mascarada de CPU
