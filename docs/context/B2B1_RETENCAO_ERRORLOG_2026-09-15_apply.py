# -*- coding: utf-8 -*-
"""B2b-1 (2026-09-15) -- politica de retencao do historico do errorlog: camadas, legal hold, corte por Log_Date, registo.

Politica decidida a 15/09 com o watcherdb-security-auditor (plano PLANO_EXECUCAO_ALERTAS_ERRORLOG_2026-09-14.md do V3.4):
  camada CURTA   90 dias (min 30, max 90)   falhas de login e contas (Security), repetitivos, e as linhas do recolhedor antigo
                                            RGPD art. 5.(1)(e): o texto traz login e IP
  camada EVENTOS 12 meses (min 12, max 36)  Lifecycle, AvailabilityGroup, Critical, Error do recolhedor B1b
                                            PCI DSS 10.5.1 quando aplicavel; DORA RTS art. 12; ISO 27001 A.8.15
  agregados horarios 13 meses: fica para quando existir a agregacao (B2b-2).
Desenho revisto pelo guardiao do recolhedor (15/09), sem veto; os dois pontos levantados estao resolvidos assim:
  - Linha do recolhedor antigo = Log_Type 'Error' com Update_TS antes de 2026-09-15. Por construcao o classificador B1b so
    produz 'Error' a partir de um cabecalho com numero (teste novo trava isso); e o limite de data faz com que um evento
    novo mal classificado fique 12 meses, nunca 90 dias.
  - Indice: Update_TS faz parte da chave clustered, logo esta em todos os indices nao clustered. O IX_LogDate (Log_Date,
    INCLUDE Instance, Log_Type) cobre o predicado inteiro sem lookup nas 2,7 milhoes de linhas antigas. Sem rebuild.

Medido a 15/09 (sql_monitoring): usp_purge_kpi_history viva = canonico; job WatcherDB_Purge_History diario 00:00, no
manifesto da Wave D (falha do job ja e acusada); HIST com 2.727.010 linhas antigas e 207 eventos novos.

O que cria (migration 013 e seccao 37 do canonico):
  1. dbo.WDB_RETENTION_POLICY com CHECK de minimo e maximo, e seed das duas camadas.
  2. dbo.WDB_RETENTION_POLICY_HIST preenchida pelo trigger TR_WDB_RETENTION_POLICY_AUDIT (set-based: quem, quando, antes
     e depois; apanha tambem edicoes manuais no SSMS).
  3. dbo.WDB_LEGAL_HOLD por instancia (activo enquanto Released_At for NULL).
  4. dbo.usp_purge_errorlog_hist: corte sobre Log_Date com os dias da politica; sem politica, RAISERROR e nao apaga;
     exclui instancias com hold activo; DELETE TOP em lotes com timebox; regista cada camada em WDB_MAINTENANCE_LOG
     (Index_Name = camada, dias, corte e numero de holds).
  5. usp_purge_kpi_history: o ERRORLOG_HIST sai da lista (90 dias sobre Update_TS) e a proc passa a chamar a nova no fim,
     com o tempo que sobra. O job e o manifesto nao mudam; um erro da proc nova falha o passo e o verificador acusa.
Efeito: as linhas antigas continuam a sair aos 90 dias, agora pela data do evento; os eventos passam a ficar 12 meses.

Uso (raiz do repo V3.4):
  py docs/context/B2B1_RETENCAO_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B2B1_RETENCAO_ERRORLOG_2026-09-15_apply.py
  cd "..\\WATCHERDB INTELLIGENCE V1" ; py -m pytest tests/unit/test_errorlog_retencao_b2b1.py -q -p no:cacheprovider
  SSMS, servidor da Intelligence, CONTA DE DEPLOY: database/migrations/013_errorlog_retencao_por_camada.sql
  (a migration termina com um ensaio @dry_run = 1 que so conta e regista; o primeiro expurgo real e o do job das 00:00)
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "migration": Path("database/migrations/013_errorlog_retencao_por_camada.sql"),
    "canonical": Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"),
    "test": Path("tests/unit/test_errorlog_retencao_b2b1.py"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "usp_purge_errorlog_hist"

OBJETOS_SQL = """IF OBJECT_ID('dbo.WDB_RETENTION_POLICY', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WDB_RETENTION_POLICY (
        Table_Name      NVARCHAR(128)   NOT NULL,
        Tier            VARCHAR(20)     NOT NULL,
        Retention_Days  INT             NOT NULL,
        Min_Days        INT             NOT NULL,
        Max_Days        INT             NOT NULL,
        Legal_Basis     NVARCHAR(400)   NULL,
        Updated_By      NVARCHAR(128)   NOT NULL CONSTRAINT DF_WDB_RETPOL_BY DEFAULT SUSER_SNAME(),
        Updated_At      DATETIME2       NOT NULL CONSTRAINT DF_WDB_RETPOL_AT DEFAULT GETDATE(),
        CONSTRAINT PK_WDB_RETENTION_POLICY PRIMARY KEY CLUSTERED (Table_Name, Tier),
        CONSTRAINT CK_WDB_RETPOL_LIMITES CHECK (Min_Days > 0 AND Min_Days <= Max_Days
                                                AND Retention_Days BETWEEN Min_Days AND Max_Days)
    );
    PRINT '  [OK] WDB_RETENTION_POLICY';
END
GO

IF OBJECT_ID('dbo.WDB_RETENTION_POLICY_HIST', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WDB_RETENTION_POLICY_HIST (
        Change_Id           BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_WDB_RETENTION_POLICY_HIST PRIMARY KEY,
        Change_At           DATETIME2       NOT NULL CONSTRAINT DF_WDB_RETPOLH_AT DEFAULT GETDATE(),
        Changed_By          NVARCHAR(128)   NOT NULL CONSTRAINT DF_WDB_RETPOLH_BY DEFAULT SUSER_SNAME(),
        Operation           CHAR(1)         NOT NULL,   -- I, U, D
        Table_Name          NVARCHAR(128)   NOT NULL,
        Tier                VARCHAR(20)     NOT NULL,
        Old_Retention_Days  INT             NULL,
        New_Retention_Days  INT             NULL,
        Old_Min_Days        INT             NULL,
        New_Min_Days        INT             NULL,
        Old_Max_Days        INT             NULL,
        New_Max_Days        INT             NULL
    );
    PRINT '  [OK] WDB_RETENTION_POLICY_HIST';
END
GO

CREATE OR ALTER TRIGGER dbo.TR_WDB_RETENTION_POLICY_AUDIT
ON dbo.WDB_RETENTION_POLICY
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    -- B2b-1 2026-09-15: historico de alteracoes da politica (quem, quando, antes e depois). Set-based: varias linhas por instrucao.
    SET NOCOUNT ON;
    INSERT INTO dbo.WDB_RETENTION_POLICY_HIST
        (Operation, Table_Name, Tier, Old_Retention_Days, New_Retention_Days, Old_Min_Days, New_Min_Days, Old_Max_Days, New_Max_Days)
    SELECT CASE WHEN d.Table_Name IS NULL THEN 'I' WHEN i.Table_Name IS NULL THEN 'D' ELSE 'U' END,
           COALESCE(i.Table_Name, d.Table_Name), COALESCE(i.Tier, d.Tier),
           d.Retention_Days, i.Retention_Days, d.Min_Days, i.Min_Days, d.Max_Days, i.Max_Days
    FROM inserted i
    FULL OUTER JOIN deleted d ON d.Table_Name = i.Table_Name AND d.Tier = i.Tier;
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.WDB_RETENTION_POLICY WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND Tier = 'EVENTOS')
    INSERT INTO dbo.WDB_RETENTION_POLICY (Table_Name, Tier, Retention_Days, Min_Days, Max_Days, Legal_Basis)
    VALUES ('KPI_MSSQL_ERRORLOG_HIST', 'EVENTOS', 365, 365, 1095,
            N'Lifecycle, AvailabilityGroup, Critical, Error. PCI DSS 10.5.1 quando aplicavel; DORA RTS art. 12; ISO 27001 A.8.15. Decisao 2026-09-15.');
IF NOT EXISTS (SELECT 1 FROM dbo.WDB_RETENTION_POLICY WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND Tier = 'CURTA')
    INSERT INTO dbo.WDB_RETENTION_POLICY (Table_Name, Tier, Retention_Days, Min_Days, Max_Days, Legal_Basis)
    VALUES ('KPI_MSSQL_ERRORLOG_HIST', 'CURTA', 90, 30, 90,
            N'Security (login e IP), Repetitive e linhas do recolhedor antigo. RGPD art. 5.(1)(e), minimizacao. Decisao 2026-09-15.');
GO

IF OBJECT_ID('dbo.WDB_LEGAL_HOLD', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WDB_LEGAL_HOLD (
        Hold_Id         INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_WDB_LEGAL_HOLD PRIMARY KEY,
        Instance        VARCHAR(128)    NOT NULL,
        Table_Name      NVARCHAR(128)   NOT NULL,
        Reason          NVARCHAR(400)   NOT NULL,
        Set_By          NVARCHAR(128)   NOT NULL CONSTRAINT DF_WDB_LEGALHOLD_BY DEFAULT SUSER_SNAME(),
        Set_At          DATETIME2       NOT NULL CONSTRAINT DF_WDB_LEGALHOLD_AT DEFAULT GETDATE(),
        Released_By     NVARCHAR(128)   NULL,
        Released_At     DATETIME2       NULL
    );
    CREATE NONCLUSTERED INDEX IX_WDB_LEGAL_HOLD_Activo ON dbo.WDB_LEGAL_HOLD (Table_Name, Instance) WHERE Released_At IS NULL;
    PRINT '  [OK] WDB_LEGAL_HOLD';
END
GO

CREATE OR ALTER PROCEDURE dbo.usp_purge_errorlog_hist
    @dry_run BIT = 1, @batch_size INT = 20000, @max_minutes INT = 20
AS
BEGIN
    -- B2b-1 2026-09-15: expurgo do historico do errorlog por camada (WDB_RETENTION_POLICY), com legal hold por instancia
    -- (WDB_LEGAL_HOLD), corte sobre Log_Date e registo de cada camada em WDB_MAINTENANCE_LOG.
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2 = GETDATE(), @t0 DATETIME2;
    DECLARE @dias_eventos INT, @dias_curta INT, @corte_eventos DATETIME2, @corte_curta DATETIME2;
    DECLARE @apagadas BIGINT, @lote INT, @holds INT;
    -- Linhas do recolhedor antigo: tipo 'Error' gravadas antes do B1b. O limite de data garante que um evento novo mal
    -- classificado cai nos 12 meses, nunca nos 90 dias. Update_TS esta na chave clustered: sem lookup no IX_LogDate.
    DECLARE @fim_legado DATETIME2 = '2026-09-15T00:00:00';

    IF OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_HIST', 'U') IS NULL
    BEGIN
        PRINT '[SKIP] KPI_MSSQL_ERRORLOG_HIST';
        RETURN 0;
    END;

    SELECT @dias_eventos = Retention_Days FROM dbo.WDB_RETENTION_POLICY
    WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND Tier = 'EVENTOS';
    SELECT @dias_curta = Retention_Days FROM dbo.WDB_RETENTION_POLICY
    WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND Tier = 'CURTA';
    IF @dias_eventos IS NULL OR @dias_curta IS NULL
    BEGIN
        RAISERROR('usp_purge_errorlog_hist: politica em falta em WDB_RETENTION_POLICY (EVENTOS e CURTA). Nada apagado.', 16, 1);
        RETURN 1;
    END;

    SET @corte_eventos = DATEADD(DAY, -@dias_eventos, GETDATE());
    SET @corte_curta = DATEADD(DAY, -@dias_curta, GETDATE());
    SELECT @holds = COUNT(*) FROM dbo.WDB_LEGAL_HOLD
    WHERE Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND Released_At IS NULL;

    -- ---- camada CURTA
    SET @t0 = GETDATE(); SET @apagadas = 0;
    IF @dry_run = 1
        SELECT @apagadas = COUNT_BIG(*) FROM dbo.KPI_MSSQL_ERRORLOG_HIST h WITH (NOLOCK)
        WHERE h.Log_Date < @corte_curta
          AND (ISNULL(h.Log_Type, '') IN ('Security', 'Repetitive') OR (ISNULL(h.Log_Type, '') = 'Error' AND h.Update_TS < @fim_legado))
          AND NOT EXISTS (SELECT 1 FROM dbo.WDB_LEGAL_HOLD lh
                          WHERE lh.Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND lh.Released_At IS NULL AND lh.Instance = h.Instance);
    ELSE
    BEGIN
        SET @lote = 1;
        WHILE @lote > 0
        BEGIN
            IF DATEDIFF(MINUTE, @inicio, GETDATE()) >= @max_minutes BEGIN PRINT '[TIMEBOX] camada CURTA'; BREAK; END;
            DELETE TOP (@batch_size) h FROM dbo.KPI_MSSQL_ERRORLOG_HIST h
            WHERE h.Log_Date < @corte_curta
              AND (ISNULL(h.Log_Type, '') IN ('Security', 'Repetitive') OR (ISNULL(h.Log_Type, '') = 'Error' AND h.Update_TS < @fim_legado))
              AND NOT EXISTS (SELECT 1 FROM dbo.WDB_LEGAL_HOLD lh
                              WHERE lh.Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND lh.Released_At IS NULL AND lh.Instance = h.Instance);
            SET @lote = @@ROWCOUNT; SET @apagadas = @apagadas + @lote;
        END;
    END;
    PRINT CONCAT('[', CASE WHEN @dry_run = 1 THEN 'DRY' ELSE 'PURGE' END, '] ERRORLOG_HIST camada CURTA: ', @apagadas);
    INSERT INTO dbo.WDB_MAINTENANCE_LOG (Run_Start, Object_Name, Index_Name, Action_Taken, Page_Count, Duration_Ms)
    VALUES (@inicio, 'KPI_MSSQL_ERRORLOG_HIST',
            CONCAT('camada=CURTA;dias=', @dias_curta, ';corte=', CONVERT(VARCHAR(19), @corte_curta, 126), ';holds=', @holds),
            CASE WHEN @dry_run = 1 THEN 'PURGE_DRY' ELSE 'PURGE' END, @apagadas, DATEDIFF(MILLISECOND, @t0, GETDATE()));

    -- ---- camada EVENTOS (tudo o que nao e CURTA)
    SET @t0 = GETDATE(); SET @apagadas = 0;
    IF @dry_run = 1
        SELECT @apagadas = COUNT_BIG(*) FROM dbo.KPI_MSSQL_ERRORLOG_HIST h WITH (NOLOCK)
        WHERE h.Log_Date < @corte_eventos
          AND NOT (ISNULL(h.Log_Type, '') IN ('Security', 'Repetitive') OR (ISNULL(h.Log_Type, '') = 'Error' AND h.Update_TS < @fim_legado))
          AND NOT EXISTS (SELECT 1 FROM dbo.WDB_LEGAL_HOLD lh
                          WHERE lh.Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND lh.Released_At IS NULL AND lh.Instance = h.Instance);
    ELSE
    BEGIN
        SET @lote = 1;
        WHILE @lote > 0
        BEGIN
            IF DATEDIFF(MINUTE, @inicio, GETDATE()) >= @max_minutes BEGIN PRINT '[TIMEBOX] camada EVENTOS'; BREAK; END;
            DELETE TOP (@batch_size) h FROM dbo.KPI_MSSQL_ERRORLOG_HIST h
            WHERE h.Log_Date < @corte_eventos
              AND NOT (ISNULL(h.Log_Type, '') IN ('Security', 'Repetitive') OR (ISNULL(h.Log_Type, '') = 'Error' AND h.Update_TS < @fim_legado))
              AND NOT EXISTS (SELECT 1 FROM dbo.WDB_LEGAL_HOLD lh
                              WHERE lh.Table_Name = 'KPI_MSSQL_ERRORLOG_HIST' AND lh.Released_At IS NULL AND lh.Instance = h.Instance);
            SET @lote = @@ROWCOUNT; SET @apagadas = @apagadas + @lote;
        END;
    END;
    PRINT CONCAT('[', CASE WHEN @dry_run = 1 THEN 'DRY' ELSE 'PURGE' END, '] ERRORLOG_HIST camada EVENTOS: ', @apagadas);
    INSERT INTO dbo.WDB_MAINTENANCE_LOG (Run_Start, Object_Name, Index_Name, Action_Taken, Page_Count, Duration_Ms)
    VALUES (@inicio, 'KPI_MSSQL_ERRORLOG_HIST',
            CONCAT('camada=EVENTOS;dias=', @dias_eventos, ';corte=', CONVERT(VARCHAR(19), @corte_eventos, 126), ';holds=', @holds),
            CASE WHEN @dry_run = 1 THEN 'PURGE_DRY' ELSE 'PURGE' END, @apagadas, DATEDIFF(MILLISECOND, @t0, GETDATE()));
    RETURN 0;
END;
GO
"""

# usp_purge_kpi_history: texto vivo = canonico (verificado a 15/09), com as duas mudancas do B2b-1
PURGE_GENERICA_SQL = """CREATE OR ALTER PROCEDURE dbo.usp_purge_kpi_history
    @dry_run BIT = 1, @batch_size INT = 50000, @max_minutes INT = 30
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2 = GETDATE();
    DECLARE @tab NVARCHAR(200), @col NVARCHAR(64), @dias INT;
    DECLARE @sql NVARCHAR(MAX), @apagadas BIGINT, @lote INT, @t0 DATETIME2;
    DECLARE @alvos TABLE (Tabela NVARCHAR(200), Coluna NVARCHAR(64), Dias INT);
    -- B2b-1 2026-09-15: KPI_MSSQL_ERRORLOG_HIST saiu desta lista (era 90 dias sobre Update_TS); ver fim da procedure.
    INSERT INTO @alvos VALUES
        ('KPI_MSSQL_FG_USAGE_HIST',    'Collect_TS',    180),
        ('KPI_MSSQL_DATAFILES_HIST',   'Collect_TS',    180),
        ('KPI_MSSQL_DEADLOCKS_HIST',   'Deadlock_Time', 180),
        ('WatcherDB_Ensemble_Results', 'EvaluatedAt',    90);
    DECLARE alvo_cur CURSOR LOCAL FOR SELECT Tabela, Coluna, Dias FROM @alvos;
    OPEN alvo_cur;
    FETCH NEXT FROM alvo_cur INTO @tab, @col, @dias;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF OBJECT_ID('dbo.' + @tab, 'U') IS NULL
        BEGIN
            PRINT '[SKIP] ' + @tab;
            FETCH NEXT FROM alvo_cur INTO @tab, @col, @dias;
            CONTINUE;
        END
        SET @t0 = GETDATE(); SET @apagadas = 0;
        IF @dry_run = 1
        BEGIN
            SET @sql = N'SELECT @n = COUNT_BIG(*) FROM dbo.' + QUOTENAME(@tab)
                     + N' WITH (NOLOCK) WHERE ' + QUOTENAME(@col)
                     + N' < DATEADD(DAY, -' + CAST(@dias AS NVARCHAR(6)) + N', GETDATE())';
            EXEC sp_executesql @sql, N'@n BIGINT OUTPUT', @n = @apagadas OUTPUT;
            PRINT '[DRY] ' + @tab + ': ' + CAST(@apagadas AS VARCHAR(20)) + ' alem da janela';
            INSERT INTO dbo.WDB_MAINTENANCE_LOG (Run_Start, Object_Name, Index_Name, Action_Taken, Page_Count, Duration_Ms)
            VALUES (@inicio, @tab, NULL, 'PURGE_DRY', @apagadas, DATEDIFF(MILLISECOND, @t0, GETDATE()));
        END
        ELSE
        BEGIN
            SET @lote = 1;
            WHILE @lote > 0
            BEGIN
                IF DATEDIFF(MINUTE, @inicio, GETDATE()) >= @max_minutes
                BEGIN PRINT '[TIMEBOX] em ' + @tab; BREAK; END
                SET @sql = N'DELETE TOP (' + CAST(@batch_size AS NVARCHAR(10)) + N') FROM dbo.' + QUOTENAME(@tab)
                         + N' WHERE ' + QUOTENAME(@col) + N' < DATEADD(DAY, -' + CAST(@dias AS NVARCHAR(6)) + N', GETDATE())';
                EXEC sp_executesql @sql;
                SET @lote = @@ROWCOUNT; SET @apagadas = @apagadas + @lote;
            END
            PRINT '[PURGE] ' + @tab + ': ' + CAST(@apagadas AS VARCHAR(20)) + ' apagadas';
            INSERT INTO dbo.WDB_MAINTENANCE_LOG (Run_Start, Object_Name, Index_Name, Action_Taken, Page_Count, Duration_Ms)
            VALUES (@inicio, @tab, NULL, 'PURGE', @apagadas, DATEDIFF(MILLISECOND, @t0, GETDATE()));
        END
        FETCH NEXT FROM alvo_cur INTO @tab, @col, @dias;
    END
    CLOSE alvo_cur; DEALLOCATE alvo_cur;

    -- B2b-1 2026-09-15: historico do errorlog por camada (politica, legal hold, corte por Log_Date), com o tempo que sobra.
    -- Sem TRY/CATCH de proposito: um erro (ex.: politica em falta) falha o passo do job e o verificador da Wave D acusa.
    IF OBJECT_ID('dbo.usp_purge_errorlog_hist', 'P') IS NOT NULL
    BEGIN
        DECLARE @restante INT = @max_minutes - DATEDIFF(MINUTE, @inicio, GETDATE());
        IF @restante < 1 SET @restante = 1;
        EXEC dbo.usp_purge_errorlog_hist @dry_run = @dry_run, @max_minutes = @restante;
    END
    ELSE
        PRINT '[AVISO] usp_purge_errorlog_hist nao existe: KPI_MSSQL_ERRORLOG_HIST nao foi expurgado';
END
GO
"""

MIGRATION_SQL = """-- ============================================================================
-- Migration 013: retencao do historico do errorlog por camada, legal hold e corte por Log_Date (B2b-1)
-- ----------------------------------------------------------------------------
-- Data: 2026-09-15 | Politica: watcherdb-security-auditor | Gate: watcherdb-v1-intel-specialist (sem veto)
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring, NUNCA utilizador de dominio) | Onde: servidor da Intelligence
--
-- CONTEXTO (medido a 15/09): o historico KPI_MSSQL_ERRORLOG_HIST era expurgado a 90 dias sobre Update_TS (data de
-- recolha) por usp_purge_kpi_history, igual para tudo. Politica decidida: CURTA 90 dias (Security, Repetitive e linhas
-- do recolhedor antigo, RGPD); EVENTOS 12 meses (Lifecycle, AvailabilityGroup, Critical, Error; PCI DSS 10.5.1, DORA,
-- ISO 27001). Legal hold por instancia. Corte pela data do evento. Registo de cada camada em WDB_MAINTENANCE_LOG.
--
-- O QUE FAZ: cria WDB_RETENTION_POLICY (+ seed), WDB_RETENTION_POLICY_HIST e o trigger de auditoria, WDB_LEGAL_HOLD,
-- usp_purge_errorlog_hist; altera usp_purge_kpi_history (tira o errorlog da lista e chama a nova no fim).
-- NAO MUDA: o job WatcherDB_Purge_History, a sua agenda nem o manifesto da Wave D.
-- NAO APAGA NADA agora: o fim deste ficheiro so faz um ensaio @dry_run = 1 (conta e regista). O primeiro expurgo real e
-- o do job das 00:00.
--
-- Idempotente. ROLLBACK: repor usp_purge_kpi_history a partir do canonico anterior (commit V1 983155a) e
-- DROP PROCEDURE dbo.usp_purge_errorlog_hist; as tabelas novas podem ficar (nao sao lidas por mais nada).
-- ============================================================================
USE [WatcherDB_Intelligence];
GO

""" + OBJETOS_SQL + "\n" + PURGE_GENERICA_SQL + """
-- Ensaio (so conta e regista em WDB_MAINTENANCE_LOG como PURGE_DRY; nao apaga)
EXEC dbo.usp_purge_errorlog_hist @dry_run = 1;
GO

-- Verificacao: esperado 2 linhas de politica e 2 linhas PURGE_DRY acabadas de registar
SELECT Table_Name, Tier, Retention_Days, Min_Days, Max_Days, Updated_By, Updated_At FROM dbo.WDB_RETENTION_POLICY;
SELECT TOP 2 Run_Start, Index_Name, Action_Taken, Page_Count AS linhas, Duration_Ms
FROM dbo.WDB_MAINTENANCE_LOG WHERE Object_Name = 'KPI_MSSQL_ERRORLOG_HIST' ORDER BY Log_Id DESC;
GO
"""

CANONICAL_SECTION = """
-- ============================================================================
-- SECAO 37: RETENCAO DO HISTORICO DO ERRORLOG POR CAMADA (B2b-1, 2026-09-15, migration 013)
-- ============================================================================
-- Politica CURTA 90 dias / EVENTOS 12 meses, legal hold por instancia, corte por Log_Date, registo em WDB_MAINTENANCE_LOG.
-- Chamada no fim de usp_purge_kpi_history (job WatcherDB_Purge_History, 00:00). Agregados horarios: B2b-2.
-- ============================================================================
""" + OBJETOS_SQL + """
PRINT '  [OK] Retencao do errorlog por camada (SECAO 37)';
GO
"""

GEN_LINHA_OLD = "        ('KPI_MSSQL_ERRORLOG_HIST',    'Update_TS',      90),\n"
GEN_LINHA_NEW = ""
GEN_FIM_OLD = "    CLOSE alvo_cur; DEALLOCATE alvo_cur;\nEND\nGO\n"
GEN_FIM_NEW = PURGE_GENERICA_SQL[PURGE_GENERICA_SQL.index("    CLOSE alvo_cur; DEALLOCATE alvo_cur;\n"):]
GEN_LISTA_OLD = "    INSERT INTO @alvos VALUES\n        ('KPI_MSSQL_FG_USAGE_HIST',"
GEN_LISTA_NEW = ("    -- B2b-1 2026-09-15: KPI_MSSQL_ERRORLOG_HIST saiu desta lista (era 90 dias sobre Update_TS); ver fim da procedure.\n"
                 "    INSERT INTO @alvos VALUES\n        ('KPI_MSSQL_FG_USAGE_HIST',")

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Alterado — B2b-1: retencao do historico do errorlog por camada (migration 013)\n\n"
                  "- **`WDB_RETENTION_POLICY`** com minimo e maximo e historico de alteracoes por trigger; **`WDB_LEGAL_HOLD`** por\n"
                  "  instancia; **`usp_purge_errorlog_hist`**: camada CURTA 90 dias (Security, Repetitive, linhas do recolhedor antigo),\n"
                  "  camada EVENTOS 12 meses, corte sobre `Log_Date`, sem politica nao apaga, registo por camada em `WDB_MAINTENANCE_LOG`.\n"
                  "- `usp_purge_kpi_history` deixa de expurgar o errorlog a 90 dias sobre `Update_TS` e chama a proc nova no fim. Job e\n"
                  "  manifesto inalterados. Politica decidida com o security-auditor; desenho revisto pelo guardiao do recolhedor.\n\n")

TEST_SRC = r'''"""
B2b-1 (2026-09-15): retencao do errorlog por camada. O classificador tem de garantir que o tipo Error traz sempre numero:
e o que permite a procedure distinguir as linhas do recolhedor antigo (Error sem numero, antes de 15/09) dos eventos novos.
"""
from datetime import datetime
from pathlib import Path

import pytest

from watcherdb_intelligence.collectors.errorlog_classifier import classify

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
T = datetime(2026, 9, 15, 15, 0)

AMOSTRA = [
    (T, "Server", "SQL Server is starting at normal priority base (=7)."),
    (T, "spid5", "Error: 3041, Severity: 16, State: 1."), (T, "spid5", "BACKUP failed to complete the command BACKUP DATABASE X."),
    (T, "spid6", "Error: 99999, Severity: 21, State: 1."),
    (T, "spid7", "Error: 18210, Severity: 16, State: 1."),
    (T, "spid8", "A significant part of sql server process memory has been paged out."),
    (T, "spid9", "The state of the local availability replica in availability group 'AG' has changed from 'A' to 'B'."),
    (T, "spid10", "Autogrow of file 'x' in database 'y' was cancelled by user or timed out after 60 ms."),
    (T, "spid11", "DBCC CHECKDB (X) executed by Y found 2 errors and repaired 0 errors."),
    (T, "Logon", "Error: 18456, Severity: 14, State: 5."), (T, "Logon", "Login failed for user 'a'."),
]


def test_tipo_error_traz_sempre_numero_de_erro():
    eventos = classify(AMOSTRA)
    erros = [e for e in eventos if e.log_type == "Error"]
    assert erros, "a amostra tem de produzir eventos Error"
    assert all(e.error_number is not None for e in erros)


def test_regras_de_texto_nunca_produzem_o_tipo_error():
    from watcherdb_intelligence.collectors import errorlog_classifier as clf
    assert all(regra[1] != "Error" for regra in clf.TEXT_RULES)


def test_migration_013_tem_as_garantias_do_desenho():
    sql = (ROOT / "database" / "migrations" / "013_errorlog_retencao_por_camada.sql").read_text(encoding="utf-8")
    assert "RAISERROR('usp_purge_errorlog_hist: politica em falta" in sql
    assert "h.Log_Date < @corte_curta" in sql and "h.Log_Date < @corte_eventos" in sql
    assert "h.Update_TS < @fim_legado" in sql and "DECLARE @fim_legado DATETIME2 = '2026-09-15T00:00:00';" in sql
    assert sql.count("lh.Released_At IS NULL AND lh.Instance = h.Instance") == 4
    assert "FULL OUTER JOIN deleted d" in sql
    assert "CHECK (Min_Days > 0 AND Min_Days <= Max_Days" in sql
    assert "('KPI_MSSQL_ERRORLOG_HIST',    'Update_TS',      90)" not in sql
    assert "EXEC dbo.usp_purge_errorlog_hist @dry_run = @dry_run, @max_minutes = @restante;" in sql
    assert "EXEC dbo.usp_purge_errorlog_hist @dry_run = 1;" in sql
    assert "@dry_run = 0" not in sql, "a migration nunca apaga: so ensaio"


def test_canonico_alinhado():
    can = (ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql").read_text(encoding="utf-8", errors="replace")
    assert "SECAO 37: RETENCAO DO HISTORICO DO ERRORLOG POR CAMADA" in can
    assert "('KPI_MSSQL_ERRORLOG_HIST',    'Update_TS',      90)" not in can
    assert "EXEC dbo.usp_purge_errorlog_hist @dry_run = @dry_run, @max_minutes = @restante;" in can
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
    if src["migration"].exists() or src["test"].exists():
        print("[ABORT] ja aplicado"); return 1
    can = src["canonical"].read_bytes().decode("utf-8")
    if MARK in can:
        print("[ABORT] canonico ja tem a procedure"); return 1
    cauda = can.replace("\r\n", "\n").rstrip()
    if not cauda.endswith("GO") or "(SECAO 36)" not in cauda[-200:]:
        print("[ABORT] o canonico nao termina na seccao 36 como medido -- nada escrito"); return 1
    ceol = _eol(can)
    can_novo = _edit(can, [(GEN_LISTA_OLD, GEN_LISTA_NEW), (GEN_LINHA_OLD, GEN_LINHA_NEW), (GEN_FIM_OLD, GEN_FIM_NEW)], "canonico")
    can_novo = can_novo + ("" if can_novo.endswith(("\n", "\r\n")) else ceol) + CANONICAL_SECTION.replace("\n", ceol)
    chg = _edit(src["changelog"].read_bytes().decode("utf-8"), [(CHANGELOG_ANCORA, CHANGELOG_NOVO)], "changelog")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] migration 013; canonico (proc generica + seccao 37); teste; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["migration"].write_bytes(MIGRATION_SQL.replace("\n", "\r\n").encode("utf-8")); print(f"[new]   {REL['migration']}")
    src["canonical"].write_bytes(can_novo.encode("utf-8")); print(f"[write] {REL['canonical']}")
    src["changelog"].write_bytes(chg.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Testes; depois a migration 013 no SSMS com a CONTA DE DEPLOY (so ensaia, nao apaga).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
