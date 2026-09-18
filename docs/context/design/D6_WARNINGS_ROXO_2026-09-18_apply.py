# -*- coding: utf-8 -*-
"""Design, lote D6 — número e ícone de WARNINGS do resumo executivo em roxo (owner, 18/09: "pode mudar a cor para roxo?").

Hoje o "1.413 WARNINGS" usa --sev-warning-text (laranja-castanho em Light) e o ícone --sev-warning-solid. O owner quer
roxo. O contrato não tem roxo; o D3 criou --coll-quiet-text/-tint só para a modal de Collectors. Este lote promove esse
roxo a token global --sev-violet-text/-tint nos 3 temas (dark #c4b5fd, light #6d28d9, HC #d9c8ff; ~7:1 sobre o tint)
e usa-o no resumo executivo. A modal de Collectors continua com os tokens locais (mesmos valores); unifica-se no codemod.

Só cor. Sem strings, sem lógica.

Uso (raiz do repo, ramo design/tokens-contrato):
  py docs/context/design/D6_WARNINGS_ROXO_2026-09-18_apply.py --check
  py docs/context/design/D6_WARNINGS_ROXO_2026-09-18_apply.py
  py -m pytest tests/test_exec_summary_redesign_smoke.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs nos 3 temas
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "--sev-violet-text"

EDITS = [
    # tokens nos 3 temas (a seguir a attention/overflow de cada bloco)
    ("""            --sev-attention-border: #eab308;--sev-attention-solid: #a16207;--sev-attention-on: #ffffff;
""", """            --sev-attention-border: #eab308;--sev-attention-solid: #a16207;--sev-attention-on: #ffffff;
            /* D6: roxo (warnings do resumo executivo; o mesmo do QUIET dos Collectors) */
            --sev-violet-text: #c4b5fd;     --sev-violet-tint: rgba(139,92,246,0.20);
""", 1),
    ("""            --sev-overflow-border: #b91c1c;  --sev-overflow-solid: #7c2d12;  --sev-overflow-on: #ffffff;
        }
""", """            --sev-overflow-border: #b91c1c;  --sev-overflow-solid: #7c2d12;  --sev-overflow-on: #ffffff;
            --sev-violet-text: #6d28d9;      --sev-violet-tint: rgba(139,92,246,0.12);
        }
""", 1),
    ("""            --sev-overflow-text: #ff9999;  --sev-overflow-tint: rgba(255,153,153,0.15);  --sev-overflow-border: #ff9999;  --sev-overflow-solid: #ff9999;  --sev-overflow-on: #000000;
        }
""", """            --sev-overflow-text: #ff9999;  --sev-overflow-tint: rgba(255,153,153,0.15);  --sev-overflow-border: #ff9999;  --sev-overflow-solid: #ff9999;  --sev-overflow-on: #000000;
            --sev-violet-text: #d9c8ff;  --sev-violet-tint: rgba(139,92,246,0.15);
        }
""", 1),
    # resumo executivo: icone e numero de warnings
    ("""        .rep-ico-warn { background:color-mix(in srgb, var(--sev-warning-solid) 15%, transparent); color:var(--sev-warning-solid); }""",
     """        .rep-ico-warn { background:var(--sev-violet-tint); color:var(--sev-violet-text); }   /* D6 (owner): warnings em roxo */""", 1),
    (""".rep-exec-stat b.warn { color:var(--sev-warning-text); }""", """.rep-exec-stat b.warn { color:var(--sev-violet-text); }""", 1),
]


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = base / PORTAL
    portal = src.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "D2 contrato" not in portal:
        print("[ABORT] o D2 nao esta aplicado neste template (ramo errado?)"); return 1
    novo = _apply(portal, EDITS, "warnings roxo")
    print(f"[ok] warnings em roxo: {len(EDITS)} blocos (tokens violet nos 3 temas, icone e numero do resumo executivo)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
