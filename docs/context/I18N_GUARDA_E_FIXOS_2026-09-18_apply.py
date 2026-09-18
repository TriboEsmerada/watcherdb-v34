# -*- coding: utf-8 -*-
"""i18n, lote 1: teste de guarda que fixa o texto escrito a` mao no portal + os 5 textos da marcacao estatica (2026-09-18).

MEDIDO A 18/09 (correccao ao inventario de ontem): dos 208 textos em portugues dentro de tags HTML fora do i18n, so' 5
estao na marcacao estatica do template; 203 estao em HTML gerado por JavaScript (template literals e concatenacoes
dentro de <script>). A ferramenta para esses e' t() nas funcoes, por regiao, com leitura linha a linha -- nao data-i18n.
Alem desses, ~1.000 strings JS (toasts, estados vazios, rotulos) tambem estao fora do dicionario.

O QUE FAZ:
 1. tests/unit/test_i18n_texto_a_mao_20260918.py: varre o template com duas heuristicas deterministas (strings JS com
    marcadores de portugues fora de t()/_kpiT/_collT/_chT/data-i18n e sem console/debug; texto em portugues dentro de
    tags HTML nas mesmas condicoes) e FALHA se o numero subir acima da linha de base gravada neste lote. A linha de base
    e' calculada no momento do apply (depois das edicoes) e escrita no teste. Baixar e' sempre permitido; ao baixar,
    actualiza-se a base no proprio teste (o teste diz o numero novo).
 2. Os 5 textos da marcacao estatica passam a data-i18n com o grupo novo `fixo` (pt/en/es; pt-BR so' o que difere).

Uso (raiz do repo):
  py docs/context/I18N_GUARDA_E_FIXOS_2026-09-18_apply.py --check
  py docs/context/I18N_GUARDA_E_FIXOS_2026-09-18_apply.py
  py -m pytest tests/unit/test_i18n_texto_a_mao_20260918.py tests/unit/test_i18n_parity.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {"portal": Path("templates/watcherdb_portal.html"), "pt": Path("static/i18n/pt.json"), "en": Path("static/i18n/en.json"),
       "es": Path("static/i18n/es.json"), "ptbr": Path("static/i18n/pt-BR.json"), "changelog": Path("docs/changelog/CHANGELOG.md"),
       "test": Path("tests/unit/test_i18n_texto_a_mao_20260918.py")}
MARK = 'data-i18n="fixo.'

GRUPOS = {
    "pt": {"predictive_title": "Análise preditiva", "confirm_new_password": "Confirmar nova senha",
           "diagnose_subtitle": "Cole a query problemática para análise de estatísticas e índices",
           "full_db_analysis": "Análise completa da base de dados", "required": "(obrigatório)"},
    "en": {"predictive_title": "Predictive analysis", "confirm_new_password": "Confirm new password",
           "diagnose_subtitle": "Paste the problem query to analyse statistics and indexes",
           "full_db_analysis": "Full database analysis", "required": "(required)"},
    "es": {"predictive_title": "Análisis predictivo", "confirm_new_password": "Confirmar nueva contraseña",
           "diagnose_subtitle": "Pegue la consulta problemática para analizar estadísticas e índices",
           "full_db_analysis": "Análisis completo de la base de datos", "required": "(obligatorio)"},
    "ptbr": {"full_db_analysis": "Análise completa do banco de dados"},
}

PORTAL_EDITS = [
    ('<h2 id="modalTitle" style="font-size: 20px; margin: 0;">Análise Preditiva</h2>',
     '<h2 id="modalTitle" style="font-size: 20px; margin: 0;" data-i18n="fixo.predictive_title">Análise Preditiva</h2>', 1),
    ('<label style="color:var(--color-text-tertiary); font-size:12px; display:block; margin-bottom:4px;">Confirmar Nova Senha</label>',
     '<label style="color:var(--color-text-tertiary); font-size:12px; display:block; margin-bottom:4px;" data-i18n="fixo.confirm_new_password">Confirmar Nova Senha</label>', 1),
    ('<p id="diagnoseQueryModalSubtitle">Cole a query problemática para análise de estatísticas e índices</p>',
     '<p id="diagnoseQueryModalSubtitle" data-i18n="fixo.diagnose_subtitle">Cole a query problemática para análise de estatísticas e índices</p>', 1),
    ('<span style="color: var(--color-text-bright); font-weight: 600;">Análise Completa do Banco de Dados</span>',
     '<span style="color: var(--color-text-bright); font-weight: 600;" data-i18n="fixo.full_db_analysis">Análise Completa do Banco de Dados</span>', 1),
    ('<span id="diagnoseDatabaseRequired" style="color: #ef4444; display: none;">(obrigatório)</span>',
     '<span id="diagnoseDatabaseRequired" style="color: #ef4444; display: none;" data-i18n="fixo.required">(obrigatório)</span>', 1),
]

# O varredor vive aqui UMA vez: o apply usa-o para calcular a base; o teste recebe o mesmo codigo.
SCANNER_SRC = r'''
import re

_PT = re.compile(r"\b(nao|sao|voce|Clique|Nenhum|Nenhuma|Carregando|Aguarde|Ultima|ultima|atualiz|actualiz|Erro ao|Sem dados|Falha ao|Detalhes|Fechar|Filtrar|Mostrar|ocultar|Executar|Verificar|Confirmar|Selecione|selecione|instancia|instância|base de dados|bases de dados|agendamento|utilizador|ficheiro|tamanho|dias|horas|minutos|PORQUE|O QUE|QUANDO|COMO)\b|[ãõçáéíóúâêôà]", re.I)
_JA_I18N = re.compile(r"\bt\(|_kpiT\(|_kpiTp\(|_collT\(|_collTp\(|_chT\(|data-i18n|i18n\.|WatcherI18N")
_NAO_VISIVEL = re.compile(r"console\.|logger\.|\.debug\(|debugLog|//|/\*|^\s*\*|\[DBG\]|n[aã]o encontrado|inv[aá]lido ao carregar|contentArea|Container de resultados")
_ES = re.compile(r"\b(instancias con|Monitorea|Sin |páginas|sospechosas|días|Verifica si|Filtra instancias)\b")
_RECURSOS = ("CARD_HELP_TEXTS", "BACKUP_KPI_INFO")   # dicionarios que sao so' recurso do i18n (as chaves existem)


def _dono(linhas, n):
    for k in range(n, max(0, n - 600), -1):
        m = re.match(r"\s*(?:const|let|var)\s+([A-Z_][A-Z0-9_]{3,})\s*=", linhas[k - 1])
        if m:
            return m.group(1)
        m = re.match(r"\s*(?:async\s+)?function\s+(\w+)", linhas[k - 1])
        if m:
            return m.group(1) + "()"
    return "?"


def contar_texto_a_mao(html: str):
    """Devolve (strings_js, html_em_tags, exemplos). Deterministico; e' a linha de base do teste de guarda."""
    linhas = html.split("\n")
    js, tags, exemplos = 0, 0, []
    for i, ln in enumerate(linhas, 1):
        s = ln.strip()
        if _NAO_VISIVEL.search(s) or _JA_I18N.search(s):
            continue
        dono = _dono(linhas, i)
        if dono in _RECURSOS:
            continue
        for m in re.finditer(r"""(['"`])((?:\\.|(?!\1).){12,}?)\1""", s):
            t = m.group(2)
            if _PT.search(t) and not _ES.search(t) and not re.search(r"^(https?:|/api|#|\.|rgba?\(|var\(|--|\d)", t):
                js += 1
                if len(exemplos) < 8:
                    exemplos.append(f"L{i} js {t[:60]!r}")
        for m in re.finditer(r">\s*([^<>{}]{6,}?)\s*<", s):
            t = m.group(1)
            if _PT.search(t) and "${" not in t and not re.search(r"^[\d\s.,:%-]+$", t):
                tags += 1
                if len(exemplos) < 8:
                    exemplos.append(f"L{i} html {t[:60]!r}")
    return js, tags, exemplos
'''

TEST_TEMPLATE = r'''"""
2026-09-18 -- guarda: o texto escrito a` mao em portugues no portal (fora do dicionario) so' pode DESCER.

Linha de base gravada pelo lote I18N_GUARDA_E_FIXOS_2026-09-18 (depois das suas edicoes): strings JS = __JS__,
texto em tags HTML = __TAGS__. Quando um lote baixar estes numeros, actualiza a base aqui (o teste diz o valor novo).
Heuristica identica a` do inventario de 17/09 (docs/context/CONTEXT.md).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
BASE_JS, BASE_TAGS = __JS__, __TAGS__
__SCANNER__

def test_texto_a_mao_nao_sobe():
    js, tags, exemplos = contar_texto_a_mao(PORTAL)
    msg = (f"texto a` mao: strings JS={js} (base {BASE_JS}), tags HTML={tags} (base {BASE_TAGS}). "
           f"Subiu: passa o texto novo por t('grupo.chave'). Exemplos: {exemplos}")
    assert js <= BASE_JS and tags <= BASE_TAGS, msg
    if js < BASE_JS or tags < BASE_TAGS:
        print(f"[i18n] texto a` mao desceu para JS={js}, tags={tags} -- actualiza BASE_JS/BASE_TAGS neste teste")


def test_os_5_textos_fixos_passam_pelo_dicionario():
    for k in ("predictive_title", "confirm_new_password", "diagnose_subtitle", "full_db_analysis", "required"):
        assert f'data-i18n="fixo.{k}"' in PORTAL, k
    for loc in ("pt", "en", "es"):
        g = json.load(open(ROOT / f"static/i18n/{loc}.json", encoding="utf-8"))["fixo"]
        assert sorted(g) == ["confirm_new_password", "diagnose_subtitle", "full_db_analysis", "predictive_title", "required"], loc
    over = json.load(open(ROOT / "static/i18n/pt-BR.json", encoding="utf-8")).get("fixo") or {}
    pt = json.load(open(ROOT / "static/i18n/pt.json", encoding="utf-8"))["fixo"]
    assert over and all(pt[k] != v for k, v in over.items())
'''

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **i18n: teste de guarda para texto escrito à mão** (18/09). Um varredor determinista conta as strings e o HTML em\n"
    "  português fora do dicionário no portal e falha se o número subir; a base fica gravada no teste e só pode descer.\n"
    "  Os cinco textos da marcação estática (títulos das modais preditiva e de diagnóstico, \"(obrigatório)\", confirmação\n"
    "  de senha) passam a `fixo.*` em pt/pt-BR/en/es. [tier: Std]\n\n",
    1,
)


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
    antes = json.loads(texto)
    if "fixo" in antes:
        raise SystemExit(f"[ABORT] {label}: grupo fixo ja existe")
    corpo = texto.rstrip()
    if not corpo.endswith("}"):
        raise SystemExit(f"[ABORT] {label}: fim inesperado")
    corpo = corpo[:-1].rstrip()
    bloco = json.dumps(grupo, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    novo = corpo + ',\n  "fixo": ' + bloco + "\n}\n"
    depois = json.loads(novo)
    assert {k: v for k, v in depois.items() if k != "fixo"} == antes, f"{label}: o resto do ficheiro mudou"
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    out = {"portal": _apply(portal, PORTAL_EDITS, "portal"), "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    for loc in ("pt", "en", "es", "ptbr"):
        out[loc] = _inserir_grupo(src[loc].read_bytes().decode("utf-8"), GRUPOS[loc], loc)
    ns: dict = {}
    exec(SCANNER_SRC, ns)
    js, tags, _ = ns["contar_texto_a_mao"](out["portal"].replace("\r\n", "\n"))
    test_src = TEST_TEMPLATE.replace("__JS__", str(js)).replace("__TAGS__", str(tags)).replace("__SCANNER__", SCANNER_SRC)
    compile(test_src, str(REL["test"]), "exec")
    print(f"[ok] portal 5 data-i18n; pt/en/es +5 chaves fixo; pt-BR +1; changelog; teste de guarda com base JS={js}, tags HTML={tags}")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(test_src.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_i18n_texto_a_mao_20260918.py tests/unit/test_i18n_parity.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
