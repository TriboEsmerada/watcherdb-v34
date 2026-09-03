/*=============================================================================
  SHRINK_DATA_PLAN_GENERATOR.sql  (v3.1)
  Gera o PLANO de shrink de DATA FILES da instância - NADA é executado.

  CHANGELOG v3.1 (revisão Salomão sobre v3 + output sqlidsprd03):
    [F5-bis] FIX ESTRUTURAL do Msg 207: os DROPs agora vivem num BATCH
         PRÓPRIO separado por GO, ANTES do batch principal. Motivo: o Msg 207
         é erro de COMPILAÇÃO - referências de coluna a temp table JÁ
         EXISTENTE fazem bind imediato ao schema existente; a resolução
         diferida só vale p/ tabelas inexistentes. DROPs dentro do batch
         nunca executam porque o batch morre no compile. CREATE TABLE
         explícito (v3 [F5]) não resolve isso - o prelúdio com GO sim.
         NOTA: GO é separador do SSMS/sqlcmd/Invoke-SqlCmd, não T-SQL.
         Se embutir este script em sp_executesql, executar prelúdio e corpo
         como comandos separados.
    [G1] Guard SEM DADOS: used_mb/pct_livre NULL (FILEPROPERTY pode falhar
         em edge cases) -> classe 'SEM DADOS (verificar)' em vez de cair no
         ELSE CANDIDATO com alvo NULL (que geraria DBCC SHRINKFILE quebrado).
    [G2] Desempate da moda por growth_mb DESC: em empate, o MAIOR growth
         vence - p/ arquivos grandes, growth pequeno demais = crescimento
         aos soluços (pior que espaço ocioso).
    [G3] CASE reordenado: work-area e nome-TEMP testados ANTES de VAZIO.
         Arquivo vazio de work-area é work-area (tanque em repouso), não
         candidato a REMOVE FILE. (Bug do output sqlidsprd03: MSTR_TEMPDB
         inteiro, used 1-4 MB, caiu no [C0] com 18 comandos de remoção.)
    [G4] Growth com FONTE ÚNICA por conjunto: [B3] e [E] emitem o MESMO
         valor p/ arquivos de conjuntos multi-arquivo:
         growth_final = MAX(moda do conjunto, régua pelo MAIOR arquivo do
         conjunto). Elimina o conflito v3 (B3 dizia 100 MB, E dizia 1 GB
         p/ o mesmo filegroup). Arquivo solitário: régua individual.
    [G5] Guard file_id = 1 no [C0]: REMOVE FILE do arquivo primário é
         inexecutável (restrição do engine) - vira comentário explicativo.

  Herdado v3: bucket geométrico [F1], gate work-area MIN(pct)>=95 [F2],
  classe SYSTEM DB [F3], moda [F4], sintaxe por versão, alvo uniforme por
  filegroup na passada 2, TRUNCATEONLY sempre primeiro.

  SEGURANÇA: 100% read-only. Compatível SQL 2012-2025. Rodar por instância.
  NÃO executar os comandos gerados em volume com incidente de storage aberto.
=============================================================================*/

------------------------------------------------------------------------------
-- PRELÚDIO [F5-bis]: batch próprio de limpeza. NÃO REMOVER O GO.
------------------------------------------------------------------------------
IF OBJECT_ID('tempdb..#files')       IS NOT NULL DROP TABLE #files;
IF OBJECT_ID('tempdb..#workarea')    IS NOT NULL DROP TABLE #workarea;
IF OBJECT_ID('tempdb..#plan')        IS NOT NULL DROP TABLE #plan;
IF OBJECT_ID('tempdb..#alvo_fg')     IS NOT NULL DROP TABLE #alvo_fg;
IF OBJECT_ID('tempdb..#growth_moda') IS NOT NULL DROP TABLE #growth_moda;
IF OBJECT_ID('tempdb..#growth_set')  IS NOT NULL DROP TABLE #growth_set;
GO
------------------------------------------------------------------------------
-- BATCH PRINCIPAL (compila já sem temp tables herdadas)
------------------------------------------------------------------------------
SET NOCOUNT ON;

------------------------------------------------------------------------------
-- PARÂMETROS
------------------------------------------------------------------------------
DECLARE @PctLivreMinimo   decimal(5,2) = 50.0;   -- critério de candidato
DECLARE @FolgaPct         decimal(5,2) = 30.0;   -- folga sobre o usado (alvo passada 2)
DECLARE @FatiaGB          int          = 5;      -- fatia p/ shrink incremental (< 2022)
DECLARE @MinGanhoGB       decimal(12,2)= 10.0;   -- ignora ganho menor que isso
DECLARE @MinArqsWorkArea  int          = 4;      -- N mínimo de arqs ~iguais p/ flag work-area
DECLARE @TolerIgualPct    decimal(5,2) = 5.0;    -- tolerância de "tamanho igual" (%)
DECLARE @WorkAreaMinLivre decimal(5,2) = 95.0;   -- work-area = conjunto c/ TODOS >= isso
DECLARE @VazioMB          bigint       = 50;     -- used <= isso = "arquivo vazio"

DECLARE @MajorVersion int =
    TRY_CONVERT(int, PARSENAME(CONVERT(nvarchar(30), SERVERPROPERTY('ProductVersion')), 4));
DECLARE @Is2022Plus bit = CASE WHEN @MajorVersion >= 16 THEN 1 ELSE 0 END;

------------------------------------------------------------------------------
-- ESTRUTURAS (schema explícito; DROPs duplicados são inofensivos e cobrem
-- re-execução do batch principal na mesma sessão com o MESMO schema)
------------------------------------------------------------------------------
IF OBJECT_ID('tempdb..#files')       IS NOT NULL DROP TABLE #files;
IF OBJECT_ID('tempdb..#workarea')    IS NOT NULL DROP TABLE #workarea;
IF OBJECT_ID('tempdb..#plan')        IS NOT NULL DROP TABLE #plan;
IF OBJECT_ID('tempdb..#alvo_fg')     IS NOT NULL DROP TABLE #alvo_fg;
IF OBJECT_ID('tempdb..#growth_moda') IS NOT NULL DROP TABLE #growth_moda;
IF OBJECT_ID('tempdb..#growth_set')  IS NOT NULL DROP TABLE #growth_set;

CREATE TABLE #files (
    db_name           sysname       NOT NULL,
    is_system_db      bit           NOT NULL,
    file_id           int           NOT NULL,
    logical_name      sysname       NOT NULL,
    physical_name     nvarchar(520) NOT NULL,
    drive             nchar(2)      NULL,
    filegroup_name    sysname       NULL,
    files_in_fg       int           NULL,
    size_mb           bigint        NOT NULL,
    used_mb           bigint        NULL,
    free_mb           bigint        NULL,
    pct_livre         decimal(5,2)  NULL,
    growth_mb         bigint        NULL,    -- NULL quando crescimento em %
    growth_desc       nvarchar(60)  NULL,
    is_percent_growth bit           NOT NULL,
    ag_role           nvarchar(60)  NULL,
    size_bucket       int           NULL
);

CREATE TABLE #workarea (
    db_name     sysname NOT NULL,
    size_bucket int     NOT NULL,
    qt_arquivos int     NOT NULL,
    min_livre   decimal(5,2) NULL,
    PRIMARY KEY (db_name, size_bucket)
);

CREATE TABLE #plan (
    db_name            sysname       NOT NULL,
    is_system_db       bit           NOT NULL,
    file_id            int           NOT NULL,
    logical_name       sysname       NOT NULL,
    drive              nchar(2)      NULL,
    filegroup_name     sysname       NULL,
    files_in_fg        int           NULL,
    size_mb            bigint        NOT NULL,
    used_mb            bigint        NULL,
    pct_livre          decimal(5,2)  NULL,
    growth_mb          bigint        NULL,
    growth_desc        nvarchar(60)  NULL,
    is_percent_growth  bit           NOT NULL,
    ag_role            nvarchar(60)  NULL,
    alvo_gb_individual decimal(12,2) NULL,
    ganho_potencial_gb decimal(12,2) NULL,
    classificacao      nvarchar(60)  NOT NULL
);

CREATE TABLE #alvo_fg (
    db_name          sysname NOT NULL,
    filegroup_name   sysname NULL,
    alvo_gb_uniforme decimal(12,2) NOT NULL
);

CREATE TABLE #growth_moda (
    db_name        sysname NOT NULL,
    filegroup_name sysname NULL,
    growth_moda_mb bigint  NOT NULL
);

-- [G4] fonte única de growth p/ conjuntos multi-arquivo
CREATE TABLE #growth_set (
    db_name         sysname NOT NULL,
    filegroup_name  sysname NULL,
    qt_arquivos     int     NOT NULL,
    growth_final_mb bigint  NOT NULL
);

------------------------------------------------------------------------------
-- COLETA
------------------------------------------------------------------------------
DECLARE @db sysname, @sql nvarchar(max);
DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
    SELECT d.name
    FROM sys.databases AS d
    WHERE d.state_desc = N'ONLINE'
      AND d.is_read_only = 0
      AND DATABASEPROPERTYEX(d.name, 'Updateability') = N'READ_WRITE'
      AND d.name <> N'tempdb';
OPEN cur;
FETCH NEXT FROM cur INTO @db;
WHILE @@FETCH_STATUS = 0
BEGIN
    BEGIN TRY
        SET @sql = N'
        USE ' + QUOTENAME(@db) + N';
        INSERT INTO #files (db_name, is_system_db, file_id, logical_name, physical_name,
                            drive, filegroup_name, files_in_fg, size_mb, used_mb, free_mb,
                            pct_livre, growth_mb, growth_desc, is_percent_growth, ag_role)
        SELECT  DB_NAME(),
                CASE WHEN DB_ID() <= 4 THEN 1 ELSE 0 END,
                f.file_id,
                f.name,
                f.physical_name,
                UPPER(LEFT(f.physical_name, 2)),
                fg.name,
                (SELECT COUNT(*) FROM sys.database_files f2
                  WHERE f2.data_space_id = f.data_space_id AND f2.type_desc = N''ROWS''),
                f.size / 128,
                FILEPROPERTY(f.name, ''SpaceUsed'') / 128,
                (f.size - FILEPROPERTY(f.name, ''SpaceUsed'')) / 128,
                CAST(100.0 * (f.size - FILEPROPERTY(f.name, ''SpaceUsed'')) / NULLIF(f.size,0) AS decimal(5,2)),
                CASE WHEN f.is_percent_growth = 1 THEN NULL ELSE f.growth / 128 END,
                CASE WHEN f.is_percent_growth = 1
                     THEN CAST(f.growth AS nvarchar(10)) + N''%''
                     ELSE CAST(f.growth / 128 AS nvarchar(20)) + N'' MB'' END,
                f.is_percent_growth,
                ISNULL((SELECT ars.role_desc
                        FROM sys.dm_hadr_database_replica_states drs
                        JOIN sys.dm_hadr_availability_replica_states ars
                          ON ars.replica_id = drs.replica_id
                        WHERE drs.database_id = DB_ID() AND drs.is_local = 1), N''-'')
        FROM    sys.database_files AS f
        LEFT JOIN sys.filegroups AS fg ON fg.data_space_id = f.data_space_id
        WHERE   f.type_desc = N''ROWS'';';
        EXEC sp_executesql @sql;
    END TRY
    BEGIN CATCH
        PRINT N'-- (pulado ' + @db + N': ' + ERROR_MESSAGE() + N')';
    END CATCH;
    FETCH NEXT FROM cur INTO @db;
END;
CLOSE cur; DEALLOCATE cur;

------------------------------------------------------------------------------
-- [F1] BUCKET GEOMÉTRICO
------------------------------------------------------------------------------
UPDATE #files
SET size_bucket = FLOOR(LOG(NULLIF(CAST(size_mb AS float), 0), 1.0 + @TolerIgualPct/100.0));

------------------------------------------------------------------------------
-- [F2] WORK-AREA: conjunto de >= N arquivos ~iguais, TODOS com tanque vazio
------------------------------------------------------------------------------
INSERT INTO #workarea (db_name, size_bucket, qt_arquivos, min_livre)
SELECT  f.db_name, f.size_bucket, COUNT(*), MIN(f.pct_livre)
FROM    #files AS f
WHERE   f.is_system_db = 0
  AND   f.size_bucket IS NOT NULL
GROUP BY f.db_name, f.size_bucket
HAVING  COUNT(*) >= @MinArqsWorkArea
   AND  MIN(f.pct_livre) >= @WorkAreaMinLivre;

------------------------------------------------------------------------------
-- CLASSIFICAÇÃO
-- Ordem [G3]: SYSTEM -> SEM DADOS [G1] -> WORK-AREA -> NOME TEMP -> VAZIO
--             -> régua normal. Arquivo vazio de work-area fica work-area.
------------------------------------------------------------------------------
INSERT INTO #plan (db_name, is_system_db, file_id, logical_name, drive,
                   filegroup_name, files_in_fg, size_mb, used_mb, pct_livre,
                   growth_mb, growth_desc, is_percent_growth, ag_role,
                   alvo_gb_individual, ganho_potencial_gb, classificacao)
SELECT  f.db_name, f.is_system_db, f.file_id, f.logical_name, f.drive,
        f.filegroup_name, f.files_in_fg, f.size_mb, f.used_mb, f.pct_livre,
        f.growth_mb, f.growth_desc, f.is_percent_growth, f.ag_role,
        CAST(f.used_mb * (1.0 + @FolgaPct/100.0) / 1024 AS decimal(12,2)),
        CAST((f.size_mb - f.used_mb * (1.0 + @FolgaPct/100.0)) / 1024 AS decimal(12,2)),
        CASE
          WHEN f.is_system_db = 1
            THEN N'SYSTEM DB (so autogrowth)'
          WHEN f.used_mb IS NULL OR f.pct_livre IS NULL                 -- [G1]
            THEN N'SEM DADOS (verificar)'
          WHEN wa.db_name IS NOT NULL                                   -- [G3]
            THEN N'CONFIRMAR PICO (work-area?)'
          WHEN f.logical_name LIKE N'%TEMP%' OR f.logical_name LIKE N'%STAGE%'
            OR f.logical_name LIKE N'%STG%'  OR f.logical_name LIKE N'%WRK%'
            OR f.db_name      LIKE N'%TEMP%'                            -- [G3]
            THEN N'CONFIRMAR PICO (nome TEMP/STG)'
          WHEN f.used_mb <= @VazioMB AND f.pct_livre >= 99.0
            THEN N'VAZIO (avaliar REMOVE FILE)'
          WHEN f.pct_livre < 30.0
            THEN N'NAO TOCAR (bem dimensionado)'
          WHEN f.pct_livre < @PctLivreMinimo
            THEN N'OBSERVAR (livre entre 30% e criterio)'
          WHEN (f.size_mb - f.used_mb * (1.0 + @FolgaPct/100.0)) / 1024 < @MinGanhoGB
            THEN N'IGNORAR (ganho pequeno)'
          ELSE N'CANDIDATO'
        END
FROM    #files AS f
LEFT JOIN #workarea AS wa
       ON wa.db_name = f.db_name
      AND wa.size_bucket = f.size_bucket;

-- Alvo uniforme por filegroup (proportional fill) - candidatos apenas
INSERT INTO #alvo_fg (db_name, filegroup_name, alvo_gb_uniforme)
SELECT  db_name, filegroup_name, MAX(alvo_gb_individual)
FROM    #plan
WHERE   classificacao = N'CANDIDATO'
GROUP BY db_name, filegroup_name
HAVING  COUNT(*) > 1;

-- [F4+G2] Moda do growth por conjunto (empate -> MAIOR growth)
INSERT INTO #growth_moda (db_name, filegroup_name, growth_moda_mb)
SELECT  db_name, filegroup_name, growth_mb
FROM (
    SELECT  p.db_name, p.filegroup_name, p.growth_mb,
            ROW_NUMBER() OVER (
                PARTITION BY p.db_name, p.filegroup_name
                ORDER BY COUNT(*) DESC, p.growth_mb DESC) AS rn      -- [G2]
    FROM    #plan AS p
    WHERE   p.is_system_db = 0
      AND   p.growth_mb IS NOT NULL
    GROUP BY p.db_name, p.filegroup_name, p.growth_mb
) AS x
WHERE x.rn = 1;

-- [G4] growth_final por conjunto = MAX(moda, régua pelo MAIOR arquivo)
--      Fonte única usada por [B3] e [E] - nunca mais comandos conflitantes.
INSERT INTO #growth_set (db_name, filegroup_name, qt_arquivos, growth_final_mb)
SELECT  p.db_name, p.filegroup_name, COUNT(*),
        CASE WHEN ISNULL(gm.growth_moda_mb, 0) >=
                  CASE WHEN MAX(p.size_mb) >= 512000 THEN 4096
                       WHEN MAX(p.size_mb) >= 51200  THEN 2048
                       ELSE 1024 END
             THEN gm.growth_moda_mb
             ELSE CASE WHEN MAX(p.size_mb) >= 512000 THEN 4096
                       WHEN MAX(p.size_mb) >= 51200  THEN 2048
                       ELSE 1024 END
        END
FROM    #plan AS p
LEFT JOIN #growth_moda AS gm
       ON gm.db_name = p.db_name
      AND ISNULL(gm.filegroup_name, N'') = ISNULL(p.filegroup_name, N'')
WHERE   p.is_system_db = 0
GROUP BY p.db_name, p.filegroup_name, gm.growth_moda_mb
HAVING  COUNT(*) >= 2;

------------------------------------------------------------------------------
-- [A] CABEÇALHO E RESUMO
------------------------------------------------------------------------------
PRINT REPLICATE(N'=', 78);
PRINT N'PLANO DE SHRINK (DATA) v3.1 - ' + @@SERVERNAME
    + N' | versao major: ' + CAST(@MajorVersion AS nvarchar(5))
    + CASE WHEN @Is2022Plus = 1 THEN N' (WAIT_AT_LOW_PRIORITY disponivel)'
           ELSE N' (usar LOCK_TIMEOUT + fatias)' END
    + N' | ' + CONVERT(nvarchar(30), SYSDATETIME(), 120);
PRINT REPLICATE(N'=', 78);
PRINT N'';
PRINT N'[A] Resumo por classificação:';

SELECT  classificacao,
        COUNT(*) AS arquivos,
        CAST(SUM(size_mb)/1024.0 AS decimal(12,2)) AS total_gb,
        CAST(SUM(CASE WHEN classificacao = N'CANDIDATO'
                      THEN ganho_potencial_gb ELSE 0 END) AS decimal(12,2)) AS ganho_estimado_gb
FROM    #plan
GROUP BY classificacao
ORDER BY MIN(CASE classificacao
               WHEN N'CANDIDATO' THEN 1
               WHEN N'VAZIO (avaliar REMOVE FILE)' THEN 2
               WHEN N'CONFIRMAR PICO (work-area?)' THEN 3
               WHEN N'CONFIRMAR PICO (nome TEMP/STG)' THEN 4
               WHEN N'OBSERVAR (livre entre 30% e criterio)' THEN 5
               WHEN N'IGNORAR (ganho pequeno)' THEN 6
               WHEN N'SEM DADOS (verificar)' THEN 7
               WHEN N'SYSTEM DB (so autogrowth)' THEN 8
               ELSE 9 END);

PRINT N'';
PRINT N'[B] Candidatos aprovados (maior ganho primeiro):';

SELECT  db_name, logical_name, drive, filegroup_name, ag_role,
        CAST(size_mb/1024.0 AS decimal(12,2)) AS size_gb,
        CAST(used_mb/1024.0 AS decimal(12,2)) AS used_gb,
        pct_livre, alvo_gb_individual, ganho_potencial_gb, growth_desc
FROM    #plan
WHERE   classificacao = N'CANDIDATO'
ORDER BY ganho_potencial_gb DESC;

PRINT N'';
PRINT N'[B2] Retidos para validação com o dono da aplicação';
PRINT N'     (work-area tanque-vazio / nome TEMP: confirmar PICO antes)';
PRINT N'     + arquivos SEM DADOS (coleta falhou - investigar):';

SELECT  db_name, logical_name, classificacao,
        CAST(size_mb/1024.0 AS decimal(12,2)) AS size_gb,
        CAST(used_mb/1024.0 AS decimal(12,2)) AS used_gb,
        pct_livre, growth_desc
FROM    #plan
WHERE   classificacao IN (N'CONFIRMAR PICO (work-area?)',
                          N'CONFIRMAR PICO (nome TEMP/STG)',
                          N'SEM DADOS (verificar)')
ORDER BY classificacao, db_name, logical_name;

------------------------------------------------------------------------------
-- [B3] GROWTH DESIGUAL EM CONJUNTOS - uniformização pelo growth_final [G4]
------------------------------------------------------------------------------
PRINT N'';
PRINT N'[B3] Growth desigual em conjuntos do mesmo filegroup (proportional';
PRINT N'     fill). Valor = MAX(moda do conjunto, régua pelo maior arquivo)';
PRINT N'     - o MESMO que a passada [E] usa. Executar uma vez só.';

SELECT  p.db_name, p.filegroup_name, p.logical_name,
        p.growth_desc AS growth_atual,
        CAST(gs.growth_final_mb AS nvarchar(20)) + N' MB' AS growth_sugerido,
        N'ALTER DATABASE ' + QUOTENAME(p.db_name) + N' MODIFY FILE (NAME = N'
      + QUOTENAME(p.logical_name, '''') + N', FILEGROWTH = '
      + CAST(gs.growth_final_mb AS nvarchar(20)) + N'MB);' AS comando_uniformizar
FROM    #plan AS p
JOIN    #growth_set AS gs
     ON gs.db_name = p.db_name
    AND ISNULL(gs.filegroup_name, N'') = ISNULL(p.filegroup_name, N'')
WHERE   p.is_system_db = 0
  AND   ISNULL(p.growth_mb, -1) <> gs.growth_final_mb
ORDER BY p.db_name, p.filegroup_name, p.logical_name;

------------------------------------------------------------------------------
-- [C0] ARQUIVOS VAZIOS: EMPTYFILE + REMOVE FILE (com checklist e guard [G5])
------------------------------------------------------------------------------
PRINT N'';
PRINT N'[C0] Arquivos ~vazios - avaliar REMOÇÃO em vez de shrink.';
PRINT N'--  CHECKLIST: 1) files_in_fg > 1? (senão: verificar objetos do FG)';
PRINT N'--             2) EMPTYFILE migra resíduos p/ os demais arquivos do FG.';
PRINT N'--  (work-areas e nomes TEMP já foram retidos em [B2] - não aparecem aqui)';

SELECT  db_name, logical_name, filegroup_name, files_in_fg,
        CAST(size_mb/1024.0 AS decimal(12,2)) AS size_gb,
        used_mb,
        CASE WHEN file_id = 1                                          -- [G5]
             THEN N'-- ' + QUOTENAME(db_name) + N'.' + QUOTENAME(logical_name)
                + N': arquivo primario (file_id=1) NAO pode ser removido pelo'
                + N' engine. Usar TRUNCATEONLY se quiser reduzir.'
             ELSE
             N'USE ' + QUOTENAME(db_name) + N'; DBCC SHRINKFILE (N'
           + QUOTENAME(logical_name, '''') + N', EMPTYFILE); ALTER DATABASE '
           + QUOTENAME(db_name) + N' REMOVE FILE ' + QUOTENAME(logical_name) + N';'
           + CASE WHEN files_in_fg <= 1
                  THEN N'  -- ATENCAO: unico arquivo do FG! Verificar objetos antes.'
                  ELSE N'' END
        END AS comando_remocao
FROM    #plan
WHERE   classificacao = N'VAZIO (avaliar REMOVE FILE)'
ORDER BY db_name, logical_name;

------------------------------------------------------------------------------
-- [C] PASSADA 1: TRUNCATEONLY
------------------------------------------------------------------------------
PRINT N'';
PRINT N'[C] PASSADA 1 - TRUNCATEONLY (zero movimentação; janela tranquila):';
PRINT N'--  Após executar, RE-RODAR este gerador antes da passada 2.';

SELECT  N'USE ' + QUOTENAME(db_name) + N'; DBCC SHRINKFILE (N'
      + QUOTENAME(logical_name, '''') + N', TRUNCATEONLY);' AS comando_passada1
FROM    #plan
WHERE   classificacao = N'CANDIDATO'
ORDER BY ganho_potencial_gb DESC;

------------------------------------------------------------------------------
-- [D] PASSADA 2: shrink até o alvo (uniforme por FG; sintaxe por versão)
------------------------------------------------------------------------------
PRINT N'';
PRINT N'[D] PASSADA 2 - shrink com movimentação (SÓ onde a passada 1 rendeu';
PRINT N'    pouco E o prêmio justifica). Fragmenta -> rebuild dos índices';
PRINT N'    críticos DEPOIS. Conjuntos de filegroup: alvo uniforme.';
PRINT N'--  NOTA: conjunto com membros FORA da lista de candidatos (OBSERVAR/';
PRINT N'--  retidos) fica meio-encolhido e desequilibra o proportional fill -';
PRINT N'--  nesses casos, considerar alvo manual p/ o conjunto INTEIRO.';

SELECT  p.db_name, p.logical_name,
        CASE WHEN @Is2022Plus = 1 THEN
            N'USE ' + QUOTENAME(p.db_name) + N'; DBCC SHRINKFILE (N'
          + QUOTENAME(p.logical_name, '''') + N', '
          + CAST(CAST(ISNULL(afg.alvo_gb_uniforme, p.alvo_gb_individual) * 1024 AS bigint) AS nvarchar(20))
          + N') WITH WAIT_AT_LOW_PRIORITY (ABORT_AFTER_WAIT = SELF);'
        ELSE
            N'USE ' + QUOTENAME(p.db_name) + N'; SET LOCK_TIMEOUT 5000; DBCC SHRINKFILE (N'
          + QUOTENAME(p.logical_name, '''') + N', '
          + CAST(CAST(ISNULL(afg.alvo_gb_uniforme, p.alvo_gb_individual) * 1024 AS bigint) AS nvarchar(20))
          + N');  -- executar em fatias decrescentes de ' + CAST(@FatiaGB AS nvarchar(5)) + N' GB'
        END
      + N'  -- alvo: ' + CAST(ISNULL(afg.alvo_gb_uniforme, p.alvo_gb_individual) AS nvarchar(20)) + N' GB'
      + CASE WHEN afg.alvo_gb_uniforme IS NOT NULL THEN N' (uniforme p/ o filegroup)' ELSE N'' END
        AS comando_passada2
FROM    #plan AS p
LEFT JOIN #alvo_fg AS afg
       ON afg.db_name = p.db_name
      AND ISNULL(afg.filegroup_name, N'') = ISNULL(p.filegroup_name, N'')
WHERE   p.classificacao = N'CANDIDATO'
ORDER BY p.ganho_potencial_gb DESC;

------------------------------------------------------------------------------
-- [E] PASSADA 3: autogrowth fixo - fonte única [G4]
--     Conjunto multi-arquivo -> growth_final do conjunto (= [B3])
--     Arquivo solitário       -> régua individual
--     System DB               -> 128 MB
------------------------------------------------------------------------------
PRINT N'';
PRINT N'[E] PASSADA 3 - autogrowth fixo (candidatos + system DBs + % growth).';
PRINT N'    Conjuntos usam o MESMO valor do [B3] - sem comandos conflitantes.';

SELECT  N'ALTER DATABASE ' + QUOTENAME(p.db_name) + N' MODIFY FILE (NAME = N'
      + QUOTENAME(p.logical_name, '''') + N', FILEGROWTH = '
      + CASE WHEN p.is_system_db = 1 THEN N'128MB'
             WHEN gs.growth_final_mb IS NOT NULL
                  THEN CAST(gs.growth_final_mb AS nvarchar(20)) + N'MB'   -- [G4]
             WHEN p.size_mb >= 512000 THEN N'4GB'
             WHEN p.size_mb >= 51200  THEN N'2GB'
             ELSE N'1GB' END
      + N');' AS comando_passada3
FROM    #plan AS p
LEFT JOIN #growth_set AS gs
       ON gs.db_name = p.db_name
      AND ISNULL(gs.filegroup_name, N'') = ISNULL(p.filegroup_name, N'')
      AND p.is_system_db = 0
WHERE   p.classificacao = N'CANDIDATO'
   OR   p.is_percent_growth = 1
   OR  (p.is_system_db = 1 AND (p.is_percent_growth = 1 OR p.growth_mb > 1024))
ORDER BY p.is_system_db DESC, p.db_name, p.logical_name;

PRINT N'';
PRINT REPLICATE(N'=', 78);
PRINT N'FIM. Nada foi executado. Ordem: [B3 growth] -> [C0 remoções c/';
PRINT N'checklist] -> [C truncate] -> re-rodar gerador -> [D onde restar';
PRINT N'prêmio] -> rebuild índices -> [E]. Retidos em [B2] só após confirmar';
PRINT N'pico com o dono da aplicação. System DBs: nunca shrink em lote.';
PRINT N'Não executar em volume com incidente de storage aberto.';
PRINT REPLICATE(N'=', 78);
