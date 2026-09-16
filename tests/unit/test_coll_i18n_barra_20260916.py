"""
2026-09-16 -- Collector Health (lote 2a): barra, filtros e caixa de eventos ligados ao dicionario.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
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
