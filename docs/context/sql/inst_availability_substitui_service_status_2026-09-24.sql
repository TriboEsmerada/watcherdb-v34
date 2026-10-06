/* =============================================================================
   O INST_AVAILABILITY substitui o SERVICE_STATUS? (2026-09-24)
   Identidade: sql_monitoring | Impacto: nenhum (so' SELECT)

   scripts/run_collections.py:133 diz que KPI_MSSQL_SERVICE_STATUS_STG foi
   "Deprecado -- substituido por INST_AVAILABILITY_STG". O portal V3.4 continua a
   ler a tabela morta (parada desde 13/05). Aqui confirma-se se o substituto
   esta' vivo e se carrega o estado dos servicos.
   ============================================================================= */

-- [1] O substituto esta' vivo?
SELECT 'INST_AVAIL' AS Bloco,
       COUNT(*)                                 AS Linhas,
       COUNT(DISTINCT Instance)                 AS Instancias,
       MAX(Update_TS)                           AS Ultima_Escrita,
       DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) AS Minutos_Desde
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK);

-- [2] Que colunas tem -- carrega servicos?
SELECT 'COLUNAS' AS Bloco, c.column_id, c.name AS Coluna, ty.name AS Tipo
FROM sys.views v
JOIN sys.columns c ON c.object_id = v.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE v.name = 'KPI_MSSQL_INST_AVAILABILITY_STG'
ORDER BY c.column_id;

-- [3] Se for tabela e nao vista, o bloco 2 vem vazio; este apanha-a.
SELECT 'COLUNAS_TBL' AS Bloco, c.column_id, c.name AS Coluna, ty.name AS Tipo
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.name LIKE 'KPI_MSSQL_INST_AVAILABILITY_STG%'
  AND t.name NOT LIKE '%GREEN%'
ORDER BY t.name, c.column_id;

-- [4] Uma amostra, para ver o que la' esta' de facto
SELECT TOP 8 'AMOSTRA' AS Bloco, *
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
ORDER BY Update_TS DESC;
