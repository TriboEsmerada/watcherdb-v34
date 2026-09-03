"""
WatcherDB V3.3 — Playwright E2E Test Configuration (pytest-playwright).

Harness convergido na familia em pytest-playwright (decisao 2026-06-25): mesmo runner
dos ~800 testes pytest, sem toolchain Node/npm. As specs .ts legadas (health/workflows)
ficam como referencia a retirar.

Prerequisites:
  pip install pytest-playwright
  playwright install chromium

Run (com o servico V3.3 NSSM a correr em http://localhost:8433):
  pytest tests/e2e/ -v

Set WATCHERDB_BASE_URL env var to override the default.
"""

import os
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: testes end-to-end de browser (Playwright); requerem servico a correr")
    config.addinivalue_line("markers", "e2e_mock: e2e determinista com endpoints mockados via page.route (CI-able)")


# Base URL do servico V3.3 a correr (porta 8433).
#
# HTTPS, nao HTTP: o TLS foi activado no host a 2026-08-16 (181dd9e) e o socket
# deixou de responder em claro -- `http://` devolve resposta vazia
# (ERR_EMPTY_RESPONSE no Playwright, 000 no curl), porque o uvicorn esta a fazer
# TLS directo, sem proxy a fazer downgrade.
#
# Este default ficou para tras nessa altura e ninguem reparou durante tres dias:
# os testes e2e estao fora da corrida por omissao (`-m "not e2e"` no
# pyproject.toml) e nao correm em automacao nenhuma. Um harness que so' se
# executa a pedido apodrece em silencio -- foi o que aconteceu aqui.
#
# O certificado e' da CA interna e o CN nao cobre `localhost`; o
# `ignore_https_errors` abaixo trata disso.
BASE_URL = os.getenv("WATCHERDB_BASE_URL", "https://localhost:8433")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "viewport": {"width": 1920, "height": 1080},
    }
