#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intelligence KPIs - Shared helpers.
Contains: connection management, query execution, cache, freshness checks,
environment detection, serialization, configuration, and dashboard KPI collectors.
"""

from fastapi import HTTPException
from typing import Dict, List, Optional, Any, Set
import logging
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
import pyodbc
from decimal import Decimal
from datetime import datetime, timedelta
import time
import os
import json
from watcherdb.core.db_identity import resolve as _resolve_db_identity
from services.secrets import get_secret
from pathlib import Path

from api.connection_pool import get_intelligence_pool, get_sql_server_pool
from api.error_helpers import safe_http_error
# Fase 0 thresholds (2026-08-04): fonte unica — ver api/kpi_thresholds_registry.py
# Fase 1 (2026-08-04): _th resolve overrides do cliente (fallback ao registry se a
# tabela WDB_KPI_THRESHOLDS estiver ausente/vazia — comportamento identico a F0).
# Assinatura compativel com value(): resolve(kpi, level[, instance, env, database]).
from api.threshold_overrides import resolve as _th

logger = logging.getLogger(__name__)

# Thread pool para executar queries de forma nao bloqueante
_query_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix='sql_query')

# ========================================
# CACHE PARA DASHBOARD KPIs
# ========================================
_dashboard_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 60  # segundos — sub a 60s para reduzir polling pressure no
               # workerpool. O frontend faz polling a cada 30s, mas com
               # ttl=60 metade dessas chamadas servem do cache em <10ms.
}
_cache_lock = threading.Lock()


def _get_cached_dashboard():
    """Retorna dados do cache se ainda validos"""
    with _cache_lock:
        if _dashboard_cache['data'] is None:
            return None
        age = time.time() - _dashboard_cache['timestamp']
        if age > _dashboard_cache['ttl']:
            return None
        logger.debug(f"Dashboard cache hit (age: {age:.1f}s)")
        return _dashboard_cache['data']


def _set_dashboard_cache(data):
    """Armazena dados no cache"""
    with _cache_lock:
        _dashboard_cache['data'] = data
        _dashboard_cache['timestamp'] = time.time()
        logger.debug("Dashboard cache updated")


# ========================================
# SNAPSHOT PERSISTIDO (stale-while-revalidate, 2026-06-11)
# Cold-cache pos-restart servia coleta ao vivo (89 servers) -> browser timeout.
# Snapshot em disco serve resposta imediata marcada stale; re-warm repoe fresco.
# [WAIVER aplicado 2026-06-11 | regra: edicao ficheiro producao | scope: snapshot SWR]
# ========================================
from watcherdb.core.paths import cache_dir as _wdb_cache_dir
# B0-4: dev resolve <root>/cache (inalterado); frozen ProgramData\WatcherDB\cache.
_SNAPSHOT_PATH = _wdb_cache_dir() / "dashboard_snapshot.json"
_SNAPSHOT_MAX_AGE_SEC = 24 * 3600  # nao servir snapshot >24h


def _save_dashboard_snapshot(response_data: dict):
    """Grava snapshot do dashboard em disco (write atomico: tmp + os.replace)."""
    try:
        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(response_data)
        payload["snapshot_at"] = datetime.now().isoformat(timespec="seconds")
        tmp = _SNAPSHOT_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        os.replace(tmp, _SNAPSHOT_PATH)
        logger.debug("[SNAPSHOT] Dashboard snapshot gravado")
    except Exception as e:
        logger.warning(f"[SNAPSHOT] Falha ao gravar dashboard snapshot: {e}")


def _load_dashboard_snapshot():
    """Le snapshot do disco; None se ausente, corrupto ou >24h.
    Retorna payload com stale=True + snapshot_at para o frontend sinalizar."""
    try:
        if not _SNAPSHOT_PATH.exists():
            return None
        with open(_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        snap_at = datetime.fromisoformat(payload.get("snapshot_at", ""))
        if (datetime.now() - snap_at).total_seconds() > _SNAPSHOT_MAX_AGE_SEC:
            logger.info("[SNAPSHOT] Snapshot >24h — ignorado")
            return None
        payload["stale"] = True
        return payload
    except Exception as e:
        logger.warning(f"[SNAPSHOT] Falha ao ler dashboard snapshot: {e}")
        return None


# ========================================
# FRESHNESS WINDOW CONFIGURATION
# ========================================
FRESHNESS_WINDOWS = {
    'services': 15,
    'real_time': 5,
    'capacity': 1440,
    'backup': 1440,
    'alwayson': 5,
}

# ========================================
# CACHE DE VALORES PERSISTENTES
# ========================================
_last_known_values = {
    'instances_ok': None,
    'db_availability_ok': None,
    'db_availability_total': None,
    'last_abnormal_count': None,
    'last_instances_off_count': None,
    '_initialized': False
}

# Configuracao de conexao SQL Server Intelligence
INTELLIGENCE_SERVER = os.getenv("INTELLIGENCE_SERVER") or os.getenv("SQL_SERVER", "SQLHDSTST505\\I01")
INTELLIGENCE_DATABASE = os.getenv("INTELLIGENCE_DATABASE") or os.getenv("SQL_DATABASE", "WatcherDB_Intelligence")
INTELLIGENCE_SCHEMA = "dbo"
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

logger.info(f"Intelligence KPIs configurado: SERVER={INTELLIGENCE_SERVER}, DATABASE={INTELLIGENCE_DATABASE}, WINDOWS_AUTH={INTELLIGENCE_USE_WINDOWS_AUTH} [{_DB_IDENTITY.mode}: {_DB_IDENTITY.source}]")

# Connection Pool simples
_connection_pool = []
_pool_lock = threading.Lock()
_MAX_POOL_SIZE = 5


def _return_connection_to_pool(conn):
    """Retorna conexao ao pool para reuso"""
    try:
        with _pool_lock:
            if len(_connection_pool) < _MAX_POOL_SIZE:
                try:
                    conn.execute("SELECT 1")
                    _connection_pool.append(conn)
                    return
                except Exception:
                    pass
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
                conn.execute("SELECT 1")
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
    return None


def get_intelligence_connection():
    """Obtem conexao com o SQL Server Intelligence usando pool centralizado."""
    try:
        pool = get_intelligence_pool()
        conn = pool.get_connection()
        logger.debug("Conexao obtida do pool Intelligence")
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao SQL Server Intelligence: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao conectar ao SQL Server Intelligence: {str(e)}")


def execute_intelligence_query(query: str, raise_on_error: bool = True) -> List[Dict]:
    """Executa query no SQL Server Intelligence e retorna resultados como lista de dicionarios"""
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
                raise safe_http_error(500, query_err, "executing Intelligence SQL query")
            return []

        _exec_time = time.time() - _q_start - _conn_time
        if _conn_time > 1 or _exec_time > 1:
            _query_preview = query[:80].replace(chr(10), " ").strip()
            logger.debug(f"[QUERY] conn={_conn_time:.2f}s exec={_exec_time:.2f}s | {_query_preview}...")

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        results = []
        for row in rows:
            row_dict = {}
            for idx, col in enumerate(columns):
                value = row[idx]
                if isinstance(value, Decimal):
                    value = float(value)
                elif isinstance(value, datetime):
                    value = value.isoformat()
                row_dict[col] = value
            results.append(row_dict)

        return results
    except Exception as e:
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
            try:
                pool = get_intelligence_pool()
                pool.return_connection(conn)
            except Exception:
                pass


async def execute_intelligence_query_async(query: str, raise_on_error: bool = True) -> List[Dict]:
    """Versao async de execute_intelligence_query"""
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


def is_data_fresh(row: Dict[str, Any], minutes: int) -> bool:
    """Check if a data row is fresh based on its timestamp columns."""
    timestamp = None
    timestamp_column = None

    possible_timestamp_columns = [
        'Last_Check', 'LAST_CHECK', 'last_check',
        'Update_TS', 'UPDATE_TS', 'update_ts',
        'Capture_TS', 'CAPTURE_TS', 'capture_ts',
        'Capture_Time', 'CAPTURE_TIME', 'capture_time',
        'Timestamp', 'TIMESTAMP', 'timestamp',
        'Updated_At', 'UPDATED_AT', 'updated_at',
        'Created_At', 'CREATED_AT', 'created_at',
        'LogDate', 'Log_Date', 'LOG_DATE', 'log_date',
        'Backup_Date', 'BACKUP_DATE', 'backup_date',
        'Last_Backup', 'LAST_BACKUP', 'last_backup',
        'Backup_Time', 'BACKUP_TIME', 'backup_time',
        'Date', 'DATE', 'date',
        'Time', 'TIME', 'time',
    ]

    for col_name in possible_timestamp_columns:
        if col_name in row:
            timestamp = row[col_name]
            timestamp_column = col_name
            break

    if not timestamp:
        # Fallback for backup data
        if 'Hours_Since_Backup' in row or 'HOURS_SINCE_BACKUP' in row or 'hours_since_backup' in row:
            hours_col = 'Hours_Since_Backup' if 'Hours_Since_Backup' in row else ('HOURS_SINCE_BACKUP' if 'HOURS_SINCE_BACKUP' in row else 'hours_since_backup')
            hours = row.get(hours_col, None)
            if hours is not None:
                try:
                    hours_val = float(hours) if not isinstance(hours, (int, float)) else hours
                    if 0 <= hours_val < 720:
                        return True
                except (ValueError, TypeError):
                    pass

        # Fallback for aggregated views
        row_keys_original = list(row.keys())
        row_keys_lower = [str(k).lower() for k in row_keys_original]

        aggregation_columns = ['warning', 'critical', 'cnt', 'count', 'abnormalcnt', 'totalcnt',
                              'unhealthy', 'deadlock_count', 'services_down_count', 'normal',
                              'failed', 'delayed', 'failed_count', 'delayed_count', 'processes']
        instance_columns = ['instance', 'instance_name', 'server', 'server_name', 'agname', 'ag_name', 'env']

        has_state_column = 'state' in row_keys_lower
        state_value = None
        if has_state_column:
            state_key = next((k for k in row_keys_original if k.lower() == 'state'), None)
            if state_key:
                state_value = str(row.get(state_key, '')).upper()

        aggregated_state_values = ['WARNING', 'CRITICAL', 'NORMAL', 'UNAVAILABLE', 'HEALTHY', 'UNHEALTHY']
        database_state_values = ['OFFLINE', 'RECOVERING', 'RESTORING', 'RECOVERY_PENDING', 'SUSPECT', 'EMERGENCY']

        is_database_state = has_state_column and state_value in database_state_values
        has_aggregated_state = has_state_column and state_value in aggregated_state_values and not is_database_state
        has_aggregation_columns = any(col in row_keys_lower for col in aggregation_columns)
        has_instance_column = any(col in row_keys_lower for col in instance_columns)

        if (has_aggregation_columns or has_aggregated_state) and has_instance_column:
            return True

        logger.warning(f"No timestamp column found in row. Available columns: {row_keys_original}")
        return False

    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Could not parse timestamp '{timestamp}' from column '{timestamp_column}': {e}")
            return False

    if not isinstance(timestamp, datetime):
        logger.warning(f"Timestamp column '{timestamp_column}' has unexpected type: {type(timestamp)}")
        return False

    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    try:
        if timestamp.tzinfo is not None:
            from datetime import timezone
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)
        is_fresh = timestamp >= cutoff_time
        if not is_fresh:
            logger.debug(f"Stale data detected: {timestamp_column}={timestamp} is older than {minutes} minutes")
        return is_fresh
    except Exception as e:
        logger.warning(f"Error comparing timestamps: {e}")
        return False


def _infer_env_from_instance(instance_name: str) -> str:
    """Infere o ambiente (PRD/QLT/TST) do nome da instancia"""
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


def _detect_env(instance_name: str, env_value: Optional[str] = None) -> str:
    """Detecta ambiente a partir do nome da instancia ou valor fornecido."""
    if env_value and env_value.strip() and env_value.strip() != 'Undefined':
        return env_value.strip()
    return _infer_env_from_instance(instance_name or '')


def _count_by_env(instances: List[Dict[str, Any]], env_key: str = 'Env') -> Dict[str, int]:
    """Conta instancias por ambiente (PRD, QLT, TST, Undefined)"""
    counts = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
    for row in instances:
        if not row:
            continue
        env = (row.get(env_key) or row.get('ENV') or row.get('Env') or row.get('Environment') or row.get('environment') or '').strip()
        if not env or env == 'Undefined':
            instance_name = (row.get('Instance') or row.get('INSTANCE') or row.get('ServerInstance') or row.get('SERVER_INSTANCE') or '').strip()
            env = _infer_env_from_instance(instance_name)
        env_upper = env.upper() if env else 'Undefined'
        if env_upper in ['PRD', 'QLT', 'TST']:
            counts[env_upper] = counts.get(env_upper, 0) + 1
        else:
            counts['Undefined'] = counts.get('Undefined', 0) + 1
    return counts


# FIND censo 2026-08-11 (batch B2): o CARD nao filtrava frescura enquanto a
# MODAL filtra 24h (FRESHNESS_WINDOWS['capacity'] em intelligence_kpis.py) —
# collector parado => card mantinha o numero velho para sempre e a modal
# esvaziava, contradicao garantida no mesmo ecra.
_CAPACITY_FRESHNESS_MIN = 1440  # espelho de FRESHNESS_WINDOWS['capacity'] (nao importar: circular)

_FRESHNESS_TS_COLS = ('last_check', 'update_ts', 'capture_ts', 'capture_time', 'timestamp')


def _fresh_rows(rows: List[Dict[str, Any]], minutes: int) -> List[Dict[str, Any]]:
    """Filtra linhas por frescura QUANDO ha coluna de timestamp; sem timestamp
    a linha passa (fail-open). Deliberadamente diferente do is_data_fresh da
    modal (fail-closed): views vivas como a DISK_USAGE_AGG (Wave T) nao expoem
    Last_Check — fail-closed zeraria o card para sempre. Quando essas views
    ganharem timestamp, a simetria com a modal fica automatica."""
    cutoff = datetime.now() - timedelta(minutes=minutes)
    out = []
    for row in rows:
        if not row:
            continue
        ts = None
        for k in row.keys():
            if k.lower() in _FRESHNESS_TS_COLS:
                ts = row[k]
                break
        if ts is None:
            out.append(row)
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts[:19])
            except (ValueError, TypeError):
                out.append(row)
                continue
        if not isinstance(ts, datetime) or ts >= cutoff:
            out.append(row)
    return out


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


def _load_monitored_servers() -> List[Dict]:
    """Carrega lista de servidores monitorados.

    E6 (2026-08-19): fonte = metadata.monitored_server via services.inventory_repo
    (BD alimentada pelo servers.json canonico do collector), fallback ao ficheiro
    local. Antes lia Path("config/servers.json") relativo ao CWD (quebrava como
    Windows Service). Mesma forma de retorno (lista de dicts estilo servers.json).
    """
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


# ========================================
# DASHBOARD KPI RESULTS TEMPLATE
# ========================================

def init_dashboard_results() -> Dict[str, Any]:
    """Returns the empty results dict template for the dashboard endpoint."""
    return {
        "db_availability": {
            "abnormal_count": 0,
            "total_count": 0,
            "total_databases": 0,
            "instances": []
        },
        "db_disk_file_system": {
            "critical_count": 0,
            "warning_count": 0,
            "instances": []
        },
        "db_transaction_logs": {
            "critical_count": 0,
            "warning_count": 0,
            "instances": []
        },
        "always_on": {
            "unhealthy_count": 0,
            "instances": []
        },
        "filegroup_usage": {
            "warning_count": 0,
            "critical_count": 0,
            "instances": []
        },
        "blocked_sessions": {
            "count": 0,
            "instances": []
        },
        "blocked_users": {
            "count": 0,
            "instances": []
        },
        "processes_alarm": {
            "count": 0,
            "instances": []
        },
        "lock_count": {
            "warning_count": 0,
            "critical_count": 0,
            "instances": []
        },
        "instance_availability": {
            "off_count": 0,
            "ok_count": 0,
            "instances": []
        },
        "backup_status": {
            "failed_count": 0,           # Wave O: FULL+DIFF+OTHER sysjobhistory, 7d (retrocompat: soma dos 3 abaixo)
            "full_failed_count": 0,       # 2026-07-28: FULL isolado -- parte a cadeia de recuperacao
            "diff_failed_count": 0,       # 2026-07-28: DIFF isolado -- depende do ultimo FULL
            "other_failed_count": 0,      # 2026-07-28: jobs sem convencao de nome reconhecida
            "log_failed_count": 0,        # Wave O NEW: LOG sysjobhistory, 24h
            # 2026-07-28 (owner): is_damaged e no_checksum estavam SOMADOS numa
            # linha so. Sao coisas diferentes: damaged = falha real (backup
            # inutilizavel); no_checksum = estado de CONFIGURACAO que nao muda de
            # ciclo para ciclo. Somados, o volume do segundo (config) escondia o
            # primeiro (falha).
            "is_damaged_count": 0,        # backupset danificado -- falha real
            "no_checksum_count": 0,       # WITH CHECKSUM desligado -- config, informativo
            "delayed_count": 0,           # Wave D: gap RPO threshold-based
            "instances": []
        },
        "deadlocks": {
            "count": 0,
            "count_critical": 0,
            "count_warning": 0,
            "count_info": 0,
            "instances": [],
            "count_by_env": {}
        },
        "service_status": {
            "down_count": 0,
            "instances": []
        },
        "error_log": {
            "critical_count": 0,
            "warning_count": 0,
            "instances": []
        },
        "db_io_stats": {
            "high_read_count": 0,
            "high_write_count": 0,
            "total_databases": 0,
            "instances": []
        },
        "tempdb_status": {
            "critical_count": 0,
            "warning_count": 0,
            "idle_high_count": 0,
            "instances": [],
            "critical_by_env": {},
            "warning_by_env": {}
        },
        "mirroring_status": {
            "unhealthy_count": 0,
            "total_count": 0,
            "instances": [],
            "by_env": {}
        },
        "server_offline_status": {
            "total_events": 0,
            "servers_offline": 0,
            "servers_sql_down": 0,
            "servers_partial": 0,
            "overall_status": "OK",
            "last_event_time": None,
            "instances": [],
            "by_env": {}
        },
        "cpu_critical": {
            "count": 0,
            "instances": [],
            "count_by_env": {}
        },
        "memory_critical": {
            "count": 0,
            "instances": [],
            "count_by_env": {}
        },
        "disk_latency": {
            "critical_count": 0,
            "warning_count": 0,
            "instances": [],
            "critical_by_env": {},
            "warning_by_env": {}
        },
        "jobs_status": {
            "failed_count": 0,
            "collision_count": 0,
            "instances": [],
            "failed_by_env": {},
            "failed_by_type": {},
            "collision_by_env": {}
        }
    }


# ========================================
# DASHBOARD KPI COLLECTOR FUNCTIONS
# ========================================

async def collect_db_availability(results: Dict[str, Any]) -> None:
    """Collect DB Availability KPIs: abnormal count, total, ok instances, by environment."""
    try:
        # 1.1 DB Not Availability - PROBLEM_VIEW
        query_not_available = f"""
        SELECT COUNT(*) AS cnt
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_PROBLEM_VIEW WITH (NOLOCK)
        """
        not_available_data = await execute_intelligence_query_async(query_not_available, raise_on_error=False) or []

        abnormal_count = 0
        if not_available_data and len(not_available_data) > 0:
            abnormal_count = int(not_available_data[0].get('cnt', 0) or 0)

        # DB Not Availability conta apenas DBs com estado anormal em servidores ACESSIVEIS.
        # Servidores offline (ping fail) sao cobertos pelo card "Instances Off" —
        # inflar este card com DBs de servidores inacessiveis seria noise.
        logger.debug(f"DB Not Availability: {abnormal_count} databases com problemas (PROBLEM_VIEW)")
        results["db_availability"]["abnormal_count"] = abnormal_count

        # Buscar instancias agregadas para o modal
        query_abnormal_instances = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW WITH (NOLOCK)
        WHERE AbnormalCnt > 0
        """
        abnormal_instances = await execute_intelligence_query_async(query_abnormal_instances, raise_on_error=False) or []
        results["db_availability"]["instances"] = abnormal_instances

        # Calcular total_count
        try:
            query_total_all = f"""
            SELECT COUNT(*) AS TOTAL_DATABASES
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK)
            """
            total_all_data = await execute_intelligence_query_async(query_total_all, raise_on_error=False)
            if total_all_data and total_all_data[0].get('TOTAL_DATABASES'):
                current_total = int(total_all_data[0]['TOTAL_DATABASES'])
                results["db_availability"]["total_count"] = current_total
                results["db_availability"]["total_databases"] = current_total
                _last_known_values['db_availability_total'] = current_total
                logger.debug(f"DB Availability Total: {current_total}")
            else:
                results["db_availability"]["total_count"] = 0
                results["db_availability"]["total_databases"] = 0

            _last_known_values['last_abnormal_count'] = abnormal_count

            # Calcular por ambiente
            try:
                # Classificacao por INST_ENVS, nao por LIKE no nome.
                # Este fix foi aplicado a 2026-08-07 a query IRMA
                # (instance_availability.ok_by_env) mas NAO foi propagado aqui --
                # ficou meia regressao, e e' o que produz o bucket 'Undefined'
                # que faz a soma por ambiente (1430) nao bater com o total (1455).
                # QA externo 6o passe, B-01.
                query_db_by_env = f"""
                SELECT ISNULL(e.Env, 'Undefined') AS Env, COUNT(*) AS Cnt
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_ACTIVE d WITH (NOLOCK)
                LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
                    ON e.Instance = d.Instance
                WHERE d.[State] = 'ONLINE'
                GROUP BY ISNULL(e.Env, 'Undefined')
                """
                db_by_env_data = await execute_intelligence_query_async(query_db_by_env, raise_on_error=False) or []
                db_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
                total_available = 0
                for row in db_by_env_data:
                    env = row.get('Env', 'Undefined')
                    cnt = int(row.get('Cnt', 0))
                    db_by_env[env] = cnt
                    total_available += cnt

                results["db_availability"]["by_environment"] = {
                    "PRD": db_by_env['PRD'],
                    "TST": db_by_env['TST'],
                    "QLT": db_by_env['QLT'],
                    "TOTAL": total_available
                }
                logger.debug(f"DB Availability por ambiente: {results['db_availability']['by_environment']}")
            except Exception as e:
                logger.warning(f"Erro ao calcular DB Availability por ambiente: {e}")
        except Exception as e:
            logger.warning(f"Erro ao calcular total_count: {e}")
            if _last_known_values['db_availability_total'] is not None:
                results["db_availability"]["total_count"] = _last_known_values['db_availability_total']
                results["db_availability"]["total_databases"] = _last_known_values['db_availability_total']
            else:
                results["db_availability"]["total_count"] = 0
                results["db_availability"]["total_databases"] = 0

        # Calcular ok_instances_count com logica de persistencia
        try:
            if abnormal_count == 0:
                if _last_known_values['db_availability_ok'] is not None:
                    results["db_availability"]["ok_instances_count"] = _last_known_values['db_availability_ok']
                    logger.debug(f"DB Availability OK: Mantendo ultimo valor conhecido: {_last_known_values['db_availability_ok']}")
                else:
                    query_ok_databases = f"""
                    SELECT COUNT(*) AS DB_Availability
                    FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_ACTIVE WITH (NOLOCK)
                    WHERE [State] = 'ONLINE'
                    """
                    ok_databases_data = await execute_intelligence_query_async(query_ok_databases, raise_on_error=False)
                    if ok_databases_data and ok_databases_data[0].get('DB_Availability'):
                        current_value = int(ok_databases_data[0]['DB_Availability'])
                        if current_value > 0:
                            results["db_availability"]["ok_instances_count"] = current_value
                            _last_known_values['db_availability_ok'] = current_value
                            logger.debug(f"DB Availability OK: Primeiro valor calculado (databases ONLINE): {current_value}")
                        else:
                            logger.debug("DB Availability OK: Valor inicial e 0, aguardando proxima atualizacao")
                            results["db_availability"]["ok_instances_count"] = 0
                    else:
                        results["db_availability"]["ok_instances_count"] = 0
            else:
                query_ok_databases = f"""
                SELECT COUNT(*) AS DB_Availability
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_ACTIVE WITH (NOLOCK)
                WHERE [State] = 'ONLINE'
                """
                ok_databases_data = await execute_intelligence_query_async(query_ok_databases, raise_on_error=False)
                # RATCHET REMOVIDO (QA externo 6o passe, 2026-08-18).
                # Havia aqui um min(current_value, ultimo_valor) sobre um dict
                # GLOBAL de modulo: o numero SO PODIA DESCER, nunca subir, ate'
                # alguem reiniciar o servico. O proprio log dizia "Mantendo ultimo
                # valor conhecido (nao aumenta)".
                # Efeito pratico: um incidente RESOLVIDO continuava a parecer em
                # curso -- num produto de monitorizacao, e' o oposto do que se pede.
                # Se algum dia for preciso suavizar flapping, o sitio e' um TTL
                # curto, nunca um minimo perpetuo.
                if ok_databases_data and ok_databases_data[0].get('DB_Availability'):
                    current_value = int(ok_databases_data[0]['DB_Availability'])
                    results["db_availability"]["ok_instances_count"] = current_value
                    _last_known_values['db_availability_ok'] = current_value
                else:
                    # Sem leitura: manter o ultimo conhecido e' aceitavel (e' o
                    # dado mais recente que temos), mas nao inventar zero.
                    last = _last_known_values.get('db_availability_ok')
                    results["db_availability"]["ok_instances_count"] = last if last is not None else 0
        except Exception as e:
            logger.warning(f"Erro ao calcular ok_instances_count: {e}")
            if _last_known_values['db_availability_ok'] is not None:
                results["db_availability"]["ok_instances_count"] = _last_known_values['db_availability_ok']
            else:
                results["db_availability"]["ok_instances_count"] = 0

    except Exception as e:
        logger.error(f"Erro ao buscar DB Availability: {e}")
        if "ok_instances_count" not in results["db_availability"]:
            results["db_availability"]["ok_instances_count"] = 0


async def collect_disk_and_tlog(results: Dict[str, Any]) -> None:
    """Collect Disk File System and Transaction Logs KPIs."""
    # DB Disk File System
    try:
        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
        WHERE Critical > 0 OR Warning > 0
        """
        disk_data = await execute_intelligence_query_async(query, raise_on_error=False) or []
        disk_data = _fresh_rows(disk_data, _CAPACITY_FRESHNESS_MIN)  # simetria com a modal (24h)

        critical_instances = [row for row in disk_data if row.get('Critical', 0) > 0]
        warning_instances = [row for row in disk_data if row.get('Warning', 0) > 0 and row.get('Critical', 0) == 0]

        results["db_disk_file_system"]["critical_count"] = len(critical_instances)
        results["db_disk_file_system"]["warning_count"] = len(warning_instances)
        results["db_disk_file_system"]["critical_items_total"] = sum(row.get('Critical', 0) for row in disk_data)
        results["db_disk_file_system"]["warning_items_total"] = sum(row.get('Warning', 0) for row in disk_data)
        results["db_disk_file_system"]["instances"] = critical_instances + warning_instances
        results["db_disk_file_system"]["critical_by_env"] = _count_by_env(critical_instances)
        results["db_disk_file_system"]["warning_by_env"] = _count_by_env(warning_instances)
    except Exception as e:
        logger.error(f"Erro ao buscar Disk File System: {e}")

    # DB Transaction Logs
    try:
        # 2026-09-02 (modal por base): a MESMA funcao pura do modal
        # (tlog_usage_classes.classify_tlog) classifica por base com o
        # registry+override (Fase 1.5 lote 3 ja lia via _th) e reproduz a forma
        # LEGADA por instancia (Instance/Env/Total_Databases/Critical/Warning/
        # Normal/Last_Check) para os consumidores do tile nao mudarem. O tile
        # continua a contar INSTANCIAS (owner 02/09: label ja o diz); os
        # contadores por BASE saem ao lado para o cabecalho da modal bater.
        from api.routers.intelligence.tlog_usage_classes import TLOG_BASE_QUERY, classify_tlog
        tlog_rows = await execute_intelligence_query_async(
            TLOG_BASE_QUERY.format(schema=INTELLIGENCE_SCHEMA), raise_on_error=False) or []
        cls = classify_tlog(
            tlog_rows,
            {'warning': _th('tlog_usage', 'warning'), 'critical': _th('tlog_usage', 'critical')},
            fresh_minutes=_CAPACITY_FRESHNESS_MIN,
            log_late_hours=_th('backup_delay_log', 'warning'))
        tlog_data = [a for a in cls["per_instance"] if a["Critical"] > 0 or a["Warning"] > 0]
        critical_instances = [row for row in tlog_data if row.get('Critical', 0) > 0]
        warning_instances = [row for row in tlog_data if row.get('Warning', 0) > 0 and row.get('Critical', 0) == 0]

        results["db_transaction_logs"]["critical_count"] = len(critical_instances)
        results["db_transaction_logs"]["warning_count"] = len(warning_instances)
        results["db_transaction_logs"]["critical_items_total"] = sum(row.get('Critical', 0) for row in tlog_data)
        results["db_transaction_logs"]["warning_items_total"] = sum(row.get('Warning', 0) for row in tlog_data)
        results["db_transaction_logs"]["instances"] = critical_instances + warning_instances
        results["db_transaction_logs"]["critical_by_env"] = _count_by_env(critical_instances)
        results["db_transaction_logs"]["warning_by_env"] = _count_by_env(warning_instances)
        results["db_transaction_logs"]["critical_bases_count"] = cls["bases_critical_count"]
        results["db_transaction_logs"]["warning_bases_count"] = cls["bases_warning_count"]
        results["db_transaction_logs"]["critical_bases_by_env"] = cls["bases_critical_by_env"]
        results["db_transaction_logs"]["warning_bases_by_env"] = cls["bases_warning_by_env"]
        results["db_transaction_logs"]["reconciliation"] = cls["reconciliation"]
        logger.info("TLOG card (02/09) - reconciliation: %s", cls["reconciliation"])
    except Exception as e:
        logger.error(f"Erro ao buscar Transaction Logs: {e}")


async def collect_alwayson(results: Dict[str, Any]) -> None:
    """Collect AlwaysOn Availability Group KPIs."""
    try:
        _has_avail_mode = False
        try:
            _am_check = await execute_intelligence_query_async(
                f"SELECT COL_LENGTH('{INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG', 'Availability_Mode') AS L",
                raise_on_error=False
            )
            if _am_check and _am_check[0].get("L") is not None:
                _has_avail_mode = True
        except Exception:
            pass

        if _has_avail_mode:
            _state_filter = """
                OR (Pri_Synch_State <> 'SYNCHRONIZED' AND Pri_Synch_State IS NOT NULL AND Pri_Synch_State <> 'UNKNOWN' AND Pri_Synch_State <> ''
                    AND NOT (Pri_Synch_State = 'SYNCHRONIZING' AND ISNULL(Availability_Mode, '') = 'ASYNCHRONOUS_COMMIT'))
                OR (Sec_Synch_State <> 'SYNCHRONIZED' AND Sec_Synch_State IS NOT NULL AND Sec_Synch_State <> 'UNKNOWN' AND Sec_Synch_State <> ''
                    AND NOT (Sec_Synch_State = 'SYNCHRONIZING' AND ISNULL(Availability_Mode, '') = 'ASYNCHRONOUS_COMMIT'))
            """
        else:
            _state_filter = """
                OR (Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Pri_Synch_State IS NOT NULL)
                OR (Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Sec_Synch_State IS NOT NULL)
            """

        query_unhealthy = f"""
        SELECT COUNT(DISTINCT Instance) AS Always_On_UnHealthy
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
        WHERE Update_TS >= DATEADD(MINUTE, -{FRESHNESS_WINDOWS['alwayson']}, GETDATE())
        AND (
            (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
            OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
            {_state_filter}
            OR Pri_Is_Suspended = 1
            OR Sec_Is_Suspended = 1
        )
        """
        unhealthy_count_data = await execute_intelligence_query_async(query_unhealthy, raise_on_error=False)
        unhealthy_count = int(unhealthy_count_data[0].get('Always_On_UnHealthy', 0)) if unhealthy_count_data and unhealthy_count_data[0].get('Always_On_UnHealthy') else 0
        results["always_on"]["unhealthy_count"] = unhealthy_count

        query_stg_instances = f"""
        SELECT
            s.AgName,
            s.Instance,
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
            {_state_filter}
            OR s.Pri_Is_Suspended = 1
            OR s.Sec_Is_Suspended = 1
        )
        ORDER BY s.Instance
        """
        unhealthy_instances = await execute_intelligence_query_async(query_stg_instances, raise_on_error=False) or []
        for row in unhealthy_instances:
            reasons = row.get('Problem_Reasons', '') or ''
            if reasons.endswith('; '):
                row['Problem_Reasons'] = reasons[:-2]

        results["always_on"]["instances"] = unhealthy_instances
        results["always_on"]["unhealthy_by_env"] = _count_by_env(unhealthy_instances)
    except Exception as e:
        logger.error(f"Erro ao buscar Always On: {e}")


async def collect_mirroring(results: Dict[str, Any]) -> None:
    """Collect Mirroring Status KPIs."""
    try:
        query_issues = f"""
        SELECT COUNT(*) AS Mirroring_Issues
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_MIRRORING_STATUS_DET_VIEW WITH (NOLOCK)
        """
        issues_data = await execute_intelligence_query_async(query_issues, raise_on_error=False)
        unhealthy_count = int(issues_data[0].get('Mirroring_Issues', 0)) if issues_data and issues_data[0].get('Mirroring_Issues') else 0
        results["mirroring_status"]["unhealthy_count"] = unhealthy_count

        query_total = f"""
        SELECT COUNT(*) AS Total_Mirroring
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_MIRRORING_STATUS_ACTIVE WITH (NOLOCK)
        """
        total_data = await execute_intelligence_query_async(query_total, raise_on_error=False)
        total_count = int(total_data[0].get('Total_Mirroring', 0)) if total_data and total_data[0].get('Total_Mirroring') else 0
        results["mirroring_status"]["total_count"] = total_count

        query_total_by_env = f"""
        SELECT
            CASE
                WHEN Env IN ('PRD', 'PROD') THEN 'PRD'
                WHEN Env IN ('QLT', 'QUAL') THEN 'QLT'
                WHEN Env IN ('TST', 'TEST', 'DEV') THEN 'TST'
                ELSE 'Undefined'
            END as Env,
            COUNT(*) as Cnt
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_MIRRORING_STATUS_ACTIVE WITH (NOLOCK)
        GROUP BY
            CASE
                WHEN Env IN ('PRD', 'PROD') THEN 'PRD'
                WHEN Env IN ('QLT', 'QUAL') THEN 'QLT'
                WHEN Env IN ('TST', 'TEST', 'DEV') THEN 'TST'
                ELSE 'Undefined'
            END
        """
        total_by_env_data = await execute_intelligence_query_async(query_total_by_env, raise_on_error=False) or []
        total_by_env = {row.get('Env', 'Undefined'): row.get('Cnt', 0) for row in total_by_env_data}
        results["mirroring_status"]["total_by_env"] = total_by_env

        if unhealthy_count > 0:
            query_instances = f"""
            SELECT Instance, [Database], Mirroring_Role, Mirroring_State, Database_State,
                   Partner_Instance, Env, Problem_Reason, Update_TS
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_MIRRORING_STATUS_DET_VIEW WITH (NOLOCK)
            ORDER BY Env, Instance, [Database]
            """
            instances = await execute_intelligence_query_async(query_instances, raise_on_error=False) or []
            results["mirroring_status"]["instances"] = instances
            results["mirroring_status"]["by_env"] = _count_by_env(instances)
            # 2026-08-18: DET_VIEW so' traz os nao-saudaveis -> by_env == unhealthy_by_env.
            # Alias para o filtro por ambiente (ev(mi,'unhealthy_count')->unhealthy_by_env).
            results["mirroring_status"]["unhealthy_by_env"] = results["mirroring_status"]["by_env"]

        logger.debug(f"Mirroring Status: {unhealthy_count} problemas de {total_count} total")
    except Exception as e:
        logger.error(f"Erro ao buscar Mirroring Status: {e}")


async def collect_filegroup_usage(results: Dict[str, Any]) -> None:
    """Collect FileGroup Usage KPIs with effective free space thresholds."""
    try:
        # 2026-07-27 (gate v1-intel, Opcao A): Growth_Type='UNLIMITED' sai do
        # calculo por alocado — o collector activo grava Max_Size_MB como CLONE
        # de Total_MB (nunca maior), pelo que o ramo maxsize-aware era morto e
        # todo o ficheiro autogrow ~cheio do alocado contava CRITICAL (ruido
        # estrutural; risco de disco real e' coberto pela aba Space, disk-aware).
        query = f"""
        ;WITH fg_effective AS (
            SELECT
                f.Instance,
                e.Env,
                CASE
                    WHEN ISNULL(f.Growth_Type, '') = 'UNLIMITED' THEN NULL
                    WHEN ISNULL(f.Max_Size_MB, 0) > 0 AND f.Max_Size_MB > f.Total_MB
                    THEN (f.Max_Size_MB - f.Used_MB) * 100.0 / NULLIF(f.Max_Size_MB, 0)
                    ELSE 100.0 - f.Percent_Used
                END AS Eff_Free_Pct
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
            LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = f.Instance
            WHERE f.Percent_Used > 80
        )
        SELECT
            Instance,
            ISNULL(Env, 'Undefined') AS Env,
            SUM(CASE WHEN Eff_Free_Pct >= {_th('filegroup_free_pct', 'warning')} AND Eff_Free_Pct < 10 THEN 1 ELSE 0 END) AS Attention,
            SUM(CASE WHEN Eff_Free_Pct >= {_th('filegroup_free_pct', 'critical')} AND Eff_Free_Pct < {_th('filegroup_free_pct', 'warning')} THEN 1 ELSE 0 END) AS Warning,
            SUM(CASE WHEN Eff_Free_Pct < {_th('filegroup_free_pct', 'critical')} THEN 1 ELSE 0 END) AS Critical
        FROM fg_effective
        WHERE Eff_Free_Pct IS NOT NULL
        GROUP BY Instance, Env
        HAVING SUM(CASE WHEN Eff_Free_Pct < 10 THEN 1 ELSE 0 END) > 0
        """
        fg_data = await execute_intelligence_query_async(query, raise_on_error=False) or []

        # Fase 2 (2026-07-27, modelo owner): UNLIMITED e' disk-bound — o teto
        # real e' o volume. Fonte: DATAFILES_STG (Is_Unlimited + Volume_Free_MB;
        # a FG_USAGE_STG nao tem dados de disco). Limiar ABSOLUTO (a STG nao tem
        # Volume_Total => % indisponivel); defaults critico <=5GB, aviso <=10GB,
        # configuraveis desde a Fase 1.5 (filegroup_unlimited_free_gb — o WHERE
        # deriva do warning: nao ha tier de folga acima dele, subir o aviso sem
        # mover o WHERE esconderia linhas em silencio).
        # DECISAO owner 2026-07-27 (2a iteracao, pos-prova 408 F:\ 683GB livres):
        # Volume_Free_MB=0 = cegueira de coleta (mount points 408/412 + SQL
        # antigo SCCM/SQLIJSPRD03) => conta como AVISO "sem visibilidade", nao
        # critico — critico fica reservado a discos comprovadamente no limiar.
        # Classe desaparece com a wave do collector (CROSS APPLY volume_stats
        # por ficheiro + fallback SQL antigo). Conta DRIVES por instancia.
        fgu_warn_mb = float(_th('filegroup_unlimited_free_gb', 'warning')) * 1024
        fgu_crit_mb = float(_th('filegroup_unlimited_free_gb', 'critical')) * 1024
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
            SUM(CASE WHEN v.Vol_Free_MB > 0 AND v.Vol_Free_MB <= {fgu_crit_mb} THEN 1 ELSE 0 END) AS Critical
        FROM vol v
        LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e ON e.Instance = v.Instance
        GROUP BY v.Instance, e.Env
        HAVING SUM(CASE WHEN v.Vol_Free_MB <= {fgu_warn_mb} THEN 1 ELSE 0 END) > 0
        """
        disk_rows = await execute_intelligence_query_async(disk_query, raise_on_error=False) or []
        if disk_rows:
            by_inst = {r.get('Instance'): r for r in fg_data}
            for dr in disk_rows:
                row = by_inst.get(dr.get('Instance'))
                if row:
                    row['Critical'] = (row.get('Critical', 0) or 0) + (dr.get('Critical', 0) or 0)
                    row['Warning'] = (row.get('Warning', 0) or 0) + (dr.get('Warning', 0) or 0)
                else:
                    fg_data.append(dr)

        critical_instances = [row for row in fg_data if row.get('Critical', 0) > 0]
        warning_instances = [row for row in fg_data if row.get('Warning', 0) > 0]
        attention_instances = [row for row in fg_data if row.get('Attention', 0) > 0]

        critical_filegroups_total = sum(row.get('Critical', 0) for row in fg_data)
        warning_filegroups_total = sum(row.get('Warning', 0) for row in fg_data)
        attention_filegroups_total = sum(row.get('Attention', 0) for row in fg_data)

        results["filegroup_usage"]["critical_count"] = len(critical_instances)
        results["filegroup_usage"]["warning_count"] = len(warning_instances)
        results["filegroup_usage"]["attention_count"] = len(attention_instances)
        results["filegroup_usage"]["critical_items_total"] = critical_filegroups_total
        results["filegroup_usage"]["warning_items_total"] = warning_filegroups_total
        results["filegroup_usage"]["attention_items_total"] = attention_filegroups_total
        results["filegroup_usage"]["critical_filegroups_total"] = critical_filegroups_total
        results["filegroup_usage"]["warning_filegroups_total"] = warning_filegroups_total
        results["filegroup_usage"]["attention_filegroups_total"] = attention_filegroups_total
        results["filegroup_usage"]["critical_instances_count"] = len(critical_instances)
        results["filegroup_usage"]["warning_instances_count"] = len(warning_instances)
        results["filegroup_usage"]["attention_instances_count"] = len(attention_instances)

        critical_fg_by_env = {}
        warning_fg_by_env = {}
        attention_fg_by_env = {}
        for row in critical_instances:
            env = row.get('Env', 'Undefined') or 'Undefined'
            critical_fg_by_env[env] = critical_fg_by_env.get(env, 0) + row.get('Critical', 0)
        for row in warning_instances:
            env = row.get('Env', 'Undefined') or 'Undefined'
            warning_fg_by_env[env] = warning_fg_by_env.get(env, 0) + row.get('Warning', 0)
        for row in attention_instances:
            env = row.get('Env', 'Undefined') or 'Undefined'
            attention_fg_by_env[env] = attention_fg_by_env.get(env, 0) + row.get('Attention', 0)
        results["filegroup_usage"]["critical_filegroups_by_env"] = critical_fg_by_env
        results["filegroup_usage"]["warning_filegroups_by_env"] = warning_fg_by_env
        # 2026-08-18: alias com o nome que ev(fg,'critical_items_total') deriva (por-item, nao por-instancia).
        results["filegroup_usage"]["critical_items_total_by_env"] = critical_fg_by_env
        results["filegroup_usage"]["warning_items_total_by_env"] = warning_fg_by_env
        results["filegroup_usage"]["attention_filegroups_by_env"] = attention_fg_by_env

        results["filegroup_usage"]["critical_instances"] = critical_instances
        results["filegroup_usage"]["warning_instances"] = warning_instances
        results["filegroup_usage"]["attention_instances"] = attention_instances
        results["filegroup_usage"]["instances"] = critical_instances

        results["filegroup_usage"]["critical_by_env"] = _count_by_env(critical_instances)
        results["filegroup_usage"]["warning_by_env"] = _count_by_env(warning_instances)
        results["filegroup_usage"]["attention_by_env"] = _count_by_env(attention_instances)
    except Exception as e:
        logger.error(f"Erro ao buscar FileGroup Usage: {e}")


async def collect_realtime_kpis(results: Dict[str, Any]) -> None:
    """Collect real-time KPIs: Blocked Sessions, Blocked Users, Long Locks, Processes."""
    # Blocked Sessions
    try:
        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
        WHERE Blocked_Count > 0
        """
        all_blocked_instances = await execute_intelligence_query_async(query, raise_on_error=False) or []
        blocked_instances = [row for row in all_blocked_instances if is_data_fresh(row, FRESHNESS_WINDOWS['real_time'])]
        results["blocked_sessions"]["count"] = len(blocked_instances)
        results["blocked_sessions"]["instances"] = blocked_instances
        results["blocked_sessions"]["data_source"] = "intelligence_aggregated"
        results["blocked_sessions"]["count_by_env"] = _count_by_env(blocked_instances)
    except Exception as e:
        logger.error(f"Erro ao buscar Blocked Sessions: {e}")

    # Blocked Users
    try:
        query_blocked_users = f"""
        SELECT COUNT(DISTINCT [User]) AS Blocked_Users
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
        WHERE Blocked_Count > 0
            AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())
        """
        blocked_users_count_data = await execute_intelligence_query_async(query_blocked_users, raise_on_error=False)
        blocked_users_count = int(blocked_users_count_data[0].get('Blocked_Users', 0)) if blocked_users_count_data and blocked_users_count_data[0].get('Blocked_Users') else 0
        results["blocked_users"]["count"] = blocked_users_count

        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
        WHERE Blocked_Count > 0
            AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())
        """
        blocked_users_data = await execute_intelligence_query_async(query, raise_on_error=False) or []
        results["blocked_users"]["instances"] = blocked_users_data
        results["blocked_users"]["count_by_env"] = _count_by_env(blocked_users_data)
    except Exception as e:
        logger.error(f"Erro ao buscar Blocked Users: {e}")

    # Long Locks
    try:
        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
        WHERE Total_Locks > 0
        """
        locks_data = await execute_intelligence_query_async(query, raise_on_error=False) or []
        critical_locks = [row for row in locks_data if row.get('Duration_Sec', 0) > _th('long_locks', 'critical')]
        warning_locks = [row for row in locks_data if _th('long_locks', 'warning') < row.get('Duration_Sec', 0) <= _th('long_locks', 'critical')]
        results["lock_count"]["critical_count"] = len(critical_locks)
        results["lock_count"]["warning_count"] = len(warning_locks)
        results["lock_count"]["instances"] = critical_locks + warning_locks
    except Exception as e:
        logger.error(f"Erro ao buscar Long Locks: {e}")

    # Processes
    try:
        # Fase 1.5 lote 3 (2026-08-13): WHERE dinamico sobre o RAW
        # (Runnable_Count) em vez do State da view — baixar o warning abaixo
        # de 20 tem de trazer linhas que a view classifica 'OK'. State
        # reescrito no backend (comparacao estrita >, como a view).
        pr_warn = float(_th('processes_runnable', 'warning'))
        pr_crit = float(_th('processes_runnable', 'critical'))
        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
        WHERE Runnable_Count > {pr_warn}
        """
        processes_data = await execute_intelligence_query_async(query, raise_on_error=False) or []
        for row in processes_data:
            rc = int(row.get('Runnable_Count') or 0)
            row['State'] = 'CRITICAL' if rc > pr_crit else 'WARNING'
        results["processes_alarm"]["count"] = len(processes_data)
        results["processes_alarm"]["instances"] = processes_data
        results["processes_alarm"]["count_by_env"] = _count_by_env(processes_data)
    except Exception as e:
        logger.error(f"Erro ao buscar Processes: {e}")


async def collect_instance_availability(results: Dict[str, Any]) -> None:
    """Collect Instance Availability KPIs (OK/Off counts, offline instances)."""
    try:
        # Instances OK count
        query_ok_count = f"""
        SELECT COUNT(DISTINCT Instance) AS Instancias_OK
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WITH (NOLOCK)
        WHERE Is_Available = 1
        """
        ok_count_data = await execute_intelligence_query_async(query_ok_count, raise_on_error=False)
        ok_count = int(ok_count_data[0].get('Instancias_OK', 0)) if ok_count_data and ok_count_data[0].get('Instancias_OK') else 0

        # Instances Off - servidores com PING falhou e evento nao resolvido
        # GROUPED_VIEW ja filtra Is_Resolved=0 e Event_Time >= -7 dias
        query_off_count = f"""
        SELECT COUNT(DISTINCT Instance) AS Instances_Off
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
        WHERE Ping_OK = 0
        """
        off_count_data = await execute_intelligence_query_async(query_off_count, raise_on_error=False)
        off_count = int(off_count_data[0].get('Instances_Off', 0)) if off_count_data and off_count_data[0].get('Instances_Off') else 0

        # OK by environment
        # 2026-08-07: era um CASE com LIKE no NOME da instancia (%PRD%/%QLT%/
        # %TST%/%DEV%). Classificava mal 4 servidores da frota:
        #   SQLSCOMINSTP03_I03, SQLSCOMINSTP04_I04, SCCM2012P01 -> producao,
        #     mas sem "PRD" no nome caiam em 'Undefined' (que o card nem mostra,
        #     logo desapareciam do ecra sem deixar rasto)
        #   SQLMDMDEV03_I01 -> quality, mas o "DEV" no nome punha-o em TST
        # Passa a usar KPI_MSSQL_INST_ENVS, que e' reconciliada a partir do
        # servers.json pela usp_reconcile_inst_envs (hourly). Diferenca medida
        # a 2026-08-07: LIKE dava 37/14/7 + 3 Undefined; INST_ENVS da' 40/15/6.
        # LEFT JOIN + fallback 'Undefined' de proposito: instancia sem linha em
        # INST_ENVS tem de aparecer algures, nunca ser silenciosamente omitida.
        query_ok_by_env = f"""
        SELECT ISNULL(e.Env, 'Undefined') AS Env,
               COUNT(DISTINCT a.Instance) AS Cnt
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE a WITH (NOLOCK)
        LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
            ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(a.Instance)))
        WHERE a.Is_Available = 1
        GROUP BY ISNULL(e.Env, 'Undefined')
        """
        ok_by_env_data = await execute_intelligence_query_async(query_ok_by_env, raise_on_error=False) or []
        ok_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        for row in ok_by_env_data:
            env = row.get('Env', 'Undefined')
            cnt = int(row.get('Cnt', 0))
            ok_by_env[env] = ok_by_env.get(env, 0) + cnt

        # Offline instances for modal
        fresh_off_instances = []
        try:
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
            offline_ping_data = await execute_intelligence_query_async(offline_query, raise_on_error=False) or []

            for row in offline_ping_data:
                fresh_off_instances.append({
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
            logger.debug(f"Instance Availability: {len(fresh_off_instances)} instancias com ping offline")
        except Exception as e_ping:
            logger.warning(f"Erro ao buscar instancias com ping offline: {e_ping}")

        # All instances for AGG view
        query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW WITH (NOLOCK)"
        all_instances = await execute_intelligence_query_async(query, raise_on_error=False) or []

        ok_instances = []
        for row in all_instances:
            row_keys_upper = [k.upper() for k in row.keys()]
            is_ok = False
            if 'IS_AVAILABLE' in row_keys_upper and row.get('Is_Available', 1) == 1:
                is_ok = True
            elif 'OK_COUNT' in row_keys_upper and row.get('Ok_Count', 0) > 0:
                is_ok = True
            elif 'COUNT_OK' in row_keys_upper and row.get('Count_Ok', 0) > 0:
                is_ok = True
            if is_ok:
                ok_instances.append(row)

        results["instance_availability"]["off_count"] = off_count
        _last_known_values['last_instances_off_count'] = off_count
        results["instance_availability"]["instances"] = fresh_off_instances
        results["instance_availability"]["off_by_env"] = _count_by_env(fresh_off_instances)
        results["instance_availability"]["ok_by_env"] = ok_by_env
        results["instance_availability"]["ok_count"] = ok_count
        _last_known_values['instances_ok'] = ok_count
        logger.debug(f"Instance Availability: OK={ok_count}, Off={off_count}")
    except Exception as e:
        logger.error(f"Erro ao buscar Instance Availability: {e}")


def build_offline_hostnames(results: Dict[str, Any]) -> Set[str]:
    """Build set of offline hostnames for filtering false positives in CPU/Memory/Disk."""
    offline_hostnames: Set[str] = set()
    for off_inst in results["instance_availability"].get("instances", []):
        srv = (off_inst.get('Server_Name') or off_inst.get('Instance') or '').upper().split('_')[0]
        if srv:
            offline_hostnames.add(srv)
    if offline_hostnames:
        logger.info(f"Offline hosts para filtro de falsos positivos: {offline_hostnames}")
    return offline_hostnames


# ========================================
# WAVE O (2026-05-21) - Backup Type Classifier
# ========================================
def classify_backup_type(job_name: str) -> str:
    """Classify SQL Server backup type from Job_Name pattern.

    Returns one of: 'FULL', 'DIFF', 'LOG', 'OTHER'.

    Wave O: zero-schema-change classifier baseado em naming convention canonical
    dos jobs cliente (DBA_<TYPE>_BACKUP, CSE07 <Type> Backup, server-specific
    variants tipo DBA_SQLHDSQLT103_I01_LOG_BACKUP). Validado 100% coverage em
    280 sysjobhistory failures reais (254 LOG + 22 DIFF + 4 FULL, 0 OTHER).

    Order matters: LOG check first (jobs tipo DBA_SQLXX_LOG_BACKUP devem
    classificar como LOG, nao OTHER). Substring sufficient sem regex
    (collector ja filtra jobs por categoria/nome backup).
    """
    if not job_name:
        return 'OTHER'
    name = job_name.upper()
    if 'LOG' in name or 'TRANSACTION' in name:
        return 'LOG'
    if 'DIFF' in name or 'INCREMENTAL' in name:
        return 'DIFF'
    if 'FULL' in name or 'COMPLETE' in name:
        return 'FULL'
    return 'OTHER'


# Fase 1 -> Fase 2 (2026-08-21): backup_job_failure_recovered() REMOVIDO.
# A Fase 1 verificava recuperacao job-level no consumidor via AGENT_JOBS_STG
# (so' o ULTIMO run, fail-open com snapshot stale 15 min). A Fase 2 move a
# verificacao para o collector V1 (collect_backup_failures.py, OUTER APPLY a
# sysjobhistory — historico completo): card e modal leem
# Resolved_By_Success_TS directamente da STG (NULL = ainda em falta).
# Historial completo: CHANGELOG_JOBS_COLETA.md 2026-08-21 (V1) + commit
# V3.3 b13a7e2 (Fase 1).


async def collect_backup_status(results: Dict[str, Any]) -> None:
    """Collect Backup Status KPIs — Wave D3 semantic split (3 tiles).

    Wave D refactor (2026-05-13): split de "Failed" gap-based (A5) em 3 KPIs distintos:
      - **failed**       : execution failures REAIS (KPI_MSSQL_BACKUP_EXEC_FAILURES_STG)
                           Fontes: sysjobhistory.run_status=0, backupset.is_damaged=1,
                                   backupset.has_backup_checksum=0.
      - **delayed**      : gap RPO (KPI_MSSQL_BACKUPS_STG) com thresholds warning+critical por tipo
                           FULL warning 120h / critical 168h
                           DIFF warning 24h  / critical 30h
                           LOG  warning 1h   / critical 2h
                           Janela 48h sobre Update_TS (frescura collector).
      - **jobs_disabled**: visibility de SQL Agent jobs com enabled=0 (KPI_MSSQL_BACKUP_JOBS_DISABLED_STG)
                           Edge case: job disabled e esquecido gera GAP sem FAILURE.

    Server-offline filter: ISNULL(a.Is_Available, 1) = 1 (FIND-KPI-OFFLINE-VS-EVENT
    2026-04-23). Backup nao corre em server down — Hours_Since_Backup congela.

    Compat: mantém `failed_count`, `delayed_count`, `failed_by_env`, `delayed_by_env`,
    `instances` (failed + delayed agregados) para tile rendering A5 retrocompat.
    """
    from datetime import datetime, timedelta

    # === TILE 1: Backup Failed (Wave O 2026-05-21 - split em 3 KPIs por classifier) ===
    # Pre-Wave O semantics: 1 tile Backup Failed misturava tudo (sysjobhistory +
    # is_damaged + no_checksum), com hack legacy a confundir DIFF=jobs e
    # LOG=corruption. User reportou que tile mostrava 42218 com "120D 42098L"
    # quando real failures de execucao eram apenas ~280 (98% no_checksum).
    #
    # Wave O 3 KPIs distintos:
    #   - failed (FULL+DIFF+OTHER de sysjobhistory, 7d): execution failures reais
    #     accionaveis. Backup_Type classificado via classify_backup_type(Job_Name).
    #   - log_failed (LOG de sysjobhistory, 24h): log backups falhados em janela
    #     curta (RPO-critical para transaction log). Naming convention cliente
    #     coberta 100% (DBA_<TYPE>_BACKUP, CSE07 <Type> Backup, server-specific
    #     variants tipo DBA_SQLHDSQLT103_I01_LOG_BACKUP).
    #   - no_checksum (is_damaged + no_checksum de backupset, 7d): silent
    #     corruption findings — backups completaram sem CHECKSUM enabled.
    #     Warning nivel, NAO critical (volume alto = config issue, nao failure).
    #
    # Query estende para 7d (window maior dos 3); filtragem por tipo/janela
    # feita em Python via classify_backup_type() para evitar duplicar logica SQL.
    try:
        # Wave R+13 (2026-05-25): removido filtro 7d/24h -- semantica "unresolved-only"
        # mostra falhas que ainda nao foram recuperadas por backup posterior, dentro
        # do natural ceiling de 14d (STG retention). Ver hunk recovery lookup abaixo.
        exec_failures_query = f"""
        SELECT
            f.Instance, f.[Database], f.Job_Name, f.Job_Id,
            f.Step_Id, f.Step_Name, f.Run_Status, f.Run_Datetime,
            f.Run_Duration_Sec, f.Message, f.Failure_Source,
            f.Resolved_By_Success_TS,
            ISNULL(e.Env, 'Undefined') AS Env,
            f.Update_TS
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG AS f WITH (NOLOCK)
        LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
            ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(f.Instance)))
        LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
            ON a.Instance = f.Instance
        WHERE ISNULL(a.Is_Available, 1) = 1
        """
        raw_failures = await execute_intelligence_query_async(exec_failures_query, raise_on_error=False) or []

        # Wave R+13 (2026-05-25): build recovery lookup -- failure considera-se recuperada
        # se existe Last_Backup_Date > failure.Run_Datetime para mesmo (Instance, Database,
        # Backup_Type). Conservativo: Database NULL ou type OTHER nao filtram (show).
        backup_recovery_query = f"""
        SELECT Instance, [Database], Backup_Type, MAX(Last_Backup_Date) AS Last_Backup_Date
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK)
        WHERE Last_Backup_Date IS NOT NULL
        GROUP BY Instance, [Database], Backup_Type
        """
        backup_latest_rows = await execute_intelligence_query_async(backup_recovery_query, raise_on_error=False) or []
        backup_latest: Dict[tuple, datetime] = {}
        _type_map = {'FULL': 'FULL', 'D': 'FULL', 'DIFF': 'DIFF', 'I': 'DIFF', 'LOG': 'LOG', 'L': 'LOG'}
        for _b in backup_latest_rows:
            _inst = (_b.get('Instance', '') or '').upper()
            _db = (_b.get('Database', '') or '').upper()
            _bt = _type_map.get((_b.get('Backup_Type', '') or '').upper())
            _ldt = _b.get('Last_Backup_Date')
            if isinstance(_ldt, str) and _ldt:
                try:
                    _ldt = datetime.fromisoformat(_ldt)
                except ValueError:
                    _ldt = None
            if _bt and isinstance(_ldt, datetime):
                _key = (_inst, _db, _bt)
                if _key not in backup_latest or backup_latest[_key] < _ldt:
                    backup_latest[_key] = _ldt

        # Fase 2 (2026-08-21, council + v1-intel GO): a recuperacao job-level
        # passou a vir do COLLECTOR V1 — coluna Resolved_By_Success_TS na
        # propria STG (OUTER APPLY a sysjobhistory: 1o sucesso step_id=0/
        # run_status=1 POSTERIOR a falha, historico completo e nao so' o
        # ultimo run como na Fase 1 via AGENT_JOBS_STG). O snapshot AGENT_JOBS
        # e o check de staleness 15 min sairam: o veredicto viaja na MESMA row
        # da falha (mesma frescura por construcao). FAIL-OPEN mantido
        # estruturalmente: sem evidencia de sucesso => NULL => falha conta.
        # Janela do collector: 30d (Fase 2; era 7d — fim do aging-out
        # silencioso de jobs com cadencia > 7d).
        recovered_by_type = {'FULL': 0, 'DIFF': 0, 'LOG': 0, 'OTHER': 0}

        failed_data = []          # FULL/DIFF/OTHER sysjobhistory failures (Fase 2: unresolved-only, janela collector 30d)
        failed_log = []           # LOG sysjobhistory failures (Fase 2: unresolved-only, janela collector 30d)
        no_checksum_unique_seen: set = set()  # (Instance, Database) dedupe -- card alinha com modal "1224 de 1224"
        is_damaged_unique_seen: set = set()   # 2026-07-28: dedupe proprio (deixou de partilhar com no_checksum)

        failed_full = []          # 2026-07-28: FULL isolado
        failed_diff = []          # 2026-07-28: DIFF isolado
        failed_other = []         # 2026-07-28: OTHER (job sem convencao reconhecida)

        failed_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        log_failed_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        # 2026-08-18: split por ambiente (dashboard filtra full/diff/other separados)
        full_failed_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        diff_failed_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        other_failed_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        no_checksum_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        is_damaged_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}

        # Backward-compat correcto via classifier (substitui legacy hack)
        failed_by_type = {'FULL': 0, 'DIFF': 0, 'LOG': 0, 'OTHER': 0}
        failed_by_source = {'sysjobhistory': 0, 'is_damaged': 0, 'no_checksum': 0}

        for row in raw_failures:
            # Env normalize (logic preservada de pre-Wave O)
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
            env_key = env.upper() if env.upper() in ('PRD', 'QLT', 'TST') else 'Undefined'

            source = row.get('Failure_Source', 'sysjobhistory')
            if source in failed_by_source:
                failed_by_source[source] += 1

            if source in ('no_checksum', 'is_damaged'):
                # Silent corruption / damaged backupset — KPI dedicada (warning)
                # Wave R+11 REVERTED (2026-05-25): filter FULL+DIFF requeria
                # Backup_Type_Classified column inexistente em STG; ver R+11.2 plan.
                # Wave R+11.3 (2026-05-25): card count + by_env dedupe por
                # (Instance, Database) -- alinha card com modal "1224 de 1224".
                # FIND-20260611-101: raw rows REMOVIDAS do payload — 203k rows
                # (167MB) que nenhum consumidor lia. Modal usa endpoint dedicado
                # instances/backup-no-checksum (SQL GROUP BY, ja agregado).
                unique_key = (row.get('Instance'), row.get('Database'))
                # 2026-07-28: dedupe SEPARADO por fonte. Antes partilhavam o mesmo
                # set, logo uma DB com backup danificado E sem checksum era contada
                # uma unica vez e a natureza da ocorrencia perdia-se.
                if source == 'is_damaged':
                    if unique_key not in is_damaged_unique_seen:
                        is_damaged_unique_seen.add(unique_key)
                        is_damaged_by_env[env_key] = is_damaged_by_env.get(env_key, 0) + 1
                elif unique_key not in no_checksum_unique_seen:
                    no_checksum_unique_seen.add(unique_key)
                    no_checksum_by_env[env_key] = no_checksum_by_env.get(env_key, 0) + 1
            else:
                # sysjobhistory: classify por tipo de backup
                backup_type = classify_backup_type(row.get('Job_Name', '') or '')
                row['Backup_Type_Classified'] = backup_type

                # Wave R+13 (2026-05-25): unresolved-only -- skip se backup posterior
                # ja' completou para mesmo (Instance, Database, Backup_Type).
                # Conservativo: Database NULL ou type OTHER nao filtram (show).
                db_norm = (row.get('Database', '') or '').upper()
                failure_dt = row.get('Run_Datetime')
                if isinstance(failure_dt, str) and failure_dt:
                    try:
                        failure_dt = datetime.fromisoformat(failure_dt)
                    except ValueError:
                        failure_dt = None
                if db_norm and isinstance(failure_dt, datetime) and backup_type in ('FULL', 'DIFF', 'LOG'):
                    rec_key = ((row.get('Instance', '') or '').upper(), db_norm, backup_type)
                    last_bkp = backup_latest.get(rec_key)
                    if last_bkp and last_bkp > failure_dt:
                        # Recovered -- backup posterior teve sucesso, falha resolvida.
                        continue

                # Fase 2 (2026-08-21): recuperacao verificada pelo collector.
                # Tile conta so' "ainda em falta" (IS NULL); recuperados ficam
                # visiveis no modal com badge (nunca desaparecimento silencioso).
                # Valor nao-parseavel => None => conta como em falta (fail-open).
                _rec_at = row.get('Resolved_By_Success_TS')
                if isinstance(_rec_at, str) and _rec_at:
                    try:
                        _rec_at = datetime.fromisoformat(_rec_at)
                    except ValueError:
                        _rec_at = None
                if isinstance(_rec_at, datetime):
                    recovered_by_type[backup_type] = recovered_by_type.get(backup_type, 0) + 1
                    continue

                failed_by_type[backup_type] = failed_by_type.get(backup_type, 0) + 1

                if backup_type == 'LOG':
                    # Wave R+13: removida janela 24h -- show todas LOG failures unresolved.
                    # Ceiling = janela do collector (30d desde a Fase 2 de 21/08; o
                    # "14d STG retention" aqui citado antes nunca foi real).
                    failed_log.append(row)
                    log_failed_by_env[env_key] = log_failed_by_env.get(env_key, 0) + 1
                else:
                    # FULL, DIFF, OTHER -- Wave R+13: removida janela 7d (idem above)
                    failed_data.append(row)
                    failed_by_env[env_key] = failed_by_env.get(env_key, 0) + 1
                    # 2026-07-28 (owner): separar FULL de DIFF. Nao e' cosmetico --
                    # um FULL falhado parte a cadeia de recuperacao; um DIFF
                    # falhado depende do ultimo FULL. Juntos, escondiam qual dos
                    # dois estava partido.
                    if backup_type == 'FULL':
                        failed_full.append(row)
                        full_failed_by_env[env_key] = full_failed_by_env.get(env_key, 0) + 1
                    elif backup_type == 'DIFF':
                        failed_diff.append(row)
                        diff_failed_by_env[env_key] = diff_failed_by_env.get(env_key, 0) + 1
                    else:
                        failed_other.append(row)
                        other_failed_by_env[env_key] = other_failed_by_env.get(env_key, 0) + 1

        # === Write results (Wave O - 3 KPIs distintos + backward-compat) ===
        # KPI 1: Backup Failed (FULL+DIFF+OTHER, 7d)
        results["backup_status"]["failed_count"] = len(failed_data)
        results["backup_status"]["failed_by_env"] = failed_by_env
        results["backup_status"]["failed_instances"] = failed_data
        results["backup_status"]["failed_by_type"] = failed_by_type  # accurate now via classifier

        # KPI 2: Backup Log Failed (LOG, 24h) — NEW Wave O
        results["backup_status"]["log_failed_count"] = len(failed_log)
        results["backup_status"]["log_failed_by_env"] = log_failed_by_env
        results["backup_status"]["log_failed_instances"] = failed_log

        # KPI 3: Backup No-Checksum (silent corruption, 7d) — NEW Wave O
        # Wave R+11.3 (2026-05-25): count = unique (Instance, Database) pairs
        # (alinhado com modal "1224 de 1224").
        # FIND-20260611-101: no_checksum_instances vazio por design — 203k raw
        # rows inflavam o payload do dashboard para 167MB sem nenhum consumidor
        # (frontend usa counts/by_env; modal usa instances/backup-no-checksum).
        results["backup_status"]["no_checksum_count"] = len(no_checksum_unique_seen)
        results["backup_status"]["no_checksum_by_env"] = no_checksum_by_env
        results["backup_status"]["no_checksum_instances"] = []

        # 2026-07-28: is_damaged deixa de estar somado ao no_checksum.
        # NOTA para quem comparar com historico: o no_checksum_count DESCE face a
        # 28/07 porque deixou de incluir os danificados -- nao e' quebra de coleta.
        results["backup_status"]["is_damaged_count"] = len(is_damaged_unique_seen)
        results["backup_status"]["is_damaged_by_env"] = is_damaged_by_env

        # 2026-07-28: FULL / DIFF / OTHER isolados (failed_count mantem-se como
        # soma dos tres, para retrocompat de consumidores existentes)
        results["backup_status"]["full_failed_count"] = len(failed_full)
        results["backup_status"]["diff_failed_count"] = len(failed_diff)
        results["backup_status"]["other_failed_count"] = len(failed_other)
        # 2026-08-18: breakdown por ambiente do split (o dashboard filtra por
        # ev(bk,'full_failed_count')->full_failed_by_env, etc.). As listas ja' tem Env
        # por linha (JOIN INST_ENVS a montante). Sem isto o filtro caia para o total.
        results["backup_status"]["full_failed_by_env"] = full_failed_by_env
        results["backup_status"]["diff_failed_by_env"] = diff_failed_by_env
        results["backup_status"]["other_failed_by_env"] = other_failed_by_env

        # Backward-compat: failed_by_source para frontend A5 retrocompat
        results["backup_status"]["failed_by_source"] = failed_by_source

        # Fase 1 (2026-08-21): contagens excluem recuperados (job-level); os
        # numeros abaixo dao ao portal o "N ja' recuperados" sem re-query.
        results["backup_status"]["full_recovered_count"] = recovered_by_type.get('FULL', 0)
        results["backup_status"]["diff_recovered_count"] = recovered_by_type.get('DIFF', 0)
        results["backup_status"]["log_recovered_count"] = recovered_by_type.get('LOG', 0)
        results["backup_status"]["other_recovered_count"] = recovered_by_type.get('OTHER', 0)
        # Fase 2 (2026-08-21): sempre False — o veredicto de recuperacao vem na
        # propria row da STG (Resolved_By_Success_TS), nao ha snapshot separado
        # que possa estar stale. Campo mantido por retrocompat do payload.
        results["backup_status"]["jobs_snapshot_stale"] = False

        logger.debug(
            f"Backup Status Wave O - failed_data={len(failed_data)} "
            f"log_failed={len(failed_log)} no_checksum_unique={len(no_checksum_unique_seen)} "
            f"by_type={failed_by_type} recovered={recovered_by_type} (Fase 2 collector-side)"
        )
    except Exception as e:
        logger.error(f"Erro Backup Status Wave O: {e}")
        # Defaults para todos os 3 KPIs (evita KeyError no frontend)
        results["backup_status"]["failed_count"] = 0
        results["backup_status"]["failed_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["full_failed_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["diff_failed_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["other_failed_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["failed_instances"] = []
        results["backup_status"]["failed_by_type"] = {'FULL': 0, 'DIFF': 0, 'LOG': 0, 'OTHER': 0}
        results["backup_status"]["log_failed_count"] = 0
        results["backup_status"]["log_failed_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["log_failed_instances"] = []
        results["backup_status"]["no_checksum_count"] = 0
        results["backup_status"]["no_checksum_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["no_checksum_instances"] = []
        results["backup_status"]["failed_by_source"] = {'sysjobhistory': 0, 'is_damaged': 0, 'no_checksum': 0}
        results["backup_status"]["full_recovered_count"] = 0
        results["backup_status"]["diff_recovered_count"] = 0
        results["backup_status"]["log_recovered_count"] = 0
        results["backup_status"]["other_recovered_count"] = 0
        results["backup_status"]["jobs_snapshot_stale"] = False

    # === TILE 2: Backup Delayed (gap RPO threshold-based per type) ===
    # Wave M (2026-05-20): redirect de KPI_MSSQL_BACKUPS_STG (per-instance) para
    # vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE (AG-aware consolidation).
    # Razao: msdb e' local a cada no AG (nao replicado). Apos failover,
    # KPI_MSSQL_BACKUPS_STG mostra dados velhos do novo primary (que tinha role
    # secondary antes) e dados frescos do ex-primary (que agora e secondary).
    # A view consolida via MAX(Last_Backup_Date) por (AgName, Database, Type)
    # usando KPI_MSSQL_ALWAYSON_STATUS_STG para topology map. Standalone DBs
    # passthrough sem mudanca. Coluna Source distingue AG_CONSOLIDATED vs STANDALONE.
    try:
        delayed_query = f"""
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
        backup_data = await execute_intelligence_query_async(delayed_query, raise_on_error=False) or []

        # Wave D thresholds (warning + critical per tipo) — Fase 0 (2026-08-04):
        # valores da fonte unica; Fase 1: _th resolve overrides globais do cliente.
        THRESHOLDS = {
            'FULL': {'warning_h': _th('backup_delay_full', 'warning'), 'critical_h': _th('backup_delay_full', 'critical')},
            'DIFF': {'warning_h': _th('backup_delay_diff', 'warning'), 'critical_h': _th('backup_delay_diff', 'critical')},
            'LOG':  {'warning_h': _th('backup_delay_log', 'warning'),  'critical_h': _th('backup_delay_log', 'critical')},
        }

        # Council 2026-09-01 (R1-R5, doc COUNCIL_BACKUP_DELAYED_SIGNAL): a
        # classificacao mudou-se para o modulo partilhado com o modal
        # (backup_delayed_classes.classify_delayed) — dedupe por BASE no
        # executivo, perdao limitado do chain-reset DIFF, banda propria para
        # schedules DIFF parados, e system DBs de nos AG roteadas com contador.
        # Mapa AG (condicao v1-intel: chave (AgName,Database) nas linhas
        # AG_CONSOLIDATED) — fail-open: sem mapa, cai para (Instance,Database).
        from api.routers.intelligence.backup_delayed_classes import (
            classify_delayed, build_ag_map, AG_MAP_QUERY)
        _ag_rows = await execute_intelligence_query_async(
            AG_MAP_QUERY.format(schema=INTELLIGENCE_SCHEMA), raise_on_error=False) or []
        cls = classify_delayed(backup_data, THRESHOLDS, ag_map=build_ag_map(_ag_rows))

        all_delayed = cls["actionable_critical"] + cls["actionable_warning"]
        # Contagens executivas = BASES (R1). Listas continuam por linha (modal).
        results["backup_status"]["delayed_count"] = cls["bases_critical_count"] + cls["bases_warning_count"]
        results["backup_status"]["delayed_warning_count"] = cls["bases_warning_count"]
        results["backup_status"]["delayed_critical_count"] = cls["bases_critical_count"]
        results["backup_status"]["delayed_critical_by_env"] = cls["delayed_critical_by_env"]
        results["backup_status"]["delayed_warning_by_env"] = cls["delayed_warning_by_env"]
        results["backup_status"]["delayed_by_env"] = cls["delayed_by_env"]
        results["backup_status"]["delayed_by_type"] = cls["delayed_by_type"]
        results["backup_status"]["delayed_instances"] = all_delayed
        # Bandas novas (visiveis — nada desaparece: persona/challenger R5)
        # 2026-09-02: contadores das bandas em BASES (regra R1, coerente com o
        # cabecalho da modal); as listas *_instances continuam por linha.
        results["backup_status"]["diff_schedule_stopped_count"] = cls["diff_schedule_stopped_bases_count"]
        results["backup_status"]["diff_schedule_stopped_instances"] = cls["diff_schedule_stopped"]
        results["backup_status"]["diff_schedule_stopped_by_env"] = cls["diff_schedule_stopped_by_env"]
        results["backup_status"]["ag_system_gap_count"] = cls["ag_system_gap_bases_count"]
        results["backup_status"]["ag_system_gap_instances"] = cls["ag_system_gap"]
        results["backup_status"]["ag_system_gap_by_env"] = cls["ag_system_gap_by_env"]
        results["backup_status"]["chain_reset_count"] = len(cls["chain_reset"])
        results["backup_status"]["delayed_reconciliation"] = cls["reconciliation"]
        logger.info(
            "Backup Delayed (council 01/09) - reconciliation: %s", cls["reconciliation"])
    except Exception as e:
        logger.error(f"Erro Backup Delayed (gap): {e}")
        results["backup_status"]["delayed_count"] = 0
        results["backup_status"]["delayed_warning_count"] = 0
        results["backup_status"]["delayed_critical_count"] = 0
        results["backup_status"]["delayed_critical_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["delayed_warning_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["delayed_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["delayed_by_type"] = {}
        results["backup_status"]["delayed_instances"] = []
        results["backup_status"]["diff_schedule_stopped_count"] = 0
        results["backup_status"]["diff_schedule_stopped_instances"] = []
        results["backup_status"]["ag_system_gap_count"] = 0
        results["backup_status"]["ag_system_gap_instances"] = []
        results["backup_status"]["chain_reset_count"] = 0
        results["backup_status"]["delayed_reconciliation"] = {}

    # === TILE 3: Backup Jobs Disabled (visibility snapshot) ===
    try:
        jobs_disabled_query = f"""
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
        """
        jobs_disabled = await execute_intelligence_query_async(jobs_disabled_query, raise_on_error=False) or []

        jobs_disabled_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        for row in jobs_disabled:
            env = row.get('Env', 'Undefined') or 'Undefined'
            if env == 'Undefined':
                inst_name = (row.get('Instance', '') or '').upper()
                if 'PRD' in inst_name or 'PROD' in inst_name:
                    env = 'PRD'
                elif 'QLT' in inst_name or 'QUAL' in inst_name:
                    env = 'QLT'
                elif 'TST' in inst_name or 'TEST' in inst_name or 'DEV' in inst_name:
                    env = 'TST'
            env_key = env.upper() if env.upper() in ('PRD', 'QLT', 'TST') else 'Undefined'
            jobs_disabled_by_env[env_key] = jobs_disabled_by_env.get(env_key, 0) + 1
            row['Env'] = env

        results["backup_status"]["jobs_disabled_count"] = len(jobs_disabled)
        results["backup_status"]["jobs_disabled_by_env"] = jobs_disabled_by_env
        results["backup_status"]["jobs_disabled_instances"] = jobs_disabled
        logger.debug(f"Backup Jobs Disabled - count={len(jobs_disabled)}, by_env={jobs_disabled_by_env}")
    except Exception as e:
        logger.error(f"Erro Backup Jobs Disabled: {e}")
        results["backup_status"]["jobs_disabled_count"] = 0
        results["backup_status"]["jobs_disabled_by_env"] = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        results["backup_status"]["jobs_disabled_instances"] = []

    # === Backward-compat: frontend Wave A5 esperava `instances` (failed + delayed agregados) ===
    # Wave O: incluir tambem log_failed (execution failures).
    # FIND-20260611-101: no_checksum_instances REMOVIDO do agregado — 203k raw
    # rows (167MB de payload) sem consumidor. Counts/by_env intactos.
    results["backup_status"]["instances"] = (
        results["backup_status"].get("failed_instances", []) +
        results["backup_status"].get("log_failed_instances", []) +
        results["backup_status"].get("delayed_instances", [])
    )
    # Wave O (2026-05-21): legacy hack REMOVIDO. `failed_by_type` agora e' set
    # inline em collect_backup_status com valores reais via classify_backup_type()
    # (FULL/DIFF/LOG/OTHER per Job_Name pattern), substituindo o hack que mappeava
    # DIFF=sysjobhistory + LOG=is_damaged+no_checksum (semanticamente errado e
    # inflado por silent corruption findings). Ver helpers.py:classify_backup_type.


async def collect_service_status(results: Dict[str, Any]) -> None:
    """Collect Service Status KPIs and integrate with Instance Availability."""
    try:
        query = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
        WHERE Services_Down_Count > 0
        """
        service_data = await execute_intelligence_query_async(query, raise_on_error=False) or []
        fresh_service_data = [
            row for row in service_data
            if is_data_fresh(row, FRESHNESS_WINDOWS['services'])
        ]

        results["service_status"]["down_count"] = len(fresh_service_data)
        results["service_status"]["services_down_total"] = sum(
            row.get("Services_Down_Count", 0)
            or row.get("Down_Count", 0)
            or row.get("DOWN", 0)
            or 0
            for row in fresh_service_data
        )
        results["service_status"]["instances"] = fresh_service_data
        results["service_status"]["by_env"] = _count_by_env(fresh_service_data)
        # 2026-08-18: alias para o filtro por ambiente do dashboard (ev(ss,'down_count')->down_by_env)
        results["service_status"]["down_by_env"] = results["service_status"]["by_env"]

        # Integrate critical services down in Instance Availability
        try:
            inst_avail = results.get("instance_availability", {})
            off_instances = inst_avail.get("instances", []) or []

            def _get_instance_key(row: Dict) -> Optional[str]:
                for key in ["Instance", "INSTANCE", "instance", "ServerInstance", "SERVER_INSTANCE", "Server_Instance"]:
                    if key in row and row.get(key):
                        return str(row.get(key))
                return None

            existing_keys = {k for k in (_get_instance_key(r) for r in off_instances) if k}
            extra_off: List[Dict] = []

            for row in fresh_service_data:
                inst_key = _get_instance_key(row)
                if not inst_key or inst_key in existing_keys:
                    continue
                down_cnt = (
                    row.get("Services_Down_Count", 0)
                    or row.get("Down_Count", 0)
                    or row.get("DOWN", 0)
                    or 0
                )
                if down_cnt and down_cnt > 0:
                    extra_off.append(row)
                    existing_keys.add(inst_key)

            if extra_off:
                inst_avail.setdefault("off_count", 0)
                inst_avail.setdefault("instances", off_instances)
                inst_avail["off_count"] = inst_avail["off_count"] + len(extra_off)
                inst_avail["instances"] = off_instances + extra_off
                results["instance_availability"] = inst_avail
        except Exception as e2:
            logger.warning(f"Erro ao integrar Service Status em Instance Availability: {e2}")

    except Exception as e:
        logger.error(f"Erro ao buscar Service Status: {e}")


async def collect_error_log(results: Dict[str, Any]) -> None:
    """Collect Error Log KPIs from STG table."""
    try:
        all_errors = []

        try:
            sample_query = f"SELECT TOP 1 * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)"
            sample = await execute_intelligence_query_async(sample_query, raise_on_error=False)

            if sample and len(sample) > 0:
                available_columns = [k.upper() for k in sample[0].keys()]
                date_column = None

                for col in ['LOG_DATE', 'LOGDATE', 'DATE', 'ERROR_DATE', 'ERRORDATE', 'TIMESTAMP', 'CREATED_DATE', 'CREATEDDATE']:
                    if col in available_columns:
                        for key in sample[0].keys():
                            if key.upper() == col:
                                date_column = key
                                break
                        if date_column:
                            break

                if date_column:
                    query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK) WHERE [{date_column}] >= DATEADD(HOUR, -24, GETDATE())"
                    all_errors = await execute_intelligence_query_async(query, raise_on_error=False) or []
                else:
                    query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)"
                    all_errors = await execute_intelligence_query_async(query, raise_on_error=False) or []
                    if all_errors:
                        cutoff_time = datetime.now() - timedelta(hours=24)
                        filtered_errors = []
                        for row in all_errors:
                            row_date = None
                            for key, value in row.items():
                                if isinstance(value, (datetime, str)) and ('date' in key.lower() or 'time' in key.lower()):
                                    try:
                                        if isinstance(value, str):
                                            row_date = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                        else:
                                            row_date = value
                                        if row_date and row_date >= cutoff_time:
                                            filtered_errors.append(row)
                                        break
                                    except (ValueError, TypeError):
                                        continue
                        all_errors = filtered_errors
            else:
                query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)"
                all_errors = await execute_intelligence_query_async(query, raise_on_error=False) or []
        except Exception as e:
            logger.warning(f"Erro ao descobrir colunas de Error Log, tentando buscar todos: {e}")
            query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)"
            all_errors = await execute_intelligence_query_async(query, raise_on_error=False) or []

        # Agrupar por instancia e contar por severidade
        instance_errors: Dict[str, Dict] = {}
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

        critical_instances = [v for v in instance_errors.values() if v['Critical_Count'] > 0]
        warning_instances = [v for v in instance_errors.values() if v['Warning_Count'] > 0 and v['Critical_Count'] == 0]

        results["error_log"]["critical_count"] = len(critical_instances)
        results["error_log"]["warning_count"] = len(warning_instances)
        results["error_log"]["instances"] = critical_instances + warning_instances
    except Exception as e:
        logger.error(f"Erro ao buscar Error Log: {e}")


async def collect_db_io_stats(results: Dict[str, Any]) -> None:
    """Collect Database I/O Stats KPIs."""
    try:
        query = f"""
        SELECT *
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_IO_STATS_AGG_VIEW WITH (NOLOCK)
        """
        all_io_stats = await execute_intelligence_query_async(query, raise_on_error=False) or []

        high_io_instances = []
        total_databases = 0
        high_read_count = 0
        high_write_count = 0

        for row in all_io_stats:
            db_count = row.get('Total_Databases', 0) or row.get('TotalCnt', 0) or row.get('Cnt', 0) or 0
            if db_count > 0:
                total_databases += db_count

            reads_percent = row.get('Reads_Percent', 0) or row.get('ReadsPercent', 0) or 0
            if reads_percent > 70:
                high_read_count += 1
                high_io_instances.append(row)

            writes_percent = row.get('Writes_Percent', 0) or row.get('WritesPercent', 0) or 0
            if writes_percent > 70 and row not in high_io_instances:
                high_write_count += 1
                high_io_instances.append(row)

        results["db_io_stats"]["high_read_count"] = high_read_count
        results["db_io_stats"]["high_write_count"] = high_write_count
        results["db_io_stats"]["total_databases"] = total_databases
        results["db_io_stats"]["instances"] = high_io_instances
    except Exception as e:
        logger.error(f"Erro ao buscar Database I/O Stats: {e}")


async def collect_tempdb_status(results: Dict[str, Any]) -> None:
    """Collect TempDB Usage KPIs."""
    try:
        critical_instances = []
        warning_instances = []
        critical_count = 0
        warning_count = 0

        tempdb_data = []
        try:
            q_int = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW WITH (NOLOCK)"
            tempdb_data = await execute_intelligence_query_async(q_int, raise_on_error=True) or []
            tempdb_data = _fresh_rows(tempdb_data, _CAPACITY_FRESHNESS_MIN)  # simetria com a modal (24h)
            logger.debug(f"TempDB KPI: usando KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW ({len(tempdb_data)} rows)")
        except Exception as e_int:
            logger.debug(f"TempDB KPI: KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW indisponivel ({e_int}) — retornando 0")

        for row in tempdb_data:
            inst = row.get('Instance', row.get('INSTANCE', row.get('instance', '')))
            if not inst:
                continue
            env = None
            for env_col in ['ENV', 'Environment', 'Env', 'ENVIRONMENT']:
                if env_col in row:
                    env = row.get(env_col)
                    break
            if not env:
                env = _infer_env_from_instance(inst)

            # 2026-08-03 (FIND Saude do Disco): a view expoe Percent_Used — o nome
            # antigo Usage_Percent nunca existiu no schema real, pelo que TODAS as
            # linhas eram ignoradas e o KPI ficava 0 para sempre (mesmo com tempdb
            # cheio). Ler o nome real primeiro; legado mantido como fallback.
            usage_pct_raw = row.get('Percent_Used', row.get('PERCENT_USED', row.get('percent_used',
                row.get('Usage_Percent', row.get('USAGE_PERCENT', row.get('usage_percent', None))))))
            if usage_pct_raw is None:
                continue
            usage_pct = float(usage_pct_raw or 0)
            is_critical = usage_pct >= _th('tempdb_usage', 'critical')
            is_warning = usage_pct >= _th('tempdb_usage', 'warning') and not is_critical
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
                'instance': inst, 'Instance': inst,
                'environment': env, 'Env': env,
                'disk_used_percent': usage_pct,
                'file_size_gb': file_size_gb,
                'disk_free_gb': disk_free_gb,
                'idle_high_sessions': int(row.get('Idle_Sessions', row.get('idle_high_sessions', 0)) or 0),
                'status': 'CRITICAL' if is_critical else 'WARNING',
                'Critical': 1 if is_critical else 0,
                'Warning': 1 if is_warning else 0,
            }
            if is_critical:
                critical_count += 1
                critical_instances.append(instance_data)
            elif is_warning:
                warning_count += 1
                warning_instances.append(instance_data)

        logger.debug(f"TempDB KPI: {critical_count} critical, {warning_count} warning")

        results["tempdb_status"]["critical_count"] = critical_count
        results["tempdb_status"]["warning_count"] = warning_count
        results["tempdb_status"]["idle_high_count"] = 0
        results["tempdb_status"]["instances"] = critical_instances + warning_instances
        results["tempdb_status"]["critical_by_env"] = _count_by_env(critical_instances)
        results["tempdb_status"]["warning_by_env"] = _count_by_env(warning_instances)

    except Exception as e:
        logger.error(f"Erro ao buscar TempDB Status: {e}")


async def collect_server_offline(results: Dict[str, Any]) -> None:
    """Collect Server Offline Status KPIs."""
    try:
        query_agg = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK)
        """
        agg_data = await execute_intelligence_query_async(query_agg, raise_on_error=False)

        if agg_data and len(agg_data) > 0:
            row = agg_data[0]
            results["server_offline_status"]["servers_offline"] = int(row.get('Servers_Offline', 0) or 0)
            results["server_offline_status"]["servers_sql_down"] = int(row.get('Servers_SQL_Down', 0) or 0)
            results["server_offline_status"]["servers_partial"] = int(row.get('Servers_Partial', 0) or 0)
            results["server_offline_status"]["total_events"] = int(row.get('Total_Events', 0) or 0)
            results["server_offline_status"]["overall_status"] = row.get('Overall_Status', 'OK')
            results["server_offline_status"]["last_event_time"] = row.get('Last_Event_Time')

        query_det = f"""
        SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW WITH (NOLOCK)
        WHERE Is_Resolved = 0
        ORDER BY
            CASE Diagnosis WHEN 'offline' THEN 1 WHEN 'sql_down' THEN 2 ELSE 3 END,
            Event_Time DESC
        """
        det_data = await execute_intelligence_query_async(query_det, raise_on_error=False) or []
        results["server_offline_status"]["instances"] = det_data

        # Bug-fix 2026-04-23 (tooltip divergence): by_env so pode contar
        # entries que bataram com o count do card "SQL Services Down".
        # Antes, by_env contava todos os diagnosis -> tooltip inflado.
        # Aplica mesma regra: sql_down AND Ping_OK=1.
        by_env: Dict[str, int] = {}
        by_env_offline: Dict[str, int] = {}
        by_env_partial: Dict[str, int] = {}
        for inst in det_data:
            env = inst.get('Env', 'Undefined')
            diag = inst.get('Diagnosis', '')
            ping_ok = int(inst.get('Ping_OK', 1) or 0)
            if diag == 'sql_down' and ping_ok == 1:
                by_env[env] = by_env.get(env, 0) + 1
            elif diag == 'offline' and ping_ok == 0:
                by_env_offline[env] = by_env_offline.get(env, 0) + 1
            elif diag == 'partial' and ping_ok == 1:
                by_env_partial[env] = by_env_partial.get(env, 0) + 1
        results["server_offline_status"]["by_env"] = by_env
        results["server_offline_status"]["by_env_offline"] = by_env_offline
        results["server_offline_status"]["by_env_partial"] = by_env_partial

        # Bug-fix 2026-04-23: Business rule "server-offline-vs-service-down":
        # Um servico SQL parado num servidor OFFLINE e consequencia, nao causa
        # independente — ja conta em "servers_offline". Logo nao deve
        # double-count em "servers_sql_down".
        #
        # Antes: AGG_VIEW nao tem coluna `Servers_SQL_Down` global — a leitura
        # de `row.get('Servers_SQL_Down', 0)` nas linhas acima retorna sempre 0.
        # O fallback DET so corria quando `total_events == 0`, que era raro.
        # Como AGG_VIEW e per-servidor (nao global), total_events nunca e 0 na
        # pratica, logo o recalculo DET raramente era aplicado — mostrava 0.
        #
        # Agora: DET e SOT para os counts globais. Sempre recalcular a partir
        # de DET quando ha data, aplicando a regra:
        #   - offline: 1 entrada por servidor com Diagnosis='offline' E Ping_OK=0
        #   - sql_down: 1 entrada por servidor com Diagnosis='sql_down' E Ping_OK=1
        #   - partial:  1 entrada por servidor com Diagnosis='partial'  E Ping_OK=1
        # Regra Ping_OK garante que os counts sao mutuamente exclusivos.
        if det_data:
            # Primeiro diagnosis visto por servidor (ORDER BY offline primeiro
            # na query det garante que servidores offline sao capturados nesse estado).
            servers_seen: Dict[str, Dict[str, Any]] = {}  # server -> {diag, ping_ok}
            for inst in det_data:
                sn = inst.get('Server_Name') or inst.get('Instance', '')
                if not sn or sn in servers_seen:
                    continue
                servers_seen[sn] = {
                    'diagnosis': inst.get('Diagnosis', ''),
                    'ping_ok': int(inst.get('Ping_OK', 1) or 0),
                }

            def _counts_with_rule(seen: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
                offline = sum(
                    1 for s in seen.values()
                    if s['diagnosis'] == 'offline' and s['ping_ok'] == 0
                )
                # Regra: sql_down so conta se servidor estiver UP (Ping_OK = 1).
                # Servidores offline com sql_down sao contabilizados em offline, nao aqui.
                sql_down = sum(
                    1 for s in seen.values()
                    if s['diagnosis'] == 'sql_down' and s['ping_ok'] == 1
                )
                partial = sum(
                    1 for s in seen.values()
                    if s['diagnosis'] == 'partial' and s['ping_ok'] == 1
                )
                return {'offline': offline, 'sql_down': sql_down, 'partial': partial}

            counts = _counts_with_rule(servers_seen)

            results["server_offline_status"]["servers_offline"] = counts['offline']
            results["server_offline_status"]["servers_sql_down"] = counts['sql_down']
            results["server_offline_status"]["servers_partial"] = counts['partial']
            results["server_offline_status"]["total_events"] = (
                counts['offline'] + counts['sql_down'] + counts['partial']
            )

            if counts['offline'] > 0:
                results["server_offline_status"]["overall_status"] = 'CRITICAL'
            elif counts['sql_down'] > 0 or counts['partial'] > 0:
                results["server_offline_status"]["overall_status"] = 'WARNING'
            else:
                results["server_offline_status"]["overall_status"] = 'OK'

            logger.info(
                f"Server Offline (rule ping_ok): "
                f"{counts['offline']} offline, "
                f"{counts['sql_down']} sql_down (ping=OK only), "
                f"{counts['partial']} partial (ping=OK only)"
            )

        logger.debug(f"Server Offline Status: {results['server_offline_status']['total_events']} eventos ativos")

    except Exception as e:
        logger.error(f"Erro ao buscar Server Offline Status: {e}")


async def collect_cpu_critical(results: Dict[str, Any], offline_hostnames: Set[str]) -> None:
    """Collect CPU Critical KPIs, filtering out offline hosts."""
    try:
        query_cpu = f"""
        SELECT Instance, Hostname, Processor_Pct, SQL_CPU_Pct, Severity
        FROM {INTELLIGENCE_SCHEMA}.vw_OS_CPU_Current WITH (NOLOCK)
        WHERE Processor_Pct >= {_th('cpu_critical', 'critical')} OR Severity = 'CRITICAL'
        """
        cpu_data_raw = await execute_intelligence_query_async(query_cpu, raise_on_error=False) or []
        cpu_data = []
        cpu_filtered_count = 0
        for row in cpu_data_raw:
            hostname = (row.get('Hostname') or row.get('Instance', '').split('_')[0]).upper()
            if hostname in offline_hostnames:
                cpu_filtered_count += 1
                continue
            cpu_data.append(row)
        if cpu_filtered_count > 0:
            logger.info(f"CPU Critical: {cpu_filtered_count} instancia(s) filtrada(s) por servidor offline")
        results["cpu_critical"]["count"] = len(cpu_data)
        results["cpu_critical"]["instances"] = cpu_data
        results["cpu_critical"]["count_by_env"] = _count_by_env(cpu_data)
        logger.debug(f"CPU Critical: {len(cpu_data)} instancias (filtradas {cpu_filtered_count} offline)")
    except Exception as e:
        logger.error(f"Erro ao buscar CPU Critical: {e}")


async def collect_memory_critical(results: Dict[str, Any], offline_hostnames: Set[str]) -> None:
    """Collect Memory Critical KPIs, filtering out offline hosts."""
    try:
        query_memory = f"""
        SELECT t.Instance, t.Hostname, t.Avg_Percent_Used AS Percent_Used,
               c.Available_MB, c.Total_Physical_MB, t.Severity
        FROM {INTELLIGENCE_SCHEMA}.vw_OS_Memory_Trend_30Min t WITH (NOLOCK)
        LEFT JOIN {INTELLIGENCE_SCHEMA}.vw_OS_Memory_Current AS c WITH (NOLOCK)
            ON t.Instance = c.Instance AND t.Hostname = c.Hostname
        WHERE t.Severity = 'CRITICAL'
           OR (t.Avg_Percent_Used >= 99 AND t.Is_Sustained = 1)
           OR (t.Avg_Page_Reads_Sec > 100 AND t.Is_Sustained = 1)
        """
        memory_data_raw = await execute_intelligence_query_async(query_memory, raise_on_error=False) or []
        memory_data = []
        mem_filtered_count = 0
        for row in memory_data_raw:
            hostname = (row.get('Hostname') or row.get('Instance', '').split('_')[0]).upper()
            if hostname in offline_hostnames:
                mem_filtered_count += 1
                continue
            memory_data.append(row)
        if mem_filtered_count > 0:
            logger.info(f"Memory Critical: {mem_filtered_count} instancia(s) filtrada(s) por servidor offline")
        results["memory_critical"]["count"] = len(memory_data)
        results["memory_critical"]["instances"] = memory_data
        results["memory_critical"]["count_by_env"] = _count_by_env(memory_data)
        logger.debug(f"Memory Critical: {len(memory_data)} instancias (filtradas {mem_filtered_count} offline)")
    except Exception as e:
        logger.error(f"Erro ao buscar Memory Critical: {e}")


async def collect_deadlocks(results: Dict[str, Any]) -> None:
    """Collect Deadlocks KPIs from KPI_MSSQL_DEADLOCKS_AGG_VIEW (24h window).

    Bug-fix 2026-04-23: aplicar server-offline-vs-event rule. Deadlocks num
    servidor actualmente offline sao eventos historicos (janela 24h) — nao
    podem ter ocorrido novos desde que server caiu. Excluir via LEFT JOIN
    com INST_AVAILABILITY_ACTIVE + ISNULL guard (instancias sem registo em
    availability -> assumir UP para nao esconder dados novos).
    """
    try:
        query_deadlocks = f"""
        SELECT d.Instance, d.Env, d.Deadlock_Count, d.Last_Deadlock,
               d.Databases_Affected, d.Objects_Affected, d.State, d.Severity
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DEADLOCKS_AGG_VIEW AS d WITH (NOLOCK)
        LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE AS a WITH (NOLOCK)
            ON a.Instance = d.Instance
        WHERE ISNULL(a.Is_Available, 1) = 1
        """
        deadlocks_data = await execute_intelligence_query_async(query_deadlocks, raise_on_error=False) or []

        total_count = 0
        crit = warn = info = 0
        # Fase 1.5 lote 2 (2026-08-13): classificacao no backend via _th
        # (deadlocks_state configuravel). O State da view fica ignorado e e'
        # REESCRITO na row para as superficies (modal/badges) verem a mesma
        # verdade que as contagens. INFO fixo >=1 (nao configuravel).
        dl_warn = float(_th('deadlocks_state', 'warning'))
        dl_crit = float(_th('deadlocks_state', 'critical'))
        for row in deadlocks_data:
            dc = int(row.get('Deadlock_Count') or 0)
            total_count += dc
            state = ('CRITICAL' if dc >= dl_crit else
                     'WARNING' if dc >= dl_warn else
                     'INFO' if dc >= 1 else 'OK')
            row['State'] = state
            row['Severity'] = {'CRITICAL': 3, 'WARNING': 2, 'INFO': 1}.get(state, 0)
            if state == 'CRITICAL':
                crit += 1
            elif state == 'WARNING':
                warn += 1
            elif state == 'INFO':
                info += 1

        results["deadlocks"]["count"] = total_count
        results["deadlocks"]["count_critical"] = crit
        results["deadlocks"]["count_warning"] = warn
        results["deadlocks"]["count_info"] = info
        results["deadlocks"]["instances"] = deadlocks_data
        # 2026-08-03 (auditoria rotulo-vs-unidade): count = DEADLOCKS (soma), mas
        # count_by_env contava INSTANCIAS — com filtro de ambiente activo o card
        # "Deadlocks 24h" trocava de unidade em silencio (178 -> nº de instancias).
        # count_by_env passa a somar deadlocks (unidade coerente com count);
        # o mapa de instancias mantem-se disponivel em instances_by_env.
        results["deadlocks"]["instances_by_env"] = _count_by_env(deadlocks_data)
        # count_by_env conta INSTANCIAS; deadlock_count_by_env soma DEADLOCKS
        dl_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
        for row in deadlocks_data:
            env = (row.get('Env') or '').strip().upper()
            dc = int(row.get('Deadlock_Count') or 0)
            if env in dl_by_env:
                dl_by_env[env] += dc
            else:
                dl_by_env['Undefined'] = dl_by_env.get('Undefined', 0) + dc
        results["deadlocks"]["deadlock_count_by_env"] = dl_by_env
        # Mesma unidade do count global (soma de deadlocks) — ver comentario acima
        results["deadlocks"]["count_by_env"] = dl_by_env
        logger.debug(f"Deadlocks: {total_count} eventos / {len(deadlocks_data)} instancias (CRIT={crit} WARN={warn} INFO={info})")
    except Exception as e:
        logger.error(f"Erro ao buscar Deadlocks: {e}")


async def collect_disk_latency(results: Dict[str, Any], offline_hostnames: Set[str]) -> None:
    """Collect Disk Latency KPIs, filtering out offline hosts."""
    try:
        query_disk_latency = f"""
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
                WHEN Avg_Read_Latency_MS >= {_th('disk_latency', 'critical')} OR Avg_Write_Latency_MS >= {_th('disk_latency', 'critical')} THEN 'CRITICAL'
                WHEN Avg_Read_Latency_MS >= {_th('disk_latency', 'warning')} OR Avg_Write_Latency_MS >= {_th('disk_latency', 'warning')} THEN 'WARNING'
                ELSE 'OK'
            END AS Latency_Status,
            CASE
                WHEN Hostname LIKE '%PRD%' OR Hostname LIKE '%PROD%' THEN 'PRD'
                WHEN Hostname LIKE '%QLT%' OR Hostname LIKE '%QUAL%' THEN 'QLT'
                WHEN Hostname LIKE '%TST%' OR Hostname LIKE '%TEST%' OR Hostname LIKE '%DEV%' THEN 'TST'
                ELSE 'Undefined'
            END AS Env
        FROM {INTELLIGENCE_SCHEMA}.KPI_OS_DISK_PERF_STG WITH (NOLOCK)
        WHERE Avg_Read_Latency_MS >= {_th('disk_latency', 'warning')} OR Avg_Write_Latency_MS >= {_th('disk_latency', 'warning')}
        ORDER BY
            CASE WHEN Avg_Read_Latency_MS >= {_th('disk_latency', 'critical')} OR Avg_Write_Latency_MS >= {_th('disk_latency', 'critical')} THEN 0 ELSE 1 END,
            CASE WHEN ISNULL(Avg_Read_Latency_MS,0) > ISNULL(Avg_Write_Latency_MS,0) THEN ISNULL(Avg_Read_Latency_MS,0) ELSE ISNULL(Avg_Write_Latency_MS,0) END DESC
        """
        disk_latency_data_raw = await execute_intelligence_query_async(query_disk_latency, raise_on_error=False) or []
        disk_latency_data = [row for row in disk_latency_data_raw if (row.get('Hostname') or '').upper() not in offline_hostnames]
        dl_filtered = len(disk_latency_data_raw) - len(disk_latency_data)
        if dl_filtered > 0:
            logger.info(f"Disk Latency: {dl_filtered} entrada(s) filtrada(s) por servidor offline")

        critical_instances = [row for row in disk_latency_data if row.get('Latency_Status') == 'CRITICAL']
        warning_instances = [row for row in disk_latency_data if row.get('Latency_Status') == 'WARNING']

        results["disk_latency"]["critical_count"] = len(critical_instances)
        results["disk_latency"]["warning_count"] = len(warning_instances)
        results["disk_latency"]["instances"] = disk_latency_data
        results["disk_latency"]["critical_by_env"] = _count_by_env(critical_instances)
        results["disk_latency"]["warning_by_env"] = _count_by_env(warning_instances)

        logger.debug(f"Disk Latency: {len(critical_instances)} critical, {len(warning_instances)} warning")
    except Exception as e:
        logger.warning(f"Erro ao buscar Disk Latency (tabela pode nao existir): {e}")


async def collect_jobs_status(results: Dict[str, Any], query_jobs_from_servers_fn) -> None:
    """Collect Jobs Status KPIs (failed jobs and collisions).

    Args:
        results: Dashboard results dict to populate.
        query_jobs_from_servers_fn: Reference to _query_jobs_from_servers async function
            from the main module (used as fallback when STG views are unavailable).
    """
    try:
        job_views = [
            f"{INTELLIGENCE_SCHEMA}.KPI_MSSQL_JOB_FAILURES_AGG_VIEW",
            f"{INTELLIGENCE_SCHEMA}.KPI_MSSQL_JOBS_FAILED_AGG_VIEW",
            f"{INTELLIGENCE_SCHEMA}.KPI_MSSQL_JOB_FAILURES_STG"
        ]
        # Sentinela: None significa "view nao existe / query falhou", []
        # significa "view existe, vazia (legitimamente sem jobs failed)".
        # Antes: `if job_data:` tratava ambos como falhos e caia no Direct
        # fallback de 14s mesmo quando a view existia. Agora paramos no
        # primeiro execute que NAO levantou excepcao.
        job_data = None
        view_used = None
        for view_name in job_views:
            try:
                query = f"""
                SELECT j.*, ISNULL(e.Env, 'Undefined') AS Env
                FROM {view_name} AS j WITH (NOLOCK)
                LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
                    ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(j.Instance)))
                """
                result = await execute_intelligence_query_async(query, raise_on_error=False)
                if result is not None:
                    # Query OK (mesmo que retorne 0 rows) — view existe.
                    job_data = result
                    view_used = view_name
                    logger.info(f"View de Jobs encontrada: {view_name} ({len(result)} registros)")
                    break
            except Exception:
                continue

        if job_data is not None:
            # job_data pode estar vazio (view existe mas sem jobs failed) — OK
            failed_by_env = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}
            failed_by_type: Dict[str, int] = {}
            failed_instances = []

            for row in job_data:
                is_failed = False
                for key in ['Failed', 'FAILED', 'failed_count', 'Failed_Count', 'CNT', 'cnt']:
                    val = row.get(key, None)
                    if val is not None and int(val or 0) > 0:
                        is_failed = True
                        break
                # If no explicit failure column found, skip this row (NOT a failure)
                if not is_failed:
                    continue

                if is_failed:
                    env = _detect_env(row.get('Instance', ''), row.get('Env'))
                    env_key = env.upper() if env.upper() in ['PRD', 'QLT', 'TST'] else 'Undefined'
                    failed_by_env[env_key] = failed_by_env.get(env_key, 0) + 1

                    job_name_upper = (row.get('Job_Name') or row.get('job_name') or row.get('JobName') or '').upper()
                    if any(k in job_name_upper for k in ('BACKUP', 'BKP', 'BKUP')):
                        job_type = 'Backup'
                    elif any(k in job_name_upper for k in ('REINDEX', 'REBUILD', 'INDEX', 'OPTIMIZE', 'DEFRAG')):
                        job_type = 'Index'
                    elif any(k in job_name_upper for k in ('STATISTIC', 'STATS', 'UPDATE STAT')):
                        job_type = 'Statistics'
                    elif any(k in job_name_upper for k in ('CHECK', 'DBCC', 'INTEGRITY', 'CHECKDB')):
                        job_type = 'DBCC'
                    elif any(k in job_name_upper for k in ('SHRINK',)):
                        job_type = 'Shrink'
                    elif any(k in job_name_upper for k in ('LOG',)):
                        job_type = 'Log'
                    elif any(k in job_name_upper for k in ('CLEANUP', 'CLEAN_UP', 'CLEAN UP', 'PURGE', 'ARCHIVE')):
                        job_type = 'Cleanup'
                    elif any(k in job_name_upper for k in ('REPLICATION', 'REPL',)):
                        job_type = 'Replication'
                    elif any(k in job_name_upper for k in ('ALWAYSON', 'ALWAYS_ON', 'ALWAYS ON', 'HADR', 'AG_')):
                        job_type = 'AlwaysOn'
                    else:
                        job_type = 'Other'
                    row['Job_Type'] = job_type
                    failed_by_type[job_type] = failed_by_type.get(job_type, 0) + 1

                    row['Env'] = env
                    failed_instances.append(row)

            results["jobs_status"]["failed_count"] = len(failed_instances)
            results["jobs_status"]["instances"] = failed_instances
            results["jobs_status"]["failed_by_env"] = failed_by_env
            results["jobs_status"]["failed_by_type"] = failed_by_type
            logger.info(f"Jobs Status (STG) - Failed: {len(failed_instances)}, By env: {failed_by_env}, By type: {failed_by_type}")
        else:
            # Fallback: query individual servers directly
            logger.info("Jobs Status - Nenhuma view STG encontrada, consultando servidores diretamente...")
            failed_results, collision_results = await query_jobs_from_servers_fn(timeout=30.0)
            if failed_results:
                results["jobs_status"]["failed_count"] = failed_results["failed_count"]
                results["jobs_status"]["instances"] = failed_results["instances"]
                results["jobs_status"]["failed_by_env"] = failed_results["failed_by_env"]
                results["jobs_status"]["failed_by_type"] = failed_results.get("failed_by_type", {})
                logger.info(f"Jobs Status (Direct) - Failed: {failed_results['failed_count']}, By env: {failed_results['failed_by_env']}")
            if collision_results:
                results["jobs_status"]["collision_count"] = collision_results["collision_count"]
                results["jobs_status"]["collision_by_env"] = collision_results["collision_by_env"]
                results["jobs_status"]["collision_instances"] = collision_results["instances"]
                logger.info(f"Jobs Status (Direct) - Collisions: {collision_results['collision_count']}, By env: {collision_results['collision_by_env']}")

        # If we still don't have collisions, fetch separately
        if results["jobs_status"]["collision_count"] == 0 and not job_data:
            pass  # Already fetched in fallback above
        elif results["jobs_status"]["collision_count"] == 0:
            try:
                _, collision_results = await query_jobs_from_servers_fn(only_collisions=True, timeout=30.0)
                if collision_results:
                    results["jobs_status"]["collision_count"] = collision_results["collision_count"]
                    results["jobs_status"]["collision_by_env"] = collision_results["collision_by_env"]
                    results["jobs_status"]["collision_instances"] = collision_results["instances"]
                    logger.info(f"Jobs Collisions (Direct) - Count: {collision_results['collision_count']}")
            except Exception as e_col:
                logger.warning(f"Erro ao buscar colisoes de jobs: {e_col}")
    except Exception as e:
        logger.warning(f"Erro ao buscar Jobs Status: {e}")


def format_dashboard_response(
    results: Dict[str, Any],
    kpi_times: Dict[str, float],
    kpi_start_total: float,
) -> Dict[str, Any]:
    """Format the final dashboard response and log timing info."""
    _kpi_total_elapsed = time.time() - kpi_start_total
    _now = time.time()

    _kpi_order = [
        'DB Availability', 'Always On', 'Mirroring', 'FileGroup Usage',
        'Blocked Sessions', 'Blocked Users', 'Instance Availability',
        'Backup Status', 'Service Status', 'Long Locks', 'Processes',
        'Error Log', 'CPU Critical', 'Memory Critical', 'Disk Latency',
        'Jobs Status'
    ]

    for kpi_name in _kpi_order:
        if kpi_name in kpi_times:
            _elapsed = _now - kpi_times[kpi_name]
            logger.info(f"[CACHE] {kpi_name}: {_elapsed:.2f}s")

    logger.info(f"[CACHE] === TOTAL: {_kpi_total_elapsed:.2f}s ===")

    response_data = {
        "success": True,
        "data": _serialize_result(results)
    }
    _set_dashboard_cache(response_data)
    _save_dashboard_snapshot(response_data)
    return response_data


async def collect_collection_freshness(results: Dict[str, Any]) -> None:
    """Freshness guard Componente A (2026-07-17, parecer v1-intel-specialist).

    Marca grupos de KPI como data_stale=True quando o COLLECTOR da tabela-fonte
    esta morto (KPI_MSSQL_COLLECTION_FRESHNESS_VIEW.Is_Stale=1). Fecha o blind
    spot que escondeu o incidente do mirroring 13/05->17/07: is_data_fresh()
    valida frescura POR LINHA — collector morto devolve 0 linhas e o tile
    mostrava "0 problemas" para sempre.

    Fail-open: se a view nao existir (DDL FRESHNESS_GUARD_COMPONENT_A.sql ainda
    nao aplicado), nenhum flag e escrito e o dashboard comporta-se como antes.
    """
    _TABLE_TO_RESULT_KEY = {
        'KPI_MSSQL_MIRRORING_STATUS_STG': 'mirroring_status',
        'KPI_MSSQL_DEADLOCKS_STG': 'deadlocks',
        'KPI_MSSQL_ERRORLOG_STG': 'error_log',
        # Wave X (2026-07-19): as 2 fontes do KPI Integridade apontam para o
        # mesmo grupo — stale se QUALQUER uma estiver morta (OR no loop abaixo)
        'KPI_MSSQL_DBCC_HISTORY_STG': 'integrity',
        'KPI_MSSQL_DB_SETTINGS_STG': 'integrity',
    }
    try:
        query = (
            f"SELECT Table_Name, Is_Stale, Minutes_Since_Evidence "
            f"FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_COLLECTION_FRESHNESS_VIEW WITH (NOLOCK)"
        )
        rows = await execute_intelligence_query_async(query, raise_on_error=False) or []
        for row in rows:
            key = _TABLE_TO_RESULT_KEY.get(row.get('Table_Name'))
            if not key:
                continue
            grp = results.get(key)
            if isinstance(grp, dict):
                # OR-combinar: grupos com varias tabelas-fonte (ex: integrity)
                # ficam stale se QUALQUER fonte estiver morta; minutos = pior caso
                is_stale = bool(row.get('Is_Stale'))
                grp['data_stale'] = bool(grp.get('data_stale')) or is_stale
                mins = row.get('Minutes_Since_Evidence')
                if is_stale and mins is not None:
                    prev = grp.get('stale_minutes')
                    grp['stale_minutes'] = max(prev, mins) if prev is not None else mins
                elif 'stale_minutes' not in grp:
                    grp['stale_minutes'] = mins
    except Exception as e:
        logger.debug(f"Freshness guard indisponivel (view ausente?): {e}")


async def collect_integrity(results: Dict[str, Any]) -> None:
    """Wave X (2026-07-19): KPI Integridade — deteccao de corrupcao.

    Le KPI_MSSQL_INTEGRITY_VERDICT_VIEW (view partilhada, parecer v1-intel
    2026-07-19): P1 = suspect pages registadas (corrupcao), P3 = nunca validado
    por CHECKDB (incl. data-sentinela do collector), P4 = CHECKDB > 30d,
    higiene = PAGE_VERIFY != CHECKSUM. P2 (823/824/825) fica NULL na view ate
    ao fast-follow do collector de errorlog — indisponivel nunca vira "0".

    Fail-open honesto: se a view nao existir (DDL da wave ainda nao aplicado),
    marca available=False — o card mostra N/D em vez de zeros silenciosos.
    """
    try:
        _joins = f"""
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INTEGRITY_VERDICT_VIEW AS v WITH (NOLOCK)
        LEFT OUTER JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS AS e WITH (NOLOCK)
            ON e.Instance = v.Instance
        """
        # Item B (2026-07-21): Measurability e' coluna ADITIVA da view. Fallback
        # defensivo: enquanto a view live nao for recriada com a coluna, a query
        # estendida falha e caimos na query base (comportamento pre-Item B).
        rows = None
        has_measurability = False
        try:
            rows = await execute_intelligence_query_async(
                "SELECT v.Verdict, v.Needs_PageVerify_Fix, v.Measurability, "
                "v.Days_Since_CheckDB, "
                "ISNULL(e.Env, 'Undefined') AS Env" + _joins,
                raise_on_error=True)
            has_measurability = rows is not None
        except Exception:
            rows = None
        if rows is None:
            rows = await execute_intelligence_query_async(
                "SELECT v.Verdict, v.Needs_PageVerify_Fix, "
                "v.Days_Since_CheckDB, "
                "ISNULL(e.Env, 'Undefined') AS Env" + _joins,
                raise_on_error=True)
        if rows is None:
            raise RuntimeError('view indisponivel')

        # Fase 1.5 lote 3 (2026-08-13): fronteira P4/P5 recalculada no backend
        # sobre Days_Since_CheckDB com cutoff configuravel (o >30 da view fica
        # para consumidores Pro/V6). P1/P3/higiene continuam da view.
        ig_cut = float(_th('integrity_checkdb_age', 'warning'))
        for r in rows:
            if r.get('Verdict') in ('P4', 'P5'):
                d = r.get('Days_Since_CheckDB')
                r['Verdict'] = 'P4' if (d is not None and float(d) > ig_cut) else 'P5'

        p1_rows = [r for r in rows if r.get('Verdict') == 'P1']
        p3_rows = [r for r in rows if r.get('Verdict') == 'P3']
        p4_rows = [r for r in rows if r.get('Verdict') == 'P4']
        results['integrity'] = {
            'available': True,
            'p1_count': len(p1_rows),
            'p3_count': len(p3_rows),
            'p4_count': len(p4_rows),
            'pageverify_count': sum(1 for r in rows if (r.get('Needs_PageVerify_Fix') or 0) == 1),
            'total': len(rows),
            'p1_by_env': _count_by_env(p1_rows),
            # 2026-08-04 (opcao A, FIND-105): Integridade passa a ter dimensao de
            # ambiente. Os rows ja' vinham com Env (JOIN INST_ENVS); so faltava
            # expor os breakdowns. Sem isto, o filtro por ambiente somava 0 para a
            # integridade e "todos os ambientes" != "sem filtro" (diferenca ~= P4).
            'p3_by_env': _count_by_env(p3_rows),
            'p4_by_env': _count_by_env(p4_rows),
            # NOT_MEASURABLE = coleta CHECKDB falhou (permissao/DB inacessivel).
            # Ortogonal ao Verdict: um P3 NOT_MEASURABLE nao e' "nunca validado",
            # e' "nao conseguimos medir". Percentagens tipo "X% sem validacao"
            # devem excluir estes. None = view ainda sem a coluna (pre-Item B).
            'unmeasurable_count': (
                sum(1 for r in rows if r.get('Measurability') == 'NOT_MEASURABLE')
                if has_measurability else None
            ),
        }
    except Exception as e:
        logger.warning(f"Integridade indisponivel (view Wave X ainda nao aplicada?): {e}")
        results['integrity'] = {
            'available': False,
            'p1_count': None, 'p3_count': None, 'p4_count': None,
            'pageverify_count': None, 'total': 0, 'p1_by_env': {},
            'unmeasurable_count': None,
        }
