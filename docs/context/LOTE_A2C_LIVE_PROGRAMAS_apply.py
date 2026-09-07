"""LOTE A-2c (pauta P4, A-4.1 do QA externo, 2026-09-07) - tipografia dos 13 programas do LIVE.

Medido pelo QA com DADOS REAIS (viewer, 6/6 medições): gate FAIL, 128-170 folhas < 12px em ~180-219
e 5 em "monospace" cru. O lote A-2 (05/09) cobriu o shell e _liveRenderQueries; os outros programas
(Fleet = por omissao, com 39 declaracoes; TempDB 8; Connections 5; Schedulers 4; ...) ficaram.

Aprovado pelo watcherdb-frontend-specialist (07/09):
  - regex ANCORADO em `font-size:\\s*(9|10|11)px` -> `font-size:12px` e `font-family:\\s*monospace\\b`
    (cru) -> `font-family:var(--font-mono)`, SO' dentro do intervalo das funcoes _liveRender*;
    nunca `9px|10px` solto (apanharia width/height:10px das barras de progresso).
  - _liveArrow() fica de fora: os 9px sao <i class="fas fa-sort" aria-hidden> (decoracao).
  - risco real = truncamento horizontal em colunas fixas do Fleet (nowrap+ellipsis), nao overflow
    vertical (o contentor tem overflow:auto) -> larguras de coluna ficam para o lote A-2d.
  - nenhuma dependencia de padStart/repeat/tab no intervalo (grep vazio) => troca de familia segura.

Idempotente; imprime o diff por funcao; aborta se o intervalo nao for encontrado ou se algo mudar
fora dele. CRLF preservado; numeracao por split("\\n") (o ficheiro tem 1 NEL U+0085).

Uso (raiz do repo):  py docs/context/LOTE_A2C_LIVE_PROGRAMAS_apply.py
Depois:              py -m pytest tests/unit/test_live_typography_tokens.py -q --no-cov
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_live_typography_tokens.py"

FUNC_RX = re.compile(r"^\s+(?:async )?function (\w+)\(")
SIZE_RX = re.compile(r"font-size:\s*(?:9|10|11)px")
MONO_RX = re.compile(r"font-family:\s*monospace\b")
MONO_LITERAL_RX = re.compile(r"font-family:\s*'Cascadia Code',\s*Consolas,\s*monospace")
FIRST_FUNC = "_liveRenderChannelOptions"
LAST_FUNC = "_liveRenderSchedulers"
EXCLUDE_FUNCS = {"_liveArrow"}


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


raw = PORTAL.read_text(encoding="utf-8", newline="")
lines = raw.split("\n")

# --- localizar funcoes (por texto, nao por numero de linha) ---------------------------
funcs = [(i, m.group(1)) for i, l in enumerate(lines) if (m := FUNC_RX.match(l))]
by_name = {name: i for i, name in funcs}
if FIRST_FUNC not in by_name or LAST_FUNC not in by_name:
    abort(f"nao encontrei {FIRST_FUNC} / {LAST_FUNC}")
start = by_name[FIRST_FUNC]
after_last = [i for i, _ in funcs if i > by_name[LAST_FUNC]]
end = after_last[0] if after_last else len(lines)  # exclusivo
if end - start < 500 or end - start > 2000:
    abort(f"intervalo suspeito: {end - start} linhas ({start + 1}-{end})")

# intervalos por funcao dentro do bloco, para relatorio e exclusoes
ranges = []
inblock = [(i, n) for i, n in funcs if start <= i < end]
for k, (i, n) in enumerate(inblock):
    j = inblock[k + 1][0] if k + 1 < len(inblock) else end
    ranges.append((n, i, j))

changed = {}
total = 0
for name, a, b in ranges:
    if name in EXCLUDE_FUNCS:
        continue
    c = 0
    for i in range(a, b):
        new = SIZE_RX.sub("font-size:12px", lines[i])
        new = MONO_LITERAL_RX.sub("font-family:var(--font-mono)", new)
        new = MONO_RX.sub("font-family:var(--font-mono)", new)
        if new != lines[i]:
            c += len(SIZE_RX.findall(lines[i])) + len(MONO_RX.findall(lines[i])) + len(MONO_LITERAL_RX.findall(lines[i]))
            lines[i] = new
    if c:
        changed[name] = c
        total += c

if total == 0:
    print("portal: lote A-2c ja aplicado (0 substituicoes) (skip)")
else:
    # garantia: fora do intervalo nada mudou (por construcao so' tocamos em [start,end))
    out = "\n".join(lines)
    before_outside = raw.split("\n")[:start] + raw.split("\n")[end:]
    after_outside = lines[:start] + lines[end:]
    if before_outside != after_outside:
        abort("alteracao fora do intervalo -- nao gravado")
    with PORTAL.open("w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    print(f"portal: {total} substituicoes em {len(changed)} funcoes (linhas {start + 1}-{end}):")
    for n, c in sorted(changed.items(), key=lambda x: -x[1]):
        print(f"   {n:28} {c}")
    print(f"   (excluidas: {', '.join(sorted(EXCLUDE_FUNCS))} -- icones de ordenacao, decoracao)")

# --- teste ratchet: todo o intervalo _liveRender* -----------------------------------------
TEST_EXTRA = '''

def _live_render_block(portal: str) -> str:
    # Todo o intervalo das funcoes _liveRender* (ChannelOptions .. Schedulers), excluindo _liveArrow
    # (icones de ordenacao <i aria-hidden>, decoracao). Localizado por texto.
    i = portal.index("function _liveRenderChannelOptions(")
    j = portal.index("function _liveRenderSchedulers(")
    k = re.search(r"\\n\\s+(?:async )?function \\w+\\(", portal[j + 40:])
    end = j + 40 + k.start() if k else len(portal)
    blk = portal[i:end]
    a = blk.find("function _liveArrow(")
    if a != -1:
        b = re.search(r"\\n\\s+(?:async )?function \\w+\\(", blk[a + 20:])
        blk = blk[:a] + (blk[a + 20 + b.start():] if b else "")
    return blk


def test_programas_do_live_sem_texto_abaixo_de_12px(portal):
    blk = _live_render_block(portal)
    pequenos = re.findall(r"font-size:\\s*(?:[0-9]|1[01])(?:\\.\\d+)?px", blk)
    assert pequenos == [], f"tamanhos < 12px nos programas do LIVE: {len(pequenos)} ({sorted(set(pequenos))})"


def test_programas_do_live_sem_monospace_cru(portal):
    blk = _live_render_block(portal)
    assert not re.search(r"font-family:\\s*monospace\\b", blk)
    assert "'Cascadia Code',Consolas,monospace" not in blk
'''

tsrc = TEST.read_text(encoding="utf-8") if TEST.exists() else None
if tsrc is None:
    abort("tests/unit/test_live_typography_tokens.py nao existe -- corre primeiro os lotes A-2/A-2b")
if "test_programas_do_live_sem_texto_abaixo_de_12px" in tsrc:
    print("teste: ja tem os 2 testes (skip)")
else:
    TEST.write_text(tsrc.rstrip("\n") + "\n" + TEST_EXTRA, encoding="utf-8")
    print("teste: +2 (9 no total)")

print("\nLOTE A-2c concluido. Correr:  py -m pytest tests/unit/test_live_typography_tokens.py -q --no-cov")
print("Depois: Restart-Service WatcherDBWebServiceV34; abrir o LIVE em Fleet e ver truncamentos (A-2d);")
print("gate do QA: qa_ext_pauta1_fonts.py --login --live --reps 3 (DPR 1.25 e 1.0).")
