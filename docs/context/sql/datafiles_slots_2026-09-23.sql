/* =============================================================================
   DATAFILES: estado dos 6 slots BLUE/GREEN por ambiente (2026-09-23)

   Identidade : sql_monitoring   |  Onde: SQLHDSTST505\I01 -> WatcherDB_Intelligence
   Impacto    : nenhum (so' SELECT)

   Objectivo: a vista KPI_MSSQL_DATAFILES_STG mostra so' o slot activo e marcava
   14:52 (antes do restart das 15:24:37). Se o slot INACTIVO tiver linhas com
   Update_TS > 15:24, o colector correu ou esta' a correr e ainda nao fez swap
   -- logo a alteracao ao collect_datafiles.py nao o partiu.
   Se os seis slots estiverem todos <= 14:52, a recolha nao arrancou.
   ============================================================================= */

SELECT 'BLUE_PRD' AS Slot, MAX(Update_TS) AS Ultima, COUNT(*) AS Linhas
FROM dbo.KPI_MSSQL_DATAFILES_STG_BLUE_PRD WITH (NOLOCK)
UNION ALL
SELECT 'GREEN_PRD', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_DATAFILES_STG_GREEN_PRD WITH (NOLOCK)
UNION ALL
SELECT 'BLUE_QA', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_DATAFILES_STG_BLUE_QA WITH (NOLOCK)
UNION ALL
SELECT 'GREEN_QA', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_DATAFILES_STG_GREEN_QA WITH (NOLOCK)
UNION ALL
SELECT 'BLUE_TST', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_DATAFILES_STG_BLUE_TST WITH (NOLOCK)
UNION ALL
SELECT 'GREEN_TST', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_DATAFILES_STG_GREEN_TST WITH (NOLOCK);
