#!/usr/bin/env python3
"""Botoes de navegacao da instancia (Overview, Performance, Always On, ...) nao traduziam -- PASSO 1.

Owner 04/09 (screenshot em ES): "os nomes do menu nao traduziram". Causa: os 16 <button class="nav-btn">
(templates/watcherdb_portal.html ~4771-4821) tem o rotulo hardcoded em ingles, sem data-i18n. O namespace
`tab.*` ja' existe nos 3 locales (es traduzido, pt em INGLES, "Sessions" por traduzir em es) mas so' e' usado
para o separador do dashboard. Fix:
  1. cada rotulo passa a <span data-i18n="tab.<chave>">Label</span> (o span e' obrigatorio: _translateElement
     substitui textContent do elemento e apagaria o <i> do icone se o data-i18n fosse no <button>);
  2. pt.json: tab.* em pt-PT (Visão Geral, Espaço, Disco, Memória, Serviços, Sessões, Segurança, Utilizadores,
     Encriptação); es.json: sessions -> Sesiones; chave nova tab.performance nos 3; pt-BR: tab.users -> Usuários.
Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_NAV_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_NAV_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"

# (data-tab, chave tab.*, icone, label actual)
BUTTONS = [
    ("overview", "overview", "fa-home", "Overview"),
    ("performance", "performance", "fa-tachometer-alt", "Performance"),
    ("alwayson", "alwayson", "fa-sync-alt", "Always On"),
    ("backup", "backup", "fa-database", "Backup"),
    ("space", "space", "fa-hdd", "Space"),
    ("disk", "disk", "fa-server", "Disk"),
    ("encrypted", "encrypted", "fa-lock", "Encrypted"),
    ("cpu", "cpu", "fa-microchip", "CPU"),
    ("memory", "memory", "fa-memory", "Memory"),
    ("services", "services", "fa-cogs", "Services"),
    ("log", "log", "fa-file-alt", "Log"),
    ("sessions", "sessions", "fa-user-clock", "Sessions"),
    ("security", "security", "fa-shield-alt", "Security"),
    ("users", "users", "fa-users", "Users"),
    ("jobs", "jobs", "fa-clock", "Jobs"),
    ("sql-diagnostics", "sql_diagnostics", "fa-stethoscope", "SQL Diag"),
]
# valores por locale dentro do bloco "tab": {...}  (None = manter)
TAB_VALUES = {
    "pt": {"overview": "Visão Geral", "space": "Espaço", "disk": "Disco", "encrypted": "Encriptação", "memory": "Memória",
           "services": "Serviços", "sessions": "Sessões", "security": "Segurança", "users": "Utilizadores", "performance": "Performance"},
    "es": {"sessions": "Sesiones", "performance": "Performance"},
    "en": {"performance": "Performance"},
}
PTBR_TAB = {"users": "Usuários"}

CHANGELOG_ENTRY = """- **Os botões de navegação da instância passam a traduzir** (owner 04/09, em espanhol: "os nomes
  do menu não traduziram"). Overview, Performance, Always On, Backup, Space, Disk, Encrypted, CPU,
  Memory, Services, Log, Sessions, Security, Users, Jobs e SQL Diag estavam hardcoded em inglês;
  ganham `data-i18n="tab.*"` (namespace que já existia mas só servia o separador do dashboard).
  Em português o bloco `tab.*` estava em inglês e passa a pt-PT (Visão Geral, Espaço, Disco,
  Memória, Serviços, Sessões, Segurança, Utilizadores, Encriptação); espanhol ganha "Sesiones";
  chave nova `tab.performance`. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def patch_tab_block(raw, nl, values, add_performance=True):
    """Substitui valores dentro do bloco "tab": {...} (2 espacos) por texto; devolve (novo, problemas)."""
    lines = raw.split(nl); problems = []
    try:
        s = next(i for i, l in enumerate(lines) if l == '  "tab": {')
        e = next(i for i in range(s + 1, len(lines)) if lines[i].startswith("  }"))
    except StopIteration:
        return raw, ["bloco \"tab\" nao encontrado"]
    for key, val in values.items():
        if key == "performance":
            continue
        hit = [i for i in range(s + 1, e) if re.match(r'\s*"%s": "' % key, lines[i])]
        if len(hit) != 1:
            problems.append(f'tab.{key}: {len(hit)}x no bloco'); continue
        i = hit[0]
        comma = "," if lines[i].rstrip().endswith(",") else ""
        lines[i] = '    "%s": %s%s' % (key, json.dumps(val, ensure_ascii=False), comma)
    if "performance" in values:
        if any(re.match(r'\s*"performance":', lines[i]) for i in range(s + 1, e)):
            problems.append("tab.performance ja existe")
        else:
            lines.insert(s + 1, '    "performance": %s,' % json.dumps(values["performance"], ensure_ascii=False))
    return nl.join(lines), problems


def add_ptbr_tab(raw, nl):
    if '"tab": {' in raw: return raw, ['pt-BR ja tem bloco "tab"']
    body = raw.rstrip(); assert body.endswith("}")
    block = "," + nl + '  "tab": {' + nl + '    "users": "Usuários"' + nl + "  }" + nl + "}" + nl
    new = body[:-1].rstrip() + block; json.loads(new); return new, []


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems, outs = [], {}
    html, hnl = read(root / HTML)
    for tab, key, icon, label in BUTTONS:
        old = 'data-tab="%s" onclick="showTab(\'%s\')"' % (tab, tab)
        m = re.search(re.escape(old) + r'[^\n]*\n(\s*)<i class="fas %s"></i> %s\n' % (re.escape(icon), re.escape(label)), html.replace("\r\n", "\n"))
        if not m: problems.append(f"botao {tab}: markup nao encontrado (icone {icon}, label {label!r})"); continue
        seg_old = norm('<i class="fas %s"></i> %s\n' % (icon, label), hnl)
        seg_new = norm('<i class="fas %s"></i> <span data-i18n="tab.%s">%s</span>\n' % (icon, key, label), hnl)
        # substitui so' a ocorrencia que segue o botao certo
        start = html.find(norm(old, hnl)); pos = html.find(seg_old, start)
        if start < 0 or pos < 0 or pos - start > 400: problems.append(f"botao {tab}: ancora fora de alcance"); continue
        html = html[:pos] + seg_new + html[pos + len(seg_old):]
    outs[HTML] = html
    for loc, vals in TAB_VALUES.items():
        raw, nl = read(root / f"static/i18n/{loc}.json")
        new, pr = patch_tab_block(raw, nl, vals); problems += [f"{loc}: {x}" for x in pr]
        try: json.loads(new)
        except Exception as ex: problems.append(f"{loc}.json invalido apos patch: {ex}")
        outs[f"static/i18n/{loc}.json"] = new
    raw, nl = read(root / "static/i18n/pt-BR.json"); new, pr = add_ptbr_tab(raw, nl); problems += pr; outs["static/i18n/pt-BR.json"] = new
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "botões de navegação da instância passam a traduzir" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] 16 botoes + tab.* em pt/es/en (+performance) + pt-BR.users + CHANGELOG OK"); return
    for rel, txt in outs.items():
        (root / rel).write_bytes(txt.encode("utf-8")); print(f"[OK] {rel}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser Ctrl+F5: menu da instancia em EN/PT/PT-BR/ES")


if __name__ == "__main__":
    main()
