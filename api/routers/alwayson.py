#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Always On Availability Groups
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging
import json
import re as _re
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from modules.monitoring.watcherdb_alwayson_check import (
    AlwaysOnChecker,
    get_alwayson_overview,
    get_alwayson_status,
    get_alwayson_checker  # Singleton — kept for non-DI endpoints during migration
)
from api.dependencies import get_checker
from api.error_helpers import safe_http_error
from api.models import AlwaysOnOverviewResponse, GenericResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alwayson", tags=["Always On"])

@router.get("/overview", response_model=AlwaysOnOverviewResponse)
async def get_alwayson_overview_endpoint(
    lazy: bool = Query(True, description="Se True, retorna apenas dados do JSON (RÁPIDO). Se False, conecta em todos os servidores (LENTO)"),
    checker: AlwaysOnChecker = Depends(get_checker),
):
    """
    Obtém overview de todos os Availability Groups

    - lazy=True (padrão): Retorna lista de AGs do inventory sem conectar (RÁPIDO - 0 conexões)
    - lazy=False: Conecta em todos os 42 servidores para buscar status completo (LENTO - 84 conexões)
    """
    try:
        overview = checker.get_all_ag_overview(lazy=lazy)
        return JSONResponse(content=overview)
    except Exception as e:
        logger.error(f"Erro ao obter overview Always On: {e}")
        raise safe_http_error(500, e, "loading AlwaysOn overview")

@router.get("/ag/{ag_name}", response_model=GenericResponse)
async def get_ag_detail(ag_name: str, checker: AlwaysOnChecker = Depends(get_checker)):
    """Obtém detalhes de um AG específico"""
    try:
        
        # Procurar o AG nos servidores
        for ag_server in checker.ag_servers:
            if ag_server.get('ag_name') == ag_name:
                server = ag_server['server']
                instance = ag_server.get('instance', '')
                
                status = await asyncio.to_thread(checker.get_ag_status, server, instance)
                if status:
                    # Adicionar eventos e padrões
                    events = checker.get_ag_failover_events(server, instance, days=30)
                    patterns = checker.analyze_failover_patterns(events)
                    
                    return JSONResponse(content={
                        'ag_name': ag_name,
                        'server': server,
                        'instance': instance,
                        'listener': ag_server.get('listener', ''),
                        'status': status,
                        'events': [
                            {
                                'timestamp': e.timestamp.isoformat(),
                                'event_type': e.event_type,
                                'source_server': e.source_server,
                                'description': e.description,
                                'severity': e.severity
                            } for e in events
                        ],
                        'patterns': [
                            {
                                'pattern_type': p.pattern_type,
                                'frequency': p.frequency,
                                'common_hour': p.common_hour,
                                'common_day_of_week': p.common_day_of_week,
                                'likely_cause': p.likely_cause,
                                'confidence': p.confidence
                            } for p in patterns
                        ]
                    })
        
        raise HTTPException(status_code=404, detail=f"AG '{ag_name}' não encontrado")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter detalhes do AG {ag_name}: {e}")
        raise safe_http_error(500, e, "getting AG detail")

def _parse_server_and_instance(server_identifier: str, instance_param: Optional[str]) -> (str, str):
    """Aceita formatos SERVER, SERVER\\INSTANCE, SERVER_INSTANCE e retorna (server, instance)."""
    # Se instance_param foi fornecido explicitamente, parsear server_identifier primeiro
    # para remover instância duplicada (ex: "SQLHDSPRD023_I01" com instance="I01")
    if instance_param:
        # Verificar se server_identifier já contém a instância
        if '\\' in server_identifier:
            srv, inst = server_identifier.split('\\', 1)
            # Se inst == instance_param, usar só server (evita duplicação)
            if inst.upper() == instance_param.upper():
                return srv, instance_param
            # Se diferentes, priorizar instance_param
            return srv, instance_param
        elif '_' in server_identifier and not server_identifier.endswith('_DEFAULT'):
            parts = server_identifier.rsplit('_', 1)
            if len(parts) == 2 and parts[1]:
                # Se parte final == instance_param, usar só server (evita duplicação)
                if parts[1].upper() == instance_param.upper():
                    return parts[0], instance_param
        # server_identifier não contém instância, retornar como está
        return server_identifier, instance_param

    # Sem instance_param, parsear server_identifier
    # SERVER\INSTANCE
    if '\\' in server_identifier:
        srv, inst = server_identifier.split('\\', 1)
        return srv, inst
    # SERVER_INSTANCE (usar último underscore como separador para suportar nomes com _)
    if '_' in server_identifier and not server_identifier.endswith('_DEFAULT'):
        parts = server_identifier.rsplit('_', 1)
        if len(parts) == 2 and parts[1]:
            return parts[0], parts[1]
    # Somente servidor
    return server_identifier.replace('_DEFAULT', ''), ""


@router.get("/server/{server_name}", response_model=GenericResponse)
async def get_server_ag_status(
    server_name: str,
    instance: Optional[str] = Query(None, description="Nome da instância SQL")
):
    """
    Obtém status do Always On de um servidor específico

    Retorna dados cached se disponível (<50ms) ou tenta conectar (até 45s).
    Se timeout, retorna erro gracefully para o usuário tentar depois.
    """
    try:
        checker = get_alwayson_checker()  # Usa singleton
        srv, inst = _parse_server_and_instance(server_name, instance)

        logger.info(f"Requisição AlwaysOn para {srv}\\{inst}")

        status = await asyncio.to_thread(checker.get_ag_status, srv, inst)

        if not status:
            # PyArmor BCC compatibility: extract conditional expression with backslash
            # out of f-string expression part (Python 3.11 PEP 701 limitation).
            inst_suffix = ('\\' + inst) if inst else ''
            raise HTTPException(
                status_code=404,
                detail=f"Always On não encontrado em {srv}{inst_suffix}"
            )

        # Verificar se houve timeout
        if status.get('timeout') or status.get('success') == False:
            error_msg = status.get('error', 'Erro desconhecido')
            logger.warning(f"Status AlwaysOn com erro para {srv}: {error_msg}")

            # Retornar resposta graceful (não levanta HTTPException)
            return JSONResponse(
                status_code=200,  # 200 OK, mas com erro no payload
                content={
                    'server': srv,
                    'instance': inst or None,
                    'status': 'ERROR',
                    'error': error_msg,
                    'timeout': status.get('timeout', False),
                    'message': (
                        f"Servidor {srv} demorou muito para responder. "
                        f"Os dados estão em cache por 5 minutos. "
                        f"Tente novamente mais tarde ou verifique a conectividade."
                    ),
                    'cached': True
                }
            )

        # Status OK - adicionar eventos recentes (com timeout de 15s)
        events = []
        patterns = []
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(checker.get_ag_failover_events, srv, inst, 7)
                events = future.result(timeout=15)
                patterns = checker.analyze_failover_patterns(events)
        except FuturesTimeoutError:
            logger.warning(f"Timeout (15s) ao obter eventos de {srv} — continuando sem eventos")
        except Exception as e:
            logger.warning(f"Erro ao obter eventos/padrões de {srv}: {e}")

        return JSONResponse(content={
            'server': srv,
            'instance': inst or None,
            'status': status,
            'recent_events': [
                {
                    'timestamp': e.timestamp.isoformat(),
                    'event_type': e.event_type,
                    'description': e.description,
                    'severity': e.severity
                } for e in events
            ],
            'patterns': [
                {
                    'pattern_type': p.pattern_type,
                    'frequency': p.frequency,
                    'common_hour': p.common_hour,
                    'likely_cause': p.likely_cause,
                    'confidence': p.confidence
                } for p in patterns
            ]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status Always On de {server_name}: {e}")
        raise safe_http_error(500, e, "getting AlwaysOn server status")

@router.get("/server/{server_id}/overview", response_model=GenericResponse)
async def get_server_ag_overview(server_id: str):
    """
    Obtém informações resumidas de Always On para o overview.
    Retorna None se não for Always On.

    Dados sempre em tempo real (sem cache).
    """
    try:
        logger.debug(f"📡 [AlwaysOn] Buscando dados em tempo real para {server_id}...")
        checker = get_alwayson_checker()  # Usa singleton

        # Primeiro, verificar se o servidor está na lista de Always On do inventory
        # Isso é mais rápido e confiável do que tentar conectar diretamente
        server_found_in_inventory = False
        ag_name_from_inventory = None
        listener_from_inventory = None

        # Normalizar server_id para comparação (remover backslash, converter para uppercase)
        server_id_normalized = server_id.replace('\\', '_').upper().strip()
        logger.info(f"🔍 Verificando Always On para server_id: {server_id} (normalizado: {server_id_normalized})")
        logger.debug(f"📋 Inventory tem {len(checker.ag_servers)} servidores Always On")
        
        for ag_server in checker.ag_servers:
            # Verificar diferentes formatos de server_id
            server_instance_raw = ag_server.get('server_instance', '')
            server_instance = server_instance_raw.replace('\\', '_').upper().strip()
            server_name = ag_server.get('server', '').upper().strip()
            instance_name = ag_server.get('instance', '').upper().strip()
            ag_name = ag_server.get('ag_name', '')
            listener = ag_server.get('listener', '')
            
            # Construir diferentes variações para comparação
            # Ex: SQLMDMPRD02_I01 pode vir como:
            # - SQLMDMPRD02\I01 (server_instance)
            # - SQLMDMPRD02_I01 (server_id)
            # - SQLMDMPRD02 + I01 (server + instance)
            
            # Comparação exata
            if server_id_normalized == server_instance:
                server_found_in_inventory = True
                ag_name_from_inventory = ag_name
                listener_from_inventory = listener
                logger.info(f"✅ Servidor {server_id} encontrado no inventory Always On (AG: {ag_name}, Listener: {listener}) - match exato")
                break
            
            # Comparação por server + instance
            if server_name and instance_name:
                server_instance_constructed = f"{server_name}_{instance_name}"
                if server_id_normalized == server_instance_constructed:
                    server_found_in_inventory = True
                    ag_name_from_inventory = ag_name
                    listener_from_inventory = listener
                    logger.info(f"✅ Servidor {server_id} encontrado no inventory Always On (AG: {ag_name}, Listener: {listener}) - match por server+instance")
                    break
            
            # Comparação parcial (server_id começa com server name)
            if server_name and server_id_normalized.startswith(server_name):
                # Verificar se a instance também corresponde
                server_id_parts = server_id_normalized.split('_')
                if len(server_id_parts) > 1:
                    server_id_instance = server_id_parts[-1]
                    if instance_name and (server_id_instance == instance_name or instance_name in server_id_instance or server_id_instance in instance_name):
                        server_found_in_inventory = True
                        ag_name_from_inventory = ag_name
                        listener_from_inventory = listener
                        logger.info(f"✅ Servidor {server_id} encontrado no inventory Always On (AG: {ag_name}, Listener: {listener}) - match parcial")
                        break
        
        # Se não encontrou no inventory, ainda pode ser Always On (mas não está no JSON)
        # Tentar conectar diretamente
        if not server_found_in_inventory:
            logger.debug(f"⚠️ Servidor {server_id} não encontrado no inventory, tentando conexão direta...")
        
        # Converter server_id para server e instance
        if '_' in server_id:
            parts = server_id.rsplit('_', 1)
            server = parts[0]
            instance = parts[1] if len(parts) > 1 else ''
        else:
            server = server_id
            instance = ''
        
        status = await asyncio.to_thread(checker.get_ag_status, server, instance)

        logger.debug(f"get_ag_status retornou para {server_id}: {status is not None}, tipo: {type(status)}")
        if status:
            logger.debug(f"Status contém: ag_name={status.get('ag_name')}, replicas={len(status.get('replicas', []))}, databases={len(status.get('databases', []))}")

        # Verificar se houve timeout ou erro na consulta
        if status and (status.get('timeout') or status.get('success') == False):
            error_msg = status.get('error', 'Erro ao obter status')
            is_timeout = status.get('timeout', False)
            logger.warning(f"⚠️ Timeout/erro ao obter status AG de {server_id}: {error_msg}")

            # Retornar resposta graciosa com informações do inventory se disponível
            return JSONResponse(content={
                'is_alwayson': True if server_found_in_inventory else False,
                'ag_name': ag_name_from_inventory or 'Unknown',
                'listener': listener_from_inventory,
                'role': 'UNKNOWN',
                'is_primary': False,
                'replicas': {'total': 0, 'healthy': 0},
                'databases': {'total': 0, 'healthy': 0},
                'synchronization_health': 'UNKNOWN',
                'availability_mode': 'UNKNOWN',
                'failover_mode': 'UNKNOWN',
                'timeout': is_timeout,
                'error': error_msg,
                'warning': f"{'Timeout: ' if is_timeout else ''}O servidor não respondeu a tempo. Os dados podem estar em cache. Tente novamente em alguns instantes."
            })

        if not status:
            # Se encontrou no inventory mas não conseguiu conectar, ainda retornar como Always On
            if server_found_in_inventory:
                logger.warning(f"⚠️ Servidor {server_id} está no inventory Always On mas não foi possível conectar. Retornando como Always On baseado no inventory.")
                return JSONResponse(content={
                    'is_alwayson': True,
                    'ag_name': ag_name_from_inventory or 'Unknown',
                    'listener': listener_from_inventory,
                    'role': 'UNKNOWN',
                    'is_primary': False,
                    'replicas': {'total': 0, 'healthy': 0},
                    'databases': {'total': 0, 'healthy': 0},
                    'synchronization_health': 'UNKNOWN',
                    'availability_mode': 'UNKNOWN',
                    'failover_mode': 'UNKNOWN',
                    'warning': 'Servidor encontrado no inventory mas não foi possível conectar para obter status detalhado'
                })
            
            # Não é Always On
            return JSONResponse(content={
                'is_alwayson': False,
                'message': 'Este servidor não está configurado como Always On'
            })
        
        # É Always On - retornar informações resumidas
        ag_name = status.get('ag_name', 'Unknown')
        replicas = status.get('replicas', [])
        
        # Réplicas já vêm como dict do get_ag_status (usando asdict)
        # Encontrar a réplica atual pelo server_name
        current_replica = None
        is_primary = False
        
        # Normalizar nome do servidor para comparação
        server_normalized = server.replace('\\', '_').lower()
        if instance:
            server_with_instance = f"{server}_{instance}".lower()
        else:
            server_with_instance = server_normalized
        
        for replica in replicas:
            replica_name = str(replica.get('server_name', '')).replace('\\', '_').lower()
            replica_role = replica.get('role', '')
            
            # Tentar encontrar pela correspondência do nome
            # Comparar server_normalized com replica_name
            if (server_normalized in replica_name or 
                replica_name in server_normalized or
                server_with_instance in replica_name or
                replica_name in server_with_instance):
                current_replica = replica
                is_primary = replica_role == 'PRIMARY'
                break
        
        # Se não encontrou, verificar se alguma réplica é local (is_local=True)
        if not current_replica:
            for replica in replicas:
                if replica.get('is_local', False):
                    current_replica = replica
                    is_primary = replica.get('role') == 'PRIMARY'
                    break
        
        # Se ainda não encontrou, verificar se alguma réplica tem is_current_primary=True
        if not current_replica:
            for replica in replicas:
                if replica.get('is_current_primary', False):
                    current_replica = replica
                    is_primary = True
                    break
        
        # Se ainda não encontrou, usar a primeira réplica PRIMARY
        if not current_replica:
            for replica in replicas:
                if replica.get('role') == 'PRIMARY':
                    current_replica = replica
                    is_primary = True
                    break
        
        # Se ainda não encontrou, usar a primeira réplica
        if not current_replica and replicas:
            current_replica = replicas[0]
            is_primary = current_replica.get('role') == 'PRIMARY'
        
        # Contar réplicas saudáveis
        healthy_replicas = sum(1 for r in replicas if r.get('synchronization_health') == 'HEALTHY')
        total_replicas = len(replicas)

        # Contar databases (já vêm como dict do get_ag_status)
        databases = status.get('databases', [])
        # A query de origem faz JOIN base x replica (watcherdb_alwayson_check.py:
        # 550-559), logo devolve UMA LINHA POR (base, replica) -- num AG de 2 nos
        # com 32 bases sao 64 linhas. Contar linhas mostrava "Bases: 64" ao
        # utilizador (QA externo 5o passe, 2026-08-17: marcado "baixa confianca",
        # confirmado em codigo). Contamos bases DISTINTAS.
        #
        # Semantica conservadora para os agregados: uma base so' conta como
        # sincronizada/saudavel se TODAS as suas replicas o estiverem -- dizer
        # "sincronizada" quando uma replica nao esta seria a mesma familia de
        # mentira otimista que este passe veio caçar.
        _by_db = {}
        for db in databases:
            _by_db.setdefault(db.get('database_name'), []).append(db)
        total_databases = len(_by_db)
        synchronized_databases = sum(
            1 for rows in _by_db.values()
            if rows and all(r.get('synchronization_state') == 'SYNCHRONIZED' for r in rows)
        )
        healthy_databases_count = sum(
            1 for rows in _by_db.values()
            if rows and all(r.get('synchronization_health') == 'HEALTHY' for r in rows)
        )

        # Para manter compatibilidade, usar synchronized_databases como healthy_databases
        healthy_databases = synchronized_databases
        
        # Retornar estrutura completa incluindo arrays de réplicas e databases
        # Isso permite que o frontend exiba as tabelas detalhadas
        # Usar listener do banco se disponível, senão usar do inventory
        listener_name = status.get('listener', None) or listener_from_inventory

        # Determinar synchronization_health do AG de forma mais precisa:
        # - Se TODAS as databases estão HEALTHY → AG HEALTHY
        # - Se réplica está NOT_HEALTHY mas databases estão OK → PARTIALLY_HEALTHY
        # - Se réplica está NOT_HEALTHY e databases também → NOT_HEALTHY
        replica_health = current_replica.get('synchronization_health', 'UNKNOWN') if current_replica else 'UNKNOWN'

        if total_databases > 0:
            # Calcular baseado nas databases (mais preciso)
            if healthy_databases_count == total_databases:
                # Todas databases HEALTHY
                overall_health = 'HEALTHY'
            elif healthy_databases_count > 0:
                # Algumas databases HEALTHY
                overall_health = 'PARTIALLY_HEALTHY'
            else:
                # Nenhuma database HEALTHY
                overall_health = 'NOT_HEALTHY'
        else:
            # Sem databases, usar health da réplica
            overall_health = replica_health

        # Log para debug
        logger.debug(f"AG Health calculation: replica_health={replica_health}, "
                    f"healthy_dbs={healthy_databases_count}/{total_databases}, overall={overall_health}")

        # Obter current_primary do status
        current_primary_name = status.get('current_primary')

        response_data = {
            'is_alwayson': True,
            'ag_name': ag_name,
            'listener': listener_name,
            'role': 'PRIMARY' if is_primary else 'SECONDARY',
            'is_primary': is_primary,
            'current_primary': current_primary_name,  # Adicionar no nível principal
            'replicas': {
                'total': total_replicas,
                'healthy': healthy_replicas
            },
            'databases': {
                'total': total_databases,
                'healthy': healthy_databases
            },
            # Usar overall_health calculado (baseado nas databases) em vez de apenas replica_health
            'synchronization_health': overall_health,
            # Manter replica_health separado para referência
            'replica_health': replica_health,
            'availability_mode': current_replica.get('availability_mode', 'UNKNOWN') if current_replica else 'UNKNOWN',
            'failover_mode': current_replica.get('failover_mode', 'UNKNOWN') if current_replica else 'UNKNOWN',
            # Incluir arrays completos para o frontend exibir tabelas detalhadas
            'status': {
                'ag_name': ag_name,
                'listener': listener_name,
                'replicas': replicas,  # Array completo de réplicas
                'databases': databases,  # Array completo de databases
                'current_primary': status.get('current_primary'),
                'total_replicas': total_replicas,
                'healthy_replicas': healthy_replicas,
                'total_databases': total_databases,
                'healthy_databases': healthy_databases,
                'synchronized_databases': status.get('synchronized_databases', 0)
            }
        }
        
        logger.info(f"Retornando overview para {server_id}: {len(replicas)} réplicas, {len(databases)} databases no campo status")
        logger.debug(f"Estrutura completa: status.replicas={len(response_data['status']['replicas'])}, status.databases={len(response_data['status']['databases'])}")

        # Validar que o campo status está presente antes de retornar
        if 'status' not in response_data:
            logger.error(f"ERRO: Campo 'status' não encontrado em response_data para {server_id}!")
        else:
            logger.info(f"✅ Campo 'status' presente com {len(response_data['status'].get('replicas', []))} réplicas e {len(response_data['status'].get('databases', []))} databases")

        return JSONResponse(content=response_data)
        
    except Exception as e:
        logger.error(f"Erro ao obter overview Always On de {server_id}: {e}")
        # Retornar como não Always On em caso de erro
        return JSONResponse(content={
            'is_alwayson': False,
            'error': str(e)
        })

@router.get("/events/{server_name}", response_model=GenericResponse)
async def get_ag_events(
    server_name: str,
    instance: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=90, description="Número de dias para buscar eventos")
):
    """Obtém eventos de failover de um servidor"""
    try:
        checker = get_alwayson_checker()  # Usa singleton
        srv, inst = _parse_server_and_instance(server_name, instance)

        # Obter eventos com timeout de 15s via ThreadPoolExecutor
        # (xp_readerrorlog pode bloquear em servidores com logs grandes)
        events = []
        patterns = []
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(checker.get_ag_failover_events, srv, inst, days)
                events = future.result(timeout=15)
                patterns = checker.analyze_failover_patterns(events)
        except FuturesTimeoutError:
            logger.warning(f"Timeout (15s) ao obter eventos de {srv} — retornando lista vazia")
        except Exception as events_err:
            logger.warning(f"Erro ao obter eventos de {srv}: {events_err}")

        # Obter data do ultimo failover (sem limite de dias)
        # Protegido com timeout de 10s para nao bloquear o carregamento do tab
        last_failover_date = None
        if events:
            # Se ha eventos, o mais recente ROLE_CHANGE e o ultimo failover
            role_changes = [e for e in events if e.event_type == 'ROLE_CHANGE']
            if role_changes:
                last_failover_date = role_changes[0].timestamp.isoformat()
            else:
                last_failover_date = events[0].timestamp.isoformat()
        else:
            # Sem eventos nos ultimos N dias - buscar no historico com timeout de 5s
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(checker.get_last_failover_date, srv, inst)
                    last_failover_date = future.result(timeout=5)
            except (FuturesTimeoutError, Exception):
                last_failover_date = None

        return JSONResponse(content={
            'server': srv,
            'instance': inst or None,
            'days': days,
            'total_events': len(events),
            'last_failover_date': last_failover_date,
            'events': [
                {
                    'timestamp': e.timestamp.isoformat(),
                    'event_type': e.event_type,
                    'source_server': e.source_server,
                    'description': e.description,
                    'severity': e.severity
                } for e in events
            ],
            'patterns': [
                {
                    'pattern_type': p.pattern_type,
                    'frequency': p.frequency,
                    'common_hour': p.common_hour,
                    'common_day_of_week': p.common_day_of_week,
                    'likely_cause': p.likely_cause,
                    'confidence': p.confidence
                } for p in patterns
            ]
        })
        
    except Exception as e:
        logger.error(f"Erro ao obter eventos Always On de {server_name}: {e}")
        raise safe_http_error(500, e, "getting AlwaysOn failover events")


@router.get("/diagnose/{server_name}", response_model=GenericResponse)
async def diagnose_ag(
    server_name: str,
    instance: Optional[str] = Query(None)
):
    """
    Executa diagnóstico de problemas do Always On e identifica causa raiz.

    Funciona tanto no primário quanto no secundário.
    Retorna:
    - Causa raiz provável
    - Status do endpoint de mirroring
    - Estado de todas as réplicas
    - Erros recentes do SQL Error Log
    - Recomendações de ação
    """
    try:
        checker = get_alwayson_checker()
        srv, inst = _parse_server_and_instance(server_name, instance)

        logger.info(f"🔍 [AG Diagnose] Iniciando diagnóstico para {srv}\\{inst or 'DEFAULT'}")

        import time
        start_time = time.time()
        diagnosis = checker.diagnose_ag_issues(srv, inst)
        elapsed = time.time() - start_time

        logger.info(f"✅ [AG Diagnose] Diagnóstico concluído em {elapsed:.2f}s - "
                   f"root_cause={diagnosis.get('root_cause_category', 'N/A')}, "
                   f"severity={diagnosis.get('severity', 'N/A')}, "
                   f"logs={len(diagnosis.get('error_log_entries', []))}")

        return JSONResponse(content=diagnosis)

    except Exception as e:
        logger.error(f"Erro ao diagnosticar Always On de {server_name}: {e}")
        return JSONResponse(content={
            'server': server_name,
            'error': str(e),
            'root_cause': f'Erro durante diagnóstico: {str(e)}',
            'root_cause_category': 'DIAGNOSTIC_ERROR',
            'severity': 'ERROR',
            'recommendations': [{
                'action': 'Verificar conectividade com o servidor',
                'priority': 'HIGH',
                'type': 'CHECK'
            }]
        })


@router.get("/instance-by-ag/{ag_name}", response_model=GenericResponse)
async def get_instance_by_ag_name(ag_name: str):
    """
    Busca a instância correta no inventory baseado no nome do Availability Group.
    Retorna o servidor e instância que devem ser usados para conectar.
    Primeiro tenta buscar no alwayson_inventory, depois no sql_servers.json.
    """
    try:
        # Limpar e normalizar o nome do AG
        # Se vier no formato SERVER\INSTANCE, extrair apenas o SERVER para buscar o AG
        ag_name_clean = ag_name.strip().upper()
        
        # Se contém backslash, pode ser que esteja passando SERVER\INSTANCE em vez do nome do AG
        # Tentar extrair o servidor e buscar o AG correspondente
        if '\\' in ag_name_clean:
            # Formato: SQLRPAPRD01\I01 -> tentar buscar AG que contenha SQLRPAPRD
            parts = ag_name_clean.split('\\', 1)
            server_part = parts[0]
            # Remover números do final para obter a base (ex: SQLRPAPRD01 -> SQLRPAPRD)
            import re
            base_match = re.match(r'^([A-Z]+)', server_part)
            if base_match:
                ag_base = base_match.group(1)
                logger.debug(f"🔍 Extraído base '{ag_base}' de '{server_part}'")
            else:
                ag_base = server_part
            ag_name_upper = ag_name_clean
        else:
            ag_name_upper = ag_name_clean
            ag_base = ag_name_upper.replace('AG', '').strip()
        
        logger.info(f"🔍 Buscando instância para AG: '{ag_name}' (normalizado: '{ag_name_upper}', base: '{ag_base}')")
        
        # 1. Tentar buscar no alwayson_inventory primeiro
        try:
            checker = get_alwayson_checker()  # Usa singleton
            
            # Procurar o AG no inventory
            logger.info(f"🔍 Buscando AG '{ag_name}' no alwayson_inventory ({len(checker.ag_servers)} servidores carregados)")
            for ag_server in checker.ag_servers:
                ag_name_in_inventory = ag_server.get('ag_name', '').upper()
                logger.debug(f"  Comparando: '{ag_name_upper}' com '{ag_name_in_inventory}'")
                if ag_name_in_inventory == ag_name_upper:
                    # Priorizar server_instance do Excel se disponível (formato: SQLMDMPRD01\101)
                    server_instance = ag_server.get('server_instance', '')
                    if server_instance:
                        # ServerInstance já vem no formato correto do Excel
                        if '\\' in server_instance:
                            parts = server_instance.split('\\', 1)
                            server = parts[0].strip()
                            instance = parts[1].strip() if len(parts) > 1 else ''
                            server_id = f"{server}_{instance}"
                        elif '_' in server_instance:
                            # Formato alternativo: SQLMDMPRD01_101
                            parts = server_instance.rsplit('_', 1)
                            server = parts[0].strip()
                            instance = parts[1].strip() if len(parts) > 1 else ''
                            server_id = server_instance  # Já está no formato correto
                        else:
                            server = server_instance
                            instance = ''
                            server_id = server
                    else:
                        # Fallback: usar server e instance separados
                        server = ag_server.get('server', '')
                        instance = ag_server.get('instance', '')
                        if instance:
                            server_id = f"{server}_{instance}"
                        else:
                            server_id = server
                    
                    logger.info(f"✅ AG '{ag_name}' encontrado no inventory: {server_id} (ServerInstance: {server_instance or 'N/A'})")
                    return JSONResponse(content={
                        'success': True,
                        'ag_name': ag_name,
                        'server': server,
                        'instance': instance,
                        'server_id': server_id,
                        'listener': ag_server.get('listener', ''),
                        'source': 'alwayson_inventory',
                        'server_instance': server_instance
                    })
        except Exception as e:
            logger.warning(f"Erro ao buscar no alwayson_inventory: {e}")
        
        # 2. Se não encontrou no inventory, buscar no sql_servers.json
        try:
            sql_servers_path = Path("config/sql_servers.json")
            if sql_servers_path.exists():
                with open(sql_servers_path, 'r', encoding='utf-8') as f:
                    sql_servers_config = json.load(f)
                
                servers = sql_servers_config.get('servers', [])
                
                # Preparar variações do AG name para busca mais flexível
                # Exemplo: "SQLMDMPRDAG" -> ["SQLMDMPRDAG", "SQLMDMPRD", "MDMPRDAG", "MDMPRD"]
                ag_variations = [
                    ag_name_upper,  # Nome completo: SQLMDMPRDAG
                    ag_name_upper.replace('AG', '').strip(),  # Sem sufixo AG: SQLMDMPRD
                    ag_name_upper.replace('SQL', '').strip(),  # Sem prefixo SQL: MDMPRDAG
                    ag_name_upper.replace('SQL', '').replace('AG', '').strip(),  # Sem prefixo e sufixo: MDMPRD
                ]
                
                # Se ag_base não foi definido ainda, extrair do nome do AG
                if 'ag_base' not in locals() or not ag_base:
                    ag_base = ag_name_upper.replace('AG', '').strip()
                
                logger.info(f"🔍 Buscando AG '{ag_name}' no sql_servers.json (base: '{ag_base}')")
                logger.debug(f"📋 Total de servidores no sql_servers.json: {len(servers)}")
                
                # Estratégia 1: Se o ag_name contém backslash, tentar match direto por server_id
                if '\\' in ag_name_upper:
                    server_instance_normalized = ag_name_upper.replace('\\', '_')
                    logger.debug(f"🔍 Tentando match direto por server_id normalizado: '{server_instance_normalized}'")
                    for server_config in servers:
                        server_id_raw = server_config.get('server_id', '') or server_config.get('id', '')
                        if server_id_raw and server_id_raw.upper() == server_instance_normalized:
                            host = server_config.get('host', '')
                            instance = server_config.get('instance', '')
                            logger.info(f"✅ AG '{ag_name}' encontrado no sql_servers.json (match direto): {server_id_raw}")
                            return JSONResponse(content={
                                'success': True,
                                'ag_name': ag_name,
                                'server': host or server_id_raw.split('_')[0],
                                'instance': instance or (server_id_raw.split('_')[1] if '_' in server_id_raw else ''),
                                'server_id': server_id_raw,
                                'source': 'sql_servers.json',
                                'match_type': 'direct_match'
                            })
                
                # Estratégia 2: Busca por base (mais eficiente para nomes de AG)
                # Para "SQLMDMPRDAG" -> base "SQLMDMPRD" -> encontrar "SQLMDMPRD01", "SQLMDMPRD02", etc.
                if ag_base and len(ag_base) >= 6:
                    logger.debug(f"🔍 Buscando servidores que começam com '{ag_base}'...")
                    matches = []
                    for server_config in servers:
                        host_raw = server_config.get('host', '')
                        server_id_raw = server_config.get('server_id', '') or server_config.get('id', '')
                        instance = server_config.get('instance', '')
                        
                        host_upper = (host_raw or '').upper()
                        server_id_upper = (server_id_raw or '').upper()
                        
                        # Verificar se host ou server_id começa com a base
                        host_match = host_upper and host_upper.startswith(ag_base)
                        server_id_match = server_id_upper and server_id_upper.startswith(ag_base)
                        
                        if host_match or server_id_match:
                            final_host = server_config.get('host', '')
                            if instance:
                                final_server_id = f"{final_host}_{instance}"
                            else:
                                final_server_id = final_host
                            
                            matches.append({
                                'host': final_host,
                                'instance': instance,
                                'server_id': final_server_id,
                                'match_type': 'host' if host_match else 'server_id'
                            })
                            
                            logger.info(f"  ✅ Match encontrado: {final_server_id} (host: {host_raw}, server_id: {server_id_raw})")
                    
                    # Se encontrou matches, retornar o primeiro (ou podemos retornar uma lista)
                    if matches:
                        match = matches[0]
                        logger.info(f"✅ AG '{ag_name}' encontrado no sql_servers.json (base match '{ag_base}'): {match['server_id']} (total: {len(matches)} matches)")
                        return JSONResponse(content={
                            'success': True,
                            'ag_name': ag_name,
                            'server': match['host'],
                            'instance': match['instance'],
                            'server_id': match['server_id'],
                            'source': 'sql_servers.json',
                            'match_type': 'base_match',
                            'total_matches': len(matches)
                        })
                    else:
                        logger.debug(f"⚠️ Nenhum servidor encontrado que comece com '{ag_base}' (continuando busca...)")
                
                # Se não encontrou por base, tentar busca mais ampla
                # Buscar servidor que tenha o AG name em qualquer campo relevante
                for server_config in servers:
                    # Tentar múltiplos campos possíveis (id, server_id, name)
                    server_id_raw = server_config.get('server_id', '') or server_config.get('id', '')
                    description_raw = server_config.get('description', '')
                    host_raw = server_config.get('host', '')
                    name_raw = server_config.get('name', '') or server_config.get('server_id', '') or server_config.get('id', '')
                    instance = server_config.get('instance', '')
                    
                    # Converter para uppercase para comparação
                    server_id = server_id_raw.upper()
                    description = description_raw.upper()
                    host = host_raw.upper()
                    name = name_raw.upper()
                    
                    # 1. Busca exata ou parcial em qualquer campo
                    for variation in ag_variations:
                        if not variation:
                            continue
                        if (variation in description or variation in server_id or variation in host or variation in name):
                            final_host = server_config.get('host', '')
                            if instance:
                                final_server_id = f"{final_host}_{instance}"
                            else:
                                final_server_id = final_host
                            
                            logger.info(f"✅ AG '{ag_name}' encontrado no sql_servers.json (match: '{variation}' em campo): {final_server_id}")
                            return JSONResponse(content={
                                'success': True,
                                'ag_name': ag_name,
                                'server': final_host,
                                'instance': instance,
                                'server_id': final_server_id,
                                'source': 'sql_servers.json',
                                'match_type': 'field_match'
                            })
                    
                    # 2. Busca reversa: verificar se o host está no AG name
                    if host and len(host) >= 6 and host in ag_name_upper:
                        final_host = server_config.get('host', '')
                        if instance:
                            final_server_id = f"{final_host}_{instance}"
                        else:
                            final_server_id = final_host
                        
                        logger.info(f"✅ AG '{ag_name}' encontrado no sql_servers.json (reverse match): {final_server_id}")
                        return JSONResponse(content={
                            'success': True,
                            'ag_name': ag_name,
                            'server': final_host,
                            'instance': instance,
                            'server_id': final_server_id,
                            'source': 'sql_servers.json',
                            'match_type': 'reverse_match'
                        })
                
                logger.warning(f"⚠️ AG '{ag_name}' não encontrado no sql_servers.json após todas as buscas")
        except Exception as e:
            logger.warning(f"Erro ao buscar no sql_servers.json: {e}")
        
        # 3. Se o AG name é um GUID, consultar KPI_MSSQL_ALWAYSON_STATUS_STG para obter Instance
        _guid_pattern = _re.compile(
            r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        )
        if _guid_pattern.match(ag_name.strip()):
            try:
                from api.routers.intelligence_kpis import execute_intelligence_query, INTELLIGENCE_SCHEMA
                stg_query = f"""
                    SELECT TOP 1 Instance
                    FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
                    WHERE UPPER(AgName) = '{ag_name.strip().upper()}'
                    AND Instance IS NOT NULL AND Instance <> ''
                    ORDER BY Update_TS DESC
                """
                stg_rows = execute_intelligence_query(stg_query, raise_on_error=False)
                if stg_rows and stg_rows[0].get('Instance'):
                    instance_from_stg = stg_rows[0]['Instance']
                    logger.info(f"✅ AG GUID '{ag_name}' resolvido via STG para Instance: {instance_from_stg}")
                    # Normalizar o nome: HOST\IINSTANCE -> HOST_IINSTANCE
                    server_id_norm = instance_from_stg.replace('\\', '_')
                    host = instance_from_stg.split('\\')[0] if '\\' in instance_from_stg else instance_from_stg
                    inst = instance_from_stg.split('\\')[1] if '\\' in instance_from_stg else ''
                    return JSONResponse(content={
                        'success': True,
                        'ag_name': ag_name,
                        'server': host,
                        'instance': inst,
                        'server_id': server_id_norm,
                        'source': 'stg_guid_lookup',
                        'match_type': 'guid_resolved'
                    })
            except Exception as e_stg:
                logger.warning(f"Erro ao consultar STG para AG GUID '{ag_name}': {e_stg}")

        # 4. Não encontrado em nenhum lugar
        logger.warning(f"⚠️ AG '{ag_name}' não encontrado em nenhum lugar")
        return JSONResponse(
            status_code=404,
            content={
                'success': False,
                'error': f"AG '{ag_name}' não encontrado no inventory nem no sql_servers.json",
                'ag_name': ag_name,
                'suggestion': 'Verifique se o AG name está correto ou se o servidor está configurado'
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao buscar instância pelo AG {ag_name}: {e}")
        raise safe_http_error(500, e, "looking up instance by AG name")

