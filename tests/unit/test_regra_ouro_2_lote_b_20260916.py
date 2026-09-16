"""
2026-09-16 -- Regra de Ouro #2, lote B: ConnectionInfo usa as credenciais do pool na allowlist e Windows fora dela.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from modules.monitoring import monitoring as mon  # noqa: E402


class PoolFalso:
    def __init__(self, allow, creds):
        self.allow, self.creds = allow, creds

    def _sql_auth_enabled_for(self, sid):
        return sid.upper() in {a.upper() for a in self.allow}

    def _resolve_credentials(self, sid):
        return self.creds.get(sid.upper())


def _com_pool(monkeypatch, pool):
    import api.connection_pool as cp
    monkeypatch.setattr(cp, "get_sql_server_pool", lambda: pool)


def test_na_allowlist_com_credenciais_liga_por_sql_auth(monkeypatch):
    _com_pool(monkeypatch, PoolFalso(["SRV_I01"], {"SRV_I01": {"use_windows_auth": False, "username": "sql_monitoring", "password": "s3gredo"}}))
    cs = mon.ConnectionInfo(server="SRV", instance="I01", use_windows_auth=True).get_connection_string()
    assert "UID=sql_monitoring;" in cs and "PWD=s3gredo;" in cs
    assert "Trusted_Connection" not in cs and "ServerSPN" not in cs


def test_fora_da_allowlist_mantem_windows(monkeypatch):
    _com_pool(monkeypatch, PoolFalso([], {"OATXP01": {"use_windows_auth": False, "username": "u", "password": "p"}}))
    cs = mon.ConnectionInfo(server="OATXP01", instance="DEFAULT", use_windows_auth=True).get_connection_string()
    assert "Trusted_Connection=yes;" in cs and "UID=" not in cs


def test_na_allowlist_sem_password_mantem_windows(monkeypatch):
    _com_pool(monkeypatch, PoolFalso(["SRV_I01"], {"SRV_I01": {"use_windows_auth": False, "username": "u", "password": ""}}))
    cs = mon.ConnectionInfo(server="SRV", instance="I01", use_windows_auth=True).get_connection_string()
    assert "Trusted_Connection=yes;" in cs


def test_pool_indisponivel_e_fail_open(monkeypatch):
    import api.connection_pool as cp
    def rebenta():
        raise RuntimeError("pool em baixo")
    monkeypatch.setattr(cp, "get_sql_server_pool", rebenta)
    cs = mon.ConnectionInfo(server="SRV", instance="I01", use_windows_auth=True).get_connection_string()
    assert "Trusted_Connection=yes;" in cs


def test_credenciais_explicitas_nao_sao_tocadas(monkeypatch):
    _com_pool(monkeypatch, PoolFalso(["SRV_I01"], {"SRV_I01": {"use_windows_auth": False, "username": "sql_monitoring", "password": "x"}}))
    cs = mon.ConnectionInfo(server="SRV", instance="I01", use_windows_auth=False, username="outro", password="pw").get_connection_string()
    assert "UID=outro;" in cs and "PWD=pw;" in cs


def test_instancia_default_usa_o_host_como_id(monkeypatch):
    visto = {}
    class P(PoolFalso):
        def _sql_auth_enabled_for(self, sid):
            visto["sid"] = sid; return False
    _com_pool(monkeypatch, P([], {}))
    mon.ConnectionInfo(server="SQLIJSPRD03", instance="DEFAULT", use_windows_auth=True).get_connection_string()
    assert visto["sid"] == "SQLIJSPRD03"


def test_o_default_trace_esta_desligado_com_motivo():
    src = (ROOT / "modules/monitoring/service_monitor.py").read_text(encoding="utf-8")
    assert "DEFAULT_TRACE_ENABLED = False" in src
    assert "if not self.DEFAULT_TRACE_ENABLED:" in src
    assert "ALTER TRACE" in src and "Object:Created" in src
    from modules.monitoring.service_monitor import SQLServiceMonitor
    assert SQLServiceMonitor().get_default_trace_logs("SRV", "I01") == []


def test_o_builder_morto_saiu():
    src = (ROOT / "modules/monitoring/monitoring.py").read_text(encoding="utf-8")
    assert "def _build_connection_string(self, server_config: dict)" not in src
