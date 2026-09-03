#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WatcherDB Always On Check Module
Verificação completa de Always On Availability Groups
"""

import pyodbc
import pandas as pd
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter
import statistics
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo, get_global_connection_pool

logger = logging.getLogger(__name__)

@dataclass
class AGReplica:
    """Informações de uma réplica do Availability Group"""
    server_name: str
    role: str
    operational_state: str
    connected_state: str
    synchronization_health: str
    availability_mode: str
    failover_mode: str
    session_timeout: int
    is_current_primary: bool = False
    is_local: bool = False

@dataclass
class AGDatabase:
    """Informações de uma base no AG"""
    database_name: str
    replica_server_name: str
    synchronization_state: str
    synchronization_health: str
    database_state: str
    is_suspended: bool
    suspend_reason: Optional[str] = None
    log_send_queue_size: Optional[int] = None
    redo_queue_size: Optional[int] = None
    is_local: bool = False

@dataclass
class AGFailoverEvent:
    """Evento de failover detectado"""
    timestamp: datetime
    event_type: str
    source_server: str
    description: str
    severity: str  # CRITICAL, ERROR, WARNING, INFO

@dataclass
class AGPattern:
    """Padrão detectado nos eventos"""
    pattern_type: str  # DAILY, WEEKLY, IRREGULAR
    frequency: int
    common_hour: Optional[int] = None
    common_day_of_week: Optional[int] = None
    likely_cause: str = ""
    confidence: float = 0.0

class AlwaysOnChecker:
    """Verificador de Always On Availability Groups"""

    def __init__(self, config_path: str = "config/alwayson_inventory.json", use_global_pool: bool = True):
        """
        Inicializa o verificador

        Args:
            config_path: Caminho para o arquivo de configuração JSON
            use_global_pool: Se True, usa pool global compartilhado (recomendado)
        """
        self.config = self._load_config(config_path)

        # Usar pool global por padrão (reduz consumo de conexões)
        if use_global_pool:
            self.connection_pool = get_global_connection_pool()
            logger.debug("AlwaysOnChecker usando pool global compartilhado")
        else:
            self.connection_pool = ConnectionPool(max_connections=15)
            logger.debug("AlwaysOnChecker usando pool dedicado")

        self.ag_servers = []
        self._load_ag_servers()

        # Carregar configuração de servidores (port, auth) do servers.json
        self._servers_config: Dict[str, Dict] = {}
        self._load_servers_config()

        # Cache local para status de servidores lentos (TTL: 5 minutos)
        self._status_cache: Dict[str, Tuple[Dict, float]] = {}
        self._cache_ttl = 300  # 5 minutos

        # ThreadPoolExecutor para queries com timeout
        self._executor = ThreadPoolExecutor(max_workers=3)
        
    def _load_config(self, config_path: str) -> Dict:
        """Carrega configuração do Always On"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar config Always On: {e}")
            return {
                "excel_path": "C:\\Server_Inventory\\TAP_SQL_Server_Inventory.xlsx",
                "sheet_name": "Servers",
                "cache_ttl_seconds": 300,
                "analysis_window_days": 30
            }
    
    def _load_servers_config(self):
        """Carrega config de servidores (port, auth) do servers.json para lookup rápido"""
        try:
            servers_path = Path('config/servers.json')
            if not servers_path.exists():
                logger.debug("servers.json não encontrado — usando Windows Auth para todos os servidores")
                return
            with open(servers_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            servers = data.get('monitored_servers', data.get('servers', []))
            for s in servers:
                sid = (s.get('id') or '').upper()
                host = (s.get('host') or '').upper()
                inst = (s.get('instance') or '').upper()
                if sid:
                    self._servers_config[sid] = s
                if host and inst:
                    self._servers_config[f"{host}_{inst}"] = s
                elif host:
                    self._servers_config[host] = s
            logger.info(f"Carregadas {len(servers)} configs de servidores para AlwaysOn (lookup: {len(self._servers_config)} entradas)")
        except Exception as e:
            logger.warning(f"Erro ao carregar servers.json para AlwaysOn: {e}")

    @staticmethod
    def _decrypt_password(encrypted_pwd: str) -> str:
        """Desencripta password com prefixo 'encrypted:'.

        FASE 1 least-priv (2026-08-21): usa a MESMA cadeia de resolucao de chave
        que o connection_pool (services.secrets.try_get_master_key): ficheiro DPAPI
        machine-scope (Tier 3, o preferido no servico packaged) -> env DPAPI
        user-scope (Tier 2) -> WATCHERDB_ENCRYPTION_KEY plain (Tier 1). Antes so'
        tentava o Tier 1 plain e, no servico packaged (que usa o DPAPI machine-
        scope), devolvia o CIPHERTEXT cru como PWD= -> os checks AlwaysOn falhavam
        em silencio com 18456.
        """
        if not isinstance(encrypted_pwd, str):
            return encrypted_pwd or ''
        if not encrypted_pwd.startswith('encrypted:'):
            return encrypted_pwd
        token = encrypted_pwd[len('encrypted:'):]
        try:
            from cryptography.fernet import Fernet
            key = None
            try:
                from services.secrets import try_get_master_key
                key = try_get_master_key()  # Tier 3 -> 2 -> 1
            except Exception:
                key = None
            if not key:
                import os
                env_key = os.environ.get('WATCHERDB_ENCRYPTION_KEY', '')
                key = env_key.encode() if env_key else None
            if key:
                return Fernet(key).decrypt(token.encode()).decode()
        except Exception as e:
            logger.warning(f"Falha ao desencriptar password AlwaysOn: {e}")
        logger.warning("Sem chave de desencriptacao valida — password AlwaysOn nao desencriptada")
        return token

    def _get_connection_info(self, server: str, instance: str = "", database: str = "master",
                             connection_timeout: int = 15, command_timeout: int = 300) -> ConnectionInfo:
        """Cria ConnectionInfo usando configuração do servers.json (port, auth)"""
        # Lookup no servers.json
        lookup_key = f"{server.upper()}_{instance.upper()}" if instance else server.upper()
        srv_cfg = self._servers_config.get(lookup_key, {})

        use_win_auth = srv_cfg.get('use_windows_auth', True)
        username = None
        password = None
        port = srv_cfg.get('port', None)

        if not use_win_auth:
            username = srv_cfg.get('username', '')
            raw_pwd = srv_cfg.get('password', '')
            password = self._decrypt_password(raw_pwd)

        return ConnectionInfo(
            server=server,
            instance=instance if instance else "DEFAULT",
            database=database,
            use_windows_auth=use_win_auth,
            username=username,
            password=password,
            connection_timeout=connection_timeout,
            command_timeout=command_timeout,
            port=port
        )

    def _load_ag_servers(self):
        """Carrega lista de servidores com Always On (prioriza JSON, fallback para Excel)"""
        # 1. Tentar carregar do JSON primeiro (mais rápido)
        ag_servers_from_json = self.config.get('ag_servers', [])
        if ag_servers_from_json:
            self.ag_servers = ag_servers_from_json
            logger.info(f"Carregados {len(self.ag_servers)} servidores Always On do JSON")
            return
        
        # 2. Se não existir no JSON, carregar do Excel (compatibilidade retroativa)
        logger.info("⚠️  ag_servers não encontrado no JSON, carregando do Excel...")
        logger.info("💡 Execute scripts/initialize_configs.py para popular o JSON e melhorar performance")
        self._load_ag_servers_from_excel()
    
    def _load_ag_servers_from_excel(self):
        """Carrega lista de servidores com Always On do Excel (fallback)"""
        try:
            excel_path = self.config.get('excel_path', '').replace('\\\\', '\\')
            sheet_name = self.config.get('sheet_name', 'Servers')
            columns = self.config.get('columns', {})
            
            if not excel_path or not Path(excel_path).exists():
                logger.warning(f"Excel não encontrado: {excel_path}")
                return
            
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            
            # Detectar colunas automaticamente
            server_col = columns.get('server', 'ServerName')
            instance_col = columns.get('instance', 'Instance')
            server_instance_col = columns.get('server_instance', 'ServerInstance')
            ag_name_col = columns.get('ag_name', 'AGName')
            listener_col = columns.get('listener', 'AGListener')
            
            # Auto-detectar colunas se não existirem pelos nomes esperados
            if server_instance_col not in df.columns:
                for col in df.columns:
                    col_upper = str(col).upper().replace(' ', '').replace('_', '')
                    if 'SERVERINSTANCE' in col_upper:
                        server_instance_col = col
                        break
            
            if ag_name_col not in df.columns:
                for col in df.columns:
                    col_upper = str(col).upper().replace(' ', '').replace('_', '')
                    if 'AGNAME' in col_upper or ('AG' in col_upper and 'NAME' in col_upper) or col_upper == 'AG_NAME':
                        ag_name_col = col
                        break
            
            if listener_col not in df.columns:
                for col in df.columns:
                    col_upper = str(col).upper().replace(' ', '').replace('_', '')
                    if 'LISTENER' in col_upper or ('AG' in col_upper and 'LISTENER' in col_upper) or col_upper == 'LISTENERS':
                        listener_col = col
                        break
            
            # Filtrar servidores Always On: linhas onde AG_NAME e Listeners estão preenchidos
            if ag_name_col in df.columns and listener_col in df.columns:
                ag_df = df[df[ag_name_col].notna() & (df[ag_name_col] != '') & 
                          df[listener_col].notna() & (df[listener_col] != '')]
                
                for _, row in ag_df.iterrows():
                    ag_name = str(row.get(ag_name_col, '')) if pd.notna(row.get(ag_name_col)) else ''
                    listener = str(row.get(listener_col, '')) if pd.notna(row.get(listener_col)) else ''
                    
                    # Priorizar ServerInstance se disponível (formato: SQLMDMPRD01\101)
                    server_instance_raw = ''
                    server = ''
                    instance = ''
                    
                    if server_instance_col and server_instance_col in df.columns:
                        server_instance_raw = str(row.get(server_instance_col, '')) if pd.notna(row.get(server_instance_col)) else ''
                        if server_instance_raw and '\\' in server_instance_raw:
                            # Extrair server e instance de ServerInstance
                            parts = server_instance_raw.split('\\', 1)
                            server = parts[0].strip()
                            instance = parts[1].strip() if len(parts) > 1 else ''
                        elif server_instance_raw and '_' in server_instance_raw:
                            # Formato alternativo: SQLMDMPRD01_101
                            parts = server_instance_raw.rsplit('_', 1)
                            server = parts[0].strip()
                            instance = parts[1].strip() if len(parts) > 1 else ''
                    
                    # Se não encontrou ServerInstance, usar server e instance separados
                    if not server:
                        server = str(row.get(server_col, ''))
                        instance = str(row.get(instance_col, '')) if pd.notna(row.get(instance_col)) else ''
                    
                    if server:
                        self.ag_servers.append({
                            'server': server,
                            'instance': instance,
                            'server_instance': server_instance_raw,  # Guardar o ServerInstance original
                            'ag_name': ag_name,
                            'listener': listener
                        })
                
                logger.info(f"Carregados {len(self.ag_servers)} servidores com Always On do Excel")
            
        except Exception as e:
            logger.error(f"Erro ao carregar servidores Always On do Excel: {e}")
    
    def _get_ag_status_with_timeout(self, server: str, instance: str, timeout: int = 45) -> Optional[Dict]:
        """
        Executa get_ag_status com timeout

        Args:
            server: Nome do servidor
            instance: Instância
            timeout: Timeout em segundos (padrão: 45s)

        Returns:
            Dict com status ou None se timeout/erro
        """
        try:
            future = self._executor.submit(self._get_ag_status_internal, server, instance)
            result = future.result(timeout=timeout)
            return result
        except FutureTimeoutError:
            logger.warning(f"Timeout ao obter status AG de {server} (>{timeout}s)")
            return {
                'success': False,
                'error': f'Timeout após {timeout}s',
                'server': server,
                'instance': instance,
                'timeout': True
            }
        except Exception as e:
            logger.error(f"Erro ao obter status AG de {server}: {e}")
            return {
                'success': False,
                'error': str(e),
                'server': server,
                'instance': instance
            }

    def get_ag_status(self, server: str, instance: str = "") -> Optional[Dict]:
        """
        Obtém status completo do AG de um servidor (com cache e timeout)

        Returns:
            Dict com status do AG ou None/erro
        """
        cache_key = f"{server}_{instance}"

        # Verificar cache (TTL: 5 minutos para servidores lentos)
        if cache_key in self._status_cache:
            cached_data, cached_time = self._status_cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                logger.debug(f"Cache hit para {server} (idade: {time.time() - cached_time:.0f}s)")
                return cached_data

        # Buscar com timeout (20s - falha rápida para melhor UX)
        result = self._get_ag_status_with_timeout(server, instance, timeout=20)

        # Cachear resultado (mesmo se for erro/timeout, para não ficar tentando repetidamente)
        if result:
            self._status_cache[cache_key] = (result, time.time())

        return result

    def _get_ag_status_internal(self, server: str, instance: str = "") -> Optional[Dict]:
        """Implementação interna do get_ag_status (executada com timeout)"""
        try:
            conn_info = self._get_connection_info(
                server=server,
                instance=instance,
                connection_timeout=15
            )

            conn = self.connection_pool.get_connection(conn_info)
            if not conn:
                logger.warning(f"Não foi possível conectar em {server}")
                return {
                    'success': False,
                    'error': 'Conexão falhou',
                    'server': server,
                    'instance': instance
                }

            cursor = conn.cursor()

            # Query para identificar o nó primário (funciona em qualquer réplica)
            # 2026-07-17: dm_hadr_availability_group_states.primary_replica vem dos
            # metadados do cluster WSFC e responde igual em PRIMARY ou SECONDARY.
            # A query anterior (role_desc='PRIMARY' em dm_hadr_availability_replica_states)
            # devolvia 0 rows quando executada numa SECUNDARIA — essa DMV só conhece
            # o estado da réplica local. Era a raiz de o banner "Nó Primário" nunca
            # aparecer nas secundárias. Mesmo padrão do módulo Backup (backup_analysis.py).
            primary_query = """
            SELECT
                ag.name as ag_name,
                ags.primary_replica
            FROM sys.availability_groups ag
            INNER JOIN sys.dm_hadr_availability_group_states ags ON ag.group_id = ags.group_id
            """
            cursor.execute(primary_query)
            primary_row = cursor.fetchone()
            discovered_primary = primary_row[1] if primary_row else None
            if not discovered_primary:
                # Fallback: método antigo (resolve quando executado na primária)
                cursor.execute("""
                SELECT ar.replica_server_name
                FROM sys.availability_replicas ar
                INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
                WHERE ars.role_desc = 'PRIMARY'
                """)
                fb_row = cursor.fetchone()
                discovered_primary = fb_row[0] if fb_row else None
            logger.debug(f"Nó primário descoberto: {discovered_primary}")

            # Query para status do AG
            ag_status_query = """
            SELECT 
                ag.name as ag_name,
                ar.replica_server_name,
                ars.role_desc as current_role,
                ars.operational_state_desc,
                ars.connected_state_desc,
                ars.synchronization_health_desc as replica_health,
                ar.availability_mode_desc,
                ar.failover_mode_desc,
                ar.session_timeout,
                CASE WHEN ars.role_desc = 'PRIMARY' THEN 1 ELSE 0 END as is_primary,
                ars.is_local as is_local
            FROM sys.availability_groups ag
            INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
            INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
            ORDER BY ag.name, ar.replica_server_name
            """

            cursor.execute(ag_status_query)
            rows = cursor.fetchall()
            
            logger.debug(f"Query de réplicas retornou {len(rows)} linhas para {server}\\{instance}")
            
            if not rows:
                # Diagnóstico adicional para diferenciar permissão vs AG inexistente
                hadr_enabled = None
                has_vss = None
                try:
                    cursor.execute(
                        "SELECT CAST(SERVERPROPERTY('IsHadrEnabled') AS INT) AS IsHadrEnabled, "
                        "HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE') AS HasViewServerState"
                    )
                    diag_row = cursor.fetchone()
                    if diag_row:
                        hadr_enabled = diag_row[0]
                        has_vss = diag_row[1]
                except Exception:
                    pass

                if has_vss == 0:
                    error_msg = 'Conta de monitoramento sem permissão VIEW SERVER STATE — necessário para consultar sys.dm_hadr_availability_replica_states'
                elif hadr_enabled == 0:
                    error_msg = 'AlwaysOn não está ativado neste servidor (IsHadrEnabled=0)'
                else:
                    error_msg = 'Réplica AlwaysOn não encontrada neste servidor — possivelmente desativada, desconectada do AG, ou sem permissão VIEW SERVER STATE'

                logger.warning(
                    f"Nenhuma réplica encontrada para {server}\\{instance} — "
                    f"IsHadrEnabled={hadr_enabled}, HasViewServerState={has_vss}"
                )
                return {
                    'success': False,
                    'error': error_msg,
                    'server': server,
                    'instance': instance,
                    'no_dmv_data': True,
                    'hadr_enabled': hadr_enabled,
                    'has_view_server_state': has_vss
                }
            
            # Processar réplicas
            replicas = []
            ag_name = None
            current_primary = discovered_primary  # Usar o primário descoberto pela query inicial

            for row in rows:
                if not ag_name:
                    ag_name = row[0]
            
            # Query para buscar o listener do AG
            listener_query = """
            SELECT
                ag.name AS AG_Name,
                agl.dns_name AS ListenerName,
                agl.port AS ListenerPort
            FROM sys.availability_groups ag
            LEFT JOIN sys.availability_group_listeners agl
                ON ag.group_id = agl.group_id
            WHERE ag.name = ?
            """
            
            listener_name = None
            listener_port = None
            try:
                cursor.execute(listener_query, ag_name)
                listener_row = cursor.fetchone()
                if listener_row:
                    listener_name = listener_row[1] if listener_row[1] else None
                    listener_port = listener_row[2] if listener_row[2] else None
                    if listener_name and listener_port:
                        listener_name = f"{listener_name}:{listener_port}"
                    elif listener_name:
                        listener_name = listener_name
                    logger.debug(f"Listener encontrado para AG {ag_name}: {listener_name}")
                else:
                    logger.debug(f"Nenhum listener encontrado para AG {ag_name}")
            except Exception as listener_err:
                logger.warning(f"Erro ao buscar listener para AG {ag_name}: {listener_err}")
            
            # Reprocessar rows para criar réplicas
            for row in rows:
                
                replica = AGReplica(
                    server_name=row[1],
                    role=row[2],
                    operational_state=row[3],
                    connected_state=row[4],
                    synchronization_health=row[5],
                    availability_mode=row[6],
                    failover_mode=row[7],
                    session_timeout=row[8],
                    is_current_primary=bool(row[9]),
                    is_local=bool(row[10]) if len(row) > 10 else False
                )
                
                replicas.append(replica)
                if replica.is_current_primary:
                    current_primary = replica.server_name
            
            # Query para bases de dados
            # NOTA: Quando executada no PRIMARY, a DMV dm_hadr_database_replica_states
            # retorna NULL para database_state_desc e redo_queue_size das réplicas remotas (is_local=0).
            # Usamos ISNULL/CASE para inferir valores quando possível.
            db_status_query = """
            SELECT
                db.name as database_name,
                ar.replica_server_name,
                drs.synchronization_state_desc,
                drs.synchronization_health_desc as db_health,
                CASE
                    WHEN drs.database_state_desc IS NOT NULL THEN drs.database_state_desc
                    WHEN drs.is_local = 0 AND drs.synchronization_state_desc = 'SYNCHRONIZED' THEN 'ONLINE'
                    WHEN drs.is_local = 0 AND drs.synchronization_state_desc = 'SYNCHRONIZING' THEN 'ONLINE'
                    WHEN drs.is_local = 0 AND drs.synchronization_state_desc = 'NOT SYNCHRONIZING' THEN 'RECOVERING'
                    ELSE drs.database_state_desc
                END as database_state_desc,
                drs.is_suspended,
                drs.suspend_reason_desc,
                drs.log_send_queue_size,
                drs.redo_queue_size,
                drs.is_local
            FROM sys.availability_groups ag
            INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
            INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
            INNER JOIN sys.availability_databases_cluster adc ON ag.group_id = adc.group_id
            INNER JOIN sys.databases db ON adc.database_name = db.name
            INNER JOIN sys.dm_hadr_database_replica_states drs ON db.database_id = drs.database_id
                AND ar.replica_id = drs.replica_id
            WHERE ag.name = ?
            ORDER BY ar.replica_server_name, db.name
            """
            
            try:
                cursor.execute(db_status_query, ag_name)
                db_rows = cursor.fetchall()
            except pyodbc.Error as db_query_err:
                logger.error(f"Erro ao executar query de databases para AG {ag_name}: {db_query_err}")
                # Continuar mesmo se a query de databases falhar - pelo menos temos as réplicas
                db_rows = []
            
            logger.debug(f"Query de databases retornou {len(db_rows)} linhas para AG {ag_name}")
            
            databases = []
            for db_row in db_rows:
                try:
                    db = AGDatabase(
                        database_name=db_row[0],
                        replica_server_name=db_row[1],
                        synchronization_state=db_row[2],
                        synchronization_health=db_row[3],
                        database_state=db_row[4] if db_row[4] else None,
                        is_suspended=bool(db_row[5]),
                        suspend_reason=db_row[6] if db_row[6] else None,
                        log_send_queue_size=db_row[7] if db_row[7] else None,
                        redo_queue_size=db_row[8] if db_row[8] else None,
                        is_local=bool(db_row[9]) if len(db_row) > 9 else False
                    )
                    databases.append(db)
                except Exception as db_err:
                    logger.warning(f"Erro ao processar database row: {db_err}, row: {db_row}")
                    continue
            
            logger.info(f"Status AG obtido: {len(replicas)} réplicas, {len(databases)} databases para {server}\\{instance}")
            
            result = {
                'ag_name': ag_name,
                'listener': listener_name,
                'replicas': [asdict(r) for r in replicas],
                'databases': [asdict(d) for d in databases],
                'current_primary': current_primary,
                'total_replicas': len(replicas),
                'healthy_replicas': len([r for r in replicas if r.synchronization_health == 'HEALTHY']),
                'total_databases': len(databases),
                'healthy_databases': len([d for d in databases if d.synchronization_health == 'HEALTHY']),
                'synchronized_databases': len([d for d in databases if d.synchronization_state == 'SYNCHRONIZED'])
            }
            
            return result
            
        except pyodbc.Error as db_err:
            logger.error(f"Erro SQL ao obter status AG de {server}\\{instance}: {db_err}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
        except Exception as e:
            logger.error(f"Erro ao obter status AG de {server}\\{instance}: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
    
    def get_ag_failover_events(self, server: str, instance: str = "", days: int = 30) -> List[AGFailoverEvent]:
        """Obtém eventos de failover dos últimos N dias"""
        events = []

        try:
            conn_info = self._get_connection_info(
                server=server,
                instance=instance,
                connection_timeout=10,
                command_timeout=10
            )

            conn = self.connection_pool.get_connection(conn_info)
            if not conn:
                return events

            # Query para XEvents de Always On
            xevents_query = """
            SELECT TOP 50
                DATEADD(ms, -1 * (DATEDIFF(ms, GETDATE(), GETUTCDATE())), 
                        xel.event_data.value('(event/@timestamp)[1]', 'datetime2')) as event_time,
                xel.event_data.value('(event/@name)[1]', 'nvarchar(256)') as event_name,
                xel.event_data.value('(event/data[@name="previous_primary_replica"]/value)[1]', 'nvarchar(256)') as previous_primary,
                xel.event_data.value('(event/data[@name="new_primary_replica"]/value)[1]', 'nvarchar(256)') as new_primary,
                xel.event_data.value('(event/data[@name="previous_state"]/value)[1]', 'int') as previous_state,
                xel.event_data.value('(event/data[@name="current_state"]/value)[1]', 'int') as current_state
            FROM (
                SELECT CAST(event_data AS XML) as event_data
                FROM sys.fn_xe_file_target_read_file('AlwaysOn*.xel', NULL, NULL, NULL)
                WHERE event_data IS NOT NULL
            ) as xel
            WHERE xel.event_data.value('(event/@name)[1]', 'nvarchar(256)') IN 
                ('availability_replica_state_change', 'availability_group_lease_expired', 
                 'alwayson_ddl_executed', 'hadr_automatic_failover_validation')
              AND DATEADD(ms, -1 * (DATEDIFF(ms, GETDATE(), GETUTCDATE())), 
                          xel.event_data.value('(event/@timestamp)[1]', 'datetime2')) >= DATEADD(dd, -?, GETDATE())
            ORDER BY event_time DESC
            """
            
            cursor = conn.cursor()
            cursor.execute(xevents_query, days)
            rows = cursor.fetchall()
            
            for row in rows:
                event_time = row[0]
                event_name = row[1]
                previous_state = row[4]
                current_state = row[5]
                
                if event_name == 'availability_replica_state_change' and previous_state == 1 and current_state == 2:
                    event = AGFailoverEvent(
                        timestamp=event_time,
                        event_type='ROLE_CHANGE',
                        source_server=server,
                        description=f"Failover: {row[2]} → {row[3]}",
                        severity='CRITICAL'
                    )
                    events.append(event)
                elif event_name == 'availability_group_lease_expired':
                    event = AGFailoverEvent(
                        timestamp=event_time,
                        event_type='LEASE_TIMEOUT',
                        source_server=server,
                        description="Lease timeout expirado",
                        severity='CRITICAL'
                    )
                    events.append(event)
            
            # Query para SQL Error Log - busca múltiplos padrões em múltiplos arquivos
            # Event IDs relevantes e seus textos no Error Log:
            #   1480  → "is changing roles from" (AG database role change - CRÍTICO)
            #   19406 → "The state of the local availability replica" (AG replica state change)
            #   19407 → "availability group is now ready for failover" / "failover completed"
            #   41142 → "lease timeout" / "lease expired"
            #   41075 → "synchronization health changed"

            # Padrões de texto para busca (máxima cobertura)
            # 5 padrões × 2 ficheiros de log = 10 chamadas xp_readerrorlog
            # (ficheiro 2 raramente contém eventos dentro do período solicitado)
            search_patterns = [
                ('changing roles', None),          # Event 1480 - role change (CRÍTICO)
                ('The state of the local availability replica', None),  # Event 19406
                ('failover', None),                # Generic failover events
                ('lease expired', None),           # Event 41142 - lease timeout
                ('is not functioning correctly', None),  # AG health issues
            ]

            errorlog_query = f"""
            SET LOCK_TIMEOUT 15000;
            CREATE TABLE #ErrorLog (LogDate DATETIME, ProcessInfo VARCHAR(50), LogText VARCHAR(MAX))

            DECLARE @StartDate DATETIME = DATEADD(DAY, -{days}, GETDATE())

            -- Buscar em 2 ficheiros de log (0=atual, 1=anterior)
            """

            for pattern1, pattern2 in search_patterns:
                p2_param = f"'{pattern2}'" if pattern2 else "NULL"
                for log_file in range(2):  # Ficheiros 0, 1 (reduzido de 3 para 2)
                    errorlog_query += f"""
            BEGIN TRY
                INSERT INTO #ErrorLog
                EXEC xp_readerrorlog {log_file}, 1, '{pattern1}', {p2_param}, @StartDate, NULL
            END TRY
            BEGIN CATCH
            END CATCH
"""

            errorlog_query += f"""
            SELECT LogDate, LogText
            FROM #ErrorLog
            WHERE LogText IS NOT NULL
              AND LEN(LogText) > 10
            ORDER BY LogDate DESC

            DROP TABLE #ErrorLog
            """

            try:
                cursor.execute(errorlog_query)
                log_rows = cursor.fetchall()

                # Deduplicar por timestamp + texto (múltiplos padrões podem encontrar o mesmo evento)
                seen_events = set()

                for log_row in log_rows:
                    log_date = log_row[0]
                    log_text_original = log_row[1][:500]
                    log_text = log_text_original.lower()

                    # Chave de deduplicação: timestamp + primeiros 100 chars
                    dedup_key = (str(log_date), log_text[:100])
                    if dedup_key in seen_events:
                        continue
                    seen_events.add(dedup_key)

                    event_type = 'INFO'
                    severity = 'INFO'

                    # Event 1480 - AG database changing roles (CRÍTICO - indica failover real)
                    if 'changing roles' in log_text:
                        event_type = 'ROLE_CHANGE'
                        severity = 'CRITICAL'
                    # Event 19406 - AG replica state change
                    elif 'the state of the local availability replica' in log_text:
                        if 'primary' in log_text:
                            event_type = 'ROLE_CHANGE'
                            severity = 'CRITICAL'
                        else:
                            event_type = 'STATE_CHANGE'
                            severity = 'WARNING'
                    # Lease timeout / expired
                    elif 'lease expired' in log_text or 'lease timeout' in log_text:
                        event_type = 'LEASE_TIMEOUT'
                        severity = 'CRITICAL'
                    # AG health issues
                    elif 'is not functioning correctly' in log_text:
                        event_type = 'HEALTH_ISSUE'
                        severity = 'ERROR'
                    # Generic failover
                    elif 'failover' in log_text:
                        if 'automatic failover' in log_text or 'failover completed' in log_text:
                            event_type = 'FAILOVER'
                            severity = 'CRITICAL'
                        else:
                            event_type = 'FAILOVER'
                            severity = 'ERROR'

                    event = AGFailoverEvent(
                        timestamp=log_date,
                        event_type=event_type,
                        source_server=server,
                        description=log_text_original[:200],
                        severity=severity
                    )
                    events.append(event)

                logger.info(f"Always On failover: encontrados {len(events)} eventos para {server} (Error Log: {len(seen_events)} únicos)")
            except Exception as e:
                logger.debug(f"Erro ao ler error log: {e}")
            
        except Exception as e:
            logger.error(f"Erro ao obter eventos de failover de {server}: {e}")
        
        return events

    def get_last_failover_date(self, server: str, instance: str = "") -> str:
        """Obtém a data/hora do último failover (sem limite de dias). Pesquisa 3 fontes:
        1. AlwaysOn XEvents (.xel) - sem filtro de data
        2. SQL Server Error Log (type 1) - 4 ficheiros
        3. Windows Application Event Log (type 2) - retenção maior
        Retorna ISO string ou None."""
        try:
            conn_info = self._get_connection_info(
                server=server,
                instance=instance,
                connection_timeout=5,
                command_timeout=5
            )
            conn = self.connection_pool.get_connection(conn_info)
            if not conn:
                return None

            cursor = conn.cursor()

            # FONTE 1: AlwaysOn XEvents (.xel) - sem filtro de data
            # Procura role changes (previous_state=1 PRIMARY -> current_state=2 SECONDARY ou vice-versa)
            try:
                xevents_query = """
                SELECT TOP 1
                    DATEADD(ms, -1 * (DATEDIFF(ms, GETDATE(), GETUTCDATE())),
                            xel.event_data.value('(event/@timestamp)[1]', 'datetime2')) as event_time
                FROM (
                    SELECT CAST(event_data AS XML) as event_data
                    FROM sys.fn_xe_file_target_read_file('AlwaysOn*.xel', NULL, NULL, NULL)
                    WHERE event_data IS NOT NULL
                ) as xel
                WHERE xel.event_data.value('(event/@name)[1]', 'nvarchar(256)')
                      IN ('availability_replica_state_change', 'hadr_automatic_failover_validation')
                ORDER BY event_time DESC
                """
                cursor.execute(xevents_query)
                row = cursor.fetchone()
                if row and row[0]:
                    logger.debug(f"Last failover de {server} encontrado via XEvents: {row[0]}")
                    return row[0].isoformat()
            except Exception as e:
                logger.debug(f"XEvents nao disponivel para {server}: {e}")

            # FONTE 2: SQL Error Log (type 1) - 6 ficheiros + Windows Event Log (type 2)
            try:
                query = """
                SET LOCK_TIMEOUT 10000;
                CREATE TABLE #LastFailover (LogDate DATETIME, ProcessInfo VARCHAR(50), LogText VARCHAR(MAX))

                -- SQL Server Error Log (type 1) - ficheiros 0 a 3
                BEGIN TRY INSERT INTO #LastFailover EXEC xp_readerrorlog 0, 1, 'changing roles', NULL END TRY BEGIN CATCH END CATCH
                BEGIN TRY INSERT INTO #LastFailover EXEC xp_readerrorlog 1, 1, 'changing roles', NULL END TRY BEGIN CATCH END CATCH
                BEGIN TRY INSERT INTO #LastFailover EXEC xp_readerrorlog 2, 1, 'changing roles', NULL END TRY BEGIN CATCH END CATCH
                BEGIN TRY INSERT INTO #LastFailover EXEC xp_readerrorlog 3, 1, 'changing roles', NULL END TRY BEGIN CATCH END CATCH

                -- Windows Application Event Log (type 2) - retencao muito maior
                BEGIN TRY INSERT INTO #LastFailover EXEC xp_readerrorlog 0, 2, 'failover', NULL END TRY BEGIN CATCH END CATCH
                BEGIN TRY INSERT INTO #LastFailover EXEC xp_readerrorlog 0, 2, 'changing roles', NULL END TRY BEGIN CATCH END CATCH

                SELECT TOP 1 LogDate FROM #LastFailover WHERE LogText IS NOT NULL ORDER BY LogDate DESC
                DROP TABLE #LastFailover
                """
                cursor.execute(query)
                row = cursor.fetchone()
                if row and row[0]:
                    source = "Error Log / Windows Event Log"
                    logger.debug(f"Last failover de {server} encontrado via {source}: {row[0]}")
                    return row[0].isoformat()
            except Exception as e:
                logger.debug(f"Error Log nao disponivel para {server}: {e}")

            return None
        except Exception as e:
            logger.debug(f"Erro ao obter last_failover_date de {server}: {e}")
            return None

    def analyze_failover_patterns(self, events: List[AGFailoverEvent]) -> List[AGPattern]:
        """Analisa padrões temporais nos eventos de failover"""
        patterns = []
        
        if len(events) < 2:
            return patterns
        
        # Agrupar por tipo
        by_type = defaultdict(list)
        for event in events:
            by_type[event.event_type].append(event)
        
        # Analisar padrões horários
        for event_type, type_events in by_type.items():
            if len(type_events) >= 2:
                hourly_data = [e.timestamp.hour for e in type_events]
                hour_counter = Counter(hourly_data)
                
                for hour, count in hour_counter.most_common(3):
                    if count >= 2:
                        confidence = min(0.9, (count / len(type_events)) * 2)
                        
                        likely_cause = "Processo automático"
                        if 1 <= hour <= 5:
                            likely_cause = "Backup automático ou manutenção programada"
                        elif 6 <= hour <= 8:
                            likely_cause = "Patches automáticos do Windows/SQL Server"
                        elif 9 <= hour <= 17:
                            likely_cause = "Manutenção durante horário comercial"
                        elif 18 <= hour <= 23:
                            likely_cause = "Processo de fim de dia"
                        
                        pattern = AGPattern(
                            pattern_type='DAILY',
                            frequency=count,
                            common_hour=hour,
                            likely_cause=likely_cause,
                            confidence=confidence
                        )
                        patterns.append(pattern)
        
        # Analisar padrões semanais
        for event_type, type_events in by_type.items():
            if len(type_events) >= 2:
                daily_data = [e.timestamp.weekday() for e in type_events]
                day_counter = Counter(daily_data)
                
                for day, count in day_counter.most_common(3):
                    if count >= 2:
                        confidence = min(0.8, (count / len(type_events)) * 1.5)
                        
                        day_names = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
                        likely_cause = f"Manutenção {day_names[day]}"
                        if day == 1:
                            likely_cause = "Patch Tuesday - atualizações da Microsoft"
                        
                        pattern = AGPattern(
                            pattern_type='WEEKLY',
                            frequency=count,
                            common_day_of_week=day,
                            likely_cause=likely_cause,
                            confidence=confidence
                        )
                        patterns.append(pattern)
        
        return patterns

    def diagnose_ag_issues(self, server: str, instance: str = "") -> Dict:
        """
        Diagnostica problemas do Always On e identifica causa raiz.

        Funciona tanto no primário quanto no secundário, adaptando as queries.
        Algumas informações só estão disponíveis no primário.

        Args:
            server: Nome do servidor
            instance: Instância SQL Server

        Returns:
            Dict com diagnóstico completo
        """
        diagnosis = {
            'server': server,
            'instance': instance,
            'timestamp': datetime.now().isoformat(),
            'is_primary': False,
            'current_role': 'UNKNOWN',
            'connection_issues': [],
            'endpoint_status': None,
            'replica_states': [],
            'error_log_entries': [],
            'recommendations': [],
            'root_cause': None,
            'root_cause_category': None,
            'severity': 'INFO'
        }

        try:
            conn_info = self._get_connection_info(
                server=server,
                instance=instance,
                connection_timeout=15
            )

            conn = self.connection_pool.get_connection(conn_info)
            if not conn:
                diagnosis['root_cause'] = 'Não foi possível conectar ao servidor SQL'
                diagnosis['root_cause_category'] = 'CONNECTION'
                diagnosis['severity'] = 'CRITICAL'
                diagnosis['recommendations'].append({
                    'action': 'Verificar se o serviço SQL Server está em execução',
                    'priority': 'HIGH'
                })
                return diagnosis

            cursor = conn.cursor()
            logger.info(f"🔍 [Diagnose] Conectado a {server}\\{instance or 'DEFAULT'}")

            # 1. Verificar role atual (funciona em qualquer nó)
            role_query = """
            SELECT
                ars.role_desc,
                ars.operational_state_desc,
                ars.connected_state_desc,
                ars.synchronization_health_desc,
                ars.last_connect_error_number,
                ars.last_connect_error_description,
                ars.last_connect_error_timestamp
            FROM sys.dm_hadr_availability_replica_states ars
            WHERE ars.is_local = 1
            """
            cursor.execute(role_query)
            local_replica = cursor.fetchone()

            if local_replica:
                diagnosis['current_role'] = local_replica[0] or 'UNKNOWN'
                diagnosis['is_primary'] = diagnosis['current_role'] == 'PRIMARY'
                diagnosis['operational_state'] = local_replica[1]
                diagnosis['connected_state'] = local_replica[2]
                diagnosis['local_sync_health'] = local_replica[3]
                logger.info(f"🔍 [Diagnose] Role: {diagnosis['current_role']}, Sync: {diagnosis['local_sync_health']}")

                # Verificar erro de conexão
                if local_replica[4] and local_replica[4] != 0:
                    diagnosis['connection_issues'].append({
                        'error_number': local_replica[4],
                        'error_description': local_replica[5] or 'Erro desconhecido',
                        'error_timestamp': local_replica[6].isoformat() if local_replica[6] else None,
                        'type': 'LAST_CONNECT_ERROR'
                    })

            # 2. Verificar status do endpoint de mirroring (funciona em qualquer nó)
            # Query compatível com todas as versões do SQL Server
            # Nota: A porta está em sys.tcp_endpoints, não em sys.database_mirroring_endpoints
            endpoint_query = """
            SELECT
                e.name as endpoint_name,
                e.state_desc as endpoint_state,
                te.port as endpoint_port,
                dm.encryption_algorithm_desc as encryption,
                dm.state_desc as mirror_state
            FROM sys.endpoints e
            INNER JOIN sys.database_mirroring_endpoints dm ON e.endpoint_id = dm.endpoint_id
            LEFT JOIN sys.tcp_endpoints te ON e.endpoint_id = te.endpoint_id
            WHERE e.type = 4  -- DATABASE_MIRRORING
            """
            cursor.execute(endpoint_query)
            endpoint = cursor.fetchone()

            if endpoint:
                diagnosis['endpoint_status'] = {
                    'name': endpoint[0],
                    'state': endpoint[1],
                    'port': endpoint[2] if endpoint[2] else 5022,  # Default AG port
                    'encryption': endpoint[3],
                    'mirror_state': endpoint[4]
                }

                if endpoint[1] != 'STARTED':
                    diagnosis['connection_issues'].append({
                        'type': 'ENDPOINT_NOT_STARTED',
                        'description': f'Endpoint "{endpoint[0]}" está {endpoint[1]} (deveria estar STARTED)',
                        'port': endpoint[2]
                    })
            else:
                diagnosis['connection_issues'].append({
                    'type': 'ENDPOINT_NOT_FOUND',
                    'description': 'Endpoint de mirroring não encontrado'
                })

            # 3. Obter estado de TODAS as réplicas (funciona em qualquer nó, mas com dados limitados no secundário)
            replicas_query = """
            SELECT
                ar.replica_server_name,
                ars.role_desc,
                ars.operational_state_desc,
                ars.connected_state_desc,
                ars.synchronization_health_desc,
                ars.last_connect_error_number,
                ars.last_connect_error_description,
                ars.last_connect_error_timestamp,
                ar.endpoint_url,
                ar.availability_mode_desc,
                ars.is_local
            FROM sys.availability_replicas ar
            INNER JOIN sys.dm_hadr_availability_replica_states ars
                ON ar.replica_id = ars.replica_id
            ORDER BY ars.is_local DESC, ar.replica_server_name
            """
            cursor.execute(replicas_query)
            replicas = cursor.fetchall()

            for rep in replicas:
                replica_info = {
                    'server_name': rep[0],
                    'role': rep[1],
                    'operational_state': rep[2],
                    'connected_state': rep[3],
                    'sync_health': rep[4],
                    'last_error_number': rep[5],
                    'last_error_desc': rep[6],
                    'last_error_time': rep[7].isoformat() if rep[7] else None,
                    'endpoint_url': rep[8],
                    'availability_mode': rep[9],
                    'is_local': bool(rep[10])
                }
                diagnosis['replica_states'].append(replica_info)

                # Detectar problemas com réplicas remotas
                if not replica_info['is_local']:
                    if replica_info['connected_state'] != 'CONNECTED':
                        diagnosis['connection_issues'].append({
                            'type': 'REPLICA_DISCONNECTED',
                            'description': f"Réplica {rep[0]} está {replica_info['connected_state']}",
                            'server': rep[0],
                            'endpoint_url': rep[8]
                        })
                    if replica_info['sync_health'] == 'NOT_HEALTHY':
                        diagnosis['connection_issues'].append({
                            'type': 'REPLICA_NOT_HEALTHY',
                            'description': f"Réplica {rep[0]} está NOT_HEALTHY",
                            'server': rep[0],
                            'last_error': replica_info['last_error_desc']
                        })

            logger.info(f"🔍 [Diagnose] Réplicas processadas: {len(diagnosis['replica_states'])}")

            # 4. Buscar erros recentes no SQL Error Log relacionados ao AG
            # OTIMIZADO: Uma única chamada a xp_readerrorlog (muito mais rápido)
            # Filtra por 'HADR' que captura a maioria dos eventos de AG
            logger.info(f"🔍 [Diagnose] Buscando error log (xp_readerrorlog)...")
            errorlog_query = """
            CREATE TABLE #AGErrors (LogDate DATETIME, ProcessInfo VARCHAR(50), LogText VARCHAR(MAX))

            -- xp_readerrorlog não aceita expressões SQL como parâmetro
            -- Precisa declarar variável para a data
            DECLARE @StartDate DATETIME = DATEADD(HOUR, -6, GETDATE())

            BEGIN TRY
                -- Uma única chamada é MUITO mais rápida que múltiplas
                -- Buscar apenas no log atual (0) das últimas 6 horas
                INSERT INTO #AGErrors
                EXEC xp_readerrorlog 0, 1, 'HADR', NULL, @StartDate, NULL
            END TRY
            BEGIN CATCH
                -- Ignora erro silenciosamente se xp_readerrorlog falhar
            END CATCH

            SELECT TOP 15 LogDate, LogText
            FROM #AGErrors
            WHERE LogText IS NOT NULL
              AND LEN(LogText) > 10
              AND LogText NOT LIKE '%informational message%'
              AND LogText NOT LIKE '%This is an informational%'
            ORDER BY LogDate DESC

            DROP TABLE #AGErrors
            """
            try:
                import time as _time
                _log_start = _time.time()
                cursor.execute(errorlog_query)
                log_rows = cursor.fetchall()
                _log_elapsed = _time.time() - _log_start
                logger.info(f"🔍 [Diagnose] Error log executado em {_log_elapsed:.2f}s, {len(log_rows)} entradas")

                for log_row in log_rows:
                    log_text = log_row[1] if log_row[1] else ''
                    log_text_lower = log_text.lower()

                    # Classificar severidade do log
                    severity = 'INFO'
                    if 'error' in log_text_lower or 'failed' in log_text_lower:
                        severity = 'ERROR'
                    elif 'warning' in log_text_lower or 'timeout' in log_text_lower:
                        severity = 'WARNING'

                    diagnosis['error_log_entries'].append({
                        'timestamp': log_row[0].isoformat() if log_row[0] else None,
                        'message': log_text[:500],  # Limitar tamanho
                        'severity': severity
                    })
            except Exception as log_err:
                logger.warning(f"⚠️ [Diagnose] Erro ao ler error log: {log_err}")

            # 5. ANÁLISE DE CAUSA RAIZ
            logger.info(f"🔍 [Diagnose] Analisando causa raiz...")
            diagnosis = self._analyze_root_cause(diagnosis)
            logger.info(f"✅ [Diagnose] Diagnóstico concluído: {diagnosis.get('root_cause_category', 'N/A')}")

        except Exception as e:
            logger.error(f"Erro no diagnóstico AG de {server}: {e}")
            diagnosis['root_cause'] = f'Erro durante diagnóstico: {str(e)}'
            diagnosis['root_cause_category'] = 'DIAGNOSTIC_ERROR'
            diagnosis['severity'] = 'ERROR'

        return diagnosis

    def _analyze_root_cause(self, diagnosis: Dict) -> Dict:
        """
        Analisa os dados coletados e determina a causa raiz provável.
        """
        issues = diagnosis['connection_issues']
        endpoint = diagnosis['endpoint_status']
        replicas = diagnosis['replica_states']
        logs = diagnosis['error_log_entries']

        # Contadores para análise
        disconnected_replicas = [r for r in replicas if r['connected_state'] != 'CONNECTED' and not r['is_local']]
        unhealthy_replicas = [r for r in replicas if r['sync_health'] == 'NOT_HEALTHY']
        error_logs = [l for l in logs if l['severity'] == 'ERROR']

        # Verificar causa raiz por prioridade

        # 1. Endpoint não iniciado
        if endpoint and endpoint['state'] != 'STARTED':
            diagnosis['root_cause'] = f"O endpoint de mirroring '{endpoint['name']}' não está iniciado (status: {endpoint['state']})"
            diagnosis['root_cause_category'] = 'ENDPOINT'
            diagnosis['severity'] = 'CRITICAL'
            diagnosis['recommendations'].append({
                'action': f"Executar: ALTER ENDPOINT [{endpoint['name']}] STATE = STARTED",
                'priority': 'HIGH',
                'type': 'SQL_COMMAND'
            })
            diagnosis['recommendations'].append({
                'action': 'Verificar se o serviço SQL Server tem permissão para usar a porta configurada',
                'priority': 'MEDIUM',
                'type': 'CHECK'
            })
            return diagnosis

        # 2. Todas as réplicas remotas desconectadas
        if len(disconnected_replicas) > 0 and len(disconnected_replicas) == len([r for r in replicas if not r['is_local']]):
            diagnosis['root_cause'] = 'Todas as réplicas remotas estão desconectadas - possível problema de rede ou firewall'
            diagnosis['root_cause_category'] = 'NETWORK'
            diagnosis['severity'] = 'CRITICAL'

            if endpoint:
                diagnosis['recommendations'].append({
                    'action': f"Verificar se a porta {endpoint['port']} está aberta no firewall para todas as réplicas",
                    'priority': 'HIGH',
                    'type': 'CHECK'
                })

            diagnosis['recommendations'].append({
                'action': 'Testar conectividade de rede (ping/telnet) entre os nós do AG',
                'priority': 'HIGH',
                'type': 'CHECK'
            })
            diagnosis['recommendations'].append({
                'action': 'Verificar se os serviços SQL Server estão em execução em todas as réplicas',
                'priority': 'HIGH',
                'type': 'CHECK'
            })
            return diagnosis

        # 3. Algumas réplicas desconectadas
        if len(disconnected_replicas) > 0:
            servers = ', '.join([r['server_name'] for r in disconnected_replicas])
            diagnosis['root_cause'] = f"Réplica(s) desconectada(s): {servers}"
            diagnosis['root_cause_category'] = 'REPLICA_CONNECTION'
            diagnosis['severity'] = 'WARNING'

            for rep in disconnected_replicas:
                if rep['last_error_desc']:
                    diagnosis['recommendations'].append({
                        'action': f"Erro reportado para {rep['server_name']}: {rep['last_error_desc']}",
                        'priority': 'HIGH',
                        'type': 'INFO'
                    })

            diagnosis['recommendations'].append({
                'action': 'Verificar conectividade de rede com as réplicas desconectadas',
                'priority': 'HIGH',
                'type': 'CHECK'
            })
            return diagnosis

        # 4. Réplicas NOT_HEALTHY mas conectadas (problema de sincronização)
        if len(unhealthy_replicas) > 0:
            # Verificar se é apenas a réplica local
            local_unhealthy = [r for r in unhealthy_replicas if r['is_local']]
            remote_unhealthy = [r for r in unhealthy_replicas if not r['is_local']]

            if local_unhealthy and not remote_unhealthy:
                # Apenas a réplica local está NOT_HEALTHY
                diagnosis['root_cause'] = 'Esta réplica está reportando NOT_HEALTHY, mas as réplicas remotas podem estar OK. Pode ser um problema de visibilidade limitada do secundário.'
                diagnosis['root_cause_category'] = 'SECONDARY_VIEW'
                diagnosis['severity'] = 'INFO'
                diagnosis['recommendations'].append({
                    'action': 'Consultar o nó primário para obter a visão completa do AG',
                    'priority': 'MEDIUM',
                    'type': 'CHECK'
                })
                diagnosis['recommendations'].append({
                    'action': 'Verificar se há logs de erro específicos no SQL Error Log',
                    'priority': 'MEDIUM',
                    'type': 'CHECK'
                })
            else:
                servers = ', '.join([r['server_name'] for r in unhealthy_replicas])
                diagnosis['root_cause'] = f"Réplica(s) com sincronização NOT_HEALTHY: {servers}"
                diagnosis['root_cause_category'] = 'SYNC_HEALTH'
                diagnosis['severity'] = 'WARNING'

                diagnosis['recommendations'].append({
                    'action': 'Verificar se há jobs ou processos consumindo recursos excessivos',
                    'priority': 'MEDIUM',
                    'type': 'CHECK'
                })
                diagnosis['recommendations'].append({
                    'action': 'Verificar latência de rede entre os nós',
                    'priority': 'MEDIUM',
                    'type': 'CHECK'
                })

            return diagnosis

        # 5. Verificar erros no log
        if error_logs:
            recent_errors = [l['message'] for l in error_logs[:3]]
            diagnosis['root_cause'] = 'Erros encontrados no SQL Error Log relacionados ao AG'
            diagnosis['root_cause_category'] = 'ERROR_LOG'
            diagnosis['severity'] = 'WARNING'
            diagnosis['recommendations'].append({
                'action': f"Analisar erros recentes: {'; '.join(recent_errors)[:200]}...",
                'priority': 'MEDIUM',
                'type': 'INFO'
            })
            return diagnosis

        # 6. Tudo parece OK
        if not issues:
            diagnosis['root_cause'] = 'Nenhum problema identificado - o AG parece estar funcionando normalmente'
            diagnosis['root_cause_category'] = 'HEALTHY'
            diagnosis['severity'] = 'INFO'
            return diagnosis

        # 7. Há issues mas não conseguimos determinar causa específica
        diagnosis['root_cause'] = 'Problemas detectados mas causa raiz não determinada automaticamente'
        diagnosis['root_cause_category'] = 'UNKNOWN'
        diagnosis['severity'] = 'WARNING'
        diagnosis['recommendations'].append({
            'action': 'Revisar manualmente os detalhes do diagnóstico',
            'priority': 'MEDIUM',
            'type': 'CHECK'
        })

        return diagnosis

    def get_all_ag_overview_lazy(self) -> Dict:
        """
        Obtém overview de todos os AGs sem conectar (lazy loading)

        Retorna apenas informações do JSON (não conecta nos servidores).
        Use este método para listagem rápida no startup.

        Returns:
            Dict com lista de AGs do inventory (sem status)
        """
        overview = {
            'total_ags': len(self.ag_servers),
            'total_replicas': 0,
            'healthy_replicas': 0,
            'total_databases': 0,
            'healthy_databases': 0,
            'synchronized_databases': 0,
            'ags': [],
            'lazy_loaded': True  # Indica que não conectou
        }

        for ag_server in self.ag_servers:
            ag_info = {
                'ag_name': ag_server.get('ag_name', ''),
                'server': ag_server['server'],
                'instance': ag_server.get('instance', ''),
                'listener': ag_server.get('listener', ''),
                'status': 'UNKNOWN',  # Só conecta quando usuário clicar
                'lazy_loaded': True
            }
            overview['ags'].append(ag_info)

        return overview

    def get_all_ag_overview(self, lazy: bool = False) -> Dict:
        """
        Obtém overview de todos os AGs

        Args:
            lazy: Se True, não conecta nos servidores (apenas retorna dados do JSON)

        Returns:
            Dict com overview de todos os AGs
        """
        # Lazy loading: retorna apenas dados do JSON sem conectar
        if lazy:
            return self.get_all_ag_overview_lazy()

        # Full loading: conecta em todos os servidores (LENTO - 84 conexões!)
        overview = {
            'total_ags': 0,
            'total_replicas': 0,
            'healthy_replicas': 0,
            'total_databases': 0,
            'healthy_databases': 0,
            'synchronized_databases': 0,
            'ags': [],
            'lazy_loaded': False
        }

        for ag_server in self.ag_servers:
            server = ag_server['server']
            instance = ag_server.get('instance', '')

            status = self.get_ag_status(server, instance)
            if status:
                overview['total_ags'] += 1
                overview['total_replicas'] += status['total_replicas']
                overview['healthy_replicas'] += status['healthy_replicas']
                overview['total_databases'] += status['total_databases']
                overview['healthy_databases'] += status['healthy_databases']
                overview['synchronized_databases'] += status['synchronized_databases']

                # Obter eventos recentes
                events = self.get_ag_failover_events(server, instance, days=7)
                patterns = self.analyze_failover_patterns(events)

                ag_info = {
                    'ag_name': status['ag_name'],
                    'server': server,
                    'instance': instance,
                    'listener': ag_server.get('listener', ''),
                    'status': status,
                    'recent_events_count': len(events),
                    'critical_events_count': len([e for e in events if e.severity == 'CRITICAL']),
                    'patterns': [asdict(p) for p in patterns]
                }

                overview['ags'].append(ag_info)

        return overview

# === SINGLETON DO ALWAYSONCHECKER ===

_alwayson_checker_instance: Optional[AlwaysOnChecker] = None
_checker_lock = threading.Lock()

def get_alwayson_checker() -> AlwaysOnChecker:
    """
    Retorna instância singleton do AlwaysOnChecker

    Benefícios:
    - Carrega JSON apenas 1 vez (42 servidores)
    - Reutiliza pool global de conexões
    - Elimina criação repetida de pools
    - Reduz drasticamente conexões no startup

    Returns:
        AlwaysOnChecker singleton
    """
    global _alwayson_checker_instance

    if _alwayson_checker_instance is None:
        with _checker_lock:
            # Double-check locking
            if _alwayson_checker_instance is None:
                _alwayson_checker_instance = AlwaysOnChecker(use_global_pool=True)
                logger.info(f"AlwaysOnChecker singleton created ({len(_alwayson_checker_instance.ag_servers)} servidores)")

    return _alwayson_checker_instance


def get_alwayson_overview(lazy: bool = True) -> Dict:
    """
    Função helper para obter overview de Always On (usa singleton)

    Args:
        lazy: Se True, retorna apenas dados do JSON sem conectar (RÁPIDO)
              Se False, conecta em todos os servidores (LENTO - 84 conexões)

    Returns:
        Dict com overview de Always On
    """
    checker = get_alwayson_checker()
    return checker.get_all_ag_overview(lazy=lazy)


def get_alwayson_status(server: str, instance: str = "") -> Optional[Dict]:
    """Função helper para obter status de um AG específico (usa singleton)"""
    checker = get_alwayson_checker()
    return checker.get_ag_status(server, instance)


def diagnose_ag_issues(server: str, instance: str = "") -> Dict:
    """
    Diagnostica problemas do Always On e identifica causa raiz.

    Funciona tanto no primário quanto no secundário, adaptando as queries.

    Args:
        server: Nome do servidor
        instance: Instância SQL Server

    Returns:
        Dict com diagnóstico completo incluindo:
        - is_primary: bool
        - connection_issues: Lista de problemas de conexão
        - endpoint_status: Status do endpoint de mirroring
        - error_log_entries: Erros recentes do AG no log
        - recommendations: Recomendações de ação
        - root_cause: Causa raiz provável
    """
    checker = get_alwayson_checker()
    return checker.diagnose_ag_issues(server, instance)

