"""
Domain models, enums, and dataclasses for WatcherDB
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class ServiceType(str, Enum):
    SQL_SERVER = "SQL_SERVER"
    SSAS = "SSAS"
    UNKNOWN = "UNKNOWN"


class CheckType(str, Enum):
    CONNECTION = "connection"
    SPACE = "space"
    BACKUP = "backup"
    PERFORMANCE = "performance"
    FULL_ANALYSIS = "full"


@dataclass
class InventoryServer:
    server_name: str
    instance_name: str
    environment: str
    database_engine: str
    location: str
    description: str
    status: str = "UNKNOWN"
    last_updated: Optional[datetime] = None
    response_time_ms: int = 0
    alerts_count: int = 0
    health_score: float = 0.0
    # Additional TAP-specific fields
    ag_name: str = ""
    criticality: str = ""
    backup_strategy: str = ""
    listeners: str = ""
    business_area: str = ""
