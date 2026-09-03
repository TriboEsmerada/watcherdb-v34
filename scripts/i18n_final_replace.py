#!/usr/bin/env python3
"""
Replace remaining hardcoded Portuguese strings in watcherdb_portal.html with t() calls.
Run AFTER i18n_final_keys.py to ensure all keys exist in the JSONs.

Usage:
    python scripts/i18n_final_replace.py              # dry-run
    python scripts/i18n_final_replace.py --apply       # apply changes
"""
import os
import shutil
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
PORTAL = os.path.join(PROJECT_ROOT, 'templates', 'watcherdb_portal.html')

# Each replacement: (old_string, new_string)
# IMPORTANT: These are exact string matches. Order matters for overlapping strings.
REPLACEMENTS = [
    # =====================================================
    # HEADER / NAVIGATION
    # =====================================================
    (
        'placeholder="Buscar servidor (nome, descri\u00e7\u00e3o ou ambiente)..."',
        'placeholder="${t(\'header.search_placeholder\')}"'
    ),
    (
        'title="Testar conectividade do servidor selecionado (Ping)"',
        'title="${t(\'header.ping_title\')}"'
    ),
    (
        'title="Ir para KPIs"',
        'title="${t(\'header.kpi_dashboard_title\')}"'
    ),
    (
        'title="Configura\u00e7\u00f5es"',
        'title="${t(\'header.settings_title\')}"'
    ),

    # =====================================================
    # KPI HELP
    # =====================================================
    (
        '<p>Selecione um KPI no menu ao lado para ver a documentacao</p>',
        '<p>${t(\'kpi.help_select_kpi\')}</p>'
    ),

    # =====================================================
    # MEMORY 100% card help
    # =====================================================
    (
        'Ver <strong>100%</strong> neste card e <strong>esperado e saudavel</strong>! Significa que o SQL Server esta usando\n                        toda a memoria que foi configurada para ele. O SQL Server foi projetado para consumir e manter memoria em cache\n                        para melhor performance.',
        '${t(\'mem.help_100_desc\')}'
    ),
    (
        '<li>Se Max Server Memory nao estiver configurado (usando padrao de 2TB)</li>',
        '<li>${t(\'mem.help_max_not_configured\')}</li>'
    ),
    (
        '<li>Se houver Memory Pressure (SQL precisando de mais memoria do que tem)</li>',
        '<li>${t(\'mem.help_memory_pressure\')}</li>'
    ),
    (
        '<li>Se PAGEIOLATCH waits estiverem altos (indica falta de memoria para cache)</li>',
        '<li>${t(\'mem.help_pageiolatch\')}</li>'
    ),

    # =====================================================
    # SPACE MODULE - dropdown options
    # =====================================================
    (
        "'>Todas (' + availableDbs.length + ')</option>'",
        "'>' + t('space.all_dbs') + ' (' + availableDbs.length + ')</option>'"
    ),
    (
        "'>Todos (' + availableFgs.length + ')</option>'",
        "'>' + t('space.all_fgs') + ' (' + availableFgs.length + ')</option>'"
    ),

    # SPACE MODULE - card titles
    (
        'title="CR\u00cdTICO: FileGroups com menos de 2% livre - A\u00e7\u00e3o imediata necess\u00e1ria"',
        'title="${t(\'space.fg_critical_title\')}"'
    ),
    (
        'title="FileGroups com >= 2% e < 5% livre"',
        'title="${t(\'space.fg_warning_title\')}"'
    ),
    (
        'title="Disco Space Critical: discos com 5% ou menos livre"',
        'title="${t(\'space.disk_critical_title\')}"'
    ),
    (
        'title="Disco Space Warning: discos com 10% ou menos livre"',
        'title="${t(\'space.disk_warning_title\')}"'
    ),
    (
        'title="Discos com risco de overflow - MAXSIZE > espa\u00e7o em disco"',
        'title="${t(\'space.overflow_title\')}"'
    ),
    (
        'title="Carregar TODOS os FileGroups do servidor (consulta completa - pode demorar mais)"',
        'title="${t(\'space.load_all_fg_title\')}"'
    ),
    (
        'title="Ver detalhes e sess\u00f5es consumidoras do TempDB"',
        'title="${t(\'space.tempdb_details_title\')}"'
    ),
    (
        'title="Atualizar ${title}"',
        'title="${t(\'space.refresh_title\')} ${title}"'
    ),
    (
        'title="Clique para ver no m\u00f3dulo Space"',
        'title="${t(\'space.click_view_space\')}"'
    ),

    # =====================================================
    # OS MEMORY HELP (inside template literals)
    # =====================================================
    (
        '<p><strong>OS Memory</strong> mostra a memoria fisica total do servidor e como esta distribuida entre o SQL Server, outros processos, e o Windows.</p>',
        '<p>${t(\'mem.help_os_desc\')}</p>'
    ),
    (
        '<p><strong>Disponivel:</strong> Memoria que pode ser imediatamente alocada. Quando e 0 GB, o Windows esta a usar tudo como File Cache (Standby) - isto e normal e reclamavel.</p>',
        '<p>${t(\'mem.help_available_desc\')}</p>'
    ),
    (
        '<p><strong>OS/Cache (Standby):</strong> O Windows usa memoria livre como cache de disco. E reclamavel quando necessario. Nao e um problema.</p>',
        '<p>${t(\'mem.help_oscache_desc\')}</p>'
    ),
    (
        '<p><strong>CRITICO vs Normal:</strong> O status CRITICO aparece quando a memoria disponivel e &lt; 5% da RAM total. Se o OS/Cache for alto, pode nao ser um problema real.</p>',
        '<p>${t(\'mem.help_critical_desc\')}</p>'
    ),

    # SQL MEMORY HELP
    (
        '<p><strong>Buffer Pool:</strong> Memoria actualmente usada pelo SQL Server para cache de dados e indices.</p>',
        '<p>${t(\'mem.help_buffer_pool\')}</p>'
    ),
    (
        '<p><strong>Max Server Memory:</strong> Limite maximo configurado. O SQL Server nao usara mais do que este valor.</p>',
        '<p>${t(\'mem.help_max_server\')}</p>'
    ),

    # RESOURCE GOVERNOR HELP
    (
        '<p>O <em>Resource Governor</em> e uma funcionalidade do SQL Server que permite limitar e gerir a alocacao de CPU e memoria entre diferentes workloads.</p>',
        '<p>${t(\'mem.help_rg_desc\')}</p>'
    ),
    (
        '<p><strong>OOM (Out-of-Memory):</strong> Corresponde ao <strong>Event ID 701</strong>. Indica que queries falharam por falta de memoria no pool.</p>',
        '<p>${t(\'mem.help_oom_desc\')}</p>'
    ),

    # =====================================================
    # MEMORY PRESSURE EXPLANATIONS
    # =====================================================
    (
        '<p><strong>O que significa "N/A - N\u00c3O CONFIGURADO"?</strong></p>',
        '<p><strong>${t(\'mem.pressure_na_title\')}</strong></p>'
    ),
    (
        '<p>O SQL Server ainda n\u00e3o alocou mem\u00f3ria suficiente para calcular o Memory Pressure. Isso pode acontecer em alguns cen\u00e1rios:</p>',
        '<p>${t(\'mem.pressure_na_desc\')}</p>'
    ),
    (
        '<li><strong>Inst\u00e2ncia rec\u00e9m-iniciada:</strong> O SQL Server est\u00e1 em processo de "warm-up" e ainda n\u00e3o carregou dados no Buffer Pool</li>',
        '<li>${t(\'mem.pressure_na_fresh\')}</li>'
    ),
    (
        '<li><strong>Pouca atividade:</strong> N\u00e3o h\u00e1 queries ativas que forcem o SQL Server a alocar mem\u00f3ria</li>',
        '<li>${t(\'mem.pressure_na_low_activity\')}</li>'
    ),
    (
        '<li><strong>Target Server Memory = 0:</strong> O contador de performance "Target Server Memory (KB)" ainda n\u00e3o foi calculado</li>',
        '<li>${t(\'mem.pressure_na_target_zero\')}</li>'
    ),
    (
        '<li><strong>Coleta de dados pendente:</strong> Os dados podem ainda n\u00e3o ter sido coletados pelo sistema de monitoramento</li>',
        '<li>${t(\'mem.pressure_na_pending\')}</li>'
    ),
    (
        '<li>Execute algumas queries no servidor para for\u00e7ar aloca\u00e7\u00e3o de mem\u00f3ria</li>',
        '<li>${t(\'mem.pressure_na_action_queries\')}</li>'
    ),
    (
        '<li>Verifique se o SQL Server est\u00e1 online e funcionando</li>',
        '<li>${t(\'mem.pressure_na_action_check\')}</li>'
    ),
    (
        '<p><strong>Excelente! Memory Pressure est\u00e1 SAUD\u00c1VEL</strong></p>',
        '<p><strong>${t(\'mem.pressure_healthy_title\')}</strong></p>'
    ),
    (
        'da mem\u00f3ria alocada (Target Server Memory).',
        '${t(\'mem.pressure_efficiency\')}.'
    ),
    (
        '<li>O Buffer Pool est\u00e1 bem utilizado</li>',
        '<li>${t(\'mem.pressure_healthy_buffer\')}</li>'
    ),
    (
        '<li>Os dados est\u00e3o sendo cacheados eficientemente</li>',
        '<li>${t(\'mem.pressure_healthy_cache\')}</li>'
    ),
    (
        '<li>N\u00e3o h\u00e1 desperd\u00edcio de mem\u00f3ria alocada</li>',
        '<li>${t(\'mem.pressure_healthy_nowaste\')}</li>'
    ),
    (
        '<p><strong>Nenhuma a\u00e7\u00e3o necess\u00e1ria</strong></p>',
        '<p>${t(\'mem.pressure_healthy_action\')}</p>'
    ),
    (
        '<p>Continue monitorando para garantir que o valor permane\u00e7a acima de 95%.</p>',
        '<p>${t(\'mem.pressure_healthy_monitor\')}</p>'
    ),
    (
        '<p>O SQL Server est\u00e1 usando menos mem\u00f3ria do que poderia. Isso pode indicar:</p>',
        '<p>${t(\'mem.pressure_warning_desc\')}</p>'
    ),
    (
        '<li>SQL Server ainda n\u00e3o "aqueceu" completamente</li>',
        '<li>${t(\'mem.pressure_warning_warmup\')}</li>'
    ),
    (
        '<li>Poss\u00edvel problema de aloca\u00e7\u00e3o de mem\u00f3ria</li>',
        '<li>${t(\'mem.pressure_warning_alloc\')}</li>'
    ),
    (
        '<p><strong>Recomenda\u00e7\u00f5es:</strong></p>',
        '<p>${t(\'mem.pressure_warning_recs\')}</p>'
    ),
    (
        '<li>Verifique se h\u00e1 queries lentas que poderiam se beneficiar de mais cache</li>',
        '<li>${t(\'mem.pressure_warning_slow\')}</li>'
    ),
    (
        '<li>Considere revisar a configura\u00e7\u00e3o de Max Server Memory</li>',
        '<li>${t(\'mem.pressure_warning_maxmem\')}</li>'
    ),
    (
        '<p>O SQL Server est\u00e1 usando significativamente menos mem\u00f3ria do que alocou. Isso pode indicar problemas s\u00e9rios:</p>',
        '<p>${t(\'mem.pressure_critical_desc\')}</p>'
    ),
    (
        '<li>Press\u00e3o externa de mem\u00f3ria do Windows</li>',
        '<li>${t(\'mem.pressure_critical_external\')}</li>'
    ),
    (
        '<li>Configura\u00e7\u00e3o incorreta de mem\u00f3ria</li>',
        '<li>${t(\'mem.pressure_critical_config\')}</li>'
    ),
    (
        '<li>Problema de performance que impede aloca\u00e7\u00e3o</li>',
        '<li>${t(\'mem.pressure_critical_perf\')}</li>'
    ),
    (
        '<p><strong>A\u00e7\u00f5es urgentes:</strong></p>',
        '<p>${t(\'mem.pressure_critical_actions\')}</p>'
    ),
    (
        '<li>Verifique o consumo de mem\u00f3ria do Windows (Available MB)</li>',
        '<li>${t(\'mem.pressure_critical_check_win\')}</li>'
    ),
    (
        '<li>Identifique processos que competem por mem\u00f3ria</li>',
        '<li>${t(\'mem.pressure_critical_identify\')}</li>'
    ),
    (
        '<li>Considere aumentar Max Server Memory se houver RAM dispon\u00edvel</li>',
        '<li>${t(\'mem.pressure_critical_increase\')}</li>'
    ),
    (
        '>efici\u00eancia do uso de mem\u00f3ria',
        '>${t(\'mem.pressure_efficiency\')}'
    ),
    (
        '>F\u00f3rmula:</strong>',
        '>${t(\'mem.pressure_formula\')}:</strong>'
    ),
    (
        'Quanto mais pr\u00f3ximo de 100%, melhor!',
        '${t(\'mem.pressure_closer_100\')}'
    ),

    # =====================================================
    # BACKUP MODULE
    # =====================================================
    (
        '>\u00daltimo FULL</th>',
        '>${t(\'backup.last_full\')}</th>'
    ),
    (
        '>\u00daltimo DIFF</th>',
        '>${t(\'backup.last_diff\')}</th>'
    ),
    (
        '>\u00daltimo LOG</th>',
        '>${t(\'backup.last_log\')}</th>'
    ),
    (
        '>Padr\u00e3o</th>',
        '>${t(\'backup.pattern\')}</th>'
    ),
    (
        '>SEM Justificativa</div>',
        '>${t(\'backup.no_justification\')}</div>'
    ),
    (
        '>Gap M\u00e9dio (h)</div>',
        '>${t(\'backup.avg_gap_h\')}</div>'
    ),
    # Backup filter options (inside template literals with backticks)
    (
        '<option value="all">Todos</option>\n                          <option value="full">Sem FULL</option>\n                          <option value="log">Sem LOG</option>',
        '<option value="all">${t(\'backup.filter_all\')}</option>\n                          <option value="full">${t(\'backup.filter_no_full\')}</option>\n                          <option value="log">${t(\'backup.filter_no_log\')}</option>'
    ),
    # Backup gaps type filter
    (
        '<option value="all">Todos</option>\n                          <option value="full">FULL</option>\n                          <option value="diff">DIFF</option>\n                          <option value="log">LOG</option>',
        '<option value="all">${t(\'backup.filter_all\')}</option>\n                          <option value="full">FULL</option>\n                          <option value="diff">DIFF</option>\n                          <option value="log">LOG</option>'
    ),
    # Backup severity "Todos"
    (
        '<option value="all">Todos</option>\n                          <option value="CRITICAL">Critical</option>',
        '<option value="all">${t(\'backup.filter_all\')}</option>\n                          <option value="CRITICAL">Critical</option>'
    ),
    # Backup "Todas" (severidade)
    (
        '<option value="all">Todas</option>\n                                    <option value="CRITICAL">CRITICAL</option>\n                                    <option value="HIGH">HIGH</option>\n                                    <option value="MEDIUM">MEDIUM</option>\n                                    <option value="LOW">LOW</option>\n                                    <option value="INFO">INFO</option>',
        '<option value="all">${t(\'backup.all_severities\')}</option>\n                                    <option value="CRITICAL">CRITICAL</option>\n                                    <option value="HIGH">HIGH</option>\n                                    <option value="MEDIUM">MEDIUM</option>\n                                    <option value="LOW">LOW</option>\n                                    <option value="INFO">INFO</option>'
    ),
    (
        '<option value="all">Todas</option>\n                                    <option value="CRITICAL">CRITICAL</option>\n                                    <option value="HIGH">HIGH</option>\n                                    <option value="MEDIUM">MEDIUM</option>\n                                    <option value="LOW">LOW</option>\n                                </select>',
        '<option value="all">${t(\'backup.all_severities\')}</option>\n                                    <option value="CRITICAL">CRITICAL</option>\n                                    <option value="HIGH">HIGH</option>\n                                    <option value="MEDIUM">MEDIUM</option>\n                                    <option value="LOW">LOW</option>\n                                </select>'
    ),
    # Last 14/21/30 days options
    (
        '>\u00daltimos 14 dias</option>',
        '>${t(\'backup.last_14_days\')}</option>'
    ),
    (
        '>\u00daltimos 21 dias</option>',
        '>${t(\'backup.last_21_days\')}</option>'
    ),
    (
        '>\u00daltimos 30 dias</option>',
        '>${t(\'backup.last_30_days\')}</option>'
    ),
    # No records found
    (
        '<p>Nenhum registro encontrado com os filtros aplicados.</p>',
        '<p>${t(\'backup.no_records_found\')}</p>'
    ),

    # =====================================================
    # LOG MODULE - Tipo filter
    # =====================================================
    (
        '<option value="all">Todos</option>\n                                <option value="windows">Apenas Windows</option>\n                                <option value="sql">Apenas SQL Server</option>',
        '<option value="all">${t(\'log.type_all\')}</option>\n                                <option value="windows">Windows</option>\n                                <option value="sql">SQL Server</option>'
    ),
    # No logs found
    (
        '<h4 style="color: #e2e8f0; margin-bottom: 8px;">Nenhum log encontrado</h4>',
        '<h4 style="color: #e2e8f0; margin-bottom: 8px;">${t(\'log.no_logs_title\')}</h4>'
    ),
    (
        '<p>Nao foram encontrados logs nas ultimas 24 horas para este servico.</p>',
        '<p>${t(\'log.no_logs_24h\')}</p>'
    ),
    (
        'title="Clique para ver a mensagem completa"',
        'title="${t(\'log.click_full_message\')}"'
    ),

    # =====================================================
    # ALWAYSON MODULE
    # =====================================================
    (
        '<strong>O AG est\u00e1 com status NOT_HEALTHY</strong>, mas n\u00e3o houve eventos de failover nos \u00faltimos 30 dias.',
        '${t(\'alwayson.ag_not_healthy_msg\')}'
    ),
    (
        'Isso indica um problema recente (r\u00e9plica offline, conectividade, sincroniza\u00e7\u00e3o pendente) que ainda n\u00e3o gerou failover.',
        '${t(\'alwayson.ag_not_healthy_hint\')}'
    ),
    (
        '<span>Executando diagn\u00f3stico... Analisando endpoint, r\u00e9plicas e logs...</span>',
        '<span>${t(\'alwayson.running_diagnosis\')}</span>'
    ),
    (
        '<strong>Erro ao executar diagn\u00f3stico:</strong>',
        '<strong>${t(\'alwayson.diagnosis_error\')}</strong>'
    ),
    (
        '<strong>A\u00e7\u00f5es recomendadas:</strong>',
        '<strong>${t(\'alwayson.actions_recommended\')}</strong>'
    ),
    (
        '<strong>N\u00e3o foi poss\u00edvel realizar o diagn\u00f3stico:</strong>',
        '<strong>${t(\'alwayson.diagnosis_failed\')}</strong>'
    ),
    (
        '<strong>N\u00e3o foi poss\u00edvel realizar a an\u00e1lise:</strong>',
        '<strong>${t(\'alwayson.analysis_failed\')}</strong>'
    ),
    (
        '<li>O servidor est\u00e1 sobrecarregado</li>',
        '<li>${t(\'alwayson.server_overloaded\')}</li>'
    ),
    (
        '<li>A rede est\u00e1 lenta ou inst\u00e1vel</li>',
        '<li>${t(\'alwayson.network_slow\')}</li>'
    ),
    (
        '<li>O servidor est\u00e1 processando muitas consultas</li>',
        '<li>${t(\'alwayson.too_many_queries\')}</li>'
    ),
    (
        '<strong>Detalhes:</strong>',
        '<strong>${t(\'alwayson.details_label\')}</strong>'
    ),
    (
        '<strong>Servidor:</strong> ${serverNameForApi}',
        '<strong>${t(\'alwayson.server_label\')}</strong> ${serverNameForApi}'
    ),
    (
        '<strong>Erro:</strong> ${serverStatus.error}',
        '<strong>${t(\'alwayson.error_label\')}</strong> ${serverStatus.error}'
    ),
    (
        'title="Buscar dados completos do n\u00f3 prim\u00e1rio"',
        'title="${t(\'alwayson.fetch_primary_title\')}"'
    ),
    (
        '<strong>Sincroniza\u00e7\u00e3o:</strong>',
        '<strong>${t(\'alwayson.sync_label\')}</strong>'
    ),
    (
        '<strong>R\u00e9plicas:</strong> ${replicasCount}',
        '<strong>${t(\'alwayson.replicas_label_inline\')}</strong> ${replicasCount}'
    ),
    # Table headers
    (
        '<th>Servidor</th>\n                                                <th>Role</th>\n                                                <th>Operacional</th>\n                                                <th>Conex\u00e3o</th>',
        '<th>${t(\'alwayson.th_server\')}</th>\n                                                <th>Role</th>\n                                                <th>Operacional</th>\n                                                <th>${t(\'alwayson.th_connection\')}</th>'
    ),
    (
        '<th>Prim\u00e1ria</th>',
        '<th>${t(\'alwayson.th_primary\')}</th>'
    ),
    # Failover table headers (second block)
    (
        '<th>Tipo</th>\n                                                <th>Severidade</th>\n                                                <th>Descri\u00e7\u00e3o</th>',
        '<th>${t(\'alwayson.failover_type\')}</th>\n                                                <th>${t(\'alwayson.failover_severity\')}</th>\n                                                <th>${t(\'alwayson.th_description\')}</th>'
    ),
    # AG overview table
    (
        '<th>Servidor</th>\n                                        <th>Status</th>\n                                        <th>R\u00e9plicas</th>',
        '<th>${t(\'alwayson.th_server\')}</th>\n                                        <th>Status</th>\n                                        <th>${t(\'alwayson.replicas_label_inline\')}</th>'
    ),

    # =====================================================
    # PREDICTIVE ANALYSIS
    # =====================================================
    (
        'title="Gerar an\u00e1lise preditiva completa"',
        'title="${t(\'predict.generate_title\')}"'
    ),
    (
        '<strong>7 dias de hist\u00f3rico</strong>',
        '<strong>${t(\'predict.min_7_days\')}</strong>'
    ),
    (
        '<li>Coleta de dados n\u00e3o est\u00e1 ativa para este servidor</li>',
        '<li>${t(\'predict.no_data_msg\')}</li>'
    ),
    (
        '<li>Servidor n\u00e3o est\u00e1 sendo monitorado</li>',
        '<li>${t(\'predict.not_monitored\')}</li>'
    ),
    (
        '<li>Verificar se a coleta de dados est\u00e1 ativa</li>',
        '<li>${t(\'predict.check_collection\')}</li>'
    ),
    (
        '<li>Aguardar acumular pelo menos 7 dias de hist\u00f3rico</li>',
        '<li>${t(\'predict.wait_7_days\')}</li>'
    ),
    (
        '<li>Tentar com outro filegroup que tenha mais dados</li>',
        '<li>${t(\'predict.try_another_fg\')}</li>'
    ),
    (
        '<li>Se n\u00e3o existir, adicione o script ou desabilite a funcionalidade de an\u00e1lise preditiva</li>',
        '<li>${t(\'predict.script_not_found\')}</li>'
    ),
    (
        '<li>Use a an\u00e1lise de espa\u00e7o atual para monitoramento imediato</li>',
        '<li>${t(\'predict.use_space_analysis\')}</li>'
    ),
    (
        'title="Atualizar An\u00e1lise Preditiva"',
        'title="${t(\'predict.refresh_title\')}"'
    ),
    # Predictive alert card titles (ternary inside template literals)
    (
        "title=\"${data.alerts_by_severity.critical.length > 0 ? 'Clique para ver alertas cr\u00edticos' : 'Nenhum alerta cr\u00edtico'}\"",
        "title=\"${data.alerts_by_severity.critical.length > 0 ? t('predict.click_critical') : t('predict.no_critical')}\""
    ),
    (
        "title=\"${data.alerts_by_severity.high.length > 0 ? 'Clique para ver alertas de risco alto' : 'Nenhum alerta de risco alto'}\"",
        "title=\"${data.alerts_by_severity.high.length > 0 ? t('predict.click_high') : t('predict.no_high')}\""
    ),
    (
        "title=\"${data.alerts_by_severity.medium.length > 0 ? 'Clique para ver alertas de risco m\u00e9dio' : 'Nenhum alerta de risco m\u00e9dio'}\"",
        "title=\"${data.alerts_by_severity.medium.length > 0 ? t('predict.click_medium') : t('predict.no_medium')}\""
    ),
    (
        'title="Clique para ver todos os filegroups analisados"',
        'title="${t(\'predict.click_all_fg\')}"'
    ),
    (
        '<th>Recomenda\u00e7\u00e3o</th>',
        '<th>${t(\'predict.recommendation\')}</th>'
    ),

    # =====================================================
    # POSSIBLE CAUSES (services, predictive)
    # =====================================================
    (
        'Poss\u00edveis causas:</strong>',
        '${t(\'predict.possible_causes\')}</strong>'
    ),
    (
        'Scripts Python n\u00e3o encontrados na raiz do projeto',
        '${t(\'predict.scripts_not_found\')}'
    ),
    (
        'Timeout na extra\u00e7\u00e3o de dados (Oracle lento)',
        '${t(\'predict.oracle_timeout\')}'
    ),

    # =====================================================
    # KPI DASHBOARD
    # =====================================================
    (
        'title="Atualizar este card"',
        'title="${t(\'kpi.refresh_card_title\')}"'
    ),

    # =====================================================
    # TEMPDB / SQL DIAGNOSTICS
    # =====================================================
    (
        'title="Clique para abrir TempDB no SQL Diagnostics"',
        'title="${t(\'tempdb.open_diag_title\')}"'
    ),
    (
        'title="Clique para ver mais detalhes"',
        'title="${t(\'tempdb.click_details\')}"'
    ),
    (
        'title="Clique para filtrar sess\u00f5es com idle =30 min"',
        'title="${t(\'tempdb.filter_idle_title\')}"'
    ),
    (
        'title="Clique para ordenar"',
        'title="${t(\'tempdb.click_sort\')}"'
    ),
    (
        'title="Clique para ver a query completa"',
        'title="${t(\'tempdb.click_full_query\')}"'
    ),
    (
        'title="Clique para ver o plano de execu\u00e7\u00e3o"',
        'title="${t(\'tempdb.click_exec_plan\')}"'
    ),
    (
        'title="Analisar padr\u00f5es e correlacionar com diagn\u00f3sticos"',
        'title="${t(\'tempdb.analyze_patterns\')}"'
    ),

    # =====================================================
    # SQL STATS / INDEX ANALYSIS
    # =====================================================
    (
        'title="HEAP: Tabela sem \u00edndice clustered. Dados armazenados sem ordem, o que pode impactar performance em buscas. Considere criar um \u00edndice clustered na chave prim\u00e1ria ou coluna mais consultada."',
        'title="${t(\'stats.heap_tooltip\')}"'
    ),
    (
        '<strong>\u00edndices j\u00e1 existentes</strong>',
        '<strong>${t(\'stats.existing_indexes\')}</strong>'
    ),
    (
        '<strong>Fatores de decis\u00e3o:</strong>',
        '<strong>${t(\'stats.decision_factors\')}</strong>'
    ),
    (
        '<th>\u00cdndice/Stats</th>\n                                            <th>\u00daltima Atualiza\u00e7\u00e3o</th>\n                                            <th>Dias</th>\n                                        <th>Modifica\u00e7\u00f5es</th>\n                                        <th>Recomenda\u00e7\u00e3o</th>',
        '<th>${t(\'stats.th_index_stats\')}</th>\n                                            <th>${t(\'stats.th_last_update\')}</th>\n                                            <th>Dias</th>\n                                        <th>${t(\'stats.th_modifications\')}</th>\n                                        <th>${t(\'stats.th_recommendation\')}</th>'
    ),
    (
        'title="Expandir para ver tabelas base da VIEW"',
        'title="${t(\'stats.expand_view_title\')}"'
    ),
    (
        '<li>Identificando tabelas e VIEWs que comp\u00f5em esta VIEW</li>',
        '<li>${t(\'stats.identifying_tables\')}</li>'
    ),
    (
        '<li>Analisando estat\u00edsticas de cada tabela base</li>',
        '<li>${t(\'stats.analyzing_stats\')}</li>'
    ),
    (
        '<li>Verificando \u00edndices faltantes sugeridos pelo SQL Server</li>',
        '<li>${t(\'stats.checking_missing\')}</li>'
    ),
    # Duplicate table headers for VIEWs
    (
        '<th>\u00cdndice/Stats</th>\n                                        <th>\u00daltima Atualiza\u00e7\u00e3o</th>\n                                        <th>Dias</th>\n                                        <th>Recomenda\u00e7\u00e3o</th>',
        '<th>${t(\'stats.th_index_stats\')}</th>\n                                        <th>${t(\'stats.th_last_update\')}</th>\n                                        <th>Dias</th>\n                                        <th>${t(\'stats.th_recommendation\')}</th>'
    ),

    # =====================================================
    # SETTINGS
    # =====================================================
    (
        '<span>Incluir bases de sistema por padr\u00e3o</span>',
        '<span>${t(\'settings.include_system_dbs\')}</span>'
    ),
    (
        '>Por frequ\u00eancia de uso</option>',
        '>${t(\'settings.sort_frequency\')}</option>'
    ),
    (
        '>Alfab\u00e9tica (A-Z)</option>',
        '>${t(\'settings.sort_alpha\')}</option>'
    ),
    (
        '>Por ambiente (PRD, DEV, QLT)</option>',
        '>${t(\'settings.sort_environment\')}</option>'
    ),
    (
        '<span>Sidebar recolhida por padr\u00e3o</span>',
        '<span>${t(\'settings.sidebar_collapsed\')}</span>'
    ),
    (
        '>Por categoria/t\u00f3pico</option>',
        '>${t(\'settings.sort_category\')}</option>'
    ),
    (
        '>Personalizada (arraste para reorganizar)</option>',
        '>${t(\'settings.sort_custom\')}</option>'
    ),

    # =====================================================
    # SQL QUERIES MODULE
    # =====================================================
    (
        'placeholder="Descri\u00e7\u00e3o da query"',
        'placeholder="${t(\'sqlquery.desc_placeholder\')}"'
    ),
    (
        '<title>Diagn\u00f3stico de Query - WatcherDB</title>',
        '<title>${t(\'sqlquery.diag_title\')}</title>'
    ),
    (
        '<h1>Diagn\u00f3stico de Query Lenta</h1>',
        '<h1>${t(\'sqlquery.diag_slow_title\')}</h1>'
    ),
    (
        '<strong>Inst\u00e2ncia:</strong>',
        '<strong>${t(\'sqlquery.instance_label\')}</strong>'
    ),

    # =====================================================
    # COPILOT / INTELLIGENCE DASHBOARD
    # =====================================================
    (
        '<span>Carregando scores de manutencao preditiva...</span>',
        '<span>${t(\'copilot.loading_scores\')}</span>'
    ),
    (
        '<strong>Instancia Mais Afetada</strong>',
        '<strong>${t(\'copilot.most_affected\')}</strong>'
    ),
    (
        '<span>Nenhum alerta urgente no momento</span>',
        '<span>${t(\'copilot.no_urgent_alerts\')}</span>'
    ),
    (
        '<p>Nenhum evento no periodo</p>',
        '<p>${t(\'copilot.no_events\')}</p>'
    ),
    (
        '<span>Carregando insights...</span>',
        '<span>${t(\'copilot.loading_insights\')}</span>'
    ),
    (
        '<p>Nenhum insight disponivel</p>',
        '<p>${t(\'copilot.no_insights\')}</p>'
    ),
    (
        '<span>Gerando relatorio...</span>',
        '<span>${t(\'copilot.generating_report\')}</span>'
    ),

    # =====================================================
    # SECURITY - config health
    # =====================================================
    (
        "A configuracao esta <strong>saudavel</strong>. Todos os indicadores estao dentro dos limites recomendados. Nenhuma acao necessaria.",
        "A configuracao esta <strong>${t('security.config_healthy')}</strong>. Todos os indicadores estao dentro dos limites recomendados. Nenhuma acao necessaria."
    ),

    # =====================================================
    # REPORTS
    # =====================================================
    (
        '<tr><th>Job</th><th>Tipo</th><th>Ultimo Status</th><th>Ultima Exec.</th><th>Prox. Exec.</th><th>Ativo</th></tr>',
        '<tr><th>Job</th><th>Tipo</th><th>${t(\'report.last_status\')}</th><th>Ultima Exec.</th><th>Prox. Exec.</th><th>Ativo</th></tr>'
    ),
]


def main():
    apply = '--apply' in sys.argv

    print('=' * 60)
    print('i18n Final Replace - Hardcoded String Replacer')
    print('=' * 60)

    if not os.path.exists(PORTAL):
        print(f'ERROR: Portal file not found: {PORTAL}')
        return 1

    with open(PORTAL, 'r', encoding='utf-8') as f:
        content = f.read()

    total_replaced = 0
    failed = []

    for old, new in REPLACEMENTS:
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            total_replaced += count
            display = old[:70].replace('\n', ' ')
            print(f'  [{count}x] {display}...')
        else:
            failed.append(old[:80].replace('\n', ' '))

    print(f'\n  Total: {total_replaced} replacements across {len(REPLACEMENTS)} patterns')
    if failed:
        print(f'  Not found ({len(failed)}):')
        for f_str in failed[:20]:
            print(f'    - {f_str}')
        if len(failed) > 20:
            print(f'    ... and {len(failed) - 20} more')

    if apply:
        # Backup
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = PORTAL + f'.bak_i18n_final_{ts}'
        shutil.copy2(PORTAL, backup)
        print(f'\n  Backup: {os.path.basename(backup)}')

        # Write
        with open(PORTAL, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  Applied {total_replaced} replacements to portal HTML')
    else:
        print('\n  DRY RUN -- no changes. Run with --apply to apply.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
