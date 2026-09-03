-- ============================================================================
-- WatcherDB V3.2 — DROP de KPI_MSSQL_JOB_FAILURES_* (deprecated)
-- ============================================================================
-- Remove os 3 objectos criados em 09_CREATE_JOB_FAILURES_AND_FG_USAGE_DET.sql:
--
--   1. dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW    (VIEW alias)
--   2. dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW     (VIEW alias)
--   3. dbo.KPI_MSSQL_JOB_FAILURES_STG         (BASE TABLE)
--
-- NAO toca em dbo.KPI_MSSQL_FG_USAGE_DET_VIEW — essa esta em uso runtime pelo
-- V5 (services/report_service.py) e foi adaptada em 10_FIX_FG_USAGE_DET_VIEW.sql.
--
-- Razao:
-- ------
-- Os 3 objectos foram criados como workaround para um problema de latencia em
-- api/routers/intelligence_kpis.py:1882-1901, onde um loop tenta 3 nomes de
-- view por ordem. Quando nenhum existia, cada falha custava ~7s em retries
-- do tenacity (1+2+4 backoff). Total ~21s desperdicados por request.
--
-- O bug raiz foi corrigido em watcherdb/core/retry.py com um predicate
-- _is_transient_db_error que distingue erros transientes (network drop,
-- deadlock) de erros permanentes (Invalid object name, Login failed). Erros
-- permanentes deixaram de ter retry — caem em <50ms.
--
-- Com o fix do retry, as 3 views deixaram de trazer beneficio significativo:
--   * Mantendo as views vazias: ~50ms (3 round-trips a devolver [])
--   * Removendo as views:       ~30ms (3 erros que caem rapido)
--
-- A diferenca de 20ms e' negligivel face ao request total. Em troca evitam-se:
--   * Falsa promessa de schema "pronto para collector" que ninguem implementou
--   * Divergencia arquitectonica vs V5 (que faz query directa a msdb em runtime)
--   * Confusao para quem ler o schema da BD e ver "KPI_MSSQL_JOB_FAILURES_STG"
--     a sugerir que existe um collector
--
-- Quando um collector real for implementado no futuro, devera criar a sua
-- propria tabela com o schema que vai realmente popular — nao tentar adaptar
-- um schema adivinhado meses antes.
--
-- Idempotencia:
-- -------------
-- Idempotente (IF EXISTS). Pode ser corrido N vezes sem efeitos colaterais.
--
-- Permissoes:
-- -----------
-- sql_monitoring e' db_owner desta BD, pode correr este script ele proprio.
--
-- Rollback:
-- ---------
-- Para reverter, correr de novo 09_CREATE_JOB_FAILURES_AND_FG_USAGE_DET.sql.
-- Atencao: o 09_*.sql tambem cria KPI_MSSQL_FG_USAGE_DET_VIEW, mas a versao
-- legacy (sem schema unificado V5). Se reverter o 09 depois do 10 ja' ter
-- corrido, vais sobrepor a view actual com a versao stub. Para evitar isso,
-- corre o 10_FIX_FG_USAGE_DET_VIEW.sql logo a seguir ao 09 quando for rollback.
-- ============================================================================

USE WatcherDB_Intelligence;
GO

SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT '====================================================================';
PRINT 'Dropping KPI_MSSQL_JOB_FAILURES_* (deprecated workaround)';
PRINT '====================================================================';
GO

-- ----------------------------------------------------------------------------
-- 1. Drop das 2 views alias
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW', 'V') IS NOT NULL
BEGIN
    DROP VIEW dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW;
    PRINT 'Dropped view dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW.';
END
ELSE
    PRINT 'View dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW does not exist — skipping.';
GO

IF OBJECT_ID('dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW', 'V') IS NOT NULL
BEGIN
    DROP VIEW dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW;
    PRINT 'Dropped view dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW.';
END
ELSE
    PRINT 'View dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW does not exist — skipping.';
GO

-- ----------------------------------------------------------------------------
-- 2. Drop da base table (e respectivos indices, automatico no DROP TABLE)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('dbo.KPI_MSSQL_JOB_FAILURES_STG', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.KPI_MSSQL_JOB_FAILURES_STG;
    PRINT 'Dropped table dbo.KPI_MSSQL_JOB_FAILURES_STG (e indices PK + IX_*).';
END
ELSE
    PRINT 'Table dbo.KPI_MSSQL_JOB_FAILURES_STG does not exist — skipping.';
GO

-- ============================================================================
-- VERIFICACAO POST-DEPLOY
-- ============================================================================
PRINT '====================================================================';
PRINT 'Post-deploy verification (esperado: 0 rows)';
PRINT '====================================================================';

SELECT
    name,
    type_desc,
    create_date
FROM sys.objects
WHERE name IN (
    'KPI_MSSQL_JOB_FAILURES_STG',
    'KPI_MSSQL_JOB_FAILURES_AGG_VIEW',
    'KPI_MSSQL_JOBS_FAILED_AGG_VIEW'
)
ORDER BY name;

PRINT '====================================================================';
PRINT 'Done. Os 3 objectos KPI_MSSQL_JOB_FAILURES_* foram removidos.';
PRINT 'O loop em api/routers/intelligence_kpis.py:1882 vai continuar a falhar';
PRINT 'os 3 nomes (~30ms total agora que o retry esta corrigido) e cair para';
PRINT 'o fallback Direct (_query_jobs_from_servers).';
PRINT '====================================================================';
GO

-- ============================================================================
-- ROLLBACK (se for preciso re-criar os objectos)
-- ============================================================================
-- Correr de novo:
--     database/09_CREATE_JOB_FAILURES_AND_FG_USAGE_DET.sql
-- Seguido de:
--     database/10_FIX_FG_USAGE_DET_VIEW.sql
-- (na ordem certa para o 10 sobrepor a versao stub do FG_USAGE_DET_VIEW que o
-- 09 tambem cria).
