# -*- coding: utf-8 -*-
"""
2026-09-21 (owner): sem canal, cada programa mostra a frota so' do seu tema (payload do Fleet, sem endpoint novo).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LIVE = PORTAL[PORTAL.index("const _liveLastData = {};"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
TEMAS = ("queries", "blocking", "tempdb", "waits", "alwayson", "connections", "errorlog", "space")


def test_modo_frota_por_tema_existe_e_cobre_os_8_temas():
    assert "function _liveFleetMode(program)" in LIVE and "function _liveRenderFleetTheme(program, data, tabId)" in LIVE
    m = re.search(r"const _LIVE_FLEET_THEME = \{([^}]*)\};", LIVE)
    assert m and set(re.findall(r"(\w+): 1", m.group(1))) == set(TEMAS)
    for tema in TEMAS:
        assert f"program === '{tema}'" in LIVE[LIVE.index("function _liveRenderFleetTheme"):]


def test_sem_canal_o_programa_decide_e_o_refresh_usa_o_fleet():
    assert "if (!instance) { if (_liveProgram !== 'fleet') liveSetProgram(tabId, _liveProgram); return; }" in LIVE
    assert "if (_liveInstance || _liveFleetMode(program)) {" in LIVE
    assert "if (!_liveInstance && !_liveFleetMode()) return;" in LIVE
    assert "const isFleet = _liveFleetMode();" in LIVE
    assert "if ((_liveInstance || _liveFleetMode()) && !_livePaused) {" in LIVE
    # o despacho so' entra em modo frota (sem instancia) e com payload do Fleet (instances)
    assert "if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && data.instances) return _liveRenderFleetTheme(program, data, tabId);" in LIVE
    # medidores: escondidos em modo frota, voltam ao escolher canal
    assert "s.style.display = _liveFleetMode(program) ? 'none' : '';" in LIVE and "_liveGaugesVisible(tabId, true);" in LIVE
    # programas sem vista de frota mantem o estado neutro (o ramo else de liveSetProgram continua)
    assert "_liveShowNoInstance(tabId, program);  // 2026-09-11" in LIVE


def test_linhas_abrem_a_instancia_no_programa_e_a_nota_esta_na_vista():
    r = LIVE[LIVE.index("function _liveRenderFleetTheme"):LIVE.index("window._liveFleetMode = _liveFleetMode;")]
    assert "_fleetSwitchTo('${esc(inst)}','${prog}')" in r and "_fleetSwitchTo('${esc(first)}','waits')" in r
    assert "_kpiT('live.fleet_theme_note'" in r and "_kpiTp('live.fleet_theme_title'" in r and "_kpiTp('live.fleet_theme_empty'" in r
    assert "_fleetSpacePanel(data.space_risk)" in r and "_fleetCopySql(this)" in r
    assert "font-size:1[01]px" not in r   # tipografia LIVE: >= 12px


def test_i18n_nas_tres_linguas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static/i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for k in ("fleet_theme_title", "fleet_theme_sub", "fleet_theme_note", "fleet_theme_empty", "fleet_theme_neutral"):
            assert k in d, (loc, k)
        assert "{theme}" in d["fleet_theme_title"] and "{n}" in d["fleet_theme_sub"] and "{theme}" in d["fleet_theme_empty"]
