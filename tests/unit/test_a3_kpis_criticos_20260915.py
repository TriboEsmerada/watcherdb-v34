"""
2026-09-15 -- A3: KPI criticos ligados ao aviso e ao sino com a classificacao aprovada pelo owner.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
CHECKS = PORTAL[PORTAL.index("const TOAST_CRITICAL_CHECKS = ["):PORTAL.index("function startCriticalNotifications()")]
POLL = PORTAL[PORTAL.index("async function pollCriticalKPIs()"):PORTAL.index("function isOnDashboardKPIs()")]
HELPERS = (ROOT / "api" / "routers" / "intelligence" / "helpers.py").read_text(encoding="utf-8")


def _bloco(key):
    i = CHECKS.index(f"key: '{key}'")
    j = CHECKS.find("key: '", i + 5)
    return CHECKS[i:j if j > 0 else len(CHECKS)]


def test_classificacao_aprovada():
    ligados = re.findall(r"key: '([a-z_]+)'", CHECKS)
    assert ligados == ["instances_offline", "blocked_sessions", "db_unavailable", "alwayson_unhealthy",
                       "disk_critical", "tlog_critical", "filegroup_critical", "backup_failed",
                       "mirroring_unhealthy", "cpu_critical", "memory_critical", "disk_latency_critical",
                       "tempdb_critical", "jobs_critical_failed"]
    # nao ligar: sem baseline, contaminado por 18456, recolha parada
    for fora in ("d.deadlocks", "d.error_log", "d.service_status"):
        assert fora not in CHECKS, fora


def test_duracao_e_histerese_so_nos_quatro():
    for key, minutos in (("cpu_critical", 10), ("memory_critical", 5), ("disk_latency_critical", 10), ("tempdb_critical", 10)):
        b = _bloco(key)
        assert f"sustainMs: {minutos} * TOAST_MIN" in b, key
        assert "holdMs: 15 * TOAST_MIN" in b, key
    for key in ("backup_failed", "mirroring_unhealthy", "jobs_critical_failed", "blocked_sessions"):
        assert "sustainMs" not in _bloco(key), key
    assert "const _sustentado = _toastSustentado(check, currentValue, _agora);" in POLL
    assert "} else if (_sustentado && currentValue > (_toastLastFired[check.key] || 0)) {" in POLL


def test_relogio_persiste_e_reinicia_depois_de_buraco():
    assert "const TOAST_GAP_MS = 15 * TOAST_MIN;" in PORTAL
    assert "(agora - (e.seen || 0)) > TOAST_GAP_MS" in PORTAL
    assert "try { localStorage.setItem(TOAST_SINCE_KEY" in PORTAL
    assert "const v = JSON.parse(localStorage.getItem(TOAST_SINCE_KEY)" in PORTAL


def test_jobs_so_os_criticos():
    assert "const TOAST_JOB_TYPES_CRITICOS = ['DBCC', 'Replication', 'AlwaysOn'];" in PORTAL
    assert "TOAST_JOB_TYPES_CRITICOS.includes(i.Job_Type)" in _bloco("jobs_critical_failed")


def test_familias_agrupadas_pelo_maximo():
    b = _bloco("blocked_sessions")
    assert "Math.max(d.blocked_sessions?.count || 0, d.lock_count?.critical_count || 0, d.blocked_users?.count || 0)" in b
    assert "toast.detail_long_locks" in b and "toast.detail_blocked_users" in b
    c = _bloco("cpu_critical")
    assert "Math.max(d.cpu_critical?.count || 0, d.processes_alarm?.count || 0)" in c
    assert "toast.detail_runnable" in c


def test_detalhe_le_o_nome_com_maiuscula_e_sai_escapado():
    assert "i.instance)" not in CHECKS and "${i.instance}" not in CHECKS
    assert "i.Instance || i.instance" in PORTAL
    assert '<div class="toast-detail">${_bellEsc(detail)}</div>' in PORTAL


def test_linha_de_servicos_sem_falso_verde():
    assert "(ss.collector_stale === true" in PORTAL
    assert "function _svcSemRecolha(ss)" in PORTAL
    assert "MAX(Update_TS) AS last_update FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_SERVICE_STATUS_STG" in HELPERS
    assert "await _service_collector_freshness(results)" in HELPERS
    assert "Trusted_Connection" not in HELPERS[HELPERS.index("async def _service_collector_freshness"):]


def test_frescura_da_recolha_de_servicos_comportamento(monkeypatch):
    from api.routers.intelligence import helpers as h
    agora = datetime.now()
    casos = [
        ([{"last_update": agora - timedelta(days=125)}], True, True),
        ([{"last_update": agora - timedelta(minutes=5)}], False, True),
        ([{"last_update": None}], True, False),
        (None, None, False),
    ]
    for rows, stale, tem_data in casos:
        async def fake(query, raise_on_error=True, _rows=rows):
            assert "KPI_MSSQL_SERVICE_STATUS_STG" in query and "MAX(Update_TS)" in query
            return _rows
        monkeypatch.setattr(h, "execute_intelligence_query_async", fake)
        res = {"service_status": {"down_count": 0}}
        asyncio.run(h._service_collector_freshness(res))
        assert res["service_status"]["collector_stale"] is stale, rows
        assert (res["service_status"]["collector_last_update"] is not None) is tem_data, rows


def test_chaves_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for k in ("backup_failed", "mirroring_unhealthy", "cpu_critical", "memory_critical",
                  "disk_latency_critical", "tempdb_critical", "jobs_critical_failed"):
            assert d["toast"][k], (loc, k)
        for k in ("detail_long_locks", "detail_blocked_users", "detail_runnable"):
            assert "{n}" in d["toast"][k], (loc, k)
        assert "{d}" in d["kpi_adv"]["services_no_collection"], loc
        assert d["kpi_adv"]["services_no_collection_never"], loc
