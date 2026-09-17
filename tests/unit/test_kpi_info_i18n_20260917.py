"""
2026-09-17 -- ajuda "?" das modais de backup: chaves kpi_info.* nos locales; o consumidor passa por _kpiT.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LOC = {k: json.load(open(ROOT / f"static/i18n/{k}.json", encoding="utf-8")) for k in ("pt", "en", "es", "pt-BR")}
CHAVES = ["backup_failed", "backup_log_failed", "backup_delayed", "backup_jobs_disabled", "backup_no_checksum"]


def test_grupo_kpi_info_completo_em_pt_en_es():
    for loc in ("pt", "en", "es"):
        g = LOC[loc].get("kpi_info") or {}
        assert sorted(g) == sorted(CHAVES), (loc, sorted(set(CHAVES) ^ set(g)))
        assert all(len(v) > 200 and "\n\n" in v for v in g.values()), loc


def test_overlay_ptbr_so_com_o_que_difere():
    over = LOC["pt-BR"].get("kpi_info") or {}
    assert over
    for k, v in over.items():
        assert k in CHAVES and LOC["pt"]["kpi_info"][k] != v, k


def test_pt_acentuado_e_ao90():
    txt = json.dumps(LOC["pt"]["kpi_info"], ensure_ascii=False)
    assert "NÃO" in txt and "execução" in txt and "última" in txt
    assert not re.search(r"desactiv|activ[oa]r?\b|reactiv|actual\b|correcç|detecta\b|protecç", txt)


def test_o_consumidor_passa_pelo_dicionario_de_idiomas():
    assert "_kpiT('kpi_info.' + String(kpiType).replace(/-/g, '_'), BACKUP_KPI_INFO[kpiType])" in PORTAL
    assert "const kpiInfo = BACKUP_KPI_INFO[kpiType];" not in PORTAL
    for k in CHAVES:  # o recurso em portugues continua la' (nunca se mostra chave crua)
        assert f"'{k.replace('_', '-')}': '" in PORTAL
