-- =============================================================================
-- 13_ADD_PASSWORD_CHANGED_AT.sql  (WatcherDB V3.4, lote P4 A-4.7, 2026-09-08)
-- Revogacao de sessoes por mudanca/reset de password: o servico rejeita qualquer
-- JWT cujo iat seja anterior a password_changed_at (UTC). Sem esta coluna o
-- servico continua a funcionar mas escreve no log
-- "REVOGACAO DE SESSAO POR RESET INACTIVA" uma vez por processo.
-- Idempotente (sys.columns). Pode ser corrido N vezes. Correr com conta de
-- administracao da BD; sql_monitoring so' consulta.
-- =============================================================================
USE WatcherDB_Intelligence;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'password_changed_at'
)
BEGIN
    ALTER TABLE dbo.WatcherDB_Users
        ADD password_changed_at DATETIME2(0) NULL;
    PRINT 'password_changed_at adicionada a dbo.WatcherDB_Users';
END
ELSE
    PRINT 'password_changed_at ja existe (skip)';
GO
