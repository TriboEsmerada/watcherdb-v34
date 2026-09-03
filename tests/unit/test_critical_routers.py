"""
Smoke tests para 3 routers criticos que tinham zero unit tests antes do
audit 2026-04-22 (qa-specialist finding):
    - api/routers/copilot.py
    - api/routers/network_diagnostics.py
    - api/routers/disk_unallocated.py

Cobertura intencional: import + routing estrutura + auth enforcement.
Nao cobre logica de negocio (requer BD real + fixtures complexos —
follow-up work). A enfase aqui e garantir que:
  1. O modulo importa sem excepcao
  2. Os endpoints declarados estao registados no router
  3. O AuthEnforcementMiddleware (P0-3) protege todos estes endpoints
     (chamar sem token retorna 401, nao 404 ou 500)
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures partilhados
# =============================================================================

@pytest.fixture(scope="module")
def app_client():
    """App FastAPI com middleware de auth activo. Requer pyodbc importavel."""
    try:
        watcherdb_main = importlib.import_module("watcherdb_main")
    except Exception as e:
        pytest.skip(f"watcherdb_main nao carregavel no ambiente de test: {e}")
    return TestClient(watcherdb_main.app, raise_server_exceptions=False)


# =============================================================================
# Copilot router — /api/v1/copilot/*
# =============================================================================

class TestCopilotRouter:
    PREFIX = "/api/v1/copilot"

    def test_module_imports_cleanly(self):
        mod = importlib.import_module("api.routers.copilot")
        assert hasattr(mod, "router"), "Router nao exportado"

    def test_router_has_expected_endpoints(self):
        mod = importlib.import_module("api.routers.copilot")
        paths = {route.path for route in mod.router.routes}
        # 6 endpoints declarados em S3-15 dispatch (linhas 92,93,107,121,137,167)
        expected_suffixes = {"/status", "/quick-answers", "/insights", "/ask", "/report"}
        for suffix in expected_suffixes:
            assert any(suffix in p for p in paths), f"Endpoint {suffix} nao registado"

    def test_status_requires_auth(self, app_client):
        # Sem token → AuthEnforcementMiddleware (P0-3) deve bloquear com 401
        resp = app_client.get(f"{self.PREFIX}/status")
        assert resp.status_code == 401, (
            f"Copilot /status deveria estar protegido. Obtive {resp.status_code}: "
            f"{resp.json() if resp.headers.get('content-type','').startswith('application/json') else resp.text}"
        )

    def test_ask_requires_auth(self, app_client):
        resp = app_client.post(f"{self.PREFIX}/ask", json={"question": "test"})
        assert resp.status_code == 401, f"Copilot /ask deveria estar protegido. Obtive {resp.status_code}"

    def test_report_requires_auth(self, app_client):
        resp = app_client.post(f"{self.PREFIX}/report", json={})
        assert resp.status_code == 401, f"Copilot /report deveria estar protegido. Obtive {resp.status_code}"


# =============================================================================
# Network Diagnostics router — /api/diagnostics/*
# =============================================================================

class TestNetworkDiagnosticsRouter:
    PREFIX = "/api/diagnostics"

    def test_module_imports_cleanly(self):
        mod = importlib.import_module("api.routers.network_diagnostics")
        assert hasattr(mod, "router")

    def test_router_has_expected_endpoints(self):
        mod = importlib.import_module("api.routers.network_diagnostics")
        paths = {route.path for route in mod.router.routes}
        for suffix in ["/network-test/{server_id}", "/network-test-quick/{server_id}"]:
            assert any(suffix in p for p in paths), f"Endpoint {suffix} nao registado"

    def test_network_test_requires_auth(self, app_client):
        # server_id fake — o 401 sai antes de haver lookup na pool
        resp = app_client.get(f"{self.PREFIX}/network-test/SRV01")
        assert resp.status_code == 401, f"network-test deveria estar protegido. Obtive {resp.status_code}"

    def test_network_test_quick_requires_auth(self, app_client):
        resp = app_client.get(f"{self.PREFIX}/network-test-quick/SRV01")
        assert resp.status_code == 401, f"network-test-quick deveria estar protegido. Obtive {resp.status_code}"


# =============================================================================
# Disk Unallocated router — /disk-unallocated/*
# =============================================================================

class TestDiskUnallocatedRouter:
    PREFIX = "/disk-unallocated"

    def test_module_imports_cleanly(self):
        mod = importlib.import_module("api.routers.disk_unallocated")
        assert hasattr(mod, "router")

    def test_router_has_expected_endpoints(self):
        mod = importlib.import_module("api.routers.disk_unallocated")
        paths = {route.path for route in mod.router.routes}
        # 8 endpoints: /summary, /server/{server_id}, /expansion-opportunities,
        #              /stats, /history/{server_id}, /collect/{server_id},
        #              /collect-batch, /health
        for suffix in [
            "/summary", "/server/{server_id}", "/expansion-opportunities",
            "/stats", "/history/{server_id}", "/collect/{server_id}",
            "/collect-batch", "/health",
        ]:
            assert any(suffix in p for p in paths), f"Endpoint {suffix} nao registado"

    def test_summary_requires_auth(self, app_client):
        resp = app_client.get(f"{self.PREFIX}/summary")
        assert resp.status_code == 401, f"disk-unallocated /summary deveria estar protegido. Obtive {resp.status_code}"

    def test_server_endpoint_requires_auth(self, app_client):
        resp = app_client.get(f"{self.PREFIX}/server/SRV01")
        assert resp.status_code == 401, f"disk-unallocated /server deveria estar protegido. Obtive {resp.status_code}"

    def test_collect_requires_auth(self, app_client):
        resp = app_client.post(f"{self.PREFIX}/collect/SRV01", json={})
        assert resp.status_code == 401, f"disk-unallocated /collect deveria estar protegido. Obtive {resp.status_code}"

    def test_health_requires_auth(self, app_client):
        # Nota: /disk-unallocated/health NAO e o /api/v3/health publico.
        # E um health scoped ao modulo — deve exigir auth.
        resp = app_client.get(f"{self.PREFIX}/health")
        assert resp.status_code == 401, f"disk-unallocated /health deveria estar protegido. Obtive {resp.status_code}"


# =============================================================================
# Cross-router auth regression guard
# =============================================================================

class TestAuthMiddlewareCoverage:
    """Garante que AuthEnforcementMiddleware (P0-3) cobre os 3 routers criticos."""

    @pytest.mark.parametrize("path", [
        "/api/v1/copilot/status",
        "/api/v1/copilot/insights",
        "/api/diagnostics/network-test/SRV01",
        "/disk-unallocated/summary",
        "/disk-unallocated/stats",
    ])
    def test_no_bypass_via_trailing_slash(self, app_client, path):
        # Confirma que pedidos sem token nao passam, independente do trailing slash
        resp1 = app_client.get(path)
        resp2 = app_client.get(path + "/")
        assert resp1.status_code == 401, f"{path} sem token devolveu {resp1.status_code}"
        # Trailing slash pode redireccionar (307) antes de chegar ao middleware,
        # mas o endpoint efectivo deve continuar 401
        assert resp2.status_code in {401, 307, 404}, f"{path}/ sem token devolveu {resp2.status_code}"
