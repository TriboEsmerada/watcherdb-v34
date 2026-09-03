"""
Pytest configuration and shared fixtures
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from watcherdb.core.cache import RedisLikeCache


@pytest.fixture
def cache():
    """Fixture for RedisLikeCache with in-memory storage"""
    return RedisLikeCache(persistence_file=None, max_memory_mb=10)


@pytest.fixture
def sample_alert_data():
    """Fixture with sample alert data"""
    return {
        "title": "Test Alert",
        "message": "This is a test alert",
        "level": "warning",
        "source": "test",
        "server_name": "TEST_SERVER",
        "database_name": "TEST_DB"
    }


@pytest.fixture
def sample_server_config():
    """Fixture with sample server configuration"""
    return {
        "id": 1,
        "host": "localhost",
        "instance": "MSSQLSERVER",
        "port": 1433,
        "environment": "test",
        "priority": "normal",
        "description": "Test server"
    }


# ============================================
# NEW FIXTURES — added during V3.2 audit
# ============================================

@pytest.fixture
def settings():
    """Fixture for WatcherDBSettings with test defaults"""
    from watcherdb.core.settings import WatcherDBSettings
    return WatcherDBSettings(
        jwt_secret_key="test-secret-key-for-testing-only",
        intelligence_server=r"TEST_SERVER\I01",
        intelligence_database="TEST_DB",
        connection_timeout=30,
        odbc_driver="ODBC Driver 17 for SQL Server",
    )


@pytest.fixture
def sql_validator():
    """Fixture for SQL validator function"""
    from watcherdb.core.sql_validator import validate_query
    return validate_query


@pytest.fixture
def pagination_params():
    """Fixture for default pagination parameters"""
    from api.pagination import PaginationParams
    return PaginationParams(page=1, page_size=50)


@pytest.fixture
def circuit_breakers():
    """Fixture returning all three circuit breakers"""
    from watcherdb.core.circuit_breaker import (
        sql_server_breaker, intelligence_breaker, external_service_breaker,
    )
    return {
        "sql_server": sql_server_breaker,
        "intelligence": intelligence_breaker,
        "external": external_service_breaker,
    }


@pytest.fixture
def copilot_service():
    """Fixture for CopilotService instance"""
    from services.copilot_service import CopilotService
    return CopilotService()


@pytest.fixture
def sample_kpi_data():
    """Fixture with sample KPI dashboard data"""
    return {
        "success": True,
        "data": {
            "services": {"total": 10, "ok": 8, "warning": 1, "critical": 1},
            "backup": {"total": 50, "ok": 45, "gap": 5},
            "space": {"total_gb": 1000, "used_gb": 750, "free_gb": 250},
        },
        "cached": False,
        "timestamp": 1711900000.0,
    }
