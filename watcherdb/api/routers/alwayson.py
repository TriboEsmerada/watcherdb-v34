"""
AlwaysOn Availability Groups Router
Handles all AlwaysOn-related monitoring endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import logging

from watcherdb.core.auth import get_current_user, User

# FIND-20260417-015 F15.1 (2026-04-17): import `from modules.monitoring.alwayson_check`
# removed — módulo nunca existiu em nenhum snapshot. Este ficheiro não está
# registado em watcherdb_main.py (rota live é api/routers/alwayson.py),
# os endpoints abaixo referenciam os 3 helpers removidos mas nunca são
# chamados. Ficheiro preservado por decisão separada sobre remoção total
# (alerts_unified.py também não-funcional — ver FIND-015 extended notes).
# Se alguém tentar usar estes endpoints, vão levantar NameError —
# comportamento igual a antes porque não havia registo da rota.

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring/alwayson",
    tags=["alwayson"],
    responses={404: {"description": "Not found"}},
)


@router.get("/status")
async def get_alwayson_status(
    current_user: User = Depends(get_current_user)
):
    """Get overall AlwaysOn status across all availability groups"""
    try:
        logger.info(f"AlwaysOn status requested by {current_user.username}")

        status = check_alwayson_status()

        return {
            "status": status,
            "timestamp": status.get("timestamp")
        }

    except Exception as e:
        logger.error(f"Error getting AlwaysOn status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/availability-groups")
async def list_availability_groups(
    current_user: User = Depends(get_current_user)
):
    """List all AlwaysOn availability groups"""
    try:
        logger.info(f"Availability groups list requested")

        ag_list = get_all_availability_groups()

        return {
            "total_groups": len(ag_list),
            "availability_groups": ag_list
        }

    except Exception as e:
        logger.error(f"Error listing availability groups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/availability-group/{ag_name}")
async def get_availability_group(
    ag_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get details for a specific availability group"""
    try:
        logger.info(f"Details requested for AG: {ag_name}")

        ag_list = get_all_availability_groups()
        ag = next((ag for ag in ag_list if ag.get("name") == ag_name), None)

        if not ag:
            raise HTTPException(status_code=404, detail=f"Availability group {ag_name} not found")

        return ag

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AG details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/summary")
async def get_health_summary(
    current_user: User = Depends(get_current_user)
):
    """Get health summary for all availability groups"""
    try:
        logger.info(f"AlwaysOn health summary requested")

        summary = get_ag_health_summary()

        return summary

    except Exception as e:
        logger.error(f"Error getting health summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_alwayson_alerts(
    severity: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get AlwaysOn-related alerts"""
    try:
        logger.info(f"AlwaysOn alerts requested")

        ag_list = get_all_availability_groups()
        alerts = []

        for ag in ag_list:
            ag_name = ag.get("name")
            health_state = ag.get("health_state", "UNKNOWN")
            sync_health = ag.get("synchronization_health", "UNKNOWN")

            # Critical alerts
            if health_state in ["CRITICAL", "ERROR"]:
                alerts.append({
                    "ag_name": ag_name,
                    "severity": "critical",
                    "type": "unhealthy_ag",
                    "message": f"Availability group {ag_name} health state: {health_state}",
                    "value": health_state
                })

            if sync_health in ["NOT_HEALTHY", "PARTIALLY_HEALTHY"]:
                alerts.append({
                    "ag_name": ag_name,
                    "severity": "critical" if sync_health == "NOT_HEALTHY" else "warning",
                    "type": "sync_issue",
                    "message": f"Synchronization health issue in {ag_name}: {sync_health}",
                    "value": sync_health
                })

            # Check replicas
            for replica in ag.get("replicas", []):
                role = replica.get("role")
                operational_state = replica.get("operational_state")
                sync_state = replica.get("synchronization_state")

                if operational_state != "ONLINE":
                    alerts.append({
                        "ag_name": ag_name,
                        "replica": replica.get("replica_server_name"),
                        "severity": "critical",
                        "type": "replica_offline",
                        "message": f"Replica {replica.get('replica_server_name')} is {operational_state}",
                        "value": operational_state
                    })

                if role == "SECONDARY" and sync_state not in ["SYNCHRONIZED", "SYNCHRONIZING"]:
                    alerts.append({
                        "ag_name": ag_name,
                        "replica": replica.get("replica_server_name"),
                        "severity": "warning",
                        "type": "sync_issue",
                        "message": f"Replica sync state: {sync_state}",
                        "value": sync_state
                    })

        # Filter by severity if specified
        if severity:
            alerts = [a for a in alerts if a["severity"].lower() == severity.lower()]

        return {
            "total_alerts": len(alerts),
            "alerts": sorted(alerts, key=lambda x: x["severity"] == "warning")
        }

    except Exception as e:
        logger.error(f"Error extracting AlwaysOn alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/availability-group/{ag_name}/replicas")
async def get_ag_replicas(
    ag_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get replica information for an availability group"""
    try:
        logger.info(f"Replicas requested for AG: {ag_name}")

        ag_list = get_all_availability_groups()
        ag = next((ag for ag in ag_list if ag.get("name") == ag_name), None)

        if not ag:
            raise HTTPException(status_code=404, detail=f"Availability group {ag_name} not found")

        replicas = ag.get("replicas", [])

        return {
            "ag_name": ag_name,
            "replica_count": len(replicas),
            "replicas": replicas
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting replicas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
