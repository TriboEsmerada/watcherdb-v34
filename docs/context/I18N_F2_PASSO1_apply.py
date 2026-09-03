#!/usr/bin/env python3
"""Wave BUG-003 -- Lote F2: titulos dos cartoes principais (KPI_METADATA) seguem o idioma escolhido.

Decisao owner 2026-09-03 ("siga com o recomendado"): title/subtitle/modalTitle dos 24 cartoes que ainda
eram literais (mistura EN/PT) passam ao MESMO padrao que cpu-critical/memory-critical/jobs-* ja usavam:
    get title() { return _kpiT('kpi_meta.<id>.title', '<literal actual>'); }
Nenhum sitio de render muda (kpi.title / kpi.subtitle / kpi.modalTitle continuam a funcionar).
Traducoes: v33-i18n-linguist (sidecar docs/context/I18N_F2_KEYS.json). Namespace novo: kpi_meta.<id>.*
(ids com hifen; o motor achata por '.').

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F2_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F2_PASSO1_apply.py
Impacto: templates/watcherdb_portal.html (bloco KPI_METADATA ~33328-34024) + static/i18n/{pt,pt-BR,en,es}.json
+ CHANGELOG. Zero backend.
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
HTML = "templates/watcherdb_portal.html"
CHG = "docs/changelog/CHANGELOG.md"
SIDE = HERE / "I18N_F2_KEYS.json"
FIELDS = {"title": "title", "subtitle": "subtitle", "modalTitle": "modal_title"}

CHANGELOG_ENTRY = """- **i18n lote F2 (wave BUG-003): os títulos dos cartões principais do dashboard seguem o idioma
  escolhido** (decisão owner 03/09). Os 24 cartões de `KPI_METADATA` que ainda tinham título,
  subtítulo e título de modal como literais (inglês puro misturado com português: "DB Not
  Availability", "Instances OK" ao lado de "TempDB - Disco Crítico") passam ao padrão de getter
  que `cpu-critical`, `memory-critical` e os cartões de Jobs já usavam, com chaves `kpi_meta.<id>.*`
  em 4 idiomas e o literal actual como fallback. Nenhum sítio de render muda. Traduções do
  v33-i18n-linguist; "UnHealthy" → "Unhealthy", "DB Not Availability" → "DB Unavailable". [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def js_str(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def add_namespace(path: Path, ns: str, tree: dict):
    raw, nl = read(path)
    body = raw.rstrip()
    assert body.endswith("}"), path
    if '"%s": {' % ns in raw:
        raise SystemExit(f"[ABORT] {path.name}: namespace {ns} ja existe")
    dumped = json.dumps(tree, ensure_ascii=False, indent=2)
    dumped = nl.join("  " + ln for ln in dumped.splitlines())  # indenta 2 (fica dentro do objecto raiz)
    block = "," + nl + '  "%s": ' % ns + dumped.lstrip() + nl + "}" + nl
    new = body[:-1].rstrip() + block
    json.loads(new)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    print(f"root: {root}  dry-run={a.dry_run}")
    if not SIDE.exists():
        print(f"[ABORT] sidecar em falta: {SIDE}"); sys.exit(2)
    keys = json.loads(SIDE.read_text(encoding="utf-8"))  # {id: {field: {en,pt_pt,pt_br?,es}}}

    raw, nl = read(root / HTML)
    lines = raw.split(nl)
    problems, patched = [], 0
    trees = {"pt": {}, "en": {}, "es": {}, "pt-BR": {}}
    # localiza o bloco KPI_METADATA
    try:
        start = next(i for i, l in enumerate(lines) if re.search(r"const KPI_METADATA\s*=", l))
    except StopIteration:
        print("[ABORT] KPI_METADATA nao encontrado"); sys.exit(2)
    end = next(i for i in range(start, start + 2000) if re.match(r"\s*\};\s*$", lines[i]))
    for kid, fields in keys.items():
        idx = [i for i in range(start, end) if re.match(r"\s*id:\s*'%s',\s*$" % re.escape(kid), lines[i])]
        if len(idx) != 1:
            problems.append(f"{kid}: id encontrado {len(idx)}x no bloco"); continue
        i0 = idx[0]
        # limite da entrada = linha do proximo "id:" (as entradas tem ~15 linhas; uma janela fixa entrava na seguinte)
        i1 = next((i for i in range(i0 + 1, end) if re.match(r"\s*id:\s*'", lines[i])), end)
        for jsf, jf in FIELDS.items():
            if jf not in fields:
                continue
            hit = [i for i in range(i0, i1) if re.match(r"\s*%s:\s*'((?:[^'\\]|\\.)*)',\s*$" % jsf, lines[i])]
            if len(hit) != 1:
                problems.append(f"{kid}.{jsf}: literal encontrado {len(hit)}x (esperado 1; ja getter?)"); continue
            li = hit[0]
            m = re.match(r"(\s*)%s:\s*'((?:[^'\\]|\\.)*)',\s*$" % jsf, lines[li])
            indent, literal = m.group(1), m.group(2).replace("\\'", "'")
            vals = fields[jf]
            for loc in ("en", "pt_pt", "es"):
                if loc not in vals or "'" in vals[loc]:
                    problems.append(f"{kid}.{jf}.{loc}: em falta ou com apostrofo (entra em onclick)")
            key = f"kpi_meta.{kid}.{jf}"
            lines[li] = f"{indent}get {jsf}() {{ return _kpiT('{key}', {js_str(literal)}); }},"
            trees["pt"].setdefault(kid, {})[jf] = vals.get("pt_pt")
            trees["en"].setdefault(kid, {})[jf] = vals.get("en")
            trees["es"].setdefault(kid, {})[jf] = vals.get("es")
            if vals.get("pt_br") and vals["pt_br"] != vals.get("pt_pt"):
                trees["pt-BR"].setdefault(kid, {})[jf] = vals["pt_br"]
            patched += 1
    for loc in ("pt", "pt-BR", "en", "es"):
        p = root / f"static/i18n/{loc}.json"
        if not p.exists(): problems.append(f"{p} nao existe")
        elif '"kpi_meta": {' in p.read_text(encoding="utf-8"): problems.append(f"{loc}.json ja tem kpi_meta")
    chg_raw, chg_nl = read(root / CHG)
    anchor = norm("## [Unreleased]\n\n### Changed\n\n", chg_nl)
    if chg_raw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada 1x")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    outs = {root / f"static/i18n/{loc}.json": add_namespace(root / f"static/i18n/{loc}.json", "kpi_meta", trees[loc]) for loc in ("pt", "en", "es", "pt-BR")}
    n_keys = sum(len(v) for v in trees["pt"].values())
    if a.dry_run:
        print(f"[DRY] {patched} literais -> getters em {len(keys)} cartoes; kpi_meta: {n_keys} chaves (pt/en/es) + {sum(len(v) for v in trees['pt-BR'].values())} overrides pt-BR; CHANGELOG OK"); return
    (root / HTML).write_bytes(nl.join(lines).encode("utf-8")); print(f"[OK] {HTML} ({patched} getters)")
    for p, txt in outs.items():
        p.write_bytes(txt.encode("utf-8")); print(f"[OK] {p.relative_to(root)}")
    (root / CHG).write_bytes(chg_raw.replace(anchor, anchor + norm(CHANGELOG_ENTRY, chg_nl) + chg_nl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser: cartoes do dashboard em EN/PT/PT-BR/ES")


if __name__ == "__main__":
    main()
