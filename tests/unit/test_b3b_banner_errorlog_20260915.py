"""
2026-09-15 -- B3b: errorlog recente no banner de diagnostico da visao geral.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
FN = PORTAL[PORTAL.index("// B3b 2026-09-15: o mesmo bloco no banner"):PORTAL.index("const _OEL_BTN = ")]
LOAD = PORTAL[PORTAL.index("async function loadOfflineErrorlog("):PORTAL.index("function _oelRender(elId, d) {")]
OVERVIEW = PORTAL[PORTAL.index("async function renderOverview() {"):PORTAL.index("// Carregar card \"Reboot SO\" async")]


def test_carrega_sozinho_so_com_falha_total_ou_evento():
    banner = OVERVIEW[OVERVIEW.index("diagBanner = `"):OVERVIEW.index("const kpis = cacheIndicator + diagBanner")]
    assert "${offlineErrorlogBannerBlock(serverId, _hard || !!_evt)}`;" in banner
    assert "_oelBannerAuto = _hard || !!_evt;" in banner
    # irmao do banner: depois de fechar a div com a cor de severidade
    assert banner.index("</div>\n                        ${offlineErrorlogBannerBlock") > banner.index("overview.diag_perspective")
    assert "let _oelBannerAuto = false;" in OVERVIEW
    assert OVERVIEW.index("let _oelBannerAuto = false;") < OVERVIEW.index("_oelBannerAuto = _hard")


def test_carrega_depois_do_innerhtml_sem_await_pelo_meio():
    fim = OVERVIEW.rstrip()
    assert fim.endswith("if (diagBanner && _oelBannerAuto) loadOfflineErrorlog(offlineErrorlogId(serverId), 2);")
    depois_do_banner = OVERVIEW[OVERVIEW.index("const kpis = cacheIndicator + diagBanner"):]
    codigo = "\n".join(l for l in depois_do_banner.splitlines() if not l.strip().startswith("//"))
    assert "await " not in codigo


def test_recolhido_a_pedido_e_um_so_pedido():
    assert '<details id="${id}-wrap" ontoggle="_oelBannerToggle(this)"' in FN
    assert " open" not in FN.split("function _oelBannerToggle")[0]
    assert "if (el && !el.dataset.pedido) loadOfflineErrorlog(el.id, 2);" in FN
    assert "el.dataset.pedido = '1';" in LOAD
    assert "resumo.textContent = " in LOAD and "innerHTML" not in LOAD.split("const resumo = ")[1]
    assert "const embutido = !!document.getElementById(elId + '-wrap');" in PORTAL


def test_chaves_do_banner_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        ov = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["overview"]
        for k in ("banner_title", "banner_link", "banner_on_demand", "summary", "failed_short"):
            assert ov["offline_errorlog_" + k].strip(), (loc, k)
        assert "{n}" in ov["offline_errorlog_summary"] and "{s}" in ov["offline_errorlog_summary"], loc
