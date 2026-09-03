"""Unit tests for watcherdb.licensing.manifest — Ed25519-signed updater."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from watcherdb.licensing.manifest import (
    ManifestDowngradeError,
    ManifestError,
    ManifestIncompatibleError,
    ManifestIntegrityError,
    ManifestProductMismatchError,
    PRODUCT_ID,
    build_manifest,
    sign_manifest,
    verify_manifest,
)
from watcherdb.licensing.exceptions import (
    LicenseCorruptedError,
    LicenseSignatureError,
)

CURRENT_VERSION = "3.3.0.0"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def keypair():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


@pytest.fixture
def bundle_zip(tmp_path: Path) -> Path:
    """A tiny file that pretends to be the update zip. manifest.build_manifest
    only reads size and SHA-256 — it never parses the content."""
    p = tmp_path / "update.zip"
    p.write_bytes(b"fake bundle payload" * 128)
    return p


def _write_manifest(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _signed_manifest(priv, zip_path, tmp_path, **overrides) -> tuple[Path, dict]:
    payload = build_manifest(
        version=overrides.pop("version", "3.3.1.0"),
        min_version=overrides.pop("min_version", "3.3.0.0"),
        zip_path=zip_path,
        file_entries=overrides.pop("file_entries", []),
        product=overrides.pop("product", PRODUCT_ID),
    )
    payload.update(overrides)
    signed = sign_manifest(payload, priv)
    path = _write_manifest(tmp_path / "manifest.json", signed)
    return path, signed


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_manifest_round_trip(tmp_path, keypair, bundle_zip):
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(priv, bundle_zip, tmp_path)

    claims = verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)

    assert claims.product == PRODUCT_ID
    assert claims.version == "3.3.1.0"
    assert claims.min_version == "3.3.0.0"
    assert claims.zip_size_bytes == bundle_zip.stat().st_size
    assert len(claims.zip_sha256) == 64


# ---------------------------------------------------------------------------
# Corruption / missing file modes
# ---------------------------------------------------------------------------

def test_missing_manifest_raises(tmp_path, keypair, bundle_zip):
    _, pub = keypair
    with pytest.raises(ManifestError):
        verify_manifest(tmp_path / "nope.json", pub, bundle_zip, CURRENT_VERSION)


def test_corrupted_json_raises(tmp_path, keypair, bundle_zip):
    _, pub = keypair
    bad = tmp_path / "manifest.json"
    bad.write_text("not json at all { [", encoding="utf-8")
    with pytest.raises(LicenseCorruptedError):
        verify_manifest(bad, pub, bundle_zip, CURRENT_VERSION)


def test_missing_fields_raises(tmp_path, keypair, bundle_zip):
    priv, pub = keypair
    manifest_path, signed = _signed_manifest(priv, bundle_zip, tmp_path)
    del signed["version"]
    _write_manifest(manifest_path, signed)
    with pytest.raises(LicenseCorruptedError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


def test_missing_update_zip_raises(tmp_path, keypair, bundle_zip):
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(priv, bundle_zip, tmp_path)
    bundle_zip.unlink()
    with pytest.raises(ManifestIntegrityError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


# ---------------------------------------------------------------------------
# Signature attacks
# ---------------------------------------------------------------------------

def test_forged_signature_rejected(tmp_path, keypair, bundle_zip):
    legit_priv, pub = keypair
    attacker = Ed25519PrivateKey.generate()
    manifest_path, _ = _signed_manifest(attacker, bundle_zip, tmp_path)  # signed w/ wrong key
    with pytest.raises(LicenseSignatureError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


def test_tampered_version_rejected(tmp_path, keypair, bundle_zip):
    priv, pub = keypair
    manifest_path, signed = _signed_manifest(priv, bundle_zip, tmp_path, version="3.3.1.0")
    # Attacker grants themselves a much newer version after the sign.
    signed["version"] = "99.99.0.0"
    _write_manifest(manifest_path, signed)
    with pytest.raises(LicenseSignatureError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


# ---------------------------------------------------------------------------
# Version policy
# ---------------------------------------------------------------------------

def test_downgrade_attack_rejected(tmp_path, keypair, bundle_zip):
    """Attacker serves a valid-but-older manifest to regress the install."""
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(priv, bundle_zip, tmp_path, version="3.2.5.0")
    with pytest.raises(ManifestDowngradeError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


def test_same_version_rejected(tmp_path, keypair, bundle_zip):
    """Applying the same version is not an upgrade."""
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(priv, bundle_zip, tmp_path, version=CURRENT_VERSION)
    with pytest.raises(ManifestDowngradeError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


def test_min_version_floor_enforced(tmp_path, keypair, bundle_zip):
    """An install older than the manifest's floor must refuse."""
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(
        priv, bundle_zip, tmp_path,
        version="3.3.5.0",
        min_version="3.3.4.0",
    )
    with pytest.raises(ManifestIncompatibleError):
        verify_manifest(manifest_path, pub, bundle_zip, current_version="3.3.0.0")


# ---------------------------------------------------------------------------
# Product / integrity
# ---------------------------------------------------------------------------

def test_wrong_product_rejected(tmp_path, keypair, bundle_zip):
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(
        priv, bundle_zip, tmp_path,
        product="watcherdb-v5-pro",
    )
    with pytest.raises(ManifestProductMismatchError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)


def test_zip_tampered_rejected(tmp_path, keypair, bundle_zip):
    """Attacker swaps the zip contents after the manifest was signed."""
    priv, pub = keypair
    manifest_path, _ = _signed_manifest(priv, bundle_zip, tmp_path)
    bundle_zip.write_bytes(b"malicious replacement")
    with pytest.raises(ManifestIntegrityError):
        verify_manifest(manifest_path, pub, bundle_zip, CURRENT_VERSION)
