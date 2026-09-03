r"""
license_cli.py — Vendor workflow tool: emite license.dat per-customer per-tier.

Sprint FIND-20260424-005 follow-up: vendor-side CLI standalone que wraps
watcherdb.licensing.generator.build_license() com per-tier feature defaults +
industry presets + batch mode.

Tools:
  issue       — emit single license.dat
  batch       — emit multiple licenses from CSV input
  features    — list features per tier (audit/debug)
  fingerprint — collect hw fingerprint do servidor cliente (helper)

Usage:

    # Single license (V6 banking)
    python deploy/license_cli.py issue \
        --customer-id <uuid> \
        --customer-name "Banco XYZ Portugal" \
        --edition pro_enhanced_banking \
        --industry banking \
        --regimes GDPR EBA BdP DORA \
        --bios-uuid AABBCCDD-1111-2222-3333-444455556666 \
        --cpu-id BFEBFBFF00090672 \
        --hostname BANKXYZ-SQL01 \
        --sql-servername SQLBANKPRD01 \
        --expires 2027-04-25 \
        --out banco_xyz.lic

    # Industry preset (banking_pt)
    python deploy/license_cli.py issue \
        --customer-id <uuid> --customer-name "Banco XYZ" \
        --edition pro_enhanced_banking --preset banking_pt \
        --bios-uuid ... --cpu-id ... --hostname ... \
        --expires 2027-04-25 --out banco_xyz.lic

    # Batch from CSV
    python deploy/license_cli.py batch \
        --input customers.csv --output-dir ./licenses/

    # List features per tier
    python deploy/license_cli.py features --tier pro_enhanced_banking

    # Collect fingerprint (helper para vendor consultar quando recebe wmic do cliente)
    python deploy/license_cli.py fingerprint --print-template

Vendor-side ONLY — requires private key em
%USERPROFILE%\.watcherdb-council-secrets\ed25519_private.pem.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid as uuid_lib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Adicionar parent dir ao sys.path para import watcherdb.licensing.generator
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from watcherdb.licensing.generator import (  # type: ignore[import-not-found]
    DEFAULT_PRIVATE_KEY_PATH,
    _load_private_key,
    _parse_date,
    build_license,
)

# ===========================================================================
# TIER FEATURE DEFAULTS
# ===========================================================================
# Mantido manualmente em sync com cada tier feature_registry.py *_ALLOWLIST.
# Alteracao em allowlist runtime → ATUALIZAR este dict.
# ===========================================================================

TIER_FEATURES: Dict[str, Dict[str, bool]] = {
    "standard": {
        # V3.3 Standard
        "core_monitoring": True,
        "intelligence_kpis": True,
        "performance_module": True,
        "dba_copilot_rule_based": True,
        "capacity_planning_basic": False,  # opt-in tier
    },
    "pro_standard": {
        # V5 Pro Standard = Standard + AI/ML stack
        "core_monitoring": True,
        "intelligence_kpis": True,
        "performance_module": True,
        "dba_copilot_rule_based": True,
        "capacity_planning_basic": True,
        "ai_assistant_service": True,
        "expert_swarm": True,
        "knowledge_graph": True,
        "ollama_local_inference": True,
        "rag_engine": True,
        "cognitive_rag": True,
        "semantic_rag": True,
        "rlhf_enabled": True,
        "predictive_alerts": True,
        "capacity_planning_advanced": True,
        "sla_calculator": True,
        "risk_scoring": True,
        "anomaly_detection": True,
        "correlation_engine": True,
        "health_score_engine": True,
        "autonomous_agent": True,
        "cascade_intelligence": True,
        "shap_explainability": True,
        "qlora_training_exposure": False,  # default off — cliente activa explicitamente
    },
    "pro_enhanced_sovereign": {
        # V5.5 = V5 + Suprema Corte tiered + multi-model sovereign
        # (todas keys do V5 ON + as novas)
        "core_monitoring": True, "intelligence_kpis": True, "performance_module": True,
        "dba_copilot_rule_based": True, "capacity_planning_basic": True,
        "ai_assistant_service": True, "expert_swarm": True, "knowledge_graph": True,
        "ollama_local_inference": True, "rag_engine": True, "cognitive_rag": True,
        "semantic_rag": True, "rlhf_enabled": True, "predictive_alerts": True,
        "capacity_planning_advanced": True, "sla_calculator": True, "risk_scoring": True,
        "anomaly_detection": True, "correlation_engine": True, "health_score_engine": True,
        "autonomous_agent": True, "cascade_intelligence": True, "shap_explainability": True,
        "qlora_training_exposure": False,
        # V5.5 sovereign extras
        "suprema_corte": True,
        "suprema_corte_tribunal": True,
        "suprema_corte_red_team": True,
        "suprema_corte_socratic": True,
        "suprema_corte_resonance": True,
        "suprema_corte_temporal": True,
        "suprema_corte_classifier": True,
        "suprema_corte_orchestrator": True,
        "multi_model_sovereign": True,
        "recommendation_taxonomy": True,
        "response_humanization": True,
        "temporal_coherence_detection": True,
        "meta_resonance_label": True,
        "appeal_decision_audit": True,
    },
    "pro_enhanced_banking": {
        # V6 = V5.5 + banking compliance module
        "core_monitoring": True, "intelligence_kpis": True, "performance_module": True,
        "dba_copilot_rule_based": True, "capacity_planning_basic": True,
        "ai_assistant_service": True, "expert_swarm": True, "knowledge_graph": True,
        "ollama_local_inference": True, "rag_engine": True, "cognitive_rag": True,
        "semantic_rag": True, "rlhf_enabled": True, "predictive_alerts": True,
        "capacity_planning_advanced": True, "sla_calculator": True, "risk_scoring": True,
        "anomaly_detection": True, "correlation_engine": True, "health_score_engine": True,
        "autonomous_agent": True, "cascade_intelligence": True, "shap_explainability": True,
        "qlora_training_exposure": True,  # banking quer auditoria training data
        "suprema_corte": True, "suprema_corte_tribunal": True,
        "suprema_corte_red_team": True, "suprema_corte_socratic": True,
        "suprema_corte_resonance": True, "suprema_corte_temporal": True,
        "suprema_corte_classifier": True, "suprema_corte_orchestrator": True,
        "multi_model_sovereign": True, "recommendation_taxonomy": True,
        "response_humanization": True, "temporal_coherence_detection": True,
        "meta_resonance_label": True, "appeal_decision_audit": True,
        # V6 banking-specific
        "ddl_change_risk_advisor": True,
        "mandatory_suprema_escalation": True,
        "banking_core_path_detection": True,
        "banking_compliance_module": True,
        "eba_gl_ict_risk_compliance": True,
        "bdp_circular_ict_compliance": True,
        "dora_art16_audit_retention": True,
        "gdpr_pii_removal_workflow": True,
        "critical_ddl_not_reviewed_audit": True,
        "banking_strict_llm_guards": True,
        "sovereign_ai_air_gapped": True,
        "signed_timestamps": True,
        "audit_chain_hash": True,
        "two_bucket_retention": True,
        "white_label_branding": True,
    },
}

# Industry → regimes preset (ajusta a defaults expectados)
INDUSTRY_PRESETS: Dict[str, Dict[str, object]] = {
    "banking_pt": {
        "industry": "banking",
        "regimes": ["GDPR", "EBA", "BdP", "DORA", "SOC2"],
        "edition_default": "pro_enhanced_banking",
    },
    "banking_eu": {
        "industry": "banking",
        "regimes": ["GDPR", "EBA", "DORA", "SOC2"],
        "edition_default": "pro_enhanced_banking",
    },
    "healthcare_us": {
        "industry": "healthcare",
        "regimes": ["HIPAA", "SOC2", "ISO27001"],
        "edition_default": "pro_enhanced_sovereign",
    },
    "retail_eu": {
        "industry": "retail",
        "regimes": ["GDPR", "PCI-DSS"],
        "edition_default": "pro_standard",
    },
    "generic_pt_pro": {
        "industry": "generic",
        "regimes": ["GDPR"],
        "edition_default": "pro_standard",
    },
}

VALID_EDITIONS = ("standard", "pro_standard", "pro_enhanced_sovereign", "pro_enhanced_banking")


# ===========================================================================
# Sub-commands
# ===========================================================================


def cmd_issue(args: argparse.Namespace) -> int:
    """Emit single license.dat."""
    # Resolve preset if provided
    industry = args.industry or ""
    regimes = list(args.regimes) if args.regimes else []
    edition = args.edition

    if args.preset:
        preset = INDUSTRY_PRESETS.get(args.preset)
        if not preset:
            print(f"ERROR: unknown preset '{args.preset}'. Available: {list(INDUSTRY_PRESETS)}", file=sys.stderr)
            return 2
        industry = industry or str(preset["industry"])
        if not regimes:
            regimes = list(preset["regimes"])  # type: ignore[arg-type]
        if not edition:
            edition = str(preset["edition_default"])

    if not edition:
        print("ERROR: --edition required (or use --preset)", file=sys.stderr)
        return 2
    if edition not in VALID_EDITIONS:
        print(f"ERROR: invalid edition '{edition}'. Must be one of {VALID_EDITIONS}", file=sys.stderr)
        return 2

    # Features: per-tier defaults, override via --features-json
    features = dict(TIER_FEATURES.get(edition, {}))
    if args.features_json:
        try:
            override = json.loads(args.features_json)
            if not isinstance(override, dict):
                raise ValueError("must be JSON object")
            features.update({str(k): bool(v) for k, v in override.items()})
        except (json.JSONDecodeError, ValueError) as e:
            print(f"ERROR: --features-json invalid: {e}", file=sys.stderr)
            return 2

    license_id = args.license_id or str(uuid_lib.uuid4())

    priv = _load_private_key(Path(args.private_key))
    payload = build_license(
        customer_id=args.customer_id,
        expires_at=_parse_date(args.expires),
        bios_uuid=args.bios_uuid,
        cpu_id=args.cpu_id,
        hostname=args.hostname,
        edition=edition,
        tier=edition,
        features=features,
        private_key=priv,
        sql_servername=args.sql_servername,
        industry=industry,
        regulatory_regime=regimes,
        license_id=license_id,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"✓ Issued: {out}")
    print(f"  customer_id  : {args.customer_id}")
    if args.customer_name:
        print(f"  customer_name: {args.customer_name}")
    print(f"  edition      : {edition}")
    print(f"  expires      : {args.expires}")
    print(f"  industry     : {industry or '(none)'}")
    print(f"  regimes      : {regimes or '(none)'}")
    print(f"  license_id   : {license_id}")
    print(f"  features ON  : {sum(1 for v in features.values() if v)}/{len(features)}")
    if args.sql_servername:
        print(f"  sql_servername: {args.sql_servername} (banking-strict fingerprint)")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Emit licenses from CSV input.

    CSV columns required:
      customer_id, customer_name, edition, expires, bios_uuid, cpu_id, hostname
    Optional:
      industry, regimes (semicolon-separated), sql_servername, license_id, preset
    """
    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    priv = _load_private_key(Path(args.private_key))

    issued = 0
    failed = 0
    with args.input.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader, start=2):  # +1 header
            try:
                edition = (row.get("edition") or "").strip()
                if row.get("preset"):
                    preset = INDUSTRY_PRESETS.get(row["preset"].strip())
                    if preset and not edition:
                        edition = str(preset["edition_default"])

                if edition not in VALID_EDITIONS:
                    print(f"  [row {row_idx}] FAIL: invalid edition '{edition}'", file=sys.stderr)
                    failed += 1
                    continue

                features = dict(TIER_FEATURES.get(edition, {}))
                regimes = []
                if row.get("regimes"):
                    regimes = [r.strip() for r in row["regimes"].split(";") if r.strip()]

                license_id = (row.get("license_id") or "").strip() or str(uuid_lib.uuid4())

                payload = build_license(
                    customer_id=row["customer_id"].strip(),
                    expires_at=_parse_date(row["expires"].strip()),
                    bios_uuid=row["bios_uuid"].strip(),
                    cpu_id=row["cpu_id"].strip(),
                    hostname=row["hostname"].strip(),
                    edition=edition,
                    tier=edition,
                    features=features,
                    private_key=priv,
                    sql_servername=(row.get("sql_servername") or "").strip(),
                    industry=(row.get("industry") or "").strip(),
                    regulatory_regime=regimes,
                    license_id=license_id,
                )

                # Output filename: customer_id slug
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in row["customer_id"].strip())
                out_path = out_dir / f"{safe_name}.lic"
                out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
                print(f"  [row {row_idx}] OK: {out_path.name} ({edition}, expires {row['expires']})")
                issued += 1
            except Exception as e:
                print(f"  [row {row_idx}] FAIL: {e}", file=sys.stderr)
                failed += 1

    print(f"\nBatch complete: {issued} issued, {failed} failed")
    return 0 if failed == 0 else 1


def cmd_features(args: argparse.Namespace) -> int:
    """List features per tier."""
    if args.tier not in TIER_FEATURES:
        print(f"ERROR: unknown tier '{args.tier}'. Available: {list(TIER_FEATURES)}", file=sys.stderr)
        return 2

    features = TIER_FEATURES[args.tier]
    print(f"=== {args.tier} ({len(features)} features) ===")
    enabled = [k for k, v in features.items() if v]
    disabled = [k for k, v in features.items() if not v]
    print(f"\nDefault ON ({len(enabled)}):")
    for f in sorted(enabled):
        print(f"  + {f}")
    if disabled:
        print(f"\nDefault OFF ({len(disabled)}) — opt-in via --features-json:")
        for f in sorted(disabled):
            print(f"  - {f}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    """Add license_id to CRL (revoke). Re-signs whole CRL.

    Existing CRL extended (preserving previous revocations).
    Output: signed `revoked_licenses.json` ready para distribuir aos clients.
    """
    crl_path = Path(args.crl)
    revocations: list = []

    if crl_path.exists():
        try:
            existing = json.loads(crl_path.read_text(encoding="utf-8"))
            existing_revs = existing.get("revocations", [])
            if isinstance(existing_revs, list):
                revocations = list(existing_revs)
        except json.JSONDecodeError:
            print(f"WARN: existing CRL malformed, starting fresh: {crl_path}", file=sys.stderr)

    if any(r.get("license_id") == args.license_id for r in revocations):
        print(f"WARN: license_id {args.license_id} already revoked. Skipping.", file=sys.stderr)
        return 0

    revocations.append({
        "license_id": args.license_id,
        "revoked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reason": args.reason or "unspecified",
    })

    from watcherdb.licensing.generator import build_crl  # type: ignore[import-not-found]
    priv = _load_private_key(Path(args.private_key))
    payload = build_crl(revocations, priv)

    crl_path.parent.mkdir(parents=True, exist_ok=True)
    crl_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Revoked: {args.license_id}")
    print(f"  CRL: {crl_path} ({len(revocations)} total revocations)")
    print(f"  Reason: {args.reason or 'unspecified'}")
    return 0


def cmd_fingerprint(args: argparse.Namespace) -> int:
    """Helper para vendor: print template das WMIC commands a correr no servidor cliente."""
    print(r"""
=== WatcherDB License — Hardware Fingerprint Collection ===

Run estes commands no servidor cliente (PowerShell elevated) e copia os values
para o vendor:

PowerShell:
    (Get-CimInstance Win32_ComputerSystemProduct).UUID
    (Get-CimInstance Win32_Processor).ProcessorId
    [System.Net.Dns]::GetHostName()

Ou WMIC (legacy):
    wmic csproduct get UUID /value
    wmic cpu get ProcessorId /value
    hostname

Para banking strict mode (V6), incluir tambem SQL Server SERVERNAME:
    sqlcmd -E -S <YOUR_SQL_INSTANCE> -Q "SELECT @@SERVERNAME"

Envia os 3 (ou 4 para banking) values ao vendor WatcherDB para emissao de license.dat.

=== Sample CSV row para batch mode ===

customer_id,customer_name,edition,expires,bios_uuid,cpu_id,hostname,industry,regimes,sql_servername
banco-xyz-001,Banco XYZ Portugal,pro_enhanced_banking,2027-04-25,AABBCCDD-1111-...,BFEBFBFF...,BANKXYZ-SQL01,banking,GDPR;EBA;BdP;DORA,SQLBANKPRD01\\I01
""")
    return 0


# ===========================================================================
# CLI dispatch
# ===========================================================================


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- issue ----
    p_issue = sub.add_parser("issue", help="Emit single license.dat")
    p_issue.add_argument("--customer-id", required=True)
    p_issue.add_argument("--customer-name", default="")
    p_issue.add_argument("--edition", choices=VALID_EDITIONS)
    p_issue.add_argument("--preset", choices=list(INDUSTRY_PRESETS))
    p_issue.add_argument("--expires", required=True, help="YYYY-MM-DD ou ISO-8601")
    p_issue.add_argument("--bios-uuid", required=True)
    p_issue.add_argument("--cpu-id", required=True)
    p_issue.add_argument("--hostname", required=True)
    p_issue.add_argument("--sql-servername", default="", help="@@SERVERNAME (banking-strict)")
    p_issue.add_argument("--industry", default="")
    p_issue.add_argument("--regimes", nargs="*", default=[])
    p_issue.add_argument("--license-id", default="", help="UUID — auto se omitido")
    p_issue.add_argument("--features-json", default="", help="JSON object para override per-feature")
    p_issue.add_argument("--private-key", default=str(DEFAULT_PRIVATE_KEY_PATH))
    p_issue.add_argument("--out", default="license.dat")
    p_issue.set_defaults(func=cmd_issue)

    # ---- batch ----
    p_batch = sub.add_parser("batch", help="Emit licenses from CSV input")
    p_batch.add_argument("--input", type=Path, required=True)
    p_batch.add_argument("--output-dir", default="./licenses")
    p_batch.add_argument("--private-key", default=str(DEFAULT_PRIVATE_KEY_PATH))
    p_batch.set_defaults(func=cmd_batch)

    # ---- features ----
    p_feat = sub.add_parser("features", help="List features per tier")
    p_feat.add_argument("--tier", required=True, choices=VALID_EDITIONS)
    p_feat.set_defaults(func=cmd_features)

    # ---- revoke ----
    p_revoke = sub.add_parser("revoke", help="Add license_id to CRL (revoke)")
    p_revoke.add_argument("--license-id", required=True, help="UUID da license a revogar")
    p_revoke.add_argument("--reason", default="", help="Razao da revogacao (audit)")
    p_revoke.add_argument("--crl", default="revoked_licenses.json", help="Path do CRL (existente ou novo)")
    p_revoke.add_argument("--private-key", default=str(DEFAULT_PRIVATE_KEY_PATH))
    p_revoke.set_defaults(func=cmd_revoke)

    # ---- fingerprint ----
    p_fp = sub.add_parser("fingerprint", help="Print fingerprint collection template")
    p_fp.add_argument("--print-template", action="store_true", default=True)
    p_fp.set_defaults(func=cmd_fingerprint)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
