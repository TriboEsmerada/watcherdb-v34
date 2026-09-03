"""
Async database connections using aioodbc.

Provides async query execution without blocking the FastAPI event loop.
For new async endpoints, use these functions instead of the sync connection pool.
"""
import os
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

try:
    import aioodbc
    HAS_AIOODBC = True
except ImportError:
    HAS_AIOODBC = False
    logger.info("aioodbc not installed — async DB disabled. Install with: pip install aioodbc")


def _build_dsn(server: str, database: str = "master", use_windows_auth: bool = True) -> str:
    """Build ODBC DSN string."""
    dsn = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Connection Timeout=30;"
    )
    if use_windows_auth:
        dsn += "Trusted_Connection=yes;"
    return dsn


@asynccontextmanager
async def async_connection(server: str, database: str = "master"):
    """
    Async context manager for database connections.

    Usage:
        async with async_connection("SERVER\\\\INSTANCE", "master") as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                rows = await cursor.fetchall()
    """
    if not HAS_AIOODBC:
        raise RuntimeError("aioodbc not installed. Install with: pip install aioodbc")

    dsn = _build_dsn(server, database)
    conn = await aioodbc.connect(dsn=dsn, autocommit=True)
    try:
        yield conn
    finally:
        await conn.close()


async def async_execute_query(
    server: str,
    query: str,
    database: str = "master",
    params: tuple = None,
) -> List[Dict[str, Any]]:
    """
    Execute a query asynchronously and return results as list of dicts.

    Args:
        server: SQL Server instance (HOST\\\\INSTANCE format)
        query: SQL query to execute
        database: Target database
        params: Optional query parameters

    Returns:
        List of dicts with column_name: value pairs
    """
    if not HAS_AIOODBC:
        # Fallback to sync pool via thread executor
        from api.connection_pool import execute_on_server
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, execute_on_server, server, query, database)

    async with async_connection(server, database) as conn:
        async with conn.cursor() as cursor:
            if params:
                await cursor.execute(query, params)
            else:
                await cursor.execute(query)

            if cursor.description is None:
                return []

            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchall()

            return [
                {col: (float(val) if hasattr(val, '__float__') else val)
                 for col, val in zip(columns, row)}
                for row in rows
            ]
