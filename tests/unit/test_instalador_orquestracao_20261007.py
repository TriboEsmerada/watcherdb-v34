# -*- coding: utf-8 -*-
"""2026-10-07 -- INSTALADOR_ORQUESTRACAO (lote E): configure/.env explicito, setup-database --create-login,
install.ps1 a orquestrar os subcomandos (f1-f4, k2, -DryRun), preflight/setup_database sem 8433/V3.3 fixos."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from watcherdb.install import envfile, cli
from watcherdb.install import dbsetup as ds

ROOT = Path(__file__).resolve().parents[2]
INSTALL = (ROOT / "deploy" / "install.ps1").read_text(encoding="utf-8").replace("\r\n", "\n")
PREFLIGHT = (ROOT / "deploy" / "preflight_target.ps1").read_text(encoding="utf-8").replace("\r\n", "\n")
SETUPDB = (ROOT / "deploy" / "setup_database.ps1").read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


# ------------------------------------------------------------------ envfile
def test_env_novo_escreve_chaves_explicitas_e_jwt(tmp_path):
    p = tmp_path / ".env"
    res = envfile.escrever_env(p, {"INTELLIGENCE_DATABASE": "WatcherDB", "INTELLIGENCE_SQL_USER": "watcherdb"},
                               segredos={"INTELLIGENCE_SQL_PASSWORD": "pw"}, cifrar=lambda s: "encrypted:" + s[::-1])
    txt = p.read_text(encoding="utf-8")
    assert "INTELLIGENCE_DATABASE=WatcherDB\n" in txt and "INTELLIGENCE_SQL_USER=watcherdb\n" in txt
    assert "INTELLIGENCE_SQL_PASSWORD=encrypted:wp\n" in txt and "pw\n" not in txt.replace("encrypted:wp", "")
    jwt = re.search(r"^JWT_SECRET_KEY=([0-9a-f]{64})$", txt, re.M)
    assert jwt and set(res["escritas"]) >= {"INTELLIGENCE_DATABASE", "INTELLIGENCE_SQL_PASSWORD", "JWT_SECRET_KEY"}


def test_env_existente_mantem_chaves_e_jwt_salvo_force(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comentario\nINTELLIGENCE_DATABASE=Antiga\nJWT_SECRET_KEY=abc\nOUTRA=1\n", encoding="utf-8")
    res = envfile.escrever_env(p, {"INTELLIGENCE_DATABASE": "Nova", "WATCHERDB_PORT": "8434"})
    txt = p.read_text(encoding="utf-8")
    assert "INTELLIGENCE_DATABASE=Antiga" in txt and "JWT_SECRET_KEY=abc" in txt and "WATCHERDB_PORT=8434" in txt and "# comentario" in txt
    assert res["mantidas"] == ["INTELLIGENCE_DATABASE"] and "WATCHERDB_PORT" in res["escritas"] and "JWT_SECRET_KEY" not in res["escritas"]
    envfile.escrever_env(p, {"INTELLIGENCE_DATABASE": "Nova"}, force=True)
    assert "INTELLIGENCE_DATABASE=Nova" in p.read_text(encoding="utf-8")


def test_env_preview_nao_escreve_e_segredo_sem_cifra_e_erro(tmp_path):
    p = tmp_path / ".env"
    res = envfile.escrever_env(p, {"A": "1"}, preview=True)
    assert not p.exists() and res["preview"] is True and "A" in res["escritas"]
    with pytest.raises(ValueError):
        envfile.escrever_env(p, {}, segredos={"INTELLIGENCE_SQL_PASSWORD": "x"})


# ------------------------------------------------------------------ setup-database --create-login
class _Cur:
    def __init__(self):
        self.exec = []
        self._ultimo = ""
        self.login_existe = False
    def execute(self, sql, *p):
        self.exec.append((sql, p)); self._ultimo = sql
        if "CREATE LOGIN" in sql:
            self.login_existe = True
    def fetchone(self):
        if self._ultimo.startswith("SELECT DB_ID"):
            return (5,)
        if "sys.server_principals" in self._ultimo:
            return (1,) if self.login_existe else None
        if "sys.database_principals" in self._ultimo:
            return None
        return None
    def nextset(self):
        return False


class _Conn:
    def __init__(self, c): self.c = c
    def cursor(self): return self.c
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_setup_database_cria_o_login_parametrizado_quando_pedido(tmp_path):
    d = tmp_path / "db"; d.mkdir()
    (d / ds.SCRIPTS[0]).write_text("SELECT 1\nGO\n", encoding="utf-8")
    cur = _Cur()
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=d, dry_run=False, login_password="ZZ_SENT",
                      connect=lambda s, b, t: _Conn(cur), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    cria = [(s, p) for s, p in cur.exec if "CREATE LOGIN" in s]
    assert cria and "ZZ_SENT" not in cria[0][0] and cria[0][1] == ("ZZ_SENT",)
    assert rel.login_criado is True and rel.login_existe is True and rel.utilizador_criado is True
    assert "ZZ_SENT" not in (tmp_path / "r.json").read_text(encoding="utf-8")


def test_setup_database_sem_password_nao_cria_login(tmp_path):
    d = tmp_path / "db"; d.mkdir()
    (d / ds.SCRIPTS[0]).write_text("SELECT 1\nGO\n", encoding="utf-8")
    cur = _Cur()
    rel = ds.executar("SRV", "WatcherDB", "watcherdb", sql_dir=d, dry_run=False,
                      connect=lambda s, b, t: _Conn(cur), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert not any("CREATE LOGIN" in s for s, _ in cur.exec) and rel.login_criado is False and rel.login_existe is False


def test_cli_setup_database_create_login_exige_a_variavel(monkeypatch, capsys):
    monkeypatch.delenv(cli.VAR_PASSWORD_LOGIN, raising=False)
    assert cli.main(["setup-database", "--server", "S", "--create-login"]) == 2
    assert cli.VAR_PASSWORD_LOGIN in capsys.readouterr().err


# ------------------------------------------------------------------ cli configure
def test_cli_configure_escreve_env_explicito_com_password_cifrada(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(cli.VAR_PASSWORD_LOGIN, "segredo")
    monkeypatch.setattr(cli, "_cifrar_decifrar", lambda: (lambda s: "encrypted:" + s.upper(), None))
    rc = cli.main(["configure", "--data-dir", str(tmp_path), "--server", "SRV\\I01", "--database", "WatcherDB", "--login", "watcherdb", "--port", "8434"])
    assert rc == 0
    txt = (tmp_path / ".env").read_text(encoding="utf-8")
    for esperado in ("WATCHERDB_PORT=8434", "WATCHERDB_EDITION=standard", "INTELLIGENCE_SERVER=SRV\\I01", "INTELLIGENCE_DATABASE=WatcherDB",
                     "INTELLIGENCE_SQL_USER=watcherdb", "INTELLIGENCE_SQL_PASSWORD=encrypted:SEGREDO", "INTELLIGENCE_USE_WINDOWS_AUTH=false"):
        assert esperado in txt
    assert "segredo" not in txt and re.search(r"^JWT_SECRET_KEY=[0-9a-f]{64}$", txt, re.M)


def test_cli_configure_sem_master_key_com_password_da_2_e_preview_nao_escreve(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(cli.VAR_PASSWORD_LOGIN, "segredo")
    monkeypatch.setattr(cli, "_cifrar_decifrar", lambda: (None, None))
    assert cli.main(["configure", "--data-dir", str(tmp_path), "--server", "S"]) == 2
    assert "master key" in capsys.readouterr().err
    assert cli.main(["configure", "--data-dir", str(tmp_path), "--server", "S", "--preview"]) == 0
    assert not (tmp_path / ".env").exists()


def test_cli_configure_sem_password_escreve_o_resto(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(cli.VAR_PASSWORD_LOGIN, raising=False)
    assert cli.main(["configure", "--data-dir", str(tmp_path), "--server", "S"]) == 0
    txt = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "INTELLIGENCE_SQL_PASSWORD" not in txt and "INTELLIGENCE_DATABASE=WatcherDB" in txt
    assert "nao definida" in capsys.readouterr().out


# ------------------------------------------------------------------ install.ps1 / preflight / setup_database (pins)
def test_install_ps1_tem_os_parametros_novos():
    for p in ("[string]$Database = 'WatcherDB'", "[string]$SqlLogin = 'watcherdb'", "[SecureString]$SqlLoginPassword",
              "[string]$InventoryPath = ''", "[ValidateSet('Auto','Manual','Skip')]", "[string]$ProvisionMode = 'Manual'",
              "[switch]$SkipDatabaseSetup", "[switch]$DryRun"):
        assert p in INSTALL, p


def test_install_ps1_orquestra_na_ordem_decidida():
    ordem = ["PASSO (f): master key", "PASSO (f1): inventario", "PASSO (f2): base", "PASSO (f3): login", "PASSO (f4): .env",
             "PASSO (g): license.dat", "PASSO (k): arranque", "PASSO (k2): preflight-fleet", "PASSO (l): registo HKLM"]
    pos = [INSTALL.index(x) for x in ordem]
    assert pos == sorted(pos), "a ordem dos passos no install.ps1 nao e' a decidida"


def test_install_ps1_passa_a_password_so_por_variavel_transitoria_e_limpa():
    bloco = INSTALL[INSTALL.index("PASSOS (f1..f4)"):INSTALL.index("PASSO (g)")]
    assert bloco.count("$env:WATCHERDB_LOGIN_PASSWORD = $loginPwdPlain") == 2
    assert bloco.count("Remove-Item Env:WATCHERDB_LOGIN_PASSWORD") == 2
    assert "ZeroFreeBSTR" in bloco and "$loginPwdPlain = $null" in bloco
    assert "--confirm-count" in bloco and "--execute" in bloco and "-DryRun" in bloco or "$DryRun" in bloco


def test_install_ps1_verifica_acl_e_dry_run_termina_antes_da_licenca():
    bloco = INSTALL[INSTALL.index("PASSO (f4)"):INSTALL.index("PASSO (g)")]
    assert "Get-Acl" in bloco and "Everyone" in bloco and "exit 7" in bloco
    assert "if ($DryRun)" in bloco and "exit 0" in bloco


def test_install_ps1_preflight_fleet_so_falha_em_auto():
    bloco = INSTALL[INSTALL.index("PASSO (k2)"):INSTALL.index("PASSO (l)")]
    assert "preflight-fleet" in bloco and "exit 8" in bloco and "'Auto'" in bloco


def test_sem_v33_nem_8433_fixos_nos_scripts_de_instalacao():
    assert "V3.3" not in INSTALL
    assert "8433" not in PREFLIGHT and "WatcherDBWebServiceV33" not in PREFLIGHT and "msiexec" not in PREFLIGHT
    assert "[int]$WebPort" in PREFLIGHT and "[string]$ServiceName" in PREFLIGHT and "[string]$SqlLogin" in PREFLIGHT
    assert "sql_monitoring" not in PREFLIGHT
    assert "WatcherDBWebServiceV33" not in SETUPDB and "V3.3" not in SETUPDB


def test_install_ps1_envia_porta_servico_e_login_ao_preflight():
    assert "$preflightArgs = @{ SqlServer = $SqlServer; WebPort = $WebPort; ServiceName = $ServiceName; SqlLogin = $SqlLogin }" in INSTALL


def test_dispatcher_inclui_configure():
    svc = (ROOT / "watcherdb_service.py").read_text(encoding="utf-8")
    assert '"configure"' in svc
