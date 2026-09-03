#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries - Backup endpoints.
Backup status, history analysis, gaps analysis, TDE status.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import logging

from modules.monitoring.queries import SQLQueries
from api.error_helpers import safe_http_error
from api.routers.queries.helpers import execute_query_on_server
from api.models import QueryResultResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/backup/{server_id}", response_model=QueryResultResponse)
async def get_backup_status(server_id: str):
    """Obtem status de backups"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BACKUP_STATUS)
        return JSONResponse(content={"server_id": server_id, "backup_status": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching backup status for {server_id}")


@router.get("/tde-status/{server_id}", response_model=QueryResultResponse)
async def get_tde_status(server_id: str):
    """Obtem status de TDE (Transparent Data Encryption)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TDE_STATUS)
        return JSONResponse(content={"server_id": server_id, "tde_status": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching TDE status for {server_id}")


@router.get("/tde-database-status/{server_id}", response_model=QueryResultResponse)
async def get_tde_database_status(server_id: str):
    """Obtem status de TDE por database (quais estao encriptadas e quais nao estao)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TDE_DATABASE_STATUS)
        return JSONResponse(content={"server_id": server_id, "tde_database_status": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching TDE database status for {server_id}")


@router.get("/backup-history-analysis/{server_id}", response_model=QueryResultResponse)
async def get_backup_history_analysis(server_id: str):
    """Obtem analise de historico de backups (considera Always On AG) - SEM filtro (precisa ver todas as databases)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BACKUP_HISTORY_ANALYSIS)
        return JSONResponse(content={"server_id": server_id, "backup_history_analysis": result})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching backup history analysis for {server_id}")


@router.get("/backup-gaps-full/{server_id}", response_model=QueryResultResponse)
async def get_backup_full_gaps(server_id: str, days: int = 1):
    """Analise de gaps em backups FULL (padrao: ultimas 24h, configuravel via ?days=)"""
    try:
        days = max(1, min(days, 90))
        query = SQLQueries.BACKUP_FULL_GAPS_ANALYSIS.replace(
            "@DaysToAnalyze INT = 1", f"@DaysToAnalyze INT = {days}")
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "full_gaps": result, "days": days})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching FULL backup gaps for {server_id}")


@router.get("/backup-gaps-diff/{server_id}", response_model=QueryResultResponse)
async def get_backup_diff_gaps(server_id: str, days: int = 1):
    """Analise de gaps em backups DIFF (padrao: ultimas 24h, configuravel via ?days=)"""
    try:
        days = max(1, min(days, 90))
        query = SQLQueries.BACKUP_DIFF_GAPS_ANALYSIS.replace(
            "@DaysToAnalyze INT = 1", f"@DaysToAnalyze INT = {days}")
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "diff_gaps": result, "days": days})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching DIFF backup gaps for {server_id}")


@router.get("/backup-gaps-log/{server_id}", response_model=QueryResultResponse)
async def get_backup_log_gaps(server_id: str, days: int = 1):
    """Analise de gaps em backups LOG com deteccao de bloqueio (padrao: ultimas 24h, configuravel via ?days=)"""
    try:
        days = max(1, min(days, 90))
        query = SQLQueries.BACKUP_LOG_GAPS_ANALYSIS.replace(
            "DATEADD(DAY, -1, GETDATE())", f"DATEADD(DAY, -{days}, GETDATE())")
        result = await execute_query_on_server(server_id, query, command_timeout=600)
        return JSONResponse(content={"server_id": server_id, "log_gaps": result, "days": days})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching LOG backup gaps for {server_id}")


@router.get("/backup-gaps-summary/{server_id}", response_model=QueryResultResponse)
async def get_backup_gaps_summary(server_id: str, days: int = 1):
    """Resumo consolidado de gaps de backup por database (padrao: ultimas 24h, configuravel via ?days=)"""
    try:
        days = max(1, min(days, 90))
        query = SQLQueries.BACKUP_GAPS_SUMMARY.replace(
            "@DaysToAnalyze INT = 1", f"@DaysToAnalyze INT = {days}")
        result = await execute_query_on_server(server_id, query, command_timeout=600)
        return JSONResponse(content={"server_id": server_id, "gaps_summary": result, "days": days})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching backup gaps summary for {server_id}")


@router.get("/backup-gaps-statistics/{server_id}", response_model=QueryResultResponse)
async def get_backup_gaps_statistics(server_id: str, days: int = 1):
    """Estatisticas consolidadas de gaps de backup LOG (padrao: ultimas 24h, configuravel via ?days=)"""
    try:
        days = max(1, min(days, 90))
        query = SQLQueries.BACKUP_GAPS_STATISTICS.replace(
            "@DaysToAnalyze INT = 1", f"@DaysToAnalyze INT = {days}")
        result = await execute_query_on_server(server_id, query, command_timeout=600)
        return JSONResponse(content={"server_id": server_id, "gaps_statistics": result, "days": days})
    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"fetching backup gaps statistics for {server_id}")
