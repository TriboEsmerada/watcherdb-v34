"""
2026-09-15 -- LIVE Waits: o re-render da ordenacao reutiliza o delta da leitura em vez de o recalcular contra ela propria.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
WAITS = PORTAL[PORTAL.index("function _liveRenderWaits(data, tabId) {"):PORTAL.index("function _liveRenderBlocking(data) {")]


def test_delta_calculado_uma_vez_por_leitura():
    assert "_liveWaitsMemo.ts === data.timestamp && _liveWaitsMemo.inst === data.instance" in WAITS
    assert "deltaWaits = _liveWaitsMemo.rows;" in WAITS
    i_memo = WAITS.index("_liveWaitsMemo = { ts: data.timestamp")
    i_prev = WAITS.index("_liveWaitsPrev = waits;")
    assert i_prev < i_memo, "o prev so avanca quando chega uma leitura nova"
    assert WAITS.count("_liveWaitsPrev = waits;") == 1


def test_mudar_de_canal_ou_programa_reinicia_o_memo():
    assert "let _liveWaitsMemo = null;" in PORTAL
    assert PORTAL.count("            _liveWaitsPrev = null;\n            _liveWaitsMemo = null;\n") == 2
