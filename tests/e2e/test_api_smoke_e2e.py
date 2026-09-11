"""TESTSUKITA V1 - smoke de API a partir do OpenAPI, por perfil (o que o TestSprite chama "API tests").

Le /openapi.json com o token do perfil; percorre os GET sem params ou com params substituiveis
(server_id/instance/hostname -> servidor de teste; kpi_type -> always-on). Invariantes:
  - nunca 5xx;
  - viewer nunca recebe campos sensiveis (password_hash, PWD=, Trusted_Connection, access_token fora do login);
  - viewer nunca recebe 200 em caminhos /admin;
  - cada endpoint responde em < WATCHERDB_QA_API_TIMEOUT_S (default 20; acima = aviso, nao falha).
Grava status e tempo por endpoint e perfil; o ratchet compara noite a noite.
  WATCHERDB_QA_API_MAX (default 150 endpoints), WATCHERDB_QA_API_BUDGET_S (default 300 s)
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_spec = importlib.util.spec_from_file_location("smoke_helpers", Path(__file__).with_name("test_smoke_modules_e2e.py"))
_smk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smk)

PERFIS = _smk.PERFIS
API_MAX = int(os.getenv("WATCHERDB_QA_API_MAX", "150"))
BUDGET_S = int(os.getenv("WATCHERDB_QA_API_BUDGET_S", "300"))
TIMEOUT_S = int(os.getenv("WATCHERDB_QA_API_TIMEOUT_S", "20"))
EXCLUIR = re.compile(r"/(docs|redoc|openapi\.json|login|logout|run|execute|reset|restart|download|export|stream|sse|ws|realtime|live|"
                     r"\.well-known|collector/run|kill|shrink|action|network-test)", re.I)  # V1 PASSO 3: network-test e' sonda (15 s, efeitos)
# V1 PASSO 3: caminhos /admin publicos por desenho (so' contadores) - achado #6 registado; ate' decisao, nao contam como fuga.
ADMIN_PUBLICO = {"/api/admin/health"}
SENSIVEL = re.compile(r"password_hash|\"password\"\s*:|PWD=|Trusted_Connection|secret_key|private_key", re.I)


def _substitui(path: str, servidor: dict) -> str | None:
    mapa = {
        "server_id": servidor["server_id"], "instance": servidor["server_id"], "instance_name": servidor["server_id"],
        "hostname": servidor["name"].split("\\")[0], "kpi_type": "always-on",
    }
    def sub(m):
        return str(mapa.get(m.group(1), "\x00"))
    out = re.sub(r"\{(\w+)\}", sub, path)
    return None if "\x00" in out else out


@pytest.mark.parametrize("perfil", [_smk._perfil_param(p) for p in PERFIS])
class TestApiSmoke:
    def test_get_endpoints_por_perfil(self, page, base_url, perfil):
        user, token = _smk._token(page, base_url, perfil)
        h = {"Authorization": f"Bearer {token}"}
        spec = page.context.request.get(f"{base_url}/openapi.json", headers=h, timeout=TIMEOUT_S * 1000)
        if spec.status == 404:
            pytest.skip("/openapi.json desligado (WATCHERDB_DISABLE_DOCS): smoke de API nao aplicavel")
        assert spec.ok, f"/openapi.json devolveu {spec.status}"
        paths = spec.json().get("paths", {})
        servidor = None
        try:
            _smk._autentica(page, base_url, perfil)
            servidor = _smk._escolhe_servidor(page)
        except Exception:  # noqa: BLE001
            servidor = None
        alvo = []
        saltados = {"excluido": 0, "sem_substituicao": 0}
        for p, ops in paths.items():
            if "get" not in ops:
                continue
            if EXCLUIR.search(p):
                saltados["excluido"] += 1; continue
            if "{" in p:
                if not servidor:
                    saltados["sem_substituicao"] += 1; continue
                q = _substitui(p, servidor)
                if not q:
                    saltados["sem_substituicao"] += 1; continue
                alvo.append((p, q))
            else:
                alvo.append((p, p))
        alvo = alvo[:API_MAX]
        resultados, problemas, avisos = [], [], []
        t_ini = time.time()
        for original, url in alvo:
            if time.time() - t_ini > BUDGET_S:
                avisos.append(f"orcamento de {BUDGET_S}s esgotado apos {len(resultados)} endpoints")
                break
            t0 = time.time()
            try:
                r = page.context.request.get(f"{base_url}{url}", headers=h, timeout=TIMEOUT_S * 1000)
                status, corpo = r.status, (r.text() or "")[:20000]
            except Exception as exc:  # noqa: BLE001
                status, corpo = -1, type(exc).__name__
            ms = int((time.time() - t0) * 1000)
            sens = bool(SENSIVEL.search(corpo)) if status == 200 else False
            item = {"path": original, "url": url, "status": status, "ms": ms, "sensivel": sens}
            if status >= 500:
                item["hipotese"] = "500 real do servico: procurar o traceback em council/service_log_window.log pelo caminho"
            elif status == -1:
                item["hipotese"] = f"sem resposta em {TIMEOUT_S}s: endpoint lento ou instancia sem resposta"
            resultados.append(item)
            if status >= 500:
                problemas.append(f"{original}: {status}")
            if status == -1:
                avisos.append(f"{original}: sem resposta em {TIMEOUT_S}s")
            if perfil == "viewer":
                if sens:
                    problemas.append(f"{original}: viewer recebeu campo sensivel")
                if status == 200 and "/admin" in original and original not in ADMIN_PUBLICO:
                    problemas.append(f"{original}: viewer recebeu 200 num caminho /admin")
            if ms > TIMEOUT_S * 1000 * 0.8:
                avisos.append(f"{original}: {ms} ms")
        _smk._grava({
            "caso": "api_smoke", "perfil": perfil, "user": user, "server": servidor, "endpoints": resultados,
            "saltados": saltados, "total_openapi_get": sum(1 for ops in paths.values() if "get" in ops),
            "load_ms": int((time.time() - t_ini) * 1000), "dom_nodes": 0,
            "pageerrors": [], "console_errors": [], "http5xx": [f"{r['status']} GET {r['url']}" for r in resultados if r["status"] >= 500],
            "warn": avisos,
        })
        assert resultados, f"[{perfil}] nenhum endpoint GET testavel"
        assert not problemas, f"[{perfil}] API:\n  - " + "\n  - ".join(problemas[:20])
