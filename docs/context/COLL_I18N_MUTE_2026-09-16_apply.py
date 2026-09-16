# -*- coding: utf-8 -*-
"""Collector Health, lote 2b/3: a janela de silenciar alertas (2026-09-16).

Segue os lotes 1 (modal dos 7 estados) e 2a (barra, filtros e eventos). Falta depois o lote 2c: janela de
detalhe da tarefa e re-correr em massa.

O QUE ESTAVA: esta janela e' a mais misturada do ecra -- "KPI Mute List", "Refresh", "Created By", "Hrs Left",
"Unmute" em ingles, ao lado de "Adicionar novo mute", "A carregar..." e mensagens de erro em portugues, e nada
disto mudava com o idioma escolhido. Alem de traduzir, o portugues passa a dizer as coisas por palavras:
"silenciar" em vez de "mute", "motivo" em vez de "reason", "horas restantes" em vez de "Hrs Left".

A contagem "N mute(s) activo(s)" desaparece: o "(s)" e' uma forma de fugir ao plural que nao sobrevive a
traducao. Passa a haver chave para singular e para plural, como na caixa de eventos.

DEPENDE de: COLL_I18N_MODAL (lote 1) e COLL_I18N_BARRA (lote 2a) -- usa o _collT e o _collTp que eles criam,
e reaproveita coll.refresh, coll.loading, coll.col.instance e coll.col.action.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_I18N_MUTE_2026-09-16_apply.py --check
  py docs/context/COLL_I18N_MUTE_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_i18n_mute_20260916.py tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov
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
    "test": Path("tests/unit/test_coll_i18n_mute_20260916.py"),
}
LOCALES = {loc: Path(f"static/i18n/{loc}.json") for loc in ("pt", "pt-BR", "en", "es")}
MARK = "coll.mute.title"

# --------------------------------------------------------------------------- chaves novas (grupo coll.mute)
PT = {
    "title": "KPIs silenciados",
    "subtitle": "silenciar os alertas de um KPI numa instância, por tempo limitado",
    "add": "Silenciar um KPI",
    "f_kpi": "Tipo de KPI",
    "ph_kpi": "ex: backup-failed",
    "f_instance": "Instância",
    "ph_instance": "ex: SQLHDSPRD302_I01",
    "f_reason": "Motivo (mínimo 10 caracteres)",
    "ph_reason": "ex: manutenção planeada CR-12345 até 2026-06-01",
    "f_hours": "Horas",
    "btn": "Silenciar",
    "note": "No máximo 720 horas (30 dias). O motivo e a data de fim são obrigatórios: não há silêncios permanentes, e fica registado quem silenciou.",
    "empty": "Nenhum KPI silenciado.",
    "empty_sub": "Todos os KPIs estão a alertar normalmente.",
    "count_one": "{n} KPI silenciado",
    "count_many": "{n} KPIs silenciados",
    "col_reason": "Motivo",
    "col_created_by": "Silenciado por",
    "col_hrs_left": "Horas restantes",
    "col_until": "Até (UTC)",
    "unmute": "Reactivar",
    "confirm_delete": "Reactivar os alertas de \"{kpi}\" em \"{inst}\"?\n\nO KPI volta a alertar de imediato.",
    "val_required": "O tipo de KPI, a instância e o motivo são obrigatórios.",
    "val_reason": "O motivo tem de ter pelo menos 10 caracteres — fica em registo.",
    "val_hours": "As horas têm de estar entre 1 e 720 (no máximo 30 dias).",
    "err_create": "Não foi possível silenciar:",
    "err_delete": "Não foi possível reactivar:",
    "err_load": "Erro:",
}

EN = {
    "title": "Muted KPIs",
    "subtitle": "silence one KPI's alerts on one instance, for a limited time",
    "add": "Mute a KPI",
    "f_kpi": "KPI type",
    "ph_kpi": "e.g. backup-failed",
    "f_instance": "Instance",
    "ph_instance": "e.g. SQLHDSPRD302_I01",
    "f_reason": "Reason (at least 10 characters)",
    "ph_reason": "e.g. planned maintenance CR-12345 until 2026-06-01",
    "f_hours": "Hours",
    "btn": "Mute",
    "note": "Up to 720 hours (30 days). Reason and end date are required: there are no permanent mutes, and who muted it is recorded.",
    "empty": "No muted KPIs.",
    "empty_sub": "Every KPI is alerting normally.",
    "count_one": "{n} muted KPI",
    "count_many": "{n} muted KPIs",
    "col_reason": "Reason",
    "col_created_by": "Muted by",
    "col_hrs_left": "Hours left",
    "col_until": "Until (UTC)",
    "unmute": "Unmute",
    "confirm_delete": "Turn alerts back on for \"{kpi}\" on \"{inst}\"?\n\nThe KPI starts alerting again immediately.",
    "val_required": "KPI type, instance and reason are all required.",
    "val_reason": "The reason must be at least 10 characters — it is recorded.",
    "val_hours": "Hours must be between 1 and 720 (30 days at most).",
    "err_create": "Could not mute:",
    "err_delete": "Could not unmute:",
    "err_load": "Error:",
}

ES = {
    "title": "KPI silenciados",
    "subtitle": "silenciar las alertas de un KPI en una instancia, por tiempo limitado",
    "add": "Silenciar un KPI",
    "f_kpi": "Tipo de KPI",
    "ph_kpi": "ej. backup-failed",
    "f_instance": "Instancia",
    "ph_instance": "ej. SQLHDSPRD302_I01",
    "f_reason": "Motivo (mínimo 10 caracteres)",
    "ph_reason": "ej. mantenimiento planificado CR-12345 hasta 2026-06-01",
    "f_hours": "Horas",
    "btn": "Silenciar",
    "note": "Como máximo 720 horas (30 días). El motivo y la fecha de fin son obligatorios: no hay silencios permanentes y queda registrado quién lo silenció.",
    "empty": "Ningún KPI silenciado.",
    "empty_sub": "Todos los KPI están alertando normalmente.",
    "count_one": "{n} KPI silenciado",
    "count_many": "{n} KPI silenciados",
    "col_reason": "Motivo",
    "col_created_by": "Silenciado por",
    "col_hrs_left": "Horas restantes",
    "col_until": "Hasta (UTC)",
    "unmute": "Reactivar",
    "confirm_delete": "¿Reactivar las alertas de \"{kpi}\" en \"{inst}\"?\n\nEl KPI vuelve a alertar de inmediato.",
    "val_required": "El tipo de KPI, la instancia y el motivo son obligatorios.",
    "val_reason": "El motivo debe tener al menos 10 caracteres: queda registrado.",
    "val_hours": "Las horas deben estar entre 1 y 720 (30 días como máximo).",
    "err_create": "No se pudo silenciar:",
    "err_delete": "No se pudo reactivar:",
    "err_load": "Error:",
}

PT_BR = {
    "subtitle": "silenciar os alertas de um KPI numa instância, por tempo limitado",  # igual? nao: ver abaixo
    "f_reason": "Motivo (mínimo 10 caracteres)",
}
# O sobreposto pt-BR e' montado abaixo, so' com o que muda mesmo.
PT_BR = {
    "subtitle": "silenciar os alertas de um KPI em uma instância, por tempo limitado",
    "note": "No máximo 720 horas (30 dias). O motivo e a data de fim são obrigatórios: não há silêncios permanentes, e fica registrado quem silenciou.",
    "empty_sub": "Todos os KPIs estão alertando normalmente.",
    "val_reason": "O motivo precisa ter pelo menos 10 caracteres — fica em registro.",
    "val_hours": "As horas precisam estar entre 1 e 720 (no máximo 30 dias).",
    "unmute": "Reativar",
    "confirm_delete": "Reativar os alertas de \"{kpi}\" em \"{inst}\"?\n\nO KPI volta a alertar imediatamente.",
    "err_delete": "Não foi possível reativar:",
}

GRUPOS = {"pt": PT, "pt-BR": PT_BR, "en": EN, "es": ES}

# --------------------------------------------------------------------------- portal
EDITS = [
    # cabecalho da janela
    ("""                            <i class="fas fa-bell-slash" style="color:#f59e0b;"></i> KPI Mute List
                            <span style="font-size:12px;color:var(--color-text-tertiary);font-weight:normal;margin-left:8px;">Smart Defaults Initiative camada 1 -- silenciar alertas por instance</span>""",
     """                            <i class="fas fa-bell-slash" style="color:#f59e0b;"></i> ${_collT('coll.mute.title', 'KPI Mute List')}
                            <span style="font-size:12px;color:var(--color-text-tertiary);font-weight:normal;margin-left:8px;">${_collT('coll.mute.subtitle', 'silenciar alertas por instance')}</span>""", 1),
    ("""                                <i class="fas fa-sync-alt"></i> Refresh
""",
     """                                <i class="fas fa-sync-alt"></i> ${_collT('coll.refresh', 'Actualizar')}
""", 1),

    # formulario
    ("""                            <i class="fas fa-plus-circle"></i> Adicionar novo mute
""",
     """                            <i class="fas fa-plus-circle"></i> ${_collT('coll.mute.add', 'Adicionar novo mute')}
""", 1),
    ("""margin-bottom:3px;">KPI Type</label>
                                <input type="text" id="kpi-mute-input-type" placeholder="ex: backup-failed\"""",
     """margin-bottom:3px;">${_collT('coll.mute.f_kpi', 'KPI Type')}</label>
                                <input type="text" id="kpi-mute-input-type" placeholder="${_collT('coll.mute.ph_kpi', 'ex: backup-failed')}\"""", 1),
    ("""margin-bottom:3px;">Instance</label>
                                <input type="text" id="kpi-mute-input-instance" placeholder="ex: SQLHDSPRD302_I01\"""",
     """margin-bottom:3px;">${_collT('coll.mute.f_instance', 'Instance')}</label>
                                <input type="text" id="kpi-mute-input-instance" placeholder="${_collT('coll.mute.ph_instance', 'ex: SQLHDSPRD302_I01')}\"""", 1),
    ("""margin-bottom:3px;">Reason (min 10 chars)</label>
                                <input type="text" id="kpi-mute-input-reason" placeholder="ex: manutencao planeada CR-12345 ate 2026-06-01\"""",
     """margin-bottom:3px;">${_collT('coll.mute.f_reason', 'Reason (min 10 chars)')}</label>
                                <input type="text" id="kpi-mute-input-reason" placeholder="${_collT('coll.mute.ph_reason', 'ex: manutencao planeada CR-12345 ate 2026-06-01')}\"""", 1),
    ("""margin-bottom:3px;">Mute Hours</label>""",
     """margin-bottom:3px;">${_collT('coll.mute.f_hours', 'Mute Hours')}</label>""", 1),
    ("""                                <i class="fas fa-plus"></i> Mute
""",
     """                                <i class="fas fa-plus"></i> ${_collT('coll.mute.btn', 'Mute')}
""", 1),
    ("""                            Max 720h (30 dias). Reason e Mute_Until obrigatorios (audit + no permanent mutes).
""",
     """                            ${_collT('coll.mute.note', 'Max 720h (30 dias). Reason e Mute_Until obrigatorios (audit + no permanent mutes).')}
""", 1),

    # "a carregar" nos dois sitios desta janela
    ("""                    <div id="kpi-mute-body" style="flex:1;overflow-y:auto;padding:16px 20px;">
                        <div style="text-align:center;padding:40px;color:var(--color-text-tertiary);">A carregar...</div>""",
     """                    <div id="kpi-mute-body" style="flex:1;overflow-y:auto;padding:16px 20px;">
                        <div style="text-align:center;padding:40px;color:var(--color-text-tertiary);">${_collT('coll.loading', 'A carregar...')}</div>""", 1),
    ("""        body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--color-text-tertiary);">A carregar...</div>';""",
     """        body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--color-text-tertiary);">' + _collT('coll.loading', 'A carregar...') + '</div>';""", 1),

    # lista vazia
    ("""                body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--color-text-tertiary);"><i class="fas fa-bell" style="font-size:32px;color:var(--color-border-strong);margin-bottom:10px;"></i><br>Nenhum mute activo. <br><span style="font-size:11px;">Smart Defaults active -- todos KPIs alertando normalmente.</span></div>';""",
     """                body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--color-text-tertiary);"><i class="fas fa-bell" style="font-size:32px;color:var(--color-border-strong);margin-bottom:10px;"></i><br>'
                    + _collT('coll.mute.empty', 'Nenhum mute activo.')
                    + ' <br><span style="font-size:11px;">' + _collT('coll.mute.empty_sub', 'Todos KPIs alertando normalmente.') + '</span></div>';""", 1),

    # botao de cada linha
    ("""                                <i class="fas fa-trash"></i> Unmute
""",
     """                                <i class="fas fa-trash"></i> ${_collT('coll.mute.unmute', 'Unmute')}
""", 1),

    # contagem e colunas
    ("""                <div style="margin-bottom:10px;color:var(--color-text-tertiary);font-size:12px;">${mutes.length} mute(s) activo(s)</div>""",
     """                <div style="margin-bottom:10px;color:var(--color-text-tertiary);font-size:12px;">${_collTp(mutes.length === 1 ? 'coll.mute.count_one' : 'coll.mute.count_many', mutes.length === 1 ? '{n} mute activo' : '{n} mutes activos', { n: mutes.length })}</div>""", 1),
    ("""                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">KPI Type</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">Instance</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">Reason</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">Created By</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">Hrs Left</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">Until (UTC)</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;width:80px;">Action</th>
""",
     """                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">${_collT('coll.mute.f_kpi', 'KPI Type')}</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">${_collT('coll.col.instance', 'Instance')}</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">${_collT('coll.mute.col_reason', 'Reason')}</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">${_collT('coll.mute.col_created_by', 'Created By')}</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">${_collT('coll.mute.col_hrs_left', 'Hrs Left')}</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;">${_collT('coll.mute.col_until', 'Until (UTC)')}</th>
                            <th style="padding:8px 6px;color:var(--color-text-tertiary);font-size:11px;font-weight:600;width:80px;">${_collT('coll.col.action', 'Action')}</th>
""", 1),

    # erros e validacoes
    ("""            body.innerHTML = `<div style="padding:20px;color:#fca5a5;">Erro: ${e.message}</div>`;""",
     """            body.innerHTML = `<div style="padding:20px;color:#fca5a5;">${_collT('coll.mute.err_load', 'Erro:')} ${e.message}</div>`;""", 1),
    ("""            alert('KPI Type, Instance e Reason obrigatorios.');""",
     """            alert(_collT('coll.mute.val_required', 'KPI Type, Instance e Reason obrigatorios.'));""", 1),
    ("""            alert('Reason minimo 10 caracteres (audit trail).');""",
     """            alert(_collT('coll.mute.val_reason', 'Reason minimo 10 caracteres (audit trail).'));""", 1),
    ("""            alert('Mute Hours entre 1 e 720 (30 dias max).');""",
     """            alert(_collT('coll.mute.val_hours', 'Mute Hours entre 1 e 720 (30 dias max).'));""", 1),
    ("""            alert('Erro a criar mute: ' + e.message);""",
     """            alert(_collT('coll.mute.err_create', 'Erro a criar mute:') + ' ' + e.message);""", 1),
    ("""        if (!confirm(`Remover mute "${kpiType}" para "${instance}"?\\n\\nKPI volta a alertar imediatamente.`)) return;""",
     """        if (!confirm(_collTp('coll.mute.confirm_delete', 'Remover mute "{kpi}" para "{inst}"?\\n\\nKPI volta a alertar imediatamente.', { kpi: kpiType, inst: instance }))) return;""", 1),
    ("""            alert('Erro a remover mute: ' + e.message);""",
     """            alert(_collT('coll.mute.err_delete', 'Erro a remover mute:') + ' ' + e.message);""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: a janela de silenciar alertas deixa de ser meio inglesa** (owner 16/09). Era a mais\n"
    "  misturada do ecrã — \"KPI Mute List\", \"Created By\", \"Hrs Left\" e \"Unmute\" ao lado de \"Adicionar novo mute\"\n"
    "  e das mensagens de erro em português, e nada disto mudava com o idioma. Passa a estar traduzida nos quatro\n"
    "  idiomas, o português deixa o jargão (\"silenciar\" em vez de \"mute\", \"motivo\" em vez de \"reason\"), e a\n"
    "  contagem deixa de ser \"N mute(s) activo(s)\": tem singular e plural a sério. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- Collector Health (lote 2b): a janela de silenciar alertas fala o idioma escolhido.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
CHAVES = ["title", "subtitle", "add", "f_kpi", "ph_kpi", "f_instance", "ph_instance", "f_reason",
          "ph_reason", "f_hours", "btn", "note", "empty", "empty_sub", "count_one", "count_many",
          "col_reason", "col_created_by", "col_hrs_left", "col_until", "unmute", "confirm_delete",
          "val_required", "val_reason", "val_hours", "err_create", "err_delete", "err_load"]


def test_os_tres_idiomas_completos():
    for loc in ("pt", "en", "es"):
        mute = LOCS[loc]["coll"]["mute"]
        for k in CHAVES:
            assert mute[k].strip(), f"{loc}: mute.{k}"
        assert len(LOCS[loc]["coll"]["state"]) == 7          # lote 1 intacto
        assert LOCS[loc]["coll"]["events"]["title"].strip()  # lote 2a intacto


def test_marcadores_certos():
    for loc in ("pt", "en", "es"):
        mute = LOCS[loc]["coll"]["mute"]
        assert "{n}" in mute["count_one"] and "{n}" in mute["count_many"]
        assert "{kpi}" in mute["confirm_delete"] and "{inst}" in mute["confirm_delete"]


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    pt, br = LOCS["pt"]["coll"]["mute"], LOCS["pt-BR"]["coll"]["mute"]
    assert [k for k, v in br.items() if pt.get(k) == v] == []
    assert set(br) <= set(pt)


def test_nada_de_jargao_ingles_no_portugues():
    """So' os VALORES: os nomes das chaves (unmute, f_kpi) sao internos e ficam em ingles de proposito."""
    texto = " | ".join(LOCS["pt"]["coll"]["mute"].values()).lower()
    for p in ("hrs left", "created by", "unmute", "mute hours", "audit trail", "mute list"):
        assert p not in texto, f"portugues ainda com jargao: {p}"


def test_o_portal_usa_as_chaves():
    for k in CHAVES:
        assert f"'coll.mute.{k}'" in PORTAL, f"chave nao usada: coll.mute.{k}"
    assert "_collT('coll.col.instance'" in PORTAL and "_collT('coll.col.action'" in PORTAL


def test_a_contagem_deixou_de_ser_parenteses_s():
    assert "mute(s) activo(s)" not in PORTAL
    assert "mutes.length === 1 ? 'coll.mute.count_one' : 'coll.mute.count_many'" in PORTAL


def test_a_confirmacao_usa_marcadores_e_nao_concatenacao():
    i = PORTAL.index("coll.mute.confirm_delete")
    bloco = PORTAL[i - 200:i + 300]
    assert "{ kpi: kpiType, inst: instance }" in bloco
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


def _fundir(raw: str, novos: dict, loc: str) -> str:
    """Acrescenta o sub-grupo "mute" dentro do grupo coll, sem tocar no resto."""
    ancora = '  "coll": {\n'
    if raw.count(ancora) != 1:
        raise SystemExit(f"[ABORT] {loc}: grupo coll nao encontrado (faltam os lotes 1 e 2a?)")
    antes = json.loads(raw)
    if "mute" in antes["coll"]:
        raise SystemExit(f"[ABORT] {loc}: coll.mute ja existe")
    texto = json.dumps({"mute": novos}, ensure_ascii=False, indent=2)
    bloco = "\n".join("  " + l for l in texto.split("\n")[1:-1])
    novo = raw.replace(ancora, ancora + bloco + ",\n")
    d = json.loads(novo)
    for k in antes:
        if k != "coll":
            assert d[k] == antes[k], f"{loc}: o grupo {k} mudou"
    for k in antes["coll"]:
        assert d["coll"][k] == antes["coll"][k], f"{loc}: coll.{k} mudou"
    assert set(d["coll"]) == set(antes["coll"]) | {"mute"}
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "const _collTp =" not in portal:
        print("[ABORT] falta o lote 2a (COLL_I18N_BARRA_2026-09-16_apply.py). Corre-o primeiro."); return 1

    out = {"portal": _apply(portal, EDITS, "portal"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}

    locais = {}
    for loc, rel in LOCALES.items():
        caminho = base / rel
        novo = _fundir(caminho.read_bytes().decode("utf-8"), GRUPOS[loc], loc)
        locais[loc] = (caminho, novo)
        print(f"[ok] {loc}: coll.mute com {len(GRUPOS[loc])} chaves")

    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal {len(EDITS)} blocos; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    for loc, (caminho, novo) in locais.items():
        caminho.write_bytes(novo.encode("utf-8")); print(f"[write] {LOCALES[loc]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_coll_i18n_mute_20260916.py "
          "tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
