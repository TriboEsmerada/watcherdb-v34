"""
Alert Management System
Handles alert creation, throttling, and distribution to notification channels
"""

import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from watcherdb.models.alerts import Alert, AlertLevel, AlertChannel
from watcherdb.services.notification import NotificationService

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Centralized alert management system
    Features:
    - Alert throttling (prevent duplicate alerts)
    - Multi-channel notification
    - Alert history tracking
    - Alert grouping
    - Escalation support
    """

    def __init__(self, config_path: str = "config/alerts.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.notification_service = NotificationService()
        self.alert_history: Dict[str, datetime] = {}  # alert_hash -> last_sent_time
        self.active_alerts: List[Alert] = []

        logger.info("AlertManager initialized")

    def _load_config(self) -> Dict[str, Any]:
        """Load alert configuration from JSON"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"Alert config not found: {self.config_path}, using defaults")
                return {"alert_rules": {}, "escalation_rules": {"enabled": False}}
        except Exception as e:
            logger.error(f"Error loading alert config: {e}")
            return {"alert_rules": {}, "escalation_rules": {"enabled": False}}

    def create_alert(
        self,
        title: str,
        message: str,
        level: AlertLevel,
        source: str,
        server_name: Optional[str] = None,
        database_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        channels: Optional[List[AlertChannel]] = None
    ) -> Optional[Alert]:
        """
        Create and send alert

        Args:
            title: Alert title
            message: Alert message
            level: Alert severity (INFO, WARNING, CRITICAL)
            source: Alert source/type (e.g., "disk_space", "backup_failure")
            server_name: SQL Server name
            database_name: Database name
            metric_value: Current metric value
            threshold_value: Threshold that was exceeded
            metadata: Additional context
            channels: Notification channels (if None, use config defaults)

        Returns:
            Alert object if sent, None if throttled
        """
        try:
            # Get alert rule config
            rule_config = self.config.get("alert_rules", {}).get(source, {})

            if not rule_config.get("enabled", True):
                logger.debug(f"Alert {source} is disabled")
                return None

            # Determine channels
            if channels is None:
                channel_names = rule_config.get("channels", ["email"])
                channels = [AlertChannel(ch) for ch in channel_names if ch in AlertChannel.__members__.values()]

            # Create alert object
            alert = Alert(
                id=self._generate_alert_id(title, source, server_name, database_name),
                title=title,
                message=message,
                level=level,
                source=source,
                server_name=server_name,
                database_name=database_name,
                metric_value=metric_value,
                threshold_value=threshold_value,
                metadata=metadata or {},
                channels=channels,
                timestamp=datetime.now()
            )

            # Check throttling
            if self._is_throttled(alert, rule_config.get("throttle_minutes", 60)):
                logger.info(f"Alert throttled: {alert.id}")
                return None

            # Send alert
            self._send_alert(alert)

            # Update history
            alert_hash = self._get_alert_hash(alert)
            self.alert_history[alert_hash] = datetime.now()
            self.active_alerts.append(alert)

            # Keep only last 1000 alerts in memory
            if len(self.active_alerts) > 1000:
                self.active_alerts = self.active_alerts[-1000:]

            logger.info(f"Alert created and sent: {alert.id} - {alert.title}")
            return alert

        except Exception as e:
            logger.error(f"Error creating alert: {e}", exc_info=True)
            return None

    def _send_alert(self, alert: Alert) -> None:
        """Send alert to configured channels"""
        for channel in alert.channels:
            try:
                success = False
                if channel == AlertChannel.EMAIL:
                    success = self.notification_service.send_email(alert)
                elif channel == AlertChannel.TEAMS:
                    success = self.notification_service.send_teams(alert)
                elif channel == AlertChannel.SLACK:
                    success = self.notification_service.send_slack(alert)
                elif channel == AlertChannel.WEBHOOK:
                    success = self.notification_service.send_webhook(alert)

                if success:
                    logger.info(f"Alert sent via {channel.value}: {alert.id}")
                else:
                    logger.warning(f"Failed to send alert via {channel.value}: {alert.id}")

            except Exception as e:
                logger.error(f"Error sending alert via {channel.value}: {e}")

    def _is_throttled(self, alert: Alert, throttle_minutes: int) -> bool:
        """Check if alert should be throttled"""
        alert_hash = self._get_alert_hash(alert)

        if alert_hash in self.alert_history:
            last_sent = self.alert_history[alert_hash]
            elapsed = datetime.now() - last_sent

            if elapsed < timedelta(minutes=throttle_minutes):
                return True

        return False

    def _get_alert_hash(self, alert: Alert) -> str:
        """Generate unique hash for alert (for throttling)"""
        hash_input = f"{alert.source}:{alert.server_name}:{alert.database_name}:{alert.title}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def _generate_alert_id(self, title: str, source: str, server: Optional[str], database: Optional[str]) -> str:
        """Generate unique alert ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        parts = [source, server or "global", database or "all", timestamp]
        return "_".join(parts)

    # ==========================================
    # Alert Query Methods
    # ==========================================
    def get_active_alerts(self, level: Optional[AlertLevel] = None) -> List[Alert]:
        """Get active alerts, optionally filtered by level"""
        if level:
            return [a for a in self.active_alerts if a.level == level and not a.resolved]
        return [a for a in self.active_alerts if not a.resolved]

    def get_alert_by_id(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID"""
        for alert in self.active_alerts:
            if alert.id == alert_id:
                return alert
        return None

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark alert as acknowledged"""
        alert = self.get_alert_by_id(alert_id)
        if alert:
            alert.acknowledged = True
            logger.info(f"Alert acknowledged: {alert_id}")
            return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark alert as resolved"""
        alert = self.get_alert_by_id(alert_id)
        if alert:
            alert.resolved = True
            logger.info(f"Alert resolved: {alert_id}")
            return True
        return False

    # ==========================================
    # Convenience Methods for Common Alerts
    # ==========================================
    def alert_disk_space_critical(self, server: str, database: str, filegroup: str,
                                   usage_percent: float, free_space_mb: float,
                                   forecast_days: Optional[int] = None) -> Optional[Alert]:
        """Create critical disk space alert"""
        message = f"CRITICAL: Disk space critically low on {server}\n"
        message += f"Database: {database}\n"
        message += f"Filegroup: {filegroup}\n"
        message += f"Current Usage: {usage_percent:.1f}%\n"
        message += f"Free Space: {free_space_mb:.1f} MB"

        if forecast_days:
            message += f"\nForecast: Full in {forecast_days} days"

        return self.create_alert(
            title=f"Critical Disk Space: {server}/{database}",
            message=message,
            level=AlertLevel.CRITICAL,
            source="disk_space",
            server_name=server,
            database_name=database,
            metric_value=usage_percent,
            threshold_value=90.0,
            metadata={
                "filegroup": filegroup,
                "free_space_mb": free_space_mb,
                "forecast_days": forecast_days
            }
        )

    def alert_backup_failure(self, server: str, database: str,
                             last_backup_time: Optional[str],
                             backup_type: str, age_hours: float) -> Optional[Alert]:
        """Create backup failure alert"""
        message = f"ALERT: Backup failure or missing backup\n"
        message += f"Server: {server}\n"
        message += f"Database: {database}\n"
        message += f"Backup Type: {backup_type}\n"
        message += f"Last Backup: {last_backup_time or 'Never'}\n"
        message += f"Age: {age_hours:.1f} hours"

        return self.create_alert(
            title=f"Backup Failure: {server}/{database}",
            message=message,
            level=AlertLevel.CRITICAL,
            source="backup_failure",
            server_name=server,
            database_name=database,
            metric_value=age_hours,
            threshold_value=24.0,
            metadata={
                "backup_type": backup_type,
                "last_backup_time": last_backup_time
            }
        )

    def alert_alwayson_failover(self, ag_name: str, primary_replica: str,
                                 failover_time: str, reason: Optional[str] = None) -> Optional[Alert]:
        """Create Always On failover alert"""
        message = f"WARNING: Always On Availability Group failover detected\n"
        message += f"AG Name: {ag_name}\n"
        message += f"New Primary: {primary_replica}\n"
        message += f"Failover Time: {failover_time}"

        if reason:
            message += f"\nReason: {reason}"

        return self.create_alert(
            title=f"AlwaysOn Failover: {ag_name}",
            message=message,
            level=AlertLevel.WARNING,
            source="alwayson_failover",
            server_name=primary_replica,
            metadata={
                "ag_name": ag_name,
                "failover_time": failover_time,
                "reason": reason
            }
        )

    def alert_memory_pressure(self, server: str, memory_percent: float,
                               available_mb: float, recommendation: str) -> Optional[Alert]:
        """Create memory pressure alert"""
        message = f"WARNING: Memory pressure detected\n"
        message += f"Server: {server}\n"
        message += f"Memory Usage: {memory_percent:.1f}%\n"
        message += f"Available Memory: {available_mb:.1f} MB\n"
        message += f"Recommendation: {recommendation}"

        level = AlertLevel.CRITICAL if memory_percent >= 90 else AlertLevel.WARNING

        return self.create_alert(
            title=f"Memory Pressure: {server}",
            message=message,
            level=level,
            source="memory_pressure",
            server_name=server,
            metric_value=memory_percent,
            threshold_value=80.0,
            metadata={
                "available_mb": available_mb,
                "recommendation": recommendation
            }
        )

    def alert_cpu_pressure(self, server: str, cpu_percent: float,
                           duration_minutes: int) -> Optional[Alert]:
        """Create CPU pressure alert"""
        message = f"WARNING: High CPU usage detected\n"
        message += f"Server: {server}\n"
        message += f"CPU Usage: {cpu_percent:.1f}%\n"
        message += f"Duration: {duration_minutes} minutes"

        level = AlertLevel.CRITICAL if cpu_percent >= 90 else AlertLevel.WARNING

        return self.create_alert(
            title=f"CPU Pressure: {server}",
            message=message,
            level=level,
            source="cpu_pressure",
            server_name=server,
            metric_value=cpu_percent,
            threshold_value=80.0,
            metadata={
                "duration_minutes": duration_minutes
            }
        )

    def alert_blocking_queries(self, server: str, blocked_count: int,
                                max_duration_seconds: int) -> Optional[Alert]:
        """Create blocking queries alert"""
        message = f"ALERT: Blocking queries detected\n"
        message += f"Server: {server}\n"
        message += f"Blocked Processes: {blocked_count}\n"
        message += f"Max Block Duration: {max_duration_seconds} seconds"

        return self.create_alert(
            title=f"Blocking Queries: {server}",
            message=message,
            level=AlertLevel.WARNING,
            source="blocking_queries",
            server_name=server,
            metric_value=float(blocked_count),
            threshold_value=5.0,
            metadata={
                "max_duration_seconds": max_duration_seconds
            }
        )

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics"""
        total_alerts = len(self.active_alerts)
        critical = len([a for a in self.active_alerts if a.level == AlertLevel.CRITICAL])
        warning = len([a for a in self.active_alerts if a.level == AlertLevel.WARNING])
        info = len([a for a in self.active_alerts if a.level == AlertLevel.INFO])
        resolved = len([a for a in self.active_alerts if a.resolved])
        acknowledged = len([a for a in self.active_alerts if a.acknowledged])

        return {
            "total_alerts": total_alerts,
            "critical": critical,
            "warning": warning,
            "info": info,
            "resolved": resolved,
            "acknowledged": acknowledged,
            "active": total_alerts - resolved,
            "throttled_count": len(self.alert_history)
        }
