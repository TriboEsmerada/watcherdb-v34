# -*- coding: utf-8 -*-
"""2026-10-07 -- SETUP_DATABASE_CLI (lotes A.1 + esqueleto D): nomes substituidos em runtime, canonico byte-igual,
lotes GO como o sqlcmd, setup estrito com dry-run por omissao, subcomandos no watcherdb.exe."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from watcherdb.install import OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR, cli
from watcherdb.install import sqlnames as sn
from watcherdb.install import dbsetup as ds

ROOT = Path(__file__).resolve().parents[2]
DB_DIR = ROOT / "database"
CANONICO = DB_DIR / "INSTALACAO_COMPLETA_UNIFICADA.sql"


# ------------------------------------------------------------------ nomes
@pytest.mark.parametrize("nome", ["WatcherDB", "watcherdb", "_x", "A1_b2", "W" * 64])
def test_identificadores_validos(nome):
    assert sn.validar_identificador(nome) == nome


@pytest.mark.parametrize("nome", ["", "1abc", "x]; DROP DATABASE [y", "a b", "a.b", "a-b", "a'b", "W" * 65, None])
def test_identificadores_invalidos(nome):
    with pytest.raises(sn.NomeInvalido):
        sn.validar_identificador(nome)


def test_canonico_byte_identico_com_os_nomes_canonicos():
    txt = CANONICO.read_text(encoding="utf-8-sig")
    out, nb, nl = sn.substituir_nomes(txt, sn.NOME_BASE_CANONICO, sn.LOGIN_CANONICO)
    assert out == txt and nb == 0 and nl == 0


def test_canonico_sem_restos_com_outros_nomes():
    txt = CANONICO.read_text(encoding="utf-8-sig")
    out, nb, nl = sn.substituir_nomes(txt, OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR)
    assert nb >= 70, nb     # 73 ocorrencias medidas a 2026-10-07; nao fixar o numero exacto
    assert nl >= 15, nl     # 19 GRANT medidos
    assert sn.restos_canonicos(out, OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR) == []
    assert "USE [WatcherDB]" in out and "USE [WatcherDB_Intelligence]" not in out
    assert "TO [watcherdb]" in out


def test_sufixos_e_ficheiros_logicos_seguem_o_nome_da_base():
    sql = "CREATE DATABASE [WatcherDB_Intelligence] ON (NAME = N'WatcherDB_Intelligence_KPI_Data', FILENAME = N'D:\\x\\WatcherDB_Intelligence.mdf')"
    out, nb, _ = sn.substituir_nomes(sql, "Cli", "watcherdb")
    assert out == "CREATE DATABASE [Cli] ON (NAME = N'Cli_KPI_Data', FILENAME = N'D:\\x\\Cli.mdf')" and nb == 3


def test_nao_toca_em_nomes_colados_a_alfanumericos():
    assert sn.substituir_nomes("XWatcherDB_Intelligence sql_monitoring2", "A", "b")[0] == "XWatcherDB_Intelligence sql_monitoring2"


@pytest.mark.parametrize("script", sn.SCRIPTS)
def test_todos_os_scripts_da_lista_substituem_sem_restos(script):
    caminho = DB_DIR / script
    if not caminho.exists():
        pytest.skip(f"{script} nao existe no repo (setup_database.ps1 tambem o salta)")
    txt = caminho.read_text(encoding="utf-8-sig")
    assert sn.substituir_nomes(txt, sn.NOME_BASE_CANONICO, sn.LOGIN_CANONICO)[0] == txt
    out, _, _ = sn.substituir_nomes(txt, OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR)
    assert sn.restos_canonicos(out, OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR) == []
    assert len(sn.dividir_lotes(out)) >= 1


# ------------------------------------------------------------------ lotes GO
def test_lotes_do_canonico_batem_com_as_linhas_go():
    txt = CANONICO.read_text(encoding="utf-8-sig")
    n_go = len(re.findall(r"^\s*GO\s*$", txt, flags=re.M | re.I))
    lotes = sn.dividir_lotes(txt)
    assert n_go >= 500 and n_go - 5 <= len(lotes) <= n_go + 1   # lotes vazios entre GO consecutivos descartam-se


def test_go_com_repeticao_minusculas_e_ponto_e_virgula():
    lotes = sn.dividir_lotes("SELECT 1\nGO 3\nselect 2\ngo\nSELECT 3\nGO;\n\n")
    assert lotes == ["SELECT 1", "SELECT 1", "SELECT 1", "select 2", "SELECT 3"]


def test_go_dentro_de_texto_nao_separa():
    assert sn.dividir_lotes("PRINT 'GO'\n-- GO ahead\nSELECT 'x GO y'\nGO") == ["PRINT 'GO'\n-- GO ahead\nSELECT 'x GO y'"]


# ------------------------------------------------------------------ plano e execucao
def test_planear_lista_os_22_scripts_na_ordem(tmp_path):
    passos = ds.planear(DB_DIR, OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR)
    assert [p.script for p in passos] == list(sn.SCRIPTS)
    canon = next(p for p in passos if p.script == "INSTALACAO_COMPLETA_UNIFICADA.sql")
    assert canon.existe and canon.lotes >= 500 and canon.subst_base >= 70


def test_dry_run_nao_liga_a_nada(tmp_path):
    chamadas = []
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=DB_DIR, dry_run=True,
                      connect=lambda *a: chamadas.append(a), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert chamadas == [] and rel.resultado == "dry-run" and (tmp_path / "r.json").exists()


class _Cursor:
    def __init__(self, falhar_no_lote: int = 0, login_existe: bool = True):
        self.exec: list = []
        self.falhar_no_lote = falhar_no_lote
        self.login_existe = login_existe
        self._ultimo = None
        self._n = 0

    def execute(self, sql, *params):
        self.exec.append(sql)
        self._ultimo = sql
        if sql.startswith("SELECT DB_ID"):
            return
        if "sys.server_principals" in sql:
            return
        if "sys.database_principals" in sql:
            return
        if sql.startswith(("CREATE DATABASE", "CREATE USER")):
            return
        self._n += 1
        if self.falhar_no_lote and self._n == self.falhar_no_lote:
            raise RuntimeError("Incorrect syntax near 'x'. PWD=segredo")

    def fetchone(self):
        if self._ultimo.startswith("SELECT DB_ID"):
            return (None,)          # base nao existe
        if "sys.server_principals" in self._ultimo:
            return (1,) if self.login_existe else None
        if "sys.database_principals" in self._ultimo:
            return None             # utilizador ainda nao existe
        return None

    def nextset(self):
        return False


class _Conn:
    def __init__(self, cursor):
        self._c = cursor
    def cursor(self):
        return self._c
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _dir_minimo(tmp_path):
    d = tmp_path / "db"
    d.mkdir()
    (d / sn.SCRIPTS[0]).write_text("SELECT 1\nGO\nSELECT 2\nGO\nSELECT 3\nGO\n", encoding="utf-8")
    (d / sn.SCRIPTS[1]).write_text("SELECT 4\nGO\n", encoding="utf-8")
    return d


def test_execucao_cria_base_e_utilizador_e_corre_os_lotes(tmp_path):
    cur = _Cursor()
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=_dir_minimo(tmp_path), dry_run=False,
                      connect=lambda s, b, t: _Conn(cur), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.resultado == "ok" and rel.base_criada is True and rel.utilizador_criado is True
    assert "CREATE DATABASE [WatcherDB]" in cur.exec and "CREATE USER [watcherdb] FOR LOGIN [watcherdb]" in cur.exec
    feitos = [p for p in rel.passos if p.existe]
    assert [(p.script, p.lotes_ok, p.estado) for p in feitos] == [(sn.SCRIPTS[0], 3, "ok"), (sn.SCRIPTS[1], 1, "ok")]
    assert all(p.estado == "saltado" for p in rel.passos if not p.existe)


def test_estrito_para_no_primeiro_erro_e_sanitiza(tmp_path):
    cur = _Cursor(falhar_no_lote=2)
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=_dir_minimo(tmp_path), dry_run=False,
                      connect=lambda s, b, t: _Conn(cur), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.resultado == "falhou"
    p0 = rel.passos[0]
    assert p0.estado == "falhou" and p0.erro.startswith("lote 2/3:") and "segredo" not in p0.erro and "PWD=***" in p0.erro
    assert rel.passos[1].estado == "dry-run"   # nunca chegou a correr
    assert "SELECT 4" not in cur.exec


def test_continue_on_error_segue_para_o_proximo_script(tmp_path):
    cur = _Cursor(falhar_no_lote=2)
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=_dir_minimo(tmp_path), dry_run=False, continue_on_error=True,
                      connect=lambda s, b, t: _Conn(cur), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.resultado == "falhou" and rel.passos[0].estado == "falhou" and rel.passos[1].estado == "ok"
    assert "SELECT 4" in cur.exec


def test_login_inexistente_avisa_e_nao_cria_utilizador(tmp_path):
    cur = _Cursor(login_existe=False)
    avisos = []
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=_dir_minimo(tmp_path), dry_run=False,
                      connect=lambda s, b, t: _Conn(cur), log=avisos.append, relatorio_path=tmp_path / "r.json")
    assert rel.login_existe is False and rel.utilizador_criado is False
    assert not any(e.startswith("CREATE USER") for e in cur.exec)
    assert any("nao existe no servidor" in a for a in avisos)


def test_nome_invalido_nunca_chega_ao_sql(tmp_path):
    with pytest.raises(sn.NomeInvalido):
        ds.executar("SRV", "x]; DROP", "watcherdb", sql_dir=_dir_minimo(tmp_path), dry_run=True, log=lambda s: None)


# ------------------------------------------------------------------ cli e dispatcher
def test_cli_omissoes_e_dry_run(tmp_path, monkeypatch, capsys):
    chamadas = {}
    monkeypatch.setattr(ds, "executar", lambda *a, **k: chamadas.update(a=a, k=k) or ds.Relatorio("S", "B", "L", "i", True, "t", resultado="dry-run"))
    rc = cli.main(["setup-database", "--server", "SRV"])
    assert rc == 0 and chamadas["a"] == ("SRV", OMISSAO_BASE_INSTALADOR, OMISSAO_LOGIN_INSTALADOR) and chamadas["k"]["dry_run"] is True


def test_cli_nome_invalido_da_2(capsys):
    assert cli.main(["setup-database", "--server", "S", "--database", "mau nome"]) == 2
    assert "nome da base" in capsys.readouterr().err


def test_cli_install_help_lista(capsys):
    assert cli.main(["install-help"]) == 0
    out = capsys.readouterr().out
    assert "setup-database" in out and "provision-login" in out


def test_cli_bootstrap_admin_delega(monkeypatch):
    import tools.bootstrap_admin as ba
    monkeypatch.setattr(ba, "main", lambda argv=None: 7)
    assert cli.main(["bootstrap-admin"]) == 7


def test_dispatcher_do_servico_envia_os_subcomandos_por_import_tardio():
    svc = (ROOT / "watcherdb_service.py").read_text(encoding="utf-8")
    i = svc.index("def main() -> int:")
    corpo = svc[i:i + 2500]
    assert "from watcherdb.install.cli import main as _install_main" in corpo
    assert corpo.index("wrap-master-key") < corpo.index("_install_main") < corpo.index("HandleCommandLine")
    # import tardio: nada de watcherdb.install no topo do ficheiro
    assert "watcherdb.install" not in svc[:i]
