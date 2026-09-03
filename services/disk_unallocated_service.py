"""
Disk Unallocated Service - Coleta e analise de espaco nao alocado em discos fisicos

Este servico coleta informacoes via WMI/PowerShell remoto sobre:
- Discos fisicos (tamanho, modelo, saude)
- Particoes (drive letters, tamanho, filesystem)
- Espaco nao alocado (oportunidades de expansao)

Autor: WatcherDB
Data: 2026-01-20
"""

import logging
import subprocess
import json
import asyncio
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, asdict
from contextlib import contextmanager

# Import do pool de conexoes centralizado
from api.connection_pool import get_intelligence_pool
from modules.monitoring.queries import DiskUnallocatedQueries

logger = logging.getLogger(__name__)


def _serialize_result(obj):
    """Serializa objetos para JSON (converte Decimal, datetime, etc)"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_result(item) for item in obj]
    return obj


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PhysicalDisk:
    """Representa um disco fisico."""
    instance: str
    disk_number: int
    disk_model: str
    disk_size_gb: float
    partition_style: str
    is_system_disk: bool
    is_boot_disk: bool
    health_status: str
    operational_status: str
    bus_type: str
    media_type: str
    collection_method: str


@dataclass
class Partition:
    """Representa uma particao."""
    instance: str
    disk_number: int
    partition_number: int
    drive_letter: Optional[str]
    volume_label: str
    partition_size_gb: float
    file_system: str
    is_active: bool
    is_boot: bool
    partition_type: str


@dataclass
class UnallocatedSpace:
    """Representa espaco nao alocado em um disco."""
    instance: str
    disk_number: int
    disk_size_gb: float
    allocated_gb: float
    unallocated_gb: float
    percent_unallocated: float
    can_expand: bool
    adjacent_drive: Optional[str]


# =============================================================================
# THRESHOLDS E CONFIGURACAO
# =============================================================================

UNALLOCATED_THRESHOLDS = {
    'high_priority_gb': 100,    # >= 100 GB = Alta prioridade
    'medium_priority_gb': 50,   # >= 50 GB = Media prioridade
    'low_priority_gb': 10,      # >= 10 GB = Baixa prioridade
    'min_expansion_gb': 1.0     # Minimo para considerar expansivel
}


# =============================================================================
# SERVICE CLASS
# =============================================================================

class DiskUnallocatedService:
    """
    Servico para coleta e analise de espaco nao alocado em discos fisicos.

    Estrategia de coleta:
    1. PLANO A: WMI via PowerShell direto (Get-WmiObject -ComputerName)
    2. PLANO B: Invoke-Command via WinRM (mais robusto para firewalls)
    """

    def __init__(self, connection_string: str = None):
        """
        Inicializa o servico.

        Args:
            connection_string: String de conexao ao banco central (opcional)
        """
        self.connection_string = connection_string
        self.queries = DiskUnallocatedQueries

    @contextmanager
    def _get_connection(self):
        """Context manager para obter conexao do pool centralizado."""
        pool = get_intelligence_pool()
        conn = None
        try:
            conn = pool.get_connection()
            yield conn
        finally:
            if conn:
                pool.return_connection(conn)

    def _extract_hostname(self, server_id: str) -> str:
        """
        Extrai hostname do server_id.

        Suporta formatos:
        - SERVER\\INSTANCE -> SERVER
        - SERVER_INSTANCE -> SERVER
        - SERVER_I01 -> SERVER
        """
        hostname = server_id.split('\\')[0] if '\\' in server_id else server_id

        if '_' in hostname:
            parts = hostname.rsplit('_', 1)
            if len(parts) == 2 and (parts[1].startswith('I') or parts[1].isdigit()):
                hostname = parts[0]

        return hostname

    # =========================================================================
    # COLETA VIA WMI
    # =========================================================================

    async def collect_via_wmi(self, hostname: str) -> Tuple[List[PhysicalDisk], List[Partition], List[UnallocatedSpace]]:
        """
        Coleta informacoes de disco via WMI/PowerShell direto.

        PLANO A - Usa Get-WmiObject -ComputerName (protocolo DCOM/RPC)
        """
        logger.info(f"[PLANO A] Tentando WMI direto para {hostname}")

        ps_script = f'''
        $ErrorActionPreference = "Stop"
        try {{
            $computer = "{hostname}"

            # Coleta discos fisicos
            $disks = Get-WmiObject -Class Win32_DiskDrive -ComputerName $computer -ErrorAction Stop | Select-Object `
                @{{N='DiskNumber';E={{$_.Index}}}},
                @{{N='Model';E={{$_.Model}}}},
                @{{N='SizeGB';E={{[math]::Round($_.Size/1GB, 2)}}}},
                @{{N='InterfaceType';E={{$_.InterfaceType}}}},
                @{{N='MediaType';E={{$_.MediaType}}}},
                @{{N='Status';E={{$_.Status}}}}

            # Coleta particoes
            $partitions = Get-WmiObject -Class Win32_DiskPartition -ComputerName $computer -ErrorAction Stop | Select-Object `
                DiskIndex,
                Index,
                @{{N='SizeGB';E={{[math]::Round($_.Size/1GB, 2)}}}},
                Type,
                PrimaryPartition,
                BootPartition

            # Coleta volumes logicos
            $volumes = Get-WmiObject -Class Win32_LogicalDisk -ComputerName $computer -Filter "DriveType=3" -ErrorAction Stop | Select-Object `
                @{{N='DriveLetter';E={{$_.DeviceID.TrimEnd(':')}}}},
                @{{N='VolumeName';E={{$_.VolumeName}}}},
                @{{N='SizeGB';E={{[math]::Round($_.Size/1GB, 2)}}}},
                @{{N='FreeGB';E={{[math]::Round($_.FreeSpace/1GB, 2)}}}},
                @{{N='FileSystem';E={{$_.FileSystem}}}}

            # Retorna como JSON
            @{{
                Disks = @($disks)
                Partitions = @($partitions)
                Volumes = @($volumes)
                Success = $true
                Hostname = $computer
                CollectionMethod = "WMI"
            }} | ConvertTo-Json -Depth 3
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
                Hostname = "{hostname}"
            }} | ConvertTo-Json
        }}
        '''

        try:
            # Executa PowerShell de forma assincrona
            proc = await asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            output = stdout.decode('utf-8', errors='ignore').strip()
            if not output:
                raise Exception(f"Saida vazia do PowerShell. Stderr: {stderr.decode('utf-8', errors='ignore')}")

            data = json.loads(output)

            if not data.get('Success', False):
                raise Exception(data.get('Error', 'Unknown WMI error'))

            return self._process_disk_data(hostname, data, "WMI")

        except asyncio.TimeoutError:
            raise Exception(f"Timeout ao coletar via WMI de {hostname}")
        except Exception as e:
            logger.warning(f"[PLANO A] WMI falhou para {hostname}: {e}")
            raise

    async def collect_via_winrm(self, hostname: str) -> Tuple[List[PhysicalDisk], List[Partition], List[UnallocatedSpace]]:
        """
        Coleta via Invoke-Command (WinRM).

        PLANO B - Mais robusto quando DCOM/RPC esta bloqueado.
        """
        logger.info(f"[PLANO B] Tentando WinRM para {hostname}")

        ps_script = f'''
        $ErrorActionPreference = "Stop"
        try {{
            $result = Invoke-Command -ComputerName {hostname} -ScriptBlock {{
                $disks = Get-Disk | Select-Object `
                    Number,
                    FriendlyName,
                    @{{N='SizeGB';E={{[math]::Round($_.Size/1GB, 2)}}}},
                    PartitionStyle,
                    IsSystem,
                    IsBoot,
                    HealthStatus,
                    OperationalStatus,
                    BusType

                $partitions = Get-Partition | Where-Object {{ $_.DriveLetter }} | Select-Object `
                    DiskNumber,
                    PartitionNumber,
                    DriveLetter,
                    @{{N='SizeGB';E={{[math]::Round($_.Size/1GB, 2)}}}},
                    Type,
                    IsActive,
                    IsBoot

                $volumes = Get-Volume | Where-Object {{ $_.DriveLetter -and $_.DriveType -eq 'Fixed' }} | Select-Object `
                    DriveLetter,
                    FileSystemLabel,
                    @{{N='SizeGB';E={{[math]::Round($_.Size/1GB, 2)}}}},
                    @{{N='FreeGB';E={{[math]::Round($_.SizeRemaining/1GB, 2)}}}},
                    FileSystem

                @{{
                    Disks = @($disks)
                    Partitions = @($partitions)
                    Volumes = @($volumes)
                }}
            }} -ErrorAction Stop

            $result.Success = $true
            $result.Hostname = "{hostname}"
            $result.CollectionMethod = "WinRM"
            $result | ConvertTo-Json -Depth 3
        }} catch {{
            @{{
                Success = $false
                Error = $_.Exception.Message
                Hostname = "{hostname}"
            }} | ConvertTo-Json
        }}
        '''

        try:
            proc = await asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            output = stdout.decode('utf-8', errors='ignore').strip()

            # Extrai JSON da saida
            json_start = output.rfind('{')
            json_end = output.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise Exception(f"JSON nao encontrado na saida. Stderr: {stderr.decode('utf-8', errors='ignore')}")

            if not data.get('Success', False):
                raise Exception(data.get('Error', 'Unknown WinRM error'))

            return self._process_disk_data(hostname, data, data.get('CollectionMethod', 'WinRM'))

        except asyncio.TimeoutError:
            raise Exception(f"Timeout ao coletar via WinRM de {hostname}")
        except Exception as e:
            logger.warning(f"[PLANO B] WinRM falhou para {hostname}: {e}")
            raise

    # =========================================================================
    # PROCESSAMENTO DE DADOS
    # =========================================================================

    def _process_disk_data(self, server_id: str, data: dict, method: str) -> Tuple[List[PhysicalDisk], List[Partition], List[UnallocatedSpace]]:
        """Processa dados coletados e retorna objetos estruturados."""

        # Processa discos fisicos
        physical_disks = []
        for disk in data.get('Disks', []) or []:
            if disk:
                physical_disks.append(PhysicalDisk(
                    instance=server_id,
                    disk_number=int(disk.get('DiskNumber', disk.get('Number', 0))),
                    disk_model=str(disk.get('Model', disk.get('FriendlyName', 'Unknown'))),
                    disk_size_gb=float(disk.get('SizeGB', 0)),
                    partition_style=str(disk.get('PartitionStyle', 'Unknown')),
                    is_system_disk=bool(disk.get('IsSystem', False)),
                    is_boot_disk=bool(disk.get('IsBoot', False)),
                    health_status=str(disk.get('HealthStatus', disk.get('Status', 'Unknown'))),
                    operational_status=str(disk.get('OperationalStatus', 'Online')),
                    bus_type=str(disk.get('BusType', disk.get('InterfaceType', 'Unknown'))),
                    media_type=str(disk.get('MediaType', 'Unknown')),
                    collection_method=method
                ))

        # Processa particoes
        partitions = []
        volumes_map = {str(v.get('DriveLetter', '')).upper(): v for v in (data.get('Volumes', []) or []) if v}

        for i, part in enumerate(data.get('Partitions', []) or []):
            if part:
                drive_letter = part.get('DriveLetter')
                if drive_letter:
                    drive_letter = str(drive_letter).upper().replace(':', '')
                volume_info = volumes_map.get(drive_letter, {}) if drive_letter else {}

                partitions.append(Partition(
                    instance=server_id,
                    disk_number=int(part.get('DiskNumber', part.get('DiskIndex', 0))),
                    partition_number=int(part.get('PartitionNumber', part.get('Index', i + 1))),
                    drive_letter=drive_letter if drive_letter else None,
                    volume_label=str(volume_info.get('FileSystemLabel', volume_info.get('VolumeName', ''))),
                    partition_size_gb=float(part.get('SizeGB', 0)),
                    file_system=str(volume_info.get('FileSystem', 'NTFS')),
                    is_active=bool(part.get('IsActive', part.get('PrimaryPartition', False))),
                    is_boot=bool(part.get('IsBoot', part.get('BootPartition', False))),
                    partition_type=str(part.get('Type', 'Basic'))
                ))

        # Calcula espaco nao alocado
        unallocated = self._calculate_unallocated(server_id, physical_disks, partitions)

        logger.info(f"[{method}] Sucesso: {len(physical_disks)} discos, {len(partitions)} particoes, {len(unallocated)} registros")
        return physical_disks, partitions, unallocated

    def _calculate_unallocated(self, server_id: str, disks: List[PhysicalDisk],
                               partitions: List[Partition]) -> List[UnallocatedSpace]:
        """Calcula o espaco nao alocado por disco."""
        unallocated_list = []

        # Agrupa particoes por disco
        partitions_by_disk: Dict[int, List[Partition]] = {}
        for p in partitions:
            if p.disk_number not in partitions_by_disk:
                partitions_by_disk[p.disk_number] = []
            partitions_by_disk[p.disk_number].append(p)

        for disk in disks:
            disk_parts = partitions_by_disk.get(disk.disk_number, [])
            allocated = sum(p.partition_size_gb for p in disk_parts)

            # Considera ~1GB de overhead para GPT/MBR
            overhead = 1.0
            unalloc = max(0, disk.disk_size_gb - allocated - overhead)

            # Determina drive adjacente ao espaco nao alocado
            adjacent_drive = None
            if disk_parts and unalloc > 0:
                drives_with_letters = [p for p in disk_parts if p.drive_letter]
                if drives_with_letters:
                    adjacent_drive = sorted(drives_with_letters,
                                           key=lambda x: x.partition_number)[-1].drive_letter

            unallocated_list.append(UnallocatedSpace(
                instance=server_id,
                disk_number=disk.disk_number,
                disk_size_gb=disk.disk_size_gb,
                allocated_gb=allocated,
                unallocated_gb=round(unalloc, 2),
                percent_unallocated=round(unalloc * 100 / disk.disk_size_gb, 2) if disk.disk_size_gb > 0 else 0,
                can_expand=unalloc >= UNALLOCATED_THRESHOLDS['min_expansion_gb'],
                adjacent_drive=adjacent_drive
            ))

        return unallocated_list

    # =========================================================================
    # COLETA COM FALLBACK
    # =========================================================================

    async def collect_from_server(self, server_id: str) -> Dict[str, Any]:
        """
        Coleta informacoes de disco de um servidor usando Plano A ou Plano B.

        Args:
            server_id: ID do servidor (pode incluir instancia)

        Returns:
            Dict com discos, particoes, espaco nao alocado e metadados
        """
        hostname = self._extract_hostname(server_id)

        try:
            # Tenta Plano A primeiro
            disks, parts, unalloc = await self.collect_via_wmi(hostname)
        except Exception as e:
            logger.info(f"Plano A falhou, tentando Plano B: {e}")
            try:
                disks, parts, unalloc = await self.collect_via_winrm(hostname)
            except Exception as e2:
                logger.error(f"Ambos os planos falharam para {server_id}: {e2}")
                return {
                    'success': False,
                    'server_id': server_id,
                    'hostname': hostname,
                    'error': str(e2),
                    'disks': [],
                    'partitions': [],
                    'unallocated': []
                }

        return {
            'success': True,
            'server_id': server_id,
            'hostname': hostname,
            'collection_time': datetime.now().isoformat(),
            'disks': [asdict(d) for d in disks],
            'partitions': [asdict(p) for p in parts],
            'unallocated': [asdict(u) for u in unalloc],
            'summary': {
                'total_disks': len(disks),
                'total_partitions': len(parts),
                'total_unallocated_gb': sum(u.unallocated_gb for u in unalloc),
                'expandable_disks': sum(1 for u in unalloc if u.can_expand)
            }
        }

    # =========================================================================
    # PERSISTENCIA NO BANCO
    # =========================================================================

    async def save_collection(self, data: Dict) -> bool:
        """
        Salva dados coletados no banco central.

        Args:
            data: Dict retornado por collect_from_server()

        Returns:
            True se salvou com sucesso
        """
        if not data.get('success', False):
            logger.warning(f"Dados invalidos para salvar: {data.get('error')}")
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Insere discos fisicos
                for disk in data.get('disks', []):
                    cursor.execute(
                        self.queries.INSERT_PHYSICAL_DISK,
                        disk['instance'], disk['disk_number'], disk['disk_model'],
                        disk['disk_size_gb'], disk['partition_style'], disk['is_system_disk'],
                        disk['is_boot_disk'], disk['health_status'], disk['operational_status'],
                        disk['bus_type'], disk['media_type'], disk['collection_method']
                    )

                # Insere particoes
                for part in data.get('partitions', []):
                    cursor.execute(
                        self.queries.INSERT_PARTITION,
                        part['instance'], part['disk_number'], part['partition_number'],
                        part['drive_letter'], part['volume_label'], part['partition_size_gb'],
                        part['file_system'], part['is_active'], part['is_boot'], part['partition_type']
                    )

                # Insere espaco nao alocado
                for unalloc in data.get('unallocated', []):
                    cursor.execute(
                        self.queries.INSERT_UNALLOCATED,
                        unalloc['instance'], unalloc['disk_number'], unalloc['disk_size_gb'],
                        unalloc['allocated_gb'], unalloc['unallocated_gb'], unalloc['percent_unallocated'],
                        unalloc['can_expand'], unalloc['adjacent_drive']
                    )

                conn.commit()
                logger.info(f"Dados salvos para {data['server_id']}: {len(data.get('disks', []))} discos")
                return True

        except Exception as e:
            logger.error(f"Erro ao salvar dados de {data.get('server_id')}: {e}")
            return False

    # =========================================================================
    # CONSULTAS
    # =========================================================================

    async def get_unallocated_summary(self) -> List[Dict]:
        """Retorna resumo de espaco nao alocado de todos os servidores."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self.queries.UNALLOCATED_SUMMARY)
                columns = [col[0] for col in cursor.description]
                return [_serialize_result(dict(zip(columns, row))) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao obter resumo: {e}")
            return []

    async def get_server_detail(self, server_id: str) -> Dict[str, Any]:
        """Retorna detalhes de um servidor especifico."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Detalhes de espaco nao alocado
                cursor.execute(self.queries.SERVER_UNALLOCATED_DETAIL, server_id)
                columns = [col[0] for col in cursor.description]
                unallocated = [_serialize_result(dict(zip(columns, row))) for row in cursor.fetchall()]

                # Particoes
                cursor.execute(self.queries.SERVER_PARTITIONS, server_id)
                columns = [col[0] for col in cursor.description]
                partitions = [_serialize_result(dict(zip(columns, row))) for row in cursor.fetchall()]

                return {
                    'server_id': server_id,
                    'unallocated': unallocated,
                    'partitions': partitions,
                    'summary': {
                        'total_disks': len(set(u['Disco'] for u in unallocated)),
                        'total_unallocated_gb': sum(float(u.get('Nao_Alocado_GB', 0) or 0) for u in unallocated),
                        'expandable_disks': sum(1 for u in unallocated if u.get('Pode_Expandir'))
                    }
                }
        except Exception as e:
            logger.error(f"Erro ao obter detalhes de {server_id}: {e}")
            return {'server_id': server_id, 'error': str(e)}

    async def get_expansion_opportunities(self, min_gb: float = 10.0) -> List[Dict]:
        """Retorna oportunidades de expansao de particoes."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self.queries.EXPANSION_OPPORTUNITIES, min_gb)
                columns = [col[0] for col in cursor.description]
                return [_serialize_result(dict(zip(columns, row))) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao obter oportunidades: {e}")
            return []

    async def get_global_stats(self) -> Dict[str, Any]:
        """Retorna estatisticas globais."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Stats globais
                cursor.execute(self.queries.GLOBAL_STATS)
                columns = [col[0] for col in cursor.description]
                row = cursor.fetchone()
                global_stats = _serialize_result(dict(zip(columns, row))) if row else {}

                # Stats por ambiente
                cursor.execute(self.queries.STATS_BY_ENVIRONMENT)
                columns = [col[0] for col in cursor.description]
                by_env = [_serialize_result(dict(zip(columns, row))) for row in cursor.fetchall()]

                return {
                    'global': global_stats,
                    'by_environment': by_env
                }
        except Exception as e:
            logger.error(f"Erro ao obter estatisticas: {e}")
            return {'error': str(e)}

    async def get_history(self, server_id: str, days: int = 30) -> List[Dict]:
        """Retorna historico de espaco nao alocado."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self.queries.UNALLOCATED_HISTORY, server_id, days)
                columns = [col[0] for col in cursor.description]
                return [_serialize_result(dict(zip(columns, row))) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao obter historico de {server_id}: {e}")
            return []
