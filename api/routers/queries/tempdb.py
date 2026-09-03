#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries - TempDB endpoints.
TempDB monitoring, growth analysis, culprits, villains, space analysis, diagnose.

NOTE: This module imports the original endpoint functions from sql_queries.py
to avoid duplicating the large amount of inline SQL and logic.
The actual endpoint functions are defined here referencing the shared helpers.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
import logging
import re

from modules.monitoring.queries import SQLQueries
from api.error_helpers import safe_http_error
from api.routers.queries.helpers import execute_query_on_server, _serialize_result
from api.models import QueryResultResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/tempdb/{server_id}", response_model=QueryResultResponse)
async def get_tempdb_monitoring(server_id: str):
    """
    Obtem monitoramento de TempDB - v2.0
    Retorna:
    - Overview do TempDB (tamanho total, usado, livre)
    - Viloes do TempDB (sessoes que mais consomem, ordenado DESC)
    """
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TEMPDB_MONITORING)
        return JSONResponse(content={"server_id": server_id, "tempdb": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching TempDB monitoring for {server_id}")


@router.get("/tempdb-space/{server_id}", response_model=QueryResultResponse)
async def get_tempdb_space_analysis(server_id: str):
    """Analise de espaco do TempDB para o modulo Space"""
    try:
        query = """
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
            vs.volume_mount_point as volume
        FROM tempdb.sys.database_files mf
        CROSS APPLY sys.dm_os_volume_stats(2, mf.file_id) vs
        WHERE mf.type_desc = 'ROWS'
        """
        result = await execute_query_on_server(server_id, query)
        serialized_result = _serialize_result(result)

        if serialized_result:
            total_size_gb = sum(r.get('size_gb', 0) or 0 for r in serialized_result)
            total_used_gb = sum(r.get('used_gb', 0) or 0 for r in serialized_result)
            total_free_gb = sum(r.get('free_gb', 0) or 0 for r in serialized_result)
            total_max_gb = sum(r.get('max_gb', 0) or 0 for r in serialized_result)

            disk_total_gb = serialized_result[0].get('disk_total_gb', 0) or 0
            disk_available_gb = serialized_result[0].get('disk_available_gb', 0) or 0
            volume = serialized_result[0].get('volume', 'N/A')

            used_percent = (total_used_gb / total_size_gb * 100) if total_size_gb > 0 else 0
            free_percent = 100 - used_percent

            response = {
                "server_id": server_id,
                "database_name": "tempdb",
                "filegroup_name": "TEMPDB_DATA",
                "file_count": len(serialized_result),
                "total_gb": round(total_size_gb, 2),
                "used_gb": round(total_used_gb, 2),
                "free_gb": round(total_free_gb, 2),
                "max_gb": round(total_max_gb, 2),
                "used_percent": round(used_percent, 2),
                "free_percent": round(free_percent, 2),
                "disk_total_gb": round(disk_total_gb, 2),
                "disk_available_gb": round(disk_available_gb, 2),
                "volume": volume,
                "files": serialized_result
            }
        else:
            response = {"server_id": server_id, "error": "no-tempdb-data"}

        return JSONResponse(content=response)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching TempDB space analysis for {server_id}")


@router.get("/tempdb-villains/{server_id}", response_model=QueryResultResponse)
async def get_tempdb_villains(server_id: str, top_n: int = Query(20, ge=1, le=100)):
    """Obtem os viloes do TempDB - sessoes que mais consomem espaco"""
    try:
        query = f"""
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
        result = await execute_query_on_server(server_id, query, command_timeout=15, connection_timeout=8)
        serialized_result = _serialize_result(result)
        return JSONResponse(content={
            "server_id": server_id,
            "villains": serialized_result,
            "count": len(serialized_result) if serialized_result else 0
        })
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching TempDB villains for {server_id}")
