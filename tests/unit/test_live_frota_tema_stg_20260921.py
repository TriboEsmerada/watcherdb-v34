# -*- coding: utf-8 -*-
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
            return [{"Instance": "A", "Drive": "L:\\LOGS\\", "Total_MB": 102400, "Free_MB": 51200, "Percent_Free": 50.0}, {"Instance": "B", "Drive": "C:\\", "Total_MB": 1, "Free_MB": 1, "Percent_Free": 100}]
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
    assert c["ba"] == "LATE" and c["dr"] == "L:\\LOGS\\" and c["vt"] == 102400 and c["vp"] == 50.0 and c["nf"] == 2 and c["e"] == "PRD"
    f = rows["folgada"]
    assert f["s"] == "OK" and f["t"] is None and f["ba"] == "SIMPLE" and f["nf"] == 0 and f["pe"] == pytest.approx(400 * 100 / 52200, abs=0.01)
    assert [d["i"] for d in b["disks"]] == ["A"]   # so' os volumes das instancias com T-Log


def test_portal_usa_o_endpoint_e_o_payload_da_staging():
    assert "const _LIVE_FLEET_THEME_STG = { tlog: 1, memory: 1, jobs: 1, schedulers: 1, io: 1 };" in LIVE
    assert "'/api/v1/live/fleet/theme/' + _liveProgram" in LIVE
    assert "data && (data.instances || data.fleet_theme)" in LIVE
    # coleta igual -> nao re-renderiza (o utilizador pode estar a filtrar)
    assert "String(_prev.collected_at) === String(pd.collected_at) && screen.querySelector('[data-fleet-theme=\"' + pd.fleet_theme + '\"]')" in LIVE
    assert 'data-fleet-theme="tlog"' in TF and "'<div data-fleet-theme=\"' + program + '\" style=\"display:flex;align-items:baseline" in LIVE
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
    assert "class=\"tf-table\"" in TF and "_tfSort(" in TF and "_tfMore()" in TF
    # Chart.js vendorizado, carregado on-demand, nunca CDN; sem graficos a pagina continua (nochart)
    assert "s.src = '/static/vendor/chartjs/chart.min.js'" in LIVE and "cdn.jsdelivr" not in TF and "cdnjs" not in TF
    assert "Chart.getChart(cv)" in LIVE and "_tfL('nochart')" in LIVE
    # a instancia abre-se ao vivo; a linha filtra; o texto procura com debounce e mantem o foco
    assert "_fleetSwitchTo('${a(r.i)}','tlog')" in TF and "onclick=\"_tfInst('${a(r.i)}')\"" in TF
    assert "_tfS.focusQ = true" in LIVE and "q.setSelectionRange(q.value.length, q.value.length)" in LIVE
    # tipografia LIVE (>= 12px) e sem stack mono cru
    assert not re.search(r"font-size:\s*(?:[0-9]|1[01])(?:\.\d+)?px", TF) and "monospace" not in TF
    css = PORTAL[PORTAL.index(".tf-root {"):PORTAL.index(".toast-notification {")]
    assert not re.search(r"font-size:\s*(?:[0-9]|1[01])(?:\.\d+)?px", css) and "var(--font-mono)" in css
    assert "#" not in css.replace("\\25B4", "").replace("\\25BE", "")   # so' tokens, nenhuma cor fixa
