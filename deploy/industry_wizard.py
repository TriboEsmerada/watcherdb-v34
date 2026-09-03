"""
industry_wizard.py — Post-install wizard que gera client_context.yaml +
compliance_rules.yaml conforme industry/regime escolhidos pelo cliente.

Sprint install flow v0.2 B2 (FIND-20260424-001).

Pergunta interactivamente (ou via --preset/--config para non-interactive):
  * Industry (banking | healthcare | retail | govt | generic)
  * Country (ISO-3166 alpha-2)
  * Regulatory regimes (multi-select: GDPR, EBA, BdP, HIPAA, PCI-DSS,
    SOC2, ISO27001, DORA, PSD2)
  * (Se banking) Lista de procs/tables criticos (BANKING_CORE_PATH)
  * (Se healthcare/banking) Audit retention days (default tier-aware)

Output (2 ficheiros em <install-dir>\\config\\ ou em C:\\ProgramData\\WatcherDB\\):
  * client_context.yaml — identidade industry/country/regime do cliente
  * compliance_rules.yaml — regras DERIVADAS (audit retention, PII regex,
    mandatory Suprema triggers, etc.) — NAO editar manualmente

Usage:
    python industry_wizard.py --output-dir C:\\ProgramData\\WatcherDB\\
    python industry_wizard.py --preset banking_pt --output-dir <dir>
    python industry_wizard.py --config wizard_answers.yaml  # non-interactive
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# ---------- Industry + regime domain model --------------------------------

INDUSTRIES = {
    "banking": "Banking / Financial Services",
    "healthcare": "Healthcare / Pharma / Life Sciences",
    "retail": "Retail / E-commerce",
    "govt": "Government / Public Sector",
    "generic": "Generic / Other",
}

REGIMES = {
    "GDPR": "EU General Data Protection Regulation",
    "EBA": "European Banking Authority Guidelines",
    "BdP": "Banco de Portugal Circulars",
    "DORA": "Digital Operational Resilience Act (EU banking)",
    "PSD2": "Payment Services Directive 2 (EU)",
    "HIPAA": "Health Insurance Portability and Accountability Act (US)",
    "PCI-DSS": "Payment Card Industry Data Security Standard",
    "SOC2": "SOC 2 Type II (US)",
    "ISO27001": "ISO/IEC 27001",
    "LGPD": "Lei Geral de Proteção de Dados (Brazil)",
}

# Industry → sensible default regimes
INDUSTRY_DEFAULT_REGIMES = {
    "banking": ["GDPR", "EBA", "BdP", "DORA", "SOC2"],
    "healthcare": ["GDPR", "HIPAA", "ISO27001"],
    "retail": ["GDPR", "PCI-DSS"],
    "govt": ["GDPR", "SOC2", "ISO27001"],
    "generic": ["GDPR"],
}

# Compliance rules templates per industry/regime combo
RETENTION_DAYS_BY_REGIME = {
    "GDPR": 365,          # 1y minimum
    "EBA": 1095,          # 3y ICT Risk
    "DORA": 1095,         # 3y DORA art. 16
    "BdP": 1095,          # Banco de Portugal ICT alignment
    "HIPAA": 2190,        # 6y HIPAA
    "SOC2": 1095,
    "PCI-DSS": 365,
    "ISO27001": 1095,
    "LGPD": 730,
}

PRESETS = {
    "banking_pt": {
        "industry": "banking",
        "country": "PT",
        "regimes": ["GDPR", "EBA", "BdP", "DORA", "SOC2"],
        "primary_language": "pt",
    },
    "banking_eu_generic": {
        "industry": "banking",
        "country": "EU",
        "regimes": ["GDPR", "EBA", "DORA", "SOC2"],
        "primary_language": "en",
    },
    "healthcare_us": {
        "industry": "healthcare",
        "country": "US",
        "regimes": ["HIPAA", "SOC2", "ISO27001"],
        "primary_language": "en",
    },
    "retail_eu": {
        "industry": "retail",
        "country": "EU",
        "regimes": ["GDPR", "PCI-DSS"],
        "primary_language": "en",
    },
}


@dataclass
class WizardAnswers:
    industry: str = "generic"
    country: str = ""
    regimes: List[str] = field(default_factory=list)
    primary_language: str = "en"
    banking_core_procs: List[str] = field(default_factory=list)
    banking_core_tables: List[str] = field(default_factory=list)
    audit_retention_days: int = 365
    customer_name: str = ""
    deployment_tier: str = "standard"  # standard | enterprise

    def validate(self) -> List[str]:
        """Return list of validation errors. Empty = OK."""
        errors = []
        if self.industry not in INDUSTRIES:
            errors.append(f"industry must be one of {list(INDUSTRIES)}")
        if self.country and not (len(self.country) in (2, 3) and self.country.isalpha()):
            errors.append(f"country must be ISO-3166 alpha-2 or EU (got '{self.country}')")
        invalid_regimes = [r for r in self.regimes if r not in REGIMES]
        if invalid_regimes:
            errors.append(f"unknown regimes: {invalid_regimes}")
        if self.industry == "banking" and not self.banking_core_procs:
            errors.append("banking industry requires banking_core_procs list (opt-in cliente)")
        if self.deployment_tier not in ("standard", "enterprise"):
            errors.append(f"deployment_tier must be 'standard' or 'enterprise'")
        return errors


# ---------- Rules derivation -----------------------------------------------


def derive_compliance_rules(ans: WizardAnswers) -> dict:
    """Derive concrete rules from industry + regime choices. Deterministic."""
    # Max retention across all regimes
    retention = max(
        (RETENTION_DAYS_BY_REGIME.get(r, 365) for r in ans.regimes),
        default=365,
    )
    if ans.audit_retention_days > retention:
        retention = ans.audit_retention_days  # user override wins if larger

    banking_strict = ans.industry == "banking"
    healthcare_strict = ans.industry == "healthcare"
    gdpr = "GDPR" in ans.regimes or ans.country in (
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
        "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
        "RO", "SK", "SI", "ES", "SE", "EU",
    )

    rules = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_from": {
            "industry": ans.industry,
            "country": ans.country,
            "regimes": list(ans.regimes),
        },
        "rules": {
            "audit_retention_days": retention,
            "pii_regex_enabled": gdpr or healthcare_strict or banking_strict,
            "pii_regex_region": _pii_region(ans.country),
            "ddl_change_review_required": banking_strict or healthcare_strict,
            "mandatory_suprema_escalation": {
                "enabled": banking_strict,  # V6 step 9e mandatory path
                "trigger": "severity_critical AND category_ddl_change" if banking_strict else None,
            },
            "banking_core_path_required": banking_strict,
            "banking_core_procs": list(ans.banking_core_procs),
            "banking_core_tables": list(ans.banking_core_tables),
            "llm_blast_radius_gate": banking_strict,
            "llm_prompt_template": _pick_prompt_template(ans),
            "two_bucket_retention": banking_strict or healthcare_strict,
            "signed_timestamps_required": banking_strict,
            "hipaa_phi_mode": healthcare_strict and "HIPAA" in ans.regimes,
            "pci_dss_mode": "PCI-DSS" in ans.regimes,
        },
    }
    return rules


def _pii_region(country: str) -> str:
    c = (country or "").upper()
    if c in ("PT", "ES", "FR", "IT", "DE", "EU"):
        return "eu"
    if c == "US":
        return "us"
    if c == "BR":
        return "br"
    return "generic"


def _pick_prompt_template(ans: WizardAnswers) -> str:
    """Derive LLM prompt template name per industry + language."""
    base = ans.industry
    lang = ans.primary_language or "en"
    return f"{base}_{lang}.txt"


def build_client_context(ans: WizardAnswers) -> dict:
    """Client identity document. User-editable (safe)."""
    return {
        "customer_name": ans.customer_name,
        "industry": ans.industry,
        "country": ans.country,
        "regimes": list(ans.regimes),
        "primary_language": ans.primary_language,
        "deployment_tier": ans.deployment_tier,
    }


# ---------- YAML writer (stdlib-only, no external dep) --------------------


def _yaml_dump(data, indent: int = 0) -> str:
    """Minimal YAML emitter (stdlib only) — suficiente para este config."""
    lines = []
    prefix = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{prefix}{k}:")
                lines.append(_yaml_dump(v, indent + 1))
            elif v is None:
                lines.append(f"{prefix}{k}: null")
            elif isinstance(v, bool):
                lines.append(f"{prefix}{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{prefix}{k}: {v}")
            else:
                # String — quote se contem chars especiais
                sv = str(v)
                if any(c in sv for c in ":#\n\"'[]{}"):
                    sv = '"' + sv.replace('\\', '\\\\').replace('"', '\\"') + '"'
                lines.append(f"{prefix}{k}: {sv}")
    elif isinstance(data, list):
        if not data:
            lines.append(f"{prefix}[]")
        else:
            for item in data:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    lines.append(_yaml_dump(item, indent + 1))
                else:
                    lines.append(f"{prefix}- {item}")
    else:
        lines.append(f"{prefix}{data}")
    return "\n".join(l for l in lines if l)


def write_client_context(output_dir: Path, context: dict) -> Path:
    path = output_dir / "client_context.yaml"
    header = (
        "# client_context.yaml — gerado pelo installer industry wizard\n"
        "# Editavel post-install (operador precisa de service restart).\n"
        "# Schema mantido pelo WatcherDB product team — nao adicionar keys custom.\n"
    )
    body = _yaml_dump(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body + "\n", encoding="utf-8")
    return path


def write_compliance_rules(output_dir: Path, rules: dict) -> Path:
    path = output_dir / "compliance_rules.yaml"
    header = (
        "# compliance_rules.yaml — DERIVADO de client_context.yaml\n"
        "# NAO editar manualmente. Re-run industry_wizard.py se precisar mudar.\n"
        "# Regras determinadas pelo installer com base em industry + regimes.\n"
    )
    body = _yaml_dump(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body + "\n", encoding="utf-8")
    return path


# ---------- Interactive wizard --------------------------------------------


def _prompt_choice(prompt: str, choices: dict, default: Optional[str] = None) -> str:
    print(f"\n{prompt}")
    keys = list(choices.keys())
    for i, k in enumerate(keys, 1):
        marker = " (default)" if k == default else ""
        print(f"  {i}) {k} — {choices[k]}{marker}")
    while True:
        raw = input("Escolha [1-{}]: ".format(len(keys))).strip()
        if not raw and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(keys):
                return keys[idx]
        except ValueError:
            pass
        print(f"  invalido, tenta de novo")


def _prompt_multi(prompt: str, choices: dict, defaults: List[str]) -> List[str]:
    print(f"\n{prompt}")
    keys = list(choices.keys())
    for i, k in enumerate(keys, 1):
        marker = " [x]" if k in defaults else " [ ]"
        print(f"  {i}){marker} {k} — {choices[k]}")
    print(f"  Defaults pre-seleccionados: {defaults}")
    raw = input("Numeros separados por virgula (vazio = usar defaults): ").strip()
    if not raw:
        return list(defaults)
    selected = []
    for part in raw.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(keys):
                selected.append(keys[idx])
        except ValueError:
            print(f"  ignorado: {part}")
    return selected or list(defaults)


def _prompt_string(prompt: str, default: str = "", allow_empty: bool = True) -> str:
    default_hint = f" [{default}]" if default else ""
    raw = input(f"{prompt}{default_hint}: ").strip()
    if not raw:
        if allow_empty or default:
            return default
        while True:
            raw = input(f"  required. {prompt}: ").strip()
            if raw:
                return raw
    return raw


def _prompt_list(prompt: str) -> List[str]:
    print(f"\n{prompt} (uma por linha; linha vazia para terminar)")
    items = []
    while True:
        raw = input("  > ").strip()
        if not raw:
            break
        items.append(raw)
    return items


def run_interactive() -> WizardAnswers:
    """Interactive wizard — retorna WizardAnswers preenchida."""
    print("=" * 70)
    print("WatcherDB Industry & Compliance Wizard")
    print("=" * 70)

    customer_name = _prompt_string("Customer name (empresa cliente)", allow_empty=False)
    industry = _prompt_choice("Industry:", INDUSTRIES, default="generic")
    country = _prompt_string("Country (ISO-3166 alpha-2, ex: PT, US, BR; 'EU' para genericamente EU)", "PT")

    regimes = _prompt_multi(
        "Regulatory regimes (multi-select):",
        REGIMES,
        defaults=INDUSTRY_DEFAULT_REGIMES.get(industry, ["GDPR"]),
    )

    language_choices = {"pt": "Português", "en": "English", "es": "Español", "fr": "Français"}
    primary_language = _prompt_choice("Primary language para AI responses:", language_choices, default="pt" if country == "PT" else "en")

    tier = _prompt_choice(
        "Deployment tier (se nao souberes, escolhe o que adquiriste):",
        {"standard": "V3.3 Standard Edition", "enterprise": "V6 Enterprise Edition"},
        default="standard",
    )

    banking_procs = []
    banking_tables = []
    if industry == "banking":
        print("\n🏦 Banking industry: preciso da lista de procs/tables core para flag BANKING_CORE_PATH.")
        banking_procs = _prompt_list("Procs core banking (ex: dbo.usp_ScoreTransaction)")
        banking_tables = _prompt_list("Tables core banking (ex: Accounts.Balance)")
        if not banking_procs and not banking_tables:
            print("  ⚠  Nenhum proc/table — Change Risk Advisor nao conseguira flag BANKING_CORE_PATH automaticamente.")

    ans = WizardAnswers(
        industry=industry,
        country=country.upper(),
        regimes=regimes,
        primary_language=primary_language,
        banking_core_procs=banking_procs,
        banking_core_tables=banking_tables,
        customer_name=customer_name,
        deployment_tier=tier,
    )
    return ans


# ---------- Non-interactive (preset + config file) ------------------------


def load_preset(preset_name: str) -> WizardAnswers:
    if preset_name not in PRESETS:
        raise ValueError(f"unknown preset '{preset_name}' (available: {list(PRESETS)})")
    p = PRESETS[preset_name]
    return WizardAnswers(
        industry=p["industry"],
        country=p["country"],
        regimes=list(p["regimes"]),
        primary_language=p["primary_language"],
        banking_core_procs=[],
        customer_name=f"PRESET_{preset_name}",
    )


def load_config(config_path: Path) -> WizardAnswers:
    """Load answers from JSON or YAML file for non-interactive runs."""
    text = config_path.read_text(encoding="utf-8")
    # Try JSON first (more strict)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Very minimal YAML parse (key: value lines only) — suficiente para config file
        data = _minimal_yaml_parse(text)
    return WizardAnswers(**{k: v for k, v in data.items() if k in WizardAnswers.__dataclass_fields__})


def _minimal_yaml_parse(text: str) -> dict:
    """Suporta só top-level key: value + listas simples — mesmo shape do _yaml_dump."""
    result = {}
    current_list_key = None
    current_list = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("-"):
            if current_list_key:
                current_list.append(s[1:].strip())
            continue
        if current_list_key:
            result[current_list_key] = current_list
            current_list_key = None
            current_list = []
        if ":" in s:
            k, _, v = s.partition(":")
            k = k.strip()
            v = v.strip()
            if not v:
                current_list_key = k
                current_list = []
            else:
                # Parse value
                if v.lower() in ("true", "false"):
                    result[k] = v.lower() == "true"
                elif v.isdigit():
                    result[k] = int(v)
                else:
                    result[k] = v.strip('"').strip("'")
    if current_list_key:
        result[current_list_key] = current_list
    return result


# ---------- CLI -----------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, required=True, help="Directorio onde escrever os 2 yamls")
    parser.add_argument("--preset", choices=list(PRESETS), help="Non-interactive: usar preset")
    parser.add_argument("--config", type=Path, help="Non-interactive: load answers de JSON/YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Validate + print mas nao escrever ficheiros")
    args = parser.parse_args(argv)

    # Modes: interactive, preset, config
    if args.config:
        ans = load_config(args.config)
    elif args.preset:
        ans = load_preset(args.preset)
    else:
        ans = run_interactive()

    errors = ans.validate()
    if errors:
        print("\nVALIDATION ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    context = build_client_context(ans)
    rules = derive_compliance_rules(ans)

    if args.dry_run:
        print("\n--- client_context.yaml ---")
        print(_yaml_dump(context))
        print("\n--- compliance_rules.yaml ---")
        print(_yaml_dump(rules))
        print("\n(dry-run: nada foi escrito)")
        return 0

    p1 = write_client_context(args.output_dir, context)
    p2 = write_compliance_rules(args.output_dir, rules)
    print(f"\nWrote {p1}")
    print(f"Wrote {p2}")
    print("\nRestart services para carregar configs:")
    print("  net stop WatcherDBWebServiceV33 && net start WatcherDBWebServiceV33")
    return 0


if __name__ == "__main__":
    sys.exit(main())
