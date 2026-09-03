"""
Exception hierarchy for WatcherDB licensing.

Callers should catch LicenseError for a generic "cannot start" branch, or the
narrower subclasses when the reason informs operator action (e.g., a
FingerprintError is resolved differently from an ExpiredError).

Exception messages are operator-facing and must not leak raw payload contents
or key material.
"""

from __future__ import annotations


class LicenseError(Exception):
    """Base class for any licensing failure."""


class LicenseMissingError(LicenseError):
    """No license.dat could be found at the expected path."""


class LicenseCorruptedError(LicenseError):
    """license.dat exists but is not parseable JSON or lacks required fields."""


class LicenseSignatureError(LicenseError):
    """The Ed25519 signature does not match the payload or the public key."""


class LicenseExpiredError(LicenseError):
    """The license's expires_at is in the past."""


class LicenseFingerprintError(LicenseError):
    """The machine's hardware fingerprint does not satisfy the 2-of-3 bind."""


class LicenseTierMismatchError(LicenseError):
    """The license is issued for a different edition (e.g., Pro license on Std service)."""
