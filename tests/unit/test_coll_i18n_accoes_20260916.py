"""
2026-09-16 -- Collector Health (lote 2d, ultimo): as accoes falam o idioma escolhido.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
RUN = ["need_enable", "confirm", "st_registering", "st_pending", "st_running", "st_done", "st_error",
       "st_timeout", "registering", "err_register", "queued", "queued_dots", "running", "done",
       "failed", "unknown_error", "timeout_queue", "timeout_poller", "close"]
BULK = ["none", "confirm_title", "confirm_count", "confirm_more", "confirm_skipped", "confirm_ask",
        "dispatching", "done_title", "done_ok", "done_failed", "done_failed_list", "done_note"]
TOGGLE = ["word_on", "word_off", "prompt", "too_short", "processing"]


def test_os_tres_idiomas_completos():
    for loc in ("pt", "en", "es"):
        coll = LOCS[loc]["coll"]
        for k in RUN:
            assert coll["run"][k].strip(), f"{loc}: run.{k}"
        for k in BULK:
            assert coll["bulk"][k].strip(), f"{loc}: bulk.{k}"
        for k in TOGGLE:
            assert coll["toggle"][k].strip(), f"{loc}: toggle.{k}"
        # lotes anteriores intactos
        assert len(coll["state"]) == 7 and coll["mute"]["title"] and coll["det"]["tab_overview"]


def test_os_marcadores_existem_em_todos_os_idiomas():
    """Se um idioma perder o {id} ou o {n}, o utilizador fica sem o numero."""
    esperados = {
        ("run", "confirm"): ["{nome}"], ("run", "queued"): ["{id}"],
        ("run", "queued_dots"): ["{id}", "{p}", "{s}"], ("run", "running"): ["{id}"],
        ("run", "done"): ["{ms}", "{n}"], ("run", "failed"): ["{err}"],
        ("run", "timeout_queue"): ["{s}", "{id}"], ("run", "timeout_poller"): ["{s}", "{id}"],
        ("bulk", "confirm_count"): ["{n}"], ("bulk", "confirm_more"): ["{n}"],
        ("bulk", "confirm_skipped"): ["{n}"], ("bulk", "dispatching"): ["{n}"],
        ("bulk", "done_ok"): ["{ok}", "{n}"], ("bulk", "done_failed"): ["{n}"],
        ("toggle", "prompt"): ["{accao}", "{nome}"], ("toggle", "too_short"): ["{n}"],
    }
    for loc in ("pt", "en", "es"):
        for (grupo, chave), marcas in esperados.items():
            texto = LOCS[loc]["coll"][grupo][chave]
            for m in marcas:
                assert m in texto, f"{loc}: {grupo}.{chave} sem {m}"


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    for grupo in ("run", "bulk", "toggle"):
        pt, br = LOCS["pt"]["coll"][grupo], LOCS["pt-BR"]["coll"].get(grupo, {})
        assert [k for k, v in br.items() if pt.get(k) == v] == [], f"{grupo}: chaves repetidas"
        assert set(br) <= set(pt)


def test_o_portal_usa_as_chaves():
    for k in RUN:
        assert f"'coll.run.{k}'" in PORTAL, f"chave nao usada: coll.run.{k}"
    for k in BULK:
        assert f"'coll.bulk.{k}'" in PORTAL, f"chave nao usada: coll.bulk.{k}"
    for k in TOGGLE:
        assert f"'coll.toggle.{k}'" in PORTAL, f"chave nao usada: coll.toggle.{k}"


def test_o_jargao_ingles_desapareceu_das_accoes():
    """O portugues CONTINUA la' como recurso dentro de _collT -- e' assim de proposito.

    O que nao pode sobrar e' o jargao ingles que estas mensagens tinham e que nenhum idioma
    aproveitava: Dispatched, Failed dispatch, PENDING, Rows. Comentarios ficam de fora da conta,
    porque contam a historia do codigo e nao vao para o ecra.
    """
    i = PORTAL.index("window.collTriggerRun = async function()")
    j = PORTAL.index("function _collUpdateToggleUI(task)")
    bloco = "\n".join(l for l in PORTAL[i:j].split("\n") if not l.lstrip().startswith("//"))
    for frase in ("Bulk Re-run", "Dispatched:", "Failed dispatch:", "Tasks falhados (top 5)",
                  "Tasks dispatched estao agora", "task(s) skipped", "PENDING na fila",
                  "Rows: ${rows}", "em execucao...`"):
        assert frase not in bloco, f"ficou por traduzir: {frase}"


def test_nada_de_portugues_no_ingles():
    en = LOCS["en"]["coll"]
    texto = " | ".join(list(en["run"].values()) + list(en["bulk"].values()) + list(en["toggle"].values())).lower()
    for p in ("pedido", "tarefa", "recolha", "motivo", "activar"):
        assert p not in texto, f"ingles com texto portugues: {p}"
