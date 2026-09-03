"""
AuthService — WatcherDB V3.1 Authentication Service (Database-backed)
Fonte unica de verdade para JWT, validacao, CRUD de users.
Persiste users em WatcherDB_Intelligence.dbo.WatcherDB_Users.
"""
import os
import re
import logging
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from watcherdb.core.settings import settings

logger = logging.getLogger(__name__)

# JWT Config — usa services.secrets.get_secret para suportar valores encriptados
# (prefixo "encrypted:..." no .env). pydantic-settings nao desencripta sozinho.
from services.secrets import get_secret as _get_secret


# ============================================================================
# AD bind_password encryption (FIND-20260428-001 P1 security, ADR-019)
# ============================================================================
# DPAPI/Fernet helpers para proteger bind_passwords AD em
# WatcherDB_System_Config.ad_domains. Path A do parecer security-auditor
# (Fernet master key DPAPI-wrapped, single-machine V3.3 Standard).
#
# Idempotent — chamadas em valores ja encrypted/plaintext sao no-op.
# Backward compat — entries plaintext legacy sao retornadas as-is em decrypt;
# proxima save (admin re-entry via Control panel) re-encrypta automaticamente.

def _encrypt_bind_password(plaintext: str) -> str:
    """Encrypt bind_password via Fernet (services/secrets.py master key).
    Idempotent: valores ja com prefix 'encrypted:' OU vazios retornam as-is.
    Sob master key DPAPI-wrapped (Tier 2 preferred per services/secrets.py).
    """
    if not plaintext:
        return ""
    if plaintext.startswith("encrypted:"):
        return plaintext  # already encrypted — no-op
    try:
        from services.secrets import encrypt_value
        return encrypt_value(plaintext)
    except Exception as exc:
        logger.error(
            "[AD encrypt] Failed to encrypt bind_password: %s. Falling back to plaintext (LEGACY).",
            exc,
        )
        return plaintext  # fail-safe: backward compat


def _decrypt_bind_password(value: str) -> str:
    """Decrypt bind_password loaded from WatcherDB_System_Config.ad_domains.
    Idempotent: plaintext (sem prefix 'encrypted:') retornado as-is (backward compat).
    """
    if not value:
        return ""
    if not value.startswith("encrypted:"):
        return value  # legacy plaintext or empty — return as-is
    try:
        from cryptography.fernet import Fernet
        from services.secrets import _get_master_key
        token = value[len("encrypted:"):]
        return Fernet(_get_master_key()).decrypt(token.encode()).decode()
    except Exception as exc:
        logger.error(
            "[AD decrypt] Failed to decrypt bind_password (corrupted ciphertext or wrong key?): %s",
            exc,
        )
        return ""  # fail-safe: empty (auth will fail loudly via AD bind 401)

# Fallback cruzado: JWT_SECRET_KEY (padrao novo) -> WATCHERDB_JWT_SECRET (legacy services/web_service)
# Evita chave efemera quando qualquer das 2 envs esta definida.
JWT_SECRET_KEY = _get_secret("JWT_SECRET_KEY", "") or os.getenv("WATCHERDB_JWT_SECRET", "")
if not JWT_SECRET_KEY:
    import secrets as _secrets_stdlib
    JWT_SECRET_KEY = _secrets_stdlib.token_hex(32)
    logger.warning("[AUTH] JWT_SECRET_KEY/WATCHERDB_JWT_SECRET nao definidos — chave efemera gerada "
                   "(tokens nao sobrevivem restart). Defina um dos 2 no ambiente para producao.")
else:
    logger.info("[AUTH] JWT_SECRET_KEY carregada do ambiente (tokens sobrevivem restart).")
JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_expire_minutes
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


# ==========================================
# Database helpers (usar pool de conexoes existente)
# ==========================================
from api.connection_pool import get_intelligence_pool


def _execute_query(query: str, params: tuple = None) -> List[Dict[str, Any]]:
    """Execute SELECT query on WatcherDB_Intelligence."""
    pool = get_intelligence_pool()
    conn = None
    try:
        conn = pool.get_connection()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        if cursor.description is None:
            cursor.close()
            return []
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, col_name in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    row_dict[col_name] = val.isoformat()
                else:
                    row_dict[col_name] = val
            results.append(row_dict)
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"[AUTH] Query error: {e}")
        raise
    finally:
        if conn:
            pool.return_connection(conn)


def _execute_update(query: str, params: tuple = None) -> int:
    """Execute INSERT/UPDATE/DELETE on WatcherDB_Intelligence."""
    pool = get_intelligence_pool()
    conn = None
    try:
        conn = pool.get_connection()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        return rowcount
    except Exception as e:
        logger.error(f"[AUTH] Update error: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return 0
    finally:
        if conn:
            pool.return_connection(conn)


# ==========================================
# Password hashing (bcrypt com fallback SHA256)
# ==========================================
try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    raise RuntimeError("[AUTH] passlib[bcrypt] e obrigatorio. Instalar: pip install passlib[bcrypt]")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def validate_strong_password(password: str) -> Optional[str]:
    """Validate password meets strong password policy.
    Returns None if valid, error message string if invalid."""
    if len(password) < 8:
        return "Minimo 8 caracteres"
    if not re.search(r'[A-Z]', password):
        return "Falta letra maiuscula"
    if not re.search(r'[a-z]', password):
        return "Falta letra minuscula"
    if not re.search(r'[0-9]', password):
        return "Falta numero"
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",./<>?\\|`~]', password):
        return "Falta simbolo (!@#$%&*...)"
    return None


def verify_password(plain: str, hashed: str) -> bool:
    # Suporte legacy: hashes sha256 antigos sao verificados mas nao criados
    if hashed.startswith("sha256:"):
        logger.warning("[AUTH] Hash SHA-256 legacy detectado — o utilizador deve alterar a password")
        return hashed == "sha256:" + hashlib.sha256(plain.encode()).hexdigest()
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ==========================================
# JWT Token management
# ==========================================
try:
    from jose import jwt, JWTError
except ImportError:
    try:
        import jwt as _pyjwt

        class jwt:
            @staticmethod
            def encode(payload, key, algorithm):
                return _pyjwt.encode(payload, key, algorithm=algorithm)

            @staticmethod
            def decode(token, key, algorithms):
                return _pyjwt.decode(token, key, algorithms=algorithms)

        class JWTError(Exception):
            pass
    except ImportError:
        logger.error("[AUTH] Nenhuma biblioteca JWT disponivel (python-jose ou PyJWT)")
        raise


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


# ==========================================
# LDAP / Active Directory Authentication (generic, configurable)
# ==========================================
# Configuration via environment variables or config.yaml:
#   AD_ENABLED=true
#   AD_DOMAIN=TAPNET           (NetBIOS domain name)
#   AD_SERVER=tapnet.on        (LDAP server / domain FQDN)
#   AD_BASE_DN=DC=tapnet,DC=on (Base DN for user search)
#   AD_DEFAULT_ROLE=viewer     (Role for new AD users)
#   AD_USE_SSL=false           (Use LDAPS on port 636)

# Load AD config: env vars take priority, then config.yaml, then auto-detect
def _load_ad_config():
    """Load AD configuration from config.yaml and/or environment variables.

    2026-08-20: o antigo services/web_service/config.yaml foi removido (modulo
    morto com passwords em comentario). Aquele ficheiro so' tinha um TEMPLATE de
    active_directory (enabled:false, YOUR_DOMAIN) -- zero config real; a de
    producao vem sempre das env vars abaixo (AD_DOMAIN/AD_SERVER/...). Passa a
    ler o config.yaml canonico do bundle (config/config.yaml) se la' houver a
    seccao; caso contrario devolve {} e as env vars mandam.
    """
    cfg = {}
    try:
        import yaml
        from pathlib import Path
        # Candidatos, por ordem: config/ do repo/bundle, depois o antigo caminho
        # (que ja' nao existe mas fica documentado para nao surpreender).
        for rel in (Path(__file__).parent.parent / "config" / "config.yaml",):
            if rel.exists():
                with open(rel, 'r', encoding='utf-8') as f:
                    full_cfg = yaml.safe_load(f) or {}
                    cfg = full_cfg.get('auth', {}).get('active_directory', {}) or {}
                break
    except Exception:
        pass
    return cfg

_ad_cfg = _load_ad_config()
AD_ENABLED = os.getenv('AD_ENABLED', str(_ad_cfg.get('enabled', True))).lower() == 'true'
AD_DOMAIN = os.getenv('AD_DOMAIN', _ad_cfg.get('domain', ''))
AD_SERVER = os.getenv('AD_SERVER', _ad_cfg.get('server', ''))
AD_BASE_DN = os.getenv('AD_BASE_DN', _ad_cfg.get('base_dn', ''))
AD_DEFAULT_ROLE = os.getenv('AD_DEFAULT_ROLE', _ad_cfg.get('default_role', 'viewer'))
AD_USE_SSL = os.getenv('AD_USE_SSL', str(_ad_cfg.get('use_ssl', False))).lower() == 'true'
AD_BIND_USER = os.getenv('AD_BIND_USER', '')
AD_BIND_PASSWORD = os.getenv('AD_BIND_PASSWORD', '')
AD_DOMAINS = []  # List of domain configs: [{"domain": "...", "server": "...", "base_dn": "...", "default_role": "viewer", "bind_user": "", "bind_password": ""}, ...]


# ==========================================
# System Config Persistence (WatcherDB_System_Config table)
# ==========================================

def _ensure_config_table():
    """Create WatcherDB_System_Config table if it doesn't exist."""
    try:
        _execute_update("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'WatcherDB_System_Config')
            CREATE TABLE dbo.WatcherDB_System_Config (
                config_key   VARCHAR(100)   PRIMARY KEY,
                config_value NVARCHAR(500),
                updated_at   DATETIME       DEFAULT GETDATE()
            )
        """)
    except Exception as e:
        logger.debug(f"[CONFIG] Could not ensure config table: {e}")


def save_system_config(key: str, value: str):
    """Save a single config key/value to DB via MERGE (upsert)."""
    try:
        _execute_update(
            """MERGE dbo.WatcherDB_System_Config AS t
               USING (SELECT ? AS config_key, ? AS config_value) AS s
               ON t.config_key = s.config_key
               WHEN MATCHED THEN UPDATE SET config_value = s.config_value, updated_at = GETDATE()
               WHEN NOT MATCHED THEN INSERT (config_key, config_value) VALUES (s.config_key, s.config_value);""",
            (key, str(value)),
        )
    except Exception as e:
        logger.warning(f"[CONFIG] Failed to save {key}: {e}")


def load_system_config():
    """Load all config from WatcherDB_System_Config into global variables."""
    global AD_ENABLED, AD_DOMAIN, AD_SERVER, AD_BASE_DN, AD_DEFAULT_ROLE
    global ACCESS_TOKEN_EXPIRE_MINUTES, MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES
    global AD_DOMAINS, AD_BIND_USER, AD_BIND_PASSWORD
    try:
        _ensure_config_table()
        rows = _execute_query("SELECT config_key, config_value FROM dbo.WatcherDB_System_Config WITH (NOLOCK)")
        cfg_map = {r["config_key"]: r["config_value"] for r in rows}
        if not cfg_map:
            return  # No config in DB yet — keep defaults/env values

        if "ad_enabled" in cfg_map:
            AD_ENABLED = cfg_map["ad_enabled"].lower() == "true"
        if "ad_domain" in cfg_map:
            AD_DOMAIN = cfg_map["ad_domain"]
        if "ad_server" in cfg_map:
            AD_SERVER = cfg_map["ad_server"]
        if "ad_base_dn" in cfg_map:
            AD_BASE_DN = cfg_map["ad_base_dn"]
        if "ad_default_role" in cfg_map:
            AD_DEFAULT_ROLE = cfg_map["ad_default_role"]
        if "ad_bind_user" in cfg_map:
            AD_BIND_USER = cfg_map["ad_bind_user"]
        if "ad_bind_password" in cfg_map:
            AD_BIND_PASSWORD = cfg_map["ad_bind_password"]

        # Multi-domain AD support
        if "ad_domains" in cfg_map:
            import json
            try:
                AD_DOMAINS = json.loads(cfg_map["ad_domains"])
                # FIND-20260428-001 P1 security (ADR-019): decrypt bind_password apos json.loads.
                # _decrypt_bind_password e idempotent (legacy plaintext retornado as-is).
                # Apos primeira save por admin via Control panel, todos os entries ficam encrypted.
                for _d in AD_DOMAINS:
                    if _d.get("bind_password"):
                        _d["bind_password"] = _decrypt_bind_password(_d["bind_password"])
                # Sync legacy vars with first domain
                if AD_DOMAINS:
                    AD_DOMAIN = AD_DOMAINS[0].get("domain", AD_DOMAIN)
                    AD_SERVER = AD_DOMAINS[0].get("server", AD_SERVER)
                    AD_BASE_DN = AD_DOMAINS[0].get("base_dn", AD_BASE_DN)
                    AD_DEFAULT_ROLE = AD_DOMAINS[0].get("default_role", AD_DEFAULT_ROLE)
                    AD_BIND_USER = AD_DOMAINS[0].get("bind_user", "")
                    AD_BIND_PASSWORD = AD_DOMAINS[0].get("bind_password", "")
            except Exception:
                pass
        elif AD_DOMAIN:
            # Migration: single domain -> multi-domain list
            AD_DOMAINS = [{"domain": AD_DOMAIN, "server": AD_SERVER, "base_dn": AD_BASE_DN, "default_role": AD_DEFAULT_ROLE, "bind_user": AD_BIND_USER, "bind_password": AD_BIND_PASSWORD}]

        if "jwt_expire_minutes" in cfg_map:
            ACCESS_TOKEN_EXPIRE_MINUTES = int(cfg_map["jwt_expire_minutes"])
        if "max_failed_attempts" in cfg_map:
            MAX_FAILED_ATTEMPTS = int(cfg_map["max_failed_attempts"])
        if "lockout_minutes" in cfg_map:
            LOCKOUT_MINUTES = int(cfg_map["lockout_minutes"])

        logger.info(f"[CONFIG] Loaded {len(cfg_map)} settings from DB (AD_ENABLED={AD_ENABLED}, JWT={ACCESS_TOKEN_EXPIRE_MINUTES}min)")
    except Exception as e:
        logger.debug(f"[CONFIG] Could not load system config from DB: {e}")


def save_ad_config(enabled: bool, domain: str, server: str, base_dn: str, default_role: str,
                    bind_user: str = "", bind_password: str = ""):
    """Update AD globals + persist to DB. Delegates to save_ad_domains for backward compat."""
    # Wrap single domain into multi-domain format and delegate
    single_domain = {
        "domain": domain,
        "server": server,
        "base_dn": base_dn,
        "default_role": default_role,
        "bind_user": bind_user,
        "bind_password": bind_password,
    }
    save_ad_domains(enabled, [single_domain])


def save_ad_domains(enabled: bool, domains: list):
    """Save multi-domain AD config. Updates globals + persists as JSON."""
    global AD_ENABLED, AD_DOMAINS, AD_DOMAIN, AD_SERVER, AD_BASE_DN, AD_DEFAULT_ROLE, AD_BIND_USER, AD_BIND_PASSWORD
    AD_ENABLED = enabled
    # Clean domains — remove empty entries, sanitize passwords
    clean = []
    for d in domains:
        if not d.get("domain"):
            continue
        # FIND-20260428-001 P1 security (ADR-019 Path A): encrypt bind_password
        # antes de json.dumps + persistencia em WatcherDB_System_Config.ad_domains.
        # _encrypt_bind_password e idempotent (no-op se ja encrypted ou vazio).
        _raw_pwd = d.get("bind_password", "") if d.get("bind_password") != "********" else _get_existing_bind_password(d["domain"])
        clean.append({
            "domain": d["domain"],
            "server": d.get("server", ""),
            "base_dn": d.get("base_dn", ""),
            "default_role": d.get("default_role", "viewer"),
            "bind_user": d.get("bind_user", ""),
            "bind_password": _encrypt_bind_password(_raw_pwd),
        })
    AD_DOMAINS = clean
    # Backward compat: sync first domain to legacy vars
    if clean:
        AD_DOMAIN = clean[0]["domain"]
        AD_SERVER = clean[0]["server"]
        AD_BASE_DN = clean[0]["base_dn"]
        AD_DEFAULT_ROLE = clean[0]["default_role"]
        AD_BIND_USER = clean[0].get("bind_user", "")
        AD_BIND_PASSWORD = clean[0].get("bind_password", "")

    save_system_config("ad_enabled", str(enabled).lower())
    import json
    save_system_config("ad_domains", json.dumps(clean))
    logger.info(f"[CONFIG] AD multi-domain config saved: enabled={enabled}, {len(clean)} domains")


def _get_existing_bind_password(domain: str) -> str:
    """Get existing bind password for a domain (when UI sends '********')."""
    for d in AD_DOMAINS:
        if d.get("domain") == domain:
            return d.get("bind_password", "")
    return ""


def get_ad_domain_config(domain: str) -> dict:
    """Get config for a specific AD domain."""
    for d in AD_DOMAINS:
        if d.get("domain") == domain:
            return d
    # Fallback to legacy single-domain
    if domain == AD_DOMAIN:
        return {"domain": AD_DOMAIN, "server": AD_SERVER, "base_dn": AD_BASE_DN, "default_role": AD_DEFAULT_ROLE, "bind_user": AD_BIND_USER, "bind_password": AD_BIND_PASSWORD}
    return {}


def save_session_policy(jwt_minutes: int, max_failed: int, lockout: int):
    """Update session policy globals + persist to DB."""
    global ACCESS_TOKEN_EXPIRE_MINUTES, MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES
    ACCESS_TOKEN_EXPIRE_MINUTES = jwt_minutes
    MAX_FAILED_ATTEMPTS = max_failed
    LOCKOUT_MINUTES = lockout
    for key, val in [
        ("jwt_expire_minutes", str(jwt_minutes)),
        ("max_failed_attempts", str(max_failed)),
        ("lockout_minutes", str(lockout)),
    ]:
        save_system_config(key, val)
    logger.info(f"[CONFIG] Session policy saved: JWT={jwt_minutes}min, MaxFailed={max_failed}, Lockout={lockout}min")


# Auto-load config from DB on import (startup)
# HARDENING 2026-07-21: correr em background -- com o Intelligence server
# inacessivel, o pyodbc.connect (login timeout 60s) x retry_db_operation
# (3 tentativas + backoff) bloqueava este import ~3 minutos e o portal
# ficava "Running mas morto" (2 incidentes no mesmo dia, rede TST instavel).
# Ate' a config carregar, valem os defaults do modulo -- mesmo comportamento
# que o except:pass antigo produzia quando a DB estava em baixo.
import threading as _threading_boot


def _load_system_config_background():
    try:
        load_system_config()
        logger.info("[AUTH] System config carregada da Intelligence DB (background).")
    except Exception as e:
        logger.warning(
            f"[AUTH] System config indisponivel no arranque ({e}); a usar defaults. "
            "Recarrega no proximo uso quando a Intelligence DB voltar."
        )


_threading_boot.Thread(target=_load_system_config_background, daemon=True).start()


try:
    import ldap3
    from ldap3 import Server, Connection, ALL, NTLM, SUBTREE
    _has_ldap = True
except ImportError:
    _has_ldap = False
    if AD_ENABLED:
        logger.warning("[AUTH] ldap3 nao disponivel — AD authentication desactivado. pip install ldap3")


# Startup diagnostic — exposes effective AD config to logs so post-deploy verification
# is trivial. Without this, AD silently failing (URI prefix bug, missing ldap3, DC down)
# only surfaces as "Credenciais invalidas" to end users with no log evidence.
logger.info(
    f"[AUTH/STARTUP] AD effective config: enabled={AD_ENABLED}, "
    f"server={AD_SERVER!r}, domain={AD_DOMAIN!r}, base_dn={AD_BASE_DN!r}, "
    f"default_role={AD_DEFAULT_ROLE!r}, use_ssl={AD_USE_SSL}, "
    f"ldap3_installed={_has_ldap}, multi_domain_count={len(AD_DOMAINS)}"
)


def _auto_detect_ad_config():
    """Auto-detect AD config from domain if not explicitly set."""
    global AD_DOMAIN, AD_SERVER, AD_BASE_DN
    if AD_DOMAIN and not AD_SERVER:
        AD_SERVER = AD_DOMAIN.lower() + '.on'  # Common pattern
    if AD_SERVER and not AD_BASE_DN:
        # Convert FQDN to Base DN: tapnet.on -> DC=tapnet,DC=on
        parts = AD_SERVER.split('.')
        AD_BASE_DN = ','.join(f'DC={p}' for p in parts)
    if not AD_DOMAIN:
        # Try to detect from environment
        userdomain = os.environ.get('USERDOMAIN', '')
        if userdomain and userdomain.upper() not in ('', 'WORKGROUP'):
            AD_DOMAIN = userdomain.upper()
            logger.info(f"[AUTH] AD domain auto-detected: {AD_DOMAIN}")


_auto_detect_ad_config()


def ad_lookup_user(username: str, domain: str = None) -> dict:
    """
    Lookup a user in Active Directory via LDAP.
    Auth priority: 1) Service Account  2) Kerberos/GSSAPI  3) Anonymous
    Returns user info if found, debug steps for diagnostics.
    If domain is specified, uses that domain's config from AD_DOMAINS.
    """
    if not _has_ldap:
        return {"success": False, "error": "ldap3 nao instalado"}
    if not AD_ENABLED or (not AD_DOMAIN and not domain):
        return {"success": False, "error": "Active Directory nao configurado"}

    debug = []
    try:
        # Resolve server/base_dn/bind credentials based on domain parameter
        if domain:
            dcfg = get_ad_domain_config(domain)
            if dcfg:
                server_url = dcfg.get("server") or f"ldap://{domain}"
                base_dn = dcfg.get("base_dn") or ",".join(f"DC={p}" for p in domain.split("."))
                bind_user = dcfg.get("bind_user", "")
                bind_password = dcfg.get("bind_password", "")
            else:
                server_url = f"ldap://{domain}"
                base_dn = ",".join(f"DC={p}" for p in domain.split("."))
                bind_user = ""
                bind_password = ""
        else:
            server_url = AD_SERVER or f"ldap://{AD_DOMAIN}"
            base_dn = AD_BASE_DN or ",".join(f"DC={p}" for p in AD_DOMAIN.split("."))
            bind_user = AD_BIND_USER
            bind_password = AD_BIND_PASSWORD

        debug.append(f"1. Server: {server_url}")
        debug.append(f"2. Base DN: {base_dn}")

        server = ldap3.Server(server_url, get_info=ldap3.ALL, connect_timeout=5)
        debug.append("4. Server object criado OK")

        # Bind priority: service account -> Kerberos -> anonymous
        conn = None
        bind_method = "anonymous"

        if bind_user and bind_password:
            debug.append(f"3. Bind User: {bind_user}")
            try:
                conn = ldap3.Connection(server, user=bind_user, password=bind_password,
                                        auto_bind=True, read_only=True, receive_timeout=5)
                bind_method = "service_account"
                debug.append(f"5. Bind Service Account OK (bound={conn.bound})")
            except Exception as e:
                debug.append(f"5. Bind Service Account FAILED: {e}")
                conn = None

        if conn is None:
            debug.append("3. Bind User: (kerberos)")
            try:
                conn = ldap3.Connection(server, authentication=ldap3.SASL, sasl_mechanism='GSSAPI',
                                        auto_bind=True, read_only=True, receive_timeout=5)
                bind_method = "kerberos"
                debug.append(f"5. Bind Kerberos/GSSAPI OK (bound={conn.bound})")
            except Exception as e:
                debug.append(f"5. Bind Kerberos FAILED: {e}")
                conn = None

        if conn is None:
            debug.append("3. Bind User: (anonymous fallback)")
            try:
                conn = ldap3.Connection(server, auto_bind=True, read_only=True, receive_timeout=5)
                bind_method = "anonymous"
                debug.append(f"5. Bind Anonymous OK (bound={conn.bound})")
            except Exception as e:
                debug.append(f"5. Bind Anonymous FAILED: {e}")
                return {"success": False, "error": f"Nao foi possivel ligar ao AD: {e}", "debug": debug}

        # Flexible search: exact + wildcard on sAMAccountName, cn, displayName
        escaped = ldap3.utils.conv.escape_filter_chars(username)
        search_filter = (
            f"(&(objectClass=user)(|"
            f"(sAMAccountName={escaped})"
            f"(sAMAccountName=*{escaped}*)"
            f"(cn=*{escaped}*)"
            f"(displayName=*{escaped}*)"
            f"))"
        )
        debug.append(f"6. Filter: {search_filter}")

        conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['displayName', 'givenName', 'sn', 'sAMAccountName', 'mail',
                        'userPrincipalName', 'proxyAddresses', 'title', 'department'],
            size_limit=10,
        )
        debug.append(f"7. Search result: {conn.result.get('result', 'N/A')}, entries: {len(conn.entries)}")

        # Safe attribute extraction — handles empty lists [] without IndexError
        def _attr(e, key):
            try:
                val = getattr(e, key, None)
                if val is None:
                    return ""
                s = str(val)
                return s if s and s != "[]" else ""
            except Exception:
                return ""

        lookup_domain = domain or AD_DOMAIN

        if conn.entries:
            # Extract all results
            users = []
            for entry in conn.entries:
                sam = _attr(entry, 'sAMAccountName') or username
                display_name = _attr(entry, 'displayName')
                given_name = _attr(entry, 'givenName')
                surname = _attr(entry, 'sn')
                mail = _attr(entry, 'mail')
                upn = _attr(entry, 'userPrincipalName')
                title = _attr(entry, 'title')
                department = _attr(entry, 'department')
                full_name = display_name or f"{given_name} {surname}".strip()

                # Email priority: mail → proxyAddresses (primary SMTP:) → UPN → fallback
                email = mail
                if not email:
                    try:
                        proxies = getattr(entry, 'proxyAddresses', [])
                        if proxies:
                            for p in proxies:
                                ps = str(p)
                                if ps.startswith("SMTP:"):  # Primary (uppercase SMTP)
                                    email = ps[5:]
                                    break
                            if not email:
                                for p in proxies:
                                    ps = str(p)
                                    if ps.lower().startswith("smtp:"):
                                        email = ps[5:]
                                        break
                    except Exception:
                        pass
                if not email and upn and "@" in upn:
                    email = upn
                if not email:
                    email = f"{sam}@{lookup_domain}"
                users.append({
                    "username": sam,
                    "full_name": full_name,
                    "email": email,
                    "title": title,
                    "department": department,
                    "dn": str(entry.entry_dn),
                })

            debug.append(f"8. Found {len(users)} user(s)")
            if len(users) > 1:
                for i, u in enumerate(users):
                    debug.append(f"   {i+1}. {u['username']} — {u['full_name']} ({u['dn'][:60]}...)")

            conn.unbind()

            if len(users) == 1:
                return {
                    "success": True,
                    "found": True,
                    "bind_method": bind_method,
                    "user": users[0],
                    "debug": debug,
                }
            else:
                return {
                    "success": True,
                    "found": True,
                    "multiple": True,
                    "count": len(users),
                    "bind_method": bind_method,
                    "users": users,
                    "debug": debug,
                }

        conn.unbind()
        return {
            "success": True,
            "found": False,
            "bind_method": bind_method,
            "message": f"Utilizador '{username}' nao encontrado no AD ({lookup_domain})",
            "debug": debug,
        }

    except Exception as e:
        logger.error(f"[AUTH] AD lookup error for {username}: {e}")
        debug.append(f"ERROR: {e}")
        return {"success": False, "error": f"Erro LDAP: {str(e)}", "debug": debug}


def ad_discover_dcs(domain: str) -> dict:
    """Discover Domain Controllers via DNS SRV records."""
    import subprocess
    try:
        result = subprocess.run(
            ["nslookup", "-type=SRV", f"_ldap._tcp.{domain}"],
            capture_output=True, text=True, timeout=10,
        )
        dcs = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # Parse "svr hostname = dchqprd01.tapnet.tap.pt"
            if "svr hostname" in line.lower():
                parts = line.split("=")
                if len(parts) >= 2:
                    hostname = parts[-1].strip().rstrip(".")
                    if hostname:
                        dcs.append(hostname)

        if not dcs:
            # Alternative parsing for different nslookup output formats
            for line in result.stdout.splitlines():
                if domain in line and "." in line:
                    # Try to extract FQDN from the line
                    words = line.split()
                    for word in words:
                        if domain in word and len(word) > len(domain) + 2:
                            dcs.append(word.rstrip("."))

        return {
            "success": True,
            "domain": domain,
            "domain_controllers": dcs,
            "recommended_server": f"ldap://{dcs[0]}" if dcs else f"ldap://{domain}",
            "raw_output": result.stdout[:500] if not dcs else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "domain": domain}


def _ad_socket_probe(timeout: float = 2.0) -> bool:
    """Quick TCP probe to AD_SERVER:389/636 to distinguish "DC unreachable"
    from "credentials invalid" in authentication error messages.

    Returns True if the DC accepts a TCP connection within `timeout` seconds,
    False otherwise. Does NOT do an LDAP bind — just a socket open.
    """
    if not AD_SERVER:
        return False
    try:
        import socket
        from urllib.parse import urlparse
        # AD_SERVER might be 'ldap://host', 'ldaps://host:636', or just 'host'
        url = AD_SERVER if '://' in AD_SERVER else f'ldap://{AD_SERVER}'
        parsed = urlparse(url)
        host = parsed.hostname or AD_SERVER
        port = parsed.port or (636 if parsed.scheme == 'ldaps' else 389)
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def _try_single_domain_bind(username: str, password: str, dom_cfg: dict,
                             connect_timeout: int = 10) -> Optional[dict]:
    """
    Tenta bind LDAP num único domínio. Retorna user_info se sucesso, None se falha.

    dom_cfg dict keys: domain, server, base_dn, [use_ssl], [bind_user], [bind_password].
    Usado por _authenticate_ldap para suportar multi-domain (itera AD_DOMAINS).
    """
    raw_server = (dom_cfg.get("server") or "").strip()
    domain = dom_cfg.get("domain") or ""
    base_dn = dom_cfg.get("base_dn") or ""
    cfg_use_ssl = dom_cfg.get("use_ssl", AD_USE_SSL)

    if not raw_server:
        return None

    try:
        # Sanitize URI prefix — Control panel admins frequently configure server as
        # "ldap://host" or "ldaps://host"; ldap3.Server expects bare hostname when
        # port is given explicitly. Strip scheme + infer use_ssl from prefix.
        server_host = raw_server
        use_ssl = bool(cfg_use_ssl)
        if server_host.lower().startswith("ldaps://"):
            server_host = server_host[len("ldaps://"):]
            use_ssl = True
        elif server_host.lower().startswith("ldap://"):
            server_host = server_host[len("ldap://"):]
        server_host = server_host.rstrip("/")
        if ":" in server_host and not server_host.startswith("["):  # not IPv6
            host_part, _, port_part = server_host.rpartition(":")
            if port_part.isdigit():
                server_host = host_part
        port = 636 if use_ssl else 389
        server = Server(server_host, port=port, use_ssl=use_ssl, get_info=ALL,
                        connect_timeout=connect_timeout)

        # SIMPLE bind com UPN, fallback NTLM com DOMAIN\user
        # [FIND-20260428-009 sub-task 2026-05-05] NTLM fallback gated por env var.
        # Default = FALSE para mitigar CVE-2025-54918 (Windows NTLM LDAP relay,
        # CVSS 8.8 HIGH). Activar via env WATCHERDB_AD_ALLOW_NTLM_FALLBACK=true
        # so' se: (a) UPN/SIMPLE bind insuficiente em deploy cliente, AND
        # (b) DC tem patch Sept 2025 cumulative update applied (verificar com
        # cliente sysadmin antes de activar).
        # Em deploy actual TAP, kerberos integrated bind via Service Account
        # cobre auth - este fallback fica dormant.
        import os as _os_for_ntlm
        _allow_ntlm = _os_for_ntlm.getenv("WATCHERDB_AD_ALLOW_NTLM_FALLBACK", "false").lower() in ("true", "1", "yes")

        upn = f"{username}@{domain}" if domain else username
        try:
            conn = Connection(server, user=upn, password=password,
                              auto_bind=True, receive_timeout=15)
        except Exception:
            if not _allow_ntlm:
                logger.debug(
                    f"[AUTH] SIMPLE bind failed for {username}@{domain or raw_server}; "
                    f"NTLM fallback disabled (WATCHERDB_AD_ALLOW_NTLM_FALLBACK=false, "
                    f"CVE-2025-54918 mitigation). Set env var to 'true' para legacy behaviour."
                )
                return None
            try:
                domain_user = f"{domain}\\{username}" if domain else username
                conn = Connection(server, user=domain_user, password=password,
                                  authentication=NTLM, auto_bind=True, receive_timeout=15)
                logger.warning(
                    f"[AUTH] NTLM fallback used for {username} on {domain or raw_server}. "
                    f"Verify DC has Sept 2025 cumulative update (CVE-2025-54918)."
                )
            except Exception:
                return None

        user_info = {
            "username": username,
            "auth_method": "ldap",
            "full_name": username,
            "email": None,
            "department": None,
            "title": None,
            "ad_domain": domain,  # tracks which domain this user came from
        }

        search_filter = f"(&(objectClass=user)(sAMAccountName={ldap3.utils.conv.escape_filter_chars(username)}))"
        search_attrs = ['displayName', 'mail', 'department', 'title', 'memberOf',
                        'sAMAccountName', 'givenName', 'sn', 'thumbnailPhoto']

        if base_dn:
            conn.search(base_dn, search_filter, search_scope=SUBTREE, attributes=search_attrs)
            if conn.entries:
                entry = conn.entries[0]
                user_info["full_name"] = str(entry.displayName) if hasattr(entry, 'displayName') and entry.displayName else username
                user_info["email"] = str(entry.mail) if hasattr(entry, 'mail') and entry.mail else None
                user_info["department"] = str(entry.department) if hasattr(entry, 'department') and entry.department else None
                user_info["title"] = str(entry.title) if hasattr(entry, 'title') and entry.title else None
                if hasattr(entry, 'memberOf') and entry.memberOf:
                    user_info["ad_groups"] = [str(g) for g in entry.memberOf]

        conn.unbind()
        logger.info(f"[AUTH] LDAP auth OK for {username} on domain {domain or '(default)'} ({user_info.get('full_name')})")
        return user_info

    except ldap3.core.exceptions.LDAPBindError:
        logger.debug(f"[AUTH] LDAP bind failed for {username} on {domain or raw_server} (invalid creds)")
        return None
    except ldap3.core.exceptions.LDAPSocketOpenError as e:
        logger.warning(f"[AUTH] LDAP server unreachable ({raw_server}): {e}")
        return None
    except Exception as e:
        logger.warning(f"[AUTH] LDAP error for {username} on {domain or raw_server}: {e}")
        return None


def _authenticate_ldap(username: str, password: str) -> Optional[dict]:
    """
    Authenticate against Active Directory — supports multi-domain.

    Itera AD_DOMAINS (configurado via Control panel → guardado em
    WatcherDB_System_Config.ad_domains JSON). Primeiro hit ganha.

    Se username trouxer domínio explícito (user@dom.fqdn ou DOM\\user) filtra
    a lista para esse domínio antes de iterar — evita tentativas desnecessárias
    em DCs irrelevantes (e evita gastar attempts de account lockout em domínios
    errados). Username sem domínio explícito tenta todos em ordem.

    Fallback: se AD_DOMAINS estiver vazio, usa singulares AD_SERVER/AD_DOMAIN
    /AD_BASE_DN (config legacy single-domain).
    """
    if not _has_ldap or not AD_ENABLED:
        return None

    # Build list of domains to try
    if AD_DOMAINS:
        domains_to_try = list(AD_DOMAINS)
    elif AD_SERVER:
        domains_to_try = [{
            "domain": AD_DOMAIN,
            "server": AD_SERVER,
            "base_dn": AD_BASE_DN,
            "default_role": AD_DEFAULT_ROLE,
        }]
    else:
        return None

    # Extract explicit domain hint from username (if any) and filter
    explicit_domain = None
    clean_username = username
    if "@" in username:
        clean_username, _, dom_part = username.partition("@")
        explicit_domain = dom_part.lower().strip()
    elif "\\" in username:
        netbios, _, clean_username = username.partition("\\")
        explicit_domain = netbios.lower().strip()  # NetBIOS short (ex: TAPNET)

    if explicit_domain and len(domains_to_try) > 1:
        filtered = []
        for d in domains_to_try:
            dom_full = (d.get("domain") or "").lower()
            # Match FQDN (tapnet.tap.pt) ou NetBIOS short (tapnet → primeiro label)
            if dom_full == explicit_domain or dom_full.split(".")[0] == explicit_domain:
                filtered.append(d)
        if filtered:
            domains_to_try = filtered
            logger.debug(
                f"[AUTH] Multi-domain: filtered to {len(filtered)} domain(s) "
                f"by explicit '{explicit_domain}' in username"
            )

    # Reduce per-domain timeout when iterating multiple — total wait stays bounded
    per_domain_timeout = 5 if len(domains_to_try) > 1 else 10

    for dom_cfg in domains_to_try:
        result = _try_single_domain_bind(clean_username, password, dom_cfg,
                                         connect_timeout=per_domain_timeout)
        if result:
            return result  # primeiro hit ganha

    return None


def _auto_provision_ad_user(ad_info: dict) -> dict:
    """
    Auto-provision or update user in local DB from AD info.
    Creates the user if not exists, updates profile if exists.
    """
    username = ad_info["username"]
    full_name = ad_info.get("full_name", username)
    email = ad_info.get("email")
    role = AD_DEFAULT_ROLE

    # Check if user already exists in DB
    try:
        rows = _execute_query(
            "SELECT username, role FROM dbo.WatcherDB_Users WITH (NOLOCK) WHERE username = ?",
            (username,)
        )
        if rows:
            # User exists — update profile from AD, keep existing role
            role = rows[0].get("role", AD_DEFAULT_ROLE)
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET full_name = ?, email = ?, last_login = GETDATE() WHERE username = ?",
                (full_name, email, username)
            )
        else:
            # New user — auto-provision with default role
            placeholder_hash = "ad_auth:" + hashlib.sha256(username.encode()).hexdigest()
            _execute_update(
                "INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, email, full_name) VALUES (?, ?, ?, ?, ?)",
                (username, placeholder_hash, role, email, full_name)
            )
            logger.info(f"[AUTH] Auto-provisioned AD user: {username} ({full_name}) as {role}")
    except Exception as e:
        logger.warning(f"[AUTH] Failed to provision AD user {username}: {e}")

    return {
        "username": username,
        "role": role,
        "full_name": full_name,
        "email": email,
        "department": ad_info.get("department"),
        "title": ad_info.get("title"),
        "auth_method": "ldap"
    }


# ==========================================
# Default fallback users REMOVIDO (security fix)
# Users devem ser criados via SQL script: database/CREATE_USER_AUTH_PREFS.sql
# ==========================================


# ==========================================
# AuthService Singleton
# ==========================================
class AuthService:
    """Servico de autenticacao hibrido: AD (LDAP) + DB local + defaults."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_user_from_db(self, username: str) -> Optional[dict]:
        """Busca user na tabela dbo.WatcherDB_Users (BD WatcherDB_Intelligence).

        Inclui local_password_hash para suportar dual auth (AD + local fallback).
        Se a coluna nao existir (BD nao migrada com 12_ADD_LOCAL_PASSWORD_HASH.sql),
        cai para o SELECT legacy sem essa coluna.
        """
        try:
            try:
                # Schema novo (com dual auth)
                rows = _execute_query(
                    "SELECT id, username, password_hash, local_password_hash, role, email, full_name, disabled, "
                    "failed_attempts, locked_until, last_login FROM dbo.WatcherDB_Users WHERE username = ?",
                    (username,)
                )
            except Exception as e:
                # Schema legacy: a coluna local_password_hash ainda nao existe
                # (script 12_ADD_LOCAL_PASSWORD_HASH.sql nao foi corrido)
                if 'local_password_hash' in str(e) or 'Invalid column' in str(e):
                    logger.warning(
                        f"[AUTH] local_password_hash column missing — caindo para schema legacy. "
                        f"Run database/12_ADD_LOCAL_PASSWORD_HASH.sql para activar dual auth."
                    )
                    rows = _execute_query(
                        "SELECT id, username, password_hash, role, email, full_name, disabled, "
                        "failed_attempts, locked_until, last_login FROM dbo.WatcherDB_Users WHERE username = ?",
                        (username,)
                    )
                else:
                    raise
            if rows:
                return rows[0]
        except Exception as e:
            logger.error(f"[AUTH] Erro ao buscar user {username} na BD: {e}")
            raise
        return None

    async def authenticate(self, username: str, password: str, ip: str = None) -> dict:
        """
        Hybrid authentication com AD prioritario e fallback local:

            1. Tentar Active Directory (LDAP) — preferencial, AD ganha sempre
               quando o DC esta alcancavel.
            2. Se AD falha (qualquer motivo) → cair para credenciais locais:
                  a) local_password_hash (campo dedicado, dual auth) — preferido
                     para users AD-provisionados que tenham fallback definido
                  b) password_hash legacy (bcrypt sem prefixo) — para os users
                     locais antigos (admin, salomao, ricardo, etc)
                  c) password_hash com prefixo 'ad_auth:' E sem fallback local
                     → "AD indisponivel" (mensagem distinta de credenciais
                     invalidas, para nao confundir o user)

        Accepts both username (ue_e-snetto) and email (ue_e-snetto@tapnet.tap.pt).
        """
        # If user provided email, extract username part
        login_name = username
        if "@" in username:
            login_name = username.split("@")[0]
            logger.debug(f"[AUTH] Email login detected: {username} → using {login_name}")

        # === STEP 1: Try AD/LDAP (preferencial) ===
        ad_attempted = False
        ad_reachable = None  # None = nao testado, True = chegou ao DC, False = network down
        if AD_ENABLED and _has_ldap and AD_SERVER:
            ad_attempted = True
            ad_info = _authenticate_ldap(login_name, password)
            if ad_info:
                # AD success — auto-provision/update in local DB
                user_profile = _auto_provision_ad_user(ad_info)
                token = create_access_token({"sub": login_name, "role": user_profile["role"]})
                self._log_auth(login_name, "LOGIN_SUCCESS", ip, "via AD/LDAP")
                return {
                    "success": True,
                    "access_token": token,
                    "token_type": "bearer",
                    "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "user": user_profile
                }
            # AD falhou — saber se foi por network ou por credenciais invalidas
            # Distinguir um do outro fazendo um socket probe rapido ao DC.
            ad_reachable = _ad_socket_probe()
            if ad_reachable:
                logger.debug(f"[AUTH] AD reachable but bind falhou para {login_name} (credenciais invalidas?)")
            else:
                logger.warning(f"[AUTH] AD inalcancavel ({AD_SERVER}) — caindo para local fallback para {login_name}")

        # === STEP 2: Try local DB (fallback) ===
        try:
            user = self._get_user_from_db(login_name)
        except Exception as e:
            logger.error(f"[AUTH] BD indisponivel durante login de {login_name}: {e}")
            return {"success": False, "error": "Servico temporariamente indisponivel"}
        if not user:
            # Constant-time: fazer hash dummy para evitar user enumeration via timing
            verify_password(password, hash_password("dummy-constant-time"))
            self._log_auth("UNKNOWN", "LOGIN_FAILED", ip, "Credenciais invalidas")
            return {"success": False, "error": "Credenciais invalidas"}

        # Check lockout
        if user.get("locked_until"):
            locked = user["locked_until"]
            if isinstance(locked, str):
                locked = datetime.fromisoformat(locked)
            if isinstance(locked, datetime) and locked > datetime.now():
                return {"success": False, "error": f"Conta bloqueada ate {locked.strftime('%H:%M')}"}

        # Check disabled
        if user.get("disabled"):
            return {"success": False, "error": "Conta desactivada"}

        # === Decisao do hash a verificar (dual auth) ===
        pw_hash = user.get("password_hash", "") or ""
        local_hash = user.get("local_password_hash", "") or ""

        # Caminho 2a: user AD-provisionado COM fallback local definido
        if pw_hash.startswith("ad_auth:") and local_hash:
            if verify_password(password, local_hash):
                token = create_access_token({"sub": login_name, "role": user.get("role", "viewer")})
                self._reset_failed_attempts(login_name)
                self._update_last_login(login_name)
                self._log_auth(login_name, "LOGIN_SUCCESS", ip, "via local fallback (AD nao disponivel)")
                return {
                    "success": True,
                    "access_token": token,
                    "token_type": "bearer",
                    "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "user": {
                        "username": login_name,
                        "role": user.get("role", "viewer"),
                        "full_name": user.get("full_name", login_name),
                        "email": user.get("email"),
                        "auth_method": "local_fallback"
                    }
                }
            # local fallback existe mas password errada
            attempts_now = self._increment_failed_attempts(login_name)
            self._log_auth(login_name, "LOGIN_FAILED", ip, f"local fallback password incorrecta [{attempts_now}/{MAX_FAILED_ATTEMPTS}]")
            return {"success": False, "error": self._failed_attempt_message(attempts_now)}

        # Caminho 2b: user legacy local (password_hash NAO comeca por ad_auth:)
        if pw_hash and not pw_hash.startswith("ad_auth:"):
            if verify_password(password, pw_hash):
                token = create_access_token({"sub": login_name, "role": user.get("role", "viewer")})
                self._reset_failed_attempts(login_name)
                self._update_last_login(login_name)
                self._log_auth(login_name, "LOGIN_SUCCESS", ip, "via local DB")
                return {
                    "success": True,
                    "access_token": token,
                    "token_type": "bearer",
                    "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "user": {
                        "username": login_name,
                        "role": user.get("role", "viewer"),
                        "full_name": user.get("full_name", login_name),
                        "email": user.get("email"),
                        "auth_method": "local"
                    }
                }
            attempts_now = self._increment_failed_attempts(login_name)
            self._log_auth(login_name, "LOGIN_FAILED", ip, f"Password incorrecta (local) [{attempts_now}/{MAX_FAILED_ATTEMPTS}]")
            return {"success": False, "error": self._failed_attempt_message(attempts_now)}

        # Caminho 2c: user AD-only sem fallback local — mensagem distinta
        # consoante o motivo da falha do AD
        if pw_hash.startswith("ad_auth:"):
            if ad_attempted and ad_reachable is False:
                self._log_auth(login_name, "LOGIN_FAILED", ip, "AD inalcancavel e user sem fallback local")
                return {
                    "success": False,
                    "error": "Servidor AD inalcancavel — verifica VPN/rede ou pede ao admin para definir password local de fallback"
                }
            # AD foi tentado e o DC estava OK → credenciais invalidas
            # OU AD nao foi tentado de todo (AD_ENABLED=false) → user AD sem caminho local
            self._log_auth(login_name, "LOGIN_FAILED", ip, "AD user, credenciais invalidas ou sem fallback")
            return {"success": False, "error": "Credenciais Windows/AD invalidas"}

        # Caminho final: nao ha hash nenhum (estado invalido)
        self._log_auth(login_name, "LOGIN_FAILED", ip, "User sem password_hash nem local_password_hash")
        return {"success": False, "error": "Conta sem credenciais configuradas — contacte o admin"}

    async def get_current_user(self, token: str) -> Optional[dict]:
        """Valida token e retorna info do user."""
        payload = decode_token(token)
        if not payload:
            return None
        username = payload.get("sub")
        if not username:
            return None
        user = self._get_user_from_db(username)
        if not user or user.get("disabled"):
            return None
        return {
            "username": username,
            "role": user.get("role", payload.get("role", "viewer")),
            "full_name": user.get("full_name", username),
            "email": user.get("email")
        }

    async def create_user(self, username: str, password: str, role: str = "viewer",
                          email: str = None, full_name: str = None) -> dict:
        """Cria novo user."""
        existing = self._get_user_from_db(username)
        if existing and existing.get("username"):
            return {"success": False, "error": "Username ja existe"}
        hashed = hash_password(password)
        try:
            rowcount = _execute_update(
                "INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, email, full_name) VALUES (?, ?, ?, ?, ?)",
                (username, hashed, role, email, full_name)
            )
            # _execute_update swallows SQL exceptions and returns 0 on failure; verify rowcount
            # to surface silent INSERT failures (permissoes BD, constraint, connection drop).
            if rowcount == 0:
                logger.error(
                    f"[AUTH] create_user INSERT returned rowcount=0 for {username} — "
                    f"verificar logs do servico e permissoes na tabela WatcherDB_Users"
                )
                return {"success": False, "error": "Falha ao inserir user na BD — verificar logs do servico e permissoes"}
            try:
                self._log_auth(username, "USER_CREATED", None, f"User {username} created with role {role}")
            except Exception as audit_err:
                logger.warning(f"[AUTH] create_user audit log failed for {username}: {audit_err}")
            return {"success": True, "username": username, "role": role}
        except Exception as e:
            logger.error(f"[AUTH] create_user exception for {username}: {e}")
            return {"success": False, "error": str(e)}

    async def change_password(self, username: str, new_password: str) -> dict:
        """Altera password do user.

        Nota: a verificacao da password actual e feita no router (auth_compat.py)
        antes de chamar este metodo. Este metodo apenas executa a alteracao.
        """
        hashed = hash_password(new_password)
        try:
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE username = ?",
                (hashed, username)
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_users(self) -> list:
        """Lista todos os users (sem password_hash)."""
        rows = _execute_query(
            "SELECT username, role, email, full_name, disabled, last_login, created_at, "
            "failed_attempts, locked_until, "
            "CASE WHEN locked_until IS NOT NULL AND locked_until > GETDATE() THEN 1 ELSE 0 END AS is_locked "
            "FROM dbo.WatcherDB_Users WITH (NOLOCK) ORDER BY username"
        )
        return rows

    async def toggle_user(self, username: str, disabled: bool) -> dict:
        """Activa/desactiva user."""
        try:
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET disabled = ? WHERE username = ?",
                (1 if disabled else 0, username)
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def unlock_user(self, username: str) -> dict:
        """Desbloqueia conta: reset failed_attempts + locked_until."""
        try:
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
                (username,)
            )
            self._log_auth(username, "USER_UNLOCKED", None, "Desbloqueado manualmente por admin")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_user(self, username: str) -> dict:
        """Remove user permanently from WatcherDB_Users."""
        try:
            # Also delete preferences
            _execute_update(
                "DELETE FROM dbo.WatcherDB_User_Preferences WHERE username = ?",
                (username,)
            )
            # Delete user
            deleted = _execute_update(
                "DELETE FROM dbo.WatcherDB_Users WHERE username = ?",
                (username,)
            )
            if deleted:
                self._log_auth(username, "USER_DELETED", None, f"User {username} permanently deleted")
                return {"success": True}
            return {"success": False, "error": "User nao encontrado"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_user(self, username: str, full_name: str = None, email: str = None, role: str = None) -> dict:
        """Update user profile fields (admin only)."""
        try:
            fields = []
            params = []
            if full_name is not None:
                fields.append("full_name = ?")
                params.append(full_name)
            if email is not None:
                fields.append("email = ?")
                params.append(email)
            if role is not None:
                if role not in ("admin", "dba", "viewer"):
                    return {"success": False, "error": "Role invalido"}
                fields.append("role = ?")
                params.append(role)
            if not fields:
                return {"success": False, "error": "Nenhum campo para actualizar"}
            params.append(username)
            _execute_update(
                f"UPDATE dbo.WatcherDB_Users SET {', '.join(fields)} WHERE username = ?",
                tuple(params)
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _increment_failed_attempts(self, username: str) -> int:
        """Incrementa failed_attempts (bloqueia na MAX-esima) e devolve o novo total."""
        try:
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET failed_attempts = failed_attempts + 1, "
                "locked_until = CASE WHEN failed_attempts >= ? "
                "THEN DATEADD(MINUTE, ?, GETDATE()) ELSE locked_until END "
                "WHERE username = ?",
                (MAX_FAILED_ATTEMPTS - 1, LOCKOUT_MINUTES, username)
            )
            rows = _execute_query(
                "SELECT failed_attempts FROM dbo.WatcherDB_Users WITH (NOLOCK) WHERE username = ?",
                (username,)
            )
            return rows[0]["failed_attempts"] if rows else 0
        except Exception as e:
            logger.error(f"[AUTH] Erro ao incrementar failed_attempts para {username}: {e}")
            return 0

    def _failed_attempt_message(self, attempts_now: int) -> str:
        """Mensagem informativa de tentativas restantes antes do lockout."""
        remaining = max(0, MAX_FAILED_ATTEMPTS - attempts_now)
        if remaining <= 0:
            return (f"Password incorrecta. Conta BLOQUEADA por {LOCKOUT_MINUTES} min "
                    f"apos {MAX_FAILED_ATTEMPTS} tentativas falhadas.")
        return (f"Password incorrecta. Tentativa {attempts_now}/{MAX_FAILED_ATTEMPTS} — "
                f"faltam {remaining} antes de bloquear {LOCKOUT_MINUTES} min.")

    def _reset_failed_attempts(self, username: str):
        try:
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
                (username,)
            )
        except Exception:
            pass

    def _update_last_login(self, username: str):
        try:
            _execute_update(
                "UPDATE dbo.WatcherDB_Users SET last_login = GETDATE() WHERE username = ?",
                (username,)
            )
        except Exception:
            pass

    def _log_auth(self, username: str, action: str, ip: str = None, details: str = None):
        try:
            _execute_update(
                "INSERT INTO dbo.WatcherDB_Auth_Log (username, action, ip_address, details) VALUES (?, ?, ?, ?)",
                (username, action, ip, details)
            )
        except Exception as e:
            logger.error(f"[AUTH] CRITICAL: Falha ao escrever auth log para {username}/{action}: {e}")


def get_auth_service() -> AuthService:
    return AuthService.get_instance()
