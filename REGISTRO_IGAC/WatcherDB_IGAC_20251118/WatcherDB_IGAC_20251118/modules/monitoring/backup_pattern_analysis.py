"""
TapOS Backup Pattern Analysis - Análise de Padrões de Backup
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
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
import statistics

logger = logging.getLogger(__name__)


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
            
            # 1. Buscar histórico de backups
            backup_history = await self._get_backup_history(server_id, database_name, window_days)
            
            if not backup_history or not backup_history.get('success'):
                logger.warning(f"Não foi possível obter histórico de backup para {database_name}")
                return self._empty_analysis(database_name)
            
            backups_by_type = backup_history.get('backups_by_type', {})
            
            logger.info(f"📊 Histórico obtido: FULL={len(backups_by_type.get('D', []))}, "
                       f"DIFF={len(backups_by_type.get('I', []))}, "
                       f"LOG={len(backups_by_type.get('L', []))}")
            
            # 2. Analisar padrão de cada tipo de backup
            full_pattern = self._analyze_pattern(backups_by_type.get('D', []), 'FULL')
            diff_pattern = self._analyze_pattern(backups_by_type.get('I', []), 'DIFF')
            log_pattern = self._analyze_pattern(backups_by_type.get('L', []), 'LOG')
            
            # 3. Detectar gaps baseado nos padrões identificados
            detected_gaps = []
            now = datetime.now()
            
            if full_pattern and full_pattern.confidence_score >= 60:
                gaps = self._detect_gaps(backups_by_type.get('D', []), full_pattern, now)
                detected_gaps.extend(gaps)
                logger.info(f"✅ FULL pattern: {full_pattern.frequency_description} (confiança: {full_pattern.confidence_score:.1f}%)")
            
            if diff_pattern and diff_pattern.confidence_score >= 60:
                gaps = self._detect_gaps(backups_by_type.get('I', []), diff_pattern, now)
                detected_gaps.extend(gaps)
                logger.info(f"✅ DIFF pattern: {diff_pattern.frequency_description} (confiança: {diff_pattern.confidence_score:.1f}%)")
            
            if log_pattern and log_pattern.confidence_score >= 60:
                gaps = self._detect_gaps(backups_by_type.get('L', []), log_pattern, now)
                detected_gaps.extend(gaps)
                logger.info(f"✅ LOG pattern: {log_pattern.frequency_description} (confiança: {log_pattern.confidence_score:.1f}%)")
            
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
                    except:
                        try:
                            backup_date = datetime.strptime(backup_date, '%Y-%m-%d %H:%M:%S')
                        except:
                            try:
                                backup_date = datetime.strptime(backup_date, '%Y-%m-%d %H:%M:%S.%f')
                            except:
                                try:
                                    backup_date = datetime.strptime(backup_date, '%Y-%m-%d')
                                except:
                                    continue
                
                backups_by_type[backup_type].append(backup_date)
        
        return {
            'success': True,
            'backups_by_type': dict(backups_by_type)
        }
    
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
                     now: datetime) -> List[BackupGap]:
        """
        Detecta gaps (backups esperados mas que não ocorreram) baseado no padrão.
        
        Args:
            backup_dates: Lista de datas dos backups
            pattern: Padrão identificado
            now: Data/hora atual
            
        Returns:
            Lista de gaps detectados
        """
        if not backup_dates or not pattern:
            return []
        
        gaps = []
        sorted_dates = sorted(backup_dates)
        
        # Verificar gaps ENTRE backups históricos (não apenas o último)
        expected_interval = pattern.avg_interval_hours
        tolerance = pattern.std_interval_hours * 2  # 2x desvio padrão como tolerância
        
        for i in range(1, len(sorted_dates)):
            prev_backup = sorted_dates[i-1]
            curr_backup = sorted_dates[i]
            actual_interval = (curr_backup - prev_backup).total_seconds() / 3600.0
            
            # Se o intervalo for muito maior que o esperado, temos um gap
            if actual_interval > (expected_interval + tolerance):
                # Calcular quando era esperado
                expected_datetime = prev_backup + timedelta(hours=expected_interval)
                gap_hours = (curr_backup - expected_datetime).total_seconds() / 3600.0
                
                severity = self._classify_gap_severity(pattern.backup_type, gap_hours)
                
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
            severity = self._classify_gap_severity(pattern.backup_type, gap_hours)
            
            gaps.append(BackupGap(
                backup_type=pattern.backup_type,
                expected_datetime=expected_next,
                actual_datetime=None,  # Ainda não ocorreu
                gap_hours=round(gap_hours, 1),
                severity=severity,
                description=f"Backup esperado em {expected_next.strftime('%Y-%m-%d %H:%M')}, ainda não ocorreu ({gap_hours:.1f}h de atraso)"
            ))
        
        return gaps
    
    def _classify_gap_severity(self, backup_type: str, gap_hours: float) -> str:
        """
        Classifica severidade de um gap.
        
        Returns: 'low', 'medium', 'high', 'critical'
        """
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
            # Buscar lista de databases
            query = """
            SELECT name 
            FROM sys.databases 
            WHERE database_id > 4 
              AND state = 0
            ORDER BY name;
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query)
            if not result or not result.get('success'):
                return {'success': False, 'error': 'Failed to get database list'}
            
            database_names = [row.get('name') for row in result.get('rows', []) if row.get('name')]
            
            # Analisar cada database
            all_analyses = []
            for db_name in database_names:
                analysis = await self.analyze_database_patterns(server_id, db_name, window_days)
                all_analyses.append(analysis)
            
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

