"""
Startup license guard — validacao unificada partilhada pelos 3 services
(web, collector, AI).

Sprint install flow v0.2 B6 (FIND-20260424-001).

Design goals:
  * Single source of truth: todos services chamam este modulo no startup.
  * Fail-close default: strict mode (service recusa start em falha).
  * Audit trail: Windows Event Log entries (event source "WatcherDB").
    - 1000 LICENSE_VALIDATION_OK
    - 1001 LICENSE_VALIDATION_FAILED
    - 1002 LICENSE_EXPIRY_WARNING (30d antes de expirar)
  * Advisory opt-out: env var WATCHERDB_LICENSE_ENFORCE=advisory apenas
    em dev/test workstations. Fallback para PYTEST_CURRENT_TEST.
  * Retrocompat: se Windows Event Log nao disponivel (dev linux / pywin32
    ausente), nao falha — regista so via logger stdlib.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WINDOWS_EVENT_LOG_SOURCE = "WatcherDB"
EVENT_ID_LICENSE_OK = 1000
EVENT_ID_LICENSE_FAILED = 1001
EVENT_ID_LICENSE_EXPIRY_WARNING = 1002
EVENT_ID_GRACE_PERIOD_ACTIVE = 1003
EVENT_ID_GRACE_PERIOD_EXPIRED = 1004
EXPIRY_WARNING_DAYS = 30


def _write_event_log(event_id: int, message: str, event_type: str = "Information") -> None:
    """Escreve no Windows Application Event Log (source=WatcherDB).

    Fail-safe: se pywin32 nao disponivel ou source nao registada,
    regista via logger stdlib apenas. Nao levanta excepcao.
    """
    try:
        import win32evtlog  # type: ignore[import-not-found]
        import win32evtlogutil  # type: ignore[import-not-found]

        etype_map = {
            "Information": win32evtlog.EVENTLOG_INFORMATION_TYPE,
            "Warning": win32evtlog.EVENTLOG_WARNING_TYPE,
            "Error": win32evtlog.EVENTLOG_ERROR_TYPE,
        }
        win32evtlogutil.ReportEvent(
            WINDOWS_EVENT_LOG_SOURCE,
            event_id,
            eventType=etype_map.get(event_type, win32evtlog.EVENTLOG_INFORMATION_TYPE),
            strings=[message],
        )
    except Exception as e:  # pragma: no cover - depende de ambiente Windows
        logger.debug("Event Log unavailable (%s) — fallback to logger only", e)

    # Sempre regista via logger stdlib (stdout/file handler do service)
    log_method = {
        "Information": logger.info,
        "Warning": logger.warning,
        "Error": logger.error,
    }.get(event_type, logger.info)
    log_method("AUDIT[event_id=%d]: %s", event_id, message)


def _resolve_license_path() -> Path:
    """Find license.dat em 3-tier priority (FIND-20260424-004 pattern)."""
    env_path = os.getenv("WATCHERDB_LICENSE_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(r"C:\ProgramData\WatcherDB\license.dat"))
    # Bundle fallback — caller passa base_dir se quiser
    return next((p for p in candidates if p.exists()), candidates[-1])


def _resolve_public_key_path(base_dir: Optional[Path] = None) -> Path:
    """Find ed25519_public.pem em 3-tier priority (FIND-20260424-004)."""
    env_path = os.getenv("WATCHERDB_PUBLIC_KEY_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(r"C:\ProgramData\WatcherDB\ed25519_public.pem"))
    if base_dir:
        candidates.append(base_dir / "deploy" / "keys" / "ed25519_public.pem")
    return next((p for p in candidates if p.exists()), candidates[-1])


def validate_and_enforce(
    service_name: str,
    *,
    accepted_edition: str = "standard",
    base_dir: Optional[Path] = None,
    sql_servername: str = "",
):
    """Valida license.dat e retorna (FeatureRegistry, LicenseClaims | None).

    Args:
        service_name: Identificador do service (audit log). Ex: "web_service",
            "collector_service", "ai_service".
        accepted_edition: Qual edition o build aceita ("standard", "pro",
            "enterprise"). Licenca mis-issued para outro tier e rejeitada.
        base_dir: Directorio base para fallback de public key (tipicamente
            dir do executavel em PyInstaller bundle).
        sql_servername: SQL @@SERVERNAME opcional para banking-strict
            fingerprint binding (B5). Empty = factor ignorado.

    Returns:
        Tuple (FeatureRegistry, Optional[LicenseClaims]):
            - Registry populada em success, empty em advisory-failure
            - Claims object em success, None em failure

    Raises:
        SystemExit: em strict mode + falha validacao.
    """
    # Import aqui para evitar circular import
    from .feature_registry import FeatureRegistry
    from .exceptions import LicenseError, LicenseMissingError
    from .validator import LicenseValidator
    from .fingerprint import build_fingerprint
    from .grace_period import check_grace_period
    from .crl import LicenseRevokedError, load_crl_safe, load_public_key_from_pem

    # Bypass explicito para pytest
    if "PYTEST_CURRENT_TEST" in os.environ:
        return FeatureRegistry.empty(), None

    # Strict default (FIND-20260424-003) — advisory requer opt-in explicito
    mode = os.getenv("WATCHERDB_LICENSE_ENFORCE", "strict").lower()
    strict = mode != "advisory"

    license_path = _resolve_license_path()
    public_key_path = _resolve_public_key_path(base_dir)

    try:
        if not public_key_path.exists():
            raise LicenseError(
                f"Public key not deployed. Tried: "
                f"{[str(p) for p in _public_key_candidates_tried(base_dir)]}"
            )
        validator = LicenseValidator.from_public_key_file(
            public_key_path, accepted_edition=accepted_edition
        )
        current_fp = build_fingerprint(sql_servername=sql_servername)
        claims = validator.load(license_path, current_fingerprint=current_fp)

        # CRL check (FIND-20260424-005 sub-task B5.2) — apos signature OK,
        # verificar se license_id foi revogada. Fail-close em strict, IGNORA grace.
        if claims.license_id:
            try:
                pub_key_obj = load_public_key_from_pem(public_key_path)
                crl = load_crl_safe(pub_key_obj, base_dir=base_dir)
            except Exception as _crl_err:
                logger.warning("CRL load unexpected error (%s) — assuming no revocations", _crl_err)
                crl = None
            if crl and crl.is_revoked(claims.license_id):
                entry = crl.find(claims.license_id)
                reason = entry.reason if entry else "unspecified"
                raise LicenseRevokedError(
                    f"License {claims.license_id} revoked at "
                    f"{entry.revoked_at.isoformat() if entry else 'unknown'} — reason: {reason}"
                )
    except LicenseMissingError as exc:
        # Grace period check — license em falta pode ser tolerada nos primeiros 60d
        # apos install (FIND-20260424-005 follow-up). Outros LicenseError (signature,
        # fingerprint, expired) fail-close sempre independentemente de grace.
        try:
            grace = check_grace_period(
                version="unknown",
                edition=accepted_edition,
            )
        except Exception as _grace_err:
            logger.warning("grace period check failed (%s) — treating as EXPIRED", _grace_err)
            grace = None

        if grace and grace.is_grace_active:
            grace_msg = (
                f"LICENSE_GRACE_PERIOD_ACTIVE service={service_name} "
                f"state={grace.state} days_since_install={grace.days_since_install} "
                f"days_remaining={grace.days_remaining} edition={accepted_edition}"
            )
            _write_event_log(EVENT_ID_GRACE_PERIOD_ACTIVE, grace_msg, event_type="Warning")
            logger.warning(
                "License missing but grace period active (%d days remaining). "
                "Service starts in degraded mode. Obtain license.dat from vendor.",
                grace.days_remaining,
            )
            return FeatureRegistry.empty(), None

        # Grace expired OR check failed → strict behavior
        if grace and grace.is_expired:
            expired_msg = (
                f"LICENSE_GRACE_PERIOD_EXPIRED service={service_name} "
                f"days_since_install={grace.days_since_install}"
            )
            _write_event_log(EVENT_ID_GRACE_PERIOD_EXPIRED, expired_msg, event_type="Error")

        msg = (
            f"LICENSE_VALIDATION_FAILED service={service_name} "
            f"reason={type(exc).__name__}: {exc}"
        )
        _write_event_log(EVENT_ID_LICENSE_FAILED, msg, event_type="Error")
        if strict:
            raise SystemExit(
                f"[WatcherDB:{service_name}] cannot start: license validation failed — {exc}"
            ) from exc
        logger.warning("License validation failed (advisory mode): %s", exc)
        return FeatureRegistry.empty(), None
    except LicenseRevokedError as exc:
        # CRL revogation — security critical, IGNORE grace, fail-close em strict.
        msg = (
            f"LICENSE_VALIDATION_FAILED service={service_name} "
            f"reason=LicenseRevokedError: {exc}"
        )
        _write_event_log(EVENT_ID_LICENSE_FAILED, msg, event_type="Error")
        if strict:
            raise SystemExit(
                f"[WatcherDB:{service_name}] cannot start: license revoked — {exc}"
            ) from exc
        logger.warning("License revoked (advisory mode): %s", exc)
        return FeatureRegistry.empty(), None
    except LicenseError as exc:
        # Non-missing license errors (signature, fingerprint, expired, tier mismatch, corrupted)
        # NEVER get grace period — these are security-critical. Fail-close em strict.
        msg = (
            f"LICENSE_VALIDATION_FAILED service={service_name} "
            f"reason={type(exc).__name__}: {exc}"
        )
        _write_event_log(EVENT_ID_LICENSE_FAILED, msg, event_type="Error")
        if strict:
            raise SystemExit(
                f"[WatcherDB:{service_name}] cannot start: license validation failed — {exc}"
            ) from exc
        logger.warning("License validation failed (advisory mode): %s", exc)
        return FeatureRegistry.empty(), None

    # OK — log audit event + check expiry warning
    days_left = claims.days_until_expiry()
    ok_msg = (
        f"LICENSE_VALIDATION_OK service={service_name} "
        f"customer={claims.customer_id} edition={claims.edition} "
        f"expires={claims.expires_at.isoformat()} days_left={days_left}"
    )
    if claims.industry:
        ok_msg += f" industry={claims.industry}"
    if claims.regulatory_regime:
        ok_msg += f" regimes={'+'.join(claims.regulatory_regime)}"
    _write_event_log(EVENT_ID_LICENSE_OK, ok_msg)

    if days_left <= EXPIRY_WARNING_DAYS:
        warn_msg = (
            f"LICENSE_EXPIRY_WARNING service={service_name} "
            f"customer={claims.customer_id} days_left={days_left} "
            f"expires={claims.expires_at.isoformat()}"
        )
        _write_event_log(EVENT_ID_LICENSE_EXPIRY_WARNING, warn_msg, event_type="Warning")

    return FeatureRegistry.from_claims(claims), claims


def _public_key_candidates_tried(base_dir: Optional[Path]) -> list:
    """For diagnostic messages — rebuild candidate list."""
    env_path = os.getenv("WATCHERDB_PUBLIC_KEY_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(r"C:\ProgramData\WatcherDB\ed25519_public.pem"))
    if base_dir:
        candidates.append(base_dir / "deploy" / "keys" / "ed25519_public.pem")
    return candidates
