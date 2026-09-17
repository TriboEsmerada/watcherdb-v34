# -*- coding: utf-8 -*-
"""Disk Latency: a regra "um disco = uma linha" aplicada a TODOS os leitores de KPI_OS_DISK_PERF_STG (2026-09-17).

OWNER (segunda captura, 17/09): "ainda continuo achando estranho isso. mesmo host e valores iguais." -- o tile ja dizia 1
(lote 40bb4c1) mas a modal continuava com dois cartoes de SQLHDSQLT301 c:.

CAUSA: o lote de ontem corrigiu o leitor do dashboard (helpers.collect_disk_latency). A modal NAO usa esse leitor: o
endpoint /api/intelligence-kpis/instances/{kpi_type} (intelligence_kpis.get_problematic_instances) tem a SUA copia da
consulta -- o mesmo padrao "dois sitios com o mesmo criterio" de 11/09 (Always On). E ha mais dois leitores da mesma
tabela no separador de desempenho do SO (services/os_performance_service.py): get_disk_by_drive (uma linha por
disco por instancia -> discos repetidos) e get_disk_latency_summary (COUNT(*) conta 12 discos onde ha 6 e o
STRING_AGG repete o disco problematico).

O QUE MUDA (portal apenas; o recolhedor V1 continua a gravar por instancia):
 1. intelligence_kpis: a consulta da modal traz Instance e passa por _uma_linha_por_disco (a mesma funcao do
    dashboard) antes de formatar -> um cartao, "Total: 1".
 2. os_performance_service.get_disk_by_drive: as linhas passam por _uma_linha_por_disco.
 3. os_performance_service.get_disk_latency_summary: os agregados calculam-se sobre a linha mais recente de cada
    disco (ROW_NUMBER por Hostname, Drive) -> Total_Drives e Problem_Drives certos.
 4. Teste de texto para os tres sitios + o teste de ontem continua a cobrir a funcao.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/DISK_POR_DISCO_TODOS_2026-09-17_apply.py --check
  py docs/context/DISK_POR_DISCO_TODOS_2026-09-17_apply.py
  py -m pytest tests/unit/test_disk_por_disco_todos_20260917.py tests/unit/test_disk_latency_por_disco_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "kpis": Path("api/routers/intelligence_kpis.py"),
    "osp": Path("services/os_performance_service.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_disk_por_disco_todos_20260917.py"),
}
MARK = "all_disk_latency = _uma_linha_por_disco(all_disk_latency)"

KPIS_EDITS = [
    ("""            SELECT
                Hostname,
                Drive,
                Avg_Read_Latency_MS,
""",
     """            SELECT
                Instance,
                Hostname,
                Drive,
                Avg_Read_Latency_MS,
""", 1),
    ("""            all_disk_latency = await execute_intelligence_query_async(query, raise_on_error=False) or []
""",
     """            all_disk_latency = await execute_intelligence_query_async(query, raise_on_error=False) or []
            # 2026-09-17: o recolhedor grava uma linha por instancia; o disco e' do host. A mesma regra do
            # dashboard (helpers.collect_disk_latency, 40bb4c1) -- esta modal tinha a sua copia da consulta.
            from api.routers.intelligence.helpers import _uma_linha_por_disco
            all_disk_latency = _uma_linha_por_disco(all_disk_latency)
""", 1),
]

OSP_EDITS = [
    ("""                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting disk by drive for {hostname}: {e}")
""",
     """                columns = [desc[0] for desc in cursor.description]
                # 2026-09-17: uma linha por disco (o recolhedor grava uma por instancia do mesmo host)
                from api.routers.intelligence.helpers import _uma_linha_por_disco
                return _uma_linha_por_disco([dict(zip(columns, row)) for row in rows])

        except Exception as e:
            logger.error(f"Error getting disk by drive for {hostname}: {e}")
""", 1),
    ("""            FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK)
            WHERE Hostname = ?
            \"\"\"
""",
     """            FROM (
                -- 2026-09-17: a linha mais recente de cada disco; havia uma por instancia do mesmo host
                SELECT *, ROW_NUMBER() OVER (PARTITION BY Hostname, Drive ORDER BY Update_TS DESC) AS rn
                FROM dbo.KPI_OS_DISK_PERF_STG WITH (NOLOCK)
                WHERE Hostname = ?
            ) D
            WHERE rn = 1
            \"\"\"
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Disk Latency: \"um disco = uma linha\" em todos os leitores** (owner 17/09). A modal do KPI e o separador de\n"
    "  desempenho do SO tinham as suas próprias consultas à tabela de discos e continuavam a repetir o mesmo disco por\n"
    "  cada instância do host; passam pela mesma regra do dashboard. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:140]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    kpis = src["kpis"].read_bytes().decode("utf-8")
    if MARK in kpis:
        print("[ABORT] ja aplicado"); return 1
    out = {"kpis": _apply(kpis, KPIS_EDITS, "intelligence_kpis"),
           "osp": _apply(src["osp"].read_bytes().decode("utf-8"), OSP_EDITS, "os_performance_service"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    compile(out["kpis"], str(REL["kpis"]), "exec"); compile(out["osp"], str(REL["osp"]), "exec"); compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] intelligence_kpis 2 blocos (Instance no SELECT, fusao); os_performance_service 2 (disk_by_drive, summary por ROW_NUMBER); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_disk_por_disco_todos_20260917.py tests/unit/test_disk_latency_por_disco_20260916.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
