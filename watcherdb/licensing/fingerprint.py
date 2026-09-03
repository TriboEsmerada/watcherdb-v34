"""
Hardware fingerprint for license binding.

Three factors are combined:

  * ``bios_uuid``  — BIOS/UEFI system UUID via `wmic csproduct get UUID`.
                      Stable across reboots. VMware/Hyper-V preserve this on
                      live migration, so it is the most reliable anchor.
  * ``cpu_id``     — CPU ProcessorId via `wmic cpu get ProcessorId`.
                      Changes only on physical hardware replacement.
  * ``hostname``   — `socket.gethostname()`. Cheap to rotate deliberately
                      (sysprep, rename) so it is only a tie-breaker.

The licence carries the three expected values; at startup the service
rebuilds its own fingerprint and accepts the licence as long as **at least
two** of the three components match. This tolerates a hostname change after
a sysprep clone *or* a NIC swap — but not both simultaneously.

Note that MAC address is deliberately **not** a factor: it flips on every
vSphere live migration in many customer estates, and using it as a gate
turned out to be an incident generator in V5 Pro pilots.
"""

from __future__ import annotations

import logging
import socket
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HardwareFingerprint:
    bios_uuid: str
    cpu_id: str
    hostname: str
    # sql_servername: optional factor added 2026-04-24 (FIND-20260424-001 B5).
    # Quando presente em ambos os lados, e um GATE adicional (hard-match).
    # Quando ausente num dos lados, ignorado (backward compat com license.dat
    # existente pre-B5).
    sql_servername: str = ""

    def as_dict(self) -> dict:
        d = {"bios_uuid": self.bios_uuid, "cpu_id": self.cpu_id, "hostname": self.hostname}
        if self.sql_servername:
            d["sql_servername"] = self.sql_servername
        return d

    def matches(self, other: "HardwareFingerprint") -> bool:
        """True quando:
          1. >= 2 dos 3 componentes base (bios/cpu/hostname) coincidem, E
          2. Se ambos os lados tem sql_servername populado, MUST match tambem.

        Se so um dos lados tem sql_servername, factor e ignorado (backward compat).
        """
        hits = 0
        if self.bios_uuid and other.bios_uuid and self.bios_uuid.casefold() == other.bios_uuid.casefold():
            hits += 1
        if self.cpu_id and other.cpu_id and self.cpu_id.casefold() == other.cpu_id.casefold():
            hits += 1
        if self.hostname and other.hostname and self.hostname.casefold() == other.hostname.casefold():
            hits += 1
        base_ok = hits >= 2

        # SQL SERVERNAME hard-match quando ambos presentes
        if self.sql_servername and other.sql_servername:
            sql_match = self.sql_servername.casefold() == other.sql_servername.casefold()
            return base_ok and sql_match
        return base_ok


def _run_powershell(cim_class: str, property_name: str, select_first: bool = False) -> Optional[str]:
    """Run PowerShell Get-CimInstance and return the property value.

    Replaces wmic which was removed in Windows 11 24H2+ and Windows Server 2025.
    Falls back gracefully on any error — caller treats None as "factor ausente"
    e a logica matches() compensa via 2-of-3 rule.
    """
    if select_first:
        cmd = f"(Get-CimInstance {cim_class} | Select-Object -First 1).{property_name}"
    else:
        cmd = f"(Get-CimInstance {cim_class}).{property_name}"
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("powershell call failed (%s.%s): %s", cim_class, property_name, e)
        return None

    if out.returncode != 0:
        logger.warning("powershell returncode=%d (%s.%s) stderr=%s",
                       out.returncode, cim_class, property_name, out.stderr.strip()[:200])
        return None

    value = out.stdout.strip()
    if value and value not in {"0", "FFFFFFFF-FFFFFFFF-FFFFFFFF-FFFFFFFF"}:
        return value
    return None


def _run_wmic(fields: str) -> Optional[str]:
    """Legacy wmic fallback (Windows < 11 24H2). Returns None when wmic absent."""
    try:
        out = subprocess.run(
            ["wmic", *fields.split(), "get", fields.split()[-1], "/value"],
            capture_output=True,
            text=True,
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug("wmic absent (%s): %s — fallback to PowerShell", fields, e)
        return None

    if out.returncode != 0:
        return None

    for line in out.stdout.splitlines():
        line = line.strip()
        if "=" in line:
            _, _, value = line.partition("=")
            value = value.strip()
            if value and value not in {"0", "FFFFFFFF-FFFFFFFF-FFFFFFFF-FFFFFFFF"}:
                return value
    return None


def _bios_uuid() -> str:
    # PowerShell Get-CimInstance preferred (Win11 24H2+ removed wmic).
    return (
        _run_powershell("Win32_ComputerSystemProduct", "UUID")
        or _run_wmic("csproduct UUID")
        or ""
    )


def _cpu_id() -> str:
    # CPU pode retornar multiplos sockets — pegar so o primeiro.
    return (
        _run_powershell("Win32_Processor", "ProcessorId", select_first=True)
        or _run_wmic("cpu ProcessorId")
        or ""
    )


def _hostname() -> str:
    try:
        return socket.gethostname() or ""
    except OSError:
        return ""


def build_fingerprint(sql_servername: str = "") -> HardwareFingerprint:
    """Collect the fingerprint factors from the current host.

    Args:
        sql_servername: Optional SQL Server @@SERVERNAME value — caller
            fornece a partir de config/config.yaml ou env. Vazio = factor
            ignorado (backward compat). Quando populado AND license tambem
            populou, e hard-match (mais estringente que os 3 base).
    """
    return HardwareFingerprint(
        bios_uuid=_bios_uuid(),
        cpu_id=_cpu_id(),
        hostname=_hostname(),
        sql_servername=sql_servername,
    )
