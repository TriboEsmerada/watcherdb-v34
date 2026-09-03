"""
Health Check API Router
Provides comprehensive health status for all monitored systems
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from watcherdb.core.auth import get_current_active_user, User

router = APIRouter(prefix="/api/health", tags=["Health"])


# ==========================================
# Models
# ==========================================
class ServerHealth(BaseModel):
    """Individual server health status"""
    server_id: int
    server_name: str
    status: str  # "healthy", "warning", "critical", "offline"
    last_check: str
    issues: List[str] = []
    metrics: Dict[str, Any] = {}


class HealthSummary(BaseModel):
    """Aggregated health summary"""
    overall_status: str
    total_servers: int
    healthy_count: int
    warning_count: int
    critical_count: int
    offline_count: int
    servers: List[ServerHealth]
    timestamp: str


# ==========================================
# Endpoints
# ==========================================
@router.get("", response_model=Dict[str, str])
async def health_check():
    """
    Basic health check (no authentication required)

    **Returns:**
    - Simple status message
    """
    return {
        "status": "healthy",
        "service": "WatcherDB",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/summary", response_model=HealthSummary)
async def get_health_summary(current_user: User = Depends(get_current_active_user)):
    """
    Get comprehensive health summary for all monitored SQL servers

    **Returns:**
    - Overall health status
    - Server-by-server health details
    - Aggregated statistics
    - Critical issues requiring attention
    """
    try:
        # Load server configuration
        servers = _load_server_configs()

        server_health_list: List[ServerHealth] = []
        healthy_count = 0
        warning_count = 0
        critical_count = 0
        offline_count = 0

        # Check each server
        for server in servers:
            health = _check_server_health(server)
            server_health_list.append(health)

            if health.status == "healthy":
                healthy_count += 1
            elif health.status == "warning":
                warning_count += 1
            elif health.status == "critical":
                critical_count += 1
            elif health.status == "offline":
                offline_count += 1

        # Determine overall status
        overall_status = "healthy"
        if critical_count > 0 or offline_count > 0:
            overall_status = "critical"
        elif warning_count > 0:
            overall_status = "warning"

        summary = HealthSummary(
            overall_status=overall_status,
            total_servers=len(servers),
            healthy_count=healthy_count,
            warning_count=warning_count,
            critical_count=critical_count,
            offline_count=offline_count,
            servers=server_health_list,
            timestamp=datetime.now().isoformat()
        )

        return summary

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting health summary: {str(e)}")


@router.get("/server/{server_id}", response_model=ServerHealth)
async def get_server_health(
    server_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed health status for specific server

    **Parameters:**
    - **server_id**: SQL Server ID

    **Returns:**
    - Detailed server health information
    - Current metrics
    - Active issues
    """
    try:
        servers = _load_server_configs()
        server = next((s for s in servers if s.get("id") == server_id), None)

        if not server:
            raise HTTPException(status_code=404, detail=f"Server {server_id} not found")

        health = _check_server_health(server)
        return health

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking server health: {str(e)}")


@router.get("/critical", response_model=List[ServerHealth])
async def get_critical_servers(current_user: User = Depends(get_current_active_user)):
    """
    Get list of servers with critical issues

    **Returns:**
    - List of servers with critical status
    """
    try:
        servers = _load_server_configs()
        critical_servers = []

        for server in servers:
            health = _check_server_health(server)
            if health.status in ["critical", "offline"]:
                critical_servers.append(health)

        return critical_servers

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting critical servers: {str(e)}")


# ==========================================
# Helper Functions
# ==========================================
def _load_server_configs() -> List[Dict]:
    """Load SQL server configurations"""
    try:
        config_file = Path("config/sql_servers.json")
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("servers", [])
        return []
    except Exception:
        return []


def _check_server_health(server: Dict) -> ServerHealth:
    """
    Check health of individual server

    In production, this would:
    - Connect to SQL Server
    - Check disk space
    - Check backup status
    - Check Always On status
    - Check memory/CPU
    - Check error log
    """
    # Mock implementation - replace with real health checks
    server_name = f"{server.get('host', 'unknown')}\\{server.get('instance', 'MSSQLSERVER')}"

    issues = []
    status = "healthy"
    metrics = {}

    # Simulate health checks (replace with real implementation)
    # Example checks:
    # - Disk space > 90%: critical
    # - Backup > 24 hours old: warning
    # - Connection failed: offline
    # - Memory > 90%: warning
    # - AlwaysOn sync issue: critical

    # For now, return healthy status
    # TODO: Implement real health checks

    return ServerHealth(
        server_id=server.get("id", 0),
        server_name=server_name,
        status=status,
        last_check=datetime.now().isoformat(),
        issues=issues,
        metrics=metrics
    )
