# -*- coding: utf-8 -*-
"""Collector Health, lote 2a/3: barra, filtros e caixa de eventos (2026-09-16).

Segue o lote 1 (modal dos 7 estados, commit fbf72e7). Aqui tratam-se os textos que se veem MAL o ecra abre:
o botao de actualizar, o de re-correr, os filtros de ambiente e estado, a pesquisa, a mensagem de "a carregar",
e a caixa "Eventos do collector" inteira -- titulo, legenda, contagem, colunas da tabela, marcas de estado,
o botao de resolver e as duas mensagens (confirmacao e erro).

Fica para o lote 2b: a janela de silenciar alertas, a janela de detalhe do task e o re-correr em massa.

DECISOES:
 - "Collector Health Monitoring" nao se traduz: e' o nome do ecra, como "Always On" ou "Blue/Green".
 - Contagens com singular e plural nao se resolvem com concatenacao ("1 ativos"): cada caso tem chave propria
   com {n}, resolvido por _collTp, tal como o _kpiTp que ja existe no portal.
 - Os textos em portugues continuam como recurso em cada chamada: se a chave faltar, aparece portugues.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_I18N_BARRA_2026-09-16_apply.py --check
  py docs/context/COLL_I18N_BARRA_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_coll_i18n_barra_20260916.py"),
}
LOCALES = {loc: Path(f"static/i18n/{loc}.json") for loc in ("pt", "pt-BR", "en", "es")}
MARK = "const _collTp ="

# --------------------------------------------------------------------------- chaves novas
PT = {
    "restricted": "Acesso restrito a DBA e administradores.",
    "refresh": "Actualizar",
    "bulk_run": "Re-correr filtrados",
    "bulk_run_title": "Re-correr, em paralelo, todas as tarefas visíveis depois dos filtros",
    "toggle_max": "Expandir ou contrair",
    "filter_env": "Ambiente:",
    "filter_state": "Estado:",
    "all": "Todos",
    "search_ph": "Procurar por nome...",
    "loading": "A carregar...",
    "events": {
        "title": "Eventos do recolhedor",
        "subtitle": "tempos esgotados e SQL em baixo, vistos pelo recolhedor central no momento da recolha (auto-vigilância, não é a frota)",
        "none_active": "sem eventos activos",
        "active_one": "{n} activo",
        "active_many": "{n} activos",
        "old_one": "({n} antigo)",
        "old_many": "({n} antigos)",
        "empty_7d": "Sem eventos nos últimos 7 dias.",
        "resolved": "resolvido",
        "active_badge": "activo",
        "old_badge": "antigo — confirmar",
        "old_title": "Evento com mais de 24 horas por resolver — pode já não estar activo. Confirme no separador Serviços do servidor antes de agir.",
        "resolve": "Resolver",
        "goto_title": "Abrir o separador adequado ao diagnóstico",
        "showing": "A mostrar 50 de {n} eventos (7 dias).",
        "confirm_resolve": "Marcar este evento do recolhedor como resolvido?",
        "resolve_error": "Erro ao resolver o evento:",
    },
    "col": {
        "instance": "Instância", "env": "Ambiente", "diagnosis": "Diagnóstico",
        "start": "Início", "duration": "Duração", "state": "Estado", "action": "Acção",
    },
}

EN = {
    "restricted": "Restricted to DBAs and administrators.",
    "refresh": "Refresh",
    "bulk_run": "Re-run filtered",
    "bulk_run_title": "Re-run, in parallel, every task visible after the filters",
    "toggle_max": "Expand or collapse",
    "filter_env": "Environment:",
    "filter_state": "State:",
    "all": "All",
    "search_ph": "Search by name...",
    "loading": "Loading...",
    "events": {
        "title": "Collector events",
        "subtitle": "timeouts and SQL down, seen by the central collector at collection time (self-monitoring, not the estate)",
        "none_active": "no active events",
        "active_one": "{n} active",
        "active_many": "{n} active",
        "old_one": "({n} old)",
        "old_many": "({n} old)",
        "empty_7d": "No events in the last 7 days.",
        "resolved": "resolved",
        "active_badge": "active",
        "old_badge": "old — please confirm",
        "old_title": "Event unresolved for over 24 hours — it may no longer be active. Check the server's Services tab before acting.",
        "resolve": "Resolve",
        "goto_title": "Open the tab that matches the diagnosis",
        "showing": "Showing 50 of {n} events (7 days).",
        "confirm_resolve": "Mark this collector event as resolved?",
        "resolve_error": "Could not resolve the event:",
    },
    "col": {
        "instance": "Instance", "env": "Environment", "diagnosis": "Diagnosis",
        "start": "Start", "duration": "Duration", "state": "State", "action": "Action",
    },
}

ES = {
    "restricted": "Acceso restringido a DBA y administradores.",
    "refresh": "Actualizar",
    "bulk_run": "Volver a ejecutar los filtrados",
    "bulk_run_title": "Volver a ejecutar, en paralelo, todas las tareas visibles tras los filtros",
    "toggle_max": "Expandir o contraer",
    "filter_env": "Entorno:",
    "filter_state": "Estado:",
    "all": "Todos",
    "search_ph": "Buscar por nombre...",
    "loading": "Cargando...",
    "events": {
        "title": "Eventos del colector",
        "subtitle": "tiempos de espera agotados y SQL caído, vistos por el colector central al momento de la recolección (automonitoreo, no el parque)",
        "none_active": "sin eventos activos",
        "active_one": "{n} activo",
        "active_many": "{n} activos",
        "old_one": "({n} antiguo)",
        "old_many": "({n} antiguos)",
        "empty_7d": "Sin eventos en los últimos 7 días.",
        "resolved": "resuelto",
        "active_badge": "activo",
        "old_badge": "antiguo — confirmar",
        "old_title": "Evento sin resolver por más de 24 horas: puede que ya no esté activo. Confirme en la pestaña Servicios del servidor antes de actuar.",
        "resolve": "Resolver",
        "goto_title": "Abrir la pestaña adecuada al diagnóstico",
        "showing": "Mostrando 50 de {n} eventos (7 días).",
        "confirm_resolve": "¿Marcar este evento del colector como resuelto?",
        "resolve_error": "Error al resolver el evento:",
    },
    "col": {
        "instance": "Instancia", "env": "Entorno", "diagnosis": "Diagnóstico",
        "start": "Inicio", "duration": "Duración", "state": "Estado", "action": "Acción",
    },
}

# Sobreposto pt-BR: so' o que muda mesmo face ao pt.
PT_BR = {
    "search_ph": "Pesquisar por nome...",
    "events": {
        "title": "Eventos do coletor",
        "subtitle": "tempos esgotados e SQL fora do ar, vistos pelo coletor central no momento da coleta (automonitoramento, não é o parque)",
        "none_active": "sem eventos ativos",
        "active_one": "{n} ativo",
        "active_many": "{n} ativos",
        "active_badge": "ativo",
        "old_title": "Evento com mais de 24 horas sem resolver — pode já não estar ativo. Confirme na aba Serviços do servidor antes de agir.",
        "goto_title": "Abrir a aba adequada ao diagnóstico",
        "confirm_resolve": "Marcar este evento do coletor como resolvido?",
    },
    "col": {"action": "Ação"},
}

GRUPOS = {"pt": PT, "pt-BR": PT_BR, "en": EN, "es": ES}

# --------------------------------------------------------------------------- portal
HELPER_OLD = """    const _collT = (chave, pt) => {
        try { const v = (typeof t === 'function') ? t(chave) : null; return (v && v !== chave) ? v : pt; }
        catch (e) { return pt; }
    };
"""
HELPER_NEW = """    const _collT = (chave, pt) => {
        try { const v = (typeof t === 'function') ? t(chave) : null; return (v && v !== chave) ? v : pt; }
        catch (e) { return pt; }
    };
    // Com marcadores {n}. Contagens nao se fazem por concatenacao ("1 ativos"): cada caso tem chave propria.
    const _collTp = (chave, pt, vals) => {
        let s = _collT(chave, pt);
        Object.keys(vals || {}).forEach(k => { s = s.split('{' + k + '}').join(vals[k]); });
        return s;
    };
"""

EDITS = [
    (HELPER_OLD, HELPER_NEW, 1),

    # --- barra e filtros
    ("""            alert('Acesso restrito a DBA/administradores.');""",
     """            alert(_collT('coll.restricted', 'Acesso restrito a DBA/administradores.'));""", 2),
    # (duas vezes de proposito: a guarda da modal do collector e a da janela de silenciar alertas)
    ("""<i class="fas fa-sync-alt"></i> Actualizar</button>""",
     """<i class="fas fa-sync-alt"></i> ${_collT('coll.refresh', 'Actualizar')}</button>""", 1),
    ("""title="Re-correr todos os tasks visiveis (apos filtros) em paralelo"><i class="fas fa-bolt"></i> Re-run Filtrados</button>""",
     """title="${_collT('coll.bulk_run_title', 'Re-correr todos os tasks visiveis (apos filtros) em paralelo')}"><i class="fas fa-bolt"></i> ${_collT('coll.bulk_run', 'Re-run Filtrados')}</button>""", 1),
    ("""onclick="collToggleMaximize()" title="Expandir/contrair\"""",
     """onclick="collToggleMaximize()" title="${_collT('coll.toggle_max', 'Expandir/contrair')}\"""", 1),
    ("""font-size:11px;">Ambiente:</label>""",
     """font-size:11px;">${_collT('coll.filter_env', 'Ambiente:')}</label>""", 1),
    ("""font-size:11px;">Estado:</label>""",
     """font-size:11px;">${_collT('coll.filter_state', 'Estado:')}</label>""", 1),
    # Os dois "Todos" tem de levar o contexto a` volta: ha um terceiro, noutro ecra (linha ~33809), que
    # nao e' deste lote.
    ("""                            <option value="">Todos</option>
                            <option value="PRD">PRD</option><option value="QA">QA</option>""",
     """                            <option value="">${_collT('coll.all', 'Todos')}</option>
                            <option value="PRD">PRD</option><option value="QA">QA</option>""", 1),
    ("""                            <option value="">Todos</option>
                            <option value="FRESH">FRESH</option>""",
     """                            <option value="">${_collT('coll.all', 'Todos')}</option>
                            <option value="FRESH">FRESH</option>""", 1),
    ("""placeholder="Pesquisar por nome..." oninput="collDebounceFilter()"/>""",
     """placeholder="${_collT('coll.search_ph', 'Pesquisar por nome...')}" oninput="collDebounceFilter()"/>""", 1),
    # "A carregar..." aparece em tres sitios do portal; este leva o contentor a` volta para so' apanhar o nosso.
    ("""                    <div class="coll-body" id="coll-body">
                        <div style="padding:40px;text-align:center;color:var(--color-text-tertiary);">A carregar...</div>""",
     """                    <div class="coll-body" id="coll-body">
                        <div style="padding:40px;text-align:center;color:var(--color-text-tertiary);">${_collT('coll.loading', 'A carregar...')}</div>""", 1),

    # --- caixa de eventos: contagem com singular e plural
    ("""        const badgeText = active.length === 0 ? 'sem eventos ativos'
            : active.length + ' ativo' + (active.length > 1 ? 's' : '') + (oldCount > 0 ? ' (' + oldCount + ' antigo' + (oldCount > 1 ? 's' : '') + ')' : '');
""",
     """        const badgeText = active.length === 0
            ? _collT('coll.events.none_active', 'sem eventos ativos')
            : _collTp(active.length > 1 ? 'coll.events.active_many' : 'coll.events.active_one',
                      active.length > 1 ? '{n} ativos' : '{n} ativo', { n: active.length })
              + (oldCount > 0
                    ? ' ' + _collTp(oldCount > 1 ? 'coll.events.old_many' : 'coll.events.old_one',
                                    oldCount > 1 ? '({n} antigos)' : '({n} antigo)', { n: oldCount })
                    : '');
""", 1),

    # --- caixa de eventos: cabecalho e legenda
    ("""font-weight:600;">Eventos do collector</span>""",
     """font-weight:600;">${_collT('coll.events.title', 'Eventos do collector')}</span>""", 1),
    ("""<span style="font-size:10px;color:var(--color-text-disabled);">timeouts / SQL down vistos pelo collector central no momento da coleta (auto-monitoria, nao frota)</span>""",
     """<span style="font-size:10px;color:var(--color-text-disabled);">${_collT('coll.events.subtitle', 'timeouts / SQL down vistos pelo collector central no momento da coleta (auto-monitoria, nao frota)')}</span>""", 1),
    ("""border-top:1px solid var(--color-border);">Sem eventos nos ultimos 7 dias.</div>""",
     """border-top:1px solid var(--color-border);">${_collT('coll.events.empty_7d', 'Sem eventos nos ultimos 7 dias.')}</div>""", 1),

    # --- marcas de estado e accao de cada linha
    ("""                        ? '<span class="coll-badge" style="background:#10b98122;color:#10b981;">resolvido</span>'""",
     """                        ? '<span class="coll-badge" style="background:#10b98122;color:#10b981;">' + _collT('coll.events.resolved', 'resolvido') + '</span>'""", 1),
    ("""                            ? '<span class="coll-badge" style="background:#f59e0b22;color:#f59e0b;" title="Evento com mais de 24h por resolver — pode ja nao estar ativo. Confirmar na aba Services do servidor antes de agir.">antigo — confirmar</span>'""",
     """                            ? '<span class="coll-badge" style="background:#f59e0b22;color:#f59e0b;" title="' + _collT('coll.events.old_title', 'Evento com mais de 24h por resolver — pode ja nao estar ativo. Confirmar na aba Services do servidor antes de agir.') + '">' + _collT('coll.events.old_badge', 'antigo — confirmar') + '</span>'""", 1),
    ("""                            : '<span class="coll-badge" style="background:#ef444422;color:#ef4444;">ativo</span>';""",
     """                            : '<span class="coll-badge" style="background:#ef444422;color:#ef4444;">' + _collT('coll.events.active_badge', 'ativo') + '</span>';""", 1),
    ("""font-size:10px;font-weight:600;">Resolver</button>';""",
     """font-size:10px;font-weight:600;">' + _collT('coll.events.resolve', 'Resolver') + '</button>';""", 1),
    ("""                            title="Abrir a aba adequada ao diagnostico">${instName || 'N/A'}</a></td>""",
     """                            title="${_collT('coll.events.goto_title', 'Abrir a aba adequada ao diagnostico')}">${instName || 'N/A'}</a></td>""", 1),

    # --- colunas da tabela de eventos
    ("""                            <th style="${th}text-align:left;">Instancia</th>
                            <th style="${th}text-align:left;">Env</th>
                            <th style="${th}text-align:left;">Diagnostico</th>
                            <th style="${th}text-align:left;">Inicio</th>
                            <th style="${th}text-align:left;">Duracao</th>
                            <th style="${th}text-align:center;">Estado</th>
                            <th style="${th}text-align:center;">Acao</th>
""",
     """                            <th style="${th}text-align:left;">${_collT('coll.col.instance', 'Instancia')}</th>
                            <th style="${th}text-align:left;">${_collT('coll.col.env', 'Env')}</th>
                            <th style="${th}text-align:left;">${_collT('coll.col.diagnosis', 'Diagnostico')}</th>
                            <th style="${th}text-align:left;">${_collT('coll.col.start', 'Inicio')}</th>
                            <th style="${th}text-align:left;">${_collT('coll.col.duration', 'Duracao')}</th>
                            <th style="${th}text-align:center;">${_collT('coll.col.state', 'Estado')}</th>
                            <th style="${th}text-align:center;">${_collT('coll.col.action', 'Acao')}</th>
""", 1),
    ("""border-top:1px solid var(--color-border);">A mostrar 50 de ${events.length} eventos (7 dias).</div>""",
     """border-top:1px solid var(--color-border);">${_collTp('coll.events.showing', 'A mostrar 50 de {n} eventos (7 dias).', { n: events.length })}</div>""", 1),

    # --- mensagens
    ("""        if (!confirm('Marcar este evento do collector como resolvido?')) return;""",
     """        if (!confirm(_collT('coll.events.confirm_resolve', 'Marcar este evento do collector como resolvido?'))) return;""", 1),
    ("""            alert('Erro ao resolver evento: ' + e.message);""",
     """            alert(_collT('coll.events.resolve_error', 'Erro ao resolver evento:') + ' ' + e.message);""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: barra, filtros e eventos do recolhedor traduzidos** (owner 16/09). Segundo lote do ecrã:\n"
    "  botões, filtros de ambiente e estado, pesquisa, mensagem de carregamento e a caixa \"Eventos do recolhedor\"\n"
    "  inteira — título, legenda, colunas, marcas de estado e mensagens. As contagens deixam de ser montadas por\n"
    "  concatenação, que dava \"1 ativos\" em qualquer idioma que não o português. Falta o lote das janelas\n"
    "  (silenciar, detalhe e re-correr em massa). [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- Collector Health (lote 2a): barra, filtros e caixa de eventos ligados ao dicionario.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
COLUNAS = ["instance", "env", "diagnosis", "start", "duration", "state", "action"]
EVENTOS = ["title", "subtitle", "none_active", "active_one", "active_many", "old_one", "old_many",
           "empty_7d", "resolved", "active_badge", "old_badge", "old_title", "resolve", "goto_title",
           "showing", "confirm_resolve", "resolve_error"]


def test_os_tres_idiomas_completos_tem_tudo():
    for loc in ("pt", "en", "es"):
        coll = LOCS[loc]["coll"]
        for c in COLUNAS:
            assert coll["col"][c].strip(), f"{loc}: col.{c}"
        for e in EVENTOS:
            assert coll["events"][e].strip(), f"{loc}: events.{e}"
        for k in ("restricted", "refresh", "bulk_run", "bulk_run_title", "toggle_max",
                  "filter_env", "filter_state", "all", "search_ph", "loading"):
            assert coll[k].strip(), f"{loc}: {k}"
        # o lote 1 nao pode ter sido tocado
        assert len(coll["state"]) == 7


def test_as_contagens_tem_marcador_n_em_todos_os_idiomas():
    for loc in ("pt", "en", "es"):
        ev = LOCS[loc]["coll"]["events"]
        for k in ("active_one", "active_many", "old_one", "old_many", "showing"):
            assert "{n}" in ev[k], f"{loc}: {k} sem marcador {{n}}"


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    def achatar(d, p=""):
        s = {}
        for k, v in d.items():
            s.update(achatar(v, p + k + ".")) if isinstance(v, dict) else s.update({p + k: v})
        return s
    pt, br = achatar(LOCS["pt"]["coll"]), achatar(LOCS["pt-BR"]["coll"])
    assert [k for k, v in br.items() if pt.get(k) == v] == []
    assert set(br) <= set(pt)


def test_nada_de_portugues_no_ingles():
    texto = json.dumps(LOCS["en"]["coll"], ensure_ascii=False).lower()
    for p in ("instância", "diagnóstico", "acção", "recolhedor", "pesquisar", "actualizar"):
        assert p not in texto, f"ingles com texto portugues: {p}"


def test_o_portal_usa_as_chaves():
    assert "const _collTp =" in PORTAL
    for chave in ("coll.restricted", "coll.refresh", "coll.bulk_run", "coll.bulk_run_title",
                  "coll.toggle_max", "coll.filter_env", "coll.filter_state", "coll.all",
                  "coll.search_ph", "coll.loading", "coll.events.title", "coll.events.subtitle",
                  "coll.events.empty_7d", "coll.events.resolved", "coll.events.old_title",
                  "coll.events.old_badge", "coll.events.active_badge", "coll.events.resolve",
                  "coll.events.goto_title", "coll.events.showing", "coll.events.confirm_resolve",
                  "coll.events.resolve_error"):
        assert f"'{chave}'" in PORTAL, f"chave nao usada no portal: {chave}"
    for c in COLUNAS:
        assert f"'coll.col.{c}'" in PORTAL


def test_a_contagem_deixou_de_ser_concatenada():
    """'1 ativo' + 's' so' funciona em portugues; em ingles dava '1 actives'."""
    assert "' ativo' + (active.length > 1 ? 's' : '')" not in PORTAL
    assert "_collTp(active.length > 1 ? 'coll.events.active_many' : 'coll.events.active_one'" in PORTAL


def test_o_portugues_continua_como_recurso():
    for recurso in ("'coll.refresh', 'Actualizar'", "'coll.all', 'Todos'",
                    "'coll.events.resolve', 'Resolver'"):
        assert recurso in PORTAL
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


def _fundir_no_grupo(raw: str, novos: dict, loc: str) -> str:
    """Acrescenta chaves DENTRO do grupo coll que ja existe, sem tocar no resto do ficheiro."""
    ancora = '  "coll": {\n'
    if raw.count(ancora) != 1:
        raise SystemExit(f"[ABORT] {loc}: grupo coll nao encontrado uma unica vez (o lote 1 foi aplicado?)")
    antes = json.loads(raw)
    repetidas = set(novos) & set(antes["coll"])
    if repetidas:
        raise SystemExit(f"[ABORT] {loc}: chaves ja existentes no grupo coll: {sorted(repetidas)}")
    texto = json.dumps(novos, ensure_ascii=False, indent=2)
    bloco = "\n".join("  " + l for l in texto.split("\n")[1:-1])
    novo = raw.replace(ancora, ancora + bloco + ",\n")
    d = json.loads(novo)
    for k in antes:
        if k != "coll":
            assert d[k] == antes[k], f"{loc}: o grupo {k} mudou"
    for k in antes["coll"]:
        assert d["coll"][k] == antes["coll"][k], f"{loc}: coll.{k} mudou"
    assert set(d["coll"]) == set(antes["coll"]) | set(novos)
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "const _collT = (chave, pt) =>" not in portal:
        print("[ABORT] falta o lote 1 (COLL_I18N_MODAL_2026-09-16_apply.py). Corre-o primeiro."); return 1

    out = {"portal": _apply(portal, EDITS, "portal"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}

    locais = {}
    for loc, rel in LOCALES.items():
        caminho = base / rel
        novo = _fundir_no_grupo(caminho.read_bytes().decode("utf-8"), GRUPOS[loc], loc)
        locais[loc] = (caminho, novo)
        print(f"[ok] {loc}: +{len(GRUPOS[loc])} chaves de topo no grupo coll")

    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal {len(EDITS)} blocos; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    for loc, (caminho, novo) in locais.items():
        caminho.write_bytes(novo.encode("utf-8")); print(f"[write] {LOCALES[loc]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_coll_i18n_barra_20260916.py "
          "tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
