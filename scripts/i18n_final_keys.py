#!/usr/bin/env python3
"""
Add all remaining i18n keys to pt.json, en.json, es.json.
Run BEFORE i18n_final_replace.py.

Usage:
    python scripts/i18n_final_keys.py
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
I18N_DIR = os.path.join(PROJECT_ROOT, 'static', 'i18n')

# All new keys needed for the 185 remaining hardcoded strings
# Format: { key: { pt: ..., en: ..., es: ... } }
NEW_KEYS = {
    # =====================================================
    # HEADER / NAVIGATION
    # =====================================================
    "header.search_placeholder": {
        "pt": "Buscar servidor (nome, descricao ou ambiente)...",
        "en": "Search server (name, description or environment)...",
        "es": "Buscar servidor (nombre, descripcion o entorno)..."
    },
    "header.ping_title": {
        "pt": "Testar conectividade do servidor selecionado (Ping)",
        "en": "Test selected server connectivity (Ping)",
        "es": "Probar conectividad del servidor seleccionado (Ping)"
    },
    "header.kpi_dashboard_title": {
        "pt": "Ir para KPIs",
        "en": "Go to KPIs",
        "es": "Ir al KPIs"
    },
    "header.settings_title": {
        "pt": "Configuracoes",
        "en": "Settings",
        "es": "Configuraciones"
    },
    "header.kpi_dashboard_btn": {
        "pt": "KPIs",
        "en": "KPIs",
        "es": "KPIs"
    },

    # =====================================================
    # KPI HELP
    # =====================================================
    "kpi.help_select_kpi": {
        "pt": "Selecione um KPI no menu ao lado para ver a documentacao",
        "en": "Select a KPI from the menu to view documentation",
        "es": "Seleccione un KPI del menu para ver la documentacion"
    },

    # =====================================================
    # MEMORY HELP (100% card explanation)
    # =====================================================
    "mem.help_100_title": {
        "pt": "100% e Normal!",
        "en": "100% is Normal!",
        "es": "100% es Normal!"
    },
    "mem.help_100_desc": {
        "pt": "Ver <strong>100%</strong> neste card e <strong>esperado e saudavel</strong>! Significa que o SQL Server esta usando toda a memoria que foi configurada para ele. O SQL Server foi projetado para consumir e manter memoria em cache para melhor performance.",
        "en": "Seeing <strong>100%</strong> on this card is <strong>expected and healthy</strong>! It means SQL Server is using all the memory configured for it. SQL Server is designed to consume and keep memory in cache for better performance.",
        "es": "Ver <strong>100%</strong> en esta tarjeta es <strong>esperado y saludable</strong>! Significa que SQL Server esta usando toda la memoria configurada. SQL Server esta disenado para consumir y mantener memoria en cache para mejor rendimiento."
    },
    "mem.help_when_worry_title": {
        "pt": "Quando se Preocupar?",
        "en": "When to Worry?",
        "es": "Cuando Preocuparse?"
    },
    "mem.help_max_not_configured": {
        "pt": "Se Max Server Memory nao estiver configurado (usando padrao de 2TB)",
        "en": "If Max Server Memory is not configured (using default 2TB)",
        "es": "Si Max Server Memory no esta configurado (usando defecto de 2TB)"
    },
    "mem.help_memory_pressure": {
        "pt": "Se houver Memory Pressure (SQL precisando de mais memoria do que tem)",
        "en": "If there is Memory Pressure (SQL needing more memory than available)",
        "es": "Si hay Memory Pressure (SQL necesitando mas memoria de la disponible)"
    },
    "mem.help_pageiolatch": {
        "pt": "Se PAGEIOLATCH waits estiverem altos (indica falta de memoria para cache)",
        "en": "If PAGEIOLATCH waits are high (indicates insufficient memory for cache)",
        "es": "Si PAGEIOLATCH waits estan altos (indica falta de memoria para cache)"
    },

    # =====================================================
    # SQL ANALYSIS (TODAS option)
    # =====================================================
    "sql.all_option": {
        "pt": "TODAS",
        "en": "ALL",
        "es": "TODAS"
    },
    "sql.full_db_analysis_desc": {
        "pt": "Esta opcao analisa <strong>TODAS</strong> as tabelas do banco selecionado, identificando estatisticas desatualizadas e tabelas HEAP. Ideal para manutencao preventiva e diagnostico geral de performance.",
        "en": "This option analyzes <strong>ALL</strong> tables in the selected database, identifying outdated statistics and HEAP tables. Ideal for preventive maintenance and general performance diagnosis.",
        "es": "Esta opcion analiza <strong>TODAS</strong> las tablas de la base seleccionada, identificando estadisticas desactualizadas y tablas HEAP. Ideal para mantenimiento preventivo y diagnostico general de rendimiento."
    },

    # =====================================================
    # SPACE MODULE (dropdowns, titles)
    # =====================================================
    "space.all_dbs": {
        "pt": "Todas",
        "en": "All",
        "es": "Todas"
    },
    "space.all_fgs": {
        "pt": "Todos",
        "en": "All",
        "es": "Todos"
    },
    "space.fg_critical_title": {
        "pt": "CRITICO: FileGroups com menos de 2% livre - Acao imediata necessaria",
        "en": "CRITICAL: FileGroups with less than 2% free - Immediate action required",
        "es": "CRITICO: FileGroups con menos de 2% libre - Accion inmediata necesaria"
    },
    "space.fg_warning_title": {
        "pt": "FileGroups com >= 2% e < 5% livre",
        "en": "FileGroups with >= 2% and < 5% free",
        "es": "FileGroups con >= 2% y < 5% libre"
    },
    "space.disk_critical_title": {
        "pt": "Disco Space Critical: discos com 5% ou menos livre",
        "en": "Disk Space Critical: disks with 5% or less free",
        "es": "Disco Space Critical: discos con 5% o menos libre"
    },
    "space.disk_warning_title": {
        "pt": "Disco Space Warning: discos com 10% ou menos livre",
        "en": "Disk Space Warning: disks with 10% or less free",
        "es": "Disco Space Warning: discos con 10% o menos libre"
    },
    "space.overflow_title": {
        "pt": "Discos com risco de overflow - MAXSIZE > espaco em disco",
        "en": "Disks with overflow risk - MAXSIZE > available disk space",
        "es": "Discos con riesgo de overflow - MAXSIZE > espacio en disco"
    },
    "space.load_all_fg_title": {
        "pt": "Carregar TODOS os FileGroups do servidor (consulta completa - pode demorar mais)",
        "en": "Load ALL server FileGroups (full query - may take longer)",
        "es": "Cargar TODOS los FileGroups del servidor (consulta completa - puede demorar mas)"
    },
    "space.tempdb_details_title": {
        "pt": "Ver detalhes e sessoes consumidoras do TempDB",
        "en": "View TempDB details and consuming sessions",
        "es": "Ver detalles y sesiones consumidoras del TempDB"
    },
    "space.refresh_title": {
        "pt": "Atualizar",
        "en": "Refresh",
        "es": "Actualizar"
    },
    "space.click_view_space": {
        "pt": "Clique para ver no modulo Space",
        "en": "Click to view in Space module",
        "es": "Clic para ver en el modulo Space"
    },

    # =====================================================
    # OS MEMORY HELP
    # =====================================================
    "mem.help_os_desc": {
        "pt": "<strong>OS Memory</strong> mostra a memoria fisica total do servidor e como esta distribuida entre o SQL Server, outros processos, e o Windows.",
        "en": "<strong>OS Memory</strong> shows the server's total physical memory and how it is distributed between SQL Server, other processes, and Windows.",
        "es": "<strong>OS Memory</strong> muestra la memoria fisica total del servidor y como esta distribuida entre SQL Server, otros procesos y Windows."
    },
    "mem.help_available_desc": {
        "pt": "<strong>Disponivel:</strong> Memoria que pode ser imediatamente alocada. Quando e 0 GB, o Windows esta a usar tudo como File Cache (Standby) - isto e normal e reclamavel.",
        "en": "<strong>Available:</strong> Memory that can be immediately allocated. When it's 0 GB, Windows is using it all as File Cache (Standby) - this is normal and reclaimable.",
        "es": "<strong>Disponible:</strong> Memoria que puede ser inmediatamente asignada. Cuando es 0 GB, Windows esta usando todo como File Cache (Standby) - esto es normal y reclamable."
    },
    "mem.help_oscache_desc": {
        "pt": "<strong>OS/Cache (Standby):</strong> O Windows usa memoria livre como cache de disco. E reclamavel quando necessario. Nao e um problema.",
        "en": "<strong>OS/Cache (Standby):</strong> Windows uses free memory as disk cache. It is reclaimable when needed. Not a problem.",
        "es": "<strong>OS/Cache (Standby):</strong> Windows usa memoria libre como cache de disco. Es reclamable cuando sea necesario. No es un problema."
    },
    "mem.help_critical_desc": {
        "pt": "<strong>CRITICO vs Normal:</strong> O status CRITICO aparece quando a memoria disponivel e &lt; 5% da RAM total. Se o OS/Cache for alto, pode nao ser um problema real.",
        "en": "<strong>CRITICAL vs Normal:</strong> CRITICAL status appears when available memory is &lt; 5% of total RAM. If OS/Cache is high, it may not be a real problem.",
        "es": "<strong>CRITICO vs Normal:</strong> El status CRITICO aparece cuando la memoria disponible es &lt; 5% de la RAM total. Si el OS/Cache es alto, puede no ser un problema real."
    },

    # =====================================================
    # SQL MEMORY HELP
    # =====================================================
    "mem.help_buffer_pool": {
        "pt": "<strong>Buffer Pool:</strong> Memoria actualmente usada pelo SQL Server para cache de dados e indices.",
        "en": "<strong>Buffer Pool:</strong> Memory currently used by SQL Server for data and index cache.",
        "es": "<strong>Buffer Pool:</strong> Memoria actualmente usada por SQL Server para cache de datos e indices."
    },
    "mem.help_max_server": {
        "pt": "<strong>Max Server Memory:</strong> Limite maximo configurado. O SQL Server nao usara mais do que este valor.",
        "en": "<strong>Max Server Memory:</strong> Maximum configured limit. SQL Server will not use more than this value.",
        "es": "<strong>Max Server Memory:</strong> Limite maximo configurado. SQL Server no usara mas de este valor."
    },

    # =====================================================
    # RESOURCE GOVERNOR HELP
    # =====================================================
    "mem.help_rg_desc": {
        "pt": "O <em>Resource Governor</em> e uma funcionalidade do SQL Server que permite limitar e gerir a alocacao de CPU e memoria entre diferentes workloads.",
        "en": "<em>Resource Governor</em> is a SQL Server feature that allows limiting and managing CPU and memory allocation between different workloads.",
        "es": "El <em>Resource Governor</em> es una funcionalidad de SQL Server que permite limitar y gestionar la asignacion de CPU y memoria entre diferentes workloads."
    },
    "mem.help_oom_desc": {
        "pt": "<strong>OOM (Out-of-Memory):</strong> Corresponde ao <strong>Event ID 701</strong>. Indica que queries falharam por falta de memoria no pool.",
        "en": "<strong>OOM (Out-of-Memory):</strong> Corresponds to <strong>Event ID 701</strong>. Indicates queries failed due to lack of memory in the pool.",
        "es": "<strong>OOM (Out-of-Memory):</strong> Corresponde al <strong>Event ID 701</strong>. Indica que queries fallaron por falta de memoria en el pool."
    },

    # =====================================================
    # MEMORY PRESSURE EXPLANATIONS
    # =====================================================
    "mem.pressure_na_title": {
        "pt": "O que significa \"N/A - NAO CONFIGURADO\"?",
        "en": "What does \"N/A - NOT CONFIGURED\" mean?",
        "es": "Que significa \"N/A - NO CONFIGURADO\"?"
    },
    "mem.pressure_na_desc": {
        "pt": "O SQL Server ainda nao alocou memoria suficiente para calcular o Memory Pressure. Isso pode acontecer em alguns cenarios:",
        "en": "SQL Server has not yet allocated enough memory to calculate Memory Pressure. This can happen in some scenarios:",
        "es": "SQL Server aun no ha asignado suficiente memoria para calcular el Memory Pressure. Esto puede suceder en algunos escenarios:"
    },
    "mem.pressure_na_fresh": {
        "pt": "<strong>Instancia recem-iniciada:</strong> O SQL Server esta em processo de \"warm-up\" e ainda nao carregou dados no Buffer Pool",
        "en": "<strong>Recently started instance:</strong> SQL Server is in \"warm-up\" process and has not yet loaded data into the Buffer Pool",
        "es": "<strong>Instancia recien iniciada:</strong> SQL Server esta en proceso de \"warm-up\" y aun no ha cargado datos en el Buffer Pool"
    },
    "mem.pressure_na_low_activity": {
        "pt": "<strong>Pouca atividade:</strong> Nao ha queries ativas que forcem o SQL Server a alocar memoria",
        "en": "<strong>Low activity:</strong> No active queries forcing SQL Server to allocate memory",
        "es": "<strong>Poca actividad:</strong> No hay queries activas que fuercen a SQL Server a asignar memoria"
    },
    "mem.pressure_na_target_zero": {
        "pt": "<strong>Target Server Memory = 0:</strong> O contador de performance \"Target Server Memory (KB)\" ainda nao foi calculado",
        "en": "<strong>Target Server Memory = 0:</strong> The performance counter \"Target Server Memory (KB)\" has not been calculated yet",
        "es": "<strong>Target Server Memory = 0:</strong> El contador de rendimiento \"Target Server Memory (KB)\" aun no ha sido calculado"
    },
    "mem.pressure_na_pending": {
        "pt": "<strong>Coleta de dados pendente:</strong> Os dados podem ainda nao ter sido coletados pelo sistema de monitoramento",
        "en": "<strong>Data collection pending:</strong> Data may not yet have been collected by the monitoring system",
        "es": "<strong>Recoleccion de datos pendiente:</strong> Los datos pueden no haber sido recolectados aun por el sistema de monitoreo"
    },
    "mem.pressure_na_action_queries": {
        "pt": "Execute algumas queries no servidor para forcar alocacao de memoria",
        "en": "Run some queries on the server to force memory allocation",
        "es": "Ejecute algunas queries en el servidor para forzar asignacion de memoria"
    },
    "mem.pressure_na_action_check": {
        "pt": "Verifique se o SQL Server esta online e funcionando",
        "en": "Check if SQL Server is online and running",
        "es": "Verifique si SQL Server esta en linea y funcionando"
    },
    "mem.pressure_healthy_title": {
        "pt": "Excelente! Memory Pressure esta SAUDAVEL",
        "en": "Excellent! Memory Pressure is HEALTHY",
        "es": "Excelente! Memory Pressure esta SALUDABLE"
    },
    "mem.pressure_healthy_buffer": {
        "pt": "O Buffer Pool esta bem utilizado",
        "en": "The Buffer Pool is well utilized",
        "es": "El Buffer Pool esta bien utilizado"
    },
    "mem.pressure_healthy_cache": {
        "pt": "Os dados estao sendo cacheados eficientemente",
        "en": "Data is being cached efficiently",
        "es": "Los datos estan siendo cacheados eficientemente"
    },
    "mem.pressure_healthy_nowaste": {
        "pt": "Nao ha desperdicio de memoria alocada",
        "en": "No waste of allocated memory",
        "es": "No hay desperdicio de memoria asignada"
    },
    "mem.pressure_healthy_action": {
        "pt": "<strong>Nenhuma acao necessaria</strong>",
        "en": "<strong>No action required</strong>",
        "es": "<strong>Ninguna accion necesaria</strong>"
    },
    "mem.pressure_healthy_monitor": {
        "pt": "Continue monitorando para garantir que o valor permaneca acima de 95%.",
        "en": "Continue monitoring to ensure the value stays above 95%.",
        "es": "Continue monitoreando para garantizar que el valor permanezca por encima del 95%."
    },
    "mem.pressure_warning_desc": {
        "pt": "O SQL Server esta usando menos memoria do que poderia. Isso pode indicar:",
        "en": "SQL Server is using less memory than it could. This may indicate:",
        "es": "SQL Server esta usando menos memoria de la que podria. Esto puede indicar:"
    },
    "mem.pressure_warning_warmup": {
        "pt": "SQL Server ainda nao \"aqueceu\" completamente",
        "en": "SQL Server has not fully \"warmed up\" yet",
        "es": "SQL Server aun no ha \"calentado\" completamente"
    },
    "mem.pressure_warning_alloc": {
        "pt": "Possivel problema de alocacao de memoria",
        "en": "Possible memory allocation issue",
        "es": "Posible problema de asignacion de memoria"
    },
    "mem.pressure_warning_recs": {
        "pt": "<strong>Recomendacoes:</strong>",
        "en": "<strong>Recommendations:</strong>",
        "es": "<strong>Recomendaciones:</strong>"
    },
    "mem.pressure_warning_slow": {
        "pt": "Verifique se ha queries lentas que poderiam se beneficiar de mais cache",
        "en": "Check for slow queries that could benefit from more cache",
        "es": "Verifique si hay queries lentas que podrian beneficiarse de mas cache"
    },
    "mem.pressure_warning_maxmem": {
        "pt": "Considere revisar a configuracao de Max Server Memory",
        "en": "Consider reviewing Max Server Memory configuration",
        "es": "Considere revisar la configuracion de Max Server Memory"
    },
    "mem.pressure_critical_desc": {
        "pt": "O SQL Server esta usando significativamente menos memoria do que alocou. Isso pode indicar problemas serios:",
        "en": "SQL Server is using significantly less memory than allocated. This may indicate serious issues:",
        "es": "SQL Server esta usando significativamente menos memoria de la asignada. Esto puede indicar problemas serios:"
    },
    "mem.pressure_critical_external": {
        "pt": "Pressao externa de memoria do Windows",
        "en": "External Windows memory pressure",
        "es": "Presion externa de memoria del Windows"
    },
    "mem.pressure_critical_config": {
        "pt": "Configuracao incorreta de memoria",
        "en": "Incorrect memory configuration",
        "es": "Configuracion incorrecta de memoria"
    },
    "mem.pressure_critical_perf": {
        "pt": "Problema de performance que impede alocacao",
        "en": "Performance issue preventing allocation",
        "es": "Problema de rendimiento que impide asignacion"
    },
    "mem.pressure_critical_actions": {
        "pt": "<strong>Acoes urgentes:</strong>",
        "en": "<strong>Urgent actions:</strong>",
        "es": "<strong>Acciones urgentes:</strong>"
    },
    "mem.pressure_critical_check_win": {
        "pt": "Verifique o consumo de memoria do Windows (Available MB)",
        "en": "Check Windows memory consumption (Available MB)",
        "es": "Verifique el consumo de memoria del Windows (Available MB)"
    },
    "mem.pressure_critical_identify": {
        "pt": "Identifique processos que competem por memoria",
        "en": "Identify processes competing for memory",
        "es": "Identifique procesos que compiten por memoria"
    },
    "mem.pressure_critical_increase": {
        "pt": "Considere aumentar Max Server Memory se houver RAM disponivel",
        "en": "Consider increasing Max Server Memory if RAM is available",
        "es": "Considere aumentar Max Server Memory si hay RAM disponible"
    },
    "mem.pressure_efficiency": {
        "pt": "eficiencia do uso de memoria",
        "en": "memory usage efficiency",
        "es": "eficiencia del uso de memoria"
    },
    "mem.pressure_formula": {
        "pt": "Formula:",
        "en": "Formula:",
        "es": "Formula:"
    },
    "mem.pressure_closer_100": {
        "pt": "Quanto mais proximo de 100%, melhor!",
        "en": "The closer to 100%, the better!",
        "es": "Cuanto mas cerca del 100%, mejor!"
    },

    # =====================================================
    # BACKUP MODULE
    # =====================================================
    "backup.last_full": {
        "pt": "Ultimo FULL",
        "en": "Last FULL",
        "es": "Ultimo FULL"
    },
    "backup.last_diff": {
        "pt": "Ultimo DIFF",
        "en": "Last DIFF",
        "es": "Ultimo DIFF"
    },
    "backup.last_log": {
        "pt": "Ultimo LOG",
        "en": "Last LOG",
        "es": "Ultimo LOG"
    },
    "backup.pattern": {
        "pt": "Padrao",
        "en": "Pattern",
        "es": "Patron"
    },
    "backup.no_justification": {
        "pt": "SEM Justificativa",
        "en": "WITHOUT Justification",
        "es": "SIN Justificacion"
    },
    "backup.avg_gap_h": {
        "pt": "Gap Medio (h)",
        "en": "Avg Gap (h)",
        "es": "Gap Medio (h)"
    },
    "backup.filter_all": {
        "pt": "Todos",
        "en": "All",
        "es": "Todos"
    },
    "backup.filter_no_full": {
        "pt": "Sem FULL",
        "en": "Without FULL",
        "es": "Sin FULL"
    },
    "backup.filter_no_log": {
        "pt": "Sem LOG",
        "en": "Without LOG",
        "es": "Sin LOG"
    },
    "backup.all_severities": {
        "pt": "Todas",
        "en": "All",
        "es": "Todas"
    },
    "backup.last_14_days": {
        "pt": "Ultimos 14 dias",
        "en": "Last 14 days",
        "es": "Ultimos 14 dias"
    },
    "backup.last_21_days": {
        "pt": "Ultimos 21 dias",
        "en": "Last 21 days",
        "es": "Ultimos 21 dias"
    },
    "backup.last_30_days": {
        "pt": "Ultimos 30 dias",
        "en": "Last 30 days",
        "es": "Ultimos 30 dias"
    },
    "backup.no_records_found": {
        "pt": "Nenhum registro encontrado com os filtros aplicados.",
        "en": "No records found with the applied filters.",
        "es": "Ningun registro encontrado con los filtros aplicados."
    },

    # =====================================================
    # LOG MODULE (extra)
    # =====================================================
    "log.type_all": {
        "pt": "Todos",
        "en": "All",
        "es": "Todos"
    },
    "log.no_logs_24h": {
        "pt": "Nao foram encontrados logs nas ultimas 24 horas para este servico.",
        "en": "No logs found in the last 24 hours for this service.",
        "es": "No se encontraron logs en las ultimas 24 horas para este servicio."
    },
    "log.no_logs_title": {
        "pt": "Nenhum log encontrado",
        "en": "No logs found",
        "es": "Ningun log encontrado"
    },
    "log.click_full_message": {
        "pt": "Clique para ver a mensagem completa",
        "en": "Click to view the full message",
        "es": "Clic para ver el mensaje completo"
    },

    # =====================================================
    # ALWAYSON MODULE (extra)
    # =====================================================
    "alwayson.ag_not_healthy_msg": {
        "pt": "<strong>O AG esta com status NOT_HEALTHY</strong>, mas nao houve eventos de failover nos ultimos 30 dias.",
        "en": "<strong>The AG has NOT_HEALTHY status</strong>, but there were no failover events in the last 30 days.",
        "es": "<strong>El AG tiene status NOT_HEALTHY</strong>, pero no hubo eventos de failover en los ultimos 30 dias."
    },
    "alwayson.ag_not_healthy_hint": {
        "pt": "Isso indica um problema recente (replica offline, conectividade, sincronizacao pendente) que ainda nao gerou failover.",
        "en": "This indicates a recent issue (offline replica, connectivity, pending synchronization) that has not yet caused a failover.",
        "es": "Esto indica un problema reciente (replica offline, conectividad, sincronizacion pendiente) que aun no ha generado failover."
    },
    "alwayson.running_diagnosis": {
        "pt": "Executando diagnostico... Analisando endpoint, replicas e logs...",
        "en": "Running diagnostics... Analyzing endpoint, replicas and logs...",
        "es": "Ejecutando diagnostico... Analizando endpoint, replicas y logs..."
    },
    "alwayson.diagnosis_error": {
        "pt": "Erro ao executar diagnostico:",
        "en": "Error running diagnostics:",
        "es": "Error al ejecutar diagnostico:"
    },
    "alwayson.actions_recommended": {
        "pt": "Acoes recomendadas:",
        "en": "Recommended actions:",
        "es": "Acciones recomendadas:"
    },
    "alwayson.diagnosis_failed": {
        "pt": "Nao foi possivel realizar o diagnostico:",
        "en": "Could not perform diagnostics:",
        "es": "No fue posible realizar el diagnostico:"
    },
    "alwayson.analysis_failed": {
        "pt": "Nao foi possivel realizar a analise:",
        "en": "Could not perform the analysis:",
        "es": "No fue posible realizar el analisis:"
    },
    "alwayson.server_overloaded": {
        "pt": "O servidor esta sobrecarregado",
        "en": "The server is overloaded",
        "es": "El servidor esta sobrecargado"
    },
    "alwayson.network_slow": {
        "pt": "A rede esta lenta ou instavel",
        "en": "The network is slow or unstable",
        "es": "La red esta lenta o inestable"
    },
    "alwayson.too_many_queries": {
        "pt": "O servidor esta processando muitas consultas",
        "en": "The server is processing too many queries",
        "es": "El servidor esta procesando muchas consultas"
    },
    "alwayson.details_label": {
        "pt": "Detalhes:",
        "en": "Details:",
        "es": "Detalles:"
    },
    "alwayson.server_label": {
        "pt": "Servidor:",
        "en": "Server:",
        "es": "Servidor:"
    },
    "alwayson.error_label": {
        "pt": "Erro:",
        "en": "Error:",
        "es": "Error:"
    },
    "alwayson.fetch_primary_title": {
        "pt": "Buscar dados completos do no primario",
        "en": "Fetch complete data from primary node",
        "es": "Buscar datos completos del nodo primario"
    },
    "alwayson.sync_label": {
        "pt": "Sincronizacao:",
        "en": "Synchronization:",
        "es": "Sincronizacion:"
    },
    "alwayson.replicas_label_inline": {
        "pt": "Replicas:",
        "en": "Replicas:",
        "es": "Replicas:"
    },
    "alwayson.th_server": {
        "pt": "Servidor",
        "en": "Server",
        "es": "Servidor"
    },
    "alwayson.th_connection": {
        "pt": "Conexao",
        "en": "Connection",
        "es": "Conexion"
    },
    "alwayson.th_primary": {
        "pt": "Primaria",
        "en": "Primary",
        "es": "Primaria"
    },
    "alwayson.th_description": {
        "pt": "Descricao",
        "en": "Description",
        "es": "Descripcion"
    },

    # =====================================================
    # PREDICTIVE ANALYSIS
    # =====================================================
    "predict.generate_title": {
        "pt": "Gerar analise preditiva completa",
        "en": "Generate complete predictive analysis",
        "es": "Generar analisis predictivo completo"
    },
    "predict.min_7_days": {
        "pt": "7 dias de historico",
        "en": "7 days of history",
        "es": "7 dias de historico"
    },
    "predict.no_data_msg": {
        "pt": "Coleta de dados nao esta ativa para este servidor",
        "en": "Data collection is not active for this server",
        "es": "La recoleccion de datos no esta activa para este servidor"
    },
    "predict.not_monitored": {
        "pt": "Servidor nao esta sendo monitorado",
        "en": "Server is not being monitored",
        "es": "El servidor no esta siendo monitorado"
    },
    "predict.check_collection": {
        "pt": "Verificar se a coleta de dados esta ativa",
        "en": "Check if data collection is active",
        "es": "Verificar si la recoleccion de datos esta activa"
    },
    "predict.wait_7_days": {
        "pt": "Aguardar acumular pelo menos 7 dias de historico",
        "en": "Wait to accumulate at least 7 days of history",
        "es": "Esperar a acumular al menos 7 dias de historico"
    },
    "predict.try_another_fg": {
        "pt": "Tentar com outro filegroup que tenha mais dados",
        "en": "Try with another filegroup that has more data",
        "es": "Intentar con otro filegroup que tenga mas datos"
    },
    "predict.script_not_found": {
        "pt": "Se nao existir, adicione o script ou desabilite a funcionalidade de analise preditiva",
        "en": "If it doesn't exist, add the script or disable the predictive analysis feature",
        "es": "Si no existe, agregue el script o deshabilite la funcionalidad de analisis predictivo"
    },
    "predict.use_space_analysis": {
        "pt": "Use a analise de espaco atual para monitoramento imediato",
        "en": "Use the current space analysis for immediate monitoring",
        "es": "Use el analisis de espacio actual para monitoreo inmediato"
    },
    "predict.possible_causes": {
        "pt": "Possiveis causas:",
        "en": "Possible causes:",
        "es": "Posibles causas:"
    },
    "predict.scripts_not_found": {
        "pt": "Scripts Python nao encontrados na raiz do projeto",
        "en": "Python scripts not found in the project root",
        "es": "Scripts Python no encontrados en la raiz del proyecto"
    },
    "predict.oracle_timeout": {
        "pt": "Timeout na extracao de dados (Oracle lento)",
        "en": "Timeout extracting data (slow Oracle)",
        "es": "Timeout en la extraccion de datos (Oracle lento)"
    },
    "predict.refresh_title": {
        "pt": "Atualizar Analise Preditiva",
        "en": "Refresh Predictive Analysis",
        "es": "Actualizar Analisis Predictivo"
    },
    "predict.click_critical": {
        "pt": "Clique para ver alertas criticos",
        "en": "Click to view critical alerts",
        "es": "Clic para ver alertas criticos"
    },
    "predict.no_critical": {
        "pt": "Nenhum alerta critico",
        "en": "No critical alerts",
        "es": "Ningun alerta critico"
    },
    "predict.click_high": {
        "pt": "Clique para ver alertas de risco alto",
        "en": "Click to view high risk alerts",
        "es": "Clic para ver alertas de riesgo alto"
    },
    "predict.no_high": {
        "pt": "Nenhum alerta de risco alto",
        "en": "No high risk alerts",
        "es": "Ningun alerta de riesgo alto"
    },
    "predict.click_medium": {
        "pt": "Clique para ver alertas de risco medio",
        "en": "Click to view medium risk alerts",
        "es": "Clic para ver alertas de riesgo medio"
    },
    "predict.no_medium": {
        "pt": "Nenhum alerta de risco medio",
        "en": "No medium risk alerts",
        "es": "Ningun alerta de riesgo medio"
    },
    "predict.click_all_fg": {
        "pt": "Clique para ver todos os filegroups analisados",
        "en": "Click to view all analyzed filegroups",
        "es": "Clic para ver todos los filegroups analizados"
    },
    "predict.recommendation": {
        "pt": "Recomendacao",
        "en": "Recommendation",
        "es": "Recomendacion"
    },

    # =====================================================
    # SERVICES MODULE
    # =====================================================
    "services.possible_causes": {
        "pt": "<strong>Possiveis causas:</strong> Firewall bloqueando acesso remoto ao SCM, permissoes insuficientes, ou dados ainda nao coletados no WatcherDB Intelligence.",
        "en": "<strong>Possible causes:</strong> Firewall blocking remote SCM access, insufficient permissions, or data not yet collected in WatcherDB Intelligence.",
        "es": "<strong>Posibles causas:</strong> Firewall bloqueando acceso remoto al SCM, permisos insuficientes, o datos aun no recolectados en WatcherDB Intelligence."
    },

    # =====================================================
    # KPI DASHBOARD
    # =====================================================
    "kpi.refresh_card_title": {
        "pt": "Atualizar este card",
        "en": "Refresh this card",
        "es": "Actualizar esta tarjeta"
    },

    # =====================================================
    # TEMPDB / SQL DIAGNOSTICS
    # =====================================================
    "tempdb.open_diag_title": {
        "pt": "Clique para abrir TempDB no SQL Diagnostics",
        "en": "Click to open TempDB in SQL Diagnostics",
        "es": "Clic para abrir TempDB en SQL Diagnostics"
    },
    "tempdb.click_details": {
        "pt": "Clique para ver mais detalhes",
        "en": "Click to view more details",
        "es": "Clic para ver mas detalles"
    },
    "tempdb.filter_idle_title": {
        "pt": "Clique para filtrar sessoes com idle =30 min",
        "en": "Click to filter sessions with idle =30 min",
        "es": "Clic para filtrar sesiones con idle =30 min"
    },
    "tempdb.click_sort": {
        "pt": "Clique para ordenar",
        "en": "Click to sort",
        "es": "Clic para ordenar"
    },
    "tempdb.click_full_query": {
        "pt": "Clique para ver a query completa",
        "en": "Click to view the full query",
        "es": "Clic para ver la query completa"
    },
    "tempdb.click_exec_plan": {
        "pt": "Clique para ver o plano de execucao",
        "en": "Click to view the execution plan",
        "es": "Clic para ver el plan de ejecucion"
    },
    "tempdb.analyze_patterns": {
        "pt": "Analisar padroes e correlacionar com diagnosticos",
        "en": "Analyze patterns and correlate with diagnostics",
        "es": "Analizar patrones y correlacionar con diagnosticos"
    },

    # =====================================================
    # SQL STATS / INDEX ANALYSIS
    # =====================================================
    "stats.heap_tooltip": {
        "pt": "HEAP: Tabela sem indice clustered. Dados armazenados sem ordem, o que pode impactar performance em buscas. Considere criar um indice clustered na chave primaria ou coluna mais consultada.",
        "en": "HEAP: Table without clustered index. Data stored without order, which can impact search performance. Consider creating a clustered index on the primary key or most queried column.",
        "es": "HEAP: Tabla sin indice clustered. Datos almacenados sin orden, lo que puede impactar el rendimiento en busquedas. Considere crear un indice clustered en la clave primaria o columna mas consultada."
    },
    "stats.existing_indexes": {
        "pt": "indices ja existentes",
        "en": "already existing indexes",
        "es": "indices ya existentes"
    },
    "stats.decision_factors": {
        "pt": "Fatores de decisao:",
        "en": "Decision factors:",
        "es": "Factores de decision:"
    },
    "stats.th_index_stats": {
        "pt": "Indice/Stats",
        "en": "Index/Stats",
        "es": "Indice/Stats"
    },
    "stats.th_last_update": {
        "pt": "Ultima Atualizacao",
        "en": "Last Update",
        "es": "Ultima Actualizacion"
    },
    "stats.th_modifications": {
        "pt": "Modificacoes",
        "en": "Modifications",
        "es": "Modificaciones"
    },
    "stats.th_recommendation": {
        "pt": "Recomendacao",
        "en": "Recommendation",
        "es": "Recomendacion"
    },
    "stats.expand_view_title": {
        "pt": "Expandir para ver tabelas base da VIEW",
        "en": "Expand to see VIEW base tables",
        "es": "Expandir para ver tablas base de la VIEW"
    },
    "stats.identifying_tables": {
        "pt": "Identificando tabelas e VIEWs que compoem esta VIEW",
        "en": "Identifying tables and VIEWs that compose this VIEW",
        "es": "Identificando tablas y VIEWs que componen esta VIEW"
    },
    "stats.analyzing_stats": {
        "pt": "Analisando estatisticas de cada tabela base",
        "en": "Analyzing statistics for each base table",
        "es": "Analizando estadisticas de cada tabla base"
    },
    "stats.checking_missing": {
        "pt": "Verificando indices faltantes sugeridos pelo SQL Server",
        "en": "Checking missing indexes suggested by SQL Server",
        "es": "Verificando indices faltantes sugeridos por SQL Server"
    },

    # =====================================================
    # SETTINGS
    # =====================================================
    "settings.include_system_dbs": {
        "pt": "Incluir bases de sistema por padrao",
        "en": "Include system databases by default",
        "es": "Incluir bases de sistema por defecto"
    },
    "settings.sort_frequency": {
        "pt": "Por frequencia de uso",
        "en": "By usage frequency",
        "es": "Por frecuencia de uso"
    },
    "settings.sort_alpha": {
        "pt": "Alfabetica (A-Z)",
        "en": "Alphabetical (A-Z)",
        "es": "Alfabetica (A-Z)"
    },
    "settings.sort_environment": {
        "pt": "Por ambiente (PRD, DEV, QLT)",
        "en": "By environment (PRD, DEV, QLT)",
        "es": "Por entorno (PRD, DEV, QLT)"
    },
    "settings.sidebar_collapsed": {
        "pt": "Sidebar recolhida por padrao",
        "en": "Sidebar collapsed by default",
        "es": "Sidebar colapsada por defecto"
    },
    "settings.sort_category": {
        "pt": "Por categoria/topico",
        "en": "By category/topic",
        "es": "Por categoria/topico"
    },
    "settings.sort_custom": {
        "pt": "Personalizada (arraste para reorganizar)",
        "en": "Custom (drag to reorganize)",
        "es": "Personalizada (arrastre para reorganizar)"
    },

    # =====================================================
    # SQL QUERIES MODULE
    # =====================================================
    "sqlquery.desc_placeholder": {
        "pt": "Descricao da query",
        "en": "Query description",
        "es": "Descripcion de la query"
    },
    "sqlquery.diag_title": {
        "pt": "Diagnostico de Query - WatcherDB",
        "en": "Query Diagnostics - WatcherDB",
        "es": "Diagnostico de Query - WatcherDB"
    },
    "sqlquery.diag_slow_title": {
        "pt": "Diagnostico de Query Lenta",
        "en": "Slow Query Diagnostics",
        "es": "Diagnostico de Query Lenta"
    },
    "sqlquery.instance_label": {
        "pt": "Instancia:",
        "en": "Instance:",
        "es": "Instancia:"
    },

    # =====================================================
    # COPILOT / INTELLIGENCE DASHBOARD
    # =====================================================
    "copilot.loading_scores": {
        "pt": "Carregando scores de manutencao preditiva...",
        "en": "Loading predictive maintenance scores...",
        "es": "Cargando scores de mantenimiento predictivo..."
    },
    "copilot.most_affected": {
        "pt": "Instancia Mais Afetada",
        "en": "Most Affected Instance",
        "es": "Instancia Mas Afectada"
    },
    "copilot.no_urgent_alerts": {
        "pt": "Nenhum alerta urgente no momento",
        "en": "No urgent alerts at the moment",
        "es": "Ningun alerta urgente en este momento"
    },
    "copilot.no_events": {
        "pt": "Nenhum evento no periodo",
        "en": "No events in the period",
        "es": "Ningun evento en el periodo"
    },
    "copilot.loading_insights": {
        "pt": "Carregando insights...",
        "en": "Loading insights...",
        "es": "Cargando insights..."
    },
    "copilot.no_insights": {
        "pt": "Nenhum insight disponivel",
        "en": "No insights available",
        "es": "Ningun insight disponible"
    },
    "copilot.generating_report": {
        "pt": "Gerando relatorio...",
        "en": "Generating report...",
        "es": "Generando informe..."
    },

    # =====================================================
    # SECURITY (config health)
    # =====================================================
    "security.config_healthy": {
        "pt": "saudavel",
        "en": "healthy",
        "es": "saludable"
    },

    # =====================================================
    # REPORTS
    # =====================================================
    "report.last_status": {
        "pt": "Ultimo Status",
        "en": "Last Status",
        "es": "Ultimo Status"
    },
}


def flatten_dict(d, prefix=''):
    result = {}
    for k, v in d.items():
        key = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict):
            result.update(flatten_dict(v, key))
        else:
            result[key] = str(v)
    return result


def flat_to_nested(flat_dict):
    nested = {}
    for key, val in sorted(flat_dict.items()):
        parts = key.split('.')
        current = nested
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                break
            current = current[part]
        current[parts[-1]] = val
    return nested


def main():
    print('=' * 60)
    print('i18n Final Keys - Adding remaining translation keys')
    print('=' * 60)

    for lang in ['pt', 'en', 'es']:
        json_path = os.path.join(I18N_DIR, f'{lang}.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)

        existing_flat = flatten_dict(existing)
        added = 0

        for key, translations in NEW_KEYS.items():
            if key not in existing_flat:
                existing_flat[key] = translations[lang]
                added += 1

        nested = flat_to_nested(existing_flat)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(nested, f, ensure_ascii=False, indent=2, sort_keys=True)

        print(f'  {lang}.json: +{added} keys (total: {len(flatten_dict(nested))})')

    print('\nDone! Keys added to all 3 JSON files.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
