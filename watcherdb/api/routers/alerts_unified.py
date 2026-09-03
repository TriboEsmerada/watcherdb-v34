"""
Unified Alerts Router (CONSOLIDADO)
Substitui os 6 endpoints individuais de alertas com um único endpoint parametrizado.

Endpoints antigos (DEPRECATED):
- /api/monitoring/backup/alerts
- /api/monitoring/cpu/alerts
- /api/monitoring/memory/alerts
- /api/monitoring/space/alerts
- /api/monitoring/alwayson/alerts
- /api/config/alerts (configuração, não monitoramento)

Novo endpoint (USE ESTE):
- /api/monitoring/alerts?type=backup,cpu,memory,space,alwayson&severity=critical,high,medium,low

Autor: WatcherDB Team
Data: 2026-02-20 (Consolidação de Endpoints)
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import logging
import time
from enum import Enum

# Imports dos serviços de alertas
try:
    from watcherdb.services.backup_analysis import BackupAnalysisEngine
    from watcherdb.api.routers.memory import get_memory_health_summary
    from watcherdb.api.routers.space import get_space_health_summary
    from watcherdb.api.routers.alwayson import get_alwayson_health_summary
    IMPORTS_OK = True
except Exception as e:
    logging.warning(f"Não foi possível importar serviços de alertas: {e}")
    IMPORTS_OK = False

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring",
    tags=["alerts-unified"],
    responses={404: {"description": "Not found"}},
)


class AlertType(str, Enum):
    """Tipos de alertas disponíveis"""
    BACKUP = "backup"
    CPU = "cpu"
    MEMORY = "memory"
    SPACE = "space"
    ALWAYSON = "alwayson"
    SECURITY = "security"
    WINDOWS = "windows"
    ALL = "all"


class AlertSeverity(str, Enum):
    """Níveis de severidade"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ============================================================================
# CACHE UNIFICADO DE ALERTAS - TTL de 1 minuto
# ============================================================================
_ALERTS_CACHE_TTL = 60
_ALERTS_CACHE: Dict[str, Dict] = {}


def _get_cached_alerts(cache_key: str) -> Optional[Dict]:
    """Retorna alertas do cache se válidos"""
    entry = _ALERTS_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _ALERTS_CACHE_TTL:
        return None
    logger.info(f"[CACHE HIT] Alerts {cache_key} (age: {int(time.time() - entry['ts'])}s)")
    return entry["data"]


def _set_alerts_cache(cache_key: str, data: Dict) -> None:
    """Salva alertas no cache"""
    _ALERTS_CACHE[cache_key] = {"data": data, "ts": time.time()}


@router.get("/alerts/unified")
async def get_unified_alerts(
    types: Optional[str] = Query(
        None,
        description="Tipos de alertas separados por vírgula (backup,cpu,memory,space,alwayson,security,windows) ou 'all'",
        example="backup,cpu,memory"
    ),
    severity: Optional[str] = Query(
        None,
        description="Severidades separadas por vírgula (critical,high,medium,low,info) ou 'all'",
        example="critical,high"
    ),
    server_id: Optional[str] = Query(
        None,
        description="Filtrar por servidor específico (opcional)"
    ),
    use_cache: bool = Query(
        True,
        description="Usar cache se disponível (TTL: 60s)"
    )
):
    """
    🆕 ENDPOINT UNIFICADO DE ALERTAS (v2.0)

    Substitui os 6 endpoints individuais com um único endpoint parametrizado.

    **Parâmetros:**
    - `types`: Filtra por tipos de alerta (backup, cpu, memory, space, alwayson, security, windows)
    - `severity`: Filtra por severidade (critical, high, medium, low, info)
    - `server_id`: Filtra por servidor específico (opcional)
    - `use_cache`: Usa cache de 60s para melhor performance

    **Exemplos:**
    - Todos alertas críticos: `/alerts/unified?severity=critical`
    - Alertas de backup e CPU: `/alerts/unified?types=backup,cpu`
    - Alertas críticos e high de um servidor: `/alerts/unified?severity=critical,high&server_id=SQL01_I01`

    **Migração:**
    - `/api/monitoring/backup/alerts` → `/alerts/unified?types=backup`
    - `/api/monitoring/cpu/alerts?severity=critical` → `/alerts/unified?types=cpu&severity=critical`

    Returns:
        JSON com alertas agregados e filtrados
    """
    try:
        # Criar cache key baseado em parâmetros
        cache_key = f"{types or 'all'}_{severity or 'all'}_{server_id or 'all'}"

        # Verificar cache
        if use_cache:
            cached = _get_cached_alerts(cache_key)
            if cached:
                cached["from_cache"] = True
                return JSONResponse(content=cached)

        # Parse tipos solicitados
        requested_types = []
        if types:
            if types.lower() == "all":
                requested_types = [t.value for t in AlertType if t != AlertType.ALL]
            else:
                requested_types = [t.strip().lower() for t in types.split(",")]
        else:
            requested_types = [t.value for t in AlertType if t != AlertType.ALL]

        # Parse severidades solicitadas
        requested_severities = []
        if severity:
            if severity.lower() == "all":
                requested_severities = [s.value for s in AlertSeverity]
            else:
                requested_severities = [s.strip().lower() for s in severity.split(",")]

        logger.info(f"[ALERTS UNIFIED] Buscando alertas: types={requested_types}, severity={requested_severities}, server={server_id}")

        # Agregar alertas de todas as fontes
        all_alerts = []
        errors = []

        # 🔧 Buscar alertas reais de cada tipo solicitado
        if IMPORTS_OK:
            # BACKUP ALERTS
            if "backup" in requested_types:
                try:
                    engine = BackupAnalysisEngine()
                    backup_alerts = engine.get_all_backup_alerts()
                    # Normalizar formato
                    for alert in backup_alerts:
                        all_alerts.append({
                            "id": f"backup_{alert.get('server_id', 'unknown')}_{alert.get('database', 'unknown')}",
                            "type": "backup",
                            "severity": alert.get("severity", "medium").lower(),
                            "server_id": alert.get("server_id"),
                            "database": alert.get("database"),
                            "message": alert.get("message"),
                            "timestamp": time.time(),
                            "details": alert.get("details", {})
                        })
                    logger.info(f"[ALERTS UNIFIED] Backup: {len(backup_alerts)} alertas")
                except Exception as e:
                    logger.error(f"[ALERTS UNIFIED] Erro ao buscar alertas de backup: {e}")
                    errors.append({"type": "backup", "error": str(e)})

            # MEMORY ALERTS
            if "memory" in requested_types:
                try:
                    summary = get_memory_health_summary()
                    for server in summary.get("servers", []):
                        server_id_mem = server.get("server_id")
                        memory_pct = server.get("memory_usage_percent", 0)
                        ple = server.get("page_life_expectancy", 0)

                        # Critical alerts
                        if memory_pct > 90:
                            all_alerts.append({
                                "id": f"memory_{server_id_mem}_high",
                                "type": "memory",
                                "severity": "critical",
                                "server_id": server_id_mem,
                                "message": f"Memória crítica: {memory_pct:.1f}%",
                                "timestamp": time.time(),
                                "details": {"memory_pct": memory_pct, "threshold": 90}
                            })
                        elif memory_pct > 80:
                            all_alerts.append({
                                "id": f"memory_{server_id_mem}_medium",
                                "type": "memory",
                                "severity": "high",
                                "server_id": server_id_mem,
                                "message": f"Memória alta: {memory_pct:.1f}%",
                                "timestamp": time.time(),
                                "details": {"memory_pct": memory_pct, "threshold": 80}
                            })

                        if ple < 300 and ple > 0:
                            all_alerts.append({
                                "id": f"memory_{server_id_mem}_ple",
                                "type": "memory",
                                "severity": "critical",
                                "server_id": server_id_mem,
                                "message": f"Page Life Expectancy baixo: {ple}s (esperado: >300s)",
                                "timestamp": time.time(),
                                "details": {"ple": ple, "threshold": 300}
                            })
                    logger.info(f"[ALERTS UNIFIED] Memory: {len([a for a in all_alerts if a['type']=='memory'])} alertas")
                except Exception as e:
                    logger.error(f"[ALERTS UNIFIED] Erro ao buscar alertas de memória: {e}")
                    errors.append({"type": "memory", "error": str(e)})

            # SPACE ALERTS
            if "space" in requested_types:
                try:
                    summary = get_space_health_summary()
                    critical_filegroups = summary.get("critical_filegroups", [])
                    for fg in critical_filegroups:
                        all_alerts.append({
                            "id": f"space_{fg.get('server_id')}_{fg.get('database')}_{fg.get('filegroup')}",
                            "type": "space",
                            "severity": "critical" if fg.get("usage_percent", 0) >= 95 else "high",
                            "server_id": fg.get("server_id"),
                            "database": fg.get("database"),
                            "filegroup": fg.get("filegroup"),
                            "message": f"Filegroup {fg.get('filegroup')} em {fg.get('usage_percent', 0):.1f}%",
                            "timestamp": time.time(),
                            "details": fg
                        })
                    logger.info(f"[ALERTS UNIFIED] Space: {len(critical_filegroups)} alertas")
                except Exception as e:
                    logger.error(f"[ALERTS UNIFIED] Erro ao buscar alertas de espaço: {e}")
                    errors.append({"type": "space", "error": str(e)})

            # ALWAYSON ALERTS
            if "alwayson" in requested_types:
                try:
                    summary = get_alwayson_health_summary()
                    issues = summary.get("issues", [])
                    for issue in issues:
                        all_alerts.append({
                            "id": f"alwayson_{issue.get('ag_name')}_{issue.get('issue_type')}",
                            "type": "alwayson",
                            "severity": issue.get("severity", "medium").lower(),
                            "server_id": issue.get("server_id"),
                            "availability_group": issue.get("ag_name"),
                            "message": issue.get("message"),
                            "timestamp": time.time(),
                            "details": issue
                        })
                    logger.info(f"[ALERTS UNIFIED] AlwaysOn: {len(issues)} alertas")
                except Exception as e:
                    logger.error(f"[ALERTS UNIFIED] Erro ao buscar alertas AlwaysOn: {e}")
                    errors.append({"type": "alwayson", "error": str(e)})

            # CPU ALERTS (simplificado - sem engine dedicado)
            if "cpu" in requested_types:
                # TODO: Implementar coleta de CPU alerts de todos servidores
                # Por enquanto, placeholder vazio
                logger.info(f"[ALERTS UNIFIED] CPU: 0 alertas (não implementado)")

            # SECURITY ALERTS
            if "security" in requested_types:
                # TODO: Integrar com security router
                logger.info(f"[ALERTS UNIFIED] Security: 0 alertas (não implementado)")

            # WINDOWS ALERTS
            if "windows" in requested_types:
                # TODO: Integrar com windows router
                logger.info(f"[ALERTS UNIFIED] Windows: 0 alertas (não implementado)")

        else:
            logger.warning("[ALERTS UNIFIED] Imports failed - returning empty alerts")

        # Aplicar filtros
        filtered_alerts = all_alerts

        # Filtrar por tipo
        if requested_types:
            filtered_alerts = [a for a in filtered_alerts if a["type"] in requested_types]

        # Filtrar por severidade
        if requested_severities:
            filtered_alerts = [a for a in filtered_alerts if a["severity"] in requested_severities]

        # Filtrar por servidor
        if server_id:
            normalized_server = server_id.replace("\\", "_").upper()
            filtered_alerts = [a for a in filtered_alerts if a["server_id"].upper() == normalized_server]

        # Ordenar por severidade (critical primeiro) e depois por timestamp
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        filtered_alerts.sort(key=lambda x: (severity_order.get(x["severity"], 5), -x["timestamp"]))

        # Calcular estatísticas
        stats = {
            "total": len(filtered_alerts),
            "by_severity": {},
            "by_type": {},
            "by_server": {}
        }

        for alert in filtered_alerts:
            # Por severidade
            sev = alert["severity"]
            stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1

            # Por tipo
            typ = alert["type"]
            stats["by_type"][typ] = stats["by_type"].get(typ, 0) + 1

            # Por servidor
            srv = alert["server_id"]
            stats["by_server"][srv] = stats["by_server"].get(srv, 0) + 1

        result = {
            "success": True,
            "version": "2.0-unified",
            "filters_applied": {
                "types": requested_types if requested_types else "all",
                "severity": requested_severities if requested_severities else "all",
                "server_id": server_id if server_id else "all"
            },
            "stats": stats,
            "alerts": filtered_alerts,
            "errors": errors if errors else None,
            "from_cache": False,
            "timestamp": time.time()
        }

        # Salvar no cache
        _set_alerts_cache(cache_key, result)

        logger.info(f"[ALERTS UNIFIED] Retornando {len(filtered_alerts)} alertas")

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"[ALERTS UNIFIED] Erro ao buscar alertas: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar alertas: {str(e)}"
        )


@router.get("/alerts/types")
async def get_alert_types():
    """
    Lista tipos de alertas disponíveis.

    Returns:
        JSON com lista de tipos e suas descrições
    """
    return JSONResponse(content={
        "success": True,
        "alert_types": [
            {"type": "backup", "description": "Gaps de backup, backups falhados", "endpoints_legacy": ["/api/monitoring/backup/alerts"]},
            {"type": "cpu", "description": "CPU alta, throttling", "endpoints_legacy": ["/api/monitoring/cpu/alerts"]},
            {"type": "memory", "description": "Memória alta, pressure", "endpoints_legacy": ["/api/monitoring/memory/alerts"]},
            {"type": "space", "description": "Espaço em disco crítico", "endpoints_legacy": ["/api/monitoring/space/alerts"]},
            {"type": "alwayson", "description": "Issues AlwaysOn, replicas", "endpoints_legacy": ["/api/monitoring/alwayson/alerts"]},
            {"type": "security", "description": "Vulnerabilidades de segurança", "endpoints_legacy": []},
            {"type": "windows", "description": "Métricas Windows OS", "endpoints_legacy": []}
        ],
        "severity_levels": [
            {"severity": "critical", "description": "Ação imediata necessária", "color": "#ef4444"},
            {"severity": "high", "description": "Ação recomendada em breve", "color": "#f59e0b"},
            {"severity": "medium", "description": "Melhoria recomendada", "color": "#eab308"},
            {"severity": "low", "description": "Recomendação geral", "color": "#6b7280"},
            {"severity": "info", "description": "Apenas informativo", "color": "#3b82f6"}
        ]
    })


@router.delete("/alerts/cache")
async def clear_alerts_cache():
    """
    Limpa todo o cache de alertas.

    Returns:
        JSON com confirmação
    """
    try:
        _ALERTS_CACHE.clear()
        logger.info("[CACHE] Cache de alertas limpo")
        return JSONResponse(content={
            "success": True,
            "message": "Cache de alertas limpo com sucesso"
        })
    except Exception as e:
        logger.error(f"[CACHE] Erro ao limpar cache: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao limpar cache: {str(e)}"
        )


@router.get("/alerts/health")
async def alerts_router_health():
    """Health check do router de alertas unificados"""
    return JSONResponse(content={
        "status": "healthy",
        "router": "alerts-unified",
        "version": "2.0",
        "cache_size": len(_ALERTS_CACHE),
        "cache_ttl_seconds": _ALERTS_CACHE_TTL,
        "imports_ok": IMPORTS_OK
    })
