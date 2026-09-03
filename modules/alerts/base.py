"""
WatcherDB Alert Routing — base classes (S3-14 C2).

AlertPayload dataclass e BaseChannel ABC que todos os transports (email,
teams, slack, log) implementam.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


VALID_SEVERITIES = frozenset({"info", "warning", "critical"})
VALID_SOURCES = frozenset({"kpi", "performance", "manual", "test"})


@dataclass
class AlertPayload:
    """Normalized alert representation — todos os channels recebem este objecto."""

    alert_id: str                        # dedup key, ex: "perf:deadlocks:SQLSRV01:20260422T1430"
    source: str                          # 'kpi' | 'performance' | 'manual' | 'test'
    severity: str                        # 'info' | 'warning' | 'critical'
    title: str
    body: str
    server_id: Optional[str] = None
    triggered_by: str = "manual"         # 'manual' | 'threshold' | 'test'
    timestamp: datetime = field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity {self.severity!r} — must be one of {sorted(VALID_SEVERITIES)}"
            )
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source {self.source!r} — must be one of {sorted(VALID_SOURCES)}"
            )
        if not self.alert_id or not self.title:
            raise ValueError("alert_id e title sao obrigatorios")


class BaseChannel(ABC):
    """Transport abstracto — herdar e implementar send()."""

    name: str = "base"

    @abstractmethod
    async def send(self, alert: AlertPayload) -> tuple[bool, Optional[str]]:
        """Send alert via este transport.

        Returns:
            (success, error_message). error_message é None em caso de sucesso.
        """
        ...

    @property
    def is_configured(self) -> bool:
        """True se o channel tem config minima para poder tentar send.

        Por defeito False — override em cada subclass para validar config
        especifica (e.g., email precisa smtp_host + recipients).
        """
        return False
