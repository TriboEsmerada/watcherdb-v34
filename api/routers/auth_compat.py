"""
Authentication Router — WatcherDB V3.2
Endpoints: login, validate, me, logout, users CRUD, preferences sync (encrypted with Fernet),
heartbeat, online users, AD config, role management, system config.
"""
import os
import logging
import time as _time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from watcherdb.core.same_origin import require_same_origin
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

from services.auth_service import (
    get_auth_service, decode_token, _execute_query, _execute_update, verify_password
)
from api.error_helpers import safe_http_error
from api.models import (
    LoginResponse, UserInfo, UserListResponse, TokenValidationResponse,
    MessageResponse, SuccessResponse, GenericResponse, PreferencesResponse,
    SavePreferencesResponse, DeletePreferenceResponse, AuthLogResponse,
    SessionsResponse, OnlineUsersResponse,
)
from api.pagination import paginate, PaginationParams

logger = logging.getLogger(__name__)
from api.versioning import AUTH_PREFIX
router = APIRouter(prefix=AUTH_PREFIX, tags=["Authentication"])


# ============================================
# REQUEST MODELS
# ============================================
class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    email: Optional[str] = None
    full_name: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str


class ToggleUserRequest(BaseModel):
    disabled: bool


class ResetPasswordRequest(BaseModel):
    new_password: str


class SessionPolicyRequest(BaseModel):
    jwt_expire_minutes: int = 480
    max_failed_attempts: int = 5
    lockout_minutes: int = 30


class SavePreferencesRequest(BaseModel):
    preferences: dict  # {key: value, ...}


class AdConfigRequest(BaseModel):
    enabled: bool = False
    domain: str = ""
    server: str = ""
    base_dn: str = ""
    default_role: str = "viewer"
    bind_user: str = ""
    bind_password: str = ""


class AdDomainsRequest(BaseModel):
    enabled: bool = False
    domains: list = []


class ChangeRoleRequest(BaseModel):
    role: str


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


# ============================================
# TOKEN BLACKLIST — DB-persisted with in-memory LRU cache
# ============================================
import hashlib
from datetime import datetime, timedelta, timezone
from collections import OrderedDict

class _TokenBlacklistManager:
    """Token blacklist persisted in WatcherDB_Token_Blacklist table.
    Falls back to in-memory set if DB is unavailable."""

    def __init__(self, max_cache_size: int = 1000):
        self._memory_cache: OrderedDict[str, bool] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._fallback_set: set = set()  # used if DB unavailable

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def add(self, token: str, username: str = "", expires_minutes: int = 1440):
        """Blacklist a token (persist to DB, cache in memory)."""
        token_hash = self._hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

        # Always add to memory cache
        self._memory_cache[token_hash] = True
        if len(self._memory_cache) > self._max_cache_size:
            self._memory_cache.popitem(last=False)

        # Try to persist to DB
        try:
            _execute_update(
                "INSERT INTO dbo.WatcherDB_Token_Blacklist (token_hash, username, expires_at) "
                "VALUES (?, ?, ?)",
                (token_hash, username, expires_at),
            )
        except Exception as e:
            logger.warning(f"Token blacklist DB insert failed (using memory fallback): {e}")
            self._fallback_set.add(token_hash)

    def __contains__(self, token: str) -> bool:
        """Check if token is blacklisted (memory first, then DB)."""
        token_hash = self._hash_token(token)

        # Fast path: check memory cache
        if token_hash in self._memory_cache:
            return True
        if token_hash in self._fallback_set:
            return True

        # Slow path: check DB
        try:
            rows = _execute_query(
                "SELECT 1 FROM dbo.WatcherDB_Token_Blacklist "
                "WHERE token_hash = ? AND expires_at > GETDATE()",
                (token_hash,),
            )
            if rows:
                # Promote to memory cache
                self._memory_cache[token_hash] = True
                if len(self._memory_cache) > self._max_cache_size:
                    self._memory_cache.popitem(last=False)
                return True
        except Exception:
            pass

        return False


_token_blacklist = _TokenBlacklistManager()

# Online heartbeat tracking (in-memory)
_online_heartbeats: dict = {}
_ONLINE_TIMEOUT_SEC = 120  # 2 minutes


# ============================================
# AUTH HELPERS
# ============================================
# Valores que aparecem no cabecalho quando o cliente o constroi a mao com um
# token ausente -- `Bearer ${token}` com token null/undefined da literalmente
# "Bearer null". Nao sao tokens: sao ausencia de token com outra roupa.
_TOKEN_STUBS = frozenset({"null", "undefined", "none", "nan", "bearer"})


def _get_token_from_request(request: Request) -> Optional[str]:
    """Token do pedido: cabecalho primeiro, cookie como fallback.

    Os stubs sao descartados ANTES de cair no cookie. Sem isto um
    `Authorization: Bearer null` mascara um cookie valido e devolve 401 -- foi
    exactamente o defeito que o SSIS Manager apanhou na migracao para cookie
    HttpOnly (rbac.py, commit 6ec4c55, 2026-08-18), e o V3.3 tem doze sitios no
    portal que constroem o cabecalho a mao, fora do interceptor global.
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        candidato = auth_header[7:].strip()
        if candidato and candidato.lower() not in _TOKEN_STUBS:
            return candidato
    return request.cookies.get('access_token')


async def _require_auth(request: Request) -> dict:
    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Token nao fornecido")
    if token in _token_blacklist:
        raise HTTPException(status_code=401, detail="Token revogado")
    service = get_auth_service()
    user = await service.get_current_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado")
    # Check if user was disabled after token was issued
    try:
        db_user = service._get_user_from_db(user.get("username", ""))
        if db_user and db_user.get("disabled"):
            raise HTTPException(status_code=401, detail="Conta desactivada")
    except HTTPException:
        raise
    except Exception:
        pass  # DB unavailable — allow token-based auth to continue
    return user


async def _require_admin(request: Request) -> dict:
    """Controlo TOTAL: utilizadores, roles, config do sistema. So' `admin`.

    USAR VIA `Depends(_require_admin)` NA ASSINATURA, nunca `await` dentro do
    corpo da funcao. O FastAPI resolve as dependencias da assinatura ANTES de
    `request_body_to_args`; um gate chamado no corpo deixa o Pydantic validar
    primeiro, e um corpo invalido devolve 422 a quem nao esta autorizado --
    revelando nomes de campo e a forma do validador. Achado R2-01/R2-06 do QA
    externo (ronda 2, 2026-08-18): oito endpoints com corpo chamavam-no inline.
    """
    user = await _require_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user


async def _require_dba(request: Request) -> dict:
    """Operacao de DBA: `dba` ou `admin` (decisao do owner 2026-08-16).

    Usar em tudo o que e' diagnostico/operacao — LIVE, mutes, thresholds,
    collectors. `admin` passa sempre porque inclui o privilegio de `dba`.
    """
    user = await _require_auth(request)
    from watcherdb.core.auth import role_at_least, UserRole
    if not role_at_least(user.get("role"), UserRole.DBA.value):
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito a DBA ou administrador",
        )
    return user


# ============================================
# ENCRYPTION HELPERS (Fernet — lazy singleton)
# ============================================
_pref_cipher_cache = None
_pref_cipher_checked = False


def _get_pref_cipher():
    global _pref_cipher_cache, _pref_cipher_checked
    if _pref_cipher_checked:
        return _pref_cipher_cache
    _pref_cipher_checked = True
    try:
        from cryptography.fernet import Fernet
        key = os.environ.get('WATCHERDB_ENCRYPTION_KEY', '')
        if key:
            _pref_cipher_cache = Fernet(key.encode())
        else:
            logger.warning("[PREFS] WATCHERDB_ENCRYPTION_KEY nao definido — preferencias serao guardadas em plaintext")
    except Exception as e:
        logger.warning(f"[PREFS] Fernet indisponivel: {e}")
    return _pref_cipher_cache


def _encrypt_pref(value: str) -> str:
    cipher = _get_pref_cipher()
    if cipher and value:
        try:
            encrypted = cipher.encrypt(value.encode('utf-8')).decode('utf-8')
            return f"enc:{encrypted}"
        except Exception as e:
            logger.warning(f"[PREFS] Erro ao encriptar: {e}")
    return value


def _decrypt_pref(value: str) -> str:
    if not value or not value.startswith('enc:'):
        return value
    cipher = _get_pref_cipher()
    if cipher:
        try:
            return cipher.decrypt(value[4:].encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.warning(f"[PREFS] Erro ao desencriptar: {e}")
            return value[4:]
    return value[4:]


# ============================================
# ENDPOINTS — Authentication
# ============================================
@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, login_req: LoginRequest):
    auth_svc = get_auth_service()
    ip = request.client.host if request.client else None
    result = await auth_svc.authenticate(login_req.username, login_req.password, ip)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error", "Credenciais invalidas"))

    # Check must_change_password flag
    try:
        rows = _execute_query(
            "SELECT must_change_password FROM dbo.WatcherDB_Users WHERE username = ?",
            (login_req.username,),
        )
        if rows and rows[0].get("must_change_password"):
            result["must_change_password"] = True
    except Exception:
        pass  # Column may not exist yet — graceful degradation

    response = JSONResponse(content=result)
    # Cookie so' e' emitido se houver token. Chave e' access_token (auth_service devolve
    # access_token em todos os caminhos); ate' 2026-09-05 testava-se "token" e o cookie
    # nunca saia -- ver tests/unit/test_login_sets_cookie.py.
    if result.get("access_token"):
        # Bug-fix 2026-04-23: secure=True incondicional quebra acesso via HTTP
        # em ambientes internos (banking-grade on-premise frequentemente HTTP
        # atras de reverse-proxy). Se request for HTTP, setar secure=False
        # para o browser enviar o cookie. Em HTTPS, manter secure=True.
        # OWASP recomenda secure=True mas aceita este pattern quando TLS
        # termina num layer anterior (ex: IIS ARR, HAProxy).
        is_https = request.url.scheme == "https"
        response.set_cookie(
            key="access_token",
            value=result["access_token"],
            httponly=True,
            secure=is_https,   # True se HTTPS, False se HTTP (dev/internal)
            samesite="lax",
            max_age=86400,     # 24h matches JWT expiry
            path="/",
        )
    return response


@router.get("/validate", response_model=TokenValidationResponse)
async def validate_token(request: Request):
    token = _get_token_from_request(request)
    if not token:
        return JSONResponse(content={"valid": False})
    service = get_auth_service()
    user = await service.get_current_user(token)
    if user:
        return JSONResponse(content={"valid": True, "user": user})
    return JSONResponse(content={"valid": False})


@router.get("/me", response_model=UserInfo)
async def get_me(request: Request):
    user = await _require_auth(request)
    return JSONResponse(content=user)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request):
    token = _get_token_from_request(request)
    if token:
        user_info = decode_token(token)
        username = user_info.get("sub", "unknown") if user_info else "unknown"
        _token_blacklist.add(token, username=username)
    response = JSONResponse(content={"success": True, "message": "Logout realizado e token revogado"})
    response.delete_cookie("access_token", path="/")
    return response


@router.get("/users", response_model=UserListResponse)
async def list_users(
    request: Request,
    pagination: PaginationParams = Depends(),
    _admin: dict = Depends(_require_admin),
):
    service = get_auth_service()
    users = await service.list_users()
    return JSONResponse(content={"success": True, **paginate(users, pagination)})


@router.post("/users", response_model=SuccessResponse)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    # AD users: password starts with "ad_auth:" — skip strong password validation
    if not body.password.startswith("ad_auth:"):
        from services.auth_service import validate_strong_password
        error = validate_strong_password(body.password)
        if error:
            raise HTTPException(status_code=400, detail=f"Senha fraca: {error}")
    service = get_auth_service()
    result = await service.create_user(body.username, body.password, body.role, body.email, body.full_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return JSONResponse(content=result)


@router.post("/change-password", response_model=SuccessResponse)
async def change_password(body: ChangePasswordRequest, request: Request):
    user = await _require_auth(request)
    if not body.current_password:
        raise HTTPException(status_code=400, detail="Password actual obrigatoria")
    from services.auth_service import validate_strong_password
    error = validate_strong_password(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=f"Senha fraca: {error}")
    service = get_auth_service()
    # Verificar password actual antes de permitir alteracao
    db_user = service._get_user_from_db(user["username"])
    if not db_user or not verify_password(body.current_password, db_user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Password actual incorrecta")
    result = await service.change_password(user["username"], body.new_password)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # Clear must_change_password flag after successful password change
    try:
        _execute_update(
            "UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE username = ?",
            (user["username"],),
        )
    except Exception:
        pass  # Column may not exist yet — graceful degradation

    return JSONResponse(content=result)


@router.post("/users/{username}/toggle", response_model=SuccessResponse)
async def toggle_user(
    username: str,
    body: ToggleUserRequest,
    request: Request,
    admin: dict = Depends(_require_admin),
):
    if username == admin["username"]:
        raise HTTPException(status_code=400, detail="Nao pode desactivar a propria conta")
    service = get_auth_service()
    result = await service.toggle_user(username, body.disabled)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # If disabling: kill active session immediately
    if body.disabled:
        # Remove from online heartbeats
        if username in _online_heartbeats:
            del _online_heartbeats[username]
        # Blacklist all active tokens for this user by adding a marker
        # The _require_auth check will reject disabled users on next request
        logger.info(f"[AUTH] User {username} disabled — session terminated by {admin['username']}")

    return JSONResponse(content=result)


@router.post("/users/{username}/unlock", response_model=SuccessResponse)
async def unlock_user(
    username: str,
    request: Request,
    _admin: dict = Depends(_require_admin),
    _origem: None = Depends(require_same_origin),
):
    """Desbloqueia conta bloqueada por tentativas falhadas. Admin only."""
    service = get_auth_service()
    result = await service.unlock_user(username)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return JSONResponse(content={"success": True, "message": f"{username} desbloqueado"})


@router.post("/users/{username}/reset-password", response_model=SuccessResponse)
async def reset_password(
    username: str,
    body: ResetPasswordRequest,
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Admin resets any user's password."""

    # Validate strong password
    from services.auth_service import validate_strong_password
    error = validate_strong_password(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=f"Senha fraca: {error}")

    service = get_auth_service()
    result = await service.change_password(username, body.new_password)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # Set must_change_password so user changes on next login
    try:
        _execute_update(
            "UPDATE dbo.WatcherDB_Users SET must_change_password = 1 WHERE username = ?",
            (username,),
        )
    except Exception:
        pass

    return JSONResponse(content={"success": True, "message": f"Senha de {username} alterada com sucesso"})


@router.delete("/users/{username}", response_model=SuccessResponse)
async def delete_user(
    username: str,
    request: Request,
    admin: dict = Depends(_require_admin),
):
    """Permanently delete a user. Admin only."""
    if username == admin["username"]:
        raise HTTPException(status_code=400, detail="Nao pode remover a propria conta")

    service = get_auth_service()
    result = await service.delete_user(username)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return JSONResponse(content=result)


@router.post("/admin/users/{username}/update", response_model=SuccessResponse)
async def update_user_profile(
    username: str,
    body: UpdateUserRequest,
    request: Request,
    admin: dict = Depends(_require_admin),
):
    """Update user profile (name, email, role). Admin only."""
    if body.role and body.role not in ("admin", "dba", "viewer"):
        raise HTTPException(status_code=400, detail="Role invalido")
    service = get_auth_service()
    result = await service.update_user(username, body.full_name, body.email, body.role)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    if body.role:  # este endpoint tambem altera privilegio -> tem de auditar
        try:
            service._log_auth(
                username, "ROLE_CHANGED",
                request.client.host if request.client else None,
                f"-> {body.role} (via update de perfil por {(admin or {}).get('username', '?')})",
            )
        except Exception:
            pass
    return JSONResponse(content=result)


@router.post("/admin/session-policy", response_model=SuccessResponse)
async def update_session_policy(
    body: SessionPolicyRequest,
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Update session/auth policy in runtime. Admin only."""

    # Validate ranges
    if not (15 <= body.jwt_expire_minutes <= 10080):
        raise HTTPException(status_code=400, detail="JWT expiracao deve ser entre 15 e 10080 minutos")
    if not (1 <= body.max_failed_attempts <= 50):
        raise HTTPException(status_code=400, detail="Max tentativas deve ser entre 1 e 50")
    if not (1 <= body.lockout_minutes <= 1440):
        raise HTTPException(status_code=400, detail="Lockout deve ser entre 1 e 1440 minutos")

    # Apply in runtime + persist to DB
    from services.auth_service import save_session_policy
    save_session_policy(body.jwt_expire_minutes, body.max_failed_attempts, body.lockout_minutes)

    return JSONResponse(content={
        "success": True,
        "message": "Politica de sessao guardada na base de dados.",
        "policy": {
            "jwt_expire_minutes": body.jwt_expire_minutes,
            "max_failed_attempts": body.max_failed_attempts,
            "lockout_minutes": body.lockout_minutes,
        }
    })


# ============================================
# ENDPOINTS — User Preferences (encrypted with Fernet)
# ============================================
@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(request: Request):
    user = await _require_auth(request)
    username = user["username"]
    try:
        rows = _execute_query(
            "SELECT preference_key, preference_value FROM dbo.WatcherDB_User_Preferences WITH (NOLOCK) WHERE username = ?",
            (username,)
        )
        prefs = {}
        for row in rows:
            prefs[row["preference_key"]] = _decrypt_pref(row["preference_value"] or '')
        return JSONResponse(content={"success": True, "preferences": prefs})
    except Exception as e:
        logger.warning(f"[PREFS] Error loading preferences for {username}: {e}")
        return JSONResponse(content={"success": True, "preferences": {}})


@router.put("/preferences", response_model=SavePreferencesResponse)
async def save_preferences(body: SavePreferencesRequest, request: Request):
    user = await _require_auth(request)
    username = user["username"]
    saved = 0
    errors = []
    try:
        for key, value in body.preferences.items():
            if not key or len(key) > 100:
                errors.append(f"Chave invalida: {key}")
                continue
            str_value = str(value) if not isinstance(value, str) else value
            enc_value = _encrypt_pref(str_value)
            try:
                _execute_update(
                    """
                    MERGE dbo.WatcherDB_User_Preferences WITH (HOLDLOCK) AS target
                    USING (SELECT ? AS username, ? AS preference_key) AS source
                    ON target.username = source.username AND target.preference_key = source.preference_key
                    WHEN MATCHED THEN
                        UPDATE SET preference_value = ?, updated_at = GETDATE()
                    WHEN NOT MATCHED THEN
                        INSERT (username, preference_key, preference_value, updated_at)
                        VALUES (?, ?, ?, GETDATE());
                    """,
                    (username, key, enc_value, username, key, enc_value)
                )
                saved += 1
            except Exception as e:
                errors.append(f"{key}: {str(e)}")
        return JSONResponse(content={"success": True, "saved": saved, "errors": errors if errors else None})
    except Exception as e:
        raise safe_http_error(500, e, "saving user preferences")


@router.delete("/preferences/{key}", response_model=DeletePreferenceResponse)
async def delete_preference(key: str, request: Request):
    user = await _require_auth(request)
    username = user["username"]
    try:
        deleted = _execute_update(
            "DELETE FROM dbo.WatcherDB_User_Preferences WHERE username = ? AND preference_key = ?",
            (username, key)
        )
        return JSONResponse(content={"success": True, "deleted": deleted > 0})
    except Exception as e:
        raise safe_http_error(500, e, f"deleting preference {key}")


# ============================================
# ENDPOINTS — Admin: Auth Log / Audit
# ============================================
@router.get("/admin/auth-log", response_model=AuthLogResponse)
async def get_auth_log(
    request: Request,
    limit: int = 100,
    username: str = None,
    _admin: dict = Depends(_require_admin),
):
    limit = min(limit, 1000)  # Impedir queries excessivas
    try:
        if username:
            rows = _execute_query(
                "SELECT TOP (?) id, username, action, ip_address, details, created_at "
                "FROM dbo.WatcherDB_Auth_Log WITH (NOLOCK) WHERE username = ? ORDER BY created_at DESC",
                (limit, username)
            )
        else:
            rows = _execute_query(
                "SELECT TOP (?) id, username, action, ip_address, details, created_at "
                "FROM dbo.WatcherDB_Auth_Log WITH (NOLOCK) ORDER BY created_at DESC",
                (limit,)
            )
        return JSONResponse(content={"success": True, "logs": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse(content={"success": True, "logs": [], "count": 0, "error": str(e)})


# ============================================
# ENDPOINTS — Admin: Active Sessions (based on recent auth log)
# ============================================
@router.get("/admin/sessions", response_model=SessionsResponse)
async def get_active_sessions(
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    try:
        # Users with successful login in last 24h (approximation of active sessions)
        rows = _execute_query("""
            SELECT u.username, u.role, u.full_name, u.email, u.last_login,
                   l.ip_address, l.created_at as login_time
            FROM dbo.WatcherDB_Users u WITH (NOLOCK)
            CROSS APPLY (
                SELECT TOP 1 ip_address, created_at
                FROM dbo.WatcherDB_Auth_Log WITH (NOLOCK)
                WHERE username = u.username AND action = 'LOGIN_SUCCESS'
                ORDER BY created_at DESC
            ) l
            WHERE u.last_login >= DATEADD(HOUR, -24, GETDATE())
            ORDER BY l.created_at DESC
        """)
        return JSONResponse(content={"success": True, "sessions": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse(content={"success": True, "sessions": [], "count": 0, "error": str(e)})


# ============================================
# ENDPOINTS — Heartbeat (for online status tracking)
# ============================================
@router.post("/heartbeat", response_model=SuccessResponse)
async def heartbeat(request: Request):
    """Heartbeat do portal — marca user como online."""
    user = await _require_auth(request)
    _online_heartbeats[user["username"]] = {
        "last_seen": _time.time(),
        "ip": request.client.host if request.client else None,
        "role": user.get("role", "viewer"),
        "full_name": user.get("full_name", user["username"]),
    }
    return JSONResponse(content={"success": True})


@router.get("/admin/online", response_model=OnlineUsersResponse)
async def get_online_users(
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Retorna users online (heartbeat < 2 min)."""
    now = _time.time()
    online = []
    expired = []
    for username, info in _online_heartbeats.items():
        if now - info["last_seen"] < _ONLINE_TIMEOUT_SEC:
            online.append({
                "username": username,
                "full_name": info.get("full_name", username),
                "role": info.get("role", "viewer"),
                "ip": info.get("ip"),
                "last_seen": datetime.fromtimestamp(info["last_seen"]).isoformat(),
            })
        else:
            expired.append(username)
    for u in expired:
        del _online_heartbeats[u]
    return JSONResponse(content={"success": True, "online": online})


# ============================================
# ENDPOINTS — Admin: AD Lookup & Config
# ============================================
@router.get("/admin/ad-lookup/{username}", response_model=GenericResponse)
async def ad_lookup(
    username: str,
    request: Request,
    domain: str = None,
    _admin: dict = Depends(_require_admin),
):
    """Lookup user in Active Directory via LDAP. Admin only."""
    from services.auth_service import ad_lookup_user
    result = ad_lookup_user(username, domain=domain)
    if not result.get("success") and "error" in result:
        return JSONResponse(content=result, status_code=200)  # Return error info, not 500
    return JSONResponse(content=result)


@router.get("/admin/ad-discover", response_model=GenericResponse)
async def ad_discover(
    request: Request,
    domain: str = "",
    _admin: dict = Depends(_require_admin),
):
    """Discover Domain Controllers via DNS SRV records. Admin only."""
    if not domain:
        return JSONResponse(content={"success": False, "error": "Parametro 'domain' obrigatorio"})
    from services.auth_service import ad_discover_dcs
    result = ad_discover_dcs(domain)
    return JSONResponse(content=result)


@router.post("/admin/ad-config", response_model=SuccessResponse)
async def update_ad_config(
    body: AdConfigRequest,
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Actualiza configuracao do Active Directory (admin only). Persiste na DB."""
    from services.auth_service import save_ad_config
    save_ad_config(body.enabled, body.domain, body.server, body.base_dn, body.default_role,
                    body.bind_user, body.bind_password)
    return JSONResponse(content={
        "success": True,
        "message": "Configuracao AD guardada na base de dados.",
    })


@router.post("/admin/ad-domains", response_model=SuccessResponse)
async def update_ad_domains(
    body: AdDomainsRequest,
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Save multi-domain AD configuration. Admin only."""
    from services.auth_service import save_ad_domains
    save_ad_domains(body.enabled, body.domains)
    return JSONResponse(content={"success": True, "message": f"Configuracao AD guardada ({len(body.domains)} dominios)."})


# ============================================
# ENDPOINTS — Admin: Change User Role
# ============================================
@router.post("/admin/users/{username}/role", response_model=SuccessResponse)
async def change_user_role(
    username: str,
    body: ChangeRoleRequest,
    request: Request,
    admin: dict = Depends(_require_admin),
):
    """Altera role de um user (admin only)."""
    if body.role not in ("admin", "dba", "viewer"):
        raise HTTPException(status_code=400, detail="Role invalido (admin, dba ou viewer)")
    try:
        # Ler o role actual ANTES do UPDATE: sem isto o audit so' diria "ficou X",
        # nao "passou de Y para X" — e' a diferenca entre saber que houve mudanca
        # e conseguir reconstruir o historico de privilegios.
        try:
            _rows = _execute_query(
                "SELECT role FROM dbo.WatcherDB_Users WHERE username = ?", (username,)
            )
            _role_antes = (_rows[0].get("role") if _rows else None) or "?"
        except Exception:
            _role_antes = "?"
        _execute_update(
            "UPDATE dbo.WatcherDB_Users SET role = ? WHERE username = ?",
            (body.role, username)
        )
        # Auditoria da mudanca de privilegio (gap apanhado pelo QA externo
        # 2026-08-16 §10.5): era a escrita mais sensivel do produto e nao
        # deixava rasto nenhum no WatcherDB_Auth_Log.
        try:
            get_auth_service()._log_auth(
                username, "ROLE_CHANGED",
                request.client.host if request.client else None,
                f"{_role_antes} -> {body.role} (por {(admin or {}).get('username', '?')})",
            )
        except Exception:
            pass
        return JSONResponse(content={"success": True, "message": f"Role de {username} alterado para {body.role}"})
    except Exception as e:
        raise safe_http_error(500, e, f"changing role for {username}")


# ============================================
# ENDPOINTS — Admin: System Config (Control Panel)
# ============================================
@router.get("/admin/system-config", response_model=GenericResponse)
async def get_system_config(
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Retorna configuracao do sistema para o control panel."""
    import services.auth_service as auth_mod
    return JSONResponse(content={
        "success": True,
        "config": {
            "auth": {
                "jwt_expire_minutes": getattr(auth_mod, 'ACCESS_TOKEN_EXPIRE_MINUTES', 1440),
                "max_failed_attempts": getattr(auth_mod, 'MAX_FAILED_ATTEMPTS', 5),
                "lockout_minutes": getattr(auth_mod, 'LOCKOUT_MINUTES', 15),
            },
            "active_directory": {
                "enabled": getattr(auth_mod, 'AD_ENABLED', False),
                "domains": [
                    {**d, "bind_password": "********" if d.get("bind_password") else ""}
                    for d in getattr(auth_mod, 'AD_DOMAINS', [])
                ],
                # Legacy compat
                "domain": getattr(auth_mod, 'AD_DOMAIN', ''),
                "server": getattr(auth_mod, 'AD_SERVER', ''),
                "base_dn": getattr(auth_mod, 'AD_BASE_DN', ''),
                "default_role": getattr(auth_mod, 'AD_DEFAULT_ROLE', 'viewer'),
            },
            "environment": {
                "server": getattr(auth_mod, 'settings', {}).intelligence_server if hasattr(auth_mod, 'settings') else 'N/A',
                "database": getattr(auth_mod, 'settings', {}).intelligence_database if hasattr(auth_mod, 'settings') else 'N/A',
            }
        }
    })


@router.get("/admin/resources", response_model=GenericResponse)
async def get_resources(
    request: Request,
    _admin: dict = Depends(_require_admin),
):
    """Resource monitor — CPU, RAM, disk, uptime of WatcherDB process. Admin only."""
    import psutil
    import platform

    proc = psutil.Process()
    mem_info = proc.memory_info()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getcwd())

    # Uptime
    create_time = datetime.fromtimestamp(proc.create_time())
    uptime_delta = datetime.now() - create_time
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m"

    # Open files & connections (safe)
    try:
        open_files = len(proc.open_files())
    except Exception:
        open_files = -1
    try:
        connections = len(proc.net_connections())
    except Exception:
        connections = -1

    return JSONResponse(content={
        "success": True,
        "resources": {
            "process": {
                "pid": proc.pid,
                "cpu_pct": round(proc.cpu_percent(interval=0.1), 1),
                "memory_mb": round(mem_info.rss / 1024 / 1024, 1),
                "memory_vms_mb": round(mem_info.vms / 1024 / 1024, 1),
                "threads": proc.num_threads(),
                "open_files": open_files,
                "connections": connections,
                "uptime": uptime_str,
                "started_at": create_time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "server": {
                "hostname": platform.node(),
                "os": f"{platform.system()} {platform.version()}",
                "cpu_count": psutil.cpu_count(logical=True),
                "cpu_total_pct": round(psutil.cpu_percent(interval=0.1), 1),
                "memory_total_gb": round(vm.total / 1024**3, 1),
                "memory_used_gb": round(vm.used / 1024**3, 1),
                "memory_available_gb": round(vm.available / 1024**3, 1),
                "memory_pct": round(vm.percent, 1),
                "disk_path": os.getcwd()[:3],
                "disk_total_gb": round(disk.total / 1024**3, 1),
                "disk_used_gb": round(disk.used / 1024**3, 1),
                "disk_free_gb": round(disk.free / 1024**3, 1),
                "disk_pct": round(disk.percent, 1),
            },
            "runtime": {
                "python_version": platform.python_version(),
                "working_dir": os.getcwd(),
                "port": os.getenv("WATCHERDB_PORT", "8446"),
            }
        }
    })
