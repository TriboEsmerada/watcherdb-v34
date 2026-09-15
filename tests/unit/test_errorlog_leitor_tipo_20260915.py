"""
2026-09-15 -- leitor do errorlog conta pelo tipo classificado (preparacao do B1b).
"""
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KPIS = (ROOT / "api" / "routers" / "intelligence_kpis.py").read_text(encoding="utf-8")


def test_bucket_por_tipo():
    from api.routers.intelligence.helpers import errorlog_bucket as b
    assert b({"Log_Type": "Critical", "Severity": 24}) == "critical"
    for t in ("Error", "AvailabilityGroup", "Lifecycle", "", None):
        assert b({"Log_Type": t}) == "warning", t
    for t in ("Security", "Repetitive", "Info"):
        assert b({"Log_Type": t, "Severity": 17}) is None, t
    # linha antiga do recolhedor: Log_Type 'Error' e Severity NULL, continua aviso
    assert b({"Log_Type": "Error", "Severity": None}) == "warning"


def test_cartao_do_dashboard_ignora_33208_e_18456_e_conta_critico_pelo_tipo(monkeypatch):
    from api.routers.intelligence import helpers as h
    linhas = [
        {"Instance": "A_I01", "Log_Date": None, "Log_Type": "Repetitive", "Severity": 17, "Error_Number": 33208},
        {"Instance": "B_I01", "Log_Date": None, "Log_Type": "Security", "Severity": 14, "Error_Number": 18456},
        {"Instance": "C_I01", "Log_Date": None, "Log_Type": "Critical", "Severity": 24, "Error_Number": 824},
        {"Instance": "D_I01", "Log_Date": None, "Log_Type": "Lifecycle", "Severity": None, "Error_Number": None},
        {"Instance": "E_I01", "Log_Date": None, "Log_Type": "Error", "Severity": None, "Error_Number": None},
    ]

    async def fake(query, raise_on_error=True):
        return [] if "TOP 1" in query else linhas

    monkeypatch.setattr(h, "execute_intelligence_query_async", fake)
    res = {"error_log": {}}
    asyncio.run(h.collect_error_log(res))
    assert res["error_log"]["critical_count"] == 1
    assert res["error_log"]["warning_count"] == 2
    assert {i["Instance"] for i in res["error_log"]["instances"]} == {"C_I01", "D_I01", "E_I01"}


def test_drill_usa_a_mesma_regra():
    bloco = KPIS[KPIS.index('elif kpi_type == "error-log":'):KPIS.index('elif kpi_type == "tempdb-status"')]
    assert "from api.routers.intelligence.helpers import errorlog_bucket" in bloco
    assert "'16', '17', '18'" not in bloco
