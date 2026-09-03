# ============================================================================
# WatcherDB DASHBOARD FIXES - CORRECOES PARA EXIBICAO
# ============================================================================
# Arquivo: modules/monitoring/dashboard_fixes.py
# ============================================================================
# CORRIGIDO: Logica UNLIMITED e thresholds 85%/95% baseado em maxsize_utilization_percent
# ============================================================================
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from decimal import Decimal
from collections import defaultdict
logger = logging.getLogger(__name__)
@dataclass
class FileGroupDisplay:
    database_name: str
    filegroup_name: str
    filegroup_type: str
    total_size_gb: float
    used_size_gb: float
    free_size_gb: float
    max_size_gb: float
    usage_percent: float
    maxsize_utilization_percent: float
    is_unlimited: bool
    is_overflow: bool
    days_until_full: int
    growth_rate_per_month: float
    volume: str
    disk_available_gb: float
    alert_level: str
    risk_factors: List[str]
    file_count: int
    logical_names: List[str]
print("Script loaded")
