"""
WatcherDB Memory Analysis Module
Análise de configuração e uso de memória SQL Server
"""

import pyodbc
import logging
from typing import Dict, List, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

def get_connection_string(server_name: str) -> str:
    """
    Gera string de conexão para o servidor SQL
    Usa o mesmo padrão do sistema WatcherDB existente
    """
    # Usar o padrão de conexão do WatcherDB (mesmo que o monitoring.py)
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server_name};Trusted_Connection=yes;Connection Timeout=10;"

def _server_id_from_name(server_name: str) -> str:
    """Converte nome exibido (HOST\\INSTANCIA) para server_id (HOST_INSTANCIA).
    Para instância DEFAULT, retorna apenas o host."""
    if "\\" in server_name:
        host, inst = server_name.split("\\", 1)
        if inst.upper() == "DEFAULT":
            return host
        return f"{host}_{inst}"
    return server_name


async def get_server_memory_analysis(server_name: str, sql_monitoring=None) -> Dict:
    """
    Analisa configuração e uso de memória de um servidor SQL
    
    Args:
        server_name: Nome do servidor (ex: SQLIDSPRD03\\I01)
    
    Returns:
        Dict com análise completa de memória
    """
    
    query = """
    SELECT
        -- RAM Física do Servidor
        physical_ram_gb = CAST(total_physical_memory_kb / 1024.0 / 1024.0 AS DECIMAL(18,2)),
        
        -- Configuração SQL Server
        max_server_memory_mb = (
            SELECT CAST(value_in_use AS BIGINT) 
            FROM sys.configurations 
            WHERE name = 'max server memory (MB)'
        ),
        min_server_memory_mb = (
            SELECT CAST(value_in_use AS BIGINT) 
            FROM sys.configurations 
            WHERE name = 'min server memory (MB)'
        ),
        
        -- Uso Atual de Memória (busca em Memory Manager ou Buffer Manager)
        target_server_memory_mb = COALESCE(
            (SELECT TOP 1 CAST(CAST(cntr_value AS BIGINT) / 1024.0 AS BIGINT)
             FROM sys.dm_os_performance_counters
             WHERE counter_name = 'Target Server Memory (KB)'
             AND (object_name LIKE '%Buffer Manager%' OR object_name LIKE '%Memory Manager%')),
            0
        ),
        total_server_memory_mb = COALESCE(
            (SELECT TOP 1 CAST(CAST(cntr_value AS BIGINT) / 1024.0 AS BIGINT)
             FROM sys.dm_os_performance_counters
             WHERE counter_name = 'Total Server Memory (KB)'
             AND (object_name LIKE '%Buffer Manager%' OR object_name LIKE '%Memory Manager%')),
            -- Fallback: usar physical_memory_in_use_kb se counter não disponível
            CAST(physical_memory_in_use_kb / 1024.0 AS BIGINT)
        ),
        
        -- Working Set do Processo
        process_working_set_mb = CAST(physical_memory_in_use_kb / 1024.0 AS DECIMAL(18,2)),

        -- Memória disponível do SO (fallback DMV - Plano D)
        os_available_mb_dmv = CAST(available_physical_memory_kb / 1024.0 AS DECIMAL(18,2)),
        system_memory_state = system_memory_state_desc,

        -- Always On Info
        is_hadr_enabled = CAST(SERVERPROPERTY('IsHadrEnabled') AS INT),
        ag_name = (
            SELECT TOP 1 ag.name 
            FROM sys.dm_hadr_availability_replica_states AS ars
            INNER JOIN sys.availability_groups AS ag ON ars.group_id = ag.group_id
            WHERE ars.is_local = 1
        ),
        replica_role = (
            SELECT TOP 1 
                CASE ars.role 
                    WHEN 1 THEN 'PRIMARY'
                    WHEN 2 THEN 'SECONDARY'
                    ELSE 'RESOLVING'
                END
            FROM sys.dm_hadr_availability_replica_states AS ars
            WHERE ars.is_local = 1
        )
        
    FROM sys.dm_os_sys_memory
    CROSS JOIN sys.dm_os_process_memory;
    """
    
    try:
        logger.info(f"🔍 Analisando memória do servidor: {server_name}")
        
        if sql_monitoring:
            # Usar o sistema de conexão do WatcherDB existente
            server_id = _server_id_from_name(server_name)
            logger.info(f"📊 Executando query de memória em: {server_id}")
            
            # Tentar primeiro com server_id original
            result = await sql_monitoring.execute_query(server_id, query)
            logger.info(f"📊 Resultado da query: {result}")
            
            # Se falhou e é DEFAULT, tentar fallback
            if (not result or not result.get('success')) and server_id.endswith('_DEFAULT'):
                alt_id = server_id.replace('_DEFAULT', '')
                logger.info(f"⚙️ Fallback DEFAULT -> HOST: {server_id} -> {alt_id}")
                result = await sql_monitoring.execute_query(alt_id, query)
                logger.info(f"📊 Resultado do fallback: {result}")
            
            if not result:
                raise Exception(f"Resultado da query é None para {server_name}")
            
            if not result.get('success'):
                raise Exception(f"Query falhou para {server_name}: {result.get('error', 'Erro desconhecido')}")
            
            rows = result.get('rows', [])
            if not rows:
                raise Exception(f"Nenhum dado retornado da query de memória para {server_name}")
            
            row = rows[0]  # Pegar primeira linha
        else:
            # Fallback para conexão direta
            conn_str = get_connection_string(server_name)
            conn = pyodbc.connect(conn_str, timeout=10, autocommit=True)
            cursor = conn.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            cursor.execute(query)
            row = cursor.fetchone()
            
            if not row:
                raise Exception("Nenhum dado retornado da query de memória")
        
        # Extrair dados com tratamento de None
        def safe_int(value, default=0):
            return int(value) if value is not None else default
        
        def safe_float(value, default=0.0):
            return float(value) if value is not None else default
        
        data = {
            'physical_ram_gb': safe_float(row.get('physical_ram_gb')),
            'max_server_memory_mb': safe_int(row.get('max_server_memory_mb')),
            'min_server_memory_mb': safe_int(row.get('min_server_memory_mb')),
            'target_server_memory_mb': safe_int(row.get('target_server_memory_mb')),
            'total_server_memory_mb': safe_int(row.get('total_server_memory_mb')),
            'process_working_set_mb': safe_float(row.get('process_working_set_mb')),
            'is_hadr_enabled': safe_int(row.get('is_hadr_enabled')),
            'ag_name': row.get('ag_name'),
            'replica_role': row.get('replica_role'),
            # Plano D: DMV fallback para memória disponível do SO
            'os_available_mb_dmv': safe_float(row.get('os_available_mb_dmv')),
            'system_memory_state': row.get('system_memory_state')
        }
        
        # Calcular recomendação Microsoft (75% da RAM)
        data['recommendation_max_memory_mb'] = int(data['physical_ram_gb'] * 1024 * 0.75)
        data['reserved_for_os_mb'] = int(data['physical_ram_gb'] * 1024 * 0.25)
        
        # Calcular memory pressure (quanto mais próximo de 100%, melhor!)
        # Memory pressure = (Total Server Memory / Target Server Memory) * 100
        # Se target = 0, significa que o SQL Server ainda não alocou memória ou não está configurado
        if data['target_server_memory_mb'] > 0:
            data['memory_pressure_pct'] = round(
                (data['total_server_memory_mb'] * 100.0) / data['target_server_memory_mb'], 
                2
            )
            # Status de memory pressure (quanto mais próximo de 100%, melhor!)
            if data['memory_pressure_pct'] >= 95:
                data['memory_pressure_status'] = 'HEALTHY'  # 🟢 Verde - SQL está usando quase toda memória alocada
            elif data['memory_pressure_pct'] >= 80:
                data['memory_pressure_status'] = 'WARNING'  # 🟡 Amarelo - SQL poderia usar mais memória
            else:
                data['memory_pressure_status'] = 'CRITICAL'  # 🔴 Vermelho - SQL não está conseguindo alocar memória suficiente
        else:
            # Se target = 0, não há como calcular pressure
            # Isso pode acontecer se o SQL Server ainda não alocou memória ou está em estado inicial
            data['memory_pressure_pct'] = None
            data['memory_pressure_status'] = 'NOT_CONFIGURED'  # ⚪ Não configurado / Inicializando
        
        # Gerar alertas
        data['alerts'] = generate_memory_alerts(data)

        # =========================================================================
        # QUERIES SECUNDÁRIAS - EXECUTADAS EM PARALELO para melhor performance
        # =========================================================================
        if sql_monitoring:
            import asyncio
            server_id = _server_id_from_name(server_name)

            # Definir queries secundárias
            buffer_pool_query = """
            SELECT
                DB_NAME(database_id) AS database_name,
                COUNT(*) * 8 / 1024.0 AS buffer_pool_mb,
                COUNT(*) * 8 / 1024.0 / 1024.0 AS buffer_pool_gb,
                100.0 * COUNT(*) * 8 / 1024.0 /
                    (SELECT SUM(CAST(cntr_value AS BIGINT)) / 1024.0
                     FROM sys.dm_os_performance_counters WITH(NOLOCK)
                     WHERE counter_name = 'Total Server Memory (KB)') AS percentage
            FROM sys.dm_os_buffer_descriptors WITH(NOLOCK)
            WHERE database_id > 4
            GROUP BY database_id
            HAVING COUNT(*) * 8 / 1024.0 > 10
            ORDER BY buffer_pool_mb DESC
            """

            ple_query = """
            SELECT
                cntr_value AS PageLifeExpectancy,
                CASE
                    WHEN cntr_value < 300 THEN 'CRITICAL'
                    WHEN cntr_value < 600 THEN 'WARNING'
                    ELSE 'HEALTHY'
                END AS Status
            FROM sys.dm_os_performance_counters WITH(NOLOCK)
            WHERE counter_name = 'Page life expectancy'
            AND instance_name = ''
            """

            grants_query = """
            SELECT
                COUNT(*) AS TotalGrants,
                SUM(CASE WHEN grant_time IS NULL THEN 1 ELSE 0 END) AS PendingGrants,
                SUM(CASE WHEN grant_time IS NOT NULL THEN 1 ELSE 0 END) AS GrantedGrants,
                SUM(requested_memory_kb) / 1024.0 AS TotalRequestedMB,
                SUM(granted_memory_kb) / 1024.0 AS TotalGrantedMB,
                MAX(requested_memory_kb) / 1024.0 AS MaxRequestedMB,
                MAX(granted_memory_kb) / 1024.0 AS MaxGrantedMB
            FROM sys.dm_exec_query_memory_grants WITH(NOLOCK)
            """

            plan_cache_query = """
            SELECT
                COUNT(*) AS PlanCount,
                SUM(size_in_bytes) / 1024.0 / 1024.0 AS PlanCacheSizeMB,
                SUM(CASE WHEN usecounts = 1 THEN size_in_bytes ELSE 0 END) / 1024.0 / 1024.0 AS SingleUsePlansMB,
                SUM(CASE WHEN usecounts > 1 THEN size_in_bytes ELSE 0 END) / 1024.0 / 1024.0 AS MultiUsePlansMB,
                100.0 * SUM(CASE WHEN usecounts = 1 THEN size_in_bytes ELSE 0 END) / NULLIF(SUM(size_in_bytes), 0) AS SingleUsePercentage
            FROM sys.dm_exec_cached_plans WITH(NOLOCK)
            """

            memory_clerks_query = """
            SELECT TOP 15
                mc.[type] AS ClerkType,
                CASE mc.[type]
                    WHEN 'MEMORYCLERK_SQLBUFFERPOOL' THEN 'Buffer Pool (Data Cache)'
                    WHEN 'MEMORYCLERK_SQLQUERYPLAN' THEN 'Query Plans Cache'
                    WHEN 'MEMORYCLERK_SQLOPTIMIZER' THEN 'Query Optimizer'
                    WHEN 'MEMORYCLERK_SQLSTORENG' THEN 'Storage Engine'
                    WHEN 'MEMORYCLERK_SQLGENERAL' THEN 'General SQL Memory'
                    WHEN 'MEMORYCLERK_SQLCLR' THEN 'CLR Runtime'
                    WHEN 'MEMORYCLERK_SOSNODE' THEN 'SOS Node Memory'
                    WHEN 'MEMORYCLERK_SQLCONNECTIONPOOL' THEN 'Connection Pool'
                    WHEN 'MEMORYCLERK_SQLLOGPOOL' THEN 'Log Pool'
                    WHEN 'MEMORYCLERK_SQLSERVICEBROKERDIALOG' THEN 'Service Broker Dialog'
                    WHEN 'MEMORYCLERK_SQLSERVICEBROKERACTIVATION' THEN 'Service Broker Activation'
                    WHEN 'MEMORYCLERK_SQLXP' THEN 'Extended Procedures'
                    WHEN 'MEMORYCLERK_XTP' THEN 'In-Memory OLTP'
                    WHEN 'CACHESTORE_OBJCP' THEN 'Object Plans'
                    WHEN 'CACHESTORE_SQLCP' THEN 'SQL Plans'
                    WHEN 'CACHESTORE_PHDR' THEN 'Bound Trees'
                    WHEN 'CACHESTORE_XPROC' THEN 'Extended Proc Cache'
                    WHEN 'USERSTORE_TOKENPERM' THEN 'Token Permissions'
                    WHEN 'OBJECTSTORE_LOCK_MANAGER' THEN 'Lock Manager'
                    ELSE mc.[type]
                END AS ClerkDescription,
                SUM(mc.pages_kb) / 1024.0 AS MemoryMB,
                SUM(mc.pages_kb) / 1024.0 / 1024.0 AS MemoryGB,
                100.0 * SUM(mc.pages_kb) /
                    (SELECT SUM(pages_kb) FROM sys.dm_os_memory_clerks) AS PercentageOfTotal,
                GETDATE() AS CollectedAt
            FROM sys.dm_os_memory_clerks mc WITH(NOLOCK)
            GROUP BY mc.[type]
            HAVING SUM(mc.pages_kb) > 1024
            ORDER BY SUM(mc.pages_kb) DESC
            """

            # Resource Governor - pools e workload groups
            resource_governor_query = """
            SELECT
                rp.pool_id,
                rp.name AS PoolName,
                rp.min_memory_percent AS MinMemoryPct,
                rp.max_memory_percent AS MaxMemoryPct,
                rp.used_memory_kb / 1024.0 AS UsedMemoryMB,
                rp.target_memory_kb / 1024.0 AS TargetMemoryMB,
                rp.max_memory_kb / 1024.0 AS MaxMemoryMB,
                rp.out_of_memory_count AS OOMCount,
                (SELECT COUNT(*) FROM sys.dm_resource_governor_workload_groups wg WHERE wg.pool_id = rp.pool_id) AS WorkloadGroupCount,
                STUFF((SELECT ', ' + wg.name FROM sys.dm_resource_governor_workload_groups wg WHERE wg.pool_id = rp.pool_id FOR XML PATH('')), 1, 2, '') AS WorkloadGroups,
                CASE
                    WHEN rp.out_of_memory_count > 0 THEN 'CRITICAL'
                    WHEN rp.max_memory_kb > 0 AND (rp.used_memory_kb * 100.0 / rp.max_memory_kb) > 90 THEN 'WARNING'
                    WHEN rp.max_memory_kb > 0 AND (rp.used_memory_kb * 100.0 / rp.max_memory_kb) > 75 THEN 'ATTENTION'
                    ELSE 'OK'
                END AS PoolStatus,
                CASE WHEN rp.max_memory_kb > 0 THEN CAST(rp.used_memory_kb * 100.0 / rp.max_memory_kb AS DECIMAL(5,1)) ELSE 0 END AS UsagePct,
                (SELECT sqlserver_start_time FROM sys.dm_os_sys_info) AS SqlServerStartTime,
                GETDATE() AS CollectedAt
            FROM sys.dm_resource_governor_resource_pools rp
            WHERE rp.used_memory_kb > 0 OR rp.out_of_memory_count > 0
            ORDER BY rp.used_memory_kb DESC
            """

            # OOM Events - buscar timestamps do Error Log
            oom_events_query = """
            DECLARE @OOMLog TABLE (LogDate DATETIME, ProcessInfo NVARCHAR(50), [Text] NVARCHAR(MAX));
            BEGIN TRY
                INSERT INTO @OOMLog EXEC xp_readerrorlog 0, 1, N'insufficient system memory in resource pool';
            END TRY
            BEGIN CATCH
            END CATCH
            SELECT TOP 10
                LogDate AS EventTime,
                [Text] AS EventMessage,
                CASE
                    WHEN [Text] LIKE '%pool ''default''%' THEN 'default'
                    WHEN [Text] LIKE '%pool ''internal''%' THEN 'internal'
                    ELSE 'unknown'
                END AS PoolName
            FROM @OOMLog
            ORDER BY LogDate DESC;
            """

            # NOTA: mg.database_id não existe em SQL Server < 2016 SP1
            # Usar s.database_id da sessão como fallback
            top_memory_queries_query = """
            SELECT TOP 10
                mg.session_id AS SessionID,
                COALESCE(s.login_name, 'N/A') AS LoginName,
                COALESCE(s.host_name, 'N/A') AS HostName,
                COALESCE(DB_NAME(s.database_id), 'N/A') AS DatabaseName,
                mg.requested_memory_kb / 1024.0 AS RequestedMemoryMB,
                mg.granted_memory_kb / 1024.0 AS GrantedMemoryMB,
                mg.used_memory_kb / 1024.0 AS UsedMemoryMB,
                mg.max_used_memory_kb / 1024.0 AS MaxUsedMemoryMB,
                CASE WHEN mg.grant_time IS NULL THEN 'Pending' ELSE 'Granted' END AS GrantStatus,
                mg.wait_time_ms AS WaitTimeMs,
                SUBSTRING(qt.text, 1, 200) AS QueryText
            FROM sys.dm_exec_query_memory_grants mg WITH(NOLOCK)
            LEFT JOIN sys.dm_exec_sessions s WITH(NOLOCK) ON mg.session_id = s.session_id
            OUTER APPLY sys.dm_exec_sql_text(mg.sql_handle) AS qt
            WHERE mg.requested_memory_kb > 0
            ORDER BY mg.requested_memory_kb DESC
            """

            # Funções auxiliares para execução paralela com tratamento de erro
            # CADA query secundaria tem o seu PROPRIO wait_for(8.0). Antes, se
            # uma delas hangava (tipico: OOM events via xp_readerrorlog em PRD
            # com errorlog grande), bloqueava o gather inteiro durante o
            # wait_for(15.0) do caller, e quando o caller cortava, TODAS as 8
            # eram canceladas mesmo que 7 ja' tivessem terminado em <1s.
            #
            # Agora cada uma falha individualmente em 8s e o gather continua
            # com as outras. A query principal e' rapida (~150ms) — e' so' nas
            # secundarias que precisamos de protecao por-query.
            PER_QUERY_TIMEOUT = 8.0

            async def _safe_query(query_text: str, label: str, default):
                """Wrapper que aplica timeout per-query e devolve default em erro."""
                try:
                    result = await asyncio.wait_for(
                        sql_monitoring.execute_query(server_id, query_text),
                        timeout=PER_QUERY_TIMEOUT
                    )
                    if result and result.get('success'):
                        rows = result.get('rows', [])
                        if isinstance(default, list):
                            return rows
                        if isinstance(default, dict):
                            return rows[0] if rows else {}
                    return default
                except asyncio.TimeoutError:
                    logger.debug(f"⚠️ [Memory/{label}] timeout {PER_QUERY_TIMEOUT}s para {server_id}")
                    return default
                except Exception as e:
                    logger.debug(f"Erro {label} para {server_id}: {e}")
                    return default

            async def fetch_buffer_pool():
                return await _safe_query(buffer_pool_query, 'buffer_pool', [])

            async def fetch_ple():
                return await _safe_query(ple_query, 'ple', {})

            async def fetch_grants():
                return await _safe_query(grants_query, 'grants', {})

            async def fetch_plan_cache():
                return await _safe_query(plan_cache_query, 'plan_cache', {})

            async def fetch_memory_clerks():
                return await _safe_query(memory_clerks_query, 'memory_clerks', [])

            async def fetch_top_queries():
                return await _safe_query(top_memory_queries_query, 'top_memory_queries', [])

            async def fetch_resource_governor():
                return await _safe_query(resource_governor_query, 'resource_governor', [])

            async def fetch_oom_events():
                # OOM via xp_readerrorlog pode demorar muito em servidores PRD
                # com errorlog gigante. Esta query e' a mais propensa a hang.
                return await _safe_query(oom_events_query, 'oom_events', [])

            # Executar todas as queries secundárias em PARALELO
            logger.debug(f"🚀 [Memory] Executando 8 queries secundárias em paralelo para {server_id}")
            buffer_pool, ple, grants, plan_cache, clerks, top_queries, resource_governor, oom_events = await asyncio.gather(
                fetch_buffer_pool(),
                fetch_ple(),
                fetch_grants(),
                fetch_plan_cache(),
                fetch_memory_clerks(),
                fetch_top_queries(),
                fetch_resource_governor(),
                fetch_oom_events(),
                return_exceptions=False  # cada fetch_ ja' apanha as suas excepcoes
            )

            # Atribuir resultados
            data["buffer_pool_by_db"] = buffer_pool
            data["page_life_expectancy"] = ple
            data["memory_grants"] = grants
            data["plan_cache"] = plan_cache
            data["memory_clerks"] = clerks
            data["top_memory_queries"] = top_queries
            data["resource_governor"] = resource_governor
            data["oom_events"] = oom_events

            # Calcular resumo do Resource Governor
            total_oom = sum(int(p.get('OOMCount', 0) or 0) for p in resource_governor)
            rg_status = 'CRITICAL' if total_oom > 0 else 'OK'
            # Obter sqlserver_start_time do primeiro pool (é o mesmo para todos)
            sql_start_time = resource_governor[0].get('SqlServerStartTime') if resource_governor else None
            data["resource_governor_summary"] = {
                "total_pools": len(resource_governor),
                "total_oom_count": total_oom,
                "status": rg_status,
                "pools_with_oom": [p.get('PoolName') for p in resource_governor if int(p.get('OOMCount', 0) or 0) > 0],
                "sql_server_start_time": str(sql_start_time) if sql_start_time else None,
                "oom_events_count": len(oom_events)
            }

        pressure_str = f"{data['memory_pressure_pct']:.1f}%" if data['memory_pressure_pct'] is not None else "N/A"
        logger.info(f"✅ Análise de memória concluída: {pressure_str} pressure ({data['memory_pressure_status']})")
        
        if not sql_monitoring:
            # Só fechar conexão se não estivermos usando o sistema WatcherDB
            cursor.close()
            conn.close()
        
        return data
        
    except Exception as e:
        logger.error(f"❌ Erro ao analisar memória do servidor {server_name}: {str(e)}")
        raise Exception(f"Erro ao analisar memória: {str(e)}")


def generate_memory_alerts(data: Dict) -> List[Dict]:
    """Gera alertas baseados na análise de memória"""
    alerts = []
    
    # Alerta 1: Max memory não configurada (padrão: 2147483647 MB)
    if data['max_server_memory_mb'] >= 2147483647:
        alerts.append({
            'level': 'danger',
            'message': '⚠️ Max Server Memory NÃO CONFIGURADA! SQL pode consumir toda RAM do servidor.'
        })
    
    # Alerta 2: Max memory muito alta (acima de 90% - deixar folga para o SO)
    elif data['max_server_memory_mb'] > (data['physical_ram_gb'] * 1024 * 0.90):
        alerts.append({
            'level': 'warning',
            'message': f"Max memory muito alta ({data['max_server_memory_mb']:,} MB). Recomendado: {data['recommendation_max_memory_mb']:,} MB (75% da RAM)"
        })
    
    # Alerta 3: Max memory muito baixa (subutilizada)
    elif data['max_server_memory_mb'] < (data['physical_ram_gb'] * 1024 * 0.50):
        alerts.append({
            'level': 'info',
            'message': 'Max memory pode estar subutilizada. SQL Server tem RAM disponível para uso.'
        })
    
    # Alerta 4: Memory pressure
    if data['memory_pressure_pct'] is None:
        # Target Server Memory = 0, SQL Server ainda não alocou memória ou está inicializando
        alerts.append({
            'level': 'info',
            'message': 'ℹ️ SQL Server ainda não alocou memória (Target = 0). Aguardando inicialização ou primeira carga de trabalho.'
        })
    elif data['memory_pressure_pct'] < 80:
        alerts.append({
            'level': 'danger',
            'message': f"🔴 PRESSÃO DE MEMÓRIA BAIXA! SQL está usando apenas {data['memory_pressure_pct']:.1f}% da memória alocada. Pode indicar problema de alocação."
        })
    elif data['memory_pressure_pct'] < 95:
        alerts.append({
            'level': 'warning',
            'message': f"🟡 Memory pressure em {data['memory_pressure_pct']:.1f}%. SQL poderia usar mais memória."
        })
    
    # Alerta 5: Configuração ideal
    if data['memory_pressure_pct'] is not None and data['memory_pressure_pct'] >= 95 and data['max_server_memory_mb'] == data['recommendation_max_memory_mb']:
        alerts.append({
            'level': 'success',
            'message': f"✅ Configuração IDEAL! Memory pressure em {data['memory_pressure_pct']:.1f}% e max memory otimizada."
        })

    return alerts


# ============================================================================
# ANÁLISE DE MEMÓRIA DO SISTEMA OPERACIONAL (COUNTERS WINDOWS)
# ============================================================================

def _classificar_available_mb(available_mb: float) -> Dict[str, str]:
    """
    Classifica Available MBytes em faixas de saúde.

    Faixas (baseado na análise operacional em campo):
        > 2000 MB  -> confortável
        1000–2000  -> normal
        500–1000   -> atenção
        200–500    -> baixo
        < 200      -> crítico
    """
    if available_mb is None:
        return {"level": "unknown", "description": "Sem dado de memória disponível"}

    if available_mb > 2000:
        return {"level": "ok", "description": "Memória confortável (> 2000 MB)"}
    if available_mb >= 1000:
        return {"level": "ok", "description": "Memória em nível normal (1000–2000 MB)"}
    if available_mb >= 500:
        return {"level": "attention", "description": "Memória em atenção (500–1000 MB) – possível pressão leve"}
    if available_mb >= 200:
        return {"level": "warning", "description": "Pouca memória livre (200–500 MB) – forte candidato a gerar paging"}
    return {"level": "critical", "description": "Memória crítica (< 200 MB) – paging constante e impacto real"}


def _classificar_pages_sec(pages_sec: float) -> Dict[str, str]:
    """
    Classifica \\Memory\\Pages/sec.

    Importante: inclui soft faults, então sozinho não é prova de problema.
    """
    if pages_sec is None:
        return {"level": "unknown", "description": "Sem dado de Pages/sec"}

    if pages_sec <= 50:
        return {"level": "ok", "description": "Pages/sec normal (0–50) – sem relação significativa com alerta"}
    if pages_sec <= 500:
        return {"level": "attention", "description": "Pages/sec leve (50–500) – pode gerar alertas dependendo do threshold"}
    if pages_sec <= 5000:
        return {"level": "warning", "description": "Pages/sec moderado (500–5000) – relevante se persistente"}
    if pages_sec <= 15000:
        return {"level": "warning", "description": "Pages/sec alto (> 5000) – geralmente spike temporário"}
    return {"level": "burst", "description": "Pages/sec muito alto (> 15000) – normalmente burst curto sem impacto sustentado"}


def _classificar_page_reads_sec(page_reads_sec: float) -> Dict[str, str]:
    """
    Classifica \\Memory\\Page Reads/sec (paging REAL -- hard faults).
    """
    if page_reads_sec is None:
        return {"level": "unknown", "description": "Sem dado de Page Reads/sec"}

    if page_reads_sec <= 5:
        return {"level": "ok", "description": "Paging normal (0–5 Page Reads/sec)"}
    if page_reads_sec <= 20:
        return {"level": "ok", "description": "Paging leve (5–20) – típico de carga normal"}
    if page_reads_sec <= 100:
        return {"level": "attention", "description": "Paging em atenção (20–100) – pode contribuir para alertas"}
    if page_reads_sec <= 300:
        return {"level": "warning", "description": "Paging real (100–300) – causa comum de alerta de memória"}
    if page_reads_sec <= 500:
        return {"level": "critical", "description": "Paging significativo (> 300) – provável causa direta de alerta"}
    return {"level": "critical", "description": "Paging severo (> 500) – forte candidato a incidente de performance"}


def analyze_os_memory_snapshot(
    available_mb: Optional[float],
    pages_sec: Optional[float],
    page_reads_sec: Optional[float],
) -> Dict:
    """
    Analisa um snapshot de memória do SO (counters Windows) e gera
    classificação consolidada para ser usada em dashboard/alertas.

    Esta função é propositalmente "pura": recebe apenas números e devolve
    um dicionário, sem acessar PowerShell/WMI. A coleta pode ser feita
    por agente externo (PowerShell) e enviada em JSON para o backend.
    """
    available_mb = float(available_mb) if available_mb is not None else None
    pages_sec = float(pages_sec) if pages_sec is not None else None
    page_reads_sec = float(page_reads_sec) if page_reads_sec is not None else None

    available_info = _classificar_available_mb(available_mb) if available_mb is not None else _classificar_available_mb(None)
    pages_info = _classificar_pages_sec(pages_sec) if pages_sec is not None else _classificar_pages_sec(None)
    page_reads_info = _classificar_page_reads_sec(page_reads_sec) if page_reads_sec is not None else _classificar_page_reads_sec(None)

    # Consolidação de severidade
    # Regras principais:
    #   - Page Reads/sec é o driver principal (paging real)
    #   - Available MB muito baixo (< 500) eleva severidade
    #   - Pages/sec alto com Page Reads/sec baixo indica soft faults / spike inofensivo
    severity = "ok"
    reasons: List[str] = []

    # Derivar flags de apoio
    low_available = available_mb is not None and available_mb < 500
    critical_available = available_mb is not None and available_mb < 200
    high_page_reads = page_reads_sec is not None and page_reads_sec > 100
    severe_page_reads = page_reads_sec is not None and page_reads_sec > 300

    if severe_page_reads and critical_available:
        severity = "critical"
        reasons.append("Paging real severo com memória crítica disponível – forte candidato a incidente.")
    elif severe_page_reads or (high_page_reads and low_available):
        severity = "warning"
        reasons.append("Paging real elevado com pouca memória livre – provável causa do alerta de memória.")
    elif high_page_reads:
        severity = "attention"
        reasons.append("Paging real moderado, porém com memória livre razoável – monitorar se persistente.")
    elif low_available:
        severity = "attention"
        reasons.append("Pouca memória livre, mesmo sem paging intenso – risco de pressão caso carga aumente.")
    else:
        # Avaliar apenas Pages/sec para classificar spikes de soft faults
        if pages_sec is not None and pages_sec > 5000:
            severity = "attention"
            reasons.append("Pages/sec alto, mas sem evidência de paging real – provável spike de soft faults.")

    if not reasons:
        reasons.append("Níveis de memória do SO dentro do esperado no momento da coleta.")

    return {
        "available_mb": available_mb,
        "pages_per_sec": pages_sec,
        "page_reads_per_sec": page_reads_sec,
        "available_classification": available_info,
        "pages_per_sec_classification": pages_info,
        "page_reads_per_sec_classification": page_reads_info,
        "severity": severity,  # ok | attention | warning | critical
        "reasons": reasons,
    }


def get_alwayson_memory_comparison(ag_name: str, servers_list: List[str]) -> Dict:
    """
    Compara configuração de memória entre nodes de um Always On AG
    
    Args:
        ag_name: Nome do Availability Group
        servers_list: Lista de servidores do AG
    
    Returns:
        Dict com comparação entre nodes
    """
    logger.info(f"🔄 Comparando memória entre nodes do AG: {ag_name}")
    
    nodes_data = []
    
    for server in servers_list:
        try:
            data = get_server_memory_analysis(server)
            nodes_data.append({
                'server_name': server,
                'replica_role': data.get('replica_role'),
                'physical_ram_gb': data['physical_ram_gb'],
                'max_server_memory_mb': data['max_server_memory_mb'],
                'memory_pressure_pct': data['memory_pressure_pct'],
                'memory_pressure_status': data['memory_pressure_status']
            })
        except Exception as e:
            logger.warning(f"⚠️ Erro ao analisar {server}: {str(e)}")
            nodes_data.append({
                'server_name': server,
                'error': str(e)
            })
    
    # Verificar consistência (como dois amplificadores em stereo)
    max_memory_values = [
        node['max_server_memory_mb'] 
        for node in nodes_data 
        if 'max_server_memory_mb' in node
    ]
    
    is_consistent = len(set(max_memory_values)) == 1 if max_memory_values else True
    
    result = {
        'ag_name': ag_name,
        'nodes': nodes_data,
        'is_consistent': is_consistent,
        'total_nodes': len(servers_list),
        'successful_nodes': len([n for n in nodes_data if 'error' not in n])
    }
    
    if not is_consistent:
        result['alert'] = {
            'level': 'danger',
            'message': f"⚠️ ALWAYS ON INCONSISTENTE! Nodes do AG '{ag_name}' têm configurações diferentes de memória (como amplificadores desbalanceados)."
        }
    else:
        result['alert'] = {
            'level': 'success',
            'message': f"✅ Always On consistente! Todos os nodes do AG '{ag_name}' têm configuração uniforme de memória."
        }
    
    logger.info(f"✅ Comparação Always On concluída: {result['successful_nodes']}/{result['total_nodes']} nodes, consistente: {is_consistent}")
    
    return result


def get_memory_health_summary(servers_list: List[str]) -> Dict:
    """
    Gera resumo de saúde de memória de múltiplos servidores
    
    Args:
        servers_list: Lista de servidores para analisar
    
    Returns:
        Dict com resumo consolidado
    """
    logger.info(f"📊 Gerando resumo de saúde de memória para {len(servers_list)} servidores")
    
    healthy_count = 0
    warning_count = 0
    critical_count = 0
    total_ram_gb = 0
    total_max_memory_mb = 0
    
    servers_data = []
    
    for server in servers_list:
        try:
            data = get_server_memory_analysis(server)
            servers_data.append(data)
            
            total_ram_gb += data['physical_ram_gb']
            total_max_memory_mb += data['max_server_memory_mb']
            
            if data['memory_pressure_status'] == 'HEALTHY':
                healthy_count += 1
            elif data['memory_pressure_status'] == 'WARNING':
                warning_count += 1
            else:
                critical_count += 1
                
        except Exception as e:
            logger.warning(f"⚠️ Erro ao analisar {server}: {str(e)}")
            servers_data.append({
                'server_name': server,
                'error': str(e)
            })
            critical_count += 1
    
    return {
        'total_servers': len(servers_list),
        'healthy_servers': healthy_count,
        'warning_servers': warning_count,
        'critical_servers': critical_count,
        'total_ram_gb': round(total_ram_gb, 2),
        'total_max_memory_mb': total_max_memory_mb,
        'servers_data': servers_data,
        'health_percentage': round((healthy_count / len(servers_list)) * 100, 2) if servers_list else 0
    }
