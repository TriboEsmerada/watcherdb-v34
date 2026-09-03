-- ============================================================================
-- SCRIPT: Monitor_2PC_Compact.sql
-- DESCRIÇÃO: Versão compacta para verificação rápida de transações 2PC
-- COMPATÍVEL: SQL Server 2012+
-- ============================================================================

SET NOCOUNT ON;

DECLARE @v INT = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)), 4) AS INT);

-- Cabeçalho
SELECT 
    @@SERVERNAME AS servidor,
    GETDATE() AS data_hora,
    @v AS versao_major,
    CASE 
        WHEN @v >= 16 THEN 'SQL 2022+ (DMV nativa) - v' + CAST(@v AS VARCHAR(5))
        WHEN @v >= 11 THEN 'SQL 2012-2019 (dm_tran_locks) - v' + CAST(@v AS VARCHAR(5))
        ELSE 'Versão antiga (dm_tran_locks) - v' + CAST(@v AS VARCHAR(5))
    END AS metodo;

-- Branch por versão
IF @v >= 16
BEGIN
    -- SQL Server 2022+ (inclui versões futuras): Usar DMV nativa + locks para comandos
    PRINT '>> SQL Server 2022+ detectado (v' + CAST(@v AS VARCHAR(5)) + ') - Usando sys.dm_tran_distributed_transaction_stats';
    
    SELECT 
        @@SERVERNAME AS servidor,
        GETDATE() AS verificado_em,
        [open] AS transacoes_abertas,
        in_doubt AS transacoes_in_doubt,
        committed AS confirmadas,
        aborted AS abortadas,
        CASE WHEN in_doubt > 0 THEN 'CRITICAL' WHEN [open] > 10 THEN 'WARNING' ELSE 'OK' END AS status
    FROM sys.dm_tran_distributed_transaction_stats;
END
ELSE
BEGIN
    -- SQL Server 2012-2019: Usar dm_tran_locks
    PRINT '>> SQL Server < 2022 detectado (v' + CAST(@v AS VARCHAR(5)) + ') - Usando sys.dm_tran_locks';
    
    SELECT 
        @@SERVERNAME AS servidor,
        GETDATE() AS verificado_em,
        COUNT(DISTINCT request_owner_guid) AS transacoes_in_doubt,
        COUNT(*) AS total_locks,
        CASE WHEN COUNT(*) > 0 THEN 'CRITICAL' ELSE 'OK' END AS status
    FROM sys.dm_tran_locks
    WHERE request_owner_type = 'DISTRIBUTED_TRANSACTION';
END

-- Detalhes das transações in-doubt (funciona em todas as versões)
IF EXISTS (
    SELECT 1 FROM sys.dm_tran_locks 
    WHERE request_owner_type = 'DISTRIBUTED_TRANSACTION'
)
BEGIN
    PRINT '';
    PRINT '⚠️ ALERTA: Transações in-doubt detectadas!';
    
    SELECT 
        @@SERVERNAME AS servidor,
        l.request_owner_guid AS uow,
        DB_NAME(l.resource_database_id) AS database_name,
        COUNT(*) AS locks,
        MAX(l.resource_type) AS tipo_recurso,
        MAX(l.request_mode) AS modo_lock,
        'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
        'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
    FROM sys.dm_tran_locks l
    WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
    GROUP BY l.request_owner_guid, l.resource_database_id;
END
ELSE
BEGIN
    PRINT '';
    PRINT '✅ Nenhuma transação distribuída pendente.';
END
GO
