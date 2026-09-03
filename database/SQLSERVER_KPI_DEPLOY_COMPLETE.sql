-- ============================================================================
-- WATCHERDB INTELLIGENCE V2 - DEPLOYMENT COMPLETO E ÚNICO
-- ============================================================================
-- Script ÚNICO para deployment completo da solução SQL Server KPI
--
-- ESTE SCRIPT EXECUTA TUDO EM SEQUÊNCIA:
--   1. Criação de database (se não existir)
--   2. Criação de filegroups
--   3. Criação de 18 tabelas
--   4. Criação de 23 views
--   5. Criação de 12 procedures de coleta
--   6. Criação de 2 SQL Agent Jobs
--   7. Teste inicial de coleta
--   8. Validação completa
--
-- TEMPO ESTIMADO: 5-10 minutos
--
-- AUTOR: WatcherDB Team
-- DATA: 2025-11-27
-- VERSÃO: 2.0.0 - SCRIPT ÚNICO COMPLETO
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '';
PRINT '================================================================================';
PRINT '███╗   ███╗ █████╗ ████████╗ ██████╗██╗  ██╗███████╗██████╗ ██████╗ ██████╗ ';
PRINT '████╗ ████║██╔══██╗╚══██╔══╝██╔════╝██║  ██║██╔════╝██╔══██╗██╔══██╗██╔══██╗';
PRINT '██╔████╔██║███████║   ██║   ██║     ███████║█████╗  ██████╔╝██║  ██║██████╔╝';
PRINT '██║╚██╔╝██║██╔══██║   ██║   ██║     ██╔══██║██╔══╝  ██╔══██╗██║  ██║██╔══██╗';
PRINT '██║ ╚═╝ ██║██║  ██║   ██║   ╚██████╗██║  ██║███████╗██║  ██║██████╔╝██████╔╝';
PRINT '╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚═════╝ ';
PRINT '                                                                              ';
PRINT 'INTELLIGENCE V2 - DEPLOYMENT COMPLETO';
PRINT '================================================================================';
PRINT '';
PRINT 'Início: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT 'Servidor: ' + @@SERVERNAME;
PRINT 'Versão SQL Server: ' + CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(50));
PRINT '';
PRINT 'ESTE SCRIPT VAI:';
PRINT '  1. Criar database WatcherDB_Intelligence_V2 (se não existir)';
PRINT '  2. Criar 2 filegroups dedicados';
PRINT '  3. Criar 18 tabelas (11 STG, 3 HIST, 2 Thresholds, 2 CMDB)';
PRINT '  4. Criar 23 views (11 AGG, 11 DET, 1 CMDB)';
PRINT '  5. Criar 12 procedures de coleta';
PRINT '  6. Criar 2 SQL Agent Jobs';
PRINT '  7. Executar teste de coleta';
PRINT '  8. Validar deployment completo';
PRINT '';
PRINT 'Tempo estimado: 5-10 minutos';
PRINT '================================================================================';
PRINT '';
PRINT 'Pressione CTRL+C para cancelar ou aguarde 10 segundos...';
WAITFOR DELAY '00:00:10';
GO

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 1/8: CRIAÇÃO DE DATABASE';
PRINT '================================================================================';
PRINT '';

-- Criar database se não existir
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'WatcherDB_Intelligence_V2')
BEGIN
    CREATE DATABASE [WatcherDB_Intelligence_V2];
    PRINT '[OK] Database WatcherDB_Intelligence_V2 criado';
END
ELSE
BEGIN
    PRINT '[INFO] Database WatcherDB_Intelligence_V2 já existe';
END
GO

USE [WatcherDB_Intelligence_V2];
GO

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 2/8: CRIAÇÃO DE FILEGROUPS';
PRINT '================================================================================';
PRINT '';

-- Criar filegroups dedicados
IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = 'FG_KPI_DATA')
BEGIN
    ALTER DATABASE [WatcherDB_Intelligence_V2]
    ADD FILEGROUP [FG_KPI_DATA];
    PRINT '[OK] Filegroup FG_KPI_DATA criado';
END
ELSE
    PRINT '[INFO] Filegroup FG_KPI_DATA já existe';

IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = 'FG_KPI_HIST')
BEGIN
    ALTER DATABASE [WatcherDB_Intelligence_V2]
    ADD FILEGROUP [FG_KPI_HIST];
    PRINT '[OK] Filegroup FG_KPI_HIST criado';
END
ELSE
    PRINT '[INFO] Filegroup FG_KPI_HIST já existe';
GO

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 3/8: CRIAÇÃO DE TABELAS (18 total)';
PRINT '================================================================================';
PRINT '';

-- Incluir o script de tabelas
:r SQLSERVER_KPI_REPLICATION_COMPLETE.sql

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 4/8: CRIAÇÃO DE VIEWS (23 total)';
PRINT '================================================================================';
PRINT '';

-- Incluir o script de views
:r SQLSERVER_KPI_VIEWS.sql

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 5/8: CRIAÇÃO DE PROCEDURES DE COLETA (12 total)';
PRINT '================================================================================';
PRINT '';

-- Incluir o script de procedures
:r SQLSERVER_KPI_COLLECTION_PROCEDURES.sql

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 6/8: CRIAÇÃO DE SQL AGENT JOBS (2 total)';
PRINT '================================================================================';
PRINT '';

-- Incluir o script de jobs
:r SQLSERVER_KPI_AGENT_JOBS.sql

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 7/8: CONFIGURAÇÃO INICIAL E TESTE';
PRINT '================================================================================';
PRINT '';

-- Popular tabela de mapeamento Instance → Environment
IF NOT EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_INST_ENVS)
BEGIN
    PRINT '[1/2] Populando tabela KPI_MSSQL_INST_ENVS...';

    INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env, Description)
    VALUES (@@SERVERNAME, 'PROD', 'Servidor local');

    PRINT '[OK] Mapeamento Instance → Environment criado';
END
ELSE
    PRINT '[INFO] Tabela KPI_MSSQL_INST_ENVS já populada';
GO

-- Executar teste de coleta
PRINT '';
PRINT '[2/2] Executando TESTE de coleta (pode levar 30-60 segundos)...';
PRINT '';

BEGIN TRY
    EXEC dbo.usp_Collect_All_KPIs @Debug = 1;
    PRINT '';
    PRINT '[OK] Teste de coleta executado com sucesso!';
END TRY
BEGIN CATCH
    PRINT '';
    PRINT '[ERRO] Falha no teste de coleta: ' + ERROR_MESSAGE();
    PRINT '[INFO] Deployment continua, mas verifique os erros acima';
END CATCH
GO

PRINT '';
PRINT '================================================================================';
PRINT 'ETAPA 8/8: VALIDAÇÃO FINAL';
PRINT '================================================================================';
PRINT '';

-- Validar objetos criados
DECLARE @TableCount INT, @ViewCount INT, @ProcCount INT, @JobCount INT;
DECLARE @DataCount INT;

-- Contar tabelas
SELECT @TableCount = COUNT(*)
FROM sys.tables
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%';

-- Contar views
SELECT @ViewCount = COUNT(*)
FROM sys.views
WHERE name LIKE 'KPI_MSSQL%' OR name LIKE 'CMDB_MSSQL%';

-- Contar procedures
SELECT @ProcCount = COUNT(*)
FROM sys.procedures
WHERE name LIKE 'usp_Collect%';

-- Contar jobs
SELECT @JobCount = COUNT(*)
FROM msdb.dbo.sysjobs
WHERE name LIKE 'WatcherDB%';

-- Contar dados coletados (exemplo)
SELECT @DataCount = COUNT(*)
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG;

-- Exibir resumo
PRINT '┌────────────────────────────────────────────────────────────────────────┐';
PRINT '│                        RESUMO DO DEPLOYMENT                             │';
PRINT '├────────────────────────────────────────────────────────────────────────┤';
PRINT '│ Objeto              │ Esperado │ Criado │ Status                       │';
PRINT '├────────────────────────────────────────────────────────────────────────┤';
PRINT '│ Tabelas             │    19    │   ' + RIGHT('  ' + CAST(@TableCount AS VARCHAR(2)), 2) + '   │ ' +
      CASE WHEN @TableCount = 19 THEN '[OK]    ' ELSE '[ERRO]  ' END + '                     │';
PRINT '│ Views               │    23    │   ' + RIGHT('  ' + CAST(@ViewCount AS VARCHAR(2)), 2) + '   │ ' +
      CASE WHEN @ViewCount = 23 THEN '[OK]    ' ELSE '[ERRO]  ' END + '                     │';
PRINT '│ Procedures          │    12    │   ' + RIGHT('  ' + CAST(@ProcCount AS VARCHAR(2)), 2) + '   │ ' +
      CASE WHEN @ProcCount = 12 THEN '[OK]    ' ELSE '[ERRO]  ' END + '                     │';
PRINT '│ SQL Agent Jobs      │     2    │   ' + RIGHT('  ' + CAST(@JobCount AS VARCHAR(2)), 2) + '   │ ' +
      CASE WHEN @JobCount = 2 THEN '[OK]    ' ELSE '[ERRO]  ' END + '                     │';
PRINT '│ Dados coletados     │    > 0   │   ' + RIGHT('  ' + CAST(@DataCount AS VARCHAR(2)), 2) + '   │ ' +
      CASE WHEN @DataCount > 0 THEN '[OK]    ' ELSE '[AVISO] ' END + '                     │';
PRINT '└────────────────────────────────────────────────────────────────────────┘';
PRINT '';

IF @TableCount = 19 AND @ViewCount = 23 AND @ProcCount = 12 AND @JobCount = 2
BEGIN
    PRINT '✓✓✓ DEPLOYMENT 100% CONCLUÍDO COM SUCESSO! ✓✓✓';
END
ELSE
BEGIN
    PRINT '⚠️  DEPLOYMENT PARCIALMENTE CONCLUÍDO - VERIFIQUE OS ERROS ACIMA';
END
GO

PRINT '';
PRINT '================================================================================';
PRINT '                         DEPLOYMENT FINALIZADO                              ';
PRINT '================================================================================';
PRINT '';
PRINT 'Término: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
PRINT '┌────────────────────────────────────────────────────────────────────────┐';
PRINT '│                           PRÓXIMOS PASSOS                               │';
PRINT '├────────────────────────────────────────────────────────────────────────┤';
PRINT '│                                                                         │';
PRINT '│ 1. VERIFICAR DADOS COLETADOS:                                           │';
PRINT '│    SELECT * FROM dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW;                     │';
PRINT '│    SELECT * FROM dbo.KPI_MSSQL_INST_AVAILABILITY_DET_VIEW;              │';
PRINT '│    SELECT * FROM dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW;                     │';
PRINT '│                                                                         │';
PRINT '│ 2. VERIFICAR JOBS AGENDADOS:                                            │';
PRINT '│    SELECT name, enabled FROM msdb.dbo.sysjobs WHERE name LIKE ''WatcherDB%''; │';
PRINT '│                                                                         │';
PRINT '│ 3. EXECUTAR COLETA MANUAL (opcional):                                   │';
PRINT '│    EXEC dbo.usp_Collect_All_KPIs @Debug = 1;                            │';
PRINT '│                                                                         │';
PRINT '│ 4. ADICIONAR MAIS SERVIDORES (opcional):                                │';
PRINT '│    INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env)                  │';
PRINT '│    VALUES (''SERVIDOR\INSTANCIA'', ''PROD'');                              │';
PRINT '│                                                                         │';
PRINT '│ 5. VER HISTÓRICO DE EXECUÇÃO DOS JOBS:                                  │';
PRINT '│    EXEC msdb.dbo.sp_help_jobhistory @job_name = ''WatcherDB_Collect_KPIs'';  │';
PRINT '│                                                                         │';
PRINT '│ 6. DOCUMENTAÇÃO COMPLETA:                                               │';
PRINT '│    Consulte: README_REPLICACAO_ORACLE_SQLSERVER.md                      │';
PRINT '│                                                                         │';
PRINT '└────────────────────────────────────────────────────────────────────────┘';
PRINT '';
PRINT '================================================================================';
PRINT '                   WATCHERDB INTELLIGENCE V2 - PRONTO!                     ';
PRINT '                                                                            ';
PRINT '  O sistema está coletando dados a cada 5 minutos automaticamente.         ';
PRINT '  Aguarde 5 minutos e consulte as views para ver os dados populados.       ';
PRINT '                                                                            ';
PRINT '  Para dúvidas: README_REPLICACAO_ORACLE_SQLSERVER.md                      ';
PRINT '================================================================================';
PRINT '';
GO
