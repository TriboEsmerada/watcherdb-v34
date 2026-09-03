-- =====================================================
-- QUERIES PARA VERIFICAR COLETAS DO WATCHERDB
-- =====================================================
-- Coluna de timestamp: Update_TS (datetime2)
-- Coluna de instância: Instance
-- =====================================================

-- =====================================================
-- 1. VERIFICAR ÚLTIMA COLETA DE CADA TABELA STG
-- =====================================================
SELECT
    'KPI_MSSQL_ALWAYSON_STATUS_STG' as Tabela,
    COUNT(*) as Registros,
    MAX(Update_TS) as Ultima_Coleta,
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) as Min_Atras,
    CASE
        WHEN DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) <= 5 THEN 'OK'
        WHEN DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) <= 30 THEN 'AVISO'
        ELSE 'CRITICO'
    END as Status
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH(NOLOCK)

UNION ALL

SELECT
    'KPI_MSSQL_DEADLOCKS_STG',
    COUNT(*),
    MAX(Update_TS),
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()),
    CASE
        WHEN DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) <= 5 THEN 'OK'
        WHEN DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) <= 30 THEN 'AVISO'
        ELSE 'CRITICO'
    END
FROM dbo.KPI_MSSQL_DEADLOCKS_STG WITH(NOLOCK)

UNION ALL

SELECT
    'KPI_MSSQL_PROCESSES_STG',
    COUNT(*),
    MAX(Update_TS),
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()),
    CASE
        WHEN DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) <= 5 THEN 'OK'
        WHEN DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) <= 30 THEN 'AVISO'
        ELSE 'CRITICO'
    END
FROM dbo.KPI_MSSQL_PROCESSES_STG WITH(NOLOCK)

ORDER BY Min_Atras DESC;

-- =====================================================
-- 2. COLETAS POR INSTÂNCIA (últimas 2 horas)
-- =====================================================
SELECT
    Instance,
    COUNT(*) as Total_Registros,
    MAX(Update_TS) as Ultima_Coleta,
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) as Min_Atras
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH(NOLOCK)
WHERE Update_TS >= DATEADD(HOUR, -2, GETDATE())
GROUP BY Instance
ORDER BY Ultima_Coleta DESC;

-- =====================================================
-- 3. GAPS DE COLETA - Instâncias sem coleta há mais de 30 min
-- =====================================================
SELECT
    Instance,
    MAX(Update_TS) as Ultima_Coleta,
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) as Min_Atras
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH(NOLOCK)
GROUP BY Instance
HAVING DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) > 30
ORDER BY Min_Atras DESC;

-- =====================================================
-- 4. HISTÓRICO DOS JOBS WATCHERDB (últimas 24h)
-- =====================================================
SELECT TOP 30
    j.name as Job_Name,
    CONVERT(VARCHAR(10),
        CAST(CAST(h.run_date AS VARCHAR(8)) AS DATE), 103) + ' ' +
        STUFF(STUFF(RIGHT('000000' + CAST(h.run_time AS VARCHAR(6)), 6), 3, 0, ':'), 6, 0, ':') as Execucao,
    CASE h.run_status
        WHEN 0 THEN 'FALHOU'
        WHEN 1 THEN 'OK'
        WHEN 2 THEN 'Retry'
        WHEN 3 THEN 'Cancelado'
        WHEN 4 THEN 'Em Progresso'
    END as Status,
    h.run_duration as Duracao_HHMMSS,
    LEFT(h.message, 100) as Mensagem
FROM msdb.dbo.sysjobhistory h WITH(NOLOCK)
INNER JOIN msdb.dbo.sysjobs j WITH(NOLOCK) ON h.job_id = j.job_id
WHERE j.name LIKE '%WatcherDB%'
  AND h.step_id = 0
  AND h.run_date >= CONVERT(INT, CONVERT(VARCHAR(8), DATEADD(DAY, -1, GETDATE()), 112))
ORDER BY h.run_date DESC, h.run_time DESC;

-- =====================================================
-- 5. CONTAGEM DE REGISTROS POR HORA (últimas 24h)
-- =====================================================
SELECT
    CONVERT(DATE, Update_TS) as Data,
    DATEPART(HOUR, Update_TS) as Hora,
    COUNT(*) as Total_Registros,
    COUNT(DISTINCT Instance) as Instancias
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH(NOLOCK)
WHERE Update_TS >= DATEADD(HOUR, -24, GETDATE())
GROUP BY CONVERT(DATE, Update_TS), DATEPART(HOUR, Update_TS)
ORDER BY Data DESC, Hora DESC;

-- =====================================================
-- 6. MONITOR EM TEMPO REAL - Últimos 10 registros
-- =====================================================
SELECT 'Hora Atual: ' + CONVERT(VARCHAR(20), GETDATE(), 120) as Info;

SELECT TOP 10
    Instance,
    [Database],
    Update_TS as Coleta,
    DATEDIFF(SECOND, Update_TS, GETDATE()) as Seg_Atras
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH(NOLOCK)
ORDER BY Update_TS DESC;

-- =====================================================
-- 7. VERIFICAR TODAS AS TABELAS STG EXISTENTES
-- =====================================================
SELECT
    t.name as Tabela,
    p.rows as Total_Linhas,
    CAST(SUM(a.total_pages) * 8 / 1024.0 AS DECIMAL(10,2)) as Tamanho_MB
FROM sys.tables t
INNER JOIN sys.indexes i ON t.object_id = i.object_id
INNER JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
WHERE t.name LIKE 'KPI_MSSQL%STG'
GROUP BY t.name, p.rows
ORDER BY t.name;

-- =====================================================
-- 8. DEADLOCKS RECENTES
-- =====================================================
SELECT TOP 10
    Instance,
    Deadlock_Id,
    Deadlock_Time,
    Database_Name,
    Object_Name,
    Update_TS
FROM dbo.KPI_MSSQL_DEADLOCKS_STG WITH(NOLOCK)
ORDER BY Deadlock_Time DESC;

-- =====================================================
-- 9. PROCESSOS ATIVOS - Últimos coletados
-- =====================================================
SELECT TOP 20
    Instance,
    Session_Id,
    [Status],
    Command,
    [Database],
    [User],
    CPU_Time_MS,
    Wait_Type,
    Update_TS
FROM dbo.KPI_MSSQL_PROCESSES_STG WITH(NOLOCK)
ORDER BY Update_TS DESC;

-- =====================================================
-- 10. VERIFICAR INVENTÁRIO DE INSTÂNCIAS
-- =====================================================
-- Quais instâncias estão cadastradas para coleta?
SELECT * FROM dbo.KPI_MSSQL_INST_ENVS WITH(NOLOCK);

-- =====================================================
-- 11. VERIFICAR SE HÁ DADOS ALWAYS ON EM OUTRAS TABELAS
-- =====================================================
-- Verificar na view agregada
SELECT
    'KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW' as Fonte,
    COUNT(*) as Total
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WITH(NOLOCK);

-- =====================================================
-- 12. LISTAR TODAS AS TABELAS/VIEWS DE ALWAYS ON
-- =====================================================
SELECT name as Objeto, type_desc as Tipo
FROM sys.objects
WHERE name LIKE '%ALWAYSON%' OR name LIKE '%AlwaysOn%'
ORDER BY type_desc, name;

-- =====================================================
-- 13. VERIFICAR CONFIGURAÇÃO DO JOB DE COLETA ALWAYSON
-- =====================================================
SELECT
    j.name as Job_Name,
    s.step_id,
    s.step_name,
    s.subsystem,
    LEFT(s.command, 500) as Comando
FROM msdb.dbo.sysjobs j
INNER JOIN msdb.dbo.sysjobsteps s ON j.job_id = s.job_id
WHERE j.name LIKE '%AlwaysOn%' OR j.name LIKE '%Collect%AlwaysOn%'
ORDER BY j.name, s.step_id;
