"""QA externo — pauta 1 / A-1 (runtime).

POST /api/auth/login (unico POST autorizado ao QA externo) com:
  --origin-probe : (1) Origin estranho -> esperado 403 pelo SameOriginMiddleware (ronda 1)
                   (4) Origin same-site noutro sub-host -> esperado 403
  (2) Origin correto + credencial valida -> esperado 200 + Set-Cookie access_token
      com HttpOnly/SameSite/Secure/Path/Max-Age (3 repeticoes; PARA ao 1.o 401)
  (5) GET /api/version e /api/health com o cookie da sessao -> versao do runtime
Imprime apenas status e NOMES/valores de ATRIBUTOS do cookie. Nunca imprime o valor
do cookie/token, hosts ou credenciais.
"""
from __future__ import annotations

import argparse
import http.cookiejar
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

# Jar so' para reutilizar o cookie no GET; nunca e' impresso.
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=CTX), urllib.request.HTTPCookieProcessor(JAR)
)


def _do(req):
    try:
        with OPENER.open(req, timeout=20) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def post_login(origin: str, username: str, password: str):
    body = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        URL + "/api/auth/login",
        data=body,
        method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json", "Origin": origin},
    )
    return _do(req)


def get(path: str):
    req = urllib.request.Request(URL + path, method="GET", headers={"User-Agent": UA})
    return _do(req)


def cookie_attrs(headers) -> list[str]:
    """Nome do cookie + atributos (nome=valor dos atributos; valor do cookie redigido)."""
    out = []
    for k, v in headers.items():
        if k.lower() == "set-cookie":
            name = v.split("=", 1)[0]
            attrs = [p.strip() for p in v.split(";")[1:]]
            out.append(f"{name}=<redacted>; " + "; ".join(attrs))
    return out


def redact(s: str) -> str:
    host = re.sub(r"^https?://", "", URL).split(":")[0]
    return s.replace(host, "<host>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin-probe", action="store_true", help="repete os controlos de Origin da ronda 1")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    print("alvo: <host>:" + URL.rsplit(":", 1)[-1])

    if a.origin_probe:
        st, hd, body = post_login("https://evil.example", "qa-invalid", "qa-invalid")
        print(f"[1] Origin=https://evil.example status={st} body={redact(body.decode(errors='replace')[:80])}")
        st, hd, body = post_login(URL.replace("://", "://x.", 1), "qa-invalid", "qa-invalid")
        print(f"[4] Origin=<sub.host same-site> status={st}")

    role = None
    for i in range(a.reps):
        st, hd, body = post_login(URL, USER, PASS)
        try:
            j = json.loads(body)
            keys = sorted(j.keys())
            role = str((j.get("user") or {}).get("role", "")).lower() or role
        except Exception:
            keys = ["<nao-json>"]
        print(f"[2] rep{i+1} Origin=<mesma origem> cred. valida status={st} set-cookie={[redact(c) for c in cookie_attrs(hd)]} body keys={keys}")
        if st == 401:
            # Ronda 3: regista o `detail` (mensagem do servidor; nunca a credencial) antes de parar.
            try:
                detail = redact(str(json.loads(body).get("detail", ""))[:120])
            except Exception:
                detail = "<nao-json>"
            print(f"    401 detail={detail!r} -> PARO (contador de bloqueio activo). Sem mais tentativas.")
            return 1
    print(f"    perfil devolvido pelo login: {role!r} (admin seria recusado pelo charter)")
    if role == "admin":
        print("    conta ADMIN — recusado; nao prossigo.")
        return 2

    for path in ("/api/version", "/api/health"):
        st, hd, body = get(path)
        txt = body.decode(errors="replace")
        try:
            j = json.loads(txt)
            # so' campos de versao/estado; nada de hosts/instancias
            keep = {k: j[k] for k in j if k.lower() in ("version", "app_version", "status", "edition", "build", "release", "name", "api_version", "ok")}
        except Exception:
            keep = {"raw": redact(txt[:100])}
        print(f"[5] GET {path} (cookie da sessao) status={st} -> {keep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
