"""TESTSUKITA TG-1c - asserções semânticas do dashboard de frota (council: afirma).

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
            # TG-1c PASSO 5: a mesma chamada que o onClick do cartao faz (portal ~34627-34635), sem depender
            # do DOM, que e' substituido a cada 30 s pelo refresh e fazia o clique real expirar.
            abriu = page.evaluate(
                """(kpiId) => {
                    const k = (window.KPI_METADATA || {})[kpiId];
                    if (!k || typeof showProblematicInstances !== 'function') return false;
                    let tipo = k.kpiType;
                    if ((kpiId.includes('-critical') || kpiId.includes('-warning')) &&
                        !(k.kpiType || '').includes('-critical') && !(k.kpiType || '').includes('-warning')) tipo = kpiId;
                    if (k.all) showProblematicInstances(tipo, k.modalTitle, true); else showProblematicInstances(tipo, k.modalTitle);
                    return true;
                }""",
                c["kpi"],
            )
            if not abriu:
                problemas.append(f"{c['kpi']}: sem entrada em KPI_METADATA ou showProblematicInstances ausente")
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
        assert 0 < depois["n"] <= total and depois["todos"], \
            f"filtro '{sub}' nao filtrou: {depois['n']}/{total} linhas, todos_contem={depois['todos']}"
        assert depois["contagem"].startswith(str(depois["n"]) + "/"), f"contagem nao acompanha: {depois['contagem']!r}"
        assert depois["foco"], "o input perdeu o foco ao filtrar (seccao recriada?)"
        assert vazio["n"] == 1 and vazio["texto"], f"sem estado vazio: {vazio}"
        assert not col.pageerrors and not col.http5xx
