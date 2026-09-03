"""Unit tests for watcherdb.licensing — Ed25519 signed license.dat."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from watcherdb.licensing import (
    FeatureRegistry,
    HardwareFingerprint,
    LicenseCorruptedError,
    LicenseExpiredError,
    LicenseFingerprintError,
    LicenseMissingError,
    LicenseSignatureError,
    LicenseTierMismatchError,
    LicenseValidator,
)
from watcherdb.licensing.generator import build_license

DEFAULT_FP = HardwareFingerprint(
    bios_uuid="AABBCCDD-1111-2222-3333-444455556666",
    cpu_id="BFEBFBFF00090672",
    hostname="CUSTOMER-SQL01",
)


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


@pytest.fixture
def validator(keypair):
    _, pub_path = keypair
    return LicenseValidator.from_public_key_file(pub_path)


def _make_license(
    priv: Ed25519PrivateKey,
    *,
    expires_in_days: int = 365,
    edition: str = "standard",
    fp: HardwareFingerprint = DEFAULT_FP,
    features: Dict[str, bool] | None = None,
    customer_id: str = "cust-001",
) -> Dict:
    return build_license(
        customer_id=customer_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        bios_uuid=fp.bios_uuid,
        cpu_id=fp.cpu_id,
        hostname=fp.hostname,
        edition=edition,
        tier=edition,
        features=features or {"core_monitoring": True, "intelligence_kpis": True},
        private_key=priv,
    )


def _write_license(path: Path, payload: Dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


# ---------- Happy path -----------------------------------------------------

def test_valid_license_loads_successfully(tmp_path, keypair, validator):
    priv, _ = keypair
    payload = _make_license(priv)
    lic_path = _write_license(tmp_path / "license.dat", payload)

    claims = validator.load(lic_path, current_fingerprint=DEFAULT_FP)

    assert claims.customer_id == "cust-001"
    assert claims.edition == "standard"
    assert claims.features["core_monitoring"] is True
    assert claims.days_until_expiry() > 360


def test_feature_registry_from_claims_respects_std_allowlist(tmp_path, keypair, validator):
    priv, _ = keypair
    # Malicious license tries to grant a Pro-only flag; the Std registry must drop it.
    payload = _make_license(priv, features={"core_monitoring": True, "cascade_intelligence": True})
    lic_path = _write_license(tmp_path / "license.dat", payload)

    claims = validator.load(lic_path, current_fingerprint=DEFAULT_FP)
    reg = FeatureRegistry.from_claims(claims)

    assert reg.is_enabled("core_monitoring") is True
    assert reg.is_enabled("cascade_intelligence") is False


# ---------- Standard failure modes ----------------------------------------

def test_missing_license_raises_missing_error(tmp_path, validator):
    with pytest.raises(LicenseMissingError):
        validator.load(tmp_path / "does-not-exist.dat", current_fingerprint=DEFAULT_FP)


def test_corrupted_json_raises_corrupted_error(tmp_path, validator):
    lic = tmp_path / "license.dat"
    lic.write_text("not a json { [", encoding="utf-8")
    with pytest.raises(LicenseCorruptedError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


def test_missing_fields_raises_corrupted_error(tmp_path, keypair, validator):
    priv, _ = keypair
    payload = _make_license(priv)
    del payload["customer_id"]
    lic = _write_license(tmp_path / "license.dat", payload)
    with pytest.raises(LicenseCorruptedError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


def test_expired_license_raises_expired_error(tmp_path, keypair, validator):
    priv, _ = keypair
    payload = _make_license(priv, expires_in_days=-1)
    lic = _write_license(tmp_path / "license.dat", payload)
    with pytest.raises(LicenseExpiredError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


def test_fingerprint_mismatch_raises_fingerprint_error(tmp_path, keypair, validator):
    priv, _ = keypair
    payload = _make_license(priv, fp=DEFAULT_FP)
    lic = _write_license(tmp_path / "license.dat", payload)

    # Change 2 of 3 factors on the running machine — should fail.
    wrong_fp = HardwareFingerprint(bios_uuid="OTHER", cpu_id="OTHER", hostname=DEFAULT_FP.hostname)
    with pytest.raises(LicenseFingerprintError):
        validator.load(lic, current_fingerprint=wrong_fp)


def test_pro_license_rejected_by_std_build(tmp_path, keypair, validator):
    priv, _ = keypair
    payload = _make_license(priv, edition="pro")
    lic = _write_license(tmp_path / "license.dat", payload)
    with pytest.raises(LicenseTierMismatchError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


# ---------- Fingerprint tolerance (2-of-3) --------------------------------

def test_single_factor_drift_still_accepts(tmp_path, keypair, validator):
    """Hostname rename alone must not lock the customer out."""
    priv, _ = keypair
    payload = _make_license(priv, fp=DEFAULT_FP)
    lic = _write_license(tmp_path / "license.dat", payload)

    drifted = HardwareFingerprint(
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname="RENAMED-HOST",
    )
    claims = validator.load(lic, current_fingerprint=drifted)
    assert claims.customer_id == "cust-001"


# ---------- Adversarial cases ---------------------------------------------

def test_adversarial_forged_signature_rejected(tmp_path, validator):
    """Attacker signs with their own Ed25519 key."""
    attacker = Ed25519PrivateKey.generate()
    payload = _make_license(attacker)
    lic = _write_license(tmp_path / "license.dat", payload)
    with pytest.raises(LicenseSignatureError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


def test_adversarial_tampered_expiry_rejected(tmp_path, keypair, validator):
    """Attacker edits expires_at after the licence was signed."""
    priv, _ = keypair
    payload = _make_license(priv, expires_in_days=30)
    # Extend expiry to ~10 years without re-signing.
    payload["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat().replace("+00:00", "Z")
    lic = _write_license(tmp_path / "license.dat", payload)
    with pytest.raises(LicenseSignatureError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


def test_adversarial_signature_replay_other_payload_rejected(tmp_path, keypair, validator):
    """Attacker takes a valid signature and grafts it onto a different payload."""
    priv, _ = keypair
    legit = _make_license(priv, customer_id="legit", expires_in_days=30)
    evil = _make_license(priv, customer_id="evil",  expires_in_days=3650)
    # Replace evil's signature with legit's — evil is now expires-far-future but bogus.
    evil["signature"] = legit["signature"]
    lic = _write_license(tmp_path / "license.dat", evil)
    with pytest.raises(LicenseSignatureError):
        validator.load(lic, current_fingerprint=DEFAULT_FP)


# ---------- Registry defaults ---------------------------------------------

def test_empty_registry_blocks_all_features():
    reg = FeatureRegistry.empty()
    for feature in reg.as_dict():
        assert reg.is_enabled(feature) is False


# ---------- B5: sql_servername fingerprint factor -------------------------

def test_fingerprint_sql_servername_ignored_when_license_has_none(tmp_path, keypair, validator):
    """License sem sql_servername (legacy) valida mesmo se host tem SERVERNAME."""
    priv, _ = keypair
    payload = _make_license(priv)  # sem sql_servername no payload
    lic_path = _write_license(tmp_path / "license.dat", payload)

    # Host tem sql_servername mas license nao — factor ignorado (backward compat)
    host_fp = HardwareFingerprint(
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname=DEFAULT_FP.hostname,
        sql_servername="SQLPRD01\\INSTANCE",
    )
    claims = validator.load(lic_path, current_fingerprint=host_fp)
    assert claims.customer_id == "cust-001"


def test_fingerprint_sql_servername_match_required_when_both_populated(tmp_path, keypair, validator):
    """Quando license + host ambos tem sql_servername, MUST match."""
    priv, _ = keypair
    # License com sql_servername
    payload = build_license(
        customer_id="bank-001",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname=DEFAULT_FP.hostname,
        sql_servername="SQLBANKPRD01",
        private_key=priv,
    )
    lic_path = _write_license(tmp_path / "license.dat", payload)

    # Host com SERVERNAME DIFERENTE — rejeitar
    wrong_host = HardwareFingerprint(
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname=DEFAULT_FP.hostname,
        sql_servername="SQLBANKPRD02",  # diferente
    )
    with pytest.raises(LicenseFingerprintError):
        validator.load(lic_path, current_fingerprint=wrong_host)

    # Host com SERVERNAME igual — aceitar
    right_host = HardwareFingerprint(
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname=DEFAULT_FP.hostname,
        sql_servername="SQLBANKPRD01",
    )
    claims = validator.load(lic_path, current_fingerprint=right_host)
    assert claims.customer_id == "bank-001"


# ---------- B5: industry + regulatory_regime parsing ----------------------

def test_license_industry_and_regime_parsed(tmp_path, keypair, validator):
    """License emitida com industry=banking + EBA/BdP tem campos expostos."""
    priv, _ = keypair
    payload = build_license(
        customer_id="bank-pt-001",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname=DEFAULT_FP.hostname,
        private_key=priv,
        industry="banking",
        regulatory_regime=["GDPR", "EBA", "BdP"],
        license_id="lic-2026-0001",
    )
    lic_path = _write_license(tmp_path / "license.dat", payload)

    claims = validator.load(lic_path, current_fingerprint=DEFAULT_FP)
    assert claims.industry == "banking"
    assert claims.regulatory_regime == ("GDPR", "EBA", "BdP")
    assert claims.license_id == "lic-2026-0001"


def test_license_without_industry_defaults_empty(tmp_path, keypair, validator):
    """Legacy license (sem industry/regime) carrega com defaults vazios."""
    priv, _ = keypair
    payload = _make_license(priv)  # sem industry
    lic_path = _write_license(tmp_path / "license.dat", payload)

    claims = validator.load(lic_path, current_fingerprint=DEFAULT_FP)
    assert claims.industry == ""
    assert claims.regulatory_regime == ()
    assert claims.license_id == ""
