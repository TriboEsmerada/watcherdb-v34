"""TESTSUKITA V1 - explorador de interaccoes por aba (o que o TestSprite faz: clicar em tudo).

Por perfil e por aba: abre a aba do servidor de teste e, DENTRO do contentor da aba,
  - clica (JS click, imune ao refresh de 30 s) nos primeiros N controlos visiveis que nao sejam
    destrutivos nem de escrita (salvar/apagar/executar/restart/export/logout/refresh...),
  - escreve nos 2 primeiros campos de texto e muda o 1.o select,
  - fecha qualquer modal que tenha aberto (Escape) e regista se abriu.
Invariantes: 0 pageerror, 0 respostas 5xx, 0 erros de consola fora do ruido. O que foi tocado fica no JSON
(coverage de interaccao por aba), para o ratchet e o painel.

  WATCHERDB_QA_INTER_CLICKS (default 6), WATCHERDB_QA_INTER_INPUTS (default 2)
  py -m pytest tests/e2e/test_interactions_e2e.py -m e2e --no-cov -p no:cacheprovider -q
"""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_spec = importlib.util.spec_from_file_location("smoke_helpers", Path(__file__).with_name("test_smoke_modules_e2e.py"))
_smk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smk)

TABS = _smk.TABS
PERFIS = _smk.PERFIS
MAX_CLICKS = int(os.getenv("WATCHERDB_QA_INTER_CLICKS", "6"))
MAX_INPUTS = int(os.getenv("WATCHERDB_QA_INTER_INPUTS", "2"))
TAB_TIMEOUT_MS = int(os.getenv("WATCHERDB_QA_TAB_TIMEOUT_MS", "60000"))

# Nunca clicar: escrita, execucao, navegacao para fora, refresh (ruido) e o proprio fecho de aba.
PERIGOSO = ("salvar|guardar|gravar|apagar|remover|eliminar|delete|reset|restart|reinic|executar|run now|run |"
            "mute|silenc|export|download|descarreg|imprimir|print|logout|sair|kill|stop|start|refresh|"
            "atualizar|actualizar|fechar|close|abort|cancel|shrink|alter |drop |truncate|enviar|submit|"
            "confirm|aplicar|apply|criar|create|novo|new |login|password|senha")

JS_LISTA = r"""
(args) => {
  const [tid, maxClicks, maxInputs, perigoso] = args;
  const root = document.getElementById('tab-content-' + tid);
  if (!root) return null;
  const rx = new RegExp(perigoso, 'i');
  const visivel = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const texto = (el) => ((el.innerText || '') + ' ' + (el.title || '') + ' ' + (el.getAttribute('onclick') || '') + ' ' + (el.className || '')).trim();
  const clicaveis = [];
  const vistos = new Set();
  for (const el of root.querySelectorAll('button, [onclick], [role="button"], a[href^="#"], .clickable, th[onclick], .kpi-card')) {
    if (clicaveis.length >= maxClicks) break;
    if (!visivel(el)) continue;
    if (el.closest('.tab-refresh, .kpi-card-refresh, form')) continue;
    const t = texto(el);
    if (rx.test(t)) continue;
    const chave = (el.tagName + '|' + (el.innerText || '').trim().slice(0, 40) + '|' + (el.getAttribute('onclick') || '').slice(0, 60));
    if (vistos.has(chave)) continue;
    vistos.add(chave);
    el.setAttribute('data-ts-click', String(clicaveis.length));
    clicaveis.push({ i: clicaveis.length, tag: el.tagName, texto: (el.innerText || el.title || '').trim().slice(0, 60) });
  }
  const inputs = [];
  for (const el of root.querySelectorAll('input[type="text"], input[type="search"], input:not([type]), textarea')) {
    if (inputs.length >= maxInputs) break;
    if (!visivel(el) || el.readOnly || el.disabled) continue;
    if (rx.test(texto(el) + ' ' + (el.placeholder || '') + ' ' + (el.name || '') + ' ' + (el.id || ''))) continue;
    el.setAttribute('data-ts-input', String(inputs.length));
    inputs.push({ i: inputs.length, id: el.id || el.name || el.placeholder || el.tagName });
  }
  let select = null;
  for (const el of root.querySelectorAll('select')) {
    if (!visivel(el) || el.disabled || el.options.length < 2) continue;
    el.setAttribute('data-ts-select', '0');
    select = { id: el.id || el.name || 'select', opcoes: el.options.length };
    break;
  }
  const total = root.querySelectorAll('button, [onclick], [role="button"], input, select').length;
  return { clicaveis, inputs, select, total_controlos: total };
}
"""

JS_MODAL_ABERTA = r"""
() => {
  const cands = document.querySelectorAll('.instances-modal.show, [role="dialog"], .modal.show, [id$="Modal"], [id$="-modal"]');
  for (const m of cands) { const cs = getComputedStyle(m); if (cs.display !== 'none' && cs.visibility !== 'hidden' && m.getBoundingClientRect().height > 40) return m.id || m.className || 'modal'; }
  return null;
}
"""


def _fecha_modais(page) -> int:
    fechadas = 0
    for _ in range(3):
        aberta = page.evaluate(JS_MODAL_ABERTA)
        if not aberta:
            break
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        fechadas += 1
    return fechadas


@pytest.mark.parametrize("perfil", [_smk._perfil_param(p) for p in PERFIS])
@pytest.mark.parametrize("tab", TABS)
class TestInteraccoes:
    def test_aba_aguenta_cliques_e_escrita(self, page, base_url, perfil, tab):
        col = _smk.Colector(page, base_url)
        user = _smk._autentica(page, base_url, perfil)
        servidor = _smk._escolhe_servidor(page)
        if not servidor:
            pytest.skip("sem servidor de test/quality no inventario")
        page.evaluate("(sid) => { const s = allServers.find(x => x.server_id === sid); selectServer(s); }", servidor["server_id"])
        page.wait_for_timeout(500)
        tab_id = page.evaluate("(tab) => { showTab(tab); return activeTabId; }", tab)
        try:
            page.wait_for_function(
                """(tid) => { const el = document.getElementById('tab-content-' + tid);
                              return !!el && !el.querySelector('.fa-spin') && (el.innerText || '').trim().length > 0; }""",
                arg=tab_id, timeout=TAB_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass  # aba lenta: explora-se o que houver

        plano = page.evaluate(JS_LISTA, [tab_id, MAX_CLICKS, MAX_INPUTS, PERIGOSO])
        assert plano is not None, f"[{perfil}/{tab}] contentor da aba nao existe"
        t0 = time.time()
        feitos, modais = [], 0
        for c in plano["clicaveis"]:
            ok = page.evaluate("(i) => { const el = document.querySelector('[data-ts-click=\"' + i + '\"]'); if (!el) return false; el.scrollIntoView({block:'center'}); el.click(); return true; }", c["i"])
            page.wait_for_timeout(700)
            abriu = page.evaluate(JS_MODAL_ABERTA)
            if abriu:
                modais += _fecha_modais(page)
            feitos.append({"tipo": "click", "alvo": f"{c['tag']}:{c['texto']}", "clicou": ok, "modal": abriu})
        for i in plano["inputs"]:
            sel = f'[data-ts-input="{i["i"]}"]'
            try:
                page.fill(sel, "a")
                page.wait_for_timeout(400)
                page.fill(sel, "")
                feitos.append({"tipo": "input", "alvo": i["id"], "clicou": True, "modal": None})
            except Exception as exc:  # noqa: BLE001
                feitos.append({"tipo": "input", "alvo": i["id"], "clicou": False, "modal": None, "erro": type(exc).__name__})
        if plano["select"]:
            page.evaluate("() => { const s = document.querySelector('[data-ts-select=\"0\"]'); if (s) { s.selectedIndex = 1; s.dispatchEvent(new Event('change', {bubbles:true})); } }")
            page.wait_for_timeout(500)
            feitos.append({"tipo": "select", "alvo": plano["select"]["id"], "clicou": True, "modal": None})
        modais += _fecha_modais(page)
        caso = {
            "caso": f"inter_{tab}", "perfil": perfil, "user": user, "server": servidor, "tab_id": tab_id,
            "total_controlos": plano["total_controlos"], "tocados": feitos, "modais_fechadas": modais,
            "load_ms": int((time.time() - t0) * 1000), "dom_nodes": _smk._dom_nodes(page),
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(), "abortados": col.abortados(),
            "http5xx": col.http5xx, "warn": [],
        }
        _smk._grava(caso)
        assert not col.pageerrors, f"[{perfil}/{tab}] excepcao JS ao interagir:\n  - " + "\n  - ".join(col.pageerrors[:5])
        assert not col.http5xx, f"[{perfil}/{tab}] respostas 5xx ao interagir:\n  - " + "\n  - ".join(col.http5xx[:5])
        assert not caso["console_errors"], f"[{perfil}/{tab}] erros de consola ao interagir:\n  - " + "\n  - ".join(caso["console_errors"][:10])
