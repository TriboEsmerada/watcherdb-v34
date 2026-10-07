"""Subcomandos do instalador: `watcherdb.exe <subcomando> ...` (ver watcherdb_service.py main()).

Implementados: setup-database, inventory, inventory-template, bootstrap-admin, install-help.
Em preparacao (DESIGN_INSTALADOR_V3.4_2026-10-07.md): provision-login, configure, preflight-fleet.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR
from .sqlnames import NomeInvalido, validar_identificador

SUBCOMANDOS = ("setup-database", "inventory", "inventory-template", "bootstrap-admin", "install-help")
EM_PREPARACAO = ("provision-login", "configure", "preflight-fleet")


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

    inv = sub.add_parser("inventory", help="Inventario da frota (.xlsx/.csv/.json) -> servers.json + scripts de grants por instancia.")
    inv.add_argument("--input", type=Path, required=True, help="ficheiro .xlsx (modelo de inventory-template), .csv, .json ou servers.json canonico")
    inv.add_argument("--output-dir", type=Path, default=None, help="pasta de saida (omissao: config do produto)")
    inv.add_argument("--database", default=OMISSAO_BASE_INSTALADOR, help="nome da base do produto")
    inv.add_argument("--login", default=OMISSAO_LOGIN_INSTALADOR, help="login SQL do produto (vai para o master e para os scripts de grants)")
    inv.add_argument("--master-host", default=None, help="host do SQL Server da base do produto (obrigatorio salvo servers.json canonico)")
    inv.add_argument("--master-instance", default="MSSQLSERVER")
    inv.add_argument("--master-port", type=int, default=1433)
    inv.add_argument("--validate-tcp", action="store_true", help="testar TCP a cada instancia (aviso, nao erro)")
    inv.add_argument("--allow-windows-auth", action="store_true", help="aceitar linhas auth_mode=windows (viola a Regra de Ouro #2; so' deliberado)")
    inv.add_argument("--strict", action="store_true", help="avisos contam como erros")
    inv.add_argument("--rollout-sem-verificacao", action="store_true",
                     help="escrever sql_auth_rollout.json a partir do inventario SEM o preflight-fleet (o caminho normal e' o preflight escrever so' quem passou)")
    inv.add_argument("--grants-dir", type=Path, default=None, help="pasta dos scripts de grants (omissao: <output-dir>/grants)")

    tpl = sub.add_parser("inventory-template", help="Gera o modelo .xlsx do inventario (folha Inventario + Instrucoes).")
    tpl.add_argument("--output", type=Path, required=True)

    ba = sub.add_parser("bootstrap-admin", help="Cria o primeiro administrador do portal (interactivo; recusa se ja houver admin).")
    ba.add_argument("resto", nargs=argparse.REMAINDER)

    sub.add_parser("install-help", help="Lista os subcomandos de instalacao.")
    return ap


def _cmd_inventory(a) -> int:
    from . import inventory as inv  # import tardio
    try:
        validar_identificador(a.database, "nome da base")
        validar_identificador(a.login, "login")
    except NomeInvalido as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    if not a.input.exists():
        print(f"ERRO: ficheiro nao encontrado: {a.input}", file=sys.stderr)
        return 2
    entries, issues, master_doc, formato = inv.ler_inventario(a.input, a.login, validate_tcp=a.validate_tcp)
    issues = list(issues) + inv.politica_windows_auth(entries, a.allow_windows_auth)
    erros = [i for i in issues if i.severity == "error"]
    avisos = [i for i in issues if i.severity == "warning"]
    for i in issues:
        print(f"{'ERRO' if i.severity == 'error' else 'AVISO'} [linha {i.row_number}] {i.field}: {i.message}", file=sys.stderr)
    if erros:
        print(f"\nFALHOU: {len(erros)} erro(s), {len(avisos)} aviso(s). Corrige e repete.", file=sys.stderr)
        return 1
    if a.strict and avisos:
        print(f"\nFALHOU (--strict): {len(avisos)} aviso(s).", file=sys.stderr)
        return 1
    if not entries:
        print("ERRO: nenhuma instancia valida no inventario", file=sys.stderr)
        return 1
    if master_doc is None:
        if not a.master_host:
            print("ERRO: --master-host e' obrigatorio (ou entrega um servers.json canonico com master_server)", file=sys.stderr)
            return 2
        master_doc = inv.build_master_server(a.master_host, instance=a.master_instance, port=a.master_port,
                                             database=a.database, username=a.login,
                                             description="WatcherDB master")
    if a.output_dir is None:
        from watcherdb.core.paths import config_dir
        out_dir = config_dir()
    else:
        out_dir = a.output_dir
    servers_path = out_dir / "servers.json"
    inv.write_servers_json(servers_path, master_doc, entries)
    print(f"servers.json: {servers_path} ({len(entries)} instancias, formato de entrada: {formato})")
    grants_dir = a.grants_dir or (out_dir / "grants")
    sids_path = grants_dir / "sids.json"
    sids = None
    if sids_path.exists():
        import json as _json
        sids = _json.loads(sids_path.read_text(encoding="utf-8"))
    res = inv.escrever_scripts_grants(entries, a.login, grants_dir, sids)
    print(f"grants: {len(res['instancias'])} scripts em {grants_dir} (INDICE.md com hashes; sids.json para AGs)")
    if a.rollout_sem_verificacao:
        roll = inv.gerar_rollout(entries)
        inv.write_rollout_json(out_dir / "sql_auth_rollout.json", roll)
        print(f"sql_auth_rollout.json: {len(roll['sql_auth_servers'])} ids (SEM verificacao: o preflight-fleet reescreve-o)")
    else:
        print("sql_auth_rollout.json: nao escrito (o preflight-fleet escreve-o com as instancias que passarem)")
    print(f"avisos: {len(avisos)} | passwords: placeholder {inv.PASSWORD_PLACEHOLDER} (o instalador pede-as e cifra-as)")
    return 0


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

    if a.cmd == "inventory":
        return _cmd_inventory(a)

    if a.cmd == "inventory-template":
        from .inventory import gerar_modelo_xlsx
        p = gerar_modelo_xlsx(a.output)
        print(f"modelo: {p}")
        return 0

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
