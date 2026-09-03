"""Unit tests for deploy.farm_inventory_parser (B7 sprint install v0.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make deploy/ importable for tests
_DEPLOY_DIR = Path(__file__).resolve().parent.parent.parent / "deploy"
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))

import farm_inventory_parser as fip  # type: ignore[import-not-found]


# ---------- Fixtures --------------------------------------------------------

@pytest.fixture
def csv_valid(tmp_path: Path) -> Path:
    csv_path = tmp_path / "farm.csv"
    csv_path.write_text(
        "host,instance,port,auth_mode,username,description,environment,priority,enabled,has_alwayson,ag_name,ag_listener\n"
        "SQL01.banco.pt,MSSQLSERVER,1433,windows,,Core Banking PRD,production,1,true,false,,\n"
        "SQL02.banco.pt,PROD,1433,sql,sql_monitoring,Risk Engine,production,1,true,false,,\n"
        "SQL03.banco.pt,AG,1433,sql,sql_monitoring,AG Listener,production,1,true,true,AG_Finance,AG_FIN_LISTENER\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def csv_missing_host(tmp_path: Path) -> Path:
    csv_path = tmp_path / "farm.csv"
    csv_path.write_text(
        "host,instance,port\n"
        ",MSSQLSERVER,1433\n"  # host vazio
        "SQL02,PROD,1433\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def csv_missing_required_column(tmp_path: Path) -> Path:
    csv_path = tmp_path / "farm.csv"
    csv_path.write_text(
        "host,instance\n"  # falta 'port'
        "SQL01,MSSQLSERVER\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def json_valid(tmp_path: Path) -> Path:
    json_path = tmp_path / "farm.json"
    json_path.write_text(
        json.dumps([
            {"host": "SQL01", "instance": "MSSQLSERVER", "port": 1433, "auth_mode": "windows"},
            {"host": "SQL02", "instance": "PROD", "port": 1433, "auth_mode": "sql", "username": "sql_monitoring"},
        ]),
        encoding="utf-8",
    )
    return json_path


# ---------- Happy path -----------------------------------------------------

def test_parse_csv_valid_returns_3_entries(csv_valid: Path):
    entries, issues = fip.parse_csv(csv_valid, master_username="sql_monitoring")
    assert len(entries) == 3
    assert len([i for i in issues if i.severity == "error"]) == 0

    # ID format
    assert entries[0].id == "SQL01_MSSQLSERVER"
    assert entries[1].id == "SQL02_PROD"

    # Windows auth entry
    assert entries[0].use_windows_auth is True
    assert entries[0].password == ""

    # SQL auth entry
    assert entries[1].use_windows_auth is False
    assert entries[1].password == fip.PASSWORD_PLACEHOLDER

    # AlwaysOn entry
    assert entries[2].has_alwayson is True
    assert entries[2].ag_name == "AG_Finance"


def test_parse_json_valid(json_valid: Path):
    entries, issues = fip.parse_json(json_valid, master_username="sql_monitoring")
    assert len(entries) == 2
    assert entries[0].use_windows_auth is True
    assert entries[1].password == fip.PASSWORD_PLACEHOLDER


# ---------- Failure modes --------------------------------------------------

def test_parse_csv_empty_host_produces_error(csv_missing_host: Path):
    entries, issues = fip.parse_csv(csv_missing_host, master_username="x")
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) >= 1
    assert any(i.field == "host" for i in errors)
    # Row 2 should have failed, row 3 should parse
    assert len(entries) == 1
    assert entries[0].host == "SQL02"


def test_parse_csv_missing_required_column_fails(csv_missing_required_column: Path):
    entries, issues = fip.parse_csv(csv_missing_required_column, master_username="x")
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert errors[0].field == "header"
    assert "port" in errors[0].message
    assert len(entries) == 0


def test_parse_invalid_auth_mode_warns_and_defaults_to_sql(tmp_path: Path):
    csv_path = tmp_path / "farm.csv"
    csv_path.write_text(
        "host,instance,port,auth_mode\n"
        "SQL01,MSSQLSERVER,1433,mixed\n",  # invalido
        encoding="utf-8",
    )
    entries, issues = fip.parse_csv(csv_path, master_username="sql_monitoring")
    warnings = [i for i in issues if i.severity == "warning"]
    assert any(i.field == "auth_mode" for i in warnings)
    assert len(entries) == 1
    assert entries[0].use_windows_auth is False  # defaulted to sql


def test_alwayson_without_ag_name_warns(tmp_path: Path):
    csv_path = tmp_path / "farm.csv"
    csv_path.write_text(
        "host,instance,port,has_alwayson,ag_name\n"
        "SQL01,AG,1433,true,\n",  # has_alwayson=true mas ag_name vazio
        encoding="utf-8",
    )
    entries, issues = fip.parse_csv(csv_path, master_username="x")
    warnings = [i for i in issues if i.severity == "warning"]
    assert any(i.field == "ag_name" for i in warnings)


# ---------- Master server + output ----------------------------------------

def test_build_master_server_windows_auth():
    master = fip.build_master_server(
        "SQLMASTER", instance="I01", use_windows_auth=True,
    )
    assert master["host"] == "SQLMASTER"
    assert master["instance"] == "I01"
    assert master["use_windows_auth"] is True
    assert master["password"] == ""
    assert master["username"] == ""
    assert master["server"] == "SQLMASTER\\I01"


def test_build_master_server_sql_auth():
    master = fip.build_master_server("SQLMASTER", username="sql_monitoring")
    assert master["use_windows_auth"] is False
    assert master["username"] == "sql_monitoring"
    assert master["password"] == fip.PASSWORD_PLACEHOLDER
    # Default instance MSSQLSERVER não aparece no server string
    assert master["server"] == "SQLMASTER"


def test_write_servers_json(tmp_path: Path, csv_valid: Path):
    entries, _ = fip.parse_csv(csv_valid, master_username="sql_monitoring")
    master = fip.build_master_server("SQLMASTER")
    out_path = tmp_path / "out" / "servers.json"
    fip.write_servers_json(out_path, master, entries)

    assert out_path.exists()
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert "master_server" in doc
    assert "monitored_servers" in doc
    assert len(doc["monitored_servers"]) == 3
    assert doc["master_server"]["host"] == "SQLMASTER"


# ---------- CLI integration ------------------------------------------------

def test_cli_end_to_end(tmp_path: Path, csv_valid: Path):
    out_path = tmp_path / "servers.json"
    exit_code = fip.main([
        "--input", str(csv_valid),
        "--output", str(out_path),
        "--master-host", "SQLMASTER",
        "--master-username", "sql_monitoring",
    ])
    assert exit_code == 0
    assert out_path.exists()
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(doc["monitored_servers"]) == 3


def test_cli_exits_1_on_errors(tmp_path: Path, csv_missing_required_column: Path):
    out_path = tmp_path / "servers.json"
    exit_code = fip.main([
        "--input", str(csv_missing_required_column),
        "--output", str(out_path),
        "--master-host", "SQLMASTER",
    ])
    assert exit_code == 1
    assert not out_path.exists()  # nao escreve em erro


def test_cli_strict_mode_fails_on_warnings(tmp_path: Path):
    csv_path = tmp_path / "farm.csv"
    csv_path.write_text(
        "host,instance,port,auth_mode\n"
        "SQL01,MSSQLSERVER,1433,mixed\n",  # warning: auth_mode invalido
        encoding="utf-8",
    )
    out_path = tmp_path / "servers.json"
    exit_code = fip.main([
        "--input", str(csv_path),
        "--output", str(out_path),
        "--master-host", "SQLMASTER",
        "--strict",
    ])
    assert exit_code == 1


def test_id_uppercase_short_hostname_from_fqdn():
    """FQDN should produce short hostname in ID (matches V1 convention)."""
    id_ = fip._build_id("sql01.banco.pt", "PROD")
    assert id_ == "SQL01_PROD"
