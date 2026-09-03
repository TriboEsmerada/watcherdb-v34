-- ============================================================
-- WatcherDB System Config Table
-- Persists Control Panel settings (AD, session policy, etc.)
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'WatcherDB_System_Config')
BEGIN
    CREATE TABLE dbo.WatcherDB_System_Config (
        config_key   VARCHAR(100)   PRIMARY KEY,
        config_value NVARCHAR(500),
        updated_at   DATETIME       DEFAULT GETDATE()
    );

    PRINT 'Table WatcherDB_System_Config created successfully.';
END
ELSE
    PRINT 'Table WatcherDB_System_Config already exists.';
GO
