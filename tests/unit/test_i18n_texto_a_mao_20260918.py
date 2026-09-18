"""
2026-09-18 -- guarda: o texto escrito a` mao em portugues no portal (fora do dicionario) so' pode DESCER.

Linha de base gravada pelo lote I18N_GUARDA_E_FIXOS_2026-09-18 (depois das suas edicoes): strings JS = 886,
texto em tags HTML = 294. Quando um lote baixar estes numeros, actualiza a base aqui (o teste diz o valor novo).
Heuristica identica a` do inventario de 17/09 (docs/context/CONTEXT.md).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
BASE_JS, BASE_TAGS = 886, 294

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
