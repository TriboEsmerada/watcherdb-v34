"""
InventoryRepo -- inventario de servidores do portal V3.3 (E6, 2026-08-19)
========================================================================

Plano: docs/context/PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md (E6).
Fonte: metadata.monitored_server (+ monitored_server_database) na
WatcherDB_Intelligence -- alimentada pelo collector V1 a partir do servers.json
canonico (fonte unica). O portal passa a LER a BD; o ficheiro local
config/servers.json fica para credenciais (connection_pool) e como fallback.

Contrato de saida = o mesmo dos leitores antigos (lista de dicts com as chaves
do servers.json: id, host, instance, port, environment, enabled, description,
priority, has_alwayson, ag_name, ag_listener, databases[], database_count,
databases_discovered_at) -- os consumidores nao mudam de forma.

Regras:
  * settings.inventory_source: "db" (default) | "file" (rollback 1 linha / env var).
  * Fail-open: se a BD falhar ou vier vazia -> ficheiro local + WARN
    [INVENTORY_REPO] (nunca sidebar vazia por causa da BD).
  * Cache em memoria por inventory_cache_seconds (default 60s); thread-safe.
  * Identidade: sql_monitoring, SELECT only (GRANT SELECT nas metadata.* novas).
  * Nao expoe password (a BD nao a tem; o ficheiro so e' lido para inventario
    quando em fallback -- e mesmo ai a chave 'password' e' removida do retorno).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SQL_SERVERS = """
SELECT m.server_id, m.instance_id, m.host, m.instance_name, m.port, m.environment, m.priority,
       m.description, m.enabled, m.is_active, m.has_alwayson, m.ag_name, m.ag_listener,
       m.sql_servername_alias, m.last_seen_in_source_at, m.updated_at
FROM metadata.monitored_server m WITH (NOLOCK)
WHERE m.tenant_id = 'default' AND m.is_active = 1
ORDER BY m.instance_id
"""

_SQL_DATABASES = """
SELECT d.server_id, d.database_name, d.database_id, d.state, d.recovery_model,
       d.is_read_only, d.is_accessible, d.compatibility_level, d.last_seen_in_source_at
FROM metadata.monitored_server_database d WITH (NOLOCK)
JOIN metadata.monitored_server m WITH (NOLOCK) ON m.server_id = d.server_id
WHERE m.tenant_id = 'default' AND m.is_active = 1 AND d.is_active = 1
ORDER BY d.server_id, d.database_name
"""

_SENSITIVE_KEYS = ("password", "username", "use_windows_auth", "driver")


def _iso(v) -> Optional[str]:
    try:
        return v.isoformat() if v is not None and hasattr(v, "isoformat") else (str(v) if v is not None else None)
    except Exception:
        return None


def rows_to_entries(servers: List[Dict[str, Any]], databases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converte rows da BD no formato de entrada do servers.json (pura, testavel)."""
    dbs_by_server: Dict[Any, List[Dict[str, Any]]] = {}
    seen_by_server: Dict[Any, Any] = {}
    for d in databases or []:
        sid = d.get("server_id")
        ls = d.get("last_seen_in_source_at")
        if ls is not None and (seen_by_server.get(sid) is None or ls > seen_by_server[sid]):
            seen_by_server[sid] = ls
        dbs_by_server.setdefault(sid, []).append({
            "name": d.get("database_name"),
            "database_id": d.get("database_id"),
            "state": d.get("state"),
            "recovery_model": d.get("recovery_model"),
            "is_read_only": bool(d["is_read_only"]) if d.get("is_read_only") is not None else None,
            "is_accessible": bool(d["is_accessible"]) if d.get("is_accessible") is not None else None,
            "compatibility_level": d.get("compatibility_level"),
        })
    out: List[Dict[str, Any]] = []
    for s in servers or []:
        dbs = dbs_by_server.get(s.get("server_id"), [])
        last_seen = seen_by_server.get(s.get("server_id"))
        out.append({
            "id": s.get("instance_id"),
            "host": s.get("host"),
            "instance": s.get("instance_name"),
            "port": int(s["port"]) if s.get("port") is not None else 1433,
            "environment": s.get("environment"),
            "priority": int(s["priority"]) if s.get("priority") is not None else 1,
            "enabled": bool(s.get("enabled", 1)),
            "description": s.get("description") or "",
            "has_alwayson": bool(s.get("has_alwayson") or 0),
            "ag_name": s.get("ag_name"),
            "ag_listener": s.get("ag_listener"),
            "sql_servername_alias": s.get("sql_servername_alias"),
            "databases": dbs,
            "database_count": len(dbs),
            "databases_discovered_at": _iso(last_seen),
            "_source": "db",
        })
    return out


class InventoryRepo:
    def __init__(self, file_path: Optional[Path] = None, cache_seconds: Optional[int] = None,
                 source: Optional[str] = None):
        self._lock = threading.RLock()
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._cache_at: float = 0.0
        self._cache_source: str = "none"
        self._file_path = file_path
        self._cache_seconds = cache_seconds
        self._source_override = source

    # -- config -----------------------------------------------------------
    def _settings(self):
        try:
            from watcherdb.core.settings import settings
            return settings
        except Exception:  # pragma: no cover
            return None

    @property
    def source_mode(self) -> str:
        if self._source_override:
            return self._source_override
        s = self._settings()
        return (getattr(s, "inventory_source", "db") or "db").lower() if s else "db"

    @property
    def cache_seconds(self) -> int:
        if self._cache_seconds is not None:
            return self._cache_seconds
        s = self._settings()
        return int(getattr(s, "inventory_cache_seconds", 60) or 60) if s else 60

    def _file(self) -> Path:
        if self._file_path is not None:
            return Path(self._file_path)
        try:
            from watcherdb.core.paths import config_dir
            return config_dir() / "servers.json"
        except Exception:
            return Path("config/servers.json")

    # -- loaders ------------------------------------------------------------
    def _local_credential_ids(self) -> Optional[set]:
        """ids (UPPER) com entrada no config/servers.json local = tem credenciais para
        ligacao directa (connection_pool). None se o ficheiro nao existir/for ilegivel.
        Nao decifra nada; so' le ids. (Parecer v33-specialist E6: servidor na BD sem
        creds locais -> drill-down partido; marcar/ocultar ate haver creds.)"""
        try:
            with open(self._file(), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            ids = set()
            for s in cfg.get("monitored_servers", cfg.get("servers", [])) or []:
                if isinstance(s, dict) and (s.get("password") or s.get("use_windows_auth")):
                    sid = (s.get("id") or s.get("server_id") or "").strip().upper().replace("\\", "_")
                    if sid:
                        ids.add(sid)
            return ids
        except Exception:
            return None

    def _load_db(self) -> List[Dict[str, Any]]:
        from api.connection_pool import execute_on_intelligence  # import tardio (evita ciclo no arranque)
        servers = execute_on_intelligence(_SQL_SERVERS)
        if not servers:
            raise RuntimeError("metadata.monitored_server vazia (sync ainda nao correu?)")
        databases = execute_on_intelligence(_SQL_DATABASES)
        entries = rows_to_entries(servers, databases)
        cred_ids = self._local_credential_ids()
        missing = []
        for e in entries:
            has = True if cred_ids is None else ((e.get("id") or "").upper() in cred_ids)
            e["has_credentials"] = has
            if not has:
                missing.append(e.get("id"))
        if missing:
            logger.warning(f"[INVENTORY_REPO] {len(missing)} servidor(es) na BD sem credenciais no servers.json local "
                           f"(ocultos na sidebar ate serem provisionados): {missing[:10]}")
        return entries

    def _load_file(self) -> List[Dict[str, Any]]:
        p = self._file()
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        raw = cfg.get("monitored_servers", cfg.get("servers", [])) or []
        out = []
        for s in raw:
            if not isinstance(s, dict):
                continue
            e = {k: v for k, v in s.items() if k not in _SENSITIVE_KEYS}
            e.setdefault("id", s.get("server_id"))
            e.setdefault("enabled", True)
            dbs = e.get("databases") or []
            e["databases"] = [{"name": d} if isinstance(d, str) else d for d in dbs]
            e["database_count"] = e.get("database_count") or len(e["databases"])
            e["has_credentials"] = bool(s.get("password") or s.get("use_windows_auth"))
            e["_source"] = "file"
            out.append(e)
        return out

    # -- API ----------------------------------------------------------------
    def servers(self, enabled_only: bool = True, environment: Optional[str] = None,
                force: bool = False, require_credentials: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            now = time.monotonic()
            if force or self._cache is None or (now - self._cache_at) >= self.cache_seconds:   # 0 = sem cache
                self._refresh()
            items = list(self._cache or [])
        if enabled_only:
            items = [s for s in items if s.get("enabled", True)]
        if require_credentials:
            items = [s for s in items if s.get("has_credentials", True)]
        if environment and environment.upper() != "ALL":
            env = environment.lower()
            items = [s for s in items if (s.get("environment") or "").lower() == env]
        return items

    def get(self, server_id: str) -> Optional[Dict[str, Any]]:
        sid = (server_id or "").strip().upper().replace("\\", "_")
        for s in self.servers(enabled_only=False):
            if (s.get("id") or "").upper() == sid:
                return s
        return None

    @property
    def source(self) -> str:
        return self._cache_source

    def _refresh(self) -> None:
        mode = self.source_mode
        if mode == "db":
            try:
                self._cache = self._load_db()
                self._cache_source = "db"
                self._cache_at = time.monotonic()
                return
            except Exception as e:
                logger.warning(f"[INVENTORY_REPO] BD indisponivel/vazia ({e}) -- fallback ao ficheiro local")
        try:
            self._cache = self._load_file()
            self._cache_source = "file"
        except Exception as e:
            logger.error(f"[INVENTORY_REPO] ficheiro local tambem falhou ({e}) -- a manter cache anterior ({len(self._cache or [])})")
            if self._cache is None:
                self._cache = []
                self._cache_source = "none"
        self._cache_at = time.monotonic()


_REPO: Optional[InventoryRepo] = None
_REPO_LOCK = threading.Lock()


def get_inventory_repo() -> InventoryRepo:
    global _REPO
    if _REPO is None:
        with _REPO_LOCK:
            if _REPO is None:
                _REPO = InventoryRepo()
    return _REPO


def load_monitored_servers(enabled_only: bool = False, require_credentials: bool = True) -> List[Dict[str, Any]]:
    """Substituto directo de `_load_monitored_servers()` (helpers/intelligence_kpis):
    mesma forma de retorno (lista de dicts estilo servers.json), fonte BD c/ fallback.
    require_credentials=True por defeito: os consumidores destes loaders LIGAM aos
    servidores (jobs, diagnosticos) -- sem creds locais so' dariam erro."""
    return get_inventory_repo().servers(enabled_only=enabled_only, require_credentials=require_credentials)
