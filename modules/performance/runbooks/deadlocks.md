# Runbook — Deadlocks

## Passo 1: Identificar a tabela/objecto envolvido
Abrir o L4 do modal e ver os 4 steps. Se houver padrao (mesma tabela/indice
em multiplos deadlocks), o problema e de design de acesso. Se e aleatorio,
pode ser blocking escalation.

## Passo 2: Analisar a ordem de acesso a objectos
Deadlocks classicos: Transacao A bloqueia T1->T2, Transacao B bloqueia T2->T1.
Garantir que TODAS as transacoes acedem objectos na MESMA ordem. Se necessario,
ajustar codigo da aplicacao ou procedures.

## Passo 3: Considerar Read Committed Snapshot Isolation (RCSI)
Se a leitura e a causa (locks S a bloquear X), RCSI elimina locks de leitura.
ALTER DATABASE [x] SET READ_COMMITTED_SNAPSHOT ON;
AVISO: aumenta tempdb. Validar em TST antes de PRD.

## Passo 4: Implementar retry com backoff na aplicacao
Error 1205 e recuperavel. Aplicacao deve fazer retry (1-2x) com backoff
exponencial. NUNCA fazer retry infinito.

## Passo 5: Capturar deadlock graph
Se o padrao continuar, activar Extended Event `system_health` (ja activo por
default em SQL Server 2014+) ou criar um dedicado. Analisar o graph em SSMS.

## Referencias
- https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide
- KPI_MSSQL_DEADLOCKS_DET_VIEW: tem victim_session, object_name, index_name, lock_mode
