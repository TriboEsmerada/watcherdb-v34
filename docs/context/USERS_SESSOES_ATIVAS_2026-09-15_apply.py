# -*- coding: utf-8 -*-
"""Aba Users (2026-09-15) -- sessoes ativas agora, pelo pedido mais recente, e fim do falso "inativo".

Pedido do owner, com a captura da aba Users de SQLHDSPRD212\\I01: "coloque aqui os users mais recentes
tambem, order by acesso mais recente".

Facto medido antes de desenhar (sql_monitoring, so leitura): o SQL Server NAO guarda data de ultimo login.
A seccao "Inactive Users" usava MAX(login_time) de sys.dm_exec_sessions, isto e', so sessoes ligadas agora.
Em SQLHDSPRD212 ha 158 logins e 136 sem sessao neste momento: sao praticamente os 135 "inativos". "Nunca"
queria dizer "sem sessao agora", os dias contavam desde a criacao, e o texto prometia "30+ dias" ao lado
de logins com 6 e 21. A Intelligence nao tem historico de acessos por login.

Parecer da persona DBA cliente (consenso com ajustes, todos incorporados):
  - Seccao nova "Sessoes ativas agora", nunca "Acessos recentes" (induz historico). Rotulo no cabecalho.
  - Hosts e programas sim (separam a aplicacao de alguem em SSMS), mas so no ecra: nao entram no relatorio.
  - Cartao e seccao dos "inativos" mudam de texto ja, com o numero intacto.
  - Nota: grupos do AD nunca aparecem em sessoes (a sessao regista o login individual).
  - Estado vazio explicito fora de horas.
  - Portugues fixo (Nunca, dias, SIM/NAO, datas pt-BR) passa a traducao nas linhas tocadas.
Achado extra: o relatorio recomendava desabilitar estas contas como inativas. Passa a avisar que sem sessao
agora nao prova inatividade.

Inatividade verdadeira (recolha periodica de sessoes para a Intelligence) fica como decisao de produto do
owner: base partilhada, canonico e veto do guardiao do recolhedor. Este lote nao muda a base de dados.

Backend: api/routers/users.py devolve active_sessions (identidade sql_monitoring, leitura de
sys.dm_exec_sessions na instancia, exclui a propria sessao da leitura).

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/USERS_SESSOES_ATIVAS_2026-09-15_apply.py --check
  py docs/context/USERS_SESSOES_ATIVAS_2026-09-15_apply.py
  py -m pytest tests/unit/test_users_sessoes_ativas_20260915.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; abrir a aba Users (a cache da aba pode servir a versao antiga uns minutos)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "users": Path("api/routers/users.py"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "ptbr": Path("static/i18n/pt-BR.json"),
    "doc": Path("docs/features/USERS_TAB_IMPLEMENTADO.md"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_users_sessoes_ativas_20260915.py"),
}
MARK = "_aggregate_active_sessions"

# ---------------------------------------------------------------- backend
AGG_FN = '''def _aggregate_active_sessions(rows, limit: int = 200) -> List[Dict[str, Any]]:
    """Sessoes de utilizador ligadas AGORA, agregadas por login, do pedido mais recente para o mais antigo.

    2026-09-15 (pedido do owner). O SQL Server nao guarda data de ultimo login: isto e' o estado de
    sys.dm_exec_sessions no momento da leitura, nunca historico. Cada linha de entrada e' um grupo
    (login_name, host_name, program_name) com sessions, connected_since e last_request.
    """
    por_login: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        login = (getattr(r, "login_name", None) or "").strip()
        if not login:
            continue
        e = por_login.setdefault(login, {"login_name": login, "sessions": 0, "connected_since": None,
                                         "last_request": None, "_hosts": {}, "_programs": {}})
        n = int(getattr(r, "sessions", 0) or 0)
        e["sessions"] += n
        cs, lr = getattr(r, "connected_since", None), getattr(r, "last_request", None)
        if cs is not None and (e["connected_since"] is None or cs < e["connected_since"]):
            e["connected_since"] = cs
        if lr is not None and (e["last_request"] is None or lr > e["last_request"]):
            e["last_request"] = lr
        host = (getattr(r, "host_name", None) or "").strip()
        prog = (getattr(r, "program_name", None) or "").strip()
        if host:
            e["_hosts"][host] = e["_hosts"].get(host, 0) + n
        if prog:
            e["_programs"][prog] = e["_programs"].get(prog, 0) + n
    saida = []
    for e in por_login.values():
        hosts = sorted(e.pop("_hosts").items(), key=lambda kv: (-kv[1], kv[0]))
        progs = sorted(e.pop("_programs").items(), key=lambda kv: (-kv[1], kv[0]))
        e["hosts"] = [h for h, _ in hosts[:3]]
        e["host_count"] = len(hosts)
        e["programs"] = [p for p, _ in progs[:2]]
        saida.append(e)
    # pedido mais recente primeiro; sem data vai para o fim
    saida.sort(key=lambda e: e["last_request"] or datetime.min, reverse=True)
    saida = saida[:limit]
    for e in saida:
        for k in ("connected_since", "last_request"):
            if e[k] is not None:
                e[k] = e[k].isoformat()
    return saida


'''

ACTIVE_BLOCK = '''        # 3b. SESSOES ATIVAS AGORA (2026-09-15, pedido do owner). O SQL Server nao guarda o ultimo login:
        # isto e' so' o que esta ligado no momento da leitura. A propria sessao desta leitura fica de fora.
        active_query = """
        SELECT
            s.login_name,
            s.host_name,
            s.program_name,
            COUNT(*) AS sessions,
            MIN(s.login_time) AS connected_since,
            MAX(s.last_request_start_time) AS last_request
        FROM sys.dm_exec_sessions s
        WHERE s.is_user_process = 1
            AND s.session_id <> @@SPID
        GROUP BY s.login_name, s.host_name, s.program_name
        """

        cursor.execute(active_query)
        active_sessions = _aggregate_active_sessions(cursor.fetchall())

'''

USERS_EDITS = [
    ("from typing import Dict, Any, List\n",
     "from typing import Dict, Any, List\nfrom datetime import datetime\n", 1),
    ('@router.get("/server/{server_id}", response_model=GenericResponse)\nasync def get_users_analysis(',
     AGG_FN + '@router.get("/server/{server_id}", response_model=GenericResponse)\nasync def get_users_analysis(', 1),
    ("    - inactive_users: Usuários inativos (30+ dias)\n",
     "    - inactive_users: logins SEM SESSAO LIGADA AGORA (o SQL Server nao guarda o ultimo login; nao e' inatividade provada)\n"
     "    - active_sessions: logins com sessao ligada agora, do pedido mais recente para o mais antigo\n", 1),
    ("        # 4. SENHAS FRACAS (Políticas desabilitadas)\n",
     ACTIVE_BLOCK + "        # 4. SENHAS FRACAS (Políticas desabilitadas)\n", 1),
    ("            'inactive_users': inactive_users,\n            'weak_passwords': weak_passwords,\n",
     "            'inactive_users': inactive_users,\n            'active_sessions': active_sessions,\n"
     "            'weak_passwords': weak_passwords,\n", 1),
]

# ---------------------------------------------------------------- portal
HELPERS_JS = r"""        // 2026-09-15: escape e datas da aba Users (sessoes ativas agora e logins sem sessao)
        function _usrEsc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
        }
        function _usrData(iso, comHora) {
            if (!iso) return '';
            const d = new Date(iso);
            if (isNaN(d.getTime())) return '';
            const lang = document.documentElement.lang || undefined;
            return comHora
                ? d.toLocaleString(lang, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
                : d.toLocaleDateString(lang, { day: '2-digit', month: '2-digit', year: 'numeric' });
        }

"""

CARD_VELHO = "<div style=\"color: var(--color-text-tertiary); font-size: 12px; margin-bottom: 4px;\">${t('users.inactive')}</div>"
CARD_NOVO = "<div style=\"color: var(--color-text-tertiary); font-size: 12px; margin-bottom: 4px;\">${t('users.no_session_now')}</div>"

ROWS_VELHO = """                const inactiveRows = inactive.map(u => `
                    <tr>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.login_name || 'N/A'}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.create_date ? new Date(u.create_date).toLocaleDateString('pt-BR') : 'N/A'}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.last_login_date ? new Date(u.last_login_date).toLocaleDateString('pt-BR') : 'Nunca'}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.days_inactive || 'N/A'} dias</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.is_disabled ? '<span style="color:#ef4444;">SIM</span>' : '<span style="color:#10b981;">NÃO</span>'}</td>
                    </tr>
                `).join('');
"""
ROWS_NOVO = """                const inactiveRows = inactive.map(u => {
                    // 2026-09-15: o SQL Server nao guarda o ultimo login. Sem sessao ligada agora os dias contam desde a
                    // criacao; com sessao (aberta ha mais de 30 dias) contam desde que abriu. Nao e' inatividade provada.
                    const temSessao = !!u.last_login_date;
                    const dias = u.days_inactive == null ? '' : (temSessao
                        ? _kpiTp('users.days_since_session', '{n} (sessão aberta)', { n: u.days_inactive })
                        : _kpiTp('users.days_since_creation', '{n} (desde a criação)', { n: u.days_inactive }));
                    return `
                    <tr>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${_usrEsc(u.login_name || 'N/A')}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.create_date ? _usrData(u.create_date) : 'N/A'}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${temSessao ? _usrData(u.last_login_date) : _usrEsc(t('users.no_session_now_short'))}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${_usrEsc(dias)}</td>
                        <td style="padding: 12px; border-bottom: 1px solid var(--color-border);">${u.is_disabled ? `<span style="color:#ef4444;">${_usrEsc(t('users.yes'))}</span>` : `<span style="color:#10b981;">${_usrEsc(t('users.no'))}</span>`}</td>
                    </tr>
                `;
                }).join('');
"""

HDR_VELHO = "                            <i class=\"fas fa-user-clock\"></i> ${t('users.inactive_users')} (${totalInactive})\n"
HDR_NOVO = "                            <i class=\"fas fa-user-clock\"></i> ${t('users.no_session_now_title')} (${totalInactive})\n"
DESC_VELHO = "                                <i class=\"fas fa-info-circle\"></i> Logins sem atividade recente (30+ dias).\n"
DESC_NOVO = "                                <i class=\"fas fa-info-circle\"></i> ${_usrEsc(t('users.no_session_now_desc'))}\n"
COL_VELHO = ("                                            <th style=\"padding: 12px; border-bottom: 2px solid #fbbf24; color: #fbbf24;\">${t('users.last_login')}</th>\n"
             "                                            <th style=\"padding: 12px; border-bottom: 2px solid #fbbf24; color: #fbbf24;\">${t('users.days_inactive')}</th>\n")
COL_NOVO = ("                                            <th style=\"padding: 12px; border-bottom: 2px solid #fbbf24; color: #fbbf24;\">${t('users.current_session_since')}</th>\n"
            "                                            <th style=\"padding: 12px; border-bottom: 2px solid #fbbf24; color: #fbbf24;\">${t('users.days_header')}</th>\n")
VAZIO_VELHO = ("                        <h4><i class=\"fas fa-check-circle\"></i> ${t('users.inactive_users')}</h4>\n"
               "                        <p style=\"color: #6ee7b7; margin-top: 12px;\">\n"
               "                            <i class=\"fas fa-thumbs-up\"></i> ${t('users.no_inactive')}\n")
VAZIO_NOVO = ("                        <h4><i class=\"fas fa-check-circle\"></i> ${t('users.no_session_now_title')}</h4>\n"
              "                        <p style=\"color: #6ee7b7; margin-top: 12px;\">\n"
              "                            <i class=\"fas fa-thumbs-up\"></i> ${t('users.all_have_session')}\n")

TH = '<th style="padding: 12px; border-bottom: 2px solid #3b82f6; color: #93c5fd;">'
TD = '<td style="padding: 12px; border-bottom: 1px solid var(--color-border);">'
ACTIVE_JS = """            // Seccao Sessoes ativas agora (2026-09-15, pedido do owner). NAO e' historico: e' o que esta ligado no
            // momento da leitura, do pedido mais recente para o mais antigo. So no ecra; nao entra no relatorio.
            let activeHtml = '';
            if (Array.isArray(data.active_sessions)) {
                const ativas = data.active_sessions;
                const activeRows = ativas.map(u => {
                    const hosts = (u.hosts || []).join(', ') + ((u.host_count || 0) > (u.hosts || []).length ? ` +${u.host_count - u.hosts.length}` : '');
                    return `
                    <tr>
                        TD${_usrEsc(u.login_name)}</td>
                        TD${Number(u.sessions) || 0}</td>
                        TD${_usrData(u.connected_since, true)}</td>
                        TD${_usrData(u.last_request, true)}</td>
                        TD${_usrEsc(hosts)}</td>
                        TD${_usrEsc((u.programs || []).join(', '))}</td>
                    </tr>`;
                }).join('');
                const corpo = ativas.length === 0
                    ? `<p style="color: var(--color-text-tertiary);"><i class="fas fa-moon"></i> ${_usrEsc(t('users.active_sessions_empty'))}</p>`
                    : `<div style="max-height: 400px; overflow-y: auto; overflow-x: auto;">
                                <table style="width: 100%; border-collapse: collapse; color: var(--color-text-faint);">
                                    <thead>
                                        <tr style="background: var(--color-bg-sunken); text-align: left; position: sticky; top: 0; z-index: 10;">
                                            TH${t('users.login')}</th>
                                            TH${t('users.sessions')}</th>
                                            TH${t('users.connected_since')}</th>
                                            TH${t('users.last_request')}</th>
                                            TH${t('users.hosts')}</th>
                                            TH${t('users.programs')}</th>
                                        </tr>
                                    </thead>
                                    <tbody>${activeRows}</tbody>
                                </table>
                            </div>`;
                activeHtml = `
                    <div id="active-section" class="card" style="border-left: 4px solid #3b82f6; margin-top: 20px;">
                        <h4 style="cursor: pointer;" onclick="toggleSection('active-section')">
                            <i class="fas fa-plug"></i> ${_usrEsc(t('users.active_sessions_title'))} (${ativas.length})
                            <i class="fas fa-chevron-down" style="float: right; font-size: 14px;"></i>
                        </h4>
                        <div class="section-content" style="margin-top: 16px;">
                            <p style="color: #93c5fd; margin-bottom: 16px;">
                                <i class="fas fa-info-circle"></i> ${_usrEsc(t('users.active_sessions_desc'))}<br>
                                <span style="color: var(--color-text-tertiary);">${_usrEsc(t('users.active_sessions_ad_note'))}</span>
                            </p>
                            ${corpo}
                        </div>
                    </div>
                `;
            }

""".replace("TH", TH).replace("TD", TD)

PORTAL_EDITS = [
    ("        function renderUsersAnalysis(data, serverName, serverId) {\n",
     HELPERS_JS + "        function renderUsersAnalysis(data, serverName, serverId) {\n", 1),
    (CARD_VELHO, CARD_NOVO, 1),
    (ROWS_VELHO, ROWS_NOVO, 1),
    (HDR_VELHO, HDR_NOVO, 1),
    (DESC_VELHO, DESC_NOVO, 1),
    (COL_VELHO, COL_NOVO, 1),
    (VAZIO_VELHO, VAZIO_NOVO, 1),
    ("            // Seção Senhas Fracas\n", ACTIVE_JS + "            // Seção Senhas Fracas\n", 1),
    ("                    ${inactiveHtml}\n                    ${weakPwdHtml}\n",
     "                    ${activeHtml}\n                    ${inactiveHtml}\n                    ${weakPwdHtml}\n", 1),
    # relatorio: deixa de recomendar desabilitar contas com base em "sem sessao agora"
    ("            id: 'USR003', title: 'Utilizadores inactivos',\n",
     "            id: 'USR003', title: 'Logins sem sessao ligada',\n", 1),
    ("return `${inact.length} utilizador(es) sem login recente.`; },\n"
     "            recommendation: 'Rever contas inactivas. Desabilitar ou remover as desnecessarias.',\n",
     "return `${inact.length} login(s) sem sessao ligada no momento da recolha (o SQL Server nao guarda o ultimo login).`; },\n"
     "            recommendation: 'Nao desabilitar com base nesta lista: sem sessao agora nao prova inactividade. Confirmar com auditoria de logins ou com as equipas de aplicacao.',\n", 1),
    ("<div class=\"kpi-value\">${inactive.length}</div><div class=\"kpi-label\">Inativos</div>",
     "<div class=\"kpi-value\">${inactive.length}</div><div class=\"kpi-label\">Sem sessao</div>", 1),
    ("reportSection('fa-user-clock', 'Utilizadores Inactivos (' + inactive.length + ')'",
     "reportSection('fa-user-clock', 'Logins sem sessao ligada (' + inactive.length + ')'", 1),
    ("[{label:'Utilizador',key:'_name'},{label:'Ultimo Login',key:'_lastLogin'},{label:'Dias Inactivo',key:'_days'}]",
     "[{label:'Utilizador',key:'_name'},{label:'Sessao ligada desde',key:'_lastLogin'},{label:'Dias (criacao ou sessao)',key:'_days'}]", 1),
]

# ---------------------------------------------------------------- i18n (bloco users)
USERS_I18N = {
    "pt": {
        "no_session_now": "Sem sessão agora", "no_session_now_title": "Logins sem sessão ligada agora",
        "no_session_now_desc": "O SQL Server não guarda a data do último login. Estes logins não têm sessão ligada neste momento; isso não prova que estejam inativos.",
        "no_session_now_short": "sem sessão agora", "all_have_session": "Todos os logins têm sessão ligada neste momento.",
        "current_session_since": "Sessão ligada desde", "days_header": "Dias",
        "days_since_creation": "{n} (desde a criação)", "days_since_session": "{n} (sessão aberta)",
        "yes": "Sim", "no": "Não",
        "active_sessions_title": "Sessões ativas agora",
        "active_sessions_desc": "Logins com sessão ligada neste momento, do pedido mais recente para o mais antigo. O SQL Server não guarda histórico de logins.",
        "active_sessions_ad_note": "Grupos do AD não aparecem aqui: a sessão regista sempre o login individual.",
        "active_sessions_empty": "0 sessões ativas neste momento.",
        "sessions": "Sessões", "connected_since": "Ligado desde", "last_request": "Último pedido",
        "hosts": "Hosts", "programs": "Programas",
    },
    "en": {
        "no_session_now": "No session now", "no_session_now_title": "Logins with no session right now",
        "no_session_now_desc": "SQL Server does not record the last login date. These logins have no session connected right now; that does not prove they are inactive.",
        "no_session_now_short": "no session now", "all_have_session": "Every login has a session connected right now.",
        "current_session_since": "Session connected since", "days_header": "Days",
        "days_since_creation": "{n} (since creation)", "days_since_session": "{n} (session open)",
        "yes": "Yes", "no": "No",
        "active_sessions_title": "Active sessions now",
        "active_sessions_desc": "Logins with a session connected right now, most recent request first. SQL Server keeps no login history.",
        "active_sessions_ad_note": "AD groups never appear here: a session always records the individual login.",
        "active_sessions_empty": "0 active sessions right now.",
        "sessions": "Sessions", "connected_since": "Connected since", "last_request": "Last request",
        "hosts": "Hosts", "programs": "Programs",
    },
    "es": {
        "no_session_now": "Sin sesión ahora", "no_session_now_title": "Logins sin sesión conectada ahora",
        "no_session_now_desc": "SQL Server no guarda la fecha del último inicio de sesión. Estos logins no tienen sesión conectada en este momento; eso no prueba que estén inactivos.",
        "no_session_now_short": "sin sesión ahora", "all_have_session": "Todos los logins tienen sesión conectada en este momento.",
        "current_session_since": "Sesión conectada desde", "days_header": "Días",
        "days_since_creation": "{n} (desde la creación)", "days_since_session": "{n} (sesión abierta)",
        "yes": "Sí", "no": "No",
        "active_sessions_title": "Sesiones activas ahora",
        "active_sessions_desc": "Logins con sesión conectada en este momento, de la petición más reciente a la más antigua. SQL Server no guarda historial de inicios de sesión.",
        "active_sessions_ad_note": "Los grupos de AD no aparecen aquí: la sesión registra siempre el login individual.",
        "active_sessions_empty": "0 sesiones activas en este momento.",
        "sessions": "Sesiones", "connected_since": "Conectado desde", "last_request": "Última petición",
        "hosts": "Hosts", "programs": "Programas",
    },
}
PTBR_I18N = {
    "no_session_now_title": "Logins sem sessão conectada agora",
    "no_session_now_desc": "O SQL Server não guarda a data do último login. Estes logins não têm sessão conectada neste momento; isso não prova que estejam inativos.",
    "all_have_session": "Todos os logins têm sessão conectada neste momento.",
    "current_session_since": "Sessão conectada desde",
    "active_sessions_desc": "Logins com sessão conectada neste momento, da requisição mais recente para a mais antiga. O SQL Server não guarda histórico de logins.",
    "connected_since": "Conectado desde", "last_request": "Última requisição",
}


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


# ---------------------------------------------------------------- documentacao e changelog
DOC_EDITS = [
    ("Lista logins sem atividade recente (30+ dias).\n",
     "> **Corrigido a 2026-09-15.** O SQL Server não guarda a data do último login. Esta secção usa\n"
     "> `sys.dm_exec_sessions`, portanto lista logins **sem sessão ligada no momento da leitura**, não\n"
     "> inatividade de 30 dias. Em SQLHDSPRD212 eram 136 de 158 logins. No portal chama-se agora \"Logins sem\n"
     "> sessão ligada agora\"; os dias contam desde a criação quando não há sessão. A secção nova \"Sessões\n"
     "> ativas agora\" mostra quem está ligado, do pedido mais recente para o mais antigo (hosts e programas só\n"
     "> no ecrã, nunca no relatório).\n", 1),
    ("**Política:** Logins sem uso por 90+ dias devem ser desabilitados.\n",
     "**Política:** Logins sem uso por 90+ dias devem ser desabilitados.\n\n"
     "> **Atenção (2026-09-15):** a lista do WatcherDB não prova 90 dias sem uso: mostra logins sem sessão\n"
     "> ligada no momento da leitura. Confirmar com auditoria de logins (Server Audit) antes de desabilitar.\n", 1),
]

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Aba Users: sessões ativas agora, e o fim do falso \"inativo\"** (owner 15/09). O SQL Server não guarda a\n"
                  "  data do último login; a lista de inativos usava só as sessões ligadas no momento, portanto \"Nunca\" queria\n"
                  "  dizer \"sem sessão agora\" e os dias contavam desde a criação, ao lado de um texto que prometia 30+ dias.\n"
                  "  A secção passa a chamar-se \"Logins sem sessão ligada agora\", com o número igual e o texto honesto, e o\n"
                  "  relatório deixa de recomendar desabilitar essas contas. Secção nova \"Sessões ativas agora\", do pedido\n"
                  "  mais recente para o mais antigo, com sessões, hora de ligação, hosts e programas (só no ecrã). Datas e\n"
                  "  sim/não traduzidos. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    users_raw = src["users"].read_bytes().decode("utf-8")
    if MARK in users_raw:
        print("[ABORT] ja aplicado"); return 1
    out = {"users": _apply(users_raw, USERS_EDITS, "users"),
           "portal": _apply(src["portal"].read_bytes().decode("utf-8"), PORTAL_EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if set(USERS_I18N[loc]) & set(json.loads(raw)["users"]):
            raise SystemExit(f"[ABORT] {loc}: chaves novas ja existem em users")
        txt = _apply(raw, [('\n  "users": {\n', '\n  "users": {\n' + _chaves(USERS_I18N[loc]), 1)], loc)
        json.loads(txt)
        out[loc] = txt
    raw = src["ptbr"].read_bytes().decode("utf-8")
    txt = _apply(raw, [('\n  "users": {\n', '\n  "users": {\n' + _chaves(PTBR_I18N), 1)], "pt-BR")
    json.loads(txt)
    out["ptbr"] = txt
    out["doc"] = _apply(src["doc"].read_bytes().decode("utf-8"), DOC_EDITS, "doc")
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    compile(out["users"], str(REL["users"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] users.py {len(USERS_EDITS)} blocos (compila); portal {len(PORTAL_EDITS)} blocos; doc {len(DOC_EDITS)}; changelog")
    print(f"[ok] i18n users: {len(USERS_I18N['pt'])} chaves em pt/en/es, {len(PTBR_I18N)} em pt-BR; JSON valido")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_users_sessoes_ativas_20260915.py -q --no-cov ; "
          "py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
