"""FIX 2026-09-09 -- Analise Preditiva de Crescimento passa a FUNCIONAR (decisao owner:
"eu quero que a analise funcione, nao quero tirar nada").

Sintoma (admin): modal mostra JSON cru {"success":false,"error":"Falha na execucao:
Traceback ... ModuleNotFoundError: No module named 'pyodbc'"} com caminhos do servidor.
Sintoma (viewer): "Error Generating Report / HTTP 403" sem explicacao.

Cadeia de causas (cada uma escondia a seguinte):
  1. modules/analytics/__init__.py arranca o script com o comando literal "python",
     resolvido pelo PATH da conta do servico -> Python 3.14 sem pyodbc. O servico
     corre em .venv-build (ImagePath do servico), que TEM pyodbc. -> sys.executable.
  2. scripts/filegroup_interactive_report_v5_watcherdb.py liga a WatcherDB_Intelligence
     com servidor hardcoded + Trusted_Connection=yes (identidade Windows da conta do
     servico) -> viola a Regra de Ouro #2. -> reutiliza a identidade da aplicacao
     (watcherdb.core.settings + db_identity + services.secrets.get_secret), SO SQL Auth
     (sql_monitoring); se a identidade nao for SQL explicita, falha com instrucoes.
     Carrega o .env 3-tier como fallback (o subprocess herda o ambiente do servico).
  3. watcherdb_main.py devolvia dict {"success":false,"error":<traceback>} com HTTP 200
     -> o portal via response.ok e injectava o JSON no modal como relatorio.
     -> JSONResponse 500 + mensagem saneada (ultima linha, caminhos mascarados);
     detalhe integral continua no log do servico.
  4. Gate _require_admin chamado INLINE no corpo (anti-padrao R2-01 documentado no
     proprio gate) -> Depends(...) na assinatura. Role mantida: admin (mudar para
     _require_dba e' trocar 1 nome, se o owner decidir).
  5. Portal: botao "Analise" visivel a toda a gente (a gating data-admin-gated corre
     so' no login; este botao e' renderizado depois) -> renderiza so' para admin;
     em falha le `error` OU `detail` (401/403 do FastAPI) e trata JSON com 200
     como erro (guarda por content-type).

Fora deste lote (ja' registado): i18n do modal (~30 strings PT + "Oracle" legado)
-> lote F6 com o linguista.

Uso (raiz do repo):
  py docs/context/FIX_PREDITIVA_FUNCIONA_2026-09-09_apply.py --check
  py docs/context/FIX_PREDITIVA_FUNCIONA_2026-09-09_apply.py --preview DIR
  py docs/context/FIX_PREDITIVA_FUNCIONA_2026-09-09_apply.py

Depois de aplicar:
  py -m pytest tests/unit/test_predictive_report_hardening_20260909.py -q
  Restart-Service WatcherDBWebServiceV34
  Portal (admin): Space > Filegroups > "Analise" num filegroup ROWS com historico.
  Se falhar, a mensagem no modal e' a ultima linha do erro; o traceback esta em
  logs/service_stderr.log ("Erro ao executar script").
Pre-requisito: .env com INTELLIGENCE_USE_WINDOWS_AUTH=false + INTELLIGENCE_SQL_USER
=sql_monitoring + INTELLIGENCE_SQL_PASSWORD (e' o estado actual do rollout 62/63).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PORTAL = ROOT / "templates" / "watcherdb_portal.html"
MAIN = ROOT / "watcherdb_main.py"
ANALYTICS = ROOT / "modules" / "analytics" / "__init__.py"
SCRIPT = ROOT / "scripts" / "filegroup_interactive_report_v5_watcherdb.py"
TEST = ROOT / "tests" / "unit" / "test_predictive_report_hardening_20260909.py"

EDITS: list[tuple[Path, str, str, int]] = []


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    EDITS.append((path, old, new, count))


# ------------------------------------------------------------ analytics --
edit(ANALYTICS,
     'import logging\n',
     'import logging\n'
     'import re as _re\n'
     '\n'
     '_WIN_PATH_RE = _re.compile(r"[A-Za-z]:\\\\[^\\s\'\\"<>|]+")\n'
     '\n'
     '\n'
     'def _sanitize_script_error(msg: str) -> str:\n'
     '    """Ultima linha util do erro do subprocess, sem caminhos do servidor.\n'
     '\n'
     '    2026-09-09: o traceback completo (C:\\\\Users\\\\<conta>\\\\...) chegava ao browser\n'
     '    dentro do modal. O detalhe integral continua no log do servico; ao\n'
     '    utilizador vai so\' a linha final (ex.: "ModuleNotFoundError: ...")."""\n'
     '    lines = [ln.strip() for ln in (msg or "").splitlines() if ln.strip()]\n'
     '    last = lines[-1] if lines else (msg or "").strip()\n'
     '    return _WIN_PATH_RE.sub("<path>", last)[:300]\n')

edit(ANALYTICS,
     '                "python",\n'
     '                str(self.forecast_script),',
     '                # 2026-09-09: era o literal "python" (PATH da conta do servico ->\n'
     '                # 3.14 sem pyodbc). O interpretador certo e\' o do proprio servico.\n'
     '                sys.executable,\n'
     '                str(self.forecast_script),')

edit(ANALYTICS,
     '                    "error": f"Falha na execução: {error_msg}",',
     '                    "error": f"Falha na execução: {_sanitize_script_error(error_msg)}",')

# --------------------------------------------------------------- script --
edit(SCRIPT,
     'import json\n',
     'import json\n'
     '\n'
     '# 2026-09-09: o script corre como subprocess do servico. Precisa da raiz do repo\n'
     '# no sys.path para reutilizar a identidade de ligacao da aplicacao (Regra de\n'
     '# Ouro #2: so\' sql_monitoring toca em BD; nunca a conta Windows do servico).\n'
     '_REPO_ROOT = Path(__file__).resolve().parent.parent\n'
     'if str(_REPO_ROOT) not in sys.path:\n'
     '    sys.path.insert(0, str(_REPO_ROOT))\n'
     '\n'
     '\n'
     'def _load_env_3tier() -> None:\n'
     '    """Carrega o .env pela mesma ordem do watcherdb_main (env var, ProgramData, raiz).\n'
     '    Nao sobrepoe variaveis ja\' herdadas do processo do servico."""\n'
     '    try:\n'
     '        from dotenv import load_dotenv\n'
     '    except ImportError:\n'
     '        return\n'
     '    candidates = []\n'
     '    wdd = os.environ.get("WATCHERDB_DATA_DIR")\n'
     '    if wdd:\n'
     '        candidates.append(Path(wdd) / ".env")\n'
     '    candidates.append(Path(r"C:\\ProgramData\\WatcherDB") / ".env")\n'
     '    candidates.append(_REPO_ROOT / ".env")\n'
     '    for c in candidates:\n'
     '        if c.exists():\n'
     '            load_dotenv(c, override=False)\n'
     '            break\n'
     '\n'
     '\n'
     'def build_intelligence_conn_str(timeout: int = 30) -> str:\n'
     '    """Connection string da WatcherDB_Intelligence com a identidade da aplicacao.\n'
     '\n'
     '    Espelha api/connection_pool.IntelligenceConnectionPool com uma diferenca\n'
     '    deliberada: este script NAO tem ramo Windows Auth. Se a identidade resolvida\n'
     '    nao for SQL Auth explicita, falha com instrucoes em vez de ligar com a conta\n'
     '    Windows do servico."""\n'
     '    _load_env_3tier()\n'
     '    from watcherdb.core.settings import settings\n'
     '    from watcherdb.core.db_identity import resolve, SQL\n'
     '    from services.secrets import get_secret\n'
     '\n'
     '    identity = resolve()\n'
     '    if identity.mode != SQL:\n'
     '        raise RuntimeError(\n'
     '            "Identidade de ligacao nao e\' SQL Auth explicita "\n'
     '            f"({identity.mode}: {identity.source}). Define INTELLIGENCE_USE_WINDOWS_AUTH=false, "\n'
     '            "INTELLIGENCE_SQL_USER=sql_monitoring e INTELLIGENCE_SQL_PASSWORD no .env."\n'
     '        )\n'
     '    password = get_secret("INTELLIGENCE_SQL_PASSWORD", "")\n'
     '    if not password:\n'
     '        raise RuntimeError("INTELLIGENCE_SQL_PASSWORD ausente ou nao desencriptavel neste contexto.")\n'
     '    return (\n'
     '        f"DRIVER={{{settings.odbc_driver}}};"\n'
     '        f"SERVER={settings.intelligence_server};"\n'
     '        f"DATABASE={settings.intelligence_database};"\n'
     '        f"UID={settings.intelligence_sql_user};"\n'
     '        f"PWD={password};"\n'
     '        f"Connection Timeout={timeout};"\n'
     '    )\n')

edit(SCRIPT,
     '        # WatcherDB Intelligence connection\n'
     '        self.watcherdb_server = "SQLHDSTST505\\\\I01"\n'
     '        self.watcherdb_database = "WatcherDB_Intelligence"\n',
     '        # WatcherDB Intelligence connection: servidor/BD/identidade vem das\n'
     '        # settings da aplicacao (.env), nao hardcoded (2026-09-09).\n'
     '        _load_env_3tier()\n'
     '        from watcherdb.core.settings import settings as _settings\n'
     '        self.watcherdb_server = _settings.intelligence_server\n'
     '        self.watcherdb_database = _settings.intelligence_database\n')

edit(SCRIPT,
     "            conn_str = (\n"
     "                f'DRIVER={{ODBC Driver 17 for SQL Server}};'\n"
     "                f'SERVER={self.watcherdb_server};'\n"
     "                f'DATABASE={self.watcherdb_database};'\n"
     "                f'Trusted_Connection=yes;'\n"
     "                f'Connection Timeout={timeout};'\n"
     "            )\n"
     "            return pyodbc.connect(conn_str)\n",
     "            # 2026-09-09: identidade da aplicacao (sql_monitoring), nunca a conta\n"
     "            # Windows do servico -- ver build_intelligence_conn_str.\n"
     "            return pyodbc.connect(build_intelligence_conn_str(timeout))\n")

# ----------------------------------------------------------------- main --
edit(MAIN,
     'from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request, Body\n',
     'from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request, Body, Depends\n')

edit(MAIN,
     'from api.routers.auth_compat import (\n'
     '    _get_token_from_request as _auth_get_token,\n'
     '    _require_auth as _auth_require,\n'
     '    _token_blacklist as _auth_blacklist,\n'
     ')\n',
     'from api.routers.auth_compat import (\n'
     '    _get_token_from_request as _auth_get_token,\n'
     '    _require_auth as _auth_require,\n'
     '    _require_admin as _auth_require_admin,  # 2026-09-09: Depends() do relatorio preditivo\n'
     '    _token_blacklist as _auth_blacklist,\n'
     ')\n')

edit(MAIN,
     'async def generate_predictive_report(http_request: Request, request: PredictiveReportRequest):\n',
     'async def generate_predictive_report(\n'
     '    http_request: Request,\n'
     '    request: PredictiveReportRequest,\n'
     '    _user: dict = Depends(_auth_require_admin),  # 2026-09-09: gate na assinatura (R2-01)\n'
     '):\n')

edit(MAIN,
     '    from api.routers.auth_compat import _require_admin\n'
     '    await _require_admin(http_request)\n'
     '    try:\n'
     '        logger.info(f"🔮 Gerando análise preditiva:',
     '    try:\n'
     '        logger.info(f"🔮 Gerando análise preditiva:')

edit(MAIN,
     '            else:\n'
     '                return {\n'
     '                    "success": False,\n'
     '                    "error": result["error"]\n'
     '                }\n',
     '            else:\n'
     '                # 2026-09-09: era dict com HTTP 200 -> o portal via response.ok e\n'
     '                # injectava o JSON (com traceback e caminhos do servidor) no modal\n'
     '                # como relatorio. 500 + mensagem ja\' saneada pelo analisador; o\n'
     '                # detalhe integral fica no log do servico.\n'
     '                return JSONResponse(status_code=500, content={\n'
     '                    "success": False,\n'
     '                    "error": result["error"]\n'
     '                })\n')

# --------------------------------------------------------------- portal --
edit(PORTAL,
     "${fg.filegroup_type === 'ROWS' ?",
     "${fg.filegroup_type === 'ROWS' && (window._currentUser && window._currentUser.role === 'admin') ?")

edit(PORTAL,
     "                if (!response.ok) {\n"
     "                    const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));\n"
     "                    const errorMessage = errorData.error || `HTTP ${response.status}`;\n",
     "                // 2026-09-09: o backend devolve JSON (nao HTML) em qualquer falha; sem este\n"
     "                // guarda um corpo {\"success\":false,...} com 200 era injectado no modal como\n"
     "                // relatorio. 401/403 do FastAPI vem em `detail`, nao em `error`.\n"
     "                const _ctype = (response.headers.get('content-type') || '').toLowerCase();\n"
     "                if (!response.ok || _ctype.includes('application/json')) {\n"
     "                    const errorData = await response.json().catch(() => ({}));\n"
     "                    const errorMessage = errorData.error || errorData.detail || `HTTP ${response.status}`;\n")

# ----------------------------------------------------------------- test --
TEST_SRC = '''"""
2026-09-09 -- Analise Preditiva de Crescimento: guardas estaticas do lote
"a analise tem de funcionar" (owner). Sem BD; le os ficheiros.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8")
ANALYTICS = (ROOT / "modules" / "analytics" / "__init__.py").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts" / "filegroup_interactive_report_v5_watcherdb.py").read_text(encoding="utf-8")


def test_script_never_uses_windows_identity():
    """Regra de Ouro #2: o script do relatorio liga como sql_monitoring."""
    assert "Trusted_Connection=yes" not in SCRIPT
    assert "Integrated Security" not in SCRIPT
    assert "build_intelligence_conn_str" in SCRIPT
    assert 'self.watcherdb_server = "SQLHDSTST505' not in SCRIPT


def test_analyzer_uses_service_interpreter_and_sanitizes():
    assert '"python",' not in ANALYTICS
    assert "sys.executable," in ANALYTICS
    assert "_sanitize_script_error(error_msg)" in ANALYTICS


def test_sanitizer_masks_paths_and_keeps_last_line():
    import importlib.util
    spec = importlib.util.spec_from_file_location("wdb_analytics", ROOT / "modules" / "analytics" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tb = ('Traceback (most recent call last):\\n  File "C:\\\\Users\\\\conta\\\\x.py", line 11, in <module>\\n'
          '    import pyodbc\\nModuleNotFoundError: No module named \\'pyodbc\\'')
    out = mod._sanitize_script_error(tb)
    assert out == "ModuleNotFoundError: No module named 'pyodbc'"
    assert mod._sanitize_script_error('erro em C:\\\\a\\\\b.py') == "erro em <path>"


def test_endpoint_gate_is_dependency_and_failure_is_500():
    assert "_user: dict = Depends(_auth_require_admin)" in MAIN
    assert "await _require_admin(http_request)" not in MAIN.split("generate_predictive_report")[1].split("@app.")[0]
    assert "return JSONResponse(status_code=500, content={" in MAIN


def test_portal_button_admin_only_and_json_guard():
    assert "window._currentUser.role === 'admin') ?" in PORTAL
    assert "_ctype.includes('application/json')" in PORTAL
    assert "errorData.error || errorData.detail ||" in PORTAL
'''


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    preview_dir = None
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv):
            print("--preview precisa de DIR")
            return 2
        preview_dir = Path(argv[i + 1]).resolve()

    contents: dict[Path, str] = {}
    eols: dict[Path, str] = {}
    for p in {e[0] for e in EDITS}:
        if not p.exists():
            print(f"[ABORT] nao existe: {p}")
            return 1
        raw = p.read_bytes().decode("utf-8")
        contents[p] = raw
        eols[p] = "\r\n" if "\r\n" in raw else "\n"

    problems = applied = skipped = 0
    for path, old, new, count in EDITS:
        text = contents[path]
        old = old.replace("\n", eols[path])
        new = new.replace("\n", eols[path])
        if new in text and old not in text:
            skipped += 1
            print(f"[skip] ja aplicado: {path.name}: {old[:60]!r}")
            continue
        n = text.count(old)
        if n != count:
            problems += 1
            print(f"[ABORT] {path.name}: esperado {count}x, encontrado {n}x: {old[:90]!r}")
            continue
        contents[path] = text.replace(old, new)
        applied += 1
        print(f"[ok] {path.name}: {count}x {old[:60]!r}")

    if problems:
        print(f"\n{problems} anchor(s) falharam -- NADA escrito.")
        return 1

    new_files = {TEST: TEST_SRC}
    if check_only:
        print(f"\n--check OK: {applied} edicoes aplicaveis, {skipped} ja aplicadas; "
              f"{len(new_files)} ficheiro(s) novo(s). Nada escrito.")
        return 0

    target_root = preview_dir if preview_dir is not None else ROOT
    for path, text in contents.items():
        out = target_root / path.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8"))
        print(f"[write] {out.relative_to(target_root)}")
    for path, src in new_files.items():
        out = target_root / path.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src.encode("utf-8"))
        print(f"[new]   {out.relative_to(target_root)}")

    if preview_dir is not None:
        print(f"\n--preview OK: copias em {preview_dir}. Repo intacto.")
    else:
        print(f"\nAplicado: {applied} edicoes ({skipped} ja estavam) + {len(new_files)} novo(s). Corre agora:\n"
              "  py -m pytest tests/unit/test_predictive_report_hardening_20260909.py -q\n"
              "  Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
