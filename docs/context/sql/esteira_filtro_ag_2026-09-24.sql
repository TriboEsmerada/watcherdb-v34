/* =============================================================================
   Esteira do filtro AG: o que se PERDE ao excluir secundarios (2026-09-24)

   Identidade : sql_monitoring   |  Onde: SQLHDSTST505\I01 -> WatcherDB_Intelligence
   Impacto    : nenhum (so' SELECT)

   Proposta em avaliacao: portar para collect_datafiles.py o filtro ja' provado
   em collect_tlog_usage.py:41-47 --
       AND HAS_DBACCESS(d.name) = 1
       AND d.database_id NOT IN (dm_hadr_database_replica_states
                                 JOIN dm_hadr_availability_replica_states
                                 WHERE is_local = 1 AND role_desc = 'SECONDARY')

   Ganho: servidores onde o erro 976 aborta a coleta INTEIRA passam a entregar
   todas as bases menos as secundarias.
   Risco (a esteira): o filtro exclui TODOS os secundarios locais, incluindo os
   LEGIVEIS. Num servidor que hoje funciona e tenha secundarios legiveis, esses
   ficheiros deixam de ser recolhidos -- hoje estao la'.

   Estas consultas medem o tamanho dessa perda antes de decidir.
   ============================================================================= */

-- -----------------------------------------------------------------------------
-- [1] Bases em AG que HOJE tem ficheiros recolhidos na DATAFILES.
--     Sao as candidatas a desaparecer se o servidor onde foram recolhidas for
--     o secundario. Se este numero for zero, nao ha' esteira nenhuma.
-- -----------------------------------------------------------------------------
SELECT 'AG COM FICHEIROS' AS Bloco,
       COUNT(DISTINCT df.Instance + '|' + df.[Database]) AS Bases_AG_Com_Ficheiros,
       COUNT(*)                                          AS Ficheiros
FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
WHERE EXISTS (
    SELECT 1 FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG ag WITH (NOLOCK)
    WHERE LTRIM(RTRIM(UPPER(ag.Instance)))   = LTRIM(RTRIM(UPPER(df.Instance)))
      AND LTRIM(RTRIM(UPPER(ag.[Database]))) = LTRIM(RTRIM(UPPER(df.[Database])))
);


-- -----------------------------------------------------------------------------
-- [2] Detalhe por instancia: quantas bases AG com ficheiros, e se essa
--     instancia tambem aparece na TLOG_USAGE (que JA' aplica o filtro).
--     Se uma base AG tem ficheiros na DATAFILES mas NAO tem linha na
--     TLOG_USAGE, e' sinal forte de que a DATAFILES a apanhou no secundario --
--     exactamente o que se vai perder.
-- -----------------------------------------------------------------------------
SELECT TOP 40 'DETALHE' AS Bloco,
       df.Instance,
       df.[Database],
       COUNT(*) AS Ficheiros,
       CASE WHEN EXISTS (
            SELECT 1 FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
            WHERE LTRIM(RTRIM(UPPER(t.Instance)))   = LTRIM(RTRIM(UPPER(df.Instance)))
              AND LTRIM(RTRIM(UPPER(t.[Database]))) = LTRIM(RTRIM(UPPER(df.[Database])))
       ) THEN 'tem TLOG (provavel primario)'
         ELSE 'SEM TLOG (provavel secundario -- perde-se)' END AS Veredicto
FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
WHERE EXISTS (
    SELECT 1 FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG ag WITH (NOLOCK)
    WHERE LTRIM(RTRIM(UPPER(ag.Instance)))   = LTRIM(RTRIM(UPPER(df.Instance)))
      AND LTRIM(RTRIM(UPPER(ag.[Database]))) = LTRIM(RTRIM(UPPER(df.[Database])))
)
GROUP BY df.Instance, df.[Database]
ORDER BY Veredicto DESC, COUNT(*) DESC;


-- -----------------------------------------------------------------------------
-- [3] Contagem do (2) resumida: quantas bases de cada lado.
-- -----------------------------------------------------------------------------
WITH ag_com_ficheiros AS (
    SELECT DISTINCT df.Instance, df.[Database]
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    WHERE EXISTS (
        SELECT 1 FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG ag WITH (NOLOCK)
        WHERE LTRIM(RTRIM(UPPER(ag.Instance)))   = LTRIM(RTRIM(UPPER(df.Instance)))
          AND LTRIM(RTRIM(UPPER(ag.[Database]))) = LTRIM(RTRIM(UPPER(df.[Database])))
    )
)
SELECT 'RESUMO' AS Bloco,
       SUM(CASE WHEN tem_tlog = 1 THEN 1 ELSE 0 END) AS Provavel_Primario_Fica,
       SUM(CASE WHEN tem_tlog = 0 THEN 1 ELSE 0 END) AS Provavel_Secundario_Perde
FROM (
    SELECT a.Instance, a.[Database],
           CASE WHEN EXISTS (
                SELECT 1 FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
                WHERE LTRIM(RTRIM(UPPER(t.Instance)))   = LTRIM(RTRIM(UPPER(a.Instance)))
                  AND LTRIM(RTRIM(UPPER(t.[Database]))) = LTRIM(RTRIM(UPPER(a.[Database])))
           ) THEN 1 ELSE 0 END AS tem_tlog
    FROM ag_com_ficheiros a
) x;
