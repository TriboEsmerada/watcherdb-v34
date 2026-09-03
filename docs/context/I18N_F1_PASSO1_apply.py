#!/usr/bin/env python3
"""Wave BUG-003 -- Lote F1: strings hardcoded do dashboard KPI + modais de backup/integridade -> chaves i18n.

Pedido owner 2026-09-03 (screenshot PT-BR da modal "Backup Delayed - Critico": "se esse tem os outros
devem estar assim tbm"). Traducoes: v33-i18n-linguist (lote F1); ordem dos lotes e padrao tecnico:
watcherdb-frontend-specialist. Padrao: `_kpiT(key, fallback)` (ja existia, linha ~34870) e novo
`_kpiTp(key, fallback, params)` para placeholders {n}. Chaves novas em namespace `kpi_adv.*`;
onde ja existia chave equivalente (modal.*, kpi_report.*, kpi_modal.*) reutiliza-se.

Identidade: owner (filesystem). Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F1_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F1_PASSO1_apply.py
Impacto: templates/watcherdb_portal.html + static/i18n/{pt,pt-BR,en,es}.json + CHANGELOG. Zero backend.
Rollback: git checkout -- templates/watcherdb_portal.html static/i18n docs/changelog/CHANGELOG.md
Verificacao: node --check (bloco JS do portal), pytest tests/unit/test_i18n_parity.py --no-cov,
             scripts/i18n_validate.py, browser em PT/PT-BR/EN/ES.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
HTML = "templates/watcherdb_portal.html"
CHG = "docs/changelog/CHANGELOG.md"

# ----------------------------------------------------------------------------
# Chaves novas: id -> (pt, en, es[, pt_br])   (pt_br so' quando difere do pt)
# ----------------------------------------------------------------------------
KEYS = {
    # cartoes do dashboard (subtitulos)
    "availability_card_subtitle": ("Estado das instâncias do ambiente", "Instance status across the environment", "Estado de las instancias del entorno"),
    "performance_card_subtitle": ("Carga e contenção", "Load and contention", "Carga y contención"),
    "disk_space_card_subtitle": ("Utilização e latência", "Usage and latency", "Utilización y latencia"),
    "backups_card_subtitle": ("Estado e falhas de backup", "Backup status and failures", "Estado y fallos de backup"),
    "disk_health_card_subtitle": ("Latência e TempDB", "Latency and TempDB", "Latencia y TempDB"),
    "ha_card_subtitle": ("Always On e Mirroring", "Always On and Mirroring", "Always On y Mirroring"),
    "fg_card_subtitle": ("Crescimento e logs", "Growth and logs", "Crecimiento y logs"),
    "blocking_card_subtitle": ("Contenção de sessões", "Session contention", "Contención de sesiones"),
    "integrity_card_subtitle": ("Corrupção e CHECKDB", "Corruption and CHECKDB", "Corrupción y CHECKDB"),
    # rows (label) e titulos de modal
    "instances_ok_modal_title": ("Instâncias OK", "Instances OK", "Instancias OK"),
    "instances_off_modal_title": ("Instâncias Offline", "Instances Offline", "Instancias Offline"),
    "badge_critical": ("crítico", "critical", "crítico"),
    "services_down_label": ("Instâncias c/ serviços em baixo", "Instances w/ services down", "Instancias con servicios caídos"),
    "services_down_modal_title": ("Serviços SQL em Baixo", "SQL Services Down", "Servicios SQL Caídos"),
    "cpu_critical_label": ("CPU crítico", "CPU critical", "CPU crítico"),
    "cpu_critical_modal_title": ("CPU Crítico - Instâncias com CPU Alto", "CPU Critical - Instances with High CPU", "CPU Crítico - Instancias con CPU Alto"),
    "memory_critical_label": ("Memória crítica", "Memory critical", "Memoria crítica"),
    "memory_critical_modal_title": ("Memória Crítica - Instâncias com Memória Alta", "Memory Critical - Instances with High Memory", "Memoria Crítica - Instancias con Memoria Alta"),
    "cpu_queue_label": ("Fila de CPU", "CPU queue", "Cola de CPU"),
    "cpu_queue_modal_title": ("Fila de CPU (sessões runnable)", "CPU queue (runnable sessions)", "Cola de CPU (sesiones runnable)"),
    "disk_fs_critical_label": ("Instâncias c/ discos críticos", "Instances w/ critical disks", "Instancias con discos críticos"),
    "disk_fs_critical_modal_title": ("DB Disk File System - Crítico", "DB Disk File System - Critical", "DB Disk File System - Crítico"),
    "disk_fs_warning_label": ("Instâncias c/ discos em aviso", "Instances w/ disks in warning", "Instancias con discos en aviso"),
    "disk_fs_warning_modal_title": ("DB Disk File System - Aviso", "DB Disk File System - Warning", "DB Disk File System - Aviso"),
    "disk_latency_critical_label": ("Drives c/ latência crítica", "Drives w/ critical latency", "Drives con latencia crítica"),
    "disk_latency_warning_label": ("Drives c/ latência em aviso", "Drives w/ latency warning", "Drives con latencia en aviso"),
    "backup_full_failed": ("Full falhou", "Full failed", "Full falló"),
    "backup_full_failed_modal_title": ("Backup FULL Falhou", "FULL Backup Failed", "Backup FULL Falló"),
    "backup_diff_failed": ("Diff falhou", "Diff failed", "Diff falló"),
    "backup_diff_failed_modal_title": ("Backup DIFF Falhou", "DIFF Backup Failed", "Backup DIFF Falló"),
    "backup_others_failed": ("Outros falharam", "Others failed", "Otros fallaron"),
    "backup_others_failed_modal_title": ("Outros Backups Falharam", "Other Backups Failed", "Otros Backups Fallaron"),
    "backup_log_failed": ("Log falhou", "Log failed", "Log falló"),
    "backup_log_failed_modal_title": ("Falha de Backup Log (não resolvida)", "Backup Log Failed (unresolved)", "Fallo de Backup Log (sin resolver)"),
    "backup_delayed_critical": ("Em atraso (crítico)", "Delayed (critical)", "Retrasado (crítico)"),
    "backup_delayed_critical_modal_title": ("Backup em Atraso - Crítico", "Backup Delayed - Critical", "Backup Retrasado - Crítico"),
    "backup_delayed_warning": ("Em atraso (aviso)", "Delayed (warning)", "Retrasado (aviso)"),
    "backup_delayed_warning_modal_title": ("Backup em Atraso - Aviso", "Backup Delayed - Warning", "Backup Retrasado - Aviso"),
    "diff_chain_stopped": ("Cadeia DIFF parada (FULL a cobrir)", "DIFF chain stopped (FULL to cover)", "Cadena DIFF parada (FULL por cubrir)"),
    "ag_system_gap_label": ("System DBs de nós AG s/ rotina", "System DBs on AG nodes w/o routine", "System DBs de nodos AG sin rutina"),
    "ag_system_gap_modal_title": ("System DBs de nós AG sem rotina", "System DBs on AG nodes without routine", "System DBs de nodos AG sin rutina"),
    "backup_damaged_label": ("Backup danificado", "Backup damaged", "Backup dañado"),
    "backup_damaged_modal_title": ("Backup Danificado", "Backup Damaged", "Backup Dañado"),
    "tempdb_critical_label": ("TempDB crítico", "TempDB critical", "TempDB crítico"),
    "tempdb_warning_label": ("TempDB aviso", "TempDB warning", "TempDB aviso"),
    "alwayson_unhealthy_label": ("Always On não saudável", "Always On unhealthy", "Always On no saludable"),
    "mirroring_unhealthy_label": ("Mirroring não saudável", "Mirroring unhealthy", "Mirroring no saludable"),
    "filegroups_critical_label": ("Filegroups críticos", "Filegroups critical", "Filegroups críticos"),
    "filegroups_warning_label": ("Filegroups aviso", "Filegroups warning", "Filegroups aviso"),
    "tlog_critical_label": ("Instâncias c/ t-log crítico", "Instances w/ critical t-log", "Instancias con t-log crítico"),
    "blocked_sessions_instances_label": ("Instâncias c/ sessões bloqueadas", "Instances w/ blocked sessions", "Instancias con sesiones bloqueadas"),
    "blocked_sessions_modal_title": ("Sessões Bloqueadas", "Blocked Sessions", "Sesiones Bloqueadas"),
    "blocked_users_label": ("Utilizadores bloqueados", "Blocked users", "Usuarios bloqueados", "Usuários bloqueados"),
    "blocked_users_modal_title": ("Utilizadores Bloqueados", "Blocked Users", "Usuarios Bloqueados", "Usuários Bloqueados"),
    "deadlocks_24h_modal_title": ("Deadlocks (últimas 24h)", "Deadlocks (last 24h)", "Deadlocks (últimas 24h)"),
    "integrity_p1_label": ("Corrompidas (suspect pages)", "Corrupted (suspect pages)", "Corruptas (suspect pages)"),
    "integrity_p1_modal_title": ("Integridade — Corrompidas (P1)", "Integrity — Corrupted (P1)", "Integridad — Corruptas (P1)"),
    "integrity_p3_label": ("Nunca validadas (CHECKDB)", "Never validated (CHECKDB)", "Nunca validadas (CHECKDB)"),
    "integrity_p3_modal_title": ("Integridade — Nunca Validadas (P3)", "Integrity — Never Validated (P3)", "Integridad — Nunca Validadas (P3)"),
    "integrity_p4_label": ("CHECKDB > 30 dias", "CHECKDB > 30 days", "CHECKDB > 30 días"),
    "integrity_p4_modal_title": ("Integridade — CHECKDB Antigo (P4)", "Integrity — Stale CHECKDB (P4)", "Integridad — CHECKDB Antiguo (P4)"),
    "integrity_unmeasurable_label": ("Não mensurável (recolha falhou)", "Not measurable (collection failed)", "No medible (falló la recolección)", "Não mensurável (coleta falhou)"),
    "integrity_unmeasurable_modal_title": ("Integridade — Não Mensurável (recolha falhou)", "Integrity — Not Measurable (collection failed)", "Integridad — No Medible (falló la recolección)", "Integridade — Não Mensurável (coleta falhou)"),
    "no_indicators_filter": ("Sem indicadores para o filtro selecionado.", "No indicators for the selected filter.", "Sin indicadores para el filtro seleccionado."),
    # cartoes da modal (labels)
    "type_label": ("Tipo", "Type", "Tipo"),
    "disk_usage_label": ("Uso Disco", "Disk usage", "Uso Disco"),
    "free_label": ("Livre", "Free", "Libre"),
    "blocked_sessions_label": ("Sessões Bloqueadas", "Blocked Sessions", "Sesiones Bloqueadas"),
    "last_label": ("Último", "Last", "Último"),
    "hours_ago": ("{n}h atrás", "{n}h ago", "hace {n}h"),
    "last_backup_label": ("Último Backup", "Last Backup", "Último Backup"),
    "overlap_label": ("Sobreposição", "Overlap", "Solapamiento"),
    "job_collision_has_failure": ("Com falha associada", "With associated failure", "Con fallo asociado"),
    "failures_label": ("Falhas", "Failures", "Fallos"),
    "last_job_run_label": ("Última Execução", "Last Run", "Última Ejecución"),
    "objects_label": ("Objetos", "Objects", "Objetos"),
    "verdict_label": ("Veredicto", "Verdict", "Veredicto"),
    "suspect_pages_label": ("Páginas suspeitas", "Suspect pages", "Páginas sospechosas"),
    "errors_word": ("erros", "errors", "errores"),
    "integrity_suspect_last_seen": (", último {date}", ", last {date}", ", último {date}"),
    "last_checkdb_label": ("Último CHECKDB", "Last CHECKDB", "Último CHECKDB"),
    "recommended_checksum": ("(recomendado CHECKSUM)", "(CHECKSUM recommended)", "(se recomienda CHECKSUM)"),
    "auto_shrink_on": ("AUTO_SHRINK ligado", "AUTO_SHRINK enabled", "AUTO_SHRINK activado"),
    "never": ("Nunca", "Never", "Nunca"),
    "recommended_fix": ("Solução recomendada", "Recommended fix", "Solución recomendada"),
    "no_collector_detail": ("Sem detalhe registado pelo coletor", "No detail recorded by the collector", "Sin detalle registrado por el colector"),
    "error_prefix": ("Erro {n}: ", "Error {n}: ", "Error {n}: "),
    "integrity_fix_p1_detail": ("Avaliar a extensão antes de decidir entre repair vs restore de backup íntegro. Várias DBs P1 na mesma instância = validar primeiro o storage/IO path.",
                                "Assess the extent before deciding repair vs restore from a clean backup. Multiple P1 DBs on the same instance = validate storage/IO path first.",
                                "Evaluar la extensión antes de decidir entre repair y restore desde un backup íntegro. Varias DBs P1 en la misma instancia = validar primero el storage/IO path."),
    "integrity_fix_p3_detail": ("Depois da 1.ª validação, incluir na rotina agendada (ex.: Ola Hallengren DatabaseIntegrityCheck). Nota AG: o CHECKDB num secundário legível não persiste o lastknowngood.",
                                "After the first validation, add it to the scheduled routine (e.g. Ola Hallengren DatabaseIntegrityCheck). AG note: CHECKDB on a readable secondary does not persist lastknowngood.",
                                "Después de la 1.ª validación, incluirla en la rutina programada (p. ej. Ola Hallengren DatabaseIntegrityCheck). Nota AG: CHECKDB en una secundaria legible no persiste el lastknowngood."),
    "reactivate_checkdb": ("Reativar o schedule da rotina de CHECKDB — última validação há {n} dias.", "Re-enable the CHECKDB routine schedule — last validation {n} days ago.", "Reactivar el schedule de la rutina de CHECKDB — última validación hace {n} días."),
    "backups_no_checksum": ("Backups sem CHECKSUM ({n} eventos <=7d): adicionar WITH CHECKSUM na rotina de backup.", "Backups without CHECKSUM ({n} events <=7d): add WITH CHECKSUM to the backup routine.", "Backups sin CHECKSUM ({n} eventos <=7d): añadir WITH CHECKSUM a la rutina de backup."),
    "action_open_sql_diag": ("Clique para abrir esta instância no SQL Diagnostics", "Click to open this instance in SQL Diagnostics", "Haga clic para abrir esta instancia en SQL Diagnostics"),
    "action_view_log_gaps": ("Clique para ver Gaps de Backup LOG", "Click to view LOG Backup Gaps", "Haga clic para ver los gaps de Backup LOG"),
    "action_view_full_gaps": ("Clique para ver Gaps de Backup FULL", "Click to view FULL Backup Gaps", "Haga clic para ver los gaps de Backup FULL"),
    "action_view_diff_gaps": ("Clique para ver Gaps de Backup DIFF", "Click to view DIFF Backup Gaps", "Haga clic para ver los gaps de Backup DIFF"),
    "action_open_backup_module": ("Clique para abrir o módulo Backup", "Click to open the Backup module", "Haga clic para abrir el módulo Backup"),
    "action_open_backup_module_jobs_disabled": ("Clique para abrir o módulo Backup (Jobs Desativados)", "Click to open the Backup module (Jobs Disabled)", "Haga clic para abrir el módulo Backup (Jobs Deshabilitados)"),
    # resumo / reconciliacao
    "recon_actionable": ("Critério revisto (council 01/09): {n} acionáveis", "Criteria revised (council 09/01): {n} actionable", "Criterio revisado (council 01/09): {n} accionables"),
    "recon_actionable_lines": ("Critério revisto (council 01/09): {n} linhas acionáveis", "Criteria revised (council 09/01): {n} actionable rows", "Criterio revisado (council 01/09): {n} filas accionables"),
    "recon_chain_reset": (" · {n} cadeia reiniciada (FULL cobre)", " · {n} chain reset (FULL covers)", " · {n} cadena reiniciada (FULL cubre)"),
    "recon_diff_stopped": (" · {n} cadeia DIFF parada (FULL a cobrir)", " · {n} DIFF chain stopped (FULL to cover)", " · {n} cadena DIFF parada (FULL por cubrir)"),
    "recon_ag_policy": (" · {n} política por-nó AG", " · {n} per-node AG policy", " · {n} política por nodo AG"),
    "showing_n_of_total_filter": ("Mostrando {n} de {total} (filtro: {filter})", "Showing {n} of {total} (filter: {filter})", "Mostrando {n} de {total} (filtro: {filter})"),
    "bases_lines_note": ("bases ({n} linhas por tipo — uma base com FULL+DIFF+LOG em atraso tem 1 linha por tipo)", "databases ({n} rows per type — a database with FULL+DIFF+LOG overdue has 1 row per type)", "bases de datos ({n} filas por tipo — una base con FULL+DIFF+LOG retrasados tiene 1 fila por tipo)"),
    "distinct_bases_note": ("Bases distintas (uma base pode ter mais de um tipo em atraso)", "Distinct databases (a database may have more than one type overdue)", "Bases de datos distintas (una base puede tener más de un tipo retrasado)"),
}

# ----------------------------------------------------------------------------
# Patches no template: (old, new, count)  count=None -> todas as ocorrencias (>=1)
# ----------------------------------------------------------------------------
def K(id_, fb=None):
    fb = KEYS[id_][0] if fb is None else fb
    return "_kpiT('kpi_adv.%s', %s)" % (id_, json.dumps(fb, ensure_ascii=False).replace('"', "'") if "'" not in fb else json.dumps(fb, ensure_ascii=False))

def KP(id_, params):
    return "_kpiTp('kpi_adv.%s', %s, %s)" % (id_, json.dumps(KEYS[id_][0], ensure_ascii=False).replace('"', "'"), params)

def LBL(old_label, id_):
    """<span ...disabled;">Label:</span> -> mesmo span com _kpiT."""
    return ('<span style="color: var(--color-text-disabled);">%s:</span>' % old_label,
            '<span style="color: var(--color-text-disabled);">${%s}:</span>' % K(id_))

HELPER_OLD = "        function _kpiT(key, fb) { try { const v = (typeof t === 'function') ? t(key) : null; return (v && v !== key) ? v : fb; } catch (e) { return fb; } }\n"
HELPER_NEW = HELPER_OLD + "        function _kpiTp(key, fb, p) { let s = _kpiT(key, fb); Object.keys(p || {}).forEach(k => { s = s.split('{' + k + '}').join(p[k]); }); return s; }  // placeholders {n} (lote F1 2026-09-03)\n"

PATCHES = [
    (HELPER_OLD, HELPER_NEW, 1),
    # --- cartoes / rows do dashboard KPI -----------------------------------
    ("_advCard('fa-server', 'Disponibilidade', 'Estado das instancias do ambiente',",
     "_advCard('fa-server', _kpiT('kpi_report.cat_availability', 'Disponibilidade'), %s," % K("availability_card_subtitle"), 1),
    ("_advRow(C.ok, 'Online', online, '', 'instance-availability', 'Instances OK') + _advRow(off > 0 ? C.crit : C.gray, 'Offline', off, off > 0 ? 'critico' : '', 'instance-availability', 'Instances Off') +",
     "_advRow(C.ok, 'Online', online, '', 'instance-availability', %s) + _advRow(off > 0 ? C.crit : C.gray, 'Offline', off, off > 0 ? %s : '', 'instance-availability', %s) +" % (K("instances_ok_modal_title"), K("badge_critical"), K("instances_off_modal_title")), 1),
    ("'Instancias c/ servicos em baixo', ev(ss, 'down_count'), '', 'service-status', 'SQL Services Down')",
     "%s, ev(ss, 'down_count'), '', 'service-status', %s)" % (K("services_down_label"), K("services_down_modal_title")), 1),
    ("_advCard('fa-gauge-high', 'Performance', 'Carga e contencao',",
     "_advCard('fa-gauge-high', _kpiT('kpi_report.cat_performance', 'Performance'), %s," % K("performance_card_subtitle"), 1),
    ("'CPU critico', ev(cpu, 'count'), '', 'cpu-critical', 'CPU Critico - Instancias com CPU Alto')",
     "%s, ev(cpu, 'count'), '', 'cpu-critical', %s)" % (K("cpu_critical_label"), K("cpu_critical_modal_title")), 1),
    ("'Memoria critico', ev(mem, 'count'), '', 'memory-critical', 'Memoria Critico - Instancias com Memoria Alta')",
     "%s, ev(mem, 'count'), '', 'memory-critical', %s)" % (K("memory_critical_label"), K("memory_critical_modal_title")), 1),
    ("'Fila de CPU', ev(pa, 'count'), '', 'processes-alarm', 'CPU queue (runnable sessions)')",
     "%s, ev(pa, 'count'), '', 'processes-alarm', %s)" % (K("cpu_queue_label"), K("cpu_queue_modal_title")), 1),
    ("_advCard('fa-hard-drive', 'Espaco em Disco', 'Utilizacao e latencia',",
     "_advCard('fa-hard-drive', _kpiT('kpi_report.cat_disk_space', 'Espaço em Disco'), %s," % K("disk_space_card_subtitle"), 1),
    ("'Instancias c/ discos criticos', ev(dfs, 'critical_count'), '', 'disk-file-system-critical', 'DB Disk File System - Crítico')",
     "%s, ev(dfs, 'critical_count'), '', 'disk-file-system-critical', %s)" % (K("disk_fs_critical_label"), K("disk_fs_critical_modal_title")), 1),
    ("'Instancias c/ discos em aviso', ev(dfs, 'warning_count'), '', 'disk-file-system-warning', 'DB Disk File System - Warning')",
     "%s, ev(dfs, 'warning_count'), '', 'disk-file-system-warning', %s)" % (K("disk_fs_warning_label"), K("disk_fs_warning_modal_title")), 1),
    ("'Drives c/ latencia critica', ev(dl, 'critical_count'), '', 'disk-latency-critical', 'Disk Latency Critical - Drives com Alta Latencia')",
     "%s, ev(dl, 'critical_count'), '', 'disk-latency-critical', _kpiT('modal.disk_latency_critical', 'Disk Latency Critical - Drives com Alta Latência'))" % K("disk_latency_critical_label"), 2),
    ("_advCard('fa-shield-halved', 'Backups', 'Estado e falhas de backup',",
     "_advCard('fa-shield-halved', _kpiT('kpi_report.cat_backups', 'Backups'), %s," % K("backups_card_subtitle"), 1),
    ("'Full falhou', ev(bk, 'full_failed_count'), '', 'backup-failed', 'Full Failed', 'FULL')",
     "%s, ev(bk, 'full_failed_count'), '', 'backup-failed', %s, 'FULL')" % (K("backup_full_failed"), K("backup_full_failed_modal_title")), 1),
    ("'Diff falhou', ev(bk, 'diff_failed_count'), '', 'backup-failed', 'Diff Failed', 'DIFF')",
     "%s, ev(bk, 'diff_failed_count'), '', 'backup-failed', %s, 'DIFF')" % (K("backup_diff_failed"), K("backup_diff_failed_modal_title")), 1),
    ("'Outros falhou', ev(bk, 'other_failed_count'), '', 'backup-failed', 'Others Failed', 'OTHER')",
     "%s, ev(bk, 'other_failed_count'), '', 'backup-failed', %s, 'OTHER')" % (K("backup_others_failed"), K("backup_others_failed_modal_title")), 1),
    ("'Log falhou', ev(bk, 'log_failed_count'), '', 'backup-log-failed', 'Backup Log Failed (Unresolved)')",
     "%s, ev(bk, 'log_failed_count'), '', 'backup-log-failed', %s)" % (K("backup_log_failed"), K("backup_log_failed_modal_title")), 1),
    ("'Em atraso (critico)', ev(bk, 'delayed_critical_count'), '', 'backup-delayed', 'Backup Delayed - Critico', 'CLASS:actionable_critical')",
     "%s, ev(bk, 'delayed_critical_count'), '', 'backup-delayed', %s, 'CLASS:actionable_critical')" % (K("backup_delayed_critical"), K("backup_delayed_critical_modal_title")), 1),
    ("'Em atraso (aviso)', ev(bk, 'delayed_warning_count'), '', 'backup-delayed', 'Backup Delayed - Aviso', 'CLASS:actionable_warning')",
     "%s, ev(bk, 'delayed_warning_count'), '', 'backup-delayed', %s, 'CLASS:actionable_warning')" % (K("backup_delayed_warning"), K("backup_delayed_warning_modal_title")), 1),
    ("'Cadeia DIFF parada (FULL a cobrir)', ev(bk, 'diff_schedule_stopped_count'), '', 'backup-delayed', 'Cadeia DIFF parada (FULL a cobrir)', 'CLASS:diff_schedule_stopped')",
     "%s, ev(bk, 'diff_schedule_stopped_count'), '', 'backup-delayed', %s, 'CLASS:diff_schedule_stopped')" % (K("diff_chain_stopped"), K("diff_chain_stopped")), 1),
    ("'System DBs de nós AG s/ rotina', ev(bk, 'ag_system_gap_count'), '', 'backup-delayed', 'System DBs de nos AG sem rotina', 'CLASS:ag_system_gap')",
     "%s, ev(bk, 'ag_system_gap_count'), '', 'backup-delayed', %s, 'CLASS:ag_system_gap')" % (K("ag_system_gap_label"), K("ag_system_gap_modal_title")), 1),
    ("_advRow(C.crit, 'Backup danificado', ev(bk, 'is_damaged_count'), '', '', 'Backup Damaged')",
     "_advRow(C.crit, %s, ev(bk, 'is_damaged_count'), '', '', %s)" % (K("backup_damaged_label"), K("backup_damaged_modal_title")), 1),
    ("_advCard('fa-heart-pulse', 'Saude do Disco', 'Latencia e TempDB',",
     "_advCard('fa-heart-pulse', _kpiT('kpi_report.cat_disk_health', 'Saúde do Disco'), %s," % K("disk_health_card_subtitle"), 1),
    ("'Drives c/ latencia em aviso', ev(dl, 'warning_count'), '', 'disk-latency-warning', 'Disk Latency Warning - Drives com Latencia em Aviso')",
     "%s, ev(dl, 'warning_count'), '', 'disk-latency-warning', _kpiT('modal.disk_latency_warning', 'Disk Latency Warning - Drives com Latência Elevada'))" % K("disk_latency_warning_label"), 1),
    ("'TempDB critico', ev(td, 'critical_count'), '', 'tempdb-status-critical', 'TempDB - Disco Crítico')",
     "%s, ev(td, 'critical_count'), '', 'tempdb-status-critical', _kpiT('modal.tempdb_critical', 'TempDB - Disco Crítico'))" % K("tempdb_critical_label"), 1),
    ("'TempDB aviso', ev(td, 'warning_count'), '', 'tempdb-status-warning', 'TempDB - Disco Atenção')",
     "%s, ev(td, 'warning_count'), '', 'tempdb-status-warning', _kpiT('modal.tempdb_warning', 'TempDB - Disco Atenção'))" % K("tempdb_warning_label"), 1),
    ("_advCard('fa-sitemap', 'Alta Disponibilidade', 'AlwaysOn e Mirroring',",
     "_advCard('fa-sitemap', _kpiT('kpi_report.cat_high_availability', 'Alta Disponibilidade'), %s," % K("ha_card_subtitle"), 1),
    ("'AlwaysOn não saudável', ev(ao, 'unhealthy_count'), '', 'always-on', 'DB Always On - Não Saudável')",
     "%s, ev(ao, 'unhealthy_count'), '', 'always-on', _kpiT('modal.alwayson_unhealthy', 'DB Always On - Não Saudável'))" % K("alwayson_unhealthy_label"), 1),
    ("'Mirroring não saudável', ev(mi, 'unhealthy_count'), '', 'mirroring', 'DB Mirroring - Não Saudável')",
     "%s, ev(mi, 'unhealthy_count'), '', 'mirroring', _kpiT('modal.mirroring_unhealthy', 'DB Mirroring - Não Saudável'))" % K("mirroring_unhealthy_label"), 1),
    ("_advCard('fa-layer-group', 'Filegroups & Transaction Log', 'Crescimento e logs',",
     "_advCard('fa-layer-group', _kpiT('kpi_report.cat_filegroups_tlog', 'Filegroups & Transaction Log'), %s," % K("fg_card_subtitle"), 1),
    ("'Filegroups criticos', ev(fg, 'critical_items_total'), '', 'filegroup-usage-critical', 'FileGroups Usage - Critical')",
     "%s, ev(fg, 'critical_items_total'), '', 'filegroup-usage-critical', _kpiT('modal.filegroup_critical', 'FileGroups Usage - Critical'))" % K("filegroups_critical_label"), 1),
    ("'Filegroups aviso', ev(fg, 'warning_items_total'), '', 'filegroup-usage-warning', 'FileGroups Usage - Warning')",
     "%s, ev(fg, 'warning_items_total'), '', 'filegroup-usage-warning', _kpiT('modal.filegroup_warning', 'FileGroups Usage - Warning'))" % K("filegroups_warning_label"), 1),
    ("'Instancias c/ t-log critico', ev(tl, 'critical_count'), '', 'transaction-logs-critical', 'DB Transaction Logs - Crítico')",
     "%s, ev(tl, 'critical_count'), '', 'transaction-logs-critical', _kpiT('modal.tlog_critical', 'DB Transaction Logs - Crítico'))" % K("tlog_critical_label"), 1),
    ("_advCard('fa-lock', 'Bloqueios & Deadlocks', 'Contencao de sessoes',",
     "_advCard('fa-lock', _kpiT('kpi_report.cat_blocking', 'Bloqueios & Deadlocks'), %s," % K("blocking_card_subtitle"), 1),
    ("'Instancias c/ sessoes bloqueadas', ev(bsx, 'count'), '', 'blocked-sessions', 'Blocked Sessions')",
     "%s, ev(bsx, 'count'), '', 'blocked-sessions', %s)" % (K("blocked_sessions_instances_label"), K("blocked_sessions_modal_title")), 1),
    ("'Utilizadores bloqueados', ev(bu, 'count'), '', 'blocked-users', 'Blocked Users')",
     "%s, ev(bu, 'count'), '', 'blocked-users', %s)" % (K("blocked_users_label"), K("blocked_users_modal_title")), 1),
    ("'Deadlocks 24h', ev(dlk, 'count'), '', 'deadlocks', 'Deadlocks (Last 24h)')",
     "'Deadlocks 24h', ev(dlk, 'count'), '', 'deadlocks', %s)" % K("deadlocks_24h_modal_title"), 1),
    ("_advCard('fa-file-shield', 'Integridade', 'Corrupcao e CHECKDB',",
     "_advCard('fa-file-shield', _kpiT('kpi_report.cat_integrity', 'Integridade'), %s," % K("integrity_card_subtitle"), 1),
    ("'Corrompidas (suspect pages)', igNA ? 'N/D' : ev(ig, 'p1_count'), ev(ig, 'p1_count') > 0 ? 'critico' : '', 'integrity-p1', 'Integridade — Corrompidas (P1)')",
     "%s, igNA ? 'N/D' : ev(ig, 'p1_count'), ev(ig, 'p1_count') > 0 ? %s : '', 'integrity-p1', %s)" % (K("integrity_p1_label"), K("badge_critical"), K("integrity_p1_modal_title")), 1),
    ("'Nunca validadas (CHECKDB)', igNA ? 'N/D' : ev(ig, 'p3_count'), '', 'integrity-p3', 'Integridade — Nunca Validadas (P3)')",
     "%s, igNA ? 'N/D' : ev(ig, 'p3_count'), '', 'integrity-p3', %s)" % (K("integrity_p3_label"), K("integrity_p3_modal_title")), 1),
    ("'CHECKDB > 30 dias', igNA ? 'N/D' : ev(ig, 'p4_count'), '', 'integrity-p4', 'Integridade — CHECKDB Antigo (P4)')",
     "%s, igNA ? 'N/D' : ev(ig, 'p4_count'), '', 'integrity-p4', %s)" % (K("integrity_p4_label"), K("integrity_p4_modal_title")), 1),
    ("'Nao mensuravel (coleta falhou)', igNA ? 'N/D' : n(ig.unmeasurable_count), '', 'integrity-unmeasurable', 'Integridade — Nao Mensuravel (coleta falhou)')",
     "%s, igNA ? 'N/D' : n(ig.unmeasurable_count), '', 'integrity-unmeasurable', %s)" % (K("integrity_unmeasurable_label"), K("integrity_unmeasurable_modal_title")), 1),
    ('`<div class="kpiadv-nodata">Sem indicadores para o filtro selecionado.</div>`',
     '`<div class="kpiadv-nodata">${%s}</div>`' % K("no_indicators_filter"), 1),
    # --- cartoes dentro das modais ------------------------------------------
    LBL("Uso Disco", "disk_usage_label") + (1,),
    LBL("Livre", "free_label") + (None,),
    LBL("Sessoes Bloqueadas", "blocked_sessions_label") + (1,),
    LBL("Tipo", "type_label") + (None,),
    LBL("Ultimo", "last_label") + (None,),
    ("`<span style=\"color: var(--color-text-tertiary);\">(${hoursSince}h atras)</span>`",
     "`<span style=\"color: var(--color-text-tertiary);\">(${%s})</span>`" % KP("hours_ago", "{ n: hoursSince }"), 1),
    ("</i>Snapshot: ${fmtDt(snapshotTs)}</div>", "</i>${_kpiT('kpi_modal.snapshot_label', 'Snapshot')}: ${fmtDt(snapshotTs)}</div>", 1),
    LBL("Ultimo Backup", "last_backup_label") + (1,),
    LBL("Sobreposicao", "overlap_label") + (1,),
    ('<i class="fas fa-exclamation-triangle"></i> Com falha associada</span>',
     '<i class="fas fa-exclamation-triangle"></i> \' + %s + \'</span>' % K("job_collision_has_failure"), 1),
    LBL("Falhas", "failures_label") + (1,),
    LBL("Ultima Execucao", "last_job_run_label") + (1,),
    LBL("Objetos", "objects_label") + (1,),
    ('<span style="color: var(--color-text-disabled);">Estado:</span>',
     '<span style="color: var(--color-text-disabled);">${_kpiT(\'kpi_modal.status\', \'Estado\')}:</span>', None),
    ("igChkIsSentinel ? 'Nunca' :", "igChkIsSentinel ? %s :" % K("never"), 1),
    ("igFixes.push('Avaliar extensao antes de decidir repair vs restore de backup integro. Varias DBs P1 na mesma instancia = validar storage/IO path primeiro.');",
     "igFixes.push(%s);" % K("integrity_fix_p1_detail"), 1),
    ("igFixes.push('Depois da 1a validacao, incluir na rotina agendada (ex: Ola Hallengren DatabaseIntegrityCheck). Nota AG: CHECKDB em secundario legivel nao persiste lastknowngood.');",
     "igFixes.push(%s);" % K("integrity_fix_p3_detail"), 1),
    ("igFixes.push(`Reactivar o schedule da rotina de CHECKDB — ultima validacao ha ${igDays} dias.`);",
     "igFixes.push(%s);" % KP("reactivate_checkdb", "{ n: igDays }"), 1),
    ("igFixes.push(`Backups sem CHECKSUM (${igNoChk} eventos <=7d): adicionar WITH CHECKSUM na rotina de backup.`);",
     "igFixes.push(%s);" % KP("backups_no_checksum", "{ n: igNoChk }"), 1),
    ("`${igErrNum != null && igErrNum !== 0 ? `Erro ${igErrNum}: ` : ''}${igErrMsg || 'Sem detalhe registado pelo coletor'}`",
     "`${igErrNum != null && igErrNum !== 0 ? %s : ''}${igErrMsg || %s}`" % (KP("error_prefix", "{ n: igErrNum }"), K("no_collector_detail")), 1),
    ('<i class="fas fa-wrench"></i> Solucao recomendada</div>', '<i class="fas fa-wrench"></i> ${%s}</div>' % K("recommended_fix"), 1),
    LBL("Veredicto", "verdict_label") + (1,),
    ('<span style="color: ${getSevTokens(\'CRITICAL\').fill};">Paginas suspeitas:</span>',
     '<span style="color: ${getSevTokens(\'CRITICAL\').fill};">${%s}:</span>' % K("suspect_pages_label"), 1),
    ("(${igSuspErrs} erros${igLastSusp ? ', ultimo ' + String(igLastSusp).substring(0, 16).replace('T', ' ') : ''})",
     "(${igSuspErrs} ${%s}${igLastSusp ? %s : ''})" % (K("errors_word"), KP("integrity_suspect_last_seen", "{ date: String(igLastSusp).substring(0, 16).replace('T', ' ') }")), 1),
    LBL("Ultimo CHECKDB", "last_checkdb_label") + (1,),
    ("(recomendado CHECKSUM)</span>", "${%s}</span>" % K("recommended_checksum"), 1),
    ('<span style="color: ${getSevTokens(\'WARNING\').fill};">AUTO_SHRINK ligado</span>',
     '<span style="color: ${getSevTokens(\'WARNING\').fill};">${%s}</span>' % K("auto_shrink_on"), None),
    ("let actionText = 'Clique para abrir esta instancia no SQL Diagnostics';", "let actionText = %s;" % K("action_open_sql_diag"), 1),
    ("actionText = 'Clique para ver Gaps de LOG Backup';", "actionText = %s;" % K("action_view_log_gaps"), 1),
    ("actionText = 'Clique para ver Gaps de FULL Backup';", "actionText = %s;" % K("action_view_full_gaps"), 1),
    ("actionText = 'Clique para ver Gaps de DIFF Backup';", "actionText = %s;" % K("action_view_diff_gaps"), 1),
    ("actionText = 'Clique para abrir o modulo Backup';", "actionText = %s;" % K("action_open_backup_module"), 1),
    ("actionText = 'Clique para abrir o modulo Backup (Jobs Disabled)';", "actionText = %s;" % K("action_open_backup_module_jobs_disabled"), 1),
    # --- resumo / reconciliacao ---------------------------------------------
    ("+ `Critério revisto (council 01/09): <strong>${_dcCount.actionable}</strong> accionáveis`\n"
     "                            + ` · ${_dcCount.chain_reset} cadeia reiniciada (FULL cobre)`\n"
     "                            + ` · ${_dcCount.diff_schedule_stopped} cadeia DIFF parada (FULL a cobrir)`\n"
     "                            + ` · ${_dcCount.ag_system_gap} política por-nó AG</div>`;",
     "+ %s\n"
     "                            + %s\n"
     "                            + %s\n"
     "                            + %s + `</div>`;" % (KP("recon_actionable", "{ n: '<strong>' + _dcCount.actionable + '</strong>' }"),
                                                       KP("recon_chain_reset", "{ n: _dcCount.chain_reset }"),
                                                       KP("recon_diff_stopped", "{ n: _dcCount.diff_schedule_stopped }"),
                                                       KP("recon_ag_policy", "{ n: _dcCount.ag_system_gap }")), 1),
    ("summaryDiv.innerHTML = `Mostrando <strong style=\"color: var(--color-text-link);\">${visibleCount}</strong> de ${originalCount} (filtro: <strong style=\"color: var(--color-text-link);\">${filterLabel}</strong>)` + reconLine;",
     "summaryDiv.innerHTML = %s + reconLine;" % KP("showing_n_of_total_filter", "{ n: '<strong style=\"color: var(--color-text-link);\">' + visibleCount + '</strong>', total: originalCount, filter: '<strong style=\"color: var(--color-text-link);\">' + filterLabel + '</strong>' }"), 1),
    ("? `<strong style=\"color: var(--color-text-link);\">${_visBases.size}</strong> bases (${visibleCount} linhas por tipo — uma base com FULL+DIFF+LOG em atraso tem 1 linha por tipo)`",
     "? `<strong style=\"color: var(--color-text-link);\">${_visBases.size}</strong> ${%s}`" % KP("bases_lines_note", "{ n: visibleCount }"), 1),
    ("+ `Critério revisto (council 01/09): <strong>${_dc.actionable}</strong> linhas accionáveis`\n"
     "                        + ` · ${_dc.diff_schedule_stopped} cadeia DIFF parada (FULL a cobrir)`\n"
     "                        + ` · ${_dc.ag_system_gap} política por-nó AG${_chainLink}</div>`;",
     "+ %s\n"
     "                        + %s\n"
     "                        + %s + `${_chainLink}</div>`;" % (KP("recon_actionable_lines", "{ n: '<strong>' + _dc.actionable + '</strong>' }"),
                                                               KP("recon_diff_stopped", "{ n: _dc.diff_schedule_stopped }"),
                                                               KP("recon_ag_policy", "{ n: _dc.ag_system_gap }")), 1),
    ("typeTotalEl.previousElementSibling.textContent = 'Bases distintas (uma base pode ter mais de um tipo em atraso)';",
     "typeTotalEl.previousElementSibling.textContent = %s;" % K("distinct_bases_note"), 1),
    ("_envTotEl.previousElementSibling.textContent = 'Total (bases)';",
     "_envTotEl.previousElementSibling.textContent = 'Total ' + _kpiT('kpi_modal.total_bases_suffix', '(bases)');", 1),
    ("summaryDiv.innerHTML = `Mostrando <strong style=\"color: #a78bfa;\">${visibleCount}</strong> de ${originalCount} (filtro: <strong style=\"color: #a78bfa;\">${filterLabel}</strong>)`;",
     "summaryDiv.innerHTML = %s;" % KP("showing_n_of_total_filter", "{ n: '<strong style=\"color: #a78bfa;\">' + visibleCount + '</strong>', total: originalCount, filter: '<strong style=\"color: #a78bfa;\">' + filterLabel + '</strong>' }"), 1),
]

CHANGELOG_ENTRY = """- **i18n lote F1 (wave BUG-003): dashboard KPI e modais de backup/integridade deixam de ter
  texto português hardcoded** (pedido owner 03/09 ao ver a modal em PT-BR: "se esse tem os outros
  devem estar assim tbm"). ~110 strings dos cartões `_advRow`/`_advCard`, dos cartões das modais
  (Último, Tipo, Falhas, Veredicto, CHECKDB, solução recomendada…), das acções de clique e das
  linhas de resumo/reconciliação passam a chaves `kpi_adv.*` (novas, 4 locales) ou a chaves já
  existentes (`modal.*`, `kpi_report.*`, `kpi_modal.*`). Helper `_kpiTp` para placeholders `{n}`.
  Acentuação corrigida em todos os fallbacks; "Outros falhou" → "Outros falharam"; "accionáveis"
  → "acionáveis" (AO90). Lotes seguintes (F2 títulos dos cartões principais, F3 ajudas "?", F4
  acentos na documentação dos KPIs, F5 relatórios, F6 diagnósticos) planeados pelo
  frontend-specialist. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8")
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def norm(s, nl):
    return s.replace("\n", nl) if nl != "\n" else s


def add_namespace(path: Path, ns: str, entries: dict):
    """Insere "ns": {...} antes do '}' final por TEXTO (pt.json tem chaves duplicadas -- sem round-trip)."""
    raw, nl = read(path)
    body = raw.rstrip()
    assert body.endswith("}"), path
    if '"%s": {' % ns in raw:
        raise SystemExit(f"[ABORT] {path.name}: namespace {ns} ja existe")
    inner = ",".join(nl + '    ' + json.dumps(k, ensure_ascii=False) + ": " + json.dumps(v, ensure_ascii=False) for k, v in entries.items())
    block = "," + nl + '  "%s": {' % ns + inner + nl + "  }" + nl + "}" + nl
    new = body[:-1].rstrip() + block
    json.loads(new)  # tem de continuar JSON valido
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    print(f"root: {root}  dry-run={a.dry_run}")

    html_p = root / HTML
    raw, nl = read(html_p)
    problems = []
    for old, new, n in PATCHES:
        c = raw.count(norm(old, nl))
        if (n is None and c < 1) or (n is not None and c != n):
            problems.append(f"esperado {n if n is not None else '>=1'}x, encontrado {c}x -> {old[:90]!r}")
    # JSON: namespace ainda nao existe
    for loc in ("pt", "pt-BR", "en", "es"):
        p = root / f"static/i18n/{loc}.json"
        if not p.exists():
            problems.append(f"{p} nao existe")
        elif '"kpi_adv": {' in p.read_text(encoding="utf-8"):
            problems.append(f"{loc}.json ja tem kpi_adv (ja aplicado?)")
    chg_raw, chg_nl = read(root / CHG)
    anchor = norm("## [Unreleased]\n\n### Changed\n\n", chg_nl)
    if chg_raw.count(anchor) != 1:
        problems.append("CHANGELOG: ancora Unreleased/Changed nao encontrada 1x")
    if problems:
        print("[ABORT] nada foi escrito:")
        for x in problems:
            print("   -", x)
        sys.exit(2)

    new_html = raw
    for old, new, n in PATCHES:
        new_html = new_html.replace(norm(old, nl), norm(new, nl))
    pt = {k: v[0] for k, v in KEYS.items()}
    en = {k: v[1] for k, v in KEYS.items()}
    es = {k: v[2] for k, v in KEYS.items()}
    ptbr = {k: v[3] for k, v in KEYS.items() if len(v) > 3 and v[3] != v[0]}
    outs = {
        root / "static/i18n/pt.json": add_namespace(root / "static/i18n/pt.json", "kpi_adv", pt),
        root / "static/i18n/en.json": add_namespace(root / "static/i18n/en.json", "kpi_adv", en),
        root / "static/i18n/es.json": add_namespace(root / "static/i18n/es.json", "kpi_adv", es),
        root / "static/i18n/pt-BR.json": add_namespace(root / "static/i18n/pt-BR.json", "kpi_adv", ptbr),
    }
    if a.dry_run:
        print(f"[DRY] {len(PATCHES)} patches no portal OK; kpi_adv: {len(pt)} chaves (pt/en/es) + {len(ptbr)} overrides pt-BR; CHANGELOG OK")
        return
    html_p.write_bytes(new_html.encode("utf-8")); print(f"[OK] {HTML} ({len(PATCHES)} patches)")
    for p, txt in outs.items():
        p.write_bytes(txt.encode("utf-8")); print(f"[OK] {p.relative_to(root)}")
    (root / CHG).write_bytes(chg_raw.replace(anchor, anchor + norm(CHANGELOG_ENTRY, chg_nl) + chg_nl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py ; browser PT/PT-BR/EN/ES")


if __name__ == "__main__":
    main()
