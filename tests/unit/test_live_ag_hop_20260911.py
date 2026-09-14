"""
2026-09-11 -- LIVE alwayson: numa secundaria as linhas vem da primaria (hop), sem nunca dar 503 pelo salto.
"""
import asyncio
import json
from pathlib import Path

from api.routers import live_monitoring as lm

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def _local_rows():
    return [{"ag_name": "AG1", "replica_server_name": "HOSTB\\I01", "role_desc": "SECONDARY", "database_name": "DB1",
             "commit_lag_sec": None, "last_commit_time": None}]


def _primary_rows():
    return [{"ag_name": "AG1", "replica_server_name": "HOSTA\\I01", "role_desc": "PRIMARY", "database_name": "DB1", "commit_lag_sec": 0},
            {"ag_name": "AG1", "replica_server_name": "HOSTB\\I01", "role_desc": "SECONDARY", "database_name": "DB1", "commit_lag_sec": 42},
            {"ag_name": "OTHER", "replica_server_name": "HOSTA\\I01", "role_desc": "PRIMARY", "database_name": "X", "commit_lag_sec": 0}]


def test_norm_and_sid():
    assert lm._ag_norm("hosta.dom.local\\i01,1433") == "HOSTA\\I01"
    assert lm._ag_norm("HOSTA") == "HOSTA"
    assert lm._ag_sid("HOSTA\\I01") == "HOSTA_I01"


def test_secondary_hops_to_primary(monkeypatch):
    calls = []

    def fake(instance, sql, database="master", timeout=10):
        calls.append((instance, "PRIM" if "local_server" in sql else "AG", timeout))
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": "HOSTA\\I01", "local_server": "HOSTB\\I01"}], None
        if instance == "HOSTA_I01":
            return _primary_rows(), None
        return _local_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    body = json.loads(lm.get_alwayson_live("HOSTB_I01")).body)
    assert body["hops"] == [{"ag": "AG1", "primary": "HOSTA\\I01", "server_id": "HOSTA_I01"}]
    names = sorted((r["replica_server_name"], r["role_desc"]) for r in body["replicas"])
    assert names == [("HOSTA\\I01", "PRIMARY"), ("HOSTB\\I01", "SECONDARY")]  # OTHER (AG nao local) fica de fora
    assert [r for r in body["replicas"] if r["role_desc"] == "SECONDARY"][0]["commit_lag_sec"] == 42
    assert ("HOSTA_I01", "AG", lm.AG_HOP_TIMEOUT_S) in calls


def test_primary_does_not_hop(monkeypatch):
    def fake(instance, sql, database="master", timeout=10):
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": "HOSTA\\I01", "local_server": "hosta\\i01"}], None
        return _primary_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    body = json.loads(lm.get_alwayson_live("HOSTA_I01")).body)
    assert body["hops"] == [] and len(body["replicas"]) == 3


def test_hop_failure_keeps_local_rows_with_note(monkeypatch):
    def fake(instance, sql, database="master", timeout=10):
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": "HOSTA\\I01", "local_server": "HOSTB\\I01"}], None
        if instance == "HOSTA_I01":
            return None, "Sem conexao a HOSTA_I01"
        return _local_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    resp = lm.get_alwayson_live("HOSTB_I01"))
    body = json.loads(resp.body)
    assert resp.status_code == 200 and body["hops"] == []
    assert body["replicas"] == _local_rows() and any("HOSTA_I01" in n for n in body["notes"])


def test_unknown_primary_keeps_local_rows(monkeypatch):
    def fake(instance, sql, database="master", timeout=10):
        if "local_server" in sql:  # ALWAYSON_SQL menciona is_primary_replica num comentario
            return [{"ag_name": "AG1", "primary_replica": None, "local_server": "HOSTB\\I01"}], None
        return _local_rows(), None

    monkeypatch.setattr(lm, "_query_instance", fake)
    body = json.loads(lm.get_alwayson_live("HOSTB_I01")).body)
    assert body["hops"] == [] and body["replicas"] == _local_rows() and body["notes"]


def test_endpoint_is_sync_so_fastapi_uses_threadpool():
    import inspect
    assert not inspect.iscoroutinefunction(lm.get_alwayson_live)  # pyodbc sincrono + ate' 3 round-trips


def test_local_query_error_still_503(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(lm, "_query_instance", lambda *a, **k: (None, "boom"))
    with pytest.raises(HTTPException) as ei:
        lm.get_alwayson_live("HOSTB_I01"))
    assert ei.value.status_code == 503


def test_portal_shows_where_data_came_from():
    assert "_kpiTp('live.ag_from_primary'" in PORTAL
    assert "let h = _hopNote + '<table" in PORTAL
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert "{primary}" in d["live"]["ag_from_primary"], loc
