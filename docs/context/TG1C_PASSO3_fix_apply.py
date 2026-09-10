"""TestGrapete TG-1c - PASSO 3: drill-down por clique real.

1.a corrida do semantico (10/09): "sem handler de clique" nos 6 cartoes. O portal esvazia
window._kpiCardClickHandlers logo depois de ligar os listeners (portal ~36567), por isso a lista
esta' vazia quando o teste a consulta. Corrigido: clique real no .kpi-value do cartao, que e' o
caminho do utilizador (o listener verifica mousedown/click no mesmo sitio; Playwright faz isso).

Uso (raiz do repo):  py docs/context/TG1C_PASSO3_fix_apply.py
Depois:              pwsh docs/context/TG1C_PASSO4_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"

OLD = '''            abriu = page.evaluate(
                """(id) => { const h = (window._kpiCardClickHandlers || []).find(x => x.cardId === id);
                            if (!h) return false; eval(h.onClick); return true; }""",
                c["cardId"],
            )
            if not abriu:
                problemas.append(f"{c['kpi']}: sem handler de clique")
                continue
'''
NEW = '''            # TG-1c PASSO 3: clique real (o portal esvazia _kpiCardClickHandlers depois de ligar os listeners).
            alvo = page.locator(f"#{c['cardId']} .kpi-value")
            if alvo.count() == 0:
                problemas.append(f"{c['kpi']}: cartao sem .kpi-value para clicar")
                continue
            alvo.first.click()
'''


def main() -> None:
    s = SEM.read_text(encoding="utf-8")
    if "TG-1c PASSO 3" in s:
        print("Ja aplicado.")
        return
    if s.count(OLD) != 1:
        sys.exit(f"ABORT: bloco do clique encontrado {s.count(OLD)}x, esperava 1.")
    s = s.replace(OLD, NEW)
    compile(s, str(SEM), "exec")
    SEM.write_text(s, encoding="utf-8", newline="\n")
    print("OK: tests/e2e/test_semantic_e2e.py (clique real)")
    print("Proximo: pwsh docs/context/TG1C_PASSO4_commit.ps1")


if __name__ == "__main__":
    main()
