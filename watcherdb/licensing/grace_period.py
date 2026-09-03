"""
Grace period policy — allow startup without license.dat durante os
primeiros N dias apos install (FIND-20260424-005 follow-up).

Scope: evita outage em clients deployed com licensing port changes mas sem
license.dat emitido pelo vendor ainda. Apos grace period expirar, service
volta a fail-close strict.

Marker file: C:\\ProgramData\\WatcherDB\\install_marker.json
  {
    "install_date_utc": "2026-04-24T21:00:00Z",
    "version": "3.3.0",
    "edition": "standard"  # declared, nao validated
  }

Policy:
  - FIRST_RUN (marker criado agora) → grace ATIVA 60 dias
  - IN_GRACE (days_since_install < 60) → allow startup, log warning
  - EXPIRED (days >= 60) → strict fail (license obrigatória)

Apenas aplicavel em LicenseMissingError. Outros erros (signature invalid,
fingerprint mismatch, expired license) fail-close sempre (ignoram grace).

Windows Event Log IDs:
  1003 LICENSE_GRACE_PERIOD_ACTIVE  (cada startup em grace)
  1004 LICENSE_GRACE_PERIOD_EXPIRED (warning when expires soon OR expired)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_GRACE_DAYS = 60
DEFAULT_MARKER_FILENAME = "install_marker.json"
DEFAULT_PROGRAMDATA = Path(r"C:\ProgramData\WatcherDB")


@dataclass(frozen=True)
class GraceStatus:
    state: str  # NOT_INITIALIZED | IN_GRACE | EXPIRED
    install_date: Optional[datetime]
    days_since_install: int
    days_remaining: int

    @property
    def is_grace_active(self) -> bool:
        return self.state in ("NOT_INITIALIZED", "IN_GRACE")

    @property
    def is_expired(self) -> bool:
        return self.state == "EXPIRED"


def _resolve_marker_path(programdata_dir: Optional[Path] = None) -> Path:
    env_override = os.getenv("WATCHERDB_INSTALL_MARKER_PATH")
    if env_override:
        return Path(env_override)
    base = programdata_dir or DEFAULT_PROGRAMDATA
    return base / DEFAULT_MARKER_FILENAME


def _read_marker(path: Path) -> Optional[datetime]:
    """Read install_date from marker. Returns None se ausente ou inválido."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        iso = data.get("install_date_utc")
        if not iso:
            return None
        if iso.endswith("Z"):
            iso = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("install marker malformed (%s) — treating as missing", e)
        return None


def _write_marker(
    path: Path,
    install_date: datetime,
    version: str,
    edition: str,
) -> None:
    """Create marker file. Atomic enough para este scope."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "install_date_utc": install_date.isoformat().replace("+00:00", "Z"),
        "version": version,
        "edition": edition,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def check_grace_period(
    *,
    version: str = "unknown",
    edition: str = "unknown",
    grace_days: int = DEFAULT_GRACE_DAYS,
    programdata_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
    auto_initialize: bool = True,
) -> GraceStatus:
    """Check grace period state. Creates marker em first run se auto_initialize=True.

    Args:
        version: Product version to write in marker (informational).
        edition: Declared edition (informational — NOT validated em grace mode).
        grace_days: N dias apos install durante os quais license e opcional.
        programdata_dir: Override de C:\\ProgramData\\WatcherDB\\ (para tests).
        now: Override current time (para tests).
        auto_initialize: Se True, cria marker em first run. Se False, retorna
            NOT_INITIALIZED sem criar (caller decide).

    Returns:
        GraceStatus com state + days info.
    """
    _now = now or datetime.now(timezone.utc)
    marker_path = _resolve_marker_path(programdata_dir)

    install_date = _read_marker(marker_path)

    if install_date is None:
        # First run ou marker corrompido
        if auto_initialize:
            try:
                _write_marker(marker_path, _now, version, edition)
                logger.info("install marker created at %s (grace period starts now)", marker_path)
            except OSError as e:
                logger.warning("could not write install marker (%s) — assuming IN_GRACE fallback", e)
        return GraceStatus(
            state="NOT_INITIALIZED",
            install_date=_now,
            days_since_install=0,
            days_remaining=grace_days,
        )

    # Marker exists
    days = (_now - install_date).days
    if days < grace_days:
        return GraceStatus(
            state="IN_GRACE",
            install_date=install_date,
            days_since_install=days,
            days_remaining=grace_days - days,
        )

    return GraceStatus(
        state="EXPIRED",
        install_date=install_date,
        days_since_install=days,
        days_remaining=0,
    )
