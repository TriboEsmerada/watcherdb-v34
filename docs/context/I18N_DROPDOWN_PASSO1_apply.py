#!/usr/bin/env python3
"""Selector de idioma em dropdown (drill-down) no header -- PASSO 1: aplicar patches.

Pedido owner 2026-09-03: "na hora de mudar o idioma eu prefiro que faca um drill-down".
Parecer watcherdb-frontend-specialist (03/09): reutilizar createLanguageSelector() do runtime
(CSS ja' linkado, 4 opcoes desde 5612d68) no lugar do botao de ciclo; corrigir antes a lacuna
WCAG 2.1.1 (zero navegacao por teclado); remover kpiCycleLang (codigo morto) e cycleLangGlobal
(substituido); manter o ciclo do Relatorio KPI por agora (fast-follow).

Identidade: owner (filesystem). Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_DROPDOWN_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_DROPDOWN_PASSO1_apply.py
Impacto: 4 ficheiros (runtime i18n, CSS do selector, portal, CHANGELOG). Zero backend, zero BD.
Rollback: git checkout -- static/js/watcherdb_i18n_v2.js static/css/i18n_selector.css \
            templates/watcherdb_portal.html docs/changelog/CHANGELOG.md
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
JS = "static/js/watcherdb_i18n_v2.js"
CSS = "static/css/i18n_selector.css"
HTML = "templates/watcherdb_portal.html"
CHG = "docs/changelog/CHANGELOG.md"

# ---------------------------------------------------------------- runtime JS
BTN_OLD = """            '<button class="i18n-lang-btn" id="langToggleBtn" aria-haspopup="listbox" aria-expanded="false">',
"""
BTN_NEW = """            '<button type="button" class="i18n-lang-btn" id="langToggleBtn" aria-haspopup="listbox" aria-expanded="false" aria-controls="langDropdown" title="Idioma / Language" aria-label="Idioma / Language">',
"""

EVENTS_OLD = """        // Event: toggle dropdown
        var btn = container.querySelector('#langToggleBtn');
        var dropdown = container.querySelector('#langDropdown');

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var isOpen = dropdown.classList.toggle('open');
            btn.setAttribute('aria-expanded', isOpen);
        });

        // Event: select language
        var options = container.querySelectorAll('.i18n-lang-option');
        for (var i = 0; i < options.length; i++) {
            options[i].addEventListener('click', function(e) {
                var lang = this.getAttribute('data-lang');
                setLanguage(lang);
                dropdown.classList.remove('open');
                btn.setAttribute('aria-expanded', 'false');
                // Update active state
                container.querySelectorAll('.i18n-lang-option').forEach(function(opt) {
                    opt.classList.toggle('active', opt.getAttribute('data-lang') === lang);
                });
            });
        }

        // Close on outside click
        document.addEventListener('click', function() {
            dropdown.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
        });

        // Mark current language as active
        var currentOpt = container.querySelector('[data-lang="' + _currentLang + '"]');
        if (currentOpt) currentOpt.classList.add('active');

        _updateSelector();
    }
"""

EVENTS_NEW = """        // Event: toggle dropdown (rato + teclado; WCAG 2.1.1 -- parecer frontend-specialist 2026-09-03)
        var btn = container.querySelector('#langToggleBtn');
        var dropdown = container.querySelector('#langDropdown');
        var options = Array.prototype.slice.call(container.querySelectorAll('.i18n-lang-option'));

        function markActive(lang) {
            options.forEach(function(opt) {
                var on = opt.getAttribute('data-lang') === lang;
                opt.classList.toggle('active', on);
                opt.setAttribute('aria-selected', on ? 'true' : 'false');
            });
        }
        function activeIndex() {
            for (var i = 0; i < options.length; i++) {
                if (options[i].getAttribute('data-lang') === _currentLang) return i;
            }
            return 0;
        }
        function openDropdown(focusOption) {
            dropdown.classList.add('open');
            btn.setAttribute('aria-expanded', 'true');
            if (focusOption) options[activeIndex()].focus();
        }
        function closeDropdown(returnFocus) {
            dropdown.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
            if (returnFocus) btn.focus();
        }
        function choose(lang) {
            setLanguage(lang);
            markActive(lang);
            closeDropdown(true);
        }

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (dropdown.classList.contains('open')) closeDropdown(false);
            else openDropdown(false);
        });
        btn.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                openDropdown(true);
            } else if (e.key === 'Escape' && dropdown.classList.contains('open')) {
                e.preventDefault();
                closeDropdown(true);
            }
        });

        options.forEach(function(opt, idx) {
            opt.addEventListener('click', function(e) {
                e.stopPropagation();
                choose(this.getAttribute('data-lang'));
            });
            opt.addEventListener('keydown', function(e) {
                var next = null;
                if (e.key === 'ArrowDown') next = (idx + 1) % options.length;
                else if (e.key === 'ArrowUp') next = (idx - 1 + options.length) % options.length;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = options.length - 1;
                else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(this.getAttribute('data-lang')); return; }
                else if (e.key === 'Escape') { e.preventDefault(); closeDropdown(true); return; }
                else if (e.key === 'Tab') { closeDropdown(false); return; }
                if (next !== null) { e.preventDefault(); options[next].focus(); }
            });
        });

        // Close on outside click
        document.addEventListener('click', function() {
            closeDropdown(false);
        });

        // Mark current language as active
        markActive(_currentLang);
        _changeListeners.push(function(lang) { markActive(lang); });

        _updateSelector();
    }
"""

CSS_APPEND = """
/* Teclado: foco visivel nas opcoes (WCAG 2.4.7) -- dropdown no header desde 2026-09-03 */
.i18n-lang-option:focus-visible {
    outline: 2px solid var(--color-info, #2563eb);
    outline-offset: -2px;
}
.i18n-lang-option[aria-selected="true"] .i18n-lang-check {
    opacity: 1;
}
"""

# ---------------------------------------------------------------- portal
HEADER_OLD = """                <div id="headerLangSelector"><button onclick="cycleLangGlobal()" id="globalLangBtn" title="Idioma / Language (PT / PT-BR / EN / ES)" aria-label="Mudar idioma" style="display:flex;align-items:center;gap:6px;background:rgba(139,92,246,0.15);border:1px solid rgba(139,92,246,0.4);color:#a78bfa;border-radius:8px;padding:8px 12px;font-size:13px;font-weight:600;cursor:pointer;"><i class="fas fa-globe"></i> <span id="globalLangCode">PT</span></button></div>
"""
HEADER_NEW = """                <div id="headerLangSelector"></div><!-- dropdown montado por WatcherI18N.createLanguageSelector (pedido owner 03/09: drill-down em vez de ciclo) -->
"""

BOOT_OLD = """        // BR PT substituido pelo nosso seletor 7B PT/EN/ES (#globalLangBtn); sem createLanguageSelector.
        try { const _gl = document.getElementById('globalLangCode'); if (_gl && WatcherI18N.getLanguage) _gl.textContent = (WatcherI18N.getLanguage() || 'pt').toUpperCase(); } catch (e) {}
        try { if (WatcherI18N.onLanguageChange) WatcherI18N.onLanguageChange(function (l) { const b = document.getElementById('globalLangCode'); if (b) b.textContent = String(l || '').toUpperCase(); }); } catch (e) {}
"""
BOOT_NEW = """        // Selector de idioma em dropdown (4 opcoes, teclado) no header -- decisao owner 2026-09-03.
        try { WatcherI18N.createLanguageSelector('#headerLangSelector'); } catch (e) { console.error('[I18N] Language selector failed:', e); }
"""

CYCLE_OLD = """        // ---- Idioma no cabeçalho dos KPIs (motor i18n nativo: setLanguage/getLanguage) ----
        function kpiCycleLang() {
            const seq = (typeof WatcherI18N !== 'undefined' && WatcherI18N.SUPPORTED_LANGS) ? WatcherI18N.SUPPORTED_LANGS : ['pt', 'pt-BR', 'en', 'es'];
            const cur = (typeof getLanguage === 'function' ? getLanguage() : 'pt');
            const nxt = seq[(seq.indexOf(cur) + 1) % seq.length];
            if (typeof setLanguage === 'function') setLanguage(nxt);
            _kpiSyncLangBtn(nxt);
        }
        // Seletor de idioma GLOBAL (no lugar do antigo "BR PT", no topo) — traduz a app toda
        function cycleLangGlobal() {
            const seq = (typeof WatcherI18N !== 'undefined' && WatcherI18N.SUPPORTED_LANGS) ? WatcherI18N.SUPPORTED_LANGS : ['pt', 'pt-BR', 'en', 'es'];
            const W = (typeof WatcherI18N !== 'undefined') ? WatcherI18N : null;
            const cur = (typeof getLanguage === 'function') ? getLanguage() : (W && W.getLanguage ? W.getLanguage() : 'pt');
            const nxt = seq[(seq.indexOf(cur) + 1) % seq.length];
            if (typeof setLanguage === 'function') setLanguage(nxt);
            else if (W && W.setLanguage) W.setLanguage(nxt);
            const b = document.getElementById('globalLangCode'); if (b) b.textContent = nxt.toUpperCase();
        }
"""
CYCLE_NEW = """        // ---- Idioma: o header usa WatcherI18N.createLanguageSelector (dropdown) desde 03/09;
        //      kpiCycleLang (nunca ligado) e cycleLangGlobal (botao de ciclo) removidos. ----
"""

CHANGELOG_ENTRY = """- **Selector de idioma em drill-down no header** (pedido owner 03/09; parecer
  frontend-specialist). O botão que rodava PT → PT-BR → EN → ES em ciclo dá lugar ao
  dropdown do próprio motor (`WatcherI18N.createLanguageSelector`, CSS já ligado), com
  as 4 opções visíveis, bandeira e nome na própria língua. O componente ganhou o que
  lhe faltava para WCAG 2.1.1: setas/Home/End para navegar, Enter/Espaço para escolher,
  Escape fecha e devolve o foco, `aria-selected` e foco visível. Removidos `kpiCycleLang`
  (nunca esteve ligado a nenhum botão) e `cycleLangGlobal`; o ciclo do Relatório KPI
  mantém-se por agora. [tier: Std]
"""


def read(p: Path):
    raw = p.read_bytes().decode("utf-8")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    print(f"root: {root}  dry-run={a.dry_run}")

    plist = [
        (JS, BTN_OLD, BTN_NEW, 1),
        (JS, 'role="option" lang=', 'role="option" tabindex="-1" lang=', 4),
        (JS, EVENTS_OLD, EVENTS_NEW, 1),
        (HTML, HEADER_OLD, HEADER_NEW, 1),
        (HTML, BOOT_OLD, BOOT_NEW, 1),
        (HTML, CYCLE_OLD, CYCLE_NEW, 1),
        (CHG, "## [Unreleased]\n\n### Changed\n\n", "## [Unreleased]\n\n### Changed\n\n" + CHANGELOG_ENTRY, 1),
    ]
    texts, problems = {}, []
    for rel, old, new, n in plist:
        p = root / rel
        if not p.exists():
            problems.append(f"{rel}: nao existe"); continue
        texts.setdefault(rel, read(p))
        raw, nl = texts[rel]
        c = raw.count(norm(old, nl))
        if c != n:
            problems.append(f"{rel}: esperado {n}x, encontrado {c}x -> {old[:80]!r}")
    css_raw, css_nl = read(root / CSS)
    if "i18n-lang-option:focus-visible" in css_raw:
        problems.append(f"{CSS}: ja tem o bloco de foco (ja aplicado?)")
    if "cycleLangGlobal" in texts.get(HTML, ("",))[0].replace(norm(CYCLE_OLD, texts[HTML][1]), "").replace(norm(HEADER_OLD, texts[HTML][1]), ""):
        problems.append(f"{HTML}: cycleLangGlobal referenciado noutro sitio alem dos 2 patches")
    if problems:
        print("[ABORT] nada foi escrito:")
        for x in problems: print("   -", x)
        sys.exit(2)
    for rel, old, new, n in plist:
        raw, nl = texts[rel]
        texts[rel] = (raw.replace(norm(old, nl), norm(new, nl)), nl)
    if a.dry_run:
        print(f"[DRY] {len(plist)} patches verificados + CSS append OK")
        return
    for rel, (raw, nl) in texts.items():
        (root / rel).write_bytes(raw.encode("utf-8")); print(f"[OK] {rel}")
    (root / CSS).write_bytes((css_raw.rstrip("\r\n") + css_nl + norm(CSS_APPEND, css_nl)).encode("utf-8"))
    print(f"[OK] {CSS}")
    print("\nSeguir com: node --check static/js/watcherdb_i18n_v2.js ; validar no browser (checklist no PLANO) ; PASSO2 commit")


if __name__ == "__main__":
    main()
