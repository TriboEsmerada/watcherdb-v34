# -*- coding: utf-8 -*-
"""LIVE ajuda e Sched amigavel (2026-09-15) -- "?" com a ajuda do separador activo em todo o LIVE, e o Sched em caixas.

Pedidos do owner (15/09, capturas do LIVE Sched em SQLHDSPRD406_I01): "ainda nao entendi o que e esse sched", "podd por em
todo live. se por em um tem que por nos outros ne" e "mas esse sched nao poderia ser apresentado de forma mais amigavel?".

Pareceres incorporados:
  watcherdb-frontend-specialist: UM "?" no fim da barra (nao 14), classe propria (liveSetProgram reescreve o estilo de
    todos os .live-prog-btn), painel entre os gauges e o live-screen (nao e apagado pelo refresh de 15 s), aria-expanded e
    aria-controls, role=region, max-height com scroll; Escape fecha primeiro a ajuda (antes fechava sempre o LIVE inteiro).
  ux-design-reviewer (Sched): estado em linguagem simples (CPU com folga / Fila de CPU a formar-se / CPU sob pressao, sem
    CRITICAL numa leitura pontual); grelha de caixas com o selo da fila (0 ausente, 1 neutro, >1 aviso com texto e negrito);
    SEM barra Active/Workers (active_workers_count conta tambem suspensos a espera de locks ou disco); selo "sem worker"
    (work_queue_count, ja na consulta e nunca mostrado); modo compacto acima de 48 schedulers; max-height 40vh; tabela
    tecnica em <details> recolhido (estado aberto mantido entre refreshes), com as colunas de fila primeiro; notas em
    --color-text-tertiary (o disabled nao passa 4.5:1 a 12px). Passo seguinte para I/O so com espera de disco sustentada.
  Persona (15/09, lote LIVE legivel): pressao so com media > 1 em leituras seguidas; limiar por linha > 1.

Sem mudanca de backend nem de base de dados.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LIVE_AJUDA_SCHED_2026-09-15_apply.py --check
  py docs/context/LIVE_AJUDA_SCHED_2026-09-15_apply.py
  py -m pytest tests/unit/test_live_ajuda_sched_20260915.py tests/unit/test_live_legivel_20260915.py tests/unit/test_live_waits_sort_20260915.py tests/unit/test_live_typography_tokens.py tests/unit/test_live_f9b_20260911.py -q --no-cov
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
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_live_ajuda_sched_20260915.py"),
}
MARK = "liveToggleHelp"
PROGS = ["fleet", "queries", "waits", "blocking", "plancache", "memory", "tempdb", "io", "tlog", "connections", "jobs",
         "alwayson", "schedulers", "errorlog"]

# ---------------------------------------------------------------- portal: barra, painel, Escape, liveSetProgram
BTN_OLD = """                    <button onclick="liveSetProgram('${tabId}','errorlog')" class="live-prog-btn" data-prog="errorlog" style="${_pb}">ErrLog</button>\n"""
BTN_NEW = BTN_OLD + """                    <button type="button" id="live-help-btn-${tabId}" class="live-help-btn" aria-expanded="false" aria-controls="live-help-${tabId}" onclick="liveToggleHelp('${tabId}')" title="${t('live.help_tip')}" style="${_pb};font-weight:700;">?</button>\n"""

SCREEN_OLD = """                <div id="live-screen-${tabId}" style="flex:1;overflow:auto;padding:12px;font-family:var(--font-mono);font-size:var(--font-sm);color:var(--color-text-bright);">\n"""
SCREEN_NEW = ("""                <div id="live-help-${tabId}" role="region" aria-label="${t('live.help_region')}" style="display:none;flex-shrink:0;max-height:220px;overflow-y:auto;padding:10px 14px;background:var(--color-bg-panel);border-bottom:1px solid var(--color-border);font-size:13px;line-height:1.5;color:var(--color-text-secondary);"></div>\n"""
              + SCREEN_OLD)

ESC_OLD = ("            const escHandler = (e) => {\n"
           "                if (e.key === 'Escape') {\n"
           "                    const m = document.getElementById('live-tv-modal');\n")
ESC_NEW = ("            const escHandler = (e) => {\n"
           "                if (e.key === 'Escape') {\n"
           "                    // 2026-09-15: com a ajuda aberta, Escape fecha so a ajuda (antes fechava sempre o LIVE inteiro)\n"
           "                    const ajuda = document.getElementById('live-help-' + tabId);\n"
           "                    if (ajuda && ajuda.style.display !== 'none') { liveToggleHelp(tabId, false); return; }\n"
           "                    const m = document.getElementById('live-tv-modal');\n")

SETPROG_OLD = ("            _liveWaitsPrev = null;\n            _liveWaitsMemo = null;\n"
               "            document.querySelectorAll('.live-prog-btn').forEach(b => {\n")
SETPROG_NEW = ("            _liveWaitsPrev = null;\n            _liveWaitsMemo = null;\n"
               "            _liveHelpRefresh(tabId);   // 2026-09-15: a ajuda aberta segue o separador\n"
               "            document.querySelectorAll('.live-prog-btn').forEach(b => {\n")

HELP_JS = r"""        // 2026-09-15 (owner: "se por em um tem que por nos outros"): ajuda "?" do separador activo em todo o LIVE. Um so botao
        // no fim da barra; painel fora do live-screen (o refresh de 15 s nao o apaga); segue o separador. Parecer do frontend.
        const _LIVE_HELP_PROGS = ['fleet', 'queries', 'waits', 'blocking', 'plancache', 'memory', 'tempdb', 'io', 'tlog', 'connections', 'jobs', 'alwayson', 'schedulers', 'errorlog'];
        let _liveSchedDetailsOpen = false;   // 2026-09-15: <details> do Sched aberto entre refreshes
        function _liveSchedToggle(el) { _liveSchedDetailsOpen = !!el.open; }
        function _liveHelpHtml(program, tabId) {
            const p = _LIVE_HELP_PROGS.indexOf(program) >= 0 ? program : 'queries';
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
            const linha = (k) => `<div style="margin-top:6px;"><b style="color:var(--color-text-bright);">${esc(t('live.help_label_' + k))}</b> ${esc(t('live.help_' + p + '_' + k))}</div>`;
            return `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;">`
                + `<b style="color:var(--color-text-link);font-size:14px;">${esc(t('live.help_' + p + '_title'))}</b>`
                + `<button type="button" onclick="liveToggleHelp('${tabId}', false)" aria-label="${esc(t('live.help_close'))}" title="${esc(t('live.help_close'))}" style="background:transparent;border:1px solid var(--color-border);color:var(--color-text-tertiary);border-radius:4px;cursor:pointer;font-size:12px;padding:0 8px;">✕</button></div>`
                + linha('what') + linha('how') + linha('when') + linha('next');
        }
        function liveToggleHelp(tabId, abrir) {
            const painel = document.getElementById('live-help-' + tabId);
            const btn = document.getElementById('live-help-btn-' + tabId);
            if (!painel) return;
            const aberto = painel.style.display !== 'none';
            const novo = typeof abrir === 'boolean' ? abrir : !aberto;
            if (novo) painel.innerHTML = _liveHelpHtml(_liveProgram, tabId);
            painel.style.display = novo ? 'block' : 'none';
            if (btn) {
                btn.setAttribute('aria-expanded', novo ? 'true' : 'false');
                btn.style.color = novo ? '#fff' : 'var(--color-text-tertiary)';          // inactivo: igual aos botoes da barra
                btn.style.background = novo ? 'var(--color-text-link)' : 'var(--color-bg-panel)';
                if (!novo) btn.focus();
            }
        }
        function _liveHelpRefresh(tabId) {
            const painel = document.getElementById('live-help-' + tabId);
            if (painel && painel.style.display !== 'none') painel.innerHTML = _liveHelpHtml(_liveProgram, tabId);
        }

"""

# ---------------------------------------------------------------- portal: Sched em caixas
SCHED_SHA = "a075a4d991d3c1b1"
SCHED_NEW = r"""        function _liveRenderSchedulers(data) {
            // 2026-09-15 (owner: "nao poderia ser apresentado de forma mais amigavel?"). Estado em linguagem simples, caixas
            // (uma por CPU logico) com o selo da fila, tabela tecnica recolhida. Parecer do ux-design-reviewer: sem barra
            // Active/Workers (active conta tambem suspensos), selo "sem worker" (work_queue_count), modo compacto > 48,
            // passo seguinte I/O so com espera de disco sustentada. Persona: pressao so com media > 1 em leituras seguidas.
            const scheds = data.schedulers || [];
            if (!scheds.length) return '<div style="color:var(--color-text-tertiary);text-align:center;padding:40px;">' + t('live.no_scheduler_data') + '</div>';
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
                const continua = antes && dt > 0 && dt < 120;
                const hist = (continua ? antes.hist : []).concat([porSched]).slice(-3);
                const ioHist = (continua ? (antes.ioHist || []) : []).concat([totalPendingIO]).slice(-3);
                memo = _liveSchedMemo[inst] = { ts: data.timestamp, snap: snap, rates: taxas, hist: hist, ioHist: ioHist };
            }
            let k = 0;
            for (let i = memo.hist.length - 1; i >= 0 && memo.hist[i] > 1; i--) k++;     // leituras seguidas acima de 1, da mais recente
            const seguidas = k >= 2;
            let kio = 0;
            for (let i = memo.ioHist.length - 1; i >= 0 && memo.ioHist[i] > 0; i--) kio++;
            const r1 = porSched.toLocaleString(undefined, { maximumFractionDigits: 1 });
            let estado, frase, cor;
            if (seguidas) {
                estado = t('live.sched_state_pressure'); cor = getSevTokens('WARNING').text;
                frase = _kpiTp('live.sched_pressure', 'Pressão de CPU: {n} pedidos à espera de CPU ({r} por scheduler) em {k} leituras seguidas.', { n: totalRunnable, r: r1, k: k });
            } else if (porSched > 1) {
                estado = t('live.sched_state_spike'); cor = 'var(--color-text-bright)';
                frase = _kpiTp('live.sched_spike', 'Pico de espera por CPU nesta leitura: {n} pedidos ({r} por scheduler). Ainda não é sustentado.', { n: totalRunnable, r: r1 });
            } else {
                estado = t('live.sched_state_ok'); cor = getSevTokens('OK').text;
                frase = _kpiTp('live.sched_ok', 'Sem pressão de CPU: {n} pedido(s) à espera de CPU em {s} schedulers.', { n: totalRunnable, s: scheds.length });
            }
            const io = totalPendingIO > 0
                ? _kpiTp('live.sched_io_wait', '{n} pedido(s) de I/O pendente(s) nos schedulers.', { n: totalPendingIO })
                : _kpiTp('live.sched_io_ok', 'Sem espera de disco nos schedulers.', {});
            const passos = [];
            if (seguidas) passos.push(t('live.sched_next_queries'));
            if (kio >= 2) passos.push(t('live.sched_next_io'));
            let h = `<div style="margin-bottom:12px;">`
                + `<div style="font-size:16px;font-weight:700;color:${cor};">${esc(estado)}</div>`
                + `<div style="font-size:13px;color:var(--color-text-secondary);margin-top:2px;">${esc(frase)} ${esc(io)}</div>`
                + passos.map(p => `<div style="font-size:13px;color:var(--color-text-bright);margin-top:4px;">➜ ${esc(p)}</div>`).join('')
                + `</div>`;
            // caixas: uma por scheduler, sempre por scheduler_id; compacto acima de 48
            const compacto = scheds.length > 48;
            const ordem = [...scheds].sort((a, b) => (+a.scheduler_id) - (+b.scheduler_id));
            const warn = getSevTokens('WARNING');
            h += `<div role="list" aria-label="${esc(t('live.sched_legend'))}" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(${compacto ? 36 : 76}px,1fr));gap:4px;max-height:40vh;overflow-y:auto;">`;
            ordem.forEach(s => {
                const run = +s.runnable_tasks_count || 0;
                const wq = +s.work_queue_count || 0;
                const pio = +s.pending_disk_io_count || 0;
                const act = +s.active_workers_count || 0;
                const selo = run === 0 ? ''
                    : `<span style="font-size:12px;border-radius:4px;padding:0 4px;${run > 1 ? `background:${warn.bg};color:${warn.text};font-weight:700;` : 'border:1px solid var(--color-border-strong);color:var(--color-text-bright);'}">${compacto ? run : esc(_kpiTp('live.sched_badge_queue', 'fila {n}', { n: run }))}</span>`;
                const semWorker = (wq > 0 && !compacto) ? `<span style="font-size:12px;border-radius:4px;padding:0 4px;background:${warn.bg};color:${warn.text};font-weight:700;">${esc(_kpiTp('live.sched_badge_noworker', 'sem worker {n}', { n: wq }))}</span>` : '';
                const disco = (pio > 0 && !compacto) ? `<span style="font-size:12px;color:var(--color-text-bright);"><i class="fas fa-hard-drive" aria-hidden="true"></i> ${pio}</span>` : '';
                const dica = _kpiTp('live.sched_card_tip', 'Scheduler {id} (CPU {cpu}): fila {run}, sem worker {wq}, a trabalhar {act}, I/O pendente {io}', { id: s.scheduler_id, cpu: s.cpu_id, run: run, wq: wq, act: act, io: pio });
                const destaque = (run > 1 || wq > 0) ? `border-color:${warn.text};` : '';
                h += `<div role="listitem" title="${esc(dica)}" style="border:1px solid var(--color-border);${destaque}border-radius:6px;padding:4px 6px;min-height:${compacto ? 30 : 48}px;background:var(--color-bg-sunken);display:flex;flex-direction:column;gap:2px;">`
                    + `<div style="display:flex;justify-content:space-between;align-items:center;gap:4px;flex-wrap:wrap;"><span style="font-size:12px;color:var(--color-text-tertiary);">${compacto ? '' : '#'}${esc(s.scheduler_id)}</span>${selo}</div>`
                    + (compacto ? '' : `<div style="font-size:12px;color:var(--color-text-tertiary);">${esc(_kpiTp('live.sched_working', 'a trabalhar {n}', { n: act }))}</div>`)
                    + ((semWorker || disco) ? `<div style="display:flex;gap:4px;flex-wrap:wrap;">${semWorker}${disco}</div>` : '')
                    + `</div>`;
            });
            h += '</div>';
            h += `<div style="font-size:12px;color:var(--color-text-tertiary);margin-top:6px;">${esc(t('live.sched_legend'))}</div>`;
            // detalhe tecnico recolhido; colunas de fila primeiro; ordenavel pelo enhancer generico
            const th = (label, dica, extra) => `<th style="padding:4px 8px;${extra || ''}"${dica ? ` title="${esc(dica)}"` : ''}>${label}</th>`;
            const R = 'text-align:right;';
            const taxa = v => v == null ? `<span title="${esc(t('live.measuring'))}">…</span>` : Math.round(v).toLocaleString();
            h += `<details ${_liveSchedDetailsOpen ? 'open' : ''} ontoggle="_liveSchedToggle(this)" style="margin-top:12px;"><summary style="cursor:pointer;color:var(--color-text-tertiary);font-size:13px;">${esc(t('live.sched_details'))}</summary>`;
            h += '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:8px;"><thead><tr style="background:var(--color-bg-panel);color:var(--color-text-tertiary);">'
                + th('Sched#') + th('Runnable', t('live.sched_tip_runnable'), R) + th('Work Queue', t('live.sched_tip_workqueue'), R)
                + th('Pending I/O', t('live.sched_tip_io'), R) + th('Active', t('live.sched_tip_workers'), R) + th('Workers', t('live.sched_tip_workers'), R)
                + th('Current Tasks', t('live.sched_tip_tasks'), R) + th('CPU#')
                + th('Yields/s', t('live.sched_tip_rates'), R) + th('Ctx Switches/s', t('live.sched_tip_rates'), R) + '</tr></thead><tbody>';
            ordem.forEach(s => {
                const run = +s.runnable_tasks_count || 0;
                const rc = run > 1 ? warn.text : 'var(--color-text-bright)';
                const tx = memo.rates[s.scheduler_id];
                h += `<tr style="border-bottom:1px solid var(--color-bg-panel);"><td style="padding:3px 8px;color:var(--color-text-link);">${esc(s.scheduler_id)}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;color:${rc};font-weight:600;">${run}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.work_queue_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.pending_disk_io_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.active_workers_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.current_workers_count || 0}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;">${+s.current_tasks_count || 0}</td>`;
                h += `<td style="padding:3px 8px;">${esc(s.cpu_id)}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;" data-sort-value="${tx ? tx.y : ''}">${taxa(tx ? tx.y : null)}</td>`;
                h += `<td style="padding:3px 8px;text-align:right;" data-sort-value="${tx ? tx.c : ''}">${taxa(tx ? tx.c : null)}</td></tr>`;
            });
            h += '</tbody></table>';
            h += `<div style="font-size:12px;color:var(--color-text-tertiary);margin-top:6px;font-style:italic;">${esc(t('live.sched_rates_note'))}</div></details>`;
            return h;
        }

"""

# ---------------------------------------------------------------- i18n
LABELS = {
    "pt": {"help_tip": "Ajuda deste separador", "help_region": "Ajuda do separador activo", "help_close": "Fechar ajuda",
           "help_label_what": "O que mostra:", "help_label_how": "Como ler:", "help_label_when": "Quando preocupar:", "help_label_next": "Passo seguinte:"},
    "en": {"help_tip": "Help for this tab", "help_region": "Help for the active tab", "help_close": "Close help",
           "help_label_what": "What it shows:", "help_label_how": "How to read it:", "help_label_when": "When to worry:", "help_label_next": "Next step:"},
    "es": {"help_tip": "Ayuda de esta pestaña", "help_region": "Ayuda de la pestaña activa", "help_close": "Cerrar ayuda",
           "help_label_what": "Qué muestra:", "help_label_how": "Cómo leerlo:", "help_label_when": "Cuándo preocuparse:", "help_label_next": "Siguiente paso:"},
}

HELP = {
    "pt": {
        "fleet": ("Fleet — a frota inteira",
                  "O estado das instâncias a partir dos KPIs e, em tempo real, só as instâncias com problema: queries pesadas, bloqueios, erros recentes e TempDB.",
                  "Cada bloco lista primeiro as instâncias piores. Clicar numa linha abre essa instância nos outros separadores.",
                  "Quando a mesma instância aparece em vários blocos ao mesmo tempo (bloqueios, queries longas e TempDB).",
                  "Clique na instância e abra Blocking ou Queries."),
        "queries": ("Queries — pedidos em execução agora",
                    "Os pedidos a correr neste momento: quem, em que base, há quanto tempo, quanto CPU e leituras gastaram e se estão bloqueados.",
                    "Elapsed é o tempo desde o início do pedido. Linhas a vermelho estão bloqueadas pela sessão da coluna Blocker. \"idle\" são sessões à espera de comando, não trabalho.",
                    "Pedidos a correr há vários minutos com CPU ou leituras a subir, ou muitos pedidos com o mesmo Wait.",
                    "Com Blocker, abra Blocking. Com Wait de disco (PAGEIOLATCH), abra I/O."),
        "waits": ("Waits — em que o SQL Server passa o tempo à espera",
                  "Os tipos de espera da instância: disco, CPU, locks, memória, rede, réplicas.",
                  "As colunas Delta mostram só o que aconteceu desde a leitura anterior. Os totais são acumulados desde o arranque e, sozinhos, dizem pouco.",
                  "Quando o mesmo tipo domina o Delta ms leitura após leitura (LCK_ para locks, PAGEIOLATCH para disco, SOS_SCHEDULER_YIELD para CPU).",
                  "Locks: Blocking. Disco: I/O. CPU: Sched e Queries. Memória: Memory."),
        "blocking": ("Blocking — cadeias de bloqueio agora",
                     "Que sessão (Blocked) espera por outra (Blocker), em que base, com que espera e há quantos segundos.",
                     "O Blocker é quem segura o recurso; o SQL de cada um mostra o que estão a fazer. Vazio quer dizer zero bloqueios nesta leitura e só nesta instância.",
                     "O mesmo Blocker em várias linhas, ou Wait sec a subir leitura após leitura.",
                     "Veja o login e o SQL do Blocker em Queries ou Conn. Não termine sessões sem confirmar com o responsável da aplicação."),
        "plancache": ("Plan Cache — os planos que mais gastam",
                      "Os planos de execução em cache com mais CPU acumulado, e quanto da cache é ocupado por planos usados uma só vez (ad hoc).",
                      "Total CPU ms é o acumulado desde que o plano entrou na cache; Avg CPU e Avg Reads são por execução; Recompiles altos indicam planos refeitos muitas vezes.",
                      "Uma query com Avg CPU ou Avg Reads muito acima das outras, ou planos ad hoc a encher a cache.",
                      "Leve o SQL à equipa da aplicação ou à análise de índices. Muitos ad hoc: avaliar a opção 'optimize for ad hoc workloads'."),
        "memory": ("Memory — onde está a memória do SQL Server",
                   "O buffer pool por base, os maiores consumidores internos (clerks) e as reservas de memória das queries (grants).",
                   "Granted é o que a query recebeu e Ideal o que queria; Wait ms é o tempo à espera de memória para começar.",
                   "Queries com Wait ms acima de zero, ou uma só base a ocupar quase todo o buffer pool.",
                   "Grants à espera: ver essas queries em Queries. Pressão constante: rever o max server memory com a infraestrutura."),
        "tempdb": ("TempDB — espaço e quem o usa",
                   "O espaço do tempdb por tipo (objectos de utilizador, internos, version store, livre), os ficheiros e as sessões que mais o usam agora.",
                   "Version store alto vem de transacções longas com snapshot; objectos internos vêm de ordenações e junções hash grandes.",
                   "O espaço livre a descer leitura após leitura, ou uma só sessão a ocupar grande parte.",
                   "Veja essa sessão em Queries. Version store alto: procurar a transacção aberta mais antiga."),
        "io": ("I/O — ficheiros de dados e de log",
               "Leituras, escritas e latência média de cada ficheiro de dados e de log.",
               "Os números são acumulados desde o arranque do SQL Server: a latência é uma média desse período, não do momento. As cores seguem os limiares de latência de disco configurados.",
               "Latência acima do limiar em ficheiros com muito tráfego, sobretudo escrita no log ou leitura nos dados.",
               "Confirme em Waits se há PAGEIOLATCH ou WRITELOG agora e leve o ficheiro e o disco à equipa de armazenamento."),
        "tlog": ("TLog — log de transacções por base",
                 "Tamanho, percentagem usada, VLFs e o motivo que impede o log de ser reutilizado.",
                 "Reuse Wait diz porque o log não liberta espaço: LOG_BACKUP (falta backup de log), ACTIVE_TRANSACTION (transacção aberta), AVAILABILITY_REPLICA (réplica atrasada).",
                 "Used % alto com Reuse Wait diferente de NOTHING, ou milhares de VLFs.",
                 "LOG_BACKUP: verificar o job de backup de log. Transacção aberta: Queries. Réplica: AG."),
        "connections": ("Conn — sessões ligadas",
                        "As sessões ligadas agora, por login, host e programa.",
                        "Mostra quem está ligado e de onde. Muitas sessões em repouso de uma aplicação são normais com pools de ligações.",
                        "Um login ou host com um número anormal de sessões, ou programas desconhecidos em produção.",
                        "Cruze com Queries (o que estão a correr) e confirme com a equipa da aplicação."),
        "jobs": ("Jobs — SQL Agent e operações em curso",
                 "Os jobs do SQL Agent em execução e as operações com progresso real (BACKUP, RESTORE, DBCC).",
                 "O progresso de um job só existe quando o SQL Server o expõe. Um job que chama um programa externo (por exemplo TSM) fica em \"—\" e o progresso aparece na tabela de operações.",
                 "Running muito acima do habitual para esse job, ou uma operação com a percentagem parada entre leituras.",
                 "Operação parada: ver a espera na tabela de operações e em I/O. Job longo: histórico do job no SQL Agent."),
        "alwayson": ("AG — Availability Groups",
                     "As réplicas de cada Availability Group: papel, estado de sincronização, filas de envio e de redo, e atraso.",
                     "Send Queue é log por enviar para a secundária; Redo Queue é log recebido por aplicar; Lag é o atraso em segundos.",
                     "Sync Health diferente de HEALTHY, filas a crescer leitura após leitura, ou uma base suspensa.",
                     "Base suspensa ou fila a crescer: o drill \"Acompanhar\" do Always On no portal. Rede lenta: ver Send KB/s."),
        "schedulers": ("Sched — há CPU que chegue?",
                       "Cada scheduler é uma \"caixa\" por CPU lógico: atende pedidos e forma fila quando o CPU não chega.",
                       "O selo \"fila\" conta pedidos prontos à espera de CPU, o número que importa. \"sem worker\" são tarefas à espera de uma thread, mais grave. O disco marca pedidos à espera de I/O.",
                       "Mais de 1 pedido à espera por scheduler em leituras seguidas (o estado passa a \"CPU sob pressão\"). Um pico isolado é normal.",
                       "Fila de CPU sustentada: Queries, para ver quem gasta CPU. Espera de disco sustentada: I/O."),
        "errorlog": ("ErrLog — últimas linhas do errorlog",
                     "As últimas 50 linhas do errorlog lidas agora na instância, sem filtro.",
                     "Inclui mensagens informativas. O histórico classificado fica na Intelligence e aparece no ecrã de servidor offline e no banner de diagnóstico.",
                     "Erros de severidade 17 ou superior, erros de I/O (823, 824, 825), falta de memória ou reinícios inesperados.",
                     "Erros de I/O: I/O e equipa de armazenamento. Reinício inesperado: errorlog anterior e equipa de DBA."),
    },
    "en": {
        "fleet": ("Fleet — the whole fleet",
                  "Instance status from the KPIs and, in real time, only the instances with problems: heavy queries, blocking, recent errors and TempDB.",
                  "Each block lists the worst instances first. Clicking a row opens that instance in the other tabs.",
                  "When the same instance shows up in several blocks at once (blocking, long queries and TempDB).",
                  "Click the instance and open Blocking or Queries."),
        "queries": ("Queries — requests running now",
                    "The requests running right now: who, in which database, for how long, how much CPU and reads they used and whether they are blocked.",
                    "Elapsed is the time since the request started. Red rows are blocked by the session in the Blocker column. \"idle\" are sessions waiting for a command, not work.",
                    "Requests running for several minutes with rising CPU or reads, or many requests with the same Wait.",
                    "With a Blocker, open Blocking. With a disk wait (PAGEIOLATCH), open I/O."),
        "waits": ("Waits — what SQL Server spends time waiting on",
                  "The instance wait types: disk, CPU, locks, memory, network, replicas.",
                  "The Delta columns show only what happened since the previous reading. Totals are cumulative since startup and say little on their own.",
                  "When the same type dominates Delta ms reading after reading (LCK_ for locks, PAGEIOLATCH for disk, SOS_SCHEDULER_YIELD for CPU).",
                  "Locks: Blocking. Disk: I/O. CPU: Sched and Queries. Memory: Memory."),
        "blocking": ("Blocking — blocking chains now",
                     "Which session (Blocked) waits on another (Blocker), in which database, with which wait and for how many seconds.",
                     "The Blocker holds the resource; each one's SQL shows what they are doing. Empty means zero blocking in this reading and only on this instance.",
                     "The same Blocker on several rows, or Wait sec rising reading after reading.",
                     "Check the Blocker's login and SQL in Queries or Conn. Do not kill sessions without confirming with the application owner."),
        "plancache": ("Plan Cache — the most expensive plans",
                      "Cached execution plans with the most accumulated CPU, and how much of the cache is taken by single-use (ad hoc) plans.",
                      "Total CPU ms is cumulative since the plan entered the cache; Avg CPU and Avg Reads are per execution; high Recompiles mean plans rebuilt often.",
                      "A query with Avg CPU or Avg Reads far above the others, or ad hoc plans filling the cache.",
                      "Take the SQL to the application team or index tuning. Many ad hoc plans: consider 'optimize for ad hoc workloads'."),
        "memory": ("Memory — where SQL Server memory goes",
                   "Buffer pool by database, the largest internal consumers (clerks) and query memory grants.",
                   "Granted is what the query received and Ideal what it wanted; Wait ms is time waiting for memory before starting.",
                   "Queries with Wait ms above zero, or a single database taking almost the whole buffer pool.",
                   "Waiting grants: check those queries in Queries. Constant pressure: review max server memory with infrastructure."),
        "tempdb": ("TempDB — space and who uses it",
                   "TempDB space by type (user objects, internal objects, version store, free), its files and the sessions using it most right now.",
                   "A high version store comes from long transactions with snapshot; internal objects come from large sorts and hash joins.",
                   "Free space dropping reading after reading, or a single session taking a large share.",
                   "Check that session in Queries. High version store: look for the oldest open transaction."),
        "io": ("I/O — data and log files",
               "Reads, writes and average latency of each data and log file.",
               "Numbers are cumulative since SQL Server started: latency is an average over that period, not the current moment. Colours follow the configured disk latency thresholds.",
               "Latency above the threshold on busy files, especially log writes or data reads.",
               "Check Waits for PAGEIOLATCH or WRITELOG now and take the file and disk to the storage team."),
        "tlog": ("TLog — transaction log per database",
                 "Size, percentage used, VLFs and what prevents the log from being reused.",
                 "Reuse Wait says why the log does not free space: LOG_BACKUP (missing log backup), ACTIVE_TRANSACTION (open transaction), AVAILABILITY_REPLICA (replica behind).",
                 "High Used % with Reuse Wait other than NOTHING, or thousands of VLFs.",
                 "LOG_BACKUP: check the log backup job. Open transaction: Queries. Replica: AG."),
        "connections": ("Conn — connected sessions",
                        "Sessions connected now, by login, host and program.",
                        "Shows who is connected and from where. Many idle sessions from one application are normal with connection pools.",
                        "A login or host with an unusual number of sessions, or unknown programs in production.",
                        "Cross-check with Queries (what they are running) and confirm with the application team."),
        "jobs": ("Jobs — SQL Agent and operations in progress",
                 "SQL Agent jobs running and operations with real progress (BACKUP, RESTORE, DBCC).",
                 "Job progress only exists when SQL Server exposes it. A job that calls an external program (for example TSM) shows \"—\" and the progress appears in the operations table.",
                 "Running far above the usual for that job, or an operation whose percentage stays flat between readings.",
                 "Stalled operation: check its wait in the operations table and in I/O. Long job: job history in SQL Agent."),
        "alwayson": ("AG — Availability Groups",
                     "The replicas of each Availability Group: role, synchronization state, send and redo queues, and lag.",
                     "Send Queue is log not yet sent to the secondary; Redo Queue is log received but not applied; Lag is the delay in seconds.",
                     "Sync Health other than HEALTHY, queues growing reading after reading, or a suspended database.",
                     "Suspended database or growing queue: the Always On \"Follow\" drill in the portal. Slow network: check Send KB/s."),
        "schedulers": ("Sched — is there enough CPU?",
                       "Each scheduler is a \"checkout\" per logical CPU: it serves requests and builds a queue when CPU is short.",
                       "The \"queue\" badge counts requests ready and waiting for CPU, the number that matters. \"no worker\" are tasks waiting for a thread, more serious. The disk marks requests waiting on I/O.",
                       "More than 1 request waiting per scheduler over consecutive readings (the state becomes \"CPU under pressure\"). An isolated spike is normal.",
                       "Sustained CPU queue: Queries, to see who uses CPU. Sustained disk wait: I/O."),
        "errorlog": ("ErrLog — latest error log lines",
                     "The last 50 error log lines read now from the instance, unfiltered.",
                     "Includes informational messages. The classified history is kept in Intelligence and appears on the server offline screen and the diagnostic banner.",
                     "Errors of severity 17 or higher, I/O errors (823, 824, 825), out-of-memory or unexpected restarts.",
                     "I/O errors: I/O and the storage team. Unexpected restart: previous error log and the DBA team."),
    },
    "es": {
        "fleet": ("Fleet — toda la flota",
                  "El estado de las instancias a partir de los KPIs y, en tiempo real, solo las instancias con problemas: consultas pesadas, bloqueos, errores recientes y TempDB.",
                  "Cada bloque muestra primero las peores instancias. Hacer clic en una fila abre esa instancia en las demás pestañas.",
                  "Cuando la misma instancia aparece en varios bloques a la vez (bloqueos, consultas largas y TempDB).",
                  "Haga clic en la instancia y abra Blocking o Queries."),
        "queries": ("Queries — peticiones en ejecución ahora",
                    "Las peticiones que se ejecutan en este momento: quién, en qué base, desde hace cuánto, cuánta CPU y lecturas usaron y si están bloqueadas.",
                    "Elapsed es el tiempo desde el inicio de la petición. Las filas en rojo están bloqueadas por la sesión de la columna Blocker. \"idle\" son sesiones esperando un comando, no trabajo.",
                    "Peticiones que llevan varios minutos con CPU o lecturas en aumento, o muchas peticiones con el mismo Wait.",
                    "Con Blocker, abra Blocking. Con espera de disco (PAGEIOLATCH), abra I/O."),
        "waits": ("Waits — en qué espera SQL Server",
                  "Los tipos de espera de la instancia: disco, CPU, bloqueos, memoria, red, réplicas.",
                  "Las columnas Delta muestran solo lo ocurrido desde la lectura anterior. Los totales se acumulan desde el arranque y por sí solos dicen poco.",
                  "Cuando el mismo tipo domina el Delta ms lectura tras lectura (LCK_ para bloqueos, PAGEIOLATCH para disco, SOS_SCHEDULER_YIELD para CPU).",
                  "Bloqueos: Blocking. Disco: I/O. CPU: Sched y Queries. Memoria: Memory."),
        "blocking": ("Blocking — cadenas de bloqueo ahora",
                     "Qué sesión (Blocked) espera a otra (Blocker), en qué base, con qué espera y desde hace cuántos segundos.",
                     "El Blocker retiene el recurso; el SQL de cada uno muestra lo que están haciendo. Vacío significa cero bloqueos en esta lectura y solo en esta instancia.",
                     "El mismo Blocker en varias filas, o Wait sec subiendo lectura tras lectura.",
                     "Revise el login y el SQL del Blocker en Queries o Conn. No termine sesiones sin confirmar con el responsable de la aplicación."),
        "plancache": ("Plan Cache — los planes más costosos",
                      "Los planes de ejecución en caché con más CPU acumulada, y cuánto de la caché ocupan planes de un solo uso (ad hoc).",
                      "Total CPU ms es el acumulado desde que el plan entró en la caché; Avg CPU y Avg Reads son por ejecución; muchos Recompiles indican planes rehechos a menudo.",
                      "Una consulta con Avg CPU o Avg Reads muy por encima de las demás, o planes ad hoc llenando la caché.",
                      "Lleve el SQL al equipo de la aplicación o al análisis de índices. Muchos ad hoc: evaluar 'optimize for ad hoc workloads'."),
        "memory": ("Memory — dónde está la memoria de SQL Server",
                   "El buffer pool por base, los mayores consumidores internos (clerks) y las reservas de memoria de las consultas (grants).",
                   "Granted es lo que recibió la consulta e Ideal lo que quería; Wait ms es el tiempo esperando memoria para empezar.",
                   "Consultas con Wait ms mayor que cero, o una sola base ocupando casi todo el buffer pool.",
                   "Grants en espera: ver esas consultas en Queries. Presión constante: revisar max server memory con infraestructura."),
        "tempdb": ("TempDB — espacio y quién lo usa",
                   "El espacio de tempdb por tipo (objetos de usuario, internos, version store, libre), sus ficheros y las sesiones que más lo usan ahora.",
                   "Un version store alto viene de transacciones largas con snapshot; los objetos internos, de ordenaciones y joins hash grandes.",
                   "El espacio libre bajando lectura tras lectura, o una sola sesión ocupando gran parte.",
                   "Revise esa sesión en Queries. Version store alto: buscar la transacción abierta más antigua."),
        "io": ("I/O — ficheros de datos y de log",
               "Lecturas, escrituras y latencia media de cada fichero de datos y de log.",
               "Los números se acumulan desde el arranque de SQL Server: la latencia es una media de ese periodo, no del momento. Los colores siguen los umbrales de latencia de disco configurados.",
               "Latencia por encima del umbral en ficheros con mucho tráfico, sobre todo escritura en el log o lectura en los datos.",
               "Confirme en Waits si hay PAGEIOLATCH o WRITELOG ahora y lleve el fichero y el disco al equipo de almacenamiento."),
        "tlog": ("TLog — log de transacciones por base",
                 "Tamaño, porcentaje usado, VLFs y el motivo que impide reutilizar el log.",
                 "Reuse Wait indica por qué el log no libera espacio: LOG_BACKUP (falta backup de log), ACTIVE_TRANSACTION (transacción abierta), AVAILABILITY_REPLICA (réplica retrasada).",
                 "Used % alto con Reuse Wait distinto de NOTHING, o miles de VLFs.",
                 "LOG_BACKUP: revisar el job de backup de log. Transacción abierta: Queries. Réplica: AG."),
        "connections": ("Conn — sesiones conectadas",
                        "Las sesiones conectadas ahora, por login, host y programa.",
                        "Muestra quién está conectado y desde dónde. Muchas sesiones inactivas de una aplicación son normales con pools de conexiones.",
                        "Un login o host con un número anormal de sesiones, o programas desconocidos en producción.",
                        "Crúcelo con Queries (lo que ejecutan) y confirme con el equipo de la aplicación."),
        "jobs": ("Jobs — SQL Agent y operaciones en curso",
                 "Los jobs de SQL Agent en ejecución y las operaciones con progreso real (BACKUP, RESTORE, DBCC).",
                 "El progreso de un job solo existe cuando SQL Server lo expone. Un job que llama a un programa externo (por ejemplo TSM) queda en \"—\" y el progreso aparece en la tabla de operaciones.",
                 "Running muy por encima de lo habitual para ese job, o una operación con el porcentaje parado entre lecturas.",
                 "Operación parada: ver la espera en la tabla de operaciones y en I/O. Job largo: historial del job en SQL Agent."),
        "alwayson": ("AG — Availability Groups",
                     "Las réplicas de cada Availability Group: rol, estado de sincronización, colas de envío y de redo, y retraso.",
                     "Send Queue es log pendiente de enviar a la secundaria; Redo Queue es log recibido sin aplicar; Lag es el retraso en segundos.",
                     "Sync Health distinto de HEALTHY, colas creciendo lectura tras lectura, o una base suspendida.",
                     "Base suspendida o cola creciendo: el drill \"Seguir\" de Always On en el portal. Red lenta: ver Send KB/s."),
        "schedulers": ("Sched — ¿hay CPU suficiente?",
                       "Cada scheduler es una \"caja\" por CPU lógica: atiende peticiones y forma cola cuando la CPU no alcanza.",
                       "El sello \"cola\" cuenta peticiones listas esperando CPU, el número que importa. \"sin worker\" son tareas esperando un hilo, más grave. El disco marca peticiones esperando E/S.",
                       "Más de 1 petición esperando por scheduler en lecturas seguidas (el estado pasa a \"CPU bajo presión\"). Un pico aislado es normal.",
                       "Cola de CPU sostenida: Queries, para ver quién usa CPU. Espera de disco sostenida: I/O."),
        "errorlog": ("ErrLog — últimas líneas del errorlog",
                     "Las últimas 50 líneas del errorlog leídas ahora en la instancia, sin filtro.",
                     "Incluye mensajes informativos. El historial clasificado se guarda en Intelligence y aparece en la pantalla de servidor offline y en el banner de diagnóstico.",
                     "Errores de severidad 17 o superior, errores de E/S (823, 824, 825), falta de memoria o reinicios inesperados.",
                     "Errores de E/S: I/O y equipo de almacenamiento. Reinicio inesperado: errorlog anterior y equipo de DBA."),
    },
}

SCHED_KEYS = {
    "pt": {"sched_state_ok": "CPU com folga", "sched_state_spike": "Fila de CPU a formar-se", "sched_state_pressure": "CPU sob pressão",
           "sched_next_queries": "Próximo passo: abra Queries para ver quem está a consumir CPU.",
           "sched_next_io": "Próximo passo: abra I/O — há pedidos à espera do disco em leituras seguidas.",
           "sched_legend": "Cada caixa é um CPU lógico (scheduler). \"fila\" conta pedidos prontos à espera de CPU; \"sem worker\" são tarefas à espera de uma thread; o disco marca pedidos à espera de I/O.",
           "sched_details": "Ver detalhe técnico", "sched_badge_queue": "fila {n}", "sched_badge_noworker": "sem worker {n}", "sched_working": "a trabalhar {n}",
           "sched_card_tip": "Scheduler {id} (CPU {cpu}): fila {run}, sem worker {wq}, a trabalhar {act}, I/O pendente {io}",
           "sched_tip_workqueue": "Tarefas à espera de uma thread de trabalho. Acima de 0 é mais grave do que a fila de CPU."},
    "en": {"sched_state_ok": "CPU has headroom", "sched_state_spike": "CPU queue building up", "sched_state_pressure": "CPU under pressure",
           "sched_next_queries": "Next step: open Queries to see who is using CPU.",
           "sched_next_io": "Next step: open I/O — requests have been waiting on disk for consecutive readings.",
           "sched_legend": "Each box is a logical CPU (scheduler). \"queue\" counts requests ready and waiting for CPU; \"no worker\" are tasks waiting for a thread; the disk marks requests waiting on I/O.",
           "sched_details": "Show technical detail", "sched_badge_queue": "queue {n}", "sched_badge_noworker": "no worker {n}", "sched_working": "working {n}",
           "sched_card_tip": "Scheduler {id} (CPU {cpu}): queue {run}, no worker {wq}, working {act}, pending I/O {io}",
           "sched_tip_workqueue": "Tasks waiting for a worker thread. Above 0 is more serious than the CPU queue."},
    "es": {"sched_state_ok": "CPU con holgura", "sched_state_spike": "Cola de CPU formándose", "sched_state_pressure": "CPU bajo presión",
           "sched_next_queries": "Siguiente paso: abra Queries para ver quién consume CPU.",
           "sched_next_io": "Siguiente paso: abra I/O — hay peticiones esperando el disco en lecturas seguidas.",
           "sched_legend": "Cada caja es una CPU lógica (scheduler). \"cola\" cuenta peticiones listas esperando CPU; \"sin worker\" son tareas esperando un hilo; el disco marca peticiones esperando E/S.",
           "sched_details": "Ver detalle técnico", "sched_badge_queue": "cola {n}", "sched_badge_noworker": "sin worker {n}", "sched_working": "trabajando {n}",
           "sched_card_tip": "Scheduler {id} (CPU {cpu}): cola {run}, sin worker {wq}, trabajando {act}, E/S pendiente {io}",
           "sched_tip_workqueue": "Tareas esperando un hilo de trabajo. Por encima de 0 es más grave que la cola de CPU."},
}

PTBR = {
    "help_region": "Ajuda da aba ativa", "help_tip": "Ajuda desta aba",
    "help_connections_title": "Conn — sessões conectadas",
    "help_connections_what": "As sessões conectadas agora, por login, host e programa.",
    "help_connections_how": "Mostra quem está conectado e de onde. Muitas sessões ociosas de uma aplicação são normais com pools de conexões.",
    "help_io_title": "I/O — arquivos de dados e de log",
    "help_io_what": "Leituras, gravações e latência média de cada arquivo de dados e de log.",
    "help_io_next": "Confirme em Waits se há PAGEIOLATCH ou WRITELOG agora e leve o arquivo e o disco à equipe de armazenamento.",
    "help_tempdb_what": "O espaço do tempdb por tipo (objetos de usuário, internos, version store, livre), os arquivos e as sessões que mais o usam agora.",
    "help_errorlog_how": "Inclui mensagens informativas. O histórico classificado fica na Intelligence e aparece na tela de servidor offline e no banner de diagnóstico.",
    "help_fleet_what": "O estado das instâncias a partir dos KPIs e, em tempo real, só as instâncias com problema: queries pesadas, bloqueios, erros recentes e TempDB.",
    "sched_state_spike": "Fila de CPU se formando",
}


def _i18n_bloco(loc):
    d = dict(LABELS[loc])
    for prog in PROGS:
        titulo, what, how, when, nxt = HELP[loc][prog]
        d[f"help_{prog}_title"], d[f"help_{prog}_what"], d[f"help_{prog}_how"] = titulo, what, how
        d[f"help_{prog}_when"], d[f"help_{prog}_next"] = when, nxt
    d.update(SCHED_KEYS[loc])
    return d


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE com ajuda em todos os separadores e Sched em linguagem simples** (owner 15/09). Um botão \"?\" no fim\n"
                  "  da barra abre a ajuda do separador activo (o que mostra, como ler, quando preocupar, passo seguinte) e segue\n"
                  "  a troca de separador; Escape fecha primeiro a ajuda. O Sched passa a mostrar o estado (CPU com folga, fila a\n"
                  "  formar-se, CPU sob pressão), uma caixa por CPU com o selo da fila e \"sem worker\", o passo seguinte, e a tabela\n"
                  "  técnica recolhida. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- LIVE: ajuda "?" do separador activo em todo o LIVE e Sched em caixas.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
SHELL = PORTAL[PORTAL.index("function openLiveMonitoringModal()"):PORTAL.index("function _liveLoadChannels")]
SCHED = PORTAL[PORTAL.index("function _liveRenderSchedulers(data) {"):PORTAL.index("// Auto-open via URL param ?autoLive=1")]
PROGS = ["fleet", "queries", "waits", "blocking", "plancache", "memory", "tempdb", "io", "tlog", "connections", "jobs",
         "alwayson", "schedulers", "errorlog"]


def test_um_botao_de_ajuda_acessivel_e_painel_fora_do_ecra():
    assert SHELL.count('class="live-help-btn"') == 1 and 'class="live-prog-btn" data-prog="help"' not in SHELL
    assert 'aria-expanded="false" aria-controls="live-help-${tabId}"' in SHELL
    assert SHELL.index('id="live-help-${tabId}" role="region"') < SHELL.index('id="live-screen-${tabId}"')
    assert "max-height:220px;overflow-y:auto;" in SHELL


def test_escape_fecha_primeiro_a_ajuda_e_ajuda_segue_o_separador():
    esc = SHELL[SHELL.index("const escHandler = (e) => {"):]
    assert esc.index("liveToggleHelp(tabId, false); return;") < esc.index("m.remove()")
    setp = PORTAL[PORTAL.index("function liveSetProgram(tabId, program) {"):]
    assert setp.index("_liveHelpRefresh(tabId);") < setp.index("document.querySelectorAll('.live-prog-btn')")
    assert "const _LIVE_HELP_PROGS = ['" + "', '".join(PROGS) + "'];" in PORTAL


def test_sched_em_caixas_sem_barra_active_workers():
    assert "repeat(auto-fill,minmax(${compacto ? 36 : 76}px,1fr))" in SCHED and "const compacto = scheds.length > 48;" in SCHED
    assert "work_queue_count" in SCHED and "live.sched_badge_noworker" in SCHED
    assert "<details ${_liveSchedDetailsOpen ? 'open' : ''} ontoggle=\"_liveSchedToggle(this)\"" in SCHED
    assert "active_workers_count / " not in SCHED and "--color-text-disabled" not in SCHED
    assert "if (kio >= 2) passos.push(t('live.sched_next_io'));" in SCHED
    assert "CRITICAL" not in SCHED


def test_chaves_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        live = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for p in PROGS:
            for k in ("title", "what", "how", "when", "next"):
                assert live[f"help_{p}_{k}"].strip(), (loc, p, k)
        for k in ("help_tip", "help_region", "help_close", "help_label_what", "help_label_how", "help_label_when",
                  "help_label_next", "sched_state_ok", "sched_state_spike", "sched_state_pressure", "sched_next_queries",
                  "sched_next_io", "sched_legend", "sched_details", "sched_working", "sched_tip_workqueue"):
            assert live[k].strip(), (loc, k)
        for k in ("sched_badge_queue", "sched_badge_noworker", "sched_working"):
            assert "{n}" in live[k], (loc, k)
        assert all(x in live["sched_card_tip"] for x in ("{id}", "{cpu}", "{run}", "{wq}", "{act}", "{io}")), loc
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
    got = hashlib.sha256(lf[a:b].encode("utf-8")).hexdigest()[:16]
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
    portal = _troca_bloco(portal, "        function _liveRenderSchedulers(data) {", "        // Auto-open via URL param ?autoLive=1",
                          SCHED_SHA, SCHED_NEW, "portal schedulers")
    portal = _apply(portal, [
        (BTN_OLD, BTN_NEW, 1), (SCREEN_OLD, SCREEN_NEW, 1), (ESC_OLD, ESC_NEW, 1), (SETPROG_OLD, SETPROG_NEW, 1),
        ("        function liveSetProgram(tabId, program) {\n", HELP_JS + "        function liveSetProgram(tabId, program) {\n", 1),
    ], "portal")
    out = {"portal": portal}
    total = 0
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        novas = _i18n_bloco(loc)
        if set(novas) & set(json.loads(raw)["live"]):
            raise SystemExit(f"[ABORT] {loc}: chaves novas ja existem em live")
        txt = _apply(raw, [('\n  "live": {\n', '\n  "live": {\n' + _chaves(novas), 1)], loc)
        json.loads(txt)
        out[loc] = txt
        total = len(novas)
    raw = src["ptbr"].read_bytes().decode("utf-8")
    if not set(PTBR) <= set(_i18n_bloco("pt")):
        raise SystemExit("[ABORT] pt-BR: chave sem par em pt")
    txt = _apply(raw, [('\n  "live": {\n', '\n  "live": {\n' + _chaves(PTBR), 1)], "pt-BR")
    json.loads(txt)
    out["ptbr"] = txt
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal: botao e painel de ajuda, Escape, liveSetProgram, Sched em caixas (sha confere); i18n {total} chaves em "
          f"pt/en/es, {len(PTBR)} em pt-BR; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_ajuda_sched_20260915.py tests/unit/test_live_legivel_20260915.py "
          "tests/unit/test_live_waits_sort_20260915.py tests/unit/test_live_typography_tokens.py tests/unit/test_live_f9b_20260911.py -q --no-cov ; "
          "py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
