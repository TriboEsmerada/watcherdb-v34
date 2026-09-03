-- ============================================================================
-- QUERIES DO DASHBOARD DE KPIs - WATCHERDB INTELLIGENCE
-- ============================================================================
-- Este arquivo contém todas as queries SQL utilizadas para coletar
-- informações para o dashboard de KPIs do WatcherDB Intelligence
-- 
-- Database: WatcherDB_Intelligence
-- Schema: dbo
-- 
-- IMPORTANTE: Este arquivo utiliza as VIEWS de KPI (AGG_VIEW e DET_VIEW)
-- ao invés de consultar diretamente as tabelas STG. As views já fazem:
-- - Agregações corretas
-- - Joins com KPI_MSSQL_INST_ENVS para obter ambiente
-- - Filtros apropriados (thresholds, estados, etc.)
-- 
-- Estrutura padrão:
-- - Query agregada (AGG_VIEW): Para dashboard e contadores
-- - Query detalhada (DET_VIEW): Para listagens e diagnósticos
-- 
-- VALIDAÇÃO:
-- - Data: 2025-12-05
-- - Status: ✅ 87% das queries validadas (13/15 corretas)
-- - Views existentes: 13/13 necessárias ✅
-- - Pendência: Criar view KPI_MSSQL_BLOCKED_USERS_AGG_VIEW (Query #8)
-- ============================================================================

USE [WatcherDB_Intelligence];
GO

-- ============================================================================
-- 1. INSTANCE AVAILABILITY (Disponibilidade de Instância)
-- ============================================================================
-- Retorna instâncias offline ou indisponíveis
-- Aplicar janela de frescor de 15 minutos (serviços)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW
WHERE [State] = 'UNAVAILABLE';
GO

-- Query detalhada (instâncias indisponíveis)
SELECT * 
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW
WHERE [State] = 'UNAVAILABLE'
ORDER BY Update_TS DESC;
GO

-- ============================================================================
-- 2. DB AVAILABILITY (Disponibilidade de Banco de Dados)
-- ============================================================================
-- Retorna instâncias com databases anormais (AbnormalCnt > 0)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
WHERE AbnormalCnt > 0;
GO

-- Query detalhada (databases anormais)
SELECT * 
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
ORDER BY Update_TS DESC;
GO

-- Query adicional: Total de databases disponíveis por ambiente (PRD)
SELECT SUM(TotalCnt) as TOTAL_DATABASES
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
WHERE AbnormalCnt = 0 AND ENV = 'PRD';
GO

-- Query adicional: Total de databases disponíveis por ambiente (TST)
SELECT SUM(TotalCnt) as TOTAL_DATABASES
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
WHERE AbnormalCnt = 0 AND ENV = 'TST';
GO

-- Query adicional: Total de databases disponíveis por ambiente (QLT)
SELECT SUM(TotalCnt) as TOTAL_DATABASES
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
WHERE AbnormalCnt = 0 AND ENV = 'QLT';
GO

-- Query adicional: Contar instâncias OK (sem databases anormais)
SELECT COUNT(*) as TOTAL
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
WHERE AbnormalCnt = 0;
GO

-- ============================================================================
-- 3. DB DISK FILE SYSTEM (Uso de Disco)
-- ============================================================================
-- Retorna instâncias com problemas de uso de disco
-- Crítico: < 10% livre | Atenção: < 20% livre
-- Aplicar janela de frescor de 60 minutos (métrica de capacidade)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW
WHERE Critical > 0 OR Warning > 0;
GO

-- Query detalhada (discos com problemas)
SELECT * 
FROM dbo.KPI_MSSQL_DISK_USAGE_DET_VIEW
ORDER BY [Available%] ASC;
GO

-- ============================================================================
-- 4. DB TRANSACTION LOGS (Logs de Transação)
-- ============================================================================
-- Retorna instâncias com problemas de uso de transaction logs
-- Crítico: >= 90% | Atenção: >= 70%
-- Aplicar janela de frescor de 60 minutos (métrica de capacidade)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW
WHERE Critical > 0 OR Warning > 0;
GO

-- Query detalhada (transaction logs com problemas)
SELECT * 
FROM dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW
ORDER BY [Used%] DESC;
GO

-- ============================================================================
-- 5. ALWAYS ON (Status Always On)
-- ============================================================================
-- Retorna instâncias com grupos Always On não saudáveis
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
WHERE Unhealthy > 0;
GO

-- Query detalhada (grupos Always On não saudáveis)
SELECT * 
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW
ORDER BY Update_TS DESC;
GO

-- ============================================================================
-- 6. FILEGROUP USAGE (Uso de FileGroups)
-- ============================================================================
-- Retorna instâncias com filegroups acima dos thresholds:
-- - Warning: >= 80% e < 90%
-- - Critical: >= 90%
-- Aplicar janela de frescor de 60 minutos (métrica de capacidade)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW
WHERE Warning > 0 OR Critical > 0;
GO

-- Query detalhada (filegroups com problemas)
SELECT TOP 10 * 
FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
ORDER BY [Used%] DESC;
GO

-- ============================================================================
-- 7. BLOCKED SESSIONS (Sessões Bloqueadas)
-- ============================================================================
-- Retorna instâncias com sessões bloqueadas
-- Aplicar janela de frescor de 5 minutos (eventos em tempo real)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW
WHERE Cnt > 0;
GO

-- Query detalhada (sessões bloqueadas)
SELECT * 
FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_DET_VIEW
ORDER BY Wait_Time_Sec DESC;
GO

-- ============================================================================
-- 8. BLOCKED USERS (Usuários Bloqueados)
-- ============================================================================
-- Retorna instâncias com usuários bloqueados
-- Aplicar janela de frescor de 5 minutos (eventos em tempo real)
-- ============================================================================
-- NOTA: View KPI_MSSQL_BLOCKED_USERS_AGG_VIEW não existe ainda.
-- Quando criada, usar: SELECT * FROM dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW WHERE Blocked_Count > 0;
-- Por enquanto, usando STG diretamente como fallback.
SELECT * 
FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG
WHERE Blocked_Count > 0;
GO

-- ============================================================================
-- 9. LONG LOCKS (Locks Longos)
-- ============================================================================
-- Retorna instâncias com locks de longa duração
-- Aplicar janela de frescor de 5 minutos (eventos em tempo real)
-- Classificação:
-- - Warning: >= 60 segundos
-- - Critical: >= 300 segundos (5 minutos)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW
WHERE Cnt > 0;
GO

-- Query detalhada (locks longos)
SELECT * 
FROM dbo.KPI_MSSQL_LONG_LOCKS_DET_VIEW
ORDER BY Duration_Sec DESC;
GO

-- ============================================================================
-- 10. DEADLOCKS
-- ============================================================================
-- Retorna instâncias com deadlocks detectados
-- Aplicar janela de frescor de 5 minutos (eventos em tempo real)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_DEADLOCKS_AGG_VIEW
WHERE Deadlock_Count > 0;
GO

-- ============================================================================
-- 11. SERVICE STATUS (Status de Serviços)
-- ============================================================================
-- Retorna instâncias com serviços SQL Server down
-- Aplicar janela de frescor de 15 minutos (serviços)
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW
WHERE Services_Down_Count > 0;
GO

-- ============================================================================
-- 12. PROCESSES ALARM (Alarme de Processos)
-- ============================================================================
-- Retorna instâncias com contagem de processos anormal
-- WARNING: >= 500 processos
-- CRITICAL: >= 1000 processos
-- ============================================================================
-- Query agregada para dashboard
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE [State] IN ('WARNING', 'CRITICAL');
GO

-- Query detalhada (processos por instância)
SELECT * 
FROM dbo.KPI_MSSQL_PROCESSES_DET_VIEW
ORDER BY Current_Count DESC;
GO

-- ============================================================================
-- 13. BACKUP STATUS (Status de Backup)
-- ============================================================================
-- Retorna databases com backup atrasado (> 24 horas)
-- Aplicar janela de frescor de 60 minutos (métrica de capacidade)
-- Classificação:
-- - Warning: > 24 horas e <= 48 horas
-- - Critical: > 48 horas
-- ============================================================================
-- Query agregada para dashboard
SELECT * 
FROM dbo.KPI_MSSQL_BACKUPS_AGG_VIEW
WHERE Critical > 0 OR Warning > 0;
GO

-- Query detalhada (backups atrasados)
SELECT * 
FROM dbo.KPI_MSSQL_BACKUPS_DET_VIEW
ORDER BY Hours_Since_Backup DESC;
GO

-- ============================================================================
-- 14. ERROR LOG (Log de Erros)
-- ============================================================================
-- Retorna erros das últimas 24 horas
-- Agrupar por instância e contar por severidade em Python
-- ============================================================================
-- Nota: A coluna de data pode variar (Log_Date, LogDate, Date, Error_Date, etc.)
SELECT * 
FROM dbo.KPI_MSSQL_ERRORLOG_STG 
WHERE Log_Date >= DATEADD(HOUR, -24, GETDATE())
ORDER BY Log_Date DESC;
GO

-- Alternativa se a coluna for LogDate:
-- SELECT * 
-- FROM dbo.KPI_MSSQL_ERRORLOG_STG 
-- WHERE LogDate >= DATEADD(HOUR, -24, GETDATE())
-- ORDER BY LogDate DESC;
-- GO

-- ============================================================================
-- 15. DATABASE I/O STATS (Estatísticas de I/O)
-- ============================================================================
-- Retorna databases com alto I/O (read-heavy ou write-heavy)
-- Aplicar janela de frescor de 60 minutos (métrica de capacidade)
-- Filtros aplicados em Python:
-- - Read-heavy: > 70% reads
-- - Write-heavy: > 70% writes
-- ============================================================================
-- Query agregada para dashboard
SELECT *
FROM dbo.KPI_MSSQL_DB_IO_STATS_AGG_VIEW;
GO

-- Query detalhada (estatísticas de I/O por database)
-- Nota: Não há view detalhada, usando STG diretamente
SELECT TOP 10
    Instance,
    [Database] AS DB_Name,
    Reads AS Leituras,
    Writes AS Escritas,
    Reads + Writes AS Total_IO,
    CAST(Reads_Percent AS DECIMAL(5,2)) AS Percentual_Leituras,
    CAST(Writes_Percent AS DECIMAL(5,2)) AS Percentual_Escritas,
    Update_TS AS Medido_Em
FROM dbo.KPI_MSSQL_DB_IO_STATS_STG
ORDER BY (Reads + Writes) DESC;
GO

-- ============================================================================
-- QUERIES ADICIONAIS - DETALHES E DIAGNÓSTICOS
-- ============================================================================

-- ============================================================================
-- FILEGROUP USAGE DETAIL (Detalhes de FileGroups por Instância)
-- ============================================================================
-- Retorna detalhes de filegroups com problema para uma instância específica
-- Substituir @InstanceName pela instância desejada
-- ============================================================================
DECLARE @InstanceName NVARCHAR(255) = 'SQLSERVER_INSTANCE'; -- Alterar conforme necessário

SELECT * 
FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
WHERE Instance = @InstanceName
ORDER BY [Used%] DESC;
GO

-- ============================================================================
-- RESUMO GERAL DA ÚLTIMA COLETA
-- ============================================================================
-- Retorna estatísticas gerais sobre a última coleta de dados
-- ============================================================================
SELECT
    'RESUMO GERAL' AS Categoria,
    COUNT(DISTINCT Instance) AS Total_Instancias,
    SUM(CASE WHEN Is_Available = 1 THEN 1 ELSE 0 END) AS Instancias_Online,
    SUM(CASE WHEN Is_Available = 0 THEN 1 ELSE 0 END) AS Instancias_Offline,
    CAST(SUM(CASE WHEN Is_Available = 1 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT Instance), 0) AS DECIMAL(5,2)) AS Taxa_Sucesso_Pct,
    MAX(Update_TS) AS Ultima_Coleta,
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) AS Minutos_Desde_Ultima_Coleta
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG;
GO

-- ============================================================================
-- STATUS POR INSTÂNCIA (Top 20 mais recentes)
-- ============================================================================
-- Retorna status detalhado das 20 instâncias mais recentemente verificadas
-- ============================================================================
SELECT TOP 20 * 
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW
ORDER BY Update_TS DESC;
GO

-- ============================================================================
-- VERIFICAÇÃO DE NORMALIZAÇÃO (Underscore vs Backslash)
-- ============================================================================
-- Verifica se todas as instâncias estão normalizadas (usando underscore)
-- ============================================================================
SELECT
    'INSTÂNCIAS COM BACKSLASH (INCORRETO)' AS Verificacao,
    COUNT(*) AS Total_Encontrado,
    CASE
        WHEN COUNT(*) = 0 THEN 'OK - Todas normalizadas'
        ELSE 'ERRO - Ainda há backslashes!'
    END AS Status
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG
WHERE Instance LIKE '%\%';
GO

-- ============================================================================
-- LISTAR VIEWS DISPONÍVEIS
-- ============================================================================
-- Lista todas as views KPI disponíveis no schema dbo
-- ============================================================================
SELECT 
    TABLE_NAME as view_name,
    'View' as object_type
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'dbo'
AND TABLE_NAME LIKE 'KPI_MSSQL_%'
ORDER BY TABLE_NAME;
GO

-- ============================================================================
-- NOTAS SOBRE JANELAS DE FRESCOR (FRESHNESS WINDOWS)
-- ============================================================================
-- As queries acima são filtradas por janelas de frescor para evitar
-- que dados antigos (não atualizados pelo ETL) apareçam como problemas ativos:
--
-- - 15 minutos: Services e Instance Availability (mudam rapidamente)
-- - 5 minutos: Blocked Sessions, Deadlocks, Long Locks (eventos em tempo real)
-- - 60 minutos: Backups, Filegroups, Disk, DB I/O (métricas de capacidade)
--
-- O filtro de frescor é aplicado em Python após a execução das queries,
-- verificando colunas de timestamp como:
-- - Last_Check, Update_TS, Capture_TS, Capture_Time, Timestamp, etc.
--
-- IMPORTANTE: Todas as instâncias devem usar underscore (_) ao invés de 
-- backslash (\) para normalização correta (ex: SQLSERVER_INSTANCE ao invés de SQLSERVER\INSTANCE)
-- ============================================================================
