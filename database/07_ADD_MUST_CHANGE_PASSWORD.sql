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
