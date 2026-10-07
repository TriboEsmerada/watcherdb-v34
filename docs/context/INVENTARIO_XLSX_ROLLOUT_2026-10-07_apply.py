# -*- coding: utf-8 -*-
"""Lote B do instalador: inventario .xlsx/.csv/.json -> servers.json + rollout + scripts de grants por instancia (2026-10-07).

Ficheiros do lote em docs/context/lotes/INVENTARIO_XLSX_ROLLOUT_2026-10-07/:
  watcherdb/install/inventory.py   parser portado de deploy/farm_inventory_parser.py (API antiga intacta) +
                                   parse_xlsx (openpyxl read_only/data_only), parse_servers_json (canonico,
                                   passthrough), politica_windows_auth (erro salvo --allow-windows-auth),
                                   gerar_rollout no formato de api/connection_pool.py:578-621, scripts de grants
                                   e rollback por instancia (CREATE LOGIN com placeholder guardado, SID fixo so'
                                   por AG, corpo = docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql sem EXECUTE AS),
                                   modelo .xlsx (Inventario + Instrucoes, validacao de dados).
  watcherdb/install/cli.py         + subcomandos inventory e inventory-template (substitui o cli.py do lote anterior).
  deploy/farm_inventory_parser.py  passa a shim que re-exporta a API antiga (tests/unit/test_farm_inventory_parser.py
                                   continua a passar sem alteracao).
  tests/unit/test_inventory_cli_20261007.py
Mais 1 edicao: watcherdb_service.py despacha inventory / inventory-template.

Decisoes de desenho (parecer de seguranca 2026-10-07): o rollout definitivo sai do preflight-fleet (so' quem
passou); a partir do inventario so' com --rollout-sem-verificacao explicito. Passwords nunca no inventario nem
nos scripts. SID aleatorio de 16 bytes, fixo so' entre replicas do mesmo ag_name, guardado em grants/sids.json.

Uso: py docs/context/INVENTARIO_XLSX_ROLLOUT_2026-10-07_apply.py --check | --preview | --repo <copia> | (aplica)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOTE = Path(__file__).resolve().parent / "lotes" / "INVENTARIO_XLSX_ROLLOUT_2026-10-07"
NOVOS = [Path("watcherdb/install/inventory.py"), Path("tests/unit/test_inventory_cli_20261007.py")]
SUBSTITUIDOS = [Path("watcherdb/install/cli.py"), Path("deploy/farm_inventory_parser.py")]
SVC = Path("watcherdb_service.py")
SVC_OLD = '    if sys.argv[1].lower() in ("setup-database", "bootstrap-admin", "install-help"):\n'
SVC_NEW = '    if sys.argv[1].lower() in ("setup-database", "inventory", "inventory-template", "bootstrap-admin", "install-help"):\n'


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
    for rel in SUBSTITUIDOS:
        if not (root / rel).exists():
            p.append(f"destino a substituir nao existe (aplicar SETUP_DATABASE_CLI primeiro?): {rel}")
    cli_txt = _read(root, Path("watcherdb/install/cli.py")) if (root / "watcherdb/install/cli.py").exists() else ""
    if 'add_parser("inventory"' in cli_txt:
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
    print(f"{SVC}: dispatcher ganha inventory / inventory-template")
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
