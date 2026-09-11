"""UX-05 (2026-09-11): regressao estatica da barra de abas compacta abaixo de 1200 px."""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parents[2] / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_media_query_compacta_existe():
    m = re.search(r"UX-05 \(2026-09-11\).*?@media \(max-width: 1200px\) \{(.*?)\n        \}", PORTAL, re.S)
    assert m, "bloco UX-05 nao existe"
    bloco = m.group(1)
    assert ".nav-btn span { display: none; }" in bloco
    assert "text-overflow: ellipsis" in bloco and ".server-header h2" in bloco


def test_botoes_mantem_title_para_o_nome():
    # com o rotulo escondido abaixo de 1200 px, o title e' o nome acessivel do botao
    botoes = re.findall(r'<button class="nav-btn" data-tab="[a-z-]+"[^>]*>', PORTAL)
    assert len(botoes) == 16
    assert all('title="' in b for b in botoes), "botao da barra de abas sem title"
