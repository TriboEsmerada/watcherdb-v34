# Runbook — Blocking Chains

## Passo 1: Identificar o lead blocker
Lead blocker = sessao no topo da cadeia que nao esta a ser bloqueada mas
esta a bloquear outras. No L4 do modal, "Lead blockers" lista estas sessoes.
Essa e a sessao a atacar.

## Passo 2: Investigar o SQL da lead blocker
Ver sql_text + wait_type. Wait_type mais comuns:
- LCK_M_X, LCK_M_U: a esperar lock exclusive/update
- ASYNC_NETWORK_IO: cliente lento a consumir resultados
- SOS_SCHEDULER_YIELD: CPU pressure
- PAGEIOLATCH_*: I/O lento

## Passo 3: Decidir accao
- Transacao aberta >5min sem razao -> comunicar ao owner / KILL com ticket
- Query legitima mas lenta -> otimizar (ver runbook slow_queries)
- Padrao recorrente -> isolation level ou design de acesso

## Passo 4: Prevenir reincidencia
- Considerar RCSI se as vitimas sao leituras
- Aplicacao deve fechar transacoes explicitamente
- Session timeout na aplicacao (evita sessoes mortas)

## Passo 5: KILL como ultimo recurso
KILL <spid> WITH STATUSONLY para ver progresso. Se rollback > 5min,
deixar terminar naturalmente. Registar em action_history.

## Referencias
- sys.dm_exec_requests: blocking_session_id
- sys.dm_os_waiting_tasks: wait_type + blocking_session_id
