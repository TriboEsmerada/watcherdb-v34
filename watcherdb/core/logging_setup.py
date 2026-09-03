"""
Structured logging setup using structlog.

Call setup_logging() once at application startup.
"""
import os
import logging
import structlog


def setup_logging(log_level: str = None):
    level = log_level or os.getenv("LOG_LEVEL", "INFO")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level, logging.INFO),
    )
