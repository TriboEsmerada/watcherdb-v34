# -*- coding: utf-8 -*-
"""LIVE F9b (2026-09-11) -- dois restos do teste do owner ao LIVE:

  1. Fleet dashboard: nomes de instancia cortados ("SQLMDMQLT...", "SQLHDSPRD...") nos paineis Queries
     pesadas, TempDB consumers, AlwaysOn queues e Idle sessions. Causa: celula com width 70-75 px + ellipsis,
     e o nome ja vinha amputado (split('_')[0] tirava o sufixo da instancia, indistinguivel com 2 instancias
     no mesmo host). Passa a id completo (ex.: SQLHDSPRD405_I01) em 130 px; ellipsis + title ficam como rede.
  2. Tooltips ainda em PT com a UI em EN: botao LIVE da navbar (title + aria-label), "Arrasta para mover" no
     bezel do LIVE, OFF sem tooltip, e "Expandir/Reduzir modal" no modal de diagnostico. Chaves live.* e ui.*.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LIVE_F9B_2026-09-11_apply.py --check
  py docs/context/LIVE_F9B_2026-09-11_apply.py
  py -m pytest tests/unit/test_live_f9b_20260911.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_live_f9b_20260911.py"),
}
MARK = "live.drag_to_move"

_CELL_OLD_A = """<div style="width:75px;color:var(--color-text-link);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>"""
_CELL_NEW_A = """<div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>"""
_CELL_OLD_B = """<div style="width:75px;color:var(--color-text-link);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>"""
_CELL_NEW_B = """<div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>"""
_CELL_OLD_C = """<div style="width:70px;color:var(--color-text-link);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>"""
_CELL_NEW_C = """<div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>"""

P_EDITS = [
    # 1) id completo da instancia (6 paineis do Fleet)
    ("const name = (q.instance||'').split('_')[0];", "const name = (q.instance||'');  // F9b: id completo", 1),
    ("const name = (b.instance||'').split('_')[0];", "const name = (b.instance||'');  // F9b: id completo", 1),
    ("const name = (t.instance||'').split('_')[0];", "const name = (t.instance||'');  // F9b: id completo", 2),
    ("const name = (a.instance||'').split('_')[0];", "const name = (a.instance||'');  // F9b: id completo", 1),
    ("const name = (s.instance||'').split('_')[0];", "const name = (s.instance||'');  // F9b: id completo", 1),
    (_CELL_OLD_A, _CELL_NEW_A, 1),
    (_CELL_OLD_B, _CELL_NEW_B, 1),
    (_CELL_OLD_C, _CELL_NEW_C, 2),
    # 2) tooltips
    ("""title="Arrasta para mover">""", """title="${t('live.drag_to_move')}">""", 1),
    ("""font-size:12px;"><i class="fas fa-power-off"></i> OFF</button>""",
     """font-size:12px;" title="${t('live.off_tip')}"><i class="fas fa-power-off"></i> OFF</button>""", 1),
    ("""                    aria-label="Abrir monitorizacao em tempo real (LIVE)"
                    title="LIVE - Monitoramento em Tempo Real">""",
     """                    aria-label="Abrir monitorização em tempo real (LIVE)" data-i18n-aria="live.nav_aria"
                    title="LIVE — Monitorização em tempo real" data-i18n-title="live.nav_tip">""", 1),
    ("""onclick="toggleDiagnoseModalExpand()" title="Expandir/Reduzir modal\"""",
     """onclick="toggleDiagnoseModalExpand()" title="Expandir/Reduzir modal" data-i18n-title="ui.expand_collapse_modal\"""", 1),
]

LIVE_KEYS = {
    "pt": {"drag_to_move": "Arraste para mover", "off_tip": "Fechar o LIVE e parar a recolha",
           "nav_aria": "Abrir monitorização em tempo real (LIVE)", "nav_tip": "LIVE — Monitorização em tempo real"},
    "en": {"drag_to_move": "Drag to move", "off_tip": "Close LIVE and stop polling",
           "nav_aria": "Open real-time monitoring (LIVE)", "nav_tip": "LIVE — Real-time monitoring"},
    "es": {"drag_to_move": "Arrastre para mover", "off_tip": "Cerrar LIVE y detener el sondeo",
           "nav_aria": "Abrir monitorización en tiempo real (LIVE)", "nav_tip": "LIVE — Monitorización en tiempo real"},
}
UI_KEYS = {"pt": "Expandir/Reduzir modal", "en": "Expand/Collapse modal", "es": "Expandir/Reducir modal"}
LIVE_ANCHOR = {"pt": '    "error_http": "Erro HTTP {code}",\n', "en": '    "error_http": "HTTP error {code}",\n',
               "es": '    "error_http": "Error HTTP {code}",\n'}
UI_ANCHOR = '  "ui": {\n'

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE F9b: nomes de instância completos no Fleet dashboard e os tooltips que faltavam** — as células\n"
                  "  de 70–75 px cortavam \"SQLMDMQLT…\" e o nome já vinha sem o sufixo da instância (duas instâncias no mesmo\n"
                  "  host eram indistinguíveis); passa a id completo em 130 px. Botão LIVE da navbar, \"Arraste para mover\",\n"
                  "  OFF e \"Expandir/Reduzir modal\" (diagnóstico) ganham chaves em pt-PT, en e es. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:100]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal_raw = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal_raw:
        print("[ABORT] ja aplicado"); return 1
    out = {"portal": _apply(portal_raw, P_EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        live_lines = "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in LIVE_KEYS[loc].items())
        ui_line = f'    "expand_collapse_modal": {json.dumps(UI_KEYS[loc], ensure_ascii=False)},\n'
        out[loc] = _apply(raw, [(LIVE_ANCHOR[loc], LIVE_ANCHOR[loc] + live_lines, 1), (UI_ANCHOR, UI_ANCHOR + ui_line, 1)], loc)
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print(f"[ok] anchors: portal {len(P_EDITS)} blocos; i18n 4 live + 1 ui x3; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_f9b_20260911.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
