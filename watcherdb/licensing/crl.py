"""
Certificate Revocation List (CRL) — signed `revoked_licenses.json` mechanism.

Sprint FIND-20260424-005 sub-task B5.2.

Permite revogar licenses individuais (por `license_id`) sem rotar o master
keypair. Use cases:
  - Cliente termina contrato cedo
  - License compromised (HW migrada sem re-license)
  - Contract dispute / fraud
  - Re-emit (vendor anula license antiga apos emitir nova com mesmo customer_id)

Format on-disk (`C:\\ProgramData\\WatcherDB\\revoked_licenses.json`):
    {
      "version": 1,
      "issued_at": "2026-04-25T10:00:00Z",
      "revocations": [
        {
          "license_id": "<uuid>",
          "revoked_at": "2026-04-25T10:00:00Z",
          "reason": "<short reason>"
        }
      ],
      "signature": "<base64 ed25519 sobre canonical payload sans signature>"
    }

Path resolution (3-tier prioridade, igual a license.dat):
  1. WATCHERDB_CRL_PATH env var
  2. C:\\ProgramData\\WatcherDB\\revoked_licenses.json
  3. <base_dir>/revoked_licenses.json (bundle fallback)

Distribuição: vendor publica novo CRL (HTTPS / portal cliente / email).
Cliente substitui ficheiro local + restart services.

Failure modes:
  - CRL ausente → OK, no revocations (positive default)
  - CRL signature invalid → WARN log + treat as ausente (avoid bricking)
  - License_id em CRL → fail-close (LicenseRevokedError) IGNORANDO grace
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .exceptions import LicenseError, LicenseSignatureError

logger = logging.getLogger(__name__)

DEFAULT_CRL_FILENAME = "revoked_licenses.json"
DEFAULT_PROGRAMDATA = Path(r"C:\ProgramData\WatcherDB")
SUPPORTED_CRL_VERSION = 1


# ===========================================================================
# Exceptions
# ===========================================================================


class LicenseRevokedError(LicenseError):
    """Raised quando license.dat tem license_id presente no CRL."""
    pass


# ===========================================================================
# Data classes
# ===========================================================================


@dataclass(frozen=True)
class CRLEntry:
    license_id: str
    revoked_at: datetime
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "license_id": self.license_id,
            "revoked_at": self.revoked_at.isoformat().replace("+00:00", "Z"),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CRLEntry":
        ts = data.get("revoked_at", "")
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
        except ValueError:
            dt = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return cls(
            license_id=str(data.get("license_id", "")),
            revoked_at=dt,
            reason=str(data.get("reason", "")),
        )


@dataclass(frozen=True)
class CRL:
    """Loaded + verified Certificate Revocation List."""
    version: int
    issued_at: datetime
    entries: List[CRLEntry] = field(default_factory=list)

    @property
    def revoked_ids(self) -> Set[str]:
        return {e.license_id for e in self.entries if e.license_id}

    def is_revoked(self, license_id: str) -> bool:
        if not license_id:
            return False  # licenses sem license_id (legacy V3.3 pre-B5) nao revogaveis
        return license_id in self.revoked_ids

    def find(self, license_id: str) -> Optional[CRLEntry]:
        for e in self.entries:
            if e.license_id == license_id:
                return e
        return None


# ===========================================================================
# Path resolution
# ===========================================================================


def _resolve_crl_path(base_dir: Optional[Path] = None) -> Path:
    """3-tier priority: env var → ProgramData → bundle fallback."""
    env = os.getenv("WATCHERDB_CRL_PATH")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(DEFAULT_PROGRAMDATA / DEFAULT_CRL_FILENAME)
    if base_dir:
        candidates.append(Path(base_dir) / DEFAULT_CRL_FILENAME)
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]  # return last (likely non-existent — caller checks)


# ===========================================================================
# Load + verify
# ===========================================================================


def load_crl(
    public_key: Ed25519PublicKey,
    *,
    crl_path: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> Optional[CRL]:
    """Load + verify CRL signature. Returns None se ausente.

    Raises LicenseSignatureError em signature invalid (caller decide warn-vs-fail).
    """
    path = crl_path or _resolve_crl_path(base_dir)
    if not path.exists():
        logger.debug("CRL absent at %s — assuming no revocations", path)
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LicenseError(f"CRL JSON invalid: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise LicenseError("CRL must be a JSON object")

    version = payload.get("version", 0)
    if version != SUPPORTED_CRL_VERSION:
        raise LicenseError(f"CRL version {version} unsupported (expected {SUPPORTED_CRL_VERSION})")

    sig_b64 = payload.pop("signature", None)
    if not sig_b64:
        raise LicenseSignatureError("CRL missing signature field")

    try:
        sig = base64.b64decode(sig_b64, validate=True)
    except (ValueError, TypeError):
        raise LicenseSignatureError("CRL signature not valid base64") from None

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        public_key.verify(sig, canonical)
    except InvalidSignature:
        raise LicenseSignatureError("CRL signature does not match payload") from None

    # Parse entries
    raw_entries = payload.get("revocations", [])
    if not isinstance(raw_entries, list):
        raise LicenseError("CRL 'revocations' must be a list")
    entries = [CRLEntry.from_dict(e) for e in raw_entries if isinstance(e, dict)]

    issued_at_raw = payload.get("issued_at", "")
    if issued_at_raw.endswith("Z"):
        issued_at_raw = issued_at_raw.replace("Z", "+00:00")
    try:
        issued_at = datetime.fromisoformat(issued_at_raw) if issued_at_raw else datetime.now(timezone.utc)
    except ValueError:
        issued_at = datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)

    return CRL(version=version, issued_at=issued_at, entries=entries)


def load_crl_safe(
    public_key: Ed25519PublicKey,
    *,
    crl_path: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> Optional[CRL]:
    """Wrapper que NAO levanta em signature invalid — log warning + retorna None.

    Razao: avoid bricking clientes se vendor distribui CRL malformado.
    Caller (startup_guard) usa este em vez de load_crl directo para fail-open
    em CRL errors (mas fail-close em license_id revoked).
    """
    try:
        return load_crl(public_key, crl_path=crl_path, base_dir=base_dir)
    except LicenseSignatureError as e:
        logger.warning("CRL signature invalid (%s) — treating as absent. Vendor must reissue.", e)
        return None
    except LicenseError as e:
        logger.warning("CRL load failed (%s) — treating as absent.", e)
        return None
    except Exception as e:
        logger.warning("CRL unexpected error (%s) — treating as absent.", e)
        return None


# ===========================================================================
# Public key loader (helper)
# ===========================================================================


def load_public_key_from_pem(path: Path) -> Ed25519PublicKey:
    """Load ed25519 public key from PEM file. Raises if not Ed25519."""
    pem = Path(path).read_bytes()
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise LicenseError(f"Public key at {path} is not Ed25519")
    return key
