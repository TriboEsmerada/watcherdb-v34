# -*- coding: utf-8 -*-
"""B1b (2026-09-15) -- o recolhedor de errorlog do V1 le so a janela e classifica. APLICAR DEPOIS do leitor do V3.4.

Pre-requisito: docs/context/ERRORLOG_LEITOR_TIPO_2026-09-15_apply.py aplicado e o servico V3.4 reiniciado. Sem isso,
a severidade que este lote passa a gravar pinta o cartao de errorlog de vermelho com o 33208 de auditoria.

O que muda em scripts/collectors/collect_errorlog.py (repo V1), no ciclo de 5 minutos:
  1. Le so os ultimos 65 minutos, pelo relogio do SERVIDOR monitorizado (o errorlog esta na hora local dele):
     xp_readerrorlog 0, 1, NULL, NULL, desde, ate, N'asc'. Datas em texto (o pyodbc manda datetime e o SQL Server
     recusa). Resultado vazio nao e' conjunto de resultados. Medido: SQLRPAPRD02 passa de 261.843 linhas em 20,9 s
     para 2.150 em 0,31 s; funciona em SQL 2012, 2016, 2019 e 2022.
  2. Timeout de CONSULTA de 60 s (conn.timeout). O timeout de ligacao nao cobre um xp_readerrorlog pendurado (uma
     leitura do log anterior de SQLHDSPRD214, 6,4 milhoes de linhas, ficou presa mais de 20 min a 15/09).
  3. Quando o log actual comecou dentro da janela (arranque ou rotacao), le tambem o log anterior na mesma janela,
     com o mesmo timeout; se falhar, regista aviso e fica com o log actual.
  4. Classifica com watcherdb_intelligence/collectors/errorlog_classifier.py (B1a): larga informativos, guarda
     arranques e encerramentos (que nao contem "Error" e o filtro antigo perdia), preenche Error_Number, Severity,
     State e Log_Type; os repetitivos entram linha a linha (a agregacao por hora e' da HIST, B2b, parecer do guardiao).
  5. Log_Text_Hash deterministico (crc32 com sinal). Verificado na base viva: nas STG BLUE/GREEN a coluna e' int
     normal sem chave primaria; na HIST e' calculada. Log_Type cabe (varchar(32)).
Nao muda: TRUNCATE + swap por ambiente, heartbeat do guard de frescura, esquema das tabelas, QA e TST.

Identidade: o recolhedor liga as instancias como sql_monitoring (ja era assim desde a Wave P) e so le.

Uso (raiz do repo V3.4; escreve no repo V1 ao lado):
  py docs/context/B1B_RECOLHEDOR_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B1B_RECOLHEDOR_ERRORLOG_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b1b.py tests/unit/test_errorlog_classifier.py -q -p no:cacheprovider
  Restart-Service WatcherDBCollector   (a classe fica em memoria no servico)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "collector": Path("scripts/collectors/collect_errorlog.py"),
    "classifier": Path("watcherdb_intelligence/collectors/errorlog_classifier.py"),
    "test": Path("tests/unit/test_collect_errorlog_b1b.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "QUERY_TIMEOUT"
METODO_INI = "    def collect_from_server(self, server_config):\n"
METODO_FIM = "    def collect_all(self, environment):\n"
METODO_SHA = "7df1ad84ba9ae1895e65156f4db8d098dec2cb316d2aa00b1ac2889eb1e0e029"   # medido a 15/09, quebras LF

METODO_NOVO = '''    def _read_window(self, cursor, log_number, desde, ate):
        """B1b: xp_readerrorlog so da janela [desde, ate].

        Datas em TEXTO: o pyodbc envia datetime e o SQL Server responde "The format for the date filter is incorrect".
        Sem linhas na janela o procedimento nao devolve conjunto de resultados (cursor.description None).
        """
        cursor.execute(
            f"EXEC master.dbo.xp_readerrorlog {int(log_number)}, 1, NULL, NULL, ?, ?, N'asc'",
            (desde.strftime("%Y%m%d %H:%M:%S"), ate.strftime("%Y%m%d %H:%M:%S")),
        )
        return cursor.fetchall() if cursor.description else []

    def collect_from_server(self, server_config):
        """Coleta a janela recente do errorlog de um servidor e classifica (B1b, 2026-09-15).

        Antes: lia o ficheiro actual INTEIRO com N'Error' a cada 5 min e filtrava 60 min em Python, sem timeout de
        consulta; descartava "This is an informational message", o que apagava os arranques.
        """
        server_id = server_config.server_id

        try:
            conn_str = self.get_connection_string(server_config)
            conn = pyodbc.connect(conn_str, timeout=self.TIMEOUT, autocommit=True)
            anterior = []
            try:
                conn.timeout = self.QUERY_TIMEOUT          # timeout de CONSULTA; o de ligacao nao cobre isto
                cursor = conn.cursor()
                cursor.execute("SELECT GETDATE()")          # relogio do servidor: o errorlog esta na hora dele
                ate = cursor.fetchone()[0]
                desde = ate - timedelta(minutes=self.WINDOW_MINUTES)
                actual = self._read_window(cursor, 0, desde, ate)
                # O cabecalho de versao so aparece no inicio de um ficheiro: o log actual comecou dentro da janela
                # (arranque ou rotacao), portanto o fim do anterior tambem la esta.
                if any((r[2] or "").lstrip().startswith("Microsoft SQL Server") for r in actual):
                    try:
                        anterior = self._read_window(conn.cursor(), 1, desde, ate)
                    except Exception as e:
                        self.logger.warning(f"{server_id}: log anterior nao lido na janela ({e}); fica o actual")
                        anterior = []
            finally:
                conn.close()

            data = []
            recolha = datetime.now()
            for numero, linhas in ((1, anterior), (0, actual)):
                for ev in classify(linhas):
                    if ev.action == DROP:
                        continue
                    log_text = ev.text[:4000]
                    data.append({
                        # FIND-20260421-NNN: mantem a canonicalizacao underscore do base_collector.py:273.
                        'Instance': server_id,
                        'Log_Date': ev.log_date,
                        'Process_Info': ev.process_info[:128],
                        'Log_Text': log_text,
                        'Log_Text_Hash': text_hash(log_text),
                        'Log_Type': ev.log_type,
                        'Error_Number': ev.error_number,
                        'Severity': ev.severity,
                        'State': ev.state,
                        'Log_File_Number': numero,
                        'Update_TS': recolha,
                    })
            return data

        except Exception as e:
            # Wave P (2026-05-21): promoted DEBUG -> WARNING. Silent failures eram
            # a razao do STALE nao gerar alerta (pre-Wave P log nao mostrava nada).
            self.logger.warning(f"Erro ao coletar de {server_id}: {e}")
            return []

'''

EDITS = [
    ("from watcherdb_intelligence.collectors.server_manager import ServerManager\n",
     "from watcherdb_intelligence.collectors.server_manager import ServerManager\n"
     "from watcherdb_intelligence.collectors.errorlog_classifier import DROP, classify, text_hash\n", 1),
    ("    TIMEOUT = 30\n",
     "    TIMEOUT = 30\n"
     "    # B1b 2026-09-15: janela de leitura (5 min de ciclo + folga) e timeout de consulta do xp_readerrorlog\n"
     "    WINDOW_MINUTES = 65\n"
     "    QUERY_TIMEOUT = 60\n", 1),
    ('            self.logger.info("Nenhum erro encontrado nos ultimos 60 minutos")\n',
     '            self.logger.info("Nenhum evento a guardar nos ultimos 65 minutos")\n', 1),
]

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Alterado — B1b: o recolhedor de errorlog le so a janela e classifica\n\n"
                  "- **`scripts/collectors/collect_errorlog.py`** le os ultimos 65 minutos pelo relogio do servidor\n"
                  "  (`xp_readerrorlog` com datas em texto) em vez do ficheiro inteiro com `N'Error'`: SQLRPAPRD02 passa de\n"
                  "  261.843 linhas em 20,9 s para 2.150 em 0,31 s. Timeout de consulta de 60 s; o log anterior so e' lido quando\n"
                  "  o actual comecou dentro da janela.\n"
                  "- **Classifica** com o modulo B1a: arranques e encerramentos passam a entrar; Error_Number, Severity, State e\n"
                  "  Log_Type deixam de ser vazios; informativos saem; hash deterministico.\n"
                  "- **Pre-requisito no V3.4:** o cartao de errorlog passou a contar pelo tipo (lote ERRORLOG_LEITOR_TIPO), senao\n"
                  "  a severidade 17 do 33208 de auditoria pintava cerca de dez instancias de vermelho.\n\n")

TEST_SRC = r'''"""
B1b (2026-09-15): collect_from_server le so a janela, com timeout de consulta, e classifica. Ligacao simulada.
"""
from datetime import datetime

import pytest

import scripts.collectors.collect_errorlog as mod

pytestmark = pytest.mark.unit
AGORA = datetime(2026, 9, 15, 11, 0, 0)


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.description, self._rows = conn, None, []

    def execute(self, sql, params=()):
        self.conn.chamadas.append((sql, params))
        if sql.startswith("SELECT GETDATE()"):
            self._rows, self.description = [(AGORA,)], [("x",)]
            return
        assert "xp_readerrorlog" in sql and "N'Error'" not in sql
        assert all(isinstance(p, str) for p in params), "datas tem de ir em texto"
        numero = int(sql.split("xp_readerrorlog")[1].split(",")[0])
        if numero in self.conn.falha:
            raise RuntimeError("Query timeout expired")
        rows = self.conn.logs.get(numero, [])
        self._rows, self.description = rows, ([("LogDate",)] if rows else None)

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self, logs, falha=()):
        self.logs, self.falha, self.chamadas, self.timeout, self.fechada = logs, set(falha), [], 0, False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.fechada = True


def coletor(monkeypatch, conn):
    c = object.__new__(mod.ErrorLogCollector)
    c.logger = type("L", (), {"warning": lambda *a, **k: None, "info": lambda *a, **k: None})()
    c.get_connection_string = lambda cfg: "DRIVER=x"
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: conn)
    return c


CFG = type("Cfg", (), {"server_id": "SRV_I01"})()
t = lambda h, m: datetime(2026, 9, 15, h, m)


def test_le_so_a_janela_com_timeout_e_classifica(monkeypatch):
    conn = FakeConn({0: [
        (t(10, 1), "Logon", "Error: 18456, Severity: 14, State: 5."), (t(10, 1), "Logon", "Login failed for user 'a'."),
        (t(10, 2), "spid9", "Log was backed up. Database: X."),
        (t(10, 3), "spid9", "Error: 824, Severity: 24, State: 2."), (t(10, 3), "spid9", "SQL Server detected a logical consistency-based I/O error."),
    ]})
    data = coletor(monkeypatch, conn).collect_from_server(CFG)
    assert conn.timeout == 60 and conn.fechada
    sql, params = conn.chamadas[1]
    assert params == ("20260915 09:55:00", "20260915 11:00:00")
    assert len([c for c in conn.chamadas if "xp_readerrorlog 1" in c[0]]) == 0, "sem arranque nao le o log anterior"
    assert [(d["Log_Type"], d["Error_Number"], d["Severity"], d["State"]) for d in data] == [("Security", 18456, 14, 5), ("Critical", 824, 24, 2)]
    assert data[0]["Log_Text"].startswith("Error: 18456, Severity: 14, State: 5. Login failed")
    assert data[0]["Log_Text_Hash"] == mod.text_hash(data[0]["Log_Text"]) and data[0]["Log_File_Number"] == 0


def test_arranque_na_janela_le_o_log_anterior(monkeypatch):
    conn = FakeConn({
        1: [(t(10, 10), "spid5s", "SQL Server is terminating in response to a 'stop' request from Service Control Manager.")],
        0: [(t(10, 12), "Server", "Microsoft SQL Server 2022 (RTM-CU14) - 16.0.4135.4 (X64)"),
            (t(10, 12), "Server", "SQL Server is starting at normal priority base (=7). This is an informational message only. No user action is required.")],
    })
    data = coletor(monkeypatch, conn).collect_from_server(CFG)
    assert [(d["Log_Type"], d["Log_File_Number"]) for d in data] == [("Lifecycle", 1), ("Lifecycle", 0)]


def test_falha_no_log_anterior_nao_perde_o_actual(monkeypatch):
    conn = FakeConn({0: [(t(10, 12), "Server", "Microsoft SQL Server 2019"),
                         (t(10, 12), "Server", "SQL Server is starting at normal priority base (=7).")]}, falha={1})
    data = coletor(monkeypatch, conn).collect_from_server(CFG)
    assert [d["Log_Type"] for d in data] == ["Lifecycle"]


def test_janela_vazia_nao_rebenta(monkeypatch):
    conn = FakeConn({0: []})
    assert coletor(monkeypatch, conn).collect_from_server(CFG) == []
    assert conn.fechada


def test_erro_de_ligacao_devolve_lista_vazia(monkeypatch):
    c = coletor(monkeypatch, FakeConn({}))
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("login failed")))
    assert c.collect_from_server(CFG) == []
'''


def _eol(t):
    return "\r\n" if "\r\n" in t else "\n"


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or V1
    src = {k: base / p for k, p in REL.items()}
    if not src["classifier"].exists():
        print("[ABORT] o B1a (errorlog_classifier.py) nao esta aplicado neste repo V1"); return 1
    raw = src["collector"].read_bytes().decode("utf-8")
    eol = _eol(raw)
    lf = raw.replace("\r\n", "\n")
    if MARK in lf:
        print("[ABORT] ja aplicado"); return 1
    if src["test"].exists():
        print("[ABORT] o teste ja existe"); return 1
    a = lf.index(METODO_INI); b = lf.index(METODO_FIM)
    sha = hashlib.sha256(lf[a:b].encode("utf-8")).hexdigest()
    if sha != METODO_SHA:
        print(f"[ABORT] collect_from_server mudou desde a medicao (sha {sha[:12]}) -- nada escrito"); return 1
    novo = lf[:a] + METODO_NOVO + lf[b:]
    for old, new, count in EDITS:
        if novo.count(old) != count:
            print(f"[ABORT] ancora {old[:60]!r} encontrada {novo.count(old)}x -- nada escrito"); return 1
        novo = novo.replace(old, new)
    compile(novo, str(REL["collector"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    chg = src["changelog"].read_bytes().decode("utf-8")
    ceol = _eol(chg)
    anc = CHANGELOG_ANCORA.replace("\n", ceol)
    if chg.count(anc) != 1 or "B1b: o recolhedor" in chg:
        print("[ABORT] changelog V1: ancora [Unreleased] nao unica ou entrada ja existe"); return 1
    chg_novo = chg.replace(anc, CHANGELOG_NOVO.replace("\n", ceol), 1)
    print(f"[ok] collect_from_server substituido (sha confere) + {len(EDITS)} ancoras; compila; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["collector"].write_bytes(novo.replace("\n", eol).encode("utf-8")); print(f"[write] {REL['collector']}")
    src["changelog"].write_bytes(chg_novo.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print('\nAplicado. Corre: cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b1b.py tests/unit/test_errorlog_classifier.py -q -p no:cacheprovider ; Restart-Service WatcherDBCollector')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
