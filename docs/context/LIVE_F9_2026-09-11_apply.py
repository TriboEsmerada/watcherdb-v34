# -*- coding: utf-8 -*-
"""LIVE F9 (2026-09-11, GO do owner) -- 5 achados de UX do teste completo ao painel LIVE.

  1. Filtro de instancia deixava a instancia seleccionada fora da lista (select mostrava o placeholder,
     polling continuava nela) -> a seleccionada aparece sempre, numa optgroup "Seleccionada" no topo.
  2. Barra vermelha de dirty pages usava o buffer do proprio banco como 100% (281 MB de dirty a 61% da
     barra ao lado de 10,6 GB a 100%) -> mesma escala da barra azul (maior buffer da lista).
  3. Plan Cache com DB vazia -> dm_exec_sql_text.dbid e' NULL em planos ad hoc/preparados (medido:
     20/20 nulos em CAGENPRD06, 13/20 em SQLHDSGENPRD01); o dbid dos atributos do plano preenche
     todos menos 2 (+75 ms). Backend: COALESCE com dm_exec_plan_attributes; front: "(ad hoc)" quando nulo.
  4. Fuga de idioma: 19 literais PT/EN crus no bloco LIVE (incl. tooltips das gauges meio-migrados e
     "Error log vazio", achados do frontend-specialist) passam a 23 chaves live.* (pt-PT com acentos, en, es).
  5. Reabrir o LIVE perdia programa e intervalo (so' a instancia persistia) -> os tres persistem.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/LIVE_F9_2026-09-11_apply.py --check
  py docs/context/LIVE_F9_2026-09-11_apply.py
  py -m pytest tests/unit/test_live_f9_20260911.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "router": Path("api/routers/live_monitoring.py"),
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_live_f9_20260911.py"),
}
MARK = "live-last-program"

R_EDITS = [
    ("    DB_NAME(qt.dbid) AS database_name,\n",
     "    COALESCE(DB_NAME(qt.dbid), DB_NAME(CAST(pa.value AS INT))) AS database_name,  -- 2026-09-11 F9: qt.dbid e' NULL em ad hoc/preparados\n", 1),
    ("CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt\nORDER BY qs.total_worker_time DESC;\n",
     "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt\n"
     "OUTER APPLY (SELECT TOP 1 value FROM sys.dm_exec_plan_attributes(qs.plan_handle) WHERE attribute = 'dbid') pa\n"
     "ORDER BY qs.total_worker_time DESC;\n", 1),
]

P_EDITS = [
    # 1) filtro: a instancia seleccionada aparece sempre
    ("""            const q = (filter || '').toLowerCase();
            sel.innerHTML = '<option value="">' + t('live.channel_placeholder') + '</option>';
            for (const [env, instances] of Object.entries(byEnv)) {""",
     """            const q = (filter || '').toLowerCase();
            sel.innerHTML = '<option value="">' + t('live.channel_placeholder') + '</option>';
            let _currentShown = false;  // 2026-09-11 F9: a seleccionada nunca cai fora da lista
            for (const [env, instances] of Object.entries(byEnv)) {""", 1),
    ("""                    if (inst.instance === current) opt.selected = true;
                    group.appendChild(opt);
                });
                sel.appendChild(group);
            }
        }
""",
     """                    if (inst.instance === current) { opt.selected = true; _currentShown = true; }
                    group.appendChild(opt);
                });
                sel.appendChild(group);
            }
            if (current && !_currentShown) {
                // filtrada para fora: fica visivel numa optgroup propria no topo, para o select dizer a
                // verdade sobre onde o polling esta a bater (antes mostrava "Canal..." com dados a chegar)
                let _desc = '';
                for (const instances of Object.values(byEnv)) { const hit = instances.find(i => i.instance === current); if (hit) { _desc = hit.description || ''; break; } }
                const pinned = document.createElement('optgroup');
                pinned.label = t('live.selected_group');
                const opt = document.createElement('option');
                opt.value = current;
                opt.textContent = current + (_desc ? ' — ' + _desc : '');
                opt.selected = true;
                pinned.appendChild(opt);
                sel.insertBefore(pinned, sel.options[0].nextSibling);
            }
        }
""", 1),
    # 2) dirty na mesma escala
    ("                    const dirtyPct = b.buffer_mb > 0 ? (b.dirty_mb / b.buffer_mb * 100).toFixed(0) : 0;\n",
     "                    const dirtyPct = ((b.dirty_mb || 0) / maxBuf * 100).toFixed(0);  // 2026-09-11 F9: mesma escala da barra azul (maior buffer)\n", 1),
    # 3) plan cache: (ad hoc) quando nao ha base
    ("""<td style="padding:4px 8px;color:var(--color-text-tertiary);">${q.database_name||''}</td>""",
     """<td style="padding:4px 8px;color:var(--color-text-tertiary);">${q.database_name || t('live.adhoc_plan')}</td>""", 1),
    # 4) fuga de idioma
    ("""<button onclick="liveTvResize('small')" title="Reduzir" """,
     """<button onclick="liveTvResize('small')" title="${t('live.btn_reduce')}" """, 1),
    ("""<button onclick="liveTvResize('normal')" title="Tamanho normal" """,
     """<button onclick="liveTvResize('normal')" title="${t('live.btn_normal')}" """, 1),
    ("""<button onclick="liveTvResize('full')" title="Tela inteira" """,
     """<button onclick="liveTvResize('full')" title="${t('live.btn_fullscreen')}" """, 1),
    ("""            if (btn) btn.innerHTML = _livePaused ? '&#9654; Play' : '&#9208; Pause';
            const status = document.getElementById('live-status-' + tabId);
            if (status) status.textContent = _livePaused ? 'PAUSADO' : '';""",
     """            if (btn) btn.innerHTML = _livePaused ? '&#9654; ' + t('live.play') : '&#9208; ' + t('live.pause');
            const status = document.getElementById('live-status-' + tabId);
            if (status) status.textContent = _livePaused ? t('live.paused') : '';""", 1),
    ("""            _liveShowLoading(tabId, 'A conectar a ' + instance + '...');""",
     """            _liveShowLoading(tabId, _kpiTp('live.connecting', 'A ligar a {instance}…', { instance }));""", 1),
    ("""                        <div style="font-size:12px;">Programa: ${_liveProgram} | Erro: ${errCode}</div>""",
     """                        <div style="font-size:12px;">${_kpiTp('live.program_error', 'Programa: {program} | Erro: {code}', { program: _liveProgram, code: errCode })}</div>""", 1),
    ("""                if (status) { status.textContent = 'Erro'; status.style.color = '#ef4444'; }""",
     """                if (status) { status.textContent = t('live.error_short'); status.style.color = '#ef4444'; }""", 1),
    ("""            return '<div style="color:var(--color-text-disabled);">Programa nao implementado</div>';""",
     """            return '<div style="color:var(--color-text-disabled);">' + t('live.program_not_implemented') + '</div>';""", 1),
    ("""            return `<div style="margin-bottom:8px;color:var(--color-text-tertiary);font-size:12px;">${queries.length} queries em execucao</div>${h}`;""",
     """            return `<div style="margin-bottom:8px;color:var(--color-text-tertiary);font-size:12px;">${_kpiTp('live.running_queries_count', '{n} queries em execução', { n: queries.length })}</div>${h}`;""", 1),
    ("""            let h = `<div style="margin-bottom:8px;color:var(--color-text-tertiary);font-size:12px;">${conns.length} conexoes</div>`;""",
     """            let h = `<div style="margin-bottom:8px;color:var(--color-text-tertiary);font-size:12px;">${_kpiTp('live.connections_count', '{n} conexões', { n: conns.length })}</div>`;""", 1),
    ("""<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">A colectar dados da fleet...</div>""",
     """<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">' + t('live.collecting_fleet') + '</div>""", 1),
    ("""<div style="font-weight:600;margin-bottom:8px;color:var(--color-text-tertiary);">Buffer Pool por Database</div>""",
     """<div style="font-weight:600;margin-bottom:8px;color:var(--color-text-tertiary);">' + t('live.buffer_pool_by_db') + '</div>""", 1),
    ("""<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">Plan cache vazio</div>""",
     """<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">' + t('live.plan_cache_empty') + '</div>""", 1),
    # 4b) achados do frontend-specialist: tooltips das gauges meio-migrados e "Error log vazio"
    ("""<span title="CPU do SQL Server. >70%=atencao, >90%=critico">CPU: """,
     """<span title="${t('live.gauge_cpu_tip')}">CPU: """, 1),
    ("""<span title="Memoria OS. >85%=atencao, >95%=critico">Mem: """,
     """<span title="${t('live.gauge_mem_tip')}">Mem: """, 1),
    ("""<span title="Page Life Expectancy. <300=critico">PLE: """,
     """<span title="${t('live.gauge_ple_tip')}">PLE: """, 1),
    ("""<span title="Batch Requests/sec">Batch/s: """,
     """<span title="${t('live.gauge_batch_tip')}">Batch/s: """, 1),
    ("""<span title="Queries em execucao">Qry: """,
     """<span title="${t('live.gauge_qry_tip')}">Qry: """, 1),
    ("""<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">Error log vazio</div>""",
     """<div style="color:var(--color-text-disabled);text-align:center;padding:40px;">' + t('live.error_log_empty') + '</div>""", 1),
    # 5) persistencia de programa e intervalo
    ("""        function liveSetProgram(tabId, program) {
            _liveProgram = program;
""",
     """        function liveSetProgram(tabId, program) {
            _liveProgram = program;
            try { localStorage.setItem('live-last-program', program); } catch (e) {}  // 2026-09-11 F9
""", 1),
    ("""        function liveChangeRate(tabId, rate) {
            _liveRefreshRate = parseInt(rate);
""",
     """        function liveChangeRate(tabId, rate) {
            _liveRefreshRate = parseInt(rate);
            try { localStorage.setItem('live-last-rate', String(_liveRefreshRate)); } catch (e) {}  // 2026-09-11 F9
""", 1),
    ("""            setTimeout(() => liveSetProgram(tabId, 'fleet'), 100);
            _liveLoadChannels(tabId);
""",
     """            // 2026-09-11 F9: reabrir lembra o intervalo e o programa, nao so' a instancia
            let _savedRate = NaN, _savedProg = 'fleet';
            try { _savedRate = parseInt(localStorage.getItem('live-last-rate') || '', 10); _savedProg = localStorage.getItem('live-last-program') || 'fleet'; } catch (e) {}
            if ([5000, 10000, 15000, 30000].includes(_savedRate)) {
                _liveRefreshRate = _savedRate;
                const _rs = document.getElementById('live-rate-' + tabId);
                if (_rs) _rs.value = String(_savedRate);
            }
            if (!document.querySelector('.live-prog-btn[data-prog="' + _savedProg + '"]')) _savedProg = 'fleet';
            _liveProgram = _savedProg;  // sincrono, antes do fetch dos canais: sem flash do programa anterior (parecer frontend)
            setTimeout(() => liveSetProgram(tabId, _savedProg), 100);
            _liveLoadChannels(tabId);
""", 1),
]

NEW_KEYS = {
    "pt": {
        "selected_group": "Selecionada",
        "adhoc_plan": "(ad hoc)",
        "btn_reduce": "Reduzir",
        "btn_normal": "Tamanho normal",
        "btn_fullscreen": "Ecrã inteiro",
        "play": "Retomar",
        "pause": "Pausa",
        "paused": "EM PAUSA",
        "connecting": "A ligar a {instance}…",
        "program_error": "Programa: {program} | Erro: {code}",
        "error_short": "Erro",
        "program_not_implemented": "Programa não implementado",
        "running_queries_count": "{n} queries em execução",
        "connections_count": "{n} conexões",
        "collecting_fleet": "A recolher dados da frota…",
        "buffer_pool_by_db": "Buffer Pool por base de dados",
        "plan_cache_empty": "Plan cache vazia",
        "error_log_empty": "Error log vazio",
        "gauge_cpu_tip": "CPU do SQL Server. >70% = atenção, >90% = crítico",
        "gauge_mem_tip": "Memória do SO. >85% = atenção, >95% = crítico",
        "gauge_ple_tip": "Page Life Expectancy. <300 s = crítico",
        "gauge_batch_tip": "Batch Requests/s",
        "gauge_qry_tip": "Queries em execução",
    },
    "en": {
        "selected_group": "Selected",
        "adhoc_plan": "(ad hoc)",
        "btn_reduce": "Reduce",
        "btn_normal": "Normal size",
        "btn_fullscreen": "Full screen",
        "play": "Resume",
        "pause": "Pause",
        "paused": "PAUSED",
        "connecting": "Connecting to {instance}…",
        "program_error": "Program: {program} | Error: {code}",
        "error_short": "Error",
        "program_not_implemented": "Program not implemented",
        "running_queries_count": "{n} running queries",
        "connections_count": "{n} connections",
        "collecting_fleet": "Collecting fleet data…",
        "buffer_pool_by_db": "Buffer Pool by database",
        "plan_cache_empty": "Plan cache is empty",
        "error_log_empty": "Error log is empty",
        "gauge_cpu_tip": "SQL Server CPU. >70% = warning, >90% = critical",
        "gauge_mem_tip": "OS memory. >85% = warning, >95% = critical",
        "gauge_ple_tip": "Page Life Expectancy. <300 s = critical",
        "gauge_batch_tip": "Batch Requests/s",
        "gauge_qry_tip": "Running queries",
    },
    "es": {
        "selected_group": "Seleccionada",
        "adhoc_plan": "(ad hoc)",
        "btn_reduce": "Reducir",
        "btn_normal": "Tamaño normal",
        "btn_fullscreen": "Pantalla completa",
        "play": "Reanudar",
        "pause": "Pausa",
        "paused": "EN PAUSA",
        "connecting": "Conectando a {instance}…",
        "program_error": "Programa: {program} | Error: {code}",
        "error_short": "Error",
        "program_not_implemented": "Programa no implementado",
        "running_queries_count": "{n} consultas en ejecución",
        "connections_count": "{n} conexiones",
        "collecting_fleet": "Recopilando datos de la flota…",
        "buffer_pool_by_db": "Buffer Pool por base de datos",
        "plan_cache_empty": "Plan cache vacía",
        "error_log_empty": "Error log vacío",
        "gauge_cpu_tip": "CPU de SQL Server. >70% = atención, >90% = crítico",
        "gauge_mem_tip": "Memoria del SO. >85% = atención, >95% = crítico",
        "gauge_ple_tip": "Page Life Expectancy. <300 s = crítico",
        "gauge_batch_tip": "Batch Requests/s",
        "gauge_qry_tip": "Consultas en ejecución",
    },
}
I18N_ANCHOR = {
    "pt": '    "error_http": "Erro HTTP {code}",\n',
    "en": '    "error_http": "HTTP error {code}",\n',
    "es": '    "error_http": "Error HTTP {code}",\n',
}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE F9: cinco acertos de UX do teste completo do owner (11/09)** — o filtro de instância deixava a\n"
                  "  seleccionada fora da lista com o polling a continuar nela (passa a aparecer sempre, em optgroup\n"
                  "  \"Selecionada\"); a barra vermelha de dirty pages usava o buffer do próprio banco como 100% e gritava um\n"
                  "  problema inexistente (mesma escala da barra azul); o Plan Cache tinha a coluna DB vazia porque o dbid do\n"
                  "  texto SQL é nulo em planos ad hoc (dbid dos atributos do plano, \"(ad hoc)\" quando continua nulo); 19\n"
                  "  literais em português cru (\"PAUSADO\", \"N queries em execucao\", tooltips do cabeçalho e das gauges…) passam a chaves\n"
                  "  `live.*` em pt-PT, en e es; e reabrir o LIVE lembra o programa e o intervalo, não só a instância. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-11 -- LIVE F9: filtro, escala do dirty, DB do plan cache, idioma, persistencia.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "api" / "routers" / "live_monitoring.py").read_text(encoding="utf-8")
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
LIVE = PORTAL[PORTAL.index("let _liveInstance = null;"):PORTAL.index("function _liveRenderSchedulers")]

NEW_KEYS = ["selected_group", "adhoc_plan", "btn_reduce", "btn_normal", "btn_fullscreen", "play", "pause", "paused",
            "connecting", "program_error", "error_short", "program_not_implemented", "running_queries_count",
            "connections_count", "collecting_fleet", "buffer_pool_by_db", "plan_cache_empty", "error_log_empty",
            "gauge_cpu_tip", "gauge_mem_tip", "gauge_ple_tip", "gauge_batch_tip", "gauge_qry_tip"]


def test_plan_cache_dbid_falls_back_to_plan_attributes():
    sql = re.search(r'PLANCACHE_SQL = """(.*?)"""', ROUTER, re.S).group(1)
    assert "COALESCE(DB_NAME(qt.dbid), DB_NAME(CAST(pa.value AS INT)))" in sql
    assert "sys.dm_exec_plan_attributes(qs.plan_handle) WHERE attribute = 'dbid'" in sql


def test_filter_keeps_selected_instance_visible():
    assert "let _currentShown = false;" in LIVE
    assert "pinned.label = t('live.selected_group');" in LIVE
    assert "sel.insertBefore(pinned, sel.options[0].nextSibling);" in LIVE


def test_dirty_bar_uses_same_scale_as_buffer_bar():
    assert "const dirtyPct = ((b.dirty_mb || 0) / maxBuf * 100).toFixed(0);" in LIVE
    assert "b.dirty_mb / b.buffer_mb" not in LIVE


def test_plan_cache_shows_adhoc_label():
    assert "${q.database_name || t('live.adhoc_plan')}" in LIVE


def test_no_raw_portuguese_literals_left_in_live_block():
    for lit in ("'PAUSADO'", "queries em execucao", "} conexoes<", "'A conectar a '", "Programa nao implementado",
                'title="Reduzir"', 'title="Tamanho normal"', 'title="Tela inteira"', "A colectar dados da fleet",
                "Buffer Pool por Database", ">Plan cache vazio<", "'&#9654; Play'", ">Error log vazio<",
                'title="CPU do SQL Server', 'title="Memoria OS', 'title="Queries em execucao"'):
        assert lit not in LIVE, lit
    assert "_liveProgram = _savedProg;" in LIVE  # restauro sincrono antes do fetch dos canais


def test_program_and_rate_persist():
    assert "localStorage.setItem('live-last-program', program)" in LIVE
    assert "localStorage.setItem('live-last-rate', String(_liveRefreshRate))" in LIVE
    assert "setTimeout(() => liveSetProgram(tabId, _savedProg), 100);" in LIVE
    assert "setTimeout(() => liveSetProgram(tabId, 'fleet'), 100);" not in LIVE


def test_new_keys_in_three_locales_with_placeholders():
    for loc in ("pt", "en", "es"):
        live = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["live"]
        for k in NEW_KEYS:
            assert k in live and live[k], (loc, k)
        assert "{instance}" in live["connecting"] and "{n}" in live["connections_count"]
        assert "{program}" in live["program_error"] and "{code}" in live["program_error"]
    pt = json.loads((ROOT / "static" / "i18n" / "pt.json").read_text(encoding="utf-8"))["live"]
    assert pt["running_queries_count"] == "{n} queries em execução" and pt["connections_count"] == "{n} conexões"
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:100]!r}")
        text = text.replace(o, n)
    return text


def _i18n_block(loc):
    lines = "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in NEW_KEYS[loc].items())
    return I18N_ANCHOR[loc] + lines


import json  # noqa: E402  (usado em _i18n_block)


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal_raw = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal_raw:
        print("[ABORT] ja aplicado (portal tem live-last-program)"); return 1
    out = {
        "router": _apply(src["router"].read_bytes().decode("utf-8"), R_EDITS, "router"),
        "portal": _apply(portal_raw, P_EDITS, "portal"),
    }
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        for k in NEW_KEYS[loc]:
            if f'"{k}":' in raw.split('"live": {', 1)[1].split("\n  }", 1)[0]:
                raise SystemExit(f"[ABORT] {loc}: chave live.{k} ja existe")
        out[loc] = _apply(raw, [(I18N_ANCHOR[loc], _i18n_block(loc), 1)], loc)
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print(f"[ok] anchors: router {len(R_EDITS)}; portal {len(P_EDITS)}; i18n {len(NEW_KEYS['pt'])} chaves x3; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_f9_20260911.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
