-- ============================================================
-- WatcherDB Token Blacklist Table
-- Persists revoked JWT tokens so logout survives server restart
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'WatcherDB_Token_Blacklist')
BEGIN
    CREATE TABLE dbo.WatcherDB_Token_Blacklist (
        token_hash      NVARCHAR(128)   PRIMARY KEY,
        username        NVARCHAR(100)   NOT NULL,
        blacklisted_at  DATETIME2       NOT NULL DEFAULT GETDATE(),
        expires_at      DATETIME2       NOT NULL
    );

    CREATE INDEX IX_TokenBlacklist_Expires
        ON dbo.WatcherDB_Token_Blacklist(expires_at);

    PRINT 'Table WatcherDB_Token_Blacklist created successfully.';
END
ELSE
    PRINT 'Table WatcherDB_Token_Blacklist already exists.';
GO

-- Cleanup procedure: remove expired tokens (run periodically)
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'usp_cleanup_token_blacklist')
    DROP PROCEDURE dbo.usp_cleanup_token_blacklist;
GO

CREATE PROCEDURE dbo.usp_cleanup_token_blacklist
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.WatcherDB_Token_Blacklist
    WHERE expires_at < GETDATE();
END
GO

PRINT 'Procedure usp_cleanup_token_blacklist created.';
