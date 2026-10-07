# -*- coding: utf-8 -*-
"""Lote C do instalador: provision-login (auto/manual/dry-run), provision-rollback e preflight-fleet (2026-10-07).

Ficheiros do lote em docs/context/lotes/PROVISION_LOGIN_2026-10-07/:
  watcherdb/install/provision.py   provisionar() sequencial com ligacao DBA injectavel (sessao Windows so' neste
                                   passo), password CSPRNG por instancia/AG parametrizada no CREATE LOGIN, SID fixo so'
                                   por AG, login existente nunca recriado (--adopt so' aplica grants), inalcancaveis nao
                                   abortam, paragem apos N falhas de autenticacao, relatorio JSON sanitizado, Event Log
                                   2000-2003/2010; rollback() so' onde created=true; preflight() por ligacao real com o
                                   login (sysadmin=0, permissoes esperadas, permissoes A MAIS = FAIL, erros 18456
                                   classificados) e exit 0/2/1; passwords cifradas no servers.json (encrypted:).
  watcherdb/install/cli.py         + provision-login (--mode manual por omissao; auto e' opt-in; --execute exige
                                   --confirm-count e master key presente), provision-rollback, preflight-fleet
                                   (escreve o rollout so' com quem passou).
  tests/unit/test_provision_login_20261007.py  (ligacoes falsas; sentinela prova que a password nao sai em log/relatorio;
                                   condicao 8 verificada em api/routers/jobs.py)
Mais 1 edicao: watcherdb_service.py despacha os 3 subcomandos.

As 14 condicoes do parecer de seguranca e onde ficam: ver docstring de provision.py. Condicoes que ficam para
lotes seguintes: 3 (prova 'nada em disco' com sentinela num servidor real -> checklist de release), 4 (ACL de
config\\ e .env verificada pelo install.ps1 -> lote E), 5 (rotate-login-password).

Uso: py docs/context/PROVISION_LOGIN_2026-10-07_apply.py --check | --preview | --repo <copia> | (aplica)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOTE = Path(__file__).resolve().parent / "lotes" / "PROVISION_LOGIN_2026-10-07"
NOVOS = [Path("watcherdb/install/provision.py"), Path("tests/unit/test_provision_login_20261007.py")]
SUBSTITUIDOS = [Path("watcherdb/install/cli.py")]
SVC = Path("watcherdb_service.py")
SVC_OLD = '    if sys.argv[1].lower() in ("setup-database", "inventory", "inventory-template", "bootstrap-admin", "install-help"):\n'
SVC_NEW = ('    if sys.argv[1].lower() in ("setup-database", "inventory", "inventory-template", "provision-login", "provision-rollback", "preflight-fleet",\n'
           '                               "bootstrap-admin", "install-help"):\n')


def _read(root: Path, rel: Path) -> str:
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def check(root: Path) -> list[str]:
    p: list[str] = []
    for rel in NOVOS + SUBSTITUIDOS:
        if not (LOTE / rel).exists():
            p.append(f"fonte do lote em falta: {LOTE / rel}")
    for rel in NOVOS:
        if (root / rel).exists():
            p.append(f"ja existe no destino: {rel}")
    cli_path = root / "watcherdb/install/cli.py"
    if not cli_path.exists() or 'add_parser("inventory"' not in _read(root, Path("watcherdb/install/cli.py")):
        p.append("watcherdb/install/cli.py: aplicar INVENTARIO_XLSX_ROLLOUT primeiro")
    elif 'add_parser("provision-login"' in _read(root, Path("watcherdb/install/cli.py")):
        p.append("watcherdb/install/cli.py: ja aplicado")
    t = _read(root, SVC).replace("\r\n", "\n")
    if t.count(SVC_OLD) != 1:
        p.append(f"{SVC}: ancora do dispatcher nao unica ({t.count(SVC_OLD)}x)")
    return p


def apply(root: Path, preview: bool) -> None:
    for rel in NOVOS:
        print(f"{rel}: novo ({(LOTE / rel).read_text(encoding='utf-8').count(chr(10))} linhas)")
    for rel in SUBSTITUIDOS:
        print(f"{rel}: substituido ({(LOTE / rel).read_text(encoding='utf-8').count(chr(10))} linhas)")
    print(f"{SVC}: dispatcher ganha provision-login / provision-rollback / preflight-fleet")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel in NOVOS + SUBSTITUIDOS:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(LOTE / rel, root / rel)
    bruto = _read(root, SVC)
    crlf = "\r\n" in bruto
    novo = bruto.replace("\r\n", "\n").replace(SVC_OLD, SVC_NEW, 1)
    with open(root / SVC, "w", encoding="utf-8", newline="") as fh:
        fh.write(novo.replace("\n", "\r\n") if crlf else novo)
    print("\naplicado.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.repo.resolve()
    p = check(root)
    if p:
        print("CHECK FALHOU:\n  " + "\n  ".join(p))
        return 1
    print(f"check ok em {root}")
    if a.check:
        return 0
    apply(root, a.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
