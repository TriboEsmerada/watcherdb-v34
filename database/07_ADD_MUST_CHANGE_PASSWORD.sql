-- ############################################################
-- HISTORICO -- NAO CORRER. Substituido por 14_ADD_MUST_CHANGE_PASSWORD.sql (2026-09-16).
--
-- Dois motivos:
--  1. Nunca funcionou. O UPDATE abaixo esta no MESMO batch do ALTER TABLE ... ADD, sem EXEC(). O SQL Server
--     compila a batch toda antes de a correr e recusa-a com o erro 207 (Invalid column name), porque a coluna
--     ainda nao existe nesse momento. O ALTER nunca chega a correr e a coluna nunca e' criada -- foi o que
--     aconteceu nesta instalacao, onde o portal escreveu "Invalid column name 'must_change_password'" em cada
--     login durante oito dias.
--  2. O ultimo UPDATE tem um hash bcrypt de semente (admin123) escrito no proprio ficheiro. O commit 5ed4f68
--     tirou esse bloco do canonico de proposito; aqui ficou para tras. Correr este ficheiro verbatim numa base
--     nova voltaria a introduzir essa logica.
--
-- Mantido apenas como registo. A forma correcta esta em database/14_ADD_MUST_CHANGE_PASSWORD.sql e em
-- INSTALACAO_COMPLETA_UNIFICADA.sql:10137-10142.
-- ############################################################

-- ============================================================
-- Add must_change_password column to WatcherDB_Users
-- Forces password change on first login (eliminates admin123)
-- ============================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users')
    AND name = 'must_change_password'
)
BEGIN
    ALTER TABLE dbo.WatcherDB_Users
        ADD must_change_password BIT NOT NULL DEFAULT 1;

    -- Existing active users: assume they already changed password
    UPDATE dbo.WatcherDB_Users
        SET must_change_password = 0
        WHERE disabled = 0;

    -- Default users with admin123: force password change
    UPDATE dbo.WatcherDB_Users
        SET must_change_password = 1
        WHERE username IN ('admin', 'salomao', 'ricardo', 'viewer')
        AND password_hash LIKE '$2b$12$w8ge4gtxBD2xEtacbiNss%';

    PRINT 'Column must_change_password added to WatcherDB_Users.';
END
ELSE
    PRINT 'Column must_change_password already exists.';
GO
