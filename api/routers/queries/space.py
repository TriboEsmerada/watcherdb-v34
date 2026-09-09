#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries - Space endpoints.
Log space, file space detail, file growth, databases, disk volumes, disk files,
filegroup growth history/forecast.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
import logging
import time

from modules.monitoring.queries import SQLQueries
from api.error_helpers import safe_http_error
from api.routers.queries.helpers import (
    execute_query_on_server, _serialize_result,
    _DATABASES_CACHE, _DATABASES_CACHE_TTL, _set_cached_databases,
)
from api.models import QueryResultResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/log-space/{server_id}", response_model=QueryResultResponse)
async def get_log_space(server_id: str):
    """Obtem espaco recuperavel por database (DATA + LOG) via dynamic SQL batch"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.LOG_SPACE_USAGE, command_timeout=120)
        return JSONResponse(content={"server_id": server_id, "log_space": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching log space for {server_id}")


@router.get("/file-space-detail/{server_id}", response_model=QueryResultResponse)
async def get_file_space_detail(server_id: str):
    """Detalhe por ficheiro individual com SIZE, MAXSIZE, GROWTH e sugestoes de redimensionamento"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.FILE_SPACE_DETAIL, command_timeout=120)
        return JSONResponse(content={"server_id": server_id, "files": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching file space detail for {server_id}")


@router.get("/file-growth/{server_id}", response_model=QueryResultResponse)
async def get_file_growth(server_id: str, database: Optional[str] = Query(None)):
    """Obtem monitoramento de crescimento de arquivos"""
    try:
        safe_db = (database or "").replace("]", "]]")
        base_query = """
        SELECT
            d.name as database_name,
            f.name as file_name,
            f.type_desc as file_type,
            CASE
                WHEN f.type_desc = 'LOG' THEN 'LOG'
                ELSE ISNULL(fg_info.filegroup_name, 'PRIMARY')
            END as filegroup_name,
            f.physical_name,
            CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2)) as current_size_mb,
            CASE
                WHEN f.max_size = -1 THEN 'Unlimited'
                WHEN f.max_size = 268435456 THEN '2TB (Default Max)'
                ELSE CAST(f.max_size * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
            END as max_size,
            CASE
                WHEN f.is_percent_growth = 1
                THEN CAST(f.growth AS VARCHAR(10)) + '%'
                ELSE CAST(f.growth * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
            END as growth_increment,
            CASE
                WHEN f.is_percent_growth = 1 AND f.growth >= 10
                THEN 'WARNING: Percent growth >= 10%%'
                WHEN f.is_percent_growth = 0 AND (f.growth * 8.0 / 1024) < 100
                THEN 'WARNING: Fixed growth < 100MB'
                ELSE 'OK'
            END as growth_recommendation
        FROM sys.databases d WITH(NOLOCK)
        INNER JOIN sys.master_files f WITH(NOLOCK) ON d.database_id = f.database_id
        OUTER APPLY (
            SELECT TOP 1 fg.name as filegroup_name
            FROM sys.filegroups fg WITH(NOLOCK)
            WHERE fg.data_space_id = f.data_space_id
            AND f.type_desc = 'ROWS'
        ) fg_info
        WHERE d.database_id > 4
        AND d.state = 0
        """

        if safe_db:
            query = base_query + f"\n        AND d.name = '{safe_db}'\n        ORDER BY d.name, f.type, f.file_id"
        else:
            query = base_query + "\n        ORDER BY d.name, f.type, f.file_id"

        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "file_growth": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching file growth for {server_id}")


@router.get("/databases/{server_id}", response_model=QueryResultResponse)
async def get_databases(server_id: str):
    """Lista todas as bases de dados do servidor"""
    try:
        cached_entry = _DATABASES_CACHE.get(server_id.upper())
        if cached_entry and time.time() - cached_entry["ts"] <= _DATABASES_CACHE_TTL:
            return JSONResponse(content={
                "success": True,  # 2026-09-09: probe/cartao do Overview exigem esta chave
                "server_id": server_id,
                "databases": cached_entry["data"],
                "server_info": cached_entry.get("server_info", {}),
                "cached": True
            })

        query = """
        SELECT
            d.name as database_name,
            d.database_id,
            d.state_desc,
            d.recovery_model_desc,
            d.collation_name,
            d.is_read_only,
            CASE WHEN d.state = 0 AND HAS_DBACCESS(d.name) = 1 THEN 1 ELSE 0 END as is_accessible,
            CASE WHEN adc.database_name IS NOT NULL THEN 1 ELSE 0 END as is_ag,
            -- 2026-07-17: replica secundaria nao-legivel => HAS_DBACCESS=0 e' NORMAL
            -- (AlwaysOn by design, nao avaria). role=2 = SECONDARY na replica local.
            CASE WHEN drs.database_id IS NOT NULL AND ars.role = 2 THEN 1 ELSE 0 END as is_ag_secondary,
            CAST(ISNULL(mf_size.total_size_mb, 0) / 1024.0 AS DECIMAL(12,2)) as size_gb
        FROM sys.databases d WITH(NOLOCK)
        LEFT JOIN sys.availability_databases_cluster adc ON d.name = adc.database_name
        LEFT JOIN sys.dm_hadr_database_replica_states drs ON drs.database_id = d.database_id AND drs.is_local = 1
        LEFT JOIN sys.dm_hadr_availability_replica_states ars ON ars.replica_id = drs.replica_id AND ars.is_local = 1
        LEFT JOIN (
            SELECT database_id, SUM(CAST(size AS BIGINT)) * 8.0 / 1024.0 as total_size_mb
            FROM sys.master_files WITH(NOLOCK)
            GROUP BY database_id
        ) mf_size ON d.database_id = mf_size.database_id
        ORDER BY d.name
        """
        result = await execute_query_on_server(server_id, query, command_timeout=15, connection_timeout=8)
        serialized_result = _serialize_result(result)

        server_info = {}
        try:
            version_query = """
            SELECT
                CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(30)) AS product_version,
                CAST(SERVERPROPERTY('ProductLevel') AS VARCHAR(20)) AS product_level,
                CAST(SERVERPROPERTY('Edition') AS VARCHAR(80)) AS edition,
                SUBSTRING(@@VERSION, 1, 60) AS version_string
            """
            ver_result = await execute_query_on_server(server_id, version_query, command_timeout=10, connection_timeout=5)
            ver_data = _serialize_result(ver_result)
            if ver_data and len(ver_data) > 0:
                server_info = ver_data[0]
        except Exception as ve:
            logger.warning(f"Nao foi possivel obter versao do servidor {server_id}: {ve}")

        if serialized_result:
            _set_cached_databases(server_id, serialized_result, server_info)

        return JSONResponse(content={
            "success": True,  # 2026-09-09: probe/cartao do Overview exigem esta chave
            "server_id": server_id,
            "databases": serialized_result,
            "server_info": server_info,
            "cached": False
        })
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"listing databases for {server_id}")


@router.get("/disk-volumes/{server_id}", response_model=QueryResultResponse)
async def get_disk_volumes(server_id: str):
    """Obtem informacoes de volumes/discos do servidor via sys.dm_os_volume_stats"""
    try:
        query = """
        SELECT DISTINCT
            vs.volume_mount_point as drive,
            vs.logical_volume_name as label,
            CAST(vs.total_bytes / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(12,2)) as total_gb,
            CAST(vs.available_bytes / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(12,2)) as free_gb,
            CAST((vs.total_bytes - vs.available_bytes) / 1024.0 / 1024.0 / 1024.0 AS DECIMAL(12,2)) as used_gb,
            CAST(100.0 * (vs.total_bytes - vs.available_bytes) / NULLIF(vs.total_bytes, 0) AS DECIMAL(5,1)) as used_percent,
            vs.file_system_type as filesystem
        FROM sys.master_files mf
        CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
        ORDER BY vs.volume_mount_point
        """
        result = await execute_query_on_server(server_id, query)
        serialized_result = _serialize_result(result)
        return JSONResponse(content={"server_id": server_id, "volumes": serialized_result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching disk volumes for {server_id}")


@router.get("/disk-files/{server_id}", response_model=QueryResultResponse)
async def get_disk_files(server_id: str, drive: str = Query(..., description="Volume mount point (e.g., 'F:\\' or 'F:\\DATA1\\')")):
    """Obtem arquivos de banco de dados em um volume especifico usando volume_mount_point real"""
    try:
        drive_path = drive.strip()
        if not drive_path.endswith('\\'):
            drive_path += '\\'

        query = f"""
        SELECT
            d.name as database_name,
            mf.name as logical_name,
            mf.type_desc as file_type,
            mf.physical_name as physical_path,
            CAST(mf.size * 8.0 / 1024.0 AS DECIMAL(12,2)) as size_mb,
            CAST(mf.size * 8.0 / 1024.0 / 1024.0 AS DECIMAL(12,3)) as size_gb,
            mf.data_space_id,
            CASE WHEN mf.is_percent_growth = 1
                THEN CAST(mf.growth AS VARCHAR) + '%'
                ELSE CAST(CAST(mf.growth * 8.0 / 1024.0 AS INT) AS VARCHAR) + ' MB'
            END as growth_setting,
            CASE WHEN mf.max_size = -1 THEN 'Unlimited'
                 WHEN mf.max_size = 268435456 THEN '2 TB'
                 ELSE CAST(CAST(mf.max_size * 8.0 / 1024.0 / 1024.0 AS DECIMAL(12,2)) AS VARCHAR) + ' GB'
            END as max_size_formatted,
            d.state_desc as db_state,
            vs.volume_mount_point as actual_volume
        FROM sys.master_files mf WITH(NOLOCK)
        JOIN sys.databases d WITH(NOLOCK) ON mf.database_id = d.database_id
        CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
        WHERE vs.volume_mount_point = '{drive_path}'
        ORDER BY mf.size DESC
        """
        result = await execute_query_on_server(server_id, query)
        serialized_result = _serialize_result(result)

        # Buscar nomes dos filegroups cross-database
        dbs_with_rows = list(set(
            f['database_name'] for f in serialized_result
            if f.get('file_type') == 'ROWS' and f.get('db_state') == 'ONLINE'
        ))
        fg_map = {}
        if dbs_with_rows:
            try:
                union_parts = []
                for db in dbs_with_rows:
                    safe_db_str = db.replace("'", "''").replace("[", "[[").replace("]", "]]")
                    safe_db_bracket = db.replace("]", "]]")
                    union_parts.append(
                        f"SELECT '{safe_db_str}' as db_name, data_space_id, name as fg_name "
                        f"FROM [{safe_db_bracket}].sys.filegroups WITH(NOLOCK)"
                    )
                fg_query = " UNION ALL ".join(union_parts)
                fg_result = await execute_query_on_server(server_id, fg_query)
                fg_serialized = _serialize_result(fg_result)
                for row in fg_serialized:
                    fg_map[(row.get('db_name', ''), row.get('data_space_id'))] = row.get('fg_name', '')
            except Exception as fg_err:
                logger.warning(f'Nao foi possivel obter filegroups: {fg_err}')

        for file in serialized_result:
            if file.get('file_type') == 'ROWS':
                key = (file.get('database_name', ''), file.get('data_space_id'))
                file['filegroup_name'] = fg_map.get(key, '-')
            else:
                file['filegroup_name'] = '-'

        by_database = {}
        total_size_gb = 0
        for file in serialized_result:
            db_name = file.get('database_name', 'Unknown')
            if db_name not in by_database:
                by_database[db_name] = {'files': [], 'total_size_gb': 0}
            by_database[db_name]['files'].append(file)
            size_gb = file.get('size_gb', 0) or 0
            by_database[db_name]['total_size_gb'] += size_gb
            total_size_gb += size_gb
            phys = (file.get('physical_path') or '').upper()
            vol = drive_path.upper()
            sub_path = phys[len(vol):] if phys.startswith(vol) else phys
            if '\\' in sub_path.rstrip('\\'):
                file['sub_folder'] = sub_path.split('\\')[0]
            else:
                file['sub_folder'] = ''

        return JSONResponse(content={
            'server_id': server_id,
            'drive': drive_path,
            'total_files': len(serialized_result),
            'total_size_gb': round(total_size_gb, 2),
            'databases_count': len(by_database),
            'by_database': by_database,
            'files': serialized_result
        })
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching disk files for drive {drive} on {server_id}")


@router.get("/filegroup-growth-history/{server_id}", response_model=QueryResultResponse)
async def get_filegroup_growth_history(server_id: str, database: Optional[str] = Query(None)):
    """Obtem historico de crescimento de filegroups (ultimos 12 meses) - Suporta filtro por database"""
    try:
        query = SQLQueries.get_filegroup_growth_history_filtered(database)
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "database": database or "ALL", "filegroup_growth_history": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching filegroup growth history for {server_id}")


@router.get("/filegroup-growth-forecast/{server_id}", response_model=QueryResultResponse)
async def get_filegroup_growth_forecast(server_id: str, database: Optional[str] = Query(None)):
    """Obtem projecao de crescimento de filegroups (MonthsUntilFull) - Suporta filtro por database"""
    try:
        query = SQLQueries.get_filegroup_growth_forecast_filtered(database)
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "database": database or "ALL", "filegroup_growth_forecast": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching filegroup growth forecast for {server_id}")
