"""Calcula o estado de saude de cada task do Collector.

Estados: FRESH, RECENT, QUIET, STALE, FAILED, DISABLED, NEVER_RAN.

Combina:
  - config.yaml (tasks estaticos: interval, enabled, environment, tables)
  - KPI_STG_ACTIVE_TABLE (estado dinamico: Last_Swap_Time, Collection_*_Time,
    Servers_Collected) — para collectors Blue/Green
  - MAX(<timestamp_col>) directo da tabela alvo — para collectors non-Blue/Green
    com fallback por multiplas colunas de timestamp (Update_TS, Event_Time,
    collected_at, detected_at, event_timestamp, etc.)
  - errors.log tail (para deteccao de FAILED recente)
"""

import fnmatch
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from modules.collector_health.config_loader import get_tasks
from modules.collector_health.log_parser import (
    failure_count,
    recent_errors_for_task,
)

logger = logging.getLogger(__name__)

# Collectors que NAO usam mecanismo Blue/Green (nao tem entry em KPI_STG_ACTIVE_TABLE).
# Fallback: ler MAX(<timestamp_col>) directamente da primeira target_table.
NON_BG_TASK_PATTERNS = [
    "collect_os_cpu_*",
    "collect_os_memory_*",
    "collect_os_disk_perf_*",
    "collect_deadlocks_*",
    "collect_2pc_transactions_*",
    "collect_agent_jobs_*",
    "collect_ag_failovers_*",
    "collect_server_ping_*",
    "collect_anomaly_detection*",
]

# Colunas de timestamp em ordem de prioridade. A primeira que existir e
# tiver dados na tabela vence. Cobre todas as variantes usadas nas tabelas
# do WatcherDB Intelligence.
TIMESTAMP_COLUMN_CANDIDATES = [
    "Update_TS",
    "Event_Time",
    "collected_at",
    "detected_at",
    "event_timestamp",
    "triggered_at",
    "Deadlock_Time",
]

# Tasks que retornam 0 rows quando o sistema esta saudavel. STALE nestes
# casos NAO e falha — e ausencia de eventos. Badge = QUIET (roxo).
EVENT_DRIVEN_TASK_PATTERNS = [
    "collect_suspect_pages_*",
    "collect_deadlocks_*",
    "collect_long_locks_*",
    "collect_blocked_sessions_*",
    "collect_blocked_users_*",
    "collect_ag_failovers_*",
    "collect_server_ping_*",
]


def _is_non_bg_task(task_name: str) -> bool:
    for pat in NON_BG_TASK_PATTERNS:
        if fnmatch.fnmatch(task_name, pat):
            return True
    return False


def _is_event_driven_task(task_name: str) -> bool:
    for pat in EVENT_DRIVEN_TASK_PATTERNS:
        if fnmatch.fnmatch(task_name, pat):
            return True
    return False


STATUS_FRESH = "FRESH"
STATUS_RECENT = "RECENT"
STATUS_QUIET = "QUIET"
STATUS_STALE = "STALE"
STATUS_FAILED = "FAILED"
STATUS_DISABLED = "DISABLED"
STATUS_NEVER_RAN = "NEVER_RAN"

STATUS_ORDER = {
    STATUS_FAILED: 0,
    STATUS_STALE: 1,
    STATUS_NEVER_RAN: 2,
    STATUS_QUIET: 3,
    STATUS_RECENT: 4,
    STATUS_FRESH: 5,
    STATUS_DISABLED: 6,
}


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _seconds_ago(dt: Optional[datetime]) -> Optional[int]:
    if not dt:
        return None
    now = datetime.utcnow()
    dt = _to_naive_utc(dt)
    delta = now - dt
    return max(0, int(delta.total_seconds()))


async def _fetch_overrides() -> Dict[str, Dict[str, Any]]:
    """Le overrides de collector_task_overrides — dict por task_name."""
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        return {}
    try:
        rows = await async_execute_on_intelligence(
            "SELECT task_name, enabled, changed_by, changed_at, reason "
            "FROM dbo.collector_task_overrides WITH (NOLOCK)"
        ) or []
        return {
            (row.get("task_name") or ""): row
            for row in rows
            if row.get("task_name")
        }
    except Exception as e:
        logger.debug("[CollectorHealth] falha a ler overrides (nao-critico): %s", e)
        return {}


async def _fetch_active_state() -> Dict[str, Dict[str, Any]]:
    """Le KPI_STG_ACTIVE_TABLE — retorna dict por Table_Name."""
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        logger.warning("[CollectorHealth] async_execute_on_intelligence nao disponivel")
        return {}

    try:
        rows = await async_execute_on_intelligence(
            "SELECT Table_Name, Active_Slot, Last_Swap_Time, "
            "Collection_Start_Time, Collection_End_Time, Servers_Collected, Created_Date "
            "FROM dbo.KPI_STG_ACTIVE_TABLE WITH (NOLOCK)"
        ) or []
        return {
            (row.get("Table_Name") or "").upper(): row
            for row in rows
            if row.get("Table_Name")
        }
    except Exception as e:
        logger.warning("[CollectorHealth] falha a ler KPI_STG_ACTIVE_TABLE: %s", e)
        return {}


# Whitelist de prefixos de tabelas aceites para o fallback MAX(Update_TS).
# Evita SQL injection mesmo tendo controlo via config.yaml.
_SAFE_TABLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


async def _fetch_schedule_meta() -> Dict[str, Dict[str, Any]]:
    """Le WDB_COLLECTION_SCHEDULE_META (freshness guard D4) — dict por Table_Name.

    Fonte de frescura para familias HEARTBEAT: tabelas nao-BLUE/GREEN sem
    coluna de timestamp (ex.: reconcile_inst_envs -> KPI_MSSQL_INST_ENVS),
    cujo adapter regista vida em Last_Success_TS em cada ciclo bem-sucedido.
    """
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        return {}
    try:
        rows = await async_execute_on_intelligence(
            "SELECT Table_Name, Collector_Name, Expected_Interval_Minutes, "
            "Freshness_Source, Last_Success_TS "
            "FROM dbo.WDB_COLLECTION_SCHEDULE_META WITH (NOLOCK)"
        ) or []
        return {
            (row.get("Table_Name") or "").upper(): row
            for row in rows
            if row.get("Table_Name")
        }
    except Exception as e:
        logger.debug("[CollectorHealth] falha a ler WDB_COLLECTION_SCHEDULE_META (nao-critico): %s", e)
        return {}


async def _fetch_max_update_ts(tables: List[str]) -> Tuple[Optional[datetime], Optional[str]]:
    """Fallback para collectors non-BG: MAX(<timestamp_col>) da primeira tabela
    valida, com fallback por multiplas colunas (TIMESTAMP_COLUMN_CANDIDATES).

    Returns:
        (datetime, column_name) se encontrado, (None, None) se nao.
    """
    if not tables:
        return None, None
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        return None, None

    for raw_tbl in tables:
        tbl = str(raw_tbl or "").strip()
        if not tbl or not _SAFE_TABLE_PATTERN.match(tbl):
            continue
        for col in TIMESTAMP_COLUMN_CANDIDATES:
            try:
                rows = await async_execute_on_intelligence(
                    f"SELECT MAX([{col}]) AS last_ts FROM dbo.[{tbl}] WITH (NOLOCK) "
                    f"WHERE [{col}] >= DATEADD(DAY, -7, SYSUTCDATETIME())"
                )
                if rows and rows[0].get("last_ts"):
                    logger.debug(
                        "[CollectorHealth] non-BG timestamp: %s.%s = %s",
                        tbl, col, rows[0]["last_ts"],
                    )
                    return rows[0]["last_ts"], col
            except Exception:
                continue
    return None, None


def _best_active_row(task: Dict[str, Any], active_by_table: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Para cada task, escolher a row de KPI_STG_ACTIVE_TABLE mais recente.

    Um task pode ter multiplas target_tables — usamos a row com Last_Swap_Time mais recente.
    """
    tables = task.get("tables") or []
    if not tables:
        return None
    best: Optional[Dict[str, Any]] = None
    best_ts: Optional[datetime] = None
    for tbl in tables:
        row = active_by_table.get(str(tbl).upper())
        if not row:
            continue
        ts = row.get("Last_Swap_Time")
        if best is None or (ts and (best_ts is None or ts > best_ts)):
            best = row
            best_ts = ts
    return best


def _classify(
    task: Dict[str, Any],
    active_row: Optional[Dict[str, Any]],
) -> Tuple[str, str, Optional[int]]:
    """Retorna (status, reason, age_seconds)."""
    if not task.get("enabled", True):
        reason = task.get("disabled_reason") or "Motivo nao documentado no config.yaml"
        return STATUS_DISABLED, reason, None

    # Verificar erro recente primeiro (toma precedencia sobre age)
    interval_min = int(task.get("interval_minutes") or 15)
    err_window_sec = max(interval_min * 60 * 2, 600)  # 2x interval ou 10 min
    recent_errs = recent_errors_for_task(task.get("name", ""), within_seconds=err_window_sec)
    if recent_errs:
        msg = recent_errs[0].get("message", "")[:200]
        return STATUS_FAILED, f"Erro recente em logs: {msg}", None

    if not active_row or not active_row.get("Last_Swap_Time"):
        return STATUS_NEVER_RAN, "Nao existe entry em KPI_STG_ACTIVE_TABLE nem timestamp em tabelas target", None

    age_sec = _seconds_ago(active_row.get("Last_Swap_Time"))
    if age_sec is None:
        return STATUS_NEVER_RAN, "Timestamp invalido", None

    age_min = age_sec / 60.0
    if age_min <= interval_min * 1.5:
        return STATUS_FRESH, "OK", age_sec
    if age_min <= interval_min * 3:
        return STATUS_RECENT, f"Ultimo run ha {int(age_min)} min (interval {interval_min} min)", age_sec

    # QUIET: collector event-driven onde 0 dados novos e comportamento esperado
    # (sistema saudavel, sem eventos a reportar). Distingue de STALE genuino.
    task_name = task.get("name", "")
    if _is_event_driven_task(task_name):
        return STATUS_QUIET, f"Sem eventos novos ha {int(age_min)} min (collector funcional, sistema saudavel)", age_sec

    return STATUS_STALE, f"Ultimo swap ha {int(age_min)} min (>2x interval {interval_min} min)", age_sec


async def compute_health(
    env_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Retorna snapshot completo de todos os tasks + summary agregado."""
    tasks = get_tasks()
    active_by_table = await _fetch_active_state()
    overrides = await _fetch_overrides()
    schedule_meta = await _fetch_schedule_meta()

    results: List[Dict[str, Any]] = []
    summary = {
        "total": 0,
        STATUS_FRESH.lower(): 0,
        STATUS_RECENT.lower(): 0,
        STATUS_QUIET.lower(): 0,
        STATUS_STALE.lower(): 0,
        STATUS_FAILED.lower(): 0,
        STATUS_DISABLED.lower(): 0,
        STATUS_NEVER_RAN.lower(): 0,
    }

    env_f = (env_filter or "").strip().upper() or None
    status_f = (status_filter or "").strip().upper() or None
    search_lower = (search or "").strip().lower() or None

    for task in tasks:
        name = task.get("name") or ""
        env = (task.get("environment") or "").upper()

        # Override de enabled via BD (toma precedencia sobre config.yaml)
        ovr = overrides.get(name)
        if ovr is not None:
            task = dict(task)  # shallow copy para nao mutar o cache
            task["enabled"] = bool(ovr.get("enabled"))
            task["_override"] = ovr  # para expor no JSON
        interval_min = int(task.get("interval_minutes") or 15)
        enabled = bool(task.get("enabled", True))

        active_row = _best_active_row(task, active_by_table)
        data_source = "blue_green"  # fonte usada para computar last_run

        # Fallback HEARTBEAT (freshness guard D4, 2026-07-27): familias sem
        # swap E sem timestamp na target (ex.: reconcile_inst_envs ->
        # KPI_MSSQL_INST_ENVS) registam vida em SCHEDULE_META.Last_Success_TS.
        # A cadencia REAL vem de Expected_Interval_Minutes (ex.: 1440 p/ tasks
        # 1x/dia com date-gate, cujo interval_minutes do config e' so o tick).
        if not active_row:
            for tbl in (task.get("tables") or []):
                meta = schedule_meta.get(str(tbl).upper())
                if meta and meta.get("Freshness_Source") == "HEARTBEAT" and meta.get("Last_Success_TS"):
                    active_row = {
                        "Table_Name": tbl,
                        "Active_Slot": None,
                        "Last_Swap_Time": meta.get("Last_Success_TS"),
                        "Collection_Start_Time": None,
                        "Collection_End_Time": None,
                        "Servers_Collected": None,
                        "_source": "heartbeat_meta",
                    }
                    data_source = "heartbeat_meta"
                    expected = meta.get("Expected_Interval_Minutes")
                    if expected:
                        task = dict(task)
                        task["interval_minutes"] = int(expected)
                    break

        # Fallback non-Blue/Green: se nao ha entry em KPI_STG_ACTIVE_TABLE E o
        # task esta na whitelist, tentar MAX(<timestamp_col>) directo da tabela
        # com fallback por multiplas colunas (Fix 1).
        if not active_row and _is_non_bg_task(name):
            max_ts, col_found = await _fetch_max_update_ts(task.get("tables") or [])
            if max_ts:
                active_row = {
                    "Table_Name": (task.get("tables") or [None])[0],
                    "Active_Slot": None,
                    "Last_Swap_Time": max_ts,
                    "Collection_Start_Time": None,
                    "Collection_End_Time": None,
                    "Servers_Collected": None,
                    "_source": f"non_bg_max_{col_found}",
                }
                data_source = f"non_bg_max_{col_found}"
            else:
                data_source = "non_bg_no_data"

        status, reason, age_sec = _classify(task, active_row)

        if status == STATUS_QUIET:
            data_source = "quiet_event_driven"

        # Count em summary (sempre, mesmo com filtros — summary e global)
        summary["total"] += 1
        key = status.lower()
        if key in summary:
            summary[key] += 1

        # Filtros (aplicar apenas a lista, nao ao summary)
        if env_f and env != env_f:
            continue
        if status_f and status != status_f:
            continue
        if search_lower and search_lower not in name.lower():
            continue

        last_run_iso = None
        coll_start = None
        coll_end = None
        duration_ms = None
        servers_collected = None
        active_slot = None
        if active_row:
            lst = active_row.get("Last_Swap_Time")
            if lst:
                last_run_iso = lst.isoformat() if hasattr(lst, "isoformat") else str(lst)
            cs = active_row.get("Collection_Start_Time")
            ce = active_row.get("Collection_End_Time")
            coll_start = cs.isoformat() if hasattr(cs, "isoformat") else (str(cs) if cs else None)
            coll_end = ce.isoformat() if hasattr(ce, "isoformat") else (str(ce) if ce else None)
            if cs and ce:
                try:
                    duration_ms = int((ce - cs).total_seconds() * 1000)
                except Exception:
                    duration_ms = None
            servers_collected = active_row.get("Servers_Collected")
            active_slot = active_row.get("Active_Slot")

        next_run_expected = None
        if last_run_iso and active_row and active_row.get("Last_Swap_Time"):
            try:
                next_dt = active_row["Last_Swap_Time"]
                from datetime import timedelta
                next_dt = next_dt + timedelta(minutes=interval_min)
                next_run_expected = next_dt.isoformat()
            except Exception:
                pass

        results.append({
            "name": name,
            "class": task.get("class"),
            "module": task.get("module"),
            "environment": env or None,
            "interval_minutes": interval_min,
            "enabled": enabled,
            "description": task.get("description"),
            "target_tables": task.get("tables") or [],
            "last_run": last_run_iso,
            "last_run_ago_seconds": age_sec,
            "collection_start": coll_start,
            "collection_end": coll_end,
            "collection_duration_ms": duration_ms,
            "servers_collected": servers_collected,
            "active_slot": active_slot,
            "next_run_expected": next_run_expected,
            "status": status,
            "status_reason": reason,
            "data_source": data_source,
            "failure_count_24h": failure_count(name, within_hours=24),
            "override": task.get("_override"),  # None se config.yaml, dict se override BD
        })

    # Ordenacao: status critico primeiro, depois por idade desc
    results.sort(key=lambda r: (
        STATUS_ORDER.get(r["status"], 99),
        -(r.get("last_run_ago_seconds") or 0),
    ))

    return {
        "summary": summary,
        "tasks": results,
        "filters_applied": {
            "environment": env_filter,
            "status": status_filter,
            "search": search,
        },
    }
