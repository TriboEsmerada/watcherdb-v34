"""
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
