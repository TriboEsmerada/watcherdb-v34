"""Subcomandos do instalador: `watcherdb.exe <subcomando> ...` (ver watcherdb_service.py main()).

Implementados: setup-database, bootstrap-admin, install-help.
Em preparacao (DESIGN_INSTALADOR_V3.4_2026-10-07.md): inventory, provision-login, configure, preflight-fleet.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR
from .sqlnames import NomeInvalido

SUBCOMANDOS = ("setup-database", "bootstrap-admin", "install-help")
EM_PREPARACAO = ("inventory", "provision-login", "configure", "preflight-fleet")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="watcherdb.exe", description="Ferramentas de instalacao do WatcherDB.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sd = sub.add_parser("setup-database", help="Cria a base (se faltar), o utilizador do login e aplica o schema.")
    sd.add_argument("--server", required=True, help="servidor\\instancia SQL Server da base do produto")
    sd.add_argument("--database", default=OMISSAO_BASE_INSTALADOR, help=f"nome da base (omissao {OMISSAO_BASE_INSTALADOR})")
    sd.add_argument("--login", default=OMISSAO_LOGIN_INSTALADOR, help=f"login SQL do produto (omissao {OMISSAO_LOGIN_INSTALADOR})")
    sd.add_argument("--sql-dir", type=Path, default=None, help="pasta dos .sql (omissao: a do pacote)")
    sd.add_argument("--execute", action="store_true", help="executa de verdade; sem isto e' dry-run (plano por script)")
    sd.add_argument("--continue-on-error", action="store_true", help="nao parar no primeiro erro (omissao: estrito)")
    sd.add_argument("--trust-server-cert", action="store_true", help="aceitar certificado TLS nao validado (registado no relatorio)")
    sd.add_argument("--report", type=Path, default=None, help="caminho do relatorio JSON (omissao: logs do produto)")

    ba = sub.add_parser("bootstrap-admin", help="Cria o primeiro administrador do portal (interactivo; recusa se ja houver admin).")
    ba.add_argument("resto", nargs=argparse.REMAINDER)

    sub.add_parser("install-help", help="Lista os subcomandos de instalacao.")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = _parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:  # argparse ja' imprimiu a ajuda/erro
        return int(exc.code or 0)

    if a.cmd == "install-help":
        print("Subcomandos de instalacao:")
        for s in SUBCOMANDOS:
            print(f"  {s}")
        print("Em preparacao: " + ", ".join(EM_PREPARACAO))
        return 0

    if a.cmd == "bootstrap-admin":
        from tools.bootstrap_admin import main as _bootstrap_main  # import tardio
        return int(_bootstrap_main(a.resto) or 0)

    if a.cmd == "setup-database":
        from .dbsetup import executar  # import tardio (pyodbc so' em --execute)
        try:
            rel = executar(
                a.server, a.database, a.login,
                sql_dir=a.sql_dir, dry_run=not a.execute, continue_on_error=a.continue_on_error,
                trust_server_cert=a.trust_server_cert, relatorio_path=a.report,
            )
        except NomeInvalido as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        except RuntimeError as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        return {"ok": 0, "dry-run": 0}.get(rel.resultado, 1)

    return 2
