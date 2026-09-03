#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WatcherDB SQL Server Service Monitor
Verifica status dos serviços SQL Server via WMI/PowerShell

ESTRATÉGIA PLAN A/B:
- Plan A: PowerShell Remoto (Get-Service -ComputerName)
- Plan B: WMI via Python (wmi library)
- Plan C: WatcherDB Intelligence (fallback de dados históricos)
"""

import subprocess
import logging
import json
import base64
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

# Import do pool de conexões centralizado
from api.connection_pool import get_intelligence_pool

logger = logging.getLogger(__name__)


# ============================================================================
# PLANO A: PowerShell Remoto via Get-Service
# PLANO B: WMI via Python (fallback quando PowerShell falha)
# ============================================================================

def _wmi_get_sql_services(server: str, instance: Optional[str] = None, all_services: bool = False) -> List[Dict]:
    """
    PLANO B: Obtém serviços SQL Server via WMI (Python).
    Funciona quando PowerShell remoto está bloqueado mas WMI/DCOM está liberado.
    """
    try:
        import wmi

        # Conectar ao servidor remoto via WMI
        conn = wmi.WMI(computer=server)

        services = []

        # Buscar serviços Windows via Win32_Service
        for svc in conn.Win32_Service():
            try:
                name = svc.Name or ''
                display_name = svc.DisplayName or ''

                # Filtrar apenas serviços SQL-related
                is_sql_service = (
                    name.upper().startswith('MSSQL') or
                    name.upper().startswith('SQLSERVER') or
                    name.upper().startswith('SQL') or
                    'SQL Server' in display_name
                )

                if not is_sql_service and not all_services:
                    continue

                # Se temos uma instância específica, filtrar
                if instance and instance.upper() != 'DEFAULT':
                    instance_clean = instance.replace('\\', '').replace('$', '').upper()
                    if instance_clean not in name.upper() and 'MSSQLSERVER' not in name.upper():
                        continue

                services.append({
                    'Name': name,
                    'DisplayName': display_name,
                    'Status': svc.State or 'Unknown',  # Running, Stopped, etc.
                    'StartType': svc.StartMode or 'Unknown',  # Auto, Manual, Disabled
                    'Method': 'WMI'
                })
            except Exception:
                continue

        logger.info(f"✅ [Services] Plano B (WMI) encontrou {len(services)} serviços em {server}")
        return services

    except Exception as e:
        logger.warning(f"❌ [Services] Plano B (WMI) falhou para {server}: {str(e)[:100]}")
        return []


def _powershell_get_sql_services(server: str, instance: Optional[str] = None,
                                  all_services: bool = False, timeout: int = 8) -> Tuple[List[Dict], Optional[str]]:
    """
    PLANO A: Obtém serviços SQL Server via PowerShell remoto.
    Retorna (lista_de_serviços, erro_se_houver)
    """
    try:
        # Montar patterns de serviços
        service_patterns = []
        if instance and instance.upper() != 'DEFAULT':
            instance_clean = instance.replace('\\', '').replace('$', '')
            service_patterns = [
                f"MSSQL${instance_clean}",
                f"SQLSERVERAGENT${instance_clean}",
                f"MSSQLSERVER",
                f"SQLSERVERAGENT"
            ]
        else:
            service_patterns = ["MSSQLSERVER", "SQLSERVERAGENT"]

        if all_services:
            # Script para buscar TODOS os serviços SQL
            remote_script = '''
$ErrorActionPreference='SilentlyContinue'
$services = @()
$allServices = Get-Service | Where-Object {
    $_.Name -like 'MSSQL*' -or
    $_.Name -like 'SQLSERVER*' -or
    $_.Name -like 'SQL*Agent*' -or
    $_.DisplayName -like '*SQL Server*'
}
foreach ($svc in $allServices) {
    $services += @{
        Name = $svc.Name
        DisplayName = $svc.DisplayName
        Status = $svc.Status.ToString()
        StartType = $svc.StartType.ToString()
    }
}
$services | ConvertTo-Json -Compress
'''
        else:
            # Script para serviços específicos
            patterns_str = ', '.join([f"'{p}'" for p in service_patterns])
            remote_script = f'''
$ErrorActionPreference='SilentlyContinue'
$services = @()
$patterns = @({patterns_str})
foreach ($pattern in $patterns) {{
    try {{
        $svc = Get-Service -Name $pattern -ErrorAction SilentlyContinue
        if ($svc) {{
            $services += @{{
                Name = $svc.Name
                DisplayName = $svc.DisplayName
                Status = $svc.Status.ToString()
                StartType = $svc.StartType.ToString()
            }}
        }}
    }} catch {{ }}
}}
$services | ConvertTo-Json -Compress
'''

        # Usar Invoke-Command com EncodedCommand para evitar problemas de escape
        local_script = f'Invoke-Command -ComputerName {server} -ScriptBlock {{ {remote_script} }}'
        encoded = base64.b64encode(local_script.encode('utf-16-le')).decode('ascii')
        cmd = f'powershell -NoProfile -EncodedCommand {encoded}'

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            error_msg = result.stderr[:200] if result.stderr else 'PS error'
            return [], error_msg

        output = result.stdout.strip()
        if not output or output == '[]':
            return [], 'Empty response'

        if output.startswith('{') or output.startswith('['):
            services_data = json.loads(output)
            if not isinstance(services_data, list):
                services_data = [services_data]

            for svc in services_data:
                svc['Method'] = 'PowerShell'

            logger.info(f"✅ [Services] Plano A (PowerShell) encontrou {len(services_data)} serviços em {server}")
            return services_data, None

        return [], 'Invalid response'

    except subprocess.TimeoutExpired:
        return [], f'PS Timeout ({timeout}s)'
    except json.JSONDecodeError as e:
        return [], f'JSON error: {str(e)[:50]}'
    except Exception as e:
        return [], str(e)[:100]

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
        """
        Retorna True se é um serviço crítico e está parado.
        
        Serviços críticos:
        - SQL Server: MSSQLSERVER (instância padrão) ou MSSQL$* (instâncias nomeadas)
        - SQL Agent: SQLSERVERAGENT (instância padrão) ou SQLAgent$* (instâncias nomeadas)
        
        Um serviço crítico parado é considerado crítico.
        """
        service_upper = self.service_name.upper()
        
        # Verificar se é SQL Server (MSSQLSERVER ou MSSQL$*)
        is_sql_server = (
            service_upper == 'MSSQLSERVER' or 
            service_upper.startswith('MSSQL$')
        )
        
        # Verificar se é SQL Agent (SQLSERVERAGENT ou SQLAgent$*)
        is_sql_agent = (
            service_upper == 'SQLSERVERAGENT' or 
            service_upper.startswith('SQLAGENT$')
        )
        
        # Se é um serviço crítico E está parado, então é crítico
        if (is_sql_server or is_sql_agent) and not self.is_running:
            return True
        
        return False

class SQLServiceMonitor:
    """Monitor de serviços SQL Server"""

    # Configuração de conexão com WatcherDB Intelligence
    WATCHERDB_CONNECTION_STRING = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=SQLHDSTST505\\I01;'
        'DATABASE=WatcherDB_Intelligence;'
        'Trusted_Connection=yes;'
        'Connection Timeout=10;'
    )

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

    def get_services_from_watcherdb(self, server: str, instance: Optional[str] = None) -> List[SQLServiceStatus]:
        """
        Busca serviços SQL Server do WatcherDB Intelligence.
        Retorna lista vazia se não houver dados.
        """
        pool = None
        conn = None
        try:
            # Montar nome da instância para busca
            if instance:
                instance_pattern = f"{server}\\{instance}"
                instance_pattern_alt = f"{server}_{instance}"
            else:
                instance_pattern = server
                instance_pattern_alt = f"{server}_DEFAULT"

            pool = get_intelligence_pool()
            conn = pool.get_connection()
            cursor = conn.cursor()

            # Primeiro, verificar na view de serviços down (que indica problemas ativos)
            query_down = """
            SELECT
                Instance,
                Services_Down_Count,
                Services_Down_List,
                Last_Check
            FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
            WHERE Instance LIKE ? OR Instance LIKE ?
            """

            cursor.execute(query_down, (f"{instance_pattern}%", f"{instance_pattern_alt}%"))
            down_rows = cursor.fetchall()

            services = []

            # Verificar se há serviços down registrados
            if down_rows:
                for row in down_rows:
                    if row[1] and row[1] > 0:  # Services_Down_Count > 0
                        services_list = row[2] if row[2] else ""
                        for svc_name in services_list.split(','):
                            svc_name = svc_name.strip()
                            if svc_name:
                                service = SQLServiceStatus(
                                    service_name=svc_name,
                                    display_name=svc_name,
                                    status='Stopped',
                                    start_mode='Automatic',  # Assumir automático para serviços críticos
                                    server=server,
                                    instance=instance,
                                    last_check=row[3] if row[3] else datetime.now()
                                )
                                services.append(service)

            # Tentar também buscar da view detalhada se existir
            try:
                query_det = """
                SELECT
                    Instance,
                    Service_Name,
                    Service_Display_Name,
                    Service_State,
                    Start_Mode,
                    Update_TS
                FROM dbo.KPI_MSSQL_SERVICE_STATUS_DET_VIEW WITH (NOLOCK)
                WHERE Instance LIKE ? OR Instance LIKE ?
                ORDER BY Update_TS DESC
                """
                cursor.execute(query_det, (f"{instance_pattern}%", f"{instance_pattern_alt}%"))
                det_rows = cursor.fetchall()

                # Se temos dados detalhados, usar esses em vez dos agregados
                if det_rows:
                    services = []  # Limpar lista anterior
                    for row in det_rows:
                        service = SQLServiceStatus(
                            service_name=row[1] if row[1] else 'Unknown',
                            display_name=row[2] if row[2] else row[1] if row[1] else 'Unknown',
                            status=row[3] if row[3] else 'Unknown',
                            start_mode=row[4] if row[4] else 'Unknown',
                            server=server,
                            instance=instance,
                            last_check=row[5] if row[5] else datetime.now()
                        )
                        services.append(service)
            except Exception as e:
                logger.debug(f"View detalhada não disponível: {e}")

            cursor.close()

            if services:
                logger.info(f"Encontrados {len(services)} serviços do WatcherDB para {instance_pattern}")

            return services

        except Exception as e:
            logger.debug(f"WatcherDB não disponível para serviços: {e}")
            return []
        finally:
            if conn and pool:
                pool.return_connection(conn)
    
    def get_sql_services(self, server: str, instance: Optional[str] = None, all_services: bool = False) -> List[SQLServiceStatus]:
        """
        Obtém status dos serviços SQL Server de um servidor.

        Estratégia de fallback (Plan A/B/C):
        1. Plan A: PowerShell remoto (Get-Service via Invoke-Command)
        2. Plan B: WMI via Python (wmi library)
        3. Plan C: WatcherDB Intelligence (dados históricos)
        """
        services = []

        # === PLANO A: PowerShell Remoto ===
        logger.info(f"📡 [Services] Plano A: PowerShell para {server}")
        ps_services, ps_error = _powershell_get_sql_services(server, instance, all_services)

        if ps_services:
            for svc_data in ps_services:
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
            logger.info(f"✅ [Services] Plano A funcionou para {server}: {len(services)} serviços")
            return services

        # === PLANO B: WMI via Python ===
        logger.info(f"📡 [Services] Plano B: WMI para {server} (PowerShell falhou: {ps_error})")
        wmi_services = _wmi_get_sql_services(server, instance, all_services)

        if wmi_services:
            for svc_data in wmi_services:
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
            logger.info(f"✅ [Services] Plano B (WMI) funcionou para {server}: {len(services)} serviços")
            return services

        # === PLANO C: WatcherDB Intelligence ===
        logger.info(f"📡 [Services] Plano C: WatcherDB para {server} (WMI também falhou)")
        services = self.get_services_from_watcherdb(server, instance)

        if services:
            logger.info(f"✅ [Services] Plano C (WatcherDB) funcionou para {server}: {len(services)} serviços")
            return services

        # === Nenhuma fonte de dados disponível ===
        logger.warning(
            f"❌ [Services] Todos os planos falharam para {server}: "
            f"PS={ps_error}, WMI=falhou, WatcherDB=sem dados"
        )

        return services
    
    def get_service_logs(self, server: str, service_name: str, hours: int = 24, instance: Optional[str] = None) -> List[Dict]:
        """Obtém logs de eventos do Windows relacionados a um serviço

        Estratégia (em ordem de prioridade):
        1. Primeiro tenta SQL Error Log direto via xp_readerrorlog - mais rápido e confiável
        2. Depois Default Trace para eventos Server Stop/Start
        3. WatcherDB (tabela KPI_MSSQL_ERRORLOG_STG) - se disponível
        4. PowerShell remoto (Event Viewer) - último recurso, mais lento
        """
        all_logs = []

        # 1. SQL Error Log direto via xp_readerrorlog (mais rápido e confiável)
        try:
            sql_error_logs = self.get_sql_error_logs(server, instance, hours)
            if sql_error_logs:
                all_logs.extend(sql_error_logs)
                logger.info(f"Encontrados {len(sql_error_logs)} logs do SQL Error Log para {server}")
        except Exception as e:
            logger.debug(f"SQL Error Log não disponível: {e}")

        # 2. Default Trace para eventos Server Stop/Start
        try:
            default_trace_logs = self.get_default_trace_logs(server, instance, hours)
            if default_trace_logs:
                all_logs.extend(default_trace_logs)
                logger.info(f"Encontrados {len(default_trace_logs)} logs do Default Trace para {server}")
        except Exception as e:
            logger.debug(f"Default Trace não disponível: {e}")

        # 3. Tentar buscar do WatcherDB (tabela centralizada)
        watcherdb_logs = self._get_logs_from_watcherdb(server, service_name, hours, instance)
        if watcherdb_logs:
            all_logs.extend(watcherdb_logs)

        # 4. Se ainda não encontrou nada, tentar via PowerShell remoto (último recurso)
        if not all_logs:
            try:
                remote_logs = self._get_logs_from_event_viewer(server, service_name, hours)
                all_logs.extend(remote_logs)
            except Exception as e:
                logger.warning(f"PowerShell remoto falhou: {e}")

        # Remover duplicatas baseado em TimeCreated + Message
        seen = set()
        unique_logs = []
        for log in all_logs:
            key = (log.get('TimeCreated', ''), log.get('Message', '')[:100])
            if key not in seen:
                seen.add(key)
                unique_logs.append(log)

        return unique_logs

    def _get_logs_from_watcherdb(self, server: str, service_name: str, hours: int = 24, instance: Optional[str] = None) -> List[Dict]:
        """Busca logs do SQL Server Error Log armazenados no WatcherDB"""
        pool = None
        conn = None
        try:
            # Montar nome da instância para busca
            instance_pattern = f"{server}"
            if instance:
                instance_pattern = f"{server}_{instance}"

            pool = get_intelligence_pool()
            conn = pool.get_connection()
            cursor = conn.cursor()

            # Buscar logs de erro do SQL Server da tabela centralizada
            query = """
            SELECT TOP 100
                Instance,
                Log_Date,
                Process_Info,
                Log_Text,
                Log_Type,
                Error_Number,
                Severity
            FROM dbo.KPI_MSSQL_ERRORLOG_STG
            WHERE Instance LIKE ?
              AND Log_Date >= DATEADD(HOUR, ?, GETDATE())
              AND (Log_Text LIKE '%service%'
                   OR Log_Text LIKE '%shutdown%'
                   OR Log_Text LIKE '%starting%'
                   OR Log_Text LIKE '%stopped%'
                   OR Log_Text LIKE '%error%'
                   OR Severity >= 16)
            ORDER BY Log_Date DESC
            """

            cursor.execute(query, (f"{instance_pattern}%", -hours))
            rows = cursor.fetchall()

            logs = []
            for row in rows:
                logs.append({
                    'TimeCreated': row[1].isoformat() if row[1] else '',
                    'EventId': row[5] if row[5] else None,
                    'Level': 'Error' if row[6] and row[6] >= 16 else 'Warning' if row[6] and row[6] >= 10 else 'Information',
                    'Message': row[3] if row[3] else '',
                    'Source': f'SQL Server Error Log ({row[2] if row[2] else "N/A"})',
                    'LogName': 'SQL Error Log',
                    'SourceType': 'WatcherDB'
                })

            cursor.close()

            if logs:
                logger.info(f"Encontrados {len(logs)} logs do WatcherDB para {instance_pattern}")

            return logs

        except Exception as e:
            logger.debug(f"WatcherDB não disponível ou sem dados: {e}")
            return []
        finally:
            if conn and pool:
                pool.return_connection(conn)

    def _get_logs_from_event_viewer(self, server: str, service_name: str, hours: int = 24) -> List[Dict]:
        """Obtém logs de eventos do Windows Event Viewer via PowerShell remoto"""
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

            pool = ConnectionPool(max_connections=15)
            conn = pool.get_connection(conn_info)
            if not conn:
                logger.warning(f"Não foi possível conectar em {server} para buscar SQL Error Log")
                return []

            cursor = conn.cursor()
            logs = []

            # Calcular data limite
            since_date = datetime.now() - timedelta(hours=hours)
            since_str = since_date.strftime('%Y-%m-%d %H:%M:%S')

            # Ler arquivos de error log (0 = atual, 1-3 = anteriores)
            for file_number in range(4):
                try:
                    # xp_readerrorlog: file_number, log_type(1=SQL), search1, search2, start_date, end_date
                    cursor.execute("EXEC xp_readerrorlog ?, 1, NULL, NULL, ?, NULL", (file_number, since_str))
                    rows = cursor.fetchall()

                    for row in rows:
                        log_text = row[2] if len(row) > 2 and row[2] else ''
                        # Filtrar apenas eventos relevantes
                        if any(keyword in log_text.lower() for keyword in ['shutdown', 'starting', 'stopped', 'terminating', 'service']):
                            logs.append({
                                'TimeCreated': row[0].isoformat() if isinstance(row[0], datetime) else str(row[0]),
                                'EventId': None,
                                'Level': 'Information',
                                'Message': log_text,
                                'Source': f'SQL Server Error Log ({row[1] if len(row) > 1 else "N/A"})',
                                'LogName': 'SQL Error Log',
                                'SourceType': 'SQLErrorLog'
                            })
                except Exception as e:
                    # Ignorar erro se arquivo não existir
                    logger.debug(f"Error log file {file_number} não disponível: {e}")
                    continue

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

            pool = ConnectionPool(max_connections=15)
            conn = pool.get_connection(conn_info)
            if not conn:
                logger.warning(f"Não foi possível conectar em {server} para buscar Default Trace")
                return []

            # Query simplificada para buscar eventos Server Stop/Start do Default Trace
            query = f"""
            DECLARE @TracePath NVARCHAR(260)
            SELECT @TracePath = path
            FROM sys.traces
            WHERE is_default = 1

            IF @TracePath IS NOT NULL
            BEGIN
                SELECT
                    LoginName,
                    HostName,
                    StartTime,
                    EventClass,
                    CASE EventClass
                        WHEN 46 THEN 'Server Start'
                        WHEN 47 THEN 'Server Stop'
                        ELSE 'Unknown'
                    END as EventDescription,
                    TextData
                FROM sys.fn_trace_gettable(@TracePath, DEFAULT)
                WHERE EventClass IN (46, 47)  -- Server Start (46) e Server Stop (47)
                  AND StartTime >= DATEADD(HOUR, -{hours}, GETDATE())
                ORDER BY StartTime DESC
            END
            ELSE
            BEGIN
                SELECT NULL as LoginName, NULL as HostName, NULL as StartTime, NULL as EventClass, NULL as EventDescription, NULL as TextData WHERE 1=0
            END
            """

            cursor = conn.cursor()
            cursor.execute(query)
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
            'is_critical': service.is_critical,
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

        # Se não conseguiu obter dados, indicar que é indisponível (não um erro)
        data_available = len(services) > 0

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
            'last_check': datetime.now().isoformat(),
            'data_available': data_available,
            'message': None if data_available else (
                'Dados de serviços indisponíveis. '
                'Acesso remoto ao SCM bloqueado e WatcherDB sem dados para este servidor.'
            )
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

