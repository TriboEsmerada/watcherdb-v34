"""Baseline migration — stamps current schema state

Revision ID: 001_baseline
Create Date: 2026-03-31
"""

revision = '001_baseline'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Baseline: current schema already exists in production
    # See database/00_WATCHERDB_MASTER_DEPLOY.sql for full schema
    pass

def downgrade():
    pass
