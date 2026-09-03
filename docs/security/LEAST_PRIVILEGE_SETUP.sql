/*
================================================================================
WatcherDB — SQL Server Least Privilege Setup
================================================================================

Propósito
---------
Criar um SQL login dedicado `WatcherDBReader` com as permissões mínimas
necessárias para que o WatcherDB monitorize o SQL Server. Usar este
login em vez de um SQL login `sysadmin` ou de uma Windows account com
privilégios excessivos.

Audience
--------
DBA ou admin SQL Server do cliente. Executar como `sysadmin` (o login
criado NÃO será sysadmin).

Tiers
-----
Este script está dividido em 3 secções. Comentar/descomentar conforme
o produto que se vai instalar:

  [TIER: STANDARD]              — WatcherDB V3.3 Standard
  [TIER: PRO]                   — WatcherDB V5.x / V5.5 Pro (additive)
  [TIER: INTELLIGENCE_COLLECTOR] — WatcherDB Intelligence V1 collector

O [TIER: PRO] é ADITIVO ao STANDARD (Pro precisa de tudo que Standard
pede + extras). Se instalar Pro, correr Standard PRIMEIRO, depois Pro.
Se instalar Intelligence Collector, correr a secção IntelligenceCollector
APENAS na instância onde corre o serviço colector (não em cada instância
monitorizada).

Uso
---
  sqlcmd -S <instance> -E -i LEAST_PRIVILEGE_SETUP.sql

Ou copiar para SSMS e executar secção a secção. Ler comentários antes de
executar — há placeholders `<PASSWORD_AQUI>`, `<DOMAIN>` que requerem
substituição.

Reversão
--------
Ver final do ficheiro — script de cleanup comentado.

================================================================================
*/

-- =============================================================================
-- Pré-condições
-- =============================================================================

-- Executar como sysadmin. Validar:
IF NOT IS_SRVROLEMEMBER('sysadmin') = 1
BEGIN
    RAISERROR('Este script requer privilégios sysadmin para criar o login WatcherDBReader.', 16, 1);
    RETURN;
END;

PRINT 'Pré-condição OK: sysadmin detectado.';
PRINT '';

-- =============================================================================
-- Escolher tipo de autenticação (SQL Auth OU Windows Auth)
-- =============================================================================

-- Descomentar UM dos dois blocos abaixo:

-- ---------- Opção A: SQL Authentication (mais portável) ----------
/*
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'WatcherDBReader')
BEGIN
    CREATE LOGIN WatcherDBReader
        WITH PASSWORD = N'<PASSWORD_AQUI>',
             CHECK_POLICY = ON,
             CHECK_EXPIRATION = OFF;  -- OFF para service accounts para evitar expiry
    PRINT 'Login WatcherDBReader criado (SQL Auth).';
END
ELSE
    PRINT 'Login WatcherDBReader já existe (SQL Auth).';
*/

-- ---------- Opção B: Windows Authentication (recomendado em AD) ----------
/*
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = '<DOMAIN>\WatcherDBReader')
BEGIN
    CREATE LOGIN [<DOMAIN>\WatcherDBReader] FROM WINDOWS;
    PRINT 'Login <DOMAIN>\WatcherDBReader criado (Windows Auth).';
END
ELSE
    PRINT 'Login <DOMAIN>\WatcherDBReader já existe.';
*/

-- Definir variável com o nome do login para reutilização abaixo.
DECLARE @LoginName SYSNAME = N'WatcherDBReader';  -- ou N'<DOMAIN>\WatcherDBReader';

-- =============================================================================
-- [TIER: STANDARD] — Permissões base (aplica a V3.3 Standard e Pro)
-- =============================================================================

PRINT '--- TIER: STANDARD ---';

-- IMPORTANTE (apanhado no teste 2026-08-21): os GRANTs server-scope abaixo
-- (VIEW SERVER STATE/DEFINITION/DATABASE) SO' se concedem com a BD actual =
-- master, senao dao Msg 4621. Nao assumir que a ligacao abre em master -- a
-- ligacao de teste abriu em WatcherDB_Intelligence. Forcar aqui.
USE master;

-- VIEW SERVER STATE: acesso read-only a DMVs (sys.dm_os_*, sys.dm_exec_*, etc.)
-- Necessário para: CPU, memória, sessions, waits, latches, locks, IO stats.
GRANT VIEW SERVER STATE TO [WatcherDBReader];  -- ajustar nome se Windows Auth
PRINT 'GRANT VIEW SERVER STATE — dmv monitoring.';

-- VIEW ANY DEFINITION: ler metadata (sys.tables, sys.indexes, sys.views, etc.)
-- Necessário para: schema discovery, filegroup analysis, index fragmentation.
GRANT VIEW ANY DEFINITION TO [WatcherDBReader];
PRINT 'GRANT VIEW ANY DEFINITION — schema metadata.';

-- VIEW ANY DATABASE: listar databases + propriedades (sys.databases).
-- NOTA: Default 'public' já tem este grant em SQL Server moderno.
GRANT VIEW ANY DATABASE TO [WatcherDBReader];
PRINT 'GRANT VIEW ANY DATABASE — database enumeration.';

-- msdb: jobs, backups, sysmail, log shipping (tudo read-only).
USE msdb;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'WatcherDBReader')
    CREATE USER WatcherDBReader FOR LOGIN WatcherDBReader;
-- Se Windows Auth: CREATE USER [<DOMAIN>\WatcherDBReader] FOR LOGIN [<DOMAIN>\WatcherDBReader];

-- Backup history + jobs
GRANT SELECT ON dbo.backupset TO WatcherDBReader;
GRANT SELECT ON dbo.backupmediafamily TO WatcherDBReader;
GRANT SELECT ON dbo.backupmediaset TO WatcherDBReader;
GRANT SELECT ON dbo.backupfile TO WatcherDBReader;
GRANT SELECT ON dbo.sysjobs TO WatcherDBReader;
GRANT SELECT ON dbo.sysjobhistory TO WatcherDBReader;
GRANT SELECT ON dbo.sysjobsteps TO WatcherDBReader;
GRANT SELECT ON dbo.sysjobschedules TO WatcherDBReader;
GRANT SELECT ON dbo.sysjobservers TO WatcherDBReader;
GRANT SELECT ON dbo.sysoperators TO WatcherDBReader;
GRANT SELECT ON dbo.sysschedules TO WatcherDBReader;
GRANT EXECUTE ON dbo.sp_help_jobactivity TO WatcherDBReader;

-- GAP 2 fechado (audit 2026-08-20; CORRIGIDO no teste 2026-08-21): o produto le
-- sysjobactivity e syssessions DIRECTAMENTE (api/routers/jobs.py:338-341,
-- api/routers/live_monitoring.py:615-619), nao via sp_help_jobactivity.
-- ATENCAO: o GRANT SELECT directo nessas tabelas do SQL Agent NAO chega
-- (testado como WatcherDBReader: "The SELECT permission was denied on
-- 'sysjobactivity'/'syssessions'"). O caminho canonico e menos-privilegio e a
-- role fixa de msdb SQLAgentReaderRole -- read-only, ve TODOS os jobs e a sua
-- actividade/sessoes. Provado a devolver linhas em SQL 2025 (2026-08-21).
ALTER ROLE SQLAgentReaderRole ADD MEMBER WatcherDBReader;
GRANT SELECT ON dbo.syscategories TO WatcherDBReader;
PRINT 'msdb: GRANT SELECT backup*/sysjobs* + SQLAgentReaderRole (job activity+sessions) + syscategories.';

USE master;

-- Os GRANT EXECUTE (xp_readerrorlog) e GRANT SHOWPLAN abaixo precisam de um USER
-- WatcherDBReader EM MASTER (senao: Msg 15151). O script criava o user em msdb e
-- WatcherDB_Intelligence mas faltava em master (apanhado no teste 2026-08-21).
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'WatcherDBReader')
    CREATE USER WatcherDBReader FOR LOGIN WatcherDBReader;
-- Se Windows Auth: CREATE USER [<DOMAIN>\WatcherDBReader] FOR LOGIN [<DOMAIN>\WatcherDBReader];

-- =============================================================================
-- GAP 1 fechado (audit least-priv 2026-08-20): xp_readerrorlog
-- =============================================================================
-- O produto le o SQL Server error log via xp_readerrorlog
-- (api/routers/live_monitoring.py:904/914, mirroring_diagnosis.py:97). Isto NAO
-- e' coberto por VIEW SERVER STATE nem db_datareader -- e' o unico item que sai
-- do modelo read-only puro, e a razao historica pela qual o produto usava
-- Windows Auth com conta dbo. Este GRANT granular resolve-o SEM dbo: e' um EXEC
-- de leitura sobre uma extended proc do sistema, nao da' sysadmin, nao e'
-- xp_cmdshell. Se o cliente banking recusar este grant numa instancia, deixa-se
-- essa instancia em use_windows_auth:true (servers.json) como EXCEPCAO
-- documentada -- o error log/mirroring caem graciosamente nessa instancia.
GRANT EXECUTE ON sys.xp_readerrorlog TO WatcherDBReader;
PRINT 'master: GRANT EXECUTE ON sys.xp_readerrorlog — error log + mirroring diag.';

-- =============================================================================
-- GAP 3 fechado (audit least-priv 2026-08-20): SHOWPLAN e' STANDARD, nao PRO
-- =============================================================================
-- A analise de plano (api/routers/queries/plan_analysis.py, via
-- sys.dm_exec_text_query_plan) corre no V3.3 STANDARD, mas o SHOWPLAN estava na
-- seccao [TIER: PRO] (ver abaixo, agora removido de la). Movido para aqui.
-- NOTA Query Store: as views sys.query_store_* exigem ainda VIEW DATABASE STATE
-- na BD-alvo -- concedido por BD onde o Query Store esteja ligado (nao global,
-- para nao alargar o scope sem necessidade).
GRANT SHOWPLAN TO [WatcherDBReader];
PRINT 'master: GRANT SHOWPLAN — plan analysis (STANDARD; era erradamente PRO).';

PRINT '[TIER: STANDARD] COMPLETE.';
PRINT '';

-- =============================================================================
-- [TIER: PRO] — Permissões adicionais para V5.x / V5.5 Pro
-- =============================================================================
-- Comentar este bloco se instalar apenas STANDARD.

PRINT '--- TIER: PRO (additive) ---';

-- TDE / encryption status (Pro feature — security dashboard)
-- VIEW SERVER SECURITY STATE (SQL Server 2022+). Pre-2022 fallback: grant
-- individual em sys.certificates e sys.symmetric_keys.
-- Compatível 2022+:
IF CAST(SERVERPROPERTY('ProductMajorVersion') AS INT) >= 16
BEGIN
    GRANT VIEW SERVER SECURITY STATE TO [WatcherDBReader];
    PRINT 'GRANT VIEW SERVER SECURITY STATE (SQL 2022+).';
END
ELSE
BEGIN
    -- Pre-2022: VIEW ANY DEFINITION já cobre sys.certificates read.
    PRINT 'SQL Server pre-2022 detectado — VIEW ANY DEFINITION cobre cert metadata.';
END;

-- SHOWPLAN: MOVIDO para [TIER: STANDARD] (2026-08-20, GAP 3). A analise de
-- plano corre no V3.3 Standard (plan_analysis.py), nao e' feature Pro. Ver o
-- GRANT SHOWPLAN na seccao STANDARD acima. Nao repetir aqui.

-- ALTER TRACE (opcional, Pro apenas — extended events read)
-- Descomentar apenas se cliente autorizar: Extended Events consultas.
-- GRANT ALTER TRACE TO [WatcherDBReader];
-- PRINT 'GRANT ALTER TRACE — Extended Events (opt-in Pro).';

PRINT '[TIER: PRO] COMPLETE.';
PRINT '';

-- =============================================================================
-- [TIER: INTELLIGENCE_COLLECTOR] — V1 Intelligence collector service
-- =============================================================================
-- APENAS na instância onde corre o collector service.
-- NÃO em todas as instâncias monitorizadas (essas só precisam STANDARD/PRO).
-- Collector precisa WRITE na base WatcherDB_Intelligence (partilhada).

PRINT '--- TIER: INTELLIGENCE_COLLECTOR ---';

-- Criar BD partilhada se não existe
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'WatcherDB_Intelligence')
BEGIN
    CREATE DATABASE WatcherDB_Intelligence;
    PRINT 'Database WatcherDB_Intelligence criada.';
END
ELSE
    PRINT 'Database WatcherDB_Intelligence já existe.';

USE WatcherDB_Intelligence;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'WatcherDBReader')
    CREATE USER WatcherDBReader FOR LOGIN WatcherDBReader;

-- Collector precisa write-access na sua própria BD
-- db_datareader + db_datawriter + CREATE TABLE (para KPI_STG_* swap)
ALTER ROLE db_datareader ADD MEMBER WatcherDBReader;
ALTER ROLE db_datawriter ADD MEMBER WatcherDBReader;
GRANT CREATE TABLE TO WatcherDBReader;
GRANT ALTER ON SCHEMA::dbo TO WatcherDBReader;  -- para swap table rename
PRINT 'WatcherDB_Intelligence: db_datareader + db_datawriter + CREATE/ALTER.';

-- Execute swap procedure
IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = 'usp_swap_kpi_stg_tables')
BEGIN
    GRANT EXECUTE ON dbo.usp_swap_kpi_stg_tables TO WatcherDBReader;
    PRINT 'GRANT EXECUTE usp_swap_kpi_stg_tables.';
END;

USE master;

PRINT '[TIER: INTELLIGENCE_COLLECTOR] COMPLETE.';
PRINT '';

-- =============================================================================
-- Verificação final
-- =============================================================================

PRINT '--- Permissões efectivas do login ---';
SELECT
    sp.class_desc,
    sp.permission_name,
    sp.state_desc,
    ISNULL(o.name, sp.class_desc) AS target
FROM sys.server_permissions sp
LEFT JOIN sys.server_principals p ON sp.grantee_principal_id = p.principal_id
LEFT JOIN sys.all_objects o ON sp.major_id = o.object_id
WHERE p.name = 'WatcherDBReader'
ORDER BY sp.class_desc, sp.permission_name;

PRINT '';
PRINT 'Setup completo. Use connection string:';
PRINT '  Server=<host>,<port>;Database=master;User Id=WatcherDBReader;Password=<pwd>;TrustServerCertificate=yes;';
PRINT 'Ou (Windows Auth):';
PRINT '  Server=<host>,<port>;Database=master;Integrated Security=SSPI;TrustServerCertificate=yes;';

-- =============================================================================
-- ROLLBACK (cleanup) — comentado por segurança
-- =============================================================================
/*
-- Remover user de todas as BDs
USE msdb;
DROP USER IF EXISTS WatcherDBReader;

USE WatcherDB_Intelligence;
DROP USER IF EXISTS WatcherDBReader;

-- Remover login (server scope)
USE master;
DROP LOGIN WatcherDBReader;
-- ou: DROP LOGIN [<DOMAIN>\WatcherDBReader];
*/
