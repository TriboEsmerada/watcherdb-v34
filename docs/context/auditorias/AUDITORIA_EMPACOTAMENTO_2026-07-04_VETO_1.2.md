# Etapa 1.2 (identity flip) — Parecer do watcherdb-v1-intel-specialist

Data: 2026-07-04 | Solicitado pelo orquestrador (veto obrigatório, infra partilhada)

## VEREDITO: APROVADO-COM-CONDIÇÕES (sem veto; 2 bloqueadores hard antes do flip)

## Bloqueadores hard (confirmados em evidência, não hipóteses)

1. GAP 3 — VIEW DATABASE STATE per-user-DB EM FALTA nos 84 servidores
   monitorizados. Logs de execução reais (V1/logs/grants/grants_execution_
   20251226_*.log): só o subset GRANTS_MSDB_SQL foi aplicado (VIEW SERVER
   STATE + msdb pontual + master VIEW DATABASE STATE). O loop Parte 2 do
   GRANTS_SQL_MONITORING_SEGUROS.sql:65-97 (VIEW DATABASE STATE por user DB)
   NUNCA correu. Pós-flip, queries per-DB (sys.dm_db_*) falham SILENCIOSAMENTE.
2. GAP 1 — sysjobsteps/sysjobschedules/sysschedules sem GRANT em nenhum
   script canónico. CONFIRMADO NECESSÁRIO pelo orquestrador via grep:
   api/routers/jobs.py usa as 3 tabelas em 14+ queries (:251,:294,:462,
   :1051-52,:1283-84,:1312-13,:1326,:1359-60,:1402-03) + live_monitoring.py:487.

## Achado crítico — login partilhado V1↔V3.3

sql_monitoring é O MESMO principal que o V1 collector já usa via SQL-auth
(credential_manager_v2.py:67, CM_TARGET_PREFIX="WatcherDB:sql_monitoring:";
master credential em sql_credentials.enc). O flip não muda nada para o V1
em runtime, MAS a password passa a viver em 2 ficheiros Fernet (V1
sql_credentials.enc + V3.3 servers.json): rotação que atualize só um derruba
o outro silenciosamente. PRÉ-CONDIÇÃO: runbook de rotação ÚNICO cobrindo ambos.

## Questão urgente ortogonal (para o owner)

ZERO_DAY_SQL_PASSWORD_ROTATION.md (V1/docs/security) está "AGUARDA EXECUCAO
MANUAL". Se a rotação nunca correu, a password em uso é a exposta no commit
fd85638. Independente do flip — confirmar estado JÁ.

## Sequência de rollout aprovada pelo specialist

1. Fechar Gap 1 (aditivo ao SEGUROS.sql) + reaplicar SEGUROS.sql COMPLETO
   (não subset) nos 84 servidores — operação DBA one-off do owner.
2. Validação read-only por servidor-piloto (standalone/FCI/AlwaysOn):
   SELECT em sys.dm_db_file_space_usage numa user DB autenticado como
   sql_monitoring deve devolver linhas (hoje falha).
3. Flag intelligence_use_windows_auth=False SÓ em TST (3 pilotos).
4. Suite V3.3 (jobs/alwayson/live_monitoring/service_status) vs baseline.
5. PRD por waves, Trusted como fallback explícito 1 sprint.
6. Só depois: flip do default em settings.py.

## Riscos adicionais levantados

- Docstring connection_pool.py:461-473 desatualizada ("datareader") — corrigir
  no commit do flip.
- DENY SELECT ON SCHEMA::dbo global (SEGUROS.sql:85): grep prévio por SELECTs
  diretos a tabelas de negócio nos routers antes do flip final.
- xp_readerrorlog direto (service_status.py:90): degradação graciosa na fase 1
  (wrapper proc só existe na Intelligence DB, não nos 84 servers).
