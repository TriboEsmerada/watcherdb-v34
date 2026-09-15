# -*- coding: utf-8 -*-
"""LIVE Waits (2026-09-15) -- ordenar deixa de esvaziar a tabela ate ao refresh seguinte.

Pedido do owner (captura do LIVE Waits em SQLHDSPRD406_I01): "quando eu clico para fazer o order by na coluna, demora
muito. poderia ter uma mensagem avisando que o order by esta sendo feito."

Causa (defeito da Wave S de 2026-05-29, nao do lote de hoje): o clique no cabecalho re-renderiza o ULTIMO payload em cache
(_liveSortClick -> _liveRenderProgram com _liveLastData). _liveRenderWaits calcula o delta contra _liveWaitsPrev, que no
render anterior ja tinha passado a ser esse mesmo payload: todos os deltas dao 0, o filtro "delta_tasks > 0" tira todas
as linhas e as colunas Delta desaparecem. A tabela fica so com cabecalhos ate ao refresh seguinte (15 s) -- era isso a
"demora". A ordenacao em si e instantanea; uma mensagem "a ordenar" so esconderia o defeito.

Correcao: o delta passa a ser calculado uma vez por leitura (timestamp e instancia do payload) e guardado em
_liveWaitsMemo; o re-render do sort reutiliza-o. Os dois pontos que reiniciam _liveWaitsPrev (mudar de canal ou de
programa) reiniciam tambem o memo.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LIVE_WAITS_SORT_2026-09-15_apply.py --check
  py docs/context/LIVE_WAITS_SORT_2026-09-15_apply.py
  py -m pytest tests/unit/test_live_waits_sort_20260915.py tests/unit/test_live_legivel_20260915.py tests/unit/test_live_typography_tokens.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_live_waits_sort_20260915.py"),
}
MARK = "_liveWaitsMemo"

DELTA_OLD = """            let deltaWaits = waits;
            if (_liveWaitsPrev) {
                const prevMap = {};
                _liveWaitsPrev.forEach(w => { prevMap[w.wait_type] = w; });
                deltaWaits = waits.map(w => {
                    const prev = prevMap[w.wait_type];
                    return { ...w, delta_tasks: prev ? (w.waiting_tasks_count - prev.waiting_tasks_count) : 0, delta_ms: prev ? (w.wait_time_ms - prev.wait_time_ms) : 0 };
                }).filter(w => w.delta_tasks > 0 || !_liveWaitsPrev).sort((a,b) => (b.delta_ms||0) - (a.delta_ms||0));
            }
            _liveWaitsPrev = waits;
"""
DELTA_NEW = """            let deltaWaits = waits;
            // 2026-09-15 (owner: "order by demora muito"): o clique no cabecalho re-renderiza o MESMO payload; recalcular o
            // delta contra ele proprio dava 0 em tudo e a tabela ficava vazia ate ao refresh seguinte. Delta uma vez por leitura.
            if (_liveWaitsMemo && _liveWaitsMemo.ts === data.timestamp && _liveWaitsMemo.inst === data.instance) {
                deltaWaits = _liveWaitsMemo.rows;
            } else {
                if (_liveWaitsPrev) {
                    const prevMap = {};
                    _liveWaitsPrev.forEach(w => { prevMap[w.wait_type] = w; });
                    deltaWaits = waits.map(w => {
                        const prev = prevMap[w.wait_type];
                        return { ...w, delta_tasks: prev ? (w.waiting_tasks_count - prev.waiting_tasks_count) : 0, delta_ms: prev ? (w.wait_time_ms - prev.wait_time_ms) : 0 };
                    }).filter(w => w.delta_tasks > 0 || !_liveWaitsPrev).sort((a,b) => (b.delta_ms||0) - (a.delta_ms||0));
                }
                _liveWaitsPrev = waits;
                _liveWaitsMemo = { ts: data.timestamp, inst: data.instance, rows: deltaWaits };
            }
"""

PORTAL_EDITS = [
    ("        let _liveWaitsPrev = null;\n",
     "        let _liveWaitsPrev = null;\n        let _liveWaitsMemo = null;   // 2026-09-15: delta dos Waits por leitura (o sort reutiliza)\n", 1),
    ("            _liveWaitsPrev = null;\n", "            _liveWaitsPrev = null;\n            _liveWaitsMemo = null;\n", 2),
    (DELTA_OLD, DELTA_NEW, 1),
]

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE Waits: ordenar deixa de esvaziar a tabela** (owner 15/09). O clique no cabeçalho recalculava a diferença\n"
                  "  contra a própria leitura, todas as linhas davam zero e desapareciam até ao refresh seguinte (15 s), o que parecia\n"
                  "  uma ordenação lenta. A diferença passa a ser calculada uma vez por leitura e a ordenação é imediata. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- LIVE Waits: o re-render da ordenacao reutiliza o delta da leitura em vez de o recalcular contra ela propria.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
WAITS = PORTAL[PORTAL.index("function _liveRenderWaits(data, tabId) {"):PORTAL.index("function _liveRenderBlocking(data) {")]


def test_delta_calculado_uma_vez_por_leitura():
    assert "_liveWaitsMemo.ts === data.timestamp && _liveWaitsMemo.inst === data.instance" in WAITS
    assert "deltaWaits = _liveWaitsMemo.rows;" in WAITS
    i_memo = WAITS.index("_liveWaitsMemo = { ts: data.timestamp")
    i_prev = WAITS.index("_liveWaitsPrev = waits;")
    assert i_prev < i_memo, "o prev so avanca quando chega uma leitura nova"
    assert WAITS.count("_liveWaitsPrev = waits;") == 1


def test_mudar_de_canal_ou_programa_reinicia_o_memo():
    assert "let _liveWaitsMemo = null;" in PORTAL
    assert PORTAL.count("            _liveWaitsPrev = null;\n            _liveWaitsMemo = null;\n") == 2
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
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    out = {"portal": _apply(portal, PORTAL_EDITS, "portal"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] portal 3 blocos (memo do delta dos Waits, 2 resets); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_waits_sort_20260915.py tests/unit/test_live_legivel_20260915.py "
          "tests/unit/test_live_typography_tokens.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
