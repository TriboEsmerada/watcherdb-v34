#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Status de Serviços SQL Server
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict
import logging
import time

from modules.monitoring.service_monitor import SQLServiceMonitor
from api.error_helpers import safe_http_error
from api.models import ServiceStatusResponse, ServiceLogsResponse, ServicesOverviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring/services", tags=["Service Status"])

# ============================================================================
# CACHE DE SERVIÇOS - TTL de 2 minutos (120 segundos)
# Balanceamento entre performance e dados atualizados
# ============================================================================
_SERVICES_CACHE_TTL = 120  # 2 minutos
_SERVICES_CACHE: Dict[str, Dict] = {}


def _get_cached_services(server_id: str) -> Optional[Dict]:
    """Retorna dados do cache se válidos"""
    cache_key = server_id.upper()
    entry = _SERVICES_CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _SERVICES_CACHE_TTL:
        return None
    return entry["data"]


def _set_services_cache(server_id: str, data: Dict) -> None:
    """Salva dados no cache"""
    cache_key = server_id.upper()
    _SERVICES_CACHE[cache_key] = {"ts": time.time(), "data": data}
    
@router.get("/server/{server_id}", response_model=ServiceStatusResponse)
async def get_server_services(
    server_id: str,
    all_services: bool = Query(
        True,
        description=(
            "Incluir todos os serviços SQL relacionados (MSSQL*, SQL*Agent*, "
            "SQL Server*). Mantido como True por padrão para garantir que "
            "serviços críticos como SQL Agent também sejam considerados no "
            "overview e nos cards de saúde."
        ),
    ),
    skip_cache: bool = Query(False, description="Ignorar cache e buscar dados frescos"),
):
    """Obtém status dos serviços SQL Server de um servidor específico

    Utiliza cache de 5 minutos para melhorar performance.
    Use skip_cache=true para forçar atualização.
    """
    try:
        # Verificar cache primeiro (se não for skip_cache)
        if not skip_cache:
            cached = _get_cached_services(server_id)
            if cached:
                logger.debug(f"✅ [Services] Cache HIT para {server_id}")
                cached['from_cache'] = True
                return JSONResponse(content=cached)

        logger.debug(f"📡 [Services] Cache MISS para {server_id}, buscando dados...")
        monitor = SQLServiceMonitor()
        result = monitor.check_server_services(server_id, all_services=all_services)

        # Salvar no cache
        _set_services_cache(server_id, result)
        result['from_cache'] = False

        return JSONResponse(content=result)
    except Exception as e:
        raise safe_http_error(500, e, f"fetching services for {server_id}")

@router.get("/server/{server_id}/logs/{service_name:path}", response_model=ServiceLogsResponse)
async def get_service_logs(server_id: str, service_name: str, hours: int = Query(24, ge=1, le=168, description="Horas para buscar logs")):
    """Obtém logs de eventos relacionados ao serviço SQL Server

    Fontes de dados (em ordem de prioridade):
    1. SQL Server Error Log (xp_readerrorlog) - mais rápido e confiável
    2. Default Trace (eventos Server Stop/Start)
    3. WatcherDB (tabela centralizada, se disponível)
    4. Event Viewer via PowerShell (último recurso)
    """
    try:
        from urllib.parse import unquote
        # Decodificar nome do serviço (pode conter $ ou outros caracteres especiais)
        service_name = unquote(service_name)
        monitor = SQLServiceMonitor()
        server, instance = monitor._parse_server_and_instance(server_id)

        # Buscar logs de múltiplas fontes
        event_logs = monitor.get_service_logs(server, service_name, hours=hours, instance=instance)

        # Ordenar por data (mais recente primeiro)
        event_logs.sort(key=lambda x: x.get('TimeCreated', ''), reverse=True)

        # Contar logs por fonte
        sql_error_count = sum(1 for log in event_logs if log.get('SourceType') == 'SQLErrorLog')
        default_trace_count = sum(1 for log in event_logs if log.get('SourceType') == 'DefaultTrace')
        watcherdb_count = sum(1 for log in event_logs if log.get('SourceType') == 'WatcherDB')
        event_viewer_count = sum(1 for log in event_logs if log.get('SourceType') in ('EventLog', 'WinEvent', None))

        return JSONResponse(content={
            'server_id': server_id,
            'service_name': service_name,
            'hours': hours,
            'logs': event_logs,
            'total_logs': len(event_logs),
            'sql_error_logs': sql_error_count,
            'default_trace_logs': default_trace_count,
            'watcherdb_logs': watcherdb_count,
            'event_viewer_logs': event_viewer_count,
            'sources_used': [
                src for src, count in [
                    ('SQL Error Log', sql_error_count),
                    ('Default Trace', default_trace_count),
                    ('WatcherDB', watcherdb_count),
                    ('Event Viewer', event_viewer_count)
                ] if count > 0
            ]
        })
    except Exception as e:
        raise safe_http_error(500, e, f"fetching service logs for {service_name} on {server_id}")

@router.get("/overview", response_model=ServicesOverviewResponse)
async def get_all_services_overview(server_ids: Optional[str] = Query(None, description="IDs separados por vírgula")):
    """Obtém overview de serviços de múltiplos servidores"""
    try:
        monitor = SQLServiceMonitor()
        
        if server_ids:
            server_list = [s.strip() for s in server_ids.split(',')]
        else:
            # Se não especificado, retornar vazio
            server_list = []
        
        if server_list:
            result = monitor.get_all_servers_services(server_list)
        else:
            result = {
                'total_servers': 0,
                'healthy_servers': 0,
                'servers_with_issues': 0,
                'servers_with_critical_down': 0,
                'servers': {}
            }
        
        return JSONResponse(content=result)
    except Exception as e:
        raise safe_http_error(500, e, "fetching services overview")

