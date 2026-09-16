# -*- coding: utf-8 -*-
"""Troca de password obrigatoria (2026-09-16) -- a ultima ponta que faltava.

CONTEXTO: de manha reparamos a canalizacao (a coluna must_change_password nunca tinha sido criada, porque o
script 07 abortava com o erro 207). Mas a obrigacao continuava a nao ser imposta por ninguem: `must_change_password`
tinha ZERO ocorrencias em templates/ e em static/, e nao havia nada no servidor a travar quem tivesse a marca a 1.
O reset feito por um administrador registava a obrigacao e mais nada acontecia.

DESENHO (o controlo e' do SERVIDOR, nao do browser):
 1. No login, a marca so' se impoe a contas LOCAIS (`auth_method == "local"`). Porque:
      - "ldap": a pessoa entra com a password do dominio; nao ha password local para trocar. Obriga-la seria
        prende-la num pedido que nao consegue satisfazer.
      - "local_fallback": conta de AD com recurso local. O `password_hash` tem o marcador `ad_auth:` e o
        change_password reescreve `password_hash` (services/auth_service.py:1383) -- trocar converteria a conta
        de AD em conta local sem ninguem pedir. Defeito latente que fica registado, mas nao e' deste lote.
    Nesses dois casos a marca continua na base; apenas nao se impoe.
 2. Quando se impoe, o token de sessao leva a marca (claim `mcp`). O middleware global le-a do proprio token:
    zero consultas a` base por pedido.
 3. O AuthEnforcementMiddleware (watcherdb_main.py:686) recusa com 403 tudo o que nao seja autenticacao,
    enquanto a marca estiver no token. O codigo `MUST_CHANGE_PASSWORD` vai no corpo para o portal saber o que fazer.
 4. O portal abre a caixa de troca sem botao de fechar e nao entra no resto da aplicacao. Depois da troca, o
    servidor ja devolve um token novo SEM a marca e renova o cookie (auth_compat.py:480,491) -- recarregar entra
    normalmente.
 5. O caso da sessao ja aberta quando a marca aparece fica coberto pelo 403 apanhado no envolvente do fetch.

POR MEDIR/ASSUMIR: nada. Fluxo de login lido em templates/watcherdb_portal.html:5063-5100, envolvente do fetch
em 5013-5037, caixa de troca em 4341 e 5325-5396, middleware em watcherdb_main.py:686-718,
get_current_user em services/auth_service.py:1322-1341, valores de auth_method em 952/1098/1272/1297.

NAO FAZ: nao corrige a conversao de conta de AD em conta local pelo change_password (defeito separado, a
reportar); nao mexe na base; nao muda quem poe ou tira a marca.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/TROCA_OBRIGATORIA_2026-09-16_apply.py --check
  py docs/context/TROCA_OBRIGATORIA_2026-09-16_apply.py
  py -m pytest tests/unit/test_troca_obrigatoria_20260916.py tests/unit/test_must_change_password_20260916.py tests/unit/test_login_sets_cookie.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5

COMO PROVAR A SERIO (opcional, na base, com ligacao com direitos de UPDATE):
  UPDATE dbo.WatcherDB_Users SET must_change_password = 1 WHERE username = '<uma conta local de teste>';
  -> login dessa conta abre a caixa sem botao de fechar; o resto do portal responde 403; depois de trocar, entra.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "auth": Path("api/routers/auth_compat.py"),
    "svc": Path("services/auth_service.py"),
    "main": Path("watcherdb_main.py"),
    "portal": Path("templates/watcherdb_portal.html"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_troca_obrigatoria_20260916.py"),
}
MARK = "_mcpForcarTroca"

# ------------------------------------------------------------------ 1. login: so' contas locais
AUTH_OLD = '''    # Check must_change_password flag
    try:
        rows = _execute_query(
            "SELECT must_change_password FROM dbo.WatcherDB_Users WHERE username = ?",
            (login_req.username,),
        )
        if rows and rows[0].get("must_change_password"):
            result["must_change_password"] = True
    except Exception as exc:
        _avisar_coluna_em_falta("login", exc)
'''
AUTH_NEW = '''    # Check must_change_password flag
    # 2026-09-16: a obrigacao SO' se impoe a contas locais. Quem entra por AD ("ldap") nao tem password local
    # para trocar; e numa conta de AD com recurso local ("local_fallback") o change_password reescreve o
    # password_hash, que ali guarda o marcador ad_auth: -- obrigar converteria a conta em local sem ninguem
    # pedir. Nesses casos a marca fica na base e nao se impoe.
    _metodo = (result.get("user") or {}).get("auth_method")
    try:
        rows = _execute_query(
            "SELECT must_change_password FROM dbo.WatcherDB_Users WHERE username = ?",
            (login_req.username,),
        )
        if rows and rows[0].get("must_change_password") and _metodo == "local":
            result["must_change_password"] = True
            # A marca viaja no token (claim mcp) para o middleware a ler sem ir a` base a cada pedido.
            result["access_token"] = create_access_token({
                "sub": login_req.username,
                "role": (result.get("user") or {}).get("role", "viewer"),
                "mcp": True,
            })
    except Exception as exc:
        _avisar_coluna_em_falta("login", exc)
'''

# ------------------------------------------------------------------ 2. o token diz se a sessao esta travada
SVC_OLD = '''        return {
            "username": username,
            "role": user.get("role", payload.get("role", "viewer")),
            "full_name": user.get("full_name", username),
            "email": user.get("email")
        }
'''
SVC_NEW = '''        return {
            "username": username,
            "role": user.get("role", payload.get("role", "viewer")),
            "full_name": user.get("full_name", username),
            "email": user.get("email"),
            # 2026-09-16: vem do proprio token (claim mcp posto no login), nao da base -- o middleware
            # decide sem custo. O token emitido depois da troca ja nao o traz.
            "must_change_password": bool(payload.get("mcp")),
        }
'''

# ------------------------------------------------------------------ 3. middleware: trava tudo menos autenticacao
MAIN_ALLOW_OLD = '''_AUTH_PUBLIC_PREFIXES = (
    "/static/",
    "/ws",  # WebSocket autentica via query param token (ver websocket_endpoint)
)
'''
MAIN_ALLOW_NEW = '''_AUTH_PUBLIC_PREFIXES = (
    "/static/",
    "/ws",  # WebSocket autentica via query param token (ver websocket_endpoint)
)

# 2026-09-16: unicos caminhos que uma sessao obrigada a trocar a password pode usar ate' a trocar.
# O resto responde 403. Os caminhos do SPA (/watcherdb, /static/...) ja estao acima, portanto a pagina
# carrega e mostra a caixa de troca; o que nao passa sao os pedidos de dados.
_AUTH_MCP_ALLOWED = frozenset({
    "/api/auth/change-password",
    "/api/auth/me",
    "/api/auth/logout",
    "/api/auth/validate",
})
'''

MAIN_MW_OLD = '''        # Attach user to request.state para endpoints que nao usam Depends(_require_auth)
        request.state.user = user
        return await call_next(request)
'''
MAIN_MW_NEW = '''        # Attach user to request.state para endpoints que nao usam Depends(_require_auth)
        request.state.user = user
        # 2026-09-16: sessao obrigada a trocar a password so' fala com os endpoints de autenticacao.
        # A marca vem do token (claim mcp), por isso isto nao custa nenhuma ida a` base.
        if user.get("must_change_password") and path not in _AUTH_MCP_ALLOWED:
            return JSONResponse(
                {"detail": "Tem de trocar a password antes de continuar",
                 "code": "MUST_CHANGE_PASSWORD"},
                status_code=403,
            )
        return await call_next(request)
'''

# ------------------------------------------------------------------ 4. portal
PORTAL_FETCH_OLD = """                if (resp.status === 401 && typeof url === 'string' && url.startsWith('/api') && !url.includes('/auth/login')) {
                    clearAuthData();
                    showLoginOverlay();
                }
                return resp;
"""
PORTAL_FETCH_NEW = """                if (resp.status === 401 && typeof url === 'string' && url.startsWith('/api') && !url.includes('/auth/login')) {
                    clearAuthData();
                    showLoginOverlay();
                }
                // 2026-09-16: sessao travada ate' trocar a password. Cobre a sessao que ja estava aberta
                // quando um administrador fez o reset, nao so' o momento do login.
                if (resp.status === 403 && typeof url === 'string' && url.startsWith('/api')) {
                    resp.clone().json().then(corpo => {
                        if (corpo && corpo.code === 'MUST_CHANGE_PASSWORD') _mcpForcarTroca();
                    }).catch(() => {});
                }
                return resp;
"""

PORTAL_LOGIN_OLD = """                const data = await resp.json();
                setAuthData(data.access_token, data.user);

                // Load preferences from server
"""
PORTAL_LOGIN_NEW = """                const data = await resp.json();
                setAuthData(data.access_token, data.user);

                // 2026-09-16: password definida por outra pessoa -> troca antes de entrar. Sai aqui de
                // proposito: qualquer pedido a seguir levaria 403 do middleware e sujaria o ecra de erros.
                if (data.must_change_password) { _mcpForcarTroca(); return; }

                // Load preferences from server
"""

PORTAL_FUNC_OLD = """        // ══════ CHANGE PASSWORD ══════
        function openChangePasswordModal() {
"""
PORTAL_FUNC_NEW = """        // ══════ Troca obrigatoria (2026-09-16) ══════
        // A caixa e' a mesma; o que muda e' que nao se pode fechar e que o portal nao abre por tras.
        let _mcpAtivo = false;
        function _mcpForcarTroca() {
            if (_mcpAtivo) return;   // o 403 pode chegar de varios pedidos ao mesmo tempo
            _mcpAtivo = true;
            const modal = document.getElementById('changePasswordModal');
            if (!modal) return;
            const fechar = modal.querySelector('.modal-close');
            if (fechar) fechar.style.display = 'none';
            openChangePasswordModal();
            const aviso = document.getElementById('cpwdMsg');
            if (aviso) {
                aviso.style.display = 'block';
                aviso.style.background = 'rgba(245,158,11,0.15)';
                aviso.style.color = '#f59e0b';
                aviso.textContent = (typeof t === 'function' && t('msg.must_change_password') !== 'msg.must_change_password')
                    ? t('msg.must_change_password')
                    : 'Esta senha foi definida por outra pessoa. Escolhe uma nova para continuares.';
            }
        }

        // ══════ CHANGE PASSWORD ══════
        function openChangePasswordModal() {
"""

PORTAL_OK_OLD = """                    setTimeout(() => { document.getElementById('changePasswordModal').style.display = 'none'; }, 1500);
"""
PORTAL_OK_NEW = """                    setTimeout(() => {
                        document.getElementById('changePasswordModal').style.display = 'none';
                        // 2026-09-16: se a troca era obrigatoria, o token novo ja nao traz a marca e o
                        // cookie foi renovado -- recarregar entra no portal em vez de ficar tudo em 403.
                        if (_mcpAtivo) { _mcpAtivo = false; location.reload(); }
                    }, 1500);
"""

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **A obrigação de trocar a password passa a ser mesmo imposta** (16/09). De manhã ficou a marca a ser\n"
    "  gravada; faltava quem a fizesse valer — o ecrã nunca lia o campo e o servidor não travava ninguém. Agora,\n"
    "  quem tem a obrigação recebe a caixa de troca sem botão de fechar, e o servidor recusa todos os pedidos que\n"
    "  não sejam de autenticação até a troca estar feita (a marca viaja no próprio token, por isso não custa uma\n"
    "  ida à base por pedido). Só se aplica a contas locais: quem entra pelo domínio não tem password local para\n"
    "  trocar, e numa conta de domínio com senha local de recurso a troca converteria a conta. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- a obrigacao de trocar a password e' imposta pelo servidor, e so' a contas locais.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
SVC = (ROOT / "services" / "auth_service.py").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")


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
    assert bloco.index("return JSONResponse") < bloco.index("return await call_next(request)"), \\
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:110]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1

    out = {
        "auth": _apply(src["auth"].read_bytes().decode("utf-8"), [(AUTH_OLD, AUTH_NEW, 1)], "auth_compat"),
        "svc": _apply(src["svc"].read_bytes().decode("utf-8"), [(SVC_OLD, SVC_NEW, 1)], "auth_service"),
        "main": _apply(src["main"].read_bytes().decode("utf-8"),
                       [(MAIN_ALLOW_OLD, MAIN_ALLOW_NEW, 1), (MAIN_MW_OLD, MAIN_MW_NEW, 1)], "watcherdb_main"),
        "portal": _apply(portal, [(PORTAL_FETCH_OLD, PORTAL_FETCH_NEW, 1),
                                  (PORTAL_LOGIN_OLD, PORTAL_LOGIN_NEW, 1),
                                  (PORTAL_FUNC_OLD, PORTAL_FUNC_NEW, 1),
                                  (PORTAL_OK_OLD, PORTAL_OK_NEW, 1)], "portal"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
    }
    for chave in ("auth", "svc", "main"):
        compile(out[chave], str(REL[chave]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] auth_compat (login); auth_service (claim); watcherdb_main (allowlist + 403); portal 4 blocos; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_troca_obrigatoria_20260916.py "
          "tests/unit/test_must_change_password_20260916.py tests/unit/test_login_sets_cookie.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
