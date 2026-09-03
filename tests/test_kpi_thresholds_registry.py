"""Fase 0 thresholds (2026-08-04) — fonte unica + anti-drift.

Tres garantias:
1. Integridade do registry (estrutura + valores em vigor "congelados" —
   mudar um default do produto exige mexer AQUI conscientemente).
2. O backend consome o registry (identidade do dict de backup delays).
3. Anti-regressao: os literais antigos NAO voltam a aparecer hardcoded
   nos consumidores do backend (helpers.py / intelligence_kpis.py).
"""
from pathlib import Path

from api.kpi_thresholds_registry import (
    THRESHOLDS,
    BACKUP_DELAY_THRESHOLDS,
    registry_as_list,
    value,
)

ROOT = Path(__file__).resolve().parents[1]


def test_registry_integrity():
    assert len(THRESHOLDS) >= 14
    for key, t in THRESHOLDS.items():
        assert t["label"], key
        assert "warning" in t and "critical" in t, key
        assert t["source"], key
        assert isinstance(t["configurable_f1"], bool), key
    listed = registry_as_list()
    assert len(listed) == len(THRESHOLDS)
    assert all("is_mirror" in row for row in listed)


def test_valores_em_vigor_fase0():
    # Golden dos defaults do produto — mudar aqui = decisao consciente
    assert value("tempdb_usage", "warning") == 60
    assert value("tempdb_usage", "critical") == 80
    assert value("disk_latency", "warning") == 20
    assert value("disk_latency", "critical") == 50
    assert value("long_locks", "warning") == 60
    assert value("long_locks", "critical") == 600
    assert value("cpu_critical", "critical") == 95
    # Fase 1.5 (2026-08-13): filegroups migrado de embedded-sql p/ registry
    assert value("filegroup_free_pct", "warning") == 5
    assert value("filegroup_free_pct", "critical") == 2
    assert value("filegroup_unlimited_free_gb", "warning") == 10
    assert value("filegroup_unlimited_free_gb", "critical") == 5
    # Fase 1.5 lote 2: deadlocks classificado no backend (era espelho da view)
    assert value("deadlocks_state", "warning") == 10
    assert value("deadlocks_state", "critical") == 20
    assert THRESHOLDS["deadlocks_state"]["configurable_f1"] is True
    assert THRESHOLDS["deadlocks_state"]["source"].startswith("backend")
    # Fase 1.5 lote 3: tlog + processes + integrity migrados para backend
    assert value("tlog_usage", "warning") == 85
    assert value("tlog_usage", "critical") == 95
    assert value("processes_runnable", "warning") == 20
    assert value("processes_runnable", "critical") == 50
    assert value("integrity_checkdb_age", "warning") == 30
    assert value("integrity_checkdb_age", "critical") is None
    for kpi in ("tlog_usage", "processes_runnable", "integrity_checkdb_age"):
        assert THRESHOLDS[kpi]["configurable_f1"] is True, kpi
        assert THRESHOLDS[kpi]["source"].startswith("backend"), kpi
    assert BACKUP_DELAY_THRESHOLDS == {
        "FULL": {"warning_h": 120, "critical_h": 168},
        "DIFF": {"warning_h": 24, "critical_h": 30},
        "LOG": {"warning_h": 1, "critical_h": 2},
    }


def test_backend_sem_literais_antigos():
    """Os thresholds hardcoded removidos na Fase 0 nao podem regressar."""
    proibidos = {
        "api/routers/intelligence/helpers.py": [
            "usage_pct >= 80",
            "usage_pct >= 60",
            "Processor_Pct >= 95",
            "Avg_Read_Latency_MS >= 50 OR Avg_Write_Latency_MS >= 50",
            "Avg_Read_Latency_MS >= 20 OR Avg_Write_Latency_MS >= 20",
            "'FULL': {'warning_h': 120",
            "> 600]",
            # Fase 1.5: literais de filegroups removidos (card + disk_query)
            "Eff_Free_Pct >= 5",
            "Eff_Free_Pct >= 2",
            "Eff_Free_Pct <  2",
            "<= 5120",
            "<= 10240",
        ],
        "api/routers/intelligence_kpis.py": [
            "usage_pct >= 80",
            "Avg_Read_Latency_MS >= 50 OR Avg_Write_Latency_MS >= 50",
            "threshold = 50 if is_critical else 20",
            # Fase 1.5: literais de filegroups removidos (modal detail)
            "Percent_Used >  98",
            "Percent_Used >  95",
            "<= 5120",
            "<= 10240",
        ],
    }
    falhas = []
    for rel, needles in proibidos.items():
        texto = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for n in needles:
            if n in texto:
                falhas.append(f"{rel}: literal hardcoded regressou: {n!r}")
    assert not falhas, "\n".join(falhas)


def test_direccao_e_cap_fase15():
    """Fase 1.5: KPIs menor=pior declaram higher_is_worse=False; o cap do
    warning de filegroup_free_pct protege o tier Attention fixo (<=10)."""
    for kpi in ("filegroup_free_pct", "filegroup_unlimited_free_gb"):
        t = THRESHOLDS[kpi]
        assert t.get("higher_is_worse") is False, kpi
        assert t["configurable_f1"] is True, kpi
        assert t["source"].startswith("backend"), kpi
        # defaults respeitam a propria direccao (warning > critical)
        assert t["warning"] > t["critical"], kpi
    assert THRESHOLDS["filegroup_free_pct"]["warning_cap"] == 10
    # restantes KPIs: default maior=pior (flag ausente ou True)
    assert THRESHOLDS["tempdb_usage"].get("higher_is_worse", True) is True
    # o espelho antigo nao pode coexistir com as chaves novas (UI duplicada)
    assert "filegroup_usage" not in THRESHOLDS


def test_helpers_usa_resolve():
    """Fase 1: helpers._th passa a ser o resolvedor de overrides (nao value)."""
    from api.routers.intelligence import helpers
    from api.threshold_overrides import resolve

    assert helpers._th is resolve


def test_overrides_golden_tabela_vazia_igual_registry():
    """CONTRATO F1: sem overrides (tabela ausente/vazia), resolve() devolve
    EXACTAMENTE o default do registry — comportamento identico a hoje."""
    from api import threshold_overrides as ovr
    from api.kpi_thresholds_registry import value

    # forcar cache vazio (simula tabela ausente)
    ovr._cache = {}
    ovr._cache_ts = 0.0
    for kpi in ("tempdb_usage", "disk_latency", "long_locks", "cpu_critical",
                "backup_delay_full", "backup_delay_diff", "backup_delay_log"):
        for level in ("warning", "critical"):
            assert ovr.resolve(kpi, level) == value(kpi, level), f"{kpi}.{level}"


def test_override_aplica_e_precedencia():
    """resolve() aplica override e respeita precedencia DATABASE>INSTANCE>ENV>GLOBAL."""
    from api import threshold_overrides as ovr

    ovr._cache = {
        "tempdb_usage": {
            "GLOBAL\x1f": {"warning": 55.0, "critical": 75.0},
            "ENV\x1fPRD": {"warning": 50.0, "critical": None},
            "INSTANCE\x1fSQLX": {"warning": None, "critical": 70.0},
        }
    }
    ovr._cache_ts = 9e18  # nunca expira durante o teste
    try:
        # GLOBAL aplica-se sem contexto
        assert ovr.resolve("tempdb_usage", "warning") == 55.0
        # ENV mais especifico que GLOBAL
        assert ovr.resolve("tempdb_usage", "warning", env="PRD") == 50.0
        # ENV sem critical cai para GLOBAL
        assert ovr.resolve("tempdb_usage", "critical", env="PRD") == 75.0
        # INSTANCE mais especifico; warning None cai para ENV/GLOBAL
        assert ovr.resolve("tempdb_usage", "critical", instance="SQLX", env="PRD") == 70.0
        assert ovr.resolve("tempdb_usage", "warning", instance="SQLX", env="PRD") == 50.0
        # KPI sem override cai para o registry
        assert ovr.resolve("disk_latency", "warning") == 20
    finally:
        ovr._cache = {}
        ovr._cache_ts = 0.0
