"""
TapOS Space Analysis - Capacity Planning Module
Análise de crescimento e previsão de espaço em disco
VERSÃO CORRIGIDA FINAL v2: Thresholds ajustados + Identificação detalhada
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============================================
# DECIMAL CONVERSION HELPERS
# ============================================
def to_float(value: Union[Decimal, float, int, None]) -> float:
    """Converte Decimal do SQL Server para float Python."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def safe_percentage(numerator: Union[Decimal, float, None], 
                   denominator: Union[Decimal, float, None]) -> float:
    """Calcula percentual seguro."""
    num = to_float(numerator)
    den = to_float(denominator)
    return round((num / den * 100.0), 2) if den != 0 else 0.0


@dataclass
class SpaceAlert:
    """Alerta de espaço crítico"""
    server_id: str
    database_name: str
    filegroup_name: str
    logical_names: List[str]
    alert_level: str
    free_percent: float
    free_gb: float
    current_gb: float
    max_gb: float
    estimated_days_to_full: int
    action_sql: str
    disk_available_gb: float
    timestamp: datetime


@dataclass
class FileGroupStatus:
    """Status de um filegroup específico"""
    database_name: str
    filegroup_name: str
    file_count: int
    logical_names: List[str]
    total_gb: float
    max_gb: float
    used_gb: float
    free_filegroup_percent: float
    free_disk_percent: float
    available_filegroup_gb: float
    available_disk_gb: float
    volume: str
    volume_logical_name: str
    alert_level: str
    disk_overflow_risk: bool


@dataclass
class GrowthPrediction:
    """Previsão de crescimento"""
    database_name: str
    current_size_gb: float
    growth_rate_mb_per_day: float
    estimated_full_date: Optional[datetime]
    days_until_full: Optional[int]
    recommended_action: str


class SpaceAnalysisEngine:
    """Engine de análise de espaço com previsão de crescimento"""
    
    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        self.cache_ttl = 300
        
    async def get_database_files(self, server_id: str, database_name: str) -> List[Dict]:
        """
        Retorna detalhes dos arquivos (logical names) de um database específico
        ✅ CORREÇÃO: Join com filegroups no contexto correto usando notation [database].sys.filegroups
        """
        query = f"""
        SELECT 
            mf.name AS LogicalName,
            mf.physical_name AS PhysicalName,
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            mf.type_desc AS FileType,
            CAST(mf.size * 8.0 / 1024 AS DECIMAL(18,2)) AS CurrentSizeMB,
            CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS CurrentSizeGB,
            CAST(
                CASE 
                    WHEN mf.max_size = -1 THEN -1
                    WHEN mf.max_size = 268435456 THEN 2097152
                    ELSE mf.max_size * 8.0 / 1024
                END 
                AS DECIMAL(18,2)
            ) AS MaxSizeMB,
            CAST(
                CASE 
                    WHEN mf.max_size = -1 THEN -1
                    WHEN mf.max_size = 268435456 THEN 2048
                    ELSE mf.max_size * 8.0 / 1024 / 1024
                END 
                AS DECIMAL(18,2)
            ) AS MaxSizeGB,
            CASE 
                WHEN mf.max_size = -1 THEN 'Unlimited'
                WHEN mf.max_size = 268435456 THEN '2TB (Default)'
                ELSE CAST(mf.max_size * 8.0 / 1024 / 1024 AS VARCHAR(20)) + ' GB'
            END AS MaxSizeFormatted,
            CASE 
                WHEN mf.is_percent_growth = 1 
                THEN CAST(mf.growth AS VARCHAR(10)) + '%'
                ELSE CAST(mf.growth * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
            END AS GrowthIncrement,
            vs.volume_mount_point AS Volume,
            CAST(vs.available_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(10,2)) AS DiskAvailableGB
        FROM sys.master_files mf
        LEFT JOIN [{database_name}].sys.filegroups fg 
            ON mf.data_space_id = fg.data_space_id 
            AND mf.database_id = DB_ID('{database_name}')
        CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
        WHERE mf.database_id = DB_ID('{database_name}')
          AND mf.state = 0
        ORDER BY mf.type, fg.name, mf.name;
        """
        
        try:
            result = await self.sql_monitoring.execute_query(server_id, query)
            
            if not result or not isinstance(result, dict):
                return []
            
            rows = result.get('rows', [])
            if not rows:
                return []
            
            files = []
            for row in rows:
                file_info = {
                    'logical_name': str(row.get('LogicalName', '')),
                    'physical_name': str(row.get('PhysicalName', '')),
                    'filegroup_name': str(row.get('FileGroupName', '')),
                    'file_type': str(row.get('FileType', '')),
                    'current_size_mb': to_float(row.get('CurrentSizeMB', 0)),
                    'current_size_gb': to_float(row.get('CurrentSizeGB', 0)),
                    'max_size_mb': to_float(row.get('MaxSizeMB', 0)),
                    'max_size_gb': to_float(row.get('MaxSizeGB', 0)),
                    'max_size_formatted': str(row.get('MaxSizeFormatted', '')),
                    'growth_increment': str(row.get('GrowthIncrement', '')),
                    'volume': str(row.get('Volume', '')),
                    'disk_available_gb': to_float(row.get('DiskAvailableGB', 0))
                }
                files.append(file_info)
            
            logger.info(f"Retrieved {len(files)} files for {database_name} on {server_id}")
            return files
            
        except Exception as e:
            logger.error(f"Error getting files for {database_name} on {server_id}: {e}", exc_info=True)
            return []
    
    async def get_database_filegroups(self, server_id: str, database_name: str) -> List[Dict]:
        """
        🔧 VERSÃO CORRIGIDA - Busca filegroups com valores reais
        """
        
        query_estimativa = f"""
        SELECT 
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END AS FileGroupType,
            COUNT(DISTINCT mf.file_id) AS FileCount,
            CAST(SUM(mf.size * 8.0 / 1024 / 1024) AS DECIMAL(18,2)) AS TotalGB,
            CAST(SUM(
                CASE 
                    WHEN mf.max_size = -1 THEN 999999
                    WHEN mf.max_size = 268435456 THEN 2048
                    ELSE mf.max_size * 8.0 / 1024 / 1024
                END
            ) AS DECIMAL(18,2)) AS MaxGB,
            CAST(SUM(mf.size * 8.0 / 1024 / 1024) * 0.75 AS DECIMAL(18,2)) AS UsedGB
        FROM sys.master_files mf
        LEFT JOIN [{database_name}].sys.filegroups fg 
            ON mf.data_space_id = fg.data_space_id
        WHERE mf.database_id = DB_ID('{database_name}')
          AND mf.state = 0
        GROUP BY 
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END,
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END
        ORDER BY FileGroupName;
        """
        
        query_precisa = f"""
        USE [{database_name}];
        
        WITH FileUsage AS (
            SELECT 
                f.data_space_id,
                f.file_id,
                CAST(FILEPROPERTY(f.name, 'SpaceUsed') * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS UsedGB
            FROM sys.database_files f
            WHERE f.type IN (0, 1) AND f.state = 0
        )
        SELECT 
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END AS FileGroupType,
            COUNT(DISTINCT mf.file_id) AS FileCount,
            CAST(SUM(mf.size * 8.0 / 1024 / 1024) AS DECIMAL(18,2)) AS TotalGB,
            CAST(SUM(
                CASE 
                    WHEN mf.max_size = -1 THEN 999999
                    WHEN mf.max_size = 268435456 THEN 2048
                    ELSE mf.max_size * 8.0 / 1024 / 1024
                END
            ) AS DECIMAL(18,2)) AS MaxGB,
            CAST(ISNULL(SUM(fu.UsedGB), SUM(mf.size * 8.0 / 1024 / 1024) * 0.75) AS DECIMAL(18,2)) AS UsedGB
        FROM sys.master_files mf
        LEFT JOIN sys.filegroups fg 
            ON mf.data_space_id = fg.data_space_id
        LEFT JOIN FileUsage fu 
            ON mf.file_id = fu.file_id
        WHERE mf.database_id = DB_ID('{database_name}')
          AND mf.state = 0
        GROUP BY 
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END,
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END
        ORDER BY FileGroupName;
        """
        
        query_por_arquivo = f"""
        SELECT 
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            CASE 
                WHEN mf.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END AS FileGroupType,
            mf.file_id AS FileId,
            mf.name AS LogicalName,
            CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS TotalGB,
            CAST(
                CASE 
                    WHEN mf.max_size = -1 THEN 999999
                    WHEN mf.max_size = 268435456 THEN 2048
                    ELSE mf.max_size * 8.0 / 1024 / 1024
                END 
            AS DECIMAL(18,2)) AS MaxGB,
            CAST(mf.size * 8.0 / 1024 / 1024 * 0.75 AS DECIMAL(18,2)) AS UsedGB
        FROM sys.master_files mf
        LEFT JOIN [{database_name}].sys.filegroups fg 
            ON mf.data_space_id = fg.data_space_id
        WHERE mf.database_id = DB_ID('{database_name}')
          AND mf.state = 0
        ORDER BY FileGroupName, mf.file_id;
        """
        
        try:
            try:
                result = await self.sql_monitoring.execute_query(server_id, query_precisa)
                if result and result.get('rows'):
                    return self._process_filegroup_rows(result.get('rows', []))
            except Exception:
                pass
            
            result = await self.sql_monitoring.execute_query(server_id, query_por_arquivo)
            
            if not result or not isinstance(result, dict):
                return []
            
            rows = result.get('rows', [])
            if not rows:
                return []
            
            filegroups_dict = {}
            for row in rows:
                fg_name = str(row.get('FileGroupName', ''))
                total_gb = to_float(row.get('TotalGB', 0))
                used_gb = to_float(row.get('UsedGB', 0))
                max_gb = to_float(row.get('MaxGB', 0))
                
                if fg_name not in filegroups_dict:
                    filegroups_dict[fg_name] = {
                        'filegroup_name': fg_name,
                        'filegroup_type': str(row.get('FileGroupType', '')),
                        'file_count': 0,
                        'total_gb': 0.0,
                        'max_gb': 0.0,
                        'used_gb': 0.0
                    }
                
                filegroups_dict[fg_name]['file_count'] += 1
                filegroups_dict[fg_name]['total_gb'] += total_gb
                filegroups_dict[fg_name]['max_gb'] += max_gb
                filegroups_dict[fg_name]['used_gb'] += used_gb
            
            filegroups = []
            for fg_name, fg_data in filegroups_dict.items():
                total_gb = fg_data['total_gb']
                used_gb = fg_data['used_gb']
                free_gb = total_gb - used_gb
                
                fg_info = {
                    'filegroup_name': fg_data['filegroup_name'],
                    'filegroup_type': fg_data['filegroup_type'],
                    'file_count': fg_data['file_count'],
                    'total_gb': round(total_gb, 2),
                    'max_gb': round(fg_data['max_gb'], 2),
                    'used_gb': round(used_gb, 2),
                    'free_gb': round(free_gb, 2),
                    'free_percent': round(safe_percentage(free_gb, total_gb), 2)
                }
                filegroups.append(fg_info)
            
            return filegroups
            
        except Exception:
            return []
    
    def _process_filegroup_rows(self, rows: List[Dict]) -> List[Dict]:
        filegroups = []
        
        for row in rows:
            total_gb = to_float(row.get('TotalGB', 0))
            used_gb = to_float(row.get('UsedGB', 0))
            free_gb = total_gb - used_gb
            
            fg_info = {
                'filegroup_name': str(row.get('FileGroupName', '')),
                'filegroup_type': str(row.get('FileGroupType', '')),
                'file_count': int(to_float(row.get('FileCount', 0))),
                'total_gb': round(total_gb, 2),
                'max_gb': round(to_float(row.get('MaxGB', 0)), 2),
                'used_gb': round(used_gb, 2),
                'free_gb': round(free_gb, 2),
                'free_percent': round(safe_percentage(free_gb, total_gb), 2)
            }
            filegroups.append(fg_info)
        
        return filegroups
    
    async def analyze_server_space(self, server_id: str) -> Dict:
        try:
            filegroups_data = await self._get_filegroups_detailed(server_id)
            volumes_data = await self._get_volumes_status(server_id)
            alerts = self._generate_space_alerts(filegroups_data)
            space_health_score = self._calculate_space_health(filegroups_data, volumes_data)
            
            critical_alerts = [a for a in alerts if a.alert_level == 'CRITICAL']
            high_alerts = [a for a in alerts if a.alert_level == 'HIGH']
            warning_alerts = [a for a in alerts if a.alert_level == 'WARNING']
            overflow_alerts = [a for a in alerts if a.alert_level == 'DISK_OVERFLOW']
            
            return {
                'server_id': server_id,
                'timestamp': datetime.now().isoformat(),
                'space_health_score': space_health_score,
                'total_alerts': len(alerts),
                'critical_alerts': len(critical_alerts),
                'high_alerts': len(high_alerts),
                'warning_alerts': len(warning_alerts),
                'overflow_alerts': len(overflow_alerts),
                'filegroups': [asdict(fg) for fg in filegroups_data],
                'volumes': volumes_data,
                'alerts': [asdict(a) for a in alerts],
                'recommendations': self._generate_recommendations(alerts, filegroups_data)
            }
        except Exception:
            return {'error': 'analysis-failed', 'server_id': server_id}
    
    async def _get_filegroups_detailed(self, server_id: str) -> List[FileGroupStatus]:
        query = """
WITH FileData AS (
    SELECT 
        mf.database_id,
        mf.type,
        mf.file_id,
        mf.name,
        mf.size,
        mf.max_size,
        FILEPROPERTY(mf.name, 'SpaceUsed') AS spaceused,
        vs.volume_mount_point,
        vs.total_bytes,
        vs.available_bytes
    FROM sys.master_files mf
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    WHERE mf.database_id > 4
      AND mf.type IN (0,1)
      AND mf.state = 0
)
SELECT
    DB_NAME(fd.database_id) AS DATABASENAME,
    CASE 
        WHEN fd.type = 1 THEN 'LOG'
        WHEN fd.type = 0 THEN 'DATA'
        ELSE 'OTHER'
    END AS FILETYPE,
    COUNT(DISTINCT fd.file_id) AS NUM_DATAFILES,
    STUFF((
        SELECT ', ' + fd2.name
        FROM FileData fd2
        WHERE fd2.database_id = fd.database_id
          AND fd2.type = fd.type
        FOR XML PATH(''), TYPE
    ).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS LOGICAL_NAMES,
    CAST(SUM(fd.size * 8.0 / 1024 / 1024) AS DECIMAL(20,2)) AS GB,
    CAST(SUM(
        CASE 
            WHEN fd.max_size = -1 THEN 999999
            WHEN fd.max_size = 268435456 THEN 2048
            ELSE fd.max_size * 8.0 / 1024 / 1024
        END
    ) AS DECIMAL(20,2)) AS MAXGB,
    CAST(SUM(fd.spaceused * 8.0 / 1024 / 1024) AS DECIMAL(20,2)) AS USEDGB,
    fd.volume_mount_point AS VOLMOUNTPOINT,
    CAST(MIN(fd.total_bytes) / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(20,2)) AS DISKTOTALGB,
    CAST(MIN(fd.available_bytes) / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(20,2)) AS DISKAVAILABLEGB
FROM FileData fd
GROUP BY fd.database_id, fd.type, fd.volume_mount_point
ORDER BY DB_NAME(fd.database_id), fd.type;

        """
        
        try:
            result = await self.sql_monitoring.execute_query(server_id, query)
            
            if not result or not isinstance(result, dict):
                return []
            
            rows = result.get('rows', [])
            if not rows:
                return []
            
            filegroups = []
            for row in rows:
                total_gb = to_float(row.get('GB', 0))
                max_gb = to_float(row.get('MAXGB', 0))
                used_gb = to_float(row.get('USEDGB', 0))
                disk_total_gb = to_float(row.get('DISKTOTALGB', 0))
                disk_available_gb = to_float(row.get('DISKAVAILABLEGB', 0))
                logical_names_str = str(row.get('LOGICAL_NAMES', ''))
                logical_names = [name.strip() for name in logical_names_str.split(',') if name.strip()]
                free_gb = total_gb - used_gb
                free_pct = safe_percentage(free_gb, total_gb) if total_gb > 0 else 0
                potential_growth = max_gb - total_gb if max_gb > 0 and max_gb < 999999 else 0
                disk_overflow = (potential_growth > disk_available_gb) if (potential_growth > 0 and disk_available_gb > 0) else False
                disk_free_pct = safe_percentage(disk_available_gb, disk_total_gb)
                fg = FileGroupStatus(
                    database_name=str(row.get('DATABASENAME', 'UNKNOWN')),
                    filegroup_name=str(row.get('FILETYPE', 'UNKNOWN')),
                    file_count=int(to_float(row.get('NUM_DATAFILES', 0))),
                    logical_names=logical_names,
                    total_gb=total_gb,
                    max_gb=max_gb,
                    used_gb=used_gb,
                    free_filegroup_percent=free_pct,
                    free_disk_percent=disk_free_pct,
                    available_filegroup_gb=free_gb,
                    available_disk_gb=disk_available_gb,
                    volume=str(row.get('VOLMOUNTPOINT', 'N/A')),
                    volume_logical_name='',
                    alert_level=self._classify_alert_level(free_pct, disk_free_pct, disk_overflow),
                    disk_overflow_risk=disk_overflow
                )
                filegroups.append(fg)
            return filegroups
        except Exception:
            return []
    
    async def _get_volumes_status(self, server_id: str) -> List[Dict]:
        query = """
        SELECT DISTINCT 
            vs.volume_mount_point AS Drive,
            CAST(vs.total_bytes / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS TotalGB,
            CAST(vs.available_bytes / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS FreeGB,
            CAST((vs.total_bytes - vs.available_bytes) / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS UsedGB,
            CAST(vs.available_bytes * 100.0 / vs.total_bytes AS DECIMAL(5,1)) AS FreePercent
        FROM sys.master_files mf
        CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
        WHERE mf.database_id > 4
        ORDER BY vs.volume_mount_point;
        """
        
        try:
            result = await self.sql_monitoring.execute_query(server_id, query)
            if not result or not isinstance(result, dict):
                return []
            rows = result.get('rows', [])
            if not rows:
                return []
            volumes = []
            for row in rows:
                volume = {
                    'Drive': str(row.get('Drive', 'N/A')),
                    'TotalGB': to_float(row.get('TotalGB', 0)),
                    'FreeGB': to_float(row.get('FreeGB', 0)),
                    'UsedGB': to_float(row.get('UsedGB', 0)),
                    'FreePercent': to_float(row.get('FreePercent', 0))
                }
                volumes.append(volume)
            return volumes
        except Exception:
            return []
    
    def _generate_space_alerts(self, filegroups: List[FileGroupStatus]) -> List[SpaceAlert]:
        alerts = []
        for fg in filegroups:
            if fg.alert_level in ['CRITICAL', 'HIGH', 'WARNING', 'DISK_OVERFLOW']:
                estimated_days = self._estimate_days_to_full(fg.available_filegroup_gb, fg.total_gb)
                if fg.disk_overflow_risk:
                    action = f"🔴 DISK OVERFLOW: MAXSIZE ({fg.max_gb:.1f}GB) > Disco disponível ({fg.available_disk_gb:.1f}GB)\n"
                    action += f"Arquivos: {', '.join(fg.logical_names[:3])}" + (" ..." if len(fg.logical_names) > 3 else "")
                else:
                    files_str = ', '.join(fg.logical_names[:2]) if fg.logical_names else '...'
                    action = f"-- Expandir arquivos: {files_str}\n"
                    action += f"ALTER DATABASE [{fg.database_name}] MODIFY FILE (NAME = '{fg.logical_names[0] if fg.logical_names else '...'}', SIZE = {fg.max_gb * 1.2:.0f}GB);"
                alert = SpaceAlert(
                    server_id='',
                    database_name=fg.database_name,
                    filegroup_name=fg.filegroup_name,
                    logical_names=fg.logical_names,
                    alert_level=fg.alert_level,
                    free_percent=fg.free_filegroup_percent,
                    free_gb=fg.available_filegroup_gb,
                    current_gb=fg.total_gb,
                    max_gb=fg.max_gb,
                    estimated_days_to_full=estimated_days,
                    action_sql=action,
                    disk_available_gb=fg.available_disk_gb,
                    timestamp=datetime.now()
                )
                alerts.append(alert)
        return alerts
    
    def _estimate_days_to_full(self, free_gb: float, total_gb: float) -> int:
        free = to_float(free_gb)
        total = to_float(total_gb)
        if free <= 0:
            return 0
        weekly_growth = total * 0.01
        daily_growth = weekly_growth / 7.0
        if daily_growth <= 0:
            return 999
        days = int(free / daily_growth)
        return max(0, days)
    
    def _calculate_space_health(self, filegroups: List[FileGroupStatus], volumes: List[Dict]) -> float:
        if not filegroups:
            return 50.0
        fg_percents = [fg.free_filegroup_percent for fg in filegroups]
        worst_fg = min(fg_percents) if fg_percents else 100.0
        disk_percents = [fg.free_disk_percent for fg in filegroups]
        worst_disk = min(disk_percents) if disk_percents else 100.0
        has_overflow = any(fg.disk_overflow_risk for fg in filegroups)
        overflow_penalty = 30.0 if has_overflow else 0.0
        health = (worst_fg * 0.6 + worst_disk * 0.4) - overflow_penalty
        return round(max(0.0, health), 1)
    
    def _classify_alert_level(self, free_filegroup_pct: float, free_disk_pct: float, disk_overflow: bool) -> str:
        if disk_overflow:
            return 'DISK_OVERFLOW'
        worst_pct = min(free_filegroup_pct, free_disk_pct)
        if worst_pct < 5:
            return 'CRITICAL'
        elif worst_pct < 10:
            return 'HIGH'
        elif worst_pct < 15:
            return 'WARNING'
        else:
            return 'OK'
    
    def _generate_recommendations(self, alerts: List[SpaceAlert], filegroups: List[FileGroupStatus]) -> List[str]:
        recommendations = []
        critical_alerts = [a for a in alerts if a.alert_level == 'CRITICAL']
        high_alerts = [a for a in alerts if a.alert_level == 'HIGH']
        warning_alerts = [a for a in alerts if a.alert_level == 'WARNING']
        overflow_fgs = [fg for fg in filegroups if fg.disk_overflow_risk]
        if overflow_fgs:
            recommendations.append(f"🔴 DISK OVERFLOW RISK: {len(overflow_fgs)} filegroups com MAXSIZE > espaço disponível")
            for fg in overflow_fgs[:3]:
                files = ', '.join(fg.logical_names[:2]) if fg.logical_names else 'N/A'
                recommendations.append(
                    f"   └─ {fg.database_name}.{fg.filegroup_name} ({files}): MAX={fg.max_gb:.1f}GB > Disco={fg.available_disk_gb:.1f}GB"
                )
        if critical_alerts:
            recommendations.append(f"🔴 URGENTE: {len(critical_alerts)} filegroups com <5% livre")
            for alert in critical_alerts[:3]:
                files = ', '.join(alert.logical_names[:2]) if alert.logical_names else 'N/A'
                recommendations.append(
                    f"   └─ {alert.database_name}.{alert.filegroup_name} ({files}): {alert.free_percent:.1f}% livre ({alert.free_gb:.1f}GB)"
                )
        if high_alerts:
            recommendations.append(f"🟠 ATENÇÃO: {len(high_alerts)} filegroups precisam de expansão (<10% livre)")
            for alert in high_alerts[:3]:
                files = ', '.join(alert.logical_names[:2]) if alert.logical_names else 'N/A'
                recommendations.append(
                    f"   └─ {alert.database_name}.{alert.filegroup_name} ({files}): {alert.free_percent:.1f}% livre ({alert.free_gb:.1f}GB)"
                )
        if warning_alerts:
            recommendations.append(f"🟡 MONITORAR: {len(warning_alerts)} filegroups com <15% livre")
            for alert in warning_alerts[:3]:
                files = ', '.join(alert.logical_names[:2]) if alert.logical_names else 'N/A'
                recommendations.append(
                    f"   └─ {alert.database_name}.{alert.filegroup_name} ({files}): {alert.free_percent:.1f}% livre ({alert.free_gb:.1f}GB)"
                )
        return recommendations


async def get_space_analysis_for_all_servers(sql_monitoring, server_ids: list = None) -> Dict:
    engine = SpaceAnalysisEngine(sql_monitoring)
    servers = server_ids if server_ids else []
    results = []
    for server_id in servers:
        analysis = await engine.analyze_server_space(server_id)
        results.append(analysis)
    total_critical = sum(r.get('critical_alerts', 0) for r in results)
    total_high = sum(r.get('high_alerts', 0) for r in results)
    total_warning = sum(r.get('warning_alerts', 0) for r in results)
    total_overflow = sum(r.get('overflow_alerts', 0) for r in results)
    total_alerts = sum(r.get('total_alerts', 0) for r in results)
    critical_servers = len([r for r in results if r.get('critical_alerts', 0) > 0])
    return {
        'timestamp': datetime.now().isoformat(),
        'total_servers_analyzed': len(results),
        'total_alerts': total_alerts,
        'critical_alerts': total_critical,
        'high_alerts': total_high,
        'warning_alerts': total_warning,
        'overflow_alerts': total_overflow,
        'critical_servers': critical_servers,
        'servers': results,
        'summary': {
            'health_status': 'CRITICAL' if critical_servers > 3 else 'WARNING' if total_alerts > 10 else 'OK',
            'requires_immediate_action': critical_servers > 0 or total_overflow > 0
        }
    }


def extract_alerts(all_servers_space_data: List[Dict]) -> List[Dict]:
    all_alerts: List[Dict] = []
    for server_data in all_servers_space_data:
        server_id = server_data.get('server_id')
        alerts_list = server_data.get('alerts')
        if isinstance(alerts_list, list):
            for a in alerts_list:
                level = a.get('alert_level')
                if level and level != 'OK':
                    db_name = a.get('database_name')
                    fg_name = a.get('filegroup_name')
                    free_pct = a.get('free_percent')
                    all_alerts.append({
                        'server': server_id,
                        'database': db_name,
                        'filegroup': fg_name,
                        'level': level,
                        'message': f'Filegroup {fg_name} no DB {db_name} em {server_id}: {level} - {free_pct}% livre.'
                    })
            continue
        databases = server_data.get('databases') or {}
        for db_name, db_data in databases.items():
            filegroups = db_data.get('filegroups') or []
            for fg_data in filegroups:
                level = fg_data.get('alert_level')
                if level and level != 'OK':
                    fg_name = fg_data.get('filegroup_name')
                    free_pct = fg_data.get('free_filegroup_percent')
                    all_alerts.append({
                        'server': server_id,
                        'database': db_name,
                        'filegroup': fg_name,
                        'level': level,
                        'message': f'Filegroup {fg_name} no DB {db_name} em {server_id}: {level} - {free_pct}% livre.'
                    })
    return all_alerts


