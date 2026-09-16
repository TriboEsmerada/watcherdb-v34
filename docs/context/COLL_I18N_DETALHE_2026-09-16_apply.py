# -*- coding: utf-8 -*-
"""Collector Health, lote 2c/4: janela de detalhe da tarefa (2026-09-16).

Segue os lotes 1 (7 estados), 2a (barra e eventos) e 2b (silenciar alertas). Fica para o 2d o que sao ACCOES:
executar agora com o acompanhamento do pedido, re-correr em massa, e activar/desactivar com o motivo.

DEFEITO ENCONTRADO E CORRIGIDO AQUI (mesma familia do que apanhamos de manha nas modais dos KPI):
`collSwitchTab` escolhia o separador activo comparando o TEXTO VISIVEL com o nome interno --
`el.textContent.toLowerCase().includes(tabName)`. Enquanto os separadores estavam em ingles e os nomes internos
tambem, funcionava por acaso. Traduzir "Overview" para "Visao geral" partiria o realce do separador em todos os
idiomas, sem erro nenhum no registo. Cada separador passa a ter `data-tab` e a comparacao e' feita sobre esse
atributo, que ninguem traduz. Isto tambem apaga o remendo que existia para o separador "runs".

TAMBEM: a tabela ordenavel usava o rotulo da coluna COMO CHAVE DOS DADOS (`row[col.k]`, cabecalho `${col.k}`).
Traduzir o cabecalho teria esvaziado as tres tabelas. Passa a haver `col.lbl` opcional para o que se mostra; a
chave dos dados continua a ser `col.k`, que fica em ingles e nunca se traduz.

DEPENDE de: os lotes 1, 2a e 2b (usa _collT e _collTp; reaproveita coll.loading e coll.col.*).

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/COLL_I18N_DETALHE_2026-09-16_apply.py --check
  py docs/context/COLL_I18N_DETALHE_2026-09-16_apply.py
  py -m pytest tests/unit/test_coll_i18n_detalhe_20260916.py tests/unit/test_coll_i18n_mute_20260916.py tests/unit/test_coll_i18n_barra_20260916.py tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov
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
    "test": Path("tests/unit/test_coll_i18n_detalhe_20260916.py"),
}
LOCALES = {loc: Path(f"static/i18n/{loc}.json") for loc in ("pt", "pt-BR", "en", "es")}
MARK = "coll.det.tab_overview"

PT = {
    "det": {
        "tab_overview": "Resumo", "tab_logs": "Erros", "tab_config": "Configuração",
        "tab_runs": "Execuções", "tab_audit": "Alterações",
        "environment": "Ambiente", "interval": "Intervalo", "enabled": "Activo",
        "status": "Estado", "data_source": "Fonte de dados", "last_run": "Última passagem",
        "delay": "Atraso", "duration": "Duração do último ciclo", "rows": "Linhas recolhidas",
        "rows_title": "Linhas inseridas na tabela de passagem no último ciclo (não é o número de servidores)",
        "active_slot": "Lado activo", "failures_24h": "Falhas nas últimas 24 horas",
        "class": "Classe", "module": "Módulo", "target_tables": "Tabelas de destino",
        "description": "Descrição",
        "yes": "Sim", "no": "Não",
        "minutes": "min",
        "ds_bg": "Blue/Green (KPI_STG_ACTIVE_TABLE)",
        "ds_max": "MAX(Update_TS) directo da tabela (sem Blue/Green)",
        "ds_none": "Sem registos recentes (sem Blue/Green)",
        "loading_logs": "A carregar os erros...",
        "empty_logs": "Sem erros registados para esta tarefa.",
        "loading_config": "A carregar a configuração...",
        "config_source": "Origem:",
        "loading_runs": "A carregar o histórico...",
        "empty_runs": "Sem execuções manuais registadas para esta tarefa.",
        "loading_audit": "A carregar o histórico de activações e desactivações...",
        "empty_audit": "Sem registos de activação ou desactivação para esta tarefa.",
        "no_data": "Sem dados.",
        "error": "Erro:",
        "activate": "Activar", "deactivate": "Desactivar", "run_now": "Executar agora",
        "run_title_on": "Executar a recolha agora",
        "run_title_off": "Tarefa desactivada — active-a primeiro para poder executar",
        "override_on": "Excepção activa na base de dados — activada por",
        "override_off": "Excepção activa na base de dados — desactivada por",
        "via_config_on": "Activa pelo ficheiro de configuração",
        "via_config_off": "Desactivada pelo ficheiro de configuração",
    },
    "col": {
        "timestamp": "Data e hora", "level": "Nível", "message": "Mensagem",
        "id": "ID", "requested_at": "Pedido em", "by": "Por", "status": "Estado",
        "pickup_lag": "Espera até começar", "error": "Erro",
        "datetime": "Data e hora", "user": "Utilizador", "reason": "Motivo",
    },
}

EN = {
    "det": {
        "tab_overview": "Overview", "tab_logs": "Errors", "tab_config": "Configuration",
        "tab_runs": "Runs", "tab_audit": "Changes",
        "environment": "Environment", "interval": "Interval", "enabled": "Enabled",
        "status": "State", "data_source": "Data source", "last_run": "Last run",
        "delay": "Delay", "duration": "Last cycle duration", "rows": "Rows collected",
        "rows_title": "Rows inserted into the staging table on the last cycle (not the number of servers)",
        "active_slot": "Active slot", "failures_24h": "Failures in the last 24 hours",
        "class": "Class", "module": "Module", "target_tables": "Target tables",
        "description": "Description",
        "yes": "Yes", "no": "No",
        "minutes": "min",
        "ds_bg": "Blue/Green (KPI_STG_ACTIVE_TABLE)",
        "ds_max": "MAX(Update_TS) straight from the table (no Blue/Green)",
        "ds_none": "No recent rows (no Blue/Green)",
        "loading_logs": "Loading errors...",
        "empty_logs": "No errors recorded for this task.",
        "loading_config": "Loading configuration...",
        "config_source": "Source:",
        "loading_runs": "Loading history...",
        "empty_runs": "No manual runs recorded for this task.",
        "loading_audit": "Loading the enable/disable history...",
        "empty_audit": "No enable or disable records for this task.",
        "no_data": "No data.",
        "error": "Error:",
        "activate": "Enable", "deactivate": "Disable", "run_now": "Run now",
        "run_title_on": "Run the collection now",
        "run_title_off": "Task disabled — enable it first to be able to run it",
        "override_on": "Override active in the database — enabled by",
        "override_off": "Override active in the database — disabled by",
        "via_config_on": "Enabled by the configuration file",
        "via_config_off": "Disabled by the configuration file",
    },
    "col": {
        "timestamp": "Timestamp", "level": "Level", "message": "Message",
        "id": "ID", "requested_at": "Requested at", "by": "By", "status": "Status",
        "pickup_lag": "Wait before start", "error": "Error",
        "datetime": "Date and time", "user": "User", "reason": "Reason",
    },
}

ES = {
    "det": {
        "tab_overview": "Resumen", "tab_logs": "Errores", "tab_config": "Configuración",
        "tab_runs": "Ejecuciones", "tab_audit": "Cambios",
        "environment": "Entorno", "interval": "Intervalo", "enabled": "Activo",
        "status": "Estado", "data_source": "Fuente de datos", "last_run": "Última ejecución",
        "delay": "Retraso", "duration": "Duración del último ciclo", "rows": "Filas recolectadas",
        "rows_title": "Filas insertadas en la tabla de paso en el último ciclo (no es el número de servidores)",
        "active_slot": "Lado activo", "failures_24h": "Fallas en las últimas 24 horas",
        "class": "Clase", "module": "Módulo", "target_tables": "Tablas de destino",
        "description": "Descripción",
        "yes": "Sí", "no": "No",
        "minutes": "min",
        "ds_bg": "Blue/Green (KPI_STG_ACTIVE_TABLE)",
        "ds_max": "MAX(Update_TS) directo de la tabla (sin Blue/Green)",
        "ds_none": "Sin registros recientes (sin Blue/Green)",
        "loading_logs": "Cargando los errores...",
        "empty_logs": "Sin errores registrados para esta tarea.",
        "loading_config": "Cargando la configuración...",
        "config_source": "Origen:",
        "loading_runs": "Cargando el historial...",
        "empty_runs": "Sin ejecuciones manuales registradas para esta tarea.",
        "loading_audit": "Cargando el historial de activaciones y desactivaciones...",
        "empty_audit": "Sin registros de activación o desactivación para esta tarea.",
        "no_data": "Sin datos.",
        "error": "Error:",
        "activate": "Activar", "deactivate": "Desactivar", "run_now": "Ejecutar ahora",
        "run_title_on": "Ejecutar la recolección ahora",
        "run_title_off": "Tarea desactivada: actívela primero para poder ejecutarla",
        "override_on": "Excepción activa en la base de datos: activada por",
        "override_off": "Excepción activa en la base de datos: desactivada por",
        "via_config_on": "Activa por el archivo de configuración",
        "via_config_off": "Desactivada por el archivo de configuración",
    },
    "col": {
        "timestamp": "Fecha y hora", "level": "Nivel", "message": "Mensaje",
        "id": "ID", "requested_at": "Solicitado el", "by": "Por", "status": "Estado",
        "pickup_lag": "Espera hasta comenzar", "error": "Error",
        "datetime": "Fecha y hora", "user": "Usuario", "reason": "Motivo",
    },
}

PT_BR = {
    "det": {
        "last_run": "Última execução",
        # rows_title nao entra: em pt-BR seria exactamente igual ao pt, e o projecto recusa sobreposto redundante
        "ds_max": "MAX(Update_TS) direto da tabela (sem Blue/Green)",
        "empty_runs": "Sem execuções manuais registradas para esta tarefa.",
        "loading_audit": "A carregar o histórico de ativações e desativações...",
        "empty_audit": "Sem registros de ativação ou desativação para esta tarefa.",
        "activate": "Ativar", "deactivate": "Desativar",
        "run_title_off": "Tarefa desativada — ative-a primeiro para poder executar",
        "override_on": "Exceção ativa no banco de dados — ativada por",
        "override_off": "Exceção ativa no banco de dados — desativada por",
        "via_config_on": "Ativa pelo arquivo de configuração",
        "via_config_off": "Desativada pelo arquivo de configuração",
        "enabled": "Ativo",
    },
    "col": {"requested_at": "Solicitado em"},
}

GRUPOS = {"pt": PT, "pt-BR": PT_BR, "en": EN, "es": ES}

# --------------------------------------------------------------------------- portal
EDITS = [
    # --- separadores: rotulo traduzido + data-tab (o realce deixa de depender do texto)
    ("""                    <div class="coll-tab active" onclick="collSwitchTab('overview')">Overview</div>
                    <div class="coll-tab" onclick="collSwitchTab('logs')">Error Log</div>
                    <div class="coll-tab" onclick="collSwitchTab('config')">Config</div>
                    <div class="coll-tab" onclick="collSwitchTab('runs')">Run History</div>
                    <div class="coll-tab" onclick="collSwitchTab('audit')">Audit</div>
""",
     """                    <div class="coll-tab active" data-tab="overview" onclick="collSwitchTab('overview')">${_collT('coll.det.tab_overview', 'Overview')}</div>
                    <div class="coll-tab" data-tab="logs" onclick="collSwitchTab('logs')">${_collT('coll.det.tab_logs', 'Error Log')}</div>
                    <div class="coll-tab" data-tab="config" onclick="collSwitchTab('config')">${_collT('coll.det.tab_config', 'Config')}</div>
                    <div class="coll-tab" data-tab="runs" onclick="collSwitchTab('runs')">${_collT('coll.det.tab_runs', 'Run History')}</div>
                    <div class="coll-tab" data-tab="audit" onclick="collSwitchTab('audit')">${_collT('coll.det.tab_audit', 'Audit')}</div>
""", 1),
    ("""        document.querySelectorAll('.coll-tab').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.coll-tab').forEach(el => {
            if ((el.textContent || '').toLowerCase().includes(tabName.toLowerCase()) ||
                (tabName === 'runs' && (el.textContent || '').toLowerCase().includes('run'))) {
                el.classList.add('active');
            }
        });
""",
     """        // 2026-09-16: o separador activo era escolhido pelo TEXTO VISIVEL
        // (textContent.includes(tabName)), com um remendo a` parte para 'runs'. Funcionava por acaso
        // enquanto os rotulos estavam em ingles; traduzi-los partia o realce em todos os idiomas, sem
        // erro nenhum. O atributo data-tab nao se traduz.
        document.querySelectorAll('.coll-tab').forEach(el => {
            el.classList.toggle('active', el.dataset.tab === tabName);
        });
""", 1),

    # --- botoes do rodape
    ("""                        <i class="fas fa-power-off"></i> <span id="coll-toggle-label">Activar</span>""",
     """                        <i class="fas fa-power-off"></i> <span id="coll-toggle-label">${_collT('coll.det.activate', 'Activar')}</span>""", 1),
    ("""                        <i class="fas fa-play"></i> Run now
""",
     """                        <i class="fas fa-play"></i> ${_collT('coll.det.run_now', 'Run now')}
""", 1),
    ("""            runBtn.title = task.enabled ? 'Executar coleta agora' : 'Task desactivado — active primeiro para poder executar';""",
     """            runBtn.title = task.enabled
                ? _collT('coll.det.run_title_on', 'Executar coleta agora')
                : _collT('coll.det.run_title_off', 'Task desactivado — active primeiro para poder executar');""", 2),
    # (duas vezes: ao abrir o detalhe e ao actualizar o estado do botao depois de activar/desactivar)

    # --- fonte de dados
    ("""                'blue_green':           { label: 'Blue/Green (KPI_STG_ACTIVE_TABLE)', color: 'var(--color-text-link)' },
                'non_bg_max_update_ts': { label: 'MAX(Update_TS) directo da tabela (non-Blue/Green)', color: '#a78bfa' },
                'non_bg_no_data':       { label: 'Sem registos recentes (non-Blue/Green)', color: 'var(--color-text-disabled)' },""",
     """                'blue_green':           { label: _collT('coll.det.ds_bg', 'Blue/Green (KPI_STG_ACTIVE_TABLE)'), color: 'var(--color-text-link)' },
                'non_bg_max_update_ts': { label: _collT('coll.det.ds_max', 'MAX(Update_TS) directo da tabela (non-Blue/Green)'), color: '#a78bfa' },
                'non_bg_no_data':       { label: _collT('coll.det.ds_none', 'Sem registos recentes (non-Blue/Green)'), color: 'var(--color-text-disabled)' },""", 1),

    # --- lista de propriedades do resumo
    ("""                <div>Environment</div><div>${_esc(task.environment||'—')}</div>
                <div>Interval</div><div>${task.interval_minutes} min</div>
                <div>Enabled</div><div>${task.enabled ? 'Sim' : 'Nao'}</div>
                <div>Status</div><div>${task.status} — ${_esc(task.status_reason||'')}</div>
                <div>Fonte de dados</div><div><span style="color:${ds.color};font-weight:600;">${_esc(ds.label)}</span></div>
                <div>Ultimo run</div><div>${_collDetailLastRun(task)}</div>
                <div>Atraso</div><div>${_collDetailDelay(task)}</div>
                <div>Duracao ultimo ciclo</div><div>${_fmtDur(task.collection_duration_ms)}</div>
                <div>Rows recolhidas</div><div title="Numero de rows inseridas no STG no ultimo ciclo (nao distinto de servers)">${task.servers_collected==null?'—':task.servers_collected}</div>
                <div>Active slot</div><div>${_esc(task.active_slot||'—')}</div>
                <div>Falhas nas 24h</div><div style="color:${(task.failure_count_24h||0)>0?'#ef4444':'#10b981'};font-weight:600;">${task.failure_count_24h||0}</div>
                <div>Classe</div><div>${_esc(task.class||'')}</div>
                <div>Modulo</div><div>${_esc(task.module||'')}</div>
                <div>Target tables</div><div>${(task.target_tables||[]).map(t=>'<code>'+_esc(t)+'</code>').join('<br>') || '—'}</div>
                <div>Descricao</div><div>${_esc(task.description||'—')}</div>
""",
     """                <div>${_collT('coll.det.environment', 'Environment')}</div><div>${_esc(task.environment||'—')}</div>
                <div>${_collT('coll.det.interval', 'Interval')}</div><div>${task.interval_minutes} ${_collT('coll.det.minutes', 'min')}</div>
                <div>${_collT('coll.det.enabled', 'Enabled')}</div><div>${task.enabled ? _collT('coll.det.yes', 'Sim') : _collT('coll.det.no', 'Nao')}</div>
                <div>${_collT('coll.det.status', 'Status')}</div><div>${task.status} — ${_esc(task.status_reason||'')}</div>
                <div>${_collT('coll.det.data_source', 'Fonte de dados')}</div><div><span style="color:${ds.color};font-weight:600;">${_esc(ds.label)}</span></div>
                <div>${_collT('coll.det.last_run', 'Ultimo run')}</div><div>${_collDetailLastRun(task)}</div>
                <div>${_collT('coll.det.delay', 'Atraso')}</div><div>${_collDetailDelay(task)}</div>
                <div>${_collT('coll.det.duration', 'Duracao ultimo ciclo')}</div><div>${_fmtDur(task.collection_duration_ms)}</div>
                <div>${_collT('coll.det.rows', 'Rows recolhidas')}</div><div title="${_collT('coll.det.rows_title', 'Numero de rows inseridas no STG no ultimo ciclo (nao distinto de servers)')}">${task.servers_collected==null?'—':task.servers_collected}</div>
                <div>${_collT('coll.det.active_slot', 'Active slot')}</div><div>${_esc(task.active_slot||'—')}</div>
                <div>${_collT('coll.det.failures_24h', 'Falhas nas 24h')}</div><div style="color:${(task.failure_count_24h||0)>0?'#ef4444':'#10b981'};font-weight:600;">${task.failure_count_24h||0}</div>
                <div>${_collT('coll.det.class', 'Classe')}</div><div>${_esc(task.class||'')}</div>
                <div>${_collT('coll.det.module', 'Modulo')}</div><div>${_esc(task.module||'')}</div>
                <div>${_collT('coll.det.target_tables', 'Target tables')}</div><div>${(task.target_tables||[]).map(t=>'<code>'+_esc(t)+'</code>').join('<br>') || '—'}</div>
                <div>${_collT('coll.det.description', 'Descricao')}</div><div>${_esc(task.description||'—')}</div>
""", 1),

    # --- separador dos erros
    ("""            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">A carregar error log...</div>';""",
     """            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.loading_logs', 'A carregar error log...') + '</div>';""", 1),
    ("""                    body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">Sem erros registados para este task.</div>';""",
     """                    body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.empty_logs', 'Sem erros registados para este task.') + '</div>';""", 1),
    ("""                        [{k:'Timestamp',w:'160px'},{k:'Level',w:'70px'},{k:'Duracao',sortK:'_duration_sort',w:'80px'},{k:'Mensagem',wrap:true}]""",
     """                        [{k:'Timestamp',lbl:_collT('coll.col.timestamp','Timestamp'),w:'160px'},
                         {k:'Level',lbl:_collT('coll.col.level','Level'),w:'70px'},
                         {k:'Duracao',lbl:_collT('coll.col.duration','Duracao'),sortK:'_duration_sort',w:'80px'},
                         {k:'Mensagem',lbl:_collT('coll.col.message','Mensagem'),wrap:true}]""", 1),

    # --- separador da configuracao
    ("""            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">A carregar config...</div>';""",
     """            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.loading_config', 'A carregar config...') + '</div>';""", 1),
    ("""                body.innerHTML = `<div style="color:var(--color-text-tertiary);font-size:11px;margin-bottom:6px;">Source: ${_esc(d.source_path||'')}</div>`""",
     """                body.innerHTML = `<div style="color:var(--color-text-tertiary);font-size:11px;margin-bottom:6px;">${_collT('coll.det.config_source', 'Source:')} ${_esc(d.source_path||'')}</div>`""", 1),

    # --- separador das execucoes
    ("""            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">A carregar historico...</div>';""",
     """            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.loading_runs', 'A carregar historico...') + '</div>';""", 1),
    ("""                    body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">Sem runs manuais registados para este task.</div>';""",
     """                    body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.empty_runs', 'Sem runs manuais registados para este task.') + '</div>';""", 1),
    ("""                        [{k:'ID',w:'50px'},{k:'Requested at',w:'160px'},{k:'By',w:'100px'},{k:'Status',w:'80px'},
                         {k:'Pickup lag',sortK:'_pickup_sort',w:'80px'},{k:'Duracao',sortK:'_dur_sort',w:'80px'},{k:'Erro',wrap:true}]""",
     """                        [{k:'ID',lbl:_collT('coll.col.id','ID'),w:'50px'},
                         {k:'Requested at',lbl:_collT('coll.col.requested_at','Requested at'),w:'160px'},
                         {k:'By',lbl:_collT('coll.col.by','By'),w:'100px'},
                         {k:'Status',lbl:_collT('coll.col.status','Status'),w:'80px'},
                         {k:'Pickup lag',lbl:_collT('coll.col.pickup_lag','Pickup lag'),sortK:'_pickup_sort',w:'80px'},
                         {k:'Duracao',lbl:_collT('coll.col.duration','Duracao'),sortK:'_dur_sort',w:'80px'},
                         {k:'Erro',lbl:_collT('coll.col.error','Erro'),wrap:true}]""", 1),

    # --- separador das alteracoes
    ("""            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">A carregar historico de activacoes/desactivacoes...</div>';""",
     """            body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.loading_audit', 'A carregar historico de activacoes/desactivacoes...') + '</div>';""", 1),
    ("""                    body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">Sem registos de activacao/desactivacao para este task.</div>';""",
     """                    body.innerHTML = '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.empty_audit', 'Sem registos de activacao/desactivacao para este task.') + '</div>';""", 1),
    ("""                        [{k:'Data/Hora',w:'160px'},{k:'Accao',w:'90px'},{k:'Utilizador',w:'120px'},{k:'Motivo',wrap:true}]""",
     """                        [{k:'Data/Hora',lbl:_collT('coll.col.datetime','Data/Hora'),w:'160px'},
                         {k:'Accao',lbl:_collT('coll.col.action','Accao'),w:'90px'},
                         {k:'Utilizador',lbl:_collT('coll.col.user','Utilizador'),w:'120px'},
                         {k:'Motivo',lbl:_collT('coll.col.reason','Motivo'),wrap:true}]""", 1),

    # --- a mesma mensagem de erro nos quatro separadores
    ("""'<div style="color:#ef4444;padding:20px;">Erro: ' + _esc(e.message) + '</div>'""",
     """'<div style="color:#ef4444;padding:20px;">' + _collT('coll.det.error', 'Erro:') + ' ' + _esc(e.message) + '</div>'""", 4),

    # --- tabela ordenavel: o rotulo deixa de ser a chave dos dados
    ("""                + `${col.k}${arrow}</th>`;""",
     """                // 2026-09-16: `col.k` e' a CHAVE dos dados (row[col.k]) e fica sempre em ingles; `col.lbl`
                // e' o que se mostra. Antes eram a mesma coisa, e traduzir o cabecalho esvaziava a tabela.
                + `${col.lbl || col.k}${arrow}</th>`;""", 1),
    ("""        if (!rows.length) return '<div style="padding:20px;color:var(--color-text-tertiary);">Sem dados.</div>';""",
     """        if (!rows.length) return '<div style="padding:20px;color:var(--color-text-tertiary);">' + _collT('coll.det.no_data', 'Sem dados.') + '</div>';""", 1),

    # --- estado do botao activar/desactivar
    ("""                toggleBtn.innerHTML = '<i class="fas fa-power-off"></i> Desactivar';""",
     """                toggleBtn.innerHTML = '<i class="fas fa-power-off"></i> ' + _collT('coll.det.deactivate', 'Desactivar');""", 1),
    ("""                toggleBtn.innerHTML = '<i class="fas fa-power-off"></i> Activar';""",
     """                toggleBtn.innerHTML = '<i class="fas fa-power-off"></i> ' + _collT('coll.det.activate', 'Activar');""", 1),
    ("""                    toggleStatus.innerHTML = '<i class="fas fa-database" style="color:#6366f1;margin-right:4px;"></i>Override activo (BD) — activado por ' + _esc(task.override.changed_by || '?');""",
     """                    toggleStatus.innerHTML = '<i class="fas fa-database" style="color:#6366f1;margin-right:4px;"></i>' + _collT('coll.det.override_on', 'Override activo (BD) — activado por') + ' ' + _esc(task.override.changed_by || '?');""", 1),
    ("""                    toggleStatus.innerHTML = '<i class="fas fa-file-code" style="color:#22c55e;margin-right:4px;"></i>Activo via config.yaml';""",
     """                    toggleStatus.innerHTML = '<i class="fas fa-file-code" style="color:#22c55e;margin-right:4px;"></i>' + _collT('coll.det.via_config_on', 'Activo via config.yaml');""", 1),
    ("""                    toggleStatus.innerHTML = '<i class="fas fa-database" style="color:#ef4444;margin-right:4px;"></i>Override activo (BD) — desactivado por ' + _esc(task.override.changed_by || '?');""",
     """                    toggleStatus.innerHTML = '<i class="fas fa-database" style="color:#ef4444;margin-right:4px;"></i>' + _collT('coll.det.override_off', 'Override activo (BD) — desactivado por') + ' ' + _esc(task.override.changed_by || '?');""", 1),
    ("""                    toggleStatus.innerHTML = '<i class="fas fa-file-code" style="color:var(--color-text-tertiary);margin-right:4px;"></i>Desactivado via config.yaml';""",
     """                    toggleStatus.innerHTML = '<i class="fas fa-file-code" style="color:var(--color-text-tertiary);margin-right:4px;"></i>' + _collT('coll.det.via_config_off', 'Desactivado via config.yaml');""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Collector Health: janela de detalhe traduzida, e dois defeitos escondidos por trás disso** (owner 16/09).\n"
    "  Separadores, lista de propriedades, tabelas de erros, execuções e alterações passam a falar o idioma\n"
    "  escolhido. Pelo caminho: o separador activo era escolhido comparando o **texto visível** com o nome interno\n"
    "  — traduzi-lo partiria o realce em todos os idiomas, tal como aconteceu de manhã nas modais dos KPI; e as\n"
    "  tabelas usavam o rótulo da coluna como chave dos dados, pelo que traduzir o cabeçalho as teria esvaziado.\n"
    "  Ambos corrigidos: o separador compara um atributo, e a coluna passa a ter rótulo separado da chave.\n"
    "  [tier: Std]\n"
    "\n",
    1,
)

TEST_SRC = '''"""
2026-09-16 -- Collector Health (lote 2c): janela de detalhe traduzida, sem depender de texto visivel.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8").replace("\\r\\n", "\\n")
LOCS = {loc: json.loads((ROOT / "static" / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("pt", "pt-BR", "en", "es")}
ABAS = ["tab_overview", "tab_logs", "tab_config", "tab_runs", "tab_audit"]
COLS = ["timestamp", "level", "message", "id", "requested_at", "by", "status", "pickup_lag",
        "error", "datetime", "user", "reason"]


def test_os_tres_idiomas_completos():
    for loc in ("pt", "en", "es"):
        det = LOCS[loc]["coll"]["det"]
        for k in ABAS + ["environment", "interval", "enabled", "status", "data_source", "last_run",
                         "delay", "duration", "rows", "rows_title", "active_slot", "failures_24h",
                         "class", "module", "target_tables", "description", "yes", "no", "no_data",
                         "activate", "deactivate", "run_now", "run_title_on", "run_title_off"]:
            assert det[k].strip(), f"{loc}: det.{k}"
        for c in COLS:
            assert LOCS[loc]["coll"]["col"][c].strip(), f"{loc}: col.{c}"
        # lotes anteriores intactos
        assert len(LOCS[loc]["coll"]["state"]) == 7
        assert LOCS[loc]["coll"]["mute"]["title"].strip()


def test_o_separador_activo_nao_depende_do_texto_visivel():
    """O defeito da manha (comparar por titulo traduzido), agora nos separadores."""
    assert "el.dataset.tab === tabName" in PORTAL
    assert "(el.textContent || '').toLowerCase().includes(tabName.toLowerCase())" not in PORTAL
    assert "tabName === 'runs' && (el.textContent" not in PORTAL, "o remendo do runs tambem sai"
    for aba in ("overview", "logs", "config", "runs", "audit"):
        assert f'data-tab="{aba}"' in PORTAL


def test_a_coluna_tem_rotulo_separado_da_chave():
    """row[col.k] usa a chave; o cabecalho usa col.lbl. Traduzir a chave esvaziaria a tabela."""
    assert "${col.lbl || col.k}${arrow}" in PORTAL
    assert "${col.k}${arrow}" not in PORTAL
    for chave in ("'Timestamp'", "'Requested at'", "'Pickup lag'", "'Data/Hora'"):
        assert f"k:{chave}" in PORTAL, f"a chave dos dados {chave} tem de ficar como esta'"


def test_o_portal_usa_as_chaves_do_detalhe():
    for k in ABAS + ["environment", "interval", "enabled", "data_source", "last_run", "delay",
                     "duration", "rows", "rows_title", "active_slot", "failures_24h", "class",
                     "module", "target_tables", "description", "yes", "no", "no_data", "error",
                     "activate", "deactivate", "run_now", "run_title_on", "run_title_off",
                     "ds_bg", "ds_max", "ds_none", "loading_logs", "empty_logs", "loading_config",
                     "config_source", "loading_runs", "empty_runs", "loading_audit", "empty_audit",
                     "override_on", "override_off", "via_config_on", "via_config_off"]:
        assert f"'coll.det.{k}'" in PORTAL, f"chave nao usada no portal: coll.det.{k}"
    for c in COLS:
        assert f"'coll.col.{c}'" in PORTAL, f"chave nao usada no portal: coll.col.{c}"


def test_o_sobreposto_pt_br_nao_repete_o_pt():
    for grupo in ("det", "col"):
        pt, br = LOCS["pt"]["coll"][grupo], LOCS["pt-BR"]["coll"].get(grupo, {})
        assert [k for k, v in br.items() if pt.get(k) == v] == [], f"{grupo}: chaves repetidas"
        assert set(br) <= set(pt)


def test_nada_de_portugues_no_ingles():
    texto = " | ".join(list(LOCS["en"]["coll"]["det"].values()) + list(LOCS["en"]["coll"]["col"].values())).lower()
    for p in ("ambiente", "duração", "última", "utilizador", "activar", "tarefa"):
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
    """Acrescenta det e funde col dentro do grupo coll que ja existe."""
    ancora = '  "coll": {\n'
    if raw.count(ancora) != 1:
        raise SystemExit(f"[ABORT] {loc}: grupo coll nao encontrado (faltam os lotes anteriores?)")
    antes = json.loads(raw)
    if "det" in antes["coll"]:
        raise SystemExit(f"[ABORT] {loc}: coll.det ja existe")
    repetidas = set(novos.get("col", {})) & set(antes["coll"].get("col", {}))
    if repetidas:
        raise SystemExit(f"[ABORT] {loc}: coll.col ja tem {sorted(repetidas)}")
    # "det" entra como bloco novo; "col" tem de ser fundido no que ja existe
    texto = json.dumps({"det": novos["det"]}, ensure_ascii=False, indent=2)
    bloco = "\n".join("  " + l for l in texto.split("\n")[1:-1])
    novo = raw.replace(ancora, ancora + bloco + ",\n")
    if novos.get("col"):
        ancora_col = '    "col": {\n'
        if novo.count(ancora_col) != 1:
            raise SystemExit(f"[ABORT] {loc}: sub-grupo coll.col nao encontrado uma unica vez")
        t2 = json.dumps(novos["col"], ensure_ascii=False, indent=2)
        b2 = "\n".join("    " + l for l in t2.split("\n")[1:-1])
        novo = novo.replace(ancora_col, ancora_col + b2 + ",\n")
    d = json.loads(novo)
    for k in antes:
        if k != "coll":
            assert d[k] == antes[k], f"{loc}: o grupo {k} mudou"
    for k in antes["coll"]:
        if k == "col":
            for c in antes["coll"]["col"]:
                assert d["coll"]["col"][c] == antes["coll"]["col"][c], f"{loc}: coll.col.{c} mudou"
        else:
            assert d["coll"][k] == antes["coll"][k], f"{loc}: coll.{k} mudou"
    assert set(d["coll"]) == set(antes["coll"]) | {"det"}
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}

    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "coll.mute.title" not in portal:
        print("[ABORT] falta o lote 2b (COLL_I18N_MUTE_2026-09-16_apply.py). Corre-o primeiro."); return 1

    out = {"portal": _apply(portal, EDITS, "portal"),
           "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}

    locais = {}
    for loc, rel in LOCALES.items():
        caminho = base / rel
        novo = _fundir(caminho.read_bytes().decode("utf-8"), GRUPOS[loc], loc)
        locais[loc] = (caminho, novo)
        print(f"[ok] {loc}: coll.det com {len(GRUPOS[loc]['det'])} chaves, +{len(GRUPOS[loc].get('col', {}))} em coll.col")

    compile(TEST_SRC, str(REL["test"]), "exec")
    print(f"[ok] portal {len(EDITS)} blocos; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0

    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    for loc, (caminho, novo) in locais.items():
        caminho.write_bytes(novo.encode("utf-8")); print(f"[write] {LOCALES[loc]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_coll_i18n_detalhe_20260916.py "
          "tests/unit/test_coll_i18n_mute_20260916.py tests/unit/test_coll_i18n_barra_20260916.py "
          "tests/unit/test_coll_i18n_modal_20260916.py -q --no-cov")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
