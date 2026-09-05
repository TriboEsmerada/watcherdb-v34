"""LOTE CSRF+COOKIE (decisao owner 2026-09-05, opcao a) - PASSO 1: middleware same-origin global.

Contexto (fonte + runtime em 8434, 05/09): o login nunca emite o cookie access_token porque
auth_compat.py:330 testa result.get("token") e o servico devolve "access_token". Ao corrigir a
chave (PASSO 2) o cookie volta e o CSRF same-site passa a ser real em 22 endpoints de escrita
sem require_same_origin e sem corpo Pydantic obrigatorio. Consenso orquestrador +
watcherdb-security-auditor: um middleware global com a MESMA politica de
watcherdb/core/same_origin.py (Origin ausente passa; Origin fora de {scheme://host} U CORS
allow_origins -> 403), registado ANTES do cookie voltar, em commit separado.

O que este script faz (idempotente; aborta se algum padrao nao bater):
  1. watcherdb/core/same_origin.py: acrescenta a classe SameOriginMiddleware (reusa
     _METODOS_COM_EFEITO, _normalizar, origens_aceites). BaseHTTPMiddleware so' ve scope http,
     logo WebSockets nao sao afectados.
  2. watcherdb_main.py: regista app.add_middleware(SameOriginMiddleware) logo a seguir ao
     AuthEnforcementMiddleware (ultimo add = mais exterior => a origem e' verificada ANTES da
     autenticacao; pedido cross-origin nem chega a validar token).
  3. tests/unit/test_same_origin_middleware.py: gate permanente (app minima + middleware;
     e um teste que confirma o registo em watcherdb_main.app).

Assuncao documentada (security-auditor): a 8434 termina TLS directamente (verificado 05/09, sem
proxy). Se algum dia houver reverse proxy a terminar TLS, request.url.scheme passa a "http" e o
Origin do browser "https://..." => 403 falso em toda a escrita. Nesse dia: ProxyHeadersMiddleware
com trusted_hosts RESTRITO aos IPs do proxy (nunca "*"), registado antes deste.

Uso (raiz do repo):  py docs/context/LOTE_CSRF_PASSO1_middleware_apply.py
Depois:              py -m pytest tests/unit/test_same_origin_middleware.py -q --no-cov
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAME_ORIGIN = ROOT / "watcherdb" / "core" / "same_origin.py"
MAIN = ROOT / "watcherdb_main.py"
TEST = ROOT / "tests" / "unit" / "test_same_origin_middleware.py"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


# --- 1. same_origin.py -----------------------------------------------------------------
MIDDLEWARE_SRC = '''

class SameOriginMiddleware(BaseHTTPMiddleware):
    """Aplica a politica de `require_same_origin` a TODO pedido com efeito (global).

    Porque middleware e nao Depends em cada endpoint: em 2026-09-05 havia 48 endpoints de
    escrita e so' 3 com o Depends -- um controlo que depende de cada autor se lembrar
    apodrece no primeiro router novo. O middleware e' um unico ponto de verdade (e de
    auditoria) e cobre endpoints futuros. Os Depends existentes ficam; sao redundantes e
    inofensivos.

    So' ve scope "http" (BaseHTTPMiddleware): WebSockets nao passam aqui. Metodos seguros e
    pedidos sem `Origin` passam -- ver docstring do modulo para a justificacao.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in _METODOS_COM_EFEITO:
            origem = _normalizar(request.headers.get("origin", ""))
            if origem and origem not in origens_aceites(request):
                logger.warning(
                    "Escrita recusada por origem cruzada (middleware): %s %s (Origin=%s)",
                    request.method,
                    request.url.path,
                    origem,
                )
                return JSONResponse({"detail": "Origem nao permitida"}, status_code=403)
        return await call_next(request)
'''

src = SAME_ORIGIN.read_text(encoding="utf-8")
if "class SameOriginMiddleware" in src:
    print("1. same_origin.py: middleware ja existe (skip)")
else:
    old_imports = "from fastapi import HTTPException, Request\n"
    if src.count(old_imports) != 1:
        abort("same_origin.py: linha de import da fastapi nao encontrada")
    new_imports = (
        "from fastapi import HTTPException, Request\n"
        "from fastapi.responses import JSONResponse\n"
        "from starlette.middleware.base import BaseHTTPMiddleware\n"
    )
    src = src.replace(old_imports, new_imports)
    if not src.endswith("\n"):
        src += "\n"
    src += MIDDLEWARE_SRC
    SAME_ORIGIN.write_text(src, encoding="utf-8")
    print("1. same_origin.py: SameOriginMiddleware acrescentado")

# --- 2. watcherdb_main.py --------------------------------------------------------------
main = MAIN.read_text(encoding="utf-8")
anchor = "app.add_middleware(AuthEnforcementMiddleware)\n"
if "SameOriginMiddleware" in main:
    print("2. watcherdb_main.py: registo ja existe (skip)")
else:
    if main.count(anchor) != 1:
        abort("watcherdb_main.py: anchor 'app.add_middleware(AuthEnforcementMiddleware)' nao e' unico")
    registration = (
        anchor
        + "\n"
        + "# CSRF same-site (lote 2026-09-05): Origin presente e fora de {scheme://host} U CORS\n"
        + "# allow_origins => 403 em POST/PUT/PATCH/DELETE. Registado DEPOIS do AuthEnforcement =>\n"
        + "# corre ANTES dele (ultimo add_middleware e' o mais exterior). Politica e justificacao\n"
        + "# em watcherdb/core/same_origin.py.\n"
        + "from watcherdb.core.same_origin import SameOriginMiddleware\n"
        + "app.add_middleware(SameOriginMiddleware)\n"
    )
    main = main.replace(anchor, registration)
    MAIN.write_text(main, encoding="utf-8")
    print("2. watcherdb_main.py: SameOriginMiddleware registado")

# --- 3. teste --------------------------------------------------------------------------
TEST_SRC = '''"""Gate permanente do CSRF same-site (lote 2026-09-05).

Politica (watcherdb/core/same_origin.py): em POST/PUT/PATCH/DELETE, `Origin` presente e fora de
{scheme://host} U CORS allow_origins => 403. Origin ausente passa (clientes nao-browser).
Metodos seguros passam sempre.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from watcherdb.core import same_origin
from watcherdb.core.same_origin import SameOriginMiddleware


@pytest.fixture
def client(monkeypatch):
    # CORS allowlist controlada pelo teste (nao depende de config/config.yaml)
    import watcherdb.core.cors as cors

    monkeypatch.setattr(
        cors, "get_cors_config", lambda: {"allow_origins": ["https://portal-aliado.example"]}
    )
    app = FastAPI()
    app.add_middleware(SameOriginMiddleware)

    @app.post("/escrita")
    async def escrita():
        return {"ok": True}

    @app.delete("/escrita")
    async def apaga():
        return {"ok": True}

    @app.get("/leitura")
    async def leitura():
        return {"ok": True}

    return TestClient(app)  # Host: testserver, scheme http


def test_origem_cruzada_em_post_da_403(client):
    r = client.post("/escrita", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Origem nao permitida"


def test_origem_cruzada_em_delete_da_403(client):
    r = client.delete("/escrita", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code == 403


def test_origem_propria_passa(client):
    r = client.post("/escrita", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_origem_propria_case_e_barra_final_passa(client):
    r = client.post("/escrita", headers={"Origin": "HTTP://TestServer/"})
    assert r.status_code == 200


def test_origem_na_allowlist_cors_passa(client):
    r = client.post("/escrita", headers={"Origin": "https://portal-aliado.example"})
    assert r.status_code == 200


def test_sem_origin_passa(client):
    # curl / collectors / k6: sem browser nao ha cookie anexado => sem vector
    r = client.post("/escrita")
    assert r.status_code == 200


def test_origin_null_da_403(client):
    # iframe sandboxed / redirects opacos enviam "null" -- nao e' a nossa origem
    r = client.post("/escrita", headers={"Origin": "null"})
    assert r.status_code == 403


def test_get_com_origem_cruzada_passa(client):
    r = client.get("/leitura", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code == 200


def test_options_com_origem_cruzada_nao_da_403(client):
    r = client.options("/escrita", headers={"Origin": "https://vizinho.tap.pt"})
    assert r.status_code != 403


def test_politica_do_middleware_e_a_mesma_do_depends():
    # O middleware tem de reutilizar as primitivas do modulo, nao reimplementar a politica.
    import inspect

    src = inspect.getsource(SameOriginMiddleware)
    assert "origens_aceites(" in src and "_METODOS_COM_EFEITO" in src and "_normalizar(" in src
    assert same_origin.require_same_origin is not None


def test_middleware_registado_na_app_real():
    try:
        import watcherdb_main
    except Exception as e:  # pragma: no cover - ambiente sem dependencias completas
        pytest.skip(f"watcherdb_main nao carregavel: {e}")
    classes = [m.cls for m in watcherdb_main.app.user_middleware]
    assert SameOriginMiddleware in classes, "SameOriginMiddleware nao esta registado em watcherdb_main.app"
    # Tem de ser mais exterior que o AuthEnforcement (add_middleware: ultimo = mais exterior,
    # e user_middleware guarda por ordem de add => o mais exterior fica no indice 0).
    names = [c.__name__ for c in classes]
    assert names.index("SameOriginMiddleware") < names.index("AuthEnforcementMiddleware")
'''

if TEST.exists():
    print("3. teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("3. tests/unit/test_same_origin_middleware.py criado")

print("\nPASSO 1 concluido. Correr:  py -m pytest tests/unit/test_same_origin_middleware.py -q --no-cov")
print('Depois: py -c "import ast;ast.parse(open(\'watcherdb_main.py\',encoding=\'utf-8\').read());print(\'main OK\')"')
