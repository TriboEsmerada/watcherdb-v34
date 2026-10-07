# -*- coding: utf-8 -*-
"""2026-10-07 -- PROVISION_LOGIN (lote C): login do produto criado/permissionado na frota (auto/manual/dry-run),
rollback so' do que foi criado, preflight por ligacao real, passwords nunca em log/relatorio.

Todas as ligacoes sao falsas (injectadas): nenhum teste toca num SQL Server."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from watcherdb.install import inventory as inv
from watcherdb.install import provision as prov
from watcherdb.install import cli

ROOT = Path(__file__).resolve().parents[2]
SENTINELA = "ZZ_SENTINELA"


def _e(id_, host, inst="I01", ag=None, windows=False, enabled=True):
    return inv.ServerEntry(id_, host, inst, 1433, "", "production", 1, enabled, windows, "" if windows else "watcherdb",
                           "" if windows else inv.PASSWORD_PLACEHOLDER, "SQL Server", bool(ag), ag, None)


ENTRIES = [_e("SQL01_I01", "sql01"), _e("SQL02_AG", "sql02", "AG", ag="AG_Fin"), _e("SQL03_AG", "sql03", "AG", ag="AG_Fin"),
           _e("SQL04_MSSQLSERVER", "sql04", "MSSQLSERVER", windows=True), _e("SQL05_I01", "sql05", enabled=False)]


# ------------------------------------------------------------------ ligacao DBA falsa
class _CursorDBA:
    """Simula master: estado do login por instancia, CREATE LOGIN e lotes de grants."""
    def __init__(self, estado, falhar_grants=False):
        self.estado = estado            # dict partilhado: id -> {"sid": bytes|None} (None = nao existe)
        self.exec = []
        self.falhar_grants = falhar_grants
        self._ultimo = None

    def execute(self, sql, *params):
        self.exec.append((sql, params))
        self._ultimo = sql
        if "CREATE LOGIN" in sql:
            self.estado["sid"] = bytes.fromhex(sql.split("SID = 0x")[1][:32]) if "SID = 0x" in sql else b"\x11" * 16
            self.estado["pw"] = params[0]
            return
        if sql.startswith(("USE master", "GRANT", "IF NOT EXISTS", "USE msdb")) or "GRANT" in sql:
            if self.falhar_grants:
                raise RuntimeError("Cannot find the user 'x'. PWD=segredo")
            return

    def fetchone(self):
        if "sys.server_principals WHERE name" in self._ultimo:
            return None if self.estado.get("sid") is None else (self.estado["sid"],)
        return None

    def nextset(self):
        return False


class _Conn:
    def __init__(self, cur):
        self.cur = cur
    def cursor(self):
        return self.cur
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _fabrica(estados, inalcancaveis=(), auth_fail=(), falhar_grants=()):
    """connect(servidor, db, trust) falso. `estados`: alvo -> dict mutavel."""
    cursores = {}

    def connect(servidor, database, trust):
        if servidor in inalcancaveis:
            raise RuntimeError("[08001] TCP Provider: timeout")
        if servidor in auth_fail:
            raise RuntimeError("[28000] [SQL Server]Login failed for user. (18456)")
        cur = cursores.setdefault(servidor, _CursorDBA(estados.setdefault(servidor, {"sid": None}), falhar_grants=servidor in falhar_grants))
        return _Conn(cur)
    connect.cursores = cursores
    return connect


# ------------------------------------------------------------------ password
def test_password_32_chars_4_classes_charset_seguro():
    for _ in range(50):
        pw = prov.gerar_password()
        assert len(pw) == 32 and re.fullmatch(r"[A-Za-z0-9_-]+", pw)
        assert any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw) and any(c in "-_" for c in pw)


def test_password_por_instancia_partilhada_so_no_mesmo_ag():
    pws = prov.passwords_por_instancia(ENTRIES)
    assert set(pws) == {"SQL01_I01", "SQL02_AG", "SQL03_AG"}       # sem windows, sem disabled
    assert pws["SQL02_AG"] == pws["SQL03_AG"] != pws["SQL01_I01"]


# ------------------------------------------------------------------ provisionar
def test_dry_run_le_o_estado_e_nao_escreve(tmp_path):
    estados = {}
    c = _fabrica(estados)
    rel, criadas = prov.provisionar(ENTRIES, "watcherdb", dry_run=True, connect=c, log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.resultado == "dry-run" and criadas == {}
    assert [r.estado for r in rel.instancias] == ["dry-run"] * 3
    assert "AG_Fin" in rel.instancias[1].detalhe
    assert not any("CREATE LOGIN" in s for cur in c.cursores.values() for s, _ in cur.exec)


def test_execute_exige_confirm_count_igual(tmp_path):
    rel, criadas = prov.provisionar(ENTRIES, "watcherdb", dry_run=False, confirm_count=2, connect=_fabrica({}), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.resultado == "recusado" and criadas == {} and rel.instancias == []


def test_execute_cria_login_grants_sid_por_ag_e_passwords_fora_do_relatorio(tmp_path):
    estados = {}
    c = _fabrica(estados)
    linhas = []
    pws = {"SQL01_I01": SENTINELA + "1", "SQL02_AG": SENTINELA + "2", "SQL03_AG": SENTINELA + "2"}
    rel, criadas = prov.provisionar(ENTRIES, "watcherdb", dry_run=False, confirm_count=3, connect=c, passwords=pws,
                                    log=linhas.append, relatorio_path=tmp_path / "r.json")
    assert rel.resultado == "ok" and [r.estado for r in rel.instancias] == ["criado"] * 3
    assert all(r.created and r.grants_ok for r in rel.instancias)
    assert criadas == pws
    # SID fixo so' no AG: as duas replicas partilham-no; o standalone nao leva SID
    sid02 = estados["sql02\\AG"]["sid"]; sid03 = estados["sql03\\AG"]["sid"]
    assert sid02 == sid03 and len(sid02) == 16 and estados["sql01\\I01"]["sid"] == b"\x11" * 16
    assert rel.instancias[1].sid_prefixo == sid02[:4].hex().upper()
    # a password foi parametrizada (nunca concatenada no SQL) e nunca aparece em log nem relatorio
    cria = [s for s, p in c.cursores["sql01\\I01"].exec if "CREATE LOGIN" in s]
    assert cria and SENTINELA not in cria[0] and estados["sql01\\I01"]["pw"] == SENTINELA + "1"
    texto = "\n".join(linhas) + (tmp_path / "r.json").read_text(encoding="utf-8")
    assert SENTINELA not in texto
    # grants aplicados: lotes do corpo com o login substituido
    grants = [s for s, _ in c.cursores["sql01\\I01"].exec if "GRANT VIEW SERVER STATE" in s]
    assert grants and "[watcherdb]" in grants[0] and "sql_monitoring" not in grants[0]


def test_login_existente_nao_e_tocado_sem_adopt_e_adoptado_com(tmp_path):
    estados = {"sql01\\I01": {"sid": b"\x22" * 16}}
    rel, criadas = prov.provisionar([ENTRIES[0]], "watcherdb", dry_run=False, confirm_count=1, connect=_fabrica(estados), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.instancias[0].estado == "ja_existia" and not rel.instancias[0].created and criadas == {}
    c = _fabrica(estados)
    rel2, criadas2 = prov.provisionar([ENTRIES[0]], "watcherdb", dry_run=False, confirm_count=1, adopt=True, connect=c, log=lambda s: None, relatorio_path=tmp_path / "r2.json")
    assert rel2.instancias[0].estado == "adoptado" and not rel2.instancias[0].created and criadas2 == {}
    assert not any("CREATE LOGIN" in s for s, _ in c.cursores["sql01\\I01"].exec)
    assert any("GRANT VIEW SERVER STATE" in s for s, _ in c.cursores["sql01\\I01"].exec)


def test_sid_diferente_do_ag_nao_altera_e_avisa(tmp_path):
    sids = {"AG_Fin": "0x" + "AA" * 16}
    estados = {"sql02\\AG": {"sid": b"\xbb" * 16}}
    rel, _ = prov.provisionar([ENTRIES[1]], "watcherdb", dry_run=False, confirm_count=1, adopt=True, sids=sids, connect=_fabrica(estados), log=lambda s: None, relatorio_path=tmp_path / "r.json")
    r = rel.instancias[0]
    assert r.estado == "ja_existia_sid_diferente" and "orfaos" in r.detalhe and estados["sql02\\AG"]["sid"] == b"\xbb" * 16


def test_inalcancavel_nao_aborta_e_falhas_de_auth_param(tmp_path):
    c = _fabrica({}, inalcancaveis=("sql01\\I01",))
    rel, _ = prov.provisionar(ENTRIES, "watcherdb", dry_run=False, confirm_count=3, connect=c, log=lambda s: None, relatorio_path=tmp_path / "r.json")
    assert rel.instancias[0].estado == "inalcancavel" and [r.estado for r in rel.instancias[1:]] == ["criado", "criado"]
    assert rel.resultado == "parcial"
    muitos = [_e(f"SQL{i}_I01", f"sql{i}") for i in range(10, 16)]
    c2 = _fabrica({}, auth_fail={f"sql{i}\\I01" for i in range(10, 16)})
    rel2, _ = prov.provisionar(muitos, "watcherdb", dry_run=False, confirm_count=6, connect=c2, max_falhas_auth=3, log=lambda s: None, relatorio_path=tmp_path / "r2.json")
    assert rel2.resultado == "parado_por_autenticacao" and len(rel2.instancias) == 3


def test_erro_nos_grants_fica_criado_para_rollback_e_sanitizado(tmp_path):
    c = _fabrica({}, falhar_grants=("sql01\\I01",))
    rel, criadas = prov.provisionar([ENTRIES[0]], "watcherdb", dry_run=False, confirm_count=1, connect=c, log=lambda s: None, relatorio_path=tmp_path / "r.json")
    r = rel.instancias[0]
    assert r.estado == "falhou" and r.created is True and "PWD=***" in r.detalhe and "segredo" not in r.detalhe
    assert "SQL01_I01" in criadas and rel.resultado == "parcial"


# ------------------------------------------------------------------ rollback
def test_rollback_so_onde_created(tmp_path):
    estados = {"sql01\\I01": {"sid": b"\x11" * 16}, "sql02\\AG": {"sid": b"\x22" * 16}}
    c = _fabrica(estados)
    rel = {"instancias": [{"id": "SQL01_I01", "alvo": "sql01\\I01", "created": True}, {"id": "SQL02_AG", "alvo": "sql02\\AG", "created": False}]}
    res = prov.rollback(rel, "watcherdb", connect=c, log=lambda s: None)
    assert res == [("SQL01_I01", "removido")]
    assert any("DROP LOGIN [watcherdb]" in s for s, _ in c.cursores["sql01\\I01"].exec) and "sql02\\AG" not in c.cursores


# ------------------------------------------------------------------ preflight
class _CursorLogin:
    def __init__(self, row, perms, roles):
        self.row, self.perms, self.roles = row, perms, roles
        self._q = None
    def execute(self, sql, *p):
        self._q = sql
    def fetchone(self):
        return self.row
    def fetchall(self):
        return [(p,) for p in self.perms] if "fn_my_permissions" in self._q else [(r,) for r in self.roles]
    def nextset(self):
        return False


def _fab_login(por_alvo, falhas=None):
    falhas = falhas or {}

    def connect(servidor, database, login, password, trust):
        if servidor in falhas:
            raise RuntimeError(falhas[servidor])
        row, perms, roles = por_alvo[servidor]
        return _Conn(_CursorLogin(row, perms, roles))
    return connect


OK_ROW = ("watcherdb", 0, 1, 1, 1, 1, 1, 1)
OK_PERMS = ["CONNECT SQL", "VIEW SERVER STATE", "VIEW ANY DEFINITION", "VIEW ANY DATABASE"]


def test_preflight_passa_falha_sysadmin_extras_faltas_e_classifica_erros():
    por = {
        "sql01\\I01": (OK_ROW, OK_PERMS, []),
        "sql02\\AG": (("watcherdb", 1, 1, 1, 1, 1, 1, 1), OK_PERMS, ["sysadmin"]),
        "sql03\\AG": (OK_ROW, OK_PERMS + ["CONTROL SERVER"], []),
        "sql10\\I01": (("watcherdb", 0, 1, 0, 1, 1, 1, 0), OK_PERMS, []),
    }
    ents = ENTRIES[:3] + [_e("SQL10_I01", "sql10"), _e("SQL11_I01", "sql11"), _e("SQL12_I01", "sql12")]
    pws = {e.id: "x" for e in ents}
    del pws["SQL12_I01"]
    c = _fab_login(por, falhas={"sql11\\I01": "[28000] Login failed for user 'watcherdb'. (18456) State: 8"})
    res = prov.preflight(ents, "watcherdb", pws, connect=c, log=lambda s: None)
    por_id = {r.id: r for r in res}
    assert por_id["SQL01_I01"].passou
    assert not por_id["SQL02_AG"].passou and "sysadmin" in por_id["SQL02_AG"].motivo and "role:sysadmin" in por_id["SQL02_AG"].extras
    assert not por_id["SQL03_AG"].passou and "CONTROL SERVER" in por_id["SQL03_AG"].motivo
    assert not por_id["SQL10_I01"].passou and "VIEW ANY DEFINITION" in por_id["SQL10_I01"].motivo and por_id["SQL10_I01"].errorlog == "omitido"
    assert por_id["SQL11_I01"].motivo == "password errada (18456/8)"
    assert "sem password" in por_id["SQL12_I01"].motivo
    assert prov.exit_code_preflight(res) == 1          # ha' sysadmin/extras
    assert prov.exit_code_preflight([por_id["SQL01_I01"], por_id["SQL10_I01"]]) == 2
    assert prov.exit_code_preflight([por_id["SQL01_I01"]]) == 0


def test_preflight_errorlog_obrigatorio_quando_pedido():
    por = {"sql01\\I01": (("watcherdb", 0, 1, 1, 1, 1, 1, 0), OK_PERMS, [])}
    res = prov.preflight([ENTRIES[0]], "watcherdb", {"SQL01_I01": "x"}, connect=_fab_login(por), log=lambda s: None, exigir_errorlog=True)
    assert not res[0].passou and "xp_readerrorlog" in res[0].motivo and res[0].errorlog == "falta"


# ------------------------------------------------------------------ servers.json: passwords cifradas
def test_guardar_e_ler_passwords_cifradas(tmp_path):
    p = tmp_path / "servers.json"
    inv.write_servers_json(p, inv.build_master_server("M"), ENTRIES)
    n = prov.guardar_passwords_cifradas(p, {"sql01_i01": "pw1", "SQL02_AG": "pw2"}, cifrar=lambda s: "encrypted:" + s[::-1])
    assert n == 2
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["monitored_servers"][0]["password"] == "encrypted:1wp" and doc["monitored_servers"][2]["password"] == inv.PASSWORD_PLACEHOLDER
    lidas = prov.ler_passwords_cifradas(p, decifrar=lambda v: v[len("encrypted:"):][::-1])
    assert lidas == {"SQL01_I01": "pw1", "SQL02_AG": "pw2"}      # placeholder e windows ficam de fora


# ------------------------------------------------------------------ cli
def test_cli_manual_e_a_omissao_e_nao_liga(tmp_path, capsys):
    p = tmp_path / "servers.json"
    inv.write_servers_json(p, inv.build_master_server("M"), ENTRIES)
    assert cli.main(["provision-login", "--inventory", str(p), "--login", "watcherdb"]) == 0
    out = capsys.readouterr().out
    assert "MANUAL" in out and "3 instancias" in out and "preflight-fleet" in out


def test_cli_auto_execute_recusa_sem_master_key(tmp_path, monkeypatch, capsys):
    p = tmp_path / "servers.json"
    inv.write_servers_json(p, inv.build_master_server("M"), ENTRIES)
    monkeypatch.setattr(cli, "_cifrar_decifrar", lambda: (None, None))
    assert cli.main(["provision-login", "--inventory", str(p), "--mode", "auto", "--execute", "--confirm-count", "3"]) == 2
    assert "master key" in capsys.readouterr().err


def test_cli_auto_dry_run_com_ligacao_falsa(tmp_path, monkeypatch, capsys):
    p = tmp_path / "servers.json"
    inv.write_servers_json(p, inv.build_master_server("M"), ENTRIES)
    monkeypatch.setattr(cli, "_cifrar_decifrar", lambda: (None, None))
    monkeypatch.setattr(prov, "connect_dba", _fabrica({}))
    assert cli.main(["provision-login", "--inventory", str(p), "--mode", "auto", "--report", str(tmp_path / "r.json")]) == 0
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["dry_run"] is True


def test_cli_preflight_escreve_rollout_so_com_quem_passou(tmp_path, monkeypatch, capsys):
    p = tmp_path / "servers.json"
    inv.write_servers_json(p, inv.build_master_server("M"), ENTRIES)
    prov.guardar_passwords_cifradas(p, {"SQL01_I01": "a", "SQL02_AG": "b", "SQL03_AG": "b"}, cifrar=lambda s: "encrypted:" + s)
    monkeypatch.setattr(cli, "_cifrar_decifrar", lambda: (None, lambda v: v[len("encrypted:"):]))
    por = {"sql01\\I01": (OK_ROW, OK_PERMS, []), "sql02\\AG": (OK_ROW, OK_PERMS, []), "sql03\\AG": (("w", 0, 0, 1, 1, 1, 1, 1), OK_PERMS, [])}
    monkeypatch.setattr(prov, "connect_login", _fab_login(por))
    rc = cli.main(["preflight-fleet", "--inventory", str(p), "--login", "watcherdb", "--rollout", str(tmp_path / "roll.json")])
    assert rc == 2
    roll = json.loads((tmp_path / "roll.json").read_text(encoding="utf-8"))
    assert roll["sql_auth_servers"] == ["SQL01_I01", "SQL02_AG"] and roll["_gerado"]["origem"] == "preflight-fleet"


def test_cli_rollback_usa_o_relatorio(tmp_path, monkeypatch):
    rel = {"instancias": [{"id": "SQL01_I01", "alvo": "sql01\\I01", "created": True}]}
    (tmp_path / "r.json").write_text(json.dumps(rel), encoding="utf-8")
    monkeypatch.setattr(prov, "connect_dba", _fabrica({"sql01\\I01": {"sid": b"\x11" * 16}}))
    assert cli.main(["provision-rollback", "--report", str(tmp_path / "r.json"), "--login", "watcherdb"]) == 0


def test_condicao_8_jobs_py_nao_executa_mutacoes_de_jobs():
    txt = (ROOT / "api" / "routers" / "jobs.py").read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"sp_(update_job|add_jobstep|start_job|delete_job)", txt):
        antes = txt[max(0, m.start() - 400):m.start()]
        assert "execute(" not in antes.rsplit("\n", 8)[-1] if "\n" in antes else True
    assert "cursor.execute(f\"EXEC msdb.dbo.sp_update_job" not in txt and "execute(\"EXEC msdb.dbo.sp_start_job" not in txt


def test_dispatcher_e_help():
    svc = (ROOT / "watcherdb_service.py").read_text(encoding="utf-8")
    assert '"provision-login", "provision-rollback", "preflight-fleet"' in svc
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert cli.main(["install-help"]) == 0
    assert "provision-login" in buf.getvalue() and "preflight-fleet" in buf.getvalue()
