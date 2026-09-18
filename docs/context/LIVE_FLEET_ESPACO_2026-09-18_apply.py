# -*- coding: utf-8 -*-
"""LIVE Fleet: sem medidores de instância no Fleet + painel "Espaço crítico (frota)" no vazio à direita (owner, 18/09).

 1. Medidores CPU/Mem/PLE/Batch/Sess/Qry/Blk são de UMA instância (o canal escolhido); no Fleet não fazem sentido.
    Ficam escondidos quando o programa é o Fleet e voltam nos outros programas. A hora do último refresh mantém-se.
 2. O espaço vazio ao lado de QUERIES PESADAS passa a "Espaço crítico (frota)": filegroups e discos já acima de 90% de
    uso, ORDENADOS PELO ESPAÇO LIVRE (menos livre primeiro), com % usado, livre / total e badge (>=98% crítico,
    >=95% aviso, >=90% atenção). Regra pedida pelo owner: 98% com 22 GB livres é mais crítico do que 99% com 80 GB —
    entre os que já estão em risco, decide o que falta, não a percentagem. Clique na linha abre o canal da instância
    no programa I/O. O filtro por card também se aplica a este painel.
    Fonte: KPI_MSSQL_FG_USAGE_STG com a MESMA regra do KPI de filegroups (Growth_Type UNLIMITED excluído por ser
    disk-bound; % livre efectiva até ao Max_Size quando existe; < 10% entra) e KPI_MSSQL_DISK_USAGE_STG (Percent_Free
    <= 10, Free_MB, Total_MB, Drive) — colunas confirmadas em INFORMATION_SCHEMA em 18/09. Sem isto, filegroups de
    0,0 GB a 100% com autogrowth inundavam a lista (visto na 1.ª prova). O endpoint do fleet passa a devolver
    space_risk (top 12) via execute_intelligence_query (WatcherDB_Intelligence, sql_monitoring, SELECT). Falha da
    consulta = painel com estado vazio, nunca erro no Fleet.

Texto novo por _kpiT(chave, fallback): live.fleet_space_title, live.fleet_space_empty, live.fleet_space_free (entram no lote i18n).

Ficheiros: templates/watcherdb_portal.html (liveSetProgram, _liveRenderFleet, helper _fleetSpacePanel) e api/routers/live_monitoring.py.
RAMO: o mesmo do LIVE_FLEET_UX (requer-o aplicado).

Uso (raiz do repo):
  py docs/context/LIVE_FLEET_ESPACO_2026-09-18_apply.py --check
  py docs/context/LIVE_FLEET_ESPACO_2026-09-18_apply.py
  py -m pytest tests/unit/test_live_f9b_20260911.py tests/unit/test_live_legivel_20260915.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
BACKEND = Path("api/routers/live_monitoring.py")
MARK = "_fleetSpacePanel"

EDITS_PORTAL = [
    # 1. medidores escondidos no Fleet
    ("""        function liveSetProgram(tabId, program) {
            _liveProgram = program;
""", """        function liveSetProgram(tabId, program) {
            _liveProgram = program;
            // 2026-09-18 (owner): os medidores sao de uma instancia; no Fleet ficam escondidos (a hora do refresh fica)
            const _gauges = document.getElementById('live-gauges-' + tabId);
            if (_gauges) _gauges.querySelectorAll(':scope > span:not([id^="live-status-"])').forEach(s => { s.style.display = program === 'fleet' ? 'none' : ''; });
""", 1),
    # 2. painel no vazio a direita das queries (fecha o painel das queries, abre o novo, fecha a grelha)
    ("""            h += '</div></div>';

            if (liveBlocking.length) {""",
     """            h += '</div>';
            h += _fleetSpacePanel(soFiltro(data.space_risk));   // 2026-09-18 (owner): espaco critico da frota no vazio a direita
            h += '</div>';

            if (liveBlocking.length) {""", 1),
    ("""        window._fleetCopySql = _fleetCopySql;""",
     """        window._fleetCopySql = _fleetCopySql;
        // 2026-09-18 (owner): filegroups e discos >= 90% usados, ordenados por espaco livre (menos livre primeiro)
        function _fleetSpacePanel(rows) {
            rows = (rows || []).slice().sort((a, b) => (a.free_mb || 0) - (b.free_mb || 0)).slice(0, 8);
            let h = '<div style="background:var(--color-bg-panel);border:1px solid var(--color-border);border-radius:8px;padding:12px;">';
            h += '<div style="color:var(--color-text-tertiary);font-size:12px;font-weight:600;margin-bottom:8px;"><i class="fas fa-hdd" style="margin-right:6px;color:var(--sev-critical-text);"></i>' + _kpiT('live.fleet_space_title', 'ESPAÇO CRÍTICO (frota)') + '</div>';
            if (!rows.length) {
                return h + '<div style="color:var(--sev-ok-text);font-size:12px;text-align:center;padding:10px;"><i class="fas fa-check-circle" style="margin-right:4px;"></i>' + _kpiT('live.fleet_space_empty', 'Sem filegroups nem discos acima de 90%') + '</div></div>';
            }
            const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
            rows.forEach(r => {
                const pct = Number(r.pct_used || 0);
                const sev = pct >= 98 ? 'critical' : pct >= 95 ? 'warning' : 'attention';
                const obj = r.kind === 'disk' ? esc(r.object) : esc(r.database) + ' · ' + esc(r.object);
                const inst = esc(r.instance || '');
                const tip = `${inst} — ${obj}: ${pct.toFixed(1)}% · ${_kpiT('live.fleet_space_free', 'livre')} ${Math.round(r.free_mb || 0)} MB / ${Math.round(r.total_mb || 0)} MB`;
                h += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;padding:2px 0;border-bottom:1px solid var(--color-bg-sunken);cursor:pointer;" onclick="_fleetSwitchTo('${inst}','io')" title="${tip}">`
                   + `<div style="width:120px;flex-shrink:0;color:var(--color-text-link);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${inst}</div>`
                   + `<i class="fas ${r.kind === 'disk' ? 'fa-hdd' : 'fa-layer-group'}" style="color:var(--color-text-tertiary);font-size:12px;flex-shrink:0;" aria-hidden="true"></i>`
                   + `<div style="flex:1;min-width:0;color:var(--color-text-secondary);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--font-mono);">${obj}</div>`
                   + `<div style="width:46px;flex-shrink:0;text-align:right;color:var(--sev-${sev}-text);font-size:12px;font-weight:600;">${pct.toFixed(1)}%</div>`
                   + `<div style="width:130px;flex-shrink:0;text-align:right;color:var(--color-text-tertiary);font-size:12px;white-space:nowrap;"><b style="color:var(--sev-${sev}-text);">${formatSizeMB(Math.round(r.free_mb || 0))}</b> / ${formatSizeMB(Math.round(r.total_mb || 0))}</div>`
                   + `<span style="flex-shrink:0;background:var(--sev-${sev}-tint);color:var(--sev-${sev}-text);padding:1px 6px;border-radius:4px;font-size:12px;font-weight:700;">${r.kind === 'disk' ? 'DISK' : 'FG'}</span></div>`;
            });
            return h + '</div>';
        }""", 1),
    # grelhas do Fleet: 1fr 1fr deixava o painel da esquerda alargar pelo min-content e cortar o da direita
    ("""'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">'""",
     """'<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-bottom:12px;">'""", 3),
]

EDITS_BACKEND = [
    ("""from api.error_helpers import safe_http_error
""", """from api.error_helpers import safe_http_error
from api.routers.intelligence.helpers import execute_intelligence_query, INTELLIGENCE_SCHEMA   # 2026-09-18: espaco critico da frota (Fleet)
""", 1),
    ("""    live_ag_queues.sort(key=lambda x: -((x.get("send_queue_kb") or 0) + (x.get("redo_queue_kb") or 0)))
    live_idle.sort(key=lambda x: -(x.get("idle_minutes") or 0))

    return _live_json({
        "timestamp": time.time(),
""", """    live_ag_queues.sort(key=lambda x: -((x.get("send_queue_kb") or 0) + (x.get("redo_queue_kb") or 0)))
    live_idle.sort(key=lambda x: -(x.get("idle_minutes") or 0))

    # 2026-09-18 (owner): espaco critico da frota -- filegroups e discos >= 90% usados, ordenados pelo espaco livre
    # (menos livre primeiro). Fonte: STG do WatcherDB_Intelligence (sql_monitoring, SELECT). Falha => lista vazia.
    space_risk = []
    try:
        space_risk = execute_intelligence_query(f\"\"\"
            SELECT TOP 12 kind, instance, [database], [object], pct_used, free_mb, total_mb FROM (
                -- mesma regra do KPI de filegroups (helpers.collect_filegroup_usage): UNLIMITED sai (e' disk-bound, o
                -- disco cobre-o); com Max_Size acima do alocado conta o espaco ate ao tecto; senao o livre do alocado
                SELECT 'fg' AS kind, g.instance, g.[database], g.[object],
                       CAST(100.0 - g.eff_free_pct AS float) AS pct_used, CAST(g.eff_free_mb AS float) AS free_mb, CAST(g.eff_total_mb AS float) AS total_mb
                FROM (
                    SELECT f.Instance AS instance, f.[Database] AS [database], f.Filegroup AS [object],
                           CASE WHEN ISNULL(f.Max_Size_MB, 0) > 0 AND f.Max_Size_MB > f.Total_MB
                                THEN (f.Max_Size_MB - f.Used_MB) * 100.0 / NULLIF(f.Max_Size_MB, 0)
                                ELSE 100.0 - f.Percent_Used END AS eff_free_pct,
                           CASE WHEN ISNULL(f.Max_Size_MB, 0) > 0 AND f.Max_Size_MB > f.Total_MB THEN f.Max_Size_MB - f.Used_MB ELSE f.Free_MB END AS eff_free_mb,
                           CASE WHEN ISNULL(f.Max_Size_MB, 0) > 0 AND f.Max_Size_MB > f.Total_MB THEN f.Max_Size_MB ELSE f.Total_MB END AS eff_total_mb
                    FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
                    WHERE ISNULL(f.Growth_Type, '') <> 'UNLIMITED' AND f.Percent_Used > 80
                ) g
                WHERE g.eff_free_pct < 10
                UNION ALL
                SELECT 'disk', d.Instance, NULL, d.Drive,
                       CAST(100 - d.Percent_Free AS float), CAST(d.Free_MB AS float), CAST(d.Total_MB AS float)
                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DISK_USAGE_STG d WITH (NOLOCK)
                WHERE d.Percent_Free <= 10
            ) x
            ORDER BY free_mb ASC, pct_used DESC\"\"\", raise_on_error=False) or []
    except Exception:
        space_risk = []

    return _live_json({
        "timestamp": time.time(),
        "space_risk": space_risk,
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
    if "_fleetToggleFilter" not in portal:
        print("[ABORT] LIVE_FLEET_UX nao esta aplicado (aplicar primeiro)"); return 1
    novo_portal = _apply(portal, EDITS_PORTAL, "portal")
    novo_back = None
    if back_p.exists():
        back = back_p.read_bytes().decode("utf-8")
        if "space_risk" in back:
            print("[ABORT] backend ja aplicado"); return 1
        novo_back = _apply(back, EDITS_BACKEND, "backend")
    print(f"[ok] portal: {len(EDITS_PORTAL)} blocos (medidores no Fleet, painel espaco critico, grelhas minmax); backend: {len(EDITS_BACKEND)} blocos" + ("" if novo_back else " (ausente na copia: saltado)"))
    if check:
        print("--check OK. Nada escrito."); return 0
    portal_p.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    if novo_back is not None:
        back_p.write_bytes(novo_back.encode("utf-8")); print(f"[write] {BACKEND}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > Fleet.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
