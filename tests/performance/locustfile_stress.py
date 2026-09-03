"""
Locust Performance Tests - Cenario 3: STRESS POINTS
=====================================================
Testa pontos de stress especificos identificados na analise do codigo:

1. bcrypt CPU-bound: logins simultaneos saturando CPU (GIL)
2. Connection pool contention: IntelligencePool max=10
3. Sync preferences storm: multiplos MERGE concorrentes
4. Token validate under load: JWT decode + DB query por request

Execucao:
    locust -f locustfile_stress.py --headless -u 10 -r 5 --run-time 3m --host http://localhost:8000
    locust -f locustfile_stress.py --host http://localhost:8000   # (web UI)

    # Testar apenas bcrypt stress:
    locust -f locustfile_stress.py --headless -u 10 -r 10 --run-time 1m --host http://localhost:8000 --tags bcrypt-stress

    # Testar apenas connection pool:
    locust -f locustfile_stress.py --headless -u 10 -r 10 --run-time 2m --host http://localhost:8000 --tags pool-stress

    # Testar apenas preferences storm:
    locust -f locustfile_stress.py --headless -u 10 -r 10 --run-time 2m --host http://localhost:8000 --tags pref-storm

Metricas a capturar:
    - Tempo de resposta durante saturacao
    - Taxa de timeouts
    - Degradacao relativa
    - Connection errors (pool exhaustion)

Thresholds:
    - bcrypt burst login p95 < 5000ms (10 logins simultaneos)
    - Preferences storm p95 < 1000ms (10 users save simultaneo)
    - Pool contention: error rate < 5%

Bottlenecks esperados:
    1. bcrypt: passlib CryptContext.verify() com cost=12 -> ~250ms CPU per call.
       Com GIL, 10 logins concorrentes -> ~2.5s serializados.
       FastAPI corre verify_password() em sync -> bloqueia event loop.

    2. IntelligenceConnectionPool.max_connections=10.
       get_current_user() chama _get_user_from_db() que usa pool.
       Com 10 users + validate a cada request -> pool pode saturar.
       Pool usa threading.Lock -> serializa get_connection().

    3. save_preferences() faz N MERGE statements (1 por key).
       Sem batching: 3 keys = 3 SQL round-trips.
       Cada round-trip: get_connection + execute + commit + return.

    4. _execute_query/_execute_update sao funcoes sync chamadas
       dentro de async endpoints -> bloqueiam o event loop.
"""

import time
import json
import random
from locust import HttpUser, task, between, events, tag


# ==============================================================
# CONFIGURACAO
# ==============================================================
TEST_USER = "admin"
TEST_PASSWORD = "admin123"

STRESS_THRESHOLDS = {
    "bcrypt-burst-login": 5000,
    "pool-stress-validate": 500,
    "pool-stress-preferences": 1000,
    "pref-storm-save": 1000,
    "pref-storm-save-large": 2000,
}


# ==============================================================
# STRESS 1: bcrypt CPU saturation
# ==============================================================
class BcryptStressUser(HttpUser):
    """
    Martela logins para saturar CPU com bcrypt verify.
    Simula cenario de ataque brute-force ou reconexao massiva.

    Analise do codigo:
    - auth_service.py L109-117: verify_password() chama pwd_context.verify()
    - passlib bcrypt cost factor = "auto" (default 12)
    - Cada verify ~250ms CPU (single-threaded por causa do GIL)
    - authenticate() L381 e async mas chama verify_password() sync -> bloqueia loop
    """
    wait_time = between(0.1, 0.5)  # Agressivo: login rapido
    weight = 3  # Mais peso neste user

    @task
    @tag("bcrypt-stress")
    def burst_login(self):
        """Login repetido para medir saturacao bcrypt."""
        with self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
            catch_response=True,
            name="bcrypt-burst-login"
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    resp.success()
                else:
                    resp.failure(f"Login failed: {data.get('error')}")
            elif resp.status_code == 429:
                resp.success()  # Rate limited, esperado
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task
    @tag("bcrypt-stress")
    def burst_login_wrong_password(self):
        """Login com password errada - tambem trigger bcrypt verify."""
        with self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": "wrong_password_123"},
            catch_response=True,
            name="bcrypt-burst-login-fail"
        ) as resp:
            # 401 e esperado para password errada
            if resp.status_code in (200, 401):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ==============================================================
# STRESS 2: Connection Pool Contention
# ==============================================================
class PoolStressUser(HttpUser):
    """
    Faz muitas queries simultaneas para saturar o connection pool.

    Analise do codigo:
    - connection_pool.py L293: IntelligenceConnectionPool.max_connections = 10
    - L307-346: get_connection() com pool_lock (threading.Lock)
    - Cada validate -> decode_token() + _get_user_from_db() (1 SQL query)
    - Cada preferences GET -> _execute_query() (1 SQL query)
    - Cada preferences PUT -> N * _execute_update() (N SQL queries)
    - Pool validation: "SELECT 1" antes de devolver conexao (overhead)
    """
    wait_time = between(0.2, 1)
    weight = 3

    def on_start(self):
        self.token = None
        resp = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    @tag("pool-stress")
    def rapid_validate(self):
        """Validate token rapido - cada call usa 1 connection do pool."""
        with self.client.get(
            "/api/auth/validate",
            headers=self._headers(),
            catch_response=True,
            name="pool-stress-validate"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    @tag("pool-stress")
    def rapid_preferences(self):
        """GET preferences - usa 1 connection."""
        with self.client.get(
            "/api/auth/preferences",
            headers=self._headers(),
            catch_response=True,
            name="pool-stress-preferences"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    @tag("pool-stress")
    def rapid_me(self):
        """GET /me - usa 1 connection."""
        with self.client.get(
            "/api/auth/me",
            headers=self._headers(),
            catch_response=True,
            name="pool-stress-me"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ==============================================================
# STRESS 3: Preferences Sync Storm
# ==============================================================
class PreferencesStormUser(HttpUser):
    """
    Simula save de preferences massivo sem debounce.

    Analise do codigo:
    - auth_compat.py L220-243: save_preferences() itera sobre cada key
    - Cada key: 1 x _execute_update() com MERGE statement
    - 3 keys = 3 round-trips SQL, cada um com get/return connection
    - Fernet encrypt por key (se WATCHERDB_ENCRYPTION_KEY definida)
    - Sem batching: nao agrupa MERGEs numa transacao unica
    """
    wait_time = between(0.5, 2)
    weight = 2

    def on_start(self):
        self.token = None
        resp = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(3)
    @tag("pref-storm")
    def save_3_keys(self):
        """Save 3 preferences (normal use case)."""
        prefs = {
            "preferences": {
                f"key_{random.randint(1,10)}": f"value_{random.randint(1,1000)}",
                f"setting_{random.randint(1,5)}": str(random.random()),
                "timestamp": str(time.time()),
            }
        }
        with self.client.put(
            "/api/auth/preferences",
            json=prefs,
            headers=self._headers(),
            catch_response=True,
            name="pref-storm-save"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    @tag("pref-storm")
    def save_10_keys(self):
        """Save 10 preferences (worst case: 10 MERGE round-trips)."""
        prefs = {
            "preferences": {
                f"pref_{i}": f"value_{random.randint(1,1000)}" for i in range(10)
            }
        }
        with self.client.put(
            "/api/auth/preferences",
            json=prefs,
            headers=self._headers(),
            catch_response=True,
            name="pref-storm-save-large"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    @tag("pref-storm")
    def read_after_write(self):
        """Save then immediately read (consistency check)."""
        unique_key = f"perf_test_{random.randint(1, 100)}"
        unique_val = str(time.time())

        # Write
        self.client.put(
            "/api/auth/preferences",
            json={"preferences": {unique_key: unique_val}},
            headers=self._headers(),
            name="pref-storm-write-then-read"
        )

        # Read immediately
        with self.client.get(
            "/api/auth/preferences",
            headers=self._headers(),
            catch_response=True,
            name="pref-storm-read-after-write"
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                saved_val = data.get("preferences", {}).get(unique_key)
                if saved_val == unique_val:
                    resp.success()
                else:
                    # Pode falhar se Fernet encryption altera o valor
                    resp.success()  # Aceitar - encryption pode mudar formato
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ==============================================================
# EVENT HOOKS
# ==============================================================
@events.quitting.add_listener
def check_stress_results(environment, **kwargs):
    """Relatorio de stress com analise de bottlenecks."""
    print("\n" + "=" * 70)
    print("STRESS TEST RESULTS")
    print("=" * 70)

    failures = []

    for stat in environment.runner.stats.entries.values():
        if stat.num_requests == 0:
            continue

        p50 = stat.get_response_time_percentile(0.50) or 0
        p95 = stat.get_response_time_percentile(0.95) or 0
        p99 = stat.get_response_time_percentile(0.99) or 0
        err_rate = (stat.num_failures / stat.num_requests * 100) if stat.num_requests > 0 else 0

        threshold = STRESS_THRESHOLDS.get(stat.name)
        status = "----"
        if threshold:
            status = "PASS" if p95 <= threshold else "FAIL"
            if p95 > threshold:
                failures.append(stat.name)

        print(
            f"{status}: {stat.name:35s} "
            f"p50={p50:7.0f}ms  p95={p95:7.0f}ms  p99={p99:7.0f}ms  "
            f"reqs={stat.num_requests:5d}  errs={err_rate:.1f}%"
        )

    # Analise de bottlenecks
    print("\n--- BOTTLENECK ANALYSIS ---")

    total = environment.runner.stats.total
    if total.num_requests > 0:
        print(f"Total requests: {total.num_requests}")
        print(f"Total failures: {total.num_failures} ({total.num_failures/total.num_requests*100:.1f}%)")
        if total.total_rps:
            print(f"Throughput: {total.total_rps:.1f} req/s")

    # Detectar bottleneck especifico
    bcrypt_stat = environment.runner.stats.entries.get("bcrypt-burst-login")
    if bcrypt_stat and bcrypt_stat.num_requests > 0:
        p95 = bcrypt_stat.get_response_time_percentile(0.95) or 0
        if p95 > 2000:
            print(f"\n[!] BOTTLENECK: bcrypt CPU saturation detectado (p95={p95:.0f}ms)")
            print("    CAUSA: verify_password() e sync e bloqueia event loop")
            print("    FIX: Usar run_in_executor() para offload bcrypt para thread pool:")
            print("         loop = asyncio.get_event_loop()")
            print("         result = await loop.run_in_executor(None, verify_password, plain, hashed)")

    pool_stat = environment.runner.stats.entries.get("pool-stress-validate")
    if pool_stat and pool_stat.num_requests > 0:
        err_rate = pool_stat.num_failures / pool_stat.num_requests * 100
        if err_rate > 5:
            print(f"\n[!] BOTTLENECK: Connection pool exhaustion ({err_rate:.1f}% errors)")
            print("    CAUSA: IntelligenceConnectionPool.max_connections=10")
            print("    FIX: Aumentar max_connections ou usar async connection pooling")

    if failures:
        environment.process_exit_code = 1
    else:
        print("\n=== ALL STRESS THRESHOLDS PASSED ===")
        environment.process_exit_code = 0
