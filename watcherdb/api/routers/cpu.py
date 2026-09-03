"""
CPU Analysis Router
Handles all CPU-related monitoring endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict
import logging
import time

from watcherdb.core.auth import get_current_user, User
from modules.monitoring.cpu_analysis import get_server_cpu_analysis
from modules.monitoring.monitoring import SQLServerMonitoring

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring/cpu",
    tags=["cpu-analysis"],
    responses={404: {"description": "Not found"}},
)

# ============================================================================
# CACHE DE CPU - TTL de 2 minutos (120 segundos)
# CPU muda frequentemente mas 2 min é suficiente para navegação entre abas
# ============================================================================
_CPU_CACHE_TTL = 120  # 2 minutos
_CPU_CACHE: Dict[str, Dict] = {}


def _get_cached_cpu(server_id: str) -> Optional[Dict]:
    """Retorna dados do cache se válidos"""
    cache_key = server_id.upper()
    entry = _CPU_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _CPU_CACHE_TTL:
        return None
    return entry["data"]


def _set_cpu_cache(server_id: str, data: Dict) -> None:
    """Salva dados no cache"""
    cache_key = server_id.upper()
    _CPU_CACHE[cache_key] = {"ts": time.time(), "data": data}


@router.get("/server/{server_id}")
async def get_cpu_analysis(
    server_id: str,
    current_user: User = Depends(get_current_user),
    skip_cache: bool = Query(False, description="Ignorar cache e buscar dados frescos")
):
    """Get CPU analysis for a specific server

    Utiliza cache de 2 minutos para melhorar performance.
    Use skip_cache=true para forçar atualização.
    """
    try:
        # Verificar cache primeiro (se não for skip_cache)
        if not skip_cache:
            cached = _get_cached_cpu(server_id)
            if cached:
                logger.debug(f"✅ [CPU] Cache HIT para {server_id}")
                cached['from_cache'] = True
                return cached

        logger.info(f"CPU analysis requested for server: {server_id} by {current_user.username}")

        # Criar instância do SQLServerMonitoring
        cache_path = "watcherdb_cache.db"
        sql_monitoring = SQLServerMonitoring(cache_path)

        # Converter server_id para server_name (formato esperado pela função)
        server_name = server_id.replace('_', '\\')

        # Chamar função async com await e passar sql_monitoring
        result = await get_server_cpu_analysis(server_name, sql_monitoring)

        if not result:
            raise HTTPException(status_code=404, detail=f"No CPU data for server {server_id}")

        response = {
            "success": True,
            "server_id": server_id,
            "server_name": server_name.replace('\\DEFAULT', ''),
            "data": result,
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "from_cache": False
        }

        # Salvar no cache
        _set_cpu_cache(server_id, response)

        return response

    except Exception as e:
        logger.error(f"Error in CPU analysis for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_cpu_alerts(
    severity: Optional[str] = None,
    threshold: Optional[float] = 80.0,
    current_user: User = Depends(get_current_user)
):
    """Get CPU-related alerts across all servers"""
    try:
        logger.info(f"CPU alerts requested (threshold: {threshold}%)")

        # This would ideally iterate through all servers
        # For now, returning a placeholder structure
        alerts = []

        # TODO: Implement actual alert collection from all servers
        # For each server, check CPU usage against threshold

        if severity:
            alerts = [a for a in alerts if a.get("severity", "").lower() == severity.lower()]

        return {
            "total_alerts": len(alerts),
            "threshold": threshold,
            "alerts": alerts
        }

    except Exception as e:
        logger.error(f"Error extracting CPU alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
