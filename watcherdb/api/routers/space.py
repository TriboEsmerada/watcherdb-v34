"""
Space Analysis Router
Handles all space-related monitoring endpoints

IMPORTANTE: Este router agora usa dados do WatcherDB Intelligence (tabelas Blue/Green)
em vez de queries diretas com estimativa de 75% que eram imprecisas.

Fonte de dados: KPI_MSSQL_FG_USAGE_ACTIVE (view que aponta para tabela Blue ou Green ativa)
Colunas: Instance, Database, Filegroup, Total_MB, Used_MB, Free_MB, Percent_Used, Max_Size_MB, Growth_Type, Update_TS
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, Any, List
import logging
import pyodbc
import os
from decimal import Decimal

from watcherdb.core.auth import get_current_user, User, require_role, UserRole
from modules.monitoring.space_analysis import (
    SpaceAnalysisEngine,
    get_space_analysis_for_all_servers,
    extract_alerts
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/monitoring/space",
    tags=["space-analysis"],
    responses={404: {"description": "Not found"}},
)

# ========================================
# CONFIGURAÇÃO DO WATCHERDB INTELLIGENCE
# ========================================
INTELLIGENCE_SERVER = os.getenv("INTELLIGENCE_SERVER", "SQLHDSTST505\\I01")
INTELLIGENCE_DATABASE = os.getenv("INTELLIGENCE_DATABASE", "WatcherDB_Intelligence")
INTELLIGENCE_SCHEMA = "dbo"
INTELLIGENCE_DRIVER = "ODBC Driver 17 for SQL Server"


def _get_intelligence_connection():
    """Cria conexão com o WatcherDB Intelligence"""
    conn_str = (
        f"DRIVER={{{INTELLIGENCE_DRIVER}}};"
        f"SERVER={INTELLIGENCE_SERVER};"
        f"DATABASE={INTELLIGENCE_DATABASE};"
        f"Trusted_Connection=yes;"
        f"Connection Timeout=30"
    )
    return pyodbc.connect(conn_str)


def _serialize_value(val):
    """Converte valores para JSON serializable"""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return val


def _execute_intelligence_query(query: str) -> List[Dict]:
    """Executa query no WatcherDB Intelligence e retorna lista de dicts"""
    try:
        conn = _get_intelligence_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        return [
            {col: _serialize_value(val) for col, val in zip(columns, row)}
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao executar query no Intelligence: {e}")
        return []


@router.get("/server/{server_id}")
async def get_space_analysis(
    server_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get space analysis for a specific server

    IMPORTANTE: Usa dados do WatcherDB Intelligence (KPI_MSSQL_FG_USAGE_ACTIVE)
    que contém os dados REAIS coletados, não estimativas de 75%.

    Thresholds:
    - CRITICAL: Percent_Used >= 98% (< 2% livre)
    - WARNING: Percent_Used >= 95% (< 5% livre)
    """
    try:
        logger.info(f"Space analysis requested for server: {server_id} by {current_user.username}")

        # Normalizar nome da instância - aceitar tanto _ quanto \
        instance_underscore = server_id.replace('\\', '_')
        instance_backslash = server_id.replace('_', '\\')
        safe_underscore = instance_underscore.replace("'", "''")
        safe_backslash = instance_backslash.replace("'", "''")

        # Query usando tabela ACTIVE (blue/green com dados mais recentes)
        query = f"""
        SELECT
            f.Instance,
            f.[Database] AS database_name,
            f.Filegroup AS filegroup_name,
            f.Total_MB,
            f.Used_MB,
            f.Free_MB,
            f.Percent_Used,
            f.Max_Size_MB,
            f.Growth_Type,
            f.Update_TS,
            -- Calcular métricas em GB
            CAST(f.Total_MB / 1024.0 AS DECIMAL(18,2)) AS total_gb,
            CAST(f.Used_MB / 1024.0 AS DECIMAL(18,2)) AS used_gb,
            CAST(f.Free_MB / 1024.0 AS DECIMAL(18,2)) AS free_gb,
            CAST(f.Max_Size_MB / 1024.0 AS DECIMAL(18,2)) AS max_gb,
            -- Free percent (inverso do Percent_Used)
            CAST(100.0 - f.Percent_Used AS DECIMAL(5,2)) AS free_percent,
            -- Status baseado em thresholds
            CASE
                WHEN f.Percent_Used >= 98 THEN 'CRITICAL'
                WHEN f.Percent_Used >= 95 THEN 'WARNING'
                ELSE 'OK'
            END AS alert_level
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_ACTIVE AS f WITH (NOLOCK)
        WHERE f.Instance IN ('{safe_underscore}', '{safe_backslash}')
        ORDER BY f.Percent_Used DESC, f.[Database], f.Filegroup
        """

        filegroups = _execute_intelligence_query(query)

        logger.info(f"WatcherDB Intelligence: {len(filegroups)} filegroups encontrados para {server_id}")

        if not filegroups:
            # Retornar estrutura vazia em vez de 404
            return {
                "success": True,
                "server_id": server_id,
                "source": "WatcherDB_Intelligence",
                "filegroups": [],
                "summary": {
                    "total_filegroups": 0,
                    "critical_count": 0,
                    "warning_count": 0,
                    "ok_count": 0
                }
            }

        # Calcular resumo
        critical_count = sum(1 for fg in filegroups if fg.get('alert_level') == 'CRITICAL')
        warning_count = sum(1 for fg in filegroups if fg.get('alert_level') == 'WARNING')
        ok_count = sum(1 for fg in filegroups if fg.get('alert_level') == 'OK')

        return {
            "success": True,
            "server_id": server_id,
            "source": "WatcherDB_Intelligence",
            "filegroups": filegroups,
            "summary": {
                "total_filegroups": len(filegroups),
                "critical_count": critical_count,
                "warning_count": warning_count,
                "ok_count": ok_count
            }
        }

    except Exception as e:
        logger.error(f"Error in space analysis for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_space_dashboard(
    current_user: User = Depends(get_current_user)
):
    """Get aggregated space dashboard data for all servers"""
    try:
        logger.info(f"Space dashboard requested by {current_user.username}")

        all_servers_data = get_space_analysis_for_all_servers()

        dashboard_data = {
            "total_servers": len(all_servers_data),
            "servers": all_servers_data,
            "summary": {
                "critical_alerts": 0,
                "warning_alerts": 0,
                "total_databases": 0,
                "total_size_gb": 0,
                "total_available_gb": 0
            }
        }

        # Calculate aggregated metrics
        for server in all_servers_data:
            dashboard_data["summary"]["total_databases"] += len(server.get("databases", []))

            for db in server.get("databases", []):
                total_size = sum(fg.get("size_mb", 0) for fg in db.get("filegroups", []))
                total_available = sum(fg.get("available_mb", 0) for fg in db.get("filegroups", []))

                dashboard_data["summary"]["total_size_gb"] += total_size / 1024
                dashboard_data["summary"]["total_available_gb"] += total_available / 1024

                # Count alerts
                for fg in db.get("filegroups", []):
                    usage_pct = fg.get("usage_percent", 0)
                    if usage_pct > 90:
                        dashboard_data["summary"]["critical_alerts"] += 1
                    elif usage_pct > 80:
                        dashboard_data["summary"]["warning_alerts"] += 1

        return dashboard_data

    except Exception as e:
        logger.error(f"Error generating space dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_space_alerts(
    severity: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get space-related alerts across all servers"""
    try:
        logger.info(f"Space alerts requested by {current_user.username}")

        all_servers_data = get_space_analysis_for_all_servers()
        alerts = extract_alerts(all_servers_data)

        # Filter by severity if specified
        if severity:
            alerts = [a for a in alerts if a.get("severity", "").lower() == severity.lower()]

        return {
            "total_alerts": len(alerts),
            "alerts": alerts
        }

    except Exception as e:
        logger.error(f"Error extracting space alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/database/{database_name}")
async def get_database_space_analysis(
    server_id: str,
    database_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed space analysis for a specific database"""
    try:
        logger.info(f"Database space analysis requested: {server_id}/{database_name}")

        engine = SpaceAnalysisEngine()
        server_data = engine.analyze_server(server_id)

        if not server_data:
            raise HTTPException(status_code=404, detail=f"Server {server_id} not found")

        # Find specific database
        database = next(
            (db for db in server_data.get("databases", []) if db.get("name") == database_name),
            None
        )

        if not database:
            raise HTTPException(
                status_code=404,
                detail=f"Database {database_name} not found on server {server_id}"
            )

        return database

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in database space analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server/{server_id}/forecast")
async def get_space_forecast(
    server_id: str,
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get space growth forecast for a server"""
    try:
        logger.info(f"Space forecast requested for {server_id} ({days} days)")

        engine = SpaceAnalysisEngine()
        forecast = engine.forecast_space_growth(server_id, days=days)

        if not forecast:
            raise HTTPException(status_code=404, detail=f"Unable to generate forecast for {server_id}")

        return forecast

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating forecast: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
