#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TapOS SQL Server Service Monitor
Verifica status dos serviços SQL Server via WMI/PowerShell
"""

import subprocess
import logging
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class SQLServiceStatus:
    """Status de um serviço SQL Server"""
    service_name: str
    display_name: str
    status: str  # Running, Stopped, Paused, etc.
    start_mode: str  # Automatic, Manual, Disabled
    server: str
    instance: Optional[str] = None
    last_check: Optional[datetime] = None
    
    @property
    def is_running(self) -> bool:
        """Retorna True se o serviço está rodando"""
        return self.status.lower() == 'running'
    
    @property
    def is_critical(self) -> bool:
        """Retorna True se é um serviço crítico e está parado"""
        critical_services = ['MSSQLSERVER', 'SQLSERVERAGENT', 'SQLSERVERAGENT$']
        service_upper = self.service_name.upper()
        for critical in critical_services:
            if critical in service_upper or service_upper in critical:
                return not self.is_running
        return False

class SQLServiceMonitor:
    """Monitor de serviços SQL Server"""
    
    def __init__(self):
        """Inicializa o monitor"""
        self.cache = {}
        self.cache_ttl = 60  # Cache por 60 segundos
    
    def _parse_server_and_instance(self, server_id: str) -> Tuple[str, Optional[str]]:
        """Parse server_id para (server, instance)"""
        if '\\' in server_id:
            server, instance = server_id.split('\\', 1)
            return server, instance
        elif '_' in server_id and not server_id.endswith('_DEFAULT'):
            parts = server_id.rsplit('_', 1)
            if len(parts) == 2 and parts[1]:
                return parts[0], parts[1]
        return server_id.replace('_DEFAULT', ''), None
    
    def get_sql_services(self, server: str, instance: Optional[str] = None, all_services: bool = False) -> List[SQLServiceStatus]:
        """Obtém status dos serviços SQL Server de um servidor"""
        try:
            # Montar nome do serviço baseado na instância
            service_patterns = []
            
            if instance and instance.upper() != 'DEFAULT':
                # Instância nomeada: MSSQL$INSTANCE, SQLAgent$INSTANCE
                instance_clean = instance.replace('\\', '').replace('$', '')
                service_patterns = [
                    f"MSSQL${instance_clean}",
                    f"SQLSERVERAGENT${instance_clean}",
                    f"MSSQLSERVER",
                    f"SQLSERVERAGENT"
                ]
            else:
                # Instância padrão
                service_patterns = [
                    "MSSQLSERVER",
                    "SQLSERVERAGENT"
                ]
            
            # Se all_services=True, buscar todos os serviços relacionados ao SQL
            if all_services:
                # PowerShell script para buscar TODOS os serviços SQL relacionados
                ps_script = f"""
                $server = '{server}'
                $services = @()
                
                # Buscar serviços que começam com MSSQL, SQLSERVER, SQL
                $allServices = Get-Service -ComputerName $server -ErrorAction SilentlyContinue | Where-Object {{
                    $_.Name -like 'MSSQL*' -or 
                    $_.Name -like 'SQLSERVER*' -or 
                    $_.Name -like 'SQL*Agent*' -or
                    $_.DisplayName -like '*SQL Server*'
                }}
                
                foreach ($svc in $allServices) {{
                    try {{
                        $services += @{{
                            Name = $svc.Name
                            DisplayName = $svc.DisplayName
                            Status = $svc.Status.ToString()
                            StartType = $svc.StartType.ToString()
                        }}
                    }} catch {{
                        # Ignorar erro
                    }}
                }}
                
                $services | ConvertTo-Json -Compress
                """
            else:
                # PowerShell script para verificar serviços específicos
                ps_script = f"""
                $server = '{server}'
                $services = @()
                $patterns = @({', '.join([f"'{p}'" for p in service_patterns])})
                
                foreach ($pattern in $patterns) {{
                    try {{
                        $svc = Get-Service -ComputerName $server -Name $pattern -ErrorAction SilentlyContinue
                        if ($svc) {{
                            $services += @{{
                                Name = $svc.Name
                                DisplayName = $svc.DisplayName
                                Status = $svc.Status.ToString()
                                StartType = $svc.StartType.ToString()
                            }}
                        }}
                    }} catch {{
                        # Serviço não encontrado - ignorar
                    }}
                }}
                
                $services | ConvertTo-Json -Compress
                """
            
            # Executar PowerShell
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.warning(f"Erro ao executar PowerShell para {server}: {result.stderr}")
                return []
            
            if not result.stdout or result.stdout.strip() == '[]':
                logger.debug(f"Nenhum serviço SQL encontrado em {server}")
                return []
            
            # Parse JSON response
            services_data = json.loads(result.stdout)
            if not isinstance(services_data, list):
                services_data = [services_data]
            
            services = []
            for svc_data in services_data:
                service = SQLServiceStatus(
                    service_name=svc_data.get('Name', ''),
                    display_name=svc_data.get('DisplayName', ''),
                    status=svc_data.get('Status', 'Unknown'),
                    start_mode=svc_data.get('StartType', 'Unknown'),
                    server=server,
                    instance=instance,
                    last_check=datetime.now()
                )
                services.append(service)
            
            return services
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout ao verificar serviços em {server}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear resposta PowerShell para {server}: {e}")
            return []
        except Exception as e:
            logger.error(f"Erro ao verificar serviços SQL em {server}: {e}", exc_info=True)
            return []
    
    def get_service_logs(self, server: str, service_name: str, hours: int = 24, instance: Optional[str] = None) -> List[Dict]:
        """Obtém logs de eventos do Windows relacionados a um serviço"""
        try:
            # Escapar caracteres especiais no nome do serviço para PowerShell
            service_name_escaped = service_name.replace("'", "''").replace("$", "`$")
            
            ps_script = f"""
            $server = '{server}'
            $serviceName = '{service_name_escaped}'
            $hours = {hours}
            $since = (Get-Date).AddHours(-$hours)
            $result = @()
            
            # 1. EVENT VIEWER - Service Control Manager (Event IDs críticos)
            try {{
                # Usar Get-EventLog para melhor compatibilidade com Event IDs específicos
                $scmEvents = Get-EventLog -LogName System -Source "Service Control Manager" -After $since -ErrorAction SilentlyContinue | Where-Object {{
                    ($_.Message -like "*$serviceName*" -or $_.Message -like "*SQL Server*") -and
                    ($_.InstanceId -eq 7034 -or $_.InstanceId -eq 7035 -or $_.InstanceId -eq 7036 -or 
                     $_.InstanceId -eq 7031 -or $_.InstanceId -eq 7037 -or $_.InstanceId -eq 7038 -or $_.InstanceId -eq 7040)
                }} | Select-Object -First 100 -Property TimeGenerated, InstanceId, EntryType, Message
                
                # Também buscar via Get-WinEvent para eventos mais recentes
                $winEvents = Get-WinEvent -ComputerName $server -FilterHashtable @{{
                    LogName = 'System'
                    StartTime = $since
                    ProviderName = 'Service Control Manager'
                }} -ErrorAction SilentlyContinue | Where-Object {{
                    ($_.Message -like "*$serviceName*" -or $_.Message -like "*SQL Server*") -and
                    ($_.Id -eq 7034 -or $_.Id -eq 7035 -or $_.Id -eq 7036 -or 
                     $_.Id -eq 7031 -or $_.Id -eq 7037 -or $_.Id -eq 7038 -or $_.Id -eq 7040)
                }} | Select-Object -First 100 -Property TimeCreated, Id, LevelDisplayName, Message, ProviderName
                
                # Converter Get-EventLog para formato compatível
                foreach ($event in $scmEvents) {{
                    $result += @{{
                        TimeCreated = $event.TimeGenerated.ToString('yyyy-MM-dd HH:mm:ss')
                        EventId = $event.InstanceId
                        Level = $event.EntryType.ToString()
                        Message = $event.Message
                        Source = 'Service Control Manager'
                        LogName = 'System'
                        SourceType = 'EventLog'
                    }}
                }}
                
                # Adicionar eventos do Get-WinEvent
                foreach ($event in $winEvents) {{
                    $result += @{{
                        TimeCreated = $event.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                        EventId = $event.Id
                        Level = $event.LevelDisplayName
                        Message = $event.Message
                        Source = 'Service Control Manager'
                        LogName = 'System'
                        SourceType = 'WinEvent'
                    }}
                }}
            }} catch {{
                Write-Warning "Erro ao buscar eventos SCM: $_"
            }}
            
            # Buscar eventos do Application Log relacionados ao SQL Server
            try {{
                $appEvents = Get-WinEvent -ComputerName $server -FilterHashtable @{{
                    LogName = 'Application'
                    StartTime = $since
                }} -ErrorAction SilentlyContinue | Where-Object {{
                    ($_.ProviderName -like "*SQL*" -or $_.ProviderName -like "*MSSQL*") -and
                    ($_.Message -like "*$serviceName*" -or $_.Message -like "*service*" -or $_.Message -like "*started*" -or $_.Message -like "*stopped*")
                }} | Select-Object -First 50 -Property TimeCreated, Id, LevelDisplayName, Message, ProviderName
                
                foreach ($event in $appEvents) {{
                    $result += @{{
                        TimeCreated = $event.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                        EventId = $event.Id
                        Level = $event.LevelDisplayName
                        Message = $event.Message
                        Source = $event.ProviderName
                        LogName = 'Application'
                    }}
                }}
            }} catch {{
                Write-Warning "Erro ao buscar eventos Application: $_"
            }}
            
            # Buscar eventos de erro crítico do sistema relacionados
            try {{
                $errorEvents = Get-WinEvent -ComputerName $server -FilterHashtable @{{
                    LogName = 'System'
                    StartTime = $since
                    Level = 2,3  # Error e Warning
                }} -ErrorAction SilentlyContinue | Where-Object {{
                    $_.Message -like "*$serviceName*" -or
                    ($_.Message -like "*SQL*" -and ($_.Message -like "*service*" -or $_.Message -like "*failed*" -or $_.Message -like "*stop*"))
                }} | Select-Object -First 30 -Property TimeCreated, Id, LevelDisplayName, Message, ProviderName
                
                foreach ($event in $errorEvents) {{
                    $result += @{{
                        TimeCreated = $event.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                        EventId = $event.Id
                        Level = $event.LevelDisplayName
                        Message = $event.Message
                        Source = $event.ProviderName
                        LogName = 'System'
                    }}
                }}
            }} catch {{
                Write-Warning "Erro ao buscar eventos de erro: $_"
            }}
            
            # Ordenar por data/hora (mais recente primeiro) e remover duplicados
            $result = $result | Sort-Object -Property TimeCreated -Descending | Select-Object -First 100 -Unique
            
            $result | ConvertTo-Json -Compress
            """
            
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.warning(f"Erro ao buscar logs de {service_name} em {server}: {result.stderr}")
                return []
            
            if not result.stdout or result.stdout.strip() == '[]':
                return []
            
            events_data = json.loads(result.stdout)
            if not isinstance(events_data, list):
                events_data = [events_data]
            
            return events_data
            
        except Exception as e:
            logger.error(f"Erro ao buscar logs de serviço {service_name} em {server}: {e}")
            return []
    
    def get_sql_error_logs(self, server: str, instance: Optional[str] = None, hours: int = 24) -> List[Dict]:
        """Obtém logs do SQL Server Error Log relacionados a shutdown/start/stop"""
        try:
            from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo
            
            conn_info = ConnectionInfo(
                server=server,
                instance=instance if instance else "DEFAULT",
                database="master",
                use_windows_auth=True
            )
            
            pool = ConnectionPool(max_connections=15)  # Aumentado para melhor performance
            conn = pool.get_connection(conn_info)
            if not conn:
                logger.warning(f"Não foi possível conectar em {server} para buscar SQL Error Log")
                return []
            
            # Query para buscar shutdown/starting/stopped no error log
            query = """
            CREATE TABLE #ErrorLog (
                LogDate DATETIME,
                ProcessInfo VARCHAR(50),
                LogText VARCHAR(MAX)
            )
            
            DECLARE @FileNumber INT = 0
            DECLARE @SinceDate DATETIME = DATEADD(HOUR, -?, GETDATE())
            
            WHILE @FileNumber <= 3
            BEGIN
                BEGIN TRY
                    INSERT INTO #ErrorLog
                    EXEC xp_readerrorlog @FileNumber, 1, NULL, NULL, @SinceDate, NULL
                END TRY
                BEGIN CATCH
                    -- Ignora erro se arquivo não existir
                END CATCH
                SET @FileNumber = @FileNumber + 1
            END
            
            SELECT 
                LogDate,
                ProcessInfo,
                LogText
            FROM #ErrorLog
            WHERE LogText LIKE '%shutdown%' 
               OR LogText LIKE '%starting%'
               OR LogText LIKE '%stopped%'
               OR LogText LIKE '%SQL Server is starting%'
               OR LogText LIKE '%SQL Server is terminating%'
            ORDER BY LogDate DESC
            
            DROP TABLE #ErrorLog
            """
            
            cursor = conn.cursor()
            cursor.execute(query, hours)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                logs.append({
                    'TimeCreated': row[0].isoformat() if isinstance(row[0], datetime) else str(row[0]),
                    'EventId': None,
                    'Level': 'Information',
                    'Message': row[2] if len(row) > 2 else '',
                    'Source': f'SQL Server Error Log ({row[1] if len(row) > 1 else "N/A"})',
                    'LogName': 'SQL Error Log',
                    'SourceType': 'SQLErrorLog'
                })
            
            cursor.close()
            pool.return_connection(conn_info, conn)
            
            return logs
            
        except Exception as e:
            logger.error(f"Erro ao buscar SQL Error Log de {server}: {e}", exc_info=True)
            return []
    
    def get_default_trace_logs(self, server: str, instance: Optional[str] = None, hours: int = 24) -> List[Dict]:
        """Obtém logs do Default Trace do SQL Server (Event Classes 46, 47, 164)"""
        try:
            from modules.monitoring.monitoring import ConnectionPool, ConnectionInfo
            
            conn_info = ConnectionInfo(
                server=server,
                instance=instance if instance else "DEFAULT",
                database="master",
                use_windows_auth=True
            )
            
            pool = ConnectionPool(max_connections=15)  # Aumentado para melhor performance
            conn = pool.get_connection(conn_info)
            if not conn:
                logger.warning(f"Não foi possível conectar em {server} para buscar Default Trace")
                return []
            
            # Query para buscar eventos do Default Trace
            # Focar APENAS em Server Stop (47) - eventos problemáticos
            # Server Start (46) só mostra se houver um Stop nas últimas 2 horas e Start dentro de 1 hora após
            query = """
            DECLARE @TracePath NVARCHAR(260)
            SELECT @TracePath = path 
            FROM sys.traces 
            WHERE is_default = 1
            
            IF @TracePath IS NOT NULL
            BEGIN
                -- Buscar Server Stops (sempre crítico - indica problema)
                SELECT 
                    LoginName,
                    HostName,
                    StartTime,
                    EventClass,
                    'Server Stop' as EventDescription,
                    TextData
                FROM sys.fn_trace_gettable(@TracePath, DEFAULT)
                WHERE EventClass = 47  -- Server Stop
                  AND StartTime >= DATEADD(HOUR, -?, GETDATE())
                
                UNION ALL
                
                -- Buscar Server Starts APENAS se houver um Server Stop recente (indicando recuperação)
                SELECT 
                    t1.LoginName,
                    t1.HostName,
                    t1.StartTime,
                    t1.EventClass,
                    'Server Start (após Stop)' as EventDescription,
                    t1.TextData
                FROM sys.fn_trace_gettable(@TracePath, DEFAULT) t1
                WHERE t1.EventClass = 46  -- Server Start
                  AND t1.StartTime >= DATEADD(HOUR, -?, GETDATE())
                  AND EXISTS (
                      SELECT 1 
                      FROM sys.fn_trace_gettable(@TracePath, DEFAULT) t2
                      WHERE t2.EventClass = 47  -- Server Stop
                        AND t2.StartTime >= DATEADD(HOUR, -?, GETDATE())
                        AND t2.StartTime < t1.StartTime  -- Stop antes do Start
                        AND DATEDIFF(MINUTE, t2.StartTime, t1.StartTime) <= 60  -- Start dentro de 1 hora após Stop
                  )
                
                ORDER BY StartTime DESC
            END
            ELSE
            BEGIN
                SELECT NULL as LoginName, NULL as HostName, NULL as StartTime, NULL as EventClass, NULL as EventDescription, NULL as TextData WHERE 1=0
            END
            """
            
            cursor = conn.cursor()
            cursor.execute(query, hours)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                if row[2]:  # StartTime não nulo
                    logs.append({
                        'TimeCreated': row[2].isoformat() if isinstance(row[2], datetime) else str(row[2]),
                        'EventId': row[3] if row[3] else None,
                        'Level': 'Information',
                        'Message': f"EventClass {row[3]}: {row[4] if len(row) > 4 else 'N/A'} | User: {row[0] if row[0] else 'N/A'} | Host: {row[1] if len(row) > 1 and row[1] else 'N/A'} | {row[5] if len(row) > 5 and row[5] else ''}",
                        'Source': f'Default Trace (EventClass {row[3] if row[3] else "N/A"})',
                        'LogName': 'SQL Default Trace',
                        'SourceType': 'DefaultTrace',
                        'LoginName': row[0] if row[0] else None,
                        'HostName': row[1] if len(row) > 1 and row[1] else None
                    })
            
            cursor.close()
            pool.return_connection(conn_info, conn)
            
            return logs
            
        except Exception as e:
            logger.error(f"Erro ao buscar Default Trace de {server}: {e}", exc_info=True)
            return []
    
    def _serialize_service(self, service: SQLServiceStatus) -> Dict:
        """Serializa um serviço para JSON (converte datetime)"""
        result = {
            'service_name': service.service_name,
            'display_name': service.display_name,
            'status': service.status,
            'start_mode': service.start_mode,
            'server': service.server,
            'instance': service.instance,
        }
        if service.last_check:
            result['last_check'] = service.last_check.isoformat()
        return result
    
    def check_server_services(self, server_id: str, all_services: bool = False) -> Dict:
        """Verifica serviços de um servidor pelo ID"""
        server, instance = self._parse_server_and_instance(server_id)
        
        services = self.get_sql_services(server, instance, all_services=all_services)
        
        # Agrupar por status
        running = [s for s in services if s.is_running]
        stopped = [s for s in services if not s.is_running]
        critical_down = [s for s in services if s.is_critical]
        
        return {
            'server': server,
            'instance': instance,
            'server_id': server_id,
            'total_services': len(services),
            'running_services': len(running),
            'stopped_services': len(stopped),
            'critical_down': len(critical_down),
            'is_healthy': len(critical_down) == 0,
            'services': [self._serialize_service(s) for s in services],
            'critical_services_down': [self._serialize_service(s) for s in critical_down],
            'last_check': datetime.now().isoformat()
        }
    
    def get_all_servers_services(self, server_ids: List[str]) -> Dict:
        """Verifica serviços de múltiplos servidores"""
        results = {}
        
        for server_id in server_ids:
            try:
                result = self.check_server_services(server_id)
                results[server_id] = result
            except Exception as e:
                logger.error(f"Erro ao verificar serviços de {server_id}: {e}")
                results[server_id] = {
                    'server_id': server_id,
                    'error': str(e),
                    'is_healthy': False
                }
        
        # Resumo geral
        total_servers = len(results)
        healthy_servers = len([r for r in results.values() if r.get('is_healthy', False)])
        servers_with_critical_down = len([r for r in results.values() if r.get('critical_down', 0) > 0])
        
        return {
            'total_servers': total_servers,
            'healthy_servers': healthy_servers,
            'servers_with_issues': total_servers - healthy_servers,
            'servers_with_critical_down': servers_with_critical_down,
            'servers': results
        }

