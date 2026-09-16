#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cria o PRIMEIRO administrador do portal WatcherDB numa instalacao nova.

Porque existe: o canonico da base nao cria nenhum utilizador (as contas-semente com password conhecida sairam a
08/09/2026) e a gestao de utilizadores do portal exige login. Sem este comando, uma instalacao nova nao tem por
onde entrar.

Regras (parecer de seguranca de 16/09/2026):
  - Interactivo: a password nunca passa por argumentos nem fica no historico da consola.
  - RECUSA correr se ja existir qualquer conta com role admin. Nao e' um comando de "criar mais um admin" -- isso
    faz-se pela UI de administracao. Sem esta recusa, o comando seria uma porta de escalada permanente.
  - Recusa nomes previsiveis (admin, administrator, sa, root): um nome fixo e' metade de uma credencial.
  - Mesma politica de password do portal; hash bcrypt novo por instalacao (custo 12, como as outras contas locais).
  - Grava must_change_password = 1: o portal obriga a trocar a password no primeiro login.
  - Deixa rasto em WatcherDB_Auth_Log (accao BOOTSTRAP_ADMIN, quem correu, de que maquina).

Uso (raiz do repositorio, com o .env configurado):
    py tools/bootstrap_admin.py
    py tools/bootstrap_admin.py --username dba.maria --full-name "Maria Silva" --email maria@cliente.pt
    py tools/bootstrap_admin.py --dry-run        (verifica tudo e nao grava nada)

Identidade: a mesma ligacao que o portal usa (INTELLIGENCE_* no .env).
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import socket
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

NOMES_PREVISIVEIS = {"admin", "administrator", "sa", "root", "watcherdb", "superuser"}
NOME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{2,99}$")
COLUNAS_OBRIGATORIAS = ("must_change_password", "password_changed_at")

# codigos de saida: quem automatiza a instalacao consegue distinguir os casos
OK, ERRO_ENTRADA, ERRO_SCHEMA, JA_HA_ADMIN, ERRO_BD = 0, 1, 2, 3, 4


def politica_password(pw: str):
    """A mesma regra do portal. Importa-se a do servico; se nao der (ambiente sem dependencias), aplica-se
    localmente a mesma lista -- e o teste garante que as duas nao divergem."""
    try:
        from services.auth_service import validate_strong_password  # type: ignore
        return validate_strong_password(pw)
    except Exception:
        if len(pw) < 8:
            return "Minimo 8 caracteres"
        if not re.search(r"[A-Z]", pw):
            return "Falta letra maiuscula"
        if not re.search(r"[a-z]", pw):
            return "Falta letra minuscula"
        if not re.search(r"[0-9]", pw):
            return "Falta numero"
        if not re.search(r"[^A-Za-z0-9]", pw):
            return "Falta simbolo"
        return None


def gerar_hash(pw: str) -> str:
    try:
        from passlib.context import CryptContext
    except ImportError:
        print("ERRO: passlib nao instalado. pip install 'passlib[bcrypt]'", file=sys.stderr)
        sys.exit(ERRO_ENTRADA)
    return CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12).hash(pw)


def validar_nome(nome: str):
    if not NOME_RE.match(nome or ""):
        return "Nome invalido: 3 a 100 caracteres, letras, numeros, ponto, hifen ou sublinhado, a comecar por letra ou numero."
    if nome.lower() in NOMES_PREVISIVEIS:
        return f"'{nome}' e' um nome previsivel -- e' metade de uma credencial. Escolha um nome proprio (ex.: dba.maria)."
    return None


def colunas_em_falta(cur) -> list:
    cur.execute(
        "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name IN (?, ?)",
        COLUNAS_OBRIGATORIAS,
    )
    existentes = {r[0] for r in cur.fetchall()}
    return [c for c in COLUNAS_OBRIGATORIAS if c not in existentes]


def administradores(cur) -> list:
    cur.execute("SELECT username, disabled FROM dbo.WatcherDB_Users WHERE role = 'admin' ORDER BY username")
    return [(r[0], bool(r[1])) for r in cur.fetchall()]


def criar(cur, username: str, hash_pw: str, full_name, email, quem: str, maquina: str) -> None:
    cur.execute(
        "INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, email, full_name, must_change_password) "
        "VALUES (?, ?, 'admin', ?, ?, 1)",
        (username, hash_pw, email, full_name),
    )
    cur.execute(
        "INSERT INTO dbo.WatcherDB_Auth_Log (username, action, ip_address, details) VALUES (?, ?, ?, ?)",
        (username, "BOOTSTRAP_ADMIN", maquina, f"primeiro administrador criado por {quem} via tools/bootstrap_admin.py"),
    )


def executar(cur, username: str, password: str, full_name=None, email=None, dry_run: bool = False,
             quem: str = "?", maquina: str = "?", saida=print) -> int:
    """Toda a logica, com o cursor injectado: e' isto que o teste corre com um cursor falso."""
    erro = validar_nome(username)
    if erro:
        saida(f"RECUSADO: {erro}")
        return ERRO_ENTRADA
    faltam = colunas_em_falta(cur)
    if faltam:
        saida(f"RECUSADO: faltam colunas em dbo.WatcherDB_Users: {', '.join(faltam)}. "
              "Corra database/13_ADD_PASSWORD_CHANGED_AT.sql e database/14_ADD_MUST_CHANGE_PASSWORD.sql primeiro.")
        return ERRO_SCHEMA
    admins = administradores(cur)
    if admins:
        lista = ", ".join(f"{u}{' (desactivado)' if d else ''}" for u, d in admins)
        saida(f"RECUSADO: ja existe administrador ({lista}). Este comando so' cria o PRIMEIRO. "
              "Para criar mais, use a gestao de utilizadores do portal com um administrador existente; "
              "se todos estiverem desactivados, o DBA reactiva um (UPDATE disabled = 0) com a identidade de deploy.")
        return JA_HA_ADMIN
    erro = politica_password(password)
    if erro:
        saida(f"RECUSADO: password fraca -- {erro}.")
        return ERRO_ENTRADA
    if dry_run:
        saida(f"[dry-run] Tudo verificado. Criaria o administrador '{username}' com troca obrigatoria no primeiro login. Nada gravado.")
        return OK
    criar(cur, username, gerar_hash(password), full_name, email, quem, maquina)
    saida(f"[OK] Administrador '{username}' criado. No primeiro login o portal obriga a trocar a password.")
    saida("     Rasto: WatcherDB_Auth_Log, accao BOOTSTRAP_ADMIN.")
    return OK


def _pool():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
    try:
        from services.secrets import clear_cache
        clear_cache()
    except Exception:
        pass
    from api.connection_pool import IntelligenceConnectionPool
    IntelligenceConnectionPool._instance = None
    return IntelligenceConnectionPool()


def _pedir_password() -> str:
    for _ in range(3):
        p1 = getpass.getpass("Password do administrador: ")
        p2 = getpass.getpass("Repita a password: ")
        if p1 != p2:
            print("As duas nao coincidem. Outra vez.")
            continue
        erro = politica_password(p1)
        if erro:
            print(f"Password fraca -- {erro}. Minimo 8 caracteres com maiuscula, minuscula, numero e simbolo.")
            continue
        return p1
    print("Tres tentativas. A sair sem criar nada.", file=sys.stderr)
    sys.exit(ERRO_ENTRADA)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cria o primeiro administrador do portal WatcherDB (interactivo).")
    ap.add_argument("--username", help="nome da conta (sem isto, pergunta)")
    ap.add_argument("--full-name", dest="full_name", default=None)
    ap.add_argument("--email", default=None)
    ap.add_argument("--dry-run", action="store_true", help="verifica tudo e nao grava nada")
    args = ap.parse_args(argv)

    username = args.username or input("Nome da conta do administrador (ex.: dba.maria): ").strip()
    erro = validar_nome(username)
    if erro:
        print(f"RECUSADO: {erro}", file=sys.stderr)
        return ERRO_ENTRADA

    pool = _pool()
    conn = pool.get_connection()
    try:
        cur = conn.cursor()
        # verificar o que e' possivel ANTES de pedir a password, para nao a pedir em vao
        if colunas_em_falta(cur) or administradores(cur):
            codigo = executar(cur, username, "Verificacao-so!1", args.full_name, args.email, dry_run=True)
            return codigo
        password = "Verificacao-so!1" if args.dry_run else _pedir_password()
        quem = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', getpass.getuser())}".strip("\\")
        codigo = executar(cur, username, password, args.full_name, args.email, dry_run=args.dry_run,
                          quem=quem, maquina=socket.gethostname())
        if codigo == OK and not args.dry_run:
            try:
                conn.commit()
            except Exception:
                pass  # ligacoes em autocommit nao tem o que confirmar
        cur.close()
        return codigo
    except Exception as e:
        print(f"ERRO de base de dados: {e}", file=sys.stderr)
        return ERRO_BD
    finally:
        pool.return_connection(conn)


if __name__ == "__main__":
    sys.exit(main())
