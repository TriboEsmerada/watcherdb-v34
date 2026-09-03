"""
General Monitoring Router
Handles general monitoring and server management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
import logging

from watcherdb.core.auth import get_current_user, User
from modules.monitoring.monitoring import SQLServerMonitoring

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)


@router.get("/servers")
async def get_all_servers(
    current_user: User = Depends(get_current_user)
):
    """Get list of all monitored SQL Servers"""
    try:
        logger.info(f"All servers list requested by {current_user.username}")

        monitoring = SQLServerMonitoring()
        servers = monitoring.get_all_servers()

        return {
            "total_servers": len(servers),
            "servers": servers
        }

    except Exception as e:
        logger.error(f"Error getting servers list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}")
async def get_server_details(
    server_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed information about a specific server"""
    try:
        logger.info(f"Server details requested for {server_id}")

        monitoring = SQLServerMonitoring()
        server_info = monitoring.get_server_details(server_id)

        if not server_info:
            raise HTTPException(status_code=404, detail=f"Server {server_id} not found")

        return server_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting server details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_all_alerts(
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get all alerts across all servers"""
    try:
        logger.info(f"All alerts requested (severity: {severity}, type: {alert_type})")

        monitoring = SQLServerMonitoring()
        alerts = monitoring.get_all_alerts()

        # Filter by severity if specified
        if severity:
            alerts = [a for a in alerts if a.get("severity", "").lower() == severity.lower()]

        # Filter by type if specified
        if alert_type:
            alerts = [a for a in alerts if a.get("type", "").lower() == alert_type.lower()]

        return {
            "total_alerts": len(alerts),
            "alerts": sorted(alerts, key=lambda x: (x.get("severity") == "warning", x.get("timestamp", "")))
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-connection/{hostname}")
async def test_connection(
    hostname: str,
    current_user: User = Depends(get_current_user)
):
    """Test connection to a SQL Server"""
    try:
        logger.info(f"Connection test requested for {hostname}")

        monitoring = SQLServerMonitoring()
        result = monitoring.test_connection(hostname)

        if result.get("success"):
            return {
                "status": "success",
                "hostname": hostname,
                "message": "Connection successful",
                "server_version": result.get("version"),
                "response_time_ms": result.get("response_time_ms")
            }
        else:
            return {
                "status": "failed",
                "hostname": hostname,
                "message": result.get("error"),
                "error_details": result.get("error_details")
            }

    except Exception as e:
        logger.error(f"Error testing connection to {hostname}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user)
):
    """Get summary data for main monitoring dashboard"""
    try:
        logger.info(f"Dashboard summary requested by {current_user.username}")

        monitoring = SQLServerMonitoring()

        # Aggregate data from different sources
        servers = monitoring.get_all_servers()
        alerts = monitoring.get_all_alerts()

        summary = {
            "servers": {
                "total": len(servers),
                "online": sum(1 for s in servers if s.get("status") == "online"),
                "offline": sum(1 for s in servers if s.get("status") == "offline"),
                "warning": sum(1 for s in servers if s.get("health_status") == "warning")
            },
            "alerts": {
                "total": len(alerts),
                "critical": sum(1 for a in alerts if a.get("severity") == "critical"),
                "warning": sum(1 for a in alerts if a.get("severity") == "warning"),
                "info": sum(1 for a in alerts if a.get("severity") == "info")
            },
            "health_score": 100.0  # Calculate based on alerts and server status
        }

        # Calculate health score
        if summary["servers"]["total"] > 0:
            health_score = 100
            health_score -= (summary["servers"]["offline"] * 10)
            health_score -= (summary["alerts"]["critical"] * 5)
            health_score -= (summary["alerts"]["warning"] * 2)
            summary["health_score"] = max(0, min(100, health_score))

        return summary

    except Exception as e:
        logger.error(f"Error generating dashboard summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/databases")
async def get_server_databases(
    server_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get list of databases on a specific server"""
    try:
        logger.info(f"Databases list requested for {server_id}")

        monitoring = SQLServerMonitoring()
        databases = monitoring.get_server_databases(server_id)

        return {
            "server_id": server_id,
            "database_count": len(databases),
            "databases": databases
        }

    except Exception as e:
        logger.error(f"Error getting databases for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/performance")
async def get_server_performance(
    server_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get performance metrics for a server"""
    try:
        logger.info(f"Performance metrics requested for {server_id}")

        monitoring = SQLServerMonitoring()
        performance = monitoring.get_server_performance(server_id)

        if not performance:
            raise HTTPException(status_code=404, detail=f"No performance data for {server_id}")

        return performance

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
