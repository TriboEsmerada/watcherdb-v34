"""FIX 2026-09-09 (3 bugs, 2 screenshots do owner) -- script de aplicacao.

Modo Consultor: a AI so escreve em docs/context/. Este script faz as edicoes
por ti, com anchors exactos; aborta se algum anchor nao bater (nada meio-feito).

BUG 1 -- KPIs > Resumo Executivo: "Bases de dados" nao muda ao filtrar ambiente.
  Causa: o tile calcula `dbTotal` directamente de dba2.total_databases, sem passar
  pelo helper evN() que os outros tiles usam (portal, _repTopCards e _repExecCard).
  E mesmo passando, o backend nao expunha `total_databases_by_env` -- evN() cai no
  total da frota quando a chave falta (mesmo anti-padrao do FIND-20260818-101).
  Fix: backend expoe total_databases_by_env (+ alias total_by_env) com a MESMA
  fonte do total (DET_VIEW) classificada por KPI_MSSQL_INST_ENVS (padrao 2026-08-07);
  frontend usa evN() nas 2 funcoes; teste de contrato ganha a chave.

BUG 2 -- Overview do servidor: banner "1/6 checks to this server failed ...
  Failed: Databases" + cartao "DBs with Issues" em N/A, com a tabela de
  Databases (97/97) carregada logo abaixo e o log a mostrar
  `GET /api/queries/databases/SQLHDSQLT105_I01 200`.
  Causa: o probe e o cartao exigem `databasesData.success === true`, mas o
  endpoint /api/queries/databases/{id} devolve {server_id, databases,
  server_info, cached} -- NUNCA teve chave success. Logo o check "Databases"
  falha em TODOS os servidores desde que o banner existe (2026-08-07), e o
  cartao "DBs com Problema" esta sempre N/D. Nao e' este servidor: e' o contrato.
  Fix: endpoint passa a devolver success:true (cache e fresco) + frontend aceita
  tambem uma lista de databases nao vazia (tolerante a respostas antigas).

BUG 3 -- log: `Arithmetic overflow error converting expression to data type
  int (8115)` em SQLHDSQLT105_I01 e SQLMDMPRD03_I01 (16 ocorrencias).
  Causa: plan_cache_query faz SUM(size_in_bytes) sobre sys.dm_exec_cached_plans;
  size_in_bytes e' INT e SUM(int) devolve INT em SQL Server -> rebenta quando a
  plan cache passa 2 GB (os 2 servidores sao DW/MDM com cache grande). O
  _safe_query engole o erro (logger.debug) e a seccao Plan Cache fica vazia sem
  ninguem saber. Mesmo padrao duplicado em modules/monitoring/queries.py.
  Fix: SUM(CAST(size_in_bytes AS BIGINT)) nas 2 copias (5 expressoes cada).
  NAO e' a causa do banner (o banner e' o bug 2) -- sao problemas independentes
  que a mesma captura expos.

Uso (raiz do repo):
  py docs/context/FIX_KPI_DBENV_PROBE_PLANCACHE_2026-09-09_apply.py --check    # so valida anchors
  py docs/context/FIX_KPI_DBENV_PROBE_PLANCACHE_2026-09-09_apply.py --preview DIR  # escreve copias em DIR
  py docs/context/FIX_KPI_DBENV_PROBE_PLANCACHE_2026-09-09_apply.py            # aplica

Depois de aplicar:
  py -m pytest tests/unit/test_kpi_env_breakdown_20260818.py -q
  restart do servico 8434 (backend mudou: helpers.py, space.py, memory_analysis.py)
  Ctrl+F5 no portal; validar: KPIs > clicar PRD -> "Bases de dados" muda;
  Overview de qualquer servidor -> banner desaparece, cartao DBs com Problema com numero.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PORTAL = ROOT / "templates" / "watcherdb_portal.html"
SPACE = ROOT / "api" / "routers" / "queries" / "space.py"
HELPERS = ROOT / "api" / "routers" / "intelligence" / "helpers.py"
MEMORY = ROOT / "modules" / "monitoring" / "memory_analysis.py"
QUERIES = ROOT / "modules" / "monitoring" / "queries.py"
TEST = ROOT / "tests" / "unit" / "test_kpi_env_breakdown_20260818.py"

# (ficheiro, old, new, ocorrencias_esperadas)
EDITS: list[tuple[Path, str, str, int]] = []


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    EDITS.append((path, old, new, count))


# ---------------------------------------------------------------- BUG 1 --
edit(PORTAL,
     "const dbTotal = (+dba2.total_databases || 0) || (+dba2.total_count || 0);",
     "const dbTotal = evN(dba2, 'total_databases') || evN(dba2, 'total_count');  // 2026-09-09: respeita filtro de ambiente (era total da frota)",
     count=2)

edit(HELPERS,
     '        "db_availability": {\n'
     '            "abnormal_count": 0,\n'
     '            "total_count": 0,\n'
     '            "total_databases": 0,\n'
     '            "instances": []\n'
     '        },',
     '        "db_availability": {\n'
     '            "abnormal_count": 0,\n'
     '            "total_count": 0,\n'
     '            "total_databases": 0,\n'
     '            "total_databases_by_env": {},\n'
     '            "total_by_env": {},\n'
     '            "instances": []\n'
     '        },')

edit(HELPERS,
     '                logger.debug(f"DB Availability por ambiente: {results[\'db_availability\'][\'by_environment\']}")\n',
     '                logger.debug(f"DB Availability por ambiente: {results[\'db_availability\'][\'by_environment\']}")\n'
     '\n'
     '                # 2026-09-09 (owner): o tile "Bases de dados" do resumo executivo\n'
     '                # nao mudava ao filtrar por ambiente. evN() deriva\n'
     '                # total_databases_by_env e, sem a chave, cai no total da frota\n'
     '                # (mesmo anti-padrao do FIND-20260818-101). MESMA fonte do total\n'
     '                # (DET_VIEW) e classificacao por INST_ENVS (padrao 2026-08-07),\n'
     '                # para a soma por ambiente bater com o total_databases.\n'
     '                query_total_by_env = f"""\n'
     '                SELECT ISNULL(e.Env, \'Undefined\') AS Env, COUNT(*) AS Cnt\n'
     '                FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW d WITH (NOLOCK)\n'
     '                LEFT JOIN {INTELLIGENCE_SCHEMA}.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)\n'
     '                    ON e.Instance = d.Instance\n'
     '                GROUP BY ISNULL(e.Env, \'Undefined\')\n'
     '                """\n'
     '                total_by_env_data = await execute_intelligence_query_async(query_total_by_env, raise_on_error=False) or []\n'
     '                total_by_env = {\'PRD\': 0, \'QLT\': 0, \'TST\': 0, \'Undefined\': 0}\n'
     '                for row in total_by_env_data:\n'
     '                    total_by_env[str(row.get(\'Env\') or \'Undefined\')] = int(row.get(\'Cnt\') or 0)\n'
     '                results["db_availability"]["total_databases_by_env"] = total_by_env\n'
     '                results["db_availability"]["total_by_env"] = total_by_env\n'
     '                logger.debug(f"DB Availability total por ambiente: {total_by_env}")\n')

edit(TEST,
     '    "p1_by_env", "p3_by_env", "p4_by_env",                               # integridade\n'
     ']',
     '    "p1_by_env", "p3_by_env", "p4_by_env",                               # integridade\n'
     '    "total_databases_by_env", "total_by_env",                            # resumo executivo (2026-09-09)\n'
     ']')

edit(TEST,
     '\ndef test_frontend_ev_derived_keys_have_backend_source():',
     '\ndef test_exec_summary_databases_tile_uses_evn_20260909():\n'
     '    """2026-09-09 (owner): tile "Bases de dados" nao mudava com o filtro de\n'
     '    ambiente -- lia dba2.total_databases directo. Tem de passar por evN() nas\n'
     '    2 funcoes (_repTopCards e _repExecCard) e o backend expor a chave."""\n'
     '    assert "const dbTotal = (+dba2.total_databases || 0)" not in PORTAL\n'
     '    assert PORTAL.count("const dbTotal = evN(dba2, \'total_databases\')") == 2\n'
     '    assert \'"total_databases_by_env"\' in HELPERS\n'
     '\n'
     '\n'
     'def test_overview_databases_probe_not_bound_to_missing_success_key_20260909():\n'
     '    """2026-09-09: /api/queries/databases/{id} nunca devolveu `success`; o probe\n'
     '    do banner "N/6 checks failed" e o cartao DBs com Problema exigiam-no ->\n'
     '    falhavam em TODOS os servidores. Backend passa a devolver success:true e o\n'
     '    frontend aceita tambem lista nao vazia."""\n'
     '    space = (ROOT / "api" / "routers" / "queries" / "space.py").read_text(encoding="utf-8")\n'
     '    assert space.count(\'"success": True,\') >= 2\n'
     '    assert "\'Databases\': databasesData?.success === true," not in PORTAL\n'
     '    assert "const dbDataAvailable = databasesData?.success === true;" not in PORTAL\n'
     '\n'
     '\n'
     'def test_frontend_ev_derived_keys_have_backend_source():')

# ---------------------------------------------------------------- BUG 2 --
edit(SPACE,
     '            return JSONResponse(content={\n'
     '                "server_id": server_id,\n'
     '                "databases": cached_entry["data"],',
     '            return JSONResponse(content={\n'
     '                "success": True,  # 2026-09-09: probe/cartao do Overview exigem esta chave\n'
     '                "server_id": server_id,\n'
     '                "databases": cached_entry["data"],')

edit(SPACE,
     '        return JSONResponse(content={\n'
     '            "server_id": server_id,\n'
     '            "databases": serialized_result,',
     '        return JSONResponse(content={\n'
     '            "success": True,  # 2026-09-09: probe/cartao do Overview exigem esta chave\n'
     '            "server_id": server_id,\n'
     '            "databases": serialized_result,')

edit(PORTAL,
     "'Databases': databasesData?.success === true,",
     "'Databases': databasesData?.success === true || (Array.isArray(databasesData?.databases) && databasesData.databases.length > 0),  // 2026-09-09: endpoint nao tinha success -> check falhava sempre")

edit(PORTAL,
     "const dbDataAvailable = databasesData?.success === true;",
     "const dbDataAvailable = databasesData?.success === true || (Array.isArray(databasesData?.databases) && databasesData.databases.length > 0);  // 2026-09-09: idem probe")

# ---------------------------------------------------------------- BUG 3 --
for f in (MEMORY, QUERIES):
    edit(f, "SUM(size_in_bytes)", "SUM(CAST(size_in_bytes AS BIGINT))", count=2)
    edit(f, "THEN size_in_bytes ELSE 0 END", "THEN CAST(size_in_bytes AS BIGINT) ELSE 0 END", count=3)


# ------------------------------------------------------------------ run --
def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    preview_dir = None
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv):
            print("--preview precisa de DIR")
            return 2
        preview_dir = Path(argv[i + 1]).resolve()

    # Preserva o EOL de cada ficheiro (space.py e memory_analysis.py sao CRLF;
    # read_text/write_text normalizariam e o diff apanharia o ficheiro inteiro).
    contents: dict[Path, str] = {}
    eols: dict[Path, str] = {}
    for p in {e[0] for e in EDITS}:
        if not p.exists():
            print(f"[ABORT] nao existe: {p}")
            return 1
        raw = p.read_bytes().decode("utf-8")
        contents[p] = raw
        eols[p] = "\r\n" if "\r\n" in raw else "\n"

    problems = 0
    applied = 0
    skipped = 0
    for path, old, new, count in EDITS:
        text = contents[path]
        old = old.replace("\n", eols[path])
        new = new.replace("\n", eols[path])
        if new in text and old not in text:
            skipped += 1
            print(f"[skip] ja aplicado: {path.name}: {old[:60]!r}")
            continue
        n = text.count(old)
        if n != count:
            problems += 1
            print(f"[ABORT] {path.name}: esperado {count}x, encontrado {n}x: {old[:80]!r}")
            continue
        contents[path] = text.replace(old, new)
        applied += 1
        print(f"[ok] {path.name}: {count}x {old[:60]!r}")

    if problems:
        print(f"\n{problems} anchor(s) falharam -- NADA escrito.")
        return 1

    if check_only:
        print(f"\n--check OK: {applied} edicoes aplicaveis, {skipped} ja aplicadas. Nada escrito.")
        return 0

    if preview_dir is not None:
        for path, text in contents.items():
            out = preview_dir / path.relative_to(ROOT)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(text.encode("utf-8"))
            print(f"[preview] {out}")
        print(f"\n--preview OK: copias em {preview_dir}. Repo intacto.")
        return 0

    for path, text in contents.items():
        path.write_bytes(text.encode("utf-8"))
        print(f"[write] {path.relative_to(ROOT)}")
    print(f"\nAplicado: {applied} edicoes ({skipped} ja estavam). Corre agora:\n"
          "  py -m pytest tests/unit/test_kpi_env_breakdown_20260818.py -q\n"
          "  restart do servico 8434 + Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
