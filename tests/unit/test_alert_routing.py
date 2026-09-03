"""
Smoke + unit tests para modules.alerts (S3-14 C8).

Foco:
- AlertPayload validation (severity/source enums)
- DeduplicationStore TTL behaviour
- LogChannel (sem mock — teste real de logger)
- EmailChannel / TeamsChannel / SlackChannel isConfigured + mocked send
- AlertDispatcher: dedup, fan-out paralelo, isolation de failures, log persist
- Router smoke: endpoints registados + auth enforcement
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# AlertPayload validation
# =============================================================================

class TestAlertPayload:
    def test_valid_payload(self):
        from modules.alerts.base import AlertPayload
        p = AlertPayload(
            alert_id="kpi:cpu:SRV01:20260422T1430",
            source="kpi",
            severity="warning",
            title="CPU alto",
            body="CPU a 85%",
            server_id="SRV01",
        )
        assert p.severity == "warning"
        assert p.triggered_by == "manual"  # default

    @pytest.mark.parametrize("bad_sev", ["error", "high", "", "CRITICAL"])
    def test_invalid_severity_rejected(self, bad_sev):
        from modules.alerts.base import AlertPayload
        with pytest.raises(ValueError, match="severity"):
            AlertPayload(alert_id="x", source="manual", severity=bad_sev, title="t", body="b")

    def test_invalid_source_rejected(self):
        from modules.alerts.base import AlertPayload
        with pytest.raises(ValueError, match="source"):
            AlertPayload(alert_id="x", source="random", severity="info", title="t", body="b")

    def test_empty_title_rejected(self):
        from modules.alerts.base import AlertPayload
        with pytest.raises(ValueError, match="obrigator"):
            AlertPayload(alert_id="x", source="manual", severity="info", title="", body="b")


# =============================================================================
# DeduplicationStore
# =============================================================================

class TestDeduplicationStore:
    def setup_method(self):
        from modules.alerts.dedup import get_dedup
        get_dedup().reset()

    def test_first_call_not_duplicate(self):
        from modules.alerts.dedup import get_dedup
        assert get_dedup().is_duplicate("alert-1", 60) is False

    def test_second_call_within_window_is_duplicate(self):
        from modules.alerts.dedup import get_dedup
        d = get_dedup()
        d.is_duplicate("alert-1", 60)  # register
        assert d.is_duplicate("alert-1", 60) is True

    def test_different_ids_not_duplicates(self):
        from modules.alerts.dedup import get_dedup
        d = get_dedup()
        d.is_duplicate("alert-1", 60)
        assert d.is_duplicate("alert-2", 60) is False

    def test_clear_expired(self):
        from modules.alerts.dedup import get_dedup
        d = get_dedup()
        d.is_duplicate("alert-1", 60)
        assert d.size() == 1
        d.clear_expired(max_age_seconds=0)  # tudo expirado
        assert d.size() == 0


# =============================================================================
# LogChannel — real test (sem mock)
# =============================================================================

class TestLogChannel:
    @pytest.mark.asyncio
    async def test_log_channel_always_configured(self):
        from modules.alerts.channels.log_channel import LogChannel
        ch = LogChannel()
        assert ch.is_configured is True

    @pytest.mark.asyncio
    async def test_log_channel_send_returns_success(self, caplog):
        import logging
        from modules.alerts.base import AlertPayload
        from modules.alerts.channels.log_channel import LogChannel

        ch = LogChannel()
        payload = AlertPayload(
            alert_id="test:log", source="manual", severity="warning",
            title="Test", body="body",
        )
        with caplog.at_level(logging.WARNING, logger="watcherdb.alerts"):
            ok, err = await ch.send(payload)
        assert ok is True
        assert err is None
        assert any("Test" in rec.message for rec in caplog.records)


# =============================================================================
# EmailChannel / TeamsChannel / SlackChannel — not-configured + mocked
# =============================================================================

class TestEmailChannel:
    @pytest.mark.asyncio
    async def test_not_configured_returns_false(self):
        from modules.alerts.channels.email_channel import EmailChannel
        ch = EmailChannel({})  # empty cfg
        assert ch.is_configured is False
        from modules.alerts.base import AlertPayload
        payload = AlertPayload(
            alert_id="t", source="manual", severity="info",
            title="t", body="b",
        )
        ok, err = await ch.send(payload)
        assert ok is False
        assert "not configured" in err

    @pytest.mark.asyncio
    async def test_configured_ok(self):
        from modules.alerts.channels.email_channel import EmailChannel
        cfg = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "x",
            "smtp_password": "y",
            "from_address": "from@example.com",
            "recipients": ["to@example.com"],
        }
        ch = EmailChannel(cfg)
        assert ch.is_configured is True


class TestTeamsChannel:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        from modules.alerts.channels.teams_channel import TeamsChannel
        ch = TeamsChannel({})
        assert ch.is_configured is False

    @pytest.mark.asyncio
    async def test_configured_requires_https(self):
        from modules.alerts.channels.teams_channel import TeamsChannel
        assert TeamsChannel({"webhook_url": "http://insecure.example"}).is_configured is False
        assert TeamsChannel({"webhook_url": "https://outlook.office.com/webhook/..."}).is_configured is True


class TestSlackChannel:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        from modules.alerts.channels.slack_channel import SlackChannel
        assert SlackChannel({}).is_configured is False

    @pytest.mark.asyncio
    async def test_configured_requires_slack_domain(self):
        from modules.alerts.channels.slack_channel import SlackChannel
        assert SlackChannel({"webhook_url": "https://evil.example.com/webhook"}).is_configured is False
        assert SlackChannel({"webhook_url": "https://hooks.slack.com/services/T00/B00/xxx"}).is_configured is True


# =============================================================================
# AlertDispatcher
# =============================================================================

class TestAlertDispatcher:

    def setup_method(self):
        from modules.alerts.dedup import get_dedup
        get_dedup().reset()

    @pytest.mark.asyncio
    async def test_dispatch_with_log_channel_only(self):
        from modules.alerts.base import AlertPayload
        from modules.alerts.channels.log_channel import LogChannel
        from modules.alerts.dispatcher import AlertDispatcher

        disp = AlertDispatcher([LogChannel()])
        payload = AlertPayload(
            alert_id="test:disp:1", source="manual", severity="info",
            title="T", body="B",
        )
        # Mock persistencia em BD (nao queremos ligar ao SQL em tests)
        with patch("modules.alerts.dispatcher.AlertDispatcher._persist_log", new=AsyncMock()):
            result = await disp.dispatch(payload, ["log"])

        assert result["status"] == "dispatched"
        assert "log" in result["sent"]
        assert result["failed"] == []

    @pytest.mark.asyncio
    async def test_dedup_suppresses_second_call(self):
        from modules.alerts.base import AlertPayload
        from modules.alerts.channels.log_channel import LogChannel
        from modules.alerts.dispatcher import AlertDispatcher

        disp = AlertDispatcher([LogChannel()])
        payload = AlertPayload(
            alert_id="test:dedup:same", source="manual", severity="info",
            title="T", body="B",
        )
        with patch("modules.alerts.dispatcher.AlertDispatcher._persist_log", new=AsyncMock()):
            result1 = await disp.dispatch(payload, ["log"])
            result2 = await disp.dispatch(payload, ["log"])

        assert result1["status"] == "dispatched"
        assert result2["status"] == "deduplicated"

    @pytest.mark.asyncio
    async def test_channel_failure_does_not_crash_dispatch(self):
        from modules.alerts.base import AlertPayload, BaseChannel
        from modules.alerts.channels.log_channel import LogChannel
        from modules.alerts.dispatcher import AlertDispatcher

        class ExplodingChannel(BaseChannel):
            name = "exploding"
            @property
            def is_configured(self):
                return True
            async def send(self, alert):
                raise RuntimeError("boom")

        disp = AlertDispatcher([LogChannel(), ExplodingChannel()])
        payload = AlertPayload(
            alert_id="test:exp", source="manual", severity="warning",
            title="T", body="B",
        )
        with patch("modules.alerts.dispatcher.AlertDispatcher._persist_log", new=AsyncMock()):
            result = await disp.dispatch(payload, ["exploding", "log"])

        assert "log" in result["sent"]
        assert "exploding" in result["failed"]
        assert "RuntimeError" in result["errors"]["exploding"]

    @pytest.mark.asyncio
    async def test_unconfigured_channel_skipped_silently(self):
        from modules.alerts.base import AlertPayload
        from modules.alerts.channels.email_channel import EmailChannel
        from modules.alerts.channels.log_channel import LogChannel
        from modules.alerts.dispatcher import AlertDispatcher

        disp = AlertDispatcher([LogChannel(), EmailChannel({})])  # email nao configurado
        payload = AlertPayload(
            alert_id="test:skipcfg", source="manual", severity="info",
            title="T", body="B",
        )
        with patch("modules.alerts.dispatcher.AlertDispatcher._persist_log", new=AsyncMock()):
            result = await disp.dispatch(payload, ["email", "log"])

        assert "log" in result["sent"]
        assert "email" not in result["sent"]
        assert "email" not in result["failed"]  # skipped, nao failed


# =============================================================================
# Router smoke + auth enforcement
# =============================================================================

class TestAlertRoutingAPI:
    PREFIX = "/api/v3/alerts"

    @pytest.fixture(scope="class")
    def client(self):
        try:
            import watcherdb_main
        except Exception as e:
            pytest.skip(f"watcherdb_main nao carregavel: {e}")
        return TestClient(watcherdb_main.app, raise_server_exceptions=False)

    def test_send_endpoint_requires_auth(self, client):
        resp = client.post(f"{self.PREFIX}/send", json={
            "severity": "info", "title": "t", "body": "b",
        })
        assert resp.status_code == 401

    def test_test_channel_requires_auth(self, client):
        resp = client.post(f"{self.PREFIX}/test/log")
        assert resp.status_code == 401

    def test_history_requires_auth(self, client):
        resp = client.get(f"{self.PREFIX}/history")
        assert resp.status_code == 401

    def test_channels_requires_auth(self, client):
        resp = client.get(f"{self.PREFIX}/channels")
        assert resp.status_code == 401

    def test_router_registered(self):
        from api.routers.alert_routing import router
        paths = {r.path for r in router.routes}
        assert any("/send" in p for p in paths)
        assert any("/test/" in p for p in paths)
        assert any("/history" in p for p in paths)
        assert any("/channels" in p for p in paths)
