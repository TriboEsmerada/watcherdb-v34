# -*- coding: utf-8 -*-
"""Collector Health, lote 2d/4 (ultimo): as accoes (2026-09-16).

Fecha o ecra. Aqui ficam os textos que aparecem quando se MEXE em alguma coisa: executar uma tarefa agora e
acompanhar o pedido ate ao fim, re-correr em massa as tarefas filtradas, e activar ou desactivar uma tarefa
com motivo obrigatorio.

Sao quase todos textos de progresso e de erro -- os que so' se veem quando algo corre mal, e por isso os que
mais facilmente ficam por traduzir. Todos passam a ter marcadores em vez de concatenacao: o numero do pedido,
a duracao, o nome da tarefa e a contagem entram na frase pelo sitio que cada idioma quiser.

DEPENDE de: lotes 1, 2a, 2b e 2c. Reaproveita coll.bulk_run, coll.det.error e coll.det.activate/deactivate.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_I18N_ACCOES_2026-09-16_apply.py --check
  py docs/context/COLL_I18N_ACCOES_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_i18n_accoes_20260916.py tests/unit/test_coll_i18n_detalhe_20260916.py tests/unit/test_coll_i18n_mute_20260916.py tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "portal": Path("templates/watcherdb_portal.html"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_coll_i18n_accoes_20260916.py"),
}
LOCALES = {loc: Path(f"static/i18n/{loc}.json") for loc in ("pt", "pt-BR", "en", "es")}
MARK = "coll.run.confirm"

PT = {
    "run": {
        "need_enable": "Para executar esta tarefa, active primeiro a recolha no botão Activar.",
        "confirm": "Executar \"{nome}\" agora?",
        "st_registering": "A registar o pedido",
        "st_pending": "À espera de execução",
        "st_running": "Em execução",
        "st_done": "Concluído com sucesso",
        "st_error": "Erro",
        "st_timeout": "Tempo esgotado",
        "registering": "A registar o pedido...",
        "err_register": "Não foi possível registar o pedido:",
        "queued": "Pedido #{id} registado. À espera de que o serviço de recolha o execute...",
        "queued_dots": "Pedido #{id} na fila{p} ({s} s)",
        "running": "Pedido #{id} em execução...",
        "done": "Concluído com sucesso. Demorou {ms} ms e recolheu {n} linhas.",
        "failed": "Falhou: {err}",
        "unknown_error": "Erro desconhecido",
        "timeout_queue": "Tempo esgotado ao fim de {s} s. O pedido #{id} continua na fila.",
        "timeout_poller": "Tempo esgotado ao fim de {s} s. O pedido #{id} continua à espera. O serviço de recolha pode não estar a consumir a fila.",
        "close": "Fechar",
    },
    "bulk": {
        "none": "Nenhuma tarefa activa entre as visíveis. Ajuste os filtros, ou active as tarefas primeiro.",
        "confirm_title": "Re-correr as tarefas filtradas",
        "confirm_count": "Vão ser disparadas {n} tarefas ao mesmo tempo:",
        "confirm_more": "... e mais {n} tarefas",
        "confirm_skipped": "({n} tarefas desactivadas ficam de fora)",
        "confirm_ask": "Confirma?",
        "dispatching": "A disparar {n}...",
        "done_title": "Re-execução terminada:",
        "done_ok": "Disparadas: {ok} de {n}",
        "done_failed": "Falharam ao disparar: {n}",
        "done_failed_list": "Tarefas que falharam (as 5 primeiras):",
        "done_note": "As tarefas disparadas ficaram em fila. Carregue em Actualizar daqui a um minuto para ver o progresso.",
    },
    "toggle": {
        "word_on": "ACTIVAR",
        "word_off": "DESACTIVAR",
        "prompt": "{accao} \"{nome}\"?\n\nMotivo (obrigatório, pelo menos 20 caracteres):\nExemplo: Reactivar para validar a correcção no recolhedor de páginas suspeitas",
        "too_short": "Motivo demasiado curto ({n} caracteres). São precisos pelo menos 20.\n\nÉ isto que deixa rasto de quem mudou o quê, e porquê.",
        "processing": "A processar...",
    },
}

EN = {
    "run": {
        "need_enable": "To run this task, enable collection first with the Enable button.",
        "confirm": "Run \"{nome}\" now?",
        "st_registering": "Registering the request",
        "st_pending": "Waiting to run",
        "st_running": "Running",
        "st_done": "Finished successfully",
        "st_error": "Error",
        "st_timeout": "Timed out",
        "registering": "Registering the request...",
        "err_register": "Could not register the request:",
        "queued": "Request #{id} registered. Waiting for the collector service to run it...",
        "queued_dots": "Request #{id} queued{p} ({s} s)",
        "running": "Request #{id} running...",
        "done": "Finished successfully. Took {ms} ms and collected {n} rows.",
        "failed": "Failed: {err}",
        "unknown_error": "Unknown error",
        "timeout_queue": "Timed out after {s} s. Request #{id} is still queued.",
        "timeout_poller": "Timed out after {s} s. Request #{id} is still waiting. The collector service may not be consuming the queue.",
        "close": "Close",
    },
    "bulk": {
        "none": "No enabled task among the visible ones. Adjust the filters, or enable the tasks first.",
        "confirm_title": "Re-run the filtered tasks",
        "confirm_count": "{n} tasks will be started at once:",
        "confirm_more": "... and {n} more tasks",
        "confirm_skipped": "({n} disabled tasks are left out)",
        "confirm_ask": "Go ahead?",
        "dispatching": "Starting {n}...",
        "done_title": "Re-run finished:",
        "done_ok": "Started: {ok} of {n}",
        "done_failed": "Failed to start: {n}",
        "done_failed_list": "Tasks that failed (first 5):",
        "done_note": "The tasks that started are queued. Click Refresh in about a minute to see progress.",
    },
    "toggle": {
        "word_on": "ENABLE",
        "word_off": "DISABLE",
        "prompt": "{accao} \"{nome}\"?\n\nReason (required, at least 20 characters):\nExample: Re-enabling to verify the fix in the suspect pages collector",
        "too_short": "Reason too short ({n} characters). At least 20 are needed.\n\nThis is what leaves a trail of who changed what, and why.",
        "processing": "Working...",
    },
}

ES = {
    "run": {
        "need_enable": "Para ejecutar esta tarea, active primero la recolección con el botón Activar.",
        "confirm": "¿Ejecutar \"{nome}\" ahora?",
        "st_registering": "Registrando la solicitud",
        "st_pending": "Esperando ejecución",
        "st_running": "En ejecución",
        "st_done": "Terminó con éxito",
        "st_error": "Error",
        "st_timeout": "Tiempo agotado",
        "registering": "Registrando la solicitud...",
        "err_register": "No se pudo registrar la solicitud:",
        "queued": "Solicitud #{id} registrada. Esperando a que el servicio de recolección la ejecute...",
        "queued_dots": "Solicitud #{id} en cola{p} ({s} s)",
        "running": "Solicitud #{id} en ejecución...",
        "done": "Terminó con éxito. Tardó {ms} ms y recolectó {n} filas.",
        "failed": "Falló: {err}",
        "unknown_error": "Error desconocido",
        "timeout_queue": "Tiempo agotado tras {s} s. La solicitud #{id} sigue en cola.",
        "timeout_poller": "Tiempo agotado tras {s} s. La solicitud #{id} sigue esperando. El servicio de recolección puede no estar consumiendo la cola.",
        "close": "Cerrar",
    },
    "bulk": {
        "none": "Ninguna tarea activa entre las visibles. Ajuste los filtros, o active las tareas primero.",
        "confirm_title": "Volver a ejecutar las tareas filtradas",
        "confirm_count": "Se lanzarán {n} tareas a la vez:",
        "confirm_more": "... y {n} tareas más",
        "confirm_skipped": "({n} tareas desactivadas quedan fuera)",
        "confirm_ask": "¿Confirma?",
        "dispatching": "Lanzando {n}...",
        "done_title": "Re-ejecución terminada:",
        "done_ok": "Lanzadas: {ok} de {n}",
        "done_failed": "Fallaron al lanzarse: {n}",
        "done_failed_list": "Tareas que fallaron (las 5 primeras):",
        "done_note": "Las tareas lanzadas quedaron en cola. Pulse Actualizar dentro de un minuto para ver el progreso.",
    },
    "toggle": {
        "word_on": "ACTIVAR",
        "word_off": "DESACTIVAR",
        "prompt": "{accao} \"{nome}\"?\n\nMotivo (obligatorio, al menos 20 caracteres):\nEjemplo: Reactivar para validar la corrección en el colector de páginas sospechosas",
        "too_short": "Motivo demasiado corto ({n} caracteres). Hacen falta al menos 20.\n\nEsto es lo que deja rastro de quién cambió qué, y por qué.",
        "processing": "Procesando...",
    },
}

PT_BR = {
    "run": {
        "need_enable": "Para executar esta tarefa, ative primeiro a coleta no botão Ativar.",
        "queued": "Pedido #{id} registrado. Esperando que o serviço de coleta o execute...",
        "timeout_queue": "Tempo esgotado depois de {s} s. O pedido #{id} continua na fila.",
        "timeout_poller": "Tempo esgotado depois de {s} s. O pedido #{id} continua esperando. O serviço de coleta pode não estar consumindo a fila.",
        "err_register": "Não foi possível registrar o pedido:",
        "registering": "A registrar o pedido...",
        "st_registering": "A registrar o pedido",
        "st_pending": "Esperando execução",
    },
    "bulk": {
        "none": "Nenhuma tarefa ativa entre as visíveis. Ajuste os filtros, ou ative as tarefas primeiro.",
        "confirm_skipped": "({n} tarefas desativadas ficam de fora)",
        "done_note": "As tarefas disparadas ficaram em fila. Clique em Atualizar daqui a um minuto para ver o progresso.",
    },
    "toggle": {
        "word_on": "ATIVAR",
        "word_off": "DESATIVAR",
        "prompt": "{accao} \"{nome}\"?\n\nMotivo (obrigatório, pelo menos 20 caracteres):\nExemplo: Reativar para validar a correção no coletor de páginas suspeitas",
        "too_short": "Motivo curto demais ({n} caracteres). São precisos pelo menos 20.\n\nÉ isto que deixa rastro de quem mudou o quê, e por quê.",
    },
}

GRUPOS = {"pt": PT, "pt-BR": PT_BR, "en": EN, "es": ES}

# --------------------------------------------------------------------------- portal
EDITS = [
    # --- executar agora
    ("""            _setRunState(document.getElementById('coll-run-btn'), statusEl, 'error',
                'Para executar este task, active primeiro a coleta atraves do botao "Activar".');""",
     """            _setRunState(document.getElementById('coll-run-btn'), statusEl, 'error',
                _collT('coll.run.need_enable', 'Para executar este task, active primeiro a coleta atraves do botao Activar.'));""", 1),
    ("""        if (!confirm(`Executar "${task.name}" agora?`)) return;""",
     """        if (!confirm(_collTp('coll.run.confirm', 'Executar "{nome}" agora?', { nome: task.name }))) return;""", 1),
    ("""        _setRunState(btn, statusEl, 'registering', 'A registar pedido...');""",
     """        _setRunState(btn, statusEl, 'registering', _collT('coll.run.registering', 'A registar pedido...'));""", 1),
    ("""            _setRunState(btn, statusEl, 'error', 'Erro ao registar: ' + e.message);""",
     """            _setRunState(btn, statusEl, 'error', _collT('coll.run.err_register', 'Erro ao registar:') + ' ' + e.message);""", 1),
    ("""        _setRunState(btn, statusEl, 'pending', `Pedido #${requestId} registado. A aguardar execucao pelo Collector Service...`);""",
     """        _setRunState(btn, statusEl, 'pending', _collTp('coll.run.queued',
            'Pedido #{id} registado. A aguardar execucao pelo servico de recolha...', { id: requestId }));""", 1),
    ("""                    if (polls >= maxPolls) { clearInterval(pollInterval); _setRunState(btn, statusEl, 'timeout', `Timeout apos ${maxPolls * 3}s. Pedido #${requestId} continua PENDING na fila.`); }""",
     """                    if (polls >= maxPolls) {
                        clearInterval(pollInterval);
                        _setRunState(btn, statusEl, 'timeout', _collTp('coll.run.timeout_queue',
                            'Tempo esgotado ao fim de {s} s. O pedido #{id} continua na fila.',
                            { s: maxPolls * 3, id: requestId }));
                    }""", 1),
    ("""                    _setRunState(btn, statusEl, 'running', `#${requestId} em execucao...`);""",
     """                    _setRunState(btn, statusEl, 'running', _collTp('coll.run.running', 'Pedido #{id} em execucao...', { id: requestId }));""", 1),
    ("""                    _setRunState(btn, statusEl, 'done',
                        `Concluido com sucesso. Duracao: ${dur}ms, Rows: ${rows}`);""",
     """                    _setRunState(btn, statusEl, 'done', _collTp('coll.run.done',
                        'Concluido com sucesso. Demorou {ms} ms e recolheu {n} linhas.', { ms: dur, n: rows }));""", 1),
    ("""                    const err = d.error_message || d.run?.error_message || 'Erro desconhecido';
                    _setRunState(btn, statusEl, 'error', `Falhou: ${err}`);""",
     """                    const err = d.error_message || d.run?.error_message || _collT('coll.run.unknown_error', 'Erro desconhecido');
                    _setRunState(btn, statusEl, 'error', _collTp('coll.run.failed', 'Falhou: {err}', { err }));""", 1),
    ("""                    _setRunState(btn, statusEl, 'pending',
                        `Pedido #${requestId} na fila${dots} (${polls * 3}s)`);""",
     """                    _setRunState(btn, statusEl, 'pending', _collTp('coll.run.queued_dots',
                        'Pedido #{id} na fila{p} ({s} s)', { id: requestId, p: dots, s: polls * 3 }));""", 1),
    ("""                _setRunState(btn, statusEl, 'timeout',
                    `Timeout apos ${maxPolls * 3}s. Pedido #${requestId} ainda PENDING. ` +
                    `O Collector Service pode nao ter o poller activo (Fase 2).`);""",
     """                _setRunState(btn, statusEl, 'timeout', _collTp('coll.run.timeout_poller',
                    'Tempo esgotado ao fim de {s} s. O pedido #{id} continua a` espera. O servico de recolha pode nao estar a consumir a fila.',
                    { s: maxPolls * 3, id: requestId }));""", 1),

    # --- re-correr em massa
    ("""            alert('Nenhum task enabled visivel para re-correr. Ajusta os filtros ou activa os tasks primeiro.');""",
     """            alert(_collT('coll.bulk.none', 'Nenhuma tarefa activa entre as visiveis. Ajuste os filtros, ou active as tarefas primeiro.'));""", 1),
    ("""        const confirmMsg = `Bulk Re-run\\n\\n` +
            `Vai disparar ${runnable.length} tasks em paralelo:\\n` +
            `${runnable.slice(0, 10).map(t => '  - ' + t.name).join('\\n')}` +
            (runnable.length > 10 ? `\\n  ... e mais ${runnable.length - 10} tasks` : '') +
            `\\n\\n` +
            (disabledCount > 0 ? `(${disabledCount} disabled task(s) skipped)\\n\\n` : '') +
            `Confirma?`;""",
     """        const confirmMsg = _collT('coll.bulk.confirm_title', 'Re-correr as tarefas filtradas') + '\\n\\n' +
            _collTp('coll.bulk.confirm_count', 'Vao ser disparadas {n} tarefas ao mesmo tempo:', { n: runnable.length }) + '\\n' +
            `${runnable.slice(0, 10).map(t => '  - ' + t.name).join('\\n')}` +
            (runnable.length > 10 ? '\\n  ' + _collTp('coll.bulk.confirm_more', '... e mais {n} tarefas', { n: runnable.length - 10 }) : '') +
            '\\n\\n' +
            (disabledCount > 0 ? _collTp('coll.bulk.confirm_skipped', '({n} tarefas desactivadas ficam de fora)', { n: disabledCount }) + '\\n\\n' : '') +
            _collT('coll.bulk.confirm_ask', 'Confirma?');""", 1),
    ("""            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> A disparar ${runnable.length}...`;""",
     """            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${_collTp('coll.bulk.dispatching', 'A disparar {n}...', { n: runnable.length })}`;""", 1),
    ("""            btn.innerHTML = `<i class="fas fa-bolt"></i> Re-run Filtrados`;""",
     """            btn.innerHTML = `<i class="fas fa-bolt"></i> ${_collT('coll.bulk_run', 'Re-run Filtrados')}`;""", 1),
    ("""        const summaryMsg = `Bulk Re-run concluido:\\n\\n` +
            `  Dispatched: ${dispatched}/${runnable.length}\\n` +
            `  Failed dispatch: ${failed}\\n\\n` +
            (failedTasks.length > 0 ? `Tasks falhados (top 5):\\n${failedTasks.map(t => '  - ' + t).join('\\n')}\\n\\n` : '') +
            `Tasks dispatched estao agora em PENDING. Clique "Actualizar" em ~1min para ver progresso.`;""",
     """        const summaryMsg = _collT('coll.bulk.done_title', 'Re-execucao terminada:') + '\\n\\n' +
            '  ' + _collTp('coll.bulk.done_ok', 'Disparadas: {ok} de {n}', { ok: dispatched, n: runnable.length }) + '\\n' +
            '  ' + _collTp('coll.bulk.done_failed', 'Falharam ao disparar: {n}', { n: failed }) + '\\n\\n' +
            (failedTasks.length > 0
                ? _collT('coll.bulk.done_failed_list', 'Tarefas que falharam (as 5 primeiras):')
                  + `\\n${failedTasks.map(t => '  - ' + t).join('\\n')}\\n\\n`
                : '') +
            _collT('coll.bulk.done_note', 'As tarefas disparadas ficaram em fila. Carregue em Actualizar daqui a um minuto para ver o progresso.');""", 1),

    # --- activar / desactivar
    ("""        const action = newEnabled ? 'ACTIVAR' : 'DESACTIVAR';""",
     """        const action = newEnabled
            ? _collT('coll.toggle.word_on', 'ACTIVAR')
            : _collT('coll.toggle.word_off', 'DESACTIVAR');""", 1),
    ("""            reason = prompt(
                `${action} "${task.name}"?\\n\\n` +
                `Motivo (obrigatorio, minimo 20 caracteres):\\n` +
                `Exemplo: "Reactivar para validacao de fix no collector de suspect pages"`
            );""",
     """            reason = prompt(_collTp('coll.toggle.prompt',
                '{accao} "{nome}"?\\n\\nMotivo (obrigatorio, pelo menos 20 caracteres):\\nExemplo: Reactivar para validar a correccao no recolhedor de paginas suspeitas',
                { accao: action, nome: task.name }));""", 1),
    ("""            alert(`Motivo demasiado curto (${reason.length} caracteres). Minimo: 20 caracteres.\\n\\nIsto garante rastreabilidade adequada no historico de alteracoes.`);""",
     """            alert(_collTp('coll.toggle.too_short',
                'Motivo demasiado curto ({n} caracteres). Sao precisos pelo menos 20.\\n\\nE\\' isto que deixa rasto de quem mudou o que, e porque.',
                { n: reason.length }));""", 1),
    ("""        if (toggleBtn) { toggleBtn.disabled = true; toggleBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> A processar...'; }""",
     """        if (toggleBtn) { toggleBtn.disabled = true; toggleBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + _collT('coll.toggle.processing', 'A processar...'); }""", 1),
    ("""            setTimeout(() => collRefresh(false), 1000);
        } catch (e) {
            alert('Erro: ' + e.message);
        }""",
     """            setTimeout(() => collRefresh(false), 1000);
        } catch (e) {
            alert(_collT('coll.det.error', 'Erro:') + ' ' + e.message);
        }""", 1),

    # --- titulos dos estados do acompanhamento
    ("""            registering: { icon: 'fa-spinner fa-spin',   color: '#3b82f6', title: 'A registar pedido',           terminal: false },
            pending:     { icon: 'fa-clock fa-spin',      color: '#f59e0b', title: 'Aguardando execucao',         terminal: false },
            running:     { icon: 'fa-cog fa-spin',        color: '#3b82f6', title: 'Em execucao',                 terminal: false },
            done:        { icon: 'fa-check-circle',       color: '#10b981', title: 'Concluido com sucesso',       terminal: true },
            error:       { icon: 'fa-exclamation-triangle',color:'#ef4444', title: 'Erro',                        terminal: true },
            timeout:     { icon: 'fa-hourglass-end',      color: '#f59e0b', title: 'Timeout',                     terminal: true },""",
     """            registering: { icon: 'fa-spinner fa-spin',   color: '#3b82f6', title: _collT('coll.run.st_registering', 'A registar pedido'),     terminal: false },
            pending:     { icon: 'fa-clock fa-spin',      color: '#f59e0b', title: _collT('coll.run.st_pending', 'Aguardando execucao'),      terminal: false },
            running:     { icon: 'fa-cog fa-spin',        color: '#3b82f6', title: _collT('coll.run.st_running', 'Em execucao'),              terminal: false },
            done:        { icon: 'fa-check-circle',       color: '#10b981', title: _collT('coll.run.st_done', 'Concluido com sucesso'),       terminal: true },
            error:       { icon: 'fa-exclamation-triangle',color:'#ef4444', title: _collT('coll.run.st_error', 'Erro'),                       terminal: true },
            timeout:     { icon: 'fa-hourglass-end',      color: '#f59e0b', title: _collT('coll.run.st_timeout', 'Timeout'),                  terminal: true },""", 1),
    ("""                            Fechar
                        </button>""",
     """                            ${_collT('coll.run.close', 'Fechar')}
                        </button>""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: as acções traduzidas fecham o ecrã** (owner 16/09). Último lote: executar uma tarefa\n"
    "  agora e acompanhar o pedido até ao fim, re-correr em massa as tarefas filtradas, e activar ou desactivar\n"
    "  com motivo obrigatório. São quase todos textos de progresso e de erro — os que só se vêem quando algo\n"
    "  corre mal, e por isso os que mais facilmente ficavam por traduzir. O número do pedido, a duração, o nome\n"
    "  da tarefa e as contagens entram nas frases por marcadores, e não por concatenação, para cada idioma os\n"
    "  poder pôr onde precisa. O ecrã do Collector Health fica sem uma única frase escrita à mão. [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- Collector Health (lote 2d, ultimo): as accoes falam o idioma escolhido.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
RUN = ["need_enable", "confirm", "st_registering", "st_pending", "st_running", "st_done", "st_error",
       "st_timeout", "registering", "err_register", "queued", "queued_dots", "running", "done",
       "failed", "unknown_error", "timeout_queue", "timeout_poller", "close"]
BULK = ["none", "confirm_title", "confirm_count", "confirm_more", "confirm_skipped", "confirm_ask",
        "dispatching", "done_title", "done_ok", "done_failed", "done_failed_list", "done_note"]
TOGGLE = ["word_on", "word_off", "prompt", "too_short", "processing"]


def test_os_tres_idiomas_completos():
    for loc in ("pt", "en", "es"):
        coll = LOCS[loc]["coll"]
        for k in RUN:
            assert coll["run"][k].strip(), f"{loc}: run.{k}"
        for k in BULK:
            assert coll["bulk"][k].strip(), f"{loc}: bulk.{k}"
        for k in TOGGLE:
            assert coll["toggle"][k].strip(), f"{loc}: toggle.{k}"
        # lotes anteriores intactos
        assert len(coll["state"]) == 7 and coll["mute"]["title"] and coll["det"]["tab_overview"]


def test_os_marcadores_existem_em_todos_os_idiomas():
    """Se um idioma perder o {id} ou o {n}, o utilizador fica sem o numero."""
    esperados = {
        ("run", "confirm"): ["{nome}"], ("run", "queued"): ["{id}"],
        ("run", "queued_dots"): ["{id}", "{p}", "{s}"], ("run", "running"): ["{id}"],
        ("run", "done"): ["{ms}", "{n}"], ("run", "failed"): ["{err}"],
        ("run", "timeout_queue"): ["{s}", "{id}"], ("run", "timeout_poller"): ["{s}", "{id}"],
        ("bulk", "confirm_count"): ["{n}"], ("bulk", "confirm_more"): ["{n}"],
        ("bulk", "confirm_skipped"): ["{n}"], ("bulk", "dispatching"): ["{n}"],
        ("bulk", "done_ok"): ["{ok}", "{n}"], ("bulk", "done_failed"): ["{n}"],
        ("toggle", "prompt"): ["{accao}", "{nome}"], ("toggle", "too_short"): ["{n}"],
    }
    for loc in ("pt", "en", "es"):
        for (grupo, chave), marcas in esperados.items():
            texto = LOCS[loc]["coll"][grupo][chave]
            for m in marcas:
                assert m in texto, f"{loc}: {grupo}.{chave} sem {m}"


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    for grupo in ("run", "bulk", "toggle"):
        pt, br = LOCS["pt"]["coll"][grupo], LOCS["pt-BR"]["coll"].get(grupo, {})
        assert [k for k, v in br.items() if pt.get(k) == v] == [], f"{grupo}: chaves repetidas"
        assert set(br) <= set(pt)


def test_o_portal_usa_as_chaves():
    for k in RUN:
        assert f"'coll.run.{k}'" in PORTAL, f"chave nao usada: coll.run.{k}"
    for k in BULK:
        assert f"'coll.bulk.{k}'" in PORTAL, f"chave nao usada: coll.bulk.{k}"
    for k in TOGGLE:
        assert f"'coll.toggle.{k}'" in PORTAL, f"chave nao usada: coll.toggle.{k}"


def test_o_jargao_ingles_desapareceu_das_accoes():
    """O portugues CONTINUA la' como recurso dentro de _collT -- e' assim de proposito.

    O que nao pode sobrar e' o jargao ingles que estas mensagens tinham e que nenhum idioma
    aproveitava: Dispatched, Failed dispatch, PENDING, Rows. Comentarios ficam de fora da conta,
    porque contam a historia do codigo e nao vao para o ecra.
    """
    i = PORTAL.index("window.collTriggerRun = async function()")
    j = PORTAL.index("function _collUpdateToggleUI(task)")
    bloco = "\\n".join(l for l in PORTAL[i:j].split("\\n") if not l.lstrip().startswith("//"))
    for frase in ("Bulk Re-run", "Dispatched:", "Failed dispatch:", "Tasks falhados (top 5)",
                  "Tasks dispatched estao agora", "task(s) skipped", "PENDING na fila",
                  "Rows: ${rows}", "em execucao...`"):
        assert frase not in bloco, f"ficou por traduzir: {frase}"


def test_nada_de_portugues_no_ingles():
    en = LOCS["en"]["coll"]
    texto = " | ".join(list(en["run"].values()) + list(en["bulk"].values()) + list(en["toggle"].values())).lower()
    for p in ("pedido", "tarefa", "recolha", "motivo", "activar"):
        assert p not in texto, f"ingles com texto portugues: {p}"
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


def _fundir(raw: str, novos: dict, loc: str) -> str:
    ancora = '  "coll": {\n'
    if raw.count(ancora) != 1:
        raise SystemExit(f"[ABORT] {loc}: grupo coll nao encontrado (faltam os lotes anteriores?)")
    antes = json.loads(raw)
    repetidos = set(novos) & set(antes["coll"])
    if repetidos:
        raise SystemExit(f"[ABORT] {loc}: coll ja tem {sorted(repetidos)}")
    texto = json.dumps(novos, ensure_ascii=False, indent=2)
    bloco = "\n".join("  " + l for l in texto.split("\n")[1:-1])
    novo = raw.replace(ancora, ancora + bloco + ",\n")
    d = json.loads(novo)
    for k in antes:
        if k != "coll":
            assert d[k] == antes[k], f"{loc}: o grupo {k} mudou"
    for k in antes["coll"]:
        assert d["coll"][k] == antes["coll"][k], f"{loc}: coll.{k} mudou"
    assert set(d["coll"]) == set(antes["coll"]) | set(novos)
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "coll.det.tab_overview" not in portal:
        print("[ABORT] falta o lote 2c (COLL_I18N_DETALHE_2026-09-16_apply.py). Corre-o primeiro."); return 1

    out = {"portal": _apply(portal, EDITS, "portal"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}

    locais = {}
    for loc, rel in LOCALES.items():
        caminho = base / rel
        novo = _fundir(caminho.read_bytes().decode("utf-8"), GRUPOS[loc], loc)
        locais[loc] = (caminho, novo)
        print(f"[ok] {loc}: run/bulk/toggle com {sum(len(v) for v in GRUPOS[loc].values())} chaves")

    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal {len(EDITS)} blocos; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    for loc, (caminho, novo) in locais.items():
        caminho.write_bytes(novo.encode("utf-8")); print(f"[write] {LOCALES[loc]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_coll_i18n_accoes_20260916.py "
          "tests/unit/test_coll_i18n_detalhe_20260916.py tests/unit/test_coll_i18n_mute_20260916.py "
          "tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
