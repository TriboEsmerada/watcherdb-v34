# -*- coding: utf-8 -*-
"""
LIVE: sem canal, cada programa mostra a FROTA so' do seu tema (2026-09-21, owner GO)

Pedido do owner (21/09): "o live, quando nenhum canal esta selecionado, poderia tratar do assunto como o fleet trata
(geral), mas somente voltado para o tema selecionado". Lote 1 = sem endpoint novo: le o mesmo payload do Fleet
(/api/v1/live/fleet/dashboard) e filtra pelo tema:
  queries -> live_queries | blocking -> live_blocking | tempdb -> live_tempdb | waits -> live_waits (agregado por wait_type)
  alwayson -> live_ag_queues | connections -> live_idle + live_long_tran | errorlog -> live_errors | space -> space_risk
Memory, Plan Cache, I/O, Sched, Jobs e TLog continuam com o estado neutro (o Fleet nao os drilla) -- lote 2 com endpoint.
Aviso na propria vista: o payload do Fleet so' traz as instancias com problema neste ciclo ("onde ha' problema agora").

Portal (templates/watcherdb_portal.html):
  P1  _LIVE_FLEET_THEME + _liveFleetMode()   (junto de _LIVE_HELP_PROGS)
  P2  liveSetProgram: sem instancia + tema com frota -> carrega a frota (nao o estado neutro); medidores escondidos em modo frota
  P3  liveChangeChannel: ao limpar o canal, o programa activo decide (frota por tema ou neutro); ao escolher canal, medidores voltam
  P4  _liveRefresh: modo frota usa o endpoint do Fleet; liveChangeRate mantem o intervalo em modo frota
  P5  _liveRenderProgram: em modo frota despacha para _liveRenderFleetTheme(program, data, tabId)
  P6  _liveRenderFleetTheme: cabecalho "Frota - <tema>", nota, tabelas por tema com clique -> _fleetSwitchTo(inst, programa)
Locales pt/en/es: live.fleet_theme_title/_sub/_note/_empty/_neutral (a seguir a "help_io_next").
Testes: tests/unit/test_live_channels_20260911.py (pin do liveChangeChannel actualizado) + tests/unit/test_live_frota_por_tema_20260921.py (novo).

Uso: --check | --preview <dir> | (sem args) aplica no repo. Idempotente (MARK = _liveRenderFleetTheme).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
T_CANAIS = Path("tests/unit/test_live_channels_20260911.py")
T_NOVO = Path("tests/unit/test_live_frota_por_tema_20260921.py")
MARK = "_liveRenderFleetTheme"

RENDERER = r"""
        // 2026-09-21 (owner): sem canal, cada programa mostra a FROTA so' do seu tema, lida do payload do Fleet.
        // So' as instancias com problema neste ciclo (o Fleet drilla as problematicas): a nota na vista diz isso.
        const _LIVE_FLEET_THEME = { queries: 1, blocking: 1, tempdb: 1, waits: 1, alwayson: 1, connections: 1, errorlog: 1, space: 1 };
        function _liveFleetMode(program) { const p = program || _liveProgram; return p === 'fleet' || (!_liveInstance && !!_LIVE_FLEET_THEME[p]); }
        function _liveGaugesVisible(tabId, show) {
            const g = document.getElementById('live-gauges-' + tabId);
            if (g) g.querySelectorAll(':scope > span:not([id^="live-status-"])').forEach(s => { s.style.display = show ? '' : 'none'; });
        }
        function _liveRenderFleetTheme(program, data, tabId) {
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
            const btn = document.querySelector('.live-prog-btn[data-prog="' + program + '"]');
            const label = btn ? btn.textContent.trim() : program;
            const instances = data.instances || [];
            const drilled = new Set([].concat(data.live_queries||[], data.live_blocking||[], data.live_tempdb||[], data.live_waits||[], data.live_ag_queues||[], data.live_idle||[], data.live_long_tran||[], data.live_errors||[]).map(x => x.instance));
            const cell = 'padding:4px 6px;font-size:12px;border-bottom:1px solid var(--color-bg-sunken);white-space:nowrap;';
            const th = 'padding:4px 6px;font-size:12px;text-align:left;color:var(--color-text-tertiary);font-weight:600;';
            const instCell = i => `<td style="${cell}color:var(--color-text-link);font-weight:600;">${esc(i)}</td>`;
            const fmtDur = sec => { sec = Math.max(0, Math.floor(+sec || 0)); const d = Math.floor(sec/86400), hh = Math.floor((sec%86400)/3600), mm = Math.floor((sec%3600)/60);
                if (d > 0) return d + 'd ' + hh + 'h'; if (hh > 0) return hh + 'h ' + mm + 'm'; if (mm > 0) return mm + 'm'; return sec + 's'; };
            const sevC = s => `color:var(--sev-${s}-text);font-weight:600;`;
            const row = (inst, prog, tds, title) => `<tr onclick="_fleetSwitchTo('${esc(inst)}','${prog}')" title="${esc(title || inst)}" style="cursor:pointer;">${instCell(inst)}${tds}</tr>`;
            const table = (cols, rows) => `<table style="width:100%;border-collapse:collapse;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;overflow:hidden;"><thead><tr>${cols.map(c => `<th style="${th}">${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
            const vazio = () => `<div style="color:var(--sev-ok-text);font-size:13px;text-align:center;padding:24px;"><i class="fas fa-check-circle" style="margin-right:6px;"></i>${_kpiTp('live.fleet_theme_empty', 'Nenhuma instância com problema de {theme} neste ciclo', { theme: label })}</div>`;
            let body = '', n = 0;
            if (program === 'queries') {
                const rows = (data.live_queries || []).slice(0, 20); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), 'SPID', 'DB', 'CPU', _kpiT('live.col_elapsed', 'Decorrido'), _kpiT('live.col_status', 'Estado'), 'SQL'], rows.map(q => {
                    const idle = /^sleeping/i.test(q.status || '') || /BROKER_RECEIVE_WAITFOR|WAITFOR/i.test(q.wait_type || '');
                    const cpu = +q.cpu_ms || 0, el = +q.elapsed_sec || 0;
                    const sqlAttr = String(q.sql_text || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
                    return row(q.instance, 'queries',
                        `<td style="${cell}">${esc(q.spid)}</td><td style="${cell}">${esc(q.db)}</td>`
                        + `<td style="${cell}${sevC(cpu > 100000 ? 'critical' : cpu > 10000 ? 'warning' : 'ok')}" data-sort-value="${cpu}">${fmtDur(cpu / 1000)}</td>`
                        + `<td style="${cell}${idle ? 'color:var(--color-text-tertiary);' : sevC(el > 300 ? 'critical' : el > 60 ? 'warning' : 'ok')}" data-sort-value="${el}">${fmtDur(el)}</td>`
                        + `<td style="${cell}color:var(--color-text-tertiary);">${esc(q.status || '')}</td>`
                        + `<td style="${cell}max-width:360px;overflow:hidden;text-overflow:ellipsis;font-family:var(--font-mono);color:var(--color-text-secondary);" title="${sqlAttr}">${esc(String(q.sql_text || '').substring(0, 80))} <button onclick="event.stopPropagation();_fleetCopySql(this)" data-sql="${sqlAttr}" title="${_kpiT('live.copy_sql', 'Copiar SQL')}" style="border:1px solid var(--color-border);background:var(--color-bg-panel);color:var(--color-text-tertiary);border-radius:4px;font-size:12px;padding:0 5px;cursor:pointer;">&#10697;</button></td>`, q.instance + ' SPID ' + q.spid);
                })) : vazio();
            } else if (program === 'blocking') {
                const rows = (data.live_blocking || []).slice(0, 30); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), _kpiT('live.col_blocked', 'Bloqueado'), _kpiT('live.col_blocker', 'Bloqueador'), 'DB', 'Wait', _kpiT('live.col_wait_time', 'Espera')], rows.map(b => row(b.instance, 'blocking',
                    `<td style="${cell}">${esc(b.blocked_spid)}</td><td style="${cell}${sevC('critical')}">${esc(b.blocker_spid)}</td><td style="${cell}">${esc(b.db)}</td>`
                    + `<td style="${cell}color:var(--color-text-tertiary);">${esc(b.wait_type || '')}</td><td style="${cell}${sevC((+b.wait_sec || 0) > 60 ? 'critical' : 'warning')}" data-sort-value="${+b.wait_sec || 0}">${fmtDur(b.wait_sec)}</td>`))) : vazio();
            } else if (program === 'tempdb') {
                const rows = (data.live_tempdb || []).slice(0, 30); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), 'SPID', 'Login', 'DB', 'TempDB', _kpiT('live.col_total', 'Total'), '%'], rows.map(x => {
                    const mb = +x.tempdb_mb || 0, tot = +x.tempdb_total_mb || 0, pct = tot > 0 ? mb / tot * 100 : null;
                    const s = pct != null ? (pct > 25 ? 'critical' : pct > 10 ? 'warning' : 'ok') : (mb > 1024 ? 'critical' : mb > 100 ? 'warning' : 'ok');
                    return row(x.instance, 'tempdb', `<td style="${cell}">${esc(x.spid)}</td><td style="${cell}">${esc(x.login_name || '')}</td><td style="${cell}">${esc(x.db)}</td>`
                        + `<td style="${cell}${sevC(s)}" data-sort-value="${mb}">${formatSizeMB(mb)}</td><td style="${cell}color:var(--color-text-tertiary);" data-sort-value="${tot}">${tot > 0 ? formatSizeMB(tot) : '-'}</td>`
                        + `<td style="${cell}${sevC(s)}" data-sort-value="${pct == null ? 0 : pct}">${pct == null ? '-' : pct.toFixed(1) + '%'}</td>`);
                })) : vazio();
            } else if (program === 'waits') {
                const map = {};
                (data.live_waits || []).forEach(w => { const k = w.wait_type || '?'; if (!map[k]) map[k] = { wait_type: k, ms: 0, tasks: 0, inst: new Set() }; map[k].ms += (+w.wait_time_ms || 0); map[k].tasks += (+w.waiting_tasks_count || 0); map[k].inst.add(w.instance || '?'); });
                const rows = Object.values(map).sort((a, b) => b.ms - a.ms).slice(0, 20); n = rows.length;
                const maxMs = Math.max(...rows.map(w => w.ms), 1);
                body = rows.length ? table(['Wait', _kpiT('live.col_wait_time', 'Espera'), 'Tasks', t('live.instances'), ''], rows.map(w => {
                    const first = Array.from(w.inst)[0];
                    return `<tr onclick="_fleetSwitchTo('${esc(first)}','waits')" title="${esc(Array.from(w.inst).join(', '))}" style="cursor:pointer;"><td style="${cell}color:var(--color-text-link);font-weight:600;">${esc(w.wait_type)}</td>`
                        + `<td style="${cell}" data-sort-value="${w.ms}">${fmtDur(w.ms / 1000)}</td><td style="${cell}" data-sort-value="${w.tasks}">${w.tasks.toLocaleString()}</td>`
                        + `<td style="${cell}" data-sort-value="${w.inst.size}">${w.inst.size} <span style="color:var(--color-text-tertiary);">${esc(Array.from(w.inst).slice(0, 3).join(', '))}${w.inst.size > 3 ? '…' : ''}</span></td>`
                        + `<td style="${cell}width:120px;"><div style="height:6px;background:var(--color-bg-sunken);border-radius:3px;"><div style="height:6px;width:${(w.ms / maxMs * 100).toFixed(0)}%;background:var(--sev-warning-text);border-radius:3px;"></div></div></td></tr>`;
                })) : vazio();
            } else if (program === 'alwayson') {
                const rows = (data.live_ag_queues || []).slice(0, 30); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), 'AG', _kpiT('live.col_replica', 'Réplica'), 'Send', 'Redo', 'Send/s', 'Redo/s'], rows.map(a => {
                    const s = ((+a.send_queue_kb || 0) / 1024 > 50 || (+a.redo_queue_kb || 0) / 1024 > 50) ? 'critical' : 'warning';
                    return row(a.instance, 'alwayson', `<td style="${cell}">${esc(a.ag_name)}</td><td style="${cell}color:var(--color-text-tertiary);">${esc(a.replica_server_name || '')}</td>`
                        + `<td style="${cell}${sevC(s)}" data-sort-value="${+a.send_queue_kb || 0}">${formatSizeMB((+a.send_queue_kb || 0) / 1024)}</td><td style="${cell}${sevC(s)}" data-sort-value="${+a.redo_queue_kb || 0}">${formatSizeMB((+a.redo_queue_kb || 0) / 1024)}</td>`
                        + `<td style="${cell}color:var(--color-text-tertiary);">${formatSizeMB((+a.send_rate_kb_sec || 0) / 1024)}</td><td style="${cell}color:var(--color-text-tertiary);">${formatSizeMB((+a.redo_rate_kb_sec || 0) / 1024)}</td>`);
                })) : vazio();
            } else if (program === 'connections') {
                const idle = (data.live_idle || []).slice(0, 20), lt = (data.live_long_tran || []).slice(0, 20); n = idle.length + lt.length;
                const hIdle = `<div style="color:var(--color-text-tertiary);font-size:12px;font-weight:600;margin:0 0 6px;"><i class="fas fa-user-clock" style="margin-right:6px;"></i>${_kpiT('live.idle_sessions', 'Sessões idle com transação aberta')}</div>`;
                const hLt = `<div style="color:var(--color-text-tertiary);font-size:12px;font-weight:600;margin:12px 0 6px;"><i class="fas fa-exchange-alt" style="margin-right:6px;color:#fb7185;"></i>${_kpiT('live.long_transactions', 'Transações longas')}</div>`;
                const tIdle = idle.length ? table([_kpiT('live.col_instance', 'Instância'), 'SPID', 'Login', 'Host', _kpiT('live.col_program', 'Programa'), 'DB', 'Idle'], idle.map(s => row(s.instance, 'connections',
                    `<td style="${cell}">${esc(s.spid)}</td><td style="${cell}">${esc(s.login_name || '')}</td><td style="${cell}color:var(--color-text-tertiary);">${esc(s.host_name || '')}</td><td style="${cell}max-width:180px;overflow:hidden;text-overflow:ellipsis;color:var(--color-text-tertiary);">${esc(s.program_name || '')}</td><td style="${cell}">${esc(s.db || '')}</td>`
                    + `<td style="${cell}${sevC((+s.idle_minutes || 0) > 480 ? 'critical' : (+s.idle_minutes || 0) > 120 ? 'warning' : 'ok')}" data-sort-value="${+s.idle_minutes || 0}">${fmtDur((+s.idle_minutes || 0) * 60)}</td>`))) : vazio();
                const tLt = lt.length ? table([_kpiT('live.col_instance', 'Instância'), 'SPID', 'Login', 'DB', _kpiT('live.col_duration', 'Duração'), 'Log'], lt.map(x => row(x.instance, 'connections',
                    `<td style="${cell}">${esc(x.spid)}</td><td style="${cell}">${esc(x.login_name || '')}</td><td style="${cell}">${esc(x.db || '')}</td>`
                    + `<td style="${cell}${sevC((+x.tran_minutes || 0) > 60 ? 'critical' : (+x.tran_minutes || 0) > 15 ? 'warning' : 'ok')}" data-sort-value="${+x.tran_minutes || 0}">${fmtDur((+x.tran_minutes || 0) * 60)}</td><td style="${cell}" data-sort-value="${+x.log_used_mb || 0}">${formatSizeMB(+x.log_used_mb || 0)}</td>`))) : vazio();
                body = hIdle + tIdle + hLt + tLt;
            } else if (program === 'errorlog') {
                const rows = (data.live_errors || []).slice(0, 40); n = rows.length;
                body = rows.length ? table([_kpiT('live.col_instance', 'Instância'), _kpiT('live.col_date', 'Data'), 'Process', _kpiT('live.col_message', 'Mensagem')], rows.map(e => row(e.instance, 'errorlog',
                    `<td style="${cell}color:var(--color-text-tertiary);">${esc(String(e.LogDate || '').replace('T', ' ').substring(0, 19))}</td><td style="${cell}color:var(--color-text-tertiary);">${esc(e.ProcessInfo || '')}</td>`
                    + `<td style="${cell}white-space:normal;color:var(--sev-critical-text);">${esc(String(e.Text || '').substring(0, 200))}</td>`, e.instance))) : vazio();
            } else if (program === 'space') {
                n = (data.space_risk || []).length;
                body = _fleetSpacePanel(data.space_risk);
            }
            let h = '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px;">';
            h += `<div style="font-size:14px;font-weight:600;color:var(--color-text-bright);"><i class="fas fa-satellite-dish" style="margin-right:6px;color:var(--color-text-link);"></i>${_kpiTp('live.fleet_theme_title', 'Frota · {theme}', { theme: label })}</div>`;
            h += `<div style="font-size:12px;color:var(--color-text-tertiary);">${_kpiTp('live.fleet_theme_sub', '{n} linhas · {d} instâncias com drill neste ciclo · {t} na frota', { n: n, d: drilled.size, t: instances.length })}</div>`;
            h += '</div>';
            h += `<div style="font-size:12px;color:var(--color-text-secondary);background:var(--sev-info-tint);border:1px solid var(--sev-info-text);border-radius:6px;padding:6px 10px;margin-bottom:10px;"><i class="fas fa-info-circle" style="margin-right:6px;color:var(--sev-info-text);"></i>${_kpiT('live.fleet_theme_note', 'Sem canal selecionado: só as instâncias onde há problema agora (o mesmo drill do Fleet). Clique numa linha para abrir a instância neste programa; escolha um canal para ver tudo.')}</div>`;
            return h + body;
        }
        window._liveFleetMode = _liveFleetMode;
"""

EDITS_PORTAL = [
    # P1: constantes + renderer, antes de _LIVE_HELP_PROGS
    ("""        const _LIVE_HELP_PROGS = ['fleet', 'queries', 'waits', 'blocking', 'plancache', 'memory', 'tempdb', 'io', 'tlog', 'connections', 'jobs', 'alwayson', 'schedulers', 'errorlog', 'space'];""",
     RENDERER.strip("\n") + """
        const _LIVE_HELP_PROGS = ['fleet', 'queries', 'waits', 'blocking', 'plancache', 'memory', 'tempdb', 'io', 'tlog', 'connections', 'jobs', 'alwayson', 'schedulers', 'errorlog', 'space'];""", 1),
    # P2: liveSetProgram -- medidores e arranque
    ("""            if (_gauges) _gauges.querySelectorAll(':scope > span:not([id^="live-status-"])').forEach(s => { s.style.display = program === 'fleet' ? 'none' : ''; });""",
     """            if (_gauges) _gauges.querySelectorAll(':scope > span:not([id^="live-status-"])').forEach(s => { s.style.display = _liveFleetMode(program) ? 'none' : ''; });   // 2026-09-21: modo frota por tema tambem""", 1),
    ("""            if (_liveInstance || program === 'fleet') {
                const label = program === 'fleet' ? t('live.loading_fleet') : _kpiTp('live.loading_program', 'A carregar {program}...', { program });  // lote F8 2026-09-09""",
     """            if (_liveInstance || _liveFleetMode(program)) {   // 2026-09-21: sem canal, tema com frota carrega o Fleet filtrado
                const label = _liveFleetMode(program) ? t('live.loading_fleet') : _kpiTp('live.loading_program', 'A carregar {program}...', { program });  // lote F8 2026-09-09""", 1),
    # P3: liveChangeChannel
    ("""            if (!instance) { if (_liveProgram !== 'fleet') _liveShowNoInstance(tabId, null); return; }""",
     """            if (!instance) { if (_liveProgram !== 'fleet') liveSetProgram(tabId, _liveProgram); return; }   // 2026-09-21: o programa decide (frota por tema ou neutro)""", 1),
    ("""            _liveShowLoading(tabId, _kpiTp('live.connecting', 'A ligar a {instance}…', { instance }));""",
     """            _liveGaugesVisible(tabId, true);   // 2026-09-21: os medidores voltam ao escolher canal
            _liveShowLoading(tabId, _kpiTp('live.connecting', 'A ligar a {instance}…', { instance }));""", 1),
    # P4: _liveRefresh + liveChangeRate
    ("""            if (!_liveInstance && _liveProgram !== 'fleet') return;""",
     """            if (!_liveInstance && !_liveFleetMode()) return;   // 2026-09-21: modo frota por tema tambem refresca""", 1),
    ("""                const isFleet = _liveProgram === 'fleet';""",
     """                const isFleet = _liveFleetMode();   // 2026-09-21: 'fleet' ou tema sem canal -> endpoint do Fleet""", 1),
    ("""            if (_liveInstance && !_livePaused) {""",
     """            if ((_liveInstance || _liveFleetMode()) && !_livePaused) {   // 2026-09-21""", 1),
    # P5: dispatch
    ("""            if (program === 'queries') return _liveRenderQueries(data, tabId);""",
     """            if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && data.instances) return _liveRenderFleetTheme(program, data, tabId);   // 2026-09-21
            if (program === 'queries') return _liveRenderQueries(data, tabId);""", 1),
]

KEYS = {
    "pt": {"fleet_theme_title": "Frota · {theme}",
           "fleet_theme_sub": "{n} linhas · {d} instâncias com drill neste ciclo · {t} na frota",
           "fleet_theme_note": "Sem canal selecionado: só as instâncias onde há problema agora (o mesmo drill do Fleet). Clique numa linha para abrir a instância neste programa; escolha um canal para ver tudo.",
           "fleet_theme_empty": "Nenhuma instância com problema de {theme} neste ciclo",
           "fleet_theme_neutral": "Este programa não tem vista de frota: selecione um canal."},
    "en": {"fleet_theme_title": "Fleet · {theme}",
           "fleet_theme_sub": "{n} rows · {d} instances drilled this cycle · {t} in the fleet",
           "fleet_theme_note": "No channel selected: only the instances with a problem right now (the same drill as Fleet). Click a row to open that instance in this program; pick a channel to see everything.",
           "fleet_theme_empty": "No instance with a {theme} problem this cycle",
           "fleet_theme_neutral": "This program has no fleet view: select a channel."},
    "es": {"fleet_theme_title": "Flota · {theme}",
           "fleet_theme_sub": "{n} filas · {d} instancias con drill en este ciclo · {t} en la flota",
           "fleet_theme_note": "Sin canal seleccionado: solo las instancias con problema ahora (el mismo drill de Fleet). Haga clic en una fila para abrir la instancia en este programa; elija un canal para ver todo.",
           "fleet_theme_empty": "Ninguna instancia con problema de {theme} en este ciclo",
           "fleet_theme_neutral": "Este programa no tiene vista de flota: seleccione un canal."},
}

TESTES = {T_CANAIS: [
    ("""    assert "if (!instance) { if (_liveProgram !== 'fleet') _liveShowNoInstance(tabId, null); return; }" in PORTAL""",
     """    assert "if (!instance) { if (_liveProgram !== 'fleet') liveSetProgram(tabId, _liveProgram); return; }" in PORTAL   # 2026-09-21: o programa decide (frota por tema ou neutro)""", 1),
]}

TESTE_NOVO = '''# -*- coding: utf-8 -*-
"""
2026-09-21 (owner): sem canal, cada programa mostra a frota so' do seu tema (payload do Fleet, sem endpoint novo).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LIVE = PORTAL[PORTAL.index("const _liveLastData = {};"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
TEMAS = ("queries", "blocking", "tempdb", "waits", "alwayson", "connections", "errorlog", "space")


def test_modo_frota_por_tema_existe_e_cobre_os_8_temas():
    assert "function _liveFleetMode(program)" in LIVE and "function _liveRenderFleetTheme(program, data, tabId)" in LIVE
    m = re.search(r"const _LIVE_FLEET_THEME = \\{([^}]*)\\};", LIVE)
    assert m and set(re.findall(r"(\\w+): 1", m.group(1))) == set(TEMAS)
    for tema in TEMAS:
        assert f"program === '{tema}'" in LIVE[LIVE.index("function _liveRenderFleetTheme"):]


def test_sem_canal_o_programa_decide_e_o_refresh_usa_o_fleet():
    assert "if (!instance) { if (_liveProgram !== 'fleet') liveSetProgram(tabId, _liveProgram); return; }" in LIVE
    assert "if (_liveInstance || _liveFleetMode(program)) {" in LIVE
    assert "if (!_liveInstance && !_liveFleetMode()) return;" in LIVE
    assert "const isFleet = _liveFleetMode();" in LIVE
    assert "if ((_liveInstance || _liveFleetMode()) && !_livePaused) {" in LIVE
    # o despacho so' entra em modo frota (sem instancia) e com payload do Fleet (instances)
    assert "if (program !== 'fleet' && !_liveInstance && _LIVE_FLEET_THEME[program] && data && data.instances) return _liveRenderFleetTheme(program, data, tabId);" in LIVE
    # medidores: escondidos em modo frota, voltam ao escolher canal
    assert "s.style.display = _liveFleetMode(program) ? 'none' : '';" in LIVE and "_liveGaugesVisible(tabId, true);" in LIVE
    # programas sem vista de frota mantem o estado neutro (o ramo else de liveSetProgram continua)
    assert "_liveShowNoInstance(tabId, program);  // 2026-09-11" in LIVE


def test_linhas_abrem_a_instancia_no_programa_e_a_nota_esta_na_vista():
    r = LIVE[LIVE.index("function _liveRenderFleetTheme"):LIVE.index("window._liveFleetMode = _liveFleetMode;")]
    assert "_fleetSwitchTo('${esc(inst)}','${prog}')" in r and "_fleetSwitchTo('${esc(first)}','waits')" in r
    assert "_kpiT('live.fleet_theme_note'" in r and "_kpiTp('live.fleet_theme_title'" in r and "_kpiTp('live.fleet_theme_empty'" in r
    assert "_fleetSpacePanel(data.space_risk)" in r and "_fleetCopySql(this)" in r
    assert "font-size:1[01]px" not in r   # tipografia LIVE: >= 12px


def test_i18n_nas_tres_linguas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static/i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for k in ("fleet_theme_title", "fleet_theme_sub", "fleet_theme_note", "fleet_theme_empty", "fleet_theme_neutral"):
            assert k in d, (loc, k)
        assert "{theme}" in d["fleet_theme_title"] and "{n}" in d["fleet_theme_sub"] and "{theme}" in d["fleet_theme_empty"]
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def _inserir_keys(texto, loc):
    eol = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.split(eol)
    idx = [i for i, l in enumerate(linhas) if l.strip().startswith('"help_io_next":')]
    if len(idx) != 1:
        raise SystemExit(f"[ABORT] {loc}.json: help_io_next nao encontrado 1x")
    ind = linhas[idx[0]][:len(linhas[idx[0]]) - len(linhas[idx[0]].lstrip())]
    novas = [f'{ind}"{k}": {json.dumps(v, ensure_ascii=False)},' for k, v in KEYS[loc].items()]
    novo = eol.join(linhas[:idx[0] + 1] + novas + linhas[idx[0] + 1:])
    antes, depois = json.loads(texto), json.loads(novo)
    extra = set(depois["live"]) - set(antes["live"])
    if extra != set(KEYS[loc]):
        raise SystemExit(f"[ABORT] {loc}.json: insercao inesperada {extra}")
    for k in extra:
        depois["live"].pop(k)
    if depois != antes:
        raise SystemExit(f"[ABORT] {loc}.json: o resto do JSON mudou")
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    portal_p = base / PORTAL
    portal = portal_p.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    for dep in ("_fleetSpacePanel", "_fleetCopySql", "_fleetSwitchTo", "_liveShowNoInstance"):
        if dep not in portal:
            print(f"[ABORT] dependencia {dep} ausente (lotes de 18/09 nao aplicados)"); return 1
    novo_portal = _apply(portal, EDITS_PORTAL, "portal")
    novos_json = {}
    for loc in ("pt", "en", "es"):
        p = base / "static/i18n" / f"{loc}.json"
        if not p.exists():
            print(f"[skip] {p} ausente na copia"); continue
        t = p.read_bytes().decode("utf-8")
        if '"fleet_theme_title"' in t:
            print(f"[ABORT] {loc}.json ja tem fleet_theme_title"); return 1
        novos_json[p] = _inserir_keys(t, loc)
    testes = {rel: _apply((base / rel).read_bytes().decode("utf-8"), edits, str(rel)) for rel, edits in TESTES.items() if (base / rel).exists()}
    print(f"[ok] portal {len(EDITS_PORTAL)} blocos (constantes+renderer, liveSetProgram, liveChangeChannel, _liveRefresh, liveChangeRate, dispatch); locales {len(novos_json)} (5 chaves); testes {len(testes)} actualizado(s) + 1 novo")
    if check:
        print("--check OK. Nada escrito."); return 0
    portal_p.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    for rel, t in testes.items():
        (base / rel).write_bytes(t.encode("utf-8")); print(f"[write] {rel}")
    novo_p = base / T_NOVO
    novo_p.parent.mkdir(parents=True, exist_ok=True)
    novo_p.write_bytes(TESTE_NOVO.encode("utf-8")); print(f"[write] {T_NOVO}")
    for p, t in novos_json.items():
        p.write_bytes(t.encode("utf-8")); print(f"[write] {p.relative_to(base)}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > sem canal > Queries/Blocking/TempDB/Waits/AG/Conn/ErrLog/Espaco.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
