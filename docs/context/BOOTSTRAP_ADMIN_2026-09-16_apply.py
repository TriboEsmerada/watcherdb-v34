# -*- coding: utf-8 -*-
"""Primeiro administrador sem password conhecida -- lote A, lado V3.4 (2026-09-16).

ACHADO (agente de seguranca: CRITICAL; confirmado por leitura e medicao):
 - O canonico do V3.4 deixou de criar utilizadores a 08/09 (5ed4f68) e nada o substituiu: tools/set_local_password.py
   so' faz UPDATE, a auto-provisao de AD entra como viewer, e a UI de admin exige login. Uma instalacao nova acaba SEM
   forma de entrar.
 - deploy/setup_database.ps1 (o caminho de instalacao nova) ainda corre database/CREATE_USER_AUTHENTICATION_SYSTEM.sql
   -- um sistema de autenticacao LEGADO (esquema auth.*, de 27/01) que nenhum codigo usa, que a base viva nao tem, e que
   semeia admin/admin123 e viewer/viewer123 com dois hashes bcrypt escritos no ficheiro e os imprime no ecra -- e corre o
   07_ADD_MUST_CHANGE_PASSWORD.sql, que aborta com o erro 207 (ver lote da manha).
 - docs/guides/USER_GUIDE_PT.md e USER_GUIDE_EN.md, entregues ao cliente, publicam admin/admin123 em dois sitios cada;
   referencia_tecnica.md fala de "passwords default" como risco a gerir a` mao.
 - Nesta base: 0 contas com qualquer dos hashes-semente e nenhum esquema auth. O risco e' para instalacoes novas.

O QUE ESTE LOTE FAZ (so' V3.4; o instalador do V1 e' o lote B, DEPOIS deste, porque a ordem certa e' bootstrap
primeiro, sementes depois -- nunca ao contrario):
 1. NOVO tools/bootstrap_admin.py -- cria o primeiro administrador. Interactivo (a password nunca passa por argumentos
    nem fica no historico), recusa correr se JA existir qualquer conta com role admin (senao seria uma porta de escalada
    permanente), recusa nomes previsiveis (admin, administrator, sa, root), aplica a mesma politica de password do
    portal, gera hash bcrypt novo por instalacao (custo 12, como as outras contas locais), grava must_change_password=1
    -- e o portal, desde a19585b, IMPOE essa troca no primeiro login -- e deixa rasto em WatcherDB_Auth_Log.
    Identidade de escrita: a mesma do portal (decisao do owner de 16/09; a conta dedicada entra na revisao de grants
    do fecho).
 2. deploy/setup_database.ps1 -- deixa de correr o script legado e o 07; corre o 14; ganha o Passo 3 (bootstrap) e a
    opcao -SkipBootstrap para instalacoes sem consola.
 3. database/CREATE_USER_AUTHENTICATION_SYSTEM.sql -- marcado HISTORICO; as duas sementes e o bloco que imprimia as
    passwords saem. As tabelas auth.* ficam como estavam (nao se apaga nada), mas sem contas.
 4. Guias PT/EN e referencia tecnica: deixam de publicar admin/admin123; explicam o bootstrap e a troca obrigatoria.
 5. Teste de guarda permanente: nenhum hash bcrypt completo e nenhum admin123/viewer123 fora de comentarios em
    database/, deploy/, docs/guides/ e tools/; o instalador nao pode voltar a listar o script legado nem o 07.
 6. Teste da ferramenta com cursor falso: recusa se ha admin, recusa nome previsivel, recusa password fraca, e no
    caminho feliz grava role admin + must_change_password=1 + rasto, sem a password em claro em lado nenhum.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/BOOTSTRAP_ADMIN_2026-09-16_apply.py --check
  py docs/context/BOOTSTRAP_ADMIN_2026-09-16_apply.py
  py -m pytest tests/unit/test_bootstrap_admin_20260916.py tests/unit/test_sem_credenciais_semente_20260916.py -q --no-cov
  (nao precisa de reinicio: nada do servico muda)

Para experimentar a ferramenta SEM criar nada: py tools/bootstrap_admin.py --dry-run
  (nesta base ha administradores, portanto recusa -- que e' exactamente o comportamento pretendido).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "ps1": Path("deploy/setup_database.ps1"),
    "legado": Path("database/CREATE_USER_AUTHENTICATION_SYSTEM.sql"),
    "guia_pt": Path("docs/guides/USER_GUIDE_PT.md"),
    "guia_en": Path("docs/guides/USER_GUIDE_EN.md"),
    "ref": Path("docs/guides/referencia_tecnica.md"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "tool": Path("tools/bootstrap_admin.py"),
    "test_tool": Path("tests/unit/test_bootstrap_admin_20260916.py"),
    "test_gate": Path("tests/unit/test_sem_credenciais_semente_20260916.py"),
}

# =============================================================================== 1. a ferramenta
TOOL_SRC = r'''#!/usr/bin/env python3
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
'''

# =============================================================================== 2. instalador
PS1_EDITS = [
    ("""    [string]$ConfirmedDBAIdentity
)
""",
     """    [string]$ConfirmedDBAIdentity,
    # 2026-09-16: o canonico nao cria utilizadores; o Passo 3 cria o primeiro administrador (interactivo).
    # -SkipBootstrap so' para instalacoes sem consola -- correr depois, a` mao: py tools\\bootstrap_admin.py
    [switch]$SkipBootstrap
)
""", 1),
    ("""    "05_WATCHERDB_BLUE_GREEN_ENV.sql",
    "CREATE_USER_AUTHENTICATION_SYSTEM.sql",
    "CREATE_USER_AUTH_PREFS.sql",
""",
     """    "05_WATCHERDB_BLUE_GREEN_ENV.sql",
    # 2026-09-16: CREATE_USER_AUTHENTICATION_SYSTEM.sql saiu da lista. Era um sistema de autenticacao legado
    # (esquema auth.*, 27/01) que nenhum codigo usa e que semeava admin/admin123 e viewer/viewer123 com hashes
    # escritos no ficheiro. O ficheiro fica marcado HISTORICO, sem sementes.
    "CREATE_USER_AUTH_PREFS.sql",
""", 1),
    ("""    "07_ADD_MUST_CHANGE_PASSWORD.sql",
""",
     """    "14_ADD_MUST_CHANGE_PASSWORD.sql",
""", 1),
    ("""foreach ($script in $scripts) {
    Invoke-SqlScript -File $script -Db $Database
}

# --- 3. Resumo ---
""",
     """foreach ($script in $scripts) {
    Invoke-SqlScript -File $script -Db $Database
}

# --- 3. Primeiro administrador (2026-09-16) ---
# O canonico nao cria NENHUM utilizador (as contas-semente admin123 sairam a 08/09). Sem este passo, uma
# instalacao nova fica sem forma de entrar. O comando e' interactivo (a password nunca passa por argumentos),
# recusa correr se ja existir um administrador e o portal obriga a trocar a password no primeiro login.
Write-Host ""
Write-Host "--- Passo 3: Primeiro administrador ---" -ForegroundColor Cyan
if ($SkipBootstrap) {
    Write-Host "  [SKIP] -SkipBootstrap: correr depois, a mao: py tools\\bootstrap_admin.py" -ForegroundColor Yellow
} else {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    & py (Join-Path $repoRoot "tools\\bootstrap_admin.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [AVISO] Bootstrap nao concluido (codigo $LASTEXITCODE). Repetir: py tools\\bootstrap_admin.py" -ForegroundColor Yellow
    }
}

# --- 4. Resumo ---
""", 1),
    ("""Write-Host "  3. Reiniciar servico: net stop/start WatcherDBWebServiceV33" -ForegroundColor White
""",
     """Write-Host "  3. Reiniciar servico: net stop/start WatcherDBWebServiceV33" -ForegroundColor White
Write-Host "  4. Entrar com o administrador criado no Passo 3 -- o portal obriga a trocar a password no primeiro login" -ForegroundColor White
""", 1),
]

# =============================================================================== 3. script legado
LEGADO_EDITS = [
    ("""-- ============================================================================
-- CRIACAO: Sistema de Autenticação de Usuários
-- ============================================================================
""",
     """-- ############################################################################
-- HISTORICO -- NAO FAZ PARTE DA INSTALACAO (retirado de deploy/setup_database.ps1 a 2026-09-16).
--
-- Este script cria um sistema de autenticacao LEGADO (esquema auth.*, 27/01/2026) que nenhum codigo do portal
-- usa: a autenticacao real vive em dbo.WatcherDB_Users (INSTALACAO_COMPLETA_UNIFICADA.sql, seccao 13). Ate 16/09
-- semeava admin/admin123 e viewer/viewer123 com dois hashes bcrypt escritos aqui e imprimia as passwords no ecra.
-- As sementes sairam; as tabelas ficam como estavam para quem ja as tenha (nao se apaga nada).
-- O primeiro administrador cria-se com tools/bootstrap_admin.py (interactivo, troca obrigatoria no primeiro login).
-- ############################################################################

-- ============================================================================
-- CRIACAO: Sistema de Autenticação de Usuários
-- ============================================================================
""", 1),
    ("""-- Verificar se já existe usuário admin
IF NOT EXISTS (SELECT 1 FROM auth.Users WHERE Username = 'admin')
BEGIN
    -- Senha padrão: admin123
    -- Hash bcrypt: $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIw.HpKgai

    INSERT INTO auth.Users (
        Username,
        PasswordHash,
        Email,
        FullName,
        Role,
        CreatedBy
    )
    VALUES (
        'admin',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIw.HpKgai',
        'admin@watcherdb.local',
        'Administrator',
        'admin',
        'SYSTEM'
    );

    PRINT '  [OK] Usuário admin criado';
    PRINT '      Username: admin';
    PRINT '      Senha: admin123';
    PRINT '      IMPORTANTE: Altere a senha após primeiro login!';
END
ELSE
BEGIN
    PRINT '  [INFO] Usuário admin já existe';
END

-- Verificar se existe usuário viewer
IF NOT EXISTS (SELECT 1 FROM auth.Users WHERE Username = 'viewer')
BEGIN
    -- Senha padrão: viewer123
    -- Hash bcrypt: $2b$12$7ZiQ6C5LD7QzPqQKZ4DpOeKqN0/fF1GwqZJ6LhfF.qiJ7Q8F9H1yy

    INSERT INTO auth.Users (
        Username,
        PasswordHash,
        Email,
        FullName,
        Role,
        CreatedBy
    )
    VALUES (
        'viewer',
        '$2b$12$7ZiQ6C5LD7QzPqQKZ4DpOeKqN0/fF1GwqZJ6LhfF.qiJ7Q8F9H1yy',
        'viewer@watcherdb.local',
        'Viewer User',
        'viewer',
        'SYSTEM'
    );

    PRINT '  [OK] Usuário viewer criado';
    PRINT '      Username: viewer';
    PRINT '      Senha: viewer123';
END
ELSE
BEGIN
    PRINT '  [INFO] Usuário viewer já existe';
END
""",
     """-- 2026-09-16: as duas contas-semente (admin e viewer, com password conhecida e hash escrito neste ficheiro)
-- foram retiradas. Nenhum utilizador e' criado por script; o primeiro administrador cria-se com
-- tools/bootstrap_admin.py, que obriga a trocar a password no primeiro login.
PRINT '  [INFO] Sem utilizadores por omissao. Primeiro administrador: py tools\\bootstrap_admin.py';
""", 1),
    ("""PRINT 'CREDENCIAIS PADRÃO:';
PRINT '==================';
PRINT 'Admin:';
PRINT '  Username: admin';
PRINT '  Senha: admin123';
PRINT '';
PRINT 'Viewer:';
PRINT '  Username: viewer';
PRINT '  Senha: viewer123';
PRINT '';
PRINT 'IMPORTANTE: Altere as senhas padrão após primeiro login!';
""",
     """PRINT 'SEM CREDENCIAIS POR OMISSAO (desde 2026-09-16).';
PRINT 'Primeiro administrador: py tools\\bootstrap_admin.py (interactivo; troca obrigatoria no primeiro login).';
""", 1),
    ("""PRINT '1. Alterar senhas padrão';
""",
     """PRINT '1. Criar o primeiro administrador: py tools\\bootstrap_admin.py';
""", 1),
]

# =============================================================================== 4. guias
TABELA_PT_OLD = """| Campo | Valor |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |
"""
TABELA_PT_NEW = """| Campo | Valor |
|-------|-------|
| Username | o nome escolhido ao criar o primeiro administrador durante a instalacao (`py tools\\bootstrap_admin.py`) |
| Password | a definida nesse passo -- o portal obriga a troca-la no primeiro inicio de sessao |
"""
GUIA_PT_EDITS = [
    (TABELA_PT_OLD, TABELA_PT_NEW, 2),
    ("3. Na pagina de login, introduzir as credenciais por defeito:\n",
     "3. Na pagina de login, introduzir as credenciais do primeiro administrador, criado durante a instalacao:\n", 1),
    ("> **AVISO DE SEGURANCA:** A senha por defeito `admin123` DEVE ser alterada imediatamente apos o primeiro login. Manter a senha por defeito constitui um risco de seguranca grave.\n",
     "> **NAO EXISTE PASSWORD POR OMISSAO.** O primeiro administrador e criado durante a instalacao com `py tools\\bootstrap_admin.py` "
     "(interactivo: a password nunca passa por argumentos nem fica no historico) e o portal obriga a troca-la no primeiro inicio de sessao. "
     "O comando recusa criar um segundo administrador; se ninguem conseguir entrar, o DBA reactiva uma conta existente.\n", 1),
    ("## Credenciais por Defeito\n", "## Primeiro Administrador\n", 1),
    ("> **ALTERAR IMEDIATAMENTE apos o primeiro login.**\n",
     "> **Criado na instalacao com `py tools\\bootstrap_admin.py`. Nao ha password por omissao; a troca e obrigatoria no primeiro inicio de sessao.**\n", 1),
]

TABELA_EN_OLD = """| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |
"""
TABELA_EN_NEW = """| Field | Value |
|-------|-------|
| Username | the name chosen when the first administrator was created during installation (`py tools\\bootstrap_admin.py`) |
| Password | the one set in that step -- the portal forces a change on the first sign-in |
"""
GUIA_EN_EDITS = [
    (TABELA_EN_OLD, TABELA_EN_NEW, 2),
    ("3. On the login page, enter the default credentials:\n",
     "3. On the login page, enter the first administrator's credentials, created during installation:\n", 1),
    ("> **SECURITY WARNING:** The default password `admin123` MUST be changed immediately after the first login. Keeping the default password is a serious security risk.\n",
     "> **THERE IS NO DEFAULT PASSWORD.** The first administrator is created during installation with `py tools\\bootstrap_admin.py` "
     "(interactive: the password never goes through arguments or shell history) and the portal forces a change on the first sign-in. "
     "The command refuses to create a second administrator; if nobody can sign in, the DBA re-enables an existing account.\n", 1),
    ("> **CHANGE IMMEDIATELY after the first login.**\n",
     "> **Created at installation with `py tools\\bootstrap_admin.py`. There is no default password; a change is forced on the first sign-in.**\n", 1),
]
# O titulo do anexo em ingles nao foi lido; tenta-se pelos nomes provaveis e regista-se o que aconteceu.
GUIA_EN_TITULO = [("## Default Credentials\n", "## First Administrator\n"),
                  ("## Default credentials\n", "## First Administrator\n")]

REF_EDITS = [
    ("3. **Alterar passwords default** -- O script SQL cria users com password `admin123`.\n",
     "3. **Primeiro administrador** -- o canonico nao cria utilizadores; criar com `py tools\\bootstrap_admin.py` "
     "(interactivo, recusa se ja houver admin, troca obrigatoria no primeiro login). Nao ha password por omissao.\n", 1),
    ("| Passwords default (admin123) | Risco | Script SQL cria users com senha fraca -- alterar |\n",
     # (sem escrever a password-semente por extenso: o proprio teste de guarda varre este ficheiro)
     "| Contas por omissao | Mitigado (16/09) | Sem sementes em script; primeiro admin por bootstrap interactivo; "
     "teste de guarda rejeita hashes fixos e passwords-semente em database/, deploy/, docs/guides/ e tools/ |\n", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Primeiro administrador sem password conhecida** (segurança, 16/09). Uma instalação nova terminava sem forma de\n"
    "  entrar: o canónico deixou de criar utilizadores a 08/09 e nada o substituiu — e o instalador ainda corria um script\n"
    "  legado que semeava `admin/admin123` e `viewer/viewer123` num esquema que nenhum código usa. Entra\n"
    "  `tools/bootstrap_admin.py`: interactivo, recusa correr se já houver um administrador, recusa nomes previsíveis,\n"
    "  aplica a política de password do portal e obriga a trocá-la no primeiro início de sessão. O instalador ganha o\n"
    "  Passo 3 (bootstrap) e deixa de correr o script legado e o 07; os guias do cliente deixam de publicar `admin123`;\n"
    "  um teste de guarda rejeita para sempre hashes fixos e passwords-semente em `database/`, `deploy/`, `docs/guides/`\n"
    "  e `tools/`. [tier: Std]\n"
    "\n",
    1,
)

# =============================================================================== 5. testes
TEST_TOOL_SRC = r'''"""
2026-09-16 -- tools/bootstrap_admin.py: cria o PRIMEIRO administrador e recusa tudo o resto.
Corre a logica real com um cursor falso; a password em claro nunca pode chegar a` base.
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bootstrap_admin", ROOT / "tools" / "bootstrap_admin.py")
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)

SENHA_BOA = "Fogueira!2026"


class CursorFalso:
    """Responde a`s tres consultas que a ferramenta faz e guarda tudo o que executa."""

    def __init__(self, colunas=("must_change_password", "password_changed_at"), admins=()):
        self.colunas, self.admins, self.executados, self._ultimo = colunas, admins, [], None

    def execute(self, sql, params=None):
        self.executados.append((sql, tuple(params or ())))
        if "sys.columns" in sql:
            self._ultimo = [(c,) for c in self.colunas]
        elif "role = 'admin'" in sql:
            self._ultimo = [(u, d) for u, d in self.admins]
        else:
            self._ultimo = []

    def fetchall(self):
        return list(self._ultimo)

    def inserts(self):
        return [(s, p) for s, p in self.executados if s.strip().upper().startswith("INSERT")]


def _correr(cur, nome="dba.maria", senha=SENHA_BOA, **kw):
    msgs = []
    codigo = ba.executar(cur, nome, senha, full_name="Maria", email="m@x.pt", quem="TAP\\ue", maquina="HOST1",
                         saida=msgs.append, **kw)
    return codigo, " ".join(msgs)


def test_recusa_se_ja_existe_administrador():
    cur = CursorFalso(admins=[("ue_e-snetto", False)])
    codigo, msg = _correr(cur)
    assert codigo == ba.JA_HA_ADMIN
    assert "ue_e-snetto" in msg and cur.inserts() == []


def test_recusa_mesmo_que_o_unico_admin_esteja_desactivado():
    """Anti-escalada: o comando nunca cria um segundo admin, nem quando o primeiro esta' desligado."""
    cur = CursorFalso(admins=[("antigo", True)])
    codigo, msg = _correr(cur)
    assert codigo == ba.JA_HA_ADMIN and "desactivado" in msg and cur.inserts() == []


@pytest.mark.parametrize("nome", ["admin", "Administrator", "sa", "root", "ab", "nome com espacos", ".ponto"])
def test_recusa_nomes_previsiveis_ou_invalidos(nome):
    cur = CursorFalso()
    codigo, _ = _correr(cur, nome=nome)
    assert codigo == ba.ERRO_ENTRADA and cur.inserts() == []


def test_recusa_sem_as_colunas_da_migracao():
    cur = CursorFalso(colunas=("password_changed_at",))
    codigo, msg = _correr(cur)
    assert codigo == ba.ERRO_SCHEMA and "must_change_password" in msg and cur.inserts() == []


@pytest.mark.parametrize("senha", ["curta1!", "semmaiuscula1!", "SEMMINUSCULA1!", "SemNumero!!", "SemSimbolo12"])
def test_recusa_password_fraca(senha):
    cur = CursorFalso()
    codigo, msg = _correr(cur, senha=senha)
    assert codigo == ba.ERRO_ENTRADA and "fraca" in msg and cur.inserts() == []


def test_dry_run_verifica_e_nao_grava():
    cur = CursorFalso()
    codigo, msg = _correr(cur, dry_run=True)
    assert codigo == ba.OK and "Nada gravado" in msg and cur.inserts() == []


def test_caminho_feliz_grava_admin_obrigado_a_trocar_com_rasto():
    cur = CursorFalso()
    codigo, msg = _correr(cur)
    assert codigo == ba.OK
    ins = cur.inserts()
    assert len(ins) == 2, "utilizador + rasto"
    sql_user, params_user = ins[0]
    assert "dbo.WatcherDB_Users" in sql_user and "'admin'" in sql_user
    assert "must_change_password" in sql_user and re.search(r"must_change_password\)\s*VALUES\s*\(.*,\s*1\)", sql_user, re.S)
    assert params_user[0] == "dba.maria" and params_user[1].startswith("$2b$12$")
    sql_log, params_log = ins[1]
    assert "WatcherDB_Auth_Log" in sql_log and params_log[1] == "BOOTSTRAP_ADMIN" and params_log[2] == "HOST1"
    # a password em claro nao pode aparecer em SQL nenhum, em parametro nenhum, nem nas mensagens
    for sql, params in cur.executados:
        assert SENHA_BOA not in sql and all(SENHA_BOA != str(p) for p in params)
    assert SENHA_BOA not in msg


def test_a_politica_local_nao_diverge_da_do_portal():
    """Se o servico nao importar (ambiente sem dependencias), a ferramenta aplica a sua copia. As duas tem de dar o mesmo."""
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from services.auth_service import validate_strong_password
    except Exception as e:  # pragma: no cover
        pytest.skip(f"servico nao importavel aqui: {e}")
    amostras = ["curta1!", "semmaiuscula1!", "SEMMINUSCULA1!", "SemNumero!!", "SemSimbolo12", SENHA_BOA, "Outra.Boa9"]
    # forca a copia local: simula a importacao a falhar
    import builtins
    real_import = builtins.__import__

    def sem_servico(name, *a, **k):
        if name == "services.auth_service":
            raise ImportError("simulado")
        return real_import(name, *a, **k)

    builtins.__import__ = sem_servico
    try:
        locais = [ba.politica_password(s) is None for s in amostras]
    finally:
        builtins.__import__ = real_import
    reais = [validate_strong_password(s) is None for s in amostras]
    assert locais == reais, f"politica local e do portal divergem: {list(zip(amostras, locais, reais))}"


def test_o_ficheiro_nao_aceita_password_por_argumento():
    src = (ROOT / "tools" / "bootstrap_admin.py").read_text(encoding="utf-8")
    assert "--password" not in src, "a password nunca pode vir por argumento (historico da consola)"
    assert "getpass.getpass(" in src
'''

TEST_GATE_SRC = r'''"""
2026-09-16 -- guarda permanente: nenhuma credencial-semente volta a entrar em scripts de instalacao, guias ou ferramentas.

Historia: tres sitios semeavam admin/admin123 (V3.4 legado, instalador V1, guias do cliente), um deles esteve num
repositorio publico, e o canonico tirou as sementes sem criar substituto. Este teste falha se voltar a aparecer
um hash bcrypt completo ou uma password-semente fora de comentario.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HASH_BCRYPT = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")
SEMENTES = re.compile(r"admin123|viewer123", re.IGNORECASE)
PASTAS = [("database", "*.sql"), ("deploy", "*.ps1"), ("deploy", "*.md"), ("docs/guides", "*.md"), ("tools", "*.py")]


def _ficheiros():
    for pasta, padrao in PASTAS:
        yield from sorted((ROOT / pasta).glob(padrao))


def _linha_e_comentario(linha, sufixo):
    s = linha.lstrip()
    return (sufixo == ".sql" and s.startswith("--")) or (sufixo in (".ps1", ".py") and s.startswith("#"))


def test_nenhum_hash_bcrypt_completo_em_scripts_guias_ou_ferramentas():
    culpados = [f"{p.relative_to(ROOT)}:{n}" for p in _ficheiros()
                for n, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                if HASH_BCRYPT.search(l)]
    assert culpados == [], f"hash bcrypt escrito em ficheiro: {culpados}"


def test_nenhuma_password_semente_fora_de_comentario():
    culpados = []
    for p in _ficheiros():
        for n, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if SEMENTES.search(l) and not _linha_e_comentario(l, p.suffix):
                culpados.append(f"{p.relative_to(ROOT)}:{n}: {l.strip()[:80]}")
    assert culpados == [], "password-semente fora de comentario:\n" + "\n".join(culpados)


def test_os_guias_do_cliente_nao_publicam_credenciais():
    for nome in ("USER_GUIDE_PT.md", "USER_GUIDE_EN.md", "referencia_tecnica.md"):
        texto = (ROOT / "docs" / "guides" / nome).read_text(encoding="utf-8", errors="replace")
        assert not SEMENTES.search(texto), f"{nome} ainda publica uma password-semente"
        assert "bootstrap_admin.py" in texto, f"{nome} nao explica como nasce o primeiro administrador"


def test_o_instalador_nao_corre_o_legado_nem_o_07_e_corre_o_bootstrap():
    ps1 = (ROOT / "deploy" / "setup_database.ps1").read_text(encoding="utf-8", errors="replace")
    activos = [l for l in ps1.splitlines() if not l.lstrip().startswith("#")]
    texto = "\n".join(activos)
    assert '"CREATE_USER_AUTHENTICATION_SYSTEM.sql"' not in texto
    assert '"07_ADD_MUST_CHANGE_PASSWORD.sql"' not in texto
    assert '"14_ADD_MUST_CHANGE_PASSWORD.sql"' in texto
    assert "bootstrap_admin.py" in texto and "$SkipBootstrap" in texto


def test_o_script_legado_esta_marcado_como_historico():
    cab = (ROOT / "database" / "CREATE_USER_AUTHENTICATION_SYSTEM.sql").read_text(encoding="utf-8", errors="replace")[:900]
    assert "HISTORICO" in cab and "bootstrap_admin.py" in cab
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
    if src["tool"].exists():
        print("[ABORT] tools/bootstrap_admin.py ja existe -- lote ja aplicado?"); return 1

    out = {
        "ps1": _apply(src["ps1"].read_bytes().decode("utf-8"), PS1_EDITS, "setup_database.ps1"),
        "legado": _apply(src["legado"].read_bytes().decode("utf-8"), LEGADO_EDITS, "CREATE_USER_AUTHENTICATION_SYSTEM.sql"),
        "guia_pt": _apply(src["guia_pt"].read_bytes().decode("utf-8"), GUIA_PT_EDITS, "USER_GUIDE_PT.md"),
        "ref": _apply(src["ref"].read_bytes().decode("utf-8"), REF_EDITS, "referencia_tecnica.md"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
    }
    en = _apply(src["guia_en"].read_bytes().decode("utf-8"), GUIA_EN_EDITS, "USER_GUIDE_EN.md")
    eol_en = "\r\n" if "\r\n" in en else "\n"
    titulo = "nao encontrado (anexo em ingles fica com o titulo antigo -- rever a` mao)"
    for old, new in GUIA_EN_TITULO:
        o = old.replace("\n", eol_en)
        if en.count(o) == 1:
            en = en.replace(o, new.replace("\n", eol_en)); titulo = f"'{old.strip()}' -> '{new.strip()}'"; break
    out["guia_en"] = en
    print(f"[ok] titulo do anexo EN: {titulo}")

    compile(TOOL_SRC, str(REL["tool"]), "exec")
    compile(TEST_TOOL_SRC, str(REL["test_tool"]), "exec")
    compile(TEST_GATE_SRC, str(REL["test_gate"]), "exec")
    print("[ok] instalador 5 blocos; legado 4 blocos; guia PT 5; guia EN 4(+titulo); referencia 2; changelog; ferramenta; 2 testes")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["tool"].parent.mkdir(parents=True, exist_ok=True)
    src["tool"].write_bytes(TOOL_SRC.encode("utf-8")); print(f"[new]   {REL['tool']}")
    src["test_tool"].write_bytes(TEST_TOOL_SRC.encode("utf-8")); print(f"[new]   {REL['test_tool']}")
    src["test_gate"].write_bytes(TEST_GATE_SRC.encode("utf-8")); print(f"[new]   {REL['test_gate']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_bootstrap_admin_20260916.py "
          "tests/unit/test_sem_credenciais_semente_20260916.py -q --no-cov")
    print("Experimentar sem gravar: py tools/bootstrap_admin.py --dry-run  (aqui recusa: ja ha administradores)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
