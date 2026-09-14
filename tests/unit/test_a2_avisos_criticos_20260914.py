"""
2026-09-14 -- A2: disciplina dos avisos criticos e sino com historico.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
POLL = PORTAL[PORTAL.index("async function pollCriticalKPIs()"):PORTAL.index("function isOnDashboardKPIs()")]


def test_d1_primeira_leitura_deixa_de_ser_silenciosa():
    assert "showCriticalSummaryToast(_activosNoArranque)" in POLL
    assert "critBellRecord(check, currentValue, previousValue, detail, {})" in POLL


def test_d2_estado_por_condicao_e_nao_por_valor():
    assert "let _toastLastFired = {};" in PORTAL
    assert "toastKey = `${check.key}_${currentValue}`" not in POLL
    # limpa sempre que volta a 0, fora do ramo de disparo
    assert "if (currentValue === 0) {\n                        delete _toastLastFired[check.key];" in POLL
    assert "currentValue > (_toastLastFired[check.key] || 0)" in POLL


def test_d2_texto_de_variacao_continua_a_usar_o_valor_anterior():
    # _toastPreviousState e _toastLastFired sao papeis distintos
    assert "_toastPreviousState[check.key] = currentValue;" in POLL
    assert "showCriticalToast(check, currentValue, previousValue, detail)" in POLL


def test_d3_suprimido_no_ecra_de_kpis_grava_como_lido():
    assert "critBellRecord(check, value, prevValue, detail, { suppressed: true });" in PORTAL
    assert "read: !!o.suppressed" in PORTAL


def test_sino_acessivel_e_no_sitio_certo():
    i_bell = PORTAL.index('id="criticalAlertsBell"')
    i_lang = PORTAL.index('id="headerLangSelector"')
    assert i_bell < i_lang, "o sino vai antes do selector de idioma"
    for attr in ('aria-haspopup="true"', 'aria-expanded="false"', 'aria-controls="critBellPanel"'):
        assert attr in PORTAL
    assert 'id="critBellLive" class="crit-bell-sr" aria-live="polite"' in PORTAL
    assert "if (e.key === 'Escape')" in PORTAL and "b.focus();" in PORTAL


def test_historico_em_localstorage_protegido():
    assert "try {\n                const v = JSON.parse(localStorage.getItem(CRIT_BELL_KEY)" in PORTAL
    assert "localStorage.setItem(CRIT_BELL_KEY, JSON.stringify(items.slice(0, CRIT_BELL_MAX)))" in PORTAL


def test_badge_pulsa_e_respeita_reduced_motion():
    assert "CRIT_BELL_STALE_MS = 30 * 60 * 1000" in PORTAL
    assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{ \.crit-bell-btn\.crit-bell-stale", PORTAL)


def test_stale_persistente_deixa_registo():
    assert "_toastStaleStreak++;" in POLL
    assert "critBellRecordMonitoringDown()" in POLL
    assert "_toastStaleStreak = 0;" in POLL


def test_drift_do_intervalo_corrigido():
    assert "(polling 60s)" not in PORTAL


def test_chaves_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        cb = d["crit_bell"]
        for k in ("title", "empty", "clear", "aria", "summary", "suppressed", "monitoring_down"):
            assert cb[k], (loc, k)
        assert "{n}" in cb["aria"] and "{n}" in cb["summary"], loc
