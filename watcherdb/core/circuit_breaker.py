"""
Circuit breaker for database and external service connections.

Prevents cascading failures by stopping calls to failing services.
States: CLOSED (normal) -> OPEN (failing, fast-fail) -> HALF-OPEN (testing recovery)
"""
import logging
import pybreaker

logger = logging.getLogger(__name__)


class _DBCircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Log circuit breaker state transitions."""

    def state_change(self, cb, old_state, new_state):
        logger.warning(
            f"Circuit breaker '{cb.name}' state change: {old_state.name} -> {new_state.name}"
        )

    def failure(self, cb, exc):
        logger.warning(f"Circuit breaker '{cb.name}' recorded failure: {exc}")

    def success(self, cb):
        logger.debug(f"Circuit breaker '{cb.name}' recorded success")


# Circuit breaker for SQL Server monitored connections
sql_server_breaker = pybreaker.CircuitBreaker(
    fail_max=5,              # Open after 5 consecutive failures
    reset_timeout=30,        # Try again after 30 seconds
    name="sql_server",
    listeners=[_DBCircuitBreakerListener()],
    exclude=[KeyError, ValueError],  # Don't count programming errors
)

# Circuit breaker for Intelligence DB
# Higher tolerance: auth depends on this — 10 failures before opening, 15s recovery
intelligence_breaker = pybreaker.CircuitBreaker(
    fail_max=10,
    reset_timeout=15,
    name="intelligence_db",
    listeners=[_DBCircuitBreakerListener()],
    exclude=[KeyError, ValueError],
)

# Circuit breaker for external services (SMTP, LLM, etc.)
external_service_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    name="external_service",
    listeners=[_DBCircuitBreakerListener()],
)
