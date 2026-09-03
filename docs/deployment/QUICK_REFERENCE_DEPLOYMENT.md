# 🚀 QUICK REFERENCE - Deployment Replicação Oracle → SQL Server

**Versão:** 2.0.0
**Data:** 2025-11-27

---

## ⚡ COMANDOS RÁPIDOS

### 1️⃣ Deployment Completo (5 minutos)

```sql
-- ==================================================
-- DEPLOYMENT EM 4 PASSOS
-- ==================================================

-- PASSO 1: Criar database (se não existir)
-- ==================================================
CREATE DATABASE [WatcherDB_Intelligence_V2];
GO

USE [WatcherDB_Intelligence_V2];
GO

-- PASSO 2: Criar tabelas (18 tabelas)
-- ==================================================
:r C:\path\to\database\SQLSERVER_KPI_REPLICATION_COMPLETE.sql
GO

-- PASSO 3: Criar views (23 views)
-- ==================================================
:r C:\path\to\database\SQLSERVER_KPI_VIEWS.sql
GO

-- PASSO 4: Configurar mapeamento Instance → Environment
-- ==================================================
INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env, Description)
VALUES
    (@@SERVERNAME, 'PROD', 'Servidor local'),
    ('SQLHDSPRD213\I01', 'PROD', 'Produção principal'),
    ('SQLHDSUAT01\I01', 'UAT', 'User Acceptance Testing'),
    ('SQLHDSDEV01\I01', 'DEV', 'Desenvolvimento');
GO
```

### ✅ Validação Rápida

```sql
-- Verificar tabelas criadas (deve retornar 19)
SELECT COUNT(*) AS Total_Tabelas
FROM sys.tables
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%';

-- Verificar views criadas (deve retornar 23)
SELECT COUNT(*) AS Total_Views
FROM sys.views
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%';

-- Verificar filegroups criados
SELECT name, type_desc
FROM sys.filegroups
WHERE name LIKE 'FG_KPI%';

-- Verificar mapeamento de ambientes
SELECT * FROM dbo.KPI_MSSQL_INST_ENVS;
```

---

## 📋 LISTA COMPLETA DE OBJETOS CRIADOS

### Tabelas (18 + 1 auxiliar = 19 total)

```
[Staging - 11 tabelas]
✓ KPI_MSSQL_ALWAYSON_STATUS_STG
✓ KPI_MSSQL_BACKUPS_STG
✓ KPI_MSSQL_BLOCKED_SESSIONS_STG
✓ KPI_MSSQL_BLOCKED_USERS_STG
✓ KPI_MSSQL_DB_AVAILABILITY_STG
✓ KPI_MSSQL_DISK_USAGE_STG
✓ KPI_MSSQL_FG_USAGE_STG
✓ KPI_MSSQL_INST_AVAILABILITY_STG
✓ KPI_MSSQL_LONG_LOCKS_STG
✓ KPI_MSSQL_PROCESSES_STG
✓ KPI_MSSQL_TLOG_USAGE_STG

[Histórico - 3 tabelas]
✓ KPI_MSSQL_DB_AVAILABILITY_HIST
✓ KPI_MSSQL_DISK_USAGE_HIST
✓ KPI_MSSQL_TLOG_USAGE_HIST

[Configuração - 2 tabelas]
✓ KPI_MSSQL_THRESHOLDS
✓ KPI_MSSQL_THRESHOLDS_V2

[CMDB - 2 tabelas]
✓ CMDB_MSSQL_DATABASES
✓ CMDB_MSSQL_DATABASES_HIST

[Auxiliar - 1 tabela]
✓ KPI_MSSQL_INST_ENVS  ← Mapear Instance → Environment
```

### Views (23 total)

```
[KPI Views - 22 views (11 AGG + 11 DET)]
✓ KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW      ✓ KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW
✓ KPI_MSSQL_BACKUPS_AGG_VIEW              ✓ KPI_MSSQL_BACKUPS_DET_VIEW
✓ KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW     ✓ KPI_MSSQL_BLOCKED_SESSIONS_DET_VIEW
✓ KPI_MSSQL_BLOCKED_USERS_AGG_VIEW        ✓ KPI_MSSQL_BLOCKED_USERS_DET_VIEW
✓ KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW      ✓ KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
✓ KPI_MSSQL_DISK_USAGE_AGG_VIEW           ✓ KPI_MSSQL_DISK_USAGE_DET_VIEW
✓ KPI_MSSQL_FG_USAGE_AGG_VIEW             ✓ KPI_MSSQL_FG_USAGE_DET_VIEW
✓ KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW    ✓ KPI_MSSQL_INST_AVAILABILITY_DET_VIEW
✓ KPI_MSSQL_LONG_LOCKS_AGG_VIEW           ✓ KPI_MSSQL_LONG_LOCKS_DET_VIEW
✓ KPI_MSSQL_PROCESSES_AGG_VIEW            ✓ KPI_MSSQL_PROCESSES_DET_VIEW
✓ KPI_MSSQL_TLOG_USAGE_AGG_VIEW           ✓ KPI_MSSQL_TLOG_USAGE_DET_VIEW

[CMDB Views - 1 view]
✓ CMDB_MSSQL_DATABASES_VW
```

---

## 🧪 TESTES RÁPIDOS

### Teste 1: Estrutura criada corretamente

```sql
-- Deve retornar 19 tabelas
SELECT 'Tabelas' AS Tipo, COUNT(*) AS Total
FROM sys.tables
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%'
UNION ALL
-- Deve retornar 23 views
SELECT 'Views', COUNT(*)
FROM sys.views
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%'
UNION ALL
-- Deve retornar 2 filegroups
SELECT 'Filegroups', COUNT(*)
FROM sys.filegroups
WHERE name LIKE 'FG_KPI%';
```

**Resultado esperado:**
```
Tipo         Total
-----------  -----
Tabelas      19
Views        23
Filegroups   2
```

### Teste 2: Views executam sem erro

```sql
-- Todas devem retornar 0 linhas (STG vazias) MAS sem erros
SELECT * FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW;
```

**Se receber erro "Invalid object name":**
- ❌ Views não foram criadas → Re-executar `SQLSERVER_KPI_VIEWS.sql`

**Se receber apenas 0 linhas:**
- ✅ Views criadas corretamente, tabelas STG vazias (esperado!)

### Teste 3: Inserir dados de teste

```sql
-- Inserir dado de teste em uma tabela STG
INSERT INTO dbo.KPI_MSSQL_DISK_USAGE_STG (Instance, Drive, Total_MB, Free_MB, Used_MB, Percent_Free, Update_TS)
VALUES ('TESTE\INST01', 'C:', 100000, 30000, 70000, 30.0, GETDATE());

-- Verificar se view mostra o dado
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;
SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_DET_VIEW;

-- Limpar teste
TRUNCATE TABLE dbo.KPI_MSSQL_DISK_USAGE_STG;
```

---

## 🔧 TROUBLESHOOTING

### Problema: "Cannot open database 'WatcherDB_Intelligence_V2'"

```sql
-- Solução: Criar database
CREATE DATABASE [WatcherDB_Intelligence_V2];
GO
USE [WatcherDB_Intelligence_V2];
GO
```

### Problema: "Filegroup 'FG_KPI_DATA' does not exist"

```sql
-- Causa: Script de tabelas não executado
-- Solução: Re-executar
:r SQLSERVER_KPI_REPLICATION_COMPLETE.sql
```

### Problema: "Invalid object name 'KPI_MSSQL_INST_ENVS'"

```sql
-- Causa: Script de views não executado
-- Solução: Executar
:r SQLSERVER_KPI_VIEWS.sql
```

### Problema: Views retornam NULL em coluna "Env"

```sql
-- Causa: Tabela KPI_MSSQL_INST_ENVS vazia
-- Solução: Popular
INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env)
VALUES (@@SERVERNAME, 'PROD');
```

### Problema: Erro de permissões

```sql
-- Verificar permissões
SELECT USER_NAME() AS Current_User;

-- Dar permissões necessárias (executar como SA)
ALTER ROLE db_owner ADD MEMBER [seu_usuario];
```

---

## 📊 QUERIES ÚTEIS

### Listar todas as tabelas KPI

```sql
SELECT
    t.name AS Table_Name,
    SUM(p.rows) AS Row_Count,
    CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(10,2)) AS Size_MB,
    fg.name AS Filegroup
FROM sys.tables t
INNER JOIN sys.indexes i ON t.object_id = i.object_id
INNER JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
LEFT JOIN sys.data_spaces fg ON i.data_space_id = fg.data_space_id
WHERE t.name LIKE 'KPI_MSSQL%' OR t.name LIKE 'CMDB_MSSQL%'
GROUP BY t.name, fg.name
ORDER BY t.name;
```

### Listar todas as views KPI

```sql
SELECT
    v.name AS View_Name,
    CAST(LEN(m.definition) AS DECIMAL(10,0)) AS Definition_Length,
    m.definition AS SQL_Definition
FROM sys.views v
INNER JOIN sys.sql_modules m ON v.object_id = m.object_id
WHERE v.name LIKE 'KPI_MSSQL%' OR v.name LIKE 'CMDB_MSSQL%'
ORDER BY v.name;
```

### Ver estrutura de uma tabela específica

```sql
-- Exemplo: KPI_MSSQL_DISK_USAGE_STG
SELECT
    c.name AS Column_Name,
    t.name AS Data_Type,
    c.max_length AS Max_Length,
    c.is_nullable AS Is_Nullable,
    dc.definition AS Default_Value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
WHERE c.object_id = OBJECT_ID('dbo.KPI_MSSQL_DISK_USAGE_STG')
ORDER BY c.column_id;
```

### Verificar índices criados

```sql
SELECT
    t.name AS Table_Name,
    i.name AS Index_Name,
    i.type_desc AS Index_Type,
    COL_NAME(ic.object_id, ic.column_id) AS Column_Name
FROM sys.tables t
INNER JOIN sys.indexes i ON t.object_id = i.object_id
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
WHERE t.name LIKE 'KPI_MSSQL%' OR t.name LIKE 'CMDB_MSSQL%'
ORDER BY t.name, i.name, ic.key_ordinal;
```

---

## 🎯 COMANDOS DE LIMPEZA (CUIDADO!)

### Remover todas as views KPI

```sql
-- ⚠️ CUIDADO: Remove todas as views!
DECLARE @sql NVARCHAR(MAX) = '';

SELECT @sql += 'DROP VIEW IF EXISTS ' + QUOTENAME(SCHEMA_NAME(schema_id)) + '.' + QUOTENAME(name) + ';' + CHAR(13)
FROM sys.views
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%';

PRINT @sql;
-- EXEC sp_executesql @sql;  ← Descomentar para executar
```

### Remover todas as tabelas KPI

```sql
-- ⚠️ CUIDADO: Remove todas as tabelas E DADOS!
DECLARE @sql NVARCHAR(MAX) = '';

SELECT @sql += 'DROP TABLE IF EXISTS ' + QUOTENAME(SCHEMA_NAME(schema_id)) + '.' + QUOTENAME(name) + ';' + CHAR(13)
FROM sys.tables
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%';

PRINT @sql;
-- EXEC sp_executesql @sql;  ← Descomentar para executar
```

### Truncar todas as tabelas STG

```sql
-- ⚠️ Remove dados mas mantém estrutura
TRUNCATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_BACKUPS_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_BLOCKED_USERS_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_DISK_USAGE_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_FG_USAGE_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_INST_AVAILABILITY_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_LONG_LOCKS_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_PROCESSES_STG;
TRUNCATE TABLE dbo.KPI_MSSQL_TLOG_USAGE_STG;
```

---

## 📁 ARQUIVOS DE REFERÊNCIA

### Scripts SQL (executar nesta ordem)

1. `database/SQLSERVER_KPI_REPLICATION_COMPLETE.sql` - Criar 18 tabelas
2. `database/SQLSERVER_KPI_VIEWS.sql` - Criar 23 views

### Documentação (ler nesta ordem)

1. `README_REPLICACAO_ORACLE_SQLSERVER.md` - **COMEÇAR AQUI** (Quick Start)
2. `docs/REPLICACAO_ORACLE_SQLSERVER_RESUMO_FINAL.md` - Resumo executivo completo
3. `docs/EXTRACAO_ORACLE_RESUMO.md` - Detalhes da extração Oracle
4. `QUICK_REFERENCE_DEPLOYMENT.md` - **ESTE ARQUIVO** (comandos rápidos)

### Scripts Python (referência)

- `extract_oracle_structure.py` - Extração Oracle (usado para gerar scripts)
- `services/sqlserver_kpi_service.py` - Queries de coleta (referência para implementar coleta)

---

## ⏭️ PRÓXIMO PASSO: POPULAR DADOS

### Opção 1: Python Script (RECOMENDADO)

```python
# collect_kpis.py
import pyodbc

# Conectar SQL Server
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=SQLHDSPRD213\\I01;"
    "DATABASE=WatcherDB_Intelligence_V2;"
    "Trusted_Connection=yes;"
)

# Coletar disk usage
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO dbo.KPI_MSSQL_DISK_USAGE_STG (Instance, Drive, Total_MB, Free_MB, ...)
    SELECT @@SERVERNAME, volume_mount_point, total_bytes/1024/1024, ...
    FROM sys.master_files mf
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id)
""")
conn.commit()

print("Dados coletados com sucesso!")
```

**Agendar execução:**
```powershell
# Windows Task Scheduler
schtasks /create /tn "WatcherDB_Collect_KPIs" /tr "python C:\...\collect_kpis.py" /sc minute /mo 5
```

### Opção 2: T-SQL Procedure

```sql
CREATE PROCEDURE dbo.usp_Collect_All_KPIs
AS
BEGIN
    -- Coletar disk usage
    TRUNCATE TABLE dbo.KPI_MSSQL_DISK_USAGE_STG;
    INSERT INTO dbo.KPI_MSSQL_DISK_USAGE_STG (...)
    SELECT ... FROM sys.dm_os_volume_stats ...;

    -- Repetir para outros KPIs
END;
GO

-- Criar SQL Agent Job
EXEC msdb.dbo.sp_add_job @job_name = 'KPI_Collect_All';
EXEC msdb.dbo.sp_add_jobstep @step_name = 'Collect', @command = 'EXEC usp_Collect_All_KPIs';
EXEC msdb.dbo.sp_add_schedule @schedule_name = 'Every5Min', @freq_type = 4, @freq_interval = 1, @freq_subday_type = 4, @freq_subday_interval = 5;
```

---

## 🏁 CHECKLIST FINAL

### Deployment Completo

- [ ] Database criado: `WatcherDB_Intelligence_V2`
- [ ] Script tabelas executado: `SQLSERVER_KPI_REPLICATION_COMPLETE.sql`
- [ ] Script views executado: `SQLSERVER_KPI_VIEWS.sql`
- [ ] Tabela INST_ENVS populada com mapeamentos Instance → Env
- [ ] Validação: 19 tabelas + 23 views criadas
- [ ] Teste: Views executam sem erro (retornam 0 linhas)
- [ ] **PRÓXIMO:** Implementar coleta de dados (Python ou T-SQL)

---

**WatcherDB Intelligence V2**
**Quick Reference - Deployment**
**Versão: 2.0.0**
**Data: 2025-11-27**
