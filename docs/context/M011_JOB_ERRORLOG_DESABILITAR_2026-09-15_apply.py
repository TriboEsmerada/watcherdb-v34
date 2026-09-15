# -*- coding: utf-8 -*-
"""Migration 011 (2026-09-15) -- desabilitar o job WatcherDB_Collect_ErrorLogs, que diz sucesso e nao grava nada.

Decisao do owner a 15/09 ("vamos seguir com o recomendado"). Medido na base viva (sql_monitoring):
  - o job corre de 5 em 5 min no servidor da Intelligence e termina sempre com sucesso;
  - escreve em raw.sql_error_logs, que tem 0 linhas: o TRY/CATCH so faz PRINT do erro;
  - o errorlog real vem do servico Python (scripts/collectors/collect_errorlog.py), agora com o B1b.
Falso verde no SQL Agent. Segue o precedente do JOB 6 (AlwaysOn) no canonico: existe DESABILITADO, com a recolha
feita em Python. Desabilitar e' reversivel; apagar nao se faz sem outra decisao.

O verificador de trabalho agendado (Wave D) tem o job no manifesto com Enabled_Expected = 1. Desabilitar sem mexer
no manifesto gerava um alarme falso. Semantica do proprio manifesto: 0 = deve existir mas desactivado por escolha
(precedente: 'WatcherDB - Monitor 2PC Transactions').

Escreve no repo V1 (regra 2: mudanca de BD = canonico + documentacao no mesmo bloco):
  database/migrations/011_job_errorlog_desabilitado.sql        novo; o OWNER corre-o (regra 5)
  database/INSTALACAO_COMPLETA_UNIFICADA.sql                  job 5 criado desabilitado; manifesto com 0
  database/WAVE_D_VERIFICADOR_AGENDADOS.sql                   manifesto com 0
  database/CHANGELOG_JOBS_COLETA.md, docs/MAPA_MENTAL_ARQUITETURA.md, docs/CHANGELOG.md

Uso (raiz do repo V3.4):
  py docs/context/M011_JOB_ERRORLOG_DESABILITAR_2026-09-15_apply.py --check
  py docs/context/M011_JOB_ERRORLOG_DESABILITAR_2026-09-15_apply.py
  Depois, em SSMS no servidor da WatcherDB_Intelligence, com a conta de deploy da BD (NUNCA sql_monitoring):
  database/migrations/011_job_errorlog_desabilitado.sql
"""
from __future__ import annotations

import sys
from pathlib import Path

V34 = Path(__file__).resolve().parents[2]
V1 = V34.parent / "WATCHERDB INTELLIGENCE V1"
MIG = Path("database/migrations/011_job_errorlog_desabilitado.sql")

MIG_SQL = """-- ============================================================================
-- Migration 011: desabilitar o job WatcherDB_Collect_ErrorLogs (falso verde)
-- ----------------------------------------------------------------------------
-- Data: 2026-09-15 | Decisao do owner | Identidade: owner/deploy da BD (NUNCA sql_monitoring)
-- Onde: servidor da WatcherDB_Intelligence (o mesmo onde corre o SQL Agent do WatcherDB)
--
-- CONTEXTO (medido na base viva a 15/09, nao assumido):
--   O job corre de 5 em 5 minutos e termina sempre com sucesso. Escreve em raw.sql_error_logs,
--   que tem 0 linhas: o TRY/CATCH do passo so faz PRINT do erro. O errorlog real e' recolhido
--   pelo servico Python (scripts/collectors/collect_errorlog.py). Falso verde no SQL Agent.
--   Precedente no canonico: o JOB 6 (AlwaysOn) existe DESABILITADO com a recolha em Python.
--
-- O manifesto do verificador de trabalho agendado (Wave D) passa de Enabled_Expected 1 para 0
-- ("deve existir, desactivado por escolha"), senao o verificador acusava o job parado.
--
-- Idempotente. Nao apaga nada.
-- ROLLBACK: EXEC msdb.dbo.sp_update_job @job_name = N'WatcherDB_Collect_ErrorLogs', @enabled = 1;
--           UPDATE dbo.WDB_SCHEDULED_WORK_MANIFEST SET Enabled_Expected = 1, Notes = NULL
--            WHERE Work_Name = N'WatcherDB_Collect_ErrorLogs' AND Work_Type = 'AGENT_JOB';
-- ============================================================================
USE [msdb];
GO

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'WatcherDB_Collect_ErrorLogs' AND enabled = 1)
BEGIN
    EXEC msdb.dbo.sp_update_job
        @job_name = N'WatcherDB_Collect_ErrorLogs',
        @enabled = 0,
        @description = N'[DESABILITADO 2026-09-15, migration 011] Escrevia 0 linhas em raw.sql_error_logs e terminava com sucesso. O errorlog e recolhido pelo servico Python (collect_errorlog.py).';
    PRINT '011: job WatcherDB_Collect_ErrorLogs desabilitado.';
END
ELSE
    PRINT '011: job ausente ou ja desabilitado, nada a fazer.';
GO

USE [WatcherDB_Intelligence];
GO

IF OBJECT_ID('dbo.WDB_SCHEDULED_WORK_MANIFEST', 'U') IS NOT NULL
BEGIN
    UPDATE dbo.WDB_SCHEDULED_WORK_MANIFEST
       SET Enabled_Expected = 0,
           Notes = N'2026-09-15 migration 011: existe DESACTIVADO por escolha; escrevia 0 linhas em raw.sql_error_logs; errorlog via servico Python'
     WHERE Work_Name = N'WatcherDB_Collect_ErrorLogs'
       AND Work_Type = 'AGENT_JOB'
       AND Enabled_Expected = 1;
    PRINT CONCAT('011: manifesto actualizado, ', @@ROWCOUNT, ' linha(s).');
END
ELSE
    PRINT '011: manifesto da Wave D ausente nesta base, nada a fazer.';
GO

-- Verificacao: esperado enabled = 0 e Enabled_Expected = 0
SELECT j.name, j.enabled, m.Enabled_Expected, m.Notes
FROM msdb.dbo.sysjobs j
LEFT JOIN WatcherDB_Intelligence.dbo.WDB_SCHEDULED_WORK_MANIFEST m
       ON m.Work_Name = j.name AND m.Work_Type = 'AGENT_JOB'
WHERE j.name = N'WatcherDB_Collect_ErrorLogs';
GO
"""

MANIFEST_OLD = "    (N'WatcherDB_Collect_ErrorLogs',                 'AGENT_JOB',    15,    45, 1, N'INSTALACAO', NULL),\n"
MANIFEST_NEW = ("    (N'WatcherDB_Collect_ErrorLogs',                 'AGENT_JOB',    15,    45, 0, N'INSTALACAO (desabilitado na migration 011)', "
                "N'existe DESACTIVADO por escolha desde 2026-09-15; escrevia 0 linhas em raw.sql_error_logs; errorlog via servico Python'),\n")

FILES = {
    Path("database/INSTALACAO_COMPLETA_UNIFICADA.sql"): [
        ("-- JOB 5: COLLECT ERROR LOGS\n",
         "-- JOB 5: COLLECT ERROR LOGS (DESABILITADO - COLETA VIA PYTHON, migration 011 de 2026-09-15)\n"
         "-- ============================================================================\n"
         "-- NOTA: escrevia em raw.sql_error_logs, que ficava com 0 linhas, e terminava sempre com sucesso (o TRY/CATCH\n"
         "-- so fazia PRINT). O errorlog e' recolhido pelo servico Python (scripts/collectors/collect_errorlog.py).\n"
         "-- Mantido DESABILITADO, como o JOB 6. Para habilitar: EXEC msdb.dbo.sp_update_job\n"
         "--   @job_name = N'WatcherDB_Collect_ErrorLogs', @enabled = 1;\n", 1),
        ("    @job_name = N'WatcherDB_Collect_ErrorLogs',\n    @enabled = 1,\n    @description = N'Coleta error logs do SQL Server dos servidores monitorados';\n",
         "    @job_name = N'WatcherDB_Collect_ErrorLogs',\n    @enabled = 0,  -- DESABILITADO (migration 011): errorlog via servico Python\n"
         "    @description = N'[DESABILITADO] Coleta error logs via linked server - escrevia 0 linhas; o errorlog e recolhido pelo servico Python';\n", 1),
        ("Job WatcherDB_Collect_ErrorLogs criado (executa a cada 5 minutos)';",
         "Job WatcherDB_Collect_ErrorLogs criado DESABILITADO (errorlog via servico Python)';", 1),
        (MANIFEST_OLD, MANIFEST_NEW, 1),
    ],
    Path("database/WAVE_D_VERIFICADOR_AGENDADOS.sql"): [(MANIFEST_OLD, MANIFEST_NEW, 1)],
    Path("database/CHANGELOG_JOBS_COLETA.md"): [
        ("| 5 | `WatcherDB_Collect_ErrorLogs` | 5 min | ✅ Habilitado | Coleta error logs do SQL Server |\n",
         "| 5 | `WatcherDB_Collect_ErrorLogs` | 5 min | Desabilitado (migration 011, 2026-09-15) | Escrevia 0 linhas em raw.sql_error_logs; errorlog via servico Python |\n", 1),
    ],
    Path("docs/MAPA_MENTAL_ARQUITETURA.md"): [
        ("| WatcherDB_Collect_ErrorLogs | 30 min | usp_Collect_ErrorLog | Coleta de error logs |\n",
         "| WatcherDB_Collect_ErrorLogs | desabilitado (migration 011, 2026-09-15) | linked server para raw.sql_error_logs | Nunca gravou; errorlog via servico Python (collect_errorlog.py) |\n", 1),
    ],
    Path("docs/CHANGELOG.md"): [
        ("## [Unreleased]\n\n",
         "## [Unreleased]\n\n"
         "### Alterado — migration 011: job WatcherDB_Collect_ErrorLogs desabilitado\n\n"
         "- **O job terminava sempre com sucesso e gravava 0 linhas** em `raw.sql_error_logs` (TRY/CATCH so com PRINT).\n"
         "  Medido a 15/09. O errorlog vem do servico Python. Fica desabilitado, como o JOB 6 (AlwaysOn), no canonico e\n"
         "  na base viva; o manifesto da Wave D passa a `Enabled_Expected = 0` para o verificador nao acusar o job parado.\n"
         "- Ficheiro `database/migrations/011_job_errorlog_desabilitado.sql`, idempotente, com rollback no cabecalho.\n\n", 1),
    ],
}


def _eol(t):
    return "\r\n" if "\r\n" in t else "\n"


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or V1
    if (base / MIG).exists():
        print("[ABORT] ja aplicado (migration 011 existe)"); return 1
    out = {}
    for rel, edits in FILES.items():
        raw = (base / rel).read_bytes().decode("utf-8")
        eol = _eol(raw)
        txt = raw
        for old, new, count in edits:
            o, n = old.replace("\n", eol), new.replace("\n", eol)
            if txt.count(o) != count:
                print(f"[ABORT] {rel}: ancora encontrada {txt.count(o)}x, esperado {count} -- nada escrito\n  {old[:80]!r}"); return 1
            txt = txt.replace(o, n)
        out[rel] = txt
    print(f"[ok] {len(FILES)} ficheiros com ancoras unicas; migration 011 nova; destino {base}")
    if check:
        print("--check OK. Nada escrito."); return 0
    (base / MIG).write_bytes(MIG_SQL.replace("\n", "\r\n").encode("utf-8")); print(f"[new]   {MIG}")
    for rel, txt in out.items():
        (base / rel).write_bytes(txt.encode("utf-8")); print(f"[write] {rel}")
    print("\nAplicado. Corre a migration 011 em SSMS no servidor da Intelligence, com a conta de deploy da BD.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
