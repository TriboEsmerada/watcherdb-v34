# -*- coding: utf-8 -*-
"""HOTFIX do B1b (2026-09-15) -- a gravacao na STG falha com 8023 quando o ciclo mistura linhas com e sem numero de erro.

Sintoma (log do recolhedor, 11:33): "Parameter 10: The supplied value is not a valid instance of data type float" (8023).
TST gravou (so linhas com numero); QA e PRD ficaram com os dados antigos das 11:21-11:23 e sem heartbeat.

Causa (erro da AI, reproduzido): o B1b passou a preencher Error_Number, Severity e State, que ficam None nas linhas sem
cabecalho (arranques, mudancas de papel AG, memoria paginada). O store_data constroi os tuplos a partir de uma DataFrame do
pandas; uma coluna que mistura inteiros e None vira float64 com NaN, e o SQL Server recusa NaN. Com o codigo antigo estas
colunas eram sempre None (dtype object) e o problema nao existia. Os testes do B1b e a prova real paravam no
collect_from_server e nunca passaram pela DataFrame nem pelo store_data.

Correcao: os tuplos passam por _sql_int (NaN e None -> None, float inteiro -> int) nas 5 colunas inteiras e por _sql_dt
(Timestamp -> datetime, NaT -> None) nas duas datas. Nao muda esquema, swap nem heartbeat.
Teste novo passa pela DataFrame e pelo store_data com uma ligacao simulada.

Uso (raiz do repo V3.4; escreve no repo V1):
  py docs/context/HOTFIX_B1B_NAN_2026-09-15_apply.py --check
  py docs/context/HOTFIX_B1B_NAN_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b1b.py tests/unit/test_collect_errorlog_hotfix_nan.py -q -p no:cacheprovider
  Restart-Service WatcherDBCollector

Alternativa se preferires voltar atras em vez de corrigir (so o recolhedor, mantem a migration 011 e a documentacao):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython
  git checkout b02ba58 -- "WATCHERDB INTELLIGENCE V1/scripts/collectors/collect_errorlog.py" ; Restart-Service WatcherDBCollector
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "collector": Path("scripts/collectors/collect_errorlog.py"),
    "test": Path("tests/unit/test_collect_errorlog_hotfix_nan.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "def _sql_int("

HELPERS = '''def _sql_int(v):
    """int ou None para as colunas inteiras da STG.

    HOTFIX B1b 2026-09-15: com Error_Number/Severity/State preenchidos so em parte das linhas, o pandas guarda a coluna
    em float64 com NaN, e o SQL Server recusa NaN (erro 8023, "not a valid instance of data type float").
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return int(v)


def _sql_dt(v):
    """datetime ou None: Timestamp do pandas passa a datetime, NaT passa a None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v.to_pydatetime() if hasattr(v, "to_pydatetime") else v


'''

TUPLES_OLD = """            data_tuples = [
                (row['Instance'], row['Log_Date'], row['Process_Info'],
                 row['Log_Text'], row['Log_Text_Hash'], row['Log_Type'],
                 row['Error_Number'], row['Severity'], row['State'],
                 row['Log_File_Number'], row['Update_TS'])
                for _, row in df.iterrows()
            ]
"""
TUPLES_NEW = """            # HOTFIX B1b 2026-09-15: inteiros e datas passam por _sql_int/_sql_dt (NaN do pandas -> None; erro 8023)
            data_tuples = [
                (row['Instance'], _sql_dt(row['Log_Date']), row['Process_Info'],
                 row['Log_Text'], _sql_int(row['Log_Text_Hash']), row['Log_Type'],
                 _sql_int(row['Error_Number']), _sql_int(row['Severity']), _sql_int(row['State']),
                 _sql_int(row['Log_File_Number']), _sql_dt(row['Update_TS']))
                for _, row in df.iterrows()
            ]
"""

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Corrigido — hotfix do B1b: gravacao do errorlog falhava com 8023\n\n"
                  "- Com Error_Number, Severity e State preenchidos so em parte das linhas, a DataFrame do pandas guardava essas\n"
                  "  colunas em float64 com NaN e o SQL Server recusava o lote (8023). TST gravou; QA e PRD ficaram com os dados\n"
                  "  antigos e sem heartbeat desde as 11:33 de 15/09. Os tuplos passam por `_sql_int` e `_sql_dt` antes do\n"
                  "  `executemany`. Teste novo passa pela DataFrame e pelo `store_data`, o caminho que os testes do B1b nao cobriam.\n\n")

TEST_SRC = r'''"""
Hotfix B1b (2026-09-15): store_data grava um ciclo que mistura linhas com e sem numero de erro, sem NaN nos parametros.
"""
import math
from datetime import datetime

import pytest

import scripts.collectors.collect_errorlog as mod

pytestmark = pytest.mark.unit


class Cur:
    def __init__(self, reg):
        self.reg = reg

    def execute(self, sql, params=()):
        self.reg["execute"].append((sql, params))

    def fetchone(self):
        return ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]

    def executemany(self, sql, batch):
        self.reg["lotes"].append(list(batch))


class Conn:
    def __init__(self, reg):
        self.reg = reg

    def cursor(self):
        return Cur(self.reg)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ciclo_misto_grava_sem_nan_e_faz_swap(monkeypatch):
    reg = {"execute": [], "lotes": [], "erros": []}
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: Conn(reg))
    c = object.__new__(mod.ErrorLogCollector)
    c.logger = type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None,
                              "error": lambda self, m: reg["erros"].append(m)})()
    c._build_master_conn_str = lambda: "DRIVER=x"
    t = datetime(2026, 9, 15, 11, 0)
    rows = [
        {"Instance": "A_I01", "Log_Date": t, "Process_Info": "Logon", "Log_Text": "Error: 18456 ...", "Log_Text_Hash": -5,
         "Log_Type": "Security", "Error_Number": 18456, "Severity": 14, "State": 5, "Log_File_Number": 0, "Update_TS": t},
        {"Instance": "A_I01", "Log_Date": t, "Process_Info": "Server", "Log_Text": "SQL Server is starting ...", "Log_Text_Hash": 7,
         "Log_Type": "Lifecycle", "Error_Number": None, "Severity": None, "State": None, "Log_File_Number": 1, "Update_TS": t},
    ]
    c.store_data(mod.pd.DataFrame(rows), "PRD")
    assert reg["erros"] == []
    tuplos = [x for lote in reg["lotes"] for x in lote]
    assert len(tuplos) == 2
    for tup in tuplos:
        for v in tup:
            assert not (isinstance(v, float) and math.isnan(v)), tup
    assert tuplos[0][6:10] == (18456, 14, 5, 0) and all(type(v) is int for v in tuplos[0][6:10])
    assert tuplos[1][6:10] == (None, None, None, 1)
    assert type(tuplos[0][1]) is datetime and type(tuplos[0][10]) is datetime
    assert any("usp_swap_kpi_stg_tables" in s for s, _ in reg["execute"])


def test_conversores():
    assert mod._sql_int(float("nan")) is None and mod._sql_int(None) is None
    assert mod._sql_int(18456.0) == 18456 and type(mod._sql_int(mod.pd.Series([1, None])[0])) is int
    assert mod._sql_dt(mod.pd.NaT) is None
    assert type(mod._sql_dt(mod.pd.Timestamp("2026-09-15 11:00"))) is datetime
'''


def _eol(t):
    return "\r\n" if "\r\n" in t else "\n"


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or V1
    src = {k: base / p for k, p in REL.items()}
    raw = src["collector"].read_bytes().decode("utf-8")
    eol = _eol(raw)
    lf = raw.replace("\r\n", "\n")
    if MARK in lf:
        print("[ABORT] ja aplicado"); return 1
    if "QUERY_TIMEOUT" not in lf:
        print("[ABORT] o B1b nao esta aplicado neste recolhedor"); return 1
    for anc, n in (("class ErrorLogCollector:\n", 1), (TUPLES_OLD, 1)):
        if lf.count(anc) != n:
            print(f"[ABORT] ancora {anc[:50]!r} encontrada {lf.count(anc)}x -- nada escrito"); return 1
    novo = lf.replace("class ErrorLogCollector:\n", HELPERS + "class ErrorLogCollector:\n").replace(TUPLES_OLD, TUPLES_NEW)
    compile(novo, str(REL["collector"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    chg = src["changelog"].read_bytes().decode("utf-8")
    ce = _eol(chg); anc = CHANGELOG_ANCORA.replace("\n", ce)
    if chg.count(anc) != 1:
        print("[ABORT] changelog V1: [Unreleased] nao unico"); return 1
    chg_novo = chg.replace(anc, CHANGELOG_NOVO.replace("\n", ce), 1)
    print(f"[ok] recolhedor com _sql_int/_sql_dt nos tuplos; compila; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["collector"].write_bytes(novo.replace("\n", eol).encode("utf-8")); print(f"[write] {REL['collector']}")
    src["changelog"].write_bytes(chg_novo.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print('\nAplicado. Corre: cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b1b.py tests/unit/test_collect_errorlog_hotfix_nan.py -q -p no:cacheprovider ; Restart-Service WatcherDBCollector')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
