# PROMPT: Módulo 2PC - PARTE 1: Database + Coleta
## Projeto: WATCHERDB INTELLIGENCE V1

---

## CONTEXTO

Estou no projeto **WATCHERDB INTELLIGENCE V1** localizado em:
```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\
```

Este projeto é responsável por:
- Scripts SQL (tabelas, views, procedures, functions)
- SQL Agent Jobs
- Collector Service (serviço de coleta em background)

**Estrutura atual relevante:**
```
WATCHERDB INTELLIGENCE V1/
├── services/
│   └── collector_service/
│       ├── service.py              # Windows Service wrapper
│       ├── collectors_base.py      # Framework base de coletores
│       ├── config.yaml             # Configuração
│       └── collectors/             # Coletores específicos
│           ├── backup_collector.py
│           ├── disk_collector.py
│           └── ...
├── database/
│   ├── tables/
│   ├── views/
│   ├── procedures/
│   └── jobs/
└── config/
    └── sql_servers.json
```

---

## OBJETIVO

Criar a **infraestrutura de database e coleta** para monitoramento de **Transações Distribuídas Two-Phase Commit (2PC)** no SQL Server.

### O que é 2PC?
- Protocolo para garantir atomicidade em transações distribuídas (via Linked Server)
- É acionado **automaticamente** pelo SQL Server quando há transações via Linked Server
- Transações "in-doubt" são **CRÍTICAS** e requerem intervenção manual do DBA
- Comando de resolução: `KILL 'UOW' WITH ROLLBACK` ou `KILL 'UOW' WITH COMMIT`

### ⚠️ IMPORTANTE: Compatibilidade de DMVs por Versão (VALIDADO)

| Versão Major | SQL Server | Método | DMV |
|--------------|------------|--------|-----|
| **≥ 16** | 2022+ (incluindo futuras) | DMV nativa | `sys.dm_tran_distributed_transaction_stats` |
| **11-15** | 2012-2019 | Universal | `sys.dm_tran_locks` com filtro `DISTRIBUTED_TRANSACTION` |
| **< 11** | Antigas | Limitado | `sys.dm_tran_locks` (funcionalidade limitada) |

**NOTAS IMPORTANTES:**
1. A DMV `sys.dm_tran_distributed_transactions` **NÃO EXISTE** no SQL Server on-premises
2. Use sempre detecção de versão com `@v >= 16` para SQL 2022+ (future-proof)
3. O método `sys.dm_tran_locks` funciona em TODAS as versões e fornece comandos KILL

**Lógica de detecção de versão (VALIDADA):**
```sql
DECLARE @v INT = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)), 4) AS INT);
-- @v >= 16 = SQL 2022+ (usa DMV nativa)
-- @v >= 11 = SQL 2012-2019 (usa dm_tran_locks)
-- @v < 11 = Versões antigas
```

---

## ENTREGÁVEIS

### 1. Script SQL: Tabelas
**Arquivo:** `database/tables/Monitor_2PC_Tables.sql`

Criar as seguintes tabelas no database `WatcherDB`:

```sql
-- ============================================
-- Tabela: Monitor_2PC_Transactions
-- Armazena histórico de transações distribuídas
-- ============================================
CREATE TABLE dbo.Monitor_2PC_Transactions (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    collected_at DATETIME2 DEFAULT GETDATE(),
    server_name SYSNAME NOT NULL,
    transaction_id BIGINT,
    state_desc NVARCHAR(60),              -- ACTIVE, PREPARED, COMMITTED, ABORTED
    dtc_state_desc NVARCHAR(60),
    result_desc NVARCHAR(60),
    uow UNIQUEIDENTIFIER,                 -- Unit of Work (para comando KILL)
    session_id INT,
    login_name NVARCHAR(128),
    host_name NVARCHAR(128),
    program_name NVARCHAR(128),
    database_name NVARCHAR(128),
    transaction_begin_time DATETIME2,
    duration_seconds INT,
    locks_held INT,
    is_in_doubt BIT,                      -- 1 = CRÍTICO, requer intervenção!
    
    INDEX IX_CollectedAt (collected_at),
    INDEX IX_ServerName (server_name),
    INDEX IX_InDoubt (is_in_doubt) WHERE is_in_doubt = 1
);

-- ============================================
-- Tabela: Monitor_2PC_Alerts
-- Armazena alertas gerados
-- ============================================
CREATE TABLE dbo.Monitor_2PC_Alerts (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    created_at DATETIME2 DEFAULT GETDATE(),
    server_name SYSNAME NOT NULL,
    alert_type NVARCHAR(50),              -- 'IN_DOUBT', 'LONG_RUNNING', 'DTC_ERROR'
    alert_severity NVARCHAR(20),          -- 'CRITICAL', 'WARNING', 'INFO'
    transaction_id BIGINT,
    uow UNIQUEIDENTIFIER,
    details NVARCHAR(MAX),
    resolved_at DATETIME2 NULL,
    resolved_by NVARCHAR(128) NULL,
    resolution_action NVARCHAR(50) NULL,  -- 'ROLLBACK', 'COMMIT', 'AUTO_RESOLVED'
    
    INDEX IX_CreatedAt (created_at),
    INDEX IX_Unresolved (resolved_at) WHERE resolved_at IS NULL
);

-- ============================================
-- Tabela: Monitor_2PC_DTC_Status
-- Armazena status do MS DTC
-- ============================================
CREATE TABLE dbo.Monitor_2PC_DTC_Status (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    checked_at DATETIME2 DEFAULT GETDATE(),
    server_name SYSNAME NOT NULL,
    dtc_status NVARCHAR(20),              -- 'RUNNING', 'STOPPED', 'ERROR'
    error_message NVARCHAR(MAX) NULL,
    
    INDEX IX_CheckedAt (checked_at)
);
```

---

### 2. Script SQL: Views
**Arquivo:** `database/views/vw_2PC_Status.sql`

```sql
-- ============================================
-- View: Status Consolidado de Transações 2PC
-- ============================================
CREATE OR ALTER VIEW dbo.vw_2PC_Current_Status
AS
SELECT 
    server_name,
    MAX(collected_at) AS last_check,
    COUNT(*) AS total_distributed_transactions,
    SUM(CASE WHEN state_desc = 'ACTIVE' THEN 1 ELSE 0 END) AS active_count,
    SUM(CASE WHEN state_desc = 'PREPARED' THEN 1 ELSE 0 END) AS in_doubt_count,
    SUM(CASE WHEN state_desc = 'COMMITTED' THEN 1 ELSE 0 END) AS committed_count,
    SUM(CASE WHEN state_desc = 'ABORTED' THEN 1 ELSE 0 END) AS aborted_count,
    MAX(duration_seconds) AS max_duration_seconds,
    CASE 
        WHEN SUM(CASE WHEN is_in_doubt = 1 THEN 1 ELSE 0 END) > 0 THEN 'CRITICAL'
        WHEN SUM(CASE WHEN duration_seconds > 1800 THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
        ELSE 'OK'
    END AS alert_status
FROM dbo.Monitor_2PC_Transactions
WHERE collected_at >= DATEADD(MINUTE, -10, GETDATE())  -- Últimos 10 min
GROUP BY server_name;
GO

-- ============================================
-- View: Alertas Ativos (não resolvidos)
-- ============================================
CREATE OR ALTER VIEW dbo.vw_2PC_Active_Alerts
AS
SELECT 
    id,
    created_at,
    server_name,
    alert_type,
    alert_severity,
    transaction_id,
    uow,
    details,
    DATEDIFF(MINUTE, created_at, GETDATE()) AS minutes_open
FROM dbo.Monitor_2PC_Alerts
WHERE resolved_at IS NULL;
GO

-- ============================================
-- View: Transações In-Doubt (CRÍTICO)
-- ============================================
CREATE OR ALTER VIEW dbo.vw_2PC_InDoubt_Transactions
AS
SELECT 
    server_name,
    transaction_id,
    state_desc,
    dtc_state_desc,
    uow,
    database_name,
    login_name,
    host_name,
    duration_seconds,
    locks_held,
    collected_at,
    'KILL ''' + CAST(uow AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
    'KILL ''' + CAST(uow AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
FROM dbo.Monitor_2PC_Transactions
WHERE is_in_doubt = 1
  AND collected_at >= DATEADD(MINUTE, -10, GETDATE());
GO
```

---

### 3. Script SQL: Procedures
**Arquivo:** `database/procedures/usp_2PC_Monitoring.sql`

```sql
-- ============================================
-- Procedure: Coletar Transações 2PC de um Servidor
-- COMPATÍVEL COM TODAS AS VERSÕES (2012+)
-- ============================================
CREATE OR ALTER PROCEDURE dbo.usp_Collect_2PC_Transactions
    @server_name SYSNAME
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Esta procedure deve ser chamada pelo collector Python
    -- que executa a query diretamente no servidor remoto
    -- e insere os resultados aqui
    
    -- Query UNIVERSAL a ser executada no servidor remoto:
    -- (Funciona em SQL Server 2012-2019-2022+)
    /*
    SELECT 
        @@SERVERNAME AS server_name,
        l.request_owner_guid AS uow,
        DB_NAME(l.resource_database_id) AS database_name,
        COUNT(*) AS locks_held,
        MAX(l.resource_type) AS resource_type,
        MAX(l.request_mode) AS request_mode,
        MAX(l.request_status) AS request_status,
        1 AS is_in_doubt,  -- Se tem lock distribuído, é in-doubt
        'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
        'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
    FROM sys.dm_tran_locks l
    WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
    GROUP BY l.request_owner_guid, l.resource_database_id;
    */
    
    -- Query ADICIONAL para SQL Server 2022+ (estatísticas):
    /*
    SELECT 
        @@SERVERNAME AS server_name,
        [open] AS open_transactions,
        in_doubt AS in_doubt_transactions,
        committed AS committed_transactions,
        aborted AS aborted_transactions
    FROM sys.dm_tran_distributed_transaction_stats;
    */
END
GO

-- ============================================
-- Procedure: Verificar e Gerar Alertas
-- ============================================
CREATE OR ALTER PROCEDURE dbo.usp_Check_2PC_Alerts
    @threshold_minutes INT = 30
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Alertar transações in-doubt (CRÍTICO)
    INSERT INTO dbo.Monitor_2PC_Alerts (server_name, alert_type, alert_severity, transaction_id, uow, details)
    SELECT 
        server_name,
        'IN_DOUBT',
        'CRITICAL',
        transaction_id,
        uow,
        'Transação in-doubt detectada! Database: ' + ISNULL(database_name, 'N/A') + 
        ', Duração: ' + CAST(duration_seconds AS VARCHAR) + 's, Locks: ' + CAST(locks_held AS VARCHAR)
    FROM dbo.Monitor_2PC_Transactions t
    WHERE is_in_doubt = 1
      AND collected_at >= DATEADD(MINUTE, -10, GETDATE())
      AND NOT EXISTS (
          SELECT 1 FROM dbo.Monitor_2PC_Alerts a 
          WHERE a.uow = t.uow 
            AND a.resolved_at IS NULL
      );
    
    -- Alertar transações muito longas (WARNING)
    INSERT INTO dbo.Monitor_2PC_Alerts (server_name, alert_type, alert_severity, transaction_id, uow, details)
    SELECT 
        server_name,
        'LONG_RUNNING',
        'WARNING',
        transaction_id,
        uow,
        'Transação distribuída rodando há ' + CAST(duration_seconds/60 AS VARCHAR) + ' minutos'
    FROM dbo.Monitor_2PC_Transactions t
    WHERE duration_seconds > (@threshold_minutes * 60)
      AND is_in_doubt = 0
      AND collected_at >= DATEADD(MINUTE, -10, GETDATE())
      AND NOT EXISTS (
          SELECT 1 FROM dbo.Monitor_2PC_Alerts a 
          WHERE a.transaction_id = t.transaction_id 
            AND a.alert_type = 'LONG_RUNNING'
            AND a.resolved_at IS NULL
      );
END
GO

-- ============================================
-- Procedure: Limpar Histórico Antigo
-- ============================================
CREATE OR ALTER PROCEDURE dbo.usp_Cleanup_2PC_History
    @retention_days INT = 30
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @cutoff_date DATETIME2 = DATEADD(DAY, -@retention_days, GETDATE());
    
    DELETE FROM dbo.Monitor_2PC_Transactions 
    WHERE collected_at < @cutoff_date;
    
    DELETE FROM dbo.Monitor_2PC_Alerts 
    WHERE created_at < @cutoff_date;
    
    DELETE FROM dbo.Monitor_2PC_DTC_Status 
    WHERE checked_at < @cutoff_date;
    
    PRINT 'Limpeza concluída. Registros anteriores a ' + CONVERT(VARCHAR, @cutoff_date, 120) + ' removidos.';
END
GO
```

---

### 4. Script SQL: Job
**Arquivo:** `database/jobs/Job_Monitor_2PC.sql`

```sql
-- ============================================
-- SQL Agent Job: Monitor 2PC
-- Executa a cada 5 minutos
-- ============================================

USE msdb;
GO

-- Criar Job
EXEC dbo.sp_add_job
    @job_name = N'WatcherDB - Monitor 2PC Transactions',
    @enabled = 1,
    @description = N'Verifica alertas de transações 2PC in-doubt e long-running',
    @category_name = N'Database Maintenance',
    @owner_login_name = N'sa';

-- Step 1: Verificar Alertas
EXEC dbo.sp_add_jobstep
    @job_name = N'WatcherDB - Monitor 2PC Transactions',
    @step_name = N'Check 2PC Alerts',
    @step_id = 1,
    @subsystem = N'TSQL',
    @command = N'EXEC WatcherDB.dbo.usp_Check_2PC_Alerts @threshold_minutes = 30;',
    @database_name = N'WatcherDB',
    @on_success_action = 2,  -- Go to next step
    @on_fail_action = 2;

-- Step 2: Cleanup (1x por dia, mas job roda a cada 5 min - procedure verifica internamente)
EXEC dbo.sp_add_jobstep
    @job_name = N'WatcherDB - Monitor 2PC Transactions',
    @step_name = N'Cleanup Old Records',
    @step_id = 2,
    @subsystem = N'TSQL',
    @command = N'
        -- Executar cleanup apenas 1x por dia (às 3h)
        IF DATEPART(HOUR, GETDATE()) = 3 AND DATEPART(MINUTE, GETDATE()) < 5
            EXEC WatcherDB.dbo.usp_Cleanup_2PC_History @retention_days = 30;
    ',
    @database_name = N'WatcherDB',
    @on_success_action = 1,  -- Quit with success
    @on_fail_action = 2;

-- Schedule: A cada 5 minutos
EXEC dbo.sp_add_jobschedule
    @job_name = N'WatcherDB - Monitor 2PC Transactions',
    @name = N'Every 5 Minutes',
    @freq_type = 4,           -- Daily
    @freq_interval = 1,
    @freq_subday_type = 4,    -- Minutes
    @freq_subday_interval = 5,
    @active_start_time = 0;

-- Associar ao servidor
EXEC dbo.sp_add_jobserver
    @job_name = N'WatcherDB - Monitor 2PC Transactions',
    @server_name = N'(local)';

PRINT 'Job criado com sucesso!';
GO
```

---

### 5. Python: Collector
**Arquivo:** `services/collector_service/collectors/distributed_transactions_collector.py`

Criar um coletor seguindo o padrão do `collectors_base.py` existente no projeto.

**Funcionalidades:**
1. Iterar por todos os servidores em `sql_servers.json`
2. Executar a query de coleta em cada servidor
3. Inserir resultados na tabela `Monitor_2PC_Transactions`
4. Verificar status do MS DTC
5. Logging apropriado

**Query de coleta a executar em cada servidor remoto (MÉTODO UNIVERSAL - Funciona em 2012-2022+):**
```sql
-- =====================================================
-- QUERY UNIVERSAL: Funciona em SQL Server 2012-2022+
-- Usa sys.dm_tran_locks (sempre disponível)
-- =====================================================
SELECT 
    @@SERVERNAME AS server_name,
    l.request_owner_guid AS uow,
    DB_NAME(l.resource_database_id) AS database_name,
    COUNT(*) AS locks_held,
    MAX(l.resource_type) AS resource_type,
    MAX(l.request_mode) AS request_mode,
    1 AS is_in_doubt,  -- Se tem lock distribuído, é in-doubt
    'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
    'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
FROM sys.dm_tran_locks l
WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
GROUP BY l.request_owner_guid, l.resource_database_id;
```

**Query ADICIONAL para estatísticas (APENAS SQL Server 2022+ / versão >= 16):**
```sql
-- =====================================================
-- QUERY ADICIONAL: Apenas SQL Server 2022+ (v16+)
-- Usa sys.dm_tran_distributed_transaction_stats
-- Detectar versão antes de executar!
-- =====================================================
DECLARE @v INT = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)), 4) AS INT);

IF @v >= 16  -- SQL 2022+ (inclui versões futuras)
BEGIN
    SELECT 
        @@SERVERNAME AS server_name,
        [open] AS open_transactions,
        in_doubt AS in_doubt_transactions,
        committed AS committed_transactions,
        aborted AS aborted_transactions
    FROM sys.dm_tran_distributed_transaction_stats;
END
```

**Query para verificar MS DTC:**
```sql
BEGIN TRY
    BEGIN DISTRIBUTED TRANSACTION;
    ROLLBACK;
    SELECT 'RUNNING' AS dtc_status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'ERROR' AS dtc_status, ERROR_MESSAGE() AS error_message;
END CATCH
```

**Intervalo de coleta:** 5 minutos (configurável no `config.yaml`)

---

## PADRÕES A SEGUIR

1. **SQL:** Seguir nomenclatura existente no projeto (prefixo `Monitor_`, `usp_`, `vw_`)
2. **Python:** Seguir o padrão do `collectors_base.py` para o novo coletor
3. **Logging:** Usar o sistema de logging já configurado
4. **Config:** Usar `config.yaml` para parâmetros configuráveis

---

## CRITÉRIOS DE QUALIDADE

- [ ] Scripts SQL executam sem erros
- [ ] Índices otimizados para consultas frequentes
- [ ] Procedure de cleanup com retenção configurável
- [ ] Job do SQL Agent com schedule correto
- [ ] Coletor Python segue padrão existente
- [ ] Tratamento de erros robusto no coletor
- [ ] Logging apropriado

---

*Prompt versão 1.2 - PARTE 1: Database + Coleta (WATCHERDB INTELLIGENCE V1)*
*Atualizado: 2026-01-28 - Queries validadas em SQL Server 2019 (v15)*
