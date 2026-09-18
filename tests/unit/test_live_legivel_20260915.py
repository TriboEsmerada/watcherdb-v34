"""
2026-09-15 -- LIVE legivel: ordenacao em todas as tabelas, Batch/s real, PLE e Mem, Sched com leitura, Jobs com passo e
progresso reais.
"""
import asyncio
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
LIVE = PORTAL[PORTAL.index("const _liveLastData = {};"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
JOBS_JS = PORTAL[PORTAL.index("function _liveRenderJobs(data) {"):PORTAL.index("function _liveRenderMemory(data) {")]
SCHED_JS = PORTAL[PORTAL.index("function _liveRenderSchedulers(data) {"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]


def _lm():
    from api.routers import live_monitoring as lm
    return lm


def test_consultas_de_jobs_so_leitura_e_passo_em_curso():
    lm = _lm()
    for sql in (lm.JOBS_RUNNING_SQL, lm.PROGRESS_OPS_SQL):
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|CREATE|ALTER|DROP|TRUNCATE)\b", sql)
    j = lm.JOBS_RUNNING_SQL
    assert "ISNULL(ja.last_executed_step_id, 0) + 1" in j and "'(starting)'" not in j
    assert "CONVERT(VARCHAR(34), CONVERT(BINARY(16), j.job_id), 1)" in j and "percent_complete" in j
    assert "WHERE r.percent_complete > 0" in lm.PROGRESS_OPS_SQL


def test_endpoint_jobs_operacoes_fail_open(monkeypatch):
    lm = _lm()
    chamadas = []

    def falso(instance, sql, database="master", timeout=10):
        chamadas.append(database)
        if "sysjobactivity" in sql:
            return [{"job_name": "J", "start_execution_date": None}], None
        return None, "sem permissao"

    monkeypatch.setattr(lm, "_query_instance", falso)
    r = asyncio.run(lm.get_jobs_running("X_I01"))
    corpo = json.loads(r.body)
    assert corpo["count"] == 1 and corpo["operations"] == [] and corpo["operations_error"] is True
    assert chamadas == ["msdb", "master"]


def test_ordenacao_generica_em_todas_as_tabelas():
    assert "_liveRenderAndSet(screen, _liveProgram, pd, tabId);" in LIVE
    assert "if (screen) _liveRenderAndSet(screen, program, cached, tabId);" in LIVE
    assert "screen.innerHTML = _liveRenderProgram(program, data, tabId);\n            _liveEnhanceTables(screen, program);" in LIVE
    assert LIVE.count("screen.innerHTML = _liveRenderProgram(") == 1
    assert "table.querySelector('th[aria-sort]')" in LIVE and "table.querySelector('tbody tr[onclick]')" in LIVE
    assert "th.addEventListener('click', ordenar);" in LIVE and "ev.key === 'Enter' || ev.key === ' '" in LIVE
    assert "th.setAttribute('tabindex', '0');" in LIVE and "if (vazioA !== vazioB) return vazioA ? 1 : -1;" in LIVE


def test_gauges_batch_ple_mem():
    assert "_gc('lg-batch-'" not in LIVE and "_liveBatchPrev[chave] = agora;" in LIVE
    assert "(agora.v - antes.v) / dt" in LIVE
    assert "_gc('lg-ple-'+tabId, gd.ple_seconds, 's', 600, 300, true);" in LIVE
    assert "(livre < 512 || pctLivre < 2) ? 'var(--sev-critical-text)'" in LIVE and "live.mem_tip_detail" in LIVE


def test_jobs_e_sched_legiveis():
    assert "${j.current_step||''} (${j.current_step_id||0}" not in JOBS_JS and "current_step_id||0)/j.total_steps" not in JOBS_JS
    assert "j.step_percent" in JOBS_JS and "data.operations" in JOBS_JS and "live.ops_eta_note" in JOBS_JS
    assert "toLocaleString(document.documentElement.lang" in JOBS_JS
    assert "const seguidas = k >= 2;" in SCHED_JS and "memo.hist[i] > 1" in SCHED_JS and "'Yields/s'" in SCHED_JS and "'Ctx Switches/s'" in SCHED_JS
    assert "run > 1 ?" in SCHED_JS and "(s.runnable_tasks_count||0) > 2" not in SCHED_JS


def test_chaves_nos_tres_idiomas():
    novas = ("measuring", "mem_tip_detail", "sched_ok", "sched_spike", "sched_pressure", "sched_io_ok", "sched_io_wait",
             "sched_rates_note", "sched_tip_tasks", "sched_tip_runnable", "sched_tip_workers", "sched_tip_io",
             "sched_tip_rates", "job_step", "job_no_progress_tip", "ops_title", "ops_none", "ops_unavailable", "ops_eta_note")
    for loc in ("pt", "en", "es"):
        live = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for k in novas:
            assert live[k].strip(), (loc, k)
        assert all(x in live["job_step"] for x in ("{i}", "{n}", "{name}")), loc
        assert all(x in live["sched_pressure"] for x in ("{n}", "{r}", "{k}")), loc
        assert ">85%" not in live["gauge_mem_tip"], loc
