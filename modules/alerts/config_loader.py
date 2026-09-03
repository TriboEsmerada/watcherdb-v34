"""
Le seccao alerts: do services/web_service/config.yaml (S3-14 C2).

Padrao defensivo — config.yaml pode nao ter a seccao alerts ainda (cliente
em pre-deploy). Neste caso, retorna defaults safe com todos os channels
desactivados.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger("watcherdb.alerts.config")


_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "dedup_windows": {
        "critical": 300,    # 5 min
        "warning": 900,     # 15 min
        "info": 3600,       # 1 hora
    },
    "email": {"enabled": False},
    "teams": {"enabled": False},
    "slack": {"enabled": False},
}


def load_alert_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Carrega seccao alerts: do config.yaml.

    Args:
        config_path: path para config.yaml. Se None, procura em
            services/web_service/config.yaml relativo a repo root.

    Returns:
        Dict com a config. Sempre retorna dict valido mesmo se ficheiro
        ausente ou seccao em falta — fallback para _DEFAULT_CONFIG.
    """
    if config_path is None:
        # PROJECT_ROOT/services/web_service/config.yaml — 3 niveis acima deste ficheiro
        here = Path(__file__).resolve()
        config_path = here.parent.parent.parent / "services" / "web_service" / "config.yaml"

    config_path = Path(config_path)
    if not config_path.exists():
        logger.warning("config.yaml nao encontrado em %s — usando defaults (alerts disabled)", config_path)
        return dict(_DEFAULT_CONFIG)

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            full = yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.error("Erro a ler %s: %s — usando defaults", config_path, exc)
        return dict(_DEFAULT_CONFIG)

    alerts = full.get("alerts")
    if not isinstance(alerts, dict):
        logger.info("Seccao alerts: ausente em %s — usando defaults (alerts disabled)", config_path)
        return dict(_DEFAULT_CONFIG)

    # Merge raso com defaults (garantir keys obrigatorios)
    merged = dict(_DEFAULT_CONFIG)
    merged.update(alerts)
    # dedup_windows pode precisar de merge nested
    dw = _DEFAULT_CONFIG["dedup_windows"].copy()
    dw.update(alerts.get("dedup_windows", {}))
    merged["dedup_windows"] = dw

    return merged
