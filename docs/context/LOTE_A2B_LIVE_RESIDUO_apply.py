"""LOTE A-2b (pauta 1, ronda 2 do QA externo, 2026-09-05) - residuo do LIVE.

Ronda 2 mediu af3a505 servido na 8434: 35/36 folhas de texto do modal LIVE OK. Resta:
  (1) ecra de erro/sem-dados em _liveRefresh: `<div style="font-size:11px;">Programa: ... | Erro: ...`
      (unica folha < 12px; o teste do lote A-2 nao cobria o bloco _liveRefresh);
  (2) contentor #live-screen-${tabId} a 13px literal: >= 12 mas FORA da escala de tokens
      (12/14/16...), logo o gate da A-3 apanha-o assim que o modal estiver aberto na medicao.
      Passa a var(--font-sm) = 14px (a area de dados herda; as celulas de _liveRenderQueries
      fixam 12px inline, por isso a tabela nao muda).

Ancoras por TEXTO (unicas), nao por numero de linha. Idempotente. CRLF preservado.

Uso (raiz do repo):  py docs/context/LOTE_A2B_LIVE_RESIDUO_apply.py
Depois:              py -m pytest tests/unit/test_live_typography_tokens.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_live_typography_tokens.py"

EDITS = [
    ('font-size:11px;">Programa: ${_liveProgram}', 'font-size:12px;">Programa: ${_liveProgram}'),
    ("font-family:var(--font-mono);font-size:13px;", "font-family:var(--font-mono);font-size:var(--font-sm);"),
]

TEST_EXTRA = '''

def test_live_refresh_sem_texto_abaixo_de_12px(portal):
    # Ronda 2 do QA externo (2026-09-05): o ecra de erro/sem-dados vive em _liveRefresh,
    # fora dos blocos cobertos pelos testes anteriores.
    blk = _block(portal, "async function _liveRefresh(", "\\n        function _liveSortRows")
    pequenos = re.findall(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px em _liveRefresh: {pequenos}"


def test_live_screen_na_escala_de_tokens(portal):
    # 13px literal estava >= 12 mas fora da escala (gate A-3); agora token --font-sm.
    blk = _block(portal, "function openLiveMonitoringModal()", "function _openLiveAsModal")
    assert "font-family:var(--font-mono);font-size:var(--font-sm);" in blk
    # so' o contentor de dados; o rotulo "LIVE" do cabecalho continua a 13px de proposito
    assert "font-family:var(--font-mono);font-size:13px" not in blk
'''


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


raw = PORTAL.read_text(encoding="utf-8", newline="")
if all(new in raw and old not in raw for old, new in EDITS):
    print("portal: lote A-2b ja aplicado (skip)")
else:
    for old, _new in EDITS:
        if raw.count(old) != 1:
            abort(f"esperava 1x {old!r}, encontrei {raw.count(old)}")
    for old, new in EDITS:
        raw = raw.replace(old, new, 1)
    with PORTAL.open("w", encoding="utf-8", newline="") as fh:
        fh.write(raw)
    print("portal: 2 substituicoes ancoradas por texto")

tsrc = TEST.read_text(encoding="utf-8") if TEST.exists() else None
if tsrc is None:
    abort("tests/unit/test_live_typography_tokens.py nao existe -- corre primeiro o lote A-2")
if "test_live_refresh_sem_texto_abaixo_de_12px" in tsrc:
    print("teste: ja tem os 2 testes novos (skip)")
else:
    TEST.write_text(tsrc.rstrip("\n") + "\n" + TEST_EXTRA, encoding="utf-8")
    print("teste: +2 (7 no total)")

print("\nLOTE A-2b concluido. Correr:  py -m pytest tests/unit/test_live_typography_tokens.py -q --no-cov")
print("Depois: Restart-Service WatcherDBWebServiceV34; gate do QA: qa_ext_pauta1_fonts.py --login --live --reps 3")
