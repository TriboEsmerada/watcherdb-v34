"""
Update-package manifest — Ed25519-signed metadata for the in-place updater.

Manifest schema (``manifest.json``)::

    {
      "product":        "watcherdb-v3.3-standard",
      "version":        "3.3.1.0",          # new build being shipped
      "min_version":    "3.3.0.0",          # oldest compatible installed version
      "issued_at":      "2026-04-22T10:00:00Z",
      "zip_sha256":     "<hex digest of update.zip>",
      "zip_size_bytes": 52428800,
      "files":          [                    # informational only; the ZIP is
        {"path": "watcherdb.exe",            # already hash-anchored above.
         "sha256": "<hex>",
         "size_bytes": 3145728}
      ],
      "signature":      "<base64 ed25519 over canonical JSON w/o signature>"
    }

Reuses the Ed25519 keypair from the licensing module. One trust root for
both licences and update packages keeps the key-rotation story simple:
rotate once, re-issue everything.

Public API
  * :func:`build_manifest`  - build the payload (called by the packaging CLI)
  * :func:`sign_manifest`   - attach the Ed25519 signature
  * :func:`verify_manifest` - load, verify signature, enforce version policy

Version policy enforced at verification time:

  * ``version`` > currently installed version  (anti-downgrade)
  * ``min_version`` <= currently installed version  (compatibility floor)
  * ``zip_sha256`` matches the on-disk update.zip  (integrity)
  * ``signature`` matches the canonical payload  (authenticity)

Operator pseudo-workflow on a customer machine::

    claims = verify_manifest(manifest_path, pub_key, zip_path, current_version)
    # If the call returns, the update is authentic + safe. Back up the
    # current install, extract the zip, health-check, rollback on failure.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .exceptions import (
    LicenseCorruptedError,
    LicenseError,
    LicenseSignatureError,
)

PRODUCT_ID = "watcherdb-v3.3-standard"

_REQUIRED_FIELDS = {
    "product", "version", "min_version", "issued_at",
    "zip_sha256", "zip_size_bytes", "files", "signature",
}


class ManifestError(LicenseError):
    """Base class for manifest failures reusing the LicenseError hierarchy."""


class ManifestProductMismatchError(ManifestError):
    """Manifest was issued for a different product."""


class ManifestDowngradeError(ManifestError):
    """Manifest's version is not strictly greater than the installed version."""


class ManifestIncompatibleError(ManifestError):
    """Installed version is older than the manifest's min_version floor."""


class ManifestIntegrityError(ManifestError):
    """update.zip hash does not match the manifest's zip_sha256."""


@dataclass(frozen=True)
class ManifestClaims:
    product: str
    version: str
    min_version: str
    issued_at: datetime
    zip_sha256: str
    zip_size_bytes: int
    files: List[Dict[str, Any]] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(repr=False, default_factory=dict)


# ---------------------------------------------------------------------------
# Build / sign (maintainer side)
# ---------------------------------------------------------------------------

def _sha256_of(path: Path) -> Tuple[str, int]:
    h = sha256()
    size = 0
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_manifest(
    *,
    version: str,
    min_version: str,
    zip_path: Path,
    file_entries: Sequence[Dict[str, Any]] = (),
    product: str = PRODUCT_ID,
    issued_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build the manifest payload (still unsigned)."""
    z = Path(zip_path)
    if not z.is_file():
        raise ManifestError(f"update zip not found: {z}")
    zip_hash, zip_size = _sha256_of(z)
    return {
        "product": product,
        "version": version,
        "min_version": min_version,
        "issued_at": (issued_at or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "zip_sha256": zip_hash,
        "zip_size_bytes": zip_size,
        "files": list(file_entries),
    }


def sign_manifest(payload: Dict[str, Any], private_key: Ed25519PrivateKey) -> Dict[str, Any]:
    """Attach an Ed25519 signature. Returns the payload with `signature` key."""
    signature = private_key.sign(_canonical(payload))
    out = dict(payload)
    out["signature"] = base64.b64encode(signature).decode("ascii")
    return out


# ---------------------------------------------------------------------------
# Verify (customer side)
# ---------------------------------------------------------------------------

def _parse_iso(value: str) -> datetime:
    value = value.replace("Z", "+00:00") if value.endswith("Z") else value
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_version(v: str) -> Tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.split("."))
    except (AttributeError, ValueError):
        raise LicenseCorruptedError(f"Invalid version string: {v!r}")


def verify_manifest(
    manifest_path: Path,
    public_key: Ed25519PublicKey,
    zip_path: Path,
    current_version: str,
    *,
    product: str = PRODUCT_ID,
) -> ManifestClaims:
    """Validate a manifest against the public key, the zip on disk and the
    currently installed version. Returns :class:`ManifestClaims` on success.

    Raises a specific :class:`ManifestError` subclass on every failure mode.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise ManifestError(f"Manifest file not found at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LicenseCorruptedError(f"manifest.json is not valid JSON: {exc.msg}") from None

    missing = _REQUIRED_FIELDS - set(payload)
    if missing:
        raise LicenseCorruptedError(f"manifest.json missing fields: {sorted(missing)}")

    # Signature.
    signature_b64 = payload.pop("signature")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        raise LicenseSignatureError("Manifest signature is not valid base64.") from None
    try:
        public_key.verify(signature, _canonical(payload))
    except InvalidSignature:
        raise LicenseSignatureError("Manifest signature does not match payload.") from None

    # Product binding.
    if payload.get("product") != product:
        raise ManifestProductMismatchError(
            f"Manifest is for product {payload.get('product')!r}; expected {product!r}."
        )

    # Version policy.
    new_v = _parse_version(str(payload["version"]))
    floor_v = _parse_version(str(payload["min_version"]))
    cur_v = _parse_version(current_version)
    if not (new_v > cur_v):
        raise ManifestDowngradeError(
            f"Manifest version {payload['version']} is not newer than installed {current_version}."
        )
    if cur_v < floor_v:
        raise ManifestIncompatibleError(
            f"Installed version {current_version} is below min_version {payload['min_version']}."
        )

    # ZIP integrity.
    z = Path(zip_path)
    if not z.exists():
        raise ManifestIntegrityError(f"update zip not found at {z}")
    actual_hash, actual_size = _sha256_of(z)
    if actual_hash.lower() != str(payload["zip_sha256"]).lower():
        raise ManifestIntegrityError("update.zip hash does not match manifest.")
    if int(payload["zip_size_bytes"]) != actual_size:
        raise ManifestIntegrityError("update.zip size does not match manifest.")

    return ManifestClaims(
        product=payload["product"],
        version=str(payload["version"]),
        min_version=str(payload["min_version"]),
        issued_at=_parse_iso(str(payload["issued_at"])),
        zip_sha256=str(payload["zip_sha256"]),
        zip_size_bytes=int(payload["zip_size_bytes"]),
        files=list(payload.get("files", [])),
        raw_payload=payload,
    )
