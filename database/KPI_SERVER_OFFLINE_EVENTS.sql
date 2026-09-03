-- =====================================================================
-- KPI_MSSQL_SERVER_OFFLINE_EVENTS
-- =====================================================================
-- Tabela para registrar eventos de servidor offline ou SQL parado
-- Usada para diagnóstico quando há TIMEOUT no armazenamento
--
-- Autor: WatcherDB Team
-- Data: 2025-12-19
-- Versão: 1.0
-- =====================================================================

USE [WatcherDB]
GO

PRINT '';
PRINT '========================================';
PRINT 'Server Offline Events Tables';
PRINT '========================================';
PRINT '';

-- ============================================================================
-- TABELA PRINCIPAL: kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'KPI_MSSQL_SERVER_OFFLINE_EVENTS' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS (
        Event_ID INT IDENTITY(1,1) PRIMARY KEY,
        Server_Name NVARCHAR(256) NOT NULL,
        Diagnosis NVARCHAR(50) NOT NULL,  -- 'offline', 'sql_down', 'partial', 'online'
        Ping_OK BIT NOT NULL,
        Ping_Message NVARCHAR(500),
        Services_Down NVARCHAR(1000),     -- Lista de serviços SQL parados (separados por vírgula)
        Event_Time DATETIME2 NOT NULL DEFAULT GETDATE(),
        Resolved_Time DATETIME2 NULL,
        Is_Resolved BIT NOT NULL DEFAULT 0
    );
    PRINT '  Created: kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS';
END
ELSE
    PRINT '  Exists: kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS';
GO

-- Índices para performance
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ServerOffline_Server')
BEGIN
    CREATE INDEX IX_ServerOffline_Server
    ON kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS(Server_Name);
    PRINT '  Created: IX_ServerOffline_Server';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ServerOffline_Time')
BEGIN
    CREATE INDEX IX_ServerOffline_Time
    ON kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS(Event_Time DESC);
    PRINT '  Created: IX_ServerOffline_Time';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ServerOffline_Unresolved')
BEGIN
    CREATE INDEX IX_ServerOffline_Unresolved
    ON kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS(Is_Resolved)
    WHERE Is_Resolved = 0;
    PRINT '  Created: IX_ServerOffline_Unresolved';
END
GO

-- ============================================================================
-- VIEW: Eventos não resolvidos (ativos)
-- ============================================================================

IF OBJECT_ID('kpi.vw_ServerOfflineEvents_Active', 'V') IS NOT NULL
    DROP VIEW kpi.vw_ServerOfflineEvents_Active;
GO

CREATE VIEW kpi.vw_ServerOfflineEvents_Active
AS
SELECT
    Event_ID,
    Server_Name,
    Diagnosis,
    Ping_OK,
    Ping_Message,
    Services_Down,
    Event_Time,
    DATEDIFF(MINUTE, Event_Time, GETDATE()) AS Minutes_Since_Event,
    CASE
        WHEN Diagnosis = 'offline' THEN 'CRITICAL'
        WHEN Diagnosis = 'sql_down' THEN 'WARNING'
        WHEN Diagnosis = 'partial' THEN 'WARNING'
        ELSE 'OK'
    END AS Severity
FROM kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
WHERE Is_Resolved = 0;
GO

PRINT '  Created: kpi.vw_ServerOfflineEvents_Active';
GO

-- ============================================================================
-- VIEW AGREGADA: Resumo para o card do dashboard
-- ============================================================================

IF OBJECT_ID('kpi.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW', 'V') IS NOT NULL
    DROP VIEW kpi.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW;
GO

CREATE VIEW kpi.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW
AS
SELECT
    SUM(CASE WHEN Diagnosis = 'offline' THEN 1 ELSE 0 END) AS Servers_Offline,
    SUM(CASE WHEN Diagnosis = 'sql_down' THEN 1 ELSE 0 END) AS Servers_SQL_Down,
    SUM(CASE WHEN Diagnosis = 'partial' THEN 1 ELSE 0 END) AS Servers_Partial,
    COUNT(*) AS Total_Events,
    MAX(Event_Time) AS Last_Event_Time,
    CASE
        WHEN SUM(CASE WHEN Diagnosis = 'offline' THEN 1 ELSE 0 END) > 0 THEN 'CRITICAL'
        WHEN SUM(CASE WHEN Diagnosis IN ('sql_down', 'partial') THEN 1 ELSE 0 END) >= 3 THEN 'CRITICAL'
        WHEN SUM(CASE WHEN Diagnosis IN ('sql_down', 'partial') THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
        ELSE 'OK'
    END AS Overall_Status
FROM kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
WHERE Is_Resolved = 0;
GO

PRINT '  Created: kpi.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW';
GO

-- ============================================================================
-- VIEW DETALHADA: Para modal do dashboard
-- ============================================================================

IF OBJECT_ID('kpi.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW', 'V') IS NOT NULL
    DROP VIEW kpi.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW;
GO

CREATE VIEW kpi.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW
AS
SELECT
    Event_ID,
    Server_Name AS Instance,
    Diagnosis,
    CASE
        WHEN Diagnosis = 'offline' THEN 'Servidor Offline'
        WHEN Diagnosis = 'sql_down' THEN 'SQL Services Down'
        WHEN Diagnosis = 'partial' THEN 'Serviços Parciais'
        ELSE Diagnosis
    END AS Diagnosis_Desc,
    Ping_OK,
    CASE WHEN Ping_OK = 1 THEN 'OK' ELSE 'FALHA' END AS Ping_Status,
    Ping_Message,
    Services_Down,
    Event_Time,
    DATEDIFF(MINUTE, Event_Time, GETDATE()) AS Minutes_Since_Event,
    CASE
        WHEN Diagnosis = 'offline' THEN 'CRITICAL'
        WHEN Diagnosis = 'sql_down' THEN 'WARNING'
        WHEN Diagnosis = 'partial' THEN 'WARNING'
        ELSE 'OK'
    END AS Severity,
    -- Inferir ambiente pelo nome do servidor
    CASE
        WHEN Server_Name LIKE '%PRD%' OR Server_Name LIKE '%PROD%' THEN 'PRD'
        WHEN Server_Name LIKE '%QLT%' OR Server_Name LIKE '%QUAL%' THEN 'QLT'
        WHEN Server_Name LIKE '%TST%' OR Server_Name LIKE '%TEST%' OR Server_Name LIKE '%DEV%' THEN 'TST'
        ELSE 'Undefined'
    END AS Env,
    Is_Resolved,
    Resolved_Time
FROM kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS;
GO

PRINT '  Created: kpi.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW';
GO

-- ============================================================================
-- PROCEDURE: Marcar evento como resolvido
-- ============================================================================

IF OBJECT_ID('kpi.usp_ResolveServerOfflineEvent', 'P') IS NOT NULL
    DROP PROCEDURE kpi.usp_ResolveServerOfflineEvent;
GO

CREATE PROCEDURE kpi.usp_ResolveServerOfflineEvent
    @Server_Name NVARCHAR(256) = NULL,
    @Event_ID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @Event_ID IS NOT NULL
    BEGIN
        UPDATE kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
        SET Is_Resolved = 1,
            Resolved_Time = GETDATE()
        WHERE Event_ID = @Event_ID;
    END
    ELSE IF @Server_Name IS NOT NULL
    BEGIN
        UPDATE kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
        SET Is_Resolved = 1,
            Resolved_Time = GETDATE()
        WHERE Server_Name = @Server_Name
          AND Is_Resolved = 0;
    END

    SELECT @@ROWCOUNT AS Events_Resolved;
END
GO

PRINT '  Created: kpi.usp_ResolveServerOfflineEvent';
GO

-- ============================================================================
-- PROCEDURE: Registrar novo evento de servidor offline
-- ============================================================================

IF OBJECT_ID('kpi.usp_RegisterServerOfflineEvent', 'P') IS NOT NULL
    DROP PROCEDURE kpi.usp_RegisterServerOfflineEvent;
GO

CREATE PROCEDURE kpi.usp_RegisterServerOfflineEvent
    @Server_Name NVARCHAR(256),
    @Diagnosis NVARCHAR(50),
    @Ping_OK BIT,
    @Ping_Message NVARCHAR(500) = NULL,
    @Services_Down NVARCHAR(1000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Verificar se já existe um evento não resolvido para este servidor
    IF EXISTS (
        SELECT 1 FROM kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
        WHERE Server_Name = @Server_Name AND Is_Resolved = 0
    )
    BEGIN
        -- Atualizar o evento existente (refresh do timestamp)
        UPDATE kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
        SET Event_Time = GETDATE(),
            Diagnosis = @Diagnosis,
            Ping_OK = @Ping_OK,
            Ping_Message = @Ping_Message,
            Services_Down = @Services_Down
        WHERE Server_Name = @Server_Name AND Is_Resolved = 0;

        SELECT SCOPE_IDENTITY() AS Event_ID, 'UPDATED' AS Action;
    END
    ELSE
    BEGIN
        -- Inserir novo evento
        INSERT INTO kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS (
            Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down
        )
        VALUES (
            @Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down
        );

        SELECT SCOPE_IDENTITY() AS Event_ID, 'INSERTED' AS Action;
    END
END
GO

PRINT '  Created: kpi.usp_RegisterServerOfflineEvent';
GO

-- ============================================================================
-- PROCEDURE: Limpar eventos antigos
-- ============================================================================

IF OBJECT_ID('kpi.usp_CleanupServerOfflineEvents', 'P') IS NOT NULL
    DROP PROCEDURE kpi.usp_CleanupServerOfflineEvents;
GO

CREATE PROCEDURE kpi.usp_CleanupServerOfflineEvents
    @RetentionDays INT = 90
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
    WHERE Event_Time < DATEADD(DAY, -@RetentionDays, GETDATE());

    SELECT @@ROWCOUNT AS Events_Deleted;
END
GO

PRINT '  Created: kpi.usp_CleanupServerOfflineEvents';
GO

-- ============================================================================
-- PROCEDURE: Auto-resolver eventos antigos (> 30 min sem atualização)
-- ============================================================================

IF OBJECT_ID('kpi.usp_AutoResolveStaleEvents', 'P') IS NOT NULL
    DROP PROCEDURE kpi.usp_AutoResolveStaleEvents;
GO

CREATE PROCEDURE kpi.usp_AutoResolveStaleEvents
    @StaleMinutes INT = 30
AS
BEGIN
    SET NOCOUNT ON;

    -- Eventos que não foram atualizados há mais de X minutos
    -- são automaticamente marcados como resolvidos
    UPDATE kpi.KPI_MSSQL_SERVER_OFFLINE_EVENTS
    SET Is_Resolved = 1,
        Resolved_Time = GETDATE()
    WHERE Is_Resolved = 0
      AND Event_Time < DATEADD(MINUTE, -@StaleMinutes, GETDATE());

    SELECT @@ROWCOUNT AS Events_AutoResolved;
END
GO

PRINT '  Created: kpi.usp_AutoResolveStaleEvents';
GO

PRINT '';
PRINT '  Server Offline Events installation complete!';
PRINT '';
GO
