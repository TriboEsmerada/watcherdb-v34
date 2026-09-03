"""
Authentication and Authorization System
JWT-based authentication with role-based access control (RBAC)
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

# Configuration — usa services.secrets.get_secret para suportar valores encriptados
# (prefixo "encrypted:..." no .env). os.getenv directo nao desencripta.
from services.secrets import get_secret as _get_secret
# Fallback cruzado: JWT_SECRET_KEY (padrao) -> WATCHERDB_JWT_SECRET (legacy services/web_service)
# Evita erro/chave efemera quando qualquer das 2 envs esta definida.
SECRET_KEY = _get_secret("JWT_SECRET_KEY", "") or os.getenv("WATCHERDB_JWT_SECRET", "")
if not SECRET_KEY:
    if os.getenv("WATCHERDB_ENV", "production") == "production":
        raise ValueError(
            "JWT_SECRET_KEY or WATCHERDB_JWT_SECRET must be set in production environment. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    else:
        # Development fallback — generate ephemeral random key (safe, but tokens won't survive restart)
        import secrets as _secrets
        SECRET_KEY = _secrets.token_hex(32)
        logger.warning("JWT_SECRET_KEY/WATCHERDB_JWT_SECRET not set — generated ephemeral key. Tokens will not survive restart.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# ==========================================
# User Roles
# ==========================================
class UserRole(str, Enum):
    """User roles for RBAC.

    Decisao do owner 2026-08-16 (na sequencia do QA externo, N-05/decisao 2):
    `admin` fica reservado a controlo TOTAL — gestao de utilizadores, roles,
    configuracao do sistema (AD, JWT, sessoes). O trabalho operacional do DBA
    passa a ter role propria, para nao ser preciso dar controlo total a quem so'
    precisa de diagnosticar.

    Hierarquia (cada um inclui o anterior):
        viewer  -> leitura: dashboard KPI, drill-downs, relatorios
        dba     -> viewer + diagnostico ao vivo (LIVE: texto SQL, blocking,
                   tempdb, waits) e operacao do dia-a-dia
        admin   -> dba + governanca: utilizadores, roles, config do sistema
    """
    ADMIN = "admin"          # Full access — inclui gestao de users e config
    DBA = "dba"              # Operacional: LIVE + operacao, sem governanca
    VIEWER = "viewer"        # Read only


# Ordem de privilegio; usar em vez de comparar strings a olho.
ROLE_ORDER = (UserRole.VIEWER.value, UserRole.DBA.value, UserRole.ADMIN.value)
VALID_ROLES = frozenset(ROLE_ORDER)


def role_at_least(role: str, minimum: str) -> bool:
    """True se `role` tem pelo menos o privilegio de `minimum`.

    Role desconhecida (dados antigos, typo) e' tratada como a MAIS BAIXA —
    fail-closed em vez de dar acesso por engano.
    """
    try:
        return ROLE_ORDER.index(str(role or "").lower()) >= ROLE_ORDER.index(minimum)
    except ValueError:
        return False


# ==========================================
# Models
# ==========================================
class User(BaseModel):
    """User model"""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    disabled: bool = False


class UserInDB(User):
    """User model with hashed password"""
    hashed_password: str


class Token(BaseModel):
    """Access token"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data"""
    username: Optional[str] = None
    role: Optional[str] = None


# ==========================================
# User Database
# ==========================================
# Users are managed in WatcherDB_Users table via SQL Server.
# No in-memory fallback users — if DB is unavailable, login fails.
# This eliminates the "secret" password backdoor.
fake_users_db = {}


# ==========================================
# Password Hashing
# ==========================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)


# ==========================================
# User Management
# ==========================================
def get_user(username: str) -> Optional[UserInDB]:
    """Get user from database"""
    if username in fake_users_db:
        user_dict = fake_users_db[username]
        return UserInDB(**user_dict)
    return None


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    """Authenticate user with username and password"""
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ==========================================
# JWT Token Management
# ==========================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")

        if username is None:
            return None

        return TokenData(username=username, role=role)

    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        return None


# ==========================================
# Authentication Dependencies
# ==========================================
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)
    if token_data is None or token_data.username is None:
        raise credentials_exception

    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception

    return User(**user.dict(exclude={"hashed_password"}))


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# ==========================================
# Authorization (Role-Based Access Control)
# ==========================================
class RoleChecker:
    """Check if user has required role"""

    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_active_user)):
        if current_user.role not in self.allowed_roles:
            logger.warning(f"User {current_user.username} denied access. Required roles: {self.allowed_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {', '.join([r.value for r in self.allowed_roles])}"
            )
        return current_user


# ==========================================
# Permission Helpers
# ==========================================
def require_admin(current_user: User = Depends(get_current_active_user)):
    """Require admin role"""
    return RoleChecker([UserRole.ADMIN])(current_user)


def require_role(allowed_roles: List[UserRole]):
    """
    Generic role checker - creates a RoleChecker for specified roles.

    Usage:
        @router.get("/endpoint")
        async def endpoint(user: User = Depends(require_role([UserRole.ADMIN, UserRole.ANALYST]))):
            ...

    Args:
        allowed_roles: List of allowed UserRole values

    Returns:
        RoleChecker dependency
    """
    return RoleChecker(allowed_roles)


# ==========================================
# Utility Functions
# ==========================================
def create_user(username: str, password: str, email: str, full_name: str, role: UserRole) -> UserInDB:
    """Create new user (for admin use)"""
    hashed_password = get_password_hash(password)
    user = UserInDB(
        username=username,
        email=email,
        full_name=full_name,
        role=role,
        hashed_password=hashed_password,
        disabled=False
    )

    # In production, save to database
    fake_users_db[username] = user.dict()

    logger.info(f"User created: {username} with role {role.value}")
    return user


def change_password(username: str, new_password: str) -> bool:
    """Change user password"""
    user = get_user(username)
    if not user:
        return False

    hashed_password = get_password_hash(new_password)
    fake_users_db[username]["hashed_password"] = hashed_password

    logger.info(f"Password changed for user: {username}")
    return True


def disable_user(username: str) -> bool:
    """Disable user account"""
    if username in fake_users_db:
        fake_users_db[username]["disabled"] = True
        logger.info(f"User disabled: {username}")
        return True
    return False


def enable_user(username: str) -> bool:
    """Enable user account"""
    if username in fake_users_db:
        fake_users_db[username]["disabled"] = False
        logger.info(f"User enabled: {username}")
        return True
    return False
