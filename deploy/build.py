"""
WatcherDB V3.3 Standard Edition — Build Script for Production Deployment

Protects Python source code with PyArmor Pro (BCC mode) and packages
everything into a dist/ directory ready for deployment.

RFT mode foi REMOVIDO 2026-07-04 (Etapa 2): renomeava simbolos cross-module
de forma inconsistente (SQLQueries -> pyarmor__428 so no consumidor, mesmo
run --recursive) e partia o arranque do bundle com ImportError. BCC compila
os corpos das funcoes para C nativo — e essa a protecao real do IP.

Usage:
    python deploy/build.py     # Build protected package

Output:
    dist/WatcherDB_V3.3/      # Ready to copy to production server

Requirements:
    - PyArmor Pro licensed (reg 011618, WatcherDB). `pyarmor --version` must
      report "pyarmor-pro" with BCC Mode and RFT Mode enabled.
    - Python 3.11+
"""

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# =============================================================
# CONFIGURATION
# =============================================================

PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT_DIR = DIST_DIR / "WatcherDB_V3.3"


def _load_release_vars(path: Path) -> dict:
    """Parser minimal para deploy/release_vars.psd1 — audit S2-5 SOT.

    PowerShell data files sao Python-unfriendly, mas o nosso formato e
    key = 'string' / key = integer, simples o suficiente para regex puro.
    """
    result: dict[str, str] = {}
    if not path.exists():
        return result
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*"
        r"(?:'([^']*)'|\"([^\"]*)\"|([0-9]+))",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        key = m.group(1)
        val = m.group(2) or m.group(3) or m.group(4)
        if val is not None:
            result[key] = val
    return result


RELEASE_VARS = _load_release_vars(PROJECT_ROOT / "deploy" / "release_vars.psd1")

# Directories with Python code to PROTECT (PyArmor)
PROTECT_DIRS = [
    "api",
    "watcherdb",
    "services",
    "modules",
    "collectors",
    "scripts",
    "tools",
    "alembic",
]

# Ficheiros que saem do compilador BCC do PyArmor (continuam protegidos em
# modo standard). Caminhos relativos a PROJECT_ROOT, com barras normais.
#
# 2026-08-12 -- FIND SystemError: api/routers/intelligence_kpis.py serve TODAS
# as modais de instancias do portal e devolvia 500 no bundle com
# "SystemError: error return without exception set", a rebentar na fronteira
# da chamada, antes de qualquer linha do corpo correr. Reproducao isolada do
# python-packaging-architect (sem PyInstaller, com a BD mockada): 148 de 152
# combinacoes falham no output BCC, 152 de 152 passam na fonte limpa. Defeito
# de codegen do BCC 9.2.6 numa funcao de 1327 linhas / 115 ramos.
# NOTA: o build passava (exit 0) e a paridade tambem -- so' rebentava no
# clique do utilizador. Ver o gate comportamental proposto para PASSO 1.5.
# Sai desta lista quando a funcao for partida em handlers pequenos (wave
# propria) -- funcoes pequenas nem qualificam para geracao BCC nativa.
BCC_DENYLIST = [
    "api/routers/intelligence_kpis.py",
]

# Root Python files to PROTECT
PROTECT_FILES = [
    "watcherdb_main.py",
    # watcherdb_intelligence.py REMOVIDO (auditoria empacotamento B0-3/1.3):
    # ficheiro morto (zero imports em runtime), ~277KB de IP do vendor.
    # Nao entra no bundle Standard.
]

# Directories/files to COPY WITHOUT protection
COPY_DIRS = [
    "templates",
    "static",
    "config",
    "database",
]

# Individual files to copy
COPY_FILES = [
    # Etapa 2 (B0-1): o launcher SCM vai SEM PyArmor — boilerplate pywin32
    # sem IP nenhum. Sob BCC o "except Exception" do fallback 1063
    # (dispatcher->consola) nao apanhava pywintypes.error e o exe morria
    # com traceback (2026-07-04: padrao OK em CPython puro, falha
    # BCC-compilado). A app inteira (watcherdb_main + pacotes) continua
    # protegida; o launcher importa-a lazy ja obfuscada.
    "watcherdb_service.py",
    ".env.example",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-alerting.txt",
    "requirements-analytics.txt",
    "alembic.ini",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    "package.json",
    "tsconfig.json",
    "vite.config.ts",
    "README.md",
    "start_server_dev.bat",
]

# Fail-loud: por default o build ABORTA se algum ficheiro ficar sem protecao
# PyArmor (caso real 2026-05-13: dashboard_api.py shipado unprotected via
# fallback silencioso - pyarmor.bug.log). Override: --allow-unprotected.
ALLOW_UNPROTECTED = "--allow-unprotected" in sys.argv

# NOTA: a protecao do que entra no bundle e o modelo ALLOWLIST
# (PROTECT_DIRS/COPY_DIRS/COPY_FILES). Nao existe camada de exclusao ativa -
# uma lista EXCLUDE anterior estava definida mas nunca aplicada (removida
# 2026-07-03, auditoria empacotamento B2-17). Sanitizacao de config/ com
# dados reais = Etapa 1.3 do roadmap.


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icon = {"INFO": "→", "OK": "✓", "WARN": "⚠", "ERROR": "✗"}
    print(f"  [{ts}] {icon.get(level, '→')} {msg}")


def check_pyarmor():
    """Verify PyArmor is installed AND is the licensed Pro build (reg 011618).

    Fail-fast: um trial/basic instalado por engano so rebentava a meio do
    build no primeiro `gen --enable bcc`. Valida returncode + dois sinais
    redundantes do output ("(pro)" na 1a linha, "pyarmor-pro" no License
    Type — formato gerado por mapa fechado em pyarmor/cli/register.py,
    estavel em 9.2.x) + o reg 011618 (apanha "Pro valido mas nao e o
    nosso"). NOTA: valida tier de LICENCA, nao o compilador BCC —
    clang.exe/LLVM e validado a parte (build_release.ps1 PASSO 2).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pyarmor.cli", "--version"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        log(f"PyArmor not found: {e}", "ERROR")
        log("Install with: pip install -r requirements-build.txt", "ERROR")
        return False
    out = (result.stdout or "") + (result.stderr or "")
    version = out.strip().split("\n")[0] if out.strip() else "unknown"
    if result.returncode != 0:
        log(f"pyarmor.cli --version falhou (exit {result.returncode}):", "ERROR")
        log(out.strip()[:600], "ERROR")
        return False
    low = out.lower()
    if "pyarmor-pro" not in low and "(pro)" not in low:
        log(f"PyArmor instalado NAO e o Pro licenciado: {version}", "ERROR")
        log(out.strip()[:600], "ERROR")
        return False
    if "011618" not in out:
        log(f"PyArmor Pro presente mas reg != 011618 (licenca errada?): {version}", "ERROR")
        log(out.strip()[:600], "ERROR")
        return False
    log(f"PyArmor version: {version}", "OK")
    return True


def check_pyinstaller():
    """Verify PyInstaller is installed on the build workstation."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        version = result.stdout.strip() or "unknown"
        log(f"PyInstaller version: {version}", "OK")
        return True
    except Exception as e:
        log(f"PyInstaller not found: {e}", "ERROR")
        log("Install with: pip install -r requirements-build.txt", "ERROR")
        return False


def clean_dist():
    """Remove previous build -- SO' o que este script produz.

    2026-08-12: apagava dist/ inteiro, incluindo dist/msi -- que NAO e' output
    deste script (e' do deploy/build_msi.ps1, que corre depois). Resultado
    real: um .msi de uma instalacao anterior ficou com handle aberto e o build
    do bundle morria em shutil.rmtree antes de sequer comecar, por causa de um
    artefacto alheio. Cada script limpa o que e' seu.
    """
    for target in (OUTPUT_DIR, BUNDLE_DIR):
        if target.exists():
            log(f"Cleaning {target}...")
            try:
                shutil.rmtree(target)
            except OSError as exc:
                log(f"Nao foi possivel limpar {target}: {exc}", "ERROR")
                log("Fecha o que estiver a usar esses ficheiros e repete.", "ERROR")
                return False
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log("dist/ directory created", "OK")
    return True


def protect_python_files():
    """Run PyArmor on all Python source files."""
    log("=" * 50)
    log("PHASE 1: Protecting Python code with PyArmor")
    log("=" * 50)

    # Protect root-level Python files
    for py_file in PROTECT_FILES:
        src = PROJECT_ROOT / py_file
        if src.exists():
            log(f"Protecting {py_file}...")
            result = subprocess.run(
                [sys.executable, "-m", "pyarmor.cli", "gen",
                 "--enable", "bcc",
                 "--output", str(OUTPUT_DIR),
                 str(src)],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT),
            )
            if result.returncode != 0:
                log(f"PyArmor error on {py_file}: {result.stderr[:200]}", "ERROR")
                return False
            log(f"Protected {py_file}", "OK")

    # Protect directories with Python code
    for dir_name in PROTECT_DIRS:
        src_dir = PROJECT_ROOT / dir_name
        if not src_dir.exists():
            log(f"Skipping {dir_name}/ (not found)", "WARN")
            continue

        # Collect all .py files in this directory tree
        py_files = list(src_dir.rglob("*.py"))
        py_files = [f for f in py_files if "__pycache__" not in str(f)]

        if not py_files:
            log(f"Skipping {dir_name}/ (no .py files)", "WARN")
            continue

        log(f"Protecting {dir_name}/ ({len(py_files)} files)...")

        # Ficheiros que NAO podem passar pelo compilador BCC (ver BCC_DENYLIST).
        # Saem do gen recursivo por --exclude e levam segunda passagem sem
        # --enable bcc logo a seguir: continuam protegidos, so' que em modo
        # standard (obf-code) em vez de compilacao nativa.
        dir_denied = [p for p in BCC_DENYLIST if p.startswith(dir_name + "/")]
        exclude_args = []
        for _p in dir_denied:
            exclude_args += ["--exclude", _p]

        # PyArmor can protect entire packages
        result = subprocess.run(
            [sys.executable, "-m", "pyarmor.cli", "gen",
             "--enable", "bcc",
             "--output", str(OUTPUT_DIR),
             "--recursive",
             *exclude_args,
             str(src_dir)],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            log(f"PyArmor error on {dir_name}/: {result.stderr[:300]}", "ERROR")
            # Try file-by-file as fallback
            log(f"Trying file-by-file for {dir_name}/...", "WARN")
            for py_file in py_files:
                rel_path = py_file.relative_to(PROJECT_ROOT)
                target_dir = OUTPUT_DIR / rel_path.parent
                target_dir.mkdir(parents=True, exist_ok=True)

                r2 = subprocess.run(
                    [sys.executable, "-m", "pyarmor.cli", "gen",
                     "--enable", "bcc",
                     "--output", str(target_dir),
                     str(py_file)],
                    capture_output=True, text=True, cwd=str(PROJECT_ROOT),
                )
                if r2.returncode != 0:
                    if ALLOW_UNPROTECTED:
                        log(f"  Failed: {rel_path} - copying UNPROTECTED (--allow-unprotected)", "WARN")
                        shutil.copy2(py_file, target_dir / py_file.name)
                    else:
                        log(f"  PyArmor failed on {rel_path}: {r2.stderr[:300]}", "ERROR")
                        log("  BUILD ABORTED: file would ship unprotected. Fix the cause or re-run with --allow-unprotected.", "ERROR")
                        return False
        else:
            log(f"Protected {dir_name}/ ({len(py_files)} files)", "OK")

        # Segunda passagem, sem BCC, para os excluidos deste directorio.
        for rel in dir_denied:
            src_file = PROJECT_ROOT / rel
            if not src_file.exists():
                log(f"BCC_DENYLIST aponta para ficheiro inexistente: {rel}", "ERROR")
                return False
            target_dir = OUTPUT_DIR / Path(rel).parent
            target_dir.mkdir(parents=True, exist_ok=True)
            log(f"Protecting {rel} WITHOUT bcc (denylist)...")
            r3 = subprocess.run(
                [sys.executable, "-m", "pyarmor.cli", "gen",
                 "--output", str(target_dir),
                 str(src_file)],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT),
            )
            if r3.returncode != 0:
                log(f"PyArmor (non-BCC) failed on {rel}: {r3.stderr[:300]}", "ERROR")
                return False
            log(f"Protected {rel} (standard mode)", "OK")

    return True


def _protected_source_relpaths():
    """Descoberta de fontes a proteger — MESMA logica de protect_python_files().

    Nao reinventar uma segunda lista (drift entre as duas invalidaria a
    verificacao de paridade). Qualquer mudanca a PROTECT_DIRS/PROTECT_FILES
    ou aos filtros de protect_python_files() tem de se reflectir aqui.
    """
    rels = set()
    for py_file in PROTECT_FILES:
        src = PROJECT_ROOT / py_file
        if src.exists():
            rels.add(Path(py_file).as_posix())
    for dir_name in PROTECT_DIRS:
        src_dir = PROJECT_ROOT / dir_name
        if not src_dir.exists():
            continue
        for f in src_dir.rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            rels.add(f.relative_to(PROJECT_ROOT).as_posix())
    return rels


def verify_protection_parity():
    """Set-diff fonte vs OUTPUT_DIR apos PyArmor, ANTES de copy_assets().

    O ramo feliz do `pyarmor gen --recursive` (returncode 0) nunca verifica
    que cada .py de entrada gerou saida — assume retcode 0 = tudo protegido.
    Consult specialists 2026-08-10: o dist de 04/07 tinha exactamente 3
    ficheiros de api/ ausentes (adicionados ao source em 04/08) — gap real
    deste tipo e invisivel sem isto. Set-diff em vez de contagem: contagem
    igual mascara um swap (1 em falta + 1 extra). Missing = ERROR fail-loud;
    extra = WARNING (sem evidencia empirica em 9.2.4, blindagem futura).

    Tem de correr antes de copy_assets(): nesse ponto OUTPUT_DIR so contem
    saida PyArmor + pyarmor_runtime_* (watcherdb_service.py unprotected e
    deploy/ entram nas fases seguintes, por design).
    """
    src = _protected_source_relpaths()
    out = set()
    for f in OUTPUT_DIR.rglob("*.py"):
        rel = f.relative_to(OUTPUT_DIR).as_posix()
        if rel.startswith("pyarmor_runtime") or "__pycache__" in rel:
            continue
        out.add(rel)
    extra = sorted(out - src)
    missing = sorted(src - out)
    if extra:
        log(f"{len(extra)} .py no output sem fonte correspondente (inesperado, nao-fatal):", "WARN")
        for rel in extra[:20]:
            log(f"  extra: {rel}", "WARN")
    if missing:
        log(f"{len(missing)} .py fonte SEM saida protegida no output:", "ERROR")
        for rel in missing[:40]:
            log(f"  missing: {rel}", "ERROR")
        log("BUILD ABORTED: paridade fonte/output falhou apos PyArmor.", "ERROR")
        return False
    log(f"Paridade PyArmor OK: {len(src)} .py fonte, todos com saida protegida.", "OK")
    return True


def copy_assets():
    """Copy non-Python files (templates, static, config, etc.)."""
    log("=" * 50)
    log("PHASE 2: Copying assets (templates, static, config, database)")
    log("=" * 50)

    # Copy directories
    for dir_name in COPY_DIRS:
        src_dir = PROJECT_ROOT / dir_name
        dst_dir = OUTPUT_DIR / dir_name
        if src_dir.exists():
            # Copy, excluding __pycache__ and .bak files
            shutil.copytree(
                src_dir, dst_dir,
                # B0-3 (auditoria empacotamento): config/*.json vivos (infra
                # real do vendor + passwords Fernet) NAO entram no bundle.
                # Templates (*.json.template), YAML e SQL entram. Runtime
                # seeds ProgramData via watcherdb.core.paths.bootstrap_config().
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.bak", "*.bak_*", "*.backup",
                    "servers.json", "sql_servers.json", "sql_servers_new.json",
                    "alwayson_inventory.json", "custom_queries.json",
                ),
                dirs_exist_ok=True,
            )
            file_count = sum(1 for _ in dst_dir.rglob("*") if _.is_file())
            log(f"Copied {dir_name}/ ({file_count} files)", "OK")

    # Copy individual files
    for file_name in COPY_FILES:
        src = PROJECT_ROOT / file_name
        if src.exists():
            dst = OUTPUT_DIR / file_name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log(f"Copied {file_name}", "OK")

    # Create empty directories
    for d in ["logs", "reports"]:
        (OUTPUT_DIR / d).mkdir(parents=True, exist_ok=True)

    # B1-8 (auditoria empacotamento): NAO criar .env no bundle. .env vive em
    # C:\ProgramData\WatcherDB\.env (editado pelo DBA), resolvido 3-tier em
    # runtime. Shippar .env em Program Files = anti-padrao (dir read-only +
    # secrets no artefacto). O .env.example fica como documentacao.


def copy_deploy_scripts():
    """Copy deployment scripts."""
    log("=" * 50)
    log("PHASE 3: Copying deployment scripts")
    log("=" * 50)

    deploy_src = PROJECT_ROOT / "deploy"
    deploy_dst = OUTPUT_DIR / "deploy"
    if deploy_src.exists():
        shutil.copytree(
            deploy_src, deploy_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "build.py"),
            dirs_exist_ok=True,
        )
        log("Copied deploy/ scripts", "OK")


BUNDLE_DIR = PROJECT_ROOT / "dist" / "watcherdb"


def bundle_with_pyinstaller():
    """Wrap the PyArmor output in a self-contained directory bundle with watcherdb.exe."""
    log("=" * 50)
    log("PHASE 4: Bundling with PyInstaller (watcherdb.exe)")
    log("=" * 50)

    spec_path = PROJECT_ROOT / "deploy" / "watcherdb.spec"
    if not spec_path.exists():
        log(f"Spec file not found: {spec_path}", "ERROR")
        return False

    # PyInstaller drops its own dist/ and build/ next to where it is run from.
    # Run from PROJECT_ROOT so dist/watcherdb/ lands in the expected place.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_path),
    ]
    log(f"Running: {' '.join(cmd[-3:])}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        log(f"PyInstaller failed with exit code {result.returncode}", "ERROR")
        return False

    exe_path = BUNDLE_DIR / "watcherdb.exe"
    if not exe_path.exists():
        log(f"PyInstaller did not produce {exe_path}", "ERROR")
        return False
    log(f"Bundle created: {BUNDLE_DIR}", "OK")
    log(f"Entry point:    {exe_path}", "OK")
    return True


def create_version_file():
    """Create version info files for both the PyArmor output and the PyInstaller bundle."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    py_version = sys.version.split()[0]
    # S2-5: product name + version lidos do SOT (release_vars.psd1) se disponivel.
    product_name = RELEASE_VARS.get("ProductName", "WatcherDB V3.3 Standard Edition")
    product_version = RELEASE_VARS.get("ProductVersion", "3.3.0.0")
    service_name = RELEASE_VARS.get("ServiceName", "WatcherDBWebServiceV33")
    web_port = RELEASE_VARS.get("WebPort", "8433")
    # Git sha do checkout de build: lido por GET /api/version (QA externo
    # 2026-08-16 - sem isto nao ha' como saber que build esta' em PRD).
    try:
        import subprocess
        git_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "n/a"
    except Exception:
        git_sha = "n/a"
    content = (
        f"{product_name}\n"
        f"Version:   {product_version}\n"
        f"Service:   {service_name} (port {web_port})\n"
        f"Build:     {stamp}\n"
        f"Git:       {git_sha}\n"
        f"Protected: PyArmor Pro (reg 011618, BCC)\n"
        f"Bundled:   PyInstaller (onedir)\n"
        f"Python:    {py_version}\n"
    )
    (OUTPUT_DIR / "VERSION.txt").write_text(content, encoding="utf-8")
    if BUNDLE_DIR.exists():
        (BUNDLE_DIR / "VERSION.txt").write_text(content, encoding="utf-8")
    log("Created VERSION.txt", "OK")


def verify_no_secrets_in_bundle():
    """Falha o build se o bundle levar segredos ou inventario real.

    2026-08-12 -- o MSI entregue levava 2,3 MB de infra do vendor: quatro
    ficheiros (servers_27072026.json, servers.json.backup_pre_reencrypt,
    servers.json.backup_pre_sync, servers.json.backup_pre_description_sync_*)
    com ~200 instancias, utilizadores e passwords Fernet. A proteccao que
    devia impedir isso existia no .spec mas filtrava por NOME EXACTO -- quatro
    variantes de nome passaram-lhe ao lado, sem ninguem reparar.

    O .spec passou a lista branca; este gate e' a segunda linha: verifica o
    CONTEUDO do bundle final. Uma lista de nomes envelhece a cada ficheiro
    novo; "isto parece um criptograma Fernet" nao envelhece.
    """
    log("=" * 50)
    log("PHASE 3.9: Secret scan (bundle content)")
    log("=" * 50)

    if not BUNDLE_DIR.exists():
        log(f"Bundle nao encontrado: {BUNDLE_DIR}", "ERROR")
        return False

    # gAAAAA = prefixo de token Fernet (versao 0x80 + timestamp) em base64url.
    needles = (b"gAAAAA", b"BEGIN RSA PRIVATE KEY", b"BEGIN PRIVATE KEY",
               b"BEGIN OPENSSH PRIVATE KEY")
    scan_suffixes = {".json", ".yaml", ".yml", ".ini", ".cfg", ".txt",
                     ".env", ".sql", ".xml", ".template", ".bak", ".backup"}

    offenders = []
    for path in BUNDLE_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in scan_suffixes and "." in path.name[1:]:
            # nomes compostos tipo servers.json.backup_pre_sync tambem entram
            if not any(s in path.name.lower() for s in (".json", ".yaml", ".env")):
                continue
        elif path.suffix.lower() not in scan_suffixes:
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        hit = next((n for n in needles if n in blob), None)
        if hit:
            offenders.append((path.relative_to(BUNDLE_DIR), hit.decode(), len(blob)))

    if offenders:
        log("SEGREDOS NO BUNDLE — build abortado:", "ERROR")
        for rel, hit, size in offenders:
            log(f"  {rel}  ({size} bytes, contem {hit!r})", "ERROR")
        log("Corrigir a lista branca de deploy/watcherdb.spec ou remover o "
            "ficheiro de config/ antes de reconstruir.", "ERROR")
        return False

    log("Secret scan limpo (nenhum criptograma nem chave privada no bundle)", "OK")
    return True


def print_summary():
    """Print build summary."""
    def _stats(path):
        if not path.exists():
            return 0, 0.0
        files = sum(1 for _ in path.rglob("*") if _.is_file())
        bytes_ = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return files, bytes_ / 1024 / 1024

    obf_files, obf_mb = _stats(OUTPUT_DIR)
    bun_files, bun_mb = _stats(BUNDLE_DIR)

    print()
    print("=" * 60)
    print(f"  BUILD COMPLETE — WatcherDB V3.3 Standard Edition")
    print("=" * 60)
    print(f"  PyArmor output: {OUTPUT_DIR}")
    print(f"    files: {obf_files}  size: {obf_mb:.1f} MB")
    if BUNDLE_DIR.exists():
        print(f"  PyInstaller bundle: {BUNDLE_DIR}")
        print(f"    files: {bun_files}  size: {bun_mb:.1f} MB")
        print(f"    entry: {BUNDLE_DIR / 'watcherdb.exe'}")
    print()
    print("  NEXT STEPS (commercial onedir bundle):")
    print(f"  1. Copy {BUNDLE_DIR.name}/ to the customer server.")
    print("  2. Deploy a signed license.dat to C:\\ProgramData\\WatcherDB\\license.dat.")
    print("  3. Register the Windows service pointing at watcherdb.exe.")
    print("  4. (Sem 3) MSI installer will automate steps 1-3.")
    print("=" * 60)


def main():
    # Ensure UTF-8 stdout/stderr — log() uses Unicode icons (✓✗→⚠).
    # Default cp1252 on Windows console crashes with UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7 (reconfigure not available)
    print()
    print("=" * 60)
    print("  WatcherDB V3.3 Standard Edition — Production Build")
    print("=" * 60)
    print(f"  Source:  {PROJECT_ROOT}")
    print(f"  Output:  {OUTPUT_DIR}")
    print()

    # Check prerequisites
    if not check_pyarmor():
        sys.exit(1)
    if not check_pyinstaller():
        sys.exit(1)

    # Build
    if not clean_dist():
        log("Build failed cleaning previous output", "ERROR")
        sys.exit(1)

    # Strip UTF-8 BOM from source files before PyArmor — a BOM causes
    # SyntaxError at runtime in obfuscated output (see pyarmor.bug.log).
    log("Sanitising source files (BOM strip)...")
    try:
        from sanitize_bom import main as _sanitize_main
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        from sanitize_bom import main as _sanitize_main
    _sanitize_main(PROJECT_ROOT)

    if not protect_python_files():
        log("Build failed during PyArmor protection", "ERROR")
        sys.exit(1)

    if not verify_protection_parity():
        log("Build failed protection parity check (source vs output)", "ERROR")
        sys.exit(1)

    copy_assets()
    copy_deploy_scripts()

    if not bundle_with_pyinstaller():
        log("Build failed during PyInstaller bundling", "ERROR")
        sys.exit(1)

    if not verify_no_secrets_in_bundle():
        log("Build failed secret scan (bundle would leak vendor infra)", "ERROR")
        sys.exit(1)

    create_version_file()
    print_summary()


if __name__ == "__main__":
    main()
