"""Gate permanente do CSRF same-site (lote 2026-09-05).

Politica (watcherdb/core/same_origin.py): em POST/PUT/PATCH/DELETE, `Origin` presente e fora de
{scheme://host} U CORS allow_origins => 403. Origin ausente passa (clientes nao-browser).
Metodos seguros passam sempre.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from watcherdb.core import same_origin
from watcherdb.core.same_origin import SameOriginMiddleware


@pytest.fixture
def client(monkeypatch):
    # CORS allowlist controlada pelo teste (nao depende de config/config.yaml)
    import watcherdb.core.cors as cors

    monkeypatch.setattr(
        cors, "get_cors_config", lambda: {"allow_origins": ["https://portal-aliado.example"]}
    )
    app = FastAPI()
    app.add_middleware(SameOriginMiddleware)

    @app.post("/escrita")
    async def escrita():
        return {"ok": True}

    @app.delete("/escrita")
    async def apaga():
        return {"ok": True}

    @app.get("/leitura")
    async def leitura():
        return {"ok": True}

    return TestClient(app)  # Host: testserver, scheme http


def test_origem_cruzada_em_post_da_403(client):
    r = client.post("/escrita", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Origem nao permitida"


def test_origem_cruzada_em_delete_da_403(client):
    r = client.delete("/escrita", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code == 403


def test_origem_propria_passa(client):
    r = client.post("/escrita", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_origem_propria_case_e_barra_final_passa(client):
    r = client.post("/escrita", headers={"Origin": "HTTP://TestServer/"})
    assert r.status_code == 200


def test_origem_na_allowlist_cors_passa(client):
    r = client.post("/escrita", headers={"Origin": "https://portal-aliado.example"})
    assert r.status_code == 200


def test_sem_origin_passa(client):
    # curl / collectors / k6: sem browser nao ha cookie anexado => sem vector
    r = client.post("/escrita")
    assert r.status_code == 200


def test_origin_null_da_403(client):
    # iframe sandboxed / redirects opacos enviam "null" -- nao e' a nossa origem
    r = client.post("/escrita", headers={"Origin": "null"})
    assert r.status_code == 403


def test_get_com_origem_cruzada_passa(client):
    r = client.get("/leitura", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code == 200


def test_options_com_origem_cruzada_nao_da_403(client):
    r = client.options("/escrita", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code != 403


def test_politica_do_middleware_e_a_mesma_do_depends():
    # O middleware tem de reutilizar as primitivas do modulo, nao reimplementar a politica.
    import inspect

    src = inspect.getsource(SameOriginMiddleware)
    assert "origens_aceites(" in src and "_METODOS_COM_EFEITO" in src and "_normalizar(" in src
    assert same_origin.require_same_origin is not None


def test_middleware_registado_na_app_real():
    try:
        import watcherdb_main
    except Exception as e:  # pragma: no cover - ambiente sem dependencias completas
        pytest.skip(f"watcherdb_main nao carregavel: {e}")
    classes = [m.cls for m in watcherdb_main.app.user_middleware]
    assert SameOriginMiddleware in classes, "SameOriginMiddleware nao esta registado em watcherdb_main.app"
    # Tem de ser mais exterior que o AuthEnforcement (add_middleware: ultimo = mais exterior,
    # e user_middleware guarda por ordem de add => o mais exterior fica no indice 0).
    names = [c.__name__ for c in classes]
    assert names.index("SameOriginMiddleware") < names.index("AuthEnforcementMiddleware")
