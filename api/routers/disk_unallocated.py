"""
API Router para endpoints de espaco nao alocado em discos fisicos.

Este modulo fornece endpoints para:
- Resumo de espaco nao alocado por servidor
- Detalhes de um servidor especifico
- Oportunidades de expansao de particoes
- Coleta manual de dados
- Historico para analise de tendencias

Autor: WatcherDB
Data: 2026-01-20
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from services.disk_unallocated_service import DiskUnallocatedService
from api.error_helpers import safe_http_error
from api.models import DiskUnallocatedSummaryResponse, DiskUnallocatedServerResponse, GenericResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/disk-unallocated", tags=["Disk Unallocated"])

# Instancia do servico (singleton)
_service: Optional[DiskUnallocatedService] = None


def get_service() -> DiskUnallocatedService:
    """Retorna instancia do servico (lazy initialization)."""
    global _service
    if _service is None:
        _service = DiskUnallocatedService()
    return _service


# =============================================================================
# ENDPOINTS DE CONSULTA
# =============================================================================

@router.get("/summary", response_model=DiskUnallocatedSummaryResponse)
async def get_unallocated_summary():
    """
    Retorna resumo de espaco nao alocado por servidor.

    Returns:
        Lista de servidores com metricas de espaco nao alocado:
        - Servidor: Nome do servidor
        - Ambiente: PRD, QLT, QA, TST, Outros
        - Qtd_Discos: Quantidade de discos fisicos
        - Total_Discos_GB: Capacidade total
        - Total_Nao_Alocado_GB: Espaco nao alocado
        - Percent_Nao_Alocado: Percentual nao alocado
        - Discos_Expandiveis: Discos com espaco para expansao
    """
    try:
        service = get_service()
        data = await service.get_unallocated_summary()

        return JSONResponse(content={
            "success": True,
            "count": len(data),
            "data": data
        })
    except Exception as e:
        logger.error(f"Erro ao obter resumo de espaco nao alocado: {e}")
        raise safe_http_error(500, e, "getting unallocated disk summary")


@router.get("/server/{server_id}", response_model=DiskUnallocatedServerResponse)
async def get_server_unallocated(server_id: str):
    """
    Retorna detalhes de espaco nao alocado de um servidor especifico.

    Args:
        server_id: ID do servidor (formato: HOSTNAME ou HOSTNAME_INSTANCE)

    Returns:
        Detalhes do servidor incluindo:
        - unallocated: Lista de discos com espaco nao alocado
        - partitions: Lista de particoes existentes
        - summary: Resumo consolidado
    """
    try:
        service = get_service()
        data = await service.get_server_detail(server_id)

        if 'error' in data:
            raise HTTPException(status_code=404, detail=data['error'])

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "data": data
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter detalhes de {server_id}: {e}")
        raise safe_http_error(500, e, "getting server unallocated detail")


@router.get("/expansion-opportunities", response_model=GenericResponse)
async def get_expansion_opportunities(
    min_gb: float = Query(default=10.0, ge=0, description="Minimo de GB nao alocado para considerar")
):
    """
    Lista oportunidades de expansao de particoes.

    Retorna discos que possuem espaco nao alocado suficiente para
    expandir particoes existentes.

    Args:
        min_gb: Minimo de GB nao alocado para considerar (default: 10)

    Returns:
        Lista de oportunidades ordenadas por prioridade:
        - Alta: >= 100 GB nao alocado
        - Media: >= 50 GB nao alocado
        - Baixa: >= 10 GB nao alocado
    """
    try:
        service = get_service()
        data = await service.get_expansion_opportunities(min_gb)

        # Agrupa por prioridade para estatisticas
        by_priority = {'Alta': 0, 'Media': 0, 'Baixa': 0, 'Minima': 0}
        total_unallocated = 0
        for item in data:
            priority = item.get('Prioridade_Expansao', 'Minima')
            by_priority[priority] = by_priority.get(priority, 0) + 1
            total_unallocated += item.get('Nao_Alocado_GB', 0) or 0

        return JSONResponse(content={
            "success": True,
            "count": len(data),
            "total_unallocated_gb": round(total_unallocated, 2),
            "by_priority": by_priority,
            "data": data
        })
    except Exception as e:
        logger.error(f"Erro ao obter oportunidades de expansao: {e}")
        raise safe_http_error(500, e, "getting expansion opportunities")


@router.get("/stats", response_model=GenericResponse)
async def get_global_stats():
    """
    Retorna estatisticas globais de espaco nao alocado.

    Returns:
        - global: Estatisticas consolidadas de todos os servidores
        - by_environment: Estatisticas agrupadas por ambiente (PRD, QA, etc.)
    """
    try:
        service = get_service()
        data = await service.get_global_stats()

        if 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])

        return JSONResponse(content={
            "success": True,
            "data": data
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise safe_http_error(500, e, "getting global disk stats")


@router.get("/history/{server_id}", response_model=GenericResponse)
async def get_unallocated_history(
    server_id: str,
    days: int = Query(default=30, ge=1, le=365, description="Numero de dias de historico")
):
    """
    Retorna historico de espaco nao alocado para analise de tendencias.

    Args:
        server_id: ID do servidor
        days: Numero de dias de historico (default: 30, max: 365)

    Returns:
        Lista de registros historicos por dia
    """
    try:
        service = get_service()
        data = await service.get_history(server_id, days)

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "days": days,
            "count": len(data),
            "data": data
        })
    except Exception as e:
        logger.error(f"Erro ao obter historico de {server_id}: {e}")
        raise safe_http_error(500, e, "getting unallocated disk history")


# =============================================================================
# ENDPOINTS DE COLETA
# =============================================================================

@router.post("/collect/{server_id}", response_model=GenericResponse)
async def trigger_collection(
    server_id: str,
    background_tasks: BackgroundTasks,
    save: bool = Query(default=True, description="Salvar dados no banco")
):
    """
    Dispara coleta de espaco nao alocado de um servidor.

    A coleta e feita via WMI/PowerShell remoto e pode levar alguns segundos.

    Args:
        server_id: ID do servidor (hostname ou hostname_instance)
        save: Se True, salva os dados no banco (default: True)

    Returns:
        Dados coletados incluindo:
        - disks: Discos fisicos
        - partitions: Particoes
        - unallocated: Espaco nao alocado calculado
        - summary: Resumo da coleta
    """
    try:
        service = get_service()

        # Executa coleta
        data = await service.collect_from_server(server_id)

        if not data.get('success', False):
            raise HTTPException(
                status_code=500,
                detail=f"Falha na coleta: {data.get('error', 'Erro desconhecido')}"
            )

        # Salva em background se solicitado
        if save:
            background_tasks.add_task(service.save_collection, data)

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "hostname": data.get('hostname'),
            "collection_time": data.get('collection_time'),
            "saved": save,
            "summary": data.get('summary'),
            "disks": data.get('disks', []),
            "partitions": data.get('partitions', []),
            "unallocated": data.get('unallocated', [])
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na coleta de {server_id}: {e}")
        raise safe_http_error(500, e, "collecting disk data from server")


@router.post("/collect-batch", response_model=GenericResponse)
async def trigger_batch_collection(
    server_ids: list[str],
    background_tasks: BackgroundTasks,
    save: bool = Query(default=True, description="Salvar dados no banco")
):
    """
    Dispara coleta de multiplos servidores.

    Args:
        server_ids: Lista de IDs de servidores
        save: Se True, salva os dados no banco

    Returns:
        Resumo da coleta em lote
    """
    try:
        service = get_service()
        results = []
        success_count = 0
        fail_count = 0

        for server_id in server_ids:
            try:
                data = await service.collect_from_server(server_id)
                if data.get('success'):
                    success_count += 1
                    if save:
                        background_tasks.add_task(service.save_collection, data)
                    results.append({
                        'server_id': server_id,
                        'success': True,
                        'summary': data.get('summary')
                    })
                else:
                    fail_count += 1
                    results.append({
                        'server_id': server_id,
                        'success': False,
                        'error': data.get('error')
                    })
            except Exception as e:
                fail_count += 1
                results.append({
                    'server_id': server_id,
                    'success': False,
                    'error': str(e)
                })

        return JSONResponse(content={
            "success": True,
            "total": len(server_ids),
            "success_count": success_count,
            "fail_count": fail_count,
            "saved": save,
            "results": results
        })

    except Exception as e:
        logger.error(f"Erro na coleta em lote: {e}")
        raise safe_http_error(500, e, "running batch disk collection")


# =============================================================================
# ENDPOINTS DE DIAGNOSTICO
# =============================================================================

@router.get("/health", response_model=GenericResponse)
async def health_check():
    """
    Verifica saude do servico de espaco nao alocado.

    Returns:
        Status do servico e ultima coleta
    """
    try:
        service = get_service()
        stats = await service.get_global_stats()

        ultima_coleta = stats.get('global', {}).get('Ultima_Coleta')

        return JSONResponse(content={
            "success": True,
            "service": "disk_unallocated",
            "status": "healthy",
            "last_collection": str(ultima_coleta) if ultima_coleta else None,
            "total_servers": stats.get('global', {}).get('Total_Servidores', 0)
        })
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "service": "disk_unallocated",
                "status": "unhealthy",
                "error": str(e)
            }
        )
