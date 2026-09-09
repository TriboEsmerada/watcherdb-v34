#!/usr/bin/env python3
"""Lote F3 (BUG-003) -- ajudas "?" dos cartoes das abas (CARD_HELP_TEXTS) seguem o idioma.

Owner 09/09: "acho que todas as interrogacoes nao traduzem" (screenshot: balao "Total de Volumes" em PT com EN activo).
CARD_HELP_TEXTS (portal ~18170-18944): 92 entradas, 444 textos (title, sections[].label/text, tip) em PT cru sem
acentos e sem chave; renderer showCardHelp (~18959-18993) usa-os directamente e tem "Dica:" hardcoded.

Fix (zero mudancas ao objecto JS -- fica como fallback):
  1. helper _chT(id, field, fb) = _kpiT('card_help.<id>.<field>', fb); showCardHelp passa a resolver title,
     s<i>_label, s<i>_text e tip por chave; "Dica:" -> t('help.tip') (chave ja existente nos 3 locales).
  2. namespace card_help.<id>.{title, s0_label, s0_text, ..., tip} em pt (pt-PT acentuado), en, es a partir do
     sidecar docs/context/I18N_F3_CARD_HELP.json (3 lotes do v33-i18n-linguist fundidos). pt-BR herda do pt.
Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F3_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F3_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"
SIDECAR = HERE / "I18N_F3_CARD_HELP.json"

HELPER_ANCHOR = "        function _docTitle(kpiId, kpi) { return _kpiT('kpi_doc.' + kpiId + '.title', kpi.title); }  // lote F4b 2026-09-09: titulos da modal de documentacao seguem o idioma (fallback = title PT)\n"
HELPER_NEW = HELPER_ANCHOR + "        function _chT(id, field, fb) { return _kpiT('card_help.' + id + '.' + field, fb); }  // lote F3 2026-09-09: ajudas \"?\" dos cartoes (CARD_HELP_TEXTS) seguem o idioma (fallback = literal PT)\n"

PATCHES = [
    ("            let sectionsHtml = config.sections.map(s => {\n                let hdr = '';\n                if (s.icon) {\n                    hdr = `<div style=\"display:flex;align-items:center;gap:8px;margin-bottom:4px;\"><i class=\"fas ${s.icon}\" style=\"color:${s.iconColor || '#3b82f6'};\"></i><strong style=\"color:${s.iconColor || 'var(--color-text-link)'};\">${s.label}</strong></div>`;\n                }\n                return `<div style=\"background:var(--color-bg-sunken);border-radius:6px;padding:10px;margin-bottom:8px;\">${hdr}<p style=\"margin:0;color:var(--color-text-tertiary);font-size:11px;\">${s.text}</p></div>`;\n            }).join('');",
     "            let sectionsHtml = config.sections.map((s, si) => {\n                let hdr = '';\n                const sLabel = _chT(helpKey, 's' + si + '_label', s.label), sText = _chT(helpKey, 's' + si + '_text', s.text);\n                if (s.icon) {\n                    hdr = `<div style=\"display:flex;align-items:center;gap:8px;margin-bottom:4px;\"><i class=\"fas ${s.icon}\" style=\"color:${s.iconColor || '#3b82f6'};\"></i><strong style=\"color:${s.iconColor || 'var(--color-text-link)'};\">${sLabel}</strong></div>`;\n                }\n                return `<div style=\"background:var(--color-bg-sunken);border-radius:6px;padding:10px;margin-bottom:8px;\">${hdr}<p style=\"margin:0;color:var(--color-text-tertiary);font-size:11px;\">${sText}</p></div>`;\n            }).join('');"),
    ("<i class=\"fas fa-lightbulb\"></i> <strong>Dica:</strong> ${config.tip}</div>` : '';",
     "<i class=\"fas fa-lightbulb\"></i> <strong>${t('help.tip')}</strong> ${_chT(helpKey, 'tip', config.tip)}</div>` : '';"),
    ("<i class=\"fas fa-info-circle\"></i> ${config.title}</strong><span onclick=\"document.getElementById('${helpId}').remove();\"",
     "<i class=\"fas fa-info-circle\"></i> ${_chT(helpKey, 'title', config.title)}</strong><span onclick=\"document.getElementById('${helpId}').remove();\""),
]
TEST = "tests/unit/test_i18n_parity.py"
# O teste AO90 marcava identificadores do SQL Server nos textos de ajuda (ACTIVE_TRANSACTION, active_end_date)
# como grafia pre-AO90. Identificadores (snake_case, MAIUSCULAS) saem antes da regex.
TEST_PATCHES = [
    ('    re.IGNORECASE,\n)\n\n\ndef test_pt_uses_post_ao90_spelling(dicts):',
     '    re.IGNORECASE,\n)\n# Identificadores tecnicos (snake_case, MAIUSCULAS: log_reuse_wait_desc, ACTIVE_TRANSACTION,\n# active_end_date) nao sao portugues -- saem antes da regex (lote F3 2026-09-09).\n_IDENTIFICADOR = re.compile(r"\\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\\b|\\b[A-Z]{4,}\\b")\n\n\ndef test_pt_uses_post_ao90_spelling(dicts):'),
    ("        if isinstance(v, str) and _PRE_AO90.search(v)\n    }",
     "        if isinstance(v, str) and _PRE_AO90.search(_IDENTIFICADOR.sub(\"\", v))\n    }"),
]
CHANGELOG_ENTRY = """- **Lote F3 (BUG-003): as ajudas "?" dos cartões das abas seguem o idioma** (owner 09/09: "acho que
  todas as interrogações não traduzem"). As 92 ajudas (444 textos: título, secções e dica) eram português
  cru sem acentos e sem chave. Namespace novo `card_help.<id>.*` em pt-PT acentuado, en-US e es (pt-BR
  herda), resolvido no balão com fallback ao literal; o rótulo "Dica:" passa a usar a chave que já existia.
  Traduções dos três lotes do v33-i18n-linguist. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def flatten(entry):
    d = {"title": entry["title"]}
    for i, s in enumerate(entry.get("sections", [])):
        d[f"s{i}_label"] = s["label"]; d[f"s{i}_text"] = s["text"]
    if entry.get("tip"): d["tip"] = entry["tip"]
    return d


def append_namespace(raw, nl, name, obj):
    if f'"{name}": {{' in raw: return None, f"namespace {name} ja existe"
    body = raw.rstrip()
    if not body.endswith("}"): return None, "ficheiro nao termina em }"
    block = json.dumps({name: obj}, ensure_ascii=False, indent=2)[1:-1].rstrip()
    new = body[:-1].rstrip() + ",\n" + block + "\n}\n"
    try: json.loads(new)
    except Exception as ex: return None, f"json invalido: {ex}"
    return new.replace("\n", nl), None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems, outs = [], {}
    side = json.loads(SIDECAR.read_bytes().decode("utf-8"))
    html, hnl = read(root / HTML)
    ids_in_js = set(re.findall(r"^            '([a-z0-9_-]+)': \{\s*$", html[html.find("const CARD_HELP_TEXTS = {"):html.find("const CARD_HELP_TEXTS = {") + 120000], re.M))
    for kid, v in side.items():
        if kid not in ids_in_js: problems.append(f"id {kid} nao existe em CARD_HELP_TEXTS"); continue
        for loc in ("pt", "en", "es"):
            if loc not in v: problems.append(f"{kid}: falta {loc}"); continue
            if len(v[loc].get("sections", [])) != len(v["pt"].get("sections", [])): problems.append(f"{kid}: {loc} tem nº de sections diferente do pt")
            if bool(v[loc].get("tip")) != bool(v["pt"].get("tip")): problems.append(f"{kid}: {loc} tip presente/ausente diferente do pt")
            for k, val in flatten(v[loc]).items():
                if not isinstance(val, str) or not val.strip(): problems.append(f"{kid}.{loc}.{k}: vazio")
                elif re.findall(r"\{[^}]*\}", val) != re.findall(r"\{[^}]*\}", flatten(v["pt"]).get(k, "")): problems.append(f"{kid}.{loc}.{k}: placeholders diferentes do pt")
    missing = sorted(ids_in_js - set(side)); print(f"  sidecar: {len(side)} ids; CARD_HELP_TEXTS: {len(ids_in_js)} ids; sem traducao (ficam no fallback PT): {len(missing)} {missing[:8]}")
    if html.count(norm(HELPER_ANCHOR, hnl)) != 1: problems.append("helper: ancora _docTitle (F4b) nao encontrada 1x -- correr o F4b primeiro")
    if "_chT(" in html: problems.append("helper _chT ja existe (ja aplicado?)")
    for old, new in PATCHES:
        c = html.count(norm(old, hnl))
        if c != 1: problems.append(f"patch esperado 1x, encontrado {c}x: {old[:60]!r}")
    for loc in ("pt", "en", "es"):
        raw, nl = read(root / f"static/i18n/{loc}.json")
        if '"tip": "' not in raw: problems.append(f"{loc}.json: chave help.tip em falta")
        new, err = append_namespace(raw, nl, "card_help", {kid: flatten(v[loc]) for kid, v in side.items() if loc in v})
        if err: problems.append(f"{loc}.json: {err}")
        else: outs[f"static/i18n/{loc}.json"] = new
    # pt-BR: so' as chaves em que o sidecar traz variante brasileira diferente do pt (overlay esparso)
    ptbr = {}
    for kid, v in side.items():
        if "pt-BR" in v:
            fp, fb = flatten(v["pt"]), flatten(v["pt-BR"])
            diff = {k: val for k, val in fb.items() if fp.get(k) != val}
            if diff: ptbr[kid] = diff
    if ptbr:
        raw, nl = read(root / "static/i18n/pt-BR.json")
        new, err = append_namespace(raw, nl, "card_help", ptbr)
        if err: problems.append(f"pt-BR.json: {err}")
        else: outs["static/i18n/pt-BR.json"] = new
    traw, tnl = read(root / TEST)
    if "_IDENTIFICADOR" in traw: problems.append("teste AO90 ja patched")
    for old, new in TEST_PATCHES:
        if traw.count(norm(old, tnl)) != 1: problems.append(f"teste: patch esperado 1x: {old[:50]!r}")
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "Lote F3 (BUG-003)" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print(f"[ABORT] nada foi escrito ({len(problems)} problemas):"); [print("   -", x) for x in problems[:40]]; sys.exit(2)
    n_keys = sum(len(flatten(v["pt"])) for v in side.values())
    if a.dry_run:
        print(f"[DRY] helper + {len(PATCHES)} patches no portal, card_help ({len(side)} ids, {n_keys} chaves) em pt/en/es, pt-BR overrides em {len(ptbr)} ids, CHANGELOG OK"); return
    html = html.replace(norm(HELPER_ANCHOR, hnl), norm(HELPER_NEW, hnl))
    for old, new in PATCHES: html = html.replace(norm(old, hnl), norm(new, hnl))
    (root / HTML).write_bytes(html.encode("utf-8")); print(f"[OK] {HTML}")
    for rel, txt in outs.items(): (root / rel).write_bytes(txt.encode("utf-8")); print(f"[OK] {rel}")
    for old, new in TEST_PATCHES: traw = traw.replace(norm(old, tnl), norm(new, tnl))
    (root / TEST).write_bytes(traw.encode("utf-8")); print(f"[OK] {TEST} (identificadores tecnicos fora da regex AO90)")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser Ctrl+F5 -> '?' de um cartao em EN/ES/PT")


if __name__ == "__main__":
    main()
