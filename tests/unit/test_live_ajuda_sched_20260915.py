"""
2026-09-15 -- LIVE: ajuda "?" do separador activo em todo o LIVE e Sched em caixas.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
SHELL = PORTAL[PORTAL.index("function openLiveMonitoringModal()"):PORTAL.index("function _liveLoadChannels")]
SCHED = PORTAL[PORTAL.index("function _liveRenderSchedulers(data) {"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
PROGS = ["fleet", "queries", "waits", "blocking", "plancache", "memory", "tempdb", "io", "tlog", "connections", "jobs",
         "alwayson", "schedulers", "errorlog"]


def test_um_botao_de_ajuda_acessivel_e_painel_fora_do_ecra():
    assert SHELL.count('class="live-help-btn"') == 1 and 'class="live-prog-btn" data-prog="help"' not in SHELL
    assert 'aria-expanded="false" aria-controls="live-help-${tabId}"' in SHELL
    assert SHELL.index('id="live-help-${tabId}" role="region"') < SHELL.index('id="live-screen-${tabId}"')
    assert "max-height:220px;overflow-y:auto;" in SHELL


def test_escape_fecha_primeiro_a_ajuda_e_ajuda_segue_o_separador():
    esc = SHELL[SHELL.index("const escHandler = (e) => {"):]
    assert esc.index("liveToggleHelp(tabId, false); return;") < esc.index("m.remove()")
    setp = PORTAL[PORTAL.index("function liveSetProgram(tabId, program) {"):]
    assert setp.index("_liveHelpRefresh(tabId);") < setp.index("document.querySelectorAll('.live-prog-btn')")
    assert "const _LIVE_HELP_PROGS = ['" + "', '".join(PROGS) + "'];" in PORTAL


def test_sched_em_caixas_sem_barra_active_workers():
    assert "repeat(auto-fill,minmax(${compacto ? 36 : 76}px,1fr))" in SCHED and "const compacto = scheds.length > 48;" in SCHED
    assert "work_queue_count" in SCHED and "live.sched_badge_noworker" in SCHED
    assert "<details ${_liveSchedDetailsOpen ? 'open' : ''} ontoggle=\"_liveSchedToggle(this)\"" in SCHED
    assert "active_workers_count / " not in SCHED and "--color-text-disabled" not in SCHED
    assert "if (kio >= 2) passos.push(t('live.sched_next_io'));" in SCHED
    assert "CRITICAL" not in SCHED


def test_chaves_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        live = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for p in PROGS:
            for k in ("title", "what", "how", "when", "next"):
                assert live[f"help_{p}_{k}"].strip(), (loc, p, k)
        for k in ("help_tip", "help_region", "help_close", "help_label_what", "help_label_how", "help_label_when",
                  "help_label_next", "sched_state_ok", "sched_state_spike", "sched_state_pressure", "sched_next_queries",
                  "sched_next_io", "sched_legend", "sched_details", "sched_working", "sched_tip_workqueue"):
            assert live[k].strip(), (loc, k)
        for k in ("sched_badge_queue", "sched_badge_noworker", "sched_working"):
            assert "{n}" in live[k], (loc, k)
        assert all(x in live["sched_card_tip"] for x in ("{id}", "{cpu}", "{run}", "{wq}", "{act}", "{io}")), loc
