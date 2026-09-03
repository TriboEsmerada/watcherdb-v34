# Plano — Wave "Reparação de fresh install" (canonical) + skip dos índices

**Data:** 2026-08-05 · **Estado:** PLANO (design, nada aplicado) · **Prioridade:** P1 (1º cliente)
**Origem:** achados do gate v1-intel + sql-deep-reviewer ao desenhar a Fase 3 da limpeza de
índices. Findings: [FIND-20260805-109](../../findings-inbox.md) (P1) + FIND-20260805-110 (P2).

> **Porque é prioritária:** um fresh install a partir só do `INSTALACAO_COMPLETA_UNIFICADA.sql`
> (o que um cliente novo recebe) **não recolhe** várias KPIs core. O ambiente vivo funciona só
> porque as tabelas foram criadas fora-de-banda por scripts standalone nunca mergeados. Com o
> foco no 1º cliente banking, instalar correctamente de raiz vale mais que a limpeza de índices.

---

## O que está partido (confirmado na fonte pelo v1-intel)

**Bloco A — tabelas base `_STG_BLUE/_GREEN` ausentes do canonical (FIND-109):**
`BACKUPS`, `TLOG_USAGE`, `ERRORLOG`, `BACKUP_EXEC_FAILURES`, `BACKUP_JOBS_DISABLED`,
`FG_USAGE`, `BLOCKED_SESSIONS`. Só existem em standalone:
- `SETUP_BLUE_GREEN_COMPLETO.sql` (BACKUPS :196-201, TLOG :540-545)
- `CREATE_BACKUP_HEALTH_STG_TABLES.sql` (:76,125,207,242)
Sem a base, o `usp_setup_environment_tables` faz no-op (IF NOT EXISTS RETURN) → as `_env`
nunca nascem → o collector falha `TRUNCATE/INSERT` em `_BLUE_<ENV>` inexistente.

**Bloco B — 5 KPIs com view a ler tabela sem sufixo de ambiente (FIND-110):**
`FILE_IO`, `WAIT_STATS`, `INDEX_USAGE`, `WORKER_THREADS`, `AG_QUEUE_SIZES`
(`INSTALACAO...:12117-12166`). O collector escreve `_BLUE_<ENV>`; a view lê a molde vazia.
Padrão já fechado para `PERF_COUNTERS`/`PERF_COUNTERS_DETAIL` em 22/07 (:12090-12111),
nunca estendido a estas 5. Falta também criar as variantes `_BLUE_<ENV>` destas 5.

**Bloco C — skip dos índices par cego (a Fase 3 da limpeza, dobrada aqui):**
- 8 famílias com base no canonical (DB_SETTINGS, SUSPECT_PAGES, AG_QUEUES, DBCC_HISTORY,
  SCHEDULER_HEALTH, JOB_DURATION, PERF_COUNTERS, AUTO_PAGE_REPAIR): `@skip=1` no caller
  **+ remover o `CREATE INDEX` hardcoded** da tabela base (linhas em FIND/parecer:
  PERF_COUNTERS :12209/12224, DB_SETTINGS :12246/12266, SUSPECT_PAGES :12287/12306,
  AG_QUEUES :12329/12350, DBCC_HISTORY :12372/12390, SCHEDULER_HEALTH :12441/12462,
  JOB_DURATION :12484/12504, AUTO_PAGE_REPAIR :15944/15965).
- `OS_PERF` (Secção 25, cursor dinâmico inline :13325-13389, `CREATE INDEX` :13370-13371):
  remover a criação do par cego aí.
- **NÃO tocar:** o índice filtrado `IX_FILE_IO_BLUE_Status WHERE Status!='OK'` (não é par cego);
  as famílias lidas (FILE_IO, WAIT_STATS, WORKER_THREADS, INDEX_USAGE, PERF_COUNTERS_DETAIL,
  AG_QUEUE_SIZES em PRD).
- `BACKUP_JOBS_DISABLED`: passar a `@skip=1` (PK `Id IDENTITY`, não lidera por Instance → par
  cego puro custo, como BACKUP_EXEC_FAILURES).
- 4 famílias DEPRECATED (BLOCKED_USERS, DB_IO_STATS, LONG_LOCKS, SERVICE_STATUS): `@skip=1`
  é cosmético (no-op hoje). Follow-up com a decisão de produto (sair do DDL vs reactivar).

## Ordem obrigatória (VETO do v1-intel)

**Bloco A ANTES de Bloco C** para BACKUPS/TLOG — não fechar o skip dos índices dessas famílias
sem primeiro criar a base, senão mascara-se o gap P1 atrás de um diff cosmético.

1. **Bloco A** — portar as base `_STG_BLUE/_GREEN` em falta para o canonical (padrão da SECÇÃO 22.8b).
   **SCOPE CONCRETO (mapeado na fonte 2026-08-06):** as 7 famílias em falta dividem-se em 2 padrões:
   - **Padrão SELECT-INTO** (5): `FG_USAGE`, `BACKUPS`, `ERRORLOG`, `BLOCKED_SESSIONS`, `TLOG_USAGE`
     — fonte `SETUP_BLUE_GREEN_COMPLETO.sql` (FG :156, BACKUPS :194, BLOCKED_SESSIONS :266,
     ERRORLOG :436, TLOG :538). Cada uma: `SELECT * INTO _BLUE/_GREEN FROM <legada> WHERE 1=0`
     + registar em `KPI_STG_ACTIVE_TABLE` + VIEW slot-aware. **OMITIR** a linha `INSERT ... SELECT *`
     de migração (é só p/ BD existente; fresh install a legada está vazia).
   - **Padrão CREATE-TABLE explícito** (2): `BACKUP_EXEC_FAILURES`, `BACKUP_JOBS_DISABLED`
     — fonte `CREATE_BACKUP_HEALTH_STG_TABLES.sql` (:73-193 e :197+). Têm `Id IDENTITY` PK clustered,
     índices próprios (NÃO par cego — manter), ACTIVE register, e a VIEW canonical. A "legada _STG"
     destas é uma **VIEW** (não tabela). Portar o bloco inteiro (tabela+índices+ACTIVE+view).
   **Ordem:** DEPOIS das legadas `_STG` existirem, ANTES dos callers de `usp_setup_environment_tables`
   (INSTALACAO :2620). **NÃO** duplicar as que já existem (todos os blocos são `IF NOT EXISTS`, logo
   idempotentes — porta seguro; verificar caso a caso quais faltam mesmo).
2. **Bloco B** — estender o padrão `_env` às 5 KPIs (criar `_BLUE_<ENV>` + view env-aware).
3. **Bloco C** — skip do par cego (callers `@skip=1` + remover `CREATE INDEX` hardcoded + OS_PERF inline).
4. **Sincronizar/arquivar** os standalone (SETUP_BLUE_GREEN_COMPLETO, CREATE_BACKUP_HEALTH_STG_TABLES,
   SETUP_ENVIRONMENT_TABLES avulso) — decidir: mergear no canonical e arquivar, para matar a
   superfície de drift (proc duplicada + escopos diferentes sob o mesmo nome).

## Gates + validação

- **Gate v1-intel** (veto de infra partilhada) ao diff antes de aplicar.
- **Confirmar com o counterpart V6** que V5/V6 leem sempre via VIEW (nunca `_STG_BLUE/_GREEN`
  directas) antes de fechar o Bloco C — o v1-intel não tem o repo V6 nesta sessão.
- **Ensaio:** validar num fresh install limpo (BD de teste) que as KPIs core passam a recolher.
- **Não é DDL na BD viva** (a viva já tem as tabelas) — é só canonical/reinstalador. Logo é
  edição de ficheiro (diff), não bloco de mutação. Mas afecta o próximo cliente → cuidado máximo.

## Relação com a limpeza de índices ao vivo

Independente. Os ~105 `DROP INDEX` + 12 `DROP TABLE` na BD **viva** (validados, dry run limpo,
rollback guardado) executam-se à parte, na janela. Esta wave é só o **canonical** (fresh install).

## Propagação V6

Toda esta wave muda o canonical → lote V6 dedicado a explicar: as base BLUE/GREEN portadas, o
padrão `_env` estendido, o skip do par cego, e a decisão sobre os standalone. Regra de sempre.
