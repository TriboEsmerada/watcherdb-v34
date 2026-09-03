# 🚀 DEPLOYMENT ÚNICO - SCRIPT COMPLETO

**Projeto:** WatcherDB Intelligence V2
**Objetivo:** Deploy completo em 1 único script
**Tempo estimado:** 5-10 minutos

---

## ⚡ DEPLOYMENT EM 1 ÚNICO COMANDO

### Passo Único: Executar Script Master

```sql
-- Abra SQL Server Management Studio (SSMS)
-- Conecte no servidor SQL Server
-- Abra o arquivo e execute:

:r C:\path\to\database\SQLSERVER_KPI_DEPLOY_COMPLETE.sql
```

**Pronto!** O script vai executar TUDO automaticamente:

1. ✅ Criar database (se não existir)
2. ✅ Criar filegroups
3. ✅ Criar 18 tabelas
4. ✅ Criar 23 views
5. ✅ Criar 12 procedures
6. ✅ Criar 2 SQL Agent Jobs
7. ✅ Executar teste de coleta
8. ✅ Validar deployment

---

## 📋 O QUE O SCRIPT FAZ

### ETAPA 1: Database e Filegroups

- Cria database `WatcherDB_Intelligence_V2` (se não existir)
- Cria filegroups dedicados:
  - `FG_KPI_DATA` - Para tabelas STG
  - `FG_KPI_HIST` - Para tabelas HIST

### ETAPA 2: Tabelas (18 total)

**Staging Tables (11):**
```
KPI_MSSQL_ALWAYSON_STATUS_STG
KPI_MSSQL_BACKUPS_STG
KPI_MSSQL_BLOCKED_SESSIONS_STG
KPI_MSSQL_BLOCKED_USERS_STG
KPI_MSSQL_DB_AVAILABILITY_STG
KPI_MSSQL_DISK_USAGE_STG
KPI_MSSQL_FG_USAGE_STG
KPI_MSSQL_INST_AVAILABILITY_STG
KPI_MSSQL_LONG_LOCKS_STG
KPI_MSSQL_PROCESSES_STG
KPI_MSSQL_TLOG_USAGE_STG
```

**Historical Tables (3):**
```
KPI_MSSQL_DB_AVAILABILITY_HIST
KPI_MSSQL_DISK_USAGE_HIST
KPI_MSSQL_TLOG_USAGE_HIST
```

**Configuration Tables (2):**
```
KPI_MSSQL_THRESHOLDS
KPI_MSSQL_THRESHOLDS_V2
```

**CMDB Tables (2):**
```
CMDB_MSSQL_DATABASES
CMDB_MSSQL_DATABASES_HIST
```

### ETAPA 3: Views (23 total)

**KPI Views (22):**
- 11 AGG Views (agregadas)
- 11 DET Views (detalhadas)

**CMDB Views (1):**
- CMDB_MSSQL_DATABASES_VW

### ETAPA 4: Procedures (12 total)

**Procedures de Coleta (11):**
```
usp_Collect_AlwaysOn_Status
usp_Collect_Backups
usp_Collect_Blocked_Sessions
usp_Collect_Blocked_Users
usp_Collect_DB_Availability
usp_Collect_Disk_Usage
usp_Collect_Filegroup_Usage
usp_Collect_Instance_Availability
usp_Collect_Long_Locks
usp_Collect_Processes
usp_Collect_TLog_Usage
```

**Procedure Master (1):**
```
usp_Collect_All_KPIs - Executa todas as coletas
```

### ETAPA 5: SQL Agent Jobs (2 total)

**Job 1: Coleta de KPIs**
- Nome: `WatcherDB_Collect_KPIs`
- Frequência: A cada 5 minutos
- Ação: Executa `usp_Collect_All_KPIs`

**Job 2: Limpeza de Histórico**
- Nome: `WatcherDB_Purge_History`
- Frequência: Diária à meia-noite
- Ação: Remove dados > 365 dias

### ETAPA 6: Configuração Inicial

- Popula tabela `KPI_MSSQL_INST_ENVS` com servidor local
- Executa teste de coleta

### ETAPA 7: Validação

- Verifica se 19 tabelas foram criadas
- Verifica se 23 views foram criadas
- Verifica se 12 procedures foram criadas
- Verifica se 2 jobs foram criados
- Verifica se dados foram coletados

---

## ✅ VALIDAÇÃO PÓS-DEPLOYMENT

Após executar o script, valide:

```sql
-- 1. Verificar objetos criados
SELECT 'Tabelas', COUNT(*) FROM sys.tables WHERE name LIKE 'KPI_MSSQL%'
UNION ALL
SELECT 'Views', COUNT(*) FROM sys.views WHERE name LIKE 'KPI_MSSQL%'
UNION ALL
SELECT 'Procedures', COUNT(*) FROM sys.procedures WHERE name LIKE 'usp_Collect%';

-- Deve retornar:
-- Tabelas      19
-- Views        23
-- Procedures   12

-- 2. Verificar jobs criados
SELECT name, enabled
FROM msdb.dbo.sysjobs
WHERE name LIKE 'WatcherDB%';

-- Deve retornar:
-- WatcherDB_Collect_KPIs    1 (enabled)
-- WatcherDB_Purge_History   1 (enabled)

-- 3. Verificar dados coletados
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;

-- Deve retornar dados do servidor local
```

---

## 🧪 TESTES

### Teste 1: Executar coleta manual

```sql
EXEC dbo.usp_Collect_All_KPIs @Debug = 1;
```

**Resultado esperado:**
```
============================================================================
WATCHERDB INTELLIGENCE V2 - COLETA COMPLETA DE KPIs
============================================================================
...
Sucesso: 11 / 11
Erros: 0
Duração: X segundos
```

### Teste 2: Verificar dados nas views

```sql
-- Disk Usage
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_DET_VIEW;

-- Instance Availability
SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;

-- Transaction Log Usage
SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW;
```

### Teste 3: Executar job manualmente

```sql
EXEC msdb.dbo.sp_start_job @job_name = 'WatcherDB_Collect_KPIs';

-- Verificar resultado
EXEC msdb.dbo.sp_help_job @job_name = 'WatcherDB_Collect_KPIs';
```

---

## 🔧 TROUBLESHOOTING

### Erro: "Cannot open database 'WatcherDB_Intelligence_V2'"

**Causa:** Database não foi criado
**Solução:** O script cria automaticamente. Se persistir, crie manualmente:
```sql
CREATE DATABASE [WatcherDB_Intelligence_V2];
```

### Erro: "SQL Server Agent not running"

**Causa:** SQL Agent não está iniciado
**Solução:**
```powershell
# Windows (Admin):
NET START SQLSERVERAGENT

# Ou via SSMS:
# SQL Server Agent → Right-click → Start
```

### Erro: Procedures falham no teste de coleta

**Causa:** Permissões insuficientes
**Solução:**
```sql
-- Verificar usuário
SELECT USER_NAME();

-- Dar permissões (como SA)
ALTER ROLE db_owner ADD MEMBER [seu_usuario];
```

### Jobs não executam automaticamente

**Causa:** Schedule não configurado ou SQL Agent parado
**Solução:**
```sql
-- Verificar schedule
SELECT j.name, s.name AS schedule_name, s.enabled
FROM msdb.dbo.sysjobs j
INNER JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id
INNER JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id
WHERE j.name LIKE 'WatcherDB%';

-- Se schedule disabled, habilitar:
EXEC msdb.dbo.sp_update_schedule
    @name = 'Every_5_Minutes',
    @enabled = 1;
```

---

## 📊 MONITORAMENTO

### Ver histórico de execuções dos jobs

```sql
SELECT TOP 20
    j.name AS Job_Name,
    CONVERT(VARCHAR(23), CAST(CAST(h.run_date AS VARCHAR(8)) + ' ' +
        STUFF(STUFF(RIGHT('000000' + CAST(h.run_time AS VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':')
        AS DATETIME2), 121) AS Run_DateTime,
    CASE h.run_status
        WHEN 0 THEN 'Failed'
        WHEN 1 THEN 'Succeeded'
        WHEN 2 THEN 'Retry'
        WHEN 3 THEN 'Canceled'
    END AS Status,
    h.run_duration AS Duration_Sec,
    LEFT(h.message, 100) AS Message
FROM msdb.dbo.sysjobs j
INNER JOIN msdb.dbo.sysjobhistory h ON j.job_id = h.job_id
WHERE j.name LIKE 'WatcherDB%'
  AND h.step_id = 0
ORDER BY h.run_date DESC, h.run_time DESC;
```

### Ver dados coletados recentemente

```sql
-- Últimas coletas
SELECT
    'Disk Usage' AS KPI,
    COUNT(*) AS Rows,
    MAX(Update_TS) AS Last_Update
FROM dbo.KPI_MSSQL_DISK_USAGE_STG
UNION ALL
SELECT
    'Instance Availability',
    COUNT(*),
    MAX(Update_TS)
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG
UNION ALL
SELECT
    'TLog Usage',
    COUNT(*),
    MAX(Update_TS)
FROM dbo.KPI_MSSQL_TLOG_USAGE_STG
UNION ALL
SELECT
    'DB Availability',
    COUNT(*),
    MAX(Update_TS)
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG;
```

---

## 🎯 PRÓXIMOS PASSOS (PÓS-DEPLOYMENT)

### 1. Adicionar mais servidores SQL Server

```sql
-- Adicionar servidores remotos ao monitoramento
INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env, Description)
VALUES
    ('SQLHDSPRD213\I01', 'PROD', 'SQL Server Produção'),
    ('SQLHDSUATXXX\I01', 'UAT', 'SQL Server UAT'),
    ('SQLHDSDEVXXX\I01', 'DEV', 'SQL Server Desenvolvimento');
```

**Nota:** Para coletar de servidores remotos, modifique os procedures para usar Linked Server ou OPENROWSET.

### 2. Configurar alertas

```sql
-- Criar alerta para disk usage crítico
-- (Exemplo - adapte conforme necessário)
EXEC msdb.dbo.sp_add_alert
    @name = 'Disk_Usage_Critical',
    @message_id = 0,
    @severity = 0,
    @enabled = 1,
    @delay_between_responses = 900; -- 15 min
```

### 3. Integrar com Python API

Modifique `watcherdb_main.py` para consultar SQL Server ao invés de Oracle:

```python
# Antes (Oracle):
import cx_Oracle
conn = cx_Oracle.connect(...)

# Depois (SQL Server):
import pyodbc
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=WatcherDB_Intelligence_V2;"
    "Trusted_Connection=yes;"
)
```

### 4. Criar dashboard

Use as views criadas para alimentar dashboards:
- Grafana
- Power BI
- Web dashboard customizado

---

## 📁 ARQUIVOS RELACIONADOS

| Arquivo | Descrição |
|---------|-----------|
| **SQLSERVER_KPI_DEPLOY_COMPLETE.sql** | ⭐ **SCRIPT ÚNICO** - Execute este |
| SQLSERVER_KPI_REPLICATION_COMPLETE.sql | Apenas tabelas (incluído no script único) |
| SQLSERVER_KPI_VIEWS.sql | Apenas views (incluído no script único) |
| SQLSERVER_KPI_COLLECTION_PROCEDURES.sql | Apenas procedures (incluído no script único) |
| SQLSERVER_KPI_AGENT_JOBS.sql | Apenas jobs (incluído no script único) |
| README_REPLICACAO_ORACLE_SQLSERVER.md | Documentação completa |
| QUICK_REFERENCE_DEPLOYMENT.md | Comandos de referência rápida |

---

## 🏁 RESUMO EXECUTIVO

### O que foi deployado:

✅ **1 Database**
✅ **2 Filegroups**
✅ **19 Tabelas** (18 KPI + 1 auxiliar)
✅ **23 Views** (22 KPI + 1 CMDB)
✅ **12 Procedures** (11 coleta + 1 master)
✅ **2 SQL Agent Jobs** (coleta + limpeza)

### Como funciona:

```
SQL Server Agent Job (a cada 5 min)
         ↓
usp_Collect_All_KPIs (procedure master)
         ↓
11 procedures de coleta individuais
         ↓
Dados armazenados em tabelas STG
         ↓
Dados copiados para tabelas HIST (DB Availability, Disk, TLog)
         ↓
Views agregam dados (AGG + DET)
         ↓
Dashboard/API consulta views
```

### Tempo de deployment:

- **Deployment:** 5-10 minutos
- **Primeira coleta:** Imediata (teste automático)
- **Coleta automática:** A cada 5 minutos (via job)

### Status:

🎉 **DEPLOYMENT 100% COMPLETO E FUNCIONAL!**

---

**WatcherDB Intelligence V2**
**Script Único de Deployment**
**Versão: 2.0.0**
**Data: 2025-11-27**
