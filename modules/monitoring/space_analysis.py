"""
WatcherDB Space Analysis - Capacity Planning Module
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

# Cache curto por servidor p/ analyze_server_space (2026-07-28): a analise percorre
# TODAS as databases (1 query/DB com FILEPROPERTY) -> caro em servers grandes (90+ DBs).
# Revisitas dentro da janela devolvem instantaneo. TTL curto p/ nao mascarar mudancas reais.
_SPACE_ANALYSIS_CACHE = {}          # {server_id: (datetime, result_dict)}
_SPACE_ANALYSIS_CACHE_TTL = 120     # segundos


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
    filegroup_type: str  # 'ROWS', 'LOG', 'OTHER'
    file_count: int
    logical_names: List[str]
    total_gb: float
    max_gb: float
    used_gb: float
    free_gb: float  # Espaço livre no filegroup
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

    # Estados de database que não permitem acesso
    INACCESSIBLE_STATES = {
        1: 'RESTORING',
        2: 'RECOVERING',
        3: 'RECOVERY_PENDING',
        4: 'SUSPECT',
        5: 'EMERGENCY',
        6: 'OFFLINE',
        7: 'COPYING',
        10: 'OFFLINE_SECONDARY'
    }

    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        self.cache_ttl = 300

    async def check_database_state(self, server_id: str, database_name: str) -> Dict:
        """
        Verifica o estado do database antes de tentar acessar.
        Retorna {'accessible': True/False, 'state': 'ONLINE/OFFLINE/...', 'state_desc': '...', 'is_ag_secondary': True/False}
        """
        query = f"""
        SELECT
            d.state,
            d.state_desc,
            d.is_read_only,
            d.user_access,
            d.user_access_desc,
            d.is_in_standby,
            d.replica_id,
            CASE
                WHEN d.state = 0 AND d.is_read_only = 0 AND d.user_access = 0 THEN 1
                WHEN d.state = 0 AND d.is_read_only = 1 THEN 1  -- Read-only mas acessível
                ELSE 0
            END AS is_accessible,
            -- Verificar se é secundário de Always On
            CASE
                WHEN d.replica_id IS NOT NULL THEN
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM sys.dm_hadr_availability_replica_states ars
                            WHERE ars.replica_id = d.replica_id
                              AND ars.role_desc = 'SECONDARY'
                        ) THEN 1
                        ELSE 0
                    END
                ELSE 0
            END AS is_ag_secondary
        FROM sys.databases d
        WHERE d.name = '{database_name}'
        """

        try:
            result = await self.sql_monitoring.execute_query(server_id, query)

            if not result or not isinstance(result, dict):
                return {'accessible': False, 'state': 'UNKNOWN', 'state_desc': 'Não foi possível verificar estado'}

            rows = result.get('rows', [])
            if not rows:
                return {'accessible': False, 'state': 'NOT_FOUND', 'state_desc': 'Database não encontrado'}

            row = rows[0]
            state = int(row.get('state', -1))
            state_desc = str(row.get('state_desc', 'UNKNOWN'))
            is_accessible = bool(row.get('is_accessible', 0))
            is_read_only = bool(row.get('is_read_only', 0))
            is_in_standby = bool(row.get('is_in_standby', 0))
            user_access_desc = str(row.get('user_access_desc', ''))
            is_ag_secondary = bool(row.get('is_ag_secondary', 0))

            # Construir mensagem descritiva
            status_info = state_desc
            if is_ag_secondary:
                status_info += ' (AG Secondary)'
            if is_read_only:
                status_info += ' (Read-Only)'
            if is_in_standby:
                status_info += ' (Standby)'
            if user_access_desc and user_access_desc != 'MULTI_USER':
                status_info += f' ({user_access_desc})'

            return {
                'accessible': is_accessible,
                'state': state_desc,
                'state_code': state,
                'state_desc': status_info,
                'is_read_only': is_read_only,
                'is_in_standby': is_in_standby,
                'is_ag_secondary': is_ag_secondary
            }

        except Exception as e:
            logger.error(f"Erro ao verificar estado do database {database_name} em {server_id}: {e}")
            return {'accessible': False, 'state': 'ERROR', 'state_desc': f'Erro: {str(e)}'}

    async def get_database_files(self, server_id: str, database_name: str) -> List[Dict]:
        """
        Retorna detalhes dos arquivos (logical names) de um database específico
        ✅ CORREÇÃO: Verifica estado do database antes de acessar sys.filegroups
        """
        # Verificar estado do database antes de tentar acessar
        db_state = await self.check_database_state(server_id, database_name)

        if not db_state.get('accessible', False):
            # Retornar informação sobre o estado do database ao invés de erro
            state = db_state.get('state', 'UNKNOWN')
            state_desc = db_state.get('state_desc', 'Estado desconhecido')

            # Tentar obter informações básicas de sys.master_files (não requer acesso ao DB)
            basic_query = f"""
            SELECT
                mf.name AS LogicalName,
                mf.physical_name AS PhysicalName,
                'N/A' AS FileGroupName,
                mf.type_desc AS FileType,
                CAST(mf.size * 8.0 / 1024 AS DECIMAL(18,2)) AS CurrentSizeMB,
                CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS CurrentSizeGB,
                0 AS MaxSizeMB,
                0 AS MaxSizeGB,
                'N/A' AS MaxSizeFormatted,
                'N/A' AS GrowthIncrement,
                'N/A' AS Volume,
                0 AS DiskAvailableGB,
                '{state}' AS DatabaseState,
                '{state_desc}' AS DatabaseStateDesc
            FROM sys.master_files mf
            WHERE mf.database_id = DB_ID('{database_name}')
            ORDER BY mf.type, mf.name;
            """

            try:
                result = await self.sql_monitoring.execute_query(server_id, basic_query)
                if result and isinstance(result, dict):
                    rows = result.get('rows', [])
                    files = []
                    for row in rows:
                        file_info = {
                            'logical_name': str(row.get('LogicalName', '')),
                            'physical_name': str(row.get('PhysicalName', '')),
                            'filegroup_name': 'N/A',
                            'file_type': str(row.get('FileType', '')),
                            'current_size_mb': to_float(row.get('CurrentSizeMB', 0)),
                            'current_size_gb': to_float(row.get('CurrentSizeGB', 0)),
                            'max_size_mb': 0,
                            'max_size_gb': 0,
                            'max_size_formatted': 'N/A',
                            'growth_increment': 'N/A',
                            'volume': 'N/A',
                            'disk_available_gb': 0,
                            'database_state': state,
                            'database_state_desc': state_desc,
                            'is_accessible': False,
                            'diagnostic_link': f'/api/v1/diagnostics/database-state/{server_id}/{database_name}',
                            'sql_diagnostic': f"-- Verificar estado do database\nSELECT name, state_desc, user_access_desc FROM sys.databases WHERE name = '{database_name}';"
                        }
                        files.append(file_info)
                    logger.warning(f"Database {database_name} em {server_id} está {state_desc}. Retornando dados básicos.")
                    return files
            except Exception:
                pass

            # Se nem os dados básicos funcionaram, retornar lista com info de status
            return [{
                'logical_name': 'N/A',
                'physical_name': 'N/A',
                'filegroup_name': 'N/A',
                'file_type': 'N/A',
                'current_size_mb': 0,
                'current_size_gb': 0,
                'max_size_mb': 0,
                'max_size_gb': 0,
                'max_size_formatted': 'N/A',
                'growth_increment': 'N/A',
                'volume': 'N/A',
                'disk_available_gb': 0,
                'database_state': state,
                'database_state_desc': state_desc,
                'is_accessible': False,
                'error_message': f'Database está {state_desc}',
                'diagnostic_link': f'/api/v1/diagnostics/database-state/{server_id}/{database_name}',
                'sql_diagnostic': f"-- Verificar estado do database\nSELECT name, state_desc, user_access_desc FROM sys.databases WHERE name = '{database_name}';"
            }]

        # Verificar se é secundário de AG
        is_ag_secondary = db_state.get('is_ag_secondary', False)

        # Query simplificada para secundários de AG (sem JOIN com database)
        # Usa subquery para buscar nome real do filegroup
        query_ag_secondary = f"""
        SELECT
            mf.name AS LogicalName,
            mf.physical_name AS PhysicalName,
            CASE
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg_info.filegroup_name, 'PRIMARY')
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
            mf.growth AS GrowthRaw,
            mf.is_percent_growth AS IsPercentGrowth,
            vs.volume_mount_point AS Volume,
            CAST(vs.available_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(10,2)) AS DiskAvailableGB
        FROM sys.master_files mf
        CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
        OUTER APPLY (
            SELECT TOP 1 fg.name as filegroup_name
            FROM sys.filegroups fg WITH(NOLOCK)
            WHERE fg.data_space_id = mf.data_space_id
            AND mf.type = 0
        ) fg_info
        WHERE mf.database_id = DB_ID('{database_name}')
          AND mf.state = 0
        ORDER BY mf.type, mf.data_space_id, mf.name;
        """

        # Database está acessível - executar query completa
        # Item 4 (2026-07-28): reescrita p/ USE [db] + sys.database_files, obtendo
        # Used REAL por ficheiro (FILEPROPERTY SpaceUsed) + growth raw (GrowthRaw/
        # IsPercentGrowth p/ Status FULL/MAXED do datafile) + volume stats.
        # query_ag_secondary abaixo NAO pode USE (secundario nao legivel) -> sem Used.
        query = f"""
        USE [{database_name}];
        SELECT
            df.name AS LogicalName,
            df.physical_name AS PhysicalName,
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            df.type_desc AS FileType,
            CAST(df.size * 8.0 / 1024 AS DECIMAL(18,2)) AS CurrentSizeMB,
            CAST(df.size * 8.0 / 1024 / 1024 AS DECIMAL(18,2)) AS CurrentSizeGB,
            CAST(FILEPROPERTY(df.name, 'SpaceUsed') * 8.0 / 1024 AS DECIMAL(18,2)) AS UsedSizeMB,
            CAST(
                CASE
                    WHEN df.max_size = -1 THEN -1
                    WHEN df.max_size = 268435456 THEN 2097152
                    ELSE df.max_size * 8.0 / 1024
                END
                AS DECIMAL(18,2)
            ) AS MaxSizeMB,
            CAST(
                CASE
                    WHEN df.max_size = -1 THEN -1
                    WHEN df.max_size = 268435456 THEN 2048
                    ELSE df.max_size * 8.0 / 1024 / 1024
                END
                AS DECIMAL(18,2)
            ) AS MaxSizeGB,
            CASE
                WHEN df.max_size = -1 THEN 'Unlimited'
                WHEN df.max_size = 268435456 THEN '2TB (Default)'
                ELSE CAST(df.max_size * 8.0 / 1024 / 1024 AS VARCHAR(20)) + ' GB'
            END AS MaxSizeFormatted,
            CASE
                WHEN df.is_percent_growth = 1
                THEN CAST(df.growth AS VARCHAR(10)) + '%'
                ELSE CAST(df.growth * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
            END AS GrowthIncrement,
            df.growth AS GrowthRaw,
            df.is_percent_growth AS IsPercentGrowth,
            vs.volume_mount_point AS Volume,
            CAST(vs.available_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(10,2)) AS DiskAvailableGB
        FROM sys.database_files df
        LEFT JOIN sys.filegroups fg
            ON df.data_space_id = fg.data_space_id
        CROSS APPLY sys.dm_os_volume_stats(DB_ID(), df.file_id) vs
        WHERE df.state = 0
        ORDER BY df.type, fg.name, df.name;
        """

        try:
            # Para secundários de AG, usar query simplificada primeiro
            if is_ag_secondary:
                logger.info(f"Database {database_name} é secundário de AG - usando query simplificada para files")
                result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)
            else:
                result = await self.sql_monitoring.execute_query(server_id, query)

            if not result or not isinstance(result, dict):
                # Fallback para query simplificada
                logger.warning(f"Query de files falhou para {database_name} - tentando query simplificada")
                result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)

            if not result or not isinstance(result, dict):
                return []

            rows = result.get('rows', [])
            if not rows:
                # Fallback para query simplificada
                logger.warning(f"Query de files retornou vazio para {database_name} - tentando query simplificada")
                result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)
                if result and isinstance(result, dict):
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
                    # Item 4: Used real por ficheiro; None em AG secondary (sem USE) -> UI mostra "—"
                    'used_size_mb': (to_float(row.get('UsedSizeMB')) if row.get('UsedSizeMB') is not None else None),
                    'max_size_mb': to_float(row.get('MaxSizeMB', 0)),
                    'max_size_gb': to_float(row.get('MaxSizeGB', 0)),
                    'max_size_formatted': str(row.get('MaxSizeFormatted', '')),
                    'growth_increment': str(row.get('GrowthIncrement', '')),
                    # Item 3: growth raw (>0 => pode crescer) p/ Status FULL/MAXED
                    'growth_raw': to_float(row.get('GrowthRaw', 0)),
                    'is_percent_growth': bool(row.get('IsPercentGrowth', 0)),
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
        ✅ CORREÇÃO: Verifica estado do database antes de acessar sys.filegroups
        """
        # Verificar estado do database antes de tentar acessar
        db_state = await self.check_database_state(server_id, database_name)

        if not db_state.get('accessible', False):
            # Retornar informação sobre o estado do database ao invés de erro
            state = db_state.get('state', 'UNKNOWN')
            state_desc = db_state.get('state_desc', 'Estado desconhecido')
            state_code = db_state.get('state_code', -1)

            # Tentar obter informações básicas de sys.master_files (não requer acesso ao DB)
            basic_query = f"""
            SELECT
                CASE
                    WHEN mf.type = 1 THEN 'LOG'
                    ELSE 'PRIMARY'
                END AS FileGroupName,
                CASE
                    WHEN mf.type = 1 THEN 'LOG'
                    ELSE 'ROWS'
                END AS FileGroupType,
                COUNT(DISTINCT mf.file_id) AS FileCount,
                CAST(SUM(mf.size * 8.0 / 1024 / 1024) AS DECIMAL(18,2)) AS TotalGB,
                0 AS MaxGB,
                0 AS UsedGB
            FROM sys.master_files mf
            WHERE mf.database_id = DB_ID('{database_name}')
            GROUP BY
                CASE
                    WHEN mf.type = 1 THEN 'LOG'
                    ELSE 'PRIMARY'
                END,
                CASE
                    WHEN mf.type = 1 THEN 'LOG'
                    ELSE 'ROWS'
                END
            ORDER BY FileGroupName;
            """

            try:
                result = await self.sql_monitoring.execute_query(server_id, basic_query)
                if result and isinstance(result, dict):
                    rows = result.get('rows', [])
                    filegroups = []
                    for row in rows:
                        total_gb = to_float(row.get('TotalGB', 0))
                        fg_info = {
                            'filegroup_name': str(row.get('FileGroupName', 'N/A')),
                            'filegroup_type': str(row.get('FileGroupType', 'N/A')),
                            'file_count': int(to_float(row.get('FileCount', 0))),
                            'total_gb': round(total_gb, 2),
                            'max_gb': 0,
                            'used_gb': 0,
                            'free_gb': 0,
                            'free_percent': 0,
                            'total_mb': round(total_gb * 1024, 2),
                            'max_mb': 0,
                            'used_mb': 0,
                            'free_mb': 0,
                            'database_state': state,
                            'database_state_desc': state_desc,
                            'database_state_code': state_code,
                            'is_accessible': False,
                            'diagnostic_link': f'/api/v1/diagnostics/database-state/{server_id}/{database_name}',
                            'sql_diagnostic': f"-- Verificar estado do database\nSELECT name, state_desc, user_access_desc FROM sys.databases WHERE name = '{database_name}';"
                        }
                        filegroups.append(fg_info)
                    logger.warning(f"Database {database_name} em {server_id} está {state_desc}. Retornando dados básicos de filegroups.")
                    return filegroups
            except Exception as e:
                logger.error(f"Erro ao obter dados básicos de filegroups para {database_name}: {e}")

            # Se nem os dados básicos funcionaram, retornar lista com info de status
            return [{
                'filegroup_name': 'N/A',
                'filegroup_type': 'N/A',
                'file_count': 0,
                'total_gb': 0,
                'max_gb': 0,
                'used_gb': 0,
                'free_gb': 0,
                'free_percent': 0,
                'total_mb': 0,
                'max_mb': 0,
                'used_mb': 0,
                'free_mb': 0,
                'database_state': state,
                'database_state_desc': state_desc,
                'database_state_code': state_code,
                'is_accessible': False,
                'error_message': f'Database está {state_desc}',
                'diagnostic_link': f'/api/v1/diagnostics/database-state/{server_id}/{database_name}',
                'sql_diagnostic': f"-- Verificar estado do database\nSELECT name, state_desc, user_access_desc FROM sys.databases WHERE name = '{database_name}';"
            }]

        # Verificar se é secundário de AG - usar query simplificada
        is_ag_secondary = db_state.get('is_ag_secondary', False)

        # Query para secundários de AG - usa apenas sys.master_files (sem JOIN com database)
        # Usa OUTER APPLY para buscar nome real do filegroup em sys.filegroups
        query_ag_secondary = f"""
        SELECT
            CASE
                WHEN mf.type = 1 THEN 'LOG'
                ELSE ISNULL(fg_info.filegroup_name, 'PRIMARY')
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
        OUTER APPLY (
            SELECT TOP 1 fg.name as filegroup_name
            FROM sys.filegroups fg WITH(NOLOCK)
            WHERE fg.data_space_id = mf.data_space_id
            AND mf.type = 0
        ) fg_info
        WHERE mf.database_id = DB_ID('{database_name}')
          AND mf.state = 0
        ORDER BY mf.type, mf.data_space_id, mf.file_id;
        """

        # Database está acessível - executar queries normalmente
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
        -- Query CORRETA usando FILEPROPERTY para valores precisos
        -- Inclui calculo correto de percentuais
        SELECT
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END AS FileGroupType,
            COUNT(DISTINCT df.file_id) AS FileCount,
            CAST(SUM(df.size) / 128.0 / 1024.0 AS DECIMAL(18,2)) AS TotalGB,
            CAST(SUM(
                CASE
                    WHEN df.max_size = -1 THEN 999999
                    WHEN df.max_size = 268435456 THEN 2048
                    ELSE df.max_size / 128.0 / 1024.0
                END
            ) AS DECIMAL(18,2)) AS MaxGB,
            CAST(SUM(FILEPROPERTY(df.name, 'SpaceUsed')) / 128.0 / 1024.0 AS DECIMAL(18,2)) AS UsedGB,
            -- FreeGB = TotalGB - UsedGB (espaco livre no tamanho atual)
            CAST((SUM(df.size) - SUM(FILEPROPERTY(df.name, 'SpaceUsed'))) / 128.0 / 1024.0 AS DECIMAL(18,2)) AS FreeGB,
            -- UsedPct = (UsedGB / TotalGB) * 100
            CAST(
                CASE
                    WHEN SUM(df.size) > 0
                    THEN (SUM(FILEPROPERTY(df.name, 'SpaceUsed')) * 100.0) / SUM(df.size)
                    ELSE 0
                END AS DECIMAL(5,2)
            ) AS UsedPct,
            -- FreePct = (FreeGB / TotalGB) * 100
            CAST(
                CASE
                    WHEN SUM(df.size) > 0
                    THEN ((SUM(df.size) - SUM(FILEPROPERTY(df.name, 'SpaceUsed'))) * 100.0) / SUM(df.size)
                    ELSE 0
                END AS DECIMAL(5,2)
            ) AS FreePct,
            -- Item 2 (2026-07-28): ingredientes p/ capacidade/livre EFETIVOS (matriz growth)
            --   growth ativo + max finito -> EffCap = Sigma max ; livre = EffCap - Used
            --   growth=0                  -> EffCap = Sigma alocado (max e' letra morta)
            --   unlimited + growth ativo  -> disk-bound (UnlimitedGrowableFiles>0 => UI mantem alocado + tooltip)
            SUM(CASE WHEN df.growth > 0 THEN 1 ELSE 0 END) AS GrowthEnabledFiles,
            SUM(CASE WHEN df.growth > 0 AND df.max_size = -1 THEN 1 ELSE 0 END) AS UnlimitedGrowableFiles,
            CAST(SUM(
                CASE
                    WHEN df.growth = 0 THEN df.size
                    WHEN df.max_size = -1 THEN df.size
                    WHEN df.max_size = 268435456 THEN 268435456
                    ELSE df.max_size
                END
            ) / 128.0 / 1024.0 AS DECIMAL(18,2)) AS EffCapGB,
            -- EffCapMB: precisao MB (evita double-rounding GB->MB no display do Free MB)
            CAST(SUM(
                CASE
                    WHEN df.growth = 0 THEN df.size
                    WHEN df.max_size = -1 THEN df.size
                    WHEN df.max_size = 268435456 THEN 268435456
                    ELSE df.max_size
                END
            ) / 128.0 AS DECIMAL(20,2)) AS EffCapMB
        FROM sys.database_files df
        LEFT JOIN sys.filegroups fg ON df.data_space_id = fg.data_space_id
        WHERE df.type IN (0, 1)
          AND df.state = 0
        GROUP BY
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END,
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END
        ORDER BY FileGroupName;
        """

        query_por_arquivo = f"""
        USE [{database_name}];
        -- Query corrigida usando FILEPROPERTY corretamente
        SELECT
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE ISNULL(fg.name, 'PRIMARY')
            END AS FileGroupName,
            CASE
                WHEN df.type = 1 THEN 'LOG'
                ELSE 'ROWS'
            END AS FileGroupType,
            df.file_id AS FileId,
            df.name AS LogicalName,
            CAST(df.size / 128.0 / 1024.0 AS DECIMAL(18,2)) AS TotalGB,
            CAST(
                CASE
                    WHEN df.max_size = -1 THEN 999999
                    WHEN df.max_size = 268435456 THEN 2048
                    ELSE df.max_size / 128.0 / 1024.0
                END
            AS DECIMAL(18,2)) AS MaxGB,
            CAST(FILEPROPERTY(df.name, 'SpaceUsed') / 128.0 / 1024.0 AS DECIMAL(18,2)) AS UsedGB
        FROM sys.database_files df
        LEFT JOIN sys.filegroups fg
            ON df.data_space_id = fg.data_space_id
        WHERE df.type IN (0, 1)
          AND df.state = 0
        ORDER BY FileGroupName, df.file_id;
        """

        try:
            # Para secundários de AG, usar query simplificada primeiro
            if is_ag_secondary:
                logger.info(f"Database {database_name} é secundário de AG - usando query simplificada")
                result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)
                if result and result.get('rows'):
                    rows = result.get('rows', [])
                    return self._aggregate_filegroup_rows(rows, is_ag_secondary=True)

            # Tentar query precisa primeiro (com USE e FILEPROPERTY)
            try:
                result = await self.sql_monitoring.execute_query(server_id, query_precisa)
                if result and result.get('rows'):
                    rows = result.get('rows', [])
                    # Verificar se FILEPROPERTY retornou valores válidos (Used != Total)
                    # Em secundários, FILEPROPERTY pode retornar o tamanho total ao invés do usado
                    first_row = rows[0] if rows else {}
                    total_check = to_float(first_row.get('TotalGB', 0))
                    used_check = to_float(first_row.get('UsedGB', 0))

                    # Se Used == Total (ou muito próximo), provavelmente é secundário de AG não detectado
                    if total_check > 0 and abs(total_check - used_check) < 0.01:
                        logger.warning(f"Database {database_name}: FILEPROPERTY retornou Used=Total, provavelmente AG secondary não detectado - usando fallback")
                        # Usar query simplificada
                        result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)
                        if result and result.get('rows'):
                            return self._aggregate_filegroup_rows(result.get('rows', []), is_ag_secondary=True)
                    else:
                        return self._process_filegroup_rows(rows)
            except Exception as e:
                logger.debug(f"Query precisa falhou para {database_name}: {e}")

            # Tentar query com JOIN no database
            result = await self.sql_monitoring.execute_query(server_id, query_por_arquivo)

            if not result or not isinstance(result, dict):
                # Fallback: tentar query simplificada (sem JOIN)
                logger.warning(f"Query com JOIN falhou para {database_name} - tentando query simplificada")
                result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)
                if result and result.get('rows'):
                    return self._aggregate_filegroup_rows(result.get('rows', []), is_ag_secondary=False)
                return []

            rows = result.get('rows', [])
            if not rows:
                # Fallback: tentar query simplificada (sem JOIN)
                logger.warning(f"Query com JOIN retornou vazio para {database_name} - tentando query simplificada")
                result = await self.sql_monitoring.execute_query(server_id, query_ag_secondary)
                if result and result.get('rows'):
                    return self._aggregate_filegroup_rows(result.get('rows', []), is_ag_secondary=False)
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
                max_gb = fg_data['max_gb']
                free_gb = total_gb - used_gb
                
                # CORREÇÃO: O free_percent deve ser baseado no tamanho atual (total_gb), não no maxsize
                # free_percent = (free_gb / total_gb) * 100 = quanto espaço livre há DENTRO do filegroup atual
                # Isso representa o espaço realmente disponível nos arquivos alocados
                if total_gb > 0:
                    free_percent = round(safe_percentage(free_gb, total_gb), 2)
                else:
                    free_percent = 0.0
                
                fg_info = {
                    'filegroup_name': fg_data['filegroup_name'],
                    'filegroup_type': fg_data['filegroup_type'],
                    'file_count': fg_data['file_count'],
                    'total_gb': round(total_gb, 2),
                    'max_gb': round(max_gb, 2),
                    'used_gb': round(used_gb, 2),
                    'free_gb': round(free_gb, 2),
                    'free_percent': free_percent,
                    # Adicionar valores em MB para compatibilidade com frontend
                    'total_mb': round(total_gb * 1024, 2),
                    'max_mb': round(max_gb * 1024, 2),
                    'used_mb': round(used_gb * 1024, 2),
                    'free_mb': round(free_gb * 1024, 2)
                }
                filegroups.append(fg_info)
            
            return filegroups
            
        except Exception:
            return []
    
    def _process_filegroup_rows(self, rows: List[Dict]) -> List[Dict]:
        """Processa linhas de filegroups retornadas pela query precisa"""
        filegroups = []

        for row in rows:
            total_gb = to_float(row.get('TotalGB', 0))
            used_gb = to_float(row.get('UsedGB', 0))
            max_gb = to_float(row.get('MaxGB', 0))

            # Usar FreeGB da query se disponível, senão calcular
            free_gb = to_float(row.get('FreeGB', 0))
            if free_gb == 0 and total_gb > 0:
                free_gb = total_gb - used_gb

            # Usar FreePct da query se disponível (valor preciso calculado no SQL)
            # Senão, calcular localmente
            free_pct = to_float(row.get('FreePct', 0))
            if free_pct == 0 and total_gb > 0:
                free_pct = round(safe_percentage(free_gb, total_gb), 2)

            # UsedPct da query
            used_pct = to_float(row.get('UsedPct', 0))
            if used_pct == 0 and total_gb > 0:
                used_pct = round(safe_percentage(used_gb, total_gb), 2)

            fg_info = {
                'filegroup_name': str(row.get('FileGroupName', '')),
                'filegroup_type': str(row.get('FileGroupType', '')),
                'file_count': int(to_float(row.get('FileCount', 0))),
                'total_gb': round(total_gb, 2),
                'max_gb': round(max_gb, 2),
                'used_gb': round(used_gb, 2),
                'free_gb': round(free_gb, 2),
                'free_percent': round(free_pct, 2),
                'pct_used': round(used_pct, 2),
                # Valores em MB para compatibilidade
                'total_mb': round(total_gb * 1024, 2),
                'max_mb': round(max_gb * 1024, 2),
                'used_mb': round(used_gb * 1024, 2),
                'free_mb': round(free_gb * 1024, 2),
                # Item 2: capacidade/livre EFETIVOS (matriz growth). Frontend usa
                # eff_cap quando unlimited_growable_files == 0 (senao disk-bound).
                'growth_enabled_files': int(to_float(row.get('GrowthEnabledFiles', 0))),
                'unlimited_growable_files': int(to_float(row.get('UnlimitedGrowableFiles', 0))),
                'eff_cap_gb': round(to_float(row.get('EffCapGB', 0)), 2),
                # eff_cap_mb da coluna MB-precisa (fallback: GB*1024 se ausente)
                'eff_cap_mb': round(to_float(row.get('EffCapMB')), 2) if row.get('EffCapMB') is not None else round(to_float(row.get('EffCapGB', 0)) * 1024, 2),
            }
            filegroups.append(fg_info)

        return filegroups

    def _aggregate_filegroup_rows(self, rows: List[Dict], is_ag_secondary: bool = False) -> List[Dict]:
        """
        Agrega linhas de arquivos individuais em filegroups.
        Usado especialmente para secundários de AG onde não podemos acessar sys.filegroups.
        """
        filegroups_dict = {}

        for row in rows:
            fg_name = str(row.get('FileGroupName', 'UNKNOWN'))
            total_gb = to_float(row.get('TotalGB', 0))
            used_gb = to_float(row.get('UsedGB', 0))
            max_gb = to_float(row.get('MaxGB', 0))

            if fg_name not in filegroups_dict:
                filegroups_dict[fg_name] = {
                    'filegroup_name': fg_name,
                    'filegroup_type': str(row.get('FileGroupType', 'ROWS')),
                    'file_count': 0,
                    'total_gb': 0.0,
                    'max_gb': 0.0,
                    'used_gb': 0.0,
                    'logical_names': []
                }

            filegroups_dict[fg_name]['file_count'] += 1
            filegroups_dict[fg_name]['total_gb'] += total_gb
            filegroups_dict[fg_name]['max_gb'] += max_gb
            filegroups_dict[fg_name]['used_gb'] += used_gb

            logical_name = row.get('LogicalName', '')
            if logical_name:
                filegroups_dict[fg_name]['logical_names'].append(str(logical_name))

        filegroups = []
        for fg_name, fg_data in filegroups_dict.items():
            total_gb = fg_data['total_gb']
            used_gb = fg_data['used_gb']
            max_gb = fg_data['max_gb']
            free_gb = total_gb - used_gb

            # CORREÇÃO: O free_percent deve ser baseado no tamanho atual (total_gb), não no maxsize
            # free_percent = (free_gb / total_gb) * 100 = quanto espaço livre há DENTRO do filegroup atual
            if total_gb > 0:
                free_percent = round(safe_percentage(free_gb, total_gb), 2)
            else:
                free_percent = 0.0

            fg_info = {
                'filegroup_name': fg_data['filegroup_name'],
                'filegroup_type': fg_data['filegroup_type'],
                'file_count': fg_data['file_count'],
                'total_gb': round(total_gb, 2),
                'max_gb': round(max_gb, 2),
                'used_gb': round(used_gb, 2),
                'free_gb': round(free_gb, 2),
                'free_percent': free_percent,
                'total_mb': round(total_gb * 1024, 2),
                'max_mb': round(max_gb * 1024, 2),
                'used_mb': round(used_gb * 1024, 2),
                'free_mb': round(free_gb * 1024, 2),
                'logical_names': fg_data['logical_names']
            }

            # Adicionar flag de AG secondary
            if is_ag_secondary:
                fg_info['is_ag_secondary'] = True
                fg_info['note'] = 'Dados obtidos de sys.master_files (nó secundário de AG)'

            filegroups.append(fg_info)

        return filegroups
    
    async def analyze_server_space(self, server_id: str) -> Dict:
        # Cache curto por servidor: revisitas dentro de _SPACE_ANALYSIS_CACHE_TTL
        # devolvem instantaneo (o load frio percorre todas as DBs, e' caro).
        _cached = _SPACE_ANALYSIS_CACHE.get(server_id)
        if _cached and (datetime.now() - _cached[0]).total_seconds() < _SPACE_ANALYSIS_CACHE_TTL:
            _r = dict(_cached[1])
            _r['cached'] = True
            return _r
        try:
            # CORREÇÃO: Iterar por cada database para usar FILEPROPERTY (valores REAIS)
            # Primeiro, obter lista de databases
            databases_query = """
            SELECT name FROM sys.databases
            WHERE database_id > 4  -- Exclui master, model, msdb, tempdb
              AND state = 0  -- Apenas ONLINE
            ORDER BY name
            """
            db_result = await self.sql_monitoring.execute_query(server_id, databases_query)
            databases = []
            if db_result and isinstance(db_result, dict):
                databases = [row.get('name') for row in db_result.get('rows', []) if row.get('name')]

            # Buscar volumes PRIMEIRO para ter dados reais de disco disponíveis
            volumes_data = await self._get_volumes_status(server_id)

            # Criar lookup de volumes e calcular pior percentual de disco livre
            volumes_lookup = {}
            worst_disk_free_pct = 100.0
            worst_disk_available_gb = 0.0
            for vol in volumes_data:
                drive = vol.get('Drive', vol.get('drive', '')).upper().rstrip('\\')
                free_pct = vol.get('FreePercent', vol.get('free_percent', 0))
                free_gb = vol.get('FreeGB', vol.get('free_gb', 0))
                total_gb_vol = vol.get('TotalGB', vol.get('total_gb', 0))
                volumes_lookup[drive] = {
                    'free_pct': free_pct,
                    'free_gb': free_gb,
                    'total_gb': total_gb_vol
                }
                if free_pct < worst_disk_free_pct:
                    worst_disk_free_pct = free_pct
                    worst_disk_available_gb = free_gb

            # Buscar filegroups de cada database em PARALELO (2026-07-28: 5->12
            # p/ acelerar o load frio em servers grandes; pool tem 30 ligacoes,
            # deixa 18 de folga p/ o resto). Se ainda lento: estado-em-1-query.
            all_filegroups = []
            BATCH_SIZE = 12

            async def _fetch_db_filegroups(db_name):
                """Busca filegroups de uma database e retorna lista de FileGroupStatus"""
                fgs = []
                db_filegroups = await self.get_database_filegroups(server_id, db_name)
                for fg in db_filegroups:
                    fg['database_name'] = db_name
                    fg_volume = fg.get('volume', 'N/A').upper().rstrip('\\')
                    if fg_volume and fg_volume != 'N/A' and fg_volume in volumes_lookup:
                        disk_free_pct = volumes_lookup[fg_volume]['free_pct']
                        disk_available_gb = volumes_lookup[fg_volume]['free_gb']
                    elif volumes_lookup:
                        disk_free_pct = worst_disk_free_pct
                        disk_available_gb = worst_disk_available_gb
                    else:
                        disk_free_pct = 100.0
                        disk_available_gb = 0.0

                    max_gb = fg.get('max_gb', 0)
                    total_gb_fg = fg.get('total_gb', 0)
                    potential_growth = max_gb - total_gb_fg if max_gb > 0 and max_gb < 999999 else 0
                    disk_overflow = (potential_growth > disk_available_gb) if (potential_growth > 0 and disk_available_gb > 0) else False

                    fg_status = FileGroupStatus(
                        database_name=db_name,
                        filegroup_name=fg.get('filegroup_name', 'UNKNOWN'),
                        filegroup_type=fg.get('filegroup_type', 'ROWS'),
                        file_count=fg.get('file_count', 0),
                        logical_names=fg.get('logical_names', []),
                        total_gb=fg.get('total_gb', 0),
                        max_gb=max_gb,
                        used_gb=fg.get('used_gb', 0),
                        free_gb=fg.get('free_gb', 0),
                        free_filegroup_percent=fg.get('free_percent', 0),
                        free_disk_percent=disk_free_pct,
                        available_filegroup_gb=fg.get('free_gb', 0),
                        available_disk_gb=disk_available_gb,
                        volume=fg.get('volume', 'N/A'),
                        volume_logical_name='',
                        alert_level=self._classify_alert_level(fg.get('free_percent', 0), disk_free_pct, disk_overflow, max_gb),
                        disk_overflow_risk=disk_overflow
                    )
                    fgs.append(fg_status)
                return fgs

            for i in range(0, len(databases), BATCH_SIZE):
                batch = databases[i:i + BATCH_SIZE]
                batch_results = await asyncio.gather(
                    *[_fetch_db_filegroups(db) for db in batch],
                    return_exceptions=True
                )
                for j, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.warning(f"Erro ao obter filegroups de {batch[j]}: {result}")
                        continue
                    all_filegroups.extend(result)

            filegroups_data = all_filegroups
            alerts = self._generate_space_alerts(filegroups_data)
            space_health_score = self._calculate_space_health(filegroups_data, volumes_data)

            critical_alerts = [a for a in alerts if a.alert_level == 'CRITICAL']
            high_alerts = [a for a in alerts if a.alert_level == 'HIGH']
            warning_alerts = [a for a in alerts if a.alert_level == 'WARNING']
            overflow_alerts = [a for a in alerts if a.alert_level == 'DISK_OVERFLOW']

            result = {
                'server_id': server_id,
                'timestamp': datetime.now().isoformat(),
                'space_health_score': space_health_score,
                'total_alerts': len(alerts),
                'critical_alerts': len(critical_alerts),
                'high_alerts': len(high_alerts),
                'warning_alerts': len(warning_alerts),
                'overflow_alerts': len(overflow_alerts),
                'filegroups': [
                    {
                        **asdict(fg),
                        # Aliases de compatibilidade para o frontend JavaScript
                        'free_percent': fg.free_filegroup_percent,
                        'disk_free_pct': fg.free_disk_percent,
                        'pct_used': round(100 - fg.free_filegroup_percent, 2),
                    }
                    for fg in filegroups_data
                ],
                'volumes': volumes_data,
                'alerts': [asdict(a) for a in alerts],
                'recommendations': self._generate_recommendations(alerts, filegroups_data)
            }
            _SPACE_ANALYSIS_CACHE[server_id] = (datetime.now(), result)
            return result
        except Exception as e:
            logger.error(f"Erro em analyze_server_space: {e}", exc_info=True)
            return {'error': 'analysis-failed', 'server_id': server_id}
    
    async def _get_filegroups_detailed(self, server_id: str) -> List[FileGroupStatus]:
        # Query original restaurada - usa sys.master_files com estimativa de 75%
        # Nota: FILEPROPERTY só funciona no contexto do database específico
        # No contexto do master, usamos estimativa (75% do tamanho alocado)
        # Agrupamos por data_space_id para separar filegroups diferentes
        query = """
WITH FileData AS (
    SELECT
        d.name AS database_name,
        mf.database_id,
        mf.type,
        mf.data_space_id,
        mf.file_id,
        mf.name AS logical_name,
        mf.size,
        mf.max_size,
        -- Estimativa: 75% do tamanho alocado está em uso
        -- FILEPROPERTY não funciona no contexto do master para outros databases
        CAST(mf.size * 0.75 AS BIGINT) AS spaceused,
        vs.volume_mount_point,
        vs.total_bytes,
        vs.available_bytes,
        -- Buscar nome real do filegroup
        fg_info.filegroup_name
    FROM sys.databases d
    JOIN sys.master_files mf ON d.database_id = mf.database_id
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    OUTER APPLY (
        SELECT TOP 1 fg.name as filegroup_name
        FROM sys.filegroups fg WITH(NOLOCK)
        WHERE fg.data_space_id = mf.data_space_id
        AND mf.type = 0
    ) fg_info
    WHERE (d.database_id > 4 OR d.database_id = 2)  -- Inclui TempDB (database_id=2)
      AND mf.type IN (0,1)
      AND mf.state = 0
      AND d.state = 0
)
SELECT
    fd.database_name AS DATABASENAME,
    -- Filegroup name: LOG para logs, ou usa nome real do filegroup
    CASE
        WHEN fd.type = 1 THEN 'LOG'
        ELSE ISNULL(fd.filegroup_name, 'PRIMARY')
    END AS FILEGROUPNAME,
    CASE
        WHEN fd.type = 1 THEN 'LOG'
        WHEN fd.type = 0 THEN 'ROWS'
        ELSE 'OTHER'
    END AS FILETYPE,
    fd.data_space_id AS DATA_SPACE_ID,
    COUNT(DISTINCT fd.file_id) AS NUM_DATAFILES,
    STUFF((
        SELECT ', ' + fd2.logical_name
        FROM FileData fd2
        WHERE fd2.database_id = fd.database_id
          AND fd2.type = fd.type
          AND fd2.data_space_id = fd.data_space_id
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
    -- Calcular FreeGB e percentuais
    CAST((SUM(fd.size) - SUM(fd.spaceused)) * 8.0 / 1024 / 1024 AS DECIMAL(20,2)) AS FREEGB,
    CAST(
        CASE WHEN SUM(fd.size) > 0
        THEN (SUM(fd.spaceused) * 100.0) / SUM(fd.size)
        ELSE 0 END AS DECIMAL(5,2)
    ) AS USEDPCT,
    CAST(
        CASE WHEN SUM(fd.size) > 0
        THEN ((SUM(fd.size) - SUM(fd.spaceused)) * 100.0) / SUM(fd.size)
        ELSE 0 END AS DECIMAL(5,2)
    ) AS FREEPCT,
    fd.volume_mount_point AS VOLMOUNTPOINT,
    CAST(MIN(fd.total_bytes) / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(20,2)) AS DISKTOTALGB,
    CAST(MIN(fd.available_bytes) / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(20,2)) AS DISKAVAILABLEGB
FROM FileData fd
GROUP BY fd.database_name, fd.database_id, fd.type, fd.data_space_id, fd.volume_mount_point, fd.filegroup_name
ORDER BY fd.database_name, fd.type, fd.data_space_id;
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

                # Usar FreeGB e FreePct da query se disponíveis
                free_gb = to_float(row.get('FREEGB', 0))
                if free_gb == 0 and total_gb > 0:
                    free_gb = total_gb - used_gb

                # Usar FreePct da query (valor preciso)
                free_pct = to_float(row.get('FREEPCT', 0))
                if free_pct == 0 and total_gb > 0:
                    free_pct = safe_percentage(free_gb, total_gb)

                # Para alertas, calcular espaço disponível até o maxsize (se definido)
                if max_gb > 0 and max_gb < 999999:
                    available_filegroup_gb = max_gb - used_gb
                else:
                    available_filegroup_gb = free_gb

                potential_growth = max_gb - total_gb if max_gb > 0 and max_gb < 999999 else 0
                disk_overflow = (potential_growth > disk_available_gb) if (potential_growth > 0 and disk_available_gb > 0) else False
                disk_free_pct = safe_percentage(disk_available_gb, disk_total_gb)

                # Usar FILEGROUPNAME para o nome real do filegroup
                fg_name = str(row.get('FILEGROUPNAME', ''))
                if not fg_name:
                    fg_name = str(row.get('FILETYPE', 'UNKNOWN'))
                fg_type = str(row.get('FILETYPE', 'ROWS'))

                fg = FileGroupStatus(
                    database_name=str(row.get('DATABASENAME', 'UNKNOWN')),
                    filegroup_name=fg_name,
                    filegroup_type=fg_type,
                    file_count=int(to_float(row.get('NUM_DATAFILES', 0))),
                    logical_names=logical_names,
                    total_gb=total_gb,
                    max_gb=max_gb,
                    used_gb=used_gb,
                    free_gb=free_gb,
                    free_filegroup_percent=free_pct,
                    free_disk_percent=disk_free_pct,
                    available_filegroup_gb=available_filegroup_gb,
                    available_disk_gb=disk_available_gb,
                    volume=str(row.get('VOLMOUNTPOINT', 'N/A')),
                    volume_logical_name='',
                    alert_level=self._classify_alert_level(free_pct, disk_free_pct, disk_overflow, max_gb),
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
    
    def _classify_alert_level(self, free_filegroup_pct: float, free_disk_pct: float, disk_overflow: bool, max_gb: float = 0) -> str:
        if disk_overflow:
            return 'DISK_OVERFLOW'
        
        # Se maxsize é ilimitado (>= 999999), não há limite de crescimento no filegroup
        # Nesse caso, usar apenas o espaço do disco para classificar
        if max_gb >= 999999:
            worst_pct = free_disk_pct
        # Se free_filegroup_pct é 0 mas não há dados válidos, não gerar alerta baseado apenas nisso
        # Usar apenas free_disk_pct se free_filegroup_pct não for confiável
        elif free_filegroup_pct == 0 and free_disk_pct > 0:
            # Se filegroup tem 0% mas disco tem espaço, pode ser que os dados do filegroup não estejam disponíveis
            # Nesse caso, usar apenas o disco para classificar
            worst_pct = free_disk_pct
        else:
            worst_pct = min(free_filegroup_pct, free_disk_pct) if free_filegroup_pct > 0 else free_disk_pct
        
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

    # ============================================
    # TEMPDB ANALYSIS - Monitoramento de TempDB
    # ============================================

    async def get_tempdb_status(self, server_id: str) -> Dict:
        """
        Retorna análise completa do TempDB incluindo:
        - Tamanho total, usado e livre
        - Arquivos de dados e configuração
        - Vilões (sessões que mais consomem)
        - Alertas de espaço
        """
        query = """
        -- =============================================================================
        -- TempDB Space Analysis - Para módulo Space
        -- Retorna informações de espaço do TempDB similar aos outros filegroups
        -- =============================================================================

        -- Informações dos arquivos de dados do TempDB
        SELECT
            'tempdb' as database_name,
            'TEMPDB_DATA' as filegroup_name,
            mf.name as logical_name,
            mf.physical_name,
            CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(12,2)) as size_gb,
            CAST(FILEPROPERTY(mf.name, 'SpaceUsed') * 8.0 / 1024 / 1024 AS DECIMAL(12,2)) as used_gb,
            CAST((mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) * 8.0 / 1024 / 1024 AS DECIMAL(12,2)) as free_gb,
            CASE
                WHEN mf.max_size = -1 THEN 999999.0
                WHEN mf.max_size = 268435456 THEN 2048.0
                ELSE CAST(mf.max_size * 8.0 / 1024 / 1024 AS DECIMAL(12,2))
            END as max_gb,
            CAST(vs.total_bytes / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(12,2)) as disk_total_gb,
            CAST(vs.available_bytes / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(12,2)) as disk_available_gb,
            vs.volume_mount_point
        FROM tempdb.sys.database_files mf
        CROSS APPLY sys.dm_os_volume_stats(2, mf.file_id) vs
        WHERE mf.type_desc = 'ROWS'
        """

        try:
            result = await self.sql_monitoring.execute_query(server_id, query)

            if not result or not isinstance(result, dict):
                return {'error': 'no-data', 'server_id': server_id}

            rows = result.get('rows', [])
            if not rows:
                return {'error': 'no-tempdb-data', 'server_id': server_id}

            # Agregar informações de todos os arquivos de dados
            total_size_gb = sum(to_float(r.get('size_gb', 0)) for r in rows)
            total_used_gb = sum(to_float(r.get('used_gb', 0)) for r in rows)
            total_free_gb = sum(to_float(r.get('free_gb', 0)) for r in rows)
            total_max_gb = sum(to_float(r.get('max_gb', 0)) for r in rows)

            # Pegar informações de disco do primeiro arquivo (mesmo volume)
            disk_total_gb = to_float(rows[0].get('disk_total_gb', 0))
            disk_available_gb = to_float(rows[0].get('disk_available_gb', 0))
            volume = str(rows[0].get('volume_mount_point', 'N/A'))

            # Calcular percentuais
            used_percent = safe_percentage(total_used_gb, total_size_gb) if total_size_gb > 0 else 0
            free_percent = 100 - used_percent

            # Verificar se pode crescer mais que o disco disponível
            potential_growth = total_max_gb - total_size_gb if total_max_gb < 999999 else 0
            disk_overflow_risk = potential_growth > disk_available_gb if potential_growth > 0 else False

            # Classificar nível de alerta
            alert_level = self._classify_alert_level(
                free_percent,
                safe_percentage(disk_available_gb, disk_total_gb),
                disk_overflow_risk,
                total_max_gb
            )

            # Lista de arquivos lógicos
            logical_names = [str(r.get('logical_name', '')) for r in rows]

            return {
                'server_id': server_id,
                'database_name': 'tempdb',
                'filegroup_name': 'TEMPDB_DATA',
                'file_count': len(rows),
                'logical_names': logical_names,
                'total_gb': total_size_gb,
                'used_gb': total_used_gb,
                'free_gb': total_free_gb,
                'max_gb': total_max_gb,
                'used_percent': used_percent,
                'free_percent': free_percent,
                'disk_total_gb': disk_total_gb,
                'disk_available_gb': disk_available_gb,
                'volume': volume,
                'alert_level': alert_level,
                'disk_overflow_risk': disk_overflow_risk,
                'files': [
                    {
                        'logical_name': str(r.get('logical_name', '')),
                        'physical_name': str(r.get('physical_name', '')),
                        'size_gb': to_float(r.get('size_gb', 0)),
                        'used_gb': to_float(r.get('used_gb', 0)),
                        'free_gb': to_float(r.get('free_gb', 0)),
                        'max_gb': to_float(r.get('max_gb', 0))
                    }
                    for r in rows
                ]
            }

        except Exception as e:
            logger.error(f"Erro ao analisar TempDB de {server_id}: {e}")
            return {'error': str(e), 'server_id': server_id}

    async def get_tempdb_villains(self, server_id: str, top_n: int = 20) -> Dict:
        """
        Retorna os vilões do TempDB - sessões que mais consomem espaço
        Ordenado por consumo decrescente
        """
        query = f"""
        -- =============================================================================
        -- TempDB Villains - Top {top_n} consumidores de TempDB
        -- =============================================================================

        DECLARE @tempdb_size_pages BIGINT;
        SELECT @tempdb_size_pages = SUM(size)
        FROM tempdb.sys.database_files
        WHERE type_desc = 'ROWS';

        SELECT TOP {top_n}
            su.session_id,
            es.login_name,
            es.host_name,
            es.program_name,
            d.name as database_context,
            es.login_time,
            es.last_request_start_time,
            es.status as session_status,
            su.user_objects_alloc_page_count as user_objects_pages,
            su.user_objects_dealloc_page_count as user_objects_dealloc_pages,
            su.internal_objects_alloc_page_count as internal_objects_pages,
            su.internal_objects_dealloc_page_count as internal_objects_dealloc_pages,
            (su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) as total_alloc_pages,
            (su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) as user_objects_net_pages,
            (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count) as internal_objects_net_pages,
            CAST((su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as total_alloc_mb,
            CAST((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count +
                  su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as net_usage_mb,
            CAST((su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) * 100.0 /
                 NULLIF(@tempdb_size_pages, 0) AS DECIMAL(5,2)) as percent_of_tempdb
        FROM tempdb.sys.dm_db_session_space_usage su WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions es WITH(NOLOCK) ON su.session_id = es.session_id
        LEFT JOIN sys.databases d WITH(NOLOCK) ON es.database_id = d.database_id
        WHERE (su.user_objects_alloc_page_count > 0 OR su.internal_objects_alloc_page_count > 0)
          AND su.session_id > 50
        ORDER BY (su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) DESC
        """

        try:
            result = await self.sql_monitoring.execute_query(server_id, query)

            if not result or not isinstance(result, dict):
                return {'server_id': server_id, 'villains': [], 'count': 0}

            rows = result.get('rows', [])

            villains = []
            for row in rows:
                villain = {
                    'session_id': int(to_float(row.get('session_id', 0))),
                    'login_name': str(row.get('login_name', 'N/A')),
                    'host_name': str(row.get('host_name', 'N/A')),
                    'program_name': str(row.get('program_name', 'N/A')),
                    'database_context': str(row.get('database_context', 'N/A')),
                    'login_time': str(row.get('login_time', '')),
                    'last_request': str(row.get('last_request_start_time', '')),
                    'session_status': str(row.get('session_status', 'N/A')),
                    'user_objects_pages': int(to_float(row.get('user_objects_pages', 0))),
                    'internal_objects_pages': int(to_float(row.get('internal_objects_pages', 0))),
                    'total_alloc_pages': int(to_float(row.get('total_alloc_pages', 0))),
                    'total_alloc_mb': to_float(row.get('total_alloc_mb', 0)),
                    'net_usage_mb': to_float(row.get('net_usage_mb', 0)),
                    'percent_of_tempdb': to_float(row.get('percent_of_tempdb', 0))
                }
                villains.append(villain)

            return {
                'server_id': server_id,
                'villains': villains,
                'count': len(villains),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Erro ao buscar vilões TempDB de {server_id}: {e}")
            return {'server_id': server_id, 'villains': [], 'count': 0, 'error': str(e)}

    async def get_tempdb_complete_analysis(self, server_id: str) -> Dict:
        """
        Retorna análise completa do TempDB:
        - Status de espaço (como filegroup)
        - Vilões (top consumidores)
        - Alertas e recomendações
        """
        # Buscar status e vilões em paralelo
        status_task = self.get_tempdb_status(server_id)
        villains_task = self.get_tempdb_villains(server_id)

        status, villains = await asyncio.gather(status_task, villains_task)

        # Gerar recomendações baseadas no status
        recommendations = []
        if 'error' not in status:
            alert_level = status.get('alert_level', 'OK')
            used_percent = status.get('used_percent', 0)

            if alert_level == 'CRITICAL':
                recommendations.append(f"🔴 CRÍTICO: TempDB está {used_percent:.1f}% utilizado")
                recommendations.append("   └─ Verificar sessões consumindo TempDB e considerar expansão")
            elif alert_level == 'HIGH':
                recommendations.append(f"🟠 ALTO: TempDB está {used_percent:.1f}% utilizado")
                recommendations.append("   └─ Monitorar tendência de crescimento")
            elif alert_level == 'WARNING':
                recommendations.append(f"🟡 ATENÇÃO: TempDB está {used_percent:.1f}% utilizado")

            if status.get('disk_overflow_risk'):
                recommendations.append("🔴 RISCO: TempDB pode exceder espaço em disco disponível")

        # Recomendações sobre vilões
        if villains.get('villains'):
            top_villain = villains['villains'][0]
            if top_villain.get('percent_of_tempdb', 0) > 20:
                recommendations.append(
                    f"⚠️ Sessão {top_villain['session_id']} ({top_villain['login_name']}) "
                    f"consumindo {top_villain['percent_of_tempdb']:.1f}% do TempDB"
                )

        return {
            'server_id': server_id,
            'tempdb_status': status,
            'tempdb_villains': villains,
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat()
        }


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


