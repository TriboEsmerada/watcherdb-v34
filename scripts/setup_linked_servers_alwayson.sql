-- =====================================================
-- SCRIPT PARA CONFIGURAR LINKED SERVERS
-- PARA COLETA DE ALWAYS ON
-- =====================================================
-- Este script cria linked servers para todas as instâncias
-- cadastradas no inventário KPI_MSSQL_INST_ENVS
-- =====================================================

SET NOCOUNT ON;

PRINT '========================================';
PRINT 'CONFIGURAÇÃO DE LINKED SERVERS';
PRINT '========================================';
PRINT '';

-- =====================================================
-- 1. LISTAR INSTÂNCIAS DO INVENTÁRIO
-- =====================================================
PRINT '1. INSTÂNCIAS NO INVENTÁRIO:';
PRINT '--------------------------------------------';

SELECT
    Instance,
    Env,
    REPLACE(Instance, '_', '\') AS LinkedServerName,
    CASE
        WHEN EXISTS (SELECT 1 FROM sys.servers WHERE name = REPLACE(Instance, '_', '\'))
        THEN 'EXISTE'
        ELSE 'NAO EXISTE'
    END AS LinkedServerStatus
FROM dbo.KPI_MSSQL_INST_ENVS WITH(NOLOCK)
ORDER BY Instance;

-- =====================================================
-- 2. LINKED SERVERS EXISTENTES
-- =====================================================
PRINT '';
PRINT '2. LINKED SERVERS EXISTENTES:';
PRINT '--------------------------------------------';

SELECT
    name AS LinkedServer,
    provider,
    data_source AS DataSource,
    CASE is_linked WHEN 1 THEN 'Sim' ELSE 'Não' END AS IsLinked
FROM sys.servers
WHERE is_linked = 1 OR name LIKE '%SQL%'
ORDER BY name;

-- =====================================================
-- 3. SCRIPT PARA CRIAR LINKED SERVERS FALTANTES
-- =====================================================
PRINT '';
PRINT '3. SCRIPTS PARA CRIAR LINKED SERVERS FALTANTES:';
PRINT '--------------------------------------------';
PRINT '';

DECLARE @Instance NVARCHAR(200);
DECLARE @LinkedServer NVARCHAR(200);
DECLARE @SQL NVARCHAR(MAX);

DECLARE inst_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT DISTINCT
        Instance,
        REPLACE(Instance, '_', '\') AS LinkedServer
    FROM dbo.KPI_MSSQL_INST_ENVS WITH(NOLOCK)
    WHERE Instance IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM sys.servers
          WHERE name = REPLACE(Instance, '_', '\')
      );

OPEN inst_cursor;
FETCH NEXT FROM inst_cursor INTO @Instance, @LinkedServer;

IF @@FETCH_STATUS <> 0
BEGIN
    PRINT '-- Todos os linked servers já existem!';
END

WHILE @@FETCH_STATUS = 0
BEGIN
    PRINT '-- Linked Server para: ' + @Instance;
    PRINT 'EXEC sp_addlinkedserver';
    PRINT '    @server = ''' + @LinkedServer + ''',';
    PRINT '    @srvproduct = '''',';
    PRINT '    @provider = ''SQLNCLI'',';
    PRINT '    @datasrc = ''' + @LinkedServer + ''';';
    PRINT '';
    PRINT 'EXEC sp_addlinkedsrvlogin';
    PRINT '    @rmtsrvname = ''' + @LinkedServer + ''',';
    PRINT '    @useself = ''True'';';
    PRINT '';
    PRINT 'GO';
    PRINT '';

    FETCH NEXT FROM inst_cursor INTO @Instance, @LinkedServer;
END

CLOSE inst_cursor;
DEALLOCATE inst_cursor;

-- =====================================================
-- 4. CRIAR LINKED SERVERS AUTOMATICAMENTE (OPCIONAL)
-- =====================================================
/*
-- DESCOMENTE ESTE BLOCO PARA CRIAR AUTOMATICAMENTE

PRINT '';
PRINT '4. CRIANDO LINKED SERVERS AUTOMATICAMENTE...';
PRINT '--------------------------------------------';

DECLARE @Instance2 NVARCHAR(200);
DECLARE @LinkedServer2 NVARCHAR(200);

DECLARE create_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT DISTINCT
        Instance,
        REPLACE(Instance, '_', '\') AS LinkedServer
    FROM dbo.KPI_MSSQL_INST_ENVS WITH(NOLOCK)
    WHERE Instance IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM sys.servers
          WHERE name = REPLACE(Instance, '_', '\')
      );

OPEN create_cursor;
FETCH NEXT FROM create_cursor INTO @Instance2, @LinkedServer2;

WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        PRINT 'Criando linked server: ' + @LinkedServer2;

        EXEC sp_addlinkedserver
            @server = @LinkedServer2,
            @srvproduct = '',
            @provider = 'SQLNCLI',
            @datasrc = @LinkedServer2;

        EXEC sp_addlinkedsrvlogin
            @rmtsrvname = @LinkedServer2,
            @useself = 'True';

        PRINT '    [OK] Criado com sucesso';
    END TRY
    BEGIN CATCH
        PRINT '    [ERRO] ' + ERROR_MESSAGE();
    END CATCH

    FETCH NEXT FROM create_cursor INTO @Instance2, @LinkedServer2;
END

CLOSE create_cursor;
DEALLOCATE create_cursor;
*/

-- =====================================================
-- 5. TESTAR CONECTIVIDADE DOS LINKED SERVERS
-- =====================================================
PRINT '';
PRINT '5. TESTANDO CONECTIVIDADE:';
PRINT '--------------------------------------------';
PRINT '';

DECLARE @TestServer NVARCHAR(200);
DECLARE @TestSQL NVARCHAR(500);

DECLARE test_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT name
    FROM sys.servers
    WHERE is_linked = 1
      AND name IN (SELECT REPLACE(Instance, '_', '\') FROM dbo.KPI_MSSQL_INST_ENVS);

OPEN test_cursor;
FETCH NEXT FROM test_cursor INTO @TestServer;

WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        SET @TestSQL = 'SELECT @result = @@SERVERNAME FROM [' + @TestServer + '].master.sys.databases WHERE database_id = 1';

        DECLARE @result NVARCHAR(200);
        EXEC sp_executesql @TestSQL, N'@result NVARCHAR(200) OUTPUT', @result OUTPUT;

        PRINT '[OK] ' + @TestServer + ' - Conectado';
    END TRY
    BEGIN CATCH
        PRINT '[ERRO] ' + @TestServer + ' - ' + ERROR_MESSAGE();
    END CATCH

    FETCH NEXT FROM test_cursor INTO @TestServer;
END

CLOSE test_cursor;
DEALLOCATE test_cursor;

PRINT '';
PRINT '========================================';
PRINT 'FIM DA VERIFICAÇÃO';
PRINT '========================================';
