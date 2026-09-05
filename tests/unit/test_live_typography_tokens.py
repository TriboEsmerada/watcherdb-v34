"""Ratchet do lote A-2 (2026-09-05): tipografia do modal LIVE em tokens.

Localiza os blocos por texto (nao por numero de linha) para sobreviver a insercoes acima.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parents[2] / "templates" / "watcherdb_portal.html"


@pytest.fixture(scope="module")
def portal() -> str:
    return PORTAL.read_text(encoding="utf-8")


def _block(src: str, start_marker: str, end_marker: str) -> str:
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def test_live_screen_usa_token_mono(portal):
    blk = _block(portal, "function openLiveMonitoringModal()", "function _openLiveAsModal")
    assert "id=\"live-screen-${tabId}\"" in blk
    assert "font-family:var(--font-mono)" in blk
    assert "'Cascadia Code',Consolas,monospace" not in blk


def test_shell_do_live_sem_texto_abaixo_de_12px(portal):
    blk = _block(portal, "function openLiveMonitoringModal()", "function _openLiveAsModal")
    pequenos = re.findall(r"font-size:\s*(?:[0-9]|1[01])(?:\.\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px no shell do LIVE: {pequenos}"


def test_bezel_sem_courier_e_sem_texto_pequeno(portal):
    blk = _block(portal, "function _openLiveAsModal", "function _liveLoadChannels")
    assert "'Courier New',monospace" not in blk
    pequenos = re.findall(r"font-size:\s*(?:[0-9]|1[01])(?:\.\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px no bezel: {pequenos}"


def test_render_queries_sem_texto_abaixo_de_12px(portal):
    blk = _block(portal, "function _liveRenderQueries(", "\n        function _liveRender")
    pequenos = re.findall(r"font-size:\s*(?:[0-9]|1[01])(?:\.\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px em _liveRenderQueries: {pequenos}"


def test_controlos_do_modal_herdam_fonte(portal):
    assert re.search(
        r"#live-tv-modal button,\s*#live-tv-modal select,\s*#live-tv-modal input\s*\{\s*font-family:\s*inherit;\s*font-size:\s*inherit;\s*\}",
        portal,
    ), "regra font-family/font-size: inherit para controlos de #live-tv-modal em falta"


def test_live_refresh_sem_texto_abaixo_de_12px(portal):
    # Ronda 2 do QA externo (2026-09-05): o ecra de erro/sem-dados vive em _liveRefresh,
    # fora dos blocos cobertos pelos testes anteriores.
    blk = _block(portal, "async function _liveRefresh(", "\n        function _liveSortRows")
    pequenos = re.findall(r"font-size:\s*(?:[0-9]|1[01])(?:\.\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px em _liveRefresh: {pequenos}"


def test_live_screen_na_escala_de_tokens(portal):
    # 13px literal estava >= 12 mas fora da escala (gate A-3); agora token --font-sm.
    blk = _block(portal, "function openLiveMonitoringModal()", "function _openLiveAsModal")
    assert "font-family:var(--font-mono);font-size:var(--font-sm);" in blk
    # so' o contentor de dados; o rotulo "LIVE" do cabecalho continua a 13px de proposito
    assert "font-family:var(--font-mono);font-size:13px" not in blk
