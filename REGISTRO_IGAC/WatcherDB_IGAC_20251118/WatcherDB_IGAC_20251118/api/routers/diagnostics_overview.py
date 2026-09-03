#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Overview Geral de Diagnósticos
Integra Always On, Queries SQL e outras métricas
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging

from modules.monitoring.watcherdb_alwayson_check import AlwaysOnChecker, get_alwayson_checker
from modules.monitoring.queries import SQLQueries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics Overview"])

@router.get("/overview")
async def get_diagnostics_overview():
    """Obtém overview geral de diagnósticos (Always On + Queries SQL)"""
    try:
        overview = {
            'alwayson': {},
            'queries_available': [],
            'timestamp': None
        }
        
        # Always On Overview
        try:
            checker = get_alwayson_checker()  # Usa singleton
            ao_overview = checker.get_all_ag_overview()
            overview['alwayson'] = {
                'total_ags': ao_overview.get('total_ags', 0),
                'healthy_replicas': ao_overview.get('healthy_replicas', 0),
                'total_replicas': ao_overview.get('total_replicas', 0),
                'healthy_databases': ao_overview.get('healthy_databases', 0),
                'total_databases': ao_overview.get('total_databases', 0),
                'ags_summary': [
                    {
                        'ag_name': ag.get('ag_name', ''),
                        'server': ag.get('server', ''),
                        'recent_events': ag.get('recent_events_count', 0),
                        'critical_events': ag.get('critical_events_count', 0),
                        'has_patterns': len(ag.get('patterns', [])) > 0
                    }
                    for ag in ao_overview.get('ags', [])
                ]
            }
        except Exception as e:
            logger.warning(f"Erro ao obter overview Always On: {e}")
            overview['alwayson'] = {'error': str(e)}
        
        # Lista de queries disponíveis
        overview['queries_available'] = [
            {
                'name': 'blocking',
                'endpoint': '/api/queries/blocking/{server_id}',
                'description': 'Hierarquia de bloqueios e deadlocks'
            },
            {
                'name': 'slow-queries',
                'endpoint': '/api/queries/slow-queries/{server_id}',
                'description': 'Top queries mais lentas com planos de execução'
            },
            {
                'name': 'log-space',
                'endpoint': '/api/queries/log-space/{server_id}',
                'description': 'Monitoramento de crescimento de log de transações'
            },
            {
                'name': 'sql-agent-jobs',
                'endpoint': '/api/queries/sql-agent-jobs/{server_id}',
                'description': 'Jobs SQL Agent falhando'
            },
            {
                'name': 'sessions',
                'endpoint': '/api/queries/sessions/{server_id}',
                'description': 'Sessões problemáticas (CPU, memória, bloqueadas)'
            },
            {
                'name': 'index-fragmentation',
                'endpoint': '/api/queries/index-fragmentation/{server_id}',
                'description': 'Índices fragmentados com recomendações de manutenção'
            },
            {
                'name': 'tempdb',
                'endpoint': '/api/queries/tempdb/{server_id}',
                'description': 'Monitoramento de uso do TempDB'
            },
            {
                'name': 'file-growth',
                'endpoint': '/api/queries/file-growth/{server_id}',
                'description': 'Monitoramento de crescimento automático de arquivos'
            },
            {
                'name': 'statistics',
                'endpoint': '/api/queries/statistics/{server_id}',
                'description': 'Estatísticas desatualizadas'
            },
            {
                'name': 'mirroring',
                'endpoint': '/api/queries/mirroring/{server_id}',
                'description': 'Status de Mirroring/Log Shipping (SQL 2008)'
            }
        ]
        
        from datetime import datetime
        overview['timestamp'] = datetime.now().isoformat()
        
        return JSONResponse(content=overview)
        
    except Exception as e:
        logger.error(f"Erro ao obter overview de diagnósticos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def get_diagnostics_health():
    """Health check dos módulos de diagnóstico"""
    try:
        health = {
            'alwayson_checker': False,
            'queries_module': False,
            'status': 'healthy'
        }
        
        # Verificar Always On Checker
        try:
            checker = get_alwayson_checker()  # Usa singleton
            health['alwayson_checker'] = True
            health['alwayson_servers_loaded'] = len(checker.ag_servers)
        except Exception as e:
            health['alwayson_checker'] = False
            health['alwayson_error'] = str(e)
        
        # Verificar Queries Module
        try:
            from modules.monitoring.queries import SQLQueries
            queries = SQLQueries()
            health['queries_module'] = True
            health['queries_count'] = len([attr for attr in dir(queries) if attr.isupper() and not attr.startswith('_')])
        except Exception as e:
            health['queries_module'] = False
            health['queries_error'] = str(e)
        
        # Status geral
        if not health['alwayson_checker'] or not health['queries_module']:
            health['status'] = 'degraded'
        
        return JSONResponse(content=health)
        
    except Exception as e:
        logger.error(f"Erro no health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

