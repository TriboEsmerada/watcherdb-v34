"""LOTE CANONICO: grants do login de monitorizacao nas instancias -> canonico + documentacao (regra 2, 2026-09-08).

ONDE fica o canonico dos grants (decisao do council, aceite pelo owner): NAO dentro do
INSTALACAO_COMPLETA_UNIFICADA.sql -- esse instala a BD WatcherDB_Intelligence no servidor master
(USE [WatcherDB_Intelligence]); os grants correm em CADA instancia monitorizada. Meter GRANTs la'
dentro dava-os so' no master numa instalacao nova. O canonico das instancias e' docs/security/:
  - docs/security/LEAST_PRIVILEGE_SETUP.sql        (artefacto de prova, login descartavel WatcherDBReader)
  - docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql  (NOVO: o mesmo conjunto para a conta canonica
    sql_monitoring, idempotente, com verificacao final; validado em 62/63 instancias em 2026-09-08)
O unificado ganha um ponteiro OBRIGATORIO no bloco final de pos-instalacao; o INSTALL_GUIDE ganha o
passo 1.4 correcto (o snippet antigo so' dava VIEW SERVER STATE + VIEW ANY DEFINITION); a referencia
tecnica ganha a linha.

Correccoes tecnicas incluidas:
  - ALTER ROLE ... ADD MEMBER -> EXEC sp_addrolemember (ALTER ROLE so' existe desde SQL 2012; em 2005/2008
    o parser rejeita o lote inteiro -- medido em OATXP01, SQL 2005).

Idempotente; ancoras por texto unico; EOL preservado.
Uso (raiz do repo):  py docs/context/LOTE_CANONICO_GRANTS_apply.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_SQL = ROOT / "docs" / "context" / "GRANTS_SQL_MONITORING_MULTI_SERVER.sql"
DST_SQL = ROOT / "docs" / "security" / "GRANTS_SQL_MONITORING_INSTANCIA.sql"
LEAST = ROOT / "docs" / "security" / "LEAST_PRIVILEGE_SETUP.sql"
CANON = ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql"
GUIDE = ROOT / "docs" / "external" / "standard" / "INSTALL_GUIDE.md"
REF = ROOT / "docs" / "guides" / "referencia_tecnica.md"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


def _read(p: Path):
    raw = p.read_text(encoding="utf-8", newline="")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def _write(p: Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def _apply(p: Path, edits, done_marker: str) -> None:
    raw, eol = _read(p)
    if done_marker in raw:
        print(f"{p.name}: ja aplicado (skip)")
        return
    for old, _new in edits:
        o = old.replace("\n", eol)
        if raw.count(o) != 1:
            abort(f"{p.name}: esperava 1x a ancora que comeca por {old[:70]!r}, encontrei {raw.count(o)}")
    for old, new in edits:
        raw = raw.replace(old.replace("\n", eol), new.replace("\n", eol), 1)
    _write(p, raw)
    print(f"{p.name}: {len(edits)} substituicoes ancoradas")


# 1. canonico das instancias (copia do ficheiro validado, com o cabecalho a apontar para o sitio novo)
if DST_SQL.exists():
    print(f"{DST_SQL.name}: ja existe (skip)")
else:
    if not SRC_SQL.exists():
        abort(f"{SRC_SQL} nao existe")
    raw, eol = _read(SRC_SQL)
    raw = raw.replace("GRANTS_SQL_MONITORING_MULTI_SERVER.sql  (WatcherDB V3.4, P2, 2026-09-08)",
                      "GRANTS_SQL_MONITORING_INSTANCIA.sql  (canonico das instancias monitorizadas; WatcherDB V3.4, 2026-09-08)", 1)
    _write(DST_SQL, raw)
    print(f"docs/security/{DST_SQL.name} criado")

# 2. LEAST_PRIVILEGE_SETUP.sql: compatibilidade 2005/2008 + nota de uso em producao
_apply(
    LEAST,
    [
        (
            "ALTER ROLE SQLAgentReaderRole ADD MEMBER WatcherDBReader;\n",
            "-- sp_addrolemember: aceite de 2005 a 2022. ALTER ROLE ... ADD MEMBER so' existe desde 2012 e em\n"
            "-- 2005/2008 o PARSER rejeita o lote inteiro (medido em producao, 2026-09-08).\n"
            "EXEC sp_addrolemember N'SQLAgentReaderRole', N'WatcherDBReader';\n",
        ),
        (
            "Uso\n---\n  sqlcmd -S <instance> -E -i LEAST_PRIVILEGE_SETUP.sql\n",
            "Uso\n---\n  sqlcmd -S <instance> -E -i LEAST_PRIVILEGE_SETUP.sql\n"
            "\n"
            "Producao (conta canonica `sql_monitoring`, que JA existe na frota): NAO correr o\n"
            "bloco CREATE LOGIN; usar docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql, que da'\n"
            "exactamente este conjunto de permissoes a essa conta, e' idempotente e termina com\n"
            "uma linha de verificacao por instancia. Para as N instancias de uma vez: SSMS >\n"
            "Registered Servers (scripts/qa/runtime/gera_regsrvr.py gera o grupo) > New Query\n"
            "sobre o grupo. Rollback = REVOKE / sp_droprolemember, nunca DROP LOGIN.\n",
        ),
    ],
    "GRANTS_SQL_MONITORING_INSTANCIA.sql",
)

# 3. unificado: ponteiro obrigatorio (nao os grants)
_apply(
    CANON,
    [(
        "PRINT '  3. Execute: EXEC dbo.usp_refresh_overview_all (atualizar Overview Dashboard)';\n",
        "PRINT '  3. Execute: EXEC dbo.usp_refresh_overview_all (atualizar Overview Dashboard)';\n"
        "PRINT '  4. OBRIGATORIO, em CADA instancia monitorizada (NAO neste servidor):';\n"
        "PRINT '     docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql -- least-privilege do login';\n"
        "PRINT '     sql_monitoring (VIEW SERVER STATE/ANY DEFINITION/ANY DATABASE, msdb backup*/sysjobs*';\n"
        "PRINT '     + SQLAgentReaderRole, xp_readerrorlog, SHOWPLAN). Multi-servidor: SSMS Registered Servers.';\n",
    )],
    "GRANTS_SQL_MONITORING_INSTANCIA.sql",
)

# 4. INSTALL_GUIDE 1.4: o snippet antigo dava 2 grants; passa a apontar para o canonico e listar o conjunto
GUIDE_OLD = (
    "```sql\n"
    "-- Execute este script em CADA SQL Server que o WatcherDB vai monitorizar.\n"
    "USE master;\n"
    "GO\n"
    "CREATE LOGIN [DOMAIN\\svc_watcherdb_v33] FROM WINDOWS;\n"
    "GO\n"
    "GRANT VIEW SERVER STATE TO [DOMAIN\\svc_watcherdb_v33];\n"
    "GRANT VIEW ANY DEFINITION TO [DOMAIN\\svc_watcherdb_v33];\n"
    "GO\n"
    "\n"
    "-- Em cada base de dados que queira ser monitorizada:\n"
    "USE [master];  -- repetir para cada BD\n"
    "GO\n"
    "CREATE USER [DOMAIN\\svc_watcherdb_v33] FOR LOGIN [DOMAIN\\svc_watcherdb_v33];\n"
    "EXEC sp_addrolemember N'db_datareader', N'DOMAIN\\svc_watcherdb_v33';\n"
    "GRANT VIEW DATABASE STATE TO [DOMAIN\\svc_watcherdb_v33];\n"
    "GO\n"
    "```\n"
)
GUIDE_NEW = (
    "Execute, em **cada** SQL Server que o WatcherDB vai monitorizar, o script canonico\n"
    "`docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql` (login SQL `sql_monitoring`, ja criado) ou\n"
    "`docs/security/LEAST_PRIVILEGE_SETUP.sql` (cria um login novo; substituir os placeholders). Conjunto\n"
    "de permissoes, identico nos dois e validado em producao (2026-09-08):\n"
    "\n"
    "| Ambito | Permissao | Para que |\n"
    "|---|---|---|\n"
    "| servidor | `VIEW SERVER STATE`, `VIEW ANY DEFINITION`, `VIEW ANY DATABASE` | DMVs, metadata, enumeracao de BDs |\n"
    "| master | `EXECUTE ON sys.xp_readerrorlog`, `SHOWPLAN` | error log, planos de execucao |\n"
    "| msdb | `SELECT` em `backupset`/`backupmedia*`/`backupfile`/`sysjob*`/`sysschedules`/`sysoperators`/`syscategories`, `EXECUTE sp_help_jobactivity`, membro de `SQLAgentReaderRole` | backups e jobs |\n"
    "\n"
    "Para muitas instancias de uma vez: SSMS > View > Registered Servers > grupo com as instancias >\n"
    "New Query sobre o grupo (o script corre em todas com a sua sessao de administracao). Validar\n"
    "depois como `sql_monitoring`: a ultima query do script devolve 1 linha por instancia, tudo a 1 e\n"
    "`sysadmin = 0`. Compativel de SQL Server 2005 a 2022.\n"
)
_apply(GUIDE, [(GUIDE_OLD, GUIDE_NEW)], "GRANTS_SQL_MONITORING_INSTANCIA.sql")

# 5. referencia tecnica
_apply(
    REF,
    [(
        "|   +-- 13_ADD_PASSWORD_CHANGED_AT.sql   # Revogacao de sessao por reset (P4 A-4.7) -- obrigatorio\n",
        "|   +-- 13_ADD_PASSWORD_CHANGED_AT.sql   # Revogacao de sessao por reset (P4 A-4.7) -- obrigatorio\n"
        "|   (instancias monitorizadas: docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql -- least-privilege do sql_monitoring, 1x por instancia)\n",
    )],
    "GRANTS_SQL_MONITORING_INSTANCIA.sql",
)

print("\nLOTE CANONICO concluido. git add docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql docs/security/LEAST_PRIVILEGE_SETUP.sql database/INSTALACAO_COMPLETA_UNIFICADA.sql docs/external/standard/INSTALL_GUIDE.md docs/guides/referencia_tecnica.md")
