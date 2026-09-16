"""
2026-09-16 -- Regra de Ouro #2: nenhuma ligacao a` frota ou a` Intelligence fora do pool com Trusted_Connection.

Fora de api/connection_pool.py (dois recursos documentados) e dos tres ficheiros do lote B ainda por migrar,
nenhum ficheiro de api/, services/, modules/ e watcherdb/ pode ter o literal fora de comentario.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERMITIDOS = {
    "api/connection_pool.py",                       # os dois recursos documentados (fora da allowlist / Intelligence)
    "modules/monitoring/monitoring.py",             # lote B: ConnectionInfo legado (5 sitios com use_windows_auth=True)
    "watcherdb/core/async_db.py",                   # morto (nenhum chamador); lote B decide se sai
    "watcherdb/models/server.py",                   # morto (ServerConfig sem chamadores); lote B decide se sai
}


def _ficheiros():
    for pasta in ("api", "services", "modules", "watcherdb"):
        yield from sorted((ROOT / pasta).rglob("*.py"))


def test_trusted_connection_so_onde_esta_documentado():
    culpados = []
    for p in _ficheiros():
        rel = p.relative_to(ROOT).as_posix()
        if rel in PERMITIDOS:
            continue
        for n, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if "Trusted_Connection=yes" in l and not l.lstrip().startswith("#"):
                culpados.append(f"{rel}:{n}")
    assert culpados == [], "Trusted_Connection fora do pool:\n" + "\n".join(culpados)


def test_as_consultas_de_jobs_usam_a_string_do_pool_com_login_curto():
    src = (ROOT / "api/routers/intelligence_kpis.py").read_text(encoding="utf-8")
    assert src.count("conn = pyodbc.connect(_conn_str_msdb(server_id), timeout=4, autocommit=True)") == 2
    assert "_build_jobs_conn_str" not in src
    i = src.index("def _conn_str_msdb"); bloco = src[i:i + 1600]
    assert 'get_sql_server_pool()._build_connection_string(server_id, "msdb")' in bloco
    assert '"Connection Timeout=4;"' in bloco, "o login timeout curto e' o que protege o fan-out (54,8 s pelo pool vs 4 s)"


def test_o_codigo_morto_saiu():
    assert "_build_jobs_conn_str" not in (ROOT / "api/routers/intelligence/__init__.py").read_text(encoding="utf-8")
    assert "def _build_jobs_conn_str" not in (ROOT / "api/routers/intelligence/helpers.py").read_text(encoding="utf-8")
    assert "def get_server_connection_string" not in (ROOT / "api/routers/jobs.py").read_text(encoding="utf-8")
    assert "WATCHERDB_CONNECTION_STRING = (" not in (ROOT / "modules/monitoring/service_monitor.py").read_text(encoding="utf-8")
    assert "def _build_connection_string" not in (ROOT / "services/os_performance_service.py").read_text(encoding="utf-8")


def test_espaco_e_memoria_usam_o_pool():
    space = (ROOT / "watcherdb/api/routers/space.py").read_text(encoding="utf-8")
    assert "pyodbc.connect(" not in space and "execute_on_intelligence" in space
    mem = (ROOT / "modules/monitoring/memory_analysis.py").read_text(encoding="utf-8")
    i = mem.index("def get_connection_string"); bloco = mem[i:i + 900]
    assert "get_sql_server_pool()._build_connection_string(_server_id_from_name(server_name)" in bloco


def test_o_diagnostico_de_rede_testa_a_ligacao_do_portal():
    nd = (ROOT / "api/routers/network_diagnostics.py").read_text(encoding="utf-8")
    assert "get_sql_server_pool()._build_connection_string(server_id, \"master\")" in nd
    assert "from cryptography.fernet import Fernet as _Fernet" not in nd, "a decifra duplicada tem de sair"
