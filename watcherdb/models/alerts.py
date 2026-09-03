"""
Alert models for WatcherDB
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class AlertLevel(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    """Alert notification channels"""
    EMAIL = "email"
    TEAMS = "teams"
    SLACK = "slack"
    WEBHOOK = "webhook"


@dataclass
class Alert:
    """Alert data model"""
    id: str
    title: str
    message: str
    level: AlertLevel
    source: str  # e.g., "disk_space", "backup_failure"
    server_name: Optional[str] = None
    database_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    channels: List[AlertChannel] = field(default_factory=list)
    acknowledged: bool = False
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "source": self.source,
            "server_name": self.server_name,
            "database_name": self.database_name,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "channels": [ch.value for ch in self.channels],
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
        }


@dataclass
class AlertRule:
    """Alert rule configuration"""
    name: str
    enabled: bool
    level: AlertLevel
    threshold: float
    channels: List[AlertChannel]
    throttle_minutes: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)

    def should_alert(self, value: float) -> bool:
        """Check if value exceeds threshold"""
        return self.enabled and value >= self.threshold
