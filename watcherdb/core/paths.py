"""Resolver central de diretorios de estado gravavel (WATCHERDB_DATA_DIR).

Auditoria empacotamento 2026-07-03 (B0-4, B1-6, B1-7, B1-8): todo o estado
gravavel (cache, config editavel, inventario, logs, secrets) vive FORA do
diretorio de instalacao — Program Files e read-only para a conta do servico,
e o CWD de um servico Windows e System32.

Resolucao 3-tier (mesmo padrao de watcherdb/licensing/crl.py):
  1. env WATCHERDB_DATA_DIR       override explicito (testes, MSI, ops)
  2. C:\\ProgramData\\WatcherDB    producao (bundle PyInstaller frozen)
  3. raiz do projeto              dev — comportamento historico inalterado

Em dev (nao-frozen, sem env var) os paths resolvem para os sitios de sempre;
o flip para ProgramData acontece APENAS no bundle congelado.
"""
import os
import sys
from pathlib import Path

_PROGRAMDATA = Path(r"C:\ProgramData\WatcherDB")


def is_frozen() -> bool:
    """True quando a correr dentro de um bundle PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Raiz do projeto em dev; _internal/ no bundle onedir."""
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    """Diretorio base de estado gravavel (3-tier)."""
    env = os.getenv("WATCHERDB_DATA_DIR")
    if env:
        return Path(env)
    if is_frozen():
        return _PROGRAMDATA
    return project_root()


def _ensure(d: Path) -> Path:
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Sem permissao para criar (ex.: dirs ainda nao criados pelo
        # instalador); devolve na mesma — o erro real aparece no primeiro
        # write, com o path completo visivel.
        pass
    return d


def config_dir() -> Path:
    """Config editavel (sql_servers.json, servers.json, custom_queries...)."""
    return _ensure(data_root() / "config")


def cache_dir() -> Path:
    """Cache regeneravel (watcherdb_cache.db pickle, dashboard_snapshot)."""
    return _ensure(data_root() / "cache")


def logs_dir() -> Path:
    """Logs de aplicacao/servico (Etapa 2)."""
    return _ensure(data_root() / "logs")


def secrets_dir() -> Path:
    """Blobs DPAPI (Etapa 1.4). ACL restrita definida pelo instalador."""
    return _ensure(data_root() / "secrets")


def inventory_dir() -> Path:
    """Inventario TAP (tap_servers.db, Excel). Dev historico: C:\\Server_Inventory."""
    env = os.getenv("WATCHERDB_DATA_DIR")
    if env:
        return _ensure(Path(env) / "inventory")
    if is_frozen():
        return _ensure(_PROGRAMDATA / "inventory")
    return _ensure(Path(r"C:\Server_Inventory"))


def bootstrap_config() -> None:
    """Seed config_dir() com skeletons vazios em falta (first-run frozen).

    Idempotente: so escreve ficheiros ausentes. Em dev (config_dir =
    raiz/config, ficheiros presentes) e no-op. Chamado no arranque antes
    de ler config. O bundle Standard nao traz os *.json vivos (B0-3), por
    isso o frozen first-run precisa destes skeletons para arrancar limpo.
    """
    import json
    cfg = config_dir()
    skeletons = {
        "servers.json": {"master_server": {}, "monitored_servers": []},
        "sql_servers.json": {"metadata": {"total_servers": 0, "version": "1.0"}, "servers": []},
        "custom_queries.json": [],
    }
    for name, skel in skeletons.items():
        target = cfg / name
        if not target.exists():
            try:
                target.write_text(json.dumps(skel, indent=2), encoding="utf-8")
            except OSError:
                pass  # dir sem permissao ainda; erro real surge no primeiro uso


def env_file() -> Path:
    """Primeiro .env existente na cadeia 3-tier; default data_root()/.env."""
    candidates = [data_root() / ".env", project_root() / ".env"]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]
