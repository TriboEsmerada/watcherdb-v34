"""Inventario da frota: .xlsx / .csv / .json -> servers.json canonico, rollout e scripts de grants por instancia.

Historia: nasceu como deploy/farm_inventory_parser.py (sprint install v0.2, B7). A 2026-10-07 (lote B do
instalador) passou para dentro do pacote watcherdb/install para viajar no watcherdb.exe (deploy/ nao vai no
bundle e o servidor alvo nao tem Python); o ficheiro em deploy/ ficou um shim que importa daqui. A API
antiga (parse_csv, parse_json, build_master_server, write_servers_json, main) mantem-se byte-compativel
com tests/unit/test_farm_inventory_parser.py.

Novo neste lote:
  - parse_xlsx: o cliente preenche uma folha (modelo gerado por `inventory-template`).
  - parse_servers_json: um servers.json canonico (chave monitored_servers) passa sem ser regenerado.
  - politica_windows_auth: auth_mode=windows viola a Regra de Ouro #2 -> ERRO, salvo --allow-windows-auth.
  - gerar_rollout: {"sql_auth_servers": [ids]} no formato que api/connection_pool.py:578-621 le (ids em
    maiusculas; ausente/invalido = fail-closed). Por desenho o rollout DEFINITIVO sai do preflight-fleet
    (so' quem passou a verificacao); a partir do inventario so' com --rollout-sem-verificacao explicito.
  - scripts de grants por instancia (CREATE LOGIN com placeholder guardado + grants minimos, sem EXECUTE AS)
    e de rollback, com SID fixo so' entre replicas do mesmo AG (parecer de seguranca 2026-10-07, condicao 6).
Passwords NUNCA entram no inventario nem nos scripts: placeholder @ENCRYPT_AT_INSTALL@ no servers.json e
<<PREENCHER_PASSWORD>> no script (com guarda que aborta se ficar).
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import logging
import re
import secrets
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Password placeholder — installer substitui via credential_manager
PASSWORD_PLACEHOLDER = "@ENCRYPT_AT_INSTALL@"
PLACEHOLDER_SCRIPT = "<<PREENCHER_PASSWORD>>"

# Required headers em CSV
REQUIRED_COLUMNS = {"host", "instance", "port"}
# Optional headers com defaults
DEFAULT_COLUMNS = {
    "auth_mode": "sql",
    "username": "sql_monitoring",
    "description": "",
    "environment": "production",
    "priority": 1,
    "enabled": True,
    "has_alwayson": False,
    "ag_name": None,
    "ag_listener": None,
}
COLUNAS = ("host", "instance", "port", "auth_mode", "username", "description", "environment",
           "priority", "enabled", "has_alwayson", "ag_name", "ag_listener")
AMBIENTES = ("production", "staging", "development", "test", "dr")


# ---------- Data model ------------------------------------------------------

@dataclass
class ServerEntry:
    """Single monitored server entry — matches V1 servers.json schema."""
    id: str
    host: str
    instance: str
    port: int
    description: str
    environment: str
    priority: int
    enabled: bool
    use_windows_auth: bool
    username: str
    password: str
    driver: str
    has_alwayson: bool
    ag_name: Optional[str]
    ag_listener: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseIssue:
    """Validation issue encontrado durante parse."""
    row_number: int
    field: str
    message: str
    severity: str = "warning"  # warning | error


@dataclass
class ParseResult:
    master_server: dict
    monitored_servers: List[ServerEntry] = field(default_factory=list)
    issues: List[ParseIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ---------- Parsing ---------------------------------------------------------

def _str_to_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().lower() in ("true", "1", "yes", "sim", "on", "t")


def _sanitize_hostname(host: str) -> str:
    """Strip whitespace, uppercase bare hostnames (preserve FQDN case)."""
    h = host.strip()
    return h


def _build_id(host: str, instance: str) -> str:
    """Construct unique server ID matching V1 convention: HOST_INSTANCE."""
    # Strip domain if FQDN (V1 convention uses short hostname em id)
    short = host.split(".")[0].upper()
    inst = instance.strip().upper() if instance else "DEFAULT"
    return f"{short}_{inst}"


def _limpar_texto(val: Any) -> str:
    """Texto livre (description, ag_name...) que vai parar a comentarios SQL: sem quebras de linha nem '--'."""
    s = "" if val is None else str(val)
    return s.replace("\r", " ").replace("\n", " ").replace("--", "- ").replace("*/", "* /").strip()


def _parse_row(row: dict, row_number: int, master_username: str) -> tuple:
    """Parse CSV row into ServerEntry. Returns (entry | None, issues)."""
    issues = []

    # Required field checks
    host = str(row.get("host", "") or "").strip()
    if not host:
        issues.append(ParseIssue(row_number, "host", "host is required", "error"))
        return None, issues

    instance = str(row.get("instance", "") or "MSSQLSERVER").strip()
    try:
        port_raw = row.get("port", 1433)
        if isinstance(port_raw, float) and port_raw.is_integer():   # celulas numericas do xlsx: 1433.0
            port_raw = int(port_raw)
        port = int(str(port_raw).strip() or 1433)
        if not (1 <= port <= 65535):
            raise ValueError("port out of range")
    except ValueError:
        issues.append(ParseIssue(row_number, "port", f"invalid port: {row.get('port')}", "error"))
        return None, issues

    auth_mode_raw = str(row.get("auth_mode", "sql") or "sql").strip().lower()
    if auth_mode_raw not in ("sql", "windows"):
        issues.append(ParseIssue(
            row_number, "auth_mode",
            f"auth_mode must be 'sql' or 'windows' (got '{auth_mode_raw}'), assuming 'sql'",
            "warning",
        ))
        auth_mode_raw = "sql"
    use_windows_auth = auth_mode_raw == "windows"

    # If SQL auth, username required (default = login do produto)
    username = str(row.get("username", "") or master_username or DEFAULT_COLUMNS["username"]).strip()
    if not use_windows_auth and not username:
        issues.append(ParseIssue(row_number, "username", "username required for sql auth", "error"))
        return None, issues

    # Defaults for optional fields
    description = _limpar_texto(row.get("description", ""))
    environment = str(row.get("environment", "production") or "production").strip().lower()
    if environment not in AMBIENTES:
        issues.append(ParseIssue(
            row_number, "environment",
            f"non-standard environment '{environment}' (expected production/staging/dev/test/dr)",
            "warning",
        ))

    try:
        prio_raw = row.get("priority", 1)
        if isinstance(prio_raw, float) and prio_raw.is_integer():
            prio_raw = int(prio_raw)
        priority = int(str(prio_raw).strip() or 1)
    except ValueError:
        priority = 1
        issues.append(ParseIssue(row_number, "priority", "invalid priority, defaulting to 1", "warning"))

    enabled = _str_to_bool(row.get("enabled", True))
    has_alwayson = _str_to_bool(row.get("has_alwayson", False))
    ag_name = _limpar_texto(row.get("ag_name", "") or "") or None
    ag_listener = _limpar_texto(row.get("ag_listener", "") or "") or None

    if has_alwayson and not ag_name:
        issues.append(ParseIssue(
            row_number, "ag_name",
            "has_alwayson=true but ag_name empty",
            "warning",
        ))

    entry = ServerEntry(
        id=_build_id(host, instance),
        host=_sanitize_hostname(host),
        instance=instance,
        port=port,
        description=description,
        environment=environment,
        priority=priority,
        enabled=enabled,
        use_windows_auth=use_windows_auth,
        username=username if not use_windows_auth else "",
        password="" if use_windows_auth else PASSWORD_PLACEHOLDER,
        driver="SQL Server",
        has_alwayson=has_alwayson,
        ag_name=ag_name,
        ag_listener=ag_listener,
    )
    return entry, issues


def _validate_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    """Optional TCP reachability check (best-effort, non-blocking)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, socket.gaierror, OSError):
        return False


def _tcp_issue(entry: ServerEntry, row_idx: int, validate_tcp: bool) -> Optional[ParseIssue]:
    if validate_tcp and not _validate_tcp(entry.host, entry.port):
        return ParseIssue(row_idx, "tcp", f"TCP unreachable: {entry.host}:{entry.port}", "warning")
    return None


def parse_csv(
    input_path: Path,
    master_username: str,
    *,
    skip_empty_rows: bool = True,
    validate_tcp: bool = False,
) -> tuple:
    """Parse CSV file. Returns (list[ServerEntry], list[ParseIssue])."""
    entries = []
    issues = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            issues.append(ParseIssue(0, "header", "empty CSV or missing header", "error"))
            return entries, issues

        missing_required = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_required:
            issues.append(ParseIssue(
                0, "header",
                f"missing required columns: {sorted(missing_required)}",
                "error",
            ))
            return entries, issues

        for row_idx, row in enumerate(reader, start=2):  # +1 header, +1 1-based
            if skip_empty_rows and not any(v and v.strip() for v in row.values()):
                continue
            entry, row_issues = _parse_row(row, row_idx, master_username)
            issues.extend(row_issues)
            if entry is None:
                continue
            t = _tcp_issue(entry, row_idx, validate_tcp)
            if t:
                issues.append(t)
            entries.append(entry)

    return entries, issues


def parse_json(
    input_path: Path,
    master_username: str,
    *,
    validate_tcp: bool = False,
) -> tuple:
    """Parse JSON array file."""
    entries = []
    issues = []

    try:
        data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        issues.append(ParseIssue(0, "json", f"invalid JSON: {e}", "error"))
        return entries, issues

    if not isinstance(data, list):
        issues.append(ParseIssue(0, "json", "expected top-level JSON array", "error"))
        return entries, issues

    for row_idx, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            issues.append(ParseIssue(row_idx, "json", "row is not an object", "error"))
            continue
        entry, row_issues = _parse_row(row, row_idx, master_username)
        issues.extend(row_issues)
        if entry is None:
            continue
        t = _tcp_issue(entry, row_idx, validate_tcp)
        if t:
            issues.append(t)
        entries.append(entry)

    return entries, issues


# ---------- 2026-10-07: xlsx e servers.json canonico -------------------------

def _normalizar_cabecalho(v: Any) -> str:
    return re.sub(r"\s+", "_", str(v or "").strip().lower())


def _celula(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def parse_xlsx(
    input_path: Path,
    master_username: str,
    *,
    validate_tcp: bool = False,
    folha: Optional[str] = None,
) -> tuple:
    """Le a folha 'Inventario' (ou a primeira) de um .xlsx com as 12 colunas do modelo.

    openpyxl em read_only + data_only: formulas sem valor em cache dao None -> erro claro na linha.
    """
    entries: List[ServerEntry] = []
    issues: List[ParseIssue] = []
    try:
        from openpyxl import load_workbook  # import tardio: so' quando ha' xlsx
    except ImportError:
        issues.append(ParseIssue(0, "xlsx", "openpyxl nao esta instalado neste pacote", "error"))
        return entries, issues
    try:
        wb = load_workbook(filename=str(input_path), read_only=True, data_only=True)
        # 2.a leitura com as formulas (data_only=False): uma formula sem valor em cache vem None na 1.a leitura
        # e seria reportada como 'host is required'; assim damos a causa certa.
        wb_f = load_workbook(filename=str(input_path), read_only=True, data_only=False)
    except Exception as e:  # noqa: BLE001 - ficheiro corrompido/zip invalido
        issues.append(ParseIssue(0, "xlsx", f"nao foi possivel abrir o xlsx: {e}", "error"))
        return entries, issues
    try:
        nomes = wb.sheetnames
        alvo = folha or next((n for n in nomes if n.strip().lower() == "inventario"), nomes[0])
        ws = wb[alvo]
        linhas = ws.iter_rows(values_only=True)
        linhas_f = wb_f[alvo].iter_rows(values_only=True)
        try:
            cab = next(linhas)
            next(linhas_f, None)
        except StopIteration:
            issues.append(ParseIssue(0, "header", "folha vazia", "error"))
            return entries, issues
        cols = [_normalizar_cabecalho(c) for c in cab]
        missing_required = REQUIRED_COLUMNS - set(cols)
        if missing_required:
            issues.append(ParseIssue(0, "header", f"missing required columns: {sorted(missing_required)}", "error"))
            return entries, issues
        for row_idx, valores in enumerate(linhas, start=2):
            formulas = next(linhas_f, ()) or ()
            if not any(v not in (None, "") for v in valores) and not any(v not in (None, "") for v in formulas):
                continue
            row = {c: _celula(v) for c, v in zip(cols, valores) if c}
            if any(v is None for v in valores) and any(isinstance(f, str) and f.startswith("=") for f in formulas):
                issues.append(ParseIssue(row_idx, "formula", "celula com formula sem valor calculado: abre e grava o ficheiro no Excel, ou escreve o valor", "error"))
                continue
            if not any(v not in (None, "") for v in valores):
                continue
            entry, row_issues = _parse_row(row, row_idx, master_username)
            issues.extend(row_issues)
            if entry is None:
                continue
            t = _tcp_issue(entry, row_idx, validate_tcp)
            if t:
                issues.append(t)
            entries.append(entry)
    finally:
        wb.close()
        wb_f.close()
    return entries, issues


def parse_servers_json(input_path: Path) -> tuple:
    """servers.json canonico (chave monitored_servers): passthrough. Devolve (entries, issues, master_server|None).

    Campos extra (databases, databases_discovered_at...) sao preservados no write via extra_campos.
    """
    issues: List[ParseIssue] = []
    try:
        doc = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        return [], [ParseIssue(0, "json", f"invalid JSON: {e}", "error")], None
    if not isinstance(doc, dict) or "monitored_servers" not in doc:
        return [], [ParseIssue(0, "json", "nao e' um servers.json canonico (sem monitored_servers)", "error")], None
    entries: List[ServerEntry] = []
    for i, s in enumerate(doc.get("monitored_servers") or [], start=1):
        try:
            entries.append(ServerEntry(
                id=str(s.get("id") or _build_id(s.get("host", ""), s.get("instance", ""))),
                host=str(s.get("host", "")), instance=str(s.get("instance", "") or "MSSQLSERVER"),
                port=int(s.get("port") or 1433), description=str(s.get("description", "") or ""),
                environment=str(s.get("environment", "production") or "production"),
                priority=int(s.get("priority") or 1), enabled=bool(s.get("enabled", True)),
                use_windows_auth=bool(s.get("use_windows_auth", False)),
                username=str(s.get("username", "") or ""), password=str(s.get("password", "") or ""),
                driver=str(s.get("driver", "SQL Server") or "SQL Server"),
                has_alwayson=bool(s.get("has_alwayson", False)),
                ag_name=(s.get("ag_name") or None), ag_listener=(s.get("ag_listener") or None),
            ))
        except (TypeError, ValueError) as e:
            issues.append(ParseIssue(i, "entry", f"entrada invalida: {e}", "error"))
    return entries, issues, doc.get("master_server")


def ler_inventario(input_path: Path, master_username: str, *, validate_tcp: bool = False) -> tuple:
    """Detecta o formato pela extensao e conteudo. Devolve (entries, issues, master_server|None, formato)."""
    suffix = input_path.suffix.lower()
    if suffix == ".xlsx":
        e, i = parse_xlsx(input_path, master_username, validate_tcp=validate_tcp)
        return e, i, None, "xlsx"
    if suffix == ".csv":
        e, i = parse_csv(input_path, master_username, validate_tcp=validate_tcp)
        return e, i, None, "csv"
    if suffix == ".json":
        try:
            doc = json.loads(input_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as ex:
            return [], [ParseIssue(0, "json", f"invalid JSON: {ex}", "error")], None, "json"
        if isinstance(doc, dict) and "monitored_servers" in doc:
            e, i, m = parse_servers_json(input_path)
            return e, i, m, "servers.json"
        e, i = parse_json(input_path, master_username, validate_tcp=validate_tcp)
        return e, i, None, "json"
    return [], [ParseIssue(0, "input", f"formato nao suportado '{suffix}' (usar .xlsx, .csv ou .json)", "error")], None, suffix


def politica_windows_auth(entries: Iterable[ServerEntry], allow_windows_auth: bool) -> List[ParseIssue]:
    """Regra de Ouro #2: o produto nao liga por Trusted_Connection. Linhas windows = erro, salvo opt-in explicito."""
    if allow_windows_auth:
        return []
    return [ParseIssue(0, "auth_mode",
                       f"{e.id}: auth_mode=windows viola a Regra de Ouro #2 (o produto liga so' com o seu login SQL); "
                       f"usa auth_mode=sql ou --allow-windows-auth de forma deliberada", "error")
            for e in entries if e.use_windows_auth]


# ---------- Master server generation ---------------------------------------

def build_master_server(
    host: str,
    *,
    instance: str = "MSSQLSERVER",
    port: int = 1433,
    database: str = "WatcherDB_Intelligence",
    description: str = "WatcherDB Intelligence master",
    environment: str = "production",
    use_windows_auth: bool = False,
    username: str = "sql_monitoring",
) -> dict:
    """Build master_server block matching V1 schema."""
    server_str = f"{host}\\{instance}" if instance and instance.upper() != "MSSQLSERVER" else host
    return {
        "server": server_str,
        "database": database,
        "host": host,
        "instance": instance,
        "port": port,
        "description": description,
        "environment": environment,
        "priority": 1,
        "use_windows_auth": use_windows_auth,
        "driver": "SQL Server",
        "username": username if not use_windows_auth else "",
        "password": "" if use_windows_auth else PASSWORD_PLACEHOLDER,
    }


# ---------- Output writers --------------------------------------------------

def write_servers_json(
    output_path: Path,
    master_server: dict,
    monitored: List[ServerEntry],
) -> None:
    """Write servers.json canonical format."""
    doc = {
        "master_server": master_server,
        "monitored_servers": [e.to_dict() for e in monitored],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def gerar_rollout(entries: Iterable[ServerEntry], verificados: Optional[Iterable[str]] = None) -> dict:
    """{"sql_auth_servers": [...]} como api/connection_pool.py:578-621 le: ids em MAIUSCULAS, so' SQL auth e enabled.

    Com `verificados` (ids que passaram o preflight-fleet) entram so' esses; e' o caminho definitivo.
    """
    ids = sorted({e.id.strip().upper() for e in entries if not e.use_windows_auth and e.enabled})
    if verificados is not None:
        ok = {v.strip().upper() for v in verificados}
        ids = [i for i in ids if i in ok]
    return {"sql_auth_servers": ids,
            "_gerado": {"em": _dt.datetime.now().isoformat(timespec="seconds"),
                        "origem": "preflight-fleet" if verificados is not None else "inventario (sem verificacao)"}}


def write_rollout_json(output_path: Path, rollout: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rollout, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- 2026-10-07: scripts de grants por instancia ----------------------

LOGIN_CANONICO_GRANTS = "sql_monitoring"

# Corpo de docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql (2026-09-08) sem o cabecalho de comentarios,
# sem a guarda 'login nao existe' (aqui o login e' criado antes) e sem o bloco final de verificacao com
# EXECUTE AS LOGIN (Regra de Ouro #2 proibe impersonation; a verificacao e' o preflight-fleet, por ligacao
# real). tests/unit/test_inventory_cli_20261007.py prova que este texto continua igual ao do ficheiro.
GRANTS_CORPO = """-- ---- servidor -----------------------------------------------------------------
GRANT VIEW SERVER STATE   TO [sql_monitoring];
GRANT VIEW ANY DEFINITION TO [sql_monitoring];
GRANT VIEW ANY DATABASE   TO [sql_monitoring];

-- ---- master: user + xp_readerrorlog + SHOWPLAN (GAP 1 e GAP 3 do audit 2026-08-20) ----
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'sql_monitoring')
    CREATE USER [sql_monitoring] FOR LOGIN [sql_monitoring];
GRANT EXECUTE ON sys.xp_readerrorlog TO [sql_monitoring];
GRANT SHOWPLAN TO [sql_monitoring];
GO

-- ---- msdb: backups, jobs, SQLAgentReaderRole -----------------------------------
USE msdb;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'sql_monitoring')
    CREATE USER [sql_monitoring] FOR LOGIN [sql_monitoring];
GRANT SELECT ON dbo.backupset          TO [sql_monitoring];
GRANT SELECT ON dbo.backupmediafamily  TO [sql_monitoring];
GRANT SELECT ON dbo.backupmediaset     TO [sql_monitoring];
GRANT SELECT ON dbo.backupfile         TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobs            TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobhistory      TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobsteps        TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobschedules    TO [sql_monitoring];
GRANT SELECT ON dbo.sysjobservers      TO [sql_monitoring];
GRANT SELECT ON dbo.sysoperators       TO [sql_monitoring];
GRANT SELECT ON dbo.sysschedules       TO [sql_monitoring];
GRANT SELECT ON dbo.syscategories      TO [sql_monitoring];
GRANT EXECUTE ON dbo.sp_help_jobactivity TO [sql_monitoring];
IF NOT EXISTS (
    SELECT 1
    FROM sys.database_role_members rm
    JOIN sys.database_principals r ON r.principal_id = rm.role_principal_id
    JOIN sys.database_principals m ON m.principal_id = rm.member_principal_id
    WHERE r.name = N'SQLAgentReaderRole' AND m.name = N'sql_monitoring'
)
    -- sp_addrolemember e' aceite em 2005..2022; ALTER ROLE ... ADD MEMBER so' existe a partir de 2012
    -- e o PARSER rejeita o lote inteiro em 2008/2005 (erro de sintaxe medido em 1 instancia, 2026-09-08).
    EXEC sp_addrolemember N'SQLAgentReaderRole', N'sql_monitoring';
GO
"""

_RE_LOGIN_GRANTS = re.compile(r"(?<![A-Za-z0-9])sql_monitoring(?![A-Za-z0-9])")


def novo_sid() -> str:
    """SID aleatorio de 16 bytes para CREATE LOGIN ... WITH SID (so' entre replicas do mesmo AG)."""
    return "0x" + secrets.token_bytes(16).hex().upper()


def sids_por_ag(entries: Iterable[ServerEntry], existentes: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Um SID por ag_name (reutiliza os ja' conhecidos). Instancias sem AG nao recebem SID fixo."""
    sids = dict(existentes or {})
    for e in entries:
        if e.has_alwayson and e.ag_name and e.ag_name not in sids:
            sids[e.ag_name] = novo_sid()
    return sids


def _cabecalho(e: ServerEntry, login: str, sid: Optional[str], rollback: bool) -> str:
    alvo = f"{e.host}\\{e.instance}" if e.instance.upper() != "MSSQLSERVER" else e.host
    return (f"-- {'ROLLBACK' if rollback else 'GRANTS'} do login do WatcherDB em {e.id} ({alvo})"
            f"{' | AG ' + e.ag_name if e.ag_name else ''}\n"
            f"-- Gerado por watcherdb.exe inventory em {_dt.datetime.now():%Y-%m-%d %H:%M}\n"
            f"-- IDENTIDADE: DBA da instancia (sysadmin ou ALTER ANY LOGIN + CONTROL SERVER). "
            f"Nunca a conta do servico.\n"
            f"-- AMBITO: so' esta instancia. IMPACTO: {'remove' if rollback else 'cria'} o login [{login}] "
            f"{'e os seus utilizadores em master/msdb' if rollback else 'e concede permissoes SO DE LEITURA para recolha de monitorizacao'}.\n"
            f"-- O login NUNCA altera dados do cliente: VIEW SERVER STATE, VIEW ANY DEFINITION, leitura de msdb e\n"
            f"-- SQLAgentReaderRole, EXECUTE xp_readerrorlog (ler o log de erros), SHOWPLAN, sp_help_jobactivity.\n"
            f"-- SID {'fixo (replicas do mesmo AG partilham-no para o failover nao deixar utilizadores orfaos)' if sid else 'gerado pelo SQL Server (instancia sem AG)'}.\n"
            f"-- ROLLBACK: ficheiro rollback_{e.id}.sql. Verificacao: watcherdb.exe preflight-fleet (ligacao real com o login, sem impersonation).\n")


def gerar_script_grants(e: ServerEntry, login: str, sid: Optional[str]) -> str:
    """Script por instancia: CREATE LOGIN (placeholder guardado) + grants minimos. Sem password, sem EXECUTE AS."""
    sid_clause = f", SID = {sid}" if sid else ""
    corpo = _RE_LOGIN_GRANTS.sub(login, GRANTS_CORPO)
    return (
        _cabecalho(e, login, sid, rollback=False)
        + "SET NOCOUNT ON;\n"
        + "USE master;\n"
        + f"DECLARE @pw NVARCHAR(128) = N'{PLACEHOLDER_SCRIPT}';   -- o DBA preenche; nunca gravar o ficheiro com a password\n"
        + "IF @pw LIKE N'<<%' BEGIN RAISERROR('Password por preencher: edita @pw antes de correr', 16, 1); RETURN; END\n"
        + f"IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{login}')\n"
        + "BEGIN\n"
        + f"    DECLARE @sql NVARCHAR(MAX) = N'CREATE LOGIN [{login}] WITH PASSWORD = N''' + REPLACE(@pw, '''', '''''') + N'''{sid_clause}, CHECK_POLICY = ON, CHECK_EXPIRATION = OFF, DEFAULT_DATABASE = master;';\n"
        + "    EXEC sp_executesql @sql;\n"
        + f"    PRINT '{login}: login criado';\n"
        + "END\n"
        + "ELSE\n"
        + f"    PRINT '{login}: login ja existia (SID e password NAO alterados)';\n"
        + "GO\n"
        + "USE master;\n"
        + corpo
    )


def gerar_script_rollback(e: ServerEntry, login: str) -> str:
    return (
        _cabecalho(e, login, None, rollback=True)
        + "SET NOCOUNT ON;\n"
        + "USE msdb;\n"
        + f"IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{login}') DROP USER [{login}];\n"
        + "GO\n"
        + "USE master;\n"
        + f"IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{login}') DROP USER [{login}];\n"
        + f"IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{login}')\n"
        + "BEGIN\n"
        + f"    -- sessoes abertas fazem o DROP LOGIN falhar; verificar com sys.dm_exec_sessions WHERE login_name = N'{login}' (nao matar sessoes automaticamente)\n"
        + f"    DROP LOGIN [{login}];\n"
        + f"    PRINT '{login}: login removido';\n"
        + "END\n"
        + "GO\n"
    )


def escrever_scripts_grants(entries: Iterable[ServerEntry], login: str, out_dir: Path,
                            sids: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Um grants_<id>.sql e um rollback_<id>.sql por instancia SQL-auth; sids.json e INDICE.md com hashes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = list(entries)
    sids = sids_por_ag(entries, sids)
    indice = []
    for e in entries:
        if e.use_windows_auth or not e.enabled:
            continue
        sid = sids.get(e.ag_name) if (e.has_alwayson and e.ag_name) else None
        g = gerar_script_grants(e, login, sid)
        r = gerar_script_rollback(e, login)
        (out_dir / f"grants_{e.id}.sql").write_text(g, encoding="utf-8")
        (out_dir / f"rollback_{e.id}.sql").write_text(r, encoding="utf-8")
        indice.append({"id": e.id, "host": e.host, "instance": e.instance, "ag": e.ag_name,
                       "sid_fixo": bool(sid),
                       "grants_sha256": hashlib.sha256(g.encode("utf-8")).hexdigest(),
                       "rollback_sha256": hashlib.sha256(r.encode("utf-8")).hexdigest()})
    (out_dir / "sids.json").write_text(json.dumps(sids, indent=2), encoding="utf-8")
    linhas = ["# Scripts de grants por instancia", "",
              f"Login: `{login}` | gerado em {_dt.datetime.now():%Y-%m-%d %H:%M} | {len(indice)} instancias", "",
              "Correr cada `grants_<id>.sql` NA instancia respectiva, com identidade DBA, depois de preencher `@pw`",
              "(a mesma password em todas as replicas do mesmo AG). O hash prova que o script revisto e' o que correu.", "",
              "| id | host | instancia | AG | SID fixo | sha256 grants |", "|---|---|---|---|---|---|"]
    for i in indice:
        linhas.append(f"| {i['id']} | {i['host']} | {i['instance']} | {i['ag'] or ''} | {'sim' if i['sid_fixo'] else ''} | {i['grants_sha256'][:16]} |")
    (out_dir / "INDICE.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return {"instancias": indice, "sids": sids, "pasta": str(out_dir)}


# ---------- 2026-10-07: modelo .xlsx ----------------------------------------

def gerar_modelo_xlsx(output_path: Path) -> Path:
    """Folha 'Inventario' com as 12 colunas, uma linha de exemplo e validacao de dados; folha 'Instrucoes'."""
    from openpyxl import Workbook  # import tardio
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario"
    ws.append(list(COLUNAS))
    ws.append(["SQL01.exemplo.local", "MSSQLSERVER", 1433, "sql", "", "Core PRD", "production", 1, True, False, "", ""])
    dv_auth = DataValidation(type="list", formula1='"sql,windows"', allow_blank=True)
    dv_env = DataValidation(type="list", formula1='"production,staging,development,test,dr"', allow_blank=True)
    dv_bool = DataValidation(type="list", formula1='"true,false"', allow_blank=True)
    for dv, col in ((dv_auth, "D"), (dv_env, "G"), (dv_bool, "I"), (dv_bool, "J")):
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}1000")
    ws.freeze_panes = "A2"
    inst = wb.create_sheet("Instrucoes")
    for linha in (
        ("Inventario das instancias SQL Server a monitorizar pelo WatcherDB",),
        ("Uma linha por instancia. Colunas obrigatorias: host, instance, port. instance = MSSQLSERVER para a omissao.",),
        ("auth_mode: sql (o produto liga com o seu login, so' leitura). windows viola a Regra de Ouro #2 e e' recusado.",),
        ("username: deixar vazio para usar o login do produto escolhido na instalacao.",),
        ("environment: production | staging | development | test | dr. priority: 1 (alta) a 5.",),
        ("has_alwayson/ag_name/ag_listener: so' para instancias em Availability Group; listar TODAS as replicas, nao so' o listener.",),
        ("NUNCA escrever passwords neste ficheiro. O instalador pede-as e cifra-as.",),
        ("Gravar como .xlsx e entregar: watcherdb.exe inventory --input <ficheiro>.xlsx",),
    ):
        inst.append(linha)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    return output_path


# ---------- CLI antigo (mantido para deploy/farm_inventory_parser.py) --------

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="SQL Server farm inventory -> servers.json canonical.")
    parser.add_argument("--input", type=Path, required=True, help="CSV, JSON ou XLSX com farm inventory")
    parser.add_argument("--output", type=Path, default=Path("servers.json"))
    parser.add_argument("--master-host", required=True, help="Hostname do SQL Server com a base do WatcherDB")
    parser.add_argument("--master-instance", default="MSSQLSERVER")
    parser.add_argument("--master-port", type=int, default=1433)
    parser.add_argument("--master-db", default="WatcherDB_Intelligence")
    parser.add_argument("--master-username", default="sql_monitoring")
    parser.add_argument("--master-windows-auth", action="store_true")
    parser.add_argument("--master-description", default="WatcherDB Intelligence master")
    parser.add_argument("--validate-tcp", action="store_true", help="Testar TCP reachability por entry")
    parser.add_argument("--skip-empty-rows", action="store_true", default=True)
    parser.add_argument("--strict", action="store_true", help="Fail if any row has warnings (default: errors only)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 2

    entries, issues, _master_doc, formato = ler_inventario(args.input, args.master_username, validate_tcp=args.validate_tcp)
    if formato not in ("csv", "json", "xlsx", "servers.json"):
        print(f"ERROR: unsupported input format '{formato}' (use .csv, .json ou .xlsx)", file=sys.stderr)
        return 2

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    for issue in issues:
        prefix = "ERROR" if issue.severity == "error" else "WARN"
        print(f"{prefix} [row {issue.row_number}] {issue.field}: {issue.message}", file=sys.stderr)
    if errors:
        print(f"\nFAIL: {len(errors)} error(s), {len(warnings)} warning(s). Fix errors and re-run.", file=sys.stderr)
        return 1
    if args.strict and warnings:
        print(f"\nFAIL (strict mode): {len(warnings)} warning(s). Re-run without --strict to allow.", file=sys.stderr)
        return 1
    if not entries:
        print("ERROR: no valid server entries parsed", file=sys.stderr)
        return 1

    master = build_master_server(
        args.master_host,
        instance=args.master_instance,
        port=args.master_port,
        database=args.master_db,
        description=args.master_description,
        use_windows_auth=args.master_windows_auth,
        username=args.master_username,
    )
    write_servers_json(args.output, master, entries)

    print(f"\nWrote {args.output} ({len(entries)} monitored servers)")
    print(f"  warnings: {len(warnings)}")
    print(f"  master:   {master['server']} / {master['database']}")
    print(f"\nNote: passwords sao placeholder '{PASSWORD_PLACEHOLDER}' — installer wizard substitui.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
