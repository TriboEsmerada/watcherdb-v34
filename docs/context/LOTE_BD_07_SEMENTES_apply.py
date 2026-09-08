"""LOTE BD: migracao 07 no canonico + sementes fora do CREATE_USER_AUTH_PREFS.sql (2026-09-08).

CORRECCAO AO COUNCIL: em 07/09 avisei que 07_ADD_MUST_CHANGE_PASSWORD.sql "obrigava todos a mudar a
password" por causa do DEFAULT 1. Errado: o proprio script faz UPDATE ... SET must_change_password = 0
WHERE disabled = 0 logo a seguir ao ALTER, e so' forca 1 nas contas que ainda tenham o hash semente
(nenhuma em PRD, verificado por SELECT em 08/09). A migracao e' segura tal como esta'.

O que este script faz (idempotente; ancoras por texto unico; EOL preservado):
  1. database/INSTALACAO_COMPLETA_UNIFICADA.sql: acrescenta a migracao 07 a` SECAO 13 (antes do PRINT
     da seccao), e corrige a nota que dizia "nao inclui 07".
  2. database/CREATE_USER_AUTH_PREFS.sql: remove o bloco "4. Inserir Users Default (password: admin123)"
     -- 4 contas, 3 admin, hash e password em comentario, ficheiro que esteve num repo publico. As tabelas
     ficam; contas criam-se pela UI de admin.
  3. docs/guides/referencia_tecnica.md: linha da migracao 07.

Depois (owner, conta de administracao da BD, regra 5): correr database/07_ADD_MUST_CHANGE_PASSWORD.sql na
WatcherDB_Intelligence -> acaba o ruido "Invalid column name 'must_change_password'" no log e o reset
pelo admin passa a marcar must_change_password=1 (o /change-password limpa).

Uso (raiz do repo):  py docs/context/LOTE_BD_07_SEMENTES_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANON = ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql"
PREFS = ROOT / "database" / "CREATE_USER_AUTH_PREFS.sql"
DOC = ROOT / "docs" / "guides" / "referencia_tecnica.md"


def abort(msg: str) -> None:
    print(f"ABORT: {msg}")
    sys.exit(1)


def _read(p: Path):
    raw = p.read_text(encoding="utf-8", newline="")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def _write(p: Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(s)


def _apply(p: Path, edits, done_marker: str) -> None:
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


# 1. canonico
_apply(
    CANON,
    [
        (
            "-- Nao inclui 07_ADD_MUST_CHANGE_PASSWORD.sql (DEFAULT 1 obriga todos a mudar; decisao\n"
            "-- separada do owner).\n",
            "-- Inclui 07_ADD_MUST_CHANGE_PASSWORD.sql (o proprio script repoe 0 nos utilizadores activos;\n"
            "-- so' forca a mudanca em contas que ainda tenham o hash semente).\n",
        ),
        (
            "PRINT '  - Secao 13: Autenticacao (WatcherDB_Users/Auth_Log/User_Preferences + colunas 12/13)';\n",
            "-- 07: obrigar mudanca de password no proximo login (reset pelo admin marca 1; /change-password limpa)\n"
            "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'must_change_password')\n"
            "BEGIN\n"
            "    ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;\n"
            "    EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');\n"
            "END\n"
            "GO\n"
            "PRINT '  - Secao 13: Autenticacao (WatcherDB_Users/Auth_Log/User_Preferences + colunas 07/12/13)';\n",
        ),
    ],
    "colunas 07/12/13",
)

# 2. sementes fora do script de tabelas
prefs_raw, prefs_eol = _read(PREFS)
START = "-- 4. Inserir Users Default (password: admin123)"
END = "PRINT 'IMPORTANTE: Alterar passwords apos primeiro login!';\nGO\n".replace("\n", prefs_eol)
if START not in prefs_raw:
    print("CREATE_USER_AUTH_PREFS.sql: sementes ja removidas (skip)")
else:
    a = prefs_raw.index(START)
    b = prefs_raw.index(END, a) + len(END)
    novo = (
        "-- 4. Utilizadores: NAO ha' contas semente (removidas em 2026-09-08, lote BD).\n"
        "--    Ate' aqui este bloco inseria admin/salomao/ricardo/viewer com a password 'admin123' e o hash\n"
        "--    bcrypt em claro, num ficheiro que esteve num repositorio publico. Verificado em 08/09: nenhuma\n"
        "--    conta em PRD tinha esse hash. Contas criam-se pela UI de admin (POST /api/auth/users) e o\n"
        "--    reset pelo admin marca must_change_password = 1 (migracao 07).\n"
        "GO\n"
    ).replace("\n", prefs_eol)
    _write(PREFS, prefs_raw[:a] + novo + prefs_raw[b:])
    print("CREATE_USER_AUTH_PREFS.sql: bloco de sementes removido")

# 3. docs
if DOC.exists():
    _apply(
        DOC,
        [(
            "|   +-- 12_ADD_LOCAL_PASSWORD_HASH.sql   # Dual auth (AD + fallback local) -- obrigatorio\n",
            "|   +-- 07_ADD_MUST_CHANGE_PASSWORD.sql   # must_change_password (reset pelo admin) -- obrigatorio\n"
            "|   +-- 12_ADD_LOCAL_PASSWORD_HASH.sql   # Dual auth (AD + fallback local) -- obrigatorio\n",
        )],
        "07_ADD_MUST_CHANGE_PASSWORD.sql   #",
    )

print("\nLOTE BD concluido. Depois (tu, conta de administracao da BD): database/07_ADD_MUST_CHANGE_PASSWORD.sql na WatcherDB_Intelligence;")
print("Restart-Service WatcherDBWebServiceV34; o log deixa de ter 'Invalid column name must_change_password'.")
