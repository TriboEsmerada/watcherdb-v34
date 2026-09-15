"""
2026-09-15 -- aba Users: sessoes ativas agora e fim do falso "inativo".
"""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as R

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
USERS = (ROOT / "api" / "routers" / "users.py").read_text(encoding="utf-8")
RENDER = PORTAL[PORTAL.index("function renderUsersAnalysis("):PORTAL.index("// JOBS ANALYSIS")]


def test_agregacao_por_login_ordenada_pelo_pedido_mais_recente():
    from api.routers.users import _aggregate_active_sessions as agg
    t = lambda h, m: datetime(2026, 9, 15, h, m)
    linhas = [
        R(login_name="app", host_name="SRV1", program_name="App", sessions=5, connected_since=t(8, 0), last_request=t(9, 10)),
        R(login_name="app", host_name="SRV2", program_name="App", sessions=2, connected_since=t(7, 30), last_request=t(9, 50)),
        R(login_name="dba", host_name="PC9", program_name="SSMS", sessions=1, connected_since=t(9, 40), last_request=t(9, 45)),
        R(login_name="lote", host_name=None, program_name=None, sessions=1, connected_since=t(1, 0), last_request=None),
        R(login_name="", host_name="X", program_name="Y", sessions=3, connected_since=t(1, 0), last_request=t(9, 59)),
    ]
    r = agg(linhas)
    assert [e["login_name"] for e in r] == ["app", "dba", "lote"]
    app = r[0]
    assert app["sessions"] == 7 and app["hosts"] == ["SRV1", "SRV2"] and app["host_count"] == 2
    assert app["connected_since"] == "2026-09-15T07:30:00" and app["last_request"] == "2026-09-15T09:50:00"
    assert r[2]["last_request"] is None and r[2]["hosts"] == []


def test_agregacao_limita_hosts_a_tres_e_linhas_ao_tecto():
    from api.routers.users import _aggregate_active_sessions as agg
    t = datetime(2026, 9, 15, 9, 0)
    linhas = [R(login_name="a", host_name=f"H{i}", program_name="P", sessions=i + 1, connected_since=t, last_request=t) for i in range(5)]
    r = agg(linhas)
    assert r[0]["hosts"] == ["H4", "H3", "H2"] and r[0]["host_count"] == 5
    muitas = [R(login_name=f"l{i}", host_name="h", program_name="p", sessions=1, connected_since=t, last_request=t) for i in range(250)]
    assert len(agg(muitas)) == 200


def test_consulta_so_sessoes_de_utilizador_sem_a_propria_leitura():
    bloco = USERS[USERS.index("# 3b. SESSOES ATIVAS AGORA"):USERS.index("# 4. SENHAS FRACAS")]
    assert "FROM sys.dm_exec_sessions s" in bloco
    assert "s.is_user_process = 1" in bloco and "s.session_id <> @@SPID" in bloco
    assert "'active_sessions': active_sessions," in USERS
    assert "Trusted_Connection" not in USERS


def test_seccao_nova_no_ecra_e_fora_do_relatorio():
    assert "${activeHtml}\n                    ${inactiveHtml}" in PORTAL
    assert 'id="active-section"' in RENDER and "users.active_sessions_empty" in RENDER
    assert "users.active_sessions_ad_note" in RENDER
    relatorio = PORTAL[PORTAL.index("function generateUsersReport("):PORTAL.index("// ======================== TDE RULES")]
    assert "active_sessions" not in relatorio


def test_inativos_sem_promessa_falsa_nem_portugues_fixo():
    assert "30+ dias" not in RENDER
    assert "'Nunca'" not in RENDER and "} dias</td>" not in RENDER
    assert "toLocaleDateString('pt-BR')" not in RENDER[RENDER.index("const inactiveRows"):RENDER.index("inactiveHtml = `")]
    assert "_usrEsc(u.login_name || 'N/A')" in RENDER
    assert "${t('users.no_session_now')}" in RENDER
    assert "sem login recente" not in PORTAL
    assert "Desabilitar ou remover as desnecessarias" not in PORTAL


def test_chaves_nos_tres_idiomas():
    novas = ("no_session_now", "no_session_now_title", "no_session_now_desc", "no_session_now_short", "all_have_session",
             "current_session_since", "days_header", "days_since_creation", "days_since_session", "yes", "no",
             "active_sessions_title", "active_sessions_desc", "active_sessions_ad_note", "active_sessions_empty",
             "sessions", "connected_since", "last_request", "hosts", "programs")
    for loc in ("pt", "en", "es"):
        u = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["users"]
        for k in novas:
            assert u[k], (loc, k)
        assert "{n}" in u["days_since_creation"] and "{n}" in u["days_since_session"], loc
