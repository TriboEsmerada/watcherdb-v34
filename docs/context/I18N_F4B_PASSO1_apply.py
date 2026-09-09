#!/usr/bin/env python3
"""Lote F4b (BUG-003) -- titulos da modal "KPI Documentation" seguem o idioma + nome de instancia de cliente fora da ajuda.

Owner 09/09 (screenshot em EN): "a interrogacao dos KPIs nao esta sendo traduzida como deveria". As categorias traduzem
(tCategory) mas os 29 `title:` de KPI_DOCUMENTATION (portal 40063-41545) sao PT cru sem chave, usados em 3 sitios:
menu (~41592), filtro de pesquisa (~41631) e cabecalho do conteudo (~41674). Os ids da documentacao coincidem com os
de KPI_METADATA, mas os titulos da ajuda sao rotulos proprios (mais curtos que kpi_meta.*.modal_title) e 5 ids nao
existem la' -> namespace proprio `kpi_doc.<id>.title` em pt/en/es (pt = texto actual; pt-BR cai no pt).
Fix: helper _docTitle(kpiId, kpi) = _kpiT('kpi_doc.<id>.title', kpi.title) e os 3 sitios passam a usa-lo.
Bonus (repo publico): o texto de ajuda de backup-jobs-disabled citava "DBA_FULL_BACKUP em SQLMDMQLT03_I01" (pt/en/es)
-> "um job de backup FULL numa instancia de QA".

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F4B_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F4B_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"
TITLES = HERE / "I18N_F4B_TITLES.json"

HELPER_ANCHOR = "        function _kpiTp(key, fb, p) { let s = _kpiT(key, fb); Object.keys(p || {}).forEach(k => { s = s.split('{' + k + '}').join(p[k]); }); return s; }  // placeholders {n} (lote F1 2026-09-03)\n"
HELPER_NEW = HELPER_ANCHOR + "        function _docTitle(kpiId, kpi) { return _kpiT('kpi_doc.' + kpiId + '.title', kpi.title); }  // lote F4b 2026-09-09: titulos da modal de documentacao seguem o idioma (fallback = title PT)\n"

PATCHES = [
    ('<span style="font-size: 13px;">${kpi.title}</span>', '<span style="font-size: 13px;">${_docTitle(kpiId, kpi)}</span>'),
    ("const matches = kpi.title.toLowerCase().includes(term) ||", "const matches = _docTitle(kpiId, kpi).toLowerCase().includes(term) ||\n                               kpi.title.toLowerCase().includes(term) ||"),
    ('margin: 0 0 4px 0;">${kpi.title}</h3>', 'margin: 0 0 4px 0;">${_docTitle(kpiId, kpi)}</h3>'),
    ("Caso real: DBA_FULL_BACKUP em SQLMDMQLT03_I01 esteve 5 semanas sem correr", "Caso real: um job de backup FULL numa instância de QA esteve 5 semanas sem correr"),
    ("Real case: DBA_FULL_BACKUP on SQLMDMQLT03_I01 went 5 weeks without running", "Real case: a FULL backup job on a QA instance went 5 weeks without running"),
    ("Caso real: DBA_FULL_BACKUP en SQLMDMQLT03_I01 estuvo 5 semanas sin ejecutarse", "Caso real: un job de backup FULL en una instancia de QA estuvo 5 semanas sin ejecutarse"),
]
CHANGELOG_ENTRY = """- **Lote F4b (BUG-003): os títulos da modal "KPI Documentation" seguem o idioma** (owner 09/09: "a
  interrogação dos KPIs não está sendo traduzida"). As categorias já traduziam; os 29 títulos eram
  português cru sem chave, no menu, na pesquisa e no cabeçalho. Namespace novo `kpi_doc.<id>.title`
  em pt/en/es (pt = texto actual, pt-BR herda) com fallback ao título antigo. De caminho, o texto de
  ajuda dos jobs de backup deixa de citar uma instância de cliente pelo nome. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def append_namespace(raw, nl, name, obj):
    if f'"{name}": {{' in raw: return None, f"namespace {name} ja existe"
    body = raw.rstrip()
    if not body.endswith("}"): return None, "ficheiro nao termina em }"
    block = json.dumps({name: obj}, ensure_ascii=False, indent=2)[1:-1].rstrip()  # sem as chavetas exteriores
    new = body[:-1].rstrip() + "," + "\n" + block + "\n}" + "\n"
    try: json.loads(new)
    except Exception as ex: return None, f"json invalido: {ex}"
    return new.replace("\n", nl), None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems, outs = [], {}
    titles = json.loads(TITLES.read_bytes().decode("utf-8"))
    if len(titles) != 29: problems.append(f"sidecar: esperado 29 ids, tem {len(titles)}")
    html, hnl = read(root / HTML)
    if html.count(norm(HELPER_ANCHOR, hnl)) != 1: problems.append("helper: ancora _kpiTp nao encontrada 1x")
    if "_docTitle(" in html: problems.append("helper _docTitle ja existe (ja aplicado?)")
    for old, new in PATCHES:
        c = html.count(norm(old, hnl))
        if c != 1: problems.append(f"patch esperado 1x, encontrado {c}x: {old[:70]!r}")
    # os ids do sidecar tem de existir em KPI_DOCUMENTATION
    for kid, v in titles.items():
        if html.count(f"            '{kid}': {{") < 1: problems.append(f"id {kid} nao existe em KPI_DOCUMENTATION")
        if not all(v.get(l) for l in ("pt", "en", "es")): problems.append(f"id {kid}: falta pt/en/es")
    for loc in ("pt", "en", "es"):
        raw, nl = read(root / f"static/i18n/{loc}.json")
        new, err = append_namespace(raw, nl, "kpi_doc", {kid: {"title": v[loc]} for kid, v in titles.items()})
        if err: problems.append(f"{loc}.json: {err}")
        else: outs[f"static/i18n/{loc}.json"] = new
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "Lote F4b (BUG-003)" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] helper + {len(PATCHES)} patches no portal, kpi_doc ({len(titles)} ids) em pt/en/es, CHANGELOG OK"); return
    html = html.replace(norm(HELPER_ANCHOR, hnl), norm(HELPER_NEW, hnl))
    for old, new in PATCHES: html = html.replace(norm(old, hnl), norm(new, hnl))
    (root / HTML).write_bytes(html.encode("utf-8")); print(f"[OK] {HTML}")
    for rel, txt in outs.items(): (root / rel).write_bytes(txt.encode("utf-8")); print(f"[OK] {rel}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser Ctrl+F5 -> '?' dos KPIs em EN/ES/PT")


if __name__ == "__main__":
    main()
