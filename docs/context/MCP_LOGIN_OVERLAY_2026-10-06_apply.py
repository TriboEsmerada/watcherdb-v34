# -*- coding: utf-8 -*-
"""Troca obrigatoria de password no LOGIN: a caixa abria por baixo do overlay (2026-10-06).

SINTOMA (prova do P0, 2026-09-24/10-02): depois de um administrador redefinir a password, o
utilizador faz login, o servidor responde com must_change_password e o portal volta a mostrar o
cartao de login. No log de autenticacao ficam LOGIN_SUCCESS seguidos (qa_viewer, 5 em 1 minuto)
e na consola 403 MUST_CHANGE_PASSWORD em dashboard e heartbeat.

CAUSA (templates/watcherdb_portal.html, ramo pos-login):
    if (data.must_change_password) { _mcpForcarTroca(); return; }
  _mcpForcarTroca abre #changePasswordModal (z-index 1000) mas o ramo sai ANTES de hideLoginOverlay()
  -- o overlay (#loginOverlay, z-index 999999) fica por cima e a caixa nunca se ve. O caminho da
  sessao ja' aberta (interceptor do 403) nao sofre disto porque o overlay ja' esta escondido;
  foi esse o que a prova de 16/09 exerceu.

CAUSA 2 (watcherdb_main.py): /api/auth/heartbeat nao esta em _AUTH_MCP_ALLOWED -> 403 a cada
  60 s durante a troca numa sessao ja' aberta. O heartbeat so' marca o utilizador como online.

O QUE MUDA (2 ficheiros + 1 pin + 1 teste):
  templates/watcherdb_portal.html   esconder o overlay antes de abrir a caixa (sem preferencias,
                                    servidores nem heartbeat: a troca dispara location.reload()).
  watcherdb_main.py                 "/api/auth/heartbeat" entra em _AUTH_MCP_ALLOWED.
  tests/unit/test_troca_obrigatoria_20260916.py   pin do ramo pos-login actualizado.
  tests/unit/test_mcp_login_overlay_20261006.py   NOVO.

Uso:
  py docs/context/MCP_LOGIN_OVERLAY_2026-10-06_apply.py --check
  py docs/context/MCP_LOGIN_OVERLAY_2026-10-06_apply.py --preview
  py docs/context/MCP_LOGIN_OVERLAY_2026-10-06_apply.py --repo <copia>
  py docs/context/MCP_LOGIN_OVERLAY_2026-10-06_apply.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
MAIN = Path("watcherdb_main.py")
TEST_OLD = Path("tests/unit/test_troca_obrigatoria_20260916.py")
TEST_NEW = Path("tests/unit/test_mcp_login_overlay_20261006.py")

PORTAL_OLD = "                if (data.must_change_password) { _mcpForcarTroca(); return; }\n"
PORTAL_NEW = (
    "                if (data.must_change_password) {\n"
    "                    // 2026-10-06: a caixa de troca (z-index 1000) abria por baixo do overlay de login\n"
    "                    // (z-index 999999) e o utilizador via o login outra vez. Esconder o overlay primeiro;\n"
    "                    // preferencias, servidores e heartbeat ficam para o reload que a troca dispara.\n"
    "                    hideLoginOverlay();\n"
    "                    _mcpForcarTroca();\n"
    "                    return;\n"
    "                }\n"
)

MAIN_OLD = (
    '_AUTH_MCP_ALLOWED = frozenset({\n'
    '    "/api/auth/change-password",\n'
)
MAIN_NEW = (
    '_AUTH_MCP_ALLOWED = frozenset({\n'
    '    "/api/auth/change-password",\n'
    '    "/api/auth/heartbeat",   # 2026-10-06: so\' marca online; sem isto a sessao em troca leva 403 a cada 60 s\n'
)

TEST_OLD_PIN_OLD = (
    '    bloco = PORTAL[i:i + 600]\n'
    '    assert "if (data.must_change_password) { _mcpForcarTroca(); return; }" in bloco\n'
    '    assert bloco.index("_mcpForcarTroca(); return;") < bloco.index("loadPreferencesFromServer")\n'
)
TEST_OLD_PIN_NEW = (
    '    bloco = PORTAL[i:i + 1000]   # 2026-10-06: o ramo cresceu de 1 para 8 linhas\n'
    '    # 2026-10-06: o overlay e\' escondido antes de abrir a caixa (MCP_LOGIN_OVERLAY_2026-10-06).\n'
    '    assert "if (data.must_change_password) {" in bloco\n'
    '    assert bloco.index("hideLoginOverlay();") < bloco.index("_mcpForcarTroca();")\n'
    '    assert bloco.index("_mcpForcarTroca();") < bloco.index("loadPreferencesFromServer")\n'
)

TEST_NEW_SRC = '''# -*- coding: utf-8 -*-
"""2026-10-06 -- troca obrigatoria no LOGIN: a caixa tem de ficar visivel (overlay escondido antes).

Antes deste lote o ramo pos-login chamava _mcpForcarTroca() e saia sem esconder #loginOverlay
(z-index 999999); a modal (z-index 1000) abria por baixo e o utilizador via o login outra vez.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8").replace("\\r\\n", "\\n")


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
    auth = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
    i = auth.index('@router.post("/heartbeat"')
    corpo = auth[i:i + 700]
    assert "_online_heartbeats[user[\\"username\\"]]" in corpo
    assert "execute" not in corpo and "INSERT" not in corpo and "UPDATE" not in corpo
'''


def _read(root: Path, rel: Path) -> str:
    """Le sem traduzir terminacoes (read_text traduziria CRLF -> LF e a deteccao falhava)."""
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(root: Path, rel: Path, txt: str) -> None:
    (root / rel).write_text(txt, encoding="utf-8", newline="\n")


def _write_como_original(root: Path, rel: Path, txt_lf: str, crlf: bool) -> None:
    """Escreve com as terminacoes que o ficheiro tinha: o repo esta' em CRLF na arvore de trabalho
    e um ficheiro inteiro convertido a LF faz um diff de 59k linhas em vez de 9."""
    dados = txt_lf.replace("\n", "\r\n") if crlf else txt_lf
    with open(root / rel, "w", encoding="utf-8", newline="") as fh:
        fh.write(dados)


def check(root: Path) -> list[str]:
    p: list[str] = []
    portal = _read(root, PORTAL).replace("\r\n", "\n")
    if portal.count(PORTAL_OLD) != 1:
        p.append(f"{PORTAL}: ramo pos-login nao unico ({portal.count(PORTAL_OLD)}x)")
    if "hideLoginOverlay();\n                    _mcpForcarTroca();" in portal:
        p.append(f"{PORTAL}: ja aplicado")
    main = _read(root, MAIN).replace("\r\n", "\n")
    if main.count(MAIN_OLD) != 1:
        p.append(f"{MAIN}: _AUTH_MCP_ALLOWED nao encontrado")
    if '"/api/auth/heartbeat",' in main:
        p.append(f"{MAIN}: ja aplicado")
    t = _read(root, TEST_OLD).replace("\r\n", "\n")
    if t.count(TEST_OLD_PIN_OLD) != 1:
        p.append(f"{TEST_OLD}: pin antigo nao encontrado")
    if (root / TEST_NEW).exists():
        p.append(f"ja existe: {TEST_NEW}")
    return p


def apply(root: Path, preview: bool) -> None:
    edicoes = [
        (PORTAL, PORTAL_OLD, PORTAL_NEW, "ramo pos-login 1 -> 8 linhas (hideLoginOverlay antes de _mcpForcarTroca)"),
        (MAIN, MAIN_OLD, MAIN_NEW, "+ /api/auth/heartbeat em _AUTH_MCP_ALLOWED"),
        (TEST_OLD, TEST_OLD_PIN_OLD, TEST_OLD_PIN_NEW, "pin do ramo pos-login actualizado"),
    ]
    prontos = []
    for rel, velho, novo, nota in edicoes:
        bruto = _read(root, rel)
        crlf = "\r\n" in bruto
        texto = bruto.replace("\r\n", "\n").replace(velho, novo, 1)
        prontos.append((rel, texto, crlf))
        print(f"{rel}: {nota} [{'CRLF' if crlf else 'LF'} preservado]")
    print(f"{TEST_NEW}: novo (5 testes)")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel, texto, crlf in prontos:
        _write_como_original(root, rel, texto, crlf)
    _write(root, TEST_NEW, TEST_NEW_SRC)
    print("\naplicado.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.repo.resolve()
    p = check(root)
    if p:
        print("CHECK FALHOU:\n  " + "\n  ".join(p))
        return 1
    print(f"check ok em {root}")
    if a.check:
        return 0
    apply(root, a.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
