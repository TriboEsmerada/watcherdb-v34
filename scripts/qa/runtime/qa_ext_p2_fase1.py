"""QA externo — pauta P2 FASE 1 (runtime). Credenciais e base de dados.

Cobre (so' GET + POST /api/auth/login; NUNCA logout — o token fresco tem de sobreviver ate' a fase 2):
  alvo    GET /api/v3/health anonimo ×3 (chaves de topo), GET /api/version e /api/health sem sessao.
  A-2.4   1 login com a conta QA (recusa ADMIN); GET /api/auth/me ×3 (baseline 200); token fresco
          gravado APENAS no scratchpad (fora do repo), sem newline; iat/exp do JWT lidos do payload
          (base64, sem verificar assinatura) e impressos como timestamps — nunca o token.
  A-2.6   GET /api/v3/health com Bearer ×3 e so' com cookie ×3: chaves de topo; diff vs anonimo.
  A-2.5   6 tentativas de login FALHADAS, espacadas por --pace s (limite 5/min por IP em
          auth_compat.py:324): nope1, nope2, QA-conta-com-password-errada (UMA so'), nope3, nope4, nope5.
          Para cada: status, detail (byte a byte), nomes de headers + valores de WWW-Authenticate/
          Retry-After/X-RateLimit-*, tempo total (ms, perf_counter em volta do pedido).

Nao imprime tokens, cookies, passwords, emails, hosts. UA identificado.
Uso: python3 scripts/qa/runtime/qa_ext_p2_fase1.py --token-out <scratchpad>/p2_fresh_token.txt --pace 15
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

UA = os.environ.get("WATCHERDB_QA_UA", "WatcherDB-QA-Externo/P2")
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
USER = os.environ["WATCHERDB_QA_USER"]
PASS = os.environ["WATCHERDB_QA_PASS"]

HDR_INTEREST = ("www-authenticate", "retry-after", "x-ratelimit-limit", "x-ratelimit-remaining",
                "x-ratelimit-reset", "content-type", "content-length")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def jbody(resp):
    try:
        return resp.json()
    except Exception:
        return {"_raw": "<nao-json>"}


def top_keys(resp):
    b = jbody(resp)
    return sorted(b.keys()) if isinstance(b, dict) else None


def jwt_times(token: str) -> dict:
    try:
        seg = token.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        p = json.loads(base64.urlsafe_b64decode(seg.encode()).decode())
        out = {}
        for k in ("iat", "exp"):
            if k in p:
                out[k] = datetime.fromtimestamp(float(p[k]), tz=timezone.utc).isoformat()
        out["claims"] = sorted(p.keys())
        return out
    except Exception:
        return {"erro": "payload nao decodificavel"}


def timed_login(ctx, username: str, password: str) -> dict:
    t0 = time.perf_counter()
    r = ctx.post(URL + "/api/auth/login",
                 data=json.dumps({"username": username, "password": password}),
                 headers={"Content-Type": "application/json", "Origin": URL})
    ms = round((time.perf_counter() - t0) * 1000, 1)
    b = jbody(r)
    hdrs = r.headers  # dict lower-case
    return {
        "t": now(), "status": r.status, "ms": ms,
        "detail": b.get("detail") if isinstance(b, dict) else None,
        "detail_bytes": len(json.dumps(b.get("detail"), ensure_ascii=False).encode()) if isinstance(b, dict) else None,
        "body_keys": sorted(b.keys()) if isinstance(b, dict) else None,
        "header_names": sorted(hdrs.keys()),
        "headers_interest": {k: hdrs.get(k) for k in HDR_INTEREST if k in hdrs},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-out", required=True)
    ap.add_argument("--pace", type=float, default=15.0)
    ap.add_argument("--skip-a25", action="store_true")
    a = ap.parse_args()
    R = {"alvo": "<host>:" + URL.rsplit(":", 1)[-1], "ua": UA, "inicio": now()}
    with sync_playwright() as p:
        anon = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})
        bearer = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})
        cookie = p.request.new_context(ignore_https_errors=True, extra_http_headers={"User-Agent": UA})

        # alvo / A-2.6 anonimo
        R["anon_health_v3"] = [{"t": now(), "status": r.status, "top_keys": top_keys(r)}
                               for r in (anon.get(URL + "/api/v3/health") for _ in range(3))]
        R["anon_version"] = {"status": anon.get(URL + "/api/version").status}
        R["anon_health"] = {"status": anon.get(URL + "/api/health").status}

        # A-2.4 login (uma vez)
        lr = cookie.post(URL + "/api/auth/login",
                         data=json.dumps({"username": USER, "password": PASS}),
                         headers={"Content-Type": "application/json", "Origin": URL})
        R["login"] = {"t": now(), "status": lr.status}
        if lr.status != 200:
            R["login"]["detail"] = jbody(lr).get("detail")
            R["ABORT"] = "login != 200; PARADO (sem repetir)"
            print(json.dumps(R, indent=1, ensure_ascii=False)); return 1
        body = jbody(lr)
        role = str((body.get("user") or {}).get("role", "")).lower()
        R["login"]["role"] = role
        if role == "admin":
            R["ABORT"] = "conta ADMIN - recusada"
            print(json.dumps(R, indent=1, ensure_ascii=False)); return 2
        fresh = body.get("access_token") or ""
        R["login"]["token_in_body"] = bool(fresh)
        R["login"]["jwt"] = jwt_times(fresh)
        R["login"]["cookie_names"] = sorted({c["name"] for c in cookie.storage_state().get("cookies", [])})
        os.makedirs(os.path.dirname(a.token_out), exist_ok=True)
        with open(a.token_out, "w", encoding="ascii", newline="") as fh:
            fh.write(fresh)
        R["token_saved"] = {"path_basename": os.path.basename(a.token_out), "bytes": len(fresh.encode())}

        auth = {"Authorization": "Bearer " + fresh}
        R["a24_me_bearer"] = [{"t": now(), "status": bearer.get(URL + "/api/auth/me", headers=auth).status}
                              for _ in range(3)]
        R["a24_me_cookie"] = [{"t": now(), "status": cookie.get(URL + "/api/auth/me").status} for _ in range(3)]
        v = bearer.get(URL + "/api/version", headers=auth)
        R["auth_version"] = {"status": v.status, "body": jbody(v)}
        h = bearer.get(URL + "/api/health", headers=auth)
        hb = jbody(h)
        R["auth_health"] = {"status": h.status, "top_keys": top_keys(h),
                            "version": hb.get("version") if isinstance(hb, dict) else None}

        # A-2.6 com sessao
        R["bearer_health_v3"] = []
        R["cookie_health_v3"] = []
        for _ in range(3):
            rb = bearer.get(URL + "/api/v3/health", headers=auth)
            rc = cookie.get(URL + "/api/v3/health")
            bb, bc = jbody(rb), jbody(rc)
            R["bearer_health_v3"].append({"t": now(), "status": rb.status, "top_keys": top_keys(rb),
                                          "auth": bb.get("auth") if isinstance(bb, dict) else None})
            R["cookie_health_v3"].append({"t": now(), "status": rc.status, "top_keys": top_keys(rc),
                                          "auth": bc.get("auth") if isinstance(bc, dict) else None})
        anon_keys = set(R["anon_health_v3"][0]["top_keys"] or [])
        sess_keys = set(R["bearer_health_v3"][0]["top_keys"] or [])
        R["a26_diff"] = {"so_com_sessao": sorted(sess_keys - anon_keys), "so_anonimo": sorted(anon_keys - sess_keys)}

        # A-2.5
        if not a.skip_a25:
            seq = []
            plan = ["nope", "nope", "qa-wrong", "nope", "nope", "nope"]
            for i, kind in enumerate(plan):
                time.sleep(a.pace)  # o login real tambem conta para o 5/min
                if kind == "nope":
                    u = "qa-ext-nope-" + secrets.token_hex(4)
                    rec = timed_login(anon, u, "Nope-" + secrets.token_hex(6) + "!1")
                    rec["kind"] = "inexistente"
                else:
                    rec = timed_login(anon, USER, "Errada-" + secrets.token_hex(6) + "!1")
                    rec["kind"] = "conta_qa_password_errada"
                seq.append(rec)
            R["a25"] = seq
            nope = [x["ms"] for x in seq if x["kind"] == "inexistente"]
            wrong = [x["ms"] for x in seq if x["kind"] != "inexistente"]
            R["a25_resumo"] = {
                "detail_inexistente": sorted({x["detail"] for x in seq if x["kind"] == "inexistente"}),
                "detail_qa_errada": sorted({x["detail"] for x in seq if x["kind"] != "inexistente"}),
                "status_set": sorted({x["status"] for x in seq}),
                "ms_inexistente": nope, "ms_inexistente_min_max": [min(nope), max(nope)] if nope else None,
                "ms_qa_errada": wrong,
                "header_names_identicos": len({tuple(x["header_names"]) for x in seq}) == 1,
            }
        for c in (anon, bearer, cookie):
            c.dispose()
    R["fim"] = now()
    print(json.dumps(R, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
