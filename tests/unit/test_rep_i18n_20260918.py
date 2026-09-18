"""
2026-09-18 -- relatorios de diagnostico: cada regra tem chave rep.<ID>.title em pt/en/es; recomendacoes e detalhes
estaticos cobertos; rotulos fixos dos geradores passam por _repT.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LOC = {k: json.load(open(ROOT / f"static/i18n/{k}.json", encoding="utf-8")) for k in ("pt", "en", "es", "pt-BR")}


def _regras():
    out = []
    for m in re.finditer(r"^    const ([A-Z]+_RULES) = \[\n", PORTAL, re.M):
        ini = m.end(); fim = PORTAL.index("\n    ];", ini); bloco = PORTAL[ini:fim]
        for e in re.finditer(r"^        \{(.*?)^        \}", bloco, re.S | re.M):
            idm = re.search(r"\bid:\s*'([A-Z0-9]+)'", e.group(1))
            if idm:
                corpo = e.group(1)
                out.append((idm.group(1), bool(re.search(r"\brecommendation:\s*'[^']", corpo)), bool(re.search(r"\bdetail:\s*(?:\(\)\s*=>\s*)?'[^']", corpo)),
                            len(re.findall(r"\{\s*title:\s*'(?:[^'\\]|\\.)*',\s*sql:", corpo))))
    return out


def test_todas_as_regras_tem_titulo_e_o_que_e_estatico_tem_chave():
    regras = _regras()
    assert len(regras) >= 70
    for loc in ("pt", "en", "es"):
        g = LOC[loc]["rep"]
        for rid, tem_rec, tem_det, n_sql in regras:
            assert rid in g and g[rid].get("title"), (loc, rid)
            if tem_rec: assert g[rid].get("rec"), (loc, rid, "rec")
            if tem_det: assert g[rid].get("detail"), (loc, rid, "detail")
            for i in range(n_sql): assert g[rid].get("sql", {}).get(str(i)), (loc, rid, "sql", i)


def test_ponto_unico_de_traducao_e_rotulos():
    assert "function _repT(k, fb)" in PORTAL
    assert "title: _repT('rep.' + rule.id + '.title', rule.title)" in PORTAL
    assert "_repT('rep.' + rule.id + '.sql.' + i, q.title)" in PORTAL
    assert "const statusLabel = hasCritical ? 'CRITICO'" not in PORTAL
    assert PORTAL.count("_repT('rep.none_detected', 'Nenhum problema detectado.')") == 10
    for k in ("h_job", "h_file", "h_cert", "h_db_service", "h_gap_hours", "h_algorithm", "yes", "no"):
        assert f"_repT('rep.{k}'" in PORTAL, k


def test_pt_ao90_e_overlay_ptbr_so_diferencas():
    txt = json.dumps(LOC["pt"]["rep"], ensure_ascii=False)
    assert not re.search(r"detectad|actual\b|activ[oa]\b|correcç|excepç", txt)
    pt = LOC["pt"]["rep"]; over = LOC["pt-BR"].get("rep") or {}
    assert over
    def folhas(d, pref=""):
        for k, v in d.items():
            if isinstance(v, dict): yield from folhas(v, pref + k + ".")
            else: yield pref + k, v
    ptf = dict(folhas(pt))
    for k, v in folhas(over):
        assert k in ptf and ptf[k] != v, k
