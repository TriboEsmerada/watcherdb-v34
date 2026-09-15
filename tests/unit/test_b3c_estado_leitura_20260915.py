"""
2026-09-15 -- B3c: o bloco do errorlog le o estado de leitura por instancia (B2a-2a).
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
RENDER = PORTAL[PORTAL.index("function _oelRender(elId, d) {"):PORTAL.index("function extractHostname(serverIdOrName) {")]
AGORA = datetime(2026, 9, 15, 18, 30)


def _ik():
    from api.routers import intelligence_kpis as ik
    return ik


def _p(estado, rows=(), ciclo_min=3):
    ik = _ik()
    return ik._errorlog_signals_payload("SQLX_I01", 2, AGORA, None, AGORA - timedelta(minutes=ciclo_min), AGORA,
                                        list(rows), estado)


def test_falhas_seguidas_tem_prioridade_e_nunca_trazem_o_texto():
    p = _p((AGORA - timedelta(hours=1), 7, AGORA - timedelta(minutes=35), "connect"), ciclo_min=40)
    assert p["empty_reason"] == "instance_unreadable" and p["collector_stale"] is True
    assert p["read_state"] == {"last_success": "2026-09-15T17:30:00", "consecutive_failures": 7,
                               "failing_since": "2026-09-15T17:55:00", "failure_class": "connect"}
    assert "text" not in json.dumps(p["read_state"])


def test_com_linhas_o_estado_vem_na_mesma_e_classe_desconhecida_passa_a_other():
    linha = ("E", AGORA - timedelta(minutes=50), "Critical", 17053, 16, "x", None)
    p = _p((None, 2, AGORA, "inventada"), rows=[linha])
    assert p["empty_reason"] is None and p["read_state"]["failure_class"] == "other"
    assert p["read_state"]["last_success"] is None


def test_leitura_boa_e_sem_estado_ficam_como_no_b3():
    p = _p((AGORA - timedelta(minutes=4), 0, None, "connect"))
    assert p["read_state"] == {"last_success": "2026-09-15T18:26:00", "consecutive_failures": 0,
                               "failing_since": None, "failure_class": None}
    assert p["empty_reason"] == "window_quiet"
    assert _p(None)["read_state"] is None and _p(None)["empty_reason"] == "window_quiet"


def test_consulta_do_estado_so_leitura_e_fail_open(monkeypatch):
    ik = _ik()
    sql = ik._ERRORLOG_SIGNALS_STATE_SQL
    assert "IF OBJECT_ID('dbo.WDB_ERRORLOG_READ_STATE', 'U') IS NOT NULL" in sql and "WITH (NOLOCK)" in sql
    assert "Last_Failure_Text" not in sql and not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC)\b", sql)

    class Cur:
        description = None

        def __init__(self):
            self.n = 0

        def execute(self, sql, *params):
            self.n += 1
            self.description = [("x",)]
            if self.n == 3:
                raise RuntimeError("The SELECT permission was denied on the object 'WDB_ERRORLOG_READ_STATE'")

        def fetchone(self):
            return (AGORA, None, AGORA - timedelta(minutes=2), None)

        def fetchall(self):
            return []

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

    monkeypatch.setattr(ik, "get_intelligence_connection", lambda: Conn())
    monkeypatch.setattr(ik, "get_intelligence_pool", lambda: type("Pool", (), {"return_connection": lambda self, c: None})())
    p = ik._errorlog_recent_signals_sync("SQLX_I01", 2)
    assert p["success"] is True and p["read_state"] is None


def test_ecra_mostra_leitura_e_aviso_sem_texto_do_driver():
    assert "const falhaLeitura = !!(rs && +rs.consecutive_failures > 0);" in RENDER
    assert "_oelT('last_read'," in RENDER and "_oelT('unreadable'," in RENDER
    assert "d.empty_reason === 'instance_unreadable'" in RENDER
    assert RENDER.index("if (falhaLeitura) {") < RENDER.index("const sec = d.security || {};")
    assert "failure_text" not in RENDER and "Last_Failure_Text" not in RENDER
    for c in ("connect", "login_failed", "permission", "query_timeout", "other"):
        assert f"'overview.offline_errorlog_failure_{c}'" in RENDER
