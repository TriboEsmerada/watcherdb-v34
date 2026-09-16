"""
2026-09-16 -- Collector Health (lote 1): a modal dos 7 estados esta ligada ao dicionario nos quatro idiomas.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
ESTADOS = ["FRESH", "RECENT", "QUIET", "STALE", "FAILED", "DISABLED", "NEVER_RAN"]
CAMPOS = ["meaning", "normal", "problem", "action"]


def test_os_quatro_idiomas_tem_o_grupo_completo():
    for loc in ("pt", "en", "es"):
        coll = LOCS[loc]["coll"]
        assert set(coll["state"]) == set(ESTADOS), f"{loc}: faltam estados"
        for e in ESTADOS:
            for c in CAMPOS:
                assert coll["state"][e][c].strip(), f"{loc}: {e}.{c} vazio"
        for r in CAMPOS:
            assert coll["state_info"]["label"][r].strip()
        assert coll["state_info"]["title"].strip()
        assert coll["help_icon"].strip() and coll["close"].strip()


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    """O projecto recusa chaves pt-BR iguais a`s de pt (seriam ruido no sobreposto)."""
    def achatar(d, prefixo=""):
        saida = {}
        for k, v in d.items():
            if isinstance(v, dict):
                saida.update(achatar(v, prefixo + k + "."))
            else:
                saida[prefixo + k] = v
        return saida
    pt = achatar(LOCS["pt"]["coll"])
    br = achatar(LOCS["pt-BR"]["coll"])
    iguais = [k for k, v in br.items() if pt.get(k) == v]
    assert iguais == [], f"chaves pt-BR iguais ao pt: {iguais}"
    assert set(br) <= set(pt), "o sobreposto nao pode ter chaves que o pt nao tem"


def test_nenhuma_traducao_ficou_em_portugues_no_ingles():
    """Rede contra copiar-colar: o ingles nao pode trazer palavras que so' existem em pt."""
    texto = json.dumps(LOCS["en"]["coll"], ensure_ascii=False).lower()
    for palavra in ("recolhedor", "coletor", "acção", "estado saudável", "nunca é problema"):
        assert palavra not in texto, f"ingles com texto portugues: {palavra}"


def test_o_glossario_do_recolhedor_e_coerente_por_idioma():
    def junta(loc):
        return json.dumps(LOCS[loc]["coll"], ensure_ascii=False).lower()
    assert "recolhedor" in junta("pt") and "coletor" not in junta("pt")
    assert "coletor" in junta("pt-BR") and "recolhedor" not in junta("pt-BR")
    assert "colector" in junta("es")
    assert "collector" in junta("en")


def test_a_modal_usa_o_dicionario_com_recurso_ao_portugues():
    assert "const _collT = (chave, pt) =>" in PORTAL
    i = PORTAL.index("window.collOpenStateInfo = function")
    bloco = PORTAL[i:i + 3000]
    assert "_collT('coll.state_info.title'" in bloco
    assert "_collT('coll.state.' + s.key + '.meaning', s.meaning)" in bloco
    for rotulo in ("meaning", "normal", "problem", "action"):
        assert f"_collT('coll.state_info.label.{rotulo}'" in bloco
    assert "_collT('coll.close', 'Fechar')" in bloco
    assert "_collT('coll.state_info.footer_esc'" in bloco


def test_o_texto_em_portugues_continua_la_como_recurso():
    """Se o dicionario falhar, o utilizador ve portugues e nao uma chave crua."""
    i = PORTAL.index("const COLL_STATE_INFO = [")
    bloco = PORTAL[i:i + 6000]
    for e in ESTADOS:
        assert f"key: '{e}'" in bloco


def test_a_dica_do_icone_tem_chave():
    assert 'data-i18n-title="coll.help_icon"' in PORTAL
