"""PONTO 3 (11/09) - dois ajustes pequenos.

  a) Viewport: a 1093 px a barra de abas termina em 1196 px (corte, nao sobreposicao) - UX-05 medido a 10/09.
     O teste passa a afirmar "a barra de abas cabe na janela" (nav.right <= innerWidth), com a medida no JSON.
     ATENCAO: isto vai FALHAR a 1093x614 ate' o UX-05 ser corrigido no portal (nav so' icone < 1200 px).
     E' a intencao: o TestSukita passa a afirmar o achado todas as noites. A 1366x768 deve passar.
  b) Portal 15432: pedidos cancelados pela troca de aba (AbortError) registados como console.error -> 'info'.
     Achado P3 da noite 1 do TestSukita.

Uso (raiz do repo):  py docs/context/PONTO3_PASSO1_apply.py
Depois:              pwsh docs/context/PONTO3_PASSO2_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"
PORTAL = ROOT / "templates" / "watcherdb_portal.html"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


V_OLD = '''                           const sobrepoe = a.bottom > b.top && a.top < b.bottom && a.right > b.left && a.left < b.right;
                           return { sobrepoe, h: [a.left, a.top, a.right, a.bottom], nav: [b.left, b.top, b.right, b.bottom] }; }"""
            )
'''
V_NEW = '''                           const sobrepoe = a.bottom > b.top && a.top < b.bottom && a.right > b.left && a.left < b.right;
                           // PONTO 3 (11/09): UX-05 medido = a barra de abas e' CORTADA (nav.right > innerWidth), nao sobreposta
                           const cabe = b.right <= window.innerWidth + 1;
                           return { sobrepoe, cabe, innerWidth: window.innerWidth, h: [a.left, a.top, a.right, a.bottom], nav: [b.left, b.top, b.right, b.bottom] }; }"""
            )
'''
V_ASSERT_OLD = '''        if medidas.get("header"):
            assert not medidas["header"]["sobrepoe"], \\
                f"[{largura}x{altura}] o nome do servidor sobrepoe a barra de abas (UX-05): {medidas['header']}"
'''
V_ASSERT_NEW = '''        if medidas.get("header"):
            assert not medidas["header"]["sobrepoe"], \\
                f"[{largura}x{altura}] o nome do servidor sobrepoe a barra de abas (UX-05): {medidas['header']}"
            assert medidas["header"]["cabe"], \\
                f"[{largura}x{altura}] a barra de abas nao cabe na janela (UX-05, corte): nav.right={medidas['header']['nav'][2]} > innerWidth={medidas['header']['innerWidth']}"
'''

P_OLD = "                            debugLog(`[processResponse] ${label} - ERRO: ${error}`, 'error');\n"
P_NEW = ("                            // PONTO 3 (11/09): pedido cancelado pela troca de aba nao e' erro (ruido no TestSukita e para quem depura)\n"
         "                            debugLog(`[processResponse] ${label} - ERRO: ${error}`, (error && error.name === 'AbortError') ? 'info' : 'error');\n")


def main() -> None:
    s = SEM.read_text(encoding="utf-8")
    if "PONTO 3 (11/09)" in s:
        print("Ja aplicado: teste de viewport")
    else:
        s = rep(s, V_OLD, V_NEW, "viewport medida"); s = rep(s, V_ASSERT_OLD, V_ASSERT_NEW, "viewport assert")
        compile(s, str(SEM), "exec"); SEM.write_text(s, encoding="utf-8", newline="\n"); print("OK: tests/e2e/test_semantic_e2e.py (nav cabe na janela)")
    p = PORTAL.read_text(encoding="utf-8")
    if "PONTO 3 (11/09)" in p:
        print("Ja aplicado: portal")
    else:
        p = rep(p, P_OLD, P_NEW, "portal AbortError"); PORTAL.write_text(p, encoding="utf-8", newline="\n"); print("OK: templates/watcherdb_portal.html (AbortError -> info)")
    print("Proximo: pwsh docs/context/PONTO3_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
