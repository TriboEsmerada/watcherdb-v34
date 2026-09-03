"""
Email channel — aiosmtplib async dispatch.

Config (secção alerts.email em services/web_service/config.yaml):
    enabled: bool
    smtp_host, smtp_port, smtp_user
    from_address
    recipients: list[str]
    use_tls: bool
    smtp_password: via .env (encrypted secret ALERTS_SMTP_PASSWORD)
"""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from modules.alerts.base import AlertPayload, BaseChannel


logger = logging.getLogger("watcherdb.alerts.email")


class EmailChannel(BaseChannel):
    name = "email"

    def __init__(self, cfg: dict):
        self._host: str = cfg.get("smtp_host", "")
        self._port: int = int(cfg.get("smtp_port", 587))
        self._user: str = cfg.get("smtp_user", "")
        self._from: str = cfg.get("from_address", "")
        self._recipients: list[str] = cfg.get("recipients", []) or []
        self._use_tls: bool = bool(cfg.get("use_tls", True))
        # Secret lookup — tenta env-var encrypted primeiro, fallback cfg plain.
        self._password = self._resolve_password(cfg)

    @staticmethod
    def _resolve_password(cfg: dict) -> str:
        """Resolve password via Fernet encrypted env-var ou plain do config."""
        try:
            from services.secrets import get_secret
            resolved = get_secret("ALERTS_SMTP_PASSWORD", "")
            if resolved:
                return resolved
        except Exception:
            pass
        return cfg.get("smtp_password", "")

    @property
    def is_configured(self) -> bool:
        return bool(self._host and self._recipients and self._from)

    async def send(self, alert: AlertPayload) -> tuple[bool, Optional[str]]:
        if not self.is_configured:
            return (False, "email channel not configured (missing smtp_host/recipients/from_address)")

        try:
            import aiosmtplib  # lazy import — so se email estiver activo
        except ImportError:
            return (False, "aiosmtplib not installed (add to requirements-alerting.txt)")

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[WatcherDB][{alert.severity.upper()}] {alert.title}"
            msg["From"] = self._from
            msg["To"] = ", ".join(self._recipients)

            body_text = (
                f"{alert.body}\n\n"
                f"---\n"
                f"Severity:     {alert.severity.upper()}\n"
                f"Server:       {alert.server_id or 'n/a'}\n"
                f"Source:       {alert.source}\n"
                f"Triggered by: {alert.triggered_by}\n"
                f"Timestamp:    {alert.timestamp.isoformat()}Z\n"
            )
            msg.attach(MIMEText(body_text, "plain", "utf-8"))

            kwargs = {
                "hostname": self._host,
                "port": self._port,
                "start_tls": self._use_tls,
                "timeout": 10,
            }
            if self._user and self._password:
                kwargs["username"] = self._user
                kwargs["password"] = self._password

            await aiosmtplib.send(msg, **kwargs)
            return (True, None)
        except Exception as exc:
            logger.warning("Email send failed: %s", exc)
            return (False, f"{type(exc).__name__}: {exc}")
