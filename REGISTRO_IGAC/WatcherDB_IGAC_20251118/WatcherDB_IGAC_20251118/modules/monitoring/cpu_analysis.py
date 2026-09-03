import logging
from typing import Dict, List


logger = logging.getLogger(__name__)


def _safe_int(value, default=0) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


def calculate_recommended_maxdop(physical_cpu_count: int, cpu_count: int) -> Dict:
    if physical_cpu_count <= 1:
        recommended_maxdop = 1
        reason = "Servidor com apenas 1 core físico"
    elif physical_cpu_count <= 8:
        recommended_maxdop = physical_cpu_count
        reason = f"Servidor com {physical_cpu_count} cores físicos (usar todos)"
    else:
        recommended_maxdop = 8
        reason = f"Servidor com {physical_cpu_count} cores (máximo recomendado: 8)"
    return {"recommended_maxdop": recommended_maxdop, "reason": reason}


def validate_cost_threshold(cost_threshold: int) -> Dict:
    if cost_threshold == 5:
        status = "danger"
        message = "Cost threshold está no PADRÃO (5) - MUITO BAIXO! Pode causar excesso de paralelismo."
        recommendation = 40
    elif cost_threshold < 25:
        status = "warning"
        message = f"Cost threshold baixo ({cost_threshold}). Considere aumentar para 25-50."
        recommendation = 40
    elif 25 <= cost_threshold <= 50:
        status = "success"
        message = f"Cost threshold bem configurado ({cost_threshold})."
        recommendation = cost_threshold
    else:
        status = "info"
        message = f"Cost threshold alto ({cost_threshold}). Pode estar limitando paralelismo."
        recommendation = 40
    return {"status": status, "message": message, "recommendation": recommendation}


def calculate_cpu_pressure(runnable_tasks: int, schedulers_online: int) -> Dict:
    avg = (runnable_tasks / schedulers_online) if schedulers_online else 0.0
    if avg <= 2:
        status, color, message = "HEALTHY", "success", "CPU sem pressão"
    elif avg <= 10:
        status, color, message = "WARNING", "warning", "CPU começando a ter pressão"
    else:
        status, color, message = "CRITICAL", "danger", "CPU COM PRESSÃO CRÍTICA! Tasks aguardando scheduler."
    return {
        "runnable_tasks": runnable_tasks,
        "avg_runnable_per_scheduler": round(avg, 2),
        "status": status,
        "color": color,
        "message": message,
    }


def generate_cpu_alerts(data: Dict) -> List[Dict]:
    alerts: List[Dict] = []
    if data.get("sqlserver_cpu_pct", 0) > 80:
        alerts.append({"level": "danger", "message": f"CPU SQL Server ALTA: {data['sqlserver_cpu_pct']}%! Investigar queries pesadas."})
    elif data.get("sqlserver_cpu_pct", 0) > 60:
        alerts.append({"level": "warning", "message": f"CPU SQL Server elevada: {data['sqlserver_cpu_pct']}%"})

    maxdop_check = calculate_recommended_maxdop(_safe_int(data.get("physical_cpu_count")), _safe_int(data.get("cpu_count")))
    if _safe_int(data.get("maxdop")) != maxdop_check["recommended_maxdop"]:
        alerts.append({
            "level": "warning",
            "message": f"MAXDOP atual ({data.get('maxdop')}) diferente do recomendado ({maxdop_check['recommended_maxdop']}). {maxdop_check['reason']}"
        })

    cost_check = validate_cost_threshold(_safe_int(data.get("cost_threshold")))
    if cost_check["status"] in ("danger", "warning"):
        alerts.append({"level": cost_check["status"], "message": cost_check["message"]})

    pressure = calculate_cpu_pressure(_safe_int(data.get("runnable_tasks_count")), _safe_int(data.get("schedulers_online")))
    if pressure["status"] != "HEALTHY":
        alerts.append({
            "level": "danger" if pressure["status"] == "CRITICAL" else "warning",
            "message": f"{pressure['message']} ({pressure['avg_runnable_per_scheduler']:.1f} runnable tasks/scheduler)"
        })

    usage_pct = 0.0
    if _safe_int(data.get("max_workers_count")) > 0:
        usage_pct = ( _safe_int(data.get("current_workers_count")) * 100.0 ) / _safe_int(data.get("max_workers_count"))
    if usage_pct > 80:
        alerts.append({
            "level": "danger",
            "message": f"Worker threads próximo do limite: {usage_pct:.1f}% ({data.get('current_workers_count')}/{data.get('max_workers_count')})"
        })

    return alerts


def _server_id_from_name(server_name: str) -> str:
    """Converte nome exibido (HOST\\INSTANCIA) em server_id do WatcherDB (HOST_INSTANCIA).
    Trata instância DEFAULT removendo o sufixo."""
    if "\\" in server_name:
        host, inst = server_name.split("\\", 1)
        if inst.upper() == "DEFAULT":
            return host  # usar somente host
        return f"{host}_{inst}"
    return server_name


async def get_server_cpu_analysis(server_name: str, sql_monitoring) -> Dict:
    """Executa a análise de CPU via sql_monitoring (async)."""
    query = """
    SELECT
        cpu_count = (SELECT cpu_count FROM sys.dm_os_sys_info),
        hyperthread_ratio = (SELECT hyperthread_ratio FROM sys.dm_os_sys_info),
        physical_cpu_count = (SELECT cpu_count / NULLIF(hyperthread_ratio,0) FROM sys.dm_os_sys_info),

        sqlserver_cpu_pct = (
            SELECT TOP 1 SQLProcessUtilization FROM (
                SELECT 
                    record.value('(./Record/@id)[1]', 'int') AS record_id,
                    record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS SQLProcessUtilization,
                    DATEADD(ms, -1 * ((SELECT ms_ticks FROM sys.dm_os_sys_info) - [timestamp]), GETDATE()) AS EventTime
                FROM (
                    SELECT [timestamp], CONVERT(xml, record) AS [record]
                    FROM sys.dm_os_ring_buffers 
                    WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR' AND record LIKE '%<SystemHealth>%'
                ) AS x
            ) AS y ORDER BY record_id DESC
        ),
        system_idle_pct = (
            SELECT TOP 1 SystemIdle FROM (
                SELECT 
                    record.value('(./Record/@id)[1]', 'int') AS record_id,
                    record.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS SystemIdle,
                    DATEADD(ms, -1 * ((SELECT ms_ticks FROM sys.dm_os_sys_info) - [timestamp]), GETDATE()) AS EventTime
                FROM (
                    SELECT [timestamp], CONVERT(xml, record) AS [record]
                    FROM sys.dm_os_ring_buffers 
                    WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR' AND record LIKE '%<SystemHealth>%'
                ) AS x
            ) AS y ORDER BY record_id DESC
        ),

        maxdop = (SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name = 'max degree of parallelism'),
        cost_threshold = (SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name = 'cost threshold for parallelism'),

        max_workers_count = (SELECT max_workers_count FROM sys.dm_os_sys_info),
        current_workers_count = (SELECT COUNT(*) FROM sys.dm_os_workers),
        schedulers_online = (SELECT COUNT(*) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE'),
        runnable_tasks_count = (SELECT SUM(runnable_tasks_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE'),
        pending_disk_io_count = (SELECT SUM(pending_disk_io_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE'),

        is_hadr_enabled = CAST(SERVERPROPERTY('IsHadrEnabled') AS INT),
        ag_name = (
            SELECT TOP 1 ag.name 
            FROM sys.dm_hadr_availability_replica_states AS ars
            INNER JOIN sys.availability_groups AS ag ON ars.group_id = ag.group_id
            WHERE ars.is_local = 1
        ),
        replica_role = (
            SELECT TOP 1 
                CASE ars.role WHEN 1 THEN 'PRIMARY' WHEN 2 THEN 'SECONDARY' ELSE 'RESOLVING' END
            FROM sys.dm_hadr_availability_replica_states AS ars
            WHERE ars.is_local = 1
        );
    """

    # Converter para server_id usado por sql_monitoring
    server_id = _server_id_from_name(server_name)
    logger.info(f"🔍 CPU Analysis em: {server_name} (id: {server_id})")
    # fallback: se HOST_DEFAULT não existir, tentar somente HOST
    # Tentar primeiro com server_id original
    result = await sql_monitoring.execute_query(server_id, query)
    logger.info(f"📊 Resultado da query: {result}")
    
    # Se falhou e é DEFAULT, tentar fallback
    if (not result or not result.get("success")) and server_id.endswith("_DEFAULT"):
        alt_id = server_id.replace("_DEFAULT", "")
        logger.info(f"⚙️ Fallback DEFAULT -> HOST: {server_id} -> {alt_id}")
        result = await sql_monitoring.execute_query(alt_id, query)
        logger.info(f"📊 Resultado do fallback: {result}")
    if not result or not result.get("success"):
        raise Exception(result.get("error", "Falha ao executar query de CPU"))

    rows = result.get("rows", [])
    if not rows:
        raise Exception("Nenhum dado retornado para CPU")

    row = rows[0]
    data: Dict = {
        "cpu_count": _safe_int(row.get("cpu_count")),
        "hyperthread_ratio": _safe_int(row.get("hyperthread_ratio")),
        "physical_cpu_count": _safe_int(row.get("physical_cpu_count")),
        "sqlserver_cpu_pct": _safe_int(row.get("sqlserver_cpu_pct")),
        "system_idle_pct": _safe_int(row.get("system_idle_pct")),
        "maxdop": _safe_int(row.get("maxdop")),
        "cost_threshold": _safe_int(row.get("cost_threshold")),
        "max_workers_count": _safe_int(row.get("max_workers_count")),
        "current_workers_count": _safe_int(row.get("current_workers_count")),
        "schedulers_online": _safe_int(row.get("schedulers_online")),
        "runnable_tasks_count": _safe_int(row.get("runnable_tasks_count")),
        "pending_disk_io_count": _safe_int(row.get("pending_disk_io_count")),
        "is_hadr_enabled": _safe_int(row.get("is_hadr_enabled")),
        "ag_name": row.get("ag_name"),
        "replica_role": row.get("replica_role"),
    }

    # Derivados
    data["other_processes_cpu_pct"] = max(0, 100 - data["sqlserver_cpu_pct"] - data["system_idle_pct"])

    maxdop_rec = calculate_recommended_maxdop(data["physical_cpu_count"], data["cpu_count"])
    data["recommended_maxdop"] = maxdop_rec["recommended_maxdop"]

    cost_check = validate_cost_threshold(data["cost_threshold"])
    data["recommended_cost_threshold"] = cost_check["recommendation"]

    pressure = calculate_cpu_pressure(data["runnable_tasks_count"], data["schedulers_online"])
    data["cpu_pressure_status"] = pressure["status"]
    data["avg_runnable_per_scheduler"] = pressure["avg_runnable_per_scheduler"]

    # Worker usage pct
    data["worker_usage_pct"] = (
        (data["current_workers_count"] * 100.0) / data["max_workers_count"]
        if data["max_workers_count"] else 0.0
    )

    data["alerts"] = generate_cpu_alerts(data)
    return data


