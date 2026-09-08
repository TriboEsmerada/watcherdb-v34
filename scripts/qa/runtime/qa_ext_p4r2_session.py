"""QA externo — pauta P4 RONDA 2 (runtime). Sessao/token apos lotes c8874a3, b920b60, 7ce5481.

Cobre:
  A-4.4  login com utilizador INVENTADO (nunca a conta QA com password errada): status + detail, N reps.
  A-4.3  login pela UI -> handleLogout() pela UI: observa POST /api/auth/logout (status/corpo),
         cookies (so' nomes/atributos), localStorage (so' nomes); depois GET /api/auth/me com o
         token antigo (guardado em memoria, NUNCA impresso) => espera-se 401 "Token revogado".
  A-4.7  baseline: GET /api/auth/me com o token fresco do login => 200. Token antigo do owner
         so' se WATCHERDB_QA_OLD_TOKEN existir (senao NAO VERIFICAVEL em runtime).

Regras: PARA ao primeiro 401 de login da conta QA (sem repetir). Recusa conta ADMIN.
Nao imprime tokens, cookies, passwords, emails, hosts.
Uso: python qa_ext_p4r2_session.py --fake-user qa_nao_existe_p4r2_<rnd> --reps 3 --pace 16
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

UA = os.environ.get("WATCHERDB_QA_UA", "WatcherDB-QA-Externo/P4r2")
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
USER = os.environ["WATCHERDB_QA_USER"]
PASS = os.environ["WATCHERDB_QA_PASS"]
OLD_TOKEN = os.environ.get("WATCHERDB_QA_OLD_TOKEN")

JS_LS_KEYS = "() => Object.keys(localStorage)"
JS_LS_TOKEN = "() => localStorage.getItem('watcherdb_token')"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


def jdetail(resp):
    try:
        return resp.json().get("detail")
    except Exception:
        return "<nao-json>"


def cookie_names(ctx):
    return [{"name": c["name"], "httpOnly": c.get("httpOnly"), "secure": c.get("secure"),
             "sameSite": c.get("sameSite"), "path": c.get("path")} for c in ctx.cookies()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake-user", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--pace", type=float, default=16.0, help="segundos entre logins (limiter 5/min em /login)")
    a = ap.parse_args()
    R = {"alvo": "<host>:" + URL.rsplit(":", 1)[-1], "ua": UA, "inicio": now(),
         "old_token_env_present": bool(OLD_TOKEN)}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        # contexto de API sem cookies (para testar tokens isoladamente)
        api = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})

        # ---- A-4.4: utilizador inventado ----
        fake = []
        for i in range(a.reps):
            t0 = time.perf_counter()
            resp = api.post(URL + "/api/auth/login",
                            data=json.dumps({"username": a.fake_user, "password": "wrong-invented-pw-p4r2"}),
                            headers={"Content-Type": "application/json", "Origin": URL})
            fake.append({"rep": i + 1, "t": now(), "status": resp.status, "detail": jdetail(resp),
                         "ms": round((time.perf_counter() - t0) * 1000, 1)})
            time.sleep(a.pace)
        R["a44_fake_user"] = fake

        # ---- A-4.7: token antigo do owner (se existir) ----
        if OLD_TOKEN:
            r7 = api.get(URL + "/api/auth/me", headers={"Authorization": "Bearer " + OLD_TOKEN})
            R["a47_old_token_me"] = {"t": now(), "status": r7.status,
                                     "detail": jdetail(r7) if r7.status != 200 else None}
        else:
            R["a47_old_token_me"] = "NAO VERIFICAVEL: WATCHERDB_QA_OLD_TOKEN ausente"

        # ---- A-4.3 reps: login UI -> logout UI -> token antigo ----
        reps = []
        for i in range(a.reps):
            ctx = browser.new_context(viewport={"width": 1366, "height": 768}, color_scheme="dark",
                                      ignore_https_errors=True, user_agent=UA,
                                      extra_http_headers={"User-Agent": UA})
            page = ctx.new_page()
            rep = {"rep": i + 1, "t_login": now()}
            net = {"logout": []}

            def on_resp(resp, net=net):
                if resp.request.method == "POST" and "/api/auth/logout" in resp.url:
                    try:
                        d = resp.json()
                    except Exception:
                        d = "<nao-json>"
                    hdrs = {k.lower() for k in resp.request.headers.keys()}
                    net["logout"].append({"status": resp.status, "body": d,
                                          "req_has_authorization": "authorization" in hdrs,
                                          "req_has_cookie_header": "cookie" in hdrs})
            page.on("response", on_resp)

            page.goto(URL + "/watcherdb", wait_until="networkidle", timeout=60000)
            page.fill("#loginUsername", USER)
            page.fill("#loginPassword", PASS)
            with page.expect_response(lambda r: "/api/auth/login" in r.url) as ri:
                page.click("#loginBtn")
            lr = ri.value
            rep["login_status"] = lr.status
            if lr.status != 200:
                rep["login_detail"] = jdetail(lr)
                rep["ABORT"] = "login != 200 as " + now() + " em POST /api/auth/login; PARADO (sem repetir)"
                reps.append(rep)
                R["a43_reps"] = reps
                print(json.dumps(R, indent=1, ensure_ascii=False))
                ctx.close(); browser.close()
                return 1
            body = lr.json()
            role = str((body.get("user") or {}).get("role", "")).lower()
            rep["role"] = role
            if role == "admin":
                rep["ABORT"] = "conta ADMIN - recusada"
                reps.append(rep)
                R["a43_reps"] = reps
                print(json.dumps(R, indent=1, ensure_ascii=False))
                ctx.close(); browser.close()
                return 2
            page.wait_for_timeout(3000)

            fresh = page.evaluate(JS_LS_TOKEN) or ""  # em memoria; nunca impresso
            rep["ls_keys_after_login"] = sorted(page.evaluate(JS_LS_KEYS))
            rep["cookies_after_login"] = cookie_names(ctx)
            # A-4.7 baseline: token fresco valida (Bearer, contexto sem cookies)
            m1 = api.get(URL + "/api/auth/me", headers={"Authorization": "Bearer " + fresh})
            rep["a47_me_fresh_bearer_status"] = m1.status
            # A-4.3 baseline: so' cookie (contexto do browser, sem Bearer)
            m2 = ctx.request.get(URL + "/api/auth/me")
            rep["a43_me_cookie_only_status_before_logout"] = m2.status

            # logout pela UI
            try:
                page.evaluate("() => handleLogout()")
                rep["logout_invoked"] = True
            except Exception as e:
                rep["logout_invoked"] = False
                rep["logout_err"] = type(e).__name__
            page.wait_for_timeout(3000)
            rep["t_logout"] = now()
            rep["logout_posts"] = net["logout"]
            rep["ls_keys_after_logout"] = sorted(page.evaluate(JS_LS_KEYS))
            rep["cookies_after_logout"] = [c["name"] for c in ctx.cookies()]
            rep["cookie_access_token_present_after_logout"] = any(c["name"] == "access_token" for c in ctx.cookies())
            rep["ls_token_present_after_logout"] = "watcherdb_token" in rep["ls_keys_after_logout"]
            # token antigo (guardado em memoria) contra /api/auth/me
            m3 = api.get(URL + "/api/auth/me", headers={"Authorization": "Bearer " + fresh})
            rep["a43_me_old_bearer_after_logout"] = {"status": m3.status,
                                                     "detail": jdetail(m3) if m3.status != 200 else None}
            m4 = ctx.request.get(URL + "/api/auth/me")
            rep["a43_me_browser_ctx_after_logout"] = {"status": m4.status,
                                                      "detail": jdetail(m4) if m4.status != 200 else None}
            reps.append(rep)
            ctx.close()
            if i + 1 < a.reps:
                time.sleep(a.pace)
        R["a43_reps"] = reps
        api.dispose()
        browser.close()
    R["fim"] = now()
    print(json.dumps(R, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
