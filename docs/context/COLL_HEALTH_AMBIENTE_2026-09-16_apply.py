# -*- coding: utf-8 -*-
"""Collector Health: o estado de uma tarefa passa a olhar para a linha do SEU ambiente (2026-09-16).

PERGUNTA DO OWNER (captura com 9 tarefas STALE): "sera que tem algum problema com esses que estao stale?"

MEDIDO:
 - KPI_STG_ACTIVE_TABLE tem UMA LINHA POR AMBIENTE para a mesma tabela: KPI_MSSQL_AG_QUEUE_SIZES_STG tem PRD
   (swap hoje 18:25, 576 registos), QA (02/03) e TST (11/04). O mesmo para ALWAYSON_STATUS, AG_QUEUES e
   MIRRORING_STATUS (PRD hoje; QA/TST em Julho).
 - Os logs dos recolhedores confirmam: alwayson_status, ag_queues e ag_queue_sizes fizeram SWAP SUCCESS em PRD
   hoje as 18:25-18:27, com 0 falhas.
 - O calculador (modules/collector_health/health_calculator.py) indexava essas linhas SO' pelo nome da tabela
   (`dict por Table_Name`): das tres linhas ficava a ultima a chegar, ao acaso -- e para estas familias ficou a
   de TST ou QA. Resultado: as tarefas PRD aparecem STALE ha 158 dias (a data do TST) enquanto escrevem todos os
   dias. WDB_COLLECTION_SCHEDULE_META tinha o mesmo defeito (uma linha por Collector_Name, indexada por tabela).
 - As tarefas QA/TST dessas familias: os swaps sao mesmo antigos, porque nesses ambientes a recolha devolve 0
   linhas (nao ha grupos de disponibilidade/mirroring la') e sem linhas nao ha swap. Isso nao e' avaria -- e' um
   ambiente sem alvo -- mas hoje aparece como STALE. Fica proposto, nao feito: classificar como QUIET com o motivo
   "sem alvos neste ambiente" quando a mesma tabela esta' fresca noutro ambiente (decisao de produto).

O QUE FAZ:
 1. _fetch_active_state le tambem Environment e devolve, por tabela, {AMBIENTE: linha, "_any": a mais recente}.
 2. _best_active_row escolhe a linha do ambiente da tarefa; sem ambiente na tarefa, a mais recente.
 3. _fetch_schedule_meta devolve, por tabela, {COLLECTOR_NAME: linha, "_any": ...}; o recurso HEARTBEAT procura
    primeiro pelo nome da tarefa.
 4. Teste com dicionarios falsos: PRD fresco e TST velho na mesma tabela -> a tarefa PRD ve o PRD.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_HEALTH_AMBIENTE_2026-09-16_apply.py --check
  py docs/context/COLL_HEALTH_AMBIENTE_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_health_ambiente_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 (Collector Health: os 4 PRD passam a FRESH)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "calc": Path("modules/collector_health/health_calculator.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_coll_health_ambiente_20260916.py"),
}
MARK = '"_any"'

EDITS = [
    ("""async def _fetch_active_state() -> Dict[str, Dict[str, Any]]:
    \"\"\"Le KPI_STG_ACTIVE_TABLE — retorna dict por Table_Name.\"\"\"
""",
     """def _indexar_por_ambiente(rows: List[Dict[str, Any]], chave_ambiente: str) -> Dict[str, Dict[str, Any]]:
    \"\"\"{TABLE_NAME: {AMBIENTE_OU_NOME: row, "_any": row mais recente}}.

    2026-09-16: KPI_STG_ACTIVE_TABLE tem uma linha por AMBIENTE para a mesma tabela (PRD/QA/TST) e
    WDB_COLLECTION_SCHEDULE_META uma por Collector_Name. Indexar so' por Table_Name ficava com a ultima a
    chegar, ao acaso: as tarefas PRD de AlwaysOn/AG/Mirroring apareciam STALE ha 158 dias (a linha do TST)
    enquanto faziam swap todos os dias.
    \"\"\"
    indice: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        tabela = (row.get("Table_Name") or "").upper()
        if not tabela:
            continue
        por_tabela = indice.setdefault(tabela, {})
        amb = (row.get(chave_ambiente) or "").upper()
        if amb:
            por_tabela[amb] = row
        ts = row.get("Last_Swap_Time") or row.get("Last_Success_TS")
        actual = por_tabela.get("_any")
        actual_ts = (actual or {}).get("Last_Swap_Time") or (actual or {}).get("Last_Success_TS")
        if actual is None or (ts and (actual_ts is None or ts > actual_ts)):
            por_tabela["_any"] = row
    return indice


def _linha_do_ambiente(indice: Dict[str, Dict[str, Any]], tabela: str, ambiente: str) -> Optional[Dict[str, Any]]:
    \"\"\"A linha do ambiente pedido; sem ambiente na tarefa, a mais recente. Com ambiente e sem linha dele: None
    (a tarefa desse ambiente nunca fez swap -- nao se empresta a frescura de outro ambiente).\"\"\"
    por_tabela = indice.get((tabela or "").upper())
    if not por_tabela:
        return None
    if ambiente:
        return por_tabela.get(ambiente.upper())
    return por_tabela.get("_any")


async def _fetch_active_state() -> Dict[str, Dict[str, Any]]:
    \"\"\"Le KPI_STG_ACTIVE_TABLE — dict por Table_Name -> {Environment: row, "_any": row mais recente}.\"\"\"
""", 1),
    ("""        rows = await async_execute_on_intelligence(
            "SELECT Table_Name, Active_Slot, Last_Swap_Time, "
            "Collection_Start_Time, Collection_End_Time, Servers_Collected, Created_Date "
            "FROM dbo.KPI_STG_ACTIVE_TABLE WITH (NOLOCK)"
        ) or []
        return {
            (row.get("Table_Name") or "").upper(): row
            for row in rows
            if row.get("Table_Name")
        }
    except Exception as e:
        logger.warning("[CollectorHealth] falha a ler KPI_STG_ACTIVE_TABLE: %s", e)
        return {}
""",
     """        rows = await async_execute_on_intelligence(
            "SELECT Table_Name, Environment, Active_Slot, Last_Swap_Time, "
            "Collection_Start_Time, Collection_End_Time, Servers_Collected, Created_Date "
            "FROM dbo.KPI_STG_ACTIVE_TABLE WITH (NOLOCK)"
        ) or []
        return _indexar_por_ambiente(rows, "Environment")
    except Exception as e:
        logger.warning("[CollectorHealth] falha a ler KPI_STG_ACTIVE_TABLE: %s", e)
        return {}
""", 1),
    ("""        rows = await async_execute_on_intelligence(
            "SELECT Table_Name, Collector_Name, Expected_Interval_Minutes, "
            "Freshness_Source, Last_Success_TS "
            "FROM dbo.WDB_COLLECTION_SCHEDULE_META WITH (NOLOCK)"
        ) or []
        return {
            (row.get("Table_Name") or "").upper(): row
            for row in rows
            if row.get("Table_Name")
        }
""",
     """        rows = await async_execute_on_intelligence(
            "SELECT Table_Name, Collector_Name, Expected_Interval_Minutes, "
            "Freshness_Source, Last_Success_TS "
            "FROM dbo.WDB_COLLECTION_SCHEDULE_META WITH (NOLOCK)"
        ) or []
        return _indexar_por_ambiente(rows, "Collector_Name")
""", 1),
    ("""    tables = task.get("tables") or []
    if not tables:
        return None
    best: Optional[Dict[str, Any]] = None
    best_ts: Optional[datetime] = None
    for tbl in tables:
        row = active_by_table.get(str(tbl).upper())
        if not row:
            continue
""",
     """    tables = task.get("tables") or []
    if not tables:
        return None
    ambiente = (task.get("environment") or "").upper()
    best: Optional[Dict[str, Any]] = None
    best_ts: Optional[datetime] = None
    for tbl in tables:
        # 2026-09-16: a linha do AMBIENTE da tarefa, nao a ultima que o dict apanhou
        row = _linha_do_ambiente(active_by_table, str(tbl), ambiente)
        if not row:
            continue
""", 1),
    ("""            for tbl in (task.get("tables") or []):
                meta = schedule_meta.get(str(tbl).upper())
                if meta and meta.get("Freshness_Source") == "HEARTBEAT" and meta.get("Last_Success_TS"):
""",
     """            for tbl in (task.get("tables") or []):
                # 2026-09-16: primeiro a linha desta tarefa (Collector_Name); depois a mais recente da tabela
                meta = _linha_do_ambiente(schedule_meta, str(tbl), name) or _linha_do_ambiente(schedule_meta, str(tbl), "")
                if meta and meta.get("Freshness_Source") == "HEARTBEAT" and meta.get("Last_Success_TS"):
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: cada tarefa passa a olhar para a linha do seu ambiente** (owner 16/09). A tabela de\n"
    "  estado tem uma linha por ambiente (PRD/QA/TST) para a mesma tabela; o quadro indexava só pelo nome da tabela\n"
    "  e ficava com a última a chegar — as tarefas PRD de Always On, filas de AG e Mirroring apareciam paradas há\n"
    "  158 dias (a data do TST) enquanto faziam swap todos os dias. Os QA/TST dessas famílias continuam antigos por\n"
    "  não terem alvos nesses ambientes; classificá-los como \"sem alvo\" fica proposto. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
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
    calc = src["calc"].read_bytes().decode("utf-8")
    if MARK in calc:
        print("[ABORT] ja aplicado"); return 1
    out = {"calc": _apply(calc, EDITS, "health_calculator"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    compile(out["calc"], str(REL["calc"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] health_calculator 5 blocos (indice por ambiente, SELECT com Environment, meta por Collector_Name, _best_active_row, HEARTBEAT); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_coll_health_ambiente_20260916.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
