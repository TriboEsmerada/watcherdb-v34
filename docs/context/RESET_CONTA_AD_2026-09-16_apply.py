# -*- coding: utf-8 -*-
"""Trocar ou repor a password de uma conta de dominio deixa de a converter em conta local (2026-09-16).

DEFEITO (encontrado no lote da troca obrigatoria, a19585b):
 - AuthService.change_password reescreve SEMPRE dbo.WatcherDB_Users.password_hash. Numa conta de dominio esse campo
   guarda o marcador `ad_auth:<sha256>` que o authenticate() usa para decidir "esta conta entra pelo AD". Reescreve-lo
   com um hash bcrypt converte a conta em conta local: a password do dominio deixa de servir e ninguem e' avisado.
 - Quem la' chega: o RESET POR ADMINISTRADOR (/users/{u}/reset-password chama change_password sem olhar ao marcador).
   O self-service (/change-password) ja nao converte -- mas por acidente: verifica a password actual contra
   password_hash, que numa conta de dominio e' o marcador, e por isso responde 401 "Password actual incorrecta" a
   qualquer utilizador de dominio, mesmo com recurso local definido. Ou seja: um utilizador de dominio com senha local
   de recurso (tools/set_local_password.py) nao consegue troca-la pelo portal.

O QUE PASSA A SER (mesmo modelo do tools/set_local_password.py, que e' o desenho de 12_ADD_LOCAL_PASSWORD_HASH.sql):
 - Numa conta de dominio, "trocar" ou "repor" a password significa mexer na SENHA LOCAL DE RECURSO
   (local_password_hash + local_password_set_at). O marcador ad_auth: nunca e' tocado; a conta continua a entrar pelo
   dominio, e a senha local e' o recurso quando o controlador esta inalcancavel -- tal como esta desenhado.
 - Self-service numa conta de dominio: a password actual verifica-se contra a senha local de recurso; se nao houver
   senha local, a resposta e' clara: "conta de dominio -- a password muda-se no AD; para definir uma senha local de
   recurso, peca ao administrador" (400, nao 401).
 - Reset por administrador numa conta de dominio: define a senha local de recurso e diz isso na resposta, em vez de
   dizer "senha alterada" e converter a conta em silencio.
 - Contas locais: nada muda.
 - must_change_password: fica como esta'; a obrigacao so' se impoe a auth_method == local (a19585b), portanto marcar
   uma conta de dominio nao a prende.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/RESET_CONTA_AD_2026-09-16_apply.py --check
  py docs/context/RESET_CONTA_AD_2026-09-16_apply.py
  py -m pytest tests/unit/test_reset_conta_ad_20260916.py tests/unit/test_troca_obrigatoria_20260916.py tests/unit/test_login_sets_cookie.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "svc": Path("services/auth_service.py"),
    "auth": Path("api/routers/auth_compat.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_reset_conta_ad_20260916.py"),
}
MARK = "def e_conta_de_dominio("

SVC_EDITS = [
    # helper de modulo, junto do verify_password
    ("""def validate_strong_password(password: str) -> Optional[str]:
""",
     """def e_conta_de_dominio(user_row) -> bool:
    \"\"\"True quando password_hash guarda o marcador ad_auth: -- a conta entra pelo dominio.

    2026-09-16: reescrever esse campo (change_password fazia-o sempre) convertia a conta em local sem aviso.
    \"\"\"
    return str((user_row or {}).get("password_hash") or "").startswith("ad_auth:")


def validate_strong_password(password: str) -> Optional[str]:
""", 1),
    ("""        hashed = hash_password(new_password)
        try:
            try:
                # Lote P4 A-4.7: marca a mudanca em UTC -> tokens anteriores deixam de validar
                _execute_update(
                    "UPDATE dbo.WatcherDB_Users SET password_hash = ?, failed_attempts = 0, locked_until = NULL, "
                    "password_changed_at = SYSUTCDATETIME() WHERE username = ?",
                    (hashed, username)
                )
""",
     """        hashed = hash_password(new_password)
        # 2026-09-16: numa conta de dominio o password_hash e' o marcador ad_auth: e NAO se toca. "Trocar" ou
        # "repor" a password dessa conta e' mexer na senha local de recurso (mesmo modelo do
        # tools/set_local_password.py). Antes, este metodo reescrevia o marcador e a conta passava a local.
        try:
            actual = self._get_user_from_db(username)
        except Exception:
            actual = None
        if e_conta_de_dominio(actual):
            try:
                _execute_update(
                    "UPDATE dbo.WatcherDB_Users SET local_password_hash = ?, local_password_set_at = SYSUTCDATETIME(), "
                    "failed_attempts = 0, locked_until = NULL, password_changed_at = SYSUTCDATETIME() WHERE username = ?",
                    (hashed, username)
                )
                return {"success": True, "conta_de_dominio": True,
                        "message": "Conta de dominio: definida a senha local de recurso. A entrada pelo dominio nao muda."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        try:
            try:
                # Lote P4 A-4.7: marca a mudanca em UTC -> tokens anteriores deixam de validar
                _execute_update(
                    "UPDATE dbo.WatcherDB_Users SET password_hash = ?, failed_attempts = 0, locked_until = NULL, "
                    "password_changed_at = SYSUTCDATETIME() WHERE username = ?",
                    (hashed, username)
                )
""", 1),
]

AUTH_EDITS = [
    ("""    get_auth_service, decode_token, _execute_query, _execute_update, verify_password,
""",
     """    get_auth_service, decode_token, _execute_query, _execute_update, verify_password, e_conta_de_dominio,
""", 1),
    ("""    db_user = service._get_user_from_db(user["username"])
    if not db_user or not verify_password(body.current_password, db_user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Password actual incorrecta")
""",
     """    db_user = service._get_user_from_db(user["username"])
    if not db_user:
        raise HTTPException(status_code=401, detail="Password actual incorrecta")
    if e_conta_de_dominio(db_user):
        # 2026-09-16: conta de dominio -- a password actual e' a senha LOCAL de recurso, nao o marcador ad_auth:
        # (contra o marcador dava sempre 401, mesmo com senha local definida). Sem senha local, nao ha o que trocar aqui.
        local_hash = db_user.get("local_password_hash") or ""
        if not local_hash:
            raise HTTPException(
                status_code=400,
                detail="Conta de dominio: a password muda-se no AD. Para definir uma senha local de recurso, peca ao administrador.",
            )
        if not verify_password(body.current_password, local_hash):
            raise HTTPException(status_code=401, detail="Password actual incorrecta")
    elif not verify_password(body.current_password, db_user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Password actual incorrecta")
""", 1),
    ("""    service = get_auth_service()
    result = await service.change_password(username, body.new_password)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # Set must_change_password so user changes on next login
""",
     """    service = get_auth_service()
    result = await service.change_password(username, body.new_password)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    if result.get("conta_de_dominio"):
        # 2026-09-16: numa conta de dominio o reset define a senha local de recurso e nao converte a conta.
        # A obrigacao de trocar nao se impoe a contas de dominio (a19585b), por isso nao se marca nada.
        return JSONResponse(content={"success": True, "conta_de_dominio": True,
                                     "message": f"{username} e uma conta de dominio: definida a senha local de recurso; a entrada pelo dominio nao muda"})

    # Set must_change_password so user changes on next login
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Repor a password de uma conta de domínio deixa de a converter em conta local** (16/09). O reset por\n"
    "  administrador reescrevia o marcador que diz \"esta conta entra pelo domínio\"; a partir daí a password do domínio\n"
    "  deixava de servir, sem aviso. Passa a definir a senha local de recurso, e a resposta diz isso. No self-service, um\n"
    "  utilizador de domínio com senha local de recurso consegue finalmente trocá-la (antes recebia sempre \"password\n"
    "  actual incorrecta\"), e sem senha local recebe uma explicação em vez de um erro. Contas locais: nada muda.\n"
    "  [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:120]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    svc = src["svc"].read_bytes().decode("utf-8")
    if MARK in svc:
        print("[ABORT] ja aplicado"); return 1
    out = {
        "svc": _apply(svc, SVC_EDITS, "auth_service"),
        "auth": _apply(src["auth"].read_bytes().decode("utf-8"), AUTH_EDITS, "auth_compat"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
    }
    compile(out["svc"], str(REL["svc"]), "exec")
    compile(out["auth"], str(REL["auth"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] auth_service 2 blocos (helper + change_password); auth_compat 3 (import, self-service, reset); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_reset_conta_ad_20260916.py "
          "tests/unit/test_troca_obrigatoria_20260916.py tests/unit/test_login_sets_cookie.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
