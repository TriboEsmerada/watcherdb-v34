"""
license.dat parser + Ed25519 signature verifier.

The on-disk format is JSON of the form::

    {
      "customer_id":   "<uuid>",
      "edition":       "standard",
      "tier":          "standard",
      "features":      {"core_monitoring": true, "intelligence_kpis": true, ...},
      "issued_at":     "2026-04-22T00:00:00Z",
      "expires_at":    "2027-04-22T00:00:00Z",
      "hw_fingerprint": {"bios_uuid": "...", "cpu_id": "...", "hostname": "..."},
      "signature":     "<base64 ed25519 signature over the JSON payload w/o signature key>"
    }

`LicenseValidator.load()` returns a `LicenseClaims` object on success and
raises a specific subclass of `LicenseError` on every failure mode. The
caller (watcherdb_main lifespan) decides whether to refuse startup or run
in reduced mode.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .exceptions import (
    LicenseCorruptedError,
    LicenseExpiredError,
    LicenseFingerprintError,
    LicenseMissingError,
    LicenseSignatureError,
    LicenseTierMismatchError,
)
from .fingerprint import HardwareFingerprint, build_fingerprint

logger = logging.getLogger(__name__)

# Edition identifier that V3.3 accepts. A license issued for Pro (tier="pro")
# will be rejected even if its signature is valid — the right product for the
# customer was not the one they installed.
ACCEPTED_EDITION = "standard"

_REQUIRED_FIELDS = {"customer_id", "edition", "tier", "features", "issued_at", "expires_at", "hw_fingerprint", "signature"}


@dataclass(frozen=True)
class LicenseClaims:
    customer_id: str
    edition: str
    tier: str
    features: Dict[str, bool]
    issued_at: datetime
    expires_at: datetime
    hw_fingerprint: HardwareFingerprint
    # Industry/compliance fields added 2026-04-24 (FIND-20260424-001 B5).
    # Optional: legacy licenses sem estes campos continuam validos.
    industry: str = ""
    regulatory_regime: tuple = ()
    license_id: str = ""  # UUID unico por emissao — para CRL futuro
    raw_payload: Dict[str, Any] = field(repr=False, default_factory=dict)

    def days_until_expiry(self, now: Optional[datetime] = None) -> int:
        now = now or datetime.now(timezone.utc)
        return (self.expires_at - now).days


class LicenseValidator:
    """Loads, parses and verifies a license.dat file."""

    def __init__(self, public_key: Ed25519PublicKey, *, accepted_edition: str = ACCEPTED_EDITION):
        self._public_key = public_key
        self._accepted_edition = accepted_edition

    @classmethod
    def from_public_key_file(cls, path: Path, **kwargs) -> "LicenseValidator":
        pem = Path(path).read_bytes()
        key = serialization.load_pem_public_key(pem)
        if not isinstance(key, Ed25519PublicKey):
            raise LicenseCorruptedError(f"Public key at {path} is not Ed25519.")
        return cls(key, **kwargs)

    def load(
        self,
        license_path: Path,
        *,
        current_fingerprint: Optional[HardwareFingerprint] = None,
        now: Optional[datetime] = None,
    ) -> LicenseClaims:
        """Read and verify a license.dat, returning the claims on success.

        Raises one of the `LicenseError` subclasses on any failure.
        """
        path = Path(license_path)
        if not path.exists():
            raise LicenseMissingError(f"License file not found at {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LicenseCorruptedError(f"license.dat is not valid JSON: {exc.msg}") from None

        missing = _REQUIRED_FIELDS - set(payload)
        if missing:
            raise LicenseCorruptedError(f"license.dat missing fields: {sorted(missing)}")

        # Verify signature over payload sans "signature" key.
        signature_b64 = payload.pop("signature")
        try:
            signature = base64.b64decode(signature_b64, validate=True)
        except (ValueError, TypeError):
            raise LicenseSignatureError("Signature is not valid base64.") from None

        payload_canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            self._public_key.verify(signature, payload_canonical)
        except InvalidSignature:
            raise LicenseSignatureError("License signature does not match payload.") from None

        # Edition check — reject mis-issued tier.
        edition = payload.get("edition", "")
        if edition != self._accepted_edition:
            raise LicenseTierMismatchError(
                f"License is for edition '{edition}', but this build accepts only '{self._accepted_edition}'."
            )

        # Expiry.
        now = now or datetime.now(timezone.utc)
        expires_at = _parse_iso(payload["expires_at"])
        if expires_at <= now:
            raise LicenseExpiredError(f"License expired on {expires_at.isoformat()}.")
        issued_at = _parse_iso(payload["issued_at"])

        # Hardware fingerprint — 2 of 3 base factors + optional sql_servername hard-match.
        expected_fp = HardwareFingerprint(
            bios_uuid=str(payload["hw_fingerprint"].get("bios_uuid", "")),
            cpu_id=str(payload["hw_fingerprint"].get("cpu_id", "")),
            hostname=str(payload["hw_fingerprint"].get("hostname", "")),
            sql_servername=str(payload["hw_fingerprint"].get("sql_servername", "")),
        )
        actual_fp = current_fingerprint or build_fingerprint()
        if not actual_fp.matches(expected_fp):
            raise LicenseFingerprintError(
                "Hardware fingerprint does not match the licensed machine."
            )

        features = payload.get("features", {})
        if not isinstance(features, dict):
            raise LicenseCorruptedError("features must be an object.")

        # Optional industry/compliance fields (FIND-20260424-001 B5)
        regulatory_regime_raw = payload.get("regulatory_regime", ())
        if isinstance(regulatory_regime_raw, list):
            regulatory_regime = tuple(str(r) for r in regulatory_regime_raw)
        elif isinstance(regulatory_regime_raw, str) and regulatory_regime_raw:
            regulatory_regime = (regulatory_regime_raw,)
        else:
            regulatory_regime = ()

        return LicenseClaims(
            customer_id=str(payload["customer_id"]),
            edition=edition,
            tier=str(payload.get("tier", edition)),
            features={str(k): bool(v) for k, v in features.items()},
            issued_at=issued_at,
            expires_at=expires_at,
            hw_fingerprint=expected_fp,
            industry=str(payload.get("industry", "")),
            regulatory_regime=regulatory_regime,
            license_id=str(payload.get("license_id", "")),
            raw_payload=payload,
        )


def _parse_iso(value: str) -> datetime:
    try:
        # Accept both "Z" and offset forms.
        value = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LicenseCorruptedError(f"Invalid ISO-8601 timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
