# -*- coding: utf-8 -*-
"""P0 do plano de atribuicao de query a aplicacao: Performance Module com redaccao por role
e gates de escrita (2026-09-24).

ACHADO (revisao do plano, verificado pelo orquestrador no V3.4 e no V6):
  api/routers/performance.py (prefixo /api/v1/performance, 10 endpoints) nao tem NENHUM
  Depends de role. A redaccao por role (_redact_node / _RoleRedactingRoute) existe so' em
  api/routers/live_monitoring.py:100-167 e cobre so' /api/v1/live. O AuthEnforcementMiddleware
  (watcherdb_main.py:696-733) so' exige token: nunca olha ao role. Resultado: um VIEWER le
  sql_text cru dos 8 investigators (17 colunas `AS sql_text` em modules/performance/investigators),
  inputbuf/hostname/clientapp dos deadlocks, login/host/program das sessoes activas, e pode
  escrever em performance_action_history (POST /action-history) -- o eixo do RBAC decidido pelo
  owner a 2026-08-16 e' ler-vs-escrever.

O QUE MUDA (3 ficheiros + 1 teste):
  api/role_redaction.py (NOVO)          modulo partilhado: REDACTED, SQL_FIELDS, IDENTITY_FIELDS,
                                        redact_node, role_do_pedido, RoleRedactingRoute. Conjunto de
                                        campos = uniao do LIVE com os do Performance (inputbuf,
                                        hostname, clientapp, statement_text, action_sql, sample_text).
  api/routers/live_monitoring.py        o bloco local (_REDACTED .. _RoleRedactingRoute) passa a
                                        importar do modulo partilhado com os MESMOS nomes privados;
                                        comportamento identico, conjunto de campos alargado.
  api/routers/performance.py            router com route_class=RoleRedactingRoute (viewer ve hash
                                        estavel do SQL e "[oculto]" nas identidades; dba/admin veem
                                        tudo, como no LIVE); POST /action-history e POST
                                        /ticket-response exigem dba (escrita; e o ticket embute SQL
                                        em prosa que a redaccao por campo nao apanha). Gate no
                                        decorador (dependencies=[...]), resolvido ANTES do corpo:
                                        viewer recebe 403, nunca 422 (achado R2-01 do QA externo).
  tests/unit/test_performance_role_gate_20260924.py (NOVO)

O QUE NAO MUDA: POST /investigate continua aberto ao viewer (e' diagnostico, como o LIVE; a
resposta sai redigida); GET /runbooks, /investigators, /snapshot, /investigations, /incidents,
/action-history (GET) idem, redigidos. O interruptor rbac_live_admin_only continua so' no LIVE.

EFEITO EM PRODUCAO: viewer passa a ver "[oculto - requer nivel dba] #hash" no Performance
Module onde via SQL cru; dba/admin sem alteracao. Rollback: git revert do commit.

PROPAGACAO V6: docs/context/PROMPT_PROPAGACAO_V6_ATRIBUICAO_APP_2026-09-24.md (P0 + P0b).

Uso:
  py docs/context/P0_PERFORMANCE_ROLE_GATE_2026-09-24_apply.py --check
  py docs/context/P0_PERFORMANCE_ROLE_GATE_2026-09-24_apply.py --preview
  py docs/context/P0_PERFORMANCE_ROLE_GATE_2026-09-24_apply.py --repo <copia>   (prova na copia)
  py docs/context/P0_PERFORMANCE_ROLE_GATE_2026-09-24_apply.py                  (aplica no repo)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LIVE = Path("api/routers/live_monitoring.py")
PERF = Path("api/routers/performance.py")
SHARED = Path("api/role_redaction.py")
TEST = Path("tests/unit/test_performance_role_gate_20260924.py")

# ---------------------------------------------------------------------------
# 1. Modulo partilhado
# ---------------------------------------------------------------------------
SHARED_SRC = '''"""Redaccao por role das respostas JSON dos routers de diagnostico.

Nasceu em api/routers/live_monitoring.py (R2-02 do QA externo, 2026-08-16) e passou a modulo
partilhado a 2026-09-24 (P0 do plano de atribuicao de query a aplicacao) porque o Performance
Module devolvia exactamente os mesmos campos -- sql_text, logins, hosts -- sem nenhum gate.

Regra: `viewer` ve um hash estavel do SQL (agrupa ocorrencias sem ver o texto) e "[oculto]" nas
identidades; `dba` e `admin` veem tudo. Feito ao nivel do ROUTER (route_class) e nao endpoint a
endpoint: o endpoint numero 17 nasce coberto sem ninguem se lembrar.

O SQL nao e' truncado de proposito: truncar continua a revelar nomes de tabela e a forma da query.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional

from fastapi import Request, Response
from fastapi.routing import APIRoute

REDACTED = "[oculto - requer nivel dba]"

# Campos com texto SQL (viewer ve hash estavel). Uniao LIVE + Performance Module.
SQL_FIELDS = frozenset({
    "sql_text", "full_sql_text", "full_query_text", "blocked_sql", "blocker_sql",
    "statement_text", "sample_text", "inputbuf", "action_sql",
})
# Campos de identidade (viewer ve o literal REDACTED).
IDENTITY_FIELDS = frozenset({
    "login_name", "blocked_login", "blocker_login",
    "host_name", "client_host", "blocked_host", "blocker_host", "hostname",
    "program_name", "clientapp",
})


def redact_node(node: Any) -> Any:
    """Percorre a arvore da resposta e redige os campos sensiveis."""
    if isinstance(node, list):
        return [redact_node(item) for item in node]
    if isinstance(node, dict):
        saida = {}
        for chave, valor in node.items():
            if chave in SQL_FIELDS and isinstance(valor, str) and valor.strip():
                digest = hashlib.sha256(valor.encode("utf-8", "replace")).hexdigest()[:12]
                saida[chave] = f"{REDACTED} #{digest}"
            elif chave in IDENTITY_FIELDS and isinstance(valor, str) and valor.strip():
                saida[chave] = REDACTED
            else:
                saida[chave] = redact_node(valor)
        return saida
    return node


def role_do_pedido(request: Request) -> Optional[str]:
    """Role do utilizador, posto no request.state pelo AuthEnforcementMiddleware."""
    user = getattr(request.state, "user", None)
    if isinstance(user, dict):
        return user.get("role")
    return None


class RoleRedactingRoute(APIRoute):
    """Redige a resposta quando quem pede e' `viewer`. `dba`/`admin` veem tudo."""

    def get_route_handler(self) -> Callable:
        handler_original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await handler_original(request)
            if role_do_pedido(request) != "viewer":
                return response
            corpo = getattr(response, "body", None)
            if not corpo or "application/json" not in response.headers.get("content-type", ""):
                return response
            try:
                payload = json.loads(corpo)
            except Exception:
                # Um corpo que nao e' JSON nao contem os campos que nos preocupam.
                return response
            novo = json.dumps(redact_node(payload), default=str).encode("utf-8")
            response.body = novo
            response.headers["content-length"] = str(len(novo))
            return response

        return handler
'''

# ---------------------------------------------------------------------------
# 2. LIVE: bloco local -> import do modulo partilhado (mesmos nomes privados)
# ---------------------------------------------------------------------------
LIVE_BLOCK_START = '_REDACTED = "[oculto - requer nivel dba]"\n'
LIVE_BLOCK_END = 'router = APIRouter(\n    prefix="/api/v1/live",\n'
LIVE_IMPORT = '''# 2026-09-24 (P0 atribuicao app): a implementacao vive em api/role_redaction.py, partilhada com o
# Performance Module. Os nomes privados mantem-se para nao tocar no resto deste ficheiro.
from api.role_redaction import (  # noqa: E402
    REDACTED as _REDACTED,
    SQL_FIELDS as _SQL_FIELDS,
    IDENTITY_FIELDS as _IDENTITY_FIELDS,
    redact_node as _redact_node,
    role_do_pedido as _role_do_pedido,
    RoleRedactingRoute as _RoleRedactingRoute,
)


'''

# ---------------------------------------------------------------------------
# 3. Performance router
# ---------------------------------------------------------------------------
PERF_EDITS = [
    (
        "from fastapi import APIRouter, Body, HTTPException, Query\n",
        "from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request\n",
    ),
    (
        "from api.error_helpers import safe_http_error\n",
        "from api.error_helpers import safe_http_error\n"
        "from api.role_redaction import RoleRedactingRoute\n",
    ),
    (
        'router = APIRouter(prefix="/api/v1/performance", tags=["Performance Intelligence"])\n',
        '# 2026-09-24 (P0 atribuicao app): este router devolve texto SQL cru, logins e hosts, tal como o\n'
        '# LIVE, e nao tinha nenhum gate de role. Redaccao ao nivel do router (viewer ve hash/oculto;\n'
        '# dba/admin veem tudo) e gate de escrita nos POST que gravam ou embutem SQL em prosa.\n'
        'router = APIRouter(\n'
        '    prefix="/api/v1/performance",\n'
        '    tags=["Performance Intelligence"],\n'
        '    route_class=RoleRedactingRoute,\n'
        ')\n'
        '\n'
        '\n'
        'async def _perf_write_gate(request: Request) -> None:\n'
        '    """dba/admin para escrever (eixo ler-vs-escrever do RBAC, decisao do owner 2026-08-16).\n'
        '\n'
        '    Usar no decorador (`dependencies=[Depends(_perf_write_gate)]`), nunca no corpo: o FastAPI\n'
        '    resolve as dependencias antes do corpo, logo o viewer recebe 403 e nao 422 (R2-01 do QA).\n'
        '    """\n'
        '    from api.routers.auth_compat import _require_dba\n'
        '    await _require_dba(request)\n',
    ),
    (
        '@router.post("/action-history")\n',
        '@router.post("/action-history", dependencies=[Depends(_perf_write_gate)])\n',
    ),
    (
        '@router.post("/ticket-response")\n',
        '@router.post("/ticket-response", dependencies=[Depends(_perf_write_gate)])\n',
    ),
]

# ---------------------------------------------------------------------------
# 4. Teste
# ---------------------------------------------------------------------------
TEST_SRC = '''# -*- coding: utf-8 -*-
"""P0 (2026-09-24): Performance Module redige por role e exige dba para escrever.

Antes deste lote api/routers/performance.py nao tinha nenhum Depends de role: um viewer lia
sql_text cru dos investigators e escrevia em performance_action_history.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import api.role_redaction as rr
from api.routers import performance as perf_mod
from api.routers import live_monitoring as live_mod


RAW_SQL = "SELECT TOP 20 * FROM dbo.Contas WHERE Saldo < 0"


class _FakeResult:
    def to_dict(self):
        return {
            "investigator_id": "cpu_queries",
            "severity": "warning",
            "steps": [
                {
                    "name": "top_cpu",
                    "rows": [
                        {"sql_text": RAW_SQL, "login_name": "svc_core", "host_name": "APP01",
                         "program_name": ".Net SqlClient Data Provider", "total_cpu_ms": 4200},
                    ],
                },
                {"name": "deadlock", "rows": [{"inputbuf": RAW_SQL, "hostname": "APP02", "clientapp": "Core"}]},
            ],
            "sql_text": "",  # vazio nao e' redigido (nada a esconder)
        }


class _FakeInvestigator:
    async def investigate(self, instance, triggered_by="manual"):
        return _FakeResult()


class _FakeAuthService:
    """O gate de escrita passa por _require_auth, que valida um TOKEN (nao o request.state).
    Aqui o token e' o proprio role vindo do header x-test-role."""

    async def get_current_user(self, token):
        return {"username": "t", "role": token} if token else None

    def _get_user_from_db(self, username):
        return None


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(perf_mod, "get_investigator", lambda _id: _FakeInvestigator())

    async def _no_persist(result):
        return None
    monkeypatch.setattr(perf_mod, "_persist_investigation", _no_persist)

    from api.routers import auth_compat
    monkeypatch.setattr(auth_compat, "_get_token_from_request", lambda req: req.headers.get("x-test-role") or None)
    monkeypatch.setattr(auth_compat, "get_auth_service", lambda: _FakeAuthService())

    app = FastAPI()

    @app.middleware("http")
    async def _fake_auth(request: Request, call_next):
        role = request.headers.get("x-test-role")
        request.state.user = {"username": "t", "role": role} if role else None
        return await call_next(request)

    app.include_router(perf_mod.router)
    return TestClient(app)


def _investigate(client, role):
    return client.post("/api/v1/performance/investigate/SRV01/cpu_queries", headers={"x-test-role": role})


def test_viewer_ve_hash_do_sql_e_identidades_ocultas(client):
    r = _investigate(client, "viewer")
    assert r.status_code == 200
    body = r.json()
    linha = body["steps"][0]["rows"][0]
    assert linha["sql_text"].startswith(rr.REDACTED + " #") and RAW_SQL not in json.dumps(body)
    assert len(linha["sql_text"].split("#")[-1]) == 12
    assert linha["login_name"] == rr.REDACTED
    assert linha["host_name"] == rr.REDACTED
    assert linha["program_name"] == rr.REDACTED
    assert linha["total_cpu_ms"] == 4200  # metricas passam intactas
    dl = body["steps"][1]["rows"][0]
    assert dl["inputbuf"].startswith(rr.REDACTED) and dl["hostname"] == rr.REDACTED and dl["clientapp"] == rr.REDACTED
    assert body["sql_text"] == ""


def test_hash_e_estavel_para_o_mesmo_sql(client):
    a = _investigate(client, "viewer").json()["steps"][0]["rows"][0]["sql_text"]
    b = _investigate(client, "viewer").json()["steps"][0]["rows"][0]["sql_text"]
    assert a == b


@pytest.mark.parametrize("role", ["dba", "admin"])
def test_dba_e_admin_veem_tudo(client, role):
    linha = _investigate(client, role).json()["steps"][0]["rows"][0]
    assert linha["sql_text"] == RAW_SQL and linha["login_name"] == "svc_core"


def test_viewer_nao_escreve_action_history_403_antes_do_corpo(client):
    # Corpo vazio de proposito: o gate tem de responder 403 antes de o Pydantic dar 422.
    r = client.post("/api/v1/performance/action-history", headers={"x-test-role": "viewer"}, json={})
    assert r.status_code == 403


def test_viewer_nao_gera_ticket_403_antes_do_corpo(client):
    r = client.post("/api/v1/performance/ticket-response", headers={"x-test-role": "viewer"}, json={})
    assert r.status_code == 403


def test_dba_escreve_action_history(client, monkeypatch):
    import api.connection_pool as cp
    chamadas = []
    monkeypatch.setattr(cp, "execute_on_intelligence", lambda q, params=None: chamadas.append(params))
    rec = {"instance": "SRV01", "database_name": "db", "object_name": "t", "action_type": "index",
           "action_sql": "CREATE INDEX ix ON t(c)", "applied_by": "dba1"}
    r = client.post("/api/v1/performance/action-history", headers={"x-test-role": "dba"}, json=rec)
    assert r.status_code == 200 and r.json().get("success") is True and len(chamadas) == 1


def test_sem_token_nao_escreve(client):
    r = client.post("/api/v1/performance/action-history", json={})
    assert r.status_code in (401, 403)


def test_guarda_os_dois_routers_usam_a_mesma_redaccao():
    assert perf_mod.router.route_class is rr.RoleRedactingRoute
    assert live_mod.router.route_class is rr.RoleRedactingRoute
    assert live_mod._redact_node is rr.redact_node
    # o conjunto do LIVE continua coberto pelo partilhado
    for campo in ("sql_text", "full_sql_text", "full_query_text", "blocked_sql", "blocker_sql"):
        assert campo in rr.SQL_FIELDS
    for campo in ("login_name", "host_name", "client_host", "program_name", "blocked_login", "blocker_host"):
        assert campo in rr.IDENTITY_FIELDS
'''


def _read(root: Path, rel: Path) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _write(root: Path, rel: Path, txt: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(txt, encoding="utf-8", newline="\n")


def check(root: Path) -> list[str]:
    problemas: list[str] = []
    if (root / SHARED).exists():
        problemas.append(f"ja aplicado: {SHARED} existe")
    live = _read(root, LIVE)
    if live.count(LIVE_BLOCK_START) != 1 or live.count(LIVE_BLOCK_END) != 1:
        problemas.append(f"{LIVE}: ancoras do bloco de redaccao nao encontradas (ou duplicadas)")
    elif live.index(LIVE_BLOCK_START) > live.index(LIVE_BLOCK_END):
        problemas.append(f"{LIVE}: ancoras fora de ordem")
    if "api.role_redaction" in live:
        problemas.append(f"{LIVE}: ja importa o modulo partilhado")
    perf = _read(root, PERF)
    for velho, _novo in PERF_EDITS:
        if perf.count(velho) != 1:
            problemas.append(f"{PERF}: ancora nao unica: {velho.strip()[:60]!r} ({perf.count(velho)}x)")
    if "RoleRedactingRoute" in perf:
        problemas.append(f"{PERF}: ja aplicado")
    if (root / TEST).exists():
        problemas.append(f"ja existe: {TEST}")
    return problemas


def apply(root: Path, preview: bool) -> None:
    live = _read(root, LIVE)
    i0, i1 = live.index(LIVE_BLOCK_START), live.index(LIVE_BLOCK_END)
    removido = live[i0:i1]
    novo_live = live[:i0] + LIVE_IMPORT + live[i1:]
    perf = _read(root, PERF)
    for velho, novo in PERF_EDITS:
        perf = perf.replace(velho, novo, 1)
    print(f"{LIVE}: bloco local removido ({removido.count(chr(10))} linhas) -> import partilhado")
    print(f"{PERF}: {len(PERF_EDITS)} edicoes (imports, router, gate, 2 decoradores)")
    print(f"{SHARED}: novo ({SHARED_SRC.count(chr(10))} linhas)")
    print(f"{TEST}: novo ({TEST_SRC.count(chr(10))} linhas)")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    _write(root, LIVE, novo_live)
    _write(root, PERF, perf)
    _write(root, SHARED, SHARED_SRC)
    _write(root, TEST, TEST_SRC)
    print("\naplicado.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.repo.resolve()
    problemas = check(root)
    if problemas:
        print("CHECK FALHOU:\n  " + "\n  ".join(problemas))
        return 1
    print(f"check ok em {root}")
    if a.check:
        return 0
    apply(root, a.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
