"""
2026-09-17 -- cartao de Disk Latency: chaves dlat.* em pt/en/es, overlay pt-BR so' com diferencas, template sem texto a` mao.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LOC = {k: json.load(open(ROOT / f"static/i18n/{k}.json", encoding="utf-8")) for k in ("pt", "en", "es", "pt-BR")}
CHAVES = ["drive", "read", "write", "disk_busy", "iops_read", "iops_write", "causes", "tip_low_iops_title", "tip_low_iops",
          "tip_read_title", "tip_read", "tip_busy_title", "tip_busy", "tip_cdrive_title", "tip_cdrive", "diag_title",
          "diag_raid", "diag_storage", "diag_perfmon", "run_diag", "more"]


def test_grupo_dlat_completo_em_pt_en_es():
    for loc in ("pt", "en", "es"):
        g = LOC[loc].get("dlat") or {}
        assert sorted(g) == sorted(CHAVES), (loc, sorted(set(CHAVES) ^ set(g)))
        assert all(isinstance(v, str) and v.strip() for v in g.values())


def test_overlay_ptbr_so_com_o_que_difere():
    over = LOC["pt-BR"].get("dlat") or {}
    assert over, "pt-BR precisa de pelo menos arquivos/equipe/status"
    for k, v in over.items():
        assert k in CHAVES and LOC["pt"]["dlat"][k] != v, f"pt-BR repete o pt-PT em {k}"


def test_placeholder_pct_em_todos():
    for loc in ("pt", "en", "es"):
        assert "{pct}" in LOC[loc]["dlat"]["tip_busy_title"]


def test_template_usa_as_chaves_e_nao_o_texto_antigo():
    for k in CHAVES:
        assert f"t('dlat.{k}')" in PORTAL, k
    for antigo in ("IOPS Leitura:", "Possiveis causas e diagnostico", "Diagnostico recomendado:", "Executar Diagnostico de I/O",
                   "Consultar equipe de storage", "Latencia alta com IOPS baixo"):
        assert antigo not in PORTAL, antigo


def test_a_percentagem_da_dica_e_mesmo_interpolada():
    assert "t('dlat.tip_busy_title').replace('{pct}', diskTimePct.toFixed(0))" in PORTAL
    assert "(${diskTimePct.toFixed(0)}%):</strong>" not in PORTAL, "${} dentro de aspas simples nao interpola"


def test_pt_sem_grafia_antiga():
    txt = json.dumps(LOC["pt"]["dlat"], ensure_ascii=False)
    assert not re.search(r"desabilitad|arquivos|equipe|\bstatus\b", txt)
