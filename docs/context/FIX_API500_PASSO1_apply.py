"""FIX API 500 (achados 1-4 da 1.a corrida do TestSukita v1, FINDINGS_TESTSUKITA_2026-09-11) - PASSO 1.

BLOCO PROVA: tests/unit/test_api_500s_20260911.py falha hoje nos 4 pontos e passa depois; o smoke de API do
TestSukita (viewer) deixa de listar os 8 endpoints a 500; o SQL da migracao (must_change_password) corre-o o owner.

  1. api/routers/sqlserver_kpis.py: 5 endpoints 500 por `Decimal is not JSON serializable`. O router e' legado
     (0 referencias no portal) mas tem consumidores em testes e acceptance; corrige-se a serializacao no proprio
     router (JSONResponse com jsonable_encoder) em vez de desmontar. Decisao de desmontar fica registada para o owner.
  2a. modules/monitoring/queries.py:1605: `sys.dm_io_virtual_file_stats(NULL, NULL) WITH(NOLOCK)` - hint numa TVF e'
     erro de sintaxe ("Incorrect syntax near the keyword 'with'") -> /api/queries/database-io-stats 500 desde sempre.
  2b. modules/monitoring/queries.py:1125: comentario com '≈' (U+2248) dentro de TEMPDB_GROWTH_ANALYSIS -> pyodbc
     UnicodeEncodeError charmap -> /api/queries/tempdb-growth-analysis 500 desde sempre.
  2c. modules/monitoring/backup_pattern_analysis.py:220 e :368: execute_query(..., params=[...]) que a assinatura
     nao aceita -> padroes de backup nunca calculados (degradacao silenciosa, endpoint devolve 200 sem dados).
  3. watcherdb/api/routers/security.py:177: get_server_security_analysis devolve JSONResponse e get_critical_issues
     trata-o como dict -> /api/monitoring/security/server/{id}/critical 500.
  4. Migracao must_change_password: bloco do canonico (INSTALACAO_COMPLETA_UNIFICADA.sql 10136-10142) para o owner
     correr na WatcherDB_Intelligence da 8434 (SQL no PASSO 2).

Fora: achado 5 (active-sessions 976) por reproduzir; queries/helpers.py execute_query_on_server usa
use_windows_auth=True (ponto 2 do ranking, lote proprio).

Uso (raiz do repo):  py docs/context/FIX_API500_PASSO1_apply.py
Depois:              pwsh docs/context/FIX_API500_PASSO2_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KPIS = ROOT / "api" / "routers" / "sqlserver_kpis.py"
QUERIES = ROOT / "modules" / "monitoring" / "queries.py"
BPA = ROOT / "modules" / "monitoring" / "backup_pattern_analysis.py"
SEC = ROOT / "watcherdb" / "api" / "routers" / "security.py"
TEST = ROOT / "tests" / "unit" / "test_api_500s_20260911.py"
MARK = "FIX API 500 2026-09-11"


def rep(text: str, old: str, new: str, label: str, expected: int = 1) -> str:
    n = text.count(old)
    if n != expected:
        sys.exit(f"ABORT [{label}]: esperava {expected}, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


K_OLD = "from fastapi.responses import JSONResponse\n"
K_NEW = '''from fastapi.responses import JSONResponse as _StarletteJSONResponse
from fastapi.encoders import jsonable_encoder as _jsonable_encoder
import json as _json


class JSONResponse(_StarletteJSONResponse):
    """FIX API 500 2026-09-11: o servico devolve Decimal/datetime e 5 endpoints deste router rebentavam com
    'Object of type Decimal is not JSON serializable' (TestSukita api_smoke). Serializa via jsonable_encoder."""

    def render(self, content) -> bytes:
        return _json.dumps(_jsonable_encoder(content), ensure_ascii=False, allow_nan=False,
                           separators=(",", ":")).encode("utf-8")
'''

Q1_OLD = "    FROM sys.dm_io_virtual_file_stats(NULL, NULL) WITH(NOLOCK)\n"
Q1_NEW = "    FROM sys.dm_io_virtual_file_stats(NULL, NULL)  -- FIX API 500 2026-09-11: hint de tabela numa TVF e' erro de sintaxe\n"
Q2_OLD = "        -- Se MinSize ≈ CurrentSize, SHRINK não vai reduzir nada significativo.\n"
Q2_NEW = "        -- Se MinSize ~= CurrentSize, SHRINK nao vai reduzir nada significativo. (FIX API 500 2026-09-11: sem U+2248, o driver rejeitava)\n"

B_OLD = "        result = await self.sql_monitoring.execute_query(server_id, query, params=[database_name])\n"
B_NEW = '''        # FIX API 500 2026-09-11: execute_query nao aceita params (assinatura: server_id, query, database);
        # a chamada rebentava em TypeError e os padroes de backup nunca eram calculados. Literal escapado.
        query = query.replace("database_name = ?", "database_name = N'" + str(database_name).replace("'", "''") + "'")
        result = await self.sql_monitoring.execute_query(server_id, query)
'''

S1_OLD = "from fastapi.responses import JSONResponse\nfrom typing import Dict, Any, List, Optional\nimport logging\n"
S1_NEW = "from fastapi.responses import JSONResponse\nfrom typing import Dict, Any, List, Optional\nimport json\nimport logging\n"
S2_OLD = '''        result = await get_server_security_analysis(server_id, request, use_cache=True)

        if not result.get("success"):
'''
S2_NEW = '''        result = await get_server_security_analysis(server_id, request, use_cache=True)
        # FIX API 500 2026-09-11: a analise devolve JSONResponse; aqui precisamos do dict (era AttributeError .get).
        if isinstance(result, JSONResponse):
            result = json.loads(bytes(result.body).decode("utf-8"))

        if not result.get("success"):
'''

TEST_SRC = '''"""FIX API 500 2026-09-11: regressoes dos 4 defeitos apanhados pelo smoke de API do TestSukita v1."""
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_io_stats_sem_hint_em_tvf():
    from modules.monitoring.queries import SQLQueries
    q = SQLQueries.DATABASE_IO_STATS
    assert "dm_io_virtual_file_stats(NULL, NULL)" in q
    assert not re.search(r"dm_io_virtual_file_stats\\([^)]*\\)\\s*WITH\\s*\\(", q, re.I), "hint de tabela numa TVF = Incorrect syntax near 'with'"


def test_queries_sem_caracteres_fora_do_cp1252():
    from modules.monitoring.queries import SQLQueries
    maus = []
    for nome in dir(SQLQueries):
        v = getattr(SQLQueries, nome)
        if isinstance(v, str) and not nome.startswith("_"):
            try:
                v.encode("cp1252")
            except UnicodeEncodeError as e:
                maus.append((nome, v[e.start:e.end], hex(ord(v[e.start]))))
    assert not maus, f"caracteres que o driver rejeita (UnicodeEncodeError charmap, e.g. U+2248): {maus[:5]}"


def test_backup_pattern_analysis_nao_passa_params():
    src = (ROOT / "modules" / "monitoring" / "backup_pattern_analysis.py").read_text(encoding="utf-8")
    assert "params=[" not in src, "execute_query(server_id, query, database=None) nao aceita params"
    assert src.count("database_name = N'") >= 2


def test_sqlserver_kpis_jsonresponse_serializa_decimal_e_datetime():
    from api.routers.sqlserver_kpis import JSONResponse
    r = JSONResponse(content={"x": Decimal("1.50"), "t": datetime(2026, 9, 11, 14, 0), "n": None})
    body = json.loads(bytes(r.body).decode("utf-8"))
    assert body["x"] == 1.5 and body["t"].startswith("2026-09-11T14:00") and body["n"] is None


def test_security_critical_converte_jsonresponse():
    src = (ROOT / "watcherdb" / "api" / "routers" / "security.py").read_text(encoding="utf-8")
    i = src.index("async def get_critical_issues")
    trecho = src[i:i + 1200]
    assert "isinstance(result, JSONResponse)" in trecho and "json.loads" in trecho
'''


def main() -> None:
    k = KPIS.read_text(encoding="utf-8")
    if MARK in k:
        print("Ja aplicado: sqlserver_kpis")
    else:
        k = rep(k, K_OLD, K_NEW, "kpis JSONResponse"); compile(k, str(KPIS), "exec")
        KPIS.write_text(k, encoding="utf-8", newline="\n"); print("OK: api/routers/sqlserver_kpis.py (JSONResponse serializa Decimal)")
    q = QUERIES.read_text(encoding="utf-8")
    if MARK in q:
        print("Ja aplicado: queries.py")
    else:
        q = rep(q, Q1_OLD, Q1_NEW, "io stats WITH"); q = rep(q, Q2_OLD, Q2_NEW, "tempdb U+2248"); compile(q, str(QUERIES), "exec")
        QUERIES.write_text(q, encoding="utf-8", newline="\n"); print("OK: modules/monitoring/queries.py (2 queries)")
    b = BPA.read_text(encoding="utf-8")
    if MARK in b:
        print("Ja aplicado: backup_pattern_analysis")
    else:
        b = rep(b, B_OLD, B_NEW, "bpa params", expected=2); compile(b, str(BPA), "exec")
        BPA.write_text(b, encoding="utf-8", newline="\n"); print("OK: modules/monitoring/backup_pattern_analysis.py (2 chamadas)")
    s = SEC.read_text(encoding="utf-8")
    if MARK in s:
        print("Ja aplicado: security.py")
    else:
        s = rep(s, S1_OLD, S1_NEW, "security import json"); s = rep(s, S2_OLD, S2_NEW, "security get"); compile(s, str(SEC), "exec")
        SEC.write_text(s, encoding="utf-8", newline="\n"); print("OK: watcherdb/api/routers/security.py")
    if TEST.exists():
        print("Ja existe: teste")
    else:
        compile(TEST_SRC, str(TEST), "exec"); TEST.write_text(TEST_SRC, encoding="utf-8", newline="\n"); print("OK: tests/unit/test_api_500s_20260911.py")
    print("Proximo: pwsh docs/context/FIX_API500_PASSO2_commit.ps1")


if __name__ == "__main__":
    main()
