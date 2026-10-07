# -*- coding: utf-8 -*-
"""test_portal_diagnosis_layout_anchors: 'script inline sem nonce' era falso positivo (2026-10-06).

SINTOMA: tests/unit/test_diagnosis_layout_wave_20260817.py::test_portal_diagnosis_layout_anchors
vermelho desde 2026-09-09 ('script inline sem nonce'; CONTEXT.md 18/09 pedia investigacao). O gate
de release de hoje confirmou que e' a UNICA falha fora da baseline do build (deploy/build_release.ps1
:334-340) -> o PASSO 1 do build abortaria com exit 2.

CAUSA: o teste procura `<script(?![^>]*\\bsrc=)([^>]*)>` em TODO o texto do template. Desde o commit
b8b3eb0e (09/09, relatorios no iframe com CSP) o JS do portal contem:
  l.30003  // ... O relatorio traz <style> e <script> inline ...            (comentario JS)
  l.30011  .replace(/<script(?![^>]*\\bnonce=)([\\s>])/gi, ...)              (regex literal em JS)
Nenhum dos dois e' uma tag. As 20 tags <script> reais do template (7 com src, 13 inline) estao
todas no inicio da linha (indentadas) e todas as inline tem nonce.

FIX (so' o teste): ancorar a procura ao inicio da linha (re.M). Verificado no template de hoje:
regex antigo 16 'inline' (3 falsos positivos, 2 deles sem nonce); regex novo 13 inline, 0 sem nonce.
Um <script> real escrito a meio de uma linha ficaria fora da guarda -- o template nao tem nenhum
e um teste novo fixa esse pressuposto.

Uso:
  py docs/context/NONCE_TEST_FALSO_POSITIVO_2026-10-06_apply.py --check
  py docs/context/NONCE_TEST_FALSO_POSITIVO_2026-10-06_apply.py --repo <copia>
  py docs/context/NONCE_TEST_FALSO_POSITIVO_2026-10-06_apply.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST = Path("tests/unit/test_diagnosis_layout_wave_20260817.py")

OLD = (
    "    # nenhum bloco <script> novo sem nonce (contagem de blocos com nonce == total)\n"
    "    scripts = re.findall(r'<script(?![^>]*\\bsrc=)([^>]*)>', portal)\n"
    "    assert all('nonce' in s for s in scripts), 'script inline sem nonce'\n"
)
NEW = (
    "    # nenhum bloco <script> novo sem nonce (contagem de blocos com nonce == total)\n"
    "    # 2026-10-06: so' tags no inicio da linha -- o JS do portal contem '<script' num comentario\n"
    "    # (l.~30003) e num regex literal (l.~30011) desde 09/09, e isso nao e' uma tag.\n"
    "    scripts = re.findall(r'^\\s*<script(?![^>]*\\bsrc=)([^>]*)>', portal, re.M)\n"
    "    assert scripts, 'nenhuma tag <script> inline encontrada: a ancora ao inicio da linha deixou de servir'\n"
    "    assert all('nonce' in s for s in scripts), 'script inline sem nonce'\n"
    "    # pressuposto da ancora: nenhuma tag <script> real a meio de uma linha\n"
    "    a_meio = [m for m in re.finditer(r'(?<!^)(?<![\\s])<script\\b[^>]*>', portal, re.M)\n"
    "              if not portal[max(0, m.start() - 80):m.start()].rstrip().endswith(('//', '/', '`', '\"', \"'\"))]\n"
    "    assert not a_meio, 'tag <script> fora do inicio da linha: rever a guarda do nonce'\n"
)


def _read(root: Path) -> str:
    with open(root / TEST, encoding="utf-8", newline="") as fh:
        return fh.read()


def check(root: Path) -> list[str]:
    t = _read(root).replace("\r\n", "\n")
    p = []
    if t.count(OLD) != 1:
        p.append(f"{TEST}: bloco do nonce nao encontrado ({t.count(OLD)}x)")
    if "re.M)" in t and "script inline sem nonce" in t and "2026-10-06" in t:
        p.append(f"{TEST}: ja aplicado")
    return p


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
    bruto = _read(root)
    crlf = "\r\n" in bruto
    novo = bruto.replace("\r\n", "\n").replace(OLD, NEW, 1)
    print(f"{TEST}: guarda do nonce ancorada ao inicio da linha + teste do pressuposto [{'CRLF' if crlf else 'LF'} preservado]")
    if a.preview:
        print("--- preview: nada escrito ---")
        return 0
    with open(root / TEST, "w", encoding="utf-8", newline="") as fh:
        fh.write(novo.replace("\n", "\r\n") if crlf else novo)
    print("aplicado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
