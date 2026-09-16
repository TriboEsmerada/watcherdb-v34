# -*- coding: utf-8 -*-
"""Regra de Ouro #2, lote A: as ligacoes directas a` frota fora do pool passam pelo pool (2026-09-16).

CONTEXTO: com CONFIG_ABSOLUTO (00542d6) o pool central passou a ligar como sql_monitoring nos 62 servidores da
allowlist. Mas o pool nao e' o unico a ligar: o inventario feito hoje encontrou 14 literais "Trusted_Connection=yes"
fora dele. Este lote trata os que sao ligacoes DIRECTAS e VIVAS, ou codigo morto que ainda ensina o caminho errado.
O caminho legado do modules/monitoring (ConnectionInfo com use_windows_auth=True em 5 sitios) e' o lote B, a seguir,
porque exige um bridge unico para as credenciais do pool.

O QUE MUDA:
 1. api/routers/intelligence_kpis.py -- as duas consultas de jobs (falhas 24h, colisoes de agenda) montavam uma
    string propria com Trusted_Connection e host\\instancia para cada um dos ~62 servidores no fan-out do dashboard.
    Passam a usar a STRING DO POOL (SQL Auth na allowlist, IP e porta aprendida), mantendo a ligacao directa curta
    de 4 s: medido, um servidor inalcancavel demorava 54,8 s a falhar pelo pool (retries + 15 s de login) contra
    4 s directo, e o fan-out tem 16 workers e um tecto de 25 s. O SQL nao muda.
 2. modules/monitoring/memory_analysis.py -- o recurso "ligacao directa" da analise de memoria usa a string do pool.
 3. api/routers/network_diagnostics.py -- o teste ODBC do diagnostico de rede passa a testar EXACTAMENTE a ligacao
    que o portal usaria (construida pelo pool) e diz no detalhe que autenticacao usou; antes montava uma string
    propria (Trusted quando use_windows_auth=True) com uma decifra Fernet duplicada.
 4. watcherdb/api/routers/space.py -- o resumo de espaco para os alertas ligava a` Intelligence com pyodbc directo
    e Trusted (fora do pool da Intelligence). Passa por execute_on_intelligence.
 5. Codigo morto com o literal: _build_jobs_conn_str duplicado em intelligence/helpers.py (+ re-export),
    get_server_connection_string DEPRECATED em jobs.py, a constante WATCHERDB_CONNECTION_STRING nunca usada em
    service_monitor.py, e a string nunca usada em os_performance_service.py (o servico le WMI).
 6. Teste de guarda: fora de api/connection_pool.py (os dois recursos documentados) e dos tres ficheiros do lote B
    (monitoring.py, async_db.py, models/server.py), NENHUM ficheiro de api/, services/, modules/ e watcherdb/ pode ter
    "Trusted_Connection=yes" fora de comentario.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/REGRA_OURO_2_LOTE_A_2026-09-16_apply.py --check
  py docs/context/REGRA_OURO_2_LOTE_A_2026-09-16_apply.py
  py -m pytest tests/unit/test_regra_ouro_2_trusted_20260916.py tests/unit/test_connection_pool.py tests/unit/test_api_routers.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "kpis": Path("api/routers/intelligence_kpis.py"),
    "helpers": Path("api/routers/intelligence/helpers.py"),
    "init": Path("api/routers/intelligence/__init__.py"),
    "jobs": Path("api/routers/jobs.py"),
    "netdiag": Path("api/routers/network_diagnostics.py"),
    "mem": Path("modules/monitoring/memory_analysis.py"),
    "svcmon": Path("modules/monitoring/service_monitor.py"),
    "osperf": Path("services/os_performance_service.py"),
    "space": Path("watcherdb/api/routers/space.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "context": Path("docs/context/CONTEXT.md"),
    "test": Path("tests/unit/test_regra_ouro_2_trusted_20260916.py"),
}
MARK = "def _conexao_msdb("

BUILD_JOBS_OLD = r'''def _build_jobs_conn_str(server_id: str) -> str:
    """Connection string com timeout curto (4s) para queries de jobs KPI."""
    if '_' in server_id and '\\' not in server_id:
        parts = server_id.split('_', 1)
        server_name = f"{parts[0]}\\{parts[1]}"
    else:
        server_name = server_id
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server_name};DATABASE=master;"
        f"Trusted_Connection=yes;TrustServerCertificate=yes;"
        f"Connection Timeout=4;"
    )
'''

KPIS_EDITS = [
    (BUILD_JOBS_OLD,
     r'''def _conn_str_msdb(server_id: str) -> str:
    """String de ligacao ao msdb de um servidor monitorizado -- a DO POOL, com o login timeout curto de sempre.

    2026-09-16 (Regra de Ouro #2): ate' aqui as duas consultas de jobs montavam uma string propria com
    Trusted_Connection (a identidade de dominio do servico) e host\\instancia (SQL Browser). Passam a usar a
    string que o pool central constroi: sql_monitoring nos servidores da allowlist, Trusted so' fora dela
    (OATXP01), e alvo por IP e porta aprendida em vez do Browser. A ligacao continua DIRECTA e curta (4 s de
    login, sem retries): medido a 16/09, um servidor inalcancavel demorava 54,8 s a falhar pelo pool (retries +
    15 s de login) contra 4 s aqui -- e o fan-out do dashboard corre isto para ~62 servidores com 16 workers e um
    tecto de 25 s; um punhado de servidores em baixo esgotaria os workers.
    """
    import re as _re
    base = get_sql_server_pool()._build_connection_string(server_id, "msdb")
    return _re.sub(r"Connection Timeout=\d+;", "Connection Timeout=4;", base)
''', 1),
    ("        # Evita bloquear a thread 30s (pool timeout) e perder todos os resultados no asyncio\n",
     "        # Evita bloquear a thread (retries + 15 s de login do pool) e perder todos os resultados no asyncio\n", 1),
    ("        # Conexao directa com timeout curto (4s) — servidores offline falham rapido\n",
     "        # Conexao directa com timeout curto (4s) e a STRING DO POOL (Regra de Ouro #2, 2026-09-16) — servidores offline falham rapido\n", 2),
    ("        conn = pyodbc.connect(_build_jobs_conn_str(server_id), timeout=4, autocommit=True)\n",
     "        conn = pyodbc.connect(_conn_str_msdb(server_id), timeout=4, autocommit=True)\n", 2),
]

HELPERS_EDITS = [
    (BUILD_JOBS_OLD,
     "# 2026-09-16: _build_jobs_conn_str (copia com Trusted_Connection, nunca chamada) saiu daqui; as consultas de\n"
     "# jobs vivem em intelligence_kpis.py e passam pelo pool central.\n", 1),
]
INIT_EDITS = [("    _build_jobs_conn_str,\n", "", 1)]

JOBS_OLD = r'''def get_server_connection_string(server_id: str) -> str:
    """
    Generate connection string for SQL Server with validation
    DEPRECATED: Use get_pooled_connection() instead for better performance.

    Args:
        server_id: Server identifier (HOST_INSTANCE or HOST\\INSTANCE)

    Returns:
        ODBC connection string

    Raises:
        ValueError: If server_id is invalid
    """
    if not server_id or not server_id.strip():
        raise ValueError("server_id não pode ser vazio")

    server_id = server_id.strip()

    # Converter formato HOST_INSTANCE para HOST\\INSTANCE
    if '_' in server_id and '\\' not in server_id:
        parts = server_id.split('_', 1)
        server_name = f"{parts[0]}\\{parts[1]}"
    else:
        server_name = server_id

    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server_name};"
        f"DATABASE=msdb;"
        f"Trusted_Connection=yes;"
        f"Connection Timeout={CONNECTION_TIMEOUT};"
    )


'''
JOBS_EDITS = [(JOBS_OLD,
               "# 2026-09-16 (Regra de Ouro #2): get_server_connection_string, marcada DEPRECATED e sem chamadores, saiu:\n"
               "# montava uma ligacao directa com Trusted_Connection. Toda a ligacao a` frota passa por get_pooled_connection().\n\n\n", 1)]

NETDIAG_OLD = r'''        if use_windows_auth:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE=master;"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout=10;"
            )
        else:
            # Desencriptar password se necessário
            pwd = password
            if isinstance(pwd, str) and pwd.startswith('encrypted:'):
                try:
                    import os as _os
                    from cryptography.fernet import Fernet as _Fernet
                    _enc_key = _os.environ.get('WATCHERDB_ENCRYPTION_KEY', '')
                    if _enc_key:
                        _f = _Fernet(_enc_key.encode())
                        pwd = _f.decrypt(pwd[len('encrypted:'):].encode()).decode()
                    else:
                        pwd = pwd[len('encrypted:'):]
                except Exception:
                    pwd = pwd[len('encrypted:'):]
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE=master;"
                f"UID={username};"
                f"PWD={pwd};"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout=10;"
            )
        conn = pyodbc.connect(conn_str, timeout=10)
        test3['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test3['detail'] = f'Conexão ODBC estabelecida em {test3["time_ms"]}ms'
'''
NETDIAG_NEW = r'''        # 2026-09-16 (Regra de Ouro #2): o teste usa EXACTAMENTE a ligacao que o portal usaria para este servidor,
        # construida pelo pool central (allowlist do SQL Auth, portas aprendidas, credenciais decifradas pelo
        # servico de segredos). Antes montava aqui uma string propria -- Trusted_Connection quando
        # use_windows_auth era True, e uma decifra Fernet duplicada -- e diagnosticava uma ligacao que nao era a do
        # portal. O alvo (ip,porta vs host\instancia) tambem passa a ser o real.
        from api.connection_pool import get_sql_server_pool
        conn_str = get_sql_server_pool()._build_connection_string(server_id, "master")
        _modo = 'SQL Auth (sql_monitoring)' if 'UID=' in conn_str else 'Windows (identidade do servico)'
        _alvo = conn_str.split('SERVER=')[1].split(';')[0] if 'SERVER=' in conn_str else server_full
        conn = pyodbc.connect(conn_str, timeout=10)
        test3['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test3['detail'] = f'Conexão ODBC estabelecida em {test3["time_ms"]}ms · {_modo} · alvo {_alvo}'
'''
NETDIAG_EDITS = [(NETDIAG_OLD, NETDIAG_NEW, 1)]

MEM_OLD = r'''def get_connection_string(server_name: str) -> str:
    """
    Gera string de conexão para o servidor SQL
    Usa o mesmo padrão do sistema WatcherDB existente
    """
    # Usar o padrão de conexão do WatcherDB (mesmo que o monitoring.py)
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server_name};Trusted_Connection=yes;Connection Timeout=10;"
'''
MEM_NEW = r'''def get_connection_string(server_name: str) -> str:
    """String de ligacao para o servidor SQL -- a MESMA que o pool central usaria.

    2026-09-16 (Regra de Ouro #2): era uma string propria com Trusted_Connection. Agora vem do pool: SQL Auth na
    allowlist, portas aprendidas, Trusted so' fora da allowlist. server_name pode vir como HOST\\INSTANCIA.
    """
    from api.connection_pool import get_sql_server_pool
    return get_sql_server_pool()._build_connection_string(_server_id_from_name(server_name), "master")
'''
MEM_EDITS = [(MEM_OLD, MEM_NEW, 1)]

SVCMON_OLD = r'''    # Configuração de conexão com WatcherDB Intelligence
    WATCHERDB_CONNECTION_STRING = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=SQLHDSTST505\\I01;'
        'DATABASE=WatcherDB_Intelligence;'
        'Trusted_Connection=yes;'
        'Connection Timeout=10;'
    )

'''
SVCMON_EDITS = [(SVCMON_OLD,
                 "    # 2026-09-16: a constante WATCHERDB_CONNECTION_STRING (servidor fixo + Trusted_Connection, nunca usada)\n"
                 "    # saiu; a Intelligence e' acedida por get_intelligence_pool().\n\n", 1)]

OSPERF_EDITS = [
    ("        self.connection_string = connection_string or self._build_connection_string()\n",
     "        # 2026-09-16: a string nunca foi usada para ligar (o servico le WMI); a antiga trazia Trusted_Connection.\n"
     "        self.connection_string = connection_string or \"\"\n", 1),
    (r'''    def _build_connection_string(self) -> str:
        """Constroi connection string baseado em variaveis de ambiente"""
        server = os.getenv('INTELLIGENCE_SERVER', 'SQLHDSTST505\\I01')
        database = os.getenv('INTELLIGENCE_DATABASE', 'WatcherDB_Intelligence')
        driver = os.getenv('SQL_DRIVER', 'ODBC Driver 17 for SQL Server')

        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
            f"Connection Timeout=30;"
        )

''', "", 1),
]

SPACE_EDITS = [
    (r'''def _get_intelligence_connection():
    """Cria conexão com o WatcherDB Intelligence"""
    conn_str = (
        f"DRIVER={{{INTELLIGENCE_DRIVER}}};"
        f"SERVER={INTELLIGENCE_SERVER};"
        f"DATABASE={INTELLIGENCE_DATABASE};"
        f"Trusted_Connection=yes;"
        f"Connection Timeout=30"
    )
    return pyodbc.connect(conn_str)
''',
     "# 2026-09-16 (Regra de Ouro #2): a ligacao directa a` Intelligence com Trusted_Connection saiu; as consultas\n"
     "# passam por execute_on_intelligence (pool da Intelligence, sql_monitoring).\n", 1),
    (r'''def _execute_intelligence_query(query: str) -> List[Dict]:
    """Executa query no WatcherDB Intelligence e retorna lista de dicts"""
    try:
        conn = _get_intelligence_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        return [
            {col: _serialize_value(val) for col, val in zip(columns, row)}
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao executar query no Intelligence: {e}")
        return []
''',
     r'''def _execute_intelligence_query(query: str) -> List[Dict]:
    """Executa query no WatcherDB Intelligence pelo pool central e devolve lista de dicts."""
    try:
        from api.connection_pool import execute_on_intelligence
        return [{col: _serialize_value(val) for col, val in row.items()} for row in execute_on_intelligence(query)]
    except Exception as e:
        logger.error(f"Erro ao executar query no Intelligence: {e}")
        return []
''', 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Ligações à frota fora do pool passam a usar a ligação do pool** (16/09, Regra de Ouro #2). Duas consultas de\n"
    "  trabalhos do dashboard abriam, para cada um dos ~62 servidores, uma ligação com a identidade de Windows do\n"
    "  serviço e pelo SQL Browser; passam a usar a string do pool central — conta `sql_monitoring` na allowlist, IP e\n"
    "  porta aprendida — mantendo o *fail-fast* de 4 s que protege o painel quando há servidores em baixo. O\n"
    "  diagnóstico de rede testa agora exactamente a ligação que o portal usaria e diz que autenticação usou.\n"
    "  O resumo de espaço dos alertas e o recurso da análise de memória seguem o mesmo caminho. Saem quatro cópias\n"
    "  mortas de ligações com identidade de Windows. Um teste de guarda impede novas. [tier: Std]\n"
    "\n",
    1,
)

CONTEXT_APPEND = (
    "- 2026-09-16 | orquestrador | REGRA DE OURO #2, lote A (REGRA_OURO_2_LOTE_A_2026-09-16_apply.py): inventario "
    "de 14 literais Trusted_Connection=yes fora do pool; migrados os directos e vivos (intelligence_kpis jobs x2 -> "
    "string do pool com login de 4 s mantido, porque pelo pool um servidor inalcancavel demorava 54,8 s a falhar "
    "contra 4 s directo; memory_analysis recurso -> string do pool; network_diagnostics teste ODBC -> string do pool com modo "
    "no detalhe; space.py -> execute_on_intelligence) e removidos 4 mortos (helpers._build_jobs_conn_str + re-export, "
    "jobs.get_server_connection_string, service_monitor.WATCHERDB_CONNECTION_STRING, os_performance._build_connection_"
    "string). Teste de guarda com allowlist de 4 ficheiros. LOTE B por fazer: modules/monitoring/monitoring.py "
    "ConnectionInfo(use_windows_auth=True) em 5 sitios (monitoring.py:389,996; queries/helpers.py:125; "
    "service_monitor.py:696,755) -- e' o caminho do LIVE/Overview/AlwaysOn/logs de servico; exige bridge unico das "
    "credenciais do pool em ConnectionInfo.get_connection_string e verificar grants (docs/security/"
    "LEAST_PRIVILEGE_SETUP.sql) para fn_trace_gettable/xp_readerrorlog; async_db.py e models/server.py estao mortos.\n"
)

TEST_SRC = r'''"""
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
    kpis = src["kpis"].read_bytes().decode("utf-8")
    if MARK in kpis:
        print("[ABORT] ja aplicado"); return 1
    ctx = src["context"].read_bytes().decode("utf-8")
    eol_ctx = "\r\n" if "\r\n" in ctx else "\n"
    if not ctx.endswith(eol_ctx):
        ctx += eol_ctx
    out = {
        "kpis": _apply(kpis, KPIS_EDITS, "intelligence_kpis"),
        "helpers": _apply(src["helpers"].read_bytes().decode("utf-8"), HELPERS_EDITS, "intelligence/helpers"),
        "init": _apply(src["init"].read_bytes().decode("utf-8"), INIT_EDITS, "intelligence/__init__"),
        "jobs": _apply(src["jobs"].read_bytes().decode("utf-8"), JOBS_EDITS, "jobs"),
        "netdiag": _apply(src["netdiag"].read_bytes().decode("utf-8"), NETDIAG_EDITS, "network_diagnostics"),
        "mem": _apply(src["mem"].read_bytes().decode("utf-8"), MEM_EDITS, "memory_analysis"),
        "svcmon": _apply(src["svcmon"].read_bytes().decode("utf-8"), SVCMON_EDITS, "service_monitor"),
        "osperf": _apply(src["osperf"].read_bytes().decode("utf-8"), OSPERF_EDITS, "os_performance_service"),
        "space": _apply(src["space"].read_bytes().decode("utf-8"), SPACE_EDITS, "space"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
        "context": ctx + CONTEXT_APPEND.replace("\n", eol_ctx),
    }
    for k in ("kpis", "helpers", "init", "jobs", "netdiag", "mem", "svcmon", "osperf", "space"):
        compile(out[k], str(REL[k]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] 9 ficheiros de codigo compilam; changelog; CONTEXT +1; teste de guarda")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_regra_ouro_2_trusted_20260916.py tests/unit/test_connection_pool.py "
          "tests/unit/test_api_routers.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
