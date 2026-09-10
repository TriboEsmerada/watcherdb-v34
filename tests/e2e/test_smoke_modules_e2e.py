"""TESTGRAPETE TG-1 - smoke dos modulos do portal, por perfil (council: afirma).

O QUE MEDE (invariantes, nunca valores literais):
  - 0 excepcoes JS por apanhar (pageerror) ao carregar o dashboard e cada aba
  - 0 erros de consola fora do ruido conhecido
  - 0 respostas HTTP >= 500 vindas do proprio servico
  - a aba responde: o contentor `#tab-content-<id>` existe e deixou de ter
    spinners; se nao responder em WATCHERDB_QA_TAB_TIMEOUT_MS regista WARN no
    bundle (PRD sem replica: uma instancia lenta nao e' defeito do portal)

EVIDENCIAS: um JSON por caso em $WATCHERDB_QA_BUNDLE/council/cases/ (default
docs/qa/externo/<hoje>/council). Screenshot e trace so' em falha, pelas flags do
pytest-playwright no script noturno (--screenshot only-on-failure
--tracing retain-on-failure --output ...).

PERFIS: viewer / dba / admin. Credenciais por perfil em
  WATCHERDB_QA_VIEWER_USER / WATCHERDB_QA_VIEWER_PASS
  WATCHERDB_QA_DBA_USER    / WATCHERDB_QA_DBA_PASS
  WATCHERDB_QA_ADMIN_USER  / WATCHERDB_QA_ADMIN_PASS
Fallback: WATCHERDB_QA_USER/PASS/ROLE (padrao das jornadas) serve o perfil
indicado em ROLE. Perfil sem credenciais => os casos desse perfil SALTAM com
motivo, nunca medem "nao autenticado" e chamam-lhe defeito (licao de 19/08).

SERVIDOR: WATCHERDB_QA_SERVER (nome ou server_id, parcial, sem distincao de
maiusculas). Sem ele: primeiro servidor com environment TST; senao o primeiro.

CORRER A MAO (servico 8434 vivo):
  $env:WATCHERDB_BASE_URL = "https://localhost:8434"
  py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -v
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

PORTAL = "/watcherdb"
TABS = [
    "overview", "performance", "alwayson", "backup", "space", "disk", "encrypted",
    "cpu", "memory", "services", "log", "sessions", "security", "users", "jobs",
    "sql-diagnostics",
]
PERFIS = ("viewer", "dba", "admin")

RUIDO_SEMPRE = ("favicon", "chrome-extension://", "ERR_INTERNET_DISCONNECTED")
TAB_TIMEOUT_MS = int(os.getenv("WATCHERDB_QA_TAB_TIMEOUT_MS", "60000"))
ROOT = Path(__file__).resolve().parents[2]


def _bundle_dir() -> Path:
    base = os.getenv("WATCHERDB_QA_BUNDLE")
    if not base:
        base = str(ROOT / "docs" / "qa" / "externo" / _dt.date.today().isoformat() / "council")
    d = Path(base) / "cases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _creds(perfil: str):
    u = os.getenv(f"WATCHERDB_QA_{perfil.upper()}_USER", "")
    p = os.getenv(f"WATCHERDB_QA_{perfil.upper()}_PASS", "")
    if u and p:
        return u, p
    # TG-1 PASSO 3: o fallback generico so' serve o perfil se WATCHERDB_QA_ROLE
    # o disser EXPLICITAMENTE (na 1.a corrida, qa_viewer caiu no perfil admin).
    if os.getenv("WATCHERDB_QA_ROLE", "").lower() == perfil:
        u, p = os.getenv("WATCHERDB_QA_USER", ""), os.getenv("WATCHERDB_QA_PASS", "")
        if u and p:
            return u, p
    return None


# TG-1 PASSO 3: /api/auth/login tem rate limit 5/minuto (auth_compat.py:324).
# Um login por perfil por sessao de pytest; o token e' reutilizado.
_TOKENS: dict[str, tuple[str, str]] = {}


def _perfil_param(perfil: str):
    if _creds(perfil) is None:
        return pytest.param(perfil, marks=pytest.mark.skip(
            reason=f"sem credenciais para o perfil {perfil} "
                   f"(WATCHERDB_QA_{perfil.upper()}_USER/PASS) - nao mede 'nao autenticado'"))
    return pytest.param(perfil, id=perfil)


class Colector:
    """Apanha pageerror, erros de consola e respostas 5xx de uma pagina."""

    def __init__(self, page, base_url: str):
        self.pageerrors: list[str] = []
        self.console: list[str] = []
        self.http5xx: list[str] = []
        self._base = base_url.rstrip("/")
        page.on("pageerror", lambda e: self.pageerrors.append(str(e)))
        page.on("console", lambda m: self.console.append(m.text) if m.type == "error" else None)
        page.on("response", self._on_response)

    def _on_response(self, r):
        try:
            if r.status >= 500 and r.url.startswith(self._base):
                self.http5xx.append(f"{r.status} {r.request.method} {r.url}")
        except Exception:  # pragma: no cover - defensivo
            pass

    def erros_de_consola(self, extra_ruido=()):
        tolerado = RUIDO_SEMPRE + tuple(extra_ruido)
        return [e for e in self.console if not any(r.lower() in e.lower() for r in tolerado)]


_LOGIN_FALHOU: dict[str, str] = {}


def _token(page, base_url: str, perfil: str) -> tuple[str, str]:
    if perfil in _TOKENS:
        return _TOKENS[perfil]
    # TG-1 PASSO 8: um login falhado por perfil chega. Repetir 17x com a password
    # errada bloqueia a conta (MAX_FAILED_ATTEMPTS=5, 15 min) e mascara a causa.
    if perfil in _LOGIN_FALHOU:
        pytest.fail(_LOGIN_FALHOU[perfil] + " (nao repetido: evita bloquear a conta)")
    user, pw = _creds(perfil)
    resposta = page.context.request.post(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": user, "password": pw}),
        headers={"Content-Type": "application/json"},
    )
    if resposta.status == 429:
        # TG-1c PASSO 5: uma espera e uma nova tentativa antes de desistir (corridas seguidas batem no 5/min).
        time.sleep(61)
        resposta = page.context.request.post(
            f"{base_url}/api/auth/login",
            data=json.dumps({"username": user, "password": pw}),
            headers={"Content-Type": "application/json"},
        )
    if resposta.status == 429:
        _LOGIN_FALHOU[perfil] = f"login de {user} ({perfil}) devolveu 429 duas vezes: rate limit 5/min esgotado"
        pytest.fail(_LOGIN_FALHOU[perfil] + " (outra corrida em paralelo?)")
    if not resposta.ok:
        _LOGIN_FALHOU[perfil] = (f"login de {user} ({perfil}) falhou com {resposta.status}: "
                                 "password errada, conta desactivada ou bloqueada (15 min apos 5 falhas)")
        pytest.fail(_LOGIN_FALHOU[perfil])
    corpo = resposta.json()
    token = corpo.get("access_token") or corpo.get("token")
    assert token, f"login devolveu 200 mas sem token: {sorted(corpo)}"
    role = str(((corpo.get("user") or {}).get("role")) or corpo.get("role") or "").lower()
    if role and role != perfil:
        pytest.fail(f"conta {user} tem role '{role}' mas esta' configurada para o perfil "
                    f"'{perfil}': corrige WATCHERDB_QA_{perfil.upper()}_USER/PASS em .env.qa")
    _TOKENS[perfil] = (user, token)
    return _TOKENS[perfil]


def _autentica(page, base_url: str, perfil: str) -> str:
    user, token = _token(page, base_url, perfil)
    page.add_init_script(
        "(() => { try { localStorage.setItem('watcherdb_token', %s); } catch (e) {} })()"
        % json.dumps(token)
    )
    page.goto(f"{base_url}{PORTAL}", wait_until="load", timeout=30000)
    # TG-1c PASSO 7: sem "networkidle" - o portal faz polling permanente e nunca fica idle (timeouts ao acaso).
    page.wait_for_function(
        "() => document.body && !/Carregando KPIs|Loading KPIs/i.test(document.body.innerText)",
        timeout=60000,
    )
    return user


def _escolhe_servidor(page):
    alvo = os.getenv("WATCHERDB_QA_SERVER", "")
    page.wait_for_function("() => Array.isArray(allServers) && allServers.length > 0", timeout=60000)
    return page.evaluate(
        """(alvo) => {
            const q = (alvo || '').toLowerCase();
            let s = null;
            if (q) s = allServers.find(x => (x.name || '').toLowerCase().includes(q)
                                        || String(x.server_id || '').toLowerCase().includes(q));
            // TG-1 PASSO 3: environment no inventario e' 'production'/'quality'/'test'.
            // Sem alvo explicito, NUNCA producao: test, depois quality, senao nada.
            if (!s) s = allServers.find(x => /^(test|tst)/i.test(x.environment || ''));
            if (!s) s = allServers.find(x => /^(quality|qlt)/i.test(x.environment || ''));
            return s ? { name: s.name, server_id: s.server_id, environment: s.environment || '' } : null;
        }""",
        alvo,
    )


def _grava(caso: dict):
    caso["ts"] = _dt.datetime.now().isoformat(timespec="seconds")
    nome = re.sub(r"[^a-z0-9_-]+", "_", f"{caso['perfil']}_{caso['caso']}".lower())
    (_bundle_dir() / f"{nome}.json").write_text(json.dumps(caso, ensure_ascii=False, indent=2), encoding="utf-8")


def _dom_nodes(page) -> int:
    return page.evaluate("() => document.querySelectorAll('*').length")


@pytest.mark.parametrize("perfil", [_perfil_param(p) for p in PERFIS])
class TestSmokeFleet:
    def test_dashboard_carrega_limpo(self, page, base_url, perfil):
        col = Colector(page, base_url)
        t0 = time.time()
        user = _autentica(page, base_url, perfil)
        caso = {
            "caso": "fleet_dashboard", "perfil": perfil, "user": user,
            "load_ms": int((time.time() - t0) * 1000), "dom_nodes": _dom_nodes(page),
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(),
            "http5xx": col.http5xx, "warn": [],
        }
        _grava(caso)
        assert not col.pageerrors, "excepcao JS por apanhar:\n  - " + "\n  - ".join(col.pageerrors[:5])
        assert not col.http5xx, "respostas 5xx:\n  - " + "\n  - ".join(col.http5xx[:5])
        assert not caso["console_errors"], "erros de consola:\n  - " + "\n  - ".join(caso["console_errors"][:10])


@pytest.mark.parametrize("perfil", [_perfil_param(p) for p in PERFIS])
@pytest.mark.parametrize("tab", TABS)
class TestSmokeModulos:
    def test_aba_abre_sem_erros(self, page, base_url, perfil, tab):
        col = Colector(page, base_url)
        user = _autentica(page, base_url, perfil)
        servidor = _escolhe_servidor(page)
        if not servidor:
            pytest.skip("sem servidor de test/quality no inventario e sem WATCHERDB_QA_SERVER: "
                        "o smoke nao corre contra producao por omissao")

        page.evaluate("(sid) => { const s = allServers.find(x => x.server_id === sid); selectServer(s); }",
                      servidor["server_id"])
        page.wait_for_timeout(500)
        t0 = time.time()
        # TG-1 PASSO 3: generateTabId() leva timestamp; o id real e' o activeTabId
        # que activateTab() define ao criar/activar a aba.
        tab_id = page.evaluate("(tab) => { showTab(tab); return activeTabId; }", tab)
        warn = []
        try:
            page.wait_for_function(
                """(tid) => {
                    const el = document.getElementById('tab-content-' + tid);
                    if (!el) return false;
                    if (el.querySelector('.fa-spin')) return false;
                    return (el.innerText || '').trim().length > 0;
                }""",
                arg=tab_id, timeout=TAB_TIMEOUT_MS,  # TG-1 PASSO 8: `arg=` e' so' por nome
            )
        except Exception as exc:  # noqa: BLE001
            if "Timeout" in type(exc).__name__ or "imeout" in str(exc):
                warn.append(f"aba {tab} nao terminou em {TAB_TIMEOUT_MS} ms (instancia lenta ou sem resposta)")
            else:
                pytest.fail(f"[{perfil}/{tab}] erro do runner ao esperar pela aba: {type(exc).__name__}: {exc}")
        load_ms = int((time.time() - t0) * 1000)
        # TESTGRAPETE TG-1c (TC-003 do TestSprite): a aba activa e' DESTE servidor e o cabecalho diz o nome dele.
        ctx = page.evaluate(
            """() => { const t = openTabs.get(activeTabId); const h = document.getElementById('serverName');
                       return { sid: t && t.server ? t.server.server_id : null, tipo: t ? t.tabType : null,
                                header: h ? (h.innerText || '').trim() : '' }; }"""
        )
        conteudo = page.evaluate(
            "(tid) => { const el = document.getElementById('tab-content-' + tid); return el ? el.innerText.slice(0, 400) : ''; }",
            tab_id,
        )
        caso = {
            "caso": f"tab_{tab}", "perfil": perfil, "user": user, "server": servidor,
            "tab_id": tab_id, "load_ms": load_ms, "dom_nodes": _dom_nodes(page), "contexto": ctx,
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(),
            "http5xx": col.http5xx, "warn": warn, "amostra": conteudo,
        }
        _grava(caso)
        assert not col.pageerrors, f"[{perfil}/{tab}] excepcao JS:\n  - " + "\n  - ".join(col.pageerrors[:5])
        assert not col.http5xx, f"[{perfil}/{tab}] respostas 5xx:\n  - " + "\n  - ".join(col.http5xx[:5])
        assert not caso["console_errors"], f"[{perfil}/{tab}] erros de consola:\n  - " + "\n  - ".join(caso["console_errors"][:10])
        assert tab_id and page.evaluate("(tid) => !!document.getElementById('tab-content-' + tid)", tab_id), \
            f"[{perfil}/{tab}] a aba nao foi criada (activeTabId={tab_id!r}; showTab sem servidor seleccionado?)"
        assert ctx["sid"] == servidor["server_id"] and ctx["tipo"] == tab, \
            f"[{perfil}/{tab}] contexto errado: aba activa e' {ctx['tipo']!r} de {ctx['sid']!r}, esperado {tab!r} de {servidor['server_id']!r}"
        assert servidor["name"].split("\\")[0].lower() in ctx["header"].lower(), \
            f"[{perfil}/{tab}] cabecalho nao mostra o servidor escolhido: {ctx['header']!r} vs {servidor['name']!r}"
