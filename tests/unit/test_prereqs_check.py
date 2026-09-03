"""Unit tests for deploy.prereqs_check (B3 sprint install v0.2)."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_DEPLOY_DIR = Path(__file__).resolve().parent.parent.parent / "deploy"
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))

import prereqs_check as pc  # type: ignore[import-not-found]


# ---------- CheckResult + report dataclasses ------------------------------

def test_report_aggregation_counters():
    report = pc.PrereqsReport(results=[
        pc.CheckResult("CHK-1", "a", "PASS", "ok"),
        pc.CheckResult("CHK-2", "b", "WARN", "careful"),
        pc.CheckResult("CHK-3", "c", "FAIL", "bad"),
        pc.CheckResult("CHK-4", "d", "PASS", "ok"),
        pc.CheckResult("CHK-5", "e", "SKIP", "skipped"),
    ])
    assert report.passed == 2
    assert report.warned == 1
    assert report.failed == 1


# ---------- Individual check mocking --------------------------------------

def test_sql_tcp_reachable_success():
    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = None
        result = pc.check_sql_tcp_reachable("SQL01", 1433)
    assert result.status == "PASS"
    assert result.check_id == "CHK-02"


def test_sql_tcp_reachable_timeout():
    with patch("socket.create_connection", side_effect=socket.timeout):
        result = pc.check_sql_tcp_reachable("SQL01", 1433, timeout=0.1)
    assert result.status == "FAIL"
    assert "timeout" in result.message.lower()
    assert "firewall" in result.fix_hint.lower()


def test_sql_tcp_reachable_dns_failure():
    with patch("socket.create_connection", side_effect=socket.gaierror):
        result = pc.check_sql_tcp_reachable("SQL-BAD", 1433)
    assert result.status == "FAIL"
    assert "DNS" in result.message


def test_sql_tcp_reachable_skip_when_no_host():
    result = pc.check_sql_tcp_reachable("", 1433)
    assert result.status == "SKIP"


def test_port_available_skips_when_no_port():
    result = pc.check_port_available(0)
    assert result.status == "SKIP"


def test_port_available_pass_for_unused_port():
    # Audit 2026-08-19: a versao anterior fixava a 54321 com o comentario "high
    # ephemeral port almost surely free" — e' precisamente ao contrario. 54321 cai
    # DENTRO do intervalo dinamico do Windows (49152-65535), que e' de onde saem as
    # portas de origem das ligacoes de SAIDA. Bastou o servico WatcherDB abrir uma
    # ligacao ao SQL Server para o teste ficar vermelho sem nada estar mal.
    # Agora pedimos uma porta livre ao SO e libertamo-la — sem palpites.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]

    result = pc.check_port_available(porta)
    assert result.status == "PASS"
    assert str(porta) in result.message


def test_ad_account_skips_when_no_account():
    result = pc.check_ad_account("")
    assert result.status == "SKIP"


def test_ad_account_warns_when_missing_domain():
    result = pc.check_ad_account("watcherdb_svc")  # sem DOMAIN\
    assert result.status == "WARN"
    assert "domain prefix" in result.message.lower()


def test_python_version_pass_on_current_interpreter():
    # Py 3.11+ required; tests run on 3.14 per pytest output
    result = pc.check_python_version(min_major=3, min_minor=11)
    assert result.status == "PASS"


def test_python_version_warn_when_below_min():
    result = pc.check_python_version(min_major=99, min_minor=0)  # impossible min
    assert result.status == "WARN"


def test_disk_space_skip_when_no_install_dir():
    result = pc.check_disk_space("", min_mb=500)
    assert result.status == "SKIP"


def test_disk_space_pass_on_current_drive():
    # Current drive has > 500MB free almost certainly
    result = pc.check_disk_space(str(Path.cwd()), min_mb=1)
    assert result.status == "PASS"


# ---------- run_all + main CLI --------------------------------------------

def test_run_all_returns_expected_check_count():
    report = pc.run_all()
    # 8 checks total (01-08)
    assert len(report.results) == 8
    check_ids = {r.check_id for r in report.results}
    assert check_ids == {f"CHK-0{i}" for i in range(1, 9)}


def test_main_json_output(capsys):
    exit_code = pc.main(["--json"])
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert "summary" in doc
    assert "checks" in doc
    assert len(doc["checks"]) == 8
    # Exit code: 0/1/2 depending on environment
    assert exit_code in (0, 1, 2)


def test_main_skip_checks_without_args():
    """With no args most checks SKIP (ODBC + admin + python + disk still run)."""
    # Use run_all directly; main would print
    report = pc.run_all()
    skipped = sum(1 for r in report.results if r.status == "SKIP")
    # SQL/AD/port/install-dir skip = 4 + maybe SQL login skip
    assert skipped >= 4
