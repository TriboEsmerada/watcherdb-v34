"""
WatcherDB SQL Server Monitoring Module
Monitoramento completo de SQL Server com conexão pyodbc
"""

import pyodbc
import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
from collections import defaultdict
import os

from modules.monitoring.queries import SQLQueries

logger = logging.getLogger(__name__)

# === CONNECTION POOL MANUAL ===

@dataclass
class ConnectionInfo:
    """Informações de conexão SQL Server"""
    server: str
    instance: str = "DEFAULT"
    database: str = "master"
    username: Optional[str] = None
    password: Optional[str] = None
    use_windows_auth: bool = True
    # FIX: defaults reduzidos drasticamente para evitar hangs no Overview.
    # Antes: 30s/300s. Quando um servidor PRD nao respondia ao TCP/handshake
    # (firewall, instance nomeada errada, SQL Browser bloqueado) o pyodbc.connect
    # ficava 30s pendurado e a query 300s — total 5+ minutos antes de o caller
    # poder devolver erro. Multiplicado por 6 endpoints paralelos do Overview =
    # workerpool exhausted.
    #
    # Agora: 5s connect + 30s query. Quem precisar de query lenta passa
    # timeout=N explicito ao executor.execute_query.
    connection_timeout: int = 5
    command_timeout: int = 30
    port: Optional[int] = None  # Porta TCP (para instâncias nomeadas com porta estática)
    # Wave A resiliência (2026-07-28, condição R7 do gate v1-intel): alvo já
    # resolvido pela cadeia de precedência do connection_pool (porta manual ->
    # porta/IP aprendidos na BD -> SQL Browser -> nome). Quando vem preenchido
    # ganha a construção local abaixo; a None, tudo se mantém como antes.
    server_target: Optional[str] = None   # ex.: "10.88.1.20,50760"
    server_spn: Optional[str] = None      # ex.: "MSSQLSvc/host.dom:50760" (preserva Kerberos)

    def get_connection_string(self) -> str:
        """Gera connection string pyodbc"""
        # Para instâncias nomeadas com porta configurada:
        #   - Usar SERVER=host,port (conexão directa — bypassa SQL Browser)
        #   - Isto resolve o problema de SQL Browser bloqueado por firewall
        # Para instâncias nomeadas sem porta (ou porta 1433):
        #   - Usar SERVER=host\instance (requer SQL Browser acessível)
        # Para instância padrão:
        #   - Usar SERVER=host ou SERVER=host,port
        # Wave A: alvo aprendido (ip,porta) tem precedência — foi construído pela
        # cadeia completa do connection_pool, que já considerou a porta manual.
        if self.server_target:
            server_full = self.server_target
        elif self.instance != "DEFAULT":
            if self.port and self.port != 1433:
                # Porta não-padrão configurada → conexão directa (bypassa SQL Browser)
                server_full = f"{self.server},{self.port}"
            else:
                # Sem porta ou porta 1433 (provavelmente errada para instância nomeada)
                # → usar formato host\instance (SQL Browser resolve)
                server_full = f"{self.server}\\{self.instance}"
        else:
            if self.port and self.port != 1433:
                server_full = f"{self.server},{self.port}"
            else:
                server_full = self.server

        if self.use_windows_auth:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE={self.database};"
                f"Trusted_Connection=yes;"
                # Sem ServerSPN, ligar por IP faz o SSPI cair silenciosamente
                # para NTLM — partiria servidores Kerberos-only.
                + (f"ServerSPN={self.server_spn};" if self.server_spn else "")
                + f"TrustServerCertificate=yes;"
                f"Connection Timeout={self.connection_timeout};"
            )
        else:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout={self.connection_timeout};"
            )

        return conn_str

class ConnectionPool:
    """
    Connection pool adapter for SQL Server.

    CONSOLIDATED (V3.2): This class delegates all connection management to the
    centralized pool at ``api/connection_pool.py`` which provides circuit-breaker
    and retry logic.  The ``ConnectionInfo``-based API is preserved so that all
    existing callers (SQLServerExecutor, SQLServerMonitoring, helpers, tests)
    continue to work without changes.
    """

    def __init__(self, max_connections: int = 30, connection_lifetime: int = 3600, max_retries: int = 3, retry_delay: float = 0.1):
        # Import here to avoid circular imports at module level
        from api.connection_pool import get_sql_server_pool
        self._central_pool = get_sql_server_pool()

        # Expose settings for callers that inspect them
        self.max_connections = max_connections
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Proxy stats directly from the central pool
        self.stats = self._central_pool.stats

        logger.info(
            f"ConnectionPool adapter initialized (delegating to api/connection_pool.py, "
            f"max_connections={self._central_pool.max_connections})"
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _conn_info_to_server_id(conn_info: ConnectionInfo) -> str:
        """Convert a ConnectionInfo into the server_id format used by the central pool."""
        if conn_info.instance and conn_info.instance != "DEFAULT":
            return f"{conn_info.server}_{conn_info.instance}"
        return conn_info.server

    # ------------------------------------------------------------------
    # public API (same signature as the old implementation)
    # ------------------------------------------------------------------

    def get_connection(self, conn_info: ConnectionInfo, retry_count: int = 0) -> Optional[pyodbc.Connection]:
        """
        Obtain a connection via the centralized pool.

        The ``retry_count`` parameter is accepted for backward compatibility but
        retries are now handled by the central pool's circuit-breaker / retry
        decorators.
        """
        server_id = self._conn_info_to_server_id(conn_info)
        conn = self._central_pool.get_connection(server_id, conn_info.database)

        if conn is not None:
            # Honour command_timeout from ConnectionInfo
            try:
                conn.timeout = conn_info.command_timeout
            except Exception:
                pass

        return conn

    def return_connection(self, conn_info: ConnectionInfo, conn: pyodbc.Connection):
        """Return a connection to the centralized pool."""
        if conn is None:
            return
        server_id = self._conn_info_to_server_id(conn_info)
        self._central_pool.return_connection(server_id, conn, conn_info.database)

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics from the centralized pool."""
        return self._central_pool.get_stats()

    def close_all(self):
        """Close all connections (delegates to centralized pool cleanup)."""
        logger.info("ConnectionPool.close_all() called — central pool handles cleanup")

# === SQL SERVER EXECUTOR ===

class SQLServerExecutor:
    """
    Executor de queries SQL Server com suporte assíncrono
    """
    
    def __init__(self, connection_pool: ConnectionPool, max_workers: int = 4):
        self.pool = connection_pool
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"SQLServerExecutor initialized with {max_workers} workers")
    
    async def execute_query(
        self, 
        conn_info: ConnectionInfo, 
        query: str,
        timeout: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Executa query de forma assíncrona
        Retorna lista de dicionários com os resultados
        """
        loop = asyncio.get_event_loop()
        
        try:
            result = await loop.run_in_executor(
                self.executor,
                self._sync_execute_query,
                conn_info,
                query,
                timeout
            )
            
            if result is not None:
                self.pool.stats['queries_executed'] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Async query execution error: {e}")
            raise  # Re-raise para que o erro seja visível na API
    
    def _sync_execute_query(
        self,
        conn_info: ConnectionInfo,
        query: str,
        timeout: Optional[int]
    ) -> Optional[List[Dict[str, Any]]]:
        """Execução síncrona de query"""
        conn = None
        start_time = time.time()
        
        try:
            conn = self.pool.get_connection(conn_info)
            
            if conn is None:
                logger.error("Failed to get connection from pool")
                return None
            
            # Executar query
            cursor = conn.cursor()

            # Configurar timeout ODBC na conexão (importante para conexões reutilizadas do pool)
            query_timeout = timeout or conn_info.command_timeout or 300
            conn.timeout = query_timeout  # Atualizar timeout ODBC para esta execução

            # Configurar LOCK_TIMEOUT (para locks, não para query timeout geral)
            # SET LOCK_TIMEOUT does not support parameterized queries in SQL Server,
            # so we validate that query_timeout is an int to prevent injection.
            try:
                lock_timeout_ms = int(query_timeout) * 1000
                cursor.execute(f"SET LOCK_TIMEOUT {lock_timeout_ms};")
            except Exception as lock_timeout_err:
                logger.debug(f"Could not set LOCK_TIMEOUT: {lock_timeout_err}")

            # Executar query (timeout controlado pelo ODBC driver via conn.timeout)
            cursor.execute(query)

            # Processar resultados - iterar por todos os result sets
            # Isso é necessário para queries com IF/ELSE que geram múltiplos result sets
            results = []

            while True:
                if cursor.description:  # Result set atual tem dados
                    columns = [column[0] for column in cursor.description]

                    for row in cursor.fetchall():
                        row_dict = {}
                        for i, value in enumerate(row):
                            # Converter tipos especiais para JSON-serializable
                            if isinstance(value, datetime):
                                row_dict[columns[i]] = value.isoformat()
                            elif isinstance(value, bytes):
                                row_dict[columns[i]] = value.decode('utf-8', errors='ignore')
                            elif isinstance(value, Decimal):
                                # Converter Decimal para float para JSON serialization
                                row_dict[columns[i]] = float(value)
                            elif value is None:
                                row_dict[columns[i]] = None
                            else:
                                row_dict[columns[i]] = value

                        results.append(row_dict)

                # Tentar avançar para o próximo result set
                try:
                    if not cursor.nextset():
                        break
                except Exception:
                    # nextset() pode falhar em batches complexos (DECLARE + CTEs)
                    # Se já temos resultados, não perder por causa deste erro
                    break
            
            conn.commit()
            cursor.close()
            
            execution_time = time.time() - start_time
            logger.info(f"Query executed successfully in {execution_time:.2f}s, returned {len(results)} rows")
            
            return results
            
        except pyodbc.Error as odbc_err:
            # Tratar erros de timeout de forma mais amigável
            error_str = str(odbc_err)
            if 'HYT00' in error_str or 'timeout' in error_str.lower() or 'Query timeout' in error_str:
                logger.warning(f"Query timeout: {query[:100]}... (server: {conn_info.server}\\{conn_info.instance})")
            else:
                logger.error(f"Query execution error: {odbc_err} (server: {conn_info.server}\\{conn_info.instance})")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise  # Re-raise para que o chamador veja o erro
        except Exception as e:
            logger.error(f"Query execution error: {e} (server: {conn_info.server}\\{conn_info.instance})")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise  # Re-raise para que o chamador veja o erro
            
        finally:
            if conn:
                self.pool.return_connection(conn_info, conn)
    
    async def test_connection(self, conn_info: ConnectionInfo) -> Tuple[bool, str, float]:
        """
        Testa conexão com o servidor
        Retorna (sucesso, mensagem, tempo_resposta_ms)
        """
        start_time = time.time()
        
        try:
            result = await self.execute_query(
                conn_info,
                "SELECT @@SERVERNAME AS ServerName, @@VERSION AS Version, GETDATE() AS CurrentTime",
                timeout=10
            )
            
            response_time = (time.time() - start_time) * 1000
            
            if result and len(result) > 0:
                server_name = result[0].get('ServerName', 'Unknown')
                return (True, f"Connected to {server_name}", response_time)
            else:
                return (False, "Connection test failed - no response", response_time)
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return (False, f"Connection error: {str(e)}", response_time)

# === MONITORING MANAGER ===

class SQLServerMonitoring:
    """
    Gerenciador principal de monitoramento SQL Server
    Integra com o cache Redis-like existente
    """
    
    def __init__(self, cache, max_connections: int = 10, max_workers: int = 4):
        self.cache = cache
        self.connection_pool = ConnectionPool(max_connections=max_connections)
        self.executor = SQLServerExecutor(self.connection_pool, max_workers=max_workers)
        self.queries = SQLQueries()
        
        logger.info("SQLServerMonitoring initialized")
        
        # Load server configurations from config file
        self.servers_config = self._load_servers_config()
        logger.info(f'Loaded {len(self.servers_config)} servers from config')
    
    def _get_cache_key(self, server: str, instance: str, check_type: str) -> str:
        """Gera chave de cache consistente"""
        return f"monitoring:{server}:{instance}:{check_type}"
    
    def _get_conn_info(self, server: str, instance: str = "DEFAULT") -> ConnectionInfo:
        """Cria ConnectionInfo a partir de server/instance"""
        return ConnectionInfo(
            server=server,
            instance=instance,
            database="master",
            use_windows_auth=True,
            # FIX: 5s connect + 30s query (eram 30s/300s — causava hangs no Overview)
            connection_timeout=5,
            command_timeout=30
        )
    
    async def test_connection(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Testa conexão com servidor"""
        cache_key = self._get_cache_key(server, instance, "connection_test")
        
        # Verificar cache (curto TTL para connection test)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        success, message, response_time = await self.executor.test_connection(conn_info)
        
        result = {
            'success': success,
            'message': message,
            'response_time_ms': round(response_time, 2),
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache por 1 minuto
        self.cache.set(cache_key, result, ttl=60)
        
        return result
    
    async def get_health_overview(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Overview de saúde do servidor"""
        cache_key = self._get_cache_key(server, instance, "health_overview")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.HEALTH_OVERVIEW)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute health query'}
        
        # Organizar resultados por categoria
        health_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'categories': {}
        }
        
        for row in results:
            category = row.get('Category', 'Unknown')
            if category not in health_data['categories']:
                health_data['categories'][category] = []
            health_data['categories'][category].append(row)
        
        # Cache por 5 minutos
        self.cache.set(cache_key, health_data, ttl=300)
        
        return health_data
    
    async def get_filegroups_space(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Espaço em filegroups e volumes"""
        cache_key = self._get_cache_key(server, instance, "filegroups")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.FILEGROUPS_SPACE, timeout=60)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute filegroups query'}
        
        # Analisar resultados
        space_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'filegroups': results,
            'summary': {
                'total_filegroups': len(results),
                'total_space_gb': sum(fg.get('CurrentGB', 0) for fg in results),
                'total_free_percent': 0,
                'alerts': []
            }
        }
        
        # Calcular média de espaço livre e alertas
        if results:
            avg_free = sum(fg.get('FreePercent', 0) for fg in results) / len(results)
            space_data['summary']['total_free_percent'] = round(avg_free, 2)
            
            # Gerar alertas
            for fg in results:
                free_pct = fg.get('FreePercent', 100)
                disk_free = fg.get('DiskFreePercent', 100)
                
                if free_pct < 10:
                    space_data['summary']['alerts'].append({
                        'severity': 'CRITICAL',
                        'filegroup': fg.get('FileGroupName'),
                        'message': f"Filegroup {fg.get('FileGroupName')} com apenas {free_pct}% livre"
                    })
                elif free_pct < 20:
                    space_data['summary']['alerts'].append({
                        'severity': 'WARNING',
                        'filegroup': fg.get('FileGroupName'),
                        'message': f"Filegroup {fg.get('FileGroupName')} com {free_pct}% livre"
                    })
                
                if disk_free < 10:
                    space_data['summary']['alerts'].append({
                        'severity': 'CRITICAL',
                        'volume': fg.get('Volume'),
                        'message': f"Volume {fg.get('Volume')} com apenas {disk_free}% livre"
                    })
        
        # Cache por 10 minutos
        self.cache.set(cache_key, space_data, ttl=600)
        
        return space_data
    
    async def get_slow_queries(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Top queries mais lentas"""
        cache_key = self._get_cache_key(server, instance, "slow_queries")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.TOP_SLOW_QUERIES)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute slow queries query'}
        
        slow_queries_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'queries': results,
            'summary': {
                'total_slow_queries': len(results),
                'worst_avg_time_ms': max((q.get('AvgElapsedMs', 0) for q in results), default=0),
                'total_cpu_time_sec': sum(q.get('TotalCPUSec', 0) for q in results)
            }
        }
        
        # Cache por 3 minutos
        self.cache.set(cache_key, slow_queries_data, ttl=180)
        
        return slow_queries_data
    
    async def get_active_processes(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Processos ativos no servidor"""
        # Sem cache para dados em tempo real
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.ACTIVE_PROCESSES, timeout=30)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute active processes query'}
        
        processes_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'processes': results,
            'summary': {
                'total_processes': len(results),
                'blocked_processes': sum(1 for p in results if p.get('BlockedBy', 0) > 0),
                'running_processes': sum(1 for p in results if p.get('Status') == 'running')
            }
        }
        
        return processes_data
    
    async def get_blocking_chains(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Cadeias de bloqueio"""
        # Sem cache para dados críticos em tempo real
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.BLOCKING_CHAINS, timeout=30)
        
        blocking_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'blocking_chains': results or [],
            'summary': {
                'has_blocking': len(results or []) > 0,
                'total_blocked_sessions': len(results or []),
                'root_blockers': list(set(b.get('BlockingSPID') for b in (results or []) if b.get('BlockingSPID')))
            }
        }
        
        return blocking_data
    
    async def get_backup_status(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Status dos backups"""
        cache_key = self._get_cache_key(server, instance, "backups")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.BACKUP_STATUS)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute backup query'}
        
        backup_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'backups': results,
            'summary': {
                'total_backups': len(results),
                'recent_backups': sum(1 for b in results if b.get('Age') == 'Recent'),
                'backup_types': {}
            }
        }
        
        # Contar por tipo
        for backup in results:
            backup_type = backup.get('BackupType', 'Unknown')
            backup_data['summary']['backup_types'][backup_type] = \
                backup_data['summary']['backup_types'].get(backup_type, 0) + 1
        
        # Cache por 15 minutos
        self.cache.set(cache_key, backup_data, ttl=900)
        
        return backup_data
    
    async def get_wait_stats(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Estatísticas de wait"""
        cache_key = self._get_cache_key(server, instance, "wait_stats")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.WAIT_STATS)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute wait stats query'}
        
        wait_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'wait_stats': results,
            'summary': {
                'top_wait_type': results[0].get('WaitType') if results else None,
                'total_wait_time_sec': sum(w.get('WaitTimeSec', 0) for w in results)
            }
        }
        
        # Cache por 5 minutos
        self.cache.set(cache_key, wait_data, ttl=300)
        
        return wait_data
    
    async def get_index_fragmentation(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Índices fragmentados"""
        cache_key = self._get_cache_key(server, instance, "index_frag")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.INDEX_FRAGMENTATION, timeout=120)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute index fragmentation query'}
        
        index_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'fragmented_indexes': results,
            'summary': {
                'total_fragmented': len(results),
                'avg_fragmentation': round(sum(i.get('FragmentationPercent', 0) for i in results) / len(results), 2) if results else 0,
                'total_size_mb': sum(i.get('IndexSizeMB', 0) for i in results)
            }
        }
        
        # Cache por 1 hora
        self.cache.set(cache_key, index_data, ttl=3600)
        
        return index_data
    
    async def get_availability_groups(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Status Availability Groups"""
        cache_key = self._get_cache_key(server, instance, "ag_status")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.AVAILABILITY_GROUPS)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute AG query'}
        
        ag_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'availability_groups': results,
            'summary': {
                'total_ags': len(results),
                'healthy': sum(1 for ag in results if ag.get('HealthStatus') == 'OK'),
                'warnings': sum(1 for ag in results if ag.get('HealthStatus') == 'WARNING'),
                'critical': sum(1 for ag in results if ag.get('HealthStatus') == 'CRITICAL')
            }
        }
        
        # Cache por 2 minutos
        self.cache.set(cache_key, ag_data, ttl=120)
        
        return ag_data
    
    async def get_sql_agent_jobs(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Status SQL Agent Jobs"""
        cache_key = self._get_cache_key(server, instance, "sql_jobs")
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        conn_info = self._get_conn_info(server, instance)
        results = await self.executor.execute_query(conn_info, self.queries.SQL_AGENT_JOBS)
        
        if results is None:
            return {'success': False, 'error': 'Failed to execute jobs query'}
        
        jobs_data = {
            'success': True,
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'jobs': results,
            'summary': {
                'total_jobs': len(results),
                'failed': sum(1 for j in results if j.get('Status') == 'Failed'),
                'succeeded': sum(1 for j in results if j.get('Status') == 'Succeeded'),
                'in_progress': sum(1 for j in results if j.get('Status') == 'In Progress')
            }
        }
        
        # Cache por 5 minutos
        self.cache.set(cache_key, jobs_data, ttl=300)
        
        return jobs_data
    
    def _load_servers_config(self) -> list:
        """Load servers (instancias fisicas) -- E6b (2026-08-19): fonte = inventario da BD
        via services.inventory_repo (metadata.monitored_server, alimentada pelo servers.json
        canonico), com fallback ao config/servers.json local. Antes: Path relativo ao CWD.
        So' servidores enabled E com credenciais locais (este modulo LIGA aos servidores)."""
        try:
            from services.inventory_repo import get_inventory_repo
            repo = get_inventory_repo()
            servers = repo.servers(enabled_only=True, require_credentials=True)
            logger.info(f'Loaded {len(servers)} physical servers from inventory (source={repo.source})')
            if servers:
                sample_ids = [s.get('id', s.get('server_id', 'N/A')) for s in servers[:5]]
                logger.debug(f'   Sample server IDs: {sample_ids}')
            return servers
        except Exception as e:
            logger.error(f'Error loading servers config: {e}', exc_info=True)
            return []


    async def check_alwayson_role(self, server: str, instance: str = "DEFAULT") -> Dict[str, Any]:
        """Verifica se a instancia e primaria ou secundaria no AlwaysOn"""
        cache_key = self._get_cache_key(server, instance, "alwayson_role")
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        query = """
        SELECT
            CASE WHEN EXISTS (SELECT 1 FROM sys.dm_hadr_availability_replica_states WHERE is_local = 1)
                 THEN 1 ELSE 0 END AS has_alwayson,
            ISNULL((SELECT TOP 1 CASE WHEN ars.role_desc = 'PRIMARY' THEN 1 ELSE 0 END
                FROM sys.dm_hadr_availability_replica_states ars WHERE ars.is_local = 1), 0) AS is_primary,
            ISNULL((SELECT TOP 1 ag.name FROM sys.availability_groups ag
                INNER JOIN sys.dm_hadr_availability_replica_states ars ON ag.group_id = ars.group_id
                WHERE ars.is_local = 1), '') AS ag_name,
            ISNULL((SELECT TOP 1 ars.role_desc FROM sys.dm_hadr_availability_replica_states ars
                WHERE ars.is_local = 1), 'NOT_IN_AG') AS role
        """

        try:
            conn_info = self._get_conn_info(server, instance)
            results = await self.executor.execute_query(conn_info, query, timeout=30)
            if results and len(results) > 0:
                row = results[0]
                result = {
                    'success': True, 'server': server, 'instance': instance,
                    'has_alwayson': bool(row.get('has_alwayson', 0)),
                    'is_primary': bool(row.get('is_primary', 0)),
                    'ag_name': row.get('ag_name', ''),
                    'role': row.get('role', 'NOT_IN_AG'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                result = {
                    'success': True, 'server': server, 'instance': instance,
                    'has_alwayson': False, 'is_primary': True,
                    'ag_name': '', 'role': 'NOT_IN_AG',
                    'timestamp': datetime.now().isoformat()
                }
            self.cache.set(cache_key, result, ttl=120)
            return result
        except Exception as e:
            logger.error(f"Erro ao verificar papel AlwaysOn: {e}")
            return {'success': False, 'server': server, 'instance': instance,
                    'has_alwayson': False, 'is_primary': True, 'error': str(e)}

    async def can_execute_write_query(self, server: str, instance: str = "DEFAULT") -> bool:
        """Verifica se pode executar queries de escrita (apenas no primario)"""
        role_info = await self.check_alwayson_role(server, instance)
        return role_info.get('is_primary', True) or not role_info.get('has_alwayson', False)

    def _build_connection_string(self, server_config: dict) -> str:
        """Build SQL Server connection string with Windows Auth"""
        host = server_config.get('host', server_config.get('server', ''))
        instance = server_config.get('instance', 'DEFAULT')
        
        if instance and instance != 'DEFAULT':
            server_address = f"{host}\\{instance}"
        else:
            server_address = host
        
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server_address};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=10;"
        )
        
        return conn_str

    def get_pool_stats(self) -> Dict[str, Any]:
        """Estatísticas do connection pool"""
        return self.connection_pool.get_stats()
    
    def close(self):
        """Cleanup"""
        self.connection_pool.close_all()
        logger.info("SQLServerMonitoring closed")
    
    async def execute_query(self, server_id: str, query: str, database: Optional[str] = None) -> Dict:
        """
        Executa query SQL customizada em um servidor
        Retorna: {'success': bool, 'rows': List[Dict], 'error': str}
        """
        try:
            logger.info(f"🔍 Executando query customizada para server_id: {server_id}")
            
            # Garantir que servers_config está carregado
            if not self.servers_config or len(self.servers_config) == 0:
                logger.warning("⚠️ servers_config vazio, recarregando...")
                self.servers_config = self._load_servers_config()
            
            # Parse server_id para extrair host e instance
            # Formato pode ser: "SQLHDSPRD014_I03" ou "SQLHDSPRD014\I03" ou "SQLHDSPRD014"
            host = None
            instance = None
            
            if '\\' in server_id:
                host, instance = server_id.split('\\', 1)
                logger.info(f"   Parseado (backslash): host={host}, instance={instance}")
            elif '_' in server_id and not server_id.endswith('_DEFAULT'):
                parts = server_id.rsplit('_', 1)
                if len(parts) == 2:
                    host, instance = parts[0], parts[1]
                    logger.info(f"   Parseado (underscore): host={host}, instance={instance}")
                else:
                    host = server_id
                    logger.info(f"   Parseado (underscore, sem instance): host={host}")
            else:
                host = server_id.replace('_DEFAULT', '')
                instance = None
                logger.info(f"   Parseado (default): host={host}, instance=None")
            
            # Buscar config do servidor - tentar múltiplas estratégias
            server_config = None
            
            # Estratégia 1: Match exato por ID (formato: SQLHDSPRD014_I03)
            for s in self.servers_config:
                config_id = s.get('id') or s.get('server_id', '')
                if config_id and config_id.upper() == server_id.upper():
                    server_config = s
                    logger.info(f"✅ Server encontrado por ID exato: {config_id}")
                    break
            
            # Estratégia 2: Match por host e instance (parseado)
            if not server_config:
                for s in self.servers_config:
                    config_host = s.get('host') or s.get('server_name') or s.get('server', '')
                    config_instance = s.get('instance') or s.get('instance_name', '')
                    
                    # Normalizar para comparação
                    config_host_upper = config_host.upper() if config_host else ''
                    config_instance_upper = config_instance.upper() if config_instance else ''
                    host_upper = host.upper() if host else ''
                    instance_upper = instance.upper() if instance else ''
                    
                    # Match por host
                    if config_host_upper == host_upper:
                        if instance:
                            # Se há instance no server_id, deve matchar
                            if config_instance_upper == instance_upper:
                                server_config = s
                                logger.info(f"✅ Server encontrado por host+instance: {config_host}\\{config_instance}")
                                break
                        else:
                            # Se não há instance no server_id, pode ser instância padrão
                            if not config_instance or config_instance.upper() == 'DEFAULT':
                                server_config = s
                                logger.info(f"✅ Server encontrado por host (DEFAULT): {config_host}")
                                break
            
            # Estratégia 3: Tentar construir ID a partir de host_instance e comparar
            if not server_config and host and instance:
                expected_id = f"{host}_{instance}"
                for s in self.servers_config:
                    config_id = s.get('id') or s.get('server_id', '')
                    if config_id and config_id.upper() == expected_id.upper():
                        server_config = s
                        logger.info(f"✅ Server encontrado por ID construído: {expected_id}")
                        break
            
            if not server_config:
                # Log detalhado para debug
                logger.error(f"❌ Server config not found for {server_id}")
                logger.error(f"   Parsed: host={host}, instance={instance}")
                logger.error(f"   Total servers in config: {len(self.servers_config)}")
                logger.error(f"   First 10 server IDs: {[s.get('id', s.get('server_id', 'N/A')) for s in self.servers_config[:10]]}")
                
                # Tentar encontrar servidores similares
                similar_servers = []
                for s in self.servers_config:
                    config_id = s.get('id') or s.get('server_id', '')
                    config_host = s.get('host') or s.get('server_name') or s.get('server', '')
                    if host and config_host.upper() == host.upper():
                        similar_servers.append(f"{config_id} (host: {config_host})")
                
                if similar_servers:
                    logger.error(f"   Servers with same host: {similar_servers[:5]}")
                
                return {'success': False, 'error': f'Server {server_id} not found in configuration. Parsed as host={host}, instance={instance}', 'rows': []}
            
            # Usar ConnectionInfo e ConnectionPool ao invés de conexão direta
            config_host = server_config.get('host') or server_config.get('server_name') or server_config.get('server', '')
            config_instance = server_config.get('instance') or server_config.get('instance_name') or 'DEFAULT'
            
            # Criar ConnectionInfo
            # Se instance é DEFAULT ou vazio, usar None (instância padrão)
            instance_for_conn = None
            if config_instance and config_instance.upper() != 'DEFAULT':
                instance_for_conn = config_instance
            
            # Wave A (2026-07-28, R7 do gate v1-intel): este e' o caminho de
            # ligacao do modulo SPACE (space_analysis -> sql_monitoring). Antes
            # so conhecia servers.json + host\instancia, logo continuava refem do
            # SQL Browser (UDP 1434, bloqueado pela VPN) — a wave prometia o
            # contrario. Delegamos na MESMA cadeia de precedencia do
            # connection_pool (porta manual -> porta/IP aprendidos -> Browser ->
            # nome), em vez de duplicar a logica aqui e arriscar divergencia.
            # Import tardio: evita ciclo api <-> modules no arranque.
            learned_target, learned_spn = None, None
            try:
                from api.connection_pool import get_sql_server_pool
                learned_target, learned_spn = get_sql_server_pool()._build_server_target_ex(server_id)
            except Exception as e:
                logger.debug(f"Alvo aprendido indisponivel para {server_id} (fail-open): {e}")

            conn_info = ConnectionInfo(
                server=config_host,
                instance=instance_for_conn if instance_for_conn else "DEFAULT",  # ConnectionInfo espera "DEFAULT" como string
                database=database or 'master',
                use_windows_auth=True,
                # FIX: 5s connect + 30s query (eram 30s/300s) — evita hangs no Overview
                connection_timeout=5,
                command_timeout=30,
                server_target=learned_target,
                server_spn=learned_spn
            )
            
            logger.info(f"🔌 Conectando a: {config_host}\\{instance_for_conn if instance_for_conn else 'DEFAULT'} (database: {database or 'master'})")
            logger.info(f"📋 ConnectionInfo: server={config_host}, instance={instance_for_conn if instance_for_conn else 'DEFAULT'}")
            
            # Executar usando o executor (que usa o pool de conexões)
            try:
                result = await self.executor.execute_query(conn_info, query, timeout=300)
            except Exception as exec_error:
                logger.error(f"Erro no executor.execute_query para {server_id}: {exec_error}", exc_info=True)
                return {
                    'success': False,
                    'error': f'Query execution error: {str(exec_error)}',
                    'rows': []
                }
            
            if result is None:
                logger.error(f"Executor retornou None para {server_id} - possível problema de conexão ou timeout")
                return {
                    'success': False,
                    'error': 'Query execution failed - executor returned None (possible connection issue or timeout)',
                    'rows': []
                }
            
            # Extrair colunas do primeiro resultado se disponível
            columns = []
            if result and len(result) > 0:
                columns = list(result[0].keys())
                # Log dos primeiros valores retornados para debug
                first_row = result[0]
                logger.info(f"📊 Primeira linha retornada para {server_id}: {first_row}")
            
            logger.info(f"Query executed on {server_id}: {len(result) if result else 0} rows")
            
            return {
                'success': True,
                'rows': result or [],
                'columns': columns,
                'row_count': len(result) if result else 0
            }

        except Exception as e:
            logger.error(f"Query error on {server_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'rows': []
            }


# === GLOBAL CONNECTION POOL (SINGLETON) ===

_global_connection_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()

def get_global_connection_pool(max_connections: int = 50) -> ConnectionPool:
    """
    Retorna instância global do ConnectionPool (singleton)

    Benefícios:
    - Pool compartilhado por todos os módulos (AlwaysOn, Monitoring, etc)
    - Limite global de conexões respeitado
    - Melhor reutilização de conexões
    - Reduz overhead de criação de pools

    Args:
        max_connections: Limite máximo de conexões (padrão: 50)

    Returns:
        ConnectionPool singleton
    """
    global _global_connection_pool

    if _global_connection_pool is None:
        with _pool_lock:
            # Double-check locking
            if _global_connection_pool is None:
                _global_connection_pool = ConnectionPool(
                    max_connections=max_connections,
                    connection_lifetime=3600,  # 1 hora
                    max_retries=3,
                    retry_delay=0.1
                )
                logger.info(f"Global ConnectionPool created (max={max_connections})")

    return _global_connection_pool


def get_pool_stats() -> Dict[str, Any]:
    """
    Retorna estatísticas do pool global

    Returns:
        Dict com estatísticas de uso do pool
    """
    pool = get_global_connection_pool()
    return pool.get_stats()