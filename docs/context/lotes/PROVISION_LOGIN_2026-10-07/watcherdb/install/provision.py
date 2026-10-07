"""provision-login e preflight-fleet: criar e permissionar o login do produto em todas as instancias, e provar.

Direccao do owner (2026-10-07): com as instancias registadas, o cliente escolhe entre o instalador criar e
permissionar o login automaticamente (modo auto) ou faze-lo a' mao com os scripts gerados pelo `inventory`
(modo manual). Em qualquer dos modos o login recebe SO' permissoes de leitura para recolha de monitorizacao
(docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql, via inventory.GRANTS_CORPO) e o `preflight-fleet` prova,
por ligacao REAL com o login, o que ficou feito.

As 14 condicoes do parecer de seguranca (DESIGN_INSTALADOR_V3.4_2026-10-07.md, lote C) e onde vivem aqui:
  1  identidade DBA = sessao Windows de quem corre, so' neste passo (connect_dba); nunca persistida.
  2  TLS validado: Encrypt=yes, TrustServerCertificate=no por omissao; --trust-server-cert registado.
  3  prova 'nada em disco': a password nunca passa pelo log, relatorio nem Event Log (teste com sentinela).
  4  password CSPRNG 32 chars, charset seguro para ODBC/T-SQL, 4 classes; POR INSTANCIA, partilhada so'
     entre replicas do mesmo AG; cifrada (encrypted:) no servers.json; ACL verificada pelo instalador (lote E).
  5  rotacao: comando proprio (lote posterior; registado no relatorio como pendente).
  6  SID fixo so' por ag_name (inventory.sids_por_ag); login existente NUNCA e' recriado; SID diferente = aviso.
  7  permissoes = lista fixa e versionada (GRANTS_CORPO), sem EXECUTE AS, sem ALTER TRACE.
  8  (verificado por grep no lote: jobs.py nao executa sp_update_job/sp_start_job com o login do produto).
  9  dry-run por omissao; --execute exige --confirm-count N igual ao numero de instancias.
 10  rollback: so' onde created=True (relatorio), via `rollback`; scripts por instancia ja' vem do inventory.
 11  auditoria: Event Log 2000 PROVISION_OK / 2001 SKIPPED / 2002 FAILED / 2003 ROLLBACK (sem segredos, sem SID
     completo) + relatorio JSON por instancia com erros sanitizados.
 12  inalcancaveis nao abortam; sequencial; 1 tentativa por instancia; para apos N falhas de autenticacao.
 13  preflight-fleet: ligacao real com o login, sysadmin=0 obrigatorio, permissoes esperadas presentes,
     permissoes A MAIS = FAIL, uma linha por instancia sem dados sensiveis; escreve o rollout com quem passou.
 14  manual: scripts sem password com guarda (inventory); o automatico e' opt-in explicito.
"""
from __future__ import annotations

import datetime as _dt
import getpass
import json
import os
import re
import secrets
import string
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .inventory import ServerEntry, GRANTS_CORPO, _RE_LOGIN_GRANTS, sids_por_ag
from .sqlnames import validar_identificador, dividir_lotes

EVENT_PROVISION_OK = 2000
EVENT_PROVISION_SKIPPED = 2001
EVENT_PROVISION_FAILED = 2002
EVENT_PROVISION_ROLLBACK = 2003
EVENT_PREFLIGHT = 2010

_DRIVER_OMISSAO = "ODBC Driver 17 for SQL Server"
_RE_SEGREDO = re.compile(r"(PWD|Password|UID)=[^;]*", re.IGNORECASE)

# Permissoes de servidor que o login deve ter (fn_my_permissions ao nivel SERVER) e as que NUNCA pode ter.
PERMISSOES_SERVIDOR_ESPERADAS = {"CONNECT SQL", "VIEW SERVER STATE", "VIEW ANY DEFINITION", "VIEW ANY DATABASE"}
PERMISSOES_SERVIDOR_PROIBIDAS = {"CONTROL SERVER", "ALTER ANY LOGIN", "IMPERSONATE ANY LOGIN", "ALTER SERVER STATE",
                                 "ALTER ANY DATABASE", "CREATE ANY DATABASE", "ALTER SETTINGS", "ALTER TRACE",
                                 "ADMINISTER BULK OPERATIONS", "ALTER ANY CREDENTIAL", "ALTER ANY LINKED SERVER",
                                 "ALTER ANY ENDPOINT", "UNSAFE ASSEMBLY", "EXTERNAL ACCESS ASSEMBLY", "SHUTDOWN"}
ROLES_PROIBIDAS = ("sysadmin", "securityadmin", "serveradmin", "setupadmin", "processadmin", "diskadmin",
                   "dbcreator", "bulkadmin")


def _sanitizar(msg: str) -> str:
    return _RE_SEGREDO.sub(r"\1=***", str(msg))[:400]


def _evento(event_id: int, mensagem: str, tipo: str = "Information") -> None:
    """Windows Event Log, source WatcherDB (mesmo padrao de watcherdb/licensing/startup_guard.py). Fail-safe."""
    try:
        from watcherdb.licensing.startup_guard import _write_event_log
        _write_event_log(event_id, mensagem, event_type=tipo)
    except Exception:  # noqa: BLE001 - sem pywin32/fora de Windows: segue
        pass


# ---------------------------------------------------------------- password
_ALFA = string.ascii_letters + string.digits
_SIMBOLOS = "-_"


def gerar_password(tamanho: int = 32) -> str:
    """CSPRNG, 4 classes garantidas, sem ' \" ; { } = \\ (partiriam a connection string ODBC ou o literal T-SQL)."""
    if tamanho < 16:
        raise ValueError("tamanho minimo 16")
    while True:
        corpo = [secrets.choice(_ALFA + _SIMBOLOS) for _ in range(tamanho - 4)]
        corpo += [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
                  secrets.choice(string.digits), secrets.choice(_SIMBOLOS)]
        secrets.SystemRandom().shuffle(corpo)
        pw = "".join(corpo)
        if (any(c.isupper() for c in pw) and any(c.islower() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in _SIMBOLOS for c in pw)):
            return pw


def passwords_por_instancia(entries: Iterable[ServerEntry]) -> Dict[str, str]:
    """Uma password por instancia; replicas do mesmo ag_name partilham-na (o login e' recriado em cada replica)."""
    por_ag: Dict[str, str] = {}
    out: Dict[str, str] = {}
    for e in entries:
        if e.use_windows_auth or not e.enabled:
            continue
        if e.has_alwayson and e.ag_name:
            out[e.id] = por_ag.setdefault(e.ag_name, gerar_password())
        else:
            out[e.id] = gerar_password()
    return out


# ---------------------------------------------------------------- ligacoes (injectaveis)
def _alvo(e: ServerEntry) -> str:
    srv = f"{e.host}\\{e.instance}" if e.instance and e.instance.upper() != "MSSQLSERVER" else e.host
    if e.port and e.port != 1433 and (not e.instance or e.instance.upper() == "MSSQLSERVER"):
        srv = f"{e.host},{e.port}"
    return srv


def connect_dba(servidor: str, database: str, trust_server_cert: bool):
    """Sessao Windows de quem corre o instalador (condicao 1). Autocommit: cada lote e' definitivo."""
    import pyodbc  # import tardio
    driver = os.getenv("WATCHERDB_ODBC_DRIVER", _DRIVER_OMISSAO)
    cs = (f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={database};Trusted_Connection=yes;"
          f"Encrypt=yes;TrustServerCertificate={'yes' if trust_server_cert else 'no'};APP=WatcherDB_Installer")
    return pyodbc.connect(cs, autocommit=True, timeout=10)


def connect_login(servidor: str, database: str, login: str, password: str, trust_server_cert: bool):
    """Ligacao REAL com o login do produto (preflight). A password so' vive aqui, em memoria."""
    import pyodbc  # import tardio
    driver = os.getenv("WATCHERDB_ODBC_DRIVER", _DRIVER_OMISSAO)
    cs = (f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={database};UID={login};PWD={password};"
          f"Encrypt=yes;TrustServerCertificate={'yes' if trust_server_cert else 'no'};APP=WatcherDB_Preflight")
    return pyodbc.connect(cs, autocommit=True, timeout=10)


# ---------------------------------------------------------------- modelo do relatorio
@dataclass
class ResultadoInstancia:
    id: str
    alvo: str
    ag: Optional[str] = None
    estado: str = "pendente"   # dry-run | criado | ja_existia | ja_existia_sid_diferente | adoptado | inalcancavel | falhou | saltado
    created: bool = False
    grants_ok: bool = False
    sid_prefixo: str = ""      # 4 bytes, para diagnostico sem expor o SID inteiro
    detalhe: str = ""


@dataclass
class RelatorioProvision:
    login: str
    modo: str
    dry_run: bool
    identidade: str
    tls_validado: bool
    inicio: str
    fim: str = ""
    instancias: List[ResultadoInstancia] = field(default_factory=list)
    resultado: str = "pendente"
    rotacao: str = "pendente (comando rotate-login-password em lote posterior; recomendar 90 dias)"

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------- provisionamento
def _ler_estado_login(cur, login: str) -> Tuple[bool, Optional[bytes]]:
    cur.execute("SELECT sid FROM sys.server_principals WHERE name = ?", login)
    r = cur.fetchone()
    if r is None:
        return False, None
    return True, (bytes(r[0]) if r[0] is not None else None)


def _lotes_grants(login: str) -> List[str]:
    return dividir_lotes("USE master;\n" + _RE_LOGIN_GRANTS.sub(login, GRANTS_CORPO))


def provisionar(
    entries: Iterable[ServerEntry],
    login: str,
    *,
    dry_run: bool = True,
    adopt: bool = False,
    confirm_count: Optional[int] = None,
    max_falhas_auth: int = 3,
    trust_server_cert: bool = False,
    sids: Optional[Dict[str, str]] = None,
    passwords: Optional[Dict[str, str]] = None,
    connect: Optional[Callable] = None,
    log: Callable[[str], None] = print,
    relatorio_path: Optional[Path] = None,
) -> Tuple[RelatorioProvision, Dict[str, str]]:
    """Modo automatico. Devolve (relatorio, passwords_criadas{id: password}) -- as passwords NUNCA vao ao relatorio.

    `connect(servidor, database, trust)` e' injectavel (testes); resolvido em tempo de chamada para o CLI
    poder ser testado por monkeypatch. Sequencial, 1 tentativa por instancia; falhas de autenticacao
    consecutivas >= max_falhas_auth param a execucao (lockout em massa).
    """
    connect = connect or connect_dba
    validar_identificador(login, "login")
    alvos = [e for e in entries if not e.use_windows_auth and e.enabled]
    identidade = f"{os.getenv('USERDOMAIN', '')}\\{getpass.getuser()}".strip("\\")
    rel = RelatorioProvision(login=login, modo="auto", dry_run=dry_run, identidade=identidade,
                             tls_validado=not trust_server_cert, inicio=_dt.datetime.now().isoformat(timespec="seconds"))
    log(f"provision-login | login={login} | {len(alvos)} instancias | identidade DBA={identidade} (sessao Windows, so' "
        f"neste passo, nunca persistida) | TLS {'validado' if not trust_server_cert else 'NAO validado (--trust-server-cert)'} "
        f"| {'DRY-RUN' if dry_run else 'EXECUCAO'}")
    if not dry_run:
        if confirm_count != len(alvos):
            rel.resultado = "recusado"
            log(f"  RECUSADO: --confirm-count {confirm_count} != {len(alvos)} instancias no inventario (condicao 9)")
            _gravar(rel, relatorio_path, log)
            return rel, {}
    sids = sids_por_ag(alvos, sids)
    passwords = passwords if passwords is not None else passwords_por_instancia(alvos)
    criadas: Dict[str, str] = {}
    falhas_auth = 0
    lotes = _lotes_grants(login)

    for e in alvos:
        r = ResultadoInstancia(id=e.id, alvo=_alvo(e), ag=e.ag_name if e.has_alwayson else None)
        rel.instancias.append(r)
        sid = sids.get(e.ag_name) if (e.has_alwayson and e.ag_name) else None
        try:
            conn = connect(_alvo(e), "master", trust_server_cert)
        except Exception as exc:  # noqa: BLE001
            msg = _sanitizar(exc)
            r.estado = "inalcancavel"
            r.detalhe = msg
            if "18456" in msg or "Login failed" in msg or "28000" in msg:
                falhas_auth += 1
                if falhas_auth >= max_falhas_auth:
                    log(f"  {e.id}: {falhas_auth} falhas de autenticacao consecutivas -> PARAR (condicao 12)")
                    rel.resultado = "parado_por_autenticacao"
                    break
            log(f"  {e.id}: inalcancavel ({msg[:120]})")
            continue
        falhas_auth = 0
        try:
            with conn:
                cur = conn.cursor()
                existe, sid_actual = _ler_estado_login(cur, login)
                if existe:
                    r.sid_prefixo = (sid_actual or b"")[:4].hex().upper()
                    if sid and sid_actual is not None and bytes.fromhex(sid[2:]) != sid_actual:
                        r.estado = "ja_existia_sid_diferente"
                        r.detalhe = "login existe com SID diferente do AG; nao alterado (replicas podem ficar com utilizadores orfaos)"
                        log(f"  {e.id}: {r.detalhe}")
                        _evento(EVENT_PROVISION_SKIPPED, f"PROVISION_SKIPPED instancia={e.id} motivo=sid_diferente identidade={identidade}", "Warning")
                        continue
                    if not adopt:
                        r.estado = "ja_existia"
                        r.detalhe = "login ja' existia; nada alterado (usar --adopt para aplicar so' os grants)"
                        log(f"  {e.id}: {r.detalhe}")
                        _evento(EVENT_PROVISION_SKIPPED, f"PROVISION_SKIPPED instancia={e.id} motivo=ja_existia identidade={identidade}", "Warning")
                        continue
                if dry_run:
                    r.estado = "dry-run"
                    r.detalhe = ("criaria o login" + (f" com SID fixo do AG {e.ag_name}" if sid else "") if not existe
                                 else "aplicaria os grants ao login existente (--adopt)")
                    log(f"  {e.id}: {r.detalhe}")
                    continue
                if not existe:
                    pw = passwords[e.id]
                    sid_clause = f", SID = {sid}" if sid else ""
                    cur.execute(
                        f"DECLARE @s NVARCHAR(MAX) = N'CREATE LOGIN [{login}] WITH PASSWORD = N''' + REPLACE(?, '''', '''''') "
                        f"+ N'''{sid_clause}, CHECK_POLICY = ON, CHECK_EXPIRATION = OFF, DEFAULT_DATABASE = master;'; EXEC sp_executesql @s;",
                        pw,
                    )
                    r.created = True
                    criadas[e.id] = pw
                    _, sid_novo = _ler_estado_login(cur, login)
                    r.sid_prefixo = (sid_novo or b"")[:4].hex().upper()
                for lote in lotes:
                    cur.execute(lote)
                    try:
                        while cur.nextset():
                            pass
                    except Exception:  # noqa: BLE001 - cursores sem nextset (fakes)
                        pass
                r.grants_ok = True
                r.estado = "criado" if r.created else "adoptado"
                log(f"  {e.id}: {r.estado}{' (SID fixo do AG ' + e.ag_name + ')' if sid and r.created else ''}")
                _evento(EVENT_PROVISION_OK, f"PROVISION_OK instancia={e.id} estado={r.estado} identidade={identidade} sid_prefixo={r.sid_prefixo}")
        except Exception as exc:  # noqa: BLE001 - erro do motor nesta instancia; segue para a proxima
            r.estado = "falhou"
            r.detalhe = _sanitizar(exc)
            log(f"  {e.id}: FALHOU {r.detalhe[:160]}")
            _evento(EVENT_PROVISION_FAILED, f"PROVISION_FAILED instancia={e.id} identidade={identidade} erro={r.detalhe[:200]}", "Error")
            if r.created and e.id in criadas:
                # login criado mas grants falharam: fica registado created=True para o rollback o apanhar
                pass

    if rel.resultado == "pendente":
        estados = {r.estado for r in rel.instancias}
        rel.resultado = "dry-run" if dry_run else ("ok" if estados <= {"criado", "adoptado", "ja_existia"} else "parcial")
    rel.fim = _dt.datetime.now().isoformat(timespec="seconds")
    _gravar(rel, relatorio_path, log)
    return rel, criadas


def rollback(
    relatorio: Dict,
    login: str,
    *,
    connect: Optional[Callable] = None,
    trust_server_cert: bool = False,
    log: Callable[[str], None] = print,
) -> List[Tuple[str, str]]:
    """Remove o login SO' nas instancias onde o relatorio diz created=True. Nunca toca em logins pre-existentes."""
    connect = connect or connect_dba
    validar_identificador(login, "login")
    saida: List[Tuple[str, str]] = []
    for inst in relatorio.get("instancias", []):
        if not inst.get("created"):
            continue
        try:
            with connect(inst["alvo"], "master", trust_server_cert) as conn:
                cur = conn.cursor()
                for lote in dividir_lotes(
                    f"USE msdb;\nIF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{login}') DROP USER [{login}];\nGO\n"
                    f"USE master;\nIF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{login}') DROP USER [{login}];\n"
                    f"IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{login}') DROP LOGIN [{login}];\nGO\n"
                ):
                    cur.execute(lote)
            saida.append((inst["id"], "removido"))
            _evento(EVENT_PROVISION_ROLLBACK, f"PROVISION_ROLLBACK instancia={inst['id']} login removido")
            log(f"  {inst['id']}: login removido")
        except Exception as exc:  # noqa: BLE001
            saida.append((inst["id"], f"falhou: {_sanitizar(exc)[:160]}"))
            log(f"  {inst['id']}: rollback falhou ({_sanitizar(exc)[:120]}); sessoes abertas? ver sys.dm_exec_sessions")
    return saida


# ---------------------------------------------------------------- preflight-fleet
_SQL_PREFLIGHT = """
SELECT SUSER_SNAME() AS login_efectivo,
       IS_SRVROLEMEMBER('sysadmin') AS sysadmin,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE') AS view_server_state,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW ANY DEFINITION') AS view_any_definition,
       HAS_PERMS_BY_NAME('msdb', 'DATABASE', 'CONNECT') AS msdb_connect,
       HAS_PERMS_BY_NAME('msdb.dbo.backupset', 'OBJECT', 'SELECT') AS msdb_backupset,
       HAS_PERMS_BY_NAME('msdb.dbo.sysjobs', 'OBJECT', 'SELECT') AS msdb_sysjobs,
       HAS_PERMS_BY_NAME('master.dbo.xp_readerrorlog', 'OBJECT', 'EXECUTE') AS xp_readerrorlog
"""
_SQL_PERMS_SERVIDOR = "SELECT permission_name FROM sys.fn_my_permissions(NULL, 'SERVER')"
_SQL_ROLES = "SELECT r.name FROM sys.server_role_members m JOIN sys.server_principals r ON r.principal_id = m.role_principal_id JOIN sys.server_principals p ON p.principal_id = m.member_principal_id WHERE p.name = SUSER_SNAME()"


@dataclass
class ResultadoPreflight:
    id: str
    alvo: str
    ligou: bool = False
    sysadmin: Optional[int] = None
    view_server_state: Optional[int] = None
    view_any_definition: Optional[int] = None
    msdb: Optional[int] = None
    backupset: Optional[int] = None
    sysjobs: Optional[int] = None
    errorlog: str = "n/a"       # ok | omitido | falta
    extras: List[str] = field(default_factory=list)
    passou: bool = False
    motivo: str = ""


def _classificar_erro_ligacao(msg: str) -> str:
    if "18456" in msg:
        if "State: 5" in msg or "state 5" in msg.lower():
            return "login inexistente (18456/5)"
        if "State: 8" in msg or "state 8" in msg.lower():
            return "password errada (18456/8)"
        return "autenticacao recusada (18456)"
    if "08001" in msg or "HYT00" in msg or "233" in msg or "timeout" in msg.lower():
        return "rede/instancia inalcancavel"
    if "SSL" in msg or "certificate" in msg.lower() or "certificado" in msg.lower():
        return "certificado TLS nao validado (usar --trust-server-cert so' se for deliberado)"
    return "erro de ligacao"


def preflight(
    entries: Iterable[ServerEntry],
    login: str,
    passwords: Dict[str, str],
    *,
    trust_server_cert: bool = False,
    connect: Optional[Callable] = None,
    log: Callable[[str], None] = print,
    exigir_errorlog: bool = False,
) -> List[ResultadoPreflight]:
    """Liga com o login a cada instancia (1 tentativa) e valida grants; permissoes a mais = FAIL (condicao 13)."""
    connect = connect or connect_login
    validar_identificador(login, "login")
    saida: List[ResultadoPreflight] = []
    for e in entries:
        if e.use_windows_auth or not e.enabled:
            continue
        r = ResultadoPreflight(id=e.id, alvo=_alvo(e))
        saida.append(r)
        pw = passwords.get(e.id)
        if not pw:
            r.motivo = "sem password para este id (login nao provisionado ou password nao cifrada no servers.json)"
            log(f"  {e.id:28s} | sem password"); continue
        try:
            conn = connect(_alvo(e), "master", login, pw, trust_server_cert)
        except Exception as exc:  # noqa: BLE001
            r.motivo = _classificar_erro_ligacao(str(exc))
            log(f"  {e.id:28s} | nao ligou: {r.motivo}"); continue
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(_SQL_PREFLIGHT)
                row = cur.fetchone()
                r.ligou = True
                (_, r.sysadmin, r.view_server_state, r.view_any_definition, r.msdb, r.backupset, r.sysjobs, xp) = row
                r.errorlog = "ok" if xp else ("falta" if exigir_errorlog else "omitido")
                cur.execute(_SQL_PERMS_SERVIDOR)
                perms = {str(x[0]).upper() for x in cur.fetchall()}
                cur.execute(_SQL_ROLES)
                roles = {str(x[0]).lower() for x in cur.fetchall()}
                extras = sorted((perms & PERMISSOES_SERVIDOR_PROIBIDAS) | {f"role:{x}" for x in roles if x in ROLES_PROIBIDAS})
                r.extras = extras
                faltas = [n for n, v in (("VIEW SERVER STATE", r.view_server_state), ("VIEW ANY DEFINITION", r.view_any_definition),
                                         ("msdb CONNECT", r.msdb), ("msdb backupset", r.backupset), ("msdb sysjobs", r.sysjobs)) if not v]
                if exigir_errorlog and r.errorlog == "falta":
                    faltas.append("xp_readerrorlog")
                if r.sysadmin:
                    r.motivo = "login e' sysadmin: PROIBIDO"
                elif extras:
                    r.motivo = "permissoes a mais: " + ", ".join(extras)
                elif faltas:
                    r.motivo = "em falta: " + ", ".join(faltas)
                else:
                    r.passou = True
        except Exception as exc:  # noqa: BLE001
            r.motivo = "erro na validacao: " + _sanitizar(exc)[:120]
        log(f"  {e.id:28s} | ligou {int(r.ligou)} | sysadmin {r.sysadmin} | VSS {r.view_server_state} | VAD {r.view_any_definition} "
            f"| msdb {r.msdb}/{r.backupset}/{r.sysjobs} | errorlog {r.errorlog} | extras {len(r.extras)} | {'PASSOU' if r.passou else r.motivo}")
    ok = sum(1 for r in saida if r.passou)
    _evento(EVENT_PREFLIGHT, f"PREFLIGHT_FLEET login={login} passaram={ok}/{len(saida)}", "Information" if ok == len(saida) else "Warning")
    return saida


def exit_code_preflight(res: List[ResultadoPreflight]) -> int:
    if not res:
        return 1
    if any(r.sysadmin or r.extras for r in res):
        return 1
    return 0 if all(r.passou for r in res) else 2


# ---------------------------------------------------------------- servers.json: passwords cifradas
def guardar_passwords_cifradas(servers_json: Path, passwords: Dict[str, str], cifrar: Callable[[str], str]) -> int:
    """Escreve password=encrypted:... nas entradas cujo id esta' em `passwords`. Devolve quantas mudou."""
    doc = json.loads(servers_json.read_text(encoding="utf-8-sig"))
    n = 0
    for s in doc.get("monitored_servers", []):
        pid = str(s.get("id", "")).strip().upper()
        for k, pw in passwords.items():
            if k.strip().upper() == pid:
                s["password"] = cifrar(pw)
                s["use_windows_auth"] = False
                n += 1
    servers_json.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return n


def ler_passwords_cifradas(servers_json: Path, decifrar: Callable[[str], str]) -> Dict[str, str]:
    """Le as passwords (encrypted:) do servers.json para o preflight. Placeholder/vazio = sem password."""
    doc = json.loads(servers_json.read_text(encoding="utf-8-sig"))
    out: Dict[str, str] = {}
    for s in doc.get("monitored_servers", []):
        pw = str(s.get("password", "") or "")
        if not pw or pw.startswith("@") or s.get("use_windows_auth"):
            continue
        out[str(s.get("id", "")).strip().upper()] = decifrar(pw) if pw.startswith("encrypted:") else pw
    return out


def _gravar(rel: RelatorioProvision, caminho: Optional[Path], log: Callable[[str], None]) -> None:
    if caminho is None:
        try:
            from watcherdb.core.paths import logs_dir
            caminho = logs_dir() / f"provision_{_dt.datetime.now():%Y%m%d_%H%M%S}.json"
        except Exception:  # noqa: BLE001
            return
    try:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        Path(caminho).write_text(json.dumps(rel.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  relatorio: {caminho}")
    except OSError as exc:
        log(f"  (relatorio nao gravado: {exc})")
