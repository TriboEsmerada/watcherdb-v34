"""Gate A-4.3 (pauta P4 do QA externo, 2026-09-07): o logout da UI revoga a sessao no servidor.

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
    j = src.index("\n        }\n", i)
    return src[i:j]


def test_logout_chama_o_endpoint(handle_logout):
    assert "'/api/auth/logout'" in handle_logout
    assert re.search(r"method:\s*'POST'", handle_logout)


def test_logout_leva_cookie_e_sobrevive_ao_fecho_da_aba(handle_logout):
    assert re.search(r"credentials:\s*'same-origin'", handle_logout)
    assert re.search(r"keepalive:\s*true", handle_logout)


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
