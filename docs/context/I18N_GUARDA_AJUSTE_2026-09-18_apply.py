# -*- coding: utf-8 -*-
"""Teste de guarda do i18n: KPI_DOCUMENTATION e' recurso (ja traduzido inline), nao texto a` mao (2026-09-18).

CORRECCAO AO INVENTARIO DE 17/09: contei 118 textos de KPI_DOCUMENTATION como "fora do i18n". Errado -- as 29 entradas
tem `i18n: { en: {...}, es: {...} }` inline e a modal "Documentacao dos KPIs" le por idioma (tDoc(kpi, campo, idx),
_docTitle via kpi_doc.*, thresholdTable via kpi.i18n[lang]). Os textos em portugues no dicionario sao o recurso por
omissao, como CARD_HELP_TEXTS e BACKUP_KPI_INFO. O varredor da guarda passa a ignora-lo e a linha de base desce.

Uso (raiz do repo):
  py docs/context/I18N_GUARDA_AJUSTE_2026-09-18_apply.py --check
  py docs/context/I18N_GUARDA_AJUSTE_2026-09-18_apply.py
  py -m pytest tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTE = ROOT / "tests/unit/test_i18n_texto_a_mao_20260918.py"
PORTAL = ROOT / "templates/watcherdb_portal.html"
OLD = '_RECURSOS = ("CARD_HELP_TEXTS", "BACKUP_KPI_INFO")   # dicionarios que sao so\' recurso do i18n (as chaves existem)'
NEW = '_RECURSOS = ("CARD_HELP_TEXTS", "BACKUP_KPI_INFO", "KPI_DOCUMENTATION")   # dicionarios que sao so\' recurso do i18n (KPI_DOCUMENTATION: i18n inline en/es + kpi_doc.*)'


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    teste, portal = base / "tests/unit/test_i18n_texto_a_mao_20260918.py", base / "templates/watcherdb_portal.html"
    txt = teste.read_bytes().decode("utf-8")
    if "KPI_DOCUMENTATION" in txt:
        print("[ABORT] ja aplicado"); return 1
    if txt.count(OLD) != 1:
        raise SystemExit(f"[ABORT] _RECURSOS esperado 1x, encontrado {txt.count(OLD)}x")
    novo = txt.replace(OLD, NEW)
    ns: dict = {}
    exec(novo[novo.index("import re"):novo.index("def test_texto_a_mao_nao_sobe")], ns)
    js, tags, _ = ns["contar_texto_a_mao"](portal.read_bytes().decode("utf-8").replace("\r\n", "\n"))
    antes = re.search(r"BASE_JS, BASE_TAGS = (\d+), (\d+)", txt)
    novo = re.sub(r"BASE_JS, BASE_TAGS = \d+, \d+", f"BASE_JS, BASE_TAGS = {js}, {tags}", novo)
    print(f"[ok] guarda: KPI_DOCUMENTATION passa a recurso; base JS {antes.group(1)} -> {js}, tags {antes.group(2)} -> {tags}")
    if check:
        print("--check OK. Nada escrito."); return 0
    teste.write_bytes(novo.encode("utf-8")); print("[write] tests/unit/test_i18n_texto_a_mao_20260918.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
