-- =====================================================================
-- WATCHERDB - BLUE-GREEN DEPLOYMENT + TABELAS POR AMBIENTE
-- =====================================================================
-- Este script implementa:
-- 1. Blue-Green Deployment para swap atômico de tabelas KPI
-- 2. Tabelas separadas por ambiente (PRD/QA/TST) para coleta paralela
--
-- Baseado em: WATCHERDB INTELLIGENCE V1\database\INSTALACAO_COMPLETA_UNIFICADA.sql
-- Portado para: WATCHERDB_DEV
-- Data: 2025-12-19
-- =====================================================================

USE [WatcherDB]
GO

SET NOCOUNT ON;
GO

PRINT '';
PRINT '========================================';
PRINT 'Blue-Green Deployment Setup';
PRINT '========================================';
PRINT '';

-- ============================================================================
-- SECTION 1: BLUE-GREEN DEPLOYMENT
-- ============================================================================
-- Permite swap atômico sem downtime durante coletas
-- Cada tabela STG tem duas versões: BLUE e GREEN
-- Python coleta na tabela INATIVA, depois faz SWAP para ativar
-- ============================================================================

-- 1.1 Tabela de controle Blue-Green
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_STG_ACTIVE_TABLE' AND schema_id = SCHEMA_ID('kpi'))
BEGIN
    CREATE TABLE kpi.KPI_STG_ACTIVE_TABLE (
        Table_Name NVARCHAR(100) PRIMARY KEY,
        Active_Slot NVARCHAR(10) NOT NULL CHECK (Active_Slot IN ('BLUE', 'GREEN')),
        Last_Swap_Time DATETIME2 DEFAULT GETDATE(),
        Collection_Start_Time DATETIME2 NULL,
        Collection_End_Time DATETIME2 NULL,
        Servers_Collected INT DEFAULT 0,
        Created_Date DATETIME2 DEFAULT GETDATE()
    );
    PRINT '  Created: kpi.KPI_STG_ACTIVE_TABLE';
END
ELSE
    PRINT '  Exists: kpi.KPI_STG_ACTIVE_TABLE';
GO

-- 1.2 Função helper para obter tabela de coleta (retorna tabela INATIVA)
IF EXISTS (SELECT 1 FROM sys.objects WHERE name = 'fn_get_kpi_collection_target' AND type = 'FN' AND schema_id = SCHEMA_ID('kpi'))
    DROP FUNCTION kpi.fn_get_kpi_collection_target;
GO

CREATE FUNCTION kpi.fn_get_kpi_collection_target(@table_name NVARCHAR(100))
RETURNS NVARCHAR(200)
AS
BEGIN
    DECLARE @active_slot NVARCHAR(10);
    DECLARE @target_table NVARCHAR(200);

    SELECT @active_slot = Active_Slot
    FROM kpi.KPI_STG_ACTIVE_TABLE
    WHERE Table_Name = @table_name;

    -- Retorna tabela INATIVA (onde coletar novos dados)
    SET @target_table = @table_name + '_' + CASE
        WHEN @active_slot = 'BLUE' THEN 'GREEN'
        WHEN @active_slot = 'GREEN' THEN 'BLUE'
        ELSE 'BLUE'
    END;

    RETURN @target_table;
END
GO
PRINT '  Created: kpi.fn_get_kpi_collection_target';
GO

-- 1.3 Stored Procedure de SWAP atômico
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_swap_kpi_stg_tables' AND schema_id = SCHEMA_ID('kpi'))
    DROP PROCEDURE kpi.usp_swap_kpi_stg_tables;
GO

CREATE PROCEDURE kpi.usp_swap_kpi_stg_tables
    @table_name NVARCHAR(100),
    @servers_collected INT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @current_active NVARCHAR(10);
    DECLARE @new_active NVARCHAR(10);

    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT @current_active = Active_Slot
        FROM kpi.KPI_STG_ACTIVE_TABLE WITH (UPDLOCK)
        WHERE Table_Name = @table_name;

        IF @current_active IS NULL
        BEGIN
            ROLLBACK TRANSACTION;
            RAISERROR('Tabela %s não encontrada em KPI_STG_ACTIVE_TABLE', 16, 1, @table_name);
            RETURN;
        END

        SET @new_active = CASE WHEN @current_active = 'BLUE' THEN 'GREEN' ELSE 'BLUE' END;

        UPDATE kpi.KPI_STG_ACTIVE_TABLE
        SET Active_Slot = @new_active,
            Last_Swap_Time = GETDATE(),
            Collection_End_Time = GETDATE(),
            Servers_Collected = @servers_collected
        WHERE Table_Name = @table_name;

        COMMIT TRANSACTION;

        -- Retornar resultado do SWAP
        SELECT @table_name AS Table_Name,
               @current_active AS Old_Active,
               @new_active AS New_Active,
               @servers_collected AS Servers_Collected,
               GETDATE() AS Swap_Time;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMessage, 16, 1);
    END CATCH
END
GO
PRINT '  Created: kpi.usp_swap_kpi_stg_tables';
GO

-- 1.4 Registrar tabelas KPI no controle Blue-Green
DECLARE @tables_to_register TABLE (table_name NVARCHAR(100));
INSERT INTO @tables_to_register VALUES
    ('KPI_MSSQL_ALWAYSON_STATUS_STG'),
    ('KPI_MSSQL_BACKUPS_STG'),
    ('KPI_MSSQL_BACKUP_STATUS_STG'),
    ('KPI_MSSQL_BLOCKED_SESSIONS_STG'),
    ('KPI_MSSQL_BLOCKED_USERS_STG'),
    ('KPI_MSSQL_DB_AVAILABILITY_STG'),
    ('KPI_MSSQL_DB_IO_STATS_STG'),
    ('KPI_MSSQL_DISK_USAGE_STG'),
    ('KPI_MSSQL_ERRORLOG_STG'),
    ('KPI_MSSQL_FG_USAGE_STG'),
    ('KPI_MSSQL_INST_AVAILABILITY_STG'),
    ('KPI_MSSQL_LONG_LOCKS_STG'),
    ('KPI_MSSQL_PROCESSES_STG'),
    ('KPI_MSSQL_SERVICE_STATUS_STG'),
    ('KPI_MSSQL_TLOG_USAGE_STG');

INSERT INTO kpi.KPI_STG_ACTIVE_TABLE (Table_Name, Active_Slot, Last_Swap_Time, Created_Date)
SELECT t.table_name, 'BLUE', GETDATE(), GETDATE()
FROM @tables_to_register t
WHERE NOT EXISTS (
    SELECT 1 FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = t.table_name
);

PRINT '  Registered KPI tables for Blue-Green deployment';
GO

-- ============================================================================
-- SECTION 2: TABELAS POR AMBIENTE (PRD/QA/TST)
-- ============================================================================
-- Permite coleta paralela sem contenção de locks
-- Cada ambiente insere em tabelas separadas
-- VIEWs fazem UNION ALL automaticamente
-- ============================================================================

PRINT '';
PRINT '========================================';
PRINT 'Environment Tables Setup (PRD/QA/TST)';
PRINT '========================================';
PRINT '';

-- 2.1 Procedure para setup de tabelas por ambiente
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_setup_environment_tables' AND schema_id = SCHEMA_ID('kpi'))
    DROP PROCEDURE kpi.usp_setup_environment_tables;
GO

CREATE PROCEDURE kpi.usp_setup_environment_tables
    @base_table_name NVARCHAR(100),
    @verbose BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @sql NVARCHAR(MAX);
    DECLARE @blue_table NVARCHAR(200) = @base_table_name + '_BLUE';
    DECLARE @green_table NVARCHAR(200) = @base_table_name + '_GREEN';
    DECLARE @env VARCHAR(3);
    DECLARE @slot VARCHAR(5);
    DECLARE @source_table NVARCHAR(200);
    DECLARE @target_table NVARCHAR(200);
    DECLARE @msg NVARCHAR(500);

    -- Verificar se tabela BLUE existe
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @blue_table)
    BEGIN
        SET @msg = '    [SKIP] Tabela ' + @blue_table + ' nao existe';
        IF @verbose = 1 PRINT @msg;
        RETURN;
    END

    -- Loop para cada ambiente (PRD, QA, TST)
    DECLARE @envs TABLE (Env VARCHAR(3));
    INSERT INTO @envs VALUES ('PRD'), ('QA'), ('TST');

    -- Loop para cada slot (BLUE, GREEN)
    DECLARE @slots TABLE (Slot VARCHAR(5));
    INSERT INTO @slots VALUES ('BLUE'), ('GREEN');

    DECLARE slot_cursor CURSOR FOR SELECT Slot FROM @slots;
    OPEN slot_cursor;
    FETCH NEXT FROM slot_cursor INTO @slot;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @source_table = @base_table_name + '_' + @slot;

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @source_table)
        BEGIN
            DECLARE env_cursor CURSOR FOR SELECT Env FROM @envs;
            OPEN env_cursor;
            FETCH NEXT FROM env_cursor INTO @env;

            WHILE @@FETCH_STATUS = 0
            BEGIN
                SET @target_table = @source_table + '_' + @env;

                IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @target_table)
                BEGIN
                    SET @sql = 'SELECT * INTO kpi.' + @target_table + ' FROM kpi.' + @source_table + ' WHERE 1=0';
                    EXEC sp_executesql @sql;

                    SET @msg = '    [OK] Criada tabela: ' + @target_table;
                    IF @verbose = 1 PRINT @msg;

                    BEGIN TRY
                        SET @sql = 'CREATE INDEX IX_' + @target_table + '_Instance ON kpi.' + @target_table + '(Instance)';
                        EXEC sp_executesql @sql;
                    END TRY
                    BEGIN CATCH END CATCH

                    BEGIN TRY
                        SET @sql = 'CREATE INDEX IX_' + @target_table + '_UpdateTS ON kpi.' + @target_table + '(Update_TS)';
                        EXEC sp_executesql @sql;
                    END TRY
                    BEGIN CATCH END CATCH
                END
                ELSE
                BEGIN
                    SET @msg = '    [INFO] Tabela ja existe: ' + @target_table;
                    IF @verbose = 1 PRINT @msg;
                END

                FETCH NEXT FROM env_cursor INTO @env;
            END

            CLOSE env_cursor;
            DEALLOCATE env_cursor;
        END

        FETCH NEXT FROM slot_cursor INTO @slot;
    END

    CLOSE slot_cursor;
    DEALLOCATE slot_cursor;

    SET @msg = '    [DONE] Setup de ambientes para ' + @base_table_name;
    IF @verbose = 1 PRINT @msg;
END
GO

PRINT '  Created: kpi.usp_setup_environment_tables';
GO

-- 2.2 Procedure para criação especial da tabela AlwaysOn (com coluna computed PERSISTED)
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_setup_alwayson_env_tables' AND schema_id = SCHEMA_ID('kpi'))
    DROP PROCEDURE kpi.usp_setup_alwayson_env_tables;
GO

CREATE PROCEDURE kpi.usp_setup_alwayson_env_tables
    @verbose BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @slots TABLE (Slot VARCHAR(5));
    INSERT INTO @slots VALUES ('BLUE'), ('GREEN');

    DECLARE @envs TABLE (Env VARCHAR(3));
    INSERT INTO @envs VALUES ('PRD'), ('QA'), ('TST');

    DECLARE @slot VARCHAR(5);
    DECLARE @env VARCHAR(3);
    DECLARE @table_name NVARCHAR(200);
    DECLARE @sql NVARCHAR(MAX);
    DECLARE @msg NVARCHAR(500);

    DECLARE slot_cursor CURSOR FOR SELECT Slot FROM @slots;
    OPEN slot_cursor;
    FETCH NEXT FROM slot_cursor INTO @slot;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        DECLARE env_cursor CURSOR FOR SELECT Env FROM @envs;
        OPEN env_cursor;
        FETCH NEXT FROM env_cursor INTO @env;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @table_name = 'KPI_MSSQL_ALWAYSON_STATUS_STG_' + @slot + '_' + @env;

            IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @table_name AND schema_id = SCHEMA_ID('kpi'))
            BEGIN
                SET @sql = '
CREATE TABLE kpi.' + @table_name + ' (
    AgName              VARCHAR(128)    NOT NULL,
    Instance            VARCHAR(64)     NOT NULL,
    [Database]          VARCHAR(128)    NOT NULL,
    Pri_Synch_State     VARCHAR(32)     NULL,
    Pri_Synch_Health    VARCHAR(32)     NULL,
    Pri_Is_Suspended    BIT             DEFAULT 0,
    Sec_Synch_State     VARCHAR(32)     NULL,
    Sec_Synch_Health    VARCHAR(32)     NULL,
    Sec_Is_Suspended    BIT             DEFAULT 0,
    Commit_Diff_Secs    INT             NULL,
    Update_TS           DATETIME2       DEFAULT GETDATE(),
    Problem_Reason AS (
        CASE
            WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY'')
                  OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'')
                  OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                 AND (Pri_Is_Suspended = 1 OR Sec_Is_Suspended = 1) THEN ''Health Problem + Suspended''
            WHEN ((Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY'')
                  OR (Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'')
                  OR (Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL))
                 AND (Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')) THEN ''Health Problem + Sync State''
            WHEN Pri_Synch_Health IS NULL AND Sec_Synch_Health IS NULL THEN ''No Health Data (Both Replicas)''
            WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY''
                 AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'' THEN ''Both Replicas Unhealthy''
            WHEN Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''HEALTHY'' THEN ''Primary Replica Unhealthy ('' + Pri_Synch_Health + '')''
            WHEN Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> ''HEALTHY'' THEN ''Secondary Replica Unhealthy ('' + Sec_Synch_Health + '')''
            WHEN Pri_Is_Suspended = 1 AND Sec_Is_Suspended = 1 THEN ''Both Replicas Suspended''
            WHEN Pri_Is_Suspended = 1 THEN ''Primary Replica Suspended''
            WHEN Sec_Is_Suspended = 1 THEN ''Secondary Replica Suspended''
            WHEN Pri_Synch_State IS NOT NULL AND Pri_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')
                 THEN ''Primary Sync State Problem ('' + Pri_Synch_State + '')''
            WHEN Sec_Synch_State IS NOT NULL AND Sec_Synch_State NOT IN (''SYNCHRONIZED'', ''SYNCHRONIZING'')
                 THEN ''Secondary Sync State Problem ('' + Sec_Synch_State + '')''
            ELSE NULL
        END
    ) PERSISTED,
    CONSTRAINT PK_' + @table_name + ' PRIMARY KEY (AgName, Instance, [Database])
)';

                BEGIN TRY
                    EXEC sp_executesql @sql;
                    SET @msg = '    [OK] Criada tabela AlwaysOn: ' + @table_name;
                    IF @verbose = 1 PRINT @msg;
                END TRY
                BEGIN CATCH
                    SET @msg = '    [ERRO] ' + @table_name + ': ' + ERROR_MESSAGE();
                    IF @verbose = 1 PRINT @msg;
                END CATCH

                -- Criar índices
                BEGIN TRY
                    SET @sql = 'CREATE INDEX IX_' + @table_name + '_Instance ON kpi.' + @table_name + '(Instance)';
                    EXEC sp_executesql @sql;
                END TRY
                BEGIN CATCH END CATCH

                BEGIN TRY
                    SET @sql = 'CREATE INDEX IX_' + @table_name + '_UpdateTS ON kpi.' + @table_name + '(Update_TS)';
                    EXEC sp_executesql @sql;
                END TRY
                BEGIN CATCH END CATCH
            END
            ELSE
            BEGIN
                SET @msg = '    [INFO] Tabela ja existe: ' + @table_name;
                IF @verbose = 1 PRINT @msg;
            END

            FETCH NEXT FROM env_cursor INTO @env;
        END

        CLOSE env_cursor;
        DEALLOCATE env_cursor;

        FETCH NEXT FROM slot_cursor INTO @slot;
    END

    CLOSE slot_cursor;
    DEALLOCATE slot_cursor;
END
GO

PRINT '  Created: kpi.usp_setup_alwayson_env_tables';
GO

-- 2.3 Procedure para criar VIEW dinâmica por ambiente (UNION ALL)
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_create_environment_view' AND schema_id = SCHEMA_ID('kpi'))
    DROP PROCEDURE kpi.usp_create_environment_view;
GO

CREATE PROCEDURE kpi.usp_create_environment_view
    @base_table_name NVARCHAR(100),
    @verbose BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @sql NVARCHAR(MAX);
    DECLARE @view_name NVARCHAR(200) = @base_table_name;
    DECLARE @msg NVARCHAR(500);
    DECLARE @active_slot NVARCHAR(10);

    SELECT @active_slot = Active_Slot
    FROM kpi.KPI_STG_ACTIVE_TABLE
    WHERE Table_Name = @base_table_name;

    IF @active_slot IS NULL SET @active_slot = 'BLUE';

    IF EXISTS (SELECT 1 FROM sys.views WHERE name = @view_name AND schema_id = SCHEMA_ID('kpi'))
    BEGIN
        SET @sql = 'DROP VIEW kpi.' + @view_name;
        EXEC sp_executesql @sql;
        SET @msg = '    [INFO] VIEW antiga removida: ' + @view_name;
        IF @verbose = 1 PRINT @msg;
    END

    SET @sql = '
CREATE VIEW kpi.' + @view_name + ' AS
SELECT * FROM kpi.' + @base_table_name + '_BLUE_PRD
WHERE (SELECT Active_Slot FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @base_table_name + ''') = ''BLUE''
UNION ALL
SELECT * FROM kpi.' + @base_table_name + '_BLUE_QA
WHERE (SELECT Active_Slot FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @base_table_name + ''') = ''BLUE''
UNION ALL
SELECT * FROM kpi.' + @base_table_name + '_BLUE_TST
WHERE (SELECT Active_Slot FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @base_table_name + ''') = ''BLUE''
UNION ALL
SELECT * FROM kpi.' + @base_table_name + '_GREEN_PRD
WHERE (SELECT Active_Slot FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @base_table_name + ''') = ''GREEN''
UNION ALL
SELECT * FROM kpi.' + @base_table_name + '_GREEN_QA
WHERE (SELECT Active_Slot FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @base_table_name + ''') = ''GREEN''
UNION ALL
SELECT * FROM kpi.' + @base_table_name + '_GREEN_TST
WHERE (SELECT Active_Slot FROM kpi.KPI_STG_ACTIVE_TABLE WHERE Table_Name = ''' + @base_table_name + ''') = ''GREEN''
';

    BEGIN TRY
        EXEC sp_executesql @sql;
        SET @msg = '    [OK] VIEW criada: ' + @view_name + ' (UNION ALL de 3 ambientes por slot)';
        IF @verbose = 1 PRINT @msg;
    END TRY
    BEGIN CATCH
        SET @msg = '    [ERRO] VIEW ' + @view_name + ': ' + ERROR_MESSAGE();
        IF @verbose = 1 PRINT @msg;
    END CATCH
END
GO

PRINT '  Created: kpi.usp_create_environment_view';
GO

-- 2.4 Função para obter tabela por ambiente
IF EXISTS (SELECT 1 FROM sys.objects WHERE name = 'fn_get_kpi_collection_target_env' AND type = 'FN' AND schema_id = SCHEMA_ID('kpi'))
    DROP FUNCTION kpi.fn_get_kpi_collection_target_env;
GO

CREATE FUNCTION kpi.fn_get_kpi_collection_target_env(
    @table_name NVARCHAR(100),
    @environment VARCHAR(3)  -- 'PRD', 'QA', 'TST'
)
RETURNS NVARCHAR(200)
AS
BEGIN
    DECLARE @active_slot NVARCHAR(10);
    DECLARE @target_table NVARCHAR(200);

    SELECT @active_slot = Active_Slot
    FROM kpi.KPI_STG_ACTIVE_TABLE
    WHERE Table_Name = @table_name;

    -- Retorna tabela INATIVA do ambiente especificado
    SET @target_table = @table_name + '_' + CASE
        WHEN @active_slot = 'BLUE' THEN 'GREEN'
        WHEN @active_slot = 'GREEN' THEN 'BLUE'
        ELSE 'BLUE'
    END + '_' + @environment;

    RETURN @target_table;
END
GO

PRINT '  Created: kpi.fn_get_kpi_collection_target_env';
GO

-- 2.3 Procedure para TRUNCATE por ambiente
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_truncate_stg_tables_env' AND schema_id = SCHEMA_ID('kpi'))
    DROP PROCEDURE kpi.usp_truncate_stg_tables_env;
GO

CREATE PROCEDURE kpi.usp_truncate_stg_tables_env
    @environment VARCHAR(3),  -- 'PRD', 'QA', 'TST'
    @kpi_list NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @truncated_count INT = 0;
    DECLARE @failed_tables NVARCHAR(MAX) = '';
    DECLARE @table_name NVARCHAR(200);
    DECLARE @target_table NVARCHAR(200);
    DECLARE @sql NVARCHAR(MAX);

    DECLARE @tables TABLE (Table_Name NVARCHAR(100));

    INSERT INTO @tables (Table_Name) VALUES
        ('KPI_MSSQL_FG_USAGE_STG'),
        ('KPI_MSSQL_BACKUPS_STG'),
        ('KPI_MSSQL_BACKUP_STATUS_STG'),
        ('KPI_MSSQL_BLOCKED_SESSIONS_STG'),
        ('KPI_MSSQL_BLOCKED_USERS_STG'),
        ('KPI_MSSQL_DB_AVAILABILITY_STG'),
        ('KPI_MSSQL_DB_IO_STATS_STG'),
        ('KPI_MSSQL_DISK_USAGE_STG'),
        ('KPI_MSSQL_ERRORLOG_STG'),
        ('KPI_MSSQL_LONG_LOCKS_STG'),
        ('KPI_MSSQL_SERVICE_STATUS_STG'),
        ('KPI_MSSQL_TLOG_USAGE_STG'),
        ('KPI_MSSQL_INST_AVAILABILITY_STG');

    DECLARE table_cursor CURSOR FOR
        SELECT Table_Name FROM @tables WHERE Table_Name IS NOT NULL;

    OPEN table_cursor;
    FETCH NEXT FROM table_cursor INTO @table_name;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @target_table = kpi.fn_get_kpi_collection_target_env(@table_name, @environment);

        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @target_table AND schema_id = SCHEMA_ID('kpi'))
        BEGIN
            BEGIN TRY
                SET @sql = 'TRUNCATE TABLE kpi.' + @target_table;
                EXEC sp_executesql @sql;
                SET @truncated_count = @truncated_count + 1;
            END TRY
            BEGIN CATCH
                BEGIN TRY
                    SET @sql = 'DELETE FROM kpi.' + @target_table;
                    EXEC sp_executesql @sql;
                    SET @truncated_count = @truncated_count + 1;
                END TRY
                BEGIN CATCH
                    IF LEN(@failed_tables) > 0 SET @failed_tables = @failed_tables + ',';
                    SET @failed_tables = @failed_tables + @target_table;
                END CATCH
            END CATCH
        END

        FETCH NEXT FROM table_cursor INTO @table_name;
    END

    CLOSE table_cursor;
    DEALLOCATE table_cursor;

    SELECT
        @truncated_count AS Truncated_Count,
        CASE WHEN LEN(@failed_tables) > 0 THEN @failed_tables ELSE NULL END AS Failed_Tables,
        @environment AS Environment;
END
GO

PRINT '  Created: kpi.usp_truncate_stg_tables_env';
GO

-- 2.4 Procedure para SWAP atômico com suporte a ambientes
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_swap_kpi_stg_tables_env' AND schema_id = SCHEMA_ID('kpi'))
    DROP PROCEDURE kpi.usp_swap_kpi_stg_tables_env;
GO

CREATE PROCEDURE kpi.usp_swap_kpi_stg_tables_env
    @table_name NVARCHAR(100),
    @environment VARCHAR(3) = NULL,  -- NULL = swap todas as tabelas; 'PRD'/'QA'/'TST' = swap apenas ambiente
    @servers_collected INT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @current_active NVARCHAR(10);
    DECLARE @new_active NVARCHAR(10);
    DECLARE @source_table NVARCHAR(200);
    DECLARE @target_table NVARCHAR(200);
    DECLARE @sql NVARCHAR(MAX);

    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT @current_active = Active_Slot
        FROM kpi.KPI_STG_ACTIVE_TABLE WITH (UPDLOCK)
        WHERE Table_Name = @table_name;

        IF @current_active IS NULL
        BEGIN
            ROLLBACK TRANSACTION;
            RAISERROR('Tabela %s não encontrada em KPI_STG_ACTIVE_TABLE', 16, 1, @table_name);
            RETURN;
        END

        SET @new_active = CASE WHEN @current_active = 'BLUE' THEN 'GREEN' ELSE 'BLUE' END;

        -- Se ambiente específico, fazer merge das tabelas de ambiente para a tabela principal
        IF @environment IS NOT NULL
        BEGIN
            SET @source_table = @table_name + '_' + @new_active + '_' + @environment;
            SET @target_table = @table_name + '_' + @new_active;

            -- Verificar se tabela de ambiente existe
            IF EXISTS (SELECT 1 FROM sys.tables WHERE name = @source_table AND schema_id = SCHEMA_ID('kpi'))
            BEGIN
                -- Inserir dados do ambiente na tabela principal
                SET @sql = 'INSERT INTO kpi.' + @target_table + ' SELECT * FROM kpi.' + @source_table;
                EXEC sp_executesql @sql;
            END
        END

        UPDATE kpi.KPI_STG_ACTIVE_TABLE
        SET Active_Slot = @new_active,
            Last_Swap_Time = GETDATE(),
            Collection_End_Time = GETDATE(),
            Servers_Collected = @servers_collected
        WHERE Table_Name = @table_name;

        COMMIT TRANSACTION;

        SELECT @table_name AS Table_Name,
               @current_active AS Old_Active,
               @new_active AS New_Active,
               @servers_collected AS Servers_Collected,
               @environment AS Environment,
               GETDATE() AS Swap_Time;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMessage, 16, 1);
    END CATCH
END
GO

PRINT '  Created: kpi.usp_swap_kpi_stg_tables_env';
GO

-- ============================================================================
-- SECTION 3: CRIAR TABELAS POR AMBIENTE PARA TODAS AS 15 TABELAS KPI
-- ============================================================================
-- Nota: As tabelas Blue-Green base devem existir antes de rodar esta seção.
-- Caso contrário, as procedures irão pular a criação.
-- ============================================================================

PRINT '';
PRINT '========================================';
PRINT 'Creating Environment Tables for All KPIs';
PRINT '========================================';
PRINT '';

-- 3.1 Tabelas padrão (usam usp_setup_environment_tables)
PRINT '>>> 1/15: KPI_MSSQL_FG_USAGE_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_FG_USAGE_STG', @verbose = 0;
GO

PRINT '>>> 2/15: KPI_MSSQL_BACKUPS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BACKUPS_STG', @verbose = 0;
GO

PRINT '>>> 3/15: KPI_MSSQL_BACKUP_STATUS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BACKUP_STATUS_STG', @verbose = 0;
GO

PRINT '>>> 4/15: KPI_MSSQL_BLOCKED_SESSIONS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BLOCKED_SESSIONS_STG', @verbose = 0;
GO

PRINT '>>> 5/15: KPI_MSSQL_BLOCKED_USERS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_BLOCKED_USERS_STG', @verbose = 0;
GO

PRINT '>>> 6/15: KPI_MSSQL_DB_AVAILABILITY_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_DB_AVAILABILITY_STG', @verbose = 0;
GO

PRINT '>>> 7/15: KPI_MSSQL_DB_IO_STATS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_DB_IO_STATS_STG', @verbose = 0;
GO

PRINT '>>> 8/15: KPI_MSSQL_DISK_USAGE_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_DISK_USAGE_STG', @verbose = 0;
GO

PRINT '>>> 9/15: KPI_MSSQL_ERRORLOG_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_ERRORLOG_STG', @verbose = 0;
GO

PRINT '>>> 10/15: KPI_MSSQL_LONG_LOCKS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_LONG_LOCKS_STG', @verbose = 0;
GO

PRINT '>>> 11/15: KPI_MSSQL_SERVICE_STATUS_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_SERVICE_STATUS_STG', @verbose = 0;
GO

PRINT '>>> 12/15: KPI_MSSQL_TLOG_USAGE_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_TLOG_USAGE_STG', @verbose = 0;
GO

PRINT '>>> 13/15: KPI_MSSQL_INST_AVAILABILITY_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_INST_AVAILABILITY_STG', @verbose = 0;
GO

PRINT '>>> 14/15: KPI_MSSQL_PROCESSES_STG';
EXEC kpi.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_PROCESSES_STG', @verbose = 0;
GO

-- 3.2 Tabela AlwaysOn (usa procedure especial com coluna computed)
PRINT '>>> 15/15: KPI_MSSQL_ALWAYSON_STATUS_STG (com Problem_Reason computed)';
EXEC kpi.usp_setup_alwayson_env_tables @verbose = 0;
GO

PRINT '';
PRINT '  Environment tables created for all 15 KPIs';
GO

-- ============================================================================
-- SECTION 4: VERIFICAÇÃO FINAL
-- ============================================================================

PRINT '';
PRINT '========================================';
PRINT 'Verification - Environment Tables Count';
PRINT '========================================';
PRINT '';

DECLARE @blue_prd INT, @blue_qa INT, @blue_tst INT;
DECLARE @green_prd INT, @green_qa INT, @green_tst INT;

SELECT @blue_prd = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_BLUE_PRD' AND schema_id = SCHEMA_ID('kpi');
SELECT @blue_qa = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_BLUE_QA' AND schema_id = SCHEMA_ID('kpi');
SELECT @blue_tst = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_BLUE_TST' AND schema_id = SCHEMA_ID('kpi');
SELECT @green_prd = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_GREEN_PRD' AND schema_id = SCHEMA_ID('kpi');
SELECT @green_qa = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_GREEN_QA' AND schema_id = SCHEMA_ID('kpi');
SELECT @green_tst = COUNT(*) FROM sys.tables WHERE name LIKE '%_STG_GREEN_TST' AND schema_id = SCHEMA_ID('kpi');

PRINT '  Tables by Environment:';
PRINT '    BLUE:  PRD=' + CAST(@blue_prd AS VARCHAR) + ', QA=' + CAST(@blue_qa AS VARCHAR) + ', TST=' + CAST(@blue_tst AS VARCHAR);
PRINT '    GREEN: PRD=' + CAST(@green_prd AS VARCHAR) + ', QA=' + CAST(@green_qa AS VARCHAR) + ', TST=' + CAST(@green_tst AS VARCHAR);
PRINT '    Total: ' + CAST(@blue_prd + @blue_qa + @blue_tst + @green_prd + @green_qa + @green_tst AS VARCHAR) + ' environment tables';
PRINT '';
GO

-- ============================================================================
-- SECTION 5: SUMMARY
-- ============================================================================

PRINT '';
PRINT '========================================';
PRINT 'Blue-Green + Environment Tables - Summary';
PRINT '========================================';
PRINT '';
PRINT 'Objects Created:';
PRINT '  Tables:';
PRINT '    - kpi.KPI_STG_ACTIVE_TABLE (Blue-Green control)';
PRINT '    - 90 environment tables (15 KPIs x 2 slots x 3 environments)';
PRINT '';
PRINT '  Functions:';
PRINT '    - kpi.fn_get_kpi_collection_target (get inactive table)';
PRINT '    - kpi.fn_get_kpi_collection_target_env (get inactive table by env)';
PRINT '';
PRINT '  Procedures:';
PRINT '    - kpi.usp_swap_kpi_stg_tables (atomic swap)';
PRINT '    - kpi.usp_setup_environment_tables (create PRD/QA/TST tables)';
PRINT '    - kpi.usp_setup_alwayson_env_tables (AlwaysOn with Problem_Reason computed)';
PRINT '    - kpi.usp_create_environment_view (create UNION ALL views)';
PRINT '    - kpi.usp_truncate_stg_tables_env (truncate by environment)';
PRINT '    - kpi.usp_swap_kpi_stg_tables_env (swap with environment support)';
PRINT '';
PRINT 'Usage Examples:';
PRINT '  -- Get target table for collection:';
PRINT '  SELECT kpi.fn_get_kpi_collection_target(''KPI_MSSQL_FG_USAGE_STG'');';
PRINT '';
PRINT '  -- Get target table for PRD environment:';
PRINT '  SELECT kpi.fn_get_kpi_collection_target_env(''KPI_MSSQL_FG_USAGE_STG'', ''PRD'');';
PRINT '';
PRINT '  -- Swap after collection:';
PRINT '  EXEC kpi.usp_swap_kpi_stg_tables @table_name = ''KPI_MSSQL_FG_USAGE_STG'', @servers_collected = 50;';
PRINT '';
PRINT '  -- Setup environment tables for a KPI:';
PRINT '  EXEC kpi.usp_setup_environment_tables @base_table_name = ''KPI_MSSQL_FG_USAGE_STG'';';
PRINT '';
PRINT '  -- Create UNION ALL view for environment tables:';
PRINT '  EXEC kpi.usp_create_environment_view @base_table_name = ''KPI_MSSQL_FG_USAGE_STG'';';
PRINT '';
PRINT 'Architecture:';
PRINT '  Parallel Collection by Environment (PRD/QA/TST):';
PRINT '    - Zero lock contention between environments';
PRINT '    - Each environment writes to its own table';
PRINT '    - VIEWs do UNION ALL automatically based on active slot';
PRINT '';
PRINT '  Blue-Green Deployment:';
PRINT '    - BLUE active = collecting to GREEN';
PRINT '    - After collection, SWAP makes GREEN active';
PRINT '    - Dashboard always reads from active slot';
PRINT '';
GO
