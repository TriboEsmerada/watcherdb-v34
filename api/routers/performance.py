"""Performance Intelligence — FastAPI router.

Endpoints:
    GET  /api/v1/performance/investigators
    GET  /api/v1/performance/snapshot/{instance}
    POST /api/v1/performance/investigate/{instance}/{investigator_id}
    GET  /api/v1/performance/investigations
    GET  /api/v1/performance/investigations/{investigation_id}
    GET  /api/v1/performance/incidents
    GET  /api/v1/performance/action-history
    POST /api/v1/performance/action-history
    POST /api/v1/performance/ticket-response
    GET  /api/v1/performance/runbooks/{investigator_id}
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from api.error_helpers import safe_http_error
from pydantic import BaseModel

from modules.performance.base import InvestigationResult
from modules.performance.investigators import get_investigator, get_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/performance", tags=["Performance Intelligence"])

RUNBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "modules" / "performance" / "runbooks"


# ============================================================================
# GET /investigators — listar investigators disponiveis
# ============================================================================
@router.get("/investigators")
async def list_investigators():
    registry = get_registry()
    return {
        "investigators": [
            {
                "id": cls.investigator_id,
                "display_name_pt": cls.display_name_pt,
                "category": cls.category,
                "icon": cls.icon,
                "help_text_pt": cls.help_text_pt,
            }
            for cls in registry.values()
        ]
    }


# ============================================================================
# GET /snapshot/{instance} — snapshot rapido dos 6 cards para 1 instancia
# ============================================================================
@router.get("/snapshot/{instance}")
async def get_snapshot(instance: str):
    """Executa cada investigator e devolve apenas os campos L1 (card summary).

    Usado para popular a grid de cards quando a tab Performance abre.
    """
    registry = get_registry()
    cards = {}

    async def _run_one(iid: str, cls):
        try:
            inst = cls()
            result = await inst.investigate(instance, triggered_by="snapshot")
            cards[iid] = {
                "id": iid,
                "display_name_pt": cls.display_name_pt,
                "category": cls.category,
                "icon": cls.icon,
                "count": result.count,
                "severity": result.severity,
                "subtitle_pt": result.subtitle_pt,
                "investigation_id": result.investigation_id,
            }
        except Exception as e:
            logger.error("[Performance] snapshot falhou para %s: %s", iid, e)
            cards[iid] = {
                "id": iid,
                "display_name_pt": cls.display_name_pt,
                "category": cls.category,
                "icon": cls.icon,
                "count": 0,
                "severity": "INFO",
                "subtitle_pt": "Nao foi possivel colectar",
                "error": str(e),
            }

    await asyncio.gather(*(_run_one(iid, cls) for iid, cls in registry.items()))

    return {"instance": instance, "cards": cards}


# ============================================================================
# POST /investigate/{instance}/{investigator_id} — investigacao completa
# ============================================================================
class InvestigateRequest(BaseModel):
    triggered_by: str = "manual"
    force_refresh: bool = False


@router.post("/investigate/{instance}/{investigator_id}")
async def investigate(
    instance: str,
    investigator_id: str,
    body: Optional[InvestigateRequest] = Body(default=None),
):
    """Executa 1 investigator contra 1 instancia. Retorna InvestigationResult completo."""
    try:
        investigator = get_investigator(investigator_id)
    except KeyError as e:
        # investigator_id e input cliente — safe para devolver valor mas nao stack
        raise HTTPException(status_code=404, detail=f"Unknown investigator: {investigator_id}")

    triggered_by = (body.triggered_by if body else None) or "manual"
    result = await investigator.investigate(instance, triggered_by=triggered_by)

    # Persistir em performance_investigations (best-effort)
    try:
        await _persist_investigation(result)
    except Exception as e:
        logger.warning("[Performance] falha ao persistir investigation: %s", e)

    return result.to_dict()


async def _persist_investigation(result: InvestigationResult) -> None:
    """Grava o result em dbo.performance_investigations."""
    from api.async_db import async_execute_on_intelligence
    from api.connection_pool import execute_on_intelligence

    # Usar pyodbc sync com params para safety
    q = """
    INSERT INTO dbo.performance_investigations
        (investigation_id, investigator_id, instance, severity, triggered_at,
         triggered_by, duration_ms, root_cause_pt, confidence_score,
         executive_summary, result_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        execute_on_intelligence(q, params=(
            result.investigation_id,
            result.investigator_id,
            result.instance,
            result.severity,
            result.triggered_at,
            result.triggered_by,
            result.duration_ms,
            result.root_cause_pt[:4000] if result.root_cause_pt else None,
            result.confidence_score,
            result.executive_summary_pt[:4000] if result.executive_summary_pt else None,
            json.dumps(result.to_dict(), default=str)[:100000],
        ))
    except Exception as e:
        # Tabela pode nao existir ainda — log e seguir
        logger.debug("[Performance] INSERT investigation skip: %s", e)


# ============================================================================
# GET /investigations — historico
# ============================================================================
@router.get("/investigations")
async def list_investigations(
    instance: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    from api.async_db import async_execute_on_intelligence

    where = []
    if instance:
        where.append(f"instance = '{instance.replace(chr(39), chr(39)*2)}'")
    if severity:
        where.append(f"severity = '{severity.replace(chr(39), chr(39)*2)}'")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    q = f"""
    SELECT TOP {int(limit)}
        investigation_id, investigator_id, instance, severity,
        triggered_at, triggered_by, duration_ms,
        root_cause_pt, confidence_score, executive_summary,
        resolved_at
    FROM dbo.performance_investigations WITH (NOLOCK)
    {where_sql}
    ORDER BY triggered_at DESC
    """
    try:
        rows = await async_execute_on_intelligence(q) or []
    except Exception as e:
        logger.warning("[Performance] listagem falhou: %s", e)
        rows = []
    return {"count": len(rows), "investigations": rows}


@router.get("/investigations/{investigation_id}")
async def get_investigation(investigation_id: str):
    from api.async_db import async_execute_on_intelligence
    q = f"""
    SELECT investigation_id, investigator_id, instance, severity,
           triggered_at, triggered_by, duration_ms,
           root_cause_pt, confidence_score, executive_summary, result_json
    FROM dbo.performance_investigations WITH (NOLOCK)
    WHERE investigation_id = '{investigation_id.replace(chr(39), chr(39)*2)}'
    """
    try:
        rows = await async_execute_on_intelligence(q) or []
    except Exception as e:
        raise safe_http_error(500, e, "performance investigation lookup")
    if not rows:
        raise HTTPException(status_code=404, detail="Investigation nao encontrada")
    row = rows[0]
    if row.get("result_json"):
        try:
            row["result"] = json.loads(row["result_json"])
        except Exception:
            row["result"] = None
    return row


# ============================================================================
# GET /incidents
# ============================================================================
@router.get("/incidents")
async def list_incidents(
    instance: Optional[str] = Query(None),
    unresolved_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
):
    from api.async_db import async_execute_on_intelligence
    where = []
    if instance:
        where.append(f"instance = '{instance.replace(chr(39), chr(39)*2)}'")
    if unresolved_only:
        where.append("resolved_at IS NULL")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    q = f"""
    SELECT TOP {int(limit)} * FROM dbo.performance_incidents WITH (NOLOCK)
    {where_sql}
    ORDER BY created_at DESC
    """
    try:
        rows = await async_execute_on_intelligence(q) or []
    except Exception as e:
        logger.warning("[Performance] list_incidents falhou: %s", e)
        rows = []
    return {"count": len(rows), "incidents": rows}


# ============================================================================
# GET / POST /action-history
# ============================================================================
@router.get("/action-history")
async def list_action_history(
    instance: Optional[str] = Query(None),
    object_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    from api.async_db import async_execute_on_intelligence
    where = []
    if instance:
        where.append(f"instance = '{instance.replace(chr(39), chr(39)*2)}'")
    if object_name:
        where.append(f"object_name LIKE '%{object_name.replace(chr(39), chr(39)*2)}%'")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    q = f"""
    SELECT TOP {int(limit)} * FROM dbo.performance_action_history WITH (NOLOCK)
    {where_sql}
    ORDER BY applied_at DESC
    """
    try:
        rows = await async_execute_on_intelligence(q) or []
    except Exception as e:
        logger.warning("[Performance] list_action_history falhou: %s", e)
        rows = []
    return {"count": len(rows), "actions": rows}


class ActionHistoryRecord(BaseModel):
    instance: str
    database_name: Optional[str] = None
    object_name: Optional[str] = None
    action_type: str
    action_sql: Optional[str] = None
    applied_by: str
    outcome_metric: Optional[str] = None
    outcome_before: Optional[float] = None
    outcome_after: Optional[float] = None
    notes_pt: Optional[str] = None
    investigation_id: Optional[str] = None


@router.post("/action-history")
async def register_action(rec: ActionHistoryRecord):
    from api.connection_pool import execute_on_intelligence
    from datetime import datetime

    q = """
    INSERT INTO dbo.performance_action_history
        (instance, database_name, object_name, action_type, action_sql,
         applied_at, applied_by, outcome_metric, outcome_before, outcome_after,
         notes_pt, investigation_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        execute_on_intelligence(q, params=(
            rec.instance, rec.database_name, rec.object_name,
            rec.action_type, rec.action_sql, datetime.utcnow(),
            rec.applied_by, rec.outcome_metric,
            rec.outcome_before, rec.outcome_after,
            rec.notes_pt, rec.investigation_id,
        ))
        return {"success": True}
    except Exception as e:
        raise safe_http_error(500, e, "performance recommendation outcome update")


# ============================================================================
# POST /ticket-response — gera texto PT
# ============================================================================
class TicketRequest(BaseModel):
    investigation_id: str
    template: str = "default"
    dba_name: str = "DBA Team"
    action_taken: bool = False
    pending_approval: bool = True


@router.post("/ticket-response")
async def ticket_response(req: TicketRequest):
    from api.async_db import async_execute_on_intelligence
    from modules.performance.engines.ticket_generator import TicketResponseGenerator

    # Buscar investigation
    q = f"""
    SELECT result_json FROM dbo.performance_investigations WITH (NOLOCK)
    WHERE investigation_id = '{req.investigation_id.replace(chr(39), chr(39)*2)}'
    """
    try:
        rows = await async_execute_on_intelligence(q) or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query falhou: {e}")

    if not rows or not rows[0].get("result_json"):
        raise HTTPException(status_code=404, detail="Investigation nao encontrada ou sem result_json")

    try:
        d = json.loads(rows[0]["result_json"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON corrompido: {e}")

    # Reconstruir dataclass minima (usar to_dict e popular InvestigationResult)
    from modules.performance.base import InvestigationResult, EstimatedImpact
    # MVP: usar objecto simples — TicketResponseGenerator acessa atributos
    class _Stub:
        pass
    stub = _Stub()
    for k, v in d.items():
        if k == "estimated_impact" and isinstance(v, dict):
            ei = EstimatedImpact(**{kk: vv for kk, vv in v.items() if kk in EstimatedImpact.__dataclass_fields__})
            setattr(stub, k, ei)
        else:
            setattr(stub, k, v)

    # triggered_at vem como string ISO — converter
    from datetime import datetime
    if isinstance(getattr(stub, "triggered_at", None), str):
        try:
            stub.triggered_at = datetime.fromisoformat(stub.triggered_at)
        except Exception:
            stub.triggered_at = datetime.utcnow()

    text = TicketResponseGenerator().generate(
        stub, template=req.template,
        action_taken=req.action_taken, pending_approval=req.pending_approval,
        dba_name=req.dba_name,
    )
    return {"ticket_text_pt": text}


# ============================================================================
# GET /runbooks/{investigator_id}
# ============================================================================
@router.get("/runbooks/{investigator_id}")
async def get_runbook(investigator_id: str):
    path = RUNBOOKS_DIR / f"{investigator_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Runbook nao encontrado: {investigator_id}")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Leitura falhou: {e}")
    return {"investigator_id": investigator_id, "content_md": content}
