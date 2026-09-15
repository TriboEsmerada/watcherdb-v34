# -*- coding: utf-8 -*-
"""PERF do B1b (2026-09-15) -- insercao em bloco na STG do errorlog, para voltar a ligar o B1b.

Incidente de hoje: com o B1b + hotfix do NaN, a gravacao ficou a ~700-1.200 linhas/min (executemany linha a linha). QA
(9.433 linhas) levou mais de 8 min e PRD (~9.900) nunca coube no ciclo de 5 min; o errorlog de PRD parou desde as 11:26.
As 11:53 o owner repos o recolhedor anterior (git checkout b02ba58). O commit HEAD do V1 (bb4024a) tem B1b + hotfix.

Facto medido depois do retrocesso: o codigo ANTERIOR tambem nao acompanha. As 11:52:46 recolheu 10.535 linhas de PRD e
as 11:58 ainda nao tinha trocado de slot; ciclos novos arrancam por cima de insercoes por acabar. A lentidao nao vem do
B1b: ja existia e ficou visivel. Por isso este lote aplica-se sobre o B1b, que e' melhor que o anterior em tudo o resto.

Correcao (parecer do guardiao do recolhedor, consenso, 15/09):
  - cursor.fast_executemany = True no store_data. Padrao ja em producao no base_collector.py (Wave R+6, 10-15x) e em
    collect_mirroring_status, collect_db_security_map, collect_alwayson_failovers, sync_monitored_servers.
  - setinputsizes OBRIGATORIO (condicao do guardiao): o fast_executemany dimensiona o buffer de texto pela primeira linha
    do lote, e o Log_Text do errorlog varia muito de tamanho (evento curto seguido de stack dump). Instance e Process_Info
    varchar(128), Log_Text nvarchar(4000) (o collect_from_server ja corta a 4000), Log_Type varchar(32); inteiros e datas
    ja chegam limpos pelo hotfix (_sql_int, _sql_dt). Verificado numa ligacao real que o pyodbc 5.3.0 aceita a lista.
  - O log passa a dizer quanto demorou a insercao, para a medicao.
A agregacao dos repetitivos continua so na HIST (guardiao: o gargalo e' de escrita, nao de volume por hora).

Pre-requisito: o recolhedor em disco tem de ser o do commit HEAD (B1b + hotfix), nao o anterior reposto.

Uso (o owner):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython
  git checkout HEAD -- "WATCHERDB INTELLIGENCE V1/scripts/collectors/collect_errorlog.py"
  cd WATCHERDB_V3.4
  py docs/context/PERF_B1B_INSERCAO_BLOCO_2026-09-15_apply.py --check
  py docs/context/PERF_B1B_INSERCAO_BLOCO_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_perf.py tests/unit/test_collect_errorlog_hotfix_nan.py tests/unit/test_collect_errorlog_b1b.py -q -p no:cacheprovider
  Restart-Service WatcherDBCollector

Criterio de sucesso (medir no log logs/collectors/errorlog_AAAAMMDD.log): em cada ambiente, "Armazenados N registros ... em S s"
com S abaixo de 60 para PRD, e "SWAP executado" a seguir. Se falhar: o mesmo retrocesso de hoje (git checkout b02ba58 -- ...).
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "collector": Path("scripts/collectors/collect_errorlog.py"),
    "test": Path("tests/unit/test_collect_errorlog_perf.py"),
    "changelog": Path("docs/CHANGELOG.md"),
    "test_hotfix": Path("tests/unit/test_collect_errorlog_hotfix_nan.py"),
}
MARK = "fast_executemany"

# o teste do hotfix usa um cursor simulado sem setinputsizes: passa a ter
HOTFIX_TEST_OLD = '    def executemany(self, sql, batch):\n        self.reg["lotes"].append(list(batch))\n'
HOTFIX_TEST_NEW = HOTFIX_TEST_OLD + '\n    def setinputsizes(self, sizes):\n        self.reg.setdefault("tamanhos", sizes)\n'

BATCH_OLD = """            batch_size = 1000
            for i in range(0, len(data_tuples), batch_size):
"""
BATCH_NEW = """            # PERF B1b 2026-09-15: insercao em bloco. Sem isto o pyodbc envia linha a linha e o ciclo de PRD (~9.900 linhas)
            # passava dos 5 minutos. Padrao do base_collector.py (Wave R+6). setinputsizes OBRIGATORIO (guardiao): o
            # fast_executemany dimensiona o buffer de texto pela 1.a linha do lote e o Log_Text varia muito de tamanho.
            cursor.fast_executemany = True
            cursor.setinputsizes([
                (pyodbc.SQL_VARCHAR, 128, 0),     # Instance
                None,                             # Log_Date
                (pyodbc.SQL_VARCHAR, 128, 0),     # Process_Info
                (pyodbc.SQL_WVARCHAR, 4000, 0),   # Log_Text (cortado a 4000 no collect_from_server)
                None,                             # Log_Text_Hash
                (pyodbc.SQL_VARCHAR, 32, 0),      # Log_Type
                None, None, None, None, None,     # Error_Number, Severity, State, Log_File_Number, Update_TS
            ])
            inicio_insercao = datetime.now()
            batch_size = 1000
            for i in range(0, len(data_tuples), batch_size):
"""
LOG_OLD = '            self.logger.info(f"Armazenados {len(df)} registros em {table_name}")\n'
LOG_NEW = ('            segundos = (datetime.now() - inicio_insercao).total_seconds()\n'
           '            self.logger.info(f"Armazenados {len(df)} registros em {table_name} em {segundos:.1f} s")\n')

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Corrigido — desempenho do B1b: insercao em bloco na STG do errorlog\n\n"
                  "- Com o B1b a gravacao ficou a ~700-1.200 linhas/min e o ciclo de PRD (~9.900 linhas) nao cabia nos 5 minutos;\n"
                  "  a 15/09 o errorlog de PRD parou das 11:26 as 11:53 e o recolhedor anterior foi reposto. `store_data` passa a\n"
                  "  usar `fast_executemany`, como o `base_collector.py`, com `setinputsizes` explicito para o texto (condicao do\n"
                  "  guardiao). O log regista a duracao da insercao.\n\n")

TEST_SRC = r'''"""
PERF B1b (2026-09-15): store_data liga fast_executemany e declara o tamanho do texto ANTES do executemany.
"""
from datetime import datetime

import pytest

import scripts.collectors.collect_errorlog as mod

pytestmark = pytest.mark.unit


class Cur:
    def __init__(self, reg):
        self.reg = reg
        object.__setattr__(self, "fast_executemany", False)

    def __setattr__(self, n, v):
        if n == "fast_executemany":
            reg = self.__dict__.get("reg")
            if reg is not None:
                reg["ordem"].append(("fast_executemany", v))
        object.__setattr__(self, n, v)

    def execute(self, sql, params=()):
        pass

    def fetchone(self):
        return ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]

    def setinputsizes(self, sizes):
        self.reg["ordem"].append(("setinputsizes", sizes))

    def executemany(self, sql, batch):
        self.reg["ordem"].append(("executemany", len(list(batch))))


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


def test_insercao_em_bloco_com_tamanho_do_texto_declarado(monkeypatch):
    reg = {"ordem": [], "info": [], "erros": []}
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: Conn(reg))
    c = object.__new__(mod.ErrorLogCollector)
    c.logger = type("L", (), {"info": lambda self, m: reg["info"].append(m), "warning": lambda *a, **k: None,
                              "error": lambda self, m: reg["erros"].append(m)})()
    c._build_master_conn_str = lambda: "DRIVER=x"
    t = datetime(2026, 9, 15, 12, 0)
    linha = {"Instance": "A_I01", "Log_Date": t, "Process_Info": "p", "Log_Text": "x" * 3999, "Log_Text_Hash": 1,
             "Log_Type": "AvailabilityGroup", "Error_Number": None, "Severity": None, "State": None,
             "Log_File_Number": 0, "Update_TS": t}
    c.store_data(mod.pd.DataFrame([linha] * 2500), "PRD")
    assert reg["erros"] == []
    nomes = [o[0] for o in reg["ordem"]]
    assert nomes.index("fast_executemany") < nomes.index("setinputsizes") < nomes.index("executemany")
    assert ("fast_executemany", True) in reg["ordem"]
    tamanhos = dict(reg["ordem"])["setinputsizes"]
    assert len(tamanhos) == 11
    assert tamanhos[3] == (mod.pyodbc.SQL_WVARCHAR, 4000, 0)
    assert tamanhos[0] == (mod.pyodbc.SQL_VARCHAR, 128, 0) and tamanhos[5] == (mod.pyodbc.SQL_VARCHAR, 32, 0)
    assert [o[1] for o in reg["ordem"] if o[0] == "executemany"] == [1000, 1000, 500]
    assert any("Armazenados 2500 registros" in m and " s" in m for m in reg["info"])
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
    if "def _sql_int(" not in lf or "QUERY_TIMEOUT" not in lf:
        print('[ABORT] o recolhedor em disco nao e o do B1b com hotfix. Corre primeiro: '
              'git checkout HEAD -- "WATCHERDB INTELLIGENCE V1/scripts/collectors/collect_errorlog.py"'); return 1
    if src["test"].exists():
        print("[ABORT] o teste ja existe"); return 1
    for anc in (BATCH_OLD, LOG_OLD):
        if lf.count(anc) != 1:
            print(f"[ABORT] ancora {anc[:50]!r} encontrada {lf.count(anc)}x -- nada escrito"); return 1
    novo = lf.replace(BATCH_OLD, BATCH_NEW).replace(LOG_OLD, LOG_NEW)
    compile(novo, str(REL["collector"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    th = src["test_hotfix"].read_bytes().decode("utf-8")
    the = _eol(th)
    if th.count(HOTFIX_TEST_OLD.replace("\n", the)) != 1:
        print("[ABORT] teste do hotfix: ancora do cursor simulado nao unica -- nada escrito"); return 1
    th_novo = th.replace(HOTFIX_TEST_OLD.replace("\n", the), HOTFIX_TEST_NEW.replace("\n", the))
    chg = src["changelog"].read_bytes().decode("utf-8")
    ce = _eol(chg); anc = CHANGELOG_ANCORA.replace("\n", ce)
    if chg.count(anc) != 1:
        print("[ABORT] changelog V1: [Unreleased] nao unico"); return 1
    chg_novo = chg.replace(anc, CHANGELOG_NOVO.replace("\n", ce), 1)
    print(f"[ok] store_data com fast_executemany e setinputsizes; log com duracao; compila; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["collector"].write_bytes(novo.replace("\n", eol).encode("utf-8")); print(f"[write] {REL['collector']}")
    src["changelog"].write_bytes(chg_novo.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test_hotfix"].write_bytes(th_novo.encode("utf-8")); print(f"[write] {REL['test_hotfix']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print('\nAplicado. Corre os testes e Restart-Service WatcherDBCollector; mede a linha "Armazenados ... em S s" no log.')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
