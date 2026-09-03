"""
Testes do services/inventory_repo.py (E6 do plano servers.json fonte unica, 2026-08-19)

Impacto se falhar: sidebar/endpoints de servidores vazios, password a vazar no
retorno, fallback ao ficheiro nao funciona quando a BD cai, cache nao expira.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services import inventory_repo as mod


ROWS_SRV = [
    {"server_id": 1, "instance_id": "A_I01", "host": "A", "instance_name": "I01", "port": 1433,
     "environment": "production", "priority": 1, "description": "Srv A", "enabled": 1, "is_active": 1,
     "has_alwayson": 0, "ag_name": None, "ag_listener": None, "sql_servername_alias": None,
     "last_seen_in_source_at": None, "updated_at": None},
    {"server_id": 2, "instance_id": "B_I01", "host": "B", "instance_name": None, "port": None,
     "environment": "quality", "priority": None, "description": None, "enabled": 0, "is_active": 1,
     "has_alwayson": 1, "ag_name": "AG1", "ag_listener": "lst", "sql_servername_alias": None,
     "last_seen_in_source_at": None, "updated_at": None},
]
ROWS_DB = [
    {"server_id": 1, "database_name": "master", "database_id": 1, "state": "ONLINE", "recovery_model": "SIMPLE",
     "is_read_only": 0, "is_accessible": 1, "compatibility_level": 160, "last_seen_in_source_at": None},
    {"server_id": 1, "database_name": "AppDB", "database_id": 5, "state": "ONLINE", "recovery_model": "FULL",
     "is_read_only": False, "is_accessible": True, "compatibility_level": 150, "last_seen_in_source_at": None},
]


class TestRowsToEntries:
    def test_shape_matches_servers_json_contract(self):
        out = mod.rows_to_entries(ROWS_SRV, ROWS_DB)
        a = out[0]
        assert a["id"] == "A_I01" and a["host"] == "A" and a["instance"] == "I01" and a["port"] == 1433
        assert a["environment"] == "production" and a["enabled"] is True and a["description"] == "Srv A"
        assert a["database_count"] == 2 and [d["name"] for d in a["databases"]] == ["master", "AppDB"]
        assert a["_source"] == "db"
        b = out[1]
        assert b["instance"] is None and b["port"] == 1433 and b["priority"] == 1 and b["enabled"] is False
        assert b["has_alwayson"] is True and b["ag_name"] == "AG1" and b["databases"] == [] and b["database_count"] == 0

    def test_no_credentials_in_output(self):
        out = mod.rows_to_entries(ROWS_SRV, ROWS_DB)
        assert all(k not in e for e in out for k in ("password", "username"))


class TestRepo:
    def _file(self, tmp_path):
        p = tmp_path / "servers.json"
        p.write_text(json.dumps({"master_server": {"password": "encrypted:X"}, "monitored_servers": [
            {"id": "F_I01", "host": "F", "instance": "I01", "environment": "test", "enabled": True,
             "username": "u", "password": "encrypted:SECRET", "use_windows_auth": False, "databases": ["x", "y"]}]}),
            encoding="utf-8")
        return p

    def test_db_source(self, tmp_path):
        repo = mod.InventoryRepo(file_path=self._file(tmp_path), cache_seconds=60, source="db")
        with patch.object(repo, "_load_db", return_value=mod.rows_to_entries(ROWS_SRV, ROWS_DB)):
            items = repo.servers(enabled_only=True)
        assert [s["id"] for s in items] == ["A_I01"] and repo.source == "db"
        assert [s["id"] for s in repo.servers(enabled_only=False)] == ["A_I01", "B_I01"]
        assert [s["id"] for s in repo.servers(enabled_only=False, environment="QUALITY")] == ["B_I01"]
        assert repo.get("b_i01")["host"] == "B" and repo.get("nope") is None

    def test_fallback_to_file_when_db_fails_and_strips_secrets(self, tmp_path):
        repo = mod.InventoryRepo(file_path=self._file(tmp_path), cache_seconds=60, source="db")
        with patch.object(repo, "_load_db", side_effect=RuntimeError("down")):
            items = repo.servers()
        assert repo.source == "file" and items[0]["id"] == "F_I01"
        assert "password" not in items[0] and "username" not in items[0]
        assert [d["name"] for d in items[0]["databases"]] == ["x", "y"] and items[0]["database_count"] == 2

    def test_file_mode_never_touches_db(self, tmp_path):
        repo = mod.InventoryRepo(file_path=self._file(tmp_path), cache_seconds=60, source="file")
        with patch.object(repo, "_load_db", side_effect=AssertionError("should not be called")):
            assert repo.servers()[0]["id"] == "F_I01" and repo.source == "file"

    def test_cache_expiry(self, tmp_path):
        repo = mod.InventoryRepo(file_path=self._file(tmp_path), cache_seconds=0, source="db")
        calls = {"n": 0}
        def fake():
            calls["n"] += 1
            return mod.rows_to_entries(ROWS_SRV, ROWS_DB)
        with patch.object(repo, "_load_db", side_effect=fake):
            repo.servers(); repo.servers()
        assert calls["n"] == 2
        repo2 = mod.InventoryRepo(file_path=self._file(tmp_path), cache_seconds=600, source="db")
        calls["n"] = 0
        with patch.object(repo2, "_load_db", side_effect=fake):
            repo2.servers(); repo2.servers(); repo2.servers(force=True)
        assert calls["n"] == 2

    def test_both_sources_fail_keeps_previous_or_empty(self, tmp_path):
        repo = mod.InventoryRepo(file_path=tmp_path / "missing.json", cache_seconds=0, source="db")
        with patch.object(repo, "_load_db", side_effect=RuntimeError("down")):
            assert repo.servers() == [] and repo.source == "none"


class TestCredentialsGate:
    def test_db_entries_without_local_creds_are_flagged_and_filterable(self, tmp_path):
        p = tmp_path / "servers.json"
        p.write_text(json.dumps({"monitored_servers": [{"id": "A_I01", "host": "A", "password": "encrypted:X"}]}), encoding="utf-8")
        repo = mod.InventoryRepo(file_path=p, cache_seconds=60, source="db")
        with patch.object(mod, "rows_to_entries", return_value=[{"id": "A_I01", "enabled": True}, {"id": "B_I01", "enabled": True}]), \
             patch("api.connection_pool.execute_on_intelligence", return_value=[{"x": 1}]):
            allx = repo.servers(enabled_only=False)
            with_creds = repo.servers(enabled_only=False, require_credentials=True)
        assert {e["id"]: e["has_credentials"] for e in allx} == {"A_I01": True, "B_I01": False}
        assert [e["id"] for e in with_creds] == ["A_I01"]
