"""Gate P4 ronda 3: /api/v3/health e' publico (o instalador depende do 200) mas o corpo anonimo
nao expoe `auth` nem `real_data_servers`; com sessao valida expoe ambos."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _FakeSvc:
    def __init__(self, user):
        self._user = user

    async def get_current_user(self, token):
        return self._user


@pytest.fixture
def main(monkeypatch):
    try:
        import watcherdb_main
    except Exception as e:  # pragma: no cover
        pytest.skip(f"watcherdb_main nao carregavel: {e}")
    import services.auth_service as auth
    # sondagem da coluna sem BD
    monkeypatch.setattr(auth, "_execute_query", lambda q, p=None: [{"password_changed_at": None}])
    return watcherdb_main


def test_anonimo_recebe_200_sem_campos_sensiveis(main):
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/api/v3/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "status" in body
    assert "auth" not in body
    assert "real_data_servers" not in body


def test_sessao_valida_recebe_auth_e_frota(main, monkeypatch):
    from services.auth_service import create_access_token

    monkeypatch.setattr(main, "_auth_get_service", lambda: _FakeSvc({"username": "u", "role": "viewer"}))
    token = create_access_token({"sub": "u", "role": "viewer"})
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/api/v3/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "real_data_servers" in body
    assert body["auth"]["reset_revocation"] in ("active", "inactive", "unknown")


def test_token_invalido_nao_da_401_e_recebe_corpo_anonimo(main, monkeypatch):
    monkeypatch.setattr(main, "_auth_get_service", lambda: _FakeSvc(None))
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/api/v3/health", headers={"Authorization": "Bearer lixo"})
    assert r.status_code == 200
    assert "auth" not in r.json()
