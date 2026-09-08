"""Gate A-4.7 (pauta P4 do QA externo): mudanca/reset de password revoga os JWT anteriores.

Sem BD. A prova em runtime (login -> reset pelo admin -> pedido com o token antigo => 401) e' o
gate do QA externo; aqui fixa-se a logica e a ausencia de falha silenciosa.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

import services.auth_service as auth
from services.auth_service import AuthService, _token_valido_apos_reset, create_access_token


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()  # como SYSUTCDATETIME() chega via isoformat()


# ---------------------------------------------------------------- helper puro

def test_token_anterior_a_mudanca_e_rejeitado():
    agora = datetime.now(timezone.utc)
    payload = {"sub": "u", "iat": (agora - timedelta(minutes=10)).timestamp()}
    assert _token_valido_apos_reset(payload, {"password_changed_at": _iso(agora)}) is False


def test_token_posterior_a_mudanca_e_aceite():
    agora = datetime.now(timezone.utc)
    payload = {"sub": "u", "iat": (agora + timedelta(seconds=5)).timestamp()}
    assert _token_valido_apos_reset(payload, {"password_changed_at": _iso(agora)}) is True


def test_mesmo_segundo_e_aceite_por_tolerancia():
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {"sub": "u", "iat": int(agora.timestamp())}
    assert _token_valido_apos_reset(payload, {"password_changed_at": _iso(agora)}) is True


def test_sem_mudanca_registada_aceita():
    payload = {"sub": "u", "iat": 1}
    assert _token_valido_apos_reset(payload, {"password_changed_at": None}) is True


def test_token_sem_iat_e_rejeitado_quando_ha_mudanca():
    assert _token_valido_apos_reset({"sub": "u"}, {"password_changed_at": _iso(datetime.now(timezone.utc))}) is False


def test_schema_sem_coluna_aceita_mas_avisa_alto(caplog):
    auth._AVISOS_SCHEMA_EMITIDOS.discard("password_changed_at")
    with caplog.at_level(logging.WARNING, logger="services.auth_service"):
        ok = _token_valido_apos_reset({"sub": "u", "iat": 1}, {"username": "u"})
    assert ok is True
    assert any("REVOGACAO DE SESSAO POR RESET INACTIVA" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- get_current_user

@pytest.fixture
def svc(monkeypatch):
    s = AuthService()
    return s


def test_get_current_user_rejeita_token_antigo(svc, monkeypatch):
    token = create_access_token({"sub": "u", "role": "viewer"})
    futuro = datetime.now(timezone.utc) + timedelta(seconds=30)
    monkeypatch.setattr(svc, "_get_user_from_db", lambda n: {"username": "u", "role": "viewer", "disabled": 0,
                                                              "password_changed_at": _iso(futuro)})
    assert asyncio.run(svc.get_current_user(token)) is None


def test_get_current_user_aceita_token_recente(svc, monkeypatch):
    token = create_access_token({"sub": "u", "role": "viewer"})
    passado = datetime.now(timezone.utc) - timedelta(minutes=5)
    monkeypatch.setattr(svc, "_get_user_from_db", lambda n: {"username": "u", "role": "viewer", "disabled": 0,
                                                              "password_changed_at": _iso(passado)})
    user = asyncio.run(svc.get_current_user(token))
    assert user and user["username"] == "u"


# ---------------------------------------------------------------- escrita e SELECT

def test_change_password_grava_password_changed_at(svc, monkeypatch):
    queries = []
    monkeypatch.setattr(auth, "_execute_update", lambda q, p=None: queries.append(q))
    monkeypatch.setattr(auth, "hash_password", lambda p: "h")
    r = asyncio.run(svc.change_password("u", "NovaPass123!"))
    assert r["success"] is True
    assert any("password_changed_at = SYSUTCDATETIME()" in q for q in queries)


def test_select_v13_le_a_coluna():
    assert "password_changed_at" in auth._USER_SELECT_V13
    assert "password_changed_at" not in auth._USER_SELECT_V12
