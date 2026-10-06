# -*- coding: utf-8 -*-
"""2026-10-06 -- troca obrigatoria no LOGIN: a caixa tem de ficar visivel (overlay escondido antes).

Antes deste lote o ramo pos-login chamava _mcpForcarTroca() e saia sem esconder #loginOverlay
(z-index 999999); a modal (z-index 1000) abria por baixo e o utilizador via o login outra vez.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8").replace("\r\n", "\n")


def _ramo_pos_login() -> str:
    i = PORTAL.index("setAuthData(data.access_token, data.user);")
    return PORTAL[i:i + 900]


def test_o_overlay_e_escondido_antes_da_caixa():
    bloco = _ramo_pos_login()
    i = bloco.index("if (data.must_change_password) {")
    ramo = bloco[i:bloco.index("}", i)]
    assert "hideLoginOverlay();" in ramo
    assert ramo.index("hideLoginOverlay();") < ramo.index("_mcpForcarTroca();")
    assert "return;" in ramo, "continua a sair antes de preferencias/servidores/heartbeat"


def test_o_ramo_nao_arranca_o_resto_do_portal():
    bloco = _ramo_pos_login()
    i = bloco.index("if (data.must_change_password) {")
    ramo = bloco[i:bloco.index("}", i)]
    for proibido in ("loadPreferencesFromServer", "loadServers", "startHeartbeat", "restoreUserSession"):
        assert proibido not in ramo, f"{proibido} so' depois do reload que a troca dispara"


def test_o_overlay_escondido_deixa_a_modal_por_cima():
    """O z-index da modal e' menor que o do overlay; so' funciona porque o overlay fica com
    opacity 0 + pointer-events none (classe hidden) e display none 400 ms depois."""
    assert ".login-overlay.hidden { opacity: 0; pointer-events: none; }" in PORTAL
    i = PORTAL.index("function hideLoginOverlay()")
    corpo = PORTAL[i:i + 400]
    assert "overlay.classList.add('hidden')" in corpo
    assert "overlay.style.display = 'none'" in corpo


def test_o_heartbeat_passa_durante_a_troca():
    i = MAIN.index("_AUTH_MCP_ALLOWED = frozenset({")
    bloco = MAIN[i:i + 500]
    assert '"/api/auth/heartbeat",' in bloco
    for caminho in ("/api/auth/change-password", "/api/auth/me", "/api/auth/logout", "/api/auth/validate"):
        assert f'"{caminho}",' in bloco, "os quatro de 16/09 continuam"


def test_o_heartbeat_so_marca_online():
    """Guarda do porque e' seguro: o handler nao le dados nem escreve na base."""
    auth = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    i = auth.index('@router.post("/heartbeat"')
    corpo = auth[i:i + 700]
    assert "_online_heartbeats[user[\"username\"]]" in corpo
    assert "execute" not in corpo and "INSERT" not in corpo and "UPDATE" not in corpo
