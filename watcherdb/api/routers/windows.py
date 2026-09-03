"""
Windows Metrics Router
Handles Windows OS-level metrics and performance data
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import logging
import time
import pyodbc

from api.connection_pool import get_sql_server_pool

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring/windows",
    tags=["windows-metrics"],
    responses={404: {"description": "Not found"}},
)

# ============================================================================
# CACHE DE WINDOWS METRICS - TTL de 1 minuto (60 segundos)
# Métricas de OS mudam frequentemente
# ============================================================================
_WINDOWS_CACHE_TTL = 60  # 1 minuto
_WINDOWS_CACHE: Dict[str, Dict] = {}


def _get_cached_metrics(server_id: str) -> Optional[Dict]:
    """Retorna dados do cache se válidos"""
    cache_key = server_id.upper()
    entry = _WINDOWS_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _WINDOWS_CACHE_TTL:
        return None
    logger.info(f"[CACHE HIT] Windows metrics para {server_id} (age: {int(time.time() - entry['ts'])}s)")
    return entry["data"]


def _set_metrics_cache(server_id: str, data: Dict) -> None:
    """Salva dados no cache"""
    cache_key = server_id.upper()
    _WINDOWS_CACHE[cache_key] = {"data": data, "ts": time.time()}
    logger.info(f"[CACHE SET] Windows metrics para {server_id}")


def get_pooled_connection(server_id: str, database: str = "master"):
    """
    Obtém conexão do pool global.

    Args:
        server_id: Server identifier (HOST_INSTANCE ou HOST\\INSTANCE)
        database: Database to connect (default: master)

    Returns:
        pyodbc.Connection
    """
    try:
        pool = get_sql_server_pool()
        return pool.get_connection(server_id, database)
    except Exception as e:
        logger.error(f"[WINDOWS] Erro ao obter conexão para {server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro de conexão: {str(e)}")


@router.get("/server/{server_id}")
async def get_windows_metrics(
    server_id: str,
    use_cache: bool = Query(True, description="Usar cache se disponível")
):
    """
    Métricas do Windows Server coletadas via SQL Server.

    Inclui:
    - CPU do sistema operacional (% utilização)
    - Memória disponível (MB)
    - Uptime do sistema
    - Versão do Windows
    - Processos em execução

    Args:
        server_id: Server identifier
        use_cache: Se True, usa cache se disponível

    Returns:
        JSON com métricas do Windows
    """
    try:
        # Normalizar server_id
        normalized_server_id = server_id.replace("\\", "_")

        # Verificar cache
        if use_cache:
            cached = _get_cached_metrics(normalized_server_id)
            if cached:
                cached["from_cache"] = True
                return JSONResponse(content=cached)

        logger.info(f"[WINDOWS] Coletando métricas Windows para {server_id}...")

        conn = get_pooled_connection(normalized_server_id)
        cursor = conn.cursor()

        # Query para métricas Windows via SQL Server DMVs
        query = """
        -- Métricas do Windows Server via SQL Server
        SELECT
            -- CPU do SO (últimos 256 samples)
            (SELECT TOP 1 100 - record.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int')
             FROM (
                SELECT CONVERT(XML, record) AS record
                FROM sys.dm_os_ring_buffers
                WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
                AND record LIKE '%<SystemHealth>%'
             ) AS x
             ORDER BY record.value('(./Record/@id)[1]', 'int') DESC
            ) AS os_cpu_pct,

            -- Memória disponível no SO (MB)
            (SELECT available_physical_memory_kb / 1024
             FROM sys.dm_os_sys_memory
            ) AS os_available_memory_mb,

            -- Memória total do SO (MB)
            (SELECT total_physical_memory_kb / 1024
             FROM sys.dm_os_sys_memory
            ) AS os_total_memory_mb,

            -- Uptime do SQL Server (aproximação do uptime do SO)
            DATEDIFF(SECOND, sqlserver_start_time, GETDATE()) AS sql_uptime_seconds,

            -- Versão do Windows
            (SELECT windows_release
             FROM sys.dm_os_windows_info
            ) AS windows_version,

            -- Service Pack do Windows
            (SELECT windows_service_pack_level
             FROM sys.dm_os_windows_info
            ) AS windows_service_pack,

            -- Número de CPUs físicas
            (SELECT cpu_count FROM sys.dm_os_sys_info) AS cpu_count,

            -- Número de schedulers
            (SELECT scheduler_count FROM sys.dm_os_sys_info) AS scheduler_count
        FROM sys.dm_os_sys_info;
        """

        cursor.execute(query)
        row = cursor.fetchone()

        if not row:
            raise Exception("Nenhum dado retornado da query")

        # Processar resultados
        os_cpu_pct = row[0] if row[0] is not None else 0
        os_available_memory_mb = row[1] if row[1] is not None else 0
        os_total_memory_mb = row[2] if row[2] is not None else 0
        sql_uptime_seconds = row[3] if row[3] is not None else 0
        windows_version = row[4] if row[4] else "Unknown"
        windows_service_pack = row[5] if row[5] else "None"
        cpu_count = row[6] if row[6] is not None else 0
        scheduler_count = row[7] if row[7] is not None else 0

        # Calcular % de memória usada
        os_memory_used_pct = 0
        if os_total_memory_mb > 0:
            os_memory_used_mb = os_total_memory_mb - os_available_memory_mb
            os_memory_used_pct = round((os_memory_used_mb / os_total_memory_mb) * 100, 2)

        # Formatar uptime
        uptime_days = sql_uptime_seconds // 86400
        uptime_hours = (sql_uptime_seconds % 86400) // 3600
        uptime_str = f"{uptime_days}d {uptime_hours}h"

        result = {
            "success": True,
            "server_id": server_id,
            "os_metrics": {
                "cpu_percent": os_cpu_pct,
                "memory_available_mb": os_available_memory_mb,
                "memory_total_mb": os_total_memory_mb,
                "memory_used_percent": os_memory_used_pct,
                "uptime_seconds": sql_uptime_seconds,
                "uptime_formatted": uptime_str,
                "cpu_count": cpu_count,
                "scheduler_count": scheduler_count
            },
            "windows_info": {
                "version": windows_version,
                "service_pack": windows_service_pack
            },
            "from_cache": False
        }

        cursor.close()
        conn.close()

        # Salvar no cache
        _set_metrics_cache(normalized_server_id, result)

        logger.info(f"[WINDOWS] Métricas coletadas para {server_id}: "
                   f"CPU={os_cpu_pct}%, Mem={os_memory_used_pct}%")

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"[WINDOWS] Erro ao coletar métricas de {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao coletar métricas Windows: {str(e)}"
        )


@router.get("/server/{server_id}/processes")
async def get_windows_processes(server_id: str):
    """
    Lista processos em execução no Windows Server.

    NOTA: Requer xp_cmdshell habilitado (não recomendado em produção).
    Esta função está desabilitada por padrão por questões de segurança.

    Args:
        server_id: Server identifier

    Returns:
        JSON com lista de processos
    """
    return JSONResponse(content={
        "success": False,
        "error": "Endpoint desabilitado por questões de segurança",
        "message": "A listagem de processos via xp_cmdshell está desabilitada. Use ferramentas de monitoramento Windows nativas."
    })


@router.get("/server/{server_id}/event-log")
async def get_windows_event_log(
    server_id: str,
    hours: int = Query(24, description="Últimas N horas", ge=1, le=168)
):
    """
    Eventos do Windows Event Log (Application, System).

    NOTA: Requer xp_cmdshell habilitado (não recomendado).
    Esta função está desabilitada por padrão.

    Args:
        server_id: Server identifier
        hours: Últimas N horas de eventos (1-168)

    Returns:
        JSON com eventos do Windows
    """
    return JSONResponse(content={
        "success": False,
        "error": "Endpoint desabilitado por questões de segurança",
        "message": "A consulta ao Event Log via xp_cmdshell está desabilitada. Use o módulo WinLog dedicado."
    })


@router.delete("/cache/{server_id}")
async def clear_windows_cache(server_id: str):
    """
    Limpa cache de métricas Windows para um servidor específico.

    Args:
        server_id: Server identifier

    Returns:
        JSON com confirmação
    """
    try:
        normalized_server_id = server_id.replace("\\", "_")
        cache_key = normalized_server_id.upper()

        if cache_key in _WINDOWS_CACHE:
            del _WINDOWS_CACHE[cache_key]
            logger.info(f"[CACHE] Cache de Windows metrics limpo para {server_id}")
            return JSONResponse(content={
                "success": True,
                "message": f"Cache limpo para {server_id}"
            })
        else:
            return JSONResponse(content={
                "success": True,
                "message": f"Nenhum cache encontrado para {server_id}"
            })

    except Exception as e:
        logger.error(f"[WINDOWS] Erro ao limpar cache de {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao limpar cache: {str(e)}"
        )


@router.get("/health")
async def windows_router_health():
    """Health check do router de Windows metrics"""
    return JSONResponse(content={
        "status": "healthy",
        "router": "windows",
        "cache_size": len(_WINDOWS_CACHE),
        "cache_ttl_seconds": _WINDOWS_CACHE_TTL
    })
