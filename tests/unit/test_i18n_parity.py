"""Paridade e higiene dos dicionarios i18n (pt/en/es + overlay pt-BR).

Nasce do relatorio de QA externo 2026-08-16 (BUG-003/005/013): o QA propos um
teste que falhe quando os 3 locales divergem, e outro para texto visivel sem
chave i18n. O segundo NAO esta aqui de proposito -- ha ~435 strings hardcoded
ja mapeadas (BUG-003, KPI_METADATA e CARD_HELP_TEXTS), logo nasceria vermelho
e seria desligado; fica para a wave que migrar essas strings.

Norma decidida pelo owner 2026-08-16: PT-PT pos-AO90 (atualizar/ativo/direto).
"""
import json
import re
from pathlib import Path

import pytest

I18N_DIR = Path(__file__).resolve().parents[2] / "static" / "i18n"
LOCALES = ("pt", "en", "es")
OVERLAY_LOCALES = ("pt-BR",)  # overlay esparso de pt (owner 2026-09-03): subconjunto, sem chaves extra


def _flatten(node, path=""):
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_flatten(v, f"{path}.{k}" if path else k))
    else:
        out[path] = node
    return out


def _load(locale):
    with open(I18N_DIR / f"{locale}.json", encoding="utf-8") as fh:
        return _flatten(json.load(fh))


@pytest.fixture(scope="module")
def dicts():
    return {loc: _load(loc) for loc in LOCALES + OVERLAY_LOCALES}


def test_all_locales_exist():
    for loc in LOCALES + OVERLAY_LOCALES:
        assert (I18N_DIR / f"{loc}.json").is_file(), f"{loc}.json em falta"


def test_key_parity_across_locales(dicts):
    """en/es tem de ter exactamente as chaves de pt (pt e' o ground truth)."""
    pt = set(dicts["pt"])
    for loc in ("en", "es"):
        other = set(dicts[loc])
        missing = sorted(pt - other)
        extra = sorted(other - pt)
        assert not missing, f"{loc}.json sem {len(missing)} chaves de pt: {missing[:10]}"
        assert not extra, f"{loc}.json com {len(extra)} chaves que pt nao tem: {extra[:10]}"


def test_no_empty_values(dicts):
    for loc, flat in dicts.items():
        empty = sorted(k for k, v in flat.items() if isinstance(v, str) and not v.strip())
        assert not empty, f"{loc}.json com valores vazios: {empty[:10]}"


# Grafia pre-AO90 que a norma PT-PT pos-AO90 elimina (decisao owner 2026-08-16).
_PRE_AO90 = re.compile(
    r"\b(actualiz|activ[oaers]|desactiv|reactiv|directa|directo|directamente|"
    r"afectad|seleccion|excepc|objectiv|colectar)",
    re.IGNORECASE,
)
# Identificadores tecnicos (snake_case, MAIUSCULAS: log_reuse_wait_desc, ACTIVE_TRANSACTION,
# active_end_date) nao sao portugues -- saem antes da regex (lote F3 2026-09-09).
_IDENTIFICADOR = re.compile(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b|\b[A-Z]{4,}\b")


def test_pt_uses_post_ao90_spelling(dicts):
    """pt.json nao volta a introduzir grafia pre-AO90 (BUG-005)."""
    offenders = {
        f"{loc}:{k}": v
        for loc in ("pt",) + OVERLAY_LOCALES
        for k, v in dicts[loc].items()
        if isinstance(v, str) and _PRE_AO90.search(_IDENTIFICADOR.sub("", v))
    }
    assert not offenders, (
        "grafia pre-AO90 em pt.json (usar atualizar/ativo/direto/selecionado): "
        + "; ".join(f"{k}={v!r}" for k, v in list(offenders.items())[:10])
    )


def test_placeholders_match_across_locales(dicts):
    """{count}, {time}, ... tem de existir nos 3 locales ou a string parte."""
    ph = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
    pt = dicts["pt"]
    problems = []
    for loc in ("en", "es") + OVERLAY_LOCALES:
        for key, value in dicts[loc].items():
            if not isinstance(value, str) or not isinstance(pt.get(key), str):
                continue
            if set(ph.findall(pt[key])) != set(ph.findall(value)):
                problems.append(f"{loc}:{key}")
    assert not problems, f"placeholders divergentes: {problems[:10]}"


def test_ptbr_overlay_is_sparse_subset_of_pt(dicts):
    """pt-BR e' overlay (owner 2026-09-03): so' chaves que existem em pt E cujo texto difere de pt."""
    pt = dicts["pt"]
    for loc in OVERLAY_LOCALES:
        flat = dicts[loc]
        assert flat, f"{loc}.json vazio -- overlay sem overrides nao faz sentido"
        orphans = sorted(k for k in flat if k not in pt)
        assert not orphans, f"{loc}.json com chaves que pt nao tem: {orphans[:10]}"
        redundant = sorted(k for k, v in flat.items() if pt.get(k) == v)
        assert not redundant, f"{loc}.json com overrides identicos a pt (redundantes): {redundant[:10]}"
