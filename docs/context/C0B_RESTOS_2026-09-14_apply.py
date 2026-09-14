# -*- coding: utf-8 -*-
"""C0b (2026-09-14) -- os dois restos que o smoke de API apanhou DEPOIS do C0.

O C0 (1c14510) fechou o sql_variant vindo de SERVERPROPERTY, mas o erro continuou a aparecer no log
com o servico ja' reiniciado. A origem que faltava e' outra: sys.configurations.

  1. "ODBC SQL type -16 is not yet supported. column-index=1 type=-16"
     `sys.configurations.value` e `value_in_use` sao sql_variant, tipo que o driver ODBC nao
     transporta. Duas consultas em security_analysis.py devolvem-nos sem CAST. O "column-index=1"
     bate certo com a primeira: as colunas sao (auth_mode, auth_mode_value) e o indice 1 e' a segunda.
     Comparar sql_variant dentro de um CASE (WHEN value = 1) e' valido e fica como esta'; o que parte
     e' DEVOLVER a coluna.

  2. 156 "Incorrect syntax near the keyword 'UNION'"
     TEMPDB_HEAVY_CONSUMERS_HISTORY tem `ORDER BY` no fim da primeira metade, imediatamente antes do
     `UNION ALL`. Em T-SQL o ORDER BY so' e' permitido no fim da consulta inteira, nunca num ramo do
     meio -- e o parser aponta o UNION. Como cada metade precisa do seu ORDER BY para o TOP 20 fazer
     sentido, a correccao e' embrulhar cada metade numa tabela derivada, onde TOP+ORDER BY sao legais.
     Endpoint afectado: /api/queries/tempdb-culprits (o "[TempDB Culprits]" do log).

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/C0B_RESTOS_2026-09-14_apply.py --check
  py docs/context/C0B_RESTOS_2026-09-14_apply.py
  py -m pytest tests/unit/test_c0b_restos_20260914.py tests/unit/test_c0_classes_20260914.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "security": Path("modules/monitoring/security_analysis.py"),
    "queries": Path("modules/monitoring/queries.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_c0b_restos_20260914.py"),
}
MARK = "AS parte_spills"

EDITS = {
    # 1) sql_variant devolvido por sys.configurations
    "security": [
        ("                value AS auth_mode_value\n",
         "                CAST(value AS INT) AS auth_mode_value\n", 1),  # C0b: sql_variant nao viaja no ODBC (tipo -16)
        ("                name,\n                value_in_use,\n                value,\n                description\n",
         "                name,\n"
         "                CAST(value_in_use AS INT) AS value_in_use,\n"
         "                CAST(value AS INT) AS value,\n"
         "                description\n", 1),
    ],
    # 2) ORDER BY num ramo do UNION ALL
    "queries": [
        ("    -- Parte 1: Queries com maiores spills (hash/sort spills para TempDB)\n    SELECT TOP 20\n",
         "    -- Parte 1: Queries com maiores spills (hash/sort spills para TempDB)\n"
         "    -- C0b 2026-09-14: cada metade vai numa tabela derivada. ORDER BY num ramo do UNION ALL\n"
         "    -- e' erro 156 ('Incorrect syntax near UNION'); dentro da derivada, TOP+ORDER BY e' legal.\n"
         "    SELECT * FROM (\n"
         "    SELECT TOP 20\n", 1),
        ("    WHERE qs.total_spills > 0  -- Apenas queries com spills\n    ORDER BY qs.total_spills DESC\n\n    UNION ALL\n",
         "    WHERE qs.total_spills > 0  -- Apenas queries com spills\n"
         "    ORDER BY qs.total_spills DESC\n"
         "    ) AS parte_spills\n\n"
         "    UNION ALL\n", 1),
        ("    -- Parte 2: Sessões com maior uso histórico de TempDB (desde restart)\n    SELECT TOP 20\n",
         "    -- Parte 2: Sessões com maior uso histórico de TempDB (desde restart)\n"
         "    SELECT * FROM (\n"
         "    SELECT TOP 20\n", 1),
        ("    ORDER BY (su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) DESC\n    \"\"\"\n",
         "    ORDER BY (su.user_objects_alloc_page_count + su.internal_objects_alloc_page_count) DESC\n"
         "    ) AS parte_sessoes\n    \"\"\"\n", 1),
    ],
}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **C0b: os dois restos que o smoke de API apanhou depois do C0.** O resumo de segurança continuava a falhar\n"
                  "  porque `sys.configurations` devolve `value` e `value_in_use` como `sql_variant`, um tipo que o driver não\n"
                  "  transporta; o lote anterior só tinha convertido o `SERVERPROPERTY`. E o detalhe de culpados do TempDB dava\n"
                  "  erro de sintaxe porque a primeira metade da consulta acaba com `ORDER BY` mesmo antes do `UNION ALL`, o que\n"
                  "  o T-SQL não permite: cada metade passa a ir numa tabela derivada, onde `TOP` com `ORDER BY` é legal. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    if MARK in src["queries"].read_bytes().decode("utf-8"):
        print("[ABORT] ja aplicado"); return 1
    out = {k: _apply(src[k].read_bytes().decode("utf-8"), e, k) for k, e in EDITS.items()}
    if src["changelog"].exists():
        out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    print("[ok] anchors: 2x sql_variant; 4x tabela derivada; changelog")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    compile(TEST_SRC, str(REL["test"]), "exec")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_c0b_restos_20260914.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
