"""FIX DB-FILTER (Overview > Bases) - PASSO 1: o filtro de nome nao filtrava.

Achado: TestSprite TC-003 (10/09) + verificacao de codigo (portal 16346/16408).
Causa: `oninput="renderDbTable(this.value)"` descarta o HTML devolvido; os cabecalhos de
ordenacao fazem `databases-section.innerHTML = renderDbTable(...)` e por isso funcionam.
Sem estado vazio: filtro sem resultado deixa o <tbody> em branco.

Correccao (minima, sem duplicar a logica de filtro/ordenacao):
  1. <tbody id="db-table-body"> e contagem em <span id="db-count">.
  2. applyDbFilter(valor): gera a seccao com renderDbTable(valor) num elemento solto e copia
     SO' o tbody e a contagem para o DOM -> o input nao e' recriado, foco e cursor mantem-se.
  3. oninput="applyDbFilter(this.value)".
  4. Linha de estado vazio (colspan 5) com chave i18n overview.no_databases_found (pt/en/es).
  5. Teste unitario estatico + caso e2e TestFiltroBases em test_semantic_e2e.py (TG-1c).

Pre-requisito: TG-1c PASSO 1 aplicado (test_semantic_e2e.py existe).
Uso (raiz do repo):  py docs/context/FIX_DBFILTER_PASSO1_apply.py
Depois:              pwsh docs/context/FIX_DBFILTER_PASSO2_commit.ps1
Propagacao V6: mesma funcao existe no portal V6? confirmar com grep 'renderDbTable' la'; prompt em CONTEXT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"
UNIT = ROOT / "tests" / "unit" / "test_overview_db_filter_20260910.py"
LOCALES = {
    "pt": ("Filtrar databases...", "Nenhuma base de dados encontrada"),
    "en": ("Filter databases...", "No databases found"),
    "es": ("Filtrar bases de datos...", "No se encontraron bases de datos"),
}
MARK = "FIX DB-FILTER 2026-09-10"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


P1_OLD = "' (' + filtered.length + '/' + window.dbTableData.length + ')</h4>"
P1_NEW = "' (<span id=\"db-count\">' + filtered.length + '/' + window.dbTableData.length + '</span>)</h4>"

P2_OLD = 'oninput="renderDbTable(this.value)"'
P2_NEW = 'oninput="applyDbFilter(this.value)"'

P3_OLD = "sortIcon('size') + '</th></tr></thead><tbody>' + rows + '</tbody></table></div></div>';"
P3_NEW = "sortIcon('size') + '</th></tr></thead><tbody id=\"db-table-body\">' + (rows || emptyRow) + '</tbody></table></div></div>';"

P4_OLD = """                            }).join('');

                            const sortIcon = (col) => {"""
P4_NEW = """                            }).join('');
                            // FIX DB-FILTER 2026-09-10: estado vazio explicito (antes o tbody ficava em branco)
                            const emptyRow = '<tr><td colspan="5" style="padding:14px 12px;text-align:center;color:var(--color-text-tertiary)">' + t('overview.no_databases_found') + '</td></tr>';

                            const sortIcon = (col) => {"""

P5_OLD = "                        window.renderDbTable = renderDbTable;\n"
P5_NEW = """                        // FIX DB-FILTER 2026-09-10 (TestSprite TC-003): o oninput chamava renderDbTable e descartava o
                        // HTML devolvido, logo o filtro nunca chegava ao DOM. Aqui gera-se a seccao num elemento solto e
                        // copia-se SO' o corpo da tabela e a contagem: o input nao e' recriado, foco e cursor mantem-se.
                        function applyDbFilter(valor) {
                            const tmp = document.createElement('div');
                            tmp.innerHTML = renderDbTable(valor || '');
                            const novoCorpo = tmp.querySelector('#db-table-body');
                            const corpo = document.getElementById('db-table-body');
                            if (novoCorpo && corpo) corpo.innerHTML = novoCorpo.innerHTML;
                            const novaContagem = tmp.querySelector('#db-count');
                            const contagem = document.getElementById('db-count');
                            if (novaContagem && contagem) contagem.textContent = novaContagem.textContent;
                        }
                        window.applyDbFilter = applyDbFilter;
                        window.renderDbTable = renderDbTable;
"""

UNIT_SRC = '''"""FIX DB-FILTER 2026-09-10: regressao estatica do filtro de bases do Overview.

Origem: TestSprite TC-003 ("servidor e bases respeitam o contexto") + leitura do codigo.
O oninput do campo chamava renderDbTable(this.value) e descartava o retorno; a ordenacao,
que faz innerHTML = renderDbTable(...), funcionava. Sem estado vazio.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_oninput_aplica_o_filtro_no_dom():
    assert 'oninput="applyDbFilter(this.value)"' in PORTAL
    assert 'oninput="renderDbTable(this.value)"' not in PORTAL, "regressao: o retorno de renderDbTable voltou a ser descartado"


def test_apply_db_filter_toca_so_corpo_e_contagem():
    m = re.search(r"function applyDbFilter\\(valor\\) \\{(.*?)\\n\\s*\\}\\n", PORTAL, re.S)
    assert m, "applyDbFilter nao existe"
    corpo = m.group(1)
    assert "getElementById('db-table-body')" in corpo and "getElementById('db-count')" in corpo
    assert "getElementById('databases-section')" not in corpo, "nao pode recriar a seccao (perde o foco do input)"


def test_tbody_e_contagem_tem_ids_e_estado_vazio():
    assert '<tbody id="db-table-body">' in PORTAL
    assert '<span id="db-count">' in PORTAL
    assert "const emptyRow = '<tr><td colspan=\\"5\\"" in PORTAL
    assert "t('overview.no_databases_found')" in PORTAL


def test_chave_i18n_nos_tres_locales():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert d["overview"]["no_databases_found"].strip(), loc
'''

SEM_ADD = '''

# FIX DB-FILTER 2026-09-10 (TC-003 do TestSprite, reproduzido em casa): o filtro de bases do Overview.
@pytest.mark.parametrize("perfil", [_perfil_param("viewer")])
class TestFiltroBases:
    def test_filtro_por_nome_filtra_e_mantem_o_foco(self, page, base_url, perfil):
        col = _smk.Colector(page, base_url)
        user = _smk._autentica(page, base_url, perfil)
        servidor = _smk._escolhe_servidor(page)
        if not servidor:
            pytest.skip("sem servidor de test/quality no inventario")
        page.evaluate("(sid) => { const s = allServers.find(x => x.server_id === sid); selectServer(s); }", servidor["server_id"])
        page.wait_for_selector("#db-filter-input", timeout=90000)
        page.wait_for_function("() => document.querySelectorAll('#db-table-body tr').length > 0", timeout=90000)
        total = page.evaluate("() => document.querySelectorAll('#db-table-body tr').length")
        primeiro = page.evaluate("() => (document.querySelector('#db-table-body tr td') || {}).innerText || ''").strip()
        sub = primeiro[:3]
        assert sub, "primeira linha sem nome de base"
        page.fill("#db-filter-input", sub)
        page.wait_for_timeout(300)
        depois = page.evaluate(
            """(sub) => { const rows = Array.from(document.querySelectorAll('#db-table-body tr'));
                          const nomes = rows.map(r => (r.querySelector('td') || {}).innerText || '');
                          return { n: rows.length, todos: nomes.every(x => x.toLowerCase().includes(sub.toLowerCase())),
                                   contagem: (document.getElementById('db-count') || {}).textContent || '',
                                   foco: document.activeElement && document.activeElement.id === 'db-filter-input' }; }""",
            sub,
        )
        page.fill("#db-filter-input", "zzz__nao_existe__zzz")
        page.wait_for_timeout(300)
        vazio = page.evaluate(
            """() => { const rows = document.querySelectorAll('#db-table-body tr');
                       return { n: rows.length, texto: rows.length ? rows[0].innerText.trim() : '' }; }"""
        )
        _smk._grava({
            "caso": "overview_filtro_bases", "perfil": perfil, "user": user, "server": servidor,
            "total": total, "sub": sub, "filtrado": depois, "vazio": vazio,
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "http5xx": col.http5xx,
            "warn": [], "dom_nodes": _smk._dom_nodes(page), "load_ms": 0,
        })
        assert 0 < depois["n"] <= total and depois["todos"], \\
            f"filtro '{sub}' nao filtrou: {depois['n']}/{total} linhas, todos_contem={depois['todos']}"
        assert depois["contagem"].startswith(str(depois["n"]) + "/"), f"contagem nao acompanha: {depois['contagem']!r}"
        assert depois["foco"], "o input perdeu o foco ao filtrar (seccao recriada?)"
        assert vazio["n"] == 1 and vazio["texto"], f"sem estado vazio: {vazio}"
        assert not col.pageerrors and not col.http5xx
'''


def main() -> None:
    p = PORTAL.read_text(encoding="utf-8")
    if MARK in p:
        print("Ja aplicado: portal")
    else:
        p = rep(p, P1_OLD, P1_NEW, "db-count")
        p = rep(p, P2_OLD, P2_NEW, "oninput")
        p = rep(p, P3_OLD, P3_NEW, "tbody")
        p = rep(p, P4_OLD, P4_NEW, "emptyRow")
        p = rep(p, P5_OLD, P5_NEW, "applyDbFilter")
        PORTAL.write_text(p, encoding="utf-8", newline="\n")
        print("OK: templates/watcherdb_portal.html (5 edicoes)")

    for loc, (ancora, texto) in LOCALES.items():
        f = ROOT / "static" / "i18n" / f"{loc}.json"
        t = f.read_text(encoding="utf-8")
        if '"no_databases_found"' in t:
            print(f"Ja existe: {loc}.json")
            continue
        old = f'    "filter_databases": "{ancora}",\n'
        new = old + f'    "no_databases_found": "{texto}",\n'
        t = rep(t, old, new, f"i18n {loc}")
        json.loads(t)  # continua JSON valido
        f.write_text(t, encoding="utf-8", newline="\n")
        print(f"OK: static/i18n/{loc}.json (+overview.no_databases_found)")

    if UNIT.exists():
        print("Ja existe: teste unitario")
    else:
        compile(UNIT_SRC, str(UNIT), "exec")
        UNIT.write_text(UNIT_SRC, encoding="utf-8", newline="\n")
        print("OK: tests/unit/test_overview_db_filter_20260910.py")

    if not SEM.exists():
        sys.exit("ABORT: tests/e2e/test_semantic_e2e.py nao existe (aplicar TG-1c PASSO 1 primeiro).")
    s = SEM.read_text(encoding="utf-8")
    if "TestFiltroBases" in s:
        print("Ja existe: TestFiltroBases")
    else:
        compile(s + SEM_ADD, str(SEM), "exec")
        SEM.write_text(s + SEM_ADD, encoding="utf-8", newline="\n")
        print("OK: tests/e2e/test_semantic_e2e.py (+TestFiltroBases)")
    print("Proximo: pwsh docs/context/FIX_DBFILTER_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
