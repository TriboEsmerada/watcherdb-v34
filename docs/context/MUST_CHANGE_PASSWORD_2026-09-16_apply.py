# -*- coding: utf-8 -*-
"""must_change_password (2026-09-16) -- a coluna nunca foi criada; o script que a criava nao podia funcionar.

SINTOMA (medido hoje no log do servico): cada login escreve
    [AUTH] Query error: ... Invalid column name 'must_change_password'.
Consequencia funcional: "obrigar a trocar a password no proximo login" nao faz nada. O reset feito por um
administrador marca a coluna a 1 (falha), a troca limpa-a (falha) e o login le-a (falha) -- as tres chamadas
apanham a excepcao e seguem em frente.

CAUSA (duas, encadeadas):
 1. O script autonomo database/07_ADD_MUST_CHANGE_PASSWORD.sql poe o UPDATE a' coluna nova no MESMO batch do
    ALTER TABLE ... ADD, sem EXEC(). O SQL Server compila a batch inteira antes de a correr e recusa-a com o
    erro 207 (Invalid column name), porque a coluna ainda nao existe no momento da compilacao. O ALTER nunca
    chega a correr. Os irmaos 12 e 13 (local_password_hash, local_password_set_at, password_changed_at) so
    tinham ALTER, sem UPDATE, e por isso passaram -- e essas tres colunas estao de facto na base viva.
    O canonico ja resolveu isto ao incorporar o bloco: INSTALACAO_COMPLETA_UNIFICADA.sql:10137-10142 usa
    EXEC('UPDATE ...'). O ficheiro autonomo ficou para tras (commit 5ed4f68, 08/09).
 2. As tres chamadas no portal engoliam a excepcao com `except Exception: pass`. O defeito ficou 8 dias sem
    dar nas vistas, apesar de escrever no log a cada login.

MEDICOES (16/09, sql_monitoring, so leitura):
 - dbo.WatcherDB_Users: 11 linhas, 1 desactivada (viewer), 0 com o hash-semente admin123.
 - Colunas existentes: ... local_password_hash NVARCHAR(500) NULL, local_password_set_at DATETIME2(0) NULL,
   password_changed_at DATETIME2(0) NULL. must_change_password: ausente.

GATE: watcherdb-v1-intel-specialist (BD partilhada) -- sem veto. Ajustes incorporados:
 - DEFAULT 1 seguido de backfill a 0 para os activos (forma do canonico), nao DEFAULT 0: com DEFAULT 0 uma
   conta desactivada, ao ser reactivada, ficava isenta de trocar a password.
 - Convencao do V3.4 e' plana: database/14_...sql, e nao database/migrations/ (essa e' do V5 e do V1).
 - Nao mexer no canonico do V3.4: ja esta correcto.
 - Achado do guardiao incorporado: o 07 tambem ainda tem o bloco do hash-semente admin123 que o 5ed4f68 tirou
   de proposito do canonico. Fica marcado como historico para ninguem o correr verbatim.

O QUE ESTE LOTE FAZ (ficheiros):
 - NOVO database/14_ADD_MUST_CHANGE_PASSWORD.sql -- copia fiel do bloco canonico, para correr na base viva.
 - database/07_ADD_MUST_CHANGE_PASSWORD.sql -- cabecalho a marcar como historico (nao corrigido: fica como
   registo do defeito, com o aviso de que abortava com 207).
 - api/routers/auth_compat.py -- as tres chamadas deixam de calar a falha; registam um aviso que nomeia a
   coluna e o script. Continuam a degradar em vez de rebentar o login.
 - CHANGELOG, SOLUCOES.md, teste novo.
NAO FAZ: nao muda o canonico, nao muda o comportamento quando a coluna existe, nao toca na BD.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/MUST_CHANGE_PASSWORD_2026-09-16_apply.py --check
  py docs/context/MUST_CHANGE_PASSWORD_2026-09-16_apply.py
  py -m pytest tests/unit/test_must_change_password_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34

Depois (na base, com a identidade de deploy -- NUNCA sql_monitoring, NUNCA utilizador de dominio):
  correr database/14_ADD_MUST_CHANGE_PASSWORD.sql no SSMS contra WatcherDB_Intelligence.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "auth": Path("api/routers/auth_compat.py"),
    "sql07": Path("database/07_ADD_MUST_CHANGE_PASSWORD.sql"),
    "sql14": Path("database/14_ADD_MUST_CHANGE_PASSWORD.sql"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "solucoes": Path("docs/context/SOLUCOES.md"),
    "test": Path("tests/unit/test_must_change_password_20260916.py"),
}
MARK = "_avisar_coluna_em_falta"

# ---------------------------------------------------------------- SQL novo (14)
SQL14 = """-- ============================================================================
-- 14: coluna must_change_password em dbo.WatcherDB_Users
-- ----------------------------------------------------------------------------
-- Data: 2026-09-16 | Gate: watcherdb-v1-intel-specialist (sem veto)
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring, NUNCA utilizador de dominio)
-- Onde: servidor da Intelligence, base WatcherDB_Intelligence
--
-- PORQUE EXISTE: a coluna nunca foi criada na base viva. O script 07 punha o UPDATE a' coluna nova no MESMO
-- batch do ALTER, sem EXEC(), e o SQL Server recusava a batch inteira com o erro 207 (Invalid column name)
-- antes de correr o ALTER. Resultado: cada login escrevia "Invalid column name 'must_change_password'" no log
-- e a obrigacao de trocar a password no proximo login nao fazia nada.
--
-- Este ficheiro e' copia fiel do bloco ja canonico em INSTALACAO_COMPLETA_UNIFICADA.sql:10137-10142.
-- Substitui o 07 para efeitos de execucao (o 07 fica como registo historico).
--
-- EFEITO NESTA BASE (medido a 16/09: 11 utilizadores, 1 desactivado, 0 com o hash-semente admin123):
--   os 10 activos ficam a 0 (nao sao incomodados); o desactivado (viewer) fica a 1, e so lhe sera pedido
--   se algum dia for reactivado -- que e' o comportamento pretendido.
-- Custo: alteracao de metadados. BIT NOT NULL com DEFAULT constante nao reescreve a tabela.
--
-- Idempotente: se a coluna ja existir, nao faz nada.
-- ROLLBACK: ALTER TABLE dbo.WatcherDB_Users DROP COLUMN must_change_password;  (a restricao DEFAULT sai junto
--           em SQL Server 2016+; em versoes anteriores, largar primeiro a DEFAULT constraint pelo nome).
-- ============================================================================
USE [WatcherDB_Intelligence];
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'must_change_password')
BEGIN
    ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;
    -- EXEC() obrigatorio: sem ele, esta batch nao compila (erro 207) porque a coluna ainda nao existe
    -- no momento em que o SQL Server compila o UPDATE. Foi exactamente esse o defeito do script 07.
    EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');
    PRINT '  [OK] must_change_password criada; utilizadores activos isentos.';
END
ELSE
    PRINT '  [SKIP] must_change_password ja existe.';
GO

-- Verificacao (leitura): a coluna existe e ninguem activo ficou obrigado sem querer.
SELECT COUNT(*) AS total,
       SUM(CASE WHEN must_change_password = 1 THEN 1 ELSE 0 END) AS obrigados,
       SUM(CASE WHEN must_change_password = 1 AND disabled = 0 THEN 1 ELSE 0 END) AS obrigados_activos
FROM dbo.WatcherDB_Users;
GO
"""

# ---------------------------------------------------------------- 07 marcado como historico
SQL07_OLD = """-- ============================================================
-- Add must_change_password column to WatcherDB_Users
"""
SQL07_NEW = """-- ############################################################
-- HISTORICO -- NAO CORRER. Substituido por 14_ADD_MUST_CHANGE_PASSWORD.sql (2026-09-16).
--
-- Dois motivos:
--  1. Nunca funcionou. O UPDATE abaixo esta no MESMO batch do ALTER TABLE ... ADD, sem EXEC(). O SQL Server
--     compila a batch toda antes de a correr e recusa-a com o erro 207 (Invalid column name), porque a coluna
--     ainda nao existe nesse momento. O ALTER nunca chega a correr e a coluna nunca e' criada -- foi o que
--     aconteceu nesta instalacao, onde o portal escreveu "Invalid column name 'must_change_password'" em cada
--     login durante oito dias.
--  2. O ultimo UPDATE tem um hash bcrypt de semente (admin123) escrito no proprio ficheiro. O commit 5ed4f68
--     tirou esse bloco do canonico de proposito; aqui ficou para tras. Correr este ficheiro verbatim numa base
--     nova voltaria a introduzir essa logica.
--
-- Mantido apenas como registo. A forma correcta esta em database/14_ADD_MUST_CHANGE_PASSWORD.sql e em
-- INSTALACAO_COMPLETA_UNIFICADA.sql:10137-10142.
-- ############################################################

-- ============================================================
-- Add must_change_password column to WatcherDB_Users
"""

# ---------------------------------------------------------------- portal: a falha passa a ver-se
HELPER_OLD = 'router = APIRouter(prefix=AUTH_PREFIX, tags=["Authentication"])\n'
HELPER_NEW = '''router = APIRouter(prefix=AUTH_PREFIX, tags=["Authentication"])


# 2026-09-16: a coluna dbo.WatcherDB_Users.must_change_password nunca chegou a ser criada (o script 07
# abortava com o erro 207) e as tres chamadas que a usam engoliam a excepcao com `except Exception: pass`.
# A funcionalidade "obrigar a trocar a password no proximo login" esteve desligada oito dias sem ninguem
# reparar. Continuamos a degradar em vez de rebentar o login, mas agora a degradacao diz o que fazer.
_AVISOS_MUST_CHANGE: set = set()


def _avisar_coluna_em_falta(onde: str, exc: Exception) -> None:
    """Regista que must_change_password nao pode ser lida/escrita, sem interromper o pedido."""
    texto = str(exc)
    if "must_change_password" in texto:
        if onde in _AVISOS_MUST_CHANGE:
            return  # uma vez por sitio, por processo: senao inunda o log a cada login
        _AVISOS_MUST_CHANGE.add(onde)
        logger.warning(
            "[AUTH] %s: a coluna dbo.WatcherDB_Users.must_change_password nao existe. A obrigacao de trocar "
            "a password no proximo login esta DESLIGADA. Corrigir com database/14_ADD_MUST_CHANGE_PASSWORD.sql. "
            "Detalhe: %s", onde, texto,
        )
    else:
        logger.warning("[AUTH] %s: must_change_password nao pode ser lida/escrita: %s", onde, texto)
'''

LOGIN_OLD = """    except Exception:
        pass  # Column may not exist yet \u2014 graceful degradation

    response = JSONResponse(content=result)
"""
LOGIN_NEW = """    except Exception as exc:
        _avisar_coluna_em_falta("login", exc)

    response = JSONResponse(content=result)
"""

TROCA_OLD = """            (user["username"],),
        )
    except Exception:
        pass  # Column may not exist yet \u2014 graceful degradation
"""
TROCA_NEW = """            (user["username"],),
        )
    except Exception as exc:
        _avisar_coluna_em_falta("mudanca de password", exc)
"""

RESET_OLD = """            (username,),
        )
    except Exception:
        pass

    return JSONResponse(content={"success": True, "message": f"Senha de {username} alterada com sucesso"})
"""
RESET_NEW = """            (username,),
        )
    except Exception as exc:
        # Sem a coluna, o reset por administrador NAO obriga o utilizador a trocar a password.
        _avisar_coluna_em_falta("reset por administrador", exc)

    return JSONResponse(content={"success": True, "message": f"Senha de {username} alterada com sucesso"})
"""

AUTH_EDITS = [
    (HELPER_OLD, HELPER_NEW, 1),
    (LOGIN_OLD, LOGIN_NEW, 1),
    (TROCA_OLD, TROCA_NEW, 1),
    (RESET_OLD, RESET_NEW, 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Obrigar a trocar a password no próximo login volta a funcionar** (16/09). A coluna que guarda essa\n"
    "  obrigação nunca chegou a ser criada na base: o script que a criava punha o UPDATE no mesmo bloco do ALTER,\n"
    "  e o SQL Server recusa o bloco inteiro quando a coluna ainda não existe. Desde 08/09, o reset feito por um\n"
    "  administrador não obrigava a nada e cada início de sessão escrevia um erro no registo. Novo script\n"
    "  `database/14_ADD_MUST_CHANGE_PASSWORD.sql` (a correr na base), o script antigo fica marcado como histórico,\n"
    "  e as três chamadas deixam de calar a falha: passam a dizer no registo qual a coluna e qual o script.\n"
    "  [tier: Std]\n"
    "\n",
    1,
)

SOL_EDIT = (
    "|---|---|---|---|---|---|\n",
    "|---|---|---|---|---|---|\n"
    "| 2026-09-16 | Cada login escreve [AUTH] Query error ... Invalid column name 'must_change_password' no log do "
    "servico, e obrigar a trocar a password no proximo login nao faz nada (o reset por administrador nao obriga a "
    "nada) | A coluna nunca foi criada na base viva: o script autonomo database/07_ADD_MUST_CHANGE_PASSWORD.sql poe "
    "o UPDATE a' coluna nova no MESMO batch do ALTER TABLE ADD, sem EXEC(); o SQL Server compila a batch inteira "
    "antes de a correr e recusa-a com o erro 207, por isso o ALTER nunca corre -- os irmaos 12 e 13, que so tinham "
    "ALTER, passaram e as colunas deles existem; e as tres chamadas no portal engoliam a excepcao com except "
    "Exception: pass, portanto o defeito ficou 8 dias sem dar nas vistas apesar de escrever no log a cada login | "
    "script novo database/14_ADD_MUST_CHANGE_PASSWORD.sql com a forma do canonico (ALTER com DEFAULT 1 mais "
    "EXEC('UPDATE ... = 0 WHERE disabled = 0')); o 07 fica marcado como historico (tinha tambem o hash-semente "
    "admin123 que o 5ed4f68 tirou do canonico); as tres chamadas passam a registar um aviso que nomeia a coluna e o "
    "script | docs/context/MUST_CHANGE_PASSWORD_2026-09-16_apply.py; tests/unit/test_must_change_password_20260916.py; "
    "INSTALACAO_COMPLETA_UNIFICADA.sql:10137-10142 | must_change_password; erro 207; Invalid column name; ALTER TABLE "
    "ADD e UPDATE na mesma batch; deferred name resolution; EXEC; except Exception pass; degradacao silenciosa; "
    "coluna em falta |\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- must_change_password: o script que cria a coluna tem de poder correr, e a falha tem de ver-se.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL14 = (ROOT / "database" / "14_ADD_MUST_CHANGE_PASSWORD.sql").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
SQL07 = (ROOT / "database" / "07_ADD_MUST_CHANGE_PASSWORD.sql").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
CANON = (ROOT / "database" / "INSTALACAO_COMPLETA_UNIFICADA.sql").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
AUTH = (ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8").replace("\\r\\n", "\\n")

ALTER = "ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;"
BACKFILL = "EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');"


def _batch_do_alter(texto):
    """Devolve o batch (delimitado por GO) que contem o ALTER."""
    batches = re.split(r"(?mi)^GO\\s*$", texto)
    alvo = [b for b in batches if ALTER in b]
    assert len(alvo) == 1, "o ALTER tem de estar exactamente num batch"
    return alvo[0]


def test_o_script_14_cria_a_coluna_com_a_forma_do_canonico():
    assert ALTER in SQL14
    assert BACKFILL in SQL14
    assert "IF NOT EXISTS (SELECT 1 FROM sys.columns" in SQL14, "tem de ser idempotente"
    assert "USE [WatcherDB_Intelligence];" in SQL14


def test_o_update_nao_fica_no_mesmo_batch_do_alter_sem_exec():
    """O defeito de origem (erro 207): o UPDATE a' coluna nova compilado no batch que a cria."""
    batch = _batch_do_alter(SQL14)
    sem_exec = [ln for ln in batch.split("\\n")
                if "must_change_password" in ln
                and re.search(r"(?i)^\\s*UPDATE\\b", ln)]
    assert sem_exec == [], f"UPDATE directo no batch do ALTER (erro 207): {sem_exec}"


def test_o_script_14_nao_traz_o_hash_semente():
    assert "$2b$12$" not in SQL14, "o hash-semente admin123 foi tirado do canonico em 5ed4f68"


def test_o_script_14_nao_diverge_do_canonico():
    """O 07 divergiu do canonico e ninguem deu por isso. Este teste tranca os dois comandos."""
    assert ALTER in CANON and BACKFILL in CANON


def test_o_script_07_esta_marcado_como_historico():
    cabecalho = SQL07[:1200]
    assert "HISTORICO" in cabecalho and "NAO CORRER" in cabecalho
    assert "14_ADD_MUST_CHANGE_PASSWORD.sql" in cabecalho
    assert "207" in cabecalho, "o cabecalho tem de dizer porque e' que o ficheiro nunca funcionou"


def test_o_portal_deixa_de_calar_a_falha():
    assert "pass  # Column may not exist yet" not in AUTH
    assert AUTH.count("_avisar_coluna_em_falta(") == 4, "a definicao mais tres chamadas"
    for sitio in ('"login"', '"mudanca de password"', '"reset por administrador"'):
        assert f"_avisar_coluna_em_falta({sitio}, exc)" in AUTH


def test_o_aviso_nomeia_a_coluna_e_o_script():
    i = AUTH.index("def _avisar_coluna_em_falta")
    corpo = AUTH[i:i + 1400]
    assert "14_ADD_MUST_CHANGE_PASSWORD.sql" in corpo
    assert "logger.warning" in corpo
    assert "_AVISOS_MUST_CHANGE.add(onde)" in corpo, "uma vez por sitio, para nao inundar o log"


def test_a_degradacao_continua_a_nao_rebentar_o_login():
    """O aviso substitui o `pass`, mas a excepcao continua apanhada: o login tem de responder."""
    i = AUTH.index("# Check must_change_password flag")
    bloco = AUTH[i:i + 700]
    assert "except Exception as exc:" in bloco
    assert "raise" not in bloco
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:110]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    auth = src["auth"].read_bytes().decode("utf-8")
    if MARK in auth:
        print("[ABORT] ja aplicado"); return 1
    if src["sql14"].exists():
        print("[ABORT] database/14_ADD_MUST_CHANGE_PASSWORD.sql ja existe"); return 1

    sql07 = src["sql07"].read_bytes().decode("utf-8")
    canon = src["sql14"].parent / "INSTALACAO_COMPLETA_UNIFICADA.sql"
    canon_txt = canon.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for exigido in ("ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;",
                    "EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');"):
        if exigido not in canon_txt:
            print(f"[ABORT] o canonico mudou; o script 14 deixaria de lhe corresponder:\n  {exigido}"); return 1

    out = {
        "auth": _apply(auth, AUTH_EDITS, "auth_compat"),
        "sql07": _apply(sql07, [(SQL07_OLD, SQL07_NEW, 1)], "07"),
        "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog"),
        "solucoes": _apply(src["solucoes"].read_bytes().decode("utf-8"), [SOL_EDIT], "solucoes"),
    }
    compile(out["auth"], str(REL["auth"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] auth_compat 4 blocos (helper + 3 chamadas); 07 marcado; changelog; solucoes; sql 14; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    eol_sql = "\r\n" if "\r\n" in sql07 else "\n"
    src["sql14"].write_bytes(SQL14.replace("\n", eol_sql).encode("utf-8")); print(f"[new]   {REL['sql14']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_must_change_password_20260916.py -q --no-cov")
    print("Depois, na BASE (identidade de deploy): database/14_ADD_MUST_CHANGE_PASSWORD.sql")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
