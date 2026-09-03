"""
Registry for ThreadPoolExecutors — ensures coordinated shutdown.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

logger = logging.getLogger(__name__)

_executors: Dict[str, ThreadPoolExecutor] = {}


def register_executor(name: str, executor: ThreadPoolExecutor):
    """Register an executor for coordinated shutdown."""
    _executors[name] = executor
    logger.debug(f"Registered executor: {name}")


def create_executor(name: str, max_workers: int = 4) -> ThreadPoolExecutor:
    """Create and register a new executor."""
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=name)
    register_executor(name, executor)
    return executor


def shutdown_all(wait: bool = True, cancel_futures: bool = False):
    """Shutdown all registered executors."""
    for name, executor in _executors.items():
        try:
            executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            logger.info(f"Executor '{name}' shutdown")
        except Exception as e:
            logger.error(f"Error shutting down executor '{name}': {e}")
    _executors.clear()
