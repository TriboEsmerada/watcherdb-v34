"""
API Versioning Strategy — WatcherDB V3.2

Current state:
- /api/v3/*          -> Main API (SQL Server monitoring)
- /api/v1/copilot/*  -> DBA Copilot
- /api/auth/*        -> Authentication (unversioned for backward compat)
- /api/monitoring/*  -> Monitoring endpoints (legacy, unversioned)

Target state (v4):
- All new endpoints under /api/v4/
- /api/v3/ maintained for backward compatibility
- /api/auth/ stays unversioned (cross-version)

Migration:
1. New features go under /api/v4/
2. Deprecation headers added to v3 endpoints after v4 is stable
3. v3 removed after 6 months deprecation period
"""

API_V3_PREFIX = "/api/v3"
API_V4_PREFIX = "/api/v4"
AUTH_PREFIX = "/api/auth"        # Unversioned -- cross-version
COPILOT_PREFIX = "/api/v1/copilot"  # Will move to v4 when LLM is production-ready
METRICS_PREFIX = "/metrics"      # Prometheus -- unversioned by convention
