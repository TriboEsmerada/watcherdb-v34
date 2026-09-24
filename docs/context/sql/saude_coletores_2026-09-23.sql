/* =============================================================================
   Que colectores correram desde o restart das 15:24:37 (2026-09-23)

   Identidade : sql_monitoring   |  Onde: SQLHDSTST505\I01 -> WatcherDB_Intelligence
   Impacto    : nenhum (so' SELECT)

   Objectivo: descartar que a alteracao ao collect_datafiles.py partiu a recolha.
   Se DISK_USAGE avancou e DATAFILES nao, o problema e' meu.
   ============================================================================= */

SELECT 'DATAFILES' AS Fonte, MAX(Update_TS) AS Ultima, COUNT(*) AS Linhas
FROM dbo.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK)
UNION ALL
SELECT 'DISK_USAGE', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK)
UNION ALL
SELECT 'TLOG_USAGE', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE WITH (NOLOCK)
UNION ALL
SELECT 'FG_USAGE', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK)
UNION ALL
SELECT 'BACKUPS', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
UNION ALL
SELECT 'OS_DISK_PERF', MAX(Update_TS), COUNT(*)
FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK);
