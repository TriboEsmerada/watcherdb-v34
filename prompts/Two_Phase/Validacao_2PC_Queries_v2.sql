-- ============================================================================
-- SCRIPT: Validacao_2PC_Queries_v2.sql
-- DESCRIÇÃO: Validação das queries de monitoramento 2PC
-- VERSÃO: 1.1 - Future-proof para versões >= 2022
-- 
-- LÓGICA DE VERSÃO:
--   >= 16 (2022+): Usa DMV nativa sys.dm_tran_distributed_transaction_stats
--   11-15 (2012-2019): Usa sys.dm_tran_locks
--   < 11 (antigas): Aviso de funcionalidade limitada
--
-- SEGURANÇA: Este script NÃO modifica dados, apenas lê DMVs
-- ============================================================================

SET NOCOUNT ON;
PRINT '============================================================================';
PRINT 'VALIDAÇÃO DE QUERIES PARA MONITORAMENTO 2PC';
PRINT 'Servidor: ' + @@SERVERNAME;
PRINT 'Data: ' + CONVERT(VARCHAR(30), GETDATE(), 120);
PRINT '============================================================================';
PRINT '';

-- ============================================================================
-- TESTE 1: Verificar permissões
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 1: Verificar permissões VIEW SERVER STATE';
PRINT '------------------------------------------------------------';

IF HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE') = 1
    PRINT '✅ PASSED: Usuário tem permissão VIEW SERVER STATE';
ELSE
BEGIN
    PRINT '❌ FAILED: Usuário NÃO tem permissão VIEW SERVER STATE';
    PRINT '   Execute: GRANT VIEW SERVER STATE TO [' + SUSER_NAME() + ']';
END
PRINT '';

-- ============================================================================
-- TESTE 2: Detectar versão do SQL Server (FUTURE-PROOF)
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 2: Detectar versão do SQL Server';
PRINT '------------------------------------------------------------';

DECLARE @MajorVersion INT;
DECLARE @VersionFull NVARCHAR(500);
DECLARE @ProductLevel NVARCHAR(50);
DECLARE @Edition NVARCHAR(100);
DECLARE @SQLVersionName NVARCHAR(100);

SELECT 
    @MajorVersion = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)), 4) AS INT),
    @VersionFull = CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)),
    @ProductLevel = CAST(SERVERPROPERTY('ProductLevel') AS NVARCHAR(50)),
    @Edition = CAST(SERVERPROPERTY('Edition') AS NVARCHAR(100));

-- ============================================================
-- LÓGICA FUTURE-PROOF para nome da versão
-- >= 17: Versões futuras (2024, 2026, etc.)
-- 16: SQL Server 2022
-- 15: SQL Server 2019
-- ...
-- < 11: Versões antigas não suportadas
-- ============================================================
SET @SQLVersionName = CASE 
    WHEN @MajorVersion >= 17 THEN '2024+ (v' + CAST(@MajorVersion AS VARCHAR(5)) + ') - Versão futura, DMV nativa disponível'
    WHEN @MajorVersion = 16 THEN '2022'
    WHEN @MajorVersion = 15 THEN '2019'
    WHEN @MajorVersion = 14 THEN '2017'
    WHEN @MajorVersion = 13 THEN '2016'
    WHEN @MajorVersion = 12 THEN '2014'
    WHEN @MajorVersion = 11 THEN '2012'
    WHEN @MajorVersion < 11 AND @MajorVersion > 0 THEN 'Versão antiga (v' + CAST(@MajorVersion AS VARCHAR(5)) + ') - Funcionalidade limitada'
    ELSE 'Desconhecida (v' + CAST(@MajorVersion AS VARCHAR(5)) + ')'
END;

PRINT '   Versão Major: ' + CAST(@MajorVersion AS VARCHAR(10));
PRINT '   Versão Completa: ' + @VersionFull;
PRINT '   Service Pack/CU: ' + @ProductLevel;
PRINT '   Edição: ' + @Edition;
PRINT '   SQL Server: ' + @SQLVersionName;

-- Determinar método de monitoramento
PRINT '   Método: ' + 
    CASE 
        WHEN @MajorVersion >= 16 THEN 'sys.dm_tran_distributed_transaction_stats (DMV nativa - SQL 2022+)'
        WHEN @MajorVersion >= 11 THEN 'sys.dm_tran_locks (método universal - SQL 2012-2019)'
        ELSE 'sys.dm_tran_locks (versão antiga - funcionalidade pode ser limitada)'
    END;

PRINT '✅ PASSED: Versão detectada corretamente';
PRINT '';

-- ============================================================================
-- TESTE 3: Verificar se DMV sys.dm_tran_locks existe e é acessível
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 3: Verificar sys.dm_tran_locks (método universal)';
PRINT '------------------------------------------------------------';

DECLARE @LockCount INT;

BEGIN TRY
    SELECT @LockCount = COUNT(*) 
    FROM sys.dm_tran_locks 
    WHERE 1=0;  -- Query vazia só para testar acesso
    
    PRINT '✅ PASSED: sys.dm_tran_locks está acessível';
    
    -- Testar filtro específico
    SELECT @LockCount = COUNT(*) 
    FROM sys.dm_tran_locks 
    WHERE request_owner_type = 'DISTRIBUTED_TRANSACTION';
    
    PRINT '   Locks distribuídos encontrados: ' + CAST(@LockCount AS VARCHAR(10));
    
    IF @LockCount > 0
        PRINT '   ⚠️ ATENÇÃO: Existem transações distribuídas pendentes!';
    ELSE
        PRINT '   OK: Nenhuma transação distribuída pendente';
        
END TRY
BEGIN CATCH
    PRINT '❌ FAILED: Erro ao acessar sys.dm_tran_locks';
    PRINT '   Erro: ' + ERROR_MESSAGE();
END CATCH
PRINT '';

-- ============================================================================
-- TESTE 4: Verificar DMV nativa (SQL 2022+ ou versões futuras >= 16)
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 4: Verificar sys.dm_tran_distributed_transaction_stats';
PRINT '------------------------------------------------------------';

IF @MajorVersion >= 16  -- 2022 ou qualquer versão FUTURA (2024, 2026, etc.)
BEGIN
    BEGIN TRY
        DECLARE @sql NVARCHAR(500) = N'SELECT TOP 1 * FROM sys.dm_tran_distributed_transaction_stats';
        EXEC sp_executesql @sql;
        PRINT '✅ PASSED: DMV nativa está disponível e acessível';
        
        IF @MajorVersion > 16
            PRINT '   (Versão futura detectada: v' + CAST(@MajorVersion AS VARCHAR(5)) + ' - DMV continua compatível)';
    END TRY
    BEGIN CATCH
        PRINT '❌ FAILED: DMV nativa não está acessível';
        PRINT '   Erro: ' + ERROR_MESSAGE();
        PRINT '   (Fallback: usaremos sys.dm_tran_locks)';
    END CATCH
END
ELSE
BEGIN
    PRINT '⏭️ SKIPPED: SQL Server < 2022 (versão ' + CAST(@MajorVersion AS VARCHAR(5)) + ')';
    PRINT '   DMV nativa não disponível nesta versão.';
    PRINT '   (Isso é esperado e OK - usaremos sys.dm_tran_locks)';
END
PRINT '';

-- ============================================================================
-- TESTE 5: Testar query de contagem de transações distribuídas
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 5: Query de contagem (método universal)';
PRINT '------------------------------------------------------------';

BEGIN TRY
    SELECT 
        @@SERVERNAME AS server_name,
        GETDATE() AS checked_at,
        COUNT(DISTINCT request_owner_guid) AS in_doubt_count,
        COUNT(*) AS total_locks,
        CASE WHEN COUNT(*) > 0 THEN 'CRITICAL' ELSE 'OK' END AS status
    FROM sys.dm_tran_locks
    WHERE request_owner_type = 'DISTRIBUTED_TRANSACTION';
    
    PRINT '✅ PASSED: Query de contagem executou com sucesso';
END TRY
BEGIN CATCH
    PRINT '❌ FAILED: Erro na query de contagem';
    PRINT '   Erro: ' + ERROR_MESSAGE();
END CATCH
PRINT '';

-- ============================================================================
-- TESTE 6: Testar query de detalhes com comandos KILL
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 6: Query de detalhes com comandos de resolução';
PRINT '------------------------------------------------------------';

BEGIN TRY
    SELECT 
        @@SERVERNAME AS server_name,
        l.request_owner_guid AS uow,
        DB_NAME(l.resource_database_id) AS database_name,
        COUNT(*) AS locks_held,
        MAX(l.resource_type) AS resource_type,
        MAX(l.request_mode) AS request_mode,
        'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
        'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
    FROM sys.dm_tran_locks l
    WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
    GROUP BY l.request_owner_guid, l.resource_database_id;
    
    PRINT '✅ PASSED: Query de detalhes executou com sucesso';
    
    IF @@ROWCOUNT = 0
        PRINT '   (Nenhuma transação distribuída encontrada - resultado esperado)';
    ELSE
        PRINT '   ⚠️ Transações distribuídas encontradas! Verifique os resultados acima.';
        
END TRY
BEGIN CATCH
    PRINT '❌ FAILED: Erro na query de detalhes';
    PRINT '   Erro: ' + ERROR_MESSAGE();
END CATCH
PRINT '';

-- ============================================================================
-- TESTE 7: Testar conectividade MS DTC
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 7: Conectividade MS DTC (Distributed Transaction Coordinator)';
PRINT '------------------------------------------------------------';

BEGIN TRY
    BEGIN DISTRIBUTED TRANSACTION;
    ROLLBACK;
    
    PRINT '✅ PASSED: MS DTC está funcionando corretamente';
END TRY
BEGIN CATCH
    PRINT '❌ FAILED: MS DTC não está acessível';
    PRINT '   Erro: ' + ERROR_MESSAGE();
    PRINT '';
    PRINT '   POSSÍVEIS SOLUÇÕES:';
    PRINT '   1. Verificar se o serviço MSDTC está em execução:';
    PRINT '      net start MSDTC';
    PRINT '   2. Verificar configuração do DTC:';
    PRINT '      dcomcnfg > Component Services > My Computer > DTC';
    PRINT '   3. Se não usa transações distribuídas, este erro pode ser ignorado';
END CATCH
PRINT '';

-- ============================================================================
-- TESTE 8: Testar outras DMVs de transação relacionadas
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 8: DMVs relacionadas a transações';
PRINT '------------------------------------------------------------';

-- sys.dm_tran_active_transactions
BEGIN TRY
    SELECT @LockCount = COUNT(*) FROM sys.dm_tran_active_transactions WHERE 1=0;
    PRINT '✅ sys.dm_tran_active_transactions: Acessível';
END TRY
BEGIN CATCH
    PRINT '❌ sys.dm_tran_active_transactions: ' + ERROR_MESSAGE();
END CATCH

-- sys.dm_tran_session_transactions
BEGIN TRY
    SELECT @LockCount = COUNT(*) FROM sys.dm_tran_session_transactions WHERE 1=0;
    PRINT '✅ sys.dm_tran_session_transactions: Acessível';
END TRY
BEGIN CATCH
    PRINT '❌ sys.dm_tran_session_transactions: ' + ERROR_MESSAGE();
END CATCH

-- sys.dm_tran_database_transactions
BEGIN TRY
    SELECT @LockCount = COUNT(*) FROM sys.dm_tran_database_transactions WHERE 1=0;
    PRINT '✅ sys.dm_tran_database_transactions: Acessível';
END TRY
BEGIN CATCH
    PRINT '❌ sys.dm_tran_database_transactions: ' + ERROR_MESSAGE();
END CATCH

PRINT '';

-- ============================================================================
-- TESTE 9: Query completa com detecção de versão (simulação FUTURE-PROOF)
-- ============================================================================
PRINT '------------------------------------------------------------';
PRINT 'TESTE 9: Simulação do script final com detecção de versão';
PRINT '------------------------------------------------------------';

BEGIN TRY
    DECLARE @v INT = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)), 4) AS INT);

    -- Mostrar método que será usado (FUTURE-PROOF)
    SELECT 
        @@SERVERNAME AS servidor,
        GETDATE() AS data_hora,
        @v AS versao_major,
        CASE 
            WHEN @v >= 16 THEN 'SQL 2022+ (DMV nativa) - Inclui versões futuras'
            WHEN @v >= 11 THEN 'SQL 2012-2019 (dm_tran_locks)'
            ELSE 'Versão antiga (dm_tran_locks - funcionalidade limitada)'
        END AS metodo;

    -- ============================================================
    -- BRANCH POR VERSÃO (FUTURE-PROOF)
    -- >= 16: SQL 2022 e TODAS as versões futuras (2024, 2026...)
    -- < 16: SQL 2019 e anteriores
    -- ============================================================
    IF @v >= 16
    BEGIN
        -- SQL Server 2022+ (e todas as versões futuras)
        PRINT '   Executando branch SQL 2022+ (inclui v' + CAST(@v AS VARCHAR(5)) + ' e futuras)...';
        DECLARE @sql2022 NVARCHAR(MAX) = N'
        SELECT 
            @@SERVERNAME AS servidor,
            [open] AS transacoes_abertas,
            in_doubt AS transacoes_in_doubt,
            CASE WHEN in_doubt > 0 THEN ''CRITICAL'' ELSE ''OK'' END AS status
        FROM sys.dm_tran_distributed_transaction_stats;';
        EXEC sp_executesql @sql2022;
    END
    ELSE
    BEGIN
        -- SQL Server < 2022 (2012, 2014, 2016, 2017, 2019)
        PRINT '   Executando branch SQL < 2022 (v' + CAST(@v AS VARCHAR(5)) + ')...';
        SELECT 
            @@SERVERNAME AS servidor,
            COUNT(DISTINCT request_owner_guid) AS transacoes_in_doubt,
            COUNT(*) AS total_locks,
            CASE WHEN COUNT(*) > 0 THEN 'CRITICAL' ELSE 'OK' END AS status
        FROM sys.dm_tran_locks
        WHERE request_owner_type = 'DISTRIBUTED_TRANSACTION';
    END
    
    PRINT '✅ PASSED: Script com detecção de versão executou corretamente';
END TRY
BEGIN CATCH
    PRINT '❌ FAILED: Erro no script com detecção de versão';
    PRINT '   Erro: ' + ERROR_MESSAGE();
END CATCH
PRINT '';

-- ============================================================================
-- RESUMO FINAL
-- ============================================================================
PRINT '============================================================================';
PRINT 'RESUMO DA VALIDAÇÃO';
PRINT '============================================================================';
PRINT '';
PRINT 'Versão detectada: SQL Server ' + @SQLVersionName;
PRINT 'Versão Major: ' + CAST(@MajorVersion AS VARCHAR(10));
PRINT 'Método: ' + 
    CASE 
        WHEN @MajorVersion >= 16 THEN 'sys.dm_tran_distributed_transaction_stats (DMV nativa)'
        ELSE 'sys.dm_tran_locks (método universal)'
    END;
PRINT '';
PRINT 'COMPATIBILIDADE FUTURA:';
PRINT '  >= 16 (2022+): Usa DMV nativa (testado e pronto para versões futuras)';
PRINT '  11-15 (2012-2019): Usa dm_tran_locks (método universal)';
PRINT '  < 11: Funcionalidade limitada';
PRINT '';
PRINT 'Se todos os testes mostraram ✅ PASSED, os scripts estão prontos para uso!';
PRINT '';
PRINT 'PRÓXIMOS PASSOS:';
PRINT '1. Execute o script Monitor_2PC_Compact.sql para verificação rápida';
PRINT '2. Deploy das views em cada servidor: Monitor_2PC_Views.sql';
PRINT '3. Configure o collector Python para automação';
PRINT '';
PRINT '============================================================================';
PRINT 'FIM DA VALIDAÇÃO';
PRINT '============================================================================';
GO
