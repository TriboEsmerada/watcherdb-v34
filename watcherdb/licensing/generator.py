"""
Internal CLI for issuing `license.dat` to a customer — maintainer tool.

Runs on a trusted workstation only. Requires the Ed25519 private key that
lives outside this repository (default
``%USERPROFILE%\\.watcherdb-council-secrets\\ed25519_private.pem``).

Usage::

    python -m watcherdb.licensing.generator \
        --customer-id 7b3e5e74-... \
        --expires 2027-04-22 \
        --bios-uuid ABCD-... \
        --cpu-id BFEBFBFF00090672 \
        --hostname CLIENT-SQL01 \
        --out ./license.dat

The script deliberately lives inside the package so the payload format is
defined next to the validator — any change to the schema is enforced by
unit tests in both directions.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_PRIVATE_KEY_PATH = Path(
    os.environ.get(
        "WATCHERDB_LICENSE_PRIVATE_KEY",
        str(Path(os.environ.get("USERPROFILE", "")) / ".watcherdb-council-secrets" / "ed25519_private.pem"),
    )
)

DEFAULT_FEATURES: Dict[str, bool] = {
    "core_monitoring": True,
    "intelligence_kpis": True,
    "performance_module": True,
    "dba_copilot_rule_based": True,
    "capacity_planning_basic": False,
}


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit(f"Private key at {path} is not Ed25519.")
    return key


def _parse_date(value: str) -> datetime:
    if len(value) == 10:
        value = f"{value}T00:00:00+00:00"
    value = value.replace("Z", "+00:00") if value.endswith("Z") else value
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def build_license(
    *,
    customer_id: str,
    expires_at: datetime,
    bios_uuid: str,
    cpu_id: str,
    hostname: str,
    edition: str = "standard",
    tier: str = "standard",
    features: Optional[Dict[str, bool]] = None,
    issued_at: Optional[datetime] = None,
    private_key: Ed25519PrivateKey,
    sql_servername: str = "",
    industry: str = "",
    regulatory_regime: Optional[list] = None,
    license_id: str = "",
) -> Dict:
    """Build and sign a license dict. Returns the full payload incl. signature.

    Optional fields (FIND-20260424-001 B5):
        sql_servername: SQL @@SERVERNAME for banking-strict fingerprint binding.
        industry: banking|healthcare|retail|govt|generic.
        regulatory_regime: lista de regimes (GDPR, EBA, BdP, HIPAA, PCI-DSS).
        license_id: UUID unico por emissao (usado por CRL futuro).
    """
    hw_fingerprint = {"bios_uuid": bios_uuid, "cpu_id": cpu_id, "hostname": hostname}
    if sql_servername:
        hw_fingerprint["sql_servername"] = sql_servername

    payload = {
        "customer_id": customer_id,
        "edition": edition,
        "tier": tier,
        "features": features or dict(DEFAULT_FEATURES),
        "issued_at": (issued_at or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "hw_fingerprint": hw_fingerprint,
    }
    # Optional fields — so incluir se fornecidos para nao poluir licenses basicas
    if industry:
        payload["industry"] = industry
    if regulatory_regime:
        payload["regulatory_regime"] = list(regulatory_regime)
    if license_id:
        payload["license_id"] = license_id

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(canonical)
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--expires", required=True, help="YYYY-MM-DD or full ISO-8601")
    parser.add_argument("--bios-uuid", required=True)
    parser.add_argument("--cpu-id", required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--edition", default="standard", choices=["standard", "pro", "enterprise"])
    parser.add_argument("--private-key", default=str(DEFAULT_PRIVATE_KEY_PATH))
    parser.add_argument("--out", default="license.dat")
    # B5: Banking-strict fingerprint + industry/compliance metadata
    parser.add_argument("--sql-servername", default="", help="SQL Server @@SERVERNAME (hard-match factor para banking)")
    parser.add_argument("--industry", default="", choices=["", "banking", "healthcare", "retail", "govt", "generic"])
    parser.add_argument("--regulatory-regime", nargs="*", default=[], help="Regimes: GDPR EBA BdP HIPAA PCI-DSS SOC2 ISO27001 DORA PSD2")
    parser.add_argument("--license-id", default="", help="UUID unico desta emissao (para CRL futuro)")
    args = parser.parse_args(argv)

    priv = _load_private_key(Path(args.private_key))
    payload = build_license(
        customer_id=args.customer_id,
        expires_at=_parse_date(args.expires),
        bios_uuid=args.bios_uuid,
        cpu_id=args.cpu_id,
        hostname=args.hostname,
        edition=args.edition,
        tier=args.edition,
        private_key=priv,
        sql_servername=args.sql_servername,
        industry=args.industry,
        regulatory_regime=args.regulatory_regime,
        license_id=args.license_id,
    )
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    extras = []
    if args.sql_servername: extras.append(f"sql={args.sql_servername}")
    if args.industry: extras.append(f"industry={args.industry}")
    if args.regulatory_regime: extras.append(f"regimes={'+'.join(args.regulatory_regime)}")
    extras_str = f" [{', '.join(extras)}]" if extras else ""
    print(f"Wrote {args.out} (edition={args.edition}, expires={args.expires}, customer_id={args.customer_id}){extras_str}")
    return 0


def build_crl(
    revocations: list,
    private_key: Ed25519PrivateKey,
    *,
    issued_at: Optional[datetime] = None,
    version: int = 1,
) -> Dict:
    """Build + sign CRL (revoked_licenses.json) — sub-task B5.2 FIND-005.

    Args:
        revocations: list of dicts com keys license_id, revoked_at (ISO),
            optional reason. Caller responsavel por garantir UUIDs validos.
        private_key: Ed25519 vendor master key.
        issued_at: timestamp do CRL emission (default now UTC).
        version: schema version (apenas 1 suportado actualmente).

    Returns:
        dict com payload + signature, ready para json.dumps + write to file.
    """
    payload = {
        "version": version,
        "issued_at": (issued_at or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "revocations": [
            {
                "license_id": str(r["license_id"]),
                "revoked_at": str(r.get("revoked_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
                "reason": str(r.get("reason", "")),
            }
            for r in revocations
            if r.get("license_id")
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(canonical)
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


if __name__ == "__main__":
    sys.exit(main())
