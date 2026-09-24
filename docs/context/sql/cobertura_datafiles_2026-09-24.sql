/* =============================================================================
   Cobertura do collect_datafiles: quem falta e ha' quanto tempo (2026-09-24)

   Identidade : sql_monitoring   |  Onde: SQLHDSTST505\I01 -> WatcherDB_Intelligence
   Impacto    : nenhum (so' SELECT)

   Contexto: o log do recolhedor mostra 18-19 servidores recolhidos de 42 por
   execucao, com ~12 TIMEOUT (60s) e erros 976/978 de AlwaysOn. Como a
   KPI_MSSQL_DATAFILES_STG e' truncada e reescrita a cada ciclo, o que la' esta'
   e' so' a ultima fotografia parcial -- nao ha' acumulacao. Estas consultas
   medem o tamanho do buraco.

   A DISK_USAGE serve de referencia porque recolhe da mesma frota com uma
   consulta muito mais leve (uma linha por volume, sem SQL dinamico por base).
   ============================================================================= */

-- -----------------------------------------------------------------------------
-- [1] Instancias na DISK_USAGE (referencia) vs na DATAFILES (a que falha)
-- -----------------------------------------------------------------------------
SELECT 'COBERTURA' AS Bloco,
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK)) AS Inst_Disk_Usage,
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_DATAFILES_STG  WITH (NOLOCK)) AS Inst_Datafiles,
       (SELECT MAX(Update_TS) FROM dbo.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK))            AS Datafiles_Ultima;


-- -----------------------------------------------------------------------------
-- [2] Quem esta' na DISK_USAGE e NAO esta' na DATAFILES.
--     Sao as instancias cujos ficheiros o portal nao consegue ver de todo:
--     sem linha aqui, nao ha' Volume_Free_MB, nem tecto de crescimento, nem
--     diagnostico de T-Log por ficheiro.
-- -----------------------------------------------------------------------------
SELECT 'EM FALTA' AS Bloco,
       du.Instance,
       ISNULL(e.Env, 'Undefined') AS Env,
       COUNT(DISTINCT du.Drive)   AS Volumes,
       MIN(du.Percent_Free)       AS Min_Pct_Free
FROM dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
       ON e.Instance = du.Instance
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    WHERE df.Instance = du.Instance
)
GROUP BY du.Instance, e.Env
ORDER BY MIN(du.Percent_Free);


-- -----------------------------------------------------------------------------
-- [3] Peso de cada instancia recolhida: numero de ficheiros.
--     Serve para perceber quem e' provavel que estoure os 60 s -- e se as
--     instancias grandes entram alguma vez.
-- -----------------------------------------------------------------------------
SELECT TOP 25 'PESO' AS Bloco,
       Instance,
       COUNT(*)                   AS Ficheiros,
       COUNT(DISTINCT [Database]) AS Bases,
       MAX(Update_TS)             AS Recolhida_Em
FROM dbo.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK)
GROUP BY Instance
ORDER BY COUNT(*) DESC;


-- -----------------------------------------------------------------------------
-- [4] Bases com T-Log conhecido mas SEM ficheiros na DATAFILES.
--     Sao as que caem em LEGACY no KPI de T-Log (sem tecto real, sem volume),
--     precisamente o ramo que o lote de 21/09 teve de inventar por nao ter
--     ficheiros. Aqui mede-se quantas sao por causa da cobertura.
-- -----------------------------------------------------------------------------
SELECT 'TLOG SEM FICHEIROS' AS Bloco,
       COUNT(*) AS Bases_Sem_Ficheiro_Log,
       COUNT(DISTINCT t.Instance) AS Instancias
FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    WHERE df.Instance = t.Instance
      AND df.[Database] = t.[Database]
      AND df.File_Type = 'LOG'
);
