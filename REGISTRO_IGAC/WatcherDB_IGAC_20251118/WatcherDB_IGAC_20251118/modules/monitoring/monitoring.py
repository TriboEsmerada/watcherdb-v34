"""
TapOS SQL Server Monitoring Module
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
    connection_timeout: int = 30
    command_timeout: int = 300  # 5 minutos para queries longas
    
    def get_connection_string(self) -> str:
        """Gera connection string pyodbc"""
        server_full = f"{self.server}\\{self.instance}" if self.instance != "DEFAULT" else self.server
        
        if self.use_windows_auth:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE={self.database};"
                f"Trusted_Connection=yes;"
                f"Connection Timeout={self.connection_timeout};"
            )
        else:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"Connection Timeout={self.connection_timeout};"
            )
        
        return conn_str

class ConnectionPool:
    """
    Connection pool manual para SQL Server
    Gerencia conexões de forma eficiente com retry e otimizações de performance
    """
    
    def __init__(self, max_connections: int = 30, connection_lifetime: int = 3600, max_retries: int = 3, retry_delay: float = 0.1):
        self.max_connections = max_connections
        self.connection_lifetime = connection_lifetime  # 1 hora
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.pools: Dict[str, List[Tuple[pyodbc.Connection, float]]] = defaultdict(list)
        self.active_connections: Dict[str, int] = defaultdict(int)  # Rastrear conexões em uso
        self.locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'connection_errors': 0,
            'queries_executed': 0,
            'retries': 0,
            'pool_hits': 0,
            'pool_misses': 0
        }
        
        # Cleanup task
        self._cleanup_running = True
        threading.Thread(target=self._cleanup_old_connections, daemon=True).start()
        
        logger.info(f"ConnectionPool initialized: max={max_connections}, lifetime={connection_lifetime}s, retries={max_retries}")
    
    def get_connection(self, conn_info: ConnectionInfo, retry_count: int = 0) -> Optional[pyodbc.Connection]:
        """
        Obtém conexão do pool ou cria nova
        Implementa retry com backoff exponencial quando pool está cheio
        """
        pool_key = f"{conn_info.server}_{conn_info.instance}_{conn_info.database}"
        
        with self.locks[pool_key]:
            # Tentar reutilizar conexão existente
            while self.pools[pool_key]:
                conn, created_at = self.pools[pool_key].pop(0)
                
                # Verificar se conexão ainda é válida
                try:
                    if time.time() - created_at < self.connection_lifetime:
                        # Testar conexão rapidamente
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        cursor.close()
                        
                        self.stats['active_connections'] += 1
                        self.stats['pool_hits'] += 1
                        self.active_connections[pool_key] += 1
                        logger.debug(f"Reusing connection to {pool_key} (active: {self.active_connections[pool_key]})")
                        return conn
                    else:
                        # Conexão expirada
                        conn.close()
                        logger.debug(f"Connection expired: {pool_key}")
                except Exception as e:
                    logger.debug(f"Connection test failed: {e}")
                    try:
                        conn.close()
                    except:
                        pass
            
            # Verificar se podemos criar nova conexão (não exceder limite)
            current_active = self.active_connections[pool_key]
            pooled_count = len(self.pools[pool_key])
            total_in_use = current_active + pooled_count
            
            if total_in_use >= self.max_connections:
                # Pool cheio - tentar retry com backoff
                if retry_count < self.max_retries:
                    self.stats['retries'] += 1
                    delay = self.retry_delay * (2 ** retry_count)  # Backoff exponencial
                    logger.debug(f"Pool full for {pool_key}, will retry in {delay}s (attempt {retry_count + 1}/{self.max_retries})")
                    
                    # Liberar lock, esperar, e tentar novamente
                    # Nota: Outras threads podem usar conexões enquanto esperamos
                    self.locks[pool_key].release()
                    try:
                        time.sleep(delay)
                    finally:
                        self.locks[pool_key].acquire()
                    
                    # Tentar novamente (pode haver conexão disponível agora)
                    return self.get_connection(conn_info, retry_count + 1)
                else:
                    # Esgotou retries - tentar criar mesmo assim (pode ser conexão temporária)
                    # Isso permite que requisições urgentes não falhem completamente
                    logger.warning(f"Pool full for {pool_key} after {self.max_retries} retries, attempting direct connection (may exceed limit temporarily)")
            
            # Criar nova conexão
            try:
                conn_str = conn_info.get_connection_string()
                conn = pyodbc.connect(conn_str, timeout=conn_info.connection_timeout, autocommit=True)
                conn.timeout = conn_info.command_timeout
                
                self.stats['total_connections'] += 1
                self.stats['active_connections'] += 1
                self.stats['pool_misses'] += 1
                self.active_connections[pool_key] += 1
                
                logger.info(f"New connection created: {pool_key} (active: {self.active_connections[pool_key]})")
                return conn
                
            except Exception as e:
                self.stats['connection_errors'] += 1
                logger.error(f"Connection error to {pool_key}: {e}")
                return None
    
    def return_connection(self, conn_info: ConnectionInfo, conn: pyodbc.Connection):
        """Devolve conexão ao pool"""
        if conn is None:
            return
        
        pool_key = f"{conn_info.server}_{conn_info.instance}_{conn_info.database}"
        
        with self.locks[pool_key]:
            # Decrementar contador de conexões ativas
            if self.active_connections[pool_key] > 0:
                self.active_connections[pool_key] -= 1
            
            # Verificar se conexão ainda é válida antes de retornar ao pool
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                connection_valid = True
            except:
                connection_valid = False
                logger.debug(f"Connection invalid when returning to pool: {pool_key}")
            
            if connection_valid:
                # Limitar tamanho do pool
                pooled_count = len(self.pools[pool_key])
                if pooled_count < self.max_connections:
                    self.pools[pool_key].append((conn, time.time()))
                    self.stats['active_connections'] -= 1
                    logger.debug(f"Connection returned to pool: {pool_key} (pooled: {pooled_count + 1})")
                else:
                    # Pool cheio, fechar conexão
                    try:
                        conn.close()
                        self.stats['active_connections'] -= 1
                        logger.debug(f"Connection closed (pool full): {pool_key}")
                    except:
                        pass
            else:
                # Conexão inválida, fechar
                try:
                    conn.close()
                    self.stats['active_connections'] -= 1
                    logger.debug(f"Connection closed (invalid): {pool_key}")
                except:
                    pass
    
    def _cleanup_old_connections(self):
        """Limpa conexões antigas do pool"""
        while self._cleanup_running:
            try:
                time.sleep(300)  # A cada 5 minutos
                
                for pool_key in list(self.pools.keys()):
                    with self.locks[pool_key]:
                        pool = self.pools[pool_key]
                        valid_connections = []
                        
                        for conn, created_at in pool:
                            if time.time() - created_at < self.connection_lifetime:
                                valid_connections.append((conn, created_at))
                            else:
                                try:
                                    conn.close()
                                    logger.debug(f"Cleanup: closed expired connection to {pool_key}")
                                except:
                                    pass
                        
                        self.pools[pool_key] = valid_connections
                
                logger.debug(f"Connection pool cleanup completed")
                
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Estatísticas do pool"""
        total_pooled = sum(len(pool) for pool in self.pools.values())
        total_active = sum(self.active_connections.values())
        
        # Calcular taxa de hit do pool
        total_requests = self.stats['pool_hits'] + self.stats['pool_misses']
        hit_rate = (self.stats['pool_hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_connections_created': self.stats['total_connections'],
            'active_connections': total_active,
            'pooled_connections': total_pooled,
            'connection_errors': self.stats['connection_errors'],
            'queries_executed': self.stats['queries_executed'],
            'retries': self.stats['retries'],
            'pool_hits': self.stats['pool_hits'],
            'pool_misses': self.stats['pool_misses'],
            'pool_hit_rate': f"{hit_rate:.1f}%",
            'pool_keys': list(self.pools.keys()),
            'active_by_pool': dict(self.active_connections)
        }
    
    def close_all(self):
        """Fecha todas as conexões"""
        self._cleanup_running = False
        
        for pool_key, pool in self.pools.items():
            for conn, _ in pool:
                try:
                    conn.close()
                except:
                    pass
        
        self.pools.clear()
        logger.info("All connections closed")

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
            return None
    
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
            
            if timeout:
                cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000};")  # Converter para ms
            
            cursor.execute(query)
            
            # Processar resultados
            results = []
            
            if cursor.description:  # Query retorna dados
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
            
            conn.commit()
            cursor.close()
            
            execution_time = time.time() - start_time
            logger.info(f"Query executed successfully in {execution_time:.2f}s, returned {len(results)} rows")
            
            return results
            
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            return None
            
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
            connection_timeout=30,
            command_timeout=300
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
        """Load servers from config/sql_servers.json"""
        try:
            import json
            config_file = 'config/sql_servers.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                servers = config.get('servers', [])
                logger.info(f'📋 Loaded {len(servers)} servers from {config_file}')
                # Log alguns exemplos de IDs para debug
                if servers:
                    sample_ids = [s.get('id', s.get('server_id', 'N/A')) for s in servers[:5]]
                    logger.debug(f'   Sample server IDs: {sample_ids}')
                return servers
            else:
                logger.warning(f'⚠️ Config file not found: {config_file}')
            return []
        except Exception as e:
            logger.error(f'❌ Error loading servers config: {e}', exc_info=True)
            return []

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
            
            conn_info = ConnectionInfo(
                server=config_host,
                instance=instance_for_conn if instance_for_conn else "DEFAULT",  # ConnectionInfo espera "DEFAULT" como string
                database=database or 'master',
                use_windows_auth=True,
                connection_timeout=30,
                command_timeout=300
            )
            
            logger.info(f"🔌 Conectando a: {config_host}\\{instance_for_conn if instance_for_conn else 'DEFAULT'} (database: {database or 'master'})")
            
            # Executar usando o executor (que usa o pool de conexões)
            result = await self.executor.execute_query(conn_info, query, timeout=300)
            
            if result is None:
                return {'success': False, 'error': 'Query execution failed', 'rows': []}
            
            # Extrair colunas do primeiro resultado se disponível
            columns = []
            if result and len(result) > 0:
                columns = list(result[0].keys())
            
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