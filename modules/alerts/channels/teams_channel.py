"""
Microsoft Teams channel via Incoming Webhook.

pymsteams e sincrono — wrap em anyio.to_thread para nao bloquear o event loop.
Webhook URL via encrypted env-var ALERTS_TEAMS_WEBHOOK (Fernet pattern).
"""
from __future__ import annotations

import logging
from typing import Optional

from modules.alerts.base import AlertPayload, BaseChannel


logger = logging.getLogger("watcherdb.alerts.teams")


def _severity_color(severity: str) -> str:
    """Hex color for Teams connector card (sem '#')."""
    return {
        "critical": "D13438",  # vermelho
        "warning": "FFA500",   # laranja
        "info": "0078D4",      # azul
    }.get(severity, "0078D4")


class TeamsChannel(BaseChannel):
    name = "teams"

    def __init__(self, cfg: dict):
        self._webhook = self._resolve_webhook(cfg)
        self._timeout = int(cfg.get("timeout_seconds", 10))

    @staticmethod
    def _resolve_webhook(cfg: dict) -> str:
        try:
            from services.secrets import get_secret
            resolved = get_secret("ALERTS_TEAMS_WEBHOOK", "")
            if resolved:
                return resolved
        except Exception:
            pass
        return cfg.get("webhook_url", "")

    @property
    def is_configured(self) -> bool:
        return bool(self._webhook and self._webhook.startswith("https://"))

    async def send(self, alert: AlertPayload) -> tuple[bool, Optional[str]]:
        if not self.is_configured:
            return (False, "teams webhook not configured")

        try:
            import anyio
            import pymsteams  # lazy import
        except ImportError as exc:
            return (False, f"pymsteams/anyio not installed: {exc}")

        def _sync_send():
            card = pymsteams.connectorcard(self._webhook)
            card.title(f"[{alert.severity.upper()}] {alert.title}")
            card.color(_severity_color(alert.severity))
            body_md = f"**Server:** {alert.server_id or 'n/a'}\n\n{alert.body[:1500]}"
            card.text(body_md)
            card.send()

        try:
            await anyio.to_thread.run_sync(_sync_send)
            return (True, None)
        except Exception as exc:
            logger.warning("Teams send failed: %s", exc)
            return (False, f"{type(exc).__name__}: {exc}")
