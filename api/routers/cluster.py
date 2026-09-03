#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Windows Failover Cluster
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import logging

from modules.monitoring.cluster_analysis import (
    check_cluster_health,
    get_cluster_events,
    get_cluster_summary
)
from modules.monitoring.cluster_analysis_fast import (
    check_cluster_health_fast,
    get_cluster_summary_fast
)
from api.error_helpers import safe_http_error
from api.models import ClusterHealthResponse, ClusterEventsResponse, ClusterSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cluster", tags=["Cluster"])


@router.get("/server/{server_name}/health", response_model=ClusterHealthResponse)
async def get_cluster_health_endpoint(server_name: str):
    """
    Obtém saúde do Windows Failover Cluster

    Retorna informações sobre:
    - Nodes do cluster e seus estados
    - Recursos do cluster (core, AG, etc.)
    - Recursos com problemas (offline, failed)
    - Configuração de quorum
    """
    try:
        # Remover sufixo de instância se presente
        server = server_name.split('_')[0].split('\\')[0]

        logger.info(f"📡 Verificando cluster health para {server}...")
        health = check_cluster_health(server, timeout=10)

        if not health.get('success'):
            # Retornar erro gracefully (não 500)
            return JSONResponse(
                status_code=200,
                content={
                    'success': False,
                    'cluster_available': False,
                    'error': health.get('error', 'Cluster not available'),
                    'message': f"Não foi possível obter informações do cluster de {server}"
                }
            )

        return JSONResponse(content=health)

    except Exception as e:
        logger.error(f"❌ Erro ao obter cluster health de {server_name}: {e}")
        raise safe_http_error(500, e, "getting cluster health")


@router.get("/server/{server_name}/events", response_model=ClusterEventsResponse)
async def get_cluster_events_endpoint(
    server_name: str,
    hours: int = Query(24, ge=1, le=168, description="Últimas N horas (1-168)")
):
    """
    Obtém eventos recentes do Windows Failover Cluster Event Log

    Parâmetros:
    - hours: Últimas N horas (padrão 24, max 168 = 1 semana)
    """
    try:
        # Remover sufixo de instância se presente
        server = server_name.split('_')[0].split('\\')[0]

        logger.info(f"📡 Buscando cluster events para {server} (últimas {hours}h)...")
        events = get_cluster_events(server, hours=hours, max_events=100)

        if not events.get('success'):
            return JSONResponse(
                status_code=200,
                content={
                    'success': False,
                    'events': [],
                    'error': events.get('error', 'Failed to retrieve events'),
                    'message': f"Não foi possível obter eventos do cluster de {server}"
                }
            )

        return JSONResponse(content=events)

    except Exception as e:
        logger.error(f"❌ Erro ao obter cluster events de {server_name}: {e}")
        raise safe_http_error(500, e, "getting cluster events")


@router.get("/server/{server_name}/summary", response_model=ClusterSummaryResponse)
async def get_cluster_summary_endpoint(
    server_name: str,
    mode: str = Query('fast', description="Mode: 'fast' (apenas AG) ou 'full' (completo)")
):
    """
    Obtém resumo do cluster

    Modes:
    - fast: Apenas cluster name e AG resources (~2-3s) - RECOMENDADO
    - full: Dados completos (nodes, recursos, quorum, events) (~10-15s)
    """
    import time
    start_time = time.time()

    try:
        # Remover sufixo de instância se presente
        server = server_name.split('_')[0].split('\\')[0]

        logger.info(f"📡 [CLUSTER {mode.upper()}] Iniciando get_cluster_summary para {server} (raw: {server_name})")

        # Usar modo rápido por padrão
        if mode == 'fast':
            summary = get_cluster_summary_fast(server)
        else:
            summary = get_cluster_summary(server)

        elapsed = time.time() - start_time
        logger.info(f"✅ [CLUSTER {mode.upper()}] Summary obtido em {elapsed:.2f}s - Success: {summary.get('health', {}).get('success', False)}")

        return JSONResponse(content=summary)

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ [CLUSTER] Erro ao obter cluster summary de {server_name} após {elapsed:.2f}s: {e}", exc_info=True)
        raise safe_http_error(500, e, "getting cluster summary")
