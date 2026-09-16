"""
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
