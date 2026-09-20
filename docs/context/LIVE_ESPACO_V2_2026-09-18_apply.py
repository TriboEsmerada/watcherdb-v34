# -*- coding: utf-8 -*-
"""LIVE › Espaço, 2.ª versão (owner, 18/09): filegroups primeiro, secções recolhíveis, filtro cruzado ao clicar.

 - Ordem: FILEGROUPS primeiro, DISCOS depois.
 - Cada secção é <details> recolhível/expansível; o estado sobrevive ao refresh de 15 s (como o Sched).
 - Clique numa linha de filegroup filtra os discos para os volumes onde esse filegroup tem ficheiros; clique numa linha de
   disco filtra os filegroups para os que têm ficheiros nesse volume. Faixa "Filtro: … ×"; segundo clique na mesma linha,
   ou o ×, limpa. Com filtro, a tabela filtrada mostra todas as correspondências (o corte de 80 só vale sem filtro).
 - Relação filegroup ↔ volume: KPI_MSSQL_DATAFILES_STG tem Database, Filegroup e Physical_Path, mas Drive é só a letra
   (F:\\) e os discos são pontos de montagem (F:\\Data_15\\). O endpoint /live/{inst}/space passa a devolver "links"
   (pares distintos database, filegroup, drive), calculados no servidor pelo PREFIXO MAIS LONGO do caminho físico contra os
   volumes da instância (case-insensitive). Terceira consulta SELECT à mesma STG, mesma identidade (sql_monitoring).
   Um ficheiro sem volume correspondente cai na letra da tabela (Drive) se esta existir entre os discos.

Texto novo por _kpiT: live.space_filter, live.space_filter_clear, live.space_files_on, live.space_no_links.
Requer LIVE_PROGRAMA_ESPACO aplicado.

Uso (raiz do repo):
  py docs/context/LIVE_ESPACO_V2_2026-09-18_apply.py --check
  py docs/context/LIVE_ESPACO_V2_2026-09-18_apply.py
  py -m pytest tests/unit/test_live_typography_tokens.py tests/unit/test_live_ajuda_sched_20260915.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Espaço
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
BACKEND = Path("api/routers/live_monitoring.py")
MARK = "_liveSpaceFilter"

RENDER = r"""        // 2026-09-18 (owner): programa Espaco v2 -- filegroups primeiro, seccoes recolhiveis, filtro cruzado ao clicar
        let _liveSpaceOpen = { fg: true, disk: true };
        let _liveSpaceFilter = null;   // { kind: 'fg', db, fg } | { kind: 'disk', drive } | null
        function _liveSpaceToggle(kind, el) { _liveSpaceOpen[kind] = !!el.open; }
        function _liveSpaceClick(kind, a, b, tabId) {
            const mesmo = _liveSpaceFilter && _liveSpaceFilter.kind === kind && (kind === 'disk' ? _liveSpaceFilter.drive === a : (_liveSpaceFilter.db === a && _liveSpaceFilter.fg === b));
            _liveSpaceFilter = mesmo ? null : (kind === 'disk' ? { kind: 'disk', drive: a } : { kind: 'fg', db: a, fg: b });
            const cached = _liveLastData['space'];
            const screen = document.getElementById('live-screen-' + tabId);
            if (cached && screen) _liveRenderAndSet(screen, 'space', cached, tabId);
        }
        window._liveSpaceToggle = _liveSpaceToggle; window._liveSpaceClick = _liveSpaceClick;
        function _liveRenderSpace(data, tabId) {
            tabId = tabId || (document.querySelector('select[id^="live-channel-"]') || { id: 'live-channel-' }).id.replace('live-channel-', '');
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
            const escJs = s => String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
            const disks = data.disks || [], fgs = data.filegroups || [], links = data.links || [];
            if (!disks.length && !fgs.length) return '<div style="color:var(--color-text-tertiary);text-align:center;padding:40px;">' + _kpiT('live.space_no_data', 'Sem dados de filegroups nem de discos para esta instância na última coleta.') + '</div>';
            const norm = s => String(s || '').toLowerCase();
            const fgKey = (db, fg) => norm(db) + '|' + norm(fg);
            const drivesDoFg = {}, fgsDoDrive = {};
            links.forEach(l => { const k = fgKey(l.database, l.filegroup), d = norm(l.drive); (drivesDoFg[k] = drivesDoFg[k] || new Set()).add(d); (fgsDoDrive[d] = fgsDoDrive[d] || new Set()).add(k); });
            const f = _liveSpaceFilter;
            let fgsVis = fgs, disksVis = disks, faixa = '';
            if (f && f.kind === 'fg') {
                const set = drivesDoFg[fgKey(f.db, f.fg)] || new Set();
                disksVis = disks.filter(d => set.has(norm(d.Drive)));
                faixa = `<b>${esc(f.db)} · ${esc(f.fg)}</b> → ${disksVis.length} ${_kpiT('live.space_disks', 'DISCOS').toLowerCase()}`;
            } else if (f && f.kind === 'disk') {
                const set = fgsDoDrive[norm(f.drive)] || new Set();
                fgsVis = fgs.filter(g => set.has(fgKey(g.Database, g.Filegroup)));
                faixa = `<b>${esc(f.drive)}</b> → ${fgsVis.length} ${_kpiT('live.space_filegroups', 'FILEGROUPS').toLowerCase()}`;
            }
            const sevDisk = pf => pf <= 5 ? 'critical' : pf <= 10 ? 'warning' : pf <= 20 ? 'attention' : 'ok';
            const sevFg = ef => ef == null ? 'ok' : ef < 2 ? 'critical' : ef < 5 ? 'warning' : ef < 10 ? 'attention' : 'ok';
            const barra = (pctUsado, sev) => `<div style="display:flex;align-items:center;gap:6px;"><div style="flex:1;height:8px;background:var(--color-bg-sunken);border-radius:4px;overflow:hidden;"><div style="width:${Math.max(0, Math.min(100, pctUsado)).toFixed(1)}%;height:100%;background:var(--sev-${sev}-border);"></div></div><span style="width:52px;text-align:right;color:var(--sev-${sev}-text);font-weight:600;">${pctUsado.toFixed(1)}%</span></div>`;
            const carimbo = (rows) => { const ts = rows.map(r => r.Update_TS || r.update_ts).filter(Boolean).sort().pop(); return ts ? String(ts).replace('T', ' ').substring(0, 19) : ''; };
            const th = 'padding:6px 8px;text-align:left;color:var(--color-text-tertiary);font-weight:600;border-bottom:1px solid var(--color-border);';
            const thR = th + 'text-align:right;';
            const td = 'padding:5px 8px;border-bottom:1px solid var(--color-bg-panel);';
            const tdR = td + 'text-align:right;font-variant-numeric:tabular-nums;';
            const selStyle = 'background:var(--sev-info-tint);outline:1px solid var(--sev-info-text);';
            const cab = (kind, icone, titulo, n, rows) => `<summary style="cursor:pointer;list-style:none;display:flex;align-items:baseline;gap:10px;color:var(--color-text-tertiary);font-size:12px;font-weight:600;margin-bottom:8px;user-select:none;"><i class="fas fa-chevron-${_liveSpaceOpen[kind] ? 'down' : 'right'}" style="width:12px;font-size:12px;" aria-hidden="true"></i><span><i class="fas ${icone}" style="margin-right:6px;color:var(--sev-info-text);"></i>${titulo} (${n})</span><span style="font-weight:400;">${carimbo(rows) ? _kpiT('live.space_collected', 'coleta') + ' ' + esc(carimbo(rows)) : ''}</span></summary>`;
            let h = '';
            if (f) {
                h += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding:6px 10px;background:var(--sev-info-tint);border:1px solid var(--sev-info-text);border-radius:6px;font-size:12px;color:var(--sev-info-text);"><i class="fas fa-filter"></i> ${_kpiT('live.space_filter', 'Filtro')}: ${faixa}`
                   + `<button onclick="_liveSpaceClick('${f.kind}','${escJs(f.kind === 'disk' ? f.drive : f.db)}','${escJs(f.kind === 'disk' ? '' : f.fg)}','${tabId}')" title="${_kpiT('live.space_filter_clear', 'Limpar filtro')}" style="margin-left:auto;background:none;border:1px solid var(--sev-info-text);color:var(--sev-info-text);border-radius:4px;padding:1px 8px;cursor:pointer;font-size:12px;">×</button></div>`;
                if (!links.length) h += `<div style="margin-bottom:10px;font-size:12px;color:var(--color-text-tertiary);">${_kpiT('live.space_no_links', 'Sem relação ficheiro → volume nesta coleta; o filtro não tem efeito.')}</div>`;
            }
            // ---- FILEGROUPS (primeiro) ----
            const eff = g => { const gt = String(g.Growth_Type || '').toUpperCase(); const mx = Number(g.Max_Size_MB || 0), tot = Number(g.Total_MB || 0), used = Number(g.Used_MB || 0);
                if (gt === 'UNLIMITED') return null; if (mx > 0 && mx > tot) return (mx - used) * 100 / mx; return 100 - Number(g.Percent_Used || 0); };
            const ordenados = fgsVis.slice().sort((a, b) => { const ea = eff(a), eb = eff(b); return (ea == null ? 999 : ea) - (eb == null ? 999 : eb); });
            const mostrados = (f && f.kind === 'disk') ? ordenados : ordenados.slice(0, 80);
            h += `<details ${_liveSpaceOpen.fg ? 'open' : ''} ontoggle="_liveSpaceToggle('fg', this)" style="background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;padding:12px;margin-bottom:12px;">`;
            h += cab('fg', 'fa-layer-group', _kpiT('live.space_filegroups', 'FILEGROUPS'), (mostrados.length < fgsVis.length ? mostrados.length + ' / ' : '') + fgsVis.length, fgs);
            if (mostrados.length) {
                h += `<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr><th style="${th}">Database</th><th style="${th}">Filegroup</th><th style="${thR}">Total</th><th style="${thR}">${_kpiT('live.space_used', 'Usado')}</th><th style="${thR}">${_kpiT('live.fleet_space_free', 'livre')}</th><th style="${th}">${_kpiT('live.space_cap', 'Tecto')}</th><th style="${th}">${_kpiT('live.space_files_on', 'Volumes')}</th><th style="${th}width:24%;">% ${_kpiT('live.space_used', 'Usado')}</th></tr></thead><tbody>`;
                mostrados.forEach(g => {
                    const ef = eff(g), sev = sevFg(ef); const gt = String(g.Growth_Type || '').toUpperCase(); const mx = Number(g.Max_Size_MB || 0), tot = Number(g.Total_MB || 0);
                    const tecto = gt === 'UNLIMITED' ? `<span style="color:var(--color-text-tertiary);">${_kpiT('live.space_unlimited', 'ilimitado (disco)')}</span>` : (mx > 0 && mx > tot) ? formatSizeMB(Math.round(mx)) : `<span style="color:var(--color-text-tertiary);">${_kpiT('live.space_capped', 'alocado')}</span>`;
                    const vols = Array.from(drivesDoFg[fgKey(g.Database, g.Filegroup)] || []); const volsTxt = vols.length ? esc(vols.slice(0, 3).join(', ')) + (vols.length > 3 ? ` +${vols.length - 3}` : '') : '';
                    const sel = f && f.kind === 'fg' && norm(f.db) === norm(g.Database) && norm(f.fg) === norm(g.Filegroup);
                    h += `<tr onclick="_liveSpaceClick('fg','${escJs(g.Database)}','${escJs(g.Filegroup)}','${tabId}')" style="cursor:pointer;${sel ? selStyle : ''}" aria-pressed="${sel ? 'true' : 'false'}"><td style="${td}color:var(--color-text-bright);">${esc(g.Database)}</td><td style="${td}font-family:var(--font-mono);">${esc(g.Filegroup)}</td><td style="${tdR}">${formatSizeMB(Math.round(tot))}</td><td style="${tdR}">${formatSizeMB(Math.round(g.Used_MB || 0))}</td><td style="${tdR}color:var(--sev-${sev}-text);font-weight:600;">${formatSizeMB(Math.round(g.Free_MB || 0))}</td><td style="${td}">${tecto}</td><td style="${td}color:var(--color-text-tertiary);font-family:var(--font-mono);">${volsTxt}</td><td style="${td}">${barra(Number(g.Percent_Used || 0), sev)}</td></tr>`;
                });
                h += '</tbody></table>';
            } else {
                h += '<div style="color:var(--color-text-tertiary);font-size:12px;padding:6px 0;">' + _kpiT('live.space_no_fgs', 'Sem dados de filegroups para esta instância.') + '</div>';
            }
            h += '</details>';
            // ---- DISCOS ----
            h += `<details ${_liveSpaceOpen.disk ? 'open' : ''} ontoggle="_liveSpaceToggle('disk', this)" style="background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;padding:12px;">`;
            h += cab('disk', 'fa-hdd', _kpiT('live.space_disks', 'DISCOS'), disksVis.length, disks);
            if (disksVis.length) {
                h += `<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr><th style="${th}">Volume</th><th style="${thR}">Total</th><th style="${thR}">${_kpiT('live.space_used', 'Usado')}</th><th style="${thR}">${_kpiT('live.fleet_space_free', 'livre')}</th><th style="${thR}">${_kpiT('live.space_filegroups', 'FILEGROUPS').toLowerCase()}</th><th style="${th}width:34%;">% ${_kpiT('live.space_used', 'Usado')}</th></tr></thead><tbody>`;
                disksVis.slice().sort((a, b) => (a.Percent_Free || 0) - (b.Percent_Free || 0)).forEach(d => {
                    const pf = Number(d.Percent_Free || 0), sev = sevDisk(pf); const nfg = (fgsDoDrive[norm(d.Drive)] || new Set()).size;
                    const sel = f && f.kind === 'disk' && norm(f.drive) === norm(d.Drive);
                    h += `<tr onclick="_liveSpaceClick('disk','${escJs(d.Drive)}','','${tabId}')" style="cursor:pointer;${sel ? selStyle : ''}" aria-pressed="${sel ? 'true' : 'false'}"><td style="${td}color:var(--color-text-bright);font-family:var(--font-mono);">${esc(d.Drive)}</td><td style="${tdR}">${formatSizeMB(Math.round(d.Total_MB || 0))}</td><td style="${tdR}">${formatSizeMB(Math.round(d.Used_MB || 0))}</td><td style="${tdR}color:var(--sev-${sev}-text);font-weight:600;">${formatSizeMB(Math.round(d.Free_MB || 0))}</td><td style="${tdR}color:var(--color-text-tertiary);">${nfg || ''}</td><td style="${td}">${barra(100 - pf, sev)}</td></tr>`;
                });
                h += '</tbody></table>';
            } else {
                h += '<div style="color:var(--color-text-tertiary);font-size:12px;padding:6px 0;">' + _kpiT('live.space_no_disks', 'Sem dados de disco para esta instância.') + '</div>';
            }
            h += '</details>';
            return h;
        }
"""

EDITS_PORTAL_EXACT = [
    # o dispatch passa o tabId (o render precisa dele para os cliques)
    ("""            if (program === 'space') return _liveRenderSpace(data);""", """            if (program === 'space') return _liveRenderSpace(data, tabId);""", 1),
]

EDITS_BACKEND = [
    ("""    disks = execute_intelligence_query(f\"\"\"
        SELECT d.Drive, d.Total_MB, d.Free_MB, d.Used_MB, d.Percent_Free, d.Update_TS
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_STG d WITH (NOLOCK)
        WHERE d.Instance = '{inst}'
        ORDER BY d.Percent_Free ASC\"\"\", raise_on_error=False) or []
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "filegroups": fgs, "disks": disks,
    })""",
     """    disks = execute_intelligence_query(f\"\"\"
        SELECT d.Drive, d.Total_MB, d.Free_MB, d.Used_MB, d.Percent_Free, d.Update_TS
        FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_STG d WITH (NOLOCK)
        WHERE d.Instance = '{inst}'
        ORDER BY d.Percent_Free ASC\"\"\", raise_on_error=False) or []
    # 2026-09-18 (owner, v2): relacao filegroup <-> volume pelo prefixo mais longo do caminho fisico (Drive na STG e' so' a
    # letra; os discos sao pontos de montagem). Pares distintos (database, filegroup, drive).
    links = []
    try:
        files = execute_intelligence_query(f\"\"\"
            SELECT DISTINCT df.[Database], df.Filegroup, df.Physical_Path, df.Drive
            FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
            WHERE df.Instance = '{inst}'\"\"\", raise_on_error=False) or []
        vols = sorted({str(d.get("Drive") or "") for d in disks if d.get("Drive")}, key=len, reverse=True)
        vols_l = [(v, v.lower()) for v in vols]
        vistos = set()
        for fl in files:
            path = str(fl.get("Physical_Path") or "").lower()
            alvo = next((v for v, vl in vols_l if vl and path.startswith(vl)), None)
            if alvo is None:
                letra = str(fl.get("Drive") or "")
                alvo = next((v for v, vl in vols_l if vl == letra.lower()), None)
            if not alvo:
                continue
            k = (fl.get("Database"), fl.get("Filegroup"), alvo)
            if k not in vistos:
                vistos.add(k); links.append({"database": k[0], "filegroup": k[1], "drive": k[2]})
    except Exception:
        links = []
    return _live_json({
        "instance": instance, "timestamp": time.time(),
        "filegroups": fgs, "disks": disks, "links": links,
    })""", 1),
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


def _substituir_render(portal):
    eol = "\r\n" if "\r\n" in portal else "\n"
    ini = "        // 2026-09-18 (owner): programa Espaco -- filegroups e discos da instancia (ultima coleta do coletor, STG)" + eol
    fim = "        function _liveRenderIO(data) {"
    if portal.count(ini) != 1 or portal.count(fim) != 1:
        raise SystemExit("[ABORT] bloco do _liveRenderSpace nao encontrado 1x")
    a, b = portal.index(ini), portal.index(fim)
    if not (a < b < a + 20000):
        raise SystemExit("[ABORT] bloco do _liveRenderSpace com forma inesperada")
    return portal[:a] + RENDER.replace("\n", eol) + portal[b:]


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    portal_p, back_p = base / PORTAL, base / BACKEND
    portal = portal_p.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "_liveRenderSpace" not in portal:
        print("[ABORT] LIVE_PROGRAMA_ESPACO nao esta aplicado (aplicar primeiro)"); return 1
    novo_portal = _apply(_substituir_render(portal), EDITS_PORTAL_EXACT, "portal")
    novo_back = None
    if back_p.exists():
        back = back_p.read_bytes().decode("utf-8")
        if '"links": links' in back:
            print("[ABORT] backend ja aplicado"); return 1
        novo_back = _apply(back, EDITS_BACKEND, "backend")
    print("[ok] portal: _liveRenderSpace v2 (filegroups primeiro, <details>, filtro cruzado) + dispatch com tabId; backend: links por prefixo do caminho" + ("" if novo_back else " (ausente: saltado)"))
    if check:
        print("--check OK. Nada escrito."); return 0
    portal_p.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    if novo_back is not None:
        back_p.write_bytes(novo_back.encode("utf-8")); print(f"[write] {BACKEND}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Espaco.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
