"""
WatcherDB V3.3 Standard Edition — Alert Routing module.

Audit 2026-04-22 / S3-14: scaffold inicial de alert routing para email/Teams/
Slack. Deliberadamente minimal em scope — objectivo e unblocking PoC
competitivo (marketing-strategist finding) sem reescrever o alerting
engine completo.

Arquitectura:
    modules.alerts.base         — BaseChannel ABC + AlertPayload dataclass
    modules.alerts.dedup        — DeduplicationStore (TTL in-memory)
    modules.alerts.config_loader — le seccao alerts: de services/web_service/config.yaml
    modules.alerts.channels.*   — LogChannel + EmailChannel + TeamsChannel + SlackChannel
    modules.alerts.dispatcher   — AlertDispatcher (orquestra channels + persiste log)
    api.routers.alert_routing   — 3 endpoints admin-only (POST /send, /test/{ch}, GET /history)
"""
