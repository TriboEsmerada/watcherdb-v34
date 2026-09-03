"""
API routers for WatcherDB
"""

from watcherdb.api.auth_router import router as auth_router
from watcherdb.api.stats_router import router as stats_router
from watcherdb.api.health_router import router as health_router

__all__ = [
    "auth_router",
    "stats_router",
    "health_router",
]
