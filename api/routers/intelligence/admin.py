#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intelligence KPIs - Admin endpoints.
Health check, cache refresh, available views, filegroup usage detail.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

from api.error_helpers import safe_http_error
from api.models import GenericResponse, MessageResponse
from api.routers.intelligence.helpers import (
    execute_intelligence_query,
    _serialize_result,
    INTELLIGENCE_SERVER,
    INTELLIGENCE_DATABASE,
    INTELLIGENCE_SCHEMA,
    _dashboard_cache,
    _cache_lock,
    _last_known_values,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=GenericResponse)
async def health_check():
    """Verifica se a conexao com o SQL Server Intelligence esta funcionando"""
    try:
        query = "SELECT 1 AS test"
        result = execute_intelligence_query(query, raise_on_error=True)
        return JSONResponse(content={
            "status": "healthy",
            "server": INTELLIGENCE_SERVER,
            "database": INTELLIGENCE_DATABASE,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check falhou: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "server": INTELLIGENCE_SERVER,
                "database": INTELLIGENCE_DATABASE,
                "timestamp": datetime.now().isoformat()
            }
        )


@router.post("/refresh", response_model=MessageResponse)
async def refresh_cache():
    """Forca atualizacao do cache de KPIs."""
    global _dashboard_cache, _last_known_values

    try:
        with _cache_lock:
            _dashboard_cache['data'] = None
            _dashboard_cache['timestamp'] = 0

        for key in _last_known_values:
            _last_known_values[key] = None

        test_query = "SELECT 1 AS test"
        execute_intelligence_query(test_query, raise_on_error=True)

        logger.info("Cache de KPIs limpo e conexao verificada com sucesso")

        return JSONResponse(content={
            "success": True,
            "message": "Cache limpo com sucesso. Proxima requisicao buscara dados frescos do banco.",
            "server": INTELLIGENCE_SERVER,
            "database": INTELLIGENCE_DATABASE,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Erro ao fazer refresh do cache: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "Falha ao limpar cache ou reconectar ao banco",
                "timestamp": datetime.now().isoformat()
            }
        )


@router.get("/available-views", response_model=GenericResponse)
async def list_available_views():
    """Lista todas as views disponiveis no schema dbo"""
    try:
        query = f"""
        SELECT
            TABLE_NAME as view_name,
            'View' as object_type
        FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = '{INTELLIGENCE_SCHEMA}'
        AND TABLE_NAME LIKE 'KPI_MSSQL_%'
        ORDER BY TABLE_NAME
        """
        views = execute_intelligence_query(query, raise_on_error=False)
        return JSONResponse(content={
            "success": True,
            "schema": INTELLIGENCE_SCHEMA,
            "views": views or [],
            "views_count": len(views) if views else 0
        })
    except Exception as e:
        raise safe_http_error(500, e, "listing available Intelligence views")


@router.get("/detail/filegroup-usage/{instance_name}", response_model=GenericResponse)
async def get_filegroup_usage_detail(instance_name: str):
    """Retorna detalhes de filegroups com problema para uma instancia especifica"""
    try:
        instance_underscore = instance_name.replace('\\', '_')
        instance_backslash = instance_name.replace('_', '\\')
        safe_underscore = instance_underscore.replace("'", "''")
        safe_backslash = instance_backslash.replace("'", "''")

        query = f"""
        SELECT
            f.Instance, f.[Database], f.Filegroup,
            f.Total_MB, f.Used_MB, f.Free_MB, f.Percent_Used,
            ISNULL(f.Max_Size_MB, 0) AS Max_Size_MB,
            f.Growth_Type, f.Update_TS,
            CASE
                WHEN f.Percent_Used >  98 THEN 'CRITICAL'
                WHEN f.Percent_Used >  95 THEN 'WARNING'
                WHEN f.Percent_Used >  90 THEN 'ATTENTION'
                ELSE 'OK'
            END AS Status
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_STG AS f WITH (NOLOCK)
        WHERE f.Instance IN ('{safe_underscore}', '{safe_backslash}')
          AND f.Percent_Used > 90
        ORDER BY f.Percent_Used DESC
        """
        filegroups = execute_intelligence_query(query, raise_on_error=False) or []

        logger.info(f"Filegroups encontrados para {instance_name}: {len(filegroups)}")

        return JSONResponse(content={
            "success": True,
            "instance": instance_name,
            "filegroups": _serialize_result(filegroups),
            "count": len(filegroups)
        })
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching filegroup details for {instance_name}")
