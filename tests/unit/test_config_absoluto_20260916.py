"""
2026-09-16 -- os caminhos de configuracao do pool sao absolutos e nao dependem do directorio corrente.

Ate' hoje eram "config/servers.json" e "config/sql_auth_rollout.json" relativos ao CWD; o servico corre em System32 e
nunca os encontrava. Consequencia escondida: a allowlist de 62 servidores do SQL Auth nunca foi lida.
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pool(monkeypatch):
    from api.connection_pool import SQLServerConnectionPool
    SQLServerConnectionPool._instance = None
    yield SQLServerConnectionPool()
    SQLServerConnectionPool._instance = None


def test_os_dois_caminhos_sao_absolutos_e_apontam_para_config_dir(pool):
    from watcherdb.core.paths import config_dir
    for atributo, nome in (("_creds_cache_path", "servers.json"), ("_sql_auth_rollout_path", "sql_auth_rollout.json")):
        p = Path(getattr(pool, atributo))
        assert p.is_absolute(), f"{atributo} ainda e' relativo: {p}"
        assert p == config_dir() / nome, f"{atributo} nao aponta para config_dir(): {p}"


def test_os_caminhos_nao_mudam_com_o_directorio_corrente(tmp_path, monkeypatch):
    """E' o defeito de origem: o servico corre com o CWD em System32."""
    from api.connection_pool import SQLServerConnectionPool
    SQLServerConnectionPool._instance = None
    antes = SQLServerConnectionPool()
    a, b = antes._creds_cache_path, antes._sql_auth_rollout_path
    SQLServerConnectionPool._instance = None
    monkeypatch.chdir(tmp_path)
    depois = SQLServerConnectionPool()
    assert (depois._creds_cache_path, depois._sql_auth_rollout_path) == (a, b)
    SQLServerConnectionPool._instance = None


def test_nao_sobra_nenhum_caminho_relativo_a_config():
    for rel in ("api/connection_pool.py", "modules/monitoring/watcherdb_alwayson_check.py"):
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        activo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        assert 'Path(\'config/servers.json\')' not in activo, rel
        assert '= "config/servers.json"' not in activo, rel
        assert '= "config/sql_auth_rollout.json"' not in activo, rel


def test_o_arranque_diz_onde_procura_e_a_allowlist_e_visivel():
    src = (ROOT / "api" / "connection_pool.py").read_text(encoding="utf-8", errors="replace")
    assert '"[CONFIG] servers.json=%s (%s) | sql_auth_rollout.json=%s (%s)"' in src
    i = src.index("SQL Auth rollout allowlist:")
    assert "logger.warning(" in src[i - 200:i], "a contagem da allowlist tem de ser WARNING para chegar ao log do servico"


def test_o_recurso_sem_config_dir_continua_absoluto(monkeypatch):
    """Se watcherdb.core.paths nao importar, o recurso e' a raiz do projecto -- nunca o CWD."""
    import builtins
    from api import connection_pool as cp
    real = builtins.__import__

    def sem_paths(name, *a, **k):
        if name == "watcherdb.core.paths":
            raise ImportError("simulado")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sem_paths)
    p = Path(cp._config_file_path("servers.json"))
    assert p.is_absolute() and p == ROOT / "config" / "servers.json"
