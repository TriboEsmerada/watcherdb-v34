# -*- coding: utf-8 -*-
"""Menu de perfil (2026-09-14) -- seguranca, acessibilidade e texto. So portal.

Pedido do owner: corrigir o Escape do menu de perfil (achado do frontend-specialist no A2). Ao ler o
codigo apareceram tres problemas no MESMO bloco, corrigidos juntos (o owner foi avisado):

  1. SEGURANCA. updateUserBadge punha no innerHTML, sem escapar, o nome, e-mail, papel, departamento
     e cargo do utilizador. Departamento e cargo vem do Active Directory: quem controla esses atributos
     no directorio injectava HTML/JS no portal de todos os que abrissem o menu. Tudo passa por _pmEsc,
     e a classe CSS do papel passa a aceitar so [a-z0-9_-].
  2. ACESSIBILIDADE. O gatilho (#userBadge) e as opcoes eram <div> sem foco nem papel: quem usa so
     teclado nem abria o menu, e nao havia Escape. Padrao de botao de menu (WAI-ARIA), o mesmo do sino:
       - gatilho com role=button, tabindex=0, aria-haspopup=menu, aria-expanded, aria-controls
       - Enter/Espaco/Seta abaixo abrem e poem o foco na 1.a opcao; Seta acima abre na ultima
       - opcoes passam a <button role=menuitem>; setas percorrem, Home/End saltam
       - ESCAPE fecha e DEVOLVE O FOCO ao gatilho; Tab fecha e deixa o foco seguir
       - clicar numa opcao NAO devolve o foco (a modal que abre tem de ficar com ele)
     O gatilho continua <div> com role=button em vez de <button> nativo, para nao mexer no layout do
     cabecalho; o comportamento para teclado e leitor de ecra e equivalente.
  3. TEXTO E VERSAO. "Alterar Senha" e "Sair" em portugues cru, "Configuracoes" sem acento, e o rodape
     dizia "WatcherDB V3.3" num portal V3.4. Chaves profile_menu.* em pt-PT, en, es, e overlay pt-BR
     (que mantem "Alterar senha" e "Sair", as formas brasileiras que estavam no original).

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/MENU_PERFIL_2026-09-14_apply.py --check
  py docs/context/MENU_PERFIL_2026-09-14_apply.py
  py -m pytest tests/unit/test_menu_perfil_20260914.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_menu_perfil_20260914.py"),
}
MARK = "function _pmEsc("

DD_INI = "                    dropdown.innerHTML = `\n"
DD_FIM = ("                        <div class=\"profile-footer\">\n"
          "                            <span>WatcherDB V3.3</span>\n"
          "                        </div>\n"
          "                    `;\n")

DD_NOVO = r"""                    dropdown.innerHTML = `
                        <div class="profile-header">
                            <div class="profile-avatar">${initials}</div>
                            <div class="profile-info">
                                <div class="profile-name">${_pmEsc(user.full_name || user.username)}</div>
                                <div class="profile-email">${_pmEsc(user.email || user.username)}</div>
                                ${dept}${title}
                                <div style="margin-top:6px;">
                                    <span class="profile-role-badge ${roleCss}">${_pmEsc(user.role)}</span>
                                    <span class="profile-auth-badge"><i class="${authIcon}" aria-hidden="true"></i> ${authLabel}</span>
                                </div>
                            </div>
                        </div>
                        <div class="profile-menu" role="menu" aria-label="${_pmEsc(t('profile_menu.menu_label'))}">
                            ${user.role === 'admin' ? `
                            <button type="button" role="menuitem" class="profile-menu-item" onclick="window.open('/watcherdb/control','_blank'); closeProfileDropdown();">
                                <i class="fas fa-shield-alt" aria-hidden="true"></i> WatcherDB Control
                            </button>` : ''}
                            <!-- KPIs removido do dropdown 2026-08-21 (pedido owner):
                                 redundante com o botao KPIs da navbar. -->
                            ${(user.role === 'admin' || user.role === 'dba') ? `
                            <button type="button" role="menuitem" class="profile-menu-item" onclick="openCollectorsModal(); closeProfileDropdown();"
                                 title="Collector Health Monitoring (dba/admin)">
                                <i class="fas fa-tower-broadcast" aria-hidden="true"></i> Collectors
                            </button>
                            <button type="button" role="menuitem" class="profile-menu-item" onclick="openKpiMuteModal(); closeProfileDropdown();"
                                 title="KPI Mute List - Smart Defaults camada 1 (dba/admin)">
                                <i class="fas fa-bell-slash" aria-hidden="true"></i> Mutes
                            </button>` : ''}
                            <button type="button" role="menuitem" class="profile-menu-item" onclick="openChangePasswordModal(); closeProfileDropdown();">
                                <i class="fas fa-key" aria-hidden="true" style="color:#f59e0b;"></i> ${_pmEsc(t('profile_menu.change_password'))}
                            </button>
                            <button type="button" role="menuitem" class="profile-menu-item" onclick="openSettingsModal(); closeProfileDropdown();">
                                <i class="fas fa-cog" aria-hidden="true"></i> ${_pmEsc(t('profile_menu.settings'))}
                            </button>
                            <div class="profile-menu-divider" role="separator"></div>
                            <button type="button" role="menuitem" class="profile-menu-item danger" onclick="handleLogout();">
                                <i class="fas fa-sign-out-alt" aria-hidden="true"></i> ${_pmEsc(t('profile_menu.logout'))}
                            </button>
                        </div>
                        <div class="profile-footer">
                            <span>WatcherDB V3.4</span>
                        </div>
                    `;
"""

FUNCOES_VELHAS = ("        function toggleProfileDropdown() {\n"
                  "            const dd = document.getElementById('userProfileDropdown');\n"
                  "            if (dd) dd.classList.toggle('show');\n"
                  "        }\n"
                  "\n"
                  "        function closeProfileDropdown() {\n"
                  "            const dd = document.getElementById('userProfileDropdown');\n"
                  "            if (dd) dd.classList.remove('show');\n"
                  "        }\n")

FUNCOES_NOVAS = r"""        // Menu de perfil (2026-09-14): padrao de botao de menu. Antes o gatilho e as opcoes eram <div> sem
        // foco nem papel, e quem usava so teclado nem conseguia abrir o menu. O mesmo padrao do sino (A2).
        function _pmEsc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
        }
        function _pmItens() {
            const dd = document.getElementById('userProfileDropdown');
            return dd ? Array.from(dd.querySelectorAll('[role="menuitem"]')) : [];
        }
        function openProfileDropdown(foco) {
            const dd = document.getElementById('userProfileDropdown');
            const badge = document.getElementById('userBadge');
            if (!dd) return;
            dd.classList.add('show');
            if (badge) badge.setAttribute('aria-expanded', 'true');
            const itens = _pmItens();
            if (itens.length) (foco === 'last' ? itens[itens.length - 1] : itens[0]).focus();
        }
        function toggleProfileDropdown() {
            const dd = document.getElementById('userProfileDropdown');
            if (!dd) return;
            if (dd.classList.contains('show')) closeProfileDropdown(false);
            else openProfileDropdown('first');
        }
        function closeProfileDropdown(devolverFoco) {
            const dd = document.getElementById('userProfileDropdown');
            const badge = document.getElementById('userBadge');
            if (dd) dd.classList.remove('show');
            if (badge) {
                badge.setAttribute('aria-expanded', 'false');
                // so no Escape: ao clicar numa opcao abre-se uma modal, e e ela que tem de ficar com o foco
                if (devolverFoco === true) badge.focus();
            }
        }
        function _pmKeydown(e) {
            const dd = document.getElementById('userProfileDropdown');
            if (!dd || !dd.classList.contains('show')) return;
            const itens = _pmItens();
            const i = itens.indexOf(document.activeElement);
            if (e.key === 'Escape') {
                e.preventDefault();
                closeProfileDropdown(true);          // fecha e devolve o foco ao gatilho
            } else if (e.key === 'Tab') {
                closeProfileDropdown(false);         // o Tab segue o seu caminho natural
            } else if (!itens.length) {
                return;
            } else if (e.key === 'ArrowDown') {
                e.preventDefault(); itens[(i + 1) % itens.length].focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault(); itens[(i - 1 + itens.length) % itens.length].focus();
            } else if (e.key === 'Home') {
                e.preventDefault(); itens[0].focus();
            } else if (e.key === 'End') {
                e.preventDefault(); itens[itens.length - 1].focus();
            }
        }
        document.addEventListener('keydown', _pmKeydown);
"""

EDITS = [
    # gatilho estatico com papel de botao de menu
    ('<div id="userBadge" class="user-badge" style="display: none;"></div>',
     '<div id="userBadge" class="user-badge" style="display: none;" role="button" tabindex="0" '
     'aria-haspopup="menu" aria-expanded="false" aria-controls="userProfileDropdown"></div>', 1),
    # 1) iniciais escapadas
    ("                const initials = (user.full_name || user.username || '?').substring(0, 2).toUpperCase();\n",
     "                // 2026-09-14: tudo o que vem do utilizador (e do Active Directory) passa por _pmEsc\n"
     "                const initials = _pmEsc((user.full_name || user.username || '?').substring(0, 2).toUpperCase());\n", 1),
    ("                        <div class=\"user-name\">${user.full_name || user.username}</div>\n"
     "                        <div class=\"user-role\">${user.role}</div>\n",
     "                        <div class=\"user-name\">${_pmEsc(user.full_name || user.username)}</div>\n"
     "                        <div class=\"user-role\">${_pmEsc(user.role)}</div>\n", 1),
    ("                    <i class=\"fas fa-chevron-down\" style=\"color: var(--color-border-strong); margin-left: 2px; font-size: 10px;\"></i>\n",
     "                    <i class=\"fas fa-chevron-down\" aria-hidden=\"true\" style=\"color: var(--color-border-strong); margin-left: 2px; font-size: 10px;\"></i>\n", 1),
    # 2) gatilho responde ao teclado
    ("                badge.onclick = function(e) { e.stopPropagation(); toggleProfileDropdown(); };\n",
     "                badge.onclick = function(e) { e.stopPropagation(); toggleProfileDropdown(); };\n"
     "                badge.setAttribute('aria-label', _kpiTp('profile_menu.aria', 'Menu do utilizador {name}', { name: user.full_name || user.username || '' }));\n"
     "                badge.onkeydown = function(e) {\n"
     "                    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') { e.preventDefault(); e.stopPropagation(); openProfileDropdown('first'); }\n"
     "                    else if (e.key === 'ArrowUp') { e.preventDefault(); e.stopPropagation(); openProfileDropdown('last'); }\n"
     "                };\n", 1),
    # 1) classe do papel so com caracteres seguros; departamento e cargo escapados (vem do AD)
    ("                    const roleCss = 'profile-role-' + (user.role || 'viewer');\n",
     "                    const roleCss = 'profile-role-' + String(user.role || 'viewer').replace(/[^a-z0-9_-]/gi, '');\n", 1),
    ("${user.department}</div>` : '';\n", "${_pmEsc(user.department)}</div>` : '';\n", 1),
    ("${user.title}</div>` : '';\n", "${_pmEsc(user.title)}</div>` : '';\n", 1),
    # clique fora sincroniza o aria-expanded
    ("            if (dd && dd.classList.contains('show') && !dd.contains(e.target) && !badge.contains(e.target)) {\n"
     "                dd.classList.remove('show');\n"
     "            }\n",
     "            if (dd && dd.classList.contains('show') && !dd.contains(e.target) && !badge.contains(e.target)) {\n"
     "                closeProfileDropdown(false);\n"
     "            }\n", 1),
    (FUNCOES_VELHAS, FUNCOES_NOVAS, 1),
    # CSS: repor o aspecto das opcoes agora <button> e foco visivel
    ("        .profile-menu-item:hover { background: rgba(59,130,246,0.08); color: var(--color-text-primary); }\n",
     "        /* 2026-09-14: as opcoes passaram de <div> a <button>; repor o aspecto e dar foco visivel */\n"
     "        button.profile-menu-item { width: 100%; background: none; border: none; text-align: left; font-family: inherit; }\n"
     "        .profile-menu-item:focus-visible { outline: 2px solid #3b82f6; outline-offset: -2px; background: rgba(59,130,246,0.08); color: var(--color-text-primary); }\n"
     "        .user-badge:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }\n"
     "        .profile-menu-item:hover { background: rgba(59,130,246,0.08); color: var(--color-text-primary); }\n", 1),
]

I18N = {
    "pt": {"aria": "Menu do utilizador {name}", "menu_label": "Opções do utilizador",
           "change_password": "Alterar palavra-passe", "settings": "Configurações", "logout": "Terminar sessão"},
    "en": {"aria": "User menu {name}", "menu_label": "User options",
           "change_password": "Change password", "settings": "Settings", "logout": "Sign out"},
    "es": {"aria": "Menú del usuario {name}", "menu_label": "Opciones del usuario",
           "change_password": "Cambiar contraseña", "settings": "Configuración", "logout": "Cerrar sesión"},
}
PTBR = {"aria": "Menu do usuário {name}", "menu_label": "Opções do usuário",
        "change_password": "Alterar senha", "logout": "Sair"}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Menu do perfil: segurança, teclado e texto** (owner 14/09). O nome, o e-mail, o papel, o departamento e o\n"
                  "  cargo entravam no HTML sem escapar; departamento e cargo vêm do Active Directory, logo um atributo com HTML\n"
                  "  corria no portal de quem abrisse o menu. Passam todos por escape. O gatilho e as opções eram `div` sem foco,\n"
                  "  e o menu não se abria com teclado: segue agora o padrão de botão de menu, com setas, Home e End, e o Escape\n"
                  "  fecha e devolve o foco ao gatilho. \"Alterar Senha\", \"Sair\" e \"Configuracoes\" passam a chaves em pt-PT,\n"
                  "  en e es, com as formas brasileiras no overlay pt-BR, e o rodapé deixa de dizer V3.3. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-14 -- menu de perfil: escape de dados do utilizador, padrao de botao de menu, texto e versao.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
UPD = PORTAL[PORTAL.index("function updateUserBadge(user)"):PORTAL.index("function _pmEsc(")]


def test_dados_do_utilizador_escapados():
    for campo in ("user.department", "user.title", "user.email || user.username", "user.role"):
        assert "${" + campo + "}" not in UPD, campo
    assert "${_pmEsc(user.department)}" in UPD and "${_pmEsc(user.title)}" in UPD
    assert "const initials = _pmEsc(" in UPD
    assert "replace(/[^a-z0-9_-]/gi, '')" in UPD   # classe CSS do papel


def test_gatilho_com_papel_de_botao_de_menu():
    for attr in ('role="button"', 'tabindex="0"', 'aria-haspopup="menu"', 'aria-expanded="false"',
                 'aria-controls="userProfileDropdown"'):
        assert attr in PORTAL[PORTAL.index('id="userBadge"'):PORTAL.index('id="userBadge"') + 260], attr
    assert "badge.onkeydown = function(e)" in UPD


def test_opcoes_sao_botoes_com_papel_de_menuitem():
    assert '<div class="profile-menu-item' not in UPD
    assert UPD.count('<button type="button" role="menuitem" class="profile-menu-item') == 6
    assert '<div class="profile-menu" role="menu"' in UPD


def test_escape_devolve_o_foco_e_clique_numa_opcao_nao():
    assert "if (e.key === 'Escape') {" in PORTAL and "closeProfileDropdown(true);" in PORTAL
    assert "if (devolverFoco === true) badge.focus();" in PORTAL
    assert "document.addEventListener('keydown', _pmKeydown);" in PORTAL


def test_texto_traduzido_e_versao_certa():
    assert "Alterar Senha" not in UPD and "Configuracoes" not in UPD and "> Sair" not in UPD
    assert "WatcherDB V3.3" not in UPD and "WatcherDB V3.4" in UPD
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["profile_menu"]
        for k in ("aria", "menu_label", "change_password", "settings", "logout"):
            assert d[k], (loc, k)
    br = json.loads((ROOT / "static" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))["profile_menu"]
    assert br["logout"] == "Sair" and br["change_password"] == "Alterar senha"
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    raw = src["portal"].read_bytes().decode("utf-8")
    if MARK in raw:
        print("[ABORT] ja aplicado"); return 1
    eol = "\r\n" if "\r\n" in raw else "\n"
    # substituir a regiao do dropdown.innerHTML por marcadores de inicio e fim
    ini, fim = DD_INI.replace("\n", eol), DD_FIM.replace("\n", eol)
    if raw.count(ini) != 1 or raw.count(fim) != 1:
        raise SystemExit(f"[ABORT] marcadores do dropdown: inicio {raw.count(ini)}x, fim {raw.count(fim)}x")
    a = raw.index(ini)
    b = raw.index(fim, a) + len(fim)
    raw = raw[:a] + DD_NOVO.replace("\n", eol) + raw[b:]
    out = {"portal": _apply(raw, EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        t = src[loc].read_bytes().decode("utf-8")
        if '"profile_menu"' in t:
            raise SystemExit(f"[ABORT] {loc}: profile_menu ja existe")
        corpo = ",\n".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in I18N[loc].items())
        out[loc] = _apply(t, [('\n  "toast": {', '\n  "profile_menu": {\n' + corpo + '\n  },\n  "toast": {', 1)], loc)
        json.loads(out[loc])
    tb = src["ptbr"].read_bytes().decode("utf-8")
    corpo = ",\n".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in PTBR.items())
    # pt-BR.json tem terminacoes corrompidas (\r\r\r\n): a ancora nao pode depender do que vem logo apos o "{"
    out["ptbr"] = _apply(tb, [('\n  "kpi_report": {', '\n  "profile_menu": {\n' + corpo + '\n  },\n  "kpi_report": {', 1)], "ptbr")
    json.loads(out["ptbr"])
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print(f"[ok] anchors: dropdown por marcadores; portal {len(EDITS)} blocos; i18n pt/en/es + overlay pt-BR (JSON valido); changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    compile(TEST_SRC, str(REL["test"]), "exec")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_menu_perfil_20260914.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
