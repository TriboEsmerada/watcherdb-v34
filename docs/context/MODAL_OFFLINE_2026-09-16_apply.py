# -*- coding: utf-8 -*-
"""Modal de instâncias offline (2026-09-16) -- errorlog e link para o Overview, e tres defeitos de comparacao por titulo.

Pedido do owner (captura da modal "Instances Offline" com SQLHDSPRD407 e SQLMDMPRD03): "A informacao do log poderia
aparecer aqui na modal tbm. e poderia ter um link para levar para o overview da instancia tbm".

Medido ao preparar o lote (so leitura):
  1. A nota "KPI-only - drilldown nao configurado (config/servers.json)" aparece em instancias MONITORIZADAS: o KPI da o
     nome do HOST (SQLHDSPRD407) e o inventario tem a instancia (SQLHDSPRD407_I01). Dos 63 servidores, so 2 hosts tem
     mais de uma instancia (SQLHDSQLT103 com 2, SQLHDSQLT105 com 4).
  2. O cartao proprio dos servidores offline (com Estado, Ping, servicos em baixo e a mensagem do ping) NUNCA e usado:
     o codigo compara `title === 'Instances Off'` e o titulo da modal e "Instances Offline" (chave kpi_meta). Por isso
     via-se o cartao generico com "Full record detail". O mesmo para o titulo do grafico por ambiente.
  3. Pior: `isOkFilter = title === 'Instances OK'` decide se a modal pede a lista de instancias OK. Em pt o titulo e
     "Instancias OK" e em es "Instancias OK" -> a comparacao falha e a modal "Instancias OK" mostra a lista de OFFLINE.
     Defeito de dados, nao cosmetico, em todos os idiomas menos o ingles.
  Correccao: comparar com o titulo traduzido da propria chave (_kpiT), nunca com o literal ingles.

Pareceres incorporados:
  watcherdb-frontend-specialist: bloco do errorlog dentro do painel expansivel (carrega so ao abrir; evita 63 pedidos),
    <summary> com stopPropagation (senao o clique abre a ajuda e fecha o cartao), id proprio na modal para nao colidir
    com o do ecra offline, e comparacao por host so quando o host tem UMA instancia.
  customer-success-persona: errorlog sempre recolhido (a modal pode ter 20 instancias), link do Overview como botao
    proprio no cabecalho (o clique no cartao ja leva ao SQL Diagnostics), tempo offline visivel sem expandir (o cartao
    proprio ja o mostra), e nunca dois niveis abertos ao mesmo tempo.

Sem mudanca de backend nem de base de dados.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/MODAL_OFFLINE_2026-09-16_apply.py --check
  py docs/context/MODAL_OFFLINE_2026-09-16_apply.py
  py -m pytest tests/unit/test_modal_offline_20260916.py tests/unit/test_live_ajuda_sched_20260915.py tests/unit/test_b3_offline_errorlog_20260915.py tests/unit/test_live_typography_tokens.py -q --no-cov
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
    "ptbr": Path("static/i18n/pt-BR.json"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_modal_offline_20260916.py"),
}
MARK = "_kpiServidorDaLinha"

# ---------------------------------------------------------------- helpers novos
HELPERS_JS = r"""        // 2026-09-16 (owner: log e link na modal de offline): tres comparacoes decidiam comportamento pelo TITULO TRADUZIDO.
        // isOkFilter falhava em pt e es (titulo "Instancias OK") e a modal de instancias OK mostrava as OFFLINE; o cartao
        // proprio dos offline e o titulo do grafico comparavam com "Instances Off" e a chave da "Instances Offline".
        function _kpiTituloDaChave(id, fb) { return _kpiT('kpi_meta.' + id + '.modal_title', fb); }
        function _ehModalInstanciasOk(titulo) { return titulo === _kpiTituloDaChave('db-availability-ok', 'Instances OK'); }
        function _ehModalInstanciasOffline(titulo) {
            return titulo === _kpiTituloDaChave('instance-availability-off', 'Instances Off')
                || titulo === _kpiTituloDaChave('db-availability-off', 'Instances Offline');
        }

        // 2026-09-16: o KPI de disponibilidade da o nome do HOST (SQLHDSPRD407) e o inventario tem a instancia
        // (SQLHDSPRD407_I01). Resolve pelo host quando esse host tem UMA instancia; com duas ou mais fica ambiguo
        // (SQLHDSQLT103 e SQLHDSQLT105 sao os unicos casos) e devolve null, para nao abrir a instancia errada.
        function _kpiServidorDaLinha(nome) {
            if (!Array.isArray(allServers) || !allServers.length || !nome) return null;
            const alvo = String(nome).replace(/\\/g, '_').toLowerCase();
            const exacto = allServers.find(s => String(s.server_id || '').toLowerCase() === alvo
                || String(s.name || '').toLowerCase() === alvo);
            if (exacto) return exacto;
            const host = alvo.split('_')[0];
            const doHost = allServers.filter(s => String(s.server_id || '').toLowerCase().split('_')[0] === host);
            return doHost.length === 1 ? doHost[0] : null;
        }
        function _kpiAbrirOverview(el) {
            const card = el.closest('.instance-item');
            const servidor = _kpiServidorDaLinha(card && card.dataset.instanceName);
            if (!servidor) return;
            const modal = document.getElementById('instancesModal');
            if (modal) modal.classList.remove('show');
            createTab(servidor, 'overview');
        }

"""

# ---------------------------------------------------------------- comparacoes por titulo
EDITS_TITULO = [
    ("                } else if (kpiType === 'db-availability-ok' || title === 'Instances OK') {\n",
     "                } else if (kpiType === 'db-availability-ok' || _ehModalInstanciasOk(title)) {\n", 1),
    ("                    } else if (title === 'Instances OK') {\n",
     "                    } else if (_ehModalInstanciasOk(title)) {   // 2026-09-16: idem no cartao proprio das instancias OK\n", 1),
    ("                const isOkFilter = title === 'Instances OK';\n",
     "                const isOkFilter = _ehModalInstanciasOk(title);   // 2026-09-16: por chave, nao pelo titulo traduzido\n", 1),
    ("                    } else if (title === 'Instances Off') {\n",
     "                    } else if (_ehModalInstanciasOffline(title)) {   // 2026-09-16: o cartao proprio dos offline nunca chegava aqui\n", 1),
    ("                    if (title === 'Instances OK') chartTitle = t('chart.instances_ok_by_env');\n"
     "                    else if (title === 'Instances Off') chartTitle = t('chart.instances_off_by_env');\n",
     "                    if (_ehModalInstanciasOk(title)) chartTitle = t('chart.instances_ok_by_env');\n"
     "                    else if (_ehModalInstanciasOffline(title)) chartTitle = t('chart.instances_off_by_env');\n", 1),
]

# ---------------------------------------------------------------- botao Overview no cartao proprio dos offline
BOTAO_OLD = ('                                            <span style="background: ${inferredEnvColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;">${inferredEnv}</span>\n'
             '                                        </div>\n')
BOTAO_NEW = ('                                            <span style="background: ${inferredEnvColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;">${inferredEnv}</span>\n'
             '                                            <button type="button" class="kpi-overview-btn" onclick="event.stopPropagation(); _kpiAbrirOverview(this);"\n'
             '                                                    style="background: transparent; border: 1px solid var(--color-border); color: var(--color-text-link); border-radius: 4px; padding: 2px 8px; font-size: 12px; cursor: pointer;">\n'
             '                                                <i class="fas fa-up-right-from-square" aria-hidden="true"></i> ${_kpiT(\'kpi_modal.open_overview\', \'Abrir Overview\')}\n'
             '                                            </button>\n'
             '                                        </div>\n')

# ---------------------------------------------------------------- drilldown por host + botao sem servidor resolvido
DRILL_OLD = ("                const candidates = [name, name.replace(/\\\\/g, '_'), name.replace(/_/g, '\\\\')];\n"
             "                const found = allServers.some(s => candidates.some(c =>\n"
             "                    String(s.server_id || '').toLowerCase() === c.toLowerCase() ||\n"
             "                    String(s.name || '').toLowerCase() === c.toLowerCase()));\n"
             "                if (!found) {\n")
DRILL_NEW = ("                // 2026-09-16: resolve tambem pelo host (o KPI de offline da SQLHDSPRD407, o inventario tem\n"
             "                // SQLHDSPRD407_I01). Sem servidor resolvido, tira tambem o botao de Overview.\n"
             "                const found = !!_kpiServidorDaLinha(name);\n"
             "                if (!found) {\n"
             "                    const btn = card.querySelector('.kpi-overview-btn');\n"
             "                    if (btn) btn.remove();\n")

# ---------------------------------------------------------------- errorlog dentro do painel expansivel
EXPAND_OLD = ("                if (kt.indexOf('filegroup-usage') === 0 && card.dataset.instanceName) {\n")
EXPAND_NEW = ("                // 2026-09-16 (owner): nas modais de disponibilidade, o mesmo bloco do errorlog do ecra offline,\n"
              "                // recolhido e a ler so quando o utilizador o abre (a modal pode ter 20 instancias). O nome vem do\n"
              "                // host; usa a instancia resolvida, senao o endpoint nao encontra linhas. Id proprio da modal.\n"
              "                if (kt === 'instance-availability' && card.dataset.instanceName) {\n"
              "                    const servidor = _kpiServidorDaLinha(card.dataset.instanceName);\n"
              "                    const alvo = servidor ? String(servidor.server_id || '') : String(card.dataset.instanceName).replace(/\\\\/g, '_');\n"
              "                    const caixa = document.createElement('div');\n"
              "                    caixa.style.cssText = 'margin-top:8px;';\n"
              "                    caixa.innerHTML = offlineErrorlogBannerBlock(alvo, false, 'modal-' + (card.dataset.idx || '0'));\n"
              "                    panel.appendChild(caixa);\n"
              "                }\n"
              "                if (kt.indexOf('filegroup-usage') === 0 && card.dataset.instanceName) {\n")

# ---------------------------------------------------------------- bloco do errorlog: sufixo de id e clique contido
BANNER_OLD = ("        function offlineErrorlogBannerBlock(instance, auto) {\n"
              "            const inst = String(instance || '').replace(/\\\\/g, '_');\n"
              "            const id = offlineErrorlogId(inst);\n")
BANNER_NEW = ("        function offlineErrorlogBannerBlock(instance, auto, sufixo) {\n"
              "            const inst = String(instance || '').replace(/\\\\/g, '_');\n"
              "            // 2026-09-16: sufixo para o bloco poder viver na modal de KPI sem colidir com o do ecra offline\n"
              "            const id = offlineErrorlogId(inst) + (sufixo ? '-' + String(sufixo).replace(/[^A-Za-z0-9_-]/g, '_') : '');\n")
SUMMARY_OLD = '                    <summary style="cursor: pointer; font-size: 13px;">\n'
SUMMARY_NEW = ('                    <summary onclick="event.stopPropagation();" style="cursor: pointer; font-size: 13px;">\n'
               '                        <!-- 2026-09-16: dentro de um cartao clicavel (modal de KPI) o clique nao pode fechar o cartao -->\n')

PORTAL_EDITS = EDITS_TITULO + [
    ("        function _kpiTituloDaChave", "        function _kpiTituloDaChave", 0),  # marcador, substituido em main
    (BOTAO_OLD, BOTAO_NEW, 1),
    (DRILL_OLD, DRILL_NEW, 1),
    (EXPAND_OLD, EXPAND_NEW, 1),
    (BANNER_OLD, BANNER_NEW, 1),
    (SUMMARY_OLD, SUMMARY_NEW, 1),
]

I18N = {
    "pt": {"open_overview": "Abrir Overview"},
    "en": {"open_overview": "Open Overview"},
    "es": {"open_overview": "Abrir Overview"},
}

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Modal de instâncias offline: errorlog, link para o Overview e três comparações por título traduzido**\n"
                  "  (owner 16/09). Cada instância passa a ter o bloco \"Errorlog antes da falha\" recolhido, que só lê quando é\n"
                  "  aberto, e um botão \"Abrir Overview\". Corrigidos: a nota \"drilldown não configurado\" em instâncias\n"
                  "  monitorizadas (o KPI dá o host e o inventário tem a instância); o cartão próprio dos servidores offline, que\n"
                  "  nunca aparecia porque o código comparava com \"Instances Off\"; e — o mais grave — a modal \"Instâncias OK\",\n"
                  "  que em português e espanhol pedia e mostrava a lista de offline. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-16 -- modal de instâncias offline: errorlog, link para o Overview e fim das comparações por título traduzido.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_sem_comparacoes_pelo_titulo_traduzido():
    assert "title === 'Instances OK'" not in PORTAL and "title === 'Instances Off'" not in PORTAL
    assert "const isOkFilter = _ehModalInstanciasOk(title);" in PORTAL
    assert "} else if (_ehModalInstanciasOffline(title)) {" in PORTAL
    assert "if (_ehModalInstanciasOk(title)) chartTitle = t('chart.instances_ok_by_env');" in PORTAL
    assert "_kpiT('kpi_meta.' + id + '.modal_title', fb)" in PORTAL


def test_resolucao_por_host_so_quando_e_unica():
    fn = PORTAL[PORTAL.index("function _kpiServidorDaLinha(nome) {"):PORTAL.index("function _kpiAbrirOverview(el) {")]
    assert "const host = alvo.split('_')[0];" in fn and "return doHost.length === 1 ? doHost[0] : null;" in fn
    drill = PORTAL[PORTAL.index("function _applyDrilldownAvailability(modalBody) {"):]
    drill = drill[:drill.index("\n        }\n")]
    assert "const found = !!_kpiServidorDaLinha(name);" in drill and "btn.remove();" in drill
    assert "allServers.some(s => candidates.some(c =>" not in PORTAL


def test_botao_overview_e_errorlog_recolhido_na_modal():
    assert 'class="kpi-overview-btn" onclick="event.stopPropagation(); _kpiAbrirOverview(this);"' in PORTAL
    assert "kpi_modal.open_overview" in PORTAL
    i = PORTAL.index("function toggleCardExpand(card) {")
    expand = PORTAL[i:PORTAL.index(chr(10) + "        function ", i)]
    assert "if (kt === 'instance-availability' && card.dataset.instanceName) {" in expand
    assert "offlineErrorlogBannerBlock(alvo, false, 'modal-'" in expand
    assert expand.index("_kpiServidorDaLinha(card.dataset.instanceName)") < expand.index("offlineErrorlogBannerBlock(")
    banner = PORTAL[PORTAL.index("function offlineErrorlogBannerBlock(instance, auto, sufixo) {"):PORTAL.index("function _oelBannerToggle")]
    assert '<summary onclick="event.stopPropagation();"' in banner
    assert "offlineErrorlogId(inst) + (sufixo ?" in banner


def test_chave_nos_tres_idiomas():
    for loc in ("pt", "en", "es"):
        d = json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        assert d["kpi_modal"]["open_overview"].strip(), loc
'''


def _chaves(d):
    return "".join(f'    "{k}": {json.dumps(v, ensure_ascii=False)},\n' for k, v in d.items())


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        if count == 0:
            continue
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
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    eol = "\r\n" if "\r\n" in portal else "\n"
    ancora_helpers = "        function _applyDrilldownAvailability(modalBody) {" + eol
    if portal.count(ancora_helpers) != 1:
        raise SystemExit("[ABORT] portal: ancora dos helpers nao unica -- nada escrito")
    portal = portal.replace(ancora_helpers, HELPERS_JS.replace("\n", eol) + ancora_helpers, 1)
    portal = _apply(portal, PORTAL_EDITS, "portal")
    out = {"portal": portal}
    for loc in ("pt", "en", "es"):
        raw = src[loc].read_bytes().decode("utf-8")
        if set(I18N[loc]) & set(json.loads(raw).get("kpi_modal", {})):
            raise SystemExit(f"[ABORT] {loc}: chave open_overview ja existe em kpi_modal")
        txt = _apply(raw, [('\n  "kpi_modal": {\n', '\n  "kpi_modal": {\n' + _chaves(I18N[loc]), 1)], loc)
        json.loads(txt)
        out[loc] = txt
    out["changelog"] = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] portal: helpers de titulo e de host, botao Overview, errorlog no painel expansivel, sufixo de id e clique contido; "
          "i18n 1 chave em pt/en/es; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_modal_offline_20260916.py tests/unit/test_live_ajuda_sched_20260915.py "
          "tests/unit/test_b3_offline_errorlog_20260915.py tests/unit/test_live_typography_tokens.py -q --no-cov ; "
          "py scripts/i18n_validate.py ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
