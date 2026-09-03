#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overview Dashboard Endpoints

Endpoints para consumir dados pre-calculados do Overview Dashboard.
Os dados sao atualizados a cada 5 minutos pelo Job SQL Agent ou via endpoint refresh.

Copiado de WATCHERDB INTELLIGENCE V1 e adaptado para WATCHERDB_DEV.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import logging
import pyodbc
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import time
import os
import re

# Import do pool de conexões centralizado
from api.connection_pool import get_intelligence_pool
from watcherdb.core.db_identity import resolve as _resolve_db_identity
from services.secrets import get_secret
from api.error_helpers import safe_http_error
from api.models import DashboardResponse, GenericResponse, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/overview", tags=["Overview Dashboard"])

# ========================================
# CONFIGURACAO DE CONEXAO SQL SERVER
# ========================================
INTELLIGENCE_SERVER = os.getenv("INTELLIGENCE_SERVER", "SQLHDSTST505\\I01")
INTELLIGENCE_DATABASE = os.getenv("INTELLIGENCE_DATABASE", "WatcherDB_Intelligence")
INTELLIGENCE_SCHEMA = "dbo"
# Identidade da ligacao: fonte unica em watcherdb.core.db_identity (achado
# P-05). Sem variavel definida NAO ha default implicito -- nunca Windows Auth.
INTELLIGENCE_USE_WINDOWS_AUTH = _resolve_db_identity().use_windows_auth
INTELLIGENCE_SQL_USER = os.getenv("INTELLIGENCE_SQL_USER", "sql_monitoring")
# get_secret decifra o formato "encrypted:<fernet>" do .env (P-05).
INTELLIGENCE_SQL_PASSWORD = get_secret("INTELLIGENCE_SQL_PASSWORD", "")
INTELLIGENCE_DRIVER = "ODBC Driver 17 for SQL Server"

# Rate limiting para refresh
_last_refresh_time = None
_refresh_cooldown_seconds = 60  # Minimo 1 minuto entre refreshes


def get_intelligence_connection():
    """
    Obtém conexão com o SQL Server Intelligence usando pool centralizado.

    Usa o IntelligenceConnectionPool do módulo connection_pool.py para
    reutilizar conexões e melhorar a performance.
    """
    try:
        pool = get_intelligence_pool()
        conn = pool.get_connection()
        logger.debug("Conexão obtida do pool Intelligence")
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao SQL Server Intelligence: {e}")
        raise safe_http_error(500, e, "connecting to Intelligence database")


def execute_query(query: str, params: Dict = None, fetch: str = "all") -> Any:
    """
    Executa query no SQL Server Intelligence.

    Args:
        query: SQL query com parametros @NomeParam
        params: Dict com parametros {"NomeParam": valor}
        fetch: "all" para lista, "one" para unico resultado

    Returns:
        Lista de dicts ou dict unico
    """
    conn = None
    cursor = None
    try:
        conn = get_intelligence_connection()
        cursor = conn.cursor()

        # Substituir @Param por ? e ordenar valores
        if params:
            # Encontrar todos os @Param na query na ordem que aparecem
            param_pattern = re.compile(r"@(\w+)")
            found_params = param_pattern.findall(query)

            # Substituir @Param por ?
            for param_name in set(found_params):
                query = query.replace(f"@{param_name}", "?")

            # Construir lista de valores na ordem correta
            values = [params.get(p) for p in found_params]
            cursor.execute(query, values)
        else:
            cursor.execute(query)

        if cursor.description is None:
            return [] if fetch == "all" else None

        columns = [desc[0] for desc in cursor.description]

        if fetch == "one":
            row = cursor.fetchone()
            if row is None:
                return None
            row_dict = {}
            for i, value in enumerate(row):
                if isinstance(value, Decimal):
                    row_dict[columns[i]] = float(value)
                elif isinstance(value, datetime):
                    row_dict[columns[i]] = value
                else:
                    row_dict[columns[i]] = value
            return row_dict
        else:
            rows = cursor.fetchall()
            results = []
            for row in rows:
                row_dict = {}
                for i, value in enumerate(row):
                    if isinstance(value, Decimal):
                        row_dict[columns[i]] = float(value)
                    elif isinstance(value, datetime):
                        row_dict[columns[i]] = value
                    else:
                        row_dict[columns[i]] = value
                results.append(row_dict)
            return results

    except Exception as e:
        raise safe_http_error(500, e, "executing Intelligence query")
    finally:
        if cursor:
            cursor.close()
        if conn:
            # Retornar conexão ao pool para reutilização
            try:
                pool = get_intelligence_pool()
                pool.return_connection(conn)
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")


_ALLOWED_PROCEDURES = {
    "dbo.usp_refresh_overview_all",
    "dbo.usp_refresh_overview_summary",
    "dbo.usp_cleanup_token_blacklist",
}


def execute_procedure(proc_name: str):
    """Executa uma stored procedure (apenas da whitelist)"""
    if proc_name not in _ALLOWED_PROCEDURES:
        raise HTTPException(status_code=400, detail=f"Procedure not allowed: {proc_name}")
    conn = None
    cursor = None
    try:
        conn = get_intelligence_connection()
        cursor = conn.cursor()
        cursor.execute(f"EXEC {proc_name}")
        conn.commit()
    except Exception as e:
        raise safe_http_error(500, e, f"executing procedure {proc_name}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            # Retornar conexão ao pool para reutilização
            try:
                pool = get_intelligence_pool()
                pool.return_connection(conn)
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")


# ========================================
# ENDPOINTS
# ========================================

@router.get("/summary", response_model=DashboardResponse)
async def get_overview_summary(
    env: Optional[str] = Query(None, description="Ambiente (PRD, HML, DEV, etc). Se nao informado, retorna ALL"),
):
    """
    Retorna sumario do Overview Dashboard.

    Dados pre-calculados por ambiente com contadores agregados de:
    - Instancias online/offline
    - Health Score medio e minimo
    - Contadores de problemas por categoria (blocking, space, backup, etc)
    """
    try:
        if env:
            query = """
                SELECT * FROM dbo.V_OVERVIEW_DASHBOARD_SUMMARY
                WHERE Env = @Env
            """
            result = execute_query(query, params={"Env": env.upper()}, fetch="one")
        else:
            query = """
                SELECT * FROM dbo.V_OVERVIEW_DASHBOARD_SUMMARY
                WHERE Env = 'ALL'
            """
            result = execute_query(query, fetch="one")

        if not result:
            return {
                "success": True,
                "data": None,
                "message": f"Nenhum dado encontrado para ambiente '{env or 'ALL'}'. Execute EXEC dbo.usp_refresh_overview_all; no banco."
            }

        # Montar resposta estruturada
        summary = {
            "env": result.get("Env"),
            "total_instances": result.get("Total_Instances", 0),
            "instances_online": result.get("Instances_Online", 0),
            "instances_offline": result.get("Instances_Offline", 0),
            "availability_percent": float(result.get("Availability_Percent", 0) or 0),
            "avg_health_score": float(result.get("Avg_Health_Score", 0) or 0),
            "min_health_score": float(result.get("Min_Health_Score", 0) or 0),
            "instances_by_status": {
                "ok": result.get("Instances_OK", 0),
                "warning": result.get("Instances_Warning", 0),
                "critical": result.get("Instances_Critical", 0),
                "offline": result.get("Instances_Offline", 0)
            },
            "performance": {
                "total_blocked_sessions": result.get("Total_Blocked_Sessions", 0),
                "total_blocked_users": result.get("Total_Blocked_Users", 0),
                "total_long_locks": result.get("Total_Long_Locks", 0),
                "cpu_critical": result.get("Total_CPU_Critical", 0),
                "memory_critical": result.get("Total_Memory_Critical", 0),
                "deadlocks_critical": result.get("Total_Deadlocks_Critical", 0),
                "deadlocks_warning": result.get("Total_Deadlocks_Warning", 0),
                "deadlocks_info": result.get("Total_Deadlocks_Info", 0),
                "deadlocks_count_24h": result.get("Total_Deadlocks_Count", 0)
            },
            "space": {
                "tlog_critical": result.get("Total_TLog_Critical", 0),
                "tlog_warning": result.get("Total_TLog_Warning", 0),
                "fg_critical": result.get("Total_FG_Critical", 0),
                "fg_warning": result.get("Total_FG_Warning", 0),
                "disk_critical": result.get("Total_Disk_Critical", 0),
                "disk_warning": result.get("Total_Disk_Warning", 0),
                "total_critical": result.get("Total_Space_Critical", 0),
                "total_warning": result.get("Total_Space_Warning", 0)
            },
            "backup_overdue": result.get("Total_Backup_Overdue", 0),
            "alwayson_unhealthy": result.get("Total_AlwaysOn_Unhealthy", 0),
            "services_stopped": result.get("Total_Services_Stopped", 0),
            "databases": {
                "total": result.get("Total_Databases", 0),
                "online": result.get("Databases_Online", 0),
                "offline": result.get("Databases_Offline", 0)
            },
            "last_refresh": result.get("Last_Refresh").isoformat() if result.get("Last_Refresh") else None,
            "refresh_duration_ms": result.get("Refresh_Duration_MS", 0)
        }

        return {
            "success": True,
            "data": summary
        }

    except Exception as e:
        raise safe_http_error(500, e, "fetching overview summary")


@router.get("/instances", response_model=GenericResponse)
async def get_overview_instances(
    env: Optional[str] = Query(None, description="Filtrar por ambiente"),
    status: Optional[str] = Query(None, description="Filtrar por status (OK, WARNING, CRITICAL, OFFLINE)"),
    limit: int = Query(100, ge=1, le=500, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginacao")
):
    """
    Retorna lista de instancias com dados de saude.

    Permite filtrar por ambiente e status de saude.
    Ordenado por Health Score (menor primeiro).
    """
    try:
        conditions = []
        params = {"Limit": limit, "Offset": offset}

        if env:
            conditions.append("Env = @Env")
            params["Env"] = env.upper()

        if status:
            conditions.append("Health_Status = @Status")
            params["Status"] = status.upper()

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT
                Instance,
                Env,
                CAST(Is_Online AS INT) AS Is_Online,
                Health_Score,
                Health_Status,
                Availability_Score,
                Performance_Score,
                Space_Score,
                Backup_Score,
                Active_Problems,
                Problem_Summary,
                Databases_Total,
                Databases_Online,
                Databases_Offline,
                Blocked_Sessions,
                Long_Locks_Count,
                TLog_Issues,
                FG_Issues,
                Disk_Issues,
                Backup_Issues,
                AlwaysOn_Issues,
                Service_Issues,
                CAST(OS_CPU_Critical AS INT) AS OS_CPU_Critical,
                OS_CPU_Percent,
                CAST(OS_Memory_Critical AS INT) AS OS_Memory_Critical,
                OS_Memory_Percent,
                OS_Available_MB,
                Last_Refresh,
                Last_Collection
            FROM dbo.V_OVERVIEW_INSTANCE_HEALTH
            {where_clause}
            ORDER BY Health_Score ASC
            OFFSET @Offset ROWS
            FETCH NEXT @Limit ROWS ONLY
        """

        results = execute_query(query, params=params, fetch="all")

        # Contar total para paginacao
        count_query = f"SELECT COUNT(*) AS Total FROM dbo.V_OVERVIEW_INSTANCE_HEALTH {where_clause}"
        count_result = execute_query(count_query, params=params, fetch="one")
        total = count_result.get("Total", 0) if count_result else 0

        instances = []
        for row in results:
            instances.append({
                "instance": row.get("Instance"),
                "env": row.get("Env"),
                "is_online": bool(row.get("Is_Online", 0)),
                "health_score": float(row.get("Health_Score", 0) or 0),
                "health_status": row.get("Health_Status"),
                "scores": {
                    "availability": float(row.get("Availability_Score", 0) or 0),
                    "performance": float(row.get("Performance_Score", 0) or 0),
                    "space": float(row.get("Space_Score", 0) or 0),
                    "backup": float(row.get("Backup_Score", 0) or 0)
                },
                "active_problems": row.get("Active_Problems", 0),
                "problem_summary": row.get("Problem_Summary"),
                "databases": {
                    "total": row.get("Databases_Total", 0),
                    "online": row.get("Databases_Online", 0),
                    "offline": row.get("Databases_Offline", 0)
                },
                "issues": {
                    "blocked_sessions": row.get("Blocked_Sessions", 0),
                    "long_locks": row.get("Long_Locks_Count", 0),
                    "tlog": row.get("TLog_Issues", 0),
                    "filegroup": row.get("FG_Issues", 0),
                    "disk": row.get("Disk_Issues", 0),
                    "backup": row.get("Backup_Issues", 0),
                    "alwayson": row.get("AlwaysOn_Issues", 0),
                    "services": row.get("Service_Issues", 0)
                },
                "os": {
                    "cpu_critical": bool(row.get("OS_CPU_Critical", 0)),
                    "cpu_percent": float(row.get("OS_CPU_Percent") or 0) if row.get("OS_CPU_Percent") else None,
                    "memory_critical": bool(row.get("OS_Memory_Critical", 0)),
                    "memory_percent": float(row.get("OS_Memory_Percent") or 0) if row.get("OS_Memory_Percent") else None,
                    "available_mb": row.get("OS_Available_MB")
                },
                "last_refresh": row.get("Last_Refresh").isoformat() if row.get("Last_Refresh") else None,
                "last_collection": row.get("Last_Collection").isoformat() if row.get("Last_Collection") else None
            })

        return {
            "success": True,
            "data": instances,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total
            }
        }

    except Exception as e:
        raise safe_http_error(500, e, "fetching overview instances")


@router.get("/problems", response_model=GenericResponse)
async def get_overview_problems(
    env: Optional[str] = Query(None, description="Filtrar por ambiente"),
    limit: int = Query(20, ge=1, le=100, description="Limite de resultados")
):
    """
    Retorna top instancias com problemas.

    Ordenado por criticidade (OFFLINE > CRITICAL > WARNING) e depois por Health Score.
    """
    try:
        params = {"Limit": limit}

        if env:
            query = """
                SELECT TOP (@Limit)
                    Instance,
                    Env,
                    Health_Status,
                    Health_Score,
                    Active_Problems,
                    Problem_Summary,
                    Primary_Issue,
                    Last_Refresh
                FROM dbo.V_OVERVIEW_TOP_PROBLEMS
                WHERE Env = @Env
                ORDER BY
                    CASE Health_Status
                        WHEN 'OFFLINE' THEN 1
                        WHEN 'CRITICAL' THEN 2
                        WHEN 'WARNING' THEN 3
                        ELSE 4
                    END,
                    Health_Score ASC,
                    Active_Problems DESC
            """
            params["Env"] = env.upper()
        else:
            query = """
                SELECT TOP (@Limit)
                    Instance,
                    Env,
                    Health_Status,
                    Health_Score,
                    Active_Problems,
                    Problem_Summary,
                    Primary_Issue,
                    Last_Refresh
                FROM dbo.V_OVERVIEW_TOP_PROBLEMS
                ORDER BY
                    CASE Health_Status
                        WHEN 'OFFLINE' THEN 1
                        WHEN 'CRITICAL' THEN 2
                        WHEN 'WARNING' THEN 3
                        ELSE 4
                    END,
                    Health_Score ASC,
                    Active_Problems DESC
            """

        results = execute_query(query, params=params, fetch="all")

        problems = []
        for row in results:
            problems.append({
                "instance": row.get("Instance"),
                "env": row.get("Env"),
                "health_status": row.get("Health_Status"),
                "health_score": float(row.get("Health_Score", 0) or 0),
                "active_problems": row.get("Active_Problems", 0),
                "problem_summary": row.get("Problem_Summary"),
                "primary_issue": row.get("Primary_Issue"),
                "last_refresh": row.get("Last_Refresh").isoformat() if row.get("Last_Refresh") else None
            })

        return {
            "success": True,
            "data": problems,
            "count": len(problems)
        }

    except Exception as e:
        raise safe_http_error(500, e, "fetching overview problems")


@router.get("/environments", response_model=GenericResponse)
async def get_overview_environments():
    """
    Retorna lista de ambientes disponiveis.

    Util para popular dropdowns/filtros no frontend.
    """
    try:
        query = """
            SELECT DISTINCT Env
            FROM dbo.V_OVERVIEW_DASHBOARD_SUMMARY
            WHERE Env <> 'ALL'
            ORDER BY Env
        """

        results = execute_query(query, fetch="all")

        environments = [row.get("Env") for row in results if row.get("Env")]

        return {
            "success": True,
            "data": environments
        }

    except Exception as e:
        raise safe_http_error(500, e, "fetching overview environments")


@router.get("/health-distribution", response_model=GenericResponse)
async def get_health_distribution(
    env: Optional[str] = Query(None, description="Filtrar por ambiente")
):
    """
    Retorna distribuicao de saude das instancias.

    Dados para grafico de pizza/donut mostrando quantas instancias estao em cada status.
    """
    try:
        if env:
            query = """
                SELECT
                    Health_Status,
                    COUNT(*) AS Count
                FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT
                WHERE Env = @Env
                GROUP BY Health_Status
            """
            params = {"Env": env.upper()}
        else:
            query = """
                SELECT
                    Health_Status,
                    COUNT(*) AS Count
                FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT
                GROUP BY Health_Status
            """
            params = {}

        results = execute_query(query, params=params, fetch="all")

        distribution = {
            "ok": 0,
            "warning": 0,
            "critical": 0,
            "offline": 0
        }

        total = 0
        for row in results:
            status = row.get("Health_Status", "").lower()
            count = row.get("Count", 0)
            total += count
            if status in distribution:
                distribution[status] = count

        # Calcular percentuais
        percentages = {}
        for status, count in distribution.items():
            percentages[status] = round(count * 100.0 / total, 2) if total > 0 else 0

        return {
            "success": True,
            "data": {
                "counts": distribution,
                "percentages": percentages,
                "total": total,
                "env": env.upper() if env else "ALL"
            }
        }

    except Exception as e:
        raise safe_http_error(500, e, "fetching health distribution")


@router.get("/os-boot/{instance_name}", response_model=GenericResponse)
async def get_os_boot(instance_name: str):
    """Ultimo reboot do SO + arranque do servico SQL (card no Overview por servidor).

    Fonte: KPI_MSSQL_INST_AVAILABILITY_ACTIVE (coletor V1 via sql_monitoring;
    OS_Boot_Time derivado de sys.dm_os_sys_info.ms_ticks — zero acesso ao SO).
    Diagnostico: se o SQL arrancou DEPOIS do SO (margem 90 min, porque
    Uptime_Hours tem granularidade de hora), houve restart isolado do servico
    (crash/manual) em vez de reboot planeado de patching.
    """
    try:
        inst = instance_name.replace("\\", "_")
        row = execute_query(
            f"""
            SELECT TOP 1
                Instance,
                Uptime_Hours,
                OS_Boot_Time,
                DATEADD(HOUR, -ISNULL(Uptime_Hours, 0), GETDATE()) AS Sql_Start_Est,
                CASE WHEN OS_Boot_Time IS NULL THEN NULL
                     ELSE DATEDIFF(DAY, OS_Boot_Time, GETDATE()) END AS Os_Uptime_Days,
                CASE
                    WHEN OS_Boot_Time IS NULL THEN 'SEM_DADOS'
                    WHEN DATEADD(HOUR, -ISNULL(Uptime_Hours, 0), GETDATE())
                         > DATEADD(MINUTE, 90, OS_Boot_Time)
                        THEN 'RESTART_SERVICO_ISOLADO'
                    ELSE 'REBOOT_CONJUNTO'
                END AS Diagnostic,
                Update_TS
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WITH (NOLOCK)
            WHERE Instance = @Instance
            ORDER BY Update_TS DESC
            """,
            {"Instance": inst},
            fetch="one",
        )
        if not row:
            return JSONResponse(content={"success": True, "data": {"available": False}})

        def _iso(v):
            return v.isoformat() if hasattr(v, "isoformat") else v

        return JSONResponse(content={
            "success": True,
            "data": {
                "available": True,
                "instance": row.get("Instance"),
                "os_boot_time": _iso(row.get("OS_Boot_Time")),
                "os_uptime_days": row.get("Os_Uptime_Days"),
                "sql_uptime_hours": row.get("Uptime_Hours"),
                "sql_start_est": _iso(row.get("Sql_Start_Est")),
                "diagnostic": row.get("Diagnostic"),
                "as_of": _iso(row.get("Update_TS")),
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching os-boot for {instance_name}")


@router.post("/refresh", response_model=MessageResponse)
async def refresh_overview(request: Request):
    """
    Executa refresh manual dos dados do Overview Dashboard.

    Chama a procedure usp_refresh_overview_all para recalcular todos os dados.
    Rate limited: 2 chamadas por minuto para evitar sobrecarga.
    """
    try:
        start_time = datetime.now(timezone.utc)

        # Executar procedure de refresh
        execute_procedure("dbo.usp_refresh_overview_all")

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.info("overview_refresh_completed", duration_ms=duration_ms)

        return {
            "success": True,
            "message": "Overview Dashboard atualizado com sucesso",
            "duration_ms": duration_ms,
            "timestamp": end_time.isoformat()
        }

    except Exception as e:
        raise safe_http_error(500, e, "refreshing overview dashboard")


@router.get("/instance/{instance_name}", response_model=DashboardResponse)
async def get_instance_details(instance_name: str):
    """
    Retorna detalhes de uma instancia especifica.
    """
    try:
        query = """
            SELECT
                s.Instance,
                s.Env,
                CAST(s.Is_Online AS INT) AS Is_Online,
                s.Health_Score,
                s.Health_Status,
                s.Availability_Score,
                s.Performance_Score,
                s.Space_Score,
                s.Backup_Score,
                s.Active_Problems,
                s.Problem_Summary,
                s.Databases_Total,
                s.Databases_Online,
                s.Databases_Offline,
                s.Blocked_Sessions,
                s.Blocked_Users,
                s.Long_Locks_Count,
                s.Active_Processes,
                s.TLog_Critical_Count,
                s.TLog_Warning_Count,
                s.TLog_Max_Percent,
                s.FG_Critical_Count,
                s.FG_Warning_Count,
                s.FG_Max_Percent,
                s.Disk_Critical_Count,
                s.Disk_Warning_Count,
                s.Disk_Min_Free_GB,
                s.Backup_Full_Overdue,
                s.Backup_Log_Overdue,
                CAST(s.Has_AlwaysOn AS INT) AS Has_AlwaysOn,
                s.AlwaysOn_Healthy,
                s.AlwaysOn_UnHealthy,
                s.Services_Running,
                s.Services_Stopped,
                CAST(s.OS_CPU_Critical AS INT) AS OS_CPU_Critical,
                s.OS_CPU_Percent,
                CAST(s.OS_Memory_Critical AS INT) AS OS_Memory_Critical,
                s.OS_Memory_Percent,
                s.OS_Available_MB,
                s.Last_Refresh,
                s.Last_Collection
            FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT s
            WHERE s.Instance = @Instance
        """

        result = execute_query(query, params={"Instance": instance_name}, fetch="one")

        if not result:
            raise HTTPException(status_code=404, detail=f"Instancia '{instance_name}' nao encontrada")

        instance_data = {
            "instance": result.get("Instance"),
            "env": result.get("Env"),
            "is_online": bool(result.get("Is_Online", 0)),
            "health": {
                "score": float(result.get("Health_Score", 0) or 0),
                "status": result.get("Health_Status"),
                "availability_score": float(result.get("Availability_Score", 0) or 0),
                "performance_score": float(result.get("Performance_Score", 0) or 0),
                "space_score": float(result.get("Space_Score", 0) or 0),
                "backup_score": float(result.get("Backup_Score", 0) or 0)
            },
            "problems": {
                "count": result.get("Active_Problems", 0),
                "summary": result.get("Problem_Summary")
            },
            "databases": {
                "total": result.get("Databases_Total", 0),
                "online": result.get("Databases_Online", 0),
                "offline": result.get("Databases_Offline", 0)
            },
            "performance": {
                "blocked_sessions": result.get("Blocked_Sessions", 0),
                "blocked_users": result.get("Blocked_Users", 0),
                "long_locks": result.get("Long_Locks_Count", 0),
                "active_processes": result.get("Active_Processes", 0)
            },
            "space": {
                "tlog": {
                    "critical": result.get("TLog_Critical_Count", 0),
                    "warning": result.get("TLog_Warning_Count", 0),
                    "max_percent": float(result.get("TLog_Max_Percent", 0) or 0)
                },
                "filegroup": {
                    "critical": result.get("FG_Critical_Count", 0),
                    "warning": result.get("FG_Warning_Count", 0),
                    "max_percent": float(result.get("FG_Max_Percent", 0) or 0)
                },
                "disk": {
                    "critical": result.get("Disk_Critical_Count", 0),
                    "warning": result.get("Disk_Warning_Count", 0),
                    "min_free_gb": float(result.get("Disk_Min_Free_GB") or 0) if result.get("Disk_Min_Free_GB") else None
                }
            },
            "backup": {
                "full_overdue": result.get("Backup_Full_Overdue", 0),
                "log_overdue": result.get("Backup_Log_Overdue", 0)
            },
            "alwayson": {
                "has_alwayson": bool(result.get("Has_AlwaysOn", 0)),
                "healthy": result.get("AlwaysOn_Healthy", 0),
                "unhealthy": result.get("AlwaysOn_UnHealthy", 0)
            },
            "services": {
                "running": result.get("Services_Running", 0),
                "stopped": result.get("Services_Stopped", 0)
            },
            "os": {
                "cpu": {
                    "critical": bool(result.get("OS_CPU_Critical", 0)),
                    "percent": float(result.get("OS_CPU_Percent") or 0) if result.get("OS_CPU_Percent") else None
                },
                "memory": {
                    "critical": bool(result.get("OS_Memory_Critical", 0)),
                    "percent": float(result.get("OS_Memory_Percent") or 0) if result.get("OS_Memory_Percent") else None,
                    "available_mb": result.get("OS_Available_MB")
                }
            },
            "last_refresh": result.get("Last_Refresh").isoformat() if result.get("Last_Refresh") else None,
            "last_collection": result.get("Last_Collection").isoformat() if result.get("Last_Collection") else None
        }

        return {
            "success": True,
            "data": instance_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching instance details for {instance_name}")

# ========================================
# NOVOS ENDPOINTS - OVERVIEW RAPIDO
# ========================================

@router.get("/instance/{instance_name}/quick", response_model=DashboardResponse)
async def get_instance_quick(instance_name: str):
    """
    Retorna dados RAPIDOS de uma instancia para o Overview.
    Apenas dados essenciais para carga inicial rapida.
    """
    try:
        query = """
            SELECT
                s.Instance,
                s.Env,
                CAST(s.Is_Online AS INT) AS Is_Online,
                s.Health_Score,
                s.Health_Status,
                s.OS_CPU_Percent,
                s.OS_Memory_Percent,
                s.OS_Available_MB,
                s.Databases_Total,
                s.Databases_Online,
                s.Databases_Offline,
                s.Services_Running,
                s.Services_Stopped,
                s.Active_Problems,
                s.Last_Refresh,
                s.Last_Collection
            FROM dbo.OVERVIEW_INSTANCE_SNAPSHOT s
            WHERE s.Instance = @Instance
        """

        result = execute_query(query, params={"Instance": instance_name}, fetch="one")

        if not result:
            raise HTTPException(status_code=404, detail=f"Instancia '{instance_name}' nao encontrada")

        return {
            "success": True,
            "data": {
                "instance": result.get("Instance"),
                "env": result.get("Env"),
                "is_online": bool(result.get("Is_Online", 0)),
                "health_score": float(result.get("Health_Score", 0) or 0),
                "health_status": result.get("Health_Status"),
                "cpu_percent": float(result.get("OS_CPU_Percent") or 0) if result.get("OS_CPU_Percent") else None,
                "memory_percent": float(result.get("OS_Memory_Percent") or 0) if result.get("OS_Memory_Percent") else None,
                "memory_available_mb": result.get("OS_Available_MB"),
                "databases_total": result.get("Databases_Total", 0),
                "databases_online": result.get("Databases_Online", 0),
                "databases_offline": result.get("Databases_Offline", 0),
                "services_running": result.get("Services_Running", 0),
                "services_stopped": result.get("Services_Stopped", 0),
                "active_problems": result.get("Active_Problems", 0),
                "last_refresh": result.get("Last_Refresh").isoformat() if result.get("Last_Refresh") else None,
                "last_collection": result.get("Last_Collection").isoformat() if result.get("Last_Collection") else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching quick data for {instance_name}")


@router.get("/instance/{instance_name}/databases", response_model=GenericResponse)
async def get_instance_databases(instance_name: str):
    """
    Retorna lista de databases de uma instancia com status consolidado.
    """
    try:
        # Normalizar nome da instancia
        instance_underscore = instance_name.replace('\\', '_')
        instance_backslash = instance_name.replace('_', '\\')
        
        query = """
            SELECT 
                db.Instance,
                db.[Database],
                db.State,
                CAST(db.Is_Available AS INT) AS Is_Available,
                db.Recovery_Model,
                db.Mirroring_Role,
                tlog.Percent_Used AS TLog_Percent,
                fg.Max_Percent AS FG_Max_Percent,
                fg.Critical_Count AS FG_Critical,
                fg.Warning_Count AS FG_Warning
            FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG db WITH (NOLOCK)
            LEFT JOIN (
                SELECT Instance, [Database], MAX(Percent_Used) AS Percent_Used
                FROM dbo.KPI_MSSQL_TLOG_USAGE_STG WITH (NOLOCK)
                WHERE Instance IN (@InstanceUnderscore, @InstanceBackslash)
                GROUP BY Instance, [Database]
            ) tlog ON db.Instance = tlog.Instance AND db.[Database] = tlog.[Database]
            LEFT JOIN (
                SELECT 
                    Instance, 
                    [Database], 
                    MAX(Percent_Used) AS Max_Percent,
                    SUM(CASE WHEN Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical_Count,
                    SUM(CASE WHEN Percent_Used >= 95 AND Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning_Count
                FROM dbo.KPI_MSSQL_FG_USAGE_STG WITH (NOLOCK)
                WHERE Instance IN (@InstanceUnderscore, @InstanceBackslash)
                GROUP BY Instance, [Database]
            ) fg ON db.Instance = fg.Instance AND db.[Database] = fg.[Database]
            WHERE db.Instance IN (@InstanceUnderscore, @InstanceBackslash)
            ORDER BY 
                CASE WHEN db.State != 'ONLINE' THEN 0 ELSE 1 END,
                CASE WHEN CAST(db.Is_Available AS INT) = 0 THEN 0 ELSE 1 END,
                db.[Database]
        """

        results = execute_query(query, params={
            "InstanceUnderscore": instance_underscore,
            "InstanceBackslash": instance_backslash
        }, fetch="all")

        databases = []
        for row in results or []:
            state = row.get("State", "UNKNOWN")
            is_available = bool(row.get("Is_Available", 1))
            tlog_pct = float(row.get("TLog_Percent") or 0) if row.get("TLog_Percent") else None
            fg_max = float(row.get("FG_Max_Percent") or 0) if row.get("FG_Max_Percent") else None
            
            if state != "ONLINE" or not is_available:
                status = "CRITICAL"
            elif (tlog_pct and tlog_pct >= 95) or (fg_max and fg_max >= 98):
                status = "CRITICAL"
            elif (tlog_pct and tlog_pct >= 80) or (fg_max and fg_max >= 95):
                status = "WARNING"
            else:
                status = "OK"
            
            databases.append({
                "database": row.get("Database"),
                "state": state,
                "is_available": is_available,
                "recovery_model": row.get("Recovery_Model"),
                "mirroring_role": row.get("Mirroring_Role"),
                "tlog_percent": tlog_pct,
                "fg_max_percent": fg_max,
                "fg_critical": row.get("FG_Critical", 0),
                "fg_warning": row.get("FG_Warning", 0),
                "status": status
            })

        return {
            "success": True,
            "instance": instance_name,
            "count": len(databases),
            "data": databases
        }

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching databases for {instance_name}")
