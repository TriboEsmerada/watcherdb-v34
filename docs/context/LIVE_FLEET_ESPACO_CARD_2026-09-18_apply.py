# -*- coding: utf-8 -*-
"""LIVE Fleet: card "Espaço" que filtra o ecrã + discos partilhados agregados por host (owner, 18/09).

 1. Card novo no topo, a seguir a Drilled: número de instâncias com filegroups/discos em risco (space_risk). Cor
    crítica se alguma linha >= 98%, aviso caso contrário, ok a zero. Clique filtra o ecrã como os outros cards.
 3. Piores canais: o espaço crítico entra no score (>= 98%: +800, em risco: +300; só o blocking pesa mais) e na razão
    mostrada no chip (💾 98,1%).
 2. "O KPI tem 3 críticos e o LIVE tem 2": o painel mostra os 8 primeiros por espaço livre e dois dos três filegroups
    críticos do SQLIDSPRD03 (99,0% com 72 GB, 98,4% com 105 GB) ficavam atrás de seis linhas de disco, das quais três
    eram o MESMO volume partilhado do cluster visto por duas instâncias (F:\\Data2 em I01 e I05, etc.). Os discos passam a
    ser agregados por volume (mesmo caminho, mesmo total e mesmo livre ao MB, mesmo entre hosts diferentes), com as
    outras instâncias no tooltip; o título mostra o total de itens em risco, porque o painel só lista 8. Com isso os três
    filegroups críticos cabem nos 8.

Texto novo por _kpiT: live.fleet_space_card ("Espaço"), live.fleet_space_also ("também em").
Requer LIVE_FLEET_ESPACO aplicado.

Uso (raiz do repo):
  py docs/context/LIVE_FLEET_ESPACO_CARD_2026-09-18_apply.py --check
  py docs/context/LIVE_FLEET_ESPACO_CARD_2026-09-18_apply.py
  py -m pytest tests/unit/test_live_f9b_20260911.py tests/unit/test_live_typography_tokens.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "spaceInst"

EDITS = [
    ("""            const drilled = instances.filter(i => _drilledSet.has(i.instance));
            const groups = { online: online, partial: partial, offline: offline, no_data: noData, cpu: cpuHigh, mem: memHigh, ple: lowPle, blocking: blocked, drilled: drilled };
            const labels = { online: 'Online', partial: 'Parcial', offline: 'Offline', no_data: t('live.no_data_short'), cpu: 'CPU >50%', mem: 'MEM >85%', ple: 'Low PLE', blocking: 'Blocking', drilled: 'Drilled' };""",
     """            const drilled = instances.filter(i => _drilledSet.has(i.instance));
            // 2026-09-18 (owner): card "Espaco" = instancias com filegroups/discos em risco (space_risk)
            const spaceRows = data.space_risk || [];
            const spaceSet = new Set(spaceRows.map(r => r.instance));
            const spaceInst = instances.filter(i => spaceSet.has(i.instance));
            const spaceMaxPct = spaceRows.reduce((m, r) => Math.max(m, Number(r.pct_used || 0)), 0);
            const spaceWorst = {}; spaceRows.forEach(r => { spaceWorst[r.instance] = Math.max(spaceWorst[r.instance] || 0, Number(r.pct_used || 0)); });
            const groups = { online: online, partial: partial, offline: offline, no_data: noData, cpu: cpuHigh, mem: memHigh, ple: lowPle, blocking: blocked, drilled: drilled, space: spaceInst };
            const labels = { online: 'Online', partial: 'Parcial', offline: 'Offline', no_data: t('live.no_data_short'), cpu: 'CPU >50%', mem: 'MEM >85%', ple: 'Low PLE', blocking: 'Blocking', drilled: 'Drilled', space: _kpiT('live.fleet_space_card', 'Espaço') };""", 1),
    ("""            h += _fleetCard(labels.drilled, problemCount, 'var(--color-text-link)', 'fa-satellite-dish', 'drilled', tabId, fKey);
""", """            h += _fleetCard(labels.drilled, problemCount, 'var(--color-text-link)', 'fa-satellite-dish', 'drilled', tabId, fKey);
            h += _fleetCard(labels.space, spaceInst.length, spaceInst.length > 0 ? (spaceMaxPct >= 98 ? 'var(--sev-critical-text)' : 'var(--sev-warning-text)') : 'var(--sev-ok-text)', 'fa-hdd', 'space', tabId, fKey);
""", 1),
    ("""            rows = (rows || []).slice().sort((a, b) => (a.free_mb || 0) - (b.free_mb || 0)).slice(0, 8);""",
     """            // discos partilhados (cluster): o mesmo volume visto por varias instancias do mesmo host conta uma vez
            const vistos = new Map();
            (rows || []).slice().sort((a, b) => (a.free_mb || 0) - (b.free_mb || 0)).forEach(r => {
                // volume partilhado de cluster: mesma letra/caminho com o MESMO total e o MESMO livre (ao MB) e' o mesmo disco,
                // mesmo quando as instancias estao em hosts diferentes (SQLMDMPRD03/04 G: na prova de 18/09)
                const k = r.kind === 'disk' ? 'disk|' + String(r.object || '').toLowerCase() + '|' + Math.round(r.total_mb || 0) + '|' + Math.round(r.free_mb || 0) : 'fg|' + r.instance + '|' + r.database + '|' + r.object;
                if (vistos.has(k)) { const p = vistos.get(k); if (p.instance !== r.instance) (p.tambem = p.tambem || []).push(r.instance); }
                else vistos.set(k, Object.assign({}, r));
            });
            const totalRisco = vistos.size;
            rows = Array.from(vistos.values()).slice(0, 8);""", 1),
    ("""                const tip = `${inst} — ${obj}: ${pct.toFixed(1)}% · ${_kpiT('live.fleet_space_free', 'livre')} ${Math.round(r.free_mb || 0)} MB / ${Math.round(r.total_mb || 0)} MB`;""",
     """                const tip = `${inst} — ${obj}: ${pct.toFixed(1)}% · ${_kpiT('live.fleet_space_free', 'livre')} ${Math.round(r.free_mb || 0)} MB / ${Math.round(r.total_mb || 0)} MB` + (r.tambem && r.tambem.length ? ` · ${_kpiT('live.fleet_space_also', 'também em')} ${r.tambem.map(esc).join(', ')}` : '');""", 1),
    # 3. piores canais: o espaco critico entra no score (owner: "veja se a regra dos piores canais envolve o espaco critico")
    ("""                const scoreA = (a.blocked||0)*1000 + (a.cpu_pct||0)*10 + (10000/(a.ple||9999)) + (a.mem_pct||0);
                const scoreB = (b.blocked||0)*1000 + (b.cpu_pct||0)*10 + (10000/(b.ple||9999)) + (b.mem_pct||0);""",
     """                const spA = spaceWorst[a.instance] || 0, spB = spaceWorst[b.instance] || 0;   // 2026-09-18: espaco critico pesa (>=98%: 800; em risco: 300)
                const scoreA = (a.blocked||0)*1000 + (spA >= 98 ? 800 : spA > 0 ? 300 : 0) + (a.cpu_pct||0)*10 + (10000/(a.ple||9999)) + (a.mem_pct||0);
                const scoreB = (b.blocked||0)*1000 + (spB >= 98 ? 800 : spB > 0 ? 300 : 0) + (b.cpu_pct||0)*10 + (10000/(b.ple||9999)) + (b.mem_pct||0);""", 1),
    ("""                    let reason = blk > 0 ? `🔒 ${blk} blocked` : cpu > 70 ? `CPU ${cpu}%` : ple < 300 ? `PLE ${ple}s` : `MEM ${mem}%`;""",
     """                    const spI = spaceWorst[i.instance] || 0;
                    let reason = blk > 0 ? `🔒 ${blk} blocked` : spI >= 98 ? `💾 ${spI.toFixed(1)}%` : cpu > 70 ? `CPU ${cpu}%` : ple < 300 ? `PLE ${ple}s` : spI > 0 ? `💾 ${spI.toFixed(1)}%` : `MEM ${mem}%`;""", 1),
    ("""' + _kpiT('live.fleet_space_title', 'ESPAÇO CRÍTICO (frota)') + '</div>';""",
     """' + _kpiT('live.fleet_space_title', 'ESPAÇO CRÍTICO (frota)') + (rows.length ? ' <span style="font-weight:400;color:var(--color-text-tertiary);">(' + totalRisco + ')</span>' : '') + '</div>';""", 1),
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
    if "_fleetSpacePanel" not in portal:
        print("[ABORT] LIVE_FLEET_ESPACO nao esta aplicado (aplicar primeiro)"); return 1
    novo = _apply(portal, EDITS, "fleet card espaco")
    print(f"[ok] {len(EDITS)} blocos (card Espaco, grupo/filtro, discos agregados por volume, tooltip, piores canais, titulo com total)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
