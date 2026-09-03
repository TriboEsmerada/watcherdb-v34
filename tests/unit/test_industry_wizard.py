"""Unit tests for deploy.industry_wizard (B2 sprint install v0.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_DEPLOY_DIR = Path(__file__).resolve().parent.parent.parent / "deploy"
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))

import industry_wizard as iw  # type: ignore[import-not-found]


# ---------- WizardAnswers validation --------------------------------------

def test_validate_invalid_industry():
    ans = iw.WizardAnswers(industry="crypto", country="PT", regimes=["GDPR"])
    errors = ans.validate()
    assert any("industry must be one of" in e for e in errors)


def test_validate_invalid_country_format():
    ans = iw.WizardAnswers(industry="generic", country="Portugal", regimes=["GDPR"])
    errors = ans.validate()
    assert any("country" in e.lower() for e in errors)


def test_validate_unknown_regime():
    ans = iw.WizardAnswers(industry="generic", country="PT", regimes=["GDPR", "FAKE_LAW"])
    errors = ans.validate()
    assert any("FAKE_LAW" in e for e in errors)


def test_validate_banking_requires_core_procs():
    ans = iw.WizardAnswers(
        industry="banking", country="PT", regimes=["GDPR", "EBA"],
        banking_core_procs=[], deployment_tier="enterprise",
    )
    errors = ans.validate()
    assert any("banking_core_procs" in e for e in errors)


def test_validate_tier_invalid():
    ans = iw.WizardAnswers(
        industry="generic", country="PT", regimes=["GDPR"],
        deployment_tier="hobbyist",
    )
    errors = ans.validate()
    assert any("deployment_tier" in e for e in errors)


def test_validate_happy_path():
    ans = iw.WizardAnswers(
        industry="retail", country="PT", regimes=["GDPR", "PCI-DSS"],
        customer_name="TestCorp",
    )
    assert ans.validate() == []


# ---------- Rules derivation ----------------------------------------------

def test_derive_rules_banking_pt_enables_mandatory_suprema():
    ans = iw.WizardAnswers(
        industry="banking", country="PT", regimes=["GDPR", "EBA", "BdP", "DORA"],
        banking_core_procs=["dbo.usp_ScoreTransaction"],
        deployment_tier="enterprise",
    )
    rules = iw.derive_compliance_rules(ans)
    r = rules["rules"]
    assert r["mandatory_suprema_escalation"]["enabled"] is True
    assert r["banking_core_path_required"] is True
    assert r["ddl_change_review_required"] is True
    assert r["llm_blast_radius_gate"] is True
    assert r["pii_regex_region"] == "eu"
    # Max retention = DORA 1095
    assert r["audit_retention_days"] == 1095


def test_derive_rules_retail_us_minimal():
    ans = iw.WizardAnswers(
        industry="retail", country="US", regimes=["PCI-DSS"],
    )
    rules = iw.derive_compliance_rules(ans)
    r = rules["rules"]
    assert r["mandatory_suprema_escalation"]["enabled"] is False
    assert r["banking_core_path_required"] is False
    assert r["ddl_change_review_required"] is False
    assert r["pii_regex_region"] == "us"
    assert r["pci_dss_mode"] is True
    assert r["hipaa_phi_mode"] is False


def test_derive_rules_healthcare_hipaa():
    ans = iw.WizardAnswers(
        industry="healthcare", country="US", regimes=["HIPAA", "SOC2"],
    )
    rules = iw.derive_compliance_rules(ans)
    r = rules["rules"]
    assert r["hipaa_phi_mode"] is True
    assert r["audit_retention_days"] == 2190  # HIPAA 6y
    assert r["ddl_change_review_required"] is True


def test_derive_rules_gdpr_auto_detect_from_eu_country():
    ans = iw.WizardAnswers(
        industry="generic", country="FR", regimes=[],  # sem GDPR explicit
    )
    rules = iw.derive_compliance_rules(ans)
    # FR esta em lista EU member → GDPR pii_regex_enabled
    assert rules["rules"]["pii_regex_enabled"] is True
    assert rules["rules"]["pii_regex_region"] == "eu"


def test_derive_rules_prompt_template_name_format():
    ans = iw.WizardAnswers(industry="banking", primary_language="pt")
    rules = iw.derive_compliance_rules(ans)
    assert rules["rules"]["llm_prompt_template"] == "banking_pt.txt"


# ---------- Presets --------------------------------------------------------

def test_preset_banking_pt():
    ans = iw.load_preset("banking_pt")
    assert ans.industry == "banking"
    assert "EBA" in ans.regimes
    assert "BdP" in ans.regimes
    assert ans.country == "PT"


def test_preset_unknown_raises():
    with pytest.raises(ValueError, match="unknown preset"):
        iw.load_preset("unobtainium")


# ---------- Config file loader --------------------------------------------

def test_load_config_json(tmp_path: Path):
    config = tmp_path / "answers.json"
    config.write_text(json.dumps({
        "industry": "retail",
        "country": "PT",
        "regimes": ["GDPR", "PCI-DSS"],
        "customer_name": "TestCorp",
        "deployment_tier": "standard",
        "primary_language": "pt",
    }), encoding="utf-8")
    ans = iw.load_config(config)
    assert ans.industry == "retail"
    assert "PCI-DSS" in ans.regimes


def test_load_config_minimal_yaml(tmp_path: Path):
    config = tmp_path / "answers.yaml"
    config.write_text(
        "industry: banking\n"
        "country: PT\n"
        "primary_language: pt\n"
        "customer_name: TestBank\n"
        "deployment_tier: enterprise\n"
        "regimes:\n"
        "  - GDPR\n"
        "  - EBA\n"
        "banking_core_procs:\n"
        "  - dbo.usp_Score\n",
        encoding="utf-8",
    )
    ans = iw.load_config(config)
    assert ans.industry == "banking"
    assert "GDPR" in ans.regimes
    assert "EBA" in ans.regimes
    assert ans.banking_core_procs == ["dbo.usp_Score"]


# ---------- File output ----------------------------------------------------

def test_write_outputs(tmp_path: Path):
    ans = iw.WizardAnswers(
        industry="banking", country="PT", regimes=["GDPR", "EBA"],
        banking_core_procs=["dbo.usp_X"],
        customer_name="TestBank",
        deployment_tier="enterprise",
    )
    context = iw.build_client_context(ans)
    rules = iw.derive_compliance_rules(ans)

    p1 = iw.write_client_context(tmp_path, context)
    p2 = iw.write_compliance_rules(tmp_path, rules)
    assert p1.exists()
    assert p2.exists()

    c1 = p1.read_text(encoding="utf-8")
    assert "industry: banking" in c1
    assert "# client_context.yaml" in c1  # header preservado
    c2 = p2.read_text(encoding="utf-8")
    assert "audit_retention_days" in c2
    assert "NAO editar manualmente" in c2


# ---------- CLI --------------------------------------------------------

def test_cli_preset_writes_both_files(tmp_path: Path):
    """Preset non-banking works standalone (banking needs core_procs — tested separately)."""
    exit_code = iw.main([
        "--preset", "retail_eu",
        "--output-dir", str(tmp_path),
    ])
    assert exit_code == 0
    assert (tmp_path / "client_context.yaml").exists()
    assert (tmp_path / "compliance_rules.yaml").exists()


def test_cli_banking_preset_alone_fails_without_procs(tmp_path: Path):
    """banking_pt preset correctly fails validation sem banking_core_procs."""
    exit_code = iw.main([
        "--preset", "banking_pt",
        "--output-dir", str(tmp_path),
    ])
    assert exit_code == 1  # validation error
    assert not (tmp_path / "client_context.yaml").exists()


def test_cli_dry_run_doesnt_write(tmp_path: Path, capsys):
    exit_code = iw.main([
        "--preset", "retail_eu",
        "--output-dir", str(tmp_path),
        "--dry-run",
    ])
    assert exit_code == 0
    assert not (tmp_path / "client_context.yaml").exists()


def test_cli_config_banking_valid_end_to_end(tmp_path: Path):
    config = tmp_path / "answers.json"
    config.write_text(json.dumps({
        "industry": "banking",
        "country": "PT",
        "regimes": ["GDPR", "EBA", "BdP"],
        "banking_core_procs": ["dbo.usp_AMLCheck"],
        "customer_name": "BankXYZ",
        "deployment_tier": "enterprise",
        "primary_language": "pt",
    }), encoding="utf-8")

    exit_code = iw.main([
        "--config", str(config),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 0
    rules_text = (tmp_path / "out" / "compliance_rules.yaml").read_text(encoding="utf-8")
    assert "audit_retention_days: 1095" in rules_text  # EBA 3y


def test_cli_config_invalid_returns_1(tmp_path: Path):
    config = tmp_path / "answers.json"
    config.write_text(json.dumps({
        "industry": "banking",  # banking sem banking_core_procs
        "country": "PT",
        "regimes": ["GDPR"],
        "customer_name": "X",
        "deployment_tier": "enterprise",
    }), encoding="utf-8")
    exit_code = iw.main([
        "--config", str(config),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 1
