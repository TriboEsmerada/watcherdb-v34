"""
2026-09-16 -- Collector Health (lote 2c): janela de detalhe traduzida, sem depender de texto visivel.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
ABAS = ["tab_overview", "tab_logs", "tab_config", "tab_runs", "tab_audit"]
COLS = ["timestamp", "level", "message", "id", "requested_at", "by", "status", "pickup_lag",
        "error", "datetime", "user", "reason"]


def test_os_tres_idiomas_completos():
    for loc in ("pt", "en", "es"):
        det = LOCS[loc]["coll"]["det"]
        for k in ABAS + ["environment", "interval", "enabled", "status", "data_source", "last_run",
                         "delay", "duration", "rows", "rows_title", "active_slot", "failures_24h",
                         "class", "module", "target_tables", "description", "yes", "no", "no_data",
                         "activate", "deactivate", "run_now", "run_title_on", "run_title_off"]:
            assert det[k].strip(), f"{loc}: det.{k}"
        for c in COLS:
            assert LOCS[loc]["coll"]["col"][c].strip(), f"{loc}: col.{c}"
        # lotes anteriores intactos
        assert len(LOCS[loc]["coll"]["state"]) == 7
        assert LOCS[loc]["coll"]["mute"]["title"].strip()


def test_o_separador_activo_nao_depende_do_texto_visivel():
    """O defeito da manha (comparar por titulo traduzido), agora nos separadores."""
    assert "el.dataset.tab === tabName" in PORTAL
    assert "(el.textContent || '').toLowerCase().includes(tabName.toLowerCase())" not in PORTAL
    assert "tabName === 'runs' && (el.textContent" not in PORTAL, "o remendo do runs tambem sai"
    for aba in ("overview", "logs", "config", "runs", "audit"):
        assert f'data-tab="{aba}"' in PORTAL


def test_a_coluna_tem_rotulo_separado_da_chave():
    """row[col.k] usa a chave; o cabecalho usa col.lbl. Traduzir a chave esvaziaria a tabela."""
    assert "${col.lbl || col.k}${arrow}" in PORTAL
    assert "${col.k}${arrow}" not in PORTAL
    for chave in ("'Timestamp'", "'Requested at'", "'Pickup lag'", "'Data/Hora'"):
        assert f"k:{chave}" in PORTAL, f"a chave dos dados {chave} tem de ficar como esta'"


def test_o_portal_usa_as_chaves_do_detalhe():
    for k in ABAS + ["environment", "interval", "enabled", "data_source", "last_run", "delay",
                     "duration", "rows", "rows_title", "active_slot", "failures_24h", "class",
                     "module", "target_tables", "description", "yes", "no", "no_data", "error",
                     "activate", "deactivate", "run_now", "run_title_on", "run_title_off",
                     "ds_bg", "ds_max", "ds_none", "loading_logs", "empty_logs", "loading_config",
                     "config_source", "loading_runs", "empty_runs", "loading_audit", "empty_audit",
                     "override_on", "override_off", "via_config_on", "via_config_off"]:
        assert f"'coll.det.{k}'" in PORTAL, f"chave nao usada no portal: coll.det.{k}"
    for c in COLS:
        assert f"'coll.col.{c}'" in PORTAL, f"chave nao usada no portal: coll.col.{c}"


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    for grupo in ("det", "col"):
        pt, br = LOCS["pt"]["coll"][grupo], LOCS["pt-BR"]["coll"].get(grupo, {})
        assert [k for k, v in br.items() if pt.get(k) == v] == [], f"{grupo}: chaves repetidas"
        assert set(br) <= set(pt)


def test_nada_de_portugues_no_ingles():
    texto = " | ".join(list(LOCS["en"]["coll"]["det"].values()) + list(LOCS["en"]["coll"]["col"].values())).lower()
    for p in ("ambiente", "duração", "última", "utilizador", "activar", "tarefa"):
        assert p not in texto, f"ingles com texto portugues: {p}"
