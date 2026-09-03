"""
WatcherDB Secret Management
============================

Provides transparent decryption of secrets stored in environment variables
(typically loaded from `.env` by python-dotenv).

Two encryption tiers are supported:

Tier 1 — Plain Fernet master key (backwards compatible):
    .env contains:
        WATCHERDB_ENCRYPTION_KEY=<plain Fernet key, base64>
        INTELLIGENCE_SQL_PASSWORD=encrypted:gAAAAA...

Tier 2 — DPAPI-wrapped Fernet master key (recommended on Windows):
    .env contains:
        WATCHERDB_ENCRYPTION_KEY_DPAPI=<base64 of DPAPI blob>
        INTELLIGENCE_SQL_PASSWORD=encrypted:gAAAAA...

    DPAPI restricts decryption to the same Windows user account that
    wrote the blob (the service account that runs WatcherDB). Anyone
    reading `.env` from another account cannot recover the master key.

Tier 3 — DPAPI machine-scope key FILE (Etapa 1.4 empacotamento; PREFERIDO
quando a app corre como servico Windows):
    secrets_dir()/master.key.dpapi (V3.3; override WATCHERDB_MASTER_KEY_FILE,
    ou WATCHERDB_SECRETS_DIR em produtos sem watcherdb.core.paths) contem
    base64 de um blob DPAPI criado com CRYPTPROTECT_LOCAL_MACHINE: qualquer
    conta DESTA maquina (NetworkService incluida) consegue decriptar, por
    isso a ACL do ficheiro e a fronteira de seguranca — o instalador
    restringe a SYSTEM + Administrators + conta do servico. Tem prioridade
    sobre os Tiers 1 e 2 na resolucao.

Public API
----------
    get_secret(name, default="") -> str
        Read an env var. If its value starts with "encrypted:" the rest
        is Fernet-decrypted with the master key.

    encrypt_value(plaintext) -> str
        Encrypt a plaintext string with the current master key,
        returning the "encrypted:..." form ready to write into .env.

    wrap_key_dpapi(fernet_key, machine_scope=False) -> str
        DPAPI-wrap a Fernet key and return base64. Use once during
        provisioning. The result goes into .env as
        WATCHERDB_ENCRYPTION_KEY_DPAPI.

    provision_master_key_file(fernet_key, target=None) -> str
        Wrap machine-scope + escreve o blob no ficheiro de secrets
        (Tier 3). Correr uma vez POR MAQUINA, na maquina alvo.

    try_get_master_key() -> Optional[bytes]
        Cadeia de resolucao completa sem levantar excepcao (None se
        indisponivel) — para consumidores fora de get_secret().

The master key is resolved lazily and cached for the process lifetime.
Decrypted secrets are also cached so each call after the first is a
plain dict lookup.

NOTA DE PROJECTO
----------------
Este modulo e' uma copia exacta de WATCHERDB_V5/services/secrets.py.
Quando o packaging comercial unificar os projectos, deve mover-se para
um shared_lib/ partilhado entre V3.2 e V5 em vez de manter copias.
Por agora aceita-se o copy-paste; alteracoes a este ficheiro devem ser
replicadas no V5 manualmente.
"""

from __future__ import annotations

import base64
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_PREFIX = "encrypted:"

# Etapa 1.4 (auditoria empacotamento): master key em ficheiro DPAPI
# machine-scope. O blob user-scope do .env (Tier 2) nao e decriptavel
# pela conta do servico (NetworkService) quando foi criado pelo admin —
# o ficheiro machine-scope resolve isso; a ACL do ficheiro e a fronteira.
CRYPTPROTECT_LOCAL_MACHINE = 0x4
_KEY_FILE_BASENAME = "master.key.dpapi"

_master_key_lock = threading.Lock()
_master_key: Optional[bytes] = None
_secret_cache: dict[str, str] = {}


def _master_key_file_candidates() -> list:
    """Paths candidatos ao ficheiro do blob machine-scope, por prioridade.

    WATCHERDB_MASTER_KEY_FILE definido = override explicito e EXCLUSIVO
    (testes, layouts nao standard). Sem override: secrets_dir() no V3.3;
    noutros produtos (V5 nao tem watcherdb.core.paths), WATCHERDB_SECRETS_DIR.
    """
    from pathlib import Path

    explicit = os.environ.get("WATCHERDB_MASTER_KEY_FILE")
    if explicit:
        return [Path(explicit)]
    try:
        from watcherdb.core.paths import secrets_dir  # V3.3

        return [secrets_dir() / _KEY_FILE_BASENAME]
    except ImportError:
        env_dir = os.environ.get("WATCHERDB_SECRETS_DIR")
        if env_dir:
            return [Path(env_dir) / _KEY_FILE_BASENAME]
    return []


def _try_dpapi_unwrap_file() -> Optional[bytes]:
    """Tier 3: blob DPAPI machine-scope em ficheiro (conteudo base64)."""
    path = next(
        (p for p in _master_key_file_candidates() if p.is_file()), None
    )
    if path is None:
        return None
    try:
        import win32crypt  # type: ignore
    except ImportError:
        logger.warning(
            "Master key file %s presente mas pywin32 nao esta instalado.",
            path,
        )
        return None
    try:
        blob = base64.b64decode(path.read_text(encoding="ascii").strip())
        # flags so contam no CryptProtectData; o unwrap e identico.
        _, plain = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return plain
    except Exception as exc:
        logger.error(
            "Falha ao decriptar master key file %s: %s", path, exc
        )
        return None


def _try_dpapi_unwrap() -> Optional[bytes]:
    """Try to recover the master key from a DPAPI-wrapped blob in env.

    Returns the raw Fernet key bytes on success, None if not configured
    or if unwrap fails (which usually means a different Windows user is
    trying to read it).
    """
    blob_b64 = os.environ.get("WATCHERDB_ENCRYPTION_KEY_DPAPI")
    if not blob_b64:
        return None
    try:
        import win32crypt  # type: ignore
    except ImportError:
        logger.warning(
            "WATCHERDB_ENCRYPTION_KEY_DPAPI is set but pywin32 is not "
            "installed. Cannot unwrap DPAPI key. Install pywin32 or use "
            "WATCHERDB_ENCRYPTION_KEY (plain) instead."
        )
        return None
    try:
        blob = base64.b64decode(blob_b64)
        # CryptUnprotectData returns (description, data)
        _, plain = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return plain
    except Exception as exc:
        logger.error(
            "Failed to DPAPI-unwrap WATCHERDB_ENCRYPTION_KEY_DPAPI. "
            "This usually means the .env was provisioned by a different "
            "Windows user. Error: %s",
            exc,
        )
        return None


def _get_master_key() -> bytes:
    """Resolve the Fernet master key, caching for the process lifetime.

    Resolution order:
        1. master.key.dpapi file (DPAPI machine-scope — Windows service)
        2. WATCHERDB_ENCRYPTION_KEY_DPAPI (DPAPI user-scope, legacy)
        3. WATCHERDB_ENCRYPTION_KEY (plain text, backwards compatible)

    Raises:
        RuntimeError if neither is set or if DPAPI unwrap fails and
        no plain key is available.
    """
    global _master_key
    if _master_key is not None:
        return _master_key

    with _master_key_lock:
        if _master_key is not None:
            return _master_key

        # Tier 3 (prioridade maxima): ficheiro DPAPI machine-scope
        file_key = _try_dpapi_unwrap_file()
        if file_key:
            _master_key = file_key
            logger.info("Master key loaded from machine-scope DPAPI key file")
            return _master_key

        # Tier 2: DPAPI
        dpapi = _try_dpapi_unwrap()
        if dpapi:
            _master_key = dpapi
            logger.info("Master key loaded from DPAPI-wrapped blob")
            return _master_key

        # Tier 1: plain key (backwards compatible)
        plain = os.environ.get("WATCHERDB_ENCRYPTION_KEY")
        if plain:
            _master_key = plain.encode() if isinstance(plain, str) else plain
            logger.info("Master key loaded from plain WATCHERDB_ENCRYPTION_KEY")
            return _master_key

        raise RuntimeError(
            "No master key available. Set WATCHERDB_ENCRYPTION_KEY_DPAPI "
            "(preferred) or WATCHERDB_ENCRYPTION_KEY in .env."
        )


def get_secret(name: str, default: str = "") -> str:
    """Read an environment variable, transparently decrypting if needed.

    If the raw value starts with the "encrypted:" prefix, the remainder
    is treated as a Fernet token and decrypted with the master key.
    Otherwise the raw value is returned unchanged.

    Returns ``default`` if the variable is unset or empty.

    Decrypted values are cached in memory by name so subsequent calls
    are O(1).
    """
    if name in _secret_cache:
        return _secret_cache[name]

    raw = os.environ.get(name)
    if not raw:
        return default

    if not raw.startswith(_PREFIX):
        # Plain value — cache and return
        _secret_cache[name] = raw
        return raw

    # Encrypted — decrypt with master key
    token = raw[len(_PREFIX):]
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(_get_master_key())
        plaintext = fernet.decrypt(token.encode()).decode()
        _secret_cache[name] = plaintext
        return plaintext
    except Exception as exc:
        logger.error(
            "Failed to decrypt secret %s. Returning default. Error: %s",
            name,
            exc,
        )
        return default


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return the ``encrypted:...`` form.

    Use this once during provisioning to convert a plain password into
    the form that goes into ``.env``. Requires the master key to be
    resolvable (either DPAPI or plain).
    """
    from cryptography.fernet import Fernet
    fernet = Fernet(_get_master_key())
    token = fernet.encrypt(plaintext.encode()).decode()
    return _PREFIX + token


def wrap_key_dpapi(fernet_key: bytes, machine_scope: bool = False) -> str:
    """DPAPI-wrap a Fernet key and return its base64 representation.

    machine_scope=False (default, backwards compat): so a MESMA conta
    Windows consegue unwrap — formato de WATCHERDB_ENCRYPTION_KEY_DPAPI.
    machine_scope=True (Etapa 1.4): CRYPTPROTECT_LOCAL_MACHINE — qualquer
    conta desta maquina consegue unwrap; usar APENAS no ficheiro de
    secrets com ACL restrita (ver provision_master_key_file).

    Run once during provisioning. Requires pywin32.
    """
    import win32crypt  # type: ignore
    if isinstance(fernet_key, str):
        fernet_key = fernet_key.encode()
    flags = CRYPTPROTECT_LOCAL_MACHINE if machine_scope else 0
    blob = win32crypt.CryptProtectData(
        fernet_key,
        "WatcherDB Master Key",
        None,
        None,
        None,
        flags,
    )
    return base64.b64encode(blob).decode("ascii")


def provision_master_key_file(fernet_key: bytes, target: Optional[str] = None) -> str:
    """Escreve o blob DPAPI machine-scope no ficheiro de secrets (Tier 3).

    Correr UMA vez por maquina, NA maquina alvo (blobs DPAPI nao viajam
    entre maquinas). A ACL do diretorio/ficheiro e responsabilidade do
    instalador. Devolve o path escrito.
    """
    from pathlib import Path

    if isinstance(fernet_key, str):
        fernet_key = fernet_key.encode()
    if target:
        path = Path(target)
    else:
        candidates = _master_key_file_candidates()
        if not candidates:
            raise RuntimeError(
                "Sem destino para o master key file: define "
                "WATCHERDB_MASTER_KEY_FILE ou WATCHERDB_SECRETS_DIR."
            )
        path = candidates[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    blob64 = wrap_key_dpapi(fernet_key, machine_scope=True)
    path.write_text(blob64 + "\n", encoding="ascii")
    return str(path)


def try_get_master_key() -> Optional[bytes]:
    """Como _get_master_key() mas devolve None em vez de levantar.

    Consumidores fora do fluxo get_secret (ex.: api/connection_pool
    _decrypt) usam isto para partilhar a MESMA cadeia de resolucao
    (ficheiro machine-scope -> env DPAPI -> plain) em vez de
    reimplementar DPAPI inline.
    """
    try:
        return _get_master_key()
    except Exception:
        return None


def clear_cache() -> None:
    """Clear the in-memory secret cache. Mostly useful for tests."""
    global _master_key
    with _master_key_lock:
        _master_key = None
        _secret_cache.clear()
