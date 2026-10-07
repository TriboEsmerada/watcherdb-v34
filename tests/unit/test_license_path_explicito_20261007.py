# -*- coding: utf-8 -*-
"""2026-10-07 -- LICENSE_PATH_EXPLICITO: o primeiro nivel configurado e' autoritativo.

Antes, um WATCHERDB_LICENSE_PATH (ou DATA_DIR) sem ficheiro caia em silencio na licenca de
C:\\ProgramData\\WatcherDB -- no PC1 a do V3.3 -> assinatura invalida em vez de 'licenca em falta'.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from watcherdb.licensing import startup_guard as sg
from watcherdb.licensing import crl as crlmod

_VARS = ("WATCHERDB_LICENSE_PATH", "WATCHERDB_PUBLIC_KEY_PATH", "WATCHERDB_CRL_PATH", "WATCHERDB_DATA_DIR")


@pytest.fixture()
def limpo(monkeypatch):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_licenca_explicita_inexistente_nao_cai_em_programdata(limpo, tmp_path):
    alvo = tmp_path / "nao_existe.dat"
    limpo.setenv("WATCHERDB_LICENSE_PATH", str(alvo))
    assert sg._resolve_license_path() == alvo  # mesmo sem existir: o validador dira' 'licenca em falta'


def test_data_dir_sem_licenca_nao_cai_em_programdata(limpo, tmp_path):
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert sg._resolve_license_path() == tmp_path / "license.dat"


def test_sem_nada_configurado_fica_o_legado(limpo):
    assert sg._resolve_license_path() == Path(r"C:\\ProgramData\\WatcherDB\\license.dat")


def test_chave_publica_explicita_e_o_unico_candidato(limpo, tmp_path):
    limpo.setenv("WATCHERDB_PUBLIC_KEY_PATH", str(tmp_path / "k.pem"))
    assert sg._public_key_candidates_tried(tmp_path) == [tmp_path / "k.pem"]


def test_chave_publica_cai_no_bundle_quando_falta_na_pasta_de_dados(limpo, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "deploy" / "keys").mkdir(parents=True)
    (bundle / "deploy" / "keys" / "ed25519_public.pem").write_text("x", encoding="utf-8")
    dados = tmp_path / "dados"
    dados.mkdir()
    limpo.setenv("WATCHERDB_DATA_DIR", str(dados))
    assert sg._resolve_public_key_path(bundle) == bundle / "deploy" / "keys" / "ed25519_public.pem"
    assert all("ProgramData" not in str(p) for p in sg._public_key_candidates_tried(bundle))


def test_chave_publica_sem_data_dir_mantem_programdata_e_bundle(limpo, tmp_path):
    tried = sg._public_key_candidates_tried(tmp_path)
    assert tried[0] == Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem")
    assert tried[-1] == tmp_path / "deploy" / "keys" / "ed25519_public.pem"


def test_crl_explicita_e_autoritativa(limpo, tmp_path):
    limpo.setenv("WATCHERDB_CRL_PATH", str(tmp_path / "nao_existe.json"))
    assert crlmod._resolve_crl_path(tmp_path) == tmp_path / "nao_existe.json"


def test_crl_com_data_dir_nao_cai_em_programdata(limpo, tmp_path):
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    p = crlmod._resolve_crl_path(None)
    assert p == tmp_path / crlmod.DEFAULT_CRL_FILENAME


def test_baseline_do_build_ja_nao_lista_o_teste_do_grace():
    br = (Path(__file__).resolve().parents[2] / "deploy" / "build_release.ps1").read_text(encoding="utf-8")
    assert "test_startup_guard_grace_period_allows_missing_license'" not in br
