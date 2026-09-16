"""
2026-09-16 -- as duas linhas de um erro do errorlog passam a ser uma, com base de dados e nivel certos.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.errorlog_pairs import emparelhar_errorlog  # noqa: E402

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
MAIN = (ROOT / "watcherdb_main.py").read_text(encoding="utf-8").replace("\r\n", "\n")


def _r(data, spid, texto):
    return {"LogDate": data, "ProcessInfo": spid, "Text": texto}


def test_cabecalho_e_continuacao_viram_uma_linha_informativa():
    rows = [
        _r("2026-09-16 16:30:09", "spid142s", "Error: 41145, Severity: 16, State: 1."),
        _r("2026-09-16 16:30:09", "spid142s", "Cannot join database 'INFA_EXC_02_105' to availability group 'SQLMDMPRDAG03'.  "
                                                "The database has already joined the availability group.  This is an informational message.  No user action is required."),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 1
    e = out[0]
    assert e["error_number"] == 41145 and e["error_severity"] == 16
    assert e["message"].startswith("Error: 41145, Severity: 16, State: 1. — Cannot join database")
    assert e["database_name"] == "INFA_EXC_02_105"
    assert e["severity"] == "INFO", "o proprio SQL Server diz que e' informativa"
    assert "already joined" in e["context"]


def test_cabecalho_com_continuacao_grave_fica_erro_com_base():
    rows = [
        _r("2026-09-16 10:00:00", "spid55", "Error: 823, Severity: 24, State: 2."),
        _r("2026-09-16 10:00:00", "spid55", "The operating system returned error 21 to SQL Server during a read at offset 0x0 in file 'E:\\data\\Vendas.mdf'. ... database 'Vendas'."),
    ]
    e = emparelhar_errorlog(rows)[0]
    assert e["severity"] == "ERROR" and e["database_name"] == "Vendas" and e["error_number"] == 823


def test_continuacao_de_outro_spid_nao_e_adoptada():
    rows = [
        _r("2026-09-16 10:00:00", "spid55", "Error: 18456, Severity: 14, State: 8."),
        _r("2026-09-16 10:00:00", "spid77", "Login failed for user 'x'. Reason: Password did not match. [CLIENT: 10.0.0.1]"),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 2
    cab = next(o for o in out if o["error_number"] == 18456)
    assert cab["context"] is None and cab["severity"] == "WARNING"


def test_dois_cabecalhos_seguidos_nao_se_engolem():
    rows = [
        _r("2026-09-16 10:00:00", "spid55", "Error: 41145, Severity: 16, State: 1."),
        _r("2026-09-16 10:00:00", "spid55", "Error: 41145, Severity: 16, State: 1."),
        _r("2026-09-16 10:00:00", "spid55", "Cannot join database 'cmx_ors' to availability group 'AG'. This is an informational message."),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 2
    assert sorted(o["context"] is not None for o in out) == [False, True]


def test_linha_solta_informativa_e_descartada_e_a_grave_fica():
    rows = [
        _r("2026-09-16 10:00:00", "spid9", "Recovery is writing a checkpoint in database 'x'. This is an informational message only."),
        _r("2026-09-16 10:00:01", "spid9", "SQL Server has encountered 3 occurrence(s) of I/O requests taking longer than 15 seconds to complete on file 'E:\\x.mdf' in database 'Vendas' (7)."),
    ]
    out = emparelhar_errorlog(rows)
    assert len(out) == 1 and out[0]["database_name"] == "Vendas"


def test_saida_vem_por_data_decrescente():
    rows = [_r("2026-09-16 09:00:00", "a", "Error: 1, Severity: 20, State: 1."), _r("2026-09-16 11:00:00", "b", "Error: 2, Severity: 20, State: 1.")]
    out = emparelhar_errorlog(rows)
    assert [o["error_number"] for o in out] == [2, 1]


def test_o_endpoint_usa_o_emparelhamento_e_a_sequencia():
    i = MAIN.index('@app.get("/api/monitoring/sql-errors/{server_id}")')
    bloco = MAIN[i:i + 9000]
    assert "Seq INT IDENTITY(1,1)" in bloco
    assert "LAG(Text) OVER (PARTITION BY ProcessInfo ORDER BY Seq)" in bloco
    assert "OR PrevIsHeader = 1" in bloco and "ORDER BY Seq;" in bloco
    assert "NOT LIKE '%This is an informational message%'" not in bloco, "a decisao 'informativa' e' depois de emparelhar"
    assert "errors.extend(emparelhar_errorlog(result))" in bloco


def test_a_tabela_sql_nasce_filtrada_por_erro():
    assert "window._logColFilter = window._logColFilter || { win: {}, sql: { level: 'ERRO' } };" in PORTAL


def test_o_ecra_honra_o_info_do_servidor_antes_do_numero_da_severidade():
    i = PORTAL.index("const classifySqlLevel = (err) => {")
    bloco = PORTAL[i:i + 700]
    assert "if (String(err.severity || '').toUpperCase() === 'INFO') return 'INFO';" in bloco
    assert bloco.index("=== 'INFO') return 'INFO'") < bloco.index("const sev = String(err.error_severity")
