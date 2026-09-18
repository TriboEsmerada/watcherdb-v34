# -*- coding: utf-8 -*-
"""i18n, lote 2 (relatórios de diagnóstico): títulos, recomendações, detalhes estáticos e títulos de SQL das 77 regras,
mais os rótulos fixos dos 13 geradores, em pt/pt-BR/en/es (2026-09-18).

DESENHO: um único ponto de tradução em evaluateRules, por id da regra (`rep.<ID>.title|rec|detail|sql.<n>`), com o texto
original como recurso -- os 13 dicionários *_RULES ficam intactos. Os 61 detalhes DINÂMICOS (funções que montam a frase
com dados) continuam em português: são o lote 2b, regra a regra. O que este lote traduz é o que se lê primeiro em cada
achado (título, badge, recomendação) e as frases fixas dos geradores ("Nenhum problema detectado.", cabeçalhos das
tabelas, CRÍTICO/ALERTA/SAUDÁVEL, Sim/Não).

Também: actualiza a linha de base do teste de guarda (tests/unit/test_i18n_texto_a_mao_20260918.py) para os números
depois deste lote -- só pode descer.

Uso (raiz do repo):
  py docs/context/REP_I18N_2026-09-18_apply.py --check
  py docs/context/REP_I18N_2026-09-18_apply.py
  py -m pytest tests/unit/test_rep_i18n_20260918.py tests/unit/test_i18n_texto_a_mao_20260918.py tests/unit/test_i18n_parity.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 (qualquer relatório de diagnóstico, portal em EN)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {"portal": Path("templates/watcherdb_portal.html"), "pt": Path("static/i18n/pt.json"), "en": Path("static/i18n/en.json"),
       "es": Path("static/i18n/es.json"), "ptbr": Path("static/i18n/pt-BR.json"), "changelog": Path("docs/changelog/CHANGELOG.md"),
       "test": Path("tests/unit/test_rep_i18n_20260918.py"), "guarda": Path("tests/unit/test_i18n_texto_a_mao_20260918.py")}
MARK = "function _repT("

# ----------------------------------------------------------------------------------------------------------------------
# Regras: id -> {title, rec, detail, sql:[...]}  (pt = português europeu, AO90, acentuado; en; es)
# ----------------------------------------------------------------------------------------------------------------------
R = {}
def regra(rid, pt, en, es):
    R[rid] = {"pt": pt, "en": en, "es": es}

regra("CPU001", {"title": "CPU do sistema operativo crítica", "rec": "Identificar queries com CPU alto (Top CPU Queries). Verificar se existem processos não-SQL a consumir CPU. Considerar escalar recursos.", "sql": ["Top 20 queries por CPU (agora)"]},
      {"title": "Operating system CPU critical", "rec": "Identify high-CPU queries (Top CPU Queries). Check for non-SQL processes consuming CPU. Consider scaling resources.", "sql": ["Top 20 queries by CPU (now)"]},
      {"title": "CPU del sistema operativo crítica", "rec": "Identificar queries con CPU alto (Top CPU Queries). Verificar si hay procesos no-SQL consumiendo CPU. Considerar escalar recursos.", "sql": ["Top 20 queries por CPU (ahora)"]})
regra("CPU002", {"title": "SQL Server com uso de CPU elevado", "rec": "Analisar as queries ativas com maior consumo de CPU. Verificar planos de execução e índices em falta.", "sql": ["Top 15 queries acumuladas por CPU (plan cache)"]},
      {"title": "SQL Server with high CPU usage", "rec": "Analyse the active queries with the highest CPU. Check execution plans and missing indexes.", "sql": ["Top 15 cumulative queries by CPU (plan cache)"]},
      {"title": "SQL Server con uso de CPU elevado", "rec": "Analizar las queries activas con mayor consumo de CPU. Verificar planes de ejecución e índices faltantes.", "sql": ["Top 15 queries acumuladas por CPU (plan cache)"]})
regra("CPU003", {"title": "MAXDOP diferente da recomendação", "sql": ["Verificar a configuração MAXDOP atual", "Recomendação MAXDOP baseada no hardware", "Queries com waits de paralelismo (agora)", "Sugestão: alterar MAXDOP (copiar para o SSMS)"]},
      {"title": "MAXDOP differs from the recommendation", "sql": ["Check current MAXDOP setting", "Hardware-based MAXDOP recommendation", "Queries with parallelism waits (now)", "Suggestion: change MAXDOP (copy to SSMS)"]},
      {"title": "MAXDOP distinto de la recomendación", "sql": ["Verificar la configuración MAXDOP actual", "Recomendación MAXDOP según el hardware", "Queries con waits de paralelismo (ahora)", "Sugerencia: cambiar MAXDOP (copiar a SSMS)"]})
regra("CPU004", {"title": "Cost Threshold for Parallelism no valor por omissão", "sql": ["Verificar o Cost Threshold atual", "Sugestão: alterar o Cost Threshold (copiar para o SSMS)"]},
      {"title": "Cost Threshold for Parallelism at default value", "sql": ["Check current Cost Threshold", "Suggestion: change Cost Threshold (copy to SSMS)"]},
      {"title": "Cost Threshold for Parallelism en el valor por defecto", "sql": ["Verificar el Cost Threshold actual", "Sugerencia: cambiar el Cost Threshold (copiar a SSMS)"]})
regra("CPU005", {"title": "Worker Threads perto do limite", "rec": "Investigar queries longas ou bloqueios que estão a manter threads ocupadas. Verificar se Max Worker Threads está configurado corretamente.", "sql": ["Detalhe de worker threads por scheduler"]},
      {"title": "Worker threads near the limit", "rec": "Investigate long queries or blocking keeping threads busy. Check that Max Worker Threads is configured correctly.", "sql": ["Worker thread detail per scheduler"]},
      {"title": "Worker threads cerca del límite", "rec": "Investigar queries largas o bloqueos que mantienen threads ocupados. Verificar que Max Worker Threads esté bien configurado.", "sql": ["Detalle de worker threads por scheduler"]})
regra("CPU006", {"title": "Pressão de CPU nos schedulers", "rec": "Existem tarefas prontas mas sem CPU disponível. Otimizar queries pesadas ou considerar adicionar CPUs ao servidor.", "sql": ["Resumo de pressão nos schedulers", "Tarefas em estado RUNNABLE (à espera de CPU)"]},
      {"title": "CPU pressure on the schedulers", "rec": "There are runnable tasks without available CPU. Optimise heavy queries or consider adding CPUs to the server.", "sql": ["Scheduler pressure summary", "Tasks in RUNNABLE state (waiting for CPU)"]},
      {"title": "Presión de CPU en los schedulers", "rec": "Hay tareas listas pero sin CPU disponible. Optimizar queries pesadas o considerar añadir CPUs al servidor.", "sql": ["Resumen de presión en los schedulers", "Tareas en estado RUNNABLE (esperando CPU)"]})
regra("CPU007", {"title": "Signal waits elevados (contenção de CPU)", "rec": "Reduzir a carga de CPU: otimizar queries, ajustar o paralelismo (MAXDOP) ou adicionar mais CPUs.", "sql": ["Top wait stats relacionados com CPU"]},
      {"title": "High signal waits (CPU contention)", "rec": "Reduce CPU load: optimise queries, tune parallelism (MAXDOP) or add CPUs.", "sql": ["Top CPU-related wait stats"]},
      {"title": "Signal waits elevados (contención de CPU)", "rec": "Reducir la carga de CPU: optimizar queries, ajustar el paralelismo (MAXDOP) o añadir más CPUs.", "sql": ["Top wait stats relacionados con CPU"]})
regra("CPU008", {"title": "Compilações excessivas", "rec": "Ativar \"Optimize for Ad Hoc Workloads\" (sp_configure). Verificar se as queries ad hoc estão parametrizadas.", "sql": ["Contadores de compilação", "Optimize for Ad Hoc Workloads + plan cache", "Plan cache: single-use vs reutilizados", "Sugestão: ativar Optimize for Ad Hoc (copiar para o SSMS)"]},
      {"title": "Excessive compilations", "rec": "Enable \"Optimize for Ad Hoc Workloads\" (sp_configure). Check whether ad hoc queries are parameterised.", "sql": ["Compilation counters", "Optimize for Ad Hoc Workloads + plan cache", "Plan cache: single-use vs reused", "Suggestion: enable Optimize for Ad Hoc (copy to SSMS)"]},
      {"title": "Compilaciones excesivas", "rec": "Activar \"Optimize for Ad Hoc Workloads\" (sp_configure). Verificar si las queries ad hoc están parametrizadas.", "sql": ["Contadores de compilación", "Optimize for Ad Hoc Workloads + plan cache", "Plan cache: single-use vs reutilizados", "Sugerencia: activar Optimize for Ad Hoc (copiar a SSMS)"]})
regra("CPU009", {"title": "Configuração de CPU adequada"}, {"title": "CPU configuration adequate"}, {"title": "Configuración de CPU adecuada"})
regra("MEM001", {"title": "Memória do SO esgotada", "rec": "Reduzir o Max Server Memory do SQL Server para libertar pelo menos 2-4 GB para o SO.", "sql": ["Memória do processo SQL Server", "Top 10 memory clerks (maiores consumidores)", "Sugestão: reduzir Max Server Memory (copiar para o SSMS)"]},
      {"title": "OS memory exhausted", "rec": "Lower SQL Server Max Server Memory to free at least 2-4 GB for the OS.", "sql": ["SQL Server process memory", "Top 10 memory clerks (largest consumers)", "Suggestion: lower Max Server Memory (copy to SSMS)"]},
      {"title": "Memoria del SO agotada", "rec": "Reducir el Max Server Memory de SQL Server para liberar al menos 2-4 GB para el SO.", "sql": ["Memoria del proceso SQL Server", "Top 10 memory clerks (mayores consumidores)", "Sugerencia: reducir Max Server Memory (copiar a SSMS)"]})
regra("MEM002", {"title": "Max Server Memory acima da recomendação Microsoft", "sql": ["Verificar Max/Min Server Memory", "Sugestão: ajustar Max Server Memory (copiar para o SSMS)"]},
      {"title": "Max Server Memory above the Microsoft recommendation", "sql": ["Check Max/Min Server Memory", "Suggestion: adjust Max Server Memory (copy to SSMS)"]},
      {"title": "Max Server Memory por encima de la recomendación de Microsoft", "sql": ["Verificar Max/Min Server Memory", "Sugerencia: ajustar Max Server Memory (copiar a SSMS)"]})
regra("MEM003", {"title": "Memory pressure elevada", "sql": ["Queries com maior consumo de memória (grants)", "Reduzir Max Server Memory temporariamente (buffer pool shrink)"]},
      {"title": "High memory pressure", "sql": ["Queries with the largest memory grants", "Temporarily lower Max Server Memory (buffer pool shrink)"]},
      {"title": "Memory pressure elevada", "sql": ["Queries con mayor consumo de memoria (grants)", "Reducir Max Server Memory temporalmente (buffer pool shrink)"]})
regra("MEM004", {"title": "Min Server Memory não configurado", "rec": "Configurar Min Server Memory para 50-70% do Max Server Memory, para evitar que o SO \"roube\" memória ao SQL Server.", "detail": "Min Server Memory está configurado como 0 MB. O Windows pode reclamar toda a memória do SQL Server sob pressão (memory drain).", "sql": ["Verificar Min/Max Server Memory", "Sugestão: configurar Min Server Memory (copiar para o SSMS)"]},
      {"title": "Min Server Memory not configured", "rec": "Set Min Server Memory to 50-70% of Max Server Memory so the OS cannot \"steal\" memory from SQL Server.", "detail": "Min Server Memory is set to 0 MB. Under pressure, Windows can reclaim all of SQL Server's memory (memory drain).", "sql": ["Check Min/Max Server Memory", "Suggestion: set Min Server Memory (copy to SSMS)"]},
      {"title": "Min Server Memory no configurado", "rec": "Configurar Min Server Memory al 50-70% del Max Server Memory para evitar que el SO le \"robe\" memoria a SQL Server.", "detail": "Min Server Memory está configurado en 0 MB. Bajo presión, Windows puede reclamar toda la memoria de SQL Server (memory drain).", "sql": ["Verificar Min/Max Server Memory", "Sugerencia: configurar Min Server Memory (copiar a SSMS)"]})
regra("MEM005", {"title": "Plan cache potencialmente elevado", "rec": "Verificar se \"Optimize for Ad Hoc Workloads\" está ativo (sp_configure). Considerar DBCC FREEPROCCACHE se necessário.", "sql": ["Optimize for Ad Hoc Workloads", "Plan cache por tipo (single-use vs reutilizados)", "Sugestão: ativar Optimize for Ad Hoc (copiar para o SSMS)"]},
      {"title": "Plan cache potentially high", "rec": "Check whether \"Optimize for Ad Hoc Workloads\" is on (sp_configure). Consider DBCC FREEPROCCACHE if needed.", "sql": ["Optimize for Ad Hoc Workloads", "Plan cache by type (single-use vs reused)", "Suggestion: enable Optimize for Ad Hoc (copy to SSMS)"]},
      {"title": "Plan cache potencialmente elevado", "rec": "Verificar si \"Optimize for Ad Hoc Workloads\" está activo (sp_configure). Considerar DBCC FREEPROCCACHE si es necesario.", "sql": ["Optimize for Ad Hoc Workloads", "Plan cache por tipo (single-use vs reutilizados)", "Sugerencia: activar Optimize for Ad Hoc (copiar a SSMS)"]})
regra("MEM006", {"title": "Resource Governor com eventos OOM", "rec": "Investigar que pools têm limites de memória insuficientes. Considerar aumentar MAX_MEMORY_PERCENT nos pools afetados.", "sql": ["Pools do Resource Governor e configuração"]},
      {"title": "Resource Governor with OOM events", "rec": "Investigate which pools have insufficient memory limits. Consider raising MAX_MEMORY_PERCENT on the affected pools.", "sql": ["Resource Governor pools and configuration"]},
      {"title": "Resource Governor con eventos OOM", "rec": "Investigar qué pools tienen límites de memoria insuficientes. Considerar aumentar MAX_MEMORY_PERCENT en los pools afectados.", "sql": ["Pools del Resource Governor y configuración"]})
regra("MEM007", {"title": "Configuração de memória adequada"}, {"title": "Memory configuration adequate"}, {"title": "Configuración de memoria adecuada"})
regra("JOB001", {"title": "Jobs com falhas nas últimas 24 h", "rec": "Verificar a mensagem de erro de cada job falhado no Job History do SQL Agent. Corrigir a causa raiz antes do próximo agendamento.", "sql": ["Jobs que falharam nas últimas 24 h"]},
      {"title": "Jobs with failures in the last 24 h", "rec": "Check the error message of each failed job in the SQL Agent Job History. Fix the root cause before the next schedule.", "sql": ["Jobs that failed in the last 24 h"]},
      {"title": "Jobs con fallos en las últimas 24 h", "rec": "Verificar el mensaje de error de cada job fallido en el Job History del SQL Agent. Corregir la causa raíz antes de la próxima programación.", "sql": ["Jobs que fallaron en las últimas 24 h"]})
regra("JOB002", {"title": "Jobs cuja última execução falhou", "rec": "Investigar cada job com a última execução falhada. Executar manualmente para verificar se o problema persiste.", "sql": ["Jobs cuja última execução falhou"]},
      {"title": "Jobs whose last run failed", "rec": "Investigate each job whose last run failed. Run it manually to check whether the problem persists.", "sql": ["Jobs whose last run failed"]},
      {"title": "Jobs cuya última ejecución falló", "rec": "Investigar cada job con la última ejecución fallida. Ejecutarlo manualmente para comprobar si el problema persiste.", "sql": ["Jobs cuya última ejecución falló"]})
regra("JOB003", {"title": "Jobs em execução prolongada", "rec": "Verificar se os jobs estão bloqueados (sp_who2, sys.dm_exec_requests). Comparar a duração com execuções anteriores.", "sql": ["Jobs em execução agora"]},
      {"title": "Long-running jobs", "rec": "Check whether the jobs are blocked (sp_who2, sys.dm_exec_requests). Compare the duration with previous runs.", "sql": ["Jobs running now"]},
      {"title": "Jobs en ejecución prolongada", "rec": "Verificar si los jobs están bloqueados (sp_who2, sys.dm_exec_requests). Comparar la duración con ejecuciones anteriores.", "sql": ["Jobs en ejecución ahora"]})
regra("JOB004", {"title": "Proporção elevada de jobs desativados", "rec": "Rever a lista de jobs desativados. Remover os que já não são necessários e reativar os que deviam estar ativos.", "sql": ["Jobs desativados"]},
      {"title": "High proportion of disabled jobs", "rec": "Review the disabled jobs. Remove the ones no longer needed and re-enable the ones that should be running.", "sql": ["Disabled jobs"]},
      {"title": "Proporción elevada de jobs desactivados", "rec": "Revisar la lista de jobs desactivados. Eliminar los que ya no hacen falta y reactivar los que deberían estar activos.", "sql": ["Jobs desactivados"]})
regra("JOB005", {"title": "Cobertura de manutenção incompleta", "rec": "Criar planos de manutenção (Rebuild Indexes, Update Statistics, Integrity Check) para todas as bases de dados. Usar Ola Hallengren ou Maintenance Plans.", "sql": ["Bases sem manutenção"]},
      {"title": "Incomplete maintenance coverage", "rec": "Create maintenance plans (Rebuild Indexes, Update Statistics, Integrity Check) for every database. Use Ola Hallengren or Maintenance Plans.", "sql": ["Databases without maintenance"]},
      {"title": "Cobertura de mantenimiento incompleta", "rec": "Crear planes de mantenimiento (Rebuild Indexes, Update Statistics, Integrity Check) para todas las bases de datos. Usar Ola Hallengren o Maintenance Plans.", "sql": ["Bases sin mantenimiento"]})
regra("JOB006", {"title": "Jobs de manutenção desativados", "rec": "Verificar e reativar os jobs de manutenção desativados. A desativação prolongada causa fragmentação de índices e estatísticas desatualizadas.", "sql": ["Jobs de manutenção e o seu estado"]},
      {"title": "Maintenance jobs disabled", "rec": "Check and re-enable the disabled maintenance jobs. Prolonged disabling causes index fragmentation and stale statistics.", "sql": ["Maintenance jobs and their state"]},
      {"title": "Jobs de mantenimiento desactivados", "rec": "Verificar y reactivar los jobs de mantenimiento desactivados. La desactivación prolongada causa fragmentación de índices y estadísticas desactualizadas.", "sql": ["Jobs de mantenimiento y su estado"]})
regra("JOB007", {"title": "Nenhum job configurado", "rec": "Verificar se o serviço SQL Server Agent está em execução. Configurar jobs de backup, manutenção e monitorização.", "detail": "Nenhum job do SQL Agent encontrado nesta instância. Pode indicar que o SQL Agent não está configurado ou que os jobs foram removidos.", "sql": ["Verificar o estado do SQL Agent"]},
      {"title": "No jobs configured", "rec": "Check that the SQL Server Agent service is running. Set up backup, maintenance and monitoring jobs.", "detail": "No SQL Agent job found on this instance. The SQL Agent may not be configured, or the jobs may have been removed.", "sql": ["Check SQL Agent state"]},
      {"title": "Ningún job configurado", "rec": "Verificar que el servicio SQL Server Agent esté en ejecución. Configurar jobs de backup, mantenimiento y monitorización.", "detail": "No se encontró ningún job del SQL Agent en esta instancia. Puede indicar que el SQL Agent no está configurado o que los jobs fueron eliminados.", "sql": ["Verificar el estado del SQL Agent"]})
regra("JOB008", {"title": "Configuração de jobs adequada"}, {"title": "Jobs configuration adequate"}, {"title": "Configuración de jobs adecuada"})
regra("BKP001", {"title": "Bases de dados sem backup FULL recente", "rec": "Executar backup FULL imediatamente. Verificar o agendamento do job de backup e os logs de erro.", "sql": ["Bases de dados sem backup FULL recente"]},
      {"title": "Databases without a recent FULL backup", "rec": "Run a FULL backup immediately. Check the backup job schedule and the error logs.", "sql": ["Databases without a recent FULL backup"]},
      {"title": "Bases de datos sin backup FULL reciente", "rec": "Ejecutar un backup FULL de inmediato. Verificar la programación del job de backup y los logs de error.", "sql": ["Bases de datos sin backup FULL reciente"]})
regra("BKP002", {"title": "Bases de dados sem backup DIFF recente", "rec": "Verificar o agendamento dos backups diferenciais. Configurar se não existir."},
      {"title": "Databases without a recent DIFF backup", "rec": "Check the differential backup schedule. Configure it if missing."},
      {"title": "Bases de datos sin backup DIFF reciente", "rec": "Verificar la programación de los backups diferenciales. Configurarla si no existe."})
regra("BKP003", {"title": "Bases em FULL recovery sem backup de LOG", "rec": "Configurar backup de LOG (15-60 min). Se não for necessário, alterar o recovery model para SIMPLE.", "sql": ["Bases em FULL recovery sem backup de LOG recente"]},
      {"title": "FULL-recovery databases without LOG backup", "rec": "Configure LOG backups (15-60 min). If not needed, switch the recovery model to SIMPLE.", "sql": ["FULL-recovery databases without a recent LOG backup"]},
      {"title": "Bases en FULL recovery sin backup de LOG", "rec": "Configurar backup de LOG (15-60 min). Si no es necesario, cambiar el recovery model a SIMPLE.", "sql": ["Bases en FULL recovery sin backup de LOG reciente"]})
regra("BKP004", {"title": "Jobs de backup falhados", "rec": "Verificar a mensagem de erro de cada job. Causas comuns: disco cheio, permissões, rede inacessível."},
      {"title": "Failed backup jobs", "rec": "Check each job's error message. Common causes: disk full, permissions, unreachable network."},
      {"title": "Jobs de backup fallidos", "rec": "Verificar el mensaje de error de cada job. Causas comunes: disco lleno, permisos, red inaccesible."})
regra("BKP005", {"title": "Bases de dados sem nenhum backup registado", "rec": "Executar backup FULL imediatamente e incluir no plano de backup."},
      {"title": "Databases with no backup on record", "rec": "Run a FULL backup immediately and add them to the backup plan."},
      {"title": "Bases de datos sin ningún backup registrado", "rec": "Ejecutar un backup FULL de inmediato e incluirlas en el plan de backup."})
regra("BKP006", {"title": "Backups OK", "detail": "Todos os backups estão em dia. Nenhuma falha crítica detetada."},
      {"title": "Backups OK", "detail": "All backups are up to date. No critical gap detected."},
      {"title": "Backups OK", "detail": "Todos los backups están al día. Ningún gap crítico detectado."})
regra("DSK001", {"title": "Volumes com uso crítico (>= 95%)", "rec": "Expandir o disco, mover dados ou limpar ficheiros temporários/backups antigos imediatamente.", "sql": ["Espaço em disco por volume"]},
      {"title": "Volumes at critical usage (>= 95%)", "rec": "Expand the disk, move data or clean temporary files/old backups immediately.", "sql": ["Disk space per volume"]},
      {"title": "Volúmenes con uso crítico (>= 95%)", "rec": "Ampliar el disco, mover datos o limpiar archivos temporales/backups antiguos de inmediato.", "sql": ["Espacio en disco por volumen"]})
regra("DSK002", {"title": "Volumes com uso alto (>= 90%)", "rec": "Planear a expansão do disco. Verificar o autogrowth das bases e limpar ficheiros desnecessários."},
      {"title": "Volumes at high usage (>= 90%)", "rec": "Plan the disk expansion. Check database autogrowth and remove unnecessary files."},
      {"title": "Volúmenes con uso alto (>= 90%)", "rec": "Planificar la ampliación del disco. Verificar el autogrowth de las bases y limpiar archivos innecesarios."})
regra("DSK003", {"title": "Latência de I/O crítica (>= 50 ms)", "rec": "Investigar o subsistema de storage. Considerar migrar para SSD/NVMe. Verificar fragmentação e contenção.", "sql": ["Latência de I/O por ficheiro"]},
      {"title": "Critical I/O latency (>= 50 ms)", "rec": "Investigate the storage subsystem. Consider moving to SSD/NVMe. Check fragmentation and contention.", "sql": ["I/O latency per file"]},
      {"title": "Latencia de I/O crítica (>= 50 ms)", "rec": "Investigar el subsistema de storage. Considerar migrar a SSD/NVMe. Verificar fragmentación y contención.", "sql": ["Latencia de I/O por archivo"]})
regra("DSK004", {"title": "Latência de I/O alta (>= 20 ms)", "rec": "Monitorizar a tendência. Considerar reorganizar ficheiros ou adicionar mais spindles."},
      {"title": "High I/O latency (>= 20 ms)", "rec": "Monitor the trend. Consider reorganising files or adding spindles."},
      {"title": "Latencia de I/O alta (>= 20 ms)", "rec": "Monitorizar la tendencia. Considerar reorganizar archivos o añadir más spindles."})
regra("DSK000", {"title": "I/O não avaliado (dados indisponíveis)", "rec": "Repetir a análise. Se persistir, verificar a conectividade e as permissões da conta de monitorização no servidor alvo.", "detail": "A consulta de latência de I/O falhou nesta recolha. As conclusões deste relatório NÃO cobrem latência de disco — este ponto ficou por avaliar."},
      {"title": "I/O not assessed (data unavailable)", "rec": "Repeat the analysis. If it persists, check connectivity and the monitoring account's permissions on the target server.", "detail": "The I/O latency query failed in this collection. This report's conclusions do NOT cover disk latency — that point remains unassessed."},
      {"title": "I/O no evaluado (datos no disponibles)", "rec": "Repetir el análisis. Si persiste, verificar la conectividad y los permisos de la cuenta de monitorización en el servidor destino.", "detail": "La consulta de latencia de I/O falló en esta recogida. Las conclusiones de este informe NO cubren la latencia de disco — ese punto quedó sin evaluar."})
regra("DSK005", {"title": "Discos OK", "detail": "Todos os volumes abaixo de 85% e latência de I/O normal."},
      {"title": "Disks OK", "detail": "All volumes below 85% and normal I/O latency."},
      {"title": "Discos OK", "detail": "Todos los volúmenes por debajo del 85% y latencia de I/O normal."})
regra("AG001", {"title": "Réplica com sync_health NOT_HEALTHY", "rec": "Verificar a conectividade de rede entre réplicas. Consultar as DMVs de AG e o error log.", "sql": ["Estado das réplicas"]},
      {"title": "Replica with sync_health NOT_HEALTHY", "rec": "Check network connectivity between replicas. Query the AG DMVs and the error log.", "sql": ["Replica state"]},
      {"title": "Réplica con sync_health NOT_HEALTHY", "rec": "Verificar la conectividad de red entre réplicas. Consultar las DMVs de AG y el error log.", "sql": ["Estado de las réplicas"]})
regra("AG002", {"title": "Bases de dados não sincronizadas", "rec": "Verificar o estado da base no AG. Pode ser necessário retomar a sincronização."},
      {"title": "Databases not synchronised", "rec": "Check the database state in the AG. Resuming synchronisation may be needed."},
      {"title": "Bases de datos no sincronizadas", "rec": "Verificar el estado de la base en el AG. Puede ser necesario reanudar la sincronización."})
regra("AG005", {"title": "Relatório gerado a partir de réplica secundária", "rec": "Gerar o relatório na réplica primária para dados de sincronização completos."},
      {"title": "Report generated from a secondary replica", "rec": "Generate the report on the primary replica for complete synchronisation data."},
      {"title": "Informe generado desde una réplica secundaria", "rec": "Generar el informe en la réplica primaria para obtener datos de sincronización completos."})
regra("AG003", {"title": "Listener não configurado", "rec": "Configurar o AG Listener com VNN e IP dedicado para failover transparente.", "detail": "Listener não configurado ou não online. As aplicações não terão failover automático transparente.", "sql": ["Listeners configurados"]},
      {"title": "Listener not configured", "rec": "Configure the AG Listener with a VNN and dedicated IP for transparent failover.", "detail": "Listener not configured or not online. Applications will not get transparent automatic failover.", "sql": ["Configured listeners"]},
      {"title": "Listener no configurado", "rec": "Configurar el AG Listener con VNN e IP dedicada para un failover transparente.", "detail": "Listener no configurado o no online. Las aplicaciones no tendrán failover automático transparente.", "sql": ["Listeners configurados"]})
regra("AG004", {"title": "Always On saudável", "detail": "Todas as réplicas saudáveis e bases sincronizadas."},
      {"title": "Always On healthy", "detail": "All replicas healthy and databases synchronised."},
      {"title": "Always On saludable", "detail": "Todas las réplicas saludables y bases sincronizadas."})
regra("LOG001", {"title": "Erros críticos no SQL Server (severity >= 17)", "rec": "Investigar cada erro de severidade alta. Erros 823/824/825: I/O. Erro 9002: log cheio. Erro 17: insuficiência de recursos.", "sql": ["Erros recentes no errorlog"]},
      {"title": "Critical SQL Server errors (severity >= 17)", "rec": "Investigate each high-severity error. Errors 823/824/825: I/O. Error 9002: log full. Error 17: insufficient resources.", "sql": ["Recent errors in the errorlog"]},
      {"title": "Errores críticos en SQL Server (severity >= 17)", "rec": "Investigar cada error de severidad alta. Errores 823/824/825: I/O. Error 9002: log lleno. Error 17: recursos insuficientes.", "sql": ["Errores recientes en el errorlog"]})
regra("LOG002", {"title": "Erros de login repetidos", "rec": "Verificar a origem dos IPs. Considerar políticas de bloqueio e auditoria SQL."},
      {"title": "Repeated login errors", "rec": "Check the source IPs. Consider blocking policies and SQL auditing."},
      {"title": "Errores de login repetidos", "rec": "Verificar el origen de las IPs. Considerar políticas de bloqueo y auditoría SQL."})
regra("LOG003", {"title": "Eventos de failover detetados", "rec": "Verificar a causa do failover. Analisar os logs de Always On/Cluster para determinar se foi planeado.", "detail": "Evento(s) de failover detetados no log. O servidor pode ter sofrido uma interrupção."},
      {"title": "Failover events detected", "rec": "Check the failover cause. Analyse the Always On/Cluster logs to determine whether it was planned.", "detail": "Failover event(s) detected in the log. The server may have suffered an outage."},
      {"title": "Eventos de failover detectados", "rec": "Verificar la causa del failover. Analizar los logs de Always On/Cluster para determinar si fue planificado.", "detail": "Evento(s) de failover detectados en el log. El servidor puede haber sufrido una interrupción."})
regra("LOG004", {"title": "Logs OK", "detail": "Sem erros críticos nem eventos de failover detetados."},
      {"title": "Logs OK", "detail": "No critical errors or failover events detected."},
      {"title": "Logs OK", "detail": "Sin errores críticos ni eventos de failover detectados."})
regra("SEC001", {"title": "Score de segurança crítico (< 60)", "rec": "Rever todas as verificações falhadas. Priorizar as correções de severidade Critical e High."},
      {"title": "Critical security score (< 60)", "rec": "Review every failed check. Prioritise Critical and High severity fixes."},
      {"title": "Score de seguridad crítico (< 60)", "rec": "Revisar todas las verificaciones fallidas. Priorizar las correcciones de severidad Critical y High."})
regra("SEC002", {"title": "Score de segurança moderado (60-79)", "rec": "Rever as verificações falhadas e os avisos. Planear correções a curto prazo."},
      {"title": "Moderate security score (60-79)", "rec": "Review failed checks and warnings. Plan fixes in the short term."},
      {"title": "Score de seguridad moderado (60-79)", "rec": "Revisar las verificaciones fallidas y los avisos. Planificar correcciones a corto plazo."})
regra("SEC003", {"title": "Verificações críticas falhadas", "rec": "Corrigir os problemas críticos imediatamente: login sa, permissões excessivas, falta de auditoria."},
      {"title": "Critical checks failed", "rec": "Fix critical issues immediately: sa login, excessive permissions, missing auditing."},
      {"title": "Verificaciones críticas fallidas", "rec": "Corregir los problemas críticos de inmediato: login sa, permisos excesivos, falta de auditoría."})
regra("SEC004", {"title": "Segurança OK"}, {"title": "Security OK"}, {"title": "Seguridad OK"})
regra("SVC001", {"title": "SQL Server Engine parado", "rec": "Iniciar o serviço SQL Server imediatamente. Verificar os event logs para a causa da paragem.", "detail": "O serviço SQL Server Engine não está em execução. Todas as operações de base de dados estão indisponíveis."},
      {"title": "SQL Server Engine stopped", "rec": "Start the SQL Server service immediately. Check the event logs for the cause of the stop.", "detail": "The SQL Server Engine service is not running. All database operations are unavailable."},
      {"title": "SQL Server Engine detenido", "rec": "Iniciar el servicio SQL Server de inmediato. Revisar los event logs para la causa de la parada.", "detail": "El servicio SQL Server Engine no está en ejecución. Todas las operaciones de base de datos están indisponibles."})
regra("SVC002", {"title": "SQL Agent parado", "rec": "Iniciar o SQL Server Agent. Verificar se o startup type está em Automatic.", "detail": "O SQL Server Agent não está em execução. Os jobs de backup, manutenção e monitorização não correm.", "sql": ["Estado dos serviços SQL"]},
      {"title": "SQL Agent stopped", "rec": "Start the SQL Server Agent. Check that the startup type is Automatic.", "detail": "SQL Server Agent is not running. Backup, maintenance and monitoring jobs are not executing.", "sql": ["SQL services state"]},
      {"title": "SQL Agent detenido", "rec": "Iniciar el SQL Server Agent. Verificar que el startup type esté en Automatic.", "detail": "SQL Server Agent no está en ejecución. Los jobs de backup, mantenimiento y monitorización no se ejecutan.", "sql": ["Estado de los servicios SQL"]})
regra("SVC003", {"title": "Serviços automáticos parados", "rec": "Verificar porque estão parados serviços automáticos. Iniciar se necessário."},
      {"title": "Automatic services stopped", "rec": "Check why automatic services are stopped. Start them if needed."},
      {"title": "Servicios automáticos detenidos", "rec": "Verificar por qué hay servicios automáticos detenidos. Iniciarlos si es necesario."})
regra("SVC004", {"title": "Serviços OK", "detail": "Todos os serviços críticos em execução."},
      {"title": "Services OK", "detail": "All critical services running."},
      {"title": "Servicios OK", "detail": "Todos los servicios críticos en ejecución."})
regra("USR001", {"title": "Utilizadores órfãos detetados", "rec": "Remover os utilizadores órfãos ou associá-los a logins existentes com ALTER USER ... WITH LOGIN.", "sql": ["Utilizadores órfãos"]},
      {"title": "Orphaned users detected", "rec": "Remove orphaned users or map them to existing logins with ALTER USER ... WITH LOGIN.", "sql": ["Orphaned users"]},
      {"title": "Usuarios huérfanos detectados", "rec": "Eliminar los usuarios huérfanos o asociarlos a logins existentes con ALTER USER ... WITH LOGIN.", "sql": ["Usuarios huérfanos"]})
regra("USR002", {"title": "Permissões excessivas (sysadmin)", "rec": "Rever a necessidade de sysadmin. Usar roles mais restritas sempre que possível.", "sql": ["Membros de sysadmin"]},
      {"title": "Excessive permissions (sysadmin)", "rec": "Review the need for sysadmin. Use more restrictive roles whenever possible.", "sql": ["sysadmin members"]},
      {"title": "Permisos excesivos (sysadmin)", "rec": "Revisar la necesidad de sysadmin. Usar roles más restrictivos siempre que sea posible.", "sql": ["Miembros de sysadmin"]})
regra("USR003", {"title": "Logins sem sessão ligada", "rec": "Não desativar com base nesta lista: sem sessão agora não prova inatividade. Confirmar com auditoria de logins ou com as equipas aplicacionais."},
      {"title": "Logins with no connected session", "rec": "Do not disable based on this list: no session right now does not prove inactivity. Confirm with login auditing or with the application teams."},
      {"title": "Logins sin sesión conectada", "rec": "No desactivar en base a esta lista: sin sesión ahora no prueba inactividad. Confirmar con auditoría de logins o con los equipos de aplicación."})
regra("USR004", {"title": "Passwords fracas", "rec": "Alterar as passwords imediatamente. Implementar uma política de complexidade."},
      {"title": "Weak passwords", "rec": "Change the passwords immediately. Enforce a complexity policy."},
      {"title": "Contraseñas débiles", "rec": "Cambiar las contraseñas de inmediato. Implementar una política de complejidad."})
regra("USR005", {"title": "Utilizadores OK", "detail": "Nenhum utilizador órfão nem password fraca detetados."},
      {"title": "Users OK", "detail": "No orphaned user or weak password detected."},
      {"title": "Usuarios OK", "detail": "Ningún usuario huérfano ni contraseña débil detectados."})
regra("TDE001", {"title": "Certificados a expirar (< 30 dias)", "rec": "Renovar os certificados TDE imediatamente. Fazer backup do novo certificado e da chave privada.", "sql": ["Certificados TDE e datas de expiração"]},
      {"title": "Certificates expiring (< 30 days)", "rec": "Renew the TDE certificates immediately. Back up the new certificate and private key.", "sql": ["TDE certificates and expiry dates"]},
      {"title": "Certificados por expirar (< 30 días)", "rec": "Renovar los certificados TDE de inmediato. Hacer backup del nuevo certificado y de la clave privada.", "sql": ["Certificados TDE y fechas de expiración"]})
regra("TDE002", {"title": "Certificados a expirar (< 90 dias)", "rec": "Planear a renovação dos certificados TDE."},
      {"title": "Certificates expiring (< 90 days)", "rec": "Plan the TDE certificate renewal."},
      {"title": "Certificados por expirar (< 90 días)", "rec": "Planificar la renovación de los certificados TDE."})
regra("TDE003", {"title": "Bases de dados sem encriptação", "rec": "Avaliar se as bases contêm dados sensíveis que devam ser encriptados."},
      {"title": "Databases without encryption", "rec": "Assess whether the databases hold sensitive data that should be encrypted."},
      {"title": "Bases de datos sin cifrado", "rec": "Evaluar si las bases contienen datos sensibles que deban cifrarse."})
regra("TDE004", {"title": "TDE OK", "detail": "TDE ativo e certificados válidos."},
      {"title": "TDE OK", "detail": "TDE enabled and certificates valid."},
      {"title": "TDE OK", "detail": "TDE activo y certificados válidos."})
regra("OVW001", {"title": "CPU do SQL Server elevado", "rec": "Identificar as queries mais pesadas com sys.dm_exec_query_stats. Considerar o Resource Governor para limitar workloads.", "sql": ["Top queries por CPU"]},
      {"title": "SQL Server CPU high", "rec": "Identify the heaviest queries with sys.dm_exec_query_stats. Consider Resource Governor to cap workloads.", "sql": ["Top queries by CPU"]},
      {"title": "CPU de SQL Server elevado", "rec": "Identificar las queries más pesadas con sys.dm_exec_query_stats. Considerar Resource Governor para limitar workloads.", "sql": ["Top queries por CPU"]})
regra("OVW002", {"title": "CPU do SQL Server em alerta", "rec": "Monitorizar a evolução. Verificar se há queries ad hoc ou missing indexes a contribuir."},
      {"title": "SQL Server CPU on alert", "rec": "Monitor the trend. Check whether ad hoc queries or missing indexes are contributing."},
      {"title": "CPU de SQL Server en alerta", "rec": "Monitorizar la evolución. Verificar si hay queries ad hoc o missing indexes que contribuyan."})
regra("OVW003", {"title": "Memória do SQL Server elevada", "rec": "Verificar o max server memory. Identificar os memory clerks com maior consumo.", "sql": ["Top memory clerks"]},
      {"title": "SQL Server memory high", "rec": "Check max server memory. Identify the memory clerks with the highest consumption.", "sql": ["Top memory clerks"]},
      {"title": "Memoria de SQL Server elevada", "rec": "Verificar el max server memory. Identificar los memory clerks con mayor consumo.", "sql": ["Top memory clerks"]})
regra("OVW004", {"title": "Memória do SQL Server em alerta", "rec": "Monitorizar a evolução da utilização de memória."},
      {"title": "SQL Server memory on alert", "rec": "Monitor the memory usage trend."},
      {"title": "Memoria de SQL Server en alerta", "rec": "Monitorizar la evolución del uso de memoria."})
regra("OVW005", {"title": "Serviços críticos parados", "rec": "Verificar e reiniciar imediatamente os serviços SQL Server parados."},
      {"title": "Critical services stopped", "rec": "Check and restart the stopped SQL Server services immediately."},
      {"title": "Servicios críticos detenidos", "rec": "Verificar y reiniciar de inmediato los servicios SQL Server detenidos."})
regra("OVW006", {"title": "Bases de dados com problemas", "rec": "Analisar cada base na lista de problemas e tomar a ação corretiva."},
      {"title": "Databases with problems", "rec": "Analyse each database on the problem list and take corrective action."},
      {"title": "Bases de datos con problemas", "rec": "Analizar cada base en la lista de problemas y tomar la acción correctiva."})
regra("OVW007", {"title": "Falhas de backup detetadas", "rec": "Verificar o agendamento dos backups e corrigir as falhas."},
      {"title": "Backup gaps detected", "rec": "Check the backup schedule and fix the gaps."},
      {"title": "Gaps de backup detectados", "rec": "Verificar la programación de los backups y corregir los gaps."})
regra("OVW008", {"title": "Espaço crítico (filegroups)", "rec": "Expandir os ficheiros de dados ou adicionar um novo ficheiro ao filegroup."},
      {"title": "Critical space (filegroups)", "rec": "Grow the data files or add a new file to the filegroup."},
      {"title": "Espacio crítico (filegroups)", "rec": "Ampliar los archivos de datos o añadir un nuevo archivo al filegroup."})
regra("OVW009", {"title": "Overview OK", "detail": "Todos os indicadores do Overview estão dentro dos limites normais."},
      {"title": "Overview OK", "detail": "All Overview indicators are within normal limits."},
      {"title": "Overview OK", "detail": "Todos los indicadores del Overview están dentro de los límites normales."})
regra("SPC001", {"title": "Filegroups com espaço crítico (< 2% livre)", "rec": "Expandir os ficheiros de dados (ALTER DATABASE ... MODIFY FILE) ou adicionar novos ficheiros ao filegroup. Verificar se o auto-growth está ativo.", "sql": ["Ficheiros de dados da instância (alocado + maxsize + growth)", "Espaço usado por filegroup (correr no contexto da base: USE <db>)"]},
      {"title": "Filegroups at critical space (< 2% free)", "rec": "Grow the data files (ALTER DATABASE ... MODIFY FILE) or add files to the filegroup. Check that auto-growth is enabled.", "sql": ["Instance data files (allocated + maxsize + growth)", "Space used per filegroup (run in the database context: USE <db>)"]},
      {"title": "Filegroups con espacio crítico (< 2% libre)", "rec": "Ampliar los archivos de datos (ALTER DATABASE ... MODIFY FILE) o añadir nuevos archivos al filegroup. Verificar que el auto-growth esté activo.", "sql": ["Archivos de datos de la instancia (asignado + maxsize + growth)", "Espacio usado por filegroup (ejecutar en el contexto de la base: USE <db>)"]})
regra("SPC002", {"title": "Filegroups com espaço em alerta (2-5% livre)", "rec": "Planear a expansão dos ficheiros. Monitorizar o crescimento."},
      {"title": "Filegroups at warning space (2-5% free)", "rec": "Plan the file growth. Monitor the trend."},
      {"title": "Filegroups con espacio en alerta (2-5% libre)", "rec": "Planificar la ampliación de los archivos. Monitorizar el crecimiento."})
regra("SPC003", {"title": "Disco crítico (< 5% livre)", "rec": "Libertar espaço em disco com urgência. Mover ficheiros de dados para volumes com mais espaço."},
      {"title": "Disk critical (< 5% free)", "rec": "Free disk space urgently. Move data files to volumes with more space."},
      {"title": "Disco crítico (< 5% libre)", "rec": "Liberar espacio en disco con urgencia. Mover archivos de datos a volúmenes con más espacio."})
regra("SPC004", {"title": "Disco em alerta (5-10% livre)", "rec": "Planear a expansão de storage. Monitorizar a utilização."},
      {"title": "Disk on alert (5-10% free)", "rec": "Plan the storage expansion. Monitor usage."},
      {"title": "Disco en alerta (5-10% libre)", "rec": "Planificar la ampliación de storage. Monitorizar el uso."})
regra("SPC005", {"title": "Risco de overflow detetado", "rec": "Verificar o MAXSIZE dos ficheiros e o espaço disponível em disco."},
      {"title": "Overflow risk detected", "rec": "Check the files' MAXSIZE and the free disk space."},
      {"title": "Riesgo de overflow detectado", "rec": "Verificar el MAXSIZE de los archivos y el espacio disponible en disco."})
regra("SPC006", {"title": "Espaço OK", "detail": "Todos os filegroups e discos com espaço adequado."},
      {"title": "Space OK", "detail": "All filegroups and disks with adequate space."},
      {"title": "Espacio OK", "detail": "Todos los filegroups y discos con espacio adecuado."})

# rotulos fixos dos geradores
FIXOS = {
    "pt": {"none_detected": "Nenhum problema detetado.", "none_detected_mem": "Nenhum problema detetado. A configuração de memória está saudável.",
           "none_detected_cpu": "Nenhum problema detetado. A configuração de CPU está saudável.", "none_detected_jobs": "Nenhum problema detetado na configuração de jobs.",
           "no_failures_24h": "Nenhuma falha nas últimas 24 h.", "no_running_jobs": "Nenhum job em execução neste momento.", "no_backup_gap": "Nenhuma falha de backup detetada.",
           "no_failed_backup_jobs": "Nenhum job de backup falhado nas últimas 24 h.", "none_found": "Nenhum encontrado.", "no_volume": "Nenhum volume detetado.",
           "no_encrypted_db": "Nenhuma base de dados encriptada.", "no_recoverable": "Dados de espaço recuperável não disponíveis.", "yes": "Sim", "no": "Não",
           "status_critical": "CRÍTICO", "status_alert": "ALERTA", "status_healthy": "SAUDÁVEL",
           "h_job": "Job", "h_status": "Estado", "h_last_run": "Última exec.", "h_duration": "Duração", "h_next_run": "Próxima exec.", "h_enabled": "Ativo",
           "h_database": "Base de dados", "h_file": "Ficheiro", "h_read_ms": "Leitura ms", "h_write_ms": "Escrita ms", "h_cert": "Certificado", "h_expiry": "Expiração",
           "h_days_left": "Dias restantes", "h_db_service": "Base/Serviço", "h_problem": "Problema", "h_type": "Tipo", "h_gap_hours": "Horas de falha", "h_severity": "Severidade",
           "h_state": "Estado", "h_algorithm": "Algoritmo"},
    "en": {"none_detected": "No problem detected.", "none_detected_mem": "No problem detected. The memory configuration is healthy.",
           "none_detected_cpu": "No problem detected. The CPU configuration is healthy.", "none_detected_jobs": "No problem detected in the jobs configuration.",
           "no_failures_24h": "No failures in the last 24 h.", "no_running_jobs": "No job running right now.", "no_backup_gap": "No backup gap detected.",
           "no_failed_backup_jobs": "No failed backup job in the last 24 h.", "none_found": "None found.", "no_volume": "No volume detected.",
           "no_encrypted_db": "No encrypted database.", "no_recoverable": "Recoverable-space data not available.", "yes": "Yes", "no": "No",
           "status_critical": "CRITICAL", "status_alert": "ALERT", "status_healthy": "HEALTHY",
           "h_job": "Job", "h_status": "Status", "h_last_run": "Last run", "h_duration": "Duration", "h_next_run": "Next run", "h_enabled": "Enabled",
           "h_database": "Database", "h_file": "File", "h_read_ms": "Read ms", "h_write_ms": "Write ms", "h_cert": "Certificate", "h_expiry": "Expiry",
           "h_days_left": "Days left", "h_db_service": "Database/Service", "h_problem": "Problem", "h_type": "Type", "h_gap_hours": "Gap hours", "h_severity": "Severity",
           "h_state": "State", "h_algorithm": "Algorithm"},
    "es": {"none_detected": "Ningún problema detectado.", "none_detected_mem": "Ningún problema detectado. La configuración de memoria es saludable.",
           "none_detected_cpu": "Ningún problema detectado. La configuración de CPU es saludable.", "none_detected_jobs": "Ningún problema detectado en la configuración de jobs.",
           "no_failures_24h": "Sin fallos en las últimas 24 h.", "no_running_jobs": "Ningún job en ejecución en este momento.", "no_backup_gap": "Ningún gap de backup detectado.",
           "no_failed_backup_jobs": "Ningún job de backup fallido en las últimas 24 h.", "none_found": "Ninguno encontrado.", "no_volume": "Ningún volumen detectado.",
           "no_encrypted_db": "Ninguna base de datos cifrada.", "no_recoverable": "Datos de espacio recuperable no disponibles.", "yes": "Sí", "no": "No",
           "status_critical": "CRÍTICO", "status_alert": "ALERTA", "status_healthy": "SALUDABLE",
           "h_job": "Job", "h_status": "Estado", "h_last_run": "Última ejec.", "h_duration": "Duración", "h_next_run": "Próxima ejec.", "h_enabled": "Activo",
           "h_database": "Base de datos", "h_file": "Archivo", "h_read_ms": "Lectura ms", "h_write_ms": "Escritura ms", "h_cert": "Certificado", "h_expiry": "Expiración",
           "h_days_left": "Días restantes", "h_db_service": "Base/Servicio", "h_problem": "Problema", "h_type": "Tipo", "h_gap_hours": "Horas de gap", "h_severity": "Severidad",
           "h_state": "Estado", "h_algorithm": "Algoritmo"},
}
# overlay pt-BR: so' o que difere do pt-PT (ficheiro->arquivo, utilizador->usuario, equipa->equipe, detetado->detectado)
def _br(s):
    return (s.replace("ficheiros", "arquivos").replace("ficheiro", "arquivo").replace("Ficheiro", "Arquivo").replace("utilizadores", "usuários")
             .replace("Utilizadores", "Usuários").replace("utilizador", "usuário").replace("Utilizador", "Usuário").replace("equipas", "equipes")
             .replace("detetad", "detectad").replace("Detetad", "Detectad").replace("registado", "registrado").replace("otimizar", "otimizar")
             .replace("Monitorizar", "Monitorar").replace("monitorização", "monitoramento").replace("palavra-passe", "senha").replace("a correr", "rodando"))


def grupo_rep(loc: str) -> dict:
    g = dict(FIXOS[loc])
    for rid, tr in R.items():
        d = tr[loc]
        g[rid] = {k: v for k, v in d.items() if k in ("title", "rec", "detail")}
        if d.get("sql"):
            g[rid]["sql"] = {str(i): s for i, s in enumerate(d["sql"])}
    return g


def grupo_ptbr() -> dict:
    pt = grupo_rep("pt"); over: dict = {}
    for k, v in pt.items():
        if isinstance(v, str):
            if _br(v) != v: over[k] = _br(v)
        else:
            sub = {}
            for kk, vv in v.items():
                if kk == "sql":
                    s2 = {i: _br(s) for i, s in vv.items() if _br(s) != s}
                    if s2: sub["sql"] = s2
                elif _br(vv) != vv:
                    sub[kk] = _br(vv)
            if sub: over[k] = sub
    return over


PORTAL_EDITS = [
    # ponto unico de traducao (t global do WatcherI18N; recurso = texto original)
    ("""    function evaluateRules(rules, data) {
        const findings = [];
        for (const rule of rules) {
            try {
                if (rule.check(data)) {
                    const sev = typeof rule.severity === 'function' ? rule.severity(data) : rule.severity;
                    const det = typeof rule.detail === 'function' ? rule.detail(data) : rule.detail;
                    const rec = typeof rule.recommendation === 'function' ? rule.recommendation(data) : rule.recommendation;
                    const sq = typeof rule.sqlQueries === 'function' ? rule.sqlQueries(data) : (rule.sqlQueries || []);
                    findings.push({
                        id: rule.id,
                        title: rule.title,
                        severity: sev,
                        detail: det,
                        recommendation: rec,
                        diagLinks: rule.diagLinks || [],
                        sqlQueries: sq
                    });
""",
     """    // 2026-09-18 (i18n dos relatorios): traducao por id da regra, com o texto original como recurso.
    // Os detalhes DINAMICOS (funcoes com dados) ficam no original ate' ao lote 2b.
    function _repT(k, fb) { try { const v = (typeof t === 'function') ? t(k) : null; return (v && v !== k) ? v : fb; } catch (e) { return fb; } }
    function evaluateRules(rules, data) {
        const findings = [];
        for (const rule of rules) {
            try {
                if (rule.check(data)) {
                    const sev = typeof rule.severity === 'function' ? rule.severity(data) : rule.severity;
                    const det = typeof rule.detail === 'function' ? rule.detail(data) : rule.detail;
                    const rec = typeof rule.recommendation === 'function' ? rule.recommendation(data) : rule.recommendation;
                    const sq = typeof rule.sqlQueries === 'function' ? rule.sqlQueries(data) : (rule.sqlQueries || []);
                    const detEstatico = typeof rule.detail !== 'function' || rule.detail.length === 0;
                    findings.push({
                        id: rule.id,
                        title: _repT('rep.' + rule.id + '.title', rule.title),
                        severity: sev,
                        detail: detEstatico ? _repT('rep.' + rule.id + '.detail', det) : det,
                        recommendation: typeof rule.recommendation === 'string' ? _repT('rep.' + rule.id + '.rec', rec) : rec,
                        diagLinks: rule.diagLinks || [],
                        sqlQueries: (sq || []).map((q, i) => Object.assign({}, q, { title: _repT('rep.' + rule.id + '.sql.' + i, q.title) }))
                    });
""", 1),
    ("const statusLabel = hasCritical ? 'CRITICO' : hasWarning ? 'ALERTA' : 'SAUDAVEL';",
     "const statusLabel = hasCritical ? _repT('rep.status_critical', 'CRITICO') : hasWarning ? _repT('rep.status_alert', 'ALERTA') : _repT('rep.status_healthy', 'SAUDAVEL');", 13),
    ("""'<p style="color:#4ade80;">Nenhum problema detectado.</p>'""", """'<p style="color:#4ade80;">' + _repT('rep.none_detected', 'Nenhum problema detectado.') + '</p>'""", 9),
    ("""'<p style="color:#4ade80;font-size:14px;">Nenhum problema detectado.</p>'""", """'<p style="color:#4ade80;font-size:14px;">' + _repT('rep.none_detected', 'Nenhum problema detectado.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:14px;">Nenhum problema detectado. A configuracao de memoria esta saudavel.</p>'""", """'<p style="color:#4ade80;font-size:14px;">' + _repT('rep.none_detected_mem', 'Nenhum problema detectado. A configuracao de memoria esta saudavel.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:14px;">Nenhum problema detectado. A configuracao de CPU esta saudavel.</p>'""", """'<p style="color:#4ade80;font-size:14px;">' + _repT('rep.none_detected_cpu', 'Nenhum problema detectado. A configuracao de CPU esta saudavel.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:14px;">Nenhum problema detectado na configuracao de Jobs.</p>'""", """'<p style="color:#4ade80;font-size:14px;">' + _repT('rep.none_detected_jobs', 'Nenhum problema detectado na configuracao de Jobs.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> Nenhuma falha nas ultimas 24h.</p>'""", """'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> ' + _repT('rep.no_failures_24h', 'Nenhuma falha nas ultimas 24h.') + '</p>'""", 1),
    ("""'<p style="color:var(--color-text-tertiary);font-size:13px;">Nenhum job em execucao no momento.</p>'""", """'<p style="color:var(--color-text-tertiary);font-size:13px;">' + _repT('rep.no_running_jobs', 'Nenhum job em execucao no momento.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> Nenhum gap de backup detectado.</p>'""", """'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> ' + _repT('rep.no_backup_gap', 'Nenhum gap de backup detectado.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> Nenhum job de backup falhado nas ultimas 24h.</p>'""", """'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> ' + _repT('rep.no_failed_backup_jobs', 'Nenhum job de backup falhado nas ultimas 24h.') + '</p>'""", 1),
    ("""'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> Nenhum encontrado.</p>'""", """'<p style="color:#4ade80;font-size:13px;"><i class="fas fa-check-circle"></i> ' + _repT('rep.none_found', 'Nenhum encontrado.') + '</p>'""", 1),
    ("""'<p style="color:var(--color-text-tertiary);">Nenhuma database encriptada.</p>'""", """'<p style="color:var(--color-text-tertiary);">' + _repT('rep.no_encrypted_db', 'Nenhuma database encriptada.') + '</p>'""", 1),
    ("""'<p style="color:var(--color-text-tertiary);">Nenhum volume detectado.</p>'""", """'<p style="color:var(--color-text-tertiary);">' + _repT('rep.no_volume', 'Nenhum volume detectado.') + '</p>'""", 1),
    ("""'<p style="color:var(--color-text-tertiary);">Dados de espaco recuperavel nao disponiveis.</p>'""", """'<p style="color:var(--color-text-tertiary);">' + _repT('rep.no_recoverable', 'Dados de espaco recuperavel nao disponiveis.') + '</p>'""", 1),
    ("""j.enabled ? '<span style="color:#4ade80">Sim</span>' : '<span style="color:#f87171">Nao</span>'""", """j.enabled ? '<span style="color:#4ade80">' + _repT('rep.yes', 'Sim') + '</span>' : '<span style="color:#f87171">' + _repT('rep.no', 'Nao') + '</span>'""", 1),
    ("""j.enabled ? 'Sim' : '<span style="color:#f87171">Nao</span>'""", """j.enabled ? _repT('rep.yes', 'Sim') : '<span style="color:#f87171">' + _repT('rep.no', 'Nao') + '</span>'""", 1),
    # cabecalhos de tabela (dentro de template literals)
    ("""<tr><th>Job</th><th>Status</th><th>Ultima Exec.</th><th style="text-align:right">Duracao</th><th>Proxima Exec.</th><th>Ativo</th></tr>""",
     """<tr><th>${_repT('rep.h_job', 'Job')}</th><th>${_repT('rep.h_status', 'Status')}</th><th>${_repT('rep.h_last_run', 'Ultima Exec.')}</th><th style="text-align:right">${_repT('rep.h_duration', 'Duracao')}</th><th>${_repT('rep.h_next_run', 'Proxima Exec.')}</th><th>${_repT('rep.h_enabled', 'Ativo')}</th></tr>""", 1),
    ("""<tr><th>Database</th><th>Ficheiro</th><th style="text-align:right">Read ms</th><th style="text-align:right">Write ms</th><th>Status</th></tr>""",
     """<tr><th>${_repT('rep.h_database', 'Database')}</th><th>${_repT('rep.h_file', 'Ficheiro')}</th><th style="text-align:right">${_repT('rep.h_read_ms', 'Read ms')}</th><th style="text-align:right">${_repT('rep.h_write_ms', 'Write ms')}</th><th>${_repT('rep.h_status', 'Status')}</th></tr>""", 1),
    ("""<tr><th>Certificado</th><th>Expiracao</th><th>Dias Restantes</th><th>Status</th></tr>""",
     """<tr><th>${_repT('rep.h_cert', 'Certificado')}</th><th>${_repT('rep.h_expiry', 'Expiracao')}</th><th>${_repT('rep.h_days_left', 'Dias Restantes')}</th><th>${_repT('rep.h_status', 'Status')}</th></tr>""", 1),
    ("""<tr><th>Database/Servico</th><th>Problema</th></tr>""", """<tr><th>${_repT('rep.h_db_service', 'Database/Servico')}</th><th>${_repT('rep.h_problem', 'Problema')}</th></tr>""", 1),
    ("""<tr><th>Database</th><th>Tipo</th><th>Horas Gap</th><th>Severidade</th></tr>""",
     """<tr><th>${_repT('rep.h_database', 'Database')}</th><th>${_repT('rep.h_type', 'Tipo')}</th><th>${_repT('rep.h_gap_hours', 'Horas Gap')}</th><th>${_repT('rep.h_severity', 'Severidade')}</th></tr>""", 1),
    ("""<tr><th>Database</th><th>Estado</th><th>Algoritmo</th></tr>""", """<tr><th>${_repT('rep.h_database', 'Database')}</th><th>${_repT('rep.h_state', 'Estado')}</th><th>${_repT('rep.h_algorithm', 'Algoritmo')}</th></tr>""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Relatórios de diagnóstico em quatro idiomas (títulos, recomendações, detalhes fixos e títulos de SQL das 77\n"
    "  regras, mais os rótulos dos geradores)** (18/09). Tradução num único ponto, por id da regra, com o texto original\n"
    "  como recurso; os detalhes dinâmicos (frases montadas com dados) ficam para o lote seguinte. [tier: Std]\n\n",
    1,
)

TEST_SRC = r'''"""
2026-09-18 -- relatorios de diagnostico: cada regra tem chave rep.<ID>.title em pt/en/es; recomendacoes e detalhes
estaticos cobertos; rotulos fixos dos geradores passam por _repT.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LOC = {k: json.load(open(ROOT / f"static/i18n/{k}.json", encoding="utf-8")) for k in ("pt", "en", "es", "pt-BR")}


def _regras():
    out = []
    for m in re.finditer(r"^    const ([A-Z]+_RULES) = \[\n", PORTAL, re.M):
        ini = m.end(); fim = PORTAL.index("\n    ];", ini); bloco = PORTAL[ini:fim]
        for e in re.finditer(r"^        \{(.*?)^        \}", bloco, re.S | re.M):
            idm = re.search(r"\bid:\s*'([A-Z0-9]+)'", e.group(1))
            if idm:
                corpo = e.group(1)
                out.append((idm.group(1), bool(re.search(r"\brecommendation:\s*'[^']", corpo)), bool(re.search(r"\bdetail:\s*(?:\(\)\s*=>\s*)?'[^']", corpo)),
                            len(re.findall(r"\{\s*title:\s*'(?:[^'\\]|\\.)*',\s*sql:", corpo))))
    return out


def test_todas_as_regras_tem_titulo_e_o_que_e_estatico_tem_chave():
    regras = _regras()
    assert len(regras) >= 70
    for loc in ("pt", "en", "es"):
        g = LOC[loc]["rep"]
        for rid, tem_rec, tem_det, n_sql in regras:
            assert rid in g and g[rid].get("title"), (loc, rid)
            if tem_rec: assert g[rid].get("rec"), (loc, rid, "rec")
            if tem_det: assert g[rid].get("detail"), (loc, rid, "detail")
            for i in range(n_sql): assert g[rid].get("sql", {}).get(str(i)), (loc, rid, "sql", i)


def test_ponto_unico_de_traducao_e_rotulos():
    assert "function _repT(k, fb)" in PORTAL
    assert "title: _repT('rep.' + rule.id + '.title', rule.title)" in PORTAL
    assert "_repT('rep.' + rule.id + '.sql.' + i, q.title)" in PORTAL
    assert "const statusLabel = hasCritical ? 'CRITICO'" not in PORTAL
    assert PORTAL.count("_repT('rep.none_detected', 'Nenhum problema detectado.')") == 10
    for k in ("h_job", "h_file", "h_cert", "h_db_service", "h_gap_hours", "h_algorithm", "yes", "no"):
        assert f"_repT('rep.{k}'" in PORTAL, k


def test_pt_ao90_e_overlay_ptbr_so_diferencas():
    txt = json.dumps(LOC["pt"]["rep"], ensure_ascii=False)
    assert not re.search(r"detectad|actual\b|activ[oa]\b|correcç|excepç", txt)
    pt = LOC["pt"]["rep"]; over = LOC["pt-BR"].get("rep") or {}
    assert over
    def folhas(d, pref=""):
        for k, v in d.items():
            if isinstance(v, dict): yield from folhas(v, pref + k + ".")
            else: yield pref + k, v
    ptf = dict(folhas(pt))
    for k, v in folhas(over):
        assert k in ptf and ptf[k] != v, k
'''


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
    if "rep" in antes:
        raise SystemExit(f"[ABORT] {label}: grupo rep ja existe")
    corpo = texto.rstrip()
    if not corpo.endswith("}"):
        raise SystemExit(f"[ABORT] {label}: fim inesperado")
    corpo = corpo[:-1].rstrip()
    bloco = json.dumps(grupo, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    novo = corpo + ',\n  "rep": ' + bloco + "\n}\n"
    depois = json.loads(novo)
    assert {k: v for k, v in depois.items() if k != "rep"} == antes, f"{label}: o resto do ficheiro mudou"
    return novo


def _actualizar_guarda(texto_teste: str, portal_novo: str) -> str:
    """Recalcula a linha de base do teste de guarda com o varredor que vive no proprio teste."""
    ns: dict = {}
    # o helper novo _repT(...) e' i18n: o varredor da guarda passa a ignora-lo (senao contava os recursos em portugues)
    texto_teste = texto_teste.replace(r"_chT\(|data-i18n", r"_chT\(|_repT\(|data-i18n") if r"_repT\(" not in texto_teste else texto_teste
    # so' o varredor (comeca em "import re", acaba antes do primeiro teste) -- sem o cabecalho, que usa __file__
    exec(texto_teste[texto_teste.index("import re"):texto_teste.index("def test_texto_a_mao_nao_sobe")], ns)
    js, tags, _ = ns["contar_texto_a_mao"](portal_novo.replace("\r\n", "\n"))
    novo = re.sub(r"BASE_JS, BASE_TAGS = \d+, \d+", f"BASE_JS, BASE_TAGS = {js}, {tags}", texto_teste)
    return novo, js, tags


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    out = {"portal": _apply(portal, PORTAL_EDITS, "portal"), "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    for loc in ("pt", "en", "es"):
        out[loc] = _inserir_grupo(src[loc].read_bytes().decode("utf-8"), grupo_rep(loc), loc)
    out["ptbr"] = _inserir_grupo(src["ptbr"].read_bytes().decode("utf-8"), grupo_ptbr(), "pt-BR")
    if src["guarda"].exists():
        out["guarda"], js, tags = _actualizar_guarda(src["guarda"].read_bytes().decode("utf-8"), out["portal"])
    else:
        js = tags = None
    compile(TEST_SRC, str(REL["test"]), "exec")
    n_chaves = sum(1 for _ in json.dumps(grupo_rep("pt")).split('": "')) - 1
    print(f"[ok] portal {len(PORTAL_EDITS)} blocos (evaluateRules + 22 rotulos); rep: 77 regras, ~{n_chaves} textos por idioma; pt-BR overlay {len(grupo_ptbr())} regras/rotulos; guarda -> JS={js}, tags={tags}; changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_rep_i18n_20260918.py tests/unit/test_i18n_texto_a_mao_20260918.py tests/unit/test_i18n_parity.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
