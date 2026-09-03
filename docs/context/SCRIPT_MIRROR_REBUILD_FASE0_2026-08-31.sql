-- Guardado do chat do owner 2026-08-31 (rasto: FIND-20260831-104).
-- Pacote de OPERADOR (corre no servidor afectado, escreve tabela de controle
-- em msdb) - NAO e' collector: identidade e permissoes fora do modelo
-- sql_monitoring (Regra de Ouro #2). Colheita para produto no FIND.
-- Veredito validado ao vivo 31/08: SharePoint fila 101 GB vs dados 6,8 GB -> REBUILD.

/* =====================================================================
   FASE 0 - Detecta os bancos com mirror SUSPENDED/DISCONNECTED e grava em msdb.dbo.MirrorRebuild.
   Rode nos DOIS lados, ANTES da fase 1 (depois do SET PARTNER OFF nao ha mais o que detectar).
   Analisa o t-log (uso, VLFs, growth, historico de log backups) e grava um alvo sugerido por banco.
   Somente leitura nos bancos; so escreve na tabela de controle.
   T-SQL puro - nao precisa de SQLCMD. Parametros no bloco CONFIG abaixo.
   ===================================================================== */
SET NOCOUNT ON;

/* Tabela de controle (DDL em batch proprio pra upgrade de versao anterior) ------- */
IF OBJECT_ID('msdb.dbo.MirrorRebuild') IS NULL
CREATE TABLE msdb.dbo.MirrorRebuild (
    db              sysname       NOT NULL PRIMARY KEY,
    detected_at     datetime      NOT NULL,
    role_at_detect  sysname       NOT NULL,   -- papel DESTE lado: PRINCIPAL ou MIRROR
    state_at_detect sysname       NOT NULL,
    safety          sysname       NULL,
    partner_url     nvarchar(260) NULL,       -- mirroring_partner_name visto DESTE lado
    log_reuse_wait  sysname       NULL,
    data_mb         bigint        NULL,
    log_mb          bigint        NULL,
    send_queue_kb   bigint        NULL,
    seed_full       nvarchar(400) NULL,
    seed_log        nvarchar(400) NULL,
    log_used_mb     bigint        NULL,
    vlfs            int           NULL,
    log_growth      nvarchar(30)  NULL,
    max_logbkp_30d_mb bigint      NULL,
    log_suggested_mb bigint       NULL,
    log_sugestao    nvarchar(200) NULL,
    phase1_at datetime NULL, phase2_at datetime NULL, phase3_at datetime NULL,
    phase4_at datetime NULL, phase5_at datetime NULL, phase6_at datetime NULL,
    notes           nvarchar(max) NULL
);
-- tabela criada por versao anterior do pacote: acrescenta as colunas do t-log
IF COL_LENGTH('msdb.dbo.MirrorRebuild', 'log_suggested_mb') IS NULL
    ALTER TABLE msdb.dbo.MirrorRebuild ADD log_used_mb bigint NULL, vlfs int NULL, log_growth nvarchar(30) NULL,
        max_logbkp_30d_mb bigint NULL, log_suggested_mb bigint NULL, log_sugestao nvarchar(200) NULL;
GO

/* ===================== CONFIG - ajuste aqui ===================== */
DECLARE @DbFilter    nvarchar(128) = N'%';   -- padrao LIKE pra restringir a deteccao (ex.: N'SharePoint%')
DECLARE @BackupDrive char(1)       = 'X';    -- drive onde as fases 2/3 gravam (so pra checar espaco)
DECLARE @MinFreeGB   int           = 20;
DECLARE @LogMinMB    int           = 512;    -- piso do alvo sugerido pro log
DECLARE @BackupPath  nvarchar(260) = N'X:\Backup\MirrorRebuild';  -- usado so pra montar os comandos prontos do panorama
DECLARE @SurveyMinMB int           = 512;    -- panorama: so lista bancos com potencial de liberar >= isso
/* =============================================================== */

SET NOCOUNT ON;
PRINT '=== FASE 0 em ' + @@SERVERNAME + ' | ' + CONVERT(varchar(19), GETDATE(), 120) + ' ===';

/* Deteccao -------------------------------------------------------------- */
IF OBJECT_ID('tempdb..#found') IS NOT NULL DROP TABLE #found;
SELECT d.name AS db, dm.mirroring_role_desc AS role_, dm.mirroring_state_desc AS state_,
       dm.mirroring_safety_level_desc AS safety, dm.mirroring_partner_name AS partner_url, d.log_reuse_wait_desc AS log_reuse_wait,
       data_mb = (SELECT SUM(size)/128 FROM sys.master_files mf WHERE mf.database_id = d.database_id AND mf.type_desc = 'ROWS'),
       log_mb  = (SELECT SUM(size)/128 FROM sys.master_files mf WHERE mf.database_id = d.database_id AND mf.type_desc = 'LOG'),
       send_queue_kb = (SELECT cntr_value FROM sys.dm_os_performance_counters pc
                        WHERE pc.object_name LIKE '%Database Mirroring%' AND pc.counter_name = 'Log Send Queue KB' AND pc.instance_name = d.name)
INTO #found
FROM sys.databases d
JOIN sys.database_mirroring dm ON dm.database_id = d.database_id
WHERE dm.mirroring_guid IS NOT NULL
  AND dm.mirroring_state_desc IN ('SUSPENDED', 'DISCONNECTED')
  AND d.name LIKE @DbFilter;

-- novos: insere. Ja detectados mas ainda sem fase 1: atualiza. Em andamento (fase1_at preenchido): nao mexe.
MERGE msdb.dbo.MirrorRebuild AS t
USING #found AS f ON f.db = t.db
WHEN NOT MATCHED THEN
    INSERT (db, detected_at, role_at_detect, state_at_detect, safety, partner_url, log_reuse_wait, data_mb, log_mb, send_queue_kb)
    VALUES (f.db, GETDATE(), f.role_, f.state_, f.safety, f.partner_url, f.log_reuse_wait, f.data_mb, f.log_mb, f.send_queue_kb)
WHEN MATCHED AND t.phase1_at IS NULL THEN
    UPDATE SET detected_at = GETDATE(), role_at_detect = f.role_, state_at_detect = f.state_, safety = f.safety,
               partner_url = f.partner_url, log_reuse_wait = f.log_reuse_wait, data_mb = f.data_mb, log_mb = f.log_mb, send_queue_kb = f.send_queue_kb;

DECLARE @n int = (SELECT COUNT(*) FROM #found);
IF @n = 0
    PRINT 'Nenhum banco com mirror SUSPENDED/DISCONNECTED encontrado em ' + @@SERVERNAME + ' (filtro ' + @DbFilter + ').';
ELSE
    PRINT CAST(@n AS varchar(5)) + ' banco(s) com problema detectado(s) e registrado(s) em msdb.dbo.MirrorRebuild.';

/* Lista de trabalho ---------------------------------------------------- */
SELECT db, role_at_detect AS papel_aqui, state_at_detect AS estado, safety, partner_url, log_reuse_wait,
       data_mb, log_mb, send_queue_kb/1024 AS send_queue_mb,
       veredito = CASE WHEN role_at_detect <> 'PRINCIPAL' THEN '(ver no principal)'
                       WHEN send_queue_kb > data_mb * 1024 THEN 'REBUILD (fila > dados)'
                       ELSE 'RESUME pode bastar (fila < dados)' END,
       phase1_at, phase2_at, phase3_at, phase4_at, phase5_at, phase6_at
FROM msdb.dbo.MirrorRebuild ORDER BY db;

/* Detalhes por banco --------------------------------------------------- */
SELECT DB_NAME(mf.database_id) AS db, mf.name AS logical_name, mf.type_desc, mf.physical_name, mf.size/128 AS size_mb
FROM sys.master_files mf JOIN msdb.dbo.MirrorRebuild r ON r.db = DB_NAME(mf.database_id)
ORDER BY db, mf.file_id;

IF OBJECT_ID('tempdb..#vlf') IS NOT NULL DROP TABLE #vlf;
CREATE TABLE #vlf (RecoveryUnitId int, FileId int, FileSize bigint, StartOffset bigint, FSeqNo int, Status int, Parity int, CreateLSN numeric(38));
IF OBJECT_ID('tempdb..#vlfsum') IS NOT NULL DROP TABLE #vlfsum;
CREATE TABLE #vlfsum (db sysname, vlfs int, vlfs_ativos int);
DECLARE @db sysname, @sql nvarchar(max);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT db FROM msdb.dbo.MirrorRebuild WHERE role_at_detect = 'PRINCIPAL' AND phase1_at IS NULL;
OPEN c; FETCH NEXT FROM c INTO @db;
WHILE @@FETCH_STATUS = 0
BEGIN
    TRUNCATE TABLE #vlf;
    SET @sql = N'DBCC LOGINFO(N''' + @db + N''') WITH NO_INFOMSGS';
    INSERT INTO #vlf EXEC (@sql);
    INSERT INTO #vlfsum SELECT @db, COUNT(*), SUM(CASE WHEN Status = 2 THEN 1 ELSE 0 END) FROM #vlf;
    FETCH NEXT FROM c INTO @db;
END
CLOSE c; DEALLOCATE c;
SELECT * FROM #vlfsum;

/* T-log: uso, historico de log backups e sugestao de alvo (so onde este lado e PRINCIPAL) ---------
   Regra: alvo = 2x o maior log backup dos ultimos 30 dias (cabe o pico + reindex), minimo @LogMinMB,
   arredondado pra cima em blocos de 512 MB. Sem historico: 10% dos dados, minimo @LogMinMB.
   Sugere shrink se log atual > 1.5x o alvo, ou se VLFs > 100 (fragmentacao), ou growth em % / < 64 MB.  */
IF OBJECT_ID('tempdb..#logspace') IS NOT NULL DROP TABLE #logspace;
CREATE TABLE #logspace (db sysname, log_size_mb float, log_used_pct float, status int);
INSERT INTO #logspace EXEC ('DBCC SQLPERF(LOGSPACE) WITH NO_INFOMSGS');

IF OBJECT_ID('tempdb..#tlog') IS NOT NULL DROP TABLE #tlog;
SELECT r.db,
       log_mb      = CAST(ls.log_size_mb AS bigint),
       log_used_mb = CAST(ls.log_size_mb * ls.log_used_pct / 100 AS bigint),
       used_pct    = CAST(ls.log_used_pct AS decimal(5,1)),
       vlfs        = v.vlfs,
       growth      = (SELECT TOP 1 CASE WHEN mf.is_percent_growth = 1 THEN CAST(mf.growth AS nvarchar(10)) + N'%' ELSE CAST(mf.growth/128 AS nvarchar(10)) + N' MB' END
                      FROM sys.master_files mf WHERE mf.database_id = DB_ID(r.db) AND mf.type_desc = 'LOG' ORDER BY mf.file_id),
       growth_ruim = (SELECT TOP 1 CASE WHEN mf.is_percent_growth = 1 OR mf.growth/128 < 64 THEN 1 ELSE 0 END
                      FROM sys.master_files mf WHERE mf.database_id = DB_ID(r.db) AND mf.type_desc = 'LOG' ORDER BY mf.file_id),
       max_logbkp_30d_mb = (SELECT MAX(b.backup_size)/1048576 FROM msdb.dbo.backupset b
                            WHERE b.database_name = r.db AND b.type = 'L' AND b.backup_start_date > DATEADD(DAY, -30, GETDATE())),
       logbkps_30d = (SELECT COUNT(*) FROM msdb.dbo.backupset b
                      WHERE b.database_name = r.db AND b.type = 'L' AND b.backup_start_date > DATEADD(DAY, -30, GETDATE())),
       recovery = CAST(DATABASEPROPERTYEX(r.db, 'Recovery') AS nvarchar(20))
INTO #tlog
FROM msdb.dbo.MirrorRebuild r
JOIN #logspace ls ON ls.db = r.db
LEFT JOIN #vlfsum v ON v.db = r.db
WHERE r.role_at_detect = 'PRINCIPAL' AND r.phase1_at IS NULL;

ALTER TABLE #tlog ADD suggested_mb bigint, sugestao nvarchar(200);

UPDATE #tlog SET suggested_mb =
    CEILING(
        CASE WHEN max_logbkp_30d_mb IS NOT NULL
             THEN (CASE WHEN max_logbkp_30d_mb * 2 > @LogMinMB THEN max_logbkp_30d_mb * 2 ELSE @LogMinMB END)
             ELSE (CASE WHEN (SELECT data_mb FROM msdb.dbo.MirrorRebuild r WHERE r.db = #tlog.db) * 0.10 > @LogMinMB
                        THEN (SELECT data_mb FROM msdb.dbo.MirrorRebuild r WHERE r.db = #tlog.db) * 0.10 ELSE @LogMinMB END)
        END / 512.0) * 512;

UPDATE #tlog SET sugestao =
    CASE WHEN log_mb > suggested_mb * 1.5
              THEN 'SHRINK: log ' + CAST(log_mb AS nvarchar(20)) + ' MB (' + CAST(used_pct AS nvarchar(10)) + '% usado) -> alvo ' + CAST(suggested_mb AS nvarchar(20)) + ' MB'
         WHEN ISNULL(vlfs, 0) > 100
              THEN 'SHRINK+REGROW: ' + CAST(vlfs AS nvarchar(10)) + ' VLFs (fragmentado); tamanho ja ok (' + CAST(log_mb AS nvarchar(20)) + ' MB)'
         WHEN growth_ruim = 1
              THEN 'so ajustar FILEGROWTH (' + growth + ' e ruim; use 512 MB fixo)'
         ELSE 'log ok - fase 2 pode ser pulada pra este banco' END
    + CASE WHEN max_logbkp_30d_mb IS NULL THEN ' [sem log backup em msdb nos ultimos 30d - alvo estimado por 10% dos dados]' ELSE '' END
    + CASE WHEN recovery <> 'FULL' THEN ' [recovery ' + recovery + '?! mirroring exige FULL]' ELSE '' END;

UPDATE r SET log_mb = t.log_mb, log_used_mb = t.log_used_mb, vlfs = t.vlfs, log_growth = t.growth,
             max_logbkp_30d_mb = t.max_logbkp_30d_mb, log_suggested_mb = t.suggested_mb, log_sugestao = t.sugestao
FROM msdb.dbo.MirrorRebuild r JOIN #tlog t ON t.db = r.db;

SELECT db, log_mb, log_used_mb, used_pct, vlfs, growth, logbkps_30d, max_logbkp_30d_mb, suggested_mb AS alvo_sugerido_mb, sugestao,
       comando_fase2 = N'-- executado pela fase 2 APOS o SET PARTNER OFF (o log nao trunca antes): ' + CHAR(10)
                     + N'BACKUP LOG ' + QUOTENAME(db) + N' TO DISK = N''' + @BackupPath + N'\' + db + N'_log_shrink.trn'' WITH CHECKSUM, COMPRESSION; '
                     + N'USE ' + QUOTENAME(db) + N'; DBCC SHRINKFILE (N''' + (SELECT TOP 1 mf.name FROM sys.master_files mf WHERE mf.database_id = DB_ID(#tlog.db) AND mf.type_desc = 'LOG' ORDER BY mf.file_id) + N''', ' + CAST(suggested_mb AS nvarchar(20)) + N');'
FROM #tlog ORDER BY db;
PRINT 'Sugestao de alvo do log gravada em MirrorRebuild.log_suggested_mb - a fase 2 usa quando @LogTargetMB = 0.';
PRINT 'Nota: com o mirror suspenso o log_used_mb esta inflado pela fila de envio; o alvo vem do historico de backups, nao do uso atual.';

/* Instancia: endpoint, conexoes, disco, defaults ----------------------------- */
SELECT e.name, te.port, e.state_desc, e.role_desc, e.connection_auth_desc, e.encryption_algorithm_desc
FROM sys.database_mirroring_endpoints e JOIN sys.tcp_endpoints te ON te.endpoint_id = e.endpoint_id;

SELECT state_desc AS connection_state, login_state_desc, principal_name, last_activity_time, total_bytes_sent, total_bytes_received
FROM sys.dm_db_mirroring_connections;

IF OBJECT_ID('tempdb..#drives') IS NOT NULL DROP TABLE #drives;
CREATE TABLE #drives (drive char(1), mb_free bigint);
INSERT INTO #drives EXEC master.dbo.xp_fixeddrives;
SELECT drive, mb_free, CAST(mb_free/1024.0 AS decimal(10,1)) AS gb_free,
       CASE WHEN drive = @BackupDrive AND mb_free < @MinFreeGB*1024 THEN '<<< ABAIXO DO MINIMO PRA BACKUP' ELSE '' END AS alerta
FROM #drives ORDER BY drive;


/* ============================================================================
   PANORAMA DE T-LOG DA INSTANCIA (todos os bancos online, exceto tempdb)
   O drive de log e compartilhado - outros bancos podem merecer shrink tambem.
   Mesma regra de alvo (2x maior log backup 30d, piso @LogMinMB; sem historico: 10% dos dados).
   Lista so quem pode liberar >= @SurveyMinMB. O comando vem pronto, mas a execucao e
   decisao sua e FORA do fluxo das fases (bancos saudaveis nao passam pelas fases 1-6).
   REGRA DE OURO: nao encolha log que esta no tamanho de trabalho - ele so vai crescer
   de novo, pausando writes no growth. Potencial real = log muito acima do historico.
   ============================================================================ */
IF OBJECT_ID('tempdb..#survey') IS NOT NULL DROP TABLE #survey;
SELECT d.name AS db,
       log_logical = (SELECT TOP 1 mf2.name FROM sys.master_files mf2 WHERE mf2.database_id = d.database_id AND mf2.type_desc = 'LOG' ORDER BY mf2.file_id),
       drive   = UPPER(LEFT((SELECT TOP 1 mf2.physical_name FROM sys.master_files mf2 WHERE mf2.database_id = d.database_id AND mf2.type_desc = 'LOG' ORDER BY mf2.file_id), 1)),
       log_mb  = (SELECT SUM(mf2.size)/128 FROM sys.master_files mf2 WHERE mf2.database_id = d.database_id AND mf2.type_desc = 'LOG'),
       data_mb = (SELECT SUM(mf2.size)/128 FROM sys.master_files mf2 WHERE mf2.database_id = d.database_id AND mf2.type_desc = 'ROWS'),
       used_pct = CAST(ls.log_used_pct AS decimal(5,1)),
       recovery = CAST(DATABASEPROPERTYEX(d.name, 'Recovery') AS nvarchar(20)),
       maxbkp_30d_mb = (SELECT MAX(b.backup_size)/1048576 FROM msdb.dbo.backupset b
                        WHERE b.database_name = d.name AND b.type = 'L' AND b.backup_start_date > DATEADD(DAY, -30, GETDATE())),
       mirror_state = dm.mirroring_state_desc
INTO #survey
FROM sys.databases d
JOIN #logspace ls ON ls.db = d.name
LEFT JOIN sys.database_mirroring dm ON dm.database_id = d.database_id AND dm.mirroring_guid IS NOT NULL
WHERE d.state_desc = 'ONLINE' AND d.name <> 'tempdb';

ALTER TABLE #survey ADD suggested_mb bigint, potencial_mb bigint, obs nvarchar(200), comando nvarchar(700);

UPDATE #survey SET suggested_mb =
    CEILING(
        CASE WHEN maxbkp_30d_mb IS NOT NULL
             THEN (CASE WHEN maxbkp_30d_mb * 2 > @LogMinMB THEN maxbkp_30d_mb * 2 ELSE @LogMinMB END)
             ELSE (CASE WHEN ISNULL(data_mb, 0) * 0.10 > @LogMinMB THEN data_mb * 0.10 ELSE @LogMinMB END)
        END / 512.0) * 512;

UPDATE #survey SET
    potencial_mb = CASE WHEN log_mb > suggested_mb * 1.5 THEN log_mb - suggested_mb ELSE 0 END,
    obs = CASE WHEN mirror_state IS NOT NULL AND mirror_state <> 'SYNCHRONIZED'
                    THEN 'MIRROR COM PROBLEMA - use as fases 1-6; o log nao trunca antes do SET PARTNER OFF'
               WHEN mirror_state = 'SYNCHRONIZED' THEN 'espelhado e saudavel - shrink ok, o mirror replica'
               WHEN recovery <> 'FULL' THEN 'recovery ' + recovery + ' - shrink direto, sem BACKUP LOG'
               WHEN maxbkp_30d_mb IS NULL THEN 'FULL sem log backup em 30d?! confira a cadeia antes de qualquer coisa'
               ELSE '' END,
    comando = CASE WHEN recovery = 'FULL' AND (mirror_state IS NULL OR mirror_state = 'SYNCHRONIZED')
                   THEN N'BACKUP LOG ' + QUOTENAME(db) + N' TO DISK = N''' + @BackupPath + N'\' + db + N'_log.trn'' WITH CHECKSUM, COMPRESSION; '
                   ELSE N'' END
            + N'USE ' + QUOTENAME(db) + N'; DBCC SHRINKFILE (N''' + log_logical + N''', ' + CAST(suggested_mb AS nvarchar(20)) + N');';

SELECT db, drive, log_mb, used_pct, recovery, maxbkp_30d_mb, suggested_mb AS alvo_mb, potencial_mb AS libera_mb, mirror_state, obs, comando
FROM #survey
WHERE potencial_mb >= @SurveyMinMB
ORDER BY potencial_mb DESC;

-- rollup por drive: quanto o shrink de todo mundo liberaria vs o que ha livre hoje
SELECT s.drive, dr.mb_free AS livre_hoje_mb, COUNT(*) AS bancos_com_potencial, SUM(s.potencial_mb) AS potencial_total_mb
FROM #survey s LEFT JOIN #drives dr ON dr.drive = s.drive
WHERE s.potencial_mb >= @SurveyMinMB
GROUP BY s.drive, dr.mb_free
ORDER BY potencial_total_mb DESC;

SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(260)) AS default_data_path,
       CAST(SERVERPROPERTY('InstanceDefaultLogPath')  AS nvarchar(260)) AS default_log_path,
       CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(30))           AS versao;

/* Errorlog: quando/por que suspendeu (ultimos 7 logs) ------------------------ */
IF OBJECT_ID('tempdb..#log') IS NOT NULL DROP TABLE #log;
CREATE TABLE #log (LogDate datetime, ProcessInfo nvarchar(50), Text nvarchar(max), LogNo int NULL);
DECLARE @i int = 0;
WHILE @i <= 6
BEGIN
    BEGIN TRY
        INSERT INTO #log (LogDate, ProcessInfo, Text) EXEC master.dbo.xp_readerrorlog @i, 1, N'mirroring';
        UPDATE #log SET LogNo = @i WHERE LogNo IS NULL;
    END TRY
    BEGIN CATCH BREAK; END CATCH
    SET @i += 1;
END
SELECT LogNo, LogDate, Text FROM #log
WHERE Text LIKE '%suspend%' OR Text LIKE '%error%' OR Text LIKE '%fail%' OR Text LIKE '%disconnect%'
ORDER BY LogDate DESC;
PRINT 'FASE 0 concluida em ' + @@SERVERNAME + '. Rode tambem no outro lado antes da fase 1.';
GO
