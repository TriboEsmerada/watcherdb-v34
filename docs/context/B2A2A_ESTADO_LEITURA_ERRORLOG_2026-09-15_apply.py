# -*- coding: utf-8 -*-
"""B2a-2a (2026-09-15) -- estado de leitura do errorlog por instancia (marca de agua, sem mudar a leitura).

Desenho: docs/context/B2A2_DESENHO_MARCA_AGUA_ERRORLOG_2026-09-15.md (V3.4). Gate do guardiao do recolhedor: GO com
ajustes, todos incorporados:
  1. Nome WDB_ERRORLOG_READ_STATE (o prefixo KPI_MSSQL_ e do contrato BLUE/GREEN); forma das tabelas de estado da
     seccao 19 (PK so Instance, MERGE, nunca TRUNCATE, GRANT SELECT a sql_monitoring).
  2. PWD= removido da mensagem antes de gravar e antes de logar (o driver pode ecoar a connection string).
  3. O heartbeat do ciclo sem linhas nunca corria no servico: o adapter chama collect_all e sai sem store_data. Corrigido
     no adapter e no run(); so escreve com pelo menos uma instancia lida (um ciclo cego nao pode parecer fresco).
  4. B2a-2a e B2a-2b (recuperar a janela perdida) em migrations separadas. Este lote nao muda a leitura.
  5. Estado gravado fora do applock do store e antes do TRUNCATE: regista a tentativa mesmo que o store falhe.

Problema medido a 15/09 (sql_monitoring): 63 instancias no inventario, 40 com linhas na HIST em 7 dias, 29 na STG; o
recolhedor devolvia [] tanto para "li e nao havia linhas" como para "nao consegui ligar". Heartbeat so global.

O que muda:
  V1 scripts/collectors/collect_errorlog.py  estado por instancia em cada leitura (ok, relogio do servidor, linhas, logs
                                             lidos; em falha classe e texto saneado); registar_estado(); logs saneados;
                                             run() com estado e heartbeat no ciclo vazio.
  V1 services/collector_service/collectors/collect_errorlog.py  o caminho real do servico: estado + heartbeat.
  V1 database/migrations/014_errorlog_estado_leitura_por_instancia.sql  tabela, procedure, GRANT, ensaio com ROLLBACK.
  V1 database/INSTALACAO_COMPLETA_UNIFICADA.sql  seccao 38 (os mesmos objectos).
  V1 tests/unit/test_collect_errorlog_b2a2a.py ; V1 docs/CHANGELOG.md

Ordem obrigatoria: migration 014 ANTES de reiniciar o servico do recolhedor. Sem ela o recolhedor so avisa
("Estado de leitura por instancia falhou (o KPI segue)") e continua.

Uso (raiz do repo V3.4):
  py docs/context/B2A2A_ESTADO_LEITURA_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B2A2A_ESTADO_LEITURA_ERRORLOG_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b2a2a.py tests/unit/test_collect_errorlog_b1b.py tests/unit/test_collect_errorlog_b2a1.py -q -p no:cacheprovider
  SSMS, servidor da Intelligence, CONTA DE DEPLOY: database/migrations/014_errorlog_estado_leitura_por_instancia.sql
  Restart-Service WatcherDBCollector
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "collector": Path("scripts/collectors/collect_errorlog.py"),
    "adapter": Path("services/collector_service/collectors/collect_errorlog.py"),
    "migration": Path("database/migrations/014_errorlog_estado_leitura_por_instancia.sql"),
    "canonical": Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"),
    "test": Path("tests/unit/test_collect_errorlog_b2a2a.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "WDB_ERRORLOG_READ_STATE"

# ---------------------------------------------------------------- SQL (migration e canonico)
OBJETOS_SQL = """IF OBJECT_ID('dbo.WDB_ERRORLOG_READ_STATE', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WDB_ERRORLOG_READ_STATE (
        Instance              VARCHAR(128)  NOT NULL,   -- server_id com underscore, igual a KPI_MSSQL_ERRORLOG_STG.Instance
        Environment           VARCHAR(8)    NOT NULL,   -- PRD, QA, TST (informativo; cada instancia so tem um)
        Last_Attempt_TS       DATETIME2     NOT NULL,   -- relogio do recolhedor
        Last_Success_TS       DATETIME2     NULL,
        Read_Until_Server_TS  DATETIME2     NULL,       -- fim da ultima janela lida, relogio do servidor (a marca de agua)
        Rows_Read             INT           NULL,       -- linhas guardadas da ultima leitura boa (depois do classificador)
        Logs_Read             TINYINT       NULL,       -- 1, ou 2 quando leu tambem o log anterior (rotacao na janela)
        Consecutive_Failures  INT           NOT NULL CONSTRAINT DF_WDB_ELRS_FALHAS DEFAULT 0,
        First_Failure_TS      DATETIME2     NULL,       -- inicio da serie de falhas em curso (NULL depois de uma leitura boa)
        Last_Failure_TS       DATETIME2     NULL,       -- ultima falha (fica depois de uma leitura boa)
        Last_Failure_Class    VARCHAR(32)   NULL,       -- connect, login_failed, permission, query_timeout, other
        Last_Failure_Text     NVARCHAR(400) NULL,       -- mensagem do driver saneada no recolhedor (sem PWD)
        Updated_At            DATETIME2     NOT NULL CONSTRAINT DF_WDB_ELRS_UPD DEFAULT GETDATE(),
        CONSTRAINT PK_WDB_ERRORLOG_READ_STATE PRIMARY KEY CLUSTERED (Instance)
    );
    PRINT '  [OK] Tabela WDB_ERRORLOG_READ_STATE criada';
END
ELSE
    PRINT '  [INFO] Tabela WDB_ERRORLOG_READ_STATE ja existe';
GO

CREATE OR ALTER PROCEDURE dbo.usp_errorlog_read_state_upsert
    @environment VARCHAR(8), @json NVARCHAR(MAX)
AS
BEGIN
    -- B2a-2a 2026-09-15: um MERGE por ciclo do recolhedor do errorlog. JSON: lista de objectos com instance, ok,
    -- attempt_ts e, na leitura boa, read_until_server_ts, rows_read, logs_read; na falha, failure_class, failure_text.
    -- Uma tentativa mais antiga do que a registada e ignorada (ciclos sobrepostos nao andam para tras).
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @json IS NULL OR ISJSON(@json) <> 1
    BEGIN
        RAISERROR('usp_errorlog_read_state_upsert: @json invalido. Nada gravado.', 16, 1);
        RETURN 1;
    END;
    DECLARE @agora DATETIME2 = GETDATE();

    MERGE dbo.WDB_ERRORLOG_READ_STATE WITH (HOLDLOCK) AS t
    USING (
        SELECT j.instance, ISNULL(j.ok, 0) AS ok, j.attempt_ts, j.read_until_server_ts, j.rows_read, j.logs_read,
               j.failure_class, LEFT(j.failure_text, 400) AS failure_text
        FROM OPENJSON(@json) WITH (
            instance             VARCHAR(128)   '$.instance',
            ok                   BIT            '$.ok',
            attempt_ts           DATETIME2      '$.attempt_ts',
            read_until_server_ts DATETIME2      '$.read_until_server_ts',
            rows_read            INT            '$.rows_read',
            logs_read            TINYINT        '$.logs_read',
            failure_class        VARCHAR(32)    '$.failure_class',
            failure_text         NVARCHAR(4000) '$.failure_text'
        ) j
        WHERE j.instance IS NOT NULL AND j.attempt_ts IS NOT NULL
    ) AS s
    ON t.Instance = s.instance
    WHEN MATCHED AND s.attempt_ts >= t.Last_Attempt_TS THEN UPDATE SET
        Environment          = @environment,
        Last_Attempt_TS      = s.attempt_ts,
        Last_Success_TS      = CASE WHEN s.ok = 1 THEN s.attempt_ts ELSE t.Last_Success_TS END,
        Read_Until_Server_TS = CASE WHEN s.ok = 1 THEN s.read_until_server_ts ELSE t.Read_Until_Server_TS END,
        Rows_Read            = CASE WHEN s.ok = 1 THEN s.rows_read ELSE t.Rows_Read END,
        Logs_Read            = CASE WHEN s.ok = 1 THEN s.logs_read ELSE t.Logs_Read END,
        Consecutive_Failures = CASE WHEN s.ok = 1 THEN 0 ELSE t.Consecutive_Failures + 1 END,
        First_Failure_TS     = CASE WHEN s.ok = 1 THEN NULL
                                    WHEN t.Consecutive_Failures = 0 THEN s.attempt_ts ELSE t.First_Failure_TS END,
        Last_Failure_TS      = CASE WHEN s.ok = 1 THEN t.Last_Failure_TS ELSE s.attempt_ts END,
        Last_Failure_Class   = CASE WHEN s.ok = 1 THEN t.Last_Failure_Class ELSE s.failure_class END,
        Last_Failure_Text    = CASE WHEN s.ok = 1 THEN t.Last_Failure_Text ELSE s.failure_text END,
        Updated_At           = @agora
    WHEN NOT MATCHED BY TARGET THEN INSERT
        (Instance, Environment, Last_Attempt_TS, Last_Success_TS, Read_Until_Server_TS, Rows_Read, Logs_Read,
         Consecutive_Failures, First_Failure_TS, Last_Failure_TS, Last_Failure_Class, Last_Failure_Text, Updated_At)
    VALUES
        (s.instance, @environment, s.attempt_ts,
         CASE WHEN s.ok = 1 THEN s.attempt_ts END, CASE WHEN s.ok = 1 THEN s.read_until_server_ts END,
         CASE WHEN s.ok = 1 THEN s.rows_read END, CASE WHEN s.ok = 1 THEN s.logs_read END,
         CASE WHEN s.ok = 1 THEN 0 ELSE 1 END, CASE WHEN s.ok = 0 THEN s.attempt_ts END,
         CASE WHEN s.ok = 0 THEN s.attempt_ts END, CASE WHEN s.ok = 0 THEN s.failure_class END,
         CASE WHEN s.ok = 0 THEN s.failure_text END, @agora);
    RETURN 0;
END;
GO

-- Leitura pelo portal (V3.4): sql_monitoring. Escrita: a identidade do servidor mestre do recolhedor.
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'sql_monitoring')
BEGIN
    GRANT SELECT ON dbo.WDB_ERRORLOG_READ_STATE TO sql_monitoring;
    PRINT '  [OK] GRANT SELECT em WDB_ERRORLOG_READ_STATE TO sql_monitoring';
END
GO
"""

MIGRATION_SQL = """-- ============================================================================
-- Migration 014: estado de leitura do errorlog por instancia (B2a-2a)
-- ----------------------------------------------------------------------------
-- Data: 2026-09-15 | Gate: watcherdb-v1-intel-specialist (GO com ajustes, incorporados)
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring, NUNCA utilizador de dominio) | Onde: servidor da Intelligence
--
-- CONTEXTO (medido a 15/09): 63 instancias no inventario, 40 com linhas na HIST em 7 dias. O recolhedor nao distinguia
-- "li e nao havia linhas" de "nao consegui ligar", e o heartbeat e global. Esta tabela guarda, por instancia, a ultima
-- tentativa, a ultima leitura boa, ate onde leu (relogio do servidor) e a serie de falhas em curso.
--
-- O QUE FAZ: cria WDB_ERRORLOG_READ_STATE e usp_errorlog_read_state_upsert; GRANT SELECT a sql_monitoring.
-- NAO MUDA: a leitura do errorlog, as STG/HIST, o arquivo, jobs. O fim deste ficheiro ensaia a procedure dentro de uma
-- transaccao com ROLLBACK (nao fica nada gravado).
-- ORDEM: correr ANTES de reiniciar o servico WatcherDBCollector com o codigo novo.
--
-- Idempotente. ROLLBACK: DROP PROCEDURE dbo.usp_errorlog_read_state_upsert; DROP TABLE dbo.WDB_ERRORLOG_READ_STATE
-- (o recolhedor so avisa e segue).
-- ============================================================================
USE [WatcherDB_Intelligence];
GO

""" + OBJETOS_SQL + """
-- Ensaio com ROLLBACK: falha, leitura boa, e uma tentativa atrasada que tem de ser ignorada
BEGIN TRAN;
EXEC dbo.usp_errorlog_read_state_upsert @environment = 'TST',
     @json = N'[{"instance":"B2A2A_ENSAIO_I01","ok":false,"attempt_ts":"2026-09-15T17:00:00","failure_class":"connect","failure_text":"ensaio"}]';
EXEC dbo.usp_errorlog_read_state_upsert @environment = 'TST',
     @json = N'[{"instance":"B2A2A_ENSAIO_I01","ok":true,"attempt_ts":"2026-09-15T17:05:00","read_until_server_ts":"2026-09-15T17:05:02","rows_read":3,"logs_read":1}]';
EXEC dbo.usp_errorlog_read_state_upsert @environment = 'TST',
     @json = N'[{"instance":"B2A2A_ENSAIO_I01","ok":false,"attempt_ts":"2026-09-15T16:00:00","failure_class":"other","failure_text":"atrasada"}]';
-- Esperado 1 linha: Consecutive_Failures 0, Last_Success_TS 17:05, Read_Until 17:05:02, Rows_Read 3,
-- First_Failure_TS NULL, Last_Failure_TS 17:00, Last_Failure_Class connect
SELECT Instance, Consecutive_Failures, Last_Success_TS, Read_Until_Server_TS, Rows_Read, First_Failure_TS,
       Last_Failure_TS, Last_Failure_Class
FROM dbo.WDB_ERRORLOG_READ_STATE WHERE Instance = 'B2A2A_ENSAIO_I01';
ROLLBACK;
GO

-- Verificacao: esperado 0 linhas depois do ROLLBACK e os dois objectos presentes
SELECT COUNT(*) AS linhas_ensaio_depois_do_rollback FROM dbo.WDB_ERRORLOG_READ_STATE WHERE Instance = 'B2A2A_ENSAIO_I01';
SELECT name, type_desc FROM sys.objects
WHERE name IN ('WDB_ERRORLOG_READ_STATE', 'usp_errorlog_read_state_upsert');
GO
"""

CANONICAL_SECTION = """
-- ============================================================================
-- SECAO 38: ESTADO DE LEITURA DO ERRORLOG POR INSTANCIA (B2a-2a, 2026-09-15)
-- ============================================================================
-- Uma linha por instancia: ultima tentativa, ultima leitura boa, ate onde leu (relogio do servidor) e serie de falhas.
-- Escrita pelo recolhedor do errorlog em todo o ciclo (fora do applock do store); leitura pelo portal (sql_monitoring).
-- Forma das tabelas de estado da SECAO 19. Migration 014.
-- ============================================================================
PRINT '';
PRINT '----------------------------------------';
PRINT 'SECAO 38: ESTADO DE LEITURA DO ERRORLOG POR INSTANCIA';
PRINT '----------------------------------------';
GO

""" + OBJETOS_SQL + """
PRINT '  [OK] Estado de leitura do errorlog por instancia (SECAO 38)';
GO
"""

# ---------------------------------------------------------------- recolhedor
HELPERS_PY = '''_PWD_RE = re.compile(r"(PWD|Password)\\s*=\\s*[^;]*", re.IGNORECASE)


def _sanear(erro, limite=400):
    """B2a-2a 2026-09-15 (guardiao): mensagem de erro sem segredos, cortada. O driver ODBC pode ecoar a connection string
    (que leva PWD=) e o texto passa a ficar numa tabela lida pelo portal."""
    return _PWD_RE.sub(lambda m: m.group(1) + "=***", str(erro))[:limite]


def _classe_falha(erro):
    """B2a-2a: classe da falha a partir do SQLSTATE do pyodbc (args[0]) e do texto."""
    estado = erro.args[0] if getattr(erro, "args", None) and isinstance(erro.args[0], str) else ""
    texto = str(erro)
    if estado == "28000" or "Login failed" in texto:
        return "login_failed"
    if estado == "HYT00" or "Query timeout" in texto:
        return "query_timeout"
    if estado.startswith("08") or "TCP Provider" in texto or "Error Locating Server" in texto:
        return "connect"
    if estado == "42000" and "permission" in texto.lower():
        return "permission"
    return "other"


'''

ESTADO_METODOS = '''    def _marcar(self, server_id, tentativa, ok, ate=None, linhas=None, logs=None, erro=None):
        """B2a-2a 2026-09-15: estado de leitura desta instancia neste ciclo (corre nas threads do ThreadPoolExecutor)."""
        estado = {"instance": server_id, "ok": bool(ok), "attempt_ts": tentativa.isoformat()}
        if ok:
            estado.update(read_until_server_ts=ate.isoformat() if hasattr(ate, "isoformat") else None,
                          rows_read=int(linhas or 0), logs_read=int(logs or 1))
        else:
            estado.update(failure_class=_classe_falha(erro), failure_text=_sanear(erro))
        with self._estados_lock:
            self.__dict__.setdefault("_estados", {})[server_id] = estado

    def leu_alguma_instancia(self):
        """B2a-2a: pelo menos uma leitura boa neste ciclo (condicao do heartbeat no ciclo sem linhas)."""
        return any(e.get("ok") for e in self.__dict__.get("_estados", {}).values())

    def registar_estado(self, environment):
        """B2a-2a 2026-09-15: grava o estado de leitura por instancia (dbo.usp_errorlog_read_state_upsert, migration 014).

        Em todo o ciclo, com ou sem linhas, antes do store e fora do applock do store (gate do guardiao): a tentativa fica
        registada mesmo que o store falhe. Try proprio: falhar o estado nao falha o KPI. Devolve o numero de instancias
        enviadas, ou None.
        """
        estados = list(self.__dict__.get("_estados", {}).values())
        if not estados:
            return None
        conn = None
        try:
            conn = pyodbc.connect(self._build_master_conn_str(), autocommit=True, timeout=15)
            conn.cursor().execute(
                "SET NOCOUNT ON; EXEC dbo.usp_errorlog_read_state_upsert @environment = ?, @json = ?;",
                (environment.upper(), json.dumps(estados)),
            )
            falhas = sum(1 for e in estados if not e["ok"])
            self.logger.info(f"Estado de leitura: {len(estados) - falhas} instancias lidas, {falhas} com falha")
            return len(estados)
        except Exception as e:
            self.logger.warning(f"Estado de leitura por instancia falhou (o KPI segue): {_sanear(e, 1000)}")
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

'''

COLLECTOR_EDITS = [
    ("import logging\nimport pyodbc\n", "import json\nimport logging\nimport re\nimport threading\nimport pyodbc\n"),
    ("class ErrorLogCollector:\n", HELPERS_PY + "class ErrorLogCollector:\n"),
    ("    WINDOW_MINUTES = 65\n    QUERY_TIMEOUT = 60\n",
     "    WINDOW_MINUTES = 65\n    QUERY_TIMEOUT = 60\n"
     "    # B2a-2a 2026-09-15: estado de leitura por instancia, escrito pelas threads de collect_from_server\n"
     "    _estados_lock = threading.Lock()\n"),
    ('                        self.logger.warning(f"{server_id}: log anterior nao lido na janela ({e}); fica o actual")\n',
     '                        self.logger.warning(f"{server_id}: log anterior nao lido na janela ({_sanear(e, 1000)}); fica o actual")\n'),
    ('                self.logger.warning(\n                    f"Falha decrypt password de {server_config.server_id}: {e}"\n                )\n',
     '                self.logger.warning(\n                    f"Falha decrypt password de {server_config.server_id}: {_sanear(e, 1000)}"\n                )\n'),
    ("        server_id = server_config.server_id\n\n        try:\n",
     "        server_id = server_config.server_id\n"
     "        tentativa = datetime.now()     # B2a-2a: relogio do recolhedor para o estado por instancia\n"
     "        leu_anterior = False\n\n        try:\n"),
    ("                        anterior = self._read_window(conn.cursor(), 1, desde, ate)\n",
     "                        anterior = self._read_window(conn.cursor(), 1, desde, ate)\n"
     "                        leu_anterior = True\n"),
    ("            return data\n\n        except Exception as e:\n",
     "            self._marcar(server_id, tentativa, ok=True, ate=ate, linhas=len(data), logs=2 if leu_anterior else 1)\n"
     "            return data\n\n        except Exception as e:\n"),
    ('            self.logger.warning(f"Erro ao coletar de {server_id}: {e}")\n            return []\n',
     '            self._marcar(server_id, tentativa, ok=False, erro=e)\n'
     '            self.logger.warning(f"Erro ao coletar de {server_id}: {_sanear(e, 1000)}")\n            return []\n'),
    ('    def collect_all(self, environment):\n        """Coleta de todos os servidores em paralelo"""\n',
     ESTADO_METODOS +
     '    def collect_all(self, environment):\n        """Coleta de todos os servidores em paralelo"""\n'
     '        self._estados = {}     # B2a-2a: estado de leitura deste ciclo, por instancia\n'),
    ('                    self.logger.warning(f"Erro em {server.server_id}: {e}")\n',
     '                    self.logger.warning(f"Erro em {server.server_id}: {_sanear(e, 1000)}")\n'),
    ('            self.logger.warning(f"Heartbeat falhou (WDB_COLLECTION_SCHEDULE_META): {e}")\n',
     '            self.logger.warning(f"Heartbeat falhou (WDB_COLLECTION_SCHEDULE_META): {_sanear(e, 1000)}")\n'),
    ('            self.logger.warning(f"Arquivo de eventos falhou (o KPI segue): {e}")\n',
     '            self.logger.warning(f"Arquivo de eventos falhou (o KPI segue): {_sanear(e, 1000)}")\n'),
    ('            self.logger.error(f"Erro ao armazenar dados: {e}")\n',
     '            self.logger.error(f"Erro ao armazenar dados: {_sanear(e, 1000)}")\n'),
    ("        df = self.collect_all(args.environment)\n\n        if not df.empty:\n"
     "            self.store_data(df, args.environment)\n        else:\n"
     '            self.logger.info("Nenhum evento a guardar nos ultimos 65 minutos")\n',
     "        df = self.collect_all(args.environment)\n"
     "        # B2a-2a 2026-09-15: estado por instancia em todo o ciclo, antes do store e fora do applock (guardiao)\n"
     "        self.registar_estado(args.environment)\n\n        if not df.empty:\n"
     "            self.store_data(df, args.environment)\n        else:\n"
     '            self.logger.info("Nenhum evento a guardar nos ultimos 65 minutos")\n'
     "            # B2a-2a: ciclo sem linhas tambem e vida, mas so com pelo menos uma instancia lida\n"
     "            if self.leu_alguma_instancia():\n"
     "                self._heartbeat(self._build_master_conn_str())\n"),
]

ADAPTER_EDITS = [
    ("    from scripts.collectors.collect_errorlog import ErrorLogCollector\nexcept ImportError as e:\n"
     '    logging.error(f"Failed to import ErrorLogCollector: {e}")\n    ErrorLogCollector = None\n',
     "    from scripts.collectors.collect_errorlog import ErrorLogCollector, _sanear\nexcept ImportError as e:\n"
     '    logging.error(f"Failed to import ErrorLogCollector: {e}")\n    ErrorLogCollector = None\n    _sanear = None\n'),
    ("            df = collector.collect_all(environment)\n\n            if df.empty:\n"
     '                self.logger.info("No errors found in SQL Server error logs")\n',
     "            df = collector.collect_all(environment)\n\n"
     "            # B2a-2a 2026-09-15: estado de leitura por instancia em TODO o ciclo, antes do store e fora do applock\n"
     "            collector.registar_estado(environment)\n\n            if df.empty:\n"
     '                self.logger.info("No errors found in SQL Server error logs")\n'
     "                # B2a-2a (guardiao): o heartbeat do ciclo sem linhas nunca corria neste caminho, que e o do servico\n"
     "                # (so dentro do store_data). So com pelo menos uma instancia lida: um ciclo cego nao parece fresco.\n"
     "                if collector.leu_alguma_instancia():\n"
     "                    collector._heartbeat(collector._build_master_conn_str())\n"),
    ('            self.logger.error(f"Collection failed: {e}", exc_info=True)\n'
     "            return {'success': False, 'rows_collected': 0, 'error': str(e), 'metadata': {'environment': environment}}\n",
     "            # B2a-2a: mensagem saneada (sem PWD) e sem traceback, que repetiria a mensagem por sanear\n"
     "            erro = _sanear(e, 1000) if _sanear else type(e).__name__\n"
     '            self.logger.error(f"Collection failed: {erro}")\n'
     "            return {'success': False, 'rows_collected': 0, 'error': erro, 'metadata': {'environment': environment}}\n"),
]

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Alterado — B2a-2a: estado de leitura do errorlog por instancia (migration 014)\n\n"
                  "- Tabela nova `WDB_ERRORLOG_READ_STATE` e `usp_errorlog_read_state_upsert` (seccao 38 do canonico): por instancia,\n"
                  "  ultima tentativa, ultima leitura boa, ate onde leu no relogio do servidor, linhas e serie de falhas com classe e\n"
                  "  texto saneado. O recolhedor grava-a em todo o ciclo, antes do store e fora do applock.\n"
                  "- O heartbeat do ciclo sem linhas passa a ser escrito no caminho do servico (antes so dentro do store_data),\n"
                  "  e so quando pelo menos uma instancia foi lida.\n"
                  "- Mensagens de erro do recolhedor do errorlog sem `PWD=` nos logs e na tabela. Gate do guardiao: GO com ajustes.\n\n")

TEST_SRC = r'''"""
B2a-2a (2026-09-15): estado de leitura do errorlog por instancia, heartbeat do ciclo vazio e mensagens saneadas.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

import scripts.collectors.collect_errorlog as mod

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
AGORA = datetime(2026, 9, 15, 17, 0, 0)


class Cur:
    def __init__(self, conn):
        self.conn, self.description, self._rows = conn, None, []

    def execute(self, sql, params=()):
        self.conn.chamadas.append((sql, params))
        if sql.startswith("SELECT GETDATE()"):
            self._rows, self.description = [(AGORA,)], [("x",)]
        elif "xp_readerrorlog" in sql:
            rows = self.conn.logs.get(int(sql.split("xp_readerrorlog")[1].split(",")[0]), [])
            self._rows, self.description = rows, ([("LogDate",)] if rows else None)
        elif "usp_errorlog_read_state_upsert" in sql and self.conn.falha_upsert:
            raise RuntimeError("Could not find stored procedure 'dbo.usp_errorlog_read_state_upsert'. PWD=segredo;")

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)


class Conn:
    def __init__(self, logs=None, falha_upsert=False):
        self.logs, self.falha_upsert, self.chamadas, self.timeout, self.fechada = logs or {}, falha_upsert, [], 0, False

    def cursor(self):
        return Cur(self)

    def close(self):
        self.fechada = True


class Log:
    def __init__(self):
        self.linhas = []

    def __getattr__(self, nivel):
        return lambda m, *a, **k: self.linhas.append((nivel, m))


def coletor(monkeypatch, conn):
    c = object.__new__(mod.ErrorLogCollector)
    c.logger = Log()
    c.get_connection_string = lambda cfg: "DRIVER=x"
    c._build_master_conn_str = lambda: "DRIVER=x;UID=u;PWD=segredo;"
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: conn)
    return c


cfg = lambda sid: type("Cfg", (), {"server_id": sid})()


def test_sanear_tira_a_password_e_corta():
    e = RuntimeError("('08001', 'falhou DRIVER={ODBC};SERVER=x;UID=sql_monitoring;PWD=Ab;c1;TrustServerCertificate=yes')")
    s = mod._sanear(e)
    assert "Ab" not in s and "PWD=***" in s and "UID=sql_monitoring" in s
    assert "password=***" in mod._sanear("Password = x y z;resto").lower()
    assert len(mod._sanear("a" * 5000)) == 400


def test_classe_da_falha():
    assert mod._classe_falha(Exception("08001", "[08001] TCP Provider: The wait operation timed out.")) == "connect"
    assert mod._classe_falha(Exception("28000", "Login failed for user 'sql_monitoring'.")) == "login_failed"
    assert mod._classe_falha(Exception("HYT00", "Query timeout expired")) == "query_timeout"
    assert mod._classe_falha(Exception("42000", "The EXECUTE permission was denied on the object 'xp_readerrorlog'")) == "permission"
    assert mod._classe_falha(RuntimeError("outra coisa")) == "other"


def test_leitura_boa_e_falha_ficam_no_estado(monkeypatch):
    conn = Conn({0: [(datetime(2026, 9, 15, 16, 50), "spid9", "Error: 824, Severity: 24, State: 2."),
                     (datetime(2026, 9, 15, 16, 50), "spid9", "SQL Server detected a logical consistency-based I/O error.")]})
    c = coletor(monkeypatch, conn)
    c._estados = {}
    assert len(c.collect_from_server(cfg("BOA_I01"))) == 1
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: (_ for _ in ()).throw(
        Exception("08001", "TCP Provider: timed out. DRIVER=x;PWD=segredo;")))
    assert c.collect_from_server(cfg("MA_I01")) == []
    boa, ma = c._estados["BOA_I01"], c._estados["MA_I01"]
    assert boa["ok"] is True and boa["read_until_server_ts"] == "2026-09-15T17:00:00" and boa["rows_read"] == 1 and boa["logs_read"] == 1
    assert ma["ok"] is False and ma["failure_class"] == "connect" and "segredo" not in ma["failure_text"]
    assert not any("segredo" in m for _, m in c.logger.linhas)
    assert c.leu_alguma_instancia() is True


def test_nenhum_log_do_recolhedor_leva_excepcao_por_sanear():
    fonte = (ROOT / "scripts" / "collectors" / "collect_errorlog.py").read_text(encoding="utf-8")
    crus = [l.strip() for l in fonte.splitlines() if "logger." in l and re.search(r"\{e\}", l)]
    assert crus == [], crus


def test_registar_estado_envia_um_json_por_ciclo(monkeypatch):
    conn = Conn()
    c = coletor(monkeypatch, conn)
    assert c.registar_estado("PRD") is None and conn.chamadas == [], "sem estados nao liga"
    c._estados = {"A_I01": {"instance": "A_I01", "ok": True, "attempt_ts": "2026-09-15T17:00:00"},
                  "B_I01": {"instance": "B_I01", "ok": False, "attempt_ts": "2026-09-15T17:00:01", "failure_class": "connect"}}
    assert c.registar_estado("prd") == 2
    (sql, params), = conn.chamadas
    assert "EXEC dbo.usp_errorlog_read_state_upsert @environment = ?, @json = ?" in sql
    assert params[0] == "PRD" and [e["instance"] for e in json.loads(params[1])] == ["A_I01", "B_I01"]
    assert conn.fechada


def test_sem_migration_o_kpi_segue_e_nao_vaza(monkeypatch):
    c = coletor(monkeypatch, Conn(falha_upsert=True))
    c._estados = {"A_I01": {"instance": "A_I01", "ok": True, "attempt_ts": "2026-09-15T17:00:00"}}
    assert c.registar_estado("PRD") is None
    nivel, msg = c.logger.linhas[-1]
    assert nivel == "warning" and "Estado de leitura por instancia falhou (o KPI segue)" in msg and "segredo" not in msg


def _adapter(monkeypatch, df_vazio, leu):
    from services.collector_service.collectors import collect_errorlog as ad
    ordem = []

    class Falso:
        def collect_all(self, env):
            ordem.append("collect_all")
            return mod.pd.DataFrame() if df_vazio else mod.pd.DataFrame([{"x": 1}])

        def registar_estado(self, env):
            ordem.append("estado")

        def leu_alguma_instancia(self):
            return leu

        def _build_master_conn_str(self):
            return "DRIVER=x"

        def _heartbeat(self, cs):
            ordem.append("heartbeat")

        def store_data(self, df, env):
            ordem.append("store")

    monkeypatch.setattr(ad, "ErrorLogCollector", Falso)
    a = object.__new__(ad.CollectErrorLogPRD)
    a.logger = Log()
    return a._execute_collection("PRD"), ordem


def test_servico_regista_estado_e_heartbeat_do_ciclo_vazio(monkeypatch):
    r, ordem = _adapter(monkeypatch, df_vazio=True, leu=True)
    assert r["success"] is True and ordem == ["collect_all", "estado", "heartbeat"]
    _, ordem = _adapter(monkeypatch, df_vazio=True, leu=False)
    assert ordem == ["collect_all", "estado"], "ciclo cego nao escreve heartbeat"
    _, ordem = _adapter(monkeypatch, df_vazio=False, leu=True)
    assert ordem == ["collect_all", "estado", "store"]


def test_migration_014_e_canonico_alinhados():
    mig = (ROOT / "database" / "migrations" / "014_errorlog_estado_leitura_por_instancia.sql").read_text(encoding="utf-8")
    can = (ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql").read_text(encoding="utf-8", errors="replace")
    for txt in (mig, can):
        assert "CREATE TABLE dbo.WDB_ERRORLOG_READ_STATE" in txt
        assert "MERGE dbo.WDB_ERRORLOG_READ_STATE WITH (HOLDLOCK) AS t" in txt
        assert "WHEN MATCHED AND s.attempt_ts >= t.Last_Attempt_TS THEN UPDATE SET" in txt
        assert "ISJSON(@json) <> 1" in txt and "GRANT SELECT ON dbo.WDB_ERRORLOG_READ_STATE TO sql_monitoring" in txt
    assert "BEGIN TRAN;" in mig and "ROLLBACK;" in mig and not re.search(r"\bCOMMIT\b", mig)
    assert "DROP TABLE" not in mig.split("-- ====", 2)[2] and "TRUNCATE" not in mig
    assert "SECAO 38: ESTADO DE LEITURA DO ERRORLOG POR INSTANCIA" in can
'''


def _eol(t):
    return "\r\n" if "\r\n" in t else "\n"


def _edit(text, edits, label):
    eol = _eol(text)
    for old, new in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != 1:
            raise SystemExit(f"[ABORT] {label}: ancora esperada 1x, encontrada {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or V1
    src = {k: base / p for k, p in REL.items()}
    if src["migration"].exists() or src["test"].exists():
        print("[ABORT] ja aplicado"); return 1
    can = src["canonical"].read_bytes().decode("utf-8")
    if MARK in can:
        print("[ABORT] canonico ja tem a tabela"); return 1
    cauda = can.replace("\r\n", "\n").rstrip()
    if not cauda.endswith("GO") or "(SECAO 37)" not in cauda[-200:]:
        print("[ABORT] o canonico nao termina na seccao 37 como medido -- nada escrito"); return 1
    col = _edit(src["collector"].read_bytes().decode("utf-8"), COLLECTOR_EDITS, "recolhedor")
    ada = _edit(src["adapter"].read_bytes().decode("utf-8"), ADAPTER_EDITS, "adapter")
    ceol = _eol(can)
    can_novo = can + ("" if can.endswith(("\n", "\r\n")) else ceol) + CANONICAL_SECTION.replace("\n", ceol)
    chg = _edit(src["changelog"].read_bytes().decode("utf-8"), [(CHANGELOG_ANCORA, CHANGELOG_NOVO)], "changelog")
    compile(col, str(REL["collector"]), "exec")
    compile(ada, str(REL["adapter"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] recolhedor {len(COLLECTOR_EDITS)} blocos e adapter {len(ADAPTER_EDITS)} (compilam); migration 014; "
          f"canonico seccao 38; teste; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["collector"].write_bytes(col.encode("utf-8")); print(f"[write] {REL['collector']}")
    src["adapter"].write_bytes(ada.encode("utf-8")); print(f"[write] {REL['adapter']}")
    src["migration"].write_bytes(MIGRATION_SQL.replace("\n", "\r\n").encode("utf-8")); print(f"[new]   {REL['migration']}")
    src["canonical"].write_bytes(can_novo.encode("utf-8")); print(f"[write] {REL['canonical']}")
    src["changelog"].write_bytes(chg.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Testes; migration 014 no SSMS com a CONTA DE DEPLOY; SO DEPOIS Restart-Service WatcherDBCollector.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
