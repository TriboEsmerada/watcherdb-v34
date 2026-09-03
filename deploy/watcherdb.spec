# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for WatcherDB V3.3 Standard Edition.

Invoked by deploy/build.py after the PyArmor Pro obfuscation pass.
The input tree is the PyArmor output (dist/WatcherDB_V3.3/) which already
contains the obfuscated .py modules plus the PyArmor runtime folder
pyarmor_runtime_011618/; PyInstaller wraps it into a onedir bundle with
all the FastAPI/pywin32 runtime dependencies resolved.

Build with:
    pyinstaller --noconfirm --clean deploy/watcherdb.spec

Output:
    dist/watcherdb/watcherdb.exe   -- the Windows service-friendly binary
    dist/watcherdb/*               -- side-by-side DLLs, templates, static
                                      assets, and pyarmor_runtime_011618
"""

from pathlib import Path

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.utils.hooks import collect_all, collect_submodules


# The spec file lives in deploy/ so PROJECT_ROOT is the repo root.
PROJECT_ROOT = Path(SPECPATH).resolve().parent
PYARMOR_OUTPUT = PROJECT_ROOT / "dist" / "WatcherDB_V3.3"
# Etapa 2 (B0-1): o entry point e o launcher SCM. watcherdb_main e
# importado lazy (so depois de o servico reportar RUNNING) — o PyInstaller
# nao ve esse import estaticamente, dai o hidden import mais abaixo.
ENTRY_POINT = PYARMOR_OUTPUT / "watcherdb_service.py"

# FastAPI + Starlette use conditional imports (anyio backends, exception
# handlers, responses). --collect-all guarantees PyInstaller ships every
# submodule and data file the runtime might walk.
_fastapi = collect_all("fastapi")
_starlette = collect_all("starlette")
_anyio = collect_all("anyio")
_uvicorn = collect_all("uvicorn")
_slowapi = collect_all("slowapi")
_pydantic = collect_all("pydantic")

# pywin32 ships a handful of helper modules that PyInstaller's default hooks
# miss when the entry point does not import them directly. Listing them as
# hidden imports forces inclusion so install-as-Service and rotating log
# handlers resolve at runtime.
PYWIN32_HIDDEN = [
    "win32timezone",
    "win32serviceutil",
    "win32service",
    "win32event",
    "servicemanager",
    "pythoncom",
    "pywintypes",
]

# SQLAlchemy dialects are imported by URL string, so PyInstaller never sees
# the literal import. The MSSQL pyodbc dialect is the only one V3.3 uses.
SQLALCHEMY_HIDDEN = [
    "sqlalchemy.dialects.mssql.pyodbc",
    "sqlalchemy.dialects.mssql",
]

# PyArmor Pro injects a native runtime (pyarmor_runtime_011618.pyd). The
# directory lives alongside the obfuscated .py files; PyInstaller sees it as
# plain data, not a Python package, so we must pin both data and imports.
PYARMOR_RUNTIME_DIR = PYARMOR_OUTPUT / "pyarmor_runtime_011618"
PYARMOR_HIDDEN = ["pyarmor_runtime_011618"] if PYARMOR_RUNTIME_DIR.exists() else []

# --- Data files shipped alongside the binary -----------------------------

DATAS = []

# Templates / static assets (resolved at runtime via _tpl()/_static()
# helpers in watcherdb_main.py).
for src_rel, dst_rel in (
    ("templates", "templates"),
    ("static", "static"),
    ("deploy/keys", "deploy/keys"),
):
    src = PROJECT_ROOT / src_rel
    if src.exists():
        DATAS.append((str(src), dst_rel))

# config/ bundled file-by-file com LISTA BRANCA (auditoria empacotamento B0-3).
#
# 2026-08-12 -- a versao anterior usava lista NEGRA de nomes exactos
# (servers.json, sql_servers.json, ...) mais um filtro de ".bak"/".backup".
# Falhou: quatro variantes de nome passaram-lhe ao lado e foram parar ao MSI
# entregue -- servers_27072026.json, servers.json.backup_pre_reencrypt,
# servers.json.backup_pre_sync e servers.json.backup_pre_description_sync_*
# (2,3 MB, ~200 instancias reais com utilizadores e passwords Fernet).
# Repara que ".bak" nem sequer e' subcadeia de ".backup" (bac != bak) e que
# "servers.json.backup_pre_X" nao TERMINA em ".backup".
#
# Lista de nomes envelhece; extensao nao. So' entra o que e' explicitamente
# seguro: configuracao declarativa, SQL e templates. Qualquer *.json vivo,
# backup ou snapshot com nome novo fica de fora por omissao.
# Runtime seeds ProgramData via watcherdb.core.paths.bootstrap_config().
_CONFIG_ALLOW_SUFFIX = {".yaml", ".yml", ".sql"}
_config_src = PROJECT_ROOT / "config"
if _config_src.exists():
    for _cf in _config_src.rglob("*"):
        if not _cf.is_file():
            continue
        _safe = (_cf.suffix.lower() in _CONFIG_ALLOW_SUFFIX
                 or _cf.name.endswith(".template"))
        if not _safe:
            continue
        _cdst = Path("config") / _cf.relative_to(_config_src).parent
        DATAS.append((str(_cf), str(_cdst)))

# PyArmor runtime is shipped as data so the obfuscated modules locate it at
# runtime via sys.path.
if PYARMOR_RUNTIME_DIR.exists():
    DATAS.append((str(PYARMOR_RUNTIME_DIR), "pyarmor_runtime_011618"))

# --- Hidden imports assembled -------------------------------------------

hidden_imports = []
# collect_all() returns (datas, binaries, hiddenimports) — index [2] is hiddenimports.
hidden_imports += _fastapi[2] + _starlette[2] + _anyio[2] + _uvicorn[2]
hidden_imports += _slowapi[2] + _pydantic[2]
hidden_imports += PYWIN32_HIDDEN + SQLALCHEMY_HIDDEN + PYARMOR_HIDDEN
# watcherdb_main: import lazy no launcher (Etapa 2). pyodbc: extensao C
# invisivel na analise das fontes obfuscadas pelo PyArmor (B0-2 — o boot
# do bundle de maio morria em ModuleNotFoundError pyodbc).
hidden_imports += ["watcherdb_main", "pyodbc"]
hidden_imports += collect_submodules("api")
hidden_imports += collect_submodules("watcherdb")
hidden_imports += collect_submodules("modules")
hidden_imports += collect_submodules("services")

# --- Third-party imports por AST scan (Etapa 2, cauda do B0-2) -----------
# O PyInstaller analisa as fontes BCC-obfuscadas do PyArmor e NAO ve os
# imports third-party dentro delas (sintomas reais no boot do bundle:
# pyodbc, depois structlog). O scan abaixo le as fontes PLAIN do repo em
# build-time e adiciona todos os imports absolutos (nome dotted completo +
# top-level) a hiddenimports. Modulos opcionais ausentes no venv de build
# geram apenas WARNING do PyInstaller — inofensivo.
import ast as _ast
import sys as _sys

_FIRST_PARTY = {
    "api", "watcherdb", "services", "modules", "collectors", "scripts",
    "tools", "alembic", "config", "watcherdb_main", "watcherdb_service",
    "tests", "deploy",
}
_DEV_ONLY = {
    "pytest", "pytest_asyncio", "pytest_cov", "pytest_mock", "ruff",
    "black", "isort", "mypy", "pre_commit", "pyarmor", "PyInstaller",
    "setuptools", "pip",
}


def _scan_third_party_imports():
    py_files = []
    for d in ("api", "watcherdb", "services", "modules", "scripts", "tools"):
        base = PROJECT_ROOT / d
        if base.exists():
            py_files += [
                p for p in base.rglob("*.py") if "__pycache__" not in str(p)
            ]
    py_files += [
        PROJECT_ROOT / "watcherdb_main.py",
        PROJECT_ROOT / "watcherdb_service.py",
    ]
    # stdlib NAO e excluida do scan: o PyInstaller so inclui modulos
    # stdlib REFERENCIADOS no grafo, e referencias dentro de fontes
    # BCC-obfuscadas sao invisiveis (caso real: email.mime, usado por
    # modules/alerts/channels/email_channel, ficou fora do bundle e os
    # canais de alerta morriam no boot). Nomes ja no grafo sao no-op.
    skip = _FIRST_PARTY | _DEV_ONLY
    found = set()
    for py in py_files:
        if not py.exists():
            continue
        try:
            tree = _ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in skip:
                        found.add(top)
                        found.add(alias.name)
            elif isinstance(node, _ast.ImportFrom):
                if node.level == 0 and node.module:
                    top = node.module.split(".")[0]
                    if top not in skip:
                        found.add(top)
                        found.add(node.module)
                        # 'from X import Y' onde Y e submodulo (ex.: jose.jwt)
                        # nao aparece no grafo se o __init__ de X nao o
                        # importar. Adiciona X.Y como candidato; nomes que
                        # nao sejam modulos geram apenas 'Hidden import not
                        # found' no log do PyInstaller (nao-fatal, esperado).
                        for alias in node.names:
                            if alias.name != "*":
                                found.add(node.module + "." + alias.name)
    return sorted(found)


_THIRD_PARTY_SCANNED = _scan_third_party_imports()
print(f"[spec] AST scan: {len(_THIRD_PARTY_SCANNED)} imports third-party adicionados a hiddenimports")
hidden_imports += _THIRD_PARTY_SCANNED

# passlib carrega handlers dinamicamente por string em runtime
# (passlib.registry.get_crypt_handler -> import passlib.handlers.bcrypt),
# invisivel ao AST scan e ao modulegraph — dai o RuntimeError [AUTH]
# passlib[bcrypt] no boot (auth_service.py:163). Empacotar TODOS os
# submodulos resolve de vez.
hidden_imports += collect_submodules("passlib")

# --- Binaries from collect_all ------------------------------------------

binaries = []
# collect_all() returns (datas, binaries, hiddenimports) — index [1] is binaries.
for pack in (_fastapi, _starlette, _anyio, _uvicorn, _slowapi, _pydantic):
    binaries += pack[1]
    DATAS += pack[0]


block_cipher = None


a = Analysis(
    [str(ENTRY_POINT)],
    pathex=[str(PYARMOR_OUTPUT), str(PROJECT_ROOT)],
    binaries=binaries,
    datas=DATAS,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev-only deps never wanted in the shipping bundle.
        "pytest",
        "pytest_asyncio",
        "pytest_cov",
        "pytest_mock",
        "ruff",
        "black",
        "isort",
        "mypy",
        "pre_commit",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="watcherdb",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX corrupts pyarmor_runtime.pyd in some versions
    console=True,          # Service captures stdout/stderr for rotating logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="watcherdb",
)
