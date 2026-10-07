# -*- coding: utf-8 -*-
"""Lote A.4 do desenho do instalador: nome do servidor, da base e do login numa fonte unica (2026-10-07).

CONTEXTO: o owner quer base e login configuraveis no instalador (omissoes WatcherDB / watcherdb em instalacoes
novas). Medido no gate de 2026-10-06 e no desenho de 2026-10-07: as omissoes do runtime estavam copiadas em
5 sitios (helpers.py:141-149, intelligence_kpis.py:277-286, overview_dashboard.py:37-43, watcherdb/api/routers/
space.py:37-38, settings.py:49-52), com dois estilos (uns aceitam SQL_* como 2.a fonte, outros nao), e com o
servidor real do empregador como omissao (gate de IP). Mais 3 sitios usavam o nome da base em mensagens/rotulos.

REGRA: watcherdb/core/db_identity.py passa a ter DEFAULT_INTELLIGENCE_{SERVER,DATABASE,SQL_USER} e as funcoes
intelligence_server()/intelligence_database()/intelligence_sql_user() (INTELLIGENCE_* > SQL_* > omissao).
As OMISSOES DO RUNTIME NAO MUDAM (WatcherDB_Intelligence / sql_monitoring): sao a rede de seguranca da frota
actual. A omissao do servidor passa a 'localhost' (era SQLHDSTST505\\I01): o .env desta instalacao define
INTELLIGENCE_SERVER explicitamente (verificado 2026-10-07, so' presenca da chave). A omissao do INSTALADOR para
instalacoes novas (WatcherDB / watcherdb) vive no instalador, que escreve sempre as chaves explicitas no .env
(DESIGN_INSTALADOR_V3.4_2026-10-07.md, lote A).

O QUE MUDA (8 ficheiros + 1 teste):
  watcherdb/core/db_identity.py      constantes + 3 funcoes; _REMEDY usa a constante.
  api/routers/intelligence/helpers.py, api/routers/intelligence_kpis.py, api/routers/overview_dashboard.py,
  watcherdb/api/routers/space.py     omissoes -> funcoes (os nomes dos modulos, INTELLIGENCE_*, mantem-se:
                                     sao re-exportados por api/routers/intelligence/__init__.py).
  watcherdb/api/routers/space.py     "source": nome da base vindo da configuracao (2x).
  watcherdb/core/settings.py         omissoes dos campos = constantes.
  api/routers/kpi_thresholds.py      mensagem 503 com o nome configurado da base.
  tests/unit/test_nome_base_login_central_20261007.py (novo): funcoes + GATE DE LITERAIS por AST (qualquer
                                     literal novo com o nome da base, do login ou do servidor fora de
                                     db_identity.py e da allowlist faz o teste falhar).

Uso: py docs/context/NOME_BASE_LOGIN_CENTRAL_2026-10-07_apply.py --check | --preview | --repo <copia> | (aplica)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DBI = Path("watcherdb/core/db_identity.py")
HELP = Path("api/routers/intelligence/helpers.py")
KPIS = Path("api/routers/intelligence_kpis.py")
OVW = Path("api/routers/overview_dashboard.py")
SPACE = Path("watcherdb/api/routers/space.py")
SETT = Path("watcherdb/core/settings.py")
THR = Path("api/routers/kpi_thresholds.py")
TEST = Path("tests/unit/test_nome_base_login_central_20261007.py")

IMPORT_OLD = "from watcherdb.core.db_identity import resolve as _resolve_db_identity\n"
IMPORT_NEW = ("from watcherdb.core.db_identity import (  # 2026-10-07: nomes do servidor/base/login numa fonte unica\n"
              "    resolve as _resolve_db_identity, intelligence_server, intelligence_database, intelligence_sql_user,\n"
              ")\n")
SRV_DB_OR_OLD = ('INTELLIGENCE_SERVER = os.getenv("INTELLIGENCE_SERVER") or os.getenv("SQL_SERVER", "SQLHDSTST505\\\\I01")\n'
                 'INTELLIGENCE_DATABASE = os.getenv("INTELLIGENCE_DATABASE") or os.getenv("SQL_DATABASE", "WatcherDB_Intelligence")\n')
SRV_DB_PLAIN_OLD = ('INTELLIGENCE_SERVER = os.getenv("INTELLIGENCE_SERVER", "SQLHDSTST505\\\\I01")\n'
                    'INTELLIGENCE_DATABASE = os.getenv("INTELLIGENCE_DATABASE", "WatcherDB_Intelligence")\n')
SRV_DB_NEW = ('INTELLIGENCE_SERVER = intelligence_server()      # fonte unica: watcherdb.core.db_identity (2026-10-07)\n'
              'INTELLIGENCE_DATABASE = intelligence_database()\n')
USER_OR_OLD = 'INTELLIGENCE_SQL_USER = os.getenv("INTELLIGENCE_SQL_USER") or os.getenv("SQL_USER", "sql_monitoring")\n'
USER_PLAIN_OLD = 'INTELLIGENCE_SQL_USER = os.getenv("INTELLIGENCE_SQL_USER", "sql_monitoring")\n'
USER_NEW = 'INTELLIGENCE_SQL_USER = intelligence_sql_user()\n'

DBI_BLOCK_ANCHOR = '_INTEL_VAR = "INTELLIGENCE_USE_WINDOWS_AUTH"\n'
DBI_BLOCK_NEW = DBI_BLOCK_ANCHOR + '''
# ---------------------------------------------------------------------------
# Servidor, base e login do produto -- fonte unica (2026-10-07, NOME_BASE_LOGIN_CENTRAL)
# ---------------------------------------------------------------------------
# Omissoes do RUNTIME: a rede de seguranca da frota actual quando o .env nao define a chave. Nao confundir com
# a omissao do INSTALADOR para instalacoes novas (WatcherDB / watcherdb), que escreve sempre as chaves
# explicitas no .env (docs/context/DESIGN_INSTALADOR_V3.4_2026-10-07.md). Prioridade: INTELLIGENCE_* > SQL_*
# (nomes antigos, ainda no .env de instalacoes anteriores) > omissao.
DEFAULT_INTELLIGENCE_SERVER = "localhost"   # ate' 2026-10-07 era um servidor real do empregador (gate de IP)
DEFAULT_INTELLIGENCE_DATABASE = "WatcherDB_Intelligence"
DEFAULT_INTELLIGENCE_SQL_USER = "sql_monitoring"


def _primeiro(*nomes: str, omissao: str) -> str:
    for n in nomes:
        v = os.getenv(n)
        if v:
            return v
    return omissao


def intelligence_server() -> str:
    """Servidor\\\\instancia da base do produto (INTELLIGENCE_SERVER > SQL_SERVER > omissao)."""
    return _primeiro("INTELLIGENCE_SERVER", "SQL_SERVER", omissao=DEFAULT_INTELLIGENCE_SERVER)


def intelligence_database() -> str:
    """Nome da base do produto (INTELLIGENCE_DATABASE > SQL_DATABASE > omissao)."""
    return _primeiro("INTELLIGENCE_DATABASE", "SQL_DATABASE", omissao=DEFAULT_INTELLIGENCE_DATABASE)


def intelligence_sql_user() -> str:
    """Login SQL do produto (INTELLIGENCE_SQL_USER > SQL_USER > omissao)."""
    return _primeiro("INTELLIGENCE_SQL_USER", "SQL_USER", omissao=DEFAULT_INTELLIGENCE_SQL_USER)
'''
REMEDY_OLD_1 = '    "    INTELLIGENCE_SQL_USER=sql_monitoring\\n"\n'
REMEDY_NEW_1 = '    f"    INTELLIGENCE_SQL_USER={DEFAULT_INTELLIGENCE_SQL_USER}\\n"\n'
REMEDY_OLD_2 = '    "-- a Regra de Ouro #2 reserva o acesso a BD ao sql_monitoring."\n'
REMEDY_NEW_2 = '    f"-- a Regra de Ouro #2 reserva o acesso a BD ao login do produto ({DEFAULT_INTELLIGENCE_SQL_USER})."\n'

SPACE_IMPORT_OLD = "from watcherdb.core.auth import get_current_user, User, require_role, UserRole\n"
SPACE_IMPORT_NEW = ("from watcherdb.core.auth import get_current_user, User, require_role, UserRole\n"
                    "from watcherdb.core.db_identity import intelligence_server, intelligence_database  # 2026-10-07\n")
SPACE_SOURCE_OLD = '"source": "WatcherDB_Intelligence",'
SPACE_SOURCE_NEW = '"source": INTELLIGENCE_DATABASE,'

SETT_IMPORT_OLD = "from pydantic import Field\n"
SETT_IMPORT_NEW = ("from pydantic import Field\n"
                   "from watcherdb.core.db_identity import (  # 2026-10-07: omissoes numa fonte unica\n"
                   "    DEFAULT_INTELLIGENCE_SERVER, DEFAULT_INTELLIGENCE_DATABASE, DEFAULT_INTELLIGENCE_SQL_USER,\n"
                   ")\n")
SETT_FIELDS_OLD = ('    intelligence_server: str = r"SQLHDSTST505\\I01"\n'
                   '    intelligence_database: str = "WatcherDB_Intelligence"\n'
                   '    intelligence_use_windows_auth: bool = True\n'
                   '    intelligence_sql_user: str = "sql_monitoring"\n')
SETT_FIELDS_NEW = ('    intelligence_server: str = DEFAULT_INTELLIGENCE_SERVER\n'
                   '    intelligence_database: str = DEFAULT_INTELLIGENCE_DATABASE\n'
                   '    intelligence_use_windows_auth: bool = True\n'
                   '    intelligence_sql_user: str = DEFAULT_INTELLIGENCE_SQL_USER\n')

THR_IMPORT_OLD = "from api.kpi_thresholds_registry import THRESHOLDS, REGISTRY_VERSION\n"
THR_IMPORT_NEW = ("from api.kpi_thresholds_registry import THRESHOLDS, REGISTRY_VERSION\n"
                  "from watcherdb.core.db_identity import intelligence_database  # 2026-10-07\n")
THR_MSG_OLD = '                        "WatcherDB_Intelligence — correr o bloco DDL "\n'
THR_MSG_NEW = '                        f"{intelligence_database()} — correr o bloco DDL "\n'

# (ficheiro, velho, novo, ocorrencias esperadas)
EDITS = [
    (DBI, DBI_BLOCK_ANCHOR, DBI_BLOCK_NEW, 1),
    (DBI, REMEDY_OLD_1, REMEDY_NEW_1, 1),
    (DBI, REMEDY_OLD_2, REMEDY_NEW_2, 1),
    (HELP, IMPORT_OLD, IMPORT_NEW, 1), (HELP, SRV_DB_OR_OLD, SRV_DB_NEW, 1), (HELP, USER_OR_OLD, USER_NEW, 1),
    (KPIS, IMPORT_OLD, IMPORT_NEW, 1), (KPIS, SRV_DB_OR_OLD, SRV_DB_NEW, 1), (KPIS, USER_OR_OLD, USER_NEW, 1),
    (OVW, IMPORT_OLD, IMPORT_NEW, 1), (OVW, SRV_DB_PLAIN_OLD, SRV_DB_NEW, 1), (OVW, USER_PLAIN_OLD, USER_NEW, 1),
    (SPACE, SPACE_IMPORT_OLD, SPACE_IMPORT_NEW, 1), (SPACE, SRV_DB_PLAIN_OLD, SRV_DB_NEW, 1), (SPACE, SPACE_SOURCE_OLD, SPACE_SOURCE_NEW, 2),
    (SETT, SETT_IMPORT_OLD, SETT_IMPORT_NEW, 1), (SETT, SETT_FIELDS_OLD, SETT_FIELDS_NEW, 1),
    (THR, THR_IMPORT_OLD, THR_IMPORT_NEW, 1), (THR, THR_MSG_OLD, THR_MSG_NEW, 1),
]

TEST_SRC = '''# -*- coding: utf-8 -*-
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
    assert not novos, "literal do nome da base/login/servidor fora de db_identity.py (usar as funcoes ou justificar na ALLOWLIST):\\n" + "\\n".join(novos)


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
    limpo.setenv("INTELLIGENCE_SERVER", "SRV\\\\\\\\I01")
    assert dbi.intelligence_server() == "SRV\\\\\\\\I01"


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
'''


def _read(root: Path, rel: Path) -> str:
    with open(root / rel, encoding="utf-8", newline="") as fh:
        return fh.read()


def check(root: Path) -> list[str]:
    p: list[str] = []
    for rel, velho, _novo, n in EDITS:
        t = _read(root, rel).replace("\r\n", "\n")
        c = t.count(velho)
        if c != n:
            p.append(f"{rel}: ancora esperada {n}x, encontrada {c}x: {velho.strip().splitlines()[0][:70]!r}")
        if "NOME_BASE_LOGIN_CENTRAL" in t or "fonte unica: watcherdb.core.db_identity (2026-10-07)" in t:
            p.append(f"{rel}: ja aplicado")
    if (root / TEST).exists():
        p.append(f"ja existe: {TEST}")
    return sorted(set(p))


def apply(root: Path, preview: bool) -> None:
    textos: dict[Path, str] = {}
    crlf: dict[Path, bool] = {}
    for rel, velho, novo, n in EDITS:
        if rel not in textos:
            bruto = _read(root, rel)
            crlf[rel] = "\r\n" in bruto
            textos[rel] = bruto.replace("\r\n", "\n")
        textos[rel] = textos[rel].replace(velho, novo, n)
        print(f"{rel}: {n}x {velho.strip().splitlines()[0][:60]}")
    print(f"{TEST}: novo (7 testes, incluindo o gate de literais)")
    if preview:
        print("\n--- preview: nada escrito ---")
        return
    for rel, txt in textos.items():
        with open(root / rel, "w", encoding="utf-8", newline="") as fh:
            fh.write(txt.replace("\n", "\r\n") if crlf[rel] else txt)
    (root / TEST).write_text(TEST_SRC, encoding="utf-8", newline="\n")
    print("\naplicado.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.repo.resolve()
    p = check(root)
    if p:
        print("CHECK FALHOU:\n  " + "\n  ".join(p))
        return 1
    print(f"check ok em {root}")
    if a.check:
        return 0
    apply(root, a.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
