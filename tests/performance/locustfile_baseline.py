"""
Locust Performance Tests - Cenario 1: BASELINE
================================================
Mede latencia individual de cada endpoint critico do WatcherDB V3.1.

Objectivo:
- Login (bcrypt verify + SQL query): p95 < 2s
- Token validate: p95 < 100ms
- GET /me: p95 < 150ms
- GET /preferences: p95 < 200ms
- PUT /preferences: p95 < 300ms
- Heartbeat: p95 < 100ms
- KPI endpoints: p95 < 3s

Execucao:
    locust -f locustfile_baseline.py --headless -u 1 -r 1 --run-time 2m --host http://localhost:8000
    locust -f locustfile_baseline.py --host http://localhost:8000   # (web UI em localhost:8089)

Metricas capturadas:
    - Latencia p50, p95, p99 por endpoint
    - Taxa de erros (target: 0%)
    - Requests/segundo

Threshold pass/fail:
    - Login p95 < 2000ms  (bcrypt cost factor 12 = ~250ms CPU)
    - Validate p95 < 100ms  (JWT decode in-memory)
    - Preferences GET p95 < 200ms  (1 SQL query)
    - Preferences PUT p95 < 300ms  (MERGE per key)
    - Heartbeat p95 < 100ms  (in-memory dict)
    - KPI dashboard p95 < 3000ms  (multi-server queries)

Bottleneck esperado:
    - Login: bcrypt.verify e CPU-bound (~200-400ms por verify com cost=12)
    - Preferences PUT: MERGE statement, 1 round-trip SQL por chave
"""

import time
import json
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner


# ==============================================================
# CONFIGURACAO - ajustar para o ambiente
# ==============================================================
TEST_USER = "admin"
TEST_PASSWORD = "admin123"

# Thresholds de aceitacao (milissegundos)
THRESHOLDS = {
    "/api/auth/login": 2000,
    "/api/auth/validate": 100,
    "/api/auth/me": 150,
    "/api/auth/heartbeat": 100,
    "/api/auth/preferences GET": 200,
    "/api/auth/preferences PUT": 300,
    "/api/sqlserver-kpis/dashboard": 3000,
    "/api/v1/overview/summary": 3000,
}


class BaselineUser(HttpUser):
    """
    Simula 1 utilizador DBA que executa cada operacao sequencialmente.
    wait_time entre 1-3s para nao sobrecarregar num teste baseline.
    """
    wait_time = between(1, 3)

    def on_start(self):
        """Login e guardar token JWT."""
        self.token = None
        self._do_login()

    def _do_login(self):
        """Autentica e guarda o token."""
        with self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
            catch_response=True,
            name="/api/auth/login"
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    self.token = data.get("access_token")
                    resp.success()
                else:
                    resp.failure(f"Login failed: {data.get('error')}")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    def _auth_headers(self):
        """Retorna headers com Bearer token."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ----------------------------------------------------------
    # TASKS: cada endpoint critico
    # ----------------------------------------------------------
    @task(3)
    def validate_token(self):
        """GET /api/auth/validate - JWT decode + DB lookup."""
        with self.client.get(
            "/api/auth/validate",
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/auth/validate"
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("valid"):
                    resp.success()
                else:
                    resp.failure("Token invalid")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def get_me(self):
        """GET /api/auth/me - user profile."""
        with self.client.get(
            "/api/auth/me",
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/auth/me"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def get_preferences(self):
        """GET /api/auth/preferences - load user prefs from SQL."""
        with self.client.get(
            "/api/auth/preferences",
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/auth/preferences GET"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def save_preferences(self):
        """PUT /api/auth/preferences - save 3 keys (simula debounce save)."""
        prefs = {
            "preferences": {
                "theme": "dark",
                "refresh_interval": "30",
                "language": "pt",
            }
        }
        with self.client.put(
            "/api/auth/preferences",
            json=prefs,
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/auth/preferences PUT"
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    resp.success()
                else:
                    resp.failure(f"Save failed: {data}")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(5)
    def heartbeat(self):
        """POST /api/auth/heartbeat - in-memory, deve ser < 100ms."""
        with self.client.post(
            "/api/auth/heartbeat",
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/auth/heartbeat"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def kpi_dashboard(self):
        """GET /api/sqlserver-kpis/dashboard - heavy, multi-server."""
        with self.client.get(
            "/api/sqlserver-kpis/dashboard",
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/sqlserver-kpis/dashboard"
        ) as resp:
            if resp.status_code in (200, 401):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def overview_summary(self):
        """GET /api/v1/overview/summary - pre-calculated data."""
        with self.client.get(
            "/api/v1/overview/summary",
            headers=self._auth_headers(),
            catch_response=True,
            name="/api/v1/overview/summary"
        ) as resp:
            if resp.status_code in (200, 401, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def login_cycle(self):
        """POST /api/auth/login - full bcrypt verify cycle."""
        self._do_login()


# ==============================================================
# EVENT HOOKS: verificar thresholds no final
# ==============================================================
@events.quitting.add_listener
def check_thresholds(environment, **kwargs):
    """Verifica se os p95 estao dentro dos thresholds. Exit code 1 se falhar."""
    failures = []

    for stat in environment.runner.stats.entries.values():
        threshold = THRESHOLDS.get(stat.name)
        if threshold and stat.num_requests > 0:
            p95 = stat.get_response_time_percentile(0.95) or 0
            if p95 > threshold:
                failures.append(
                    f"FAIL: {stat.name} p95={p95:.0f}ms > threshold={threshold}ms"
                )
            else:
                print(f"PASS: {stat.name} p95={p95:.0f}ms <= threshold={threshold}ms")

    if failures:
        for f in failures:
            print(f)
        environment.process_exit_code = 1
    else:
        print("\n=== ALL BASELINE THRESHOLDS PASSED ===")
        environment.process_exit_code = 0
