"""Gate permanente: o login emite o cookie de sessao (lote 2026-09-05).

Ate' 2026-09-05 o handler testava result.get("token") e o servico devolvia "access_token":
o cookie HttpOnly nunca era emitido e o fallback por cookie era codigo morto. Este teste
falha se a chave voltar a divergir.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _FakeAuthService:
    def __init__(self, ok: bool):
        self.ok = ok

    async def authenticate(self, username, password, ip=None):
        if not self.ok:
            return {"success": False, "error": "Credenciais invalidas"}
        return {
            "success": True,
            "access_token": "tok-de-teste",
            "token_type": "bearer",
            "expires_in": 60,
            "user": {"username": username, "role": "viewer", "auth_method": "local"},
        }


@pytest.fixture
def app_client(monkeypatch):
    try:
        import watcherdb_main
    except Exception as e:  # pragma: no cover
        pytest.skip(f"watcherdb_main nao carregavel: {e}")
    import api.routers.auth_compat as auth_compat

    # Sem BD: a consulta de must_change_password devolve vazio.
    monkeypatch.setattr(auth_compat, "_execute_query", lambda *a, **k: [])
    # Sem rate-limit: outros testes da suite tambem batem no /login com o mesmo IP.
    monkeypatch.setattr(auth_compat.limiter, "enabled", False, raising=False)

    def _make(ok: bool):
        monkeypatch.setattr(auth_compat, "get_auth_service", lambda: _FakeAuthService(ok))
        return TestClient(watcherdb_main.app, raise_server_exceptions=False)

    return _make


def _set_cookie_header(resp) -> str:
    return "; ".join(v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie")


def test_login_ok_emite_cookie_httponly_lax(app_client):
    client = app_client(ok=True)
    r = client.post("/api/auth/login", json={"username": "qa_viewer", "password": "x"})
    assert r.status_code == 200, r.text
    assert r.json().get("access_token") == "tok-de-teste"
    assert r.cookies.get("access_token") == "tok-de-teste"
    sc = _set_cookie_header(r).lower()
    assert "httponly" in sc
    assert "samesite=lax" in sc
    assert "path=/" in sc


def test_login_falhado_nao_emite_cookie(app_client):
    client = app_client(ok=False)
    r = client.post("/api/auth/login", json={"username": "qa_viewer", "password": "errada"})
    assert r.status_code == 401
    assert r.cookies.get("access_token") is None
    assert "access_token" not in _set_cookie_header(r).lower()


def test_logout_apaga_cookie(app_client):
    client = app_client(ok=True)
    client.post("/api/auth/login", json={"username": "qa_viewer", "password": "x"})
    r = client.post("/api/auth/logout")
    sc = _set_cookie_header(r).lower()
    # delete_cookie => Set-Cookie access_token=""; expires no passado / max-age=0
    assert "access_token=" in sc
    assert ("max-age=0" in sc) or ("expires=" in sc)
