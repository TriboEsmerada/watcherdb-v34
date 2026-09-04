#!/usr/bin/env python3
"""Lotes B/C do linguista -- acentos em pt.json e es.json -- PASSO 1 (aplica pares confirmados pelo linguista).

Fonte: docs/context/I18N_ACENTOS_PT.json e I18N_ACENTOS_ES.json — arrays de {"path","old","new"} produzidos pelo
v33-i18n-linguist (04/09) a partir de um varrimento mecanico (455 candidatos es, 227 pt) e confirmados palavra a
palavra. So' acentos/til/cedilha/ñ e grafia AO90 dessas palavras; termos e frases intactos.

Aplicacao por TEXTO (nunca round-trip json.dump: pt.json tem chaves duplicadas que se perderiam): para cada par,
substitui `"<chave-folha>": "<old>"` -> `"<chave-folha>": "<new>"` (old/new escapados como JSON). Cada par tem de
bater >= 1x; se bater 0x aborta ANTES de escrever. Depois valida json.loads e, para pt, a regex AO90 do teste.

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_ACENTOS_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_ACENTOS_PASSO1_apply.py
    py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py
Rollback: git checkout -- static/i18n/pt.json static/i18n/es.json docs/changelog/CHANGELOG.md
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
CHG = "docs/changelog/CHANGELOG.md"
LOTES = {"pt": "I18N_ACENTOS_PT.json", "es": "I18N_ACENTOS_ES.json"}
AO90_BAD = re.compile(r"\b(detecta|detectad[ao]s?|activ[ao]s?|direct[ao]s?|óptim[ao]s?|objecto|acção|acções|actual|actualiz\w*|correcto|correcção|projecto|selecção|direcção|contacto|facto)\b", re.I)


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def jstr(s):
    return json.dumps(s, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems, outs, stats = [], {}, {}
    for loc, side in LOTES.items():
        sp = HERE / side
        if not sp.exists(): problems.append(f"sidecar em falta: {sp}"); continue
        pairs = json.loads(sp.read_bytes().decode("utf-8"))
        raw, nl = read(root / f"static/i18n/{loc}.json"); new = raw; hits = 0
        for i, p in enumerate(pairs):
            key = p["path"].split(".")[-1]
            if p["old"] == p["new"]: problems.append(f"{loc}[{i}] old==new: {p['path']}"); continue
            if re.findall(r"\{[^}]*\}", p["old"]) != re.findall(r"\{[^}]*\}", p["new"]): problems.append(f"{loc}[{i}] placeholders diferentes: {p['path']}"); continue
            old_t = f'"{key}": {jstr(p["old"])}'; new_t = f'"{key}": {jstr(p["new"])}'
            c = new.count(old_t)
            if c == 0:
                # mesma chave-folha + mesmo valor noutro namespace: um par anterior ja' substituiu as duas ocorrencias
                if new_t in new: continue
                problems.append(f"{loc}[{i}] 0x no ficheiro: {p['path']} = {p['old'][:60]!r}"); continue
            new = new.replace(old_t, new_t); hits += c
        try: json.loads(new)
        except Exception as ex: problems.append(f"{loc}.json invalido apos patch: {ex}")
        if loc == "pt":
            bad = sorted({m.group(0) for m in AO90_BAD.finditer(new) if m.group(0).lower() not in {m2.group(0).lower() for m2 in AO90_BAD.finditer(raw)}})
            if bad: problems.append(f"pt: grafia pre-AO90 introduzida: {bad}")
        outs[loc] = (new, nl); stats[loc] = (len(pairs), hits)
    # Overlay pt-BR: um override que fique IGUAL ao pt corrigido e' redundante (o teste de paridade rejeita) -> remove-se.
    ptbr_new, ptbr_removed = None, []
    if "pt" in outs:
        pt_d = json.loads(outs["pt"][0]); ptbr_raw, ptbr_nl = read(root / "static/i18n/pt-BR.json"); ptbr_d = json.loads(ptbr_raw)
        def prune(o, ref, path=""):
            for k in list(o.keys()):
                r = ref.get(k) if isinstance(ref, dict) else None
                if isinstance(o[k], dict):
                    prune(o[k], r or {}, f"{path}.{k}" if path else k)
                    if not o[k]: del o[k]
                elif o[k] == r:
                    ptbr_removed.append(f"{path}.{k}" if path else k); del o[k]
        prune(ptbr_d, pt_d)
        if ptbr_removed:
            ptbr_new = json.dumps(ptbr_d, ensure_ascii=False, indent=2).replace("\n", ptbr_nl) + ptbr_nl
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "Lotes B/C do linguista" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print(f"[ABORT] nada foi escrito ({len(problems)} problemas):"); [print("   -", x) for x in problems[:40]]; sys.exit(2)
    for loc, (n, h) in stats.items(): print(f"  {loc}: {n} pares -> {h} ocorrencias")
    if ptbr_removed: print(f"  pt-BR: {len(ptbr_removed)} overrides ficam redundantes e saem: {ptbr_removed}")
    if a.dry_run: print("[DRY] OK"); return
    for loc, (new, nl) in outs.items():
        (root / f"static/i18n/{loc}.json").write_bytes(new.encode("utf-8")); print(f"[OK] static/i18n/{loc}.json")
    if ptbr_new is not None:
        (root / "static/i18n/pt-BR.json").write_bytes(ptbr_new.encode("utf-8")); print("[OK] static/i18n/pt-BR.json (overrides redundantes removidos)")
    entry = ("- **Lotes B/C do linguista: acentuação em pt.json e es.json** (owner: acentos correctos como P1; o "
             "screenshot em espanhol de 04/09 mostrava \"Tamano\", \"diagnostico\", \"analisis\"). "
             f"{stats['pt'][0]} chaves em português e {stats['es'][0]} em espanhol ganham os acentos, til, cedilha e ñ "
             "em falta, sem mudar termos nem frases; confirmados palavra a palavra pelo v33-i18n-linguist a partir de "
             "um varrimento mecânico. [tier: Std]" + cnl)
    (root / CHG).write_bytes(craw.replace(anchor, anchor + entry + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: pytest tests/unit/test_i18n_parity.py --no-cov ; scripts/i18n_validate.py ; browser Ctrl+F5 em ES e PT")


if __name__ == "__main__":
    main()
