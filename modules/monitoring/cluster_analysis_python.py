#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WatcherDB - Windows Failover Cluster Analysis (Python Native)
Versão Python nativa usando WMI - MUITO mais rápida que PowerShell!
"""

import wmi
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import time

logger = logging.getLogger(__name__)


def check_cluster_health_python(server: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Verifica saúde do Windows Failover Cluster via WMI Python (RÁPIDO!)

    Plano A: Dados completos via WMI (~2-3s)
    Plano B: Apenas AG resources via WMI (~1s)

    Args:
        server: Nome do servidor
        timeout: Timeout em segundos (padrão 10s)

    Returns:
        Dict com informações de saúde do cluster
    """
    start_time = time.time()

    result = {
        'success': False,
        'cluster_available': False,
        'cluster_name': None,
        'cluster_domain': None,
        'nodes': [],
        'resources': [],
        'ag_resources': [],
        'failed_resources': [],
        'quorum': {},
        'error': None,
        'plan_used': None,
        'method': 'python_wmi',
        'elapsed_time': 0,
        'timestamp': datetime.now().isoformat()
    }

    # PLANO A: Dados completos via WMI
    try:
        logger.info(f"🐍 [PYTHON PLANO A] Conectando via WMI ao cluster {server}...")

        # Conectar via WMI ao servidor remoto
        c = wmi.WMI(computer=server, namespace="root\\MSCluster")

        # 1. Obter informações do cluster
        cluster_objs = list(c.MSCluster_Cluster())
        if not cluster_objs:
            raise Exception("Cluster not found")

        cluster = cluster_objs[0]
        result['cluster_name'] = cluster.Name
        result['cluster_domain'] = getattr(cluster, 'Domain', None)

        logger.info(f"✅ [PYTHON A] Cluster encontrado: {result['cluster_name']}")

        # 2. Obter nodes do cluster
        nodes = []
        for node in c.MSCluster_Node():
            nodes.append({
                'name': node.Name,
                'state': node.State,  # 0=Up, 1=Down, 2=Paused, 3=Joining
                'status_info': node.StatusInformation if hasattr(node, 'StatusInformation') else ''
            })
        result['nodes'] = nodes

        logger.info(f"✅ [PYTHON A] Nodes: {len(nodes)}")

        # 3. Obter recursos do cluster
        resources = []
        ag_resources = []

        for res in c.MSCluster_Resource():
            resource_info = {
                'name': res.Name,
                'resource_type': res.Type,
                'state': res.State,  # 0=Inherited, 1=Initializing, 2=Online, 3=Offline, 4=Failed, etc.
                'owner_group': res.OwnerGroup if hasattr(res, 'OwnerGroup') else '',
                'owner_node': res.OwnerNode if hasattr(res, 'OwnerNode') else '',
                'is_core': res.CoreResource if hasattr(res, 'CoreResource') else False
            }
            resources.append(resource_info)

            # Filtrar AG resources
            if 'SQL Server Availability Group' in str(res.Type):
                ag_resources.append({
                    'name': res.Name,
                    'state': res.State,
                    'owner_group': resource_info['owner_group'],
                    'owner_node': resource_info['owner_node']
                })

        result['resources'] = resources
        result['ag_resources'] = ag_resources

        logger.info(f"✅ [PYTHON A] Resources: {len(resources)}, AG: {len(ag_resources)}")

        # 4. Obter quorum
        try:
            quorum_objs = list(c.MSCluster_ClusterQuorum())
            if quorum_objs:
                quorum = quorum_objs[0]
                result['quorum'] = {
                    'type': quorum.QuorumType if hasattr(quorum, 'QuorumType') else 'Unknown',
                    'resource': quorum.QuorumResource if hasattr(quorum, 'QuorumResource') else 'N/A'
                }
        except Exception as e:
            logger.warning(f"⚠️ [PYTHON A] Não foi possível obter quorum: {e}")
            result['quorum'] = {'type': 'Unknown', 'resource': 'N/A'}

        # 5. Identificar recursos com problema
        # States: 0=Inherited, 1=Initializing, 2=Online, 3=Offline, 4=Failed
        for res in result['resources']:
            if res['state'] not in [0, 2]:  # Não é Inherited ou Online
                state_name = {
                    1: 'Initializing',
                    3: 'Offline',
                    4: 'Failed',
                    5: 'Pending',
                    128: 'Unknown'
                }.get(res['state'], f'State {res["state"]}')

                result['failed_resources'].append({
                    'name': res['name'],
                    'type': res['resource_type'],
                    'state': state_name,
                    'owner_node': res['owner_node'],
                    'issue': f"Resource '{res['name']}' is {state_name} (expected Online)"
                })

        # Identificar nodes com problema
        unhealthy_nodes = [n for n in result['nodes'] if n['state'] != 0]  # State 0 = Up

        result['success'] = True
        result['cluster_available'] = True
        result['plan_used'] = 'A_python'
        result['elapsed_time'] = time.time() - start_time

        logger.info(
            f"✅ [PYTHON A] Sucesso em {result['elapsed_time']:.2f}s - "
            f"{len(nodes)} nodes, {len(resources)} resources, {len(result['failed_resources'])} failed"
        )

        if unhealthy_nodes:
            logger.warning(f"⚠️ [PYTHON A] Unhealthy nodes: {[n['name'] for n in unhealthy_nodes]}")

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.warning(f"⚠️ [PYTHON A] Falhou após {elapsed:.2f}s: {e}")

        # Se Plano A falhou, tentar Plano B
        if elapsed < timeout - 2:  # Ainda tem tempo
            pass  # Continua para Plano B abaixo
        else:
            result['error'] = f"Python WMI error: {str(e)}"
            result['elapsed_time'] = elapsed
            return result

    # PLANO B: Apenas AG resources (mais rápido)
    if not result['success']:
        try:
            logger.info(f"🚀 [PYTHON PLANO B] Buscando apenas AG resources via WMI...")

            c = wmi.WMI(computer=server, namespace="root\\MSCluster")

            # Cluster name
            cluster_objs = list(c.MSCluster_Cluster())
            if cluster_objs:
                cluster = cluster_objs[0]
                result['cluster_name'] = cluster.Name
                result['cluster_domain'] = getattr(cluster, 'Domain', None)

            # Apenas AG resources
            ag_resources = []
            for res in c.MSCluster_Resource():
                if 'SQL Server Availability Group' in str(res.Type):
                    ag_resources.append({
                        'name': res.Name,
                        'state': res.State,
                        'owner_group': res.OwnerGroup if hasattr(res, 'OwnerGroup') else '',
                        'owner_node': res.OwnerNode if hasattr(res, 'OwnerNode') else ''
                    })

            result['ag_resources'] = ag_resources

            # Identificar AG resources com problema
            for ag in ag_resources:
                if ag['state'] not in [0, 2]:  # Não Online
                    state_name = {
                        1: 'Initializing',
                        3: 'Offline',
                        4: 'Failed',
                        5: 'Pending'
                    }.get(ag['state'], f'State {ag["state"]}')

                    result['failed_resources'].append({
                        'name': ag['name'],
                        'type': 'SQL Server Availability Group',
                        'state': state_name,
                        'owner_node': ag['owner_node'],
                        'issue': f"Resource '{ag['name']}' is {state_name} (expected Online)"
                    })

            result['success'] = True
            result['cluster_available'] = True
            result['plan_used'] = 'B_python'
            result['elapsed_time'] = time.time() - start_time

            logger.info(
                f"✅ [PYTHON B] Sucesso em {result['elapsed_time']:.2f}s - "
                f"{len(ag_resources)} AG resources, {len(result['failed_resources'])} failed"
            )

        except Exception as e:
            elapsed = time.time() - start_time
            result['error'] = f"Python WMI error (Plano B): {str(e)}"
            result['elapsed_time'] = elapsed
            logger.warning(f"⚠️ [PYTHON B] Falhou após {elapsed:.2f}s: {e}")

    return result


def get_cluster_events_python(server: str, hours: int = 24, max_events: int = 50) -> Dict[str, Any]:
    """
    Obtém eventos do cluster via WMI Python (ainda usa PowerShell para eventos)

    Nota: Eventos de cluster são mais complexos via WMI, mantém PowerShell por enquanto
    """
    from .cluster_analysis import get_cluster_events
    return get_cluster_events(server, hours, max_events)


def get_cluster_summary_python(server: str) -> Dict[str, Any]:
    """
    Obtém resumo completo do cluster via Python WMI
    """
    health = check_cluster_health_python(server)

    # Events ainda via PowerShell (opcional)
    events = {'success': False, 'events': [], 'error': 'Events via PowerShell'}
    if health.get('cluster_available'):
        try:
            events = get_cluster_events_python(server, hours=24, max_events=20)
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível obter events: {e}")

    return {
        'health': health,
        'events': events,
        'timestamp': datetime.now().isoformat()
    }
