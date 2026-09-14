"""
2026-09-14 -- C0b: sql_variant de sys.configurations e ORDER BY num ramo do UNION ALL.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEC = (ROOT / "modules" / "monitoring" / "security_analysis.py").read_text(encoding="utf-8")
QRY = (ROOT / "modules" / "monitoring" / "queries.py").read_text(encoding="utf-8")


def test_sys_configurations_nao_devolve_sql_variant():
    assert "value AS auth_mode_value" not in SEC.replace("CAST(value AS INT) AS auth_mode_value", "")
    assert "CAST(value AS INT) AS auth_mode_value" in SEC
    assert "CAST(value_in_use AS INT) AS value_in_use" in SEC


def test_comparacao_dentro_do_case_fica_intacta():
    # comparar sql_variant e' valido; so' devolver a coluna e' que parte
    assert "WHEN value = 1 THEN" in SEC


def test_order_by_nao_fica_antes_do_union_all():
    m = re.search(r'TEMPDB_HEAVY_CONSUMERS_HISTORY = """(.*?)"""', QRY, re.S)
    assert m
    linhas = m.group(1).splitlines()
    # o UNION ALL a serio e' a linha que so' tem isso; comentarios que mencionam UNION nao contam
    i = next(n for n, l in enumerate(linhas) if l.strip() == "UNION ALL")
    antes = [l for l in linhas[:i] if l.strip() and not l.strip().startswith("--")]
    # a ultima instrucao antes do UNION tem de ser o fecho da tabela derivada, nao um ORDER BY
    assert antes[-1].strip() == ") AS parte_spills", antes[-1]
    sql = m.group(1)
    assert sql.count("SELECT * FROM (") == 2
    assert ") AS parte_sessoes" in sql
