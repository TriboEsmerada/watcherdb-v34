"""LOTE P4 - PASSO 4: /api/v3/health continua publico, mas o corpo anonimo perde os campos sensiveis.

Achado da ronda 3 do QA externo (2026-09-08): /api/v3/health esta em _AUTH_PUBLIC_PATHS
(watcherdb_main.py ~661) e servia ao anonimo `auth.reset_revocation` + caminho da migracao (lote
7a12a94) e `real_data_servers` (ja antes). O council tinha assumido "autenticado" sem verificar.

Porque NAO sai da lista publica: deploy/install.ps1:699-712 espera por 200 neste endpoint sem
credenciais; docs/external/standard/INSTALL_GUIDE.md:226/264/453, tests/smoke/test_install_smoke.ps1:201
(le `status` ou `components`), deploy/validate_cell.ps1 e tests/test_functional_acceptance.py:228
(so' o 200) tambem o usam anonimamente. Tirar o endpoint da lista partia a instalacao.

Correccao (opcao recomendada pelo council): anonimo recebe success/status/timestamp/components/
implementation (o que o instalador e o smoke leem); `auth` e `real_data_servers` so' com sessao
valida (Bearer ou cookie), verificada com os mesmos helpers do AuthEnforcementMiddleware.
Nunca levanta: sessao invalida => corpo anonimo, nunca 401 (o instalador depende do 200).

Idempotente; ancoras por texto unico; EOL preservado.

Uso (raiz do repo):  py docs/context/LOTE_P4_PASSO4_health_anonimo_apply.py
Depois:              py -m pytest tests/unit/test_health_v3_anonimo.py tests/unit/test_reset_revoga_token.py -q --no-cov
                     Restart-Service WatcherDBWebServiceV34
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "watcherdb_main.py"
TEST = ROOT / "tests" / "unit" / "test_health_v3_anonimo.py"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


def _read(p: Path):
    raw = p.read_text(encoding="utf-8", newline="")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def _write(p: Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def _apply(p: Path, edits, done_marker: str) -> None:
    raw, eol = _read(p)
    if done_marker in raw:
        print(f"{p.name}: ja aplicado (skip)")
        return
    for old, _new in edits:
        o = old.replace("\n", eol)
        if raw.count(o) != 1:
            abort(f"{p.name}: esperava 1x a ancora que comeca por {old[:70]!r}, encontrei {raw.count(o)}")
    for old, new in edits:
        raw = raw.replace(old.replace("\n", eol), new.replace("\n", eol), 1)
    _write(p, raw)
    print(f"{p.name}: {len(edits)} substituicoes ancoradas")


EDITS = [
    # (a) helper de sessao antes de _auth_health_flags
    (
        "def _auth_health_flags() -> dict:\n",
        "async def _sessao_valida(request) -> bool:\n"
        "    \"\"\"True se o pedido traz um token valido (Bearer ou cookie). Nunca levanta.\n"
        "\n"
        "    P4 ronda 3 (2026-09-08): /api/v3/health e' publico (instalador/smoke dependem do 200 sem\n"
        "    credenciais), mas `auth` e `real_data_servers` so' saem com sessao valida.\n"
        "    \"\"\"\n"
        "    try:\n"
        "        token = _auth_get_token(request)\n"
        "        if not token or token in _auth_blacklist:\n"
        "            return False\n"
        "        return bool(await _auth_get_service().get_current_user(token))\n"
        "    except Exception:\n"
        "        return False\n"
        "\n"
        "\n"
        "def _auth_health_flags() -> dict:\n",
    ),
    # (b) handler recebe o Request
    (
        "@app.get(\"/api/v3/health\")\n"
        "async def health_check():\n",
        "@app.get(\"/api/v3/health\")\n"
        "async def health_check(request: Request):\n",
    ),
    # (c) corpo: dict em variavel; campos sensiveis so' com sessao
    (
        "        return {\n"
        "            'success': True,\n"
        "            'status': 'healthy' if overall_healthy else 'degraded',\n",
        "        corpo = {\n"
        "            'success': True,\n"
        "            'status': 'healthy' if overall_healthy else 'degraded',\n",
    ),
    (
        "            'real_data_servers': real_data_count,\n",
        "",
    ),
    (
        "            # P4 ronda 2 (2026-09-08): estado da revogacao de sessao por reset, observavel por GET.\n"
        "            # Nunca faz o health falhar: erro na sondagem => \"unknown\".\n"
        "            'auth': _auth_health_flags(),\n"
        "            'implementation': 'WatcherDB Monitoring System v3.0.0 - Using YOUR Excel data only'\n"
        "        }\n",
        "            'implementation': 'WatcherDB Monitoring System v3.0.0 - Using YOUR Excel data only'\n"
        "        }\n"
        "        # P4 ronda 3 (2026-09-08): so' com sessao valida. O anonimo (instalador, smoke, probes)\n"
        "        # recebe status/components; estado da revogacao e dimensao da frota nao saem sem login.\n"
        "        if await _sessao_valida(request):\n"
        "            corpo['real_data_servers'] = real_data_count\n"
        "            corpo['auth'] = _auth_health_flags()  # nunca faz o health falhar: erro => \"unknown\"\n"
        "        return corpo\n",
    ),
]
_apply(MAIN, EDITS, "_sessao_valida")

TEST_SRC = '''"""Gate P4 ronda 3: /api/v3/health e' publico (o instalador depende do 200) mas o corpo anonimo
nao expoe `auth` nem `real_data_servers`; com sessao valida expoe ambos."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _FakeSvc:
    def __init__(self, user):
        self._user = user

    async def get_current_user(self, token):
        return self._user


@pytest.fixture
def main(monkeypatch):
    try:
        import watcherdb_main
    except Exception as e:  # pragma: no cover
        pytest.skip(f"watcherdb_main nao carregavel: {e}")
    import services.auth_service as auth
    # sondagem da coluna sem BD
    monkeypatch.setattr(auth, "_execute_query", lambda q, p=None: [{"password_changed_at": None}])
    return watcherdb_main


def test_anonimo_recebe_200_sem_campos_sensiveis(main):
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/api/v3/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "status" in body
    assert "auth" not in body
    assert "real_data_servers" not in body


def test_sessao_valida_recebe_auth_e_frota(main, monkeypatch):
    from services.auth_service import create_access_token

    monkeypatch.setattr(main, "_auth_get_service", lambda: _FakeSvc({"username": "u", "role": "viewer"}))
    token = create_access_token({"sub": "u", "role": "viewer"})
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/api/v3/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "real_data_servers" in body
    assert body["auth"]["reset_revocation"] in ("active", "inactive", "unknown")


def test_token_invalido_nao_da_401_e_recebe_corpo_anonimo(main, monkeypatch):
    monkeypatch.setattr(main, "_auth_get_service", lambda: _FakeSvc(None))
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/api/v3/health", headers={"Authorization": "Bearer lixo"})
    assert r.status_code == 200
    assert "auth" not in r.json()
'''
if TEST.exists():
    print("teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("tests/unit/test_health_v3_anonimo.py criado (3 testes)")

print("\nPASSO 4 concluido. Correr:  py -m pytest tests/unit/test_health_v3_anonimo.py tests/unit/test_reset_revoga_token.py -q --no-cov")
print("Depois: Restart-Service WatcherDBWebServiceV34; curl anonimo ao /api/v3/health sem 'auth'; com Bearer com 'auth'.")
