# PROMPT PROPAGACAO V6 — KPI Backup Failed FASE 2 (Resolved_By_Success_TS)
Data: 2026-08-21 | Origem: sessao V3.3 Fase 2 (council 21/08 + v1-intel GO-com-condicoes)
Predecessor: PROMPT_PROPAGACAO_V6_BACKUP_RECUPERADO_2026-08-21.md (Fase 1)

## O QUE MUDOU E PORQUE (explicacao, nao so diff)

**Problema de fundo** (bulletin v33->v1-intel 21/08): a Source 1 do collector
`collect_backup_failures.py` (sysjobhistory) grava `[Database]=NULL` por
desenho — a falha e' de JOB, nao de database. Logo o check "unresolved-only"
por-database (Wave R+13, via `KPI_MSSQL_BACKUPS_STG.Last_Backup_Date`) nunca
disparava para estas linhas, e a falha so' saia do KPI por IDADE (janela 7d do
collector) — nunca por verificacao de sucesso. Job com cadencia > 7d falhado
desaparecia sozinho SEM ter recuperado = falso-negativo silencioso.

**Fase 1** (V3.3-only, commit V3.3 `b13a7e2`): verificacao job-level no
CONSUMIDOR via JOIN a `KPI_MSSQL_AGENT_JOBS_STG` (LastRunStatus/LastRunDate =
so' o ULTIMO run), fail-open com snapshot stale >15 min.

**Fase 2** (este lote): a verificacao moveu-se para o COLLECTOR V1 — infra
PARTILHADA, por isso V6 herda os dados automaticamente:

1. Nova coluna `Resolved_By_Success_TS DATETIME2 NULL` nas 8 tabelas
   `KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_{BLUE,GREEN}[_PRD/_QA/_TST]` + view
   refreshed (`sp_refreshview` — view e' `SELECT *` UNION ALL, licao R+11.2).
   Migration: `WATCHERDB INTELLIGENCE V1/database/MIGRATION_F2_RESOLVED_BY_SUCCESS_TS.sql`.
2. O collector preenche a coluna na propria query (Source 1): OUTER APPLY a
   `msdb.dbo.sysjobhistory` — `MIN` do primeiro sucesso (`step_id=0`,
   `run_status=1`) POSTERIOR a falha, sobre o historico COMPLETO (nao so' o
   ultimo run). Sources 2/3 (is_damaged, no_checksum): sempre NULL (nao ha
   conceito de sucesso de job). `>` estrito = continue-on-error nao conta.
3. Janela Source 1: 7d -> 30d (alinha com is_damaged; fim do aging-out).
4. Contrato para consumidores: **`Resolved_By_Success_TS IS NULL` = falha
   ainda em falta** (e' o que o tile deve contar). NOT NULL = recuperada
   (modal mostra com badge, nunca esconder silenciosamente — council 21/08).
   Fail-open e' ESTRUTURAL: sem evidencia de sucesso => NULL => conta.

**Semantica que muda (importante, nao e' regressao):** padrao
falha->sucesso->falha: Fase 1 (ultimo run = Failed) mantinha a falha ANTIGA
activa; Fase 2 resolve a antiga e mostra so' a nova. Contagens podem divergir
da Fase 1 — e' a semantica correcta (parecer v1-intel 21/08, pergunta 6).

## O QUE O V6 HERDA SEM FAZER NADA

- Coluna + dados (BD partilhada). Depois da migration + restart do collector
  V1, a view ja' expoe `Resolved_By_Success_TS` populado.

## O QUE O V6 TEM DE FAZER NO CODIGO DELE

ATENCAO: V6 portal NAO e' superset do V3.3 (memoria
`feedback_v6_portal_not_superset`) — **grep primeiro**, nao assumir que os
anchors da Fase 1 existem.

1. `grep -n "BACKUP_EXEC_FAILURES" api/routers/intelligence_kpis.py` — pontos
   conhecidos (verificados pelo v1-intel 21/08): ~1571-1579, ~3455-3463,
   ~4438-4444. Em cada consumidor do tile/contagem "backup failed":
   adicionar `f.Resolved_By_Success_TS` ao SELECT e excluir da contagem as
   linhas `IS NOT NULL` (ou filtrar `WHERE ... IS NULL` se a query so' serve
   a contagem). Modal/detalhe: manter as linhas recuperadas com campo
   `Recovered`/`Recovered_At` derivado da coluna (badge, se o portal V6 tiver
   esse modal — grep antes; se nao tiver, so' a contagem muda).
2. SE a Fase 1 do prompt predecessor ainda NAO foi aplicada em V6: **saltar a
   Fase 1 por completo** — implementar directamente a Fase 2 (mais simples:
   sem JOIN a AGENT_JOBS_STG para recuperacao, sem check staleness 15 min).
   SE ja' foi aplicada: substituir o mecanismo (remover helper/JOIN de
   recuperacao; manter JOIN a AGENT_JOBS_STG APENAS se estiver a alimentar
   campos de agendamento tipo Next_Run_Date, como no V3.3 17/08).
3. Doc catalog V6: `docs/catalog/21_backup_exec_failures.md` — corrigir o doc
   drift (dizia append/14d/48h; real e' Blue-Green full-swap com janelas por
   fonte 30d/30d/7d-agregado) + documentar a coluna nova. (Mesmo drift ja'
   corrigido 21/08 na Nestor central `watcherdb-family/architecture/kpis/
   backups_kpis.md` e `cross_cutting/intelligence_db_schema.md`.)
4. AI Assistant/NLU V6 (`services/ai_assistant_service.py`,
   `watcherdb/ai/nlu/ontology.py`): se descrevem o KPI Backup Failed, alinhar
   a semantica (unresolved-only via coluna; janela 30d).

## VALIDACAO NO V6

- Antes do cutover: `SELECT COUNT(*) FROM KPI_MSSQL_BACKUP_EXEC_FAILURES_STG
  WHERE Failure_Source='sysjobhistory' AND Resolved_By_Success_TS IS NOT NULL`
  > 0 (collector novo ja' correu). Medicao V3.3 21/08 como referencia: 76%
  (38/50) das falhas na janela ja' recuperadas.
- Depois: contagem do tile V6 == linhas `IS NULL` (por tipo, apos classify).
- Nao comparar contra Fase 1 a espera de igualdade exacta (ver semantica).

## PRECEDENTES/REGRAS INVOCADAS

- Migration standalone + sp_refreshview: precedente
  `MIGRATION_R_R11_2_BACKUP_TYPE_CLASSIFIED.sql` (CHANGELOG_JOBS_COLETA.md).
- Compat SQL 2005 na query do collector (sem CAST DATETIME2; OATXP01).
- Canonical + docs no mesmo bloco do DDL (regra owner 24/07).
