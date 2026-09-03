"""
Structured Logging System
Provides JSON and text logging with rotation
"""

import logging
import logging.handlers
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "server_id"):
            log_data["server_id"] = record.server_id

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if hasattr(record, "user"):
            log_data["user"] = record.user

        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """
    Custom text formatter with colors (optional)
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",      # Reset
    }

    def __init__(self, colorize: bool = False):
        super().__init__()
        self.colorize = colorize

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as text"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        level = record.levelname
        if self.colorize and level in self.COLORS:
            level = f"{self.COLORS[level]}{level}{self.COLORS['RESET']}"

        message = record.getMessage()

        # Basic format
        log_line = f"[{timestamp}] {level:8s} [{record.name}] {message}"

        # Add location info for ERROR and above
        if record.levelno >= logging.ERROR:
            log_line += f" ({record.module}:{record.funcName}:{record.lineno})"

        # Add exception if present
        if record.exc_info:
            log_line += "\n" + self.formatException(record.exc_info)

        return log_line


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "text",  # "json" or "text"
    log_file: Optional[str] = None,
    log_file_max_mb: int = 10,
    log_file_backup_count: int = 5,
    console_enabled: bool = True,
    console_colorize: bool = True,
) -> None:
    """
    Configure logging for the application

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format ("json" or "text")
        log_file: Path to log file (optional)
        log_file_max_mb: Max log file size in MB before rotation
        log_file_backup_count: Number of backup log files to keep
        console_enabled: Enable console logging
        console_colorize: Colorize console output (text format only)
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Choose formatter
    if log_format == "json":
        formatter = JSONFormatter()
        console_colorize = False  # No colors in JSON
    else:
        formatter = TextFormatter(colorize=console_colorize)

    # Console handler
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter if log_format == "json" else TextFormatter(colorize=console_colorize))
        root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=log_file_max_mb * 1024 * 1024,
            backupCount=log_file_backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set specific log levels for noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    root_logger.info(f"Logging configured: level={log_level}, format={log_format}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# ==========================================
# Context Manager for Request Logging
# ==========================================
class LogContext:
    """
    Context manager for adding context to logs
    """

    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        """Add context to all log records"""
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        self.old_factory = old_factory
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original factory"""
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)


# ==========================================
# Performance Logging Decorator
# ==========================================
import time
import functools


def log_performance(logger: Optional[logging.Logger] = None):
    """
    Decorator to log function execution time

    Usage:
        @log_performance()
        def my_function():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = logging.getLogger(func.__module__)

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                logger.info(
                    f"Function {func.__name__} completed",
                    extra={"duration_ms": duration_ms, "function": func.__name__}
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Function {func.__name__} failed: {e}",
                    extra={"duration_ms": duration_ms, "function": func.__name__},
                    exc_info=True
                )
                raise

        return wrapper

    return decorator
