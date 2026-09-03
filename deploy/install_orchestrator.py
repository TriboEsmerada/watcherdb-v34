r"""
install_orchestrator.py — Entry point unico que compoe os 4 scripts do sprint
install flow v0.2 numa sequencia de 5 fases.

Sprint install flow v0.2 orchestrator (FIND-20260424-001).

Chamado pelo Burn bootstrapper (B1, deferred) OU directamente como standalone
Python script. Compoe:

  Fase 1: prereqs_check.py        (B3) — valida ambiente antes de instalar
  Fase 2: (MSI install — externo) — bootstrapper invoca msiexec; orchestrator
                                    nao corre este step, so spawna chamadas
                                    antes/depois
  Fase 3: industry_wizard.py      (B2) — client_context + compliance_rules
  Fase 4: farm_inventory_parser.py (B7) — servers.json canonical
  Fase 5: license generation       (B5) — vendor gera license.dat (out-of-band)
                                           OU operador coloca .dat recebido

Usage:
    # Interactive full wizard
    python install_orchestrator.py --mode interactive --install-dir "C:\Program Files\WatcherDB"

    # Non-interactive (para Burn bootstrapper)
    python install_orchestrator.py --mode batch --config install_answers.yaml

    # Single phase
    python install_orchestrator.py --phase prereqs --sql-server SQL01.banco.pt

Exit codes:
    0 — todas as fases OK
    1 — prereqs fail
    2 — industry wizard fail
    3 — farm inventory fail
    4 — license missing/invalid
    5 — orchestration error (bad args, missing script)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEPLOY_DIR = Path(__file__).resolve().parent


@dataclass
class PhaseResult:
    phase: str
    status: str  # PASS | WARN | FAIL | SKIP
    exit_code: int
    message: str
    artifacts: List[str] = field(default_factory=list)


@dataclass
class OrchestrationReport:
    phases: List[PhaseResult] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return sum(1 for p in self.phases if p.status == "FAIL")

    @property
    def any_warnings(self) -> bool:
        return any(p.status == "WARN" for p in self.phases)


# ---------- Phase runners --------------------------------------------------


def run_prereqs(
    sql_server: str,
    sql_port: int,
    sql_user: str,
    ad_account: str,
    web_port: int,
    install_dir: str,
) -> PhaseResult:
    """Phase 1: prereqs_check.py via subprocess (mantém isolamento)."""
    cmd = [
        sys.executable, str(_DEPLOY_DIR / "prereqs_check.py"),
        "--sql-server", sql_server,
        "--sql-port", str(sql_port),
        "--sql-user", sql_user,
        "--ad-service-account", ad_account,
        "--web-port", str(web_port),
        "--install-dir", install_dir,
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return PhaseResult("prereqs", "FAIL", 1, "timeout (60s) — ambiente inacessivel?")

    # Parse JSON output
    try:
        doc = json.loads(result.stdout)
        summary = doc.get("summary", {})
        passed = summary.get("passed", 0)
        warnings = summary.get("warnings", 0)
        failed = summary.get("failed", 0)
    except json.JSONDecodeError:
        return PhaseResult(
            "prereqs", "FAIL", result.returncode or 1,
            f"prereqs_check.py output nao parseavel: {result.stdout[:120]}",
        )

    if failed > 0:
        return PhaseResult(
            "prereqs", "FAIL", 1,
            f"{failed} check(s) falharam ({passed} passed, {warnings} warnings)",
        )
    if warnings > 0:
        return PhaseResult(
            "prereqs", "WARN", 2,
            f"{warnings} warning(s) ({passed} passed, {failed} failed)",
        )
    return PhaseResult(
        "prereqs", "PASS", 0,
        f"all {passed} checks passed",
    )


def run_industry_wizard(
    output_dir: str,
    preset: Optional[str] = None,
    config_file: Optional[str] = None,
) -> PhaseResult:
    """Phase 3: industry_wizard.py via subprocess."""
    cmd = [
        sys.executable, str(_DEPLOY_DIR / "industry_wizard.py"),
        "--output-dir", output_dir,
    ]
    if preset:
        cmd.extend(["--preset", preset])
    if config_file:
        cmd.extend(["--config", config_file])

    try:
        result = subprocess.run(cmd, capture_output=False, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return PhaseResult("industry", "FAIL", 2, "industry wizard timeout (600s)")

    if result.returncode != 0:
        return PhaseResult(
            "industry", "FAIL", 2,
            f"industry wizard exit code {result.returncode}",
        )

    artifacts = []
    out_path = Path(output_dir)
    for name in ("client_context.yaml", "compliance_rules.yaml"):
        p = out_path / name
        if p.exists():
            artifacts.append(str(p))

    return PhaseResult(
        "industry", "PASS", 0,
        f"{len(artifacts)} config file(s) written",
        artifacts=artifacts,
    )


def run_farm_inventory(
    input_file: str,
    output_file: str,
    master_host: str,
    master_instance: str = "MSSQLSERVER",
    master_db: str = "WatcherDB_Intelligence",
    master_username: str = "sql_monitoring",
    validate_tcp: bool = False,
    strict: bool = False,
) -> PhaseResult:
    """Phase 4: farm_inventory_parser.py via subprocess."""
    cmd = [
        sys.executable, str(_DEPLOY_DIR / "farm_inventory_parser.py"),
        "--input", input_file,
        "--output", output_file,
        "--master-host", master_host,
        "--master-instance", master_instance,
        "--master-db", master_db,
        "--master-username", master_username,
    ]
    if validate_tcp:
        cmd.append("--validate-tcp")
    if strict:
        cmd.append("--strict")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return PhaseResult("farm_inventory", "FAIL", 3, "farm parser timeout (120s)")

    if result.returncode == 1:
        return PhaseResult(
            "farm_inventory", "FAIL", 3,
            f"parser errors: {result.stderr[:240]}",
        )

    out_p = Path(output_file)
    if not out_p.exists():
        return PhaseResult("farm_inventory", "FAIL", 3, f"servers.json não gerado em {output_file}")

    try:
        doc = json.loads(out_p.read_text(encoding="utf-8"))
        monitored_count = len(doc.get("monitored_servers", []))
    except (json.JSONDecodeError, OSError):
        monitored_count = 0

    return PhaseResult(
        "farm_inventory", "PASS", 0,
        f"{monitored_count} monitored servers parsed",
        artifacts=[str(out_p)],
    )


def check_license_presence(license_path: str) -> PhaseResult:
    """Phase 5: verify license.dat exists. Generation is out-of-band (vendor task)."""
    p = Path(license_path)
    if not p.exists():
        return PhaseResult(
            "license", "FAIL", 4,
            f"license.dat não encontrado em {license_path}. "
            f"Pedir ao vendor WatcherDB via access key + machine fingerprint.",
        )

    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        edition = doc.get("edition", "unknown")
        expires = doc.get("expires_at", "unknown")
    except (json.JSONDecodeError, OSError):
        return PhaseResult("license", "FAIL", 4, "license.dat mal-formado")

    return PhaseResult(
        "license", "PASS", 0,
        f"license.dat presente (edition={edition}, expires={expires})",
        artifacts=[str(p)],
    )


# ---------- Orchestration entry --------------------------------------------


def orchestrate_full(args: argparse.Namespace) -> OrchestrationReport:
    """Execute all phases em ordem."""
    report = OrchestrationReport()

    # Fase 1 — prereqs
    p1 = run_prereqs(
        sql_server=args.sql_server or "",
        sql_port=args.sql_port,
        sql_user=args.sql_user,
        ad_account=args.ad_service_account or "",
        web_port=args.web_port,
        install_dir=args.install_dir,
    )
    report.phases.append(p1)
    if p1.status == "FAIL":
        _print_report(report)
        return report

    # Fase 3 — industry wizard (Fase 2 = MSI, externo)
    p3 = run_industry_wizard(
        output_dir=args.config_dir or str(Path(args.install_dir) / "config"),
        preset=args.preset,
        config_file=args.wizard_config,
    )
    report.phases.append(p3)
    if p3.status == "FAIL":
        _print_report(report)
        return report

    # Fase 4 — farm inventory
    if args.farm_inventory:
        p4 = run_farm_inventory(
            input_file=args.farm_inventory,
            output_file=args.servers_json or str(Path(args.install_dir) / "config" / "servers.json"),
            master_host=args.master_host,
            master_instance=args.master_instance,
            master_db=args.master_db,
            master_username=args.master_username,
            validate_tcp=args.validate_tcp,
            strict=args.farm_strict,
        )
        report.phases.append(p4)
        if p4.status == "FAIL":
            _print_report(report)
            return report

    # Fase 5 — license check
    if args.license_path:
        p5 = check_license_presence(args.license_path)
        report.phases.append(p5)

    _print_report(report)
    return report


def _print_report(report: OrchestrationReport) -> None:
    print()
    print("=" * 70)
    print("Install Orchestration Report")
    print("=" * 70)
    for p in report.phases:
        symbol = {"PASS": "OK", "WARN": "!!", "FAIL": "XX", "SKIP": "--"}[p.status]
        print(f"  [{symbol}] {p.phase:20} {p.status:4} — {p.message}")
        for art in p.artifacts:
            print(f"            artefact: {art}")
    print("-" * 70)
    total = len(report.phases)
    failed = report.failed
    print(f"  {total - failed}/{total} phases OK" + (f" ({failed} failed)" if failed else ""))
    print("=" * 70)


# ---------- CLI -----------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["interactive", "batch", "single"], default="interactive")
    parser.add_argument("--phase", choices=["prereqs", "industry", "farm", "license", "all"], default="all")
    parser.add_argument("--install-dir", default=r"C:\Program Files\WatcherDB")
    parser.add_argument("--config-dir", help="Directorio para client_context/compliance_rules/servers.json (default: <install-dir>/config)")

    # Phase 1 (prereqs) args
    parser.add_argument("--sql-server", help="SQL Server hostname")
    parser.add_argument("--sql-port", type=int, default=1433)
    parser.add_argument("--sql-user", default="sql_monitoring")
    parser.add_argument("--ad-service-account", help="DOMAIN\\watcherdb_svc")
    parser.add_argument("--web-port", type=int, default=8433)

    # Phase 3 (industry) args
    parser.add_argument("--preset", choices=["banking_pt", "banking_eu_generic", "healthcare_us", "retail_eu"])
    parser.add_argument("--wizard-config", help="JSON/YAML file com answers non-interactive")

    # Phase 4 (farm) args
    parser.add_argument("--farm-inventory", help="CSV/JSON da farm SQL cliente")
    parser.add_argument("--servers-json", help="Output path (default: <config-dir>/servers.json)")
    parser.add_argument("--master-host", help="SQL Server com WatcherDB_Intelligence DB")
    parser.add_argument("--master-instance", default="MSSQLSERVER")
    parser.add_argument("--master-db", default="WatcherDB_Intelligence")
    parser.add_argument("--master-username", default="sql_monitoring")
    parser.add_argument("--validate-tcp", action="store_true")
    parser.add_argument("--farm-strict", action="store_true")

    # Phase 5 (license) args
    parser.add_argument("--license-path", help="Path para license.dat recebido do vendor")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Validar args minimos
    if args.phase in ("prereqs", "all") and not args.sql_server:
        print("WARN: --sql-server nao fornecido — Phase 1 prereqs checks SQL serao SKIP", file=sys.stderr)
    if args.phase == "farm" and not args.farm_inventory:
        print("ERROR: --farm-inventory required para phase=farm", file=sys.stderr)
        return 5

    # Single phase mode
    if args.phase != "all":
        if args.phase == "prereqs":
            result = run_prereqs(
                args.sql_server or "", args.sql_port, args.sql_user,
                args.ad_service_account or "", args.web_port, args.install_dir,
            )
        elif args.phase == "industry":
            result = run_industry_wizard(
                args.config_dir or str(Path(args.install_dir) / "config"),
                preset=args.preset, config_file=args.wizard_config,
            )
        elif args.phase == "farm":
            result = run_farm_inventory(
                args.farm_inventory,
                args.servers_json or str(Path(args.install_dir) / "config" / "servers.json"),
                args.master_host or args.sql_server or "",
                master_instance=args.master_instance,
                master_db=args.master_db,
                master_username=args.master_username,
                validate_tcp=args.validate_tcp,
                strict=args.farm_strict,
            )
        elif args.phase == "license":
            if not args.license_path:
                print("ERROR: --license-path required", file=sys.stderr)
                return 5
            result = check_license_presence(args.license_path)
        else:
            print(f"ERROR: unknown phase {args.phase}", file=sys.stderr)
            return 5

        report = OrchestrationReport(phases=[result])
        _print_report(report)
        return result.exit_code if result.status == "FAIL" else 0

    # Full orchestration
    report = orchestrate_full(args)
    if report.failed > 0:
        # Retornar exit code da primeira fase que falhou
        first_fail = next(p for p in report.phases if p.status == "FAIL")
        return first_fail.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
