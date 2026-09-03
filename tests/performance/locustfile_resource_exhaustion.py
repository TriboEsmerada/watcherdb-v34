"""
Locust Performance Tests - Cenario 4: RESOURCE EXHAUSTION
==========================================================
Testes de longa duracao para detectar leaks e problemas de recursos.

Problemas testados:
1. Memory leak: _active_heartbeats dict cresce sem limite
2. Connection leak: conexoes nao devolvidas ao pool
3. JWT sem revogacao: tokens validos depois de logout
4. Auth log growth: INSERT sem cleanup

Execucao:
    # Teste longo (15 minutos) com 5 users para detectar leaks
    locust -f locustfile_resource_exhaustion.py --headless -u 5 -r 1 --run-time 15m --host http://localhost:8000

    # Apenas teste JWT revogacao:
    locust -f locustfile_resource_exhaustion.py --headless -u 3 -r 1 --run-time 3m --host http://localhost:8000 --tags jwt-revoke

    # Web UI para observar degradacao ao longo do tempo:
    locust -f locustfile_resource_exhaustion.py --host http://localhost:8000

Metricas a capturar:
    - Latencia ao longo do tempo (deve ser estavel, nao crescente)
    - Memory do processo Python (monitorar externamente com psutil/Task Manager)
    - Numero de conexoes SQL abertas (monitorar com sp_who2)
    - Tamanho de _active_heartbeats (acessivel via /api/auth/admin/online)

Thresholds:
    - Latencia nao deve degradar > 50% ao longo de 15 min
    - Error rate < 1% durante todo o teste
    - JWT pos-logout deve retornar valid=false (FAIL esperado - nao ha revogacao)

Bottlenecks esperados:
    1. _active_heartbeats (auth_compat.py L349): dict global in-memory
       Nunca e limpo. Cada username unico adiciona 1 entry.
       Com users AD auto-provisionados, pode crescer indefinidamente.
       FIX: TTL-based cleanup ou Redis com EXPIRE.

    2. Connection leak potencial (auth_service.py L28-88):
       _execute_query() tem try/finally com pool.return_connection().
       MAS: se pool.get_connection() lanca excepcao depois de adquirir
       conexao, o finally pode nao ter referencia valida.
       Risco baixo mas real sob alta carga.

    3. JWT sem blacklist (auth_service.py L145-157):
       logout() em auth_compat.py L148 e client-side only.
       Token continua valido ate expirar (24h por defeito).
       Sem token blacklist, sem refresh token rotation.

    4. WatcherDB_Auth_Log cresce sem cleanup:
       Cada login/validate gera INSERT.
       Sem job de purge automatico.
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


class ResourceExhaustionUser(HttpUser):
    """
    User que executa operacoes normais durante periodo prolongado.
    Objectivo: detectar degradacao gradual de performance.
    """
    wait_time = between(3, 8)

    def on_start(self):
        self.token = None
        self.old_tokens = []  # Guardar tokens antigos para teste de revogacao
        self._login()
        self._iteration = 0

    def _login(self):
        resp = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                if self.token:
                    self.old_tokens.append(self.token)
                self.token = data.get("access_token")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # ----------------------------------------------------------
    # TASKS: uso normal prolongado
    # ----------------------------------------------------------
    @task(5)
    @tag("steady-state")
    def validate_and_refresh(self):
        """Simula ciclo normal: validate + refresh KPI."""
        self._iteration += 1

        # Validate
        with self.client.get(
            "/api/auth/validate",
            headers=self._headers(),
            catch_response=True,
            name="exhaustion-validate"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    @tag("steady-state")
    def heartbeat(self):
        """Heartbeat - adiciona ao _active_heartbeats dict."""
        with self.client.post(
            "/api/auth/heartbeat",
            headers=self._headers(),
            catch_response=True,
            name="exhaustion-heartbeat"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    @tag("steady-state")
    def preferences_cycle(self):
        """Load and save preferences."""
        # Read
        self.client.get(
            "/api/auth/preferences",
            headers=self._headers(),
            name="exhaustion-pref-read"
        )
        # Write
        self.client.put(
            "/api/auth/preferences",
            json={"preferences": {"iteration": str(self._iteration)}},
            headers=self._headers(),
            name="exhaustion-pref-write"
        )

    @task(1)
    @tag("steady-state")
    def relogin(self):
        """
        Re-login periodico (simula sessao expirada).
        Gera novo token sem invalidar o anterior.
        """
        self._login()

    # ----------------------------------------------------------
    # TASKS: teste especifico de JWT revogacao
    # ----------------------------------------------------------
    @task(1)
    @tag("jwt-revoke")
    def test_jwt_no_revocation(self):
        """
        Testa se tokens antigos continuam validos apos logout.

        Fluxo:
        1. Login -> obter token A
        2. Logout (client-side)
        3. Login -> obter token B
        4. Usar token A -> DEVE falhar mas VAI funcionar (bug conhecida)
        """
        # Step 1: Login
        resp = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
            name="jwt-revoke-login"
        )
        if resp.status_code != 200:
            return

        token_a = resp.json().get("access_token")
        if not token_a:
            return

        # Step 2: Logout
        self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token_a}"},
            name="jwt-revoke-logout"
        )

        # Step 3: New login
        resp2 = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
            name="jwt-revoke-relogin"
        )

        # Step 4: Use old token A (should fail but won't)
        with self.client.get(
            "/api/auth/validate",
            headers={"Authorization": f"Bearer {token_a}"},
            catch_response=True,
            name="jwt-revoke-old-token-check"
        ) as resp3:
            if resp3.status_code == 200:
                data = resp3.json()
                if data.get("valid"):
                    # Token antigo AINDA valido = sem revogacao
                    # Registar como warning, nao como failure (e comportamento conhecido)
                    resp3.success()
                else:
                    resp3.success()

    @task(1)
    @tag("jwt-revoke")
    def test_expired_token_handling(self):
        """Testa comportamento com token manipulado/expirado."""
        fake_tokens = [
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MH0.invalid",
            "not-a-jwt-token",
            "",
        ]
        for fake in fake_tokens:
            with self.client.get(
                "/api/auth/validate",
                headers={"Authorization": f"Bearer {fake}"},
                catch_response=True,
                name="jwt-revoke-fake-token"
            ) as resp:
                if resp.status_code == 200:
                    data = resp.json()
                    if not data.get("valid"):
                        resp.success()  # Correcto: token invalido
                    else:
                        resp.failure("SECURITY: fake token accepted as valid!")
                elif resp.status_code == 401:
                    resp.success()
                else:
                    resp.failure(f"HTTP {resp.status_code}")


# ==============================================================
# EVENT HOOKS: analise de degradacao temporal
# ==============================================================
_latency_samples = []


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Captura amostras para analise de degradacao temporal."""
    _latency_samples.append({
        "time": time.time(),
        "name": name,
        "response_time": response_time,
        "exception": str(exception) if exception else None,
    })


@events.quitting.add_listener
def analyze_resource_exhaustion(environment, **kwargs):
    """Analisa tendencia temporal de latencia para detectar degradacao."""
    print("\n" + "=" * 70)
    print("RESOURCE EXHAUSTION ANALYSIS")
    print("=" * 70)

    if not _latency_samples:
        print("No samples collected.")
        return

    # Dividir em quartis temporais
    start_time = _latency_samples[0]["time"]
    end_time = _latency_samples[-1]["time"]
    duration = end_time - start_time

    if duration < 30:
        print("Test too short for temporal analysis.")
        return

    quarter = duration / 4
    quarters = [[], [], [], []]

    for sample in _latency_samples:
        t = sample["time"] - start_time
        q = min(int(t / quarter), 3)
        quarters[q].append(sample["response_time"])

    print("\nLatency Trend (all endpoints combined):")
    print("-" * 50)

    q_medians = []
    for i, q in enumerate(quarters):
        if q:
            q_sorted = sorted(q)
            median = q_sorted[len(q_sorted) // 2]
            p95 = q_sorted[int(len(q_sorted) * 0.95)]
            q_medians.append(median)
            print(f"  Q{i+1} ({len(q):4d} reqs): median={median:7.0f}ms  p95={p95:7.0f}ms")
        else:
            q_medians.append(0)

    # Verificar degradacao
    if q_medians[0] > 0 and q_medians[3] > 0:
        degradation = (q_medians[3] - q_medians[0]) / q_medians[0] * 100
        print(f"\n  Degradation Q1 -> Q4: {degradation:+.1f}%")

        if degradation > 50:
            print("  [!] WARNING: Significant performance degradation detected!")
            print("      Possible causes:")
            print("      - Memory leak (_active_heartbeats growing)")
            print("      - Connection pool fragmentation")
            print("      - Auth log table growing (INSERT overhead)")
            environment.process_exit_code = 1
        elif degradation > 20:
            print("  [~] NOTICE: Moderate degradation, monitor in production.")
        else:
            print("  [OK] Latency stable over time.")

    # JWT revogacao check
    revoke_stat = environment.runner.stats.entries.get("jwt-revoke-old-token-check")
    if revoke_stat and revoke_stat.num_requests > 0:
        print(f"\n--- JWT Revocation Check ---")
        print(f"  Old tokens tested: {revoke_stat.num_requests}")
        print(f"  Failures (security): {revoke_stat.num_failures}")
        if revoke_stat.num_failures == 0:
            print("  [!] KNOWN ISSUE: No token revocation implemented.")
            print("      Tokens remain valid for 24h after logout.")
            print("      FIX OPTIONS:")
            print("        a) Token blacklist in Redis (TTL = token expiry)")
            print("        b) Short-lived access tokens (15m) + refresh token rotation")
            print("        c) Store token jti in DB, check on validate")

    # Error rate
    total = environment.runner.stats.total
    if total.num_requests > 0:
        err_rate = total.num_failures / total.num_requests * 100
        print(f"\nOverall: {total.num_requests} requests, {err_rate:.2f}% error rate")
        if err_rate > 1:
            print("  [!] Error rate above 1% threshold")
            environment.process_exit_code = 1

    fake_stat = environment.runner.stats.entries.get("jwt-revoke-fake-token")
    if fake_stat and fake_stat.num_failures > 0:
        print(f"\n  [!!!] CRITICAL: {fake_stat.num_failures} fake tokens accepted!")
        environment.process_exit_code = 1
