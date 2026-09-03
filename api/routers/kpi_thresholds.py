"""KPI Threshold overrides — endpoints REST (Fase 1: global).

Wave thresholds configuraveis (design 2026-08-04). Fase 1 = overrides
GLOBAIS por KPI (sem scope na UI). Escrita admin-only; leitura efectiva
(registry + overrides) para o ecra 'Thresholds em vigor'.

Precedencia de leitura (DATABASE>INSTANCE>ENV>GLOBAL>default) vive em
api/threshold_overrides.py — a Fase 2 (Pro/V6) liga os scopes sem tocar
neste router alem de relaxar a validacao de Scope_Type.

Endpoints:
    GET    /api/v1/kpi-thresholds            registry + overrides aplicados
    POST   /api/v1/kpi-thresholds            upsert override GLOBAL (admin)
    DELETE /api/v1/kpi-thresholds/{kpi_type}  repor default do produto (admin)

Tabela ausente => leitura devolve defaults; escrita devolve 503 claro
(a tabela e' criada pelo owner via bloco DDL — ver design doc).
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.error_helpers import safe_http_error
from api import threshold_overrides as _ovr
from api.kpi_thresholds_registry import THRESHOLDS, REGISTRY_VERSION

logger = logging.getLogger(__name__)


async def _require_admin_for_thresholds(request: Request) -> Dict[str, Any]:
    # dba ou admin (decisao do owner 2026-08-16): afinar thresholds e ajustar
    # o que dispara alarme e trabalho de DBA. Nome mantido para nao partir
    # os Depends ja espalhados pelo ficheiro.
    from api.routers.auth_compat import _require_dba
    return await _require_dba(request)


router = APIRouter(prefix="/api/v1/kpi-thresholds", tags=["KPI Thresholds"])


class ThresholdSetRequest(BaseModel):
    kpi_type: str = Field(..., min_length=1, max_length=64)
    warning_value: Optional[float] = Field(None)
    critical_value: Optional[float] = Field(None)


@router.get("")
async def list_thresholds():
    """Registry + overrides GLOBAIS aplicados (read-only, sem auth extra)."""
    try:
        rows = _ovr.effective_list()
        return {
            "success": True,
            "version": REGISTRY_VERSION,
            "overrides_active": _ovr.table_available(),
            "thresholds": rows,
        }
    except Exception as e:
        raise safe_http_error(500, e, "listing thresholds")


@router.post("")
async def set_threshold(
    body: ThresholdSetRequest,
    admin: Dict[str, Any] = Depends(_require_admin_for_thresholds),
):
    """Upsert de override GLOBAL para um KPI. Admin-only.

    Regras (Fase 1):
      - kpi_type tem de existir no registry E ser configurable_f1.
      - warning/critical ambos None => equivalente a DELETE (repor default).
      - grava sempre Scope_Type='GLOBAL', Scope_Value=''.
    """
    kpi = body.kpi_type
    meta = THRESHOLDS.get(kpi)
    if meta is None:
        raise HTTPException(status_code=400, detail=f"KPI desconhecido: {kpi}")
    if not meta.get("configurable_f1"):
        raise HTTPException(
            status_code=400,
            detail=f"KPI '{kpi}' nao e' configuravel nesta fase (vive em "
                   f"view/colector). Ver 'Thresholds em vigor'.",
        )
    if body.warning_value is None and body.critical_value is None:
        return await delete_threshold(kpi, admin)  # repor default

    # coerencia: se ambos definidos, warning tem de estar do lado certo de
    # critical conforme a direccao do KPI. higher_is_worse=False (ex:
    # filegroup_free_pct — % LIVRE, menor=pior) inverte a comparacao;
    # sem isto o POST dos proprios defaults (w=5 > c=2) devolvia 400.
    w, c = body.warning_value, body.critical_value
    hib = meta.get("higher_is_worse", True)
    if w is not None and c is not None:
        if hib and w > c:
            raise HTTPException(
                status_code=400,
                detail=f"Aviso ({w}) nao pode ser maior que critico ({c}) para {kpi}.",
            )
        if not hib and w < c:
            raise HTTPException(
                status_code=400,
                detail=f"Aviso ({w}) nao pode ser menor que critico ({c}) para "
                       f"{kpi} — neste KPI menor e' pior.",
            )
    # cap superior do warning (ex: filegroup_free_pct <= 10 — acima disso a
    # banda Warning engoliria o tier Attention fixo e os pre-filtros WHERE
    # estaticos deixariam de cobrir todas as linhas classificaveis).
    cap = meta.get("warning_cap")
    if cap is not None and w is not None and w > cap:
        raise HTTPException(
            status_code=400,
            detail=f"Aviso ({w}) acima do maximo permitido ({cap}) para {kpi}.",
        )

    changed_by = (admin.get("username") or admin.get("email") or "unknown")[:128]
    try:
        from api.connection_pool import execute_on_intelligence
        execute_on_intelligence(
            """
            MERGE dbo.WDB_KPI_THRESHOLDS AS target
            USING (SELECT ? AS Kpi_Type, 'GLOBAL' AS Scope_Type, '' AS Scope_Value) AS src
            ON  target.Kpi_Type = src.Kpi_Type
            AND target.Scope_Type = src.Scope_Type
            AND target.Scope_Value = src.Scope_Value
            WHEN MATCHED THEN
                UPDATE SET Warning_Value = ?, Critical_Value = ?,
                           Updated_By = ?, Updated_At = SYSDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (Kpi_Type, Scope_Type, Scope_Value, Warning_Value,
                        Critical_Value, Updated_By)
                VALUES (?, 'GLOBAL', '', ?, ?, ?);
            """,
            params=(kpi, w, c, changed_by, kpi, w, c, changed_by),
        )
        _ovr.refresh_cache(force=True)
        logger.info("KPI threshold override GLOBAL %s -> w=%s c=%s by %s",
                    kpi, w, c, changed_by)
        return {"success": True, "kpi_type": kpi, "warning_value": w,
                "critical_value": c, "changed_by": changed_by}
    except Exception as e:
        # Tabela ainda nao criada: o safe_http_error generico escondia isto
        # atras de "Internal error (ref)" — incidente 2026-08-13 (owner tentou
        # gravar e ficou sem pista). 42S02/208 = objecto inexistente: mensagem
        # accionavel sem vazar internals; resto continua generico com ref.
        if "42S02" in str(e) or "Invalid object name" in str(e):
            logger.error("WDB_KPI_THRESHOLDS ausente ao gravar %s: %s", kpi, e)
            raise HTTPException(
                status_code=503,
                detail=("A tabela WDB_KPI_THRESHOLDS ainda nao existe nesta "
                        "WatcherDB_Intelligence — correr o bloco DDL "
                        "(CREATE_WDB_KPI_THRESHOLDS.sql) e repetir. Ate la o "
                        "produto usa os defaults."),
            )
        raise safe_http_error(
            503, e,
            f"gravar override de {kpi} (a tabela WDB_KPI_THRESHOLDS existe?)",
        )


@router.delete("/{kpi_type}")
async def delete_threshold(
    kpi_type: str,
    admin: Dict[str, Any] = Depends(_require_admin_for_thresholds),
):
    """Remove o override GLOBAL => o KPI volta ao default do produto."""
    try:
        from api.connection_pool import execute_on_intelligence
        execute_on_intelligence(
            "DELETE FROM dbo.WDB_KPI_THRESHOLDS "
            "WHERE Kpi_Type = ? AND Scope_Type = 'GLOBAL' AND Scope_Value = ''",
            params=(kpi_type,),
        )
        _ovr.refresh_cache(force=True)
        by = (admin.get("username") or admin.get("email") or "unknown")[:128]
        logger.info("KPI threshold override removido: %s by %s", kpi_type, by)
        return {"success": True, "message": f"{kpi_type} reposto ao default"}
    except Exception as e:
        raise safe_http_error(503, e, f"remover override de {kpi_type}")
