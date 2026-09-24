/* =============================================================================
   Quanto custa agrupar por Drive em vez do volume real (2026-09-24)

   Identidade : sql_monitoring   |  Onde: SQLHDSTST505\I01 -> WatcherDB_Intelligence
   Impacto    : nenhum (so' SELECT)
   Correr com : py docs/context/sql/_run.py docs/context/sql/impacto_group_by_drive_2026-09-24.sql

   O QUE SE MEDE
   O KPI de filegroups UNLIMITED agrupa por KPI_MSSQL_DATAFILES_STG.Drive, que e'
   LEFT(caminho, 3) -- so' a letra:

       SELECT d.Instance, d.Drive, MIN(ISNULL(d.Volume_Free_MB, 0)) AS Vol_Free_MB
       FROM KPI_MSSQL_DATAFILES_STG d
       WHERE d.Is_Unlimited = 1 AND d.File_Type = 'ROWS'
       GROUP BY d.Instance, d.Drive

   Dois sitios com este texto:
       api/routers/intelligence/helpers.py:1090
       api/routers/intelligence_kpis.py:1420
   Superficies (kpi_thresholds_registry.py:198): cartao "Filegroups & Transaction
   Log" e modal "filegroup-usage-critical/warning".
   Limiares: warning 10 GB, critical 5 GB. Embutidos aqui em MB (10240 / 5120)
   porque o _run.py proibe DECLARE.

   PORQUE IMPORTA
   O commit ed35ccc deu a CADA ficheiro o espaco livre do SEU volume. Onde uma
   letra aloja varios volumes (mount points NTFS, CSV de cluster), este GROUP BY
   junta-os e o MIN fica com o mais apertado. Dois efeitos opostos no mesmo
   cartao:
     - falso CRITICAL: ficheiro num volume com folga julgado pelo irmao apertado;
     - sub-contagem: N volumes viram 1 linha, logo N criticos contam 1.

   Medido na frota (sobre DISK_USAGE, todos os volumes): 58 volumes reais em 8
   prefixos, o pior SQLIDSPRD03_I01 com 31 sob F:. Aqui restringe-se ao universo
   que o KPI usa de facto, que e' bem mais pequeno.

   CUIDADO NA LEITURA
   O volume real e' derivado pelo prefixo MAIS LONGO do Physical_Path que casa
   com um Drive da DISK_USAGE. Ficheiros cujo caminho nao casa com volume nenhum
   caem fora do JOIN -- o bloco 1 conta-os em separado para nao desaparecerem.
   ============================================================================= */


-- -----------------------------------------------------------------------------
-- [1] Dimensao: quantos prefixos escondem mais de um volume, no universo do KPI
-- -----------------------------------------------------------------------------
WITH mapa AS (
    SELECT df.Instance, df.[Database], df.File_Name,
           df.Drive                AS Prefixo,
           df.Volume_Free_MB,
           du.Drive                AS Volume_Real,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.[Database], df.File_Name
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Is_Unlimited = 1 AND df.File_Type = 'ROWS'
),
ambiguos AS (
    SELECT Instance, Prefixo
    FROM mapa WHERE rn = 1
    GROUP BY Instance, Prefixo
    HAVING COUNT(DISTINCT Volume_Real) > 1
)
SELECT 'DIMENSAO' AS Bloco,
       (SELECT COUNT(*) FROM mapa WHERE rn = 1)                              AS Ficheiros_Mapeados,
       (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK)
         WHERE Is_Unlimited = 1 AND File_Type = 'ROWS')                      AS Ficheiros_No_Universo,
       (SELECT COUNT(*) FROM ambiguos)                                       AS Prefixos_Ambiguos,
       (SELECT COUNT(DISTINCT Instance) FROM ambiguos)                       AS Instancias_Afectadas,
       (SELECT COUNT(*) FROM mapa m WHERE m.rn = 1
          AND EXISTS (SELECT 1 FROM ambiguos a
                       WHERE a.Instance = m.Instance AND a.Prefixo = m.Prefixo)) AS Ficheiros_Afectados;


-- -----------------------------------------------------------------------------
-- [2] A BARRA. Contagem de Warning e Critical como o KPI faz hoje (por prefixo,
--     com MIN) contra a contagem pelo volume real. E' este par de numeros que
--     decide se vale a pena mexer, e em que sentido o portal vai mudar.
-- -----------------------------------------------------------------------------
WITH mapa AS (
    SELECT df.Instance, df.[Database], df.File_Name,
           df.Drive AS Prefixo, df.Volume_Free_MB, du.Drive AS Volume_Real,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.[Database], df.File_Name
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Is_Unlimited = 1 AND df.File_Type = 'ROWS'
),
hoje AS (
    SELECT Instance, Prefixo AS Chave, MIN(ISNULL(Volume_Free_MB, 0)) AS Vol_Free
    FROM mapa WHERE rn = 1 GROUP BY Instance, Prefixo
),
correcto AS (
    SELECT Instance, Volume_Real AS Chave, MIN(ISNULL(Volume_Free_MB, 0)) AS Vol_Free
    FROM mapa WHERE rn = 1 GROUP BY Instance, Volume_Real
)
SELECT 'BARRA' AS Bloco,
       (SELECT COUNT(*) FROM hoje)     AS Linhas_Hoje,
       (SELECT COUNT(*) FROM correcto) AS Linhas_Pelo_Volume,
       (SELECT SUM(CASE WHEN Vol_Free = 0 OR (Vol_Free > 5120 AND Vol_Free <= 10240)
                        THEN 1 ELSE 0 END) FROM hoje)     AS Warning_Hoje,
       (SELECT SUM(CASE WHEN Vol_Free = 0 OR (Vol_Free > 5120 AND Vol_Free <= 10240)
                        THEN 1 ELSE 0 END) FROM correcto) AS Warning_Pelo_Volume,
       (SELECT SUM(CASE WHEN Vol_Free > 0 AND Vol_Free <= 5120
                        THEN 1 ELSE 0 END) FROM hoje)     AS Critical_Hoje,
       (SELECT SUM(CASE WHEN Vol_Free > 0 AND Vol_Free <= 5120
                        THEN 1 ELSE 0 END) FROM correcto) AS Critical_Pelo_Volume;


-- -----------------------------------------------------------------------------
-- [3] Os casos concretos que mudam de veredicto. Se este bloco vier vazio, o
--     defeito e' real mas nao esta' a produzir nenhum numero errado hoje -- e
--     entao a correccao e' higiene, nao urgencia. Ler antes de decidir.
-- -----------------------------------------------------------------------------
WITH mapa AS (
    SELECT df.Instance, df.[Database], df.File_Name,
           df.Drive AS Prefixo, df.Volume_Free_MB, du.Drive AS Volume_Real,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.[Database], df.File_Name
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Is_Unlimited = 1 AND df.File_Type = 'ROWS'
),
hoje AS (
    SELECT Instance, Prefixo, MIN(ISNULL(Volume_Free_MB, 0)) AS Vol_Free
    FROM mapa WHERE rn = 1 GROUP BY Instance, Prefixo
),
correcto AS (
    SELECT Instance, Volume_Real, MIN(ISNULL(Volume_Free_MB, 0)) AS Vol_Free
    FROM mapa WHERE rn = 1 GROUP BY Instance, Volume_Real
)
SELECT TOP 40 'CASOS' AS Bloco,
       c.Instance,
       c.Volume_Real,
       CAST(c.Vol_Free / 1024.0 AS DECIMAL(10,1)) AS Livre_GB_Real,
       h.Prefixo,
       CAST(h.Vol_Free / 1024.0 AS DECIMAL(10,1)) AS Livre_GB_Usado_Hoje,
       CASE WHEN c.Vol_Free > 0 AND c.Vol_Free <= 5120 THEN 'CRITICAL'
            WHEN c.Vol_Free = 0 OR (c.Vol_Free > 5120 AND c.Vol_Free <= 10240) THEN 'WARNING'
            ELSE 'OK' END AS Veredicto_Real,
       CASE WHEN h.Vol_Free > 0 AND h.Vol_Free <= 5120 THEN 'CRITICAL'
            WHEN h.Vol_Free = 0 OR (h.Vol_Free > 5120 AND h.Vol_Free <= 10240) THEN 'WARNING'
            ELSE 'OK' END AS Veredicto_Hoje
FROM correcto c
JOIN hoje h
  ON h.Instance = c.Instance
 AND h.Prefixo  = LEFT(c.Volume_Real, 3)
WHERE CASE WHEN c.Vol_Free > 0 AND c.Vol_Free <= 5120 THEN 'CRITICAL'
           WHEN c.Vol_Free = 0 OR (c.Vol_Free > 5120 AND c.Vol_Free <= 10240) THEN 'WARNING'
           ELSE 'OK' END
   <> CASE WHEN h.Vol_Free > 0 AND h.Vol_Free <= 5120 THEN 'CRITICAL'
           WHEN h.Vol_Free = 0 OR (h.Vol_Free > 5120 AND h.Vol_Free <= 10240) THEN 'WARNING'
           ELSE 'OK' END
ORDER BY c.Vol_Free;


-- -----------------------------------------------------------------------------
-- [4] A MODAL DE DRILL (intelligence_kpis.py:1032-1048). Aqui o agregado e' MAX,
--     nao MIN -- erra para o SILENCIO, nao para o alarme. Um filegroup espalhado
--     por dois volumes sob a mesma letra mostra o espaco do mais folgado e pode
--     rotular WARNING o que e' CRITICAL. O filtro <= warning e' por LINHA, antes
--     do grupo, logo o MAX corre sobre volumes ja' apertados.
-- -----------------------------------------------------------------------------
WITH mapa AS (
    SELECT df.Instance, df.[Database], df.Filegroup, df.Drive, df.Physical_Path,
           ISNULL(df.Volume_Free_MB, 0) AS Livre,
           du.Drive AS Volume_Real,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.Physical_Path
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Is_Unlimited = 1 AND df.File_Type = 'ROWS'
      AND ISNULL(df.Volume_Free_MB, 0) <= 10240
),
grupos AS (
    SELECT Instance, [Database], Filegroup, Drive,
           COUNT(DISTINCT Volume_Real) AS Volumes_No_Grupo,
           MAX(Livre) AS Livre_Mostrado,
           MIN(Livre) AS Livre_Pior
    FROM mapa WHERE rn = 1
    GROUP BY Instance, [Database], Filegroup, Drive
)
SELECT 'MODAL' AS Bloco,
       COUNT(*)                                                          AS Grupos,
       SUM(CASE WHEN Volumes_No_Grupo > 1 THEN 1 ELSE 0 END)             AS Grupos_Com_Varios_Volumes,
       SUM(CASE WHEN Volumes_No_Grupo > 1
                 AND Livre_Pior > 0 AND Livre_Pior <= 5120
                 AND NOT (Livre_Mostrado > 0 AND Livre_Mostrado <= 5120)
                THEN 1 ELSE 0 END)                                       AS Criticos_Escondidos
FROM grupos;


-- -----------------------------------------------------------------------------
-- [5] O KPI DE T-LOG (tlog_usage_classes.py:72-84). Agrupa por (Instance,
--     Database) com MIN(NULLIF(Volume_Free_MB,0)) sobre os ficheiros LOG. So'
--     morde quando a MESMA base tem dois ou mais logs em volumes reais
--     diferentes -- raro, mas alimenta VOLUME_SATURADO / VOLUME_BAIXO /
--     AUTOGROW_NAO_CABE. Este bloco diz se existe algum caso na frota.
-- -----------------------------------------------------------------------------
WITH mapa AS (
    SELECT df.Instance, df.[Database], df.Physical_Path,
           ISNULL(df.Volume_Free_MB, 0) AS Livre,
           du.Drive AS Volume_Real,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.Physical_Path
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.File_Type = 'LOG'
)
SELECT TOP 20 'TLOG' AS Bloco,
       Instance, [Database],
       COUNT(DISTINCT Volume_Real) AS Volumes_Distintos,
       COUNT(*)                    AS Ficheiros_Log,
       CAST(MIN(Livre) / 1024.0 AS DECIMAL(10,1)) AS Livre_GB_Usado,
       CAST(MAX(Livre) / 1024.0 AS DECIMAL(10,1)) AS Livre_GB_Maior
FROM mapa WHERE rn = 1
GROUP BY Instance, [Database]
HAVING COUNT(DISTINCT Volume_Real) > 1
ORDER BY MIN(Livre);
