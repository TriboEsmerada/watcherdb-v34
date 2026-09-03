"""
SQL Server KPIs Router
======================

FastAPI Router para KPIs do SQL Server.
Replica a funcionalidade do oracle_kpis.py, mas para SQL Server direto.

Endpoints:
- GET /api/sqlserver-kpis/dashboard - Dashboard completo com todos os KPIs
- GET /api/sqlserver-kpis/db-availability - Database availability
- GET /api/sqlserver-kpis/disk-usage - Disk usage por volume
- GET /api/sqlserver-kpis/tlog-usage - Transaction log usage
- GET /api/sqlserver-kpis/alwayson-status - Always On health
- GET /api/sqlserver-kpis/filegroup-usage - Filegroup usage
- GET /api/sqlserver-kpis/blocked-sessions - Blocked sessions
- GET /api/sqlserver-kpis/instance-availability - Instance availability
- GET /api/sqlserver-kpis/backup-status - Backup status
- GET /api/sqlserver-kpis/job-failures - SQL Agent job failures
- GET /api/sqlserver-kpis/index-fragmentation - Index fragmentation
- GET /api/sqlserver-kpis/statistics-outdated - Statistics outdated
- GET /api/sqlserver-kpis/tempdb-usage - TempDB usage

Author: WatcherDB Team
Date: 2025-11-27
Version: 1.0.0
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
import logging

# Import do serviço SQL Server KPI
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from services.sqlserver_kpi_service import SQLServerKPIService
from api.error_helpers import safe_http_error
from api.models import SQLServerKPIDashboardResponse, SQLServerKPIResponse, GenericResponse

logger = logging.getLogger(__name__)

# Criar router
router = APIRouter(
    prefix="/api/sqlserver-kpis",
    tags=["SQL Server KPIs"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"}
    }
)

# Inicializar serviço (será reusado entre requests)
_kpi_service = None


def get_kpi_service() -> SQLServerKPIService:
    """
    Retorna instância do serviço KPI (singleton)

    Returns:
        SQLServerKPIService instance
    """
    global _kpi_service
    if _kpi_service is None:
        _kpi_service = SQLServerKPIService()
    return _kpi_service


# ============================================================================
# ENDPOINT PRINCIPAL: DASHBOARD COMPLETO
# ============================================================================

@router.get("/dashboard", response_model=SQLServerKPIDashboardResponse)
async def get_kpi_dashboard():
    """
    **KPI Dashboard Completo**

    Retorna todos os KPIs agregados em um único endpoint.
    Utiliza cache (TTL 60s) e execução paralela dos 12 KPIs.

    Equivalente ao Oracle: `/api/oracle-kpis/dashboard`

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "timestamp": "2025-11-27T10:00:00",
            "instance": "SQLHDSPRD213\\I01",
            "kpis": {
                "db_availability": {...},
                "disk_usage": {...},
                "tlog_usage": {...},
                "alwayson_status": {...},
                "filegroup_usage": {...},
                "blocked_sessions": {...},
                "instance_availability": {...},
                "backup_status": {...},
                "job_failures": {...},
                "index_fragmentation": {...},
                "statistics_outdated": {...},
                "tempdb_usage": {...}
            }
        }
    }
    ```

    **Erros:**
    - 500: Erro ao coletar KPIs
    """
    try:
        import time as _time
        t0 = _time.perf_counter()

        service = get_kpi_service()
        dashboard = service.get_dashboard()

        elapsed_ms = int((_time.perf_counter() - t0) * 1000)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": dashboard,
                "performance": {
                    "response_time_ms": elapsed_ms,
                    "cache_ttl_seconds": service.CACHE_TTL_SECONDS
                }
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar dashboard KPI: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server KPI dashboard")


# ============================================================================
# ENDPOINTS INDIVIDUAIS POR KPI
# ============================================================================

@router.get("/db-availability", response_model=SQLServerKPIResponse)
async def get_database_availability():
    """
    **KPI: Database Availability**

    Retorna databases em estado anormal (não ONLINE).

    Equivalente ao Oracle: `KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW`

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "total_databases": 50,
            "abnormal_count": 2,
            "abnormal_databases": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "TestDB",
                    "state_desc": "RESTORING",
                    "user_access_desc": "MULTI_USER"
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_database_availability()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar database availability: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server database availability")


@router.get("/disk-usage", response_model=SQLServerKPIResponse)
async def get_disk_usage():
    """
    **KPI: Disk File System Usage**

    Retorna uso de espaço em disco por volume/drive.

    Equivalente ao Oracle: `KPI_MSSQL_DISK_USAGE_AGG_VIEW`

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "volumes": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "volume": "F",
                    "total_size_gb": 500.00,
                    "used_size_gb": 350.00,
                    "free_size_gb": 150.00,
                    "used_percent": 70.00
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_disk_usage()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar disk usage: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server disk usage")


@router.get("/tlog-usage", response_model=SQLServerKPIResponse)
async def get_tlog_usage(
    threshold: float = Query(75.0, ge=0, le=100, description="Threshold percentual para considerar crítico")
):
    """
    **KPI: Transaction Log Usage**

    Retorna databases com uso de transaction log acima do threshold.

    Equivalente ao Oracle: `KPI_MSSQL_TLOG_USAGE_AGG_VIEW`

    **Parameters:**
    - `threshold` (float): Percentual de uso considerado crítico (padrão: 75%)

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "critical_count": 3,
            "critical_databases": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "ProductionDB",
                    "log_size_mb": 10240.00,
                    "log_used_percent": 85.50,
                    "used_log_mb": 8755.20,
                    "free_log_mb": 1484.80,
                    "log_reuse_wait_desc": "LOG_BACKUP",
                    "alert_level": "CRITICAL"
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_tlog_usage(threshold_percent=threshold)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar tlog usage: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server tlog usage")


@router.get("/alwayson-status", response_model=SQLServerKPIResponse)
async def get_alwayson_status():
    """
    **KPI: Always On Availability Group Status**

    Retorna réplicas Always On em estado não saudável.

    Equivalente ao Oracle: `KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW`

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "unhealthy_count": 1,
            "unhealthy_replicas": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "ag_name": "AG_Production",
                    "replica_server": "SQLHDSPRD214",
                    "current_role": "SECONDARY",
                    "sync_health": "NOT_HEALTHY",
                    "operational_state": "ONLINE",
                    "connected_state": "CONNECTED"
                }
            ]
        }
    }
    ```

    **Note:**
    Se Always On não estiver configurado, retorna:
    ```json
    {
        "unhealthy_count": 0,
        "unhealthy_replicas": [],
        "message": "Always On não disponível nesta instância"
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_alwayson_status()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar always on status: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server Always On status")


@router.get("/filegroup-usage", response_model=SQLServerKPIResponse)
async def get_filegroup_usage(
    threshold: float = Query(10.0, ge=0, le=100, description="Threshold percentual de espaço livre considerado crítico")
):
    """
    **KPI: Filegroup Usage**

    Retorna filegroups com espaço livre abaixo do threshold.

    Equivalente ao Oracle: `KPI_MSSQL_FG_USAGE_AGG_VIEW`

    **Parameters:**
    - `threshold` (float): Percentual de espaço livre considerado crítico (padrão: 10%)

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "critical_count": 2,
            "critical_filegroups": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "LargeDB",
                    "filegroup_name": "PRIMARY",
                    "file_name": "LargeDB_Data",
                    "current_mb": 102400.00,
                    "free_percent": 5.50
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_filegroup_usage(threshold_percent=threshold)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar filegroup usage: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server filegroup usage")


@router.get("/blocked-sessions", response_model=SQLServerKPIResponse)
async def get_blocked_sessions():
    """
    **KPI: Blocked Sessions**

    Retorna sessões bloqueadas atualmente.

    Equivalente ao Oracle: `KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW`

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "blocked_count": 5,
            "blocked_sessions": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "session_id": 123,
                    "blocking_session_id": 456,
                    "wait_type": "LCK_M_X",
                    "wait_time": 15000,
                    "login_name": "app_user",
                    "program_name": "MyApp",
                    "host_name": "WEB01",
                    "session_status": "sleeping"
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_blocked_sessions()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar blocked sessions: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server blocked sessions")


@router.get("/instance-availability", response_model=SQLServerKPIResponse)
async def get_instance_availability():
    """
    **KPI: Instance Availability**

    Verifica se a instância SQL Server está disponível.

    Equivalente ao Oracle: `KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW`

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "instance": "SQLHDSPRD213\\I01",
            "is_available": true,
            "uptime_days": 45,
            "sqlserver_start_time": "2025-10-13T08:30:00"
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_instance_availability()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar instance availability: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server instance availability")


@router.get("/backup-status", response_model=SQLServerKPIResponse)
async def get_backup_status(
    days: int = Query(1, ge=0, le=365, description="Dias sem backup considerado crítico")
):
    """
    **KPI: Backup Status**

    Retorna databases sem backup recente.

    Equivalente ao Oracle: `KPI_MSSQL_BACKUP_STATUS_AGG_VIEW`

    **Parameters:**
    - `days` (int): Número de dias sem backup considerado crítico (padrão: 1)

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "missing_backup_count": 3,
            "databases_missing_backup": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "OldDB",
                    "last_full_backup": "2025-11-20T02:00:00",
                    "days_since_backup": 7
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_backup_status(days_threshold=days)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar backup status: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server backup status")


@router.get("/job-failures", response_model=SQLServerKPIResponse)
async def get_job_failures(
    days: int = Query(7, ge=1, le=365, description="Dias para buscar falhas de jobs")
):
    """
    **KPI: SQL Agent Job Failures**

    Retorna jobs que falharam nos últimos N dias.

    Equivalente ao Oracle: `KPI_MSSQL_JOB_FAILURES_AGG_VIEW`

    **Parameters:**
    - `days` (int): Número de dias para buscar falhas (padrão: 7)

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "failure_count": 10,
            "failed_jobs": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "job_name": "Daily Backup",
                    "step_name": "Backup Full",
                    "run_date": 20251127,
                    "run_time": 20000,
                    "run_datetime": "2025-11-27T02:00:00",
                    "message": "Access denied to backup file"
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_job_failures(days_lookback=days)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar job failures: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server job failures")


@router.get("/index-fragmentation", response_model=SQLServerKPIResponse)
async def get_index_fragmentation(
    threshold: float = Query(30.0, ge=0, le=100, description="Threshold percentual de fragmentação considerado crítico")
):
    """
    **KPI: Index Fragmentation**

    Retorna índices com fragmentação acima do threshold.

    Equivalente ao Oracle: `KPI_MSSQL_INDEX_FRAGMENTATION_AGG_VIEW`

    **Parameters:**
    - `threshold` (float): Percentual de fragmentação considerado crítico (padrão: 30%)

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "fragmented_count": 25,
            "fragmented_indexes": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "ProductionDB",
                    "schema_name": "dbo",
                    "table_name": "Orders",
                    "index_name": "IX_Orders_Date",
                    "fragmentation_percent": 75.50,
                    "page_count": 50000,
                    "maintenance_action": "REBUILD"
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_index_fragmentation(threshold_percent=threshold)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar index fragmentation: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server index fragmentation")


@router.get("/statistics-outdated", response_model=SQLServerKPIResponse)
async def get_statistics_outdated(
    threshold: float = Query(20.0, ge=0, le=100, description="Threshold percentual de modificação considerado crítico")
):
    """
    **KPI: Statistics Outdated**

    Retorna estatísticas desatualizadas.

    Equivalente ao Oracle: `KPI_MSSQL_STATISTICS_OUTDATED_AGG_VIEW`

    **Parameters:**
    - `threshold` (float): Percentual de modificação considerado crítico (padrão: 20%)

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "outdated_count": 15,
            "outdated_statistics": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "ProductionDB",
                    "schema_name": "dbo",
                    "table_name": "Customers",
                    "stats_name": "_WA_Sys_00000003_12345678",
                    "last_updated": "2025-11-01T10:00:00",
                    "modification_percent": 45.50,
                    "days_since_update": 26
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_statistics_outdated(modification_threshold=threshold)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar statistics outdated: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server statistics outdated")


@router.get("/tempdb-usage", response_model=SQLServerKPIResponse)
async def get_tempdb_usage():
    """
    **KPI: TempDB Usage**

    Retorna uso de TempDB.

    **Returns:**
    ```json
    {
        "success": true,
        "data": {
            "total_mb": 10240.00,
            "used_mb": 2560.00,
            "free_mb": 7680.00,
            "used_percent": 25.00,
            "files": [
                {
                    "instance": "SQLHDSPRD213\\I01",
                    "database_name": "tempdb",
                    "file_name": "tempdev",
                    "file_type": "ROWS",
                    "total_mb": 5120.00,
                    "used_mb": 1280.00,
                    "free_mb": 3840.00,
                    "used_percent": 25.00
                }
            ]
        }
    }
    ```
    """
    try:
        service = get_kpi_service()
        result = service.get_tempdb_usage()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"Erro ao coletar tempdb usage: {e}", exc_info=True)
        raise safe_http_error(500, e, "collecting SQL Server tempdb usage")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health", response_model=GenericResponse)
async def health_check():
    """
    **Health Check**

    Verifica se o serviço de KPIs está funcionando.

    **Returns:**
    ```json
    {
        "success": true,
        "service": "SQL Server KPIs",
        "status": "healthy",
        "version": "1.0.0"
    }
    ```
    """
    try:
        # Testar conexão
        service = get_kpi_service()
        conn = service.get_connection()
        conn.close()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "service": "SQL Server KPIs",
                "status": "healthy",
                "version": "1.0.0"
            }
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "service": "SQL Server KPIs",
                "status": "unhealthy",
                "error": "Service unavailable. Check server logs for details."
            }
        )


# ============================================================================
# DOCUMENTAÇÃO ADICIONAL
# ============================================================================

@router.get("/", response_model=GenericResponse)
async def root():
    """
    **SQL Server KPIs API**

    API para coleta de KPIs do SQL Server.

    Replica a funcionalidade dos KPIs Oracle, mas com queries diretas no SQL Server.

    **Endpoints Disponíveis:**

    - `GET /dashboard` - Dashboard completo com todos os KPIs
    - `GET /db-availability` - Database availability
    - `GET /disk-usage` - Disk usage por volume
    - `GET /tlog-usage` - Transaction log usage
    - `GET /alwayson-status` - Always On health
    - `GET /filegroup-usage` - Filegroup usage
    - `GET /blocked-sessions` - Blocked sessions
    - `GET /instance-availability` - Instance availability
    - `GET /backup-status` - Backup status
    - `GET /job-failures` - SQL Agent job failures
    - `GET /index-fragmentation` - Index fragmentation
    - `GET /statistics-outdated` - Statistics outdated
    - `GET /tempdb-usage` - TempDB usage
    - `GET /health` - Health check

    **Swagger UI:** `/api/docs`
    """
    return JSONResponse(
        status_code=200,
        content={
            "service": "SQL Server KPIs API",
            "version": "1.0.0",
            "documentation": "/api/docs",
            "endpoints": [
                "/api/sqlserver-kpis/dashboard",
                "/api/sqlserver-kpis/db-availability",
                "/api/sqlserver-kpis/disk-usage",
                "/api/sqlserver-kpis/tlog-usage",
                "/api/sqlserver-kpis/alwayson-status",
                "/api/sqlserver-kpis/filegroup-usage",
                "/api/sqlserver-kpis/blocked-sessions",
                "/api/sqlserver-kpis/instance-availability",
                "/api/sqlserver-kpis/backup-status",
                "/api/sqlserver-kpis/job-failures",
                "/api/sqlserver-kpis/index-fragmentation",
                "/api/sqlserver-kpis/statistics-outdated",
                "/api/sqlserver-kpis/tempdb-usage",
                "/api/sqlserver-kpis/health"
            ]
        }
    )
