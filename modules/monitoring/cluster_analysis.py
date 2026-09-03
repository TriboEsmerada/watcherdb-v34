#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WatcherDB - Windows Failover Cluster Analysis Module
Análise de saúde e recursos de Windows Failover Cluster
"""

import subprocess
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def check_cluster_health(server: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Verifica saúde do Windows Failover Cluster via PowerShell remoto

    Usa estratégia Plano A + Plano B:
    - Plano A: Dados completos (nodes, recursos, quorum) - ~9s
    - Plano B: Apenas AG resources (mais rápido) - ~3s se Plano A falhar

    Args:
        server: Nome do servidor (sem instância)
        timeout: Timeout em segundos (padrão 15s para Plano A, 5s para Plano B)

    Returns:
        Dict com informações de saúde do cluster
    """
    result = {
        'success': False,
        'cluster_available': False,
        'cluster_name': None,
        'nodes': [],
        'resources': [],
        'ag_resources': [],
        'failed_resources': [],
        'quorum': {},
        'error': None,
        'plan_used': None,
        'timestamp': datetime.now().isoformat()
    }

    # PLANO C: Super Fast - Apenas verificar se cluster existe (1-2s)
    try:
        logger.info(f"⚡ [PLANO C] Verificação rápida do cluster {server}...")
        ps_script_quick = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            $cluster = Get-Cluster -Name {server}
            @{{ cluster_name = $cluster.Name; cluster_domain = $cluster.Domain }} | ConvertTo-Json -Compress
        }} catch {{
            Write-Output "ERROR: $($_.Exception.Message)"
        }}
        """

        proc = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script_quick],
            capture_output=True,
            text=True,
            timeout=5,  # Apenas 5s para verificar se existe
            encoding='utf-8',
            errors='ignore'
        )

        if proc.returncode == 0 and proc.stdout and not proc.stdout.startswith('ERROR:'):
            data = json.loads(proc.stdout.strip())
            result['cluster_name'] = data.get('cluster_name')
            result['cluster_domain'] = data.get('cluster_domain')
            logger.info(f"✅ [PLANO C] Cluster {result['cluster_name']} existe - continuando com Plano A...")
        else:
            raise Exception("Cluster not found or timeout")

    except Exception as e:
        logger.warning(f"⚠️ [PLANO C] Falhou: {e} - pulando para Plano B")
        # Se nem o Plano C funcionar (5s), pular direto para Plano B
        result['plan_used'] = 'B'  # Forçar Plano B

    # PLANO A: Dados completos OTIMIZADO (só executa se Plano C funcionou)
    if not result.get('plan_used'):
        try:
            logger.info(f"📊 [PLANO A FAST] Buscando dados completos otimizados do cluster {server}...")
            # Otimizações: removido StatusInformation e IsCoreResource (lentos)
            ps_script = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            $cluster = Get-Cluster -Name {server}
            $nodes = Get-ClusterNode -Cluster {server} | Select-Object Name, State
            $allResources = Get-ClusterResource -Cluster {server} | Select-Object Name, ResourceType, State, OwnerGroup, OwnerNode
            $agResources = $allResources | Where-Object {{ $_.ResourceType -eq 'SQL Server Availability Group' }}
            $quorum = Get-ClusterQuorum -Cluster {server}

            @{{
                cluster_name = $cluster.Name
                cluster_domain = $cluster.Domain
                nodes = @($nodes | ForEach-Object {{ @{{ name = $_.Name; state = $_.State.ToString(); status_info = '' }} }})
                all_resources = @($allResources | ForEach-Object {{ @{{ name = $_.Name; resource_type = $_.ResourceType; state = $_.State.ToString(); owner_group = $_.OwnerGroup; owner_node = $_.OwnerNode; is_core = $false }} }})
                ag_resources = @($agResources | ForEach-Object {{ @{{ name = $_.Name; state = $_.State.ToString(); owner_group = $_.OwnerGroup; owner_node = $_.OwnerNode }} }})
                quorum = @{{ type = $quorum.QuorumType.ToString(); resource = $quorum.QuorumResource.Name }}
            }} | ConvertTo-Json -Depth 2 -Compress
        }} catch {{
            Write-Output "ERROR: $($_.Exception.Message)"
        }}
        """

            # Executar PowerShell com timeout
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )

            if proc.returncode == 0 and proc.stdout and not proc.stdout.startswith('ERROR:'):
                data = json.loads(proc.stdout.strip())

                result['success'] = True
                result['cluster_available'] = True
                result['cluster_name'] = data.get('cluster_name')
                result['cluster_domain'] = data.get('cluster_domain')
                result['nodes'] = data.get('nodes', [])
                result['resources'] = data.get('all_resources', [])
                result['ag_resources'] = data.get('ag_resources', [])
                result['quorum'] = data.get('quorum', {})

                # Identificar recursos com problema
                for res in result['resources']:
                    if res['state'] not in ['Online', 'Running']:
                        result['failed_resources'].append({
                            'name': res['name'],
                            'type': res['resource_type'],
                            'state': res['state'],
                            'owner_node': res['owner_node'],
                            'issue': f"Resource '{res['name']}' is {res['state']} (expected Online)"
                        })

                # Identificar nodes com problema
                unhealthy_nodes = [n for n in result['nodes'] if n['state'] != 'Up']

                result['plan_used'] = 'A'
                logger.info(
                    f"✅ [PLANO A] Cluster check: {result['cluster_name']} - "
                    f"{len(result['nodes'])} nodes, "
                    f"{len(result['resources'])} resources, "
                    f"{len(result['failed_resources'])} failed"
                )

                if unhealthy_nodes:
                    logger.warning(f"⚠️ Unhealthy nodes: {[n['name'] for n in unhealthy_nodes]}")

            else:
                error_msg = proc.stdout if proc.stdout.startswith('ERROR:') else proc.stderr
                result['error'] = f"PowerShell error: {error_msg}"
                logger.warning(f"⚠️ [PLANO A] Cluster health check failed for {server}: {error_msg}")

        except subprocess.TimeoutExpired:
            logger.warning(f"⏱ [PLANO A] Timeout ({timeout}s) - Tentando PLANO B (apenas AG resources)...")
            # PLANO B será executado abaixo
            pass
        except json.JSONDecodeError as e:
            logger.error(f"❌ [PLANO A] Failed to parse cluster data for {server}: {e}")
            # Tentar PLANO B
            pass
        except Exception as e:
            logger.warning(f"⚠️ [PLANO A] Cluster health check exception for {server}: {e}")
            # Tentar PLANO B
            pass

    # PLANO B: Apenas AG resources (mais rápido)
    if not result['success']:
        try:
            logger.info(f"🚀 [PLANO B] Buscando apenas AG resources do cluster {server}...")
            ps_script_fast = f"""
            $ErrorActionPreference = 'Stop'
            try {{
                # Apenas cluster name e AG resources
                $cluster = Get-Cluster -Name {server}
                $agResources = Get-ClusterResource -Cluster {server} | Where-Object {{
                    $_.ResourceType -eq 'SQL Server Availability Group'
                }} | Select-Object Name, State, OwnerGroup, OwnerNode

                @{{
                    cluster_name = $cluster.Name
                    cluster_domain = $cluster.Domain
                    ag_resources = @($agResources | ForEach-Object {{
                        @{{
                            name = $_.Name
                            state = $_.State.ToString()
                            owner_group = $_.OwnerGroup
                            owner_node = $_.OwnerNode
                        }}
                    }})
                }} | ConvertTo-Json -Depth 2 -Compress
            }} catch {{
                Write-Output "ERROR: $($_.Exception.Message)"
            }}
            """

            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_script_fast],
                capture_output=True,
                text=True,
                timeout=7,  # Timeout menor para Plano B
                encoding='utf-8',
                errors='ignore'
            )

            if proc.returncode == 0 and proc.stdout and not proc.stdout.startswith('ERROR:'):
                data = json.loads(proc.stdout.strip())

                result['success'] = True
                result['cluster_available'] = True
                result['cluster_name'] = data.get('cluster_name')
                result['cluster_domain'] = data.get('cluster_domain')
                result['ag_resources'] = data.get('ag_resources', [])
                result['plan_used'] = 'B'

                # Identificar AG resources com problema
                for ag in result['ag_resources']:
                    if ag['state'] not in ['Online', 'Running']:
                        result['failed_resources'].append({
                            'name': ag['name'],
                            'type': 'SQL Server Availability Group',
                            'state': ag['state'],
                            'owner_node': ag['owner_node'],
                            'issue': f"Resource '{ag['name']}' is {ag['state']} (expected Online)"
                        })

                logger.info(
                    f"✅ [PLANO B] Cluster check: {result['cluster_name']} - "
                    f"{len(result['ag_resources'])} AG resources, "
                    f"{len(result['failed_resources'])} failed"
                )

            else:
                error_msg = proc.stdout if proc.stdout.startswith('ERROR:') else proc.stderr
                result['error'] = f"PowerShell error (Plano B): {error_msg}"
                logger.warning(f"⚠️ [PLANO B] Failed for {server}: {error_msg}")

        except subprocess.TimeoutExpired:
            result['error'] = "PowerShell timeout (Plano A e B falharam)"
            logger.warning(f"⚠️ [PLANO B] Timeout (7s) for {server}")
        except Exception as e:
            result['error'] = f"Plano A e B falharam: {str(e)}"
            logger.warning(f"⚠️ [PLANO B] Exception for {server}: {e}")

    return result


def get_cluster_events(server: str, hours: int = 24, max_events: int = 50) -> Dict[str, Any]:
    """
    Obtém eventos recentes do Windows Failover Cluster Event Log

    Args:
        server: Nome do servidor
        hours: Últimas N horas (padrão 24)
        max_events: Máximo de eventos (padrão 50)

    Returns:
        Dict com eventos do cluster
    """
    result = {
        'success': False,
        'events': [],
        'critical_count': 0,
        'error_count': 0,
        'warning_count': 0,
        'error': None
    }

    try:
        ps_script = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            $startTime = (Get-Date).AddHours(-{hours})

            # Obter eventos do Failover Clustering log
            $events = Get-WinEvent -ComputerName {server} -FilterHashtable @{{
                LogName = 'Microsoft-Windows-FailoverClustering/Operational'
                StartTime = $startTime
            }} -MaxEvents {max_events} -ErrorAction SilentlyContinue

            # Converter para JSON
            @($events | ForEach-Object {{
                @{{
                    time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                    level = $_.LevelDisplayName
                    id = $_.Id
                    message = $_.Message
                    provider = $_.ProviderName
                }}
            }}) | ConvertTo-Json -Depth 2 -Compress
        }} catch {{
            Write-Output "ERROR: $($_.Exception.Message)"
        }}
        """

        proc = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )

        if proc.returncode == 0 and proc.stdout and not proc.stdout.startswith('ERROR:'):
            events = json.loads(proc.stdout.strip())
            if not isinstance(events, list):
                events = [events] if events else []

            result['success'] = True
            result['events'] = events

            # Contar por nível
            for event in events:
                level = event.get('level', '').lower()
                if 'critical' in level:
                    result['critical_count'] += 1
                elif 'error' in level:
                    result['error_count'] += 1
                elif 'warning' in level:
                    result['warning_count'] += 1

            logger.info(
                f"✅ Cluster events: {len(events)} events "
                f"({result['critical_count']} critical, {result['error_count']} errors)"
            )

        else:
            error_msg = proc.stdout if proc.stdout.startswith('ERROR:') else proc.stderr
            result['error'] = f"PowerShell error: {error_msg}"
            logger.warning(f"⚠️ Cluster events check failed for {server}: {error_msg}")

    except subprocess.TimeoutExpired:
        result['error'] = "PowerShell timeout (10s)"
    except Exception as e:
        result['error'] = str(e)
        logger.warning(f"⚠️ Cluster events exception for {server}: {e}")

    return result


def get_cluster_summary(server: str) -> Dict[str, Any]:
    """
    Obtém resumo completo do cluster (saúde + eventos recentes)

    Args:
        server: Nome do servidor

    Returns:
        Dict com resumo do cluster
    """
    health = check_cluster_health(server)

    # Se cluster está disponível, buscar eventos
    events = {'success': False, 'events': [], 'error': 'Cluster not available'}
    if health.get('cluster_available'):
        events = get_cluster_events(server, hours=24, max_events=20)

    return {
        'health': health,
        'events': events,
        'timestamp': datetime.now().isoformat()
    }
