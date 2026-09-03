"""Parser do config.yaml do WatcherDBCollector service, com cache in-memory.

O config.yaml vive no projecto companion `WATCHERDB INTELLIGENCE V1`. O V5 le apenas —
nao modifica. Cache TTL de 60s para evitar I/O repetido em requests consecutivos.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # degradacao graceful

logger = logging.getLogger(__name__)

# Localizacao default do collector_service config.yaml (companion V1).
# Pode ser sobrescrito via env var WATCHERDB_COLLECTOR_CONFIG_PATH.
_DEFAULT_CANDIDATES = [
    # Relative from V5 root to V1 (most common dev layout)
    Path(__file__).resolve().parents[2].parent / "WATCHERDB INTELLIGENCE V1"
        / "services" / "collector_service" / "config.yaml",
    # Alternative absolute path fallback (user's primary layout)
    Path(r"C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python"
         r"\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1"
         r"\services\collector_service\config.yaml"),
]

_CACHE_TTL_SECONDS = 60
_cache_lock = threading.Lock()
_cached_config: Optional[Dict[str, Any]] = None
_cached_at: float = 0.0
_resolved_path: Optional[Path] = None


def _resolve_config_path() -> Optional[Path]:
    """Localiza o config.yaml. Usa env var se definida, senao tenta candidatos default."""
    global _resolved_path
    if _resolved_path and _resolved_path.exists():
        return _resolved_path

    env_path = os.environ.get("WATCHERDB_COLLECTOR_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            _resolved_path = p
            return p
        logger.warning("[CollectorConfig] WATCHERDB_COLLECTOR_CONFIG_PATH=%s nao existe", env_path)

    for cand in _DEFAULT_CANDIDATES:
        if cand.exists():
            _resolved_path = cand
            return cand

    logger.error(
        "[CollectorConfig] config.yaml nao encontrado. "
        "Definir WATCHERDB_COLLECTOR_CONFIG_PATH no .env."
    )
    return None


def get_config_path() -> Optional[Path]:
    """API publica para obter o path resolvido (ex: para o endpoint /config)."""
    return _resolve_config_path()


def load_config(force_refresh: bool = False) -> Dict[str, Any]:
    """Retorna o config parseado. Thread-safe, cacheado 60s."""
    global _cached_config, _cached_at

    now = time.time()
    with _cache_lock:
        if (not force_refresh
                and _cached_config is not None
                and (now - _cached_at) < _CACHE_TTL_SECONDS):
            return _cached_config

        if yaml is None:
            logger.error("[CollectorConfig] PyYAML nao esta instalado")
            return {"tasks": [], "_error": "PyYAML not installed"}

        path = _resolve_config_path()
        if not path:
            return {"tasks": [], "_error": "config.yaml nao encontrado"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _cached_config = data
            _cached_at = now
            logger.debug("[CollectorConfig] config.yaml carregado (%d tasks)",
                         len(data.get("tasks", [])))
            return data
        except Exception as e:
            logger.error("[CollectorConfig] falha a carregar %s: %s", path, e)
            return {"tasks": [], "_error": str(e)}


def get_tasks() -> List[Dict[str, Any]]:
    """Retorna apenas a lista de tasks do config."""
    return load_config().get("tasks", []) or []


def get_task(name: str) -> Optional[Dict[str, Any]]:
    """Lookup por nome exacto. None se nao existe."""
    for t in get_tasks():
        if t.get("name") == name:
            return t
    return None


def get_logs_dir() -> Optional[Path]:
    """Directoria de logs do collector_service (../logs/ relativo ao config)."""
    path = _resolve_config_path()
    if not path:
        return None
    candidate = path.parent / "logs"
    return candidate if candidate.exists() else None
