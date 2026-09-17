"""
2026-09-17 -- todos os leitores de KPI_OS_DISK_PERF_STG devolvem um disco por (host, disco).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KPIS = (ROOT / "api/routers/intelligence_kpis.py").read_text(encoding="utf-8")
OSP = (ROOT / "services/os_performance_service.py").read_text(encoding="utf-8")


def test_modal_traz_a_instancia_e_funde_por_disco():
    i = KPIS.index('elif kpi_type == "disk-latency-critical" or kpi_type == "disk-latency-warning":')
    bloco = KPIS[i:i + 4000]
    assert "                Instance,\n                Hostname,\n                Drive," in bloco
    assert "all_disk_latency = _uma_linha_por_disco(all_disk_latency)" in bloco
    assert bloco.index("_uma_linha_por_disco(all_disk_latency)") < bloco.index("disk_latency_instances = []")


def test_disk_by_drive_funde_por_disco():
    i = OSP.index("async def get_disk_by_drive(")
    j = OSP.index("async def get_disk_latency_summary(", i)
    assert "return _uma_linha_por_disco([dict(zip(columns, row)) for row in rows])" in OSP[i:j]


def test_summary_agrega_sobre_a_linha_mais_recente_de_cada_disco():
    i = OSP.index("async def get_disk_latency_summary(")
    j = OSP.index("async def get_servers_needing_attention(", i)
    bloco = OSP[i:j]
    assert "ROW_NUMBER() OVER (PARTITION BY Hostname, Drive ORDER BY Update_TS DESC) AS rn" in bloco
    assert "WHERE rn = 1" in bloco
    assert bloco.count("FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK)") == 1


def test_nao_sobra_leitor_sem_a_regra():
    # cada leitor da tabela no portal ou funde em Python ou agrega com ROW_NUMBER
    import re
    for rel in ("api/routers/intelligence/helpers.py", "api/routers/intelligence_kpis.py", "services/os_performance_service.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        for m in re.finditer(r"KPI_OS_DISK_PERF_STG WITH \(NOLOCK\)", src):
            janela = src[max(0, m.start() - 2500):m.end() + 2500]
            assert "_uma_linha_por_disco(" in janela or "ROW_NUMBER() OVER (PARTITION BY Hostname, Drive" in janela, (rel, m.start())
