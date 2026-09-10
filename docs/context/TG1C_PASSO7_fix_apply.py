"""TestGrapete TG-1c - PASSO 7: sem `networkidle` no login.

Corrida do PASSO 6 (16:2x): grupos e drill-down verdes nos 2 perfis; TestFiltroBases e TestViewport
1366x768 falharam com TimeoutError 30 s em wait_for_load_state("networkidle"). O portal faz polling
permanente (KPIs, toasts, LIVE), a rede nunca fica "idle" e o timeout dispara ao acaso. A espera util
ja existe a seguir (wait_for_function ate' o dashboard deixar de dizer "Carregando KPIs").

Uso (raiz do repo):  py docs/context/TG1C_PASSO7_fix_apply.py
Depois:              pwsh docs/context/TG1C_PASSO8_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"

OLD = '''    page.goto(f"{base_url}{PORTAL}", wait_until="load", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_function(
'''
NEW = '''    page.goto(f"{base_url}{PORTAL}", wait_until="load", timeout=30000)
    # TG-1c PASSO 7: sem "networkidle" - o portal faz polling permanente e nunca fica idle (timeouts ao acaso).
    page.wait_for_function(
'''


def main() -> None:
    k = SMOKE.read_text(encoding="utf-8")
    if "TG-1c PASSO 7" in k:
        print("Ja aplicado.")
        return
    if k.count(OLD) != 1:
        sys.exit(f"ABORT: bloco encontrado {k.count(OLD)}x.")
    k = k.replace(OLD, NEW)
    compile(k, str(SMOKE), "exec")
    SMOKE.write_text(k, encoding="utf-8", newline="\n")
    print("OK: tests/e2e/test_smoke_modules_e2e.py (login sem networkidle)")
    print("Proximo: pwsh docs/context/TG1C_PASSO8_commit.ps1")


if __name__ == "__main__":
    main()
