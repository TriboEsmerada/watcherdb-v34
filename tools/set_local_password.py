#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Define ou actualiza a fallback local password para um user da tabela
dbo.WatcherDB_Users (BD WatcherDB_Intelligence em SQLHDSTST505\\I01).

CONTEXTO
--------
A coluna `local_password_hash` (criada por database/12_ADD_LOCAL_PASSWORD_HASH.sql)
permite que users marcados como AD-only (`password_hash` com prefixo
`ad_auth:`) tenham TAMBEM uma password local de fallback. O `authenticate()`
em services/auth_service.py tenta SEMPRE AD primeiro; so' cai para a
fallback local quando o DC esta inalcancavel ou rejeita o bind.

USO INTERACTIVO (recomendado — password nao fica no historico do shell):

    python tools/set_local_password.py ue_e-snetto

USO INLINE (apenas para scripts; aviso de seguranca emitido):

    python tools/set_local_password.py ue_e-snetto "minha_password_temporaria"

REMOVER fallback local de um user (volta a ser AD-only puro):

    python tools/set_local_password.py ue_e-snetto --remove

Bastidor:
- bcrypt cost factor 12 (igual aos outros users locais existentes)
- UPDATE atomico via pyodbc (mesma conexao do IntelligenceConnectionPool)
- valida que o user existe antes de actualizar
- imprime hash prefix + timestamp para confirmar
"""
import sys
import os
import getpass

# Adicionar PROJECT_ROOT ao sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))


def _get_pool():
    """Lazy import to keep error messages clean if .env is not configured."""
    try:
        from services.secrets import clear_cache
        clear_cache()
    except Exception:
        pass
    from api.connection_pool import IntelligenceConnectionPool
    IntelligenceConnectionPool._instance = None
    return IntelligenceConnectionPool()


def _hash_password(plaintext: str) -> str:
    """bcrypt hash com mesmo cost factor que os outros users locais (12)."""
    try:
        from passlib.context import CryptContext
    except ImportError:
        print("ERRO: passlib nao instalado. pip install 'passlib[bcrypt]'", file=sys.stderr)
        sys.exit(1)
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
    return ctx.hash(plaintext)


def _user_exists(pool, username: str) -> dict:
    """Returns user row dict or None. Also confirms the column exists."""
    conn = pool.get_connection()
    try:
        cur = conn.cursor()
        # Confirmar que a coluna nova existe antes de prosseguir
        cur.execute(
            "SELECT 1 FROM sys.columns "
            "WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_hash'"
        )
        if not cur.fetchone():
            cur.close()
            print("ERRO: a coluna dbo.WatcherDB_Users.local_password_hash nao existe.", file=sys.stderr)
            print("Corre primeiro: database/12_ADD_LOCAL_PASSWORD_HASH.sql", file=sys.stderr)
            sys.exit(2)
        cur.execute(
            "SELECT username, role, full_name, "
            "       LEFT(ISNULL(password_hash, ''), 12) AS pw_prefix, "
            "       LEFT(ISNULL(local_password_hash, ''), 12) AS local_prefix, "
            "       local_password_set_at "
            "FROM dbo.WatcherDB_Users WHERE username = ?",
            (username,)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            return None
        cols = [d[0] for d in cur.description]
        result = dict(zip(cols, row))
        cur.close()
        return result
    finally:
        pool.return_connection(conn)


def _update_local_hash(pool, username: str, new_hash) -> None:
    conn = pool.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.WatcherDB_Users "
            "SET local_password_hash = ?, local_password_set_at = SYSUTCDATETIME() "
            "WHERE username = ?",
            (new_hash, username)
        )
        cur.close()
    finally:
        pool.return_connection(conn)


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__, file=sys.stderr)
        return 2

    username = args[0]
    remove = '--remove' in args
    inline_pwd = None
    if not remove and len(args) >= 2 and not args[1].startswith('-'):
        inline_pwd = args[1]

    pool = _get_pool()

    user = _user_exists(pool, username)
    if not user:
        print(f"ERRO: user '{username}' nao existe em dbo.WatcherDB_Users.", file=sys.stderr)
        return 1

    print(f"Encontrado user: {user['username']} | role={user['role']} | "
          f"full_name={user.get('full_name', '')}")
    print(f"  password_hash atual: {user['pw_prefix']}...")
    print(f"  local_password_hash atual: "
          f"{(user['local_prefix'] + '...') if user['local_prefix'] else '(nao definida)'}")
    if user.get('local_password_set_at'):
        print(f"  local set at: {user['local_password_set_at']}")
    print()

    if remove:
        confirm = input(f"REMOVER local fallback do user '{username}'? (yes/NO): ").strip().lower()
        if confirm != 'yes':
            print("Cancelado.")
            return 0
        _update_local_hash(pool, username, None)
        print(f"OK — local_password_hash de '{username}' removido.")
        return 0

    # Definir nova password
    if inline_pwd is not None:
        print("[AVISO] Password passada como argumento — fica visivel no historico do shell.",
              file=sys.stderr)
        plaintext = inline_pwd
    else:
        plaintext = getpass.getpass(f"Nova password local para '{username}': ")
        if not plaintext:
            print("ERRO: password vazia.", file=sys.stderr)
            return 1
        confirm = getpass.getpass("Confirmar password: ")
        if confirm != plaintext:
            print("ERRO: passwords nao coincidem.", file=sys.stderr)
            return 1
        if len(plaintext) < 8:
            print("ERRO: password tem menos de 8 caracteres.", file=sys.stderr)
            return 1

    new_hash = _hash_password(plaintext)
    _update_local_hash(pool, username, new_hash)

    # Confirmar
    user_after = _user_exists(pool, username)
    print()
    print(f"OK — local_password_hash actualizado para '{username}'.")
    print(f"  novo prefix: {user_after['local_prefix']}...")
    print(f"  set at: {user_after['local_password_set_at']}")
    print()
    print("Agora podes fazer login com este user e a password definida")
    print("MESMO quando o DC AD esta inalcancavel.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
