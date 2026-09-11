"""
2026-09-11 -- Space > DATAFILES: o painel era cortado pela regra global de <td>
(overflow hidden / max-width 400) aplicada a celula que o hospeda. Guardas estaticas.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_expansion_cells_opt_out_of_global_td_clip():
    assert ".space-fg-expansion > td, .space-files-expansion > td {" in PORTAL
    rule = PORTAL.split(".space-fg-expansion > td, .space-files-expansion > td {", 1)[1].split("}", 1)[0]
    assert "overflow: visible" in rule and "max-width: none" in rule and "white-space: normal" in rule


def test_files_row_spans_all_nine_filegroup_columns():
    assert 'id="files-row-${fgId}" class="space-files-expansion"' in PORTAL
    row = PORTAL.split('id="files-row-${fgId}"', 1)[1].split("</tr>", 1)[0]
    assert 'colspan="9"' in row and 'colspan="8"' not in row


def test_logical_name_column_no_longer_forces_420px():
    assert "min-width: 420px; word-break: break-all;" not in PORTAL
    assert PORTAL.count("min-width: 260px; max-width: 420px; white-space: normal; word-break: break-all;") == 2


def test_decision_20260731_sticky_header_preserved():
    # o painel embutido continua SEM scroll proprio (thead sticky no scroll exterior)
    assert ".space-datafiles-scroll { overflow: visible; }" in PORTAL
