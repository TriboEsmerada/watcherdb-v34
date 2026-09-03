#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Queries - Diagnostics Legacy endpoints.
Contains the large diagnostic endpoints that were too complex to decompose:
  - /tempdb-diagnose/{server_id}/{session_id}
  - /diagnose-query/{server_id}
  - /expand-view/{server_id}
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging
import re

from modules.monitoring.queries import SQLQueries
from api.error_helpers import safe_http_error
from api.routers.queries.helpers import execute_query_on_server, _serialize_result
from watcherdb.core.sql_validator import validate_query
from api.models import GenericResponse

logger = logging.getLogger(__name__)

# Pattern for valid SQL identifiers (database names, schema names, object names)
_VALID_SQL_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_@$#]{0,127}$')


def _sanitize_sql_identifier(name: str, field_label: str) -> str:
    """
    Validate and sanitize a SQL identifier (database, schema, or object name).
    Raises HTTPException 400 if the identifier contains suspicious characters.
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail=f"Empty {field_label}")
    cleaned = name.strip().strip('[]')
    if not _VALID_SQL_IDENTIFIER.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_label}: '{name}'. Only alphanumeric characters, underscores, @, $, # are allowed."
        )
    return cleaned


diagnostics_router = APIRouter()

@diagnostics_router.get("/tempdb-diagnose/{server_id}/{session_id}", response_model=GenericResponse)
async def diagnose_tempdb_villain(server_id: str, session_id: int):
    """
    Diagnóstico inteligente de vilão TempDB - v1.0

    Analisa a query executada pela sessão e correlaciona com:
    - Estatísticas desatualizadas
    - Índices faltantes
    - Fragmentação de índices
    - Padrões de consumo de TempDB (ORDER BY, GROUP BY, REBUILD, etc)

    Retorna:
    - query_info: Informações da query original
    - pattern_analysis: Padrões identificados na query
    - correlations: Correlações com outros diagnósticos
    - recommendations: Recomendações de ação
    """
    try:
        import re

        # 1. Obter informações da sessão e query
        # v2.5 - Adicionado last_request_end_time, idle_time_minutes, user/internal objects MB
        session_query = f"""
        SELECT
            su.session_id,
            es.login_name,
            es.host_name,
            es.program_name,
            d.name as database_name,
            es.status as session_status,
            r.status as request_status,
            r.command,
            r.wait_type,
            r.wait_time as wait_time_ms,
            r.cpu_time as cpu_time_ms,
            r.total_elapsed_time as elapsed_time_ms,
            r.logical_reads,
            r.writes,
            es.login_time,
            es.last_request_start_time,
            es.last_request_end_time,
            -- Tempo idle em minutos (só faz sentido para sleeping)
            CASE
                WHEN es.status = 'sleeping' AND es.last_request_end_time IS NOT NULL
                THEN DATEDIFF(MINUTE, es.last_request_end_time, GETDATE())
                ELSE NULL
            END as idle_time_minutes,
            -- Uso líquido (alocado - desalocado)
            (su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) as user_objects_pages,
            (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count) as internal_objects_pages,
            ((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) +
             (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count)) as total_pages,
            CAST(((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) +
                  (su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count)) * 8.0 / 1024 AS DECIMAL(12,2)) as space_used_mb,
            CAST((su.user_objects_alloc_page_count - su.user_objects_dealloc_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as user_objects_mb,
            CAST((su.internal_objects_alloc_page_count - su.internal_objects_dealloc_page_count) * 8.0 / 1024 AS DECIMAL(12,2)) as internal_objects_mb,
            COALESCE(t.text, t2.text) as full_query_text,
            CASE
                WHEN r.sql_handle IS NOT NULL THEN
                    SUBSTRING(t.text, (r.statement_start_offset/2) + 1,
                        ((CASE r.statement_end_offset
                            WHEN -1 THEN DATALENGTH(t.text)
                            ELSE r.statement_end_offset
                        END - r.statement_start_offset)/2) + 1)
                ELSE NULL
            END as current_statement
        FROM tempdb.sys.dm_db_session_space_usage su WITH(NOLOCK)
        INNER JOIN sys.dm_exec_sessions es WITH(NOLOCK) ON su.session_id = es.session_id
        LEFT JOIN sys.databases d WITH(NOLOCK) ON es.database_id = d.database_id
        LEFT JOIN sys.dm_exec_requests r WITH(NOLOCK) ON su.session_id = r.session_id
        LEFT JOIN sys.dm_exec_connections ec WITH(NOLOCK) ON su.session_id = ec.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        OUTER APPLY sys.dm_exec_sql_text(ec.most_recent_sql_handle) t2
        WHERE su.session_id = {session_id}
        """

        session_result = await execute_query_on_server(server_id, session_query)
        session_info = session_result[0] if session_result else {}

        query_text = session_info.get('full_query_text') or session_info.get('current_statement') or ''
        database_name = session_info.get('database_name') or 'master'

        # 2. Análise de padrões na query
        patterns_found = []
        consumption_type = 'UNKNOWN'

        query_upper = query_text.upper() if query_text else ''

        # Padrões de manutenção
        if 'REBUILD' in query_upper or 'ALTER INDEX' in query_upper:
            patterns_found.append({
                'pattern': 'INDEX_REBUILD',
                'description': 'Reconstrução de índice detectada',
                'severity': 'INFO',
                'impact': 'Alto consumo temporário de TempDB durante rebuild'
            })
            consumption_type = 'MAINTENANCE'

        if 'UPDATE STATISTICS' in query_upper or 'DBCC' in query_upper:
            patterns_found.append({
                'pattern': 'STATISTICS_UPDATE',
                'description': 'Atualização de estatísticas ou DBCC detectado',
                'severity': 'INFO',
                'impact': 'Consumo normal de manutenção'
            })
            consumption_type = 'MAINTENANCE'

        # Padrões de ordenação/agregação
        if 'ORDER BY' in query_upper and 'TOP' not in query_upper:
            patterns_found.append({
                'pattern': 'LARGE_SORT',
                'description': 'Ordenação sem limite TOP detectada',
                'severity': 'WARNING',
                'impact': 'Sort spill para TempDB se dados excedem memória'
            })
            if consumption_type == 'UNKNOWN':
                consumption_type = 'SORTING_AGGREGATION'

        if 'GROUP BY' in query_upper:
            patterns_found.append({
                'pattern': 'AGGREGATION',
                'description': 'Agregação GROUP BY detectada',
                'severity': 'INFO',
                'impact': 'Hash aggregation pode usar TempDB'
            })
            if consumption_type == 'UNKNOWN':
                consumption_type = 'SORTING_AGGREGATION'

        if 'DISTINCT' in query_upper:
            patterns_found.append({
                'pattern': 'DISTINCT_OPERATION',
                'description': 'Operação DISTINCT detectada',
                'severity': 'INFO',
                'impact': 'Sort para eliminação de duplicatas'
            })
            if consumption_type == 'UNKNOWN':
                consumption_type = 'SORTING_AGGREGATION'

        # Padrões de tabelas temporárias
        if '#' in query_text:
            temp_tables = re.findall(r'#[a-zA-Z_][a-zA-Z0-9_]*', query_text)
            if temp_tables:
                patterns_found.append({
                    'pattern': 'TEMP_TABLES',
                    'description': f'Tabelas temporárias detectadas: {", ".join(set(temp_tables))}',
                    'severity': 'INFO',
                    'impact': 'Consumo direto de TempDB'
                })
                if consumption_type == 'UNKNOWN':
                    consumption_type = 'TEMP_TABLES'

        # Padrões de joins pesados
        join_count = query_upper.count(' JOIN ')
        if join_count >= 3:
            patterns_found.append({
                'pattern': 'HEAVY_JOINS',
                'description': f'{join_count} JOINs detectados na query',
                'severity': 'WARNING',
                'impact': 'Hash joins podem usar TempDB para work tables'
            })
            if consumption_type == 'UNKNOWN':
                consumption_type = 'HEAVY_JOINS'

        # CTEs e subqueries
        if 'WITH ' in query_upper and 'AS (' in query_upper:
            patterns_found.append({
                'pattern': 'CTE_USAGE',
                'description': 'Common Table Expression (CTE) detectada',
                'severity': 'INFO',
                'impact': 'CTEs materializadas usam TempDB'
            })

        # Cursores
        if 'CURSOR' in query_upper or 'FETCH' in query_upper:
            patterns_found.append({
                'pattern': 'CURSOR_OPERATION',
                'description': 'Operação com cursor detectada',
                'severity': 'WARNING',
                'impact': 'Cursores podem consumir TempDB significativamente'
            })
            if consumption_type == 'UNKNOWN':
                consumption_type = 'CURSOR_PROCESSING'

        if consumption_type == 'UNKNOWN' and session_info.get('internal_objects_pages', 0) > session_info.get('user_objects_pages', 0):
            consumption_type = 'INTERNAL_OPERATIONS'

        # 3. Correlação com outros diagnósticos
        correlations = {
            'outdated_statistics': [],
            'missing_indexes': [],
            'index_fragmentation': []
        }

        # Extrair tabelas mencionadas na query para correlação
        tables_in_query = []
        if query_text:
            # Padrão para encontrar tabelas: FROM/JOIN seguido de schema.table ou [schema].[table]
            table_pattern = r'(?:FROM|JOIN)\s+(?:\[?(\w+)\]?\.)?(?:\[?(\w+)\]?)'
            matches = re.findall(table_pattern, query_text, re.IGNORECASE)
            for match in matches:
                schema = match[0] or 'dbo'
                table = match[1]
                if table and table.lower() not in ('select', 'where', 'and', 'or', 'on'):
                    tables_in_query.append({'schema': schema, 'table': table})

        # 3a. Verificar estatísticas desatualizadas
        # STATS_DATE() é mais confiável que dm_db_stats_properties.last_updated
        if database_name and database_name.lower() not in ('master', 'tempdb', 'model', 'msdb'):
            try:
                stats_query = f"""
                USE [{database_name}];
                SELECT TOP 10
                    OBJECT_SCHEMA_NAME(s.object_id) as schema_name,
                    OBJECT_NAME(s.object_id) as table_name,
                    s.name as stats_name,
                    STATS_DATE(s.object_id, s.stats_id) as last_updated,
                    DATEDIFF(day, STATS_DATE(s.object_id, s.stats_id), GETDATE()) as days_since_update,
                    sp.rows as table_rows,
                    sp.modification_counter as modifications,
                    CASE WHEN sp.rows > 0 THEN CAST((sp.modification_counter * 100.0 / sp.rows) AS DECIMAL(5,2)) ELSE 0 END as modification_percent
                FROM sys.stats s WITH(NOLOCK)
                CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
                WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
                AND sp.rows >= 100
                AND (DATEDIFF(day, STATS_DATE(s.object_id, s.stats_id), GETDATE()) >= 7 OR (sp.modification_counter * 100.0 / NULLIF(sp.rows, 0)) >= 10)
                ORDER BY sp.modification_counter DESC
                """
                stats_result = await execute_query_on_server(server_id, stats_query)

                for stat in (stats_result or []):
                    stat_table = stat.get('table_name', '').lower()
                    for tbl in tables_in_query:
                        if tbl['table'].lower() == stat_table:
                            correlations['outdated_statistics'].append({
                                'table': f"{stat.get('schema_name')}.{stat.get('table_name')}",
                                'stats_name': stat.get('stats_name'),
                                'days_since_update': stat.get('days_since_update'),
                                'modification_percent': _serialize_result(stat.get('modification_percent')),
                                'correlation': 'DIRECT_MATCH'
                            })
                            break
            except Exception as e:
                logger.warning(f"Erro ao verificar estatísticas: {e}")

        # 3b. Verificar índices faltantes
        if database_name and database_name.lower() not in ('master', 'tempdb', 'model', 'msdb'):
            try:
                missing_idx_query = f"""
                SELECT TOP 10
                    OBJECT_SCHEMA_NAME(mid.object_id, mid.database_id) AS schema_name,
                    OBJECT_NAME(mid.object_id, mid.database_id) AS table_name,
                    mid.equality_columns,
                    mid.inequality_columns,
                    mid.included_columns,
                    CAST(migs.avg_total_user_cost AS DECIMAL(12,2)) as avg_query_cost,
                    CAST(migs.avg_user_impact AS DECIMAL(5,2)) as avg_impact_percent,
                    migs.user_seeks + migs.user_scans as total_reads
                FROM sys.dm_db_missing_index_details mid WITH(NOLOCK)
                INNER JOIN sys.dm_db_missing_index_groups mig WITH(NOLOCK) ON mid.index_handle = mig.index_handle
                INNER JOIN sys.dm_db_missing_index_group_stats migs WITH(NOLOCK) ON mig.index_group_handle = migs.group_handle
                WHERE DB_NAME(mid.database_id) = '{database_name}'
                AND OBJECT_NAME(mid.object_id, mid.database_id) IS NOT NULL
                ORDER BY (migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) DESC
                """
                missing_idx_result = await execute_query_on_server(server_id, missing_idx_query)

                for idx in (missing_idx_result or []):
                    idx_table = idx.get('table_name', '').lower()
                    for tbl in tables_in_query:
                        if tbl['table'].lower() == idx_table:
                            correlations['missing_indexes'].append({
                                'table': f"{idx.get('schema_name')}.{idx.get('table_name')}",
                                'equality_columns': idx.get('equality_columns'),
                                'inequality_columns': idx.get('inequality_columns'),
                                'included_columns': idx.get('included_columns'),
                                'avg_query_cost': _serialize_result(idx.get('avg_query_cost')),
                                'avg_impact_percent': _serialize_result(idx.get('avg_impact_percent')),
                                'correlation': 'DIRECT_MATCH'
                            })
                            break
            except Exception as e:
                logger.warning(f"Erro ao verificar índices faltantes: {e}")

        # 3c. Verificar fragmentação de índices
        if database_name and database_name.lower() not in ('master', 'tempdb', 'model', 'msdb'):
            try:
                frag_query = f"""
                SELECT TOP 10
                    OBJECT_SCHEMA_NAME(i.object_id) as schema_name,
                    OBJECT_NAME(i.object_id) as table_name,
                    i.name as index_name,
                    CAST(ips.avg_fragmentation_in_percent AS DECIMAL(5,2)) as fragmentation_percent,
                    ips.page_count
                FROM [{database_name}].sys.dm_db_index_physical_stats(DB_ID('{database_name}'), NULL, NULL, NULL, 'LIMITED') ips
                INNER JOIN [{database_name}].sys.indexes i WITH(NOLOCK) ON ips.object_id = i.object_id AND ips.index_id = i.index_id
                WHERE ips.index_level = 0
                AND ips.page_count > 1000
                AND ips.avg_fragmentation_in_percent > 30
                ORDER BY ips.avg_fragmentation_in_percent DESC
                """
                frag_result = await execute_query_on_server(server_id, frag_query)

                for frag in (frag_result or []):
                    frag_table = frag.get('table_name', '').lower()
                    for tbl in tables_in_query:
                        if tbl['table'].lower() == frag_table:
                            correlations['index_fragmentation'].append({
                                'table': f"{frag.get('schema_name')}.{frag.get('table_name')}",
                                'index_name': frag.get('index_name'),
                                'fragmentation_percent': _serialize_result(frag.get('fragmentation_percent')),
                                'page_count': frag.get('page_count'),
                                'correlation': 'DIRECT_MATCH'
                            })
                            break
            except Exception as e:
                logger.warning(f"Erro ao verificar fragmentação: {e}")

        # 4. Gerar recomendações
        recommendations = []

        # Informações para recomendações baseadas em status
        session_status = session_info.get('session_status', '').lower()
        idle_time_minutes = session_info.get('idle_time_minutes')
        space_used_mb = float(session_info.get('space_used_mb') or 0)
        user_objects_mb = float(session_info.get('user_objects_mb') or 0)
        internal_objects_mb = float(session_info.get('internal_objects_mb') or 0)
        login_name = session_info.get('login_name', 'N/A')
        program_name = session_info.get('program_name', 'N/A')

        # =====================================================================
        # RECOMENDAÇÕES PARA SESSÕES SLEEPING (PRIORIDADE ALTA)
        # =====================================================================
        if session_status == 'sleeping':
            # Sessão sleeping com uso de TempDB é candidata a KILL
            if idle_time_minutes is not None:
                if idle_time_minutes >= 60 and space_used_mb >= 100:
                    # CRÍTICO: Idle há mais de 1 hora com consumo significativo
                    recommendations.append({
                        'type': 'ACTION_REQUIRED',
                        'category': 'SESSION_KILL',
                        'message': f'Sessão SLEEPING há {idle_time_minutes} minutos consumindo {space_used_mb:.2f} MB',
                        'action': f'RECOMENDADO: Execute KILL {session_id} para liberar TempDB. Sessão está ociosa há muito tempo.',
                        'kill_command': f'KILL {session_id}',
                        'severity': 'CRITICAL'
                    })
                elif idle_time_minutes >= 30 and space_used_mb >= 50:
                    # ALTO: Idle há mais de 30 minutos
                    recommendations.append({
                        'type': 'ACTION_REQUIRED',
                        'category': 'SESSION_KILL',
                        'message': f'Sessão SLEEPING há {idle_time_minutes} minutos consumindo {space_used_mb:.2f} MB',
                        'action': f'Considere executar KILL {session_id}. A sessão está ociosa e prendendo espaço.',
                        'kill_command': f'KILL {session_id}',
                        'severity': 'HIGH'
                    })
                elif idle_time_minutes >= 10 and space_used_mb >= 10:
                    # MÉDIO: Idle há mais de 10 minutos
                    recommendations.append({
                        'type': 'WARNING',
                        'category': 'SESSION_IDLE',
                        'message': f'Sessão SLEEPING há {idle_time_minutes} minutos com {space_used_mb:.2f} MB alocados',
                        'action': f'Monitore a sessão. Se continuar ociosa, considere KILL {session_id}.',
                        'kill_command': f'KILL {session_id}',
                        'severity': 'MEDIUM'
                    })
                elif idle_time_minutes >= 5:
                    # BAIXO: Idle recente
                    recommendations.append({
                        'type': 'INFO',
                        'category': 'SESSION_IDLE',
                        'message': f'Sessão SLEEPING há {idle_time_minutes} minutos',
                        'action': 'Sessão ociosa recentemente. Aguarde ou monitore se o consumo aumentar.',
                        'severity': 'LOW'
                    })
            else:
                # Sleeping mas sem idle_time (raro)
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'SESSION_IDLE',
                    'message': f'Sessão SLEEPING consumindo {space_used_mb:.2f} MB de TempDB',
                    'action': f'Verifique se a sessão está ativa. Considere KILL {session_id} se não for necessária.',
                    'kill_command': f'KILL {session_id}',
                    'severity': 'MEDIUM'
                })

            # Informação adicional sobre tipo de consumo em sleeping
            if user_objects_mb > 0 and internal_objects_mb == 0:
                recommendations.append({
                    'type': 'INFO',
                    'category': 'TEMPDB_ANALYSIS',
                    'message': f'Consumo de {user_objects_mb:.2f} MB em tabelas temporárias (#temp)',
                    'action': 'A sessão criou tabelas temporárias que não foram limpas. KILL liberará o espaço.',
                    'severity': 'INFO'
                })
            elif internal_objects_mb > 0 and user_objects_mb == 0:
                recommendations.append({
                    'type': 'INFO',
                    'category': 'TEMPDB_ANALYSIS',
                    'message': f'Consumo de {internal_objects_mb:.2f} MB em objetos internos (sorts, spools)',
                    'action': 'O SQL Server está mantendo worktables. KILL liberará o espaço.',
                    'severity': 'INFO'
                })

        # =====================================================================
        # RECOMENDAÇÕES PARA SESSÕES ATIVAS (running, runnable, suspended)
        # =====================================================================
        elif session_status in ('running', 'runnable', 'suspended'):
            # Sessão ativa - não recomendar KILL imediatamente
            if session_status == 'suspended':
                wait_type = session_info.get('wait_type', 'N/A')
                wait_time_ms = session_info.get('wait_time_ms', 0)
                if wait_time_ms and wait_time_ms > 60000:  # Mais de 1 minuto esperando
                    recommendations.append({
                        'type': 'WARNING',
                        'category': 'SESSION_WAIT',
                        'message': f'Sessão SUSPENDED esperando por {wait_type} há {wait_time_ms/1000:.0f} segundos',
                        'action': f'Investigue o bloqueio. Se estiver travada, considere KILL {session_id}.',
                        'severity': 'HIGH'
                    })

            if session_status == 'runnable':
                recommendations.append({
                    'type': 'INFO',
                    'category': 'SESSION_STATUS',
                    'message': 'Sessão RUNNABLE - aguardando CPU',
                    'action': 'Sessão está na fila do scheduler. Verifique se há pressão de CPU no servidor.',
                    'severity': 'INFO'
                })

        # =====================================================================
        # RECOMENDAÇÕES BASEADAS EM PADRÕES DA QUERY
        # =====================================================================
        if any(p['pattern'] == 'INDEX_REBUILD' for p in patterns_found):
            recommendations.append({
                'type': 'INFO',
                'category': 'MAINTENANCE',
                'message': 'Rebuild de índice em andamento - consumo de TempDB é esperado e temporário',
                'action': 'Aguarde a conclusão do rebuild ou execute em horário de baixa atividade'
            })

        if any(p['pattern'] == 'LARGE_SORT' for p in patterns_found):
            recommendations.append({
                'type': 'OPTIMIZATION',
                'category': 'QUERY',
                'message': 'Sort sem limite TOP detectado - pode causar spill para TempDB',
                'action': 'Adicione cláusula TOP ou índice na coluna ORDER BY'
            })

        if any(p['pattern'] == 'HEAVY_JOINS' for p in patterns_found):
            recommendations.append({
                'type': 'OPTIMIZATION',
                'category': 'QUERY',
                'message': 'Múltiplos JOINs detectados - hash joins podem usar TempDB',
                'action': 'Verifique se existem índices nas colunas de JOIN'
            })

        if any(p['pattern'] == 'CURSOR_OPERATION' for p in patterns_found):
            recommendations.append({
                'type': 'OPTIMIZATION',
                'category': 'QUERY',
                'message': 'Uso de cursor detectado - alto consumo de TempDB',
                'action': 'Considere reescrever usando operações baseadas em conjunto (SET-based)'
            })

        # =====================================================================
        # RECOMENDAÇÕES BASEADAS EM CORRELAÇÕES
        # =====================================================================
        if correlations['outdated_statistics']:
            tables_with_outdated = [c['table'] for c in correlations['outdated_statistics']]
            recommendations.append({
                'type': 'ACTION_REQUIRED',
                'category': 'STATISTICS',
                'message': f'Estatísticas desatualizadas em: {", ".join(tables_with_outdated)}',
                'action': 'Execute UPDATE STATISTICS nas tabelas listadas para melhorar planos de execução'
            })

        if correlations['missing_indexes']:
            tables_with_missing = [c['table'] for c in correlations['missing_indexes']]
            recommendations.append({
                'type': 'ACTION_REQUIRED',
                'category': 'INDEXES',
                'message': f'Índices faltantes em: {", ".join(tables_with_missing)}',
                'action': 'Considere criar os índices sugeridos para evitar table scans'
            })

        if correlations['index_fragmentation']:
            tables_with_frag = [c['table'] for c in correlations['index_fragmentation']]
            recommendations.append({
                'type': 'ACTION_REQUIRED',
                'category': 'INDEXES',
                'message': f'Índices fragmentados (>30%) em: {", ".join(tables_with_frag)}',
                'action': 'Execute REBUILD ou REORGANIZE nos índices fragmentados'
            })

        # =====================================================================
        # RECOMENDAÇÃO GERAL BASEADA EM CONSUMO
        # =====================================================================
        if space_used_mb > 1000 and session_status not in ('sleeping',):
            recommendations.append({
                'type': 'WARNING',
                'category': 'TEMPDB',
                'message': f'Sessão consumindo {space_used_mb:.2f} MB de TempDB',
                'action': 'Monitore a sessão e considere aumentar TempDB se necessário'
            })

        # Se nenhuma recomendação específica
        if not recommendations:
            recommendations.append({
                'type': 'INFO',
                'category': 'GENERAL',
                'message': 'Nenhum problema crítico identificado',
                'action': 'Consumo de TempDB dentro dos parâmetros normais'
            })

        # 5. Construir resposta
        # Determinar se há recomendação de KILL
        has_kill_recommendation = any(r.get('category') == 'SESSION_KILL' for r in recommendations)
        kill_command = next((r.get('kill_command') for r in recommendations if r.get('kill_command')), None)

        response = {
            'server_id': server_id,
            'session_id': session_id,
            'diagnosis_timestamp': str(__import__('datetime').datetime.now()),
            'query_info': {
                'database': database_name,
                'login_name': session_info.get('login_name'),
                'host_name': session_info.get('host_name'),
                'program_name': session_info.get('program_name'),
                'session_status': session_info.get('session_status'),
                'command': session_info.get('command'),
                'wait_type': session_info.get('wait_type'),
                'wait_time_ms': session_info.get('wait_time_ms'),
                'cpu_time_ms': session_info.get('cpu_time_ms'),
                'elapsed_time_ms': session_info.get('elapsed_time_ms'),
                'logical_reads': session_info.get('logical_reads'),
                'writes': session_info.get('writes'),
                'space_used_mb': _serialize_result(session_info.get('space_used_mb')),
                'user_objects_mb': _serialize_result(session_info.get('user_objects_mb')),
                'internal_objects_mb': _serialize_result(session_info.get('internal_objects_mb')),
                'user_objects_pages': session_info.get('user_objects_pages'),
                'internal_objects_pages': session_info.get('internal_objects_pages'),
                'login_time': str(session_info.get('login_time')) if session_info.get('login_time') else None,
                'last_request_start_time': str(session_info.get('last_request_start_time')) if session_info.get('last_request_start_time') else None,
                'last_request_end_time': str(session_info.get('last_request_end_time')) if session_info.get('last_request_end_time') else None,
                'idle_time_minutes': session_info.get('idle_time_minutes'),
                'query_text': query_text[:2000] if query_text else None,  # Limitar tamanho
                'current_statement': session_info.get('current_statement')[:500] if session_info.get('current_statement') else None
            },
            'pattern_analysis': {
                'consumption_type': consumption_type,
                'consumption_type_description': {
                    'MAINTENANCE': 'Operação de manutenção (rebuild, statistics)',
                    'SORTING_AGGREGATION': 'Ordenação ou agregação de dados',
                    'TEMP_TABLES': 'Uso de tabelas temporárias',
                    'HEAVY_JOINS': 'JOINs pesados com hash/merge operations',
                    'CURSOR_PROCESSING': 'Processamento com cursores',
                    'INTERNAL_OPERATIONS': 'Operações internas do SQL Server',
                    'SLEEPING_WITH_TEMPDB': 'Sessão ociosa mantendo espaço alocado',
                    'UNKNOWN': 'Padrão não identificado'
                }.get(consumption_type, 'Não identificado'),
                'patterns_found': patterns_found,
                'tables_referenced': tables_in_query
            },
            'correlations': {
                'outdated_statistics': correlations['outdated_statistics'],
                'missing_indexes': correlations['missing_indexes'],
                'index_fragmentation': correlations['index_fragmentation'],
                'has_correlations': bool(correlations['outdated_statistics'] or correlations['missing_indexes'] or correlations['index_fragmentation'])
            },
            'recommendations': recommendations,
            'action_summary': {
                'has_kill_recommendation': has_kill_recommendation,
                'kill_command': kill_command,
                'is_sleeping': session_status == 'sleeping',
                'idle_time_minutes': idle_time_minutes,
                'space_recoverable_mb': space_used_mb if session_status == 'sleeping' else 0
            },
            'summary': {
                'total_patterns': len(patterns_found),
                'total_correlations': len(correlations['outdated_statistics']) + len(correlations['missing_indexes']) + len(correlations['index_fragmentation']),
                'total_recommendations': len(recommendations),
                'severity': 'CRITICAL' if any(r['type'] == 'ACTION_REQUIRED' for r in recommendations) else 'WARNING' if any(r['type'] == 'WARNING' for r in recommendations) else 'INFO'
            }
        }

        return JSONResponse(content=_serialize_result(response))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao diagnosticar vilão TempDB {session_id} em {server_id}: {e}", exc_info=True)
        raise safe_http_error(500, e, "diagnostics query")



class DiagnoseQueryRequest(BaseModel):
    """Modelo para requisição de diagnóstico de query"""
    query_text: str = ""  # Pode ser vazio se analyze_full_database=True
    stats_age_threshold_days: int = 30  # Threshold em dias para considerar estatísticas desatualizadas
    database_name: Optional[str] = None  # Database específico para análise
    analyze_full_database: bool = False  # Se True, analisa todas as tabelas do banco (ignora query_text)


def extract_columns_from_query(query_text: str) -> Dict[str, List[str]]:
    """
    Extrai colunas usadas em WHERE, JOIN e ORDER BY da query.
    Retorna dict com listas de colunas por contexto.
    """
    columns = {
        'where': [],
        'join': [],
        'order_by': []
    }

    # Padrão para WHERE: coluna = valor, coluna > valor, coluna LIKE, etc.
    where_pattern = re.compile(r'WHERE\s+(.+?)(?:ORDER\s+BY|GROUP\s+BY|HAVING|$)', re.IGNORECASE | re.DOTALL)
    where_match = where_pattern.search(query_text)
    if where_match:
        where_clause = where_match.group(1)
        # Extrair nomes de colunas (simplificado)
        col_pattern = re.compile(r'(?:\[)?([a-zA-Z_][a-zA-Z0-9_]*)(?:\])?\s*(?:=|>|<|LIKE|IN|BETWEEN|IS)', re.IGNORECASE)
        columns['where'] = list(set(col_pattern.findall(where_clause)))

    # Padrão para JOIN ON: tabela.coluna = tabela.coluna
    join_pattern = re.compile(r'JOIN\s+.+?\s+ON\s+(.+?)(?:WHERE|JOIN|ORDER|GROUP|$)', re.IGNORECASE | re.DOTALL)
    for join_match in join_pattern.finditer(query_text):
        on_clause = join_match.group(1)
        col_pattern = re.compile(r'\.(?:\[)?([a-zA-Z_][a-zA-Z0-9_]*)(?:\])?', re.IGNORECASE)
        columns['join'].extend(col_pattern.findall(on_clause))
    columns['join'] = list(set(columns['join']))

    # Padrão para ORDER BY
    order_pattern = re.compile(r'ORDER\s+BY\s+(.+?)(?:$|OFFSET|FETCH)', re.IGNORECASE | re.DOTALL)
    order_match = order_pattern.search(query_text)
    if order_match:
        order_clause = order_match.group(1)
        col_pattern = re.compile(r'(?:\[)?([a-zA-Z_][a-zA-Z0-9_]*)(?:\])?(?:\s+(?:ASC|DESC))?', re.IGNORECASE)
        columns['order_by'] = [c for c in col_pattern.findall(order_clause) if c.upper() not in ('ASC', 'DESC')]

    return columns


def extract_objects_from_query(query_text: str) -> List[tuple]:
    """
    Extrai objetos (schema.tabela) de uma query SQL.

    IMPORTANTE: Esta função extrai APENAS tabelas/views referenciadas em FROM/JOIN,
    ignorando referências a colunas (alias.coluna).

    Padrões reconhecidos (somente após FROM/JOIN/INTO/UPDATE):
    - FROM [database].[schema].[tabela] -> retorna (database, schema, tabela)
    - FROM [schema].[tabela] -> retorna (None, schema, tabela)
    - FROM tabela -> retorna (None, 'dbo', tabela)

    Returns:
        Lista de tuplas: (database, schema, table)
        database pode ser None se não especificado
    """
    objects = set()

    # Remover comentários para evitar falsos positivos
    # Remove comentários de linha (-- até fim da linha)
    query_clean = re.sub(r'--[^\n]*', ' ', query_text)
    # Remove comentários de bloco (/* ... */)
    query_clean = re.sub(r'/\*.*?\*/', ' ', query_clean, flags=re.DOTALL)

    # Normalizar espaços em branco
    query_clean = ' '.join(query_clean.split())

    logger.info(f"[extract] Query limpa (primeiros 300 chars): {query_clean[:300]}...")

    # Padrão principal: Capturar tabelas após FROM/JOIN/INTO/UPDATE/DELETE FROM
    # Captura: keyword + [database].[schema].[table] ou [schema].[table] ou table

    # Padrão 1: FROM/JOIN [schema].[tabela] [alias] - duas partes com colchetes
    # Este é o padrão mais comum na query do usuário
    pattern_from_2part = re.compile(
        r'(?:FROM|JOIN|INTO|UPDATE)\s+\[([^\]]+)\]\.\[([^\]]+)\](?:\s+(?:AS\s+)?\[?([a-zA-Z_][a-zA-Z0-9_]*)\]?)?',
        re.IGNORECASE
    )
    for match in pattern_from_2part.finditer(query_clean):
        schema = match.group(1)
        table = match.group(2)
        alias = match.group(3) if match.group(3) else None
        objects.add((None, schema, table))
        logger.info(f"[extract] Padrão FROM 2-partes: [{schema}].[{table}] (alias: {alias})")

    # Padrão 2: FROM/JOIN [database].[schema].[tabela] - três partes com colchetes
    pattern_from_3part = re.compile(
        r'(?:FROM|JOIN|INTO|UPDATE)\s+\[([^\]]+)\]\.\[([^\]]+)\]\.\[([^\]]+)\]',
        re.IGNORECASE
    )
    for match in pattern_from_3part.finditer(query_clean):
        database = match.group(1)
        schema = match.group(2)
        table = match.group(3)
        objects.add((database, schema, table))
        logger.info(f"[extract] Padrão FROM 3-partes: [{database}].[{schema}].[{table}]")

    # Padrão 3: FROM/JOIN schema.tabela (sem colchetes)
    pattern_from_2part_nobrackets = re.compile(
        r'(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?',
        re.IGNORECASE
    )
    for match in pattern_from_2part_nobrackets.finditer(query_clean):
        schema = match.group(1)
        table = match.group(2)
        # Ignorar schemas do sistema
        if schema.lower() not in ('sys', 'information_schema'):
            # Verificar se não é uma referência já capturada
            if (None, schema, table) not in objects:
                objects.add((None, schema, table))
                logger.info(f"[extract] Padrão FROM 2-partes (sem colchetes): {schema}.{table}")

    # Padrão 4: FROM/JOIN database.schema.tabela (três partes sem colchetes)
    pattern_from_3part_nobrackets = re.compile(
        r'(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)',
        re.IGNORECASE
    )
    for match in pattern_from_3part_nobrackets.finditer(query_clean):
        database = match.group(1)
        schema = match.group(2)
        table = match.group(3)
        if database.lower() not in ('sys', 'information_schema'):
            objects.add((database, schema, table))
            logger.info(f"[extract] Padrão FROM 3-partes (sem colchetes): {database}.{schema}.{table}")

    # Padrão 5: FROM/JOIN [tabela] ou tabela (assume dbo)
    pattern_from_single = re.compile(
        r'(?:FROM|JOIN|INTO|UPDATE)\s+\[?([a-zA-Z_][a-zA-Z0-9_]*)\]?(?:\s|$|,)',
        re.IGNORECASE
    )
    for match in pattern_from_single.finditer(query_clean):
        table = match.group(1)
        # Verificar se já foi capturado com schema (evitar duplicatas)
        already_captured = any(o[2].lower() == table.lower() for o in objects)
        # Ignorar palavras-chave SQL que podem ser capturadas erroneamente
        sql_keywords = {'select', 'where', 'and', 'or', 'on', 'as', 'set', 'values', 'inner', 'left', 'right', 'outer', 'cross', 'full'}
        if not already_captured and table.lower() not in sql_keywords:
            objects.add((None, 'dbo', table))
            logger.info(f"[extract] Padrão FROM simples: dbo.{table}")

    result = list(objects)
    logger.info(f"[extract_objects_from_query] Total de objetos extraídos: {len(result)}")
    for obj in result:
        logger.info(f"[extract_objects_from_query]   -> {obj[0] or 'NULL'}.{obj[1]}.{obj[2]}")
    return result


@diagnostics_router.post("/diagnose-query/{server_id}", response_model=GenericResponse)
async def diagnose_slow_query(
    server_id: str,
    request: DiagnoseQueryRequest
):
    """
    Diagnóstico de Query Lenta - Analisa estatísticas das tabelas usadas na query.

    Funcionalidade:
    1. Extrai tabelas/views da query fornecida
    2. Verifica tipo do objeto (TABLE ou VIEW)
    3. Analisa idade das estatísticas de cada índice
    4. Retorna comandos UPDATE STATISTICS sugeridos

    Args:
        server_id: ID do servidor SQL
        request: Query a ser analisada e threshold de dias

    Returns:
        Lista de objetos analisados com status das estatísticas
    """
    try:
        query_text = request.query_text
        threshold_days = request.stats_age_threshold_days
        database_name = request.database_name
        analyze_full_database = request.analyze_full_database

        # Note: query_text is NOT executed — only parsed to extract table/view names
        # for statistics analysis. No SQL validation needed here since we only use
        # the extracted identifiers (which are sanitized separately below).

        # Sanitize database_name to prevent SQL injection via identifier interpolation
        if database_name:
            database_name = _sanitize_sql_identifier(database_name, "database_name")

        # Se análise de banco completo, buscar todas as tabelas com estatísticas desatualizadas
        if analyze_full_database:
            if not database_name:
                raise HTTPException(status_code=400, detail="database_name é obrigatório para análise completa do banco")

            # Query usando USE [database] + STATS_DATE() para maior confiabilidade
            # STATS_DATE() é mais confiável que dm_db_stats_properties.last_updated
            full_db_query = f"""
            USE [{database_name}];
            SET NOCOUNT ON;

            SELECT
                s.name AS schema_name,
                o.name AS table_name,
                st.name AS stats_name,
                STATS_DATE(st.object_id, st.stats_id) AS last_updated,
                DATEDIFF(DAY, STATS_DATE(st.object_id, st.stats_id), GETDATE()) AS days_since_update,
                sp.rows AS rows_sampled,
                sp.modification_counter,
                st.auto_created,
                st.user_created,
                st.no_recompute,
                CONCAT(
                    'USE [{database_name}]; UPDATE STATISTICS ',
                    QUOTENAME(s.name), '.', QUOTENAME(o.name),
                    ' ', QUOTENAME(st.name),
                    ' WITH FULLSCAN;'
                ) AS suggested_command,
                @@SERVERNAME AS server_queried,
                DB_NAME() AS database_queried
            FROM sys.stats st
            JOIN sys.objects o ON o.object_id = st.object_id
            JOIN sys.schemas s ON s.schema_id = o.schema_id
            OUTER APPLY sys.dm_db_stats_properties(st.object_id, st.stats_id) sp
            WHERE o.type = 'U'
              AND o.is_ms_shipped = 0
              AND (
                    STATS_DATE(st.object_id, st.stats_id) IS NULL
                    OR STATS_DATE(st.object_id, st.stats_id) < DATEADD(DAY, -{threshold_days}, GETDATE())
                    OR (sp.modification_counter > sp.rows * 0.2 AND sp.rows > 0)
                  )
            ORDER BY
                CASE WHEN STATS_DATE(st.object_id, st.stats_id) IS NULL THEN 0 ELSE 1 END,
                STATS_DATE(st.object_id, st.stats_id),
                s.name, o.name, st.name;
            """

            try:
                full_results = await execute_query_on_server(server_id, full_db_query)
            except Exception as e:
                logger.error(f"Erro ao executar análise completa: {e}")
                raise HTTPException(status_code=500, detail=f"Erro ao executar análise: {str(e)}")

            # Processar resultados
            statistics_analysis = []
            update_commands = []
            tables_found = set()

            for row in full_results:
                tables_found.add(f"{row.get('schema_name')}.{row.get('table_name')}")

                days_old = row.get('days_since_update')
                mod_counter = row.get('modification_counter') or 0
                rows_sampled = row.get('rows_sampled') or 0

                if days_old is None:
                    status = "CRÍTICO - Nunca teve estatísticas"
                elif days_old > threshold_days:
                    status = f"DESATUALIZADO - {days_old} dias"
                elif rows_sampled > 0 and mod_counter > rows_sampled * 0.2:
                    status = f"MODIFICADO - {mod_counter} alterações"
                else:
                    status = "OK"

                if status != "OK":
                    statistics_analysis.append({
                        "schema_name": row.get('schema_name'),
                        "table_name": row.get('table_name'),
                        "stats_name": row.get('stats_name'),
                        "last_updated": str(row.get('last_updated')) if row.get('last_updated') else None,
                        "days_since_update": days_old,
                        "rows_sampled": rows_sampled,
                        "modification_counter": mod_counter,
                        "status": status
                    })

                    cmd = row.get('suggested_command')
                    if cmd and cmd not in update_commands:
                        update_commands.append(cmd)

            # Buscar HEAPs no banco
            heap_query = f"""
            USE [{database_name}];

            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                SUM(p.rows) AS row_count,
                CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(18,2)) AS size_mb
            FROM sys.tables t
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id = 0
            JOIN sys.allocation_units a ON p.partition_id = a.container_id
            WHERE t.is_ms_shipped = 0
            GROUP BY s.name, t.name
            HAVING SUM(p.rows) > 1000
            ORDER BY SUM(p.rows) DESC;
            """

            heap_tables = []
            try:
                heap_results = await execute_query_on_server(server_id, heap_query)
                for row in heap_results:
                    heap_tables.append({
                        "schema_name": row.get('schema_name'),
                        "table_name": row.get('table_name'),
                        "row_count": row.get('row_count'),
                        "size_mb": float(row.get('size_mb') or 0)
                    })
            except Exception as heap_error:
                logger.debug(f"Erro ao buscar HEAPs: {heap_error}")

            # Diagnóstico inteligente
            diagnosis = []
            if statistics_analysis:
                # Agrupar por tabela para diagnóstico
                tables_with_issues = set(f"{s['schema_name']}.{s['table_name']}" for s in statistics_analysis)
                for table in tables_with_issues:
                    table_stats = [s for s in statistics_analysis if f"{s['schema_name']}.{s['table_name']}" == table]
                    critical = any("CRÍTICO" in s.get('status', '') for s in table_stats)
                    outdated = any("DESATUALIZADO" in s.get('status', '') for s in table_stats)
                    modified = any("MODIFICADO" in s.get('status', '') for s in table_stats)

                    if critical:
                        reason = "Estatísticas nunca criadas - executar UPDATE STATISTICS urgentemente"
                        priority = "CRÍTICO"
                    elif outdated:
                        max_days = max(s.get('days_since_update', 0) or 0 for s in table_stats)
                        reason = f"Estatísticas com {max_days} dias de idade - recomendado UPDATE STATISTICS"
                        priority = "ALTO"
                    else:
                        reason = "Muitas modificações desde última atualização - recomendado UPDATE STATISTICS"
                        priority = "MÉDIO"

                    diagnosis.append({
                        "table": table,
                        "action": "UPDATE_STATISTICS",
                        "reason": reason,
                        "priority": priority
                    })

            # Adicionar HEAPs ao diagnóstico
            for heap in heap_tables:
                diagnosis.append({
                    "table": f"{heap['schema_name']}.{heap['table_name']}",
                    "action": "CONSIDER_CLUSTERED_INDEX",
                    "reason": f"Tabela HEAP com {heap['row_count']:,} linhas - considerar criar índice clustered",
                    "priority": "MÉDIO" if heap['row_count'] < 100000 else "ALTO"
                })

            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "database_name": database_name,
                "analysis_mode": "full_database",
                "tables_found": list(tables_found),
                "statistics_analysis": statistics_analysis,
                "update_statistics_commands": update_commands,
                "heap_tables": heap_tables,
                "missing_indexes": [],  # Não aplicável para análise full
                "create_index_commands": [],
                "diagnosis": diagnosis
            })

        # Modo original: análise baseada na query colada
        if not query_text or len(query_text.strip()) < 10:
            raise HTTPException(status_code=400, detail="Query muito curta ou vazia. Use 'analyze_full_database=true' com 'database_name' para análise completa.")

        # Extrair objetos da query
        objects = extract_objects_from_query(query_text)

        if not objects:
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "message": "Nenhuma tabela/view identificada na query",
                "objects_found": 0,
                "results": [],
                "update_statistics_commands": []
            })

        logger.info(f"[Diagnose Query] Objetos extraídos: {objects}")

        results = []
        update_commands = []

        # Detectar database da query se não especificado
        detected_database = database_name
        if not detected_database:
            # Verificar se há USE statement na query
            use_match = re.search(r'USE\s+\[?([a-zA-Z_][a-zA-Z0-9_]*)\]?', query_text, re.IGNORECASE)
            if use_match:
                detected_database = use_match.group(1)

        for obj_tuple in objects:
            # Desempacotar tupla de 3 elementos (database, schema, table)
            obj_database, schema, obj_name = obj_tuple

            # Se objeto tem database especificado, usar ele; senão, usar o detectado
            target_database = obj_database or detected_database

            logger.info(f"[Diagnose Query] Analisando: obj_database={obj_database}, schema={schema}, obj_name={obj_name}, target_database={target_database}, detected_database={detected_database}")

            # Construir query usando notação de três partes se temos um database
            if target_database:
                # IMPORTANTE: sys.dm_db_stats_properties NÃO aceita notação de três partes
                # Precisamos usar USE [database] para executar no contexto correto
                # Query direta: busca estatísticas da tabela especificada
                check_query = f"""
            USE [{target_database}];
            SET NOCOUNT ON;

            -- Debug: mostrar servidor e banco atual
            DECLARE @debug_info NVARCHAR(500) = 'Server: ' + @@SERVERNAME + ', Database: ' + DB_NAME();
            PRINT @debug_info;

            -- Verificar se objeto existe
            IF NOT EXISTS (
                SELECT 1 FROM sys.objects o
                JOIN sys.schemas s ON o.schema_id = s.schema_id
                WHERE s.name = '{schema}' AND o.name = '{obj_name}'
            )
            BEGIN
                SELECT
                    '{schema}' AS schema_name,
                    '{obj_name}' AS object_name,
                    'NOT_FOUND' AS object_type,
                    'NOT_FOUND' AS status,
                    NULL AS index_name,
                    NULL AS stats_name,
                    NULL AS last_updated,
                    NULL AS days_old,
                    NULL AS rows_sampled,
                    NULL AS modification_counter,
                    'Objeto não encontrado no banco [{target_database}]' AS recommendation;
            END
            ELSE IF EXISTS (
                SELECT 1 FROM sys.objects o
                JOIN sys.schemas s ON o.schema_id = s.schema_id
                WHERE s.name = '{schema}' AND o.name = '{obj_name}' AND o.type = 'V'
            )
            BEGIN
                SELECT
                    '{schema}' AS schema_name,
                    '{obj_name}' AS object_name,
                    'VIEW' AS object_type,
                    'FOUND' AS status,
                    NULL AS index_name,
                    NULL AS stats_name,
                    NULL AS last_updated,
                    NULL AS days_old,
                    NULL AS rows_sampled,
                    NULL AS modification_counter,
                    'VIEW - Verificar tabelas subjacentes' AS recommendation;
            END
            ELSE
            BEGIN
                -- STATS_DATE() é mais confiável que dm_db_stats_properties.last_updated
                -- DEBUG: incluindo sp.last_updated e object_id para comparação
                SELECT
                    s.name AS schema_name,
                    o.name AS object_name,
                    'USER_TABLE' AS object_type,
                    'FOUND' AS status,
                    ISNULL(i.name, 'HEAP') AS index_name,
                    st.name AS stats_name,
                    STATS_DATE(o.object_id, st.stats_id) AS last_updated,
                    DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS days_old,
                    sp.rows AS rows_sampled,
                    sp.modification_counter,
                    CASE
                        WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 'CRÍTICO - Nunca teve estatísticas'
                        WHEN DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) > {threshold_days} THEN
                            'DESATUALIZADO - ' + CAST(DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS VARCHAR) + ' dias'
                        WHEN sp.modification_counter > sp.rows * 0.2 AND sp.rows > 0 THEN
                            'MODIFICADO - ' + CAST(ISNULL(sp.modification_counter, 0) AS VARCHAR) + ' alterações'
                        ELSE 'OK - Estatísticas atualizadas'
                    END AS recommendation,
                    @@SERVERNAME AS server_queried,
                    DB_NAME() AS database_queried,
                    sp.last_updated AS dmv_last_updated,
                    o.object_id AS debug_object_id
                FROM sys.objects o
                JOIN sys.schemas s ON o.schema_id = s.schema_id
                JOIN sys.stats st ON o.object_id = st.object_id
                LEFT JOIN sys.indexes i ON o.object_id = i.object_id AND st.stats_id = i.index_id
                OUTER APPLY sys.dm_db_stats_properties(o.object_id, st.stats_id) sp
                WHERE s.name = '{schema}' AND o.name = '{obj_name}'
                ORDER BY
                    CASE WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 0 ELSE 1 END,
                    days_old DESC;
            END
            """
            else:
                # Sem database especificado - usar query no contexto atual (master)
                check_query = f"""
            SET NOCOUNT ON;

            -- Verificar se objeto existe
            IF NOT EXISTS (
                SELECT 1 FROM sys.objects o
                JOIN sys.schemas s ON o.schema_id = s.schema_id
                WHERE s.name = '{schema}' AND o.name = '{obj_name}'
            )
            BEGIN
                SELECT
                    '{schema}' AS schema_name,
                    '{obj_name}' AS object_name,
                    'NOT_FOUND' AS object_type,
                    'NOT_FOUND' AS status,
                    NULL AS index_name,
                    NULL AS stats_name,
                    NULL AS last_updated,
                    NULL AS days_old,
                    NULL AS rows_sampled,
                    NULL AS modification_counter,
                    'Objeto não encontrado no banco atual' AS recommendation;
            END
            ELSE IF EXISTS (
                SELECT 1 FROM sys.objects o
                JOIN sys.schemas s ON o.schema_id = s.schema_id
                WHERE s.name = '{schema}' AND o.name = '{obj_name}' AND o.type = 'V'
            )
            BEGIN
                SELECT
                    '{schema}' AS schema_name,
                    '{obj_name}' AS object_name,
                    'VIEW' AS object_type,
                    'FOUND' AS status,
                    NULL AS index_name,
                    NULL AS stats_name,
                    NULL AS last_updated,
                    NULL AS days_old,
                    NULL AS rows_sampled,
                    NULL AS modification_counter,
                    'VIEW - Verificar tabelas subjacentes' AS recommendation;
            END
            ELSE
            BEGIN
                -- STATS_DATE() é mais confiável que dm_db_stats_properties.last_updated
                SELECT
                    s.name AS schema_name,
                    o.name AS object_name,
                    'USER_TABLE' AS object_type,
                    'FOUND' AS status,
                    ISNULL(i.name, 'HEAP') AS index_name,
                    st.name AS stats_name,
                    STATS_DATE(o.object_id, st.stats_id) AS last_updated,
                    DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS days_old,
                    sp.rows AS rows_sampled,
                    sp.modification_counter,
                    CASE
                        WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 'CRÍTICO - Nunca teve estatísticas'
                        WHEN DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) > {threshold_days} THEN
                            'DESATUALIZADO - ' + CAST(DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS VARCHAR) + ' dias'
                        WHEN sp.modification_counter > sp.rows * 0.2 AND sp.rows > 0 THEN
                            'MODIFICADO - ' + CAST(ISNULL(sp.modification_counter, 0) AS VARCHAR) + ' alterações'
                        ELSE 'OK - Estatísticas atualizadas'
                    END AS recommendation,
                    @@SERVERNAME AS server_queried,
                    DB_NAME() AS database_queried
                FROM sys.objects o
                JOIN sys.schemas s ON o.schema_id = s.schema_id
                JOIN sys.stats st ON o.object_id = st.object_id
                LEFT JOIN sys.indexes i ON o.object_id = i.object_id AND st.stats_id = i.index_id
                OUTER APPLY sys.dm_db_stats_properties(o.object_id, st.stats_id) sp
                WHERE s.name = '{schema}' AND o.name = '{obj_name}'
                ORDER BY
                    CASE WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 0 ELSE 1 END,
                    days_old DESC;
            END
            """

            try:
                logger.info(f"[Diagnose Query] Executando query para {target_database or 'master'}.{schema}.{obj_name}")
                obj_results = await execute_query_on_server(server_id, check_query)
                logger.info(f"[Diagnose Query] Resultado para {schema}.{obj_name}: {len(obj_results)} linhas")

                if obj_results:
                    # DEBUG: Logar todas as informações de data para diagnóstico
                    first_row = obj_results[0]
                    logger.info(f"[Diagnose Query] DEBUG DATAS - Tabela: {first_row.get('object_name')}")
                    logger.info(f"[Diagnose Query] DEBUG DATAS - STATS_DATE (last_updated): {first_row.get('last_updated')}")
                    logger.info(f"[Diagnose Query] DEBUG DATAS - DMV last_updated: {first_row.get('dmv_last_updated')}")
                    logger.info(f"[Diagnose Query] DEBUG DATAS - days_old: {first_row.get('days_old')}")
                    logger.info(f"[Diagnose Query] DEBUG DATAS - object_id: {first_row.get('debug_object_id')}")
                    logger.info(f"[Diagnose Query] DEBUG DATAS - server_queried: {first_row.get('server_queried')}, database_queried: {first_row.get('database_queried')}")

                for row in obj_results:
                    obj_type = row.get("object_type", "UNKNOWN")

                    results.append({
                        "schema_name": row.get("schema_name", schema),
                        "object_name": row.get("object_name", obj_name),
                        "object_type": obj_type,
                        "index_name": row.get("index_name"),
                        "stats_name": row.get("stats_name"),
                        "last_updated": str(row.get("last_updated")) if row.get("last_updated") else None,
                        "days_old": row.get("days_old"),
                        "rows_sampled": row.get("rows_sampled"),
                        "modification_counter": row.get("modification_counter"),
                        "recommendation": row.get("recommendation", ""),
                        "status": row.get("status", "UNKNOWN")
                    })

                    # Gerar comando UPDATE STATISTICS se necessário
                    rec = row.get("recommendation", "")
                    if "CRÍTICO" in rec or "DESATUALIZADO" in rec or "MODIFICADO" in rec:
                        if target_database:
                            cmd = f"USE [{target_database}]; UPDATE STATISTICS [{schema}].[{obj_name}] WITH FULLSCAN;"
                        else:
                            cmd = f"UPDATE STATISTICS [{schema}].[{obj_name}] WITH FULLSCAN;"
                        if cmd not in update_commands:
                            update_commands.append(cmd)

                    # =====================================================
                    # EXPANSÃO DE VIEW: Buscar tabelas base da VIEW
                    # =====================================================
                    if obj_type == "VIEW":
                        logger.info(f"[Diagnose Query] VIEW detectada: {schema}.{obj_name} - Expandindo para tabelas base...")
                        try:
                            # Query para obter as tabelas referenciadas pela VIEW
                            view_expansion_query = f"""
                            USE [{target_database}];
                            SET NOCOUNT ON;

                            -- Buscar todas as tabelas referenciadas pela VIEW usando sys.dm_sql_referenced_entities
                            SELECT DISTINCT
                                ref.referenced_schema_name AS base_schema,
                                ref.referenced_entity_name AS base_table,
                                CASE
                                    WHEN o.type = 'U' THEN 'USER_TABLE'
                                    WHEN o.type = 'V' THEN 'VIEW'
                                    ELSE 'OTHER'
                                END AS base_object_type
                            FROM sys.dm_sql_referenced_entities('[{schema}].[{obj_name}]', 'OBJECT') ref
                            LEFT JOIN sys.objects o ON o.object_id = OBJECT_ID(QUOTENAME(ref.referenced_schema_name) + '.' + QUOTENAME(ref.referenced_entity_name))
                            WHERE ref.referenced_entity_name IS NOT NULL
                              AND ref.referenced_schema_name IS NOT NULL
                              AND ref.referenced_minor_name IS NULL  -- Exclui colunas, pega só tabelas
                            ORDER BY ref.referenced_schema_name, ref.referenced_entity_name;
                            """

                            view_tables = await execute_query_on_server(server_id, view_expansion_query)
                            logger.info(f"[Diagnose Query] VIEW {schema}.{obj_name} tem {len(view_tables)} tabelas/views base")

                            # Para cada tabela base encontrada, analisar estatísticas
                            for base_obj in view_tables:
                                base_schema = base_obj.get("base_schema")
                                base_table = base_obj.get("base_table")
                                base_type = base_obj.get("base_object_type", "USER_TABLE")

                                if not base_schema or not base_table:
                                    continue

                                logger.info(f"[Diagnose Query] Analisando tabela base da VIEW: [{base_schema}].[{base_table}] ({base_type})")

                                # Verificar se já analisamos esta tabela (evitar duplicatas)
                                already_analyzed = any(
                                    r.get("schema_name") == base_schema and r.get("object_name") == base_table
                                    for r in results
                                )
                                if already_analyzed:
                                    logger.info(f"[Diagnose Query] Tabela {base_schema}.{base_table} já foi analisada, pulando...")
                                    continue

                                # Se for outra VIEW, apenas registrar (evitar recursão infinita)
                                if base_type == "VIEW":
                                    results.append({
                                        "schema_name": base_schema,
                                        "object_name": base_table,
                                        "object_type": "VIEW",
                                        "index_name": None,
                                        "stats_name": None,
                                        "last_updated": None,
                                        "days_old": None,
                                        "rows_sampled": None,
                                        "modification_counter": None,
                                        "recommendation": f"VIEW aninhada (base de {schema}.{obj_name}) - Verificar tabelas subjacentes",
                                        "status": "FOUND",
                                        "is_base_of_view": f"{schema}.{obj_name}"
                                    })
                                    continue

                                # Buscar estatísticas da tabela base
                                base_stats_query = f"""
                                USE [{target_database}];
                                SET NOCOUNT ON;

                                SELECT
                                    s.name AS schema_name,
                                    o.name AS object_name,
                                    'USER_TABLE' AS object_type,
                                    'FOUND' AS status,
                                    ISNULL(i.name, 'HEAP') AS index_name,
                                    st.name AS stats_name,
                                    STATS_DATE(o.object_id, st.stats_id) AS last_updated,
                                    DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS days_old,
                                    sp.rows AS rows_sampled,
                                    sp.modification_counter,
                                    CASE
                                        WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 'CRÍTICO - Nunca teve estatísticas'
                                        WHEN DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) > {threshold_days} THEN
                                            'DESATUALIZADO - ' + CAST(DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS VARCHAR) + ' dias'
                                        WHEN sp.modification_counter > sp.rows * 0.2 AND sp.rows > 0 THEN
                                            'MODIFICADO - ' + CAST(ISNULL(sp.modification_counter, 0) AS VARCHAR) + ' alterações'
                                        ELSE 'OK - Estatísticas atualizadas'
                                    END AS recommendation
                                FROM sys.objects o
                                JOIN sys.schemas s ON o.schema_id = s.schema_id
                                JOIN sys.stats st ON o.object_id = st.object_id
                                LEFT JOIN sys.indexes i ON o.object_id = i.object_id AND st.stats_id = i.index_id
                                OUTER APPLY sys.dm_db_stats_properties(o.object_id, st.stats_id) sp
                                WHERE s.name = '{base_schema}' AND o.name = '{base_table}'
                                ORDER BY
                                    CASE WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 0 ELSE 1 END,
                                    days_old DESC;
                                """

                                base_stats_results = await execute_query_on_server(server_id, base_stats_query)

                                if base_stats_results:
                                    for base_row in base_stats_results:
                                        results.append({
                                            "schema_name": base_row.get("schema_name", base_schema),
                                            "object_name": base_row.get("object_name", base_table),
                                            "object_type": base_row.get("object_type", "USER_TABLE"),
                                            "index_name": base_row.get("index_name"),
                                            "stats_name": base_row.get("stats_name"),
                                            "last_updated": str(base_row.get("last_updated")) if base_row.get("last_updated") else None,
                                            "days_old": base_row.get("days_old"),
                                            "rows_sampled": base_row.get("rows_sampled"),
                                            "modification_counter": base_row.get("modification_counter"),
                                            "recommendation": base_row.get("recommendation", ""),
                                            "status": base_row.get("status", "FOUND"),
                                            "is_base_of_view": f"{schema}.{obj_name}"
                                        })

                                        # Gerar comando UPDATE STATISTICS para tabela base se necessário
                                        base_rec = base_row.get("recommendation", "")
                                        if "CRÍTICO" in base_rec or "DESATUALIZADO" in base_rec or "MODIFICADO" in base_rec:
                                            base_cmd = f"USE [{target_database}]; UPDATE STATISTICS [{base_schema}].[{base_table}] WITH FULLSCAN;"
                                            if base_cmd not in update_commands:
                                                update_commands.append(base_cmd)
                                else:
                                    # Tabela não encontrada ou sem estatísticas
                                    results.append({
                                        "schema_name": base_schema,
                                        "object_name": base_table,
                                        "object_type": "USER_TABLE",
                                        "index_name": None,
                                        "stats_name": None,
                                        "last_updated": None,
                                        "days_old": None,
                                        "rows_sampled": None,
                                        "modification_counter": None,
                                        "recommendation": f"Tabela base de VIEW {schema}.{obj_name} - Sem estatísticas ou não encontrada",
                                        "status": "WARNING",
                                        "is_base_of_view": f"{schema}.{obj_name}"
                                    })

                        except Exception as view_error:
                            logger.warning(f"[Diagnose Query] Erro ao expandir VIEW {schema}.{obj_name}: {view_error}")

            except Exception as obj_error:
                logger.warning(f"Erro ao analisar {schema}.{obj_name} no banco {target_database or 'master'}: {obj_error}")
                results.append({
                    "schema_name": schema,
                    "object_name": obj_name,
                    "object_type": "ERROR",
                    "index_name": None,
                    "stats_name": None,
                    "last_updated": None,
                    "days_old": None,
                    "rows_sampled": None,
                    "modification_counter": None,
                    "recommendation": f"Erro ao analisar: {str(obj_error)}",
                    "status": "ERROR"
                })

        # =====================================================
        # ANÁLISE DE ÍNDICES FALTANTES (Missing Indexes)
        # =====================================================
        missing_indexes = []
        create_index_commands = []
        index_names_used = set()  # Rastrear nomes de índices já usados para evitar duplicatas

        # Buscar missing indexes para as tabelas encontradas
        for obj_tuple in objects:
            obj_database, schema, obj_name = obj_tuple
            target_db = obj_database or detected_database

            if target_db:
                missing_idx_query = f"""
            USE [{target_db}];
            -- Missing Indexes sugeridos pelo SQL Server para esta tabela
            SELECT TOP 10
                '{schema}' AS schema_name,
                '{obj_name}' AS table_name,
                migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans) AS improvement_measure,
                migs.avg_total_user_cost,
                migs.avg_user_impact,
                migs.user_seeks,
                migs.user_scans,
                mid.equality_columns,
                mid.inequality_columns,
                mid.included_columns,
                mid.index_handle
            FROM sys.dm_db_missing_index_details mid
            JOIN sys.dm_db_missing_index_groups mig ON mid.index_handle = mig.index_handle
            JOIN sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
            JOIN sys.objects o ON mid.object_id = o.object_id
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE s.name = '{schema}' AND o.name = '{obj_name}'
            ORDER BY improvement_measure DESC
            """
            else:
                missing_idx_query = f"""
            -- Missing Indexes sugeridos pelo SQL Server para esta tabela
            SELECT TOP 10
                '{schema}' AS schema_name,
                '{obj_name}' AS table_name,
                migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans) AS improvement_measure,
                migs.avg_total_user_cost,
                migs.avg_user_impact,
                migs.user_seeks,
                migs.user_scans,
                mid.equality_columns,
                mid.inequality_columns,
                mid.included_columns,
                mid.index_handle
            FROM sys.dm_db_missing_index_details mid
            JOIN sys.dm_db_missing_index_groups mig ON mid.index_handle = mig.index_handle
            JOIN sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
            JOIN sys.objects o ON mid.object_id = o.object_id
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE s.name = '{schema}' AND o.name = '{obj_name}'
            ORDER BY improvement_measure DESC
            """

            try:
                idx_results = await execute_query_on_server(server_id, missing_idx_query)

                for row in idx_results:
                    improvement = row.get("improvement_measure", 0) or 0
                    if improvement > 1000:  # Threshold de impacto significativo
                        eq_cols = row.get("equality_columns") or ""
                        ineq_cols = row.get("inequality_columns") or ""
                        incl_cols = row.get("included_columns")
                        index_handle = row.get("index_handle", 0)

                        # Gerar nome único do índice usando hash do index_handle
                        base_name = f"IX_{obj_name}"
                        col_suffix = (eq_cols + "_" + ineq_cols).replace("[", "").replace("]", "").replace(", ", "_").replace(" ", "")
                        if len(col_suffix) > 50:
                            col_suffix = col_suffix[:50]

                        index_name = f"{base_name}_{col_suffix}"

                        # Se nome já usado, adicionar sufixo único com index_handle
                        if index_name in index_names_used:
                            index_name = f"{base_name}_{index_handle}"

                        index_names_used.add(index_name)

                        # Construir colunas do índice
                        key_columns = eq_cols
                        if eq_cols and ineq_cols:
                            key_columns = f"{eq_cols}, {ineq_cols}"
                        elif ineq_cols:
                            key_columns = ineq_cols

                        # Gerar script com IF NOT EXISTS
                        if target_db:
                            create_script = f"""USE [{target_db}];
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = '{index_name}'
      AND object_id = OBJECT_ID('[{schema}].[{obj_name}]')
)
CREATE NONCLUSTERED INDEX [{index_name}]
ON [{schema}].[{obj_name}] ({key_columns})"""
                        else:
                            create_script = f"""IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = '{index_name}'
      AND object_id = OBJECT_ID('[{schema}].[{obj_name}]')
)
CREATE NONCLUSTERED INDEX [{index_name}]
ON [{schema}].[{obj_name}] ({key_columns})"""

                        if incl_cols:
                            create_script += f"\nINCLUDE ({incl_cols})"
                        create_script += ";"

                        missing_indexes.append({
                            "schema_name": row.get("schema_name", schema),
                            "table_name": row.get("table_name", obj_name),
                            "index_name": index_name,
                            "improvement_measure": float(improvement),
                            "avg_user_impact": row.get("avg_user_impact"),
                            "user_seeks": row.get("user_seeks"),
                            "user_scans": row.get("user_scans"),
                            "equality_columns": eq_cols or None,
                            "inequality_columns": ineq_cols or None,
                            "included_columns": incl_cols,
                            "key_columns": key_columns,
                            "create_index_script": create_script
                        })

                        if create_script not in create_index_commands:
                            create_index_commands.append(create_script)

            except Exception as idx_error:
                logger.debug(f"Erro ao buscar missing indexes para {schema}.{obj_name}: {idx_error}")

        # =====================================================
        # ANÁLISE DE REDUNDÂNCIA E CONSOLIDAÇÃO DE ÍNDICES
        # =====================================================
        index_analysis = {
            "redundant_suggestions": [],
            "merge_candidates": [],
            "consolidation_tips": []
        }

        # Agrupar sugestões por tabela para análise
        indexes_by_table = {}
        for idx in missing_indexes:
            table_key = f"{idx['schema_name']}.{idx['table_name']}"
            if table_key not in indexes_by_table:
                indexes_by_table[table_key] = []
            indexes_by_table[table_key].append(idx)

        for table_key, table_indexes in indexes_by_table.items():
            if len(table_indexes) > 1:
                # Analisar redundância: índices com as mesmas colunas de igualdade
                eq_cols_seen = {}
                for idx in table_indexes:
                    eq = idx.get("equality_columns") or ""
                    if eq in eq_cols_seen:
                        # Índice potencialmente redundante
                        index_analysis["redundant_suggestions"].append({
                            "table": table_key,
                            "index_1": eq_cols_seen[eq]["index_name"],
                            "index_2": idx["index_name"],
                            "reason": f"Ambos índices têm as mesmas colunas de igualdade: {eq}",
                            "recommendation": "Considere criar apenas o índice com mais colunas INCLUDE ou maior impacto"
                        })
                    else:
                        eq_cols_seen[eq] = idx

                # Analisar merge: índices que poderiam ser consolidados
                # Se temos múltiplos índices na mesma tabela com colunas sobrepostas
                for i, idx1 in enumerate(table_indexes):
                    for idx2 in table_indexes[i+1:]:
                        eq1 = set((idx1.get("equality_columns") or "").replace("[", "").replace("]", "").split(", "))
                        eq2 = set((idx2.get("equality_columns") or "").replace("[", "").replace("]", "").split(", "))
                        eq1.discard("")
                        eq2.discard("")

                        # Se um é subconjunto do outro, possível merge
                        if eq1 and eq2 and (eq1.issubset(eq2) or eq2.issubset(eq1)):
                            larger = idx1 if len(eq1) >= len(eq2) else idx2
                            smaller = idx2 if len(eq1) >= len(eq2) else idx1

                            # Combinar INCLUDE columns
                            incl1 = set((idx1.get("included_columns") or "").replace("[", "").replace("]", "").split(", "))
                            incl2 = set((idx2.get("included_columns") or "").replace("[", "").replace("]", "").split(", "))
                            incl1.discard("")
                            incl2.discard("")
                            merged_incl = incl1.union(incl2)

                            index_analysis["merge_candidates"].append({
                                "table": table_key,
                                "index_1": idx1["index_name"],
                                "index_2": idx2["index_name"],
                                "reason": f"Colunas de {smaller['index_name']} são subconjunto de {larger['index_name']}",
                                "recommendation": f"Criar apenas {larger['index_name']} com INCLUDE adicional: {', '.join(merged_incl) if merged_incl else 'nenhum'}",
                                "merged_index_suggestion": {
                                    "key_columns": larger.get("key_columns"),
                                    "include_columns": ", ".join(merged_incl) if merged_incl else None,
                                    "estimated_impact": max(idx1.get("improvement_measure", 0), idx2.get("improvement_measure", 0))
                                }
                            })

                # Dicas de consolidação se muitos índices sugeridos
                if len(table_indexes) >= 3:
                    index_analysis["consolidation_tips"].append({
                        "table": table_key,
                        "suggested_indexes_count": len(table_indexes),
                        "tip": f"Muitos índices sugeridos ({len(table_indexes)}) para {table_key}. "
                               f"Cada índice adicional aumenta custo de escrita (INSERT/UPDATE/DELETE). "
                               f"Considere: 1) Criar apenas os de maior impacto (>10000), "
                               f"2) Combinar índices com colunas sobrepostas, "
                               f"3) Avaliar padrões de uso real antes de criar todos.",
                        "total_write_overhead_estimate": f"~{len(table_indexes) * 5}% overhead em operações de escrita"
                    })

        # =====================================================
        # COMPARAÇÃO COM ÍNDICES EXISTENTES
        # =====================================================
        # Esta seção analisa os índices JÁ existentes nas tabelas e compara
        # com os sugeridos para identificar se devemos:
        # - CREATE: Criar novo índice (não existe nada similar)
        # - ALTER: Modificar índice existente (adicionar colunas INCLUDE)
        # - SKIP: Ignorar (já existe índice igual ou melhor)

        existing_indexes = {}  # {table_key: [list of existing indexes]}
        index_comparison_results = []  # Resultado da comparação

        for obj_tuple in objects:
            obj_database, schema, obj_name = obj_tuple
            target_db = obj_database or detected_database
            table_key = f"{schema}.{obj_name}"

            if target_db:
                # Query para buscar índices existentes com detalhes das colunas
                existing_idx_query = f"""
            USE [{target_db}];
            SELECT
                i.name AS index_name,
                i.type_desc AS index_type,
                i.is_unique,
                i.is_primary_key,
                -- Colunas KEY do índice (ordenadas)
                STUFF((
                    SELECT ', ' + QUOTENAME(c.name)
                    FROM sys.index_columns ic
                    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                    WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
                    ORDER BY ic.key_ordinal
                    FOR XML PATH('')
                ), 1, 2, '') AS key_columns,
                -- Colunas INCLUDE do índice
                STUFF((
                    SELECT ', ' + QUOTENAME(c.name)
                    FROM sys.index_columns ic
                    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                    WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 1
                    ORDER BY ic.index_column_id
                    FOR XML PATH('')
                ), 1, 2, '') AS include_columns,
                -- Estatísticas de uso do índice
                ISNULL(ius.user_seeks, 0) AS user_seeks,
                ISNULL(ius.user_scans, 0) AS user_scans,
                ISNULL(ius.user_lookups, 0) AS user_lookups,
                ISNULL(ius.user_updates, 0) AS user_updates,
                -- Tamanho do índice
                CAST(SUM(ps.used_page_count) * 8.0 / 1024 AS DECIMAL(18,2)) AS size_mb
            FROM sys.indexes i
            JOIN sys.objects o ON i.object_id = o.object_id
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            LEFT JOIN sys.dm_db_index_usage_stats ius
                ON i.object_id = ius.object_id AND i.index_id = ius.index_id AND ius.database_id = DB_ID()
            LEFT JOIN sys.dm_db_partition_stats ps
                ON i.object_id = ps.object_id AND i.index_id = ps.index_id
            WHERE s.name = '{schema}'
              AND o.name = '{obj_name}'
              AND i.type > 0  -- Excluir HEAP (type=0)
              AND i.is_hypothetical = 0
            GROUP BY i.name, i.type_desc, i.is_unique, i.is_primary_key, i.object_id, i.index_id,
                     ius.user_seeks, ius.user_scans, ius.user_lookups, ius.user_updates
            ORDER BY i.is_primary_key DESC, i.is_unique DESC, i.name
            """

                try:
                    existing_results = await execute_query_on_server(server_id, existing_idx_query)
                    existing_indexes[table_key] = []

                    for row in existing_results:
                        existing_indexes[table_key].append({
                            "index_name": row.get("index_name"),
                            "index_type": row.get("index_type"),
                            "is_unique": row.get("is_unique"),
                            "is_primary_key": row.get("is_primary_key"),
                            "key_columns": row.get("key_columns") or "",
                            "include_columns": row.get("include_columns") or "",
                            "user_seeks": row.get("user_seeks", 0),
                            "user_scans": row.get("user_scans", 0),
                            "user_lookups": row.get("user_lookups", 0),
                            "user_updates": row.get("user_updates", 0),
                            "size_mb": float(row.get("size_mb") or 0)
                        })

                except Exception as ex_idx_error:
                    logger.debug(f"Erro ao buscar índices existentes para {table_key}: {ex_idx_error}")

        # Função auxiliar para normalizar e comparar colunas
        def normalize_columns(cols_str):
            """Normaliza string de colunas para comparação (remove [], espaços extras, lowercase)"""
            if not cols_str:
                return set()
            # Remove colchetes, espaços extras, converte para lowercase
            cols = cols_str.replace("[", "").replace("]", "").replace(" ", "")
            return set(c.strip().lower() for c in cols.split(",") if c.strip())

        # Comparar cada índice sugerido com os existentes
        for suggested_idx in missing_indexes:
            table_key = f"{suggested_idx['schema_name']}.{suggested_idx['table_name']}"
            existing_for_table = existing_indexes.get(table_key, [])

            suggested_key_cols = normalize_columns(suggested_idx.get("key_columns", ""))
            suggested_eq_cols = normalize_columns(suggested_idx.get("equality_columns", ""))
            suggested_incl_cols = normalize_columns(suggested_idx.get("included_columns", ""))

            comparison = {
                "table": table_key,
                "suggested_index": suggested_idx["index_name"],
                "suggested_key_columns": suggested_idx.get("key_columns", ""),
                "suggested_include_columns": suggested_idx.get("included_columns", ""),
                "improvement_measure": suggested_idx.get("improvement_measure", 0),
                "action": "CREATE",  # Default: criar novo
                "reason": "Nenhum índice existente cobre estas colunas",
                "existing_index": None,
                "recommendation_details": None
            }

            best_match = None
            best_match_score = 0

            for existing in existing_for_table:
                existing_key_cols = normalize_columns(existing.get("key_columns", ""))
                existing_incl_cols = normalize_columns(existing.get("include_columns", ""))

                # Calcular score de similaridade
                # Score baseado em: colunas KEY em comum, colunas INCLUDE em comum
                if not suggested_key_cols:
                    continue

                # Verificar cobertura das colunas KEY
                key_overlap = suggested_key_cols.intersection(existing_key_cols)
                key_coverage = len(key_overlap) / len(suggested_key_cols) if suggested_key_cols else 0

                # Verificar se as primeiras colunas do índice existente cobrem as colunas de igualdade
                # (importante para leftmost prefix)
                existing_key_list = [c.strip().lower().replace("[", "").replace("]", "")
                                     for c in (existing.get("key_columns", "") or "").split(",") if c.strip()]

                leftmost_match = False
                if existing_key_list and suggested_eq_cols:
                    # Verificar se as N primeiras colunas do índice existente = colunas de igualdade sugeridas
                    first_n_cols = set(existing_key_list[:len(suggested_eq_cols)])
                    leftmost_match = suggested_eq_cols.issubset(first_n_cols) or first_n_cols == suggested_eq_cols

                # Verificar cobertura das colunas INCLUDE
                incl_coverage = 0
                missing_includes = set()
                if suggested_incl_cols:
                    all_covered_cols = existing_key_cols.union(existing_incl_cols)
                    incl_overlap = suggested_incl_cols.intersection(all_covered_cols)
                    incl_coverage = len(incl_overlap) / len(suggested_incl_cols)
                    missing_includes = suggested_incl_cols - all_covered_cols

                # Calcular score total
                score = (key_coverage * 0.7) + (incl_coverage * 0.3)
                if leftmost_match:
                    score += 0.2  # Bonus para leftmost prefix match

                if score > best_match_score:
                    best_match_score = score
                    best_match = {
                        "existing": existing,
                        "key_coverage": key_coverage,
                        "incl_coverage": incl_coverage,
                        "leftmost_match": leftmost_match,
                        "missing_includes": missing_includes,
                        "score": score
                    }

            # Determinar ação baseada no score
            if best_match:
                existing = best_match["existing"]

                if best_match["score"] >= 0.95:
                    # Índice existente cobre completamente ou quase completamente
                    comparison["action"] = "SKIP"
                    comparison["reason"] = f"Índice existente '{existing['index_name']}' já cobre estas colunas"
                    comparison["existing_index"] = existing["index_name"]
                    comparison["recommendation_details"] = {
                        "type": "EXISTING_SUFFICIENT",
                        "existing_index_name": existing["index_name"],
                        "existing_key_columns": existing.get("key_columns"),
                        "existing_include_columns": existing.get("include_columns"),
                        "usage_stats": {
                            "seeks": existing.get("user_seeks", 0),
                            "scans": existing.get("user_scans", 0),
                            "updates": existing.get("user_updates", 0)
                        }
                    }

                elif best_match["key_coverage"] >= 0.8 and best_match["missing_includes"]:
                    # Índice existente tem boas colunas KEY mas faltam INCLUDEs
                    comparison["action"] = "ALTER"
                    comparison["reason"] = f"Índice '{existing['index_name']}' pode ser expandido com INCLUDE adicional"
                    comparison["existing_index"] = existing["index_name"]
                    missing_incl_str = ", ".join(f"[{c}]" for c in best_match["missing_includes"])

                    # Gerar script de ALTER (DROP + CREATE com novas colunas)
                    new_includes = existing.get("include_columns", "")
                    if new_includes:
                        new_includes += ", " + missing_incl_str
                    else:
                        new_includes = missing_incl_str

                    alter_script = f"""-- ATENÇÃO: Modificar índice existente requer DROP + CREATE
-- Avalie o impacto em produção antes de executar

-- Índice atual: {existing['index_name']}
-- Colunas KEY: {existing.get('key_columns')}
-- Colunas INCLUDE atuais: {existing.get('include_columns') or 'nenhuma'}
-- Colunas INCLUDE sugeridas para adicionar: {missing_incl_str}

USE [{target_db}];
-- Opção 1: Criar novo índice com INCLUDE expandido (mais seguro)
CREATE NONCLUSTERED INDEX [{existing['index_name']}_expanded]
ON [{schema}].[{obj_name}] ({existing.get('key_columns')})
INCLUDE ({new_includes})
WITH (ONLINE = ON, DROP_EXISTING = OFF);

-- Opção 2: Após validar, remover índice antigo
-- DROP INDEX [{existing['index_name']}] ON [{schema}].[{obj_name}];
-- EXEC sp_rename N'{schema}.{obj_name}.{existing['index_name']}_expanded', N'{existing['index_name']}', N'INDEX';
"""
                    comparison["recommendation_details"] = {
                        "type": "EXPAND_EXISTING",
                        "existing_index_name": existing["index_name"],
                        "existing_key_columns": existing.get("key_columns"),
                        "existing_include_columns": existing.get("include_columns"),
                        "missing_include_columns": list(best_match["missing_includes"]),
                        "alter_script": alter_script,
                        "impact_notes": "Expandir INCLUDE é geralmente seguro e melhora performance sem overhead significativo"
                    }

                elif best_match["leftmost_match"] and best_match["key_coverage"] >= 0.5:
                    # Há sobreposição parcial - avaliar se vale criar
                    comparison["action"] = "EVALUATE"
                    comparison["reason"] = f"Índice '{existing['index_name']}' tem sobreposição parcial ({int(best_match['key_coverage']*100)}%)"
                    comparison["existing_index"] = existing["index_name"]
                    comparison["recommendation_details"] = {
                        "type": "PARTIAL_OVERLAP",
                        "existing_index_name": existing["index_name"],
                        "existing_key_columns": existing.get("key_columns"),
                        "overlap_percentage": int(best_match["key_coverage"] * 100),
                        "suggestion": "Se o índice existente já atende bem as queries, pode não valer criar outro. "
                                     "Monitore sys.dm_db_index_usage_stats por 1-2 semanas antes de decidir.",
                        "decision_factors": [
                            f"Impacto sugerido: {suggested_idx.get('improvement_measure', 0):,.0f}",
                            f"Uso atual do índice existente: {existing.get('user_seeks', 0):,} seeks, {existing.get('user_scans', 0):,} scans",
                            f"Custo de escrita atual: {existing.get('user_updates', 0):,} updates"
                        ]
                    }

            index_comparison_results.append(comparison)

        # Adicionar ao index_analysis
        index_analysis["existing_indexes"] = existing_indexes
        index_analysis["comparison_results"] = index_comparison_results

        # Resumo da comparação
        actions_summary = {
            "CREATE": len([c for c in index_comparison_results if c["action"] == "CREATE"]),
            "ALTER": len([c for c in index_comparison_results if c["action"] == "ALTER"]),
            "SKIP": len([c for c in index_comparison_results if c["action"] == "SKIP"]),
            "EVALUATE": len([c for c in index_comparison_results if c["action"] == "EVALUATE"])
        }
        index_analysis["comparison_summary"] = actions_summary

        # =====================================================
        # VERIFICAR SE TABELAS SÃO HEAP (sem clustered index)
        # =====================================================
        heap_tables = []
        for obj_tuple in objects:
            obj_database, schema, obj_name = obj_tuple
            target_db = obj_database or detected_database

            if target_db:
                heap_query = f"""
            USE [{target_db}];
            SELECT
                s.name AS schema_name,
                o.name AS table_name,
                CASE WHEN NOT EXISTS (
                    SELECT 1 FROM sys.indexes i
                    WHERE i.object_id = o.object_id AND i.type = 1  -- Clustered
                ) THEN 1 ELSE 0 END AS is_heap,
                (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = o.object_id AND p.index_id IN (0,1)) AS row_count
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE s.name = '{schema}' AND o.name = '{obj_name}' AND o.type = 'U'
            """
            else:
                heap_query = f"""
            SELECT
                s.name AS schema_name,
                o.name AS table_name,
                CASE WHEN NOT EXISTS (
                    SELECT 1 FROM sys.indexes i
                    WHERE i.object_id = o.object_id AND i.type = 1  -- Clustered
                ) THEN 1 ELSE 0 END AS is_heap,
                (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = o.object_id AND p.index_id IN (0,1)) AS row_count
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE s.name = '{schema}' AND o.name = '{obj_name}' AND o.type = 'U'
            """

            try:
                heap_results = await execute_query_on_server(server_id, heap_query)
                for row in heap_results:
                    if row.get("is_heap") == 1:
                        heap_tables.append({
                            "schema_name": row.get("schema_name"),
                            "table_name": row.get("table_name"),
                            "row_count": row.get("row_count"),
                            "recommendation": "HEAP - Tabela sem clustered index. Considere criar um para melhor performance."
                        })
            except Exception as heap_error:
                logger.debug(f"Erro ao verificar heap para {schema}.{obj_name}: {heap_error}")

        # =====================================================
        # ANÁLISE INTELIGENTE: UPDATE STATISTICS vs CREATE INDEX
        # =====================================================
        diagnosis = []

        # Verificar estatísticas desatualizadas
        stats_issues = [r for r in results if "CRÍTICO" in r.get("recommendation", "") or "DESATUALIZADO" in r.get("recommendation", "") or "MODIFICADO" in r.get("recommendation", "")]

        if stats_issues:
            diagnosis.append({
                "priority": 1,
                "action": "UPDATE_STATISTICS",
                "reason": f"{len(stats_issues)} tabela(s) com estatísticas desatualizadas ou modificadas",
                "explanation": "Estatísticas desatualizadas podem causar planos de execução ruins. UPDATE STATISTICS é rápido e não requer lock exclusivo.",
                "commands": update_commands
            })

        # Verificar missing indexes com alto impacto
        high_impact_indexes = [idx for idx in missing_indexes if idx.get("improvement_measure", 0) > 10000]
        if high_impact_indexes:
            diagnosis.append({
                "priority": 2,
                "action": "CREATE_INDEX",
                "reason": f"{len(high_impact_indexes)} índice(s) sugeridos com alto impacto de melhoria",
                "explanation": "SQL Server identificou que estes índices podem melhorar significativamente a performance. Avalie criar após atualizar estatísticas.",
                "commands": [idx.get("create_index_script") for idx in high_impact_indexes]
            })

        # Verificar HEAPs
        if heap_tables:
            large_heaps = [h for h in heap_tables if (h.get("row_count") or 0) > 10000]
            if large_heaps:
                diagnosis.append({
                    "priority": 3,
                    "action": "CONSIDER_CLUSTERED_INDEX",
                    "reason": f"{len(large_heaps)} tabela(s) HEAP com mais de 10.000 linhas",
                    "explanation": "Tabelas HEAP grandes podem ter performance ruim em buscas. Considere criar um clustered index na chave primária ou coluna mais buscada.",
                    "tables": [f"[{h['schema_name']}].[{h['table_name']}] ({h['row_count']} rows)" for h in large_heaps]
                })

        # Se não há issues
        if not diagnosis:
            diagnosis.append({
                "priority": 0,
                "action": "OK",
                "reason": "Nenhum problema de estatísticas ou índices identificado",
                "explanation": "As estatísticas estão atualizadas e não há sugestões de índices faltantes do SQL Server. O problema de performance pode estar em outro lugar (recursos, locks, network, etc)."
            })

        # Resumo
        total_objects = len(objects)
        objects_with_issues = len(stats_issues)
        views_found = len([r for r in results if r.get("object_type") == "VIEW" and not r.get("is_base_of_view")])
        nested_views_found = len([r for r in results if r.get("object_type") == "VIEW" and r.get("is_base_of_view")])
        base_tables_from_views = len([r for r in results if r.get("is_base_of_view") and r.get("object_type") != "VIEW"])
        not_found = len([r for r in results if r.get("status") == "NOT_FOUND"])

        # Contagem de issues nas tabelas base de VIEWs
        base_tables_with_issues = len([r for r in results
            if r.get("is_base_of_view")
            and ("CRÍTICO" in r.get("recommendation", "") or "DESATUALIZADO" in r.get("recommendation", "") or "MODIFICADO" in r.get("recommendation", ""))
        ])

        # Adicionar alertas de redundância/merge ao diagnóstico
        if index_analysis["redundant_suggestions"]:
            diagnosis.append({
                "priority": 2,
                "action": "REVIEW_REDUNDANT_INDEXES",
                "reason": f"{len(index_analysis['redundant_suggestions'])} sugestão(ões) de índice potencialmente redundante(s)",
                "explanation": "Alguns índices sugeridos têm colunas idênticas. Criar índices redundantes aumenta custo de escrita sem benefício.",
                "details": index_analysis["redundant_suggestions"]
            })

        if index_analysis["merge_candidates"]:
            diagnosis.append({
                "priority": 2,
                "action": "CONSIDER_INDEX_MERGE",
                "reason": f"{len(index_analysis['merge_candidates'])} oportunidade(s) de consolidar índices",
                "explanation": "Alguns índices sugeridos podem ser combinados em um único índice mais eficiente, reduzindo overhead de escrita.",
                "details": index_analysis["merge_candidates"]
            })

        if index_analysis["consolidation_tips"]:
            diagnosis.append({
                "priority": 3,
                "action": "INDEX_CONSOLIDATION_ALERT",
                "reason": "Alerta de overhead de escrita",
                "explanation": "Tabelas com muitos índices sugeridos. Cada índice adicional aumenta tempo de INSERT/UPDATE/DELETE.",
                "details": index_analysis["consolidation_tips"]
            })

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "threshold_days": threshold_days,
            "summary": {
                "objects_analyzed": total_objects,
                "stats_issues": objects_with_issues,
                "missing_indexes_found": len(missing_indexes),
                "redundant_index_suggestions": len(index_analysis["redundant_suggestions"]),
                "merge_candidates": len(index_analysis["merge_candidates"]),
                "heap_tables_found": len(heap_tables),
                "views_found": views_found,
                "nested_views_found": nested_views_found,
                "base_tables_from_views": base_tables_from_views,
                "base_tables_with_issues": base_tables_with_issues,
                "not_found": not_found
            },
            "diagnosis": diagnosis,
            "statistics_analysis": results,
            "missing_indexes": missing_indexes,
            "index_analysis": index_analysis,
            "heap_tables": heap_tables,
            "commands": {
                "update_statistics": update_commands,
                "create_index": create_index_commands
            },
            "query_analyzed": query_text[:500] + "..." if len(query_text) > 500 else query_text
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao diagnosticar query em {server_id}: {e}", exc_info=True)
        raise safe_http_error(500, e, "diagnostics query")


# =====================================================
# MODELO PARA EXPANDIR TABELAS BASE DE VIEW
# =====================================================
class ExpandViewRequest(BaseModel):
    """Request para expandir tabelas base de uma VIEW"""
    schema_name: str = "dbo"
    view_name: str
    database_name: str
    stats_age_threshold_days: int = 30
    max_depth: int = 5  # Profundidade máxima de recursão (VIEW -> VIEW -> Tabela)



class ExpandViewRequest(BaseModel):
    """Request para expandir tabelas base de uma VIEW"""
    schema_name: str = "dbo"
    view_name: str
    database_name: str
    stats_age_threshold_days: int = 30
    max_depth: int = 5  # Profundidade máxima de recursão (VIEW -> VIEW -> Tabela)


@diagnostics_router.post("/expand-view/{server_id}", response_model=GenericResponse)
async def expand_view_base_tables(
    server_id: str,
    request: ExpandViewRequest
):
    """
    Expande uma VIEW para descobrir todas as tabelas base (recursivamente).

    Funcionalidade:
    1. Identifica as dependências da VIEW (tabelas e outras VIEWs)
    2. Se encontrar outra VIEW, repete o processo recursivamente
    3. Para cada tabela base encontrada:
       - Analisa estatísticas (desatualizadas/OK)
       - Identifica missing indexes
       - Verifica se é HEAP
    4. Retorna estrutura hierárquica com recomendações priorizadas

    Prioridade de ações:
    1. UPDATE STATISTICS (rápido, pode resolver o problema)
    2. Verificar performance após estatísticas
    3. CREATE INDEX (se necessário após avaliar estatísticas)

    Args:
        server_id: ID do servidor SQL
        request: Nome da VIEW, database e configurações

    Returns:
        Estrutura hierárquica VIEW -> dependências -> estatísticas/índices
    """
    try:
        schema_name = request.schema_name
        view_name = request.view_name
        database_name = request.database_name
        threshold_days = request.stats_age_threshold_days

        # Sanitize all user-supplied SQL identifiers to prevent injection
        database_name = _sanitize_sql_identifier(database_name, "database_name")
        schema_name = _sanitize_sql_identifier(schema_name, "schema_name")
        view_name = _sanitize_sql_identifier(view_name, "view_name")
        max_depth = request.max_depth

        logger.info(f"[Expand VIEW] Iniciando expansão de [{database_name}].[{schema_name}].[{view_name}]")

        # Estrutura para armazenar resultados
        expansion_result = {
            "view_name": f"[{schema_name}].[{view_name}]",
            "database_name": database_name,
            "type": "VIEW",
            "dependencies": [],
            "base_tables_count": 0,
            "views_count": 0,
            "total_stats_issues": 0,
            "total_missing_indexes": 0,
            "total_heaps": 0
        }

        # Conjunto para evitar loops infinitos (VIEWs que referenciam umas às outras)
        visited_objects = set()

        # Fila de objetos para processar
        all_base_tables = []
        all_stats_results = []
        all_missing_indexes = []
        all_heap_tables = []
        update_commands = []
        create_index_commands = []

        async def get_view_dependencies(db_name: str, schema: str, obj_name: str, depth: int = 0):
            """
            Função recursiva para descobrir dependências de uma VIEW.
            Retorna lista de objetos (tabelas e VIEWs) que a VIEW referencia.
            """
            if depth > max_depth:
                logger.warning(f"[Expand VIEW] Profundidade máxima ({max_depth}) atingida para {schema}.{obj_name}")
                return []

            obj_key = f"{db_name}.{schema}.{obj_name}".upper()
            if obj_key in visited_objects:
                logger.debug(f"[Expand VIEW] Objeto já visitado: {obj_key}")
                return []

            visited_objects.add(obj_key)

            # Query para descobrir dependências usando sys.dm_sql_referenced_entities
            deps_query = f"""
            USE [{db_name}];
            SET NOCOUNT ON;

            SELECT DISTINCT
                COALESCE(ref.referenced_schema_name, 'dbo') AS referenced_schema,
                ref.referenced_entity_name AS referenced_name,
                CASE
                    WHEN o.type = 'U' THEN 'TABLE'
                    WHEN o.type = 'V' THEN 'VIEW'
                    ELSE 'OTHER'
                END AS referenced_type,
                CASE WHEN o.type = 'U' THEN
                    (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = o.object_id AND p.index_id IN (0,1))
                ELSE NULL END AS row_count
            FROM sys.dm_sql_referenced_entities('[{schema}].[{obj_name}]', 'OBJECT') ref
            LEFT JOIN sys.objects o ON o.object_id = OBJECT_ID(
                COALESCE(ref.referenced_schema_name, 'dbo') + '.' + ref.referenced_entity_name
            )
            WHERE ref.referenced_entity_name IS NOT NULL
              AND ref.referenced_minor_name IS NULL  -- Excluir colunas
              AND o.type IN ('U', 'V')  -- Apenas tabelas e views
            ORDER BY referenced_type, referenced_name;
            """

            dependencies = []

            try:
                deps_results = await execute_query_on_server(server_id, deps_query)

                for dep in deps_results:
                    ref_schema = dep.get('referenced_schema', 'dbo')
                    ref_name = dep.get('referenced_name')
                    ref_type = dep.get('referenced_type', 'OTHER')
                    row_count = dep.get('row_count')

                    if not ref_name:
                        continue

                    dep_info = {
                        "schema_name": ref_schema,
                        "object_name": ref_name,
                        "type": ref_type,
                        "row_count": row_count,
                        "depth": depth + 1,
                        "children": []
                    }

                    if ref_type == 'VIEW':
                        # Recursão: expandir a VIEW filha
                        logger.info(f"[Expand VIEW] Encontrada VIEW aninhada: [{ref_schema}].[{ref_name}] (profundidade {depth + 1})")
                        child_deps = await get_view_dependencies(db_name, ref_schema, ref_name, depth + 1)
                        dep_info["children"] = child_deps
                        expansion_result["views_count"] += 1
                    else:
                        # É uma tabela base - adicionar à lista para análise
                        all_base_tables.append({
                            "database": db_name,
                            "schema": ref_schema,
                            "table": ref_name,
                            "row_count": row_count,
                            "source_view": f"[{schema}].[{obj_name}]"
                        })
                        expansion_result["base_tables_count"] += 1

                    dependencies.append(dep_info)

            except Exception as e:
                logger.warning(f"[Expand VIEW] Erro ao obter dependências de {schema}.{obj_name}: {e}")
                # Tentar método alternativo com sys.sql_expression_dependencies
                alt_query = f"""
                USE [{db_name}];
                SELECT DISTINCT
                    OBJECT_SCHEMA_NAME(d.referenced_id) AS referenced_schema,
                    OBJECT_NAME(d.referenced_id) AS referenced_name,
                    CASE o.type
                        WHEN 'U' THEN 'TABLE'
                        WHEN 'V' THEN 'VIEW'
                        ELSE 'OTHER'
                    END AS referenced_type
                FROM sys.sql_expression_dependencies d
                JOIN sys.objects o ON d.referenced_id = o.object_id
                WHERE d.referencing_id = OBJECT_ID('[{schema}].[{obj_name}]')
                  AND o.type IN ('U', 'V');
                """
                try:
                    alt_results = await execute_query_on_server(server_id, alt_query)
                    for dep in alt_results:
                        ref_schema = dep.get('referenced_schema', 'dbo')
                        ref_name = dep.get('referenced_name')
                        ref_type = dep.get('referenced_type', 'OTHER')

                        if not ref_name:
                            continue

                        dep_info = {
                            "schema_name": ref_schema,
                            "object_name": ref_name,
                            "type": ref_type,
                            "row_count": None,
                            "depth": depth + 1,
                            "children": []
                        }

                        if ref_type == 'VIEW':
                            child_deps = await get_view_dependencies(db_name, ref_schema, ref_name, depth + 1)
                            dep_info["children"] = child_deps
                            expansion_result["views_count"] += 1
                        else:
                            all_base_tables.append({
                                "database": db_name,
                                "schema": ref_schema,
                                "table": ref_name,
                                "row_count": None,
                                "source_view": f"[{schema}].[{obj_name}]"
                            })
                            expansion_result["base_tables_count"] += 1

                        dependencies.append(dep_info)
                except Exception as e2:
                    logger.error(f"[Expand VIEW] Métodos alternativos também falharam: {e2}")

            return dependencies

        # Iniciar expansão recursiva
        expansion_result["dependencies"] = await get_view_dependencies(database_name, schema_name, view_name, 0)

        # Agora analisar estatísticas e índices de cada tabela base encontrada
        logger.info(f"[Expand VIEW] Analisando {len(all_base_tables)} tabelas base encontradas")

        for table_info in all_base_tables:
            db = table_info["database"]
            schema = table_info["schema"]
            table = table_info["table"]

            # Query para estatísticas
            stats_query = f"""
            USE [{db}];
            SET NOCOUNT ON;

            SELECT
                s.name AS schema_name,
                o.name AS object_name,
                'USER_TABLE' AS object_type,
                'FOUND' AS status,
                ISNULL(i.name, 'HEAP') AS index_name,
                st.name AS stats_name,
                STATS_DATE(o.object_id, st.stats_id) AS last_updated,
                DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS days_old,
                sp.rows AS rows_sampled,
                sp.modification_counter,
                CASE
                    WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 'CRÍTICO - Nunca teve estatísticas'
                    WHEN DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) > {threshold_days} THEN
                        'DESATUALIZADO - ' + CAST(DATEDIFF(DAY, STATS_DATE(o.object_id, st.stats_id), GETDATE()) AS VARCHAR) + ' dias'
                    WHEN sp.modification_counter > sp.rows * 0.2 AND sp.rows > 0 THEN
                        'MODIFICADO - ' + CAST(ISNULL(sp.modification_counter, 0) AS VARCHAR) + ' alterações'
                    ELSE 'OK - Estatísticas atualizadas'
                END AS recommendation
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            JOIN sys.stats st ON o.object_id = st.object_id
            LEFT JOIN sys.indexes i ON o.object_id = i.object_id AND st.stats_id = i.index_id
            OUTER APPLY sys.dm_db_stats_properties(o.object_id, st.stats_id) sp
            WHERE s.name = '{schema}' AND o.name = '{table}'
            ORDER BY CASE WHEN STATS_DATE(o.object_id, st.stats_id) IS NULL THEN 0 ELSE 1 END, days_old DESC;
            """

            try:
                stats_results = await execute_query_on_server(server_id, stats_query)
                for row in stats_results:
                    row["source_view"] = table_info["source_view"]
                    row["database_name"] = db
                    all_stats_results.append(row)

                    rec = row.get("recommendation", "")
                    if "CRÍTICO" in rec or "DESATUALIZADO" in rec or "MODIFICADO" in rec:
                        expansion_result["total_stats_issues"] += 1
                        cmd = f"USE [{db}]; UPDATE STATISTICS [{schema}].[{table}] WITH FULLSCAN;"
                        if cmd not in update_commands:
                            update_commands.append(cmd)

            except Exception as e:
                logger.warning(f"[Expand VIEW] Erro ao analisar estatísticas de {schema}.{table}: {e}")

            # Query para missing indexes
            missing_idx_query = f"""
            USE [{db}];
            SELECT TOP 5
                '{schema}' AS schema_name,
                '{table}' AS table_name,
                migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans) AS improvement_measure,
                migs.avg_user_impact,
                migs.user_seeks,
                migs.user_scans,
                mid.equality_columns,
                mid.inequality_columns,
                mid.included_columns,
                'USE [{db}]; CREATE NONCLUSTERED INDEX [IX_{table}_' +
                    REPLACE(REPLACE(REPLACE(ISNULL(mid.equality_columns, '') + ISNULL('_' + mid.inequality_columns, ''), '[', ''), ']', ''), ', ', '_') +
                    '] ON [{schema}].[{table}] (' +
                    ISNULL(mid.equality_columns, '') +
                    CASE WHEN mid.equality_columns IS NOT NULL AND mid.inequality_columns IS NOT NULL THEN ', ' ELSE '' END +
                    ISNULL(mid.inequality_columns, '') +
                    ')' +
                    CASE WHEN mid.included_columns IS NOT NULL THEN ' INCLUDE (' + mid.included_columns + ')' ELSE '' END +
                    ';' AS create_index_script
            FROM sys.dm_db_missing_index_details mid
            JOIN sys.dm_db_missing_index_groups mig ON mid.index_handle = mig.index_handle
            JOIN sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
            JOIN sys.objects o ON mid.object_id = o.object_id
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE s.name = '{schema}' AND o.name = '{table}'
            ORDER BY improvement_measure DESC;
            """

            try:
                idx_results = await execute_query_on_server(server_id, missing_idx_query)
                for row in idx_results:
                    improvement = row.get("improvement_measure", 0) or 0
                    if improvement > 1000:
                        row["source_view"] = table_info["source_view"]
                        row["database_name"] = db
                        all_missing_indexes.append(row)
                        expansion_result["total_missing_indexes"] += 1

                        cmd = row.get("create_index_script")
                        if cmd and cmd not in create_index_commands:
                            create_index_commands.append(cmd)
            except Exception as e:
                logger.debug(f"[Expand VIEW] Erro ao buscar missing indexes de {schema}.{table}: {e}")

            # Query para verificar HEAP
            heap_query = f"""
            USE [{db}];
            SELECT
                s.name AS schema_name,
                o.name AS table_name,
                CASE WHEN NOT EXISTS (
                    SELECT 1 FROM sys.indexes i WHERE i.object_id = o.object_id AND i.type = 1
                ) THEN 1 ELSE 0 END AS is_heap,
                (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = o.object_id AND p.index_id IN (0,1)) AS row_count
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE s.name = '{schema}' AND o.name = '{table}' AND o.type = 'U';
            """

            try:
                heap_results = await execute_query_on_server(server_id, heap_query)
                for row in heap_results:
                    if row.get("is_heap") == 1 and (row.get("row_count") or 0) > 1000:
                        row["source_view"] = table_info["source_view"]
                        row["database_name"] = db
                        all_heap_tables.append(row)
                        expansion_result["total_heaps"] += 1
            except Exception as e:
                logger.debug(f"[Expand VIEW] Erro ao verificar HEAP de {schema}.{table}: {e}")

        # Construir diagnóstico priorizado
        diagnosis = []

        # Prioridade 1: UPDATE STATISTICS
        if expansion_result["total_stats_issues"] > 0:
            diagnosis.append({
                "priority": 1,
                "action": "UPDATE_STATISTICS",
                "reason": f"{expansion_result['total_stats_issues']} estatística(s) desatualizada(s) nas tabelas base da VIEW",
                "explanation": "PASSO 1: Atualize as estatísticas primeiro. Isso é rápido e pode resolver o problema de performance sem necessidade de criar índices.",
                "next_step": "Após atualizar, execute novamente a query e verifique se a performance melhorou.",
                "commands_count": len(update_commands)
            })

        # Prioridade 2: Reavaliar após estatísticas
        if expansion_result["total_missing_indexes"] > 0 and expansion_result["total_stats_issues"] > 0:
            diagnosis.append({
                "priority": 2,
                "action": "REEVALUATE",
                "reason": "Reavaliar necessidade de índices após atualizar estatísticas",
                "explanation": "PASSO 2: Após atualizar estatísticas, execute a query novamente. Os missing indexes podem mudar ou até desaparecer com estatísticas corretas.",
                "next_step": "Se a query ainda estiver lenta, avalie os índices sugeridos."
            })

        # Prioridade 3: CREATE INDEX (se ainda necessário)
        if expansion_result["total_missing_indexes"] > 0:
            diagnosis.append({
                "priority": 3,
                "action": "CREATE_INDEX",
                "reason": f"{expansion_result['total_missing_indexes']} índice(s) sugeridos nas tabelas base",
                "explanation": "PASSO 3: Se após atualizar estatísticas a query ainda estiver lenta, considere criar os índices sugeridos.",
                "impact_note": "O SQL Server estima melhoria significativa com estes índices. Avalie o impacto no storage e operações de escrita.",
                "commands_count": len(create_index_commands)
            })

        # Prioridade 4: HEAPs
        if expansion_result["total_heaps"] > 0:
            diagnosis.append({
                "priority": 4,
                "action": "CONSIDER_CLUSTERED_INDEX",
                "reason": f"{expansion_result['total_heaps']} tabela(s) HEAP nas tabelas base",
                "explanation": "Tabelas sem índice clustered (HEAP) podem ter performance inferior em buscas. Considere criar um clustered index.",
                "tables_count": expansion_result["total_heaps"]
            })

        # Se não houver problemas
        if not diagnosis:
            diagnosis.append({
                "priority": 0,
                "action": "OK",
                "reason": "Nenhum problema identificado nas tabelas base da VIEW",
                "explanation": "As estatísticas estão atualizadas e não há sugestões de índices faltantes. O problema de performance pode estar em outro lugar."
            })

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "view_expanded": f"[{database_name}].[{schema_name}].[{view_name}]",
            "expansion_summary": expansion_result,
            "diagnosis": diagnosis,
            "base_tables": all_base_tables,
            "statistics_analysis": all_stats_results,
            "missing_indexes": all_missing_indexes,
            "heap_tables": all_heap_tables,
            "commands": {
                "update_statistics": update_commands,
                "create_index": create_index_commands
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Expand VIEW] Erro ao expandir VIEW: {e}", exc_info=True)
        raise safe_http_error(500, e, "diagnostics query")

