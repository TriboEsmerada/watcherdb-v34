# Chaves naturais das famílias STG (extraídas das `_STG_OLD` antes de as dropar)

**Data:** 2026-08-05 · **Fonte:** PKs clustered das 12 tabelas `_STG_OLD` (remanescentes
da migração BLUE/GREEN, `sp_rename`, nunca limpas). São a **única documentação viva do
desenho original** das chaves — extraídas antes do `DROP TABLE` (aviso do `sql-deep-reviewer`).

**Uso:** fonte para a **Fase 3** (corrigir `usp_setup_environment_tables` para criar PK
clustered) e a **Fase 4** (retrofit de PK nas famílias muito lidas). **Todas lideram por
`Instance`** — logo a clustered por `Instance` dá seek nativo e substitui o par cego.

| Família STG | Chave natural (PK clustered original) |
|---|---|
| BACKUPS | `Instance, Database, Backup_Type` |
| BLOCKED_SESSIONS | `Instance, Session_Id, Update_TS` |
| BLOCKED_USERS | `Instance, User, Update_TS` |
| DB_AVAILABILITY | `Instance, Database` |
| DB_IO_STATS | `Instance, Database, Update_TS` |
| DISK_USAGE | `Instance, Drive` |
| ERRORLOG | `Instance, Log_Date, Log_Text_Hash` |
| FG_USAGE | `Instance, Database, Filegroup` |
| INST_AVAILABILITY | `Instance` |
| LONG_LOCKS | `Instance, Session_Id, Update_TS` |
| SERVICE_STATUS | `Instance, Service_Name, Update_TS` |
| TLOG_USAGE | `Instance, Database` |

**Nota de excepção (do reviewer):** `BACKUP_EXEC_FAILURES` e `BACKUP_JOBS_DISABLED` têm PK
`Id IDENTITY` (não lidera por Instance) → aí o par cego é puro custo, **drop directo** (não
promover a PK por Instance). A proc já foi alterada a 30/07 com `@skip_default_indexes=1`
para essas + ERRORLOG.

**HIST não entra nesta campanha** (é outra classe: `KPI_OS_MEMORY_HIST`, `AGENT_JOBS_HIST`,
`SERVICE_STATUS_HIST` — índices de história com covering, lidos por baseline/relatórios;
analisar à parte, não dropar em bloco com o par cego das STG).
