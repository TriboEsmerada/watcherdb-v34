# Runbook — Memory Queries

## Passo 1: Distinguir pressao real vs sobrestimacao
- **Pressao real:** sessoes em RESOURCE_SEMAPHORE (step 2) → memoria OS esgotada
- **Sobrestimacao:** granted_kb >> used_kb (step 3) → optimizer errado, mas sem queue

## Passo 2: Em caso de pressao real
1. Medir `Total Server Memory` vs `Target Server Memory` (perf counters)
2. Se Total < Target: OS esta a ceder memoria (memory pressure externa)
3. Se ambos estao no max_server_memory: considerar aumentar

## Passo 3: Em caso de sobrestimacao
- UPDATE STATISTICS FULLSCAN nas tabelas envolvidas (off-hours)
- Verificar se ha Legacy Cardinality Estimation (compat level < 120)
- Hint OPTION (MIN_GRANT_PERCENT = X) como ultimo recurso

## Passo 4: Reduzir grants excessivos
Queries com `total_grant_kb > 1GB` merecem atencao:
- Procurar Sort/Hash operators grandes no plano
- Considerar INDEX sorted em ORDER BY / GROUP BY columns

## Passo 5: MAXDOP e memoria
Grants escalam com DOP. Se instance tem MAXDOP 8 mas workload e OLTP:
- Baixar MAXDOP para 2 ou 4
- Validar cost_threshold_for_parallelism (50 default e muito baixo)

## Referencias
- sys.dm_exec_query_memory_grants: grants activos
- sys.dm_exec_query_resource_semaphores: queue de espera
- KB: "Understanding SQL Server Memory Grant"
