/* =============================================================================
   Prova do fix do JOIN em collect_datafiles.py (2026-09-23)

   Identidade : sql_monitoring
   Onde       : SQLHDSTST505\I01 -> WatcherDB_Intelligence
   Impacto    : nenhum (so' SELECT, tudo com NOLOCK)

   Contexto: ate' 2026-09-23 o colector juntava #Datafiles a #VolumeInfo por
   LEFT(caminho,3). Onde uma letra aloja varios volumes, dezenas de candidatos
   partilhavam a chave e o UPDATE...FROM escolhia um ao acaso. Resultado medido
   no ciclo das 13:59 (codigo antigo): no SQLIDSPRD03_I01, ficheiros espalhados
   por 8 volumes de F: (219 a 330 GB livres) reportavam TODOS os 127,9 GB do
   F:\Hist_Data_11\; e os logs em L:\Logs1\ (1011,9 GB) reportavam os 1564,5 GB
   do L:\Logs2\.

   Fix aplicado 15:24:37: o JOIN passou a ser por (DB_Id, File_Id).

   Gravar o resultado em:
     C:\Users\ue_e-snetto\Documents\projetosPython\_qout\coerencia_volume_free.csv
   (SSMS: Ctrl+T para texto, Ctrl+Shift+F para ficheiro, depois Executar)
   ============================================================================= */

-- -----------------------------------------------------------------------------
-- [1] A coleta ja' e' posterior ao fix?  Se disser PRE-FIX, o resto nao conta.
-- -----------------------------------------------------------------------------
SELECT 'FRESCURA' AS Bloco,
       MAX(Update_TS) AS Ultima_Coleta,
       COUNT(*)       AS Ficheiros,
       CASE WHEN MAX(Update_TS) > '2026-09-23 15:24:37'
            THEN 'POS-FIX -- veredicto valido'
            ELSE 'PRE-FIX -- esperar o proximo ciclo (15 min)'
       END AS Estado
FROM dbo.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK);


-- -----------------------------------------------------------------------------
-- [2] Veredicto agregado por volume real.
--     Para cada ficheiro, o volume correcto e' o mount point cujo caminho e'
--     o prefixo MAIS LONGO do caminho fisico (F:\Hist_Data_10\ ganha a F:\).
--     Tolerancia de 1 GB cobre o desfasamento entre as duas coletas; as
--     diferencas do bug sao de dezenas a centenas de GB.
-- -----------------------------------------------------------------------------
WITH esperado AS (
    SELECT df.Instance,
           df.[Database],
           df.File_Name,
           df.Volume_Free_MB AS Obtido_MB,
           du.Drive          AS Volume_Correcto,
           du.Free_MB        AS Esperado_MB,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.[Database], df.File_Name
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Volume_Free_MB > 0
)
SELECT 'RESUMO' AS Bloco,
       Instance,
       Volume_Correcto,
       COUNT(*) AS Ficheiros,
       SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) <= 1024 THEN 1 ELSE 0 END) AS OK,
       SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) >  1024 THEN 1 ELSE 0 END) AS ERRADO,
       CAST(MIN(Esperado_MB)/1024.0 AS DECIMAL(10,1)) AS Esperado_GB,
       CAST(MIN(Obtido_MB)  /1024.0 AS DECIMAL(10,1)) AS Obtido_Min_GB,
       CAST(MAX(Obtido_MB)  /1024.0 AS DECIMAL(10,1)) AS Obtido_Max_GB
FROM esperado
WHERE rn = 1
GROUP BY Instance, Volume_Correcto
HAVING SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) > 1024 THEN 1 ELSE 0 END) > 0
    OR COUNT(*) > 0
ORDER BY ERRADO DESC, Instance, Volume_Correcto;


-- -----------------------------------------------------------------------------
-- [3] Total da frota, uma linha. E' este o numero que vale.
-- -----------------------------------------------------------------------------
WITH esperado AS (
    SELECT df.Volume_Free_MB AS Obtido_MB,
           du.Free_MB        AS Esperado_MB,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.[Database], df.File_Name
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Volume_Free_MB > 0
)
SELECT 'TOTAL' AS Bloco,
       COUNT(*) AS Ficheiros_Verificados,
       SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) <= 1024 THEN 1 ELSE 0 END) AS OK,
       SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) >  1024 THEN 1 ELSE 0 END) AS ERRADO
FROM esperado
WHERE rn = 1;
