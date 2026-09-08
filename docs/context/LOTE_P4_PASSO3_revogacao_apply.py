"""LOTE P4 - PASSO 3: A-4.7 -- reset/mudanca de password revoga os JWT emitidos antes (opcao A).

Decisao do owner 2026-09-07; desenho do watcherdb-security-auditor: estado de revogacao tem de viver
na BD (sobrevive a restart, serve V33 e V34). Mecanismo: coluna dbo.WatcherDB_Users.password_changed_at
(UTC) escrita em cada change_password (reset por admin E auto-servico); get_current_user rejeita
qualquer token cujo `iat` (ja' presente em todos os tokens, create_access_token) seja anterior a essa
data (tolerancia 1 s para tokens emitidos no mesmo segundo). O mesmo caminho serve _require_auth,
_require_admin e o AuthEnforcementMiddleware.

Licao do cookie inerte (18/08 -> 05/09): NADA aqui falha em silencio. Se a coluna nao existir, o
servico continua a funcionar mas escreve UMA VEZ por processo um aviso inequivoco ("REVOGACAO DE
SESSAO POR RESET INACTIVA"), e o gate do QA (login -> reset -> pedido com o token antigo => 401)
e' a prova em runtime.

O que este script faz (idempotente; ancoras por texto unico; aborta se algo nao bater; EOL preservado):
  1. database/13_ADD_PASSWORD_CHANGED_AT.sql  (novo; idempotente; owner corre na BD -- regra 5)
  2. services/auth_service.py
     - 3 SELECTs de utilizador (v13 / v12 / legacy) com degradacao explicita e aviso por coluna
     - helper _token_valido_apos_reset(payload, user) + aviso unico por processo
     - get_current_user rejeita token anterior a password_changed_at
     - change_password grava password_changed_at = SYSUTCDATETIME() (com fallback avisado)
  3. api/routers/auth_compat.py
     - /change-password (auto-servico) emite token NOVO + cookie, para o proprio utilizador nao ser
       deslogado pela sua propria mudanca (a revogacao apanha as OUTRAS sessoes)
  4. templates/watcherdb_portal.html: apos mudar a password, a UI guarda o token novo (setAuthData)
  5. database/INSTALACAO_COMPLETA_UNIFICADA.sql: SECAO 13 -- tabelas de autenticacao (Users,
     Auth_Log, User_Preferences) + colunas das migracoes 12 e 13. Hoje o canonico NAO cria nenhuma
     tabela de auth (0 ocorrencias) -- regra 2 do owner. SEM os utilizadores semente de
     CREATE_USER_AUTH_PREFS.sql (contas por omissao nao pertencem ao canonico).
  6. docs/guides/referencia_tecnica.md: linha das migracoes 12/13
  7. tests/unit/test_reset_revoga_token.py (9 testes, sem BD)

Fora deste lote: migracao 07 (must_change_password, DEFAULT 1 obriga todos a mudar -- decisao
separada); mensagens dos ramos AD.

Uso (raiz do repo):  py docs/context/LOTE_P4_PASSO3_revogacao_apply.py
Depois:              py -m pytest tests/unit/test_reset_revoga_token.py tests/unit/test_login_generic_and_lockout.py tests/unit/test_login_sets_cookie.py -q --no-cov
                     correr database/12_ADD_LOCAL_PASSWORD_HASH.sql e database/13_ADD_PASSWORD_CHANGED_AT.sql na
                     WatcherDB_Intelligence (identidade: a tua de administracao da BD; sql_monitoring so' consulta)
                     Restart-Service WatcherDBWebServiceV34; confirmar no log a AUSENCIA de "REVOGACAO ... INACTIVA"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH_SVC = ROOT / "services" / "auth_service.py"
AUTH_RT = ROOT / "api" / "routers" / "auth_compat.py"
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
CANON = ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql"
PREFS_SQL = ROOT / "database" / "CREATE_USER_AUTH_PREFS.sql"
MIG13 = ROOT / "database" / "13_ADD_PASSWORD_CHANGED_AT.sql"
DOC = ROOT / "docs" / "guides" / "referencia_tecnica.md"
TEST = ROOT / "tests" / "unit" / "test_reset_revoga_token.py"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


def _read(p: Path) -> tuple[str, str]:
    raw = p.read_text(encoding="utf-8", newline="")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def _write(p: Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def _apply(p: Path, edits: list[tuple[str, str]], done_marker: str) -> None:
    raw, eol = _read(p)
    if done_marker in raw:
        print(f"{p.name}: ja aplicado (skip)")
        return
    for old, _new in edits:
        o = old.replace("\n", eol)
        if raw.count(o) != 1:
            abort(f"{p.name}: esperava 1x a ancora que comeca por {old[:70]!r}, encontrei {raw.count(o)}")
    for old, new in edits:
        raw = raw.replace(old.replace("\n", eol), new.replace("\n", eol), 1)
    _write(p, raw)
    print(f"{p.name}: {len(edits)} substituicoes ancoradas")


# =====================================================================================
# 1. migracao 13
# =====================================================================================
MIG13_SQL = """-- =============================================================================
-- 13_ADD_PASSWORD_CHANGED_AT.sql  (WatcherDB V3.4, lote P4 A-4.7, 2026-09-08)
-- Revogacao de sessoes por mudanca/reset de password: o servico rejeita qualquer
-- JWT cujo iat seja anterior a password_changed_at (UTC). Sem esta coluna o
-- servico continua a funcionar mas escreve no log
-- "REVOGACAO DE SESSAO POR RESET INACTIVA" uma vez por processo.
-- Idempotente (sys.columns). Pode ser corrido N vezes. Correr com conta de
-- administracao da BD; sql_monitoring so' consulta.
-- =============================================================================
USE WatcherDB_Intelligence;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'password_changed_at'
)
BEGIN
    ALTER TABLE dbo.WatcherDB_Users
        ADD password_changed_at DATETIME2(0) NULL;
    PRINT 'password_changed_at adicionada a dbo.WatcherDB_Users';
END
ELSE
    PRINT 'password_changed_at ja existe (skip)';
GO
"""
if MIG13.exists():
    print("13_ADD_PASSWORD_CHANGED_AT.sql: ja existe (skip)")
else:
    MIG13.write_text(MIG13_SQL, encoding="utf-8")
    print("database/13_ADD_PASSWORD_CHANGED_AT.sql criado")

# =====================================================================================
# 2. services/auth_service.py
# =====================================================================================
SVC_EDITS = [
    # (a) helper + SELECTs + aviso unico, antes do bloco LDAP
    (
        "# ==========================================\n"
        "# LDAP / Active Directory Authentication (generic, configurable)\n",
        "# ==========================================\n"
        "# Revogacao de sessao por mudanca de password (lote P4 A-4.7, 2026-09-08)\n"
        "# ==========================================\n"
        "_USER_COLS_BASE = \"id, username, password_hash, role, email, full_name, disabled, failed_attempts, locked_until, last_login\"\n"
        "_USER_SELECT_LEGACY = f\"SELECT {_USER_COLS_BASE} FROM dbo.WatcherDB_Users WHERE username = ?\"\n"
        "_USER_SELECT_V12 = f\"SELECT {_USER_COLS_BASE}, local_password_hash FROM dbo.WatcherDB_Users WHERE username = ?\"\n"
        "_USER_SELECT_V13 = f\"SELECT {_USER_COLS_BASE}, local_password_hash, password_changed_at FROM dbo.WatcherDB_Users WHERE username = ?\"\n"
        "_AVISOS_SCHEMA_EMITIDOS: set = set()\n"
        "\n"
        "\n"
        "def _avisar_schema_uma_vez(chave: str, mensagem: str) -> None:\n"
        "    \"\"\"Aviso de schema em falta: UMA linha por processo, em WARNING, e nao a cada pedido.\"\"\"\n"
        "    if chave not in _AVISOS_SCHEMA_EMITIDOS:\n"
        "        _AVISOS_SCHEMA_EMITIDOS.add(chave)\n"
        "        logger.warning(mensagem)\n"
        "\n"
        "\n"
        "def _token_valido_apos_reset(payload: dict, user: dict, tolerancia_s: int = 1) -> bool:\n"
        "    \"\"\"False se o token foi emitido ANTES da ultima mudanca de password do utilizador.\n"
        "\n"
        "    - user sem a chave password_changed_at (schema sem a migracao 13): aceita, mas avisa\n"
        "      uma vez por processo -- a revogacao esta' INACTIVA e isso tem de ser visivel no log.\n"
        "    - password_changed_at NULL (nunca mudou): aceita.\n"
        "    - token sem iat: rejeita (nao se prova que e' posterior).\n"
        "    - iat + tolerancia >= password_changed_at (UTC): aceita.\n"
        "    \"\"\"\n"
        "    if \"password_changed_at\" not in user:\n"
        "        _avisar_schema_uma_vez(\n"
        "            \"password_changed_at\",\n"
        "            \"[AUTH] coluna password_changed_at em falta em dbo.WatcherDB_Users -- \"\n"
        "            \"REVOGACAO DE SESSAO POR RESET INACTIVA. Run database/13_ADD_PASSWORD_CHANGED_AT.sql\",\n"
        "        )\n"
        "        return True\n"
        "    changed = user.get(\"password_changed_at\")\n"
        "    if not changed:\n"
        "        return True\n"
        "    iat = payload.get(\"iat\")\n"
        "    if iat is None:\n"
        "        return False\n"
        "    if isinstance(changed, str):\n"
        "        changed = datetime.fromisoformat(changed)\n"
        "    if changed.tzinfo is None:\n"
        "        changed = changed.replace(tzinfo=timezone.utc)  # SYSUTCDATETIME() -> UTC\n"
        "    return float(iat) + tolerancia_s >= changed.timestamp()\n"
        "\n"
        "\n"
        "# ==========================================\n"
        "# LDAP / Active Directory Authentication (generic, configurable)\n",
    ),
    # (b) _get_user_from_db: v13 -> v12 -> legacy, cada degradacao avisada
    (
        "            try:\n"
        "                # Schema novo (com dual auth)\n"
        "                rows = _execute_query(\n"
        "                    \"SELECT id, username, password_hash, local_password_hash, role, email, full_name, disabled, \"\n"
        "                    \"failed_attempts, locked_until, last_login FROM dbo.WatcherDB_Users WHERE username = ?\",\n"
        "                    (username,)\n"
        "                )\n"
        "            except Exception as e:\n"
        "                # Schema legacy: a coluna local_password_hash ainda nao existe\n"
        "                # (script 12_ADD_LOCAL_PASSWORD_HASH.sql nao foi corrido)\n"
        "                if 'local_password_hash' in str(e) or 'Invalid column' in str(e):\n"
        "                    logger.warning(\n"
        "                        f\"[AUTH] local_password_hash column missing — caindo para schema legacy. \"\n"
        "                        f\"Run database/12_ADD_LOCAL_PASSWORD_HASH.sql para activar dual auth.\"\n"
        "                    )\n"
        "                    rows = _execute_query(\n"
        "                        \"SELECT id, username, password_hash, role, email, full_name, disabled, \"\n"
        "                        \"failed_attempts, locked_until, last_login FROM dbo.WatcherDB_Users WHERE username = ?\",\n"
        "                        (username,)\n"
        "                    )\n"
        "                else:\n"
        "                    raise\n",
        "            # Schema v13 (migracoes 12 + 13) -> v12 (so' 12) -> legacy (nenhuma), cada degradacao\n"
        "            # avisada UMA vez por processo. Lote P4 A-4.7 (2026-09-08): a revogacao por reset\n"
        "            # depende de password_changed_at; sem a coluna o servico funciona mas avisa.\n"
        "            def _sel(q):\n"
        "                return _execute_query(q, (username,))\n"
        "\n"
        "            def _coluna_em_falta(err, col):\n"
        "                s = str(err)\n"
        "                return col in s or ('Invalid column' in s and col == 'local_password_hash')\n"
        "\n"
        "            try:\n"
        "                rows = _sel(_USER_SELECT_V13)\n"
        "            except Exception as e:\n"
        "                if _coluna_em_falta(e, 'password_changed_at') or _coluna_em_falta(e, 'local_password_hash'):\n"
        "                    _avisar_schema_uma_vez(\n"
        "                        \"select_v13\",\n"
        "                        \"[AUTH] dbo.WatcherDB_Users sem password_changed_at -- REVOGACAO DE SESSAO POR RESET \"\n"
        "                        \"INACTIVA. Run database/13_ADD_PASSWORD_CHANGED_AT.sql\",\n"
        "                    )\n"
        "                    try:\n"
        "                        rows = _sel(_USER_SELECT_V12)\n"
        "                    except Exception as e2:\n"
        "                        if _coluna_em_falta(e2, 'local_password_hash'):\n"
        "                            _avisar_schema_uma_vez(\n"
        "                                \"select_v12\",\n"
        "                                \"[AUTH] local_password_hash column missing — schema legacy. \"\n"
        "                                \"Run database/12_ADD_LOCAL_PASSWORD_HASH.sql para activar dual auth.\",\n"
        "                            )\n"
        "                            rows = _sel(_USER_SELECT_LEGACY)\n"
        "                        else:\n"
        "                            raise\n"
        "                else:\n"
        "                    raise\n",
    ),
    # (c) get_current_user: rejeita token anterior a' mudanca de password
    (
        "        user = self._get_user_from_db(username)\n"
        "        if not user or user.get(\"disabled\"):\n"
        "            return None\n"
        "        return {\n"
        "            \"username\": username,\n"
        "            \"role\": user.get(\"role\", payload.get(\"role\", \"viewer\")),\n",
        "        user = self._get_user_from_db(username)\n"
        "        if not user or user.get(\"disabled\"):\n"
        "            return None\n"
        "        if not _token_valido_apos_reset(payload, user):\n"
        "            # Lote P4 A-4.7: token emitido antes do ultimo reset/mudanca de password\n"
        "            return None\n"
        "        return {\n"
        "            \"username\": username,\n"
        "            \"role\": user.get(\"role\", payload.get(\"role\", \"viewer\")),\n",
    ),
    # (d) change_password grava password_changed_at (UTC), com fallback avisado
    (
        "        hashed = hash_password(new_password)\n"
        "        try:\n"
        "            _execute_update(\n"
        "                \"UPDATE dbo.WatcherDB_Users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE username = ?\",\n"
        "                (hashed, username)\n"
        "            )\n"
        "            return {\"success\": True}\n",
        "        hashed = hash_password(new_password)\n"
        "        try:\n"
        "            try:\n"
        "                # Lote P4 A-4.7: marca a mudanca em UTC -> tokens anteriores deixam de validar\n"
        "                _execute_update(\n"
        "                    \"UPDATE dbo.WatcherDB_Users SET password_hash = ?, failed_attempts = 0, locked_until = NULL, \"\n"
        "                    \"password_changed_at = SYSUTCDATETIME() WHERE username = ?\",\n"
        "                    (hashed, username)\n"
        "                )\n"
        "            except Exception as e:\n"
        "                if 'password_changed_at' in str(e) or 'Invalid column' in str(e):\n"
        "                    _avisar_schema_uma_vez(\n"
        "                        \"update_v13\",\n"
        "                        \"[AUTH] change_password sem password_changed_at -- REVOGACAO DE SESSAO POR RESET \"\n"
        "                        \"INACTIVA. Run database/13_ADD_PASSWORD_CHANGED_AT.sql\",\n"
        "                    )\n"
        "                    _execute_update(\n"
        "                        \"UPDATE dbo.WatcherDB_Users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE username = ?\",\n"
        "                        (hashed, username)\n"
        "                    )\n"
        "                else:\n"
        "                    raise\n"
        "            return {\"success\": True}\n",
    ),
]
_apply(AUTH_SVC, SVC_EDITS, "_token_valido_apos_reset")

# =====================================================================================
# 3. api/routers/auth_compat.py
# =====================================================================================
RT_EDITS = [
    (
        "    get_auth_service, decode_token, _execute_query, _execute_update, verify_password\n",
        "    get_auth_service, decode_token, _execute_query, _execute_update, verify_password,\n"
        "    create_access_token\n",
    ),
    (
        "@router.post(\"/login\", response_model=LoginResponse)\n",
        "def _set_session_cookie(response: JSONResponse, request: Request, token: str) -> None:\n"
        "    \"\"\"Cookie de sessao com os mesmos atributos do login (HttpOnly, SameSite=lax, Secure em HTTPS).\"\"\"\n"
        "    response.set_cookie(\n"
        "        key=\"access_token\",\n"
        "        value=token,\n"
        "        httponly=True,\n"
        "        secure=(request.url.scheme == \"https\"),\n"
        "        samesite=\"lax\",\n"
        "        max_age=86400,\n"
        "        path=\"/\",\n"
        "    )\n"
        "\n"
        "\n"
        "@router.post(\"/login\", response_model=LoginResponse)\n",
    ),
    (
        "    # Clear must_change_password flag after successful password change\n"
        "    try:\n"
        "        _execute_update(\n"
        "            \"UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE username = ?\",\n"
        "            (user[\"username\"],),\n"
        "        )\n"
        "    except Exception:\n"
        "        pass  # Column may not exist yet — graceful degradation\n"
        "\n"
        "    return JSONResponse(content=result)\n",
        "    # Clear must_change_password flag after successful password change\n"
        "    try:\n"
        "        _execute_update(\n"
        "            \"UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE username = ?\",\n"
        "            (user[\"username\"],),\n"
        "        )\n"
        "    except Exception:\n"
        "        pass  # Column may not exist yet — graceful degradation\n"
        "\n"
        "    # Lote P4 A-4.7 (2026-09-08): a mudanca de password revoga TODOS os tokens anteriores\n"
        "    # (password_changed_at). Para o proprio utilizador nao ficar deslogado, emite-se um\n"
        "    # token novo (iat posterior a' mudanca) e o cookie e' renovado. As outras sessoes caem.\n"
        "    novo_token = create_access_token({\"sub\": user[\"username\"], \"role\": user.get(\"role\", \"viewer\")})\n"
        "    result = dict(result)\n"
        "    result[\"access_token\"] = novo_token\n"
        "    result[\"token_type\"] = \"bearer\"\n"
        "    result[\"user\"] = {\n"
        "        \"username\": user[\"username\"],\n"
        "        \"role\": user.get(\"role\", \"viewer\"),\n"
        "        \"full_name\": user.get(\"full_name\", user[\"username\"]),\n"
        "        \"email\": user.get(\"email\"),\n"
        "    }\n"
        "    response = JSONResponse(content=result)\n"
        "    _set_session_cookie(response, request, novo_token)\n"
        "    return response\n",
    ),
]
_apply(AUTH_RT, RT_EDITS, "_set_session_cookie")

# =====================================================================================
# 4. portal: guardar o token novo apos mudar a password
# =====================================================================================
PORTAL_EDITS = [
    (
        "                if (resp.ok && data.success) {\n"
        "                    msg.style.display = 'block'; msg.style.background = 'rgba(34,197,94,0.15)'; msg.style.color = '#22c55e';\n"
        "                    msg.textContent = 'Senha alterada com sucesso!';\n",
        "                if (resp.ok && data.success) {\n"
        "                    // A-4.7 (2026-09-08): a mudanca revoga os tokens antigos; o servidor devolve um novo.\n"
        "                    if (data.access_token) { setAuthData(data.access_token, data.user || window._currentUser); }\n"
        "                    msg.style.display = 'block'; msg.style.background = 'rgba(34,197,94,0.15)'; msg.style.color = '#22c55e';\n"
        "                    msg.textContent = 'Senha alterada com sucesso!';\n",
    ),
]
_apply(PORTAL, PORTAL_EDITS, "A-4.7 (2026-09-08)")

# =====================================================================================
# 5. canonico: SECAO 13 -- autenticacao (tabelas + colunas 12/13, SEM utilizadores semente)
# =====================================================================================
canon_raw, canon_eol = _read(CANON)
MARK = "-- SECAO 13: AUTENTICACAO"
if MARK in canon_raw:
    print("INSTALACAO_COMPLETA_UNIFICADA.sql: SECAO 13 ja existe (skip)")
else:
    prefs = PREFS_SQL.read_text(encoding="utf-8").replace("\r\n", "\n")
    a = prefs.find("IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_Users')")
    b = prefs.find("IF NOT EXISTS (SELECT 1 FROM dbo.WatcherDB_Users WHERE username =")
    if a == -1 or b == -1 or b <= a:
        abort("CREATE_USER_AUTH_PREFS.sql: nao encontrei o bloco das 3 tabelas (sem os utilizadores semente)")
    tabelas = prefs[a:b].rstrip()
    # o bloco termina num GO; garantimos que nao arrasta comentarios da seccao das sementes
    tabelas = tabelas[: tabelas.rfind("GO") + 2]
    secao = (
        "\n"
        "-- ============================================================================\n"
        f"{MARK} (WatcherDB_Users, WatcherDB_Auth_Log, WatcherDB_User_Preferences)\n"
        "-- Origem: database/CREATE_USER_AUTH_PREFS.sql (tabelas) + 12_ADD_LOCAL_PASSWORD_HASH.sql\n"
        "-- + 13_ADD_PASSWORD_CHANGED_AT.sql. Incluido no canonico em 2026-09-08 (lote P4 A-4.7):\n"
        "-- ate' aqui o canonico nao criava NENHUMA tabela de autenticacao. SEM utilizadores\n"
        "-- semente: contas por omissao nao pertencem ao canonico (criar pela UI de admin).\n"
        "-- Nao inclui 07_ADD_MUST_CHANGE_PASSWORD.sql (DEFAULT 1 obriga todos a mudar; decisao\n"
        "-- separada do owner).\n"
        "-- ============================================================================\n"
        "USE [WatcherDB_Intelligence];\n"
        "GO\n"
        f"{tabelas}\n"
        "\n"
        "-- 12: dual auth (AD + fallback local)\n"
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_hash')\n"
        "    ALTER TABLE dbo.WatcherDB_Users ADD local_password_hash NVARCHAR(500) NULL;\n"
        "GO\n"
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_set_at')\n"
        "    ALTER TABLE dbo.WatcherDB_Users ADD local_password_set_at DATETIME2(0) NULL;\n"
        "GO\n"
        "-- 13: revogacao de sessao por mudanca/reset de password\n"
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'password_changed_at')\n"
        "    ALTER TABLE dbo.WatcherDB_Users ADD password_changed_at DATETIME2(0) NULL;\n"
        "GO\n"
        "PRINT '  - Secao 13: Autenticacao (WatcherDB_Users/Auth_Log/User_Preferences + colunas 12/13)';\n"
        "GO\n"
    )
    _write(CANON, canon_raw.rstrip("\r\n") + secao.replace("\n", canon_eol) + canon_eol)
    print("INSTALACAO_COMPLETA_UNIFICADA.sql: SECAO 13 (autenticacao) acrescentada no fim")

# =====================================================================================
# 6. docs
# =====================================================================================
DOC_EDITS = [
    (
        "|   +-- CREATE_USER_AUTH_PREFS.sql # Schema: Users, Auth_Log, Preferences\n",
        "|   +-- CREATE_USER_AUTH_PREFS.sql # Schema: Users, Auth_Log, Preferences\n"
        "|   +-- 12_ADD_LOCAL_PASSWORD_HASH.sql   # Dual auth (AD + fallback local) -- obrigatorio\n"
        "|   +-- 13_ADD_PASSWORD_CHANGED_AT.sql   # Revogacao de sessao por reset (P4 A-4.7) -- obrigatorio\n",
    ),
]
if DOC.exists():
    _apply(DOC, DOC_EDITS, "13_ADD_PASSWORD_CHANGED_AT.sql")
else:
    print("referencia_tecnica.md nao existe (skip docs)")

# =====================================================================================
# 7. testes
# =====================================================================================
TEST_SRC = '''"""Gate A-4.7 (pauta P4 do QA externo): mudanca/reset de password revoga os JWT anteriores.

Sem BD. A prova em runtime (login -> reset pelo admin -> pedido com o token antigo => 401) e' o
gate do QA externo; aqui fixa-se a logica e a ausencia de falha silenciosa.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

import services.auth_service as auth
from services.auth_service import AuthService, _token_valido_apos_reset, create_access_token


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()  # como SYSUTCDATETIME() chega via isoformat()


# ---------------------------------------------------------------- helper puro

def test_token_anterior_a_mudanca_e_rejeitado():
    agora = datetime.now(timezone.utc)
    payload = {"sub": "u", "iat": (agora - timedelta(minutes=10)).timestamp()}
    assert _token_valido_apos_reset(payload, {"password_changed_at": _iso(agora)}) is False


def test_token_posterior_a_mudanca_e_aceite():
    agora = datetime.now(timezone.utc)
    payload = {"sub": "u", "iat": (agora + timedelta(seconds=5)).timestamp()}
    assert _token_valido_apos_reset(payload, {"password_changed_at": _iso(agora)}) is True


def test_mesmo_segundo_e_aceite_por_tolerancia():
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {"sub": "u", "iat": int(agora.timestamp())}
    assert _token_valido_apos_reset(payload, {"password_changed_at": _iso(agora)}) is True


def test_sem_mudanca_registada_aceita():
    payload = {"sub": "u", "iat": 1}
    assert _token_valido_apos_reset(payload, {"password_changed_at": None}) is True


def test_token_sem_iat_e_rejeitado_quando_ha_mudanca():
    assert _token_valido_apos_reset({"sub": "u"}, {"password_changed_at": _iso(datetime.now(timezone.utc))}) is False


def test_schema_sem_coluna_aceita_mas_avisa_alto(caplog):
    auth._AVISOS_SCHEMA_EMITIDOS.discard("password_changed_at")
    with caplog.at_level(logging.WARNING, logger="services.auth_service"):
        ok = _token_valido_apos_reset({"sub": "u", "iat": 1}, {"username": "u"})
    assert ok is True
    assert any("REVOGACAO DE SESSAO POR RESET INACTIVA" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- get_current_user

@pytest.fixture
def svc(monkeypatch):
    s = AuthService()
    return s


def test_get_current_user_rejeita_token_antigo(svc, monkeypatch):
    token = create_access_token({"sub": "u", "role": "viewer"})
    futuro = datetime.now(timezone.utc) + timedelta(seconds=30)
    monkeypatch.setattr(svc, "_get_user_from_db", lambda n: {"username": "u", "role": "viewer", "disabled": 0,
                                                              "password_changed_at": _iso(futuro)})
    assert asyncio.run(svc.get_current_user(token)) is None


def test_get_current_user_aceita_token_recente(svc, monkeypatch):
    token = create_access_token({"sub": "u", "role": "viewer"})
    passado = datetime.now(timezone.utc) - timedelta(minutes=5)
    monkeypatch.setattr(svc, "_get_user_from_db", lambda n: {"username": "u", "role": "viewer", "disabled": 0,
                                                              "password_changed_at": _iso(passado)})
    user = asyncio.run(svc.get_current_user(token))
    assert user and user["username"] == "u"


# ---------------------------------------------------------------- escrita e SELECT

def test_change_password_grava_password_changed_at(svc, monkeypatch):
    queries = []
    monkeypatch.setattr(auth, "_execute_update", lambda q, p=None: queries.append(q))
    monkeypatch.setattr(auth, "hash_password", lambda p: "h")
    r = asyncio.run(svc.change_password("u", "NovaPass123!"))
    assert r["success"] is True
    assert any("password_changed_at = SYSUTCDATETIME()" in q for q in queries)


def test_select_v13_le_a_coluna():
    assert "password_changed_at" in auth._USER_SELECT_V13
    assert "password_changed_at" not in auth._USER_SELECT_V12
'''
if TEST.exists():
    print("teste ja existe (skip)")
else:
    TEST.write_text(TEST_SRC, encoding="utf-8")
    print("tests/unit/test_reset_revoga_token.py criado (10 testes)")

print("\nPASSO 3 concluido. Correr:")
print("  py -m pytest tests/unit/test_reset_revoga_token.py tests/unit/test_login_generic_and_lockout.py tests/unit/test_login_sets_cookie.py -q --no-cov")
print("  BD (tu, conta de administracao): database/12_ADD_LOCAL_PASSWORD_HASH.sql ; database/13_ADD_PASSWORD_CHANGED_AT.sql")
print("  Restart-Service WatcherDBWebServiceV34 ; Select-String logs\\service_stderr.log -Pattern 'INACTIVA' -> tem de dar VAZIO")
