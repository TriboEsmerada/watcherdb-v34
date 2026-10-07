"""Subcomandos do instalador: `watcherdb.exe <subcomando> ...` (ver watcherdb_service.py main()).

Implementados: setup-database, inventory, inventory-template, provision-login, provision-rollback,
preflight-fleet, bootstrap-admin, install-help. Em preparacao: configure (lote E).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR
from .sqlnames import NomeInvalido, validar_identificador

SUBCOMANDOS = ("setup-database", "inventory", "inventory-template", "provision-login", "provision-rollback",
               "preflight-fleet", "bootstrap-admin", "install-help")
EM_PREPARACAO = ("configure",)


def _config_dir() -> Path:
    from watcherdb.core.paths import config_dir
    return config_dir()


def _cifrar_decifrar():
    """(cifrar, decifrar) com a master key do produto; (None, None) se nao houver master key."""
    try:
        from services.secrets import try_get_master_key, encrypt_value
        key = try_get_master_key()
        if not key:
            return None, None
        from cryptography.fernet import Fernet
        f = Fernet(key)

        def decifrar(v: str) -> str:
            return f.decrypt(v[len("encrypted:"):].encode()).decode()
        return encrypt_value, decifrar
    except Exception:  # noqa: BLE001
        return None, None


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

    pl = sub.add_parser("provision-login", help="Cria e permissiona o login do produto em todas as instancias do inventario (auto) ou aponta para os scripts (manual).")
    pl.add_argument("--inventory", type=Path, default=None, help="servers.json (omissao: config do produto)")
    pl.add_argument("--login", default=OMISSAO_LOGIN_INSTALADOR)
    pl.add_argument("--mode", choices=("auto", "manual"), default="manual", help="manual = scripts do inventory (omissao, recomendado); auto = o instalador cria o login (opt-in)")
    pl.add_argument("--execute", action="store_true", help="auto: executa de verdade; sem isto e' dry-run (le o estado, nao escreve)")
    pl.add_argument("--confirm-count", type=int, default=None, help="auto + --execute: numero de instancias que esperas tocar (tem de bater)")
    pl.add_argument("--adopt", action="store_true", help="auto: aplicar os grants a um login que ja' existe (por omissao nao se toca)")
    pl.add_argument("--max-auth-failures", type=int, default=3, help="parar apos N falhas de autenticacao consecutivas (lockout em massa)")
    pl.add_argument("--trust-server-cert", action="store_true", help="aceitar certificado TLS nao validado (registado no relatorio)")
    pl.add_argument("--report", type=Path, default=None)

    rb = sub.add_parser("provision-rollback", help="Remove o login SO' nas instancias onde o relatorio do provision-login diz created=true.")
    rb.add_argument("--report", type=Path, required=True)
    rb.add_argument("--login", default=OMISSAO_LOGIN_INSTALADOR)
    rb.add_argument("--trust-server-cert", action="store_true")

    pf = sub.add_parser("preflight-fleet", help="Liga com o login a cada instancia, valida grants (sem permissoes a mais) e escreve o rollout com quem passou.")
    pf.add_argument("--inventory", type=Path, default=None, help="servers.json com as passwords cifradas (omissao: config do produto)")
    pf.add_argument("--login", default=OMISSAO_LOGIN_INSTALADOR)
    pf.add_argument("--rollout", type=Path, default=None, help="onde escrever sql_auth_rollout.json (omissao: config do produto)")
    pf.add_argument("--no-rollout", action="store_true", help="so' validar; nao escrever o rollout")
    pf.add_argument("--require-errorlog", action="store_true", help="xp_readerrorlog em falta conta como falha")
    pf.add_argument("--trust-server-cert", action="store_true")

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
    out_dir = a.output_dir if a.output_dir is not None else _config_dir()
    servers_path = out_dir / "servers.json"
    inv.write_servers_json(servers_path, master_doc, entries)
    print(f"servers.json: {servers_path} ({len(entries)} instancias, formato de entrada: {formato})")
    grants_dir = a.grants_dir or (out_dir / "grants")
    sids_path = grants_dir / "sids.json"
    sids = json.loads(sids_path.read_text(encoding="utf-8")) if sids_path.exists() else None
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


def _carregar_inventario(caminho: Optional[Path]):
    from . import inventory as inv
    p = caminho or (_config_dir() / "servers.json")
    if not p.exists():
        print(f"ERRO: inventario nao encontrado: {p}", file=sys.stderr)
        return None, None
    entries, issues, _m = inv.parse_servers_json(p)
    erros = [i for i in issues if i.severity == "error"]
    if erros:
        for i in erros:
            print(f"ERRO [{i.row_number}] {i.field}: {i.message}", file=sys.stderr)
        return None, None
    return p, entries


def _cmd_provision(a) -> int:
    from . import provision as prov
    try:
        validar_identificador(a.login, "login")
    except NomeInvalido as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    p, entries = _carregar_inventario(a.inventory)
    if entries is None:
        return 2
    if a.mode == "manual":
        n = sum(1 for e in entries if not e.use_windows_auth and e.enabled)
        print(f"modo MANUAL (recomendado): {n} instancias. O DBA corre os scripts grants_<id>.sql gerados por "
              f"`watcherdb.exe inventory` (pasta grants ao lado do servers.json), com a password preenchida em @pw "
              f"(a mesma nas replicas do mesmo AG). Depois: `watcherdb.exe preflight-fleet` valida e escreve o rollout.")
        return 0
    cifrar, _ = _cifrar_decifrar()
    if a.execute and cifrar is None:
        print("ERRO: sem master key do produto (master.key.dpapi ou WATCHERDB_ENCRYPTION_KEY): as passwords geradas nao "
              "poderiam ser cifradas no servers.json e os logins ficariam inacessiveis. Corre o install.ps1 (PASSO f) primeiro.",
              file=sys.stderr)
        return 2
    sids_path = p.parent / "grants" / "sids.json"
    sids = json.loads(sids_path.read_text(encoding="utf-8")) if sids_path.exists() else None
    rel, criadas = prov.provisionar(entries, a.login, dry_run=not a.execute, adopt=a.adopt, confirm_count=a.confirm_count,
                                    max_falhas_auth=a.max_auth_failures, trust_server_cert=a.trust_server_cert,
                                    sids=sids, relatorio_path=a.report)
    if criadas:
        n = prov.guardar_passwords_cifradas(p, criadas, cifrar)
        print(f"passwords cifradas no servers.json: {n} (prefixo encrypted:)")
        if sids is None and rel.instancias:
            pass
    if rel.resultado in ("dry-run", "ok"):
        return 0
    return 1


def _cmd_rollback(a) -> int:
    from . import provision as prov
    if not a.report.exists():
        print(f"ERRO: relatorio nao encontrado: {a.report}", file=sys.stderr)
        return 2
    rel = json.loads(a.report.read_text(encoding="utf-8"))
    res = prov.rollback(rel, a.login, trust_server_cert=a.trust_server_cert)
    print(f"rollback: {sum(1 for _, s in res if s == 'removido')} removidos de {len(res)} com created=true")
    return 0 if all(s == "removido" for _, s in res) else 1


def _cmd_preflight(a) -> int:
    from . import provision as prov
    from . import inventory as inv
    p, entries = _carregar_inventario(a.inventory)
    if entries is None:
        return 2
    _, decifrar = _cifrar_decifrar()
    if decifrar is None:
        print("ERRO: sem master key do produto para decifrar as passwords do servers.json.", file=sys.stderr)
        return 2
    passwords = prov.ler_passwords_cifradas(p, decifrar)
    res = prov.preflight(entries, a.login, passwords, trust_server_cert=a.trust_server_cert, exigir_errorlog=a.require_errorlog)
    rc = prov.exit_code_preflight(res)
    passaram = [r.id for r in res if r.passou]
    print(f"preflight-fleet: {len(passaram)}/{len(res)} passaram | exit {rc}")
    if not a.no_rollout:
        destino = a.rollout or (p.parent / "sql_auth_rollout.json")
        inv.write_rollout_json(destino, inv.gerar_rollout(entries, verificados=passaram))
        print(f"sql_auth_rollout.json: {destino} ({len(passaram)} ids)")
    return rc


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
        print(f"modelo: {gerar_modelo_xlsx(a.output)}")
        return 0
    if a.cmd == "provision-login":
        return _cmd_provision(a)
    if a.cmd == "provision-rollback":
        return _cmd_rollback(a)
    if a.cmd == "preflight-fleet":
        return _cmd_preflight(a)
    if a.cmd == "setup-database":
        from .dbsetup import executar  # import tardio (pyodbc so' em --execute)
        try:
            rel = executar(
                a.server, a.database, a.login,
                sql_dir=a.sql_dir, dry_run=not a.execute, continue_on_error=a.continue_on_error,
                trust_server_cert=a.trust_server_cert, relatorio_path=a.report,
            )
        except (NomeInvalido, RuntimeError) as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        return {"ok": 0, "dry-run": 0}.get(rel.resultado, 1)
    return 2
