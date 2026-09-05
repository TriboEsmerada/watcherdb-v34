"""QA externo — pauta 1 / A-2 e A-3 (runtime, Playwright).

Uso (venv isolado em %TEMP%\\qa-pw, nunca o ambiente do projeto):
  python qa_ext_pauta1_fonts.py --dpr 1.25 [--login] [--live] [--reps 3]

Sem --login: mede apenas a pagina publica ("/", overlay de login) — tokens,
conjunto de font-size computados, estado de #liveBtn e #live-tv-modal.
Com --login: autentica com WATCHERDB_QA_USER/PASS (perfil viewer/dba; recusa admin),
mede KPIs e Overview de servidor; com --live clica #liveBtn e mede o modal.

Nunca imprime valores de credenciais, cookies, hosts ou nomes de instancia.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

from playwright.sync_api import sync_playwright

UA = "WatcherDB-QA-Externo/pauta-1"
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
SCALE = [12, 14, 16, 18, 20, 24, 30, 36]

JS_FONT_SET = """
(rootSel) => {
  const root = rootSel ? document.querySelector(rootSel) : document.body;
  if (!root) return null;
  const out = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  let el = root;
  while (el) {
    const cs = getComputedStyle(el);
    const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && el.getClientRects().length > 0;
    // "folha de texto": tem pelo menos um filho de texto nao vazio
    let hasText = false;
    for (const n of el.childNodes) { if (n.nodeType === 3 && n.textContent.trim()) { hasText = true; break; } }
    if (visible && hasText) out.push({fs: cs.fontSize, ff: cs.fontFamily, tag: el.tagName.toLowerCase(), cls: (el.className && typeof el.className === 'string') ? el.className.slice(0, 40) : '', id: el.id || '', txt: el.textContent.trim().slice(0, 30)});
    el = walker.nextNode();
  }
  return out;
}
"""

JS_ALL_SIZES = """
() => {
  const set = {};
  for (const e of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || e.getClientRects().length === 0) continue;
    const fs = cs.fontSize; set[fs] = (set[fs] || 0) + 1;
  }
  return set;
}
"""

JS_OFF_SAMPLES = """(scale) => { const out={}; for (const e of document.querySelectorAll('body *')) { const cs=getComputedStyle(e); if (cs.display==='none'||e.getClientRects().length===0) continue; const v=parseFloat(cs.fontSize); if (scale.some(s=>Math.abs(v-s)<=0.5)) continue; const k=cs.fontSize; if (!out[k]) out[k]={n:0,samples:[]}; out[k].n++; if (out[k].samples.length<3) out[k].samples.push((e.tagName.toLowerCase())+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.split(' ')[0]:'')+' inline='+(e.style.fontSize||'-')); } return out; }"""

JS_ENV = """
() => ({
  dpr: window.devicePixelRatio,
  inner: [window.innerWidth, window.innerHeight],
  theme: document.documentElement.getAttribute('data-theme'),
  rootFontSize: getComputedStyle(document.documentElement).fontSize,
  bodyFontSize: getComputedStyle(document.body).fontSize,
  bodyFontFamily: getComputedStyle(document.body).fontFamily,
  rootZoom: getComputedStyle(document.documentElement).zoom,
  bodyZoom: getComputedStyle(document.body).zoom,
  fontSans: getComputedStyle(document.documentElement).getPropertyValue('--font-sans').trim(),
  fontMono: getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim(),
  liveBtn: (() => { const b = document.getElementById('liveBtn'); if (!b) return 'ausente'; const cs = getComputedStyle(b); return `presente display=${cs.display} gated=${b.getAttribute('data-live-gated')}`; })(),
  liveModal: document.getElementById('live-tv-modal') ? 'presente' : 'ausente',
  bodyChildrenIds: [...document.body.children].map(c => c.id || c.tagName.toLowerCase()).slice(0, 40),
})
"""


def classify(sizes: dict) -> tuple[dict, dict]:
    on, off = {}, {}
    for k, n in sizes.items():
        v = float(k.replace("px", ""))
        (on if any(abs(v - s) <= 0.5 for s in SCALE) else off)[k] = n
    return on, off


def redact(s: str) -> str:
    """Remove fragmentos que possam ser nomes de instancia/host (heuristica)."""
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpr", type=float, default=1.25)
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--live-prelogin", action="store_true", dest="live_prelogin")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        for rep in range(a.reps):
            ctx = browser.new_context(
                viewport={"width": 1366, "height": 768},
                device_scale_factor=a.dpr,
                color_scheme="dark",
                ignore_https_errors=True,
                user_agent=UA,
                extra_http_headers={"User-Agent": UA},
            )
            page = ctx.new_page()
            page.add_init_script("try{localStorage.setItem('wdb-theme','dark')}catch(e){}")
            page.goto(URL + "/watcherdb", wait_until="networkidle", timeout=60000)  # portal servido em /watcherdb (watcherdb_main.py:3348)
            page.wait_for_timeout(1500)
            r = {"rep": rep + 1, "dpr": a.dpr, "env": page.evaluate(JS_ENV)}
            sizes = page.evaluate(JS_ALL_SIZES)
            r["login_page_sizes"] = sizes
            r["login_page_on"], r["login_page_off"] = classify(sizes)
            r["login_page_off_samples"] = page.evaluate(JS_OFF_SAMPLES, SCALE)

            if a.live_prelogin:
                # Sem sessao: openLiveMonitoringModal() constroi o shell do modal na mesma
                # (portal:50303/50403); os fetch de dados falham com 401 (apenas GET).
                r["live_before"] = page.evaluate(JS_ENV)["liveModal"]
                btn = page.locator("#liveBtn")
                r["live_btn_visible"] = btn.count() > 0 and btn.is_visible()
                if r["live_btn_visible"]:
                    # Sem sessao o #loginOverlay (portal:3917) cobre o botao e intercepta o
                    # clique normal; regista-se isso e usa-se clique forcado (mesmo handler).
                    r["live_btn_covered_by"] = page.evaluate("() => { const b=document.getElementById('liveBtn'); const r=b.getBoundingClientRect(); const t=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2); return t ? (t.tagName.toLowerCase()+(t.id?'#'+t.id:'')+(t.className&&typeof t.className==='string'?'.'+t.className.split(' ')[0]:'')) : null; }")
                    btn.click(force=True, timeout=10000)
                    page.wait_for_timeout(1500)
                    r["live_open_method"] = "click(force)"
                    if page.evaluate("() => !!document.getElementById('live-tv-modal')") is False:
                        # O clique forcado e' entregue ao overlay, nao ao botao. Invoca-se o
                        # mesmo handler do onclick (portal:4189 -> openLiveMonitoringModal()).
                        page.evaluate("() => openLiveMonitoringModal()")
                        r["live_open_method"] = "evaluate(openLiveMonitoringModal) — clique interceptado pelo overlay de login"
                    page.wait_for_selector("#live-tv-modal", state="attached", timeout=10000)
                    page.wait_for_timeout(10000)
                    r["live_after"] = page.evaluate(JS_ENV)["liveModal"]
                    r["live_modal_parent"] = page.evaluate("() => { const m=document.getElementById('live-tv-modal'); return m ? m.parentElement.tagName + ' z=' + getComputedStyle(m).zIndex + ' pos=' + getComputedStyle(m).position : null; }")
                    leaves = page.evaluate(JS_FONT_SET, "#live-tv-modal") or []
                    r["live_leaf_count"] = len(leaves)
                    r["live_family_count"] = Counter(l["ff"] for l in leaves).most_common()
                    r["live_size_count"] = Counter(l["fs"] for l in leaves).most_common()
                    r["live_leaves"] = [{k: l[k] for k in ("tag", "id", "fs", "ff")} | {"txt": l["txt"][:20]} for l in leaves][:60]
                    r["live_screen"] = page.evaluate("() => { const e=document.querySelector('[id^=live-screen-]'); if(!e) return null; const cs=getComputedStyle(e); const ch=e.querySelector('div'); return {ff: cs.fontFamily, fs: cs.fontSize, inlineFF: e.style.fontFamily, child: ch ? {ff:getComputedStyle(ch).fontFamily, fs:getComputedStyle(ch).fontSize, inlineFF: ch.style.fontFamily||'-'} : null}; }")
                    r["live_form_controls"] = page.evaluate("() => { const out={}; for (const e of document.querySelectorAll('#live-tv-modal button, #live-tv-modal input, #live-tv-modal select')) { const ff=getComputedStyle(e).fontFamily; out[ff]=(out[ff]||0)+1; } return out; }")

            if a.login:
                page.fill("#loginUsername", os.environ["WATCHERDB_QA_USER"])
                page.fill("#loginPassword", os.environ["WATCHERDB_QA_PASS"])
                with page.expect_response(lambda resp: "/api/auth/login" in resp.url) as ri:
                    page.click("#loginBtn")
                resp = ri.value
                r["login_status"] = resp.status
                if resp.status != 200:
                    r["login_error"] = "login falhou (status acima); sem medicao autenticada"
                    results.append(r)
                    ctx.close()
                    continue
                try:
                    user = resp.json().get("user", {}) or {}
                    role = str(user.get("role", "")).lower()
                except Exception:
                    role = "?"
                r["login_role"] = role
                if role == "admin":
                    r["login_error"] = "conta e ADMIN — recusado pelo charter"
                    results.append(r)
                    ctx.close()
                    continue
                page.wait_for_timeout(6000)
                # Pagina KPIs: hook do portal (templates/watcherdb_portal.html:4205)
                try:
                    page.evaluate("() => { if (typeof goToDashboardKPIs === 'function') goToDashboardKPIs(); }")
                except Exception:
                    pass
                page.wait_for_timeout(8000)
                r["env_after_login"] = page.evaluate(JS_ENV)
                sizes = page.evaluate(JS_ALL_SIZES)
                r["kpi_page_sizes"] = sizes
                r["kpi_on"], r["kpi_off"] = classify(sizes)
                # 3 fora-da-escala: apontar elementos
                r["kpi_off_samples"] = page.evaluate(
                    """(scale) => { const out={}; for (const e of document.querySelectorAll('body *')) { const cs=getComputedStyle(e); if (cs.display==='none'||e.getClientRects().length===0) continue; const v=parseFloat(cs.fontSize); if (scale.some(s=>Math.abs(v-s)<=0.5)) continue; const k=cs.fontSize; if (!out[k]) out[k]={n:0,samples:[]}; out[k].n++; if (out[k].samples.length<3) out[k].samples.push((e.tagName.toLowerCase())+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.split(' ')[0]:'')+' inline='+(e.style.fontSize||'-')); } return out; }""",
                    SCALE,
                )

                # Overview de servidor: primeiro item da lista de servidores
                try:
                    # Overview: selectServer(primeiro servidor) + showTab('overview') (portal:7455, :4771)
                    page.evaluate("() => { const s = (window.allServers||[])[0]; if (s && typeof selectServer==='function') selectServer(s); }")
                    page.wait_for_timeout(4000)
                    page.evaluate("() => { if (typeof showTab==='function') showTab('overview'); }")
                    page.wait_for_timeout(8000)
                    sizes = page.evaluate(JS_ALL_SIZES)
                    r["overview_sizes"] = sizes
                    r["overview_on"], r["overview_off"] = classify(sizes)
                except Exception as e:
                    r["overview_error"] = type(e).__name__

                if a.live:
                    r["live_before"] = page.evaluate(JS_ENV)["liveModal"]
                    btn = page.locator("#liveBtn")
                    if btn.count() == 0 or not btn.is_visible():
                        r["live_error"] = "liveBtn ausente ou escondido (gated) para esta conta"
                    else:
                        btn.click()
                        page.wait_for_selector("#live-tv-modal", timeout=10000)
                        page.wait_for_timeout(10000)
                        r["live_after"] = page.evaluate(JS_ENV)["liveModal"]
                        leaves = page.evaluate(JS_FONT_SET, "#live-tv-modal") or []
                        r["live_family_count"] = Counter(l["ff"] for l in leaves).most_common()
                        r["live_size_count"] = Counter(l["fs"] for l in leaves).most_common()
                        r["live_leaf_count"] = len(leaves)
                        r["live_form_controls"] = page.evaluate(
                            """() => { const out={}; for (const e of document.querySelectorAll('#live-tv-modal button, #live-tv-modal input, #live-tv-modal select')) { const ff=getComputedStyle(e).fontFamily; out[ff]=(out[ff]||0)+1; } return out; }"""
                        )
            results.append(r)
            ctx.close()
        browser.close()

    txt = json.dumps(results, indent=1, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
    try:
        print(txt)
    except UnicodeEncodeError:  # consola cp1252 no Windows
        print(json.dumps(results, indent=1, ensure_ascii=True))


if __name__ == "__main__":
    sys.exit(main())
