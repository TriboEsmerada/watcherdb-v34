"""
OpenTelemetry distributed tracing for WatcherDB.

Provides:
- Automatic FastAPI instrumentation (spans for all requests)
- Request ID middleware (X-Request-ID header)
- Trace context propagation
"""

import os
import uuid
import logging
from typing import Optional

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add X-Request-ID header to all requests and responses."""

    async def dispatch(self, request: Request, call_next):
        # Use incoming header or generate new
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def setup_telemetry(app: FastAPI, service_name: str = "watcherdb"):
    """
    Initialize OpenTelemetry tracing and request ID middleware.

    Reads configuration from environment:
    - OTEL_ENABLED: Enable/disable tracing (default: true)
    - OTEL_EXPORTER: Exporter type — "console" or "otlp" (default: console)
    - OTEL_ENDPOINT: OTLP endpoint if using otlp exporter
    - OTEL_SERVICE_NAME: Override service name
    """
    # Always add Request ID middleware
    app.add_middleware(RequestIDMiddleware)

    otel_enabled = os.getenv("OTEL_ENABLED", "true").lower() in ("true", "1", "yes")
    if not otel_enabled:
        logger.info("OpenTelemetry disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        service = os.getenv("OTEL_SERVICE_NAME", service_name)
        resource = Resource.create({"service.name": service})
        provider = TracerProvider(resource=resource)

        exporter_type = os.getenv("OTEL_EXPORTER", "console").lower()

        if exporter_type == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                endpoint = os.getenv("OTEL_ENDPOINT", "http://localhost:4317")
                exporter = OTLPSpanExporter(endpoint=endpoint)
                logger.info(f"OpenTelemetry OTLP exporter → {endpoint}")
            except ImportError:
                logger.warning("OTLP exporter not installed, falling back to console")
                exporter = ConsoleSpanExporter()
        else:
            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        logger.info(f"OpenTelemetry initialized (service={service}, exporter={exporter_type})")

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed ({e}). Tracing disabled.")
    except Exception as e:
        logger.error(f"OpenTelemetry initialization failed: {e}")
