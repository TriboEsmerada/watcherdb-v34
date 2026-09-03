#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TapOS Always On Check Module
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
                "excel_path": "C:\\Server_Inventory\\XPTO_SQL_Server_Inventory.xlsx",
                "sheet_name": "Servers",
                "cache_ttl_seconds": 300,
                "analysis_window_days": 30
            }
    
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

        # Buscar com timeout (45s - menor que o timeout HTTP do frontend)
        result = self._get_ag_status_with_timeout(server, instance, timeout=45)

        # Cachear resultado (mesmo se for erro/timeout, para não ficar tentando repetidamente)
        if result:
            self._status_cache[cache_key] = (result, time.time())

        return result

    def _get_ag_status_internal(self, server: str, instance: str = "") -> Optional[Dict]:
        """Implementação interna do get_ag_status (executada com timeout)"""
        try:
            conn_info = ConnectionInfo(
                server=server,
                instance=instance if instance else "DEFAULT",
                database="master",
                connection_timeout=45  # Timeout de conexão
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
            
            cursor = conn.cursor()
            cursor.execute(ag_status_query)
            rows = cursor.fetchall()
            
            logger.debug(f"Query de réplicas retornou {len(rows)} linhas para {server}\\{instance}")
            
            if not rows:
                logger.warning(f"Nenhuma réplica encontrada para {server}\\{instance}")
                return None
            
            # Processar réplicas
            replicas = []
            ag_name = None
            current_primary = None
            
            for row in rows:
                if not ag_name:
                    ag_name = row[0]
                
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
            db_status_query = """
            SELECT 
                db.name as database_name,
                ar.replica_server_name,
                drs.synchronization_state_desc,
                drs.synchronization_health_desc as db_health,
                drs.database_state_desc,
                drs.is_suspended,
                drs.suspend_reason_desc,
                drs.log_send_queue_size,
                drs.redo_queue_size
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
                        database_state=db_row[4],
                        is_suspended=bool(db_row[5]),
                        suspend_reason=db_row[6] if db_row[6] else None,
                        log_send_queue_size=db_row[7] if db_row[7] else None,
                        redo_queue_size=db_row[8] if db_row[8] else None
                    )
                    databases.append(db)
                except Exception as db_err:
                    logger.warning(f"Erro ao processar database row: {db_err}, row: {db_row}")
                    continue
            
            logger.info(f"Status AG obtido: {len(replicas)} réplicas, {len(databases)} databases para {server}\\{instance}")
            
            result = {
                'ag_name': ag_name,
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
            conn_info = ConnectionInfo(
                server=server,
                instance=instance if instance else "DEFAULT",
                database="master"
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
                          xel.event_data.value('(event/@timestamp)[1]', 'datetime2')) >= DATEADD(DAY, -?, GETDATE())
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
            
            # Query para SQL Error Log
            errorlog_query = f"""
            CREATE TABLE #ErrorLog (LogDate DATETIME, ProcessInfo VARCHAR(50), LogText VARCHAR(MAX))
            
            DECLARE @FileNumber INT = 0
            WHILE @FileNumber <= 3
            BEGIN
                BEGIN TRY
                    INSERT INTO #ErrorLog
                    EXEC xp_readerrorlog @FileNumber, 1, 'Always On', NULL, DATEADD(DAY, -{days}, GETDATE()), NULL
                END TRY
                BEGIN CATCH
                    -- Ignora erro se arquivo não existir
                END CATCH
                SET @FileNumber = @FileNumber + 1
            END
            
            SELECT TOP 20 LogDate, LogText
            FROM #ErrorLog
            WHERE (LogText LIKE '%primary%' AND LogText LIKE '%secondary%')
               OR LogText LIKE '%failover%'
               OR LogText LIKE '%role change%'
               OR LogText LIKE '%lease expired%'
               OR LogText LIKE '%lease timeout%'
            ORDER BY LogDate DESC
            
            DROP TABLE #ErrorLog
            """
            
            try:
                cursor.execute(errorlog_query)
                log_rows = cursor.fetchall()
                
                for log_row in log_rows:
                    log_date = log_row[0]
                    log_text = log_row[1].lower()
                    
                    event_type = 'INFO'
                    severity = 'INFO'
                    
                    if 'lease expired' in log_text or 'lease timeout' in log_text:
                        event_type = 'LEASE_TIMEOUT'
                        severity = 'CRITICAL'
                    elif 'failover' in log_text:
                        event_type = 'FAILOVER'
                        severity = 'ERROR'
                    elif 'role change' in log_text:
                        event_type = 'ROLE_CHANGE'
                        severity = 'WARNING'
                    
                    event = AGFailoverEvent(
                        timestamp=log_date,
                        event_type=event_type,
                        source_server=server,
                        description=log_row[1][:200],
                        severity=severity
                    )
                    events.append(event)
            except Exception as e:
                logger.debug(f"Erro ao ler error log: {e}")
            
        except Exception as e:
            logger.error(f"Erro ao obter eventos de failover de {server}: {e}")
        
        return events
    
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

