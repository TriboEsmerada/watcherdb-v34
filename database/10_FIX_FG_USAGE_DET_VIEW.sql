-- ============================================================================
-- WatcherDB — Adaptar KPI_MSSQL_FG_USAGE_DET_VIEW para schema unificado V5+V3.2
-- ============================================================================
-- ORIGEM:
-- -------
-- Este ficheiro e' COPIA EXACTA do DDL versionado em
--   WATCHERDB_V5/database/10_ADAPT_FG_USAGE_DET_VIEW.sql
-- A BD WatcherDB_Intelligence em SQLHDSTST505\I01 e' partilhada entre
-- V5 e V3.2 — so' pode existir UMA definicao desta view. Sempre que mudar
-- num lado, replicar manualmente no outro ate' termos um shared_lib/.
--
-- Contexto:
-- ---------
-- Esta view existia com 10 colunas (Instance, Database, Filegroup, Total_MB,
-- Used_MB, Free_MB, Percent_Used, Max_Size_MB, Growth_Type, Update_TS) — schema
-- 1:1 com a base table KPI_MSSQL_FG_USAGE_STG.
--
-- Problema: o V5 (services/report_service.py:322-331) consome esta view
-- esperando colunas que NAO existiam:
--   * Current_MB    (rename de Total_MB)
--   * [Used%]       (rename de Percent_Used)
--   * State         (calculada — CRITICAL/WARNING/OK por threshold)
--   * Env           (vem de JOIN com KPI_MSSQL_INST_ENVS)
--
-- Solucao escolhida (em vez de criar uma view nova ou refactorizar Python):
-- adaptar a view existente para expor AMBOS os schemas em simultaneo. Os
-- consumidores legacy (Percent_Used, Total_MB) continuam a funcionar; os
-- consumidores novos (V5 com Used%, Current_MB, State, Env) passam a funcionar.
-- A view fica como single source of truth para filegroup usage com severidade.
--
-- Consumidores conhecidos a 2026-04-08:
-- -------------------------------------
-- 1. WATCHERDB_V5/services/report_service.py:322 — relatorio (runtime, executado
--    sob demanda via /api/reports/* ou pelo scheduler). Ja' espera o schema novo.
-- 2. WATCHERDB_V3.2/tests/integration/test_det_view.py — test integration
--    (apenas Instance, [Database], Filegroup, Percent_Used). Continua a
--    funcionar porque mantemos os nomes legacy.
-- 3. WATCHERDB_V3.2/config/dashboard_kpis_queries.sql — queries documentadas
--    que ja' usam ORDER BY [Used%] DESC. Confirma que o schema unificado e' a
--    convencao desejada original.
--
-- Thresholds de State alinhados com os defaults do WatcherDB (90/80):
--   * Percent_Used >= 90  -> 'CRITICAL'
--   * Percent_Used >= 80  -> 'WARNING'
--   * Percent_Used IS NULL ou tudo o resto -> 'OK'
--
-- Idempotente: pode ser corrido N vezes sem efeitos colaterais.
--
-- Substitui:
-- ----------
-- Substitui a versao "stub" da view criada em
--   09_CREATE_JOB_FAILURES_AND_FG_USAGE_DET.sql
-- (que era apenas SELECT * FROM KPI_MSSQL_FG_USAGE_STG, sem Env/State/aliases).
-- ============================================================================

USE WatcherDB_Intelligence;
GO

SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT '====================================================================';
PRINT 'Adapting dbo.KPI_MSSQL_FG_USAGE_DET_VIEW (unified schema)';
PRINT '====================================================================';
GO

-- Drop+create — view nao tem dependencias indexed nem schemabinding
IF OBJECT_ID('dbo.KPI_MSSQL_FG_USAGE_DET_VIEW', 'V') IS NOT NULL
BEGIN
    DROP VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW;
    PRINT 'Existing view dropped.';
END
GO

CREATE VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
AS
SELECT
    s.Instance,
    -- Env vem da tabela de inventario; se nao houver match, usa 'Undefined'
    ISNULL(e.Env, 'Undefined')                          AS Env,
    s.[Database],
    s.Filegroup,
    -- Schema legacy (V3.2 test, retro-compat)
    s.Total_MB,
    s.Used_MB,
    s.Free_MB,
    s.Percent_Used,
    s.Max_Size_MB,
    s.Growth_Type,
    -- Aliases novos para o V5 (sem refactor Python)
    s.Total_MB                                          AS Current_MB,
    s.Percent_Used                                      AS [Used%],
    -- Severity calculada (V5 reports)
    CASE
        WHEN s.Percent_Used >= 90 THEN 'CRITICAL'
        WHEN s.Percent_Used >= 80 THEN 'WARNING'
        ELSE 'OK'
    END                                                  AS State,
    s.Update_TS
FROM dbo.KPI_MSSQL_FG_USAGE_STG AS s WITH (NOLOCK)
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
    ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(s.Instance)));
GO

PRINT 'View dbo.KPI_MSSQL_FG_USAGE_DET_VIEW recreated with unified schema.';
GO

-- ============================================================================
-- Permissoes — re-aplicar GRANT SELECT para sql_monitoring (DROP/CREATE limpa)
-- ============================================================================
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'sql_monitoring' AND type IN ('S','U'))
BEGIN
    GRANT SELECT ON dbo.KPI_MSSQL_FG_USAGE_DET_VIEW TO sql_monitoring;
    PRINT 'Grant SELECT applied to sql_monitoring.';
END
ELSE
    PRINT 'WARNING: user "sql_monitoring" nao existe — grant nao aplicado.';
GO

-- ============================================================================
-- Verificacao post-deploy
-- ============================================================================
PRINT '====================================================================';
PRINT 'Post-deploy verification:';
PRINT '====================================================================';

-- 1. Listar todas as colunas da view (deve ter 14 colunas)
SELECT
    ORDINAL_POSITION,
    COLUMN_NAME,
    DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'KPI_MSSQL_FG_USAGE_DET_VIEW'
ORDER BY ORDINAL_POSITION;

-- 2. Test V3.2-style (legacy columns) — tem que voltar pelo menos uma row
SELECT TOP 3 Instance, [Database], Filegroup, Percent_Used
FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
ORDER BY Percent_Used DESC;

-- 3. Test V5-style (new columns + State + Env)
SELECT TOP 3 Instance, Env, [Database], Filegroup,
       Used_MB, Current_MB, [Used%], State
FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
WHERE State IN ('CRITICAL', 'WARNING')
ORDER BY [Used%] DESC;

PRINT '====================================================================';
PRINT 'Done. View esta a expor schema unificado V5 + V3.2.';
PRINT '====================================================================';
GO

-- ============================================================================
-- ROLLBACK (so executar se for preciso reverter para o schema legacy puro)
-- ============================================================================
-- IF OBJECT_ID('dbo.KPI_MSSQL_FG_USAGE_DET_VIEW', 'V') IS NOT NULL
--     DROP VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW;
-- GO
-- CREATE VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
-- AS
-- SELECT Instance, [Database], Filegroup, Total_MB, Used_MB, Free_MB,
--        Percent_Used, Max_Size_MB, Growth_Type, Update_TS
-- FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK);
-- GO
-- GRANT SELECT ON dbo.KPI_MSSQL_FG_USAGE_DET_VIEW TO sql_monitoring;
-- GO
