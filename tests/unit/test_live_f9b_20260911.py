"""
2026-09-11 -- LIVE F9b: nomes completos no Fleet + tooltips sobreviventes.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
FLEET = PORTAL[PORTAL.index("function _liveRenderFleet"):PORTAL.index("function _fleetSwitchTo")]


def test_fleet_shows_full_instance_id():
    assert ".instance||'').split('_')[0]" not in FLEET
    assert FLEET.count("// F9b: id completo") == 6


def test_fleet_name_cells_are_wide_enough():
    assert 'width:75px;color:var(--color-text-link)' not in FLEET
    assert 'width:70px;color:var(--color-text-link)' not in FLEET
    assert FLEET.count('width:130px;flex-shrink:0;color:var(--color-text-link)') == 4


def test_surviving_tooltips_have_keys():
    assert 'title="Arrasta para mover"' not in PORTAL
    assert """title="${t('live.off_tip')}"><i class="fas fa-power-off"></i> OFF</button>""" in PORTAL
    assert 'data-i18n-title="live.nav_tip"' in PORTAL and 'data-i18n-aria="live.nav_aria"' in PORTAL
    assert 'data-i18n-title="ui.expand_collapse_modal"' in PORTAL


def test_keys_in_three_locales():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for k in ("drag_to_move", "off_tip", "nav_aria", "nav_tip"):
            assert d["live"][k], (loc, k)
        assert d["ui"]["expand_collapse_modal"], loc
