# -*- coding: utf-8 -*-
"""2026-10-07 -- DATA_DIR_SERVICO: o licenciamento honra WATCHERDB_DATA_DIR e o instalador grava-a no servico.

Antes: startup_guard/grace_period/crl so' aceitavam variaveis por ficheiro ou C:\\ProgramData\\WatcherDB fixo,
e o install.ps1 provisionava em %ProgramData%\\WatcherDB\\V3.4 sem dizer ao servico onde era.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from watcherdb.licensing import startup_guard as sg
from watcherdb.licensing import grace_period as gp
from watcherdb.licensing import crl as crlmod

ROOT = Path(__file__).resolve().parents[2]
INSTALL = (ROOT / "deploy" / "install.ps1").read_text(encoding="utf-8").replace("\r\n", "\n")

_ESPECIFICAS = ("WATCHERDB_LICENSE_PATH", "WATCHERDB_PUBLIC_KEY_PATH", "WATCHERDB_INSTALL_MARKER_PATH", "WATCHERDB_CRL_PATH")


@pytest.fixture()
def limpo(monkeypatch):
    for v in _ESPECIFICAS + ("WATCHERDB_DATA_DIR",):
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_licenca_na_pasta_de_dados(limpo, tmp_path):
    (tmp_path / "license.dat").write_text("x", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert sg._resolve_license_path() == tmp_path / "license.dat"


def test_chave_publica_na_pasta_de_dados(limpo, tmp_path):
    (tmp_path / "ed25519_public.pem").write_text("x", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert sg._resolve_public_key_path(None) == tmp_path / "ed25519_public.pem"
    tried = sg._public_key_candidates_tried(None)
    assert tried.index(tmp_path / "ed25519_public.pem") < tried.index(Path(r"C:\\ProgramData\\WatcherDB\\ed25519_public.pem"))


def test_a_variavel_especifica_continua_a_ganhar(limpo, tmp_path):
    esp = tmp_path / "outra" ; esp.mkdir()
    (esp / "lic.dat").write_text("x", encoding="utf-8")
    (tmp_path / "license.dat").write_text("x", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    limpo.setenv("WATCHERDB_LICENSE_PATH", str(esp / "lic.dat"))
    assert sg._resolve_license_path() == esp / "lic.dat"


def test_sem_variavel_o_caminho_fixo_mantem_se(limpo, tmp_path):
    # ficheiros inexistentes -> devolve o ultimo candidato, como antes
    assert sg._resolve_license_path() == Path(r"C:\\ProgramData\\WatcherDB\\license.dat")
    assert gp._resolve_marker_path() == gp.DEFAULT_PROGRAMDATA / gp.DEFAULT_MARKER_FILENAME


def test_marker_do_grace_na_pasta_de_dados(limpo, tmp_path):
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert gp._resolve_marker_path() == tmp_path / gp.DEFAULT_MARKER_FILENAME
    # argumento explicito continua a ganhar (usado pelos testes antigos)
    assert gp._resolve_marker_path(tmp_path / "x") == tmp_path / "x" / gp.DEFAULT_MARKER_FILENAME


def test_crl_na_pasta_de_dados(limpo, tmp_path):
    (tmp_path / crlmod.DEFAULT_CRL_FILENAME).write_text("{}", encoding="utf-8")
    limpo.setenv("WATCHERDB_DATA_DIR", str(tmp_path))
    assert crlmod._resolve_crl_path(None) == tmp_path / crlmod.DEFAULT_CRL_FILENAME


def test_instalador_grava_o_ambiente_do_servico():
    i = INSTALL.index("PASSO (i-ter): ambiente do servico")
    bloco = INSTALL[i:i + 1600]
    assert "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\$ServiceName" in bloco
    assert "'WATCHERDB_DATA_DIR' = $DataDir" in bloco
    assert "'WATCHERDB_PORT' = [string]$rv.WebPort" in bloco
    assert "-Type MultiString" in bloco
    assert "$svcEnvKept" in bloco, "entradas alheias do Environment tem de ser preservadas"
    # depois de criar/reconfigurar o servico e antes do passo seguinte
    assert INSTALL.index("reconfigurado (upgrade)") < i < INSTALL.index("PASSO (i-bis)")
