"""TestGrapete TG-1 - PASSO 1: escreve o runner do council, o script noturno e o
.gitignore das evidencias pesadas. Idempotente: nao reescreve ficheiros que ja
existam com o marcador TG-1 (aborta se existirem SEM o marcador).

Uso (raiz do repo):  py docs/context/TG1_PASSO1_apply.py
Depois:              pwsh docs/context/TG1_PASSO2_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARK = "TESTGRAPETE TG-1"

TEST_PATH = ROOT / "tests" / "e2e" / "test_smoke_modules_e2e.py"
NIGHTLY_PATH = ROOT / "scripts" / "qa" / "nightly_testgrapete.ps1"
GITIGNORE = ROOT / ".gitignore"

TEST_SRC = r'''"""TESTGRAPETE TG-1 - smoke dos modulos do portal, por perfil (council: afirma).

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
    if os.getenv("WATCHERDB_QA_ROLE", "admin").lower() == perfil:
        u, p = os.getenv("WATCHERDB_QA_USER", ""), os.getenv("WATCHERDB_QA_PASS", "")
        if u and p:
            return u, p
    return None


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


def _autentica(page, base_url: str, perfil: str) -> str:
    user, pw = _creds(perfil)
    resposta = page.context.request.post(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": user, "password": pw}),
        headers={"Content-Type": "application/json"},
    )
    assert resposta.ok, f"login de {user} ({perfil}) falhou com {resposta.status}"
    corpo = resposta.json()
    token = corpo.get("access_token") or corpo.get("token")
    assert token, f"login devolveu 200 mas sem token: {sorted(corpo)}"
    page.add_init_script(
        "(() => { try { localStorage.setItem('watcherdb_token', %s); } catch (e) {} })()"
        % json.dumps(token)
    )
    page.goto(f"{base_url}{PORTAL}", wait_until="load", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=30000)
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
            if (!s) s = allServers.find(x => /tst/i.test(x.environment || ''));
            if (!s) s = allServers[0];
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
        assert servidor, "sidebar sem servidores - nada a testar"

        page.evaluate("(sid) => { const s = allServers.find(x => x.server_id === sid); selectServer(s); }",
                      servidor["server_id"])
        page.wait_for_timeout(500)
        t0 = time.time()
        tab_id = page.evaluate(
            "([sid, tab]) => { showTab(tab); return generateTabId(sid, tab); }", [servidor["server_id"], tab]
        )
        warn = []
        try:
            page.wait_for_function(
                """(tid) => {
                    const el = document.getElementById('tab-content-' + tid);
                    if (!el) return false;
                    if (el.querySelector('.fa-spin')) return false;
                    return (el.innerText || '').trim().length > 0;
                }""",
                tab_id, timeout=TAB_TIMEOUT_MS,
            )
        except Exception:
            warn.append(f"aba {tab} nao terminou em {TAB_TIMEOUT_MS} ms (instancia lenta ou sem resposta)")
        load_ms = int((time.time() - t0) * 1000)
        conteudo = page.evaluate(
            "(tid) => { const el = document.getElementById('tab-content-' + tid); return el ? el.innerText.slice(0, 400) : ''; }",
            tab_id,
        )
        caso = {
            "caso": f"tab_{tab}", "perfil": perfil, "user": user, "server": servidor,
            "tab_id": tab_id, "load_ms": load_ms, "dom_nodes": _dom_nodes(page),
            "pageerrors": col.pageerrors, "console_errors": col.erros_de_consola(),
            "http5xx": col.http5xx, "warn": warn, "amostra": conteudo,
        }
        _grava(caso)
        assert not col.pageerrors, f"[{perfil}/{tab}] excepcao JS:\n  - " + "\n  - ".join(col.pageerrors[:5])
        assert not col.http5xx, f"[{perfil}/{tab}] respostas 5xx:\n  - " + "\n  - ".join(col.http5xx[:5])
        assert not caso["console_errors"], f"[{perfil}/{tab}] erros de consola:\n  - " + "\n  - ".join(caso["console_errors"][:10])
        assert tab_id and page.evaluate("(tid) => !!document.getElementById('tab-content-' + tid)", tab_id), \
            f"[{perfil}/{tab}] a aba nao foi criada (showTab sem servidor seleccionado?)"
'''

NIGHTLY_SRC = r'''# TESTGRAPETE TG-1 - corrida noturna: council (afirma) e depois qa-externo (confere).
# PS7. Corre no host da 8434. Credenciais em .env.qa (fora do git) ou no ambiente.
#
# Uso manual:   pwsh scripts/qa/nightly_testgrapete.ps1
# Agendado:     ver docs/context/PLANO_TESTGRAPETE_2026-09-09.md (TG-2)
#
# .env.qa (raiz do repo, ignorado pelo git), uma variavel por linha:
#   WATCHERDB_BASE_URL=https://localhost:8434
#   WATCHERDB_QA_VIEWER_USER=qa_viewer
#   WATCHERDB_QA_VIEWER_PASS=...
#   WATCHERDB_QA_DBA_USER=qa_dba
#   WATCHERDB_QA_DBA_PASS=...
#   WATCHERDB_QA_ADMIN_USER=qa_admin
#   WATCHERDB_QA_ADMIN_PASS=...
#   WATCHERDB_QA_SERVER=<nome ou server_id de um TST>

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

$envFile = Join-Path $repo '.env.qa'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process')
        }
    }
}
if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }

$dia = Get-Date -Format 'yyyy-MM-dd'
$bundle = Join-Path $repo "docs\qa\externo\$dia"
$council = Join-Path $bundle 'council'
$externo = Join-Path $bundle 'externo'
New-Item -ItemType Directory -Force -Path $council, $externo, (Join-Path $council 'cases') | Out-Null
$env:WATCHERDB_QA_BUNDLE = $council

$inicio = Get-Date
$head = (git rev-parse --short HEAD).Trim()

# ---- 1) Council: runner Playwright ----
$junit = Join-Path $council 'junit.xml'
& py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -q `
    --screenshot only-on-failure --tracing retain-on-failure --output (Join-Path $council 'playwright') `
    --junitxml $junit 2>&1 | Tee-Object -FilePath (Join-Path $council 'pytest.log') | Select-Object -Last 15
$councilExit = $LASTEXITCODE

# ---- 2) qa-externo: scripts proprios, intocados, cada um no seu log ----
$extResults = @()
Get-ChildItem scripts/qa/runtime -Filter 'qa_ext_*.py' | Sort-Object Name | ForEach-Object {
    $log = Join-Path $externo ($_.BaseName + '.log')
    & py $_.FullName 2>&1 | Out-File -FilePath $log -Encoding utf8
    $extResults += [pscustomobject]@{ script = $_.Name; exit = $LASTEXITCODE }
}

# ---- 3) Sumario ----
$cases = Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue
$falhas = 0; $warns = 0
foreach ($c in $cases) {
    $j = Get-Content $c.FullName -Raw | ConvertFrom-Json
    if ($j.pageerrors.Count -or $j.console_errors.Count -or $j.http5xx.Count) { $falhas++ }
    if ($j.warn.Count) { $warns++ }
}
$dur = [int]((Get-Date) - $inicio).TotalSeconds
$linhas = @(
    "# TestGrapete $dia (HEAD $head, $($env:WATCHERDB_BASE_URL))",
    "",
    "| Metade | Resultado |",
    "|---|---|",
    "| Council | pytest exit $councilExit; $($cases.Count) casos; $falhas com erro; $warns com aviso de tempo |",
    "| qa-externo | $($extResults.Count) scripts; $(@($extResults | Where-Object exit -ne 0).Count) com exit != 0 |",
    "| Duracao | $dur s |",
    "",
    "## qa-externo por script",
    ""
) + ($extResults | ForEach-Object { "- $($_.script): exit $($_.exit)" })
$linhas | Set-Content -Path (Join-Path $bundle 'SUMMARY.md') -Encoding utf8

$logLine = "| $dia | $head | council exit $councilExit ($($cases.Count) casos, $falhas erro, $warns aviso) | externo $(@($extResults | Where-Object exit -ne 0).Count)/$($extResults.Count) com erro | $dur s |"
$nightly = Join-Path $repo 'docs\qa\externo\NIGHTLY_LOG.md'
if (-not (Test-Path $nightly)) {
    "# TestGrapete - corridas noturnas`n`n| Dia | HEAD | Council | qa-externo | Duracao |`n|---|---|---|---|---|" | Set-Content $nightly -Encoding utf8
}
Add-Content -Path $nightly -Value $logLine -Encoding utf8

# ---- 4) Painel (TG-1b): resultados do externo em JSON + index.html/board.html ----
$extResults | ConvertTo-Json -AsArray | Set-Content -Path (Join-Path $externo 'results.json') -Encoding utf8
if (Test-Path scripts/qa/testgrapete_board.py) { & py scripts/qa/testgrapete_board.py 2>&1 | Select-Object -Last 2 }

Write-Host $logLine
exit $councilExit
'''

GITIGNORE_LINES = [
    "# TESTGRAPETE TG-1: evidencias pesadas (screenshots/traces) e credenciais de QA",
    "docs/qa/externo/*/council/playwright/",
    ".env.qa",
]


def _write_once(path: Path, src: str, label: str) -> None:
    if path.exists():
        if MARK in path.read_text(encoding="utf-8", errors="replace"):
            print(f"Ja existe (marcador TG-1): {label}")
            return
        sys.exit(f"ABORT: {path.relative_to(ROOT)} existe SEM o marcador TG-1. Nao sobrescrevo.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src, encoding="utf-8", newline="\n")
    print(f"OK: {label}")


def main() -> None:
    compile(TEST_SRC, str(TEST_PATH), "exec")  # sintaxe antes de escrever
    _write_once(TEST_PATH, TEST_SRC, "tests/e2e/test_smoke_modules_e2e.py")
    _write_once(NIGHTLY_PATH, NIGHTLY_SRC, "scripts/qa/nightly_testgrapete.ps1")

    gi = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.exists() else ""
    faltam = [ln for ln in GITIGNORE_LINES if ln not in gi]
    if faltam:
        with GITIGNORE.open("a", encoding="utf-8", newline="\n") as f:
            if gi and not gi.endswith("\n"):
                f.write("\n")
            f.write("\n".join(faltam) + "\n")
        print(f"OK: .gitignore (+{len(faltam)} linhas)")
    else:
        print("Ja existe: .gitignore")
    print("Proximo: pwsh docs/context/TG1_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
