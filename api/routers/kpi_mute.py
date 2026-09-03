"""KPI Mute -- universal mute list endpoints REST.

Wave R+10 (2026-05-25) -- Smart Defaults Initiative camada 1.

Permite admin silenciar alertas de qualquer KPI para uma instance especifica
durante periodo limitado (Mute_Until mandatory). Implementa a camada 1 do
priority chain definido em docs/architecture/SMART_DEFAULTS_PRINCIPLE.md.

Caracteristicas:
    - Auth: role dba ou admin (auth_compat._require_dba)
    - Instance-level granularity (per-DB seria config sprawl)
    - Expiry MANDATORY no schema (no permanent mutes)
    - Reason MANDATORY (audit trail)

Endpoints:
    GET    /api/v1/kpi-mute              listar mutes activos
    GET    /api/v1/kpi-mute/all          listar todos incluindo expirados (audit)
    POST   /api/v1/kpi-mute              criar/upsert mute
    DELETE /api/v1/kpi-mute/{kpi_type}/{instance}  remover mute manualmente

MVP NOTE: integration com KPI alert filtering NAO incluida (defer S+1).
Por agora endpoints sao CRUD pura -- KPI queries existentes nao consultam
a tabela ainda. Admin pode gerir mutes; "respect mute" e' wave seguinte.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.error_helpers import safe_http_error

logger = logging.getLogger(__name__)


# --- Auth guard: admin-only ---
async def _require_admin_for_mute(request: Request) -> Dict[str, Any]:
    """Guard: apenas role=admin."""
    # dba ou admin (decisao do owner 2026-08-16): silenciar um KPI ruidoso
    # e operacao de turno, nao governanca do sistema.
    from api.routers.auth_compat import _require_dba
    return await _require_dba(request)


router = APIRouter(
    prefix="/api/v1/kpi-mute",
    tags=["KPI Mute (Smart Defaults)"],
    # Sem guard ao nivel do router (decisao do owner 2026-08-16): LER a lista de
    # mutes e' para toda a gente autenticada; criar/remover e' operacao (dba).
)


# =============================================================================
# Pydantic models
# =============================================================================
class MuteCreateRequest(BaseModel):
    kpi_type: str = Field(..., min_length=1, max_length=40,
                          description="KPI type (ex: backup-failed, disk-usage, cpu-critical)")
    instance: str = Field(..., min_length=1, max_length=128,
                          description="Instance name (ex: SQLHDSPRD302_I01)")
    reason: str = Field(..., min_length=10, max_length=500,
                        description="Audit-friendly justificacao (min 10 chars)")
    mute_hours: int = Field(..., ge=1, le=720,
                            description="Mute duration em horas (1h min, 720h=30d max)")


# =============================================================================
# Endpoints
# =============================================================================
@router.get("")
async def list_active_mutes(
    kpi_type: Optional[str] = Query(None, description="Filtrar por kpi_type"),
):
    """Lista mutes ACTIVOS (Mute_Until > GETDATE())."""
    try:
        from api.connection_pool import execute_on_intelligence
        sql = (
            "SELECT Kpi_Type, Instance, Reason, Created_By, "
            "Created_At, Mute_Until "
            "FROM dbo.WDB_KPI_MUTE WITH (NOLOCK) "
            "WHERE Mute_Until > GETDATE() "
        )
        params = ()
        if kpi_type:
            sql += "AND Kpi_Type = ? "
            params = (kpi_type,)
        sql += "ORDER BY Mute_Until ASC"
        rows = execute_on_intelligence(sql, params=params) or []
        return {"count": len(rows), "mutes": rows}
    except Exception as e:
        raise safe_http_error(500, e, "listing active mutes")


@router.get("/all")
async def list_all_mutes(
    kpi_type: Optional[str] = Query(None, description="Filtrar por kpi_type"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Lista TODOS mutes (incluindo expirados) -- para audit."""
    try:
        from api.connection_pool import execute_on_intelligence
        sql = (
            f"SELECT TOP {int(limit)} Kpi_Type, Instance, Reason, Created_By, "
            "Created_At, Mute_Until, "
            "CASE WHEN Mute_Until > GETDATE() THEN 1 ELSE 0 END AS is_active "
            "FROM dbo.WDB_KPI_MUTE WITH (NOLOCK) "
        )
        params = ()
        if kpi_type:
            sql += "WHERE Kpi_Type = ? "
            params = (kpi_type,)
        sql += "ORDER BY Created_At DESC"
        rows = execute_on_intelligence(sql, params=params) or []
        return {"count": len(rows), "mutes": rows}
    except Exception as e:
        raise safe_http_error(500, e, "listing all mutes")


@router.post("")
async def create_mute(
    body: MuteCreateRequest,
    admin: Dict[str, Any] = Depends(_require_admin_for_mute),
):
    """Criar/upsert mute. PK (Kpi_Type, Instance) garante 1 row.

    Reason min 10 chars + Mute_Until mandatory (calculado de mute_hours).
    Idempotent: re-POST mesma (kpi_type, instance) UPDATEs row existente.
    """
    try:
        from api.connection_pool import execute_on_intelligence

        created_by = (admin.get("username") or admin.get("email") or "unknown")[:128]
        mute_until = datetime.utcnow() + timedelta(hours=body.mute_hours)
        mute_until_str = mute_until.strftime("%Y-%m-%d %H:%M:%S")

        # MERGE pattern para upsert
        execute_on_intelligence(
            """
            MERGE dbo.WDB_KPI_MUTE AS target
            USING (SELECT ? AS Kpi_Type, ? AS Instance) AS src
            ON target.Kpi_Type = src.Kpi_Type AND target.Instance = src.Instance
            WHEN MATCHED THEN
                UPDATE SET Reason = ?, Created_By = ?, Created_At = GETDATE(), Mute_Until = ?
            WHEN NOT MATCHED THEN
                INSERT (Kpi_Type, Instance, Reason, Created_By, Mute_Until)
                VALUES (?, ?, ?, ?, ?);
            """,
            params=(
                body.kpi_type, body.instance,
                body.reason, created_by, mute_until_str,
                body.kpi_type, body.instance, body.reason, created_by, mute_until_str,
            ),
        )

        logger.info(
            f"KPI Mute created: {body.kpi_type}|{body.instance} by {created_by} "
            f"until {mute_until_str} (reason: {body.reason[:60]})"
        )

        return {
            "success": True,
            "kpi_type": body.kpi_type,
            "instance": body.instance,
            "mute_until": mute_until_str,
            "created_by": created_by,
        }
    except Exception as e:
        raise safe_http_error(500, e, f"creating mute for {body.kpi_type}/{body.instance}")


@router.delete("/{kpi_type}/{instance}")
async def delete_mute(
    kpi_type: str,
    instance: str,
    admin: Dict[str, Any] = Depends(_require_admin_for_mute),
):
    """Remove mute manualmente (antes de expiry natural)."""
    try:
        from api.connection_pool import execute_on_intelligence
        execute_on_intelligence(
            "DELETE FROM dbo.WDB_KPI_MUTE WHERE Kpi_Type = ? AND Instance = ?",
            params=(kpi_type, instance),
        )
        deleted_by = (admin.get("username") or admin.get("email") or "unknown")[:128]
        logger.info(f"KPI Mute deleted: {kpi_type}|{instance} by {deleted_by}")
        return {"success": True, "message": f"Mute removed for {kpi_type}/{instance}"}
    except Exception as e:
        raise safe_http_error(500, e, f"deleting mute {kpi_type}/{instance}")
