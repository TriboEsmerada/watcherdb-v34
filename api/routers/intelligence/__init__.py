#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intelligence KPIs Router - Assembled from sub-modules.

Sub-modules:
  - helpers.py  -- connection pool, query execution, cache, freshness, env detection
  - events.py   -- server offline resolve, history, summary endpoints
  - admin.py    -- health, refresh, available-views, filegroup detail

The large /dashboard and /instances/{kpi_type} endpoints remain in the
original intelligence_kpis.py file due to their extreme size (1600+ and 900+ lines).
"""

from fastapi import APIRouter

from api.routers.intelligence.events import router as events_router
from api.routers.intelligence.admin import router as admin_router

# Main assembled router - NO prefix (will be included in the parent router that has the prefix)
router = APIRouter(tags=["Intelligence KPIs"])

# Include all sub-routers
router.include_router(events_router)
router.include_router(admin_router)

# Re-export helpers for backward compatibility
from api.routers.intelligence.helpers import (
    execute_intelligence_query,
    execute_intelligence_query_async,
    _serialize_result,
    _get_cached_dashboard,
    _set_dashboard_cache,
    _last_known_values,
    _dashboard_cache,
    _cache_lock,
    is_data_fresh,
    _infer_env_from_instance,
    _detect_env,
    _count_by_env,
    _load_monitored_servers,
    _build_jobs_conn_str,
    _query_executor,
    FRESHNESS_WINDOWS,
    INTELLIGENCE_SERVER,
    INTELLIGENCE_DATABASE,
    INTELLIGENCE_SCHEMA,
    INTELLIGENCE_USE_WINDOWS_AUTH,
)

__all__ = [
    'router',
    'execute_intelligence_query',
    'execute_intelligence_query_async',
    '_serialize_result',
    '_get_cached_dashboard',
    '_set_dashboard_cache',
    '_last_known_values',
    'is_data_fresh',
    '_infer_env_from_instance',
    '_detect_env',
    '_count_by_env',
    'FRESHNESS_WINDOWS',
    'INTELLIGENCE_SERVER',
    'INTELLIGENCE_DATABASE',
    'INTELLIGENCE_SCHEMA',
]
