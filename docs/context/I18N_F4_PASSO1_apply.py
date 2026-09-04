#!/usr/bin/env python3
"""Wave BUG-003 -- Lote F4: acentos e AO90 nos campos PT de KPI_DOCUMENTATION (documentacao dos KPIs, abre em cada "?").

So' texto, so' dentro do bloco `const KPI_DOCUMENTATION = {...};` do portal e so' fora dos sub-blocos i18n.en/es.
Sidecar: docs/context/I18N_F4_PAIRS.json = [{"old": "...", "new": "...", "class": "fix|ok"}] (v33-i18n-linguist).
Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F4_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F4_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html docs/changelog/CHANGELOG.md
"""
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"
SIDE = HERE / "I18N_F4_PAIRS.json"

CHANGELOG_ENTRY = """- **i18n lote F4 (wave BUG-003): acentuação e AO90 na documentação dos KPIs** (o texto que abre em
  cada "?" do dashboard). Os campos portugueses de `KPI_DOCUMENTATION` que ainda tinham acentos em
  falta ou grafia pré-AO90 ("actualizado", "activa", "detectada", "directamente", "afectadas")
  foram corrigidos sem reescrever uma frase; os blocos en/es, já correctos, não foram tocados.
  {n} literais. Só texto. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    if not SIDE.exists(): print(f"[ABORT] sidecar em falta: {SIDE}"); sys.exit(2)
    pairs = [p for p in json.loads(SIDE.read_text(encoding="utf-8")) if p.get("class") == "fix" and p["old"] != p["new"]]
    raw, nl = read(root / HTML)
    lines = raw.split(nl)
    start = next((i for i, l in enumerate(lines) if re.search(r"const KPI_DOCUMENTATION\s*=", l)), None)
    if start is None: print("[ABORT] KPI_DOCUMENTATION nao encontrado"); sys.exit(2)
    end = next(i for i in range(start + 1, len(lines)) if re.match(r"^        \};\s*$", lines[i]))
    # linhas dentro de i18n: {...} ficam intocadas
    protected, in_i18n, brace = set(), False, 0
    for i in range(start, end + 1):
        l = lines[i]
        if not in_i18n and re.match(r"\s*i18n:\s*\{", l): in_i18n = True; brace = l.count("{") - l.count("}"); protected.add(i); continue
        if in_i18n:
            protected.add(i); brace += l.count("{") - l.count("}")
            if brace <= 0: in_i18n = False
    problems, total = [], 0
    for p in pairs:
        c = sum(lines[i].count(p["old"]) for i in range(start, end + 1) if i not in protected)
        if c < 1: problems.append(f"nao encontrado no bloco PT: {p['old'][:80]!r}")
        for ph in re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}|\$\{[^}]*\}", p["old"]):
            if ph not in p["new"]: problems.append(f"placeholder perdido {ph}: {p['old'][:60]!r}")
        total += c
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada 1x")
    if "lote F4" in craw: problems.append("CHANGELOG: entrada F4 ja existe")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] {len(pairs)} literais -> {total} ocorrencias no bloco PT (linhas {start+1}-{end+1}, {len(protected)} linhas i18n protegidas)"); return
    for i in range(start, end + 1):
        if i in protected: continue
        for p in pairs: lines[i] = lines[i].replace(p["old"], p["new"])
    (root / HTML).write_bytes(nl.join(lines).encode("utf-8")); print(f"[OK] {HTML} ({total} ocorrencias)")
    entry = CHANGELOG_ENTRY.replace("{n}", str(len(pairs))).replace("\n", cnl)
    (root / CHG).write_bytes(craw.replace(anchor, anchor + entry + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: node --check nos blocos (validador scratchpad) ; browser: abrir um '?' de KPI em PT")


if __name__ == "__main__":
    main()
