"""
Error handling helpers — prevent internal details from leaking to clients.

Usage:
    from api.error_helpers import safe_http_error

    except Exception as e:
        raise safe_http_error(500, e, "loading backup analysis")
"""

import uuid
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def safe_http_error(
    status_code: int,
    exc: Exception,
    context: str = "",
) -> HTTPException:
    """
    Create an HTTPException that logs the real error but returns a generic message.

    Args:
        status_code: HTTP status code (typically 500)
        exc: The caught exception
        context: Human-readable context (e.g. "loading backup analysis for server X")

    Returns:
        HTTPException with a safe, non-leaking detail message
    """
    error_id = uuid.uuid4().hex[:8]
    log_msg = f"[{error_id}] {context}: {exc}" if context else f"[{error_id}] {exc}"
    logger.error(log_msg, exc_info=True)
    return HTTPException(
        status_code=status_code,
        detail=f"Internal error (ref: {error_id}). Check server logs for details.",
    )
