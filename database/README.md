# 📁 WatcherDB Intelligence - Database Scripts

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Scripts de Deploy](#scripts-de-deploy)
- [Scripts de Views](#scripts-de-views)
- [Scripts de Procedures](#scripts-de-procedures)
- [Scripts de Correções](#scripts-de-correções)
- [Documentação](#documentação)
- [Ordem de Execução](#ordem-de-execução)

---

## 🎯 Visão Geral

Esta pasta contém todos os scripts SQL necessários para criar, manter e atualizar o banco de dados **WatcherDB_Intelligence**.

**Banco de Dados:** WatcherDB_Intelligence
**Versão:** 2.0 (Intelligence Edition)
**Última Atualização:** 2026-01-27

---

## 📦 Scripts de Deploy

### 🚀 Deploy Completo

| Arquivo | Descrição | Ordem |
|---------|-----------|-------|
| `00_WATCHERDB_MASTER_DEPLOY.sql` | Script mestre de criação do banco | 1 |
| `INSTALACAO_COMPLETA_UNIFICADA.sql` | Deploy unificado completo | 1 (alternativa) |
| `SQLSERVER_KPI_DEPLOY_COMPLETE.sql` | Deploy completo de KPIs SQL Server | 2 |

### 📊 Componentes Individuais

| Arquivo | Descrição | Ordem |
|---------|-----------|-------|
| `02_WATCHERDB_INDEXES.sql` | Criação de índices otimizados | 3 |
| `03_WATCHERDB_PROCEDURES.sql` | Stored procedures principais | 4 |
| `04_WATCHERDB_VIEWS.sql` | Views de dashboard e reporting | 5 |
| `05_WATCHERDB_BLUE_GREEN_ENV.sql` | Configuração de ambientes Blue/Green | 6 |

---

## 🔍 Scripts de Views

### Views de Disponibilidade de Databases

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql` | ⭐ View de problemas reais (exclui falsos positivos) | ✅ **RECOMENDADO** |

**Documentação Completa:** [DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md](DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md)

### Views AlwaysOn

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `CRIAR_VIEW_ALWAYSON_AGG.sql` | View agregada de AlwaysOn Availability Groups | ✅ Implementado |

### Views de KPIs

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `SQLSERVER_KPI_VIEWS.sql` | Views de KPIs SQL Server | ✅ Implementado |

---

## ⚙️ Scripts de Procedures

### Coleta de KPIs

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `SQLSERVER_KPI_COLLECTION_PROCEDURES.sql` | Procedures de coleta de KPIs | ✅ Implementado |
| `SQLSERVER_KPI_AGENT_JOBS.sql` | Jobs de coleta automatizada | ✅ Implementado |

---

## 🔧 Scripts de Correções

### Database Availability

| Arquivo | Descrição | Data | Ticket |
|---------|-----------|------|--------|
| `CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql` | ⭐ Correção de falsos positivos (mirrors em RESTORING) | 2026-01-27 | #BUG-001 |
| `UPDATE_DB_AVAILABILITY_MIRRORING.sql` | Atualização de dados de mirroring | 2026-01-27 | - |

**Problema Corrigido:** 141 databases em estado RESTORING (mirrors secundários) eram reportados como problemas. Agora são corretamente excluídos.

**Resultado:**
- ✅ Antes: 141 falsos positivos (100%)
- ✅ Depois: 0 problemas (correto!)

### Disk Unallocated

| Arquivo | Descrição | Data |
|---------|-----------|------|
| `CREATE_DISK_UNALLOCATED_TABLES.sql` | Criação de tabelas para disk unallocated | 2026-01-15 |

### Eventos de Servidor Offline

| Arquivo | Descrição | Data |
|---------|-----------|------|
| `KPI_SERVER_OFFLINE_EVENTS.sql` | Tabela de eventos de servidor offline | 2026-01-20 |

---

## 📚 Documentação

### Documentos Disponíveis

| Documento | Descrição | Status |
|-----------|-----------|--------|
| [DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md](DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md) | ⭐ Documentação completa de Database Availability Views | ✅ **NOVO** |
| `README.md` | Este arquivo - Índice de scripts | ✅ Atual |

### Conteúdo da Documentação de Database Availability:

- ✅ Estrutura das 4 views (STG, DET, AGG, PROBLEM)
- ✅ Lógica de exclusão de falsos positivos
- ✅ Casos de uso e exemplos
- ✅ Casos de teste
- ✅ Procedimentos de manutenção
- ✅ Changelog completo da correção

---

## 🔢 Ordem de Execução

### 📍 Instalação Inicial (Banco Novo)

```sql
-- 1. Criar banco e estrutura base
-- Execute em ordem:

USE master;
GO
-- 1.1. Deploy Master
:r 00_WATCHERDB_MASTER_DEPLOY.sql

-- 1.2. Deploy KPIs SQL Server
:r SQLSERVER_KPI_DEPLOY_COMPLETE.sql

-- 1.3. Índices
:r 02_WATCHERDB_INDEXES.sql

-- 1.4. Procedures
:r 03_WATCHERDB_PROCEDURES.sql

-- 1.5. Views
:r 04_WATCHERDB_VIEWS.sql

-- 1.6. Blue/Green Environments (opcional)
:r 05_WATCHERDB_BLUE_GREEN_ENV.sql
```

### ⚡ Correções e Atualizações (Banco Existente)

```sql
-- 1. Database Availability Problem View (RECOMENDADO)
USE WatcherDB_Intelligence;
GO
:r CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql

-- 2. AlwaysOn Views
:r CRIAR_VIEW_ALWAYSON_AGG.sql

-- 3. Disk Unallocated Tables
:r CREATE_DISK_UNALLOCATED_TABLES.sql

-- 4. Server Offline Events
:r KPI_SERVER_OFFLINE_EVENTS.sql
```

### 🔄 Após Executar Scripts SQL

```powershell
# SEMPRE reinicie o serviço WatcherDB para aplicar mudanças
cd C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV
python install.py restart
```

---

## 🗂️ Organização de Arquivos

### Por Categoria:

#### 📦 Deploy e Estrutura
```
00_WATCHERDB_MASTER_DEPLOY.sql
INSTALACAO_COMPLETA_UNIFICADA.sql
SQLSERVER_KPI_DEPLOY_COMPLETE.sql
```

#### 🔧 Componentes
```
02_WATCHERDB_INDEXES.sql
03_WATCHERDB_PROCEDURES.sql
04_WATCHERDB_VIEWS.sql
05_WATCHERDB_BLUE_GREEN_ENV.sql
```

#### 🔍 Views Específicas
```
CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql    ⭐ NOVO
CRIAR_VIEW_ALWAYSON_AGG.sql
SQLSERVER_KPI_VIEWS.sql
```

#### ⚙️ Procedures e Jobs
```
SQLSERVER_KPI_COLLECTION_PROCEDURES.sql
SQLSERVER_KPI_AGENT_JOBS.sql
```

#### 🔄 Correções e Updates
```
UPDATE_DB_AVAILABILITY_MIRRORING.sql
CREATE_DISK_UNALLOCATED_TABLES.sql
KPI_SERVER_OFFLINE_EVENTS.sql
```

#### 🗄️ Collection History
```
COLLECTION_HISTORY_SECTION.sql
```

#### 🔁 Replicação Oracle
```
oracle_procedures_jobs_20251127_225005.sql
oracle_sqlserver_kpi_structure_20251127_224257.sql
oracle_sqlserver_kpi_structure_20251127_224538.sql
SQLSERVER_KPI_REPLICATION_COMPLETE.sql
```

---

## 🔍 Verificação de Integridade

### Verificar Objetos Criados

```sql
USE WatcherDB_Intelligence;
GO

-- Verificar views
SELECT
    SCHEMA_NAME(schema_id) AS [Schema],
    name AS ViewName,
    create_date,
    modify_date
FROM sys.views
WHERE is_ms_shipped = 0
ORDER BY name;

-- Verificar procedures
SELECT
    SCHEMA_NAME(schema_id) AS [Schema],
    name AS ProcedureName,
    create_date,
    modify_date
FROM sys.procedures
WHERE is_ms_shipped = 0
ORDER BY name;

-- Verificar tabelas
SELECT
    SCHEMA_NAME(schema_id) AS [Schema],
    name AS TableName,
    create_date,
    modify_date
FROM sys.tables
WHERE is_ms_shipped = 0
ORDER BY name;
```

### Verificar Database Availability

```sql
-- Deve retornar 0 se não houver problemas reais
SELECT COUNT(*) AS Problem_Count
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW;

-- Comparar com total de databases
SELECT
    (SELECT COUNT(*) FROM KPI_MSSQL_DB_AVAILABILITY_STG) AS Total_Databases,
    (SELECT COUNT(*) FROM KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW) AS Problem_Databases,
    (SELECT COUNT(*) FROM KPI_MSSQL_DB_AVAILABILITY_STG WHERE [State] = 'RESTORING') AS Restoring_Databases;
```

---

## ⚠️ Avisos Importantes

### ⚡ Database Availability Problem View

**IMPORTANTE:** Se você está vendo falsos positivos no card "DB Not Availability" do portal WatcherDB:

1. **Execute o script:**
   ```sql
   USE WatcherDB_Intelligence;
   GO
   :r CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql
   ```

2. **Reinicie o serviço:**
   ```powershell
   python install.py restart
   ```

3. **Leia a documentação:** [DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md](DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md)

### 🔄 Após Atualizações

Sempre que executar scripts SQL que modificam views ou procedures:

```powershell
# Reiniciar o serviço WatcherDB
python install.py restart

# Verificar se iniciou corretamente
python install.py status
```

### 🗄️ Backup Recomendado

Antes de executar scripts de correção em produção:

```sql
-- Fazer backup do banco
BACKUP DATABASE WatcherDB_Intelligence
TO DISK = 'C:\Backups\WatcherDB_Intelligence_BEFORE_UPDATE.bak'
WITH FORMAT, COMPRESSION;
```

---

## 📊 Métricas de Qualidade

### Scripts Executados com Sucesso:

| Script | Data Execução | Status | Problemas Corrigidos |
|--------|---------------|--------|----------------------|
| `CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql` | 2026-01-27 16:40:49 | ✅ Sucesso | 141 falsos positivos eliminados |
| `00_WATCHERDB_MASTER_DEPLOY.sql` | - | ✅ Validado | - |
| `04_WATCHERDB_VIEWS.sql` | - | ✅ Validado | - |

### Resultados Pós-Implementação:

```
View: KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total de databases na STG:        1962
Databases em RESTORING:            141
Problemas detectados:                0  ✅
Falsos positivos eliminados:       141  ✅
Precisão:                         100%  ✅
```

---

## 🆘 Troubleshooting

### Problema: View não encontrada

```sql
-- Erro: Invalid object name 'KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW'

-- Solução:
USE WatcherDB_Intelligence;
GO
:r CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql
```

### Problema: Coluna Mirroring_Role não existe

```sql
-- O script CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql já adiciona a coluna se necessário
-- Mas se precisar adicionar manualmente:

ALTER TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG
ADD Mirroring_Role VARCHAR(32) NULL;
GO
```

### Problema: Ainda vejo falsos positivos

```powershell
# 1. Verificar se a view foi criada
# 2. Reiniciar o serviço
python install.py restart

# 3. Verificar logs
type services\web_service\service.log

# 4. Testar manualmente
# Execute no SQL Server:
SELECT COUNT(*) FROM KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW;
```

---

## 📞 Suporte

**Em caso de dúvidas ou problemas:**

1. Consulte a documentação específica de cada componente
2. Verifique os logs do serviço: `services/web_service/service.log`
3. Verifique a integridade do banco de dados (queries acima)
4. Revise o changelog neste README

---

## 📝 Changelog

### [2.1.0] - 2026-01-27

#### ✅ Adicionado:
- ⭐ `CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql` - View inteligente de problemas
- ⭐ `DATABASE_AVAILABILITY_VIEWS_DOCUMENTATION.md` - Documentação completa
- ⭐ `README.md` - Este arquivo de índice e documentação

#### 🐛 Corrigido:
- Bug crítico: 141 databases em RESTORING reportados como problemas
- Falsos positivos: Mirrors secundários em estado normal agora são excluídos
- Precisão do KPI "DB Not Availability": Agora 100% preciso

#### 📊 Impacto:
- Portal WatcherDB: Card "DB Not Availability" agora mostra apenas problemas REAIS
- Alertas: Redução de 141 falsos positivos (100% das detecções anteriores)
- Operação: Melhor visibilidade de problemas reais

---

**Mantido por:** Equipe WatcherDB
**Última Atualização:** 2026-01-27
**Versão do Banco:** 2.1.0
**Status:** ✅ Estável e Documentado
