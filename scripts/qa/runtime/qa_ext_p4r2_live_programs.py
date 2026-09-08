"""QA externo — P4 ronda 2, gate A-4.1 por PROGRAMA do LIVE (uma sessao por DPR).

Login pela UI (1 vez; para ao 401; recusa admin), abre #live-tv-modal, selecciona a 1.a instancia
disponivel (liveChangeChannel, portal ~50570) e, por cada programa (liveSetProgram, ~50589),
espera o render e mede: folhas de texto visiveis (fontSize/fontFamily), gate (>=12px; familia em
computed(--font-sans)/computed(--font-mono)), icones <i aria-hidden> (fora do gate; so' contagem),
presenca de <table>, marcadores de erro/sem-dados. Repete N vezes na mesma sessao (sem logins extra).
Nunca imprime instancias, tokens, cookies, hosts.

Uso: python qa_ext_p4r2_live_programs.py --dpr 1.25 --reps 3
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa_ext_pauta1_fonts import JS_FONT_SET, JS_TOKEN_FAMILIES, live_gate  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

UA = os.environ.get("WATCHERDB_QA_UA", "WatcherDB-QA-Externo/P4r2")
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
PROGRAMS = ["queries", "tempdb", "waits", "blocking", "io", "jobs", "memory", "connections",
            "alwayson", "tlog", "plancache", "errorlog", "schedulers", "fleet"]

JS_ICONS = """() => { const out={}; for (const e of document.querySelectorAll('#live-tv-modal i[aria-hidden="true"]')) {
  if (e.getClientRects().length===0) continue; const k=getComputedStyle(e).fontSize; out[k]=(out[k]||0)+1; } return out; }"""
JS_MARKERS = """() => { const e = document.querySelector('[id^=live-screen-]'); if (!e) return null;
  const t = (e.textContent||'').toLowerCase();
  const err = t.match(/erro:\\s*(\\d{3})/);
  return {len: t.length, tables: e.querySelectorAll('table').length, rows: e.querySelectorAll('tr').length,
          sem_dados: t.includes('sem dados disponiveis'), err_code: err ? err[1] : null,
          carregar: t.includes('a carregar'), nao_impl: t.includes('nao implementado')}; }"""


def fam_label(f: str, tok: dict) -> str:
    if f == tok.get("sans"):
        return "SANS(--font-sans)"
    if f == tok.get("mono"):
        return "MONO(--font-mono)"
    return "OUTRA:" + f[:60]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpr", type=float, default=1.25)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--wait", type=int, default=8000)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    R = {"alvo": "<host>:" + URL.rsplit(":", 1)[-1], "dpr": a.dpr, "ua": UA, "programs": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, device_scale_factor=a.dpr,
                                  color_scheme="dark", ignore_https_errors=True, user_agent=UA,
                                  extra_http_headers={"User-Agent": UA})
        page = ctx.new_page()
        page.add_init_script("try{localStorage.setItem('wdb-theme','dark')}catch(e){}")
        page.goto(URL + "/watcherdb", wait_until="networkidle", timeout=60000)
        page.fill("#loginUsername", os.environ["WATCHERDB_QA_USER"])
        page.fill("#loginPassword", os.environ["WATCHERDB_QA_PASS"])
        with page.expect_response(lambda r: "/api/auth/login" in r.url) as ri:
            page.click("#loginBtn")
        R["login_status"] = ri.value.status
        if ri.value.status != 200:
            try:
                R["login_detail"] = ri.value.json().get("detail")
            except Exception:
                R["login_detail"] = "<nao-json>"
            R["ABORT"] = "login != 200; PARADO"
            print(json.dumps(R, indent=1)); browser.close(); return 1
        role = str((ri.value.json().get("user") or {}).get("role", "")).lower()
        R["role"] = role
        if role == "admin":
            R["ABORT"] = "conta ADMIN - recusada"
            print(json.dumps(R, indent=1)); browser.close(); return 2
        page.wait_for_timeout(6000)
        R["env"] = page.evaluate("() => ({dpr: window.devicePixelRatio, theme: document.documentElement.getAttribute('data-theme'), inner: [innerWidth, innerHeight]})")
        page.click("#liveBtn")
        page.wait_for_selector("#live-tv-modal", timeout=10000)
        page.wait_for_timeout(5000)
        tab_id = page.evaluate("() => { const e=document.querySelector('[id^=live-screen-]'); return e ? e.id.replace('live-screen-','') : null; }")
        R["tab_found"] = bool(tab_id)
        # 1.a instancia do seletor de canal (valor guardado so' no browser; nunca impresso)
        n_ch = page.evaluate("(tabId) => { const s=document.getElementById('live-channel-'+tabId); return s ? [...s.options].filter(o=>o.value).length : 0; }", tab_id)
        R["channels_available"] = n_ch
        if n_ch:
            page.evaluate("(tabId) => { const s=document.getElementById('live-channel-'+tabId); const v=[...s.options].find(o=>o.value).value; s.value=v; liveChangeChannel(tabId, v); }", tab_id)
            page.wait_for_timeout(a.wait)
        tok = page.evaluate(JS_TOKEN_FAMILIES)
        R["token_families_len"] = {k: len(v) for k, v in tok.items()}
        for rep in range(a.reps):
            for prog in PROGRAMS:
                page.evaluate("([t, p]) => liveSetProgram(t, p)", [tab_id, prog])
                page.wait_for_timeout(a.wait)
                leaves = page.evaluate(JS_FONT_SET, "#live-tv-modal") or []
                g = live_gate(leaves, tok)
                # folhas do proprio ecra (exclui casca do modal) para atribuir ao programa
                screen_leaves = page.evaluate(JS_FONT_SET, "[id^=live-screen-]") or []
                gs = live_gate(screen_leaves, tok)
                entry = {
                    "rep": rep + 1,
                    "modal_gate": g["result"], "modal_leaves": g["n_leaves"], "modal_fails": g["n_fail"],
                    "screen_gate": gs["result"], "screen_leaves": gs["n_leaves"], "screen_fails": gs["n_fail"],
                    "screen_sizes": dict(Counter(l["fs"] for l in screen_leaves)),
                    "screen_families": dict(Counter(fam_label(l["ff"], tok) for l in screen_leaves)),
                    "icons_aria_hidden": page.evaluate(JS_ICONS),
                    "markers": page.evaluate(JS_MARKERS),
                    "fails_sample": [f.split(":")[0][:60] + ": " + f.split(": ", 1)[-1][:60] for f in gs["fails"][:5]],
                }
                R["programs"].setdefault(prog, []).append(entry)
        browser.close()
    txt = json.dumps(R, indent=1, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
