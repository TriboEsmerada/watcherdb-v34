# -*- coding: utf-8 -*-
"""Contrato 2026-09-11 -- drill "Acompanhar resume" Always On (api/routers/queries/alwayson_resume.py).

async_execute_on_server mockado (molde: test_tlog_diagnosis_20260902.py). Sem BD.
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routers.queries import alwayson_resume as ar

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 11, 15, 0, 0)


def _row(**kw):
    base = {"sampled_on": "PRD01\\I01", "server_now": NOW, "ag_name": "AG1", "replica_server": "PRD01\\I01",
            "role_desc": "SECONDARY", "connected_state_desc": "CONNECTED", "availability_mode_desc": "SYNCHRONOUS_COMMIT",
            "replica_sync_health": "HEALTHY", "is_local": 0, "db_sync_state": "SYNCHRONIZED", "db_sync_health": "HEALTHY",
            "database_state_desc": None, "is_suspended": 0, "suspend_reason_desc": None,
            "log_send_queue_size": 0, "log_send_rate": 0, "redo_queue_size": 0, "redo_rate": 0,
            "last_commit_time": NOW, "last_hardened_time": NOW, "last_redone_time": NOW, "secondary_lag_seconds": None}
    base.update(kw)
    return base


# ---- state_code: precedencia ------------------------------------------------
def test_suspended_wins_even_with_zero_queues():
    assert ar.state_code(_row(is_suspended=1, db_sync_state="SYNCHRONIZED")) == "SUSPENDED"


@pytest.mark.parametrize("state,code", [("REVERTING", "REVERTING"), ("INITIALIZING", "INITIALIZING"),
                                        ("NOT SYNCHRONIZING", "NOT_SYNC"), ("SYNCHRONIZED", "SYNCED")])
def test_state_mapping(state, code):
    assert ar.state_code(_row(db_sync_state=state)) == code


def test_sync_replica_synchronizing_is_syncing_even_with_empty_queues():
    assert ar.state_code(_row(db_sync_state="SYNCHRONIZING", log_send_queue_size=0, redo_queue_size=0)) == "SYNCING"


def test_async_replica_never_synced_but_healthy_when_drained():
    r = _row(availability_mode_desc="ASYNCHRONOUS_COMMIT", db_sync_state="SYNCHRONIZING", log_send_queue_size=10, redo_queue_size=20)
    assert ar.state_code(r) == "ASYNC_HEALTHY"
    r["redo_queue_size"] = 14014220
    assert ar.state_code(r) == "SYNCING"


def test_primary_row_code():
    assert ar.state_code(_row(role_desc="PRIMARY", is_local=1)) == "PRIMARY"


# ---- lag ----------------------------------------------------------------------
def test_lag_prefers_secondary_lag_seconds_then_commit_delta():
    assert ar.lag_seconds(NOW, _row(secondary_lag_seconds=7)) == 7
    assert ar.lag_seconds(NOW, _row(last_commit_time=NOW - timedelta(seconds=90))) == 90
    assert ar.lag_seconds(None, _row()) is None


# ---- query ----------------------------------------------------------------------
def test_query_escapes_and_lag_column_only_when_detected():
    q = ar.q_sample("AG'1", "Db'X", has_lag=False)
    assert "N'AG''1'" in q and "N'Db''X'" in q and "CAST(NULL AS BIGINT) AS secondary_lag_seconds" in q
    assert "drs.secondary_lag_seconds," in ar.q_sample("AG1", "DbX", has_lag=True)


# ---- endpoint -------------------------------------------------------------------
def _run(coro):
    return asyncio.run(coro)  # 3.14: get_event_loop() sem loop corrente levanta RuntimeError


def _exec_factory(by_server, has_lag=1, calls=None, primary="PRD01\\I01"):
    async def fake(server_id, query, database="master", timeout_s=0):
        if calls is not None:
            calls.append((server_id, timeout_s))
        if "sys.all_columns" in query:
            return [{"has_lag": has_lag}]
        if "primary_replica" in query:
            return [{"primary_replica": primary}] if primary else []
        return by_server.get(server_id, [])
    return fake


def test_invalid_names_are_400(monkeypatch):
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({}))
    for ag, db in (("AG1]", "DbX"), ("AG1", "Db;X"), ("AG'1", "Db\"X")):
        with pytest.raises(HTTPException) as ei:
            _run(ar.alwayson_resume_sample("PRD01_I01", ag=ag, db=db))
        assert ei.value.status_code == 400


def test_primary_sample_shapes_replicas_and_uses_timeout(monkeypatch):
    calls = []
    rows = [_row(role_desc="PRIMARY", is_local=1, replica_server="PRD01\\I01", last_commit_time=NOW),
            _row(replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", log_send_queue_size=0, redo_queue_size=14014220,
                 redo_rate=3678, last_commit_time=NOW - timedelta(seconds=600))]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD01_I01": rows}, calls=calls))
    out = _run(ar.alwayson_resume_sample("PRD01_I01", ag="AG1", db="DbX"))
    assert out["success"] and out["sampled_on"] == "PRD01\\I01" and out["hops"] == []
    sec = [r for r in out["replicas"] if r["role"] == "SECONDARY"][0]
    assert sec["state_code"] == "SYNCING" and sec["redo_queue_kb"] == 14014220 and sec["lag_seconds"] == 600
    assert sec["source"] == "primary" and out["defaults"]["done_queue_kb"] == 64
    assert all(t == ar.TIMEOUT_S for _, t in calls)


def test_secondary_server_is_retargeted_to_primary(monkeypatch):
    # numa secundaria so' existe a linha LOCAL (medido no SQLHDSPRD405): a primaria vem de primary_replica
    sec_view = [_row(role_desc="SECONDARY", is_local=1, replica_server="PRD02\\I01", sampled_on="PRD02\\I01")]
    pri_view = [_row(role_desc="PRIMARY", is_local=1, replica_server="PRD01\\I01", sampled_on="PRD01\\I01"),
                _row(role_desc="SECONDARY", replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", redo_queue_size=500)]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD02_I01": sec_view, "PRD01_I01": pri_view}))
    out = _run(ar.alwayson_resume_sample("PRD02_I01", ag="AG1", db="DbX"))
    assert out["sampled_on"] == "PRD01\\I01" and out["hops"] == ["PRD01_I01"] and out["primary"] == "PRD01\\I01"


def test_secondary_fallback_fills_null_redo(monkeypatch):
    pri = [_row(role_desc="PRIMARY", is_local=1, replica_server="PRD01\\I01"),
           _row(replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", redo_queue_size=None, redo_rate=None, database_state_desc=None)]
    sec_local = [_row(role_desc="SECONDARY", is_local=1, replica_server="PRD02\\I01", db_sync_state="SYNCHRONIZING", redo_queue_size=777, redo_rate=9, database_state_desc="ONLINE")]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD01_I01": pri, "PRD02_I01": sec_local}))
    out = _run(ar.alwayson_resume_sample("PRD01_I01", ag="AG1", db="DbX"))
    sec = [r for r in out["replicas"] if r["replica_server"] == "PRD02\\I01"][0]
    assert sec["redo_queue_kb"] == 777 and sec["database_state"] == "ONLINE" and sec["source"] == "secondary_fallback"


def test_not_found_and_not_primary_paths(monkeypatch):
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({}))
    with pytest.raises(HTTPException) as ei:
        _run(ar.alwayson_resume_sample("PRD01_I01", ag="AG1", db="DbX"))
    assert ei.value.status_code == 404
    only_sec = [_row(role_desc="SECONDARY", is_local=1)]
    monkeypatch.setattr(ar, "async_execute_on_server", _exec_factory({"PRD02_I01": only_sec}, primary=None))
    with pytest.raises(HTTPException) as ei2:
        _run(ar.alwayson_resume_sample("PRD02_I01", ag="AG1", db="DbX"))
    assert ei2.value.status_code == 409


# ---- portal (estatico) -----------------------------------------------------------
def test_portal_button_in_both_tables_and_kb_threshold_fixed():
    portal = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
    assert portal.count("_agResumeBtn(") >= 3  # definicao + 2 tabelas
    assert "window._AG_QUEUE_WARN_KB = 51200" in portal
    assert "> 1000) return true; // Filas > 1GB" not in portal
    assert "alwayson-resume-sample/" in portal and "function openAgResume(" in portal


def test_i18n_keys_present_in_three_locales():
    import json
    for loc in ("pt", "en", "es"):
        data = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        res = data["alwayson"]["resume"]
        for k in ("title", "button", "state_SUSPENDED", "state_ASYNC_HEALTHY", "stalled_note", "completed_async"):
            assert res.get(k), f"{loc}: falta alwayson.resume.{k}"

def test_lot2_suspended_is_not_stalled_and_tiles_have_help():
    portal = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
    assert "const suspended = last.code === 'SUSPENDED';" in portal
    assert "['SYNCING', 'NOT_SYNC', 'INITIALIZING', 'REVERTING'].indexOf(last.code) >= 0" in portal
    assert "slope < -1 ? 'draining' : (slope > 1 ? 'growing' : 'stable')" in portal
    assert "function _agResumeSpark(" in portal and "createDiskSparklineSVG(vals, 560" not in portal
    assert "toLocaleString('pt-PT'" not in portal.split("function _agResumeIngest")[1].split("// ---- Vista Avancada RICA")[0]
    assert "${r.operational_state ?? 'N/A'}" in portal and "Redo Queue (KB)" in portal
    for hk in ("help_state", "help_send", "help_redo", "help_rate", "help_eta", "help_progress", "help_chart", "help_resume_cmd"):
        assert "'" + hk + "'" in portal, f"falta o ? de ajuda {hk}"
    assert "SET HADR RESUME;" in portal
    import json
    for loc in ("pt", "en", "es"):
        res = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["alwayson"]["resume"]
        for k in ("trend_stable", "help_rate", "reason_SUSPEND_FROM_REDO", "resume_cmd_note", "progress_suspended"):
            assert res.get(k), f"{loc}: falta alwayson.resume.{k}"

