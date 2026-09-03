"""
WatcherDB V3.3 Standard Edition — licensing module.

Responsibilities:
  * Verify the Ed25519-signed license.dat delivered to each customer.
  * Bind each license to the target machine via a 2-of-3 hardware fingerprint.
  * Expose the feature set declared in the license to the rest of the service.

Public API:
  * LicenseValidator.load(path)          -> LicenseClaims
  * FeatureRegistry.from_claims(claims)  -> FeatureRegistry
  * build_fingerprint()                  -> HardwareFingerprint
"""

from .exceptions import (
    LicenseError,
    LicenseMissingError,
    LicenseCorruptedError,
    LicenseSignatureError,
    LicenseExpiredError,
    LicenseFingerprintError,
    LicenseTierMismatchError,
)
from .fingerprint import HardwareFingerprint, build_fingerprint
from .validator import LicenseClaims, LicenseValidator
from .feature_registry import FeatureRegistry

__all__ = [
    "LicenseError",
    "LicenseMissingError",
    "LicenseCorruptedError",
    "LicenseSignatureError",
    "LicenseExpiredError",
    "LicenseFingerprintError",
    "LicenseTierMismatchError",
    "HardwareFingerprint",
    "build_fingerprint",
    "LicenseClaims",
    "LicenseValidator",
    "FeatureRegistry",
]
