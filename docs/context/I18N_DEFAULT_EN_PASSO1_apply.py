#!/usr/bin/env python3
"""Lingua default do portal passa a INGLES -- PASSO 1: aplicar (decisao owner 2026-09-03).

Semantica: "default" = o que um utilizador ve' antes de escolher idioma (sem preferencia em
localStorage 'watcherdb_lang'). Quem ja' escolheu mantem a escolha. pt.json continua a ser o
ground truth de CHAVES (paridade en/es testada) -- muda so' o idioma inicial e o <html lang>.
FALLBACK_CHAIN mantem-se (en -> pt): chave em falta em en mostra pt, nunca a chave crua.

AVISO: com ingles por omissao, qualquer string portuguesa hardcoded (wave BUG-003) passa a ser
vista por TODOS os utilizadores novos. Aplicar o lote F1 (I18N_F1_PASSO1_apply.py) ANTES deste.

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_DEFAULT_EN_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_DEFAULT_EN_PASSO1_apply.py
Impacto: runtime i18n, <html lang> do portal (linha 2 -- os outros 3 <html lang="pt-PT"> sao
documentos exportados e ficam), FEATURE_MATRIX, glossario, CHANGELOG. Zero backend.
Rollback: git checkout -- static/js/watcherdb_i18n_v2.js templates/watcherdb_portal.html \
            docs/FEATURE_MATRIX.md knowledge_base/domain/i18n_glossary.md docs/changelog/CHANGELOG.md
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent

PATCHES = [
    ("static/js/watcherdb_i18n_v2.js", "    const DEFAULT_LANG = 'pt';\n",
     "    const DEFAULT_LANG = 'en';   // decisao owner 2026-09-03: ingles por omissao; pt.json continua ground truth de chaves\n", 1),
    ("static/js/watcherdb_i18n_v2.js", " * Supports: PT-PT (default, pt.json), PT-BR (pt-BR.json = overlay esparso com fallback por chave para pt), EN, ES\n",
     " * Supports: EN (default), PT-PT (pt.json = ground truth de chaves), PT-BR (pt-BR.json = overlay esparso com fallback por chave para pt), ES\n", 1),
    # 4 ocorrencias no ficheiro (portal + 3 documentos exportados que sao strings JS); so' a 1.a (linha 2) e' o portal
    ("templates/watcherdb_portal.html", '<html lang="pt-PT">\n<head>\n    <meta charset="UTF-8">',
     '<html lang="en">\n<head>\n    <meta charset="UTF-8">', 4, "first"),
    ("docs/FEATURE_MATRIX.md", "- PT-PT (default, `pt.json`), PT-BR (`pt-BR.json`, overlay esparso: só chaves que diferem de pt-PT; fallback por chave), EN (en-US), ES (neutro).",
     "- **EN (en-US) é o idioma por omissão** (decisão owner 2026-09-03; quem já escolheu mantém). PT-PT (`pt.json`, ground truth de chaves), PT-BR (`pt-BR.json`, overlay esparso: só chaves que diferem de pt-PT; fallback por chave), ES (neutro).", 1),
    ("knowledge_base/domain/i18n_glossary.md", "`pt.json` = pt-PT pós-AO90 (default); `pt-BR.json` = overlay esparso (só o que difere);",
     "`en.json` = idioma por omissão (decisão owner 2026-09-03); `pt.json` = pt-PT pós-AO90 e ground truth de chaves; `pt-BR.json` = overlay esparso (só o que difere);", 1),
]
CHANGELOG_ENTRY = """- **Inglês passa a idioma por omissão do portal** (decisão owner 03/09). Aplica-se a quem
  ainda não escolheu idioma; a preferência guardada (`watcherdb_lang`) continua a mandar.
  `pt.json` mantém-se como ground truth de chaves (paridade testada) e o fallback en → pt
  mantém-se, pelo que uma chave em falta em inglês mostra português, nunca a chave crua.
  `<html lang>` do portal passa a `en`. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    texts, problems = {}, []
    PATCHES[:] = [(t + (None,))[:5] for t in PATCHES]  # normaliza para (rel, old, new, n, mode)
    for rel, old, new, n, mode in PATCHES:
        p = root / rel
        if not p.exists(): problems.append(f"{rel}: nao existe"); continue
        texts.setdefault(rel, read(p)); raw, nl = texts[rel]
        c = raw.count(norm(old, nl))
        if c != n: problems.append(f"{rel}: esperado {n}x, encontrado {c}x -> {old[:70]!r}")
        if mode == "first" and not raw.startswith(norm("<!DOCTYPE html>\n" + old.split("\n")[0], nl)):
            problems.append(f"{rel}: a 1.a ocorrencia nao esta na linha 2 (portal)")
    chg = root / "docs/changelog/CHANGELOG.md"; craw, cnl = read(chg)
    anchor = norm("## [Unreleased]\n\n### Changed\n\n", cnl)
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada 1x")
    if "Inglês passa a idioma por omissão" in craw: problems.append("CHANGELOG: entrada ja existe (ja aplicado?)")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    for rel, old, new, n, mode in PATCHES:
        raw, nl = texts[rel]
        texts[rel] = (raw.replace(norm(old, nl), norm(new, nl), 1 if mode == "first" else -1), nl)
    if a.dry_run:
        print(f"[DRY] {len(PATCHES)} patches OK + CHANGELOG"); return
    for rel, (raw, nl) in texts.items():
        (root / rel).write_bytes(raw.encode("utf-8")); print(f"[OK] {rel}")
    chg.write_bytes(craw.replace(anchor, anchor + norm(CHANGELOG_ENTRY, cnl) + cnl, 1).encode("utf-8")); print("[OK] docs/changelog/CHANGELOG.md")
    print("\nSeguir com: node --check static/js/watcherdb_i18n_v2.js ; browser em janela privada (sem localStorage) -> deve abrir em EN")


if __name__ == "__main__":
    main()
