# ============================================================================
# WatcherDB LOGS COLLECTOR - Coleta de Logs do Windows e SQL Server
# ============================================================================
# Implementação completa baseada nos comandos PowerShell fornecidos
#
# ESTRATÉGIA PLAN A/B:
# - Plan A: PowerShell Remoto (Get-WinEvent via Invoke-Command)
# - Plan B: WMI via Python (Win32_NTLogEvent)
# ============================================================================

import subprocess
import json
import logging
import base64
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re

logger = logging.getLogger(__name__)


# ============================================================================
# PLANO B: WMI para coleta de eventos Windows
# ============================================================================

# Whitelist of valid Windows Event Log names (Application/System/Security são suportados via WMI;
# canais Microsoft-Windows-* só funcionam via PowerShell Get-WinEvent — Plan A).
VALID_LOG_NAMES = {"Application", "System", "Security"}

# Regex de validação genérica para log_name (previne WQL injection mas permite canais Microsoft-Windows-*)
import re as _re_log
_VALID_LOG_NAME_PATTERN = _re_log.compile(r'^[A-Za-z0-9/_\-]+$')


def _wmi_get_windows_events(server_name: str, log_name: str = 'System',
                             event_ids: List[int] = None, hours: int = 24,
                             max_events: int = 100) -> List[Dict]:
    """
    PLANO B: Obtém eventos do Windows Event Log via WMI (Python).
    Funciona quando PowerShell remoto está bloqueado mas WMI/DCOM está liberado.
    NOTA: WMI Win32_NTLogEvent só suporta Application/System/Security.
    Para canais Microsoft-Windows-*/Operational, este método devolve [] e o caller deve usar Plan A.
    """
    try:
        import wmi
        from datetime import datetime, timedelta

        # WMI Win32_NTLogEvent só suporta os canais clássicos.
        if log_name not in VALID_LOG_NAMES:
            logger.info(f"[Logs/WMI] '{log_name}' não suportado por WMI (só Plan A PowerShell pode ler este canal)")
            return []

        # Conectar ao servidor remoto via WMI
        conn = wmi.WMI(computer=server_name)

        # Calcular data limite (WMI usa formato diferente)
        since_date = datetime.now() - timedelta(hours=hours)
        wmi_date = since_date.strftime('%Y%m%d%H%M%S.000000-000')

        events = []

        # Query WMI para eventos
        # Win32_NTLogEvent: Logfile, EventCode, TimeGenerated, Message, Type, SourceName
        query = f"SELECT * FROM Win32_NTLogEvent WHERE Logfile = '{log_name}' AND TimeGenerated >= '{wmi_date}'"

        for event in conn.query(query):
            try:
                # Filtrar por Event IDs se especificado
                if event_ids and int(event.EventCode) not in event_ids:
                    continue

                # Parsear data do WMI (formato: 20240115123456.000000-000)
                time_str = str(event.TimeGenerated).split('.')[0] if event.TimeGenerated else ''
                try:
                    time_created = datetime.strptime(time_str, '%Y%m%d%H%M%S').isoformat() if time_str else ''
                except (ValueError, TypeError):
                    time_created = str(event.TimeGenerated) if event.TimeGenerated else ''

                events.append({
                    'TimeCreated': time_created,
                    'Id': int(event.EventCode) if event.EventCode else 0,
                    'LevelDisplayName': event.Type or 'Unknown',
                    'ProviderName': event.SourceName or 'Unknown',
                    'Message': (event.Message or '')[:500],  # Limitar tamanho
                    'LogName': log_name,
                    'Method': 'WMI'
                })

                if len(events) >= max_events:
                    break

            except Exception:
                continue

        logger.info(f"✅ [Logs] Plano B (WMI) encontrou {len(events)} eventos em {server_name}")
        return events

    except Exception as e:
        logger.warning(f"❌ [Logs] Plano B (WMI) falhou para {server_name}: {str(e)[:100]}")
        return []


class WindowsLogsCollector:
    """
    Coletor de logs do Windows usando PowerShell remoto/local
    FOCO: Problemas que afetam SQL Server, Always On e Backups
    """

    # Event IDs - DISK ERRORS (afetam SQL Server, Always On e Backups)
    DISK_ERROR_EVENT_IDS = [
        7,      # The device has a bad block
        9,      # Bad sector on disk
        11,     # The driver detected a controller error
        15,     # The device is not ready
        51,     # An error was detected on device during a paging operation
        52,     # The driver detected an internal driver error
        55,     # The file system structure on the disk is corrupt
        98,     # Storage device timeout
        129,    # Reset to device was issued
        153,    # Disk timeout
        154,    # Disk timeout
        157,    # Disk bad block
        2013,   # Volume corruption detected
        2018,   # Volume corruption detected
        2020,   # Lost delayed-write data
    ]

    # Event IDs - ALWAYS ON AVAILABILITY GROUPS (críticos para failover)
    ALWAYSON_EVENT_IDS = [
        # Always On - Failover e Sincronização
        1480,   # AG role change (CRÍTICO - failover detectado)
        35201,  # Connection to AG listener failed
        35202,  # Connection to AG failed
        35204,  # AG database connectivity
        35206,  # AG listener connectivity
        35264,  # AG data movement suspended
        35265,  # AG data movement resumed
        35274,  # AG database synchronization stopped
        41075,  # AG synchronization health changed (CRÍTICO)
        41142,  # AG lease timeout (CRÍTICO - pode causar failover)
        41144,  # AG database not in sync
        19406,  # AG role change notification
        19407,  # AG failover completed
        19421,  # AG synchronization state changed
        19422,  # AG failover detected
        1135,   # Cluster node removed (afeta AG)
        1146,   # Cluster network interface failed (afeta AG)
    ]

    # Event IDs - SQL SERVER ERRORS (afetam operação geral, backups e AG)
    SQL_SERVER_CRITICAL_IDS = [
        # Erros de I/O e Corrupção (afetam TUDO)
        823,    # I/O error (CRÍTICO - pode corromper backups e AG)
        824,    # Logical I/O error (CRÍTICO)
        825,    # Read-retry success (aviso de problema de disco)
        832,    # Constant page read error (corrupção)
        833,    # SQL I/O request took longer than 15 seconds

        # Erros de Espaço (afetam backups e AG)
        1105,   # Could not allocate space (CRÍTICO - afeta backups)
        9002,   # Transaction log full (CRÍTICO - afeta AG sync e backups)
        1101,   # Could not allocate new page
        5242,   # Inconsistency detected during upgrade

        # Erros de Backup
        3041,   # BACKUP failed to complete
        3013,   # BACKUP DATABASE is terminating abnormally
        3271,   # Nonrecoverable I/O error during backup
        18204,  # BackupDiskFile::CreateMedia failure
        18210,  # BackupMedium::ReportIoError failure

        # Erros Críticos de Sistema
        17053,  # Operating system error (pode afetar tudo)
        17204,  # Unable to open Windows event log
        17207,  # Could not expand full-text index
        17300,  # SQL Server cannot start
        845,    # Time-out waiting for buffer latch
        1204,   # Deadlock detected

        # Erros de Conexão e Rede (afetam AG)
        17806,  # SSPI handshake failed
        18456,  # Login failed (monitorar ataques)
    ]

    # Event IDs - SHUTDOWN/RESTART (afetam disponibilidade do SQL Server)
    SHUTDOWN_EVENT_IDS = [
        1074,   # System shutdown/restart initiated (CRÍTICO)
        6006,   # Event log service stopped (shutdown)
        6008,   # Unexpected shutdown (CRÍTICO - pode corromper dados)
        6005,   # Event log service started (após reboot)
        41,     # Kernel-Power - System rebooted without cleanly shutting down
        1076,   # Shutdown reason
        6013,   # System uptime
    ]

    # Event IDs - BACKUP RELACIONADOS (VSS, Backup Software)
    BACKUP_EVENT_IDS = [
        8193,   # Volume Shadow Copy Service error (afeta backups)
        8194,   # Volume Shadow Copy Service warning
        12292,  # VSS writer failure
        12293,  # VSS snapshot creation failed
        8224,   # VSS insufficient resources
        8230,   # VSS timeout
    ]

    # Event IDs - CLUSTER (afetam Always On)
    CLUSTER_EVENT_IDS = [
        1006,   # Cluster resource failed
        1069,   # Cluster resource failed (CRÍTICO para AG)
        1135,   # Cluster node removed (CRÍTICO para AG)
        1146,   # Cluster network interface failed (afeta AG)
        1177,   # Quorum witness failed
        1230,   # Cluster network failure
        1244,   # Cluster resource online failed
        1573,   # Cluster service started
    ]

    # Event IDs - CLUSTER SHARED VOLUME / STORAGE (CRÍTICO - afetam I/O do SQL Server e backups)
    # Capturam erros como "Shared Volume IO is paused" / STATUS_IO_TIMEOUT(c00000b5)
    CSV_STORAGE_EVENT_IDS = [
        5120,   # Cluster Shared Volume não está mais disponível (CRÍTICO)
        5121,   # CSV ficou offline
        5125,   # CSV identificou filter drivers ativos
        5142,   # CSV deixou de estar acessível (CRÍTICO - I/O paused)
        5145,   # CSV operação retornou status (inclui IO_TIMEOUT)
        5150,   # Cluster physical disk resource falhou
        5157,   # Cluster physical disk resource ficou offline
    ]

    # Padrões de texto para fallback (capturam variações sem depender só de Event IDs)
    CSV_STORAGE_TEXT_PATTERNS = [
        'Shared Volume IO is paused',
        'STATUS_IO_TIMEOUT',
        'c00000b5',
        'will temporarily be queued',
        'has entered a paused state',
    ]

    # Event IDs - SERVICE BROKER / DATABASE MIRRORING (afetam comunicacao entre instancias)
    SERVICE_BROKER_EVENT_IDS = [
        # Erros de Endpoint de Transporte (CRITICOS - capturados pelo SCOM)
        9642,   # Service Broker/Database Mirroring transport connection endpoint error
        8474,   # Error relacionado ao endpoint de transporte

        # Service Broker - Erros de Conexao
        9724,   # Service Broker dialog security error
        9736,   # Service Broker could not resolve the network address
        28054,  # Service Broker activation procedure failure
        28047,  # Service Broker queue disabled due to errors
        28051,  # Service Broker could not deliver message

        # Service Broker - Erros de Configuracao
        9649,   # Service Broker invalid configuration
        9655,   # Service Broker certificate error
        9666,   # Service Broker encryption error

        # Database Mirroring - Erros de Conexao
        1440,   # Database Mirroring connection error
        1441,   # Database Mirroring timeout
        1454,   # Database Mirroring partner not responding

        # Database Mirroring - Erros de Sincronizacao
        1456,   # Database Mirroring send failed
        1457,   # Database Mirroring synchronization interrupted
        1459,   # Database Mirroring error in data transfer

        # Erros de Endpoint (afetam ambos)
        1418,   # Endpoint could not be created
        1419,   # Endpoint configuration error
        9691,   # Endpoint listener error
        9693,   # Endpoint connection refused
    ]

    # Event IDs - MEMORY (pressão de memória do OS e SQL Server)
    MEMORY_EVENT_IDS = [
        # Windows Resource Exhaustion Detector (System Log)
        2004,   # Windows successfully diagnosed a low virtual memory condition
        2017,   # Resource exhaustion detected
        2019,   # A process consumed a large amount of memory
        2020,   # A process ran out of memory

        # Memory Manager (System Log)
        333,    # An I/O operation initiated by the Registry failed unrecoverably

        # Application Pool Memory (Application Log - IIS/WAS)
        5117,   # A worker process serving application pool exceeded memory limit

        # SQL Server Memory Events (Application Log)
        701,    # There is insufficient system memory in resource pool
        802,    # There is insufficient memory available in the buffer pool
        8628,   # A time out occurred while waiting for memory resources
        8645,   # A time out occurred while waiting for memory resources to execute the query

        # SQL Server Memory Pressure
        17890,  # A significant part of sql server process memory has been paged out
        17891,  # Resource Monitor memory notification: There is insufficient memory available

        # SQL Server Buffer Pool
        832,    # A page that should have been constant has changed
        833,    # SQL Server has encountered N occurrence(s) of I/O requests taking longer than 15 seconds

        # Low Memory Condition
        6511,   # Failed to open COM object due to memory issue
        6521,   # COM object creation failed due to memory

        # Virtual Address Space
        855,    # Uncorrectable hardware memory corruption detected
        856,    # SQL Server has detected hardware memory corruption

        # General Memory Events
        1069,   # An allocation of protected memory failed (possible memory corruption)
        26,     # SQL Server cannot start because the memory configuration is invalid
    ]

    def __init__(self):
        self.timeout = 30  # Timeout para comandos PowerShell (reduzido de 120s para 30s)
        self.cache = {}  # Cache de resultados
        self.cache_ttl = 300  # TTL de 5 minutos
        self.max_workers = 4  # Número de categorias processadas em paralelo

    def _get_cache_key(self, server_id: str, hours: int, categories: List[str]) -> str:
        """Gera chave de cache"""
        return f"{server_id}_{hours}_{','.join(sorted(categories))}"

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Recupera do cache se válido"""
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            age = time.time() - cached_time
            if age < self.cache_ttl:
                logger.info(f"Cache HIT: {cache_key} (idade: {age:.1f}s)")
                return cached_data
            else:
                logger.info(f"Cache EXPIRED: {cache_key} (idade: {age:.1f}s)")
                del self.cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any]):
        """Salva no cache"""
        self.cache[cache_key] = (data, time.time())
        logger.info(f"Cache SAVED: {cache_key}")

        # Limpar cache antigo (manter apenas últimos 50 itens)
        if len(self.cache) > 50:
            oldest_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k][1])[:25]
            for key in oldest_keys:
                del self.cache[key]
            logger.info(f"Cache cleanup: removidos {len(oldest_keys)} itens antigos")

    def _get_server_hostname(self, server_id: str) -> str:
        """Extrai o hostname do server_id"""
        # Formato: SQLHDSPRD001_I0001 -> SQLHDSPRD001
        return server_id.split('_')[0] if '_' in server_id else server_id

    def _execute_powershell_remote(self, server_name: str, script: str) -> Tuple[bool, str, str]:
        """
        PLANO A: Executa PowerShell remoto via WinRM com EncodedCommand.
        Usa Base64 encoding para evitar problemas de escape.
        """
        try:
            # Usar EncodedCommand para evitar problemas de escape
            local_script = f'Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {script} }}'
            encoded = base64.b64encode(local_script.encode('utf-16-le')).decode('ascii')
            cmd = f'powershell -NoProfile -EncodedCommand {encoded}'

            completed = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return completed.returncode == 0, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired:
            logger.warning(f"⏱️ [Logs] Plano A Timeout ({self.timeout}s) em {server_name}")
            return False, "", f"Timeout ({self.timeout}s)"
        except Exception as e:
            logger.error(f"❌ [Logs] Plano A erro em {server_name}: {e}")
            return False, "", str(e)
    
    def _execute_powershell_local(self, script: str) -> Tuple[bool, str, str]:
        """Executa PowerShell local (fallback)"""
        try:
            cmd = ["powershell", "-NoProfile", "-Command", script]
            completed = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.timeout
            )
            return completed.returncode == 0, completed.stdout, completed.stderr
        except Exception as e:
            logger.error(f"Erro ao executar PowerShell local: {e}")
            return False, "", str(e)
    
    def _build_event_query_script(
        self, 
        event_ids: List[int], 
        hours: int,
        log_name: str = 'System',
        provider_name: Optional[str] = None,
        max_events: int = 1000
    ) -> str:
        """Constrói script PowerShell para buscar eventos"""
        event_ids_str = ','.join(map(str, event_ids))
        start_time = f"(Get-Date).AddHours(-{hours})"
        
        filter_parts = [
            f"LogName = '{log_name}'",
            f"ID = {event_ids_str}",
            f"StartTime = {start_time}"
        ]
        
        if provider_name:
            filter_parts.append(f"ProviderName = '{provider_name}'")
        
        filter_hash = '{' + '; '.join(filter_parts) + '}'
        
        # Fallback chain para Message:
        #   1. $_.Message — usa o provider message file (pode ser $null para
        #      drivers como storvsc cujo message file nao esta acessivel)
        #   2. $_.FormatDescription() — forca o lookup; falha silenciosa em try
        #   3. $_.Properties como string — ultimo recurso, mostra os args raw
        # Sem este fallback, eventos com Message=null ficam '' no JSON e o
        # frontend mostra "N/A" para o storvsc 129, ntfs 55, etc.
        script = f"""
$ErrorActionPreference='SilentlyContinue'
try {{
    $events = Get-WinEvent -FilterHashtable @{filter_hash} -ErrorAction SilentlyContinue -MaxEvents {max_events}
    $result = $events | Select-Object @{{
        n='TimeCreated'; e={{$_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')}}
    }}, @{{
        n='Id'; e={{$_.Id}}
    }}, @{{
        n='LevelDisplayName'; e={{$_.LevelDisplayName}}
    }}, @{{
        n='ProviderName'; e={{$_.ProviderName}}
    }}, @{{
        n='Message'; e={{
            if ($_.Message) {{ $_.Message }}
            else {{
                $fmt = $null
                try {{ $fmt = $_.FormatDescription() }} catch {{}}
                if ($fmt) {{ $fmt }}
                else {{
                    try {{
                        $props = ($_.Properties | ForEach-Object {{ if ($_.Value -ne $null) {{ $_.Value.ToString() }} else {{ '' }} }}) -join ' | '
                        if ($props -and $props.Length -gt 0) {{ "[Event $($_.Id) from $($_.ProviderName)] Properties: $props" }}
                        else {{ "[Event $($_.Id) from $($_.ProviderName)] (sem mensagem - provider message file indisponivel)" }}
                    }} catch {{
                        "[Event $($_.Id) from $($_.ProviderName)] (erro ao extrair detalhes)"
                    }}
                }}
            }}
        }}
    }}, @{{
        n='LogName'; e={{$_.LogName}}
    }}
    $result | ConvertTo-Json -Depth 3
}} catch {{
    Write-Output '[]'
}}
"""
        return script
    
    def _collect_category_events(
        self,
        server_name: str,
        category: str,
        event_ids: List[int],
        log_name: str,
        provider: Optional[str],
        hours: int
    ) -> List[Dict[str, Any]]:
        """
        Coleta eventos de uma única categoria com fallback Plan A/B.

        ESTRATÉGIA:
        - Plan A: PowerShell remoto (Get-WinEvent)
        - Plan B: WMI via Python (Win32_NTLogEvent)
        """
        try:
            # === PLANO A: PowerShell Remoto ===
            logger.info(f"📡 [Logs/{category}] Plano A: PowerShell para {server_name}")
            script = self._build_event_query_script(
                event_ids, hours, log_name, provider, max_events=200
            )

            success, stdout, stderr = self._execute_powershell_remote(server_name, script)
            logger.info(
                f"[Logs/{category}] Plano A status: success={success} stdout_len={len(stdout) if stdout else 0} "
                f"stderr={(stderr or '')[:200]}"
            )

            # IMPORTANTE: stdout vazio NAO e' falha — e' "0 eventos" (ConvertTo-Json
            # nao escreve nada quando $result e' $null). So caimos para Plano B em
            # falha real: returncode != 0 OU JSON invalido. Isto evita 5 categorias
            # vazias x 30s timeout do Plano B = 2-3 minutos desperdicados.
            if success:
                try:
                    raw = stdout.strip() or '[]'
                    events = json.loads(raw)
                    if isinstance(events, dict):
                        events = [events]
                    for event in events:
                        event['category'] = category
                        event['event_type'] = self._classify_event_type(event.get('Id', 0))
                        event['Method'] = 'PowerShell'
                    logger.info(f"✅ [Logs/{category}] Plano A funcionou: {len(events)} eventos")
                    return events
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️ [Logs/{category}] Plano A JSON error: {e} — caindo para Plano B")
                    # cai para Plan B abaixo

            # === PLANO B: WMI via Python ===
            logger.info(f"📡 [Logs/{category}] Plano B: WMI para {server_name} (PS falhou: {stderr[:50] if stderr else 'N/A'})")
            wmi_events = _wmi_get_windows_events(
                server_name,
                log_name=log_name,
                event_ids=event_ids,
                hours=hours,
                max_events=200
            )

            if wmi_events:
                for event in wmi_events:
                    event['category'] = category
                    event['event_type'] = self._classify_event_type(event.get('Id', 0))
                logger.info(f"✅ [Logs/{category}] Plano B (WMI) funcionou: {len(wmi_events)} eventos")
                return wmi_events

            logger.warning(f"❌ [Logs/{category}] Ambos planos falharam para {server_name}")
            return []

        except Exception as e:
            logger.error(f"❌ [Logs/{category}] Erro geral: {e}")
            return []

    def _collect_csv_text_search(self, server_name: str, hours: int) -> List[Dict[str, Any]]:
        """
        Rede de segurança: pesquisa System log por texto, captura erros CSV mesmo
        quando o Event ID não está na lista (Microsoft pode mudar IDs entre versões).
        Patterns: 'Shared Volume IO is paused', 'STATUS_IO_TIMEOUT', 'c00000b5'.
        """
        # Construir filtro PowerShell — escapa cada padrão e usa OR
        patterns_ps = ' -or '.join(
            [f'$_.Message -match \'{p}\'' for p in self.CSV_STORAGE_TEXT_PATTERNS]
        )
        script = f"""
$ErrorActionPreference='SilentlyContinue'
try {{
    $start = (Get-Date).AddHours(-{int(hours)})
    $events = Get-WinEvent -FilterHashtable @{{LogName='System'; StartTime=$start}} -ErrorAction SilentlyContinue -MaxEvents 500 |
        Where-Object {{ {patterns_ps} }}
    $result = $events | Select-Object @{{
        n='TimeCreated'; e={{$_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')}}
    }}, @{{
        n='Id'; e={{$_.Id}}
    }}, @{{
        n='LevelDisplayName'; e={{$_.LevelDisplayName}}
    }}, @{{
        n='ProviderName'; e={{$_.ProviderName}}
    }}, @{{
        n='Message'; e={{$_.Message}}
    }}, @{{
        n='LogName'; e={{$_.LogName}}
    }}
    $result | ConvertTo-Json -Depth 3
}} catch {{
    Write-Output '[]'
}}
"""
        success, stdout, stderr = self._execute_powershell_remote(server_name, script)
        if not success or not stdout.strip():
            logger.info(f"[Logs/csv_text] PS remoto sem resultados ({stderr[:100] if stderr else 'no stderr'})")
            return []
        try:
            events = json.loads(stdout.strip() or '[]')
            if isinstance(events, dict):
                events = [events]
        except json.JSONDecodeError as e:
            logger.warning(f"[Logs/csv_text] JSON parse error: {e}")
            return []
        for evt in events:
            evt['category'] = 'csv_storage'
            evt['event_type'] = 'CSV_STORAGE'
            evt['Method'] = 'PowerShell-TextSearch'
        return events

    def collect_windows_events(
        self,
        server_id: str,
        hours: int = 24,
        event_categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Coleta eventos do Windows por categoria (VERSÃO OTIMIZADA COM CACHE E PARALELIZAÇÃO)

        FOCO: Problemas que afetam SQL Server, Always On e Backups

        event_categories:
        - 'disk' - Erros de disco (afetam SQL Server, AG, Backups)
        - 'sql_server' - Erros críticos SQL Server (I/O, corrupção, espaço, backup)
        - 'alwayson' - Problemas Always On (failover, sync, cluster)
        - 'shutdown' - Shutdowns/Restarts (afetam disponibilidade)
        - 'backup' - Problemas VSS/Backup
        - 'cluster' - Problemas de cluster (afetam AG)
        """
        # Categorias padrão: FOCO EM SQL SERVER, ALWAYS ON E BACKUPS
        if event_categories is None:
            event_categories = [
                'shutdown',     # CRÍTICO - Reinicializações/crashes (afetam disponibilidade)
                'disk',         # CRÍTICO - I/O afeta tudo
                'sql_server',   # CRÍTICO - Erros SQL + Backup
                'alwayson',     # CRÍTICO - Failover e Sync
                'backup',       # CRÃTICO - VSS e backup failures
                # 'cluster' e 'csv_storage' removidas do default — caras (Microsoft-Windows-* canal so via PS)
                # e raras na maioria dos servidores. Activar via ?categories=cluster,csv_storage no endpoint.
                'service_broker',  # CRÃTICO - ComunicaÃ§Ã£o entre instÃ¢ncias (AG/Mirroring)
            ]

        # Verificar cache primeiro
        cache_key = self._get_cache_key(server_id, hours, event_categories)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        logger.info(f"Coletando eventos do Windows para {server_id} ({hours}h) - SEM CACHE")
        logger.info(f"Categorias: {', '.join(event_categories)}")

        server_name = self._get_server_hostname(server_id)

        # Mapear categorias para Event IDs (ATUALIZADO COM FOCO)
        category_map = {
            'disk': (self.DISK_ERROR_EVENT_IDS, 'System', None),
            'sql_server': (self.SQL_SERVER_CRITICAL_IDS, 'Application', 'MSSQLSERVER'),
            'alwayson': (self.ALWAYSON_EVENT_IDS, 'Application', 'MSSQLSERVER'),
            'shutdown': (self.SHUTDOWN_EVENT_IDS, 'System', None),
            'backup': (self.BACKUP_EVENT_IDS, 'System', 'VSS'),
            'cluster': (self.CLUSTER_EVENT_IDS, 'Microsoft-Windows-FailoverClustering/Operational', None),
            'service_broker': (self.SERVICE_BROKER_EVENT_IDS, 'Application', 'MSSQLSERVER'),
            # CSV Storage: System log + provider FailoverClustering (capta Event IDs 5120/5142/etc)
            'csv_storage': (self.CSV_STORAGE_EVENT_IDS, 'System', 'Microsoft-Windows-FailoverClustering'),
            # Memory (opt-in, 2026-07-27): antes desta entry MEMORY_EVENT_IDS era
            # inalcancavel — classificado em _classify_event_type mas sem caminho
            # de coleta (achado corroborado por frontend-specialist + customer
            # -success-persona). System log capta Resource-Exhaustion/2004 etc;
            # IDs de memoria do lado SQL (701/8628...) chegam via 'sql_server'.
            'memory': (self.MEMORY_EVENT_IDS, 'System', None),
        }

        # PARALELIZAÇÃO: Coletar todas as categorias em paralelo
        all_events = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submeter todas as tarefas
            future_to_category = {}
            for category in event_categories:
                if category not in category_map:
                    continue

                event_ids, log_name, provider = category_map[category]
                future = executor.submit(
                    self._collect_category_events,
                    server_name, category, event_ids, log_name, provider, hours
                )
                future_to_category[future] = category

            # Coletar resultados conforme ficam prontos
            for future in as_completed(future_to_category):
                category = future_to_category[future]
                try:
                    events = future.result()
                    logger.info(f"[Logs] Categoria '{category}' retornou {len(events)} eventos")
                    all_events.extend(events)
                except Exception as e:
                    logger.error(f"Erro ao processar categoria {category}: {e}")

        # Rede de segurança: text-search para CSV/Storage IO timeouts
        # Captura mensagens "Shared Volume IO is paused", STATUS_IO_TIMEOUT, c00000b5
        # mesmo quando os Event IDs diferem dos conhecidos.
        if 'csv_storage' in event_categories:
            try:
                text_events = self._collect_csv_text_search(server_name, hours)
                if text_events:
                    # Deduplicar contra os já capturados (mesmo TimeCreated+Id)
                    existing_keys = {(e.get('TimeCreated', ''), e.get('Id', 0)) for e in all_events}
                    new_count = 0
                    for evt in text_events:
                        key = (evt.get('TimeCreated', ''), evt.get('Id', 0))
                        if key not in existing_keys:
                            all_events.append(evt)
                            existing_keys.add(key)
                            new_count += 1
                    logger.info(f"[Logs/csv_text] Text-search adicionou {new_count} eventos novos")
            except Exception as e:
                logger.warning(f"[Logs/csv_text] Text-search falhou: {e}")

        # Ordenar por data (mais recente primeiro)
        all_events.sort(
            key=lambda x: x.get('TimeCreated', ''),
            reverse=True
        )

        result = {
            'success': True,
            'server_id': server_id,
            'events': all_events[:500],  # Limitar a 500 eventos (reduzido de 1000)
            'total_count': len(all_events),
            'categories_found': list(set(e.get('category', 'unknown') for e in all_events)),
            'cached': False
        }

        # Salvar no cache
        self._save_to_cache(cache_key, result)

        return result
    
    def _classify_event_type(self, event_id: int) -> str:
        """Classifica o tipo de evento baseado no ID

        Foco em eventos que afetam:
        - SQL Server em geral (I/O, corrupção, espaço, erros críticos)
        - Always On Availability Groups (failover, sync, cluster)
        - Backups (VSS, backup failures)
        """
        if event_id in self.SHUTDOWN_EVENT_IDS:
            return 'SHUTDOWN'
        elif event_id in self.DISK_ERROR_EVENT_IDS:
            return 'DISK_ERROR'
        elif event_id in self.SQL_SERVER_CRITICAL_IDS:
            return 'SQL_SERVER_ERROR'
        elif event_id in self.ALWAYSON_EVENT_IDS:
            return 'ALWAYS_ON'
        elif event_id in self.BACKUP_EVENT_IDS:
            return 'BACKUP_ERROR'
        elif event_id in self.CSV_STORAGE_EVENT_IDS:
            return 'CSV_STORAGE'
        elif event_id in self.CLUSTER_EVENT_IDS:
            return 'CLUSTER'
        elif event_id in self.SERVICE_BROKER_EVENT_IDS:
            return 'SERVICE_BROKER'
        elif event_id in self.MEMORY_EVENT_IDS:
            return 'MEMORY'
        else:
            return 'OTHER'
    
    def _classify_windows_event(self, event_id: int, source: str, level: str) -> str:
        """Classifica evento do Windows para categorização"""
        if event_id in self.SHUTDOWN_EVENT_IDS:
            return 'Shutdown/Restart'
        elif event_id in self.DISK_ERROR_EVENT_IDS:
            return 'Disk Error'
        elif event_id in self.SQL_SERVER_CRITICAL_IDS:
            return 'SQL Server Critical'
        elif event_id in self.ALWAYSON_EVENT_IDS:
            return 'Always On'
        elif event_id in self.BACKUP_EVENT_IDS:
            return 'Backup Error'
        elif event_id in self.CSV_STORAGE_EVENT_IDS:
            return 'CSV Storage'
        elif event_id in self.CLUSTER_EVENT_IDS:
            return 'Cluster'
        elif event_id in self.SERVICE_BROKER_EVENT_IDS:
            return 'Service Broker'
        elif event_id in self.MEMORY_EVENT_IDS:
            return 'Memory'
        else:
            return 'Other'


class SQLLogsCollector:
    """Coletor de logs do SQL Server (ERRORLOG e Event IDs)"""

    def __init__(self):
        self.timeout = 30  # Reduzido para 30 segundos (era 120s)
        self.cache = {}  # Cache de resultados
        self.cache_ttl = 300  # TTL de 5 minutos
        
    def _get_cache_key(self, server_id: str, hours: int) -> str:
        """Gera chave de cache"""
        return f"sql_{server_id}_{hours}"

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Recupera do cache se válido"""
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            age = time.time() - cached_time
            if age < self.cache_ttl:
                logger.info(f"SQL Cache HIT: {cache_key} (idade: {age:.1f}s)")
                return cached_data
            else:
                logger.info(f"SQL Cache EXPIRED: {cache_key}")
                del self.cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any]):
        """Salva no cache"""
        self.cache[cache_key] = (data, time.time())
        logger.info(f"SQL Cache SAVED: {cache_key}")

        # Limpar cache antigo
        if len(self.cache) > 30:
            oldest_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k][1])[:15]
            for key in oldest_keys:
                del self.cache[key]

    def _get_server_hostname(self, server_id: str) -> str:
        """Extrai o hostname do server_id"""
        return server_id.split('_')[0] if '_' in server_id else server_id

    def _get_errorlog_path(self, server_id: str) -> str:
        """Tenta descobrir o caminho do ERRORLOG do SQL Server"""
        # Padrões comuns de caminho
        patterns = [
            r"C:\\Program Files\\Microsoft SQL Server\\MSSQL*.MSSQLSERVER\\MSSQL\\Log\\ERRORLOG",
            r"C:\\Program Files\\Microsoft SQL Server\\MSSQL*.MSSQLSERVER\\MSSQL\\Log\\ERRORLOG.*",
            r"C:\\Program Files (x86)\\Microsoft SQL Server\\MSSQL*.MSSQLSERVER\\MSSQL\\Log\\ERRORLOG",
        ]
        
        # Por enquanto, retornar padrão comum
        # Em produção, seria melhor consultar via SQL
        return "C:\\Program Files\\Microsoft SQL Server\\MSSQL16.MSSQLSERVER\\MSSQL\\Log\\ERRORLOG"
    
    def collect_errorlog_errors(
        self, 
        server_id: str, 
        hours: int = 24,
        severity_min: int = 17
    ) -> List[Dict[str, Any]]:
        """
        Coleta erros críticos do ERRORLOG do SQL Server
        
        severity_min: Severidade mínima (17+ são críticos)
        """
        server_name = self._get_server_hostname(server_id)
        errorlog_path = self._get_errorlog_path(server_id)
        
        script = f"""
$ErrorActionPreference='SilentlyContinue'
try {{
    $cutoff = (Get-Date).AddHours(-{hours})
    $errors = @()
    
    if (Test-Path "{errorlog_path}") {{
        $content = Get-Content "{errorlog_path}" -Tail 1000
        foreach ($line in $content) {{
            if ($line -match 'Error:|Severity: ([1-9][0-9]+)|CHECKDB|corruption|I/O|AG|cluster|failover') {{
                $errors += $line
            }}
        }}
    }}
    
    # Também tentar via xp_readerrorlog se possível
    $errors | Select-Object -First 100 | ConvertTo-Json
}} catch {{
    Write-Output '[]'
}}
"""
        
        success, stdout, stderr = self._execute_powershell_local(script)
        if not success:
            # Tentar remoto
            success, stdout, stderr = self._execute_powershell_remote(server_name, script)
        
        errors = []
        if success:
            try:
                error_lines = json.loads(stdout.strip() or '[]')
                if isinstance(error_lines, str):
                    error_lines = [error_lines]
                
                for line in error_lines[:100]:  # Limitar a 100
                    error = self._parse_errorlog_line(str(line))
                    if error:
                        errors.append(error)
            except Exception as e:
                logger.warning(f"Erro ao processar ERRORLOG: {e}")
        
        return errors
    
    def _parse_errorlog_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parseia uma linha do ERRORLOG"""
        # Padrões comuns do ERRORLOG
        # Exemplo: "2024-01-15 10:30:45.12 spid51      Error: 823, Severity: 24, State: 2"
        
        error = {
            'message': line[:500],  # Limitar tamanho
            'severity': None,
            'error_number': None,
            'timestamp': None
        }
        
        # Extrair severity
        severity_match = re.search(r'Severity:\s*(\d+)', line, re.IGNORECASE)
        if severity_match:
            error['severity'] = int(severity_match.group(1))
        
        # Extrair error number
        error_match = re.search(r'Error:\s*(\d+)', line, re.IGNORECASE)
        if error_match:
            error['error_number'] = int(error_match.group(1))
        
        # Extrair timestamp
        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        if timestamp_match:
            try:
                error['timestamp'] = datetime.strptime(
                    timestamp_match.group(1), 
                    '%Y-%m-%d %H:%M:%S'
                ).isoformat()
            except (ValueError, TypeError):
                pass

        # Só retornar se tiver informação relevante
        if error['severity'] or error['error_number'] or 'error' in line.lower():
            return error
        
        return None
    
    def _execute_powershell_remote(self, server_name: str, script: str) -> Tuple[bool, str, str]:
        """Executa PowerShell remoto via WinRM"""
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                f"Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {script} }}"
            ]
            completed = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.timeout
            )
            return completed.returncode == 0, completed.stdout, completed.stderr
        except Exception as e:
            logger.error(f"Erro ao executar PowerShell remoto: {e}")
            return False, "", str(e)
    
    def _execute_powershell_local(self, script: str) -> Tuple[bool, str, str]:
        """Executa PowerShell local"""
        try:
            cmd = ["powershell", "-NoProfile", "-Command", script]
            completed = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.timeout
            )
            return completed.returncode == 0, completed.stdout, completed.stderr
        except Exception as e:
            logger.error(f"Erro ao executar PowerShell local: {e}")
            return False, "", str(e)
    
    def collect_sql_event_ids(
        self, 
        server_id: str, 
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Coleta Event IDs do SQL Server no Application Log"""
        server_name = self._get_server_hostname(server_id)
        
        # Event IDs críticos do SQL Server
        sql_event_ids = [823, 824, 825, 832, 833, 845, 1105, 1204, 9002, 17053, 17204, 17207, 17300]
        
        script = f"""
$ErrorActionPreference='SilentlyContinue'
try {{
    $start = (Get-Date).AddHours(-{hours})
    $events = Get-WinEvent -FilterHashtable @{{
        LogName = 'Application'
        ProviderName = 'MSSQLSERVER'
        Level = 1, 2, 3
        ID = {','.join(map(str, sql_event_ids))}
        StartTime = $start
    }} -ErrorAction SilentlyContinue -MaxEvents 500
    
    $result = $events | Select-Object @{{
        n='TimeCreated'; e={{$_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')}}
    }}, @{{
        n='Id'; e={{$_.Id}}
    }}, @{{
        n='LevelDisplayName'; e={{$_.LevelDisplayName}}
    }}, @{{
        n='Message'; e={{$_.Message}}
    }}
    $result | ConvertTo-Json -Depth 3
}} catch {{
    Write-Output '[]'
}}
"""
        
        success, stdout, stderr = self._execute_powershell_remote(server_name, script)
        if not success:
            success, stdout, stderr = self._execute_powershell_local(script)
        
        errors = []
        if success:
            try:
                events = json.loads(stdout.strip() or '[]')
                if isinstance(events, dict):
                    events = [events]
                
                for event in events:
                    errors.append({
                        'error_date': event.get('TimeCreated'),
                        'error_severity': self._map_event_level_to_severity(event.get('LevelDisplayName', '')),
                        'error_number': event.get('Id'),
                        'error_message': event.get('Message', '')[:500],
                        'database_name': None,  # Não disponível no Event ID
                        'source': 'Windows Event Log'
                    })
            except Exception as e:
                logger.warning(f"Erro ao processar Event IDs do SQL: {e}")
        
        return errors
    
    def _map_event_level_to_severity(self, level: str) -> int:
        """Mapeia nível do evento para severidade SQL"""
        level_upper = level.upper()
        if 'CRITICAL' in level_upper or 'ERROR' in level_upper:
            return 20
        elif 'WARNING' in level_upper:
            return 16
        else:
            return 14
    
    def collect_all_sql_errors(
        self,
        server_id: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Coleta todos os erros do SQL Server (ERRORLOG + Event IDs)
        VERSÃO OTIMIZADA COM CACHE E PARALELIZAÇÃO
        """
        # Verificar cache primeiro
        cache_key = self._get_cache_key(server_id, hours)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        logger.info(f"Coletando erros SQL para {server_id} ({hours}h) - SEM CACHE")

        # PARALELIZAÇÃO: Coletar ERRORLOG e Event IDs em paralelo
        from concurrent.futures import ThreadPoolExecutor, as_completed

        errorlog_errors = []
        event_id_errors = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submeter ambas as tarefas em paralelo
            future_errorlog = executor.submit(self.collect_errorlog_errors, server_id, hours)
            future_events = executor.submit(self.collect_sql_event_ids, server_id, hours)

            # Aguardar resultados
            try:
                errorlog_errors = future_errorlog.result()
            except Exception as e:
                logger.error(f"Erro ao coletar ERRORLOG: {e}")

            try:
                event_id_errors = future_events.result()
            except Exception as e:
                logger.error(f"Erro ao coletar Event IDs: {e}")

        # Combinar e remover duplicatas
        all_errors = errorlog_errors + event_id_errors

        # Ordenar por data (mais recente primeiro)
        all_errors.sort(
            key=lambda x: x.get('timestamp') or x.get('error_date') or '',
            reverse=True
        )

        result = {
            'success': True,
            'server_id': server_id,
            'errors': all_errors[:200],  # Limitar a 200 erros (reduzido de 500)
            'total_count': len(all_errors),
            'errorlog_count': len(errorlog_errors),
            'event_id_count': len(event_id_errors),
            'cached': False
        }

        # Salvar no cache
        self._save_to_cache(cache_key, result)

        return result







