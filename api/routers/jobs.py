"""
Jobs Analysis Router
Handles SQL Server Agent jobs monitoring endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Set
import logging
import pyodbc
import re
from collections import defaultdict

from api.connection_pool import get_sql_server_pool, SQLServerConnectionPool
from api.dependencies import get_pool
from api.error_helpers import safe_http_error
from api.pagination import paginate, PaginationParams
from api.models import JobsAnalysisResponse, JobTrendsResponse, JobConflictsResponse

# 2026-08-17: classificador UNICO de tipo de backup (FULL/DIFF/LOG/OTHER) —
# o mesmo que o KPI global usa (Wave O). Fallback local identico se o import
# falhar (helpers puxa connection pools; nunca deixar a aba Jobs cair por isso).
try:
    from api.routers.intelligence.helpers import classify_backup_type as _classify_backup_type
except Exception:  # pragma: no cover
    def _classify_backup_type(job_name: str) -> str:
        if not job_name:
            return 'OTHER'
        n = job_name.upper()
        if 'LOG' in n or 'TRANSACTION' in n:
            return 'LOG'
        if 'DIFF' in n or 'INCREMENTAL' in n:
            return 'DIFF'
        if 'FULL' in n or 'COMPLETE' in n:
            return 'FULL'
        return 'OTHER'

logger = logging.getLogger(__name__)

# ========================================
# CONFIGURAÇÕES E CONSTANTES
# ========================================

# Limites de databases do sistema
SYSTEM_DATABASE_ID_MAX = 4  # master, tempdb, model, msdb
SYSTEM_DATABASES = ('master', 'tempdb', 'model', 'msdb')

# Thresholds de cobertura de manutenção (%)
COVERAGE_CRITICAL_THRESHOLD = 50
COVERAGE_WARNING_THRESHOLD = 80
COVERAGE_EXCELLENT_THRESHOLD = 95

# Limites de histórico e queries
FAILED_JOBS_HOURS_WINDOW = 24  # horas
HISTORY_LIMIT = 100  # execuções
FAILED_JOBS_LIMIT = 50  # jobs

# Timeouts
CONNECTION_TIMEOUT = 30  # segundos


def _agent_dt(date_col: str, time_col: str) -> str:
    """Expressao T-SQL inline equivalente a msdb.dbo.agent_datetime(date, time).

    2026-08-17: agent_datetime e' UDF escalar em msdb que (a) exige EXECUTE —
    o LEAST_PRIVILEGE_SETUP so' concede SELECT em sysjobs* (regra do projecto:
    sql_monitoring SELECT-only, nada de GRANT EXECUTE) e (b) em WHERE/ORDER BY
    forca avaliacao linha-a-linha sobre toda a sysjobhistory (nao-sargavel,
    principal risco de timeout 30s da aba). Reescrita inline, SQL 2014-safe:
    CONVERT(...,112) e' imune a DATEFORMAT/language; guarda > 0 evita Msg 241
    (run_date=0 em linhas sem execucao / next_run_date=0 em schedule parado).
    """
    return (
        f"CASE WHEN {date_col} > 0 THEN DATEADD(SECOND, "
        f"({time_col} / 10000) * 3600 + (({time_col} % 10000) / 100) * 60 + ({time_col} % 100), "
        f"CONVERT(DATETIME, CAST({date_col} AS CHAR(8)), 112)) END"
    )


def _run_date_floor(sql_dateadd_expr: str) -> str:
    """Pre-filtro SARGAVEL por run_date (INT yyyymmdd) para cortar sysjobhistory
    ANTES da comparacao de datetime. Ex.: _run_date_floor("DATEADD(HOUR,-25,GETDATE())")."""
    return f"CONVERT(INT, CONVERT(CHAR(8), {sql_dateadd_expr}, 112))"

# Análise de Tendências
TRENDS_SHORT_PERIOD_DAYS = 7   # período curto (última semana)
TRENDS_LONG_PERIOD_DAYS = 30   # período longo (último mês)
TRENDS_DURATION_INCREASE_THRESHOLD = 1.5  # 150% = alerta se duração aumentou 50%
TRENDS_FAILURE_RATE_THRESHOLD = 0.2  # 20% = alerta se taxa de falha > 20%

# Schedule Conflicts Analysis
CONFLICTS_HISTORY_DAYS = 30  # days to check real collisions
OVERLAP_MIN_MINUTES = 1  # minimum overlap to be considered a collision

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs-analysis"],
    responses={404: {"description": "Not found"}},
)


def get_server_connection_string(server_id: str) -> str:
    """
    Generate connection string for SQL Server with validation
    DEPRECATED: Use get_pooled_connection() instead for better performance.

    Args:
        server_id: Server identifier (HOST_INSTANCE or HOST\\INSTANCE)

    Returns:
        ODBC connection string

    Raises:
        ValueError: If server_id is invalid
    """
    if not server_id or not server_id.strip():
        raise ValueError("server_id não pode ser vazio")

    server_id = server_id.strip()

    # Converter formato HOST_INSTANCE para HOST\\INSTANCE
    if '_' in server_id and '\\' not in server_id:
        parts = server_id.split('_', 1)
        server_name = f"{parts[0]}\\{parts[1]}"
    else:
        server_name = server_id

    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server_name};"
        f"DATABASE=msdb;"
        f"Trusted_Connection=yes;"
        f"Connection Timeout={CONNECTION_TIMEOUT};"
    )


def get_pooled_connection(server_id: str, database: str = "msdb", pool: SQLServerConnectionPool = None):
    """
    Obtém conexão do pool global (mais eficiente que criar nova a cada requisição).

    Args:
        server_id: Server identifier (HOST_INSTANCE or HOST\\INSTANCE)
        database: Database to connect (default: msdb for jobs)
        pool: Injected connection pool (from Depends). Falls back to singleton if None.

    Returns:
        Tuple of (connection, pool) - caller must return connection to pool when done
    """
    if pool is None:
        pool = get_sql_server_pool()
    conn = pool.get_connection(server_id, database)
    if conn is None:
        raise HTTPException(status_code=500, detail=f"Não foi possível conectar ao servidor {server_id}")
    return conn, pool


def track_database_maintenance(
    db_name: str,
    maintenance_type: str,
    tracking_sets: Dict[str, Set[str]]
) -> None:
    """
    Adiciona database ao conjunto de tracking apropriado baseado no tipo de manutenção

    Args:
        db_name: Nome do database
        maintenance_type: Tipo de manutenção (Index Maintenance, Statistics Update, etc.)
        tracking_sets: Dicionário com conjuntos de tracking por tipo
    """
    type_map = {
        'Index Maintenance': 'index',
        'Statistics Update': 'stats',
        'Integrity Check': 'integrity',
        'Backup': 'backup'
    }

    if maintenance_type in type_map:
        tracking_key = type_map[maintenance_type]
        if tracking_key in tracking_sets:
            tracking_sets[tracking_key].add(db_name)


@router.get("/server/{server_id}", response_model=JobsAnalysisResponse)
async def get_jobs_analysis(server_id: str, pagination: PaginationParams = Depends(), pool: SQLServerConnectionPool = Depends(get_pool)):
    """
    Get complete jobs analysis for a server

    Returns:
    - failed_jobs: Jobs que falharam recentemente (últimas 24h)
    - all_jobs: Todos os jobs com último status
    - job_history: Histórico recente de execuções
    - running_jobs: Jobs em execução no momento
    - disabled_jobs: Jobs desabilitados
    - total_jobs: Total de jobs no servidor
    """
    conn = None
    try:
        logger.info(f"Jobs analysis requested for server: {server_id}")

        # Usar pool de conexões global para melhor performance
        conn, pool = get_pooled_connection(server_id, "msdb", pool=pool)
        cursor = conn.cursor()
        # Set query timeout to prevent hanging
        cursor.execute("SET LOCK_TIMEOUT 15000")  # 15s max wait for locks
        conn.timeout = 30  # 30s max per query

        # 1. JOBS QUE FALHARAM (últimas 24h)
        failed_query = f"""
        SELECT TOP {FAILED_JOBS_LIMIT}
            j.name AS job_name,
            j.description AS job_description,
            CASE j.enabled WHEN 1 THEN 'Habilitado' ELSE 'Desabilitado' END AS job_status,
            h.step_id,
            h.step_name,
            h.run_status,
            CASE h.run_status
                WHEN 0 THEN 'Falhou'
                WHEN 1 THEN 'Sucesso'
                WHEN 2 THEN 'Retry'
                WHEN 3 THEN 'Cancelado'
                WHEN 4 THEN 'Em Progresso'
                ELSE 'Desconhecido'
            END AS status_desc,
            {_agent_dt('h.run_date', 'h.run_time')} AS run_datetime,
            h.run_duration,
            (h.run_duration / 10000 * 3600) + ((h.run_duration % 10000) / 100 * 60) + (h.run_duration % 100) AS duration_seconds,
            h.message AS error_message,
            c.name AS category_name
        FROM msdb.dbo.sysjobs j WITH (NOLOCK)
        INNER JOIN msdb.dbo.sysjobhistory h WITH (NOLOCK) ON j.job_id = h.job_id
        LEFT JOIN msdb.dbo.syscategories c WITH (NOLOCK) ON j.category_id = c.category_id
        WHERE h.run_status = 0  -- Failed
            AND h.step_id > 0  -- Exclude job outcome row
            -- pre-filtro sargavel (INT yyyymmdd, 1h de folga) ANTES da comparacao datetime
            AND h.run_date >= {_run_date_floor(f'DATEADD(HOUR, -{FAILED_JOBS_HOURS_WINDOW + 1}, GETDATE())')}
            AND {_agent_dt('h.run_date', 'h.run_time')} >= DATEADD(HOUR, -{FAILED_JOBS_HOURS_WINDOW}, GETDATE())
        ORDER BY h.run_date DESC, h.run_time DESC
        """

        cursor.execute(failed_query)
        failed_jobs = []
        for row in cursor.fetchall():
            failed_jobs.append({
                'job_name': row.job_name,
                'job_description': row.job_description,
                'job_status': row.job_status,
                'step_id': row.step_id,
                'step_name': row.step_name,
                'run_status': row.run_status,
                'status_desc': row.status_desc,
                'run_datetime': row.run_datetime.isoformat() if row.run_datetime else None,
                'duration_seconds': row.duration_seconds,
                'error_message': row.error_message,
                'category_name': row.category_name
            })

        # 2. TODOS OS JOBS COM ÚLTIMO STATUS (Otimizado com OUTER APPLY)
        all_jobs_query = f"""
        SELECT
            j.job_id,
            j.name AS job_name,
            j.description AS job_description,
            j.enabled,
            CASE j.enabled WHEN 1 THEN 'Habilitado' ELSE 'Desabilitado' END AS enabled_desc,
            c.name AS category_name,
            SUSER_SNAME(j.owner_sid) AS owner_name,
            j.date_created,
            j.date_modified,
            -- Último resultado (via OUTER APPLY - performance otimizada)
            CASE last_run.run_status
                WHEN 0 THEN 'Falhou'
                WHEN 1 THEN 'Sucesso'
                WHEN 2 THEN 'Retry'
                WHEN 3 THEN 'Cancelado'
                WHEN 4 THEN 'Em Progresso'
                ELSE 'Nunca Executou'
            END AS last_run_status,
            last_run.run_datetime AS last_run_datetime,
            last_run.run_duration AS last_run_duration,
            -- Próxima execução
            next_run.next_run_datetime
        FROM msdb.dbo.sysjobs j WITH (NOLOCK)
        LEFT JOIN msdb.dbo.syscategories c WITH (NOLOCK) ON j.category_id = c.category_id
        OUTER APPLY (
            SELECT TOP 1
                run_status,
                {_agent_dt('h.run_date', 'h.run_time')} AS run_datetime,
                run_duration
            FROM msdb.dbo.sysjobhistory h WITH (NOLOCK)
            WHERE h.job_id = j.job_id AND h.step_id = 0
            ORDER BY h.instance_id DESC
        ) last_run
        OUTER APPLY (
            SELECT TOP 1
                {_agent_dt('js.next_run_date', 'js.next_run_time')} AS next_run_datetime
            FROM msdb.dbo.sysjobschedules js WITH (NOLOCK)
            WHERE js.job_id = j.job_id AND js.next_run_date > 0
            ORDER BY js.next_run_date, js.next_run_time
        ) next_run
        ORDER BY
            CASE
                WHEN last_run.run_status = 0 THEN 0  -- Falhas primeiro
                ELSE 1
            END,
            j.name
        """

        cursor.execute(all_jobs_query)
        all_jobs = []
        for row in cursor.fetchall():
            duration_sec = 0
            if row.last_run_duration:
                d = row.last_run_duration
                duration_sec = (d // 10000 * 3600) + ((d % 10000) // 100 * 60) + (d % 100)

            all_jobs.append({
                'job_id': str(row.job_id),
                'job_name': row.job_name,
                'job_description': row.job_description,
                'enabled': row.enabled,
                'enabled_desc': row.enabled_desc,
                'category_name': row.category_name,
                'owner_name': row.owner_name,
                'date_created': row.date_created.isoformat() if row.date_created else None,
                'date_modified': row.date_modified.isoformat() if row.date_modified else None,
                'last_run_status': row.last_run_status or 'Nunca Executou',
                'last_run_datetime': row.last_run_datetime.isoformat() if row.last_run_datetime else None,
                'last_run_duration_sec': duration_sec,
                'next_run_datetime': row.next_run_datetime.isoformat() if row.next_run_datetime else None
            })

        # 3. JOBS EM EXECUÇÃO AGORA
        running_query = """
        SELECT
            j.name AS job_name,
            ja.start_execution_date,
            DATEDIFF(SECOND, ja.start_execution_date, GETDATE()) AS running_seconds,
            ja.last_executed_step_id,
            (SELECT step_name FROM msdb.dbo.sysjobsteps WHERE job_id = j.job_id AND step_id = ja.last_executed_step_id) AS current_step_name
        FROM msdb.dbo.sysjobactivity ja
        INNER JOIN msdb.dbo.sysjobs j ON ja.job_id = j.job_id
        WHERE ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.syssessions)
            AND ja.start_execution_date IS NOT NULL
            AND ja.stop_execution_date IS NULL
        ORDER BY ja.start_execution_date
        """

        cursor.execute(running_query)
        running_jobs = []
        for row in cursor.fetchall():
            running_jobs.append({
                'job_name': row.job_name,
                'start_execution_date': row.start_execution_date.isoformat() if row.start_execution_date else None,
                'running_seconds': row.running_seconds,
                'current_step_name': row.current_step_name
            })

        # 4. HISTÓRICO RECENTE
        history_query = f"""
        SELECT TOP {HISTORY_LIMIT}
            j.name AS job_name,
            h.step_id,
            h.step_name,
            CASE h.run_status
                WHEN 0 THEN 'Falhou'
                WHEN 1 THEN 'Sucesso'
                WHEN 2 THEN 'Retry'
                WHEN 3 THEN 'Cancelado'
                WHEN 4 THEN 'Em Progresso'
                ELSE 'Desconhecido'
            END AS status_desc,
            h.run_status,
            {_agent_dt('h.run_date', 'h.run_time')} AS run_datetime,
            (h.run_duration / 10000 * 3600) + ((h.run_duration % 10000) / 100 * 60) + (h.run_duration % 100) AS duration_seconds,
            h.message
        FROM msdb.dbo.sysjobhistory h WITH (NOLOCK)
        INNER JOIN msdb.dbo.sysjobs j WITH (NOLOCK) ON h.job_id = j.job_id
        WHERE h.step_id = 0  -- Job outcome only
        ORDER BY h.run_date DESC, h.run_time DESC
        """

        cursor.execute(history_query)
        job_history = []
        for row in cursor.fetchall():
            job_history.append({
                'job_name': row.job_name,
                'step_id': row.step_id,
                'step_name': row.step_name,
                'status_desc': row.status_desc,
                'run_status': row.run_status,
                'run_datetime': row.run_datetime.isoformat() if row.run_datetime else None,
                'duration_seconds': row.duration_seconds,
                'message': row.message
            })

        # 5. JOBS DESABILITADOS
        disabled_jobs = [j for j in all_jobs if not j['enabled']]

        # 5b. AGENDAMENTOS POR JOB (2026-08-17, revisao owner: "quando um backup falha
        # nao sabemos a janela do proximo"). 1 linha por (job x schedule); so' toca
        # sysjobs/sysjobschedules/sysschedules (tabelas pequenas, sem sysjobhistory,
        # sem UDF). Devolve os CODIGOS CRUS de sysschedules — a descricao legivel
        # (Diario 22:00 / Semanal Dom,Qua / a cada 15 min) e' formatada no portal
        # com i18n (PT/EN/ES), nunca texto fixo aqui. SQL 2014-safe.
        # Um job sem schedule nao aparece (all_jobs ja o cobre); N schedules = N linhas.
        schedules_query = f"""
        SELECT
            j.job_id,
            j.name              AS job_name,
            j.enabled           AS job_enabled,
            s.schedule_id,
            s.name              AS schedule_name,
            s.enabled           AS schedule_enabled,
            s.freq_type, s.freq_interval, s.freq_subday_type, s.freq_subday_interval,
            s.freq_relative_interval, s.freq_recurrence_factor,
            s.active_start_time, s.active_end_time,
            CASE WHEN s.active_start_date > 0 THEN CONVERT(DATE, CAST(s.active_start_date AS CHAR(8)), 112) END AS active_start_date,
            CASE WHEN s.active_end_date   > 0 THEN CONVERT(DATE, CAST(s.active_end_date   AS CHAR(8)), 112) END AS active_end_date,
            {_agent_dt('js.next_run_date', 'js.next_run_time')} AS next_run_datetime
        FROM msdb.dbo.sysjobs          j  WITH (NOLOCK)
        JOIN msdb.dbo.sysjobschedules  js WITH (NOLOCK) ON js.job_id = j.job_id
        JOIN msdb.dbo.sysschedules     s  WITH (NOLOCK) ON s.schedule_id = js.schedule_id
        ORDER BY j.name,
                 CASE WHEN js.next_run_date > 0 THEN 0 ELSE 1 END,
                 js.next_run_date, js.next_run_time
        """
        job_schedules = []
        try:
            cursor.execute(schedules_query)
            for row in cursor.fetchall():
                job_schedules.append({
                    'job_id': str(row.job_id),
                    'job_name': row.job_name,
                    'job_enabled': bool(row.job_enabled),
                    'schedule_id': row.schedule_id,
                    'schedule_name': row.schedule_name,
                    'schedule_enabled': bool(row.schedule_enabled),
                    'freq_type': row.freq_type,
                    'freq_interval': row.freq_interval,
                    'freq_subday_type': row.freq_subday_type,
                    'freq_subday_interval': row.freq_subday_interval,
                    'freq_relative_interval': row.freq_relative_interval,
                    'freq_recurrence_factor': row.freq_recurrence_factor,
                    'active_start_time': row.active_start_time,
                    'active_end_time': row.active_end_time,
                    'active_start_date': row.active_start_date.isoformat() if row.active_start_date else None,
                    'active_end_date': row.active_end_date.isoformat() if row.active_end_date else None,
                    'next_run_datetime': row.next_run_datetime.isoformat() if row.next_run_datetime else None,
                })
        except pyodbc.Error as sched_err:
            # Graceful degradation: a aba continua a funcionar sem a seccao de
            # agendamentos (ex.: sem SELECT em sysschedules numa instancia).
            logger.warning(f"Schedules query failed for {server_id} (seccao de agendamentos vazia): {sched_err}")

        # Enriquecer all_jobs com a semantica dos agendamentos (fonte unica p/ portal):
        #   has_active_schedule = existe schedule com schedule_enabled=1
        #   schedule_count      = numero de schedules ligados
        _sched_by_job = {}
        for s in job_schedules:
            _sched_by_job.setdefault(s['job_id'], []).append(s)
        for j in all_jobs:
            _ss = _sched_by_job.get(j['job_id'], [])
            j['schedule_count'] = len(_ss)
            j['has_active_schedule'] = any(s['schedule_enabled'] for s in _ss)
            # Classificacao FULL/DIFF/LOG/OTHER — UM classificador (o mesmo do KPI
            # global, helpers.classify_backup_type) em vez de listas de keywords no
            # portal. So' para jobs cujo nome sugere backup; os outros ficam None.
            _nm = (j.get('job_name') or '').lower()
            j['backup_type_classified'] = (
                _classify_backup_type(j['job_name'])
                if any(kw in _nm for kw in ('backup', 'bkp'))
                else None
            )

        # 6. JOBS DE MANUTENÇÃO (Rebuild/Reindex, Update Statistics, Integrity Check e BACKUP)
        # Identificar por nome ou categoria
        index_keywords = ['index', 'reindex', 'rebuild', 'defrag', 'reorganize', 'optimize']
        statistics_keywords = ['statistic', 'stats', 'update stat']
        integrity_keywords = ['checkdb', 'integrity', 'dbcc']
        backup_keywords = ['backup', 'bkp', 'log backup', 'full backup', 'differential']

        # Keywords de exclusão (jobs que NÃO são manutenção)
        exclude_keywords = ['restore', 'log ship', 'replication', 'monitor', 'sync', 'mirror']

        maintenance_jobs = []
        for job in all_jobs:
            job_name_lower = job['job_name'].lower()
            job_desc_lower = (job['job_description'] or '').lower()
            category_lower = (job['category_name'] or '').lower()

            job_text = f"{job_name_lower} {job_desc_lower} {category_lower}"

            # Excluir jobs de restore/replication/monitoring
            is_excluded = any(keyword in job_text for keyword in exclude_keywords)
            if is_excluded:
                continue

            # Verificar se é job de manutenção
            has_index = any(keyword in job_text for keyword in index_keywords)
            has_stats = any(keyword in job_text for keyword in statistics_keywords)
            has_integrity = any(keyword in job_text for keyword in integrity_keywords)
            has_backup = any(keyword in job_text for keyword in backup_keywords)

            if has_index or has_stats or has_integrity or has_backup:
                # Determinar tipo de manutenção (prioridade na ordem)
                if has_backup:
                    maintenance_type = 'Backup'
                elif has_index:
                    maintenance_type = 'Index Maintenance'
                elif has_stats:
                    maintenance_type = 'Statistics Update'
                elif has_integrity:
                    maintenance_type = 'Integrity Check'
                else:
                    maintenance_type = 'Other'

                maintenance_jobs.append({
                    **job,
                    'maintenance_type': maintenance_type
                })

        # Query para verificar databases sem manutenção configurada
        databases_query = f"""
        SELECT
            name AS database_name,
            database_id,
            create_date,
            state_desc,
            recovery_model_desc
        FROM sys.databases
        WHERE database_id > {SYSTEM_DATABASE_ID_MAX}  -- Excluir system databases
            AND state_desc = 'ONLINE'
            AND name NOT IN {SYSTEM_DATABASES}
        ORDER BY name
        """

        cursor.execute(databases_query)
        all_databases = []
        for row in cursor.fetchall():
            all_databases.append({
                'database_name': row.database_name,
                'database_id': row.database_id,
                'create_date': row.create_date.isoformat() if row.create_date else None,
                'state_desc': row.state_desc,
                'recovery_model_desc': row.recovery_model_desc
            })

        # Analisar cobertura de manutenção - VERSÃO OTIMIZADA (1 query em vez de N)
        # Buscar comandos dos jobs de manutenção para identificar databases reais
        total_databases = len(all_databases)
        databases_with_maintenance = set()
        maintenance_recommendations = []

        # Tracking por tipo de manutenção usando dicionário
        tracking_sets = {
            'index': set(),
            'stats': set(),
            'integrity': set(),
            'backup': set()
        }
        databases_with_index_maintenance = tracking_sets['index']
        databases_with_stats_maintenance = tracking_sets['stats']
        databases_with_integrity_check = tracking_sets['integrity']
        databases_with_backup = tracking_sets['backup']

        # OTIMIZAÇÃO CRÍTICA: Buscar TODOS os steps de UMA VEZ (elimina N+1 queries)
        if maintenance_jobs:
            # Preparar lista de job_ids
            maintenance_job_ids = [j['job_id'] for j in maintenance_jobs]

            # Criar mapa job_id -> job info para acesso rápido
            job_map = {j['job_id']: j for j in maintenance_jobs}

            # Query otimizada: busca steps de TODOS os jobs de manutenção em 1 query
            placeholders = ','.join(['?' for _ in maintenance_job_ids])
            all_steps_query = f"""
            SELECT
                job_id,
                step_id,
                step_name,
                database_name,
                command
            FROM msdb.dbo.sysjobsteps
            WHERE job_id IN ({placeholders})
            ORDER BY job_id, step_id
            """

            cursor.execute(all_steps_query, maintenance_job_ids)
            all_steps = cursor.fetchall()

            # Agrupar steps por job_id
            steps_by_job = defaultdict(list)
            for step in all_steps:
                steps_by_job[str(step.job_id)].append(step)

            logger.info(f"📊 Loaded {len(all_steps)} steps from {len(maintenance_jobs)} maintenance jobs in 1 query")

        # Processar steps agrupados por job
        for job in maintenance_jobs:
            job_id = job['job_id']
            job_name = job['job_name']
            maintenance_type = job['maintenance_type']

            # Obter steps do dicionário (já carregados em 1 query)
            steps = steps_by_job.get(job_id, [])

            for step in steps:
                step_db = step.database_name
                step_command = (step.command or '').lower()

                # Flag para verificar se encontrou databases
                found_databases = False

                # 1. DETECÇÃO DE PADRÕES OLA HALLENGREN
                # Procurar por @Databases='USER_DATABASES', 'ALL_DATABASES', 'SYSTEM_DATABASES'
                if "@databases=" in step_command or "@databases =" in step_command:
                    if "'user_databases'" in step_command or '"user_databases"' in step_command:
                        # Job executa em TODOS os databases user
                        for db in all_databases:
                            databases_with_maintenance.add(db['database_name'])
                            track_database_maintenance(db['database_name'], maintenance_type, tracking_sets)
                        found_databases = True
                        break

                    elif "'all_databases'" in step_command or '"all_databases"' in step_command:
                        # Job executa em TODOS os databases (incluindo system)
                        for db in all_databases:
                            databases_with_maintenance.add(db['database_name'])
                            track_database_maintenance(db['database_name'], maintenance_type, tracking_sets)
                        found_databases = True
                        break

                    # Detectar databases específicos listados
                    # Padrão: @Databases='DB1, DB2, DB3'
                    db_param_match = re.search(r"@databases\s*=\s*['\"]([^'\"]+)['\"]", step_command)
                    if db_param_match:
                        db_list = db_param_match.group(1).strip()
                        # Validar se não está vazio e não é padrão especial
                        if db_list and db_list.lower() not in ('user_databases', 'all_databases', 'system_databases'):
                            # Split por vírgula e filtrar vazios
                            db_names = [name.strip() for name in db_list.split(',') if name.strip()]
                            for db_name in db_names:
                                # Verificar se existe no servidor (case-insensitive)
                                matching_db = next(
                                    (db for db in all_databases if db['database_name'].lower() == db_name.lower()),
                                    None
                                )
                                if matching_db:
                                    databases_with_maintenance.add(matching_db['database_name'])
                                    track_database_maintenance(matching_db['database_name'], maintenance_type, tracking_sets)
                                    found_databases = True

                # 2. Se step especifica um database específico no campo "Run as"
                if step_db and step_db not in SYSTEM_DATABASES:
                    databases_with_maintenance.add(step_db)
                    track_database_maintenance(step_db, maintenance_type, tracking_sets)
                    found_databases = True

                # 3. Se comando usa sp_MSforeachdb
                if 'sp_msforeachdb' in step_command or 'sp_msforeachdatabase' in step_command:
                    for db in all_databases:
                        databases_with_maintenance.add(db['database_name'])
                        track_database_maintenance(db['database_name'], maintenance_type, tracking_sets)
                    found_databases = True
                    break

                # 4. Se comando menciona databases específicos explicitamente
                if not found_databases:
                    for db in all_databases:
                        db_name_lower = db['database_name'].lower()
                        if (f'use [{db_name_lower}]' in step_command or
                            f'use {db_name_lower}' in step_command or
                            f'[{db_name_lower}].' in step_command or
                            f'{db_name_lower}.' in step_command or
                            f"'{db_name_lower}'" in step_command):
                            databases_with_maintenance.add(db['database_name'])
                            track_database_maintenance(db['database_name'], maintenance_type, tracking_sets)
                            found_databases = True

        # GERAR RECOMENDAÇÕES INTELIGENTES
        databases_without_maintenance = [
            db for db in all_databases
            if db['database_name'] not in databases_with_maintenance
        ]

        # Recomendação 1: Databases sem NENHUMA manutenção
        if databases_without_maintenance:
            maintenance_recommendations.append({
                'level': 'critical',
                'title': f'{len(databases_without_maintenance)} database(s) sem NENHUMA manutenção configurada',
                'message': f'Os seguintes databases não possuem jobs de manutenção: {", ".join([db["database_name"] for db in databases_without_maintenance[:5]])}{"..." if len(databases_without_maintenance) > 5 else ""}',
                'action': 'Crie jobs de manutenção usando Ola Hallengren ou SQL Server Maintenance Solution para esses databases.',
                'databases': [db['database_name'] for db in databases_without_maintenance]
            })

        # Recomendação 2: Databases sem Index Maintenance
        databases_without_index = [
            db['database_name'] for db in all_databases
            if db['database_name'] not in databases_with_index_maintenance
        ]
        if databases_without_index:
            maintenance_recommendations.append({
                'level': 'warning',
                'title': f'{len(databases_without_index)} database(s) sem Index Rebuild/Reorganize',
                'message': f'Databases sem manutenção de índices: {", ".join(databases_without_index[:5])}{"..." if len(databases_without_index) > 5 else ""}',
                'action': 'Índices fragmentados afetam performance. Crie job usando: EXEC [dbo].[IndexOptimize] @Databases=\'USER_DATABASES\', @FragmentationLow=NULL, @FragmentationMedium=\'INDEX_REORGANIZE\', @FragmentationHigh=\'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE\'',
                'databases': databases_without_index
            })

        # Recomendação 3: Databases sem Backup
        databases_without_backup = [
            db['database_name'] for db in all_databases
            if db['database_name'] not in databases_with_backup
        ]
        if databases_without_backup:
            maintenance_recommendations.append({
                'level': 'critical',
                'title': f'{len(databases_without_backup)} database(s) sem BACKUP configurado',
                'message': f'CRÍTICO! Databases sem backup: {", ".join(databases_without_backup[:5])}{"..." if len(databases_without_backup) > 5 else ""}',
                'action': 'BACKUP é ESSENCIAL para recuperação de desastres! Crie jobs de backup FULL, DIFFERENTIAL e LOG usando: EXEC [dbo].[DatabaseBackup] @Databases=\'USER_DATABASES\', @BackupType=\'FULL\' (diário), @BackupType=\'LOG\' (a cada 15 min)',
                'databases': databases_without_backup
            })

        # Recomendação 4: Databases sem Update Statistics
        databases_without_stats = [
            db['database_name'] for db in all_databases
            if db['database_name'] not in databases_with_stats_maintenance
        ]
        if databases_without_stats:
            maintenance_recommendations.append({
                'level': 'warning',
                'title': f'{len(databases_without_stats)} database(s) sem Update Statistics',
                'message': f'Databases sem atualização de estatísticas: {", ".join(databases_without_stats[:5])}{"..." if len(databases_without_stats) > 5 else ""}',
                'action': 'Estatísticas desatualizadas causam planos de execução ruins. Crie job usando: EXEC [dbo].[IndexOptimize] @Databases=\'USER_DATABASES\', @UpdateStatistics=\'ALL\'',
                'databases': databases_without_stats
            })

        # Recomendação 5: Databases sem Integrity Check
        databases_without_integrity = [
            db['database_name'] for db in all_databases
            if db['database_name'] not in databases_with_integrity_check
        ]
        if databases_without_integrity:
            maintenance_recommendations.append({
                'level': 'info',
                'title': f'{len(databases_without_integrity)} database(s) sem DBCC CHECKDB',
                'message': f'Databases sem verificação de integridade: {", ".join(databases_without_integrity[:5])}{"..." if len(databases_without_integrity) > 5 else ""}',
                'action': 'DBCC CHECKDB detecta corrupção de dados. RECOMENDADO executar semanalmente: EXEC [dbo].[DatabaseIntegrityCheck] @Databases=\'USER_DATABASES\'',
                'databases': databases_without_integrity
            })

        # Recomendação 6: Verificar se jobs estão agendados corretamente
        disabled_maintenance = [j for j in maintenance_jobs if not j['enabled']]
        if disabled_maintenance:
            maintenance_recommendations.append({
                'level': 'critical',
                'title': f'{len(disabled_maintenance)} job(s) de manutenção DESABILITADOS',
                'message': f'Jobs desabilitados: {", ".join([j["job_name"] for j in disabled_maintenance[:3]])}{"..." if len(disabled_maintenance) > 3 else ""}',
                'action': 'Habilite esses jobs ou exclua-os se não forem mais necessários. Jobs desabilitados não executam manutenção!',
                'jobs': [j['job_name'] for j in disabled_maintenance]
            })

        # Recomendação 7: Verificar se jobs nunca foram executados
        never_run_maintenance = [
            j for j in maintenance_jobs
            if j.get('last_run_status') == 'Nunca Executou'
        ]
        if never_run_maintenance:
            maintenance_recommendations.append({
                'level': 'warning',
                'title': f'{len(never_run_maintenance)} job(s) de manutenção NUNCA EXECUTARAM',
                'message': f'Jobs que nunca rodaram: {", ".join([j["job_name"] for j in never_run_maintenance[:3]])}{"..." if len(never_run_maintenance) > 3 else ""}',
                'action': 'Verifique se os jobs têm schedule configurado. Execute manualmente para testar: EXEC msdb.dbo.sp_start_job @job_name=\'NOME_DO_JOB\'',
                'jobs': [j['job_name'] for j in never_run_maintenance]
            })

        # Recomendação 8: Cobertura geral baixa (usando constantes)
        coverage_pct = (len(databases_with_maintenance) / total_databases * 100) if total_databases > 0 else 0
        if coverage_pct < COVERAGE_CRITICAL_THRESHOLD:
            maintenance_recommendations.append({
                'level': 'critical',
                'title': f'Cobertura de manutenção CRÍTICA: {coverage_pct:.1f}%',
                'message': f'Apenas {len(databases_with_maintenance)} de {total_databases} databases têm manutenção. RISCO ALTO de performance degradada e corrupção de dados.',
                'action': 'URGENTE: Implemente Ola Hallengren SQL Server Maintenance Solution: https://ola.hallengren.com/',
                'docs_link': 'https://ola.hallengren.com/'
            })
        elif coverage_pct < COVERAGE_WARNING_THRESHOLD:
            maintenance_recommendations.append({
                'level': 'warning',
                'title': f'Cobertura de manutenção BAIXA: {coverage_pct:.1f}%',
                'message': f'{len(databases_with_maintenance)} de {total_databases} databases têm manutenção.',
                'action': 'Expanda a manutenção para cobrir todos os databases user usando @Databases=\'USER_DATABASES\'',
            })
        elif coverage_pct >= COVERAGE_EXCELLENT_THRESHOLD:
            maintenance_recommendations.append({
                'level': 'success',
                'title': f'✅ Cobertura de manutenção EXCELENTE: {coverage_pct:.1f}%',
                'message': f'{len(databases_with_maintenance)} de {total_databases} databases cobertos.',
                'action': 'Continue monitorando execuções para garantir que jobs estão rodando com sucesso.',
            })

        # 7. ESTATÍSTICAS
        total_jobs = len(all_jobs)
        total_failed_24h = len(failed_jobs)
        total_running = len(running_jobs)
        total_disabled = len(disabled_jobs)
        total_maintenance_jobs = len(maintenance_jobs)

        # Contar jobs que falharam na última execução
        jobs_last_failed = len([j for j in all_jobs if j['last_run_status'] == 'Falhou'])

        # Manutenção habilitada vs desabilitada
        maintenance_enabled = len([j for j in maintenance_jobs if j['enabled']])
        maintenance_disabled = total_maintenance_jobs - maintenance_enabled

        # Agendamentos (2026-08-17): contagens que os cards da aba Jobs consomem.
        # jobs_without_active_schedule = enabled SEM schedule activo. NAO e' alarme
        # por si (ferramenta externa TDP/Commvault pode disparar o job via
        # sp_start_job) — o portal mostra como warning com tooltip.
        total_scheduled_jobs = len({s['job_id'] for s in job_schedules})
        jobs_without_active_schedule = len([j for j in all_jobs if j['enabled'] and not j.get('has_active_schedule')])

        result = {
            # 2026-08-17: 'success' + 'server_id' sao exigidos pelo response_model;
            # sem eles a validacao falhava e o handler devolvia 200 SEM dados
            # (aba Jobs a zeros desde 16/04). Ver api/models.py JobsAnalysisResponse.
            'success': True,
            'server_id': server_id,
            'failed_jobs': failed_jobs,
            # all_jobs e' consumido como ARRAY pelo portal (allJobs.length/.map) e
            # alimenta a seccao de agendamentos; jobs por instancia sao dezenas,
            # logo lista completa. Metadados de paginacao ficam a parte, opcionais.
            'all_jobs': all_jobs,
            'all_jobs_pagination': {k: v for k, v in paginate(all_jobs, pagination).items() if k != 'data'},
            'job_history': job_history,
            'running_jobs': running_jobs,
            'disabled_jobs': disabled_jobs,
            'maintenance_jobs': maintenance_jobs,
            'job_schedules': job_schedules,
            'total_scheduled_jobs': total_scheduled_jobs,
            'jobs_without_active_schedule': jobs_without_active_schedule,
            'all_databases': all_databases,
            'databases_without_maintenance': databases_without_maintenance,
            'total_jobs': total_jobs,
            'total_failed_24h': total_failed_24h,
            'total_running': total_running,
            'total_disabled': total_disabled,
            'jobs_last_failed': jobs_last_failed,
            'total_maintenance_jobs': total_maintenance_jobs,
            'maintenance_enabled': maintenance_enabled,
            'maintenance_disabled': maintenance_disabled,
            'total_databases': total_databases,
            'databases_with_maintenance': len(databases_with_maintenance),
            'databases_without_maintenance_count': len(databases_without_maintenance),
            'maintenance_coverage_pct': round((len(databases_with_maintenance) / total_databases * 100) if total_databases > 0 else 0, 1),
            # Tracking detalhado por tipo de manutenção
            'databases_with_index_maintenance': list(databases_with_index_maintenance),
            'databases_with_stats_maintenance': list(databases_with_stats_maintenance),
            'databases_with_integrity_check': list(databases_with_integrity_check),
            'databases_with_backup': list(databases_with_backup),
            'databases_without_index_count': len([db for db in all_databases if db['database_name'] not in databases_with_index_maintenance]),
            'databases_without_stats_count': len([db for db in all_databases if db['database_name'] not in databases_with_stats_maintenance]),
            'databases_without_integrity_count': len([db for db in all_databases if db['database_name'] not in databases_with_integrity_check]),
            'databases_without_backup_count': len([db for db in all_databases if db['database_name'] not in databases_with_backup]),
            'index_coverage_pct': round((len(databases_with_index_maintenance) / total_databases * 100) if total_databases > 0 else 0, 1),
            'stats_coverage_pct': round((len(databases_with_stats_maintenance) / total_databases * 100) if total_databases > 0 else 0, 1),
            'integrity_coverage_pct': round((len(databases_with_integrity_check) / total_databases * 100) if total_databases > 0 else 0, 1),
            'backup_coverage_pct': round((len(databases_with_backup) / total_databases * 100) if total_databases > 0 else 0, 1),
            # Recomendações inteligentes
            'maintenance_recommendations': maintenance_recommendations
        }

        logger.info(f"Jobs analysis completed for {server_id}: {total_jobs} total, {total_failed_24h} failed (24h), {total_running} running")

        return result

    except pyodbc.Error as e:
        raise safe_http_error(500, e, f"database error fetching jobs analysis for {server_id}")

    except Exception as e:
        raise safe_http_error(500, e, f"fetching jobs analysis for {server_id}")

    finally:
        # Retornar conexão ao pool para reutilização
        if conn and pool:
            pool.return_connection(server_id, conn, "msdb")


@router.get("/server/{server_id}/trends", response_model=JobTrendsResponse)
async def get_job_trends(server_id: str, pool: SQLServerConnectionPool = Depends(get_pool)) -> Dict[str, Any]:
    """
    Analisa tendências de falhas e performance dos jobs ao longo do tempo

    Detecta:
    - Jobs com aumento de duração (degradação de performance)
    - Jobs com aumento de taxa de falha
    - Padrões de falhas recorrentes
    - Comparação período curto (7 dias) vs longo (30 dias)

    Args:
        server_id: ID do servidor SQL

    Returns:
        Dict com análise de tendências, jobs em degradação e alertas
    """
    conn = None
    try:
        logger.info(f"Analyzing job trends for {server_id}")

        # Usar pool de conexões global para melhor performance
        conn, pool = get_pooled_connection(server_id, "msdb", pool=pool)
        cursor = conn.cursor()

        # Query principal: histórico de execuções dos últimos 30 dias
        trends_query = f"""
        WITH JobHistory AS (
            SELECT
                j.job_id,
                j.name AS job_name,
                j.enabled,
                h.run_status,
                {_agent_dt('h.run_date', 'h.run_time')} AS run_datetime,
                h.run_duration,
                -- Converter run_duration (HHMMSS) para segundos
                (h.run_duration / 10000 * 3600) +
                ((h.run_duration / 100 % 100) * 60) +
                (h.run_duration % 100) AS duration_seconds,
                CASE
                    WHEN {_agent_dt('h.run_date', 'h.run_time')} >= DATEADD(day, -{TRENDS_SHORT_PERIOD_DAYS}, GETDATE()) THEN 'short'
                    ELSE 'long'
                END AS period,
                DATEDIFF(day, {_agent_dt('h.run_date', 'h.run_time')}, GETDATE()) AS days_ago
            FROM msdb.dbo.sysjobs j WITH (NOLOCK)
            INNER JOIN msdb.dbo.sysjobhistory h WITH (NOLOCK) ON j.job_id = h.job_id
            WHERE
                h.step_id = 0  -- apenas resultado final do job
                -- pre-filtro sargavel por run_date (INT) antes da comparacao datetime
                AND h.run_date >= {_run_date_floor(f'DATEADD(day, -{TRENDS_LONG_PERIOD_DAYS + 1}, GETDATE())')}
                AND {_agent_dt('h.run_date', 'h.run_time')} >= DATEADD(day, -{TRENDS_LONG_PERIOD_DAYS}, GETDATE())
        )
        SELECT
            job_id,
            job_name,
            enabled,
            period,
            COUNT(*) AS total_executions,
            SUM(CASE WHEN run_status = 0 THEN 1 ELSE 0 END) AS total_failures,
            SUM(CASE WHEN run_status = 1 THEN 1 ELSE 0 END) AS total_successes,
            AVG(CAST(duration_seconds AS FLOAT)) AS avg_duration_seconds,
            MAX(duration_seconds) AS max_duration_seconds,
            MIN(duration_seconds) AS min_duration_seconds,
            MIN(days_ago) AS most_recent_execution_days_ago,
            MAX(days_ago) AS oldest_execution_days_ago
        FROM JobHistory
        GROUP BY job_id, job_name, enabled, period
        ORDER BY job_name, period
        """

        cursor.execute(trends_query)
        rows = cursor.fetchall()

        # Organizar dados por job e período
        jobs_data = defaultdict(lambda: {'short': None, 'long': None})

        for row in rows:
            job_key = str(row.job_id)
            period = row.period

            jobs_data[job_key][period] = {
                'job_id': str(row.job_id),
                'job_name': row.job_name,
                'enabled': row.enabled,
                'total_executions': row.total_executions,
                'total_failures': row.total_failures,
                'total_successes': row.total_successes,
                'failure_rate': round((row.total_failures / row.total_executions * 100) if row.total_executions > 0 else 0, 2),
                'success_rate': round((row.total_successes / row.total_executions * 100) if row.total_executions > 0 else 0, 2),
                'avg_duration_seconds': round(row.avg_duration_seconds, 2) if row.avg_duration_seconds else 0,
                'max_duration_seconds': row.max_duration_seconds,
                'min_duration_seconds': row.min_duration_seconds,
                'most_recent_days_ago': row.most_recent_execution_days_ago,
                'oldest_days_ago': row.oldest_execution_days_ago
            }

        # Análise de tendências: comparar período curto vs longo
        degrading_jobs = []  # Jobs com piora de performance
        improving_jobs = []  # Jobs com melhora de performance
        increased_failures = []  # Jobs com aumento de falhas

        for job_id, periods in jobs_data.items():
            short = periods.get('short')
            long = periods.get('long')

            if not short or not long:
                continue  # Precisa ter dados nos 2 períodos

            job_analysis = {
                'job_id': job_id,
                'job_name': short['job_name'],
                'enabled': short['enabled'],
                'short_period': short,
                'long_period': long
            }

            # ANÁLISE 1: Aumento de duração (degradação de performance)
            if short['avg_duration_seconds'] > 0 and long['avg_duration_seconds'] > 0:
                duration_ratio = short['avg_duration_seconds'] / long['avg_duration_seconds']

                if duration_ratio >= TRENDS_DURATION_INCREASE_THRESHOLD:
                    # Duração aumentou 50%+ = DEGRADAÇÃO
                    increase_pct = round((duration_ratio - 1) * 100, 1)
                    job_analysis['duration_increase_pct'] = increase_pct
                    job_analysis['duration_ratio'] = round(duration_ratio, 2)
                    job_analysis['alert_level'] = 'critical' if duration_ratio >= 2.0 else 'warning'
                    job_analysis['alert_message'] = f"Duração média aumentou {increase_pct}% nos últimos {TRENDS_SHORT_PERIOD_DAYS} dias"
                    degrading_jobs.append(job_analysis.copy())

                elif duration_ratio <= 0.7:
                    # Duração diminuiu 30%+ = MELHORIA
                    decrease_pct = round((1 - duration_ratio) * 100, 1)
                    job_analysis['duration_decrease_pct'] = decrease_pct
                    job_analysis['duration_ratio'] = round(duration_ratio, 2)
                    improving_jobs.append(job_analysis.copy())

            # ANÁLISE 2: Aumento de taxa de falha
            short_failure_rate = short['failure_rate'] / 100
            long_failure_rate = long['failure_rate'] / 100

            if short_failure_rate > long_failure_rate:
                failure_increase = short_failure_rate - long_failure_rate

                if failure_increase >= 0.1:  # Aumento de 10%+ na taxa de falha
                    job_analysis['failure_rate_increase'] = round(failure_increase * 100, 1)
                    job_analysis['short_failure_rate'] = round(short_failure_rate * 100, 1)
                    job_analysis['long_failure_rate'] = round(long_failure_rate * 100, 1)
                    job_analysis['alert_level'] = 'critical' if short_failure_rate >= TRENDS_FAILURE_RATE_THRESHOLD else 'warning'
                    job_analysis['alert_message'] = f"Taxa de falha aumentou {round(failure_increase * 100, 1)}% pontos percentuais"
                    increased_failures.append(job_analysis.copy())

        # Ordenar por severidade
        degrading_jobs.sort(key=lambda x: x.get('duration_ratio', 0), reverse=True)
        increased_failures.sort(key=lambda x: x.get('failure_rate_increase', 0), reverse=True)
        improving_jobs.sort(key=lambda x: x.get('duration_ratio', 0))

        # Criar alertas consolidados
        alerts = []

        if degrading_jobs:
            alerts.append({
                'type': 'performance_degradation',
                'level': 'critical' if any(j.get('duration_ratio', 0) >= 2.0 for j in degrading_jobs) else 'warning',
                'title_key': 'jobs.alert_degradation_title',
                'message_key': 'jobs.alert_degradation_message',
                'action_key': 'jobs.alert_degradation_action',
                'jobs_count': len(degrading_jobs),
                'params': {'count': len(degrading_jobs), 'days': TRENDS_SHORT_PERIOD_DAYS}
            })

        if increased_failures:
            alerts.append({
                'type': 'increased_failures',
                'level': 'critical',
                'title_key': 'jobs.alert_failures_title',
                'message_key': 'jobs.alert_failures_message',
                'action_key': 'jobs.alert_failures_action',
                'jobs_count': len(increased_failures),
                'params': {'count': len(increased_failures), 'days': TRENDS_SHORT_PERIOD_DAYS}
            })

        if improving_jobs:
            alerts.append({
                'type': 'improvements',
                'level': 'success',
                'title_key': 'jobs.alert_improvements_title',
                'message_key': 'jobs.alert_improvements_message',
                'jobs_count': len(improving_jobs),
                'params': {'count': len(improving_jobs), 'days': TRENDS_SHORT_PERIOD_DAYS}
            })

        # Estatísticas gerais
        total_jobs_analyzed = len(jobs_data)
        jobs_with_data_both_periods = len([j for j in jobs_data.values() if j['short'] and j['long']])

        result = {
            'success': True,  # 2026-08-17: exigido pelo response_model (ver models.py)
            'server_id': server_id,
            'analysis_timestamp': conn.cursor().execute("SELECT GETDATE()").fetchval().isoformat(),
            'periods': {
                'short': {
                    'days': TRENDS_SHORT_PERIOD_DAYS
                },
                'long': {
                    'days': TRENDS_LONG_PERIOD_DAYS
                }
            },
            'summary': {
                'total_jobs_analyzed': total_jobs_analyzed,
                'jobs_with_complete_data': jobs_with_data_both_periods,
                'degrading_jobs_count': len(degrading_jobs),
                'increased_failures_count': len(increased_failures),
                'improving_jobs_count': len(improving_jobs),
                'alerts_count': len(alerts)
            },
            'alerts': alerts,
            'degrading_jobs': degrading_jobs[:10],  # Top 10 piores
            'increased_failures': increased_failures[:10],  # Top 10 com mais falhas
            'improving_jobs': improving_jobs[:5],  # Top 5 melhores
            'thresholds': {
                'duration_increase': f'{int((TRENDS_DURATION_INCREASE_THRESHOLD - 1) * 100)}%',
                'failure_rate': f'{int(TRENDS_FAILURE_RATE_THRESHOLD * 100)}%'
            }
        }

        logger.info(f"Trends analysis completed: {jobs_with_data_both_periods} jobs analyzed, {len(degrading_jobs)} degrading, {len(increased_failures)} with increased failures")

        return result

    except pyodbc.Error as e:
        raise safe_http_error(500, e, f"database error fetching job trends for {server_id}")

    except Exception as e:
        raise safe_http_error(500, e, f"fetching job trends for {server_id}")

    finally:
        # Retornar conexão ao pool para reutilização
        if conn and pool:
            pool.return_connection(server_id, conn, "msdb")


@router.get("/server/{server_id}/schedule-conflicts", response_model=JobConflictsResponse)
async def get_schedule_conflicts(server_id: str, pool: SQLServerConnectionPool = Depends(get_pool)) -> Dict[str, Any]:
    """
    Analyze job schedule conflicts and real execution overlaps.

    Returns:
    - schedule_conflicts: Jobs with overlapping schedules (potential conflicts)
    - real_collisions: Jobs that actually ran at the same time (last 30 days)
    - collision_pairs: Aggregated collision statistics per pair
    - recommendations: Actionable recommendations with SQL commands
    - summary: Overall conflict analysis summary
    """
    conn = None
    try:
        logger.info(f"Analyzing schedule conflicts for {server_id}")

        conn, pool = get_pooled_connection(server_id, "msdb", pool=pool)
        cursor = conn.cursor()

        # ── Query 1: Schedule Conflicts (potential) ──
        schedule_conflicts_query = """
        WITH JobSchedules AS (
            SELECT
                j.name AS job_name,
                j.enabled AS job_enabled,
                s.name AS schedule_name,
                s.freq_type,
                s.freq_interval,
                s.freq_subday_type,
                s.freq_subday_interval,
                s.active_start_time,
                s.active_end_time,
                CASE s.freq_type
                    WHEN 1 THEN 'Once'
                    WHEN 4 THEN 'Daily'
                    WHEN 8 THEN 'Weekly'
                    WHEN 16 THEN 'Monthly'
                    WHEN 64 THEN 'On SQL Agent Start'
                    ELSE 'Other'
                END AS frequency_desc,
                CASE s.freq_subday_type
                    WHEN 1 THEN 'At specific time'
                    WHEN 2 THEN 'Every ' + CAST(s.freq_subday_interval AS VARCHAR) + ' seconds'
                    WHEN 4 THEN 'Every ' + CAST(s.freq_subday_interval AS VARCHAR) + ' minutes'
                    WHEN 8 THEN 'Every ' + CAST(s.freq_subday_interval AS VARCHAR) + ' hours'
                    ELSE 'Unknown'
                END AS subday_desc,
                CASE s.freq_subday_type
                    WHEN 1 THEN 1440
                    WHEN 2 THEN s.freq_subday_interval / 60.0
                    WHEN 4 THEN CAST(s.freq_subday_interval AS FLOAT)
                    WHEN 8 THEN s.freq_subday_interval * 60.0
                    ELSE 1440
                END AS interval_minutes,
                CASE
                    WHEN j.name LIKE '%backup%' OR j.name LIKE '%Backup%' OR j.name LIKE '%BKP%' THEN 'BACKUP'
                    WHEN j.name LIKE '%log%' OR j.name LIKE '%Log%' THEN 'LOG'
                    WHEN j.name LIKE '%reindex%' OR j.name LIKE '%rebuild%' OR j.name LIKE '%index%' OR j.name LIKE '%Index%' OR j.name LIKE '%optimize%' THEN 'INDEX'
                    WHEN j.name LIKE '%check%' OR j.name LIKE '%DBCC%' OR j.name LIKE '%integrity%' THEN 'DBCC'
                    WHEN j.name LIKE '%statistic%' OR j.name LIKE '%stats%' OR j.name LIKE '%Statistic%' THEN 'STATISTICS'
                    WHEN j.name LIKE '%shrink%' THEN 'SHRINK'
                    ELSE 'OTHER'
                END AS job_category
            FROM msdb.dbo.sysjobs j WITH (NOLOCK)
            JOIN msdb.dbo.sysjobschedules js WITH (NOLOCK) ON j.job_id = js.job_id
            JOIN msdb.dbo.sysschedules s WITH (NOLOCK) ON js.schedule_id = s.schedule_id
            WHERE j.enabled = 1
        )
        SELECT
            A.job_name AS job_a,
            A.schedule_name AS schedule_a,
            A.frequency_desc + ' - ' + A.subday_desc AS frequency_a,
            A.job_category AS category_a,
            B.job_name AS job_b,
            B.schedule_name AS schedule_b,
            B.frequency_desc + ' - ' + B.subday_desc AS frequency_b,
            B.job_category AS category_b,
            CASE
                WHEN A.job_category = B.job_category
                THEN 'SAME_TYPE'
                WHEN A.job_category IN ('BACKUP','LOG') AND B.job_category IN ('BACKUP','LOG')
                THEN 'CONCURRENT_BACKUPS'
                WHEN A.job_category IN ('INDEX','DBCC','SHRINK','STATISTICS') AND B.job_category IN ('INDEX','DBCC','SHRINK','STATISTICS')
                THEN 'CONCURRENT_MAINTENANCE'
                ELSE 'DIFFERENT_TYPES'
            END AS risk_level,
            A.interval_minutes AS interval_a_min,
            B.interval_minutes AS interval_b_min
        FROM JobSchedules A
        JOIN JobSchedules B ON A.job_name < B.job_name
        WHERE
            (A.active_start_time = B.active_start_time
            OR (A.interval_minutes > 0 AND B.interval_minutes > 0
                AND (CAST(A.interval_minutes AS INT) % CAST(CASE WHEN B.interval_minutes = 0 THEN 1 ELSE B.interval_minutes END AS INT) = 0
                     OR CAST(B.interval_minutes AS INT) % CAST(CASE WHEN A.interval_minutes = 0 THEN 1 ELSE A.interval_minutes END AS INT) = 0)))
            AND (A.freq_type <> 8 OR B.freq_type <> 8
                 OR (A.freq_interval & B.freq_interval) > 0)
        ORDER BY
            CASE
                WHEN A.job_category = B.job_category THEN 0
                WHEN A.job_category IN ('BACKUP','LOG') AND B.job_category IN ('BACKUP','LOG') THEN 1
                WHEN A.job_category IN ('INDEX','DBCC','SHRINK','STATISTICS') AND B.job_category IN ('INDEX','DBCC','SHRINK','STATISTICS') THEN 2
                ELSE 3
            END,
            A.job_name
        """

        cursor.execute(schedule_conflicts_query)
        columns = [desc[0] for desc in cursor.description]
        schedule_conflicts = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Convert Decimal to float for JSON serialization
        for conflict in schedule_conflicts:
            for key in ('interval_a_min', 'interval_b_min'):
                if conflict.get(key) is not None:
                    conflict[key] = float(conflict[key])

        # ── Query 2: Real Collisions (last N days) ──
        real_collisions_query = f"""
        WITH JobRuns AS (
            SELECT
                j.name AS job_name,
                h.run_status,
                CONVERT(DATETIME,
                    STUFF(STUFF(CAST(h.run_date AS VARCHAR),5,0,'-'),8,0,'-') + ' ' +
                    STUFF(STUFF(RIGHT('000000' + CAST(h.run_time AS VARCHAR),6),3,0,':'),6,0,':')
                ) AS start_time,
                DATEADD(SECOND,
                    (h.run_duration / 10000) * 3600 +
                    ((h.run_duration % 10000) / 100) * 60 +
                    (h.run_duration % 100),
                    CONVERT(DATETIME,
                        STUFF(STUFF(CAST(h.run_date AS VARCHAR),5,0,'-'),8,0,'-') + ' ' +
                        STUFF(STUFF(RIGHT('000000' + CAST(h.run_time AS VARCHAR),6),3,0,':'),6,0,':')
                    )
                ) AS end_time,
                CASE h.run_status
                    WHEN 0 THEN 'Failed'
                    WHEN 1 THEN 'Succeeded'
                    WHEN 2 THEN 'Retry'
                    WHEN 3 THEN 'Canceled'
                    ELSE 'Unknown'
                END AS status_desc
            FROM msdb.dbo.sysjobhistory h WITH (NOLOCK)
            JOIN msdb.dbo.sysjobs j WITH (NOLOCK) ON h.job_id = j.job_id
            WHERE h.step_id = 1
            AND h.run_date >= CONVERT(INT, CONVERT(VARCHAR, DATEADD(DAY, -{CONFLICTS_HISTORY_DAYS}, GETDATE()), 112))
        )
        SELECT TOP 100
            A.job_name AS job_a,
            A.status_desc AS status_a,
            B.job_name AS job_b,
            B.status_desc AS status_b,
            A.start_time AS start_a,
            A.end_time AS end_a,
            B.start_time AS start_b,
            B.end_time AS end_b,
            DATEDIFF(MINUTE,
                CASE WHEN A.start_time > B.start_time THEN A.start_time ELSE B.start_time END,
                CASE WHEN A.end_time < B.end_time THEN A.end_time ELSE B.end_time END
            ) AS overlap_minutes
        FROM JobRuns A
        JOIN JobRuns B ON A.job_name < B.job_name
            AND A.start_time < B.end_time
            AND B.start_time < A.end_time
        WHERE DATEDIFF(MINUTE,
                CASE WHEN A.start_time > B.start_time THEN A.start_time ELSE B.start_time END,
                CASE WHEN A.end_time < B.end_time THEN A.end_time ELSE B.end_time END
            ) >= {OVERLAP_MIN_MINUTES}
        ORDER BY A.start_time DESC
        """

        cursor.execute(real_collisions_query)
        columns = [desc[0] for desc in cursor.description]
        real_collisions_raw = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Convert datetime to ISO strings for JSON
        real_collisions = []
        for col in real_collisions_raw:
            entry = {}
            for k, v in col.items():
                if hasattr(v, 'isoformat'):
                    entry[k] = v.isoformat()
                else:
                    entry[k] = v
            real_collisions.append(entry)

        # ── Aggregate collision pairs ──
        pair_stats = defaultdict(lambda: {'count': 0, 'total_overlap_min': 0, 'last_collision': None, 'failures_involved': 0})
        for col in real_collisions:
            pair_key = f"{col['job_a']}|{col['job_b']}"
            pair_stats[pair_key]['count'] += 1
            pair_stats[pair_key]['total_overlap_min'] += col.get('overlap_minutes', 0) or 0
            if col.get('status_a') == 'Failed' or col.get('status_b') == 'Failed':
                pair_stats[pair_key]['failures_involved'] += 1
            if pair_stats[pair_key]['last_collision'] is None:
                pair_stats[pair_key]['last_collision'] = col.get('start_a')

        collision_pairs = []
        for pair_key, stats in sorted(pair_stats.items(), key=lambda x: -x[1]['count']):
            job_a, job_b = pair_key.split('|', 1)
            collision_pairs.append({
                'job_a': job_a,
                'job_b': job_b,
                'collision_count': stats['count'],
                'total_overlap_minutes': stats['total_overlap_min'],
                'avg_overlap_minutes': round(stats['total_overlap_min'] / stats['count'], 1) if stats['count'] > 0 else 0,
                'failures_involved': stats['failures_involved'],
                'last_collision': stats['last_collision']
            })

        # ── Generate Recommendations ──
        recommendations = _generate_conflict_recommendations(schedule_conflicts, collision_pairs)

        # ── Summary ──
        critical_conflicts = [c for c in schedule_conflicts if c['risk_level'] in ('SAME_TYPE', 'CONCURRENT_BACKUPS')]
        warning_conflicts = [c for c in schedule_conflicts if c['risk_level'] == 'CONCURRENT_MAINTENANCE']

        summary = {
            'total_schedule_conflicts': len(schedule_conflicts),
            'critical_conflicts': len(critical_conflicts),
            'warning_conflicts': len(warning_conflicts),
            'info_conflicts': len(schedule_conflicts) - len(critical_conflicts) - len(warning_conflicts),
            'total_real_collisions': len(real_collisions),
            'unique_collision_pairs': len(collision_pairs),
            'collisions_with_failures': sum(1 for p in collision_pairs if p['failures_involved'] > 0),
            'analysis_period_days': CONFLICTS_HISTORY_DAYS
        }

        logger.info(f"Schedule conflicts analysis completed: {len(schedule_conflicts)} potential, {len(collision_pairs)} real collision pairs")

        return {
            'success': True,  # 2026-08-17: exigido pelo response_model (ver models.py)
            'server_id': server_id,
            'schedule_conflicts': schedule_conflicts,
            'real_collisions': real_collisions[:50],
            'collision_pairs': collision_pairs,
            'recommendations': recommendations,
            'summary': summary
        }

    except pyodbc.Error as e:
        raise safe_http_error(500, e, f"database error fetching schedule conflicts for {server_id}")

    except Exception as e:
        raise safe_http_error(500, e, f"fetching schedule conflicts for {server_id}")

    finally:
        if conn and pool:
            pool.return_connection(server_id, conn, "msdb")


def _generate_conflict_recommendations(
    schedule_conflicts: List[Dict],
    collision_pairs: List[Dict]
) -> List[Dict[str, Any]]:
    """
    Generate actionable recommendations with SQL commands based on conflicts.
    """
    recommendations = []
    seen_pairs = set()

    for conflict in schedule_conflicts:
        pair = (conflict['job_a'], conflict['job_b'])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        risk = conflict['risk_level']
        cat_a = conflict.get('category_a', 'OTHER')
        cat_b = conflict.get('category_b', 'OTHER')

        # Find real collision data for this pair
        real_data = None
        for cp in collision_pairs:
            if cp['job_a'] == conflict['job_a'] and cp['job_b'] == conflict['job_b']:
                real_data = cp
                break

        collision_text = ""
        if real_data:
            collision_text = (
                f" (confirmed: {real_data['collision_count']} real collisions in "
                f"{CONFLICTS_HISTORY_DAYS} days, {real_data['failures_involved']} with failures)"
            )

        if risk == 'SAME_TYPE':
            severity = 'critical'
            title = f"Same-type conflict: {conflict['job_a']} vs {conflict['job_b']}"
            description = f"Both jobs are type '{cat_a}' and share the same schedule window.{collision_text}"

            if cat_a in ('BACKUP', 'LOG'):
                action = "Concurrent backup jobs compete for transaction log access. Disable the redundant job or stagger schedules."
                commands = [
                    f"-- Option 1: Disable redundant job",
                    f"EXEC msdb.dbo.sp_update_job @job_name = N'{conflict['job_b']}', @enabled = 0;",
                    f"",
                    f"-- Option 2: Stagger schedule by 30 minutes",
                    f"SELECT s.name, s.active_start_time FROM msdb.dbo.sysschedules s",
                    f"JOIN msdb.dbo.sysjobschedules js ON s.schedule_id = js.schedule_id",
                    f"JOIN msdb.dbo.sysjobs j ON js.job_id = j.job_id",
                    f"WHERE j.name = N'{conflict['job_b']}';",
                ]
            elif cat_a in ('INDEX', 'STATISTICS'):
                action = "Index Rebuild invalidates statistics. Run Index first, then Statistics sequentially."
                commands = [
                    f"-- Chain: Run Statistics after Index completes",
                    f"-- Add step to Index job that triggers Statistics:",
                    f"EXEC msdb.dbo.sp_add_jobstep",
                    f"    @job_name = N'{conflict['job_a']}',",
                    f"    @step_name = N'Chain - Start Statistics Update',",
                    f"    @subsystem = N'TSQL',",
                    f"    @command = N'EXEC msdb.dbo.sp_start_job @job_name = N''{conflict['job_b']}'';',",
                    f"    @on_success_action = 1;",
                ]
            elif cat_a == 'DBCC':
                action = "Multiple DBCC jobs compete for I/O. Run them sequentially."
                commands = [
                    f"-- Stagger DBCC jobs - disable one and chain it:",
                    f"EXEC msdb.dbo.sp_update_job @job_name = N'{conflict['job_b']}', @enabled = 0;",
                    f"-- Add final step to {conflict['job_a']} to start {conflict['job_b']}",
                ]
            else:
                action = "Same-type jobs should not run concurrently. Stagger or chain them."
                commands = [
                    f"SELECT j.name, s.name AS schedule, s.active_start_time",
                    f"FROM msdb.dbo.sysjobs j",
                    f"JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id",
                    f"JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id",
                    f"WHERE j.name IN (N'{conflict['job_a']}', N'{conflict['job_b']}');",
                ]

        elif risk == 'CONCURRENT_BACKUPS':
            severity = 'critical'
            title = f"Concurrent backups: {conflict['job_a']} vs {conflict['job_b']}"
            description = f"Backup ({cat_a}) and Log ({cat_b}) jobs share schedule window. Compete for transaction log access.{collision_text}"
            action = "Stagger backup schedules or disable the redundant log backup job."
            commands = [
                f"-- Check if both jobs backup the same databases:",
                f"SELECT j.name, js.step_name, js.command",
                f"FROM msdb.dbo.sysjobs j",
                f"JOIN msdb.dbo.sysjobsteps js ON j.job_id = js.job_id",
                f"WHERE j.name IN (N'{conflict['job_a']}', N'{conflict['job_b']}');",
                f"",
                f"-- If redundant, disable the less frequent one:",
                f"-- EXEC msdb.dbo.sp_update_job @job_name = N'{conflict['job_b']}', @enabled = 0;",
            ]

        elif risk == 'CONCURRENT_MAINTENANCE':
            severity = 'warning'
            title = f"Concurrent maintenance: {conflict['job_a']} vs {conflict['job_b']}"
            description = f"Maintenance ({cat_a} + {cat_b}) share schedule window. Compete for CPU/IO.{collision_text}"

            if ('INDEX' in (cat_a, cat_b)) and ('STATISTICS' in (cat_a, cat_b)):
                action = "Index Rebuild updates statistics automatically. Run Index first, then Statistics."
                idx_job = conflict['job_a'] if cat_a == 'INDEX' else conflict['job_b']
                stats_job = conflict['job_b'] if cat_a == 'INDEX' else conflict['job_a']
                commands = [
                    f"-- 1. Disable Stats schedule (will be triggered by Index job):",
                    f"EXEC msdb.dbo.sp_update_job @job_name = N'{stats_job}', @enabled = 0;",
                    f"",
                    f"-- 2. Add final step to Index job to start Stats:",
                    f"EXEC msdb.dbo.sp_add_jobstep",
                    f"    @job_name = N'{idx_job}',",
                    f"    @step_name = N'Chain - Start Statistics Update',",
                    f"    @subsystem = N'TSQL',",
                    f"    @command = N'EXEC msdb.dbo.sp_start_job @job_name = N''{stats_job}'';',",
                    f"    @on_success_action = 1;",
                ]
            else:
                action = "Stagger maintenance jobs to avoid I/O contention."
                commands = [
                    f"SELECT j.name, s.name AS schedule, s.active_start_time",
                    f"FROM msdb.dbo.sysjobs j",
                    f"JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id",
                    f"JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id",
                    f"WHERE j.name IN (N'{conflict['job_a']}', N'{conflict['job_b']}');",
                ]
        else:
            severity = 'info'
            title = f"Schedule overlap: {conflict['job_a']} vs {conflict['job_b']}"
            description = f"Different-type jobs ({cat_a} + {cat_b}) share schedule window. Usually safe.{collision_text}"
            action = "Monitor resource usage. Only act if performance issues are observed."
            commands = [
                f"-- Monitor running jobs during overlap window:",
                f"SELECT j.name, ja.start_execution_date",
                f"FROM msdb.dbo.sysjobactivity ja",
                f"JOIN msdb.dbo.sysjobs j ON ja.job_id = j.job_id",
                f"WHERE ja.start_execution_date IS NOT NULL AND ja.stop_execution_date IS NULL;",
            ]

        recommendations.append({
            'severity': severity,
            'title': title,
            'description': description,
            'action': action,
            'commands': commands,
            'job_a': conflict['job_a'],
            'job_b': conflict['job_b'],
            'risk_level': risk,
            'has_real_collisions': real_data is not None,
            'collision_count': real_data['collision_count'] if real_data else 0
        })

    # Additional: Collision pairs without schedule conflicts (unexpected)
    for cp in collision_pairs:
        pair = (cp['job_a'], cp['job_b'])
        if pair not in seen_pairs and cp['collision_count'] >= 3:
            seen_pairs.add(pair)
            recommendations.append({
                'severity': 'warning',
                'title': f"Unexpected collisions: {cp['job_a']} vs {cp['job_b']}",
                'description': f"{cp['collision_count']} collisions in {CONFLICTS_HISTORY_DAYS} days ({cp['failures_involved']} with failures). No schedule conflict found - may have dynamic triggers.",
                'action': "Investigate job triggers and manual starts.",
                'commands': [
                    f"SELECT j.name, s.name AS schedule, s.freq_type, s.active_start_time",
                    f"FROM msdb.dbo.sysjobs j",
                    f"JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id",
                    f"JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id",
                    f"WHERE j.name IN (N'{cp['job_a']}', N'{cp['job_b']}');",
                ],
                'job_a': cp['job_a'],
                'job_b': cp['job_b'],
                'risk_level': 'UNEXPECTED',
                'has_real_collisions': True,
                'collision_count': cp['collision_count']
            })

    severity_order = {'critical': 0, 'warning': 1, 'info': 2}
    recommendations.sort(key=lambda r: (severity_order.get(r['severity'], 9), -r.get('collision_count', 0)))

    return recommendations
