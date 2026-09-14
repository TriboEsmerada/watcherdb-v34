"""
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
