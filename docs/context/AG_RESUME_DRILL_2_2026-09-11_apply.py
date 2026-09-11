# -*- coding: utf-8 -*-
"""LOTE AG-RESUME-2 (afinacao apos a 1a captura do owner, 2026-09-11 15:22) -- so portal + i18n.

O que a captura mostrou de errado no MEU desenho (nao no calculo):
  1. Base SUSPENDED aparecia como "STALLED" a vermelho. Suspensa nao e' estagnada: nao ha resume
     em curso ate alguem fazer RESUME. Passa a: tile "Suspensa" com o MOTIVO explicado
     (SUSPEND_FROM_REDO = o redo da secundaria bateu num erro), banner proprio com o comando
     RESUME comentado (correr na secundaria) e o aviso "se voltar a suspender, e' o redo a bater
     no mesmo erro: errorlog da secundaria 823/824/9002/1453 antes de insistir".
     "Estagnado" fica reservado a SYNCING/NOT_SYNC/INITIALIZING/REVERTING sem descer.
  2. "Taxa medida 0 MB/s -- a drenar" a verde. Declive ~0 nao e' drenar: passa a tres estados
     com epsilon de 1 KB/s (a drenar / estavel / a crescer), verde so' a drenar, vermelho a crescer.
  3. "Progresso 0%" em base suspensa le-se como avaria. O calculo esta certo (nada se moveu desde
     a fila inicial), mas em SUSPENDED nao ha progresso a medir: mostra "--" com "aguarda RESUME".
     Fora de suspensa mantem 1 - fila/baseline (baseline = maior fila vista).
  4. "Fila de envio 0,0 MB" quando a primaria NAO reportou (null): zero fabricado, contra a regra
     da casa (ausencia de dado != zero). Passa a "--".
  5. Grafico plano virava um bloco vermelho: a sparkline generica enche a area ate ao topo quando
     todos os valores sao iguais. Passa a SVG proprio: eixo 0..max*1,15, area leve, rotulos de
     hora inicial/final e do maximo.
  6. Redundancia: "amostras: 30" estava na barra de topo E no tile. Sai do tile; o sub do tile de
     estado passa a dizer o motivo (suspensa) ou a tendencia. Tamanhos passam a GB acima de 1 GB.
  7. Faltavam os "?" de ajuda: cada tile ganha um "?" (padrao dg2-help, tooltip) com a formula em
     linguagem corrente, e o cabecalho ganha "ultimo redo aplicado" e "ultimo commit" da replica
     acompanhada (o mais proximo de "suspensa desde" que a DMV oferece).
  Traducoes: 26 chaves novas em alwayson.resume.* (pt-PT / en-US / es). NOTA: os cabecalhos
  "Base / Sync State / Health / DB State / Suspensa / Log Send Queue / Redo Queue", "Sim/Nao" e
  "N/A" das tabelas do separador Always On (por baixo do modal) sao divida i18n PRE-EXISTENTE da
  wave BUG-003 (nao deste lote) -- fica registada para o lote F9 do linguista.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/AG_RESUME_DRILL_2_2026-09-11_apply.py --check
  py docs/context/AG_RESUME_DRILL_2_2026-09-11_apply.py
  py -m pytest tests/unit/test_alwayson_resume_20260911.py tests/unit/test_i18n_parity.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; Always On do SQLHDSPRD406 > MYBAGP2 > Acompanhar
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_alwayson_resume_20260911.py"
I18N = {loc: ROOT / "static" / "i18n" / f"{loc}.json" for loc in ("pt", "en", "es")}

START_MARK = "        function _agResumeIngest(run, j) {"
END_MARK = "\n        // ---- Vista Avancada RICA (topo polido + cards ricos + Resumo Executivo) ----\n"

NEW_BLOCK = r'''        function _agResumeIngest(run, j) {
            const tgt = _agResumePickTarget(j);
            const lsqRaw = tgt ? tgt.log_send_queue_kb : null, rqRaw = tgt ? tgt.redo_queue_kb : null;
            const total = (lsqRaw || 0) + (rqRaw || 0);
            const s = { t: Date.now(), lsq: lsqRaw, rq: rqRaw, total: total, code: tgt ? tgt.state_code : 'UNKNOWN', mode: tgt ? String(tgt.mode || '') : '',
                        reason: tgt ? (tgt.suspend_reason || '') : '', lastRedone: tgt ? tgt.last_redone_time : null, lastCommit: tgt ? tgt.last_commit_time : null };
            if (run.target && tgt && run.target !== tgt.replica_server) { run.samples = []; run.baseline = null; run.done = false; }  // mudou a replica-alvo: recomeca
            run.target = tgt ? tgt.replica_server : null;
            run.samples.push(s);
            if (run.samples.length > 720) run.samples.shift();  // 2 h
            run.baseline = (run.baseline === null) ? total : Math.max(run.baseline, total);  // maior fila vista = ponto de partida do progresso
        }
        function _agResumeSlope(samples, n) {
            const k = samples.slice(-Math.min(n || 6, samples.length));
            if (k.length < 2) return null;
            const t0 = k[0].t; let sx = 0, sy = 0, sxx = 0, sxy = 0;
            k.forEach(function (p) { const x = (p.t - t0) / 1000; sx += x; sy += p.total; sxx += x * x; sxy += x * p.total; });
            const m = k.length, den = m * sxx - sx * sx;
            return den === 0 ? null : (m * sxy - sx * sy) / den;  // KB/s (negativo = a drenar)
        }
        function _agResumeMetrics(run, j) {
            const d = (j && j.defaults) || {};
            const doneKb = d.done_queue_kb || 64, doneN = d.done_samples || 3, stallN = d.stall_samples || 18;
            const s = run.samples, last = s[s.length - 1];
            const slope = _agResumeSlope(s, 6);
            // epsilon 1 KB/s: declive ~0 nao e' "a drenar" nem "a crescer"
            const trend = slope === null ? 'none' : (slope < -1 ? 'draining' : (slope > 1 ? 'growing' : 'stable'));
            const suspended = last.code === 'SUSPENDED';
            const eta = (trend === 'draining' && last.total > doneKb) ? last.total / (-slope) : null;
            const progress = (!suspended && run.baseline && run.baseline > 0) ? Math.max(0, Math.min(100, 100 * (1 - last.total / run.baseline))) : null;
            const isAsync = /^ASYNC/i.test(last.mode);
            const okCode = isAsync ? 'ASYNC_HEALTHY' : 'SYNCED';
            const tail = s.slice(-doneN);
            const done = tail.length >= doneN && tail.every(function (p) { return p.code === okCode; });
            // estagnacao so' faz sentido com um resume EM CURSO (nao suspensa, nao concluida)
            let stalled = false;
            if (!done && !suspended && ['SYNCING', 'NOT_SYNC', 'INITIALIZING', 'REVERTING'].indexOf(last.code) >= 0 && s.length >= stallN && last.total > doneKb) {
                const w = s.slice(-stallN);
                stalled = w[w.length - 1].total >= w[0].total * 0.98;  // nao desceu 2% em 3 min
            }
            run.done = done;
            return { slope: slope, trend: trend, eta: eta, progress: progress, done: done, stalled: stalled, suspended: suspended, isAsync: isAsync, last: last, doneKb: doneKb };
        }
        // numeros no idioma ACTIVO do portal (o motor i18n poe o codigo em <html lang>), nao pt-PT fixo
        function _agResumeLocale() { return (document.documentElement && document.documentElement.lang) || 'pt-PT'; }
        function _agResumeFmtSize(kb) {
            if (kb === null || kb === undefined || isNaN(kb)) return '—';
            const mb = kb / 1024, loc = _agResumeLocale();
            if (mb >= 1024) return (mb / 1024).toLocaleString(loc, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' GB';
            return mb.toLocaleString(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' MB';
        }
        function _agResumeFmtDur(sec) {
            if (sec === null || sec === undefined || !isFinite(sec)) return '—';
            sec = Math.round(sec); const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s2 = sec % 60;
            return (d ? d + 'd ' : '') + String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s2).padStart(2, '0');
        }
        function _agResumeSev(code) {
            if (code === 'SUSPENDED' || code === 'NOT_SYNC') return 'CRITICAL';
            if (code === 'SYNCING' || code === 'REVERTING' || code === 'INITIALIZING') return 'WARNING';
            if (code === 'SYNCED' || code === 'ASYNC_HEALTHY' || code === 'PRIMARY') return 'OK';
            return 'INFO';
        }
        function _agResumeReason(reason) {
            const r = String(reason || '').toUpperCase();
            if (!r) return '';
            const k = 'alwayson.resume.reason_' + r;
            const txt = t(k);
            return (txt && txt !== k) ? txt : r;
        }
        // Sparkline propria (revisao externa 11/09: a generica virava um bloco com serie constante e ficava
        // a 560 px no modal maximizado). Largura MEDIDA do contentor, eixo 0..max*1,15, area leve, rotulos
        // de hora inicial/final, maximo e minimo; serie constante = linha fina a meio com "estavel em X".
        function _agResumeSpark(samples, color) {
            if (!samples || samples.length < 2) return '<div class="diag-empty">' + _diagEsc(t('alwayson.resume.waiting_samples')) + '</div>';
            const body = document.getElementById('ag-resume-body');
            const W = Math.max(320, ((body && body.clientWidth) || 640) - 44), H = 96, padL = 8, padR = 8, padT = 16, padB = 18;
            const w = W - padL - padR, h = H - padT - padB;
            const vals = samples.map(function (p) { return p.total / 1024; });
            const vmax = Math.max.apply(null, vals), vmin = Math.min.apply(null, vals);
            const fmtT = function (ms) { const d = new Date(ms); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + ':' + String(d.getSeconds()).padStart(2, '0'); };
            const axis = '<line x1="' + padL + '" y1="' + (padT + h) + '" x2="' + (padL + w) + '" y2="' + (padT + h) + '" stroke="var(--color-border)" stroke-width="1"/>' +
                '<text x="' + padL + '" y="' + (H - 4) + '" font-size="10" fill="var(--color-text-tertiary)">' + fmtT(samples[0].t) + '</text>' +
                '<text x="' + (padL + w) + '" y="' + (H - 4) + '" font-size="10" text-anchor="end" fill="var(--color-text-tertiary)">' + fmtT(samples[samples.length - 1].t) + '</text>';
            const open = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" style="display:block; max-width:100%;" role="img" aria-label="' + _diagEsc(t('alwayson.resume.chart_title')) + '">';
            if (vmax - vmin < 0.05) {  // constante: linha fina a meio + rotulo, nunca area
                const y = (padT + h / 2).toFixed(1);
                return open + axis +
                    '<line x1="' + padL + '" y1="' + y + '" x2="' + (padL + w) + '" y2="' + y + '" stroke="' + color + '" stroke-width="1.5" stroke-dasharray="4 3"/>' +
                    '<circle cx="' + (padL + w).toFixed(1) + '" cy="' + y + '" r="3.5" fill="' + color + '"/>' +
                    '<text x="' + (padL + 4) + '" y="' + (padT + h / 2 - 6).toFixed(1) + '" font-size="11" fill="var(--color-text-secondary)">' + _diagEsc(t('alwayson.resume.chart_flat')) + ' ' + _agResumeFmtSize(vmax * 1024) + '</text></svg>';
            }
            const max = vmax * 1.15;
            const pts = vals.map(function (v, i) { return { x: padL + (i / (vals.length - 1)) * w, y: padT + h - (v / max) * h }; });
            let line = ''; pts.forEach(function (c, i) { line += (i === 0 ? 'M' : 'L') + c.x.toFixed(1) + ',' + c.y.toFixed(1) + ' '; });
            const area = line + 'L' + (padL + w).toFixed(1) + ',' + (padT + h).toFixed(1) + ' L' + padL + ',' + (padT + h).toFixed(1) + ' Z';
            const last = pts[pts.length - 1];
            return open + axis +
                '<path d="' + area + '" fill="' + color + '" fill-opacity="0.10"/>' +
                '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linejoin="round"/>' +
                '<circle cx="' + last.x.toFixed(1) + '" cy="' + last.y.toFixed(1) + '" r="3.5" fill="' + color + '"/>' +
                '<text x="' + (padL + w) + '" y="11" font-size="10" text-anchor="end" fill="var(--color-text-tertiary)">' + _diagEsc(t('alwayson.resume.chart_max')) + ' ' + _agResumeFmtSize(vmax * 1024) + '</text>' +
                '<text x="' + padL + '" y="11" font-size="10" fill="var(--color-text-tertiary)">' + _diagEsc(t('alwayson.resume.chart_min')) + ' ' + _agResumeFmtSize(vmin * 1024) + '</text>' +
                '</svg>';
        }
        function _agResumeRender(ov, run, j) {
            const m = _agResumeMetrics(run, j);
            const T = function (k) { return _diagEsc(t('alwayson.resume.' + k)); };
            const help = function (k) { return '<span class="dg2-help" tabindex="0" title="' + T(k) + '" aria-label="' + T(k) + '">?</span>'; };
            const sevCls = { CRITICAL: 'red', WARNING: 'yellow', OK: 'green', INFO: 'gray' };
            const stateSev = m.done ? 'OK' : (m.stalled ? 'CRITICAL' : _agResumeSev(m.last.code));
            const tok = getSevTokens(stateSev);
            const tile = function (label, value, sub, cls, helpKey) {
                return '<div class="stat-card ' + (cls || 'gray') + '"><div class="label">' + label + (helpKey ? ' ' + help(helpKey) : '') + '</div><div class="value" style="font-variant-numeric:tabular-nums;">' + value + '</div>' + (sub ? '<div class="diag-sub">' + sub + '</div>' : '') + '</div>';
            };
            const stateLbl = m.done ? T('completed') : (m.stalled ? T('stalled') : T('state_' + m.last.code));
            const stateSub = m.suspended ? _diagEsc(_agResumeReason(m.last.reason)) : (m.done ? '' : T('trend_' + m.trend));
            const rateVal = m.slope === null ? '—' : (Math.abs(m.slope) / 1024).toLocaleString(_agResumeLocale(), { maximumFractionDigits: 2 }) + ' MB/s';
            const rateCls = m.trend === 'draining' ? 'green' : (m.trend === 'growing' ? 'red' : 'gray');
            const etaSub = m.suspended ? T('eta_suspended') : (m.trend === 'growing' ? T('eta_growing') : (m.eta === null ? T('eta_unknown') : T('eta_by_slope')));
            const progVal = m.progress === null ? '—' : Math.round(m.progress) + '%';
            const progSub = m.suspended ? T('progress_suspended') : (T('progress_baseline') + ' ' + _agResumeFmtSize(run.baseline));
            let banner = '';
            if (m.done) {
                banner = '<div class="dg2-note" style="border-color:var(--sev-ok-solid);"><i class="fas fa-check-circle" aria-hidden="true"></i><span>' + T(m.isAsync ? 'completed_async' : 'completed_sync') + '</span></div>';
            } else if (m.suspended) {
                const secName = run.target || '';
                const cmd = '-- ' + t('alwayson.resume.resume_cmd_where') + ' ' + secName + '\nALTER DATABASE [' + String(ov._ctx.db || '').replace(/]/g, ']]') + '] SET HADR RESUME;';
                banner = '<div class="dg2-note" style="border-color:var(--sev-critical-solid);"><i class="fas fa-pause-circle" aria-hidden="true"></i><span>' + T('suspended_note') + ' <strong>' + _diagEsc(_agResumeReason(m.last.reason)) + '</strong> ' + T('suspended_note_2') + '</span></div>' +
                    '<div class="ag-resume-cmd"><div class="diag-section-title">' + T('resume_cmd_title') + ' ' + help('help_resume_cmd') + '</div>' +
                    '<button type="button" class="diag-copy-btn" data-diag-copy="agresume"><i class="fas fa-copy" aria-hidden="true"></i> ' + T('copy_cmd') + '</button>' +
                    '<pre class="diag-sql" data-diag-sql="agresume" style="display:block;">' + _diagEsc(cmd) + '</pre>' +
                    '<div class="dg2-subtle">' + T('resume_cmd_note') + '</div></div>';
            } else if (m.stalled) {
                banner = '<div class="dg2-note" style="border-color:var(--sev-critical-solid);"><i class="fas fa-exclamation-triangle" aria-hidden="true"></i><span>' + T('stalled_note') + '</span></div>';
            }
            const head = '<div class="ag-resume-head"><span>' + T('sampled_on') + ' <strong>' + _diagEsc(j.sampled_on || '') + '</strong></span>' +
                (run.target ? '<span>' + T('target_replica') + ' <strong>' + _diagEsc(run.target) + '</strong> · ' + T(m.isAsync ? 'mode_async' : 'mode_sync') + '</span>' : '') +
                (m.last.lastRedone ? '<span>' + T('last_redone') + ' <strong>' + _diagEsc(m.last.lastRedone) + '</strong></span>' : '') +
                (m.last.lastCommit ? '<span>' + T('last_commit') + ' <strong>' + _diagEsc(m.last.lastCommit) + '</strong></span>' : '') +
                (j.server_now ? '<span>' + T('server_time') + ' ' + _diagEsc(j.server_now) + '</span>' : '') + '</div>';
            const tiles = '<div class="diag-summary-grid ag-resume-tiles">' +
                tile(T('tile_state'), stateLbl, stateSub, sevCls[stateSev], 'help_state') +
                tile(T('tile_send_queue'), _agResumeFmtSize(m.last.lsq), m.last.lsq === null ? T('not_reported') : '', (m.last.lsq || 0) > (window._AG_QUEUE_WARN_KB) ? 'yellow' : 'gray', 'help_send') +
                tile(T('tile_redo_queue'), _agResumeFmtSize(m.last.rq), m.last.rq === null ? T('not_reported') : '', (m.last.rq || 0) > (window._AG_QUEUE_WARN_KB) ? 'yellow' : 'gray', 'help_redo') +
                tile(T('tile_rate'), rateVal, T('trend_' + m.trend), rateCls, 'help_rate') +
                tile(T('tile_eta'), _agResumeFmtDur(m.eta), etaSub, 'gray', 'help_eta') +
                tile(T('tile_progress'), progVal, progSub, 'gray', 'help_progress') +
                '</div>';
            const chart = '<div class="ag-resume-chart"><div class="diag-section-title">' + T('chart_title') + ' ' + help('help_chart') + '</div>' + _agResumeSpark(run.samples, tok.fill) + '</div>';
            const cols = [['col_replica', function (r) { return _diagEsc(r.replica_server || ''); }],
                          ['col_role', function (r) { return _diagEsc(r.role || ''); }],
                          ['col_mode', function (r) { return _diagEsc(String(r.mode || '').replace('_COMMIT', '')); }],
                          ['col_connected', function (r) { return _diagEsc(r.connected || ''); }],
                          ['col_sync_state', function (r) { const sv = _agResumeSev(r.state_code); return '<span class="gap-pill ' + (sv === 'CRITICAL' ? 'crit' : sv === 'WARNING' ? 'warn' : sv === 'OK' ? 'ok' : 'muted') + '">' + T('state_' + r.state_code) + '</span>'; }],
                          ['col_health', function (r) { return _diagEsc(r.sync_health || ''); }],
                          ['col_suspended', function (r) { return r.is_suspended ? '<strong style="color:var(--sev-critical-text)">' + T('yes') + '</strong>' + (r.suspend_reason ? ' <span class="dg2-subtle" title="' + _diagEsc(_agResumeReason(r.suspend_reason)) + '">' + _diagEsc(r.suspend_reason) + '</span>' : '') : T('no'); }],
                          ['col_send_queue', function (r) { return _agResumeFmtSize(r.log_send_queue_kb); }],
                          ['col_redo_queue', function (r) { return _agResumeFmtSize(r.redo_queue_kb) + (r.source === 'secondary_fallback' ? ' <span class="dg2-subtle" title="' + T('fallback_note') + '">*</span>' : ''); }],
                          ['col_lag', function (r) { return r.state_code === 'PRIMARY' ? '—' : _agResumeFmtDur(r.lag_seconds); }]];
            const table = '<div class="ag-resume-table"><table><thead><tr>' + cols.map(function (c) { return '<th>' + T(c[0]) + '</th>'; }).join('') + '</tr></thead><tbody>' +
                (j.replicas || []).map(function (r) { return '<tr' + (r.replica_server === run.target ? ' class="ag-resume-target"' : '') + '>' + cols.map(function (c) { return '<td>' + c[1](r) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></div>';
            const notes = (j.notes && j.notes.length) ? '<div class="dg2-subtle" style="margin-top:8px;">' + _diagEsc(j.notes.join(' · ')) + '</div>' : '';
            document.getElementById('ag-resume-body').innerHTML = '<div class="ag-resume-wrap" data-diag-root="1">' + head + banner + tiles + chart + table + notes + '</div>';
        }
'''

# edicoes pontuais FORA do bloco substituido (revisao externa 11/09)
EXTRA_EDITS = [
    # paragem defensiva do timer ao reabrir + guardar a ultima amostra para re-render ao maximizar
    ("            ov._ctx = { primary: primary, ag: ag, db: db, key: key };\n",
     "            _agResumeStop(ov);  // defensivo: nunca dois timers no mesmo overlay\n"
     "            ov._ctx = { primary: primary, ag: ag, db: db, key: key };\n", 1),
    ("                _agResumeIngest(run, j);\n                _agResumeRender(ov, run, j);\n",
     "                _agResumeIngest(run, j);\n                ov._lastJ = j;\n                _agResumeRender(ov, run, j);\n", 1),
    ("                if (e.target.closest && e.target.closest('[data-ag-resume-max]')) { if (typeof toggleMaximizeModal === 'function') toggleMaximizeModal('ag-resume-overlay'); return; }\n",
     "                if (e.target.closest && e.target.closest('[data-ag-resume-max]')) {\n"
     "                    if (typeof toggleMaximizeModal === 'function') toggleMaximizeModal('ag-resume-overlay');\n"
     "                    // o grafico e' medido do contentor: re-render com a nova largura\n"
     "                    setTimeout(function () { if (ov._ctx && ov._lastJ && window._agResumeRuns[ov._ctx.key]) _agResumeRender(ov, window._agResumeRuns[ov._ctx.key], ov._lastJ); }, 60);\n"
     "                    return;\n"
     "                }\n", 1),
    # tabela de replicas da vista local: null cru -> N/A (padrao da tabela)
    ("                                                    <td>${r.operational_state}</td>\n",
     "                                                    <td>${r.operational_state ?? 'N/A'}</td>\n", 1),
    # unidade nos cabecalhos das filas (a DMV devolve KB; a mesma metrica aparecia sem unidade)
    ("<th>Log Send Queue</th><th>Redo Queue</th><th></th></tr>",
     "<th>Log Send Queue (KB)</th><th>Redo Queue (KB)</th><th></th></tr>", 1),
    ('<th style="padding: 12px; border-bottom: 2px solid ${borderColor}; color: ${borderColor};">Log Send Queue</th>',
     '<th style="padding: 12px; border-bottom: 2px solid ${borderColor}; color: ${borderColor};">Log Send Queue (KB)</th>', 1),
    ('<th style="padding: 12px; border-bottom: 2px solid ${borderColor}; color: ${borderColor};">Redo Queue</th>',
     '<th style="padding: 12px; border-bottom: 2px solid ${borderColor}; color: ${borderColor};">Redo Queue (KB)</th>', 1),
]
EN_FIX = ("Track this database's resynchronisation", "Track this database's resynchronization")

CSS_OLD = "        .ag-resume-btn { padding: 4px 8px; font-size: 11px; }\n"
CSS_NEW = ("        .ag-resume-btn { padding: 4px 8px; font-size: 11px; }\n"
           "        .ag-resume-cmd { display: grid; gap: 6px; }\n"
           "        .ag-resume-cmd .diag-copy-btn { justify-self: start; }\n"
           "        .ag-resume-tiles .dg2-help { margin-left: 2px; }\n")

KEYS = {
    "trend_none": ("a aguardar amostras", "waiting for samples", "esperando muestras"),
    "trend_draining": ("a drenar", "draining", "drenando"),
    "trend_stable": ("estável: a fila não se move", "stable: the queue is not moving", "estable: la cola no se mueve"),
    "trend_growing": ("a crescer: a primária gera log mais depressa do que a réplica aplica", "growing: the primary generates log faster than the replica applies it", "creciendo: la primaria genera log más rápido de lo que la réplica aplica"),
    "not_reported": ("não reportado pela primária", "not reported by the primary", "no reportado por la primaria"),
    "eta_suspended": ("sem estimativa enquanto suspensa", "no estimate while suspended", "sin estimación mientras esté suspendida"),
    "eta_growing": ("sem estimativa: a fila está a crescer", "no estimate: the queue is growing", "sin estimación: la cola está creciendo"),
    "progress_suspended": ("aguarda RESUME", "awaiting RESUME", "espera RESUME"),
    "last_redone": ("último redo aplicado", "last redo applied", "último redo aplicado"),
    "last_commit": ("último commit na réplica", "last commit on the replica", "último commit en la réplica"),
    "chart_max": ("máx.", "max", "máx."),
    "chart_min": ("mín.", "min", "mín."),
    "chart_flat": ("estável em", "steady at", "estable en"),
    "copy_cmd": ("Copiar comando", "Copy command", "Copiar comando"),
    "suspended_note": ("Base suspensa: não há resume em curso. Motivo reportado:", "Database suspended: no resume in progress. Reported reason:", "Base suspendida: no hay resume en curso. Motivo reportado:"),
    "suspended_note_2": ("O acompanhamento continua; quando alguém fizer RESUME, a fila começa a descer aqui.", "Tracking continues; once someone runs RESUME, the queue will start dropping here.", "El seguimiento continúa; cuando alguien ejecute RESUME, la cola empezará a bajar aquí."),
    "resume_cmd_title": ("Comando para retomar (não é executado pelo WatcherDB)", "Command to resume (WatcherDB does not run it)", "Comando para reanudar (WatcherDB no lo ejecuta)"),
    "resume_cmd_where": ("correr na SECUNDÁRIA", "run on the SECONDARY", "ejecutar en la SECUNDARIA"),
    "resume_cmd_note": ("Antes de retomar, veja o errorlog da secundária (separador Log deste servidor) e a sessão XE AlwaysOn_health: se o motivo for redo (823/824 corrupção, 9002 log cheio, 1453), o RESUME volta a suspender no mesmo ponto e a solução é corrigir a causa ou reconstruir a réplica.", "Before resuming, check the secondary's errorlog (this server's Log tab) and the AlwaysOn_health XE session: if the reason is redo (823/824 corruption, 9002 log full, 1453), RESUME will suspend again at the same point and the fix is to address the cause or rebuild the replica.", "Antes de reanudar, revise el errorlog de la secundaria (pestaña Log de este servidor) y la sesión XE AlwaysOn_health: si el motivo es redo (823/824 corrupción, 9002 log lleno, 1453), RESUME volverá a suspender en el mismo punto y la solución es corregir la causa o reconstruir la réplica."),
    "reason_SUSPEND_FROM_REDO": ("o redo na secundária bateu num erro (disco, corrupção ou log cheio) e parou", "redo on the secondary hit an error (disk, corruption or full log) and stopped", "el redo en la secundaria encontró un error (disco, corrupción o log lleno) y se detuvo"),
    "reason_SUSPEND_FROM_USER": ("suspensa manualmente por um utilizador", "suspended manually by a user", "suspendida manualmente por un usuario"),
    "reason_SUSPEND_FROM_PARTNER": ("suspensa a pedido da réplica parceira", "suspended at the partner replica's request", "suspendida a petición de la réplica asociada"),
    "reason_SUSPEND_FROM_CAPTURE": ("erro ao capturar log na primária", "error capturing log on the primary", "error al capturar log en la primaria"),
    "reason_SUSPEND_FROM_APPLY": ("erro ao aplicar log na secundária", "error applying log on the secondary", "error al aplicar log en la secundaria"),
    "reason_SUSPEND_FROM_RESTART": ("suspensa após reinício do serviço", "suspended after a service restart", "suspendida tras un reinicio del servicio"),
    "reason_SUSPEND_FROM_UNDO": ("em undo após failover", "in undo after a failover", "en undo tras un failover"),
    "reason_SUSPEND_FROM_REVALIDATION": ("em revalidação do log", "revalidating the log", "en revalidación del log"),
    "reason_SUSPEND_FROM_XRF_UPDATE": ("a atualizar referência cruzada de LSN", "updating LSN cross-reference", "actualizando la referencia cruzada de LSN"),
    "help_state": ("Estado da réplica acompanhada, calculado a cada amostra: suspensa vence tudo; depois a reverter, a inicializar, não sincroniza, a sincronizar, sincronizada. Uma réplica assíncrona nunca fica SYNCHRONIZED: com filas drenadas mostra 'assíncrona em dia'. 'Estagnado' = resume em curso mas a fila não desceu 2% em 3 minutos. 'Concluído' = 3 amostras seguidas no estado final.", "State of the tracked replica, computed at every sample: suspended wins over everything; then reverting, initializing, not synchronizing, synchronizing, synchronized. An asynchronous replica never becomes SYNCHRONIZED: with drained queues it shows 'asynchronous, caught up'. 'Stalled' = resume in progress but the queue has not dropped 2% in 3 minutes. 'Completed' = 3 consecutive samples in the final state.", "Estado de la réplica seguida, calculado en cada muestra: suspendida gana a todo; luego revirtiendo, inicializando, no sincroniza, sincronizando, sincronizada. Una réplica asíncrona nunca queda SYNCHRONIZED: con colas drenadas muestra 'asíncrona al día'. 'Estancado' = resume en curso pero la cola no bajó un 2% en 3 minutos. 'Completado' = 3 muestras seguidas en el estado final."),
    "help_send": ("Log que a primária ainda não enviou à réplica (log_send_queue_size, em KB na DMV). Cresce quando a rede ou a réplica não acompanham as escritas.", "Log the primary has not yet sent to the replica (log_send_queue_size, KB in the DMV). Grows when the network or the replica cannot keep up with writes.", "Log que la primaria aún no envió a la réplica (log_send_queue_size, KB en la DMV). Crece cuando la red o la réplica no siguen las escrituras."),
    "help_redo": ("Log já recebido pela réplica mas ainda não aplicado (redo_queue_size). É este o trabalho que falta fazer depois de um RESUME; quando a réplica está suspensa não desce.", "Log already received by the replica but not yet applied (redo_queue_size). This is the work left after a RESUME; while the replica is suspended it does not drop.", "Log ya recibido por la réplica pero aún no aplicado (redo_queue_size). Es el trabajo pendiente tras un RESUME; mientras la réplica está suspendida no baja."),
    "help_rate": ("Velocidade medida pelo WatcherDB: declive da fila total nas últimas 6 amostras (1 minuto), por mínimos quadrados. Não é o rate da DMV, que é uma média móvel do motor e ignora o log novo que a primária continua a gerar. Verde = a drenar; vermelho = a crescer.", "Speed measured by WatcherDB: slope of the total queue over the last 6 samples (1 minute), least squares. Not the DMV rate, which is an engine moving average that ignores the new log the primary keeps generating. Green = draining; red = growing.", "Velocidad medida por WatcherDB: pendiente de la cola total en las últimas 6 muestras (1 minuto), por mínimos cuadrados. No es la tasa de la DMV, que es una media móvil del motor e ignora el log nuevo que la primaria sigue generando. Verde = drenando; rojo = creciendo."),
    "help_eta": ("Fila total a dividir pela velocidade medida. Só existe com a fila a descer; muda a cada amostra e é uma projecção, não uma promessa.", "Total queue divided by the measured speed. Only exists while the queue is dropping; it changes at every sample and is a projection, not a promise.", "Cola total dividida por la velocidad medida. Solo existe con la cola bajando; cambia en cada muestra y es una proyección, no una promesa."),
    "help_progress": ("Quanto da fila inicial já foi drenado: 1 − fila actual / maior fila vista desde a primeira amostra deste acompanhamento. Numa base suspensa não há progresso a medir.", "How much of the initial queue has been drained: 1 − current queue / largest queue seen since this tracking started. There is no progress to measure on a suspended database.", "Cuánto de la cola inicial ya se drenó: 1 − cola actual / mayor cola vista desde la primera muestra de este seguimiento. En una base suspendida no hay progreso que medir."),
    "help_chart": ("Fila total (envio + redo) da réplica acompanhada, uma amostra a cada 10 segundos enquanto este modal estiver aberto. As amostras vivem na memória do browser e perdem-se ao fechar.", "Total queue (send + redo) of the tracked replica, one sample every 10 seconds while this dialog is open. Samples live in the browser's memory and are lost on close.", "Cola total (envío + redo) de la réplica seguida, una muestra cada 10 segundos mientras este diálogo esté abierto. Las muestras viven en la memoria del navegador y se pierden al cerrar."),
    "help_resume_cmd": ("O WatcherDB nunca executa comandos de alteração. Copie e corra no SSMS, ligado à réplica secundária indicada, com uma conta com ALTER ANY AVAILABILITY GROUP ou sysadmin.", "WatcherDB never runs change commands. Copy and run it in SSMS, connected to the indicated secondary replica, with an account holding ALTER ANY AVAILABILITY GROUP or sysadmin.", "WatcherDB nunca ejecuta comandos de cambio. Cópielo y ejecútelo en SSMS, conectado a la réplica secundaria indicada, con una cuenta con ALTER ANY AVAILABILITY GROUP o sysadmin."),
}

TEST_APPEND = r'''

def test_lot2_suspended_is_not_stalled_and_tiles_have_help():
    portal = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
    assert "const suspended = last.code === 'SUSPENDED';" in portal
    assert "['SYNCING', 'NOT_SYNC', 'INITIALIZING', 'REVERTING'].indexOf(last.code) >= 0" in portal
    assert "slope < -1 ? 'draining' : (slope > 1 ? 'growing' : 'stable')" in portal
    assert "function _agResumeSpark(" in portal and "createDiskSparklineSVG(vals, 560" not in portal
    assert "toLocaleString('pt-PT'" not in portal.split("function _agResumeIngest")[1].split("// ---- Vista Avancada RICA")[0]
    assert "${r.operational_state ?? 'N/A'}" in portal and "Redo Queue (KB)" in portal
    for hk in ("help_state", "help_send", "help_redo", "help_rate", "help_eta", "help_progress", "help_chart", "help_resume_cmd"):
        assert "'" + hk + "'" in portal, f"falta o ? de ajuda {hk}"
    assert "SET HADR RESUME;" in portal
    import json
    for loc in ("pt", "en", "es"):
        res = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["alwayson"]["resume"]
        for k in ("trend_stable", "help_rate", "reason_SUSPEND_FROM_REDO", "resume_cmd_note", "progress_suspended"):
            assert res.get(k), f"{loc}: falta alwayson.resume.{k}"
'''


def patch_i18n(raw: str, idx: int):
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    try:
        s = next(i for i, l in enumerate(lines) if l.strip() == '"resume": {' and i > 70 and i < 400)
    except StopIteration:
        return None, 'bloco alwayson.resume nao encontrado (lote 1 aplicado?)'
    existing = set()
    for l in lines[s + 1:s + 200]:
        st = l.strip()
        if st.startswith("}"):
            break
        if st.startswith('"'):
            existing.add(st.split('"')[1])
    if "help_rate" in existing:
        return None, "ja aplicado (help_rate existe)"
    block = [f'      "{k}": {json.dumps(v[idx], ensure_ascii=False)},' for k, v in KEYS.items() if k not in existing]
    lines[s + 1:s + 1] = block
    out = nl.join(lines)
    try:
        json.loads(out)
    except Exception as ex:
        return None, f"json invalido: {ex}"
    return out, None


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    preview_dir = None
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv):
            print("--preview precisa de DIR"); return 2
        preview_dir = Path(argv[i + 1]).resolve()

    problems: list[str] = []
    portal = PORTAL.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in portal else "\n"
    sm, em = START_MARK.replace("\n", eol), END_MARK.replace("\n", eol)
    if portal.count(sm) != 1: problems.append(f"portal: START_MARK {portal.count(sm)}x")
    if portal.count(em) != 1: problems.append(f"portal: END_MARK {portal.count(em)}x")
    if "function _agResumeSpark(" in portal: problems.append("portal: ja aplicado (_agResumeSpark existe)")
    if portal.count(CSS_OLD.replace("\n", eol)) != 1: problems.append("portal: CSS_OLD nao encontrado 1x")
    for old, new, cnt in EXTRA_EDITS:
        c = portal.count(old.replace("\n", eol))
        if c != cnt: problems.append(f"portal: extra esperado {cnt}x, encontrado {c}x: {old.strip()[:70]!r}")
    test_raw = TEST.read_bytes().decode("utf-8") if TEST.exists() else None
    if test_raw is None: problems.append("teste do lote 1 nao existe")
    elif "test_lot2_suspended_is_not_stalled" in test_raw: problems.append("teste: ja aplicado")
    i18n_out = {}
    for idx, loc in enumerate(("pt", "en", "es")):
        out, err = patch_i18n(I18N[loc].read_bytes().decode("utf-8"), idx)
        if err: problems.append(f"{loc}.json: {err}")
        else: i18n_out[I18N[loc]] = out
    if problems:
        print("[ABORT] nada escrito:"); [print("  -", p) for p in problems]; return 1

    a = portal.index(sm); b = portal.index(em)
    new_portal = portal[:a] + NEW_BLOCK.replace("\n", eol) + portal[b:]
    new_portal = new_portal.replace(CSS_OLD.replace("\n", eol), CSS_NEW.replace("\n", eol), 1)
    for old, new, _cnt in EXTRA_EDITS:
        new_portal = new_portal.replace(old.replace("\n", eol), new.replace("\n", eol))
    if I18N["en"] in i18n_out and EN_FIX[0] in i18n_out[I18N["en"]]:
        i18n_out[I18N["en"]] = i18n_out[I18N["en"]].replace(EN_FIX[0], EN_FIX[1]); print("[ok] en.json: grafia americana em button_title")
    removed = portal[a:b].count(eol); added = NEW_BLOCK.count("\n")
    print(f"[ok] portal: bloco _agResumeIngest.._agResumeRender substituido ({removed} -> {added} linhas) + CSS")
    print(f"[ok] i18n: +{len(KEYS)} chaves alwayson.resume.* em pt/en/es")
    print("[ok] teste: +1")
    if check_only:
        print("\n--check OK. Nada escrito."); return 0
    target = preview_dir if preview_dir is not None else ROOT
    def w(path: Path, text: str) -> None:
        out = target / path.relative_to(ROOT); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8")); print(f"[write] {out.relative_to(target)}")
    w(PORTAL, new_portal)
    for p, txt in i18n_out.items(): w(p, txt)
    teol = "\r\n" if "\r\n" in test_raw else "\n"
    w(TEST, test_raw.rstrip(teol) + TEST_APPEND.replace("\n", teol) + teol)
    print("\n--preview OK. Repo intacto." if preview_dir else "\nAplicado. Corre: py -m pytest tests/unit/test_alwayson_resume_20260911.py tests/unit/test_i18n_parity.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
