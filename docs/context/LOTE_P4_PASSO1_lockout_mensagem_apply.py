"""LOTE P4 - PASSO 1: A-4.5 (lockout expirado nao repunha o contador) + A-4.4 (enumeracao de contas
pela mensagem do 401). Decisao do owner 2026-09-07 ("siga com o recomendado"); ordem e agrupamento
aprovados pelo watcherdb-security-auditor (ambos so' em services/auth_service.py, logica pura, sem DDL).

A-4.5 (QA externo, CONFIRMADO por fonte): no ramo do lockout, quando locked_until ja' passou o codigo
caia atraves' sem tocar em failed_attempts (ficava em 5); a query de incremento re-bloqueava ao 1.o
erro seguinte. Correccao: bloqueio expirado => _reset_failed_attempts (failed_attempts=0,
locked_until=NULL) antes de verificar a password. Janela deslizante fica registada como melhoria.

A-4.4 (QA externo, CONFIRMADO em runtime): 401 dizia "Credenciais invalidas" para conta inexistente
e "Password incorrecta. Tentativa n/5 -- faltam r ..." para conta existente (e "Conta bloqueada ate
HH:MM" / "Conta desactivada") => oraculo de existencia de contas locais. Correccao: resposta HTTP
GENERICA em todos os ramos locais (constante GENERIC_LOGIN_ERROR); o motivo real (n/MAX, bloqueio,
desactivada) continua no audit log dbo.WatcherDB_Auth_Log. Fora de ambito (pauta AD): mensagens dos
ramos AD-only ("Servidor AD inalcancavel", "Credenciais Windows/AD invalidas", "Conta sem
credenciais configuradas") -- tambem revelam existencia; registadas para a P4 ronda 2.

Ancoras por TEXTO unico (verificadas em HEAD 41ae729). Idempotente. Ficheiro e' LF.

Uso (raiz do repo):  py docs/context/LOTE_P4_PASSO1_lockout_mensagem_apply.py
Depois:              py -m pytest tests/unit/test_login_generic_and_lockout.py tests/unit/test_login_sets_cookie.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "services" / "auth_service.py"
TEST = ROOT / "tests" / "unit" / "test_login_generic_and_lockout.py"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


EDITS = [
    # 0. constante
    (
        "LOCKOUT_MINUTES = 15\n",
        "LOCKOUT_MINUTES = 15\n"
        "# A-4.4 (QA externo 2026-09-07): resposta unica para TODOS os ramos locais de falha de login.\n"
        "# Qualquer variacao (mensagem, contador, bloqueio) e' um oraculo de existencia de contas.\n"
        "# O motivo real fica em dbo.WatcherDB_Auth_Log, nunca na resposta HTTP.\n"
        "GENERIC_LOGIN_ERROR = \"Credenciais invalidas\"\n",
    ),
    # 1. conta inexistente -> usa a constante
    (
        "            return {\"success\": False, \"error\": \"Credenciais invalidas\"}\n",
        "            return {\"success\": False, \"error\": GENERIC_LOGIN_ERROR}\n",
    ),
    # 2. lockout activo -> generico + audit; lockout expirado -> repor contador (A-4.5)
    (
        "            if isinstance(locked, datetime) and locked > datetime.now():\n"
        "                return {\"success\": False, \"error\": f\"Conta bloqueada ate {locked.strftime('%H:%M')}\"}\n",
        "            if isinstance(locked, datetime) and locked > datetime.now():\n"
        "                self._log_auth(login_name, \"LOGIN_FAILED\", ip, f\"Conta bloqueada ate {locked.strftime('%H:%M')}\")\n"
        "                return {\"success\": False, \"error\": GENERIC_LOGIN_ERROR}\n"
        "            if isinstance(locked, datetime):\n"
        "                # A-4.5 (QA externo 2026-09-07): bloqueio expirado -> repor o contador. Sem isto\n"
        "                # failed_attempts ficava em MAX e a 1.a falha seguinte re-bloqueava de imediato.\n"
        "                self._reset_failed_attempts(login_name)\n"
        "                user[\"failed_attempts\"] = 0\n"
        "                user[\"locked_until\"] = None\n",
    ),
    # 3. conta desactivada -> generico + audit
    (
        "        if user.get(\"disabled\"):\n"
        "            return {\"success\": False, \"error\": \"Conta desactivada\"}\n",
        "        if user.get(\"disabled\"):\n"
        "            self._log_auth(login_name, \"LOGIN_FAILED\", ip, \"Conta desactivada\")\n"
        "            return {\"success\": False, \"error\": GENERIC_LOGIN_ERROR}\n",
    ),
    # 4. mensagem de tentativas -> generica (o detalhe n/MAX ja' vai no _log_auth de cada ramo)
    (
        "    def _failed_attempt_message(self, attempts_now: int) -> str:\n"
        "        \"\"\"Mensagem informativa de tentativas restantes antes do lockout.\"\"\"\n"
        "        remaining = max(0, MAX_FAILED_ATTEMPTS - attempts_now)\n"
        "        if remaining <= 0:\n"
        "            return (f\"Password incorrecta. Conta BLOQUEADA por {LOCKOUT_MINUTES} min \"\n"
        "                    f\"apos {MAX_FAILED_ATTEMPTS} tentativas falhadas.\")\n"
        "        return (f\"Password incorrecta. Tentativa {attempts_now}/{MAX_FAILED_ATTEMPTS} — \"\n"
        "                f\"faltam {remaining} antes de bloquear {LOCKOUT_MINUTES} min.\")\n",
        "    def _failed_attempt_message(self, attempts_now: int) -> str:\n"
        "        \"\"\"A-4.4 (QA externo 2026-09-07): resposta GENERICA, igual a' de conta inexistente.\n"
        "\n"
        "        A mensagem antiga (\"Tentativa n/5 -- faltam r antes de bloquear\") so' saia para\n"
        "        contas existentes e permitia enumeracao. O contador (n/MAX) continua a ser gravado\n"
        "        no audit log por cada ramo que chama este metodo; a resposta HTTP nao varia.\n"
        "        \"\"\"\n"
        "        return GENERIC_LOGIN_ERROR\n",
    ),
]

src = AUTH.read_text(encoding="utf-8")
if "GENERIC_LOGIN_ERROR" in src:
    print("auth_service.py: lote ja aplicado (skip)")
else:
    for old, _new in EDITS:
        if src.count(old) != 1:
            abort(f"esperava 1x a ancora que comeca por {old[:60]!r}, encontrei {src.count(old)}")
    for old, new in EDITS:
        src = src.replace(old, new, 1)
    AUTH.write_text(src, encoding="utf-8")
    print(f"auth_service.py: {len(EDITS)} substituicoes ancoradas")

TEST_SRC = '''"""Gates A-4.4 (resposta generica no login) e A-4.5 (lockout expirado repoe contador).

Origem: pauta P4 do QA externo (2026-09-07). Sem BD: _get_user_from_db e os helpers de
contador/audit sao substituidos; a verificacao de password e' determinista.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

import services.auth_service as auth
from services.auth_service import GENERIC_LOGIN_ERROR, AuthService


class _Harness:
    def __init__(self, svc: AuthService):
        self.svc = svc
        self.increments: list[str] = []
        self.resets: list[str] = []
        self.audit: list[tuple] = []
        self.counter = 0


@pytest.fixture
def h(monkeypatch):
    monkeypatch.setattr(auth, "AD_ENABLED", False)          # sem AD: caminho local
    monkeypatch.setattr(auth, "verify_password", lambda plain, hashed: plain == "certa")
    monkeypatch.setattr(auth, "hash_password", lambda p: "hash-dummy")
    monkeypatch.setattr(auth, "create_access_token", lambda data: "tok-de-teste")
    svc = AuthService()
    hh = _Harness(svc)

    def _inc(username):
        hh.increments.append(username)
        hh.counter += 1
        return hh.counter

    monkeypatch.setattr(svc, "_increment_failed_attempts", _inc)
    monkeypatch.setattr(svc, "_reset_failed_attempts", lambda u: hh.resets.append(u))
    monkeypatch.setattr(svc, "_update_last_login", lambda u: None)
    monkeypatch.setattr(svc, "_log_auth", lambda *a, **k: hh.audit.append(a))
    return hh


def _user(**over):
    base = {"username": "u", "password_hash": "$2b$fake", "role": "viewer", "disabled": 0,
            "failed_attempts": 0, "locked_until": None, "full_name": "U", "email": None}
    base.update(over)
    return base


def _login(h, user, password):
    h.svc._get_user_from_db = lambda name: (dict(user) if user is not None else None)
    return asyncio.run(h.svc.authenticate("u", password, "127.0.0.1"))


# ---------------------------------------------------------------- A-4.4: resposta generica

def test_conta_inexistente_e_password_errada_dao_a_mesma_mensagem(h):
    r_inexistente = _login(h, None, "qualquer")
    r_errada = _login(h, _user(), "errada")
    assert r_inexistente["success"] is False and r_errada["success"] is False
    assert r_inexistente["error"] == r_errada["error"] == GENERIC_LOGIN_ERROR


def test_mensagem_nao_revela_contador_nem_bloqueio(h):
    h.counter = 4  # proxima falha e' a 5.a
    r = _login(h, _user(failed_attempts=4), "errada")
    assert r["error"] == GENERIC_LOGIN_ERROR
    assert "Tentativa" not in r["error"] and "BLOQUEADA" not in r["error"]
    # o detalhe continua no audit log
    assert any("5/" in str(a) for a in h.audit)


def test_conta_bloqueada_activa_da_mensagem_generica_e_nao_incrementa(h):
    futuro = (datetime.now() + timedelta(minutes=10)).isoformat()
    r = _login(h, _user(failed_attempts=5, locked_until=futuro), "certa")
    assert r["success"] is False and r["error"] == GENERIC_LOGIN_ERROR
    assert h.increments == [] and h.resets == []
    assert any("bloqueada" in str(a).lower() for a in h.audit)


def test_conta_desactivada_da_mensagem_generica(h):
    r = _login(h, _user(disabled=1), "certa")
    assert r["success"] is False and r["error"] == GENERIC_LOGIN_ERROR


def test_login_correcto_continua_a_funcionar(h):
    r = _login(h, _user(), "certa")
    assert r["success"] is True and r["access_token"] == "tok-de-teste"
    assert h.resets == ["u"]


# ---------------------------------------------------------------- A-4.5: lockout expirado

def test_lockout_expirado_repoe_contador_antes_de_verificar(h):
    passado = (datetime.now() - timedelta(minutes=1)).isoformat()
    r = _login(h, _user(failed_attempts=5, locked_until=passado), "errada")
    # 1) o contador foi reposto por causa da expiracao (antes do incremento da falha nova)
    assert h.resets == ["u"], "bloqueio expirado tem de repor failed_attempts/locked_until"
    # 2) a falha nova conta como 1.a, nao como 6.a
    assert h.increments == ["u"] and h.counter == 1
    assert r["success"] is False and r["error"] == GENERIC_LOGIN_ERROR


def test_lockout_expirado_e_password_certa_entra(h):
    passado = (datetime.now() - timedelta(minutes=1)).isoformat()
    r = _login(h, _user(failed_attempts=5, locked_until=passado), "certa")
    assert r["success"] is True
    # reposto pela expiracao e outra vez pelo sucesso: nunca fica em MAX
    assert h.resets.count("u") >= 1 and h.increments == []
'''

if TEST.exists():
    print("teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("tests/unit/test_login_generic_and_lockout.py criado (7 testes)")

print("\nPASSO 1 concluido. Correr:  py -m pytest tests/unit/test_login_generic_and_lockout.py tests/unit/test_login_sets_cookie.py -q --no-cov")
print("Depois: Restart-Service WatcherDBWebServiceV34; com um user inventado o 401 deve dizer so' 'Credenciais invalidas'.")
