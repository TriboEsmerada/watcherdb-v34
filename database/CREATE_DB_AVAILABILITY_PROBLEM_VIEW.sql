-- ============================================================================
-- CRIACAO: KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW
-- ============================================================================
-- Data: 2026-01-27
-- Descricao: Cria a view que o codigo Python espera para mostrar databases
--            com problemas REAIS, excluindo:
--            - Mirrors em estado RESTORING (comportamento normal)
--            - Databases RESTORING sem mirroring_role (pode ser mirroring nao detectado)
--            - AlwaysOn Secondary databases saudaveis
-- ============================================================================

USE [WatcherDB_Intelligence];
GO

PRINT '============================================================================';
PRINT 'CRIACAO: KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';

-- ============================================================================
-- 1. VERIFICAR SE COLUNA Mirroring_Role EXISTE
-- ============================================================================

PRINT '-- [1/2] Verificando coluna Mirroring_Role na tabela STG...';

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_STG')
    AND name = 'Mirroring_Role'
)
BEGIN
    PRINT '  [AVISO] Coluna Mirroring_Role NAO existe - adicionando...';
    ALTER TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG
    ADD Mirroring_Role VARCHAR(32) NULL;
    PRINT '  [OK] Coluna Mirroring_Role adicionada';
END
ELSE
BEGIN
    PRINT '  [OK] Coluna Mirroring_Role ja existe';
END
GO

-- ============================================================================
-- 2. CRIAR VIEW KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW
-- ============================================================================

PRINT '';
PRINT '-- [2/2] Criando view KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW...';
PRINT '';

IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW', 'V') IS NOT NULL
BEGIN
    DROP VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW;
    PRINT '  [INFO] View antiga removida';
END
GO

CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW
AS
/*
    View que retorna APENAS databases com problemas REAIS.

    REGRAS DE EXCLUSAO (NAO SAO PROBLEMAS):
    1. Mirror em RESTORING -> Estado normal para mirror secundario (mirroring tradicional)
    2. Database RESTORING sem Mirroring_Role E sem AlwaysOn -> Pode ser mirroring nao detectado

    REGRAS DE INCLUSAO (SAO PROBLEMAS):
    1. Principal em mirroring que NAO esta ONLINE
    2. Mirror que NAO esta RESTORING (deveria estar)
    3. Database sem mirroring que NAO esta ONLINE (exceto RESTORING sem AlwaysOn)
    4. Database em AlwaysOn que esta RESTORING (pode indicar problema de sincronizacao)
    5. Qualquer database com Is_Available = 0 (exceto mirror em RESTORING)

    NOTA SOBRE ALWAYSON:
    - Em AlwaysOn, databases secundarios NAO devem ficar em RESTORING
    - O estado normal e SYNCHRONIZED ou SYNCHRONIZING
    - RESTORING em AlwaysOn indica restore pendente ou problema de sync
*/
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.[Database],
    d.[State],
    d.Is_Available,
    d.Recovery_Model,
    d.Mirroring_Role,
    d.Update_TS
FROM
    dbo.KPI_MSSQL_DB_AVAILABILITY_STG d WITH (NOLOCK)
    LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
      ON e.Instance = d.Instance
WHERE
    -- IMPORTANTE: Logica de problemas REAIS
    --
    -- CASO 1: Database como MIRROR em mirroring tradicional
    --   - NAO e problema se State = 'RESTORING' (comportamento normal)
    --   - Problema se State <> 'RESTORING' (deveria estar RESTORING)
    (d.Mirroring_Role = 'MIRROR'
        AND d.[State] <> 'RESTORING'
    )
    --
    -- CASO 2: Database como PRINCIPAL em mirroring
    --   - Problema se State <> 'ONLINE' ou Is_Available = 0
    --   - Principal DEVE estar ONLINE
    OR (d.Mirroring_Role = 'PRINCIPAL'
        AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0)
    )
    --
    -- CASO 3: Database sem mirroring (Mirroring_Role IS NULL)
    --   - Verificar se faz parte de AlwaysOn
    OR (d.Mirroring_Role IS NULL
        AND (
            -- 3a: Se NAO esta ONLINE e NAO esta RESTORING -> Problema
            (d.[State] NOT IN ('ONLINE', 'RESTORING'))
            -- 3b: Se Is_Available = 0 -> Problema
            OR (d.Is_Available = 0 AND d.[State] <> 'RESTORING')
            -- 3c: Se esta RESTORING E faz parte de AlwaysOn -> Problema (sync issue)
            -- Nota: A tabela ALWAYSON_STATUS_STG tem colunas [Database] e Instance
            OR (d.[State] = 'RESTORING'
                AND EXISTS (
                    SELECT 1
                    FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG ag WITH (NOLOCK)
                    WHERE ag.[Database] = d.[Database]
                      AND ag.Instance = d.Instance
                )
            )
        )
    );
GO

PRINT '  [OK] View KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW criada';
GO

-- ============================================================================
-- 3. VALIDAR CRIACAO
-- ============================================================================

PRINT '';
PRINT '-- Validando view criada...';

-- Contar registros
DECLARE @cnt INT;
SELECT @cnt = COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW WITH (NOLOCK);
PRINT '  Registros na PROBLEM_VIEW: ' + CAST(@cnt AS VARCHAR(10));

-- Contar total de databases
DECLARE @total INT;
SELECT @total = COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK);
PRINT '  Total de databases na STG: ' + CAST(@total AS VARCHAR(10));

-- Contar RESTORING excluidos
DECLARE @restoring INT;
SELECT @restoring = COUNT(*)
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
WHERE [State] = 'RESTORING';
PRINT '  Databases em RESTORING (excluidos): ' + CAST(@restoring AS VARCHAR(10));

PRINT '';
PRINT '============================================================================';
PRINT 'CRIACAO CONCLUIDA COM SUCESSO!';
PRINT '============================================================================';
PRINT 'Finalizado em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
PRINT 'A view KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW agora:';
PRINT '  - Exclui mirrors em RESTORING (comportamento normal)';
PRINT '  - Exclui databases RESTORING sem mirroring (pode ser mirroring)';
PRINT '  - Mostra apenas problemas REAIS';
PRINT '';
PRINT 'PROXIMO PASSO: Reinicie o servico WatcherDB para ver as mudancas';
PRINT '============================================================================';
GO
