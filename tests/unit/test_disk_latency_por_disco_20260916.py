"""
2026-09-16 -- Disk Latency: uma linha por (host, disco); o recolhedor grava uma por instancia.
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.routers.intelligence import helpers as h  # noqa: E402

T1, T2 = datetime(2026, 9, 16, 22, 56, 9), datetime(2026, 9, 16, 22, 56, 10)


def _r(inst, host, drive, ts, write_ms):
    return {"Instance": inst, "Hostname": host, "Drive": drive, "Update_TS": ts, "Avg_Write_Latency_MS": write_ms, "Env": "QLT"}


def test_duas_instancias_do_mesmo_host_dao_um_cartao_com_a_linha_mais_recente():
    rows = [_r("SQLHDSQLT301_I01", "SQLHDSQLT301", "c:", T1, 191.9), _r("SQLHDSQLT301_I02", "SQLHDSQLT301", "c:", T2, 192.4)]
    out = h._uma_linha_por_disco(rows)
    assert len(out) == 1
    assert out[0]["Update_TS"] == T2 and out[0]["Avg_Write_Latency_MS"] == 192.4
    assert out[0]["Instances_On_Host"] == 2 and out[0]["Instances"] == ["SQLHDSQLT301_I01", "SQLHDSQLT301_I02"]


def test_a_ordem_de_chegada_nao_muda_o_resultado():
    rows = [_r("I02", "H", "c:", T2, 2.0), _r("I01", "H", "c:", T1, 1.0)]
    out = h._uma_linha_por_disco(rows)
    assert out[0]["Update_TS"] == T2 and out[0]["Avg_Write_Latency_MS"] == 2.0 and out[0]["Instances_On_Host"] == 2


def test_discos_diferentes_e_hosts_diferentes_ficam_todos():
    rows = [_r("I01", "H1", "c:", T1, 1), _r("I01", "H1", "d:", T1, 1), _r("I01", "H2", "c:", T1, 1)]
    out = h._uma_linha_por_disco(rows)
    assert [(o["Hostname"], o["Drive"]) for o in out] == [("H1", "c:"), ("H1", "d:"), ("H2", "c:")]
    assert all(o["Instances_On_Host"] == 1 for o in out)


def test_nome_do_host_e_letra_do_disco_sem_distincao_de_maiusculas():
    rows = [_r("I01", "sqlhdsqlt301", "C:", T1, 1), _r("I02", "SQLHDSQLT301", "c:", T2, 1)]
    assert len(h._uma_linha_por_disco(rows)) == 1


def test_quatro_instancias_como_sqlhdsqlt105():
    rows = [_r(f"SQLHDSQLT105_I0{i}", "SQLHDSQLT105", "e:", T1, 3.0) for i in range(1, 5)]
    out = h._uma_linha_por_disco(rows)
    assert len(out) == 1 and out[0]["Instances_On_Host"] == 4


def test_a_consulta_traz_a_instancia_e_o_colector_funde():
    src = (ROOT / "api/routers/intelligence/helpers.py").read_text(encoding="utf-8")
    i = src.index("async def collect_disk_latency(")
    bloco = src[i:i + 4000]
    assert "            Instance,\n            Hostname,\n            Drive," in bloco
    assert "disk_latency_data = _uma_linha_por_disco(disk_latency_data)" in bloco
    assert bloco.index("_uma_linha_por_disco(") < bloco.index("critical_instances = [")
