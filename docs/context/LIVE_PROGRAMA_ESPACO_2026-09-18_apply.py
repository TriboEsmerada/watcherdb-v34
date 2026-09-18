# -*- coding: utf-8 -*-
"""LIVE: programa novo "Espaço" por instância — filegroups e discos — e o clique do painel "Espaço crítico" passa a abri-lo
(owner, 18/09: "é preciso criar o sítio dele para quando clicar em alguma instância traga as informações de filegroup e disco").

 - Botão "Espaço" na barra de programas (antes de ErrLog). Endpoint novo GET /api/v1/live/{instance}/space: lê as duas STG do
   WatcherDB_Intelligence (KPI_MSSQL_FG_USAGE_STG e KPI_MSSQL_DISK_USAGE_STG) para a instância, via execute_intelligence_query
   (identidade sql_monitoring, SELECT). Não toca na instância monitorizada: é a última coleta do coletor, com o carimbo.
 - Ecrã: DISCOS (volume, total, usado, livre, % usado com barra; cor por % livre: <= 5 crítico, <= 10 aviso, <= 20 atenção)
   e FILEGROUPS (base, filegroup, total, usado, livre, % usado, tecto/crescimento; cor pela regra do KPI: % livre efectiva
   < 2 crítico, < 5 aviso, < 10 atenção; UNLIMITED assinalado como dependente do disco). Piores primeiro.
 - Ajuda "?" do programa: 5 chaves live.help_space_* em pt/en/es (o painel de ajuda usa t() sem fallback); pt-BR herda do pt.
 - Painel "Espaço crítico (frota)" e os chips: o clique abre o programa Espaço da instância (era I/O).

Texto novo por _kpiT: live.prog_space, live.space_disks, live.space_filegroups, live.space_collected, live.space_no_data,
live.space_unlimited, live.space_capped. Requer LIVE_CANAL_AJUDA aplicado.

Uso (raiz do repo):
  py docs/context/LIVE_PROGRAMA_ESPACO_2026-09-18_apply.py --check
  py docs/context/LIVE_PROGRAMA_ESPACO_2026-09-18_apply.py
  py -m pytest tests/unit/test_i18n_parity.py tests/unit/test_live_typography_tokens.py tests/unit/test_live_ajuda_sched_20260915.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet > clicar numa linha do Espaço crítico
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
BACKEND = Path("api/routers/live_monitoring.py")
MARK = "_liveRenderSpace"
# teste que fixa a lista de programas com ajuda: entra o 'space'
_T_OLD = 'PROGS = ["fleet", "queries", "waits", "blocking", "plancache", "memory", "tempdb", "io", "tlog", "connections", "jobs",\n         "alwayson", "schedulers", "errorlog"]'
_T_NEW = 'PROGS = ["fleet", "queries", "waits", "blocking", "plancache", "memory", "tempdb", "io", "tlog", "connections", "jobs",\n         "alwayson", "schedulers", "errorlog", "space"]   # 2026-09-18: programa Espaco'
TESTES = {Path("tests/unit/test_live_ajuda_sched_20260915.py"): [(_T_OLD, _T_NEW, 1)]}

HELP = {
    "pt": {"title": "Espaço — filegroups e discos da instância",
           "what": "Ocupação dos filegroups e dos volumes de disco da instância na última coleta do coletor, do mais cheio para o menos.",
           "how": "Filegroups: % usado do alocado; com Max Size acima do alocado conta o espaço até ao tecto; crescimento ilimitado depende do disco. Discos: % livre por volume. Cores pela regra do KPI de filegroups e dos limiares de disco.",
           "when": "Filegroup com menos de 5% livre efetivo ou volume com 10% ou menos livre, sobretudo com pouco espaço absoluto.",
           "next": "Filegroup: aumentar o ficheiro ou o Max Size, ou libertar espaço. Disco: abrir Space no servidor e ver os maiores ficheiros e o crescimento."},
    "en": {"title": "Space — filegroups and disks of the instance",
           "what": "Filegroup and disk volume usage of the instance from the collector's latest run, fullest first.",
           "how": "Filegroups: % used of allocated space; with a Max Size above the allocated size, the room up to that cap counts; unlimited growth depends on the disk. Disks: % free per volume. Colours follow the filegroup KPI rule and the disk thresholds.",
           "when": "A filegroup under 5% effective free space or a volume with 10% or less free, especially with little absolute space left.",
           "next": "Filegroup: grow the file or the Max Size, or free space. Disk: open Space on the server and look at the largest files and growth."},
    "es": {"title": "Espacio — filegroups y discos de la instancia",
           "what": "Ocupación de los filegroups y de los volúmenes de disco de la instancia en la última recolección del colector, del más lleno al menos.",
           "how": "Filegroups: % usado del asignado; con Max Size por encima del asignado cuenta el espacio hasta el tope; el crecimiento ilimitado depende del disco. Discos: % libre por volumen. Colores según la regla del KPI de filegroups y los umbrales de disco.",
           "when": "Filegroup con menos del 5% libre efectivo o volumen con 10% o menos libre, sobre todo con poco espacio absoluto.",
           "next": "Filegroup: aumentar el archivo o el Max Size, o liberar espacio. Disco: abrir Space en el servidor y ver los archivos más grandes y el crecimiento."},
}

EDITS_PORTAL = [
    # botao na barra (antes de ErrLog)
    ("""                    <button onclick="liveSetProgram('${tabId}','errorlog')" class="live-prog-btn" data-prog="errorlog" style="${_pb}">ErrLog</button>""",
     """                    <button onclick="liveSetProgram('${tabId}','space')" class="live-prog-btn" data-prog="space" style="${_pb}" title="${_kpiT('live.prog_space_tip', 'Filegroups e discos da instância (última coleta)')}">${_kpiT('live.prog_space', 'Espaço')}</button>
                    <button onclick="liveSetProgram('${tabId}','errorlog')" class="live-prog-btn" data-prog="errorlog" style="${_pb}">ErrLog</button>""", 1),
    # ajuda do programa
    ("""        const _LIVE_HELP_PROGS = ['fleet', 'queries', 'waits', 'blocking', 'plancache', 'memory', 'tempdb', 'io', 'tlog', 'connections', 'jobs', 'alwayson', 'schedulers', 'errorlog'];""",
     """        const _LIVE_HELP_PROGS = ['fleet', 'queries', 'waits', 'blocking', 'plancache', 'memory', 'tempdb', 'io', 'tlog', 'connections', 'jobs', 'alwayson', 'schedulers', 'errorlog', 'space'];"""
     , 1),
    # dispatch
    ("""            if (program === 'io') return _liveRenderIO(data);""",
     """            if (program === 'io') return _liveRenderIO(data);
            if (program === 'space') return _liveRenderSpace(data);""", 1),
    # painel do Fleet: clique abre o programa Espaco
    ("""onclick="_fleetSwitchTo('${inst}','io')" title="${tip}">""", """onclick="_fleetSwitchTo('${inst}','space')" title="${tip}">""", 1),
    # renderer (a seguir ao _liveRenderIO)
    ("""        function _liveRenderIO(data) {""",
     """        // 2026-09-18 (owner): programa Espaco -- filegroups e discos da instancia (ultima coleta do coletor, STG)
        function _liveRenderSpace(data) {
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
            const disks = data.disks || [], fgs = data.filegroups || [];
            if (!disks.length && !fgs.length) return '<div style="color:var(--color-text-tertiary);text-align:center;padding:40px;">' + _kpiT('live.space_no_data', 'Sem dados de filegroups nem de discos para esta instância na última coleta.') + '</div>';
            const sevDisk = pf => pf <= 5 ? 'critical' : pf <= 10 ? 'warning' : pf <= 20 ? 'attention' : 'ok';
            const sevFg = ef => ef == null ? 'ok' : ef < 2 ? 'critical' : ef < 5 ? 'warning' : ef < 10 ? 'attention' : 'ok';
            const barra = (pctUsado, sev) => `<div style="display:flex;align-items:center;gap:6px;"><div style="flex:1;height:8px;background:var(--color-bg-sunken);border-radius:4px;overflow:hidden;"><div style="width:${Math.max(0, Math.min(100, pctUsado)).toFixed(1)}%;height:100%;background:var(--sev-${sev}-border);"></div></div><span style="width:52px;text-align:right;color:var(--sev-${sev}-text);font-weight:600;">${pctUsado.toFixed(1)}%</span></div>`;
            const carimbo = (rows) => { const ts = rows.map(r => r.Update_TS || r.update_ts).filter(Boolean).sort().pop(); return ts ? String(ts).replace('T', ' ').substring(0, 19) : ''; };
            const th = 'padding:6px 8px;text-align:left;color:var(--color-text-tertiary);font-weight:600;border-bottom:1px solid var(--color-border);';
            const thR = th + 'text-align:right;';
            const td = 'padding:5px 8px;border-bottom:1px solid var(--color-bg-panel);';
            const tdR = td + 'text-align:right;font-variant-numeric:tabular-nums;';
            let h = '';
            h += '<div style="background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;padding:12px;margin-bottom:12px;">';
            h += `<div style="display:flex;align-items:baseline;gap:10px;color:var(--color-text-tertiary);font-size:12px;font-weight:600;margin-bottom:8px;"><span><i class="fas fa-hdd" style="margin-right:6px;color:var(--sev-info-text);"></i>${_kpiT('live.space_disks', 'DISCOS')} (${disks.length})</span><span style="font-weight:400;">${carimbo(disks) ? _kpiT('live.space_collected', 'coleta') + ' ' + esc(carimbo(disks)) : ''}</span></div>`;
            if (disks.length) {
                h += `<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr><th style="${th}">Volume</th><th style="${thR}">Total</th><th style="${thR}">${_kpiT('live.space_used', 'Usado')}</th><th style="${thR}">${_kpiT('live.fleet_space_free', 'livre')}</th><th style="${th}width:34%;">% ${_kpiT('live.space_used', 'Usado')}</th></tr></thead><tbody>`;
                disks.slice().sort((a, b) => (a.Percent_Free || 0) - (b.Percent_Free || 0)).forEach(d => {
                    const pf = Number(d.Percent_Free || 0), sev = sevDisk(pf);
                    h += `<tr><td style="${td}color:var(--color-text-bright);font-family:var(--font-mono);">${esc(d.Drive)}</td><td style="${tdR}">${formatSizeMB(Math.round(d.Total_MB || 0))}</td><td style="${tdR}">${formatSizeMB(Math.round(d.Used_MB || 0))}</td><td style="${tdR}color:var(--sev-${sev}-text);font-weight:600;">${formatSizeMB(Math.round(d.Free_MB || 0))}</td><td style="${td}">${barra(100 - pf, sev)}</td></tr>`;
                });
                h += '</tbody></table>';
            } else {
                h += '<div style="color:var(--color-text-tertiary);font-size:12px;padding:6px 0;">' + _kpiT('live.space_no_disks', 'Sem dados de disco para esta instância.') + '</div>';
            }
            h += '</div>';
            h += '<div style="background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;padding:12px;">';
            h += `<div style="display:flex;align-items:baseline;gap:10px;color:var(--color-text-tertiary);font-size:12px;font-weight:600;margin-bottom:8px;"><span><i class="fas fa-layer-group" style="margin-right:6px;color:var(--sev-info-text);"></i>${_kpiT('live.space_filegroups', 'FILEGROUPS')} (${fgs.length > 80 ? '80 / ' : ''}${fgs.length})</span><span style="font-weight:400;">${carimbo(fgs) ? _kpiT('live.space_collected', 'coleta') + ' ' + esc(carimbo(fgs)) : ''}</span></div>`;
            if (fgs.length) {
                h += `<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr><th style="${th}">Database</th><th style="${th}">Filegroup</th><th style="${thR}">Total</th><th style="${thR}">${_kpiT('live.space_used', 'Usado')}</th><th style="${thR}">${_kpiT('live.fleet_space_free', 'livre')}</th><th style="${th}">${_kpiT('live.space_cap', 'Tecto')}</th><th style="${th}width:26%;">% ${_kpiT('live.space_used', 'Usado')}</th></tr></thead><tbody>`;
                const eff = f => { const gt = String(f.Growth_Type || '').toUpperCase(); const mx = Number(f.Max_Size_MB || 0), tot = Number(f.Total_MB || 0), used = Number(f.Used_MB || 0);
                    if (gt === 'UNLIMITED') return null; if (mx > 0 && mx > tot) return (mx - used) * 100 / mx; return 100 - Number(f.Percent_Used || 0); };
                // 450 filegroups numa instancia grande (prova de 18/09): mostra os 80 piores; o titulo diz quantos ha
                const ordenados = fgs.slice().sort((a, b) => { const ea = eff(a), eb = eff(b); return (ea == null ? 999 : ea) - (eb == null ? 999 : eb); });
                const mostrados = ordenados.slice(0, 80);
                mostrados.forEach(f => {
                    const ef = eff(f), sev = sevFg(ef); const gt = String(f.Growth_Type || '').toUpperCase(); const mx = Number(f.Max_Size_MB || 0), tot = Number(f.Total_MB || 0);
                    const tecto = gt === 'UNLIMITED' ? `<span style="color:var(--color-text-tertiary);">${_kpiT('live.space_unlimited', 'ilimitado (disco)')}</span>` : (mx > 0 && mx > tot) ? formatSizeMB(Math.round(mx)) : `<span style="color:var(--color-text-tertiary);">${_kpiT('live.space_capped', 'alocado')}</span>`;
                    h += `<tr><td style="${td}color:var(--color-text-bright);">${esc(f.Database)}</td><td style="${td}font-family:var(--font-mono);">${esc(f.Filegroup)}</td><td style="${tdR}">${formatSizeMB(Math.round(tot))}</td><td style="${tdR}">${formatSizeMB(Math.round(f.Used_MB || 0))}</td><td style="${tdR}color:var(--sev-${sev}-text);font-weight:600;">${formatSizeMB(Math.round(f.Free_MB || 0))}</td><td style="${td}">${tecto}</td><td style="${td}">${barra(Number(f.Percent_Used || 0), sev)}</td></tr>`;
                });
                h += '</tbody></table>';
            } else {
                h += '<div style="color:var(--color-text-tertiary);font-size:12px;padding:6px 0;">' + _kpiT('live.space_no_fgs', 'Sem dados de filegroups para esta instância.') + '</div>';
            }
            h += '</div>';
            return h;
        }
        function _liveRenderIO(data) {""", 1),
]

EDITS_BACKEND = [
    ("""@router.get("/{instance}/jobs")""",
     """@router.get("/{instance}/space")
async def get_space(instance: str):
    \"\"\"Espaco por instancia (2026-09-18, owner): filegroups e discos da ULTIMA coleta do coletor (STG do WatcherDB_Intelligence),
    via execute_intelligence_query (sql_monitoring, SELECT). Nao toca na instancia monitorizada.\"\"\"
    inst = (instance or "").replace("'", "''")
    fgs = execute_intelligence_query(f\"\"\"
        SELECT f.[Database], f.Filegroup, f.Total_MB, f.Used_MB, f.Free_MB, f.Percent_Used, f.Max_Size_MB, f.Growth_Type, f.Update_TS
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
        WHERE f.Instance = '{inst}'
        ORDER BY f.Percent_Used DESC\"\"\", raise_on_error=False) or []
    disks = execute_intelligence_query(f\"\"\"
        SELECT d.Drive, d.Total_MB, d.Free_MB, d.Used_MB, d.Percent_Free, d.Update_TS
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_STG d WITH (NOLOCK)
        WHERE d.Instance = '{inst}'
        ORDER BY d.Percent_Free ASC\"\"\", raise_on_error=False) or []
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "filegroups": fgs, "disks": disks,
    })


@router.get("/{instance}/jobs")""", 1),
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


def _inserir_ajuda(texto, loc):
    """Insere as 5 chaves help_space_* logo a seguir a linha "help_io_next" (grupo live), sem reformatar o JSON."""
    eol = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.split(eol)
    idx = [i for i, l in enumerate(linhas) if l.strip().startswith('"help_io_next":')]
    if len(idx) != 1:
        raise SystemExit(f"[ABORT] {loc}.json: help_io_next nao encontrado 1x")
    ind = linhas[idx[0]][:len(linhas[idx[0]]) - len(linhas[idx[0]].lstrip())]
    novas = [f'{ind}"help_space_{k}": {json.dumps(HELP[loc][k], ensure_ascii=False)},' for k in ("title", "what", "how", "when", "next")]
    novo = eol.join(linhas[:idx[0] + 1] + novas + linhas[idx[0] + 1:])
    antes, depois = json.loads(texto), json.loads(novo)
    extra = set(depois["live"]) - set(antes["live"])
    if extra != {"help_space_title", "help_space_what", "help_space_how", "help_space_when", "help_space_next"}:
        raise SystemExit(f"[ABORT] {loc}.json: insercao inesperada {extra}")
    for k in extra: depois["live"].pop(k)
    if depois != antes:
        raise SystemExit(f"[ABORT] {loc}.json: o resto do JSON mudou")
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    portal_p, back_p = base / PORTAL, base / BACKEND
    portal = portal_p.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "_liveChannelPickFirst" not in portal:
        print("[ABORT] LIVE_CANAL_AJUDA nao esta aplicado (aplicar primeiro)"); return 1
    novo_portal = _apply(portal, EDITS_PORTAL, "portal")
    novo_back = None
    if back_p.exists():
        back = back_p.read_bytes().decode("utf-8")
        if '"/{instance}/space"' in back:
            print("[ABORT] backend ja aplicado"); return 1
        novo_back = _apply(back, EDITS_BACKEND, "backend")
    novos_json = {}
    for loc in ("pt", "en", "es"):
        p = base / "static/i18n" / f"{loc}.json"
        if not p.exists():
            print(f"[skip] {p} ausente na copia"); continue
        t = p.read_bytes().decode("utf-8")
        if '"help_space_title"' in t:
            print(f"[ABORT] {loc}.json ja tem help_space_title"); return 1
        novos_json[p] = _inserir_ajuda(t, loc)
    testes_novos = {rel: _apply((base / rel).read_bytes().decode("utf-8"), edits, str(rel)) for rel, edits in TESTES.items() if (base / rel).exists()}
    print(f"[ok] portal {len(EDITS_PORTAL)} blocos (botao, ajuda, dispatch, clique do painel, renderer); backend {len(EDITS_BACKEND)}" + ("" if novo_back else " (ausente: saltado)") + f"; locales {len(novos_json)} (help_space_* x5); testes {len(testes_novos)}")
    if check:
        print("--check OK. Nada escrito."); return 0
    portal_p.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    for rel, t in testes_novos.items():
        (base / rel).write_bytes(t.encode("utf-8")); print(f"[write] {rel}")
    if novo_back is not None:
        back_p.write_bytes(novo_back.encode("utf-8")); print(f"[write] {BACKEND}")
    for p, t in novos_json.items():
        p.write_bytes(t.encode("utf-8")); print(f"[write] {p.relative_to(base)}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet > linha do Espaco critico.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
