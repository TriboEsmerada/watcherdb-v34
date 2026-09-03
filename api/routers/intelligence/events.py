#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intelligence KPIs - Server Offline Events endpoints.
Resolve, history, and summary for server offline events.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import logging
import re

from api.error_helpers import safe_http_error
from api.models import GenericResponse, MessageResponse
from api.routers.intelligence.helpers import (
    execute_intelligence_query,
    _serialize_result,
    INTELLIGENCE_SCHEMA,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/server-offline/resolve/{event_id}", response_model=MessageResponse)
async def resolve_server_offline_event(event_id: int):
    """Marca um evento de servidor offline como resolvido."""
    try:
        query = f"EXEC {INTELLIGENCE_SCHEMA}.usp_ResolveServerOfflineEvent @Event_ID = {event_id}"
        result = execute_intelligence_query(query, raise_on_error=True)

        events_resolved = 0
        if result and len(result) > 0:
            events_resolved = result[0].get('Events_Resolved', 0)

        if events_resolved > 0:
            return JSONResponse(content={
                "success": True,
                "message": f"Evento {event_id} marcado como resolvido",
                "events_resolved": events_resolved
            })
        else:
            raise HTTPException(status_code=404, detail=f"Evento {event_id} nao encontrado ou ja resolvido")

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"resolving server offline event {event_id}")


@router.post("/server-offline/resolve-by-server/{server_name:path}", response_model=MessageResponse)
async def resolve_server_offline_by_server(server_name: str):
    """Marca todos os eventos nao resolvidos de um servidor como resolvidos."""
    if not re.match(r'^[A-Za-z0-9_\\.\-]{1,256}$', server_name):
        raise HTTPException(status_code=400, detail="Nome de servidor invalido")

    try:
        query = f"EXEC {INTELLIGENCE_SCHEMA}.usp_ResolveServerOfflineEvent @Server_Name = N'{server_name.replace(chr(39), chr(39)+chr(39))}'"
        result = execute_intelligence_query(query, raise_on_error=True)

        events_resolved = 0
        if result and len(result) > 0:
            events_resolved = result[0].get('Events_Resolved', 0)

        return JSONResponse(content={
            "success": True,
            "message": f"{events_resolved} evento(s) resolvido(s) para {server_name}",
            "events_resolved": events_resolved,
            "server_name": server_name
        })

    except HTTPException:
        raise
    except Exception as e:
        raise safe_http_error(500, e, f"resolving server offline events for {server_name}")


@router.get("/server-offline/history", response_model=GenericResponse)
async def get_server_offline_history(days: int = 7, include_resolved: bool = True):
    """Retorna historico de eventos de servidor offline."""
    try:
        where_clause = f"WHERE Event_Time >= DATEADD(DAY, -{days}, GETDATE())"
        if not include_resolved:
            where_clause += " AND Is_Resolved = 0"

        query = f"""
        SELECT
            Event_ID,
            Server_Name AS Instance,
            Diagnosis,
            CASE Diagnosis
                WHEN 'offline' THEN 'Servidor Offline'
                WHEN 'sql_down' THEN 'SQL Services Down'
                WHEN 'partial' THEN 'Servicos Parciais'
                ELSE Diagnosis
            END AS Diagnosis_Desc,
            Ping_OK,
            CASE WHEN Ping_OK = 1 THEN 'OK' ELSE 'FALHA' END AS Ping_Status,
            Ping_Message,
            Services_Down,
            Event_Time,
            Resolved_Time,
            Is_Resolved,
            CASE WHEN Is_Resolved = 1 THEN 'Resolvido' ELSE 'Ativo' END AS Status,
            DATEDIFF(MINUTE, Event_Time, ISNULL(Resolved_Time, GETDATE())) AS Duration_Minutes,
            CASE
                WHEN Server_Name LIKE '%PRD%' OR Server_Name LIKE '%PROD%' THEN 'PRD'
                WHEN Server_Name LIKE '%QLT%' OR Server_Name LIKE '%QUAL%' THEN 'QLT'
                WHEN Server_Name LIKE '%TST%' OR Server_Name LIKE '%TEST%' OR Server_Name LIKE '%DEV%' THEN 'TST'
                ELSE 'Undefined'
            END AS Env
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_EVENTS WITH (NOLOCK)
        {where_clause}
        ORDER BY Event_Time DESC
        """
        events = execute_intelligence_query(query, raise_on_error=False) or []

        return JSONResponse(content={
            "success": True,
            "events": _serialize_result(events),
            "count": len(events),
            "days": days,
            "include_resolved": include_resolved
        })

    except Exception as e:
        raise safe_http_error(500, e, "fetching server offline event history")


@router.get("/server-offline/summary", response_model=GenericResponse)
async def get_server_offline_summary():
    """Retorna resumo dos eventos de servidor offline para o card do dashboard."""
    try:
        query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK)"
        result = execute_intelligence_query(query, raise_on_error=False)

        if result and len(result) > 0:
            row = result[0]
            return JSONResponse(content={
                "success": True,
                "summary": {
                    "servers_offline": int(row.get('Servers_Offline', 0) or 0),
                    "servers_sql_down": int(row.get('Servers_SQL_Down', 0) or 0),
                    "servers_partial": int(row.get('Servers_Partial', 0) or 0),
                    "total_events": int(row.get('Total_Events', 0) or 0),
                    "last_event_time": row.get('Last_Event_Time'),
                    "overall_status": row.get('Overall_Status', 'OK')
                }
            })
        else:
            return JSONResponse(content={
                "success": True,
                "summary": {
                    "servers_offline": 0, "servers_sql_down": 0, "servers_partial": 0,
                    "total_events": 0, "last_event_time": None, "overall_status": "OK"
                }
            })

    except Exception as e:
        raise safe_http_error(500, e, "fetching server offline event summary")
