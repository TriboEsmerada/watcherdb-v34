"""
Space Analysis Service
Business logic for SQL Server disk space analysis and forecasting
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from watcherdb.core.cache import RedisLikeCache
from modules.monitoring.space_analysis import SpaceAnalysisEngine

logger = logging.getLogger(__name__)


class SpaceService:
    """Service for space analysis operations"""

    def __init__(self):
        """Initialize space service with cache"""
        self.cache = RedisLikeCache()
        self.engine = SpaceAnalysisEngine()

    async def get_server_space_analysis(self, server_id: str) -> Dict[str, Any]:
        """
        Get space analysis for a specific server

        Args:
            server_id: SQL Server identifier

        Returns:
            Dictionary with space analysis data
        """
        cache_key = f"space:analysis:{server_id}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for space analysis: {server_id}")
            return cached

        try:
            # Get analysis from engine
            result = self.engine.analyze_server(server_id)

            # Cache for 5 minutes
            self.cache.set(cache_key, result, ttl=300)

            return result

        except Exception as e:
            logger.error(f"Error getting space analysis for {server_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id
            }

    async def get_space_forecast(self, server_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get space growth forecast for a server

        Args:
            server_id: SQL Server identifier
            days: Number of days to forecast

        Returns:
            Dictionary with forecast data
        """
        cache_key = f"space:forecast:{server_id}:{days}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for space forecast: {server_id}")
            return cached

        try:
            # Get forecast from engine
            result = self.engine.forecast_space_growth(server_id, days=days)

            # Cache for 1 hour
            self.cache.set(cache_key, result, ttl=3600)

            return result

        except Exception as e:
            logger.error(f"Error getting space forecast for {server_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id,
                "days": days
            }

    async def get_all_servers_space_analysis(self) -> List[Dict[str, Any]]:
        """
        Get space analysis for all servers

        Returns:
            List of space analysis results
        """
        cache_key = "space:all_servers"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug("Cache hit for all servers space analysis")
            return cached

        try:
            # Get all servers analysis
            from modules.monitoring.space_analysis import get_space_analysis_for_all_servers
            results = get_space_analysis_for_all_servers()

            # Cache for 10 minutes
            self.cache.set(cache_key, results, ttl=600)

            return results

        except Exception as e:
            logger.error(f"Error getting all servers space analysis: {e}")
            return []

    async def get_space_health(self, server_id: str) -> Dict[str, Any]:
        """
        Get space health score and status for a server

        Args:
            server_id: SQL Server identifier

        Returns:
            Dictionary with health information
        """
        cache_key = f"space:health:{server_id}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        try:
            analysis = await self.get_server_space_analysis(server_id)

            # Calculate health score (0-100)
            health_score = 100
            if analysis.get("success"):
                # Reduce score based on space usage
                for db in analysis.get("databases", []):
                    usage_pct = db.get("space_used_percent", 0)
                    if usage_pct > 90:
                        health_score -= 20
                    elif usage_pct > 80:
                        health_score -= 10
                    elif usage_pct > 70:
                        health_score -= 5

            health = {
                "success": True,
                "server_id": server_id,
                "health_score": max(0, health_score),
                "status": "healthy" if health_score > 70 else "warning" if health_score > 40 else "critical"
            }

            # Cache for 5 minutes
            self.cache.set(cache_key, health, ttl=300)

            return health

        except Exception as e:
            logger.error(f"Error getting space health for {server_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id
            }
