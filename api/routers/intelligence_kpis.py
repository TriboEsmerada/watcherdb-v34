#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para KPIs do WatcherDB Intelligence
Busca dados das views agregadas do SQL Server Intelligence para exibir no dashboard
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from api.routers.auth_compat import _require_admin, _require_auth, _require_dba
from watcherdb.core.db_identity import resolve as _resolve_db_identity
from services.secrets import get_secret
from typing import Dict, List, Optional, Any
import logging
import re
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
import pyodbc
from decimal import Decimal
from datetime import datetime, timedelta
import time
from cachetools import TTLCache

# Import do pool de conexões centralizado
from api.connection_pool import get_intelligence_pool, get_sql_server_pool
from pathlib import Path
import json
from api.error_helpers import safe_http_error
from api.models import DashboardResponse, GenericResponse, MessageResponse, SuccessResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

# Thread pool para executar queries de forma nao bloqueante
_query_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="sql_query")

# ========================================
# CACHE PARA DASHBOARD KPIs
# ========================================
# Thread-safe TTL cache (replaces manual dict + lock pattern)
_dashboard_cache = TTLCache(maxsize=10, ttl=30)
_cache_lock = threading.Lock()

def _get_cached_dashboard():
    """Retorna dados do cache se ainda validos"""
    with _cache_lock:
        return _dashboard_cache.get('dashboard_data')

def _set_dashboard_cache(data):
    """Armazena dados no cache"""
    with _cache_lock:
        _dashboard_cache['dashboard_data'] = data

logger = logging.getLogger(__name__)

# ========================================
# FRESHNESS WINDOW CONFIGURATION
# ========================================
# Freshness windows define how recent data must be to be considered valid for KPI counting.
# This prevents stale data from views (that may not have been refreshed by ETL) from
# showing as active problems in the dashboard.
#
# Freshness Rules by KPI Category:
# - Services/Instance Availability: 15 minutes (services can change state quickly)
# - Blocked Sessions/Deadlocks/Long Locks: 5 minutes (real-time operational events)
# - Backups/Filegroups/Disk/DB I/O/Other capacity metrics: 60 minutes (capacity metrics change slowly)
# - AlwaysOn Status: 5 minutes (dedicated collection every 1 minute - 2025-12-21)
#
FRESHNESS_WINDOWS = {
    'services': 15,           # Services and Instance Availability (minutes)
    'real_time': 5,           # Blocked Sessions, Deadlocks, Long Locks (minutes)
    'capacity': 1440,         # Filegroups, Disk, DB I/O, capacity metrics: 24 horas
    'backup': 1440,           # Backups: 24 horas (coleta menos frequente)
    'alwayson': 5,            # AlwaysOn status - coleta dedicada a cada 1 minuto (minutes)
}

# ========================================
# CACHE DE VALORES PERSISTENTES
# ========================================
# Armazena os últimos valores conhecidos de KPIs que devem manter o valor
# até que um problema seja detectado (diminuindo apenas quando há problemas)
_last_known_values = {
    'instances_ok': None,           # Último valor conhecido de instâncias OK
    'db_availability_ok': None,     # Último valor conhecido de DB Availability OK (instâncias)
    'db_availability_total': None,   # Último valor conhecido de DB Availability Total (databases)
    'last_abnormal_count': None,    # Último valor de DB Not Availability (para detectar mudanças)
    'last_instances_off_count': None, # Último valor de Instances Off (para detectar mudanças)
    '_initialized': False           # Flag para indicar se já foi inicializado com valores do DB
}


def is_data_fresh(row: Dict[str, Any], minutes: int) -> bool:
    """
    Check if a data row is fresh (recent enough) based on its timestamp columns.

    This function attempts to find timestamp columns in the row using common naming patterns
    and checks if the data is within the specified freshness window.

    Args:
        row: Dictionary containing the data row from a database query
        minutes: Freshness threshold in minutes (from FRESHNESS_WINDOWS)

    Returns:
        True if data is fresh (within threshold), False if stale or no timestamp found

    Timestamp Column Detection:
    The function tries multiple common column name patterns in order:
    - Last_Check, LAST_CHECK, last_check
    - Update_TS, UPDATE_TS, update_ts
    - Capture_TS, CAPTURE_TS, capture_ts
    - Capture_Time, CAPTURE_TIME, capture_time
    - Timestamp, TIMESTAMP, timestamp
    - Updated_At, UPDATED_AT, updated_at
    - Created_At, CREATED_AT, created_at

    Freshness Windows (from FRESHNESS_WINDOWS constant):
    - FRESHNESS_WINDOWS['services'] = 15 min: Services, Instance Availability
    - FRESHNESS_WINDOWS['real_time'] = 5 min: Blocked Sessions, Deadlocks, Long Locks
    - FRESHNESS_WINDOWS['capacity'] = 60 min: Backups, Filegroups, Disk, DB I/O

    Examples:
        >>> row = {'Instance': 'SQL01', 'Last_Check': '2025-12-01T10:30:00'}
        >>> is_data_fresh(row, FRESHNESS_WINDOWS['services'])  # 15 minutes
        True  # if current time is within 15 minutes of 10:30

        >>> row = {'Instance': 'SQL01', 'Update_TS': '2025-12-01T09:00:00'}
        >>> is_data_fresh(row, FRESHNESS_WINDOWS['real_time'])  # 5 minutes
        False  # if current time is more than 5 minutes after 09:00
    """
    # Try to find timestamp column using common naming patterns
    timestamp = None
    timestamp_column = None

    # List of possible timestamp column names (in order of priority)
    # Incluindo padrões específicos para backups e outras tabelas
    possible_timestamp_columns = [
        'Last_Check', 'LAST_CHECK', 'last_check',
        'Update_TS', 'UPDATE_TS', 'update_ts',
        'Capture_TS', 'CAPTURE_TS', 'capture_ts',
        'Capture_Time', 'CAPTURE_TIME', 'capture_time',
        'Timestamp', 'TIMESTAMP', 'timestamp',
        'Updated_At', 'UPDATED_AT', 'updated_at',
        'Created_At', 'CREATED_AT', 'created_at',
        'LogDate', 'Log_Date', 'LOG_DATE', 'log_date',
        'Backup_Date', 'BACKUP_DATE', 'backup_date',  # Específico para backups
        'Last_Backup', 'LAST_BACKUP', 'last_backup',  # Específico para backups
        'Backup_Time', 'BACKUP_TIME', 'backup_time',  # Específico para backups
        'Date', 'DATE', 'date',  # Genérico
        'Time', 'TIME', 'time',  # Genérico
    ]

    for col_name in possible_timestamp_columns:
        if col_name in row:
            timestamp = row[col_name]
            timestamp_column = col_name
            break

    # If no timestamp found, try fallback logic
    if not timestamp:
        # Fallback 1: Para dados de backup, se Hours_Since_Backup existe e é válido,
        # considerar como "fresco" se o valor for razoável (menos de 30 dias)
        if 'Hours_Since_Backup' in row or 'HOURS_SINCE_BACKUP' in row or 'hours_since_backup' in row:
            hours_col = 'Hours_Since_Backup' if 'Hours_Since_Backup' in row else ('HOURS_SINCE_BACKUP' if 'HOURS_SINCE_BACKUP' in row else 'hours_since_backup')
            hours = row.get(hours_col, None)
            if hours is not None:
                try:
                    hours_val = float(hours) if not isinstance(hours, (int, float)) else hours
                    # Se Hours_Since_Backup é válido e razoável (< 30 dias = 720 horas),
                    # considerar como dado recente (assumindo que foi coletado recentemente)
                    if 0 <= hours_val < 720:
                        logger.debug(f"Using Hours_Since_Backup as freshness indicator: {hours_val} hours (no timestamp column found)")
                        return True
                except (ValueError, TypeError):
                    pass
        
        # Fallback 2: Para views agregadas (AGG_VIEW) que não têm timestamp,
        # assumir que os dados são "frescos" se a view tem a estrutura de agregação
        # Views agregadas são atualizadas pelo ETL, então se existem dados, são relativamente recentes
        # Identificar views agregadas pela presença de colunas típicas de agregação
        row_keys_original = list(row.keys())  # Manter original para logging
        row_keys_lower = [str(k).lower() for k in row_keys_original]  # Normalizar para lowercase para comparação
        
        # Lista de colunas de agregação (case-insensitive)
        aggregation_columns = ['warning', 'critical', 'cnt', 'count', 'abnormalcnt', 'totalcnt', 
                              'unhealthy', 'deadlock_count', 'services_down_count', 'normal', 
                              'failed', 'delayed', 'failed_count', 'delayed_count', 'processes']
        
        # Lista de colunas de instância (case-insensitive)
        instance_columns = ['instance', 'instance_name', 'server', 'server_name', 'agname', 'ag_name', 'env']
        
        # Verificar se tem coluna 'State' com valores típicos de views agregadas
        has_state_column = 'state' in row_keys_lower
        state_value = None
        if has_state_column:
            state_key = next((k for k in row_keys_original if k.lower() == 'state'), None)
            if state_key:
                state_value = str(row.get(state_key, '')).upper()
        
        # Valores típicos de State em views agregadas
        # IMPORTANTE: Não incluir estados de database (OFFLINE, RECOVERING, etc.) que são da DET_VIEW
        aggregated_state_values = ['WARNING', 'CRITICAL', 'NORMAL', 'UNAVAILABLE', 'HEALTHY', 'UNHEALTHY']
        # Estados de database (DET_VIEW) que NÃO devem ser considerados como agregação
        database_state_values = ['OFFLINE', 'RECOVERING', 'RESTORING', 'RECOVERY_PENDING', 'SUSPECT', 'EMERGENCY']

        # Se o State for um estado de database, não considerar como view agregada
        is_database_state = has_state_column and state_value in database_state_values
        has_aggregated_state = has_state_column and state_value in aggregated_state_values and not is_database_state
        
        has_aggregation_columns = any(col in row_keys_lower for col in aggregation_columns)
        has_instance_column = any(col in row_keys_lower for col in instance_columns)
        
        # É uma view agregada se tem: (colunas de agregação OU State com valores agregados) E coluna de instância
        if (has_aggregation_columns or has_aggregated_state) and has_instance_column:
            # É uma view agregada - assumir que é fresca se tem a estrutura correta
            # Views agregadas são atualizadas pelo ETL, então se a view retorna dados, são recentes
            logger.debug(f"AGG_VIEW detected (no timestamp): Assuming fresh data for row with columns {row_keys_original}")
            return True
        
        # Só logar warning se não for uma view agregada (já tratada acima)
        logger.warning(f"No timestamp column found in row. Available columns: {row_keys_original}")
        # Fail-safe: retornar False (considerar como stale)
        return False

    # Convert to datetime if string
    if isinstance(timestamp, str):
        try:
            # Handle ISO format with or without timezone
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Could not parse timestamp '{timestamp}' from column '{timestamp_column}': {e}")
            return False

    # Ensure it's a datetime object
    if not isinstance(timestamp, datetime):
        logger.warning(f"Timestamp column '{timestamp_column}' has unexpected type: {type(timestamp)}")
        return False

    # Check if within freshness window
    cutoff_time = datetime.now() - timedelta(minutes=minutes)

    # Handle timezone-aware vs timezone-naive comparison
    try:
        if timestamp.tzinfo is not None:
            # Timestamp is timezone-aware, make cutoff_time aware too (UTC)
            from datetime import timezone
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

        is_fresh = timestamp >= cutoff_time

        if not is_fresh:
            logger.debug(f"Stale data detected: {timestamp_column}={timestamp} is older than {minutes} minutes (cutoff: {cutoff_time})")

        return is_fresh
    except Exception as e:
        logger.warning(f"Error comparing timestamps: {e}")
        return False

router = APIRouter(prefix="/api/intelligence-kpis", tags=["Intelligence KPIs"])

# Fase 0 thresholds (2026-08-04): fonte unica — ver api/kpi_thresholds_registry.py
# Fase 1: _th resolve overrides globais do cliente (fallback ao registry).
from api.kpi_thresholds_registry import registry_as_list, REGISTRY_VERSION
from api.threshold_overrides import resolve as _th

# NOTE: Sub-modules exist in api/routers/intelligence/ for future decomposition.
# The helpers, events, and admin endpoints have been extracted there.
# Currently, this file retains all endpoints for backward compatibility.
# To complete the migration, remove the duplicated endpoints here and use:
#   from api.routers.intelligence import router as _sub_router
#   router.include_router(_sub_router)
limiter = Limiter(key_func=get_remote_address)

# Configuração de conexão SQL Server Intelligence
import os

# Prioridade: INTELLIGENCE_* > SQL_* > default
INTELLIGENCE_SERVER = os.getenv("INTELLIGENCE_SERVER") or os.getenv("SQL_SERVER", "SQLHDSTST505\\I01")
INTELLIGENCE_DATABASE = os.getenv("INTELLIGENCE_DATABASE") or os.getenv("SQL_DATABASE", "WatcherDB_Intelligence")
INTELLIGENCE_SCHEMA = "dbo"
# Windows Auth: prioridade para SQL_TRUSTED_CONNECTION do .env
# Identidade da ligacao: fonte unica em watcherdb.core.db_identity (achado
# P-05). Sem variavel definida NAO ha default implicito -- resolve() devolve
# UNSET (nunca Windows Auth) e o arranque do servico e' recusado la'.
_DB_IDENTITY = _resolve_db_identity()
INTELLIGENCE_USE_WINDOWS_AUTH = _DB_IDENTITY.use_windows_auth
INTELLIGENCE_SQL_USER = os.getenv("INTELLIGENCE_SQL_USER") or os.getenv("SQL_USER", "sql_monitoring")
# get_secret decifra o formato "encrypted:<fernet>" que o .env usa. Ler com
# os.getenv cru entregava o ciphertext ao pyodbc e o login falhava -- e' isso
# que obrigava o SQL_TRUSTED_CONNECTION=yes a mascarar o problema (P-05).
INTELLIGENCE_SQL_PASSWORD = get_secret("INTELLIGENCE_SQL_PASSWORD", "") or get_secret("SQL_PASSWORD", "")
INTELLIGENCE_DRIVER = "ODBC Driver 17 for SQL Server"

# Log da configuracao ao carregar o modulo
import logging as _init_logging
_init_logger = _init_logging.getLogger(__name__)
_init_logger.info(f"Intelligence KPIs configurado: SERVER={INTELLIGENCE_SERVER}, DATABASE={INTELLIGENCE_DATABASE}, WINDOWS_AUTH={INTELLIGENCE_USE_WINDOWS_AUTH} [{_DB_IDENTITY.mode}: {_DB_IDENTITY.source}]")

# Connection Pool simples para evitar abrir/fechar conexao a cada query
_connection_pool = []
_pool_lock = threading.Lock()
_MAX_POOL_SIZE = 5


def _return_connection_to_pool(conn):
    """Retorna conexao ao pool para reuso"""
    try:
        with _pool_lock:
            if len(_connection_pool) < _MAX_POOL_SIZE:
                # Testar se conexao ainda e valida
                try:
                    conn.execute("SELECT 1")
                    _connection_pool.append(conn)
                    return
                except Exception:
                    pass
            # Fechar se pool cheio ou conexao invalida
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass

def _get_pooled_connection():
    """Obtem conexao do pool ou cria nova"""
    with _pool_lock:
        while _connection_pool:
            conn = _connection_pool.pop()
            try:
                # Testar se conexao ainda e valida
                conn.execute("SELECT 1")
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
    # Pool vazio, criar nova conexao
    return None

def get_intelligence_connection():
    """
    Obtém conexão com o SQL Server Intelligence usando pool centralizado.

    Usa o IntelligenceConnectionPool do módulo connection_pool.py para
    reutilizar conexões e melhorar a performance.
    """
    try:
        pool = get_intelligence_pool()
        conn = pool.get_connection()
        logger.debug("Conexão obtida do pool Intelligence")
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao SQL Server Intelligence: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao conectar ao SQL Server Intelligence: {str(e)}"
        )


def execute_intelligence_query(query: str, raise_on_error: bool = True) -> List[Dict]:
    """Executa query no SQL Server Intelligence e retorna resultados como lista de dicionários"""
    conn = None
    cursor = None
    _q_start = time.time()
    try:
        conn = get_intelligence_connection()
        _conn_time = time.time() - _q_start
        cursor = conn.cursor()

        try:
            cursor.execute(query)
        except Exception as query_err:
            logger.error(f"[QUERY ERROR] Falha ao executar query: {query}\nErro: {query_err}")
            if raise_on_error:
                # Inclui o texto da query no HTTPException para facilitar debug em ambiente de desenvolvimento
                raise safe_http_error(500, query_err, "executing Intelligence SQL query")
            return []

        _exec_time = time.time() - _q_start - _conn_time
        if _conn_time > 1 or _exec_time > 1:
            # Log apenas queries lentas (>1s)
            _query_preview = query[:80].replace(chr(10), " ").strip()
            logger.debug(f"[QUERY] conn={_conn_time:.2f}s exec={_exec_time:.2f}s | {_query_preview}...")

        # Obter nomes das colunas
        columns = [desc[0] for desc in cursor.description]

        # Buscar todos os resultados
        rows = cursor.fetchall()

        # Converter para lista de dicionários
        results = []
        for row in rows:
            row_dict = {}
            for idx, col in enumerate(columns):
                value = row[idx]
                # Converter Decimal para float
                if isinstance(value, Decimal):
                    value = float(value)
                # Converter datetime para string ISO
                elif isinstance(value, datetime):
                    value = value.isoformat()
                row_dict[col] = value
            results.append(row_dict)

        return results
    except Exception as e:
        # Neste ponto, erros não relacionados ao SQL "bad column name", mas sim de conexão, etc.
        logger.error(f"Erro ao executar query no Intelligence: {e}", exc_info=True)
        if raise_on_error:
            raise safe_http_error(500, e, "executing Intelligence query")
        return []
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            # Retornar conexão ao pool para reutilização
            try:
                pool = get_intelligence_pool()
                pool.return_connection(conn)
            except Exception:
                pass


async def execute_intelligence_query_async(query: str, raise_on_error: bool = True) -> List[Dict]:
    """Versao async de execute_intelligence_query - nao bloqueia o event loop"""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _query_executor,
            lambda: execute_intelligence_query(query, raise_on_error=False)
        )
    except Exception as e:
        logger.error(f'Erro ao executar query async: {e}', exc_info=True)
        if raise_on_error:
            raise safe_http_error(500, e, "executing async Intelligence query")
        return []


async def _initialize_last_known_values_from_db():
    """
    Inicializa _last_known_values com dados do banco de dados na primeira execucao.
    OTIMIZADO: Executa todas as queries em PARALELO para reduzir tempo.
    """
    global _last_known_values

    if _last_known_values.get('_initialized'):
        return

    logger.info("[CACHE] Iniciando inicializacao de KPIs (PARALELO)...")
    total_start = time.time()

    try:
        # Definir todas as queries (conforme QUERIES_KPI_DASHBOARD.sql)
        queries = [
            # DB Availability Total - contar databases distintos da ACTIVE
            (f"SELECT COUNT(DISTINCT Instance + '|' + [Database]) AS v FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_ACTIVE WITH (NOLOCK)", 'db_availability_total', 'v'),
            # Instances OK
            (f"SELECT COUNT(DISTINCT Instance) AS v FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WITH (NOLOCK) WHERE Is_Available = 1", 'instances_ok', 'v'),
            # 1.1 DB Not Availability - usar PROBLEM_VIEW (databases com problema)
            (f"SELECT COUNT(*) AS v FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW WITH (NOLOCK)", 'last_abnormal_count', 'v'),
            # Instances Off - servidores com PING FALHOU e evento nao resolvido (GROUPED_VIEW ja filtra Is_Resolved=0 e ultimos 7 dias)
            (f"SELECT COUNT(DISTINCT Instance) AS v FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK) WHERE Ping_OK = 0", 'last_instances_off_count', 'v'),
        ]

        # Executar TODAS em PARALELO com timing individual
        async def _timed_query(query_tuple, idx, labels):
            q, key, field = query_tuple
            _start = time.time()
            result = await execute_intelligence_query_async(q, raise_on_error=False)
            _elapsed = time.time() - _start
            logger.info(f"[CACHE-TIMING] {labels[idx]}: {_elapsed:.2f}s")
            return result
        
        labels = ['DB Availability Total (AGG)', 'Instances OK', 'DB Abnormal (PROBLEM)', 'Instances Off']
        results = await asyncio.gather(
            *[_timed_query(q, i, labels) for i, q in enumerate(queries)],
            return_exceptions=True
        )

        # Processar resultados - com tempo individual de cada query
        labels = ['DB Availability Total (AGG)', 'Instances OK', 'DB Abnormal (PROBLEM)', 'Instances Off']
        for i, (query, key, field) in enumerate(queries):
            data = results[i]
            if isinstance(data, Exception):
                logger.error(f"[CACHE] {labels[i]}: ERRO - {data}")
            elif isinstance(data, list) and data and data[0].get(field) is not None:
                _last_known_values[key] = int(data[0][field])
                logger.info(f"[CACHE] {labels[i]}: {_last_known_values[key]}")
            else:
                logger.warning(f"[CACHE] {labels[i]}: Sem dados")

        _last_known_values['_initialized'] = True
        logger.info(f"[CACHE] Inicializacao completa em {time.time() - total_start:.2f}s (PARALELO)")

    except Exception as e:
        logger.error(f"Erro ao inicializar cache de KPIs: {e}", exc_info=True)


def _detect_env(instance_name: str, env_value: Optional[str] = None) -> str:
    """Detecta ambiente a partir do nome da instancia ou valor fornecido."""
    if env_value and env_value.strip() and env_value.strip() != 'Undefined':
        return env_value.strip()
    return _infer_env_from_instance(instance_name or '')


def _load_monitored_servers() -> List[Dict]:
    """E6: delega na copia canonica (helpers -> services.inventory_repo). Era copia literal."""
    try:
        from services.inventory_repo import load_monitored_servers
        return load_monitored_servers(enabled_only=False)
    except Exception as e:
        logger.warning(f"Erro ao carregar inventario (inventory_repo): {e}")
        return []


def _build_jobs_conn_str(server_id: str) -> str:
    """Connection string com timeout curto (4s) para queries de jobs KPI."""
    if '_' in server_id and '\\' not in server_id:
        parts = server_id.split('_', 1)
        server_name = f"{parts[0]}\\{parts[1]}"
    else:
        server_name = server_id
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server_name};DATABASE=master;"
        f"Trusted_Connection=yes;TrustServerCertificate=yes;"
        f"Connection Timeout=4;"
    )


def _query_server_failed_jobs(server_id: str) -> List[Dict]:
    """Query failed jobs nas ultimas 24h de um servidor via msdb."""
    conn = None
    try:
        # Conexao directa com timeout curto (4s) — servidores offline falham rapido
        # Evita bloquear a thread 30s (pool timeout) e perder todos os resultados no asyncio
        conn = pyodbc.connect(_build_jobs_conn_str(server_id), timeout=4, autocommit=True)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 50
                j.name AS job_name,
                h.step_name,
                CASE h.run_status
                    WHEN 0 THEN 'Failed'
                    WHEN 2 THEN 'Retry'
                    WHEN 3 THEN 'Cancelled'
                END AS status_desc,
                msdb.dbo.agent_datetime(h.run_date, h.run_time) AS run_datetime,
                (h.run_duration / 10000 * 3600) + ((h.run_duration % 10000) / 100 * 60) + (h.run_duration % 100) AS duration_seconds,
                LEFT(h.message, 500) AS error_message
            FROM msdb.dbo.sysjobs j WITH (NOLOCK)
            INNER JOIN msdb.dbo.sysjobhistory h WITH (NOLOCK) ON j.job_id = h.job_id
            WHERE h.run_status = 0
                AND h.step_id > 0
                AND msdb.dbo.agent_datetime(h.run_date, h.run_time) >= DATEADD(HOUR, -24, GETDATE())
            ORDER BY msdb.dbo.agent_datetime(h.run_date, h.run_time) DESC
        """)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        results = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, 'isoformat'):
                    row_dict[col] = val.isoformat()
                elif hasattr(val, '__float__'):
                    row_dict[col] = float(val)
                else:
                    row_dict[col] = val
            results.append(row_dict)
        cursor.close()
        return results
    except Exception as e:
        logger.debug(f"Erro ao buscar failed jobs de {server_id}: {e}")
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _query_server_job_collisions(server_id: str) -> List[Dict]:
    """Detecta colisoes de schedule (jobs que executaram ao mesmo tempo) nas ultimas 24h."""
    conn = None
    try:
        # Conexao directa com timeout curto (4s) — servidores offline falham rapido
        conn = pyodbc.connect(_build_jobs_conn_str(server_id), timeout=4, autocommit=True)
        cursor = conn.cursor()
        # Detectar jobs que executaram simultaneamente nas ultimas 24h
        cursor.execute("""
            ;WITH job_runs AS (
                SELECT
                    j.name AS job_name,
                    j.job_id,
                    msdb.dbo.agent_datetime(h.run_date, h.run_time) AS start_time,
                    DATEADD(SECOND,
                        (h.run_duration / 10000 * 3600) + ((h.run_duration % 10000) / 100 * 60) + (h.run_duration % 100),
                        msdb.dbo.agent_datetime(h.run_date, h.run_time)
                    ) AS end_time,
                    h.run_status
                FROM msdb.dbo.sysjobs j WITH (NOLOCK)
                INNER JOIN msdb.dbo.sysjobhistory h WITH (NOLOCK) ON j.job_id = h.job_id
                WHERE h.step_id = 0
                    AND msdb.dbo.agent_datetime(h.run_date, h.run_time) >= DATEADD(HOUR, -24, GETDATE())
                    AND h.run_duration > 0
            )
            SELECT
                a.job_name AS job_a,
                b.job_name AS job_b,
                a.start_time AS start_a,
                b.start_time AS start_b,
                DATEDIFF(MINUTE,
                    CASE WHEN a.start_time > b.start_time THEN a.start_time ELSE b.start_time END,
                    CASE WHEN a.end_time < b.end_time THEN a.end_time ELSE b.end_time END
                ) AS overlap_minutes,
                CASE WHEN a.run_status = 0 OR b.run_status = 0 THEN 1 ELSE 0 END AS has_failure
            FROM job_runs a
            INNER JOIN job_runs b ON a.job_id < b.job_id
                AND a.start_time < b.end_time
                AND b.start_time < a.end_time
        """)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        results = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, 'isoformat'):
                    row_dict[col] = val.isoformat()
                elif hasattr(val, '__float__'):
                    row_dict[col] = float(val)
                else:
                    row_dict[col] = val
            results.append(row_dict)
        cursor.close()
        return results
    except Exception as e:
        logger.debug(f"Erro ao buscar job collisions de {server_id}: {e}")
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


async def _query_jobs_from_servers(only_collisions: bool = False, timeout: float = 25.0) -> tuple:
    """
    Consulta todos os servidores monitorados para obter dados de jobs.
    Retorna (failed_results, collision_results) como dicts ou (None, None).
    """
    servers = _load_monitored_servers()
    if not servers:
        logger.warning("Jobs Status - Nenhum servidor monitorado encontrado em servers.json")
        return None, None

    loop = asyncio.get_event_loop()
    failed_results_data = {"failed_count": 0, "instances": [], "failed_by_env": {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}, "failed_by_type": {}}
    collision_results_data = {"collision_count": 0, "instances": [], "collision_by_env": {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}}

    # E6b (2026-08-19): ANTES cortava a servers[:20] -- o KPI de jobs so' cobria 20 dos ~62
    # servidores em silencio. Agora consulta TODOS (enabled + com credenciais locais, ja'
    # filtrado pelo inventory_repo) com concorrencia limitada (16 workers) em vez de um
    # worker por servidor; o asyncio.wait(timeout) continua a devolver resultados parciais.
    servers_to_query = [s for s in servers if s.get('enabled', True)]
    _jobs_executor = ThreadPoolExecutor(max_workers=min(16, max(1, len(servers_to_query))), thread_name_prefix='jobs_query')

    # Query servidores em paralelo
    async def _query_one_server(server):
        server_id = server.get('id', '')
        env = server.get('environment', 'Undefined')
        # Normalizar env
        env_map = {'production': 'PRD', 'quality': 'QLT', 'test': 'TST', 'development': 'TST'}
        env_key = env_map.get(env.lower(), _infer_env_from_instance(server_id))

        failed = []
        collisions = []
        if not only_collisions:
            try:
                failed = await loop.run_in_executor(
                    _jobs_executor, lambda sid=server_id: _query_server_failed_jobs(sid)
                )
            except Exception as e:
                logger.debug(f"Failed jobs query error for {server_id}: {e}")

        try:
            collisions = await loop.run_in_executor(
                _jobs_executor, lambda sid=server_id: _query_server_job_collisions(sid)
            )
        except Exception as e:
            logger.debug(f"Collision query error for {server_id}: {e}")

        return server_id, env_key, failed, collisions

    # Executar em paralelo — asyncio.wait devolve resultados parciais mesmo se alguns servers atrasam
    # ao contrario de asyncio.wait_for(gather) que perde TODOS os resultados se algum server atrasa
    tasks = [asyncio.ensure_future(_query_one_server(s)) for s in servers_to_query]
    try:
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        if pending:
            logger.warning(f"Jobs Status - {len(pending)}/{len(tasks)} servidores nao responderam em {timeout}s (ignorados)")
            for t in pending:
                t.cancel()
    finally:
        _jobs_executor.shutdown(wait=False)

    completed_results = []
    for t in done:
        try:
            completed_results.append(t.result())
        except Exception:
            pass

    for result in completed_results:
        if isinstance(result, Exception):
            continue
        server_id, env_key, failed, collisions = result

        if failed:
            for job in failed:
                job['Instance'] = server_id
                job['Env'] = env_key
                # Classificar tipo de job pelo nome
                jn = (job.get('Job_Name') or job.get('job_name') or job.get('JobName') or '').upper()
                if any(k in jn for k in ('BACKUP', 'BKP', 'BKUP')):
                    jt = 'Backup'
                elif any(k in jn for k in ('REINDEX', 'REBUILD', 'INDEX', 'OPTIMIZE', 'DEFRAG')):
                    jt = 'Index'
                elif any(k in jn for k in ('STATISTIC', 'STATS', 'UPDATE STAT')):
                    jt = 'Statistics'
                elif any(k in jn for k in ('CHECK', 'DBCC', 'INTEGRITY', 'CHECKDB')):
                    jt = 'DBCC'
                elif any(k in jn for k in ('SHRINK',)):
                    jt = 'Shrink'
                elif any(k in jn for k in ('LOG',)):
                    jt = 'Log'
                elif any(k in jn for k in ('CLEANUP', 'CLEAN_UP', 'CLEAN UP', 'PURGE', 'ARCHIVE')):
                    jt = 'Cleanup'
                elif any(k in jn for k in ('REPLICATION', 'REPL')):
                    jt = 'Replication'
                elif any(k in jn for k in ('ALWAYSON', 'ALWAYS_ON', 'ALWAYS ON', 'HADR', 'AG_')):
                    jt = 'AlwaysOn'
                else:
                    jt = 'Other'
                job['Job_Type'] = jt
                failed_results_data["failed_by_type"][jt] = failed_results_data["failed_by_type"].get(jt, 0) + 1
            failed_results_data["instances"].extend(failed)
            env_k = env_key if env_key in ['PRD', 'QLT', 'TST'] else 'Undefined'
            failed_results_data["failed_by_env"][env_k] = failed_results_data["failed_by_env"].get(env_k, 0) + len(failed)

        if collisions:
            # Contar pares unicos de colisao por servidor
            seen_pairs = set()
            for col in collisions:
                pair = (col.get('job_a', ''), col.get('job_b', ''))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    col['Instance'] = server_id
                    col['Env'] = env_key
                    collision_results_data["instances"].append(col)
            env_k = env_key if env_key in ['PRD', 'QLT', 'TST'] else 'Undefined'
            collision_results_data["collision_by_env"][env_k] = collision_results_data["collision_by_env"].get(env_k, 0) + len(seen_pairs)

    failed_results_data["failed_count"] = len(failed_results_data["instances"])
    collision_results_data["collision_count"] = len(collision_results_data["instances"])

    return (
        failed_results_data if failed_results_data["failed_count"] > 0 else None,
        collision_results_data if collision_results_data["collision_count"] > 0 else None
    )


def _infer_env_from_instance(instance_name: str) -> str:
    """
    Infere o ambiente (PRD/QLT/TST) do nome da instância
    """
    if not instance_name:
        return 'Undefined'
    instance_upper = instance_name.upper()
    if 'PRD' in instance_upper or 'PROD' in instance_upper:
        return 'PRD'
    elif 'QLT' in instance_upper or 'QUAL' in instance_upper:
        return 'QLT'
    elif 'TST' in instance_upper or 'TEST' in instance_upper or 'DEV' in instance_upper:
        return 'TST'
    return 'Undefined'

def _count_by_env(instances: List[Dict[str, Any]], env_key: str = 'Env') -> Dict[str, int]:
    """
    Conta instâncias por ambiente (PRD, QLT, TST, Undefined)
    """
    counts = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
    for row in instances:
        if not row:
            continue
        # Tentar diferentes nomes de coluna para ambiente
        env = (row.get(env_key) or row.get('ENV') or row.get('Env') or row.get('Environment') or row.get('environment') or '').strip()

        # Se não encontrou ambiente, tentar inferir do nome da instância
        if not env or env == 'Undefined':
            instance_name = (row.get('Instance') or row.get('INSTANCE') or row.get('ServerInstance') or row.get('SERVER_INSTANCE') or '').strip()
            env = _infer_env_from_instance(instance_name)

        env_upper = env.upper() if env else 'Undefined'
        if env_upper in ['PRD', 'QLT', 'TST']:
            counts[env_upper] = counts.get(env_upper, 0) + 1
        else:
            # Contar Undefined e outros ambientes não reconhecidos
            counts['Undefined'] = counts.get('Undefined', 0) + 1
    return counts

def _serialize_result(obj):
    """Serializa objetos para JSON (Decimal, datetime, etc)"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_result(item) for item in obj]
    return obj


import asyncio as _aio_sf
_dashboard_refresh_lock = _aio_sf.Lock()


async def _collect_and_cache_dashboard() -> dict:
    """Single-flight wrapper (2026-06-09): garante UM gather de cada vez. Concorrentes
    (re-warm + pedidos + toast poller) ESPERAM e reusam o cache, em vez de lancarem
    gathers paralelos que esgotavam o pool (10 conns) e criavam espiral de latencia.
    [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: single-flight]"""
    from api.routers.intelligence.helpers import _get_cached_dashboard as _h_get_cached
    async with _dashboard_refresh_lock:
        _cached = _h_get_cached()
        if _cached:
            return _cached
        return await _do_collect_and_cache_dashboard()


async def _do_collect_and_cache_dashboard() -> dict:
    """Core: coleta KPIs (3 fases) + popula cache. SEM Request/limiter.
    [#1+#3+F5 DS-Reconcile 2026-06-09]"""
    from api.routers.intelligence.helpers import (
        init_dashboard_results,
        collect_db_availability,
        collect_disk_and_tlog,
        collect_alwayson,
        collect_mirroring,
        collect_filegroup_usage,
        collect_realtime_kpis,
        collect_instance_availability,
        build_offline_hostnames,
        collect_backup_status,
        collect_service_status,
        collect_error_log,
        collect_db_io_stats,
        collect_tempdb_status,
        collect_server_offline,
        collect_cpu_critical,
        collect_memory_critical,
        collect_deadlocks,
        collect_disk_latency,
        collect_jobs_status,
        collect_collection_freshness,
        collect_integrity,
        format_dashboard_response,
    )
    import asyncio
    _kpi_start_total = time.time()
    _kpi_times = {}

    # Fase 1 thresholds (2026-08-04): refrescar overrides do cliente ANTES das
    # classificacoes (que sao sincronas). Cache TTL 60s; tabela ausente = defaults.
    try:
        from api import threshold_overrides as _thr_ovr
        _thr_ovr.refresh_cache()
    except Exception:
        pass

    await _initialize_last_known_values_from_db()
    results = init_dashboard_results()
    _kpi_times["parallel_start"] = time.time()

    # Phase 1: independentes (JOBS movido para Phase 3 — #3)
    await asyncio.gather(
        collect_db_availability(results),
        collect_disk_and_tlog(results),
        collect_alwayson(results),
        collect_mirroring(results),
        collect_filegroup_usage(results),
        collect_realtime_kpis(results),
        collect_instance_availability(results),
        collect_backup_status(results),
        collect_service_status(results),
        collect_error_log(results),
        collect_db_io_stats(results),
        collect_tempdb_status(results),
        collect_server_offline(results),
        collect_deadlocks(results),
        collect_integrity(results),
        return_exceptions=True,
    )

    # Phase 2: dependem de offline_hostnames (depois de instance_availability)
    offline_hostnames = build_offline_hostnames(results)
    await asyncio.gather(
        collect_cpu_critical(results, offline_hostnames),
        collect_memory_critical(results, offline_hostnames),
        collect_disk_latency(results, offline_hostnames),
        return_exceptions=True,
    )

    # Phase 3: JOBS isolado com timeout duro — nao bloqueia a resposta >10s (#3)
    try:
        await asyncio.wait_for(
            collect_jobs_status(results, _query_jobs_from_servers), timeout=10.0
        )
    except asyncio.TimeoutError:
        logger.warning("[KPI] collect_jobs_status timeout 10s — jobs com ultimo valor/defaults")

    # Freshness guard Componente A (2026-07-17): marca tiles STALE quando o
    # collector-fonte esta morto (fail-open se a view nao existir)
    await collect_collection_freshness(results)

    return format_dashboard_response(results, _kpi_times, _kpi_start_total)


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit("60/minute")
async def get_kpi_dashboard(request: Request):
    """Retorna todos os KPIs agregados para o dashboard do WatcherDB Intelligence.

    This endpoint orchestrates collection of all KPI categories via helper
    functions defined in ``api.routers.intelligence.helpers``.
    """
    from api.routers.intelligence.helpers import (
        _get_cached_dashboard as _h_get_cached,
        _load_dashboard_snapshot as _h_load_snapshot,
    )
    import asyncio as _aio
    try:
        cached = _h_get_cached()
        if cached:
            return JSONResponse(content=cached)
        # Stale-while-revalidate (2026-06-11): cache frio (janela pos-restart) servia
        # coleta ao vivo de 89 servers -> browser timeout 25/90s. Com snapshot em disco,
        # responder IMEDIATO com dados stale + lancar refresh em background (apenas se
        # nao ha refresh em curso — single-flight lock evita stampede).
        snapshot = _h_load_snapshot()
        if snapshot:
            if not _dashboard_refresh_lock.locked():
                _aio.create_task(_collect_and_cache_dashboard())
            return JSONResponse(content=snapshot)
        # Sem snapshot (primeira instalacao): comportamento original
        return JSONResponse(content=await _collect_and_cache_dashboard())
    except Exception as e:
        raise safe_http_error(500, e, "fetching Intelligence KPI dashboard")


@router.get("/detail/filegroup-usage/{instance_name}", response_model=GenericResponse)
async def get_filegroup_usage_detail(instance_name: str):
    """Retorna detalhes de filegroups com problema para uma instância específica

    Usa tabela KPI_MSSQL_FG_USAGE_STG (tabela blue/green ativa com últimas coletas):
    - Instance, Database, Filegroup, Total_MB, Used_MB, Free_MB, Percent_Used, Max_Size_MB, Growth_Type, Update_TS

    Thresholds (Fase 1.5, 2026-08-13): configuráveis via registry+overrides —
    filegroup_free_pct (% livre; defaults w=5/c=2 => Percent_Used >95/>98;
    ATTENTION fixo >90) e filegroup_unlimited_free_gb (defaults w=10/c=5 GB).
    """
    try:
        # mesma guarda do get_problematic_instances (:1174-1178): refresh do
        # cache de overrides em cold start; tabela ausente = defaults.
        try:
            from api import threshold_overrides as _thr_ovr
            _thr_ovr.refresh_cache()
        except Exception:
            pass
        # % livre -> Percent_Used (menor=pior invertido); warning_cap<=10 no
        # router garante fg_warn_pu >= 90, logo o WHERE estatico >90 (tier
        # ATTENTION fixo) continua a cobrir todas as linhas classificaveis.
        fg_crit_pu = 100 - float(_th('filegroup_free_pct', 'critical'))
        fg_warn_pu = 100 - float(_th('filegroup_free_pct', 'warning'))
        # UNLIMITED disk-bound: WHERE deriva do warning (sem folga acima dele)
        fgu_warn_mb = float(_th('filegroup_unlimited_free_gb', 'warning')) * 1024
        fgu_crit_mb = float(_th('filegroup_unlimited_free_gb', 'critical')) * 1024
        # Normalizar nome da instância - aceitar tanto _ quanto \
        instance_underscore = instance_name.replace('\\', '_')
        instance_backslash = instance_name.replace('_', '\\')
        safe_underscore = instance_underscore.replace("'", "''")
        safe_backslash = instance_backslash.replace("'", "''")

        # Regra baseada em % livre (Fase 1.5: defaults do registry, override
        # do cliente aplica): Critical = livre < critical (default 2);
        # Warning = livre entre critical e warning (default 2-5);
        # Attention = livre entre warning e 10 (tier fixo nesta fase).
        # 2026-07-27 (gate v1-intel, Opcao A): Growth_Type='UNLIMITED' excluido
        # da lista de problemas — ficheiro autogrow ~cheio do alocado e' estado
        # normal (Max_Size_MB do collector e' clone de Total_MB, nao um tecto);
        # era a fonte dos "8 critical com MAXSIZE 0.00" vistos pelo owner.
        # Mantem card e modal consistentes (mesma exclusao no aggregate).
        query = f"""
        SELECT
            f.Instance, f.[Database], f.Filegroup,
            f.Total_MB, f.Used_MB, f.Free_MB, f.Percent_Used,
            ISNULL(f.Max_Size_MB, 0) AS Max_Size_MB,
            f.Growth_Type, f.Update_TS,
            CASE
                WHEN f.Percent_Used > {fg_crit_pu} THEN 'CRITICAL'
                WHEN f.Percent_Used > {fg_warn_pu} THEN 'WARNING'
                WHEN f.Percent_Used > 90 THEN 'ATTENTION'
                ELSE 'OK'
            END AS Status
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_STG AS f WITH (NOLOCK)
        WHERE f.Instance IN ('{safe_underscore}', '{safe_backslash}')
          AND f.Percent_Used > 90
          AND ISNULL(f.Growth_Type, '') <> 'UNLIMITED'
        UNION ALL
        SELECT d.Instance, d.[Database],
            d.Filegroup + CASE WHEN MAX(ISNULL(d.Volume_Free_MB, 0)) = 0
                THEN N' [UNLIMITED: disco ' + ISNULL(d.Drive, N'?') + N' SEM VISIBILIDADE de espaco livre - verificar no host]'
                ELSE N' [UNLIMITED: disco ' + ISNULL(d.Drive, N'?') + N' com '
                    + CAST(CAST(MAX(d.Volume_Free_MB) / 1024.0 AS DECIMAL(18,1)) AS NVARCHAR(20)) + N' GB livres]'
            END AS Filegroup,
            SUM(d.Size_MB) AS Total_MB, SUM(d.Used_MB) AS Used_MB,
            MAX(d.Volume_Free_MB) AS Free_MB, MAX(d.Percent_Used) AS Percent_Used,
            -1 AS Max_Size_MB, 'UNLIMITED' AS Growth_Type, MAX(d.Update_TS) AS Update_TS,
            CASE WHEN MAX(ISNULL(d.Volume_Free_MB, 0)) = 0 THEN 'WARNING'
                 WHEN MAX(ISNULL(d.Volume_Free_MB, 0)) <= {fgu_crit_mb} THEN 'CRITICAL'
                 ELSE 'WARNING' END AS Status
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DATAFILES_STG AS d WITH (NOLOCK)
        WHERE d.Instance IN ('{safe_underscore}', '{safe_backslash}')
          AND d.Is_Unlimited = 1 AND d.File_Type = 'ROWS'
          AND ISNULL(d.Volume_Free_MB, 0) <= {fgu_warn_mb}
        GROUP BY d.Instance, d.[Database], d.Filegroup, d.Drive
        ORDER BY Percent_Used DESC
        """
        filegroups = execute_intelligence_query(query, raise_on_error=False) or []

        logger.info(f"Filegroups encontrados para {instance_name}: {len(filegroups)}")

        return JSONResponse(content={
            "success": True,
            "instance": instance_name,
            "filegroups": _serialize_result(filegroups),
            "count": len(filegroups)
        })
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching filegroup details for {instance_name}")


@router.get("/thresholds", response_model=GenericResponse)
async def get_kpi_thresholds():
    """Thresholds em vigor — leitura da fonte unica (Fase 0, read-only).

    Alimenta o ecra 'Thresholds em vigor' (Configuracoes). Entradas com
    is_mirror=True documentam thresholds cuja definicao real vive em
    view SQL ou no colector V1 (inventario anti-drift) — mudar o registry
    nao muda essas camadas.
    """
    return JSONResponse(content={
        "success": True,
        "version": REGISTRY_VERSION,
        "thresholds": registry_as_list(),
    })


@router.get("/health", response_model=GenericResponse)
async def health_check():
    """Verifica se a conexão com o SQL Server Intelligence está funcionando"""
    try:
        query = "SELECT 1 AS test"
        result = execute_intelligence_query(query, raise_on_error=True)
        return JSONResponse(content={
            "status": "healthy",
            "server": INTELLIGENCE_SERVER,
            "database": INTELLIGENCE_DATABASE,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check falhou: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "server": INTELLIGENCE_SERVER,
                "database": INTELLIGENCE_DATABASE,
                "timestamp": datetime.now().isoformat()
            }
        )


@router.post("/refresh", response_model=MessageResponse)
@limiter.limit("10/minute")
async def refresh_cache(request: Request):
    """
    Força atualização do cache de KPIs.
    Útil para recuperar de falhas de conexão ou forçar reload após alterações nas views.
    """
    # Recarregar o cache nao altera dados — e so ler outra vez. Aberto a
    # qualquer sessao autenticada, incluindo viewer (decisao do owner
    # 2026-08-16); ja tem rate limit de 10/min acima.
    await _require_auth(request)
    global _dashboard_cache, _last_known_values
    
    try:
        # Limpar cache do dashboard
        with _cache_lock:
            _dashboard_cache['data'] = None
            _dashboard_cache['timestamp'] = 0
        
        # Limpar cache de valores persistentes
        for key in _last_known_values:
            _last_known_values[key] = None
        
        # Testar conexão
        test_query = "SELECT 1 AS test"
        execute_intelligence_query(test_query, raise_on_error=True)
        
        logger.info("Cache de KPIs limpo e conexão verificada com sucesso")
        
        return JSONResponse(content={
            "success": True,
            "message": "Cache limpo com sucesso. Próxima requisição buscará dados frescos do banco.",
            "server": INTELLIGENCE_SERVER,
            "database": INTELLIGENCE_DATABASE,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Erro ao fazer refresh do cache: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "Falha ao limpar cache ou reconectar ao banco",
                "timestamp": datetime.now().isoformat()
            }
        )


@router.get("/available-views", response_model=GenericResponse)
async def list_available_views():
    """Lista todas as views disponíveis no schema dbo"""
    try:
        query = f"""
        SELECT 
            TABLE_NAME as view_name,
            'View' as object_type
        FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = '{INTELLIGENCE_SCHEMA}'
        AND TABLE_NAME LIKE 'KPI_MSSQL_%'
        ORDER BY TABLE_NAME
        """
        views = execute_intelligence_query(query, raise_on_error=False)
        return JSONResponse(content={
            "success": True,
            "schema": INTELLIGENCE_SCHEMA,
            "views": views or [],
            "views_count": len(views) if views else 0
        })
    except Exception as e:
        raise safe_http_error(500, e, "listing available Intelligence views")


@router.get("/instances/{kpi_type}", response_model=GenericResponse)
async def get_problematic_instances(kpi_type: str, all: bool = Query(False, description="Retornar todas as instâncias, não apenas as problemáticas"), ok: bool = Query(False, description="Retornar instâncias OK ao invés de problemáticas")):
    """Retorna instâncias com problema para um tipo específico de KPI"""
    try:
        # Fase 1 thresholds (fix 2026-08-05): este endpoint usa _th()
        # (tempdb_usage, disk_latency) mas nunca refrescava o cache de
        # overrides -- so' o dashboard o fazia (:877-881). Em cold start, um
        # pedido a' modal antes do dashboard lia _cache={} e devolvia o default
        # do produto, ignorando o override do cliente: card e modal com
        # thresholds diferentes. Mesmo padrao e mesma guarda do bloco :877-881
        # (TTL 60s; tabela ausente = defaults).
        try:
            from api import threshold_overrides as _thr_ovr
            _thr_ovr.refresh_cache()
        except Exception:
            pass

        kpi_type = kpi_type.lower()
        instances = []
        # Sentinelas: os ramos abaixo atribuem estas duas condicionalmente e o
        # tail em :2468/:2472 consultava-as via locals() -- ver nota la'.
        total_databases = None
        env_counts = None

        if kpi_type == "db-availability" or kpi_type == "db-availability-ok":
            if all:
                # Para "all", retornar TODAS as databases (da STG, não agregado)
                # O card mostra total de databases (ex: 1.70K), então o modal deve mostrar todas
                query = f"""
                SELECT 
                    d.Instance,
                    d.[Database],
                    d.State,
                    ISNULL(e.Env, 'Undefined') AS Env
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_ACTIVE d WITH (NOLOCK)
                LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK) ON e.Instance = d.Instance
                ORDER BY d.Instance, d.[Database]
                """
                instances = execute_intelligence_query(query, raise_on_error=False) or []
                logger.debug(f"DB Availability (all=True): {len(instances)} databases retornadas da STG")

                # Calcular contagem por ENV (PRD, QLT, TST, DEV, Undefined)
                env_counts = {'PRD': 0, 'QLT': 0, 'TST': 0, 'DEV': 0, 'Undefined': 0}
                for row in instances:
                    env = (row.get('Env') or 'Undefined').upper().strip()
                    if env in ['PRD', 'PROD', 'PRODUCTION']:
                        env_counts['PRD'] += 1
                    elif env in ['QLT', 'QUAL', 'QUALITY', 'QA']:
                        env_counts['QLT'] += 1
                    elif env in ['TST', 'TEST', 'TESTING']:
                        env_counts['TST'] += 1
                    elif env in ['DEV', 'DEVELOPMENT']:
                        env_counts['DEV'] += 1
                    else:
                        env_counts['Undefined'] += 1
                logger.debug(f"DB Availability ENV counts: {env_counts}")
            elif kpi_type == "db-availability-ok":
                # Para "OK", retornar instâncias agregadas (sem problemas)
                query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WITH (NOLOCK) WHERE AbnormalCnt = 0 ORDER BY Instance"
                instances = execute_intelligence_query(query, raise_on_error=False) or []
            else:
                # Para "db-availability" (problemas), usar PROBLEM_VIEW (conforme QUERIES_KPI_DASHBOARD.sql)
                # A PROBLEM_VIEW filtra databases com problemas REAIS:
                # - Exclui mirrors RESTORING + SYNCHRONIZED (comportamento normal)
                # - Exclui AlwaysOn Secondary databases saudáveis
                # - Mostra apenas problemas reais
                query = f"""
                SELECT *
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW WITH (NOLOCK)
                ORDER BY Instance, [Database]
                """
                instances = execute_intelligence_query(query, raise_on_error=False) or []
                logger.debug(f"DB Availability (problemas): {len(instances)} registros da PROBLEM_VIEW")

                # NOTA: NÃO aplicar filtro de frescor para db-availability
                # A PROBLEM_VIEW já faz a filtragem lógica correta (exclui mirrors e AlwaysOn normais)
                # O Dashboard KPI também não usa freshness filter, então mantemos consistência
                # Freshness filters são apropriados para métricas de capacidade (disk, tlog), não para availability

                # Calcular total de databases usando COUNT(*) da DET_VIEW (mais confiável)
                query_total = f"""
                SELECT COUNT(*) as TOTAL_DATABASES
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK)
                """
                total_data = execute_intelligence_query(query_total, raise_on_error=False)
                total_databases = int(total_data[0].get('TOTAL_DATABASES', 0)) if total_data and total_data[0].get('TOTAL_DATABASES') else 0

                # Armazenar total_databases para retornar na resposta
                # (será usado no final do endpoint)
        elif kpi_type == "disk-file-system" or kpi_type == "disk-file-system-critical" or kpi_type == "disk-file-system-warning":
            # Enrich per-instance rows with drive-level aggregates for the modal card.
            # AGG_VIEW only carries Normal/Warning/Critical counts; the frontend also reads
            # Total_MB, Free_MB, Used_MB, Min_Percent_Free, Avg_Percent_Free, Drive_Count.
            # JOIN the STG base table aggregated per instance to supply those fields.
            # NOTE: timestamp must be aliased Update_TS (recognised by is_data_fresh).
            query = f"""
            SELECT agv.Instance, agv.Env, agv.Normal, agv.Warning, agv.Critical,
                   stg.Drive_Count, stg.Total_MB, stg.Free_MB, stg.Used_MB,
                   stg.Min_Percent_Free, stg.Avg_Percent_Free, stg.Update_TS
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_AGG_VIEW agv WITH (NOLOCK)
            INNER JOIN (
                SELECT Instance,
                       COUNT(*)          AS Drive_Count,
                       SUM(Total_MB)     AS Total_MB,
                       SUM(Free_MB)      AS Free_MB,
                       SUM(Used_MB)      AS Used_MB,
                       MIN(Percent_Free) AS Min_Percent_Free,
                       AVG(Percent_Free) AS Avg_Percent_Free,
                       MAX(Update_TS)    AS Update_TS
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK)
                GROUP BY Instance
            ) stg ON stg.Instance = agv.Instance
            WHERE agv.Critical > 0 OR agv.Warning > 0
            """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Apply 60-minute freshness window for disk usage (capacity metric)
            fresh_instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['capacity'])]
            
            # Filtrar por tipo específico se solicitado
            # CORRIGIDO: Warning mostra TODAS instâncias com Warning > 0
            if kpi_type == "disk-file-system-critical":
                instances = [row for row in fresh_instances if row.get('Critical', 0) > 0]
            elif kpi_type == "disk-file-system-warning":
                instances = [row for row in fresh_instances if row.get('Warning', 0) > 0]
            else:
                instances = fresh_instances
        elif kpi_type == "transaction-logs" or kpi_type == "transaction-logs-critical" or kpi_type == "transaction-logs-warning":
            # 2026-09-02 (owner: "modais mostram nomes, nao numeros"): o payload
            # passa de 1 linha por INSTANCIA (contagens) para 1 linha por BASE —
            # Instance/Database/Env/Percent_Used/Used_MB/Current_MB/Update_TS/
            # Severity/Base_Key/Last_Log_Backup_Date/Hours_Since_Log_Backup/
            # Recovery_Model/Log_Backup_Age/Threshold_*. Mesmo kpi_type (7 mapas
            # do portal chaveiam por ele). A classificacao e' a MESMA funcao
            # pura do card (tlog_usage_classes.classify_tlog): registry 85/95 +
            # override via _th, frescura 1440 dentro da funcao — o tile conta
            # instancias, o modal lista bases, e os dois numeros reconciliam.
            from api.routers.intelligence.tlog_usage_classes import TLOG_BASE_QUERY, classify_tlog
            _rows = execute_intelligence_query(
                TLOG_BASE_QUERY.format(schema=INTELLIGENCE_SCHEMA), raise_on_error=False) or []
            cls = classify_tlog(
                _rows,
                {'warning': _th('tlog_usage', 'warning'), 'critical': _th('tlog_usage', 'critical')},
                fresh_minutes=FRESHNESS_WINDOWS['capacity'],
                log_late_hours=_th('backup_delay_log', 'warning'))
            if kpi_type == "transaction-logs-critical":
                instances = cls["critical"]
            elif kpi_type == "transaction-logs-warning":
                instances = cls["warning"]
            else:
                instances = cls["critical"] + cls["warning"]
            logger.debug("TLOG modal (02/09) - reconciliation: %s", cls["reconciliation"])
        elif kpi_type == "always-on":
            # Consultar STG directamente — uma linha por (instancia, base), nao por AG.
            # Permite mostrar multiplas instancias do mesmo AG (ex: Primary + Secondary ambos unhealthy).
            # 2026-08-07 (regra owner "nome, nao numero"): +[Database] — a STG ja tinha
            # granularidade por base mas a coluna nunca era seleccionada, pelo que o modal
            # so conseguia dizer QUE servidor estava mal, nunca QUAL base.
            # NOTA: nao usar a coluna s.Problem_Reason da STG — o collector escreve-a com
            # logica antiga que trata o lado vazio da replica (normal) como avaria, ficando
            # falso positivo em 100% das linhas. O Problem_Reasons abaixo e' recalculado aqui.
            query = f"""
            SELECT
                s.AgName,
                s.Instance,
                s.[Database],
                ISNULL(e.Env, 'Undefined') AS Env,
                s.Pri_Synch_Health,
                s.Sec_Synch_Health,
                s.Pri_Synch_State,
                s.Sec_Synch_State,
                s.Pri_Is_Suspended,
                s.Sec_Is_Suspended,
                s.Update_TS,
                RTRIM(LTRIM(
                    CASE WHEN (s.Pri_Synch_Health <> 'HEALTHY' AND s.Pri_Synch_Health IS NOT NULL AND s.Pri_Synch_Health <> '')
                              OR (s.Sec_Synch_Health <> 'HEALTHY' AND s.Sec_Synch_Health IS NOT NULL AND s.Sec_Synch_Health <> '')
                         THEN 'Health Problem; ' ELSE '' END +
                    CASE WHEN s.Pri_Is_Suspended = 1 OR s.Sec_Is_Suspended = 1 THEN 'Suspended; ' ELSE '' END +
                    CASE WHEN (s.Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Pri_Synch_State IS NOT NULL)
                              OR (s.Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Sec_Synch_State IS NOT NULL)
                         THEN 'Sync State; ' ELSE '' END
                )) AS Problem_Reasons
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG s WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = s.Instance
            WHERE s.Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
            AND (
                (s.Pri_Synch_Health <> 'HEALTHY' AND s.Pri_Synch_Health IS NOT NULL AND s.Pri_Synch_Health <> '')
                OR (s.Sec_Synch_Health <> 'HEALTHY' AND s.Sec_Synch_Health IS NOT NULL AND s.Sec_Synch_Health <> '')
                OR (s.Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Pri_Synch_State IS NOT NULL)
                OR (s.Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND s.Sec_Synch_State IS NOT NULL)
                OR s.Pri_Is_Suspended = 1
                OR s.Sec_Is_Suspended = 1
            )
            ORDER BY s.Instance, s.[Database]
            """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Remover trailing '; ' do Problem_Reasons
            for row in all_instances:
                reasons = row.get('Problem_Reasons', '') or ''
                if reasons.endswith('; '):
                    row['Problem_Reasons'] = reasons[:-2]
            # Freshness ja aplicada na query SQL via WHERE clause
            instances = all_instances
        elif kpi_type == "filegroup-usage" or kpi_type == "filegroup-usage-critical" or kpi_type == "filegroup-usage-warning":
            # MAXSIZE-aware: mesma lógica CTE do dashboard para consistência card ↔ modal
            # Fase 1.5 (2026-08-13): thresholds do registry+overrides (% livre
            # invertido p/ Percent_Used; GB do ramo UNLIMITED em MB). Cache ja
            # refrescado no topo da funcao (:1174-1178).
            fg_crit_pu = 100 - float(_th('filegroup_free_pct', 'critical'))
            fg_warn_pu = 100 - float(_th('filegroup_free_pct', 'warning'))
            fgu_warn_mb = float(_th('filegroup_unlimited_free_gb', 'warning')) * 1024
            fgu_crit_mb = float(_th('filegroup_unlimited_free_gb', 'critical')) * 1024
            query = f"""
            ;WITH fg_effective AS (
                SELECT
                    f.Instance,
                    ISNULL(e.Env, 'Undefined') AS Env,
                    CASE
                        WHEN ISNULL(f.Growth_Type, '') = 'UNLIMITED' THEN 0
                        WHEN ISNULL(f.Max_Size_MB, 0) <= 0 THEN 0
                        WHEN f.Max_Size_MB > f.Total_MB AND f.Max_Size_MB > 0
                            THEN CAST(f.Used_MB * 100.0 / f.Max_Size_MB AS DECIMAL(5,2))
                        ELSE f.Percent_Used
                    END AS Effective_Pct,
                    f.Update_TS
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
                LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = f.Instance
            )
            SELECT
                Instance,
                Env,
                SUM(CASE WHEN Effective_Pct >= 90 AND Effective_Pct < {fg_warn_pu} THEN 1 ELSE 0 END) AS Attention,
                SUM(CASE WHEN Effective_Pct >= {fg_warn_pu} AND Effective_Pct < {fg_crit_pu} THEN 1 ELSE 0 END) AS Warning,
                SUM(CASE WHEN Effective_Pct >= {fg_crit_pu} THEN 1 ELSE 0 END) AS Critical,
                MAX(Update_TS) AS Last_Check
            FROM fg_effective
            GROUP BY Instance, Env
            HAVING SUM(CASE WHEN Effective_Pct >= 90 THEN 1 ELSE 0 END) > 0
            """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []

            # Fase 2 (2026-07-27): merge do ramo UNLIMITED disk-bound (mesma
            # regra do aggregate em helpers.collect_filegroup_usage; limiares
            # configuraveis desde a Fase 1.5; Volume_Free_MB=0 = desconhecido).
            # Mantem drill consistente com o card.
            disk_query = f"""
            ;WITH vol AS (
                SELECT d.Instance, d.Drive, MIN(ISNULL(d.Volume_Free_MB, 0)) AS Vol_Free_MB
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DATAFILES_STG d WITH (NOLOCK)
                WHERE d.Is_Unlimited = 1 AND d.File_Type = 'ROWS'
                GROUP BY d.Instance, d.Drive
            )
            SELECT v.Instance, ISNULL(e.Env, 'Undefined') AS Env,
                0 AS Attention,
                SUM(CASE WHEN v.Vol_Free_MB = 0 OR (v.Vol_Free_MB > {fgu_crit_mb} AND v.Vol_Free_MB <= {fgu_warn_mb}) THEN 1 ELSE 0 END) AS Warning,
                SUM(CASE WHEN v.Vol_Free_MB > 0 AND v.Vol_Free_MB <= {fgu_crit_mb} THEN 1 ELSE 0 END) AS Critical,
                MAX(GETDATE()) AS Last_Check
            FROM vol v
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = v.Instance
            GROUP BY v.Instance, e.Env
            HAVING SUM(CASE WHEN v.Vol_Free_MB <= {fgu_warn_mb} THEN 1 ELSE 0 END) > 0
            """
            disk_rows = execute_intelligence_query(disk_query, raise_on_error=False) or []
            if disk_rows:
                by_inst = {r.get('Instance'): r for r in all_instances}
                for dr in disk_rows:
                    row = by_inst.get(dr.get('Instance'))
                    if row:
                        row['Critical'] = (row.get('Critical', 0) or 0) + (dr.get('Critical', 0) or 0)
                        row['Warning'] = (row.get('Warning', 0) or 0) + (dr.get('Warning', 0) or 0)
                    else:
                        all_instances.append(dr)

            # Filtrar por tipo específico
            if kpi_type == "filegroup-usage-critical":
                instances = [row for row in all_instances if row.get('Critical', 0) > 0]
            elif kpi_type == "filegroup-usage-warning":
                instances = [row for row in all_instances if row.get('Warning', 0) > 0]
            else:
                instances = all_instances
        elif kpi_type == "blocked-sessions":
            query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK) WHERE Blocked_Count > 0"
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Apply 5-minute freshness window for blocked sessions (real-time events)
            instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['real_time'])]
        elif kpi_type == "blocked-users":
            query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK) WHERE Blocked_Count > 0"
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Apply 5-minute freshness window for blocked users (real-time events)
            instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['real_time'])]
        elif kpi_type == "service-status" or kpi_type == "services-down":
            # Instâncias com serviços SQL down (engine, agent, browser, etc.)
            query = f"""
            SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
            WHERE Services_Down_Count > 0
            """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Apply 15-minute freshness window for service status
            instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['services'])]
        elif kpi_type == "instance-availability":
            # Se for para mostrar instâncias OK (parâmetro ok=true), buscar da STG
            if ok:
                # Buscar instâncias disponíveis da STG com informações detalhadas
                # Usar subquery para pegar apenas o registro mais recente de cada instância
                # FIND-20260811-102: o Env vinha de CASE LIKE no nome (classificava
                # mal 4 servidores da frota — medido 2026-08-07). Passa a INST_ENVS,
                # o MESMO metodo do card (helpers.collect_instance_availability) —
                # aqui a chave E' Instance, o padrao aplica-se directamente.
                query_ok = f"""
                SELECT
                    s.Instance,
                    s.Is_Available,
                    s.Update_TS,
                    ISNULL(e.Env, 'Undefined') AS Env
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS s WITH (NOLOCK)
            INNER JOIN (
                    SELECT Instance, MAX(Update_TS) as MaxUpdate
                    FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WITH (NOLOCK)
                    GROUP BY Instance
                ) latest ON s.Instance = latest.Instance AND s.Update_TS = latest.MaxUpdate
                LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
                    ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(s.Instance)))
                WHERE s.Is_Available = 1
                ORDER BY s.Instance
                """
                instances = execute_intelligence_query(query_ok, raise_on_error=False) or []
                logger.debug(f"Instance Availability OK: {len(instances)} instâncias disponíveis")
            else:
                # Instâncias OFF = APENAS onde PING FALHOU (Ping_OK = 0)
                # Buscar diretamente da view de ping offline
                offline_query = f"""
                SELECT
                    Instance,
                    Server_Name,
                    Env,
                    Diagnosis,
                    Diagnosis_Desc,
                    Ping_OK,
                    Ping_Status,
                    Ping_Message,
                    Services_Down,
                    Last_Event_Time,
                    Minutes_Since_Last_Event,
                    Severity,
                    [State]
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
                WHERE Ping_OK = 0
                """
                offline_data = execute_intelligence_query(offline_query, raise_on_error=False) or []

                off_instances = []
                for row in offline_data:
                    off_instances.append({
                        'Instance': row.get('Instance', ''),
                        'Server_Name': row.get('Server_Name', ''),
                        'Env': row.get('Env', 'Undefined'),
                        'Is_Available': 0,
                        'diagnosis': row.get('Diagnosis', 'offline'),
                        'diagnosis_desc': row.get('Diagnosis_Desc', 'Servidor Offline'),
                        'ping_ok': row.get('Ping_OK', 0),
                        'ping_status': row.get('Ping_Status', 'FAIL'),
                        'ping_message': row.get('Ping_Message', ''),
                        'services_down': row.get('Services_Down', ''),
                        'event_time': row.get('Last_Event_Time'),
                        'minutes_since_event': row.get('Minutes_Since_Last_Event', 0),
                        'severity': row.get('Severity', 'CRITICAL'),
                        'status': row.get('State', 'CRITICAL')
                    })

                # Se for all=true, buscar todas as instâncias da AGG_VIEW
                if all:
                    query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW WITH (NOLOCK)"
                    all_instances = execute_intelligence_query(query, raise_on_error=False) or []
                    fresh_all_instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['services'])]
                    instances = fresh_all_instances
                else:
                    instances = off_instances

                logger.debug(f"Instance Availability Modal: {len(off_instances)} instâncias com ping offline")
        elif kpi_type == "backup-no-checksum":
            # Wave O (2026-05-21): SQL aggregation por (Instance, Database) para evitar
            # browser RangeError ao render 200k+ backupset entries individuais.
            # Silent corruption risk e' actionable por DB/instancia, nao por backup
            # individual (`SQLPRD01: 3450 backups sem checksum em DB_X` e' mais util
            # que 3450 linhas individuais identicas). SQL GROUP BY reduz ~200k -> ~200 rows.
            query = f"""
            SELECT
                f.Instance,
                f.[Database],
                COUNT(*) AS Total_Count,
                SUM(CASE WHEN f.Failure_Source = 'no_checksum' THEN 1 ELSE 0 END) AS No_Checksum_Count,
                SUM(CASE WHEN f.Failure_Source = 'is_damaged' THEN 1 ELSE 0 END) AS Is_Damaged_Count,
                MIN(f.Run_Datetime) AS First_Seen,
                MAX(f.Run_Datetime) AS Last_Seen,
                ISNULL(MAX(e.Env), 'Undefined') AS Env,
                MAX(f.Update_TS) AS Update_TS,
                '(silent corruption)' AS Job_Name,
                CAST(NULL AS UNIQUEIDENTIFIER) AS Job_Id,
                CAST(0 AS INT) AS Step_Id,
                CAST(NULL AS NVARCHAR(256)) AS Step_Name,
                CAST(0 AS TINYINT) AS Run_Status,
                CAST(NULL AS INT) AS Run_Duration_Sec
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG AS f WITH (NOLOCK)
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(f.Instance)))
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
                ON a.Instance = f.Instance
            WHERE ISNULL(a.Is_Available, 1) = 1
              AND f.Failure_Source IN ('no_checksum', 'is_damaged')
              -- Wave R+11 REVERTED (2026-05-25): filter FULL+DIFF requeria
              -- coluna Backup_Type_Classified inexistente em producao. Query
              -- falhava com Msg 207 silenciosamente (raise_on_error=False).
              -- Ver Wave R+11.2 plan: V1 collector update + ALTER TABLE.
              -- Wave W (2026-06-12, FIND-20260612-101): janela 7d removida — o card
              -- no_checksum_count nao filtra data (ceiling 14d STG); sem isto o
              -- "X de X" do modal divergia do count do card.
            GROUP BY f.Instance, f.[Database]
            ORDER BY COUNT(*) DESC
            """
            raw_rows = execute_intelligence_query(query, raise_on_error=False) or []

            # Env normalize + synthesize Message human-readable para card render
            for row in raw_rows:
                env = row.get('Env', 'Undefined') or 'Undefined'
                if env == 'Undefined':
                    inst_name = (row.get('Instance', '') or '').upper()
                    if 'PRD' in inst_name or 'PROD' in inst_name:
                        env = 'PRD'
                    elif 'QLT' in inst_name or 'QUAL' in inst_name:
                        env = 'QLT'
                    elif 'TST' in inst_name or 'TEST' in inst_name or 'DEV' in inst_name:
                        env = 'TST'
                    row['Env'] = env
                total = row.get('Total_Count', 0)
                nc = row.get('No_Checksum_Count', 0)
                dmg = row.get('Is_Damaged_Count', 0)
                last_seen = row.get('Last_Seen', '')
                parts = []
                if nc > 0:
                    parts.append(f"{nc} sem checksum")
                if dmg > 0:
                    parts.append(f"{dmg} damaged")
                row['Message'] = f"{total} backups silent corruption risk ({' + '.join(parts)}) - ultimo: {last_seen}"
                # Last_Seen serve como Run_Datetime para sort/display consistency
                row['Run_Datetime'] = row.get('Last_Seen')
                row['Failure_Source'] = 'aggregated'

            instances = raw_rows
            logger.debug(f"backup-no-checksum Modal (Wave O aggregated) - {len(raw_rows)} (Instance,Database) groups")

        elif kpi_type in ("backup-failed", "backup-log-failed"):
            # Wave O (2026-05-21): 2 modais com mesma query base + filter Python.
            # Wave W (2026-06-12, FIND-20260612-101): modais alinhados a semantica
            # dos CARDS (Wave R+13): unresolved-only, SEM janelas 7d/24h legacy —
            # ceiling natural = janela do collector (30d desde Fase 2 2026-08-21;
            # era 7d). Paridade exacta com helpers.py collect_backup_status
            # (backup_latest lookup + skip recovered via Resolved_By_Success_TS).
            # backup-no-checksum tem seu proprio elif acima (SQL GROUP BY para evitar
            # browser RangeError em 200k+ rows).
            # Classifier via helpers.classify_backup_type (Job_Name pattern, 100% coverage validado).
            from api.routers.intelligence.helpers import classify_backup_type
            from datetime import datetime as _dt

            # 2026-08-17 (revisao owner): "quando um backup falha nao sabemos a janela
            # do proximo". LEFT JOIN a KPI_MSSQL_AGENT_JOBS_STG (collector V1
            # collect_agent_jobs, 5/5 min; tabela unica sem BLUE/GREEN,
            # FIND-20260506-001) por (JobId, Instance). Sem DDL — colunas ja' existem.
            # OBRIGATORIO (veto V1-Intel): AGENT_JOBS_STG.Instance e' @@SERVERNAME cru
            # (backslash) e EXEC_FAILURES.Instance e' normalizado a underscore pelo
            # BaseCollector.transform -> normalizar no ON, senao o JOIN da' sempre NULL.
            # So' linhas Failure_Source='sysjobhistory' tem Job_Id real (as outras
            # trazem o GUID sentinela 0) — o WHERE abaixo ja' garante isso.
            # Semantica dos campos (portal decide o texto, nunca inventar data):
            #   Job_Enabled=0            -> "job desabilitado, nao corre sozinho"
            #   Has_Schedule=0           -> "sem agendamento no Agent" (pode ser TDP/externo)
            #   Next_Run_Date < agora    -> "devia ter corrido e nao correu" (Agent parado?)
            #   Jobs_Snapshot_TS velho   -> stale (collector parado), NAO 'sem agendamento'
            #   JobId NULL no JOIN       -> "sem informacao (snapshot)"
            query = f"""
            SELECT
                f.Instance, f.[Database], f.Job_Name, f.Job_Id,
                f.Step_Id, f.Step_Name, f.Run_Status, f.Run_Datetime,
                f.Run_Duration_Sec, f.Message, f.Failure_Source,
                f.Resolved_By_Success_TS,
                ISNULL(e.Env, 'Undefined') AS Env,
                f.Update_TS,
                aj.NextRunDate      AS Next_Run_Date,
                aj.HasSchedule      AS Has_Schedule,
                aj.IsEnabled        AS Job_Enabled,
                aj.LastRunStatus    AS Job_Last_Run_Status,
                aj.LastRunDate      AS Job_Last_Run_Date,
                aj.Update_TS        AS Jobs_Snapshot_TS,
                CASE WHEN aj.JobId IS NULL THEN 1 ELSE 0 END AS Job_Missing_In_Snapshot
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG AS f WITH (NOLOCK)
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(f.Instance)))
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
                ON a.Instance = f.Instance
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_AGENT_JOBS_STG AS aj WITH (NOLOCK)
                ON aj.JobId = f.Job_Id
               AND LTRIM(RTRIM(UPPER(REPLACE(aj.Instance, '\\', '_')))) = LTRIM(RTRIM(UPPER(f.Instance)))
            WHERE ISNULL(a.Is_Available, 1) = 1
              AND f.Failure_Source = 'sysjobhistory'
            ORDER BY f.Run_Datetime DESC
            """
            raw_rows = execute_intelligence_query(query, raise_on_error=False) or []

            # Recovery lookup — paridade exacta com helpers.py:1305-1330 (card).
            # Qualquer divergencia aqui re-cria a discrepancia card-vs-modal.
            backup_recovery_query = f"""
            SELECT Instance, [Database], Backup_Type,
                   MAX(Last_Backup_Date) AS Last_Backup_Date
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
            WHERE Last_Backup_Date IS NOT NULL
            GROUP BY Instance, [Database], Backup_Type
            """
            _bl_rows = execute_intelligence_query(backup_recovery_query, raise_on_error=False) or []
            backup_latest = {}
            _type_map = {'FULL': 'FULL', 'D': 'FULL', 'DIFF': 'DIFF', 'I': 'DIFF', 'LOG': 'LOG', 'L': 'LOG'}
            for _b in _bl_rows:
                _inst = (_b.get('Instance', '') or '').upper()
                _db = (_b.get('Database', '') or '').upper()
                _bt = _type_map.get((_b.get('Backup_Type', '') or '').upper())
                _ldt = _b.get('Last_Backup_Date')
                if isinstance(_ldt, str) and _ldt:
                    try:
                        _ldt = _dt.fromisoformat(_ldt)
                    except ValueError:
                        _ldt = None
                if _bt and isinstance(_ldt, _dt):
                    _key = (_inst, _db, _bt)
                    if _key not in backup_latest or backup_latest[_key] < _ldt:
                        backup_latest[_key] = _ldt

            def _parse_run_dt(val):
                if isinstance(val, _dt):
                    return val
                if isinstance(val, str) and val:
                    try:
                        return _dt.fromisoformat(val)
                    except ValueError:
                        return None
                return None

            # Fase 2 (2026-08-21): o veredicto Recovered vem do COLLECTOR
            # (f.Resolved_By_Success_TS na propria row — OUTER APPLY a
            # sysjobhistory, historico completo). O check de staleness 15 min
            # da Fase 1 saiu: nao ha snapshot separado que possa estar stale
            # (mesma frescura da falha por construcao). FAIL-OPEN estrutural:
            # sem evidencia de sucesso => NULL => "AINDA EM FALTA".
            # O JOIN a AGENT_JOBS_STG MANTEM-SE apenas pelos campos de
            # agendamento de 17/08 (Next_Run_Date / Has_Schedule / Job_Enabled
            # / Jobs_Snapshot_TS — portal decide o texto por estes campos).

            filtered = []
            for row in raw_rows:
                # Env normalize (fallback se KPI_MSSQL_INST_ENVS sem match)
                env = row.get('Env', 'Undefined') or 'Undefined'
                if env == 'Undefined':
                    inst_name = (row.get('Instance', '') or '').upper()
                    if 'PRD' in inst_name or 'PROD' in inst_name:
                        env = 'PRD'
                    elif 'QLT' in inst_name or 'QUAL' in inst_name:
                        env = 'QLT'
                    elif 'TST' in inst_name or 'TEST' in inst_name or 'DEV' in inst_name:
                        env = 'TST'
                    row['Env'] = env

                backup_type = classify_backup_type(row.get('Job_Name', '') or '')
                row['Backup_Type_Classified'] = backup_type

                if kpi_type == "backup-log-failed":
                    if backup_type != 'LOG':
                        continue
                else:
                    # backup-failed = FULL+DIFF+OTHER sysjobhistory
                    if backup_type == 'LOG':
                        continue

                # Unresolved-check (Wave R+13, identico ao card): skip se backup
                # posterior completou para mesmo (Instance, Database, Type).
                # Conservativo: Database NULL ou type OTHER nao filtram (show).
                db_norm = (row.get('Database', '') or '').upper()
                failure_dt = _parse_run_dt(row.get('Run_Datetime'))
                if db_norm and failure_dt is not None and backup_type in ('FULL', 'DIFF', 'LOG'):
                    rec_key = ((row.get('Instance', '') or '').upper(), db_norm, backup_type)
                    last_bkp = backup_latest.get(rec_key)
                    if last_bkp and last_bkp > failure_dt:
                        continue  # recovered — backup posterior teve sucesso

                # Fase 2 (2026-08-21): recuperacao lida da propria row (collector).
                # Ao contrario do card (que exclui da contagem), o modal MANTEM a
                # linha com Recovered=1 — badge "Recuperado" no portal, nunca
                # desaparecimento silencioso (council 21/08). Paridade: contagem
                # do card == linhas Recovered=0 deste modal (mesma coluna fonte).
                _rec_at = _parse_run_dt(row.get('Resolved_By_Success_TS'))
                row['Recovered'] = 1 if _rec_at is not None else 0
                row['Recovered_At'] = _rec_at.isoformat() if _rec_at is not None else None
                # Fase 2: sempre 0 — veredicto embutido na row da falha, nao ha
                # snapshot separado stale. Campo mantido por retrocompat do
                # portal (_kpiBackupRecoveredHtml suprime badge quando 1).
                row['Jobs_Snapshot_Stale'] = 0

                filtered.append(row)

            instances = filtered
            _n_rec = sum(1 for _r in filtered if _r.get('Recovered'))
            logger.debug(
                f"{kpi_type} Modal (Fase 2 collector-side) - {len(filtered)} de {len(raw_rows)} raw rows, "
                f"{_n_rec} recuperadas")

        elif kpi_type == "backup-delayed":
            # Wave D3 (2026-05-13): refactor para gap RPO threshold-based per tipo
            # Thresholds: FULL warning 120h/critical 168h, DIFF 24h/30h, LOG 1h/2h.
            # Delayed inclui AMBOS warning e critical (qualquer gap > warning threshold).
            # Wave M.2 (2026-05-21): redirect modal de KPI_MSSQL_BACKUPS_STG (per-instance,
            # 712 rows mostrando duplicados pos-failover) para vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE
            # (AG-consolidated, alinha com tile que mostra 270). Wave M.1 ja redirected o
            # tile em helpers.py:1245; esta query da modal precisava do mesmo fix para
            # consistencia tile vs modal.
            from datetime import datetime, timedelta
            query = f"""
            SELECT b.*, ISNULL(e.Env, 'Undefined') AS Env
            FROM {INTELLIGENCE_SCHEMA}.vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE AS b WITH (NOLOCK)
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(b.Instance)))
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
                ON a.Instance = b.Instance
            INNER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_STG AS av WITH (NOLOCK)
                ON av.Instance = b.Instance
               AND av.[Database] = b.[Database]
            WHERE ISNULL(a.Is_Available, 1) = 1
              AND av.Is_Available = 1
              AND b.Update_TS >= DATEADD(DAY, -2, GETDATE())
            """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            logger.debug(f"Backup Delayed Modal (Wave M.2 AG-consolidated) - Total registros: {len(all_instances)}")

            # 2026-08-06: era um dict hardcoded (120/168, 24/30, 1/2) enquanto o
            # card equivalente (helpers.collect_backup_status) ja lia do registry
            # via _th() desde a Fase 0 (04/08). Assim que um cliente gravasse um
            # override na Fase 1, card e modal passavam a discordar em silencio --
            # exactamente a classe de drift que o registry existe para matar.
            from api.threshold_overrides import resolve as _thr
            THRESHOLDS = {
                'FULL': {'warning_h': _thr('backup_delay_full', 'warning'),
                         'critical_h': _thr('backup_delay_full', 'critical')},
                'DIFF': {'warning_h': _thr('backup_delay_diff', 'warning'),
                         'critical_h': _thr('backup_delay_diff', 'critical')},
                'LOG':  {'warning_h': _thr('backup_delay_log', 'warning'),
                         'critical_h': _thr('backup_delay_log', 'critical')},
            }
            # Council 2026-09-01 (R5): MESMA funcao de classificacao do card —
            # o loop duplicado que vivia aqui foi retirado (o bug de coerencia
            # tile-vs-painel de 31/08 nao se repete). O modal mostra TODAS as
            # classes, anotadas (persona: nada desaparece, tudo navegavel):
            # actionable (critical/warning) + diff_schedule_stopped (warning)
            # + ag_system_gap (policy) + chain_reset (info).
            from api.routers.intelligence.backup_delayed_classes import (
                classify_delayed, build_ag_map, AG_MAP_QUERY)
            _ag_rows = execute_intelligence_query(
                AG_MAP_QUERY.format(schema=INTELLIGENCE_SCHEMA), raise_on_error=False) or []
            cls = classify_delayed(all_instances, THRESHOLDS, ag_map=build_ag_map(_ag_rows))
            instances = (cls["actionable_critical"] + cls["actionable_warning"]
                         + cls["diff_schedule_stopped"] + cls["ag_system_gap"]
                         + cls["chain_reset"])
            logger.debug(
                "Backup Delayed Modal (council 01/09) - reconciliation: %s",
                cls["reconciliation"])

        elif kpi_type == "backup-jobs-disabled":
            # Wave D3 (2026-05-13): novo endpoint para visibility de jobs SQL Agent desactivados
            # Consume KPI_MSSQL_BACKUP_JOBS_DISABLED_STG (snapshot mode)
            # Edge case que motivou Wave D: job disabled e esquecido NAO gera failure mas gera gap.
            query = f"""
            SELECT
                jd.Instance, jd.Job_Id, jd.Job_Name, jd.Job_Category,
                jd.Date_Last_Modified, jd.Approx_Disabled_Since,
                jd.Last_Run_Date, jd.Last_Run_Status, jd.Owner_Login,
                ISNULL(e.Env, 'Undefined') AS Env,
                jd.Update_TS
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG AS jd WITH (NOLOCK)
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(jd.Instance)))
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
                ON a.Instance = jd.Instance
            WHERE ISNULL(a.Is_Available, 1) = 1
            ORDER BY jd.Approx_Disabled_Since DESC
            """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            for row in all_instances:
                env = row.get('Env', 'Undefined') or 'Undefined'
                if env == 'Undefined':
                    inst_name = (row.get('Instance', '') or '').upper()
                    if 'PRD' in inst_name or 'PROD' in inst_name:
                        env = 'PRD'
                    elif 'QLT' in inst_name or 'QUAL' in inst_name:
                        env = 'QLT'
                    elif 'TST' in inst_name or 'TEST' in inst_name or 'DEV' in inst_name:
                        env = 'TST'
                    row['Env'] = env
            instances = all_instances
            logger.debug(f"Backup Jobs Disabled Modal (Wave D3) - {len(instances)} rows")
        elif kpi_type == "backup-ag-system-gap":
            # Wave M.4.b (2026-05-29): surface dedicada FIND-20260529-102.
            # Lista system DBs (master/model/msdb/tempdb/DBA_RESOURCE_DB) em nos AG
            # com gap de backup. Consume view nova vw_KPI_MSSQL_BACKUPS_AG_SYSTEM_GAP
            # (V1 DDL Wave M.4.a, validado v1-intel-specialist 2026-05-29).
            # Standalones nao aparecem (correcto -- view filtra por AG topology).
            query = f"""
            SELECT AgName, Instance, [Database], Backup_Type,
                   Last_Backup_Date, Hours_Since_Backup, Update_TS, Severity
            FROM {INTELLIGENCE_SCHEMA}.vw_KPI_MSSQL_BACKUPS_AG_SYSTEM_GAP WITH (NOLOCK)
            WHERE Severity IN ('CRITICAL','WARNING')
            ORDER BY Hours_Since_Backup DESC
            """
            instances = execute_intelligence_query(query, raise_on_error=False) or []
            logger.debug(f"Backup AG System Gap Modal (Wave M.4.b) - {len(instances)} rows")
        elif kpi_type == "mirroring" or kpi_type == "mirroring-issues" or kpi_type == "mirroring-total":
            # Mirroring Status - Conforme QUERIES_KPI_DASHBOARD.sql:
            # - Total: KPI_MSSQL_MIRRORING_STATUS_ACTIVE
            # - Problemas: KPI_MSSQL_MIRRORING_STATUS_DET_VIEW
            # 2026-08-31 (owner + v1-intel GO): +Safety_Level (recolhido desde
            # sempre, omitido aqui), +Witness_State, +Log_Send_Queue_KB,
            # +Redo_Queue_KB (MIGRATION_MIRRORING_WITNESS_QUEUES.sql). ORDEM DE
            # DEPLOY: migration -> restart collector V1 -> 1 ciclo -> restart
            # V33; este SELECT antes da migration = Msg 207 -> modal vazio
            # (raise_on_error=False). Filas NULL = sem dado (nunca 0).
            # 2026-09-01 (Fase A, v1-intel GO-com-condicoes): +Data_MB via LEFT JOIN
            # a agregado do DATAFILES (VIEW confirmada viva na BD; verificacao
            # bloqueante da consulta passou: type=VIEW, Update_TS fresco).
            # LTRIM/RTRIM/UPPER nos dois lados (condicao 2); Data_TS exposto para
            # o tooltip de honestidade (DATAFILES cadencia 15 min vs mirroring 5).
            # Fail-open: sem match -> Data_MB NULL -> frontend nao mostra veredito.
            _df_join = f"""
                LEFT OUTER JOIN (
                    SELECT LTRIM(RTRIM(UPPER(Instance))) AS Instance_N,
                           LTRIM(RTRIM(UPPER([Database]))) AS Database_N,
                           SUM(Size_MB) AS Data_MB, MAX(Update_TS) AS Data_TS
                    FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK)
                    WHERE File_Type = 'ROWS'
                    GROUP BY LTRIM(RTRIM(UPPER(Instance))), LTRIM(RTRIM(UPPER([Database])))
                ) AS df
                    ON df.Instance_N = LTRIM(RTRIM(UPPER(m.Instance)))
                   AND df.Database_N = LTRIM(RTRIM(UPPER(m.[Database])))"""
            if kpi_type == "mirroring-total":
                query = f"""
                SELECT m.Instance, m.[Database], m.Mirroring_Role, m.Mirroring_State, m.Database_State,
                       m.Safety_Level, m.Partner_Instance, m.Witness_State,
                       m.Log_Send_Queue_KB, m.Redo_Queue_KB, df.Data_MB, df.Data_TS, m.Env, m.Update_TS
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_MIRRORING_STATUS_ACTIVE AS m WITH (NOLOCK)
                {_df_join}
                ORDER BY m.Instance, m.[Database]
                """
            else:
                # 2026-09-01 (Fase B, v1-intel GO + desvio ACEITE): serie temporal
                # via WDB_MIRRORING_QUEUE_HIST (retencao 7d no collector).
                # sus = inicio do run CONTIGUO do estado actual (quebra = ultima
                # linha com estado diferente); Hist_Oldest_TS para o frontend
                # mostrar "ha pelo menos" quando o inicio real saiu da janela de
                # retencao (honestidade de datas — condicao 3 do v1-intel).
                # tr = ponto mais antigo das ultimas 24h p/ taxa MB/h; sem 2
                # pontos o frontend mostra "a monitorizar", nunca ETA fabricado.
                # DEPLOY: migration da HIST ANTES do restart V33 (Msg 208 -> modal
                # vazio, mesma armadilha de ordem de 31/08).
                query = f"""
                SELECT m.Instance, m.[Database], m.Mirroring_Role, m.Mirroring_State, m.Database_State,
                       m.Safety_Level, m.Partner_Instance, m.Witness_State,
                       m.Log_Send_Queue_KB, m.Redo_Queue_KB, df.Data_MB, df.Data_TS,
                       sus.Suspended_Since, old.Hist_Oldest_TS, tr.Trend_TS, tr.Trend_LSQ,
                       m.Problem_Reason, m.Env, m.Update_TS
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_MIRRORING_STATUS_DET_VIEW AS m WITH (NOLOCK)
                {_df_join}
                OUTER APPLY (
                    SELECT MIN(h.Update_TS) AS Suspended_Since
                    FROM {INTELLIGENCE_SCHEMA}.WDB_MIRRORING_QUEUE_HIST h WITH (NOLOCK)
                    WHERE h.Instance = m.Instance AND h.[Database] = m.[Database]
                      AND ISNULL(h.Mirroring_State,'') = ISNULL(m.Mirroring_State,'')
                      AND h.Update_TS > ISNULL((
                            SELECT MAX(h2.Update_TS)
                            FROM {INTELLIGENCE_SCHEMA}.WDB_MIRRORING_QUEUE_HIST h2 WITH (NOLOCK)
                            WHERE h2.Instance = m.Instance AND h2.[Database] = m.[Database]
                              AND ISNULL(h2.Mirroring_State,'') <> ISNULL(m.Mirroring_State,'')
                          ), '1900-01-01')
                ) AS sus
                OUTER APPLY (
                    SELECT MIN(h.Update_TS) AS Hist_Oldest_TS
                    FROM {INTELLIGENCE_SCHEMA}.WDB_MIRRORING_QUEUE_HIST h WITH (NOLOCK)
                    WHERE h.Instance = m.Instance AND h.[Database] = m.[Database]
                ) AS old
                OUTER APPLY (
                    SELECT TOP 1 h.Update_TS AS Trend_TS, h.Log_Send_Queue_KB AS Trend_LSQ
                    FROM {INTELLIGENCE_SCHEMA}.WDB_MIRRORING_QUEUE_HIST h WITH (NOLOCK)
                    WHERE h.Instance = m.Instance AND h.[Database] = m.[Database]
                      AND h.Log_Send_Queue_KB IS NOT NULL
                      AND h.Update_TS >= DATEADD(HOUR, -24, GETDATE())
                    ORDER BY h.Update_TS ASC
                ) AS tr
                ORDER BY m.Env, m.Instance, m.[Database]
                """
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Mirroring: SEM filtro de freshness pois dados sao coletados com pouca frequencia
            instances = all_instances
        elif kpi_type == "deadlocks":
            # Janela 24h — CRITICAL primeiro, depois por Deadlock_Count DESC.
            # Coluna Severity numerica e crescente (1=INFO, 3=CRITICAL) — usar
            # State textual via CASE para evitar confusao de mapping.
            # Wave W (2026-06-12, FIND-20260612-101): + JOIN Is_Available (paridade
            # com o card, que exclui servers down — deadlock em server down e historico).
            # 2026-07-27 (regra owner "nome, nao numero"): +Databases_List/Objects_List
            # com os NOMES distintos vindos da DET_VIEW (24h) — STUFF/FOR XML por
            # causa do piso SQL 2014 (sem STRING_AGG). Contagens mantem-se para
            # quantidade; a UI mostra os nomes.
            query = f"""
            SELECT d.*,
                STUFF((SELECT DISTINCT ', ' + dv.Database_Name
                       FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_DET_VIEW AS dv WITH (NOLOCK)
                       WHERE dv.Instance = d.Instance
                         AND dv.Database_Name IS NOT NULL AND LTRIM(RTRIM(dv.Database_Name)) <> ''
                       FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS Databases_List,
                STUFF((SELECT DISTINCT ', ' + dv.Object_Name
                       FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_DET_VIEW AS dv WITH (NOLOCK)
                       WHERE dv.Instance = d.Instance
                         AND dv.Object_Name IS NOT NULL AND LTRIM(RTRIM(dv.Object_Name)) <> ''
                       FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS Objects_List
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_AGG_VIEW AS d WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
                ON a.Instance = d.Instance
            WHERE ISNULL(a.Is_Available, 1) = 1
            """
            instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Fase 1.5 lote 2 (2026-08-13): State/Severity reclassificados no
            # backend via _th (o SELECT d.* traz o State da view, que deixou de
            # ser a verdade — reescrever aqui mantem card e modal coerentes com
            # o override do cliente). Ordenacao movida do SQL para Python pela
            # mesma razao (ORDER BY d.State ordenava pela verdade velha).
            dl_warn = float(_th('deadlocks_state', 'warning'))
            dl_crit = float(_th('deadlocks_state', 'critical'))
            for r in instances:
                dc = int(r.get('Deadlock_Count') or 0)
                r['State'] = ('CRITICAL' if dc >= dl_crit else
                              'WARNING' if dc >= dl_warn else
                              'INFO' if dc >= 1 else 'OK')
                r['Severity'] = {'CRITICAL': 3, 'WARNING': 2, 'INFO': 1}.get(r['State'], 0)
            _dl_order = {'CRITICAL': 0, 'WARNING': 1, 'INFO': 2}
            instances.sort(key=lambda r: (_dl_order.get(r.get('State'), 3),
                                          -(int(r.get('Deadlock_Count') or 0))))
        elif kpi_type in ("integrity", "integrity-p1", "integrity-p3", "integrity-p4", "integrity-unmeasurable"):
            # Wave X (2026-07-19): drill-down do KPI Integridade — veredicto por DB
            # da KPI_MSSQL_INTEGRITY_VERDICT_VIEW (spec: DIAG_ERROR_824_SWEEP.sql
            # do owner, seccao [4]). So P1/P3/P4 + higiene PAGE_VERIFY; P5 "ok"
            # fica fora do modal. SEM filtro de freshness: fontes DBCC/settings
            # tem cadencia 30-60min (freshness guard cobre a morte do collector).
            # 1o raio-x real (19/07): P3=1195 (frota sem rotina CHECKDB) — TOP 300
            # com prioridade P1 > P4 > higiene > P3 para nao afogar o DOM do modal
            # nem enterrar o signal accionavel debaixo de 1200 rows estruturais
            # (memoria: KPI signal vs noise). O card mostra as contagens totais.
            # Variantes -p1/-p3/-p4 (feedback owner 19/07): cada row do card abre
            # o modal JA filtrado pelo seu veredicto (clicar "Corrompidas = 3"
            # tem que mostrar 3, nao a lista completa).
            # Fase 1.5 lote 3 (2026-08-13): a fronteira P4/P5 e' recalculada
            # em SQL sobre Days_Since_CheckDB com cutoff configuravel — o >30
            # cozido no Verdict da view deixou de ser a verdade para o Std.
            # P1/P3/unmeasurable continuam a vir da view tal-e-qual.
            ig_cut = float(_th('integrity_checkdb_age', 'warning'))
            _ig_verdict_sql = (
                "CASE WHEN v.Verdict IN ('P4','P5') THEN "
                f"CASE WHEN v.Days_Since_CheckDB > {ig_cut} THEN 'P4' ELSE 'P5' END "
                "ELSE v.Verdict END"
            )
            _IG_WHERE = {
                "integrity-p1": "v.Verdict = 'P1'",
                "integrity-p3": "v.Verdict = 'P3'",
                "integrity-p4": f"{_ig_verdict_sql} = 'P4'",
                # Item B (2026-07-22): coleta CHECKDB falhou (permissao/DB inacessivel).
                # Ortogonal ao Verdict — o modal mostra Error_Number/Message por DB,
                # a evidencia concreta para o ticket de grants (ex.: 2571).
                "integrity-unmeasurable": "v.Measurability = 'NOT_MEASURABLE'",
            }
            ig_where = _IG_WHERE.get(kpi_type, f"({_ig_verdict_sql} <> 'P5' OR v.Needs_PageVerify_Fix = 1)")
            query = f"""
            SELECT TOP 300
                   v.Instance, v.Database_Name,
                   {_ig_verdict_sql} AS Verdict,
                   CASE WHEN v.Verdict IN ('P4','P5') THEN
                       CASE WHEN v.Days_Since_CheckDB > {ig_cut}
                            THEN 'Validacao velha: reincluir na rotina'
                            ELSE 'OK' END
                   ELSE v.Verdict_Reason END AS Verdict_Reason,
                   v.Suspect_Pages, v.Suspect_Errors, v.Last_Suspect_Date,
                   v.Last_CheckDB_Date, v.Days_Since_CheckDB,
                   v.Page_Verify_Option, v.Needs_PageVerify_Fix,
                   v.Is_Auto_Shrink, v.State_Desc, v.Recovery_Model,
                   v.NoChecksum_Events_Recent_LTE7d,
                   v.Collection_Status, v.Error_Number, v.Error_Message,
                   ISNULL(e.Env, 'Undefined') AS Env
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INTEGRITY_VERDICT_VIEW AS v WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                ON e.Instance = v.Instance
            WHERE {ig_where}
            ORDER BY CASE
                WHEN v.Verdict = 'P1' THEN 0
                WHEN {_ig_verdict_sql} = 'P4' THEN 1
                WHEN v.Needs_PageVerify_Fix = 1 THEN 2
                ELSE 3 END,
                v.Suspect_Errors DESC, v.Days_Since_CheckDB DESC,
                v.Instance, v.Database_Name
            """
            instances = execute_intelligence_query(query, raise_on_error=False) or []
        elif kpi_type == "lock-count":
            query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK) WHERE Total_Locks > 0"
            all_instances = execute_intelligence_query(query, raise_on_error=False) or []
            # Apply 5-minute freshness window for long locks (real-time events)
            instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['real_time'])]
        elif kpi_type == "processes-alarm":
            # 2026-08-05: o filtro anterior procurava Process_Count/Cnt/Count --
            # colunas que a KPI_MSSQL_PROCESSES_AGG_VIEW nao tem (expoe
            # Total_Processes, Runnable_Count, Suspended_Count, Sleeping_Count,
            # Last_Check, State). Resultado: has_processes nunca era True e o
            # drilldown vinha SEMPRE vazio enquanto o card contava instancias.
            # Passa a usar o MESMO criterio do card. Fase 1.5 lote 3
            # (2026-08-13): criterio = Runnable_Count > warning configuravel
            # (nao o State da view) + State reescrito no backend, paridade
            # com helpers.collect (comparacao estrita > como a view).
            pr_warn = float(_th('processes_runnable', 'warning'))
            pr_crit = float(_th('processes_runnable', 'critical'))
            query = (
                f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_PROCESSES_AGG_VIEW "
                f"WITH (NOLOCK) WHERE Runnable_Count > {pr_warn}"
            )
            instances = execute_intelligence_query(query, raise_on_error=False) or []
            for r in instances:
                rc = int(r.get('Runnable_Count') or 0)
                r['State'] = 'CRITICAL' if rc > pr_crit else 'WARNING'
        elif kpi_type == "error-log":
            # Buscar erros recentes (ultimas 24 horas) da tabela STG
            # Usar Update_TS que eh coluna comum, ou buscar todos se nao existir
            all_errors = []
            
            # Primeiro tentar com Update_TS (coluna padrao do sistema)
            query_with_date = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK) WHERE Update_TS >= DATEADD(HOUR, -24, GETDATE())"
            query_all = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)"
            
            # Tentar com filtro de data primeiro
            all_errors = execute_intelligence_query(query_with_date, raise_on_error=False) or []
            
            # Se nao retornou dados, buscar todos (pode nao ter coluna Update_TS)
            if not all_errors:
                all_errors = execute_intelligence_query(query_all, raise_on_error=False) or []
            
            # Agrupar por instância e contar por severidade
            instance_errors = {}
            for row in all_errors:
                instance = row.get('Instance', '')
                if not instance:
                    continue
                
                if instance not in instance_errors:
                    instance_errors[instance] = {
                        'Instance': instance,
                        'Error_Count': 0,
                        'Critical_Count': 0,
                        'Warning_Count': 0,
                        'Last_Error_Date': None
                    }
                
                instance_errors[instance]['Error_Count'] += 1
                
                # Verificar severidade
                row_keys_upper = [k.upper() for k in row.keys()]
                severity = None
                for key in ['SEVERITY', 'SEVERITY_LEVEL', 'LEVEL', 'ERROR_LEVEL']:
                    if key in row_keys_upper:
                        severity = str(row.get(key, '')).upper()
                        break
                
                if severity and severity in ['ERROR', 'CRITICAL', 'FATAL', '16', '17', '18', '19', '20', '21', '22', '23', '24']:
                    instance_errors[instance]['Critical_Count'] += 1
                elif severity and severity in ['WARNING', 'WARN', '14', '15']:
                    instance_errors[instance]['Warning_Count'] += 1
                else:
                    instance_errors[instance]['Warning_Count'] += 1
                
                # Atualizar última data de erro (tentar múltiplas variações de nome)
                log_date = None
                for key in row.keys():
                    if 'date' in key.lower() or 'time' in key.lower():
                        value = row.get(key)
                        if value:
                            try:
                                if isinstance(value, str):
                                    log_date = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                elif isinstance(value, datetime):
                                    log_date = value
                                break
                            except (ValueError, TypeError):
                                continue

                if log_date:
                    if not instance_errors[instance]['Last_Error_Date'] or log_date > instance_errors[instance]['Last_Error_Date']:
                        instance_errors[instance]['Last_Error_Date'] = log_date
            
            instances = list(instance_errors.values())
        elif kpi_type == "tempdb-status" or kpi_type == "tempdb-status-critical" or kpi_type == "tempdb-status-warning":
            # TempDB Uso Interno: tentar KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW (uso real por sessões)
            # Threshold: Critical = usage_percent >= 80, Warning = usage_percent >= 60
            all_instances = []
            use_internal = False
            try:
                q_internal = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW WITH (NOLOCK)"
                raw = execute_intelligence_query(q_internal, raise_on_error=True) or []
                if raw:
                    all_instances = raw
                    use_internal = True
                    logger.info(f"TempDB: usando KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW ({len(raw)} rows)")
            except Exception as e:
                logger.debug(f"TempDB: KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW indisponível ({e}), sem dados")

            # Se não há view de uso interno, retornar lista vazia (não duplicar Disk File System)
            fresh_instances = [row for row in all_instances if is_data_fresh(row, FRESHNESS_WINDOWS['capacity'])] if all_instances else []

            tempdb_instances = []
            for row in fresh_instances:
                inst = row.get('Instance', row.get('INSTANCE', row.get('instance', '')))
                if not inst:
                    continue
                env = None
                for env_col in ['ENV', 'Environment', 'Env', 'ENVIRONMENT', 'environment']:
                    if env_col in row:
                        env = row.get(env_col)
                        break
                if not env:
                    env = _infer_env_from_instance(inst)

                if use_internal:
                    # 2026-08-03 (FIND Saude do Disco): a view expoe Percent_Used —
                    # Usage_Percent nunca existiu no schema real; todas as linhas
                    # eram ignoradas e a modal ficava sempre vazia.
                    usage_pct_raw = row.get('Percent_Used', row.get('PERCENT_USED', row.get('percent_used',
                        row.get('Usage_Percent', row.get('USAGE_PERCENT', row.get('usage_percent', None))))))
                    if usage_pct_raw is None:
                        continue  # View não tem coluna de uso interno — ignorar linha
                    usage_pct = float(usage_pct_raw or 0)
                    is_critical = usage_pct >= _th('tempdb_usage', 'critical')
                    is_warning = usage_pct >= _th('tempdb_usage', 'warning') and not is_critical
                else:
                    usage_pct = 0.0
                    is_critical = False
                    is_warning = False

                if not is_critical and not is_warning:
                    continue

                # Colunas reais da view sao *_MB (File_Size_GB/Free_GB nao existem)
                total_mb = row.get('Total_Size_MB', row.get('total_size_mb', None))
                free_mb = row.get('Free_MB', row.get('free_mb', None))
                file_size_gb = round(float(total_mb or 0) / 1024, 2) if total_mb is not None \
                    else float(row.get('File_Size_GB', row.get('file_size_gb', 0)) or 0)
                disk_free_gb = round(float(free_mb or 0) / 1024, 2) if free_mb is not None \
                    else float(row.get('Free_GB', row.get('disk_free_gb', 0)) or 0)

                instance_data = {
                    'instance': inst,
                    'Instance': inst,
                    'environment': env,
                    'Env': env,
                    'disk_used_percent': usage_pct,
                    'file_size_gb': file_size_gb,
                    'disk_free_gb': disk_free_gb,
                    'idle_high_sessions': int(row.get('Idle_Sessions', row.get('idle_high_sessions', 0)) or 0),
                    'status': 'CRITICAL' if is_critical else 'WARNING',
                    'Critical': 1 if is_critical else 0,
                    'Warning': 1 if is_warning else 0,
                }

                if kpi_type == "tempdb-status-critical" and not is_critical:
                    continue
                if kpi_type == "tempdb-status-warning" and not is_warning:
                    continue
                tempdb_instances.append(instance_data)

            instances = tempdb_instances
            logger.debug(f"TempDB Status Modal: {len(instances)} instâncias (internal={use_internal})")
        elif kpi_type in ["server-offline", "server-offline-all", "sql-services-down"]:
            # SQL Services Down - APENAS serviços SQL parados (ping OK, mas serviços down)
            # Eventos com Diagnosis = 'offline' (ping falhou) vão para Instances Off
            query = f"""
            SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
            WHERE Diagnosis = 'sql_down'
            ORDER BY Event_Count DESC
            """
            all_events = execute_intelligence_query(query, raise_on_error=False) or []

            # Formatar para o frontend (agrupado por servidor)
            server_offline_instances = []
            for row in all_events:
                instance_name = row.get('Instance') or row.get('Server_Name', '')
                event_count = row.get('Event_Count', 1)
                instance_data = {
                    'instance': instance_name,
                    'Instance': instance_name,
                    'server_name': row.get('Server_Name', ''),
                    'event_count': event_count,
                    'diagnosis': row.get('Diagnosis', ''),
                    'diagnosis_desc': row.get('Diagnosis_Desc', 'SQL Services Down'),
                    'ping_ok': row.get('Ping_OK', True),
                    'ping_status': row.get('Ping_Status', 'OK'),
                    'ping_message': row.get('Ping_Message', ''),
                    'services_down': row.get('Services_Down', ''),
                    'first_event_time': row.get('First_Event_Time'),
                    'last_event_time': row.get('Last_Event_Time'),
                    'event_time': row.get('Last_Event_Time'),
                    'minutes_since_first_event': row.get('Minutes_Since_First_Event', 0),
                    'minutes_since_event': row.get('Minutes_Since_Last_Event', 0),
                    'severity': row.get('Severity', 'WARNING'),
                    'environment': row.get('Env', 'Undefined'),
                    'Env': row.get('Env', 'Undefined'),
                    'status': 'WARNING'
                }
                server_offline_instances.append(instance_data)

            instances = server_offline_instances
            logger.debug(f"SQL Services Down Modal: {len(instances)} eventos retornados (apenas sql_down)")
        elif kpi_type == "cpu-critical":
            # CPU Crítico - Instâncias com CPU >= threshold OU Severity CRITICAL
            # ALINHADO COM O CARD: mesma lógica E mesmo threshold da fonte única
            # (censo B5, 2026-08-11: era 95 hardcoded — cpu_critical é configurável
            # F1, um override do cliente fazia card e modal divergirem)
            query = f"""
            SELECT
                c.Instance,
                c.Hostname,
                c.Processor_Pct,
                c.SQL_CPU_Pct,
                c.Queue_Length,
                c.Processor_Status,
                c.Queue_Status,
                c.Severity,
                c.Update_TS,
                c.Age_Seconds,
                ISNULL(e.Env, 'Undefined') AS Env
            FROM {INTELLIGENCE_SCHEMA}.vw_OS_CPU_Current c WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
                ON e.Instance = c.Instance
            WHERE c.Processor_Pct >= {_th('cpu_critical', 'critical')} OR c.Severity = 'CRITICAL'
            ORDER BY c.Processor_Pct DESC
            """
            all_cpu_critical = execute_intelligence_query(query, raise_on_error=False) or []

            # Filtrar servidores offline (mesma logica do dashboard card)
            offline_query = f"""
            SELECT DISTINCT UPPER(Server_Name) AS Server_Name
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
            WHERE Ping_OK = 0
            """
            offline_rows = execute_intelligence_query(offline_query, raise_on_error=False) or []
            offline_hosts = {(r.get('Server_Name') or '').upper() for r in offline_rows}

            # Formatar para o frontend com link para módulo CPU
            # Usa dados atuais da vw_OS_CPU_Current (mesma view do card)
            cpu_critical_instances = []
            for row in all_cpu_critical:
                # Excluir servidores offline (dados stale)
                hostname = (row.get('Hostname') or row.get('Instance', '').split('_')[0]).upper()
                if hostname in offline_hosts:
                    continue
                instance_name = row.get('Instance', '')
                # Converter formato HOSTNAME\INSTANCE para HOSTNAME_INSTANCE para URL
                instance_url = instance_name.replace('\\', '_')

                processor_pct = row.get('Processor_Pct', 0) or 0
                sql_cpu_pct = row.get('SQL_CPU_Pct', 0) or 0
                queue_length = row.get('Queue_Length', 0) or 0

                instance_data = {
                    'instance': instance_name,
                    'Instance': instance_name,
                    'hostname': row.get('Hostname', ''),
                    'Env': row.get('Env', 'Undefined'),
                    # Dados atuais (vw_OS_CPU_Current)
                    'processor_pct': processor_pct,
                    'current_cpu_pct': processor_pct,
                    'sql_cpu_pct': sql_cpu_pct,
                    'current_sql_cpu_pct': sql_cpu_pct,
                    'queue_length': queue_length,
                    'current_queue_length': queue_length,
                    # Status e severidade
                    'processor_status': row.get('Processor_Status', ''),
                    'queue_status': row.get('Queue_Status', ''),
                    'severity': row.get('Severity', 'CRITICAL'),
                    'update_ts': row.get('Update_TS'),
                    'age_seconds': row.get('Age_Seconds', 0),
                    'status': 'CRITICAL',
                    # Link para módulo CPU
                    'detail_link': f'/api/monitoring/cpu/server/{instance_url}',
                    'detail_module': 'cpu'
                }
                cpu_critical_instances.append(instance_data)

            instances = cpu_critical_instances
            logger.debug(f"CPU Critical Modal: {len(instances)} instâncias retornadas")
        elif kpi_type == "memory-critical":
            # Memória Crítico - Instâncias com memória >= 99% ou alto page fault/swap
            # Usa a view vw_OS_Memory_Trend_30Min para análise de tendência
            query = f"""
            SELECT
                t.Instance,
                t.Hostname,
                t.Avg_Percent_Used,
                t.Max_Percent_Used,
                t.Min_Available_MB,
                t.Avg_Available_MB,
                t.Max_Available_MB,
                t.Avg_Pages_Sec,
                t.Max_Pages_Sec,
                t.Avg_Page_Reads_Sec,
                t.Max_Page_Reads_Sec,
                t.Avg_Percent_Committed,
                t.Max_Percent_Committed,
                t.High_Page_Reads_Count,
                t.Low_Available_MB_Count,
                t.Sample_Count,
                t.Is_Sustained,
                t.Severity,
                t.Period_Start,
                t.Period_End,
                c.Available_MB AS Current_Available_MB,
                c.Percent_Used AS Current_Percent_Used,
                c.Pages_Per_Sec AS Current_Pages_Sec,
                c.Page_Reads_Sec AS Current_Page_Reads_Sec,
                c.Percent_Committed AS Current_Percent_Committed,
                c.Available_MB_Status,
                c.Page_Reads_Status,
                c.Pages_Sec_Status,
                c.Update_TS,
                c.Age_Seconds
            FROM {INTELLIGENCE_SCHEMA}.vw_OS_Memory_Trend_30Min t WITH (NOLOCK)
            LEFT JOIN {INTELLIGENCE_SCHEMA}.vw_OS_Memory_Current AS c WITH (NOLOCK)
                ON t.Instance = c.Instance AND t.Hostname = c.Hostname
            WHERE t.Severity = 'CRITICAL'
               OR (t.Avg_Percent_Used >= 99 AND t.Is_Sustained = 1)
               OR (t.Avg_Page_Reads_Sec > 100 AND t.Is_Sustained = 1)
            ORDER BY t.Max_Percent_Used DESC, t.Avg_Page_Reads_Sec DESC
            """
            all_memory_critical = execute_intelligence_query(query, raise_on_error=False) or []

            # Censo B4 (2026-08-11): o CARD exclui hosts offline (dados stale de
            # memoria num servidor em baixo); a modal nao excluia — o par
            # contradizia-se exactamente no pior momento. Mesmo padrao do cpu-critical.
            offline_query = f"""
            SELECT DISTINCT UPPER(Server_Name) AS Server_Name
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
            WHERE Ping_OK = 0
            """
            offline_rows = execute_intelligence_query(offline_query, raise_on_error=False) or []
            offline_hosts = {(r.get('Server_Name') or '').upper() for r in offline_rows}

            # Formatar para o frontend com link para módulo Memória
            memory_critical_instances = []
            for row in all_memory_critical:
                hostname_upper = (row.get('Hostname') or row.get('Instance', '').split('_')[0]).upper()
                if hostname_upper in offline_hosts:
                    continue
                instance_name = row.get('Instance', '')
                # Converter formato HOSTNAME\INSTANCE para HOSTNAME_INSTANCE para URL
                instance_url = instance_name.replace('\\', '_')

                instance_data = {
                    'instance': instance_name,
                    'Instance': instance_name,
                    'hostname': row.get('Hostname', ''),
                    'avg_percent_used': row.get('Avg_Percent_Used', 0),
                    'max_percent_used': row.get('Max_Percent_Used', 0),
                    'current_percent_used': row.get('Current_Percent_Used', 0),
                    'min_available_mb': row.get('Min_Available_MB', 0),
                    'avg_available_mb': row.get('Avg_Available_MB', 0),
                    'current_available_mb': row.get('Current_Available_MB', 0),
                    'avg_pages_sec': row.get('Avg_Pages_Sec', 0),
                    'max_pages_sec': row.get('Max_Pages_Sec', 0),
                    'current_pages_sec': row.get('Current_Pages_Sec', 0),
                    'avg_page_reads_sec': row.get('Avg_Page_Reads_Sec', 0),
                    'max_page_reads_sec': row.get('Max_Page_Reads_Sec', 0),
                    'current_page_reads_sec': row.get('Current_Page_Reads_Sec', 0),
                    'avg_percent_committed': row.get('Avg_Percent_Committed', 0),
                    'max_percent_committed': row.get('Max_Percent_Committed', 0),
                    'current_percent_committed': row.get('Current_Percent_Committed', 0),
                    'high_page_reads_count': row.get('High_Page_Reads_Count', 0),
                    'low_available_mb_count': row.get('Low_Available_MB_Count', 0),
                    'sample_count': row.get('Sample_Count', 0),
                    'is_sustained': row.get('Is_Sustained', 0),
                    'severity': row.get('Severity', 'CRITICAL'),
                    'available_mb_status': row.get('Available_MB_Status', ''),
                    'page_reads_status': row.get('Page_Reads_Status', ''),
                    'pages_sec_status': row.get('Pages_Sec_Status', ''),
                    'period_start': row.get('Period_Start'),
                    'period_end': row.get('Period_End'),
                    'update_ts': row.get('Update_TS'),
                    'age_seconds': row.get('Age_Seconds', 0),
                    'status': 'CRITICAL',
                    # Link para módulo Memória
                    'detail_link': f'/api/monitoring/memory/server/{instance_url}',
                    'detail_module': 'memory'
                }
                memory_critical_instances.append(instance_data)

            instances = memory_critical_instances
            logger.debug(f"Memory Critical Modal: {len(instances)} instâncias retornadas")
        elif kpi_type == "disk-latency-critical" or kpi_type == "disk-latency-warning":
            # Disk Latency - Drives com latência alta
            # Thresholds da fonte unica (api/kpi_thresholds_registry.py)
            is_critical = kpi_type == "disk-latency-critical"
            _dl_crit = _th('disk_latency', 'critical')
            _dl_warn = _th('disk_latency', 'warning')
            threshold = _dl_crit if is_critical else _dl_warn
            max_threshold = _dl_crit if not is_critical else 999999  # Para warning, mostrar < critical

            query = f"""
            SELECT
                Hostname,
                Drive,
                Avg_Read_Latency_MS,
                Avg_Write_Latency_MS,
                Disk_Reads_Sec,
                Disk_Writes_Sec,
                Percent_Disk_Time,
                Update_TS,
                CASE
                    WHEN Avg_Read_Latency_MS >= {_dl_crit} OR Avg_Write_Latency_MS >= {_dl_crit} THEN 'CRITICAL'
                    WHEN Avg_Read_Latency_MS >= {_dl_warn} OR Avg_Write_Latency_MS >= {_dl_warn} THEN 'WARNING'
                    ELSE 'OK'
                END AS Latency_Status
            FROM {INTELLIGENCE_SCHEMA}.KPI_OS_DISK_PERF_STG WITH (NOLOCK)
            WHERE (Avg_Read_Latency_MS >= {threshold} OR Avg_Write_Latency_MS >= {threshold})
            """
            if not is_critical:
                # Para warning, excluir os que são critical
                query += f" AND (Avg_Read_Latency_MS < {max_threshold} AND Avg_Write_Latency_MS < {max_threshold})"
            query += """
            ORDER BY
                CASE WHEN ISNULL(Avg_Read_Latency_MS,0) > ISNULL(Avg_Write_Latency_MS,0) THEN ISNULL(Avg_Read_Latency_MS,0) ELSE ISNULL(Avg_Write_Latency_MS,0) END DESC
            """

            all_disk_latency = await execute_intelligence_query_async(query, raise_on_error=False) or []

            # Censo B4 (2026-08-11): card exclui hosts offline, modal nao excluia —
            # mesmo padrao do cpu-critical. (O Env por LIKE abaixo fica: a chave
            # aqui e' Hostname, um dos 2 blocos do handoff §5 que exigem desenho
            # proprio — JOIN cego a INST_ENVS falharia em FCI/instancia nomeada.)
            offline_query = f"""
            SELECT DISTINCT UPPER(Server_Name) AS Server_Name
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
            WHERE Ping_OK = 0
            """
            offline_rows = execute_intelligence_query(offline_query, raise_on_error=False) or []
            offline_hosts = {(r.get('Server_Name') or '').upper() for r in offline_rows}

            # Formatar para o frontend
            disk_latency_instances = []
            for row in all_disk_latency:
                hostname = row.get('Hostname', '')
                if hostname.upper() in offline_hosts:
                    continue
                drive = row.get('Drive', '')
                read_latency = row.get('Avg_Read_Latency_MS', 0) or 0
                write_latency = row.get('Avg_Write_Latency_MS', 0) or 0
                max_latency = max(read_latency, write_latency)

                # Determinar ambiente
                env = 'Undefined'
                hostname_upper = hostname.upper()
                if 'PRD' in hostname_upper or 'PROD' in hostname_upper:
                    env = 'PRD'
                elif 'QLT' in hostname_upper or 'QUAL' in hostname_upper:
                    env = 'QLT'
                elif 'TST' in hostname_upper or 'TEST' in hostname_upper or 'DEV' in hostname_upper:
                    env = 'TST'

                instance_data = {
                    'Instance': hostname,
                    'instance': hostname,
                    'Hostname': hostname,
                    'Drive': drive,
                    'Avg_Read_Latency_MS': read_latency,
                    'Avg_Write_Latency_MS': write_latency,
                    'Max_Latency_MS': max_latency,
                    'Disk_Reads_Sec': row.get('Disk_Reads_Sec', 0) or 0,
                    'Disk_Writes_Sec': row.get('Disk_Writes_Sec', 0) or 0,
                    'Percent_Disk_Time': row.get('Percent_Disk_Time', 0) or 0,
                    'Latency_Status': row.get('Latency_Status', 'WARNING'),
                    'Env': env,
                    'Update_TS': row.get('Update_TS'),
                    'status': 'CRITICAL' if is_critical else 'WARNING'
                }
                disk_latency_instances.append(instance_data)

            instances = disk_latency_instances
            logger.debug(f"Disk Latency {'Critical' if is_critical else 'Warning'} Modal: {len(instances)} drives retornados")
        elif kpi_type == "jobs-failed" or kpi_type == "jobs-collisions":
            # Jobs — tentar STG views, fallback para query direta
            job_views = [
                f"{INTELLIGENCE_SCHEMA}.KPI_MSSQL_JOB_FAILURES_AGG_VIEW",
                f"{INTELLIGENCE_SCHEMA}.KPI_MSSQL_JOBS_FAILED_AGG_VIEW",
                f"{INTELLIGENCE_SCHEMA}.KPI_MSSQL_JOB_FAILURES_STG"
            ]
            job_data = []
            for view_name in job_views:
                try:
                    query = f"""
                    SELECT j.*, ISNULL(e.Env, 'Undefined') AS Env
                    FROM {view_name} AS j WITH (NOLOCK)
                    LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                        ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(j.Instance)))
                    """
                    job_data = await execute_intelligence_query_async(query, raise_on_error=False)
                    if job_data:
                        logger.info(f"Jobs modal - view encontrada: {view_name} ({len(job_data)} registros)")
                        break
                except Exception:
                    continue

            if job_data and kpi_type == "jobs-failed":
                for row in job_data:
                    row['Env'] = _detect_env(row.get('Instance', ''), row.get('Env'))
                instances = job_data
            elif kpi_type == "jobs-collisions":
                # Colisoes — sempre buscar direto (STG nao tem)
                _, collision_results = await _query_jobs_from_servers(only_collisions=True)
                if collision_results and collision_results.get("instances"):
                    instances = collision_results["instances"]
                else:
                    instances = []
            elif not job_data and kpi_type == "jobs-failed":
                # Fallback: query servidores diretamente
                failed_results, _ = await _query_jobs_from_servers(only_collisions=False)
                if failed_results and failed_results.get("instances"):
                    instances = failed_results["instances"]
                else:
                    instances = []
            logger.debug(f"Jobs Modal ({kpi_type}): {len(instances)} registros retornados")
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de KPI inválido: {kpi_type}")

        # Para db-availability, incluir total de databases no retorno
        response_data = {
            "success": True,
            "kpi_type": kpi_type,
            "instances": _serialize_result(instances),
            "count": len(instances)
        }
        
        # Adicionar total_databases se foi calculado (para db-availability)
        # 2026-08-12: era `'total_databases' in locals()`. locals() devolve
        # dados ERRADOS sob PyArmor BCC (repro isolado do packaging-architect)
        # e era um dos gatilhos do SystemError que matava TODAS as modais de
        # instancias no bundle. Sentinela explicita no topo da funcao.
        if kpi_type == "db-availability" and total_databases is not None:
            response_data["total_databases"] = total_databases

        # Adicionar contagem por ENV se foi calculada (para db-availability all=true)
        if env_counts:
            response_data["env_counts"] = env_counts

        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, "fetching Intelligence problematic instances")


# ========================================
# SERVER OFFLINE EVENTS MANAGEMENT
# ========================================

@router.post("/server-offline/resolve/{event_id}", response_model=MessageResponse)
async def resolve_server_offline_event(event_id: int, request: Request):
    """
    Marca um evento de servidor offline como resolvido.

    Args:
        event_id: ID do evento a ser resolvido

    Returns:
        JSON com status da operação
    """
    admin = await _require_dba(request)  # resolver offline e operacao de turno
    # migration 009: auditoria de quem resolveu (distingue manual de auto-collector)
    resolved_by = re.sub(r"[^A-Za-z0-9_\\.\-@]", "", str((admin or {}).get("username") or "portal-admin"))[:64] or "portal-admin"
    try:
        # Executar procedure para resolver evento
        query = f"""
        EXEC {INTELLIGENCE_SCHEMA}.usp_ResolveServerOfflineEvent @Event_ID = {event_id}, @Resolved_By = N'{resolved_by}'
        """
        try:
            result = execute_intelligence_query(query, raise_on_error=True)
        except Exception as e:
            if 'Resolved_By' not in str(e):
                raise
            # migration 009 ainda nao aplicada — resolver sem auditoria
            result = execute_intelligence_query(f"""
        EXEC {INTELLIGENCE_SCHEMA}.usp_ResolveServerOfflineEvent @Event_ID = {event_id}
        """, raise_on_error=True)

        events_resolved = 0
        if result and len(result) > 0:
            events_resolved = result[0].get('Events_Resolved', 0)

        if events_resolved > 0:
            return JSONResponse(content={
                "success": True,
                "message": f"Evento {event_id} marcado como resolvido",
                "events_resolved": events_resolved
            })
        else:
            raise HTTPException(status_code=404, detail=f"Evento {event_id} não encontrado ou já resolvido")

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"resolving server offline event {event_id}")


@router.post("/server-offline/resolve-by-server/{server_name:path}", response_model=MessageResponse)
async def resolve_server_offline_by_server(server_name: str, request: Request):
    """
    Marca todos os eventos não resolvidos de um servidor como resolvidos.

    Args:
        server_name: Nome do servidor

    Returns:
        JSON com status da operação
    """
    admin = await _require_dba(request)  # resolver offline e' operacao de turno
    if not re.match(r'^[A-Za-z0-9_\\.\-]{1,256}$', server_name):
        raise HTTPException(status_code=400, detail="Nome de servidor inválido")
    # migration 009: auditoria de quem resolveu (distingue manual de auto-collector)
    resolved_by = re.sub(r"[^A-Za-z0-9_\\.\-@]", "", str((admin or {}).get("username") or "portal-admin"))[:64] or "portal-admin"

    try:
        # Executar procedure para resolver eventos do servidor
        query = f"""
        EXEC {INTELLIGENCE_SCHEMA}.usp_ResolveServerOfflineEvent @Server_Name = N'{server_name.replace("'", "''")}', @Resolved_By = N'{resolved_by}'
        """
        try:
            result = execute_intelligence_query(query, raise_on_error=True)
        except Exception as e:
            if 'Resolved_By' not in str(e):
                raise
            # migration 009 ainda nao aplicada — resolver sem auditoria
            result = execute_intelligence_query(f"""
        EXEC {INTELLIGENCE_SCHEMA}.usp_ResolveServerOfflineEvent @Server_Name = N'{server_name.replace("'", "''")}'
        """, raise_on_error=True)

        events_resolved = 0
        if result and len(result) > 0:
            events_resolved = result[0].get('Events_Resolved', 0)

        return JSONResponse(content={
            "success": True,
            "message": f"{events_resolved} evento(s) resolvido(s) para {server_name}",
            "events_resolved": events_resolved,
            "server_name": server_name
        })

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"resolving server offline events for {server_name}")


@router.get("/server-offline/history", response_model=GenericResponse)
async def get_server_offline_history(days: int = 7, include_resolved: bool = True):
    """
    Retorna histórico de eventos de servidor offline.

    Args:
        days: Número de dias para buscar (padrão: 7)
        include_resolved: Incluir eventos já resolvidos (padrão: True)

    Returns:
        JSON com lista de eventos
    """
    try:
        where_clause = f"WHERE Event_Time >= DATEADD(DAY, -{days}, GETDATE())"
        if not include_resolved:
            where_clause += " AND Is_Resolved = 0"

        query = f"""
        SELECT
            Event_ID,
            Server_Name AS Instance,
            Diagnosis,
            CASE Diagnosis
                WHEN 'offline' THEN 'Servidor Offline'
                WHEN 'sql_down' THEN 'SQL Services Down'
                WHEN 'partial' THEN 'Serviços Parciais'
                ELSE Diagnosis
            END AS Diagnosis_Desc,
            Ping_OK,
            CASE WHEN Ping_OK = 1 THEN 'OK' ELSE 'FALHA' END AS Ping_Status,
            Ping_Message,
            Services_Down,
            Event_Time,
            Resolved_Time,
            Is_Resolved,
            CASE WHEN Is_Resolved = 1 THEN 'Resolvido' ELSE 'Ativo' END AS Status,
            DATEDIFF(MINUTE, Event_Time, ISNULL(Resolved_Time, GETDATE())) AS Duration_Minutes,
            CASE
                WHEN Server_Name LIKE '%PRD%' OR Server_Name LIKE '%PROD%' THEN 'PRD'
                WHEN Server_Name LIKE '%QLT%' OR Server_Name LIKE '%QUAL%' THEN 'QLT'
                WHEN Server_Name LIKE '%TST%' OR Server_Name LIKE '%TEST%' OR Server_Name LIKE '%DEV%' THEN 'TST'
                ELSE 'Undefined'
            END AS Env
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
        {where_clause}
        ORDER BY Event_Time DESC
        """
        events = execute_intelligence_query(query, raise_on_error=False) or []

        return JSONResponse(content={
            "success": True,
            "events": _serialize_result(events),
            "count": len(events),
            "days": days,
            "include_resolved": include_resolved
        })

    except Exception as e:
        raise safe_http_error(500, e, "fetching server offline event history")


@router.get("/server-offline/summary", response_model=GenericResponse)
async def get_server_offline_summary():
    """
    Retorna resumo dos eventos de servidor offline para o card do dashboard.

    Returns:
        JSON com contagem por tipo e status geral
    """
    try:
        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK)
        """
        result = execute_intelligence_query(query, raise_on_error=False)

        if result and len(result) > 0:
            row = result[0]
            return JSONResponse(content={
                "success": True,
                "summary": {
                    "servers_offline": int(row.get('Servers_Offline', 0) or 0),
                    "servers_sql_down": int(row.get('Servers_SQL_Down', 0) or 0),
                    "servers_partial": int(row.get('Servers_Partial', 0) or 0),
                    "total_events": int(row.get('Total_Events', 0) or 0),
                    "last_event_time": row.get('Last_Event_Time'),
                    "overall_status": row.get('Overall_Status', 'OK')
                }
            })
        else:
            return JSONResponse(content={
                "success": True,
                "summary": {
                    "servers_offline": 0,
                    "servers_sql_down": 0,
                    "servers_partial": 0,
                    "total_events": 0,
                    "last_event_time": None,
                    "overall_status": "OK"
                }
            })

    except Exception as e:
        raise safe_http_error(500, e, "fetching server offline event summary")

# ========================================
# FUNCAO DE PRE-CARREGAMENTO DO CACHE
# ========================================
# Deve ser chamada no lifespan do FastAPI para carregar o cache antes de aceitar conexoes

async def preload_kpi_cache() -> bool:
    """
    Pre-carrega o cache de KPIs no startup da aplicacao.
    Deve ser chamado no lifespan do FastAPI para que o dashboard
    carregue instantaneamente quando o usuario abrir a pagina.
    
    Chama internamente get_kpi_dashboard() que popula o cache _dashboard_cache.
    
    Returns:
        bool: True se o cache foi carregado com sucesso, False caso contrario
    """
    logger.info("[STARTUP] Iniciando pre-carregamento do cache de KPIs...")
    start_time = time.time()
    
    try:
        # 1. Testar conexao com o SQL Server
        # FIX 2026-07-23: em thread, NUNCA inline. execute_intelligence_query e'
        # sincrona; se o connect pendura (ex: SQL Browser UDP sem resposta, fase
        # que o login timeout de 15s nao cobre), bloqueia o event loop inteiro e
        # o portal vira tijolo -- nem paginas estaticas respondem (incidente
        # 2026-07-23, 1h+ pendurado em "Testando conexao").
        import asyncio as _aio_preload
        logger.info(f"[STARTUP] Testando conexao com {INTELLIGENCE_SERVER}/{INTELLIGENCE_DATABASE}...")
        test_query = "SELECT 1 AS test"
        test_result = await _aio_preload.to_thread(execute_intelligence_query, test_query, raise_on_error=True)
        if not test_result:
            logger.error("[STARTUP] Falha no teste de conexao com SQL Server")
            return False
        logger.info("[STARTUP] Conexao com SQL Server OK")
        
        # 2. Coletar e popular o cache (sem Request — #1+#3+F5; antes chamava
        #    get_kpi_dashboard() sem request -> TypeError -> cache nunca aquecia)
        logger.info("[STARTUP] Executando queries do dashboard para popular cache...")
        await _collect_and_cache_dashboard()

        # Verificar se o cache foi populado (cache REAL em helpers.py)
        from api.routers.intelligence.helpers import _get_cached_dashboard as _h_get_cached
        cached = _h_get_cached()
        if cached:
            elapsed = time.time() - start_time
            logger.info(f"[STARTUP] Cache de KPIs pre-carregado com sucesso em {elapsed:.2f}s")
            
            # Log de resumo dos KPIs carregados
            if cached.get('data'):
                data = cached['data']
                logger.info(f"[STARTUP] KPIs carregados - Instances OK: {data.get('instance_availability', {}).get('ok_count', 'N/A')}, " +
                           f"DB Issues: {data.get('db_availability', {}).get('abnormal_count', 'N/A')}, " +
                           f"Disk Critical: {data.get('db_disk_file_system', {}).get('critical_count', 'N/A')}")
            return True
        else:
            logger.warning("[STARTUP] Cache nao foi populado apos chamada ao dashboard")
            return False
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[STARTUP] Erro ao pre-carregar cache de KPIs apos {elapsed:.2f}s: {e}", exc_info=True)
        return False
