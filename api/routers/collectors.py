"""Collector Health Monitoring — endpoints REST.

Acesso restrito a role=admin (regra do produto: operacoes sobre collectors
tocam infra-estrutura e podem disparar carga em instancias monitorizadas).

Endpoints:
    GET  /api/v1/collectors/health              lista completa + summary
    GET  /api/v1/collectors/{task_name}/logs    logs parseados de 1 task
    GET  /api/v1/collectors/{task_name}/config  config.yaml snippet do task
    POST /api/v1/collectors/{task_name}/run     trigger manual (Opcao B: flag em BD)
    GET  /api/v1/collectors/runs/{request_id}   status de um run manual
    GET  /api/v1/collectors/service/status      sc query WatcherDBCollector
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header

from api.error_helpers import safe_http_error
from watcherdb.core.same_origin import require_same_origin
from pydantic import BaseModel

from modules.collector_health.config_loader import (
    get_task,
    get_tasks,
    get_config_path,
)
from modules.collector_health.health_calculator import compute_health
from modules.collector_health.log_parser import (
    logs_for_task,
    recent_errors_for_task,
)

logger = logging.getLogger(__name__)


# --- Auth guard: admin-only (adaptado para V3.3 auth_compat) ---
from fastapi import Request

async def _require_admin_for_collectors(request: Request) -> Dict[str, Any]:
    """Guard: role `dba` ou `admin` (decisao do owner 2026-08-16 -- gerir
    collectors e operacao de DBA, nao governanca). Nome mantido para nao
    partir os Depends ja espalhados pelo ficheiro."""
    from api.routers.auth_compat import _require_dba
    return await _require_dba(request)


router = APIRouter(
    prefix="/api/v1/collectors",
    tags=["Collector Health"],
    # Sem guard ao nivel do router (decisao do owner 2026-08-16): LER a saude
    # dos collectors e' para toda a gente autenticada, incluindo `viewer`. O
    # guard fica so' nas 3 mutacoes (toggle on/off e run), que sao operacao.
)


# =============================================================================
# F1 — Health snapshot
# =============================================================================
@router.get("/health")
async def get_health(
    env: Optional[str] = Query(None, description="PRD | QA | TST | SCOM (case-insensitive)"),
    status: Optional[str] = Query(None, description="FRESH | RECENT | STALE | FAILED | DISABLED | NEVER_RAN"),
    search: Optional[str] = Query(None, description="Substring match no nome do task"),
):
    """Retorna summary + lista de tasks com estado actual.

    Filtros aplicam-se apenas a lista — o summary e sempre global.
    """
    try:
        return await compute_health(env_filter=env, status_filter=status, search=search)
    except Exception as e:
        logger.error("[CollectorHealth] compute_health falhou: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Compute health failed: {e}")


# =============================================================================
# F5 — Logs parseados
# =============================================================================
@router.get("/{task_name}/logs")
async def get_task_logs(
    task_name: str,
    limit: int = Query(100, ge=1, le=1000),
):
    """Retorna ultimas N entries combinando info + errors para este task."""
    task = get_task(task_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_name}' nao existe no config.yaml")
    entries = logs_for_task(task_name, limit=limit)
    # Remover campos internos antes de devolver
    clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries]
    return {
        "task_name": task_name,
        "count": len(clean),
        "entries": clean,
    }


# =============================================================================
# Config snippet (read-only, sem passwords)
# =============================================================================
@router.get("/{task_name}/config")
async def get_task_config(task_name: str):
    """Retorna o snippet do config.yaml relativo a este task."""
    task = get_task(task_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_name}' nao existe")
    # Clone para nao expor referencias mutaveis; config.yaml e read-only
    return {
        "task_name": task_name,
        "config": dict(task),
        "source_path": str(get_config_path()) if get_config_path() else None,
    }


# =============================================================================
# F4 — Trigger manual (Opcao B: flag em BD)
# =============================================================================
class RunRequest(BaseModel):
    reason: Optional[str] = None


class ToggleRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = None


@router.post("/{task_name}/toggle")
async def toggle_task(
    task_name: str,
    body: ToggleRequest,
    admin: Dict[str, Any] = Depends(_require_admin_for_collectors),
):
    """Activa/desactiva um task via override na BD.

    O override toma precedencia sobre o config.yaml:
    - enabled=true  → task aparece como ENABLED no dashboard + scheduler pode executar
    - enabled=false → task aparece como DISABLED
    Apagar o override (DELETE) volta ao estado do config.yaml.
    """
    task = get_task(task_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_name}' nao existe no config.yaml")

    reason_text = (body.reason or "").strip()
    if len(reason_text) < 20:
        raise HTTPException(
            status_code=422,
            detail=f"Motivo obrigatorio com minimo 20 caracteres (recebido: {len(reason_text)}). "
                   f"Garante rastreabilidade adequada no historico de alteracoes.",
        )

    changed_by = (admin.get("username") or admin.get("email") or "unknown")[:100]
    reason = reason_text[:500]

    try:
        from api.connection_pool import execute_on_intelligence
        # MERGE: insert ou update
        execute_on_intelligence(
            "MERGE dbo.collector_task_overrides AS t "
            "USING (SELECT ? AS task_name) AS s ON t.task_name = s.task_name "
            "WHEN MATCHED THEN UPDATE SET enabled = ?, changed_by = ?, changed_at = SYSUTCDATETIME(), reason = ? "
            "WHEN NOT MATCHED THEN INSERT (task_name, enabled, changed_by, reason) VALUES (?, ?, ?, ?);",
            params=(task_name, body.enabled, changed_by, reason,
                    task_name, body.enabled, changed_by, reason),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao gravar override: {e}")

    action_label = "ENABLED" if body.enabled else "DISABLED"
    action_pt = "activado" if body.enabled else "desactivado"

    # Audit trail (append-only — historico completo de quem activou/desactivou)
    try:
        execute_on_intelligence(
            "INSERT INTO dbo.collector_toggle_audit "
            "(task_name, action, changed_by, reason) VALUES (?, ?, ?, ?)",
            params=(task_name, action_label, changed_by, reason),
        )
    except Exception as e:
        logger.warning("[CollectorToggle] audit insert falhou (nao fatal): %s", e)

    logger.info("[CollectorToggle] %s %s por %s — motivo: %s", task_name, action_pt, changed_by, reason)

    return {
        "success": True,
        "task_name": task_name,
        "enabled": body.enabled,
        "changed_by": changed_by,
        "reason": reason,
        "message": f"Task {action_pt} com sucesso.",
    }


@router.get("/{task_name}/toggle-history")
async def toggle_history(
    task_name: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Historico de activacoes/desactivacoes de um task."""
    try:
        from api.async_db import async_execute_on_intelligence
        rows = await async_execute_on_intelligence(
            f"SELECT TOP {int(limit)} audit_id, task_name, action, changed_by, "
            f"changed_at, reason FROM dbo.collector_toggle_audit WITH (NOLOCK) "
            f"WHERE task_name = '{task_name.replace(chr(39), chr(39)*2)}' "
            f"ORDER BY changed_at DESC"
        ) or []
        return {"count": len(rows), "history": rows}
    except Exception as e:
        raise safe_http_error(500, e, "CollectorToggle history")


@router.delete("/{task_name}/toggle")
async def remove_override(
    task_name: str,
    admin: Dict[str, Any] = Depends(_require_admin_for_collectors),
):
    """Remove override — task volta ao estado definido no config.yaml."""
    try:
        from api.connection_pool import execute_on_intelligence
        execute_on_intelligence(
            "DELETE FROM dbo.collector_task_overrides WHERE task_name = ?",
            params=(task_name,),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao remover override: {e}")

    return {"success": True, "message": f"Override removido. Task volta ao estado do config.yaml."}


@router.post("/{task_name}/run")
async def run_task(
    task_name: str,
    body: Optional[RunRequest] = None,
    admin: Dict[str, Any] = Depends(_require_admin_for_collectors),
    _origem: None = Depends(require_same_origin),
):
    """Insere request PENDING em dbo.collector_run_requests.

    O WatcherDBCollector service (V1) tem de ter um poller que le esta tabela
    e executa o collector out-of-band. Esta API nao invoca directamente — evita
    conflito de locks com o scheduler (ver decisao no PROMPT: Opcao B).
    """
    task = get_task(task_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_name}' nao existe")

    # Verificar enabled: override na BD toma precedencia sobre config.yaml
    effective_enabled = task.get("enabled", True)
    try:
        from api.connection_pool import execute_on_intelligence
        ovr = execute_on_intelligence(
            "SELECT enabled FROM dbo.collector_task_overrides WITH (NOLOCK) WHERE task_name = ?",
            params=(task_name,),
        )
        if ovr:
            effective_enabled = bool(ovr[0].get("enabled"))
    except Exception:
        pass  # Se falhar a ler override, usa config.yaml

    if not effective_enabled:
        raise HTTPException(status_code=409, detail="Task esta DISABLED (config.yaml + sem override activo). Active primeiro via toggle.")

    try:
        from api.connection_pool import execute_on_intelligence
    except ImportError:
        raise HTTPException(status_code=500, detail="connection_pool nao disponivel")

    # Inserir PENDING; depois service (V1) faz poll
    triggered_by = (admin.get("username") or admin.get("email") or "unknown")[:100]
    reason = (body.reason if body else None) or "manual trigger via portal"

    try:
        execute_on_intelligence(
            "INSERT INTO dbo.collector_run_requests "
            "(task_name, requested_by, status, metadata_json) "
            "VALUES (?, ?, 'PENDING', ?)",
            params=(task_name, triggered_by, json.dumps({"reason": reason[:500]})),
        )
        # Obter o ID recem-inserido
        rows = execute_on_intelligence(
            "SELECT TOP 1 request_id, requested_at FROM dbo.collector_run_requests WITH (NOLOCK) "
            "WHERE task_name = ? AND requested_by = ? ORDER BY request_id DESC",
            params=(task_name, triggered_by),
        ) or []
        request_id = rows[0].get("request_id") if rows else None

        # Audit log separado
        try:
            execute_on_intelligence(
                "INSERT INTO dbo.collector_manual_runs "
                "(task_name, triggered_by, metadata_json) VALUES (?, ?, ?)",
                params=(task_name, triggered_by, json.dumps({"request_id": request_id, "reason": reason[:500]})),
            )
        except Exception as e:
            logger.warning("[CollectorRun] audit log falhou (nao fatal): %s", e)

        return {
            "success": True,
            "request_id": request_id,
            "task_name": task_name,
            "status": "PENDING",
            "poll_url": f"/api/v1/collectors/runs/{request_id}" if request_id else None,
            "message": (
                "Pedido registado. O WatcherDBCollector service ira executar na proxima "
                "iteracao do poller (~10s). Poll request_id para estado."
            ),
        }
    except Exception as e:
        logger.error("[CollectorRun] falha a inserir request: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Falha a registar run request: {e}")


# =============================================================================
# Service status (Windows sc query)
# =============================================================================
@router.get("/service/status")
async def service_status():
    """Invoca `sc query WatcherDBCollector` local."""
    try:
        proc = subprocess.run(
            ["sc", "query", "WatcherDBCollector"],
            capture_output=True, text=True, timeout=10,
        )
        out = proc.stdout or ""
        state = "UNKNOWN"
        lower = out.lower()
        if "running" in lower:
            state = "RUNNING"
        elif "stopped" in lower:
            state = "STOPPED"
        elif "paused" in lower:
            state = "PAUSED"
        elif proc.returncode != 0:
            state = "NOT_INSTALLED_OR_ACCESS_DENIED"
        return {
            "service_name": "WatcherDBCollector",
            "state": state,
            "return_code": proc.returncode,
            "raw_output": out[-2000:],
        }
    except FileNotFoundError:
        return {
            "service_name": "WatcherDBCollector",
            "state": "NOT_AVAILABLE",
            "message": "comando 'sc' nao encontrado (nao-Windows ou PATH errado)",
        }
    except subprocess.TimeoutExpired:
        return {
            "service_name": "WatcherDBCollector",
            "state": "TIMEOUT",
            "message": "sc query excedeu 10s",
        }
    except Exception as e:
        raise safe_http_error(500, e, "CollectorService sc query")


# =============================================================================
# Lista simples de tasks (sem estado — util para dropdowns)
# =============================================================================
@router.get("/tasks")
async def list_tasks():
    """Lista o config.yaml de todos os tasks (read-only, sem state)."""
    return {"count": len(get_tasks()), "tasks": get_tasks()}


# =============================================================================
# Run history + success rate (via views validadas em PRD)
# =============================================================================
@router.get("/runs/recent")
async def recent_runs(
    limit: int = Query(50, ge=1, le=500),
    task_name: Optional[str] = Query(None),
):
    """Historico recente de run requests (vw_collector_recent_runs).

    Inclui wait_seconds e pickup_lag_seconds para monitorizar latencia do poller.
    """
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        raise HTTPException(status_code=500, detail="async_db nao disponivel")
    try:
        if task_name:
            safe = task_name.replace("'", "''")
            q = (
                f"SELECT TOP {int(limit)} * FROM dbo.vw_collector_recent_runs "
                f"WHERE task_name = '{safe}' ORDER BY requested_at DESC"
            )
        else:
            q = f"SELECT TOP {int(limit)} * FROM dbo.vw_collector_recent_runs ORDER BY requested_at DESC"
        rows = await async_execute_on_intelligence(q) or []
        return {"count": len(rows), "runs": rows}
    except Exception as e:
        raise safe_http_error(500, e, "CollectorRuns recent_runs")


@router.get("/runs/success-rate")
async def success_rate_24h():
    """Taxa de sucesso agregada 24h (vw_collector_success_rate_24h)."""
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        raise HTTPException(status_code=500, detail="async_db nao disponivel")
    try:
        rows = await async_execute_on_intelligence(
            "SELECT * FROM dbo.vw_collector_success_rate_24h"
        ) or []
        return rows[0] if rows else {}
    except Exception as e:
        raise safe_http_error(500, e, "CollectorRuns success_rate")


# =============================================================================
# Wave D Fase 3 — verificador de trabalho agendado (declarado vs instalado)
# Expoe WDB_SCHEDULED_WORK_AUDIT: os achados que hoje vivem so na BD. O DBA
# deixa de precisar de correr SQL para saber se um job/tarefa parou em silencio.
# =============================================================================
@router.get("/scheduled-work/audit")
async def scheduled_work_audit():
    """Ultimo estado do verificador de trabalho agendado (Wave D).

    Devolve: os achados abertos da corrida mais recente de CADA fase
    (SQL Agent + Task Scheduler), a prova-de-vida (linha OK) de cada uma, e
    ha_quanto_tempo cada fase correu -- para o proprio verificador ser
    detectavel se parar.
    """
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        raise HTTPException(status_code=500, detail="async_db nao disponivel")
    try:
        # Achados nao-OK, DEDUPLICADOS por (Check_Type, Item): o verificador
        # reescreve os mesmos achados a cada ciclo/restart -- so interessa o
        # estado mais recente de cada um (janela de 26h cobre os diarios).
        achados = await async_execute_on_intelligence(
            "WITH ranked AS ("
            "  SELECT Check_Type, Item, Detail, Severity, Run_TS, "
            "         ROW_NUMBER() OVER (PARTITION BY Check_Type, Item "
            "                            ORDER BY Run_TS DESC) AS rn "
            "  FROM dbo.WDB_SCHEDULED_WORK_AUDIT WITH (NOLOCK) "
            "  WHERE Check_Type <> 'OK' "
            "    AND Run_TS >= DATEADD(HOUR, -26, GETDATE())) "
            "SELECT Check_Type, Item, Detail, Severity, "
            "       CONVERT(varchar(19), Run_TS, 120) AS Run_TS "
            "FROM ranked WHERE rn = 1 "
            "ORDER BY CASE Severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, "
            "         Run_TS DESC"
        ) or []
        # Prova de vida: ultima linha OK e ha quanto tempo (por fase/item)
        vida = await async_execute_on_intelligence(
            "SELECT Item, CONVERT(varchar(19), MAX(Run_TS), 120) AS Ultima_OK, "
            "       DATEDIFF(MINUTE, MAX(Run_TS), GETDATE()) AS Min_Desde "
            "FROM dbo.WDB_SCHEDULED_WORK_AUDIT WITH (NOLOCK) "
            "WHERE Check_Type = 'OK' GROUP BY Item"
        ) or []
        return {
            "achados_abertos": len(achados),
            "achados": achados,
            "prova_de_vida": vida,
        }
    except Exception as e:
        raise safe_http_error(500, e, "ScheduledWorkAudit")


# NOTA: /runs/{request_id} DEVE estar APOS /runs/recent e /runs/success-rate
# (paths estaticos antes de parametrizados — FastAPI faz match por ordem).
@router.get("/runs/{request_id}")
async def get_run_status(request_id: int):
    """Poll do estado de um request manual."""
    try:
        from api.async_db import async_execute_on_intelligence
    except ImportError:
        raise HTTPException(status_code=500, detail="async_db nao disponivel")

    rows = await async_execute_on_intelligence(
        f"SELECT request_id, task_name, requested_at, requested_by, status, "
        f"started_at, completed_at, duration_ms, error_message, result_json "
        f"FROM dbo.collector_run_requests WITH (NOLOCK) "
        f"WHERE request_id = {int(request_id)}"
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail=f"Request #{request_id} nao existe")
    row = rows[0]
    raw = row.get("result_json")
    if raw:
        try:
            row["result"] = json.loads(raw)
        except Exception:
            pass
    return row
