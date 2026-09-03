"""Unit tests for deploy.license_cli (vendor-side multi-tier CLI)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Make deploy/ importable
_DEPLOY_DIR = Path(__file__).resolve().parent.parent.parent / "deploy"
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))

import license_cli as cli  # type: ignore[import-not-found]


@pytest.fixture
def tmp_priv_key(tmp_path: Path) -> Path:
    """Generate throwaway private key in tmp."""
    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "ed25519_private.pem"
    key_path.write_bytes(pem)
    return key_path


# ---------- TIER_FEATURES integrity ----------------------------------------

def test_tier_features_has_all_4_editions():
    assert set(cli.TIER_FEATURES.keys()) == {
        "standard", "pro_standard", "pro_enhanced_sovereign", "pro_enhanced_banking"
    }


def test_pro_standard_is_superset_of_standard():
    """V5 deve incluir todas features V3.3 standard."""
    std = set(cli.TIER_FEATURES["standard"].keys())
    pro = set(cli.TIER_FEATURES["pro_standard"].keys())
    assert std.issubset(pro)


def test_pro_enhanced_sovereign_is_superset_of_pro_standard():
    pro = set(cli.TIER_FEATURES["pro_standard"].keys())
    sov = set(cli.TIER_FEATURES["pro_enhanced_sovereign"].keys())
    assert pro.issubset(sov)
    # V5.5 deve adicionar suprema_corte
    assert "suprema_corte_tribunal" in sov


def test_pro_enhanced_banking_is_superset_of_sovereign():
    sov = set(cli.TIER_FEATURES["pro_enhanced_sovereign"].keys())
    bank = set(cli.TIER_FEATURES["pro_enhanced_banking"].keys())
    assert sov.issubset(bank)
    # V6 banking-specific
    assert "ddl_change_risk_advisor" in bank
    assert "mandatory_suprema_escalation" in bank
    assert "banking_compliance_module" in bank


# ---------- INDUSTRY_PRESETS integrity --------------------------------------

def test_banking_pt_preset_has_correct_regimes():
    p = cli.INDUSTRY_PRESETS["banking_pt"]
    assert p["industry"] == "banking"
    assert "GDPR" in p["regimes"]
    assert "EBA" in p["regimes"]
    assert "BdP" in p["regimes"]
    assert p["edition_default"] == "pro_enhanced_banking"


def test_healthcare_us_preset_has_hipaa():
    p = cli.INDUSTRY_PRESETS["healthcare_us"]
    assert p["industry"] == "healthcare"
    assert "HIPAA" in p["regimes"]


# ---------- cmd_issue ------------------------------------------------------

def test_cmd_issue_single_license(tmp_path: Path, tmp_priv_key: Path):
    out_path = tmp_path / "test.lic"
    exit_code = cli.main([
        "issue",
        "--customer-id", "test-001",
        "--customer-name", "Test Corp",
        "--edition", "pro_standard",
        "--expires", "2027-04-25",
        "--bios-uuid", "AABBCCDD",
        "--cpu-id", "BFEBFBFF",
        "--hostname", "TEST-HOST",
        "--private-key", str(tmp_priv_key),
        "--out", str(out_path),
    ])
    assert exit_code == 0
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["customer_id"] == "test-001"
    assert payload["edition"] == "pro_standard"
    assert payload["features"]["ai_assistant_service"] is True
    assert "signature" in payload
    assert "license_id" in payload  # auto-generated UUID


def test_cmd_issue_preset_banking_pt(tmp_path: Path, tmp_priv_key: Path):
    out_path = tmp_path / "test.lic"
    exit_code = cli.main([
        "issue",
        "--customer-id", "bank-001",
        "--preset", "banking_pt",
        "--expires", "2027-04-25",
        "--bios-uuid", "AA",
        "--cpu-id", "BB",
        "--hostname", "BANK-SQL",
        "--sql-servername", "BANK-SQL\\PROD",
        "--private-key", str(tmp_priv_key),
        "--out", str(out_path),
    ])
    assert exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["edition"] == "pro_enhanced_banking"
    assert payload["industry"] == "banking"
    assert "EBA" in payload["regulatory_regime"]
    assert "BdP" in payload["regulatory_regime"]
    assert payload["hw_fingerprint"]["sql_servername"] == "BANK-SQL\\PROD"


def test_cmd_issue_invalid_edition_rejected(tmp_path: Path, tmp_priv_key: Path):
    # argparse choices rejects with SystemExit(2)
    with pytest.raises(SystemExit) as excinfo:
        cli.main([
            "issue",
            "--customer-id", "x",
            "--edition", "ultra_premium",  # invalid
            "--expires", "2027-04-25",
            "--bios-uuid", "AA", "--cpu-id", "BB", "--hostname", "X",
            "--private-key", str(tmp_priv_key),
        ])
    assert excinfo.value.code == 2


def test_cmd_issue_features_json_override(tmp_path: Path, tmp_priv_key: Path):
    """--features-json permite ligar features default-OFF."""
    out_path = tmp_path / "test.lic"
    # qlora_training_exposure default OFF em pro_standard
    exit_code = cli.main([
        "issue",
        "--customer-id", "cust-1",
        "--edition", "pro_standard",
        "--expires", "2027-04-25",
        "--bios-uuid", "A", "--cpu-id", "B", "--hostname", "H",
        "--features-json", '{"qlora_training_exposure": true}',
        "--private-key", str(tmp_priv_key),
        "--out", str(out_path),
    ])
    assert exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["features"]["qlora_training_exposure"] is True


def test_cmd_issue_features_json_invalid(tmp_path: Path, tmp_priv_key: Path, capsys):
    exit_code = cli.main([
        "issue",
        "--customer-id", "x",
        "--edition", "pro_standard",
        "--expires", "2027-04-25",
        "--bios-uuid", "A", "--cpu-id", "B", "--hostname", "H",
        "--features-json", "not valid json",
        "--private-key", str(tmp_priv_key),
        "--out", str(tmp_path / "x.lic"),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "features-json invalid" in err


# ---------- cmd_batch -------------------------------------------------------

def test_cmd_batch_csv_emits_multiple_licenses(tmp_path: Path, tmp_priv_key: Path):
    csv_path = tmp_path / "customers.csv"
    csv_path.write_text(
        "customer_id,customer_name,edition,expires,bios_uuid,cpu_id,hostname,industry,regimes,sql_servername\n"
        "cust-001,Cliente A,pro_standard,2027-04-25,AABB,CCDD,HOST-A,retail,GDPR,\n"
        "cust-002,Cliente B,pro_enhanced_banking,2027-04-25,EEFF,1122,HOST-B,banking,GDPR;EBA;BdP,SQL-B\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    exit_code = cli.main([
        "batch",
        "--input", str(csv_path),
        "--output-dir", str(out_dir),
        "--private-key", str(tmp_priv_key),
    ])
    assert exit_code == 0
    licenses = list(out_dir.glob("*.lic"))
    assert len(licenses) == 2

    # Validate one
    cust_a = json.loads((out_dir / "cust-001.lic").read_text(encoding="utf-8"))
    assert cust_a["edition"] == "pro_standard"
    assert cust_a["industry"] == "retail"

    cust_b = json.loads((out_dir / "cust-002.lic").read_text(encoding="utf-8"))
    assert cust_b["edition"] == "pro_enhanced_banking"
    assert cust_b["regulatory_regime"] == ["GDPR", "EBA", "BdP"]
    assert cust_b["hw_fingerprint"]["sql_servername"] == "SQL-B"


def test_cmd_batch_skips_invalid_rows(tmp_path: Path, tmp_priv_key: Path, capsys):
    csv_path = tmp_path / "customers.csv"
    csv_path.write_text(
        "customer_id,customer_name,edition,expires,bios_uuid,cpu_id,hostname\n"
        "good-001,Good,pro_standard,2027-04-25,AA,BB,HOST\n"
        "bad-001,Bad,fake_edition,2027-04-25,CC,DD,HOST2\n"
        "good-002,Good2,standard,2027-04-25,EE,FF,HOST3\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    exit_code = cli.main([
        "batch",
        "--input", str(csv_path),
        "--output-dir", str(out_dir),
        "--private-key", str(tmp_priv_key),
    ])
    assert exit_code == 1  # had failures
    licenses = list(out_dir.glob("*.lic"))
    assert len(licenses) == 2  # only 2 valid issued
    assert (out_dir / "good-001.lic").exists()
    assert (out_dir / "good-002.lic").exists()


# ---------- cmd_features --------------------------------------------------

def test_cmd_features_lists_tier(capsys):
    exit_code = cli.main(["features", "--tier", "pro_enhanced_banking"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "pro_enhanced_banking" in out
    assert "ddl_change_risk_advisor" in out
    assert "53 features" in out


def test_cmd_features_invalid_tier_rejected():
    # argparse choices rejects with SystemExit
    with pytest.raises(SystemExit):
        cli.main(["features", "--tier", "ultra"])


# ---------- cmd_revoke -----------------------------------------------------

def test_cmd_revoke_creates_new_crl(tmp_path: Path, tmp_priv_key: Path):
    crl_path = tmp_path / "revoked.json"
    exit_code = cli.main([
        "revoke",
        "--license-id", "lic-uuid-001",
        "--reason", "test contract terminated",
        "--crl", str(crl_path),
        "--private-key", str(tmp_priv_key),
    ])
    assert exit_code == 0
    assert crl_path.exists()

    crl_doc = json.loads(crl_path.read_text(encoding="utf-8"))
    assert crl_doc["version"] == 1
    assert "signature" in crl_doc
    assert len(crl_doc["revocations"]) == 1
    assert crl_doc["revocations"][0]["license_id"] == "lic-uuid-001"
    assert "test contract" in crl_doc["revocations"][0]["reason"]


def test_cmd_revoke_appends_to_existing_crl(tmp_path: Path, tmp_priv_key: Path):
    crl_path = tmp_path / "revoked.json"
    cli.main(["revoke", "--license-id", "lic-001", "--reason", "first",
              "--crl", str(crl_path), "--private-key", str(tmp_priv_key)])
    cli.main(["revoke", "--license-id", "lic-002", "--reason", "second",
              "--crl", str(crl_path), "--private-key", str(tmp_priv_key)])

    crl_doc = json.loads(crl_path.read_text(encoding="utf-8"))
    assert len(crl_doc["revocations"]) == 2
    ids = {r["license_id"] for r in crl_doc["revocations"]}
    assert ids == {"lic-001", "lic-002"}


def test_cmd_revoke_skips_duplicate(tmp_path: Path, tmp_priv_key: Path, capsys):
    crl_path = tmp_path / "revoked.json"
    cli.main(["revoke", "--license-id", "lic-dupe", "--reason", "first",
              "--crl", str(crl_path), "--private-key", str(tmp_priv_key)])
    cli.main(["revoke", "--license-id", "lic-dupe", "--reason", "duplicate",
              "--crl", str(crl_path), "--private-key", str(tmp_priv_key)])

    crl_doc = json.loads(crl_path.read_text(encoding="utf-8"))
    assert len(crl_doc["revocations"]) == 1  # nao duplicou


# ---------- cmd_fingerprint -----------------------------------------------

def test_cmd_fingerprint_prints_template(capsys):
    exit_code = cli.main(["fingerprint"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Win32_ComputerSystemProduct" in out
    assert "@@SERVERNAME" in out
    assert "csv" in out.lower()
