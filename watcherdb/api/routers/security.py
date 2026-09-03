"""
Security Analysis Router
Handles all security monitoring and vulnerability assessment endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import logging
import time

from modules.monitoring.security_analysis import SecurityAnalysisEngine

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring/security",
    tags=["security-analysis"],
    responses={404: {"description": "Not found"}},
)

# ============================================================================
# CACHE DE SECURITY CHECKS - TTL de 5 minutos (300 segundos)
# Análise de segurança é custosa, cache ajuda performance
# ============================================================================
_SECURITY_CACHE_TTL = 300  # 5 minutos
_SECURITY_CACHE: Dict[str, Dict] = {}


def _get_cached_security(server_id: str) -> Optional[Dict]:
    """Retorna dados do cache se válidos"""
    cache_key = server_id.upper()
    entry = _SECURITY_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _SECURITY_CACHE_TTL:
        return None
    logger.info(f"[CACHE HIT] Security analysis para {server_id} (age: {int(time.time() - entry['ts'])}s)")
    return entry["data"]


def _set_security_cache(server_id: str, data: Dict) -> None:
    """Salva dados no cache"""
    cache_key = server_id.upper()
    _SECURITY_CACHE[cache_key] = {"data": data, "ts": time.time()}
    logger.info(f"[CACHE SET] Security analysis para {server_id}")


@router.get("/server/{server_id}")
async def get_server_security_analysis(
    server_id: str,
    request: Request,
    use_cache: bool = Query(True, description="Usar cache se disponível"),
    refresh: bool = Query(False, description="Forçar atualização ignorando cache")
):
    """
    Análise completa de segurança para um servidor SQL Server.

    Inclui verificações de:
    - Autenticação e autorização
    - Permissões excessivas
    - Configurações de segurança do SQL Server
    - Criptografia (TDE, conexões, etc.)
    - Auditoria e logging
    - Versão e patches

    Args:
        server_id: Server identifier (HOST_INSTANCE ou HOST\\INSTANCE)
        use_cache: Se True, retorna dados do cache se válidos (padrão: True)
        refresh: Se True, força atualização ignorando cache (padrão: False)

    Returns:
        JSON com análise de segurança completa
    """
    try:
        # Normalizar server_id (substituir backslash por underscore)
        normalized_server_id = server_id.replace("\\", "_")

        # Verificar cache primeiro (se não for refresh forçado)
        if use_cache and not refresh:
            cached = _get_cached_security(normalized_server_id)
            if cached:
                cached["from_cache"] = True
                return JSONResponse(content=cached)

        logger.info(f"[SECURITY] Iniciando análise de segurança para {server_id}...")

        # Criar engine de análise com o sql_monitoring REAL
        # [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: Fix1 security]
        sql_mon = getattr(request.app.state, 'sql_monitoring', None)
        if sql_mon is None:
            raise HTTPException(status_code=503, detail="sql_monitoring não inicializado")
        engine = SecurityAnalysisEngine(sql_mon)

        # Executar análise
        result = await engine.analyze_server_security(normalized_server_id)

        # Adicionar metadados
        result["from_cache"] = False
        result["server_id"] = server_id

        # Salvar no cache
        _set_security_cache(normalized_server_id, result)

        logger.info(f"[SECURITY] Análise concluída para {server_id}: "
                   f"{result['summary']['total_checks']} checks, "
                   f"{result['summary']['critical_issues']} críticos")

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"[SECURITY] Erro ao analisar segurança de {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao analisar segurança: {str(e)}"
        )


@router.get("/server/{server_id}/summary")
async def get_security_summary(server_id: str, request: Request):
    """
    Resumo rápido do status de segurança (apenas estatísticas).
    Usa cache extensivamente para performance.

    Args:
        server_id: Server identifier

    Returns:
        JSON com resumo (sem detalhes dos checks)
    """
    try:
        # Tentar cache primeiro
        normalized_server_id = server_id.replace("\\", "_")
        cached = _get_cached_security(normalized_server_id)

        if cached:
            # Retornar apenas summary do cache
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "summary": cached.get("summary", {}),
                "from_cache": True
            })

        # Se não tem cache, fazer análise completa e retornar apenas summary
        result = await get_server_security_analysis(server_id, request, use_cache=False)
        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "summary": result.get("summary", {}),
            "from_cache": False
        })

    except Exception as e:
        logger.error(f"[SECURITY] Erro ao obter summary de {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter summary de segurança: {str(e)}"
        )


@router.get("/server/{server_id}/critical")
async def get_critical_issues(server_id: str, request: Request):
    """
    Retorna apenas issues críticos de segurança.

    Args:
        server_id: Server identifier

    Returns:
        JSON com lista de issues críticos
    """
    try:
        # Obter análise completa
        result = await get_server_security_analysis(server_id, request, use_cache=True)

        if not result.get("success"):
            return JSONResponse(content=result)

        # Filtrar apenas checks críticos com falha
        checks = result.get("checks", [])
        critical_issues = [
            check for check in checks
            if check.get("severity") == "critical" and check.get("status") == "fail"
        ]

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "critical_count": len(critical_issues),
            "issues": critical_issues
        })

    except Exception as e:
        logger.error(f"[SECURITY] Erro ao obter issues críticos de {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter issues críticos: {str(e)}"
        )


@router.delete("/cache/{server_id}")
async def clear_security_cache(server_id: str):
    """
    Limpa cache de análise de segurança para um servidor específico.

    Args:
        server_id: Server identifier

    Returns:
        JSON com confirmação
    """
    try:
        normalized_server_id = server_id.replace("\\", "_")
        cache_key = normalized_server_id.upper()

        if cache_key in _SECURITY_CACHE:
            del _SECURITY_CACHE[cache_key]
            logger.info(f"[CACHE] Cache de segurança limpo para {server_id}")
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
        logger.error(f"[SECURITY] Erro ao limpar cache de {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao limpar cache: {str(e)}"
        )


@router.get("/health")
async def security_router_health():
    """Health check do router de segurança"""
    return JSONResponse(content={
        "status": "healthy",
        "router": "security",
        "cache_size": len(_SECURITY_CACHE),
        "cache_ttl_seconds": _SECURITY_CACHE_TTL
    })
