"""
Fallback channel — sempre activo, zero deps externas.

Escreve alert no logger "watcherdb.alerts". Serve como:
  1. Safety net se todos os outros channels falharem
  2. Smoke test da infra asyncio em tests
  3. Dev/staging onde SMTP/Teams/Slack nao estao configurados
"""
from __future__ import annotations

import logging
from typing import Optional

from modules.alerts.base import AlertPayload, BaseChannel


logger = logging.getLogger("watcherdb.alerts")


class LogChannel(BaseChannel):
    name = "log"

    @property
    def is_configured(self) -> bool:
        return True  # sempre activo

    async def send(self, alert: AlertPayload) -> tuple[bool, Optional[str]]:
        # Nivel do logger depende da severidade do alerta
        level = {
            "critical": logging.ERROR,
            "warning": logging.WARNING,
            "info": logging.INFO,
        }.get(alert.severity, logging.INFO)

        logger.log(
            level,
            "[ALERT][%s] %s | server=%s | %s",
            alert.severity.upper(),
            alert.title,
            alert.server_id or "n/a",
            alert.body[:500],
        )
        return (True, None)
