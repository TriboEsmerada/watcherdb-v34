# -*- coding: utf-8 -*-
"""2026-10-07 -- NOME_BASE_LOGIN_CENTRAL: servidor, base e login do produto numa fonte unica + gate de literais.

O gate percorre o codigo por AST e falha se aparecer um literal novo com o nome da base, do login ou do
servidor do empregador fora de watcherdb/core/db_identity.py e da allowlist (cada entrada com motivo).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from watcherdb.core import db_identity as dbi

ROOT = Path(__file__).resolve().parents[2]
ALVOS = ("WatcherDB_Intelligence", "sql_monitoring", "SQLHDSTST505")
DIRS = ("api", "services", "modules", "watcherdb", "tools", "collectors")

# (caminho relativo, fragmento do literal) -> motivo. Entradas novas exigem motivo escrito aqui.
ALLOWLIST = {
    ("api/routers/network_diagnostics.py", "SQL Auth (sql_monitoring)"): "rotulo do modo de ligacao a' FROTA (login por servidor; lote C do instalador)",
    ("modules/monitoring/security_analysis.py", "do sql_monitoring ou conectividade"): "mensagem sobre o login da frota (lote C)",
    ("modules/monitoring/service_monitor.py", "sem ALTER TRACE para sql_monitoring"): "log de diagnostico sobre o login da frota",
    ("api/routers/queries/tlog_diagnosis.py", "a sql_monitoring"): "texto de diagnostico sobre o login da frota",
    ("modules/monitoring/queries.py", "sem acesso do sql_monitoring"): "comentario dentro de SQL (LOG_SPACE_USAGE)",
    ("modules/monitoring/queries.py", "sem permissao do sql_monitoring"): "comentario dentro de SQL (FILE_SPACE_DETAIL)",
    ("modules/monitoring/monitoring_integration.py", "sql_monitoring"): "nome de atributo app.state, nao e' o login",
    ("watcherdb/api/routers/security.py", "sql_monitoring"): "nome de atributo app.state / mensagem 503, nao e' o login",
}


def _literais(f: Path):
    src = f.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    doc = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                doc.update(range(first.lineno, first.end_lineno + 1))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and any(a in node.value for a in ALVOS):
            if node.lineno not in doc:
                yield node.lineno, node.value


def test_gate_de_literais_fora_da_fonte_unica():
    novos = []
    for d in DIRS:
        for f in (ROOT / d).rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            rel = f.relative_to(ROOT).as_posix()
            if rel == "watcherdb/core/db_identity.py":
                continue
            for lineno, valor in _literais(f):
                if any(rel == p and frag in valor for (p, frag) in ALLOWLIST):
                    continue
                novos.append(f"{rel}:{lineno}: {valor.strip()[:80]!r}")
    assert not novos, "literal do nome da base/login/servidor fora de db_identity.py (usar as funcoes ou justificar na ALLOWLIST):\n" + "\n".join(novos)


def test_allowlist_sem_entradas_mortas():
    """Cada entrada da allowlist tem de continuar a casar com algo; senao e' lixo que esconde regressoes."""
    mortas = []
    for (p, frag) in ALLOWLIST:
        f = ROOT / p
        if not f.exists():
            mortas.append(f"{p} (ficheiro nao existe)")
            continue
        if not any(frag in v for _, v in _literais(f)):
            mortas.append(f"{p}: {frag!r}")
    assert not mortas, "entradas da allowlist sem correspondencia: " + "; ".join(mortas)


@pytest.fixture()
def limpo(monkeypatch):
    for v in ("INTELLIGENCE_SERVER", "SQL_SERVER", "INTELLIGENCE_DATABASE", "SQL_DATABASE", "INTELLIGENCE_SQL_USER", "SQL_USER"):
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_omissoes_do_runtime_nao_mudaram(limpo):
    assert dbi.intelligence_database() == "WatcherDB_Intelligence" == dbi.DEFAULT_INTELLIGENCE_DATABASE
    assert dbi.intelligence_sql_user() == "sql_monitoring" == dbi.DEFAULT_INTELLIGENCE_SQL_USER
    assert dbi.intelligence_server() == "localhost" == dbi.DEFAULT_INTELLIGENCE_SERVER


def test_prioridade_intelligence_depois_sql_depois_omissao(limpo):
    limpo.setenv("SQL_DATABASE", "Antiga")
    assert dbi.intelligence_database() == "Antiga"
    limpo.setenv("INTELLIGENCE_DATABASE", "Nova")
    assert dbi.intelligence_database() == "Nova"
    limpo.setenv("SQL_USER", "u_antigo")
    assert dbi.intelligence_sql_user() == "u_antigo"
    limpo.setenv("INTELLIGENCE_SQL_USER", "u_novo")
    assert dbi.intelligence_sql_user() == "u_novo"
    limpo.setenv("INTELLIGENCE_SERVER", "SRV\\\\I01")
    assert dbi.intelligence_server() == "SRV\\\\I01"


def test_vazio_conta_como_ausente(limpo):
    limpo.setenv("INTELLIGENCE_DATABASE", "")
    limpo.setenv("SQL_DATABASE", "X")
    assert dbi.intelligence_database() == "X"


def test_settings_usa_as_mesmas_omissoes(limpo):
    from watcherdb.core.settings import WatcherDBSettings
    s = WatcherDBSettings(_env_file=None)
    assert s.intelligence_database == dbi.DEFAULT_INTELLIGENCE_DATABASE
    assert s.intelligence_sql_user == dbi.DEFAULT_INTELLIGENCE_SQL_USER
    assert s.intelligence_server == dbi.DEFAULT_INTELLIGENCE_SERVER


def test_remedio_cita_o_login_configurado():
    assert dbi.DEFAULT_INTELLIGENCE_SQL_USER in dbi._REMEDY
