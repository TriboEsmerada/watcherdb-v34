"""
CORS Configuration — reads from config/config.yaml

Provides get_cors_config() for use with FastAPI CORSMiddleware.
"""

import logging
from pathlib import Path
from typing import Dict, Any

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


def _load_config() -> dict:
    """Load root config/config.yaml"""
    if not _CONFIG_PATH.exists():
        logger.warning(f"Config not found: {_CONFIG_PATH}")
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}


def get_cors_config() -> Dict[str, Any]:
    """
    Return CORS params dict for FastAPI CORSMiddleware.

    Reads from config/config.yaml -> security.cors section.
    Falls back to restrictive defaults (localhost only) if config missing.
    """
    config = _load_config()
    cors_section = config.get("security", {}).get("cors", {})

    if not cors_section.get("enabled", True):
        logger.warning("CORS disabled in config")
        return {
            "allow_origins": [],
            "allow_credentials": False,
            "allow_methods": [],
            "allow_headers": [],
        }

    allowed_origins = cors_section.get("allowed_origins", [])

    # Filter out CIDR ranges — not supported by CORS spec
    processed = []
    for origin in allowed_origins:
        if "/8" in origin or "/16" in origin or "/24" in origin:
            logger.warning(f"CIDR range in CORS not supported: {origin} — use reverse proxy")
        else:
            processed.append(origin)

    if not processed:
        logger.warning(
            "No CORS origins configured — defaulting to localhost only. "
            "Set security.cors.allowed_origins in config/config.yaml for production."
        )
        processed = ["http://localhost:8000", "http://localhost:3000"]

    cors_params = {
        "allow_origins": processed,
        "allow_credentials": cors_section.get("allow_credentials", True),
        "allow_methods": cors_section.get("allowed_methods", ["GET", "POST", "PUT", "DELETE"]),
        "allow_headers": cors_section.get("allowed_headers", [
            "Authorization", "Content-Type", "Accept", "Origin",
            "X-Requested-With", "X-Request-ID",
        ]),
        "max_age": cors_section.get("max_age", 600),
    }

    logger.info(f"CORS configured with {len(processed)} allowed origins: {processed}")
    return cors_params
