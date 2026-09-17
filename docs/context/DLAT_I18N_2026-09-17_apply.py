# -*- coding: utf-8 -*-
"""Cartao de Disk Latency (modal do KPI) em quatro idiomas (2026-09-17).

CAPTURA DO OWNER (16/09): portal em ingles, cartao em portugues -- Leitura/Escrita/Uso Disco, IOPS Leitura/Escrita,
"Possiveis causas e diagnostico", as quatro dicas, "Diagnostico recomendado" e a lista, "Executar Diagnostico de
I/O", "Clique para mais detalhes". Mesma classe de falha do Collector Health: texto escrito a` mao no template.

DEFEITO APANHADO PELO CAMINHO: a dica "Disco muito ocupado (${diskTimePct.toFixed(0)}%)" estava dentro de uma string
de aspas simples -- o ${...} nunca era interpolado e o ecra mostrava o codigo. Passa a concatenacao com o valor.

O QUE MUDA:
 1. static/i18n/{pt,en,es}.json: grupo novo `dlat` (20 chaves); pt-BR so' com o que difere (6 chaves).
 2. templates/watcherdb_portal.html: os 17 textos do cartao passam a t('dlat.*'); as dicas em aspas simples passam a
    concatenacao (t() nao interpola dentro de '...').
 3. Teste: paridade das chaves, overlay pt-BR so' com diferencas, nenhum texto antigo no template.
 4. De caminho: live.help_region ('activo'), live.sched_tip_workers ('Active' apanhado pela regex) em pt e pt-BR, e
    o override pt-BR live.help_fleet_what igual ao pt-PT -- tests/unit/test_i18n_parity.py ja falhava por eles.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/DLAT_I18N_2026-09-17_apply.py --check
  py docs/context/DLAT_I18N_2026-09-17_apply.py
  py -m pytest tests/unit/test_dlat_i18n_20260917.py tests/unit/test_i18n_parity.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 (KPIs > Disk Health > Drives w/ critical latency)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"), "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"), "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_dlat_i18n_20260917.py"),
}
MARK = "t('dlat.causes')"

GRUPOS = {
    "pt": {
        "drive": "Disco:", "read": "Leitura", "write": "Escrita", "disk_busy": "Uso do disco",
        "iops_read": "IOPS leitura:", "iops_write": "IOPS escrita:",
        "causes": "Possíveis causas e diagnóstico",
        "tip_low_iops_title": "Latência alta com IOPS baixo:",
        "tip_low_iops": "Pode indicar RAID degradado, cache de escrita desativada (bateria BBU em falha) ou problema no storage/SAN.",
        "tip_read_title": "Latência de leitura alta:",
        "tip_read": "Possível fragmentação do disco, disco mecânico (HDD) ou falha iminente do disco.",
        "tip_busy_title": "Disco muito ocupado ({pct}%):",
        "tip_busy": "Congestionamento de I/O. Considere mover ficheiros para discos separados.",
        "tip_cdrive_title": "Disco C: (sistema):",
        "tip_cdrive": "Verificar pagefile, antivírus e se há ficheiros do SQL Server (MDF/LDF/TempDB) neste disco. Ideal: mover para disco dedicado.",
        "diag_title": "Diagnóstico recomendado:",
        "diag_raid": "Verificar o estado do controlador RAID e da bateria da cache",
        "diag_storage": "Consultar a equipa de storage sobre o estado da LUN/volume",
        "diag_perfmon": "PerfMon: Avg. Disk sec/Write, Disk Queue Length",
        "run_diag": "Executar diagnóstico de I/O",
        "more": "Clique para mais detalhes",
    },
    "en": {
        "drive": "Drive:", "read": "Read", "write": "Write", "disk_busy": "Disk busy",
        "iops_read": "Read IOPS:", "iops_write": "Write IOPS:",
        "causes": "Possible causes and diagnosis",
        "tip_low_iops_title": "High latency with low IOPS:",
        "tip_low_iops": "May indicate a degraded RAID, write cache disabled (failed BBU battery) or a storage/SAN problem.",
        "tip_read_title": "High read latency:",
        "tip_read": "Possible disk fragmentation, mechanical disk (HDD) or imminent disk failure.",
        "tip_busy_title": "Disk very busy ({pct}%):",
        "tip_busy": "I/O congestion. Consider moving files to separate disks.",
        "tip_cdrive_title": "Drive C: (system):",
        "tip_cdrive": "Check the pagefile, antivirus and whether SQL Server files (MDF/LDF/TempDB) live on this disk. Ideally move them to a dedicated disk.",
        "diag_title": "Recommended diagnosis:",
        "diag_raid": "Check the RAID controller status and the cache battery",
        "diag_storage": "Ask the storage team about the LUN/volume status",
        "diag_perfmon": "PerfMon: Avg. Disk sec/Write, Disk Queue Length",
        "run_diag": "Run I/O diagnostic",
        "more": "Click for more details",
    },
    "es": {
        "drive": "Unidad:", "read": "Lectura", "write": "Escritura", "disk_busy": "Uso del disco",
        "iops_read": "IOPS lectura:", "iops_write": "IOPS escritura:",
        "causes": "Posibles causas y diagnóstico",
        "tip_low_iops_title": "Latencia alta con IOPS bajo:",
        "tip_low_iops": "Puede indicar RAID degradado, caché de escritura desactivada (batería BBU fallida) o un problema en el storage/SAN.",
        "tip_read_title": "Latencia de lectura alta:",
        "tip_read": "Posible fragmentación del disco, disco mecánico (HDD) o fallo inminente del disco.",
        "tip_busy_title": "Disco muy ocupado ({pct}%):",
        "tip_busy": "Congestión de I/O. Considere mover archivos a discos separados.",
        "tip_cdrive_title": "Unidad C: (sistema):",
        "tip_cdrive": "Verificar pagefile, antivirus y si hay archivos de SQL Server (MDF/LDF/TempDB) en este disco. Ideal: moverlos a un disco dedicado.",
        "diag_title": "Diagnóstico recomendado:",
        "diag_raid": "Verificar el estado del controlador RAID y de la batería de la caché",
        "diag_storage": "Consultar al equipo de storage sobre el estado de la LUN/volumen",
        "diag_perfmon": "PerfMon: Avg. Disk sec/Write, Disk Queue Length",
        "run_diag": "Ejecutar diagnóstico de I/O",
        "more": "Clic para más detalles",
    },
    # overlay: so' o que difere do pt-PT
    "ptbr": {
        "drive": "Drive:",
        "tip_low_iops": "Pode indicar RAID degradado, cache de escrita desativado (bateria BBU com falha) ou problema no storage/SAN.",
        "tip_busy": "Congestionamento de I/O. Considere mover arquivos para discos separados.",
        "tip_cdrive": "Verificar pagefile, antivírus e se há arquivos do SQL Server (MDF/LDF/TempDB) neste disco. Ideal: mover para disco dedicado.",
        "diag_raid": "Verificar o status do controlador RAID e da bateria do cache",
        "diag_storage": "Consultar a equipe de storage sobre o status da LUN/volume",
    },
}

# De caminho: tres chaves do grupo `live` (lote LIVE de 15/09) que ja faziam falhar tests/unit/test_i18n_parity.py
# antes deste lote -- grafia pre-AO90 ("activo"; "Active" apanhado pela regex) e um override pt-BR igual ao pt-PT.
LIVE_FIX = {
    "pt": [
        ('    "help_region": "Ajuda do separador activo",\n', '    "help_region": "Ajuda do separador ativo",\n', 1),
        ('    "sched_tip_workers": "Threads associadas a este scheduler; Active são as que estão a trabalhar agora.",\n',
         '    "sched_tip_workers": "Threads associadas a este scheduler; as ativas são as que estão a trabalhar agora.",\n', 1),
    ],
    "ptbr": [
        ('    "sched_tip_workers": "Threads associadas a este scheduler; Active são as que estão trabalhando agora.",\n',
         '    "sched_tip_workers": "Threads associadas a este scheduler; as ativas são as que estão trabalhando agora.",\n', 1),
        ('    "help_fleet_what": "O estado das instâncias a partir dos KPIs e, em tempo real, só as instâncias com problema: queries pesadas, bloqueios, erros recentes e TempDB.",\n', "", 1),
    ],
}

PORTAL_EDITS = [
    ("</i>Drive: <strong", "</i>${t('dlat.drive')} <strong", 1),
    ("</i>Leitura\n", "</i>${t('dlat.read')}\n", 1),
    ("</i>Escrita\n", "</i>${t('dlat.write')}\n", 1),
    ("</i>Uso Disco\n", "</i>${t('dlat.disk_busy')}\n", 1),
    ("IOPS Leitura: <strong", "${t('dlat.iops_read')} <strong", 1),
    ("IOPS Escrita: <strong", "${t('dlat.iops_write')} <strong", 1),
    ("Possiveis causas e diagnostico\n", "${t('dlat.causes')}\n", 1),
    # as dicas vivem em strings de aspas simples: t() entra por concatenacao (e o ${pct} passa a ser interpolado de facto)
    (">Latencia alta com IOPS baixo:</strong> Pode indicar RAID degradado, cache de escrita desabilitado (bateria BBU falha) ou problema no storage/SAN.</div>'",
     ">' + t('dlat.tip_low_iops_title') + '</strong> ' + t('dlat.tip_low_iops') + '</div>'", 1),
    (">Latencia de leitura alta:</strong> Possivel fragmentacao de disco, disco mecanico (HDD), ou falha iminente do disco.</div>'",
     ">' + t('dlat.tip_read_title') + '</strong> ' + t('dlat.tip_read') + '</div>'", 1),
    (">Disco muito ocupado (${diskTimePct.toFixed(0)}%):</strong> Congestionamento de I/O. Considere mover arquivos para discos separados.</div>'",
     ">' + t('dlat.tip_busy_title').replace('{pct}', diskTimePct.toFixed(0)) + '</strong> ' + t('dlat.tip_busy') + '</div>'", 1),
    (">Drive C: (sistema):</strong> Verificar pagefile, antivirus, e se ha arquivos SQL Server (MDF/LDF/TempDB) neste disco. Ideal: mover para disco dedicado.</div>'",
     ">' + t('dlat.tip_cdrive_title') + '</strong> ' + t('dlat.tip_cdrive') + '</div>'", 1),
    (">Diagnostico recomendado:</div>", ">${t('dlat.diag_title')}</div>", 1),
    ("</i>Verificar status do controlador RAID e bateria do cache</div>", "</i>${t('dlat.diag_raid')}</div>", 1),
    ("</i>Consultar equipe de storage sobre status da LUN/volume</div>", "</i>${t('dlat.diag_storage')}</div>", 1),
    ("</i>PerfMon: Avg. Disk sec/Write, Disk Queue Length</div>", "</i>${t('dlat.diag_perfmon')}</div>", 1),
    ('<i class="fas fa-play"></i> Executar Diagnostico de I/O', '<i class="fas fa-play"></i> ${t(\'dlat.run_diag\')}', 1),
    ("</i> Clique para mais detalhes", "</i> ${t('dlat.more')}", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Cartão de Disk Latency em quatro idiomas** (owner 16/09). O corpo do cartão da modal — métricas, dicas de\n"
    "  diagnóstico, lista recomendada e botões — estava escrito à mão em português; passa a `dlat.*` em pt/pt-BR/en/es.\n"
    "  A dica \"Disco muito ocupado (N%)\" mostrava o código em vez do número (interpolação dentro de aspas simples);\n"
    "  corrigido. De caminho, três chaves do grupo `live` que faziam falhar o teste de paridade i18n (grafia\n"
    "  pré-AO90 e um override pt-BR redundante). [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
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
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:140]!r}")
        text = text.replace(o, n)
    return text


def _inserir_grupo(texto: str, grupo: dict, label: str) -> str:
    """Acrescenta "dlat" no fim do JSON sem re-serializar o resto (a re-serializacao nao e' byte a byte igual)."""
    antes = json.loads(texto)
    if "dlat" in antes:
        raise SystemExit(f"[ABORT] {label}: grupo dlat ja existe")
    corpo = texto.rstrip()
    if not corpo.endswith("}"):
        raise SystemExit(f"[ABORT] {label}: fim inesperado")
    corpo = corpo[:-1].rstrip()
    bloco = json.dumps(grupo, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    novo = corpo + ',\n  "dlat": ' + bloco + "\n}\n"
    depois = json.loads(novo)
    assert {k: v for k, v in depois.items() if k != "dlat"} == antes, f"{label}: o resto do ficheiro mudou"
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    out = {"portal": _apply(portal, PORTAL_EDITS, "portal"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    for loc in ("pt", "en", "es", "ptbr"):
        out[loc] = _inserir_grupo(_apply(src[loc].read_bytes().decode("utf-8"), LIVE_FIX.get(loc, []), loc), GRUPOS[loc], loc)
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal {len(PORTAL_EDITS)} textos -> t('dlat.*'); pt/en/es +{len(GRUPOS['pt'])} chaves; pt-BR +{len(GRUPOS['ptbr'])}; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_dlat_i18n_20260917.py tests/unit/test_i18n_parity.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
