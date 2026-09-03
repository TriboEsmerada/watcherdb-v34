-- ============================================================================
-- CRIAR TABELAS PARA ESPACO NAO ALOCADO (UNALLOCATED SPACE)
-- ============================================================================
-- Projeto: WATCHERDB_DEV
-- Objetivo: Armazenar informacoes sobre espaco fisico dos discos vs particoes
-- Isso permite responder: "Tenho espaco nao alocado disponivel para expandir?"
--
-- Data: 2026-01-20
-- ============================================================================

USE [WatcherDB]
GO

-- ============================================================================
-- 1. TABELA: DISCOS FISICOS (Physical Disks)
-- ============================================================================
-- Armazena informacoes dos discos fisicos (como aparecem no Disk Manager)

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_OS_DISK_PHYSICAL_STG')
BEGIN
    CREATE TABLE dbo.KPI_OS_DISK_PHYSICAL_STG (
        ID                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        Instance            NVARCHAR(256) NOT NULL,         -- Nome do servidor (ServerID_Formatted)
        Disk_Number         INT NOT NULL,                   -- Numero do disco (0, 1, 2...)
        Disk_Model          NVARCHAR(256),                  -- Modelo do disco
        Disk_Size_GB        DECIMAL(18,2) NOT NULL,         -- Tamanho total do disco fisico
        Partition_Style     NVARCHAR(20),                   -- GPT ou MBR
        Is_System_Disk      BIT DEFAULT 0,                  -- Disco do sistema?
        Is_Boot_Disk        BIT DEFAULT 0,                  -- Disco de boot?
        Health_Status       NVARCHAR(50),                   -- Healthy, Warning, etc.
        Operational_Status  NVARCHAR(50),                   -- Online, Offline, etc.
        Bus_Type            NVARCHAR(50),                   -- SAS, SATA, NVMe, etc.
        Media_Type          NVARCHAR(50),                   -- SSD, HDD, etc.
        Collection_Time     DATETIME2 NOT NULL DEFAULT GETDATE(),
        Collection_Method   NVARCHAR(20) DEFAULT 'WMI',     -- WMI, WinRM, PowerShell
        CONSTRAINT UQ_DISK_PHYSICAL_STG UNIQUE (Instance, Disk_Number, Collection_Time)
    );

    PRINT 'Tabela KPI_OS_DISK_PHYSICAL_STG criada';
END
GO


-- ============================================================================
-- 2. TABELA: PARTICOES (Volumes/Drives)
-- ============================================================================
-- Armazena informacoes das particoes (letras de unidade)

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_OS_DISK_PARTITION_STG')
BEGIN
    CREATE TABLE dbo.KPI_OS_DISK_PARTITION_STG (
        ID                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        Instance            NVARCHAR(256) NOT NULL,         -- Nome do servidor
        Disk_Number         INT NOT NULL,                   -- Disco fisico onde esta
        Partition_Number    INT NOT NULL,                   -- Numero da particao
        Drive_Letter        CHAR(1),                        -- C, D, E, etc (pode ser NULL)
        Volume_Label        NVARCHAR(128),                  -- Nome do volume
        Partition_Size_GB   DECIMAL(18,2) NOT NULL,         -- Tamanho da particao
        File_System         NVARCHAR(20),                   -- NTFS, ReFS, etc.
        Is_Active           BIT DEFAULT 0,                  -- Particao ativa?
        Is_Boot             BIT DEFAULT 0,                  -- Particao de boot?
        Partition_Type      NVARCHAR(100),                  -- Basic, Recovery, EFI, etc.
        Collection_Time     DATETIME2 NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_DISK_PARTITION_STG UNIQUE (Instance, Disk_Number, Partition_Number, Collection_Time)
    );

    PRINT 'Tabela KPI_OS_DISK_PARTITION_STG criada';
END
GO


-- ============================================================================
-- 3. TABELA: ESPACO NAO ALOCADO (Unallocated Space)
-- ============================================================================
-- Armazena o espaco nao alocado calculado

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_OS_DISK_UNALLOCATED_STG')
BEGIN
    CREATE TABLE dbo.KPI_OS_DISK_UNALLOCATED_STG (
        ID                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        Instance            NVARCHAR(256) NOT NULL,         -- Nome do servidor
        Disk_Number         INT NOT NULL,                   -- Numero do disco
        Disk_Size_GB        DECIMAL(18,2) NOT NULL,         -- Tamanho total do disco
        Allocated_GB        DECIMAL(18,2) NOT NULL,         -- Soma das particoes
        Unallocated_GB      DECIMAL(18,2) NOT NULL,         -- Espaco nao alocado
        Percent_Unallocated DECIMAL(5,2),                   -- % nao alocado
        Can_Expand          BIT DEFAULT 0,                  -- Ha espaco para expandir?
        Adjacent_Drive      CHAR(1),                        -- Drive que pode expandir (mais proximo)
        Collection_Time     DATETIME2 NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_DISK_UNALLOCATED_STG UNIQUE (Instance, Disk_Number, Collection_Time)
    );

    PRINT 'Tabela KPI_OS_DISK_UNALLOCATED_STG criada';
END
GO


-- ============================================================================
-- 4. TABELA HISTORICA (para tendencia)
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_OS_DISK_UNALLOCATED_HIST')
BEGIN
    CREATE TABLE dbo.KPI_OS_DISK_UNALLOCATED_HIST (
        ID                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        Instance            NVARCHAR(256) NOT NULL,
        Disk_Number         INT NOT NULL,
        Disk_Size_GB        DECIMAL(18,2) NOT NULL,
        Allocated_GB        DECIMAL(18,2) NOT NULL,
        Unallocated_GB      DECIMAL(18,2) NOT NULL,
        Percent_Unallocated DECIMAL(5,2),
        Collect_Date        DATE NOT NULL,
        Collect_TS          DATETIME2 NOT NULL,
        Insert_TS           DATETIME2 DEFAULT GETDATE(),
        CONSTRAINT UQ_DISK_UNALLOCATED_HIST UNIQUE (Instance, Disk_Number, Collect_Date)
    );

    PRINT 'Tabela KPI_OS_DISK_UNALLOCATED_HIST criada';
END
GO


-- ============================================================================
-- 5. VIEW: POTENCIAL DE EXPANSAO POR SERVIDOR
-- ============================================================================
-- Consolida informacoes para responder: "Posso expandir o disco?"

IF EXISTS (SELECT 1 FROM sys.views WHERE name = 'VW_DISK_EXPANSION_POTENTIAL')
    DROP VIEW dbo.VW_DISK_EXPANSION_POTENTIAL;
GO

CREATE VIEW dbo.VW_DISK_EXPANSION_POTENTIAL
AS
WITH LatestCollection AS (
    SELECT Instance, Disk_Number, MAX(Collection_Time) AS Max_Collection
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
    GROUP BY Instance, Disk_Number
)
SELECT
    u.Instance AS Servidor,
    CASE
        WHEN u.Instance LIKE '%PRD%' OR u.Instance LIKE '%PROD%' THEN 'PRD'
        WHEN u.Instance LIKE '%QLT%' THEN 'QLT'
        WHEN u.Instance LIKE '%QA%' OR u.Instance LIKE '%HML%' THEN 'QA'
        WHEN u.Instance LIKE '%TST%' OR u.Instance LIKE '%DEV%' THEN 'TST'
        ELSE 'Outros'
    END AS Ambiente,
    u.Disk_Number AS Disco,
    p.Disk_Model AS Modelo_Disco,
    p.Media_Type AS Tipo_Midia,
    u.Disk_Size_GB AS Tamanho_Disco_GB,
    u.Allocated_GB AS Alocado_GB,
    u.Unallocated_GB AS Nao_Alocado_GB,
    u.Percent_Unallocated AS Percent_Nao_Alocado,
    u.Can_Expand AS Pode_Expandir,
    u.Adjacent_Drive AS Drive_Adjacente,
    p.Health_Status AS Saude_Disco,
    u.Collection_Time AS Ultima_Coleta
FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
INNER JOIN LatestCollection lc
    ON u.Instance = lc.Instance
    AND u.Disk_Number = lc.Disk_Number
    AND u.Collection_Time = lc.Max_Collection
LEFT JOIN dbo.KPI_OS_DISK_PHYSICAL_STG p
    ON u.Instance = p.Instance
    AND u.Disk_Number = p.Disk_Number
    AND p.Collection_Time = (
        SELECT MAX(Collection_Time)
        FROM dbo.KPI_OS_DISK_PHYSICAL_STG p2
        WHERE p2.Instance = p.Instance AND p2.Disk_Number = p.Disk_Number
    );
GO

PRINT 'View VW_DISK_EXPANSION_POTENTIAL criada';
GO


-- ============================================================================
-- 6. VIEW: RESUMO DE ESPACO NAO ALOCADO POR SERVIDOR
-- ============================================================================

IF EXISTS (SELECT 1 FROM sys.views WHERE name = 'VW_DISK_UNALLOCATED_SUMMARY')
    DROP VIEW dbo.VW_DISK_UNALLOCATED_SUMMARY;
GO

CREATE VIEW dbo.VW_DISK_UNALLOCATED_SUMMARY
AS
WITH LatestCollection AS (
    SELECT Instance, MAX(Collection_Time) AS Max_Collection
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
    GROUP BY Instance
)
SELECT
    u.Instance AS Servidor,
    CASE
        WHEN u.Instance LIKE '%PRD%' OR u.Instance LIKE '%PROD%' THEN 'PRD'
        WHEN u.Instance LIKE '%QLT%' THEN 'QLT'
        WHEN u.Instance LIKE '%QA%' OR u.Instance LIKE '%HML%' THEN 'QA'
        WHEN u.Instance LIKE '%TST%' OR u.Instance LIKE '%DEV%' THEN 'TST'
        ELSE 'Outros'
    END AS Ambiente,
    COUNT(DISTINCT u.Disk_Number) AS Qtd_Discos,
    SUM(u.Disk_Size_GB) AS Total_Discos_GB,
    SUM(u.Allocated_GB) AS Total_Alocado_GB,
    SUM(u.Unallocated_GB) AS Total_Nao_Alocado_GB,
    CAST(SUM(u.Unallocated_GB) * 100.0 / NULLIF(SUM(u.Disk_Size_GB), 0) AS DECIMAL(5,2)) AS Percent_Nao_Alocado,
    SUM(CASE WHEN u.Can_Expand = 1 THEN 1 ELSE 0 END) AS Discos_Expandiveis,
    MAX(u.Collection_Time) AS Ultima_Coleta
FROM dbo.KPI_OS_DISK_UNALLOCATED_STG u
INNER JOIN LatestCollection lc
    ON u.Instance = lc.Instance
    AND u.Collection_Time = lc.Max_Collection
GROUP BY u.Instance;
GO

PRINT 'View VW_DISK_UNALLOCATED_SUMMARY criada';
GO


-- ============================================================================
-- 7. VIEW: OPORTUNIDADES DE EXPANSAO (para Dashboard)
-- ============================================================================

IF EXISTS (SELECT 1 FROM sys.views WHERE name = 'VW_DISK_EXPANSION_OPPORTUNITIES')
    DROP VIEW dbo.VW_DISK_EXPANSION_OPPORTUNITIES;
GO

CREATE VIEW dbo.VW_DISK_EXPANSION_OPPORTUNITIES
AS
SELECT
    Servidor,
    Ambiente,
    Disco,
    Modelo_Disco,
    Tipo_Midia,
    Tamanho_Disco_GB,
    Nao_Alocado_GB,
    Percent_Nao_Alocado,
    Drive_Adjacente,
    Pode_Expandir,
    Ultima_Coleta,
    -- Classificacao de oportunidade
    CASE
        WHEN Nao_Alocado_GB >= 100 THEN 'Alta'
        WHEN Nao_Alocado_GB >= 50 THEN 'Media'
        WHEN Nao_Alocado_GB >= 10 THEN 'Baixa'
        ELSE 'Minima'
    END AS Prioridade_Expansao
FROM dbo.VW_DISK_EXPANSION_POTENTIAL
WHERE Can_Expand = 1
  AND Nao_Alocado_GB >= 1;  -- Pelo menos 1 GB
GO

PRINT 'View VW_DISK_EXPANSION_OPPORTUNITIES criada';
GO


-- ============================================================================
-- 8. INDICES PARA PERFORMANCE
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DISK_UNALLOCATED_Instance_Time')
    CREATE NONCLUSTERED INDEX IX_DISK_UNALLOCATED_Instance_Time
    ON dbo.KPI_OS_DISK_UNALLOCATED_STG (Instance, Collection_Time DESC)
    INCLUDE (Disk_Number, Unallocated_GB, Can_Expand);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DISK_PHYSICAL_Instance')
    CREATE NONCLUSTERED INDEX IX_DISK_PHYSICAL_Instance
    ON dbo.KPI_OS_DISK_PHYSICAL_STG (Instance, Disk_Number, Collection_Time DESC);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DISK_PARTITION_Instance')
    CREATE NONCLUSTERED INDEX IX_DISK_PARTITION_Instance
    ON dbo.KPI_OS_DISK_PARTITION_STG (Instance, Disk_Number, Drive_Letter);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DISK_UNALLOCATED_HIST_Instance')
    CREATE NONCLUSTERED INDEX IX_DISK_UNALLOCATED_HIST_Instance
    ON dbo.KPI_OS_DISK_UNALLOCATED_HIST (Instance, Collect_Date DESC);
GO


-- ============================================================================
-- 9. PROCEDURE: ARQUIVAR DADOS PARA HISTORICO
-- ============================================================================

IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'SP_ARCHIVE_DISK_UNALLOCATED')
    DROP PROCEDURE dbo.SP_ARCHIVE_DISK_UNALLOCATED;
GO

CREATE PROCEDURE dbo.SP_ARCHIVE_DISK_UNALLOCATED
AS
BEGIN
    SET NOCOUNT ON;

    -- Insere dados do dia atual no historico (1 registro por servidor/disco/dia)
    INSERT INTO dbo.KPI_OS_DISK_UNALLOCATED_HIST
        (Instance, Disk_Number, Disk_Size_GB, Allocated_GB, Unallocated_GB,
         Percent_Unallocated, Collect_Date, Collect_TS)
    SELECT
        Instance,
        Disk_Number,
        AVG(Disk_Size_GB),
        AVG(Allocated_GB),
        AVG(Unallocated_GB),
        AVG(Percent_Unallocated),
        CAST(Collection_Time AS DATE),
        MAX(Collection_Time)
    FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
    WHERE CAST(Collection_Time AS DATE) = CAST(GETDATE() AS DATE)
      AND NOT EXISTS (
          SELECT 1 FROM dbo.KPI_OS_DISK_UNALLOCATED_HIST h
          WHERE h.Instance = KPI_OS_DISK_UNALLOCATED_STG.Instance
            AND h.Disk_Number = KPI_OS_DISK_UNALLOCATED_STG.Disk_Number
            AND h.Collect_Date = CAST(GETDATE() AS DATE)
      )
    GROUP BY Instance, Disk_Number, CAST(Collection_Time AS DATE);

    -- Remove dados staging mais antigos que 7 dias
    DELETE FROM dbo.KPI_OS_DISK_UNALLOCATED_STG
    WHERE Collection_Time < DATEADD(DAY, -7, GETDATE());

    DELETE FROM dbo.KPI_OS_DISK_PHYSICAL_STG
    WHERE Collection_Time < DATEADD(DAY, -7, GETDATE());

    DELETE FROM dbo.KPI_OS_DISK_PARTITION_STG
    WHERE Collection_Time < DATEADD(DAY, -7, GETDATE());

    PRINT 'Arquivamento de dados de disco concluido';
END
GO

PRINT 'Procedure SP_ARCHIVE_DISK_UNALLOCATED criada';
GO


-- ============================================================================
-- RESUMO
-- ============================================================================
PRINT '============================================';
PRINT 'TABELAS E VIEWS CRIADAS COM SUCESSO';
PRINT '============================================';
PRINT '';
PRINT 'Tabelas criadas:';
PRINT '  - KPI_OS_DISK_PHYSICAL_STG (discos fisicos)';
PRINT '  - KPI_OS_DISK_PARTITION_STG (particoes)';
PRINT '  - KPI_OS_DISK_UNALLOCATED_STG (espaco nao alocado)';
PRINT '  - KPI_OS_DISK_UNALLOCATED_HIST (historico)';
PRINT '';
PRINT 'Views criadas:';
PRINT '  - VW_DISK_EXPANSION_POTENTIAL (potencial de expansao)';
PRINT '  - VW_DISK_UNALLOCATED_SUMMARY (resumo por servidor)';
PRINT '  - VW_DISK_EXPANSION_OPPORTUNITIES (oportunidades)';
PRINT '';
PRINT 'Procedures:';
PRINT '  - SP_ARCHIVE_DISK_UNALLOCATED (arquivamento diario)';
PRINT '';
PRINT 'Proximo passo: Configure a coleta via API ou coletor Python';
GO
