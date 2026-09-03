
-- =====================================================================
-- SECTION: COLLECTION HISTORY (Historico de Coletas)
-- =====================================================================
-- Tabelas e views para rastreamento de cada execucao de coleta Python
-- Permite analise de tendencias e identificacao de problemas recorrentes
-- Adicionado em: 2025-12-18
-- =====================================================================

USE [WatcherDB]
GO

PRINT '';
PRINT '========================================';
PRINT 'Collection History Tables';
PRINT '========================================';
PRINT '';

-- ============================================================================
-- TABELA PRINCIPAL: kpi.Collection_History
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'kpi.Collection_History') AND type = 'U')
BEGIN
    CREATE TABLE kpi.Collection_History (
        Collection_ID           INT IDENTITY(1,1) PRIMARY KEY,
        Collection_Start        DATETIME2 NOT NULL,
        Collection_End          DATETIME2 NULL,
        Duration_Seconds        INT NULL,
        Mode                    VARCHAR(20) NOT NULL,

        Servers_Configured      INT NOT NULL DEFAULT 0,
        Servers_Online          INT NOT NULL DEFAULT 0,
        Servers_Skipped         INT NOT NULL DEFAULT 0,
        Servers_With_Errors     INT NOT NULL DEFAULT 0,
        Success_Rate_Pct        DECIMAL(5,2) NULL,

        Servers_Ping_Failed     INT NOT NULL DEFAULT 0,
        Servers_SQL_Down        INT NOT NULL DEFAULT 0,
        Servers_Auth_Error      INT NOT NULL DEFAULT 0,
        Servers_Timeout         INT NOT NULL DEFAULT 0,
        Servers_Query_Error     INT NOT NULL DEFAULT 0,

        Total_KPIs_Collected    INT NOT NULL DEFAULT 0,
        Total_Rows_Inserted     INT NOT NULL DEFAULT 0,
        KPIs_With_Errors        INT NOT NULL DEFAULT 0,

        -- Campos de Blue-Green SWAP (adicionados em 2025-12-19)
        SWAP_Success_Count      INT NOT NULL DEFAULT 0,
        SWAP_Failed_Count       INT NOT NULL DEFAULT 0,
        SWAP_Skipped            BIT NOT NULL DEFAULT 0,

        Avg_Connection_Time_MS  FLOAT NULL,
        Max_Connection_Time_MS  FLOAT NULL,
        Avg_Query_Time_MS       FLOAT NULL,
        Max_Query_Time_MS       FLOAT NULL,
        Total_Queries_Executed  INT NOT NULL DEFAULT 0,

        Servers_Failed_JSON     NVARCHAR(MAX) NULL,
        Queries_Failed_JSON     NVARCHAR(MAX) NULL,
        Warnings_JSON           NVARCHAR(MAX) NULL,
        Summary_Text            NVARCHAR(MAX) NULL,

        Hostname                VARCHAR(255) NULL,
        Script_Version          VARCHAR(50) NULL,
        Python_Version          VARCHAR(50) NULL,
        Created_At              DATETIME2 NOT NULL DEFAULT GETDATE(),

        CONSTRAINT CK_Collection_Mode CHECK (Mode IN ('all', 'kpi-only', 'kpi-fast', 'full-no-kpi', 'locks-only', 'alwayson-only', 'kpi-prd', 'kpi-qa', 'kpi-tst'))
    );
    PRINT '  Created: kpi.Collection_History';
END
ELSE
    PRINT '  Exists: kpi.Collection_History';
GO

-- Indices
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_History_Start')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_History_Start
    ON kpi.Collection_History (Collection_Start DESC)
    INCLUDE (Mode, Servers_Configured, Servers_Online, Servers_Skipped, Success_Rate_Pct);
    PRINT '  Created: IX_Collection_History_Start';
END
GO

-- ============================================================================
-- TABELA DE DETALHES POR SERVIDOR
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'kpi.Collection_Server_Details') AND type = 'U')
BEGIN
    CREATE TABLE kpi.Collection_Server_Details (
        Detail_ID               INT IDENTITY(1,1) PRIMARY KEY,
        Collection_ID           INT NOT NULL,
        Server_ID               VARCHAR(255) NOT NULL,
        Status                  VARCHAR(20) NOT NULL,
        Skip_Reason             VARCHAR(50) NULL,
        Error_Message           NVARCHAR(MAX) NULL,
        Connection_Time_MS      FLOAT NULL,
        Total_Query_Time_MS     FLOAT NULL,
        Queries_Executed        INT NOT NULL DEFAULT 0,
        Queries_Failed          INT NOT NULL DEFAULT 0,
        Rows_Collected          INT NOT NULL DEFAULT 0,
        KPIs_Collected          VARCHAR(500) NULL,
        KPIs_Failed             VARCHAR(500) NULL,
        Services_Checked        BIT NOT NULL DEFAULT 0,
        Services_Down_Count     INT NOT NULL DEFAULT 0,
        Services_Down_List      VARCHAR(500) NULL,
        Start_Time              DATETIME2 NULL,
        End_Time                DATETIME2 NULL,
        CONSTRAINT FK_Collection_Server_Details_History
            FOREIGN KEY (Collection_ID)
            REFERENCES kpi.Collection_History(Collection_ID)
            ON DELETE CASCADE
    );
    PRINT '  Created: kpi.Collection_Server_Details';
END
ELSE
    PRINT '  Exists: kpi.Collection_Server_Details';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Collection_Server_Details_ServerID')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Collection_Server_Details_ServerID
    ON kpi.Collection_Server_Details (Server_ID, Collection_ID DESC);
    PRINT '  Created: IX_Collection_Server_Details_ServerID';
END
GO

-- ============================================================================
-- VIEWS DE ANALISE
-- ============================================================================

IF OBJECT_ID('monitoring.VW_Collection_Summary', 'V') IS NOT NULL
    DROP VIEW monitoring.VW_Collection_Summary;
GO

CREATE VIEW monitoring.VW_Collection_Summary AS
SELECT TOP 100
    Collection_ID, Collection_Start, Collection_End, Duration_Seconds, Mode,
    Servers_Configured, Servers_Online, Servers_Skipped, Servers_With_Errors, Success_Rate_Pct,
    Servers_Ping_Failed, Servers_SQL_Down,
    SWAP_Success_Count, SWAP_Failed_Count,
    Total_KPIs_Collected, Total_Rows_Inserted, Avg_Query_Time_MS, Max_Query_Time_MS,
    CASE
        WHEN Servers_Skipped > 0 OR Servers_With_Errors > 0 THEN 'WARNING'
        WHEN SWAP_Failed_Count > 0 THEN 'WARNING'
        WHEN Success_Rate_Pct < 95 THEN 'WARNING'
        ELSE 'OK'
    END AS Health_Status
FROM kpi.Collection_History
ORDER BY Collection_Start DESC;
GO

PRINT '  Created: monitoring.VW_Collection_Summary';
GO

IF OBJECT_ID('monitoring.VW_Problematic_Servers', 'V') IS NOT NULL
    DROP VIEW monitoring.VW_Problematic_Servers;
GO

CREATE VIEW monitoring.VW_Problematic_Servers AS
SELECT
    d.Server_ID,
    COUNT(*) AS Total_Collections,
    SUM(CASE WHEN d.Status = 'success' THEN 1 ELSE 0 END) AS Success_Count,
    SUM(CASE WHEN d.Status = 'skipped' THEN 1 ELSE 0 END) AS Skipped_Count,
    SUM(CASE WHEN d.Status = 'error' THEN 1 ELSE 0 END) AS Error_Count,
    SUM(CASE WHEN d.Status = 'partial' THEN 1 ELSE 0 END) AS Partial_Count,
    CAST(SUM(CASE WHEN d.Status = 'success' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS DECIMAL(5,2)) AS Success_Rate_Pct,
    AVG(d.Connection_Time_MS) AS Avg_Connection_MS,
    MAX(d.Connection_Time_MS) AS Max_Connection_MS,
    MAX(d.Skip_Reason) AS Skip_Reason,
    MAX(h.Collection_Start) AS Last_Collection
FROM kpi.Collection_Server_Details d
INNER JOIN kpi.Collection_History h ON d.Collection_ID = h.Collection_ID
WHERE h.Collection_Start >= DATEADD(DAY, -7, GETDATE())
GROUP BY d.Server_ID
HAVING SUM(CASE WHEN d.Status IN ('skipped', 'error') THEN 1 ELSE 0 END) > 0;
GO

PRINT '  Created: monitoring.VW_Problematic_Servers';
GO

-- ============================================================================
-- VIEW DE TENDÊNCIA DIÁRIA
-- ============================================================================

IF OBJECT_ID('monitoring.VW_Collection_Daily_Trend', 'V') IS NOT NULL
    DROP VIEW monitoring.VW_Collection_Daily_Trend;
GO

CREATE VIEW monitoring.VW_Collection_Daily_Trend AS
SELECT
    CAST(Collection_Start AS DATE) AS Collection_Date,
    COUNT(*) AS Total_Collections,
    AVG(Servers_Configured) AS Avg_Servers_Configured,
    AVG(Servers_Online) AS Avg_Servers_Online,
    AVG(Servers_Skipped) AS Avg_Servers_Skipped,
    AVG(Success_Rate_Pct) AS Avg_Success_Rate_Pct,
    AVG(Duration_Seconds) AS Avg_Duration_Seconds,
    AVG(Avg_Query_Time_MS) AS Avg_Query_Time_MS,
    SUM(Total_Rows_Inserted) AS Total_Rows_Inserted,
    SUM(Servers_Ping_Failed) AS Total_Ping_Failed,
    SUM(Servers_SQL_Down) AS Total_SQL_Down,
    SUM(SWAP_Success_Count) AS Total_SWAP_Success,
    SUM(SWAP_Failed_Count) AS Total_SWAP_Failed
FROM kpi.Collection_History
WHERE Collection_Start >= DATEADD(DAY, -30, GETDATE())
GROUP BY CAST(Collection_Start AS DATE);
GO

PRINT '  Created: monitoring.VW_Collection_Daily_Trend';
GO

-- ============================================================================
-- PROCEDURE DE LIMPEZA
-- ============================================================================

IF OBJECT_ID('monitoring.usp_Purge_Collection_History', 'P') IS NOT NULL
    DROP PROCEDURE monitoring.usp_Purge_Collection_History;
GO

CREATE PROCEDURE monitoring.usp_Purge_Collection_History
    @retention_days INT = 90
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @cutoff_date DATETIME2 = DATEADD(DAY, -@retention_days, GETDATE());
    DECLARE @rows_deleted INT;

    DELETE FROM kpi.Collection_Server_Details
    WHERE Collection_ID IN (
        SELECT Collection_ID FROM kpi.Collection_History
        WHERE Collection_Start < @cutoff_date
    );
    SET @rows_deleted = @@ROWCOUNT;
    PRINT 'Details deleted: ' + CAST(@rows_deleted AS VARCHAR(10));

    DELETE FROM kpi.Collection_History
    WHERE Collection_Start < @cutoff_date;
    SET @rows_deleted = @@ROWCOUNT;
    PRINT 'History deleted: ' + CAST(@rows_deleted AS VARCHAR(10));
END;
GO

PRINT '  Created: monitoring.usp_Purge_Collection_History';
GO

PRINT '';
PRINT '  Collection History installation complete!';
PRINT '';
GO
