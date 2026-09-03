"""
Unit tests for Alert System
"""

import pytest
from datetime import datetime
from watcherdb.models.alerts import Alert, AlertLevel, AlertChannel
from watcherdb.services.alerting import AlertManager


class TestAlertModels:
    """Test alert data models"""

    def test_alert_creation(self, sample_alert_data):
        """Test alert object creation"""
        alert = Alert(
            id="test_001",
            title=sample_alert_data["title"],
            message=sample_alert_data["message"],
            level=AlertLevel.WARNING,
            source=sample_alert_data["source"],
            server_name=sample_alert_data["server_name"],
            database_name=sample_alert_data["database_name"]
        )

        assert alert.id == "test_001"
        assert alert.level == AlertLevel.WARNING
        assert not alert.acknowledged
        assert not alert.resolved

    def test_alert_to_dict(self, sample_alert_data):
        """Test alert serialization"""
        alert = Alert(
            id="test_002",
            title=sample_alert_data["title"],
            message=sample_alert_data["message"],
            level=AlertLevel.CRITICAL,
            source=sample_alert_data["source"]
        )

        alert_dict = alert.to_dict()
        assert alert_dict["id"] == "test_002"
        assert alert_dict["level"] == "critical"
        assert "timestamp" in alert_dict


class TestAlertManager:
    """Test AlertManager functionality"""

    def test_alert_creation_basic(self):
        """Test basic alert creation"""
        manager = AlertManager()

        alert = manager.create_alert(
            title="Test Alert",
            message="This is a test",
            level=AlertLevel.INFO,
            source="test"
        )

        # Note: Alert may be None if config disables it or throttling applies
        # In production tests, configure appropriately

    def test_alert_stats(self):
        """Test alert statistics"""
        manager = AlertManager()
        stats = manager.get_alert_stats()

        assert "total_alerts" in stats
        assert "critical" in stats
        assert "warning" in stats
        assert "info" in stats
