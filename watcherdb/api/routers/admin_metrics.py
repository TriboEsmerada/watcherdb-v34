"""
Admin Metrics Router
Endpoints administrativos para métricas e estatísticas do sistema.

Inclui:
- Estatísticas de uso de endpoints
- Identificação de endpoints não utilizados
- Performance de endpoints
- Relatórios de auditoria

⚠️ SEGURANÇA: Todos endpoints requerem autenticação com role ADMIN

Autor: WatcherDB Team
Data: 2026-02-20
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional
import logging

from watcherdb.core.endpoint_usage_tracker import (
    EndpointUsageTracker,
    get_most_used_endpoints,
    get_slowest_endpoints
)
from watcherdb.core.auth import require_admin, User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-metrics"],
    responses={404: {"description": "Not found"}},
)


@router.get("/metrics/endpoints/usage")
async def get_endpoints_usage_stats(
    top_n: int = Query(20, description="Número de top endpoints a retornar", ge=1, le=100),
    current_user: User = Depends(require_admin)
):
    """
    🔐 Estatísticas de uso de todos os endpoints rastreados.

    **Requer:** Role ADMIN

    Returns:
        JSON com estatísticas completas de uso
    """
    try:
        stats = EndpointUsageTracker.get_usage_stats()
        unused = EndpointUsageTracker.get_unused_endpoints(min_days_since_first_tracked=7)
        most_used = get_most_used_endpoints(top_n=top_n)
        slowest = get_slowest_endpoints(top_n=top_n)

        return JSONResponse(content={
            "success": True,
            "summary": {
                "total_endpoints_tracked": len(stats),
                "total_endpoints_unused": len(unused),
                "total_calls_all_endpoints": sum(s["total_calls"] for s in stats.values()),
                "deprecated_endpoints_count": sum(1 for s in stats.values() if s.get("deprecated", False))
            },
            "most_used_endpoints": most_used,
            "slowest_endpoints": slowest,
            "unused_endpoints": unused[:20],  # Limitar a 20 para não sobrecarregar resposta
            "all_stats": stats
        })

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao obter estatísticas de uso: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter estatísticas: {str(e)}"
        )


@router.get("/metrics/endpoints/unused")
async def get_unused_endpoints(
    min_days: int = Query(7, description="Mínimo de dias sem chamadas", ge=1),
    current_user: User = Depends(require_admin)
):
    """
    🔐 Lista endpoints que não são utilizados.

    **Requer:** Role ADMIN

    Args:
        min_days: Número mínimo de dias sem chamadas para considerar como não utilizado

    Returns:
        JSON com lista de endpoints não utilizados
    """
    try:
        unused = EndpointUsageTracker.get_unused_endpoints(min_days_since_first_tracked=min_days)

        return JSONResponse(content={
            "success": True,
            "min_days_threshold": min_days,
            "total_unused": len(unused),
            "unused_endpoints": unused,
            "recommendation": "Considere deprecar ou remover endpoints não utilizados após análise detalhada."
        })

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao obter endpoints não utilizados: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter endpoints não utilizados: {str(e)}"
        )


@router.get("/metrics/endpoints/deprecated")
async def get_deprecated_endpoints(
    current_user: User = Depends(require_admin)
):
    """
    🔐 Lista todos os endpoints marcados como deprecated.

    **Requer:** Role ADMIN

    Returns:
        JSON com endpoints deprecated e suas alternativas
    """
    try:
        stats = EndpointUsageTracker.get_usage_stats()

        deprecated = [
            {
                "endpoint": endpoint,
                "alternative": s.get("alternative"),
                "total_calls": s["total_calls"],
                "last_call": s.get("last_call"),
                "avg_response_time_ms": s["avg_response_time_ms"]
            }
            for endpoint, s in stats.items()
            if s.get("deprecated", False)
        ]

        # Ordenar por uso (mais usados primeiro - maior urgência de migração)
        deprecated.sort(key=lambda x: x["total_calls"], reverse=True)

        return JSONResponse(content={
            "success": True,
            "total_deprecated": len(deprecated),
            "deprecated_endpoints": deprecated,
            "migration_urgency": {
                "high": [e for e in deprecated if e["total_calls"] > 100],
                "medium": [e for e in deprecated if 10 < e["total_calls"] <= 100],
                "low": [e for e in deprecated if e["total_calls"] <= 10]
            }
        })

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao obter endpoints deprecated: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter endpoints deprecated: {str(e)}"
        )


@router.get("/metrics/endpoints/performance")
async def get_endpoints_performance(
    top_n: int = Query(20, description="Número de endpoints a retornar", ge=1, le=100),
    current_user: User = Depends(require_admin)
):
    """
    🔐 Performance de endpoints (mais lentos, mais erros).

    **Requer:** Role ADMIN

    Args:
        top_n: Número de endpoints a retornar

    Returns:
        JSON com métricas de performance
    """
    try:
        slowest = get_slowest_endpoints(top_n=top_n)
        stats = EndpointUsageTracker.get_usage_stats()

        # Endpoints com mais erros
        most_errors = sorted(
            [
                {
                    "endpoint": endpoint,
                    "error_count": s["error_count"],
                    "total_calls": s["total_calls"],
                    "error_rate": s["error_count"] / max(s["total_calls"], 1)
                }
                for endpoint, s in stats.items()
                if s["error_count"] > 0
            ],
            key=lambda x: x["error_rate"],
            reverse=True
        )[:top_n]

        return JSONResponse(content={
            "success": True,
            "slowest_endpoints": slowest,
            "endpoints_with_most_errors": most_errors,
            "recommendations": [
                "Endpoints lentos (>1000ms): considere otimização, cache ou índices",
                "Endpoints com erros (>5%): revisar lógica e tratamento de exceções",
                "Endpoints não usados: remover após 30 dias sem chamadas"
            ]
        })

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao obter performance de endpoints: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao obter performance: {str(e)}"
        )


@router.get("/metrics/endpoints/report")
async def export_usage_report(
    format: str = Query("json", description="Formato do relatório (json)"),
    current_user: User = Depends(require_admin)
):
    """
    🔐 Exporta relatório completo de uso de endpoints.

    **Requer:** Role ADMIN

    Args:
        format: Formato do arquivo (json)

    Returns:
        Arquivo para download
    """
    try:
        output_file = f"endpoint_usage_report_{format}"
        report_path = EndpointUsageTracker.export_usage_report(output_file=output_file)

        return FileResponse(
            path=report_path,
            filename=f"watcherdb_endpoint_usage_report.json",
            media_type="application/json"
        )

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao exportar relatório: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao exportar relatório: {str(e)}"
        )


@router.delete("/metrics/endpoints/clear")
async def clear_usage_stats(
    current_user: User = Depends(require_admin)
):
    """
    🔐 Limpa todas as estatísticas de uso (útil para reiniciar tracking).

    **Requer:** Role ADMIN
    **ATENÇÃO:** Esta ação é irreversível!

    Returns:
        JSON com confirmação
    """
    try:
        EndpointUsageTracker.clear_stats()

        return JSONResponse(content={
            "success": True,
            "message": "Estatísticas de uso limpas com sucesso"
        })

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao limpar estatísticas: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao limpar estatísticas: {str(e)}"
        )


@router.get("/health")
async def admin_metrics_health():
    """Health check do router de métricas admin"""
    stats = EndpointUsageTracker.get_usage_stats()

    return JSONResponse(content={
        "status": "healthy",
        "router": "admin-metrics",
        "endpoints_tracked": len(stats),
        "total_api_calls": sum(s["total_calls"] for s in stats.values())
    })
