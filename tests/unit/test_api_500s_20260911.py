"""FIX API 500 2026-09-11: regressoes dos 4 defeitos apanhados pelo smoke de API do TestSukita v1."""
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
    assert not re.search(r"dm_io_virtual_file_stats\([^)]*\)\s*WITH\s*\(", q, re.I), "hint de tabela numa TVF = Incorrect syntax near 'with'"


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
