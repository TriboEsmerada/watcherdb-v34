#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries Router - Assembled from sub-modules.

Sub-modules:
  - performance.py: blocking, deadlocks, slow queries, I/O, sessions, indexes, jobs, mirroring
  - space.py: log space, file space, file growth, databases, disk volumes/files, filegroup growth
  - backup.py: backup status, history, gaps, TDE
  - system.py: sql-script endpoint
  - helpers.py: shared execute_query_on_server, connection pool, serialization

TempDB endpoints (tempdb, tempdb-growth-analysis, tempdb-growth-culprits,
tempdb-villains, tempdb-space) and heavy diagnostic endpoints (diagnose-query,
expand-view, tempdb-diagnose) remain in the original sql_queries.py file
and are included here to keep all routes under /api/queries.
"""

from fastapi import APIRouter

from api.routers.queries.performance import router as performance_router
from api.routers.queries.space import router as space_router
from api.routers.queries.backup import router as backup_router
from api.routers.queries.system import router as system_router
from api.routers.queries.tempdb import router as tempdb_router
from api.routers.queries.plan_analysis import router as plan_analysis_router  # 2026-08-17 layout Diagnostico
from api.routers.queries.mirroring_diagnosis import router as mirroring_diagnosis_router  # 2026-08-17 drill-down mirroring
from api.routers.queries.tlog_diagnosis import router as tlog_diagnosis_router  # 2026-09-02 drill-down transaction log por base

# Main assembled router - same prefix as original
router = APIRouter(prefix="/api/queries", tags=["SQL Queries"])

# Include all sub-routers (no additional prefix - endpoints keep their paths)
router.include_router(performance_router)
router.include_router(space_router)
router.include_router(backup_router)
router.include_router(system_router)
router.include_router(tempdb_router)
router.include_router(plan_analysis_router)
router.include_router(mirroring_diagnosis_router)
router.include_router(tlog_diagnosis_router)

# Re-export helpers for backward compatibility
from api.routers.queries.helpers import (
    execute_query_on_server,
    _serialize_result,
    _get_global_executor,
    _DATABASES_CACHE,
    _DATABASES_CACHE_TTL,
    _get_cached_databases,
    _set_cached_databases,
)

__all__ = [
    'router',
    'execute_query_on_server',
    '_serialize_result',
    '_get_global_executor',
    '_DATABASES_CACHE',
    '_DATABASES_CACHE_TTL',
    '_get_cached_databases',
    '_set_cached_databases',
]
