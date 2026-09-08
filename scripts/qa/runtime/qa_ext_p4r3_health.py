"""QA externo — pauta P4 RONDA 3 (runtime). Gate A-4.7 apos 7a12a94.

  (b) GET /api/v3/health: sem sessao, com Bearer (contexto sem cookies) e so' com cookie (contexto
      que fez o login): status + auth.reset_revocation + checked_at (para ver a cache de 60 s), N reps
      espacadas por --pace segundos (>60 s no total => pelo menos uma sondagem fresca).
  (a) baseline: GET /api/auth/me com o token fresco => 200. Token anterior ao reset SO' se
      WATCHERDB_QA_OLD_TOKEN existir (senao NAO VERIFICAVEL em runtime; nunca derivado).

Um unico login (POST /api/auth/login). PARA ao primeiro 401 da conta QA. Recusa ADMIN.
Nao imprime tokens, cookies, passwords, emails, hosts.
Uso: python qa_ext_p4r3_health.py --reps 3 --pace 35
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

UA = os.environ.get("WATCHERDB_QA_UA", "WatcherDB-QA-Externo/P4r3")
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
USER = os.environ["WATCHERDB_QA_USER"]
PASS = os.environ["WATCHERDB_QA_PASS"]
OLD_TOKEN = os.environ.get("WATCHERDB_QA_OLD_TOKEN")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


def jbody(resp):
    try:
        return resp.json()
    except Exception:
        return {"_raw": "<nao-json>"}


def health_view(resp) -> dict:
    b = jbody(resp)
    auth = b.get("auth") if isinstance(b, dict) else None
    return {"t": now(), "status": resp.status,
            "detail": b.get("detail") if isinstance(b, dict) and resp.status != 200 else None,
            "top_keys": sorted(b.keys()) if isinstance(b, dict) else None,
            "auth": auth}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--pace", type=float, default=35.0)
    a = ap.parse_args()
    R = {"alvo": "<host>:" + URL.rsplit(":", 1)[-1], "ua": UA, "inicio": now(),
         "old_token_env_present": bool(OLD_TOKEN)}
    with sync_playwright() as p:
        anon = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})
        bearer_ctx = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})
        cookie_ctx = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})

        # login (uma vez) no contexto que guardara' o cookie
        lr = cookie_ctx.post(URL + "/api/auth/login",
                             data=json.dumps({"username": USER, "password": PASS}),
                             headers={"Content-Type": "application/json", "Origin": URL})
        R["login"] = {"t": now(), "status": lr.status}
        if lr.status != 200:
            R["login"]["detail"] = jbody(lr).get("detail")
            R["ABORT"] = "login != 200 em POST /api/auth/login; PARADO (sem repetir)"
            print(json.dumps(R, indent=1, ensure_ascii=False)); return 1
        body = jbody(lr)
        role = str((body.get("user") or {}).get("role", "")).lower()
        R["login"]["role"] = role
        if role == "admin":
            R["ABORT"] = "conta ADMIN - recusada"
            print(json.dumps(R, indent=1, ensure_ascii=False)); return 2
        fresh = body.get("access_token") or body.get("token") or ""  # em memoria; nunca impresso
        R["login"]["token_in_body"] = bool(fresh)
        R["login"]["cookie_names"] = sorted({c["name"] for c in cookie_ctx.storage_state().get("cookies", [])})

        # A-4.7 baseline (a): token fresco valida
        m = bearer_ctx.get(URL + "/api/auth/me", headers={"Authorization": "Bearer " + fresh})
        R["a47_me_fresh_bearer"] = {"t": now(), "status": m.status}
        m2 = cookie_ctx.get(URL + "/api/auth/me")
        R["a47_me_cookie_only"] = {"t": now(), "status": m2.status}
        if OLD_TOKEN:
            o = bearer_ctx.get(URL + "/api/auth/me", headers={"Authorization": "Bearer " + OLD_TOKEN})
            R["a47_old_token_me"] = {"t": now(), "status": o.status,
                                     "detail": jbody(o).get("detail") if o.status != 200 else None}
        else:
            R["a47_old_token_me"] = "NAO VERIFICAVEL: WATCHERDB_QA_OLD_TOKEN ausente"

        # A-4.7 (b): health nos tres modos, N reps
        reps = []
        for i in range(a.reps):
            reps.append({
                "rep": i + 1,
                "anon": health_view(anon.get(URL + "/api/v3/health")),
                "bearer": health_view(bearer_ctx.get(URL + "/api/v3/health",
                                                     headers={"Authorization": "Bearer " + fresh})),
                "cookie": health_view(cookie_ctx.get(URL + "/api/v3/health")),
            })
            if i + 1 < a.reps:
                time.sleep(a.pace)
        R["a47b_health"] = reps
        # cortesia: fecha a sessao (POST /api/auth/logout e' permitido pela pauta)
        lo = cookie_ctx.post(URL + "/api/auth/logout", headers={"Authorization": "Bearer " + fresh, "Origin": URL})
        R["logout"] = {"t": now(), "status": lo.status}
        for c in (anon, bearer_ctx, cookie_ctx):
            c.dispose()
    R["fim"] = now()
    print(json.dumps(R, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
