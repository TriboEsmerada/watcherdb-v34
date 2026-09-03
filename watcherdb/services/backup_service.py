"""
Backup Analysis Service
Business logic for SQL Server backup monitoring and analysis
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from watcherdb.core.cache import RedisLikeCache
from modules.monitoring.backup_analysis import BackupAnalysisEngine
from modules.monitoring.backup_pattern_analysis import BackupPatternAnalyzer

logger = logging.getLogger(__name__)


class BackupService:
    """Service for backup analysis operations"""

    def __init__(self):
        """Initialize backup service with cache and engines"""
        self.cache = RedisLikeCache()
        self.engine = BackupAnalysisEngine()
        self.pattern_analyzer = BackupPatternAnalyzer()

    async def get_server_backup_summary(self, server_id: str, days: int = 7) -> Dict[str, Any]:
        """
        Get backup summary for a specific server

        Args:
            server_id: SQL Server identifier
            days: Number of days to analyze

        Returns:
            Dictionary with backup summary
        """
        cache_key = f"backup:summary:{server_id}:{days}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for backup summary: {server_id}")
            return cached

        try:
            # Get summary from engine
            result = self.engine.get_backup_summary(server_id, days=days)

            # Cache for 15 minutes
            self.cache.set(cache_key, result, ttl=900)

            return result

        except Exception as e:
            logger.error(f"Error getting backup summary for {server_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id
            }

    async def get_backup_patterns(self, server_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get backup patterns analysis for a server

        Args:
            server_id: SQL Server identifier
            days: Number of days to analyze

        Returns:
            Dictionary with pattern analysis
        """
        cache_key = f"backup:patterns:{server_id}:{days}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for backup patterns: {server_id}")
            return cached

        try:
            # Get patterns from analyzer
            result = self.pattern_analyzer.analyze_patterns(server_id, days=days)

            # Cache for 1 hour
            self.cache.set(cache_key, result, ttl=3600)

            return result

        except Exception as e:
            logger.error(f"Error getting backup patterns for {server_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id
            }

    async def get_failed_backups(self, server_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get list of failed backups for a server

        Args:
            server_id: SQL Server identifier
            days: Number of days to look back

        Returns:
            List of failed backup records
        """
        cache_key = f"backup:failed:{server_id}:{days}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        try:
            # Get failed backups from engine
            result = self.engine.get_failed_backups(server_id, days=days)

            # Cache for 10 minutes
            self.cache.set(cache_key, result, ttl=600)

            return result

        except Exception as e:
            logger.error(f"Error getting failed backups for {server_id}: {e}")
            return []

    async def get_missing_backups(self, server_id: str) -> List[Dict[str, Any]]:
        """
        Get list of databases missing backups

        Args:
            server_id: SQL Server identifier

        Returns:
            List of databases with missing backups
        """
        cache_key = f"backup:missing:{server_id}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        try:
            # Get missing backups from engine
            result = self.engine.get_missing_backups(server_id)

            # Cache for 15 minutes
            self.cache.set(cache_key, result, ttl=900)

            return result

        except Exception as e:
            logger.error(f"Error getting missing backups for {server_id}: {e}")
            return []

    async def get_backup_health(self, server_id: str) -> Dict[str, Any]:
        """
        Get overall backup health score for a server

        Args:
            server_id: SQL Server identifier

        Returns:
            Dictionary with health score and status
        """
        cache_key = f"backup:health:{server_id}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        try:
            summary = await self.get_server_backup_summary(server_id)
            failed = await self.get_failed_backups(server_id)
            missing = await self.get_missing_backups(server_id)

            # Calculate health score (0-100)
            health_score = 100
            health_score -= len(failed) * 10  # -10 per failed backup
            health_score -= len(missing) * 15  # -15 per missing backup

            health = {
                "success": True,
                "server_id": server_id,
                "health_score": max(0, min(100, health_score)),
                "status": "healthy" if health_score > 70 else "warning" if health_score > 40 else "critical",
                "failed_count": len(failed),
                "missing_count": len(missing)
            }

            # Cache for 10 minutes
            self.cache.set(cache_key, health, ttl=600)

            return health

        except Exception as e:
            logger.error(f"Error getting backup health for {server_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id
            }
