"""
WatcherDB LIVE Monitoring Router — Real-time instance monitoring.

Endpoints para dados live de uma instancia monitorizada.
Todas as queries sao executadas directamente na instancia alvo
(nao na Intelligence DB) para dados em tempo real.

Programas disponiveis:
  1. Queries em Execucao  — sys.dm_exec_requests + dm_exec_sql_text
  2. TempDB Live          — dm_db_file_space_usage + dm_db_session_space_usage
  3. Health Gauges         — CPU, Memory, PLE, Batch/s, Sessions (1 query)
  4. Wait Stats Live       — dm_os_wait_stats (delta entre polls)
  5. Locks & Blocking      — dm_tran_locks + blocking chains

Todos os endpoints recebem `instance` como path param (formato HOST_INSTANCE).
"""

import hashlib
import json
import logging
import os
import time
from typing import Callable, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute

from api.error_helpers import safe_http_error

logger = logging.getLogger(__name__)


def _live_json(payload, status_code: int = 200):
    """JSONResponse com Decimal/datetime/bytes seguros.

    2026-09-11: /live/{inst}/tempdb dava 500 puro ("Object of type Decimal is not JSON
    serializable") sempre que TEMPDB_ACTIVE_USAGE_SQL tinha linhas -- o 1024.0 devolve
    Decimal. Em vez de caçar coluna a coluna, todas as respostas do LIVE passam por aqui.
    """
    return JSONResponse(status_code=status_code,
                        content=jsonable_encoder(payload, custom_encoder={bytes: lambda b: b.hex()}))


# RBAC do LIVE (QA externo 2026-08-16, decisao 2 / achado do security-auditor):
# estes endpoints devolvem texto SQL completo, logins de servico e hostnames de
# producao. O AuthEnforcementMiddleware so' valida que o token existe -- nunca
# olhou para o role -- por isso um VIEWER via exactamente o mesmo que um ADMIN.
#
# DESLIGADO POR OMISSAO: nao ha ambiente QLT nesta instalacao (so' 8433 e 8660),
# logo o interruptor e' a rede de seguranca. Ligar em config.yaml:
#     security:
#       rbac_live_admin_only: true
# Rollback = voltar a false + Restart-Service (sem redeploy de codigo).
#
# ANTES DE LIGAR: corrigir os roles no painel Control. Ha' utilizadores com
# "(Admin)" no nome e role=viewer (N-05 do QA) -- ligar isto primeiro tranca-os
# fora do LIVE E do Control, que e' onde os roles se corrigem.
def _rbac_live_enabled() -> bool:
    try:
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parents[2] / "services" / "web_service" / "config.yaml"
        if not cfg_path.is_file():
            return False
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        return bool(cfg.get("security", {}).get("rbac_live_admin_only", False))
    except Exception:
        return False  # fail-open: um erro de config nunca tranca o LIVE


async def _live_role_gate(request: Request) -> None:
    """403 para viewer quando a flag esta ligada; no-op quando desligada.

    Passa `dba` E `admin` (decisao do owner 2026-08-16: LIVE e' diagnostico,
    nao governanca — nao exige controlo total).
    """
    if not _rbac_live_enabled():
        return
    from api.routers.auth_compat import _require_dba
    await _require_dba(request)


# ---------------------------------------------------------------------------
# Redaccao por role (R2-02 do QA externo, ronda 2)
# ---------------------------------------------------------------------------
# A decisao do owner (2026-08-16, commit 493c6de) foi que o viewer VE o LIVE:
# o eixo do RBAC passou a ser ler-vs-escrever, nao area. Mas o achado do
# security-auditor continua de pe' -- estes endpoints devolvem texto SQL cru,
# logins de servico e nomes de maquina. Fechar a pagina ao viewer revertia a
# decisao do owner; redigir os campos preserva-a e fecha a exposicao.
#
# Feito ao nivel do ROUTER (route_class) e nao endpoint a endpoint, de proposito:
# o endpoint numero 17 nasce coberto sem ninguem se lembrar. Controlo que depende
# de memoria apodrece -- foi assim que o `Optional[RunRequest] = None` reabriu
# uma porta em silencio noutro sitio.
#
# O SQL nao e' truncado: truncar continua a revelar nomes de tabela e a forma da
# query. Sai um hash estavel, que deixa o viewer agrupar ocorrencias da mesma
# query e dizer "sao todas a mesma" sem ver o texto.

_REDACTED = "[oculto - requer nivel dba]"

_SQL_FIELDS = frozenset({
    "sql_text", "full_sql_text", "full_query_text", "blocked_sql", "blocker_sql",
})
_IDENTITY_FIELDS = frozenset({
    "login_name", "blocked_login", "blocker_login",
    "host_name", "client_host", "blocked_host", "blocker_host",
    "program_name",
})


def _redact_node(node):
    """Percorre a arvore da resposta e redige os campos sensiveis."""
    if isinstance(node, list):
        return [_redact_node(item) for item in node]
    if isinstance(node, dict):
        saida = {}
        for chave, valor in node.items():
            if chave in _SQL_FIELDS and isinstance(valor, str) and valor.strip():
                digest = hashlib.sha256(valor.encode("utf-8", "replace")).hexdigest()[:12]
                saida[chave] = f"{_REDACTED} #{digest}"
            elif chave in _IDENTITY_FIELDS and isinstance(valor, str) and valor.strip():
                saida[chave] = _REDACTED
            else:
                saida[chave] = _redact_node(valor)
        return saida
    return node


def _role_do_pedido(request: Request) -> Optional[str]:
    """Role do utilizador, posto no request.state pelo AuthEnforcementMiddleware."""
    user = getattr(request.state, "user", None)
    if isinstance(user, dict):
        return user.get("role")
    return None


class _RoleRedactingRoute(APIRoute):
    """Redige a resposta quando quem pede e' `viewer`. `dba`/`admin` veem tudo."""

    def get_route_handler(self) -> Callable:
        handler_original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await handler_original(request)
            if _role_do_pedido(request) != "viewer":
                return response
            corpo = getattr(response, "body", None)
            if not corpo or "application/json" not in response.headers.get("content-type", ""):
                return response
            try:
                payload = json.loads(corpo)
            except Exception:
                # Fail-closed seria devolver 500 num ecra de diagnostico; aqui o
                # risco e' o inverso do habitual: um corpo que nao e' JSON nao
                # contem os campos que nos preocupam.
                return response
            novo = json.dumps(_redact_node(payload), default=str).encode("utf-8")
            response.body = novo
            response.headers["content-length"] = str(len(novo))
            return response

        return handler


router = APIRouter(
    prefix="/api/v1/live",
    tags=["Live Monitoring"],
    dependencies=[Depends(_live_role_gate)],
    route_class=_RoleRedactingRoute,
)


def _get_pool():
    from api.connection_pool import get_sql_server_pool
    return get_sql_server_pool()


def _query_instance(instance: str, sql: str, database: str = "master", timeout: int = 10):
    """Executa query na instancia monitorizada com timeout."""
    pool = _get_pool()
    conn = pool.get_connection(instance, database)
    if not conn:
        return None, f"Sem conexao a {instance}"
    try:
        conn.timeout = timeout
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows, None
    except Exception as e:
        return None, str(e)
    finally:
        pool.return_connection(instance, conn)


# =========================================================================
# 1. HEALTH GAUGES — metricas essenciais num unico round-trip
# =========================================================================

GAUGES_SQL = """
SET NOCOUNT ON;

-- CPU + Memory + PLE + Batch/s num unico SELECT
SELECT
    (SELECT TOP 1 CAST(record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]','int') AS INT)
     FROM (SELECT TOP 1 CAST(record AS XML) AS record
           FROM sys.dm_os_ring_buffers WITH (NOLOCK)
           WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
           ORDER BY timestamp DESC) AS rb
    ) AS cpu_pct,
    (SELECT CAST(cntr_value AS BIGINT) FROM sys.dm_os_performance_counters WITH (NOLOCK)
     WHERE counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') AS ple_seconds,
    (SELECT CAST(cntr_value AS BIGINT) FROM sys.dm_os_performance_counters WITH (NOLOCK)
     WHERE counter_name = 'Batch Requests/sec' AND object_name LIKE '%SQL Statistics%') AS batch_requests_sec,
    (SELECT COUNT(*) FROM sys.dm_exec_sessions WITH (NOLOCK) WHERE is_user_process = 1) AS active_sessions,
    (SELECT COUNT(*) FROM sys.dm_exec_requests WITH (NOLOCK) WHERE session_id > 50) AS running_queries,
    (SELECT COUNT(*) FROM sys.dm_exec_requests WITH (NOLOCK) WHERE blocking_session_id > 0) AS blocked_count,
    (SELECT physical_memory_in_use_kb / 1024 FROM sys.dm_os_process_memory WITH (NOLOCK)) AS sql_memory_mb,
    (SELECT total_physical_memory_kb / 1024 FROM sys.dm_os_sys_memory WITH (NOLOCK)) AS total_memory_mb,
    (SELECT available_physical_memory_kb / 1024 FROM sys.dm_os_sys_memory WITH (NOLOCK)) AS available_memory_mb,
    (SELECT CAST(value_in_use AS INT) FROM sys.configurations WITH (NOLOCK) WHERE name = 'max server memory (MB)') AS max_server_memory_mb
"""


@router.get("/{instance}/gauges")
async def get_live_gauges(instance: str):
    """Metricas essenciais em tempo real (CPU, Memory, PLE, Sessions)."""
    rows, err = _query_instance(instance, GAUGES_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    if not rows:
        return _live_json({"instance": instance, "data": None})

    r = rows[0]
    total_mem = r.get("total_memory_mb") or 1
    avail_mem = r.get("available_memory_mb") or 0
    mem_pct = round((total_mem - avail_mem) / total_mem * 100, 1) if total_mem > 0 else 0

    return _live_json({
        "instance": instance,
        "timestamp": time.time(),
        "gauges": {
            "cpu_pct": r.get("cpu_pct") or 0,
            "memory_pct": mem_pct,
            "sql_memory_mb": r.get("sql_memory_mb") or 0,
            "max_server_memory_mb": r.get("max_server_memory_mb") or 0,
            "total_memory_mb": total_mem,
            "available_memory_mb": avail_mem,
            "ple_seconds": r.get("ple_seconds") or 0,
            "batch_requests_sec": r.get("batch_requests_sec") or 0,
            "active_sessions": r.get("active_sessions") or 0,
            "running_queries": r.get("running_queries") or 0,
            "blocked_count": r.get("blocked_count") or 0,
        }
    })


# =========================================================================
# 2. QUERIES EM EXECUCAO — dm_exec_requests + sql_text
# =========================================================================

RUNNING_QUERIES_SQL = """
SET NOCOUNT ON;
SELECT TOP 50
    r.session_id AS spid,
    r.status,
    DB_NAME(r.database_id) AS database_name,
    r.command,
    r.wait_type,
    r.wait_time AS wait_time_ms,
    r.blocking_session_id AS blocking_spid,
    r.cpu_time AS cpu_ms,
    r.reads AS logical_reads,
    r.writes,
    DATEDIFF(SECOND, r.start_time, GETDATE()) AS elapsed_sec,
    r.start_time,
    r.percent_complete,
    r.granted_query_memory * 8 / 1024 AS granted_memory_mb,
    s.login_name,
    s.host_name AS client_host,
    s.program_name,
    SUBSTRING(t.text,
        (r.statement_start_offset / 2) + 1,
        CASE WHEN r.statement_end_offset = -1
             THEN LEN(t.text)
             ELSE (r.statement_end_offset - r.statement_start_offset) / 2 + 1
        END
    ) AS current_statement,
    LEFT(t.text, 500) AS full_sql_text
FROM sys.dm_exec_requests r WITH (NOLOCK)
JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.session_id > 50
  AND r.session_id != @@SPID
ORDER BY r.cpu_time DESC
"""


@router.get("/{instance}/queries")
async def get_running_queries(instance: str):
    """Queries em execucao com SQL text, waits, blocking."""
    rows, err = _query_instance(instance, RUNNING_QUERIES_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)

    # Sanitizar datetimes
    for r in (rows or []):
        if r.get("start_time") and hasattr(r["start_time"], "isoformat"):
            r["start_time"] = r["start_time"].isoformat()

    return _live_json({
        "instance": instance,
        "timestamp": time.time(),
        "count": len(rows or []),
        "queries": rows or [],
    })


# =========================================================================
# 3. TEMPDB LIVE — space breakdown + top consumers
# =========================================================================

TEMPDB_SPACE_SQL = """
SET NOCOUNT ON;
-- Space breakdown
SELECT
    SUM(unallocated_extent_page_count) * 8 / 1024 AS free_mb,
    SUM(version_store_reserved_page_count) * 8 / 1024 AS version_store_mb,
    SUM(user_object_reserved_page_count) * 8 / 1024 AS user_objects_mb,
    SUM(internal_object_reserved_page_count) * 8 / 1024 AS internal_objects_mb,
    SUM(mixed_extent_page_count) * 8 / 1024 AS mixed_extents_mb
FROM tempdb.sys.dm_db_file_space_usage WITH (NOLOCK);
"""

TEMPDB_FILES_SQL = """
SET NOCOUNT ON;
SELECT
    name,
    physical_name,
    size * 8 / 1024 AS size_mb,
    FILEPROPERTY(name, 'SpaceUsed') * 8 / 1024 AS used_mb,
    CASE WHEN max_size = -1 THEN -1 ELSE max_size * 8 / 1024 END AS max_size_mb,
    growth * 8 / 1024 AS growth_mb,
    type_desc
FROM tempdb.sys.database_files WITH (NOLOCK)
ORDER BY type, file_id;
"""

TEMPDB_CONSUMERS_SQL = """
SET NOCOUNT ON;
SELECT TOP 15
    su.session_id AS spid,
    s.login_name,
    s.host_name AS client_host,
    s.program_name,
    DB_NAME(s.database_id) AS current_db,
    su.internal_objects_alloc_page_count * 8 / 1024 AS internal_alloc_mb,
    su.internal_objects_dealloc_page_count * 8 / 1024 AS internal_dealloc_mb,
    su.user_objects_alloc_page_count * 8 / 1024 AS user_alloc_mb,
    su.user_objects_dealloc_page_count * 8 / 1024 AS user_dealloc_mb,
    (su.internal_objects_alloc_page_count + su.user_objects_alloc_page_count
     - su.internal_objects_dealloc_page_count - su.user_objects_dealloc_page_count
    ) * 8 / 1024 AS net_usage_mb,
    r.status AS request_status,
    r.command,
    r.wait_type,
    SUBSTRING(t.text, (r.statement_start_offset/2)+1,
        CASE WHEN r.statement_end_offset=-1 THEN LEN(t.text)
             ELSE (r.statement_end_offset-r.statement_start_offset)/2+1 END
    ) AS current_statement
FROM sys.dm_db_session_space_usage su WITH (NOLOCK)
JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON su.session_id = s.session_id
LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK) ON su.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE s.is_user_process = 1
  AND (su.internal_objects_alloc_page_count + su.user_objects_alloc_page_count) > 0
ORDER BY (su.internal_objects_alloc_page_count + su.user_objects_alloc_page_count
          - su.internal_objects_dealloc_page_count - su.user_objects_dealloc_page_count) DESC;
"""


TEMPDB_ACTIVE_USAGE_SQL = """
SET NOCOUNT ON;
SELECT TOP 20
    r.session_id AS spid,
    s.login_name,
    r.status,
    r.command,
    r.cpu_time AS cpu_ms,
    r.total_elapsed_time / 1000 AS elapsed_sec,
    r.wait_type,
    SUM(tsu.internal_objects_alloc_page_count + tsu.user_objects_alloc_page_count) * 8 / 1024.0 AS tempdb_usage_mb,
    DB_NAME(r.database_id) AS database_name,
    SUBSTRING(t.text, (r.statement_start_offset/2)+1,
        CASE WHEN r.statement_end_offset=-1 THEN LEN(t.text)
             ELSE (r.statement_end_offset-r.statement_start_offset)/2+1 END
    ) AS current_statement,
    LEFT(t.text, 500) AS full_query_text
FROM sys.dm_db_task_space_usage tsu WITH (NOLOCK)
JOIN sys.dm_exec_requests r WITH (NOLOCK)
    ON tsu.session_id = r.session_id AND tsu.request_id = r.request_id
JOIN sys.dm_exec_sessions s WITH (NOLOCK)
    ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.session_id <> @@SPID
GROUP BY
    r.session_id, s.login_name, r.status, r.command,
    r.cpu_time, r.total_elapsed_time, r.wait_type,
    r.database_id, r.statement_start_offset, r.statement_end_offset,
    t.text
HAVING SUM(tsu.internal_objects_alloc_page_count + tsu.user_objects_alloc_page_count) > 0
ORDER BY SUM(tsu.internal_objects_alloc_page_count + tsu.user_objects_alloc_page_count) DESC;
"""


@router.get("/{instance}/tempdb")
async def get_tempdb_live(instance: str):
    """TempDB live: space breakdown, files, top consumers, active usage."""
    pool = _get_pool()
    conn = pool.get_connection(instance, "tempdb")
    if not conn:
        raise HTTPException(status_code=503, detail=f"Sem conexao a {instance}")

    result = {"instance": instance, "timestamp": time.time()}
    try:
        cur = conn.cursor()

        # Space breakdown
        cur.execute(TEMPDB_SPACE_SQL)
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            result["space"] = dict(zip(cols, row))

        # Files
        cur.execute(TEMPDB_FILES_SQL)
        cols = [d[0] for d in cur.description]
        result["files"] = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Top consumers (session-level)
        cur.execute(TEMPDB_CONSUMERS_SQL)
        cols = [d[0] for d in cur.description]
        result["consumers"] = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Active TempDB usage por query (task-level — quem esta a usar AGORA)
        try:
            cur.execute(TEMPDB_ACTIVE_USAGE_SQL)
            cols = [d[0] for d in cur.description]
            result["active_usage"] = [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception:
            result["active_usage"] = []

    except Exception as e:
        result["error"] = str(e)
    finally:
        pool.return_connection(instance, conn)

    return _live_json(result)


# =========================================================================
# 4. WAIT STATS LIVE — top waits (snapshot para delta no frontend)
# =========================================================================

WAIT_STATS_SQL = """
SET NOCOUNT ON;
SELECT TOP 20
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    signal_wait_time_ms,
    CASE
        WHEN wait_type LIKE 'LCK%' THEN 'Lock'
        WHEN wait_type LIKE 'PAGEIOLATCH%' THEN 'I/O'
        WHEN wait_type LIKE 'PAGELATCH%' THEN 'TempDB/Memory'
        WHEN wait_type LIKE 'CXPACKET%' OR wait_type = 'CXCONSUMER' THEN 'Parallelism'
        WHEN wait_type = 'SOS_SCHEDULER_YIELD' THEN 'CPU'
        WHEN wait_type = 'WRITELOG' THEN 'Log I/O'
        WHEN wait_type LIKE 'ASYNC_NETWORK%' THEN 'Network/Client'
        WHEN wait_type = 'RESOURCE_SEMAPHORE' THEN 'Memory Grant'
        WHEN wait_type LIKE 'HADR%' THEN 'AlwaysOn'
        ELSE 'Other'
    END AS category
FROM sys.dm_os_wait_stats WITH (NOLOCK)
WHERE waiting_tasks_count > 0
  AND wait_type NOT IN (
    'BROKER_EVENTHANDLER','BROKER_RECEIVE_WAITFOR','BROKER_TASK_STOP',
    'BROKER_TO_FLUSH','CHECKPOINT_QUEUE','CLR_AUTO_EVENT','CLR_MANUAL_EVENT',
    'DIRTY_PAGE_POLL','DISPATCHER_QUEUE_SEMAPHORE','FT_IFTS_SCHEDULER_IDLE_WAIT',
    'HADR_FILESTREAM_IOMGR_IOCOMPLETION','HADR_WORK_QUEUE',
    'LAZYWRITER_SLEEP','LOGMGR_QUEUE','ONDEMAND_TASK_QUEUE',
    'REQUEST_FOR_DEADLOCK_SEARCH','SLEEP_TASK','SP_SERVER_DIAGNOSTICS_SLEEP',
    'SQLTRACE_BUFFER_FLUSH','SQLTRACE_INCREMENTAL_FLUSH_SLEEP',
    'TRACEWRITE','WAIT_XTP_HOST_WAIT','WAITFOR','XE_DISPATCHER_WAIT',
    'XE_TIMER_EVENT','PREEMPTIVE_OS_AUTHENTICATIONOPS'
  )
ORDER BY wait_time_ms DESC;
"""


@router.get("/{instance}/waits")
async def get_wait_stats(instance: str):
    """Wait stats snapshot (frontend calcula delta entre polls)."""
    rows, err = _query_instance(instance, WAIT_STATS_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    return _live_json({
        "instance": instance,
        "timestamp": time.time(),
        "waits": rows or [],
    })


# =========================================================================
# 5. LOCKS & BLOCKING — blocking chains
# =========================================================================

BLOCKING_SQL = """
SET NOCOUNT ON;
SELECT
    r.session_id AS blocked_spid,
    r.blocking_session_id AS blocker_spid,
    DB_NAME(r.database_id) AS database_name,
    r.wait_type,
    r.wait_time / 1000 AS wait_sec,
    r.command,
    s.login_name AS blocked_login,
    s.host_name AS blocked_host,
    s.program_name AS blocked_program,
    bs.login_name AS blocker_login,
    bs.host_name AS blocker_host,
    SUBSTRING(t.text, (r.statement_start_offset/2)+1,
        CASE WHEN r.statement_end_offset=-1 THEN LEN(t.text)
             ELSE (r.statement_end_offset-r.statement_start_offset)/2+1 END
    ) AS blocked_sql,
    SUBSTRING(bt.text, 1, 500) AS blocker_sql
FROM sys.dm_exec_requests r WITH (NOLOCK)
JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON r.session_id = s.session_id
LEFT JOIN sys.dm_exec_sessions bs WITH (NOLOCK) ON r.blocking_session_id = bs.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
OUTER APPLY sys.dm_exec_sql_text(
    (SELECT TOP 1 most_recent_sql_handle FROM sys.dm_exec_connections WITH (NOLOCK)
     WHERE session_id = r.blocking_session_id)
) bt
WHERE r.blocking_session_id > 0
ORDER BY r.wait_time DESC;
"""


@router.get("/{instance}/blocking")
async def get_blocking_chains(instance: str):
    """Blocking chains activas."""
    rows, err = _query_instance(instance, BLOCKING_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    return _live_json({
        "instance": instance,
        "timestamp": time.time(),
        "count": len(rows or []),
        "chains": rows or [],
    })


# =========================================================================
# 6. LISTA DE INSTANCIAS DISPONIVEIS (para o selector de "canais")
# =========================================================================

# =========================================================================
# 6. I/O LIVE — dm_io_virtual_file_stats (snapshot para delta no frontend)
# =========================================================================

IO_STATS_SQL = """
SET NOCOUNT ON;
SELECT TOP 30
    DB_NAME(vfs.database_id) AS database_name,
    mf.physical_name,
    mf.type_desc AS file_type,
    vfs.num_of_reads,
    vfs.num_of_writes,
    vfs.num_of_bytes_read / 1048576 AS read_mb,
    vfs.num_of_bytes_written / 1048576 AS write_mb,
    CASE WHEN vfs.num_of_reads > 0
         THEN vfs.io_stall_read_ms / vfs.num_of_reads ELSE 0 END AS avg_read_latency_ms,
    CASE WHEN vfs.num_of_writes > 0
         THEN vfs.io_stall_write_ms / vfs.num_of_writes ELSE 0 END AS avg_write_latency_ms,
    vfs.io_stall_read_ms,
    vfs.io_stall_write_ms,
    vfs.size_on_disk_bytes / 1048576 AS file_size_mb
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs  -- sem hint: WITH (NOLOCK) numa TVF = erro 319 (2026-09-11)
JOIN sys.master_files mf WITH (NOLOCK)
    ON vfs.database_id = mf.database_id AND vfs.file_id = mf.file_id
ORDER BY (vfs.io_stall_read_ms + vfs.io_stall_write_ms) DESC;
"""


@router.get("/{instance}/io")
async def get_io_stats(instance: str):
    """I/O stats por ficheiro (snapshot para delta no frontend)."""
    rows, err = _query_instance(instance, IO_STATS_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "files": rows or [],
    })


# =========================================================================
# 7. JOBS RUNNING — SQL Agent jobs activos
# =========================================================================

JOBS_RUNNING_SQL = """
SET NOCOUNT ON;
SELECT
    j.name AS job_name,
    ja.start_execution_date,
    DATEDIFF(MINUTE, ja.start_execution_date, GETDATE()) AS running_minutes,
    ISNULL(js.step_name, '(starting)') AS current_step,
    js.step_id AS current_step_id,
    (SELECT COUNT(*) FROM msdb.dbo.sysjobsteps s2 WHERE s2.job_id = j.job_id) AS total_steps,
    jc.name AS category_name
FROM msdb.dbo.sysjobactivity ja WITH (NOLOCK)
JOIN msdb.dbo.sysjobs j WITH (NOLOCK) ON ja.job_id = j.job_id
LEFT JOIN msdb.dbo.sysjobsteps js WITH (NOLOCK) ON ja.job_id = js.job_id AND ja.last_executed_step_id = js.step_id
LEFT JOIN msdb.dbo.syscategories jc WITH (NOLOCK) ON j.category_id = jc.category_id
WHERE ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.syssessions WITH (NOLOCK))
  AND ja.start_execution_date IS NOT NULL
  AND ja.stop_execution_date IS NULL
ORDER BY ja.start_execution_date;
"""


@router.get("/{instance}/jobs")
async def get_jobs_running(instance: str):
    """Jobs SQL Agent em execucao."""
    rows, err = _query_instance(instance, JOBS_RUNNING_SQL, database="msdb")
    if err:
        raise HTTPException(status_code=503, detail=err)
    for r in (rows or []):
        if r.get("start_execution_date") and hasattr(r["start_execution_date"], "isoformat"):
            r["start_execution_date"] = r["start_execution_date"].isoformat()
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "count": len(rows or []), "jobs": rows or [],
    })


# =========================================================================
# 8. MEMORY LIVE — buffer pool + clerks + grants
# =========================================================================

MEMORY_SQL = """
SET NOCOUNT ON;
-- Buffer pool por DB (top 10)
SELECT TOP 10
    DB_NAME(database_id) AS database_name,
    COUNT(*) * 8 / 1024 AS buffer_mb,
    SUM(CAST(is_modified AS INT)) * 8 / 1024 AS dirty_mb
FROM sys.dm_os_buffer_descriptors WITH (NOLOCK)
WHERE database_id > 0
GROUP BY database_id
ORDER BY COUNT(*) DESC;
"""

MEMORY_CLERKS_SQL = """
SET NOCOUNT ON;
SELECT TOP 15
    type AS clerk_type,
    SUM(pages_kb) / 1024 AS size_mb
FROM sys.dm_os_memory_clerks WITH (NOLOCK)
GROUP BY type
HAVING SUM(pages_kb) > 1024
ORDER BY SUM(pages_kb) DESC;
"""

MEMORY_GRANTS_SQL = """
SET NOCOUNT ON;
SELECT
    session_id AS spid,
    granted_memory_kb / 1024 AS granted_mb,
    requested_memory_kb / 1024 AS requested_mb,
    required_memory_kb / 1024 AS required_mb,
    used_memory_kb / 1024 AS used_mb,
    ideal_memory_kb / 1024 AS ideal_mb,
    queue_id,
    wait_time_ms,
    is_next_candidate,
    grant_time
FROM sys.dm_exec_query_memory_grants WITH (NOLOCK)
WHERE granted_memory_kb > 0 OR is_next_candidate = 1
ORDER BY granted_memory_kb DESC;
"""


@router.get("/{instance}/memory")
async def get_memory_live(instance: str):
    """Memory live: buffer pool por DB, clerks, grants."""
    pool = _get_pool()
    conn = pool.get_connection(instance)
    if not conn:
        raise HTTPException(status_code=503, detail=f"Sem conexao a {instance}")
    result = {"instance": instance, "timestamp": time.time()}
    try:
        cur = conn.cursor()
        cur.execute(MEMORY_SQL)
        cols = [d[0] for d in cur.description]
        result["buffer_pool"] = [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute(MEMORY_CLERKS_SQL)
        cols = [d[0] for d in cur.description]
        result["clerks"] = [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute(MEMORY_GRANTS_SQL)
        cols = [d[0] for d in cur.description]
        grants = [dict(zip(cols, r)) for r in cur.fetchall()]
        for g in grants:
            if g.get("grant_time") and hasattr(g["grant_time"], "isoformat"):
                g["grant_time"] = g["grant_time"].isoformat()
        result["grants"] = grants
    except Exception as e:
        result["error"] = str(e)
    finally:
        pool.return_connection(instance, conn)
    return _live_json(result)


# =========================================================================
# 9. CONNECTIONS — quem esta ligado
# =========================================================================

CONNECTIONS_SQL = """
SET NOCOUNT ON;
SELECT TOP 50
    s.session_id AS spid,
    s.login_name,
    s.host_name AS client_host,
    s.program_name,
    DB_NAME(s.database_id) AS current_db,
    s.status,
    s.cpu_time AS total_cpu_ms,
    s.memory_usage * 8 AS memory_kb,
    s.reads AS total_reads,
    s.writes AS total_writes,
    s.login_time,
    DATEDIFF(MINUTE, s.login_time, GETDATE()) AS connected_minutes,
    c.client_net_address,
    c.auth_scheme,
    c.encrypt_option,
    c.net_transport
FROM sys.dm_exec_sessions s WITH (NOLOCK)
LEFT JOIN sys.dm_exec_connections c WITH (NOLOCK) ON s.session_id = c.session_id
WHERE s.is_user_process = 1
ORDER BY s.cpu_time DESC;
"""


@router.get("/{instance}/connections")
async def get_connections(instance: str):
    """Conexoes activas."""
    rows, err = _query_instance(instance, CONNECTIONS_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    for r in (rows or []):
        if r.get("login_time") and hasattr(r["login_time"], "isoformat"):
            r["login_time"] = r["login_time"].isoformat()
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "count": len(rows or []), "connections": rows or [],
    })


# =========================================================================
# 10. ALWAYSON LIVE — AG sync status + queues
# =========================================================================

ALWAYSON_SQL = """
SET NOCOUNT ON;
-- 2026-09-11: dm_hadr_database_replica_states NAO tem database_name (erro 207) -- vem de
-- sys.availability_databases_cluster por group_database_id. E o lag deixa de ser DATEDIFF ate
-- GETDATE() (media "tempo desde a ultima escrita": base ociosa ficava vermelha): passa a ser o
-- delta entre o last_commit_time da primaria e o da replica. NULL quando a linha da primaria
-- nao e' visivel (numa secundaria a DMV so' devolve a linha local -- facto medido a 11/09).
SELECT
    ag.name AS ag_name,
    ar.replica_server_name,
    ars.role_desc,
    ars.connected_state_desc,
    ars.synchronization_health_desc,
    adc.database_name,
    drs.synchronization_state_desc,
    drs.log_send_queue_size AS send_queue_kb,
    drs.redo_queue_size AS redo_queue_kb,
    drs.log_send_rate AS send_rate_kb_sec,
    drs.redo_rate AS redo_rate_kb_sec,
    drs.last_commit_time,
    CASE WHEN ars.role = 1 THEN 0
         WHEN drs.last_commit_time IS NULL OR pc.primary_commit IS NULL THEN NULL
         ELSE DATEDIFF(SECOND, drs.last_commit_time, pc.primary_commit) END AS commit_lag_sec,
    drs.is_suspended,
    drs.suspend_reason_desc
FROM sys.availability_groups ag WITH (NOLOCK)
JOIN sys.availability_replicas ar WITH (NOLOCK) ON ag.group_id = ar.group_id
JOIN sys.dm_hadr_availability_replica_states ars WITH (NOLOCK) ON ar.replica_id = ars.replica_id
LEFT JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK) ON ar.replica_id = drs.replica_id
LEFT JOIN sys.availability_databases_cluster adc WITH (NOLOCK) ON adc.group_database_id = drs.group_database_id
OUTER APPLY (SELECT MAX(p.last_commit_time) AS primary_commit
             FROM sys.dm_hadr_database_replica_states p WITH (NOLOCK)
             JOIN sys.dm_hadr_availability_replica_states pa WITH (NOLOCK) ON pa.replica_id = p.replica_id AND pa.role = 1
             WHERE p.group_database_id = drs.group_database_id) pc  -- ars.role/pa.role: 2012-safe (is_primary_replica e' 2014+; ha' 4 x 2012 na frota)
ORDER BY ag.name, ar.replica_server_name, adc.database_name;
"""


@router.get("/{instance}/alwayson")
async def get_alwayson_live(instance: str):
    """AlwaysOn AG status + queues em tempo real."""
    rows, err = _query_instance(instance, ALWAYSON_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    for r in (rows or []):
        if r.get("last_commit_time") and hasattr(r["last_commit_time"], "isoformat"):
            r["last_commit_time"] = r["last_commit_time"].isoformat()
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "replicas": rows or [],
    })


# =========================================================================
# 11. TRANSACTION LOG LIVE
# =========================================================================

TLOG_SQL = """
SET NOCOUNT ON;
-- 2026-09-11: sem WITH (NOLOCK) na TVF (erro 319/102) e por CROSS APPLY em sys.databases:
-- dm_db_log_stats(NULL) devolve 0 linhas em 2016 SP2 (medido em CAGENPRD06). So' bases ONLINE e
-- sem snapshots. O 319 escondia um 207: dm_db_log_stats NAO tem log_reuse_wait_desc (vem de
-- sys.databases) nem log_space_in_bytes_since_last_backup (a coluna e' log_since_last_log_backup_mb).
SELECT
    d.name AS database_name,
    ls.total_vlf_count AS vlf_count,
    ls.active_vlf_count AS active_vlfs,
    CAST(ls.log_since_last_log_backup_mb AS FLOAT) AS log_since_backup_mb,
    ls.log_truncation_holdup_reason AS truncation_reason,
    d.log_reuse_wait_desc AS reuse_wait
FROM sys.databases d WITH (NOLOCK)
CROSS APPLY sys.dm_db_log_stats(d.database_id) ls
WHERE d.database_id > 4 AND d.state = 0 AND d.source_database_id IS NULL
ORDER BY ls.total_vlf_count DESC;
"""

# Fallback para SQL 2014 (dm_db_log_stats é 2016+)
TLOG_SQL_LEGACY = """
SET NOCOUNT ON;
SELECT
    d.name AS database_name,
    d.log_reuse_wait_desc AS reuse_wait,
    mf.size * 8 / 1024 AS log_size_mb,
    FILEPROPERTY(mf.name, 'SpaceUsed') * 8 / 1024 AS log_used_mb
FROM sys.databases d WITH (NOLOCK)
JOIN sys.master_files mf WITH (NOLOCK) ON d.database_id = mf.database_id AND mf.type = 1
WHERE d.database_id > 4 AND d.state = 0
ORDER BY mf.size DESC;
"""


@router.get("/{instance}/tlog")
async def get_tlog_live(instance: str):
    """Transaction log status."""
    rows, err = _query_instance(instance, TLOG_SQL)
    if err and "dm_db_log_stats" in str(err):
        rows, err = _query_instance(instance, TLOG_SQL_LEGACY)
    if err:
        raise HTTPException(status_code=503, detail=err)
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "databases": rows or [],
    })


# =========================================================================
# 12. PLAN CACHE LIVE
# =========================================================================

PLANCACHE_SQL = """
SET NOCOUNT ON;
SELECT TOP 20
    qs.total_worker_time / qs.execution_count AS avg_cpu_us,
    qs.total_logical_reads / qs.execution_count AS avg_reads,
    qs.execution_count,
    qs.total_worker_time / 1000 AS total_cpu_ms,
    qs.total_logical_reads,
    qs.plan_generation_num AS recompiles,
    qs.creation_time AS plan_created,
    DB_NAME(qt.dbid) AS database_name,
    SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
        CASE WHEN qs.statement_end_offset=-1 THEN LEN(qt.text)
             ELSE (qs.statement_end_offset-qs.statement_start_offset)/2+1 END
    ) AS sql_text
FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
ORDER BY qs.total_worker_time DESC;
"""


@router.get("/{instance}/plancache")
async def get_plan_cache(instance: str):
    """Top queries no plan cache por CPU."""
    rows, err = _query_instance(instance, PLANCACHE_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    for r in (rows or []):
        if r.get("plan_created") and hasattr(r["plan_created"], "isoformat"):
            r["plan_created"] = r["plan_created"].isoformat()
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "queries": rows or [],
    })


# =========================================================================
# 13. ERROR LOG LIVE (tail)
# =========================================================================

ERRORLOG_SQL = """
SET NOCOUNT ON;
CREATE TABLE #err (LogDate DATETIME, ProcessInfo VARCHAR(64), Text NVARCHAR(MAX));
INSERT INTO #err EXEC xp_readerrorlog 0, 1, NULL, NULL, NULL, NULL, N'desc';
SELECT TOP 50 LogDate, ProcessInfo, Text
FROM #err
ORDER BY LogDate DESC;
DROP TABLE #err;
"""

# Fallback simples se xp_readerrorlog falhar
ERRORLOG_SQL_SIMPLE = """
SET NOCOUNT ON;
EXEC xp_readerrorlog 0, 1, NULL, NULL, NULL, NULL, N'desc';
"""


@router.get("/{instance}/errorlog")
async def get_error_log(instance: str):
    """Ultimas 50 entradas do error log."""
    pool = _get_pool()
    conn = pool.get_connection(instance)
    if not conn:
        raise HTTPException(status_code=503, detail=f"Sem conexao a {instance}")
    try:
        cur = conn.cursor()
        try:
            cur.execute(ERRORLOG_SQL)
        except Exception:
            cur.execute(ERRORLOG_SQL_SIMPLE)
        cols = [d[0] for d in cur.description] if cur.description else ["LogDate", "ProcessInfo", "Text"]
        rows = []
        for r in cur.fetchall()[:50]:
            row = dict(zip(cols, r))
            if row.get("LogDate") and hasattr(row["LogDate"], "isoformat"):
                row["LogDate"] = row["LogDate"].isoformat()
            rows.append(row)
        return _live_json({
            "instance": instance, "timestamp": time.time(),
            "entries": rows,
        })
    except Exception as e:
        raise safe_http_error(503, e, "live_monitoring SQL Server errorlog")
    finally:
        pool.return_connection(instance, conn)


# =========================================================================
# 14. SCHEDULER HEALTH
# =========================================================================

SCHEDULER_SQL = """
SET NOCOUNT ON;
SELECT
    scheduler_id,
    cpu_id,
    status,
    current_tasks_count,
    runnable_tasks_count,
    current_workers_count,
    active_workers_count,
    work_queue_count,
    pending_disk_io_count,
    yield_count,
    context_switches_count
FROM sys.dm_os_schedulers WITH (NOLOCK)
WHERE status = 'VISIBLE ONLINE'
ORDER BY scheduler_id;
"""


@router.get("/{instance}/schedulers")
async def get_scheduler_health(instance: str):
    """Scheduler health (runnable tasks, yields, pending I/O)."""
    rows, err = _query_instance(instance, SCHEDULER_SQL)
    if err:
        raise HTTPException(status_code=503, detail=err)
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "schedulers": rows or [],
        "total_runnable": sum(r.get("runnable_tasks_count", 0) or 0 for r in (rows or [])),
        "total_pending_io": sum(r.get("pending_disk_io_count", 0) or 0 for r in (rows or [])),
    })


# =========================================================================
# 15. FLEET DASHBOARD — overview de todas as instancias em paralelo
# =========================================================================

FLEET_GAUGE_SQL = """
SET NOCOUNT ON;
SELECT
    @@SERVERNAME AS instance_name,
    (SELECT TOP 1 CAST(record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]','int') AS INT)
     FROM (SELECT TOP 1 CAST(record AS XML) AS record
           FROM sys.dm_os_ring_buffers WITH (NOLOCK)
           WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
           ORDER BY timestamp DESC) AS rb
    ) AS cpu_pct,
    (SELECT CAST(cntr_value AS BIGINT) FROM sys.dm_os_performance_counters WITH (NOLOCK)
     WHERE counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') AS ple,
    (SELECT COUNT(*) FROM sys.dm_exec_requests WITH (NOLOCK) WHERE session_id > 50) AS queries,
    (SELECT COUNT(*) FROM sys.dm_exec_requests WITH (NOLOCK) WHERE blocking_session_id > 0) AS blocked,
    (SELECT COUNT(*) FROM sys.dm_exec_sessions WITH (NOLOCK) WHERE is_user_process = 1) AS sessions,
    (SELECT available_physical_memory_kb / 1024 FROM sys.dm_os_sys_memory WITH (NOLOCK)) AS avail_mem_mb,
    (SELECT total_physical_memory_kb / 1024 FROM sys.dm_os_sys_memory WITH (NOLOCK)) AS total_mem_mb
"""


@router.get("/fleet/dashboard")
async def get_fleet_dashboard():
    """
    Fleet LIVE Dashboard v2 — KPI-guided live drill.
    Usa KPIs para overview geral + conecta em tempo real APENAS as
    instancias problematicas (~10-15) para dados exclusivos do LIVE:
    - Top queries pesadas AGORA (cross-fleet)
    - Blocking chains activas
    - Erros recentes no Error Log
    - TempDB consumers activos
    """
    from api.connection_pool import execute_on_intelligence
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # ── 1. Overview geral (KPI data, instantaneo) ──
    # Normalizar nomes: PERF usa '\' enquanto outras tabelas usam '_'
    # Uma instancia e "online" se tem dados em QUALQUER tabela KPI recente
    inv = execute_on_intelligence("""
        WITH perf_data AS (
            SELECT REPLACE(Instance, CHAR(92), '_') AS Instance,
                   Processor_Pct, Memory_Usage_Pct, PLE_Seconds, Batch_Requests_Sec
            FROM dbo.KPI_MSSQL_OS_PERF_STG WITH (NOLOCK)
        ),
        avail_data AS (
            SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
        ),
        disk_data AS (
            SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK)
        )
        SELECT
            e.Instance, e.Env,
            p.Processor_Pct AS cpu_pct,
            p.Memory_Usage_Pct AS mem_pct,
            p.PLE_Seconds AS ple,
            p.Batch_Requests_Sec AS batch_sec,
            CASE
                WHEN p.Instance IS NOT NULL THEN 'perf'
                WHEN a.Instance IS NOT NULL THEN 'avail'
                WHEN d.Instance IS NOT NULL THEN 'disk'
                ELSE NULL
            END AS data_source
        FROM dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
        LEFT JOIN perf_data p ON p.Instance = e.Instance
        LEFT JOIN avail_data a ON a.Instance = e.Instance
        LEFT JOIN disk_data d ON d.Instance = e.Instance
        ORDER BY e.Env, e.Instance
    """) or []

    # Cruzar com servidores offline (ping fail) para distinguir
    # "sem dados de perf" de "realmente offline"
    offline_servers = set()
    try:
        off = execute_on_intelligence("""
            SELECT Server_Name FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
            WHERE Ping_OK = 0
        """) or []
        offline_servers = {(r.get("Server_Name") or "").strip().upper() for r in off}
        logger.debug(f"[Fleet] Offline servers (ping fail): {offline_servers}")
    except Exception:
        pass

    instances = []
    for r in inv:
        has_perf = r.get("cpu_pct") is not None
        data_src = r.get("data_source")  # 'perf', 'avail', 'disk', ou None
        inst_name = r.get("Instance", "?")
        hostname = inst_name.split("_")[0].upper()
        # Determinar status:
        #   ok      - tem dados de performance (CPU/MEM/PLE visiveis)
        #   partial - online (avail/disk) mas sem collector de perf
        #   offline - sem dados + ping fail
        #   no_data - sem dados em nenhuma tabela
        if has_perf:
            status = "ok"
        elif data_src in ("avail", "disk"):
            status = "partial"
        elif hostname in offline_servers:
            status = "offline"
        else:
            status = "no_data"
        instances.append({
            "instance": inst_name,
            "env": r.get("Env", "?"),
            "status": status,
            "data_source": data_src,
            "cpu_pct": float(r.get("cpu_pct") or 0),
            "mem_pct": float(r.get("mem_pct") or 0),
            "ple": int(r.get("ple") or 0),
            "blocked": 0,
        })

    # Blocked sessions
    try:
        blocked = execute_on_intelligence("""
            SELECT Instance, COUNT(*) AS blocked
            FROM dbo.KPI_MSSQL_BLOCKED_SESSIONS_STG WITH (NOLOCK)
            GROUP BY Instance
        """) or []
        bmap = {b.get("Instance", "").upper(): int(b.get("blocked", 0)) for b in blocked}
        for i in instances:
            i["blocked"] = bmap.get(i["instance"].upper(), 0)
    except Exception:
        pass

    online = [i for i in instances if i["status"] == "ok"]
    offline = [i for i in instances if i["status"] != "ok"]

    # ── 2. Identificar instancias problematicas (para live drill) ──
    problem_instances = set()
    for i in online:
        if i["cpu_pct"] >= 50 or i["mem_pct"] >= 90 or i["blocked"] > 0 or (i["ple"] > 0 and i["ple"] < 300):
            problem_instances.add(i["instance"])
    # Limitar a 15 para nao sobrecarregar
    problem_list = list(problem_instances)[:15]

    # ── 3. Live drill — conectar APENAS as problematicas ──
    live_queries = []       # top queries pesadas cross-fleet
    live_errors = []        # erros recentes no error log
    live_blocking = []      # blocking chains
    live_tempdb = []        # tempdb consumers activos
    live_waits = []         # top waits
    live_ag_queues = []     # alwayson send/redo queues
    live_idle = []          # sessoes idle >1h
    live_long_tran = []     # transacoes longas >5min

    pool = _get_pool()

    def _drill_instance(instance):
        """Colecta dados live exclusivos de 1 instancia. Rapido (<2s)."""
        result = {"instance": instance, "queries": [], "errors": [], "blocking": [],
                  "tempdb_consumers": [], "top_waits": [], "ag_queues": [],
                  "idle_sessions": [], "long_transactions": []}
        conn = pool.get_connection(instance)
        if not conn:
            return result
        try:
            # Timeout de query de 2s para nao bloquear
            conn.timeout = 2
            cur = conn.cursor()
            # Top queries pesadas (CPU > 1000ms)
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT TOP 3 r.session_id AS spid, DB_NAME(r.database_id) AS db,
                        r.cpu_time AS cpu_ms, r.wait_type, r.status,
                        DATEDIFF(SECOND, r.start_time, GETDATE()) AS elapsed_sec,
                        SUBSTRING(t.text,(r.statement_start_offset/2)+1,
                            CASE WHEN r.statement_end_offset=-1 THEN LEN(t.text)
                            ELSE (r.statement_end_offset-r.statement_start_offset)/2+1 END) AS sql_text
                    FROM sys.dm_exec_requests r WITH (NOLOCK)
                    CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
                    WHERE r.session_id > 50 AND r.session_id != @@SPID AND r.cpu_time > 1000
                    ORDER BY r.cpu_time DESC""")
                cols = [d[0] for d in cur.description]
                result["queries"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # Blocking
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT r.session_id AS blocked_spid, r.blocking_session_id AS blocker_spid,
                        DB_NAME(r.database_id) AS db, r.wait_type, r.wait_time/1000 AS wait_sec
                    FROM sys.dm_exec_requests r WITH (NOLOCK)
                    WHERE r.blocking_session_id > 0""")
                cols = [d[0] for d in cur.description]
                result["blocking"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # TempDB consumers activos
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT TOP 3 r.session_id AS spid, s.login_name,
                        SUM(tsu.internal_objects_alloc_page_count + tsu.user_objects_alloc_page_count) * 8 / 1024 AS tempdb_mb,
                        DB_NAME(r.database_id) AS db
                    FROM sys.dm_db_task_space_usage tsu WITH (NOLOCK)
                    JOIN sys.dm_exec_requests r WITH (NOLOCK) ON tsu.session_id = r.session_id AND tsu.request_id = r.request_id
                    JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON r.session_id = s.session_id
                    WHERE r.session_id <> @@SPID
                    GROUP BY r.session_id, s.login_name, r.database_id
                    HAVING SUM(tsu.internal_objects_alloc_page_count + tsu.user_objects_alloc_page_count) > 128
                    ORDER BY SUM(tsu.internal_objects_alloc_page_count + tsu.user_objects_alloc_page_count) DESC""")
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    result["tempdb_consumers"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # Top waits (snapshot para delta)
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT TOP 5 wait_type, waiting_tasks_count, wait_time_ms
                    FROM sys.dm_os_wait_stats WITH (NOLOCK)
                    WHERE waiting_tasks_count > 0
                    AND wait_type NOT IN ('BROKER_EVENTHANDLER','BROKER_RECEIVE_WAITFOR','BROKER_TASK_STOP',
                        'CHECKPOINT_QUEUE','CLR_AUTO_EVENT','DIRTY_PAGE_POLL','DISPATCHER_QUEUE_SEMAPHORE',
                        'FT_IFTS_SCHEDULER_IDLE_WAIT','HADR_WORK_QUEUE','LAZYWRITER_SLEEP','LOGMGR_QUEUE',
                        'ONDEMAND_TASK_QUEUE','REQUEST_FOR_DEADLOCK_SEARCH','SLEEP_TASK',
                        'SP_SERVER_DIAGNOSTICS_SLEEP','SQLTRACE_BUFFER_FLUSH','WAITFOR',
                        'XE_DISPATCHER_WAIT','XE_TIMER_EVENT')
                    ORDER BY wait_time_ms DESC""")
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    result["top_waits"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # AlwaysOn queue sizes
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT ag.name AS ag_name, ar.replica_server_name,
                        adc.database_name, drs.synchronization_state_desc,
                        drs.log_send_queue_size AS send_queue_kb,
                        drs.redo_queue_size AS redo_queue_kb,
                        drs.log_send_rate AS send_rate_kb_sec,
                        drs.redo_rate AS redo_rate_kb_sec
                    FROM sys.availability_groups ag WITH (NOLOCK)
                    JOIN sys.availability_replicas ar WITH (NOLOCK) ON ag.group_id = ar.group_id
                    JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK) ON ar.replica_id = drs.replica_id
                    LEFT JOIN sys.availability_databases_cluster adc WITH (NOLOCK) ON adc.group_database_id = drs.group_database_id
                    WHERE drs.log_send_queue_size > 1024 OR drs.redo_queue_size > 1024
                    ORDER BY (drs.log_send_queue_size + drs.redo_queue_size) DESC""")
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    result["ag_queues"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # Sessoes idle ha mais de 1h
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT TOP 5 s.session_id AS spid, s.login_name, s.host_name,
                        s.program_name, DB_NAME(s.database_id) AS db,
                        DATEDIFF(MINUTE, s.last_request_end_time, GETDATE()) AS idle_minutes,
                        s.memory_usage * 8 AS memory_kb, s.cpu_time AS total_cpu_ms
                    FROM sys.dm_exec_sessions s WITH (NOLOCK)
                    WHERE s.is_user_process = 1 AND s.status = 'sleeping'
                    AND DATEDIFF(MINUTE, s.last_request_end_time, GETDATE()) > 60
                    ORDER BY DATEDIFF(MINUTE, s.last_request_end_time, GETDATE()) DESC""")
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    result["idle_sessions"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # Long running transactions (>5 min) — podem bloquear tlog truncation
            try:
                cur.execute("""SET NOCOUNT ON;
                    SELECT TOP 3 s.session_id AS spid, s.login_name,
                        DB_NAME(dt.database_id) AS db,
                        DATEDIFF(MINUTE, dt.database_transaction_begin_time, GETDATE()) AS tran_minutes,
                        dt.database_transaction_log_bytes_used / 1048576 AS log_used_mb
                    FROM sys.dm_tran_database_transactions dt WITH (NOLOCK)
                    JOIN sys.dm_tran_session_transactions st WITH (NOLOCK) ON dt.transaction_id = st.transaction_id
                    JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON st.session_id = s.session_id
                    WHERE DATEDIFF(MINUTE, dt.database_transaction_begin_time, GETDATE()) > 5
                    ORDER BY dt.database_transaction_log_bytes_used DESC""")
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    result["long_transactions"] = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception:
                pass

            # NOTA: xp_readerrorlog removido do drill por ser muito lento (~10s+).
            # Error log agora e obtido via endpoint /{instance}/errorlog quando
            # o user entra no canal da instancia.

        except Exception:
            pass
        finally:
            pool.return_connection(instance, conn)
        return result

    if problem_list:
        # Limitar a 8 instancias (top 8 por gravidade) e 10 threads
        online_problems = [i for i in online if i["instance"] in problem_list]
        online_problems.sort(key=lambda x: -(x["cpu_pct"] + x["mem_pct"] + x["blocked"]*100))
        problem_list = [i["instance"] for i in online_problems[:8]]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_drill_instance, inst): inst for inst in problem_list}
            try:
                for future in as_completed(futures, timeout=8):
                    try:
                        drill = future.result(timeout=2)
                        inst = drill.get("instance", "?")
                        for q in drill.get("queries", []):
                            q["instance"] = inst
                            live_queries.append(q)
                        for b in drill.get("blocking", []):
                            b["instance"] = inst
                            live_blocking.append(b)
                        for e in drill.get("errors", []):
                            e["instance"] = inst
                            live_errors.append(e)
                        for t in drill.get("tempdb_consumers", []):
                            t["instance"] = inst
                            live_tempdb.append(t)
                        for w in drill.get("top_waits", []):
                            w["instance"] = inst
                            live_waits.append(w)
                        for a in drill.get("ag_queues", []):
                            a["instance"] = inst
                            live_ag_queues.append(a)
                        for s in drill.get("idle_sessions", []):
                            s["instance"] = inst
                            live_idle.append(s)
                        for lt in drill.get("long_transactions", []):
                            lt["instance"] = inst
                            live_long_tran.append(lt)
                    except Exception:
                        pass
            except TimeoutError:
                pass

    # Ordenar resultados live
    live_queries.sort(key=lambda x: -(x.get("cpu_ms") or 0))
    live_errors.sort(key=lambda x: x.get("LogDate", ""), reverse=True)
    live_blocking.sort(key=lambda x: -(x.get("wait_sec") or 0))
    live_tempdb.sort(key=lambda x: -(x.get("tempdb_mb") or 0))
    live_waits.sort(key=lambda x: -(x.get("wait_time_ms") or 0))
    live_ag_queues.sort(key=lambda x: -((x.get("send_queue_kb") or 0) + (x.get("redo_queue_kb") or 0)))
    live_idle.sort(key=lambda x: -(x.get("idle_minutes") or 0))

    return _live_json({
        "timestamp": time.time(),
        "total": len(instances),
        "online": len(online),
        "offline": len(offline),
        "instances": instances,
        "problem_count": len(problem_list),
        "live_queries": live_queries[:10],
        "live_blocking": live_blocking[:10],
        "live_errors": live_errors[:15],
        "live_tempdb": live_tempdb[:10],
        "live_waits": live_waits[:15],
        "live_ag_queues": live_ag_queues[:10],
        "live_idle": live_idle[:10],
        "live_long_tran": sorted(live_long_tran, key=lambda x: -(x.get("tran_minutes") or 0))[:10],
    })


# =========================================================================
# 16. LISTA DE INSTANCIAS DISPONIVEIS (para o selector de "canais")
# =========================================================================

@router.get("/channels")
async def get_available_channels():
    """Lista de instancias monitorizadas agrupadas por ambiente."""
    from api.connection_pool import execute_on_intelligence
    rows = execute_on_intelligence("""
        SELECT Instance, Env, Description
        FROM dbo.KPI_MSSQL_INST_ENVS WITH (NOLOCK)
        ORDER BY Env, Instance
    """) or []

    # Agrupar por ambiente
    by_env = {}
    for r in rows:
        env = r.get("Env", "?")
        if env not in by_env:
            by_env[env] = []
        by_env[env].append({
            "instance": r.get("Instance"),
            "description": r.get("Description", ""),
        })

    return _live_json({
        "total": len(rows),
        "by_environment": by_env,
        "environments": list(by_env.keys()),
    })
