"""UX-05 (relatorio QA + medicao TestSukita 10/09) - PASSO 1: barra de abas cabe na janela da persona.

Medido: a 1093 px CSS (1366x768 @125%, portatil corporativo) a barra de abas terminava em 1196 px: os
ultimos botoes ficavam fora do ecra (corte, nao sobreposicao). Sidebar fixa 320 px + 15 botoes com rotulo
em 2 filas de ~918 px.

Correccao (so' CSS, inserida a seguir a `.nav-btn.active i`):
  @media (max-width: 1200px): botoes so' com icone (o `title` de cada botao ja' da' o nome; o <span> com
  o rotulo i18n fica escondido), botoes com largura minima e centrados, nome do servidor trunca com
  reticencias. Acima de 1200 px nada muda.

Prova: TestViewport a 1093x614 (tests/e2e/test_semantic_e2e.py) afirma nav.right <= innerWidth desde fd0d7f0
e falhava; passa a passar. Teste estatico novo garante que a regra existe.

Uso (raiz do repo):  py docs/context/UX05_NAV_PASSO1_apply.py
Depois:              pwsh docs/context/UX05_NAV_PASSO2_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_ux05_nav_compacta_20260911.py"
MARK = "UX-05 (2026-09-11)"

ANCHOR = "        .nav-btn.active i {\n            color: #3b82f6;\n        }\n"
CSS = ANCHOR + """        /* UX-05 (2026-09-11): a 1093 px CSS (1366x768 @125%) a barra de abas terminava em 1196 px e cortava os
           ultimos botoes. Abaixo de 1200 px: so' icone (o title da' o nome), botoes compactos, nome do servidor
           trunca. Medido pelo TestSukita (TestViewport) todas as noites. */
        @media (max-width: 1200px) {
            .server-header.show { gap: var(--space-sm); }
            .server-header h2 { max-width: 34vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .nav-btn span { display: none; }
            .nav-btn { padding: var(--space-xs); min-width: 34px; justify-content: center; }
            .nav-btn i { font-size: var(--font-sm); }
        }
"""

TEST_SRC = '''"""UX-05 (2026-09-11): regressao estatica da barra de abas compacta abaixo de 1200 px."""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parents[2] / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_media_query_compacta_existe():
    m = re.search(r"UX-05 \\(2026-09-11\\).*?@media \\(max-width: 1200px\\) \\{(.*?)\\n        \\}", PORTAL, re.S)
    assert m, "bloco UX-05 nao existe"
    bloco = m.group(1)
    assert ".nav-btn span { display: none; }" in bloco
    assert "text-overflow: ellipsis" in bloco and ".server-header h2" in bloco


def test_botoes_mantem_title_para_o_nome():
    # com o rotulo escondido abaixo de 1200 px, o title e' o nome acessivel do botao
    botoes = re.findall(r'<button class="nav-btn" data-tab="[a-z-]+"[^>]*>', PORTAL)
    assert len(botoes) == 16
    assert all('title="' in b for b in botoes), "botao da barra de abas sem title"
'''


def main() -> None:
    p = PORTAL.read_text(encoding="utf-8")
    if MARK in p:
        print("Ja aplicado: portal")
    else:
        if p.count(ANCHOR) != 1:
            sys.exit(f"ABORT: ancora encontrada {p.count(ANCHOR)}x.")
        PORTAL.write_text(p.replace(ANCHOR, CSS), encoding="utf-8", newline="\n")
        print("OK: templates/watcherdb_portal.html (+media 1200px)")
    if TEST.exists():
        print("Ja existe: teste")
    else:
        compile(TEST_SRC, str(TEST), "exec")
        TEST.write_text(TEST_SRC, encoding="utf-8", newline="\n")
        print("OK: tests/unit/test_ux05_nav_compacta_20260911.py")
    print("Proximo: pwsh docs/context/UX05_NAV_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
