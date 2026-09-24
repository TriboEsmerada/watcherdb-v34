/* =============================================================================
   (a) Recolha de servicos parada desde 13/05  (b) pre-voo da DATAFILES_STG
   2026-09-24 | Identidade: sql_monitoring | Impacto: nenhum (so' SELECT)

   (a) O portal mostra "NO COLLECTION SINCE 05/13" no cartao Availability, linha
       "Instances w/ services down". O badge foi posto de proposito a 2026-09-15
       (helpers.py:1870-1873) porque "0 instancias com servicos em baixo" era
       indistinguivel de saudavel. O badge funciona; a causa nunca foi tratada.
       Fonte do sinal: MAX(Update_TS) de KPI_MSSQL_SERVICE_STATUS_STG
       (helpers.py:1884-1886), com tecto de 60 min.

   (b) O especialista do V1 pediu tres consultas antes de se poder sequer avaliar
       acrescentar uma coluna a' KPI_MSSQL_DATAFILES_STG: as fontes do V1
       contradizem-se sobre se o objecto e' TABLE ou VIEW, e a DATAFILES nao
       aparece no registo em bloco da KPI_STG_ACTIVE_TABLE.
   ============================================================================= */


-- -----------------------------------------------------------------------------
-- [1] Ha' quanto tempo esta' parada, e com que dimensao
-- -----------------------------------------------------------------------------
SELECT 'SERVICOS' AS Bloco,
       COUNT(*)                                     AS Linhas,
       COUNT(DISTINCT Instance)                     AS Instancias,
       MIN(Update_TS)                               AS Primeira_Escrita,
       MAX(Update_TS)                               AS Ultima_Escrita,
       DATEDIFF(DAY, MAX(Update_TS), GETDATE())     AS Dias_Parada
FROM dbo.KPI_MSSQL_SERVICE_STATUS_STG WITH (NOLOCK);


-- -----------------------------------------------------------------------------
-- [2] O que ficou congelado la' dentro. Se houver servicos em baixo nesta
--     fotografia de 13/05, sao dados velhos a fingir de actuais.
-- -----------------------------------------------------------------------------
SELECT TOP 20 'CONGELADO' AS Bloco, *
FROM dbo.KPI_MSSQL_SERVICE_STATUS_STG WITH (NOLOCK)
ORDER BY Update_TS DESC;


-- -----------------------------------------------------------------------------
-- [3] Pre-voo (b.1): o que E' a KPI_MSSQL_DATAFILES_STG -- tabela ou vista?
-- -----------------------------------------------------------------------------
SELECT 'IDENTIDADE' AS Bloco, name, type_desc, create_date, modify_date
FROM sys.objects
WHERE name LIKE 'KPI_MSSQL_DATAFILES_STG%'
   OR name LIKE 'KPI_MSSQL_SERVICE_STATUS%'
ORDER BY name;


-- -----------------------------------------------------------------------------
-- [4] Pre-voo (b.2): esta' registada no controlo BLUE/GREEN, e por ambiente?
-- -----------------------------------------------------------------------------
SELECT 'ACTIVE_TABLE' AS Bloco, *
FROM dbo.KPI_STG_ACTIVE_TABLE WITH (NOLOCK)
WHERE Table_Name LIKE '%DATAFILES%'
   OR Table_Name LIKE '%SERVICE_STATUS%';


-- -----------------------------------------------------------------------------
-- [5] Pre-voo (b.3): os slots existem e tem as mesmas colunas entre si?
--     No caso da DISK_USAGE apareceram pares legados a VARCHAR(8) com 0 linhas,
--     residuo do desenho anterior a' particao por ambiente. Procura-se o mesmo.
-- -----------------------------------------------------------------------------
SELECT 'COLUNAS' AS Bloco,
       t.name AS Tabela, c.column_id, c.name AS Coluna,
       ty.name AS Tipo, c.max_length, c.is_nullable
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty  ON ty.user_type_id = c.user_type_id
WHERE t.name LIKE 'KPI_MSSQL_DATAFILES_STG%'
ORDER BY t.name, c.column_id;
