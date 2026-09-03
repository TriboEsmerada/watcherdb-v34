"""
WatcherDB Backup Pattern Analysis - Análise de Padrões de Backup
=====================================================================

OBJETIVO:
Identificar padrões de frequência de backups (FULL, DIFF, LOG) baseado em 
histórico de 30 dias, para detectar gaps e desvios do comportamento esperado.

FUNCIONALIDADES:
- Identifica frequência de FULL (semanal? quinzenal? dias da semana típicos?)
- Identifica frequência de DIFF (diária? horários típicos?)
- Identifica frequência de LOG (horária? 30min? 15min?)
- Detecta gaps/desvios do padrão esperado
- Calcula score de confiança do padrão identificado

ANALOGIA:
É como analisar o ritmo de uma banda - você identifica o BPM, o groove,
e quando alguém perde a batida! 🥁
"""

import logging
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
import statistics

logger = logging.getLogger(__name__)


@dataclass
class BackupSchedule:
    """Representa o schedule real de um job de backup do SQL Agent"""
    database_name: str
    backup_type: str  # 'FULL', 'DIFF', 'LOG'
    job_name: str
    schedule_name: str
    frequency_type: str  # 'Daily', 'Weekly', 'Monthly', etc
    expected_interval_hours: Optional[float]  # Intervalo esperado calculado do schedule
    scheduled_time: str  # Hora específica 'HH:MM:SS'
    is_enabled: bool
    schedule_enabled: bool


@dataclass
class BackupPattern:
    """Padrão de backup identificado"""
    backup_type: str  # 'FULL', 'DIFF', 'LOG'
    frequency_description: str  # Ex: "1x por semana", "2x por dia", "a cada 30 minutos"
    typical_hours: List[int]  # Horários típicos (horas do dia)
    typical_weekdays: List[int]  # Dias da semana típicos (0=segunda, 6=domingo)
    avg_interval_hours: float  # Intervalo médio em horas
    std_interval_hours: float  # Desvio padrão do intervalo
    confidence_score: float  # 0-100: confiança no padrão identificado
    sample_count: int  # Quantidade de backups analisados
    last_backup: Optional[datetime]  # Último backup detectado
    next_expected: Optional[datetime]  # Próximo backup esperado


@dataclass
class BackupGap:
    """Gap detectado (backup esperado mas não ocorreu)"""
    backup_type: str
    expected_datetime: datetime
    actual_datetime: Optional[datetime]  # None se não ocorreu
    gap_hours: float
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str


@dataclass
class DatabaseBackupPatternAnalysis:
    """Análise completa de padrões para uma database"""
    database_name: str
    full_pattern: Optional[BackupPattern]
    diff_pattern: Optional[BackupPattern]
    log_pattern: Optional[BackupPattern]
    detected_gaps: List[BackupGap]
    overall_health_score: float  # 0-100
    analysis_date: datetime


class BackupPatternAnalyzer:
    """
    Analisador de padrões de backup.
    
    Identifica comportamento esperado baseado em histórico e detecta desvios.
    """
    
    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        self.analysis_window_days = 30  # Janela de análise padrão
        self.min_samples_for_pattern = 3  # Mínimo de amostras para identificar padrão
        
        # Thresholds para classificação de severidade de gaps
        self.gap_thresholds = {
            'FULL': {'medium': 7*24, 'high': 10*24, 'critical': 14*24},  # horas
            'DIFF': {'medium': 24, 'high': 48, 'critical': 72},
            'LOG': {'medium': 2, 'high': 4, 'critical': 8}
        }
    
    async def analyze_database_patterns(self, server_id: str, database_name: str, 
                                       window_days: int = 30) -> DatabaseBackupPatternAnalysis:
        """
        Analisa padrões de backup para uma database específica.
        
        Args:
            server_id: ID do servidor
            database_name: Nome da database
            window_days: Janela de análise em dias (padrão: 30)
            
        Returns:
            DatabaseBackupPatternAnalysis com padrões identificados e gaps detectados
        """
        try:
            logger.info(f"🔍 Analisando padrões de backup para {database_name} (últimos {window_days} dias)")
            
            # 1. Buscar histórico de backups E schedules dos jobs
            backup_history = await self._get_backup_history(server_id, database_name, window_days)

            if not backup_history or not backup_history.get('success'):
                logger.warning(f"Não foi possível obter histórico de backup para {database_name}")
                return self._empty_analysis(database_name)

            backups_by_type = backup_history.get('backups_by_type', {})

            logger.info(f"📊 Histórico obtido: FULL={len(backups_by_type.get('D', []))}, "
                       f"DIFF={len(backups_by_type.get('I', []))}, "
                       f"LOG={len(backups_by_type.get('L', []))}")

            # 1.1 Buscar schedules reais dos jobs (fonte da verdade para gaps)
            backup_schedules = await self._get_backup_schedules(server_id, database_name)

            # 1.2 Wave R+8 (2026-05-25) -- Smart Defaults Initiative:
            # Para tipos SEM sysjobs schedule (TSM/Commvault/manual), tentar
            # inferir schedule from msdb.backupset history pattern. Cobre gap
            # major em production (~30% dos servers usam tools externos).
            for bt_code, bt_name in [('D', 'FULL'), ('I', 'DIFF'), ('L', 'LOG')]:
                if backup_schedules.get(bt_name) is None:
                    dates = backups_by_type.get(bt_code, [])
                    inferred = self._detect_schedule_from_backupset_history(dates, bt_name)
                    if inferred:
                        backup_schedules[bt_name] = inferred

            # 2. Analisar padrão de cada tipo de backup
            full_pattern = self._analyze_pattern(backups_by_type.get('D', []), 'FULL')
            diff_pattern = self._analyze_pattern(backups_by_type.get('I', []), 'DIFF')
            log_pattern = self._analyze_pattern(backups_by_type.get('L', []), 'LOG')
            
            # 3. Detectar gaps baseado nos padrões identificados E schedules reais
            detected_gaps = []
            now = datetime.now()

            if full_pattern and full_pattern.confidence_score >= 60:
                full_schedule = backup_schedules.get('FULL')
                gaps = self._detect_gaps(backups_by_type.get('D', []), full_pattern, now, full_schedule)
                detected_gaps.extend(gaps)
                logger.info(f"✅ FULL pattern: {full_pattern.frequency_description} (confiança: {full_pattern.confidence_score:.1f}%, fonte: {self._source_label(full_schedule)})")

            if diff_pattern and diff_pattern.confidence_score >= 60:
                diff_schedule = backup_schedules.get('DIFF')
                gaps = self._detect_gaps(backups_by_type.get('I', []), diff_pattern, now, diff_schedule)
                detected_gaps.extend(gaps)
                logger.info(f"✅ DIFF pattern: {diff_pattern.frequency_description} (confiança: {diff_pattern.confidence_score:.1f}%, fonte: {self._source_label(diff_schedule)})")

            if log_pattern and log_pattern.confidence_score >= 60:
                log_schedule = backup_schedules.get('LOG')
                gaps = self._detect_gaps(backups_by_type.get('L', []), log_pattern, now, log_schedule)
                detected_gaps.extend(gaps)
                logger.info(f"✅ LOG pattern: {log_pattern.frequency_description} (confiança: {log_pattern.confidence_score:.1f}%, fonte: {self._source_label(log_schedule)})")
            
            # 4. Calcular score de saúde geral
            health_score = self._calculate_health_score(full_pattern, diff_pattern, log_pattern, detected_gaps)
            
            if detected_gaps:
                logger.warning(f"⚠️ {len(detected_gaps)} gaps detectados para {database_name}")
            
            return DatabaseBackupPatternAnalysis(
                database_name=database_name,
                full_pattern=full_pattern,
                diff_pattern=diff_pattern,
                log_pattern=log_pattern,
                detected_gaps=detected_gaps,
                overall_health_score=health_score,
                analysis_date=now
            )
            
        except Exception as e:
            logger.error(f"Erro ao analisar padrões para {database_name}: {e}", exc_info=True)
            return self._empty_analysis(database_name)
    
    async def _get_backup_history(self, server_id: str, database_name: str, 
                                  window_days: int) -> Dict:
        """
        Busca histórico de backups dos últimos N dias.
        
        Returns:
            {
                'success': bool,
                'backups_by_type': {
                    'D': [datetime1, datetime2, ...],  # FULL
                    'I': [datetime1, datetime2, ...],  # DIFF
                    'L': [datetime1, datetime2, ...]   # LOG
                }
            }
        """
        start_date = (datetime.now() - timedelta(days=window_days)).strftime('%Y-%m-%d %H:%M:%S')
        
        query = f"""
        SELECT 
            type AS backup_type,
            backup_finish_date
        FROM msdb.dbo.backupset
        WHERE database_name = ?
          AND backup_finish_date >= CONVERT(datetime, '{start_date}')
        ORDER BY backup_finish_date;
        """
        
        result = await self.sql_monitoring.execute_query(server_id, query, params=[database_name])
        
        if not result or not result.get('success'):
            return {'success': False}
        
        # Organizar backups por tipo
        backups_by_type = defaultdict(list)
        for row in result.get('rows', []):
            backup_type = row.get('backup_type')
            backup_date = row.get('backup_finish_date')
            
            if backup_date:
                # Converter para datetime se necessário
                if isinstance(backup_date, str):
                    try:
                        backup_date = datetime.fromisoformat(backup_date.replace('Z', ''))
                    except (ValueError, TypeError):
                        try:
                            backup_date = datetime.strptime(backup_date, '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            try:
                                backup_date = datetime.strptime(backup_date, '%Y-%m-%d %H:%M:%S.%f')
                            except (ValueError, TypeError):
                                try:
                                    backup_date = datetime.strptime(backup_date, '%Y-%m-%d')
                                except (ValueError, TypeError):
                                    continue
                
                backups_by_type[backup_type].append(backup_date)
        
        return {
            'success': True,
            'backups_by_type': dict(backups_by_type)
        }

    async def _get_backup_schedules(self, server_id: str, database_name: str) -> Dict[str, BackupSchedule]:
        """
        Busca os schedules reais dos jobs de backup do SQL Agent.

        Returns:
            {
                'FULL': BackupSchedule,
                'DIFF': BackupSchedule,
                'LOG': BackupSchedule
            }
        """
        query = """
        WITH BackupJobs AS (
            SELECT DISTINCT
                j.job_id,
                j.name AS job_name,
                j.enabled AS is_enabled,
                js.step_id,
                js.command,
                -- Extrair database name do comando
                CASE
                    WHEN js.command LIKE '%DATABASE = %' THEN
                        SUBSTRING(
                            js.command,
                            CHARINDEX('DATABASE = ', js.command) + 11,
                            CHARINDEX(',', js.command, CHARINDEX('DATABASE = ', js.command)) - CHARINDEX('DATABASE = ', js.command) - 11
                        )
                    WHEN js.command LIKE '%BACKUP DATABASE [[]%' THEN
                        SUBSTRING(
                            js.command,
                            CHARINDEX('BACKUP DATABASE [', js.command) + 16,
                            CHARINDEX(']', js.command, CHARINDEX('BACKUP DATABASE [', js.command)) - CHARINDEX('BACKUP DATABASE [', js.command) - 16
                        )
                    WHEN js.command LIKE '%BACKUP LOG [[]%' THEN
                        SUBSTRING(
                            js.command,
                            CHARINDEX('BACKUP LOG [', js.command) + 12,
                            CHARINDEX(']', js.command, CHARINDEX('BACKUP LOG [', js.command)) - CHARINDEX('BACKUP LOG [', js.command) - 12
                        )
                    ELSE NULL
                END AS database_name,
                -- Identificar tipo de backup
                CASE
                    WHEN js.command LIKE '%BACKUP LOG%' THEN 'LOG'
                    WHEN js.command LIKE '%DIFFERENTIAL%' OR js.command LIKE '%TYPE = DIFFERENTIAL%' THEN 'DIFF'
                    WHEN js.command LIKE '%BACKUP DATABASE%' THEN 'FULL'
                    ELSE 'UNKNOWN'
                END AS backup_type
            FROM msdb.dbo.sysjobs j WITH(NOLOCK)
            INNER JOIN msdb.dbo.sysjobsteps js WITH(NOLOCK) ON j.job_id = js.job_id
            WHERE (
                js.command LIKE '%BACKUP DATABASE%'
                OR js.command LIKE '%BACKUP LOG%'
            )
            AND j.enabled = 1
        ),
        JobSchedules AS (
            SELECT
                bj.job_id,
                bj.job_name,
                bj.database_name,
                bj.backup_type,
                bj.is_enabled,
                s.schedule_id,
                s.name AS schedule_name,
                s.enabled AS schedule_enabled,
                s.freq_type,
                s.freq_interval,
                s.freq_subday_type,
                s.freq_subday_interval,
                s.active_start_time,
                s.active_end_time
            FROM BackupJobs bj
            INNER JOIN msdb.dbo.sysjobschedules js WITH(NOLOCK) ON bj.job_id = js.job_id
            INNER JOIN msdb.dbo.sysschedules s WITH(NOLOCK) ON js.schedule_id = s.schedule_id
            WHERE s.enabled = 1
        )
        SELECT
            database_name,
            backup_type,
            job_name,
            schedule_name,
            CASE freq_type
                WHEN 1 THEN 'Once'
                WHEN 4 THEN 'Daily'
                WHEN 8 THEN 'Weekly'
                WHEN 16 THEN 'Monthly'
                WHEN 32 THEN 'Monthly Relative'
                WHEN 64 THEN 'SQL Agent Start'
                WHEN 128 THEN 'Computer Idle'
                ELSE 'Unknown'
            END AS frequency_type,
            -- Calcular intervalo esperado em horas
            CASE
                WHEN freq_type = 4 AND freq_subday_type = 8 THEN freq_subday_interval
                WHEN freq_type = 4 AND freq_subday_type = 4 THEN CAST(freq_subday_interval AS FLOAT) / 60.0
                WHEN freq_type = 4 AND freq_subday_type = 1 THEN 24
                WHEN freq_type = 8 THEN 24 * 7 / NULLIF((
                    (freq_interval & 1) + ((freq_interval & 2) / 2) + ((freq_interval & 4) / 4) +
                    ((freq_interval & 8) / 8) + ((freq_interval & 16) / 16) + ((freq_interval & 32) / 32) +
                    ((freq_interval & 64) / 64)
                ), 0)
                WHEN freq_type = 16 THEN 24 * 30
                ELSE NULL
            END AS expected_interval_hours,
            STUFF(STUFF(RIGHT('000000' + CAST(active_start_time AS VARCHAR(6)), 6), 5, 0, ':'), 3, 0, ':') AS scheduled_time,
            is_enabled,
            schedule_enabled
        FROM JobSchedules
        WHERE database_name = ?
        ORDER BY backup_type, expected_interval_hours;
        """

        result = await self.sql_monitoring.execute_query(server_id, query, params=[database_name])

        if not result or not result.get('success'):
            logger.debug(f"Não foi possível buscar schedules para {database_name}")
            return {}

        schedules = {}
        for row in result.get('rows', []):
            backup_type = row.get('backup_type')
            if backup_type and backup_type in ['FULL', 'DIFF', 'LOG']:
                # Se já existe um schedule desse tipo, usar o de menor intervalo
                # (mais conservador para detecção de gaps)
                if backup_type in schedules:
                    existing_interval = schedules[backup_type].expected_interval_hours
                    new_interval = row.get('expected_interval_hours')
                    if new_interval and (not existing_interval or new_interval < existing_interval):
                        schedules[backup_type] = BackupSchedule(
                            database_name=row.get('database_name', database_name),
                            backup_type=backup_type,
                            job_name=row.get('job_name', ''),
                            schedule_name=row.get('schedule_name', ''),
                            frequency_type=row.get('frequency_type', ''),
                            expected_interval_hours=new_interval,
                            scheduled_time=row.get('scheduled_time', ''),
                            is_enabled=row.get('is_enabled', False),
                            schedule_enabled=row.get('schedule_enabled', False)
                        )
                else:
                    schedules[backup_type] = BackupSchedule(
                        database_name=row.get('database_name', database_name),
                        backup_type=backup_type,
                        job_name=row.get('job_name', ''),
                        schedule_name=row.get('schedule_name', ''),
                        frequency_type=row.get('frequency_type', ''),
                        expected_interval_hours=row.get('expected_interval_hours'),
                        scheduled_time=row.get('scheduled_time', ''),
                        is_enabled=row.get('is_enabled', False),
                        schedule_enabled=row.get('schedule_enabled', False)
                    )

        if schedules:
            logger.info(f"📅 Schedules encontrados para {database_name}: {', '.join(schedules.keys())}")

        return schedules

    def _detect_schedule_from_backupset_history(
        self,
        backup_dates: List[datetime],
        backup_type: str,
        confidence_threshold: float = 70.0
    ) -> Optional[BackupSchedule]:
        """
        Wave R+8 (2026-05-25) -- Smart Defaults Initiative.

        Infer expected backup schedule from msdb.backupset history pattern.
        Cobre gap de schedule detection actual: backups feitos por TSM/Commvault/
        NetBackup via VDI nao aparecem em msdb.sysjobs, mas SAO registados em
        msdb.dbo.backupset. Este metodo le essa historia (ja capturada por
        `_get_backup_history`) e infere schedule via clustering de intervals.

        Algoritmo:
            1. Min 5 backups para auto-detect (sample size confiavel)
            2. Calcular intervals consecutive (hours)
            3. Median interval (resistente a outliers vs mean)
            4. Tolerance: 20% do median (min 0.5h absoluto)
            5. Conformance rate: % intervals dentro de median ± tolerance
            6. Se conformance >= 70% -> return BackupSchedule sintetico
            7. Senao -> None (irregular, fallback a pattern inferido)

        Args:
            backup_dates: datetimes ordenados de backups completados
            backup_type: 'FULL', 'DIFF', 'LOG'
            confidence_threshold: min % conformance (default 70%)

        Returns:
            BackupSchedule com expected_interval_hours inferido, OR None
        """
        if not backup_dates or len(backup_dates) < 5:
            return None

        sorted_dates = sorted(backup_dates)

        # 1. Intervals consecutive em horas
        intervals = []
        for i in range(1, len(sorted_dates)):
            delta = (sorted_dates[i] - sorted_dates[i-1]).total_seconds() / 3600.0
            intervals.append(delta)

        if not intervals:
            return None

        # 2. Median (robust to outliers)
        srt = sorted(intervals)
        n = len(srt)
        median = srt[n // 2] if n % 2 == 1 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0

        # 3. Tolerance: 20% do median, minimo 0.5h
        tolerance = max(median * 0.20, 0.5)

        # 4. Conformance rate
        conformant = sum(1 for x in intervals if abs(x - median) <= tolerance)
        conformance_rate = (conformant / len(intervals)) * 100.0

        if conformance_rate < confidence_threshold:
            logger.debug(
                f"📉 R+8 pattern from backupset history para {backup_type}: "
                f"conformance {conformance_rate:.1f}% < threshold {confidence_threshold}% "
                f"-- irregular, sem auto-detect"
            )
            return None

        logger.info(
            f"📅 R+8 pattern from backupset history detected para {backup_type}: "
            f"interval={median:.1f}h, conformance={conformance_rate:.1f}% "
            f"(samples={len(intervals)})"
        )

        # 5. Synthetic BackupSchedule (database_name fica vazio -- caller knows)
        return BackupSchedule(
            database_name='',
            backup_type=backup_type,
            job_name='[R+8 auto-baseline from msdb.backupset]',
            schedule_name='[Wave R+8 inferred]',
            frequency_type='InferredFromHistory',
            expected_interval_hours=median,
            scheduled_time='',
            is_enabled=True,
            schedule_enabled=True
        )

    def _source_label(self, schedule: Optional['BackupSchedule']) -> str:
        """Wave R+8: distinguish 3 sources nos logs (sysjobs / R+8 history / pattern inferido)."""
        if not schedule:
            return "padrão inferido"
        if schedule.frequency_type == 'InferredFromHistory':
            return "R+8 history pattern"
        return "schedule (sysjobs)"

    def _analyze_pattern(self, backup_dates: List[datetime], backup_type: str) -> Optional[BackupPattern]:
        """
        Analisa lista de datas de backup e identifica o padrão.
        
        Args:
            backup_dates: Lista de datetimes dos backups
            backup_type: 'FULL', 'DIFF' ou 'LOG'
            
        Returns:
            BackupPattern ou None se não houver dados suficientes
        """
        if not backup_dates or len(backup_dates) < self.min_samples_for_pattern:
            logger.debug(f"Dados insuficientes para identificar padrão de {backup_type}: {len(backup_dates)} amostras")
            return None
        
        # Ordenar datas
        sorted_dates = sorted(backup_dates)
        
        # Calcular intervalos entre backups consecutivos
        intervals_hours = []
        for i in range(1, len(sorted_dates)):
            interval = (sorted_dates[i] - sorted_dates[i-1]).total_seconds() / 3600.0
            intervals_hours.append(interval)
        
        if not intervals_hours:
            return None
        
        # Estatísticas dos intervalos
        avg_interval = statistics.mean(intervals_hours)
        std_interval = statistics.stdev(intervals_hours) if len(intervals_hours) > 1 else 0
        
        # Identificar horários típicos (hora do dia)
        hours_of_day = [dt.hour for dt in sorted_dates]
        hour_counter = Counter(hours_of_day)
        typical_hours = [hour for hour, count in hour_counter.most_common(3)]
        
        # Identificar dias da semana típicos
        weekdays = [dt.weekday() for dt in sorted_dates]
        weekday_counter = Counter(weekdays)
        typical_weekdays = [day for day, count in weekday_counter.most_common(2)]
        
        # Gerar descrição da frequência
        frequency_desc = self._generate_frequency_description(avg_interval, backup_type)
        
        # Calcular score de confiança
        confidence = self._calculate_confidence_score(intervals_hours, std_interval, avg_interval, len(sorted_dates))
        
        # Estimar próximo backup esperado
        last_backup = sorted_dates[-1]
        next_expected = last_backup + timedelta(hours=avg_interval)
        
        return BackupPattern(
            backup_type=backup_type,
            frequency_description=frequency_desc,
            typical_hours=typical_hours,
            typical_weekdays=typical_weekdays,
            avg_interval_hours=round(avg_interval, 2),
            std_interval_hours=round(std_interval, 2),
            confidence_score=round(confidence, 1),
            sample_count=len(sorted_dates),
            last_backup=last_backup,
            next_expected=next_expected
        )
    
    def _generate_frequency_description(self, avg_interval_hours: float, backup_type: str) -> str:
        """
        Gera descrição human-readable da frequência de backup.
        
        Exemplos:
        - "A cada 7 dias (semanal)"
        - "2x por dia (a cada 12 horas)"
        - "A cada 30 minutos"
        """
        if avg_interval_hours < 1:
            # Minutos
            minutes = round(avg_interval_hours * 60)
            return f"A cada {minutes} minutos"
        elif avg_interval_hours < 24:
            # Horas
            hours = round(avg_interval_hours, 1)
            backups_per_day = round(24 / avg_interval_hours, 1)
            return f"{backups_per_day}x por dia (a cada {hours} horas)"
        elif avg_interval_hours < 168:  # < 1 semana
            # Dias
            days = round(avg_interval_hours / 24, 1)
            return f"A cada {days} dias"
        else:
            # Semanas
            weeks = round(avg_interval_hours / 168, 1)
            return f"A cada {weeks} semanas"
    
    def _calculate_confidence_score(self, intervals: List[float], std_dev: float, 
                                   avg_interval: float, sample_count: int) -> float:
        """
        Calcula score de confiança do padrão identificado (0-100).
        
        Fatores considerados:
        - Consistência dos intervalos (baixo desvio padrão = alta confiança)
        - Quantidade de amostras (mais amostras = maior confiança)
        - Regularidade (intervalos similares = alta confiança)
        """
        if not intervals or avg_interval == 0:
            return 0.0
        
        # Fator 1: Consistência (CV - Coeficiente de Variação)
        # CV baixo = intervalos consistentes = alta confiança
        cv = (std_dev / avg_interval) if avg_interval > 0 else 1.0
        consistency_score = max(0, 100 - (cv * 100))
        
        # Fator 2: Quantidade de amostras
        # Mais amostras = maior confiança (saturando em 20 amostras)
        sample_score = min(100, (sample_count / 20) * 100)
        
        # Fator 3: Regularidade (todos os intervalos dentro de 2x desvio padrão)
        within_2std = sum(1 for i in intervals if abs(i - avg_interval) <= 2 * std_dev)
        regularity_score = (within_2std / len(intervals)) * 100 if intervals else 0
        
        # Score final (média ponderada)
        confidence = (consistency_score * 0.4 + sample_score * 0.3 + regularity_score * 0.3)
        
        return max(0, min(100, confidence))
    
    def _detect_gaps(self, backup_dates: List[datetime], pattern: BackupPattern,
                     now: datetime, schedule: Optional[BackupSchedule] = None) -> List[BackupGap]:
        """
        Detecta gaps (backups esperados mas que não ocorreram) baseado no padrão.

        Args:
            backup_dates: Lista de datas dos backups
            pattern: Padrão identificado (inferido dos dados históricos)
            now: Data/hora atual
            schedule: Schedule real do SQL Agent job (fonte da verdade quando disponível)

        Returns:
            Lista de gaps detectados
        """
        if not backup_dates or not pattern:
            return []

        gaps = []
        sorted_dates = sorted(backup_dates)

        # PRIORIDADE: usar schedule real se disponível, senão usar padrão inferido
        if schedule and schedule.expected_interval_hours:
            expected_interval = schedule.expected_interval_hours
            # Tolerância fixa baseada no tipo de backup (mais conservador)
            tolerance_map = {'LOG': 2.0, 'DIFF': 4.0, 'FULL': 12.0}
            tolerance = tolerance_map.get(pattern.backup_type, 2.0)
            logger.debug(f"📅 Usando schedule real para {pattern.backup_type}: intervalo={expected_interval}h, tolerância={tolerance}h")
        else:
            expected_interval = pattern.avg_interval_hours
            tolerance = pattern.std_interval_hours * 2  # 2x desvio padrão como tolerância
            logger.debug(f"📊 Usando padrão inferido para {pattern.backup_type}: intervalo={expected_interval:.1f}h, tolerância={tolerance:.1f}h")
        
        for i in range(1, len(sorted_dates)):
            prev_backup = sorted_dates[i-1]
            curr_backup = sorted_dates[i]
            actual_interval = (curr_backup - prev_backup).total_seconds() / 3600.0
            
            # Se o intervalo for muito maior que o esperado, temos um gap
            if actual_interval > (expected_interval + tolerance):
                # Calcular quando era esperado
                expected_datetime = prev_backup + timedelta(hours=expected_interval)
                gap_hours = (curr_backup - expected_datetime).total_seconds() / 3600.0

                severity = self._classify_gap_severity(pattern.backup_type, gap_hours, expected_interval)

                gaps.append(BackupGap(
                    backup_type=pattern.backup_type,
                    expected_datetime=expected_datetime,
                    actual_datetime=curr_backup,
                    gap_hours=round(gap_hours, 1),
                    severity=severity,
                    description=f"Backup esperado em {expected_datetime.strftime('%Y-%m-%d %H:%M')}, ocorreu apenas em {curr_backup.strftime('%Y-%m-%d %H:%M')} ({gap_hours:.1f}h de atraso)"
                ))
        
        # Verificar se o PRÓXIMO backup está atrasado (baseado no último backup)
        last_backup = sorted_dates[-1]
        expected_next = last_backup + timedelta(hours=expected_interval)
        
        if now > expected_next + timedelta(hours=tolerance):
            # Próximo backup está atrasado!
            gap_hours = (now - expected_next).total_seconds() / 3600.0
            severity = self._classify_gap_severity(pattern.backup_type, gap_hours, expected_interval)

            gaps.append(BackupGap(
                backup_type=pattern.backup_type,
                expected_datetime=expected_next,
                actual_datetime=None,  # Ainda não ocorreu
                gap_hours=round(gap_hours, 1),
                severity=severity,
                description=f"Backup esperado em {expected_next.strftime('%Y-%m-%d %H:%M')}, ainda não ocorreu ({gap_hours:.1f}h de atraso)"
            ))
        
        return gaps
    
    def _classify_gap_severity(self, backup_type: str, gap_hours: float,
                              expected_interval_hours: Optional[float] = None) -> str:
        """
        Classifica severidade de um gap.

        Args:
            backup_type: 'FULL', 'DIFF', 'LOG'
            gap_hours: Horas de atraso do gap
            expected_interval_hours: Intervalo esperado do schedule (se disponível)

        Returns: 'low', 'medium', 'high', 'critical'
        """
        # Se temos o intervalo esperado do schedule, usar thresholds FIXOS
        if expected_interval_hours:
            # Thresholds fixos definidos pelo negócio:
            # gap <= 6h → low
            # gap > 6h e <= 30h → medium
            # gap > 30h e <= 48h → high
            # gap > 48h → critical
            if gap_hours > 48:
                return 'critical'
            elif gap_hours > 30:
                return 'high'
            elif gap_hours > 6:
                return 'medium'
            else:
                return 'low'
        else:
            # Fallback: usar thresholds fixos por tipo de backup
            thresholds = self.gap_thresholds.get(backup_type, {})

            if gap_hours >= thresholds.get('critical', float('inf')):
                return 'critical'
            elif gap_hours >= thresholds.get('high', float('inf')):
                return 'high'
            elif gap_hours >= thresholds.get('medium', float('inf')):
                return 'medium'
            else:
                return 'low'
    
    def _calculate_health_score(self, full_pattern: Optional[BackupPattern],
                               diff_pattern: Optional[BackupPattern],
                               log_pattern: Optional[BackupPattern],
                               gaps: List[BackupGap]) -> float:
        """
        Calcula score geral de saúde dos backups (0-100).
        
        Considera:
        - Existência de padrões identificados
        - Confiança nos padrões
        - Quantidade e severidade de gaps
        """
        score = 100.0
        
        # Penalidade por falta de padrões
        if full_pattern is None:
            score -= 20
        if diff_pattern is None:
            score -= 10
        if log_pattern is None:
            score -= 10
        
        # Bonus por padrões com alta confiança
        if full_pattern and full_pattern.confidence_score >= 80:
            score += 5
        if diff_pattern and diff_pattern.confidence_score >= 80:
            score += 3
        if log_pattern and log_pattern.confidence_score >= 80:
            score += 2
        
        # Penalidade por gaps
        for gap in gaps:
            if gap.severity == 'critical':
                score -= 20
            elif gap.severity == 'high':
                score -= 10
            elif gap.severity == 'medium':
                score -= 5
            else:  # low
                score -= 2
        
        return max(0, min(100, score))
    
    def _empty_analysis(self, database_name: str) -> DatabaseBackupPatternAnalysis:
        """Retorna análise vazia quando não há dados"""
        return DatabaseBackupPatternAnalysis(
            database_name=database_name,
            full_pattern=None,
            diff_pattern=None,
            log_pattern=None,
            detected_gaps=[],
            overall_health_score=0.0,
            analysis_date=datetime.now()
        )

    async def _detect_missing_log_chain(
        self,
        server_id: str,
        window_days: int
    ) -> List[dict]:
        """
        Wave I (2026-05-19): detecta DBs FULL/BULK_LOGGED recovery que NAO tem
        NENHUM registo de LOG backup dentro da janela de analise.

        Bug original (false negative): _get_backup_history filtra por window_days
        (default 30). Se a chain de LOG quebrou ha mais tempo (ex: 69d para
        ENCYA/GDNA em CAGENPRD06\\I06), zero rows L sao devolvidas. _analyze_pattern
        retorna None (len < min_samples_for_pattern=3). _detect_gaps nunca corre.
        Resultado: DB silenciosamente ignorada — pior caso possivel para banking.

        Este metodo faz LEFT JOIN msdb.dbo.backupset SEM filtro de janela e usa
        HAVING para apanhar exactamente DBs FULL com zero L na window. Distingue
        'nunca teve L' (worst case, RPO ilimitado) de 'L fora da window'.

        Retorna lista de dicts compativeis com BackupGap.asdict().
        """
        # Janela explicita em SQL para tornar o pivot claro no HAVING.
        # GETDATE() server-side e' a referencia de "now" — evita drift cliente/servidor.

        # Wave I.1 (2026-05-19 hotfix): excluir AG secondary databases.
        # Em AG topology com Backup Preference=Primary (default), LOG backups
        # correm no servidor primary. msdb LOCAL do secondary nao tem registos
        # desses backups por design SQL Server. Sem este filter, Wave I gera
        # 27+ false positives por servidor secondary com 27 DBs FULL recovery.
        # Bug reportado em screenshot 2026-05-19 SQLMDMPRD04\\I01 (secondary
        # do SQLMDMPRDAG03).
        query = f"""
        SELECT
            d.name                          AS database_name,
            d.recovery_model_desc           AS recovery_model,
            MAX(bs_log.backup_finish_date)  AS last_log_backup,
            DATEDIFF(HOUR,
                MAX(bs_log.backup_finish_date),
                GETDATE()
            )                               AS hours_since_log,
            CASE
                WHEN MAX(bs_log.backup_finish_date) IS NULL
                    THEN 'NEVER'
                WHEN MAX(bs_log.backup_finish_date) < DATEADD(DAY, -{window_days}, GETDATE())
                    THEN 'OUTSIDE_WINDOW'
                ELSE 'IN_WINDOW'
            END                             AS log_status
        FROM sys.databases d WITH (NOLOCK)
        LEFT JOIN msdb.dbo.backupset bs_log WITH (NOLOCK)
            ON  bs_log.database_name = d.name
            AND bs_log.type          = 'L'
        WHERE d.recovery_model_desc IN ('FULL', 'BULK_LOGGED')
          AND d.state               = 0
          AND d.database_id         > 4
          -- Wave I.1 + I.1.1 hotfix (2026-05-19): excluir AG SECONDARY local.
          -- msdb deste servidor nao tem L backups (correm no primary).
          -- I.1.1: corrigido — role_desc nao existe em sys.availability_replicas
          -- (catalog view); usar is_primary_replica=0 em sys.dm_hadr_database_replica_states
          -- (DMV) que cobre SECONDARY + RESOLVING (ambos a excluir).
          AND NOT EXISTS (
              SELECT 1
              FROM sys.dm_hadr_database_replica_states drs WITH (NOLOCK)
              WHERE drs.database_id        = d.database_id
                AND drs.is_local           = 1
                AND drs.is_primary_replica = 0
          )
        GROUP BY d.name, d.recovery_model_desc
        HAVING MAX(
            CASE WHEN bs_log.backup_finish_date >= DATEADD(DAY, -{window_days}, GETDATE())
                 THEN 1 ELSE 0
            END
        ) = 0
        ORDER BY hours_since_log DESC;
        """

        result = await self.sql_monitoring.execute_query(server_id, query)
        if not result or not result.get('success'):
            logger.warning(f"_detect_missing_log_chain: query falhou para {server_id}")
            return []

        missing_chain_gaps = []
        for row in result.get('rows', []):
            db_name      = row.get('database_name')
            last_log     = row.get('last_log_backup')
            hours_since  = row.get('hours_since_log')
            log_status   = row.get('log_status', 'NEVER')

            if not db_name:
                continue

            if last_log is None:
                # Nunca teve LOG backup registado — RPO ilimitado
                effective_gap_hours = 99999.0  # placeholder explicito
                description = (
                    f"DB {db_name} ({row.get('recovery_model', 'FULL')} recovery) "
                    f"NUNCA teve LOG backup registado em msdb. "
                    f"Log chain nao existe — RPO ilimitado. "
                    f"Verificar se SQL Agent job de LOG backup existe e esta enabled."
                )
            else:
                if isinstance(hours_since, (int, float)):
                    effective_gap_hours = float(hours_since)
                else:
                    effective_gap_hours = 99999.0

                last_log_str = (
                    last_log.strftime('%Y-%m-%d %H:%M')
                    if isinstance(last_log, datetime) else str(last_log)
                )
                description = (
                    f"DB {db_name} ({row.get('recovery_model', 'FULL')} recovery) "
                    f"sem LOG backup ha {effective_gap_hours:.0f}h "
                    f"(ultimo: {last_log_str}). "
                    f"Log chain quebrada — fora da janela de {window_days}d."
                )

            # Severidade conforme magnitude do gap (LOG backup chain rules of thumb)
            if effective_gap_hours > 168:        # > 7 dias
                severity = 'critical'
            elif effective_gap_hours > 48:       # > 2 dias
                severity = 'high'
            elif effective_gap_hours > 8:        # > 8 horas
                severity = 'medium'
            else:
                severity = 'low'

            missing_chain_gaps.append({
                'database_name':     db_name,
                'backup_type':       'LOG',
                'expected_datetime': None,
                'actual_datetime':   (
                    last_log.isoformat()
                    if isinstance(last_log, datetime) else None
                ),
                'gap_hours':   round(effective_gap_hours, 1),
                'severity':    severity,
                'description': description,
                'source':      'missing_log_chain',  # distingue de gaps por padrao
                'log_status':  log_status,
            })

        if missing_chain_gaps:
            logger.warning(
                f"_detect_missing_log_chain: {len(missing_chain_gaps)} DBs FULL recovery "
                f"sem LOG chain na janela de {window_days}d em {server_id}"
            )
        else:
            logger.debug(
                f"_detect_missing_log_chain: nenhuma DB com missing log chain em {server_id}"
            )

        return missing_chain_gaps

    async def analyze_server_patterns(self, server_id: str, window_days: int = 30) -> Dict:
        """
        Analisa padrões de todas as databases de um servidor.
        
        Returns:
            {
                'success': bool,
                'server_id': str,
                'total_databases': int,
                'databases': [DatabaseBackupPatternAnalysis, ...],
                'overall_server_health': float,
                'summary': {
                    'databases_with_gaps': int,
                    'total_gaps': int,
                    'critical_gaps': int
                }
            }
        """
        try:
            # Wave I.2 (2026-05-19): excluir AG SECONDARY local na enumeracao.
            # msdb LOCAL no secondary nao tem registos dos backups (correm no
            # primary por design AlwaysOn com Backup Preference). Sem este filter,
            # qualquer DIFF/LOG/FULL residual em msdb local (pre-role-change,
            # COPY_ONLY, restos) vira false positive critico. Bug reportado
            # 2026-05-19 SQLMDMPRD04\\I01: 7 DIFF gaps "DIFF nao executado ha
            # 53 dias" depois de Wave I.1 ter resolvido o caso LOG. Principio
            # confirmado pelo utilizador: "se nao tem backup em replica
            # secundaria, nao tem erro ou gap". Single source of truth — secondary
            # DBs nunca entram no pipeline de analise.
            query = """
            SELECT d.name
            FROM sys.databases d WITH (NOLOCK)
            WHERE d.database_id > 4
              AND d.state       = 0
              -- I.2.1 hotfix: corrigido para usar is_primary_replica=0 em
              -- sys.dm_hadr_database_replica_states (role_desc nao existe em
              -- sys.availability_replicas — bug que partia hard o endpoint).
              AND NOT EXISTS (
                  SELECT 1
                  FROM sys.dm_hadr_database_replica_states drs WITH (NOLOCK)
                  WHERE drs.database_id        = d.database_id
                    AND drs.is_local           = 1
                    AND drs.is_primary_replica = 0
              )
            ORDER BY d.name;
            """

            result = await self.sql_monitoring.execute_query(server_id, query)
            if not result or not result.get('success'):
                return {'success': False, 'error': 'Failed to get database list'}

            database_names = [row.get('name') for row in result.get('rows', []) if row.get('name')]

            # Analisar databases em PARALELO (otimização: antes era sequencial)
            # Limitar concorrência para não sobrecarregar o servidor SQL
            MAX_CONCURRENT = 10
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            async def analyze_with_limit(db_name):
                async with semaphore:
                    return await self.analyze_database_patterns(server_id, db_name, window_days)

            # Executar todas as análises em paralelo
            tasks = [analyze_with_limit(db_name) for db_name in database_names]
            all_analyses = await asyncio.gather(*tasks, return_exceptions=True)

            # Filtrar exceções e manter apenas resultados válidos
            all_analyses = [a for a in all_analyses if not isinstance(a, Exception)]

            # Wave I (2026-05-19): FASE 2 — detectar DBs FULL/BULK_LOGGED com
            # LOG chain completamente quebrada (zero L records na janela).
            # _detect_gaps requer min_samples_for_pattern (default 3) — DBs sem
            # nenhum L na janela sao silenciosamente ignoradas. Este metodo
            # apanha-as via LEFT JOIN msdb sem filtro de janela.
            try:
                missing_chain_gaps_raw = await self._detect_missing_log_chain(server_id, window_days)
            except Exception as e:
                logger.warning(f"_detect_missing_log_chain raised, continuando sem fase 2: {e}")
                missing_chain_gaps_raw = []

            if missing_chain_gaps_raw:
                # DBs ja' com LOG gaps detectados pela analise de padrao (evitar duplicados)
                databases_already_with_log_gaps = {
                    a.database_name
                    for a in all_analyses
                    if any(g.backup_type == 'LOG' for g in a.detected_gaps)
                }

                # Mapa nome -> objecto para insercao/criacao
                analysis_by_db = {a.database_name: a for a in all_analyses}
                now_ts = datetime.now()

                for mc_gap in missing_chain_gaps_raw:
                    db_name = mc_gap.get('database_name')
                    if not db_name or db_name in databases_already_with_log_gaps:
                        continue

                    gap_obj = BackupGap(
                        backup_type=mc_gap['backup_type'],
                        expected_datetime=now_ts,
                        actual_datetime=None,
                        gap_hours=float(mc_gap.get('gap_hours') or 99999.0),
                        severity=mc_gap['severity'],
                        description=mc_gap['description'],
                    )

                    if db_name in analysis_by_db:
                        # Anexar ao analysis existente
                        analysis_by_db[db_name].detected_gaps.append(gap_obj)
                    else:
                        # DB existe em sys.databases mas analyze_database_patterns
                        # nao a processou (ex: nova DB adicionada apos query de lista).
                        # Criar analise minima para a incluir no resultado.
                        analysis_by_db[db_name] = DatabaseBackupPatternAnalysis(
                            database_name=db_name,
                            full_pattern=None,
                            diff_pattern=None,
                            log_pattern=None,
                            detected_gaps=[gap_obj],
                            overall_health_score=0.0,
                            analysis_date=now_ts,
                        )

                # Reconstruir all_analyses incluindo extras
                all_analyses = list(analysis_by_db.values())

            # Calcular métricas do servidor
            total_gaps = sum(len(a.detected_gaps) for a in all_analyses)
            databases_with_gaps = sum(1 for a in all_analyses if a.detected_gaps)
            critical_gaps = sum(1 for a in all_analyses for g in a.detected_gaps if g.severity == 'critical')
            
            overall_health = statistics.mean([a.overall_health_score for a in all_analyses]) if all_analyses else 0
            
            return {
                'success': True,
                'server_id': server_id,
                'total_databases': len(all_analyses),
                'databases': [asdict(a) for a in all_analyses],
                'overall_server_health': round(overall_health, 1),
                'summary': {
                    'databases_with_gaps': databases_with_gaps,
                    'total_gaps': total_gaps,
                    'critical_gaps': critical_gaps
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao analisar padrões do servidor {server_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

