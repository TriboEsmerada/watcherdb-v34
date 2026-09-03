#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries - System endpoints.
TempDB monitoring, growth analysis, culprits, villains, space analysis, sql-script.
This module re-exports endpoints from the original sql_queries.py that deal with
TempDB and system-level diagnostics.

NOTE: The tempdb endpoints and the large diagnose-query/expand-view endpoints
are kept in the original sql_queries.py and included via the __init__.py router.
This file contains the sql-script endpoint and a reference note.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import logging

from modules.monitoring.queries import SQLQueries
from api.error_helpers import safe_http_error
from watcherdb.core.sql_validator import validate_query
from api.models import GenericResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sql-script/{query_id}", response_model=GenericResponse)
async def get_sql_script(query_id: str):
    """Retorna o script SQL de uma query pelo ID"""
    try:
        query_map = {
            'blocking': 'BLOCKING_HIERARCHY',
            'deadlocks': 'DEADLOCKS_ANALYSIS',
            'slow-queries': 'TOP_SLOW_QUERIES_DETAILED',
            'log-space': 'LOG_SPACE_MONITORING',
            'sql-agent-jobs': 'SQL_AGENT_JOBS_FAILING',
            'sessions': 'PROBLEMATIC_SESSIONS',
            'index-fragmentation': 'INDEX_FRAGMENTATION',
            'tempdb': 'TEMPDB_MONITORING',
            'file-growth': 'FILE_GROWTH_MONITORING',
            'statistics': 'STATISTICS_OUTDATED',
            'database-connections': 'DATABASE_CONNECTIONS',
            'backup': 'BACKUP_STATUS',
            'tde-status': 'TDE_STATUS',
            'tde-database-status': 'TDE_DATABASE_STATUS',
            'mirroring': 'MIRRORING_LOGSHIPPING_STATUS',
            'filegroup-growth-history': 'FILEGROUP_GROWTH_HISTORY',
            'filegroup-growth-forecast': 'FILEGROUP_GROWTH_FORECAST',
            'backup-history-analysis': 'BACKUP_HISTORY_ANALYSIS',
            'backup-gaps-full': 'BACKUP_FULL_GAPS_ANALYSIS',
            'backup-gaps-diff': 'BACKUP_DIFF_GAPS_ANALYSIS',
            'backup-gaps-log': 'BACKUP_LOG_GAPS_ANALYSIS',
            'backup-gaps-summary': 'BACKUP_GAPS_SUMMARY',
            'backup-gaps-statistics': 'BACKUP_GAPS_STATISTICS',
            'missing-index-analysis': 'MISSING_INDEX_ANALYSIS'
        }

        attr_name = query_map.get(query_id)
        if not attr_name:
            return JSONResponse(content={"query_id": query_id, "sql_script": "-- Query ID nao encontrado"})

        sql_script = getattr(SQLQueries, attr_name, None)

        if callable(sql_script):
            try:
                sql_script = sql_script(None)
            except Exception:
                sql_script = "-- Erro ao obter script SQL (metodo requer parametros)"

        if not sql_script:
            sql_script = "-- Script SQL nao disponivel"

        # Validate SQL before returning (defense-in-depth for predefined queries)
        is_safe, error_msg = validate_query(sql_script)
        if not is_safe:
            logger.warning(f"SQL validation failed for query_id={query_id}: {error_msg}")
            raise HTTPException(status_code=400, detail=f"Query blocked: {error_msg}")

        return JSONResponse(content={"query_id": query_id, "sql_script": sql_script})
    except Exception as e:
        logger.error(f"Erro ao obter script SQL para {query_id}: {e}")
        return JSONResponse(content={"query_id": query_id, "sql_script": f"-- Erro: {str(e)}"})
