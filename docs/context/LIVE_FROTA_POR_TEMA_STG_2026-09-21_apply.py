# -*- coding: utf-8 -*-
"""
LIVE frota por tema, lote 2: TLog, Memory, Jobs, Sched e I/O sem canal, a partir da STAGING (2026-09-21, owner GO)

Lote 1 (195a40d) cobriu os 8 temas que o Fleet drilla ao vivo. Estes 5 nao vem no drill: passam a ler a ultima coleta do
coletor V1 (tabelas KPI_MSSQL_*_STG da WatcherDB_Intelligence) por um endpoint novo, so' SELECT via sql_monitoring:
  GET /api/v1/live/fleet/theme/{program}   program in tlog|memory|jobs|schedulers|io
    tlog       TLOG_USAGE_ACTIVE + regra do KPI (classify_tlog) + DISK_USAGE + DATAFILES: TODAS as bases (nao so' as
               criticas) -- o owner pediu o painel igual ao relatorio "T-Log da Frota" (TLOG_CONSUMO_FROTA_2026-09-21.html)
               sem os dois primeiros graficos: tiles, filtros, 5 graficos (ambiente, limitado/ilimitado, recovery x backup,
               risco, volumes) e a tabela instancia x base. Chart.js vendorizado (/static/vendor/chartjs, v4.5.1, CSP 'self')
               carregado on-demand; nada de CDN.
    memory     OS_PERF + SQL_MEMORY_CONFIG: Status <> OK, PLE < 300 s, < 1 GB livre no SO ou max server memory fora da recomendacao
    jobs       AGENT_JOBS: jobs activos com ultima execucao Failed/Cancelled (JOB_FAILURES_STG esta' vazia: 0 linhas em 24 h)
    schedulers SCHEDULER_HEALTH + WORKER_THREADS: workers > 50 %, runnable > 0, I/O pendente > 0 ou Status <> OK
    io         FILE_IO: ficheiros com Status WARNING/CRITICAL do coletor (latencia), piores primeiro
  Plan Cache fica neutro: nao ha staging e o drill ao vivo em 63 instancias nao e' aceitavel.
  O caminho e' /fleet/theme/{program} (3 segmentos) porque /fleet/{program} colidiria com /{instance}/tlog etc.

Portal: _LIVE_FLEET_THEME ganha os 5 temas + _LIVE_FLEET_THEME_STG; _liveRefresh escolhe o endpoint e NAO re-renderiza
quando a coleta nao mudou (o utilizador esta' a filtrar; a staging muda de 15 em 15 min); o despacho aceita o payload novo;
o renderer ganha 4 ramos tabulares + o painel T-Log (_liveRenderTlogFleet, CSS .tf-*), com cabecalho "ultima coleta hh:mm".
Locales pt/en/es: live.fleet_theme_sub_stg, live.fleet_theme_note_stg (os rotulos do painel usam _kpiT com fallback; lote i18n).
Testes: pin dos temas actualizado + tests/unit/test_live_frota_tema_stg_20260921.py (novo).

Uso: --check | --preview <dir> | (sem args) aplica. Requer o lote 1 aplicado. Idempotente (MARK = /fleet/theme/).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
BACKEND = Path("api/routers/live_monitoring.py")
T_TEMA = Path("tests/unit/test_live_frota_por_tema_20260921.py")
T_NOVO = Path("tests/unit/test_live_frota_tema_stg_20260921.py")
MARK = "/fleet/theme/"

# ------------------------------------------------------------------------------------------------------------ BACKEND
BACKEND_BLOCK = '''
# 2026-09-21 (owner, lote 2 da frota por tema): TLog/Memory/Jobs/Sched/IO sem canal, da ULTIMA COLETA (staging V1).
# So' SELECT via execute_intelligence_query (sql_monitoring). Caminho com 3 segmentos: /fleet/{program} colidiria com
# /{instance}/tlog, /{instance}/memory, ... declarados acima.
_FLEET_THEME_STG = ("tlog", "memory", "jobs", "schedulers", "io")


def _fleet_theme_tlog():
    """Painel T-Log da frota (owner: igual ao relatorio TLOG_CONSUMO_FROTA sem os 2 primeiros graficos): TODAS as bases da
    TLOG_USAGE_ACTIVE com a regra do KPI, + volumes (DISK_USAGE) + n.o de ficheiros de log (DATAFILES). Devolve (rows, total, extra)."""
    from datetime import datetime
    from api.routers.intelligence.helpers import _th
    from api.routers.intelligence.tlog_usage_classes import TLOG_BASE_QUERY, classify_tlog, _log_backup_age, _to_float
    S = INTELLIGENCE_SCHEMA
    late_h = float(_th("backup_delay_log", "warning") or 24)
    base = [dict(r) for r in (execute_intelligence_query(TLOG_BASE_QUERY.format(schema=S), raise_on_error=False) or [])]
    cls = classify_tlog(base, {"warning": _th("tlog_usage", "warning"), "critical": _th("tlog_usage", "critical")},
                        unlimited_free_gb={"warning": _th("filegroup_unlimited_free_gb", "warning"), "critical": _th("filegroup_unlimited_free_gb", "critical")},
                        log_late_hours=late_h)
    sev = {}
    for lst, s in ((cls.get("critical") or [], "CRITICAL"), (cls.get("warning") or [], "WARNING")):
        for r in lst:
            sev[(str(r.get("Instance") or "").upper(), str(r.get("Database") or "").upper())] = s
    insts = {str(r.get("Instance") or "").upper() for r in base}
    disks_raw = execute_intelligence_query(f"SELECT Instance, Drive, Total_MB, Free_MB, Percent_Free FROM {S}.KPI_MSSQL_DISK_USAGE_STG WITH (NOLOCK)", raise_on_error=False) or []
    by_inst = {}
    for d in disks_raw:
        by_inst.setdefault(str(d.get("Instance") or "").upper(), []).append(d)
    nf_rows = execute_intelligence_query(f"SELECT Instance, [Database], COUNT(*) AS n FROM {S}.KPI_MSSQL_DATAFILES_STG WITH (NOLOCK) WHERE File_Type = 'LOG' GROUP BY Instance, [Database]", raise_on_error=False) or []
    nf = {(str(x.get("Instance") or "").upper(), str(x.get("Database") or "").upper()): int(x.get("n") or 0) for x in nf_rows}
    now = datetime.now()
    rows = []
    for r in base:
        inst, db = str(r.get("Instance") or ""), str(r.get("Database") or "")
        key = (inst.upper(), db.upper())
        kind = (r.get("Log_Kind") or "LEGACY").upper()
        used = _to_float(r.get("Used_MB")) or 0.0
        cur = _to_float(r.get("Current_MB")) or 0.0
        pct = _to_float(r.get("Percent_Used")) or 0.0
        ceiling = _to_float(r.get("Ceiling_MB")) or 0.0
        vf = _to_float(r.get("Volume_Free_MB"))
        pe = _to_float(r.get("Pct_Eff"))
        if pe is None:   # UNLIMITED: ate' onde pode crescer hoje = alocado + livre no volume (relatorio 21/09)
            cap = (cur + vf) if vf else 0.0
            pe = (used * 100.0 / cap) if cap > 0 else pct
        t = ceiling if (kind in ("LIMITED", "FIXED") or (kind == "LEGACY" and 0 < ceiling < 2097152)) else None
        last_log = r.get("Last_Log_Backup_Date")
        if isinstance(last_log, str):   # execute_intelligence_query devolve datas ja' em ISO
            try:
                last_log = datetime.fromisoformat(last_log[:26])
            except ValueError:
                last_log = None
        hours = max(0.0, round((now - last_log).total_seconds() / 3600.0, 1)) if isinstance(last_log, datetime) else None
        ba = _log_backup_age(r.get("Recovery_Model"), hours, late_h)
        letter = str(r.get("Drive") or "").upper().rstrip(":\\\\")[:1]
        disk = None
        for d in by_inst.get(inst.upper(), []):
            drv = str(d.get("Drive") or "").upper()
            dfree = _to_float(d.get("Free_MB"))
            mesmo_livre = vf is not None and dfree is not None and abs(dfree - vf) < 1
            if mesmo_livre:                      # o volume do log (mount points de cluster nao partilham a letra)
                disk = d
                break
            if letter and drv.startswith(letter + ":") and disk is None:
                disk = d
        rows.append({"i": inst, "d": db, "e": r.get("Env") or "Undefined", "r": str(r.get("Recovery_Model") or "?").upper(), "k": kind,
                     "u": round(used, 1), "c": round(cur, 1), "p": round(pct, 1), "t": t, "pe": round(pe, 2), "s": sev.get(key, "OK"),
                     "g": _to_float(r.get("Next_Growth_MB")), "dr": (str(disk.get("Drive")) if disk else (letter or None)),
                     "vf": vf, "vt": _to_float(disk.get("Total_MB")) if disk else None, "vp": _to_float(disk.get("Percent_Free")) if disk else None,
                     "lb": last_log.isoformat() if isinstance(last_log, datetime) else (str(last_log) if last_log else None), "ba": ba,
                     "nf": nf.get(key, 0), "rs": r.get("Reason"), "Update_TS": r.get("Update_TS")})
    disks = [{"i": str(d.get("Instance")), "dr": str(d.get("Drive")), "t": _to_float(d.get("Total_MB")), "f": _to_float(d.get("Free_MB")), "pf": _to_float(d.get("Percent_Free"))}
             for d in disks_raw if str(d.get("Instance") or "").upper() in insts]
    return rows, len(insts), {"disks": disks, "late_h": late_h, "critical": len(cls.get("critical") or []), "warning": len(cls.get("warning") or [])}


def _fleet_theme_rows(program: str):
    """Linhas da frota para um tema, lidas da staging. Devolve (rows, total_instances[, extra])."""
    S = INTELLIGENCE_SCHEMA
    if program == "tlog":
        return _fleet_theme_tlog()
    if program == "memory":
        rows = execute_intelligence_query(f"""
            SELECT o.Instance, o.Status, o.Memory_Usage_Pct, o.PLE_Seconds, o.Total_Memory_MB, o.Available_Memory_MB, o.Max_Server_Memory_MB,
                   m.Memory_Pressure_Pct, m.Recommended_Max_Memory_MB, m.Max_Memory_Status, m.Buffer_Pool_MB, m.SQL_Plans_MB, o.Update_TS
            FROM {S}.KPI_MSSQL_OS_PERF_STG o WITH (NOLOCK)
            LEFT JOIN {S}.KPI_MSSQL_SQL_MEMORY_CONFIG_STG m WITH (NOLOCK) ON m.Instance = o.Instance
            WHERE ISNULL(o.Status, 'OK') <> 'OK' OR ISNULL(m.Max_Memory_Status, 'OK') <> 'OK'
               OR ISNULL(o.PLE_Seconds, 9999) < 300 OR ISNULL(o.Available_Memory_MB, 99999) < 1024
            ORDER BY CASE WHEN o.Status = 'CRITICAL' THEN 0 WHEN o.Status = 'WARNING' THEN 1 ELSE 2 END, o.Available_Memory_MB ASC""", raise_on_error=False) or []
        tot = execute_intelligence_query(f"SELECT COUNT(*) AS n FROM {S}.KPI_MSSQL_OS_PERF_STG WITH (NOLOCK)", raise_on_error=False) or []
        return rows, int((tot[0] or {}).get("n") or 0) if tot else 0
    if program == "jobs":
        rows = execute_intelligence_query(f"""
            SELECT TOP 80 Instance, JobName, LastRunStatus, LastRunDate, LastRunDurationSec, NextRunDate, Category, IsEnabled, HasSchedule, Update_TS
            FROM {S}.KPI_MSSQL_AGENT_JOBS_STG WITH (NOLOCK)
            WHERE LastRunStatus IN ('Failed', 'Cancelled') AND IsEnabled = 1
            ORDER BY CASE WHEN LastRunStatus = 'Failed' THEN 0 ELSE 1 END, LastRunDate DESC""", raise_on_error=False) or []
        tot = execute_intelligence_query(f"SELECT COUNT(DISTINCT Instance) AS n FROM {S}.KPI_MSSQL_AGENT_JOBS_STG WITH (NOLOCK)", raise_on_error=False) or []
        return rows, int((tot[0] or {}).get("n") or 0) if tot else 0
    if program == "schedulers":
        rows = execute_intelligence_query(f"""
            SELECT s.Instance, ISNULL(w.Status, 'OK') AS Status, s.Max_Workers, s.Current_Workers, s.Running_Workers, w.Suspended_Workers, s.Worker_Usage_Pct,
                   s.Total_Schedulers, s.Avg_Runnable_Tasks, s.Max_Runnable_Tasks, s.Total_Pending_IO, s.Avg_Work_Queue, s.Update_TS
            FROM {S}.KPI_MSSQL_SCHEDULER_HEALTH_STG s WITH (NOLOCK)
            LEFT JOIN {S}.KPI_MSSQL_WORKER_THREADS_STG w WITH (NOLOCK) ON w.Instance = s.Instance
            WHERE ISNULL(w.Status, 'OK') <> 'OK' OR ISNULL(s.Max_Runnable_Tasks, 0) > 0 OR ISNULL(s.Total_Pending_IO, 0) > 0 OR ISNULL(s.Worker_Usage_Pct, 0) > 50
            ORDER BY CASE WHEN ISNULL(w.Status, 'OK') <> 'OK' THEN 0 ELSE 1 END, s.Worker_Usage_Pct DESC, s.Max_Runnable_Tasks DESC""", raise_on_error=False) or []
        tot = execute_intelligence_query(f"SELECT COUNT(*) AS n FROM {S}.KPI_MSSQL_SCHEDULER_HEALTH_STG WITH (NOLOCK)", raise_on_error=False) or []
        return rows, int((tot[0] or {}).get("n") or 0) if tot else 0
    if program == "io":
        rows = execute_intelligence_query(f"""
            SELECT TOP 80 Instance, Database_Name, File_Type, File_Name, Size_MB, Read_Latency_Ms, Write_Latency_Ms, Num_Of_Reads, Num_Of_Writes, Status, Update_TS
            FROM {S}.KPI_MSSQL_FILE_IO_STG WITH (NOLOCK)
            WHERE Status IN ('WARNING', 'CRITICAL')
            ORDER BY CASE WHEN Status = 'CRITICAL' THEN 0 ELSE 1 END, (ISNULL(Read_Latency_Ms, 0) + ISNULL(Write_Latency_Ms, 0)) DESC""", raise_on_error=False) or []
        tot = execute_intelligence_query(f"SELECT COUNT(DISTINCT Instance) AS n FROM {S}.KPI_MSSQL_FILE_IO_STG WITH (NOLOCK)", raise_on_error=False) or []
        return rows, int((tot[0] or {}).get("n") or 0) if tot else 0
    return [], 0


@router.get("/fleet/theme/{program}")
async def get_fleet_theme(program: str):
    """Frota por tema a partir da staging (2026-09-21, owner): so' SELECT na WatcherDB_Intelligence, nunca nas instancias."""
    prog = (program or "").strip().lower()
    if prog not in _FLEET_THEME_STG:
        raise HTTPException(status_code=404, detail=f"fleet theme desconhecido: {prog}")
    res = _fleet_theme_rows(prog)
    rows, total = res[0], res[1]
    extra = res[2] if len(res) > 2 else {}
    ts = None
    for r in rows:
        v = r.get("Update_TS")
        if v is not None and (ts is None or str(v) > str(ts)):
            ts = v
    payload = {"fleet_theme": prog, "rows": rows, "count": len(rows), "total_instances": total, "collected_at": ts, "timestamp": time.time()}
    payload.update(extra)
    return _live_json(payload)


'''

EDITS_BACKEND = [
    ('''@router.get("/fleet/dashboard")
async def get_fleet_dashboard():''',
     BACKEND_BLOCK.lstrip("\n") + '''@router.get("/fleet/dashboard")
async def get_fleet_dashboard():''', 1),
]

# ------------------------------------------------------------------------------------------------------- PORTAL: CSS
CSS_TF = """        /* 2026-09-21 (owner): painel T-Log da frota no LIVE sem canal (.tf-*), tokens dos 3 temas, >= 12px */
        .tf-root { color: var(--color-text-primary); font-size: 12px; }
        .tf-head { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:6px 16px; margin-bottom:8px; }
        .tf-filters { display:flex; flex-wrap:wrap; align-items:center; gap:6px 12px; padding:6px 0 8px; border-bottom:1px solid var(--color-border); margin-bottom:10px; }
        .tf-group { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
        .tf-eyebrow { font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--color-text-tertiary); font-weight:600; margin-right:2px; }
        .tf-chip { border:1px solid var(--color-border); background:var(--color-bg-panel); color:var(--color-text-secondary); border-radius:999px; padding:2px 9px; font:inherit; font-size:12px; cursor:pointer; line-height:1.3; }
        .tf-chip:hover { color:var(--color-text-primary); border-color:var(--color-text-tertiary); }
        .tf-chip.on { background:var(--color-text-primary); color:var(--color-bg-primary); border-color:var(--color-text-primary); }
        .tf-chip .tf-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; }
        .tf-q { font:inherit; font-size:12px; padding:4px 8px; border:1px solid var(--color-border); border-radius:6px; background:var(--color-bg-panel); color:var(--color-text-primary); width:220px; }
        .tf-btn { font:inherit; font-size:12px; padding:3px 9px; border:1px solid var(--color-border); background:var(--color-bg-panel); color:var(--color-text-primary); border-radius:6px; cursor:pointer; }
        .tf-count { font-family:var(--font-mono); font-size:12px; color:var(--color-text-secondary); }
        .tf-active { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:-4px 0 10px; min-height:20px; }
        .tf-tag { background:var(--sev-warning-tint); color:var(--color-text-primary); border:1px solid var(--sev-warning-text); border-radius:6px; padding:1px 8px; font-size:12px; font-family:var(--font-mono); cursor:pointer; }
        .tf-tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; margin-bottom:12px; }
        .tf-tile { background:var(--color-bg-panel); border:1px solid var(--color-border); border-radius:8px; padding:8px 10px; cursor:pointer; text-align:left; font:inherit; color:inherit; }
        .tf-tile:hover { border-color:var(--color-text-tertiary); }
        .tf-tile.on { border-color:var(--color-text-link); box-shadow:inset 0 0 0 1px var(--color-text-link); }
        .tf-tile .v { font-size:22px; font-weight:600; font-variant-numeric:tabular-nums; line-height:1.1; margin-top:3px; color:var(--color-text-bright); }
        .tf-tile .l { font-size:12px; color:var(--color-text-secondary); margin-top:2px; }
        .tf-tile.crit .v { color:var(--sev-critical-text); } .tf-tile.warn .v { color:var(--sev-warning-text); } .tf-tile.acc .v { color:var(--color-text-link); }
        .tf-grid { display:grid; grid-template-columns:repeat(12, minmax(0, 1fr)); gap:10px; margin-bottom:12px; }
        .tf-card { background:var(--color-bg-panel); border:1px solid var(--color-border); border-radius:8px; padding:10px 12px; min-width:0; }
        .tf-card h4 { font-size:13px; font-weight:600; margin:0 0 2px; color:var(--color-text-bright); }
        .tf-card .hint { font-size:12px; color:var(--color-text-tertiary); margin-bottom:6px; }
        .tf-c12 { grid-column:span 12; } .tf-c6 { grid-column:span 6; } .tf-c4 { grid-column:span 4; }
        @media (max-width:1100px) { .tf-c4 { grid-column:span 6; } }
        @media (max-width:760px) { .tf-c6, .tf-c4 { grid-column:span 12; } }
        .tf-ch { position:relative; width:100%; }
        .tf-tablewrap { overflow-x:auto; background:var(--color-bg-panel); border:1px solid var(--color-border); border-radius:8px; }
        .tf-table { border-collapse:collapse; width:100%; font-size:12px; min-width:1040px; }
        .tf-table th, .tf-table td { padding:4px 7px; border-bottom:1px solid var(--color-border); text-align:left; white-space:nowrap; vertical-align:middle; }
        .tf-table th { position:sticky; top:0; background:var(--color-bg-sunken); font-weight:600; color:var(--color-text-secondary); cursor:pointer; user-select:none; z-index:2; }
        .tf-table th:first-child { left:0; z-index:3; }
        .tf-table td:first-child { position:sticky; left:0; background:var(--color-bg-panel); z-index:1; box-shadow:1px 0 0 var(--color-border); color:var(--color-text-link); font-weight:600; }
        .tf-table tbody tr { cursor:pointer; } .tf-table tbody tr:hover, .tf-table tbody tr:hover td:first-child { background:var(--color-bg-sunken); }
        .tf-table tbody tr.sel, .tf-table tbody tr.sel td:first-child { background:var(--sev-warning-tint); }
        .tf-table th.num, .tf-table td.num { text-align:right; font-family:var(--font-mono); font-variant-numeric:tabular-nums; }
        .tf-table th.s::after { content:" \\25B4"; color:var(--color-text-tertiary); } .tf-table th.s.desc::after { content:" \\25BE"; }
        .tf-table td.db { max-width:230px; overflow:hidden; text-overflow:ellipsis; }
        .tf-pill { display:inline-block; padding:1px 7px; border-radius:999px; font-size:12px; font-weight:600; border:1px solid transparent; }
        .tf-pill.PRD { background:var(--sev-info-tint); color:var(--sev-info-text); } .tf-pill.QLT { background:var(--sev-attention-tint); color:var(--sev-attention-text); }
        .tf-pill.TST { background:var(--sev-ok-tint); color:var(--sev-ok-text); } .tf-pill.Undefined { background:var(--color-bg-sunken); color:var(--color-text-secondary); }
        .tf-pill.CRITICAL { background:var(--sev-critical-tint); color:var(--sev-critical-text); border-color:var(--sev-critical-text); }
        .tf-pill.WARNING { background:var(--sev-warning-tint); color:var(--sev-warning-text); border-color:var(--sev-warning-text); }
        .tf-pill.OK, .tf-pill.SIMPLE, .tf-pill.UNKNOWN { color:var(--color-text-tertiary); border-color:var(--color-border); }
        .tf-pill.LATE, .tf-pill.NEVER { background:var(--sev-attention-tint); color:var(--sev-attention-text); border-color:var(--sev-attention-text); }
        .tf-bar { display:inline-block; height:8px; width:48px; background:var(--color-bg-sunken); border-radius:2px; vertical-align:middle; margin-right:6px; overflow:hidden; }
        .tf-bar b { display:block; height:100%; background:var(--color-text-link); } .tf-bar.w b { background:var(--sev-warning-text); } .tf-bar.c b { background:var(--sev-critical-text); }
        .tf-inf { color:var(--color-text-tertiary); }
        .tf-more { padding:8px 12px; text-align:center; }
        .toast-notification {"""

# -------------------------------------------------------------------------------------------------------- PORTAL: JS
TF_JS = r"""
        // 2026-09-21 (owner): painel T-Log da FROTA no LIVE sem canal -- o relatorio "T-Log da Frota" (TLOG_CONSUMO_FROTA
        // 2026-09-21) sem os dois primeiros graficos: tiles, filtros, 5 graficos e tabela instancia x base. Dados do endpoint
        // /api/v1/live/fleet/theme/tlog (staging, ultima coleta). Chart.js vendorizado, carregado on-demand (CSP 'self').
        const _tfS = { q: '', e: new Set(), k: new Set(), r: new Set(), s: new Set(), ba: new Set(), i: null, d: null, sort: { k: 'u', desc: true }, limit: 200, focusQ: false, tabId: null };
        let _tfChartP = null;
        function _tfEnsureChart() {
            if (window.Chart) return Promise.resolve(true);
            if (_tfChartP) return _tfChartP;
            _tfChartP = new Promise(res => { const s = document.createElement('script'); s.src = '/static/vendor/chartjs/chart.min.js'; s.onload = () => res(true); s.onerror = () => res(false); document.head.appendChild(s); });
            return _tfChartP;
        }
        function _tfL(k) {
            switch (k) {
                case 'title': return _kpiT('live.tf_title', 'T-Log da frota');
                case 'sub': return _kpiT('live.tf_sub', 'Consumo de transaction log por instância × base, na última coleta. Clique em barras, fatias, tiles ou linhas para filtrar; clique outra vez para desfazer. O nome da instância abre-a ao vivo.');
                case 'search': return _kpiT('live.tf_search', 'Procurar instância ou base…');
                case 'env': return _kpiT('live.tf_env', 'Ambiente');
                case 'kind': return _kpiT('live.tf_kind', 'Max size');
                case 'rec': return _kpiT('live.tf_rec', 'Recovery');
                case 'sev': return _kpiT('live.tf_sev', 'Estado');
                case 'ba': return _kpiT('live.tf_ba', 'Backup log');
                case 'clear': return _kpiT('live.tf_clear', 'Limpar filtros');
                case 'count': return _kpiT('live.tf_count', '{n} de {t} bases · {i} instâncias');
                case 'nofilter': return _kpiT('live.tf_nofilter', 'Sem filtros — a ver toda a frota.');
                case 'tag_text': return _kpiT('live.tf_tag_text', 'texto');
                case 'tag_inst': return _kpiT('live.tf_tag_inst', 'instância');
                case 'tag_db': return _kpiT('live.tf_tag_db', 'base');
                case 't_used': return _kpiT('live.tf_t_used', 'Log usado');
                case 't_used_sub': return _kpiT('live.tf_t_used_sub', 'de {c} alocado ({p}%)');
                case 't_bases': return _kpiT('live.tf_t_bases', 'Bases');
                case 't_bases_sub': return _kpiT('live.tf_t_bases_sub', '{i} instâncias');
                case 't_crit': return _kpiT('live.tf_t_crit', 'Críticas');
                case 't_crit_sub': return _kpiT('live.tf_t_crit_sub', 'regra do KPI (tecto, autogrow, volume)');
                case 't_warn': return _kpiT('live.tf_t_warn', 'Em aviso');
                case 't_warn_sub': return _kpiT('live.tf_t_warn_sub', 'a aproximar-se do limite');
                case 't_unl': return _kpiT('live.tf_t_unl', 'Ilimitadas');
                case 't_unl_sub': return _kpiT('live.tf_t_unl_sub', 'max_size = unlimited');
                case 't_lim': return _kpiT('live.tf_t_lim', 'Limitadas');
                case 't_lim_sub': return _kpiT('live.tf_t_lim_sub', 'max_size definido');
                case 't_disk': return _kpiT('live.tf_t_disk', 'Volume < 10% livre');
                case 't_disk_sub': return _kpiT('live.tf_t_disk_sub', 'disco do log quase cheio');
                case 't_bkp': return _kpiT('live.tf_t_bkp', 'Backup log em falta');
                case 't_bkp_sub': return _kpiT('live.tf_t_bkp_sub', 'FULL sem backup ou > {h}h');
                case 'c_env': return _kpiT('live.tf_c_env', 'Por ambiente');
                case 'c_env_h': return _kpiT('live.tf_c_env_h', 'Log usado (MB) por ambiente.');
                case 'c_kind': return _kpiT('live.tf_c_kind', 'Max size: limitado vs ilimitado');
                case 'c_kind_h': return _kpiT('live.tf_c_kind_h', 'Bases por tipo de max_size do ficheiro de log. LEGACY = sem detalhe de ficheiros.');
                case 'c_rec': return _kpiT('live.tf_c_rec', 'Recovery × backup de log');
                case 'c_rec_h': return _kpiT('live.tf_c_rec_h', 'Bases por recovery model e idade do último backup de log (> {h}h = LATE).');
                case 'c_risk': return _kpiT('live.tf_c_risk', 'Risco: % da capacidade × espaço livre no volume');
                case 'c_risk_h': return _kpiT('live.tf_c_risk_h', 'Cada ponto é uma base. Em cima e à esquerda = perto do max size e com pouco disco. Eixo X em escala log.');
                case 'c_disk': return _kpiT('live.tf_c_disk', 'Volumes com menos espaço livre');
                case 'c_disk_h': return _kpiT('live.tf_c_disk_h', 'Volumes das instâncias filtradas que alojam ficheiros de log, ordenados por MB livres. Vermelho < 10 % livre, amarelo < 20 %. Clique para isolar a instância.');
                case 'ax_free': return _kpiT('live.tf_ax_free', 'MB livres no volume do log (log)');
                case 'ax_cap': return _kpiT('live.tf_ax_cap', '% da capacidade');
                case 'ax_free_vol': return _kpiT('live.tf_ax_free_vol', 'MB livres no volume');
                case 'tbl': return _kpiT('live.tf_tbl', 'Tabela · instância × base');
                case 'tbl_h': return _kpiT('live.tf_tbl_h', 'Cabeçalho ordena; linha isola a instância; o nome da instância abre-a ao vivo neste programa.');
                case 'more': return _kpiT('live.tf_more', 'Mostrar mais ({n} restantes)');
                case 'rows': return _kpiT('live.tf_rows', '{n} linhas');
                case 'h_inst': return _kpiT('live.col_instance', 'Instância');
                case 'h_db': return _kpiT('live.col_database', 'Base');
                case 'h_env': return _kpiT('live.tf_h_env', 'Amb.');
                case 'h_used': return _kpiT('live.tf_h_used', 'Usado MB');
                case 'h_cur': return _kpiT('live.tf_h_cur', 'Alocado MB');
                case 'h_p': return _kpiT('live.tf_h_p', '% aloc.');
                case 'h_t': return _kpiT('live.tf_h_t', 'Max size MB');
                case 'h_pe': return _kpiT('live.tf_h_pe', '% capac.');
                case 'h_g': return _kpiT('live.tf_h_g', 'Próx. cresc. MB');
                case 'h_vf': return _kpiT('live.tf_h_vf', 'Livre vol. MB');
                case 'h_vp': return _kpiT('live.tf_h_vp', '% vol. livre');
                case 'h_lb': return _kpiT('live.tf_h_lb', 'Último bkp log');
                case 'h_nf': return _kpiT('live.tf_h_nf', 'Fich.');
                case 'h_rs': return _kpiT('live.col_reason', 'Motivo');
                case 'unl': return _kpiT('live.tf_unl', '∞ ilimitado');
                case 'lim': return _kpiT('live.tf_lim', 'limitado');
                case 'used_w': return _kpiT('live.tf_used_w', 'usado');
                case 'bases_w': return _kpiT('live.tf_bases_w', 'bases');
                case 'free_w': return _kpiT('live.tf_free_w', 'livre');
                case 'logs_here': return _kpiT('live.tf_logs_here', 'logs neste volume');
                case 'nochart': return _kpiT('live.tf_nochart', 'Gráficos indisponíveis (Chart.js não carregou).');
                default: return k;
            }
        }
        const _tfP = (s, o) => String(s).replace(/\{(\w+)\}/g, (m, k) => (o && o[k] != null) ? o[k] : m);
        const _tfCss = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
        const _tfFmt = n => n == null ? '—' : Math.round(n).toLocaleString('pt-PT');
        const _tfFmt1 = n => n == null ? '—' : (Math.round(n * 10) / 10).toLocaleString('pt-PT', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
        const _tfGb = mb => mb == null ? '—' : mb >= 10240 ? (mb / 1024).toLocaleString('pt-PT', { maximumFractionDigits: 0 }) + ' GB' : mb >= 1024 ? (mb / 1024).toLocaleString('pt-PT', { maximumFractionDigits: 1 }) + ' GB' : _tfFmt(mb) + ' MB';
        const _tfEsc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
        const _tfA = s => String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
        const _TF_ENV_C = { PRD: '--sev-info-text', QLT: '--sev-attention-text', TST: '--sev-ok-text', Undefined: '--color-text-tertiary' };
        const _TF_KIND_C = { UNLIMITED: '--color-text-link', LIMITED: '--sev-attention-text', LEGACY: '--color-text-tertiary', FIXED: '--sev-ok-text' };
        const _TF_SEV_C = { CRITICAL: '--sev-critical-text', WARNING: '--sev-warning-text', OK: '--color-text-link' };
        const _TF_BA_C = { LATE: '--sev-attention-text', NEVER: '--sev-critical-text', OK: '--sev-ok-text', SIMPLE: '--color-text-tertiary', UNKNOWN: '--color-border' };
        function _tfRows(data) {
            const S = _tfS, q = S.q;
            return (data.rows || []).filter(r =>
                (q === '#disco' ? (r.vp != null && r.vp < 10) : (!q || String(r.i).toLowerCase().includes(q) || String(r.d).toLowerCase().includes(q)))
                && (!S.e.size || S.e.has(r.e)) && (!S.k.size || S.k.has(r.k)) && (!S.r.size || S.r.has(r.r))
                && (!S.s.size || S.s.has(r.s)) && (!S.ba.size || S.ba.has(r.ba)) && (!S.i || r.i === S.i) && (!S.d || r.d === S.d));
        }
        function _tfRerender() {
            const tabId = _tfS.tabId; const cached = _liveLastData['tlog']; const screen = document.getElementById('live-screen-' + tabId);
            if (cached && screen) _liveRenderAndSet(screen, 'tlog', cached, tabId);
        }
        function _tfToggle(key, v) { const s = _tfS[key]; s.has(v) ? s.delete(v) : s.add(v); _tfS.limit = 200; _tfRerender(); }
        function _tfOnly(key, vals) { const s = _tfS[key]; const on = s.size === vals.length && vals.every(v => s.has(v)); _tfS[key] = on ? new Set() : new Set(vals); _tfRerender(); }
        function _tfInst(i) { _tfS.i = (_tfS.i === i) ? null : i; _tfS.d = null; _tfS.limit = 200; _tfRerender(); }
        function _tfDb(i, d) { if (_tfS.i === i && _tfS.d === d) { _tfS.i = null; _tfS.d = null; } else { _tfS.i = i; _tfS.d = d; } _tfRerender(); }
        function _tfDisk() { _tfS.q = _tfS.q === '#disco' ? '' : '#disco'; _tfRerender(); }
        let _tfQT = null;
        function _tfQ(v) { clearTimeout(_tfQT); _tfQT = setTimeout(() => { _tfS.q = String(v || '').trim().toLowerCase(); _tfS.focusQ = true; _tfS.limit = 200; _tfRerender(); }, 350); }
        function _tfClear() { _tfS.q = ''; ['e', 'k', 'r', 's', 'ba'].forEach(k => _tfS[k].clear()); _tfS.i = null; _tfS.d = null; _tfS.limit = 200; _tfRerender(); }
        function _tfSort(k) { const s = _tfS.sort; if (s.k === k) s.desc = !s.desc; else _tfS.sort = { k: k, desc: !['i', 'd', 'e', 'r', 'k', 'dr', 's', 'ba', 'rs'].includes(k) }; _tfRerender(); }
        function _tfMore() { _tfS.limit += 300; _tfRerender(); }
        function _tfClearOne(kind, v) { if (kind === 'q') _tfS.q = ''; else if (kind === 'i') { _tfS.i = null; _tfS.d = null; } else if (kind === 'd') _tfS.d = null; else _tfS[kind].delete(v); _tfRerender(); }
        window._tfToggle = _tfToggle; window._tfOnly = _tfOnly; window._tfInst = _tfInst; window._tfDb = _tfDb; window._tfDisk = _tfDisk; window._tfQ = _tfQ;
        window._tfClear = _tfClear; window._tfSort = _tfSort; window._tfMore = _tfMore; window._tfClearOne = _tfClearOne;
        function _liveRenderTlogFleet(data, tabId) {
            _tfS.tabId = tabId;
            const S = _tfS, all = data.rows || [], rows = _tfRows(data), esc = _tfEsc, a = _tfA;
            const lateH = data.late_h != null ? data.late_h : 24;
            const coleta = data.collected_at ? String(data.collected_at).replace('T', ' ').substring(0, 16) : '?';
            const chip = (key, v, colors) => `<button type="button" class="tf-chip${S[key].has(v) ? ' on' : ''}" onclick="_tfToggle('${key}','${a(v)}')">${colors ? `<span class="tf-dot" style="background:var(${colors[v] || '--color-text-tertiary'})"></span>` : ''}${esc(v)}</button>`;
            const group = (label, key, vals, colors) => vals.length ? `<div class="tf-group"><span class="tf-eyebrow">${label}</span>${vals.map(v => chip(key, v, colors)).join('')}</div>` : '';
            let h = `<div class="tf-root" id="tf-root-${tabId}" data-fleet-theme="tlog">`;
            h += `<div class="tf-head"><div><div style="font-size:14px;font-weight:600;color:var(--color-text-bright);"><i class="fas fa-satellite-dish" style="margin-right:6px;color:var(--color-text-link);"></i>${_tfL('title')}</div><div style="font-size:12px;color:var(--color-text-secondary);max-width:900px;">${_tfL('sub')}</div></div>`;
            h += `<div class="tf-count">${_kpiTp('live.fleet_theme_sub_stg', '{n} linhas · última coleta {ts} · {t} instâncias na coleta', { n: all.length, ts: coleta, t: data.total_instances || 0 })}</div></div>`;
            h += `<div class="tf-filters"><input type="search" class="tf-q" value="${esc(S.q === '#disco' ? '' : S.q)}" placeholder="${_tfL('search')}" aria-label="${_tfL('search')}" oninput="_tfQ(this.value)">`;
            h += group(_tfL('env'), 'e', ['PRD', 'QLT', 'TST', 'Undefined'].filter(v => all.some(r => r.e === v)), _TF_ENV_C);
            h += group(_tfL('kind'), 'k', ['UNLIMITED', 'LIMITED', 'FIXED', 'LEGACY'].filter(v => all.some(r => r.k === v)), _TF_KIND_C);
            h += group(_tfL('rec'), 'r', [...new Set(all.map(r => r.r))].sort(), null);
            h += group(_tfL('sev'), 's', ['CRITICAL', 'WARNING', 'OK'], _TF_SEV_C);
            h += group(_tfL('ba'), 'ba', ['LATE', 'NEVER', 'OK', 'SIMPLE', 'UNKNOWN'].filter(v => all.some(r => r.ba === v)), _TF_BA_C);
            h += `<button type="button" class="tf-btn" onclick="_tfClear()">${_tfL('clear')}</button><span class="tf-count">${_tfP(_tfL('count'), { n: rows.length, t: all.length, i: new Set(rows.map(r => r.i)).size })}</span></div>`;
            // filtros activos
            const tags = [];
            if (S.q) tags.push([_tfL('tag_text') + ': ' + S.q, 'q', '']);
            if (S.i) tags.push([_tfL('tag_inst') + ': ' + S.i, 'i', '']);
            if (S.d) tags.push([_tfL('tag_db') + ': ' + S.d, 'd', '']);
            [['e', 'env'], ['k', 'kind'], ['r', 'rec'], ['s', 'sev'], ['ba', 'ba']].forEach(([k, l]) => S[k].forEach(v => tags.push([_tfL(l) + ': ' + v, k, v])));
            h += `<div class="tf-active">${tags.length ? tags.map(([t, k, v]) => `<button type="button" class="tf-tag" onclick="_tfClearOne('${k}','${a(v)}')">${esc(t)} ×</button>`).join('') : `<span class="tf-count">${_tfL('nofilter')}</span>`}</div>`;
            // tiles
            const used = rows.reduce((x, r) => x + r.u, 0), cur = rows.reduce((x, r) => x + r.c, 0);
            const crit = rows.filter(r => r.s === 'CRITICAL').length, warn = rows.filter(r => r.s === 'WARNING').length;
            const unl = rows.filter(r => r.k === 'UNLIMITED').length, lim = rows.filter(r => r.k === 'LIMITED').length;
            const lowDisk = rows.filter(r => r.vp != null && r.vp < 10).length, bkp = rows.filter(r => r.ba === 'LATE' || r.ba === 'NEVER').length;
            const one = (key, v) => S[key].size === 1 && S[key].has(v);
            const tiles = [
                [_tfL('t_used'), _tfGb(used), _tfP(_tfL('t_used_sub'), { c: _tfGb(cur), p: cur ? _tfFmt1(used * 100 / cur) : 0 }), 'acc', '', false],
                [_tfL('t_bases'), rows.length, _tfP(_tfL('t_bases_sub'), { i: new Set(rows.map(r => r.i)).size }), '', '', false],
                [_tfL('t_crit'), crit, _tfL('t_crit_sub'), 'crit', "_tfOnly('s',['CRITICAL'])", one('s', 'CRITICAL')],
                [_tfL('t_warn'), warn, _tfL('t_warn_sub'), 'warn', "_tfOnly('s',['WARNING'])", one('s', 'WARNING')],
                [_tfL('t_unl'), unl, _tfL('t_unl_sub'), '', "_tfOnly('k',['UNLIMITED'])", one('k', 'UNLIMITED')],
                [_tfL('t_lim'), lim, _tfL('t_lim_sub'), '', "_tfOnly('k',['LIMITED'])", one('k', 'LIMITED')],
                [_tfL('t_disk'), lowDisk, _tfL('t_disk_sub'), 'crit', '_tfDisk()', S.q === '#disco'],
                [_tfL('t_bkp'), bkp, _tfP(_tfL('t_bkp_sub'), { h: lateH }), 'warn', "_tfOnly('ba',['LATE','NEVER'])", S.ba.size === 2 && S.ba.has('LATE') && S.ba.has('NEVER')],
            ];
            h += '<div class="tf-tiles">' + tiles.map(([l, v, sub, cls, fn, on]) => `<${fn ? 'button type="button"' : 'div'} class="tf-tile ${cls}${on ? ' on' : ''}"${fn ? ` onclick="${fn}"` : ''}><div class="tf-eyebrow">${l}</div><div class="v">${v}</div><div class="l">${sub}</div></${fn ? 'button' : 'div'}>`).join('') + '</div>';
            // graficos (canvas; montados depois do innerHTML)
            const card = (cls, id, title, hint, height) => `<div class="tf-card ${cls}"><h4>${title}</h4><div class="hint">${hint}</div><div class="tf-ch" style="height:${height}px;"><canvas id="tf-${id}-${tabId}"></canvas></div></div>`;
            const nDisk = Math.min(20, (data.disks || []).length);
            h += '<div class="tf-grid">' + card('tf-c4', 'env', _tfL('c_env'), _tfL('c_env_h'), 200) + card('tf-c4', 'kind', _tfL('c_kind'), _tfL('c_kind_h'), 200)
               + card('tf-c4', 'rec', _tfL('c_rec'), _tfP(_tfL('c_rec_h'), { h: lateH }), 200) + card('tf-c6', 'risk', _tfL('c_risk'), _tfL('c_risk_h'), 300)
               + card('tf-c6', 'disk', _tfL('c_disk'), _tfL('c_disk_h'), Math.max(200, nDisk * 22 + 40)) + '</div>';
            // tabela
            const { k: sk, desc } = S.sort;
            const sorted = [...rows].sort((x, y) => { let p = x[sk], q2 = y[sk]; if (p == null) p = desc ? -Infinity : Infinity; if (q2 == null) q2 = desc ? -Infinity : Infinity;
                if (typeof p === 'string' || typeof q2 === 'string') return desc ? String(q2).localeCompare(String(p)) : String(p).localeCompare(String(q2)); return desc ? q2 - p : p - q2; });
            const th = (k, l, num) => `<th class="${num ? 'num ' : ''}${sk === k ? 's' + (desc ? ' desc' : '') : ''}" onclick="_tfSort('${k}')">${l}</th>`;
            h += `<div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:6px;"><h4 style="font-size:13px;margin:0;color:var(--color-text-bright);">${_tfL('tbl')}</h4><span class="hint" style="font-size:12px;color:var(--color-text-tertiary);">${_tfL('tbl_h')}</span></div>`;
            h += '<div class="tf-tablewrap"><table class="tf-table"><thead><tr>' + th('i', _tfL('h_inst')) + th('d', _tfL('h_db')) + th('e', _tfL('h_env')) + th('r', _tfL('rec')) + th('k', _tfL('kind'))
               + th('u', _tfL('h_used'), 1) + th('c', _tfL('h_cur'), 1) + th('p', _tfL('h_p'), 1) + th('t', _tfL('h_t'), 1) + th('pe', _tfL('h_pe'), 1) + th('s', _tfL('sev')) + th('rs', _tfL('h_rs'))
               + th('g', _tfL('h_g'), 1) + th('dr', 'Drive') + th('vf', _tfL('h_vf'), 1) + th('vp', _tfL('h_vp'), 1) + th('lb', _tfL('h_lb')) + th('ba', _tfL('ba')) + th('nf', _tfL('h_nf'), 1) + '</tr></thead><tbody>';
            sorted.slice(0, S.limit).forEach(r => {
                const bc = r.pe > 95 ? 'c' : r.pe > 85 ? 'w' : '';
                h += `<tr class="${S.d === r.d && S.i === r.i ? 'sel' : ''}" onclick="_tfInst('${a(r.i)}')">`
                   + `<td onclick="event.stopPropagation();_fleetSwitchTo('${a(r.i)}','tlog')" title="${esc(r.i)}">${esc(r.i)}</td><td class="db" title="${esc(r.d)}">${esc(r.d)}</td>`
                   + `<td><span class="tf-pill ${esc(r.e)}">${esc(r.e)}</span></td><td>${esc(r.r)}</td>`
                   + `<td>${r.k === 'UNLIMITED' ? `<span class="tf-inf">${_tfL('unl')}</span>` : r.k === 'LIMITED' ? _tfL('lim') : esc(String(r.k).toLowerCase())}</td>`
                   + `<td class="num">${_tfFmt(r.u)}</td><td class="num">${_tfFmt(r.c)}</td><td class="num">${_tfFmt1(r.p)}%</td>`
                   + `<td class="num">${r.t ? _tfFmt(r.t) : '<span class="tf-inf">∞</span>'}</td>`
                   + `<td class="num"><span class="tf-bar ${bc}"><b style="width:${Math.min(r.pe || 0, 100)}%"></b></span>${_tfFmt1(r.pe)}%</td>`
                   + `<td><span class="tf-pill ${esc(r.s)}">${esc(String(r.s).toLowerCase())}</span></td><td class="tf-inf">${esc(r.rs || '')}</td>`
                   + `<td class="num">${r.g ? _tfFmt(r.g) : '<span class="tf-inf">0</span>'}</td><td>${r.dr ? esc(r.dr) : '<span class="tf-inf">?</span>'}</td>`
                   + `<td class="num">${_tfFmt(r.vf)}</td><td class="num">${r.vp != null ? _tfFmt1(r.vp) + '%' : '—'}</td>`
                   + `<td style="font-family:var(--font-mono);">${r.lb ? esc(String(r.lb).slice(0, 16).replace('T', ' ')) : '<span class="tf-inf">—</span>'}</td>`
                   + `<td><span class="tf-pill ${esc(r.ba)}">${esc(r.ba)}</span></td><td class="num">${r.nf || '<span class="tf-inf">0</span>'}</td></tr>`;
            });
            h += '</tbody></table>';
            h += `<div class="tf-more">${sorted.length > S.limit ? `<button type="button" class="tf-btn" onclick="_tfMore()">${_tfP(_tfL('more'), { n: sorted.length - S.limit })}</button>` : `<span class="tf-count">${_tfP(_tfL('rows'), { n: sorted.length })}</span>`}</div></div></div>`;
            setTimeout(() => _tfMount(tabId, data, rows), 0);
            return h;
        }
        function _tfMount(tabId, data, rows) {
            const root = document.getElementById('tf-root-' + tabId);
            if (!root) return;
            if (_tfS.focusQ) { const q = root.querySelector('.tf-q'); if (q) { q.focus(); try { q.setSelectionRange(q.value.length, q.value.length); } catch (e) {} } _tfS.focusQ = false; }
            _tfEnsureChart().then(ok => {
                if (!ok || !window.Chart || !document.getElementById('tf-root-' + tabId)) { root.querySelectorAll('.tf-ch').forEach(c => { c.innerHTML = `<div class="tf-inf" style="padding:20px;text-align:center;">${_tfL('nochart')}</div>`; }); return; }
                try { _tfCharts(tabId, data, rows); } catch (e) { console.warn('[tf] charts', e); }
            });
        }
        function _tfCharts(tabId, data, rows) {
            const css = _tfCss, S = _tfS, all = data.rows || [];
            const ink = css('--color-text-primary'), ink2 = css('--color-text-secondary'), ink3 = css('--color-text-tertiary'), grid = css('--color-border'), surface = css('--color-bg-panel');
            Chart.defaults.font.family = getComputedStyle(document.body).fontFamily; Chart.defaults.font.size = 12;
            const base = extra => Object.assign({ responsive: true, maintainAspectRatio: false, animation: false,
                plugins: { legend: { display: false }, tooltip: { backgroundColor: css('--color-bg-elevated'), titleColor: css('--color-text-bright'), bodyColor: ink, borderColor: grid, borderWidth: 1, padding: 8, displayColors: false } },
                scales: { x: { grid: { color: grid }, ticks: { color: ink2 }, border: { display: false } }, y: { grid: { color: grid }, ticks: { color: ink2 }, border: { display: false } } } }, extra);
            const mk = (id, cfg) => { const cv = document.getElementById('tf-' + id + '-' + tabId); if (!cv) return null; const old = Chart.getChart(cv); if (old) old.destroy(); return new Chart(cv, cfg); };
            const hit = (ch, evt) => { const p = ch.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true); return p.length ? p[0] : null; };
            // ambiente
            const envs = ['PRD', 'QLT', 'TST', 'Undefined'].filter(v => all.some(r => r.e === v));
            const envChart = mk('env', { type: 'bar', data: { labels: envs, datasets: [{ data: envs.map(v => rows.filter(r => r.e === v).reduce((x, r) => x + r.u, 0)), backgroundColor: envs.map(v => css(_TF_ENV_C[v])), borderRadius: 3, barPercentage: .7 }] },
                options: base({ scales: { y: { grid: { color: grid }, ticks: { color: ink2, callback: v => _tfGb(v) }, border: { display: false } }, x: { grid: { display: false }, ticks: { color: ink }, border: { display: false } } },
                    plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${_tfGb(c.raw)} ${_tfL('used_w')} · ${rows.filter(r => r.e === envs[c.dataIndex]).length} ${_tfL('bases_w')}` } } },
                    onClick: (e) => { const p = hit(envChart, e); if (p) _tfToggle('e', envs[p.index]); } }) });
            // tipo de max_size
            const kinds = ['UNLIMITED', 'LIMITED', 'FIXED', 'LEGACY'].filter(v => all.some(r => r.k === v));
            const kindChart = mk('kind', { type: 'doughnut', data: { labels: kinds, datasets: [{ data: kinds.map(v => rows.filter(r => r.k === v).length), backgroundColor: kinds.map(v => css(_TF_KIND_C[v])), borderColor: surface, borderWidth: 2, hoverOffset: 6 }] },
                options: { responsive: true, maintainAspectRatio: false, animation: false, cutout: '58%',
                    plugins: { legend: { position: 'right', labels: { color: ink2, boxWidth: 10, usePointStyle: true, generateLabels: ch => ch.data.labels.map((l, i) => ({ text: `${l} (${ch.data.datasets[0].data[i]})`, fillStyle: ch.data.datasets[0].backgroundColor[i], strokeStyle: 'transparent', pointStyle: 'circle', fontColor: ink2, index: i })) } },
                        tooltip: { backgroundColor: css('--color-bg-elevated'), titleColor: css('--color-text-bright'), bodyColor: ink, borderColor: grid, borderWidth: 1, callbacks: { label: c => { const rs = rows.filter(r => r.k === kinds[c.dataIndex]); return `${rs.length} ${_tfL('bases_w')} · ${_tfGb(rs.reduce((x, r) => x + r.u, 0))} ${_tfL('used_w')}`; } } } },
                    onClick: (e) => { const p = hit(kindChart, e); if (p) _tfToggle('k', kinds[p.index]); } } });
            // recovery x backup
            const recs = [...new Set(all.map(r => r.r))].sort(), bas = ['OK', 'LATE', 'NEVER', 'SIMPLE', 'UNKNOWN'].filter(v => all.some(r => r.ba === v));
            const recChart = mk('rec', { type: 'bar', data: { labels: recs, datasets: bas.map(b => ({ label: b, data: recs.map(rc => rows.filter(r => r.r === rc && r.ba === b).length), backgroundColor: css(_TF_BA_C[b]), borderRadius: 2, barPercentage: .6 })) },
                options: base({ scales: { x: { stacked: true, grid: { display: false }, ticks: { color: ink }, border: { display: false } }, y: { stacked: true, grid: { color: grid }, ticks: { color: ink2, precision: 0 }, border: { display: false } } },
                    plugins: { legend: { display: true, position: 'bottom', labels: { color: ink2, boxWidth: 10, usePointStyle: true } }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c.raw} ${_tfL('bases_w')}` } } },
                    onClick: (e) => { const p = hit(recChart, e); if (p) { const b = bas[p.datasetIndex], rc = recs[p.index]; if (S.ba.has(b) && S.r.has(rc)) { S.ba.delete(b); S.r.delete(rc); } else { S.ba = new Set([b]); S.r = new Set([rc]); } _tfRerender(); } } }) });
            // risco
            const pts = rows.map(r => ({ x: Math.max(r.vf || 1, 1), y: r.pe, r: r }));
            const riskChart = mk('risk', { type: 'scatter', data: { datasets: [{ data: pts, pointRadius: pts.map(p => p.r.u > 10000 ? 7 : p.r.u > 1000 ? 5 : 3.5), pointHoverRadius: 9, backgroundColor: pts.map(p => css(_TF_SEV_C[p.r.s]) + 'CC'), borderColor: surface, borderWidth: 1 }] },
                options: base({ scales: { x: { type: 'logarithmic', title: { display: true, text: _tfL('ax_free'), color: ink3 }, grid: { color: grid }, ticks: { color: ink2, callback: v => [1, 10, 100, 1000, 10000, 100000, 1000000].includes(v) ? _tfGb(v) : '' }, border: { display: false } },
                        y: { min: 0, max: 105, title: { display: true, text: _tfL('ax_cap'), color: ink3 }, grid: { color: grid }, ticks: { color: ink2, callback: v => v + '%' }, border: { display: false } } },
                    plugins: { legend: { display: false }, tooltip: { callbacks: { title: c => c[0].raw.r.d + ' · ' + c[0].raw.r.i, label: c => { const r = c.raw.r; return [`${_tfFmt1(r.pe)}% · ${_tfGb(r.u)} / ${_tfGb(r.c)}`, `${r.k}${r.t ? ' max ' + _tfGb(r.t) : ''} · ${_tfL('free_w')} ${r.vf ? _tfGb(r.vf) : '?'} (${r.dr || '?'})`]; } } } },
                    onClick: (e) => { const p = hit(riskChart, e); if (p) { const r = pts[p.index].r; _tfDb(r.i, r.d); } } }) });
            // volumes
            const instSet = new Set(rows.map(r => r.i)), logDrives = new Set(rows.map(r => r.i + '|' + String(r.dr || '').toUpperCase()));
            const dks = (data.disks || []).filter(x => instSet.has(x.i) && (logDrives.has(x.i + '|' + String(x.dr).toUpperCase()) || rows.some(r => r.i === x.i && r.vf != null && x.f != null && Math.abs(r.vf - x.f) < 1))).sort((p, q) => (p.f || 0) - (q.f || 0)).slice(0, 20);
            const short = d => { const p = String(d).split('\\').filter(Boolean); return p.length > 1 ? p[0] + '\\…\\' + p[p.length - 1] : String(d); };
            const diskChart = mk('disk', { type: 'bar', data: { labels: dks.map(x => short(x.dr) + '  ·  ' + x.i), datasets: [{ data: dks.map(x => x.f), backgroundColor: dks.map(x => x.pf < 10 ? css('--sev-critical-text') : x.pf < 20 ? css('--sev-warning-text') : css('--sev-ok-text')), borderRadius: 3, barPercentage: .8, categoryPercentage: .85 }] },
                options: base({ indexAxis: 'y', scales: { x: { grid: { color: grid }, title: { display: true, text: _tfL('ax_free_vol'), color: ink3 }, ticks: { color: ink2, callback: v => _tfGb(v) }, border: { display: false } }, y: { grid: { display: false }, ticks: { color: ink, autoSkip: false, font: { family: css('--font-mono'), size: 12 } }, border: { display: false } } },
                    plugins: { legend: { display: false }, tooltip: { callbacks: { title: c => dks[c[0].dataIndex].dr + '  ·  ' + dks[c[0].dataIndex].i, label: c => { const x = dks[c.dataIndex]; return `${_tfL('free_w')} ${_tfGb(x.f)} / ${_tfGb(x.t)} (${_tfFmt1(x.pf)}%) · ${rows.filter(r => r.i === x.i && String(r.dr || '').toUpperCase() === String(x.dr).toUpperCase()).length} ${_tfL('logs_here')}`; } } } },
                    onClick: (e) => { const p = hit(diskChart, e); if (p) _tfInst(dks[p.index].i); } }) });
        }
"""

RENDER_STG = r"""            } else if (program === 'tlog') {
                return _liveRenderTlogFleet(data, tabId);   // 2026-09-21 (owner): painel completo, como o relatorio T-Log da frota sem os 2 primeiros graficos
            } else if (program === 'memory') {
                const rows = (data.rows || []).slice(0, 80); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), _kpiT('live.col_status', 'Estado'), _kpiT('live.col_os_mem', 'Mem SO'), _kpiT('live.col_os_free', 'Livre SO'), 'PLE', _kpiT('live.col_max_memory', 'Max server memory'), _kpiT('live.col_recommended', 'Recomendado'), 'Buffer pool'], rows.map(m => {
                    const st = String(m.Status || 'OK').toUpperCase(), ms = String(m.Max_Memory_Status || 'OK').toUpperCase();
                    const s = st === 'CRITICAL' ? 'critical' : (st === 'WARNING' || ms !== 'OK') ? 'warning' : 'ok';
                    const ple = +m.PLE_Seconds || 0, livre = +m.Available_Memory_MB || 0;
                    return row(m.Instance, 'memory', `<td style="${cell}${sevC(s)}">${esc(st)}${ms !== 'OK' ? ' · max ' + esc(ms) : ''}</td>`
                        + `<td style="${cell}" data-sort-value="${+m.Memory_Usage_Pct || 0}">${(+m.Memory_Usage_Pct || 0).toFixed(0)}%</td>`
                        + `<td style="${cell}${sevC(livre < 512 ? 'critical' : livre < 1024 ? 'warning' : 'ok')}" data-sort-value="${livre}">${formatSizeMB(livre)}</td>`
                        + `<td style="${cell}${sevC(ple < 300 ? 'critical' : ple < 600 ? 'warning' : 'ok')}" data-sort-value="${ple}">${ple.toLocaleString()} s</td>`
                        + `<td style="${cell}" data-sort-value="${+m.Max_Server_Memory_MB || 0}">${formatSizeMB(+m.Max_Server_Memory_MB || 0)}</td>`
                        + `<td style="${cell}color:var(--color-text-tertiary);" data-sort-value="${+m.Recommended_Max_Memory_MB || 0}">${m.Recommended_Max_Memory_MB ? formatSizeMB(+m.Recommended_Max_Memory_MB) : '-'}</td>`
                        + `<td style="${cell}color:var(--color-text-tertiary);" data-sort-value="${+m.Buffer_Pool_MB || 0}">${m.Buffer_Pool_MB ? formatSizeMB(+m.Buffer_Pool_MB) : '-'}</td>`);
                })) : vazio();
            } else if (program === 'jobs') {
                const rows = (data.rows || []).slice(0, 80); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), 'Job', _kpiT('live.col_status', 'Estado'), _kpiT('live.col_last_run', 'Última execução'), _kpiT('live.col_duration', 'Duração'), _kpiT('live.col_next_run', 'Próxima'), _kpiT('live.col_category', 'Categoria')], rows.map(j => row(j.Instance, 'jobs',
                    `<td style="${cell}max-width:320px;overflow:hidden;text-overflow:ellipsis;" title="${esc(j.JobName)}">${esc(j.JobName)}</td>`
                    + `<td style="${cell}${sevC(String(j.LastRunStatus) === 'Failed' ? 'critical' : 'warning')}">${esc(j.LastRunStatus)}</td>`
                    + `<td style="${cell}color:var(--color-text-tertiary);">${esc(String(j.LastRunDate || '').replace('T', ' ').substring(0, 16))}</td>`
                    + `<td style="${cell}" data-sort-value="${+j.LastRunDurationSec || 0}">${fmtDur(j.LastRunDurationSec)}</td>`
                    + `<td style="${cell}color:var(--color-text-tertiary);">${esc(String(j.NextRunDate || '').replace('T', ' ').substring(0, 16)) || '-'}</td>`
                    + `<td style="${cell}color:var(--color-text-tertiary);">${esc(j.Category || '')}</td>`, j.Instance + ' · ' + j.JobName))) : vazio();
            } else if (program === 'schedulers') {
                const rows = (data.rows || []).slice(0, 80); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), _kpiT('live.col_status', 'Estado'), 'Workers', _kpiT('live.col_usage', 'Uso'), 'Running', 'Runnable máx', 'I/O pendente', _kpiT('live.col_work_queue', 'Fila')], rows.map(s => {
                    const st = String(s.Status || 'OK').toUpperCase(), uso = +s.Worker_Usage_Pct || 0, run = +s.Max_Runnable_Tasks || 0;
                    const sv = st === 'CRITICAL' || uso > 80 ? 'critical' : (st !== 'OK' || uso > 50 || run > 0) ? 'warning' : 'ok';
                    return row(s.Instance, 'schedulers', `<td style="${cell}${sevC(sv)}">${esc(st)}</td>`
                        + `<td style="${cell}" data-sort-value="${+s.Current_Workers || 0}">${esc(s.Current_Workers)} / ${esc(s.Max_Workers)}</td>`
                        + `<td style="${cell}${sevC(uso > 80 ? 'critical' : uso > 50 ? 'warning' : 'ok')}" data-sort-value="${uso}">${uso.toFixed(0)}%</td>`
                        + `<td style="${cell}">${esc(s.Running_Workers)}</td>`
                        + `<td style="${cell}${sevC(run > 0 ? 'warning' : 'ok')}" data-sort-value="${run}">${run}</td>`
                        + `<td style="${cell}${sevC((+s.Total_Pending_IO || 0) > 0 ? 'warning' : 'ok')}" data-sort-value="${+s.Total_Pending_IO || 0}">${+s.Total_Pending_IO || 0}</td>`
                        + `<td style="${cell}color:var(--color-text-tertiary);">${(+s.Avg_Work_Queue || 0).toFixed(1)}</td>`);
                })) : vazio();
            } else if (program === 'io') {
                const rows = (data.rows || []).slice(0, 80); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), _kpiT('live.col_database', 'Base'), _kpiT('live.col_file', 'Ficheiro'), _kpiT('live.col_kind', 'Tipo'), _kpiT('live.col_read_ms', 'Leitura'), _kpiT('live.col_write_ms', 'Escrita'), _kpiT('live.col_status', 'Estado')], rows.map(f => {
                    const st = String(f.Status || 'OK').toUpperCase(), sv = st === 'CRITICAL' ? 'critical' : st === 'WARNING' ? 'warning' : 'ok';
                    return row(f.Instance, 'io', `<td style="${cell}">${esc(f.Database_Name)}</td><td style="${cell}max-width:220px;overflow:hidden;text-overflow:ellipsis;color:var(--color-text-tertiary);" title="${esc(f.File_Name)}">${esc(f.File_Name)}</td>`
                        + `<td style="${cell}color:var(--color-text-tertiary);">${esc(f.File_Type || '')}</td>`
                        + `<td style="${cell}${sevC((+f.Read_Latency_Ms || 0) > 50 ? 'critical' : (+f.Read_Latency_Ms || 0) > 20 ? 'warning' : 'ok')}" data-sort-value="${+f.Read_Latency_Ms || 0}">${(+f.Read_Latency_Ms || 0).toFixed(1)} ms</td>`
                        + `<td style="${cell}${sevC((+f.Write_Latency_Ms || 0) > 50 ? 'critical' : (+f.Write_Latency_Ms || 0) > 20 ? 'warning' : 'ok')}" data-sort-value="${+f.Write_Latency_Ms || 0}">${(+f.Write_Latency_Ms || 0).toFixed(1)} ms</td>`
                        + `<td style="${cell}${sevC(sv)}">${esc(st)}</td>`, f.Instance + ' · ' + f.Database_Name + ' · ' + f.File_Name);
                })) : vazio();
            } else if (program === 'space') {"""

EDITS_PORTAL = [
    ("""        .toast-notification {""", CSS_TF, 1),
    ("""        const _LIVE_FLEET_THEME = { queries: 1, blocking: 1, tempdb: 1, waits: 1, alwayson: 1, connections: 1, errorlog: 1, space: 1 };""",
     """        const _LIVE_FLEET_THEME = { queries: 1, blocking: 1, tempdb: 1, waits: 1, alwayson: 1, connections: 1, errorlog: 1, space: 1, tlog: 1, memory: 1, jobs: 1, schedulers: 1, io: 1 };
        const _LIVE_FLEET_THEME_STG = { tlog: 1, memory: 1, jobs: 1, schedulers: 1, io: 1 };   // 2026-09-21 lote 2: ultima coleta (staging), endpoint /fleet/theme/{program}""", 1),
    ("""        window._liveFleetMode = _liveFleetMode;""",
     """        window._liveFleetMode = _liveFleetMode;""" + TF_JS.rstrip("\n"), 1),
    ("""                const progUrl = isFleet
                    ? '/api/v1/live/fleet/dashboard'
                    : '/api/v1/live/' + encodeURIComponent(_liveInstance) + '/' + _liveProgram;""",
     """                const progUrl = isFleet
                    ? (_liveProgram !== 'fleet' && _LIVE_FLEET_THEME_STG[_liveProgram] ? '/api/v1/live/fleet/theme/' + _liveProgram : '/api/v1/live/fleet/dashboard')   // 2026-09-21 lote 2
                    : '/api/v1/live/' + encodeURIComponent(_liveInstance) + '/' + _liveProgram;""", 1),
    ("""                    _liveLastData[_liveProgram] = pd;
                    _liveRenderAndSet(screen, _liveProgram, pd, tabId);""",
     """                    // 2026-09-21 lote 2: payload da staging sem coleta nova -> nao re-renderizar (o utilizador pode estar a filtrar)
                    const _prev = _liveLastData[_liveProgram];
                    if (pd && pd.fleet_theme && _prev && _prev.fleet_theme === pd.fleet_theme && String(_prev.collected_at) === String(pd.collected_at) && screen.querySelector('[data-fleet-theme="' + pd.fleet_theme + '"]')) {
                        if (status) { status.textContent = new Date().toLocaleTimeString('pt-PT', {hour:'2-digit',minute:'2-digit',second:'2-digit'}); status.style.color = 'var(--color-text-tertiary)'; }
                        return;
                    }
                    _liveLastData[_liveProgram] = pd;
                    _liveRenderAndSet(screen, _liveProgram, pd, tabId);""", 1),
    ("""            if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && data.instances) return _liveRenderFleetTheme(program, data, tabId);   // 2026-09-21""",
     """            if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && (data.instances || data.fleet_theme)) return _liveRenderFleetTheme(program, data, tabId);   // 2026-09-21 (+ lote 2: payload da staging)""", 1),
    ("""            const instances = data.instances || [];
            const drilled = new Set(""",
     """            const instances = data.instances || [];
            const stg = !!data.fleet_theme;   // 2026-09-21 lote 2: ultima coleta da staging, nao e' ao vivo
            const coleta = stg && data.collected_at ? String(data.collected_at).replace('T', ' ').substring(11, 16) : '';
            const drilled = new Set(""", 1),
    ("""            h += `<div style="font-size:12px;color:var(--color-text-tertiary);">${_kpiTp('live.fleet_theme_sub', '{n} linhas · {d} instâncias com drill neste ciclo · {t} na frota', { n: n, d: drilled.size, t: instances.length })}</div>`;""",
     """            h += `<div style="font-size:12px;color:var(--color-text-tertiary);">${stg ? _kpiTp('live.fleet_theme_sub_stg', '{n} linhas · última coleta {ts} · {t} instâncias na coleta', { n: n, ts: coleta || '?', t: data.total_instances || 0 }) : _kpiTp('live.fleet_theme_sub', '{n} linhas · {d} instâncias com drill neste ciclo · {t} na frota', { n: n, d: drilled.size, t: instances.length })}</div>`;""", 1),
    ("""${_kpiT('live.fleet_theme_note', 'Sem canal selecionado: só as instâncias onde há problema agora (o mesmo drill do Fleet). Clique numa linha para abrir a instância neste programa; escolha um canal para ver tudo.')}</div>`;""",
     """${stg ? _kpiT('live.fleet_theme_note_stg', 'Sem canal selecionado: última coleta do coletor, não é ao vivo. Só o que está fora do normal. Clique numa linha para abrir a instância neste programa ao vivo.') : _kpiT('live.fleet_theme_note', 'Sem canal selecionado: só as instâncias onde há problema agora (o mesmo drill do Fleet). Clique numa linha para abrir a instância neste programa; escolha um canal para ver tudo.')}</div>`;""", 1),
    ("""            } else if (program === 'space') {""", RENDER_STG, 1),
    # marca do render de frota por tema: a guarda de coleta so' salta o render quando o ecra JA' mostra este tema
    ("""            let h = '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px;">';""",
     """            let h = '<div data-fleet-theme="' + program + '" style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px;">';""", 1),
]

KEYS = {
    "pt": {"fleet_theme_sub_stg": "{n} linhas · última coleta {ts} · {t} instâncias na coleta",
           "fleet_theme_note_stg": "Sem canal selecionado: última coleta do coletor, não é ao vivo. Só o que está fora do normal. Clique numa linha para abrir a instância neste programa ao vivo."},
    "en": {"fleet_theme_sub_stg": "{n} rows · last collection {ts} · {t} instances collected",
           "fleet_theme_note_stg": "No channel selected: last collector snapshot, not live. Only what is out of the ordinary. Click a row to open that instance in this program, live."},
    "es": {"fleet_theme_sub_stg": "{n} filas · última recolección {ts} · {t} instancias recolectadas",
           "fleet_theme_note_stg": "Sin canal seleccionado: última recolección del colector, no es en vivo. Solo lo que está fuera de lo normal. Haga clic en una fila para abrir la instancia en este programa en vivo."},
}

TESTES = {T_TEMA: [
    ("""TEMAS = ("queries", "blocking", "tempdb", "waits", "alwayson", "connections", "errorlog", "space")""",
     """TEMAS = ("queries", "blocking", "tempdb", "waits", "alwayson", "connections", "errorlog", "space",
         "tlog", "memory", "jobs", "schedulers", "io")   # 2026-09-21 lote 2: os 5 ultimos vem da staging""", 1),
    ("""    assert "if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && data.instances) return _liveRenderFleetTheme(program, data, tabId);" in LIVE""",
     """    assert "if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && (data.instances || data.fleet_theme)) return _liveRenderFleetTheme(program, data, tabId);" in LIVE   # lote 2: payload da staging""", 1),
]}

TESTE_NOVO = '''# -*- coding: utf-8 -*-
"""
2026-09-21 (owner, lote 2): TLog/Memory/Jobs/Sched/IO sem canal vem da staging por GET /api/v1/live/fleet/theme/{program};
o TLog e' o painel do relatorio "T-Log da Frota" sem os 2 primeiros graficos (Chart.js vendorizado, on-demand).
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routers import live_monitoring as lm

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LIVE = PORTAL[PORTAL.index("const _liveLastData = {};"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
TF = LIVE[LIVE.index("function _liveRenderTlogFleet"):LIVE.index("const _LIVE_HELP_PROGS")]


def _body(resp):
    return json.loads(bytes(resp.body).decode("utf-8"))


def _th_fake(k, lvl):
    return {("tlog_usage", "warning"): 85, ("tlog_usage", "critical"): 95, ("filegroup_unlimited_free_gb", "warning"): 10,
            ("filegroup_unlimited_free_gb", "critical"): 5, ("backup_delay_log", "warning"): 24}[(k, lvl)]


def test_programa_desconhecido_e_404_sem_tocar_na_bd(monkeypatch):
    monkeypatch.setattr(lm, "execute_intelligence_query", lambda *a, **k: pytest.fail("nao devia consultar"))
    with pytest.raises(HTTPException) as e:
        asyncio.run(lm.get_fleet_theme("plancache"))
    assert e.value.status_code == 404


def test_jobs_le_agent_jobs_falhados_e_devolve_payload_da_frota(monkeypatch):
    vistos = []
    def fake(sql, *a, **k):
        vistos.append(sql)
        if "COUNT(DISTINCT Instance)" in sql:
            return [{"n": 61}]
        return [{"Instance": "SRV_I01", "JobName": "Backup FULL", "LastRunStatus": "Failed", "LastRunDate": "2026-09-21T03:00:00",
                 "LastRunDurationSec": 42, "NextRunDate": None, "Category": "Backup", "IsEnabled": True, "HasSchedule": True, "Update_TS": "2026-09-21T17:04:00"}]
    monkeypatch.setattr(lm, "execute_intelligence_query", fake)
    b = _body(asyncio.run(lm.get_fleet_theme("jobs")))
    assert b["fleet_theme"] == "jobs" and b["count"] == 1 and b["total_instances"] == 61 and b["collected_at"].startswith("2026-09-21T17:04")
    assert b["rows"][0]["JobName"] == "Backup FULL"
    q = " ".join(vistos).upper()
    assert "KPI_MSSQL_AGENT_JOBS_STG" in q and "'FAILED'" in q and "ISENABLED = 1" in q
    assert all(not s.strip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE")) for s in vistos)


def test_tlog_devolve_todas_as_bases_com_regra_do_kpi_volumes_e_ficheiros(monkeypatch):
    now = datetime.now()
    base = [{"Instance": "A", "Database": "cheia", "Env": "PRD", "Percent_Used": 99.0, "Used_MB": 990.0, "Current_MB": 1000, "Max_Available_MB": 1050,
             "Update_TS": now, "Recovery_Model": "FULL", "Last_Log_Backup_Date": (now - timedelta(hours=30)).isoformat(),   # a helper devolve datas em ISO
             "Log_Kind": "LIMITED", "Ceiling_MB": 1050, "Drive": "L:", "Volume_Free_MB": 51200, "Next_Growth_MB": 64},
            {"Instance": "A", "Database": "folgada", "Env": "PRD", "Percent_Used": 40.0, "Used_MB": 400.0, "Current_MB": 1000, "Max_Available_MB": 2097152,
             "Update_TS": now, "Recovery_Model": "SIMPLE", "Last_Log_Backup_Date": None, "Log_Kind": "UNLIMITED", "Ceiling_MB": 2097152, "Drive": "L:", "Volume_Free_MB": 51200, "Next_Growth_MB": 64}]
    def fake(sql, *a, **k):
        u = sql.upper()
        if "TLOG_USAGE" in u:
            return base
        if "DISK_USAGE" in u:
            return [{"Instance": "A", "Drive": "L:\\\\LOGS\\\\", "Total_MB": 102400, "Free_MB": 51200, "Percent_Free": 50.0}, {"Instance": "B", "Drive": "C:\\\\", "Total_MB": 1, "Free_MB": 1, "Percent_Free": 100}]
        if "DATAFILES" in u:
            return [{"Instance": "A", "Database": "cheia", "n": 2}]
        return []
    monkeypatch.setattr(lm, "execute_intelligence_query", fake)
    import api.routers.intelligence.helpers as H
    monkeypatch.setattr(H, "_th", _th_fake)
    b = _body(asyncio.run(lm.get_fleet_theme("tlog")))
    assert b["total_instances"] == 1 and b["count"] == 2 and b["late_h"] == 24 and b["warning"] == 1 and b["critical"] == 0
    rows = {r["d"]: r for r in b["rows"]}
    c = rows["cheia"]
    assert c["k"] == "LIMITED" and c["s"] == "WARNING" and c["rs"] == "TECTO" and c["pe"] == pytest.approx(94.29, abs=0.01) and c["t"] == 1050
    assert c["ba"] == "LATE" and c["dr"] == "L:\\\\LOGS\\\\" and c["vt"] == 102400 and c["vp"] == 50.0 and c["nf"] == 2 and c["e"] == "PRD"
    f = rows["folgada"]
    assert f["s"] == "OK" and f["t"] is None and f["ba"] == "SIMPLE" and f["nf"] == 0 and f["pe"] == pytest.approx(400 * 100 / 52200, abs=0.01)
    assert [d["i"] for d in b["disks"]] == ["A"]   # so' os volumes das instancias com T-Log


def test_portal_usa_o_endpoint_e_o_payload_da_staging():
    assert "const _LIVE_FLEET_THEME_STG = { tlog: 1, memory: 1, jobs: 1, schedulers: 1, io: 1 };" in LIVE
    assert "'/api/v1/live/fleet/theme/' + _liveProgram" in LIVE
    assert "data && (data.instances || data.fleet_theme)" in LIVE
    # coleta igual -> nao re-renderiza (o utilizador pode estar a filtrar)
    assert "String(_prev.collected_at) === String(pd.collected_at) && screen.querySelector('[data-fleet-theme=\\"' + pd.fleet_theme + '\\"]')" in LIVE
    assert 'data-fleet-theme="tlog"' in TF and "'<div data-fleet-theme=\\"' + program + '\\" style=\\"display:flex;align-items:baseline" in LIVE
    r = LIVE[LIVE.index("function _liveRenderFleetTheme"):LIVE.index("window._liveFleetMode = _liveFleetMode;")]
    for tema in ("memory", "jobs", "schedulers", "io"):
        assert f"program === '{tema}'" in r
    assert "return _liveRenderTlogFleet(data, tabId);" in r
    assert "_kpiT('live.fleet_theme_note_stg'" in r and "_kpiTp('live.fleet_theme_sub_stg'" in r
    assert "plancache" not in r   # Plan Cache continua neutro (sem staging)
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static/i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        assert "fleet_theme_sub_stg" in d and "fleet_theme_note_stg" in d and "{ts}" in d["fleet_theme_sub_stg"]


def test_painel_tlog_da_frota_sem_os_dois_primeiros_graficos():
    # os 5 graficos que ficam + a tabela; nunca "top bases" nem "instancias por consumo"
    for cid in ("env", "kind", "rec", "risk", "disk"):
        assert f"card('tf-c" in TF and f"'{cid}'" in TF
    assert "'top'" not in TF and "'inst'" not in TF
    assert "class=\\"tf-table\\"" in TF and "_tfSort(" in TF and "_tfMore()" in TF
    # Chart.js vendorizado, carregado on-demand, nunca CDN; sem graficos a pagina continua (nochart)
    assert "s.src = '/static/vendor/chartjs/chart.min.js'" in LIVE and "cdn.jsdelivr" not in TF and "cdnjs" not in TF
    assert "Chart.getChart(cv)" in LIVE and "_tfL('nochart')" in LIVE
    # a instancia abre-se ao vivo; a linha filtra; o texto procura com debounce e mantem o foco
    assert "_fleetSwitchTo('${a(r.i)}','tlog')" in TF and "onclick=\\"_tfInst('${a(r.i)}')\\"" in TF
    assert "_tfS.focusQ = true" in LIVE and "q.setSelectionRange(q.value.length, q.value.length)" in LIVE
    # tipografia LIVE (>= 12px) e sem stack mono cru
    assert not re.search(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", TF) and "monospace" not in TF
    css = PORTAL[PORTAL.index(".tf-root {"):PORTAL.index(".toast-notification {")]
    assert not re.search(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", css) and "var(--font-mono)" in css
    assert "#" not in css.replace("\\\\25B4", "").replace("\\\\25BE", "")   # so' tokens, nenhuma cor fixa
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def _inserir_keys(texto, loc):
    eol = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.split(eol)
    idx = [i for i, l in enumerate(linhas) if l.strip().startswith('"help_io_next":')]
    if len(idx) != 1:
        raise SystemExit(f"[ABORT] {loc}.json: help_io_next nao encontrado 1x")
    ind = linhas[idx[0]][:len(linhas[idx[0]]) - len(linhas[idx[0]].lstrip())]
    novas = [f'{ind}"{k}": {json.dumps(v, ensure_ascii=False)},' for k, v in KEYS[loc].items()]
    novo = eol.join(linhas[:idx[0] + 1] + novas + linhas[idx[0] + 1:])
    antes, depois = json.loads(texto), json.loads(novo)
    extra = set(depois["live"]) - set(antes["live"])
    if extra != set(KEYS[loc]):
        raise SystemExit(f"[ABORT] {loc}.json: insercao inesperada {extra}")
    for k in extra:
        depois["live"].pop(k)
    if depois != antes:
        raise SystemExit(f"[ABORT] {loc}.json: o resto do JSON mudou")
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    portal_p, back_p = base / PORTAL, base / BACKEND
    portal = portal_p.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] portal ja aplicado"); return 1
    if "_liveRenderFleetTheme" not in portal:
        print("[ABORT] lote 1 (LIVE_FROTA_POR_TEMA) nao esta aplicado"); return 1
    novo_portal = _apply(portal, EDITS_PORTAL, "portal")
    novo_back = None
    if back_p.exists():
        back = back_p.read_bytes().decode("utf-8")
        if MARK in back:
            print("[ABORT] backend ja aplicado"); return 1
        novo_back = _apply(back, EDITS_BACKEND, "backend")
    novos_json = {}
    for loc in ("pt", "en", "es"):
        p = base / "static/i18n" / f"{loc}.json"
        if not p.exists():
            print(f"[skip] {p} ausente na copia"); continue
        t = p.read_bytes().decode("utf-8")
        if '"fleet_theme_sub_stg"' in t:
            print(f"[ABORT] {loc}.json ja tem fleet_theme_sub_stg"); return 1
        novos_json[p] = _inserir_keys(t, loc)
    testes = {rel: _apply((base / rel).read_bytes().decode("utf-8"), edits, str(rel)) for rel, edits in TESTES.items() if (base / rel).exists()}
    print(f"[ok] portal {len(EDITS_PORTAL)} blocos (CSS .tf-*, temas, painel T-Log, endpoint, guarda de coleta, despacho, 4 ramos); backend {'1 endpoint + painel tlog' if novo_back else 'ausente: saltado'}; locales {len(novos_json)} (2 chaves); testes {len(testes)} actualizado(s) + 1 novo")
    if check:
        print("--check OK. Nada escrito."); return 0
    portal_p.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    if novo_back is not None:
        back_p.write_bytes(novo_back.encode("utf-8")); print(f"[write] {BACKEND}")
    for rel, t in testes.items():
        (base / rel).write_bytes(t.encode("utf-8")); print(f"[write] {rel}")
    novo_p = base / T_NOVO
    novo_p.parent.mkdir(parents=True, exist_ok=True)
    novo_p.write_bytes(TESTE_NOVO.encode("utf-8")); print(f"[write] {T_NOVO}")
    for p, t in novos_json.items():
        p.write_bytes(t.encode("utf-8")); print(f"[write] {p.relative_to(base)}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > sem canal > TLog / Memory / Jobs / Sched / I/O.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
