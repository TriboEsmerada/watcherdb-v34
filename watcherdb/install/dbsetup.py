"""setup-database: cria a base (se faltar), o utilizador do login e aplica o schema do produto.

IDENTIDADE: a sessao Windows de quem corre o instalador (DBA com direitos de DDL). Decisao do owner
2026-10-07: Windows Auth e' aceite SO' neste passo de provisionamento, nunca persistida -- e' a identidade
do cliente, com a auditoria do cliente. O produto em si continua a ligar so' com o seu login SQL (Regra de
Ouro #2). Nenhuma credencial entra em disco, em log ou no relatorio.

ORDEM (achado do deploy-architect): o canonico nao cria o login nem o utilizador, mas faz 19 GRANT ao login;
numa base nova sem o utilizador esses GRANT falham. Logo: 1 base -> 2 utilizador do login -> 3 schema.
Se o login ainda nao existir no servidor, o passo 2 avisa e o schema para no primeiro GRANT (modo estrito),
que e' o comportamento correcto: o antigo setup_database.ps1 engolia este erro e imprimia [OK].

ESTRITO por omissao: o primeiro erro para a execucao e identifica script e lote. --continue-on-error e'
explicito. --dry-run (omissao) nao liga a nada: mostra o plano por script com o numero de lotes e de
substituicoes.
"""
from __future__ import annotations

import datetime as _dt
import getpass
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .sqlnames import (
    SCRIPTS, NOME_BASE_CANONICO, LOGIN_CANONICO,
    validar_identificador, substituir_nomes, restos_canonicos, dividir_lotes,
)

_DRIVER_OMISSAO = "ODBC Driver 17 for SQL Server"
_RE_SEGREDO = re.compile(r"(PWD|Password|UID)=[^;]*", re.IGNORECASE)


def _sanitizar(msg: str) -> str:
    return _RE_SEGREDO.sub(r"\1=***", str(msg))[:400]


def localizar_sql_dir(override: Optional[Path] = None) -> Path:
    """database/ do repo em dev; _internal/database no bundle (build.py COPY_DIRS)."""
    if override:
        return Path(override)
    from watcherdb.core.paths import project_root
    return project_root() / "database"


def _ler_sql(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8-sig")


@dataclass
class PassoScript:
    script: str
    existe: bool
    lotes: int = 0
    subst_base: int = 0
    subst_login: int = 0
    lotes_ok: int = 0
    estado: str = "pendente"   # pendente | dry-run | ok | falhou | saltado
    erro: str = ""


@dataclass
class Relatorio:
    servidor: str
    base: str
    login: str
    identidade: str
    dry_run: bool
    inicio: str
    fim: str = ""
    base_criada: Optional[bool] = None
    utilizador_criado: Optional[bool] = None
    login_existe: Optional[bool] = None
    passos: List[PassoScript] = field(default_factory=list)
    resultado: str = "pendente"

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


def planear(sql_dir: Path, base: str, login: str) -> List[PassoScript]:
    """Le cada script, substitui em memoria e conta lotes e substituicoes. Nao toca em nenhuma base."""
    validar_identificador(base, "nome da base")
    validar_identificador(login, "login")
    passos: List[PassoScript] = []
    for nome in SCRIPTS:
        caminho = sql_dir / nome
        if not caminho.exists():
            passos.append(PassoScript(script=nome, existe=False, estado="saltado", erro="ficheiro nao encontrado"))
            continue
        sql, nb, nl = substituir_nomes(_ler_sql(caminho), base, login)
        restos = restos_canonicos(sql, base, login)
        if restos:
            raise RuntimeError(f"{nome}: ficaram {len(restos)} ocorrencias do nome canonico apos substituir "
                               f"(primeira: linha {restos[0][0]}: {restos[0][1]})")
        passos.append(PassoScript(script=nome, existe=True, lotes=len(dividir_lotes(sql)),
                                  subst_base=nb, subst_login=nl, estado="dry-run"))
    return passos


def _connect_windows_auth(servidor: str, base: str, trust_server_cert: bool):
    """Ligacao com a sessao Windows de quem corre (so' neste passo). TLS validado por omissao."""
    import pyodbc  # import tardio: so' quando se executa de verdade
    driver = os.getenv("WATCHERDB_ODBC_DRIVER", _DRIVER_OMISSAO)
    cs = (f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base};Trusted_Connection=yes;"
          f"Encrypt=yes;TrustServerCertificate={'yes' if trust_server_cert else 'no'};"
          f"APP=WatcherDB_Installer")
    conn = pyodbc.connect(cs, autocommit=True, timeout=15)
    return conn


def executar(
    servidor: str,
    base: str,
    login: str,
    *,
    sql_dir: Optional[Path] = None,
    dry_run: bool = True,
    continue_on_error: bool = False,
    trust_server_cert: bool = False,
    connect: Optional[Callable] = None,
    log: Callable[[str], None] = print,
    relatorio_path: Optional[Path] = None,
) -> Relatorio:
    """Executa (ou planeia) o setup. `connect(servidor, base, trust)` e' injectavel para testes."""
    validar_identificador(base, "nome da base")
    validar_identificador(login, "login")
    sql_dir = localizar_sql_dir(sql_dir)
    identidade = f"{os.getenv('USERDOMAIN', '')}\\{getpass.getuser()}".strip("\\")
    rel = Relatorio(servidor=servidor, base=base, login=login, identidade=identidade, dry_run=dry_run,
                    inicio=_dt.datetime.now().isoformat(timespec="seconds"))
    log(f"setup-database | servidor={servidor} base={base} login={login} | identidade={identidade} "
        f"(sessao Windows, so' neste passo, nunca persistida) | {'DRY-RUN' if dry_run else 'EXECUCAO'}")
    if base != NOME_BASE_CANONICO or login != LOGIN_CANONICO:
        log(f"  nomes substituidos em memoria: {NOME_BASE_CANONICO} -> {base}, {LOGIN_CANONICO} -> {login} "
            f"(o ficheiro canonico nao e' alterado)")

    rel.passos = planear(sql_dir, base, login)
    for p in rel.passos:
        log(f"  {p.script:45s} {'' if p.existe else 'SALTADO (nao encontrado)':25s} lotes={p.lotes:4d} "
            f"subst base={p.subst_base} login={p.subst_login}")
    if dry_run:
        rel.resultado = "dry-run"
        rel.fim = _dt.datetime.now().isoformat(timespec="seconds")
        _gravar(rel, relatorio_path, log)
        return rel

    connect = connect or _connect_windows_auth
    try:
        # 1. base
        with connect(servidor, "master", trust_server_cert) as c:
            cur = c.cursor()
            cur.execute("SELECT DB_ID(?)", base)
            existia = cur.fetchone()[0] is not None
            if not existia:
                cur.execute(f"CREATE DATABASE [{base}]")
                log(f"  base [{base}] criada")
            else:
                log(f"  base [{base}] ja' existia")
            rel.base_criada = not existia
            cur.execute("SELECT 1 FROM sys.server_principals WHERE name = ?", login)
            rel.login_existe = cur.fetchone() is not None
        # 2. utilizador do login na base
        with connect(servidor, base, trust_server_cert) as c:
            cur = c.cursor()
            if rel.login_existe:
                cur.execute("SELECT 1 FROM sys.database_principals WHERE name = ?", login)
                if cur.fetchone() is None:
                    cur.execute(f"CREATE USER [{login}] FOR LOGIN [{login}]")
                    rel.utilizador_criado = True
                    log(f"  utilizador [{login}] criado em [{base}]")
                else:
                    rel.utilizador_criado = False
                    log(f"  utilizador [{login}] ja' existia em [{base}]")
            else:
                rel.utilizador_criado = False
                log(f"  AVISO: o login [{login}] nao existe no servidor. Cria-o primeiro (provision-login ou o DBA); "
                    f"os GRANT do schema vao falhar.")
            # 3. schema
            for p in rel.passos:
                if not p.existe:
                    continue
                sql, _, _ = substituir_nomes(_ler_sql(sql_dir / p.script), base, login)
                lotes = dividir_lotes(sql)
                p.estado = "ok"
                for i, lote in enumerate(lotes, start=1):
                    try:
                        cur.execute(lote)
                        # drenar result sets (PRINT/SELECT) para nao deixar o cursor pendurado
                        while cur.nextset():
                            pass
                        p.lotes_ok += 1
                    except Exception as exc:  # noqa: BLE001 - erro do motor, reportado e decidido abaixo
                        p.estado = "falhou"
                        p.erro = f"lote {i}/{len(lotes)}: {_sanitizar(exc)}"
                        log(f"  ERRO {p.script} {p.erro}")
                        if not continue_on_error:
                            rel.resultado = "falhou"
                            rel.fim = _dt.datetime.now().isoformat(timespec="seconds")
                            _gravar(rel, relatorio_path, log)
                            return rel
                        break
                log(f"  ok   {p.script} ({p.lotes_ok}/{len(lotes)} lotes)")
        rel.resultado = "ok" if all(p.estado in ("ok", "saltado") for p in rel.passos) else "falhou"
    except Exception as exc:  # noqa: BLE001 - ligacao/identidade; nunca expor segredos
        rel.resultado = "falhou"
        log(f"  ERRO: {_sanitizar(exc)}")
    rel.fim = _dt.datetime.now().isoformat(timespec="seconds")
    _gravar(rel, relatorio_path, log)
    return rel


def _gravar(rel: Relatorio, caminho: Optional[Path], log: Callable[[str], None]) -> None:
    if caminho is None:
        try:
            from watcherdb.core.paths import logs_dir
            caminho = logs_dir() / f"setup_database_{_dt.datetime.now():%Y%m%d_%H%M%S}.json"
        except Exception:  # noqa: BLE001
            return
    try:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        Path(caminho).write_text(json.dumps(rel.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  relatorio: {caminho}")
    except OSError as exc:
        log(f"  (relatorio nao gravado: {exc})")
