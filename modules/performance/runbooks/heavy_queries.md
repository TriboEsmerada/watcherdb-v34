# Runbook — Heavy Queries (multi-offenders)

## Passo 1: Priorizar pelo heavy_score
Score 70-100 = CRITICAL (afecta multiplas dimensoes). Atacar primeiro.
Score 40-70 = WARNING (tuning preventivo). Atacar depois.

## Passo 2: Analisar o score breakdown
A query com heavy_score=85 pode ter:
- cpu_score 30, reads_score 25, duration_score 20, memory_score 5, frequency_score 5 → CPU+I/O bound
- cpu_score 15, reads_score 10, duration_score 20, memory_score 15, frequency_score 25 → frequencia e o problema

A componente dominante indica onde tunar.

## Passo 3: Multi-offenders (step 2) sao ROI alto
Queries presentes em top-20 CPU E top-20 I/O simultaneamente — tuning delas beneficia em 2 dimensoes.

## Passo 4: Frequent + slow (step 3)
Impacto = frequencia x latencia. Query que corre 1000x/dia com avg_elapsed 2s = 2000s/dia de carga.
Reduzir para 500ms = 1500s/dia poupados.

## Passo 5: Verificar plan cache reuse
Heavy queries devem ter plan cache hit. Se count(cached_plans) por query_hash >> 1,
pode haver parameter sniffing ou plan bloat — ver runbook cpu_queries.

## Passo 6: Medir antes/depois
Importante registar baseline antes de qualquer accao. POST /api/v1/performance/action-history
com outcome_before e outcome_after apos tuning.

## Referencias
- Formula de heavy_score: 30% CPU + 25% reads + 20% duration + 15% memory + 10% frequency
- Pesos podem ser ajustados editando o SQL no investigator se prioridades mudarem
