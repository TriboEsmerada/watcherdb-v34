#!/usr/bin/env python3
"""Lote F7 (BUG-003) -- checklist de carregamento das abas ("A carregar Filegroups e espaco por database...") segue o idioma.

Owner 09/09 (screenshot EN, aba Space): "achei mais 1 caso". O checklist generico startLoadingChecklist (portal ~7186-7244)
mostra "A carregar ${label}..." / "sem resposta (Ns)" hardcoded, e os 26 lc.track('<rotulo PT>') das 13 abas passam o
rotulo em PT cru. Fix: namespace lc.* em pt/en/es (25 rotulos + loading + no_response); renderer resolve por chave com
placeholder via _kpiTp (fallback = literal); os 26 call sites passam a t('lc.<chave>'). pt-BR herda do pt.

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F7_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F7_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"

# chave: (literal actual no portal, pt-PT, en-US, es)
STEPS = {
    "windows_event_log": ("Windows Event Log", "Windows Event Log", "Windows Event Log", "Windows Event Log"),
    "sql_error_log": ("SQL Error Log", "SQL Error Log", "SQL Error Log", "SQL Error Log"),
    "sql_server_error_log": ("SQL Server Error Log", "SQL Server Error Log", "SQL Server Error Log", "SQL Server Error Log"),
    "logins_roles_perms": ("Logins, roles e permissoes", "Logins, roles e permissões", "Logins, roles and permissions", "Logins, roles y permisos"),
    "jobs_history_schedules": ("Jobs, historico e schedules", "Jobs, histórico e schedules", "Jobs, history and schedules", "Jobs, historial y schedules"),
    "disk_volumes": ("Volumes de disco", "Volumes de disco", "Disk volumes", "Volúmenes de disco"),
    "unallocated_space": ("Espaco nao alocado", "Espaço não alocado", "Unallocated space", "Espacio no asignado"),
    "io_diagnostics": ("Diagnostico de I/O", "Diagnóstico de I/O", "I/O diagnostics", "Diagnóstico de I/O"),
    "log_space": ("Log space", "Log space", "Log space", "Log space"),
    "history_90d": ("Historico (90d)", "Histórico (90d)", "History (90d)", "Historial (90d)"),
    "filegroups_space": ("Filegroups e espaco por database", "Filegroups e espaço por database", "Filegroups and space per database", "Filegroups y espacio por database"),
    "memory_analysis": ("Analise de memoria (DMVs)", "Análise de memória (DMVs)", "Memory analysis (DMVs)", "Análisis de memoria (DMVs)"),
    "cpu_analysis": ("Analise de CPU (DMVs)", "Análise de CPU (DMVs)", "CPU analysis (DMVs)", "Análisis de CPU (DMVs)"),
    "security_checks": ("Checks de seguranca", "Checks de segurança", "Security checks", "Checks de seguridad"),
    "tde_server": ("Estado TDE do servidor", "Estado TDE do servidor", "Server TDE status", "Estado TDE del servidor"),
    "tde_per_db": ("TDE por database", "TDE por database", "TDE per database", "TDE por database"),
    "backup_gaps_30d": ("Gaps de backup (30d)", "Gaps de backup (30d)", "Backup gaps (30d)", "Gaps de backup (30d)"),
    "backup_jobs": ("Jobs de backup", "Jobs de backup", "Backup jobs", "Jobs de backup"),
    "schedule_collisions": ("Colisoes de schedule", "Colisões de schedule", "Schedule collisions", "Colisiones de schedule"),
    "alwayson_validation": ("Validacao Always On", "Validação Always On", "Always On validation", "Validación Always On"),
    "alwayson_events_30d": ("Eventos Always On (30d)", "Eventos Always On (30d)", "Always On events (30d)", "Eventos Always On (30d)"),
    "ag_state": ("Estado do Availability Group", "Estado do Availability Group", "Availability Group state", "Estado del Availability Group"),
    "database_list": ("Lista de databases", "Lista de databases", "Database list", "Lista de databases"),
    "custom_queries": ("Queries customizadas", "Queries customizadas", "Custom queries", "Queries personalizadas"),
    "sql_services_realtime": ("Servicos SQL (tempo real, sem cache)", "Serviços SQL (tempo real, sem cache)", "SQL services (real time, no cache)", "Servicios SQL (tiempo real, sin caché)"),
}
EXTRA = {
    "loading": ("A carregar {label}...", "Loading {label}...", "Cargando {label}..."),
    "no_response": ("sem resposta ({secs}s)", "no response ({secs}s)", "sin respuesta ({secs}s)"),
}
EXPECTED_CALLS = 26
SKEL = {  # skeleton do Overview (~15258): clone do checklist com rotulos proprios
    "skel_services": ("Serviços SQL", "SQL services", "Servicios SQL"),
    "skel_cpu": ("CPU", "CPU", "CPU"),
    "skel_memory": ("Memória", "Memory", "Memoria"),
    "skel_databases": ("Databases", "Databases", "Databases"),
    "skel_backup_summary": ("Backup — resumo", "Backup — summary", "Backup — resumen"),
    "skel_backup_gaps": ("Backup — gaps", "Backup — gaps", "Backup — gaps"),
    "skel_backup_patterns": ("Backup — padrões", "Backup — patterns", "Backup — patrones"),
}
RENDER_PATCHES = [
    ("            const _skelLabels = {\n                SERVICES: 'Serviços SQL',\n                CPU: 'CPU',\n                MEMORY: 'Memória',\n                DATABASES: 'Databases',\n                BACKUP_SUMMARY: 'Backup — resumo',\n                BACKUP_GAPS: 'Backup — gaps',\n                BACKUP_PATTERNS: 'Backup — padrões'\n            };",
     "            const _skelLabels = {  // lote F7 2026-09-09: rotulos por chave lc.skel_* (fallback = literal)\n                SERVICES: _kpiT('lc.skel_services', 'Serviços SQL'),\n                CPU: _kpiT('lc.skel_cpu', 'CPU'),\n                MEMORY: _kpiT('lc.skel_memory', 'Memória'),\n                DATABASES: _kpiT('lc.skel_databases', 'Databases'),\n                BACKUP_SUMMARY: _kpiT('lc.skel_backup_summary', 'Backup — resumo'),\n                BACKUP_GAPS: _kpiT('lc.skel_backup_gaps', 'Backup — gaps'),\n                BACKUP_PATTERNS: _kpiT('lc.skel_backup_patterns', 'Backup — padrões')\n            };"),
    ('item.innerHTML = `<i class="fas fa-circle-notch fa-spin" style="width: 16px; color: var(--color-text-link);"></i> A carregar ${_skelLabels[key] || key}...`;',
     'item.innerHTML = `<i class="fas fa-circle-notch fa-spin" style="width: 16px; color: var(--color-text-link);"></i> ${_kpiTp(\'lc.loading\', \'A carregar {label}...\', { label: _skelLabels[key] || key })}`;'),
    ('item.innerHTML = `<i class="fas fa-circle-notch fa-spin" style="width: 16px; color: var(--color-text-link);"></i> A carregar ${label}...`;',
     'item.innerHTML = `<i class="fas fa-circle-notch fa-spin" style="width: 16px; color: var(--color-text-link);"></i> ${_kpiTp(\'lc.loading\', \'A carregar {label}...\', { label })}`;  // lote F7 2026-09-09'),
    ('<span style="color: var(--color-text-disabled);">sem resposta (${secs}s)</span>`;',
     '<span style="color: var(--color-text-disabled);">${_kpiTp(\'lc.no_response\', \'sem resposta ({secs}s)\', { secs })}</span>`;'),
]
CHANGELOG_ENTRY = """- **Lote F7 (BUG-003): o checklist de carregamento das abas segue o idioma** (owner 09/09: "achei mais
  1 caso" — "A carregar Filegroups e espaço por database…" em inglês). Os 26 passos das 13 abas e o
  prefixo/estado do checklist ("A carregar…", "sem resposta") ganham chaves `lc.*` em pt-PT, en-US e es
  (pt-BR herda), com fallback ao literal. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


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
    html, hnl = read(root / HTML)
    total = 0
    for key, (lit, *_r) in STEPS.items():
        c = html.count(f".track('{lit}'")
        if c == 0: problems.append(f"lc.{key}: literal nao encontrado: {lit!r}")
        total += c
    if total != EXPECTED_CALLS: problems.append(f"call sites: esperado {EXPECTED_CALLS}, encontrado {total}")
    if "_kpiTp('lc." in html: problems.append("renderer ja aplicado")
    # "sem resposta" existe 2x: checklist generico (~7222) e skeleton do Overview (~15282) -- ambos traduzidos
    for old, new in RENDER_PATCHES:
        exp = 2 if "sem resposta" in old else 1
        o = old.replace("\n", hnl)
        if html.count(o) != exp: problems.append(f"renderer: patch esperado {exp}x, encontrado {html.count(o)}x: {old[:60]!r}")
    for i, loc in enumerate(("pt", "en", "es")):
        raw, nl = read(root / f"static/i18n/{loc}.json")
        obj = {k: v[i + 1] for k, v in STEPS.items()}; obj.update({k: v[i] for k, v in EXTRA.items()}); obj.update({k: v[i] for k, v in SKEL.items()})
        new, err = append_namespace(raw, nl, "lc", obj)
        if err: problems.append(f"{loc}.json: {err}")
        else: outs[f"static/i18n/{loc}.json"] = new
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "Lote F7 (BUG-003)" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] renderer + skeleton ({len(RENDER_PATCHES)} patches) + {total} call sites -> t('lc.*'), namespace lc ({len(STEPS) + len(EXTRA)} chaves) em pt/en/es, CHANGELOG OK"); return
    for key, (lit, *_r) in STEPS.items(): html = html.replace(f".track('{lit}'", f".track(t('lc.{key}')")
    for old, new in RENDER_PATCHES: html = html.replace(old.replace("\n", hnl), new.replace("\n", hnl))
    (root / HTML).write_bytes(html.encode("utf-8")); print(f"[OK] {HTML}")
    for rel, txt in outs.items(): (root / rel).write_bytes(txt.encode("utf-8")); print(f"[OK] {rel}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser Ctrl+F5 -> abrir aba Space/Disk em EN: 'Loading Filegroups and space per database...'")


if __name__ == "__main__":
    main()
