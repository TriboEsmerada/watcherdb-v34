# -*- coding: utf-8 -*-
"""Collector Health, revisão linguística do grupo `coll` (2026-09-16, fim do dia).

PARECER do v33-i18n-linguist: WARN -- nao ir para cliente tal como estava. E a medicao feita a seguir mostrou que o
problema era maior do que o parecer dizia:
 - ORTOGRAFIA: o resto do pt.json esta' no Acordo de 1990 (atualizar 24x0, ativo 43x7, acao 24x0, atual 36x6,
   direto 5x0, correcao 3x0); o grupo coll escrito hoje esta' INTEIRO na grafia antiga (activ 21, acc 4, actualiz 2,
   actual 2, direct 1, correcc 1, excepcao, detectado). Nao e' "Actualizar" que esta' mal -- e' o grupo todo.
 - TERMO DA CASA: "frota" (pt), "fleet" (en), "flota" (es) -- o coll usou "parque"/"estate"/"parque" nos 7 estados
   e na legenda dos eventos (o proprio coll.events.subtitle em pt ja dizia "frota").
 - pt-BR: padrao do overlay e' gerundio ("Carregando" 42x0 "A carregar") e "Buscar" (5x0 "Pesquisar"); o coll trouxe
   "A registrar", "A carregar", "Pesquisar". E "Ultima execucao" quebrava a distincao pt entre passagem (ciclo
   automatico) e execucao (corrida manual).
 - Placeholders, glossario (Collector Health, Blue/Green, recolhedor/coletor/colector/collector) e sentido: sem
   problemas.

O QUE FAZ (programatico, nao a` mao -- sao 194 chaves x 4 ficheiros):
 1. pt: converte o grupo coll para o Acordo de 1990 com uma lista EXPLICITA de palavras (nao regex cega: "facto",
    "contacto", "seccao" ficam como estao em pt-PT); "parque" -> "frota"; "Procurar" -> "Pesquisar" (convencao do
    ficheiro).
 2. en: "estate" -> "fleet".  es: "parque" -> "flota" (com o artigo certo).
 3. pt-BR: recalculado a partir do pt novo: mantem os overrides escritos a` mao (coletor, rodou, registro...), corrige
    os 5 que o linguista apanhou, acrescenta os que o padrao do overlay exige (Carregando, registro(s), Buscar) e
    REMOVE todos os que ficaram iguais ao pt depois da conversao (ex.: "Ação recomendada", "ATIVAR", "Reativar" --
    so' existiam por causa de "acção/ação" e "activo/ativo").
 4. Regenera o bloco "coll" de cada ficheiro (e' o ultimo grupo); todos os outros grupos ficam byte a byte iguais.
 5. Teste de guarda: sem grafia antiga no coll pt, sem parque/estate, pt-BR sem "A carregar"/"Pesquisar"/"A registrar"
    e sem chaves iguais ao pt.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_I18N_REVISAO_2026-09-16_apply.py --check
  py docs/context/COLL_I18N_REVISAO_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_i18n_revisao_20260916.py tests/unit/test_coll_i18n_modal_20260916.py tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_mute_20260916.py tests/unit/test_coll_i18n_detalhe_20260916.py tests/unit/test_coll_i18n_accoes_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALES = {loc: Path(f"static/i18n/{loc}.json") for loc in ("pt", "pt-BR", "en", "es")}
REL = {"changelog": Path("docs/changelog/CHANGELOG.md"), "test": Path("tests/unit/test_coll_i18n_revisao_20260916.py")}
MARK_TESTE = "test_coll_i18n_revisao_20260916"

# ------------------------------------------------------------------ 1. pt: Acordo de 1990, lista explicita
AO90 = [
    ("actualiz", "atualiz"), ("Actualiz", "Atualiz"),
    ("activ", "ativ"), ("Activ", "Ativ"),            # activo, activar, reactivar, desactivar, activacoes
    ("acção", "ação"), ("Acção", "Ação"), ("acções", "ações"),
    ("correcção", "correção"), ("excepção", "exceção"), ("Excepção", "Exceção"),
    ("detectad", "detetad"), ("directo", "direto"), ("directa", "direta"),
    ("actual", "atual"), ("Actual", "Atual"),
]
PT_TERMOS = [("no parque", "na frota"), ("parque a funcionar", "frota a funcionar"), ("Procurar por nome", "Pesquisar por nome")]
EN_TERMOS = [("not the estate", "not the fleet"), ("across the estate", "across the fleet"), ("the estate is working", "the fleet is working")]
ES_TERMOS = [("no el parque", "no la flota"), ("en el parque", "en la flota"), ("el parque funciona", "la flota funciona")]

# ------------------------------------------------------------------ 3. pt-BR: padrao do overlay
BR_MECANICO = [
    ("A carregar", "Carregando"), ("a carregar", "carregando"),
    ("A registar", "Registrando"), ("a registar", "registrando"),
    ("registados", "registrados"), ("registadas", "registradas"), ("registado", "registrado"), ("registada", "registrada"),
    ("registos", "registros"), ("registo", "registro"), ("registar", "registrar"),
    ("Pesquisar por nome", "Buscar por nome"),
    ("recolhedor", "coletor"), ("recolhedores", "coletores"), ("recolha", "coleta"),
    ("utilizador", "usuário"), ("utilizadores", "usuários"),
    ("ficheiro", "arquivo"), ("base de dados", "banco de dados"),
]
# correccoes explicitas apanhadas pelo linguista nos overrides ja escritos a` mao
BR_FIX = {
    "run.registering": "Registrando o pedido...",
    "run.st_registering": "Registrando o pedido",
    "det.loading_audit": "Carregando o histórico de ativações e desativações...",
    "search_ph": "Buscar por nome...",
}
BR_REMOVER = {"det.last_run"}   # quebrava passagem (ciclo automatico) vs execucao (manual); herda o pt


def _achatar(d, p=""):
    s = {}
    for k, v in d.items():
        s.update(_achatar(v, p + k + ".")) if isinstance(v, dict) else s.update({p + k: v})
    return s


def _aninhar(plano):
    raiz = {}
    for k, v in plano.items():
        cur = raiz
        partes = k.split(".")
        for p in partes[:-1]:
            cur = cur.setdefault(p, {})
        cur[partes[-1]] = v
    return raiz


def _subst(texto, pares):
    for a, b in pares:
        texto = texto.replace(a, b)
    return texto


def _regenerar(raw: str, coll_novo: dict, loc: str) -> str:
    """Substitui o bloco "coll" (ultimo grupo) mantendo tudo o resto byte a byte."""
    ancora = '  "coll": {\n'
    if raw.count(ancora) != 1:
        raise SystemExit(f"[ABORT] {loc}: grupo coll nao encontrado uma unica vez")
    antes = json.loads(raw)
    i = raw.index(ancora)
    texto = json.dumps({"coll": coll_novo}, ensure_ascii=False, indent=2)
    bloco = "\n".join(texto.split("\n")[1:-1])
    novo = raw[:i] + bloco + "\n}\n"
    d = json.loads(novo)
    for k in antes:
        if k != "coll":
            assert d[k] == antes[k], f"{loc}: o grupo {k} mudou"
    assert set(_achatar(d["coll"])) <= set(_achatar(antes["coll"])) | set(_achatar(coll_novo)), loc
    return novo


CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: revisão linguística das 194 chaves** (16/09). O grupo escrito hoje estava inteiro na grafia\n"
    "  anterior ao Acordo de 1990 (\"activo\", \"acção\", \"actualizar\") num ficheiro que usa a nova em todo o lado; passa\n"
    "  a AO90. \"Parque\"/\"estate\" dão lugar ao termo da casa — frota, fleet, flota. O português do Brasil deixa de\n"
    "  herdar \"A carregar\" e \"Pesquisar\" (usa gerúndio e \"Buscar\", como o resto do sobreposto) e perde as chaves\n"
    "  que só existiam por causa da grafia. Parecer: v33-i18n-linguist. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = r'''"""
2026-09-16 -- revisao linguistica do grupo coll: AO90 no pt, termo da casa (frota/fleet/flota), pt-BR no padrao do overlay.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}


def achatar(d, p=""):
    s = {}
    for k, v in d.items():
        s.update(achatar(v, p + k + ".")) if isinstance(v, dict) else s.update({p + k: v})
    return s


PT = achatar(LOCS["pt"]["coll"]); BR = achatar(LOCS["pt-BR"]["coll"]); EN = achatar(LOCS["en"]["coll"]); ES = achatar(LOCS["es"]["coll"])


def test_pt_esta_no_acordo_de_1990_como_o_resto_do_ficheiro():
    texto = " ".join(PT.values())
    for antigo in ("actualiz", "Actualiz", "activ", "Activ", "acção", "Acção", "correcção", "excepção", "Excepção",
                   "detectad", "directo", "directa", "actual", "Actual"):
        assert antigo not in texto, f"grafia antiga no coll pt: {antigo}"


def test_termo_da_casa_frota_fleet_flota():
    assert "parque" not in " ".join(PT.values()).lower() and "frota" in " ".join(PT.values()).lower()
    assert "estate" not in " ".join(EN.values()).lower() and "fleet" in " ".join(EN.values()).lower()
    assert "parque" not in " ".join(ES.values()).lower() and "flota" in " ".join(ES.values()).lower()


def test_pt_br_segue_o_padrao_do_overlay():
    texto = " ".join(BR.values())
    for pt_pt in ("A carregar", "A registar", "A registrar", "Pesquisar", "recolhedor", "registo ", "registado"):
        assert pt_pt not in texto, f"pt-BR com construcao pt-PT: {pt_pt!r}"
    # onde o pt diz "A carregar", o pt-BR tem de ter override em gerundio
    for k, v in PT.items():
        if "A carregar" in v:
            assert k in BR and "Carregando" in BR[k], f"pt-BR sem override em gerundio para {k}"


def test_pt_br_nao_repete_o_pt_nem_perde_o_que_difere():
    iguais = [k for k, v in BR.items() if PT.get(k) == v]
    assert iguais == [], f"chaves pt-BR iguais ao pt: {iguais}"
    assert set(BR) <= set(PT)
    assert "det.last_run" not in BR, "pt-BR nao pode quebrar a distincao passagem (automatico) / execucao (manual)"
    assert BR["search_ph"] == "Buscar por nome..." and BR["run.st_registering"] == "Registrando o pedido"


def test_marcadores_sobrevivem_em_todos_os_idiomas():
    for k, v in PT.items():
        marcas = set(re.findall(r"\{[a-z]+\}", v))
        for loc, d in (("pt-BR", {**PT, **BR}), ("en", EN), ("es", ES)):
            assert set(re.findall(r"\{[a-z]+\}", d[k])) == marcas, f"{loc}: {k} perdeu ou ganhou marcadores"
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


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    if (base / REL["test"]).exists():
        print("[ABORT] ja aplicado (teste existe)"); return 1

    raws = {loc: (base / rel).read_bytes().decode("utf-8") for loc, rel in LOCALES.items()}
    pt = _achatar(json.loads(raws["pt"])["coll"])
    br_antigo = _achatar(json.loads(raws["pt-BR"])["coll"])
    en = _achatar(json.loads(raws["en"])["coll"])
    es = _achatar(json.loads(raws["es"])["coll"])

    # 1. pt
    pt_novo = {k: _subst(_subst(v, AO90), PT_TERMOS) for k, v in pt.items()}
    # 2. en / es
    en_novo = {k: _subst(v, EN_TERMOS) for k, v in en.items()}
    es_novo = {k: _subst(v, ES_TERMOS) for k, v in es.items()}
    # 3. pt-BR: base = override existente (ja BR) ou pt novo transformado; depois fixes, remocoes e dedupe
    br_novo = {}
    for k, v_pt in pt_novo.items():
        base_v = br_antigo.get(k, v_pt)
        base_v = _subst(_subst(base_v, AO90), BR_MECANICO)
        br_novo[k] = base_v
    for k, v in BR_FIX.items():
        br_novo[k] = v
    for k in BR_REMOVER:
        br_novo.pop(k, None)
    br_novo = {k: v for k, v in br_novo.items() if v != pt_novo.get(k)}

    novos = {"pt": pt_novo, "pt-BR": br_novo, "en": en_novo, "es": es_novo}
    saidas = {loc: _regenerar(raws[loc], _aninhar(novos[loc]), loc) for loc in LOCALES}

    # medidas para a entrega
    def conta(vals, *radicais):
        t = " ".join(vals)
        return {r: t.count(r) for r in radicais}
    print("[ok] pt: grafia antiga ->", conta(pt_novo.values(), "activ", "acç", "actualiz", "actual", "direct", "correcç", "excepç"),
          "| parque:", sum(v.lower().count("parque") for v in pt_novo.values()))
    print("[ok] en: estate ->", sum(v.lower().count("estate") for v in en_novo.values()),
          "| es: parque ->", sum(v.lower().count("parque") for v in es_novo.values()))
    print(f"[ok] pt-BR: {len(br_antigo)} overrides -> {len(br_novo)} (removidos {len(set(br_antigo) - set(br_novo))}, "
          f"acrescentados {len(set(br_novo) - set(br_antigo))}, iguais ao pt: {sum(1 for k, v in br_novo.items() if v == pt_novo.get(k))})")
    mudadas = sum(1 for k in pt if pt[k] != pt_novo[k])
    print(f"[ok] pt: {mudadas} de {len(pt)} chaves alteradas")

    changelog = _apply((base / REL["changelog"]).read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    compile(TEST_SRC, str(REL["test"]), "exec")
    if check:
        print("--check OK. Nada escrito."); return 0
    for loc, rel in LOCALES.items():
        (base / rel).write_bytes(saidas[loc].encode("utf-8")); print(f"[write] {rel}")
    (base / REL["changelog"]).write_bytes(changelog.encode("utf-8")); print(f"[write] {REL['changelog']}")
    (base / REL["test"]).write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre os testes coll (ver cabecalho) e Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
