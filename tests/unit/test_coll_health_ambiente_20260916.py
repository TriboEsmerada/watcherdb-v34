"""
2026-09-16 -- Collector Health: a linha de estado e' a do ambiente da tarefa, nao a ultima que o dict apanhou.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.collector_health import health_calculator as hc  # noqa: E402

AGORA = datetime(2026, 9, 16, 18, 30)
ROWS = [
    {"Table_Name": "KPI_MSSQL_AG_QUEUE_SIZES_STG", "Environment": "PRD", "Last_Swap_Time": AGORA - timedelta(minutes=4), "Servers_Collected": 576},
    {"Table_Name": "KPI_MSSQL_AG_QUEUE_SIZES_STG", "Environment": "QA", "Last_Swap_Time": AGORA - timedelta(days=198), "Servers_Collected": 537},
    {"Table_Name": "KPI_MSSQL_AG_QUEUE_SIZES_STG", "Environment": "TST", "Last_Swap_Time": AGORA - timedelta(days=158), "Servers_Collected": 537},
]


def test_a_tarefa_prd_ve_a_linha_prd_e_nao_a_do_tst():
    indice = hc._indexar_por_ambiente(ROWS, "Environment")
    prd = hc._best_active_row({"tables": ["KPI_MSSQL_AG_QUEUE_SIZES_STG"], "environment": "PRD"}, indice)
    tst = hc._best_active_row({"tables": ["KPI_MSSQL_AG_QUEUE_SIZES_STG"], "environment": "TST"}, indice)
    assert prd["Servers_Collected"] == 576 and (AGORA - prd["Last_Swap_Time"]) < timedelta(minutes=10)
    assert (AGORA - tst["Last_Swap_Time"]).days == 158


def test_sem_ambiente_na_tarefa_usa_a_mais_recente():
    indice = hc._indexar_por_ambiente(ROWS, "Environment")
    row = hc._best_active_row({"tables": ["KPI_MSSQL_AG_QUEUE_SIZES_STG"]}, indice)
    assert row["Environment"] == "PRD"


def test_ambiente_sem_linha_nao_pede_emprestada_a_frescura_de_outro():
    indice = hc._indexar_por_ambiente(ROWS[:1], "Environment")   # so' PRD existe
    assert hc._best_active_row({"tables": ["KPI_MSSQL_AG_QUEUE_SIZES_STG"], "environment": "QA"}, indice) is None


def test_a_ordem_de_chegada_deixou_de_importar():
    directa = hc._indexar_por_ambiente(ROWS, "Environment")
    invertida = hc._indexar_por_ambiente(list(reversed(ROWS)), "Environment")
    for idx in (directa, invertida):
        assert hc._linha_do_ambiente(idx, "KPI_MSSQL_AG_QUEUE_SIZES_STG", "PRD")["Servers_Collected"] == 576
        assert idx["KPI_MSSQL_AG_QUEUE_SIZES_STG"]["_any"]["Environment"] == "PRD"


def test_schedule_meta_indexa_por_nome_da_tarefa():
    rows = [
        {"Table_Name": "KPI_MSSQL_MIRRORING_STATUS_STG", "Collector_Name": "collect_mirroring_PRD", "Freshness_Source": "HEARTBEAT", "Last_Success_TS": AGORA - timedelta(minutes=3)},
        {"Table_Name": "KPI_MSSQL_MIRRORING_STATUS_STG", "Collector_Name": "collect_mirroring_TST", "Freshness_Source": "HEARTBEAT", "Last_Success_TS": AGORA - timedelta(days=47)},
    ]
    idx = hc._indexar_por_ambiente(rows, "Collector_Name")
    assert hc._linha_do_ambiente(idx, "KPI_MSSQL_MIRRORING_STATUS_STG", "collect_mirroring_PRD")["Collector_Name"] == "collect_mirroring_PRD"
    assert hc._linha_do_ambiente(idx, "KPI_MSSQL_MIRRORING_STATUS_STG", "")["Collector_Name"] == "collect_mirroring_PRD"


def test_a_consulta_le_o_ambiente():
    src = (ROOT / "modules/collector_health/health_calculator.py").read_text(encoding="utf-8")
    assert '"SELECT Table_Name, Environment, Active_Slot, Last_Swap_Time, "' in src
    assert 'row = _linha_do_ambiente(active_by_table, str(tbl), ambiente)' in src
