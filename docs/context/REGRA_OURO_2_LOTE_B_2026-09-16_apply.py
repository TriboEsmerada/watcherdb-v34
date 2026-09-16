# -*- coding: utf-8 -*-
"""Regra de Ouro #2, lote B: o caminho legado (ConnectionInfo) passa a usar as credenciais do pool (2026-09-16).

CONTEXTO: depois do lote A (e8e6495) sobrava o caminho legado do modules/monitoring: cinco sitios constroem
ConnectionInfo(..., use_windows_auth=True) -- monitoring.py:389 (_get_conn_info), monitoring.py:996 (a ligacao do
LIVE/Overview, a que escreve "Conectando a:" no log), api/routers/queries/helpers.py:125 (consultas do LIVE) e
service_monitor.py:696/755 (errorlog e default trace dos logs de servico). E' por aqui que passa quase tudo o que
o portal pergunta a` frota. ConnectionInfo.get_connection_string() montava Trusted_Connection com a identidade de
dominio do servico.

DESENHO (recomendado, aprovado pelo owner): UM ponto de ligacao a`s credenciais do pool, dentro de
ConnectionInfo.get_connection_string(): quando use_windows_auth=True, pergunta ao pool central se o servidor esta
na allowlist do SQL Auth e tem credenciais completas; se sim, liga com elas (UID/PWD); se nao, mantem a identidade
de Windows. Os cinco sitios ficam como estao e passam todos a ser cobertos -- e os futuros tambem. A allowlist
continua a ser o unico interruptor (rollback: allowlist a [] e reiniciar).

DEFAULT TRACE (a excepcao medida): service_monitor.get_default_trace_logs le sys.fn_trace_gettable, que exige
ALTER TRACE -- grant que o sql_monitoring nao tem (docs/security/LEAST_PRIVILEGE_SETUP.sql: VIEW SERVER STATE, msdb,
xp_readerrorlog, SHOWPLAN). E a funcao rotula os EventClass 46/47 como "Server Start/Stop" quando 46/47 sao
Object:Created/Object:Deleted: mostrava criacoes de objectos como arranques do servico. Opcao (c) do owner: a
leitura do default trace fica DESLIGADA por interruptor (DEFAULT_TRACE_ENABLED = False), com o motivo escrito; os
arranques e paragens reais ja vem do errorlog (get_sql_error_logs, xp_readerrorlog, que esta' no grant). Quando o
grant ALTER TRACE entrar na revisao de grants do fecho, o interruptor volta a True e os rotulos corrigem-se.

TAMBEM: sai o _build_connection_string(server_config) morto (Trusted-only, sem chamadores) de monitoring.py.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/REGRA_OURO_2_LOTE_B_2026-09-16_apply.py --check
  py docs/context/REGRA_OURO_2_LOTE_B_2026-09-16_apply.py
  py -m pytest tests/unit/test_regra_ouro_2_lote_b_20260916.py tests/unit/test_regra_ouro_2_trusted_20260916.py tests/unit/test_connection_pool.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34
  (prova do lado do servico: abrir o LIVE de um servidor e correr a consulta do dm_exec_sessions com o PID do servico)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "mon": Path("modules/monitoring/monitoring.py"),
    "svcmon": Path("modules/monitoring/service_monitor.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_regra_ouro_2_lote_b_20260916.py"),
}
MARK = "def _credenciais_do_pool("

MON_EDITS = [
    ("""@dataclass
class ConnectionInfo:
""",
     """def _credenciais_do_pool(server: str, instance: str):
    \"\"\"(username, password) do pool central para este servidor, ou None.

    2026-09-16 (Regra de Ouro #2, lote B): o caminho legado montava Trusted_Connection com a identidade de dominio
    do servico. Agora pergunta ao pool central -- que ja decide pela allowlist do SQL Auth e pelas credenciais do
    servers.json -- e so' usa SQL Auth quando o pool tambem usaria. Fora da allowlist (ex.: OATXP01) ou sem
    credenciais completas, devolve None e o chamador mantem a identidade de Windows. FAIL-OPEN: qualquer erro
    aqui e' "sem credenciais", nunca uma ligacao partida.
    \"\"\"
    try:
        from api.connection_pool import get_sql_server_pool
        pool = get_sql_server_pool()
        inst = (instance or "").strip()
        server_id = f"{server}_{inst}" if inst and inst.upper() != "DEFAULT" else server
        if not pool._sql_auth_enabled_for(server_id):
            return None
        creds = pool._resolve_credentials(server_id)
        if not creds or creds.get("use_windows_auth") or not creds.get("username") or not creds.get("password"):
            return None
        return creds["username"], creds["password"]
    except Exception:
        return None


@dataclass
class ConnectionInfo:
""", 1),
    ("""    def get_connection_string(self) -> str:
        \"\"\"Gera connection string pyodbc\"\"\"
""",
     """    def get_connection_string(self) -> str:
        \"\"\"Gera connection string pyodbc\"\"\"
        # 2026-09-16 (Regra de Ouro #2, lote B): com use_windows_auth=True, as credenciais vem do pool central
        # quando o servidor esta' na allowlist do SQL Auth; senao mantem-se a identidade de Windows.
        use_windows = self.use_windows_auth
        username, password = self.username, self.password
        if use_windows:
            creds = _credenciais_do_pool(self.server, self.instance)
            if creds:
                use_windows = False
                username, password = creds
""", 1),
    ("""        if self.use_windows_auth:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE={self.database};"
                f"Trusted_Connection=yes;"
""",
     """        if use_windows:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE={self.database};"
                f"Trusted_Connection=yes;"
""", 1),
    ("""                f"UID={self.username};"
                f"PWD={self.password};"
""",
     """                f"UID={username};"
                f"PWD={password};"
""", 1),
    ("""    def _build_connection_string(self, server_config: dict) -> str:
        \"\"\"Build SQL Server connection string with Windows Auth\"\"\"
        host = server_config.get('host', server_config.get('server', ''))
        instance = server_config.get('instance', 'DEFAULT')
        
        if instance and instance != 'DEFAULT':
            server_address = f"{host}\\\\{instance}"
        else:
            server_address = host
        
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server_address};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=10;"
        )
        
        return conn_str

""",
     """    # 2026-09-16 (Regra de Ouro #2): _build_connection_string(server_config), Trusted-only e sem chamadores, saiu.

""", 1),
]

SVCMON_EDITS = [
    ("""    def get_default_trace_logs(self, server: str, instance: Optional[str] = None, hours: int = 24) -> List[Dict]:
        \"\"\"Obtém logs do Default Trace do SQL Server (Event Classes 46, 47, 164)\"\"\"
        try:
""",
     """    # 2026-09-16 (Regra de Ouro #2, lote B): a leitura do default trace fica DESLIGADA ate' haver grant.
    #  - sys.fn_trace_gettable exige ALTER TRACE, que a conta sql_monitoring nao tem (LEAST_PRIVILEGE_SETUP.sql);
    #    com o caminho legado a ligar pelo pool, esta leitura falharia nos 62 servidores da allowlist.
    #  - E a funcao rotulava os EventClass 46/47 como "Server Start/Stop" quando 46/47 sao Object:Created/Deleted:
    #    mostrava criacoes de objectos como arranques do servico. Os arranques e paragens reais ja vem do errorlog
    #    (get_sql_error_logs, via xp_readerrorlog, que esta' no grant).
    #  Quando ALTER TRACE entrar na revisao de grants, por a True e corrigir os rotulos (18 = Audit Server Starts And Stops).
    DEFAULT_TRACE_ENABLED = False

    def get_default_trace_logs(self, server: str, instance: Optional[str] = None, hours: int = 24) -> List[Dict]:
        \"\"\"Obtém logs do Default Trace do SQL Server (Event Classes 46, 47, 164)\"\"\"
        if not self.DEFAULT_TRACE_ENABLED:
            logger.debug("Default Trace desligado (sem ALTER TRACE para sql_monitoring; rotulos 46/47 errados) -- ver service_monitor.py")
            return []
        try:
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **O caminho legado de ligação à frota passa a usar as credenciais do pool** (16/09, Regra de Ouro #2, lote B).\n"
    "  O LIVE, o Overview, o Always On e os logs de serviço ligavam com a identidade de Windows do serviço; passam\n"
    "  a ligar como `sql_monitoring` nos servidores da allowlist, decidido num único sítio, e mantêm a identidade de\n"
    "  Windows fora dela. A leitura do *default trace* nos logs de serviço fica desligada por interruptor: exige um\n"
    "  grant que a conta não tem, e rotulava criações de objectos como arranques do serviço; os arranques reais\n"
    "  continuam a vir do errorlog. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:140]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    mon = src["mon"].read_bytes().decode("utf-8")
    if MARK in mon:
        print("[ABORT] ja aplicado"); return 1
    out = {
        "mon": _apply(mon, MON_EDITS, "monitoring"),
        "svcmon": _apply(src["svcmon"].read_bytes().decode("utf-8"), SVCMON_EDITS, "service_monitor"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
    }
    compile(out["mon"], str(REL["mon"]), "exec")
    compile(out["svcmon"], str(REL["svcmon"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] monitoring 5 blocos (helper, prelude, ramo Windows, UID/PWD, builder morto); service_monitor 1 (interruptor); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_regra_ouro_2_lote_b_20260916.py tests/unit/test_regra_ouro_2_trusted_20260916.py "
          "tests/unit/test_connection_pool.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
