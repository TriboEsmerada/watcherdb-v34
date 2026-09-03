"""
Retry decorators for database operations.

Background — why a custom predicate instead of retry_if_exception_type:
-----------------------------------------------------------------------
``pyodbc.Error`` is the BASE class of every pyodbc exception, including
permanent failures like "Invalid object name" (208), "Login failed" (18456),
"Cannot open database" (4060), syntax errors, permission denied, etc.

Using ``retry_if_exception_type(pyodbc.Error)`` makes tenacity retry every
single SQL error 3 times with 1+2+4s exponential backoff, wasting ~7 seconds
per request when the error is in fact permanent and would never succeed on
retry. In a parallel dashboard fan-out (e.g. /api/intelligence-kpis/dashboard
hitting 200+ instances) this multiplies into minutes of waste.

The fix is a custom predicate ``_is_transient_db_error`` that inspects the
SQLSTATE and the textual message to decide if the error is genuinely
transient (worth retrying) or permanent (give up immediately).

Usage:
    from watcherdb.core.retry import retry_db_operation

    @retry_db_operation
    def get_data():
        ...
"""
import logging
import pyodbc
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Predicate: is this DB error worth retrying?
# ----------------------------------------------------------------------------

# SQLSTATE classes that indicate TRANSIENT failures (worth retrying):
#   08xxx — Connection exception (network drop, timeout, server gone)
#   HYTxx — CLI-specific timeouts (HYT00 = timeout expired, HYT01 = connection timeout)
#   40001 — Serialization failure (deadlock victim)
#   40P01 — Deadlock detected
_TRANSIENT_SQLSTATE_PREFIXES = ('08', 'HYT')
_TRANSIENT_SQLSTATE_EXACT = {'40001', '40P01'}

# SQL Server native error numbers that indicate TRANSIENT failures:
#   1205 — Deadlock victim
#   1222 — Lock request time out
#   -2   — Client-side query timeout
#   10054 — Connection reset by peer
#   10060 — Network timeout
#   10061 — Connection refused (service down briefly)
#   258  — Wait operation timed out
#   233  — Connection initialisation failure
#   64   — Specified network name no longer available
#   121  — Semaphore timeout
#   2    — Cannot find server (DNS hiccup)
_TRANSIENT_NATIVE_ERRORS = {
    1205, 1222, -2,
    10054, 10060, 10061, 258, 233, 64, 121, 2,
}

# SQL Server native error numbers that are PERMANENT (do NOT retry, never):
#   208   — Invalid object name (table/view does not exist)
#   207   — Invalid column name
#   2812  — Could not find stored procedure
#   18456 — Login failed for user
#   4060  — Cannot open database (login lacks access)
#   229   — Permission denied on object
#   262   — Permission denied on database
#   297   — User does not have permission to perform this action
#   102   — Incorrect syntax
#   105   — Unclosed quotation mark
#   8180  — Statement(s) could not be prepared (usually paired with 208/207)
#   15151 — Cannot find object (varies)
_PERMANENT_NATIVE_ERRORS = {
    208, 207, 2812,
    18456, 4060, 229, 262, 297,
    102, 105, 8180, 15151,
}


def _extract_pyodbc_error_info(exc: BaseException) -> tuple:
    """Extract (sqlstate, native_error, message) from a pyodbc exception.

    pyodbc exceptions are typically constructed as
        pyodbc.Error('SQLSTATE', '[SQLSTATE] [Driver][Server] message (native)')
    so exc.args is usually a 2-tuple. Be defensive: if the structure differs,
    fall back to inspecting str(exc).
    """
    sqlstate = ''
    native = None
    message = str(exc)
    try:
        if hasattr(exc, 'args') and exc.args and len(exc.args) >= 1:
            sqlstate = str(exc.args[0]) if exc.args[0] else ''
            if len(exc.args) >= 2 and exc.args[1]:
                message = str(exc.args[1])
    except Exception:
        pass
    # Try to pull native error number from the message tail "(208)" / "(18456)"
    import re as _re
    m = _re.search(r'\((-?\d+)\)\s*$', message)
    if m:
        try:
            native = int(m.group(1))
        except ValueError:
            native = None
    return sqlstate, native, message


def _is_transient_db_error(exc: BaseException) -> bool:
    """Decide whether a database exception is worth retrying.

    Returns True (retry) for genuinely transient failures: network drops,
    deadlock victims, brief timeouts. Returns False (give up immediately)
    for permanent failures: missing objects, login failed, permission denied,
    syntax errors. Anything we can't classify is treated as PERMANENT
    (conservative — better to fail fast than waste 7s).
    """
    # Always retry these stdlib network errors
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    # OSError: only retry the network-related subset (ETIMEDOUT, ECONNRESET, etc).
    # We accept all OSError here because the caller (DB connect) only raises
    # OSError when it's actually a socket problem.
    if isinstance(exc, OSError) and not isinstance(exc, pyodbc.Error):
        return True

    if not isinstance(exc, pyodbc.Error):
        return False

    sqlstate, native, message = _extract_pyodbc_error_info(exc)

    # Permanent native errors trump everything — never retry
    if native in _PERMANENT_NATIVE_ERRORS:
        return False
    # Transient native errors — retry
    if native in _TRANSIENT_NATIVE_ERRORS:
        return True
    # SQLSTATE-based classification
    if sqlstate in _TRANSIENT_SQLSTATE_EXACT:
        return True
    if any(sqlstate.startswith(p) for p in _TRANSIENT_SQLSTATE_PREFIXES):
        return True

    # Heuristic fallback: look for known transient strings in the message
    msg_lower = message.lower()
    transient_markers = (
        'timeout expired',
        'connection is busy',
        'connection was reset',
        'transport-level error',
        'communication link failure',
        'network-related or instance-specific',
        'tcp provider',
    )
    if any(marker in msg_lower for marker in transient_markers):
        return True

    # Default: do NOT retry — better to fail fast than waste 7s on a
    # permanent error like "Invalid object name".
    return False


# ----------------------------------------------------------------------------
# Decorators
# ----------------------------------------------------------------------------

# For database connection operations — retry on transient DB errors only
retry_db_operation = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_transient_db_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# For external API calls (LLM, SMTP, etc.)
retry_external_call = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
