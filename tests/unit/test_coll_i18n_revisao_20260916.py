"""
2026-09-16 -- revisao linguistica do grupo coll: AO90 no pt, termo da casa (frota/fleet/flota), pt-BR no padrao do overlay.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}


def achatar(d, p=""):
    s = {}
    for k, v in d.items():
        s.update(achatar(v, p + k + ".")) if isinstance(v, dict) else s.update({p + k: v})
    return s


PT = achatar(LOCS["pt"]["coll"]); BR = achatar(LOCS["pt-BR"]["coll"]); EN = achatar(LOCS["en"]["coll"]); ES = achatar(LOCS["es"]["coll"])


def test_pt_esta_no_acordo_de_1990_como_o_resto_do_ficheiro():
    texto = " ".join(PT.values())
    for antigo in ("actualiz", "Actualiz", "activ", "Activ", "acção", "Acção", "correcção", "excepção", "Excepção",
                   "detectad", "directo", "directa", "actual", "Actual"):
        assert antigo not in texto, f"grafia antiga no coll pt: {antigo}"


def test_termo_da_casa_frota_fleet_flota():
    assert "parque" not in " ".join(PT.values()).lower() and "frota" in " ".join(PT.values()).lower()
    assert "estate" not in " ".join(EN.values()).lower() and "fleet" in " ".join(EN.values()).lower()
    assert "parque" not in " ".join(ES.values()).lower() and "flota" in " ".join(ES.values()).lower()


def test_pt_br_segue_o_padrao_do_overlay():
    texto = " ".join(BR.values())
    for pt_pt in ("A carregar", "A registar", "A registrar", "Pesquisar", "recolhedor", "registo ", "registado"):
        assert pt_pt not in texto, f"pt-BR com construcao pt-PT: {pt_pt!r}"
    # onde o pt diz "A carregar", o pt-BR tem de ter override em gerundio
    for k, v in PT.items():
        if "A carregar" in v:
            assert k in BR and "Carregando" in BR[k], f"pt-BR sem override em gerundio para {k}"


def test_pt_br_nao_repete_o_pt_nem_perde_o_que_difere():
    iguais = [k for k, v in BR.items() if PT.get(k) == v]
    assert iguais == [], f"chaves pt-BR iguais ao pt: {iguais}"
    assert set(BR) <= set(PT)
    assert "det.last_run" not in BR, "pt-BR nao pode quebrar a distincao passagem (automatico) / execucao (manual)"
    assert BR["search_ph"] == "Buscar por nome..." and BR["run.st_registering"] == "Registrando o pedido"


def test_marcadores_sobrevivem_em_todos_os_idiomas():
    for k, v in PT.items():
        marcas = set(re.findall(r"\{[a-z]+\}", v))
        for loc, d in (("pt-BR", {**PT, **BR}), ("en", EN), ("es", ES)):
            assert set(re.findall(r"\{[a-z]+\}", d[k])) == marcas, f"{loc}: {k} perdeu ou ganhou marcadores"
