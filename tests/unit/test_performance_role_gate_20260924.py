# -*- coding: utf-8 -*-
"""P0 (2026-09-24): Performance Module redige por role e exige dba para escrever.

Antes deste lote api/routers/performance.py nao tinha nenhum Depends de role: um viewer lia
sql_text cru dos investigators e escrevia em performance_action_history.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import api.role_redaction as rr
from api.routers import performance as perf_mod
from api.routers import live_monitoring as live_mod


RAW_SQL = "SELECT TOP 20 * FROM dbo.Contas WHERE Saldo < 0"


class _FakeResult:
    def to_dict(self):
        return {
            "investigator_id": "cpu_queries",
            "severity": "warning",
            "steps": [
                {
                    "name": "top_cpu",
                    "rows": [
                        {"sql_text": RAW_SQL, "login_name": "svc_core", "host_name": "APP01",
                         "program_name": ".Net SqlClient Data Provider", "total_cpu_ms": 4200},
                    ],
                },
                {"name": "deadlock", "rows": [{"inputbuf": RAW_SQL, "hostname": "APP02", "clientapp": "Core"}]},
            ],
            "sql_text": "",  # vazio nao e' redigido (nada a esconder)
        }


class _FakeInvestigator:
    async def investigate(self, instance, triggered_by="manual"):
        return _FakeResult()


class _FakeAuthService:
    """O gate de escrita passa por _require_auth, que valida um TOKEN (nao o request.state).
    Aqui o token e' o proprio role vindo do header x-test-role."""

    async def get_current_user(self, token):
        return {"username": "t", "role": token} if token else None

    def _get_user_from_db(self, username):
        return None


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(perf_mod, "get_investigator", lambda _id: _FakeInvestigator())

    async def _no_persist(result):
        return None
    monkeypatch.setattr(perf_mod, "_persist_investigation", _no_persist)

    from api.routers import auth_compat
    monkeypatch.setattr(auth_compat, "_get_token_from_request", lambda req: req.headers.get("x-test-role") or None)
    monkeypatch.setattr(auth_compat, "get_auth_service", lambda: _FakeAuthService())

    app = FastAPI()

    @app.middleware("http")
    async def _fake_auth(request: Request, call_next):
        role = request.headers.get("x-test-role")
        request.state.user = {"username": "t", "role": role} if role else None
        return await call_next(request)

    app.include_router(perf_mod.router)
    return TestClient(app)


def _investigate(client, role):
    return client.post("/api/v1/performance/investigate/SRV01/cpu_queries", headers={"x-test-role": role})


def test_viewer_ve_hash_do_sql_e_identidades_ocultas(client):
    r = _investigate(client, "viewer")
    assert r.status_code == 200
    body = r.json()
    linha = body["steps"][0]["rows"][0]
    assert linha["sql_text"].startswith(rr.REDACTED + " #") and RAW_SQL not in json.dumps(body)
    assert len(linha["sql_text"].split("#")[-1]) == 12
    assert linha["login_name"] == rr.REDACTED
    assert linha["host_name"] == rr.REDACTED
    assert linha["program_name"] == rr.REDACTED
    assert linha["total_cpu_ms"] == 4200  # metricas passam intactas
    dl = body["steps"][1]["rows"][0]
    assert dl["inputbuf"].startswith(rr.REDACTED) and dl["hostname"] == rr.REDACTED and dl["clientapp"] == rr.REDACTED
    assert body["sql_text"] == ""


def test_hash_e_estavel_para_o_mesmo_sql(client):
    a = _investigate(client, "viewer").json()["steps"][0]["rows"][0]["sql_text"]
    b = _investigate(client, "viewer").json()["steps"][0]["rows"][0]["sql_text"]
    assert a == b


@pytest.mark.parametrize("role", ["dba", "admin"])
def test_dba_e_admin_veem_tudo(client, role):
    linha = _investigate(client, role).json()["steps"][0]["rows"][0]
    assert linha["sql_text"] == RAW_SQL and linha["login_name"] == "svc_core"


def test_viewer_nao_escreve_action_history_403_antes_do_corpo(client):
    # Corpo vazio de proposito: o gate tem de responder 403 antes de o Pydantic dar 422.
    r = client.post("/api/v1/performance/action-history", headers={"x-test-role": "viewer"}, json={})
    assert r.status_code == 403


def test_viewer_nao_gera_ticket_403_antes_do_corpo(client):
    r = client.post("/api/v1/performance/ticket-response", headers={"x-test-role": "viewer"}, json={})
    assert r.status_code == 403


def test_dba_escreve_action_history(client, monkeypatch):
    import api.connection_pool as cp
    chamadas = []
    monkeypatch.setattr(cp, "execute_on_intelligence", lambda q, params=None: chamadas.append(params))
    rec = {"instance": "SRV01", "database_name": "db", "object_name": "t", "action_type": "index",
           "action_sql": "CREATE INDEX ix ON t(c)", "applied_by": "dba1"}
    r = client.post("/api/v1/performance/action-history", headers={"x-test-role": "dba"}, json=rec)
    assert r.status_code == 200 and r.json().get("success") is True and len(chamadas) == 1


def test_sem_token_nao_escreve(client):
    r = client.post("/api/v1/performance/action-history", json={})
    assert r.status_code in (401, 403)


def test_guarda_os_dois_routers_usam_a_mesma_redaccao():
    assert perf_mod.router.route_class is rr.RoleRedactingRoute
    assert live_mod.router.route_class is rr.RoleRedactingRoute
    assert live_mod._redact_node is rr.redact_node
    # o conjunto do LIVE continua coberto pelo partilhado
    for campo in ("sql_text", "full_sql_text", "full_query_text", "blocked_sql", "blocker_sql"):
        assert campo in rr.SQL_FIELDS
    for campo in ("login_name", "host_name", "client_host", "program_name", "blocked_login", "blocker_host"):
        assert campo in rr.IDENTITY_FIELDS
