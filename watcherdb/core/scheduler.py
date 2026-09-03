"""
Centralized task scheduler using APScheduler.

Replaces ad-hoc daemon threads with a managed scheduler.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the singleton scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            job_defaults={
                'coalesce': True,       # Combine missed runs
                'max_instances': 1,     # Prevent overlapping
                'misfire_grace_time': 60,
            }
        )
        logger.info("APScheduler initialized")
    return _scheduler


def start_scheduler():
    """Start the scheduler (call during app startup)."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info(f"APScheduler started with {len(scheduler.get_jobs())} jobs")


def shutdown_scheduler():
    """Shutdown the scheduler (call during app shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler shutdown")
    _scheduler = None


def add_periodic_task(func, interval_seconds: int, task_id: str, **kwargs):
    """
    Register a periodic task.

    Args:
        func: Async or sync callable
        interval_seconds: Run every N seconds
        task_id: Unique identifier for the job
    """
    scheduler = get_scheduler()

    # Remove existing job with same ID (idempotent)
    if scheduler.get_job(task_id):
        scheduler.remove_job(task_id)

    scheduler.add_job(
        func,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id=task_id,
        name=task_id,
        **kwargs,
    )
    logger.info(f"Scheduled task '{task_id}' every {interval_seconds}s")
