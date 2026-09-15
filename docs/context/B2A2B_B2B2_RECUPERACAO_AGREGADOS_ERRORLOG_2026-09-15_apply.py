# -*- coding: utf-8 -*-
"""B2a-2b + B2b-2 (2026-09-15) -- recuperar a janela perdida do errorlog e agregados horarios com retencao de 13 meses.

Desenho: docs/context/B2A2B_B2B2_DESENHO_ERRORLOG_2026-09-15.md (V3.4). Gate do guardiao do recolhedor: consenso com
ajustes nos dois, todos incorporados:
  B2a-2b  (d) tecto de 10 instancias em recuperacao por ciclo: as outras leem a janela normal e mantem a marca antiga,
              para recuperarem num ciclo seguinte (nunca se perde o intervalo por causa do tecto).
          Sem migration; arquivo passa a @days_to_archive = 2 (borda dos 24 h).
  B2b-2   (a) Sample_Text sempre NULL em Security (login e IP): no recolhedor e numa CHECK da tabela.
          (b) agregados so de Security e Repetitive (AG e Critical ja vao linha a linha para a HIST; sem dupla contagem).
          (c) usp_purge_kpi_history recalcula o tempo que sobra DEPOIS da purga da HIST, antes da dos agregados.
          Chamada separada do estado de leitura, try proprio, fora do applock do store.

Medido a 15/09 (sql_monitoring): STG com 10.589 Repetitive e 8.776 Security contra 220 eventos (99% do volume nao entra
na parte recuperada); ~158 grupos horarios por ciclo; WDB_ERRORLOG_READ_STATE com PRD 42 e QA 15 instancias.

O que muda:
  V1 scripts/collectors/collect_errorlog.py  marcas por ambiente e plano de recuperacao; janela desde a marca; so eventos
                                             na parte recuperada; agregados por instancia; registar_agregados(); arquivo 2 dias.
  V1 services/collector_service/collectors/collect_errorlog.py  registar_agregados no caminho do servico.
  V1 database/migrations/015_errorlog_agregados_horarios.sql  tabela, merge, camada AGREGADOS, purge proprio, chamada
                                             na purga generica, GRANT, ensaios (ROLLBACK e @dry_run = 1).
  V1 database/INSTALACAO_COMPLETA_UNIFICADA.sql  seccao 39 e chamada nova no fim de usp_purge_kpi_history.
  V1 tests/unit/test_collect_errorlog_b2a2b_b2b2.py (novo); tests/unit/test_collect_errorlog_b2a2a.py (adapter: +agregados)
  V1 docs/CHANGELOG.md

Ordem: migration 015 ANTES de reiniciar o WatcherDBCollector (sem ela, a recuperacao funciona e os agregados so avisam).

Uso (raiz do repo V3.4):
  py docs/context/B2A2B_B2B2_RECUPERACAO_AGREGADOS_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B2A2B_B2B2_RECUPERACAO_AGREGADOS_ERRORLOG_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_collect_errorlog_b2a2b_b2b2.py tests/unit/test_collect_errorlog_b2a2a.py tests/unit/test_collect_errorlog_b1b.py tests/unit/test_collect_errorlog_b2a1.py tests/unit/test_collect_errorlog_hotfix_nan.py tests/unit/test_collect_errorlog_perf.py tests/unit/test_errorlog_retencao_b2b1.py -q -p no:cacheprovider
  SSMS, servidor da Intelligence, CONTA DE DEPLOY: database/migrations/015_errorlog_agregados_horarios.sql
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
    "migration": Path("database/migrations/015_errorlog_agregados_horarios.sql"),
    "canonical": Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"),
    "test": Path("tests/unit/test_collect_errorlog_b2a2b_b2b2.py"),
    "test_b2a2a": Path("tests/unit/test_collect_errorlog_b2a2a.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "KPI_MSSQL_ERRORLOG_AGG_HIST"

# ---------------------------------------------------------------- SQL
OBJETOS_SQL = """IF OBJECT_ID('dbo.WDB_RETENTION_POLICY', 'U') IS NULL OR OBJECT_ID('dbo.WDB_LEGAL_HOLD', 'U') IS NULL
    RAISERROR('B2b-2: falta a migration 013 (WDB_RETENTION_POLICY e WDB_LEGAL_HOLD). Corra-a primeiro.', 16, 1);
GO

IF OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_AGG_HIST', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_ERRORLOG_AGG_HIST (
        Instance        VARCHAR(128)   NOT NULL,
        Hour_TS         DATETIME2(0)   NOT NULL,   -- hora do servidor, truncada
        Log_Type        VARCHAR(32)    NOT NULL,   -- so Security e Repetitive (AG e Critical ficam linha a linha na HIST)
        Category        VARCHAR(64)    NOT NULL,   -- do classificador
        Error_Number    INT            NOT NULL,   -- 0 quando nao ha
        State           INT            NOT NULL,   -- motivo do login em Security; -1 nos outros
        Severity        INT            NULL,
        Occurrences     INT            NOT NULL,   -- MAX das leituras sobrepostas; numa hora partida por falha e um minimo
        First_Log_Date  DATETIME2      NOT NULL,
        Last_Log_Date   DATETIME2      NOT NULL,
        Sample_Text     NVARCHAR(400)  NULL,       -- NULL em Security (login e IP)
        Updated_At      DATETIME2      NOT NULL CONSTRAINT DF_ELAGG_UPD DEFAULT GETDATE(),
        CONSTRAINT PK_KPI_MSSQL_ERRORLOG_AGG_HIST PRIMARY KEY CLUSTERED (Instance, Hour_TS, Log_Type, Category, Error_Number, State),
        CONSTRAINT CK_ELAGG_TIPO CHECK (Log_Type IN ('Security', 'Repetitive')),
        CONSTRAINT CK_ELAGG_SEM_TEXTO_PESSOAL CHECK (Log_Type <> 'Security' OR Sample_Text IS NULL)
    ) ON [FG_KPI_HIST];
    CREATE NONCLUSTERED INDEX IX_ELAGG_Hour ON dbo.KPI_MSSQL_ERRORLOG_AGG_HIST (Hour_TS) ON [FG_KPI_HIST];
    PRINT '  [OK] Tabela KPI_MSSQL_ERRORLOG_AGG_HIST criada';
END
ELSE
    PRINT '  [INFO] Tabela KPI_MSSQL_ERRORLOG_AGG_HIST ja existe';
GO

CREATE OR ALTER PROCEDURE dbo.usp_errorlog_agg_merge
    @environment VARCHAR(8), @json NVARCHAR(MAX)
AS
BEGIN
    -- B2b-2 2026-09-15: um MERGE por ciclo do recolhedor. As janelas lidas sobrepoem-se (65 min a cada 5 min): a contagem
    -- de uma hora e o MAX das leituras, o primeiro e o ultimo sao MIN e MAX. So Security e Repetitive; texto de exemplo
    -- nunca em Security. @environment e informativo (a chave inclui a instancia).
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @json IS NULL OR ISJSON(@json) <> 1
    BEGIN
        RAISERROR('usp_errorlog_agg_merge: @json invalido. Nada gravado.', 16, 1);
        RETURN 1;
    END;
    DECLARE @agora DATETIME2 = GETDATE();

    MERGE dbo.KPI_MSSQL_ERRORLOG_AGG_HIST WITH (HOLDLOCK) AS t
    USING (
        SELECT j.instance, j.hour_ts, j.log_type, j.category, ISNULL(j.error_number, 0) AS error_number,
               CASE WHEN j.log_type = 'Security' THEN ISNULL(j.state, -1) ELSE -1 END AS state,
               MAX(j.severity) AS severity, MAX(j.occurrences) AS occurrences,
               MIN(j.first_log_date) AS first_log_date, MAX(j.last_log_date) AS last_log_date,
               CASE WHEN j.log_type = 'Security' THEN NULL ELSE MAX(LEFT(j.sample_text, 400)) END AS sample_text
        FROM OPENJSON(@json) WITH (
            instance        VARCHAR(128)   '$.instance',
            hour_ts         DATETIME2(0)   '$.hour_ts',
            log_type        VARCHAR(32)    '$.log_type',
            category        VARCHAR(64)    '$.category',
            error_number    INT            '$.error_number',
            state           INT            '$.state',
            severity        INT            '$.severity',
            occurrences     INT            '$.occurrences',
            first_log_date  DATETIME2      '$.first_log_date',
            last_log_date   DATETIME2      '$.last_log_date',
            sample_text     NVARCHAR(4000) '$.sample_text'
        ) j
        WHERE j.instance IS NOT NULL AND j.hour_ts IS NOT NULL AND j.category IS NOT NULL
          AND j.log_type IN ('Security', 'Repetitive') AND j.occurrences > 0
          AND j.first_log_date IS NOT NULL AND j.last_log_date IS NOT NULL
        GROUP BY j.instance, j.hour_ts, j.log_type, j.category, ISNULL(j.error_number, 0),
                 CASE WHEN j.log_type = 'Security' THEN ISNULL(j.state, -1) ELSE -1 END
    ) AS s
    ON t.Instance = s.instance AND t.Hour_TS = s.hour_ts AND t.Log_Type = s.log_type AND t.Category = s.category
       AND t.Error_Number = s.error_number AND t.State = s.state
    WHEN MATCHED THEN UPDATE SET
        Occurrences    = CASE WHEN s.occurrences > t.Occurrences THEN s.occurrences ELSE t.Occurrences END,
        First_Log_Date = CASE WHEN s.first_log_date < t.First_Log_Date THEN s.first_log_date ELSE t.First_Log_Date END,
        Last_Log_Date  = CASE WHEN s.last_log_date > t.Last_Log_Date THEN s.last_log_date ELSE t.Last_Log_Date END,
        Severity       = ISNULL(t.Severity, s.severity),
        Sample_Text    = CASE WHEN t.Log_Type = 'Security' THEN NULL ELSE ISNULL(t.Sample_Text, s.sample_text) END,
        Updated_At     = @agora
    WHEN NOT MATCHED BY TARGET THEN INSERT
        (Instance, Hour_TS, Log_Type, Category, Error_Number, State, Severity, Occurrences,
         First_Log_Date, Last_Log_Date, Sample_Text, Updated_At)
    VALUES
        (s.instance, s.hour_ts, s.log_type, s.category, s.error_number, s.state, s.severity, s.occurrences,
         s.first_log_date, s.last_log_date, s.sample_text, @agora);
    RETURN 0;
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.WDB_RETENTION_POLICY WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_AGG_HIST' AND Tier = 'AGREGADOS')
    INSERT INTO dbo.WDB_RETENTION_POLICY (Table_Name, Tier, Retention_Days, Min_Days, Max_Days, Legal_Basis)
    VALUES ('KPI_MSSQL_ERRORLOG_AGG_HIST', 'AGREGADOS', 395, 365, 1095,
            N'Agregados horarios de Security e Repetitive, sem texto pessoal. Comparacao ano a ano (13 meses). Decisao 2026-09-15.');
GO

CREATE OR ALTER PROCEDURE dbo.usp_purge_errorlog_agg
    @dry_run BIT = 1, @batch_size INT = 20000, @max_minutes INT = 20
AS
BEGIN
    -- B2b-2 2026-09-15: expurgo dos agregados horarios do errorlog pela camada AGREGADOS (WDB_RETENTION_POLICY), corte
    -- sobre Hour_TS, legal hold por instancia (holds da HIST ou dos agregados) e registo em WDB_MAINTENANCE_LOG.
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2 = GETDATE(), @dias INT, @corte DATETIME2, @apagadas BIGINT = 0, @lote INT, @holds INT;

    IF OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_AGG_HIST', 'U') IS NULL
    BEGIN
        PRINT '[SKIP] KPI_MSSQL_ERRORLOG_AGG_HIST';
        RETURN 0;
    END;
    SELECT @dias = Retention_Days FROM dbo.WDB_RETENTION_POLICY
    WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_AGG_HIST' AND Tier = 'AGREGADOS';
    IF @dias IS NULL
    BEGIN
        RAISERROR('usp_purge_errorlog_agg: politica AGREGADOS em falta em WDB_RETENTION_POLICY. Nada apagado.', 16, 1);
        RETURN 1;
    END;
    SET @corte = DATEADD(DAY, -@dias, GETDATE());
    SELECT @holds = COUNT(*) FROM dbo.WDB_LEGAL_HOLD
    WHERE Table_Name IN ('KPI_MSSQL_ERRORLOG_HIST', 'KPI_MSSQL_ERRORLOG_AGG_HIST') AND Released_At IS NULL;

    IF @dry_run = 1
        SELECT @apagadas = COUNT_BIG(*) FROM dbo.KPI_MSSQL_ERRORLOG_AGG_HIST a WITH (NOLOCK)
        WHERE a.Hour_TS < @corte
          AND NOT EXISTS (SELECT 1 FROM dbo.WDB_LEGAL_HOLD lh
                          WHERE lh.Table_Name IN ('KPI_MSSQL_ERRORLOG_HIST', 'KPI_MSSQL_ERRORLOG_AGG_HIST')
                            AND lh.Released_At IS NULL AND lh.Instance = a.Instance);
    ELSE
    BEGIN
        SET @lote = 1;
        WHILE @lote > 0
        BEGIN
            IF DATEDIFF(MINUTE, @inicio, GETDATE()) >= @max_minutes BEGIN PRINT '[TIMEBOX] camada AGREGADOS'; BREAK; END;
            DELETE TOP (@batch_size) a FROM dbo.KPI_MSSQL_ERRORLOG_AGG_HIST a
            WHERE a.Hour_TS < @corte
              AND NOT EXISTS (SELECT 1 FROM dbo.WDB_LEGAL_HOLD lh
                              WHERE lh.Table_Name IN ('KPI_MSSQL_ERRORLOG_HIST', 'KPI_MSSQL_ERRORLOG_AGG_HIST')
                                AND lh.Released_At IS NULL AND lh.Instance = a.Instance);
            SET @lote = @@ROWCOUNT; SET @apagadas = @apagadas + @lote;
        END;
    END;
    PRINT CONCAT('[', CASE WHEN @dry_run = 1 THEN 'DRY' ELSE 'PURGE' END, '] ERRORLOG_AGG_HIST camada AGREGADOS: ', @apagadas);
    INSERT INTO dbo.WDB_MAINTENANCE_LOG (Run_Start, Object_Name, Index_Name, Action_Taken, Page_Count, Duration_Ms)
    VALUES (@inicio, 'KPI_MSSQL_ERRORLOG_AGG_HIST',
            CONCAT('camada=AGREGADOS;dias=', @dias, ';corte=', CONVERT(VARCHAR(19), @corte, 126), ';holds=', @holds),
            CASE WHEN @dry_run = 1 THEN 'PURGE_DRY' ELSE 'PURGE' END, @apagadas, DATEDIFF(MILLISECOND, @inicio, GETDATE()));
    RETURN 0;
END;
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'sql_monitoring')
BEGIN
    GRANT SELECT ON dbo.KPI_MSSQL_ERRORLOG_AGG_HIST TO sql_monitoring;
    PRINT '  [OK] GRANT SELECT em KPI_MSSQL_ERRORLOG_AGG_HIST TO sql_monitoring';
END
GO
"""

# chamada nova no fim da purga generica (canonico; a migration leva a procedure inteira ja editada)
GEN_FIM_OLD = ("        PRINT '[AVISO] usp_purge_errorlog_hist nao existe: KPI_MSSQL_ERRORLOG_HIST nao foi expurgado';\n"
               "END\nGO\n")
GEN_FIM_NEW = ("        PRINT '[AVISO] usp_purge_errorlog_hist nao existe: KPI_MSSQL_ERRORLOG_HIST nao foi expurgado';\n"
               "\n"
               "    -- B2b-2 2026-09-15: agregados horarios do errorlog, com o tempo que sobra DEPOIS da purga da HIST (guardiao).\n"
               "    IF OBJECT_ID('dbo.usp_purge_errorlog_agg', 'P') IS NOT NULL\n"
               "    BEGIN\n"
               "        DECLARE @restante_agg INT = @max_minutes - DATEDIFF(MINUTE, @inicio, GETDATE());\n"
               "        IF @restante_agg < 1 SET @restante_agg = 1;\n"
               "        EXEC dbo.usp_purge_errorlog_agg @dry_run = @dry_run, @max_minutes = @restante_agg;\n"
               "    END\n"
               "END\nGO\n")

MIGRATION_HEAD = """-- ============================================================================
-- Migration 015: agregados horarios do errorlog e retencao de 13 meses (B2b-2)
-- ----------------------------------------------------------------------------
-- Data: 2026-09-15 | Gate: watcherdb-v1-intel-specialist (consenso com ajustes, incorporados)
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring, NUNCA utilizador de dominio) | Onde: servidor da Intelligence
-- Depende de: migration 013 (WDB_RETENTION_POLICY, WDB_LEGAL_HOLD, usp_purge_errorlog_hist)
--
-- CONTEXTO (medido a 15/09): Security e Repetitive sao 99% do errorlog recolhido e so viviam 65 min na STG. A politica
-- de 15/09 preve agregados horarios sem texto pessoal durante 13 meses.
--
-- O QUE FAZ: cria KPI_MSSQL_ERRORLOG_AGG_HIST (CHECK: so Security e Repetitive; Sample_Text NULL em Security),
-- usp_errorlog_agg_merge, a camada AGREGADOS (395 dias, 365 a 1095), usp_purge_errorlog_agg; altera usp_purge_kpi_history
-- (chama a nova no fim, com o tempo que sobra depois da HIST); GRANT SELECT a sql_monitoring.
-- NAO MUDA: a HIST, o arquivo, o job WatcherDB_Purge_History, o manifesto da Wave D.
-- NAO APAGA NADA: o fim ensaia o merge com ROLLBACK e a purga com @dry_run = 1 (so conta e regista).
-- ORDEM: correr ANTES de reiniciar o WatcherDBCollector.
--
-- Idempotente. ROLLBACK: repor usp_purge_kpi_history da migration 013; DROP PROCEDURE dbo.usp_purge_errorlog_agg e
-- dbo.usp_errorlog_agg_merge; DELETE da linha AGREGADOS em WDB_RETENTION_POLICY; DROP TABLE dbo.KPI_MSSQL_ERRORLOG_AGG_HIST.
-- ============================================================================
USE [WatcherDB_Intelligence];
GO

"""

MIGRATION_TAIL = """
-- Ensaio do merge com ROLLBACK: a 2.a leitura com contagem menor nao baixa o total; Security perde o texto; Critical e ignorado
BEGIN TRAN;
EXEC dbo.usp_errorlog_agg_merge @environment = 'TST', @json = N'[
 {"instance":"B2B2_ENSAIO_I01","hour_ts":"2026-09-15T17:00:00","log_type":"Repetitive","category":"auditoria_sem_acesso","error_number":33208,"state":null,"severity":17,"occurrences":12,"first_log_date":"2026-09-15T17:01:00","last_log_date":"2026-09-15T17:40:00","sample_text":"Error: 33208"},
 {"instance":"B2B2_ENSAIO_I01","hour_ts":"2026-09-15T17:00:00","log_type":"Security","category":"login_falhado","error_number":18456,"state":8,"severity":14,"occurrences":5,"first_log_date":"2026-09-15T17:02:00","last_log_date":"2026-09-15T17:30:00","sample_text":"Login failed for user x [CLIENT: 10.0.0.1]"},
 {"instance":"B2B2_ENSAIO_I01","hour_ts":"2026-09-15T17:00:00","log_type":"Critical","category":"io_corrupcao","error_number":824,"state":null,"severity":24,"occurrences":1,"first_log_date":"2026-09-15T17:03:00","last_log_date":"2026-09-15T17:03:00","sample_text":"Error: 824"}]';
EXEC dbo.usp_errorlog_agg_merge @environment = 'TST', @json = N'[
 {"instance":"B2B2_ENSAIO_I01","hour_ts":"2026-09-15T17:00:00","log_type":"Repetitive","category":"auditoria_sem_acesso","error_number":33208,"state":null,"severity":17,"occurrences":7,"first_log_date":"2026-09-15T16:59:00","last_log_date":"2026-09-15T17:55:00","sample_text":"Error: 33208"}]';
-- Esperado 2 linhas: Repetitive 33208 State -1 Occurrences 12, First 16:59, Last 17:55, com texto;
--                    Security 18456 State 8 Occurrences 5, Sample_Text NULL
SELECT Log_Type, Error_Number, State, Occurrences, First_Log_Date, Last_Log_Date, Sample_Text
FROM dbo.KPI_MSSQL_ERRORLOG_AGG_HIST WHERE Instance = 'B2B2_ENSAIO_I01' ORDER BY Log_Type;
ROLLBACK;
GO

-- Ensaio da purga (so conta e regista PURGE_DRY; nao apaga)
EXEC dbo.usp_purge_errorlog_agg @dry_run = 1;
GO

-- Verificacao: 0 linhas de ensaio, a camada AGREGADOS, o registo PURGE_DRY e os objectos
SELECT COUNT(*) AS linhas_ensaio_depois_do_rollback FROM dbo.KPI_MSSQL_ERRORLOG_AGG_HIST WHERE Instance = 'B2B2_ENSAIO_I01';
SELECT Table_Name, Tier, Retention_Days, Min_Days, Max_Days FROM dbo.WDB_RETENTION_POLICY WHERE Tier = 'AGREGADOS';
SELECT TOP 1 Run_Start, Index_Name, Action_Taken, Page_Count AS linhas FROM dbo.WDB_MAINTENANCE_LOG
WHERE Object_Name = 'KPI_MSSQL_ERRORLOG_AGG_HIST' ORDER BY Log_Id DESC;
SELECT name, type_desc FROM sys.objects
WHERE name IN ('KPI_MSSQL_ERRORLOG_AGG_HIST', 'usp_errorlog_agg_merge', 'usp_purge_errorlog_agg', 'usp_purge_kpi_history');
GO
"""

CANONICAL_SECTION = """
-- ============================================================================
-- SECAO 39: AGREGADOS HORARIOS DO ERRORLOG (B2b-2, 2026-09-15)
-- ============================================================================
-- Security e Repetitive contados por hora, sem texto pessoal, 13 meses (camada AGREGADOS de WDB_RETENTION_POLICY).
-- Escrita pelo recolhedor do errorlog em cada ciclo (fora do applock do store); expurgo por usp_purge_errorlog_agg,
-- chamada no fim de usp_purge_kpi_history. Migration 015.
-- ============================================================================
PRINT '';
PRINT '----------------------------------------';
PRINT 'SECAO 39: AGREGADOS HORARIOS DO ERRORLOG';
PRINT '----------------------------------------';
GO

""" + OBJETOS_SQL + """
PRINT '  [OK] Agregados horarios do errorlog (SECAO 39)';
GO
"""

# ---------------------------------------------------------------- recolhedor
CLASS_ATTRS = '''    # B2a-2b 2026-09-15: recuperar a janela perdida a partir da marca de agua (WDB_ERRORLOG_READ_STATE)
    RECOVERY_MAX_HOURS = 24
    RECOVERY_OVERLAP_MINUTES = 5
    RECOVERY_MAX_INSTANCES = 10          # guardiao: espalhar uma recuperacao de frota por varios ciclos
    EVENT_TYPES = ("Lifecycle", "AvailabilityGroup", "Critical", "Error")   # os que o arquivo guarda na HIST
    AGG_TYPES = ("Security", "Repetitive")                                  # B2b-2: so estes vao para os agregados
'''

JANELA_METODOS = '''    def _janela(self, server_id, ate, normal):
        """B2a-2b 2026-09-15: inicio da leitura e marca de agua a gravar, no relogio do servidor.

        Marca atrasada e escolhida para recuperar neste ciclo: desde a marca menos a sobreposicao, com tecto de 24 h, e a
        marca passa a ser `ate`. Atrasada mas adiada (tecto de instancias por ciclo): janela normal e fica gravada a marca
        antiga, para recuperar num ciclo seguinte. Sem marca ou sem atraso: janela normal e marca `ate`.
        """
        folga = timedelta(minutes=self.RECOVERY_OVERLAP_MINUTES)
        marca = self.__dict__.get("_recuperar", {}).get(server_id)
        if marca is not None and marca - folga < normal:
            desde = max(ate - timedelta(hours=self.RECOVERY_MAX_HOURS), marca - folga)
            self.logger.info(f"{server_id}: recuperacao de janela desde {desde:%Y-%m-%d %H:%M} "
                             f"({int((normal - desde).total_seconds() // 60)} min alem da janela normal)")
            return desde, ate
        adiada = self.__dict__.get("_adiados", {}).get(server_id)
        if adiada is not None and adiada - folga < normal:
            return normal, adiada
        return normal, ate

    def _ler_marcas(self, environment):
        """B2a-2b: marcas de agua do ambiente (identidade do mestre do recolhedor, so leitura). Fail-open: {}."""
        conn = None
        try:
            conn = pyodbc.connect(self._build_master_conn_str(), autocommit=True, timeout=15)
            cur = conn.cursor()
            cur.execute(
                "SET NOCOUNT ON; IF OBJECT_ID('dbo.WDB_ERRORLOG_READ_STATE', 'U') IS NOT NULL "
                "SELECT Instance, Read_Until_Server_TS FROM dbo.WDB_ERRORLOG_READ_STATE WITH (NOLOCK) WHERE Environment = ?;",
                (environment.upper(),),
            )
            return {r[0]: r[1] for r in (cur.fetchall() if cur.description else []) if r[1] is not None}
        except Exception as e:
            self.logger.warning(f"Marcas de agua indisponiveis (le a janela normal): {_sanear(e, 1000)}")
            return {}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _planear_recuperacao(self, environment, servers):
        """B2a-2b: as marcas mais antigas primeiro, ate RECOVERY_MAX_INSTANCES; as outras ficam adiadas (guardiao)."""
        marcas = self._ler_marcas(environment)
        limite = datetime.now() - timedelta(minutes=self.WINDOW_MINUTES + self.RECOVERY_OVERLAP_MINUTES)
        ids = {s.server_id for s in servers}
        atrasadas = sorted((m, sid) for sid, m in marcas.items() if sid in ids and m < limite)
        recuperar = {sid: m for m, sid in atrasadas[:self.RECOVERY_MAX_INSTANCES]}
        adiados = {sid: m for m, sid in atrasadas[self.RECOVERY_MAX_INSTANCES:]}
        if atrasadas:
            self.logger.info(f"Recuperacao de janela: {len(recuperar)} instancias neste ciclo, {len(adiados)} adiadas")
        return recuperar, adiados

    def _agregar(self, server_id, eventos):
        """B2b-2 2026-09-15: contagens horarias de Security e Repetitive desta leitura (corre nas threads).

        Error_Number 0 e State -1 quando nao ha (fazem parte da chave). Sample_Text sempre None em Security: o texto traz
        login e IP e os agregados ficam 13 meses (guardiao; a tabela tambem o impoe com uma CHECK).
        """
        grupos = []
        for g in aggregate_hourly(e for e in eventos if e.log_type in self.AGG_TYPES):
            seguranca = g["log_type"] == "Security"
            grupos.append({
                "instance": server_id, "hour_ts": g["hour"].isoformat(), "log_type": g["log_type"],
                "category": g["category"], "error_number": g["error_number"] if g["error_number"] is not None else 0,
                "state": g["state"] if (seguranca and g["state"] is not None) else -1,
                "severity": g["severity"], "occurrences": int(g["occurrences"]),
                "first_log_date": g["first_log_date"].isoformat(), "last_log_date": g["last_log_date"].isoformat(),
                "sample_text": None if seguranca else (g["sample_text"] or "")[:400],
            })
        with self._estados_lock:
            self.__dict__.setdefault("_agregados", {})[server_id] = grupos

    def registar_agregados(self, environment):
        """B2b-2 2026-09-15: grava os agregados horarios (dbo.usp_errorlog_agg_merge, migration 015).

        Chamada propria, fora do applock do store, try proprio: falhar os agregados nao falha o KPI. Devolve o numero de
        grupos enviados, ou None.
        """
        grupos = [g for lista in self.__dict__.get("_agregados", {}).values() for g in lista]
        if not grupos:
            return None
        conn = None
        try:
            conn = pyodbc.connect(self._build_master_conn_str(), autocommit=True, timeout=15)
            conn.cursor().execute(
                "SET NOCOUNT ON; EXEC dbo.usp_errorlog_agg_merge @environment = ?, @json = ?;",
                (environment.upper(), json.dumps(grupos)),
            )
            self.logger.info(f"Agregados horarios: {len(grupos)} grupos")
            return len(grupos)
        except Exception as e:
            self.logger.warning(f"Agregados horarios falharam (o KPI segue): {_sanear(e, 1000)}")
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

'''

COLLECTOR_EDITS = [
    ("from watcherdb_intelligence.collectors.errorlog_classifier import DROP, classify, text_hash\n",
     "from watcherdb_intelligence.collectors.errorlog_classifier import DROP, aggregate_hourly, classify, text_hash\n"),
    ("    _estados_lock = threading.Lock()\n", "    _estados_lock = threading.Lock()\n" + CLASS_ATTRS),
    ("                desde = ate - timedelta(minutes=self.WINDOW_MINUTES)\n                actual = self._read_window(cursor, 0, desde, ate)\n",
     "                normal = ate - timedelta(minutes=self.WINDOW_MINUTES)\n"
     "                desde, marca_gravar = self._janela(server_id, ate, normal)     # B2a-2b\n"
     "                actual = self._read_window(cursor, 0, desde, ate)\n"),
    ("            data = []\n            recolha = datetime.now()\n            for numero, linhas in ((1, anterior), (0, actual)):\n"
     "                for ev in classify(linhas):\n                    if ev.action == DROP:\n                        continue\n",
     "            data = []\n            recolha = datetime.now()\n            eventos = []\n"
     "            for numero, linhas in ((1, anterior), (0, actual)):\n"
     "                for ev in classify(linhas):\n                    eventos.append(ev)\n"
     "                    if ev.action == DROP:\n                        continue\n"
     "                    # B2a-2b: na parte recuperada (antes da janela normal) so eventos; Security e Repetitive vao so para\n"
     "                    # os agregados. Sem isto uma recuperacao de frota traria centenas de milhares de linhas num ciclo.\n"
     "                    if ev.log_date < normal and ev.log_type not in self.EVENT_TYPES:\n"
     "                        continue\n"),
    ("            self._marcar(server_id, tentativa, ok=True, ate=ate, linhas=len(data), logs=2 if leu_anterior else 1)\n",
     "            self._agregar(server_id, eventos)     # B2b-2\n"
     "            self._marcar(server_id, tentativa, ok=True, ate=marca_gravar, linhas=len(data), logs=2 if leu_anterior else 1)\n"),
    ("    def _marcar(self, server_id, tentativa, ok, ate=None, linhas=None, logs=None, erro=None):\n",
     JANELA_METODOS + "    def _marcar(self, server_id, tentativa, ok, ate=None, linhas=None, logs=None, erro=None):\n"),
    ('        self.logger.info(f"Servidores selecionados: {len(servers)} de {len(all_servers)} ({environment})")\n',
     '        self.logger.info(f"Servidores selecionados: {len(servers)} de {len(all_servers)} ({environment})")\n'
     "        self._agregados = {}     # B2b-2: agregados horarios deste ciclo, por instancia\n"
     "        self._recuperar, self._adiados = self._planear_recuperacao(environment, servers)     # B2a-2b\n"),
    ('cursor.execute("SET NOCOUNT ON; EXEC dbo.usp_archive_errorlog_events @days_to_archive = 1;")\n',
     '# B2a-2b 2026-09-15: 2 dias -- a recuperacao traz ate 24 h e a borda nao pode ficar de fora (guardiao)\n'
     '            cursor.execute("SET NOCOUNT ON; EXEC dbo.usp_archive_errorlog_events @days_to_archive = 2;")\n'),
    ("        self.registar_estado(args.environment)\n",
     "        self.registar_estado(args.environment)\n        self.registar_agregados(args.environment)     # B2b-2\n"),
]

ADAPTER_EDITS = [
    ("            collector.registar_estado(environment)\n",
     "            collector.registar_estado(environment)\n"
     "            collector.registar_agregados(environment)     # B2b-2: agregados horarios, chamada propria\n"),
]

B2A2A_TEST_EDITS = [
    ('        def registar_estado(self, env):\n            ordem.append("estado")\n',
     '        def registar_estado(self, env):\n            ordem.append("estado")\n\n'
     '        def registar_agregados(self, env):\n            ordem.append("agregados")\n'),
    ('    assert r["success"] is True and ordem == ["collect_all", "estado", "heartbeat"]\n',
     '    assert r["success"] is True and ordem == ["collect_all", "estado", "agregados", "heartbeat"]\n'),
    ('    assert ordem == ["collect_all", "estado"], "ciclo cego nao escreve heartbeat"\n',
     '    assert ordem == ["collect_all", "estado", "agregados"], "ciclo cego nao escreve heartbeat"\n'),
    ('    assert ordem == ["collect_all", "estado", "store"]\n',
     '    assert ordem == ["collect_all", "estado", "agregados", "store"]\n'),
]

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Alterado — B2a-2b e B2b-2: recuperacao da janela do errorlog e agregados horarios (migration 015)\n\n"
                  "- O recolhedor do errorlog recupera o intervalo nao lido depois de uma falha, a partir da marca de agua de\n"
                  "  `WDB_ERRORLOG_READ_STATE` (tecto de 24 h, sobreposicao de 5 min, no maximo 10 instancias por ciclo; as outras\n"
                  "  mantem a marca e recuperam depois). Na parte recuperada so entram eventos; o arquivo passa a 2 dias.\n"
                  "- Tabela nova `KPI_MSSQL_ERRORLOG_AGG_HIST` (seccao 39): Security e Repetitive contados por hora, sem texto\n"
                  "  pessoal (CHECK), 13 meses pela camada AGREGADOS; `usp_errorlog_agg_merge` e `usp_purge_errorlog_agg`, chamada no\n"
                  "  fim de `usp_purge_kpi_history` com o tempo que sobra. Gate do guardiao: consenso com ajustes.\n\n")

TEST_SRC = r'''"""
B2a-2b e B2b-2 (2026-09-15): recuperar a janela perdida a partir da marca de agua e agregados horarios.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import scripts.collectors.collect_errorlog as mod

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
ATE = datetime(2026, 9, 15, 18, 0, 0)
NORMAL = ATE - timedelta(minutes=65)


class Log:
    def __init__(self):
        self.linhas = []

    def __getattr__(self, nivel):
        return lambda m, *a, **k: self.linhas.append((nivel, m))


def novo():
    c = object.__new__(mod.ErrorLogCollector)
    c.logger = Log()
    c.get_connection_string = lambda cfg: "DRIVER=x"
    c._build_master_conn_str = lambda: "DRIVER=x;PWD=segredo;"
    return c


def test_janela_normal_recuperada_adiada_e_tecto():
    c = novo()
    assert c._janela("A_I01", ATE, NORMAL) == (NORMAL, ATE)
    marca = ATE - timedelta(hours=3)
    c._recuperar = {"A_I01": marca, "B_I01": ATE - timedelta(hours=30), "C_I01": ATE - timedelta(minutes=5)}
    assert c._janela("A_I01", ATE, NORMAL) == (marca - timedelta(minutes=5), ATE)
    assert c._janela("B_I01", ATE, NORMAL) == (ATE - timedelta(hours=24), ATE)
    assert c._janela("C_I01", ATE, NORMAL) == (NORMAL, ATE), "sem atraso real no relogio do servidor"
    c._adiados = {"D_I01": marca, "E_I01": ATE - timedelta(minutes=4)}
    assert c._janela("D_I01", ATE, NORMAL) == (NORMAL, marca), "adiada: marca antiga fica gravada"
    assert c._janela("E_I01", ATE, NORMAL) == (NORMAL, ATE)


def test_plano_mais_antigas_primeiro_com_tecto_de_dez(monkeypatch):
    c = novo()
    agora = datetime.now()
    marcas = {f"S{i:02d}_I01": agora - timedelta(hours=i + 2) for i in range(15)}
    marcas["RECENTE_I01"] = agora - timedelta(minutes=3)
    marcas["FORA_I01"] = agora - timedelta(days=1)
    c._ler_marcas = lambda env: marcas
    servers = [type("S", (), {"server_id": sid})() for sid in marcas if sid != "FORA_I01"]
    recuperar, adiados = c._planear_recuperacao("PRD", servers)
    assert sorted(recuperar) == sorted(f"S{i:02d}_I01" for i in range(5, 15))
    assert sorted(adiados) == sorted(f"S{i:02d}_I01" for i in range(5))
    assert "RECENTE_I01" not in recuperar and "FORA_I01" not in recuperar and "FORA_I01" not in adiados


class Cur:
    def __init__(self, conn):
        self.conn, self.description, self._rows = conn, None, []

    def execute(self, sql, params=()):
        self.conn.chamadas.append((sql, params))
        if sql.startswith("SELECT GETDATE()"):
            self._rows, self.description = [(ATE,)], [("x",)]
        elif "xp_readerrorlog" in sql:
            rows = self.conn.logs.get(int(sql.split("xp_readerrorlog")[1].split(",")[0]), [])
            self._rows, self.description = rows, ([("LogDate",)] if rows else None)
        elif "usp_errorlog_agg_merge" in sql and self.conn.falha:
            raise RuntimeError("Could not find stored procedure 'dbo.usp_errorlog_agg_merge'. PWD=segredo;")

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)


class Conn:
    def __init__(self, logs=None, falha=False):
        self.logs, self.falha, self.chamadas, self.timeout = logs or {}, falha, [], 0

    def cursor(self):
        return Cur(self)

    def close(self):
        pass


def test_recuperacao_so_eventos_na_parte_antiga_e_agregados_sem_texto_pessoal(monkeypatch):
    velho, recente = datetime(2026, 9, 15, 15, 30), datetime(2026, 9, 15, 17, 30)
    logs = {0: [
        (velho, "Logon", "Error: 18456, Severity: 14, State: 8."), (velho, "Logon", "Login failed for user 'x'. [CLIENT: 10.0.0.1]"),
        (velho, "spid9", "Error: 824, Severity: 24, State: 2."), (velho, "spid9", "SQL Server detected a logical consistency-based I/O error."),
        (recente, "Logon", "Error: 18456, Severity: 14, State: 8."), (recente, "Logon", "Login failed for user 'x'. [CLIENT: 10.0.0.1]"),
        (recente, "spid7", "Error: 33208, Severity: 17, State: 1."),
    ]}
    conn = Conn(logs)
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: conn)
    c = novo()
    c._recuperar = {"SRV_I01": datetime(2026, 9, 15, 15, 0)}
    data = c.collect_from_server(type("Cfg", (), {"server_id": "SRV_I01"})())
    _, params = next(ch for ch in conn.chamadas if "xp_readerrorlog 0" in ch[0])
    assert params[0] == "20260915 14:55:00"
    assert sorted((d["Log_Type"], d["Log_Date"]) for d in data) == [("Critical", velho), ("Repetitive", recente), ("Security", recente)]
    grupos = c._agregados["SRV_I01"]
    seg = [g for g in grupos if g["log_type"] == "Security"]
    assert {g["hour_ts"] for g in seg} == {"2026-09-15T15:00:00", "2026-09-15T17:00:00"}
    assert all(g["sample_text"] is None and g["state"] == 8 and g["error_number"] == 18456 for g in seg)
    rep, = [g for g in grupos if g["log_type"] == "Repetitive"]
    assert rep["state"] == -1 and rep["sample_text"].startswith("Error: 33208")
    assert not any(g["log_type"] in ("Critical", "AvailabilityGroup") for g in grupos)
    assert c._estados["SRV_I01"]["read_until_server_ts"] == "2026-09-15T18:00:00"


def test_adiada_grava_a_marca_antiga(monkeypatch):
    conn = Conn({0: []})
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: conn)
    c = novo()
    c._adiados = {"SRV_I01": datetime(2026, 9, 15, 12, 0)}
    c.collect_from_server(type("Cfg", (), {"server_id": "SRV_I01"})())
    assert c._estados["SRV_I01"]["read_until_server_ts"] == "2026-09-15T12:00:00"
    _, params = next(ch for ch in conn.chamadas if "xp_readerrorlog 0" in ch[0])
    assert params[0] == "20260915 16:55:00"


def test_registar_agregados(monkeypatch):
    conn = Conn()
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: conn)
    c = novo()
    assert c.registar_agregados("PRD") is None and conn.chamadas == []
    c._agregados = {"A_I01": [{"instance": "A_I01", "log_type": "Repetitive"}], "B_I01": []}
    assert c.registar_agregados("prd") == 1
    (sql, params), = conn.chamadas
    assert "EXEC dbo.usp_errorlog_agg_merge @environment = ?, @json = ?" in sql and params[0] == "PRD"
    assert json.loads(params[1])[0]["instance"] == "A_I01"
    c2 = novo()
    monkeypatch.setattr(mod.pyodbc, "connect", lambda *a, **k: Conn(falha=True))
    c2._agregados = {"A_I01": [{"instance": "A_I01"}]}
    assert c2.registar_agregados("PRD") is None
    nivel, msg = c2.logger.linhas[-1]
    assert nivel == "warning" and "Agregados horarios falharam (o KPI segue)" in msg and "segredo" not in msg


def test_arquivo_dois_dias_e_servico():
    fonte = (ROOT / "scripts" / "collectors" / "collect_errorlog.py").read_text(encoding="utf-8")
    assert "@days_to_archive = 2;" in fonte and "@days_to_archive = 1;" not in fonte
    adapter = (ROOT / "services" / "collector_service" / "collectors" / "collect_errorlog.py").read_text(encoding="utf-8")
    assert adapter.index("collector.registar_estado(environment)") < adapter.index("collector.registar_agregados(environment)") \
        < adapter.index("if df.empty:")


def test_migration_015_e_canonico():
    mig = (ROOT / "database" / "migrations" / "015_errorlog_agregados_horarios.sql").read_text(encoding="utf-8")
    can = (ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql").read_text(encoding="utf-8", errors="replace")
    for txt in (mig, can):
        assert "CONSTRAINT CK_ELAGG_SEM_TEXTO_PESSOAL CHECK (Log_Type <> 'Security' OR Sample_Text IS NULL)" in txt
        assert "CONSTRAINT CK_ELAGG_TIPO CHECK (Log_Type IN ('Security', 'Repetitive'))" in txt
        assert "Occurrences    = CASE WHEN s.occurrences > t.Occurrences THEN s.occurrences ELSE t.Occurrences END" in txt
        assert "'KPI_MSSQL_ERRORLOG_AGG_HIST', 'AGREGADOS', 395, 365, 1095" in txt
        purga = txt[txt.index("CREATE OR ALTER PROCEDURE dbo.usp_purge_kpi_history"):]
        purga = purga[:purga.index("\nGO")]
        assert purga.index("EXEC dbo.usp_purge_errorlog_hist") < purga.index("DECLARE @restante_agg INT") \
            < purga.index("EXEC dbo.usp_purge_errorlog_agg")
    assert "BEGIN TRAN;" in mig and "ROLLBACK;" in mig and not re.search(r"\bCOMMIT\b", mig)
    assert "EXEC dbo.usp_purge_errorlog_agg @dry_run = 1;" in mig and "@dry_run = 0" not in mig
    assert "SECAO 39: AGREGADOS HORARIOS DO ERRORLOG" in can
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
    if not cauda.endswith("GO") or "(SECAO 38)" not in cauda[-200:]:
        print("[ABORT] o canonico nao termina na seccao 38 como medido -- nada escrito"); return 1
    ceol = _eol(can)
    can_novo = _edit(can, [(GEN_FIM_OLD, GEN_FIM_NEW)], "canonico")
    # a migration leva a purga generica inteira, tal como fica no canonico
    lf = can_novo.replace("\r\n", "\n")
    ini = lf.index("CREATE OR ALTER PROCEDURE dbo.usp_purge_kpi_history")
    fim = lf.index("\nEND\nGO\n", ini) + len("\nEND\nGO\n")
    purga_generica = lf[ini:fim]
    if "usp_purge_errorlog_agg" not in purga_generica or "usp_purge_errorlog_hist" not in purga_generica:
        print("[ABORT] purga generica extraida sem as duas chamadas -- nada escrito"); return 1
    can_novo = can_novo + ("" if can_novo.endswith(("\n", "\r\n")) else ceol) + CANONICAL_SECTION.replace("\n", ceol)
    migration = MIGRATION_HEAD + OBJETOS_SQL + "\n" + purga_generica + MIGRATION_TAIL
    col = _edit(src["collector"].read_bytes().decode("utf-8"), COLLECTOR_EDITS, "recolhedor")
    ada = _edit(src["adapter"].read_bytes().decode("utf-8"), ADAPTER_EDITS, "adapter")
    t2a = _edit(src["test_b2a2a"].read_bytes().decode("utf-8"), B2A2A_TEST_EDITS, "teste B2a-2a")
    chg = _edit(src["changelog"].read_bytes().decode("utf-8"), [(CHANGELOG_ANCORA, CHANGELOG_NOVO)], "changelog")
    compile(col, str(REL["collector"]), "exec")
    compile(ada, str(REL["adapter"]), "exec")
    compile(t2a, str(REL["test_b2a2a"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] recolhedor {len(COLLECTOR_EDITS)} blocos, adapter {len(ADAPTER_EDITS)}, teste B2a-2a {len(B2A2A_TEST_EDITS)} (compilam); "
          f"migration 015 ({migration.count(chr(10))} linhas); canonico seccao 39 + purga generica; teste; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["collector"].write_bytes(col.encode("utf-8")); print(f"[write] {REL['collector']}")
    src["adapter"].write_bytes(ada.encode("utf-8")); print(f"[write] {REL['adapter']}")
    src["migration"].write_bytes(migration.replace("\n", "\r\n").encode("utf-8")); print(f"[new]   {REL['migration']}")
    src["canonical"].write_bytes(can_novo.encode("utf-8")); print(f"[write] {REL['canonical']}")
    src["test_b2a2a"].write_bytes(t2a.encode("utf-8")); print(f"[write] {REL['test_b2a2a']}")
    src["changelog"].write_bytes(chg.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Testes; migration 015 no SSMS com a CONTA DE DEPLOY; SO DEPOIS Restart-Service WatcherDBCollector.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
