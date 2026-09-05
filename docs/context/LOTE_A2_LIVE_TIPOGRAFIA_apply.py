"""LOTE A-2 (pauta 1 do QA externo, 2026-09-05) - tipografia do modal LIVE em tokens.

Veredito do QA externo (docs/qa/externo/2026-09-05-pauta-1.md, A-2 PARCIAL/P1), concedido pelo
council: o contentor #live-screen-${tabId} (portal:50357) declara
font-family:'Cascadia Code',Consolas,monospace inline, logo tudo o que _liveRenderQueries
renderiza e' mono por heranca; 34/36 folhas de texto do modal estao a 10-11px (abaixo de
--font-xs = 12px) e os 23 controlos caem em Arial (default do UA).

Lote 1 aprovado pelo watcherdb-frontend-specialist (diff minimo; mono seletivo por coluna fica
para um lote 2 com decisao do owner):
  - tamanhos 10px/11px do shell e das celulas -> 12px (= --font-xs)
  - :50357 familia literal -> var(--font-mono), mantem 13px
  - bezel 'Courier New' -> var(--font-mono), 10/11px -> 12px
  - regra CSS longhand (NAO `font: inherit`, que e' shorthand e mexe em line-height):
      #live-tv-modal button, #live-tv-modal select, #live-tv-modal input
        { font-family: inherit; font-size: inherit; }
  - a barra de 14 programas pode passar a 2 linhas a 1366px (flex-wrap ja' existe): aceite;
    se incomodar, lote 2 move Sched/ErrLog/AG para um <select> "Mais".

Metodo: substituicoes ANCORADAS POR LINHA com verificacao do conteudo (font-size:10px aparece
309x no ficheiro; nunca substituir globalmente). Aborta se qualquer linha nao contiver o
fragmento esperado exactamente 1 vez. Idempotente: se tudo ja' estiver aplicado, sai com skip.

Validacao: scripts/qa/runtime/qa_ext_pauta1_fonts.py --login --live (gate do QA externo) +
tests/unit/test_live_typography_tokens.py (criado aqui: ratchet no fonte).

Uso (raiz do repo):  py docs/context/LOTE_A2_LIVE_TIPOGRAFIA_apply.py
Depois:              py -m pytest tests/unit/test_live_typography_tokens.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_live_typography_tokens.py"

MONO_LITERAL = "font-family:'Cascadia Code',Consolas,monospace"
COURIER_LITERAL = "font-family:'Courier New',monospace"
TOKEN_MONO = "font-family:var(--font-mono)"

# (linha 1-based, fragmento antigo, fragmento novo) -- linhas verificadas em 2026-09-05 (HEAD cb44328)
EDITS = [
    (50305, "font-size:10px;", "font-size:12px;"),   # _pb: 14 botoes de programa
    (50339, "font-size:10px;", "font-size:12px;"),   # rate-select
    (50343, "font-size:10px;", "font-size:12px;"),   # pause
    (50347, "font-size:11px;", "font-size:12px;"),   # gauges
    (50355, "font-size:10px;", "font-size:12px;"),   # status
    (50357, MONO_LITERAL, TOKEN_MONO),                 # #live-screen: familia em token (13px fica)
    (50415, COURIER_LITERAL, TOKEN_MONO),              # bezel titulo
    (50415, "font-size:11px;", "font-size:12px;"),
    (50418, COURIER_LITERAL, TOKEN_MONO),              # bezel relogio
    (50418, "font-size:10px;", "font-size:12px;"),
    (50419, "font-size:11px;", "font-size:12px;"),   # bezel: botoes Reduzir / Normal / Tela inteira /
    (50420, "font-size:11px;", "font-size:12px;"),   #        Pop-out / Fechar (medidos a 11px pelo QA)
    (50421, "font-size:11px;", "font-size:12px;"),
    (50422, "font-size:11px;", "font-size:12px;"),
    (50423, "font-size:11px;", "font-size:12px;"),
    (50799, "font-size:10px;", "font-size:12px;"),   # _liveRenderQueries badge idle
    (50800, "font-size:11px;", "font-size:12px;"),
    (50807, "font-size:11px;", "font-size:12px;"),
    (50808, "font-size:11px;", "font-size:12px;"),
    (50812, "font-size:11px;", "font-size:12px;"),
]

CSS_ANCHOR = "@keyframes live-pulse"
CSS_RULE = (
    "        /* LOTE A-2 2026-09-05: controlos dentro do modal LIVE herdam a fonte da app em vez do\n"
    "           default do UA (Arial). Longhand de proposito -- `font: inherit` e' shorthand e\n"
    "           reescreveria line-height/weight que os estilos inline ja' fixam. */\n"
    "        #live-tv-modal button, #live-tv-modal select, #live-tv-modal input { font-family: inherit; font-size: inherit; }\n"
)


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


# split("\n") e nao splitlines(): o ficheiro tem separadores Unicode ( /\x0c...) que
# splitlines() trata como quebra de linha e desalinham a numeracao face a sed/editores.
_raw = PORTAL.read_text(encoding="utf-8", newline="")
lines = [l + "\n" for l in _raw.split("\n")]
if _raw.endswith("\n"):
    lines.pop()  # o split deixa um elemento vazio no fim
else:
    lines[-1] = lines[-1][:-1]

# --- idempotencia: tudo ja aplicado? ---------------------------------------------------
already = all(new in lines[n - 1] and old not in lines[n - 1] for n, old, new in EDITS) and any(
    "#live-tv-modal button, #live-tv-modal select, #live-tv-modal input" in l for l in lines
)
if already:
    print("portal: lote A-2 ja aplicado (skip)")
else:
    # --- verificacao previa de TODAS as ancoras antes de tocar em qualquer linha ----------
    for n, old, _new in EDITS:
        if n > len(lines):
            abort(f"linha {n} nao existe ({len(lines)} linhas)")
        c = lines[n - 1].count(old)
        if c != 1:
            abort(f"linha {n}: esperava 1x {old!r}, encontrei {c}. Ficheiro mudou desde cb44328? Re-anchorar.")
    anchors = [i for i, l in enumerate(lines) if CSS_ANCHOR in l]
    if len(anchors) != 1:
        abort(f"anchor CSS {CSS_ANCHOR!r}: esperava 1, encontrei {len(anchors)}")

    # --- aplicar (de baixo para cima nao e' preciso: so' substituimos dentro da linha) ----
    for n, old, new in EDITS:
        lines[n - 1] = lines[n - 1].replace(old, new, 1)
    # regra CSS logo a seguir ao @keyframes live-pulse (mesmo bloco <style> do LIVE),
    # com o mesmo fim de linha do ficheiro (o portal e' CRLF integral: 57101 CRLF, 0 LF em 05/09)
    eol = "\r\n" if "\r\n" in _raw else "\n"
    lines.insert(anchors[0] + 1, CSS_RULE.replace("\n", eol))

    # newline="" para nao traduzir \n -> \r\n no Windows (o ficheiro e' LF; git autocrlf trata do resto)
    with PORTAL.open("w", encoding="utf-8", newline="") as fh:
        fh.write("".join(lines))
    print(f"portal: {len(EDITS)} substituicoes ancoradas + 1 regra CSS inserida apos a linha {anchors[0] + 1}")
    print("NOTA: a insercao da regra CSS desloca +4 linhas tudo abaixo de ~1175 -- as referencias")
    print("      50305..50812 deste lote passam a 50309..50816. O teste abaixo localiza por texto, nao por numero.")

# --- teste ratchet ---------------------------------------------------------------------
TEST_SRC = '''"""Ratchet do lote A-2 (2026-09-05): tipografia do modal LIVE em tokens.

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
    assert "id=\\"live-screen-${tabId}\\"" in blk
    assert "font-family:var(--font-mono)" in blk
    assert "'Cascadia Code',Consolas,monospace" not in blk


def test_shell_do_live_sem_texto_abaixo_de_12px(portal):
    blk = _block(portal, "function openLiveMonitoringModal()", "function _openLiveAsModal")
    pequenos = re.findall(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px no shell do LIVE: {pequenos}"


def test_bezel_sem_courier_e_sem_texto_pequeno(portal):
    blk = _block(portal, "function _openLiveAsModal", "function _liveLoadChannels")
    assert "'Courier New',monospace" not in blk
    pequenos = re.findall(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px no bezel: {pequenos}"


def test_render_queries_sem_texto_abaixo_de_12px(portal):
    blk = _block(portal, "function _liveRenderQueries(", "\\n        function _liveRender")
    pequenos = re.findall(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px em _liveRenderQueries: {pequenos}"


def test_controlos_do_modal_herdam_fonte(portal):
    assert re.search(
        r"#live-tv-modal button,\\s*#live-tv-modal select,\\s*#live-tv-modal input\\s*\\{\\s*font-family:\\s*inherit;\\s*font-size:\\s*inherit;\\s*\\}",
        portal,
    ), "regra font-family/font-size: inherit para controlos de #live-tv-modal em falta"
'''

if TEST.exists():
    print("teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("tests/unit/test_live_typography_tokens.py criado")

print("\nLOTE A-2 concluido. Correr:  py -m pytest tests/unit/test_live_typography_tokens.py -q --no-cov")
print("Depois (owner): Restart-Service WatcherDBWebServiceV34 e abrir o LIVE no browser -- barra de programas")
print("pode passar a 2 linhas a 1366px (aceite pelo frontend-specialist). Gate runtime: sessao 2,")
print("scripts/qa/runtime/qa_ext_pauta1_fonts.py --login --live.")
