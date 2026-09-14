"""
2026-09-14 -- C0: as classes de defeito do LIVE, fora do LIVE.
"""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ler(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_percentagem_de_modificacoes_nao_cabe_em_decimal_5_2():
    # sp.modification_counter NAO e' limitado por sp.rows: 100 linhas com 1M de modificacoes = 1.000.000,00
    for rel in ("services/sqlserver_kpi_service.py",
                "api/routers/queries/_diagnostics_legacy.py",
                "modules/monitoring/queries.py"):
        s = _ler(rel)
        assert "(sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2)" not in s, rel
        assert "(sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(18,2)" in s, rel


def test_percentagens_limitadas_ficam_em_decimal_5_2():
    # o lote alarga so' a expressao que pode passar de 100; nao e' uma varredura cega
    s = _ler("modules/monitoring/queries.py")
    assert "CAST(avg_fragmentation_in_percent AS DECIMAL(5,2))" in s


def test_union_all_de_filegroups_com_collation_explicita():
    s = _ler("api/routers/queries/space.py")
    assert "name COLLATE DATABASE_DEFAULT as fg_name" in s


def test_serverproperty_convertido_e_coluna_inexistente_removida():
    s = _ler("modules/monitoring/security_analysis.py")
    assert "encryption_state_desc" not in s
    assert "CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128))" in s
    assert "CAST(SERVERPROPERTY('IsIntegratedSecurityOnly') AS INT)" in s
    # a comparacao dentro do CASE nao precisa de conversao e fica intacta
    assert "WHEN SERVERPROPERTY('IsIntegratedSecurityOnly') = 1" in s


def test_is_encrypted_continua_a_ser_lido():
    # a coluna removida nunca era usada; a que o codigo le' tem de continuar la'
    s = _ler("modules/monitoring/security_analysis.py")
    assert "d.is_encrypted" in s and "d.get('is_encrypted', 0)" in s


def test_resumo_de_servicos_serializa_decimal():
    from api.routers import service_status as svc
    assert "JSONResponse(content=" not in _ler("api/routers/service_status.py")
    resp = svc._svc_json({"mb": Decimal("1.5"), "b": b"\x0a\xff"})
    corpo = json.loads(resp.body)
    assert corpo["mb"] == 1.5 and corpo["b"] == "0aff" and resp.status_code == 200
