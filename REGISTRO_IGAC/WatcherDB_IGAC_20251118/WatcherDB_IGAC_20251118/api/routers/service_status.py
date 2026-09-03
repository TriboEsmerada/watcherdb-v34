#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Status de Serviços SQL Server
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
import logging

from modules.monitoring.service_monitor import SQLServiceMonitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring/services", tags=["Service Status"])

@router.get("/server/{server_id}")
async def get_server_services(server_id: str, all_services: bool = Query(False, description="Incluir todos os serviços SQL relacionados")):
    """Obtém status dos serviços SQL Server de um servidor específico"""
    try:
        monitor = SQLServiceMonitor()
        result = monitor.check_server_services(server_id, all_services=all_services)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Erro ao obter serviços de {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/server/{server_id}/logs/{service_name:path}")
async def get_service_logs(server_id: str, service_name: str, hours: int = Query(24, ge=1, le=168, description="Horas para buscar logs")):
    """Obtém logs de eventos do Windows Event Viewer relacionados ao serviço (Service Control Manager)"""
    try:
        from urllib.parse import unquote
        # Decodificar nome do serviço (pode conter $ ou outros caracteres especiais)
        service_name = unquote(service_name)
        monitor = SQLServiceMonitor()
        server, instance = monitor._parse_server_and_instance(server_id)
        
        # Buscar APENAS logs do Event Viewer relacionados ao serviço
        # Não incluir SQL Error Log ou Default Trace - isso é específico para análise de serviços Windows
        event_logs = monitor.get_service_logs(server, service_name, hours=hours, instance=instance)
        
        # Ordenar por data (mais recente primeiro)
        event_logs.sort(key=lambda x: x.get('TimeCreated', ''), reverse=True)
        
        return JSONResponse(content={
            'server_id': server_id,
            'service_name': service_name,
            'hours': hours,
            'logs': event_logs,
            'total_logs': len(event_logs),
            'event_viewer_logs': len(event_logs),
            'sql_error_logs': 0,
            'default_trace_logs': 0
        })
    except Exception as e:
        logger.error(f"Erro ao obter logs de {service_name} em {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/overview")
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
        logger.error(f"Erro ao obter overview de serviços: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

