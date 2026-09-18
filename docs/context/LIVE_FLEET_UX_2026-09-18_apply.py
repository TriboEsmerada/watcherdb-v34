# -*- coding: utf-8 -*-
"""LIVE Fleet, lote de UX (owner, 18/09, cinco pedidos numa sessão de LIVE):

 1. Os cards do topo (Online, Parcial, Offline, No data, CPU >50%, MEM >85%, Low PLE, Blocking, Drilled) FILTRAM o ecrã ao
    clique: as listas do Fleet (queries pesadas, blocking, tempdb, waits, AG, idle, transacções longas) passam a mostrar só
    as instâncias do card e a secção final lista essas instâncias (em vez dos 8 piores canais). Segundo clique, ou o ×
    na faixa de filtro, limpa. Re-render a partir do cache do LIVE (sem novo pedido).
 2. ErrLog e o botão de ajuda na mesma linha dos outros programas: o cabeçalho passa a duas linhas deliberadas —
    linha 1: pulso LIVE, filtro de instância, canal; linha 2: todos os programas + taxa + pausa.
 3. Caixa do canal mais pequena: 320px -> 240px (e o filtro de instância 130px -> 110px).
 4. QUERIES PESADAS AGORA: coluna CPU mais larga (55px -> 80px, elapsed 58px -> 70px), comando mais curto (80 -> 60
    caracteres e no máximo metade da linha) com botão de copiar o comando completo; o clique na linha continua a abrir Queries.
 5. TEMPDB CONSUMERS AGORA: mostra consumo / total do tempdb da instância, e a cor passa a ser pela fracção do total
    (>25% crítico, >10% aviso) em vez de MB absolutos. O backend passa a devolver tempdb_total_mb e tempdb_free_mb por
    instância drillada (uma consulta SELECT a tempdb.sys.database_files e dm_db_file_space_usage, pela mesma ligação do
    pool que o drill já usa: identidade sql_monitoring, só leitura).

 6. Estados vazios do Fleet ("No heavy queries"...) em verde fixo #10b981 (2,54 em Light, so' visiveis com o filtro) -> --sev-ok-text.

Ficheiros: templates/watcherdb_portal.html (cabeçalho do LIVE e _liveRenderFleet/_fleetCard) e api/routers/live_monitoring.py
(_drill_instance e merge do fleet). Texto novo passa por _kpiT(chave, fallback): live.copy_sql, live.copied, live.fleet_filter,
live.fleet_filter_clear, live.tempdb_of_total (as chaves entram no lote de i18n; até lá vale o fallback).

RAMO: o mesmo do D1-D6 (toca na mesma região). Requer D1 aplicado.

Uso (raiz do repo):
  py docs/context/LIVE_FLEET_UX_2026-09-18_apply.py --check
  py docs/context/LIVE_FLEET_UX_2026-09-18_apply.py
  py -m pytest tests/unit/test_live_ajuda_sched_20260915.py tests/unit/test_live_legivel_20260915.py tests/unit/test_live_f9b_20260911.py tests/unit/test_live_channels_20260911.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
BACKEND = Path("api/routers/live_monitoring.py")
MARK = "_fleetToggleFilter"

EDITS_PORTAL = [
    # ---- 2 e 3: cabecalho em duas linhas, canal mais pequeno ----
    ("""                           style="width:130px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:5px;color:var(--color-text-bright);font-size:12px;">
                    <select id="live-channel-${tabId}" onchange="liveChangeChannel('${tabId}', this.value)"
                            style="max-width:320px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:5px;color:var(--color-text-bright);font-size:12px;font-weight:500;">""",
     """                           style="width:110px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:5px;color:var(--color-text-bright);font-size:12px;">
                    <select id="live-channel-${tabId}" onchange="liveChangeChannel('${tabId}', this.value)"
                            style="max-width:240px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:5px;color:var(--color-text-bright);font-size:12px;font-weight:500;">""", 1),
    ("""                    </select>
                    <span style="width:1px;height:14px;background:var(--color-border);"></span>
                    <button onclick="liveSetProgram('${tabId}','fleet')" class="live-prog-btn" data-prog="fleet" style="${_pb}" title="Fleet Dashboard">📡 Fleet</button>""",
     """                    </select>
                    <div style="flex-basis:100%;height:0;"></div><!-- 2026-09-18 (owner): programas todos na 2.a linha, ErrLog e ? incluidos -->
                    <button onclick="liveSetProgram('${tabId}','fleet')" class="live-prog-btn" data-prog="fleet" style="${_pb}" title="Fleet Dashboard">📡 Fleet</button>""", 1),
    # ---- 1: grupos, filtro e listas filtradas ----
    ("""            const lowPle = online.filter(i => (i.ple||9999) < 300);
            const liveQueries = data.live_queries || [];
            const liveBlocking = data.live_blocking || [];
            const problemCount = data.problem_count || 0;
            let h = '';
            h += '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">';
            h += _fleetCard('Online', online.length, 'var(--sev-ok-text)', 'fa-check-circle');
            h += _fleetCard('Parcial', partial.length, partial.length>0?'var(--sev-warning-text)':'var(--color-text-tertiary)', 'fa-exclamation');
            h += _fleetCard('Offline', offline.length, offline.length>0?'var(--sev-critical-text)':'var(--color-text-tertiary)', 'fa-times-circle');
            h += _fleetCard(t('live.no_data_short'), noData.length, 'var(--color-text-tertiary)', 'fa-question-circle');
            h += _fleetCard('CPU >50%', cpuHigh.length, cpuHigh.length>0?'var(--sev-warning-text)':'var(--sev-ok-text)', 'fa-microchip');
            h += _fleetCard('MEM >85%', memHigh.length, memHigh.length>0?'var(--sev-warning-text)':'var(--sev-ok-text)', 'fa-memory');
            h += _fleetCard('Low PLE', lowPle.length, lowPle.length>0?'var(--sev-critical-text)':'var(--sev-ok-text)', 'fa-clock');
            h += _fleetCard('Blocking', blocked.length, blocked.length>0?'var(--sev-critical-text)':'var(--sev-ok-text)', 'fa-lock');
            h += _fleetCard('Drilled', problemCount, 'var(--color-text-link)', 'fa-satellite-dish');
            h += '</div>';
""",
     """            const lowPle = online.filter(i => (i.ple||9999) < 300);
            const problemCount = data.problem_count || 0;
            // 2026-09-18 (owner): os cards filtram o ecra. "Drilled" = instancias com dados live neste ciclo.
            const _drilledSet = new Set([].concat(data.live_queries||[], data.live_blocking||[], data.live_tempdb||[], data.live_waits||[], data.live_ag_queues||[], data.live_idle||[], data.live_long_tran||[]).map(x => x.instance).filter(Boolean));
            const drilled = instances.filter(i => _drilledSet.has(i.instance));
            const groups = { online: online, partial: partial, offline: offline, no_data: noData, cpu: cpuHigh, mem: memHigh, ple: lowPle, blocking: blocked, drilled: drilled };
            const labels = { online: 'Online', partial: 'Parcial', offline: 'Offline', no_data: t('live.no_data_short'), cpu: 'CPU >50%', mem: 'MEM >85%', ple: 'Low PLE', blocking: 'Blocking', drilled: 'Drilled' };
            const fKey = window._fleetFilter && groups[window._fleetFilter] ? window._fleetFilter : null;
            const fSet = fKey ? new Set(groups[fKey].map(i => i.instance)) : null;
            const soFiltro = arr => fSet ? (arr || []).filter(x => fSet.has(x.instance)) : (arr || []);
            const liveQueries = soFiltro(data.live_queries);
            const liveBlocking = soFiltro(data.live_blocking);
            let h = '';
            h += '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">';
            h += _fleetCard(labels.online, online.length, 'var(--sev-ok-text)', 'fa-check-circle', 'online', tabId, fKey);
            h += _fleetCard(labels.partial, partial.length, partial.length>0?'var(--sev-warning-text)':'var(--color-text-tertiary)', 'fa-exclamation', 'partial', tabId, fKey);
            h += _fleetCard(labels.offline, offline.length, offline.length>0?'var(--sev-critical-text)':'var(--color-text-tertiary)', 'fa-times-circle', 'offline', tabId, fKey);
            h += _fleetCard(labels.no_data, noData.length, 'var(--color-text-tertiary)', 'fa-question-circle', 'no_data', tabId, fKey);
            h += _fleetCard(labels.cpu, cpuHigh.length, cpuHigh.length>0?'var(--sev-warning-text)':'var(--sev-ok-text)', 'fa-microchip', 'cpu', tabId, fKey);
            h += _fleetCard(labels.mem, memHigh.length, memHigh.length>0?'var(--sev-warning-text)':'var(--sev-ok-text)', 'fa-memory', 'mem', tabId, fKey);
            h += _fleetCard(labels.ple, lowPle.length, lowPle.length>0?'var(--sev-critical-text)':'var(--sev-ok-text)', 'fa-clock', 'ple', tabId, fKey);
            h += _fleetCard(labels.blocking, blocked.length, blocked.length>0?'var(--sev-critical-text)':'var(--sev-ok-text)', 'fa-lock', 'blocking', tabId, fKey);
            h += _fleetCard(labels.drilled, problemCount, 'var(--color-text-link)', 'fa-satellite-dish', 'drilled', tabId, fKey);
            h += '</div>';
            if (fKey) {
                h += `<div style="display:flex;align-items:center;gap:8px;margin:-4px 0 12px;padding:6px 10px;background:var(--sev-info-tint);border:1px solid var(--sev-info-text);border-radius:6px;font-size:12px;color:var(--sev-info-text);">`
                   + `<i class="fas fa-filter"></i> ${_kpiT('live.fleet_filter', 'Filtro')}: <b>${labels[fKey]}</b> (${groups[fKey].length})`
                   + `<button onclick="_fleetToggleFilter('${tabId}', null)" title="${_kpiT('live.fleet_filter_clear', 'Limpar filtro')}" style="margin-left:auto;background:none;border:1px solid var(--sev-info-text);color:var(--sev-info-text);border-radius:4px;padding:1px 8px;cursor:pointer;font-size:12px;">×</button></div>`;
            }
""", 1),
    ("""            const liveTempdb = data.live_tempdb || [];
            const liveWaits = data.live_waits || [];
""", """            const liveTempdb = soFiltro(data.live_tempdb);
            const liveWaits = soFiltro(data.live_waits);
""", 1),
    ("""            const liveAgQueues = data.live_ag_queues || [];
            const liveIdle = data.live_idle || [];
""", """            const liveAgQueues = soFiltro(data.live_ag_queues);
            const liveIdle = soFiltro(data.live_idle);
""", 1),
    ("""            const liveLongTran = data.live_long_tran || [];
""", """            const liveLongTran = soFiltro(data.live_long_tran);
""", 1),
    ("""            const worst = [...online].sort((a,b) => {
                const scoreA = (a.blocked||0)*1000 + (a.cpu_pct||0)*10 + (10000/(a.ple||9999)) + (a.mem_pct||0);
                const scoreB = (b.blocked||0)*1000 + (b.cpu_pct||0)*10 + (10000/(b.ple||9999)) + (b.mem_pct||0);
                return scoreB - scoreA;
            }).slice(0, 8);""",
     """            const worst = [...(fSet ? groups[fKey] : online)].sort((a,b) => {
                const scoreA = (a.blocked||0)*1000 + (a.cpu_pct||0)*10 + (10000/(a.ple||9999)) + (a.mem_pct||0);
                const scoreB = (b.blocked||0)*1000 + (b.cpu_pct||0)*10 + (10000/(b.ple||9999)) + (b.mem_pct||0);
                return scoreB - scoreA;
            }).slice(0, fSet ? 40 : 8);   // com filtro: as instancias do card (ate 40), nao so' as 8 piores""", 1),
    ("""        function _fleetCard(label, value, color, icon) {
            return `<div style="background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;padding:10px 14px;min-width:100px;text-align:center;"><div style="font-size:22px;font-weight:700;color:${color};">${value}</div><div style="color:var(--color-text-tertiary);font-size:12px;margin-top:2px;"><i class="fas ${icon}" style="margin-right:4px;color:${color};"></i>${label}</div></div>`;
        }""",
     """        function _fleetCard(label, value, color, icon, key, tabId, activeKey) {
            const on = key && key === activeKey;
            const click = key ? ` onclick="_fleetToggleFilter('${tabId}','${key}')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}" aria-pressed="${on ? 'true' : 'false'}"` : '';
            const frame = on ? 'border:2px solid var(--sev-info-text);background:var(--sev-info-tint);' : 'border:1px solid var(--color-border);background:var(--color-bg-panel);';
            return `<div${click} style="${frame}border-radius:8px;padding:10px 14px;min-width:100px;text-align:center;${key ? 'cursor:pointer;' : ''}"><div style="font-size:22px;font-weight:700;color:${color};">${value}</div><div style="color:var(--color-text-tertiary);font-size:12px;margin-top:2px;"><i class="fas ${icon}" style="margin-right:4px;color:${color};"></i>${label}</div></div>`;
        }
        // 2026-09-18 (owner): cards do Fleet filtram o ecra; re-render a partir do cache, sem novo pedido
        function _fleetToggleFilter(tabId, key) {
            window._fleetFilter = (key && window._fleetFilter !== key) ? key : null;
            const cached = _liveLastData['fleet'];
            const screen = document.getElementById('live-screen-' + tabId);
            if (cached && screen) _liveRenderAndSet(screen, 'fleet', cached, tabId);
        }
        window._fleetToggleFilter = _fleetToggleFilter;
        function _fleetCopySql(btn) {
            const sql = btn.getAttribute('data-sql') || '';
            const ok = () => { const old = btn.textContent; btn.textContent = '✓'; btn.title = _kpiT('live.copied', 'Copiado'); setTimeout(() => { btn.textContent = old; }, 1200); };
            if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(sql).then(ok).catch(() => {}); return; }
            const ta = document.createElement('textarea'); ta.value = sql; document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); ok(); } catch (e) {} document.body.removeChild(ta);
        }
        window._fleetCopySql = _fleetCopySql;""", 1),
    # ---- 4: queries pesadas: CPU mais largo, comando mais curto + copiar ----
    ("""                    const sql = (q.sql_text||'').replace(/</g,'&lt;').substring(0,80);""",
     """                    const sql = (q.sql_text||'').replace(/</g,'&lt;').substring(0,60);
                    const sqlAttr = String(q.sql_text||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');""", 1),
    ("""<div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div><div style="width:30px;color:var(--color-text-tertiary);font-size:12px;">${q.spid}</div><div style="flex:1;color:var(--color-text-secondary);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--font-mono);">${sql}</div><div style="width:55px;text-align:right;color:${cc};font-size:12px;font-weight:600;" title="${t('live.cpu_title')}">CPU ${fCpuH}</div><div style="width:58px;text-align:right;color:${fElC};font-size:12px;font-weight:600;" title="${t('live.elapsed_title')}${fIdle ? ' — ' + t('live.idle_not_exec') : ''}">${fElH}${fIdle ? ' idle' : ''}</div></div>`;""",
     """<div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div><div style="width:30px;color:var(--color-text-tertiary);font-size:12px;">${q.spid}</div><div style="flex:1;min-width:0;max-width:50%;color:var(--color-text-secondary);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--font-mono);">${sql}</div><button type="button" onclick="event.stopPropagation();_fleetCopySql(this)" data-sql="${sqlAttr}" title="${_kpiT('live.copy_sql', 'Copiar comando')}" aria-label="${_kpiT('live.copy_sql', 'Copiar comando')}" style="flex-shrink:0;background:none;border:1px solid var(--color-border);color:var(--color-text-tertiary);border-radius:4px;padding:0 5px;font-size:12px;line-height:18px;cursor:pointer;">⧉</button><div style="width:80px;flex-shrink:0;text-align:right;color:${cc};font-size:12px;font-weight:600;" title="${t('live.cpu_title')}">CPU ${fCpuH}</div><div style="width:70px;flex-shrink:0;text-align:right;color:${fElC};font-size:12px;font-weight:600;" title="${t('live.elapsed_title')}${fIdle ? ' — ' + t('live.idle_not_exec') : ''}">${fElH}${fIdle ? ' idle' : ''}</div></div>`;""", 1),
    # ---- 5: tempdb consumo / total ----
    ("""                    const mb = parseInt(t.tempdb_mb || 0);
                    const c = mb > 1024 ? 'var(--sev-critical-text)' : mb > 100 ? 'var(--sev-warning-text)' : 'var(--sev-ok-text)';
                    h += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;cursor:pointer;" onclick="_fleetSwitchTo('${t.instance}','tempdb')" title="${t.instance} SPID ${t.spid}: ${mb} MB"><div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div><div style="width:30px;color:var(--color-text-tertiary);font-size:12px;">${t.spid}</div><div style="width:50px;color:${c};font-size:12px;font-weight:600;">${formatSizeMB(mb)}</div><div style="flex:1;color:var(--color-text-tertiary);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${t.login_name||''}</div></div>`;""",
     """                    const mb = parseInt(t.tempdb_mb || 0);
                    // 2026-09-18 (owner): consumo / total do tempdb da instancia; cor pela fraccao do total quando o total existe
                    const totalMb = parseInt(t.tempdb_total_mb || 0);
                    const pct = totalMb > 0 ? (mb / totalMb) * 100 : null;
                    const c = pct != null ? (pct > 25 ? 'var(--sev-critical-text)' : pct > 10 ? 'var(--sev-warning-text)' : 'var(--sev-ok-text)')
                                          : (mb > 1024 ? 'var(--sev-critical-text)' : mb > 100 ? 'var(--sev-warning-text)' : 'var(--sev-ok-text)');
                    const doTotal = totalMb > 0 ? ` <span style="color:var(--color-text-tertiary);font-weight:400;">/ ${formatSizeMB(totalMb)}</span>` : '';
                    const tip = `${t.instance} SPID ${t.spid}: ${mb} MB` + (totalMb > 0 ? ` ${_kpiT('live.tempdb_of_total', 'de')} ${totalMb} MB (${pct.toFixed(1)}%)` + (t.tempdb_free_mb != null ? `, ${_kpiT('live.free_short', 'livre')} ${t.tempdb_free_mb} MB` : '') : '');
                    h += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;cursor:pointer;" onclick="_fleetSwitchTo('${t.instance}','tempdb')" title="${tip}"><div style="width:130px;flex-shrink:0;color:var(--color-text-link);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div><div style="width:30px;color:var(--color-text-tertiary);font-size:12px;">${t.spid}</div><div style="min-width:50px;color:${c};font-size:12px;font-weight:600;white-space:nowrap;">${formatSizeMB(mb)}${doTotal}</div><div style="flex:1;color:var(--color-text-tertiary);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${t.login_name||''}</div></div>`;""", 1),
    # ---- estados vazios do Fleet ("No heavy queries", etc.): verde fixo #10b981 (2,54 em Light) -> --sev-ok-text ----
    ("""'<div style="color:#10b981;font-size:12px;text-align:center;padding:10px;"><i class="fas fa-check-circle" style="margin-right:4px;"></i>' + t('live.""",
     """'<div style="color:var(--sev-ok-text);font-size:12px;text-align:center;padding:10px;"><i class="fas fa-check-circle" style="margin-right:4px;"></i>' + t('live.""", 4),
]

EDITS_BACKEND = [
    ("""            # Top waits (snapshot para delta)
""", """            # TempDB: total e livre da instancia (2026-09-18, owner: o Fleet mostra consumo / total). SELECT, mesma ligacao.
            try:
                cur.execute(\"\"\"SET NOCOUNT ON;
                    SELECT (SELECT SUM(CAST(size AS bigint)) * 8 / 1024 FROM tempdb.sys.database_files WITH (NOLOCK) WHERE type = 0) AS tempdb_total_mb,
                           (SELECT SUM(CAST(unallocated_extent_page_count AS bigint)) * 8 / 1024 FROM tempdb.sys.dm_db_file_space_usage WITH (NOLOCK)) AS tempdb_free_mb\"\"\")
                row = cur.fetchone()
                if row:
                    result["tempdb_total_mb"] = int(row[0] or 0)
                    result["tempdb_free_mb"] = int(row[1] or 0)
            except Exception:
                pass

            # Top waits (snapshot para delta)
""", 1),
    ("""                        for t in drill.get("tempdb_consumers", []):
                            t["instance"] = inst
                            live_tempdb.append(t)
""", """                        for t in drill.get("tempdb_consumers", []):
                            t["instance"] = inst
                            t["tempdb_total_mb"] = drill.get("tempdb_total_mb")
                            t["tempdb_free_mb"] = drill.get("tempdb_free_mb")
                            live_tempdb.append(t)
""", 1),
]


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    portal_p, back_p = base / PORTAL, base / BACKEND
    portal = portal_p.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "D1 piloto LIVE" not in portal:
        print("[ABORT] o D1 nao esta aplicado neste template (ramo errado?)"); return 1
    novo_portal = _apply(portal, EDITS_PORTAL, "portal")
    novo_back = None
    if back_p.exists():
        back = back_p.read_bytes().decode("utf-8")
        if "tempdb_total_mb" in back:
            print("[ABORT] backend ja aplicado"); return 1
        novo_back = _apply(back, EDITS_BACKEND, "backend")
    print(f"[ok] portal: {len(EDITS_PORTAL)} blocos (cabecalho 2, filtro por card 7, queries 2, tempdb 1, estados vazios 1); backend: {len(EDITS_BACKEND)} blocos" + ("" if novo_back else " (ficheiro ausente na copia: saltado)"))
    if check:
        print("--check OK. Nada escrito."); return 0
    portal_p.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    if novo_back is not None:
        back_p.write_bytes(novo_back.encode("utf-8")); print(f"[write] {BACKEND}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
