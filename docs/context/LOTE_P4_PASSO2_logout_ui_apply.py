"""LOTE P4 - PASSO 2: A-4.3 -- o logout da UI passa a revogar a sessao no servidor.

Medido pelo QA externo (2026-09-07, viewer, Playwright): apos handleLogout() o localStorage fica
limpo mas o cookie HttpOnly access_token PERSISTE e nao ha nenhum POST /api/auth/logout na rede
(login_posts=1, logout_posts=0). O endpoint (api/routers/auth_compat.py:371-380) ja faz tudo o
que e' preciso -- blacklist do token + delete_cookie -- e ja aceita o token por cookie sem Bearer
(_get_token_from_request), mas a UI nunca o chamava: handleLogout (portal ~5063) so' fazia
clearAuthData() + showLoginOverlay(). O teste test_logout_apaga_cookie testava o endpoint, nao o
fluxo da UI (falso conforto, palavras do QA).

Desenho (watcherdb-security-auditor, 07/09): OPTIMISTA -- a UI limpa o localStorage e mostra o
overlay de imediato (nunca fica presa se o servico estiver em baixo); o POST segue em paralelo com
keepalive:true (sobrevive ao fecho da aba; sendBeacon nao permite Authorization nem credentials),
credentials:'same-origin' (leva o cookie) e Authorization Bearer (leva o token do localStorage).
Usa _originalFetch, como o login, para nao passar pelo interceptor global. O backend nao muda.

Ancora por TEXTO unico (corpo actual de handleLogout). Idempotente. Portal e' CRLF integral.

Uso (raiz do repo):  py docs/context/LOTE_P4_PASSO2_logout_ui_apply.py
Depois:              py -m pytest tests/unit/test_logout_ui_calls_endpoint.py tests/unit/test_login_sets_cookie.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_logout_ui_calls_endpoint.py"

OLD = (
    "        function handleLogout() {\n"
    "            // Sync pending preferences before logout\n"
    "            if (_prefSyncTimer) {\n"
    "                clearTimeout(_prefSyncTimer);\n"
    "                syncPreferencesToServer();\n"
    "            }\n"
    "            clearAuthData();\n"
    "            showLoginOverlay();\n"
    "        }\n"
)
NEW = (
    "        function handleLogout() {\n"
    "            // Sync pending preferences before logout\n"
    "            if (_prefSyncTimer) {\n"
    "                clearTimeout(_prefSyncTimer);\n"
    "                syncPreferencesToServer();\n"
    "            }\n"
    "            // A-4.3 (QA externo 2026-09-07): revogar a sessao no servidor -- blacklist do token +\n"
    "            // delete_cookie do access_token HttpOnly (que a UI nao consegue apagar sozinha).\n"
    "            // Optimista: a UI limpa ja; o POST segue em paralelo com keepalive (sobrevive ao fecho\n"
    "            // da aba). Se o servico estiver em baixo, o token/cookie expiram por si (24h).\n"
    "            const _logoutToken = getAuthToken();\n"
    "            try {\n"
    "                _originalFetch('/api/auth/logout', {\n"
    "                    method: 'POST',\n"
    "                    credentials: 'same-origin',\n"
    "                    keepalive: true,\n"
    "                    headers: _logoutToken ? { 'Authorization': 'Bearer ' + _logoutToken } : {}\n"
    "                }).catch(function (e) { debugLog('logout: revogacao no servidor falhou: ' + e, 'warn'); });\n"
    "            } catch (e) {\n"
    "                debugLog('logout: fetch indisponivel: ' + e, 'warn');\n"
    "            }\n"
    "            clearAuthData();\n"
    "            showLoginOverlay();\n"
    "        }\n"
)


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


raw = PORTAL.read_text(encoding="utf-8", newline="")
eol = "\r\n" if "\r\n" in raw else "\n"
old = OLD.replace("\n", eol)
new = NEW.replace("\n", eol)

if new in raw:
    print("portal: lote A-4.3 ja aplicado (skip)")
else:
    if raw.count(old) != 1:
        abort(f"esperava 1x o corpo actual de handleLogout, encontrei {raw.count(old)}")
    for sym in ("function getAuthToken()", "_originalFetch", "function debugLog("):
        if sym not in raw:
            abort(f"simbolo {sym!r} nao encontrado no portal")
    raw = raw.replace(old, new, 1)
    with PORTAL.open("w", encoding="utf-8", newline="") as fh:
        fh.write(raw)
    print("portal: handleLogout passa a chamar POST /api/auth/logout (optimista, keepalive, cookie + Bearer)")

TEST_SRC = '''"""Gate A-4.3 (pauta P4 do QA externo, 2026-09-07): o logout da UI revoga a sessao no servidor.

Ratchet no fonte: o corpo de handleLogout tem de chamar POST /api/auth/logout com o cookie
(credentials same-origin) e keepalive, ANTES de limpar o localStorage. A prova em runtime
(cookie ausente apos logout + POST observado na rede) e' o gate do QA externo em
scripts/qa/runtime/qa_ext_p4_session_token.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parents[2] / "templates" / "watcherdb_portal.html"


@pytest.fixture(scope="module")
def handle_logout() -> str:
    src = PORTAL.read_text(encoding="utf-8")
    i = src.index("function handleLogout()")
    j = src.index("\\n        }\\n", i)
    return src[i:j]


def test_logout_chama_o_endpoint(handle_logout):
    assert "'/api/auth/logout'" in handle_logout
    assert re.search(r"method:\\s*'POST'", handle_logout)


def test_logout_leva_cookie_e_sobrevive_ao_fecho_da_aba(handle_logout):
    assert re.search(r"credentials:\\s*'same-origin'", handle_logout)
    assert re.search(r"keepalive:\\s*true", handle_logout)


def test_logout_leva_bearer_do_localstorage(handle_logout):
    assert "getAuthToken()" in handle_logout
    assert "'Authorization': 'Bearer ' +" in handle_logout


def test_logout_e_optimista_mas_pede_revogacao_antes_de_limpar(handle_logout):
    # o fetch e' disparado antes de clearAuthData() (senao o token ja nao existe para o Bearer)
    assert handle_logout.index("/api/auth/logout") < handle_logout.index("clearAuthData();")
    # e a UI limpa/mostra o overlay sem esperar pelo servidor (nao ha await antes de clearAuthData)
    antes = handle_logout[: handle_logout.index("clearAuthData();")]
    assert "await " not in antes


def test_backend_logout_aceita_so_cookie():
    # o endpoint le o token por cabecalho OU cookie (fallback) -- sem isto o fluxo de UI nao revoga
    src = (PORTAL.parents[1] / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8")
    i = src.index('@router.post("/logout"')
    j = src.index("@router.", i + 10)
    blk = src[i:j]
    assert "_get_token_from_request(request)" in blk
    assert 'delete_cookie("access_token"' in blk
    assert "_token_blacklist.add(" in blk
'''

if TEST.exists():
    print("teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("tests/unit/test_logout_ui_calls_endpoint.py criado (5 testes)")

print("\nPASSO 2 concluido. Correr:  py -m pytest tests/unit/test_logout_ui_calls_endpoint.py tests/unit/test_login_sets_cookie.py -q --no-cov")
print("Depois: Restart-Service WatcherDBWebServiceV34; no browser: login qa_viewer -> logout -> F12 Application/Cookies: access_token ausente.")
