"""
2026-09-11 -- LIVE F9: filtro, escala do dirty, DB do plan cache, idioma, persistencia.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "api" / "routers" / "live_monitoring.py").read_text(encoding="utf-8")
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
LIVE = PORTAL[PORTAL.index("let _liveInstance = null;"):PORTAL.index("function _liveRenderSchedulers")]

NEW_KEYS = ["selected_group", "adhoc_plan", "btn_reduce", "btn_normal", "btn_fullscreen", "play", "pause", "paused",
            "connecting", "program_error", "error_short", "program_not_implemented", "running_queries_count",
            "connections_count", "collecting_fleet", "buffer_pool_by_db", "plan_cache_empty", "error_log_empty",
            "gauge_cpu_tip", "gauge_mem_tip", "gauge_ple_tip", "gauge_batch_tip", "gauge_qry_tip"]


def test_plan_cache_dbid_falls_back_to_plan_attributes():
    sql = re.search(r'PLANCACHE_SQL = """(.*?)"""', ROUTER, re.S).group(1)
    assert "COALESCE(DB_NAME(qt.dbid), DB_NAME(CAST(pa.value AS INT)))" in sql
    assert "sys.dm_exec_plan_attributes(qs.plan_handle) WHERE attribute = 'dbid'" in sql


def test_filter_keeps_selected_instance_visible():
    assert "let _currentShown = false;" in LIVE
    assert "pinned.label = t('live.selected_group');" in LIVE
    assert "sel.insertBefore(pinned, sel.options[0].nextSibling);" in LIVE


def test_dirty_bar_uses_same_scale_as_buffer_bar():
    assert "const dirtyPct = ((b.dirty_mb || 0) / maxBuf * 100).toFixed(0);" in LIVE
    assert "b.dirty_mb / b.buffer_mb" not in LIVE


def test_plan_cache_shows_adhoc_label():
    assert "${q.database_name || t('live.adhoc_plan')}" in LIVE


def test_no_raw_portuguese_literals_left_in_live_block():
    for lit in ("'PAUSADO'", "queries em execucao", "} conexoes<", "'A conectar a '", "Programa nao implementado",
                'title="Reduzir"', 'title="Tamanho normal"', 'title="Tela inteira"', "A colectar dados da fleet",
                "Buffer Pool por Database", ">Plan cache vazio<", "'&#9654; Play'", ">Error log vazio<",
                'title="CPU do SQL Server', 'title="Memoria OS', 'title="Queries em execucao"'):
        assert lit not in LIVE, lit
    assert "_liveProgram = _savedProg;" in LIVE  # restauro sincrono antes do fetch dos canais


def test_program_and_rate_persist():
    assert "localStorage.setItem('live-last-program', program)" in LIVE
    assert "localStorage.setItem('live-last-rate', String(_liveRefreshRate))" in LIVE
    assert "setTimeout(() => liveSetProgram(tabId, _savedProg), 100);" in LIVE
    assert "setTimeout(() => liveSetProgram(tabId, 'fleet'), 100);" not in LIVE


def test_new_keys_in_three_locales_with_placeholders():
    for loc in ("pt", "en", "es"):
        live = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for k in NEW_KEYS:
            assert k in live and live[k], (loc, k)
        assert "{instance}" in live["connecting"] and "{n}" in live["connections_count"]
        assert "{program}" in live["program_error"] and "{code}" in live["program_error"]
    pt = json.loads((ROOT / "static" / "i18n" / "pt.json").read_text(encoding="utf-8"))["live"]
    assert pt["running_queries_count"] == "{n} queries em execução" and pt["connections_count"] == "{n} conexões"
