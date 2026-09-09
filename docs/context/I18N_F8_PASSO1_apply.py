#!/usr/bin/env python3
"""Lote F8 (BUG-003) -- painel LIVE (WatcherDB Live) segue o idioma.

Owner 09/09 (screenshot EN): "A carregar Fleet Dashboard...", "Filtrar instancia...", "Canal..." em PT cru. Regiao do
portal ~50239-51400 (painel LIVE + drilldown de disco): ~47 textos em strings JS ('...' + concat e template literals):
placeholders, tooltips, mensagens "Sem dados de ...", "Nenhum ... ativo", cabecalhos de seccao. Namespace live.* (47
chaves) em pt-PT/en/es via sidecar I18N_F8_KEYS.json; pt-BR herda. Tabelas com cabecalhos ja em ingles ficam.

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F8_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F8_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
HTML, CHG = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md"
KEYS = HERE / "I18N_F8_KEYS.json"

# (old, new, esperado)  -- strings '...' + concat usam ' + t() + '; template literals usam ${t()}
PATCHES = [
    ("<i class=\"fas fa-spinner fa-spin\"></i> Carregando arquivos...</div>' +", "<i class=\"fas fa-spinner fa-spin\"></i> ' + t('live.loading_files') + '</div>' +", 1),
    ("display:block\"></i>Nenhum arquivo de banco de dados encontrado neste drive</div>';", "display:block\"></i>' + t('live.no_db_files_drive') + '</div>';", 1),
    ('placeholder="Filtrar instancia..."', 'placeholder="${t(\'live.filter_instance\')}"', 1),
    ('                        <option value="">Canal...</option>', '                        <option value="">${t(\'live.channel_placeholder\')}</option>', 1),
    ("sel.innerHTML = '<option value=\"\">Canal...</option>';", "sel.innerHTML = '<option value=\"\">' + t('live.channel_placeholder') + '</option>';", 1),
    ('title="Pausar/Retomar">', 'title="${t(\'live.pause_resume\')}">', 1),
    ('<span title="Sessoes activas">', '<span title="${t(\'live.active_sessions\')}">', 1),
    ('<span title="Sessoes bloqueadas">', '<span title="${t(\'live.blocked_sessions\')}">', 1),
    ('margin-bottom:8px;">Selecione um canal ou clique em Fleet</div>', 'margin-bottom:8px;">${t(\'live.select_channel\')}</div>', 1),
    ('title="Abrir em janela separada"', 'title="${t(\'live.pop_out\')}"', 1),
    ("${msg || 'A carregar...'}", "${msg || t('live.loading')}", 1),
    ("const label = program === 'fleet' ? 'A carregar Fleet Dashboard...' : 'A carregar ' + program + '...';", "const label = program === 'fleet' ? t('live.loading_fleet') : _kpiTp('live.loading_program', 'A carregar {program}...', { program });  // lote F8 2026-09-09", 1),
    ("let errMsg = 'Sem dados disponiveis';", "let errMsg = t('live.no_data');", 1),
    ("errMsg = 'Instancia indisponivel ou sem permissao para este recurso';", "errMsg = t('live.instance_unavailable');", 1),
    ("display:block;\"></i>Nenhuma query em execucao</div>';", "display:block;\"></i>' + t('live.no_running_queries') + '</div>';", 1),
    ("(isIdle ? ' | sessao idle/a espera - nao e tempo de execucao' : '')", "(isIdle ? ' | ' + t('live.idle_not_exec') : '')", 1),
    # este title vive dentro de uma string '...' aninhada num ${cond ? '...' : ''} -> concatenacao, nao ${}
    ('title="Sessao a dormir ou a espera (transaccao aberta / fila) — nao e query em execucao"', 'title="\' + t(\'live.idle_title\') + \'"', 1),
    ("margin-right:6px;\"></i>Nenhum consumer activo no TempDB</div>';", "margin-right:6px;\"></i>' + t('live.no_tempdb_consumer') + '</div>';", 1),
    ("margin-right:6px;\"></i>Utilizacao Activa de TempDB (' + activeUsage.length + ' queries)</div>';", "margin-right:6px;\"></i>' + _kpiTp('live.tempdb_active_usage', 'Utilização Ativa de TempDB ({n} queries)', { n: activeUsage.length }) + '</div>';", 1),
    ("padding:40px;\">Sem wait stats significativos</div>';", "padding:40px;\">' + t('live.no_wait_stats') + '</div>';", 1),
    ("font-size:12px;\">Delta desde ultimo refresh (' + (_liveRefreshRate/1000) + 's)</div>' + h;", "font-size:12px;\">' + _kpiTp('live.delta_since_refresh', 'Delta desde o último refresh ({s}s)', { s: _liveRefreshRate/1000 }) + '</div>' + h;", 1),
    ("(_inst ? 'Instancia: <b style=\"color:var(--color-text-tertiary);\">' + _inst + '</b>' : 'Sem canal seleccionado')", "(_inst ? t('live.instance_label') + ': <b style=\"color:var(--color-text-tertiary);\">' + _inst + '</b>' : t('live.no_channel'))", 1),
    ("(_ts ? ' &middot; amostra ' + _ts : '') + ' &middot; so esta instancia (o Fleet agrega varias)</div>';", "(_ts ? ' &middot; ' + t('live.sample') + ' ' + _ts : '') + ' &middot; ' + t('live.only_this_instance') + '</div>';", 1),
    ("display:block;\"></i>Nenhum bloqueio activo' + (_inst ? ' em ' + _inst : '') + (_ts ? ' as ' + _ts : '') + '</div>';", "display:block;\"></i>' + t('live.no_blocking') + (_inst ? ' ' + t('live.in') + ' ' + _inst : '') + (_ts ? ' ' + t('live.at') + ' ' + _ts : '') + '</div>';", 1),
    ("margin-right:6px;\"></i>' + chains.length + ' sessao(oes) bloqueada(s)</div>';", "margin-right:6px;\"></i>' + _kpiTp('live.blocked_sessions_n', '{n} sessão(ões) bloqueada(s)', { n: chains.length }) + '</div>';", 1),
    ("_fleetCard('Sem dados', noData.length,", "_fleetCard(t('live.no_data_short'), noData.length,", 1),
    ('title="CPU acumulado (soma das threads em plano paralelo) — nao e tempo decorrido"', 'title="${t(\'live.cpu_title\')}"', 1),
    ("title=\"Tempo decorrido desde start_time${fIdle ? ' — sessao idle/a espera, nao e tempo de execucao' : ''}\"", "title=\"${t('live.elapsed_title')}${fIdle ? ' — ' + t('live.idle_not_exec') : ''}\"", 1),
    ("margin-right:4px;\"></i>Sem queries pesadas</div>';", "margin-right:4px;\"></i>' + t('live.no_heavy_queries') + '</div>';", 1),
    ("margin-right:6px;\"></i>BLOCKING ACTIVO (' + liveBlocking.length + ')<span style=\"font-weight:400;color:var(--color-text-disabled);margin-left:8px;\">sessoes bloqueadas nas instancias em drill (top 8) &middot; Blocked/Blocker = SPID &middot; clica na linha para abrir o canal</span></div>';",
     "margin-right:6px;\"></i>' + _kpiTp('live.blocking_active', 'BLOCKING ATIVO ({n})', { n: liveBlocking.length }) + '<span style=\"font-weight:400;color:var(--color-text-disabled);margin-left:8px;\">' + t('live.blocking_hint') + '</span></div>';", 1),
    ("margin-right:4px;\"></i>Sem consumers activos</div>';", "margin-right:4px;\"></i>' + t('live.no_active_consumers') + '</div>';", 1),
    ("${w.instances.size} instancias\"", "${w.instances.size} ${t('live.instances')}\"", 1),
    ("margin-right:4px;\"></i>Sem waits significativos</div>';", "margin-right:4px;\"></i>' + t('live.no_significant_waits') + '</div>';", 1),
    ("color:var(--color-text-tertiary);\"></i>SESSOES IDLE >1h</div>';", "color:var(--color-text-tertiary);\"></i>' + t('live.idle_sessions_1h') + '</div>';", 1),
    ("margin-right:4px;\"></i>Sem sessoes idle</div>';", "margin-right:4px;\"></i>' + t('live.no_idle_sessions') + '</div>';", 1),
    ("padding:40px;\">Sem dados de I/O</div>';", "padding:40px;\">' + t('live.no_io_data') + '</div>';", 1),
    ("display:block;\"></i>Nenhum job em execucao</div>';", "display:block;\"></i>' + t('live.no_running_jobs') + '</div>';", 1),
    ("padding:40px;\">Sem dados de memoria</div>';", "padding:40px;\">' + t('live.no_memory_data') + '</div>';", 1),
    ("padding:40px;\">Sem conexoes activas</div>';", "padding:40px;\">' + t('live.no_active_connections') + '</div>';", 1),
    ("display:block;\"></i>Sem AGs configurados</div>';", "display:block;\"></i>' + t('live.no_ags') + '</div>';", 1),
    ("padding:40px;\">Sem dados de transaction log</div>';", "padding:40px;\">' + t('live.no_tlog_data') + '</div>';", 1),
    ("padding:40px;\">Sem dados de schedulers</div>';", "padding:40px;\">' + t('live.no_scheduler_data') + '</div>';", 1),
]
CHANGELOG_ENTRY = """- **Lote F8 (BUG-003): o painel LIVE segue o idioma** (owner 09/09: "achei mais 1 caso: o LIVE" — "A carregar
  Fleet Dashboard…", "Filtrar instância…", "Canal…" em inglês). Placeholders, tooltips, mensagens "Sem dados
  de…" / "Nenhum … ativo" e cabeçalhos de secção do painel LIVE e do drill de disco ganham chaves `live.*`
  em pt-PT, en-US e es (pt-BR herda), com placeholders para contagens. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def upsert_namespace(raw, name, obj):
    """Insere as chaves no bloco `  "name": {` se existir; senao acrescenta o namespace no fim. Preserva CRLF/LF."""
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = [l.rstrip("\r") for l in raw.split("\n")]
    hit = [i for i, l in enumerate(lines) if l.strip() == f'"{name}": {{' and l.startswith("  ")]
    if hit:
        s = hit[0]; e = next(i for i in range(s + 1, len(lines)) if lines[i].startswith("  }"))
        existing = {m.group(1) for i in range(s + 1, e) for m in [re.match(r'\s*"([^"]+)":', lines[i])] if m}
        dup = sorted(set(obj) & existing)
        if dup: return None, f"chaves ja existem em {name}: {dup[:6]}"
        lines[s + 1:s + 1] = [f'    "{k}": {json.dumps(v, ensure_ascii=False)},' for k, v in obj.items()]
        out = nl.join(lines)
    else:
        body = raw.rstrip()
        block = json.dumps({name: obj}, ensure_ascii=False, indent=2)[1:-1].rstrip()
        out = (body[:-1].rstrip() + ",\n" + block + "\n}\n").replace("\n", nl)
    try: json.loads(out)
    except Exception as ex: return None, f"json invalido: {ex}"
    return out, None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems, outs = [], {}
    keys = json.loads(KEYS.read_bytes().decode("utf-8"))
    used = set(re.findall(r"live\.([a-z0-9_]+)", " ".join(n for _, n, _ in PATCHES)))
    for k in used - set(keys): problems.append(f"chave usada no patch sem traducao no sidecar: live.{k}")
    for k in set(keys) - used: problems.append(f"chave no sidecar sem uso: live.{k}")
    html, hnl = read(root / HTML)
    if "t('live.loading_fleet')" in html: problems.append("ja aplicado")
    for old, new, exp in PATCHES:
        c = html.count(old)
        if c != exp: problems.append(f"patch esperado {exp}x, encontrado {c}x: {old[:70]!r}")
    for loc in ("pt", "en", "es"):
        raw, nl = read(root / f"static/i18n/{loc}.json")
        new, err = upsert_namespace(raw, "live", {k: v[loc] for k, v in keys.items()})
        if err: problems.append(f"{loc}.json: {err}")
        else: outs[f"static/i18n/{loc}.json"] = new
    # pt-BR: overrides so' para as chaves com marcador pt-PT (a carregar / ficheiro) -- overlay esparso
    PTBR = {"loading_files": "Carregando arquivos...", "no_db_files_drive": "Nenhum arquivo de banco de dados encontrado neste drive",
            "loading": "Carregando...", "loading_fleet": "Carregando Fleet Dashboard...", "loading_program": "Carregando {program}..."}
    raw, nl = read(root / "static/i18n/pt-BR.json")
    new, err = upsert_namespace(raw, "live", PTBR)
    if err: problems.append(f"pt-BR.json: {err}")
    else: outs["static/i18n/pt-BR.json"] = new
    craw, cnl = read(root / CHG); anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada")
    if "Lote F8 (BUG-003)" in craw: problems.append("CHANGELOG: ja aplicado")
    if problems:
        print(f"[ABORT] nada foi escrito ({len(problems)} problemas):"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] {len(PATCHES)} patches no portal, {len(keys)} chaves live.* em pt/en/es, CHANGELOG OK"); return
    for old, new, exp in PATCHES: html = html.replace(old, new)
    (root / HTML).write_bytes(html.encode("utf-8")); print(f"[OK] {HTML}")
    for rel, txt in outs.items(): (root / rel).write_bytes(txt.encode("utf-8")); print(f"[OK] {rel}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser Ctrl+F5 -> LIVE em EN: 'Loading Fleet Dashboard...', 'Filter instance...'")


if __name__ == "__main__":
    main()
