"""QA externo — pauta 1 / A-1 (runtime).

POST /api/auth/login (unico POST autorizado ao QA externo) com:
  (1) Origin estranho  -> esperado 403 pelo SameOriginMiddleware
  (2) Origin correto   -> esperado 200 + Set-Cookie access_token com HttpOnly/SameSite
  (3) Origin correto, credenciais erradas (controlo)
Imprime apenas status e NOMES de atributos do cookie. Nunca imprime valores,
hosts ou credenciais.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

UA = "WatcherDB-QA-Externo/pauta-1"
URL = os.environ["WATCHERDB_QA_URL"].rstrip("/")
USER = os.environ["WATCHERDB_QA_USER"]
PASS = os.environ["WATCHERDB_QA_PASS"]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def post_login(origin: str, username: str, password: str):
    body = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        URL + "/api/auth/login",
        data=body,
        method="POST",
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Origin": origin,
        },
    )
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=20) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def cookie_attrs(headers) -> list[str]:
    out = []
    for k, v in headers.items():
        if k.lower() == "set-cookie":
            name = v.split("=", 1)[0]
            attrs = [p.strip().split("=", 1)[0] for p in v.split(";")[1:]]
            # SameSite: manter o valor (Lax/Strict/None) -- nao e' segredo
            m = re.search(r"samesite=([a-z]+)", v, re.I)
            if m:
                attrs = [a for a in attrs if a.lower() != "samesite"] + [f"SameSite={m.group(1)}"]
            out.append(f"{name}=<redacted>; " + "; ".join(attrs))
    return out


def main():
    print("alvo: <host>:" + URL.rsplit(":", 1)[-1] if URL.count(":") >= 2 else "alvo: <host>")
    for i in range(3):
        st, hd, body = post_login("https://evil.example", "qa-invalid", "qa-invalid")
        txt = body.decode(errors="replace")[:120]
        print(f"[1] Origin=https://evil.example  rep{i+1}: status={st} body={txt}")
    st, hd, body = post_login(URL, USER, PASS)
    print(f"[2] Origin=<mesma origem>          status={st} set-cookie={cookie_attrs(hd)}")
    try:
        keys = sorted(json.loads(body).keys())
    except Exception:
        keys = ["<nao-json>"]
    print(f"    body keys={keys}")
    st, hd, body = post_login(URL, "qa-invalid", "qa-invalid")
    print(f"[3] Origin=<mesma origem>, cred. erradas (controlo) status={st} set-cookie={cookie_attrs(hd)}")
    st, hd, body = post_login(URL.replace("://", "://x.", 1), "qa-invalid", "qa-invalid")
    print(f"[4] Origin=<sub.host same-site> (controlo same-site) status={st}")


if __name__ == "__main__":
    sys.exit(main())
