"""Gates A-4.4 (resposta generica no login) e A-4.5 (lockout expirado repoe contador).

Origem: pauta P4 do QA externo (2026-09-07). Sem BD: _get_user_from_db e os helpers de
contador/audit sao substituidos; a verificacao de password e' determinista.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

import services.auth_service as auth
from services.auth_service import GENERIC_LOGIN_ERROR, AuthService


class _Harness:
    def __init__(self, svc: AuthService):
        self.svc = svc
        self.increments: list[str] = []
        self.resets: list[str] = []
        self.audit: list[tuple] = []
        self.counter = 0


@pytest.fixture
def h(monkeypatch):
    monkeypatch.setattr(auth, "AD_ENABLED", False)          # sem AD: caminho local
    monkeypatch.setattr(auth, "verify_password", lambda plain, hashed: plain == "certa")
    monkeypatch.setattr(auth, "hash_password", lambda p: "hash-dummy")
    monkeypatch.setattr(auth, "create_access_token", lambda data: "tok-de-teste")
    svc = AuthService()
    hh = _Harness(svc)

    def _inc(username):
        hh.increments.append(username)
        hh.counter += 1
        return hh.counter

    monkeypatch.setattr(svc, "_increment_failed_attempts", _inc)
    monkeypatch.setattr(svc, "_reset_failed_attempts", lambda u: hh.resets.append(u))
    monkeypatch.setattr(svc, "_update_last_login", lambda u: None)
    monkeypatch.setattr(svc, "_log_auth", lambda *a, **k: hh.audit.append(a))
    return hh


def _user(**over):
    base = {"username": "u", "password_hash": "$2b$fake", "role": "viewer", "disabled": 0,
            "failed_attempts": 0, "locked_until": None, "full_name": "U", "email": None}
    base.update(over)
    return base


def _login(h, user, password):
    h.svc._get_user_from_db = lambda name: (dict(user) if user is not None else None)
    return asyncio.run(h.svc.authenticate("u", password, "127.0.0.1"))


# ---------------------------------------------------------------- A-4.4: resposta generica

def test_conta_inexistente_e_password_errada_dao_a_mesma_mensagem(h):
    r_inexistente = _login(h, None, "qualquer")
    r_errada = _login(h, _user(), "errada")
    assert r_inexistente["success"] is False and r_errada["success"] is False
    assert r_inexistente["error"] == r_errada["error"] == GENERIC_LOGIN_ERROR


def test_mensagem_nao_revela_contador_nem_bloqueio(h):
    h.counter = 4  # proxima falha e' a 5.a
    r = _login(h, _user(failed_attempts=4), "errada")
    assert r["error"] == GENERIC_LOGIN_ERROR
    assert "Tentativa" not in r["error"] and "BLOQUEADA" not in r["error"]
    # o detalhe continua no audit log
    assert any("5/" in str(a) for a in h.audit)


def test_conta_bloqueada_activa_da_mensagem_generica_e_nao_incrementa(h):
    futuro = (datetime.now() + timedelta(minutes=10)).isoformat()
    r = _login(h, _user(failed_attempts=5, locked_until=futuro), "certa")
    assert r["success"] is False and r["error"] == GENERIC_LOGIN_ERROR
    assert h.increments == [] and h.resets == []
    assert any("bloqueada" in str(a).lower() for a in h.audit)


def test_conta_desactivada_da_mensagem_generica(h):
    r = _login(h, _user(disabled=1), "certa")
    assert r["success"] is False and r["error"] == GENERIC_LOGIN_ERROR


def test_login_correcto_continua_a_funcionar(h):
    r = _login(h, _user(), "certa")
    assert r["success"] is True and r["access_token"] == "tok-de-teste"
    assert h.resets == ["u"]


# ---------------------------------------------------------------- A-4.5: lockout expirado

def test_lockout_expirado_repoe_contador_antes_de_verificar(h):
    passado = (datetime.now() - timedelta(minutes=1)).isoformat()
    r = _login(h, _user(failed_attempts=5, locked_until=passado), "errada")
    # 1) o contador foi reposto por causa da expiracao (antes do incremento da falha nova)
    assert h.resets == ["u"], "bloqueio expirado tem de repor failed_attempts/locked_until"
    # 2) a falha nova conta como 1.a, nao como 6.a
    assert h.increments == ["u"] and h.counter == 1
    assert r["success"] is False and r["error"] == GENERIC_LOGIN_ERROR


def test_lockout_expirado_e_password_certa_entra(h):
    passado = (datetime.now() - timedelta(minutes=1)).isoformat()
    r = _login(h, _user(failed_attempts=5, locked_until=passado), "certa")
    assert r["success"] is True
    # reposto pela expiracao e outra vez pelo sucesso: nunca fica em MAX
    assert h.resets.count("u") >= 1 and h.increments == []
