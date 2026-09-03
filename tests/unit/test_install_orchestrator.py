"""Unit tests for deploy.install_orchestrator (orchestration entry point v0.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_DEPLOY_DIR = Path(__file__).resolve().parent.parent.parent / "deploy"
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))

import install_orchestrator as orch  # type: ignore[import-not-found]


# ---------- PhaseResult + report aggregation ------------------------------

def test_orchestration_report_counts_failed():
    r = orch.OrchestrationReport(phases=[
        orch.PhaseResult("a", "PASS", 0, "ok"),
        orch.PhaseResult("b", "FAIL", 3, "bad"),
        orch.PhaseResult("c", "WARN", 0, "careful"),
    ])
    assert r.failed == 1
    assert r.any_warnings is True


# ---------- Phase wrappers (subprocess mocked) -----------------------------

def _mock_subprocess_run(returncode: int, stdout: str = "", stderr: str = ""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_run_prereqs_parses_json_output_pass():
    json_out = json.dumps({
        "summary": {"passed": 5, "warnings": 0, "failed": 0},
        "checks": [],
    })
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(0, stdout=json_out)):
        result = orch.run_prereqs("SQL01", 1433, "svc", "DOM\\acc", 8433, "C:\\X")
    assert result.status == "PASS"
    assert "5 checks passed" in result.message


def test_run_prereqs_detects_warnings():
    json_out = json.dumps({"summary": {"passed": 3, "warnings": 2, "failed": 0}, "checks": []})
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(2, stdout=json_out)):
        result = orch.run_prereqs("SQL01", 1433, "svc", "", 8433, "C:\\X")
    assert result.status == "WARN"
    assert "2 warning" in result.message


def test_run_prereqs_detects_failures():
    json_out = json.dumps({"summary": {"passed": 3, "warnings": 0, "failed": 2}, "checks": []})
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(1, stdout=json_out)):
        result = orch.run_prereqs("SQL01", 1433, "svc", "", 8433, "C:\\X")
    assert result.status == "FAIL"
    assert "2 check" in result.message


def test_run_prereqs_bad_json_output_is_fail():
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(1, stdout="not json")):
        result = orch.run_prereqs("SQL01", 1433, "svc", "", 8433, "C:\\X")
    assert result.status == "FAIL"
    assert "nao parseavel" in result.message


# ---------- Industry wizard wrapper ----------------------------------------

def test_run_industry_wizard_preset_pass(tmp_path: Path):
    # Write fake output files BEFORE running (subprocess mocked anyway)
    (tmp_path / "client_context.yaml").write_text("industry: retail\n", encoding="utf-8")
    (tmp_path / "compliance_rules.yaml").write_text("rules: {}\n", encoding="utf-8")

    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(0)):
        result = orch.run_industry_wizard(str(tmp_path), preset="retail_eu")
    assert result.status == "PASS"
    assert len(result.artifacts) == 2


def test_run_industry_wizard_failure():
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(1)):
        result = orch.run_industry_wizard("/tmp/nonexistent")
    assert result.status == "FAIL"
    assert "exit code 1" in result.message


# ---------- Farm inventory wrapper -----------------------------------------

def test_run_farm_inventory_pass(tmp_path: Path):
    inp = tmp_path / "farm.csv"
    inp.write_text("host,instance,port\nSQL01,PROD,1433\n", encoding="utf-8")
    out = tmp_path / "servers.json"
    out.write_text(json.dumps({
        "master_server": {"host": "M"},
        "monitored_servers": [{"host": "SQL01"}, {"host": "SQL02"}],
    }), encoding="utf-8")

    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(0)):
        result = orch.run_farm_inventory(str(inp), str(out), "MASTER")
    assert result.status == "PASS"
    assert "2 monitored" in result.message


def test_run_farm_inventory_parser_fail():
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(1, stderr="bad csv")):
        result = orch.run_farm_inventory("/tmp/x.csv", "/tmp/y.json", "MASTER")
    assert result.status == "FAIL"


def test_run_farm_inventory_missing_output(tmp_path: Path):
    # subprocess returns 0 but output file doesn't exist
    with patch("install_orchestrator.subprocess.run", return_value=_mock_subprocess_run(0)):
        result = orch.run_farm_inventory("/tmp/x.csv", str(tmp_path / "missing.json"), "MASTER")
    assert result.status == "FAIL"
    assert "não gerado" in result.message or "nao gerado" in result.message


# ---------- License presence check -----------------------------------------

def test_check_license_present(tmp_path: Path):
    lic = tmp_path / "license.dat"
    lic.write_text(json.dumps({
        "edition": "enterprise",
        "expires_at": "2027-04-24T00:00:00Z",
    }), encoding="utf-8")

    result = orch.check_license_presence(str(lic))
    assert result.status == "PASS"
    assert "enterprise" in result.message


def test_check_license_missing(tmp_path: Path):
    result = orch.check_license_presence(str(tmp_path / "nonexistent.dat"))
    assert result.status == "FAIL"
    assert "vendor" in result.message.lower()


def test_check_license_malformed(tmp_path: Path):
    lic = tmp_path / "license.dat"
    lic.write_text("not json", encoding="utf-8")
    result = orch.check_license_presence(str(lic))
    assert result.status == "FAIL"
    assert "mal-formado" in result.message


# ---------- CLI --------------------------------------------------------

def test_cli_single_phase_license_exits_5_without_path():
    exit_code = orch.main(["--phase", "license"])
    assert exit_code == 5


def test_cli_farm_phase_without_inventory_exits_5():
    exit_code = orch.main(["--phase", "farm"])
    assert exit_code == 5


def test_cli_single_phase_license_present(tmp_path: Path):
    lic = tmp_path / "license.dat"
    lic.write_text(json.dumps({"edition": "std", "expires_at": "2027-01-01"}), encoding="utf-8")
    exit_code = orch.main(["--phase", "license", "--license-path", str(lic)])
    assert exit_code == 0
