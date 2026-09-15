# -*- coding: utf-8 -*-
"""B2a-1c (2026-09-15) -- DDL da familia KPI_MSSQL_ERRORLOG no canonico, alinhada com a base viva. So canonico e docs.

Parecer do guardiao do recolhedor (15/09): o bloco comentado da STG base e da HIST no canonico e obsoleto (taxonomia e
chave antigas) e nao deve ser descomentado; a DDL a trazer e a da base viva, num lote proprio. Baseline de referencia:
database/baseline/errorlog_familia_viva_2026-09-15.sql (V1 521abdc).

O defeito numa instalacao nova: o passo "Criar tabelas Blue-Green base" so copia _BLUE/_GREEN quando a tabela base existe,
e a base do errorlog esta comentada; o usp_setup_environment_tables faz SKIP; a familia fica sem tabelas, mas as vistas
_ACTIVE/_STG, o recolhedor e a procedure usp_archive_errorlog_events contam com ela.

O que muda no canonico (idempotente, IF NOT EXISTS, sem DROP):
  1. Cria KPI_MSSQL_ERRORLOG_STG_BLUE e _GREEN explicitamente, como ja se faz para a ALWAYSON, logo a seguir a essa, antes
     do usp_setup_environment_tables. Estrutura igual a viva: HEAP sem chave, Log_Text_Hash INT NULL (nao calculado).
  2. Cria KPI_MSSQL_ERRORLOG_HIST explicitamente com a estrutura viva: Log_Text_Hash AS CHECKSUM(Log_Text) PERSISTED,
     PK (Instance, Log_Date, Log_Text_Hash, Update_TS) em FG_KPI_HIST, indices LogDate (DESC, INCLUDE Instance, Log_Type) e
     LogType (Log_Type, Log_Date DESC).
  3. Nota antes dos dois blocos comentados antigos a dizer que estao obsoletos e onde esta a DDL certa.
Nada disto corre na base viva: la a familia ja existe. Verificado na base viva, so leitura, que a DDL gerada coincide
coluna a coluna com o catalogo (script de prova no scratchpad da sessao).
Documentacao: docs/DIAGRAMA_RELACIONAMENTO_BANCO.md (seccao ERRORLOG) e docs/CHANGELOG.md.

Uso (raiz do repo V3.4):
  py docs/context/B2A1C_CANONICO_DDL_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B2A1C_CANONICO_DDL_ERRORLOG_2026-09-15_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
REL = {
    "canonical": Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"),
    "diagrama": Path("docs/DIAGRAMA_RELACIONAMENTO_BANCO.md"),
    "changelog": Path("docs/CHANGELOG.md"),
}
MARK = "B2a-1c 2026-09-15"

COLUNAS_STG = """        Instance            VARCHAR(128)    NOT NULL,
        Log_Date            DATETIME2(7)    NOT NULL,
        Process_Info        VARCHAR(128)    NULL,
        Log_Text            NVARCHAR(MAX)   NOT NULL,
        Log_Text_Hash       INT             NULL,
        Log_Type            VARCHAR(32)     NULL,
        Error_Number        INT             NULL,
        Severity            INT             NULL,
        State               INT             NULL,
        Log_File_Number     INT             NULL,
        Update_TS           DATETIME2(7)    NULL
"""

BLUE_GREEN_SQL = ""
for _slot in ("BLUE", "GREEN"):
    BLUE_GREEN_SQL += (
        f"IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_ERRORLOG_STG_{_slot}')\n"
        "BEGIN\n"
        f"    CREATE TABLE dbo.KPI_MSSQL_ERRORLOG_STG_{_slot} (\n"
        + COLUNAS_STG +
        "    );\n"
        f"    PRINT '    [OK] KPI_MSSQL_ERRORLOG_STG_{_slot}';\n"
        "END\n"
        "GO\n\n")

BLUE_GREEN_BLOCK = (
    "\n-- B2a-1c 2026-09-15: base Blue-Green do ERRORLOG criada explicitamente (como a ALWAYSON acima). A tabela base\n"
    "-- KPI_MSSQL_ERRORLOG_STG esta comentada como descontinuada (bloco obsoleto), por isso o ciclo de copia acima nao a\n"
    "-- criava e o usp_setup_environment_tables fazia SKIP. Estrutura igual a base viva (baseline 2026-09-15): HEAP sem\n"
    "-- chave primaria, Log_Text_Hash INT normal. Os indices por ambiente sao omitidos (@skip_default_indexes = 1, abaixo).\n"
    + BLUE_GREEN_SQL)

HIST_BLOCK = """-- ============================================================================
-- B2a-1c 2026-09-15: KPI_MSSQL_ERRORLOG_HIST com a estrutura da base viva (baseline 2026-09-15). Escrita a cada ciclo
-- por dbo.usp_archive_errorlog_events (SECAO 36, migration 012) e diariamente por usp_archive_errorlog. Expurgo em
-- usp_purge_kpi_history. O bloco comentado "HIST 4" logo abaixo e OBSOLETO e nao deve ser descomentado.
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_ERRORLOG_HIST')
BEGIN
    CREATE TABLE dbo.KPI_MSSQL_ERRORLOG_HIST (
        Instance            VARCHAR(128)    NOT NULL,
        Log_Date            DATETIME2(7)    NOT NULL,
        Process_Info        VARCHAR(128)    NULL,
        Log_Text            NVARCHAR(MAX)   NOT NULL,
        Log_Text_Hash       AS CHECKSUM(Log_Text) PERSISTED NOT NULL,
        Log_Type            VARCHAR(32)     NULL,
        Error_Number        INT             NULL,
        Severity            INT             NULL,
        State               INT             NULL,
        Log_File_Number     INT             NULL,
        Update_TS           DATETIME2(7)    NOT NULL,
        CONSTRAINT PK_KPI_MSSQL_ERRORLOG_HIST
            PRIMARY KEY CLUSTERED (Instance, Log_Date, Log_Text_Hash, Update_TS)
    ) ON [FG_KPI_HIST];
    PRINT '  [OK] KPI_MSSQL_ERRORLOG_HIST';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPI_MSSQL_ERRORLOG_HIST_LogDate'
               AND object_id = OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_HIST'))
    CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_HIST_LogDate
        ON dbo.KPI_MSSQL_ERRORLOG_HIST (Log_Date DESC) INCLUDE (Instance, Log_Type) ON [FG_KPI_HIST];
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_KPI_MSSQL_ERRORLOG_HIST_LogType'
               AND object_id = OBJECT_ID('dbo.KPI_MSSQL_ERRORLOG_HIST'))
    CREATE NONCLUSTERED INDEX IX_KPI_MSSQL_ERRORLOG_HIST_LogType
        ON dbo.KPI_MSSQL_ERRORLOG_HIST (Log_Type, Log_Date DESC) ON [FG_KPI_HIST];
GO

"""

STG_NOTE = ("-- B2a-1c 2026-09-15: o bloco comentado abaixo e OBSOLETO (taxonomia ERROR/WARNING/INFO e chave antigas). A familia\n"
            "-- real do errorlog e Blue-Green por ambiente: as bases _BLUE/_GREEN sao criadas explicitamente a seguir a ALWAYSON.\n")

ANCHOR_ALWAYSON_GREEN = "    PRINT '    [OK] KPI_MSSQL_ALWAYSON_STATUS_STG_GREEN';\nEND\nGO\n"
ANCHOR_STG13 = "-- STG 13: KPI_MSSQL_ERRORLOG_STG\n"
ANCHOR_HIST4 = "-- HIST 4: KPI_MSSQL_ERRORLOG_HIST\n"

DIAGRAMA_OLD = "### ERRORLOG\n- KPI_MSSQL_ERRORLOG_STG\n"
DIAGRAMA_NEW = ("### ERRORLOG\n"
                "- KPI_MSSQL_ERRORLOG_STG (vista) -> _ACTIVE, slots _BLUE/_GREEN por ambiente (_PRD, _QA, _TST), HEAP sem PK\n"
                "- KPI_MSSQL_ERRORLOG_HIST (PK Instance, Log_Date, Log_Text_Hash calculado, Update_TS): escrita a cada ciclo por\n"
                "  usp_archive_errorlog_events (so eventos, migration 012) e as 05:00 por usp_archive_errorlog\n"
                "- Log_Type: Lifecycle, AvailabilityGroup, Critical, Error, Security, Repetitive (recolhedor B1b, 15/09)\n"
                "- Referencia da base viva: database/baseline/errorlog_familia_viva_2026-09-15.sql\n")

CHANGELOG_ANCORA = "## [Unreleased]\n\n"
CHANGELOG_NOVO = ("## [Unreleased]\n\n"
                  "### Corrigido — B2a-1c: DDL da familia errorlog no canonico\n\n"
                  "- Numa instalacao nova a familia `KPI_MSSQL_ERRORLOG` ficava sem tabelas: a base estava comentada como\n"
                  "  descontinuada, o passo Blue-Green nao copiava e o `usp_setup_environment_tables` fazia SKIP. O canonico passa a\n"
                  "  criar explicitamente `KPI_MSSQL_ERRORLOG_STG_BLUE/_GREEN` e `KPI_MSSQL_ERRORLOG_HIST` com a estrutura da base viva\n"
                  "  (baseline de 15/09), idempotente. Os blocos comentados antigos ficam marcados como obsoletos. Sem migration: a base\n"
                  "  viva ja tem a familia.\n\n")


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
    can = src["canonical"].read_bytes().decode("utf-8")
    if MARK in can:
        print("[ABORT] ja aplicado"); return 1
    lf = can.replace("\r\n", "\n")
    if lf.index(ANCHOR_ALWAYSON_GREEN) > lf.index("EXEC dbo.usp_setup_environment_tables @base_table_name = 'KPI_MSSQL_ERRORLOG_STG'"):
        print("[ABORT] a ALWAYSON GREEN ja nao vem antes do setup de ambientes -- nada escrito"); return 1
    out = {
        "canonical": _edit(can, [(ANCHOR_ALWAYSON_GREEN, ANCHOR_ALWAYSON_GREEN + BLUE_GREEN_BLOCK),
                                 (ANCHOR_STG13, STG_NOTE + ANCHOR_STG13),
                                 (ANCHOR_HIST4, HIST_BLOCK + ANCHOR_HIST4)], "canonico"),
        "diagrama": _edit(src["diagrama"].read_bytes().decode("utf-8"), [(DIAGRAMA_OLD, DIAGRAMA_NEW)], "diagrama"),
        "changelog": _edit(src["changelog"].read_bytes().decode("utf-8"), [(CHANGELOG_ANCORA, CHANGELOG_NOVO)], "changelog"),
    }
    print(f"[ok] canonico 3 blocos (base Blue-Green, HIST, notas de obsoleto); diagrama; changelog; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, txt in out.items():
        src[k].write_bytes(txt.encode("utf-8")); print(f"[write] {REL[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
