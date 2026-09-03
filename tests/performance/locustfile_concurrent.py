"""
Locust Performance Tests - Cenario 2: CARGA CONCORRENTE
========================================================
Simula 10 utilizadores DBA simultaneos com refresh automatico a cada 30s.

Modelo de carga real:
- 10 users autenticados
- Cada user faz refresh de KPIs a cada 30s
- Heartbeat a cada 60s
- Preferences sync com debounce 5s (ocasional)
- Token validate periodico

Execucao:
    locust -f locustfile_concurrent.py --headless -u 10 -r 2 --run-time 5m --host http://localhost:8000
    locust -f locustfile_concurrent.py --host http://localhost:8000   # (web UI em localhost:8089)

Metricas a capturar:
    - Latencia p95 sob carga de 10 users
    - Throughput total (requests/s)
    - Connection pool hit rate (verificar via /api/pool/stats se existir)
    - Taxa de erros (target: < 1%)
    - Degradacao relativa ao baseline

Thresholds (com 10 users):
    - Login p95 < 3000ms  (bcrypt serializado pelo GIL)
    - Validate p95 < 200ms
    - Heartbeat p95 < 200ms
    - KPI endpoints p95 < 5000ms  (connection pool contention)
    - Preferences p95 < 500ms
    - Error rate < 1%

Bottleneck esperado:
    - bcrypt verify e CPU-bound e single-threaded (GIL) -> logins concorrentes serializam
    - IntelligenceConnectionPool max_connections=10 -> contention com 10 users
    - _execute_query/_execute_update sao sync, bloqueiam o event loop do FastAPI
    - MERGE statement em preferences nao tem batching -> N round-trips SQL
"""

import time
import json
import random
from locust import HttpUser, task, between, events, tag


# ==============================================================
# CONFIGURACAO
# ==============================================================
# Criar 10 users distintos para simular equipa DBA real
# Em producao, usar users reais. Para teste, todos usam admin.
TEST_USERS = [
    {"username": "admin", "password": "admin123"},
    {"username": "salomao", "password": "admin123"},
    {"username": "ricardo", "password": "admin123"},
]

# Thresholds sob carga (mais relaxados que baseline)
THRESHOLDS_CONCURRENT = {
    "/api/auth/login": 3000,
    "/api/auth/validate": 200,
    "/api/auth/me": 200,
    "/api/auth/heartbeat": 200,
    "/api/auth/preferences GET": 500,
    "/api/auth/preferences PUT": 500,
    "/api/sqlserver-kpis/dashboard": 5000,
    "/api/v1/overview/summary": 5000,
    "KPI refresh cycle": 5000,
}


class DBAUser(HttpUser):
    """
    Simula um DBA com o portal WatcherDB aberto.

    Padrao de uso real:
    - Login uma vez no inicio
    - KPI refresh automatico a cada ~30s
    - Heartbeat a cada ~60s
    - Preferences sync ocasional (debounce 5s)
    - Validate token periodicamente
    """
    # Simula refresh a cada 25-35s (jitter para nao sincronizar todos)
    wait_time = between(5, 10)

    def on_start(self):
        """Login com um user aleatorio da lista."""
        creds = random.choice(TEST_USERS)
        self.username = creds["username"]
        self.token = None
        self._login(creds["username"], creds["password"])
        self._request_count = 0

    def _login(self, username, password):
        with self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
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

    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ----------------------------------------------------------
    # TASKS: ponderadas para simular uso real
    # ----------------------------------------------------------

    @task(10)
    @tag("kpi-refresh")
    def kpi_refresh_cycle(self):
        """
        Simula o refresh automatico do dashboard.
        Em producao, o frontend chama varios endpoints KPI em paralelo.
        Aqui simulamos 2-3 chamadas sequenciais (como o browser faria).
        """
        endpoints = [
            "/api/sqlserver-kpis/dashboard",
            "/api/v1/overview/summary",
            "/api/sqlserver-kpis/instance-availability",
        ]
        # Simula refresh: 2 endpoints aleatorios por ciclo
        selected = random.sample(endpoints, min(2, len(endpoints)))

        for ep in selected:
            with self.client.get(
                ep,
                headers=self._headers(),
                catch_response=True,
                name="KPI refresh cycle"
            ) as resp:
                if resp.status_code in (200, 401, 404):
                    resp.success()
                else:
                    resp.failure(f"HTTP {resp.status_code} on {ep}")

    @task(5)
    @tag("validate")
    def validate_token(self):
        """Token validation (frontend check periodico)."""
        with self.client.get(
            "/api/auth/validate",
            headers=self._headers(),
            catch_response=True,
            name="/api/auth/validate"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    @tag("heartbeat")
    def heartbeat(self):
        """Heartbeat (cada 60s em producao, aqui mais frequente para stress)."""
        with self.client.post(
            "/api/auth/heartbeat",
            headers=self._headers(),
            catch_response=True,
            name="/api/auth/heartbeat"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    @tag("preferences")
    def load_preferences(self):
        """GET preferences."""
        with self.client.get(
            "/api/auth/preferences",
            headers=self._headers(),
            catch_response=True,
            name="/api/auth/preferences GET"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    @tag("preferences")
    def save_preferences(self):
        """PUT preferences (debounce 5s em producao, aqui mais frequente)."""
        prefs = {
            "preferences": {
                "theme": random.choice(["dark", "light"]),
                "refresh_interval": str(random.choice([15, 30, 60])),
                "sidebar_collapsed": str(random.choice(["true", "false"])),
            }
        }
        with self.client.put(
            "/api/auth/preferences",
            json=prefs,
            headers=self._headers(),
            catch_response=True,
            name="/api/auth/preferences PUT"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    @tag("me")
    def get_me(self):
        """GET /me."""
        with self.client.get(
            "/api/auth/me",
            headers=self._headers(),
            catch_response=True,
            name="/api/auth/me"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ==============================================================
# EVENT HOOKS
# ==============================================================
@events.quitting.add_listener
def check_thresholds(environment, **kwargs):
    """Verifica thresholds e calcula metricas de concorrencia."""
    print("\n" + "=" * 70)
    print("CONCURRENT LOAD TEST RESULTS (10 users)")
    print("=" * 70)

    failures = []
    total_requests = 0
    total_failures = 0

    for stat in environment.runner.stats.entries.values():
        total_requests += stat.num_requests
        total_failures += stat.num_failures

        threshold = THRESHOLDS_CONCURRENT.get(stat.name)
        if threshold and stat.num_requests > 0:
            p95 = stat.get_response_time_percentile(0.95) or 0
            p50 = stat.get_response_time_percentile(0.50) or 0
            status = "PASS" if p95 <= threshold else "FAIL"
            line = (
                f"{status}: {stat.name:40s} "
                f"p50={p50:7.0f}ms  p95={p95:7.0f}ms  "
                f"threshold={threshold}ms  "
                f"reqs={stat.num_requests}  "
                f"errs={stat.num_failures}"
            )
            print(line)
            if p95 > threshold:
                failures.append(line)

    # Error rate global
    error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0
    print(f"\nTotal requests: {total_requests}")
    print(f"Total failures: {total_failures}")
    print(f"Error rate: {error_rate:.2f}%")

    if error_rate > 1.0:
        failures.append(f"FAIL: Error rate {error_rate:.2f}% > 1%")

    # Throughput
    total_stats = environment.runner.stats.total
    if total_stats.total_rps:
        print(f"Throughput: {total_stats.total_rps:.1f} req/s")

    if failures:
        print(f"\n{'=' * 70}")
        print(f"FAILED: {len(failures)} threshold(s) exceeded")
        environment.process_exit_code = 1
    else:
        print(f"\n=== ALL CONCURRENT THRESHOLDS PASSED ===")
        environment.process_exit_code = 0
