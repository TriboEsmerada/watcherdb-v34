"""
Alert Routing HTTP API — 3 endpoints admin-only (S3-14 C5).

POST /api/v3/alerts/send         — manual dispatch de um alert custom
POST /api/v3/alerts/test/{ch}    — test dispatch para 1 channel (smoke)
GET  /api/v3/alerts/history      — ultimos N dispatches do log

Todos os endpoints requerem role admin via _require_admin dependency.
Global auth middleware (AuthEnforcementMiddleware P0-3) bloqueia
unauthenticated antes de chegar ao Depends.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from api.routers.auth_compat import _require_admin
from modules.alerts.base import AlertPayload
from modules.alerts.dispatcher import AlertDispatcher


router = APIRouter(
    prefix="/api/v3/alerts",
    tags=["alert-routing"],
    dependencies=[Depends(_require_admin)],  # router-level admin enforcement
)


# =============================================================================
# Request / Response models (Pydantic)
# =============================================================================

class AlertSendRequest(BaseModel):
    severity: str = Field(..., description="info | warning | critical")
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field("", max_length=4000)
    channels: list[str] = Field(default_factory=lambda: ["log"])
    alert_id: Optional[str] = Field(None, description="Chave de dedup — auto-gerada se ausente")
    server_id: Optional[str] = Field(None, max_length=255)
    source: str = Field("manual", description="'manual' | 'performance' | 'kpi' | 'test'")


class AlertSendResponse(BaseModel):
    status: str
    sent: list[str]
    failed: list[str]
    errors: dict[str, str] = Field(default_factory=dict)
    alert_id: str


class ChannelTestResponse(BaseModel):
    channel: str
    status: str
    success: bool
    error: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================

def _get_dispatcher(request: Request) -> AlertDispatcher:
    dispatcher = getattr(request.app.state, "alert_dispatcher", None)
    if dispatcher is None:
        raise HTTPException(
            status_code=503,
            detail="AlertDispatcher nao inicializado. Verifique config.yaml seccao alerts:",
        )
    return dispatcher


def _generate_alert_id(source: str, server_id: Optional[str]) -> str:
    """Gera alert_id default quando nao fornecido — dedup-friendly."""
    ts = int(time.time())
    sid = server_id or "nosrv"
    return f"{source}:{sid}:{ts}"


# =============================================================================
# POST /api/v3/alerts/send
# =============================================================================

@router.post("/send", response_model=AlertSendResponse)
async def send_alert(body: AlertSendRequest, request: Request) -> AlertSendResponse:
    """Dispatch manual de um alert. Admin-only."""
    dispatcher = _get_dispatcher(request)

    alert_id = body.alert_id or _generate_alert_id(body.source, body.server_id)

    try:
        payload = AlertPayload(
            alert_id=alert_id,
            source=body.source,
            severity=body.severity,
            title=body.title,
            body=body.body,
            server_id=body.server_id,
            triggered_by="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = await dispatcher.dispatch(payload, body.channels)

    return AlertSendResponse(
        status=result.get("status", "unknown"),
        sent=result.get("sent", []),
        failed=result.get("failed", []),
        errors=result.get("errors", {}),
        alert_id=alert_id,
    )


# =============================================================================
# POST /api/v3/alerts/test/{channel}
# =============================================================================

@router.post("/test/{channel}", response_model=ChannelTestResponse)
async def test_channel(channel: str, request: Request) -> ChannelTestResponse:
    """Smoke test dispatch para 1 channel. Admin-only."""
    dispatcher = _get_dispatcher(request)

    if channel not in dispatcher.available_channels:
        raise HTTPException(
            status_code=404,
            detail=f"Channel {channel!r} nao registado. Disponiveis: {dispatcher.available_channels}",
        )

    payload = AlertPayload(
        alert_id=f"test:{channel}:{int(time.time())}",
        source="test",
        severity="info",
        title=f"WatcherDB — Teste de canal: {channel}",
        body=(
            "Esta e uma mensagem de teste do WatcherDB V3.3 Standard Edition.\n"
            "Se esta mensagem apareceu no canal correcto, a configuracao esta OK."
        ),
        triggered_by="test",
    )

    result = await dispatcher.dispatch(payload, [channel])

    success = channel in result.get("sent", [])
    error = result.get("errors", {}).get(channel)

    return ChannelTestResponse(
        channel=channel,
        status=result.get("status", "unknown"),
        success=success,
        error=error,
    )


# =============================================================================
# GET /api/v3/alerts/history
# =============================================================================

@router.get("/history")
async def alert_history(limit: int = Query(50, ge=1, le=200)) -> dict:
    """Ultimas N entradas do alert_dispatch_log. Admin-only."""
    sql = """
    SELECT TOP (?)
        dispatch_id, alert_id, alert_source, severity, title, server_id,
        channels_target, channels_sent, channels_failed, error_detail,
        triggered_by, triggered_at, sent_at
    FROM dbo.alert_dispatch_log WITH (NOLOCK)
    ORDER BY triggered_at DESC
    """

    from api.connection_pool import execute_on_intelligence
    rows = await asyncio.to_thread(execute_on_intelligence, sql, (limit,))
    return {"rows": rows, "count": len(rows)}


# =============================================================================
# GET /api/v3/alerts/channels
# =============================================================================

@router.get("/channels")
async def list_channels(request: Request) -> dict:
    """Introspection — que channels estao disponiveis e quais configurados."""
    dispatcher = _get_dispatcher(request)
    return {
        "available": dispatcher.available_channels,
        "configured": dispatcher.configured_channels,
    }
