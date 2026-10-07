# -*- coding: utf-8 -*-
"""Lotes A.1 + esqueleto D do instalador: `watcherdb.exe setup-database` com nomes substituidos em runtime (2026-10-07).

Ficheiros do lote (revisaveis como ficheiros normais) em docs/context/lotes/SETUP_DATABASE_CLI_2026-10-07/:
  watcherdb/install/__init__.py   omissoes do INSTALADOR (WatcherDB / watcherdb)
  watcherdb/install/sqlnames.py   validacao de identificadores, substituicao em memoria (canonico byte-igual),
                                  lotes GO como o sqlcmd, ordem dos 22 scripts (= setup_database.ps1:105-131)
  watcherdb/install/dbsetup.py    plano (dry-run) e execucao estrita: base -> utilizador do login -> schema;
                                  identidade = sessao Windows de quem corre, so' neste passo (decisao 2026-10-07)
  watcherdb/install/cli.py        subcomandos setup-database, bootstrap-admin, install-help
  tests/unit/test_setup_database_cli_20261007.py

Mais 1 edicao: watcherdb_service.py main() despacha os subcomandos por import tardio (antes de HandleCommandLine).

O que NAO muda: database/*.sql (byte-iguais), deploy/setup_database.ps1 (fica como wrapper do vendor ate' o
lote E), o build (watcherdb/ ja' e' PROTECT_DIR e collect_submodules("watcherdb") apanha o pacote;
database/ ja' vai no bundle em _internal/database = project_root()).

Uso: py docs/context/SETUP_DATABASE_CLI_2026-10-07_apply.py --check | --preview | --repo <copia> | (aplica)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOTE = Path(__file__).resolve().parent / "lotes" / "SETUP_DATABASE_CLI_2026-10-07"
NOVOS = [
    Path("watcherdb/install/__init__.py"),
    Path("watcherdb/install/sqlnames.py"),
    Path("watcherdb/install/dbsetup.py"),
    Path("watcherdb/install/cli.py"),
    Path("tests/unit/test_setup_database_cli_20261007.py"),
]
SVC = Path("watcherdb_service.py")
SVC_OLD = ('    if sys.argv[1].lower() in ("wrap-master-key", "--wrap-master-key"):\n'
           '        return wrap_master_key()\n')
SVC_NEW = ('    if sys.argv[1].lower() in ("wrap-master-key", "--wrap-master-key"):\n'
           '        return wrap_master_key()\n'
           '    if sys.argv[1].lower() in ("setup-database", "bootstrap-admin", "install-help"):\n'
           '        # 2026-10-07: subcomandos do instalador (watcherdb/install). Import TARDIO de proposito:\n'
           '        # nada de watcherdb.*/api.* antes do dispatcher (erro 1053 com EDR no arranque do servico).\n'
           '        from watcherdb.install.cli import main as _install_main\n'
           '        return _install_main(sys.argv[1:])\n')


def _read(root: Path, rel: Path) -> str:
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def check(root: Path) -> list[str]:
    p: list[str] = []
    for rel in NOVOS:
        if not (LOTE / rel).exists():
            p.append(f"fonte do lote em falta: {LOTE / rel}")
        if (root / rel).exists():
            p.append(f"ja existe no destino: {rel}")
    t = _read(root, SVC).replace("\r\n", "\n")
    if t.count(SVC_OLD) != 1:
        p.append(f"{SVC}: ancora do dispatcher nao unica ({t.count(SVC_OLD)}x)")
    if "watcherdb.install.cli" in t:
        p.append(f"{SVC}: ja aplicado")
    return p


def apply(root: Path, preview: bool) -> None:
    for rel in NOVOS:
        print(f"{rel}: novo ({(LOTE / rel).read_text(encoding='utf-8').count(chr(10))} linhas)")
    print(f"{SVC}: dispatcher ganha setup-database / bootstrap-admin / install-help (import tardio)")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel in NOVOS:
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
