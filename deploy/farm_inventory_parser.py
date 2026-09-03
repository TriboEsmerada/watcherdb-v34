"""
farm_inventory_parser.py — SQL Server farm inventory → servers.json canonical.

Sprint install flow v0.2 B7 (FIND-20260424-001).

Aceita inventory cliente (CSV / JSON) + produz servers.json canonical
consumido por V1 collector (WatcherDB Intelligence).

Format input (CSV):
    host,instance,port,auth_mode,username,description,environment,priority,enabled,has_alwayson,ag_name,ag_listener
    SQL01.banco.pt,MSSQLSERVER,1433,windows,,Core Banking PRD,production,1,true,false,,
    SQL02.banco.pt,PROD,1433,sql,sql_monitoring,Risk Engine,production,1,true,false,,
    SQL03.banco.pt,AG,1433,sql,sql_monitoring,AG Listener,production,1,true,true,AG_Finance,AG_FIN_LISTENER

Format input (JSON): array de objectos com mesma shape.

Format output (servers.json canonical V1):
    {
      "master_server": {...},
      "monitored_servers": [...]
    }

Passwords:
    Por razoes de seguranca, CSV NAO deve conter passwords em plaintext.
    Parser emite placeholder "@ENCRYPT_AT_INSTALL@" na password — installer
    wizard (B2) recolhe interactivamente e substitui via credential_manager.

Usage:
    python farm_inventory_parser.py \
        --input farm.csv \
        --master-host SQLHDMASTER01 \
        --master-instance I01 \
        --master-username sql_monitoring \
        --output servers.json \
        [--validate-tcp]        # opcional: testar TCP reachability por entry
        [--skip-empty-rows]     # ignora linhas vazias
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Password placeholder — installer substitui via credential_manager
PASSWORD_PLACEHOLDER = "@ENCRYPT_AT_INSTALL@"

# Required headers em CSV
REQUIRED_COLUMNS = {"host", "instance", "port"}
# Optional headers com defaults
DEFAULT_COLUMNS = {
    "auth_mode": "sql",
    "username": "sql_monitoring",
    "description": "",
    "environment": "production",
    "priority": 1,
    "enabled": True,
    "has_alwayson": False,
    "ag_name": None,
    "ag_listener": None,
}


@dataclass
class ServerEntry:
    """Single monitored server entry — matches V1 servers.json schema."""
    id: str
    host: str
    instance: str
    port: int
    description: str
    environment: str
    priority: int
    enabled: bool
    use_windows_auth: bool
    username: str
    password: str
    driver: str
    has_alwayson: bool
    ag_name: Optional[str]
    ag_listener: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseIssue:
    """Validation issue para um row."""
    row_number: int
    field: str
    message: str
    severity: str = "warning"  # warning | error


@dataclass
class ParseResult:
    master_server: dict
    monitored_servers: List[ServerEntry] = field(default_factory=list)
    issues: List[ParseIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ---------- Parsing ---------------------------------------------------------

def _str_to_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().lower() in ("true", "1", "yes", "sim", "on", "t")


def _sanitize_hostname(host: str) -> str:
    """Strip whitespace, uppercase bare hostnames (preserve FQDN case)."""
    h = host.strip()
    return h


def _build_id(host: str, instance: str) -> str:
    """Construct unique server ID matching V1 convention: HOST_INSTANCE."""
    # Strip domain if FQDN (V1 convention uses short hostname em id)
    short = host.split(".")[0].upper()
    inst = instance.strip().upper() if instance else "DEFAULT"
    return f"{short}_{inst}"


def _parse_row(row: dict, row_number: int, master_username: str) -> tuple:
    """Parse CSV row into ServerEntry. Returns (entry | None, issues)."""
    issues = []

    # Required field checks
    host = str(row.get("host", "")).strip()
    if not host:
        issues.append(ParseIssue(row_number, "host", "host is required", "error"))
        return None, issues

    instance = str(row.get("instance", "") or "MSSQLSERVER").strip()
    try:
        port = int(str(row.get("port", 1433)).strip() or 1433)
        if not (1 <= port <= 65535):
            raise ValueError("port out of range")
    except ValueError:
        issues.append(ParseIssue(row_number, "port", f"invalid port: {row.get('port')}", "error"))
        return None, issues

    auth_mode_raw = str(row.get("auth_mode", "sql")).strip().lower()
    if auth_mode_raw not in ("sql", "windows"):
        issues.append(ParseIssue(
            row_number, "auth_mode",
            f"auth_mode must be 'sql' or 'windows' (got '{auth_mode_raw}'), assuming 'sql'",
            "warning",
        ))
        auth_mode_raw = "sql"
    use_windows_auth = auth_mode_raw == "windows"

    # If SQL auth, username required (default sql_monitoring)
    username = str(row.get("username", "") or master_username or "sql_monitoring").strip()
    if not use_windows_auth and not username:
        issues.append(ParseIssue(row_number, "username", "username required for sql auth", "error"))
        return None, issues

    # Defaults for optional fields
    description = str(row.get("description", "")).strip()
    environment = str(row.get("environment", "production")).strip().lower()
    if environment not in ("production", "staging", "development", "test", "dr"):
        issues.append(ParseIssue(
            row_number, "environment",
            f"non-standard environment '{environment}' (expected production/staging/dev/test/dr)",
            "warning",
        ))

    try:
        priority = int(str(row.get("priority", 1)).strip() or 1)
    except ValueError:
        priority = 1
        issues.append(ParseIssue(row_number, "priority", "invalid priority, defaulting to 1", "warning"))

    enabled = _str_to_bool(row.get("enabled", True))
    has_alwayson = _str_to_bool(row.get("has_alwayson", False))
    ag_name = str(row.get("ag_name", "") or "").strip() or None
    ag_listener = str(row.get("ag_listener", "") or "").strip() or None

    if has_alwayson and not ag_name:
        issues.append(ParseIssue(
            row_number, "ag_name",
            "has_alwayson=true but ag_name empty",
            "warning",
        ))

    entry = ServerEntry(
        id=_build_id(host, instance),
        host=_sanitize_hostname(host),
        instance=instance,
        port=port,
        description=description,
        environment=environment,
        priority=priority,
        enabled=enabled,
        use_windows_auth=use_windows_auth,
        username=username if not use_windows_auth else "",
        password="" if use_windows_auth else PASSWORD_PLACEHOLDER,
        driver="SQL Server",
        has_alwayson=has_alwayson,
        ag_name=ag_name,
        ag_listener=ag_listener,
    )
    return entry, issues


def _validate_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    """Optional TCP reachability check (best-effort, non-blocking)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, socket.gaierror, OSError):
        return False


def parse_csv(
    input_path: Path,
    master_username: str,
    *,
    skip_empty_rows: bool = True,
    validate_tcp: bool = False,
) -> tuple:
    """Parse CSV file. Returns (list[ServerEntry], list[ParseIssue])."""
    entries = []
    issues = []

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            issues.append(ParseIssue(0, "header", "empty CSV or missing header", "error"))
            return entries, issues

        missing_required = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_required:
            issues.append(ParseIssue(
                0, "header",
                f"missing required columns: {sorted(missing_required)}",
                "error",
            ))
            return entries, issues

        for row_idx, row in enumerate(reader, start=2):  # +1 header, +1 1-based
            if skip_empty_rows and not any(v and v.strip() for v in row.values()):
                continue
            entry, row_issues = _parse_row(row, row_idx, master_username)
            issues.extend(row_issues)
            if entry is None:
                continue

            if validate_tcp:
                if not _validate_tcp(entry.host, entry.port):
                    issues.append(ParseIssue(
                        row_idx, "tcp",
                        f"TCP unreachable: {entry.host}:{entry.port}",
                        "warning",
                    ))

            entries.append(entry)

    return entries, issues


def parse_json(
    input_path: Path,
    master_username: str,
    *,
    validate_tcp: bool = False,
) -> tuple:
    """Parse JSON array file."""
    entries = []
    issues = []

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        issues.append(ParseIssue(0, "json", f"invalid JSON: {e}", "error"))
        return entries, issues

    if not isinstance(data, list):
        issues.append(ParseIssue(0, "json", "expected top-level JSON array", "error"))
        return entries, issues

    for row_idx, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            issues.append(ParseIssue(row_idx, "json", "row is not an object", "error"))
            continue
        entry, row_issues = _parse_row(row, row_idx, master_username)
        issues.extend(row_issues)
        if entry is None:
            continue

        if validate_tcp:
            if not _validate_tcp(entry.host, entry.port):
                issues.append(ParseIssue(
                    row_idx, "tcp",
                    f"TCP unreachable: {entry.host}:{entry.port}",
                    "warning",
                ))

        entries.append(entry)

    return entries, issues


# ---------- Master server generation ---------------------------------------

def build_master_server(
    host: str,
    *,
    instance: str = "MSSQLSERVER",
    port: int = 1433,
    database: str = "WatcherDB_Intelligence",
    description: str = "WatcherDB Intelligence master",
    environment: str = "production",
    use_windows_auth: bool = False,
    username: str = "sql_monitoring",
) -> dict:
    """Build master_server block matching V1 schema."""
    server_str = f"{host}\\{instance}" if instance and instance.upper() != "MSSQLSERVER" else host
    return {
        "server": server_str,
        "database": database,
        "host": host,
        "instance": instance,
        "port": port,
        "description": description,
        "environment": environment,
        "priority": 1,
        "use_windows_auth": use_windows_auth,
        "driver": "SQL Server",
        "username": username if not use_windows_auth else "",
        "password": "" if use_windows_auth else PASSWORD_PLACEHOLDER,
    }


# ---------- Output writer --------------------------------------------------

def write_servers_json(
    output_path: Path,
    master_server: dict,
    monitored: List[ServerEntry],
) -> None:
    """Write servers.json canonical format."""
    doc = {
        "master_server": master_server,
        "monitored_servers": [e.to_dict() for e in monitored],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------- CLI -------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="CSV ou JSON file com farm inventory")
    parser.add_argument("--output", type=Path, default=Path("servers.json"))
    parser.add_argument("--master-host", required=True, help="Hostname do SQL Server com WatcherDB_Intelligence DB")
    parser.add_argument("--master-instance", default="MSSQLSERVER")
    parser.add_argument("--master-port", type=int, default=1433)
    parser.add_argument("--master-db", default="WatcherDB_Intelligence")
    parser.add_argument("--master-username", default="sql_monitoring")
    parser.add_argument("--master-windows-auth", action="store_true")
    parser.add_argument("--master-description", default="WatcherDB Intelligence master")
    parser.add_argument("--validate-tcp", action="store_true", help="Testar TCP reachability por entry")
    parser.add_argument("--skip-empty-rows", action="store_true", default=True)
    parser.add_argument("--strict", action="store_true", help="Fail if any row has warnings (default: errors only)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 2

    # Format detection por extension
    suffix = args.input.suffix.lower()
    if suffix == ".csv":
        entries, issues = parse_csv(
            args.input, args.master_username,
            skip_empty_rows=args.skip_empty_rows,
            validate_tcp=args.validate_tcp,
        )
    elif suffix == ".json":
        entries, issues = parse_json(
            args.input, args.master_username,
            validate_tcp=args.validate_tcp,
        )
    else:
        print(f"ERROR: unsupported input format '{suffix}' (use .csv ou .json)", file=sys.stderr)
        return 2

    # Report issues
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    for issue in issues:
        prefix = "ERROR" if issue.severity == "error" else "WARN"
        print(f"{prefix} [row {issue.row_number}] {issue.field}: {issue.message}", file=sys.stderr)

    if errors:
        print(f"\nFAIL: {len(errors)} error(s), {len(warnings)} warning(s). Fix errors and re-run.", file=sys.stderr)
        return 1

    if args.strict and warnings:
        print(f"\nFAIL (strict mode): {len(warnings)} warning(s). Re-run without --strict to allow.", file=sys.stderr)
        return 1

    if not entries:
        print("ERROR: no valid server entries parsed", file=sys.stderr)
        return 1

    # Build master + write
    master = build_master_server(
        args.master_host,
        instance=args.master_instance,
        port=args.master_port,
        database=args.master_db,
        description=args.master_description,
        use_windows_auth=args.master_windows_auth,
        username=args.master_username,
    )
    write_servers_json(args.output, master, entries)

    print(f"\nWrote {args.output} ({len(entries)} monitored servers)")
    print(f"  warnings: {len(warnings)}")
    print(f"  master:   {master['server']} / {master['database']}")
    print(f"\nNote: passwords sao placeholder '{PASSWORD_PLACEHOLDER}' — installer wizard substitui.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
