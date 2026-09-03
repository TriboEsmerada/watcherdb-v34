#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries - Performance endpoints.
Blocking, deadlocks, slow queries, I/O stats, sessions, index fragmentation, statistics.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
import logging

from modules.monitoring.queries import SQLQueries
from api.error_helpers import safe_http_error
from api.routers.queries.helpers import execute_query_on_server, _serialize_result
from api.models import QueryResultResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/blocking/{server_id}", response_model=QueryResultResponse)
async def get_blocking_hierarchy(server_id: str):
    """Obtem hierarquia de bloqueios"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BLOCKING_HIERARCHY)
        return JSONResponse(content={"server_id": server_id, "blocking_chains": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching blocking hierarchy for {server_id}")


@router.get("/deadlocks/{server_id}", response_model=QueryResultResponse)
async def get_deadlocks(server_id: str):
    """Obtem analise de deadlocks (ultimas 24 horas)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.DEADLOCKS_ANALYSIS)
        return JSONResponse(content={"server_id": server_id, "deadlocks": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching deadlocks for {server_id}")


@router.get("/database-io-stats/{server_id}", response_model=QueryResultResponse)
async def get_database_io_stats(server_id: str):
    """Obtem estatisticas de I/O por database"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.DATABASE_IO_STATS)
        return JSONResponse(content={"server_id": server_id, "database_io_stats": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching database I/O stats for {server_id}")


@router.get("/slow-queries/{server_id}", response_model=QueryResultResponse)
async def get_slow_queries(server_id: str):
    """Obtem top queries lentas"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TOP_SLOW_QUERIES_DETAILED)
        return JSONResponse(content={"server_id": server_id, "slow_queries": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching slow queries for {server_id}")


@router.get("/sessions/{server_id}", response_model=QueryResultResponse)
async def get_problematic_sessions(server_id: str):
    """Obtem sessoes problematicas"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.PROBLEMATIC_SESSIONS)
        return JSONResponse(content={"server_id": server_id, "problematic_sessions": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching problematic sessions for {server_id}")


# 2026-07-17 (tab Sessions): equivalente ao painel Processes do Activity Monitor
# do SSMS — sessoes activas com login/host/comando/waits/blocking/query em curso.
# Read-only puro (DMVs; sql_monitoring tem VIEW SERVER STATE). head_blocker = 1
# quando a sessao bloqueia outras e nao esta ela propria bloqueada.
ACTIVE_SESSIONS_QUERY = """
SELECT
    s.session_id,
    s.is_user_process AS user_process,
    ISNULL(s.login_name, '') AS login_name,
    ISNULL(COALESCE(DB_NAME(r.database_id), DB_NAME(s.database_id)), '') AS database_name,
    ISNULL(r.status, '') AS task_state,
    ISNULL(r.command, '') AS command,
    ISNULL(s.program_name, '') AS application,
    ISNULL(r.wait_time, 0) AS wait_time_ms,
    ISNULL(r.wait_type, '') AS wait_type,
    ISNULL(r.wait_resource, '') AS wait_resource,
    ISNULL(NULLIF(r.blocking_session_id, 0), 0) AS blocked_by,
    CASE WHEN ISNULL(r.blocking_session_id, 0) = 0
              AND EXISTS (SELECT 1 FROM sys.dm_exec_requests rb WHERE rb.blocking_session_id = s.session_id)
         THEN 1 ELSE 0 END AS head_blocker,
    s.memory_usage * 8 AS memory_use_kb,
    ISNULL(s.host_name, '') AS host_name,
    ISNULL(rg.name, 'default') AS workload_group,
    ISNULL(s.status, '') AS session_status,
    s.cpu_time AS cpu_time_ms,
    CONVERT(VARCHAR(19), s.last_request_start_time, 120) AS last_request_start,
    -- 2026-07-17: 4000 truncava procedures/batches grandes ao copiar (report owner).
    -- 100k cobre praticamente qualquer batch real; so sessoes COM request activo
    -- trazem texto, o payload nao explode.
    ISNULL(SUBSTRING(t.text, 1, 100000), '') AS sql_text
FROM sys.dm_exec_sessions s
LEFT JOIN sys.dm_exec_requests r ON r.session_id = s.session_id
LEFT JOIN sys.resource_governor_workload_groups rg ON rg.group_id = s.group_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE s.session_id <> @@SPID
ORDER BY s.session_id;
"""


@router.get("/active-sessions/{server_id}", response_model=QueryResultResponse)
async def get_active_sessions(server_id: str):
    """Sessoes activas estilo Activity Monitor (tab Sessions do portal)"""
    try:
        result = await execute_query_on_server(server_id, ACTIVE_SESSIONS_QUERY)
        return JSONResponse(content={"server_id": server_id, "active_sessions": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching active sessions for {server_id}")


@router.get("/index-fragmentation/{server_id}", response_model=QueryResultResponse)
async def get_index_fragmentation(server_id: str):
    """Obtem indices fragmentados (v1.4.8.1 - com suporte a HEAP e QUOTENAME)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.INDEX_FRAGMENTATION)
        return JSONResponse(content={"server_id": server_id, "index_fragmentation": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching index fragmentation for {server_id}")


@router.get("/statistics/{server_id}", response_model=QueryResultResponse)
async def get_statistics_outdated(server_id: str):
    """Obtem estatisticas desatualizadas"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.STATISTICS_OUTDATED)
        return JSONResponse(content={"server_id": server_id, "statistics": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching outdated statistics for {server_id}")


@router.get("/database-connections/{server_id}", response_model=QueryResultResponse)
async def get_database_connections(server_id: str):
    """Obtem numero de conexoes por database"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.DATABASE_CONNECTIONS)
        return JSONResponse(content={"server_id": server_id, "database_connections": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching database connections for {server_id}")


@router.get("/disk-io-diagnostics/{server_id}", response_model=QueryResultResponse)
async def get_disk_io_diagnostics(server_id: str):
    """Diagnostico de I/O por arquivo de banco - latencia, IOPS e throughput via sys.dm_io_virtual_file_stats"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.DISK_IO_DIAGNOSTICS, command_timeout=120)
        return JSONResponse(content={"server_id": server_id, "disk_io": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching disk I/O diagnostics for {server_id}")


@router.get("/missing-index-analysis/{server_id}", response_model=QueryResultResponse)
async def get_missing_index_analysis(server_id: str, database: Optional[str] = Query(None)):
    """Obtem analise de indices faltantes com alto impacto - Suporta filtro por database"""
    try:
        query = SQLQueries.get_missing_index_analysis_filtered(database)
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "database": database or "ALL", "missing_index_analysis": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching missing index analysis for {server_id}")


@router.get("/sql-agent-jobs/{server_id}", response_model=QueryResultResponse)
async def get_sql_agent_jobs_failing(server_id: str):
    """Obtem jobs SQL Agent falhando"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.SQL_AGENT_JOBS_FAILING)
        return JSONResponse(content={"server_id": server_id, "failing_jobs": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching SQL Agent jobs for {server_id}")


@router.get("/mirroring/{server_id}", response_model=QueryResultResponse)
async def get_mirroring_logshipping(server_id: str):
    """Obtem status de Mirroring/Log Shipping"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.MIRRORING_LOGSHIPPING_STATUS)
        return JSONResponse(content={"server_id": server_id, "mirroring_logshipping": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching mirroring/log shipping status for {server_id}")
