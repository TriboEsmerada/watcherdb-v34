"""QA externo — P4 ronda 2: diagnostico do carregamento do LIVE (porque nao ha tabela?).

Login pela UI (1 unica vez; para ao 401), clica #liveBtn, regista as respostas de rede do LIVE
(so' status + caminho com query removida e segmentos variaveis mascarados), espera ate' 40 s por
uma <table> em [id^=live-screen-], e classifica o texto do ecra por marcadores (sem o imprimir).
Nao imprime tokens/cookies/hosts/instancias.
"""
from __future__ import annotations
import json
import os
import re
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

UA = os.environ.get("WATCHERDB_QA_UA", "WatcherDB-QA-Externo/P4r2")
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")


def mask_path(u: str) -> str:
    p = urlsplit(u).path
    segs = p.split("/")
    out = []
    for i, s in enumerate(segs):
        out.append(s if i <= 3 or s in ("live", "api", "queries", "tempdb", "waits", "blocking", "fleet", "io", "jobs",
                                         "memory", "connections", "alwayson", "tlog", "plancache", "errorlog",
                                         "schedulers", "channels", "programs") else "<seg>")
    return "/".join(out)


def main() -> int:
    R = {"alvo": "<host>:" + URL.rsplit(":", 1)[-1]}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, device_scale_factor=1.25,
                                  color_scheme="dark", ignore_https_errors=True, user_agent=UA,
                                  extra_http_headers={"User-Agent": UA})
        page = ctx.new_page()
        page.add_init_script("try{localStorage.setItem('wdb-theme','dark')}catch(e){}")
        net = []
        page.on("response", lambda r: net.append((r.request.method, mask_path(r.url), r.status))
                if "/api/" in r.url else None)
        console = []
        page.on("console", lambda m: console.append(m.type + ": " + re.sub(r"[A-Za-z0-9_.-]*\\\\[A-Za-z0-9_.-]*", "<inst>", m.text)[:120])
                if m.type in ("error", "warning") else None)
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
            print(json.dumps(R, indent=1)); browser.close(); return 1
        page.wait_for_timeout(6000)
        net.clear()
        btn = page.locator("#liveBtn")
        R["liveBtn_visible"] = btn.is_visible()
        btn.click()
        page.wait_for_selector("#live-tv-modal", timeout=10000)
        found = None
        for t in range(8):
            page.wait_for_timeout(5000)
            n_tables = page.evaluate("() => document.querySelectorAll('[id^=live-screen-] table').length")
            if n_tables and found is None:
                found = (t + 1) * 5
        R["seconds_until_table"] = found
        R["n_tables_final"] = page.evaluate("() => document.querySelectorAll('[id^=live-screen-] table').length")
        R["screen_markers"] = page.evaluate("""() => {
            const e = document.querySelector('[id^=live-screen-]'); if (!e) return null;
            const t = (e.textContent || '').toLowerCase();
            return {len: t.length,
                    has_sem_dados: t.includes('sem dados') || t.includes('no data'),
                    has_erro: t.includes('erro') || t.includes('error'),
                    has_401: t.includes('401') || t.includes('nao autenticado') || t.includes('unauthorized'),
                    has_carregar: t.includes('carregar') || t.includes('loading'),
                    has_forbidden: t.includes('403') || t.includes('forbidden') || t.includes('pro'),
                    child_tags: [...e.querySelectorAll('*')].map(x => x.tagName.toLowerCase()).reduce((a, k) => (a[k] = (a[k] || 0) + 1, a), {})};
        }""")
        R["live_program_state"] = page.evaluate("() => { try { return {sortKeys: Object.keys(_liveSortState || {})}; } catch (e) { return String(e).slice(0, 60); } }")
        R["live_channel_labels"] = page.evaluate("() => [...document.querySelectorAll('#live-tv-modal [data-program], #live-tv-modal [data-channel]')].map(x => x.getAttribute('data-program') || x.getAttribute('data-channel')).slice(0, 30)")
        R["net_after_click"] = net[:60]
        R["console"] = console[:20]
        browser.close()
    print(json.dumps(R, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
