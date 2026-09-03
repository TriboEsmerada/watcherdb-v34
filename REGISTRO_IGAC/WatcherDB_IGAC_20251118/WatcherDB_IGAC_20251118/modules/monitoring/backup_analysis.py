"""
TapOS Backup Analysis - Análise de Backups MSDB
Inspirado no analisador de tickets anexado pelo usuário, focado em endpoints rápidos para o dashboard.
"""
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import re

logger = logging.getLogger(__name__)


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


class BackupAnalysisEngine:
    """Engine simples para análise de backups usando msdb.dbo.backupset."""

    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        self.tdp_log_path = r"C:\\Program Files\\tivoli\\TSM\\TDPSql\\dsierror.log"
        # SLAs padrão
        self.log_sla_hours = 2            # LOG deve ocorrer a cada ~30–60min (tolerância 2h)
        self.diff_sla_hours = 12          # DIFF típico a cada 12h
        self.full_sla_days = 7            # FULL semanal

    async def _check_alwayson_and_get_replicas(self, server_id: str) -> Optional[Dict]:
        """
        Verifica se o servidor é Always On e retorna informações sobre primário e secundário.
        Retorna None se não for Always On.
        Usa a query fornecida pelo usuário para identificar o primário.
        """
        try:
            # Query fornecida pelo usuário para identificar primário
            query = """
            SELECT 
                ags.primary_replica,
                ag.name AS ag_name
            FROM sys.availability_groups ag
            JOIN sys.dm_hadr_availability_group_states ags
                ON ag.group_id = ags.group_id;
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query)
            if not result or not result.get('success'):
                return None
            
            rows = result.get('rows', [])
            if not rows:
                return None
            
            # Pegar o primeiro AG (geralmente há apenas um por servidor)
            ag_info = rows[0]
            primary_replica = ag_info.get('primary_replica')
            ag_name = ag_info.get('ag_name')
            
            if not primary_replica or not ag_name:
                return None
            
            # Identificar o servidor atual (normalizar para comparação)
            current_server_id_normalized = self._normalize_server_name(server_id)
            primary_normalized = self._normalize_server_name(primary_replica)
            is_current_primary = (current_server_id_normalized == primary_normalized)
            
            # Buscar todas as réplicas do AG
            replicas_query = """
            SELECT 
                ar.replica_server_name,
                ars.role_desc,
                ars.operational_state_desc
            FROM sys.availability_groups ag
            INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
            INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
            WHERE ag.name = ?
            ORDER BY ars.role_desc;
            """
            
            # Executar query com parâmetro
            replicas_result = await self.sql_monitoring.execute_query(server_id, replicas_query, params=[ag_name])
            if not replicas_result or not replicas_result.get('success'):
                # Se falhar, retornar pelo menos o primário
                return {
                    'is_alwayson': True,
                    'ag_name': ag_name,
                    'primary_replica': primary_replica,
                    'current_is_primary': is_current_primary,
                    'replicas': [{'server_name': primary_replica, 'role': 'PRIMARY'}]
                }
            
            replica_rows = replicas_result.get('rows', [])
            replicas = []
            for rep_row in replica_rows:
                replica_name = rep_row.get('replica_server_name')
                role = rep_row.get('role_desc', '')
                if replica_name:
                    replicas.append({
                        'server_name': replica_name,
                        'role': role
                    })
            
            return {
                'is_alwayson': True,
                'ag_name': ag_name,
                'primary_replica': primary_replica,
                'current_is_primary': is_current_primary,
                'replicas': replicas
            }
            
        except Exception as e:
            logger.debug(f"Erro ao verificar Always On em {server_id}: {e}")
            return None
    
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

    def _check_backup_issues(self, last_full, last_diff, last_log, recovery_model: str, now: datetime) -> List[str]:
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
                    except:
                        try:
                            last_diff_dt = datetime.strptime(last_diff, '%Y-%m-%d %H:%M:%S')
                        except:
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
        
        # Query simplificada: busca backups e inclui server_name do backup mais recente de cada tipo
        # Isso permite identificar onde o backup foi executado (importante para Always On)
        # Abordagem similar ao backupCheck.py: usar server_name do backup para identificar o node
        query = f"""
        WITH latest_backups AS (
                SELECT 
                    bs.database_name,
                    bs.type AS btype,
                bs.backup_finish_date,
                bs.server_name AS backup_server_name,
                ROW_NUMBER() OVER (PARTITION BY bs.database_name, bs.type ORDER BY bs.backup_finish_date DESC) AS rn
                FROM msdb.dbo.backupset bs
                WHERE bs.backup_finish_date >= CONVERT(datetime, '{start_time}')
            )
            SELECT 
                d.name AS database_name,
                d.recovery_model_desc AS recovery_model,
            MAX(CASE WHEN lbk.btype='D' THEN lbk.backup_finish_date END) AS last_full,
            MAX(CASE WHEN lbk.btype='I' THEN lbk.backup_finish_date END) AS last_diff,
            MAX(CASE WHEN lbk.btype='L' THEN lbk.backup_finish_date END) AS last_log,
            MAX(CASE WHEN lbk.btype='D' AND lbk.rn = 1 THEN lbk.backup_server_name END) AS full_backup_server,
            MAX(CASE WHEN lbk.btype='I' AND lbk.rn = 1 THEN lbk.backup_server_name END) AS diff_backup_server,
            MAX(CASE WHEN lbk.btype='L' AND lbk.rn = 1 THEN lbk.backup_server_name END) AS log_backup_server
            FROM sys.databases d
        LEFT JOIN latest_backups lbk ON d.name = lbk.database_name AND lbk.rn = 1
        WHERE d.state = 0 {sys_filter} {db_filter}
            GROUP BY d.name, d.recovery_model_desc
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
        """
        try:
            # 1. Verificar se é Always On
            alwayson_info = await self._check_alwayson_and_get_replicas(server_id)
            
            if alwayson_info and alwayson_info.get('is_alwayson'):
                # É Always On - usar abordagem simplificada: analisar apenas servidor atual
                # mas usar server_name do backup para identificar onde foi executado
                ag_name = alwayson_info.get('ag_name', 'N/A')
                is_primary = alwayson_info.get('current_is_primary', False)
                primary_replica = alwayson_info.get('primary_replica', 'N/A')
                logger.info(f"✅ Servidor {server_id} é Always On (AG: {ag_name}, Primary: {primary_replica}, Current is Primary: {is_primary}). Analisando backups usando server_name do backup.")
                
                # Obter databases do AG
                ag_databases_query = """
                SELECT DISTINCT adc.database_name
                FROM sys.availability_groups ag
                INNER JOIN sys.availability_databases_cluster adc ON ag.group_id = adc.group_id
                WHERE ag.name = ?;
                """
                
                ag_name = alwayson_info.get('ag_name')
                ag_db_result = await self.sql_monitoring.execute_query(server_id, ag_databases_query, params=[ag_name])
                ag_databases = []
                if ag_db_result and ag_db_result.get('success'):
                    ag_databases = [row.get('database_name') for row in ag_db_result.get('rows', []) if row.get('database_name')]
                
                # Analisar backups apenas no servidor atual (msdb tem backups de todos os nodes)
                logger.info(f"Analisando backups no servidor atual {server_id} (msdb contém backups de todos os nodes do AG)")
                result = await self._analyze_backups_for_server(
                    server_id, lookback_days, ag_databases, include_system_databases
                )
                
                if not result.get('success'):
                    return {'success': False, 'error': result.get('error', 'query-failed')}
                
                rows = result.get('rows', [])
                statuses: List[DatabaseBackupStatus] = []
                now = datetime.now()
                server_host = self._extract_server_host(server_id)
                tdp_log_lines = self._read_tdp_log(server_host)
                
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
                            except:
                                continue
                        
                        # Tentar formato ISO (mais flexível)
                        try:
                            # Remover 'Z' se houver e adicionar timezone
                            if date_value.endswith('Z'):
                                date_value = date_value[:-1]
                            # fromisoformat não aceita 'Z', então removemos
                            return datetime.fromisoformat(date_value)
                        except:
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
                    
                    # Log detalhado para debug do parse
                    logger.info(f"📅 {db_name} - Parse das datas:")
                    logger.info(f"   - RAW FULL: {row.get('last_full')} (tipo: {type(row.get('last_full'))}) → Parsed: {last_full}")
                    logger.info(f"   - RAW DIFF: {row.get('last_diff')} (tipo: {type(row.get('last_diff'))}) → Parsed: {last_diff}")
                    logger.info(f"   - RAW LOG: {row.get('last_log')} (tipo: {type(row.get('last_log'))}) → Parsed: {last_log}")
                    
                    # Pegar server_name onde cada backup foi executado
                    full_backup_server = row.get('full_backup_server') or ''
                    diff_backup_server = row.get('diff_backup_server') or ''
                    log_backup_server = row.get('log_backup_server') or ''
                    
                    # Log para debug
                    logger.info(f"🔍 {db_name}: FULL={last_full} (server: {full_backup_server}), DIFF={last_diff} (server: {diff_backup_server}), LOG={last_log} (server: {log_backup_server})")
                    logger.info(f"🔍 Always On: is_primary={is_current_primary}, primary_replica={primary_replica}")
                    
                    # IMPORTANTE: Para Always On, a lógica é diferente:
                    # - Se há data de backup, o backup EXISTE (mesmo que em outro node)
                    # - O server_name indica onde foi executado (informativo)
                    # - Só marcar como issue se:
                    #   1. Não há backup (data é None) - backup não existe em NENHUM node
                    #   2. OU o backup está MUITO antigo (mais de 7 dias para FULL)
                    # - Para DIFF e LOG, se há backup (mesmo que antigo), NÃO é issue para Always On
                    #   porque o backup pode ter sido feito no primário e estamos vendo o secundário
                    
                    issues = []
                    
                    # FULL: só marcar issue se não existe OU está muito antigo (>7 dias)
                    if last_full is None:
                        issues.append('Sem FULL nos últimos dias')
                    else:
                        hrs_full = round((now - last_full).total_seconds() / 3600.0, 1) if last_full else None
                        if hrs_full and hrs_full > (self.full_sla_days * 24):
                            # FULL está muito antigo (>7 dias) - é issue mesmo para Always On
                            issues.append('FULL >7d')
                    
                    # DIFF: para Always On, se existe backup (tem data), não é issue
                    # O backup pode ter sido feito no primário e estamos vendo o secundário
                    if last_diff is None:
                        # Não há DIFF em nenhum node - verificar se é issue
                        # REGRA: DIFF só é esperado A PARTIR DO DIA SEGUINTE ao FULL
                        # Se FULL foi hoje, DIFF não é esperado até amanhã
                        if last_full is not None:
                            # Calcular quando o DIFF é esperado: dia seguinte ao FULL
                            full_date = last_full.date()
                            expected_diff_date = full_date + timedelta(days=1)
                            today = now.date()
                            
                            # Se ainda não chegamos no dia esperado do DIFF, não é issue
                            if today < expected_diff_date:
                                # FULL foi hoje (ou ontem antes da meia-noite), DIFF não é esperado ainda
                                pass
                            else:
                                # Já passou do dia esperado do DIFF e não há DIFF - é issue
                                issues.append('Sem DIFF desde o último FULL')
                        else:
                            # Não há FULL nem DIFF - é issue
                            issues.append('Sem FULL e DIFF nos últimos dias')
                    # Se há DIFF (mesmo que antigo), não é issue para Always On
                    # porque o backup foi feito em algum node do AG
                    
                    # LOG: para Always On, se existe backup (tem data), não é issue
                    # O backup pode ter sido feito no primário e estamos vendo o secundário
                    if recovery_model.upper() in ('FULL', 'BULK_LOGGED'):
                        if last_log is None:
                            # Não há LOG em nenhum node - é issue
                            issues.append('Sem LOG nos últimos dias')
                        # Se há LOG (mesmo que antigo), NÃO é issue para Always On
                        # porque o backup foi feito em algum node do AG
                        # IMPORTANTE: NÃO adicionar "LOG >2H" aqui porque para Always On,
                        # se o backup existe (mesmo que antigo), não é problema
                        # O backup pode ter sido feito no primário e estamos vendo o secundário
                    
                    logger.info(f"✅ {db_name}: Issues após verificação Always On: {issues} | FULL={last_full} (server: {full_backup_server}), DIFF={last_diff} (server: {diff_backup_server}), LOG={last_log} (server: {log_backup_server})")
                    
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
                        alwayson_info=backup_info_message  # Mensagem informativa sobre Always On
                    )
                    
                    statuses.append(backup_status)
                
                # Resumo
                total = len(statuses)
                with_issues = sum(1 for s in statuses if s.issues)
                return {
                    'success': True,
                    'server_id': server_id,
                    'is_alwayson': True,
                    'ag_name': ag_name,
                    'current_is_primary': is_current_primary,
                    'primary_replica': primary_replica,
                    'total_databases': total,
                    'databases_with_issues': with_issues,
                    'items': [asdict(s) for s in statuses]
                }
            
            # Não é Always On - análise normal
            result = await self._analyze_backups_for_server(
                server_id, lookback_days, include_system_databases=include_system_databases
            )
            if not result.get('success'):
                return {'success': False, 'error': result.get('error', 'query-failed')}

            rows = result.get('rows', [])
            statuses: List[DatabaseBackupStatus] = []
            now = datetime.now()

            # Pré-carregar log do TDP (se acessível) para buscas por DB
            server_host = self._extract_server_host(server_id)
            tdp_log_lines = self._read_tdp_log(server_host)

            for row in rows:
                name = str(row.get('database_name'))
                recovery_model = str(row.get('recovery_model') or 'UNKNOWN')
                last_full = row.get('last_full')
                last_diff = row.get('last_diff')
                last_log = row.get('last_log')

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

                issues: List[str] = []
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
                            except:
                                try:
                                    last_diff_dt = datetime.strptime(last_diff, '%Y-%m-%d %H:%M:%S')
                                except:
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
                    tdp_samples=tdp_samples
                ))

            # Resumo
            total = len(statuses)
            with_issues = sum(1 for s in statuses if s.issues)
            return {
                'success': True,
                'server_id': server_id,
                'total_databases': total,
                'databases_with_issues': with_issues,
                'items': [asdict(s) for s in statuses]
            }

        except Exception as e:
            logger.error(f"Backup analysis error: {e}", exc_info=True)
            return {'success': False, 'error': str(e), 'server_id': server_id}

    def _extract_server_host(self, server_id: str) -> str:
        try:
            return server_id.split('_')[0]
        except Exception:
            return server_id

    def _read_tdp_log(self, server_host: str) -> Optional[List[str]]:
        try:
            local = self.tdp_log_path
            if ':' in local:
                drive, rest = local.split(':', 1)
                unc = f"\\\\{server_host}\\{drive}$\\{rest.strip('\\/')}"
            else:
                unc = f"\\\\{server_host}\\{local.strip('\\/')}"
            if not os.path.exists(unc):
                return None
            with open(unc, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines()[-5000:]
        except Exception as e:
            logger.debug(f"TDP log read failed for {server_host}: {e}")
            return None

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


