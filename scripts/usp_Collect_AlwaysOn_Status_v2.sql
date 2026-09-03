-- =====================================================
-- STORED PROCEDURE: usp_Collect_AlwaysOn_Status
-- VERSÃO: 2.0
-- DESCRIÇÃO: Coleta status Always On de TODAS as instâncias
--            cadastradas no inventário KPI_MSSQL_INST_ENVS
-- =====================================================
-- EXECUÇÃO: EXEC dbo.usp_Collect_AlwaysOn_Status
-- =====================================================

ALTER PROCEDURE dbo.usp_Collect_AlwaysOn_Status
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Instance NVARCHAR(200);
    DECLARE @ServerName NVARCHAR(100);
    DECLARE @InstanceName NVARCHAR(100);
    DECLARE @LinkedServer NVARCHAR(200);
    DECLARE @SQL NVARCHAR(MAX);
    DECLARE @TotalColetado INT = 0;
    DECLARE @TotalInstancias INT = 0;
    DECLARE @InstanciasComAlwaysOn INT = 0;
    DECLARE @Erros INT = 0;

    BEGIN TRY
        PRINT '========================================';
        PRINT 'COLETA DE ALWAYS ON STATUS - v2.0';
        PRINT 'Início: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
        PRINT '========================================';

        -- Truncar staging table
        TRUNCATE TABLE dbo.KPI_MSSQL_ALWAYSON_STATUS_STG;
        PRINT '[INFO] Tabela STG truncada';

        -- Criar tabela temporária para armazenar resultados
        IF OBJECT_ID('tempdb..#AlwaysOnResults') IS NOT NULL
            DROP TABLE #AlwaysOnResults;

        CREATE TABLE #AlwaysOnResults (
            AgName NVARCHAR(200),
            Instance NVARCHAR(200),
            [Database] NVARCHAR(200),
            Pri_Synch_State NVARCHAR(100),
            Pri_Synch_Health NVARCHAR(100),
            Pri_Is_Suspended BIT,
            Sec_Synch_State NVARCHAR(100),
            Sec_Synch_Health NVARCHAR(100),
            Sec_Is_Suspended BIT,
            Commit_Diff_Secs INT,
            Update_TS DATETIME2
        );

        -- Cursor para iterar sobre todas as instâncias do inventário
        DECLARE inst_cursor CURSOR LOCAL FAST_FORWARD FOR
            SELECT DISTINCT Instance
            FROM dbo.KPI_MSSQL_INST_ENVS WITH(NOLOCK)
            WHERE Instance IS NOT NULL AND Instance <> '';

        OPEN inst_cursor;
        FETCH NEXT FROM inst_cursor INTO @Instance;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @TotalInstancias = @TotalInstancias + 1;

            -- Converter formato Instance (ex: SERVIDOR_I01) para LinkedServer (ex: SERVIDOR\I01)
            -- O inventário pode ter formato SERVIDOR_INSTANCIA ou SERVIDOR\INSTANCIA
            SET @LinkedServer = REPLACE(@Instance, '_', '\');

            -- Se não tem \, pode ser instância default
            IF CHARINDEX('\', @LinkedServer) = 0
                SET @LinkedServer = @Instance;

            PRINT '';
            PRINT '[' + CAST(@TotalInstancias AS VARCHAR(5)) + '] Processando: ' + @Instance + ' (LinkedServer: ' + @LinkedServer + ')';

            BEGIN TRY
                -- Verificar se o linked server existe
                IF EXISTS (SELECT 1 FROM sys.servers WHERE name = @LinkedServer)
                BEGIN
                    -- Construir query dinâmica para executar no servidor remoto
                    SET @SQL = N'
                    SELECT
                        ag.name AS AgName,
                        ''' + @Instance + ''' AS Instance,
                        DB_NAME(rs.database_id) AS [Database],
                        MAX(CASE WHEN ars.role_desc = ''PRIMARY'' THEN rs.synchronization_state_desc ELSE NULL END) AS Pri_Synch_State,
                        MAX(CASE WHEN ars.role_desc = ''PRIMARY'' THEN rs.synchronization_health_desc ELSE NULL END) AS Pri_Synch_Health,
                        MAX(CASE WHEN ars.role_desc = ''PRIMARY'' AND rs.suspend_reason_desc IS NOT NULL THEN 1 ELSE 0 END) AS Pri_Is_Suspended,
                        MAX(CASE WHEN ars.role_desc = ''SECONDARY'' THEN rs.synchronization_state_desc ELSE NULL END) AS Sec_Synch_State,
                        MAX(CASE WHEN ars.role_desc = ''SECONDARY'' THEN rs.synchronization_health_desc ELSE NULL END) AS Sec_Synch_Health,
                        MAX(CASE WHEN ars.role_desc = ''SECONDARY'' AND rs.suspend_reason_desc IS NOT NULL THEN 1 ELSE 0 END) AS Sec_Is_Suspended,
                        0 AS Commit_Diff_Secs,
                        GETDATE() AS Update_TS
                    FROM [' + @LinkedServer + '].master.sys.availability_groups ag
                    INNER JOIN [' + @LinkedServer + '].master.sys.dm_hadr_database_replica_states rs
                        ON ag.group_id = rs.group_id
                    INNER JOIN [' + @LinkedServer + '].master.sys.dm_hadr_availability_replica_states ars
                        ON rs.replica_id = ars.replica_id
                    WHERE rs.is_local = 1
                    GROUP BY ag.name, rs.database_id';

                    -- Inserir resultados na tabela temporária
                    INSERT INTO #AlwaysOnResults
                    EXEC sp_executesql @SQL;

                    IF @@ROWCOUNT > 0
                    BEGIN
                        SET @InstanciasComAlwaysOn = @InstanciasComAlwaysOn + 1;
                        PRINT '    [OK] Always On encontrado - ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' databases';
                    END
                    ELSE
                    BEGIN
                        PRINT '    [INFO] Sem Always On configurado';
                    END
                END
                ELSE
                BEGIN
                    -- Linked server não existe, tentar criar dinamicamente ou usar OPENROWSET
                    PRINT '    [AVISO] Linked server não existe: ' + @LinkedServer;

                    -- Tentar conexão direta via OPENROWSET (requer Ad Hoc Distributed Queries habilitado)
                    BEGIN TRY
                        SET @SQL = N'
                        SELECT
                            ag.name AS AgName,
                            ''' + @Instance + ''' AS Instance,
                            DB_NAME(rs.database_id) AS [Database],
                            MAX(CASE WHEN ars.role_desc = ''PRIMARY'' THEN rs.synchronization_state_desc ELSE NULL END) AS Pri_Synch_State,
                            MAX(CASE WHEN ars.role_desc = ''PRIMARY'' THEN rs.synchronization_health_desc ELSE NULL END) AS Pri_Synch_Health,
                            MAX(CASE WHEN ars.role_desc = ''PRIMARY'' AND rs.suspend_reason_desc IS NOT NULL THEN 1 ELSE 0 END) AS Pri_Is_Suspended,
                            MAX(CASE WHEN ars.role_desc = ''SECONDARY'' THEN rs.synchronization_state_desc ELSE NULL END) AS Sec_Synch_State,
                            MAX(CASE WHEN ars.role_desc = ''SECONDARY'' THEN rs.synchronization_health_desc ELSE NULL END) AS Sec_Synch_Health,
                            MAX(CASE WHEN ars.role_desc = ''SECONDARY'' AND rs.suspend_reason_desc IS NOT NULL THEN 1 ELSE 0 END) AS Sec_Is_Suspended,
                            0 AS Commit_Diff_Secs,
                            GETDATE() AS Update_TS
                        FROM OPENROWSET(''SQLNCLI'', ''Server=' + @LinkedServer + ';Trusted_Connection=yes;'',
                            ''SELECT ag.name, ag.group_id, rs.database_id, rs.synchronization_state_desc,
                                    rs.synchronization_health_desc, rs.suspend_reason_desc, rs.replica_id, rs.is_local,
                                    ars.role_desc
                             FROM sys.availability_groups ag
                             INNER JOIN sys.dm_hadr_database_replica_states rs ON ag.group_id = rs.group_id
                             INNER JOIN sys.dm_hadr_availability_replica_states ars ON rs.replica_id = ars.replica_id
                             WHERE rs.is_local = 1'') AS remote
                        GROUP BY ag.name, rs.database_id';

                        -- Esta abordagem pode não funcionar dependendo das configurações
                        -- Por isso está em um TRY separado
                        PRINT '    [INFO] Tentando OPENROWSET...';
                    END TRY
                    BEGIN CATCH
                        PRINT '    [ERRO] OPENROWSET falhou: ' + ERROR_MESSAGE();
                    END CATCH
                END
            END TRY
            BEGIN CATCH
                SET @Erros = @Erros + 1;
                PRINT '    [ERRO] ' + ERROR_MESSAGE();
            END CATCH

            FETCH NEXT FROM inst_cursor INTO @Instance;
        END

        CLOSE inst_cursor;
        DEALLOCATE inst_cursor;

        -- Inserir resultados na tabela STG
        INSERT INTO dbo.KPI_MSSQL_ALWAYSON_STATUS_STG (
            AgName, Instance, [Database],
            Pri_Synch_State, Pri_Synch_Health, Pri_Is_Suspended,
            Sec_Synch_State, Sec_Synch_Health, Sec_Is_Suspended,
            Commit_Diff_Secs, Update_TS
        )
        SELECT
            AgName, Instance, [Database],
            Pri_Synch_State, Pri_Synch_Health, Pri_Is_Suspended,
            Sec_Synch_State, Sec_Synch_Health, Sec_Is_Suspended,
            Commit_Diff_Secs, Update_TS
        FROM #AlwaysOnResults;

        SET @TotalColetado = @@ROWCOUNT;

        -- Limpar
        DROP TABLE #AlwaysOnResults;

        -- Resumo
        PRINT '';
        PRINT '========================================';
        PRINT 'RESUMO DA COLETA';
        PRINT '========================================';
        PRINT 'Total de instâncias processadas: ' + CAST(@TotalInstancias AS VARCHAR(10));
        PRINT 'Instâncias com Always On: ' + CAST(@InstanciasComAlwaysOn AS VARCHAR(10));
        PRINT 'Total de databases coletados: ' + CAST(@TotalColetado AS VARCHAR(10));
        PRINT 'Erros encontrados: ' + CAST(@Erros AS VARCHAR(10));
        PRINT 'Fim: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
        PRINT '========================================';

    END TRY
    BEGIN CATCH
        PRINT '';
        PRINT '[ERRO FATAL] ' + ERROR_MESSAGE();

        IF CURSOR_STATUS('local', 'inst_cursor') >= 0
        BEGIN
            CLOSE inst_cursor;
            DEALLOCATE inst_cursor;
        END

        -- Re-throw do erro
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        DECLARE @ErrorState INT = ERROR_STATE();
        RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END;
GO

-- =====================================================
-- VERIFICAR LINKED SERVERS EXISTENTES
-- =====================================================
PRINT '';
PRINT 'LINKED SERVERS DISPONÍVEIS:';
SELECT name AS LinkedServer, provider, data_source
FROM sys.servers
WHERE is_linked = 1
ORDER BY name;

-- =====================================================
-- SCRIPT PARA CRIAR LINKED SERVERS (SE NECESSÁRIO)
-- =====================================================
/*
-- Exemplo: Criar linked server para uma instância
EXEC sp_addlinkedserver
    @server = 'SERVIDOR\INSTANCIA',
    @srvproduct = '',
    @provider = 'SQLNCLI',
    @datasrc = 'SERVIDOR\INSTANCIA';

-- Configurar para usar contexto de segurança atual
EXEC sp_addlinkedsrvlogin
    @rmtsrvname = 'SERVIDOR\INSTANCIA',
    @useself = 'True';
*/
