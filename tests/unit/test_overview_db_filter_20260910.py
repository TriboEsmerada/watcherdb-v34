"""FIX DB-FILTER 2026-09-10: regressao estatica do filtro de bases do Overview.

Origem: TestSprite TC-003 ("servidor e bases respeitam o contexto") + leitura do codigo.
O oninput do campo chamava renderDbTable(this.value) e descartava o retorno; a ordenacao,
que faz innerHTML = renderDbTable(...), funcionava. Sem estado vazio.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_oninput_aplica_o_filtro_no_dom():
    assert 'oninput="applyDbFilter(this.value)"' in PORTAL
    assert 'oninput="renderDbTable(this.value)"' not in PORTAL, "regressao: o retorno de renderDbTable voltou a ser descartado"


def test_apply_db_filter_toca_so_corpo_e_contagem():
    m = re.search(r"function applyDbFilter\(valor\) \{(.*?)\n\s*\}\n", PORTAL, re.S)
    assert m, "applyDbFilter nao existe"
    corpo = m.group(1)
    assert "getElementById('db-table-body')" in corpo and "getElementById('db-count')" in corpo
    assert "getElementById('databases-section')" not in corpo, "nao pode recriar a seccao (perde o foco do input)"


def test_tbody_e_contagem_tem_ids_e_estado_vazio():
    assert '<tbody id="db-table-body">' in PORTAL
    assert '<span id="db-count">' in PORTAL
    assert "const emptyRow = '<tr><td colspan=\"5\"" in PORTAL
    assert "t('overview.no_databases_found')" in PORTAL


def test_chave_i18n_nos_tres_locales():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert d["overview"]["no_databases_found"].strip(), loc
