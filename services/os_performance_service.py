"""
OS Performance Service - Coleta e analise de metricas do Windows OS
Implementa coleta via WMI (preferencial) e PowerShell (fallback)
Para responder alertas SCOM como "Memory Pages Per Second is too High"
"""
import logging
import os
import subprocess
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import pyodbc

# Import do pool de conexões centralizado
from api.connection_pool import get_intelligence_pool

logger = logging.getLogger(__name__)

# Thresholds baseados no prompt
MEMORY_THRESHOLDS = {
    'available_mb': {'ok': 2048, 'info': 1024, 'warning': 512, 'critical': 256},
    'page_reads_sec': {'ok': 20, 'info': 50, 'warning': 100, 'critical': 200},
    'pages_sec': {'ok': 100, 'info': 500, 'warning': 1000, 'critical': 2000},
    'percent_committed': {'ok': 80, 'info': 90, 'warning': 95, 'critical': 98}
}

CPU_THRESHOLDS = {
    'processor_pct': {'ok': 70, 'warning': 85, 'critical': 95},
    'queue_length': {'ok': 2, 'warning': 5, 'critical': 10}
}


@dataclass
class OSMemoryMetrics:
    """Metricas de memoria do Windows OS"""
    hostname: str
    available_mb: float
    total_physical_mb: float
    used_mb: float
    percent_used: float
    pages_per_sec: float
    page_reads_sec: float
    page_writes_sec: float
    page_faults_sec: float
    commit_limit_mb: float
    commit_total_mb: float
    percent_committed: float
    pool_paged_mb: float
    pool_nonpaged_mb: float
    cache_mb: float
    severity: str
    collection_method: str
    update_ts: datetime


@dataclass
class OSCPUMetrics:
    """Metricas de CPU do Windows OS"""
    hostname: str
    processor_pct: float
    privileged_pct: float
    user_pct: float
    interrupt_pct: float
    dpc_pct: float
    queue_length: int
    context_switches_sec: float
    sql_cpu_pct: float
    severity: str
    collection_method: str
    update_ts: datetime


@dataclass
class MemoryDiagnosis:
    """Diagnostico de memoria para resposta a alertas SCOM"""
    hostname: str
    alert_classification: str
    is_actionable: bool
    current_severity: str
    trend_severity: str
    avg_page_reads_30min: float
    max_page_reads_30min: float
    avg_available_mb_30min: float
    min_available_mb_30min: float
    sql_ple_current: Optional[float]
    sql_buffer_pool_mb: Optional[float]
    recommended_response: str
    ticket_suggestion: str
    collection_timestamp: datetime


class OSPerformanceService:
    """Service para coleta e analise de metricas OS"""

    def __init__(self, connection_string: str = None):
        """
        Inicializa o service

        Args:
            connection_string: String de conexao ao WatcherDB_Intelligence
        """
        self.connection_string = connection_string or self._build_connection_string()
        self._wmi_available = self._check_wmi_available()

    def _build_connection_string(self) -> str:
        """Constroi connection string baseado em variaveis de ambiente"""
        server = os.getenv('INTELLIGENCE_SERVER', 'SQLHDSTST505\\I01')
        database = os.getenv('INTELLIGENCE_DATABASE', 'WatcherDB_Intelligence')
        driver = os.getenv('SQL_DRIVER', 'ODBC Driver 17 for SQL Server')

        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
            f"Connection Timeout=30;"
        )

    def _check_wmi_available(self) -> bool:
        """Verifica se WMI esta disponivel"""
        try:
            import wmi
            return True
        except ImportError:
            logger.warning("WMI module not available, will use PowerShell fallback")
            return False

    @contextmanager
    def _get_connection(self):
        """
        Context manager para obter conexão do pool centralizado.
        Retorna a conexão ao pool automaticamente ao sair do bloco with.
        """
        pool = get_intelligence_pool()
        conn = None
        try:
            conn = pool.get_connection()
            yield conn
        finally:
            if conn:
                pool.return_connection(conn)

    def _calculate_memory_severity(self, metrics: Dict) -> str:
        """Calcula severidade baseada nas metricas de memoria"""
        available_mb = metrics.get('available_mb', 0)
        page_reads_sec = metrics.get('page_reads_sec', 0)
        percent_committed = metrics.get('percent_committed', 0)

        # Ordem de prioridade: critical > warning > info > ok
        if (available_mb < MEMORY_THRESHOLDS['available_mb']['critical'] or
            page_reads_sec > MEMORY_THRESHOLDS['page_reads_sec']['critical'] or
            percent_committed > MEMORY_THRESHOLDS['percent_committed']['critical']):
            return 'CRITICAL'

        if (available_mb < MEMORY_THRESHOLDS['available_mb']['warning'] or
            page_reads_sec > MEMORY_THRESHOLDS['page_reads_sec']['warning'] or
            percent_committed > MEMORY_THRESHOLDS['percent_committed']['warning']):
            return 'WARNING'

        if (available_mb < MEMORY_THRESHOLDS['available_mb']['info'] or
            page_reads_sec > MEMORY_THRESHOLDS['page_reads_sec']['info'] or
            percent_committed > MEMORY_THRESHOLDS['percent_committed']['info']):
            return 'INFO'

        return 'OK'

    async def get_memory_current(self, hostname: str) -> Optional[Dict]:
        """
        Obtem metricas de memoria atuais da view vw_OS_Memory_Current

        Args:
            hostname: Nome do servidor

        Returns:
            Dict com metricas ou None se nao encontrar
        """
        try:
            query = """
            SELECT
                Hostname,
                Available_MB,
                Total_Physical_MB,
                Used_MB,
                Percent_Used,
                Pages_Per_Sec,
                Page_Reads_Sec,
                Page_Writes_Sec,
                Page_Faults_Sec,
                Commit_Limit_MB,
                Commit_Total_MB,
                Percent_Committed,
                Pool_Paged_MB,
                Pool_NonPaged_MB,
                Cache_MB,
                Severity,
                Collection_Method,
                Update_TS
            FROM vw_OS_Memory_Current
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

        except Exception as e:
            logger.error(f"Error getting memory current for {hostname}: {e}")
            return None

    async def get_memory_trend(self, hostname: str, minutes: int = 30) -> List[Dict]:
        """
        Obtem tendencia de memoria dos ultimos N minutos

        Args:
            hostname: Nome do servidor
            minutes: Quantidade de minutos para analise

        Returns:
            Lista de dicts com metricas historicas
        """
        try:
            query = """
            SELECT
                Hostname,
                Available_MB,
                Pages_Per_Sec,
                Page_Reads_Sec,
                Percent_Committed,
                Severity,
                Update_TS
            FROM KPI_OS_MEMORY_HIST
            WHERE Hostname = ?
              AND Update_TS >= DATEADD(MINUTE, -?, GETDATE())
            ORDER BY Update_TS DESC
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname, minutes))
                rows = cursor.fetchall()

                if not rows:
                    return []

                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting memory trend for {hostname}: {e}")
            return []

    async def get_memory_diagnosis(self, hostname: str) -> Optional[Dict]:
        """
        Obtem diagnostico completo de memoria para resposta a alertas SCOM
        Usa a view vw_OS_Memory_Alert_Diagnosis

        Args:
            hostname: Nome do servidor

        Returns:
            Dict com diagnostico ou None
        """
        try:
            query = """
            SELECT *
            FROM vw_OS_Memory_Alert_Diagnosis
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    # Se nao tem dados na view, retornar diagnostico basico
                    return await self._build_basic_diagnosis(hostname)

                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

        except Exception as e:
            logger.error(f"Error getting memory diagnosis for {hostname}: {e}")
            return None

    async def _build_basic_diagnosis(self, hostname: str) -> Dict:
        """Constroi diagnostico basico quando nao ha dados na view"""
        current = await self.get_memory_current(hostname)

        if not current:
            return {
                'Hostname': hostname,
                'Alert_Classification': 'NO_DATA',
                'Is_Actionable': False,
                'Current_Severity': 'UNKNOWN',
                'Recommended_Response': 'Sem dados disponiveis. Verificar se o agente de coleta esta funcionando.',
                'Ticket_Suggestion': 'Aguardar proxima coleta de dados',
                'Collection_Timestamp': datetime.now().isoformat()
            }

        severity = current.get('Severity', 'UNKNOWN')
        page_reads = current.get('Page_Reads_Sec', 0)
        available_mb = current.get('Available_MB', 0)

        # Classificar alerta
        if severity == 'CRITICAL':
            classification = 'CRITICAL: High memory pressure detected'
            is_actionable = True
            response = 'INVESTIGATE IMMEDIATELY: Check for memory leaks or processes consuming excessive memory'
            ticket = 'Keep ticket open for investigation'
        elif severity == 'WARNING':
            classification = 'WARNING: Moderate memory pressure'
            is_actionable = True
            response = 'MONITOR: Watch for escalation in the next 30 minutes'
            ticket = 'Monitor and escalate if condition persists'
        else:
            classification = 'OK: Normal memory usage'
            is_actionable = False
            response = 'No action required'
            ticket = 'Close ticket - false positive or transient spike'

        return {
            'Hostname': hostname,
            'Alert_Classification': classification,
            'Is_Actionable': is_actionable,
            'Current_Severity': severity,
            'Page_Reads_Sec': page_reads,
            'Available_MB': available_mb,
            'Recommended_Response': response,
            'Ticket_Suggestion': ticket,
            'Collection_Timestamp': current.get('Update_TS', datetime.now()).isoformat() if current.get('Update_TS') else datetime.now().isoformat()
        }

    async def get_cpu_current(self, hostname: str) -> Optional[Dict]:
        """Obtem metricas de CPU atuais"""
        try:
            query = """
            SELECT *
            FROM vw_OS_CPU_Current
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

        except Exception as e:
            logger.error(f"Error getting CPU current for {hostname}: {e}")
            return None

    async def get_disk_current(self, hostname: str) -> Optional[Dict]:
        """Obtem metricas de disco atuais"""
        try:
            query = """
            SELECT *
            FROM vw_OS_Disk_Current
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

        except Exception as e:
            logger.error(f"Error getting disk current for {hostname}: {e}")
            return None

    async def get_disk_by_drive(self, hostname: str) -> List[Dict]:
        """
        Obtem metricas de disco por drive com latência detalhada (sec/Read, sec/Write)
        Usa a tabela KPI_OS_DISK_PERF_STG com dados de Performance Counters

        Args:
            hostname: Nome do servidor

        Returns:
            Lista de dicts com metricas por drive incluindo:
            - Avg_Sec_Per_Read: Latência média de leitura em segundos
            - Avg_Sec_Per_Write: Latência média de escrita em segundos
            - Avg_Read_Latency_MS: Latência em milissegundos
            - Avg_Write_Latency_MS: Latência em milissegundos
            - Disk_Reads_Sec: IOPS de leitura
            - Disk_Writes_Sec: IOPS de escrita
        """
        try:
            query = """
            SELECT
                Instance,
                Hostname,
                Drive,
                Avg_Queue_Length,
                Current_Queue_Len,
                Percent_Disk_Time,
                Percent_Read_Time,
                Percent_Write_Time,
                Percent_Idle_Time,
                Avg_Sec_Per_Read,
                Avg_Sec_Per_Write,
                Avg_Sec_Per_Transfer,
                Avg_Read_Latency_MS,
                Avg_Write_Latency_MS,
                Disk_Reads_Sec,
                Disk_Writes_Sec,
                Disk_Transfers_Sec,
                Disk_Read_Bytes_Sec,
                Disk_Write_Bytes_Sec,
                Disk_Bytes_Sec,
                Severity,
                Disk_Type,
                Collection_Method,
                Update_TS,
                -- Classificação de latência
                CASE
                    WHEN Avg_Read_Latency_MS >= 50 THEN 'CRITICAL'
                    WHEN Avg_Read_Latency_MS >= 20 THEN 'WARNING'
                    WHEN Avg_Read_Latency_MS >= 10 THEN 'INFO'
                    ELSE 'OK'
                END AS Read_Latency_Status,
                CASE
                    WHEN Avg_Write_Latency_MS >= 50 THEN 'CRITICAL'
                    WHEN Avg_Write_Latency_MS >= 20 THEN 'WARNING'
                    WHEN Avg_Write_Latency_MS >= 10 THEN 'INFO'
                    ELSE 'OK'
                END AS Write_Latency_Status
            FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK)
            WHERE Hostname = ?
            ORDER BY Drive
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                rows = cursor.fetchall()

                if not rows:
                    return []

                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting disk by drive for {hostname}: {e}")
            return []

    async def get_disk_latency_summary(self, hostname: str) -> Optional[Dict]:
        """
        Obtem resumo de latência de disco para o hostname
        Útil para detectar ciclo de degradação memória -> paging -> disk I/O

        Returns:
            Dict com:
            - max_read_latency_ms: Maior latência de leitura
            - max_write_latency_ms: Maior latência de escrita
            - problem_drives: Lista de drives com latência crítica/warning
            - overall_status: Status geral baseado na pior latência
        """
        try:
            query = """
            SELECT
                MAX(Avg_Read_Latency_MS) AS Max_Read_Latency_MS,
                MAX(Avg_Write_Latency_MS) AS Max_Write_Latency_MS,
                AVG(Avg_Read_Latency_MS) AS Avg_Read_Latency_MS,
                AVG(Avg_Write_Latency_MS) AS Avg_Write_Latency_MS,
                COUNT(*) AS Total_Drives,
                SUM(CASE WHEN Avg_Read_Latency_MS >= 20 OR Avg_Write_Latency_MS >= 20 THEN 1 ELSE 0 END) AS Drives_With_High_Latency,
                STRING_AGG(
                    CASE WHEN Avg_Read_Latency_MS >= 20 OR Avg_Write_Latency_MS >= 20
                        THEN Drive + ' (R:' + CAST(ISNULL(Avg_Read_Latency_MS, 0) AS VARCHAR) + 'ms, W:' + CAST(ISNULL(Avg_Write_Latency_MS, 0) AS VARCHAR) + 'ms)'
                        ELSE NULL
                    END, ', '
                ) AS Problem_Drives
            FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK)
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row))

                # Determinar status geral
                max_read = result.get('Max_Read_Latency_MS') or 0
                max_write = result.get('Max_Write_Latency_MS') or 0
                max_latency = max(max_read, max_write)

                if max_latency >= 50:
                    result['Overall_Status'] = 'CRITICAL'
                elif max_latency >= 20:
                    result['Overall_Status'] = 'WARNING'
                elif max_latency >= 10:
                    result['Overall_Status'] = 'INFO'
                else:
                    result['Overall_Status'] = 'OK'

                return result

        except Exception as e:
            logger.error(f"Error getting disk latency summary for {hostname}: {e}")
            return None

    async def get_servers_needing_attention(self) -> List[Dict]:
        """Retorna lista de servidores que precisam de atencao"""
        try:
            query = """
            SELECT *
            FROM vw_OS_Servers_Needing_Attention
            ORDER BY Severity_Priority DESC, Hostname
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()

                if not rows:
                    return []

                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting servers needing attention: {e}")
            return []

    async def get_sql_memory_correlation(self, hostname: str) -> Optional[Dict]:
        """Obtem correlacao entre memoria OS e SQL Server"""
        try:
            query = """
            SELECT *
            FROM vw_OS_SQL_Memory_Correlation
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

        except Exception as e:
            logger.error(f"Error getting SQL memory correlation for {hostname}: {e}")
            return None

    async def get_full_correlation(self, hostname: str) -> Optional[Dict]:
        """Obtem correlacao completa OS + SQL Server"""
        try:
            query = """
            SELECT *
            FROM vw_OS_SQL_Full_Correlation
            WHERE Hostname = ?
            """

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (hostname,))
                row = cursor.fetchone()

                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row))

                # Converter datetime para string
                for key, value in result.items():
                    if isinstance(value, datetime):
                        result[key] = value.isoformat()

                return result

        except Exception as e:
            logger.error(f"Error getting full correlation for {hostname}: {e}")
            return None


# Instancia global do service
_os_performance_service: Optional[OSPerformanceService] = None


def get_os_performance_service() -> OSPerformanceService:
    """Factory para obter instancia do service"""
    global _os_performance_service
    if _os_performance_service is None:
        _os_performance_service = OSPerformanceService()
    return _os_performance_service
