"""
Statistics API Router
Provides WatcherDB usage statistics and metrics
"""

import psutil
import time
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends

from watcherdb.core.auth import get_current_active_user, User

router = APIRouter(prefix="/api/stats", tags=["Statistics"])

# Track application start time
APP_START_TIME = time.time()


@router.get("", response_model=Dict[str, Any])
async def get_stats(current_user: User = Depends(get_current_active_user)):
    """
    Get WatcherDB application statistics

    **Returns:**
    - Application uptime
    - System resource usage
    - Cache statistics
    - Alert statistics
    - API request statistics
    """
    try:
        # Calculate uptime
        uptime_seconds = time.time() - APP_START_TIME
        uptime_days = int(uptime_seconds // 86400)
        uptime_hours = int((uptime_seconds % 86400) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        stats = {
            "application": {
                "name": "WatcherDB",
                "version": "1.0.0",
                "uptime": {
                    "seconds": int(uptime_seconds),
                    "human_readable": f"{uptime_days}d {uptime_hours}h {uptime_minutes}m"
                },
                "start_time": datetime.fromtimestamp(APP_START_TIME).isoformat()
            },
            "system": {
                "cpu_percent": cpu_percent,
                "memory": {
                    "total_mb": round(memory.total / (1024 * 1024), 2),
                    "used_mb": round(memory.used / (1024 * 1024), 2),
                    "available_mb": round(memory.available / (1024 * 1024), 2),
                    "percent": memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
                    "used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
                    "free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
                    "percent": disk.percent
                }
            },
            "cache": {
                "enabled": True,
                "type": "RedisLikeCache",
                "note": "Cache stats available via cache.get_stats()"
            },
            "monitoring": {
                "total_servers": 0,  # Populated from SQL servers config
                "active_servers": 0,
                "monitored_databases": 0,
                "alwayson_groups": 0
            },
            "alerts": {
                "enabled": True,
                "active_alerts": 0,
                "total_sent_today": 0,
                "channels": ["email", "teams", "slack", "webhook"]
            },
            "api": {
                "total_requests": 0,
                "avg_response_time_ms": 0,
                "errors_count": 0
            },
            "user": {
                "username": current_user.username,
                "role": current_user.role.value
            }
        }

        return stats

    except Exception as e:
        return {
            "error": f"Error collecting stats: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/cache", response_model=Dict[str, Any])
async def get_cache_stats(current_user: User = Depends(get_current_active_user)):
    """
    Get cache statistics

    **Returns:**
    - Cache hit/miss rates
    - Total keys
    - Memory usage
    - TTL statistics
    """
    try:
        # Import here to avoid circular dependency
        from watcherdb.core.cache import RedisLikeCache

        # This would use the global cache instance
        # For now, return mock stats
        stats = {
            "total_keys": 0,
            "keys_with_ttl": 0,
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "memory_usage_mb": 0.0,
            "max_memory_mb": 100,
            "evictions": 0,
            "note": "Connect to global cache instance for real stats"
        }

        return stats

    except Exception as e:
        return {"error": f"Error collecting cache stats: {str(e)}"}


@router.get("/health", response_model=Dict[str, Any])
async def get_health_metrics():
    """
    Get basic health metrics (no authentication required)

    **Returns:**
    - Application health status
    - System resource availability
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        health_status = "healthy"
        issues = []

        if cpu_percent > 90:
            health_status = "degraded"
            issues.append("High CPU usage")

        if memory.percent > 90:
            health_status = "degraded"
            issues.append("High memory usage")

        return {
            "status": health_status,
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": int(time.time() - APP_START_TIME),
            "issues": issues,
            "metrics": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent
            }
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }
