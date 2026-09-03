"""Add token blacklist table and must_change_password column

Revision ID: 002_security
Create Date: 2026-03-31
"""
from alembic import op

revision = '002_security'
down_revision = '001_baseline'
branch_labels = None
depends_on = None

def upgrade():
    # Token blacklist table
    op.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'WatcherDB_Token_Blacklist')
        CREATE TABLE dbo.WatcherDB_Token_Blacklist (
            token_hash      NVARCHAR(128)   PRIMARY KEY,
            username        NVARCHAR(100)   NOT NULL,
            blacklisted_at  DATETIME2       NOT NULL DEFAULT GETDATE(),
            expires_at      DATETIME2       NOT NULL
        )
    """)
    op.execute("""
        IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_TokenBlacklist_Expires')
        CREATE INDEX IX_TokenBlacklist_Expires
            ON dbo.WatcherDB_Token_Blacklist(expires_at)
    """)

    # must_change_password column
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users')
            AND name = 'must_change_password'
        )
        ALTER TABLE dbo.WatcherDB_Users
            ADD must_change_password BIT NOT NULL DEFAULT 1
    """)
    op.execute("""
        UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0
    """)

def downgrade():
    op.execute("DROP TABLE IF EXISTS dbo.WatcherDB_Token_Blacklist")
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users')
            AND name = 'must_change_password'
        )
        ALTER TABLE dbo.WatcherDB_Users DROP COLUMN must_change_password
    """)
