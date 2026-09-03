"""
WatcherDB V3.3 — E2E (browser) do fix UX #1 (port do V6, sweep cross-product 2026-06-25).

Prova COMPORTAMENTO RUNTIME que o smoke string-based nao consegue: executa a JS de
producao real (_repExecCard) no portal carregado (chromium headless) contra o servico
vivo (8433).

  #1 link "Relatorio Tecnico" persistente em estado limpo (totalCrit==0)

Os outros achados (#2 deep-link AI, #3 i18n ask, #4 timeout/cancelar) NAO se aplicam ao
V3.3 Standard: AI e Pro-only (TIER GUARD) e o i18n usa motor key-lookup, nao nytLocalize.

Run (servico V3.3 a correr):  pytest tests/e2e/test_ux_fixes_e2e.py -v
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_mock]

PORTAL = "/watcherdb"


def _load_portal(page, base_url):
    # Estabilizado 2026-08-19: com `wait_until="load"` seguido de 15s a esperar
    # por _repExecCard, esta suite dava timeout em 2 a 3 dos 5 testes, e a
    # ROTACAO era aleatoria entre corridas -- num run falhava o alinhamento dos
    # numeros, no seguinte o tamanho do icone, e os achados nao se repetiam.
    # Achado instavel e' achado que ninguem trata.
    #
    # Esperar por `networkidle` antes da funcao, e dar 30s em vez de 15, REDUZ a
    # variancia mas NAO a elimina: em tres corridas seguidas deu 2, 4 e 2 falhas,
    # e o `TestFix1ReportLinkPersistent` continua a aparecer e desaparecer. A
    # causa residual fica por diagnosticar -- nao e' so' o tempo de espera.
    #
    # O que a mudanca tornou visivel, e vale mais do que a cura: dois testes
    # falham em TODAS as corridas (tamanho do icone e alinhamento dos numeros).
    # Esses sao achados reais, nao ruido, e estavam escondidos atras da rotacao
    # aleatoria de timeouts.
    page.goto(f"{base_url}{PORTAL}", wait_until="load", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_function("typeof _repExecCard === 'function'", timeout=30000)
    page.evaluate("() => { const o = document.getElementById('loginOverlay'); if (o) o.style.display = 'none'; }")


class TestFix1ReportLinkPersistent:
    """#1 — em estado limpo (totalCrit==0) o link para o Relatorio Tecnico tem de existir."""

    def test_clean_state_emits_persistent_link(self, page, base_url):
        _load_portal(page, base_url)
        html = page.evaluate("() => _repExecCard({}, {env:[],cat:[],sev:'ALL'}, null, false)")
        assert "rep-exec-link" in html, "estado limpo nao emitiu o link persistente"
        assert "openKpiReport()" in html, "link nao aponta para openKpiReport()"

    def test_inside_report_has_no_self_link(self, page, base_url):
        _load_portal(page, base_url)
        html = page.evaluate("() => _repExecCard({}, {env:[],cat:[],sev:'ALL'}, null, true)")
        assert "openKpiReport()" not in html, "relatorio nao deve ter auto-link"


class TestExecIconsRender:
    """Regressao (2026-06-26): os 5 icones do Resumo Executivo apareciam VAZIOS porque a
    regra da label `.rep-exec-stat span` (espec. 0,1,1) atropelava o `.rep-exec-ico` (span,
    0,1,0) -> display:block + font-size:11px = icone minusculo no canto. Fix: `.rep-exec-txt span`."""

    def test_icons_centered_sized_and_glyph_present(self, page, base_url):
        _load_portal(page, base_url)
        m = page.evaluate(
            """() => {
                const d = document.createElement('div');
                d.innerHTML = _repExecCard({}, {env:[],cat:[],sev:'ALL'}, null, false);
                document.body.appendChild(d);
                const span = d.querySelector('.rep-exec-ico');
                const i = d.querySelector('.rep-exec-ico i');
                const cs = getComputedStyle(span);
                const before = i ? getComputedStyle(i, '::before') : null;
                const r = {
                    hasIcon: !!i, display: cs.display, fontSize: parseFloat(cs.fontSize),
                    glyph: before ? before.content : null, glyphFont: before ? before.fontFamily : null,
                };
                d.remove();
                return r;
            }"""
        )
        assert m["hasIcon"], "sem <i> dentro de .rep-exec-ico"
        # flex-item blockifica inline-flex->flex; o bug era display:block (nao centra)
        assert m["display"] in ("inline-flex", "flex"), f"icone nao centra: display={m['display']} (bug .rep-exec-stat span)"
        assert m["fontSize"] >= 18, f"icone minusculo: {m['fontSize']}px (esperado ~21)"
        assert m["glyph"] and m["glyph"] not in ('none', 'normal', '""', "''"), f"glifo FA ausente: {m['glyph']!r}"
        assert "Awesome" in (m["glyphFont"] or ""), f"::before sem fonte FA: {m['glyphFont']!r}"


class TestExecNumbersAligned:
    """Regressao (2026-06-26): (1) "Bases de dados" quebrava e o numero subia -> align-items:
    flex-start; (2) quebrava por ter espacos -> white-space:nowrap. Numeros na mesma linha +
    todas as labels numa so linha sem overflow, na largura que antes quebrava."""

    def test_numbers_aligned_and_labels_single_line(self, page, base_url):
        _load_portal(page, base_url)
        r = page.evaluate(
            """() => {
                const d = document.createElement('div');
                d.style.cssText = 'position:fixed;top:0;left:0;width:760px;padding:24px;';
                d.innerHTML = _repExecCard({}, {env:[],cat:[],sev:'ALL'}, null, false);
                document.body.appendChild(d);
                const stats = [...d.querySelectorAll('.rep-exec-stat')];
                const tops = stats.map(s => Math.round(s.querySelector('b').getBoundingClientRect().top));
                const labels = stats.map(s => { const l = s.querySelector('.rep-exec-txt span');
                    return { h: l.offsetHeight, overflow: l.scrollWidth - l.clientWidth }; });
                d.remove();
                return { tops, labels };
            }"""
        )
        assert len(set(r["tops"])) == 1, f"numeros desalinhados: tops={r['tops']}"
        heights = [l["h"] for l in r["labels"]]
        assert len(set(heights)) == 1, f"labels com alturas diferentes (alguma quebrou): {heights}"
        assert max(l["overflow"] for l in r["labels"]) <= 1, f"label transborda a coluna: {r['labels']}"


class TestExecTypography:
    """Tipografia Inter (2026-06-26): bundle local (woff2) + 'Inter' no inicio do --font-sans +
    pesos titulo 600 / numero 700 / texto 400. Antes renderizava em Segoe UI."""

    def test_inter_loaded_applied_and_weights(self, page, base_url):
        _load_portal(page, base_url)
        r = page.evaluate(
            """() => {
                const interLoaded = document.fonts.check('16px Inter');
                const d = document.createElement('div');
                d.innerHTML = _repExecCard({}, {env:[],cat:[],sev:'ALL'}, null, false);
                document.body.appendChild(d);
                const ff = getComputedStyle(d.querySelector('.rep-card-h')).fontFamily;
                const out = {
                    interLoaded, ff,
                    titleW: getComputedStyle(d.querySelector('.rep-card-h')).fontWeight,
                    numW: getComputedStyle(d.querySelector('.rep-exec-stat b')).fontWeight,
                    lblW: getComputedStyle(d.querySelector('.rep-exec-txt span')).fontWeight,
                };
                d.remove();
                return out;
            }"""
        )
        first = r["ff"].split(",")[0].strip().strip('"').strip("'")
        assert r["interLoaded"] is True, "Inter nao carregado (@font-face/woff2 em falta?)"
        assert first == "Inter", f"Inter nao e a 1a fonte da stack: {r['ff']}"
        assert r["titleW"] == "600", f"titulo deveria ser 600 (SemiBold): {r['titleW']}"
        assert r["numW"] == "700", f"numero deveria ser 700 (Bold): {r['numW']}"
        assert r["lblW"] == "400", f"texto deveria ser 400 (Regular): {r['lblW']}"
