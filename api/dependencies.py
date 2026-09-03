"""
FastAPI dependency injection -- request-scoped dependencies.

Migration strategy:
    This module centralizes singleton access behind FastAPI Depends().
    Benefits:
    - Easier to mock in tests (override dependencies instead of patching globals)
    - Explicit declaration of what each endpoint needs
    - Future: can add request-scoped resources (e.g., per-request DB sessions)

    Migration plan (incremental, not big-bang):
    1. [DONE] Create this module with get_pool() and get_intelligence_db()
    2. [DONE] Migrate 1-2 routers as examples (users.py, alwayson.py)
    3. [TODO] Migrate remaining routers one-by-one in future PRs
    4. [TODO] Add request-scoped dependencies (e.g., current_user from auth)
"""
from api.connection_pool import (
    get_sql_server_pool,
    get_intelligence_pool,
    SQLServerConnectionPool,
    IntelligenceConnectionPool,
)
from modules.monitoring.watcherdb_alwayson_check import (
    AlwaysOnChecker,
    get_alwayson_checker,
)


def get_pool() -> SQLServerConnectionPool:
    """Dependency: SQL Server connection pool (singleton)."""
    return get_sql_server_pool()


def get_intelligence_db() -> IntelligenceConnectionPool:
    """Dependency: Intelligence DB connection pool (singleton)."""
    return get_intelligence_pool()


def get_checker() -> AlwaysOnChecker:
    """Dependency: AlwaysOn checker (singleton)."""
    return get_alwayson_checker()
