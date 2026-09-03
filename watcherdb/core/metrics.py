"""
Prometheus metrics for WatcherDB.

Exposes /metrics endpoint for Prometheus scraping.
"""
import time
import logging
from typing import Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    generate_latest, CONTENT_TYPE_LATEST,
)

logger = logging.getLogger(__name__)

# Application info
APP_INFO = Info("watcherdb", "WatcherDB application info")

# Request metrics
REQUEST_COUNT = Counter(
    "watcherdb_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_DURATION = Histogram(
    "watcherdb_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# WebSocket metrics
WS_CONNECTIONS = Gauge(
    "watcherdb_websocket_connections",
    "Active WebSocket connections",
)

# Cache metrics
CACHE_HITS = Counter("watcherdb_cache_hits_total", "Cache hits")
CACHE_MISSES = Counter("watcherdb_cache_misses_total", "Cache misses")
CACHE_SIZE = Gauge("watcherdb_cache_size_bytes", "Cache memory usage in bytes")

# Connection pool metrics
POOL_ACTIVE = Gauge(
    "watcherdb_pool_active_connections",
    "Active database connections",
    ["pool"],
)
POOL_ERRORS = Counter(
    "watcherdb_pool_connection_errors_total",
    "Database connection errors",
    ["pool"],
)


def setup_metrics(app: FastAPI, version: str = "3.2.0"):
    """Register metrics middleware and /metrics endpoint."""

    APP_INFO.info({"version": version, "app": "watcherdb"})

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        # Normalize path to avoid high cardinality
        path = request.url.path
        # Group dynamic segments
        parts = path.split("/")
        normalized = "/".join(
            "{id}" if (i > 0 and parts[i-1] in ("servers", "users", "databases", "ag"))
            else p
            for i, p in enumerate(parts)
        )

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=normalized,
            status_code=response.status_code,
        ).inc()
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=normalized,
        ).observe(duration)

        return response

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics enabled at /metrics")
