"""
API Router para descoberta de databases.

Endpoints:
- GET /discover/server/{server_id} - Descobre databases de um servidor
- POST /discover/all - Descobre databases de todos os servidores
- GET /discover/cache - Retorna cache de databases
- DELETE /discover/cache - Limpa cache

Autor: WatcherDB
Data: 2026-01-21
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from api.routers.auth_compat import _require_dba
from watcherdb.core.same_origin import require_same_origin
from fastapi.responses import JSONResponse

from services.database_discovery_service import get_discovery_service
from api.error_helpers import safe_http_error
from api.pagination import paginate, PaginationParams
from api.models import DatabaseDiscoveryResponse, GenericResponse, MessageResponse, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discover", tags=["Database Discovery"])


@router.get("/server/{server_id}", response_model=DatabaseDiscoveryResponse)
async def discover_server_databases(server_id: str, pagination: PaginationParams = Depends()):
    """
    Descobre databases de um servidor especifico.

    Args:
        server_id: ID do servidor (ex: OATXP01, SQLHDSPRD201_I01)

    Returns:
        Lista de databases com estado, recovery model, etc.
    """
    try:
        service = get_discovery_service()
        result = await service.discover_server(server_id)

        if result['success']:
            databases = result.get('databases', [])
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "database_count": result.get('database_count', 0),
                "databases": paginate(databases, pagination),
                "discovered_at": result.get('discovered_at')
            })
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Falha na descoberta: {result.get('error', 'Erro desconhecido')}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao descobrir databases de {server_id}: {e}")
        raise safe_http_error(500, e, "discovering server databases")


@router.post("/all", response_model=GenericResponse)
async def discover_all_databases(
    request: Request,
    background_tasks: BackgroundTasks,
    _origem: None = Depends(require_same_origin),
    run_in_background: bool = Query(default=True, description="Executar em background"),
    max_concurrent: int = Query(default=5, ge=1, le=20, description="Maximo de descobertas simultaneas")
):
    """
    Descobre databases de todos os servidores habilitados.

    Args:
        run_in_background: Se True, executa em background e retorna imediatamente
        max_concurrent: Numero maximo de descobertas simultaneas

    Returns:
        Se background=False: resultado completo
        Se background=True: confirmacao de que iniciou
    """
    await _require_dba(request)  # descoberta de BDs e operacao de DBA
    try:
        service = get_discovery_service()

        if run_in_background:
            # Executar em background
            background_tasks.add_task(service.discover_all, None, max_concurrent)
            return JSONResponse(content={
                "success": True,
                "message": "Descoberta iniciada em background",
                "max_concurrent": max_concurrent
            })
        else:
            # Executar e aguardar resultado
            result = await service.discover_all(max_concurrent=max_concurrent)
            return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Erro ao iniciar descoberta: {e}")
        raise safe_http_error(500, e, "starting database discovery")


@router.get("/cache", response_model=GenericResponse)
async def get_discovery_cache():
    """
    Retorna cache em memoria dos databases descobertos.

    Returns:
        Dict com todos os servidores e seus databases em cache
    """
    try:
        service = get_discovery_service()
        cache = service.get_all_cached()

        return JSONResponse(content={
            "success": True,
            "servers_in_cache": len(cache),
            "cache": cache
        })

    except Exception as e:
        logger.error(f"Erro ao obter cache: {e}")
        raise safe_http_error(500, e, "getting discovery cache")


@router.get("/cache/{server_id}", response_model=GenericResponse)
async def get_server_cache(server_id: str):
    """
    Retorna cache de databases de um servidor especifico.

    Args:
        server_id: ID do servidor

    Returns:
        Databases em cache ou 404 se nao encontrado
    """
    try:
        service = get_discovery_service()
        cached = service.get_cached_databases(server_id)

        if cached:
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "cached": True,
                **cached
            })
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Servidor {server_id} nao encontrado no cache. Execute /discover/server/{server_id} primeiro."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter cache de {server_id}: {e}")
        raise safe_http_error(500, e, "getting server discovery cache")


@router.delete("/cache", response_model=MessageResponse)
async def clear_discovery_cache(request: Request):
    """
    Limpa o cache em memoria de databases.

    Returns:
        Confirmacao de limpeza
    """
    await _require_dba(request)  # descoberta de BDs e operacao de DBA
    try:
        service = get_discovery_service()
        service.clear_cache()

        return JSONResponse(content={
            "success": True,
            "message": "Cache limpo com sucesso"
        })

    except Exception as e:
        logger.error(f"Erro ao limpar cache: {e}")
        raise safe_http_error(500, e, "clearing discovery cache")


@router.get("/failed", response_model=GenericResponse)
async def get_failed_servers():
    """
    Retorna lista de servidores que falharam na descoberta.

    Returns:
        Lista de servidores com erro e detalhes do erro
    """
    try:
        service = get_discovery_service()
        failed = service.get_failed_servers()

        return JSONResponse(content={
            "success": True,
            "failed_count": len(failed),
            "servers": failed
        })

    except Exception as e:
        logger.error(f"Erro ao obter servidores com falha: {e}")
        raise safe_http_error(500, e, "getting failed discovery servers")


@router.get("/status", response_model=GenericResponse)
async def get_discovery_status():
    """
    Retorna status do servico de descoberta.

    Returns:
        Informacoes sobre o servico e cache
    """
    try:
        service = get_discovery_service()
        cache = service.get_all_cached()

        total_databases = sum(
            entry.get('database_count', 0)
            for entry in cache.values()
        )

        return JSONResponse(content={
            "success": True,
            "service": "database_discovery",
            "status": "healthy",
            "servers_cached": len(cache),
            "total_databases_cached": total_databases,
            "cache_summary": {
                server_id: {
                    "database_count": entry.get('database_count', 0),
                    "discovered_at": entry.get('discovered_at')
                }
                for server_id, entry in cache.items()
            }
        })

    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "service": "database_discovery",
                "status": "unhealthy",
                "error": str(e)
            }
        )
