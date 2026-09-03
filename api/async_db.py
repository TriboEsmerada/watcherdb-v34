"""
WatcherDB Async DB Layer — Non-blocking wrapper for pyodbc.

Problem:
    pyodbc is synchronous. Calling it from async FastAPI endpoints blocks
    the event loop, degrading throughput under concurrent load.

Solution:
    Use anyio.to_thread.run_sync to run pyodbc calls in a thread pool,
    keeping the event loop free for other requests.

Usage:
    from api.async_db import async_execute_on_intelligence, async_execute_on_server

    # In an async endpoint:
    rows = await async_execute_on_intelligence("SELECT ...")
    rows = await async_execute_on_server("MYSERVER\\I01", "SELECT ...")

Drop-in replacements for execute_on_intelligence / execute_on_server.
"""

import logging
from typing import Dict, List, Any

import anyio

from api.connection_pool import execute_on_intelligence, execute_on_server

logger = logging.getLogger(__name__)


async def async_execute_on_intelligence(query: str) -> List[Dict[str, Any]]:
    """
    Async version of execute_on_intelligence.
    Runs the synchronous pyodbc call in a worker thread.
    """
    return await anyio.to_thread.run_sync(
        lambda: execute_on_intelligence(query),
        cancellable=True,
    )


async def async_execute_on_server(
    server_id: str, query: str, database: str = "master", timeout_s: int = 0
) -> List[Dict[str, Any]]:
    """
    Async version of execute_on_server.
    Runs the synchronous pyodbc call in a worker thread.
    timeout_s (2026-09-02): command timeout opcional; 0 = sem limite (historico).
    """
    return await anyio.to_thread.run_sync(
        lambda: execute_on_server(server_id, query, database, timeout_s),
        cancellable=True,
    )
