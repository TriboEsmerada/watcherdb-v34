# -*- coding: utf-8 -*-
"""LIVE legivel (2026-09-15) -- Sched com leitura, Batch/s real, PLE e Mem sem vermelho falso, Jobs com passo e progresso
reais, e ordenacao por clique em todas as colunas das tabelas do LIVE.

Pedidos do owner (15/09): capturas do LIVE em SQLHDSPRD406_I01 -- "dificil de entender isso" (Sched), "o started e o
progress parecem estar estranhos" (Jobs) e "coloque order by em todas as colunas das tabelas do live".

Medido (sql_monitoring, so leitura, SQLHDSPRD406_I01):
  - Batch/s 712.277.434 -> 712.317.130 em ~2 min: e o contador acumulado de 'Batch Requests/sec' (cntr_value), ~330/s reais.
  - PLE 2467 s a vermelho: _gc pinta vermelho quando v >= limite, mas no PLE mais baixo e pior.
  - Jobs: "(starting) (0/1)" e 0% durante 5 h -- a consulta usava last_executed_step_id (ultimo passo TERMINADO) e o
    progresso era passos/total. O backup real (TSM DP for SQL, BACKUP DATABASE MYBAGP2) estava a 42,9% em
    sys.dm_exec_requests, com estimativa de 441 min. As consultas novas foram corridas na instancia: 1,15 s e 0,04 s.

Pareceres incorporados:
  frontend-specialist: wrapper unico _liveRenderAndSet nos dois pontos de render; ordenacao generica no DOM com
    addEventListener (clique, Enter, Espaco), aria-sort e tabindex; Queries e Waits mantem o sort Wave S (th com
    aria-sort); tabelas com linhas clicaveis (Fleet) ficam de fora; PLE invertido por parametro, sem mudar os outros.
  customer-success-persona: frase de leitura no Sched; pressao de CPU so com media de pedidos a espera por scheduler
    acima de 1 em leituras seguidas (um pico isolado nao alarma); limiar por linha coerente (> 1); estimativa de fim do
    SQL Server marcada como incerta; progresso "—" explicado.

Backend (api/routers/live_monitoring.py, identidade na instancia: sql_monitoring, so SELECT): JOBS_RUNNING_SQL com o
passo em curso e o progresso do pedido do passo; PROGRESS_OPS_SQL novo (fail-open no endpoint /jobs).

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LIVE_LEGIVEL_2026-09-15_apply.py --check
  py docs/context/LIVE_LEGIVEL_2026-09-15_apply.py
  py -m pytest tests/unit/test_live_legivel_20260915.py tests/unit/test_live_f9b_20260911.py tests/unit/test_live_channels_20260911.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "live": Path("api/routers/live_monitoring.py"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_live_legivel_20260915.py"),
}
MARK = "_liveEnhanceTables"

# ---------------------------------------------------------------- backend
JOBS_SQL_SHA = "f6e6ad3b2ea40906"
JOBS_SQL_NEW = '''JOBS_RUNNING_SQL = """
SET NOCOUNT ON;
-- 2026-09-15 (owner): last_executed_step_id e o ultimo passo TERMINADO (NULL durante o 1.o passo), por isso um job de 1
-- passo aparecia "(starting) (0/1)" e 0% ate ao fim. Passo em curso = seguinte ao ultimo terminado (limitado ao total).
-- Progresso: percent_complete do pedido do passo (sessao "SQLAgent - TSQL JobStep (Job 0x... : Step N)"), quando existe.
SELECT
    j.name AS job_name,
    ja.start_execution_date,
    DATEDIFF(MINUTE, ja.start_execution_date, GETDATE()) AS running_minutes,
    st.total_steps,
    cs.current_step_id,
    js.step_name AS current_step,
    jc.name AS category_name,
    CAST(r.percent_complete AS DECIMAL(5, 1)) AS step_percent,
    r.wait_type AS step_wait_type
FROM msdb.dbo.sysjobactivity ja WITH (NOLOCK)
JOIN msdb.dbo.sysjobs j WITH (NOLOCK) ON ja.job_id = j.job_id
CROSS APPLY (SELECT COUNT(*) AS total_steps FROM msdb.dbo.sysjobsteps s2 WITH (NOLOCK) WHERE s2.job_id = j.job_id) st
CROSS APPLY (SELECT CASE WHEN ISNULL(ja.last_executed_step_id, 0) + 1 > st.total_steps THEN st.total_steps
                         ELSE ISNULL(ja.last_executed_step_id, 0) + 1 END AS current_step_id) cs
LEFT JOIN msdb.dbo.sysjobsteps js WITH (NOLOCK) ON js.job_id = j.job_id AND js.step_id = cs.current_step_id
LEFT JOIN msdb.dbo.syscategories jc WITH (NOLOCK) ON j.category_id = jc.category_id
OUTER APPLY (SELECT TOP 1 rq.percent_complete, rq.wait_type
             FROM sys.dm_exec_sessions es WITH (NOLOCK)
             JOIN sys.dm_exec_requests rq WITH (NOLOCK) ON rq.session_id = es.session_id
             WHERE es.program_name LIKE 'SQLAgent - TSQL JobStep (Job ' + CONVERT(VARCHAR(34), CONVERT(BINARY(16), j.job_id), 1) + ' : Step %') r
WHERE ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.syssessions WITH (NOLOCK))
  AND ja.start_execution_date IS NOT NULL
  AND ja.stop_execution_date IS NULL
ORDER BY ja.start_execution_date;
"""

# 2026-09-15 (owner): operacoes com progresso real na instancia (BACKUP, RESTORE, DBCC, ...). Um job que chama um programa
# externo (ex.: TSM) fica em PREEMPTIVE_OS_PIPEOPS com 0%; o progresso esta noutra sessao.
PROGRESS_OPS_SQL = """
SET NOCOUNT ON;
SELECT r.session_id, r.command, DB_NAME(r.database_id) AS database_name,
       CAST(r.percent_complete AS DECIMAL(5, 1)) AS percent_complete,
       DATEDIFF(MINUTE, r.start_time, GETDATE()) AS running_minutes,
       CAST(r.estimated_completion_time / 60000 AS INT) AS eta_minutes,
       r.wait_type, s.program_name
FROM sys.dm_exec_requests r WITH (NOLOCK)
JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON s.session_id = r.session_id
WHERE r.percent_complete > 0
ORDER BY r.start_time;
"""


'''

JOBS_ENDPOINT_OLD = '''    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "count": len(rows or []), "jobs": rows or [],
    })
'''
JOBS_ENDPOINT_NEW = '''    ops, ops_err = _query_instance(instance, PROGRESS_OPS_SQL)   # 2026-09-15: fail-open, a lista de jobs vale sozinha
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "count": len(rows or []), "jobs": rows or [],
        "operations": [] if ops_err else (ops or []),
        "operations_error": bool(ops_err),
    })
'''

# ---------------------------------------------------------------- portal
ESTADO_OLD = "        const _liveLastData = {};\n"
ESTADO_NEW = ("        const _liveLastData = {};\n"
              "        // 2026-09-15 (owner): ordenacao generica, Batch/s por diferenca e taxas do Sched (estado fora do DOM)\n"
              "        const _liveDomSort = {};\n"
              "        const _liveBatchPrev = {};\n"
              "        const _liveSchedMemo = {};\n")

GC_OLD = ("                    const _gc = (id, val, unit, warnAt, critAt) => {\n"
          "                        const el = document.getElementById(id);\n"
          "                        if (!el) return;\n"
          "                        const v = parseFloat(val) || 0;\n"
          "                        el.textContent = v.toFixed(0) + (unit || '');\n"
          "                        el.style.color = v >= (critAt||999) ? '#ef4444' : v >= (warnAt||999) ? '#f59e0b' : '#10b981';\n"
          "                    };\n")
GC_NEW = ("                    const _gc = (id, val, unit, warnAt, critAt, menorPior) => {\n"
          "                        const el = document.getElementById(id);\n"
          "                        if (!el) return;\n"
          "                        const v = parseFloat(val) || 0;\n"
          "                        el.textContent = v.toFixed(0) + (unit || '');\n"
          "                        // 2026-09-15: menorPior (PLE) -- abaixo do limite e que e mau; antes 2467 s aparecia vermelho\n"
          "                        el.style.color = menorPior\n"
          "                            ? (v <= critAt ? '#ef4444' : v <= warnAt ? '#f59e0b' : '#10b981')\n"
          "                            : (v >= (critAt||999) ? '#ef4444' : v >= (warnAt||999) ? '#f59e0b' : '#10b981');\n"
          "                    };\n")

GAUGES_OLD = ("                    _gc('lg-mem-'+tabId, gd.memory_pct, '%', 85, 95);\n"
              "                    _gc('lg-ple-'+tabId, gd.ple_seconds, 's', 600, 300);\n"
              "                    _gc('lg-batch-'+tabId, gd.batch_requests_sec, '', 999999, 999999);\n")
GAUGES_NEW = ("                    _gc('lg-mem-'+tabId, gd.memory_pct, '%', 101, 101);\n"
              "                    (function () {\n"
              "                        // 2026-09-15 (owner): num servidor SQL a memoria do SO fica alta por desenho (o SQL reserva-a). Cor pela\n"
              "                        // memoria DISPONIVEL do SO; a memoria do SQL face ao max server memory vai na dica.\n"
              "                        const el = document.getElementById('lg-mem-' + tabId);\n"
              "                        if (!el) return;\n"
              "                        const livre = +gd.available_memory_mb || 0, total = +gd.total_memory_mb || 0;\n"
              "                        const pctLivre = total > 0 ? livre / total * 100 : 100;\n"
              "                        el.style.color = (livre < 512 || pctLivre < 2) ? '#ef4444' : (livre < 1024 || pctLivre < 5) ? '#f59e0b' : '#10b981';\n"
              "                        el.title = _kpiTp('live.mem_tip_detail', 'SQL Server: {sql} MB (max server memory: {max} MB) · disponível no sistema operativo: {avail} MB',\n"
              "                            { sql: (+gd.sql_memory_mb || 0).toLocaleString(), max: (+gd.max_server_memory_mb || 0).toLocaleString(), avail: livre.toLocaleString() });\n"
              "                    })();\n"
              "                    _gc('lg-ple-'+tabId, gd.ple_seconds, 's', 600, 300, true);\n"
              "                    (function () {\n"
              "                        // 2026-09-15 (owner): 'Batch Requests/sec' e um contador acumulado; a taxa e a diferenca entre leituras\n"
              "                        const el = document.getElementById('lg-batch-' + tabId);\n"
              "                        if (!el) return;\n"
              "                        const chave = tabId + '|' + (_instAtCall || '');\n"
              "                        const antes = _liveBatchPrev[chave];\n"
              "                        const agora = { v: parseFloat(gd.batch_requests_sec) || 0, t: Date.now() };\n"
              "                        _liveBatchPrev[chave] = agora;\n"
              "                        const dt = antes ? (agora.t - antes.t) / 1000 : 0;\n"
              "                        const taxa = (antes && dt > 0 && agora.v >= antes.v) ? (agora.v - antes.v) / dt : null;\n"
              "                        el.textContent = taxa == null ? '…' : Math.round(taxa).toLocaleString();\n"
              "                        el.style.color = 'var(--color-text-bright)';\n"
              "                        el.title = taxa == null ? t('live.measuring') : '';\n"
              "                    })();\n")

RENDER1_OLD = "                    screen.innerHTML = _liveRenderProgram(_liveProgram, pd, tabId);\n"
RENDER1_NEW = "                    _liveRenderAndSet(screen, _liveProgram, pd, tabId);\n"
RENDER2_OLD = "                if (screen) screen.innerHTML = _liveRenderProgram(program, cached, tabId);\n"
RENDER2_NEW = "                if (screen) _liveRenderAndSet(screen, program, cached, tabId);\n"

SORT_JS = r"""        // 2026-09-15 (owner): "order by em todas as colunas das tabelas do live". Ordenacao generica no DOM depois de cada
        // render. Queries e Waits mantem o sort Wave S (th com aria-sort); tabelas com linhas clicaveis (Fleet) ficam de fora.
        // Estado em _liveDomSort (fora do DOM), reaplicado a cada refresh. Parecer do frontend: addEventListener, Enter/Espaco.
        function _liveRenderAndSet(screen, program, data, tabId) {
            screen.innerHTML = _liveRenderProgram(program, data, tabId);
            _liveEnhanceTables(screen, program);
        }

        function _liveSortValue(td) {
            const dv = td.getAttribute('data-sort-value');
            const raw = (dv != null ? dv : (td.textContent || '')).trim();
            if (!raw || raw === '-' || raw === '—' || raw === '…') return { n: null, s: '' };
            if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
                const tt = Date.parse(raw);
                if (!isNaN(tt)) return { n: tt, s: raw };
            }
            const m = raw.replace(/[\u00a0\u202f ]/g, '').match(/^~?(-?[\d.,]+)(%|ms|s|min|h|d|kb|mb|gb|tb)?$/i);
            if (m) {
                let num = m[1];
                if (num.indexOf(',') >= 0 && num.indexOf('.') >= 0) {
                    num = num.lastIndexOf(',') > num.lastIndexOf('.') ? num.replace(/\./g, '').replace(',', '.') : num.replace(/,/g, '');
                } else if (num.indexOf(',') >= 0) {
                    num = /,\d{3}(,|$)/.test(num) ? num.replace(/,/g, '') : num.replace(',', '.');
                } else if ((num.match(/\./g) || []).length > 1) {
                    num = num.replace(/\./g, '');
                }
                const mult = { ms: 0.001, s: 1, min: 60, h: 3600, d: 86400, kb: 1 / 1024, mb: 1, gb: 1024, tb: 1048576 }[(m[2] || '').toLowerCase()] || 1;
                const v = parseFloat(num);
                if (!isNaN(v)) return { n: v * mult, s: raw };
            }
            return { n: null, s: raw.toLowerCase() };
        }

        function _liveApplyDomSort(table, key) {
            const st = _liveDomSort[key];
            Array.from(table.tHead.rows[0].cells).forEach((th, i) => {
                const activa = !!(st && st.col === i);
                th.setAttribute('aria-sort', activa ? (st.asc ? 'ascending' : 'descending') : 'none');
                const ic = th.querySelector('.live-dom-sort-ic');
                if (ic) {
                    ic.className = 'fas ' + (activa ? (st.asc ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort') + ' live-dom-sort-ic';
                    ic.style.opacity = activa ? '1' : '0.35';
                }
            });
            if (!st || !table.tBodies[0]) return;
            const tb = table.tBodies[0];
            Array.from(tb.rows)
                .map((tr, idx) => ({ tr, idx, v: tr.cells[st.col] ? _liveSortValue(tr.cells[st.col]) : { n: null, s: '' } }))
                .sort((a, b) => {
                    const va = a.v, vb = b.v;
                    const vazioA = va.n == null && !va.s, vazioB = vb.n == null && !vb.s;
                    if (vazioA !== vazioB) return vazioA ? 1 : -1;          // vazios sempre no fim
                    let c;
                    if (va.n != null && vb.n != null) c = va.n - vb.n;
                    else if (va.n != null || vb.n != null) c = va.n != null ? -1 : 1;
                    else c = va.s.localeCompare(vb.s);
                    return (st.asc ? c : -c) || (a.idx - b.idx);
                })
                .forEach(x => tb.appendChild(x.tr));
        }

        function _liveEnhanceTables(screen, program) {
            if (!screen) return;
            screen.querySelectorAll('table').forEach((table, ti) => {
                if (!table.tHead || !table.tHead.rows[0] || !table.tBodies[0] || table.tBodies[0].rows.length < 2) return;
                if (table.querySelector('th[aria-sort]') || table.querySelector('tbody tr[onclick]')
                    || table.querySelector('tbody td[colspan], tbody td[rowspan]')) return;
                const key = program + '#' + ti;
                Array.from(table.tHead.rows[0].cells).forEach((th, i) => {
                    th.setAttribute('scope', 'col');
                    th.setAttribute('tabindex', '0');
                    th.style.cursor = 'pointer';
                    th.style.userSelect = 'none';
                    th.insertAdjacentHTML('beforeend', ' <i class="fas fa-sort live-dom-sort-ic" aria-hidden="true" style="opacity:0.35;font-size:12px;margin-left:2px;"></i>');
                    const ordenar = () => {
                        const s = _liveDomSort[key];
                        _liveDomSort[key] = { col: i, asc: s && s.col === i ? !s.asc : false };
                        _liveApplyDomSort(table, key);
                    };
                    th.addEventListener('click', ordenar);
                    th.addEventListener('keydown', ev => {
                        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ordenar(); }
                    });
                });
                _liveApplyDomSort(table, key);
            });
        }

"""

JOBS_JS_SHA = "e02d39aa50bf5c4f"
JOBS_JS_NEW = r"""        function _liveRenderJobs(data) {
            // 2026-09-15 (owner: "o started e o progress parecem estranhos"). Passo em curso (antes: ultimo passo terminado,
            // "(starting) (0/1)" ate ao fim), progresso do pedido do passo quando o SQL Server o expoe, data local, e as
            // operacoes com progresso real da instancia por baixo (um job que chama o TSM fica a 0% e o backup esta noutra sessao).
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
            const quando = iso => {
                if (!iso) return '';
                const d = new Date(iso);
                return isNaN(d.getTime()) ? esc(iso) : d.toLocaleString(document.documentElement.lang || undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
            };
            const barra = pct => `<div style="background:var(--color-bg-sunken);border-radius:4px;height:8px;width:80px;display:inline-block;vertical-align:middle;overflow:hidden;"><div style="background:#3b82f6;height:100%;width:${Math.min(100, pct)}%;"></div></div> ${pct.toFixed(1)}%`;
            const TH = 'padding:6px 8px;text-align:left;';
            const jobs = data.jobs || [];
            const ops = data.operations || [];
            let h = '';
            if (!jobs.length) {
                h += '<div style="color:var(--color-text-disabled);text-align:center;padding:40px;"><i class="fas fa-check-circle" style="font-size:32px;color:#10b981;margin-bottom:10px;display:block;"></i>' + t('live.no_running_jobs') + '</div>';
            } else {
                h += `<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:var(--color-bg-panel);color:var(--color-text-tertiary);"><th style="${TH}">Job</th><th style="${TH}">Step</th><th style="${TH}">Progress</th><th style="${TH}">Running</th><th style="${TH}">Wait</th><th style="${TH}">Category</th><th style="${TH}">Started</th></tr></thead><tbody>`;
                jobs.forEach(j => {
                    const mins = +j.running_minutes || 0;
                    const mc = mins > 120 ? '#ef4444' : mins > 30 ? '#f59e0b' : '#10b981';
                    const pct = (j.step_percent != null && +j.step_percent > 0) ? +j.step_percent : null;
                    const passo = _kpiTp('live.job_step', 'Passo {i} de {n}: {name}', { i: j.current_step_id || 1, n: j.total_steps || 1, name: j.current_step || '' });
                    const prog = pct == null ? `<span style="color:var(--color-text-disabled);" title="${esc(t('live.job_no_progress_tip'))}">—</span>` : barra(pct);
                    h += `<tr style="border-bottom:1px solid var(--color-bg-panel);"><td style="padding:5px 8px;color:var(--color-text-bright);font-weight:500;">${esc(j.job_name)}</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-tertiary);">${esc(passo)}</td>`;
                    h += `<td style="padding:5px 8px;" data-sort-value="${pct == null ? '' : pct}">${prog}</td>`;
                    h += `<td style="padding:5px 8px;color:${mc};font-weight:600;" data-sort-value="${mins}">${mins} min</td>`;
                    h += `<td style="padding:5px 8px;color:#f59e0b;font-size:12px;">${esc(j.step_wait_type || '-')}</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-disabled);font-size:12px;">${esc(j.category_name)}</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-tertiary);font-size:12px;" data-sort-value="${esc(j.start_execution_date || '')}">${quando(j.start_execution_date)}</td></tr>`;
                });
                h += '</tbody></table>';
            }
            h += `<div style="margin:18px 0 6px;color:var(--color-text-tertiary);font-weight:600;">${esc(t('live.ops_title'))}</div>`;
            if (data.operations_error) {
                h += `<div style="color:var(--color-text-disabled);font-size:12px;">${esc(t('live.ops_unavailable'))}</div>`;
            } else if (!ops.length) {
                h += `<div style="color:var(--color-text-disabled);font-size:12px;">${esc(t('live.ops_none'))}</div>`;
            } else {
                h += `<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:var(--color-bg-panel);color:var(--color-text-tertiary);"><th style="${TH}">Command</th><th style="${TH}">DB</th><th style="${TH}">Progress</th><th style="${TH}">Running</th><th style="${TH}" title="${esc(t('live.ops_eta_note'))}">ETA</th><th style="${TH}">Wait</th><th style="${TH}">Program</th><th style="${TH}">SPID</th></tr></thead><tbody>`;
                ops.forEach(o => {
                    const pct = +o.percent_complete || 0;
                    const eta = +o.eta_minutes || 0;
                    h += `<tr style="border-bottom:1px solid var(--color-bg-panel);"><td style="padding:5px 8px;color:var(--color-text-bright);font-weight:500;">${esc(o.command)}</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-tertiary);">${esc(o.database_name)}</td>`;
                    h += `<td style="padding:5px 8px;" data-sort-value="${pct}">${barra(pct)}</td>`;
                    h += `<td style="padding:5px 8px;" data-sort-value="${+o.running_minutes || 0}">${+o.running_minutes || 0} min</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-tertiary);" data-sort-value="${eta > 0 ? eta : ''}" title="${esc(t('live.ops_eta_note'))}">${eta > 0 ? '~' + eta + ' min' : '—'}</td>`;
                    h += `<td style="padding:5px 8px;color:#f59e0b;font-size:12px;">${esc(o.wait_type || '-')}</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-disabled);font-size:12px;">${esc(o.program_name)}</td>`;
                    h += `<td style="padding:5px 8px;color:var(--color-text-link);">${esc(o.session_id)}</td></tr>`;
                });
                h += '</tbody></table>';
                h += `<div style="font-size:12px;color:var(--color-text-disabled);margin-top:4px;font-style:italic;">${esc(t('live.ops_eta_note'))}</div>`;
            }
            return h;
        }

"""

SCHED_JS_SHA = "9909866740760bb6"
SCHED_JS_NEW = r"""        function _liveRenderSchedulers(data) {
            // 2026-09-15 (owner: "dificil de entender"). Frase de leitura no topo; Runnable com o mesmo limiar da frase (> 1 por
            // scheduler); Yields e Ctx Switches por segundo pela diferenca entre leituras; ajuda por coluna. Persona: pressao de
            // CPU so quando a media de pedidos a espera por scheduler passa de 1 em leituras seguidas (um pico nao alarma).
            const scheds = data.schedulers || [];
            if (!scheds.length) return '<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">' + t('live.no_scheduler_data') + '</div>';
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
            const totalRunnable = +data.total_runnable || 0;
            const totalPendingIO = +data.total_pending_io || 0;
            const porSched = totalRunnable / scheds.length;
            const inst = data.instance || '';
            let memo = _liveSchedMemo[inst];
            if (!memo || memo.ts !== data.timestamp) {
                const antes = memo || null;
                const dt = antes ? (data.timestamp - antes.ts) : 0;
                const taxas = {};
                if (antes && dt > 0) {
                    scheds.forEach(s => {
                        const p = antes.snap[s.scheduler_id];
                        if (!p) return;
                        const dy = (s.yield_count || 0) - p.y, dc = (s.context_switches_count || 0) - p.c;
                        if (dy >= 0 && dc >= 0) taxas[s.scheduler_id] = { y: dy / dt, c: dc / dt };
                    });
                }
                const snap = {};
                scheds.forEach(s => { snap[s.scheduler_id] = { y: s.yield_count || 0, c: s.context_switches_count || 0 }; });
                const hist = ((antes && dt > 0 && dt < 120) ? antes.hist : []).concat([porSched]).slice(-3);
                memo = _liveSchedMemo[inst] = { ts: data.timestamp, snap: snap, rates: taxas, hist: hist };
            }
            let k = 0;
            for (let i = memo.hist.length - 1; i >= 0 && memo.hist[i] > 1; i--) k++;     // leituras seguidas acima de 1, da mais recente
            const seguidas = k >= 2;
            const r1 = porSched.toLocaleString(undefined, { maximumFractionDigits: 1 });
            let frase, cor;
            if (seguidas) {
                frase = _kpiTp('live.sched_pressure', 'Pressão de CPU: {n} pedidos à espera de CPU ({r} por scheduler) em {k} leituras seguidas.', { n: totalRunnable, r: r1, k: k });
                cor = getSevTokens('WARNING').text;
            } else if (porSched > 1) {
                frase = _kpiTp('live.sched_spike', 'Pico de espera por CPU nesta leitura: {n} pedidos ({r} por scheduler). Ainda não é sustentado.', { n: totalRunnable, r: r1 });
                cor = 'var(--color-text-secondary)';
            } else {
                frase = _kpiTp('live.sched_ok', 'Sem pressão de CPU: {n} pedido(s) à espera de CPU em {s} schedulers.', { n: totalRunnable, s: scheds.length });
                cor = getSevTokens('OK').text;
            }
            const io = totalPendingIO > 0
                ? _kpiTp('live.sched_io_wait', '{n} pedido(s) de I/O pendente(s) nos schedulers.', { n: totalPendingIO })
                : _kpiTp('live.sched_io_ok', 'Sem espera de disco nos schedulers.', {});
            let h = `<div style="margin-bottom:12px;font-size:13px;"><div style="color:${cor};font-weight:600;">${esc(frase)}</div><div style="color:var(--color-text-tertiary);margin-top:2px;">${esc(io)}</div></div>`;
            const th = (label, dica, extra) => `<th style="padding:4px 8px;${extra || ''}"${dica ? ` title="${esc(dica)}"` : ''}>${label}</th>`;
            const R = 'text-align:right;';
            h += '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:var(--color-bg-panel);color:var(--color-text-tertiary);">'
                + th('Sched#') + th('CPU#') + th('Current Tasks', t('live.sched_tip_tasks'), R) + th('Runnable', t('live.sched_tip_runnable'), R)
                + th('Workers', t('live.sched_tip_workers'), R) + th('Active', t('live.sched_tip_workers'), R) + th('Pending I/O', t('live.sched_tip_io'), R)
                + th('Yields/s', t('live.sched_tip_rates'), R) + th('Ctx Switches/s', t('live.sched_tip_rates'), R) + '</tr></thead><tbody>';
            const taxa = v => v == null ? `<span title="${esc(t('live.measuring'))}">…</span>` : Math.round(v).toLocaleString();
            scheds.forEach(s => {
                const run = +s.runnable_tasks_count || 0;
                const rc = run > 1 ? getSevTokens('WARNING').text : 'var(--color-text-bright)';
                const tx = memo.rates[s.scheduler_id];
                h += `<tr style="border-bottom:1px solid var(--color-bg-panel);"><td style="padding:3px 8px;color:var(--color-text-link);">${esc(s.scheduler_id)}</td>`;
                h += `<td style="padding:3px 8px;">${esc(s.cpu_id)}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.current_tasks_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;color:${rc};font-weight:600;">${run}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.current_workers_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.active_workers_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.pending_disk_io_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;" data-sort-value="${tx ? tx.y : ''}">${taxa(tx ? tx.y : null)}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;" data-sort-value="${tx ? tx.c : ''}">${taxa(tx ? tx.c : null)}</td></tr>`;
            });
            h += '</tbody></table>';
            h += `<div style="font-size:12px;color:var(--color-text-disabled);margin-top:6px;font-style:italic;">${esc(t('live.sched_rates_note'))}</div>`;
            return h;
        }

"""

I18N = {
    "pt": {
        "measuring": "a medir…",
        "mem_tip_detail": "SQL Server: {sql} MB (max server memory: {max} MB) · disponível no sistema operativo: {avail} MB",
        "sched_ok": "Sem pressão de CPU: {n} pedido(s) à espera de CPU em {s} schedulers.",
        "sched_spike": "Pico de espera por CPU nesta leitura: {n} pedidos ({r} por scheduler). Ainda não é sustentado.",
        "sched_pressure": "Pressão de CPU: {n} pedidos à espera de CPU ({r} por scheduler) em {k} leituras seguidas.",
        "sched_io_ok": "Sem espera de disco nos schedulers.",
        "sched_io_wait": "{n} pedido(s) de I/O pendente(s) nos schedulers.",
        "sched_rates_note": "Yields/s e Ctx Switches/s são calculados pela diferença entre duas leituras.",
        "sched_tip_tasks": "Tarefas atribuídas a este scheduler, incluindo as que esperam por outra coisa.",
        "sched_tip_runnable": "Pedidos prontos a correr à espera de CPU neste scheduler. Acima de 1 de forma sustentada indica pressão de CPU.",
        "sched_tip_workers": "Threads associadas a este scheduler; Active são as que estão a trabalhar agora.",
        "sched_tip_io": "Pedidos de I/O à espera de conclusão neste scheduler.",
        "sched_tip_rates": "Por segundo, pela diferença entre duas leituras.",
        "job_step": "Passo {i} de {n}: {name}",
        "job_no_progress_tip": "O SQL Server não expõe progresso para este passo. Veja abaixo as operações com progresso em curso.",
        "ops_title": "Operações com progresso em curso (BACKUP, RESTORE, DBCC…)",
        "ops_none": "Nenhuma operação com progresso em curso.",
        "ops_unavailable": "Não foi possível ler as operações em curso nesta instância.",
        "ops_eta_note": "Estimativa de fim calculada pelo SQL Server: pode variar muito (por exemplo, em backups limitados pela rede ou pelo TSM).",
    },
    "en": {
        "measuring": "measuring…",
        "mem_tip_detail": "SQL Server: {sql} MB (max server memory: {max} MB) · available to the operating system: {avail} MB",
        "sched_ok": "No CPU pressure: {n} request(s) waiting for CPU across {s} schedulers.",
        "sched_spike": "CPU wait spike in this reading: {n} requests ({r} per scheduler). Not sustained yet.",
        "sched_pressure": "CPU pressure: {n} requests waiting for CPU ({r} per scheduler) for {k} consecutive readings.",
        "sched_io_ok": "No disk wait on the schedulers.",
        "sched_io_wait": "{n} pending I/O request(s) on the schedulers.",
        "sched_rates_note": "Yields/s and Ctx Switches/s are calculated from the difference between two readings.",
        "sched_tip_tasks": "Tasks assigned to this scheduler, including those waiting on something else.",
        "sched_tip_runnable": "Requests ready to run and waiting for CPU on this scheduler. Sustained above 1 indicates CPU pressure.",
        "sched_tip_workers": "Threads attached to this scheduler; Active are the ones working right now.",
        "sched_tip_io": "I/O requests waiting to complete on this scheduler.",
        "sched_tip_rates": "Per second, from the difference between two readings.",
        "job_step": "Step {i} of {n}: {name}",
        "job_no_progress_tip": "SQL Server does not expose progress for this step. See the operations in progress below.",
        "ops_title": "Operations in progress (BACKUP, RESTORE, DBCC…)",
        "ops_none": "No operations with progress running.",
        "ops_unavailable": "Could not read the operations in progress on this instance.",
        "ops_eta_note": "Completion estimate calculated by SQL Server: it can vary a lot (for example, backups throttled by the network or TSM).",
    },
    "es": {
        "measuring": "midiendo…",
        "mem_tip_detail": "SQL Server: {sql} MB (max server memory: {max} MB) · disponible en el sistema operativo: {avail} MB",
        "sched_ok": "Sin presión de CPU: {n} petición(es) esperando CPU en {s} schedulers.",
        "sched_spike": "Pico de espera de CPU en esta lectura: {n} peticiones ({r} por scheduler). Aún no es sostenido.",
        "sched_pressure": "Presión de CPU: {n} peticiones esperando CPU ({r} por scheduler) en {k} lecturas seguidas.",
        "sched_io_ok": "Sin espera de disco en los schedulers.",
        "sched_io_wait": "{n} petición(es) de E/S pendiente(s) en los schedulers.",
        "sched_rates_note": "Yields/s y Ctx Switches/s se calculan por la diferencia entre dos lecturas.",
        "sched_tip_tasks": "Tareas asignadas a este scheduler, incluidas las que esperan otra cosa.",
        "sched_tip_runnable": "Peticiones listas para ejecutar esperando CPU en este scheduler. Por encima de 1 de forma sostenida indica presión de CPU.",
        "sched_tip_workers": "Hilos asociados a este scheduler; Active son los que están trabajando ahora.",
        "sched_tip_io": "Peticiones de E/S esperando finalizar en este scheduler.",
        "sched_tip_rates": "Por segundo, por la diferencia entre dos lecturas.",
        "job_step": "Paso {i} de {n}: {name}",
        "job_no_progress_tip": "SQL Server no expone el progreso de este paso. Vea abajo las operaciones con progreso en curso.",
        "ops_title": "Operaciones con progreso en curso (BACKUP, RESTORE, DBCC…)",
        "ops_none": "Ninguna operación con progreso en curso.",
        "ops_unavailable": "No fue posible leer las operaciones en curso en esta instancia.",
        "ops_eta_note": "Estimación de fin calculada por SQL Server: puede variar mucho (por ejemplo, en backups limitados por la red o por TSM).",
    },
}
PTBR = {
    "measuring": "medindo…",
    "mem_tip_detail": "SQL Server: {sql} MB (max server memory: {max} MB) · disponível no sistema operacional: {avail} MB",
    "sched_tip_workers": "Threads associadas a este scheduler; Active são as que estão trabalhando agora.",
    "sched_tip_runnable": "Pedidos prontos para rodar esperando CPU neste scheduler. Acima de 1 de forma sustentada indica pressão de CPU.",
}
MEM_TIP = {
    "pt": ('"gauge_mem_tip": "Memória do SO. >85% = atenção, >95% = crítico",',
           '"gauge_mem_tip": "Memória em uso no sistema operativo. Num servidor SQL fica alta por desenho; a cor segue a memória disponível.",'),
    "en": ('"gauge_mem_tip": "OS memory. >85% = warning, >95% = critical",',
           '"gauge_mem_tip": "Memory in use by the operating system. On a SQL server it is high by design; the colour follows available memory.",'),
    "es": ('"gauge_mem_tip": "Memoria del SO. >85% = atención, >95% = crítico",',
           '"gauge_mem_tip": "Memoria en uso en el sistema operativo. En un servidor SQL es alta por diseño; el color sigue la memoria disponible.",'),
}


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE mais legível e com números certos** (owner 15/09). Todas as colunas das tabelas do LIVE ordenam por\n"
                  "  clique (teclado incluído) e a ordem mantém-se entre refreshes. Batch/s passa a ser a taxa real (antes mostrava o\n"
                  "  contador acumulado desde o arranque, a vermelho). PLE deixa de ficar vermelho quando está saudável e Mem só avisa\n"
                  "  quando o sistema operativo fica sem memória disponível. Sched tem uma frase de leitura (pressão de CPU só quando é\n"
                  "  sustentada) e Yields/Ctx Switches por segundo. Jobs mostra o passo em curso e o progresso real, e uma tabela nova\n"
                  "  com as operações em curso (BACKUP, RESTORE, DBCC) com percentagem e estimativa. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- LIVE legivel: ordenacao em todas as tabelas, Batch/s real, PLE e Mem, Sched com leitura, Jobs com passo e
progresso reais.
"""
import asyncio
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
LIVE = PORTAL[PORTAL.index("const _liveLastData = {};"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
JOBS_JS = PORTAL[PORTAL.index("function _liveRenderJobs(data) {"):PORTAL.index("function _liveRenderMemory(data) {")]
SCHED_JS = PORTAL[PORTAL.index("function _liveRenderSchedulers(data) {"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]


def _lm():
    from api.routers import live_monitoring as lm
    return lm


def test_consultas_de_jobs_so_leitura_e_passo_em_curso():
    lm = _lm()
    for sql in (lm.JOBS_RUNNING_SQL, lm.PROGRESS_OPS_SQL):
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|CREATE|ALTER|DROP|TRUNCATE)\b", sql)
    j = lm.JOBS_RUNNING_SQL
    assert "ISNULL(ja.last_executed_step_id, 0) + 1" in j and "'(starting)'" not in j
    assert "CONVERT(VARCHAR(34), CONVERT(BINARY(16), j.job_id), 1)" in j and "percent_complete" in j
    assert "WHERE r.percent_complete > 0" in lm.PROGRESS_OPS_SQL


def test_endpoint_jobs_operacoes_fail_open(monkeypatch):
    lm = _lm()
    chamadas = []

    def falso(instance, sql, database="master", timeout=10):
        chamadas.append(database)
        if "sysjobactivity" in sql:
            return [{"job_name": "J", "start_execution_date": None}], None
        return None, "sem permissao"

    monkeypatch.setattr(lm, "_query_instance", falso)
    r = asyncio.run(lm.get_jobs_running("X_I01"))
    corpo = json.loads(r.body)
    assert corpo["count"] == 1 and corpo["operations"] == [] and corpo["operations_error"] is True
    assert chamadas == ["msdb", "master"]


def test_ordenacao_generica_em_todas_as_tabelas():
    assert "_liveRenderAndSet(screen, _liveProgram, pd, tabId);" in LIVE
    assert "if (screen) _liveRenderAndSet(screen, program, cached, tabId);" in LIVE
    assert "screen.innerHTML = _liveRenderProgram(program, data, tabId);\n            _liveEnhanceTables(screen, program);" in LIVE
    assert LIVE.count("screen.innerHTML = _liveRenderProgram(") == 1
    assert "table.querySelector('th[aria-sort]')" in LIVE and "table.querySelector('tbody tr[onclick]')" in LIVE
    assert "th.addEventListener('click', ordenar);" in LIVE and "ev.key === 'Enter' || ev.key === ' '" in LIVE
    assert "th.setAttribute('tabindex', '0');" in LIVE and "if (vazioA !== vazioB) return vazioA ? 1 : -1;" in LIVE


def test_gauges_batch_ple_mem():
    assert "_gc('lg-batch-'" not in LIVE and "_liveBatchPrev[chave] = agora;" in LIVE
    assert "(agora.v - antes.v) / dt" in LIVE
    assert "_gc('lg-ple-'+tabId, gd.ple_seconds, 's', 600, 300, true);" in LIVE
    assert "(livre < 512 || pctLivre < 2) ? '#ef4444'" in LIVE and "live.mem_tip_detail" in LIVE


def test_jobs_e_sched_legiveis():
    assert "${j.current_step||''} (${j.current_step_id||0}" not in JOBS_JS and "current_step_id||0)/j.total_steps" not in JOBS_JS
    assert "j.step_percent" in JOBS_JS and "data.operations" in JOBS_JS and "live.ops_eta_note" in JOBS_JS
    assert "toLocaleString(document.documentElement.lang" in JOBS_JS
    assert "const seguidas = k >= 2;" in SCHED_JS and "memo.hist[i] > 1" in SCHED_JS and "'Yields/s'" in SCHED_JS and "'Ctx Switches/s'" in SCHED_JS
    assert "run > 1 ?" in SCHED_JS and "(s.runnable_tasks_count||0) > 2" not in SCHED_JS


def test_chaves_nos_tres_idiomas():
    novas = ("measuring", "mem_tip_detail", "sched_ok", "sched_spike", "sched_pressure", "sched_io_ok", "sched_io_wait",
             "sched_rates_note", "sched_tip_tasks", "sched_tip_runnable", "sched_tip_workers", "sched_tip_io",
             "sched_tip_rates", "job_step", "job_no_progress_tip", "ops_title", "ops_none", "ops_unavailable", "ops_eta_note")
    for loc in ("pt", "en", "es"):
        live = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for k in novas:
            assert live[k].strip(), (loc, k)
        assert all(x in live["job_step"] for x in ("{i}", "{n}", "{name}")), loc
        assert all(x in live["sched_pressure"] for x in ("{n}", "{r}", "{k}")), loc
        assert ">85%" not in live["gauge_mem_tip"], loc
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def _troca_bloco(text, inicio, fim, sha, novo, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    lf = text.replace("\r\n", "\n")
    if lf.count(inicio) != 1:
        raise SystemExit(f"[ABORT] {label}: inicio nao unico -- nada escrito")
    a = lf.index(inicio)
    b = lf.index(fim, a)
    velho = lf[a:b]
    got = hashlib.sha256(velho.encode("utf-8")).hexdigest()[:16]
    if got != sha:
        raise SystemExit(f"[ABORT] {label}: o bloco mudou desde a medicao (sha {got}) -- nada escrito")
    return (lf[:a] + novo + lf[b:]).replace("\n", eol)


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    live = src["live"].read_bytes().decode("utf-8")
    live = _troca_bloco(live, 'JOBS_RUNNING_SQL = """', '@router.get("/{instance}/jobs")', JOBS_SQL_SHA, JOBS_SQL_NEW, "live_monitoring")
    live = _apply(live, [(JOBS_ENDPOINT_OLD, JOBS_ENDPOINT_NEW, 1)], "live_monitoring")
    portal = _troca_bloco(portal, "        function _liveRenderJobs(data) {", "        function _liveRenderMemory(data) {",
                          JOBS_JS_SHA, JOBS_JS_NEW, "portal jobs")
    portal = _troca_bloco(portal, "        function _liveRenderSchedulers(data) {", "        // Auto-open via URL param ?autoLive=1",
                          SCHED_JS_SHA, SCHED_JS_NEW, "portal schedulers")
    portal = _apply(portal, [
        (ESTADO_OLD, ESTADO_NEW, 1), (GC_OLD, GC_NEW, 1), (GAUGES_OLD, GAUGES_NEW, 1),
        (RENDER1_OLD, RENDER1_NEW, 1), (RENDER2_OLD, RENDER2_NEW, 1),
        ("        function _liveRenderProgram(program, data, tabId) {\n", SORT_JS + "        function _liveRenderProgram(program, data, tabId) {\n", 1),
    ], "portal")
    out = {"live": live, "portal": portal}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if set(I18N[loc]) & set(json.loads(raw)["live"]):
            raise SystemExit(f"[ABORT] {loc}: chaves novas ja existem em live")
        txt = _apply(raw, [('\n  "live": {\n', '\n  "live": {\n' + _chaves(I18N[loc]), 1), (MEM_TIP[loc][0], MEM_TIP[loc][1], 1)], loc)
        json.loads(txt)
        out[loc] = txt
    raw = src["ptbr"].read_bytes().decode("utf-8")
    txt = _apply(raw, [('\n  "live": {\n', '\n  "live": {\n' + _chaves(PTBR), 1)], "pt-BR")
    json.loads(txt)
    out["ptbr"] = txt
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    compile(out["live"], str(REL["live"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] live_monitoring.py (jobs + operacoes, compila); portal: ordenacao generica, gauges, Jobs e Sched (sha conferem); "
          f"i18n {len(I18N['pt'])} chaves em pt/en/es + gauge_mem_tip, {len(PTBR)} em pt-BR; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_legivel_20260915.py tests/unit/test_live_f9b_20260911.py "
          "tests/unit/test_live_channels_20260911.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
