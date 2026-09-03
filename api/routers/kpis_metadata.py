#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Metadados de KPIs
Fornece endpoints para metadados de KPIs usados no dashboard
"""

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime, timedelta
from api.error_helpers import safe_http_error
from api.models import KPIMetadataItem, GenericResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/kpis",
    tags=["KPI Metadata"],
    responses={404: {"description": "Not found"}}
)

# ============================================================================
# METADADOS DOS KPIs
# ============================================================================
# Definição dos metadados de cada KPI do dashboard
# Baseado na estrutura esperada pelo frontend
# ============================================================================

# ============================================================================
# MAPEAMENTO DE MODOS DE COLETA
# ============================================================================
# Define quais KPIs são incluídos em cada modo de coleta
# 
# Modos disponíveis:
# - kpi-fast: 11 KPIs rápidos (coletados a cada 5 min)
# - kpi-only: 14 KPIs (11 fast + long_locks + deadlocks + service_status)
# - locks-only: 2 KPIs (long_locks, deadlocks)
# ============================================================================

KPI_MODES = {
    'kpi-fast': [
        'blocked_sessions',
        'blocked_users',
        'db_transaction_logs',  # tlog_usage
        'always_on',  # alwayson_status
        'instance_availability',
        'processes_alarm',  # processes
        'db_availability',
        'backup_status',  # backups
        'db_io_stats',
        'db_disk_file_system',  # disk_usage
        'filegroup_usage',
        'cpu_critical',      # CPU >= 95% sustentado
        'memory_critical'    # Memoria >= 99% com page fault/swap
    ],
    'kpi-only': [
        # Todos os 13 do kpi-fast
        'blocked_sessions',
        'blocked_users',
        'db_transaction_logs',
        'always_on',
        'instance_availability',
        'processes_alarm',
        'db_availability',
        'backup_status',
        'db_io_stats',
        'db_disk_file_system',
        'filegroup_usage',
        'cpu_critical',
        'memory_critical',
        # Mais 3 adicionais
        'lock_count',  # long_locks
        'deadlocks',  # card Deadlocks activo (janela 24h via AGG_VIEW)
        'service_status'
    ],
    'locks-only': [
        'lock_count',  # long_locks
        'deadlocks'    # card Deadlocks activo (janela 24h via AGG_VIEW)
    ],
    'performance-only': [
        'processes_alarm',
        'db_io_stats',
        'cpu_critical',
        'memory_critical'
    ]
}

# ============================================================================
# FRESCURA REAL DOS KPIs
# ============================================================================
# O `last_update` era `datetime.now()` (placeholder que ficou em producao -- o
# comentario original dizia "Simular ultima coleta"). Isso fazia com que a UI
# nunca conseguisse distinguir um dado de agora de um dado de ha' meses: o QA
# externo apanhou collectors parados ha' 129 dias por tras de cartoes verdes.
#
# A infra real ja existia e nao estava ligada: modules/collector_health le' o
# Last_Swap_Time da KPI_STG_ACTIVE_TABLE (swap Blue/Green) e tem fallback
# MAX(<coluna de timestamp>). Aqui so' fazemos o wiring.
#
# Regra: quando nao se consegue determinar, devolve-se None -- NUNCA now(). Um
# "desconhecido" honesto vale mais do que um "agora" inventado.

def _stg_table_for(table_name: Optional[str]) -> Optional[str]:
    """Normaliza o nome da tabela do KPI para o nome que a KPI_STG_ACTIVE_TABLE regista.

    O KPI_METADATA aponta para as vistas (_AGG_VIEW/_DET_VIEW) mas o registo de
    swap guarda a tabela base _STG. Sem esta normalizacao o lookup falha sempre
    e cai no fallback -- o V6 ja documentou 2 drifts neste mapeamento.
    """
    if not table_name:
        return None
    for suffix in ("_AGG_VIEW", "_DET_VIEW", "_ACTIVE"):
        if table_name.endswith(suffix):
            return table_name[: -len(suffix)] + "_STG"
    return table_name if table_name.endswith("_STG") else None


async def _fetch_freshness_state() -> Dict[str, Any]:
    """Le uma vez o estado de swap para todos os KPIs do pedido (evita N queries)."""
    try:
        from modules.collector_health.health_calculator import _fetch_active_state
        return await _fetch_active_state()
    except Exception as e:
        logger.warning(f"[KPI-META] estado de frescura indisponivel: {e}")
        return {}


async def _resolve_last_update(table_name: Optional[str],
                               active_state: Dict[str, Any]) -> tuple:
    """Devolve (iso_timestamp | None, origem). Origem e' explicita para o cliente
    poder distinguir 'medido' de 'desconhecido' sem adivinhar."""
    stg = _stg_table_for(table_name)
    if not stg:
        return None, "unmapped"
    row = active_state.get(stg.upper())
    if row and row.get("Last_Swap_Time"):
        ts = row["Last_Swap_Time"]
        return (ts.isoformat() if hasattr(ts, "isoformat") else str(ts)), "active_table"
    try:
        from modules.collector_health.health_calculator import _fetch_max_update_ts
        ts, col = await _fetch_max_update_ts([stg])
        if ts:
            return (ts.isoformat() if hasattr(ts, "isoformat") else str(ts)), f"max_{col}"
    except Exception as e:
        logger.debug(f"[KPI-META] fallback MAX() falhou para {stg}: {e}")
    return None, "unknown"


KPI_METADATA = [
    {
        "name": "db_availability",
        "display_name": "Disponibilidade de Banco de Dados",
        "category": "availability",
        "description": "Monitora a disponibilidade de databases nas instâncias SQL Server",
        "avg_duration_ms": 130.0,
        "max_duration_ms": 1500.0,
        "table_name": "KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "db_disk_file_system",
        "display_name": "Uso de Disco",
        "category": "capacity",
        "description": "Monitora o uso de espaço em disco dos volumes das instâncias",
        "avg_duration_ms": 180.0,
        "max_duration_ms": 1200.0,
        "table_name": "KPI_MSSQL_DISK_USAGE_AGG_VIEW",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "db_transaction_logs",
        "display_name": "Logs de Transação",
        "category": "capacity",
        "description": "Monitora o uso de espaço dos transaction logs",
        "avg_duration_ms": 170.0,
        "max_duration_ms": 1300.0,
        "table_name": "KPI_MSSQL_TLOG_USAGE_AGG_VIEW",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "always_on",
        "display_name": "Always On",
        "category": "availability",
        "description": "Monitora o status de saúde dos grupos Always On",
        "avg_duration_ms": 50.0,
        "max_duration_ms": 2000.0,
        "table_name": "KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "filegroup_usage",
        "display_name": "Uso de FileGroups",
        "category": "capacity",
        "description": "Monitora o uso de espaço dos filegroups",
        "avg_duration_ms": 220.0,
        "max_duration_ms": 1400.0,
        "table_name": "KPI_MSSQL_FG_USAGE_STG",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "blocked_sessions",
        "display_name": "Sessões Bloqueadas",
        "category": "real_time",
        "description": "Monitora sessões bloqueadas em tempo real",
        "avg_duration_ms": 60.0,
        "max_duration_ms": 800.0,
        "table_name": "KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "blocked_users",
        "display_name": "Usuários Bloqueados",
        "category": "real_time",
        "description": "Monitora usuários com sessões bloqueadas",
        "avg_duration_ms": 120.0,
        "max_duration_ms": 700.0,
        "table_name": "KPI_MSSQL_BLOCKED_USERS_STG",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "processes_alarm",
        "display_name": "Alarme de Processos",
        "category": "performance",
        "description": "Monitora contagem anormal de processos",
        "avg_duration_ms": 70.0,
        "max_duration_ms": 600.0,
        "table_name": "KPI_MSSQL_PROCESSES_AGG_VIEW",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "lock_count",
        "display_name": "Contagem de Locks",
        "category": "real_time",
        "description": "Monitora locks de longa duração (query lenta: 15-18s, não recomendado para coleta rápida)",
        "avg_duration_ms": 15000.0,
        "max_duration_ms": 18000.0,
        "table_name": "KPI_MSSQL_LONG_LOCKS_AGG_VIEW",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "instance_availability",
        "display_name": "Disponibilidade de Instância",
        "category": "availability",
        "description": "Monitora disponibilidade das instâncias SQL Server",
        "avg_duration_ms": 50.0,
        "max_duration_ms": 500.0,
        "table_name": "KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW",
        "is_fast": True,
        "collection_interval_minutes": 5
    },
    {
        "name": "backup_status",
        "display_name": "Status de Backup",
        "category": "capacity",
        "description": "Monitora status e atrasos de backups",
        "avg_duration_ms": 280.0,
        "max_duration_ms": 1800.0,
        "table_name": "KPI_MSSQL_BACKUPS_STG",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "deadlocks",
        "display_name": "Deadlocks",
        "category": "performance",
        "description": "Monitoriza ocorrências de deadlocks via system_health ring_buffer. Janela de 24h, agregado por instância com severity OK/INFO/WARNING/CRITICAL baseado em Deadlock_Count. Read-only (zero pegada nos servidores monitorizados).",
        "avg_duration_ms": 150.0,
        "max_duration_ms": 800.0,
        "table_name": "KPI_MSSQL_DEADLOCKS_AGG_VIEW",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "service_status",
        "display_name": "Status de Serviços",
        "category": "availability",
        "description": "Monitora status dos serviços SQL Server (problemas técnicos com DECLARE, não recomendado para coleta rápida)",
        "avg_duration_ms": 90.0,
        "max_duration_ms": 550.0,
        "table_name": "KPI_MSSQL_SERVICE_STATUS_AGG_VIEW",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "error_log",
        "display_name": "Log de Erros",
        "category": "availability",
        "description": "Monitora erros críticos nos logs do SQL Server",
        "avg_duration_ms": 350.0,
        "max_duration_ms": 2500.0,
        "table_name": "KPI_MSSQL_ERRORLOG_STG",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "db_io_stats",
        "display_name": "Estatísticas de I/O",
        "category": "performance",
        "description": "Monitora estatísticas de I/O das databases",
        "avg_duration_ms": 320.0,
        "max_duration_ms": 2200.0,
        "table_name": "KPI_MSSQL_DB_IO_STATS_AGG_VIEW",
        "is_fast": False,
        "collection_interval_minutes": 15
    },
    {
        "name": "cpu_critical",
        "display_name": "CPU Crítico",
        "category": "performance",
        "description": "Monitora instâncias com CPU >= 95% sustentado por 1-2 minutos. Ao clicar, abre modal com link para o módulo de CPU da instância problemática.",
        "avg_duration_ms": 80.0,
        "max_duration_ms": 500.0,
        "table_name": "OS_PERFORMANCE_HISTORY",
        "is_fast": True,
        "collection_interval_minutes": 5,
        "detail_module": "/api/monitoring/cpu/server/{instance}",
        "threshold_critical": 95,
        "sustained_minutes": 2
    },
    {
        "name": "memory_critical",
        "display_name": "Memória Crítico",
        "category": "performance",
        "description": "Monitora instâncias com memória >= 99% com alto page fault ou swap em disco. Ao clicar, abre modal com link para o módulo de Memória da instância problemática.",
        "avg_duration_ms": 100.0,
        "max_duration_ms": 600.0,
        "table_name": "OS_PERFORMANCE_HISTORY",
        "is_fast": True,
        "collection_interval_minutes": 5,
        "detail_module": "/api/monitoring/memory/server/{instance}",
        "threshold_critical": 99,
        "check_page_fault": True,
        "check_swap": True
    }
]


@router.get("/metadata", response_model=List[KPIMetadataItem])
async def get_kpi_metadata():
    """
    Retorna todos os metadados de KPIs
    
    Usado pelo frontend para:
    - Obter informações sobre cada KPI (display_name, description, etc.)
    - Determinar se é fast ou completo (is_fast)
    - Exibir tempo médio de coleta (avg_duration_ms)
    - Filtrar KPIs por modo
    
    Returns:
        Lista de objetos com metadados de cada KPI
    """
    try:
        # Frescura REAL da coleta, nao a hora do pedido.
        # Antes: last_update = datetime.now() -- os 17 KPIs mudavam de timestamp a
        # cada chamada (o QA externo provou-o com 2 pedidos a 4s de intervalo). Era
        # o mecanismo que fazia dados de 129 dias parecerem "agora".
        metadata_with_timestamp = []
        active_state = await _fetch_freshness_state()
        for kpi in KPI_METADATA:
            kpi_copy = kpi.copy()
            ts, source = await _resolve_last_update(kpi.get("table_name"), active_state)
            kpi_copy["last_update"] = ts          # None quando desconhecido -- nunca now()
            kpi_copy["last_update_source"] = source
            metadata_with_timestamp.append(kpi_copy)
        
        return JSONResponse(
            status_code=200,
            content=metadata_with_timestamp
        )
    except Exception as e:
        logger.error(f"Erro ao retornar metadados de KPIs: {e}", exc_info=True)
        raise safe_http_error(500, e, "returning KPI metadata")


@router.get("/by-mode/{mode}", response_model=GenericResponse)
async def get_kpis_by_mode(mode: str = Path(..., description="Modo de filtro: 'kpi-fast', 'kpi-only', 'locks-only', ou 'all'")):
    """
    Retorna KPIs filtrados por modo de coleta
    
    Modos disponíveis:
    - 'kpi-fast': 11 KPIs rápidos (blocked_sessions, blocked_users, tlog_usage, alwayson_status, instance_availability, processes, db_availability, backups, db_io_stats, disk_usage, filegroup_usage)
    - 'kpi-only': 14 KPIs (11 fast + long_locks + deadlocks + service_status)
    - 'locks-only': 2 KPIs (long_locks, deadlocks)
    - 'all': Todos os KPIs
    
    Args:
        mode: Modo de filtro
        
    Returns:
        Lista de KPIs filtrados com informações de última coleta
    """
    try:
        # Validar modo
        valid_modes = ['kpi-fast', 'kpi-only', 'locks-only', 'all']
        if mode not in valid_modes:
            raise HTTPException(
                status_code=400,
                detail=f"Modo inválido. Use um dos seguintes: {', '.join(valid_modes)}"
            )
        
        # Criar dicionário de KPIs por nome para busca rápida
        kpi_by_name = {kpi['name']: kpi for kpi in KPI_METADATA}
        
        # Filtrar KPIs baseado no modo
        filtered_kpis = []
        if mode == 'all':
            # Todos os KPIs
            filtered_kpis = list(KPI_METADATA)
        elif mode in KPI_MODES:
            # Usar mapeamento explícito do modo
            kpi_names = KPI_MODES[mode]
            for kpi_name in kpi_names:
                if kpi_name in kpi_by_name:
                    filtered_kpis.append(kpi_by_name[kpi_name])
                else:
                    logger.warning(f"KPI '{kpi_name}' definido no modo '{mode}' não encontrado nos metadados")
        else:
            # Fallback para lógica antiga (compatibilidade)
            for kpi in KPI_METADATA:
                if mode == 'kpi-fast' and kpi.get('is_fast', False):
                    filtered_kpis.append(kpi)
                elif mode == 'kpi-only' and not kpi.get('is_fast', False):
                    filtered_kpis.append(kpi)
        
        # Adicionar informações de última coleta (simulado - em produção viria do banco)
        result = []
        current_time = datetime.now()
        for kpi in filtered_kpis:
            kpi_copy = kpi.copy()
            # Frescura REAL (era simulada: 3 ou 12 minutos fixos, inventados a
            # partir do flag is_fast). Um numero plausivel e' pior do que nenhum
            # -- parece medido. Ver o bloco de helpers no topo do ficheiro.
            ts, source = await _resolve_last_update(kpi.get("table_name"), active_state)
            kpi_copy["last_collection_time"] = ts
            kpi_copy["last_update"] = ts
            kpi_copy["last_update_source"] = source
            result.append(kpi_copy)
        
        return JSONResponse(
            status_code=200,
            content={
                "mode": mode,
                "count": len(result),
                "kpis": result,
                "timestamp": current_time.isoformat()
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao filtrar KPIs por modo: {e}", exc_info=True)
        raise safe_http_error(500, e, "filtering KPIs by mode")


@router.get("/", response_model=GenericResponse)
async def root():
    """
    Endpoint raiz - informações sobre a API de metadados
    """
    return JSONResponse(
        status_code=200,
        content={
            "service": "KPI Metadata API",
            "version": "1.0.0",
            "endpoints": {
                "metadata": "/api/v1/kpis/metadata",
                "by_mode": "/api/v1/kpis/by-mode/{mode}",
                "modes": ["kpi-fast", "kpi-only", "locks-only", "all"]
            },
            "total_kpis": len(KPI_METADATA),
            "fast_kpis": len([k for k in KPI_METADATA if k.get('is_fast', False)]),
            "complete_kpis": len([k for k in KPI_METADATA if not k.get('is_fast', False)]),
            "mode_definitions": {
                "kpi-fast": {
                    "count": len(KPI_MODES.get('kpi-fast', [])),
                    "kpis": KPI_MODES.get('kpi-fast', [])
                },
                "kpi-only": {
                    "count": len(KPI_MODES.get('kpi-only', [])),
                    "kpis": KPI_MODES.get('kpi-only', [])
                },
                "locks-only": {
                    "count": len(KPI_MODES.get('locks-only', [])),
                    "kpis": KPI_MODES.get('locks-only', [])
                }
            }
        }
    )

