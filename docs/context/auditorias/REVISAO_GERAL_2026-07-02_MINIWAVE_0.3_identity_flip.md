# Mini-wave 0.3 — Identity flip (Trusted → sql_monitoring)

> Data: 2026-07-02 | Prep para o item 0.3 do plano de remediação.
> Objetivo: parar de usar `Trusted_Connection=yes` (conta de domínio com dbo) e passar
> tudo por `sql_monitoring` (SQL Auth, least-privilege) — cumprir Regra de Ouro #2.
> **Modo Consultor: owner executa. A AI NÃO liga a DB nem executa GRANTs.**

## ⚠️ ATUALIZAÇÃO 2026-07-02 (pós-verificação) — metade já existe

Grep no V1 revelou infraestrutura que NÃO deve ser reinventada. O 0.3 passa de
"construir GRANTs" para "reconciliar existente + fechar gaps específicos do V3.3":

**Já existe e foi APLICADO (logs 2025-12-26 em `V1/logs/grants/`):**
- `V1/database/GRANTS_SQL_MONITORING_SEGUROS.sql` v1.3 (2026-04-30): `VIEW SERVER STATE`,
  `CONNECT ANY DATABASE`, `VIEW DATABASE STATE` por-BD + `DENY SELECT ON SCHEMA::dbo`
  (garantia zero-dados-de-negócio — excelente para banking) + msdb: backupset,
  backupmediafamily, restorehistory, sysjobs, sysjobhistory, sysjobactivity, suspect_pages.
- `V1/database/CONFIGURAR_PERMISSOES_SQL_MONITORING.sql`: `VIEW ANY DEFINITION` + role
  `MonitoringRole`.
- `V1/database/CREATE_PROCEDURE_COLLECT_ERRORLOG.sql`: **wrapper proc que encapsula
  `xp_readerrorlog`** (a "opção A" do caveat — já implementada para o collector V1).
- `V1/scripts/apply_grants_all_servers.py`: orquestrador (ServerManager) que aplica a
  todos os servidores PRD. **NOTA: aplica um subset msdb-only inline (`GRANTS_MSDB_SQL`),
  NÃO o `SEGUROS.sql` completo** — divergência a reconciliar.
- `api/connection_pool.py`: plumbing SQL-auth completa — `_build_connection_string_sql_auth`
  (505), `_resolve_credentials` (400), cache de `servers.json` com decrypt Fernet/DPAPI
  (292-398). `IntelligenceConnectionPool` já ramifica em `use_windows_auth` (695).

**Gaps REAIS específicos do V3.3 (a confirmar com a query do PASSO 1):**
1. **msdb `sysjobsteps` / `sysjobschedules` / `sysschedules`** — usados por
   `modules/monitoring/backup_pattern_analysis.py:304,328,329`, mas NÃO estão na lista de
   GRANT do SEGUROS.sql (só sysjobs/sysjobhistory/sysjobactivity). Provável gap.
2. **V3.3 chama `xp_readerrorlog` DIRETAMENTE** (`watcherdb_main.py:2987`,
   `watcherdb_alwayson_check.py:708`) em vez de usar o wrapper proc do collector. Sob
   `sql_monitoring` isto fica bloqueado. Escolha: (A) apontar V3.3 ao wrapper proc
   existente, (B) grant, (C) degradação graciosa (já há fallback em :3045).
3. **Divergência canonical vs aplicado**: o `apply_grants_all_servers.py` aplicou o subset
   msdb-only — confirmar se `VIEW ANY DEFINITION` e `VIEW DATABASE STATE` per-DB do
   SEGUROS.sql chegaram mesmo a todos os servidores, ou só o msdb.

O resto do doc (query de levantamento, flip de código) mantém-se válido — a query do
PASSO 1 é agora a ferramenta de *verificação de gaps*, não de descoberta do zero. O PASSO 2
abaixo foi REESCRITO para referenciar o existente.

## Porque é uma mini-wave (não um commit)

O flip de código é trivial (`intelligence_use_windows_auth=False` + `_build_connection_string`
respeitar a flag). O que NÃO é trivial: garantir que `sql_monitoring` tem as permissões
certas nos ~95 servidores ANTES do flip, senão o produto fica cego. Ordem obrigatória:

1. **Levantamento** (query read-only, este doc) — o que falta a `sql_monitoring` hoje.
2. **GRANTs** (owner executa como sysadmin em cada servidor — NÃO a AI).
3. **Flip de código** (só depois de 1-2 verdes).
4. **Validação** (portal contra 2-3 servidores piloto antes de generalizar).

Handoff obrigatório: `watcherdb-v1-intel-specialist` (BD partilhada, direito de veto) +
`watcherdb-deploy-architect` (packaging/service account + o caso xp_readerrorlog).

## Inventário de necessidades elevadas (confirmado no código, 2026-07-02)

Nenhuma operação de mutação/RCE. Tudo leitura:

| Necessidade | Onde é usada (evidência) | GRANT alvo |
|---|---|---|
| `VIEW SERVER STATE` | `dm_os_*` (cpu_analysis.py:124-322), `dm_exec_*` (_diagnostics_legacy.py:117-120), `dm_io_virtual_file_stats` (cpu_analysis.py:311, performance.py:121), `dm_hadr_*` (backup_analysis.py:97, monitoring.py:786), `dm_db_*` (todos os diagnósticos) | server-level |
| `EXEC xp_readerrorlog` / `sp_readerrorlog` | `watcherdb_main.py:2987-2992`, `watcherdb_alwayson_check.py:708-848` | master (ver caveat) |
| Leitura `msdb` (backupset, sysjobs, sysjobsteps, sysjobschedules, sysschedules) | `backup_analysis.py:491-503`, `backup_pattern_analysis.py:214-329` | `db_datareader` em msdb + `SQLAgentReaderRole` |
| `CONNECT` + leitura por-BD (contexto `USE [db]`) | `_diagnostics_legacy.py:1051`, auto-discovery `sys.databases` | `db_datareader` por BD (ou CONNECT + VIEW DATABASE STATE) |
| `VIEW ANY DEFINITION` (metadata cross-object) | `dm_sql_referenced_entities` (_diagnostics_legacy.py:1277,2208) | server-level |

**Caveat xp_readerrorlog (para deploy-architect decidir):** é um extended proc de sistema
em `master.sys`; não se concede `EXECUTE` a um login não-sysadmin de forma direta e limpa.
Opções, por ordem de preferência least-privilege:
- (A) **Wrapper proc assinado por certificado** em master que faz o `EXEC xp_readerrorlog`,
  com o certificado a conceder a permissão — `sql_monitoring` só recebe EXECUTE no wrapper.
  Mais trabalho, mas mantém least-privilege puro.
- (B) Conceder ao login a role fixa mínima que permita (historicamente `securityadmin`
  dá acesso, mas é privilégio a mais — evitar).
- (C) Degradação graciosa: se `sql_monitoring` não puder ler o errorlog, o endpoint de
  SQL Errors abstém-se (já há timeout/fallback em `watcherdb_main.py:3045`). Aceitável
  como fase 1 se A for adiado — mas documenta a perda de feature.

---

## PASSO 1 — Query de levantamento (READ-ONLY)

**Como correr:** ligar a CADA servidor-alvo **como `sql_monitoring`** (SQL Auth, a
identidade real de runtime — não como o teu domain user, senão o teste é falso). SSMS →
nova ligação SQL Auth com as credenciais de `sql_monitoring` → correr contra `master`.
Não usa `EXECUTE AS` (proibido). Só funções read-only de permissão + probes TRY/CATCH.

```sql
-- =====================================================================
-- LEVANTAMENTO de permissões de sql_monitoring (READ-ONLY)
-- Correr LIGADO COMO sql_monitoring, contexto master. Não muta nada.
-- Revisão geral V3.3 — mini-wave 0.3, 2026-07-02
-- =====================================================================
SET NOCOUNT ON;

SELECT
    @@SERVERNAME                                              AS server_name,
    SUSER_SNAME()                                             AS connected_as,
    CAST(SERVERPROPERTY('ProductMajorVersion') AS INT)       AS sql_major_version,
    IS_SRVROLEMEMBER('sysadmin')                             AS is_sysadmin,      -- esperado: 0
    HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE')       AS has_view_server_state,
    HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW ANY DEFINITION')     AS has_view_any_definition,
    HAS_PERMS_BY_NAME(NULL, NULL, 'CONNECT SQL')             AS has_connect_sql;

-- Acesso a msdb (backup + agent history)
BEGIN TRY
    DECLARE @msdb_ok INT;
    SELECT TOP 1 @msdb_ok = 1 FROM msdb.dbo.backupset;
    SELECT 'msdb.dbo.backupset' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'msdb.dbo.backupset' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;

BEGIN TRY
    DECLARE @jobs_ok INT;
    SELECT TOP 1 @jobs_ok = 1 FROM msdb.dbo.sysjobs;
    SELECT 'msdb.dbo.sysjobs' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'msdb.dbo.sysjobs' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;

-- DMVs server-scoped (dependem de VIEW SERVER STATE)
BEGIN TRY
    DECLARE @dmv1 INT; SELECT TOP 1 @dmv1 = 1 FROM sys.dm_os_sys_info;
    SELECT 'sys.dm_os_sys_info' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'sys.dm_os_sys_info' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;

BEGIN TRY
    DECLARE @dmv2 INT; SELECT TOP 1 @dmv2 = 1 FROM sys.dm_exec_sessions;
    SELECT 'sys.dm_exec_sessions' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'sys.dm_exec_sessions' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;

BEGIN TRY
    DECLARE @dmv3 INT; SELECT TOP 1 @dmv3 = 1 FROM sys.dm_io_virtual_file_stats(NULL, NULL);
    SELECT 'sys.dm_io_virtual_file_stats' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'sys.dm_io_virtual_file_stats' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;

-- AlwaysOn (só relevante em instâncias com AG)
BEGIN TRY
    DECLARE @hadr INT; SELECT TOP 1 @hadr = 1 FROM sys.dm_hadr_availability_replica_states;
    SELECT 'sys.dm_hadr_availability_replica_states' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'sys.dm_hadr_availability_replica_states' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;

-- Error log (o caso espinhoso)
BEGIN TRY
    CREATE TABLE #el (LogDate DATETIME, ProcessInfo NVARCHAR(64), LogText NVARCHAR(MAX));
    INSERT INTO #el EXEC xp_readerrorlog 0, 1, NULL, NULL;
    DROP TABLE #el;
    SELECT 'xp_readerrorlog' AS probe, 'OK' AS status, NULL AS error_message;
END TRY
BEGIN CATCH
    IF OBJECT_ID('tempdb..#el') IS NOT NULL DROP TABLE #el;
    SELECT 'xp_readerrorlog' AS probe, 'BLOCKED' AS status, ERROR_MESSAGE() AS error_message;
END CATCH;
```

**Interpretação:** onde `status = BLOCKED`, o GRANT correspondente (passo 2) é necessário.
Registar os resultados por servidor (basta um servidor representativo de cada topologia:
1 standalone, 1 FCI, 1 com AlwaysOn) para dimensionar o esforço.

---

## PASSO 2 — REESCRITO: reconciliar existente + fechar 3 gaps (NÃO reinventar)

**Não escrever GRANTs do zero.** O canonical é `V1/database/GRANTS_SQL_MONITORING_SEGUROS.sql`
(já aplicado 2025-12-26). O trabalho é: (a) confirmar cobertura real via PASSO 1, (b) fechar
os 3 gaps do V3.3. Owner executa como sysadmin; handoff V1 obrigatório (BD partilhada).

**Gap 1 — msdb job steps/schedules.** Acrescentar ao SEGUROS.sql (PARTE 3, junto aos
outros GRANT de msdb) — é aditivo e alinhado com o padrão existente:

```sql
-- Gap V3.3 (backup_pattern_analysis.py:304,328,329): inferência de schedule
USE [msdb];
GRANT SELECT ON dbo.sysjobsteps      TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobschedules  TO [sql_monitoring];
GRANT SELECT ON dbo.sysschedules     TO [sql_monitoring];
```

**Gap 2 — xp_readerrorlog (decisão, não código-já).** O wrapper proc já existe para o
collector (`V1/database/CREATE_PROCEDURE_COLLECT_ERRORLOG.sql`). O problema é que o V3.3
chama `xp_readerrorlog` DIRETO. Opções (deploy-architect decide):
- (A) **Apontar o V3.3 ao wrapper proc** (reutiliza o que já existe; muda
  `watcherdb_main.py:2987` e `watcherdb_alwayson_check.py:708` de `EXEC xp_readerrorlog`
  para `EXEC <wrapper>`). Least-privilege puro, reaproveita infra. **Recomendado.**
- (B) GRANT EXECUTE direto no XP (requer assinatura por certificado à mesma) — sem ganho vs A.
- (C) Degradação graciosa: SQL Errors abstém-se sob `sql_monitoring` (já há fallback em
  `watcherdb_main.py:3045`). Aceitável como fase 1 se A for adiado; documenta perda.

**Gap 3 — reconciliação canonical vs aplicado.** O `apply_grants_all_servers.py` aplicou um
subset **msdb-only** inline, não o `SEGUROS.sql` completo. Confirmar (via PASSO 1) se
`VIEW ANY DEFINITION` e `VIEW DATABASE STATE` per-DB chegaram a todos os servidores, ou só
o msdb. Se só msdb: re-correr o orquestrador apontando ao `SEGUROS.sql` completo (+ Gap 1)
em vez do subset inline — ou alinhar o inline com o canonical (eliminar a divergência).

**Login existe?** Sim (grants aplicados em Dec 2025 pressupõem-no) — mas a password de
`sql_monitoring` tem de estar no `servers.json`/cofre para o flip (PASSO 3). Confirmar com
deploy-architect onde vive hoje (o `connection_pool` já decripta Fernet/DPAPI).

---

## PASSO 3 — Flip de código (só após 1-2 verdes)

- `watcherdb/core/settings.py:48`: `intelligence_use_windows_auth: bool = False`.
- `api/connection_pool.py:458` `_build_connection_string`: passar a respeitar a flag —
  se `use_windows_auth` False, usar `_build_connection_string_sql_auth` (linha 490, hoje
  nunca chamado); Trusted só com flag `dev` explícita.
- Purgar o docstring que documenta a dívida (linhas 461-477) após o flip.
- Aplicar o mesmo aos ~12 sítios réplica listados na revisão de arquitetura (C1):
  `jobs.py:89`, `intelligence_kpis.py:522`, `models/server.py:18,36`, `alembic/env.py:43`, etc.

## PASSO 4 — Validação piloto

Portal contra 2-3 servidores (1 standalone, 1 FCI, 1 AlwaysOn) sob `sql_monitoring`.
Confirmar que os módulos Performance, Backup, AlwaysOn e SQL Errors funcionam ou degradam
graciosamente. Só depois generalizar aos restantes.

---

## Ordem e handoff

1. Owner corre PASSO 1 nos 3 servidores-piloto → regista o que está BLOCKED.
2. Handoff a `watcherdb-v1-intel-specialist` + `watcherdb-deploy-architect` com os
   resultados + a decisão xp_readerrorlog (A/B/C).
3. Owner corre PASSO 2 (GRANTs) nos piloto.
4. Re-correr PASSO 1 → tudo OK (exceto xp_readerrorlog se ficar em degradação C).
5. PASSO 3 (flip código) numa branch, validação piloto (PASSO 4), depois rollout.

Este é o item que desbloqueia a venda banking — mas é também o de maior risco operacional.
Vale a mini-wave dedicada com os dois specialists de infra, não um commit apressado.
