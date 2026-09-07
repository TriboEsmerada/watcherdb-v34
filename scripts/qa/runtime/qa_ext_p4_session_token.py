"""QA externo — pauta P4 (runtime). Sessao/token.

Um unico login bem-sucedido da conta QA (viewer/dba; recusa admin) reutilizado
para todas as medicoes de sessao. NUNCA imprime valores de token/cookie/password.

Cobre:
  A-4.3  localStorage keys + cookies (nomes/atributos) apos login; logout pela UI
         (handleLogout -> clearAuthData) e repete a leitura. Regista se o POST
         /api/auth/logout chega a ser chamado pela UI (captura de rede).
  A-4.4  login com utilizador INVENTADO + password inventada (nunca a conta QA):
         status + detail + timing (3 reps). Ramo "existe+password errada" e' so' fonte.
  A-4.6  GET /openapi.json (LoginResponse schema) vs corpo real do login 200
         (com token redigido).

Uso: python qa_ext_p4_session_token.py --fake-user qa_nao_existe_p4_<rnd>
"""
from __future__ import annotations
import argparse, json, os, sys, time
from playwright.sync_api import sync_playwright

UA = "WatcherDB-QA-Externo/P4"
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
USER = os.environ["WATCHERDB_QA_USER"]
PASS = os.environ["WATCHERDB_QA_PASS"]


def redact_token(body: dict) -> dict:
    out = {}
    for k, v in (body or {}).items():
        if k in ("access_token", "token") and v:
            out[k] = "<token>"
        elif k == "user" and isinstance(v, dict):
            out[k] = {kk: ("<redacted>" if kk in ("email",) else vv) for kk, vv in v.items()}
        else:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake-user", required=True)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    R = {"alvo": "<host>:" + URL.rsplit(":", 1)[-1]}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 768}, color_scheme="dark",
            ignore_https_errors=True, user_agent=UA,
            extra_http_headers={"User-Agent": UA},
        )
        page = ctx.new_page()

        # ---- A-4.6: openapi sem sessao ----
        api = ctx.request
        oa = api.get(URL + "/openapi.json")
        R["openapi_status_nosession"] = oa.status
        if oa.status == 200:
            try:
                spec = oa.json()
                R["openapi_LoginResponse"] = spec.get("components", {}).get("schemas", {}).get("LoginResponse")
            except Exception as e:
                R["openapi_parse_err"] = type(e).__name__

        # ---- A-4.4: fake user, invented password, 3 reps, timing ----
        fake = []
        for i in range(a.reps):
            t0 = time.perf_counter()
            resp = api.post(URL + "/api/auth/login", data=json.dumps({"username": a.fake_user, "password": "wrong-invented-pw-p4"}),
                            headers={"Content-Type": "application/json", "User-Agent": UA, "Origin": URL})
            dt = (time.perf_counter() - t0) * 1000
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = "<nao-json>"
            fake.append({"rep": i + 1, "status": resp.status, "detail": detail, "ms": round(dt, 1)})
        R["a44_fake_user"] = fake

        # ---- Login real (UI) ----
        net = {"login_posts": 0, "logout_posts": 0}
        def on_req(req):
            if req.method == "POST" and "/api/auth/login" in req.url: net["login_posts"] += 1
            if req.method == "POST" and "/api/auth/logout" in req.url: net["logout_posts"] += 1
        page.on("request", on_req)

        page.goto(URL + "/watcherdb", wait_until="networkidle", timeout=60000)
        login_body = {}
        page.fill("#loginUsername", USER)
        page.fill("#loginPassword", PASS)
        with page.expect_response(lambda r: "/api/auth/login" in r.url) as ri:
            page.click("#loginBtn")
        lr = ri.value
        R["login_status"] = lr.status
        if lr.status != 200:
            try: R["login_detail"] = lr.json().get("detail")
            except Exception: R["login_detail"] = "<nao-json>"
            R["ABORT"] = "login != 200; sem medicoes de sessao"
            print(json.dumps(R, indent=1, ensure_ascii=False)); ctx.close(); browser.close(); return 1
        try:
            login_body = lr.json()
        except Exception:
            login_body = {}
        R["a46_login_body_keys"] = sorted(login_body.keys())
        R["a46_login_body_redacted"] = redact_token(login_body)
        R["a46_login_top_has_token"] = "token" in login_body
        R["a46_login_top_has_role"] = "role" in login_body
        R["a46_login_has_access_token"] = "access_token" in login_body
        R["a46_login_user_role"] = (login_body.get("user") or {}).get("role")
        role = str((login_body.get("user") or {}).get("role", "")).lower()
        if role == "admin":
            R["ABORT"] = "conta ADMIN — recusada"
            print(json.dumps(R, indent=1, ensure_ascii=False)); ctx.close(); browser.close(); return 2
        page.wait_for_timeout(3000)

        # ---- A-4.3: after login ----
        ls_keys = page.evaluate("() => Object.keys(localStorage)")
        R["a43_localstorage_keys_after_login"] = sorted(ls_keys)
        R["a43_localstorage_has_token_key"] = "watcherdb_token" in ls_keys
        cookies = ctx.cookies()
        R["a43_cookies_after_login"] = [
            {"name": c["name"], "httpOnly": c.get("httpOnly"), "secure": c.get("secure"),
             "sameSite": c.get("sameSite"), "path": c.get("path")} for c in cookies]
        R["a43_cookie_access_token_present_after_login"] = any(c["name"] == "access_token" for c in cookies)

        # ---- logout via UI ----
        did_logout = False
        try:
            page.evaluate("() => handleLogout()")
            did_logout = True
        except Exception as e:
            R["a43_logout_err"] = type(e).__name__
        page.wait_for_timeout(2500)
        R["a43_logout_invoked"] = did_logout
        R["a43_ui_calls_logout_endpoint"] = net["logout_posts"] > 0
        R["a43_login_posts_seen"] = net["login_posts"]
        ls2 = page.evaluate("() => Object.keys(localStorage)")
        R["a43_localstorage_keys_after_logout"] = sorted(ls2)
        R["a43_localstorage_token_cleared"] = "watcherdb_token" not in ls2
        cookies2 = ctx.cookies()
        R["a43_cookies_after_logout"] = [
            {"name": c["name"], "httpOnly": c.get("httpOnly"), "path": c.get("path")} for c in cookies2]
        R["a43_cookie_access_token_present_after_logout"] = any(c["name"] == "access_token" for c in cookies2)

        ctx.close(); browser.close()
    print(json.dumps(R, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
