"""
Memory Analysis Router
Handles all memory-related monitoring endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, Any
import logging
import time
from datetime import datetime

from watcherdb.core.auth import get_current_user, User
from modules.monitoring.memory_analysis import (
    get_server_memory_analysis,
    get_alwayson_memory_comparison,
    get_memory_health_summary,
    analyze_os_memory_snapshot
)
from modules.monitoring.monitoring import SQLServerMonitoring

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring/memory",
    tags=["memory-analysis"],
    responses={404: {"description": "Not found"}},
)

# ============================================================================
# CACHE DE MEMORY - TTL de 2 minutos (120 segundos)
# Memory muda frequentemente mas 2 min é suficiente para navegação entre abas
# ============================================================================
_MEMORY_CACHE_TTL = 120  # 2 minutos
_MEMORY_CACHE: Dict[str, Dict] = {}


def _get_cached_memory(server_id: str) -> Optional[Dict]:
    """Retorna dados do cache se válidos"""
    cache_key = server_id.upper()
    entry = _MEMORY_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _MEMORY_CACHE_TTL:
        return None
    return entry["data"]


def _set_memory_cache(server_id: str, data: Dict) -> None:
    """Salva dados no cache"""
    cache_key = server_id.upper()
    _MEMORY_CACHE[cache_key] = {"ts": time.time(), "data": data}


@router.get("/server/{server_id}")
async def get_memory_analysis(
    server_id: str,
    current_user: User = Depends(get_current_user),
    skip_cache: bool = Query(False, description="Ignorar cache e buscar dados frescos")
):
    """Get memory analysis for a specific server

    Utiliza cache de 2 minutos para melhorar performance.
    Use skip_cache=true para forçar atualização.
    """
    try:
        # Verificar cache primeiro (se não for skip_cache)
        if not skip_cache:
            cached = _get_cached_memory(server_id)
            if cached:
                logger.debug(f"✅ [Memory] Cache HIT para {server_id}")
                cached['from_cache'] = True
                return cached

        logger.info(f"Memory analysis requested for server: {server_id} by {current_user.username}")

        # Criar instância do SQLServerMonitoring
        cache_path = "watcherdb_cache.db"
        sql_monitoring = SQLServerMonitoring(cache_path)

        # Converter server_id para server_name (formato esperado pela função)
        server_name = server_id.replace('_', '\\')
        display_name = server_name.replace('\\DEFAULT', '')

        # Chamar função async com await e passar sql_monitoring
        result = await get_server_memory_analysis(server_name, sql_monitoring)

        if not result:
            raise HTTPException(status_code=404, detail=f"Server {server_id} not found or no memory data available")

        response = {
            "success": True,
            "server_id": server_id,
            "server_name": display_name,
            "data": result,
            "timestamp": datetime.now().isoformat(),
            "from_cache": False
        }

        # Salvar no cache
        _set_memory_cache(server_id, response)

        return response

    except Exception as e:
        logger.error(f"Error in memory analysis for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alwayson/comparison")
async def get_alwayson_comparison(
    availability_group: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get memory comparison for AlwaysOn availability groups"""
    try:
        logger.info(f"AlwaysOn memory comparison requested by {current_user.username}")

        result = get_alwayson_memory_comparison(availability_group)

        if not result:
            raise HTTPException(
                status_code=404,
                detail="No AlwaysOn memory data available"
            )

        return result

    except Exception as e:
        logger.error(f"Error in AlwaysOn memory comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/summary")
async def get_health_summary(
    current_user: User = Depends(get_current_user)
):
    """Get aggregated memory health summary across all servers"""
    try:
        logger.info(f"Memory health summary requested by {current_user.username}")

        summary = get_memory_health_summary()

        return {
            "summary": summary,
            "timestamp": summary.get("timestamp"),
            "total_servers": summary.get("total_servers", 0)
        }

    except Exception as e:
        logger.error(f"Error generating memory health summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/pressure")
async def get_memory_pressure(
    server_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get memory pressure indicators for a specific server"""
    try:
        logger.info(f"Memory pressure check for {server_id} by {current_user.username}")

        # Criar instância do SQLServerMonitoring
        cache_path = "watcherdb_cache.db"
        sql_monitoring = SQLServerMonitoring(cache_path)
        
        # Converter server_id para server_name (formato esperado pela função)
        server_name = server_id.replace('_', '\\')
        
        # Chamar função async com await e passar sql_monitoring
        memory_data = await get_server_memory_analysis(server_name, sql_monitoring)

        if not memory_data:
            raise HTTPException(status_code=404, detail=f"Server {server_id} not found")

        # Extract pressure indicators
        # A função retorna um dict com os dados, então precisamos acessar corretamente
        memory_pressure_pct = memory_data.get("memory_pressure_pct")
        page_life_expectancy_data = memory_data.get("page_life_expectancy", {})
        ple = page_life_expectancy_data.get("PageLifeExpectancy", 0) if isinstance(page_life_expectancy_data, dict) else 0
        
        pressure_data = {
            "server_id": server_id,
            "memory_pressure_pct": memory_pressure_pct,
            "memory_pressure_status": memory_data.get("memory_pressure_status", "UNKNOWN"),
            "total_server_memory_mb": memory_data.get("total_server_memory_mb", 0),
            "target_server_memory_mb": memory_data.get("target_server_memory_mb", 0),
            "max_server_memory_mb": memory_data.get("max_server_memory_mb", 0),
            "page_life_expectancy": ple,
            "pressure_status": "normal"
        }

        # Determine pressure status
        if memory_pressure_pct is not None:
            if memory_pressure_pct < 80:
                pressure_data["pressure_status"] = "critical"
            elif memory_pressure_pct < 95:
                pressure_data["pressure_status"] = "warning"
            else:
                pressure_data["pressure_status"] = "normal"
        
        if ple > 0:
            if ple < 300:
                pressure_data["pressure_status"] = "critical"
            elif ple < 600 and pressure_data["pressure_status"] != "critical":
                pressure_data["pressure_status"] = "warning"

        return pressure_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking memory pressure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_memory_alerts(
    severity: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get memory-related alerts across all servers"""
    try:
        logger.info(f"Memory alerts requested by {current_user.username}")

        summary = get_memory_health_summary()
        alerts = []

        for server in summary.get("servers", []):
            server_id = server.get("server_id")
            memory_pct = server.get("memory_usage_percent", 0)
            ple = server.get("page_life_expectancy", 0)

            # Critical alerts
            if memory_pct > 90:
                alerts.append({
                    "server_id": server_id,
                    "severity": "critical",
                    "type": "high_memory_usage",
                    "message": f"Critical: Memory usage at {memory_pct:.1f}%",
                    "value": memory_pct
                })

            if ple < 300:
                alerts.append({
                    "server_id": server_id,
                    "severity": "critical",
                    "type": "low_page_life_expectancy",
                    "message": f"Critical: Page Life Expectancy at {ple}s (target: >300s)",
                    "value": ple
                })

            # Warning alerts
            elif memory_pct > 80:
                alerts.append({
                    "server_id": server_id,
                    "severity": "warning",
                    "type": "high_memory_usage",
                    "message": f"Warning: Memory usage at {memory_pct:.1f}%",
                    "value": memory_pct
                })

            if ple < 600 and ple >= 300:
                alerts.append({
                    "server_id": server_id,
                    "severity": "warning",
                    "type": "low_page_life_expectancy",
                    "message": f"Warning: Page Life Expectancy at {ple}s (target: >600s)",
                    "value": ple
                })

        # Filter by severity if specified
        if severity:
            alerts = [a for a in alerts if a["severity"].lower() == severity.lower()]

        return {
            "total_alerts": len(alerts),
            "alerts": sorted(alerts, key=lambda x: (x["severity"] == "warning", -x["value"]))
        }

    except Exception as e:
        logger.error(f"Error extracting memory alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
