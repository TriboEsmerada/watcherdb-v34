"""
SQL Server KPI Service
======================

Serviço para coleta de KPIs diretamente do SQL Server.

Baseado em:
- modules/monitoring/queries.py (queries SQL Server)

Author: WatcherDB Team
Date: 2025-11-27
Version: 1.0.0
"""

import pyodbc
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

# Import do pool de conexões centralizado
from api.connection_pool import get_sql_server_pool

logger = logging.getLogger(__name__)


class SQLServerKPIService:
    """
    Serviço para coleta de KPIs do SQL Server.

    Cada método corresponde a um KPI específico do dashboard.
    """

    # Cache do dashboard: {server_id: {"data": ..., "timestamp": ...}}
    _dashboard_cache: Dict[str, Any] = {}
    _cache_lock = threading.Lock()
    CACHE_TTL_SECONDS = 60  # 60 segundos de TTL

    def __init__(self, connection_string: Optional[str] = None, server_id: Optional[str] = None):
        """
        Inicializa o serviço de KPIs

        Args:
            connection_string: String de conexão SQL Server (opcional, deprecated)
            server_id: ID do servidor no formato HOST_INSTANCE (opcional)
                      Se não fornecido, usa variáveis de ambiente SQL_SERVER
        """
        # Determinar server_id a partir das variáveis de ambiente
        if server_id:
            self.server_id = server_id
        else:
            server = os.getenv("SQL_SERVER", "localhost")
            # Converter formato HOST\\INSTANCE para HOST_INSTANCE
            self.server_id = server.replace("\\", "_")

        self.database = os.getenv("SQL_DATABASE", "master")
        self.pool = get_sql_server_pool()

    def get_connection(self) -> pyodbc.Connection:
        """Obtém conexão do pool centralizado"""
        try:
            conn = self.pool.get_connection(self.server_id, self.database)
            if conn is None:
                raise Exception(f"Não foi possível conectar ao servidor {self.server_id}")
            return conn
        except Exception as e:
            logger.error(f"Erro ao conectar SQL Server: {e}")
            raise

    def return_connection(self, conn: pyodbc.Connection):
        """Retorna conexão ao pool"""
        if conn:
            self.pool.return_connection(self.server_id, conn, self.database)

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Executa query e retorna resultados como lista de dicts

        Args:
            query: Query SQL a executar
            params: Parâmetros para a query (opcional)

        Returns:
            Lista de dicionários com os resultados
        """
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Obter nomes das colunas
            columns = [column[0] for column in cursor.description] if cursor.description else []

            # Converter rows para dicts
            results = []
            for row in cursor.fetchall():
                row_dict = {}
                for idx, value in enumerate(row):
                    # Converter datetime para string
                    if isinstance(value, datetime):
                        row_dict[columns[idx]] = value.isoformat()
                    else:
                        row_dict[columns[idx]] = value
                results.append(row_dict)

            return results

        except Exception as e:
            logger.error(f"Erro ao executar query: {e}")
            raise

        finally:
            if cursor:
                cursor.close()
            if conn:
                self.return_connection(conn)

    # ========================================================================
    # KPI 1: DATABASE AVAILABILITY
    # ========================================================================
    # Source view: KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
    # Lógica: Conta databases em estado anormal (não ONLINE)

    def get_database_availability(self) -> Dict[str, Any]:
        """
        KPI: Database Availability

        Retorna databases em estado anormal (não ONLINE).
        Source view: KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW

        Returns:
            {
                "total_databases": int,
                "abnormal_count": int,
                "abnormal_databases": [
                    {
                        "instance": str,
                        "database_name": str,
                        "state_desc": str,
                        "user_access_desc": str
                    }
                ]
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            name AS database_name,
            state_desc,
            user_access_desc
        FROM sys.databases WITH(NOLOCK)
        WHERE state_desc <> 'ONLINE'
        ORDER BY name;
        """

        abnormal_dbs = self.execute_query(query)

        # Contar total de databases
        total_query = "SELECT COUNT(*) AS total FROM sys.databases WITH(NOLOCK);"
        total_result = self.execute_query(total_query)
        total_count = total_result[0]["total"] if total_result else 0

        return {
            "total_databases": total_count,
            "abnormal_count": len(abnormal_dbs),
            "abnormal_databases": abnormal_dbs
        }

    # ========================================================================
    # KPI 2: DISK FILE SYSTEM USAGE
    # ========================================================================
    # Source view: KPI_MSSQL_DISK_USAGE_AGG_VIEW
    # Lógica: Soma espaço usado e livre por volume/drive

    def get_disk_usage(self) -> Dict[str, Any]:
        """
        KPI: Disk File System Usage

        Retorna uso de espaço em disco por volume.
        Source view: KPI_MSSQL_DISK_USAGE_AGG_VIEW

        Returns:
            {
                "volumes": [
                    {
                        "instance": str,
                        "volume": str,
                        "total_size_gb": float,
                        "used_size_gb": float,
                        "free_size_gb": float,
                        "used_percent": float
                    }
                ]
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            LEFT(physical_name, 1) AS volume,
            CAST(SUM(size * 8.0 / 1024 / 1024) AS DECIMAL(18,2)) AS total_size_gb,
            CAST(SUM((size - FILEPROPERTY(name, 'SpaceUsed')) * 8.0 / 1024 / 1024) AS DECIMAL(18,2)) AS free_size_gb,
            CAST(SUM(FILEPROPERTY(name, 'SpaceUsed') * 8.0 / 1024 / 1024) AS DECIMAL(18,2)) AS used_size_gb,
            CAST((SUM(FILEPROPERTY(name, 'SpaceUsed')) * 100.0 / SUM(size)) AS DECIMAL(5,2)) AS used_percent
        FROM sys.master_files WITH(NOLOCK)
        WHERE type_desc = 'ROWS'  -- Apenas arquivos de dados
        GROUP BY LEFT(physical_name, 1)
        ORDER BY volume;
        """

        volumes = self.execute_query(query)

        return {
            "volumes": volumes
        }

    # ========================================================================
    # KPI 3: TRANSACTION LOG USAGE
    # ========================================================================
    # Source view: KPI_MSSQL_TLOG_USAGE_AGG_VIEW
    # Lógica: Mostra databases com log usage > threshold (exemplo: 75%)

    def get_tlog_usage(self, threshold_percent: float = 75.0) -> Dict[str, Any]:
        """
        KPI: Transaction Log Usage

        Retorna databases com uso de transaction log acima do threshold.
        Source view: KPI_MSSQL_TLOG_USAGE_AGG_VIEW

        Args:
            threshold_percent: Percentual de uso considerado crítico (padrão: 75%)

        Returns:
            {
                "critical_count": int,
                "critical_databases": [
                    {
                        "instance": str,
                        "database_name": str,
                        "log_size_mb": float,
                        "log_used_percent": float,
                        "used_log_mb": float,
                        "free_log_mb": float,
                        "log_reuse_wait_desc": str,
                        "alert_level": str
                    }
                ]
            }
        """
        query = """
        SET NOCOUNT ON;

        -- Criar tabela temporaria para armazenar resultado do DBCC SQLPERF
        CREATE TABLE #LogSpace (
            DatabaseName NVARCHAR(128),
            LogSizeMB DECIMAL(18,2),
            LogSpaceUsedPercent DECIMAL(5,2),
            Status INT
        );

        -- Inserir dados do DBCC SQLPERF
        INSERT INTO #LogSpace
        EXEC('DBCC SQLPERF(LOGSPACE) WITH NO_INFOMSGS');

        -- Selecionar databases com uso acima do threshold
        SELECT
            @@SERVERNAME AS instance,
            ls.DatabaseName as database_name,
            ls.LogSizeMB as log_size_mb,
            ls.LogSpaceUsedPercent as log_used_percent,
            CAST(ls.LogSizeMB * ls.LogSpaceUsedPercent / 100.0 AS DECIMAL(12,2)) as used_log_mb,
            CAST(ls.LogSizeMB * (100.0 - ls.LogSpaceUsedPercent) / 100.0 AS DECIMAL(12,2)) as free_log_mb,
            ISNULL(d.log_reuse_wait_desc, 'NOTHING') as log_reuse_wait_desc,
            CASE
                WHEN ls.LogSpaceUsedPercent > 90 THEN 'CRITICAL'
                WHEN ls.LogSpaceUsedPercent > 75 THEN 'HIGH'
                WHEN ls.LogSpaceUsedPercent > 60 THEN 'MEDIUM'
                ELSE 'OK'
            END as alert_level
        FROM #LogSpace ls
        LEFT JOIN sys.databases d WITH(NOLOCK) ON ls.DatabaseName = d.name
        WHERE ls.LogSpaceUsedPercent >= ?
          AND ls.LogSizeMB > 0
          AND (d.state IS NULL OR d.state = 0)
        ORDER BY ls.LogSpaceUsedPercent DESC;

        -- Limpar tabela temporaria
        DROP TABLE #LogSpace;
        """

        critical_logs = self.execute_query(query, (threshold_percent,))

        return {
            "critical_count": len(critical_logs),
            "critical_databases": critical_logs
        }

    # ========================================================================
    # KPI 4: ALWAYS ON STATUS
    # ========================================================================
    # Source view: KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
    # Lógica: Mostra réplicas com synchronization_health_desc <> 'HEALTHY'

    def get_alwayson_status(self) -> Dict[str, Any]:
        """
        KPI: Always On Availability Group Status

        Retorna réplicas Always On em estado não saudável.
        Source view: KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW

        Returns:
            {
                "unhealthy_count": int,
                "unhealthy_replicas": [
                    {
                        "instance": str,
                        "ag_name": str,
                        "replica_server": str,
                        "current_role": str,
                        "sync_health": str,
                        "operational_state": str,
                        "connected_state": str
                    }
                ]
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            ag.name AS ag_name,
            ar.replica_server_name AS replica_server,
            ars.role_desc AS current_role,
            ars.synchronization_health_desc AS sync_health,
            ars.operational_state_desc AS operational_state,
            ars.connected_state_desc AS connected_state
        FROM sys.availability_groups ag WITH(NOLOCK)
        INNER JOIN sys.availability_replicas ar WITH(NOLOCK) ON ag.group_id = ar.group_id
        INNER JOIN sys.dm_hadr_availability_replica_states ars WITH(NOLOCK) ON ar.replica_id = ars.replica_id
        WHERE ars.synchronization_health_desc <> 'HEALTHY'
        ORDER BY ag.name, ar.replica_server_name;
        """

        try:
            unhealthy_replicas = self.execute_query(query)
            return {
                "unhealthy_count": len(unhealthy_replicas),
                "unhealthy_replicas": unhealthy_replicas
            }
        except Exception as e:
            # Always On pode não estar configurado
            logger.warning(f"Always On não disponível ou não configurado: {e}")
            return {
                "unhealthy_count": 0,
                "unhealthy_replicas": [],
                "message": "Always On não disponível nesta instância"
            }

    # ========================================================================
    # KPI 5: FILEGROUP USAGE
    # ========================================================================
    # Source view: KPI_MSSQL_FG_USAGE_AGG_VIEW
    # Lógica: Mostra filegroups com espaço livre baixo

    def get_filegroup_usage(self, threshold_percent: float = 10.0) -> Dict[str, Any]:
        """
        KPI: Filegroup Usage

        Retorna filegroups com espaço livre abaixo do threshold.
        Source view: KPI_MSSQL_FG_USAGE_AGG_VIEW

        Args:
            threshold_percent: Percentual de espaço livre considerado crítico (padrão: 10%)

        Returns:
            {
                "critical_count": int,
                "critical_filegroups": [
                    {
                        "instance": str,
                        "database_name": str,
                        "filegroup_name": str,
                        "file_name": str,
                        "current_mb": float,
                        "free_percent": float
                    }
                ]
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            DB_NAME(f.database_id) AS database_name,
            fg.name AS filegroup_name,
            f.name AS file_name,
            CAST(f.size * 8.0 / 1024 AS DECIMAL(18,2)) AS current_mb,
            CAST(((f.size - FILEPROPERTY(f.name, 'SpaceUsed')) * 100.0 / f.size) AS DECIMAL(5,2)) AS free_percent
        FROM sys.master_files f WITH(NOLOCK)
        LEFT JOIN sys.filegroups fg WITH(NOLOCK) ON f.data_space_id = fg.data_space_id
        WHERE f.type_desc = 'ROWS'
          AND CAST(((f.size - FILEPROPERTY(f.name, 'SpaceUsed')) * 100.0 / f.size) AS DECIMAL(5,2)) < ?
        ORDER BY free_percent ASC;
        """

        critical_filegroups = self.execute_query(query, (threshold_percent,))

        return {
            "critical_count": len(critical_filegroups),
            "critical_filegroups": critical_filegroups
        }

    # ========================================================================
    # KPI 6: BLOCKED SESSIONS
    # ========================================================================
    # Source view: KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW
    # Lógica: Conta sessões bloqueadas

    def get_blocked_sessions(self) -> Dict[str, Any]:
        """
        KPI: Blocked Sessions

        Retorna sessões bloqueadas.
        Source view: KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW

        Returns:
            {
                "blocked_count": int,
                "blocked_sessions": [
                    {
                        "instance": str,
                        "session_id": int,
                        "blocking_session_id": int,
                        "wait_type": str,
                        "wait_time": int,
                        "login_name": str,
                        "program_name": str,
                        "host_name": str
                    }
                ]
            }
        """
        query = """
        SELECT DISTINCT
            @@SERVERNAME AS instance,
            r.session_id,
            r.blocking_session_id,
            r.wait_type,
            r.wait_time,
            s.login_name,
            s.program_name,
            s.host_name,
            s.status as session_status
        FROM sys.dm_exec_requests r WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON r.session_id = s.session_id
        WHERE r.blocking_session_id > 0
          AND r.blocking_session_id <> r.session_id
          AND (s.login_name IS NOT NULL OR s.host_name IS NOT NULL OR s.program_name IS NOT NULL)
        ORDER BY r.wait_time DESC;
        """

        blocked_sessions = self.execute_query(query)

        return {
            "blocked_count": len(blocked_sessions),
            "blocked_sessions": blocked_sessions
        }

    # ========================================================================
    # KPI 7: INSTANCE AVAILABILITY
    # ========================================================================
    # Source view: KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW
    # Lógica: Verifica se instância está respondendo

    def get_instance_availability(self) -> Dict[str, Any]:
        """
        KPI: Instance Availability

        Verifica se a instância SQL Server está disponível.
        Source view: KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW

        Returns:
            {
                "instance": str,
                "is_available": bool,
                "uptime_days": int,
                "sqlserver_start_time": str
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            1 AS is_available,
            DATEDIFF(DAY, sqlserver_start_time, GETDATE()) AS uptime_days,
            sqlserver_start_time
        FROM sys.dm_os_sys_info WITH(NOLOCK);
        """

        try:
            result = self.execute_query(query)
            if result:
                return result[0]
            else:
                return {
                    "instance": "unknown",
                    "is_available": False,
                    "uptime_days": 0
                }
        except Exception as e:
            logger.error(f"Erro ao verificar disponibilidade da instância: {e}")
            return {
                "instance": "unknown",
                "is_available": False,
                "error": str(e)
            }

    # ========================================================================
    # KPI 8: BACKUP STATUS
    # ========================================================================
    # Source view: KPI_MSSQL_BACKUP_STATUS_AGG_VIEW
    # Lógica: Mostra databases sem backup recente

    def get_backup_status(self, days_threshold: int = 1) -> Dict[str, Any]:
        """
        KPI: Backup Status

        Retorna databases sem backup recente.
        Source view: KPI_MSSQL_BACKUP_STATUS_AGG_VIEW

        Args:
            days_threshold: Número de dias sem backup considerado crítico (padrão: 1)

        Returns:
            {
                "missing_backup_count": int,
                "databases_missing_backup": [
                    {
                        "instance": str,
                        "database_name": str,
                        "last_full_backup": str,
                        "days_since_backup": int
                    }
                ]
            }
        """
        query = """
        WITH LastBackups AS (
            SELECT
                d.name AS database_name,
                MAX(bs.backup_finish_date) AS last_full_backup,
                DATEDIFF(DAY, MAX(bs.backup_finish_date), GETDATE()) AS days_since_backup
            FROM sys.databases d WITH(NOLOCK)
            LEFT JOIN msdb.dbo.backupset bs WITH(NOLOCK) ON d.name = bs.database_name AND bs.type = 'D'
            WHERE d.name NOT IN ('tempdb')
              AND d.state = 0  -- ONLINE
            GROUP BY d.name
        )
        SELECT
            @@SERVERNAME AS instance,
            database_name,
            last_full_backup,
            ISNULL(days_since_backup, 9999) AS days_since_backup
        FROM LastBackups
        WHERE last_full_backup IS NULL
           OR days_since_backup > ?
        ORDER BY days_since_backup DESC;
        """

        missing_backups = self.execute_query(query, (days_threshold,))

        return {
            "missing_backup_count": len(missing_backups),
            "databases_missing_backup": missing_backups
        }

    # ========================================================================
    # KPI 9: JOB FAILURES
    # ========================================================================
    # Source view: KPI_MSSQL_JOB_FAILURES_AGG_VIEW
    # Lógica: Mostra jobs que falharam recentemente

    def get_job_failures(self, days_lookback: int = 7) -> Dict[str, Any]:
        """
        KPI: SQL Agent Job Failures

        Retorna jobs que falharam nos últimos N dias.
        Source view: KPI_MSSQL_JOB_FAILURES_AGG_VIEW

        Args:
            days_lookback: Número de dias para buscar falhas (padrão: 7)

        Returns:
            {
                "failure_count": int,
                "failed_jobs": [
                    {
                        "instance": str,
                        "job_name": str,
                        "step_name": str,
                        "run_date": int,
                        "run_time": int,
                        "run_datetime": str,
                        "message": str
                    }
                ]
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            j.name as job_name,
            js.step_name,
            jh.run_date,
            jh.run_time,
            CASE
                WHEN jh.run_date > 0
                THEN CONVERT(DATETIME,
                        CAST(jh.run_date as CHAR(8)) + ' ' +
                        STUFF(STUFF(RIGHT('000000' + CAST(jh.run_time as VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':'))
                ELSE NULL
            END as run_datetime,
            jh.message
        FROM msdb.dbo.sysjobs j WITH(NOLOCK)
        INNER JOIN msdb.dbo.sysjobsteps js WITH(NOLOCK) ON j.job_id = js.job_id
        INNER JOIN msdb.dbo.sysjobhistory jh WITH(NOLOCK) ON js.job_id = jh.job_id AND js.step_id = jh.step_id
        WHERE jh.run_status = 0  -- Failed
          AND jh.run_date >= CONVERT(INT, CONVERT(VARCHAR, GETDATE()-?, 112))
        ORDER BY jh.run_date DESC, jh.run_time DESC;
        """

        failed_jobs = self.execute_query(query, (days_lookback,))

        return {
            "failure_count": len(failed_jobs),
            "failed_jobs": failed_jobs
        }

    # ========================================================================
    # KPI 10: INDEX FRAGMENTATION
    # ========================================================================
    # Source view: KPI_MSSQL_INDEX_FRAGMENTATION_AGG_VIEW
    # Lógica: Mostra índices com fragmentação alta

    def get_index_fragmentation(self, threshold_percent: float = 30.0) -> Dict[str, Any]:
        """
        KPI: Index Fragmentation

        Retorna índices com fragmentação acima do threshold.
        Source view: KPI_MSSQL_INDEX_FRAGMENTATION_AGG_VIEW

        Args:
            threshold_percent: Percentual de fragmentação considerado crítico (padrão: 30%)

        Returns:
            {
                "fragmented_count": int,
                "fragmented_indexes": [
                    {
                        "instance": str,
                        "database_name": str,
                        "schema_name": str,
                        "table_name": str,
                        "index_name": str,
                        "fragmentation_percent": float,
                        "page_count": int,
                        "maintenance_action": str
                    }
                ]
            }
        """
        # Esta query precisa executar em cada database
        # Por simplificação, vamos executar apenas na database corrente
        query = """
        SELECT TOP 100
            @@SERVERNAME AS instance,
            DB_NAME() as database_name,
            ss.name as schema_name,
            OBJECT_NAME(ips.object_id) as table_name,
            si.name as index_name,
            ips.avg_fragmentation_in_percent as fragmentation_percent,
            ips.page_count,
            CASE
                WHEN ips.avg_fragmentation_in_percent > 30 AND ips.page_count > 1000 THEN 'REBUILD'
                WHEN ips.avg_fragmentation_in_percent > 10 AND ips.page_count > 1000 THEN 'REORGANIZE'
                ELSE 'OK'
            END as maintenance_action
        FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
        INNER JOIN sys.indexes si ON ips.object_id = si.object_id AND ips.index_id = si.index_id
        INNER JOIN sys.objects so ON si.object_id = so.object_id
        INNER JOIN sys.schemas ss ON so.schema_id = ss.schema_id
        WHERE ips.avg_fragmentation_in_percent >= ?
          AND ips.page_count > 1000
          AND si.name IS NOT NULL
        ORDER BY ips.avg_fragmentation_in_percent DESC;
        """

        fragmented_indexes = self.execute_query(query, (threshold_percent,))

        return {
            "fragmented_count": len(fragmented_indexes),
            "fragmented_indexes": fragmented_indexes
        }

    # ========================================================================
    # KPI 11: STATISTICS OUTDATED
    # ========================================================================
    # Source view: KPI_MSSQL_STATISTICS_OUTDATED_AGG_VIEW
    # Lógica: Mostra estatísticas desatualizadas

    def get_statistics_outdated(self, modification_threshold: float = 20.0) -> Dict[str, Any]:
        """
        KPI: Statistics Outdated

        Retorna estatísticas desatualizadas.
        Source view: KPI_MSSQL_STATISTICS_OUTDATED_AGG_VIEW

        Args:
            modification_threshold: Percentual de modificação considerado crítico (padrão: 20%)

        Returns:
            {
                "outdated_count": int,
                "outdated_statistics": [
                    {
                        "instance": str,
                        "database_name": str,
                        "schema_name": str,
                        "table_name": str,
                        "stats_name": str,
                        "last_updated": str,
                        "modification_percent": float,
                        "days_since_update": int
                    }
                ]
            }
        """
        query = """
        SELECT TOP 100
            @@SERVERNAME AS instance,
            DB_NAME() as database_name,
            OBJECT_SCHEMA_NAME(s.object_id) as schema_name,
            OBJECT_NAME(s.object_id) as table_name,
            s.name as stats_name,
            sp.last_updated,
            CASE
                WHEN sp.rows > 0
                THEN CAST((sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2))
                ELSE 0
            END as modification_percent,
            CASE
                WHEN sp.last_updated IS NOT NULL
                THEN DATEDIFF(day, sp.last_updated, GETDATE())
                ELSE NULL
            END as days_since_update
        FROM sys.stats s WITH(NOLOCK)
        CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
        WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
          AND sp.rows >= 100
          AND sp.last_updated IS NOT NULL
          AND CAST((sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2)) >= ?
        ORDER BY modification_percent DESC;
        """

        outdated_stats = self.execute_query(query, (modification_threshold,))

        return {
            "outdated_count": len(outdated_stats),
            "outdated_statistics": outdated_stats
        }

    # ========================================================================
    # KPI 12: TEMPDB USAGE
    # ========================================================================
    # Source view: KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW (se existir)
    # Lógica: Mostra uso de TempDB

    def get_tempdb_usage(self) -> Dict[str, Any]:
        """
        KPI: TempDB Usage

        Retorna uso de TempDB.

        Returns:
            {
                "total_mb": float,
                "used_mb": float,
                "free_mb": float,
                "used_percent": float,
                "files": [...]
            }
        """
        query = """
        SELECT
            @@SERVERNAME AS instance,
            DB_NAME(database_id) AS database_name,
            name AS file_name,
            type_desc AS file_type,
            CAST(size * 8.0 / 1024 AS DECIMAL(12,2)) AS total_mb,
            CAST(ISNULL(FILEPROPERTY(name, 'SpaceUsed'), 0) * 8.0 / 1024 AS DECIMAL(12,2)) AS used_mb,
            CAST((size - ISNULL(FILEPROPERTY(name, 'SpaceUsed'), 0)) * 8.0 / 1024 AS DECIMAL(12,2)) AS free_mb,
            CAST((ISNULL(FILEPROPERTY(name, 'SpaceUsed'), 0) * 100.0 / NULLIF(size, 0)) AS DECIMAL(5,2)) AS used_percent
        FROM sys.master_files WITH(NOLOCK)
        WHERE database_id = 2  -- TempDB
        ORDER BY type_desc, file_id;
        """

        files = self.execute_query(query)

        # Calcular totais
        total_mb = sum(f.get("total_mb", 0) for f in files)
        used_mb = sum(f.get("used_mb", 0) for f in files)
        free_mb = sum(f.get("free_mb", 0) for f in files)
        used_percent = (used_mb / total_mb * 100) if total_mb > 0 else 0

        return {
            "total_mb": round(total_mb, 2),
            "used_mb": round(used_mb, 2),
            "free_mb": round(free_mb, 2),
            "used_percent": round(used_percent, 2),
            "files": files
        }

    # ========================================================================
    # DASHBOARD COMPLETO
    # ========================================================================

    def get_dashboard(self) -> Dict[str, Any]:
        """
        KPI Dashboard Completo

        Agrega todos os KPIs em um único endpoint.
        Equivalente ao Oracle: /api/oracle-kpis/dashboard

        Optimizações:
        - Cache com TTL de 60s para evitar re-queries frequentes
        - ThreadPoolExecutor para executar os 12 KPIs em paralelo

        Returns:
            Dictionary contendo todos os KPIs
        """
        # Verificar cache
        with self._cache_lock:
            cached = self._dashboard_cache.get(self.server_id)
            if cached and (time.time() - cached["cached_at"]) < self.CACHE_TTL_SECONDS:
                logger.info(f"KPI Dashboard cache hit para {self.server_id} (age: {time.time() - cached['cached_at']:.1f}s)")
                return cached["data"]

        # Cache miss — coletar dados
        t_start = time.perf_counter()

        dashboard = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance": "unknown",
            "kpis": {}
        }

        try:
            # Definir todas as tarefas KPI (nome, função, args)
            kpi_tasks = {
                "db_availability": (self.get_database_availability, {}),
                "disk_usage": (self.get_disk_usage, {}),
                "tlog_usage": (self.get_tlog_usage, {"threshold_percent": 75.0}),
                "alwayson_status": (self.get_alwayson_status, {}),
                "filegroup_usage": (self.get_filegroup_usage, {"threshold_percent": 10.0}),
                "blocked_sessions": (self.get_blocked_sessions, {}),
                "instance_availability": (self.get_instance_availability, {}),
                "backup_status": (self.get_backup_status, {"days_threshold": 1}),
                "job_failures": (self.get_job_failures, {"days_lookback": 7}),
                "index_fragmentation": (self.get_index_fragmentation, {"threshold_percent": 30.0}),
                "statistics_outdated": (self.get_statistics_outdated, {"modification_threshold": 20.0}),
                "tempdb_usage": (self.get_tempdb_usage, {}),
            }

            kpis = {}

            # Executar todos os KPIs em paralelo com ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=6) as executor:
                future_to_kpi = {}
                for kpi_name, (func, kwargs) in kpi_tasks.items():
                    future = executor.submit(func, **kwargs)
                    future_to_kpi[future] = kpi_name

                for future in as_completed(future_to_kpi):
                    kpi_name = future_to_kpi[future]
                    try:
                        kpis[kpi_name] = future.result(timeout=60)
                    except Exception as e:
                        logger.error(f"Erro ao coletar {kpi_name}: {e}")
                        kpis[kpi_name] = {"error": str(e)}

            # Extrair nome da instância do KPI instance_availability
            instance_info = kpis.get("instance_availability", {})
            dashboard["instance"] = instance_info.get("instance", "unknown")
            dashboard["kpis"] = kpis

            elapsed = time.perf_counter() - t_start
            logger.info(f"KPI Dashboard coletado em {elapsed:.2f}s (paralelo) para {self.server_id}")

            # Guardar em cache
            with self._cache_lock:
                self._dashboard_cache[self.server_id] = {
                    "data": dashboard,
                    "cached_at": time.time()
                }

        except Exception as e:
            logger.error(f"Erro ao coletar dashboard: {e}")
            dashboard["error"] = str(e)

        return dashboard


# ============================================================================
# EXEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)

    # Criar serviço
    service = SQLServerKPIService()

    # Testar KPI individual
    print("\n=== Database Availability ===")
    db_avail = service.get_database_availability()
    print(f"Total databases: {db_avail['total_databases']}")
    print(f"Abnormal count: {db_avail['abnormal_count']}")

    # Obter dashboard completo
    print("\n=== Dashboard Completo ===")
    dashboard = service.get_dashboard()
    print(f"Instance: {dashboard['instance']}")
    print(f"Timestamp: {dashboard['timestamp']}")
    print(f"KPIs coletados: {len(dashboard['kpis'])}")
