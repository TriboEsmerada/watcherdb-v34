"""Parser dos logs do WatcherDBCollector service.

Le tail de `collectors.log` (info) e `errors.log` (erros) e faz match por task_name.
Cache de 30s para evitar I/O repetido.
"""

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.collector_health.config_loader import get_logs_dir

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30
_TAIL_LINES = 500  # ~ultimas horas de log

_cache_lock = threading.Lock()
_cached_errors: Optional[List[Dict[str, Any]]] = None
_cached_info: Optional[List[Dict[str, Any]]] = None
_cached_at_err: float = 0.0
_cached_at_inf: float = 0.0


# --- Regex patterns ---
# errors.log:
#   2026-04-16 15:35:20 | ERROR | WatcherDBService | _execute_collector |
#      [collect_blocked_sessions_PRD] Failed - Error: ..., Duration: 120.3s
_RE_ERROR = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s*[|,]\s*"
    r"(?P<level>ERROR|WARNING|CRITICAL)\s*[|,]\s*"
    r"(?P<logger>[^|]+?)\s*[|,]\s*"
    r"(?P<func>[^|]+?)\s*[|,]\s*"
    r"(?:\[(?P<task>[^\]]+)\]\s*)?"
    r"(?P<msg>.*)$",
    re.IGNORECASE,
)

# collectors.log (info)
_RE_INFO = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s*[|,]\s*"
    r"(?P<level>\w+)\s*[|,]\s*"
    r".*?(?:\[(?P<task>[^\]]+)\])?\s*(?P<msg>.*)$",
    re.IGNORECASE,
)

_RE_DURATION = re.compile(r"[Dd]uration:\s*(\d+(?:\.\d+)?)\s*s")


def _parse_timestamp(s: str) -> Optional[datetime]:
    """Aceita ISO com espaco, T, e fracoes (. ou ,)."""
    s = s.replace(",", ".")
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _tail_file(path: Path, n_lines: int = _TAIL_LINES) -> List[str]:
    """Le as ultimas n linhas de um ficheiro (best-effort, file safe)."""
    if not path.exists() or not path.is_file():
        return []
    try:
        # Estrategia simples: read full se ficheiro < 2MB, senao tail binary
        size = path.stat().st_size
        if size < 2 * 1024 * 1024:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return lines[-n_lines:]
        # Ficheiro grande: tail binary
        with open(path, "rb") as f:
            f.seek(0, 2)  # end
            end = f.tell()
            block = 65536
            data = b""
            pos = end
            while len(data.splitlines()) <= n_lines + 10 and pos > 0:
                step = min(block, pos)
                pos -= step
                f.seek(pos)
                data = f.read(step) + data
        text = data.decode("utf-8", errors="replace")
        return text.splitlines(keepends=True)[-n_lines:]
    except Exception as e:
        logger.warning("[LogParser] falha a ler %s: %s", path, e)
        return []


def _parse_lines(
    lines: List[str],
    regex: re.Pattern,
    default_level: str = "INFO",
) -> List[Dict[str, Any]]:
    """Parse lines em dicts estruturados."""
    entries: List[Dict[str, Any]] = []
    for raw in lines:
        line = raw.rstrip("\n\r")
        if not line.strip():
            continue
        m = regex.match(line)
        if not m:
            continue
        ts = _parse_timestamp(m.group("ts"))
        if not ts:
            continue
        task = (m.groupdict().get("task") or "").strip() or None
        msg = (m.group("msg") or "").strip()
        level = (m.groupdict().get("level") or default_level).upper()
        entry: Dict[str, Any] = {
            "timestamp": ts.isoformat(),
            "_ts_epoch": ts.timestamp(),
            "level": level,
            "task": task,
            "message": msg,
            "raw": line,
        }
        dm = _RE_DURATION.search(msg)
        if dm:
            try:
                entry["duration_ms"] = int(float(dm.group(1)) * 1000)
            except ValueError:
                pass
        entries.append(entry)
    return entries


def load_errors(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Tail do errors.log parseado (fallback para collectors.log filtrado por ERROR)."""
    global _cached_errors, _cached_at_err
    now = time.time()
    with _cache_lock:
        if (not force_refresh and _cached_errors is not None
                and (now - _cached_at_err) < _CACHE_TTL_SECONDS):
            return _cached_errors

        logs_dir = get_logs_dir()
        entries: List[Dict[str, Any]] = []
        if logs_dir:
            # Primary: errors.log
            errors_file = logs_dir / "errors.log"
            if errors_file.exists():
                entries = _parse_lines(_tail_file(errors_file), _RE_ERROR, "ERROR")
            # Fallback: collectors.log filtrado
            if not entries:
                main_log = logs_dir / "collectors.log"
                if main_log.exists():
                    parsed = _parse_lines(_tail_file(main_log), _RE_ERROR, "INFO")
                    entries = [e for e in parsed if e["level"] in ("ERROR", "CRITICAL")]
        _cached_errors = entries
        _cached_at_err = now
        return entries


def load_info(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Tail do collectors.log (info)."""
    global _cached_info, _cached_at_inf
    now = time.time()
    with _cache_lock:
        if (not force_refresh and _cached_info is not None
                and (now - _cached_at_inf) < _CACHE_TTL_SECONDS):
            return _cached_info

        logs_dir = get_logs_dir()
        entries: List[Dict[str, Any]] = []
        if logs_dir:
            for name in ("collectors.log", "service.log"):
                p = logs_dir / name
                if p.exists():
                    entries = _parse_lines(_tail_file(p), _RE_INFO, "INFO")
                    break
        _cached_info = entries
        _cached_at_inf = now
        return entries


def recent_errors_for_task(task_name: str, within_seconds: int = 1800) -> List[Dict[str, Any]]:
    """Erros para um task especifico nos ultimos N segundos (default 30min)."""
    cutoff = time.time() - within_seconds
    return [
        e for e in load_errors()
        if e.get("task") == task_name and e.get("_ts_epoch", 0) >= cutoff
    ]


def logs_for_task(task_name: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Combina info + erros para um task, ordenado por timestamp desc."""
    combined = [e for e in load_info() if e.get("task") == task_name]
    combined += [e for e in load_errors() if e.get("task") == task_name]
    combined.sort(key=lambda e: e.get("_ts_epoch", 0), reverse=True)
    return combined[:limit]


def failure_count(task_name: str, within_hours: int = 24) -> int:
    """Count de erros recentes para um task."""
    cutoff = time.time() - within_hours * 3600
    return sum(1 for e in load_errors()
               if e.get("task") == task_name and e.get("_ts_epoch", 0) >= cutoff)
