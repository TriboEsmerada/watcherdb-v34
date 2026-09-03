"""
Backup Analysis Router
Handles all backup-related monitoring endpoints
OTIMIZADO: Cache com TTL para evitar queries repetidas
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, Any
import logging
import time
from functools import lru_cache

from watcherdb.core.auth import get_current_user, User
from modules.monitoring.backup_analysis import BackupAnalysisEngine
from modules.monitoring.backup_pattern_analysis import BackupPatternAnalyzer
from modules.monitoring.monitoring import SQLServerMonitoring

logger = logging.getLogger(__name__)

# ========================================
# CACHE SIMPLES COM TTL
# ========================================
class TTLCache:
    """Cache simples com Time-To-Live para evitar queries repetidas"""
    def __init__(self, ttl_seconds: int = 300):  # 5 minutos default
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                logger.debug(f"Cache HIT: {key}")
                return value
            else:
                # Expirado, remover
                del self._cache[key]
                logger.debug(f"Cache EXPIRED: {key}")
        return None

    def set(self, key: str, value: Any):
        self._cache[key] = (value, time.time())
        logger.debug(f"Cache SET: {key}")

    def clear(self):
        self._cache.clear()
        logger.info("Cache cleared")

    def invalidate(self, pattern: str):
        """Remove entries matching pattern"""
        keys_to_remove = [k for k in self._cache.keys() if pattern in k]
        for k in keys_to_remove:
            del self._cache[k]
        logger.debug(f"Cache invalidated {len(keys_to_remove)} entries for pattern: {pattern}")


# Cache global para backup data (TTL 5 minutos)
backup_cache = TTLCache(ttl_seconds=300)

router = APIRouter(
    prefix="/api/monitoring/backup",
    tags=["backup-analysis"],
    responses={404: {"description": "Not found"}},
)


@router.get("/server/{server_id}/summary")
async def get_backup_summary(
    server_id: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user)
):
    """Get backup summary for a specific server"""
    try:
        cache_key = f"backup_summary:{server_id}:{days}"

        # Verificar cache primeiro
        cached = backup_cache.get(cache_key)
        if cached:
            logger.info(f"Backup summary from CACHE for: {server_id}")
            return cached

        logger.info(f"Backup summary requested for server: {server_id} (days={days})")

        sql_monitoring = SQLServerMonitoring("watcherdb_cache.db")
        server_name = server_id.replace('_', '\\')
        engine = BackupAnalysisEngine(sql_monitoring)
        summary = await engine.analyze_server_backups(server_name, lookback_days=days)

        if not summary:
            raise HTTPException(status_code=404, detail=f"No backup data for server {server_id}")

        # Salvar no cache
        backup_cache.set(cache_key, summary)
        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting backup summary for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/patterns")
@router.get("/server/{server_id}/pattern")
async def get_backup_patterns(
    server_id: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user)
):
    """Analyze backup patterns for a specific server"""
    try:
        cache_key = f"backup_pattern:{server_id}:{days}"

        # Verificar cache primeiro (padrões podem ter TTL maior)
        cached = backup_cache.get(cache_key)
        if cached:
            logger.info(f"Backup patterns from CACHE for: {server_id}")
            return cached

        logger.info(f"Backup pattern analysis for {server_id} ({days} days)")

        sql_monitoring = SQLServerMonitoring("watcherdb_cache.db")
        server_name = server_id.replace('_', '\\')
        analyzer = BackupPatternAnalyzer(sql_monitoring)
        patterns = await analyzer.analyze_server_patterns(server_name, window_days=days)

        if not patterns:
            raise HTTPException(status_code=404, detail=f"No backup pattern data for {server_id}")

        # Salvar no cache
        backup_cache.set(cache_key, patterns)
        return patterns

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing backup patterns: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/gaps")
async def get_backup_gaps(
    server_id: str,
    window_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """
    Detect backup gaps based on SQL Agent job schedules
    Returns databases where backups are overdue based on their actual schedule
    """
    try:
        cache_key = f"backup_gaps:{server_id}:{window_days}"

        # Verificar cache primeiro
        cached = backup_cache.get(cache_key)
        if cached:
            logger.info(f"Backup gaps from CACHE for: {server_id}")
            return cached

        logger.info(f"Detecting backup gaps for {server_id} (window: {window_days} days)")

        from watcherdb.services.backup_gap_detector import BackupGapDetector

        detector = BackupGapDetector()
        gaps_result = detector.detect_gaps(server_id, window_days=window_days)

        # Salvar no cache (TTL menor para gaps - 2 minutos)
        backup_cache._ttl = 120  # 2 minutos para gaps
        backup_cache.set(cache_key, gaps_result)
        backup_cache._ttl = 300  # Voltar para 5 minutos

        return gaps_result

    except Exception as e:
        logger.error(f"Error detecting backup gaps for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/why-log-not-run")
async def why_log_backup_not_running(
    server_id: str,
    database_name: str,
    current_user: User = Depends(get_current_user)
):
    """Explain why log backups are not running for a database"""
    try:
        logger.info(f"Analyzing log backup issue for {server_id}/{database_name}")

        engine = BackupAnalysisEngine()
        analysis = engine.diagnose_log_backup_issue(server_id, database_name)

        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"Unable to diagnose log backup for {database_name} on {server_id}"
            )

        return analysis

    except Exception as e:
        logger.error(f"Error diagnosing log backup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/failed")
async def get_failed_backups(
    server_id: str,
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get failed backups for a server in the last N hours"""
    try:
        logger.info(f"Failed backups requested for {server_id} (last {hours}h)")

        engine = BackupAnalysisEngine()
        failed = engine.get_failed_backups(server_id, hours=hours)

        return {
            "server_id": server_id,
            "hours": hours,
            "failed_count": len(failed),
            "failed_backups": failed
        }

    except Exception as e:
        logger.error(f"Error getting failed backups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/missing")
async def get_missing_backups(
    server_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get databases with missing or overdue backups"""
    try:
        logger.info(f"Missing backups check for {server_id}")

        engine = BackupAnalysisEngine()
        missing = engine.get_missing_backups(server_id)

        return {
            "server_id": server_id,
            "missing_count": len(missing),
            "missing_backups": missing
        }

    except Exception as e:
        logger.error(f"Error checking missing backups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_backup_alerts(
    severity: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get backup-related alerts across all servers"""
    try:
        logger.info(f"Backup alerts requested")

        engine = BackupAnalysisEngine()
        alerts = engine.get_all_backup_alerts()

        # Filter by severity if specified
        if severity:
            alerts = [a for a in alerts if a.get("severity", "").lower() == severity.lower()]

        return {
            "total_alerts": len(alerts),
            "alerts": alerts
        }

    except Exception as e:
        logger.error(f"Error extracting backup alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_backup_dashboard(
    refresh: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Get aggregated backup dashboard data"""
    try:
        cache_key = "backup_dashboard:all"

        # Verificar cache (a menos que refresh=True)
        if not refresh:
            cached = backup_cache.get(cache_key)
            if cached:
                logger.info("Backup dashboard from CACHE")
                return cached

        logger.info(f"Backup dashboard requested (refresh={refresh})")

        engine = BackupAnalysisEngine()
        dashboard = engine.get_backup_dashboard()

        # Salvar no cache
        backup_cache.set(cache_key, dashboard)
        return dashboard

    except Exception as e:
        logger.error(f"Error generating backup dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache")
async def clear_backup_cache(
    server_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Clear backup cache (all or for specific server)"""
    try:
        if server_id:
            backup_cache.invalidate(server_id)
            logger.info(f"Backup cache cleared for server: {server_id}")
            return {"message": f"Cache cleared for server {server_id}"}
        else:
            backup_cache.clear()
            logger.info("Backup cache cleared (all)")
            return {"message": "All backup cache cleared"}

    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/database/{database_name}/history")
async def get_backup_history(
    server_id: str,
    database_name: str,
    days: int = 7,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """Get backup history for a specific database (with pagination)"""
    try:
        cache_key = f"backup_history:{server_id}:{database_name}:{days}"

        # Verificar cache
        cached = backup_cache.get(cache_key)
        if cached:
            all_history = cached
            logger.info(f"Backup history from CACHE for {server_id}/{database_name}")
        else:
            logger.info(f"Backup history for {server_id}/{database_name} (last {days} days)")
            engine = BackupAnalysisEngine()
            all_history = engine.get_backup_history(server_id, database_name, days=days)
            # Salvar no cache
            backup_cache.set(cache_key, all_history)

        # Aplicar paginação
        total_count = len(all_history)
        paginated_history = all_history[offset:offset + limit]

        return {
            "server_id": server_id,
            "database_name": database_name,
            "days": days,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count,
            "backup_count": len(paginated_history),
            "history": paginated_history
        }

    except Exception as e:
        logger.error(f"Error getting backup history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/recovery-model/{recovery_model}")
async def get_databases_by_recovery_model(
    server_id: str,
    recovery_model: str,
    current_user: User = Depends(get_current_user)
):
    """Get databases by recovery model (FULL, SIMPLE, BULK_LOGGED)"""
    try:
        logger.info(f"Databases with {recovery_model} recovery model on {server_id}")

        engine = BackupAnalysisEngine()
        databases = engine.get_databases_by_recovery_model(server_id, recovery_model)

        return {
            "server_id": server_id,
            "recovery_model": recovery_model,
            "database_count": len(databases),
            "databases": databases
        }

    except Exception as e:
        logger.error(f"Error filtering by recovery model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
