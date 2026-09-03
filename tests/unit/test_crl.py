"""Unit tests for watcherdb.licensing.crl (B5.2 — FIND-20260424-005 sub-task)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from watcherdb.licensing.crl import (
    CRL,
    CRLEntry,
    LicenseRevokedError,
    load_crl,
    load_crl_safe,
    load_public_key_from_pem,
)
from watcherdb.licensing.exceptions import LicenseError, LicenseSignatureError
from watcherdb.licensing.generator import build_crl


@pytest.fixture
def keypair(tmp_path: Path):
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_path = tmp_path / "pub.pem"
    pub_path.write_bytes(
        pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv, pub_path


def _write_crl(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


# ---------- CRLEntry / CRL dataclasses -------------------------------------

def test_crl_entry_to_from_dict_roundtrip():
    e = CRLEntry(
        license_id="abc-123",
        revoked_at=datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc),
        reason="contract terminated",
    )
    d = e.to_dict()
    assert d["license_id"] == "abc-123"
    assert d["revoked_at"].endswith("Z")
    e2 = CRLEntry.from_dict(d)
    assert e2.license_id == e.license_id
    assert e2.reason == e.reason


def test_crl_is_revoked():
    crl = CRL(
        version=1,
        issued_at=datetime.now(timezone.utc),
        entries=[
            CRLEntry("uuid-1", datetime.now(timezone.utc), "reason-1"),
            CRLEntry("uuid-2", datetime.now(timezone.utc), "reason-2"),
        ],
    )
    assert crl.is_revoked("uuid-1") is True
    assert crl.is_revoked("uuid-2") is True
    assert crl.is_revoked("uuid-NOT-IN-LIST") is False
    assert crl.is_revoked("") is False  # empty license_id never revoked


def test_crl_find_returns_entry():
    crl = CRL(version=1, issued_at=datetime.now(timezone.utc), entries=[
        CRLEntry("abc", datetime.now(timezone.utc), "test reason"),
    ])
    entry = crl.find("abc")
    assert entry is not None
    assert entry.reason == "test reason"
    assert crl.find("nonexistent") is None


# ---------- build_crl + load_crl roundtrip ---------------------------------

def test_build_and_load_crl_roundtrip(tmp_path: Path, keypair):
    priv, pub_path = keypair
    revocations = [
        {"license_id": "abc-123", "reason": "test contract termination"},
        {"license_id": "def-456", "reason": "hardware migration unauthorized"},
    ]
    payload = build_crl(revocations, priv)
    crl_path = _write_crl(tmp_path / "revoked_licenses.json", payload)

    pub_key = load_public_key_from_pem(pub_path)
    crl = load_crl(pub_key, crl_path=crl_path)

    assert crl is not None
    assert crl.version == 1
    assert len(crl.entries) == 2
    assert crl.is_revoked("abc-123") is True
    assert crl.is_revoked("def-456") is True
    assert crl.is_revoked("not-revoked") is False


def test_load_crl_returns_none_when_absent(tmp_path: Path, keypair):
    _, pub_path = keypair
    pub_key = load_public_key_from_pem(pub_path)

    result = load_crl(pub_key, crl_path=tmp_path / "does-not-exist.json")
    assert result is None


def test_load_crl_signature_invalid_raises(tmp_path: Path, keypair):
    priv, pub_path = keypair
    revocations = [{"license_id": "abc", "reason": "test"}]
    payload = build_crl(revocations, priv)

    # Tamper: change license_id depois de sign
    payload["revocations"][0]["license_id"] = "TAMPERED"
    crl_path = _write_crl(tmp_path / "revoked_licenses.json", payload)

    pub_key = load_public_key_from_pem(pub_path)
    with pytest.raises(LicenseSignatureError):
        load_crl(pub_key, crl_path=crl_path)


def test_load_crl_unsupported_version_raises(tmp_path: Path, keypair):
    priv, pub_path = keypair
    payload = build_crl([], priv, version=999)
    crl_path = _write_crl(tmp_path / "revoked_licenses.json", payload)

    pub_key = load_public_key_from_pem(pub_path)
    with pytest.raises(LicenseError, match="version 999 unsupported"):
        load_crl(pub_key, crl_path=crl_path)


# ---------- load_crl_safe (no-raise wrapper) -------------------------------

def test_load_crl_safe_returns_none_on_signature_invalid(tmp_path: Path, keypair):
    """Wrapper safe NAO levanta — log warning + return None (avoid bricking)."""
    priv, pub_path = keypair
    payload = build_crl([{"license_id": "x"}], priv)
    payload["revocations"][0]["license_id"] = "TAMPERED"
    crl_path = _write_crl(tmp_path / "revoked_licenses.json", payload)

    pub_key = load_public_key_from_pem(pub_path)
    result = load_crl_safe(pub_key, crl_path=crl_path)
    assert result is None  # Doesnt raise


def test_load_crl_safe_returns_crl_when_valid(tmp_path: Path, keypair):
    priv, pub_path = keypair
    payload = build_crl([{"license_id": "valid-uuid"}], priv)
    crl_path = _write_crl(tmp_path / "revoked_licenses.json", payload)

    pub_key = load_public_key_from_pem(pub_path)
    crl = load_crl_safe(pub_key, crl_path=crl_path)
    assert crl is not None
    assert crl.is_revoked("valid-uuid") is True


# ---------- Path resolution -----------------------------------------------

def test_crl_path_env_override(tmp_path: Path, keypair, monkeypatch):
    priv, pub_path = keypair
    custom_path = tmp_path / "custom_crl.json"
    payload = build_crl([{"license_id": "uuid-x"}], priv)
    _write_crl(custom_path, payload)

    monkeypatch.setenv("WATCHERDB_CRL_PATH", str(custom_path))

    pub_key = load_public_key_from_pem(pub_path)
    crl = load_crl(pub_key)  # No explicit path — usa env var
    assert crl is not None
    assert crl.is_revoked("uuid-x") is True


# ---------- LicenseRevokedError ---------------------------------------------

def test_license_revoked_error_is_license_error():
    """LicenseRevokedError deve herdar LicenseError para apanhar em except hierarchy."""
    err = LicenseRevokedError("test")
    assert isinstance(err, LicenseError)


# ---------- Empty CRL ---------------------------------------------------

def test_empty_revocations_list_is_valid(tmp_path: Path, keypair):
    """CRL pode ser emitida vazia (vendor publica CRL inicial sem revocations)."""
    priv, pub_path = keypair
    payload = build_crl([], priv)
    crl_path = _write_crl(tmp_path / "revoked_licenses.json", payload)

    pub_key = load_public_key_from_pem(pub_path)
    crl = load_crl(pub_key, crl_path=crl_path)
    assert crl is not None
    assert len(crl.entries) == 0
    assert crl.is_revoked("any-uuid") is False


def test_revocations_skip_entries_without_license_id(tmp_path: Path, keypair):
    """build_crl filtra entries sem license_id."""
    priv, pub_path = keypair
    revocations = [
        {"license_id": "valid-uuid", "reason": "test"},
        {"license_id": "", "reason": "garbage"},  # filtered out
        {"reason": "no license_id"},  # filtered out
    ]
    payload = build_crl(revocations, priv)
    assert len(payload["revocations"]) == 1
