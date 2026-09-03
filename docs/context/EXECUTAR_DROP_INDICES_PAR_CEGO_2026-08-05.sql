/* ============================================================================
   LIMPEZA DE ÍNDICES PAR CEGO 0-LEITURA + TABELAS _OLD  (WatcherDB_Intelligence)
   Data: 2026-08-05 · Validado: v1-intel (GO zero-breakage) + sql-deep-reviewer
   ----------------------------------------------------------------------------
   IDENTIDADE : correr em SSMS ligado a SQLHDSTST505\I01
   IMPACTO    : remove ~105 índices nunca lidos (40 dias) + 12 tabelas _OLD frias
                (Dez/2025). Os índices KEEP (lidos) NÃO são tocados.
   ROLLBACK   : índices -> a coluna rollback_create da PARTE 1 (guarda-a).
                _OLD -> sem rollback (snapshot morto de há 8 meses).
   JANELA     : DROP INDEX pega Sch-M lock (offline em Standard). Correr o
                @DryRun=0 ENTRE CICLOS do colector, nunca a meio do swap.
   ============================================================================ */

USE [WatcherDB_Intelligence];
GO

/* ----------------------------------------------------------------------------
   PARTE 1 — ROLLBACK: gera as CREATE INDEX para repor, se preciso.
   Corre isto PRIMEIRO e GUARDA a coluna rollback_create num ficheiro.
   ---------------------------------------------------------------------------- */
;WITH cego AS (
  SELECT i.object_id, i.index_id, i.name AS ixname, OBJECT_NAME(i.object_id) AS tbl,
         i.filter_definition, i.is_unique
  FROM sys.indexes i
  LEFT JOIN sys.dm_db_index_usage_stats us
       ON us.object_id=i.object_id AND us.index_id=i.index_id AND us.database_id=DB_ID()
  WHERE i.type_desc='NONCLUSTERED' AND i.is_primary_key=0 AND i.is_unique_constraint=0
    AND OBJECTPROPERTY(i.object_id,'IsUserTable')=1
    AND (i.name LIKE 'IX[_]%[_]Inst' OR i.name LIKE 'IX[_]%[_]Instance'
         OR i.name LIKE 'IX[_]%[_]InstDB' OR i.name LIKE 'IX[_]%[_]DB'
         OR i.name LIKE 'IX[_]%[_]UpdateTS')
    AND ISNULL(us.user_seeks+us.user_scans+us.user_lookups,0) = 0
    AND (OBJECT_NAME(i.object_id) LIKE 'KPI[_]MSSQL[_]%' OR OBJECT_NAME(i.object_id) LIKE 'KPI[_]OS[_]%')
    AND OBJECT_NAME(i.object_id) NOT LIKE '%[_]STG[_]OLD'
    AND OBJECT_NAME(i.object_id) NOT LIKE '%[_]HIST'
)
SELECT c.tbl, c.ixname,
  'CREATE '+CASE WHEN c.is_unique=1 THEN 'UNIQUE ' ELSE '' END+'NONCLUSTERED INDEX ['+c.ixname+'] ON [dbo].['+c.tbl+'] ('
   + STUFF((SELECT ', ['+COL_NAME(ic.object_id,ic.column_id)+']'+CASE WHEN ic.is_descending_key=1 THEN ' DESC' ELSE '' END
            FROM sys.index_columns ic WHERE ic.object_id=c.object_id AND ic.index_id=c.index_id AND ic.is_included_column=0
            ORDER BY ic.key_ordinal FOR XML PATH('')),1,2,'')+')'
   + ISNULL(' INCLUDE ('+STUFF((SELECT ', ['+COL_NAME(ic.object_id,ic.column_id)+']'
            FROM sys.index_columns ic WHERE ic.object_id=c.object_id AND ic.index_id=c.index_id AND ic.is_included_column=1
            ORDER BY ic.key_ordinal FOR XML PATH('')),1,2,'')+')','')
   + ISNULL(' WHERE '+c.filter_definition,'')+';'                          AS rollback_create
FROM cego c ORDER BY c.tbl, c.ixname;
GO

/* ----------------------------------------------------------------------------
   PARTE 2 — EXECUTOR. Corre 1x com @DryRun=1 (só LISTA), revê, depois muda
   para @DryRun=0 EM JANELA para EXECUTAR. Mesmos critérios validados.
   ---------------------------------------------------------------------------- */
SET NOCOUNT ON;
DECLARE @DryRun BIT = 1;   -- <<< 1 = só MOSTRA; muda para 0 para EXECUTAR
DECLARE @sql NVARCHAR(MAX), @n INT = 0;

-- 1) par cego 0-leitura (KPI_MSSQL_/KPI_OS_, sem HIST, sem _OLD)
DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
  SELECT 'DROP INDEX ['+i.name+'] ON [dbo].['+OBJECT_NAME(i.object_id)+'];'
  FROM sys.indexes i
  LEFT JOIN sys.dm_db_index_usage_stats us
       ON us.object_id=i.object_id AND us.index_id=i.index_id AND us.database_id=DB_ID()
  WHERE i.type_desc='NONCLUSTERED' AND i.is_primary_key=0 AND i.is_unique_constraint=0
    AND OBJECTPROPERTY(i.object_id,'IsUserTable')=1
    AND (i.name LIKE 'IX[_]%[_]Inst' OR i.name LIKE 'IX[_]%[_]Instance'
         OR i.name LIKE 'IX[_]%[_]InstDB' OR i.name LIKE 'IX[_]%[_]DB'
         OR i.name LIKE 'IX[_]%[_]UpdateTS')
    AND ISNULL(us.user_seeks+us.user_scans+us.user_lookups,0) = 0
    AND (OBJECT_NAME(i.object_id) LIKE 'KPI[_]MSSQL[_]%' OR OBJECT_NAME(i.object_id) LIKE 'KPI[_]OS[_]%')
    AND OBJECT_NAME(i.object_id) NOT LIKE '%[_]STG[_]OLD'
    AND OBJECT_NAME(i.object_id) NOT LIKE '%[_]HIST'
  ORDER BY OBJECT_NAME(i.object_id), i.name;
OPEN cur; FETCH NEXT FROM cur INTO @sql;
WHILE @@FETCH_STATUS=0
BEGIN
   PRINT @sql; SET @n+=1;
   IF @DryRun=0 EXEC sys.sp_executesql @sql;
   FETCH NEXT FROM cur INTO @sql;
END
CLOSE cur; DEALLOCATE cur;

-- 2) as 12 tabelas _OLD (frias, Dez 2025 -- guarda das linhas ja confirmou)
DECLARE cur2 CURSOR LOCAL FAST_FORWARD FOR
  SELECT 'DROP TABLE [dbo].['+name+'];' FROM sys.tables WHERE name LIKE '%[_]STG[_]OLD' ORDER BY name;
OPEN cur2; FETCH NEXT FROM cur2 INTO @sql;
WHILE @@FETCH_STATUS=0
BEGIN
   PRINT @sql; SET @n+=1;
   IF @DryRun=0 EXEC sys.sp_executesql @sql;
   FETCH NEXT FROM cur2 INTO @sql;
END
CLOSE cur2; DEALLOCATE cur2;

PRINT '----------------------------------------';
PRINT CAST(@n AS VARCHAR)+' comandos '+CASE WHEN @DryRun=1
      THEN 'LISTADOS (dry run -- nada executado). Revê acima e poe @DryRun=0.'
      ELSE 'EXECUTADOS.' END;
GO

/* ----------------------------------------------------------------------------
   PARTE 3 — RE-CENSO (correr depois do @DryRun=0).
   Esperado: par_cego_0leitura_restantes ~0 ; keep_intactos mantem-se em 190.
   ---------------------------------------------------------------------------- */
SELECT
  SUM(CASE WHEN leituras=0 THEN 1 ELSE 0 END) AS par_cego_0leitura_restantes,
  SUM(CASE WHEN leituras>0 THEN 1 ELSE 0 END) AS keep_intactos
FROM (
  SELECT ISNULL(us.user_seeks+us.user_scans+us.user_lookups,0) AS leituras
  FROM sys.indexes i
  LEFT JOIN sys.dm_db_index_usage_stats us
       ON us.object_id=i.object_id AND us.index_id=i.index_id AND us.database_id=DB_ID()
  WHERE i.type_desc='NONCLUSTERED' AND OBJECTPROPERTY(i.object_id,'IsUserTable')=1
    AND (i.name LIKE 'IX[_]%[_]Inst' OR i.name LIKE 'IX[_]%[_]Instance'
         OR i.name LIKE 'IX[_]%[_]InstDB' OR i.name LIKE 'IX[_]%[_]DB' OR i.name LIKE 'IX[_]%[_]UpdateTS')
    AND (OBJECT_NAME(i.object_id) LIKE 'KPI[_]MSSQL[_]%' OR OBJECT_NAME(i.object_id) LIKE 'KPI[_]OS[_]%')
    AND OBJECT_NAME(i.object_id) NOT LIKE '%[_]HIST'
) q;
GO
