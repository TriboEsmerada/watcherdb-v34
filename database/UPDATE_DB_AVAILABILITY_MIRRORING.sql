-- ============================================================================
-- ATUALIZAÇÃO: Adicionar suporte a Mirroring Role em DB Availability
-- ============================================================================
-- Data: 2025-12-09
-- Descrição: Adiciona coluna mirroring_role para identificar databases em mirroring
--            e ajusta a lógica para não considerar RESTORING como problema quando
--            mirroring_role = 'MIRROR' (estado normal em mirroring)
-- ============================================================================

USE [WatcherDB_Intelligence];
GO

PRINT '============================================================================';
PRINT 'ATUALIZAÇÃO: DB Availability - Suporte a Mirroring Role';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';

-- ============================================================================
-- 1. ADICIONAR COLUNA mirroring_role NA TABELA STG
-- ============================================================================

PRINT '';
PRINT '-- [1/4] Adicionando coluna Mirroring_Role na tabela STG...';
PRINT '';

IF NOT EXISTS (
    SELECT 1 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_STG') 
    AND name = 'Mirroring_Role'
)
BEGIN
    ALTER TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG
    ADD Mirroring_Role VARCHAR(32) NULL;
    
    PRINT '  [OK] Coluna Mirroring_Role adicionada na tabela STG';
END
ELSE
BEGIN
    PRINT '  [INFO] Coluna Mirroring_Role já existe na tabela STG';
END
GO

-- ============================================================================
-- 2. ADICIONAR COLUNA mirroring_role NA TABELA HIST
-- ============================================================================

PRINT '';
PRINT '-- [2/4] Adicionando coluna Mirroring_Role na tabela HIST...';
PRINT '';

IF NOT EXISTS (
    SELECT 1 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_HIST') 
    AND name = 'Mirroring_Role'
)
BEGIN
    ALTER TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_HIST
    ADD Mirroring_Role VARCHAR(32) NULL;
    
    PRINT '  [OK] Coluna Mirroring_Role adicionada na tabela HIST';
END
ELSE
BEGIN
    PRINT '  [INFO] Coluna Mirroring_Role já existe na tabela HIST';
END
GO

-- ============================================================================
-- 3. ATUALIZAR PROCEDURE DE COLETA
-- ============================================================================

PRINT '';
PRINT '-- [3/4] Atualizando procedure usp_Collect_DB_Availability...';
PRINT '';

IF OBJECT_ID('dbo.usp_Collect_DB_Availability', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_Collect_DB_Availability;
GO

CREATE PROCEDURE dbo.usp_Collect_DB_Availability
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG;

        -- Coletar disponibilidade de databases com mirroring_role
        INSERT INTO dbo.KPI_MSSQL_DB_AVAILABILITY_STG (
            Instance, [Database], [State], Is_Available,
            Recovery_Model, Mirroring_Role, Update_TS
        )
        SELECT
            @@SERVERNAME AS Instance,
            db.name AS [Database],
            db.state_desc AS [State],
            CASE WHEN db.state_desc = 'ONLINE' THEN 1 ELSE 0 END AS Is_Available,
            db.recovery_model_desc AS Recovery_Model,
            m.mirroring_role_desc AS Mirroring_Role,
            GETDATE() AS Update_TS
        FROM sys.databases db WITH(NOLOCK)
        LEFT OUTER JOIN sys.database_mirroring m WITH(NOLOCK) 
            ON db.database_id = m.database_id
        WHERE db.name NOT IN ('tempdb');

        -- Inserir dados em histórico
        INSERT INTO dbo.KPI_MSSQL_DB_AVAILABILITY_HIST (
            Instance, [Database], [State], Is_Available,
            Recovery_Model, Mirroring_Role, Update_TS
        )
        SELECT
            Instance, [Database], [State], Is_Available,
            Recovery_Model, Mirroring_Role, Update_TS
        FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG;

        PRINT '  [OK] DB Availability coletada: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linhas';
    END TRY
    BEGIN CATCH
        PRINT '  [ERRO] DB Availability: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO

PRINT '  [OK] Procedure usp_Collect_DB_Availability atualizada';
GO

-- ============================================================================
-- 4. ATUALIZAR VIEW DET_VIEW COM LÓGICA DO ORACLE
-- ============================================================================

PRINT '';
PRINT '-- [4/4] Atualizando view KPI_MSSQL_DB_AVAILABILITY_DET_VIEW...';
PRINT '';

IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
AS
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
    dbo.KPI_MSSQL_DB_AVAILABILITY_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    -- Lógica do Oracle: excluir RESTORING apenas quando mirroring_role = 'MIRROR'
    -- Para outras situações, RESTORING é considerado problema
    -- IMPORTANTE: Se Mirroring_Role for NULL e State for RESTORING, também excluir
    -- (pode ser mirroring não detectado pela coleta)
    (
        -- Sem mirroring: considerar problema se State <> 'ONLINE' ou Is_Available = 0
        -- Mas excluir RESTORING mesmo sem mirroring_role (pode ser mirroring não detectado)
        (d.Mirroring_Role IS NULL AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0) AND d.[State] <> 'RESTORING')
        -- Principal em mirroring: considerar problema se State <> 'ONLINE' ou Is_Available = 0
        OR (d.Mirroring_Role = 'PRINCIPAL' AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0))
        -- Mirror em mirroring: considerar problema se State <> 'RESTORING' ou Is_Available = 0
        -- (RESTORING é estado normal para MIRROR, então não é problema)
        OR (d.Mirroring_Role = 'MIRROR' AND (d.[State] <> 'RESTORING' OR d.Is_Available = 0))
    );
GO

PRINT '  [OK] View KPI_MSSQL_DB_AVAILABILITY_DET_VIEW atualizada';
GO

-- ============================================================================
-- 5. ATUALIZAR VIEW AGG_VIEW COM LÓGICA DO ORACLE
-- ============================================================================

PRINT '';
PRINT '-- [5/5] Atualizando view KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW...';
PRINT '';

IF OBJECT_ID('dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW;
GO

CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
AS
SELECT
    t.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    t.Total AS TotalCnt,
    ISNULL(d.Cnt, 0) AS AbnormalCnt
FROM
    (SELECT Instance, COUNT(1) AS Total
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
     GROUP BY Instance) t
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = t.Instance
    LEFT OUTER JOIN
    (SELECT Instance, COUNT(1) AS Cnt
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
     WHERE 
         -- Mesma lógica da DET_VIEW
         -- IMPORTANTE: Se Mirroring_Role for NULL e State for RESTORING, também excluir
         (
             (Mirroring_Role IS NULL AND ([State] <> 'ONLINE' OR Is_Available = 0) AND [State] <> 'RESTORING')
             OR (Mirroring_Role = 'PRINCIPAL' AND ([State] <> 'ONLINE' OR Is_Available = 0))
             OR (Mirroring_Role = 'MIRROR' AND ([State] <> 'RESTORING' OR Is_Available = 0))
         )
     GROUP BY Instance) d
      ON t.Instance = d.Instance;
GO

PRINT '  [OK] View KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW atualizada';
GO

PRINT '';
PRINT '============================================================================';
PRINT 'ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!';
PRINT '============================================================================';
PRINT 'Finalizado em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
PRINT 'PRÓXIMOS PASSOS:';
PRINT '1. Executar a procedure usp_Collect_DB_Availability para coletar dados atualizados';
PRINT '2. Verificar se as views estão retornando dados corretos';
PRINT '============================================================================';
GO

