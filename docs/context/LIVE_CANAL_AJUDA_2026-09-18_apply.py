# -*- coding: utf-8 -*-
"""LIVE: filtro dentro do canal com selecção enquanto se escreve; ícone do No data; "?" de ajuda em todos os cards do Fleet
(owner, 18/09).

 1. Canal: o filtro e a lista passam a um só controlo (campo + lista colados). Escrever ou colar vai seleccionando: com
    nome exacto ou uma única correspondência, o canal muda sozinho (450 ms depois da última tecla); Enter escolhe a
    primeira correspondência visível. A lista continua a funcionar como antes.
    Extra: com ?autoLive=1 a modal nascia antes do dicionário i18n carregar e o placeholder ficava "live.filter_instance"
    (print do owner); o placeholder passa a ser reposto quando os canais chegam, como já acontece com "Canal...".
 2. Card "No data": o ícone fa-question-circle confundia-se com o "?" de ajuda; passa a fa-eye-slash.
 3. "?" em todos os 10 cards do Fleet, com a explicação e as métricas usadas (tooltip; clique não dispara o filtro).
    Textos fiéis ao backend (get_fleet_dashboard): ok = tem métricas de perf; partial = visto por disponibilidade/disco
    sem perf; offline = sem dados e ping falhou; no_data = sem dados em tabela nenhuma; CPU >= 50 / MEM >= 85 / PLE < 300
    sobre o último snapshot; blocking = sessões bloqueadas na última coleta; drilled = instâncias problemáticas onde o
    servidor faz drill ao vivo (CPU >= 50, MEM >= 90, blocking ou PLE < 300; até 15); espaço = regra do painel.

Texto novo por _kpiT(chave, fallback): live.card_help_online/partial/offline/no_data/cpu/mem/ple/blocking/drilled/space.
Requer LIVE_FLEET_ESPACO_CARD aplicado.

Uso (raiz do repo):
  py docs/context/LIVE_CANAL_AJUDA_2026-09-18_apply.py --check
  py docs/context/LIVE_CANAL_AJUDA_2026-09-18_apply.py
  py -m pytest tests/unit/test_live_f9b_20260911.py tests/unit/test_live_typography_tokens.py tests/unit/test_live_channels_20260911.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "_liveChannelPickFirst"

EDITS = [
    # 1. campo + lista num so' controlo
    ("""                    <input id="live-channel-search-${tabId}" type="text" placeholder="${t('live.filter_instance')}"
                           oninput="liveFilterChannels('${tabId}', this.value)" autocomplete="off"
                           style="width:110px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:5px;color:var(--color-text-bright);font-size:12px;">
                    <select id="live-channel-${tabId}" onchange="liveChangeChannel('${tabId}', this.value)"
                            style="max-width:240px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:5px;color:var(--color-text-bright);font-size:12px;font-weight:500;">
                        <option value="">${t('live.channel_placeholder')}</option>
                    </select>""",
     """                    <span style="display:inline-flex;align-items:stretch;"><!-- 2026-09-18 (owner): filtro dentro do canal; escrever/colar selecciona -->
                    <input id="live-channel-search-${tabId}" type="text" placeholder="${t('live.filter_instance')}"
                           oninput="liveFilterChannels('${tabId}', this.value)" onkeydown="if(event.key==='Enter'){event.preventDefault();_liveChannelPickFirst('${tabId}');}" autocomplete="off"
                           style="width:150px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-right:none;border-radius:5px 0 0 5px;color:var(--color-text-bright);font-size:12px;">
                    <select id="live-channel-${tabId}" onchange="liveChangeChannel('${tabId}', this.value)"
                            style="max-width:240px;padding:4px 8px;background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:0 5px 5px 0;color:var(--color-text-bright);font-size:12px;font-weight:500;">
                        <option value="">${t('live.channel_placeholder')}</option>
                    </select>
                    </span>""", 1),
    ("""        function liveFilterChannels(tabId, q) {
            _liveRenderChannelOptions(tabId, q);
        }""",
     """        let _liveTypeAheadT = null;
        function _liveChannelCandidates(sel) {
            const pinned = t('live.selected_group');
            return Array.from(sel.options).filter(o => o.value && !(o.parentElement && o.parentElement.label === pinned));
        }
        function liveFilterChannels(tabId, q) {
            _liveRenderChannelOptions(tabId, q);
            // 2026-09-18 (owner): escrever ou colar vai seleccionando o canal -- nome exacto ou correspondencia unica muda o canal
            clearTimeout(_liveTypeAheadT);
            const txt = (q || '').trim().toLowerCase();
            const sel = document.getElementById('live-channel-' + tabId);
            if (!txt || !sel) return;
            const opts = _liveChannelCandidates(sel);
            const alvo = opts.find(o => o.value.toLowerCase() === txt) || (opts.length === 1 ? opts[0] : null);
            if (!alvo || alvo.value === _liveInstance) return;
            _liveTypeAheadT = setTimeout(() => { sel.value = alvo.value; liveChangeChannel(tabId, alvo.value); }, 450);
        }
        function _liveChannelPickFirst(tabId) {
            const sel = document.getElementById('live-channel-' + tabId);
            if (!sel) return;
            const first = _liveChannelCandidates(sel)[0];
            if (first && first.value !== _liveInstance) { clearTimeout(_liveTypeAheadT); sel.value = first.value; liveChangeChannel(tabId, first.value); }
        }
        window._liveChannelPickFirst = _liveChannelPickFirst;""", 1),
    # placeholder reposto quando os canais chegam (corrida com ?autoLive=1)
    ("""            const sel = document.getElementById('live-channel-' + tabId);
            if (!sel) return;
            const byEnv = _liveChannelsByEnv[tabId] || {};
            const current = sel.value || localStorage.getItem('live-last-channel') || '';""",
     """            const sel = document.getElementById('live-channel-' + tabId);
            if (!sel) return;
            const _inp = document.getElementById('live-channel-search-' + tabId);   // 2026-09-18: com ?autoLive=1 a modal nasce antes do i18n
            if (_inp) _inp.placeholder = t('live.filter_instance');
            const byEnv = _liveChannelsByEnv[tabId] || {};
            const current = sel.value || localStorage.getItem('live-last-channel') || '';""", 1),
    # 2. icone do No data
    ("""'fa-question-circle', 'no_data', tabId, fKey);""", """'fa-eye-slash', 'no_data', tabId, fKey);""", 1),
    # 3. "?" em todos os cards
    ("""        function _fleetCard(label, value, color, icon, key, tabId, activeKey) {
            const on = key && key === activeKey;""",
     """        // 2026-09-18 (owner): "?" em todos os cards com o que medem (textos fieis a get_fleet_dashboard)
        function _fleetCardHelp(key) {
            // (uma chamada _kpiT por linha: a guarda de texto a mao e' por linha)
            switch (key) {
                case 'online': return _kpiT('live.card_help_online', 'Instâncias com métricas de performance (CPU, memória, PLE) no último ciclo do coletor.');
                case 'partial': return _kpiT('live.card_help_partial', 'Instâncias vistas pelo coletor de disponibilidade/disco mas sem métricas de performance neste ciclo.');
                case 'offline': return _kpiT('live.card_help_offline', 'Sem dados no ciclo e com falha de ping: o servidor não responde.');
                case 'no_data': return _kpiT('live.card_help_no_data', 'Sem dados em nenhuma tabela do coletor neste ciclo, com ping OK.');
                case 'cpu': return _kpiT('live.card_help_cpu', 'Instâncias online com CPU ≥ 50% no último snapshot (Processor_Pct).');
                case 'mem': return _kpiT('live.card_help_mem', 'Instâncias online com memória ≥ 85% no último snapshot (Memory_Usage_Pct).');
                case 'ple': return _kpiT('live.card_help_ple', 'Instâncias online com Page Life Expectancy < 300 s no último snapshot.');
                case 'blocking': return _kpiT('live.card_help_blocking', 'Instâncias com sessões bloqueadas na última coleta de blocking.');
                case 'drilled': return _kpiT('live.card_help_drilled', 'Instâncias onde o servidor fez drill ao vivo neste ciclo (queries, blocking, tempdb, waits, AG, sessões): só as problemáticas, CPU ≥ 50%, MEM ≥ 90%, blocking ou PLE < 300 s, até 15.');
                case 'space': return _kpiT('live.card_help_space', 'Instâncias com filegroups ou discos em risco: filegroups pela regra do KPI (menos de 10% livre efetivo, crescimento ilimitado excluído) e discos com 10% ou menos livre. No painel, ordenados pelo espaço livre.');
                default: return '';
            }
        }
        function _fleetCard(label, value, color, icon, key, tabId, activeKey) {
            const on = key && key === activeKey;
            const help = _fleetCardHelp(key).replace(/"/g, '&quot;');
            const ajuda = help ? `<span title="${help}" aria-label="${help}" onclick="event.stopPropagation()" style="position:absolute;top:4px;right:6px;width:16px;height:16px;line-height:14px;border-radius:50%;font-size:12px;color:var(--color-text-tertiary);border:1px solid var(--color-border);cursor:help;text-align:center;">?</span>` : '';""", 1),
    ("""            return `<div${click} style="${frame}border-radius:8px;padding:10px 14px;min-width:100px;text-align:center;${key ? 'cursor:pointer;' : ''}"><div style="font-size:22px;font-weight:700;color:${color};">${value}</div>""",
     """            return `<div${click} style="position:relative;${frame}border-radius:8px;padding:10px 18px 10px 14px;min-width:100px;text-align:center;${key ? 'cursor:pointer;' : ''}">${ajuda}<div style="font-size:22px;font-weight:700;color:${color};">${value}</div>""", 1),
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
    src = base / PORTAL
    portal = src.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "spaceInst" not in portal:
        print("[ABORT] LIVE_FLEET_ESPACO_CARD nao esta aplicado (aplicar primeiro)"); return 1
    novo = _apply(portal, EDITS, "canal/ajuda")
    print(f"[ok] {len(EDITS)} blocos (canal com filtro dentro e type-ahead, placeholder reposto, icone No data, ajuda nos 10 cards)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
