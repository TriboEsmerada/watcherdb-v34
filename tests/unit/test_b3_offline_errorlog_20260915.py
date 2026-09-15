"""
2026-09-15 -- B3: errorlog antes da falha, no ecra de servidor offline.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
KPIS = (ROOT / "api" / "routers" / "intelligence_kpis.py").read_text(encoding="utf-8")
JS = PORTAL[PORTAL.index("// B3 2026-09-15: errorlog antes da falha, no ecra"):PORTAL.index("function extractHostname(serverIdOrName) {")]
PRECHECK = PORTAL[PORTAL.index("updateSkeletonProgress(t('overview.precheck_connectivity'));"):PORTAL.index("[PRECHECK] Erro no ping")]
AGORA = datetime(2026, 9, 15, 15, 0, 0)


def _ik():
    from api.routers import intelligence_kpis as ik
    return ik


def test_payload_listadas_seguranca_e_omitidas():
    ik = _ik()
    ancora = datetime(2026, 9, 15, 12, 53, 14)
    rows = [
        ("E", datetime(2026, 9, 15, 12, 50), "Critical", 17053, 16, "  Stack dump  ", None),
        ("C", datetime(2026, 9, 15, 12, 50), "E", None, None, None, 3),
        ("C", datetime(2026, 9, 15, 12, 51), "S", None, None, None, 40),
        ("C", datetime(2026, 9, 15, 12, 40), "O", None, None, None, 7),
        ("P", datetime(2026, 9, 15, 12, 20), "Security", None, None, None, 12),
    ]
    p = ik._errorlog_signals_payload("SQLX_I01", 2, AGORA, ancora, AGORA - timedelta(minutes=3), AGORA, rows)
    assert p["events"] == [{"log_date": "2026-09-15T12:50:00", "log_type": "Critical", "error_number": 17053,
                            "severity": 16, "text": "Stack dump"}]
    assert p["events_total"] == 3 and p["omitted_count"] == 7
    assert p["security"] == {"count": 40, "peak": {"minute": "2026-09-15T12:20:00", "count": 12}}
    assert p["anchor_source"] == "offline_event" and p["since"] == "2026-09-15T10:53:14"
    assert p["collector_cycle_minutes"] == 3 and p["collector_stale"] is False and p["empty_reason"] is None
    json.dumps(p)


def test_lista_vazia_tem_sempre_motivo():
    ik = _ik()
    fresco = AGORA - timedelta(minutes=5)
    casos = [
        (AGORA - timedelta(minutes=16), AGORA, "collector_stale"),
        (None, AGORA, "collector_stale"),
        (fresco, None, "instance_never"),
        (fresco, AGORA - timedelta(days=1), "window_quiet"),
    ]
    for ciclo, ultima, motivo in casos:
        p = ik._errorlog_signals_payload("SQLX_I01", 6, AGORA, None, ciclo, ultima, [])
        assert p["empty_reason"] == motivo, (ciclo, ultima)
        assert p["collector_stale"] is (motivo == "collector_stale")
        assert p["anchor_source"] == "now" and p["since"] == "2026-09-15T09:00:00"


def test_consultas_so_leitura_parametrizadas_e_deduplicadas():
    ik = _ik()
    for sql in (ik._ERRORLOG_SIGNALS_CONTEXT_SQL, ik._ERRORLOG_SIGNALS_ROWS_SQL):
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|CREATE|ALTER|DROP|TRUNCATE)\b", sql)
        assert "DECLARE @inst VARCHAR(128) = ?" in sql
    linhas = ik._ERRORLOG_SIGNALS_ROWS_SQL
    assert linhas.count("WITH (NOLOCK)") == 2 and "PARTITION BY Log_Date, hsh" in linhas
    assert "TOP (15)" in linhas and "Grupo = 'E'" in linhas
    assert "WHEN ISNULL(Log_Type, '') = 'Security' THEN 'S'" in linhas
    bloco = KPIS[KPIS.index("# B3 2026-09-15: errorlog antes da falha"):KPIS.index('@router.get("/server-offline/summary"')]
    assert "get_intelligence_connection()" in bloco and "pyodbc.connect" not in bloco
    assert "Trusted_Connection" not in bloco and "Integrated Security" not in bloco


def test_endpoint_exige_sessao_antes_de_validar(monkeypatch):
    ik = _ik()
    chamadas = []

    async def sem_sessao(request):
        raise HTTPException(status_code=401, detail="Token nao fornecido")

    monkeypatch.setattr(ik, "_require_auth", sem_sessao)
    with pytest.raises(HTTPException) as e:
        asyncio.run(ik.get_errorlog_recent_signals(None, instance="a;b", hours=9))
    assert e.value.status_code == 401

    async def com_sessao(request):
        return {"username": "dba"}

    monkeypatch.setattr(ik, "_require_auth", com_sessao)
    monkeypatch.setattr(ik, "_errorlog_recent_signals_sync", lambda inst, h: chamadas.append((inst, h)) or {"success": True})
    for inst, h in (("SQLX_I01; DROP", 2), ("SQLX\\I01", 2), ("SQLX_I01", 3)):
        with pytest.raises(HTTPException) as e:
            asyncio.run(ik.get_errorlog_recent_signals(None, instance=inst, hours=h))
        assert e.value.status_code == 400
    r = asyncio.run(ik.get_errorlog_recent_signals(None, instance="SQLHDSPRD214_I01", hours=6))
    assert r.status_code == 200 and chamadas == [("SQLHDSPRD214_I01", 6)]


def test_portal_bloco_no_ecra_offline():
    assert "${offlineErrorlogBlock(serverId)}" in PRECHECK
    assert "loadOfflineErrorlog(offlineErrorlogId(serverId), 2);\n                        return;" in PRECHECK.replace("\r\n", "\n")
    assert "createFetchWithAbort(" in JS and "{ timeout: 8000 }" in JS and "fetchWithTimeout(" not in JS
    assert 'role="status" aria-live="polite"' in JS and "<details>" in JS and 'type="button"' in JS
    assert "<script" not in JS and "setTabCache" not in JS
    assert "/api/intelligence-kpis/errorlog/recent-signals?instance=${encodeURIComponent(" in JS
    for motivo in ("empty_collector_stale", "empty_instance_never", "empty_window_quiet"):
        assert f"'{motivo}'" in JS


def test_chaves_nos_idiomas_sem_prometer_ausencia_de_erros():
    chaves = None
    for loc in ("pt", "en", "es"):
        ov = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["overview"]
        novas = {k: v for k, v in ov.items() if k.startswith("offline_errorlog_")}
        chaves = chaves or set(novas)
        assert set(novas) == chaves and len(chaves) == 28, loc  # B3b: +5 chaves do banner
        for k in chaves:
            assert novas[k].strip(), (loc, k)
            curta = k[len("offline_errorlog_"):]
            assert f"'{curta}'" in JS or f"'overview.{k}'" in JS, k
        for k, ph in (("window_event", ("{since}", "{h}", "{anchor}")), ("security", ("{n}", "{p}", "{time}")),
                      ("shown", ("{shown}", "{total}")), ("collector_ago", ("{n}", "{time}"))):
            assert all(x in novas["offline_errorlog_" + k] for x in ph), (loc, k)
        texto = " ".join(novas.values()).lower()
        assert "sem erros" not in texto and "no errors" not in texto and "sin errores" not in texto
    ptbr = json.loads((ROOT / "static" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))["overview"]
    assert {k for k in ptbr if k.startswith("offline_errorlog_")} <= chaves
