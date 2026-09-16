"""
2026-09-16 -- Collector Health (lote 2b): a janela de silenciar alertas fala o idioma escolhido.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
CHAVES = ["title", "subtitle", "add", "f_kpi", "ph_kpi", "f_instance", "ph_instance", "f_reason",
          "ph_reason", "f_hours", "btn", "note", "empty", "empty_sub", "count_one", "count_many",
          "col_reason", "col_created_by", "col_hrs_left", "col_until", "unmute", "confirm_delete",
          "val_required", "val_reason", "val_hours", "err_create", "err_delete", "err_load"]


def test_os_tres_idiomas_completos():
    for loc in ("pt", "en", "es"):
        mute = LOCS[loc]["coll"]["mute"]
        for k in CHAVES:
            assert mute[k].strip(), f"{loc}: mute.{k}"
        assert len(LOCS[loc]["coll"]["state"]) == 7          # lote 1 intacto
        assert LOCS[loc]["coll"]["events"]["title"].strip()  # lote 2a intacto


def test_marcadores_certos():
    for loc in ("pt", "en", "es"):
        mute = LOCS[loc]["coll"]["mute"]
        assert "{n}" in mute["count_one"] and "{n}" in mute["count_many"]
        assert "{kpi}" in mute["confirm_delete"] and "{inst}" in mute["confirm_delete"]


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    pt, br = LOCS["pt"]["coll"]["mute"], LOCS["pt-BR"]["coll"]["mute"]
    assert [k for k, v in br.items() if pt.get(k) == v] == []
    assert set(br) <= set(pt)


def test_nada_de_jargao_ingles_no_portugues():
    """So' os VALORES: os nomes das chaves (unmute, f_kpi) sao internos e ficam em ingles de proposito."""
    texto = " | ".join(LOCS["pt"]["coll"]["mute"].values()).lower()
    for p in ("hrs left", "created by", "unmute", "mute hours", "audit trail", "mute list"):
        assert p not in texto, f"portugues ainda com jargao: {p}"


def test_o_portal_usa_as_chaves():
    for k in CHAVES:
        assert f"'coll.mute.{k}'" in PORTAL, f"chave nao usada: coll.mute.{k}"
    assert "_collT('coll.col.instance'" in PORTAL and "_collT('coll.col.action'" in PORTAL


def test_a_contagem_deixou_de_ser_parenteses_s():
    assert "mute(s) activo(s)" not in PORTAL
    assert "mutes.length === 1 ? 'coll.mute.count_one' : 'coll.mute.count_many'" in PORTAL


def test_a_confirmacao_usa_marcadores_e_nao_concatenacao():
    i = PORTAL.index("coll.mute.confirm_delete")
    bloco = PORTAL[i - 200:i + 300]
    assert "{ kpi: kpiType, inst: instance }" in bloco
