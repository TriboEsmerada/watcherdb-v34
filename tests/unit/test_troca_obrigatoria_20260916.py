"""
2026-09-16 -- a obrigacao de trocar a password e' imposta pelo servidor, e so' a contas locais.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\r\n", "\n")
SVC = (ROOT / "services" / "auth_service.py").read_text(encoding="utf-8").replace("\r\n", "\n")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8").replace("\r\n", "\n")
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_so_contas_locais_sao_obrigadas():
    i = AUTH.index("# Check must_change_password flag")
    bloco = AUTH[i:i + 1500]
    assert '_metodo = (result.get("user") or {}).get("auth_method")' in bloco
    assert '_metodo == "local"' in bloco, "ldap e local_fallback ficam de fora"


def test_a_marca_viaja_no_token():
    i = AUTH.index("# Check must_change_password flag")
    bloco = AUTH[i:i + 1500]
    assert '"mcp": True' in bloco
    assert 'result["access_token"] = create_access_token(' in bloco


def test_o_token_reemitido_apos_a_troca_nao_traz_a_marca():
    """auth_compat.py:480 -- o token da troca leva so' sub e role."""
    i = AUTH.index("novo_token = create_access_token(")
    assert "mcp" not in AUTH[i:i + 120]


def test_get_current_user_le_a_marca_do_token():
    i = SVC.index("async def get_current_user")
    bloco = SVC[i:i + 1200]
    assert '"must_change_password": bool(payload.get("mcp")),' in bloco


def test_o_token_transporta_mesmo_a_marca():
    """Comportamento real, nao texto: o que se poe no token sai do outro lado."""
    import sys
    sys.path.insert(0, str(ROOT))
    from services.auth_service import create_access_token, decode_token
    tok = create_access_token({"sub": "teste", "role": "viewer", "mcp": True})
    payload = decode_token(tok)
    assert payload is not None and payload.get("mcp") is True
    assert decode_token(create_access_token({"sub": "teste", "role": "viewer"})).get("mcp") is None


def test_o_middleware_trava_tudo_menos_autenticacao():
    assert "_AUTH_MCP_ALLOWED = frozenset({" in MAIN
    for caminho in ("/api/auth/change-password", "/api/auth/me", "/api/auth/logout", "/api/auth/validate"):
        assert f'"{caminho}",' in MAIN
    i = MAIN.index('if user.get("must_change_password") and path not in _AUTH_MCP_ALLOWED:')
    bloco = MAIN[i:i + 400]
    assert '"code": "MUST_CHANGE_PASSWORD"' in bloco
    assert "status_code=403" in bloco
    assert bloco.index("return JSONResponse") < bloco.index("return await call_next(request)"), \
        "o 403 tem de sair ANTES de o pedido seguir"


def test_o_portal_obriga_e_nao_deixa_fechar():
    assert "function _mcpForcarTroca()" in PORTAL
    i = PORTAL.index("function _mcpForcarTroca()")
    corpo = PORTAL[i:i + 1200]
    assert "modal.querySelector('.modal-close')" in corpo
    assert "fechar.style.display = 'none'" in corpo
    assert "if (_mcpAtivo) return;" in corpo, "varios 403 ao mesmo tempo nao podem reabrir a caixa"


def test_o_login_nao_entra_no_portal_com_a_obrigacao_por_cumprir():
    i = PORTAL.index("setAuthData(data.access_token, data.user);")
    bloco = PORTAL[i:i + 600]
    assert "if (data.must_change_password) { _mcpForcarTroca(); return; }" in bloco
    assert bloco.index("_mcpForcarTroca(); return;") < bloco.index("loadPreferencesFromServer")


def test_a_sessao_ja_aberta_tambem_e_apanhada():
    i = PORTAL.index("// Auto-logout on 401")
    bloco = PORTAL[i:i + 900]
    assert "resp.status === 403" in bloco
    assert "corpo.code === 'MUST_CHANGE_PASSWORD'" in bloco


def test_depois_da_troca_o_portal_recarrega():
    i = PORTAL.index("Senha alterada com sucesso!")
    bloco = PORTAL[i:i + 700]
    assert "if (_mcpAtivo) { _mcpAtivo = false; location.reload(); }" in bloco
