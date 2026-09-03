#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WatcherDB - Windows Failover Cluster Analysis (FAST VERSION)
Versão otimizada que coleta APENAS o essencial
"""

import subprocess
import logging
import json
from typing import Dict, Any
from datetime import datetime
import time

logger = logging.getLogger(__name__)


def check_cluster_health_fast(server: str) -> Dict[str, Any]:
    """
    Verifica cluster de forma RÁPIDA - apenas AG resources e cluster name

    Esta versão é 3-5x mais rápida que a completa porque:
    - Não coleta nodes
    - Não coleta todos os recursos
    - Não coleta quorum
    - Foca apenas em AG resources (o que realmente importa)

    Args:
        server: Nome do servidor

    Returns:
        Dict com informações essenciais do cluster
    """
    start_time = time.time()

    result = {
        'success': False,
        'cluster_available': False,
        'cluster_name': None,
        'cluster_domain': None,
        'ag_resources': [],
        'failed_resources': [],
        'error': None,
        'plan_used': 'FAST',
        'elapsed_time': 0,
        'timestamp': datetime.now().isoformat()
    }

    try:
        logger.info(f"⚡ [FAST] Buscando apenas AG resources do cluster {server}...")

        # Script minimalista - APENAS cluster name e AG resources
        ps_script = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            $cluster = Get-Cluster -Name {server}
            $agResources = Get-ClusterResource -Cluster {server} | Where-Object {{
                $_.ResourceType -eq 'SQL Server Availability Group'
            }} | Select-Object Name, State, OwnerGroup, OwnerNode

            @{{
                cluster_name = $cluster.Name
                cluster_domain = $cluster.Domain
                ag_resources = @($agResources | ForEach-Object {{
                    @{{ name = $_.Name; state = $_.State.ToString(); owner_group = $_.OwnerGroup; owner_node = $_.OwnerNode }}
                }})
            }} | ConvertTo-Json -Compress
        }} catch {{
            Write-Output "ERROR: $($_.Exception.Message)"
        }}
        """

        proc = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=25,  # Timeout aumentado para 25s (ambientes de produção podem ser MUITO lentos)
            encoding='utf-8',
            errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )

        if proc.returncode == 0 and proc.stdout and not proc.stdout.startswith('ERROR:'):
            data = json.loads(proc.stdout.strip())

            result['success'] = True
            result['cluster_available'] = True
            result['cluster_name'] = data.get('cluster_name')
            result['cluster_domain'] = data.get('cluster_domain')
            result['ag_resources'] = data.get('ag_resources', [])

            # Identificar AG resources com problema
            # States: Inherited=0, Initializing=1, Online=2, Offline=3, Failed=4
            for ag in result['ag_resources']:
                state_str = ag.get('state', '')
                if state_str not in ['Online', 'Inherited']:
                    result['failed_resources'].append({
                        'name': ag['name'],
                        'type': 'SQL Server Availability Group',
                        'state': state_str,
                        'owner_node': ag.get('owner_node', ''),
                        'issue': f"Resource '{ag['name']}' is {state_str} (expected Online)"
                    })

            result['elapsed_time'] = time.time() - start_time

            logger.info(
                f"✅ [FAST] Sucesso em {result['elapsed_time']:.2f}s - "
                f"Cluster: {result['cluster_name']}, "
                f"AG Resources: {len(result['ag_resources'])}, "
                f"Failed: {len(result['failed_resources'])}"
            )

        else:
            error_msg = proc.stdout if proc.stdout.startswith('ERROR:') else proc.stderr
            result['error'] = f"PowerShell error: {error_msg}"
            result['elapsed_time'] = time.time() - start_time
            logger.warning(f"⚠️ [FAST] Failed after {result['elapsed_time']:.2f}s: {error_msg}")

    except subprocess.TimeoutExpired:
        result['error'] = "PowerShell timeout (25s) - Ambiente muito lento ou permissões lentas"
        result['elapsed_time'] = time.time() - start_time
        logger.warning(f"⏱ [FAST] Timeout after {result['elapsed_time']:.2f}s - Ambiente MUITO lento")
    except Exception as e:
        result['error'] = str(e)
        result['elapsed_time'] = time.time() - start_time
        logger.warning(f"⚠️ [FAST] Exception after {result['elapsed_time']:.2f}s: {e}")

    return result


def get_cluster_events_fast(server: str, max_events: int = 50) -> Dict[str, Any]:
    """
    Coleta eventos críticos do cluster de forma RÁPIDA
    Foca apenas em eventos Error e Warning das últimas 24 horas
    """
    start_time = time.time()

    result = {
        'success': False,
        'events': [],
        'error': None,
        'elapsed_time': 0
    }

    try:
        logger.info(f"⚡ [FAST EVENTS] Buscando eventos críticos do cluster {server} (últimas 24h)...")

        # Script PowerShell otimizado - apenas eventos críticos (Error + Warning) das últimas 24h
        ps_script = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            $after = (Get-Date).AddHours(-24)
            $events = Get-WinEvent -ComputerName {server} -FilterHashtable @{{
                LogName = 'Microsoft-Windows-FailoverClustering/Operational'
                Level = @(2, 3)
                StartTime = $after
            }} -MaxEvents {max_events} -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, LevelDisplayName, Message

            @{{
                events = @($events | ForEach-Object {{
                    @{{
                        timestamp = $_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')
                        event_id = $_.Id
                        level = $_.LevelDisplayName
                        message = $_.Message -replace '[\\r\\n]+', ' '
                    }}
                }})
            }} | ConvertTo-Json -Compress
        }} catch {{
            Write-Output "ERROR: $($_.Exception.Message)"
        }}
        """

        proc = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=15,  # Timeout aumentado para 15s
            encoding='utf-8',
            errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )

        if proc.returncode == 0 and proc.stdout and not proc.stdout.startswith('ERROR:'):
            data = json.loads(proc.stdout.strip())
            result['success'] = True
            result['events'] = data.get('events', [])
            result['elapsed_time'] = time.time() - start_time

            logger.info(
                f"✅ [FAST EVENTS] {len(result['events'])} eventos obtidos em {result['elapsed_time']:.2f}s"
            )
        else:
            error_msg = proc.stdout if proc.stdout.startswith('ERROR:') else proc.stderr
            result['error'] = f"PowerShell error: {error_msg}"
            result['elapsed_time'] = time.time() - start_time
            logger.warning(f"⚠️ [FAST EVENTS] Failed after {result['elapsed_time']:.2f}s: {error_msg}")

    except subprocess.TimeoutExpired:
        result['error'] = "PowerShell timeout (15s)"
        result['elapsed_time'] = time.time() - start_time
        logger.warning(f"⏱ [FAST EVENTS] Timeout after {result['elapsed_time']:.2f}s")
    except Exception as e:
        result['error'] = str(e)
        result['elapsed_time'] = time.time() - start_time
        logger.warning(f"⚠️ [FAST EVENTS] Exception after {result['elapsed_time']:.2f}s: {e}")

    return result


def get_cluster_summary_fast(server: str) -> Dict[str, Any]:
    """
    Obtém resumo rápido do cluster com eventos básicos
    Se health check demorar muito (>20s), pula eventos para não exceder timeout do frontend
    """
    health = check_cluster_health_fast(server)

    # Se health check falhou ou demorou muito (>20s), não buscar eventos
    health_time = health.get('elapsed_time', 0)
    if not health.get('success') or health_time > 20:
        logger.info(f"⏭️ [FAST] Pulando eventos (health {'falhou' if not health.get('success') else f'demorou {health_time:.1f}s'})")
        events = {
            'success': False,
            'events': [],
            'error': 'Eventos não coletados (health check falhou ou demorou muito)',
            'elapsed_time': 0
        }
    else:
        events = get_cluster_events_fast(server, max_events=50)

    return {
        'health': health,
        'events': events,
        'timestamp': datetime.now().isoformat()
    }
