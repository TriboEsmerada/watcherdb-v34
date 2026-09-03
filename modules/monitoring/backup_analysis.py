"""
WatcherDB Backup Analysis - Análise de Backups MSDB
Inspirado no analisador de tickets anexado pelo usuário, focado em endpoints rápidos para o dashboard.

Performance Optimizations:
- Paralelização de queries Always On + Backup analysis
- Leitura assíncrona de TDP log com ThreadPoolExecutor
- Ganho estimado: 30-40% redução no tempo total
"""
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import os
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool para operações I/O (TDP log read)
_io_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="backup_io")

# Cache de servidores onde TDP NÃO está disponível (evita retry por 30 min)
_tdp_unavailable_cache: Dict[str, datetime] = {}
_TDP_UNAVAILABLE_TTL = timedelta(minutes=30)

# 🚨 VERSION MARKER - Para confirmar que o código correto está carregado
__BACKUP_ANALYSIS_VERSION__ = "2026-01-16_PARAMS_FIX_V2"
logger.info(f"🚨 backup_analysis.py CARREGADO - VERSÃO: {__BACKUP_ANALYSIS_VERSION__}")


@dataclass
class DatabaseBackupStatus:
    database_name: str
    recovery_model: str
    last_full: Optional[str]
    last_diff: Optional[str]
    last_log: Optional[str]
    hours_since_last_full: Optional[float]
    hours_since_last_diff: Optional[float]
    hours_since_last_log: Optional[float]
    issues: List[str]
    tdp_error_count: int = 0
    tdp_samples: List[str] = None
    alwayson_info: Optional[str] = None  # Mensagem informativa sobre Always On
    is_ag_secondary: bool = False  # Wave I.4 (2026-05-19): setado incondicionalmente quando AG secondary local. Frontend usa para suprimir recalculateIssues stale.
    # 2026-08-17 (revisao owner: ferramentas externas de backup). Origem do ULTIMO
    # backup de cada tipo, auto-detectada de msdb (sem config): device_type 7 =
    # virtual device (TDP/Commvault/Veeam/NetBackup...), 2 disco, 5 tape, 9 URL;
    # physical_device_name identifica a ferramenta; user_name = quem correu.
    # Forma: {'FULL': {...}, 'DIFF': {...}, 'LOG': {...}} com chaves
    # source ('VIRTUAL_DEVICE'|'DISK'|'TAPE'|'URL'|'UNKNOWN'), tool (str|None),
    # device_type (int|None), physical_device (str|None), user_name (str|None).
    backup_source: Optional[Dict[str, Any]] = None


# Padroes de nome de dispositivo virtual das ferramentas externas mais comuns.
# Ordem importa (o 1o match ganha). Substring case-insensitive sobre
# backupmediafamily.physical_device_name (+ user_name como pista fraca).
_EXTERNAL_TOOL_PATTERNS = (
    ('TDP',        ('TDPSQL', 'TDP', 'TIVOLI', 'TSM', 'SPECTRUM')),
    ('COMMVAULT',  ('COMMVAULT', 'CV_', 'GALAXY', 'SIMPANA')),
    ('VEEAM',      ('VEEAM',)),
    ('NETBACKUP',  ('NETBACKUP', 'VNBU', 'NBU', 'VERITAS')),
    ('NETWORKER',  ('NETWORKER', 'LEGATO', 'NSR')),
    ('RUBRIK',     ('RUBRIK',)),
    ('COHESITY',   ('COHESITY',)),
    ('DPM',        ('DPM', 'MABS')),
    ('AVAMAR',     ('AVAMAR', 'AVTAR')),
    ('LITESPEED',  ('LITESPEED',)),
    ('SQLSAFE',    ('SQLSAFE', 'IDERA')),
)


def classify_backup_source(device_type, physical_device: Optional[str], user_name: Optional[str]) -> Dict[str, Any]:
    """Classifica a origem de um backup a partir de msdb.dbo.backupmediafamily/backupset.

    device_type: 2 disk | 5 tape | 7 virtual device | 9 Azure URL | 102/105/107/109 permanent
    Devolve dict serializavel; nunca levanta (dado ausente -> UNKNOWN).
    """
    try:
        dt = int(device_type) if device_type is not None else None
    except (TypeError, ValueError):
        dt = None
    pd = (physical_device or '')
    un = (user_name or '')
    hay = (pd + ' ' + un).upper()
    tool = None
    for name, pats in _EXTERNAL_TOOL_PATTERNS:
        if any(p in hay for p in pats):
            tool = name
            break
    if dt in (7, 107):
        source = 'VIRTUAL_DEVICE'
        if tool is None:
            tool = 'OTHER'   # VDI generico (GUID/nome opaco) — externo, ferramenta desconhecida
    elif dt in (2, 102):
        source = 'DISK'
    elif dt in (5, 105):
        source = 'TAPE'
    elif dt in (9, 109):
        source = 'URL'
    else:
        source = 'UNKNOWN'
    return {
        'source': source,
        'tool': tool,
        'device_type': dt,
        'physical_device': pd[:200] if pd else None,
        'user_name': un[:128] if un else None,
        'is_external': source == 'VIRTUAL_DEVICE',
    }


def _backup_source_from_row(row: Dict) -> Optional[Dict[str, Any]]:
    """Constroi o dict backup_source (FULL/DIFF/LOG) a partir de uma linha da query
    de ultimos backups. Devolve None se a linha nao trouxer as colunas (query antiga)."""
    if not row or not any(k in row for k in ('full_device_type', 'diff_device_type', 'log_device_type')):
        return None
    out = {}
    for typ, pfx in (('FULL', 'full'), ('DIFF', 'diff'), ('LOG', 'log')):
        if row.get(f'{pfx}_device_type') is None and not row.get(f'{pfx}_physical_device') and not row.get(f'{pfx}_user_name'):
            continue  # sem backup deste tipo
        out[typ] = classify_backup_source(
            row.get(f'{pfx}_device_type'), row.get(f'{pfx}_physical_device'), row.get(f'{pfx}_user_name'))
    return out or None


class BackupAnalysisEngine:
    """Engine simples para análise de backups usando msdb.dbo.backupset."""

    def __init__(self, sql_monitoring, backup_tool_config: Optional[Dict] = None):
        self.sql_monitoring = sql_monitoring

        # Configuração da ferramenta de backup (TDP, Veeam, Commvault, nativo, etc.)
        # Se não configurado, TDP log analysis é DESABILITADO por padrão
        tool_cfg = backup_tool_config or {}
        self.backup_tool_enabled = tool_cfg.get('enabled', False)
        self.backup_tool_name = tool_cfg.get('tool_name', 'none')  # 'tdp', 'veeam', 'commvault', 'native', 'none'
        self.backup_tool_log_path = tool_cfg.get('log_path', '')   # Path do log (ex: C:\Program Files\tivoli\TSM\TDPSql\dsierror.log)

        # SLAs padrão
        self.log_sla_hours = 2            # LOG deve ocorrer a cada ~30–60min (tolerância 2h)
        self.diff_sla_hours = 12          # DIFF típico a cada 12h
        self.full_sla_days = 7            # FULL semanal

    async def _check_alwayson_and_get_replicas(self, server_id: str) -> Optional[Dict]:
        """
        Verifica se o servidor é Always On e retorna informações sobre primário e secundário.
        Retorna None se não for Always On.

        Retorna:
            - is_alwayson: True se for Always On
            - ag_name: Nome do Availability Group
            - primary_replica: Nome da réplica primária
            - current_is_primary: True se o servidor atual é o primário
            - backup_preference: Preferência de backup (0=Primary, 1=Secondary, 2=SecondaryOnly, 3=Any)
            - backup_preference_desc: Descrição da preferência
            - replicas: Lista de réplicas do AG
        """
        try:
            # Query para identificar primário e preferência de backup
            query = """
            SELECT
                ags.primary_replica,
                ag.name AS ag_name,
                ag.automated_backup_preference AS backup_preference,
                CASE ag.automated_backup_preference
                    WHEN 0 THEN 'Primary'
                    WHEN 1 THEN 'Secondary Preferred'
                    WHEN 2 THEN 'Secondary Only'
                    WHEN 3 THEN 'Any Replica'
                    ELSE 'Unknown'
                END AS backup_preference_desc
            FROM sys.availability_groups ag
            JOIN sys.dm_hadr_availability_group_states ags
                ON ag.group_id = ags.group_id;
            """

            result = await self.sql_monitoring.execute_query(server_id, query)
            logger.debug(f"🔍 Always On query result: success={result.get('success') if result else 'None'}, rows={len(result.get('rows', [])) if result else 0}")
            if not result or not result.get('success'):
                logger.info(f"❌ Servidor {server_id} NÃO é Always On (query falhou ou retornou erro)")
                return None

            rows = result.get('rows', [])
            if not rows:
                logger.info(f"❌ Servidor {server_id} NÃO é Always On (query não retornou linhas)")
                return None

            # Pegar o primeiro AG (geralmente há apenas um por servidor)
            ag_info = rows[0]
            primary_replica = ag_info.get('primary_replica')
            ag_name = ag_info.get('ag_name')
            backup_preference = ag_info.get('backup_preference', 0)
            backup_preference_desc = ag_info.get('backup_preference_desc', 'Primary')

            if not primary_replica or not ag_name:
                return None

            # Identificar o servidor atual (normalizar para comparação)
            current_server_id_normalized = self._normalize_server_name(server_id)
            primary_normalized = self._normalize_server_name(primary_replica)
            is_current_primary = (current_server_id_normalized == primary_normalized)

            # DEBUG: Log comparação
            logger.info(f"🔍 Comparação Always On:")
            logger.info(f"   server_id: {server_id} → normalizado: {current_server_id_normalized}")
            logger.info(f"   primary_replica: {primary_replica} → normalizado: {primary_normalized}")
            logger.info(f"   is_current_primary: {is_current_primary}")

            # Buscar todas as réplicas do AG com backup priority
            # 🔧 FIX: execute_query() não aceita 'params', usar string interpolation com escape SQL
            ag_name_escaped = ag_name.replace("'", "''")  # Escape single quotes (SQL standard)
            replicas_query = f"""
            SELECT
                ar.replica_server_name,
                ar.backup_priority,
                ars.role_desc,
                ars.operational_state_desc,
                ars.synchronization_health_desc
            FROM sys.availability_groups ag
            INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
            INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
            WHERE ag.name = '{ag_name_escaped}'
            ORDER BY ar.backup_priority DESC, ars.role_desc;
            """

            logger.info(f"🚨 DEBUG: Executando replicas query com ag_name='{ag_name_escaped}'")
            # Executar query (sem params)
            replicas_result = await self.sql_monitoring.execute_query(server_id, replicas_query)
            if not replicas_result or not replicas_result.get('success'):
                # Se falhar, retornar pelo menos o primário
                return {
                    'is_alwayson': True,
                    'ag_name': ag_name,
                    'primary_replica': primary_replica,
                    'current_is_primary': is_current_primary,
                    'backup_preference': backup_preference,
                    'backup_preference_desc': backup_preference_desc,
                    'replicas': [{'server_name': primary_replica, 'role': 'PRIMARY', 'backup_priority': 50}]
                }

            replica_rows = replicas_result.get('rows', [])
            replicas = []
            for rep_row in replica_rows:
                replica_name = rep_row.get('replica_server_name')
                role = rep_row.get('role_desc', '')
                backup_priority = rep_row.get('backup_priority', 50)
                if replica_name:
                    replicas.append({
                        'server_name': replica_name,
                        'role': role,
                        'backup_priority': backup_priority
                    })

            return {
                'is_alwayson': True,
                'ag_name': ag_name,
                'primary_replica': primary_replica,
                'current_is_primary': is_current_primary,
                'backup_preference': backup_preference,
                'backup_preference_desc': backup_preference_desc,
                'replicas': replicas
            }

        except Exception as e:
            logger.error(f"❌ EXCEÇÃO em _check_alwayson_and_get_replicas para {server_id}: {e}", exc_info=True)
            logger.error(f"❌ Tipo da exceção: {type(e).__name__}")
            return None
    
    def _get_backup_recommendation(self, backup_preference: int, is_primary: bool) -> str:
        """
        Gera recomendação contextual baseada na preferência de backup e papel do servidor.

        Args:
            backup_preference: 0=Primary, 1=Secondary Preferred, 2=Secondary Only, 3=Any
            is_primary: True se é servidor primário

        Returns:
            String com recomendação
        """
        if backup_preference == 0:  # Primary
            if is_primary:
                return "Backups configurados para execução neste servidor (Primário)."
            else:
                return "Backups configurados para execução no servidor primário. Dados exibidos são do primário."

        elif backup_preference == 1:  # Secondary Preferred
            if is_primary:
                return "Backups preferencialmente executados em secundários. Backups podem aparecer neste servidor apenas se secundários não estiverem disponíveis."
            else:
                return "Backups preferencialmente executados neste servidor (Secundário). Verifique a coluna 'Backup Server' para confirmar onde cada backup foi executado."

        elif backup_preference == 2:  # Secondary Only
            if is_primary:
                return "Backups configurados apenas em secundários. Este servidor (Primário) NÃO executa backups."
            else:
                return "Backups executados apenas em secundários. Este servidor deve ter os backups mais recentes."

        elif backup_preference == 3:  # Any Replica
            if is_primary:
                return "Backups podem ser executados em qualquer réplica (Primary ou Secondary). Verifique a coluna 'Backup Server' para ver onde cada backup foi executado."
            else:
                return "Backups podem ser executados em qualquer réplica. Verifique a coluna 'Backup Server' para ver onde cada backup foi executado."

        return "Configuração de backup não identificada."

    def _normalize_server_name(self, server_name: str) -> str:
        """
        Normaliza nome do servidor para comparação (remove domínio, converte para lowercase).
        Ex: 'SQLHDSPRD023\\I01' -> 'sqlhdprd023_i01'
        Ex: 'SQLHDSPRD023.tapnet.tap.pt\\I01' -> 'sqlhdprd023_i01'
        """
        if not server_name:
            return ''
        
        # Remover domínio
        base = server_name.split('.')[0]
        
        # Converter barra invertida para underscore
        normalized = base.replace('\\', '_').lower()
        
        return normalized

    def _convert_replica_to_server_id(self, replica_name: str) -> str:
        """
        Converte nome de réplica (ex: 'SQLHDSPRD023\\I01') para server_id (ex: 'SQLHDSPRD023_I01').
        """
        if '\\' in replica_name:
            parts = replica_name.split('\\', 1)
            host = parts[0].split('.')[0]  # Remover domínio
            instance = parts[1] if len(parts) > 1 else ''
            if instance:
                return f"{host}_{instance}"
            return host
        return replica_name.split('.')[0]  # Remover domínio se houver

    def _check_backup_issues(self, last_full, last_diff, last_log, recovery_model: str, now: datetime,
                            last_full_start: Optional[datetime] = None,
                            last_diff_start: Optional[datetime] = None) -> List[str]:
        """
        Verifica issues de backup baseado nos últimos backups e recovery model.
        Retorna lista de issues encontradas.
        """
        issues: List[str] = []
        
        def hours_since(dt):
            try:
                return round((now - dt).total_seconds() / 3600.0, 1) if dt else None
            except Exception:
                return None
        
        hrs_full = hours_since(last_full) if last_full else None
        hrs_diff = hours_since(last_diff) if last_diff else None
        hrs_log = hours_since(last_log) if last_log else None
        
        # Heurísticas simples
        if last_full is None:
            issues.append('Sem FULL nos últimos dias')
        elif hrs_full is not None and hrs_full > (self.full_sla_days * 24):
            issues.append('FULL >7d')

        # Regras de LOG dependem do recovery model
        requires_log = recovery_model.upper() in ('FULL', 'BULK_LOGGED')
        if requires_log:
            if last_log is None:
                issues.append('Sem LOG nos últimos dias')
            elif hrs_log is not None and hrs_log > self.log_sla_hours:
                # Verificar se havia FULL/DIFF rodando quando LOG deveria ter rodado
                blocking_info = self._check_log_blocked_by_full_diff(
                    last_log, last_full, last_diff, now, 
                    last_full_start, last_diff_start
                )
                if blocking_info:
                    issues.append(f'LOG >{self.log_sla_hours}h (bloqueado por {blocking_info})')
                else:
                    issues.append(f'LOG >{self.log_sla_hours}h')

        # Regras de DIFF (informativas com SLA padrão 12h)
        # IMPORTANTE: Considerar o horário esperado do próximo backup
        # Se o último DIFF foi ontem às 22:52, o próximo é esperado hoje às 22:52
        # Não é issue se ainda não passou do horário esperado
        
        # Verificar se um FULL foi executado recentemente (últimas 24 horas)
        full_recent = (last_full is not None and 
                      hrs_full is not None and 
                      hrs_full < 24)
        
        if last_diff is None:
            # Só marcar como issue se não houver FULL recente
            # Se houver FULL recente, o DIFF será executado amanhã (não é issue)
            if not full_recent:
                issues.append('Sem DIFF nos últimos dias')
        elif hrs_diff is not None and hrs_diff > self.diff_sla_hours:
            # Verificar se já passou do horário esperado do próximo backup
            # Se o último DIFF foi ontem às 22:52, o próximo é esperado hoje às 22:52
            # Só é issue se já passou do horário esperado
            try:
                # Converter last_diff para datetime
                if isinstance(last_diff, datetime):
                    last_diff_dt = last_diff
                elif isinstance(last_diff, str):
                    # Tentar vários formatos
                    try:
                        last_diff_dt = datetime.fromisoformat(last_diff.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        try:
                            last_diff_dt = datetime.strptime(last_diff, '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            last_diff_dt = datetime.strptime(last_diff, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    raise ValueError(f"Formato de data não suportado: {type(last_diff)}")
                
                # Remover timezone se houver
                if last_diff_dt.tzinfo:
                    last_diff_dt = last_diff_dt.replace(tzinfo=None)
                
                # Data do último DIFF
                last_diff_date = last_diff_dt.date()
                
                # Horário esperado do próximo DIFF (mesmo horário, dia seguinte)
                expected_next_date = last_diff_date + timedelta(days=1)
                expected_next_datetime = datetime.combine(expected_next_date, last_diff_dt.time())
                
                # Se já passou do horário esperado, é issue
                # Se ainda não passou, não é issue (backup ainda pode acontecer)
                if now < expected_next_datetime:
                    # Ainda não passou do horário esperado, não é issue
                    # Exemplo: último DIFF foi ontem 22:52, esperado hoje 22:52, agora são 16:13 -> não é issue
                    pass
                else:
                    # Já passou do horário esperado
                    if not full_recent:
                        issues.append(f'DIFF >{self.diff_sla_hours}h')
            except Exception as e:
                # Se der erro ao calcular horário esperado, usar lógica antiga
                logger.debug(f"Erro ao calcular horário esperado do DIFF: {e}")
                if not full_recent:
                    issues.append(f'DIFF >{self.diff_sla_hours}h')
        
        return issues
    
    def _check_log_blocked_by_full_diff(self, last_log: datetime, last_full: Optional[datetime],
                                        last_diff: Optional[datetime], now: datetime,
                                        last_full_start: Optional[datetime] = None,
                                        last_diff_start: Optional[datetime] = None) -> Optional[str]:
        """
        Verifica se o backup LOG não rodou porque havia FULL/DIFF em execução.
        Retorna o tipo de backup que bloqueou ('FULL' ou 'DIFF') ou None se não houver bloqueio.
        
        Lógica simplificada (sem acesso a backup_start_date):
        - Se o último LOG foi há mais de 2 horas
        - E havia um FULL/DIFF que terminou depois do último LOG
        - E esse FULL/DIFF foi recente (últimas 6 horas)
        - Então é provável que o LOG foi bloqueado pelo FULL/DIFF
        
        Nota: Esta é uma heurística. Para detecção precisa, seria necessário
        verificar backup_start_date do FULL/DIFF, mas isso requer query adicional.
        """
        if not last_log:
            return None
        
        # Calcular horas desde o último LOG
        try:
            hours_since_log = (now - last_log).total_seconds() / 3600.0
        except Exception:
            return None
        
        # Só verificar se LOG está atrasado (>2 horas)
        if hours_since_log <= 2:
            return None
        
        # Verificar FULL: se estava rodando quando LOG deveria ter rodado
        if last_full and last_full_start:
            try:
                # FULL que terminou depois do último LOG
                if last_full > last_log:
                    # Verificar se FULL estava rodando quando o próximo LOG deveria ter rodado
                    # (LOG deveria rodar a cada 1-2 horas após o último)
                    expected_next_log_time = last_log + timedelta(hours=2)
                    
                    # Se FULL começou antes ou durante o período esperado do próximo LOG
                    # E terminou depois do último LOG, então bloqueou o LOG
                    if (last_full_start <= expected_next_log_time + timedelta(hours=1) and
                        last_full > last_log):
                        hours_since_full = (now - last_full).total_seconds() / 3600.0
                        # Se FULL terminou recentemente (últimas 6 horas), confirma bloqueio
                        if hours_since_full < 6:
                            return 'FULL'
            except Exception:
                pass
        
        # Verificar DIFF: mesma lógica
        if last_diff and last_diff_start:
            try:
                if last_diff > last_log:
                    expected_next_log_time = last_log + timedelta(hours=2)
                    if (last_diff_start <= expected_next_log_time + timedelta(hours=1) and
                        last_diff > last_log):
                        hours_since_diff = (now - last_diff).total_seconds() / 3600.0
                        if hours_since_diff < 6:
                            return 'DIFF'
            except Exception:
                pass
        
        # Fallback: se não temos backup_start_date, usar heurística simplificada
        if last_full and not last_full_start:
            try:
                if last_full > last_log:
                    hours_since_full = (now - last_full).total_seconds() / 3600.0
                    if hours_since_full < 6:
                        expected_next_log_time = last_log + timedelta(hours=2)
                        if last_full <= expected_next_log_time + timedelta(hours=4):
                            return 'FULL'
            except Exception:
                pass
        
        if last_diff and not last_diff_start:
            try:
                if last_diff > last_log:
                    hours_since_diff = (now - last_diff).total_seconds() / 3600.0
                    if hours_since_diff < 6:
                        expected_next_log_time = last_log + timedelta(hours=2)
                        if last_diff <= expected_next_log_time + timedelta(hours=4):
                            return 'DIFF'
            except Exception:
                pass
        
        return None

    async def _analyze_backups_for_server(self, server_id: str, lookback_days: int, 
                                         ag_databases: Optional[List[str]] = None,
                                         include_system_databases: bool = False) -> Dict:
        """
        Analisa backups para um servidor específico.
        Se ag_databases for fornecido, analisa apenas essas databases (para Always On).
        IMPORTANTE: Para Always On, busca backups de TODOS os nodes (usando server_name do backup).
        """
        start_time = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Se for Always On e tiver databases específicas, filtrar por elas
        db_filter = ""
        if ag_databases:
            db_list = "', '".join(ag_databases)
            db_filter = f"AND d.name IN ('{db_list}')"
        
        # Incluir ou excluir bases de sistema
        sys_filter = "" if include_system_databases else "AND d.database_id > 4"
        
        # Query otimizada: usa OUTER APPLY TOP 1 em vez de CTE com ROW_NUMBER()
        # CROSS APPLY TOP 1 é MUITO mais eficiente porque SQL Server faz Index Seek + Top 1
        # em vez de escanear toda a tabela backupset e calcular ROW_NUMBER() para cada linha.
        # Isso resolve o timeout em servidores Always On com muitos databases (ex: 25+ bases).
        query = f"""
            SELECT
                d.name AS database_name,
                d.recovery_model_desc AS recovery_model,
                lf.backup_finish_date AS last_full,
                li.backup_finish_date AS last_diff,
                ll.backup_finish_date AS last_log,
                lf.backup_start_date AS last_full_start,
                li.backup_start_date AS last_diff_start,
                lf.server_name AS full_backup_server,
                li.server_name AS diff_backup_server,
                ll.server_name AS log_backup_server,
                -- 2026-08-17: origem do ultimo backup por tipo (ferramenta externa vs nativo).
                -- backupmediafamily por media_set_id e' seek na PK (barato).
                lf.user_name AS full_user_name,  mf.device_type AS full_device_type,  mf.physical_device_name AS full_physical_device,
                li.user_name AS diff_user_name,  mi.device_type AS diff_device_type,  mi.physical_device_name AS diff_physical_device,
                ll.user_name AS log_user_name,   ml.device_type AS log_device_type,   ml.physical_device_name AS log_physical_device
            FROM sys.databases d
            OUTER APPLY (
                SELECT TOP 1 bs.backup_finish_date, bs.backup_start_date, bs.server_name, bs.user_name, bs.media_set_id
                FROM msdb.dbo.backupset bs
                WHERE bs.database_name = d.name AND bs.type = 'D'
                ORDER BY bs.backup_finish_date DESC
            ) lf
            OUTER APPLY (
                SELECT TOP 1 bs.backup_finish_date, bs.backup_start_date, bs.server_name, bs.user_name, bs.media_set_id
                FROM msdb.dbo.backupset bs
                WHERE bs.database_name = d.name AND bs.type = 'I'
                ORDER BY bs.backup_finish_date DESC
            ) li
            OUTER APPLY (
                SELECT TOP 1 bs.backup_finish_date, bs.backup_start_date, bs.server_name, bs.user_name, bs.media_set_id
                FROM msdb.dbo.backupset bs
                WHERE bs.database_name = d.name AND bs.type = 'L'
                ORDER BY bs.backup_finish_date DESC
            ) ll
            OUTER APPLY (
                SELECT TOP 1 bmf.device_type, bmf.physical_device_name
                FROM msdb.dbo.backupmediafamily bmf
                WHERE bmf.media_set_id = lf.media_set_id
                ORDER BY bmf.family_sequence_number
            ) mf
            OUTER APPLY (
                SELECT TOP 1 bmf.device_type, bmf.physical_device_name
                FROM msdb.dbo.backupmediafamily bmf
                WHERE bmf.media_set_id = li.media_set_id
                ORDER BY bmf.family_sequence_number
            ) mi
            OUTER APPLY (
                SELECT TOP 1 bmf.device_type, bmf.physical_device_name
                FROM msdb.dbo.backupmediafamily bmf
                WHERE bmf.media_set_id = ll.media_set_id
                ORDER BY bmf.family_sequence_number
            ) ml
            WHERE d.state = 0 {sys_filter} {db_filter}
            ORDER BY d.name;
            """

        result = await self.sql_monitoring.execute_query(server_id, query)
        if not result or not result.get('success'):
            return {'success': False, 'error': result.get('error', 'query-failed'), 'rows': []}

        return {'success': True, 'rows': result.get('rows', [])}

    async def analyze_server_backups(self, server_id: str, lookback_days: int = 7,
                                     include_system_databases: bool = False) -> Dict:
        """
        Retorna status de backup por database e possíveis issues.
        Para Always On: analisa apenas o servidor atual, mas usa server_name do backup
        para identificar onde foi executado (como no backupCheck.py).

        Performance Optimizations:
        - Paraleliza AG databases query + Backup analysis (quando possível)
        - Leitura assíncrona de TDP log em thread separada
        """
        import time as _time
        _t_start = _time.perf_counter()
        logger.info(f"🚨 INÍCIO analyze_server_backups para {server_id} (lookback={lookback_days})")
        try:
            # 1. Verificar se é Always On
            _t1 = _time.perf_counter()
            alwayson_info = await self._check_alwayson_and_get_replicas(server_id)
            _t2 = _time.perf_counter()
            logger.info(f"⏱ STEP 1 - AlwaysOn check: {_t2-_t1:.1f}s (is_ag={alwayson_info.get('is_alwayson') if alwayson_info else False})")

            if alwayson_info and alwayson_info.get('is_alwayson'):
                # É Always On - usar abordagem simplificada: analisar apenas servidor atual
                # mas usar server_name do backup para identificar onde foi executado
                ag_name = alwayson_info.get('ag_name', 'N/A')
                is_primary = alwayson_info.get('current_is_primary', False)
                primary_replica = alwayson_info.get('primary_replica', 'N/A')
                logger.info(f"✅ Servidor {server_id} é Always On (AG: {ag_name}, Primary: {primary_replica}, Current is Primary: {is_primary}). Analisando backups usando server_name do backup.")
                logger.info(f"🔍 DEBUG CRÍTICO: Entrando no bloco Always On (linha 504-797)")

                # 🚀 OTIMIZAÇÃO 1: Paralelizar AG databases query + Backup analysis + TDP log read
                ag_name = alwayson_info.get('ag_name')
                # 🔧 FIX: execute_query() não aceita 'params', usar string interpolation com escape SQL
                ag_name_escaped = ag_name.replace("'", "''") if ag_name else ""

                ag_databases_query = f"""
                SELECT DISTINCT adc.database_name
                FROM sys.availability_groups ag
                INNER JOIN sys.availability_databases_cluster adc ON ag.group_id = adc.group_id
                WHERE ag.name = '{ag_name_escaped}';
                """

                server_host = self._extract_server_host(server_id)

                # Executar 2 queries + TDP log read em paralelo
                _t3 = _time.perf_counter()
                ag_db_task = self.sql_monitoring.execute_query(server_id, ag_databases_query)
                tdp_task = asyncio.get_event_loop().run_in_executor(_io_executor, self._read_tdp_log, server_host)

                # Aguardar AG databases primeiro (backup analysis depende dele)
                try:
                    ag_db_result = await ag_db_task
                except Exception as e:
                    logger.warning(f"Erro ao buscar databases do AG: {e}")
                    ag_db_result = None
                _t4 = _time.perf_counter()
                logger.info(f"⏱ STEP 2 - AG databases query: {_t4-_t3:.1f}s")

                ag_databases = []
                if ag_db_result and ag_db_result.get('success'):
                    ag_databases = [row.get('database_name') for row in ag_db_result.get('rows', []) if row.get('database_name')]

                # Agora paralelizar backup analysis + TDP log (se ainda não terminou)
                _t5 = _time.perf_counter()
                backup_task = self._analyze_backups_for_server(
                    server_id, lookback_days, ag_databases, include_system_databases
                )

                # Aguardar ambos em paralelo com tratamento de erro individual
                try:
                    result, tdp_log_lines = await asyncio.gather(backup_task, tdp_task, return_exceptions=False)
                except Exception as e:
                    logger.error(f"Erro na execução paralela (backup + TDP): {e}")
                    # Fallback: executar sequencialmente
                    logger.warning("Fallback para execução sequencial...")
                    result = await backup_task if not backup_task.done() else backup_task.result()
                    tdp_log_lines = []
                _t6 = _time.perf_counter()
                logger.info(f"⏱ STEP 3 - Backup query + TDP log (paralelo): {_t6-_t5:.1f}s")

                logger.info(f"🔍 DEBUG: Resultado de _analyze_backups_for_server: success={result.get('success')}, rows={len(result.get('rows', []))}")
                if not result.get('success'):
                    logger.error(f"❌ DEBUG CRÍTICO: _analyze_backups_for_server falhou! Retornando erro. Error={result.get('error')}")
                    return {'success': False, 'error': result.get('error', 'query-failed')}

                rows = result.get('rows', [])
                statuses: List[DatabaseBackupStatus] = []
                now = datetime.now()
                
                # Identificar se o servidor atual é primário ou secundário
                is_current_primary = alwayson_info.get('current_is_primary', False)
                primary_replica = alwayson_info.get('primary_replica', '')
                
                # Função auxiliar para converter data string para datetime
                def parse_backup_date(date_value):
                    """Converte data de backup (string ou datetime) para datetime"""
                    if date_value is None:
                        return None
                    
                    # Se já é datetime, retornar direto
                    if isinstance(date_value, datetime):
                        return date_value
                    
                    # Se for string, tentar vários formatos
                    if isinstance(date_value, str):
                        # Remover espaços extras
                        date_value = date_value.strip()
                        
                        # Lista de formatos mais comuns primeiro
                        formats = [
                            '%Y-%m-%d %H:%M:%S.%f',  # 2025-11-07 20:11:38.123456
                            '%Y-%m-%d %H:%M:%S',     # 2025-11-07 20:11:38
                            '%Y-%m-%d',              # 2025-11-04 ✅ NOVO!
                            '%Y-%m-%dT%H:%M:%S.%f',  # 2025-11-07T20:11:38.123456
                            '%Y-%m-%dT%H:%M:%S',     # 2025-11-07T20:11:38
                        ]
                        
                        # Tentar cada formato
                        for fmt in formats:
                            try:
                                return datetime.strptime(date_value, fmt)
                            except (ValueError, TypeError):
                                continue

                        # Tentar formato ISO (mais flexível)
                        try:
                            # Remover 'Z' se houver e adicionar timezone
                            if date_value.endswith('Z'):
                                date_value = date_value[:-1]
                            # fromisoformat não aceita 'Z', então removemos
                            return datetime.fromisoformat(date_value)
                        except (ValueError, TypeError):
                            pass
                        
                        # ÚLTIMO RECURSO: Se falhar tudo, logar ERRO e retornar None
                        logger.error(f"⚠️ FALHA NO PARSE DA DATA: '{date_value}' - tipo: {type(date_value)} - NÃO conseguiu parsear com nenhum formato!")
                        return None
                    
                    # Se não for string nem datetime, logar e retornar None
                    logger.error(f"⚠️ TIPO DE DATA INESPERADO: '{date_value}' - tipo: {type(date_value)}")
                    return None
                
                for row in rows:
                    db_name = row.get('database_name')
                    recovery_model = row.get('recovery_model', 'UNKNOWN')
                    
                    # Converter datas para datetime
                    last_full = parse_backup_date(row.get('last_full'))
                    last_diff = parse_backup_date(row.get('last_diff'))
                    last_log = parse_backup_date(row.get('last_log'))
                    # NOVO: Datas de início dos backups (para detectar bloqueio de LOG)
                    last_full_start = parse_backup_date(row.get('last_full_start'))
                    last_diff_start = parse_backup_date(row.get('last_diff_start'))
                    
                    # Pegar server_name onde cada backup foi executado
                    full_backup_server = row.get('full_backup_server') or ''
                    diff_backup_server = row.get('diff_backup_server') or ''
                    log_backup_server = row.get('log_backup_server') or ''

                    # Log resumido apenas em nível DEBUG (não INFO) para evitar spam
                    logger.debug(f"📅 {db_name}: FULL={last_full}, DIFF={last_diff}, LOG={last_log}")
                    
                    # IMPORTANTE: Para Always On, a lógica depende se estamos no primário ou secundário:
                    #
                    # PRIMÁRIO: Aplicar SLAs normais (FULL, DIFF, LOG) — o primário TEM os dados
                    #   reais no seu msdb e deve detectar gaps/atrasos normalmente.
                    #
                    # SECUNDÁRIO: Lógica leniente — o msdb local pode não ter os backups recentes
                    #   (que foram feitos no primário). Só marcar issue se:
                    #   1. Não há backup (data é None) - backup não existe em NENHUM node
                    #   2. OU o backup está MUITO antigo (mais de 7 dias para FULL)
                    #   Para DIFF e LOG, se há backup (mesmo que antigo), NÃO é issue

                    if is_current_primary:
                        # PRIMÁRIO: usar lógica completa de SLA (mesma dos servidores não-AG)
                        issues = self._check_backup_issues(
                            last_full, last_diff, last_log, recovery_model, now,
                            last_full_start, last_diff_start
                        )
                    else:
                        # SECUNDÁRIO AG — Wave I.4 (2026-05-19): msdb LOCAL nao tem
                        # dados fiaveis. Backups correm no primario por design
                        # (Backup Preference=Primary). Records que estejam em msdb
                        # local sao pre-failover (stale) ou COPY_ONLY. Bloco
                        # anterior tinha "logica leniente" mas ainda gerava issues
                        # quando last_diff/last_log eram None ou last_full >7d —
                        # falsos positivos garantidos. Wave I.4: supressao total.
                        # A supervisao de SLA pertence ao primario (que reporta o
                        # estado correcto). Single source of truth.
                        issues = []
                    
                    # Log apenas se houver issues (evita spam)
                    if issues:
                        logger.debug(f"⚠️ {db_name}: Issues Always On: {issues}")
                    
                    # Se estiver no secundário e não houver issues, adicionar informação sobre primário
                    backup_info_message = None
                    if not is_current_primary and not issues:
                        # Se estiver no secundário e não houver problemas, informar que backup foi feito no primário
                        if last_full or last_diff or last_log:
                            # Verificar se o backup foi feito no primário (usando server_name do backup)
                            backup_server = full_backup_server or diff_backup_server or log_backup_server
                            if backup_server:
                                # Normalizar nomes para comparação
                                backup_server_normalized = self._normalize_server_name(backup_server)
                                primary_normalized = self._normalize_server_name(primary_replica)
                                if backup_server_normalized == primary_normalized:
                                    backup_info_message = f"Backup executado no node primário: {primary_replica}"
                                else:
                                    backup_info_message = f"Backup executado em: {backup_server}"
                            else:
                                backup_info_message = f"Backup executado no node primário: {primary_replica}"
                    
                    def to_iso(dt):
                        try:
                            return dt.isoformat() if dt else None
                        except Exception:
                            return None
                    
                    def hours_since(dt):
                        try:
                            return round((now - dt).total_seconds() / 3600.0, 1) if dt else None
                        except Exception:
                            return None
                    
                    # TDP: coletar erros recentes vinculados à base somente se houver issues
                    tdp_error_count = 0
                    tdp_samples: List[str] = []
                    if issues and tdp_log_lines:
                        samples = self._extract_tdp_errors(tdp_log_lines, db_name, lookback_days)
                        tdp_error_count = len(samples)
                        tdp_samples = samples[:2]
                    
                    # Adicionar informação sobre Always On se aplicável
                    backup_status = DatabaseBackupStatus(
                        database_name=db_name,
                        recovery_model=recovery_model or 'UNKNOWN',
                        last_full=to_iso(last_full),
                        last_diff=to_iso(last_diff),
                        last_log=to_iso(last_log),
                        hours_since_last_full=hours_since(last_full) if last_full else None,
                        hours_since_last_diff=hours_since(last_diff) if last_diff else None,
                        hours_since_last_log=hours_since(last_log) if last_log else None,
                        issues=issues,
                        tdp_error_count=tdp_error_count,
                        tdp_samples=tdp_samples,
                        alwayson_info=backup_info_message,  # Mensagem informativa sobre Always On
                        is_ag_secondary=(alwayson_info is not None and not is_current_primary),  # Wave I.4: incondicional, true sempre que AG secondary local (independente de issues)
                        backup_source=_backup_source_from_row(row)  # 2026-08-17: origem (TDP/VDI vs nativo)
                    )
                    
                    statuses.append(backup_status)
                
                # Resumo
                total = len(statuses)
                with_issues = sum(1 for s in statuses if s.issues)
                logger.info(f"🔍 DEBUG: Processados {total} databases, {with_issues} com issues")

                # Montar contexto de aviso para o frontend
                backup_preference = alwayson_info.get('backup_preference', 0)
                backup_preference_desc = alwayson_info.get('backup_preference_desc', 'Primary')
                logger.info(f"🔍 DEBUG: backup_preference={backup_preference}, desc={backup_preference_desc}")

                # Criar mensagem contextual baseada no papel e preferência
                warning_context = None
                if not is_current_primary:
                    # Servidor secundário
                    logger.info(f"🔍 DEBUG: Servidor é SECUNDÁRIO, criando warning_context laranja")
                    warning_context = {
                        'type': 'secondary',
                        'title': '⚠️ Réplica Secundária do Always On',
                        'message': f'Este servidor é uma réplica SECUNDÁRIA do Availability Group "{ag_name}".',
                        'primary_server': primary_replica,
                        'backup_preference': backup_preference_desc,
                        'recommendation': self._get_backup_recommendation(backup_preference, False)
                    }
                    logger.info(f"🔍 DEBUG: warning_context criado: {warning_context}")
                else:
                    # Servidor primário
                    logger.debug(f"🔍 DEBUG: Servidor é PRIMÁRIO")
                    if backup_preference != 0:  # 0 = Primary
                        # Primário, mas backup configurado em secundário
                        logger.debug(f"🔍 DEBUG: Primário com backup em secundário, criando warning_context azul")
                        warning_context = {
                            'type': 'primary_with_secondary_backup',
                            'title': 'ℹ️ Réplica Primária (Backup em Secundário)',
                            'message': f'Este servidor é a réplica PRIMÁRIA do AG "{ag_name}".',
                            'backup_preference': backup_preference_desc,
                            'recommendation': self._get_backup_recommendation(backup_preference, True)
                        }
                        logger.info(f"🔍 DEBUG: warning_context criado: {warning_context}")
                    else:
                        logger.debug(f"🔍 DEBUG: Primário com backup no primary, SEM warning_context")

                _t_total = _time.perf_counter() - _t_start
                logger.info(f"⏱ TOTAL analyze_server_backups({server_id}): {_t_total:.1f}s (AlwaysOn path)")
                return {
                    'success': True,
                    'server_id': server_id,
                    'is_alwayson': True,
                    'ag_name': ag_name,
                    'current_is_primary': is_current_primary,
                    'primary_replica': primary_replica,
                    'backup_preference': backup_preference,
                    'backup_preference_desc': backup_preference_desc,
                    'warning_context': warning_context,
                    'total_databases': total,
                    'databases_with_issues': with_issues,
                    'items': [asdict(s) for s in statuses]
                }
            
            # Não é Always On - análise normal
            _t3 = _time.perf_counter()
            server_host = self._extract_server_host(server_id)

            backup_task = self._analyze_backups_for_server(
                server_id, lookback_days, include_system_databases=include_system_databases
            )
            tdp_task = asyncio.get_event_loop().run_in_executor(_io_executor, self._read_tdp_log, server_host)

            # Aguardar ambos em paralelo com tratamento de erro
            try:
                result, tdp_log_lines = await asyncio.gather(backup_task, tdp_task, return_exceptions=False)
            except Exception as e:
                logger.error(f"Erro na execução paralela (backup + TDP) standalone: {e}")
                # Fallback: executar sequencialmente
                logger.warning("Fallback para execução sequencial...")
                try:
                    result = await backup_task if not backup_task.done() else backup_task.result()
                except Exception:
                    result = {'success': False, 'error': str(e)}
                tdp_log_lines = []

            if not result.get('success'):
                return {'success': False, 'error': result.get('error', 'query-failed')}

            rows = result.get('rows', [])
            statuses: List[DatabaseBackupStatus] = []
            now = datetime.now()

            def _parse_dt(value):
                # execute_query() serializa datetime -> string ISO (monitoring.py:277).
                # Sem este parse, to_iso()/hours_since() engolem o AttributeError e
                # devolvem None, e _check_backup_issues nao dispara "Sem FULL/LOG"
                # (string nao e' None) -- datas N/A + zero issues em todos os
                # servidores standalone. O caminho AG ja parseia (parse_backup_date).
                if isinstance(value, datetime):
                    return value
                if isinstance(value, str) and value:
                    try:
                        return datetime.fromisoformat(value.rstrip('Z'))
                    except ValueError:
                        logger.error(f"⚠️ FALHA NO PARSE DA DATA (standalone): '{value}'")
                        return None
                return None

            for row in rows:
                name = str(row.get('database_name'))
                recovery_model = str(row.get('recovery_model') or 'UNKNOWN')
                last_full = _parse_dt(row.get('last_full'))
                last_diff = _parse_dt(row.get('last_diff'))
                last_log = _parse_dt(row.get('last_log'))
                # NOVO: Datas de início dos backups (para detectar bloqueio de LOG)
                last_full_start = _parse_dt(row.get('last_full_start'))
                last_diff_start = _parse_dt(row.get('last_diff_start'))

                def to_iso(dt):
                    try:
                        return dt.isoformat()
                    except Exception:
                        return None

                def hours_since(dt):
                    try:
                        return round((now - dt).total_seconds() / 3600.0, 1) if dt else None
                    except Exception:
                        return None

                # Usar função centralizada para verificar issues (inclui detecção de bloqueio de LOG)
                issues = self._check_backup_issues(
                    last_full, last_diff, last_log, recovery_model, now,
                    last_full_start, last_diff_start
                )
                
                hrs_full = hours_since(last_full) if last_full else None
                hrs_diff = hours_since(last_diff) if last_diff else None
                hrs_log = hours_since(last_log) if last_log else None
                
                # Issues já foram verificadas pela função _check_backup_issues acima
                # (inclui detecção de bloqueio de LOG por FULL/DIFF)
                
                # NOVO: Verificar gaps históricos significativos (últimos 7 dias)
                # Buscar gaps LOG históricos que não foram justificados
                if recovery_model.upper() in ('FULL', 'BULK_LOGGED'):
                    historical_gaps = await self._check_historical_log_gaps(server_id, name, lookback_days)
                    for gap_info in historical_gaps:
                        issues.append(gap_info)

                # TDP: coletar erros recentes vinculados à base somente se houver issues
                tdp_error_count = 0
                tdp_samples: List[str] = []
                if issues and tdp_log_lines:
                    samples = self._extract_tdp_errors(tdp_log_lines, name, lookback_days)
                    tdp_error_count = len(samples)
                    tdp_samples = samples[:2]

                statuses.append(DatabaseBackupStatus(
                    database_name=name,
                    recovery_model=recovery_model,
                    last_full=to_iso(last_full) if last_full else None,
                    last_diff=to_iso(last_diff) if last_diff else None,
                    last_log=to_iso(last_log) if last_log else None,
                    hours_since_last_full=hrs_full,
                    hours_since_last_diff=hrs_diff,
                    hours_since_last_log=hrs_log,
                    issues=issues,
                    tdp_error_count=tdp_error_count,
                    tdp_samples=tdp_samples,
                    backup_source=_backup_source_from_row(row)  # 2026-08-17: origem (TDP/VDI vs nativo)
                ))

            # Resumo
            total = len(statuses)
            with_issues = sum(1 for s in statuses if s.issues)
            _t_total = _time.perf_counter() - _t_start
            logger.info(f"⏱ TOTAL analyze_server_backups({server_id}): {_t_total:.1f}s (Standalone path)")
            return {
                'success': True,
                'server_id': server_id,
                'total_databases': total,
                'databases_with_issues': with_issues,
                'items': [asdict(s) for s in statuses]
            }

        except Exception as e:
            _t_total = _time.perf_counter() - _t_start
            logger.error(f"⏱ TOTAL analyze_server_backups({server_id}): ERRO após {_t_total:.1f}s")
            logger.error(f"❌ EXCEÇÃO CAPTURADA no analyze_server_backups: {e}", exc_info=True)
            logger.error(f"❌ Tipo da exceção: {type(e).__name__}")
            logger.error(f"❌ Servidor: {server_id}")
            return {'success': False, 'error': str(e), 'server_id': server_id}

    async def _get_all_historical_log_gaps(self, server_id: str) -> Dict[str, List[Dict]]:
        """
        Busca TODOS os gaps históricos de LOG backup UMA ÚNICA VEZ.
        Retorna um dicionário: {database_name: [lista de gaps]}
        OTIMIZAÇÃO: Antes era chamado N vezes (uma por database), agora é chamado 1 vez.
        """
        try:
            from modules.monitoring.queries import SQLQueries

            # Executar query de gaps LOG apenas UMA vez
            result = await self.sql_monitoring.execute_query(server_id, SQLQueries.BACKUP_LOG_GAPS_ANALYSIS)
            if not result or not result.get('success'):
                return {}

            rows = result.get('rows', [])
            if not rows:
                return {}

            # Agrupar gaps por database
            gaps_by_db: Dict[str, List[Dict]] = {}
            for row in rows:
                db_name = row.get('DatabaseName')
                if db_name:
                    if db_name not in gaps_by_db:
                        gaps_by_db[db_name] = []
                    gaps_by_db[db_name].append(row)

            return gaps_by_db

        except Exception as e:
            logger.debug(f"Erro ao buscar gaps históricos para {server_id}: {e}")
            return {}

    def _filter_historical_log_gaps(self, gaps_for_db: List[Dict], database_name: str, lookback_days: int) -> List[str]:
        """
        Filtra gaps históricos para uma database específica.
        Usa os dados já carregados (não faz nova query).
        """
        if not gaps_for_db:
            return []

        gaps_issues = []
        for row in gaps_for_db:
            severity = row.get('Severity', '').upper()
            gap_hours = row.get('GapHours')
            blocking_type = row.get('BlockingBackupType')
            last_log_backup = row.get('LastLogBackup')

            # Só considerar gaps HIGH ou CRITICAL que não foram justificados
            if severity in ('HIGH', 'CRITICAL') and not blocking_type:
                if last_log_backup:
                    try:
                        if isinstance(last_log_backup, str):
                            last_log_dt = datetime.fromisoformat(last_log_backup.replace('Z', '+00:00'))
                            if last_log_dt.tzinfo:
                                last_log_dt = last_log_dt.replace(tzinfo=None)
                        else:
                            last_log_dt = last_log_backup

                        days_ago = (datetime.now() - last_log_dt).days
                        if days_ago <= lookback_days:
                            gap_msg = f'Gap histórico LOG de {gap_hours}h sem justificativa'
                            gaps_issues.append(gap_msg)
                    except Exception as e:
                        logger.debug(f"Erro ao processar gap histórico para {database_name}: {e}")

        return gaps_issues

    async def _check_historical_log_gaps(self, server_id: str, database_name: str, lookback_days: int) -> List[str]:
        """
        DEPRECATED: Use _get_all_historical_log_gaps + _filter_historical_log_gaps
        Mantido para compatibilidade, mas agora usa cache interno.
        """
        # Se não temos cache, buscar todos os gaps
        if not hasattr(self, '_gaps_cache') or self._gaps_cache.get('server_id') != server_id:
            self._gaps_cache = {
                'server_id': server_id,
                'gaps': await self._get_all_historical_log_gaps(server_id)
            }

        gaps_for_db = self._gaps_cache.get('gaps', {}).get(database_name, [])
        return self._filter_historical_log_gaps(gaps_for_db, database_name, lookback_days)

    def _extract_server_host(self, server_id: str) -> str:
        try:
            return server_id.split('_')[0]
        except Exception:
            return server_id

    def _read_backup_tool_log(self, server_host: str) -> Optional[List[str]]:
        """Lê log da ferramenta de backup (TDP, Veeam, etc.) via UNC.
        Só executa se backup_tool estiver habilitado na configuração.
        Proteção contra timeout SMB com cache de indisponibilidade."""
        global _tdp_unavailable_cache

        # Se ferramenta de backup não está configurada/habilitada, skip
        if not self.backup_tool_enabled or not self.backup_tool_log_path:
            return None

        try:
            # Verificar cache de servidores indisponíveis (evita timeout SMB repetido)
            cached_until = _tdp_unavailable_cache.get(server_host)
            if cached_until and datetime.now() < cached_until:
                logger.debug(f"Backup tool log skip (cached unavailable): {server_host}")
                return None

            local = self.backup_tool_log_path
            # PyArmor BCC compatibility: extract .strip() with backslash arg out of
            # f-string expression part (Python 3.11 PEP 701 limitation).
            if ':' in local:
                drive, rest = local.split(':', 1)
                rest_clean = rest.strip('\\/')
                unc = f"\\\\{server_host}\\{drive}$\\{rest_clean}"
            else:
                local_clean = local.strip('\\/')
                unc = f"\\\\{server_host}\\{local_clean}"

            # Timeout de 5s para verificar existência do arquivo UNC
            # (os.path.exists em UNC pode travar por 30-60s se share inacessível)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as check_executor:
                future = check_executor.submit(os.path.exists, unc)
                try:
                    exists = future.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"Backup tool log UNC timeout (5s) para {server_host} - cached 30min")
                    _tdp_unavailable_cache[server_host] = datetime.now() + _TDP_UNAVAILABLE_TTL
                    return None

            if not exists:
                _tdp_unavailable_cache[server_host] = datetime.now() + _TDP_UNAVAILABLE_TTL
                logger.debug(f"Backup tool log não encontrado em {server_host} - cached 30min")
                return None

            with open(unc, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines()[-5000:]
        except Exception as e:
            logger.debug(f"Backup tool log read failed for {server_host}: {e}")
            _tdp_unavailable_cache[server_host] = datetime.now() + _TDP_UNAVAILABLE_TTL
            return None

    # Alias para compatibilidade
    def _read_tdp_log(self, server_host: str) -> Optional[List[str]]:
        return self._read_backup_tool_log(server_host)

    def _extract_tdp_errors(self, lines: List[str], db_name: str, lookback_days: int) -> List[str]:
        error_codes = [
            'ANS1236E', 'ANS4987E', 'ANS5101E', 'ANS5250E', 'ANS1005E',
            'ANS1799E', 'ANS1512E', 'VDI_E_ABORT', 'VDI_E_CLIENT_ABORT',
            'VDI_E_TIMEOUT', 'ANS1315W', 'ANS5216E', 'ANS9020E', 'ANS1802E'
        ]
        now = datetime.now()
        start = now - timedelta(days=lookback_days)
        results: List[str] = []
        date_re = re.compile(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})")
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if not any(code in line for code in error_codes):
                continue
            # Preferir linhas que mencionem o DB, mas aceitar erros gerais VDI
            if db_name.lower() not in line.lower() and 'VDI' not in line:
                continue
            m = date_re.search(line)
            if m:
                try:
                    dt = datetime.strptime(m.group(1), '%m/%d/%Y %H:%M:%S')
                    if start <= dt <= now:
                        results.append(line[:220])
                except Exception:
                    continue
        return results


