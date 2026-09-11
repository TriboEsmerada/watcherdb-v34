# -*- coding: utf-8 -*-
"""LOTE AG-RESUME (GO do owner 2026-09-11) -- drill "Acompanhar resume" no separador Always On.

Consenso (sql-deep-reviewer + watcherdb-frontend-specialist + v33/v34-specialist, 2026-09-11):
drill on-demand, sem DDL, sem collector, sem Chart.js/Canvas; tier Std (FEATURE_MATRIX:59-62,
mesmo precedente do drill de mirroring). Endpoint read-only sem gate admin (como os irmaos
mirroring/tlog: so' o AuthEnforcementMiddleware). Botao nas DUAS tabelas por base do Always On.
Correccao do bug pre-existente no mesmo lote: filas em KB comparadas com 1000 e rotuladas "1GB".

Objeccao dos dois especialistas ("redo_queue_size vem NULL quando lido na primaria") DESFEITA por
medicao (CONTEXT 2026-09-11): 384/384 linhas remotas lidas nas primarias pela familia AG_QUEUES
trazem redo queue e redo rate preenchidos, incluindo NOT SYNCHRONIZING. O comentario do codigo
(watcherdb_alwayson_check.py:545) e' verdadeiro para database_state_desc. Desenho final: amostra
na primaria (re-target automatico se o server_id for secundaria) + fallback a secundaria SO quando
as colunas de redo vierem nulas com a replica ligada.

Divergencias deliberadas (explicadas): (1) limiares em constantes do modulo (RESUME_DEFAULTS),
nao no registo de thresholds -- entrar no registo expoe-os no ecra de Thresholds do cliente e
isso e' decisao de produto do owner; (2) o lag falso por DATEDIFF no painel LIVE
(live_monitoring.py:784 / portal ~51364) fica para lote proprio -- ficheiro e superficie distintos.

Pecas:
  A. api/routers/queries/alwayson_resume.py (NOVO): GET /api/queries/alwayson-resume-sample/{server_id}?ag=&db=
     - regex de entrada (sem [ ] ' " ;), literais N'...' escapados, timeout 5 s, sem 500 por bloco
     - deteccao de secondary_lag_seconds via sys.all_columns (2016+), lag = commit primaria - commit secundaria
     - state_code por precedencia: SUSPENDED > REVERTING > INITIALIZING > NOT_SYNC > SYNCING > SYNCED > ASYNC_HEALTHY
       (replica assincrona nunca fica SYNCHRONIZED: SYNCHRONIZING com filas <= 64 KB = ASYNC_HEALTHY)
  B. api/routers/queries/__init__.py: registo do router
  C. templates/watcherdb_portal.html: botao nas 2 tabelas + limiar 51200 KB (50 MB) + modal/JS/CSS do drill
     (casca .inv-modal, _dg2 topbar, createDiskSparklineSVG, amostra 10 s em memoria, declive por minimos
     quadrados, ETA por declive, progresso = 1 - fila/baseline, estagnacao 18 amostras, conclusao 3 amostras)
  D. static/i18n/{pt,en,es}.json: objecto alwayson.resume.* (42 chaves)
  E. tests/unit/test_alwayson_resume_20260911.py (NOVO): 14 testes
  F. docs/changelog/CHANGELOG.md: entrada [Unreleased]

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/AG_RESUME_DRILL_2026-09-11_apply.py --check
  py docs/context/AG_RESUME_DRILL_2026-09-11_apply.py --preview DIR
  py docs/context/AG_RESUME_DRILL_2026-09-11_apply.py
Depois:
  py -m pytest tests/unit/test_alwayson_resume_20260911.py tests/unit/test_i18n_parity.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; Always On do SQLHDSPRD406 (MYBAGP2 na 405 esta
  NOT SYNCHRONIZING com ~13 GB de redo em fila: caso real para validar).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
QINIT = ROOT / "api" / "routers" / "queries" / "__init__.py"
ROUTER = ROOT / "api" / "routers" / "queries" / "alwayson_resume.py"
TEST = ROOT / "tests" / "unit" / "test_alwayson_resume_20260911.py"
CHG = ROOT / "docs" / "changelog" / "CHANGELOG.md"
I18N = {loc: ROOT / "static" / "i18n" / f"{loc}.json" for loc in ("pt", "en", "es")}

# =============================================================================
# A. BACKEND
# =============================================================================
ROUTER_SRC = r'''# -*- coding: utf-8 -*-
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
'''

# =============================================================================
# C. PORTAL -- JS + CSS
# =============================================================================
PORTAL_JS = r'''        // ===================================================================
        // Always On: drill "Acompanhar resume" (2026-09-11, GO do owner)
        // Amostra /api/queries/alwayson-resume-sample a cada 10 s enquanto o
        // modal esta aberto; amostras ficam em memoria da sessao (por AG|base).
        // Declive por minimos quadrados sobre as ultimas 6 amostras (nao o
        // rate da DMV, que e' media movel e ignora a geracao de log);
        // ETA = fila / -declive; progresso = 1 - fila / baseline (1a amostra);
        // estagnacao = 18 amostras sem descer; conclusao = 3 amostras seguidas
        // em SYNCED (sync) ou ASYNC_HEALTHY (async).
        // ===================================================================
        window._AG_QUEUE_WARN_KB = 51200;  // 50 MB. A DMV devolve KB; o codigo antigo comparava com 1000 (~1 MB) e chamava-lhe "1GB".
        window._agResumeRuns = window._agResumeRuns || {};
        function _agResumeNeeds(d) {
            if (!d) return false;
            const lsq = parseFloat(d.log_send_queue_size), rq = parseFloat(d.redo_queue_size);
            const st = String(d.synchronization_state || '').toUpperCase();
            return d.is_suspended === true || (!isNaN(lsq) && lsq > window._AG_QUEUE_WARN_KB) || (!isNaN(rq) && rq > window._AG_QUEUE_WARN_KB) ||
                (st && st !== 'SYNCHRONIZED' && st !== 'SYNCHRONIZING');
        }
        function _agResumeBtn(primary, ag, db, d) {
            if (!_agResumeNeeds(d) || !db) return '';
            return '<button type="button" class="analysis-btn ag-resume-btn" data-ag-resume-primary="' + _diagEsc(primary || '') + '" data-ag-resume-ag="' + _diagEsc(ag || '') + '" data-ag-resume-db="' + _diagEsc(db) + '" title="' + _diagEsc(t('alwayson.resume.button_title')) + '"><i class="fas fa-wave-square" aria-hidden="true"></i> ' + _diagEsc(t('alwayson.resume.button')) + '</button>';
        }
        document.addEventListener('click', function (e) {
            const b = e.target.closest && e.target.closest('[data-ag-resume-db]');
            if (!b) return;
            e.stopPropagation();
            openAgResume(b.getAttribute('data-ag-resume-primary'), b.getAttribute('data-ag-resume-ag'), b.getAttribute('data-ag-resume-db'));
        });
        function _agResumeModal() {
            let ov = document.getElementById('ag-resume-overlay');
            if (ov) return ov;
            ov = document.createElement('div');
            ov.id = 'ag-resume-overlay';
            ov.className = 'inv-modal-overlay';
            ov.style.zIndex = '100001';
            ov.innerHTML = '<div class="inv-modal" role="dialog" aria-modal="true" aria-labelledby="ag-resume-title">' +
                '<div class="inv-header"><h3 id="ag-resume-title"><i class="fas fa-wave-square" aria-hidden="true"></i> ' + _diagEsc(t('alwayson.resume.title')) + '<span data-ag-resume-sub></span></h3>' +
                '<div style="display:flex;align-items:center;gap:6px;">' +
                '<div class="dg2-topbar" data-dg2-topbar="1"><span>' + _diagEsc(t('alwayson.resume.samples_count')) + ' <span data-ag-resume-n>0</span></span><span class="dg2-topbar-sep">|</span><span>' + _diagEsc(t('alwayson.resume.next_sample')) + ' <span data-ag-resume-countdown>00:10</span></span></div>' +
                '<button class="inv-close" type="button" data-ag-resume-refresh title="' + _diagEsc(t('ui.refresh')) + '" aria-label="' + _diagEsc(t('ui.refresh')) + '"><i class="fas fa-sync-alt" aria-hidden="true"></i></button>' +
                '<button class="inv-close" type="button" data-ag-resume-max title="' + _diagEsc(t('ui.maximize')) + '" aria-label="' + _diagEsc(t('ui.maximize')) + '" style="font-size:16px;"><i class="fas fa-expand-alt" id="ag-resume-overlayMaxIcon" aria-hidden="true"></i></button>' +
                '<button class="inv-close" type="button" data-ag-resume-close aria-label="' + _diagEsc(t('ui.close')) + '">&times;</button></div></div>' +
                '<div class="inv-body" id="ag-resume-body"></div></div>';
            document.body.appendChild(ov);
            ov.addEventListener('click', function (e) {
                if (e.target === ov || (e.target.closest && e.target.closest('[data-ag-resume-close]'))) { _agResumeStop(ov); ov.classList.remove('show'); return; }
                if (e.target.closest && e.target.closest('[data-ag-resume-refresh]') && ov._ctx) { _agResumeTick(ov, true); return; }
                if (e.target.closest && e.target.closest('[data-ag-resume-max]')) { if (typeof toggleMaximizeModal === 'function') toggleMaximizeModal('ag-resume-overlay'); return; }
            });
            document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && ov.classList.contains('show')) { _agResumeStop(ov); ov.classList.remove('show'); } });
            return ov;
        }
        function _agResumeStop(ov) { if (ov && ov._agTimer) { clearInterval(ov._agTimer); ov._agTimer = null; } }
        async function openAgResume(primary, ag, db) {
            const ov = _agResumeModal();
            const key = (ag || '') + '|' + (db || '');
            ov._ctx = { primary: primary, ag: ag, db: db, key: key };
            if (!window._agResumeRuns[key]) window._agResumeRuns[key] = { samples: [], baseline: null, target: null, done: false };
            ov.classList.add('show');
            const sub = ov.querySelector('[data-ag-resume-sub]'); if (sub) sub.textContent = ' — ' + (ag || '') + ' · ' + (db || '');
            document.getElementById('ag-resume-body').innerHTML = '<div style="padding:24px; color:var(--color-text-tertiary);"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> ' + _diagEsc(t('alwayson.resume.loading')) + '</div>';
            await _agResumeTick(ov, true);
            _agResumeStop(ov);
            let remaining = 10;
            const cd = ov.querySelector('[data-ag-resume-countdown]');
            ov._agTimer = setInterval(function () {
                if (!ov.classList.contains('show')) { _agResumeStop(ov); return; }
                remaining--;
                if (cd) cd.textContent = '00:' + String(Math.max(0, remaining)).padStart(2, '0');
                if (remaining <= 0) { remaining = 10; _agResumeTick(ov, false); }
            }, 1000);
        }
        window.openAgResume = openAgResume;
        async function _agResumeTick(ov, force) {
            const c = ov._ctx; if (!c) return;
            const run = window._agResumeRuns[c.key];
            if (run.done && !force) return;
            try {
                const sid = String(c.primary || (window.currentAGInfo && (window.currentAGInfo.currentPrimary || window.currentAGInfo.currentServer)) || '').replace(/\\/g, '_');
                const url = '/api/queries/alwayson-resume-sample/' + encodeURIComponent(sid) + '?ag=' + encodeURIComponent(c.ag || '') + '&db=' + encodeURIComponent(c.db || '');
                const r = await fetch(url, { headers: { 'Authorization': 'Bearer ' + getAuthToken() } });
                const j = await r.json().catch(function () { return {}; });
                if (!r.ok || !j.success) {
                    const det = j && j.detail;
                    const msg = (det && (det.message || det)) || ('HTTP ' + r.status);
                    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
                }
                _agResumeIngest(run, j);
                _agResumeRender(ov, run, j);
                const n = ov.querySelector('[data-ag-resume-n]'); if (n) n.textContent = String(run.samples.length);
            } catch (e) {
                document.getElementById('ag-resume-body').innerHTML = '<div class="card" style="border-left:4px solid var(--sev-critical-solid); margin:16px;"><strong>' + _diagEsc(t('alwayson.resume.error')) + '</strong><div style="color:var(--color-text-tertiary); font-size:12px; margin-top:6px;">' + _diagEsc(String(e.message || e)) + '</div></div>';
            }
        }
        function _agResumePickTarget(j) {
            // a replica que interessa: suspensa, ou nao-primaria com a maior fila total
            const secs = (j.replicas || []).filter(function (r) { return r.state_code !== 'PRIMARY'; });
            if (!secs.length) return null;
            secs.sort(function (a, b) {
                const sa = a.is_suspended ? 1 : 0, sb = b.is_suspended ? 1 : 0;
                if (sa !== sb) return sb - sa;
                return ((b.log_send_queue_kb || 0) + (b.redo_queue_kb || 0)) - ((a.log_send_queue_kb || 0) + (a.redo_queue_kb || 0));
            });
            return secs[0];
        }
        function _agResumeIngest(run, j) {
            const tgt = _agResumePickTarget(j);
            const lsq = tgt ? (tgt.log_send_queue_kb || 0) : 0, rq = tgt ? (tgt.redo_queue_kb || 0) : 0;
            const s = { t: Date.now(), lsq: lsq, rq: rq, total: lsq + rq, code: tgt ? tgt.state_code : 'UNKNOWN', mode: tgt ? String(tgt.mode || '') : '' };
            if (run.target && tgt && run.target !== tgt.replica_server) { run.samples = []; run.baseline = null; run.done = false; }  // mudou a replica-alvo: recomeca
            run.target = tgt ? tgt.replica_server : null;
            run.samples.push(s);
            if (run.samples.length > 720) run.samples.shift();  // 2 h
            if (run.baseline === null || run.baseline < s.total) run.baseline = run.baseline === null ? s.total : Math.max(run.baseline, s.total);
        }
        function _agResumeSlope(samples, n) {
            const k = samples.slice(-Math.min(n || 6, samples.length));
            if (k.length < 2) return null;
            const t0 = k[0].t; let sx = 0, sy = 0, sxx = 0, sxy = 0;
            k.forEach(function (p) { const x = (p.t - t0) / 1000; sx += x; sy += p.total; sxx += x * x; sxy += x * p.total; });
            const m = k.length, den = m * sxx - sx * sx;
            return den === 0 ? null : (m * sxy - sx * sy) / den;  // KB/s (negativo = a drenar)
        }
        function _agResumeMetrics(run, j) {
            const d = (j && j.defaults) || {};
            const doneKb = d.done_queue_kb || 64, doneN = d.done_samples || 3, stallN = d.stall_samples || 18;
            const s = run.samples, last = s[s.length - 1];
            const slope = _agResumeSlope(s, 6);
            const eta = (slope !== null && slope < -0.001 && last.total > doneKb) ? last.total / (-slope) : null;
            const progress = (run.baseline && run.baseline > 0) ? Math.max(0, Math.min(100, 100 * (1 - last.total / run.baseline))) : null;
            const isAsync = /^ASYNC/i.test(last.mode);
            const okCode = isAsync ? 'ASYNC_HEALTHY' : 'SYNCED';
            const tail = s.slice(-doneN);
            const done = tail.length >= doneN && tail.every(function (p) { return p.code === okCode; });
            let stalled = false;
            if (!done && s.length >= stallN && last.total > doneKb) {
                const w = s.slice(-stallN);
                stalled = w[w.length - 1].total >= w[0].total * 0.98;  // nao desceu 2% em 3 min
            }
            run.done = done;
            return { slope: slope, eta: eta, progress: progress, done: done, stalled: stalled, isAsync: isAsync, last: last, doneKb: doneKb };
        }
        function _agResumeFmtMb(kb) { return (kb === null || kb === undefined) ? '—' : (kb / 1024).toLocaleString('pt-PT', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' MB'; }
        function _agResumeFmtDur(sec) {
            if (sec === null || sec === undefined || !isFinite(sec)) return '—';
            sec = Math.round(sec); const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s2 = sec % 60;
            return (d ? d + 'd ' : '') + String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s2).padStart(2, '0');
        }
        function _agResumeSev(code) {
            if (code === 'SUSPENDED' || code === 'NOT_SYNC') return 'CRITICAL';
            if (code === 'SYNCING' || code === 'REVERTING' || code === 'INITIALIZING') return 'WARNING';
            if (code === 'SYNCED' || code === 'ASYNC_HEALTHY' || code === 'PRIMARY') return 'OK';
            return 'INFO';
        }
        function _agResumeRender(ov, run, j) {
            const m = _agResumeMetrics(run, j);
            const T = function (k) { return _diagEsc(t('alwayson.resume.' + k)); };
            const tok = getSevTokens(m.done ? 'OK' : (m.stalled ? 'CRITICAL' : _agResumeSev(m.last.code)));
            const tile = function (label, value, sub, cls) {
                return '<div class="stat-card ' + (cls || 'gray') + '"><div class="label">' + label + '</div><div class="value" style="font-variant-numeric:tabular-nums;">' + value + '</div>' + (sub ? '<div class="diag-sub">' + sub + '</div>' : '') + '</div>';
            };
            const sevCls = { CRITICAL: 'red', WARNING: 'yellow', OK: 'green', INFO: 'gray' };
            const stateLbl = m.done ? T('completed') : (m.stalled ? T('stalled') : T('state_' + m.last.code));
            const rate = m.slope === null ? '—' : (Math.abs(m.slope) / 1024).toLocaleString('pt-PT', { maximumFractionDigits: 2 }) + ' MB/s';
            const rateSub = m.slope === null ? T('waiting_samples') : (m.slope < 0 ? T('rate_draining') : T('rate_growing'));
            const banner = m.done ? '<div class="dg2-note" style="border-color:var(--sev-ok-solid);"><i class="fas fa-check-circle" aria-hidden="true"></i><span>' + T(m.isAsync ? 'completed_async' : 'completed_sync') + '</span></div>'
                : (m.stalled ? '<div class="dg2-note" style="border-color:var(--sev-critical-solid);"><i class="fas fa-exclamation-triangle" aria-hidden="true"></i><span>' + T('stalled_note') + '</span></div>' : '');
            const vals = run.samples.map(function (p) { return p.total / 1024; });
            const spark = vals.length >= 2 ? createDiskSparklineSVG(vals, 560, 64, Math.max.apply(null, vals) || 1, tok.fill) : '<div class="diag-empty">' + T('waiting_samples') + '</div>';
            const head = '<div class="ag-resume-head"><span>' + T('sampled_on') + ' <strong>' + _diagEsc(j.sampled_on || '') + '</strong></span>' +
                (run.target ? '<span>' + T('target_replica') + ' <strong>' + _diagEsc(run.target) + '</strong> · ' + T(m.isAsync ? 'mode_async' : 'mode_sync') + '</span>' : '') +
                (j.server_now ? '<span>' + T('server_time') + ' ' + _diagEsc(j.server_now) + '</span>' : '') + '</div>';
            const tiles = '<div class="diag-summary-grid ag-resume-tiles">' +
                tile(T('tile_state'), stateLbl, T('samples_count') + ' ' + run.samples.length, sevCls[m.done ? 'OK' : (m.stalled ? 'CRITICAL' : _agResumeSev(m.last.code))]) +
                tile(T('tile_send_queue'), _agResumeFmtMb(m.last.lsq), '', m.last.lsq > (window._AG_QUEUE_WARN_KB) ? 'yellow' : 'gray') +
                tile(T('tile_redo_queue'), _agResumeFmtMb(m.last.rq), '', m.last.rq > (window._AG_QUEUE_WARN_KB) ? 'yellow' : 'gray') +
                tile(T('tile_rate'), rate, rateSub, m.slope !== null && m.slope < 0 ? 'green' : 'gray') +
                tile(T('tile_eta'), _agResumeFmtDur(m.eta), m.eta === null ? T('eta_unknown') : T('eta_by_slope'), 'gray') +
                tile(T('tile_progress'), m.progress === null ? '—' : Math.round(m.progress) + '%', T('progress_baseline') + ' ' + _agResumeFmtMb(run.baseline), 'gray') +
                '</div>';
            const chart = '<div class="ag-resume-chart"><div class="diag-section-title">' + T('chart_title') + '</div>' + spark + '</div>';
            const cols = [['col_replica', function (r) { return _diagEsc(r.replica_server || ''); }],
                          ['col_role', function (r) { return _diagEsc(r.role || ''); }],
                          ['col_mode', function (r) { return _diagEsc(String(r.mode || '').replace('_COMMIT', '')); }],
                          ['col_connected', function (r) { return _diagEsc(r.connected || ''); }],
                          ['col_sync_state', function (r) { const sv = _agResumeSev(r.state_code); return '<span class="gap-pill ' + (sv === 'CRITICAL' ? 'crit' : sv === 'WARNING' ? 'warn' : sv === 'OK' ? 'ok' : 'muted') + '">' + T('state_' + r.state_code) + '</span>'; }],
                          ['col_health', function (r) { return _diagEsc(r.sync_health || ''); }],
                          ['col_suspended', function (r) { return r.is_suspended ? '<strong style="color:var(--sev-critical-text)">' + T('yes') + '</strong>' + (r.suspend_reason ? ' <span class="dg2-subtle">' + _diagEsc(r.suspend_reason) + '</span>' : '') : T('no'); }],
                          ['col_send_queue', function (r) { return _agResumeFmtMb(r.log_send_queue_kb); }],
                          ['col_redo_queue', function (r) { return _agResumeFmtMb(r.redo_queue_kb) + (r.source === 'secondary_fallback' ? ' <span class="dg2-subtle" title="' + T('fallback_note') + '">*</span>' : ''); }],
                          ['col_lag', function (r) { return r.state_code === 'PRIMARY' ? '—' : _agResumeFmtDur(r.lag_seconds); }]];
            const table = '<div class="ag-resume-table"><table><thead><tr>' + cols.map(function (c) { return '<th>' + T(c[0]) + '</th>'; }).join('') + '</tr></thead><tbody>' +
                (j.replicas || []).map(function (r) { return '<tr' + (r.replica_server === run.target ? ' class="ag-resume-target"' : '') + '>' + cols.map(function (c) { return '<td>' + c[1](r) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></div>';
            const notes = (j.notes && j.notes.length) ? '<div class="dg2-subtle" style="margin-top:8px;">' + _diagEsc(j.notes.join(' · ')) + '</div>' : '';
            document.getElementById('ag-resume-body').innerHTML = '<div class="ag-resume-wrap">' + head + banner + tiles + chart + table + notes + '</div>';
        }
'''

PORTAL_CSS = r'''        /* Always On > drill "Acompanhar resume" (2026-09-11) */
        .ag-resume-wrap { padding: 16px 18px 20px; display: grid; gap: 14px; }
        .ag-resume-head { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 12px; color: var(--color-text-tertiary); }
        .ag-resume-head strong { color: var(--color-text-primary); }
        .ag-resume-tiles { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
        .ag-resume-chart svg { width: 100%; height: 64px; }
        .ag-resume-table { overflow-x: auto; }
        .ag-resume-table table { width: 100%; min-width: 0; font-size: 12px; }
        .ag-resume-table th, .ag-resume-table td { padding: 8px 10px; min-width: 0; max-width: none; white-space: nowrap; }
        .ag-resume-table td { font-variant-numeric: tabular-nums; }
        .ag-resume-target td { background: var(--color-bg-sunken); }
        .ag-resume-btn { padding: 4px 8px; font-size: 11px; }
        @container (max-width: 760px) { .ag-resume-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
'''

# =============================================================================
# D. I18N -- objecto alwayson.resume (pt-PT / en-US / es)
# =============================================================================
KEYS = {
    "title": ("Acompanhar resume do Always On", "Track Always On resume", "Seguir el resume de Always On"),
    "button": ("Acompanhar", "Track", "Seguir"),
    "button_title": ("Acompanhar a ressincronização desta base (amostra a cada 10 s enquanto o modal estiver aberto)", "Track this database's resynchronisation (sampled every 10 s while the dialog is open)", "Seguir la resincronización de esta base (muestra cada 10 s mientras el diálogo esté abierto)"),
    "loading": ("A recolher a primeira amostra na primária…", "Collecting the first sample on the primary…", "Recogiendo la primera muestra en la primaria…"),
    "error": ("Não foi possível amostrar", "Could not sample", "No fue posible muestrear"),
    "sampled_on": ("Amostrado em", "Sampled on", "Muestreado en"),
    "target_replica": ("Réplica acompanhada", "Tracked replica", "Réplica seguida"),
    "server_time": ("hora do servidor", "server time", "hora del servidor"),
    "mode_sync": ("commit síncrono", "synchronous commit", "commit síncrono"),
    "mode_async": ("commit assíncrono", "asynchronous commit", "commit asíncrono"),
    "samples_count": ("amostras:", "samples:", "muestras:"),
    "next_sample": ("próxima amostra em", "next sample in", "próxima muestra en"),
    "tile_state": ("Estado", "State", "Estado"),
    "tile_send_queue": ("Fila de envio", "Send queue", "Cola de envío"),
    "tile_redo_queue": ("Fila de redo", "Redo queue", "Cola de redo"),
    "tile_rate": ("Taxa medida", "Measured rate", "Tasa medida"),
    "tile_eta": ("Tempo estimado", "Estimated time", "Tiempo estimado"),
    "tile_progress": ("Progresso", "Progress", "Progreso"),
    "chart_title": ("Fila total (envio + redo) ao longo das amostras", "Total queue (send + redo) across samples", "Cola total (envío + redo) a lo largo de las muestras"),
    "waiting_samples": ("a aguardar mais amostras", "waiting for more samples", "esperando más muestras"),
    "rate_draining": ("a drenar (declive medido, não o rate da DMV)", "draining (measured slope, not the DMV rate)", "drenando (pendiente medida, no la tasa de la DMV)"),
    "rate_growing": ("a fila NÃO desce: a primária gera log mais depressa do que a réplica aplica", "queue is NOT shrinking: the primary generates log faster than the replica applies it", "la cola NO baja: la primaria genera log más rápido de lo que la réplica aplica"),
    "eta_unknown": ("sem tendência de descida para estimar", "no downward trend to estimate from", "sin tendencia de bajada para estimar"),
    "eta_by_slope": ("pelo declive das últimas amostras", "from the slope of the latest samples", "por la pendiente de las últimas muestras"),
    "progress_baseline": ("desde a fila inicial de", "since the initial queue of", "desde la cola inicial de"),
    "stalled": ("ESTAGNADO", "STALLED", "ESTANCADO"),
    "stalled_note": ("A fila não desceu nos últimos 3 minutos. Verifique se a réplica está suspensa, se o redo está bloqueado por uma consulta longa na secundária, ou se a rede/disco da secundária está saturado.", "The queue has not shrunk in the last 3 minutes. Check whether the replica is suspended, whether redo is blocked by a long-running query on the secondary, or whether the secondary's network/disk is saturated.", "La cola no ha bajado en los últimos 3 minutos. Compruebe si la réplica está suspendida, si el redo está bloqueado por una consulta larga en la secundaria, o si la red/disco de la secundaria está saturado."),
    "completed": ("CONCLUÍDO", "COMPLETED", "COMPLETADO"),
    "completed_sync": ("Base sincronizada (SYNCHRONIZED) em 3 amostras seguidas. O resume terminou.", "Database SYNCHRONIZED for 3 consecutive samples. The resume has finished.", "Base SYNCHRONIZED en 3 muestras seguidas. El resume ha terminado."),
    "completed_async": ("Réplica assíncrona com filas drenadas em 3 amostras seguidas. Em commit assíncrono o estado normal é SYNCHRONIZING, nunca SYNCHRONIZED.", "Asynchronous replica with drained queues for 3 consecutive samples. In asynchronous commit the normal state is SYNCHRONIZING, never SYNCHRONIZED.", "Réplica asíncrona con colas drenadas en 3 muestras seguidas. En commit asíncrono el estado normal es SYNCHRONIZING, nunca SYNCHRONIZED."),
    "fallback_note": ("valor lido diretamente na secundária (a primária não o reportou)", "value read directly on the secondary (the primary did not report it)", "valor leído directamente en la secundaria (la primaria no lo reportó)"),
    "col_replica": ("Réplica", "Replica", "Réplica"),
    "col_role": ("Papel", "Role", "Rol"),
    "col_mode": ("Modo", "Mode", "Modo"),
    "col_connected": ("Ligação", "Connection", "Conexión"),
    "col_sync_state": ("Estado", "State", "Estado"),
    "col_health": ("Saúde", "Health", "Salud"),
    "col_suspended": ("Suspensa", "Suspended", "Suspendida"),
    "col_send_queue": ("Fila de envio", "Send queue", "Cola de envío"),
    "col_redo_queue": ("Fila de redo", "Redo queue", "Cola de redo"),
    "col_lag": ("Atraso", "Lag", "Retraso"),
    "yes": ("Sim", "Yes", "Sí"),
    "no": ("Não", "No", "No"),
    "state_PRIMARY": ("Primária", "Primary", "Primaria"),
    "state_SUSPENDED": ("Suspensa", "Suspended", "Suspendida"),
    "state_REVERTING": ("A reverter (pós-failover)", "Reverting (post-failover)", "Revirtiendo (post-failover)"),
    "state_INITIALIZING": ("A inicializar", "Initializing", "Inicializando"),
    "state_NOT_SYNC": ("Não sincroniza", "Not synchronizing", "No sincroniza"),
    "state_SYNCING": ("A sincronizar", "Synchronizing", "Sincronizando"),
    "state_SYNCED": ("Sincronizada", "Synchronized", "Sincronizada"),
    "state_ASYNC_HEALTHY": ("Assíncrona em dia", "Asynchronous, caught up", "Asíncrona al día"),
    "state_UNKNOWN": ("Desconhecido", "Unknown", "Desconocido"),
}

# =============================================================================
# E. TESTES
# =============================================================================
TEST_SRC = r'''# -*- coding: utf-8 -*-
"""Contrato 2026-09-11 -- drill "Acompanhar resume" Always On (api/routers/queries/alwayson_resume.py).

async_execute_on_server mockado (molde: test_tlog_diagnosis_20260902.py). Sem BD.
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routers.queries import alwayson_resume as ar

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 11, 15, 0, 0)


def _row(**kw):
    base = {"sampled_on": "PRD01\\I01", "server_now": NOW, "ag_name": "AG1", "replica_server": "PRD01\\I01",
            "role_desc": "SECONDARY", "connected_state_desc": "CONNECTED", "availability_mode_desc": "SYNCHRONOUS_COMMIT",
            "replica_sync_health": "HEALTHY", "is_local": 0, "db_sync_state": "SYNCHRONIZED", "db_sync_health": "HEALTHY",
            "database_state_desc": None, "is_suspended": 0, "suspend_reason_desc": None,
            "log_send_queue_size": 0, "log_send_rate": 0, "redo_queue_size": 0, "redo_rate": 0,
            "last_commit_time": NOW, "last_hardened_time": NOW, "last_redone_time": NOW, "secondary_lag_seconds": None}
    base.update(kw)
    return base


# ---- state_code: precedencia ------------------------------------------------
def test_suspended_wins_even_with_zero_queues():
    assert ar.state_code(_row(is_suspended=1, db_sync_state="SYNCHRONIZED")) == "SUSPENDED"


@pytest.mark.parametrize("state,code", [("REVERTING", "REVERTING"), ("INITIALIZING", "INITIALIZING"),
                                        ("NOT SYNCHRONIZING", "NOT_SYNC"), ("SYNCHRONIZED", "SYNCED")])
def test_state_mapping(state, code):
    assert ar.state_code(_row(db_sync_state=state)) == code


def test_sync_replica_synchronizing_is_syncing_even_with_empty_queues():
    assert ar.state_code(_row(db_sync_state="SYNCHRONIZING", log_send_queue_size=0, redo_queue_size=0)) == "SYNCING"


def test_async_replica_never_synced_but_healthy_when_drained():
    r = _row(availability_mode_desc="ASYNCHRONOUS_COMMIT", db_sync_state="SYNCHRONIZING", log_send_queue_size=10, redo_queue_size=20)
    assert ar.state_code(r) == "ASYNC_HEALTHY"
    r["redo_queue_size"] = 14014220
    assert ar.state_code(r) == "SYNCING"


def test_primary_row_code():
    assert ar.state_code(_row(role_desc="PRIMARY", is_local=1)) == "PRIMARY"


# ---- lag ----------------------------------------------------------------------
def test_lag_prefers_secondary_lag_seconds_then_commit_delta():
    assert ar.lag_seconds(NOW, _row(secondary_lag_seconds=7)) == 7
    assert ar.lag_seconds(NOW, _row(last_commit_time=NOW - timedelta(seconds=90))) == 90
    assert ar.lag_seconds(None, _row()) is None


# ---- query ----------------------------------------------------------------------
def test_query_escapes_and_lag_column_only_when_detected():
    q = ar.q_sample("AG'1", "Db'X", has_lag=False)
    assert "N'AG''1'" in q and "N'Db''X'" in q and "CAST(NULL AS BIGINT) AS secondary_lag_seconds" in q
    assert "drs.secondary_lag_seconds," in ar.q_sample("AG1", "DbX", has_lag=True)


# ---- endpoint -------------------------------------------------------------------
def _run(coro):
    return asyncio.run(coro)  # 3.14: get_event_loop() sem loop corrente levanta RuntimeError


def _exec_factory(by_server, has_lag=1, calls=None, primary="PRD01\\I01"):
    async def fake(server_id, query, database="master", timeout_s=0):
        if calls is not None:
            calls.append((server_id, timeout_s))
        if "sys.all_columns" in query:
            return [{"has_lag": has_lag}]
        if "primary_replica" in query:
            return [{"primary_replica": primary}] if primary else []
        return by_server.get(server_id, [])
    return fake


def test_invalid_names_are_400(monkeypatch):
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({}))
    for ag, db in (("AG1]", "DbX"), ("AG1", "Db;X"), ("AG'1", "Db\"X")):
        with pytest.raises(HTTPException) as ei:
            _run(ar.alwayson_resume_sample("PRD01_I01", ag=ag, db=db))
        assert ei.value.status_code == 400


def test_primary_sample_shapes_replicas_and_uses_timeout(monkeypatch):
    calls = []
    rows = [_row(role_desc="PRIMARY", is_local=1, replica_server="PRD01\\I01", last_commit_time=NOW),
            _row(replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", log_send_queue_size=0, redo_queue_size=14014220,
                 redo_rate=3678, last_commit_time=NOW - timedelta(seconds=600))]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD01_I01": rows}, calls=calls))
    out = _run(ar.alwayson_resume_sample("PRD01_I01", ag="AG1", db="DbX"))
    assert out["success"] and out["sampled_on"] == "PRD01\\I01" and out["hops"] == []
    sec = [r for r in out["replicas"] if r["role"] == "SECONDARY"][0]
    assert sec["state_code"] == "SYNCING" and sec["redo_queue_kb"] == 14014220 and sec["lag_seconds"] == 600
    assert sec["source"] == "primary" and out["defaults"]["done_queue_kb"] == 64
    assert all(t == ar.TIMEOUT_S for _, t in calls)


def test_secondary_server_is_retargeted_to_primary(monkeypatch):
    # numa secundaria so' existe a linha LOCAL (medido no SQLHDSPRD405): a primaria vem de primary_replica
    sec_view = [_row(role_desc="SECONDARY", is_local=1, replica_server="PRD02\\I01", sampled_on="PRD02\\I01")]
    pri_view = [_row(role_desc="PRIMARY", is_local=1, replica_server="PRD01\\I01", sampled_on="PRD01\\I01"),
                _row(role_desc="SECONDARY", replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", redo_queue_size=500)]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD02_I01": sec_view, "PRD01_I01": pri_view}))
    out = _run(ar.alwayson_resume_sample("PRD02_I01", ag="AG1", db="DbX"))
    assert out["sampled_on"] == "PRD01\\I01" and out["hops"] == ["PRD01_I01"] and out["primary"] == "PRD01\\I01"


def test_secondary_fallback_fills_null_redo(monkeypatch):
    pri = [_row(role_desc="PRIMARY", is_local=1, replica_server="PRD01\\I01"),
           _row(replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", redo_queue_size=None, redo_rate=None, database_state_desc=None)]
    sec_local = [_row(role_desc="SECONDARY", is_local=1, replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", redo_queue_size=777, redo_rate=9, database_state_desc="ONLINE")]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD01_I01": pri, "PRD02_I01": sec_local}))
    out = _run(ar.alwayson_resume_sample("PRD01_I01", ag="AG1", db="DbX"))
    sec = [r for r in out["replicas"] if r["replica_server"] == "PRD02\\I01"][0]
    assert sec["redo_queue_kb"] == 777 and sec["database_state"] == "ONLINE" and sec["source"] == "secondary_fallback"


def test_not_found_and_not_primary_paths(monkeypatch):
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({}))
    with pytest.raises(HTTPException) as ei:
        _run(ar.alwayson_resume_sample("PRD01_I01", ag="AG1", db="DbX"))
    assert ei.value.status_code == 404
    only_sec = [_row(role_desc="SECONDARY", is_local=1)]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD02_I01": only_sec}, primary=None))
    with pytest.raises(HTTPException) as ei2:
        _run(ar.alwayson_resume_sample("PRD02_I01", ag="AG1", db="DbX"))
    assert ei2.value.status_code == 409


# ---- portal (estatico) -----------------------------------------------------------
def test_portal_button_in_both_tables_and_kb_threshold_fixed():
    portal = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
    assert portal.count("_agResumeBtn(") >= 3  # definicao + 2 tabelas
    assert "window._AG_QUEUE_WARN_KB = 51200" in portal
    assert "> 1000) return true; // Filas > 1GB" not in portal
    assert "alwayson-resume-sample/" in portal and "function openAgResume(" in portal


def test_i18n_keys_present_in_three_locales():
    import json
    for loc in ("pt", "en", "es"):
        data = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        res = data["alwayson"]["resume"]
        for k in ("title", "button", "state_SUSPENDED", "state_ASYNC_HEALTHY", "stalled_note", "completed_async"):
            assert res.get(k), f"{loc}: falta alwayson.resume.{k}"
'''

CHANGELOG_ENTRY = """- **Always On: drill "Acompanhar resume"** (GO do owner 11/09; consenso sql-deep-reviewer + frontend +
  v34). Nas bases de um AG suspensas, com filas altas ou fora de SYNCHRONIZED/SYNCHRONIZING aparece
  o botão "Acompanhar", nas duas tabelas por base do separador Always On. Abre um modal que amostra a
  DMV na primária a cada 10 s (endpoint read-only novo `GET /api/queries/alwayson-resume-sample`,
  re-target automático à primária, fallback à secundária só se o redo vier nulo) e calcula no browser
  a taxa real por declive, a estimativa de tempo, o progresso desde a fila inicial, a estagnação
  (3 min sem descer) e a conclusão por modo (síncrono: SYNCHRONIZED; assíncrono: filas drenadas em
  3 amostras). Corrige de caminho o limiar das filas na tabela do Always On: comparava KB com 1000 e
  chamava-lhe "1 GB" — passa a 50 MB. Sem DDL, sem collector, sem Chart.js. [tier: Std]
"""

# =============================================================================
# EDITS
# =============================================================================
EDITS: list[tuple[Path, str, str, int]] = []


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    EDITS.append((path, old, new, count))


# B. registo do router
edit(QINIT,
     "from api.routers.queries.tlog_diagnosis import router as tlog_diagnosis_router  # 2026-09-02 drill-down transaction log por base\n",
     "from api.routers.queries.tlog_diagnosis import router as tlog_diagnosis_router  # 2026-09-02 drill-down transaction log por base\n"
     "from api.routers.queries.alwayson_resume import router as alwayson_resume_router  # 2026-09-11 drill 'Acompanhar resume' Always On\n")
edit(QINIT,
     "router.include_router(tlog_diagnosis_router)\n",
     "router.include_router(tlog_diagnosis_router)\n"
     "router.include_router(alwayson_resume_router)\n")

# C1. tabela da vista "do Primario" (renderAlwaysOnFromPrimary): header + linha
edit(PORTAL,
     "<tr><th>Base</th><th>Sync State</th><th>Health</th><th>DB State</th><th>Suspensa</th><th>Log Send Queue</th><th>Redo Queue</th></tr>",
     "<tr><th>Base</th><th>Sync State</th><th>Health</th><th>DB State</th><th>Suspensa</th><th>Log Send Queue</th><th>Redo Queue</th><th></th></tr>")
edit(PORTAL,
     "                                                <td>${d.redo_queue_size ?? 'N/A'}</td>\n"
     "                                            </tr>\n",
     "                                                <td>${d.redo_queue_size ?? 'N/A'}</td>\n"
     "                                                <td>${_agResumeBtn(primaryServerName, agName, d.database_name, d)}</td>\n"
     "                                            </tr>\n")

# C2. tabela da vista local (loadAlwaysOn): header + linha
edit(PORTAL,
     '<th style="padding: 12px; border-bottom: 2px solid ${borderColor}; color: ${borderColor};">Redo Queue</th>\n'
     '                                                    </tr>\n',
     '<th style="padding: 12px; border-bottom: 2px solid ${borderColor}; color: ${borderColor};">Redo Queue</th>\n'
     '                                                        <th style="padding: 12px; border-bottom: 2px solid ${borderColor};"></th>\n'
     '                                                    </tr>\n')
edit(PORTAL,
     '                                                            <td style="padding: 12px;">${d.redo_queue_size ?? \'N/A\'}</td>\n'
     '                                                        </tr>\n',
     '                                                            <td style="padding: 12px;">${d.redo_queue_size ?? \'N/A\'}</td>\n'
     '                                                            <td style="padding: 12px;">${_agResumeBtn((window.currentAGInfo && (window.currentAGInfo.currentPrimary || window.currentAGInfo.currentServer)) || serverId, (window.currentAGInfo && window.currentAGInfo.agName) || \'\', d.database_name, d)}</td>\n'
     '                                                        </tr>\n')

# C3. limiar KB rotulado "1GB" (bug pre-existente, 4 sitios)
edit(PORTAL,
     "if (!isNaN(logQueueNum) && logQueueNum > 1000) return true; // Filas > 1GB são problema",
     "if (!isNaN(logQueueNum) && logQueueNum > (window._AG_QUEUE_WARN_KB || 51200)) return true; // 2026-09-11: KB nativos da DMV; era 1000 (~1 MB) rotulado \"1GB\"")
edit(PORTAL,
     "if (!isNaN(redoQueueNum) && redoQueueNum > 1000) return true; // Filas > 1GB são problema",
     "if (!isNaN(redoQueueNum) && redoQueueNum > (window._AG_QUEUE_WARN_KB || 51200)) return true; // 2026-09-11: idem")
edit(PORTAL,
     "parseFloat(d.log_send_queue_size) > 1000) ||",
     "parseFloat(d.log_send_queue_size) > (window._AG_QUEUE_WARN_KB || 51200)) ||")
edit(PORTAL,
     "parseFloat(d.redo_queue_size) > 1000);",
     "parseFloat(d.redo_queue_size) > (window._AG_QUEUE_WARN_KB || 51200));")

# C4. bloco JS + CSS
edit(PORTAL,
     "        // ---- Vista Avancada RICA (topo polido + cards ricos + Resumo Executivo) ----\n",
     PORTAL_JS + "\n        // ---- Vista Avancada RICA (topo polido + cards ricos + Resumo Executivo) ----\n")
edit(PORTAL,
     "        /* Report content - DARK MODE */\n",
     PORTAL_CSS + "\n        /* Report content - DARK MODE */\n")


def patch_i18n(raw: str, loc_idx: int) -> tuple[str | None, str | None]:
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    try:
        s = next(i for i, l in enumerate(lines) if l.rstrip() == '  "alwayson": {')
    except StopIteration:
        return None, 'bloco "alwayson" nao encontrado'
    if any(l.strip() == '"resume": {' for l in lines[s + 1:s + 200]):
        return None, "ja aplicado (alwayson.resume existe)"
    block = ['    "resume": {']
    items = list(KEYS.items())
    for i, (k, vals) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        block.append(f'      "{k}": {json.dumps(vals[loc_idx], ensure_ascii=False)}{comma}')
    block.append("    },")
    lines[s + 1:s + 1] = block
    out = nl.join(lines)
    try:
        json.loads(out)
    except Exception as ex:
        return None, f"json invalido: {ex}"
    return out, None


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    preview_dir = None
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv):
            print("--preview precisa de DIR"); return 2
        preview_dir = Path(argv[i + 1]).resolve()

    problems: list[str] = []
    contents: dict[Path, str] = {}
    for p in {e[0] for e in EDITS}:
        if not p.exists():
            problems.append(f"nao existe: {p}"); continue
        contents[p] = p.read_bytes().decode("utf-8")
    if ROUTER.exists():
        problems.append(f"ja existe: {ROUTER.relative_to(ROOT)} (lote ja aplicado?)")
    if problems:
        print("[ABORT]"); [print("  -", x) for x in problems]; return 1

    applied = 0
    for path, old, new, count in EDITS:
        text = contents[path]
        eol = "\r\n" if "\r\n" in text else "\n"
        old_n, new_n = old.replace("\n", eol), new.replace("\n", eol)
        n = text.count(old_n)
        if n != count:
            problems.append(f"{path.name}: esperado {count}x, encontrado {n}x: {old[:80]!r}"); continue
        contents[path] = text.replace(old_n, new_n); applied += 1
        print(f"[ok] {path.name}: {count}x {old[:58]!r}")

    i18n_out: dict[Path, str] = {}
    for idx, loc in enumerate(("pt", "en", "es")):
        raw = I18N[loc].read_bytes().decode("utf-8")
        out, err = patch_i18n(raw, idx)
        if err:
            problems.append(f"{loc}.json: {err}")
        else:
            i18n_out[I18N[loc]] = out; print(f"[ok] {loc}.json: +{len(KEYS)} chaves alwayson.resume.*")

    craw = CHG.read_bytes().decode("utf-8"); cnl = "\r\n" if "\r\n" in craw else "\n"
    anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1:
        problems.append("CHANGELOG: ancora '## [Unreleased] / ### Changed' nao encontrada")
    if 'drill "Acompanhar resume"' in craw:
        problems.append("CHANGELOG: ja aplicado")

    if problems:
        print(f"\n{len(problems)} problema(s) -- NADA escrito:"); [print("  -", x) for x in problems]; return 1
    if check_only:
        print(f"\n--check OK: {applied} edicoes + router novo + teste novo + {len(KEYS)} chaves x3 locales + CHANGELOG. Nada escrito.")
        return 0

    target = preview_dir if preview_dir is not None else ROOT
    def w(path: Path, text: str, tag: str) -> None:
        out = target / path.relative_to(ROOT); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8")); print(f"[{tag}] {out.relative_to(target)}")
    for path, text in contents.items():
        w(path, text, "write")
    for path, text in i18n_out.items():
        w(path, text, "write")
    w(ROUTER, ROUTER_SRC, "new")
    w(TEST, TEST_SRC, "new")
    w(CHG, craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1), "write")
    if preview_dir is not None:
        print(f"\n--preview OK: copias em {preview_dir}. Repo intacto.")
    else:
        print("\nAplicado. Corre agora:\n  py -m pytest tests/unit/test_alwayson_resume_20260911.py tests/unit/test_i18n_parity.py -q --no-cov\n"
              "  py scripts/i18n_validate.py\n  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; Always On do SQLHDSPRD406")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
