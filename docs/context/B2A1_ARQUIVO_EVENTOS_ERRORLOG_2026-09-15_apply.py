# -*- coding: utf-8 -*-
"""B2a-1 (2026-09-15) -- historico do errorlog a cada ciclo (so eventos) e applock por ambiente no recolhedor.

Desenho acordado com o guardiao do recolhedor depois do veto ao primeiro desenho (15/09), sobre a baseline B2a-0:
  - PROCEDURE NOVA dbo.usp_archive_errorlog_events, em vez de parametrizar a usp_archive_errorlog (que o job das 05:00
    continua a usar tal como esta na baseline). Arquiva da STG activa para a HIST so Log_Type Lifecycle,
    AvailabilityGroup, Critical e Error, com a mesma deduplicacao por conteudo da proc viva (Instance, Log_Date,
    CHECKSUM(Log_Text), sem Update_TS: condicao do guardiao). Repetitive e Security ficam para o B2b (agregacao horaria);
    arquiva-los linha a linha levava a HIST de ~33 mil para ~400 mil linhas por dia.
  - sp_getapplock com owner Transaction e timeout de 5 s (guardiao): liberta sozinho no COMMIT/ROLLBACK; ocupado = salta.
  - Recolhedor: applock por ambiente antes do TRUNCATE (padrao base_collector.py:492-507). Visto a 15/09: um ciclo novo
    de PRD truncou a tabela inactiva a meio do anterior e perdeu-se um ciclo. Depois do swap chama a proc em try proprio;
    se a migration 012 ainda nao correu, regista aviso e o KPI segue.
Permissoes: o recolhedor escreve na Intelligence como sql_monitoring, que e db_owner (medido): nao ha GRANT a fazer.

Escreve no repo V1 (regra 2: mudanca de BD = canonico + documentacao no mesmo bloco):
  database/migrations/012_errorlog_arquivo_eventos_por_ciclo.sql   nova; o OWNER corre-a com a conta de deploy (regra 5)
  database/INSTALACAO_COMPLETA_UNIFICADA.sql                      seccao 36 no fim com a mesma procedure
  scripts/collectors/collect_errorlog.py                          applock e chamada ao arquivo
  tests/unit/test_collect_errorlog_b2a1.py                        novo; ajusta os cursores simulados de dois testes
  docs/CHANGELOG.md

Uso (raiz do repo V3.4):
  py docs/context/B2A1_ARQUIVO_EVENTOS_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B2A1_ARQUIVO_EVENTOS_ERRORLOG_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b2a1.py tests/unit/test_collect_errorlog_perf.py tests/unit/test_collect_errorlog_hotfix_nan.py tests/unit/test_collect_errorlog_b1b.py tests/unit/test_errorlog_classifier.py -q -p no:cacheprovider
  SSMS, servidor da Intelligence, conta de deploy: database/migrations/012_errorlog_arquivo_eventos_por_ciclo.sql
  Restart-Service WatcherDBCollector
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "migration": Path("database/migrations/012_errorlog_arquivo_eventos_por_ciclo.sql"),
    "canonical": Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"),
    "collector": Path("scripts/collectors/collect_errorlog.py"),
    "test": Path("tests/unit/test_collect_errorlog_b2a1.py"),
    "test_hotfix": Path("tests/unit/test_collect_errorlog_hotfix_nan.py"),
    "test_perf": Path("tests/unit/test_collect_errorlog_perf.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "usp_archive_errorlog_events"

PROC_SQL = """IF OBJECT_ID('dbo.usp_archive_errorlog_events', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_archive_errorlog_events;
GO

CREATE PROCEDURE dbo.usp_archive_errorlog_events
    @days_to_archive INT = 1
AS
BEGIN
    -- B2a-1 2026-09-15: chamada pelo recolhedor de errorlog depois de cada swap. So eventos; Repetitive e Security
    -- ficam para a agregacao horaria do B2b. Deduplicacao por conteudo, sem Update_TS (condicao do guardiao).
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @rows INT = 0;
    DECLARE @lock INT;
    DECLARE @cutoff DATETIME2 = DATEADD(DAY, -@days_to_archive, GETDATE());

    IF OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_STG') IS NULL OR OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_HIST') IS NULL
    BEGIN
        PRINT 'usp_archive_errorlog_events: STG ou HIST ausente nesta base, nada a fazer.';
        SELECT CAST(0 AS INT) AS rows_archived;
        RETURN 0;
    END;

    BEGIN TRANSACTION;

    -- Owner Transaction: liberta sozinho no COMMIT ou ROLLBACK. Ocupado mais de 5 s: salta este ciclo.
    EXEC @lock = sp_getapplock @Resource = N'ARCHIVE_KPI_MSSQL_ERRORLOG_EVENTS', @LockMode = 'Exclusive',
                               @LockOwner = 'Transaction', @LockTimeout = 5000;
    IF @lock < 0
    BEGIN
        ROLLBACK TRANSACTION;
        SELECT CAST(-1 AS INT) AS rows_archived;
        RETURN 1;
    END;

    ;WITH dedup AS (
        SELECT Instance, Log_Date, Process_Info, Log_Text, Log_Type,
               Error_Number, Severity, State, Log_File_Number, Update_TS,
               ROW_NUMBER() OVER (PARTITION BY Instance, Log_Date, CHECKSUM(Log_Text) ORDER BY Update_TS ASC) AS rn
        FROM dbo.KPI_MSSQL_ERRORLOG_STG WITH (NOLOCK)
        WHERE Log_Date >= @cutoff
          AND Log_Type IN ('Lifecycle', 'AvailabilityGroup', 'Critical', 'Error')
    )
    INSERT INTO dbo.KPI_MSSQL_ERRORLOG_HIST
        (Instance, Log_Date, Process_Info, Log_Text, Log_Type,
         Error_Number, Severity, State, Log_File_Number, Update_TS)
    SELECT d.Instance, d.Log_Date, d.Process_Info, d.Log_Text, d.Log_Type,
           d.Error_Number, d.Severity, d.State, d.Log_File_Number, d.Update_TS
    FROM dedup d
    WHERE d.rn = 1
      AND NOT EXISTS (
          SELECT 1 FROM dbo.KPI_MSSQL_ERRORLOG_HIST h
          WHERE h.Instance = d.Instance
            AND h.Log_Date = d.Log_Date
            AND h.Log_Text_Hash = CHECKSUM(d.Log_Text)
      );
    SET @rows = @@ROWCOUNT;

    COMMIT TRANSACTION;
    SELECT @rows AS rows_archived;
    RETURN 0;
END;
GO
"""

MIGRATION_SQL = """-- ============================================================================
-- Migration 012: historico do errorlog a cada ciclo, so eventos (B2a-1)
-- ----------------------------------------------------------------------------
-- Data: 2026-09-15 | Gate: watcherdb-v1-intel-specialist (desenho revisto depois do veto de 15/09)
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring) | Onde: servidor da WatcherDB_Intelligence
--
-- CONTEXTO (medido na base viva, baseline em database/baseline/errorlog_familia_viva_2026-09-15.sql):
--   A KPI_MSSQL_ERRORLOG_HIST so era escrita pela usp_archive_errorlog no job diario das 05:00, uma fotografia da STG
--   (que guarda so os ultimos 65 min). Um arranque as 14:00 so ficava no historico se ainda estivesse na STG as 05:00.
--   Esta procedure nova e chamada pelo recolhedor depois de cada swap e arquiva so eventos (Lifecycle,
--   AvailabilityGroup, Critical, Error). Repetitive e Security ficam para a agregacao horaria do B2b.
--
-- O QUE FAZ: cria dbo.usp_archive_errorlog_events. Nao muda tabelas, nao muda a usp_archive_errorlog nem o job das 05:00.
-- PERMISSOES: o recolhedor liga como sql_monitoring, db_owner na Intelligence (medido a 15/09): nao ha GRANT.
-- ORDEM: pode correr antes ou depois de actualizar o recolhedor (sem a proc, o recolhedor regista aviso e segue).
-- Idempotente. ROLLBACK: DROP PROCEDURE dbo.usp_archive_errorlog_events; (o recolhedor passa a registar aviso).
-- ============================================================================
USE [WatcherDB_Intelligence];
GO

""" + PROC_SQL + """
-- Verificacao: esperado 1 linha com a procedure criada agora
SELECT name, create_date FROM sys.procedures WHERE name = 'usp_archive_errorlog_events';
GO
"""

CANONICAL_SECTION = """
-- ============================================================================
-- SECAO 36: HISTORICO DO ERRORLOG A CADA CICLO, SO EVENTOS (B2a-1, 2026-09-15, migration 012)
-- ============================================================================
-- Chamada pelo recolhedor scripts/collectors/collect_errorlog.py depois de cada swap. A usp_archive_errorlog e o job
-- das 05:00 continuam como estao (baseline em database/baseline/errorlog_familia_viva_2026-09-15.sql).
-- NOTA: a DDL da familia KPI_MSSQL_ERRORLOG (base, _BLUE/_GREEN, HIST) ainda nao esta alinhada neste canonico; o bloco
-- comentado das seccoes STG 13 e HIST 4 esta obsoleto. Lote proprio, a seguir (parecer do guardiao, 15/09).
-- ============================================================================
""" + PROC_SQL + """
PRINT '  [OK] usp_archive_errorlog_events (SECAO 36)';
GO
"""

ARCHIVE_METHOD = '''    def _archive_events(self, cursor):
        """B2a-1 2026-09-15: arquiva os eventos da STG activa na HIST (dbo.usp_archive_errorlog_events, migration 012).

        Try proprio: falhar o arquivo nao pode falhar o KPI (padrao Wave A). Devolve as linhas arquivadas, -1 se outro
        arquivo tinha o lock, ou None se a chamada falhou (por exemplo, migration 012 ainda por correr).
        """
        try:
            cursor.execute("SET NOCOUNT ON; EXEC dbo.usp_archive_errorlog_events @days_to_archive = 1;")
            linhas = None
            while True:
                if cursor.description:
                    r = cursor.fetchone()
                    if r is not None:
                        linhas = r[0]
                if not cursor.nextset():
                    break
            if linhas is not None and linhas < 0:
                self.logger.warning("Arquivo de eventos saltado neste ciclo: outro arquivo tinha o lock")
            else:
                self.logger.info(f"Arquivo de eventos na HIST: {linhas} linhas novas")
            return linhas
        except Exception as e:
            self.logger.warning(f"Arquivo de eventos falhou (o KPI segue): {e}")
            return None

'''

LOCK_OLD = """            conn = pyodbc.connect(conn_str, autocommit=True, timeout=60)
            cursor = conn.cursor()

"""
LOCK_NEW = """            conn = pyodbc.connect(conn_str, autocommit=True, timeout=60)
            cursor = conn.cursor()

            # B2a-1 2026-09-15: applock por ambiente (padrao base_collector.py:492-507). Visto a 15/09: um ciclo novo de PRD
            # truncou a tabela inactiva a meio do anterior e perdeu-se um ciclo inteiro. Owner Session: liberta no close.
            recurso_lock = f"COLLECTOR_{self.TARGET_TABLE}_{env_suffix}"
            cursor.execute(
                "SET NOCOUNT ON; DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
                "@LockOwner = 'Session', @LockTimeout = 60000; SELECT @r;",
                (recurso_lock,)
            )
            if cursor.fetchone()[0] < 0:
                self.logger.error(f"Store abortado: lock {recurso_lock} ocupado ha mais de 60 s (outro ciclo a gravar)")
                conn.close()
                return

"""
SWAP_OLD = '            self.logger.info(f"SWAP executado para {self.TARGET_TABLE} ({len(df)} registros)")\n'
SWAP_NEW = (SWAP_OLD +
            "\n            # B2a-1 2026-09-15: historico a cada ciclo, so eventos; try proprio dentro do metodo\n"
            "            self._archive_events(cursor)\n")
STORE_ANCHOR = "    def store_data(self, df, environment):\n"

HOTFIX_FETCH_OLD = '    def fetchone(self):\n        return ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]\n'
HOTFIX_FETCH_NEW = ('    def fetchone(self):\n'
                    '        # B2a-1: o store_data pede primeiro o applock (SELECT @r)\n'
                    '        if self.reg["execute"] and "sp_getapplock" in self.reg["execute"][-1][0]:\n'
                    '            return [1]\n'
                    '        return ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]\n')
PERF_EXEC_OLD = "    def execute(self, sql, params=()):\n        pass\n"
PERF_EXEC_NEW = "    def execute(self, sql, params=()):\n        self.__dict__[\"ultimo\"] = sql\n"
PERF_FETCH_OLD = '    def fetchone(self):\n        return ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]\n'
PERF_FETCH_NEW = ('    def fetchone(self):\n'
                  '        # B2a-1: o store_data pede primeiro o applock (SELECT @r)\n'
                  '        if "sp_getapplock" in self.__dict__.get("ultimo", ""):\n'
                  '            return [1]\n'
                  '        return ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]\n')

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Adicionado — B2a-1: historico do errorlog a cada ciclo (migration 012)\n\n"
                  "- **`dbo.usp_archive_errorlog_events`** (migration 012 e seccao 36 do canonico): arquiva na HIST, depois de cada\n"
                  "  swap, so os eventos (Lifecycle, AvailabilityGroup, Critical, Error), com deduplicacao por conteudo e applock de\n"
                  "  transaccao de 5 s. Antes a HIST era uma fotografia diaria das 05:00 da STG, que guarda so 65 minutos.\n"
                  "- **Recolhedor de errorlog:** applock por ambiente antes do TRUNCATE (a 15/09 um ciclo de PRD sobreposto apagou\n"
                  "  o anterior) e chamada ao arquivo em try proprio. Sem a migration, regista aviso e o KPI segue.\n\n")

TEST_SRC = r'''"""
B2a-1 (2026-09-15): store_data pede o applock por ambiente antes do TRUNCATE e arquiva os eventos depois do swap.
"""
from datetime import datetime

import pytest

import scripts.collectors.collect_errorlog as mod

pytestmark = pytest.mark.unit


class Cur:
    def __init__(self, reg):
        self.reg = reg
        self.description = None
        self._uma = None
        self._conjuntos = []

    def execute(self, sql, params=()):
        self.reg["sql"].append(sql)
        self.description, self._uma, self._conjuntos = None, None, []
        if "sp_getapplock" in sql:
            self.description, self._uma = [("r",)], [self.reg["lock"]]
        elif "fn_get_kpi_collection_target_env" in sql:
            self.description, self._uma = [("t",)], ["KPI_MSSQL_ERRORLOG_STG_BLUE_PRD"]
        elif "usp_archive_errorlog_events" in sql:
            if self.reg.get("arquivo_falha"):
                raise RuntimeError("Could not find stored procedure 'dbo.usp_archive_errorlog_events'")
            self._conjuntos = [[(self.reg["arquivadas"],)]]
            self.description, self._uma = [("rows_archived",)], [self.reg["arquivadas"]]

    def fetchone(self):
        return self._uma

    def nextset(self):
        return False

    def executemany(self, sql, batch):
        self.reg["sql"].append("INSERT_LOTE")

    def setinputsizes(self, sizes):
        pass


class Conn:
    def __init__(self, reg):
        self.reg = reg

    def cursor(self):
        return Cur(self.reg)

    def close(self):
        self.reg["fechada"] = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def coletor(monkeypatch, reg):
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: Conn(reg))
    c = object.__new__(mod.ErrorLogCollector)
    c.logger = type("L", (), {"info": lambda self, m: reg["info"].append(m),
                              "warning": lambda self, m: reg["avisos"].append(m),
                              "error": lambda self, m: reg["erros"].append(m)})()
    c._build_master_conn_str = lambda: "DRIVER=x"
    return c


def df():
    t = datetime(2026, 9, 15, 14, 0)
    return mod.pd.DataFrame([{"Instance": "A_I01", "Log_Date": t, "Process_Info": "Server", "Log_Text": "SQL Server is starting",
                              "Log_Text_Hash": 1, "Log_Type": "Lifecycle", "Error_Number": None, "Severity": None,
                              "State": None, "Log_File_Number": 0, "Update_TS": t}])


def novo_reg(**kw):
    reg = {"sql": [], "info": [], "avisos": [], "erros": [], "lock": 0, "arquivadas": 3}
    reg.update(kw)
    return reg


def test_lock_antes_do_truncate_e_arquivo_depois_do_swap(monkeypatch):
    reg = novo_reg()
    coletor(monkeypatch, reg).store_data(df(), "PRD")
    sql = reg["sql"]
    i_lock = next(i for i, s in enumerate(sql) if "sp_getapplock" in s)
    i_trunc = next(i for i, s in enumerate(sql) if s.startswith("TRUNCATE"))
    i_swap = next(i for i, s in enumerate(sql) if "usp_swap_kpi_stg_tables" in s)
    i_arq = next(i for i, s in enumerate(sql) if "usp_archive_errorlog_events" in s)
    assert i_lock < i_trunc < i_swap < i_arq
    assert reg["erros"] == []
    assert any("Arquivo de eventos na HIST: 3 linhas novas" in m for m in reg["info"])


def test_lock_ocupado_nao_toca_na_tabela(monkeypatch):
    reg = novo_reg(lock=-1)
    coletor(monkeypatch, reg).store_data(df(), "PRD")
    assert not any(s.startswith("TRUNCATE") or s == "INSERT_LOTE" or "usp_swap" in s for s in reg["sql"])
    assert reg.get("fechada") is True
    assert any("lock COLLECTOR_KPI_MSSQL_ERRORLOG_STG_PRD ocupado" in m for m in reg["erros"])


def test_sem_migration_o_kpi_segue(monkeypatch):
    reg = novo_reg(arquivo_falha=True)
    coletor(monkeypatch, reg).store_data(df(), "PRD")
    assert reg["erros"] == []
    assert any("usp_swap_kpi_stg_tables" in s for s in reg["sql"])
    assert any("Arquivo de eventos falhou (o KPI segue)" in m for m in reg["avisos"])


def test_arquivo_ocupado_regista_aviso(monkeypatch):
    reg = novo_reg(arquivadas=-1)
    coletor(monkeypatch, reg).store_data(df(), "PRD")
    assert any("outro arquivo tinha o lock" in m for m in reg["avisos"])
'''


def _eol(t):
    return "\r\n" if "\r\n" in t else "\n"


def _edit(text, edits, label):
    eol = _eol(text)
    lf = text.replace("\r\n", "\n")
    for old, new in edits:
        if lf.count(old) != 1:
            raise SystemExit(f"[ABORT] {label}: ancora encontrada {lf.count(old)}x -- nada escrito\n  {old[:80]!r}")
        lf = lf.replace(old, new)
    return lf.replace("\n", eol)


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or V1
    src = {k: base / p for k, p in REL.items()}
    if src["migration"].exists():
        print("[ABORT] ja aplicado (migration 012 existe)"); return 1
    col = src["collector"].read_bytes().decode("utf-8")
    if MARK in col or "fast_executemany" not in col:
        print("[ABORT] recolhedor inesperado: ja tem o B2a-1 ou nao tem o lote de desempenho"); return 1
    out = {
        "collector": _edit(col, [(STORE_ANCHOR, ARCHIVE_METHOD + STORE_ANCHOR), (LOCK_OLD, LOCK_NEW), (SWAP_OLD, SWAP_NEW)], "recolhedor"),
        "test_hotfix": _edit(src["test_hotfix"].read_bytes().decode("utf-8"), [(HOTFIX_FETCH_OLD, HOTFIX_FETCH_NEW)], "teste hotfix"),
        "test_perf": _edit(src["test_perf"].read_bytes().decode("utf-8"), [(PERF_EXEC_OLD, PERF_EXEC_NEW), (PERF_FETCH_OLD, PERF_FETCH_NEW)], "teste perf"),
        "changelog": _edit(src["changelog"].read_bytes().decode("utf-8"), [(CHANGELOG_ANCORA, CHANGELOG_NOVO)], "changelog"),
    }
    can = src["canonical"].read_bytes().decode("utf-8")
    if MARK in can:
        print("[ABORT] canonico ja tem a procedure"); return 1
    cauda = can.replace("\r\n", "\n").rstrip()
    if not cauda.endswith("GO") or "SECAO 35 MIRRORING QUEUE HIST - CONCLUIDA" not in cauda[-400:]:
        print("[ABORT] o canonico nao termina na seccao 35 como medido -- nada escrito"); return 1
    ceol = _eol(can)
    out["canonical"] = can + ("" if can.endswith(("\n", "\r\n")) else ceol) + CANONICAL_SECTION.replace("\n", ceol)
    compile(out["collector"].replace("\r\n", "\n"), str(REL["collector"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] recolhedor 3 blocos (compila); canonico seccao 36; migration 012; 2 testes ajustados; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["migration"].write_bytes(MIGRATION_SQL.replace("\n", "\r\n").encode("utf-8")); print(f"[new]   {REL['migration']}")
    for k in ("collector", "canonical", "test_hotfix", "test_perf", "changelog"):
        src[k].write_bytes(out[k].encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Testes, depois a migration 012 no SSMS com a conta de deploy, depois Restart-Service WatcherDBCollector.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
