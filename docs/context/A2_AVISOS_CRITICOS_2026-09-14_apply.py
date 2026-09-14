# -*- coding: utf-8 -*-
"""A2 (2026-09-14) -- disciplina dos avisos criticos + sino com historico. So portal.

Pedido do owner: "sempre que um KPI critico novo ocorrer, um aviso no ecra". O mecanismo ja
existia (7 checks em TOAST_CRITICAL_CHECKS) mas tinha tres defeitos, confirmados no codigo e pelo
watcherdb-frontend-specialist (consenso nos tres, com refinamentos incorporados):

  D1 A primeira leitura era silenciosa por construcao (_toastBaselineDone): quem abria o portal
     com condicoes criticas ja activas nunca via aviso nenhum.
  D2 Deduplicacao por VALOR (key_value, 5 min) e disparo so' em subida face a leitura anterior:
     um valor a oscilar 3->4->3->4 disparava a cada subida.
  D3 No ecra de KPIs o aviso fazia `return` sem registo: um critico surgido ali desaparecia.
  Extra: o debugLog dizia "polling 60s" com o intervalo real a 30 s.

O que muda:
  P1 Primeira leitura grava CADA condicao no historico e mostra UM aviso consolidado que abre o
     sino (em vez de 7 avisos de uma vez; o proprio codigo ja limita a 5 visiveis).
  P2 Estado por condicao em _toastLastFired, SEPARADO de _toastPreviousState (que continua a
     alimentar o texto "3 -> 4"). Dispara se agravou face ao ultimo valor que ja disparou; limpa
     SEMPRE que volta a 0, fora do ramo de disparo.
  P3 Suprimido no ecra de KPIs: grava no historico ja MARCADO COMO LIDO (o ecra e' o aviso; nao
     incrementa o badge com o mesmo evento que o DBA esta a ver).
  P4 Sino no header-user-group, antes do selector de idioma. Badge de nao lidos; painel com hora,
     titulo, valor e detalhe; clicar abre a mesma modal que o aviso. Teclado ao padrao do selector
     de idioma (c15493a): setas, Home/End, Escape devolve o foco. NAO copia o menu de perfil, que
     nao trata Escape. aria-live proprio, separado do #toastContainer.
  Sem lembrete por toast: o badge PULSA quando o nao-lido mais antigo passa de 30 min.
  Achado do especialista: dados stale em 10 leituras seguidas (~5 min) gravam "monitorizacao de
  criticos parada", em vez de o sino ficar vazio sem sinal.

Historico em localStorage por viewer (conveniencia de UI, nao auditoria), tecto 50, try/catch.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/A2_AVISOS_CRITICOS_2026-09-14_apply.py --check
  py docs/context/A2_AVISOS_CRITICOS_2026-09-14_apply.py
  py -m pytest tests/unit/test_a2_avisos_criticos_20260914.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_a2_avisos_criticos_20260914.py"),
}
MARK = "_toastLastFired"

CSS = """        /* A2 2026-09-14: sino de avisos criticos (historico por viewer) */
        .crit-bell { position: relative; }
        .crit-bell-btn { position: relative; background: transparent; border: 1px solid var(--color-border); color: var(--color-text-tertiary); border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 14px; line-height: 1; }
        .crit-bell-btn:hover { color: var(--color-text-bright); border-color: #ef4444; }
        .crit-bell-btn:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
        .crit-bell-badge { position: absolute; top: -6px; right: -6px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: #ef4444; color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; font-variant-numeric: tabular-nums; }
        .crit-bell-badge[hidden] { display: none; }
        .crit-bell-btn.crit-bell-stale .crit-bell-badge { animation: critBellPulse 1.6s ease-in-out infinite; }
        @keyframes critBellPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); } 50% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); } }
        @media (prefers-reduced-motion: reduce) { .crit-bell-btn.crit-bell-stale .crit-bell-badge { animation: none; outline: 2px solid #f59e0b; } }
        .crit-bell-panel { position: absolute; top: calc(100% + 8px); right: 0; width: 380px; max-width: calc(100vw - 24px); max-height: 60vh; overflow-y: auto; background: var(--color-bg-panel); border: 1px solid var(--color-border); border-radius: 8px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35); z-index: 99998; }
        .crit-bell-panel[hidden] { display: none; }
        .crit-bell-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid var(--color-border); font-size: 12px; font-weight: 700; color: var(--color-text-bright); }
        .crit-bell-clear { background: none; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-tertiary); font-size: 11px; padding: 2px 8px; cursor: pointer; }
        .crit-bell-clear:focus-visible { outline: 2px solid #3b82f6; outline-offset: 1px; }
        .crit-bell-item { display: block; width: 100%; text-align: left; background: none; border: none; border-bottom: 1px solid var(--color-bg-sunken); border-left: 3px solid transparent; padding: 9px 12px; cursor: pointer; color: var(--color-text-bright); font-size: 12px; }
        .crit-bell-item:hover, .crit-bell-item:focus-visible { background: var(--color-bg-sunken); outline: none; }
        .crit-bell-item.unread { border-left-color: #ef4444; }
        .crit-bell-meta { display: flex; justify-content: space-between; gap: 8px; color: var(--color-text-disabled); font-size: 11px; margin-top: 3px; }
        .crit-bell-empty { padding: 18px 12px; text-align: center; color: var(--color-text-disabled); font-size: 12px; }
        .crit-bell-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

"""

HTML = """                <!-- A2 2026-09-14: sino de avisos criticos (antes do idioma: ordem sino, idioma, perfil) -->
                <div id="criticalAlertsBell" class="crit-bell">
                    <button type="button" id="critBellBtn" class="crit-bell-btn" aria-haspopup="true" aria-expanded="false" aria-controls="critBellPanel" aria-label="Avisos criticos" onclick="critBellToggle()">
                        <i class="fas fa-bell" aria-hidden="true"></i>
                        <span id="critBellBadge" class="crit-bell-badge" hidden>0</span>
                    </button>
                    <span id="critBellLive" class="crit-bell-sr" aria-live="polite"></span>
                    <div id="critBellPanel" class="crit-bell-panel" role="menu" hidden></div>
                </div>
"""

LOOP_VELHO = (
    "                TOAST_CRITICAL_CHECKS.forEach(check => {\n"
    "                    const currentValue = check.getValue(data);\n"
    "                    const previousValue = _toastPreviousState[check.key] || 0;\n"
    "\n"
    "                    // So notificar a partir do segundo poll (primeiro = baseline)\n"
    "                    if (_toastBaselineDone && currentValue > 0 && currentValue > previousValue) {\n"
    "                        const toastKey = `${check.key}_${currentValue}`;\n"
    "                        if (!_toastShownKeys.has(toastKey)) {\n"
    "                            const detail = check.getDetail(data);\n"
    "                            showCriticalToast(check, currentValue, previousValue, detail);\n"
    "                            _toastShownKeys.add(toastKey);\n"
    "                            setTimeout(() => _toastShownKeys.delete(toastKey), 300000);\n"
    "                        }\n"
    "                    }\n"
    "\n"
    "                    _toastPreviousState[check.key] = currentValue;\n"
    "                });\n"
    "\n"
    "                if (!_toastBaselineDone) {\n"
    "                    _toastBaselineDone = true;\n"
    "                    debugLog('[TOAST] Baseline capturado: ' + JSON.stringify(_toastPreviousState), 'info');\n"
    "                }\n"
)
LOOP_NOVO = (
    "                _toastStaleStreak = 0;\n"
    "                const _activosNoArranque = [];\n"
    "                TOAST_CRITICAL_CHECKS.forEach(check => {\n"
    "                    const currentValue = check.getValue(data);\n"
    "                    const previousValue = _toastPreviousState[check.key] || 0;\n"
    "\n"
    "                    // A2 2026-09-14: estado por CONDICAO. Limpa SEMPRE que volta a 0 (fora do ramo de\n"
    "                    // disparo), para a proxima subida disparar. So' dispara se agravou face ao ultimo\n"
    "                    // valor que JA disparou: 3->4->3->4 dispara uma vez, nao a cada subida.\n"
    "                    if (currentValue === 0) {\n"
    "                        delete _toastLastFired[check.key];\n"
    "                    } else if (currentValue > (_toastLastFired[check.key] || 0)) {\n"
    "                        const detail = check.getDetail(data);\n"
    "                        if (_toastBaselineDone) {\n"
    "                            showCriticalToast(check, currentValue, previousValue, detail);\n"
    "                        } else {\n"
    "                            // primeira leitura: grava cada condicao, mas nao dispara um aviso por cada\n"
    "                            critBellRecord(check, currentValue, previousValue, detail, {});\n"
    "                            _activosNoArranque.push(check);\n"
    "                        }\n"
    "                        _toastLastFired[check.key] = currentValue;\n"
    "                    }\n"
    "\n"
    "                    _toastPreviousState[check.key] = currentValue;\n"
    "                });\n"
    "\n"
    "                if (!_toastBaselineDone) {\n"
    "                    _toastBaselineDone = true;\n"
    "                    // A2 2026-09-14: a primeira leitura deixou de ser silenciosa. Quem abre o portal com\n"
    "                    // condicoes criticas ja activas ve UM aviso consolidado que abre o sino.\n"
    "                    if (_activosNoArranque.length) showCriticalSummaryToast(_activosNoArranque);\n"
    "                    debugLog('[TOAST] Baseline capturado: ' + JSON.stringify(_toastPreviousState), 'info');\n"
    "                }\n"
)

BELL_JS = r"""
        // ========================================
        // A2 2026-09-14: SINO DE AVISOS CRITICOS
        // Historico por viewer em localStorage: conveniencia de UI, NAO trilho de auditoria (os valores
        // de KPI continuam a ser verdade do backend). Tecto 50, try/catch em toda a leitura e escrita.
        // Teclado ao padrao do selector de idioma (c15493a): setas, Home/End, Escape devolve o foco.
        // ========================================
        function _bellEsc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
        }
        function critBellLoad() {
            try {
                const v = JSON.parse(localStorage.getItem(CRIT_BELL_KEY) || '[]');
                return Array.isArray(v) ? v : [];
            } catch (e) { return []; }
        }
        function critBellSave(items) {
            try { localStorage.setItem(CRIT_BELL_KEY, JSON.stringify(items.slice(0, CRIT_BELL_MAX))); } catch (e) { /* modo privado ou quota */ }
        }
        function critBellRecord(check, value, prevValue, detail, opts) {
            const o = opts || {};
            const items = critBellLoad();
            items.unshift({
                ts: Date.now(), key: check.key, kpiType: check.kpiType || '', modalTitle: check.modalTitle || '',
                value: value, prev: prevValue || 0, detail: detail || '',
                suppressed: !!o.suppressed,
                // suprimido no ecra de KPIs entra ja lido: o DBA esta a olhar para o proprio cartao
                read: !!o.suppressed
            });
            critBellSave(items);
            critBellRender();
        }
        function critBellRecordMonitoringDown() {
            const items = critBellLoad();
            items.unshift({ ts: Date.now(), key: '__monitoring_down', kpiType: '', modalTitle: '', value: 0, prev: 0, detail: '', suppressed: false, read: false });
            critBellSave(items);
            critBellRender();
            debugLog('[TOAST] ' + TOAST_STALE_STREAK_WARN + ' leituras stale seguidas: monitorizacao de criticos parada', 'warn');
        }
        function critBellRender() {
            const btn = document.getElementById('critBellBtn');
            const badge = document.getElementById('critBellBadge');
            if (!btn || !badge) return;
            const items = critBellLoad();
            const unread = items.filter(i => !i.read);
            badge.hidden = unread.length === 0;
            badge.textContent = unread.length > 99 ? '99+' : String(unread.length);
            btn.setAttribute('aria-label', _kpiTp('crit_bell.aria', 'Avisos críticos, {n} por ler', { n: unread.length }));
            // sem lembrete por toast: o badge pulsa quando o nao-lido mais antigo passa do limiar
            const oldest = unread.reduce((m, i) => Math.min(m, i.ts), Infinity);
            btn.classList.toggle('crit-bell-stale', unread.length > 0 && (Date.now() - oldest) > CRIT_BELL_STALE_MS);
            const panel = document.getElementById('critBellPanel');
            if (panel && !panel.hidden) critBellRenderPanel(items);
        }
        function critBellTitle(item) {
            return item.key === '__monitoring_down' ? t('crit_bell.monitoring_down') : t('toast.' + item.key);
        }
        function critBellRenderPanel(items) {
            const panel = document.getElementById('critBellPanel');
            if (!panel) return;
            const list = items || critBellLoad();
            let h = '<div class="crit-bell-head"><span>' + _bellEsc(t('crit_bell.title')) + '</span>'
                  + '<button type="button" class="crit-bell-clear" onclick="event.stopPropagation(); critBellClear()">' + _bellEsc(t('crit_bell.clear')) + '</button></div>';
            if (!list.length) {
                h += '<div class="crit-bell-empty">' + _bellEsc(t('crit_bell.empty')) + '</div>';
            } else {
                list.forEach((item, idx) => {
                    const hora = new Date(item.ts).toLocaleTimeString(document.documentElement.lang || undefined, { hour: '2-digit', minute: '2-digit' });
                    const valor = item.key === '__monitoring_down' ? '' : (item.prev ? item.prev + ' → ' + item.value : String(item.value));
                    h += '<button type="button" role="menuitem" class="crit-bell-item' + (item.read ? '' : ' unread') + '" onclick="critBellOpen(' + idx + ')">'
                       + '<div>' + _bellEsc(critBellTitle(item)) + (valor ? ': <b>' + _bellEsc(valor) + '</b>' : '') + '</div>'
                       + (item.detail ? '<div class="crit-bell-meta"><span>' + _bellEsc(item.detail) + '</span></div>' : '')
                       + '<div class="crit-bell-meta"><span>' + _bellEsc(hora) + '</span><span>' + _bellEsc(item.suppressed ? t('crit_bell.suppressed') : '') + '</span></div>'
                       + '</button>';
                });
            }
            panel.innerHTML = h;
        }
        function critBellToggle(force) {
            const btn = document.getElementById('critBellBtn');
            const panel = document.getElementById('critBellPanel');
            if (!btn || !panel) return;
            const abrir = typeof force === 'boolean' ? force : panel.hidden;
            if (abrir) {
                critBellRenderPanel();
                panel.hidden = false;
                btn.setAttribute('aria-expanded', 'true');
                const items = critBellLoad();       // abrir o sino marca tudo como lido
                items.forEach(i => { i.read = true; });
                critBellSave(items);
                critBellRender();
                const primeiro = panel.querySelector('[role="menuitem"]');
                if (primeiro) primeiro.focus();
            } else {
                panel.hidden = true;
                btn.setAttribute('aria-expanded', 'false');
            }
        }
        function critBellOpen(idx) {
            const item = critBellLoad()[idx];
            critBellToggle(false);
            if (!item) return;
            if (item.kpiType && typeof showProblematicInstances === 'function') {
                showProblematicInstances(item.kpiType, item.modalTitle);
            } else if (typeof goToDashboardKPIs === 'function') {
                goToDashboardKPIs();
            }
        }
        function critBellClear() {
            critBellSave([]);
            critBellRender();
            critBellRenderPanel([]);
        }
        function showCriticalSummaryToast(checks) {
            const resumo = _kpiTp('crit_bell.summary', '{n} condições críticas ativas', { n: checks.length });
            const live = document.getElementById('critBellLive');
            if (live) live.textContent = resumo;
            if (isOnDashboardKPIs()) return;   // ja gravados no sino; o ecra de KPIs e' o aviso
            const container = document.getElementById('toastContainer');
            if (!container) return;
            const toast = document.createElement('div');
            toast.className = 'toast-notification';
            const nomes = checks.slice(0, 3).map(c => t('toast.' + c.key)).join(', ') + (checks.length > 3 ? '…' : '');
            toast.innerHTML = '<div class="toast-header">'
                + '<span class="toast-severity"><i class="fas fa-bell"></i> ' + _bellEsc(t('toast.critical')) + '</span>'
                + '<button class="toast-close" onclick="event.stopPropagation(); dismissToast(this.closest(\'.toast-notification\'))"><i class="fas fa-times"></i></button>'
                + '</div>'
                + '<div class="toast-body">' + _bellEsc(resumo) + '</div>'
                + '<div class="toast-detail">' + _bellEsc(nomes) + '</div>'
                + '<div class="toast-progress"></div>';
            toast.onclick = () => { dismissToast(toast); critBellToggle(true); };
            container.appendChild(toast);
            setTimeout(() => dismissToast(toast), TOAST_AUTO_DISMISS);
        }
        document.addEventListener('keydown', (e) => {
            const panel = document.getElementById('critBellPanel');
            if (!panel || panel.hidden) return;
            const itens = Array.from(panel.querySelectorAll('[role="menuitem"]'));
            const i = itens.indexOf(document.activeElement);
            if (e.key === 'Escape') {
                e.preventDefault();
                critBellToggle(false);
                const b = document.getElementById('critBellBtn');
                if (b) b.focus();                  // Escape devolve o foco (o menu de perfil nao faz isto)
            } else if (!itens.length) {
                return;
            } else if (e.key === 'ArrowDown') {
                e.preventDefault(); itens[(i + 1) % itens.length].focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault(); itens[(i - 1 + itens.length) % itens.length].focus();
            } else if (e.key === 'Home') {
                e.preventDefault(); itens[0].focus();
            } else if (e.key === 'End') {
                e.preventDefault(); itens[itens.length - 1].focus();
            }
        });
        document.addEventListener('click', (e) => {
            const bell = document.getElementById('criticalAlertsBell');
            const panel = document.getElementById('critBellPanel');
            if (bell && panel && !panel.hidden && !bell.contains(e.target)) critBellToggle(false);
        });
        setInterval(critBellRender, 60000);       // reavalia a idade dos nao-lidos sem novo polling
"""

EDITS = [
    ("        /* Critical Toast Notifications */\n        .toast-container {\n",
     CSS + "        /* Critical Toast Notifications */\n        .toast-container {\n", 1),
    ("                <!-- Language Selector v2 (i18n with flags) -->\n",
     HTML + "                <!-- Language Selector v2 (i18n with flags) -->\n", 1),
    ("        let _toastBaselineDone = false; // primeiro poll e silencioso\n",
     "        let _toastBaselineDone = false;\n"
     "        // A2 2026-09-14: estado por CONDICAO, separado de _toastPreviousState (que alimenta o texto \"3 -> 4\")\n"
     "        let _toastLastFired = {};\n"
     "        let _toastStaleStreak = 0;\n"
     "        const CRIT_BELL_KEY = 'watcherdb-crit-bell-v1';\n"
     "        const CRIT_BELL_MAX = 50;\n"
     "        const CRIT_BELL_STALE_MS = 30 * 60 * 1000;   // nao-lido ha mais de 30 min: o badge pulsa\n"
     "        const TOAST_STALE_STREAK_WARN = 10;           // ~5 min de dados stale seguidos\n", 1),
    ("debugLog('[TOAST] Sistema de notificacoes criticas iniciado (polling 60s)', 'info');",
     "critBellRender();\n"
     "            debugLog('[TOAST] Sistema de notificacoes criticas iniciado (polling ' + (TOAST_POLL_INTERVAL / 1000) + 's)', 'info');", 1),
    ("                if (result.stale === true) {\n",
     "                if (result.stale === true) {\n"
     "                    // A2 2026-09-14: stale persistente = monitorizacao de criticos parada. Sem isto o sino\n"
     "                    // ficava vazio sem sinal nenhum (achado do frontend-specialist).\n"
     "                    _toastStaleStreak++;\n"
     "                    if (_toastStaleStreak === TOAST_STALE_STREAK_WARN) critBellRecordMonitoringDown();\n", 1),
    (LOOP_VELHO, LOOP_NOVO, 1),
    ("        function showCriticalToast(check, value, prevValue, detail) {\n"
     "            // Suprimir toasts se o utilizador ja esta no KPIs\n"
     "            if (isOnDashboardKPIs()) return;\n",
     "        function showCriticalToast(check, value, prevValue, detail) {\n"
     "            // A2 2026-09-14: no ecra de KPIs o toast continua suprimido (o proprio ecra e' o aviso), mas o\n"
     "            // evento GRAVA-SE no sino, marcado como lido, em vez de desaparecer sem rasto.\n"
     "            if (isOnDashboardKPIs()) {\n"
     "                critBellRecord(check, value, prevValue, detail, { suppressed: true });\n"
     "                return;\n"
     "            }\n"
     "            critBellRecord(check, value, prevValue, detail, {});\n", 1),
    ("        function dismissToast(toast) {\n"
     "            if (!toast || toast.classList.contains('toast-exit')) return;\n"
     "            toast.classList.add('toast-exit');\n"
     "            setTimeout(() => toast.remove(), 300);\n"
     "        }\n",
     "        function dismissToast(toast) {\n"
     "            if (!toast || toast.classList.contains('toast-exit')) return;\n"
     "            toast.classList.add('toast-exit');\n"
     "            setTimeout(() => toast.remove(), 300);\n"
     "        }\n" + BELL_JS, 1),
]

I18N = {
    "pt": {"title": "Avisos críticos", "empty": "Sem avisos críticos registados", "clear": "Limpar",
           "aria": "Avisos críticos, {n} por ler", "summary": "{n} condições críticas ativas",
           "suppressed": "visto no ecrã de KPIs",
           "monitoring_down": "Monitorização de críticos parada (dados desatualizados)"},
    "en": {"title": "Critical alerts", "empty": "No critical alerts recorded", "clear": "Clear",
           "aria": "Critical alerts, {n} unread", "summary": "{n} active critical conditions",
           "suppressed": "seen on the KPIs screen",
           "monitoring_down": "Critical monitoring stalled (stale data)"},
    "es": {"title": "Alertas críticas", "empty": "Sin alertas críticas registradas", "clear": "Limpiar",
           "aria": "Alertas críticas, {n} sin leer", "summary": "{n} condiciones críticas activas",
           "suppressed": "vista en la pantalla de KPIs",
           "monitoring_down": "Monitorización de críticos detenida (datos obsoletos)"},
}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Avisos críticos com disciplina, e um sino com histórico** (A2, pedido do owner a 14/09). O aviso de KPI\n"
                  "  crítico já existia mas tinha três defeitos: a primeira leitura era silenciosa (quem abria o portal com\n"
                  "  condições críticas activas nunca via aviso), a deduplicação era por valor (um valor a oscilar disparava a\n"
                  "  cada subida) e no ecrã de KPIs o aviso era descartado sem registo. Agora a primeira leitura mostra um aviso\n"
                  "  consolidado, cada condição só volta a disparar se agravar, e tudo fica num sino ao lado do idioma, com os\n"
                  "  avisos vistos no ecrã de KPIs já marcados como lidos. O badge pulsa quando há um aviso por ler há mais de\n"
                  "  30 minutos, e dados desactualizados persistentes deixam registo de que a vigilância parou. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-14 -- A2: disciplina dos avisos criticos e sino com historico.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
POLL = PORTAL[PORTAL.index("async function pollCriticalKPIs()"):PORTAL.index("function isOnDashboardKPIs()")]


def test_d1_primeira_leitura_deixa_de_ser_silenciosa():
    assert "showCriticalSummaryToast(_activosNoArranque)" in POLL
    assert "critBellRecord(check, currentValue, previousValue, detail, {})" in POLL


def test_d2_estado_por_condicao_e_nao_por_valor():
    assert "let _toastLastFired = {};" in PORTAL
    assert "toastKey = `${check.key}_${currentValue}`" not in POLL
    # limpa sempre que volta a 0, fora do ramo de disparo
    assert "if (currentValue === 0) {\n                        delete _toastLastFired[check.key];" in POLL
    assert "currentValue > (_toastLastFired[check.key] || 0)" in POLL


def test_d2_texto_de_variacao_continua_a_usar_o_valor_anterior():
    # _toastPreviousState e _toastLastFired sao papeis distintos
    assert "_toastPreviousState[check.key] = currentValue;" in POLL
    assert "showCriticalToast(check, currentValue, previousValue, detail)" in POLL


def test_d3_suprimido_no_ecra_de_kpis_grava_como_lido():
    assert "critBellRecord(check, value, prevValue, detail, { suppressed: true });" in PORTAL
    assert "read: !!o.suppressed" in PORTAL


def test_sino_acessivel_e_no_sitio_certo():
    i_bell = PORTAL.index('id="criticalAlertsBell"')
    i_lang = PORTAL.index('id="headerLangSelector"')
    assert i_bell < i_lang, "o sino vai antes do selector de idioma"
    for attr in ('aria-haspopup="true"', 'aria-expanded="false"', 'aria-controls="critBellPanel"'):
        assert attr in PORTAL
    assert 'id="critBellLive" class="crit-bell-sr" aria-live="polite"' in PORTAL
    assert "if (e.key === 'Escape')" in PORTAL and "b.focus();" in PORTAL


def test_historico_em_localstorage_protegido():
    assert "try {\n                const v = JSON.parse(localStorage.getItem(CRIT_BELL_KEY)" in PORTAL
    assert "localStorage.setItem(CRIT_BELL_KEY, JSON.stringify(items.slice(0, CRIT_BELL_MAX)))" in PORTAL


def test_badge_pulsa_e_respeita_reduced_motion():
    assert "CRIT_BELL_STALE_MS = 30 * 60 * 1000" in PORTAL
    assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{ \.crit-bell-btn\.crit-bell-stale", PORTAL)


def test_stale_persistente_deixa_registo():
    assert "_toastStaleStreak++;" in POLL
    assert "critBellRecordMonitoringDown()" in POLL
    assert "_toastStaleStreak = 0;" in POLL


def test_drift_do_intervalo_corrigido():
    assert "(polling 60s)" not in PORTAL


def test_chaves_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        cb = d["crit_bell"]
        for k in ("title", "empty", "clear", "aria", "summary", "suppressed", "monitoring_down"):
            assert cb[k], (loc, k)
        assert "{n}" in cb["aria"] and "{n}" in cb["summary"], loc
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


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal_raw = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal_raw:
        print("[ABORT] ja aplicado"); return 1
    out = {"portal": _apply(portal_raw, EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if '"crit_bell"' in raw:
            raise SystemExit(f"[ABORT] {loc}: crit_bell ja existe")
        corpo = ",\n".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in I18N[loc].items())
        bloco = '\n  "crit_bell": {\n' + corpo + '\n  },\n  "toast": {'
        out[loc] = _apply(raw, [('\n  "toast": {', bloco, 1)], loc)
        json.loads(out[loc])   # tem de continuar JSON valido
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print(f"[ok] anchors: portal {len(EDITS)} blocos; i18n crit_bell 7 chaves x3 (JSON valido); changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    compile(TEST_SRC, str(REL["test"]), "exec")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_a2_avisos_criticos_20260914.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
