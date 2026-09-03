"""Unit tests for watcherdb.licensing.startup_guard (B6 sprint install v0.2)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from watcherdb.licensing import HardwareFingerprint
from watcherdb.licensing.generator import build_license
from watcherdb.licensing.startup_guard import (
    EVENT_ID_LICENSE_EXPIRY_WARNING,
    EVENT_ID_LICENSE_FAILED,
    EVENT_ID_LICENSE_OK,
    validate_and_enforce,
)

DEFAULT_FP = HardwareFingerprint(
    bios_uuid="AABBCCDD-1111-2222-3333-444455556666",
    cpu_id="BFEBFBFF00090672",
    hostname="CUSTOMER-SQL01",
)


@pytest.fixture(autouse=True)
def _modo_de_licenca_estrito(monkeypatch):
    """Fixa o modo ESTRITO, em vez de o herdar do ambiente.

    Estes testes asserem comportamento fail-close: sem licenca valida, o
    servico tem de sair com SystemExit. O modo vem de WATCHERDB_LICENSE_ENFORCE
    e o default do produto e' `strict` -- mas *default* nao e' *garantido*: uma
    consola onde alguem tenha exportado `advisory` (para correr o bundle a mao,
    por exemplo) desarma tres testes de seguranca de uma vez.

    Aconteceu a 2026-08-20: um `$env:WATCHERDB_LICENSE_ENFORCE="advisory"`
    deixado numa sessao de PowerShell propagou-se ao pytest e abortou o gate de
    release com "3 falhas NOVAS" que nao existiam no codigo. O gate fez bem o
    seu trabalho; os testes e' que nao deviam depender do ambiente.

    Um teste que verifica que algo FALHA quando deve nunca pode ficar a merce
    de uma variavel que desliga precisamente esse algo. O teste que quer
    `advisory` declara-o no proprio corpo e sobrepoe-se a esta fixture.
    """
    monkeypatch.setenv("WATCHERDB_LICENSE_ENFORCE", "strict")


@pytest.fixture
def tmp_keypair(tmp_path: Path):
    """Generate throwaway keypair + write public key to deploy/keys layout."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    key_dir = tmp_path / "deploy" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    pub_path = key_dir / "ed25519_public.pem"
    pub_path.write_bytes(
        pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv, pub_path, tmp_path  # tmp_path = base_dir


def _write_license(tmp_path: Path, priv: Ed25519PrivateKey, **overrides) -> Path:
    kwargs = dict(
        customer_id="test-customer",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        bios_uuid=DEFAULT_FP.bios_uuid,
        cpu_id=DEFAULT_FP.cpu_id,
        hostname=DEFAULT_FP.hostname,
        edition="standard",
        tier="standard",
        private_key=priv,
    )
    kwargs.update(overrides)
    payload = build_license(**kwargs)
    lic_path = tmp_path / "license.dat"
    lic_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return lic_path


# ---------- PYTEST bypass preserved ---------------------------------------

def test_startup_guard_pytest_current_test_returns_empty(tmp_keypair):
    """Quando PYTEST_CURRENT_TEST set (sempre em pytest), retorna empty + None."""
    _, _, base_dir = tmp_keypair
    # PYTEST_CURRENT_TEST ja presente automaticamente durante pytest
    registry, claims = validate_and_enforce(
        service_name="test_svc",
        base_dir=base_dir,
    )
    assert registry is not None
    assert claims is None
    # Empty registry blocks all features
    assert registry.is_enabled("core_monitoring") is False


# ---------- Strict mode failure behavior (simulated sem PYTEST_CURRENT_TEST) --

def test_startup_guard_strict_fails_on_missing_license_post_grace(tmp_keypair, monkeypatch):
    """Strict + no license.dat + grace expired = SystemExit.

    FIND-20260424-005 follow-up: grace period de 60d permite startup sem license
    nos primeiros 60d post-install. Este teste simula grace expirado via mocking
    de check_grace_period.
    """
    from unittest.mock import patch
    from watcherdb.licensing.grace_period import GraceStatus
    from datetime import datetime, timezone, timedelta

    _, _, base_dir = tmp_keypair
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("WATCHERDB_LICENSE_PATH", str(base_dir / "nonexistent.dat"))
    monkeypatch.setenv("WATCHERDB_PUBLIC_KEY_PATH", str(base_dir / "deploy" / "keys" / "ed25519_public.pem"))

    # Mock grace period to EXPIRED (install > 60 days ago)
    expired_grace = GraceStatus(
        state="EXPIRED",
        install_date=datetime.now(timezone.utc) - timedelta(days=90),
        days_since_install=90,
        days_remaining=0,
    )
    with patch("watcherdb.licensing.grace_period.check_grace_period", return_value=expired_grace):
        with pytest.raises(SystemExit) as excinfo:
            validate_and_enforce(service_name="test_svc", base_dir=base_dir)
    assert "license validation failed" in str(excinfo.value)


def test_startup_guard_grace_period_allows_missing_license(tmp_keypair, monkeypatch, tmp_path):
    """Missing license + within grace period (first 60d) = allow start, log warning."""
    _, _, base_dir = tmp_keypair
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("WATCHERDB_LICENSE_PATH", str(base_dir / "nonexistent.dat"))
    monkeypatch.setenv("WATCHERDB_PUBLIC_KEY_PATH", str(base_dir / "deploy" / "keys" / "ed25519_public.pem"))
    # Override install marker path para tmp_path (avoid polluting real ProgramData)
    monkeypatch.setenv("WATCHERDB_INSTALL_MARKER_PATH", str(tmp_path / "install_marker.json"))

    registry, claims = validate_and_enforce(service_name="test_svc", base_dir=base_dir)
    # Grace period active → empty registry + no claims, BUT no SystemExit
    assert claims is None
    assert registry.is_enabled("core_monitoring") is False
    # Marker deve ter sido criado
    assert (tmp_path / "install_marker.json").exists()


def test_startup_guard_signature_error_ignores_grace(tmp_keypair, monkeypatch, tmp_path):
    """Non-missing license errors (signature, fingerprint, expired) NEVER get grace.

    Grace period so aplica em LicenseMissingError. Qualquer outro LicenseError
    fail-close em strict mode — security-critical.
    """
    from unittest.mock import patch
    from watcherdb.licensing.exceptions import LicenseSignatureError

    priv, _, base_dir = tmp_keypair
    lic_path = _write_license(base_dir, priv)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("WATCHERDB_LICENSE_PATH", str(lic_path))
    monkeypatch.setenv("WATCHERDB_INSTALL_MARKER_PATH", str(tmp_path / "install_marker.json"))

    # Make grace period ACTIVE (we're within 60d) — should still fail-close on signature error
    with patch("watcherdb.licensing.fingerprint.build_fingerprint", return_value=DEFAULT_FP):
        with patch.object(
            __import__("watcherdb.licensing.validator", fromlist=["LicenseValidator"]).LicenseValidator,
            "load",
            side_effect=LicenseSignatureError("forged signature"),
        ):
            with pytest.raises(SystemExit) as excinfo:
                validate_and_enforce(service_name="test_svc", base_dir=base_dir)
    assert "license validation failed" in str(excinfo.value)


def test_startup_guard_advisory_returns_empty_on_missing(tmp_keypair, monkeypatch):
    """Advisory mode + no license.dat = (empty_registry, None) + warning log."""
    _, _, base_dir = tmp_keypair
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("WATCHERDB_LICENSE_ENFORCE", "advisory")
    monkeypatch.setenv("WATCHERDB_LICENSE_PATH", str(base_dir / "nonexistent.dat"))
    monkeypatch.setenv("WATCHERDB_PUBLIC_KEY_PATH", str(base_dir / "deploy" / "keys" / "ed25519_public.pem"))

    registry, claims = validate_and_enforce(service_name="test_svc", base_dir=base_dir)
    assert claims is None
    assert registry.is_enabled("core_monitoring") is False  # empty


# ---------- Success path + industry/regime audit --------------------------

def test_startup_guard_success_returns_registry_and_claims(tmp_keypair, monkeypatch):
    """Valid license + valid pubkey + valid fingerprint = (registry, claims)."""
    priv, _, base_dir = tmp_keypair
    lic_path = _write_license(
        base_dir, priv,
        industry="banking",
        regulatory_regime=["GDPR", "EBA", "BdP"],
        license_id="lic-2026-0001",
    )
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("WATCHERDB_LICENSE_PATH", str(lic_path))

    # Mock fingerprint to match license (tests run on dev machine with different fp)
    from unittest.mock import patch
    with patch("watcherdb.licensing.fingerprint.build_fingerprint", return_value=DEFAULT_FP):
        registry, claims = validate_and_enforce(
            service_name="test_svc",
            base_dir=base_dir,
        )

    assert claims is not None
    assert claims.customer_id == "test-customer"
    assert claims.industry == "banking"
    assert claims.regulatory_regime == ("GDPR", "EBA", "BdP")
    assert claims.license_id == "lic-2026-0001"
    assert registry.is_enabled("core_monitoring") is True


# ---------- Edition mismatch rejected --------------------------------------

def test_startup_guard_edition_mismatch_strict_fails(tmp_keypair, monkeypatch):
    """License emitida para pro + build accepts standard = SystemExit."""
    priv, _, base_dir = tmp_keypair
    lic_path = _write_license(base_dir, priv, edition="pro", tier="pro")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("WATCHERDB_LICENSE_PATH", str(lic_path))

    from unittest.mock import patch
    with patch("watcherdb.licensing.fingerprint.build_fingerprint", return_value=DEFAULT_FP):
        with pytest.raises(SystemExit):
            validate_and_enforce(
                service_name="test_svc",
                accepted_edition="standard",
                base_dir=base_dir,
            )


# ---------- Event ID constants ---------------------------------------------

def test_event_id_constants_stable():
    """Event IDs should not change between versions — used by SIEM/audit collectors."""
    assert EVENT_ID_LICENSE_OK == 1000
    assert EVENT_ID_LICENSE_FAILED == 1001
    assert EVENT_ID_LICENSE_EXPIRY_WARNING == 1002
