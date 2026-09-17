# -*- coding: utf-8 -*-
"""KPI Disk Latency: uma linha por DISCO, nao por instancia (2026-09-16).

PERGUNTA DO OWNER (captura "Disk Latency Critical - High Latency Drives"): SQLHDSQLT301 drive c: aparece duas vezes,
com os mesmos numeros. "pq aparece duplicado?"

CAUSA (medida em KPI_OS_DISK_PERF_STG): o recolhedor de desempenho de disco (WMI) corre UMA VEZ POR INSTANCIA e
grava a linha com a coluna Instance. Num host com duas instancias (SQLHDSQLT301_I01 e _I02) o mesmo disco c: fica
com duas linhas iguais, um segundo de diferenca no Update_TS; SQLHDSQLT105 tem quatro instancias -> quatro linhas
por disco. Na tabela inteira: 519 linhas para 468 pares (host, disco). A consulta do portal (collect_disk_latency,
api/routers/intelligence/helpers.py) le Hostname e Drive sem Instance e sem agrupar -> a modal repete o cartao e o
KPI "Drives w/ critical latency" conta 2 quando ha' 1 disco critico.

O QUE MUDA (so' no portal; o recolhedor V1 fica como esta -- recolher o disco uma vez por host e' optimizacao de
outro lote, com veto do guardiao do recolhedor):
 1. helpers.py: _uma_linha_por_disco(rows) fica com a linha mais recente de cada (Hostname, Drive) e anota
    Instances_On_Host e Instances (a lista); collect_disk_latency usa-a depois do filtro de offline.
 2. Teste unitario com linhas falsas: 2 instancias -> 1 cartao, a mais recente; discos diferentes ficam; nome do
    host sem distincao de maiusculas.

NOTA (nao tratada aqui): o corpo do cartao esta em portugues com o portal em ingles (Leitura/Escrita/Uso Disco,
IOPS Leitura/Escrita, "Possiveis causas e diagnostico" e as dicas). E' a mesma classe de falha do Collector Health;
fica proposto como lote proprio.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/DISK_LATENCY_POR_DISCO_2026-09-16_apply.py --check
  py docs/context/DISK_LATENCY_POR_DISCO_2026-09-16_apply.py
  py -m pytest tests/unit/test_disk_latency_por_disco_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 (KPI Disk Health: "Drives w/ critical latency" passa de 2 a 1)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "helpers": Path("api/routers/intelligence/helpers.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_disk_latency_por_disco_20260916.py"),
}
MARK = "def _uma_linha_por_disco("

EDITS = [
    ("""def _count_by_env(instances: List[Dict[str, Any]], env_key: str = 'Env') -> Dict[str, int]:
""",
     """def _uma_linha_por_disco(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    \"\"\"Uma linha por (Hostname, Drive): a mais recente, com Instances_On_Host e Instances anotados.

    2026-09-16: o recolhedor de disco (WMI) corre uma vez por INSTANCIA e grava Instance; num host com duas
    instancias o mesmo c: vinha em duplicado (SQLHDSQLT301), com quatro em SQLHDSQLT105. O disco e' do host,
    nao da instancia: aqui fica um cartao e uma contagem por disco. A ordem de entrada e' preservada.
    \"\"\"
    por_disco: Dict[tuple, Dict[str, Any]] = {}
    ordem: List[tuple] = []
    for row in rows:
        chave = ((row.get('Hostname') or '').strip().upper(), (row.get('Drive') or '').strip().lower())
        inst = (row.get('Instance') or '').strip()
        actual = por_disco.get(chave)
        if actual is None:
            novo = dict(row)
            novo['Instances'] = [inst] if inst else []
            novo['Instances_On_Host'] = 1
            por_disco[chave] = novo
            ordem.append(chave)
            continue
        if inst and inst not in actual['Instances']:
            actual['Instances'].append(inst)
        actual['Instances_On_Host'] = max(len(actual['Instances']), actual['Instances_On_Host'] + 1)
        ts_novo, ts_actual = row.get('Update_TS'), actual.get('Update_TS')
        if ts_novo is not None and (ts_actual is None or ts_novo > ts_actual):
            guardado_inst, guardado_n = actual['Instances'], actual['Instances_On_Host']
            actual.update({k: v for k, v in row.items() if k not in ('Instance',)})
            actual['Instances'], actual['Instances_On_Host'] = guardado_inst, guardado_n
    return [por_disco[c] for c in ordem]


def _count_by_env(instances: List[Dict[str, Any]], env_key: str = 'Env') -> Dict[str, int]:
""", 1),
    ("""        SELECT
            Hostname,
            Drive,
            Avg_Read_Latency_MS,
            Avg_Write_Latency_MS,
            Disk_Reads_Sec,
            Disk_Writes_Sec,
            Percent_Disk_Time,
            Update_TS,
""",
     """        SELECT
            Instance,
            Hostname,
            Drive,
            Avg_Read_Latency_MS,
            Avg_Write_Latency_MS,
            Disk_Reads_Sec,
            Disk_Writes_Sec,
            Percent_Disk_Time,
            Update_TS,
""", 1),
    ("""        disk_latency_data = [row for row in disk_latency_data_raw if (row.get('Hostname') or '').upper() not in offline_hostnames]
        dl_filtered = len(disk_latency_data_raw) - len(disk_latency_data)
""",
     """        disk_latency_data = [row for row in disk_latency_data_raw if (row.get('Hostname') or '').upper() not in offline_hostnames]
        dl_filtered = len(disk_latency_data_raw) - len(disk_latency_data)
        # 2026-09-16: o recolhedor grava uma linha por instancia; o disco e' do host -> um cartao por disco
        antes = len(disk_latency_data)
        disk_latency_data = _uma_linha_por_disco(disk_latency_data)
        if len(disk_latency_data) != antes:
            logger.info(f"Disk Latency: {antes - len(disk_latency_data)} linha(s) repetida(s) por instancia do mesmo host fundidas")
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Disk Latency: um cartão e uma contagem por disco, não por instância** (owner 16/09). O recolhedor de\n"
    "  desempenho de disco grava uma linha por instância; num host com duas instâncias o mesmo `c:` aparecia duas\n"
    "  vezes na modal e contava 2 no KPI. O portal passa a fundir as linhas do mesmo (host, disco), ficando com a\n"
    "  mais recente e a lista de instâncias. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
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
    helpers = src["helpers"].read_bytes().decode("utf-8")
    if MARK in helpers:
        print("[ABORT] ja aplicado"); return 1
    out = {"helpers": _apply(helpers, EDITS, "helpers"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    compile(out["helpers"], str(REL["helpers"]), "exec"); compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] helpers 3 blocos (_uma_linha_por_disco, SELECT com Instance, fusao apos o filtro de offline); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_disk_latency_por_disco_20260916.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
