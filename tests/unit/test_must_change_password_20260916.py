"""
2026-09-16 -- must_change_password: o script que cria a coluna tem de poder correr, e a falha tem de ver-se.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL14 = (ROOT / "database" / "14_ADD_MUST_CHANGE_PASSWORD.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
SQL07 = (ROOT / "database" / "07_ADD_MUST_CHANGE_PASSWORD.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
CANON = (ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
AUTH = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\r\n", "\n")

ALTER = "ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;"
BACKFILL = "EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');"


def _batch_do_alter(texto):
    """Devolve o batch (delimitado por GO) que contem o ALTER."""
    batches = re.split(r"(?mi)^GO\s*$", texto)
    alvo = [b for b in batches if ALTER in b]
    assert len(alvo) == 1, "o ALTER tem de estar exactamente num batch"
    return alvo[0]


def test_o_script_14_cria_a_coluna_com_a_forma_do_canonico():
    assert ALTER in SQL14
    assert BACKFILL in SQL14
    assert "IF NOT EXISTS (SELECT 1 FROM sys.columns" in SQL14, "tem de ser idempotente"
    assert "USE [WatcherDB_Intelligence];" in SQL14


def test_o_update_nao_fica_no_mesmo_batch_do_alter_sem_exec():
    """O defeito de origem (erro 207): o UPDATE a' coluna nova compilado no batch que a cria."""
    batch = _batch_do_alter(SQL14)
    sem_exec = [ln for ln in batch.split("\n")
                if "must_change_password" in ln
                and re.search(r"(?i)^\s*UPDATE\b", ln)]
    assert sem_exec == [], f"UPDATE directo no batch do ALTER (erro 207): {sem_exec}"


def test_o_script_14_nao_traz_o_hash_semente():
    assert "$2b$12$" not in SQL14, "o hash-semente admin123 foi tirado do canonico em 5ed4f68"


def test_o_script_14_nao_diverge_do_canonico():
    """O 07 divergiu do canonico e ninguem deu por isso. Este teste tranca os dois comandos."""
    assert ALTER in CANON and BACKFILL in CANON


def test_o_script_07_esta_marcado_como_historico():
    cabecalho = SQL07[:1200]
    assert "HISTORICO" in cabecalho and "NAO CORRER" in cabecalho
    assert "14_ADD_MUST_CHANGE_PASSWORD.sql" in cabecalho
    assert "207" in cabecalho, "o cabecalho tem de dizer porque e' que o ficheiro nunca funcionou"


def test_o_portal_deixa_de_calar_a_falha():
    assert "pass  # Column may not exist yet" not in AUTH
    assert AUTH.count("_avisar_coluna_em_falta(") == 4, "a definicao mais tres chamadas"
    for sitio in ('"login"', '"mudanca de password"', '"reset por administrador"'):
        assert f"_avisar_coluna_em_falta({sitio}, exc)" in AUTH


def test_o_aviso_nomeia_a_coluna_e_o_script():
    i = AUTH.index("def _avisar_coluna_em_falta")
    corpo = AUTH[i:i + 1400]
    assert "14_ADD_MUST_CHANGE_PASSWORD.sql" in corpo
    assert "logger.warning" in corpo
    assert "_AVISOS_MUST_CHANGE.add(onde)" in corpo, "uma vez por sitio, para nao inundar o log"


def test_a_degradacao_continua_a_nao_rebentar_o_login():
    """O aviso substitui o `pass`, mas a excepcao continua apanhada: o login tem de responder."""
    i = AUTH.index("# Check must_change_password flag")
    # 2026-09-16: era AUTH[i:i+700]. O lote da tarde acrescentou comentarios ao bloco e o `except` saiu
    # da janela -- teste vermelho sem defeito nenhum. Delimitar pelo fim real do bloco, nao por contagem.
    bloco = AUTH[i:AUTH.index("response = JSONResponse(content=result)", i)]
    assert "except Exception as exc:" in bloco
    assert "raise" not in bloco
