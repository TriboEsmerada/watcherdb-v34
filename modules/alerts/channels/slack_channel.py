"""
Slack channel via Incoming Webhook.

slack-sdk WebhookClient e sincrono — wrap em anyio.to_thread.
Webhook URL via encrypted env-var ALERTS_SLACK_WEBHOOK (Fernet pattern).
"""
from __future__ import annotations

import logging
from typing import Optional

from modules.alerts.base import AlertPayload, BaseChannel


logger = logging.getLogger("watcherdb.alerts.slack")


def _severity_emoji(severity: str) -> str:
    return {
        "critical": ":rotating_light:",
        "warning": ":warning:",
        "info": ":information_source:",
    }.get(severity, ":bell:")


class SlackChannel(BaseChannel):
    name = "slack"

    def __init__(self, cfg: dict):
        self._webhook = self._resolve_webhook(cfg)

    @staticmethod
    def _resolve_webhook(cfg: dict) -> str:
        try:
            from services.secrets import get_secret
            resolved = get_secret("ALERTS_SLACK_WEBHOOK", "")
            if resolved:
                return resolved
        except Exception:
            pass
        return cfg.get("webhook_url", "")

    @property
    def is_configured(self) -> bool:
        return bool(
            self._webhook
            and self._webhook.startswith("https://hooks.slack.com")
        )

    async def send(self, alert: AlertPayload) -> tuple[bool, Optional[str]]:
        if not self.is_configured:
            return (False, "slack webhook not configured")

        try:
            import anyio
            from slack_sdk.webhook import WebhookClient  # lazy import
        except ImportError as exc:
            return (False, f"slack-sdk/anyio not installed: {exc}")

        emoji = _severity_emoji(alert.severity)
        text = (
            f"{emoji} *[{alert.severity.upper()}] {alert.title}*\n"
            f"Server: `{alert.server_id or 'n/a'}` | Source: `{alert.source}`\n"
            f"{alert.body[:1000]}"
        )

        def _sync_send():
            client = WebhookClient(self._webhook, timeout=10)
            return client.send(text=text)

        try:
            import anyio as _anyio
            resp = await _anyio.to_thread.run_sync(_sync_send)
            if getattr(resp, "status_code", None) == 200:
                return (True, None)
            return (False, f"slack HTTP {getattr(resp, 'status_code', '?')}")
        except Exception as exc:
            logger.warning("Slack send failed: %s", exc)
            return (False, f"{type(exc).__name__}: {exc}")
