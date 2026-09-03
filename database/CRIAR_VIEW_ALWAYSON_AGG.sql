-- ============================================================================
-- SCRIPT: CRIAR VIEW KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
-- ============================================================================
-- Execute este script no banco WatcherDB_Intelligence para criar a view
-- que está faltando e causando o erro:
-- "Invalid object name 'dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW'"
--
-- IMPORTANTE: Esta versão corrige o problema de strings vazias que causavam
-- falsos positivos (ex: Sec_Synch_Health = '' era contado como problema)
-- ============================================================================
-- Database: WatcherDB_Intelligence
-- Schema: dbo
-- Data: 2025-12-29
-- ============================================================================

USE WatcherDB_Intelligence;
GO

-- Remover view antiga se existir
IF OBJECT_ID('dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW;
GO

-- Criar view agregada do AlwaysOn Status
-- CORRIGIDO: Exclui strings vazias para evitar falsos positivos
CREATE VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
AS
SELECT
    t.AgName,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(f.N, 0) AS Unhealthy,
    t.N AS Total,
    ISNULL(pr.Problem_Reasons, '') AS Problem_Reasons,
    t.Update_TS
FROM
    -- Total de replicas por AG
    (
        SELECT AgName, COUNT(1) AS N, MAX(Update_TS) AS Update_TS
        FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
        GROUP BY AgName
    ) AS t

    -- Ambiente do AG
    LEFT OUTER JOIN
    (
        SELECT
            stg.AgName,
            MAX(env.Env) AS Env
        FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG AS stg WITH (NOLOCK)
        LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS AS env ON env.Instance = stg.Instance
        GROUP BY stg.AgName
    ) AS e ON e.AgName = t.AgName

    -- Contagem de unhealthy (CORRIGIDO: exclui strings vazias)
    LEFT OUTER JOIN
    (
        SELECT
            AgName,
            COUNT(1) AS N
        FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
        WHERE (
            -- Health nao saudavel - EXCLUI strings vazias
            (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
            OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')

            -- OU replicas suspensas
            OR Pri_Is_Suspended = 1
            OR Sec_Is_Suspended = 1

            -- OU estados de sincronizacao problematicos - EXCLUI strings vazias e UNKNOWN
            OR (Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '')
                AND Pri_Synch_State IS NOT NULL)
            OR (Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '')
                AND Sec_Synch_State IS NOT NULL)
        )
        GROUP BY AgName
    ) AS f ON f.AgName = t.AgName

    -- Razoes dos problemas
    LEFT OUTER JOIN
    (
        SELECT
            AgName,
            STRING_AGG(Problem_Reason, '; ') WITHIN GROUP (ORDER BY Problem_Reason) AS Problem_Reasons
        FROM (
            SELECT DISTINCT AgName, Problem_Reason
            FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
            WHERE Problem_Reason IS NOT NULL AND Problem_Reason <> ''
        ) AS sub
        GROUP BY AgName
    ) AS pr ON pr.AgName = t.AgName;
GO

-- Verificar se a view foi criada
IF OBJECT_ID('dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW', 'V') IS NOT NULL
    PRINT 'VIEW dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW criada com sucesso!'
ELSE
    PRINT 'ERRO: Falha ao criar a view!'
GO

-- Teste: verificar dados
SELECT 'Dados da view:' AS Info;
SELECT * FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WITH (NOLOCK);

-- Teste: contar unhealthy
SELECT 'Total Unhealthy:' AS Info, COUNT(*) AS Unhealthy_AGs
FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Unhealthy > 0;
GO

-- ============================================================================
-- NOTAS DE CORRECAO:
-- ============================================================================
-- Problema anterior: Strings vazias ('') eram tratadas como problemas porque:
--   '' <> 'HEALTHY' retorna TRUE
--
-- Correcao aplicada: Adicionado AND column <> '' em todas as condicoes
-- que verificam valores de Health e State
-- ============================================================================
