"""
2026-08-18 — Filtro por ambiente do dashboard KPIs: cada cartao filtravel tem de
ter o breakdown *_by_env que o frontend ev()/evN() deriva do campo do valor.
Onde faltava, o cartao caia para o total e ignorava o filtro (bug do owner).
Teste estatico (sem BD): backend expoe as chaves; frontend usa ev() (nao n()).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = (ROOT / "api" / "routers" / "intelligence" / "helpers.py").read_text(encoding="utf-8")
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")

# chaves *_by_env que passaram a ser obrigatorias nesta correccao
REQUIRED_BACKEND_KEYS = [
    "full_failed_by_env", "diff_failed_by_env", "other_failed_by_env",  # split de backups
    "down_by_env",                                                       # servicos (alias)
    "unhealthy_by_env",                                                  # alwayson + mirroring
    "critical_items_total_by_env", "warning_items_total_by_env",         # filegroups (alias)
    "p1_by_env", "p3_by_env", "p4_by_env",                               # integridade
    "total_databases_by_env", "total_by_env",                            # resumo executivo (2026-09-09)
]


def test_backend_exposes_required_by_env_keys():
    missing = [k for k in REQUIRED_BACKEND_KEYS if (f'"{k}"' not in HELPERS and f"'{k}'" not in HELPERS)]
    assert not missing, f"helpers.py nao expoe: {missing}"


def test_backup_split_by_env_written_and_defaulted():
    # escrito no caminho normal e nos defaults do except (senao KeyError sob erro)
    for k in ("full_failed_by_env", "diff_failed_by_env", "other_failed_by_env"):
        assert HELPERS.count(f'results["backup_status"]["{k}"]') >= 2, k


def test_frontend_integrity_p3_p4_use_ev_not_plain_n():
    # regressao: P3/P4 usavam n(ig.pX_count) directo -> nunca filtravam
    assert "n(ig.p3_count)" not in PORTAL and "n(ig.p4_count)" not in PORTAL
    assert "ev(ig, 'p3_count')" in PORTAL and "ev(ig, 'p4_count')" in PORTAL


def test_exec_summary_databases_tile_uses_evn_20260909():
    """2026-09-09 (owner): tile "Bases de dados" nao mudava com o filtro de
    ambiente -- lia dba2.total_databases directo. Tem de passar por evN() nas
    2 funcoes (_repTopCards e _repExecCard) e o backend expor a chave."""
    assert "const dbTotal = (+dba2.total_databases || 0)" not in PORTAL
    assert PORTAL.count("const dbTotal = evN(dba2, 'total_databases')") == 2
    assert '"total_databases_by_env"' in HELPERS


def test_overview_databases_probe_not_bound_to_missing_success_key_20260909():
    """2026-09-09: /api/queries/databases/{id} nunca devolveu `success`; o probe
    do banner "N/6 checks failed" e o cartao DBs com Problema exigiam-no ->
    falhavam em TODOS os servidores. Backend passa a devolver success:true e o
    frontend aceita tambem lista nao vazia."""
    space = (ROOT / "api" / "routers" / "queries" / "space.py").read_text(encoding="utf-8")
    assert space.count('"success": True,') >= 2
    assert "'Databases': databasesData?.success === true," not in PORTAL
    assert "const dbDataAvailable = databasesData?.success === true;" not in PORTAL


def test_frontend_ev_derived_keys_have_backend_source():
    """Para cada ev(sec,'campo') do dashboard avancado, a chave by_env derivada
    (campo X_count->X_by_env; count->count_by_env; senao campo+_by_env) tem de
    existir no backend. Cobre o modo de falha silenciosa do evN (cai no total)."""
    derived = set()
    for m in re.finditer(r"ev\([a-z0-9_]+,\s*'([a-z0-9_]+)'\)", PORTAL):
        f = m.group(1)
        if f == "count":
            be = "count_by_env"
        elif f.endswith("_count"):
            be = f[:-len("_count")] + "_by_env"
        else:
            be = f + "_by_env"
        derived.add(be)
    missing = sorted(k for k in derived if (f'"{k}"' not in HELPERS and f"'{k}'" not in HELPERS))
    assert not missing, f"ev() deriva chaves sem fonte no backend (filtro cai no total): {missing}"
