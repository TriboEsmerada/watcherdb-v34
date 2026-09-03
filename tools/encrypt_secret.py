#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper para encriptar uma password e imprimir o token "encrypted:..."
pronto a colar no .env.

USO INTERATIVO (recomendado):
    python tools/encrypt_secret.py

USO INLINE (cuidado: aparece no historico do shell):
    python tools/encrypt_secret.py "minha_password"

Bastidor:
    Delega para services.secrets.encrypt_value, que usa a master key Fernet
    resolvida automaticamente:
    1. WATCHERDB_ENCRYPTION_KEY_DPAPI (DPAPI-wrapped, recomendado em Windows)
    2. WATCHERDB_ENCRYPTION_KEY (plain Fernet key, backwards compat)

    A segurança vem do facto de a master key estar protegida por DPAPI:
    so a conta Windows que escreveu o blob consegue desencriptar qualquer
    secret encriptado por este helper.

Para gerar a master key inicial em Windows (uma vez por maquina/conta):
    python -c "
    from cryptography.fernet import Fernet
    from services.secrets import wrap_key_dpapi
    k = Fernet.generate_key()
    print('WATCHERDB_ENCRYPTION_KEY_DPAPI=' + wrap_key_dpapi(k))
    "
    Cola o output no .env. (Mas isto NAO e' preciso na maioria dos casos —
    o .env actual ja' tem WATCHERDB_ENCRYPTION_KEY_DPAPI configurada.)
"""
import sys
import os
import getpass

# Adicionar a raiz do projecto ao sys.path para conseguir importar services.secrets
# (correr "python tools/encrypt_secret.py" so adiciona tools/ por defeito)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Carregar .env antes de importar services.secrets para o get_master_key
# encontrar a chave correta
from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

try:
    from services.secrets import encrypt_value
except ImportError as e:
    print(f"ERRO: nao consegui importar services.secrets: {e}", file=sys.stderr)
    print(f"PROJECT_ROOT: {_PROJECT_ROOT}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    if len(sys.argv) > 2:
        print("Uso: python tools/encrypt_secret.py [password]", file=sys.stderr)
        return 2

    if len(sys.argv) == 2:
        plaintext = sys.argv[1]
        print("[AVISO] Password passada como argumento — fica visivel no historico do shell.",
              file=sys.stderr)
    else:
        plaintext = getpass.getpass("Password a encriptar: ")
        if not plaintext:
            print("ERRO: password vazia", file=sys.stderr)
            return 1
        confirm = getpass.getpass("Confirmar password: ")
        if confirm != plaintext:
            print("ERRO: passwords nao coincidem", file=sys.stderr)
            return 1

    try:
        token = encrypt_value(plaintext)
    except RuntimeError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        print("Verifica se WATCHERDB_ENCRYPTION_KEY_DPAPI ou WATCHERDB_ENCRYPTION_KEY", file=sys.stderr)
        print("estao definidas no .env.", file=sys.stderr)
        return 1

    # Validar round-trip
    from services.secrets import get_secret, clear_cache
    import os
    test_var = '_TEMP_ENCRYPT_VALIDATE'
    os.environ[test_var] = token
    clear_cache()
    recovered = get_secret(test_var, '')
    os.environ.pop(test_var, None)
    if recovered != plaintext:
        print(f"ERRO: round-trip de validacao falhou", file=sys.stderr)
        return 1

    user = getpass.getuser()
    print()
    print(f"OK — encriptado com a master key resolvida para a conta: {user}")
    print()
    print("Cola esta linha no .env (ajusta o nome da variavel conforme necessario):")
    print()
    print(f"  INTELLIGENCE_SQL_PASSWORD={token}")
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
