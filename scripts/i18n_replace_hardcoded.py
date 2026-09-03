#!/usr/bin/env python3
"""
Replace hardcoded Portuguese strings in watcherdb_portal.html with t() calls.
Creates a backup before modifying.

Usage:
    python scripts/i18n_replace_hardcoded.py              # dry-run
    python scripts/i18n_replace_hardcoded.py --apply       # apply changes
"""
import os
import re
import shutil
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
PORTAL = os.path.join(PROJECT_ROOT, 'templates', 'watcherdb_portal.html')

# Each replacement: (old_string, new_string)
# We use exact string matching for safety
REPLACEMENTS = [
    # =====================================================
    # ALWAYS ON MODULE - Second table (legacy block ~25350)
    # =====================================================
    (
        '<h4><i class="fas fa-server" style="margin-right: 8px; color: #3b82f6;"></i>R\u00e9plicas do AG</h4>',
        '<h4><i class="fas fa-server" style="margin-right: 8px; color: #3b82f6;"></i>${t(\'alwayson.replicas_title\')}</h4>'
    ),
    # Always On - Bases no AG section
    (
        "Bases no AG (${databases.length} total - ${Object.keys(databasesByReplica).length} r\u00e9plica(s))",
        "${t('alwayson.bases_title')} (${databases.length} total - ${Object.keys(databasesByReplica).length} ${t('alwayson.replicas_label')})"
    ),
    # Always On - ATUAL badge
    (
        "ATUAL</span>",
        "${t('alwayson.current_badge')}</span>"
    ),
    # Always On - Failover Events title (all occurrences)
    (
        'Eventos de Failover (30 dias)',
        "${t('alwayson.failover_events_title')}"
    ),
    # Always On - Failover table headers
    (
        '<th>Data/Hora</th><th>Tipo</th><th>Severidade</th><th>Descri\u00e7\u00e3o</th>',
        "<th>${t('alwayson.failover_datetime')}</th><th>${t('alwayson.failover_type')}</th><th>${t('alwayson.failover_severity')}</th><th>${t('alwayson.failover_description')}</th>"
    ),
    # Always On - No failover message
    (
        'Nenhum evento de failover nos \u00faltimos 30 dias - o AG est\u00e1 operando normalmente.',
        "${t('alwayson.no_failover_30d')}"
    ),
    # Always On - No failover history
    (
        'Sem registo de failover no hist\u00f3rico do Error Log.',
        "${t('alwayson.no_failover_history')}"
    ),
    # Always On - Diagnosis titles
    (
        "'Diagn\u00f3stico de Problemas'",
        "t('alwayson.diagnosis_problems')"
    ),
    (
        "'Diagn\u00f3stico do AG'",
        "t('alwayson.diagnosis_ag')"
    ),
    # Always On - Run Diagnosis button
    (
        'Executar Diagn\u00f3stico',
        "${t('alwayson.run_diagnosis')}"
    ),
    # Always On - Diagnosis description
    (
        'Clique no bot\u00e3o para executar o diagn\u00f3stico autom\u00e1tico e identificar a causa raiz do problema.',
        "${t('alwayson.diagnosis_desc')}"
    ),
    # Always On - Loading failover
    (
        'Carregando eventos de failover...',
        "${t('alwayson.loading_failover')}"
    ),
    # Always On - Replicas card label
    (
        '>R\u00e9plicas</div>',
        ">${t('alwayson.replicas_card_label')}</div>"
    ),
    # Always On - View Replica Details
    (
        'Ver Detalhes das R\u00e9plicas',
        "${t('alwayson.view_replica_details')}"
    ),

    # =====================================================
    # MEMORY MODULE
    # =====================================================
    (
        '>RAM Total</div>',
        ">${t('mem.ram_total')}</div>"
    ),
    (
        '>Disponivel SO</div>',
        ">${t('mem.available_os')}</div>"
    ),
    (
        '>Disponivel SQL Server</div>',
        ">${t('mem.available_sql')}</div>"
    ),
    (
        '>Uso real SQL:</span>',
        ">${t('mem.real_sql_usage')}:</span>"
    ),
    (
        ">Marca d'agua:</span>",
        ">${t('mem.watermark')}:</span>"
    ),
    (
        '>Max config:</span>',
        ">${t('mem.max_config')}:</span>"
    ),
    # Memory - Above/Below/Normal status
    (
        "isAbove ? 'Acima' : isBelow ? 'Abaixo' : 'Normal'",
        "isAbove ? t('mem.above') : isBelow ? t('mem.below') : t('mem.normal')"
    ),
    # Memory - Base/Atual labels
    (
        "'>Base</span>",
        "'>${t('mem.baseline')}</span>"
    ),
    (
        "'>Atual</span>",
        "'>${t('mem.current')}</span>"
    ),
    # Memory - No OOM events
    (
        "'Sem eventos OOM'",
        "t('mem.no_oom_events')"
    ),
    # Memory - Outros Proc. (chart bar labels)
    (
        "memBar('Outros Proc.",
        "memBar(t('mem.other_processes'),"
    ),
    (
        "memBar('OS/Cache",
        "memBar(t('mem.os_cache'),"
    ),

    # =====================================================
    # LOG MODULE
    # =====================================================
    (
        'Logs do Sistema Operacional (Windows Events)',
        "${t('log.os_logs_title')}"
    ),
    (
        'Logs do SQL Server (Database Errors)',
        "${t('log.sql_logs_title')}"
    ),
    # Log - Table headers (individual th elements)
    (
        '>Data/Hora</th>',
        ">${t('log.datetime_header')}</th>"
    ),
    (
        '>N\u00edvel</th>',
        ">${t('log.level_header')}</th>"
    ),
    (
        '>Fonte</th>',
        ">${t('log.source_header')}</th>"
    ),
    (
        '>ID do Evento</th>',
        ">${t('log.event_id_header')}</th>"
    ),
    (
        '>Mensagem</th>',
        ">${t('log.message_header')}</th>"
    ),
    # Log - No SQL errors
    (
        "'Nenhum erro do SQL Server encontrado'",
        "t('log.no_sql_errors')"
    ),
    # Log - Period options
    (
        '>\u00daltimas 24h</option>',
        ">${t('log.last_24h')}</option>"
    ),
    (
        '>24 horas</option>',
        ">${t('log.hours_24')}</option>"
    ),
    (
        '>48 horas</option>',
        ">${t('log.hours_48')}</option>"
    ),
    (
        '>\u00daltimos 7 dias</option>',
        ">${t('log.last_7_days')}</option>"
    ),
    # Log - Controls
    (
        '>Controles</h4>',
        ">${t('log.controls')}</h4>"
    ),
    # Log - Period label
    (
        '>Per\u00edodo:</label>',
        ">${t('log.period_label')}</label>"
    ),

    # =====================================================
    # TDE / ENCRYPTED MODULE
    # =====================================================
    (
        '>Criptografado</div>',
        ">${t('tde.encrypted_label')}</div>"
    ),
    (
        '>Sem Criptografia</div>',
        ">${t('tde.no_encryption')}</div>"
    ),
    (
        'Exportar Tudo (CSV)',
        "${t('tde.export_all_csv')}"
    ),
    (
        'Exportar Criptografadas',
        "${t('tde.export_encrypted')}"
    ),
    (
        'Exportar Sem Criptografia',
        "${t('tde.export_unencrypted')}"
    ),
    (
        "Certificados TDE (${tdeStatus.length})",
        "${t('tde.certificates_title')} (${tdeStatus.length})"
    ),
    (
        'Databases Criptografadas (${encryptedDatabases.length})',
        "${t('tde.encrypted_dbs')} (${encryptedDatabases.length})"
    ),
    (
        'Databases Sem Criptografia (${unencryptedDatabases.length})',
        "${t('tde.unencrypted_dbs')} (${unencryptedDatabases.length})"
    ),
    (
        'Clique para expandir',
        "${t('tde.click_to_expand')}"
    ),
    (
        "placeholder=\"Filtrar por nome do database...\"",
        "placeholder=\"${t('tde.filter_db_placeholder')}\""
    ),
    # TDE - Certificate labels
    (
        '>Nome</span><br>',
        ">${t('tde.cert_name')}</span><br>"
    ),
    (
        '>Tipo</span><br>',
        ">${t('tde.cert_type')}</span><br>"
    ),
    (
        '>Criado em</span><br>',
        ">${t('tde.cert_created')}</span><br>"
    ),
    (
        '>Expira em</span><br>',
        ">${t('tde.cert_expires')}</span><br>"
    ),
    (
        '>Emissor:</span>',
        ">${t('tde.cert_issuer')}:</span>"
    ),
    # TDE - Alert texts
    (
        "ok: 'Valido'",
        "ok: t('tde.valid_status')"
    ),
    (
        "expired: 'EXPIRADO!'",
        "expired: t('tde.expired_status')"
    ),
    (
        "unknown: 'Data desconhecida'",
        "unknown: t('tde.unknown_date')"
    ),
    # TDE - No TDE / criptografado
    (
        '>Sem TDE</span>',
        ">${t('tde.no_tde_label')}</span>"
    ),
    (
        '>criptografado</text>',
        ">${t('tde.encrypted_lower')}</text>"
    ),
    (
        'TDE Nao Configurado',
        "${t('tde.tde_not_configured')}"
    ),

    # =====================================================
    # SECURITY MODULE
    # =====================================================
    (
        "'Auditoria'",
        "t('security.audit')"
    ),
    (
        "'Autentica\u00e7\u00e3o'",
        "t('security.authentication')"
    ),
    (
        "'Configura\u00e7\u00f5es SQL Server'",
        "t('security.sql_config')"
    ),
    (
        "'Criptografia'",
        "t('security.encryption_section')"
    ),
    (
        "'Permiss\u00f5es'",
        "t('security.permissions_section')"
    ),
    (
        "'Vers\u00e3o'",
        "t('security.version_section')"
    ),
    (
        'Erro na Verifica\u00e7\u00e3o',
        "${t('security.verification_error')}"
    ),

    # =====================================================
    # JOBS MODULE
    # =====================================================
    (
        '>An\u00e1lise de Tend\u00eancias</span>',
        ">${t('jobs.trend_title')}</span>"
    ),
    (
        '>Jobs Analisados</div>',
        ">${t('jobs.jobs_analyzed')}</div>"
    ),
    (
        '>Performance Degradada</div>',
        ">${t('jobs.perf_degraded')}</div>"
    ),
    (
        '>Aumento de Falhas</div>',
        ">${t('jobs.failure_increase')}</div>"
    ),
    (
        '>Melhorias Detectadas</div>',
        ">${t('jobs.improvements_detected')}</div>"
    ),
    (
        '>CONFIGURADO</span>',
        ">${t('jobs.configured')}</span>"
    ),
    (
        '>RECOMENDADO</span>',
        ">${t('jobs.recommended')}</span>"
    ),

    # =====================================================
    # DISK MODULE
    # =====================================================
    (
        '>Tendencias de Disco</h4>',
        ">${t('disk.trends_title')}</h4>"
    ),
    (
        '>Tendencias de Disco</span>',
        ">${t('disk.trends_title')}</span>"
    ),
    (
        'Espa\u00e7o N\u00e3o Alocado',
        "${t('disk.unallocated_space')}"
    ),
    (
        'Espaco Nao Alocado (Potencial de Expansao)',
        "${t('disk.unallocated_expansion')}"
    ),
    (
        'Espaco Nao Alocado',
        "${t('disk.unallocated_space')}"
    ),
    (
        'GB Nao Alocado',
        "${t('disk.gb_unallocated')}"
    ),
]


def main():
    apply = '--apply' in sys.argv

    print('=' * 60)
    print('i18n Hardcoded String Replacer')
    print('=' * 60)

    if not os.path.exists(PORTAL):
        print(f'ERROR: Portal file not found: {PORTAL}')
        return 1

    with open(PORTAL, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    total_replaced = 0
    failed = []

    for old, new in REPLACEMENTS:
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            total_replaced += count
            print(f'  [{count}x] {old[:60]}...')
        else:
            failed.append(old[:80])

    print(f'\n  Total: {total_replaced} replacements across {len(REPLACEMENTS)} patterns')
    if failed:
        print(f'  Not found ({len(failed)}):')
        for f_str in failed[:15]:
            print(f'    - {f_str}')
        if len(failed) > 15:
            print(f'    ... and {len(failed) - 15} more')

    if apply:
        # Backup
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = PORTAL + f'.bak_i18n_{ts}'
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
