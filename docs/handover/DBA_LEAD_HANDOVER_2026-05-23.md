# Handover DBA Lead -- 4 items para accao

**Data:** 2026-05-23
**Autor:** Salomao Netto (founder WatcherDB)
**Audience:** DBA Lead -- Banking client production environment
**Source:** Investigacao iterativa Waves M-R no monitoring de 41 PRD servers (2026-05-21 a 2026-05-23)

---

## Sumario executivo

5 items identificados durante sprint de monitoring fixes. 2 sao **bloqueios para WatcherDB** (precisam decisao DBA Lead para destrancar). 3 sao **achados operacionais** (silent risks no ambiente que o monitoring revelou).

| # | Item | Tipo | Severidade | Esforco |
|---|---|---|---|---|
| 1 | xp_readerrorlog EXECUTE permission | Bloqueio WatcherDB | Medio | 1h analise + decisao |
| 2 | no_checksum top-5 servers config | Achado | Medio | 5min por server (sp_configure) |
| 3 | CAGENPRD07_I07 TSM Exit Code 255 | Achado | **Alto -- RPO em risco** | Investigacao TSM team |
| 4 | FULL no_checksum 1,064 entries | Achado | **Alto -- silent corruption risk** | Audit + remediation per server |
| 5 | msdb bloat em SQLIJSPRD03 + SQLHDSQLT* | Operacional/perf | Baixo-Medio | sp_purge_jobhistory por instance |

---

## Item 1 -- xp_readerrorlog EXECUTE permission

**Contexto:** Wave P (2026-05-22) tentou completar `collect_errorlog` collector para capturar
SQL Server error log events em 41 PRD instances. Bloqueado por permissao.

**Problema tecnico:**
- `sql_monitoring` account (SQL Login, SELECT-only por design CLAUDE.md) NAO tem
  EXECUTE em `sys.xp_readerrorlog`
- Sem essa proc, nao conseguimos ler error log via SELECT
- Tentativas alternativas (ring buffer, ERRORLOG file directo) tambem requerem
  permissoes elevadas que violam o principio do least privilege do design

**Impacto:**
- Errorlog KPI fica DESACTIVADO em PRD ate decisao
- Perda de visibilidade de eventos SQL Server (Error 18056, 17310, 9001, deadlock graphs, etc.)
- Compensado parcialmente por outros KPIs (deadlocks via Extended Events, backup
  failures via msdb, etc.) mas erro raw fica blackbox

**Caminhos possiveis (escolha do DBA Lead):**

**(A) GRANT EXECUTE on xp_readerrorlog to sql_monitoring** (Recomendado)
- Risk: minimal. xp_readerrorlog e read-only, nao expoe credentials.
- Pro: solucao limpa, mantem one-collector-one-purpose pattern.
- Con: quebra estritamente o "SELECT only" rule mas pratica industria considera
  xp_readerrorlog read-only.

**(B) SQL Agent job workaround:** job dedicado lendo errorlog e escrevendo
para tabela acessivel a sql_monitoring. Job corre como SQL Agent service account.
- Pro: mantem sql_monitoring SELECT-only.
- Con: 1 job a manter por instance (41 jobs), latencia +5min, complexidade.

**(C) Ring buffer SQL DMV (`sys.dm_os_ring_buffers`):** captura subset de eventos
sem precisar xp_readerrorlog.
- Pro: zero permissoes adicionais, ja temos VIEW grant.
- Con: cobertura parcial -- nao todos os eventos relevantes estao no ring buffer.
  Tipicamente 60-70% do error log capturado.

**Decisao pedida ao DBA Lead:** escolher (A), (B), ou (C). Recomendamos (A).
Se nao for possivel (A), recomendamos (C) como compromise pragmatico.

---

## Item 2 -- no_checksum top-5 servers (sp_configure default OFF)

**Contexto:** Wave R (2026-05-22) investigacao do KPI Backup No-Checksum revelou
**148,031 entries de backups sem WITH CHECKSUM** em 7 dias PRD.

**Causa raiz:** SQL Server default e' `backup checksum default = 0` (OFF). Top-5
servers contribuem ~70% do volume porque tem este default mantido.

**Top-5 ofensores:**

| Instance | no_checksum entries | distinct DBs | % total |
|---|---|---|---|
| SQLHDSPRD302_I01 | 74,972 | 116 | **50.6%** |
| SQLMDMPRD03_I01 | 12,987 | 31 | 8.8% |
| SQLRPAPRD01_I01 | 8,166 | 16 | 5.5% |
| SQLMDMPRD04_I01 | 6,607 | 31 | 4.5% |
| SQLMDMPRD02_I01 | 6,432 | 14 | 4.3% |

**Fix por server (DBA executa):**

```sql
-- Verificar default actual
EXEC sp_configure 'backup checksum default';
GO

-- Activar (1 = ON)
EXEC sp_configure 'backup checksum default', 1;
RECONFIGURE;
GO
```

**Nota:** mudanca aplica-se aos PROXIMOS backups (nao re-escreve historico). Backups
existentes em msdb continuam marked sem checksum, mas paramos de adicionar mais.

**Verificacao:** apos fix nos top-5, esperar 7 dias e re-correr query no_checksum por
instance. Esperado: drop ~70% no volume total.

---

## Item 3 -- CAGENPRD07_I07 TSM (IBM Spectrum Protect) Exit Code 255

**Contexto:** Wave Q (2026-05-22) investigacao filtros AG SECONDARY identificou que
**CAGENPRD07_I07** tem padrao consistente de TSM (IBM Spectrum Protect / Tivoli)
backup integration **a falhar ha 4+ dias consecutivos**.

**Evidencia:**
- Job: `CSE07 Logs Backup` (subsystem CmdExec)
- Command: `C:\ClusterStorage\I07_DATA0\TSMCONFIG\CAGENCSE07_log_backup.cmd`
- Exit Code 255 (signature TSM agent error)
- 10 occurrences em 7 dias visiveis em msdb.dbo.sysjobhistory
- Status: log backups via TSM NAO estao a completar com sucesso

**Impacto critico:**
- RPO (Recovery Point Objective) comprometido para esta instance
- Em caso de incidente, perda de transacoes desde ultimo backup TSM SUCCESSFUL
- AG SECONDARY no nodo CSE07 nao protegido (mesmo padrao deve verificar em outros nos CSE)

**Accao recomendada:**
1. **Imediato (hoje):** TSM team investigar Exit 255 em CAGENPRD07. Verificar:
   - TSM agent service status no servidor
   - tdpsql.exe binary integrity
   - TSM server connectivity + authentication
   - Disk space em TSM staging area
   - dsm.opt / dsm.sys configuration

2. **Curto prazo (esta semana):** validar TODOS os outros 6 nos CAGENPRDxx_Ixx para o
   mesmo padrao. Possivel issue partilhada cross-cluster.

3. **Mitigation (ate fix):** activar backup nativo SQL Server complementar (BACKUP LOG
   TO DISK) com retencao curta. Garante recovery option enquanto TSM nao fixa.

**Query para audit cross-cluster:**

```sql
-- Run em WatcherDB_Intelligence (sql_monitoring SELECT only)
SELECT Instance, Job_Name, COUNT(*) AS occurrences,
       MIN(Run_Datetime) AS first, MAX(Run_Datetime) AS last
FROM KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE_PRD
WHERE Failure_Source = 'sysjobhistory'
  AND Message LIKE '%Process Exit Code 255%'
GROUP BY Instance, Job_Name
ORDER BY occurrences DESC;
```

---

## Item 4 -- FULL backups sem checksum (silent corruption risk REAL)

**Contexto:** Wave R (2026-05-22) introduziu `Backup_Type_Classified` column no
KPI Backup No-Checksum, permitindo split por tipo de backup. Resultado revelou
que dentro dos 148k entries no_checksum:

| Tipo | Count | % | Risco |
|---|---|---|---|
| LOG | 143,456 | 97.0% | Baixo -- decisao consciente DBA (perf trade-off) |
| DIFF | 3,403 | 2.3% | Medio |
| **FULL** | **1,064** | **0.7%** | **ALTO -- silent corruption risk** |

**Porque FULL e' critico:**
- FULL backup e' a base da chain de recovery -- corruption silenciosa aqui invalida
  toda a chain DIFF + LOG subsequente
- `RESTORE VERIFYONLY` sem checksum NAO consegue detectar corruption em paginas
- Bit-rot em FULL backup file pode estar la ha semanas/meses sem ninguem saber
- Em caso de incidente DR, restore pode falhar com message tipo
  "Could not redo log record" -- impossivel de recuperar

**Audit query para enriquecer este handover:**

```sql
SELECT TOP 50
    Instance, [Database], COUNT(*) AS no_checksum_full_count,
    MIN(Run_Datetime) AS oldest_unprotected,
    MAX(Run_Datetime) AS newest_unprotected
FROM KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE_PRD
WHERE Failure_Source = 'no_checksum'
  AND Backup_Type_Classified = 'FULL'
GROUP BY Instance, [Database]
ORDER BY no_checksum_full_count DESC;
```

**Accao recomendada DBA Lead:**

1. **Run query acima** -- lista as instance+DB combinations afectadas (top contribuidores)
2. **Cross-reference com Item 2** -- maior parte coincide com top-5 sp_configure issue.
   Fix de Item 2 cobre estes automaticamente nos PROXIMOS FULL backups.
3. **Para FULL backups existentes (ja sem checksum):** correr `RESTORE VERIFYONLY` em
   um subset para sample-check. Se passar, considerar acceptable risk. Se falhar,
   considerar re-FULL backup com WITH CHECKSUM imediato.

---

## Item 5 -- msdb bloat (sysjobhistory + backupset) em SQLIJSPRD03 + SQLHDSQLT*

**Contexto:** Investigacao Wave R+5 SQL timeouts (2026-05-23) -- collector backup_failures
hit 60s timeout em **SQLIJSPRD03** durante coleta ciclo Wave R. Outros KPIs (backups,
processes) funcionaram normalmente para estes servers. Confirmado: timeouts sao
INTERMITTENTES, nao chronic.

**Causa raiz:** `msdb.dbo.sysjobhistory` + `msdb.dbo.backupset` nestes instances tem
historico acumulado grande sem cleanup. A query Wave R varre full table com DATEADD
computado per row -> tempo de scan escala com tamanho. Quando msdb tem anos de jobs/backups
sem purge, ultrapassa 60s budget.

**Instances candidatas:**
- **SQLIJSPRD03** (PRD) -- confirmed timeout Wave R 2026-05-22
- **SQLHDSQLT023** (QA) -- mencionado em defers
- **SQLHDSQLT103\SQLIJSQLT03** (QA) -- mencionado em defers

**Accao recomendada:**

1. **Audit msdb size por instance:**

```sql
-- Run em cada instance candidata (NAO em WatcherDB_Intelligence)
USE msdb;
SELECT
    'sysjobhistory' AS table_name, COUNT(*) AS row_count,
    MIN(run_date) AS oldest_date, MAX(run_date) AS newest_date
FROM dbo.sysjobhistory
UNION ALL
SELECT
    'backupset', COUNT(*),
    CONVERT(INT, CONVERT(VARCHAR, MIN(backup_start_date), 112)),
    CONVERT(INT, CONVERT(VARCHAR, MAX(backup_start_date), 112))
FROM dbo.backupset;
```

Esperado: sysjobhistory com >250k rows OU backupset com historia >180 dias indicam
candidato para purge.

2. **Purge job history (retencao 90 dias):**

```sql
-- Run em cada instance afectada
DECLARE @cutoff DATETIME = DATEADD(DAY, -90, GETDATE());
EXEC msdb.dbo.sp_purge_jobhistory @oldest_date = @cutoff;
GO

DECLARE @cutoff DATETIME = DATEADD(DAY, -180, GETDATE());
EXEC msdb.dbo.sp_delete_backuphistory @oldest_date = @cutoff;
GO
```

3. **Scheduled cleanup (preventivo):** criar SQL Agent job mensal em cada instance que
   corre os 2 procs acima. Mantem msdb saudavel sem intervencao manual.

**Impacto pos-fix:**
- Collector backup_failures ja nao tem timeouts em ciclos normais
- msdb size reduz ~70-80% (depende de quanto historia tem)
- Backup performance melhora (msdb queries durante operacoes nativas SQL Server tambem)

---

## Items relacionados (defers pos-Wave R, nao bloqueante)

- **Env=NULL** na view `KPI_MSSQL_BACKUP_EXEC_FAILURES_STG` (cosmetic, base_collector bug)
- **STORE backup_failures perf** -- ~30min SWAP em PRD (148k rows). QA tambem afectado
  (~8min). Defer perf optimization.
- **SettingWithCopyWarning** em pandas transform() (cosmetic, pre-existing)
- **Bulk Re-run UI** (Wave N) para re-correr collectors em batch
- **server_manager.py:138 decrypt gap** para monitored_servers passwords

---

**Contacto para esclarecimentos:** Salomao Netto.

**Documentos relacionados:**
- WatcherDB_V3.3 commit 8fd59a7 (Wave R complete -- adicionou typeChart por tipo)
- WatcherDB_V3.3 commit 67f2e52 (Wave Q -- AG SECONDARY filter)
- WatcherDB Intelligence collector schema doc: `WATCHERDB INTELLIGENCE V1/database/CREATE_BACKUP_HEALTH_STG_TABLES.sql`
