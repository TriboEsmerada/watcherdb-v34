# -*- coding: utf-8 -*-
"""GET /api/queries/alwayson-resume-sample/{server_id}?ag=...&db=...   (2026-09-11)

Amostra pontual de sys.dm_hadr_database_replica_states para o drill "Acompanhar resume"
do separador Always On. O portal chama isto a cada 10 s enquanto o modal esta aberto e
calcula no browser declive da fila, ETA, progresso, estagnacao e conclusao. Nada e'
persistido; nada e' alterado no servidor.

Regras (consenso 2026-09-11):
  - Corre na PRIMARIA. Se o server_id recebido for uma secundaria, faz UM salto para a
    primaria que a topologia do AG indica (catalogo replicado, fiavel em qualquer no').
  - As colunas reportadas pela secundaria (redo_*) vem preenchidas na primaria para
    replicas ligadas (medido: 384/384 na frota). Se vierem NULL e a replica estiver
    ligada, faz UM salto a essa secundaria para as ler no local (fallback, nunca regra).
  - Devolve CODIGOS, nao texto: SUSPENDED > REVERTING > INITIALIZING > NOT_SYNC >
    SYNCING > SYNCED > ASYNC_HEALTHY. Replica assincrona nunca fica SYNCHRONIZED --
    SYNCHRONIZING com filas <= done_queue_kb e' o "saudavel" dela.
  - lag = last_commit_time(primaria) - last_commit_time(secundaria); em 2016+ tambem
    secondary_lag_seconds. Nunca DATEDIFF contra GETDATE (base ociosa != atraso).
  - Identidade: pool da aplicacao (sql_monitoring). VIEW SERVER STATE + VIEW ANY
    DEFINITION ja' concedidos (canonical :10044).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.async_db import async_execute_on_server

logger = logging.getLogger(__name__)
router = APIRouter()

_NAME = re.compile(r"^[^\[\]'\";]{1,128}$")
TIMEOUT_S = 5

# Defaults do drill. Follow-up (decisao do owner): expor no registo de thresholds
# (api/kpi_thresholds_registry.py, chave alwayson_resume) se quiser configuravel pelo cliente.
RESUME_DEFAULTS: Dict[str, int] = {
    "done_queue_kb": 64,        # filas <= 64 KB = drenado
    "done_samples": 3,          # 3 amostras seguidas (30 s) para declarar concluido
    "stall_samples": 18,        # 18 amostras (3 min) sem a fila descer = estagnado
    "attention_queue_kb": 51200,  # 50 MB: a partir daqui a base merece o botao
}

STATE_CODES = ("SUSPENDED", "REVERTING", "INITIALIZING", "NOT_SYNC", "SYNCING", "SYNCED", "ASYNC_HEALTHY", "PRIMARY", "UNKNOWN")


def _sid(instance: str) -> str:
    """'HOST\\I01' -> 'HOST_I01' (formato server_id do pool)."""
    return (instance or "").strip().replace("\\", "_")


def _esc(v: str) -> str:
    return (v or "").replace("'", "''")


def _num(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _dt(v) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)[:26]) if v else None
    except Exception:
        return None


def _iso(v) -> Optional[str]:
    d = _dt(v)
    return d.isoformat(sep=" ", timespec="seconds") if d else None


def q_primary(ag: str) -> str:
    """Quem e' a primaria deste AG. Visivel em QUALQUER no' (estado do grupo replicado
    pelo cluster) -- ao contrario de dm_hadr_database_replica_states, que numa secundaria
    so' devolve a linha local (medido 2026-09-11 no SQLHDSPRD405)."""
    return (f"SELECT ags.primary_replica FROM sys.availability_groups ag WITH (NOLOCK) "
            f"JOIN sys.dm_hadr_availability_group_states ags WITH (NOLOCK) ON ags.group_id = ag.group_id "
            f"WHERE ag.name = N'{_esc(ag)}';")


Q_HAS_LAG = ("SELECT CASE WHEN EXISTS (SELECT 1 FROM sys.all_columns "
             "WHERE object_id = OBJECT_ID('sys.dm_hadr_database_replica_states') AND name = 'secondary_lag_seconds') "
             "THEN 1 ELSE 0 END AS has_lag;")


def q_sample(ag: str, db: str, has_lag: bool) -> str:
    lag_col = "drs.secondary_lag_seconds," if has_lag else "CAST(NULL AS BIGINT) AS secondary_lag_seconds,"
    return f"""
SELECT CAST(@@SERVERNAME AS NVARCHAR(128)) AS sampled_on, SYSDATETIME() AS server_now,
       ag.name AS ag_name, ar.replica_server_name AS replica_server,
       ars.role_desc, ars.connected_state_desc, ar.availability_mode_desc,
       ars.synchronization_health_desc AS replica_sync_health,
       drs.is_local, drs.synchronization_state_desc AS db_sync_state,
       drs.synchronization_health_desc AS db_sync_health, drs.database_state_desc,
       drs.is_suspended, drs.suspend_reason_desc,
       drs.log_send_queue_size, drs.log_send_rate, drs.redo_queue_size, drs.redo_rate,
       drs.last_commit_time, drs.last_hardened_time, drs.last_redone_time,
       {lag_col}
       drs.last_sent_lsn, drs.last_received_lsn, drs.last_hardened_lsn, drs.last_redone_lsn
FROM sys.availability_groups ag WITH (NOLOCK)
JOIN sys.availability_replicas ar WITH (NOLOCK) ON ar.group_id = ag.group_id
JOIN sys.dm_hadr_availability_replica_states ars WITH (NOLOCK) ON ars.replica_id = ar.replica_id
JOIN sys.databases d WITH (NOLOCK) ON d.name = N'{_esc(db)}'
JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK)
     ON drs.replica_id = ar.replica_id AND drs.database_id = d.database_id
WHERE ag.name = N'{_esc(ag)}'
ORDER BY drs.is_local DESC, ar.replica_server_name;
"""


def state_code(row: Dict[str, Any], defaults: Optional[Dict[str, int]] = None) -> str:
    """Codigo de estado de UMA linha (replica x base). Precedencia do consenso."""
    d = defaults or RESUME_DEFAULTS
    if str(row.get("role_desc") or "").upper() == "PRIMARY":
        return "PRIMARY"
    if row.get("is_suspended") in (True, 1, "1", "True"):
        return "SUSPENDED"
    s = str(row.get("db_sync_state") or "").upper()
    if s == "REVERTING":
        return "REVERTING"
    if s == "INITIALIZING":
        return "INITIALIZING"
    if s == "NOT SYNCHRONIZING":
        return "NOT_SYNC"
    if s == "SYNCHRONIZED":
        return "SYNCED"
    if s == "SYNCHRONIZING":
        mode = str(row.get("availability_mode_desc") or "").upper()
        lsq = _num(row.get("log_send_queue_size")) or 0.0
        rq = _num(row.get("redo_queue_size")) or 0.0
        if mode.startswith("ASYNCHRONOUS") and lsq <= d["done_queue_kb"] and rq <= d["done_queue_kb"]:
            return "ASYNC_HEALTHY"
        return "SYNCING"
    return "UNKNOWN"


def lag_seconds(primary_commit, row: Dict[str, Any]) -> Optional[float]:
    """secondary_lag_seconds (2016+) se existir; senao commit primaria - commit secundaria."""
    v = _num(row.get("secondary_lag_seconds"))
    if v is not None:
        return v
    p, s = _dt(primary_commit), _dt(row.get("last_commit_time"))
    if p and s:
        return max(0.0, (p - s).total_seconds())
    return None


def shape_replica(row: Dict[str, Any], primary_commit, source: str) -> Dict[str, Any]:
    return {
        "replica_server": row.get("replica_server"),
        "role": row.get("role_desc"),
        "connected": row.get("connected_state_desc"),
        "mode": row.get("availability_mode_desc"),
        "replica_health": row.get("replica_sync_health"),
        "sync_state": row.get("db_sync_state"),
        "sync_health": row.get("db_sync_health"),
        "database_state": row.get("database_state_desc"),
        "is_suspended": bool(row.get("is_suspended") in (True, 1, "1", "True")),
        "suspend_reason": row.get("suspend_reason_desc"),
        "log_send_queue_kb": _num(row.get("log_send_queue_size")),
        "log_send_rate_kbs": _num(row.get("log_send_rate")),
        "redo_queue_kb": _num(row.get("redo_queue_size")),
        "redo_rate_kbs": _num(row.get("redo_rate")),
        "last_commit_time": _iso(row.get("last_commit_time")),
        "last_hardened_time": _iso(row.get("last_hardened_time")),
        "last_redone_time": _iso(row.get("last_redone_time")),
        "lag_seconds": lag_seconds(primary_commit, row),
        "is_local": bool(row.get("is_local") in (True, 1, "1", "True")),
        "state_code": state_code(row),
        "source": source,
    }


async def _fetch(sid: str, ag: str, db: str, notes: List[str], label: str) -> List[Dict[str, Any]]:
    try:
        has = await async_execute_on_server(sid, Q_HAS_LAG, "master", TIMEOUT_S)
        has_lag = bool(has and int(has[0].get("has_lag") or 0) == 1)
    except Exception as e:  # 2012/2014 ou permissao: segue sem a coluna
        notes.append(f"{label}: has_lag {str(e)[:120]}")
        has_lag = False
    try:
        return await async_execute_on_server(sid, q_sample(ag, db, has_lag), "master", TIMEOUT_S) or []
    except Exception as e:
        notes.append(f"{label}: {str(e)[:160]}")
        return []


def _needs_secondary_fallback(row: Dict[str, Any]) -> bool:
    return (row.get("redo_queue_size") is None and row.get("redo_rate") is None
            and str(row.get("connected_state_desc") or "").upper() == "CONNECTED"
            and str(row.get("role_desc") or "").upper() != "PRIMARY")


@router.get("/alwayson-resume-sample/{server_id}")
async def alwayson_resume_sample(server_id: str, ag: str = Query(..., min_length=1, max_length=128),
                                 db: str = Query(..., min_length=1, max_length=128)):
    if not _NAME.match(ag) or not _NAME.match(db) or not re.match(r"^[A-Za-z0-9_.\-]{1,128}$", server_id or ""):
        raise HTTPException(status_code=400, detail="Nome de AG, base ou servidor invalido")
    notes: List[str] = []
    sid = _sid(server_id)
    rows = await _fetch(sid, ag, db, notes, f"amostra {sid}")
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "AG/base nao encontrados nesta instancia", "notes": notes})

    local = next((r for r in rows if r.get("is_local") in (True, 1, "1", "True")), rows[0])
    sampled_on = local.get("sampled_on") or server_id
    hops: List[str] = []
    if str(local.get("role_desc") or "").upper() != "PRIMARY":
        # numa secundaria as linhas remotas NAO existem: a primaria vem do estado do grupo
        primary_name = None
        try:
            prow = await async_execute_on_server(sid, q_primary(ag), "master", TIMEOUT_S)
            primary_name = (prow[0].get("primary_replica") if prow else None) or None
        except Exception as e:
            notes.append(f"primary_replica: {str(e)[:120]}")
        if not primary_name:
            prim = next((r for r in rows if str(r.get("role_desc") or "").upper() == "PRIMARY"), None)
            primary_name = prim.get("replica_server") if prim else None
        if not primary_name:
            raise HTTPException(status_code=409, detail={"code": "NOT_PRIMARY", "message": "Instancia nao e' a primaria e a primaria nao e' visivel", "notes": notes})
        psid = _sid(primary_name)
        prows = await _fetch(psid, ag, db, notes, f"primaria {psid}")
        if not prows:
            raise HTTPException(status_code=409, detail={"code": "NOT_PRIMARY", "primary": primary_name, "message": "Nao foi possivel amostrar na primaria", "notes": notes})
        rows, sid = prows, psid
        hops.append(psid)
        local = next((r for r in rows if r.get("is_local") in (True, 1, "1", "True")), rows[0])
        sampled_on = local.get("sampled_on") or primary_name

    primary_row = next((r for r in rows if str(r.get("role_desc") or "").upper() == "PRIMARY"), None)
    primary_commit = primary_row.get("last_commit_time") if primary_row else None

    replicas: List[Dict[str, Any]] = []
    fallbacks = 0
    for r in rows:
        source = "primary"
        if _needs_secondary_fallback(r) and fallbacks < 2:
            fallbacks += 1
            ssid = _sid(r.get("replica_server"))
            srows = await _fetch(ssid, ag, db, notes, f"fallback {ssid}")
            sl = next((x for x in srows if x.get("is_local") in (True, 1, "1", "True")), None)
            if sl:
                for k in ("redo_queue_size", "redo_rate", "database_state_desc", "last_redone_time", "last_redone_lsn"):
                    if r.get(k) is None and sl.get(k) is not None:
                        r[k] = sl[k]
                source = "secondary_fallback"
        replicas.append(shape_replica(r, primary_commit, source))

    return {
        "success": True,
        "ag": ag, "db": db,
        "server_id": server_id, "sampled_on": sampled_on, "hops": hops,
        "server_now": _iso(local.get("server_now")),
        "primary": primary_row.get("replica_server") if primary_row else None,
        "replicas": replicas,
        "defaults": RESUME_DEFAULTS,
        "notes": notes,
    }
