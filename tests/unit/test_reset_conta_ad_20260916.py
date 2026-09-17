"""
2026-09-16 -- trocar/repor a password de uma conta de dominio mexe na senha local de recurso, nunca no marcador ad_auth:.
Corre o metodo real do servico com a base falsa; captura o SQL executado.
"""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services import auth_service as svc  # noqa: E402

AD = {"username": "ue_e-maria", "password_hash": "ad_auth:abc123", "local_password_hash": None, "role": "viewer"}
AD_COM_LOCAL = {"username": "ue_e-maria", "password_hash": "ad_auth:abc123", "local_password_hash": "$2b$12$xyz", "role": "viewer"}
LOCAL = {"username": "dba.maria", "password_hash": "$2b$12$local", "local_password_hash": None, "role": "admin"}


class Captura:
    def __init__(self):
        self.updates = []

    def update(self, sql, params=None):
        self.updates.append((sql, tuple(params or ())))
        return 1


@pytest.fixture
def servico(monkeypatch):
    cap = Captura()
    monkeypatch.setattr(svc, "_execute_update", cap.update)
    s = svc.AuthService.__new__(svc.AuthService)   # sem __init__: nao toca em BD nem em AD
    return s, cap


def _troca(s, user, nova="Fogueira!2026"):
    s._get_user_from_db = lambda u: dict(user)
    return asyncio.run(s.change_password(user["username"], nova))


def test_e_conta_de_dominio_le_o_marcador():
    assert svc.e_conta_de_dominio(AD) and svc.e_conta_de_dominio(AD_COM_LOCAL)
    assert not svc.e_conta_de_dominio(LOCAL) and not svc.e_conta_de_dominio(None) and not svc.e_conta_de_dominio({})


def test_conta_de_dominio_nao_perde_o_marcador(servico):
    s, cap = servico
    r = _troca(s, AD)
    assert r["success"] and r.get("conta_de_dominio") is True
    assert len(cap.updates) == 1
    sql, params = cap.updates[0]
    assert "SET local_password_hash = ?" in sql and "local_password_set_at = SYSUTCDATETIME()" in sql
    assert "SET password_hash" not in sql, "o marcador ad_auth: nunca pode ser reescrito"
    assert params[0].startswith("$2b$") and params[-1] == "ue_e-maria"


def test_conta_local_continua_a_mudar_o_password_hash(servico):
    s, cap = servico
    r = _troca(s, LOCAL)
    assert r["success"] and not r.get("conta_de_dominio")
    sql, _ = cap.updates[0]
    assert "SET password_hash = ?" in sql and "password_changed_at = SYSUTCDATETIME()" in sql
    assert "local_password_hash" not in sql


def test_a_troca_numa_conta_de_dominio_tambem_revoga_sessoes_antigas(servico):
    """password_changed_at e' o que invalida os tokens anteriores (A-4.7); tem de avancar nos dois caminhos."""
    s, cap = servico
    _troca(s, AD_COM_LOCAL)
    assert "password_changed_at = SYSUTCDATETIME()" in cap.updates[0][0]


def test_o_router_verifica_a_actual_contra_a_senha_local_e_explica_quando_nao_ha():
    src = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    i = src.index("db_user = service._get_user_from_db(user[\"username\"])")
    bloco = src[i:i + 1400]
    assert "if e_conta_de_dominio(db_user):" in bloco
    assert 'local_hash = db_user.get("local_password_hash") or ""' in bloco
    assert "status_code=400" in bloco and "a password muda-se no AD" in bloco
    assert "verify_password(body.current_password, local_hash)" in bloco


def test_o_reset_por_administrador_diz_que_definiu_a_senha_local():
    src = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    i = src.index('async def reset_password(')
    bloco = src[i:i + 2200]
    assert 'if result.get("conta_de_dominio"):' in bloco
    assert "senha local de recurso" in bloco
    # a obrigacao de trocar nao se marca numa conta de dominio: o return vem ANTES do UPDATE must_change_password
    assert bloco.index('if result.get("conta_de_dominio"):') < bloco.index("SET must_change_password = 1")
