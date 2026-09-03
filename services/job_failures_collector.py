"""
Job Failures Collector
======================

Collects failed SQL Agent jobs from all monitored servers and persists them
into ``dbo.KPI_MSSQL_JOB_FAILURES_STG`` so the dashboard can read from there
instead of falling back to a 14s "Direct" fan-out on every request.

Why this exists
---------------
Before this collector, the dashboard at ``/api/intelligence-kpis/dashboard``
would try 3 views (``KPI_MSSQL_JOB_FAILURES_AGG_VIEW`` etc), find them empty
or missing, and fall back to ``_query_jobs_from_servers()`` which iterates
all 200+ instances directly via msdb. That fallback alone took 13-14s per
request and pinned a worker.

With this collector running every N minutes:

  * the views are always populated with the last 24h of failures
  * the loop in ``helpers.collect_jobs_status`` reads from
    ``KPI_MSSQL_JOB_FAILURES_AGG_VIEW`` in <100ms
  * the Direct fallback never runs from the hot path

Idempotency
-----------
Each row has a natural key ``(Instance, job_name, run_datetime, step_name)``.
The collector uses MERGE so a row that already exists is left alone instead
of being inserted again. Re-runs are safe.

Retention
---------
After every successful collection, rows older than ``RETENTION_HOURS`` are
deleted. The view filters ``Insert_TS >= -24h``, so we keep 25h to allow a
small safety margin.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

import pyodbc

logger = logging.getLogger(__name__)

# Run every 5 minutes — same cadence as the dashboard cache TTL is 60s, so a
# 5-minute lag in seeing brand-new failed jobs is acceptable. The collector
# itself is heavy because it queries 20 servers in parallel; cadence shorter
# than 5 minutes risks overlapping with itself.
INTERVAL_SECONDS = 300

# Keep slightly more than the view window so the view never sees a gap during
# the moment between "old rows deleted" and "new rows inserted".
RETENTION_HOURS = 25


def _classify_job_type(job_name: str) -> str:
    """Heuristic classification by job name keyword. Mirrors the logic in
    api/routers/intelligence/helpers.py:collect_jobs_status."""
    name = (job_name or '').upper()
    if any(k in name for k in ('BACKUP', 'BKP', 'BKUP')):
        return 'Backup'
    if any(k in name for k in ('REINDEX', 'REBUILD', 'INDEX', 'OPTIMIZE', 'DEFRAG')):
        return 'Index'
    if any(k in name for k in ('STATISTIC', 'STATS', 'UPDATE STAT')):
        return 'Statistics'
    if any(k in name for k in ('CHECK', 'DBCC', 'INTEGRITY', 'CHECKDB')):
        return 'DBCC'
    if 'SHRINK' in name:
        return 'Shrink'
    if 'LOG' in name:
        return 'Log'
    if any(k in name for k in ('CLEANUP', 'CLEAN_UP', 'CLEAN UP', 'PURGE', 'ARCHIVE')):
        return 'Cleanup'
    if any(k in name for k in ('REPLICATION', 'REPL')):
        return 'Replication'
    if any(k in name for k in ('ALWAYSON', 'ALWAYS_ON', 'ALWAYS ON', 'HADR', 'AG_')):
        return 'AlwaysOn'
    return 'Other'


def _normalise_run_datetime(value):
    """Convert run_datetime from the upstream query to a Python datetime
    suitable for pyodbc parameter binding.

    The upstream ``_query_server_failed_jobs`` returns isoformat strings via
    ``hasattr(val, 'isoformat')`` branch — we accept str, datetime, or None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # ISO 8601 — use fromisoformat (handles both date and datetime forms)
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    return value  # already a datetime


async def collect_and_persist_job_failures() -> dict:
    """Run one collection cycle.

    Returns a dict with stats:
        {'fetched': N, 'inserted': N, 'kept': N, 'pruned': N, 'duration_s': float}
    """
    t_start = time.time()
    stats = {'fetched': 0, 'inserted': 0, 'kept': 0, 'pruned': 0, 'duration_s': 0.0}

    # Lazy import to avoid circular: intelligence_kpis imports a lot of stuff
    # that we don't want at module load time.
    from api.routers.intelligence_kpis import _query_jobs_from_servers
    from api.connection_pool import get_intelligence_pool

    # 1. Collect from all monitored servers (uses the existing parallel impl
    #    that already handles offline servers, timeout per server, etc).
    try:
        failed_results, _collisions = await _query_jobs_from_servers(
            only_collisions=False,
            timeout=25.0,
        )
    except Exception as e:
        logger.warning(f"[JobFailuresCollector] Failed to query servers: {e}")
        return stats

    if not failed_results or not failed_results.get('instances'):
        logger.info("[JobFailuresCollector] No failed jobs from any server this cycle")
        # Even if there are no new failures, prune old rows so retention holds
        _prune_old(stats)
        stats['duration_s'] = round(time.time() - t_start, 2)
        return stats

    rows: list = failed_results['instances']
    stats['fetched'] = len(rows)

    # 2. Persist via MERGE (idempotent on natural key)
    pool = get_intelligence_pool()
    conn: pyodbc.Connection = pool.get_connection()
    try:
        cursor = conn.cursor()

        # MERGE statement: match on (Instance, job_name, run_datetime, step_name)
        # — these four together identify a unique failed-job execution. If the
        # row exists we leave it alone (no UPDATE), otherwise INSERT.
        merge_sql = """
            MERGE dbo.KPI_MSSQL_JOB_FAILURES_STG WITH (HOLDLOCK) AS tgt
            USING (SELECT
                      ? AS Instance,
                      ? AS job_name,
                      ? AS step_name,
                      ? AS status_desc,
                      ? AS run_datetime,
                      ? AS duration_seconds,
                      ? AS error_message,
                      ? AS Job_Type
                  ) AS src
            ON tgt.Instance = src.Instance
                AND tgt.job_name = src.job_name
                AND ISNULL(tgt.run_datetime, '1900-01-01') = ISNULL(src.run_datetime, '1900-01-01')
                AND ISNULL(tgt.step_name, '') = ISNULL(src.step_name, '')
            WHEN NOT MATCHED BY TARGET THEN
                INSERT (Instance, job_name, step_name, status_desc,
                        run_datetime, duration_seconds, error_message, Job_Type)
                VALUES (src.Instance, src.job_name, src.step_name, src.status_desc,
                        src.run_datetime, src.duration_seconds, src.error_message, src.Job_Type);
        """

        inserted = 0
        kept = 0
        for r in rows:
            instance = r.get('Instance') or ''
            job_name = r.get('job_name') or r.get('Job_Name') or r.get('JobName') or ''
            if not instance or not job_name:
                continue
            step_name = r.get('step_name') or r.get('StepName')
            status_desc = r.get('status_desc') or r.get('StatusDesc')
            run_dt = _normalise_run_datetime(r.get('run_datetime') or r.get('RunDateTime'))
            duration = r.get('duration_seconds') or r.get('DurationSeconds')
            err_msg = (r.get('error_message') or r.get('ErrorMessage') or '')[:500]
            job_type = r.get('Job_Type') or _classify_job_type(job_name)

            try:
                cursor.execute(
                    merge_sql,
                    instance, job_name, step_name, status_desc,
                    run_dt, duration, err_msg, job_type,
                )
                # rowcount==1 means INSERT happened; 0 means already existed
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    kept += 1
            except Exception as merge_err:
                logger.debug(f"[JobFailuresCollector] MERGE failed for {instance}/{job_name}: {merge_err}")
                continue

        # Commit explicit even though pool uses autocommit — defensive.
        try:
            conn.commit()
        except Exception:
            pass

        stats['inserted'] = inserted
        stats['kept'] = kept

        # 3. Prune old rows (retention)
        try:
            cursor.execute(
                f"DELETE FROM dbo.KPI_MSSQL_JOB_FAILURES_STG "
                f"WHERE Insert_TS < DATEADD(HOUR, -{RETENTION_HOURS}, SYSUTCDATETIME())"
            )
            stats['pruned'] = cursor.rowcount or 0
            try:
                conn.commit()
            except Exception:
                pass
        except Exception as prune_err:
            logger.debug(f"[JobFailuresCollector] Prune failed: {prune_err}")

        cursor.close()

    finally:
        try:
            pool.return_connection(conn)
        except Exception:
            pass

    stats['duration_s'] = round(time.time() - t_start, 2)
    logger.info(
        f"[JobFailuresCollector] cycle done: fetched={stats['fetched']} "
        f"inserted={stats['inserted']} kept={stats['kept']} "
        f"pruned={stats['pruned']} duration={stats['duration_s']}s"
    )
    return stats


def _prune_old(stats: dict) -> None:
    """Helper to prune even when there were no fetched rows."""
    try:
        from api.connection_pool import get_intelligence_pool
        pool = get_intelligence_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM dbo.KPI_MSSQL_JOB_FAILURES_STG "
                f"WHERE Insert_TS < DATEADD(HOUR, -{RETENTION_HOURS}, SYSUTCDATETIME())"
            )
            stats['pruned'] = cursor.rowcount or 0
            try:
                conn.commit()
            except Exception:
                pass
            cursor.close()
        finally:
            try:
                pool.return_connection(conn)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[JobFailuresCollector] _prune_old failed: {e}")


def register_with_scheduler() -> None:
    """Register this collector as a periodic task with the global scheduler.

    Called once during application startup. Idempotent.
    """
    from watcherdb.core.scheduler import add_periodic_task

    add_periodic_task(
        collect_and_persist_job_failures,
        interval_seconds=INTERVAL_SECONDS,
        task_id='job_failures_collector',
        next_run_time=None,  # let APScheduler decide first run
    )
    logger.info(
        f"[JobFailuresCollector] registered with scheduler "
        f"(interval={INTERVAL_SECONDS}s, retention={RETENTION_HOURS}h)"
    )
