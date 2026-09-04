#!/usr/bin/env python3
"""Troca de idioma "demora a traduzir" -- PASSO 1: re-render imediato da aba activa + lazy nas restantes.

Diagnostico (04/09, verificado no codigo; parecer frontend-specialist + verificacao do orquestrador):
- static/js/watcherdb_i18n_v2.js:430-448 `_refreshOpenContent()` chamava `refreshTab(tab.id)`; a propriedade
  do objecto de aba e' `tabId` (portal ~6817), logo `tab.id` e' undefined e a chamada era um NO-OP. Na troca de
  idioma so' os elementos `[data-i18n]` mudavam na hora; cartoes e conteudo das abas so' mudavam quando o
  refresh periodico voltava a renderizar -> "demora para traduzir".
- Nao se pode re-renderizar a partir da cache: 11 dos 13 tipos de aba guardam em tabCache o HTML JA
  RENDERIZADO (setTabCache(..., content.innerHTML), portal 7977/8029/8081/8124/8186/9128/9866/14992/15032/
  15072/15175), logo um cache HIT devolveria a aba na lingua anterior. So' overview e always-on guardam dados.
- Fix: aba ACTIVA -> refreshTab (limpa cache + refetch, 1 aba); restantes -> clearTabCache + flag `_i18nStale`,
  e activateTab (portal ~6932) recarrega-as quando forem activadas. Custo da troca = 1 recolha, nao N.
- Bonus: `mainContentArea` (runtime :441) nao existe no portal (so' `tabsContentArea`) -> ramo morto corrigido.

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_PERF_SWITCH_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_PERF_SWITCH_PASSO1_apply.py
Impacto: static/js/watcherdb_i18n_v2.js + templates/watcherdb_portal.html (1 if) + CHANGELOG. Zero backend.
Rollback: git checkout -- static/js/watcherdb_i18n_v2.js templates/watcherdb_portal.html docs/changelog/CHANGELOG.md
"""
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JS, HTML, CHG = "static/js/watcherdb_i18n_v2.js", "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"

JS_OLD = """    function _refreshOpenContent() {
        try {
            if (typeof openTabs !== 'undefined' && openTabs && openTabs.values) {
                for (var tab of openTabs.values()) {
                    if (typeof refreshTab === 'function') {
                        refreshTab(tab.id);
                    }
                }
            }
            if (typeof renderDashboardCards === 'function') {
                var contentArea = document.getElementById('mainContentArea');
                if (contentArea && contentArea.querySelector('#kpi-dashboard-container')) {
                    renderDashboardCards();
                }
            }
        } catch (e) {
            // openTabs or refreshTab may not be initialized yet
        }
    }
"""
JS_NEW = """    function _refreshOpenContent() {
        try {
            if (typeof openTabs !== 'undefined' && openTabs && openTabs.values) {
                // 2026-09-04 (owner: "demora para traduzir"): o codigo antigo chamava
                // refreshTab(tab.id) -- a propriedade do objecto de aba e' tabId, logo era
                // um no-op e as abas so' mudavam de lingua no refresh periodico.
                // Nao se pode re-renderizar a partir da cache: 11 tipos de aba guardam
                // em tabCache o HTML ja' renderizado (na lingua antiga). Por isso:
                //   - aba ACTIVA: refreshTab (limpa cache + recarrega) -- 1 recolha, ja';
                //   - restantes: cache limpa + flag _i18nStale; activateTab recarrega-as
                //     quando forem activadas (custo diferido, nunca N recolhas de uma vez).
                var activeId = (typeof activeTabId !== 'undefined') ? activeTabId : null;
                for (var tab of openTabs.values()) {
                    var id = tab.tabId || tab.id;
                    if (!id) continue;
                    if (id === activeId) {
                        if (typeof refreshTab === 'function') refreshTab(id);
                    } else {
                        tab._i18nStale = true;
                        if (typeof clearTabCache === 'function' && tab.server) {
                            clearTabCache(tab.tabType, tab.server.server_id);
                        }
                    }
                }
            }
            if (typeof renderDashboardCards === 'function') {
                // id correcto e' tabsContentArea (mainContentArea nunca existiu no portal)
                var contentArea = document.getElementById('tabsContentArea');
                if (contentArea && contentArea.querySelector('#kpi-dashboard-container')) {
                    renderDashboardCards();
                }
            }
        } catch (e) {
            // openTabs or refreshTab may not be initialized yet
        }
    }
"""
JS_DOC_OLD = "     * Refresh open tabs and dashboard to apply new translations.\n"
JS_DOC_NEW = "     * Re-render the ACTIVE tab now and mark the others stale (reloaded on activation) to apply new translations.\n"

HTML_OLD = """            if (!hasContent) {
                loadTabContent(tabId);
            } else {
                debugLog(`[DBG] Conteúdo da aba ${tabId} já carregado, pulando recarregamento`, 'info');
            }
"""
HTML_NEW = """            // _i18nStale: marcada pelo motor i18n na troca de idioma (a cache desta aba
            // guardava HTML na lingua antiga e foi limpa) -- recarrega agora que ficou visivel.
            if (!hasContent || tab._i18nStale) {
                tab._i18nStale = false;
                loadTabContent(tabId);
            } else {
                debugLog(`[DBG] Conteúdo da aba ${tabId} já carregado, pulando recarregamento`, 'info');
            }
"""
CHANGELOG_ENTRY = """- **Troca de idioma passa a traduzir a aba visível na hora** (owner 04/09: "demora para traduzir").
  Causa: o motor chamava `refreshTab(tab.id)` e a propriedade é `tabId`, logo a chamada nunca fazia
  nada; só os elementos com `data-i18n` mudavam na hora e o resto esperava pelo refresh periódico.
  Como 11 tipos de aba guardam na cache o HTML já renderizado (na língua antiga), a aba activa é
  recarregada de imediato (uma recolha) e as outras ficam marcadas e recarregam ao serem activadas,
  nunca todas de uma vez. Corrigido também o id do contentor do dashboard no mesmo caminho. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    js, jnl = read(root / JS); html, hnl = read(root / HTML); craw, cnl = read(root / CHG)
    problems = []
    for rel, raw, nl, old, name in ((JS, js, jnl, JS_OLD, "_refreshOpenContent"), (JS, js, jnl, JS_DOC_OLD, "docstring"), (HTML, html, hnl, HTML_OLD, "activateTab if(!hasContent)")):
        c = raw.count(norm(old, nl))
        if c != 1: problems.append(f"{rel}: {name} esperado 1x, encontrado {c}x")
    anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada 1x")
    if "Troca de idioma passa a traduzir" in craw: problems.append("CHANGELOG: entrada ja existe")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print("[DRY] runtime (2 patches) + portal (1 patch) + CHANGELOG OK"); return
    (root / JS).write_bytes(js.replace(norm(JS_OLD, jnl), norm(JS_NEW, jnl)).replace(norm(JS_DOC_OLD, jnl), norm(JS_DOC_NEW, jnl)).encode("utf-8")); print(f"[OK] {JS}")
    (root / HTML).write_bytes(html.replace(norm(HTML_OLD, hnl), norm(HTML_NEW, hnl)).encode("utf-8")); print(f"[OK] {HTML}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: node --check static/js/watcherdb_i18n_v2.js ; browser Ctrl+F5: abrir 3 abas, trocar idioma -> a visivel traduz ja' (1 pedido na Network), as outras traduzem ao clicar nelas")


if __name__ == "__main__":
    main()
