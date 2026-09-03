"""
Backup Gap Detector
Detects backup gaps based on SQL Agent job schedules
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from watcherdb.core.database import get_server_connection

logger = logging.getLogger(__name__)


class BackupGapDetector:
    """Detects backup gaps by comparing schedules with actual backups"""

    def detect_gaps(self, server_id: str, window_days: int = 30) -> Dict[str, Any]:
        """
        Detect backup gaps for a server based on job schedules

        Args:
            server_id: Server identifier
            window_days: Number of days to look back (default 30)

        Returns:
            Dict with gaps information
        """
        try:
            # 1. Get backup schedules from SQL Agent jobs
            schedules = self._get_backup_schedules(server_id)

            # 2. Get actual backup history
            actual_backups = self._get_backup_history(server_id, window_days)

            # 3. Compare and detect gaps
            gaps = self._compare_and_detect_gaps(schedules, actual_backups)

            # 4. Calculate statistics
            stats = self._calculate_statistics(gaps)

            return {
                "success": True,
                "server_id": server_id,
                "window_days": window_days,
                "total_gaps": len(gaps),
                "critical_count": stats['critical'],
                "high_count": stats['high'],
                "medium_count": stats['medium'],
                "low_count": stats['low'],
                "gaps": gaps,
                "summary": self._create_summary(gaps)
            }

        except Exception as e:
            logger.error(f"Error detecting gaps for {server_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id,
                "gaps": []
            }

    def _get_backup_schedules(self, server_id: str) -> List[Dict]:
        """Get backup schedules from SQL Agent jobs"""
        query = """
        WITH BackupJobs AS (
            SELECT DISTINCT
                j.job_id,
                j.name AS job_name,
                j.enabled AS is_enabled,
                js.step_id,
                js.command,
                CASE
                    WHEN js.command LIKE '%DATABASE = %' THEN
                        SUBSTRING(
                            js.command,
                            CHARINDEX('DATABASE = ', js.command) + 11,
                            CHARINDEX(',', js.command, CHARINDEX('DATABASE = ', js.command)) - CHARINDEX('DATABASE = ', js.command) - 11
                        )
                    WHEN js.command LIKE '%BACKUP DATABASE [[]%' THEN
                        SUBSTRING(
                            js.command,
                            CHARINDEX('BACKUP DATABASE [', js.command) + 16,
                            CHARINDEX(']', js.command, CHARINDEX('BACKUP DATABASE [', js.command)) - CHARINDEX('BACKUP DATABASE [', js.command) - 16
                        )
                    WHEN js.command LIKE '%BACKUP LOG [[]%' THEN
                        SUBSTRING(
                            js.command,
                            CHARINDEX('BACKUP LOG [', js.command) + 12,
                            CHARINDEX(']', js.command, CHARINDEX('BACKUP LOG [', js.command)) - CHARINDEX('BACKUP LOG [', js.command) - 12
                        )
                    ELSE NULL
                END AS database_name,
                CASE
                    WHEN js.command LIKE '%BACKUP LOG%' THEN 'LOG'
                    WHEN js.command LIKE '%DIFFERENTIAL%' OR js.command LIKE '%TYPE = DIFFERENTIAL%' THEN 'DIFF'
                    WHEN js.command LIKE '%BACKUP DATABASE%' THEN 'FULL'
                    ELSE 'UNKNOWN'
                END AS backup_type
            FROM msdb.dbo.sysjobs j WITH(NOLOCK)
            INNER JOIN msdb.dbo.sysjobsteps js WITH(NOLOCK) ON j.job_id = js.job_id
            WHERE (
                js.command LIKE '%BACKUP DATABASE%'
                OR js.command LIKE '%BACKUP LOG%'
            )
            AND j.enabled = 1
        ),
        JobSchedules AS (
            SELECT
                bj.job_id,
                bj.job_name,
                bj.database_name,
                bj.backup_type,
                bj.is_enabled,
                s.schedule_id,
                s.name AS schedule_name,
                s.enabled AS schedule_enabled,
                s.freq_type,
                s.freq_interval,
                s.freq_subday_type,
                s.freq_subday_interval,
                s.active_start_time,
                s.active_end_time,
                s.active_start_date,
                s.active_end_date
            FROM BackupJobs bj
            INNER JOIN msdb.dbo.sysjobschedules js WITH(NOLOCK) ON bj.job_id = js.job_id
            INNER JOIN msdb.dbo.sysschedules s WITH(NOLOCK) ON js.schedule_id = s.schedule_id
            WHERE s.enabled = 1
        )
        SELECT
            database_name,
            backup_type,
            job_name,
            schedule_name,
            CASE freq_type
                WHEN 1 THEN 'Once'
                WHEN 4 THEN 'Daily'
                WHEN 8 THEN 'Weekly'
                WHEN 16 THEN 'Monthly'
                WHEN 32 THEN 'Monthly Relative'
                WHEN 64 THEN 'When SQL Server Agent starts'
                WHEN 128 THEN 'When computer is idle'
                ELSE 'Unknown'
            END AS frequency_type,
            CASE
                WHEN freq_type = 4 AND freq_subday_type = 8 THEN freq_subday_interval
                WHEN freq_type = 4 AND freq_subday_type = 4 THEN CAST(freq_subday_interval AS FLOAT) / 60.0
                WHEN freq_type = 4 AND freq_subday_type = 1 THEN 24
                WHEN freq_type = 8 THEN 24.0 * 7 / NULLIF(
                    (freq_interval & 1) + ((freq_interval & 2) / 2) + ((freq_interval & 4) / 4) +
                    ((freq_interval & 8) / 8) + ((freq_interval & 16) / 16) + ((freq_interval & 32) / 32) +
                    ((freq_interval & 64) / 64), 0
                )
                WHEN freq_type = 16 THEN 24 * 30
                ELSE NULL
            END AS expected_interval_hours,
            STUFF(STUFF(RIGHT('000000' + CAST(active_start_time AS VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':') AS scheduled_time,
            freq_interval,
            freq_subday_type,
            freq_subday_interval,
            active_start_time
        FROM JobSchedules
        WHERE database_name IS NOT NULL
        ORDER BY database_name, backup_type
        """

        conn = get_server_connection(server_id)
        cursor = conn.cursor()
        cursor.execute(query)

        columns = [column[0] for column in cursor.description]
        schedules = []
        for row in cursor.fetchall():
            schedules.append(dict(zip(columns, row)))

        cursor.close()
        conn.close()

        logger.info(f"Found {len(schedules)} backup schedules for {server_id}")
        return schedules

    def _get_backup_history(self, server_id: str, window_days: int) -> Dict[str, Dict]:
        """Get actual backup history from msdb"""
        query = f"""
        SELECT
            d.name AS database_name,
            bs.type AS backup_type_code,
            CASE bs.type
                WHEN 'D' THEN 'FULL'
                WHEN 'I' THEN 'DIFF'
                WHEN 'L' THEN 'LOG'
                ELSE 'UNKNOWN'
            END AS backup_type,
            MAX(bs.backup_finish_date) AS last_backup_date,
            DATEDIFF(HOUR, MAX(bs.backup_finish_date), GETDATE()) AS hours_since_last
        FROM sys.databases d WITH(NOLOCK)
        LEFT JOIN msdb.dbo.backupset bs WITH(NOLOCK)
            ON d.name = bs.database_name
            AND bs.backup_finish_date >= DATEADD(DAY, -{window_days}, GETDATE())
        WHERE d.state = 0  -- ONLINE
        GROUP BY d.name, bs.type
        ORDER BY d.name, backup_type
        """

        conn = get_server_connection(server_id)
        cursor = conn.cursor()
        cursor.execute(query)

        # Organizar por database e tipo
        history = {}
        for row in cursor.fetchall():
            db_name = row[0]
            backup_type = row[2]
            last_backup = row[3]
            hours_since = row[4] if row[4] else None

            if db_name not in history:
                history[db_name] = {}

            history[db_name][backup_type] = {
                'last_backup_date': last_backup,
                'hours_since_last': hours_since
            }

        cursor.close()
        conn.close()

        logger.info(f"Loaded backup history for {len(history)} databases")
        return history

    def _compare_and_detect_gaps(self, schedules: List[Dict], actual_backups: Dict) -> List[Dict]:
        """Compare schedules with actual backups and detect gaps"""
        gaps = []
        now = datetime.now()

        for schedule in schedules:
            db_name = schedule['database_name']
            backup_type = schedule['backup_type']
            expected_interval = schedule.get('expected_interval_hours')

            if not expected_interval or expected_interval is None:
                logger.warning(f"No expected interval for {db_name}/{backup_type}, skipping")
                continue

            # Get actual backup info
            actual = actual_backups.get(db_name, {}).get(backup_type)

            if not actual or actual['last_backup_date'] is None:
                # No backup found - critical gap
                gaps.append({
                    'database_name': db_name,
                    'backup_type': backup_type,
                    'gap_hours': None,
                    'severity': 'CRITICAL',
                    'expected_interval_hours': expected_interval,
                    'last_backup_date': None,
                    'schedule_name': schedule.get('schedule_name'),
                    'frequency_type': schedule.get('frequency_type'),
                    'message': f'No {backup_type} backup found in last {30} days'
                })
                continue

            hours_since = actual['hours_since_last']

            # Check if overdue (with tolerance of 10% to avoid false positives)
            tolerance = expected_interval * 0.1
            if hours_since > (expected_interval + tolerance):
                gap_hours = hours_since - expected_interval

                # Determine severity
                if gap_hours > expected_interval * 2:
                    severity = 'CRITICAL'
                elif gap_hours > expected_interval:
                    severity = 'HIGH'
                elif gap_hours > expected_interval * 0.5:
                    severity = 'MEDIUM'
                else:
                    severity = 'LOW'

                gaps.append({
                    'database_name': db_name,
                    'backup_type': backup_type,
                    'gap_hours': round(gap_hours, 1),
                    'severity': severity,
                    'expected_interval_hours': expected_interval,
                    'last_backup_date': actual['last_backup_date'].isoformat() if actual['last_backup_date'] else None,
                    'schedule_name': schedule.get('schedule_name'),
                    'frequency_type': schedule.get('frequency_type'),
                    'message': f'{backup_type} backup overdue by {round(gap_hours, 1)}h (expected every {expected_interval}h)'
                })

        logger.info(f"Detected {len(gaps)} backup gaps")
        return gaps

    def _calculate_statistics(self, gaps: List[Dict]) -> Dict[str, int]:
        """Calculate gap statistics by severity"""
        stats = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}

        for gap in gaps:
            severity = gap.get('severity', '').lower()
            if severity in stats:
                stats[severity] += 1

        return stats

    def _create_summary(self, gaps: List[Dict]) -> List[Dict]:
        """Create summary of gaps by database"""
        summary_dict = {}

        for gap in gaps:
            db_name = gap['database_name']
            if db_name not in summary_dict:
                summary_dict[db_name] = {
                    'database_name': db_name,
                    'gap_count': 0,
                    'backup_types_affected': set(),
                    'max_severity': 'LOW'
                }

            summary_dict[db_name]['gap_count'] += 1
            summary_dict[db_name]['backup_types_affected'].add(gap['backup_type'])

            # Update max severity
            severity_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'CRITICAL': 4}
            current_severity = summary_dict[db_name]['max_severity']
            if severity_order.get(gap['severity'], 0) > severity_order.get(current_severity, 0):
                summary_dict[db_name]['max_severity'] = gap['severity']

        # Convert sets to lists for JSON serialization
        summary = []
        for db_summary in summary_dict.values():
            db_summary['backup_types_affected'] = list(db_summary['backup_types_affected'])
            summary.append(db_summary)

        return summary
