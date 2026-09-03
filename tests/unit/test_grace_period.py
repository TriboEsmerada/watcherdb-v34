"""Unit tests for watcherdb.licensing.grace_period (FIND-20260424-005 follow-up)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from watcherdb.licensing.grace_period import (
    DEFAULT_GRACE_DAYS,
    GraceStatus,
    check_grace_period,
)


def test_grace_status_is_grace_active_properties():
    s1 = GraceStatus(state="NOT_INITIALIZED", install_date=None, days_since_install=0, days_remaining=60)
    s2 = GraceStatus(state="IN_GRACE", install_date=datetime.now(timezone.utc), days_since_install=5, days_remaining=55)
    s3 = GraceStatus(state="EXPIRED", install_date=datetime.now(timezone.utc), days_since_install=90, days_remaining=0)

    assert s1.is_grace_active is True
    assert s2.is_grace_active is True
    assert s3.is_grace_active is False
    assert s1.is_expired is False
    assert s3.is_expired is True


def test_first_run_creates_marker_returns_not_initialized(tmp_path: Path):
    status = check_grace_period(
        version="3.3.0", edition="standard",
        programdata_dir=tmp_path,
    )
    assert status.state == "NOT_INITIALIZED"
    assert status.days_since_install == 0
    assert status.days_remaining == DEFAULT_GRACE_DAYS
    # Marker file created
    marker = tmp_path / "install_marker.json"
    assert marker.exists()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["version"] == "3.3.0"
    assert data["edition"] == "standard"
    assert "install_date_utc" in data


def test_second_run_reads_marker_returns_in_grace(tmp_path: Path):
    # Write marker 10 days ago
    marker = tmp_path / "install_marker.json"
    past = datetime.now(timezone.utc) - timedelta(days=10)
    marker.write_text(json.dumps({
        "install_date_utc": past.isoformat().replace("+00:00", "Z"),
        "version": "3.3.0",
        "edition": "standard",
    }), encoding="utf-8")

    status = check_grace_period(programdata_dir=tmp_path)
    assert status.state == "IN_GRACE"
    assert status.days_since_install == 10
    assert status.days_remaining == DEFAULT_GRACE_DAYS - 10


def test_expired_marker_returns_expired(tmp_path: Path):
    marker = tmp_path / "install_marker.json"
    past = datetime.now(timezone.utc) - timedelta(days=90)
    marker.write_text(json.dumps({
        "install_date_utc": past.isoformat().replace("+00:00", "Z"),
        "version": "3.3.0",
    }), encoding="utf-8")

    status = check_grace_period(programdata_dir=tmp_path)
    assert status.state == "EXPIRED"
    assert status.days_since_install == 90
    assert status.days_remaining == 0
    assert status.is_expired is True


def test_malformed_marker_treated_as_missing(tmp_path: Path):
    marker = tmp_path / "install_marker.json"
    marker.write_text("not valid json", encoding="utf-8")

    status = check_grace_period(programdata_dir=tmp_path)
    # Malformed → treated como missing → NOT_INITIALIZED (creates new marker)
    assert status.state == "NOT_INITIALIZED"
    # Re-read should now be valid
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert "install_date_utc" in data


def test_custom_grace_days_override(tmp_path: Path):
    marker = tmp_path / "install_marker.json"
    past = datetime.now(timezone.utc) - timedelta(days=20)
    marker.write_text(json.dumps({
        "install_date_utc": past.isoformat().replace("+00:00", "Z"),
    }), encoding="utf-8")

    # 14-day grace (tighter than default 60d) — should be EXPIRED
    status = check_grace_period(programdata_dir=tmp_path, grace_days=14)
    assert status.state == "EXPIRED"

    # 30-day grace — still IN_GRACE
    status2 = check_grace_period(programdata_dir=tmp_path, grace_days=30)
    assert status2.state == "IN_GRACE"


def test_env_var_marker_path_override(tmp_path: Path, monkeypatch):
    custom_marker = tmp_path / "custom" / "my_marker.json"
    monkeypatch.setenv("WATCHERDB_INSTALL_MARKER_PATH", str(custom_marker))

    status = check_grace_period(version="test", edition="test")
    assert status.state == "NOT_INITIALIZED"
    assert custom_marker.exists()


def test_auto_initialize_false_does_not_create_marker(tmp_path: Path):
    status = check_grace_period(
        programdata_dir=tmp_path,
        auto_initialize=False,
    )
    assert status.state == "NOT_INITIALIZED"
    # Marker NOT created
    assert not (tmp_path / "install_marker.json").exists()


def test_timezone_z_suffix_parsed_correctly(tmp_path: Path):
    marker = tmp_path / "install_marker.json"
    marker.write_text(json.dumps({
        "install_date_utc": "2026-04-01T00:00:00Z",
    }), encoding="utf-8")

    # Use fixed 'now' para testar parse com Z suffix
    now = datetime(2026, 4, 11, tzinfo=timezone.utc)
    status = check_grace_period(programdata_dir=tmp_path, now=now)
    assert status.state == "IN_GRACE"
    assert status.days_since_install == 10
