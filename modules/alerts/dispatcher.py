"""
AlertDispatcher — orquestra envio a multiplos channels (S3-14 C4).

Responsabilidades:
  - Aplica dedup por alert_id + severity (janelas configuraveis)
  - Executa channels em paralelo via asyncio.gather
  - LogChannel e sempre incluido como fallback/safety-net
  - Persiste resultado em dbo.alert_dispatch_log (BD partilhada V1 Intel)
  - Nao crasha em failure de channel individual — isola erros
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Iterable

from modules.alerts.base import AlertPayload, BaseChannel
from modules.alerts.dedup import get_dedup


logger = logging.getLogger("watcherdb.alerts.dispatcher")


# Default windows — podem ser override via config (dedup_windows)
_DEFAULT_DEDUP_WINDOWS: dict[str, int] = {
    "critical": 300,    # 5 min
    "warning": 900,     # 15 min
    "info": 3600,       # 1 hora
}


class AlertDispatcher:
    """Dispatcher de alerts. Construido pelo app startup com channels configurados."""

    def __init__(
        self,
        channels: Iterable[BaseChannel],
        dedup_windows: dict[str, int] | None = None,
    ):
        self._channels: dict[str, BaseChannel] = {ch.name: ch for ch in channels}
        self._dedup_windows = dict(_DEFAULT_DEDUP_WINDOWS)
        if dedup_windows:
            self._dedup_windows.update(dedup_windows)

    @property
    def available_channels(self) -> list[str]:
        """Nomes dos channels registados (inclui nao-configurados)."""
        return list(self._channels.keys())

    @property
    def configured_channels(self) -> list[str]:
        """Nomes dos channels que tem config minima (is_configured True)."""
        return [name for name, ch in self._channels.items() if ch.is_configured]

    async def dispatch(
        self,
        alert: AlertPayload,
        channel_names: list[str],
    ) -> dict:
        """Envia alert para os channels pedidos. Returns summary dict."""
        dedup_window = self._dedup_windows.get(alert.severity, 900)
        dedup_key = f"{alert.alert_id}:{alert.severity}"

        if get_dedup().is_duplicate(dedup_key, dedup_window):
            logger.info(
                "[DEDUP] Alert suprimido: %s (severity=%s, window=%ds)",
                alert.alert_id, alert.severity, dedup_window,
            )
            return {
                "status": "deduplicated",
                "sent": [],
                "failed": [],
                "dedup_window_seconds": dedup_window,
            }

        # LogChannel sempre incluido (safety-net — append se nao no target)
        effective = list(dict.fromkeys([*channel_names, "log"]))

        tasks = {}
        for name in effective:
            ch = self._channels.get(name)
            if ch is None:
                continue  # unknown channel — ignora silenciosamente
            if not ch.is_configured:
                continue  # skip nao-configured (nao conta como failure)
            tasks[name] = ch.send(alert)

        if not tasks:
            # Pelo menos o log deveria estar sempre configured. Se nao esta,
            # e erro grave de inicializacao.
            logger.error("[DISPATCH] Nenhum channel configurado para %s", alert.alert_id)
            return {
                "status": "no_channels",
                "sent": [],
                "failed": effective,
                "error": "no configured channels",
            }

        names = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        sent: list[str] = []
        failed: list[str] = []
        errors: dict[str, str] = {}

        for name, result in zip(names, results):
            if isinstance(result, Exception):
                failed.append(name)
                errors[name] = f"{type(result).__name__}: {result}"
                logger.warning("Channel %s raised %s: %s", name, type(result).__name__, result)
            else:
                ok, err = result
                if ok:
                    sent.append(name)
                else:
                    failed.append(name)
                    if err:
                        errors[name] = err

        # Persistencia best-effort — nao aborta se falhar
        try:
            await self._persist_log(alert, channel_names, sent, failed, errors)
        except Exception as exc:
            logger.error("[DISPATCH] Falha a persistir log do dispatch %s: %s", alert.alert_id, exc)

        return {
            "status": "dispatched",
            "sent": sent,
            "failed": failed,
            "errors": errors,
        }

    @staticmethod
    async def _persist_log(
        alert: AlertPayload,
        target: list[str],
        sent: list[str],
        failed: list[str],
        errors: dict[str, str],
    ) -> None:
        """Persiste resultado em dbo.alert_dispatch_log via execute_on_intelligence.

        Wrapped em asyncio.to_thread porque o pool e sync. Erro ai nao deve
        crashar o dispatch — logado como warning.
        """
        sql = """
        INSERT INTO dbo.alert_dispatch_log (
            alert_id, alert_source, severity, title, body, server_id,
            channels_target, channels_sent, channels_failed, error_detail,
            triggered_by, sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
        """
        params = (
            alert.alert_id,
            alert.source,
            alert.severity,
            alert.title[:255],
            (alert.body or "")[:4000],
            alert.server_id,
            json.dumps(target),
            json.dumps(sent),
            json.dumps(failed),
            json.dumps(errors) if errors else None,
            alert.triggered_by,
        )

        from api.connection_pool import execute_on_intelligence
        await asyncio.to_thread(execute_on_intelligence, sql, params)
