# -*- coding: utf-8 -*-
"""Contrato 2026-09-02 — drill-down "Diagnostico de Transaction Log" por base.

Endpoint api/routers/queries/tlog_diagnosis.py com async_execute_on_server
mockado (molde: test_diagnosis_layout_wave_20260817.py::test_mirroring_...).
Cenarios: cadeia parada (FULL sem log backup) / transacao aberta / replica AG /
shrink candidato / saudavel / 2012 sem dm_db_log_stats / degradacao sem 500 /
nome com apostrofe escapado / DDL so' comentado.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from api.routers.queries import tlog_diagnosis as td

NOW = datetime(2026, 9, 2, 15, 0, 0)
SERVER = "SRV_I01"
DB = "DbX"


def _caps(**kw):
    base = {"product_version": "15.0.4382.1", "major_version": 15, "edition": "Enterprise", "uptime_hours": 240, "server_name": "SRV\I01",
            "server_now": NOW, "has_log_stats": 1, "has_log_info": 1, "has_input_buffer": 1}
    base.update(kw)
    return [base]


def _state(lrw="LOG_BACKUP", recovery="FULL", pct_growth=0, growth_mb=512, size_mb=20480, data_mb=6800, max_size=None):
    return [{"database_id": 7, "database_name": DB, "state_desc": "ONLINE", "recovery_model_desc": recovery,
             "log_reuse_wait_desc": lrw, "is_read_only": 0, "has_db_access": 1, "log_file_count": 1,
             "file_id": 2, "log_logical_name": f"{DB}_log", "log_physical_name": f"L:\\Logs\\{DB}_log.ldf",
             "log_size_mb": size_mb, "log_unlimited": 1 if max_size is None else 0, "log_max_size_mb": max_size,
             "log_growth_disabled": 0, "is_percent_growth": pct_growth, "log_growth_value": (10 if pct_growth else growth_mb),
             "data_size_mb": data_mb}]


def _counters(size_mb=20480, used_mb=19900, growths=3):
    return [{"counter_name": "Log File(s) Size (KB)", "cntr_value": size_mb * 1024},
            {"counter_name": "Log File(s) Used Size (KB)", "cntr_value": used_mb * 1024},
            {"counter_name": "Log Growths", "cntr_value": growths}]


def _vols(free_gb=2.0, headroom_mb=2048):
    return [{"file_id": 2, "logical_name": f"{DB}_log", "physical_name": "L:\\x.ldf", "volume_mount_point": "L:\\",
             "volume_total_gb": 100.0, "volume_free_gb": free_gb, "volume_free_pct": free_gb, "log_size_mb": 20480,
             "log_headroom_mb": headroom_mb, "log_mb_written_since_start": 24000, "avg_write_latency_ms": 2.1}]


def _bk30(log_days=7, log_mb_per_day=500.0, with_full=True):
    rows = []
    for i in range(log_days):
        d = (NOW - timedelta(days=i)).date()
        rows.append({"backup_type": "L", "backup_day": d.isoformat(), "backups": 12, "total_mb": log_mb_per_day,
                     "max_size_mb": 120.0, "last_finish": datetime.combine(d, datetime.min.time()) + timedelta(hours=14 if i else 14), "copy_only_count": 0})
    if with_full:
        rows.append({"backup_type": "D", "backup_day": (NOW - timedelta(days=1)).date().isoformat(), "backups": 1, "total_mb": 5000.0,
                     "max_size_mb": 5000.0, "last_finish": NOW - timedelta(days=1), "copy_only_count": 0})
    return rows


def _make_exec(scenario):
    async def fake_exec(server_id, query, database="master", timeout_s=0):
        q = query.upper()
        assert server_id == SERVER
        if "SERVERPROPERTY" in q:
            return scenario.get("caps", _caps())
        if "SYS.DATABASES D" in q and "LOG_LOGICAL_NAME" in q:
            return scenario.get("state", _state())
        if "DM_OS_PERFORMANCE_COUNTERS" in q:
            return scenario.get("counters", _counters())
        if "DBCC SQLPERF" in q:
            return scenario.get("sqlperf", [])
        if "DM_DB_LOG_STATS" in q and "SYS.DM_DB_LOG_STATS(" in q:
            return scenario.get("log_stats", [{"status": "ok", "total_vlf_count": 120, "active_vlf_count": 4,
                                               "log_backup_time": NOW - timedelta(hours=1), "log_since_last_log_backup_mb": 50}])
        if "DM_DB_LOG_INFO" in q:
            return scenario.get("log_info", [{"status": "ok", "vlf_count": 120, "active_vlf_count": 4, "vlfs_under_1mb": 0}])
        if "DM_TRAN_DATABASE_TRANSACTIONS" in q:
            return scenario.get("open_tran", [])
        if "BACKUP_FINISH_DATE >= DATEADD(DAY, -30," in q:
            return scenario.get("bk30", _bk30())
        if "BACKUP_FINISH_DATE >= DATEADD(DAY, -3," in q:
            return scenario.get("bk3", [])
        if "DM_OS_VOLUME_STATS" in q:
            return scenario.get("vols", _vols(free_gb=40.0, headroom_mb=40000))
        if "DM_HADR_DATABASE_REPLICA_STATES DRS" in q:
            return scenario.get("ha", [{"database_name": DB}])
        if "DM_EXEC_REQUESTS R" in q:
            return scenario.get("reqs", [])
        if "XP_READERRORLOG" in q:
            if "errorlog" in scenario:
                return scenario["errorlog"]
            raise RuntimeError("The EXECUTE permission was denied on the object 'xp_readerrorlog' (229)")
        return []
    return fake_exec


def _run(monkeypatch, scenario, **kw):
    monkeypatch.setattr(td, "async_execute_on_server", _make_exec(scenario))
    monkeypatch.setattr(td, "_th", lambda k, lvl: {("tlog_usage", "warning"): 85, ("tlog_usage", "critical"): 95,
                                                    ("backup_delay_log", "warning"): 1, ("backup_delay_log", "critical"): 2}[(k, lvl)])
    return asyncio.run(td.tlog_diagnosis(SERVER, database=DB, **kw))


def test_cadeia_parada_full_sem_log_backup(monkeypatch):
    out = _run(monkeypatch, {"bk30": [], "log_stats": [{"status": "ok", "total_vlf_count": 900, "active_vlf_count": 700, "log_backup_time": None}],
                             "state": _state(lrw="LOG_BACKUP", size_mb=114049, data_mb=6800, pct_growth=1)})
    d = out["diagnosis"]
    ids = {p["id"] for p in d["problems"]}
    assert {"chain_stopped", "log_usage", "vlf_high", "growth_bad"} <= ids
    assert d["header"]["verdict"] == "critical"
    assert out["raw"]["derived"]["triage"] == "CADEIA PARADA" and d["principal"]["headline"] == "CADEIA DE BACKUP DE LOG INTERROMPIDA"
    recs = {r["id"]: r for r in d["recommendations"]}
    assert "rec_log_backup" in recs and recs["rec_log_backup"]["impact"] == "very_high"
    # comando de mudanca so' comentado
    assert "-- BACKUP LOG [DbX]" in recs["rec_log_backup"]["sqlCheck"]
    assert all(not ln.strip().upper().startswith(("BACKUP ", "ALTER ", "DBCC SHRINKFILE", "KILL ")) for r in d["recommendations"] for ln in (r.get("sqlCheck") or "").splitlines() if ln.strip())
    # sem log backup registado -> tile "NUNCA"
    assert d["summary"][2]["value"] == "NUNCA"
    # errorlog sem permissao degrada com nota, nunca 500
    assert any("errorlog" in n for n in out["notes"])
    assert out["success"] is True


def test_transacao_aberta_orfa(monkeypatch):
    otr = [{"session_id": 87, "login_name": "app_user", "host_name": "APP01", "program_name": ".Net SqlClient", "session_status": "sleeping",
            "request_command": None, "open_minutes": 180, "log_reserved_mb": 3500.0, "last_batch": "UPDATE dbo.Orders SET ..."}]
    out = _run(monkeypatch, {"state": _state(lrw="ACTIVE_TRANSACTION"), "open_tran": otr})
    d = out["diagnosis"]
    ids = {p["id"] for p in d["problems"]}
    assert {"log_not_truncating", "open_tran"} <= ids
    lnt = [p for p in d["problems"] if p["id"] == "log_not_truncating"][0]
    assert "ACTIVE_TRANSACTION" in lnt["evidence"] and "87" in lnt["evidence"] and lnt["recIds"] == ["rec_open_tran"]
    ot = [p for p in d["problems"] if p["id"] == "open_tran"][0]
    assert ot["severity"] == "critical" and "órfã" in ot["title"]
    rec = [r for r in d["recommendations"] if r["id"] == "rec_open_tran"][0]
    assert "-- KILL 87" in rec["sqlCheck"]
    assert out["raw"]["derived"]["triage"] == "TRANSACAO ABERTA"
    # mapeamento explicito: NAO recomenda log backup nem shrink como accao da causa
    assert "rec_shrink" not in {r["id"] for r in d["recommendations"]}


def test_replica_ag_retendo(monkeypatch):
    ha = [{"database_name": DB, "ag_name": "AG1", "ag_role": "PRIMARY", "synchronization_state_desc": "SYNCHRONIZED",
           "log_send_queue_kb": 0, "max_remote_send_queue_kb": 5242880, "unhealthy_remote_replicas": 1}]
    out = _run(monkeypatch, {"state": _state(lrw="AVAILABILITY_REPLICA"), "ha": ha})
    d = out["diagnosis"]
    lnt = [p for p in d["problems"] if p["id"] == "log_not_truncating"][0]
    assert lnt["recIds"] == ["rec_replica"] and "5,00 GB" in lnt["evidence"]
    assert out["raw"]["derived"]["triage"] == "REPLICA"
    assert "AG AG1" in [r for r in d["side"]["rows"] if r["k"] == "HA / AG"][0]["v"]


def test_shrink_candidato_quando_nada_retem(monkeypatch):
    # log 20 GB com maior log backup 120 MB -> alvo 512 MB -> 40x -> warning + rec_shrink comentado
    out = _run(monkeypatch, {"state": _state(lrw="NOTHING", size_mb=20480), "counters": _counters(size_mb=20480, used_mb=800)})
    d = out["diagnosis"]
    ids = {p["id"] for p in d["problems"]}
    assert "log_vs_target" in ids and "log_usage" not in ids
    rec = [r for r in d["recommendations"] if r["id"] == "rec_shrink"][0]
    assert "-- USE [DbX]; DBCC SHRINKFILE (N'DbX_log', 512)" in rec["sqlCheck"]
    assert out["raw"]["derived"]["triage"] == "SHRINK"
    assert out["raw"]["derived"]["alvo_mb"] == 512 and out["raw"]["derived"]["potencial_mb"] == 20480 - 512


def test_saudavel(monkeypatch):
    out = _run(monkeypatch, {"state": _state(lrw="NOTHING", size_mb=1024), "counters": _counters(size_mb=1024, used_mb=200)})
    d = out["diagnosis"]
    assert d["problems"] == [] or all(p["severity"] == "info" for p in d["problems"])
    assert d["header"]["verdict"] == "ok"
    assert out["raw"]["derived"]["triage"] == "SAUDAVEL"


def test_runway_e_disco(monkeypatch):
    # margem 2048 MB, 5 dias x 500 MB em 7 (media 357 MB/dia) -> 5.7 d -> warning;
    # 5/7 dias com backup de log -> nota de gap (estimativa subavaliada)
    out = _run(monkeypatch, {"vols": _vols(free_gb=2.0, headroom_mb=2048), "bk30": _bk30(log_days=5)})
    d = out["diagnosis"]
    rw = [p for p in d["problems"] if p["id"] == "runway"][0]
    assert rw["severity"] == "warning" and "subavaliada" in rw["evidence"] and rw["confidence"] == "heuristic"
    assert out["raw"]["derived"]["runway_days"] == 5.7
    assert "rec_disk" in {r["id"] for r in d["recommendations"]}


def test_sql2012_sem_log_stats_degrada_com_nota(monkeypatch):
    out = _run(monkeypatch, {"caps": _caps(product_version="11.0.7001.0", major_version=11, has_log_stats=0, has_log_info=0, has_input_buffer=0)})
    assert any("VLFs: requer SQL 2016 SP2+" in n for n in out["notes"])
    vl = [r for r in out["diagnosis"]["side"]["rows"] if r["k"] == "VLFs"][0]
    assert vl["v"].startswith("n/d")
    assert out["success"] is True


def test_simple_recovery_nunca_vermelho_por_log_backup(monkeypatch):
    out = _run(monkeypatch, {"state": _state(lrw="NOTHING", recovery="SIMPLE"), "bk30": [], "log_stats": [{"status": "ok", "total_vlf_count": 10, "active_vlf_count": 1, "log_backup_time": None}]})
    d = out["diagnosis"]
    assert "chain_stopped" not in {p["id"] for p in d["problems"]}
    assert d["summary"][2]["value"] == "n/a" and d["summary"][2]["severity"] == "info"


def test_snapshot_intelligence_no_painel(monkeypatch):
    out = _run(monkeypatch, {}, snapshot_pct=96.2, snapshot_ts="2026-09-02T14:32:00", snapshot_age="LATE")
    row = [r for r in out["diagnosis"]["side"]["rows"] if r["k"].startswith("Intelligence")][0]
    assert "96,2%" in row["v"] and "LATE" in row["v"] and "live" in row["v"]


def test_nome_com_apostrofe_escapado_e_sem_500(monkeypatch):
    seen = []

    async def fake_exec(server_id, query, database="master", timeout_s=0):
        seen.append(query)
        return []
    monkeypatch.setattr(td, "async_execute_on_server", fake_exec)
    monkeypatch.setattr(td, "_th", lambda k, lvl: 1)
    out = asyncio.run(td.tlog_diagnosis(SERVER, database="O'Brien"))
    assert out["success"] is True
    assert all("N'O''Brien'" in q or "O'Brien" not in q for q in seen)
    with pytest.raises(Exception):
        asyncio.run(td.tlog_diagnosis(SERVER, database="x\x00y"))


def test_timeout_passado_ao_executor(monkeypatch):
    tos = []

    async def fake_exec(server_id, query, database="master", timeout_s=0):
        tos.append(timeout_s)
        return []
    monkeypatch.setattr(td, "async_execute_on_server", fake_exec)
    monkeypatch.setattr(td, "_th", lambda k, lvl: 1)
    asyncio.run(td.tlog_diagnosis(SERVER, database=DB))
    assert tos and all(t > 0 for t in tos) and max(tos) == td._TO["errorlog"]


# ---- 2026-09-02 (owner): capacidade EFECTIVA gradua a urgencia do "log usado"
def test_ficheiro_cheio_com_disco_folgado_e_aviso(monkeypatch):
    # ficheiro a 99% (27,457/27,729) mas ilimitado com 46,738 MB de margem -> efectivo 37% -> aviso
    out = _run(monkeypatch, {"state": _state(lrw="LOG_BACKUP", size_mb=27729, growth_mb=1024),
                             "counters": _counters(size_mb=27729, used_mb=27457),
                             "vols": _vols(free_gb=45.6, headroom_mb=46738)})
    d = out["diagnosis"]
    lu = [p for p in d["problems"] if p["id"] == "log_usage"][0]
    assert lu["severity"] == "warning" and "limite efetivo a 37%" in lu["evidence"] and "autogrow (+1.024 MB)" in lu["impact"]
    assert d["summary"][0]["severity"] == "warning" and "37% do limite efetivo" in d["summary"][0]["sub"]
    assert round(out["raw"]["derived"]["effective_pct"]) == 37
    assert [r for r in d["side"]["rows"] if r["k"] == "Limite efetivo"][0]["v"].startswith("72,72 GB")


def test_ficheiro_cheio_sem_margem_ou_growth_desligado_e_critico(monkeypatch):
    out = _run(monkeypatch, {"state": _state(lrw="LOG_BACKUP", size_mb=27729), "counters": _counters(size_mb=27729, used_mb=27457),
                             "vols": _vols(free_gb=0.5, headroom_mb=512)})
    lu = [p for p in out["diagnosis"]["problems"] if p["id"] == "log_usage"][0]
    assert lu["severity"] == "critical" and "rec_disk" in lu["recIds"]
    st = _state(lrw="LOG_BACKUP", size_mb=27729); st[0]["log_growth_disabled"] = 1
    out2 = _run(monkeypatch, {"state": st, "counters": _counters(size_mb=27729, used_mb=27457), "vols": _vols(free_gb=45.6, headroom_mb=46738)})
    lu2 = [p for p in out2["diagnosis"]["problems"] if p["id"] == "log_usage"][0]
    assert lu2["severity"] == "critical" and "DESLIGADO" in lu2["evidence"] and "rec_growth" in lu2["recIds"]


# ---- 2026-09-02 (mockup owner): banner "diagnostico principal" + "desde"
def test_principal_e_since_cadeia_parada(monkeypatch):
    out = _run(monkeypatch, {"bk30": _bk30(log_days=7), "log_stats": [{"status": "ok", "total_vlf_count": 10, "active_vlf_count": 2, "log_backup_time": NOW - timedelta(hours=7.2)}],
                             "errorlog": [{"LogDate": "2026-09-01 16:53:01", "Text": "The transaction log for database 'DbX' is full due to 'AVAILABILITY_REPLICA'"}] * 3})
    d = out["diagnosis"]
    p = d["principal"]
    assert p["headline"] == "CADEIA DE BACKUP DE LOG INTERROMPIDA" and p["severity"] == "critical"
    labels = [c["label"] for c in p["chain"]]
    assert labels[0] == "FULL" and "Log não trunca" in labels and labels[-1].startswith("Risco de erro 9002") and "Backup de log atrasado" in labels
    assert "3 eventos de Erro 9002" in p["risk"]["text"] and p["risk"]["cta"]["section"] == "errorlog"
    # desde = o proprio ultimo backup de log (modelo do owner): 15:00 - 7.2h = 07:48
    assert d["since"]["ts"].startswith("2026-09-02T07:48")


def test_principal_saudavel_sem_since(monkeypatch):
    out = _run(monkeypatch, {"state": _state(lrw="NOTHING", size_mb=1024), "counters": _counters(size_mb=1024, used_mb=200)})
    d = out["diagnosis"]
    assert d["principal"]["headline"] == "TRANSACTION LOG SAUDÁVEL" and d["principal"]["severity"] == "ok"
    assert d["since"] is None


def test_formatos_pt_e_int_sem_ponto_zero(monkeypatch):
    # SPID chega como float do executor -> tem de sair inteiro; numeros em formato pt (virgula decimal, GB)
    otr = [{"session_id": 110.0, "login_name": "app", "host_name": "H", "program_name": "P", "session_status": "sleeping",
            "request_command": None, "open_minutes": 200.0, "log_reserved_mb": 1536.0, "last_batch": "EXEC x" + chr(0)}]
    out = _run(monkeypatch, {"state": _state(lrw="ACTIVE_TRANSACTION", size_mb=27729), "counters": _counters(size_mb=27729, used_mb=27457), "open_tran": otr})
    d = out["diagnosis"]
    assert d["summary"][3]["sub"].startswith("sessão 110 ·") and "110.0" not in d["summary"][3]["sub"]
    assert "-- KILL 110;" in [r for r in d["recommendations"] if r["id"] == "rec_open_tran"][0]["sqlCheck"]
    assert d["summary"][0]["value"] == "99,0%" and d["summary"][0]["sub"].startswith("26,81 GB / 27,08 GB")
    assert out["raw"]["open_transactions"][0]["last_batch"] == "EXEC x"
    assert len(d["summary"]) == 5 and d["summary"][1]["label"] == "Causa atual (log_reuse_wait)"
    assert d["header"]["subtitle"].startswith("SRV\I01 ·") or d["header"]["subtitle"].startswith("SRV_I01 ·")
