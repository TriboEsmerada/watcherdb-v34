# -*- coding: utf-8 -*-
"""Collector Health, lote 1/2: a modal dos 7 estados passa a falar o idioma escolhido (2026-09-16).

PEDIDO DO OWNER (captura do portal em EN com a modal inteira em portugues): "verifique a traducao no collector".

MEDIDO: o bloco do Collector Health (templates/watcherdb_portal.html, 1496 linhas) tem ZERO `data-i18n` e ZERO
chamadas `t(...)`, enquanto o resto do portal tem 1949 `t(...)` e 253 `_kpiT(...)`. Nao existe nenhum grupo para
este ecra nos ficheiros de idioma (os 64 grupos de static/i18n/en.json nao o incluem). O texto esta escrito a`
mao dentro do HTML e do JavaScript, por isso nao havia o que traduzir.

ESTE LOTE trata so' a modal dos 7 estados (o que o owner viu): 7 estados x 4 campos, mais rotulos, titulo,
rodape, o botao de fechar e a dica do "?" no cabecalho. O resto do ecra (cabecalhos, filtros, colunas da tabela,
botoes, mensagens de "a carregar") fica para o lote 2, de proposito: o owner ve e corrige o estilo antes de eu
multiplicar isto por mais uma centena de textos.

COMO: cada texto passa por `_collT(chave, texto_em_portugues)`. Se a chave faltar no dicionario, aparece o
portugues -- nunca a chave crua. E' o mesmo padrao do `_kpiT(key, fb)` que ja existe no portal (linha 35450).

GLOSSARIO (medido nos proprios ficheiros de idioma, nao inventado): pt usa "recolhedor", pt-BR usa "coletor",
es usa "colector", en usa "collector". O sobreposto pt-BR so' leva as chaves que MUDAM mesmo (o teste do
projecto recusa chaves pt-BR iguais a`s de pt).

A par da traducao, o portugues foi acentuado e passado a linguagem simples -- o texto original estava sem
acentos e cheio de jargao ("Detail modal -> Error Log", "runs", "collector event-driven"). Digo-o aqui porque
nao e' so' traduzir: o texto de partida tambem muda.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_I18N_MODAL_2026-09-16_apply.py --check
  py docs/context/COLL_I18N_MODAL_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5  (e trocar de idioma no cabecalho)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_coll_i18n_modal_20260916.py"),
}
LOCALES = {loc: Path(f"static/i18n/{loc}.json") for loc in ("pt", "pt-BR", "en", "es")}
# Marcador especifico de proposito: "_collT" sozinho apanhava o _collTabSort que ja existia no ficheiro.
MARK = "const _collT = (chave, pt) =>"

# --------------------------------------------------------------------------- textos
ESTADOS = ["FRESH", "RECENT", "QUIET", "STALE", "FAILED", "DISABLED", "NEVER_RAN"]

PT = {
    "help_icon": "Explicar os 7 estados",
    "close": "Fechar",
    "state_info": {
        "title": "Os 7 estados do Collector Health",
        "label": {
            "meaning": "Significa",
            "normal": "Quando é normal",
            "problem": "Quando é problema",
            "action": "Acção recomendada",
        },
        "footer_how": "Como decidimos o estado:",
        "footer_order": "Ordem de avaliação:",
        "footer_esc": "Premir <code>Esc</code> ou clicar fora fecha esta janela.",
    },
    "state": {
        "FRESH": {
            "meaning": "O recolhedor correu há pouco, com sucesso, e a última passagem está dentro do intervalo configurado.",
            "normal": "É o estado desejado — recolhedor saudável, a correr no horário.",
            "problem": "Nunca é problema. Um atraso abaixo de 30 minutos ainda é tolerância normal.",
            "action": "Nenhuma acção necessária.",
        },
        "RECENT": {
            "meaning": "O recolhedor já correu antes, mas o atraso ultrapassa o intervalo configurado (ainda abaixo do dobro).",
            "normal": "Em sistemas com muito paralelismo, alguma latência entre passagens é esperada.",
            "problem": "Se o atraso continuar a crescer ou passar o dobro do intervalo, investigue — está prestes a ficar parado.",
            "action": "Observe a tendência. Se persistir, abra o detalhe e veja o registo de erros.",
        },
        "QUIET": {
            "meaning": "Recolhedor movido a acontecimentos (páginas suspeitas, deadlocks, mudanças de função em Always On, ping, bloqueios longos) sem nada de novo no parque.",
            "normal": "Estado SAUDÁVEL — quer dizer \"nenhum problema detectado, parque a funcionar\". A hora da última troca fica parada por desenho.",
            "problem": "Nunca é problema. Não confunda com parado: aqui o recolhedor está activo, apenas não tem o que registar.",
            "action": "Nenhuma acção. Para confirmar que está vivo, abra o detalhe e veja a hora da última troca e o estado do serviço.",
        },
        "STALE": {
            "meaning": "O recolhedor não corre há demasiado tempo (atraso acima do dobro do intervalo, sem falhas registadas).",
            "normal": "Pode acontecer por pouco tempo depois de reiniciar o serviço, ou em janelas de manutenção.",
            "problem": "Se durar mais de uma hora, o agendador está bloqueado ou o recolhedor está sem recursos. Pode ser sinal de paragem silenciosa.",
            "action": "1) Veja o estado do serviço no topo da página. 2) Abra o detalhe e o registo de erros. 3) Se nada explicar, reinicie o serviço.",
        },
        "FAILED": {
            "meaning": "O recolhedor correu e levantou um erro no último ciclo (falhas nas últimas 24 horas acima de zero).",
            "normal": "Uma falha isolada pode ser passageira — rede, deadlock, tempo esgotado no SQL, ouvinte momentaneamente sem resposta.",
            "problem": "Falhas repetidas (mais de três em 24 horas), ou sempre no mesmo servidor, são defeito ou problema de infra-estrutura.",
            "action": "Abra o detalhe e o registo de erros e identifique o erro. Se for infra-estrutura, fale com quem a opera; se for código, abra um registo de defeito.",
        },
        "DISABLED": {
            "meaning": "Recolhedor marcado como desactivado na configuração (antigo, substituído, ou em manutenção).",
            "normal": "Estado declarado — esperado para recolhedores substituídos por outros mais recentes.",
            "problem": "Se um recolhedor importante ficar desactivado por engano, os indicadores dele deixam de ser alimentados.",
            "action": "Reveja a lista de desactivados de vez em quando e reactive na configuração, se for preciso.",
        },
        "NEVER_RAN": {
            "meaning": "Recolhedor registado que nunca correu (sem qualquer passagem no histórico).",
            "normal": "Comum depois de instalar um recolhedor novo, até o agendador completar o primeiro ciclo.",
            "problem": "Se continuar assim depois do dobro do intervalo, o agendador não está a apanhar a tarefa.",
            "action": "Veja os registos do agendador (APScheduler / Task Scheduler) para confirmar que a tarefa está registada.",
        },
    },
}

EN = {
    "help_icon": "Explain the 7 states",
    "close": "Close",
    "state_info": {
        "title": "The 7 Collector Health states",
        "label": {
            "meaning": "What it means",
            "normal": "When it is normal",
            "problem": "When it is a problem",
            "action": "Recommended action",
        },
        "footer_how": "How the state is decided:",
        "footer_order": "Evaluation order:",
        "footer_esc": "Press <code>Esc</code> or click outside to close this window.",
    },
    "state": {
        "FRESH": {
            "meaning": "The collector ran recently and succeeded, and the last run is within the configured interval.",
            "normal": "This is the desired state — a healthy collector running on schedule.",
            "problem": "Never a problem. A delay under 30 minutes is still normal tolerance.",
            "action": "No action needed.",
        },
        "RECENT": {
            "meaning": "The collector has run before, but the delay already exceeds the configured interval (still under twice it).",
            "normal": "On systems with heavy parallelism, some latency between runs is expected.",
            "problem": "If the delay keeps growing or passes twice the interval, investigate — it is about to go stale.",
            "action": "Watch the trend. If it persists, open the detail view and check the error log.",
        },
        "QUIET": {
            "meaning": "Event-driven collector (suspect pages, deadlocks, Always On failovers, server ping, blocking, long locks) with no new events across the estate.",
            "normal": "A HEALTHY state — it means \"nothing wrong detected, the estate is working\". The last swap time stays frozen by design.",
            "problem": "Never a problem. Not the same as stale: here the collector is running, it simply has nothing to record.",
            "action": "No action. To confirm it is alive, open the detail view and check the last swap time and the service state.",
        },
        "STALE": {
            "meaning": "The collector has not run for too long (delay over twice the configured interval, with no failures recorded).",
            "normal": "Can happen briefly after a service restart, or during maintenance windows.",
            "problem": "If it lasts over an hour, the scheduler is blocked or the collector is out of resources. It can be a sign of a silent crash.",
            "action": "1) Check the service state at the top of the page. 2) Open the detail view and the error log. 3) If nothing explains it, restart the service.",
        },
        "FAILED": {
            "meaning": "The collector ran and raised an error on the last cycle (failures in the last 24 hours above zero).",
            "normal": "A single failure can be transient — network, deadlock, SQL timeout, listener briefly unresponsive.",
            "problem": "Repeated failures (more than three in 24 hours), or a consistent pattern on one server, mean a bug or an infrastructure problem.",
            "action": "Open the detail view and the error log and identify the error. If it is infrastructure, talk to whoever runs it; if it is code, raise a finding.",
        },
        "DISABLED": {
            "meaning": "Collector marked as disabled in the configuration (legacy, superseded, or under maintenance).",
            "normal": "A declared state — expected for collectors replaced by newer ones.",
            "problem": "If an important collector is disabled by mistake, its KPIs stop being populated.",
            "action": "Review the disabled list from time to time and re-enable it in the configuration if needed.",
        },
        "NEVER_RAN": {
            "meaning": "Collector registered but never run (no run in the history).",
            "normal": "Common after deploying a new collector, until the scheduler completes its first cycle.",
            "problem": "If it stays this way past twice the interval, the scheduler is not picking the job up.",
            "action": "Check the scheduler logs (APScheduler / Task Scheduler) to confirm the job is registered.",
        },
    },
}

ES = {
    "help_icon": "Explicar los 7 estados",
    "close": "Cerrar",
    "state_info": {
        "title": "Los 7 estados de Collector Health",
        "label": {
            "meaning": "Qué significa",
            "normal": "Cuándo es normal",
            "problem": "Cuándo es problema",
            "action": "Acción recomendada",
        },
        "footer_how": "Cómo se decide el estado:",
        "footer_order": "Orden de evaluación:",
        "footer_esc": "Pulsar <code>Esc</code> o hacer clic fuera cierra esta ventana.",
    },
    "state": {
        "FRESH": {
            "meaning": "El colector se ejecutó hace poco y con éxito, y la última ejecución está dentro del intervalo configurado.",
            "normal": "Es el estado deseado: colector sano, ejecutándose a horario.",
            "problem": "Nunca es problema. Un retraso de menos de 30 minutos sigue siendo tolerancia normal.",
            "action": "No se requiere ninguna acción.",
        },
        "RECENT": {
            "meaning": "El colector ya se ejecutó antes, pero el retraso supera el intervalo configurado (aún por debajo del doble).",
            "normal": "En sistemas con mucho paralelismo se espera algo de latencia entre ejecuciones.",
            "problem": "Si el retraso sigue creciendo o supera el doble del intervalo, investigue: está por quedar detenido.",
            "action": "Observe la tendencia. Si persiste, abra el detalle y revise el registro de errores.",
        },
        "QUIET": {
            "meaning": "Colector basado en eventos (páginas sospechosas, bloqueos mutuos, conmutaciones de Always On, ping, bloqueos prolongados) sin eventos nuevos en el parque.",
            "normal": "Estado SALUDABLE: significa \"no se detectó ningún problema, el parque funciona\". La hora del último cambio queda congelada por diseño.",
            "problem": "Nunca es problema. No lo confunda con detenido: aquí el colector está activo, solo que no tiene nada que registrar.",
            "action": "Ninguna acción. Para confirmar que está vivo, abra el detalle y vea la hora del último cambio y el estado del servicio.",
        },
        "STALE": {
            "meaning": "El colector no se ejecuta desde hace demasiado tiempo (retraso mayor al doble del intervalo, sin fallas registradas).",
            "normal": "Puede ocurrir brevemente tras reiniciar el servicio, o en ventanas de mantenimiento.",
            "problem": "Si dura más de una hora, el planificador está bloqueado o el colector no tiene recursos. Puede ser señal de una caída silenciosa.",
            "action": "1) Vea el estado del servicio en la parte superior de la página. 2) Abra el detalle y el registro de errores. 3) Si nada lo explica, reinicie el servicio.",
        },
        "FAILED": {
            "meaning": "El colector se ejecutó y generó un error en el último ciclo (fallas en las últimas 24 horas por encima de cero).",
            "normal": "Una falla aislada puede ser transitoria: red, bloqueo mutuo, tiempo de espera agotado en SQL, escucha momentáneamente sin respuesta.",
            "problem": "Fallas repetidas (más de tres en 24 horas), o un patrón constante en un mismo servidor, indican un defecto o un problema de infraestructura.",
            "action": "Abra el detalle y el registro de errores e identifique el error. Si es infraestructura, hable con quien la opera; si es código, abra un reporte.",
        },
        "DISABLED": {
            "meaning": "Colector marcado como deshabilitado en la configuración (heredado, reemplazado o en mantenimiento).",
            "normal": "Estado declarado: esperado para colectores reemplazados por otros más recientes.",
            "problem": "Si un colector importante queda deshabilitado por error, sus indicadores dejan de alimentarse.",
            "action": "Revise la lista de deshabilitados de vez en cuando y vuelva a habilitarlo en la configuración si hace falta.",
        },
        "NEVER_RAN": {
            "meaning": "Colector registrado que nunca se ejecutó (sin ejecuciones en el historial).",
            "normal": "Habitual después de instalar un colector nuevo, hasta que el planificador complete el primer ciclo.",
            "problem": "Si sigue así pasado el doble del intervalo, el planificador no está tomando la tarea.",
            "action": "Revise los registros del planificador (APScheduler / Task Scheduler) para confirmar que la tarea está registrada.",
        },
    },
}

# Sobreposto pt-BR: SO' o que muda mesmo face ao pt (o projecto recusa chaves iguais).
PT_BR = {
    "state_info": {
        "label": {"action": "Ação recomendada"},
        "footer_esc": "Pressionar <code>Esc</code> ou clicar fora fecha esta janela.",
    },
    "state": {
        "FRESH": {
            "meaning": "O coletor rodou há pouco, com sucesso, e a última passagem está dentro do intervalo configurado.",
            "normal": "É o estado desejado — coletor saudável, rodando no horário.",
            "action": "Nenhuma ação necessária.",
        },
        "RECENT": {
            "meaning": "O coletor já rodou antes, mas o atraso ultrapassa o intervalo configurado (ainda abaixo do dobro).",
            "action": "Observe a tendência. Se persistir, abra o detalhe e veja o registro de erros.",
        },
        "QUIET": {
            "meaning": "Coletor movido a eventos (páginas suspeitas, deadlocks, mudanças de função em Always On, ping, bloqueios longos) sem nada de novo no parque.",
            "normal": "Estado SAUDÁVEL — quer dizer \"nenhum problema detectado, parque funcionando\". A hora da última troca fica parada por design.",
            "problem": "Nunca é problema. Não confunda com parado: aqui o coletor está ativo, apenas não tem o que registrar.",
            "action": "Nenhuma ação. Para confirmar que está vivo, abra o detalhe e veja a hora da última troca e o estado do serviço.",
        },
        "STALE": {
            "meaning": "O coletor não roda há tempo demais (atraso acima do dobro do intervalo, sem falhas registradas).",
            "problem": "Se durar mais de uma hora, o agendador está travado ou o coletor está sem recursos. Pode ser sinal de parada silenciosa.",
            "action": "1) Veja o estado do serviço no topo da página. 2) Abra o detalhe e o registro de erros. 3) Se nada explicar, reinicie o serviço.",
        },
        "FAILED": {
            "meaning": "O coletor rodou e levantou um erro no último ciclo (falhas nas últimas 24 horas acima de zero).",
            "problem": "Falhas repetidas (mais de três em 24 horas), ou sempre no mesmo servidor, são defeito ou problema de infraestrutura.",
            "action": "Abra o detalhe e o registro de erros e identifique o erro. Se for infraestrutura, fale com quem a opera; se for código, abra um registro de defeito.",
        },
        "DISABLED": {
            "meaning": "Coletor marcado como desativado na configuração (antigo, substituído, ou em manutenção).",
            "normal": "Estado declarado — esperado para coletores substituídos por outros mais recentes.",
            "problem": "Se um coletor importante ficar desativado por engano, os indicadores dele deixam de ser alimentados.",
            "action": "Reveja a lista de desativados de vez em quando e reative na configuração, se for preciso.",
        },
        "NEVER_RAN": {
            "meaning": "Coletor registrado que nunca rodou (sem nenhuma passagem no histórico).",
            "normal": "Comum depois de instalar um coletor novo, até o agendador completar o primeiro ciclo.",
            "action": "Veja os registros do agendador (APScheduler / Task Scheduler) para confirmar que a tarefa está registrada.",
        },
    },
}

GRUPOS = {"pt": PT, "pt-BR": PT_BR, "en": EN, "es": ES}

# --------------------------------------------------------------------------- portal
HELPER_OLD = """    // === Phase 0c: Modal info 7 estados ===
"""
HELPER_NEW = """    // 2026-09-16: este ecra era o unico do portal sem traducao nenhuma (zero data-i18n, zero t()).
    // Mesmo padrao do _kpiT(key, fb) da linha ~35450: se a chave faltar, mostra-se o portugues,
    // nunca a chave crua.
    const _collT = (chave, pt) => {
        try { const v = (typeof t === 'function') ? t(chave) : null; return (v && v !== chave) ? v : pt; }
        catch (e) { return pt; }
    };

    // === Phase 0c: Modal info 7 estados ===
"""

RENDER_OLD = """            let inner = '<div class="panel">'
                + '<div class="panel-header"><h3>7 estados do Collector Health</h3>'
                + '<button class="panel-close" onclick="document.getElementById(\\'coll-state-info-modal\\').classList.remove(\\'show\\')" aria-label="Fechar">&times;</button>'
                + '</div><div class="panel-body">';
            COLL_STATE_INFO.forEach(s => {
                inner += `<div class="coll-state-info-block ${s.cssCls}" id="csi-${s.key}">`
                    + `<span class="label">${s.key}</span>`
                    + `<dl>`
                    + `<dt>Significa</dt><dd>${_esc(s.meaning)}</dd>`
                    + `<dt>Quando e normal</dt><dd>${_esc(s.normal)}</dd>`
                    + `<dt>Quando e problema</dt><dd>${_esc(s.problem)}</dd>`
                    + `<dt>Accao recomendada</dt><dd>${_esc(s.action)}</dd>`
                    + `</dl></div>`;
            });
            inner += '</div>'
                + '<div class="coll-state-info-footer">'
                + 'Como decidimos o estado: <code>modules/collector_health/health_calculator.py</code>. '
                + 'Ordem de avaliacao: NEVER_RAN -> DISABLED -> FAILED -> STALE -> QUIET -> RECENT -> FRESH. '
                + 'Premir <code>Esc</code> ou clicar fora fecha este modal.'
                + '</div></div>';
"""
RENDER_NEW = """            let inner = '<div class="panel">'
                + `<div class="panel-header"><h3>${_esc(_collT('coll.state_info.title', '7 estados do Collector Health'))}</h3>`
                + '<button class="panel-close" onclick="document.getElementById(\\'coll-state-info-modal\\').classList.remove(\\'show\\')" aria-label="'
                + _esc(_collT('coll.close', 'Fechar')) + '">&times;</button>'
                + '</div><div class="panel-body">';
            COLL_STATE_INFO.forEach(s => {
                inner += `<div class="coll-state-info-block ${s.cssCls}" id="csi-${s.key}">`
                    + `<span class="label">${s.key}</span>`
                    + `<dl>`
                    + `<dt>${_esc(_collT('coll.state_info.label.meaning', 'Significa'))}</dt><dd>${_esc(_collT('coll.state.' + s.key + '.meaning', s.meaning))}</dd>`
                    + `<dt>${_esc(_collT('coll.state_info.label.normal', 'Quando e normal'))}</dt><dd>${_esc(_collT('coll.state.' + s.key + '.normal', s.normal))}</dd>`
                    + `<dt>${_esc(_collT('coll.state_info.label.problem', 'Quando e problema'))}</dt><dd>${_esc(_collT('coll.state.' + s.key + '.problem', s.problem))}</dd>`
                    + `<dt>${_esc(_collT('coll.state_info.label.action', 'Accao recomendada'))}</dt><dd>${_esc(_collT('coll.state.' + s.key + '.action', s.action))}</dd>`
                    + `</dl></div>`;
            });
            inner += '</div>'
                + '<div class="coll-state-info-footer">'
                + _esc(_collT('coll.state_info.footer_how', 'Como decidimos o estado:'))
                + ' <code>modules/collector_health/health_calculator.py</code>. '
                + _esc(_collT('coll.state_info.footer_order', 'Ordem de avaliacao:'))
                + ' NEVER_RAN -> DISABLED -> FAILED -> STALE -> QUIET -> RECENT -> FRESH. '
                + _collT('coll.state_info.footer_esc', 'Premir <code>Esc</code> ou clicar fora fecha este modal.')
                + '</div></div>';
"""

ICONE_OLD = '<span class="coll-info-icon" onclick="event.stopPropagation();collOpenStateInfo()" title="Explicar os 7 estados" role="button" tabindex="0">?</span>'
ICONE_NEW = '<span class="coll-info-icon" onclick="event.stopPropagation();collOpenStateInfo()" title="Explicar os 7 estados" data-i18n-title="coll.help_icon" role="button" tabindex="0">?</span>'

PORTAL_EDITS = [(HELPER_OLD, HELPER_NEW, 1), (RENDER_OLD, RENDER_NEW, 1), (ICONE_OLD, ICONE_NEW, 1)]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: a explicação dos 7 estados passa a falar o idioma escolhido** (owner 16/09). O ecrã era\n"
    "  o único do portal sem tradução nenhuma — nem uma chave, nem uma chamada ao dicionário — por isso a janela de\n"
    "  ajuda aparecia sempre em português, mesmo com o portal em inglês. Os 7 estados, os rótulos, o título, o\n"
    "  rodapé e a dica do \"?\" passam a ter tradução nos quatro idiomas, e o texto português foi acentuado e\n"
    "  reescrito em linguagem simples. O resto do ecrã segue num segundo lote. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- Collector Health (lote 1): a modal dos 7 estados esta ligada ao dicionario nos quatro idiomas.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
ESTADOS = ["FRESH", "RECENT", "QUIET", "STALE", "FAILED", "DISABLED", "NEVER_RAN"]
CAMPOS = ["meaning", "normal", "problem", "action"]


def test_os_quatro_idiomas_tem_o_grupo_completo():
    for loc in ("pt", "en", "es"):
        coll = LOCS[loc]["coll"]
        assert set(coll["state"]) == set(ESTADOS), f"{loc}: faltam estados"
        for e in ESTADOS:
            for c in CAMPOS:
                assert coll["state"][e][c].strip(), f"{loc}: {e}.{c} vazio"
        for r in CAMPOS:
            assert coll["state_info"]["label"][r].strip()
        assert coll["state_info"]["title"].strip()
        assert coll["help_icon"].strip() and coll["close"].strip()


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    """O projecto recusa chaves pt-BR iguais a`s de pt (seriam ruido no sobreposto)."""
    def achatar(d, prefixo=""):
        saida = {}
        for k, v in d.items():
            if isinstance(v, dict):
                saida.update(achatar(v, prefixo + k + "."))
            else:
                saida[prefixo + k] = v
        return saida
    pt = achatar(LOCS["pt"]["coll"])
    br = achatar(LOCS["pt-BR"]["coll"])
    iguais = [k for k, v in br.items() if pt.get(k) == v]
    assert iguais == [], f"chaves pt-BR iguais ao pt: {iguais}"
    assert set(br) <= set(pt), "o sobreposto nao pode ter chaves que o pt nao tem"


def test_nenhuma_traducao_ficou_em_portugues_no_ingles():
    """Rede contra copiar-colar: o ingles nao pode trazer palavras que so' existem em pt."""
    texto = json.dumps(LOCS["en"]["coll"], ensure_ascii=False).lower()
    for palavra in ("recolhedor", "coletor", "acção", "estado saudável", "nunca é problema"):
        assert palavra not in texto, f"ingles com texto portugues: {palavra}"


def test_o_glossario_do_recolhedor_e_coerente_por_idioma():
    def junta(loc):
        return json.dumps(LOCS[loc]["coll"], ensure_ascii=False).lower()
    assert "recolhedor" in junta("pt") and "coletor" not in junta("pt")
    assert "coletor" in junta("pt-BR") and "recolhedor" not in junta("pt-BR")
    assert "colector" in junta("es")
    assert "collector" in junta("en")


def test_a_modal_usa_o_dicionario_com_recurso_ao_portugues():
    assert "const _collT = (chave, pt) =>" in PORTAL
    i = PORTAL.index("window.collOpenStateInfo = function")
    bloco = PORTAL[i:i + 3000]
    assert "_collT('coll.state_info.title'" in bloco
    assert "_collT('coll.state.' + s.key + '.meaning', s.meaning)" in bloco
    for rotulo in ("meaning", "normal", "problem", "action"):
        assert f"_collT('coll.state_info.label.{rotulo}'" in bloco
    assert "_collT('coll.close', 'Fechar')" in bloco
    assert "_collT('coll.state_info.footer_esc'" in bloco


def test_o_texto_em_portugues_continua_la_como_recurso():
    """Se o dicionario falhar, o utilizador ve portugues e nao uma chave crua."""
    i = PORTAL.index("const COLL_STATE_INFO = [")
    bloco = PORTAL[i:i + 6000]
    for e in ESTADOS:
        assert f"key: '{e}'" in bloco


def test_a_dica_do_icone_tem_chave():
    assert 'data-i18n-title="coll.help_icon"' in PORTAL
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:110]!r}")
        text = text.replace(o, n)
    return text


def _juntar_grupo(raw: str, grupo: dict) -> str:
    """Acrescenta "coll" como ultimo grupo de topo, deixando o resto do ficheiro byte a byte igual."""
    if '"coll"' in raw:
        raise SystemExit("[ABORT] o ficheiro de idioma ja tem o grupo coll")
    corpo = raw.rstrip()
    if not corpo.endswith("}"):
        raise SystemExit("[ABORT] ficheiro de idioma com fim inesperado")
    texto = json.dumps({"coll": grupo}, ensure_ascii=False, indent=2)
    bloco = "\n".join(texto.split("\n")[1:-1])   # tira as chavetas exteriores
    return corpo[:-1].rstrip() + ",\n" + bloco + "\n}\n"


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

    locais = {}
    for loc, rel in LOCALES.items():
        caminho = base / rel
        raw = caminho.read_bytes().decode("utf-8")
        novo = _juntar_grupo(raw, GRUPOS[loc])
        d = json.loads(novo)                      # tem de continuar JSON valido
        antes = json.loads(raw)
        assert set(d) - set(antes) == {"coll"}, f"{loc}: mexeu em mais do que o grupo coll"
        for k in antes:
            assert d[k] == antes[k], f"{loc}: o grupo {k} mudou"
        locais[loc] = (caminho, novo)
        print(f"[ok] {loc}: grupo coll com {len(json.dumps(GRUPOS[loc]))} bytes")

    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] portal 3 blocos (helper, render da modal, dica do icone); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    for loc, (caminho, novo) in locais.items():
        caminho.write_bytes(novo.encode("utf-8")); print(f"[write] {LOCALES[loc]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
