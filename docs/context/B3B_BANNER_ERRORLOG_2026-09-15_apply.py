# -*- coding: utf-8 -*-
"""B3b (2026-09-15) -- errorlog recente no banner de diagnostico da visao geral (host responde, verificacoes falham).

Continuacao do B3 (commit f044057), que pos o bloco no ecra do precheck quando o ping falha. Os reinicios de SQL de
hoje foram todos Ping_OK=1 e Diagnosis sql_down: esse caso cai no banner de diagnostico, nao no precheck.

Parecer da persona DBA cliente (incorporado):
  - Carrega sozinho so quando TODAS as verificacoes falharam ou ha evento offline activo. Falha parcial (ex.: 1 de 5
    por uma consulta lenta, ou o DNS da maquina do recolhedor) nao e sinal fiavel: fica um link a pedido.
  - Recolhido por omissao (o banner ja empurra os cartoes de KPI); titulo e contagem visiveis no resumo.
  - Titulo proprio, sem o tom de servidor caido.
Parecer do frontend-specialist (incorporado):
  - Um so innerHTML com ${kpis}, sem await depois do banner: carregar logo a seguir.
  - A cache da visao geral guarda dados, nunca HTML; no caminho de cache o banner fica vazio. Nada fica preso.
  - Ids sem sufixo: createTab reactiva a aba existente do mesmo servidor.
  - Bloco irmao do banner, nunca dentro da cor de severidade.

Sem mudanca de backend nem de base de dados: usa o endpoint do B3.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/B3B_BANNER_ERRORLOG_2026-09-15_apply.py --check
  py docs/context/B3B_BANNER_ERRORLOG_2026-09-15_apply.py
  py -m pytest tests/unit/test_b3_offline_errorlog_20260915.py tests/unit/test_b3b_banner_errorlog_20260915.py -q --no-cov
  py scripts/i18n_validate.py
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "pt": Path("static/i18n/pt.json"),
    "en": Path("static/i18n/en.json"),
    "es": Path("static/i18n/es.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test_b3": Path("tests/unit/test_b3_offline_errorlog_20260915.py"),
    "test": Path("tests/unit/test_b3b_banner_errorlog_20260915.py"),
}
MARK = "offlineErrorlogBannerBlock"

# ---------------------------------------------------------------- portal: funcoes
BANNER_FN = r"""        // B3b 2026-09-15: o mesmo bloco no banner de diagnostico (host responde, verificacoes falham). Persona: carrega
        // sozinho so com todas as verificacoes falhadas ou evento offline activo; nos parciais so a pedido; recolhido por
        // omissao; titulo proprio. Frontend: irmao do banner, nunca dentro da cor de severidade.
        function offlineErrorlogBannerBlock(instance, auto) {
            const inst = String(instance || '').replace(/\\/g, '_');
            const id = offlineErrorlogId(inst);
            return `<details id="${id}-wrap" ontoggle="_oelBannerToggle(this)"
                         style="background: var(--color-bg-sunken); border: 1px solid var(--color-border); border-radius: 8px; padding: 10px 14px; margin: -8px 0 16px; text-align: left; color: var(--color-text-secondary);">
                    <summary style="cursor: pointer; font-size: 13px;">
                        <i class="fas fa-file-lines" aria-hidden="true"></i>
                        <strong style="color: var(--color-text-primary);">${auto ? _oelT('banner_title', 'Errorlog recente da instância') : _oelT('banner_link', 'Ver errorlog recente desta instância')}</strong>
                        · <span id="${id}-resumo">${auto ? _oelT('loading', 'A ler o errorlog guardado na Intelligence…') : _oelT('banner_on_demand', 'abrir para ler a pedido')}</span>
                    </summary>
                    <div id="${id}" data-inst="${_oelEsc(inst)}" role="status" aria-live="polite" aria-atomic="true" style="margin-top: 10px;">${auto ? _oelLoading() : ''}</div>
                </details>`;
        }
        function _oelBannerToggle(det) {
            const el = det.open ? det.querySelector('[data-inst]') : null;
            if (el && !el.dataset.pedido) loadOfflineErrorlog(el.id, 2);
        }
"""

PORTAL_EDITS = [
    ("        const _OEL_BTN = 'background", BANNER_FN + "        const _OEL_BTN = 'background", 1),
    # um pedido por bloco: o toggle nao volta a carregar o que ja foi pedido
    ("            el.setAttribute('aria-busy', 'true');\n",
     "            el.setAttribute('aria-busy', 'true');\n            el.dataset.pedido = '1';\n", 1),
    # resumo do bloco recolhido (so existe no banner)
    ("style=\"${_OEL_BTN} margin-left: 10px;\">${_oelT('retry', 'Tentar outra vez')}</button>`;\n        }\n        function _oelRender(elId, d) {\n",
     "style=\"${_OEL_BTN} margin-left: 10px;\">${_oelT('retry', 'Tentar outra vez')}</button>`;\n"
     "            const resumo = document.getElementById(elId + '-resumo');\n"
     "            if (resumo) resumo.textContent = !(d && d.success)\n"
     "                ? _kpiTp('overview.offline_errorlog_failed_short', 'leitura falhou', {})\n"
     "                : _kpiTp('overview.offline_errorlog_summary', '{n} linhas classificadas · {s} eventos de segurança',\n"
     "                         { n: +d.events_total || 0, s: +(d.security && d.security.count) || 0 });\n"
     "        }\n        function _oelRender(elId, d) {\n", 1),
    # dentro do banner o titulo ja esta no resumo: fica so o distintivo
    ("                    <i class=\"fas fa-file-lines\" aria-hidden=\"true\" style=\"color: ${neutro};\"></i>\n"
     "                    <strong style=\"color: var(--color-text-primary); font-size: 15px;\">${_oelT('title', 'Errorlog antes da falha')}</strong>\n",
     "                    ${embutido ? '' : `<i class=\"fas fa-file-lines\" aria-hidden=\"true\" style=\"color: ${neutro};\"></i>\n"
     "                    <strong style=\"color: var(--color-text-primary); font-size: 15px;\">${_oelT('title', 'Errorlog antes da falha')}</strong>`}\n", 1),
    ("            const tipoCor = tp =>",
     "            const embutido = !!document.getElementById(elId + '-wrap');\n            const tipoCor = tp =>", 1),
    # renderOverview: estado hoisted ao lado do banner
    ("                let diagBanner = '';\n",
     "                let diagBanner = '';\n                let _oelBannerAuto = false;  // B3b 2026-09-15\n", 1),
    ("                            <div style=\"color:var(--color-text-disabled); font-size:11px; margin-top:6px; font-style:italic;\">${t('overview.diag_perspective')}</div>\n"
     "                        </div>`;\n                }\n\n                const kpis = cacheIndicator + diagBanner + `\n",
     "                            <div style=\"color:var(--color-text-disabled); font-size:11px; margin-top:6px; font-style:italic;\">${t('overview.diag_perspective')}</div>\n"
     "                        </div>\n"
     "                        ${offlineErrorlogBannerBlock(serverId, _hard || !!_evt)}`;\n"
     "                    // B3b 2026-09-15: errorlog recente so carrega sozinho com todas as verificacoes falhadas ou evento offline\n"
     "                    _oelBannerAuto = _hard || !!_evt;\n"
     "                }\n\n                const kpis = cacheIndicator + diagBanner + `\n", 1),
    ("                    ${databasesHtml}\n                    </div>\n                `;\n\n                // Carregar card \"Reboot SO\" async",
     "                    ${databasesHtml}\n                    </div>\n                `;\n\n"
     "                // B3b 2026-09-15: o bloco do errorlog no banner ja esta no DOM (nenhum await desde o banner)\n"
     "                if (diagBanner && _oelBannerAuto) loadOfflineErrorlog(offlineErrorlogId(serverId), 2);\n\n"
     "                // Carregar card \"Reboot SO\" async", 1),
]

I18N = {
    "pt": {
        "offline_errorlog_banner_title": "Errorlog recente da instância",
        "offline_errorlog_banner_link": "Ver errorlog recente desta instância",
        "offline_errorlog_banner_on_demand": "abrir para ler a pedido",
        "offline_errorlog_summary": "{n} linhas classificadas · {s} eventos de segurança",
        "offline_errorlog_failed_short": "leitura falhou",
    },
    "en": {
        "offline_errorlog_banner_title": "Recent error log for this instance",
        "offline_errorlog_banner_link": "View recent error log for this instance",
        "offline_errorlog_banner_on_demand": "open to read on demand",
        "offline_errorlog_summary": "{n} classified lines · {s} security events",
        "offline_errorlog_failed_short": "read failed",
    },
    "es": {
        "offline_errorlog_banner_title": "Errorlog reciente de la instancia",
        "offline_errorlog_banner_link": "Ver errorlog reciente de esta instancia",
        "offline_errorlog_banner_on_demand": "abrir para leer a petición",
        "offline_errorlog_summary": "{n} líneas clasificadas · {s} eventos de seguridad",
        "offline_errorlog_failed_short": "la lectura falló",
    },
}


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Banner de diagnóstico da visão geral com o errorlog recente** (B3b, owner 15/09). Quando o host responde\n"
                  "  mas as verificações da WatcherDB falham (o caso dos reinícios de SQL), o bloco do B3 aparece por baixo do\n"
                  "  banner, recolhido, com a contagem no resumo. Carrega sozinho só quando todas as verificações falharam ou há\n"
                  "  evento offline activo; nas falhas parciais fica um link que lê a pedido. [tier: Std]\n"
                  "\n", 1)

B3_TEST_EDIT = ("        assert set(novas) == chaves and len(chaves) == 23, loc\n",
                "        assert set(novas) == chaves and len(chaves) == 28, loc  # B3b: +5 chaves do banner\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- B3b: errorlog recente no banner de diagnostico da visao geral.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")
FN = PORTAL[PORTAL.index("// B3b 2026-09-15: o mesmo bloco no banner"):PORTAL.index("const _OEL_BTN = ")]
LOAD = PORTAL[PORTAL.index("async function loadOfflineErrorlog("):PORTAL.index("function _oelRender(elId, d) {")]
OVERVIEW = PORTAL[PORTAL.index("async function renderOverview() {"):PORTAL.index("// Carregar card \"Reboot SO\" async")]


def test_carrega_sozinho_so_com_falha_total_ou_evento():
    banner = OVERVIEW[OVERVIEW.index("diagBanner = `"):OVERVIEW.index("const kpis = cacheIndicator + diagBanner")]
    assert "${offlineErrorlogBannerBlock(serverId, _hard || !!_evt)}`;" in banner
    assert "_oelBannerAuto = _hard || !!_evt;" in banner
    # irmao do banner: depois de fechar a div com a cor de severidade
    assert banner.index("</div>\n                        ${offlineErrorlogBannerBlock") > banner.index("overview.diag_perspective")
    assert "let _oelBannerAuto = false;" in OVERVIEW
    assert OVERVIEW.index("let _oelBannerAuto = false;") < OVERVIEW.index("_oelBannerAuto = _hard")


def test_carrega_depois_do_innerhtml_sem_await_pelo_meio():
    fim = OVERVIEW.rstrip()
    assert fim.endswith("if (diagBanner && _oelBannerAuto) loadOfflineErrorlog(offlineErrorlogId(serverId), 2);")
    depois_do_banner = OVERVIEW[OVERVIEW.index("const kpis = cacheIndicator + diagBanner"):]
    codigo = "\n".join(l for l in depois_do_banner.splitlines() if not l.strip().startswith("//"))
    assert "await " not in codigo


def test_recolhido_a_pedido_e_um_so_pedido():
    assert '<details id="${id}-wrap" ontoggle="_oelBannerToggle(this)"' in FN
    assert " open" not in FN.split("function _oelBannerToggle")[0]
    assert "if (el && !el.dataset.pedido) loadOfflineErrorlog(el.id, 2);" in FN
    assert "el.dataset.pedido = '1';" in LOAD
    assert "resumo.textContent = " in LOAD and "innerHTML" not in LOAD.split("const resumo = ")[1]
    assert "const embutido = !!document.getElementById(elId + '-wrap');" in PORTAL


def test_chaves_do_banner_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        ov = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["overview"]
        for k in ("banner_title", "banner_link", "banner_on_demand", "summary", "failed_short"):
            assert ov["offline_errorlog_" + k].strip(), (loc, k)
        assert "{n}" in ov["offline_errorlog_summary"] and "{s}" in ov["offline_errorlog_summary"], loc
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal_raw = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal_raw:
        print("[ABORT] ja aplicado"); return 1
    if "function loadOfflineErrorlog(" not in portal_raw:
        print("[ABORT] o B3 nao esta aplicado neste portal"); return 1
    out = {"portal": _apply(portal_raw, PORTAL_EDITS, "portal")}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if set(I18N[loc]) & set(json.loads(raw)["overview"]):
            raise SystemExit(f"[ABORT] {loc}: chaves novas ja existem em overview")
        txt = _apply(raw, [('\n  "overview": {\n', '\n  "overview": {\n' + _chaves(I18N[loc]), 1)], loc)
        json.loads(txt)
        out[loc] = txt
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    out["test_b3"] = _apply(src["test_b3"].read_bytes().decode("utf-8"), [B3_TEST_EDIT], "test_b3")
    compile(out["test_b3"], str(REL["test_b3"]), "exec")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal {len(PORTAL_EDITS)} blocos (funcoes do banner + renderOverview); i18n {len(I18N['pt'])} chaves em pt/en/es; "
          "changelog; teste B3 ajustado (23 -> 28 chaves)")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_b3_offline_errorlog_20260915.py tests/unit/test_b3b_banner_errorlog_20260915.py -q --no-cov ; "
          "py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
