# -*- coding: utf-8 -*-
"""FIX 2026-09-11 -- painel LIVE: 4 canais por instancia partidos no backend + falso "tudo limpo" no front.

Medido pelo owner (3 instancias) e reproduzido por SELECT via sql_monitoring (CAGENPRD06 = 2016 SP2,
SQLHDSGENPRD01 = 2022):

  /live/{inst}/io        503 "Incorrect syntax near 'with'" (319)  -> hint WITH (NOLOCK) numa funcao de tabela
                                                                     (sys.dm_io_virtual_file_stats). NAO e' CTE.
  /live/{inst}/tlog      503 319 (2016) / 102 near ')' (2022)      -> mesmo hint em sys.dm_db_log_stats(NULL);
                                                                     e dm_db_log_stats(NULL) devolve 0 linhas em 2016.
  /live/{inst}/alwayson  503 "Invalid column name 'database_name'" -> sys.dm_hadr_database_replica_states nao tem essa
                                                                     coluna; vem de sys.availability_databases_cluster.
                                                                     De caminho: commit_lag_sec era DATEDIFF ate GETDATE()
                                                                     (base ociosa ficava vermelha) -> delta face a primaria.
  /live/{inst}/tempdb    500 sem detail (SQLHDSPRD405)             -> "Object of type Decimal is not JSON serializable"
                                                                     (1024.0 em TEMPDB_ACTIVE_USAGE_SQL, so' com uso activo).
                                                                     Fix estrutural: jsonable_encoder em TODAS as respostas.
  Front: sem instancia, clicar num programa nao pede nada e deixa o render anterior (pode ser um check verde
         "No running queries") e o carimbo congela -> estado neutro "Selecione uma instancia" + status '--';
         no erro HTTP o status mostra o codigo a vermelho; lag do AG NULL mostra n/d em vez de 0 verde.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/FIX_LIVE_CANAIS_2026-09-11_apply.py --check
  py docs/context/FIX_LIVE_CANAIS_2026-09-11_apply.py
  py -m pytest tests/unit/test_live_channels_20260911.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; LIVE > instancia > IO / TLog / AG / TempDB
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
    "test": Path("tests/unit/test_live_channels_20260911.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **LIVE: quatro canais por instância voltam a responder e o painel deixa de fingir \"tudo limpo\"**\n"
                  "  (owner 11/09, teste em 3 instâncias; consenso sql-deep-reviewer + frontend-specialist). `io` e `tlog`\n"
                  "  davam 503 por um `WITH (NOLOCK)` numa função de tabela (erro 319/102 — não era CTE); `tlog` escondia\n"
                  "  ainda colunas que `sys.dm_db_log_stats` não tem e devolvia 0 linhas em 2016 SP2 (passa a CROSS APPLY\n"
                  "  sobre `sys.databases`, só ONLINE e sem snapshots; provado numa secundária não legível); `alwayson` dava 207\n"
                  "  porque `database_name` vem de `sys.availability_databases_cluster`, e o \"lag\" media o tempo desde a\n"
                  "  última escrita — passa ao delta entre o commit da primária e o da réplica (2012-safe, NULL quando a linha\n"
                  "  da primária não é visível); o mesmo 207 estava engolido no resumo de saúde (`ag_queues` nunca vinha);\n"
                  "  `tempdb` dava 500 puro por um Decimal — todas as respostas do LIVE passam por `jsonable_encoder`\n"
                  "  (Decimal, datetime, bytes em hex). No portal: sem instância, um programa mostra \"Selecione uma instância\"\n"
                  "  em vez do render anterior (podia ser um check verde sem pedido nenhum), o carimbo volta a `--`, um erro\n"
                  "  HTTP fica escrito a vermelho no carimbo, uma resposta tardia não reescreve um estado que já mudou, e o\n"
                  "  lag do AG nulo mostra `n/d` em vez de 0 verde. 3 chaves `live.*` em pt/en/es. [tier: Std]\n"
                  "\n", 1)
MARK = "_live_json("  # idempotencia

# ----------------------------------------------------------------------------- router
R_EDITS = [
    # 1) helper JSON seguro (Decimal/datetime/bytes) + import
    ("from fastapi.responses import JSONResponse\n",
     "from fastapi.responses import JSONResponse\n"
     "from fastapi.encoders import jsonable_encoder\n", 1),
    ("logger = logging.getLogger(__name__)\n",
     "logger = logging.getLogger(__name__)\n"
     "\n"
     "\n"
     "def _live_json(payload, status_code: int = 200):\n"
     "    \"\"\"JSONResponse com Decimal/datetime/bytes seguros.\n"
     "\n"
     "    2026-09-11: /live/{inst}/tempdb dava 500 puro (\"Object of type Decimal is not JSON\n"
     "    serializable\") sempre que TEMPDB_ACTIVE_USAGE_SQL tinha linhas -- o 1024.0 devolve\n"
     "    Decimal. Em vez de caçar coluna a coluna, todas as respostas do LIVE passam por aqui.\n"
     "    \"\"\"\n"
     "    return JSONResponse(status_code=status_code,\n"
     "                        content=jsonable_encoder(payload, custom_encoder={bytes: lambda b: b.hex()}))\n", 1),
    # 1b) health summary: o MESMO 207 (drs.database_name) engolido por except: pass -- ag_queues nunca vinha
    ("                    SELECT ag.name AS ag_name, ar.replica_server_name,\n"
     "                        drs.database_name, drs.synchronization_state_desc,\n",
     "                    SELECT ag.name AS ag_name, ar.replica_server_name,\n"
     "                        adc.database_name, drs.synchronization_state_desc,\n", 1),
    ("                    JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK) ON ar.replica_id = drs.replica_id\n"
     "                    WHERE drs.log_send_queue_size > 1024 OR drs.redo_queue_size > 1024\n",
     "                    JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK) ON ar.replica_id = drs.replica_id\n"
     "                    LEFT JOIN sys.availability_databases_cluster adc WITH (NOLOCK) ON adc.group_database_id = drs.group_database_id\n"
     "                    WHERE drs.log_send_queue_size > 1024 OR drs.redo_queue_size > 1024\n", 1),
    # 2) IO: hint numa TVF e' erro de sintaxe (319) em todas as versoes
    ("FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs WITH (NOLOCK)\n",
     "FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs  -- sem hint: WITH (NOLOCK) numa TVF = erro 319 (2026-09-11)\n", 1),
    # 3) TLOG 2016 SP2+: sem hint, e por CROSS APPLY (dm_db_log_stats(NULL) devolve 0 linhas em 2016)
    ('''TLOG_SQL = """
SET NOCOUNT ON;
SELECT
    DB_NAME(database_id) AS database_name,
    total_vlf_count AS vlf_count,
    active_vlf_count AS active_vlfs,
    CAST(log_space_in_bytes_since_last_backup / 1048576.0 AS DECIMAL(18,1)) AS log_since_backup_mb,
    log_truncation_holdup_reason AS truncation_reason,
    log_reuse_wait_desc AS reuse_wait
FROM sys.dm_db_log_stats(NULL) WITH (NOLOCK)
WHERE database_id > 4
ORDER BY total_vlf_count DESC;
"""
''',
     '''TLOG_SQL = """
SET NOCOUNT ON;
-- 2026-09-11: sem WITH (NOLOCK) na TVF (erro 319/102) e por CROSS APPLY em sys.databases:
-- dm_db_log_stats(NULL) devolve 0 linhas em 2016 SP2 (medido em CAGENPRD06). So' bases ONLINE e
-- sem snapshots. O 319 escondia um 207: dm_db_log_stats NAO tem log_reuse_wait_desc (vem de
-- sys.databases) nem log_space_in_bytes_since_last_backup (a coluna e' log_since_last_log_backup_mb).
SELECT
    d.name AS database_name,
    ls.total_vlf_count AS vlf_count,
    ls.active_vlf_count AS active_vlfs,
    CAST(ls.log_since_last_log_backup_mb AS FLOAT) AS log_since_backup_mb,
    ls.log_truncation_holdup_reason AS truncation_reason,
    d.log_reuse_wait_desc AS reuse_wait
FROM sys.databases d WITH (NOLOCK)
CROSS APPLY sys.dm_db_log_stats(d.database_id) ls
WHERE d.database_id > 4 AND d.state = 0 AND d.source_database_id IS NULL
ORDER BY ls.total_vlf_count DESC;
"""
''', 1),
    # 4) ALWAYSON: nome da base vem de availability_databases_cluster; lag = delta face a primaria
    ('''ALWAYSON_SQL = """
SET NOCOUNT ON;
SELECT
    ag.name AS ag_name,
    ar.replica_server_name,
    ars.role_desc,
    ars.connected_state_desc,
    ars.synchronization_health_desc,
    drs.database_name,
    drs.synchronization_state_desc,
    drs.log_send_queue_size AS send_queue_kb,
    drs.redo_queue_size AS redo_queue_kb,
    drs.log_send_rate AS send_rate_kb_sec,
    drs.redo_rate AS redo_rate_kb_sec,
    drs.last_commit_time,
    DATEDIFF(SECOND, drs.last_commit_time, GETDATE()) AS commit_lag_sec,
    drs.is_suspended,
    drs.suspend_reason_desc
FROM sys.availability_groups ag WITH (NOLOCK)
JOIN sys.availability_replicas ar WITH (NOLOCK) ON ag.group_id = ar.group_id
JOIN sys.dm_hadr_availability_replica_states ars WITH (NOLOCK) ON ar.replica_id = ars.replica_id
LEFT JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK) ON ar.replica_id = drs.replica_id
ORDER BY ag.name, ar.replica_server_name, drs.database_name;
"""
''',
     '''ALWAYSON_SQL = """
SET NOCOUNT ON;
-- 2026-09-11: dm_hadr_database_replica_states NAO tem database_name (erro 207) -- vem de
-- sys.availability_databases_cluster por group_database_id. E o lag deixa de ser DATEDIFF ate
-- GETDATE() (media "tempo desde a ultima escrita": base ociosa ficava vermelha): passa a ser o
-- delta entre o last_commit_time da primaria e o da replica. NULL quando a linha da primaria
-- nao e' visivel (numa secundaria a DMV so' devolve a linha local -- facto medido a 11/09).
SELECT
    ag.name AS ag_name,
    ar.replica_server_name,
    ars.role_desc,
    ars.connected_state_desc,
    ars.synchronization_health_desc,
    adc.database_name,
    drs.synchronization_state_desc,
    drs.log_send_queue_size AS send_queue_kb,
    drs.redo_queue_size AS redo_queue_kb,
    drs.log_send_rate AS send_rate_kb_sec,
    drs.redo_rate AS redo_rate_kb_sec,
    drs.last_commit_time,
    CASE WHEN ars.role = 1 THEN 0
         WHEN drs.last_commit_time IS NULL OR pc.primary_commit IS NULL THEN NULL
         ELSE DATEDIFF(SECOND, drs.last_commit_time, pc.primary_commit) END AS commit_lag_sec,
    drs.is_suspended,
    drs.suspend_reason_desc
FROM sys.availability_groups ag WITH (NOLOCK)
JOIN sys.availability_replicas ar WITH (NOLOCK) ON ag.group_id = ar.group_id
JOIN sys.dm_hadr_availability_replica_states ars WITH (NOLOCK) ON ar.replica_id = ars.replica_id
LEFT JOIN sys.dm_hadr_database_replica_states drs WITH (NOLOCK) ON ar.replica_id = drs.replica_id
LEFT JOIN sys.availability_databases_cluster adc WITH (NOLOCK) ON adc.group_database_id = drs.group_database_id
OUTER APPLY (SELECT MAX(p.last_commit_time) AS primary_commit
             FROM sys.dm_hadr_database_replica_states p WITH (NOLOCK)
             JOIN sys.dm_hadr_availability_replica_states pa WITH (NOLOCK) ON pa.replica_id = p.replica_id AND pa.role = 1
             WHERE p.group_database_id = drs.group_database_id) pc  -- ars.role/pa.role: 2012-safe (is_primary_replica e' 2014+; ha' 4 x 2012 na frota)
ORDER BY ag.name, ar.replica_server_name, adc.database_name;
"""
''', 1),
    # 5) todas as respostas passam pelo helper (17 sitios)
    ("JSONResponse(content=", "_live_json(", 17),
]

# ----------------------------------------------------------------------------- portal
P_EDITS = [
    # a) estado neutro reutilizavel + liveChangeChannel sem instancia
    ('''        function liveChangeChannel(tabId, instance) {
            _liveInstance = instance;
            localStorage.setItem('live-last-channel', instance);
            if (_liveInterval) { clearInterval(_liveInterval); _liveInterval = null; }
            _liveWaitsPrev = null;
            for (const k in _liveGaugeHistory) delete _liveGaugeHistory[k];
            if (!instance) return;
''',
     '''        // 2026-09-11: sem instancia, um programa por instancia NAO pode mostrar o render anterior
        // (podia ser um check verde "No running queries" sem pedido nenhum) nem manter o carimbo
        // do ultimo refresh. Estado neutro, status '--', sem intervalo.
        function _liveShowNoInstance(tabId, program) {
            if (_liveInterval) { clearInterval(_liveInterval); _liveInterval = null; }
            const screen = document.getElementById('live-screen-' + tabId);
            if (screen) screen.innerHTML = `<div style="text-align:center;padding:60px 20px;color:var(--color-text-disabled);">
                <i class="fas fa-satellite-dish" style="font-size:48px;margin-bottom:16px;color:var(--color-border);display:block;"></i>
                <div style="font-size:16px;margin-bottom:8px;">${_diagEsc(program ? _kpiTp('live.select_instance_for_program', 'Selecione uma instância para ver {program}', { program }) : t('live.select_channel'))}</div>
            </div>`;
            const status = document.getElementById('live-status-' + tabId);
            if (status) { status.textContent = '--'; status.style.color = 'var(--color-text-disabled)'; }
            ['cpu','mem','ple','batch','sess','qry','blk'].forEach(g => { const el = document.getElementById('lg-' + g + '-' + tabId); if (el) { el.textContent = '--'; el.style.color = 'var(--color-text-bright)'; } });
        }

        function liveChangeChannel(tabId, instance) {
            _liveInstance = instance;
            localStorage.setItem('live-last-channel', instance);
            if (_liveInterval) { clearInterval(_liveInterval); _liveInterval = null; }
            _liveWaitsPrev = null;
            for (const k in _liveGaugeHistory) delete _liveGaugeHistory[k];
            if (!instance) { if (_liveProgram !== 'fleet') _liveShowNoInstance(tabId, null); return; }
''', 1),
    # a2) resposta tardia nao reescreve um estado que ja mudou (achado do frontend-specialist)
    ('''            try {
                const isFleet = _liveProgram === 'fleet';
''',
     '''            const _instAtCall = _liveInstance, _progAtCall = _liveProgram;  // 2026-09-11: guarda de corrida
            try {
                const isFleet = _liveProgram === 'fleet';
''', 1),
    ('''                const responses = await Promise.all(promises);
''',
     '''                const responses = await Promise.all(promises);
                if (_instAtCall !== _liveInstance || _progAtCall !== _liveProgram) return;  // canal/programa mudou entretanto
''', 1),
    # b) liveSetProgram sem instancia
    ('''                _liveShowLoading(tabId, label);
                _liveRefresh(tabId);
                if (!_liveInterval) {
                    _liveInterval = setInterval(() => { if (!_livePaused) _liveRefresh(tabId); }, _liveRefreshRate);
                }
            }
        }
''',
     '''                _liveShowLoading(tabId, label);
                _liveRefresh(tabId);
                if (!_liveInterval) {
                    _liveInterval = setInterval(() => { if (!_livePaused) _liveRefresh(tabId); }, _liveRefreshRate);
                }
            } else {
                _liveShowNoInstance(tabId, program);  // 2026-09-11: nunca deixar o render anterior no ecrã
            }
        }
''', 1),
    # c) erro HTTP: o carimbo diz o erro em vez de manter o ultimo horario verde
    ('''                    let errMsg = t('live.no_data');
                    if (errCode === 503) errMsg = t('live.instance_unavailable');
''',
     '''                    let errMsg = t('live.no_data');
                    if (errCode === 503) errMsg = t('live.instance_unavailable');
                    if (status) { status.textContent = _kpiTp('live.error_http', 'Erro HTTP {code}', { code: errCode }); status.style.color = '#ef4444'; }  // 2026-09-11
''', 1),
    # e) lag do AG pode vir NULL (sem linha da primaria): n/d, nao 0 verde
    ('''                h += `<td style="padding:4px 8px;text-align:right;color:${(r.commit_lag_sec||0)>30?'#ef4444':'#10b981'};">${r.commit_lag_sec||0}</td></tr>`;
''',
     '''                const _lag = (r.commit_lag_sec === null || r.commit_lag_sec === undefined) ? null : Number(r.commit_lag_sec);  // 2026-09-11: NULL = sem linha da primária
                // suspensa: o lag so' cresce quando a primária commita -- a cor sai primeiro do estado, depois do lag
                h += `<td style="padding:4px 8px;text-align:right;color:${_lag === null ? 'var(--color-text-disabled)' : r.is_suspended ? '#f59e0b' : _lag > 30 ? '#ef4444' : '#10b981'};">${_lag === null ? 'n/d' : _lag}</td></tr>`;
''', 1),
]

# ----------------------------------------------------------------------------- i18n
I18N = {
    "pt": ('    "no_ags": "Sem AGs configurados",\n',
           '    "no_ags": "Sem AGs configurados",\n    "select_instance_for_program": "Selecione uma instância no Canal para ver {program}",\n    "error_http": "Erro HTTP {code}",\n'),
    "en": ('    "no_ags": "No AGs configured",\n',
           '    "no_ags": "No AGs configured",\n    "select_instance_for_program": "Select an instance in Channel to view {program}",\n    "error_http": "HTTP error {code}",\n'),
    "es": ('    "no_ags": "Sin AGs configurados",\n',
           '    "no_ags": "Sin AGs configurados",\n    "select_instance_for_program": "Seleccione una instancia en Canal para ver {program}",\n    "error_http": "Error HTTP {code}",\n'),
}

TEST_SRC = r'''"""
2026-09-11 -- painel LIVE: 4 canais por instancia (io, tlog, alwayson, tempdb) + falso "tudo limpo" sem instancia.
"""
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = ROOT / "api" / "routers" / "live_monitoring.py"
ROUTER = ROUTER_PATH.read_text(encoding="utf-8")
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def _sql_const(name):
    m = re.search(name + r' = """(.*?)"""', ROUTER, re.S)
    assert m, name
    # sem comentarios T-SQL: os comentarios explicam o bug antigo e citam as colunas erradas
    return "\n".join(line.split("--", 1)[0] for line in m.group(1).splitlines())


def test_no_table_hint_on_table_valued_functions():
    # WITH (NOLOCK) a seguir a uma chamada de funcao (...) e' erro 319/102 em todas as versoes
    assert not re.search(r"\)\s*(AS\s+)?\w*\s*WITH \(NOLOCK\)", _sql_const("IO_STATS_SQL"))
    assert not re.search(r"dm_db_log_stats\([^)]*\)\s*WITH", _sql_const("TLOG_SQL"))
    assert "CROSS APPLY sys.dm_db_log_stats(d.database_id) ls" in _sql_const("TLOG_SQL")
    assert "d.state = 0" in _sql_const("TLOG_SQL")


def test_alwayson_database_name_from_availability_databases_cluster():
    sql = _sql_const("ALWAYSON_SQL")
    assert "drs.database_name" not in ROUTER  # inclui o health summary (ag_queues), que engolia o 207
    assert "adc.database_name" in sql
    assert "sys.availability_databases_cluster adc" in sql
    # lag face a primaria, nunca ate GETDATE(); e 2012-safe (role, nao is_primary_replica)
    assert "DATEDIFF(SECOND, drs.last_commit_time, GETDATE())" not in sql
    assert "is_primary_replica" not in sql
    assert "pa.role = 1" in sql and "CASE WHEN ars.role = 1 THEN 0" in sql


def test_tlog_uses_real_dm_db_log_stats_columns():
    sql = _sql_const("TLOG_SQL")
    assert "log_space_in_bytes_since_last_backup" not in sql and "ls.log_reuse_wait_desc" not in sql
    assert "ls.log_since_last_log_backup_mb" in sql and "d.log_reuse_wait_desc AS reuse_wait" in sql
    assert "d.source_database_id IS NULL" in sql


def test_all_live_responses_go_through_safe_json():
    assert "JSONResponse(content=" not in ROUTER  # o helper usa status_code= primeiro, de proposito
    assert "custom_encoder={bytes: lambda b: b.hex()}" in ROUTER
    assert ROUTER.count("_live_json(") >= 18  # 17 sitios + a definicao


def test_live_json_serialises_decimal_datetime_and_bytes():
    import datetime as dt
    from api.routers import live_monitoring as lm
    resp = lm._live_json({"x": Decimal("1.5"), "t": dt.datetime(2026, 9, 11, 18, 7, 33), "n": None, "h": b"\x0a\xff"})
    body = json.loads(resp.body)
    assert body["x"] == 1.5 and body["t"].startswith("2026-09-11T18:07:33") and body["n"] is None and body["h"] == "0aff"
    assert resp.status_code == 200


def test_tlog_falls_back_to_legacy_when_dm_db_log_stats_missing(monkeypatch):
    import asyncio
    from api.routers import live_monitoring as lm
    calls = []

    def fake_query(instance, sql, database="master", timeout=10):
        calls.append(sql)
        if "dm_db_log_stats" in sql:
            return None, "Invalid object name 'sys.dm_db_log_stats'."
        return [{"database_name": "X", "reuse_wait": "NOTHING", "log_size_mb": 10, "log_used_mb": Decimal("2.5")}], None

    monkeypatch.setattr(lm, "_query_instance", fake_query)
    resp = asyncio.run(lm.get_tlog_live("SRV"))  # asyncio.run: py 3.14 sem get_event_loop implicito
    assert len(calls) == 2 and "FILEPROPERTY" in calls[1]
    assert json.loads(resp.body)["databases"][0]["log_used_mb"] == 2.5


def test_portal_neutral_state_without_instance():
    assert "function _liveShowNoInstance(tabId, program)" in PORTAL
    assert "_liveShowNoInstance(tabId, program);  // 2026-09-11" in PORTAL
    assert "if (!instance) { if (_liveProgram !== 'fleet') _liveShowNoInstance(tabId, null); return; }" in PORTAL
    assert "_kpiTp('live.error_http', 'Erro HTTP {code}', { code: errCode })" in PORTAL
    assert "${r.commit_lag_sec||0}" not in PORTAL
    assert "if (_instAtCall !== _liveInstance || _progAtCall !== _liveProgram) return;" in PORTAL


def test_i18n_keys_in_three_locales():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert "{program}" in d["live"]["select_instance_for_program"], loc
        assert "{code}" in d["live"]["error_http"], loc
'''


def _apply(text: str, edits, label: str) -> str:
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
    src = {k: (base / p) for k, p in REL.items()}

    router_raw = src["router"].read_bytes().decode("utf-8")
    if MARK in router_raw:
        print("[ABORT] ja aplicado (router tem _live_json)"); return 1
    out = {}
    out["router"] = _apply(router_raw, R_EDITS, "router")
    out["portal"] = _apply(src["portal"].read_bytes().decode("utf-8"), P_EDITS, "portal")
    for loc, (old, new) in I18N.items():
        out[loc] = _apply(src[loc].read_bytes().decode("utf-8"), [(old, new, 1)], loc)
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    else:
        print("[skip] changelog nao existe nesta copia")
    print("[ok] anchors: router 7 blocos + 17 respostas; portal 6 blocos; i18n pt/en/es; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].parent.mkdir(parents=True, exist_ok=True)
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_live_channels_20260911.py -q --no-cov ; py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
