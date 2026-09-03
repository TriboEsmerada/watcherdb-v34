r"""
prereqs_check.py — Pre-install validator (B3 sprint install v0.2).

Install flow v0.2 sprint B3 (FIND-20260424-001).

Valida pre-requisitos antes do installer arrancar. Nao instala nada —
reporta status actionable ao operador. Exit code determina se installer
deve prosseguir.

Checks:
  * CHK-01: ODBC Driver 17 ou 18 para SQL Server presente
  * CHK-02: SQL Server TCP reachable (host/port acessivel)
  * CHK-03: sql_monitoring SQL login existe + perms minimas
  * CHK-04: AD service account resolvivel
  * CHK-05: Porta do web service disponivel (nao em uso)
  * CHK-06: Python 3.11+ (se usar PyInstaller bundle, irrelevante)
  * CHK-07: Disk space >= 500MB em install directory
  * CHK-08: Admin privileges para MSI install

Usage:
    python prereqs_check.py \
        --sql-server SQL01.banco.pt \
        --sql-port 1433 \
        --sql-user sql_monitoring \
        --ad-service-account DOMAIN\watcherdb_svc \
        --web-port 8433 \
        --install-dir "C:\Program Files\WatcherDB"

Exit codes:
    0 - all checks pass
    1 - one or more errors (blocking)
    2 - warnings only (installer may proceed)
    3 - invocation error (bad args)
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ---------- Result types ---------------------------------------------------


@dataclass
class CheckResult:
    check_id: str
    name: str
    status: str  # PASS | WARN | FAIL | SKIP
    message: str
    fix_hint: str = ""


@dataclass
class PrereqsReport:
    results: List[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == "WARN")

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")


# ---------- Individual checks ----------------------------------------------


def check_odbc_driver() -> CheckResult:
    """CHK-01: ODBC Driver 17 or 18 for SQL Server installed."""
    try:
        key_path = r"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
            i = 0
            found_drivers = []
            while True:
                try:
                    name, _, _ = winreg.EnumValue(k, i)
                    if "ODBC Driver 17 for SQL Server" in name or "ODBC Driver 18 for SQL Server" in name:
                        found_drivers.append(name)
                    i += 1
                except OSError:
                    break

            if found_drivers:
                return CheckResult(
                    "CHK-01", "ODBC Driver 17/18",
                    "PASS", f"Found: {', '.join(found_drivers)}",
                )
            return CheckResult(
                "CHK-01", "ODBC Driver 17/18",
                "FAIL", "ODBC Driver 17 or 18 for SQL Server not installed",
                fix_hint="Download: https://aka.ms/odbc-sqlserver",
            )
    except OSError as e:
        return CheckResult(
            "CHK-01", "ODBC Driver 17/18",
            "WARN", f"Registry query failed: {e}",
            fix_hint="Run as Administrator or check registry access",
        )


def check_sql_tcp_reachable(host: str, port: int = 1433, timeout: float = 5.0) -> CheckResult:
    """CHK-02: SQL Server TCP port reachable."""
    if not host:
        return CheckResult(
            "CHK-02", "SQL Server TCP",
            "SKIP", "No --sql-server provided",
        )
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return CheckResult(
                "CHK-02", "SQL Server TCP",
                "PASS", f"{host}:{port} reachable",
            )
    except socket.timeout:
        return CheckResult(
            "CHK-02", "SQL Server TCP",
            "FAIL", f"{host}:{port} timeout ({timeout}s)",
            fix_hint="Check firewall rules + SQL Server TCP enabled + instance running",
        )
    except socket.gaierror:
        return CheckResult(
            "CHK-02", "SQL Server TCP",
            "FAIL", f"{host} DNS resolution failed",
            fix_hint="Check DNS server config + hostname spelling",
        )
    except OSError as e:
        return CheckResult(
            "CHK-02", "SQL Server TCP",
            "FAIL", f"Network error: {e}",
        )


def check_sql_login_exists(
    host: str, port: int, login_name: str, timeout: int = 10,
) -> CheckResult:
    """CHK-03: sql_monitoring login exists + has required permissions.

    Usa pyodbc se disponivel; senao SKIP (check detalhado corre durante install).
    """
    if not host or not login_name:
        return CheckResult(
            "CHK-03", "SQL login + perms",
            "SKIP", "No --sql-server or --sql-user provided",
        )

    try:
        import pyodbc  # type: ignore[import-not-found]
    except ImportError:
        return CheckResult(
            "CHK-03", "SQL login + perms",
            "SKIP", "pyodbc not installed in current env (installer bundle will include it)",
            fix_hint="Skipped — installer will validate after bundle deployed",
        )

    # Tenta Windows auth primeiro (menos intrusive)
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={host},{port};DATABASE=master;Trusted_Connection=Yes;"
            f"Connection Timeout={timeout};"
        )
        with pyodbc.connect(conn_str, timeout=timeout) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, type_desc FROM sys.server_principals WHERE name = ?",
                login_name,
            )
            row = cursor.fetchone()
            if not row:
                return CheckResult(
                    "CHK-03", "SQL login + perms",
                    "FAIL", f"Login '{login_name}' does not exist on {host}",
                    fix_hint=f"CREATE LOGIN [{login_name}] WITH PASSWORD = '...' (or Windows group); GRANT VIEW SERVER STATE",
                )

            # Check VIEW SERVER STATE perm (minimum required)
            cursor.execute(
                """
                SELECT COUNT(*) FROM sys.server_permissions sp
                JOIN sys.server_principals pr ON sp.grantee_principal_id = pr.principal_id
                WHERE pr.name = ? AND sp.permission_name = 'VIEW SERVER STATE' AND sp.state = 'G'
                """,
                login_name,
            )
            has_vss = cursor.fetchone()[0] > 0
            if not has_vss:
                return CheckResult(
                    "CHK-03", "SQL login + perms",
                    "WARN", f"Login '{login_name}' exists but missing VIEW SERVER STATE",
                    fix_hint=f"GRANT VIEW SERVER STATE TO [{login_name}]",
                )

            return CheckResult(
                "CHK-03", "SQL login + perms",
                "PASS", f"Login '{login_name}' exists with VIEW SERVER STATE",
            )
    except pyodbc.Error as e:
        return CheckResult(
            "CHK-03", "SQL login + perms",
            "WARN", f"Could not verify via Windows auth: {e}",
            fix_hint="Installer will retry with configured credentials",
        )


def check_ad_account(account_spec: str) -> CheckResult:
    """CHK-04: AD service account resolvable (DOMAIN\\user)."""
    if not account_spec:
        return CheckResult(
            "CHK-04", "AD service account",
            "SKIP", "No --ad-service-account provided",
        )

    if "\\" not in account_spec:
        return CheckResult(
            "CHK-04", "AD service account",
            "WARN", f"Account '{account_spec}' missing domain prefix (expected DOMAIN\\user)",
        )

    domain, user = account_spec.split("\\", 1)
    try:
        # Usar `net user /domain` para validar — mais portavel que LDAP
        result = subprocess.run(
            ["net", "user", user, "/domain"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return CheckResult(
                "CHK-04", "AD service account",
                "PASS", f"Account '{account_spec}' resolvable",
            )
        return CheckResult(
            "CHK-04", "AD service account",
            "FAIL", f"Account '{account_spec}' not found: {result.stderr.strip()[:120]}",
            fix_hint=f"Create AD user '{user}' in domain '{domain}' with 'Logon as a service' right",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return CheckResult(
            "CHK-04", "AD service account",
            "WARN", f"Could not validate via net.exe: {e}",
            fix_hint="Verify manually with 'net user <user> /domain'",
        )


def check_port_available(port: int) -> CheckResult:
    """CHK-05: Target web port not in use."""
    if not port:
        return CheckResult(
            "CHK-05", "Port available",
            "SKIP", "No --web-port provided",
        )
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
        return CheckResult(
            "CHK-05", "Port available",
            "PASS", f"Port {port} is free",
        )
    except OSError as e:
        return CheckResult(
            "CHK-05", "Port available",
            "FAIL", f"Port {port} in use: {e}",
            fix_hint=f"Use 'netstat -ano | findstr :{port}' to identify occupier",
        )


def check_disk_space(install_dir: str, min_mb: int = 500) -> CheckResult:
    """CHK-07: Disk free space in install drive."""
    if not install_dir:
        return CheckResult(
            "CHK-07", "Disk space",
            "SKIP", "No --install-dir provided",
        )
    try:
        p = Path(install_dir)
        # Use parent if dir doesnt exist yet (install target)
        target = p if p.exists() else p.anchor or "C:\\"
        total, used, free = shutil.disk_usage(str(target))
        free_mb = free // (1024 * 1024)
        if free_mb < min_mb:
            return CheckResult(
                "CHK-07", "Disk space",
                "FAIL", f"{free_mb}MB free on {target} (need {min_mb}MB)",
                fix_hint="Free up disk space or choose different install drive",
            )
        return CheckResult(
            "CHK-07", "Disk space",
            "PASS", f"{free_mb}MB free on {target}",
        )
    except OSError as e:
        return CheckResult(
            "CHK-07", "Disk space",
            "WARN", f"Could not query: {e}",
        )


def check_admin_privileges() -> CheckResult:
    """CHK-08: Running as Administrator (MSI needs elevated)."""
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if is_admin:
            return CheckResult(
                "CHK-08", "Admin privileges",
                "PASS", "Running as Administrator",
            )
        return CheckResult(
            "CHK-08", "Admin privileges",
            "WARN", "Not elevated (installer MSI requires Admin)",
            fix_hint="Re-run prereqs check / installer from elevated shell (Right-click → Run as administrator)",
        )
    except (AttributeError, OSError):
        return CheckResult(
            "CHK-08", "Admin privileges",
            "SKIP", "Not a Windows environment",
        )


def check_python_version(min_major: int = 3, min_minor: int = 11) -> CheckResult:
    """CHK-06: Python 3.11+ (relevant if not using bundled PyInstaller)."""
    v = sys.version_info
    if (v.major, v.minor) >= (min_major, min_minor):
        return CheckResult(
            "CHK-06", "Python version",
            "PASS", f"Python {v.major}.{v.minor}.{v.micro}",
        )
    return CheckResult(
        "CHK-06", "Python version",
        "WARN", f"Python {v.major}.{v.minor}.{v.micro} — recommended >= {min_major}.{min_minor}",
        fix_hint="PyInstaller bundle bypasses this — warning only if running from source",
    )


# ---------- Runner + reporter ----------------------------------------------


def run_all(
    *,
    sql_server: str = "",
    sql_port: int = 1433,
    sql_user: str = "sql_monitoring",
    ad_service_account: str = "",
    web_port: int = 0,
    install_dir: str = "",
    min_disk_mb: int = 500,
) -> PrereqsReport:
    """Execute all checks and return report."""
    report = PrereqsReport()
    report.results.append(check_odbc_driver())
    report.results.append(check_sql_tcp_reachable(sql_server, sql_port))
    report.results.append(check_sql_login_exists(sql_server, sql_port, sql_user))
    report.results.append(check_ad_account(ad_service_account))
    report.results.append(check_port_available(web_port))
    report.results.append(check_python_version())
    report.results.append(check_disk_space(install_dir, min_disk_mb))
    report.results.append(check_admin_privileges())
    return report


def print_report(report: PrereqsReport) -> None:
    """Human-readable report to stdout."""
    COLOR = {
        "PASS": "\033[92m",
        "WARN": "\033[93m",
        "FAIL": "\033[91m",
        "SKIP": "\033[90m",
    }
    RESET = "\033[0m"
    # Windows console may not support ANSI — strip if TERM not set
    if os.name == "nt" and not os.environ.get("TERM"):
        COLOR = {k: "" for k in COLOR}
        RESET = ""

    print("=" * 70)
    print("WatcherDB Pre-install Prereqs Check")
    print("=" * 70)
    for r in report.results:
        c = COLOR.get(r.status, "")
        print(f"  [{c}{r.status:4}{RESET}] {r.check_id} {r.name}: {r.message}")
        if r.fix_hint and r.status in ("FAIL", "WARN"):
            print(f"         → {r.fix_hint}")

    print("-" * 70)
    print(f"  {report.passed} passed, {report.warned} warnings, {report.failed} failed")
    print("=" * 70)

    if report.failed > 0:
        print("\nFAIL: fix errors above before running installer.")
    elif report.warned > 0:
        print("\nWARN: installer may proceed but review warnings.")
    else:
        print("\nOK: all checks passed. Safe to install.")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sql-server", default="", help="SQL Server hostname for reachability check")
    parser.add_argument("--sql-port", type=int, default=1433)
    parser.add_argument("--sql-user", default="sql_monitoring")
    parser.add_argument("--ad-service-account", default="", help="DOMAIN\\user for AD validation")
    parser.add_argument("--web-port", type=int, default=0, help="Web service port to check availability")
    parser.add_argument("--install-dir", default="", help="Install target for disk space check")
    parser.add_argument("--min-disk-mb", type=int, default=500)
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args(argv)

    report = run_all(
        sql_server=args.sql_server,
        sql_port=args.sql_port,
        sql_user=args.sql_user,
        ad_service_account=args.ad_service_account,
        web_port=args.web_port,
        install_dir=args.install_dir,
        min_disk_mb=args.min_disk_mb,
    )

    if args.json:
        import json
        doc = {
            "summary": {
                "passed": report.passed,
                "warnings": report.warned,
                "failed": report.failed,
            },
            "checks": [
                {
                    "id": r.check_id, "name": r.name, "status": r.status,
                    "message": r.message, "fix_hint": r.fix_hint,
                }
                for r in report.results
            ],
        }
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print_report(report)

    if report.failed > 0:
        return 1
    if report.warned > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
