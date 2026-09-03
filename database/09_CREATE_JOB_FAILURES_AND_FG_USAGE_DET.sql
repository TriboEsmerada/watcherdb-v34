-- ============================================================================
-- WatcherDB V3.2 — Objectos em falta detectados em 2026-04-08
-- ============================================================================
--
-- !!! DEPRECATED — DO NOT RE-RUN AS-IS !!!
-- ----------------------------------------
-- A 2026-04-08 (mesmo dia da criacao):
--   * Os 3 objectos KPI_MSSQL_JOB_FAILURES_* foram REMOVIDOS por
--     11_DROP_JOB_FAILURES_STG.sql. Razao: o bug raiz que justificava as views
--     (retries de 7s em erros permanentes) foi corrigido em
--     watcherdb/core/retry.py. As views deixaram de trazer beneficio.
--   * O KPI_MSSQL_FG_USAGE_DET_VIEW foi RECRIADO em
--     10_FIX_FG_USAGE_DET_VIEW.sql com schema unificado V3.2 + V5
--     (a versao deste ficheiro tem schema "stub" que nao serve o V5).
--
-- Se correres este ficheiro de novo, *deves* correr a seguir o
-- 10_FIX_FG_USAGE_DET_VIEW.sql para sobrepor a versao stub. E para repor o
-- estado actual (sem os 3 JOB_FAILURES_*) corres tambem o 11_DROP_*.
--
-- Mantido como historico/rollback. NAO eliminar deste directorio.
-- ============================================================================
-- Cria os objectos abaixo na BD WatcherDB_Intelligence:
--
--   1. dbo.KPI_MSSQL_JOB_FAILURES_STG          (BASE TABLE — collector target)  [REMOVIDO em 11]
--   2. dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW     (VIEW alias — para api/routers/intelligence_kpis.py)  [REMOVIDO em 11]
--   3. dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW      (VIEW alias — idem, nome alternativo legacy)  [REMOVIDO em 11]
--   4. dbo.KPI_MSSQL_FG_USAGE_DET_VIEW         (VIEW detail — para tests/integration/test_det_view.py)  [SUBSTITUIDO em 10]
--
-- Contexto:
-- ---------
-- Os 5 objectos em falta foram detectados no diagnostico das 488 tabelas dbo.*
-- contra os nomes referenciados no codigo Python. WatcherDB_Token_Blacklist foi
-- criada por separado em 06_CREATE_TOKEN_BLACKLIST.sql, ja existe.
--
-- O comportamento problematico era: o loop em api/routers/intelligence_kpis.py
-- linhas 1882-1901 tenta 3 nomes de view por ordem; se NAO existem, cada
-- tentativa gasta ~7-8s em retries do tenacity (1s+2s+4s) antes de cair para o
-- fallback "Direct" — total ~24s desperdicados por request, multiplicado por
-- requests paralelos = timeouts no frontend. Criando os objectos (mesmo vazios)
-- o loop sai em ~50ms.
--
-- Decisao arquitectonica:
-- -----------------------
-- NAO se usa o padrao Blue/Green (6 tabelas + KPI_STG_ACTIVE_TABLE) porque:
--   * JOB_FAILURES e' uma tabela pequena (<100 jobs/dia em todo o estate)
--   * Nao existe collector que saiba popular Blue/Green para job failures
--   * Adicionar a infra-estrutura blue/green sem collector seria complexidade
--     sem beneficio imediato
--
-- Usa-se em vez disso: 1 tabela fisica STG + 2 views alias por cima. Permite
-- que um collector futuro insira em JOB_FAILURES_STG sem mudar codigo.
--
-- Idempotencia:
-- -------------
-- O script e' idempotente (IF NOT EXISTS / DROP IF EXISTS). Pode ser corrido
-- multiplas vezes sem efeitos colaterais.
--
-- Permissoes:
-- -----------
-- Tem de ser corrido por uma conta com permissao de DDL em
-- WatcherDB_Intelligence (typicamente db_ddladmin ou db_owner). O user
-- 'sql_monitoring' que o WatcherDB usa em runtime so' tem datareader/datawriter.
-- Corre via SSMS ligado com a tua conta DBA.
--
-- Como rollback:
-- --------------
-- Ver bloco -- ROLLBACK no final do ficheiro (comentado por seguranca).
-- ============================================================================

USE WatcherDB_Intelligence;
GO

SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT '====================================================================';
PRINT 'WatcherDB V3.2 — Creating missing objects';
PRINT '====================================================================';
GO

-- ============================================================================
-- 1. STG TABLE — KPI_MSSQL_JOB_FAILURES_STG
-- ============================================================================
-- Schema alinhado com as colunas que api/routers/intelligence_kpis.py
-- _query_server_failed_jobs() devolve via msdb.dbo.sysjobs/sysjobhistory.
-- O frontend (templates/watcherdb_portal.html linhas 12080-12087) le:
--   Instance, job_name, step_name, run_datetime, duration_seconds, error_message
-- (status_desc e adicional, devolvido pelo collector mas usado pelo backend
-- so para classificacao — nao por colunas).
-- ============================================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE schema_id = SCHEMA_ID('dbo') AND name = 'KPI_MSSQL_JOB_FAILURES_STG'
)
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_JOB_FAILURES_STG (
        ID                  BIGINT          IDENTITY(1,1) NOT NULL,
        Instance            VARCHAR(64)     NOT NULL,
        job_name            NVARCHAR(256)   NOT NULL,
        step_name           NVARCHAR(256)   NULL,
        status_desc         VARCHAR(20)     NULL,
        run_datetime        DATETIME2(0)    NULL,
        duration_seconds    INT             NULL,
        error_message       NVARCHAR(500)   NULL,
        Job_Type            VARCHAR(20)     NULL,    -- preenchido pelo collector ou backend (Backup/Index/etc)
        Insert_TS           DATETIME2(0)    NOT NULL CONSTRAINT DF_JobFailures_InsertTS DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_KPI_MSSQL_JOB_FAILURES_STG PRIMARY KEY CLUSTERED (ID)
    );

    PRINT 'Table dbo.KPI_MSSQL_JOB_FAILURES_STG created.';
END
ELSE
    PRINT 'Table dbo.KPI_MSSQL_JOB_FAILURES_STG already exists — skipping CREATE.';
GO

-- ----------------------------------------------------------------------------
-- Indices nao-clustered para os padroes de query mais comuns:
--   * Por (Instance, run_datetime DESC) — usado para listar falhas de uma
--     instancia ordenadas pelas mais recentes (modal "jobs-failed").
--   * Por run_datetime — usado para purge antigo / rolling window de 24h.
-- ----------------------------------------------------------------------------

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.KPI_MSSQL_JOB_FAILURES_STG')
      AND name = 'IX_JobFailures_Instance_RunDt'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_JobFailures_Instance_RunDt
        ON dbo.KPI_MSSQL_JOB_FAILURES_STG (Instance, run_datetime DESC)
        INCLUDE (job_name, step_name, duration_seconds, error_message, Job_Type);
    PRINT 'Index IX_JobFailures_Instance_RunDt created.';
END
ELSE
    PRINT 'Index IX_JobFailures_Instance_RunDt already exists.';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.KPI_MSSQL_JOB_FAILURES_STG')
      AND name = 'IX_JobFailures_RunDt'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_JobFailures_RunDt
        ON dbo.KPI_MSSQL_JOB_FAILURES_STG (run_datetime);
    PRINT 'Index IX_JobFailures_RunDt created.';
END
ELSE
    PRINT 'Index IX_JobFailures_RunDt already exists.';
GO

-- ============================================================================
-- 2. AGG VIEW (primary) — KPI_MSSQL_JOB_FAILURES_AGG_VIEW
-- ============================================================================
-- E' a primeira tentativa do loop em intelligence_kpis.py:1883.
-- Devolve so falhas da ultima janela (24h por defeito), com colunas alinhadas
-- com o que o backend e o frontend esperam ler.
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW
AS
SELECT
    s.Instance,
    s.job_name,
    s.step_name,
    s.status_desc,
    s.run_datetime,
    s.duration_seconds,
    s.error_message,
    s.Job_Type,
    s.Insert_TS
FROM dbo.KPI_MSSQL_JOB_FAILURES_STG AS s WITH (NOLOCK)
WHERE s.run_datetime >= DATEADD(HOUR, -24, GETDATE());
GO

PRINT 'View dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW created.';
GO

-- ============================================================================
-- 3. AGG VIEW (alias) — KPI_MSSQL_JOBS_FAILED_AGG_VIEW
-- ============================================================================
-- Nome alternativo legacy (a 2a tentativa do loop em intelligence_kpis.py:1884).
-- Identica em estrutura — existe so' para satisfazer ambos os nomes que o
-- codigo procura. Quando o codigo for refactored para usar so um nome, este
-- pode ser apagado.
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW
AS
SELECT
    s.Instance,
    s.job_name,
    s.step_name,
    s.status_desc,
    s.run_datetime,
    s.duration_seconds,
    s.error_message,
    s.Job_Type,
    s.Insert_TS
FROM dbo.KPI_MSSQL_JOB_FAILURES_STG AS s WITH (NOLOCK)
WHERE s.run_datetime >= DATEADD(HOUR, -24, GETDATE());
GO

PRINT 'View dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW created.';
GO

-- ============================================================================
-- 4. DET VIEW — KPI_MSSQL_FG_USAGE_DET_VIEW
-- ============================================================================
-- Vista "detail" sobre KPI_MSSQL_FG_USAGE_STG (que ja existe e tem o padrao
-- Blue/Green). Segue a convencao das outras *_DET_VIEW: SELECT *, ordenado
-- pelo campo de relevancia (Percent_Used DESC).
--
-- Usado por tests/integration/test_det_view.py — nao e usado em runtime do
-- portal. As colunas vem todas de KPI_MSSQL_FG_USAGE_STG (Instance, [Database],
-- Filegroup, Total_MB, Used_MB, Free_MB, Percent_Used, Max_Size_MB,
-- Growth_Type, Update_TS).
-- ============================================================================

IF OBJECT_ID('dbo.KPI_MSSQL_FG_USAGE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_FG_USAGE_DET_VIEW
AS
SELECT
    Instance,
    [Database],
    Filegroup,
    Total_MB,
    Used_MB,
    Free_MB,
    Percent_Used,
    Max_Size_MB,
    Growth_Type,
    Update_TS
FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK);
-- Nota: ORDER BY nao e' permitido em views sem TOP. Quem consumir esta view
-- deve aplicar ORDER BY Percent_Used DESC na sua query.
GO

PRINT 'View dbo.KPI_MSSQL_FG_USAGE_DET_VIEW created.';
GO

-- ============================================================================
-- 5. PERMISSOES (GRANTS) para sql_monitoring
-- ============================================================================
-- O user 'sql_monitoring' e' quem o WatcherDB usa em runtime para ler/escrever
-- a Intelligence DB. Tem que ter:
--   * SELECT em ambas as views (para o loop em intelligence_kpis.py)
--   * SELECT em FG_USAGE_DET_VIEW (para tests, e por consistencia)
--   * SELECT/INSERT/UPDATE/DELETE na STG fisica (para um collector futuro)
--
-- Nota: estes grants assumem que o user 'sql_monitoring' ja existe e ja' tem
-- pelo menos db_datareader. O GRANT explicito por objecto e seguro mesmo
-- quando o role-level grant ja cobre — nao falha, apenas reforca.
-- ============================================================================

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'sql_monitoring' AND type IN ('S','U'))
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.KPI_MSSQL_JOB_FAILURES_STG       TO sql_monitoring;
    GRANT SELECT                          ON dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW TO sql_monitoring;
    GRANT SELECT                          ON dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW  TO sql_monitoring;
    GRANT SELECT                          ON dbo.KPI_MSSQL_FG_USAGE_DET_VIEW     TO sql_monitoring;
    PRINT 'Grants applied to sql_monitoring.';
END
ELSE
    PRINT 'WARNING: user "sql_monitoring" nao existe nesta BD — grants nao aplicados.';
GO

-- ============================================================================
-- 6. VERIFICACAO POST-DEPLOY
-- ============================================================================
-- Listar os objectos criados e contar linhas (deve ser 0 inicialmente).
-- ============================================================================

PRINT '====================================================================';
PRINT 'Post-deploy verification:';
PRINT '====================================================================';

SELECT
    name,
    type_desc,
    create_date
FROM sys.objects
WHERE name IN (
    'KPI_MSSQL_JOB_FAILURES_STG',
    'KPI_MSSQL_JOB_FAILURES_AGG_VIEW',
    'KPI_MSSQL_JOBS_FAILED_AGG_VIEW',
    'KPI_MSSQL_FG_USAGE_DET_VIEW'
)
ORDER BY name;

SELECT
    'KPI_MSSQL_JOB_FAILURES_STG'        AS object_name,
    COUNT(*)                            AS row_count
FROM dbo.KPI_MSSQL_JOB_FAILURES_STG WITH (NOLOCK)
UNION ALL
SELECT
    'KPI_MSSQL_FG_USAGE_DET_VIEW',
    COUNT(*)
FROM dbo.KPI_MSSQL_FG_USAGE_DET_VIEW WITH (NOLOCK);
GO

PRINT '====================================================================';
PRINT 'Done. Os 4 objectos estao criados e os grants aplicados.';
PRINT '====================================================================';
GO

-- ============================================================================
-- ROLLBACK (so' executar manualmente se for preciso desfazer)
-- ============================================================================
-- DROP VIEW IF EXISTS dbo.KPI_MSSQL_FG_USAGE_DET_VIEW;
-- DROP VIEW IF EXISTS dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW;
-- DROP VIEW IF EXISTS dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW;
-- DROP TABLE IF EXISTS dbo.KPI_MSSQL_JOB_FAILURES_STG;
-- GO
