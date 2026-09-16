"""
2026-09-16 -- modal de instâncias offline: errorlog, link para o Overview e fim das comparações por título traduzido.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_sem_comparacoes_pelo_titulo_traduzido():
    assert "title === 'Instances OK'" not in PORTAL and "title === 'Instances Off'" not in PORTAL
    assert "const isOkFilter = _ehModalInstanciasOk(title);" in PORTAL
    assert "} else if (_ehModalInstanciasOffline(title)) {" in PORTAL
    assert "if (_ehModalInstanciasOk(title)) chartTitle = t('chart.instances_ok_by_env');" in PORTAL
    assert "_kpiT('kpi_meta.' + id + '.modal_title', fb)" in PORTAL


def test_resolucao_por_host_so_quando_e_unica():
    fn = PORTAL[PORTAL.index("function _kpiServidorDaLinha(nome) {"):PORTAL.index("function _kpiAbrirOverview(el) {")]
    assert "const host = alvo.split('_')[0];" in fn and "return doHost.length === 1 ? doHost[0] : null;" in fn
    drill = PORTAL[PORTAL.index("function _applyDrilldownAvailability(modalBody) {"):]
    drill = drill[:drill.index("\n        }\n")]
    assert "const found = !!_kpiServidorDaLinha(name);" in drill and "btn.remove();" in drill
    assert "allServers.some(s => candidates.some(c =>" not in PORTAL


def test_botao_overview_e_errorlog_recolhido_na_modal():
    assert 'class="kpi-overview-btn" onclick="event.stopPropagation(); _kpiAbrirOverview(this);"' in PORTAL
    assert "kpi_modal.open_overview" in PORTAL
    i = PORTAL.index("function toggleCardExpand(card) {")
    expand = PORTAL[i:PORTAL.index(chr(10) + "        function ", i)]
    assert "if (kt === 'instance-availability' && card.dataset.instanceName) {" in expand
    assert "offlineErrorlogBannerBlock(alvo, false, 'modal-'" in expand
    assert expand.index("_kpiServidorDaLinha(card.dataset.instanceName)") < expand.index("offlineErrorlogBannerBlock(")
    banner = PORTAL[PORTAL.index("function offlineErrorlogBannerBlock(instance, auto, sufixo) {"):PORTAL.index("function _oelBannerToggle")]
    assert '<summary onclick="event.stopPropagation();"' in banner
    assert "offlineErrorlogId(inst) + (sufixo ?" in banner


def test_chave_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert d["kpi_modal"]["open_overview"].strip(), loc
