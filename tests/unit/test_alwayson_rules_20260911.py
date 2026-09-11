"""ALWAYS ON REGRA UNICA 2026-09-11: os 5 casos do prompt do TestSprite (TC-011) + contrato dos 3 sitios."""
from pathlib import Path

import pytest

from api.routers.intelligence.alwayson_rules import (
    by_env_distinct_instances, classify, distinct_instances, is_unhealthy, problem_reasons_case, unhealthy_where,
)

ROOT = Path(__file__).resolve().parents[2]


def _row(inst, db, env="PRD", **kw):
    base = {"Instance": inst, "Database": db, "Env": env, "Pri_Synch_Health": "HEALTHY", "Sec_Synch_Health": "HEALTHY",
            "Pri_Synch_State": "SYNCHRONIZED", "Sec_Synch_State": "SYNCHRONIZED", "Pri_Is_Suspended": 0, "Sec_Is_Suspended": 0}
    base.update(kw)
    return base


def test_duas_instancias_unhealthy_reais():
    rows = [_row("SQLHDSPRD211_I01", "FENIX", Sec_Synch_Health="NOT_HEALTHY"),
            _row("SQLHDSPRD405_I01", "MYBAGP2", Sec_Is_Suspended=1, Sec_Synch_State="NOT SYNCHRONIZING")]
    assert all(is_unhealthy(r) for r in rows)
    assert distinct_instances(rows) == {"SQLHDSPRD211_I01", "SQLHDSPRD405_I01"}
    assert classify(rows[1]) == ["Suspended", "Sync State"]


def test_linhas_duplicadas_por_base_contam_uma_instancia():
    # o caso do TC-011: 4 bases em 2 instancias -> cartao 2, modal 4 linhas
    rows = [_row("SQLHDSPRD211_I01", d, Sec_Synch_Health="NOT_HEALTHY") for d in ("DATACAP_01", "FENIX", "MicroStrategyRep")]
    rows.append(_row("SQLHDSPRD405_I01", "MYBAGP2", Sec_Is_Suspended=1))
    assert len(rows) == 4
    assert len(distinct_instances(rows)) == 2


def test_by_env_conta_instancias_distintas():
    # FALHAVA antes deste lote: _count_by_env contava linhas (4), o cartao dizia 2
    rows = [_row("SQLHDSPRD211_I01", d, Sec_Synch_Health="NOT_HEALTHY") for d in ("A", "B", "C")]
    rows.append(_row("SQLHDSPRD405_I01", "MYBAGP2", Sec_Is_Suspended=1))
    rows.append(_row("SQLHDSQLT211_I01", "A", "QLT", Sec_Synch_Health="NOT_HEALTHY"))
    env = by_env_distinct_instances(rows)
    assert env == {"PRD": 2, "QLT": 1, "TST": 0, "Undefined": 0}
    assert sum(env.values()) == len(distinct_instances(rows))


def test_replica_assincrona_em_synchronizing_nao_e_unhealthy():
    sem_coluna = _row("X", "D", Sec_Synch_State="SYNCHRONIZING")
    assert not is_unhealthy(sem_coluna, has_avail_mode=False)
    com_coluna_async = _row("X", "D", Sec_Synch_State="SYNCHRONIZING", Availability_Mode="ASYNCHRONOUS_COMMIT")
    assert not is_unhealthy(com_coluna_async, has_avail_mode=True)
    com_coluna_sync = _row("X", "D", Sec_Synch_State="SYNCHRONIZING", Availability_Mode="SYNCHRONOUS_COMMIT")
    assert classify(com_coluna_sync, has_avail_mode=True) == ["Sync State"]
    # SQL segue a mesma regra
    assert "ASYNCHRONOUS_COMMIT" in unhealthy_where("s", True) and "ASYNCHRONOUS_COMMIT" not in unhealthy_where("s", False)


def test_instancia_suspensa_conta_e_lado_vazio_nao_conta():
    assert classify(_row("X", "D", Pri_Is_Suspended=1)) == ["Suspended"]
    vazio = _row("X", "D", Sec_Synch_Health=None, Sec_Synch_State="", Sec_Is_Suspended=None)
    assert not is_unhealthy(vazio), "o lado vazio de uma replica e' normal, nao avaria"


def test_dados_vazios_ou_indisponiveis():
    assert classify({}) == [] and classify(None) == []
    assert distinct_instances(None) == set()
    assert by_env_distinct_instances(None) == {"PRD": 0, "QLT": 0, "TST": 0, "Undefined": 0}


def test_case_sql_coerente_com_where():
    for am in (False, True):
        w, c = unhealthy_where("s", am), problem_reasons_case("s", am)
        for frag in ("Pri_Synch_Health", "Sec_Is_Suspended", "Pri_Synch_State"):
            assert frag in w and frag in c
        assert ("ASYNCHRONOUS_COMMIT" in c) == am


def test_contrato_os_tres_sitios_usam_a_regra_unica():
    helpers = (ROOT / "api" / "routers" / "intelligence" / "helpers.py").read_text(encoding="utf-8")
    kpis = (ROOT / "api" / "routers" / "intelligence_kpis.py").read_text(encoding="utf-8")
    portal = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
    assert helpers.count("_ao_where(") >= 2 and "_ao_by_env(" in helpers
    assert kpis.count("_ao_where(") >= 1 and "_ao_reasons(" in kpis
    velho = "NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '')"
    assert velho not in kpis, "a modal voltou a ter a regra inline"
    assert "kpiType === 'always-on'" in portal and "kpi_modal.database_s" in portal
