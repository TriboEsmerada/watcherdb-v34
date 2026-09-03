"""
Smoke test for the PyInstaller bundle produced by deploy/build.py.

The test spawns dist/watcherdb/watcherdb.exe as a subprocess on a
non-default port, polls until the HTTP server binds, hits a known
lightweight endpoint and asserts the service is alive. It then
terminates the subprocess.

The test is a no-op on machines where the bundle has never been built
(dist/watcherdb/watcherdb.exe missing) so CI on build-less developer
workstations stays green.

This test also intentionally skips on non-Windows hosts: PyInstaller
onedir is produced for Windows and the pywin32 dependencies will not
resolve on Linux/macOS.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

try:
    import httpx
except ImportError:  # pragma: no cover - dev install skew
    httpx = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLE_EXE = PROJECT_ROOT / "dist" / "watcherdb" / "watcherdb.exe"

SMOKE_PORT = int(os.environ.get("WATCHERDB_SMOKE_PORT", "8499"))
SMOKE_HOST = "127.0.0.1"

# HTTPS, nao HTTP (2026-08-19). O bundle traz um config.yaml com `ssl.enabled`
# e o cert em PEM, portanto arranca em TLS:
#     [START] WatcherDB V3.3 Standard (consola) - https://127.0.0.1:8499
#             | TLS: ON (cert=watcherdb.crt.pem)
#
# Falar HTTP contra esse socket da' ligacao ACEITE e fechada sem resposta -- o
# curl reporta 000 em milissegundos e o httpx levanta RemoteProtocolError
# ("Server disconnected without sending a response"). O sintoma imita
# perfeitamente "o servico esta pendurado", e custou uma investigacao inteira:
# porta LISTENING, processo vivo, zero respostas. O servico estava impecavel.
#
# E' o MESMO defeito que o tests/e2e/conftest.py tinha, corrigido horas antes
# no ficheiro ao lado. O TLS vem do config.yaml, nao de variaveis de ambiente --
# por isso procurar WATCHERDB_TLS_CERT no ambiente da' vazio e engana.
SMOKE_SCHEME = os.environ.get("WATCHERDB_SMOKE_SCHEME", "https")
SMOKE_BASE = f"{SMOKE_SCHEME}://{SMOKE_HOST}:{SMOKE_PORT}"
# O cert e' da CA interna e o CN nao cobre 127.0.0.1.
SMOKE_VERIFY = False
# Etapa 2: bundle ~147MB (imports third-party completos) + EDR scan no
# primeiro arranque — 60s ficava a meio do lifespan startup.
BOOT_TIMEOUT_S = 120
READY_PROBE_INTERVAL_S = 0.5


pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="PyInstaller bundle is Windows-only."),
    pytest.mark.skipif(not BUNDLE_EXE.exists(), reason=f"Bundle not built yet: {BUNDLE_EXE}"),
    pytest.mark.skipif(httpx is None, reason="httpx not installed"),
]


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout_s: int) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(READY_PROBE_INTERVAL_S)
    return False


@pytest.fixture
def bundle_process(tmp_path):
    """Launch watcherdb.exe, yield the Popen handle, terminate on teardown.

    stdout vai para FICHEIRO, nao para PIPE: o arranque emite dezenas de
    KB de log e um pipe nao-drenado (~64KB de buffer no Windows) enchia e
    bloqueava o processo em write() ANTES do bind — deadlock classico do
    Popen (2026-07-04: o exe binda em ~12s com stdout em ficheiro; nunca
    bindava com o pipe cheio).
    """
    env = os.environ.copy()
    env["WATCHERDB_HOST"] = SMOKE_HOST
    env["WATCHERDB_PORT"] = str(SMOKE_PORT)
    env["WATCHERDB_LICENSE_ENFORCE"] = "advisory"   # no license.dat on CI

    # Identidade de BD explicita (2026-08-19). Desde que o Windows Auth por
    # omissao foi removido (7daeb34), o servico RECUSA arrancar sem decisao
    # escrita -- e um bundle acabado de construir nao tem .env nenhum, por
    # definicao. Sem isto o exe morre em enforce_explicit_identity() e o smoke
    # nunca ve a porta abrir; foi o que abortou o primeiro `-Target msi`.
    env["INTELLIGENCE_USE_WINDOWS_AUTH"] = "false"
    env.pop("SQL_TRUSTED_CONNECTION", None)   # herdada criaria CONFLICT

    # NAO se exigem credenciais de BD aqui, e isso e' deliberado.
    #
    # Uma versao anterior deste ficheiro falhava com instrucoes a pedir
    # INTELLIGENCE_SQL_USER/PASSWORD, na convicção de que sem elas o bundle
    # abria a porta e nao servia nada. Estava errado: medido em laboratorio, o
    # ciclo de cache fecha em 0,08 s, as falhas de ligacao sao instantaneas
    # ("SQL Authentication requer senha") e o /healthz responde em 40 ms. O que
    # parecia um servico pendurado era HTTP contra um socket TLS (ver
    # SMOKE_SCHEME).
    #
    # O smoke prova que o bundle ARRANCA E SERVE. Que sirva com a BD em baixo e'
    # propriedade desejavel, nao defeito -- e testa-la sem credenciais e' mais
    # valioso do que testa-la com elas.
    # subprocess inherits env but pytest's own PYTEST_CURRENT_TEST leaks in too,
    # which makes the license validator bypass automatically. Both paths are
    # valid: if we remove PYTEST_CURRENT_TEST the advisory branch runs.
    env.pop("PYTEST_CURRENT_TEST", None)

    boot_log = tmp_path / "watcherdb_boot.log"
    log_fh = open(boot_log, "wb")
    proc = subprocess.Popen(
        [str(BUNDLE_EXE)],
        cwd=str(BUNDLE_EXE.parent),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    try:
        if not _wait_for_port(SMOKE_HOST, SMOKE_PORT, BOOT_TIMEOUT_S):
            # Surface o TAIL do log do subprocess (a causa real fica no fim).
            log_fh.flush()
            out = b""
            try:
                out = boot_log.read_bytes()[-6000:]
            except OSError:
                pass
            pytest.fail(
                f"watcherdb.exe did not bind {SMOKE_HOST}:{SMOKE_PORT} within "
                f"{BOOT_TIMEOUT_S}s. stdout tail:\n{out!r}"
            )
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log_fh.close()


def test_bundle_serves_health_endpoint(bundle_process):
    """The bundled service must answer /api/v3/health with a JSON payload."""
    url = f"{SMOKE_BASE}/api/v3/health"
    resp = httpx.get(url, timeout=10.0, verify=SMOKE_VERIFY)
    assert resp.status_code == 200, f"health returned {resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    # Tolerant shape check — we only need evidence the app booted and
    # the router registration survived the PyInstaller transformation.
    assert isinstance(body, dict), f"unexpected body type: {type(body).__name__}"
    assert "status" in body or "components" in body, f"unexpected body: {body!r}"


def test_bundle_docs_disabled_in_release_mode(bundle_process):
    """When WATCHERDB_DISABLE_DOCS=true the OpenAPI surface must be hidden.

    The fixture launches without that flag so /docs should be available.
    This test asserts the negative: /docs either 200s (dev) or redirects —
    either way it does not raise an InternalServerError.
    """
    resp = httpx.get(f"{SMOKE_BASE}/docs", timeout=5.0, verify=SMOKE_VERIFY)
    # 401: desde a Etapa 2 o bundle carrega o auth middleware completo e
    # /docs fica protegido — comportamento correto de producao. O teste
    # continua a garantir apenas que /docs nao devolve 5xx.
    assert resp.status_code in (200, 301, 302, 401, 404), (
        f"/docs returned unexpected {resp.status_code}"
    )


def test_bundle_portal_shell_renders(bundle_process):
    """GET /watcherdb tem de renderizar HTML via Jinja2Templates sem 500.

    Regressao-alvo: TemplateResponse old-style quebra em starlette>=1.0
    (shim removido — incidente instalacao real 2026-08-10, SQLHDSPRD213:
    portal inteiro 500 "unhashable type: dict"). /api/v3/health e /docs
    nao passam por Jinja2Templates e nao apanham este padrao. /watcherdb
    esta em _AUTH_PUBLIC_PATHS, logo 200 sem token e o esperado.
    """
    resp = httpx.get(f"{SMOKE_BASE}/watcherdb", timeout=10.0, verify=SMOKE_VERIFY)
    assert resp.status_code == 200, (
        f"/watcherdb returned {resp.status_code}: {resp.text[:300]}"
    )
    assert "text/html" in resp.headers.get("content-type", "")
    assert len(resp.text) > 1000
