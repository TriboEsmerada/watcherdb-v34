/*=============================================================================
  DIAG_ERROR_824_SWEEP.sql  (v3 - SEM CHECKDB, leve para produção)
  Varredura BANCO A BANCO em busca de sinais de corrupção, sem carga de I/O.
  Compatível SQL Server 2012-2022 | Executar como sysadmin
  Output: Results to Text (Ctrl+T)

  Autor: owner (Salomão) | Guardado 2026-07-19 como ferramenta ops do WatcherDB.
  NOTA: este script é a SPEC do futuro KPI "Integridade" (ver Diário
  docs/context/CONTEXT.md 2026-07-19) — ferramenta ad-hoc sysadmin; a versão
  KPI usará os collectors existentes (SUSPECT_PAGES/ERRORLOG/DBCC_HISTORY/
  DB_SETTINGS/BACKUPS) sem privilégios novos.

  O QUE FAZ:
    [1] msdb.dbo.suspect_pages agrupado por banco (onde o 823/824 já bateu)
    [2] Caça 823/824/825 em TODOS os error logs disponíveis (xp_readerrorlog),
        com timestamp e mensagem - identifica banco, arquivo e página
    [3] Inventário por banco: PAGE_VERIFY, último CHECKDB limpo conhecido
        (dbi_dbccLastKnownGood), papel no AG, último backup FULL com checksum
    [4] Veredicto por banco: cruzamento dos sinais + prioridade de investigação

  SEGURANÇA: 100% read-only e LEVE. Nenhum CHECKDB, repair ou rebuild.
  O CHECKDB do(s) banco(s) apontados aqui deve rodar depois, em janela
  ou na secundária do AG - este script te diz ONDE gastar essa janela.
=============================================================================*/

SET NOCOUNT ON;

------------------------------------------------------------------------------
-- PARÂMETROS
------------------------------------------------------------------------------
DECLARE @DiasErrorLog int = 30;  -- olhar erros de I/O dos últimos N dias

------------------------------------------------------------------------------
-- ESTRUTURAS DE TRABALHO
------------------------------------------------------------------------------
IF OBJECT_ID('tempdb..#dbs')      IS NOT NULL DROP TABLE #dbs;
IF OBJECT_ID('tempdb..#errlog')   IS NOT NULL DROP TABLE #errlog;
IF OBJECT_ID('tempdb..#logs')     IS NOT NULL DROP TABLE #logs;
IF OBJECT_ID('tempdb..#dbinfo')   IS NOT NULL DROP TABLE #dbinfo;
IF OBJECT_ID('tempdb..#lastgood') IS NOT NULL DROP TABLE #lastgood;

CREATE TABLE #dbs (
    database_id       int           NOT NULL PRIMARY KEY,
    db_name           sysname       NOT NULL,
    size_gb           decimal(12,2) NULL,
    page_verify       nvarchar(60)  NULL,
    state_desc        nvarchar(60)  NULL,
    ag_role           nvarchar(60)  NULL,
    updateability     nvarchar(60)  NULL,
    last_good_checkdb datetime      NULL,
    last_backup_ckms  datetime      NULL,
    qt_suspect_pages  int           NULL,
    qt_erros_log      int           NULL
);

CREATE TABLE #errlog (
    LogDate     datetime       NULL,
    ProcessInfo nvarchar(100)  NULL,
    LogText     nvarchar(max)  NULL
);

CREATE TABLE #logs (ArchiveNo int, LogDate datetime, LogSizeBytes bigint);

CREATE TABLE #dbinfo (ParentObject nvarchar(255), [Object] nvarchar(255),
                      Field nvarchar(255), [Value] nvarchar(255));
CREATE TABLE #lastgood (db_name sysname, last_good datetime);

PRINT REPLICATE(N'=', 78);
PRINT N'SWEEP DE CORRUPCAO (sem CHECKDB) - Instancia: ' + @@SERVERNAME
    + N' | ' + CONVERT(nvarchar(30), SYSDATETIME(), 120);
PRINT REPLICATE(N'=', 78);

------------------------------------------------------------------------------
-- [1] SUSPECT_PAGES - registro oficial de onde o erro físico já ocorreu
------------------------------------------------------------------------------
PRINT NCHAR(13) + N'[1] msdb.dbo.suspect_pages (histórico completo, por banco):';

SELECT  DB_NAME(sp.database_id)  AS database_name,
        COUNT(*)                 AS paginas_afetadas,
        SUM(sp.error_count)      AS total_erros,
        MIN(sp.last_update_date) AS primeiro_registro,
        MAX(sp.last_update_date) AS ultimo_registro,
        STUFF((SELECT N', ' + CAST(sp2.file_id AS varchar(10)) + N':' + CAST(sp2.page_id AS varchar(20))
                     + N' (' + CASE sp2.event_type
                                    WHEN 1 THEN N'823'
                                    WHEN 2 THEN N'824 bad pageid'
                                    WHEN 3 THEN N'824 bad checksum'
                                    WHEN 4 THEN N'torn page'
                                    WHEN 5 THEN N'reparada'
                                    WHEN 7 THEN N'desalocada'
                                    ELSE CAST(sp2.event_type AS varchar(4)) END + N')'
               FROM msdb.dbo.suspect_pages AS sp2
               WHERE sp2.database_id = sp.database_id
               ORDER BY sp2.last_update_date DESC
               FOR XML PATH(N''), TYPE).value(N'.', N'nvarchar(max)'), 1, 2, N'') AS paginas
FROM    msdb.dbo.suspect_pages AS sp
GROUP BY sp.database_id
ORDER BY MAX(sp.last_update_date) DESC;

IF NOT EXISTS (SELECT 1 FROM msdb.dbo.suspect_pages)
    PRINT N'    (vazio - nenhum 823/824 registrado nesta instância)';

------------------------------------------------------------------------------
-- [2] CAÇA A 823/824/825 NOS ERROR LOGS (todos os arquivos disponíveis)
--     825 = read-retry: o SQL leu errado, tentou de novo e conseguiu.
--     É o "aviso prévio" do 824 - storage entregando lixo intermitente.
------------------------------------------------------------------------------
PRINT NCHAR(13) + N'[2] Ocorrências de 823/824/825 nos error logs (últimos '
    + CAST(@DiasErrorLog AS nvarchar(5)) + N' dias):';

INSERT INTO #logs EXEC master.dbo.xp_enumerrorlogs;

DECLARE @Arq int, @Corte datetime = DATEADD(DAY, -@DiasErrorLog, SYSDATETIME());
DECLARE cur_log CURSOR LOCAL FAST_FORWARD FOR
    SELECT ArchiveNo FROM #logs
    WHERE ISNULL(LogDate, SYSDATETIME()) >= @Corte OR ArchiveNo = 0
    ORDER BY ArchiveNo;
OPEN cur_log;
FETCH NEXT FROM cur_log INTO @Arq;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        INSERT INTO #errlog (LogDate, ProcessInfo, LogText)
        EXEC master.dbo.xp_readerrorlog @Arq, 1, N'error', N'82';
    END TRY
    BEGIN CATCH
        PRINT N'    (falha lendo error log #' + CAST(@Arq AS nvarchar(5)) + N': '
            + ERROR_MESSAGE() + N')';
    END CATCH;
    FETCH NEXT FROM cur_log INTO @Arq;
END;
CLOSE cur_log; DEALLOCATE cur_log;

-- filtra só 823/824/825 reais e dentro da janela
DELETE FROM #errlog
WHERE LogDate < @Corte
   OR (LogText NOT LIKE N'%Error: 823%'
   AND LogText NOT LIKE N'%Error: 824%'
   AND LogText NOT LIKE N'%Error: 825%'
   AND LogText NOT LIKE N'%incorrect pageid%'
   AND LogText NOT LIKE N'%incorrect checksum%'
   AND LogText NOT LIKE N'%read retry%');

SELECT  LogDate,
        CASE WHEN LogText LIKE N'%825%' OR LogText LIKE N'%read retry%'
             THEN N'825 (aviso!)'
             WHEN LogText LIKE N'%824%' OR LogText LIKE N'%incorrect%'
             THEN N'824'
             ELSE N'823' END AS erro,
        LEFT(LogText, 500)  AS mensagem
FROM    #errlog
ORDER BY LogDate DESC;

IF NOT EXISTS (SELECT 1 FROM #errlog)
    PRINT N'    (nenhuma ocorrência de 823/824/825 na janela analisada)';

------------------------------------------------------------------------------
-- [3] INVENTÁRIO POR BANCO
------------------------------------------------------------------------------
INSERT INTO #dbs (database_id, db_name, size_gb, page_verify, state_desc,
                  ag_role, updateability)
SELECT  d.database_id,
        d.name,
        CAST(SUM(mf.size) * 8.0 / 1048576.0 AS decimal(12,2)),
        d.page_verify_option_desc,
        d.state_desc,
        ISNULL(ars.role_desc, N'-'),
        CAST(DATABASEPROPERTYEX(d.name, 'Updateability') AS nvarchar(60))
FROM    sys.databases AS d
JOIN    sys.master_files AS mf ON mf.database_id = d.database_id
LEFT JOIN sys.dm_hadr_database_replica_states AS drs
        ON drs.database_id = d.database_id AND drs.is_local = 1
LEFT JOIN sys.dm_hadr_availability_replica_states AS ars
        ON ars.replica_id = drs.replica_id
WHERE   d.name <> N'tempdb'
GROUP BY d.database_id, d.name, d.page_verify_option_desc, d.state_desc,
         ars.role_desc, DATABASEPROPERTYEX(d.name, 'Updateability');

-- Último backup FULL com checksum
UPDATE t
SET    last_backup_ckms = bs.dt
FROM   #dbs AS t
CROSS APPLY (SELECT MAX(b.backup_finish_date) AS dt
             FROM msdb.dbo.backupset AS b
             WHERE b.database_name = t.db_name
               AND b.type = 'D'
               AND b.has_backup_checksums = 1) AS bs;

-- Último CHECKDB limpo conhecido (dbi_dbccLastKnownGood) - leitura de metadado, leve
DECLARE @db sysname, @sql nvarchar(max);
DECLARE cur_info CURSOR LOCAL FAST_FORWARD FOR
    SELECT db_name FROM #dbs WHERE state_desc = N'ONLINE' ORDER BY db_name;
OPEN cur_info;
FETCH NEXT FROM cur_info INTO @db;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        DELETE #dbinfo;
        SET @sql = N'DBCC DBINFO(' + QUOTENAME(@db, '''') + N') WITH TABLERESULTS, NO_INFOMSGS;';
        INSERT INTO #dbinfo EXEC sp_executesql @sql;
        INSERT INTO #lastgood (db_name, last_good)
        SELECT @db, TRY_CONVERT(datetime, [Value])
        FROM   #dbinfo
        WHERE  Field = N'dbi_dbccLastKnownGood';
    END TRY
    BEGIN CATCH
        INSERT INTO #lastgood VALUES (@db, NULL);
    END CATCH;
    FETCH NEXT FROM cur_info INTO @db;
END;
CLOSE cur_info; DEALLOCATE cur_info;

UPDATE t SET last_good_checkdb = lg.last_good
FROM #dbs t JOIN #lastgood lg ON lg.db_name = t.db_name;

-- Cruza os sinais coletados em [1] e [2]
UPDATE t
SET qt_suspect_pages = ISNULL(sp.qt, 0)
FROM #dbs t
OUTER APPLY (SELECT COUNT(*) AS qt FROM msdb.dbo.suspect_pages s
             WHERE s.database_id = t.database_id) sp;

UPDATE t
SET qt_erros_log = ISNULL(el.qt, 0)
FROM #dbs t
OUTER APPLY (SELECT COUNT(*) AS qt FROM #errlog e
             WHERE e.LogText LIKE N'%' + t.db_name + N'%'
                OR e.LogText LIKE N'%ID ' + CAST(t.database_id AS nvarchar(10)) + N'%') el;

PRINT NCHAR(13) + N'[3] Inventário por banco:';
SELECT  db_name, size_gb, state_desc, ag_role, updateability, page_verify,
        last_good_checkdb,
        DATEDIFF(DAY, last_good_checkdb, SYSDATETIME()) AS dias_sem_checkdb,
        last_backup_ckms AS ultimo_full_com_checksum,
        qt_suspect_pages, qt_erros_log
FROM    #dbs
ORDER BY qt_suspect_pages DESC, qt_erros_log DESC, ISNULL(last_good_checkdb,'1900-01-01') ASC;

------------------------------------------------------------------------------
-- [4] VEREDICTO: prioridade de investigação por banco
------------------------------------------------------------------------------
PRINT NCHAR(13) + N'[4] Veredicto - onde gastar a janela de CHECKDB:';
SELECT  db_name,
        size_gb,
        ag_role,
        CASE
          WHEN qt_suspect_pages > 0
            THEN N'P1 *** CORROMPIDO: agendar CHECKDB + plano de correção JÁ ***'
          WHEN qt_erros_log > 0
            THEN N'P2 ** erros de I/O no log: CHECKDB na próxima janela **'
          WHEN last_good_checkdb IS NULL
            THEN N'P3 * nunca validado: incluir na rotina de CHECKDB *'
          WHEN DATEDIFF(DAY, last_good_checkdb, SYSDATETIME()) > 30
            THEN N'P4 validação velha (>30d): reincluir na rotina'
          ELSE N'P5 ok'
        END AS veredicto,
        CASE WHEN page_verify <> N'CHECKSUM'
             THEN N'+ ALTER DATABASE ... SET PAGE_VERIFY CHECKSUM' ELSE N'' END AS ajuste_extra,
        CASE WHEN last_backup_ckms IS NULL
             THEN N'+ SEM full c/ CHECKSUM: page restore indisponível!' ELSE N'' END AS alerta_backup
FROM    #dbs
WHERE   state_desc = N'ONLINE'
ORDER BY CASE
          WHEN qt_suspect_pages > 0 THEN 1
          WHEN qt_erros_log > 0 THEN 2
          WHEN last_good_checkdb IS NULL THEN 3
          WHEN DATEDIFF(DAY, last_good_checkdb, SYSDATETIME()) > 30 THEN 4
          ELSE 5 END,
         size_gb DESC;

PRINT NCHAR(13) + REPLICATE(N'=', 78);
PRINT N'FIM. Este sweep NÃO valida páginas - ele aponta os bancos suspeitos.';
PRINT N'Próximo passo: DBCC CHECKDB (PHYSICAL_ONLY) nos P1/P2, em janela ou na';
PRINT N'secundária do AG. Correção: índice NC -> rebuild | dados -> page restore.';
PRINT REPLICATE(N'=', 78);
