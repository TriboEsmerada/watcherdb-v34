"""TestGrapete TG-1c - PASSO 1: asserções semânticas (o que o TestSprite mede e o smoke não).

Origem: TestSprite do owner (10/09) com TC-003 "servidor e bases respeitam o contexto" FAILED,
TC-006 desktop, TC-007..014 grupos de KPI. O smoke prova que o portal não rebenta; isto prova que
mostra a coisa certa, com invariantes baratos e sem crawler.

O que escreve:
  1. tests/e2e/test_smoke_modules_e2e.py: +1 asserção por aba (TC-003): a aba activa pertence ao
     servidor escolhido e o cabeçalho #serverName mostra o nome dele.
  2. tests/e2e/test_semantic_e2e.py (novo):
       - TestGruposKPI: cada grupo do dashboard tem cartões e cada cartão tem valor (número, K ou N/D),
         nunca vazio/undefined/NaN (TC-007..014).
       - TestDrilldown: os N primeiros cartões (WATCHERDB_QA_DRILL_MAX, default 6) abrem a modal
         #instancesModal; cartão > 0 => modal com conteúdo; valor e linhas gravados no JSON (FE-E2E-02
         em modo registo: a igualdade exacta depende do KPI, humanos e ratchet comparam).
       - TestViewport: dashboard e uma aba a 1093x614 (1366x768 @125%, persona) sem scroll horizontal (TC-006).
  3. scripts/qa/nightly_testgrapete.ps1: corre também o ficheiro novo.
  4. PLANO: linha TG-1c.

Uso (raiz do repo):  py docs/context/TG1C_PASSO1_apply.py
Depois:              pwsh docs/context/TG1C_PASSO2_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"
SEM = ROOT / "tests" / "e2e" / "test_semantic_e2e.py"
NIGHTLY = ROOT / "scripts" / "qa" / "nightly_testgrapete.ps1"
PLANO = ROOT / "docs" / "context" / "PLANO_TESTGRAPETE_2026-09-09.md"
MARK = "TESTGRAPETE TG-1c"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


# ---------- 1. smoke: contexto da aba (TC-003) ----------
S_OLD = '''        load_ms = int((time.time() - t0) * 1000)
        conteudo = page.evaluate(
'''
S_NEW = '''        load_ms = int((time.time() - t0) * 1000)
        # TESTGRAPETE TG-1c (TC-003 do TestSprite): a aba activa e' DESTE servidor e o cabecalho diz o nome dele.
        ctx = page.evaluate(
            """() => { const t = openTabs.get(activeTabId); const h = document.getElementById('serverName');
                       return { sid: t && t.server ? t.server.server_id : null, tipo: t ? t.tabType : null,
                                header: h ? (h.innerText || '').trim() : '' }; }"""
        )
        conteudo = page.evaluate(
'''
S_OLD2 = '''            "tab_id": tab_id, "load_ms": load_ms, "dom_nodes": _dom_nodes(page),
'''
S_NEW2 = '''            "tab_id": tab_id, "load_ms": load_ms, "dom_nodes": _dom_nodes(page), "contexto": ctx,
'''
S_OLD3 = '''        assert tab_id and page.evaluate("(tid) => !!document.getElementById('tab-content-' + tid)", tab_id), \\
            f"[{perfil}/{tab}] a aba nao foi criada (activeTabId={tab_id!r}; showTab sem servidor seleccionado?)"
'''
S_NEW3 = '''        assert tab_id and page.evaluate("(tid) => !!document.getElementById('tab-content-' + tid)", tab_id), \\
            f"[{perfil}/{tab}] a aba nao foi criada (activeTabId={tab_id!r}; showTab sem servidor seleccionado?)"
        assert ctx["sid"] == servidor["server_id"] and ctx["tipo"] == tab, \\
            f"[{perfil}/{tab}] contexto errado: aba activa e' {ctx['tipo']!r} de {ctx['sid']!r}, esperado {tab!r} de {servidor['server_id']!r}"
        assert servidor["name"].split("\\\\")[0].lower() in ctx["header"].lower(), \\
            f"[{perfil}/{tab}] cabecalho nao mostra o servidor escolhido: {ctx['header']!r} vs {servidor['name']!r}"
'''

# ---------- 2. ficheiro novo ----------
SEM_SRC = r'''"""TESTGRAPETE TG-1c - asserções semânticas do dashboard de frota (council: afirma).

Complementa o smoke (que só prova "não rebenta") com o que o TestSprite mede:
  - TestGruposKPI  (TC-007..014): cada grupo tem cartões; cada cartão tem valor legível.
  - TestDrilldown  (FE-E2E-02):   cartão abre modal; cartão > 0 => modal com conteúdo; números gravados.
  - TestViewport   (TC-006):      1093x614 (persona 1366x768 @125%) sem scroll horizontal.

Reutiliza login/servidor/evidências do smoke. Corre com o mesmo .env.qa.
  py -m pytest tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -v
"""
from __future__ import annotations

import importlib.util
import os
import re
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_spec = importlib.util.spec_from_file_location("smoke_helpers", Path(__file__).with_name("test_smoke_modules_e2e.py"))
_smk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smk)

PERFIS = _smk.PERFIS
DRILL_MAX = int(os.getenv("WATCHERDB_QA_DRILL_MAX", "6"))
MODAL_TIMEOUT_MS = int(os.getenv("WATCHERDB_QA_MODAL_TIMEOUT_MS", "60000"))
VALOR_OK = re.compile(r"^(\d+([.,]\d+)?K?|N/?[DA]|--|-)$", re.I)


def _perfil_param(p):
    return _smk._perfil_param(p)


def _espera_dashboard(page):
    page.wait_for_function(
        "() => document.querySelectorAll('.kpi-category-group .kpi-card').length > 0", timeout=90000
    )


@pytest.mark.parametrize("perfil", [_perfil_param(p) for p in PERFIS])
class TestGruposKPI:
    def test_cada_grupo_tem_cartoes_com_valor(self, page, base_url, perfil):
        col = _smk.Colector(page, base_url)
        user = _smk._autentica(page, base_url, perfil)
        _espera_dashboard(page)
        grupos = page.evaluate(
            """() => Array.from(document.querySelectorAll('.kpi-category-group')).map(g => ({
                 titulo: (g.querySelector('h3') ? g.querySelector('h3').innerText : '').trim(),
                 cartoes: Array.from(g.querySelectorAll('.kpi-card')).map(c => ({
                   id: c.dataset.kpiId, valor: (c.querySelector('.kpi-value') ? c.querySelector('.kpi-value').innerText : '').trim()
                 }))
               }))"""
        )
        problemas = []
        for g in grupos:
            if not g["cartoes"]:
                problemas.append(f"grupo {g['titulo']!r} sem cartoes")
            for c in g["cartoes"]:
                if not VALOR_OK.match(c["valor"] or ""):
                    problemas.append(f"{g['titulo']}/{c['id']}: valor ilegivel {c['valor']!r}")
        _smk._grava({
            "caso": "kpi_grupos", "perfil": perfil, "user": user, "grupos": grupos,
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "http5xx": col.http5xx,
            "warn": [], "dom_nodes": _smk._dom_nodes(page), "load_ms": 0,
        })
        assert len(grupos) >= 5, f"[{perfil}] so' {len(grupos)} grupos de KPI no dashboard"
        assert not problemas, f"[{perfil}] grupos/cartoes:\n  - " + "\n  - ".join(problemas[:12])
        assert not col.pageerrors and not col.http5xx, f"[{perfil}] erros: {col.pageerrors[:3]} {col.http5xx[:3]}"


@pytest.mark.parametrize("perfil", [_perfil_param(p) for p in PERFIS])
class TestDrilldown:
    def test_cartoes_de_topo_abrem_modal_com_conteudo(self, page, base_url, perfil):
        col = _smk.Colector(page, base_url)
        user = _smk._autentica(page, base_url, perfil)
        _espera_dashboard(page)
        cartoes = page.evaluate(
            """(n) => Array.from(document.querySelectorAll('.kpi-category-group .kpi-card')).slice(0, n).map(c => ({
                 cardId: c.id, kpi: c.dataset.kpiId,
                 valor: (c.querySelector('.kpi-value') ? c.querySelector('.kpi-value').innerText : '').trim() }))""",
            DRILL_MAX,
        )
        resultados, warn, problemas = [], [], []
        for c in cartoes:
            abriu = page.evaluate(
                """(id) => { const h = (window._kpiCardClickHandlers || []).find(x => x.cardId === id);
                            if (!h) return false; eval(h.onClick); return true; }""",
                c["cardId"],
            )
            if not abriu:
                problemas.append(f"{c['kpi']}: sem handler de clique")
                continue
            t0 = time.time()
            try:
                page.wait_for_function(
                    """() => { const b = document.getElementById('instancesModalBody'); if (!b) return false;
                               if (b.querySelector('.fa-spin')) return false;
                               return !/A carregar|Loading|Carregando/i.test((b.innerText || '').slice(0, 200)); }""",
                    timeout=MODAL_TIMEOUT_MS,
                )
            except Exception as exc:  # noqa: BLE001
                if "imeout" in str(exc) or "Timeout" in type(exc).__name__:
                    warn.append(f"{c['kpi']}: modal nao terminou em {MODAL_TIMEOUT_MS} ms")
                else:
                    pytest.fail(f"[{perfil}] erro do runner na modal de {c['kpi']}: {type(exc).__name__}: {exc}")
            info = page.evaluate(
                """() => { const b = document.getElementById('instancesModalBody'); const m = document.getElementById('instancesModal');
                           return { linhas: b ? b.querySelectorAll('tbody tr, tr[data-row], .modal-row').length : -1,
                                    texto: b ? (b.innerText || '').trim().length : -1,
                                    visivel: !!(m && getComputedStyle(m).display !== 'none') }; }"""
            )
            numero = re.match(r"^(\d+)", (c["valor"] or "").replace(",", ""))
            valor = int(numero.group(1)) if numero else None
            if c["valor"].upper().endswith("K") and numero:
                valor = int(float(c["valor"][:-1].replace(",", ".")) * 1000)
            resultados.append({"kpi": c["kpi"], "valor_cartao": c["valor"], "valor": valor,
                               "modal_linhas": info["linhas"], "modal_texto": info["texto"], "ms": int((time.time() - t0) * 1000)})
            if not info["visivel"]:
                problemas.append(f"{c['kpi']}: modal nao ficou visivel")
            elif valor and valor > 0 and info["linhas"] <= 0 and info["texto"] < 50:
                problemas.append(f"{c['kpi']}: cartao diz {c['valor']} mas a modal esta' vazia")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        _smk._grava({
            "caso": "drilldown_topo", "perfil": perfil, "user": user, "cartoes": resultados,
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "http5xx": col.http5xx,
            "warn": warn, "dom_nodes": _smk._dom_nodes(page), "load_ms": 0,
        })
        assert cartoes, f"[{perfil}] dashboard sem cartoes"
        assert not problemas, f"[{perfil}] drill-down:\n  - " + "\n  - ".join(problemas)
        assert not col.pageerrors and not col.http5xx, f"[{perfil}] erros: {col.pageerrors[:3]} {col.http5xx[:3]}"


@pytest.mark.parametrize("perfil", [_perfil_param("viewer")])
@pytest.mark.parametrize("largura,altura", [(1093, 614), (1366, 768)])
class TestViewport:
    def test_sem_scroll_horizontal(self, page, base_url, perfil, largura, altura):
        col = _smk.Colector(page, base_url)
        page.set_viewport_size({"width": largura, "height": altura})
        user = _smk._autentica(page, base_url, perfil)
        _espera_dashboard(page)
        medidas = {"dashboard": page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")}
        servidor = _smk._escolhe_servidor(page)
        if servidor:
            page.evaluate("(sid) => { const s = allServers.find(x => x.server_id === sid); selectServer(s); }", servidor["server_id"])
            page.wait_for_timeout(1500)
            medidas["overview"] = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
            medidas["header"] = page.evaluate(
                """() => { const h = document.getElementById('serverName'); const nav = document.querySelector('.nav-menu');
                           if (!h || !nav) return null; const a = h.getBoundingClientRect(), b = nav.getBoundingClientRect();
                           const sobrepoe = a.bottom > b.top && a.top < b.bottom && a.right > b.left && a.left < b.right;
                           return { sobrepoe, h: [a.left, a.top, a.right, a.bottom], nav: [b.left, b.top, b.right, b.bottom] }; }"""
            )
        _smk._grava({
            "caso": f"viewport_{largura}x{altura}", "perfil": perfil, "user": user, "medidas": medidas,
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "http5xx": col.http5xx,
            "warn": [], "dom_nodes": _smk._dom_nodes(page), "load_ms": 0,
        })
        for nome, (sw, iw) in ((k, v) for k, v in medidas.items() if isinstance(v, list)):
            assert sw <= iw + 1, f"[{largura}x{altura}] {nome}: scroll horizontal ({sw}px de conteudo em {iw}px)"
        if medidas.get("header"):
            assert not medidas["header"]["sobrepoe"], \
                f"[{largura}x{altura}] o nome do servidor sobrepoe a barra de abas (UX-05): {medidas['header']}"
'''

# ---------- 3. nightly ----------
N_OLD = "& py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -q `\n"
N_NEW = "& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -q `\n"

# ---------- 4. plano ----------
P_OLD = "| TG-2 | Job noturno:"
P_NEW = ("| TG-1c | Asserções semânticas (o que o TestSprite mede): contexto da aba no smoke (TC-003), grupos de KPI com valor "
         "(TC-007..014), drill-down dos cartões de topo com números gravados (FE-E2E-02), viewport 1093x614 sem scroll "
         "horizontal nem sobreposição do cabeçalho (TC-006/UX-05). tests/e2e/test_semantic_e2e.py | meio dia | "
         "Corrida na 8434 com viewer e dba verde; divergência com o TestSprite explicada |\n"
         "| TG-2 | Job noturno:")


def main() -> None:
    s = SMOKE.read_text(encoding="utf-8")
    if MARK in s:
        print("Ja aplicado: smoke")
    else:
        s = rep(s, S_OLD, S_NEW, "smoke ctx"); s = rep(s, S_OLD2, S_NEW2, "smoke json"); s = rep(s, S_OLD3, S_NEW3, "smoke assert")
        compile(s, str(SMOKE), "exec")
        SMOKE.write_text(s, encoding="utf-8", newline="\n"); print("OK: tests/e2e/test_smoke_modules_e2e.py (+contexto)")
    if SEM.exists():
        if MARK not in SEM.read_text(encoding="utf-8", errors="replace"):
            sys.exit("ABORT: test_semantic_e2e.py existe sem marcador."); print("Ja existe: test_semantic_e2e.py")
    else:
        compile(SEM_SRC, str(SEM), "exec"); SEM.write_text(SEM_SRC, encoding="utf-8", newline="\n"); print("OK: tests/e2e/test_semantic_e2e.py")
    n = NIGHTLY.read_text(encoding="utf-8")
    if "test_semantic_e2e.py" in n:
        print("Ja aplicado: nightly")
    else:
        NIGHTLY.write_text(rep(n, N_OLD, N_NEW, "nightly"), encoding="utf-8", newline="\n"); print("OK: nightly")
    p = PLANO.read_text(encoding="utf-8")
    if "| TG-1c |" in p:
        print("Ja aplicado: plano")
    else:
        PLANO.write_text(rep(p, P_OLD, P_NEW, "plano"), encoding="utf-8", newline="\n"); print("OK: plano")
    print("Proximo: pwsh docs/context/TG1C_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
