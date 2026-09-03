#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Always On Availability Groups
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging
import json
from pathlib import Path

from modules.monitoring.watcherdb_alwayson_check import (
    AlwaysOnChecker,
    get_alwayson_overview,
    get_alwayson_status,
    get_alwayson_checker  # Singleton
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alwayson", tags=["Always On"])

@router.get("/overview")
async def get_alwayson_overview_endpoint(
    lazy: bool = Query(True, description="Se True, retorna apenas dados do JSON (RÁPIDO). Se False, conecta em todos os servidores (LENTO)")
):
    """
    Obtém overview de todos os Availability Groups

    - lazy=True (padrão): Retorna lista de AGs do inventory sem conectar (RÁPIDO - 0 conexões)
    - lazy=False: Conecta em todos os 42 servidores para buscar status completo (LENTO - 84 conexões)
    """
    try:
        checker = get_alwayson_checker()  # Usa singleton
        overview = checker.get_all_ag_overview(lazy=lazy)
        return JSONResponse(content=overview)
    except Exception as e:
        logger.error(f"Erro ao obter overview Always On: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ag/{ag_name}")
async def get_ag_detail(ag_name: str):
    """Obtém detalhes de um AG específico"""
    try:
        checker = get_alwayson_checker()  # Usa singleton
        
        # Procurar o AG nos servidores
        for ag_server in checker.ag_servers:
            if ag_server.get('ag_name') == ag_name:
                server = ag_server['server']
                instance = ag_server.get('instance', '')
                
                status = checker.get_ag_status(server, instance)
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
        raise HTTPException(status_code=500, detail=str(e))

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


@router.get("/server/{server_name}")
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

        status = checker.get_ag_status(srv, inst)

        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Always On não encontrado em {srv}{'\\' + inst if inst else ''}"
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

        # Status OK - adicionar eventos recentes
        try:
            events = checker.get_ag_failover_events(srv, inst, days=7)
            patterns = checker.analyze_failover_patterns(events)
        except Exception as e:
            logger.warning(f"Erro ao obter eventos/padrões de {srv}: {e}")
            events = []
            patterns = []

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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/server/{server_id}/overview")
async def get_server_ag_overview(server_id: str):
    """
    Obtém informações resumidas de Always On para o overview.
    Retorna None se não for Always On.
    """
    try:
        checker = get_alwayson_checker()  # Usa singleton
        
        # Primeiro, verificar se o servidor está na lista de Always On do inventory
        # Isso é mais rápido e confiável do que tentar conectar diretamente
        server_found_in_inventory = False
        ag_name_from_inventory = None
        
        # Normalizar server_id para comparação (remover backslash, converter para uppercase)
        server_id_normalized = server_id.replace('\\', '_').upper().strip()
        
        for ag_server in checker.ag_servers:
            # Verificar diferentes formatos de server_id
            server_instance_raw = ag_server.get('server_instance', '')
            server_instance = server_instance_raw.replace('\\', '_').upper().strip()
            server_name = ag_server.get('server', '').upper().strip()
            instance_name = ag_server.get('instance', '').upper().strip()
            ag_name = ag_server.get('ag_name', '')
            
            # Construir diferentes variações para comparação
            # Ex: SQLMDMPRD02_I01 pode vir como:
            # - SQLMDMPRD02\I01 (server_instance)
            # - SQLMDMPRD02_I01 (server_id)
            # - SQLMDMPRD02 + I01 (server + instance)
            
            # Comparação exata
            if server_id_normalized == server_instance:
                server_found_in_inventory = True
                ag_name_from_inventory = ag_name
                logger.info(f"✅ Servidor {server_id} encontrado no inventory Always On (AG: {ag_name}) - match exato")
                break
            
            # Comparação por server + instance
            if server_name and instance_name:
                server_instance_constructed = f"{server_name}_{instance_name}"
                if server_id_normalized == server_instance_constructed:
                    server_found_in_inventory = True
                    ag_name_from_inventory = ag_name
                    logger.info(f"✅ Servidor {server_id} encontrado no inventory Always On (AG: {ag_name}) - match por server+instance")
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
                        logger.info(f"✅ Servidor {server_id} encontrado no inventory Always On (AG: {ag_name}) - match parcial")
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
        
        status = checker.get_ag_status(server, instance)
        
        logger.debug(f"get_ag_status retornou para {server_id}: {status is not None}, tipo: {type(status)}")
        if status:
            logger.debug(f"Status contém: ag_name={status.get('ag_name')}, replicas={len(status.get('replicas', []))}, databases={len(status.get('databases', []))}")
        
        if not status:
            # Se encontrou no inventory mas não conseguiu conectar, ainda retornar como Always On
            if server_found_in_inventory:
                logger.warning(f"⚠️ Servidor {server_id} está no inventory Always On mas não foi possível conectar. Retornando como Always On baseado no inventory.")
                return JSONResponse(content={
                    'is_alwayson': True,
                    'ag_name': ag_name_from_inventory or 'Unknown',
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
        healthy_databases = sum(1 for db in databases if db.get('synchronization_state') == 'SYNCHRONIZED')
        total_databases = len(databases)
        
        # Retornar estrutura completa incluindo arrays de réplicas e databases
        # Isso permite que o frontend exiba as tabelas detalhadas
        response_data = {
            'is_alwayson': True,
            'ag_name': ag_name,
            'role': 'PRIMARY' if is_primary else 'SECONDARY',
            'is_primary': is_primary,
            'replicas': {
                'total': total_replicas,
                'healthy': healthy_replicas
            },
            'databases': {
                'total': total_databases,
                'healthy': healthy_databases
            },
            'synchronization_health': current_replica.get('synchronization_health', 'UNKNOWN') if current_replica else 'UNKNOWN',
            'availability_mode': current_replica.get('availability_mode', 'UNKNOWN') if current_replica else 'UNKNOWN',
            'failover_mode': current_replica.get('failover_mode', 'UNKNOWN') if current_replica else 'UNKNOWN',
            # Incluir arrays completos para o frontend exibir tabelas detalhadas
            'status': {
                'ag_name': ag_name,
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

@router.get("/events/{server_name}")
async def get_ag_events(
    server_name: str,
    instance: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=90, description="Número de dias para buscar eventos")
):
    """Obtém eventos de failover de um servidor"""
    try:
        checker = get_alwayson_checker()  # Usa singleton
        srv, inst = _parse_server_and_instance(server_name, instance)
        events = checker.get_ag_failover_events(srv, inst, days=days)
        patterns = checker.analyze_failover_patterns(events)
        
        return JSONResponse(content={
            'server': srv,
            'instance': inst or None,
            'days': days,
            'total_events': len(events),
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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/instance-by-ag/{ag_name}")
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
        
        # 3. Se não encontrou em nenhum lugar, retornar erro
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
        raise HTTPException(status_code=500, detail=str(e))

