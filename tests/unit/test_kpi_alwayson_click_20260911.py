"""
2026-09-11 -- modal KPI Always On: clicar na linha (instancia) nao pode ir ao resolvedor de AG.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_alwayson_click_skips_ag_resolver_for_instances():
    assert "const _aoLooksInstance = _aoKnown || /_I\\d+$/i.test(_aoNorm);" in PORTAL
    assert "resolvedor de AG dispensado" in PORTAL


def test_alwayson_click_never_alerts_ag_not_found():
    branch = PORTAL.split("if (kpiType === 'always-on') {\n                // 2026-09-11", 1)[1].split("// Remover domínio do nome", 1)[0]
    assert "alert(" not in branch and "closeInstancesModal();" not in branch
