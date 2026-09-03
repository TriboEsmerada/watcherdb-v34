"""
Rate Limiting Implementation
Simple in-memory rate limiter for API endpoints
"""

import time
import threading
from typing import Dict, Optional, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    In-memory rate limiter using sliding window algorithm

    Usage:
        limiter = RateLimiter()
        limiter.add_rule("/api/queries", max_requests=30, window_seconds=60)

        if not limiter.is_allowed(client_id, endpoint):
            # Rate limit exceeded
            raise HTTPException(429, "Too many requests")
    """

    def __init__(self):
        self.rules: Dict[str, Tuple[int, int]] = {}  # endpoint -> (max_requests, window_seconds)
        self.requests: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))  # client -> endpoint -> [timestamps]
        self.lock = threading.RLock()
        self.default_limit = (100, 60)  # 100 requests per minute by default

    def add_rule(self, endpoint_pattern: str, max_requests: int, window_seconds: int) -> None:
        """
        Add rate limiting rule for endpoint

        Args:
            endpoint_pattern: Endpoint pattern (e.g., "/api/queries/*")
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
        """
        with self.lock:
            self.rules[endpoint_pattern] = (max_requests, window_seconds)
        logger.info(f"Rate limit rule added: {endpoint_pattern} - {max_requests} requests per {window_seconds}s")

    def is_allowed(self, client_id: str, endpoint: str) -> bool:
        """
        Check if request is allowed

        Args:
            client_id: Client identifier (e.g., IP address, user ID)
            endpoint: API endpoint

        Returns:
            True if allowed, False if rate limit exceeded
        """
        with self.lock:
            # Find matching rule
            max_requests, window_seconds = self._get_rule_for_endpoint(endpoint)

            # Get request history for this client/endpoint
            request_times = self.requests[client_id][endpoint]

            # Remove old requests outside the window
            current_time = time.time()
            cutoff_time = current_time - window_seconds
            request_times[:] = [t for t in request_times if t > cutoff_time]

            # Check if limit exceeded
            if len(request_times) >= max_requests:
                logger.warning(f"Rate limit exceeded: {client_id} - {endpoint}")
                return False

            # Add current request
            request_times.append(current_time)
            return True

    def _get_rule_for_endpoint(self, endpoint: str) -> Tuple[int, int]:
        """Get rate limit rule for endpoint (with pattern matching)"""
        # Exact match
        if endpoint in self.rules:
            return self.rules[endpoint]

        # Pattern matching (simple wildcard support)
        for pattern, rule in self.rules.items():
            if pattern.endswith("/*"):
                prefix = pattern[:-2]
                if endpoint.startswith(prefix):
                    return rule

        # Default limit
        return self.default_limit

    def get_remaining(self, client_id: str, endpoint: str) -> int:
        """
        Get remaining requests for client/endpoint

        Args:
            client_id: Client identifier
            endpoint: API endpoint

        Returns:
            Number of remaining requests
        """
        with self.lock:
            max_requests, window_seconds = self._get_rule_for_endpoint(endpoint)
            request_times = self.requests[client_id][endpoint]

            # Remove old requests
            current_time = time.time()
            cutoff_time = current_time - window_seconds
            request_times[:] = [t for t in request_times if t > cutoff_time]

            return max(0, max_requests - len(request_times))

    def reset(self, client_id: Optional[str] = None, endpoint: Optional[str] = None) -> None:
        """
        Reset rate limit counters

        Args:
            client_id: Reset specific client (if None, reset all)
            endpoint: Reset specific endpoint (if None, reset all)
        """
        with self.lock:
            if client_id is None:
                self.requests.clear()
                logger.info("All rate limit counters reset")
            elif endpoint is None:
                if client_id in self.requests:
                    del self.requests[client_id]
                logger.info(f"Rate limit counters reset for client: {client_id}")
            else:
                if client_id in self.requests and endpoint in self.requests[client_id]:
                    del self.requests[client_id][endpoint]
                logger.info(f"Rate limit counter reset for {client_id}/{endpoint}")

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        with self.lock:
            total_clients = len(self.requests)
            total_endpoints = sum(len(endpoints) for endpoints in self.requests.values())
            total_rules = len(self.rules)

            return {
                "total_clients": total_clients,
                "total_endpoints": total_endpoints,
                "total_rules": total_rules,
                "rules": {pattern: {"max_requests": r[0], "window_seconds": r[1]} for pattern, r in self.rules.items()}
            }


# ==========================================
# Global Rate Limiter Instance
# ==========================================
global_rate_limiter = RateLimiter()


# ==========================================
# FastAPI Middleware Helper
# ==========================================
def get_client_ip(request) -> str:
    """Extract client IP from request"""
    # Check for forwarded IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Check for real IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Use direct client
    return request.client.host if request.client else "unknown"
