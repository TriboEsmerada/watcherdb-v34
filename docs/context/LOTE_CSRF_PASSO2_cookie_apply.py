"""LOTE CSRF+COOKIE (decisao owner 2026-09-05, opcao a) - PASSO 2: o login volta a emitir o cookie.

SO' CORRER DEPOIS do PASSO 1 estar commitado e o teste do middleware verde. Ordem imposta pelo
security-auditor: o middleware sem cookie e' inofensivo; o cookie sem middleware reabre o CSRF
same-site em 22 endpoints. Um rollback parcial nunca pode deixar o cookie sozinho.

Causa (fonte + runtime em 8434, 05/09): auth_compat.py:330 testa `result.get("token")` e
:340 le `result["token"]`, mas services/auth_service.py devolve a chave "access_token" em todos
os caminhos (AD 1114, AD+fallback 1164, local 1189). Logo o cookie HttpOnly desenhado em
2026-08-18 nunca foi emitido no V3.4 e `_get_token_from_request` (auth_compat.py:201) lia um
cookie que nao existia.

O que este script faz (idempotente; aborta se algum padrao nao bater):
  1. api/routers/auth_compat.py: `result.get("token")` -> `result.get("access_token")` e
     `value=result["token"]` -> `value=result["access_token"]` (exactamente 1 ocorrencia cada).
  2. tests/unit/test_login_sets_cookie.py: gate permanente -- login com sucesso emite
     Set-Cookie access_token HttpOnly SameSite=lax; login falhado nao emite cookie; logout apaga.

Fora deste lote (pauta P4 do qa-externo): o SPA continua a guardar o token em localStorage e a
enviar Bearer; o cookie e' fallback. Logout apaga o cookie mas nao o localStorage (pre-existente).
max_age=86400 e' fixo enquanto jwt_expire_minutes e' configuravel (1440 por omissao = coerente
hoje; documentar se o admin mudar).

Uso (raiz do repo):  py docs/context/LOTE_CSRF_PASSO2_cookie_apply.py
Depois:              py -m pytest tests/unit/test_login_sets_cookie.py tests/unit/test_same_origin_middleware.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "api" / "routers" / "auth_compat.py"
TEST = ROOT / "tests" / "unit" / "test_login_sets_cookie.py"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


# --- 1. auth_compat.py -----------------------------------------------------------------
src = AUTH.read_text(encoding="utf-8")
gate_old, gate_new = 'if result.get("token"):', 'if result.get("access_token"):'
val_old, val_new = 'value=result["token"],', 'value=result["access_token"],'

if gate_new in src and val_new in src and gate_old not in src and val_old not in src:
    print("1. auth_compat.py: chave ja corrigida (skip)")
else:
    if src.count(gate_old) != 1:
        abort(f"auth_compat.py: esperava 1 ocorrencia de {gate_old!r}, encontrei {src.count(gate_old)}")
    if src.count(val_old) != 1:
        abort(f"auth_compat.py: esperava 1 ocorrencia de {val_old!r}, encontrei {src.count(val_old)}")
    src = src.replace(gate_old, gate_new).replace(val_old, val_new)
    # Nota de manutencao junto ao gate, para ninguem "corrigir" de volta.
    marker = "    # Cookie so' e' emitido se houver token. Chave e' access_token (auth_service devolve\n" \
             "    # access_token em todos os caminhos); ate' 2026-09-05 testava-se \"token\" e o cookie\n" \
             "    # nunca saia -- ver tests/unit/test_login_sets_cookie.py.\n"
    src = src.replace("    " + gate_new, marker + "    " + gate_new, 1)
    AUTH.write_text(src, encoding="utf-8")
    print("1. auth_compat.py: cookie passa a ler access_token")

# --- 2. teste --------------------------------------------------------------------------
TEST_SRC = '''"""Gate permanente: o login emite o cookie de sessao (lote 2026-09-05).

Ate' 2026-09-05 o handler testava result.get("token") e o servico devolvia "access_token":
o cookie HttpOnly nunca era emitido e o fallback por cookie era codigo morto. Este teste
falha se a chave voltar a divergir.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _FakeAuthService:
    def __init__(self, ok: bool):
        self.ok = ok

    async def authenticate(self, username, password, ip=None):
        if not self.ok:
            return {"success": False, "error": "Credenciais invalidas"}
        return {
            "success": True,
            "access_token": "tok-de-teste",
            "token_type": "bearer",
            "expires_in": 60,
            "user": {"username": username, "role": "viewer", "auth_method": "local"},
        }


@pytest.fixture
def app_client(monkeypatch):
    try:
        import watcherdb_main
    except Exception as e:  # pragma: no cover
        pytest.skip(f"watcherdb_main nao carregavel: {e}")
    import api.routers.auth_compat as auth_compat

    # Sem BD: a consulta de must_change_password devolve vazio.
    monkeypatch.setattr(auth_compat, "_execute_query", lambda *a, **k: [])
    # Sem rate-limit: outros testes da suite tambem batem no /login com o mesmo IP.
    monkeypatch.setattr(auth_compat.limiter, "enabled", False, raising=False)

    def _make(ok: bool):
        monkeypatch.setattr(auth_compat, "get_auth_service", lambda: _FakeAuthService(ok))
        return TestClient(watcherdb_main.app, raise_server_exceptions=False)

    return _make


def _set_cookie_header(resp) -> str:
    return "; ".join(v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie")


def test_login_ok_emite_cookie_httponly_lax(app_client):
    client = app_client(ok=True)
    r = client.post("/api/auth/login", json={"username": "qa_viewer", "password": "x"})
    assert r.status_code == 200, r.text
    assert r.json().get("access_token") == "tok-de-teste"
    assert r.cookies.get("access_token") == "tok-de-teste"
    sc = _set_cookie_header(r).lower()
    assert "httponly" in sc
    assert "samesite=lax" in sc
    assert "path=/" in sc


def test_login_falhado_nao_emite_cookie(app_client):
    client = app_client(ok=False)
    r = client.post("/api/auth/login", json={"username": "qa_viewer", "password": "errada"})
    assert r.status_code == 401
    assert r.cookies.get("access_token") is None
    assert "access_token" not in _set_cookie_header(r).lower()


def test_logout_apaga_cookie(app_client):
    client = app_client(ok=True)
    client.post("/api/auth/login", json={"username": "qa_viewer", "password": "x"})
    r = client.post("/api/auth/logout")
    sc = _set_cookie_header(r).lower()
    # delete_cookie => Set-Cookie access_token=""; expires no passado / max-age=0
    assert "access_token=" in sc
    assert ("max-age=0" in sc) or ("expires=" in sc)
'''

if TEST.exists():
    print("2. teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("2. tests/unit/test_login_sets_cookie.py criado")

print("\nPASSO 2 concluido. Correr:  py -m pytest tests/unit/test_login_sets_cookie.py tests/unit/test_same_origin_middleware.py -q --no-cov")
