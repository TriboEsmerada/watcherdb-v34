# ============================================================================
# SISTEMA DE ALERTAS PREDITIVOS - VERSÃO CORRIGIDA
# ============================================================================
# Análise agregada por FILEGROUP (não por datafile individual)
# ============================================================================

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from decimal import Decimal
from collections import defaultdict

logger = logging.getLogger(__name__)

def to_float(value) -> float:
    """Converte Decimal para float"""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


@dataclass
class FileGroupAnalysis:
    """Análise agregada de um filegroup completo"""
    server_id: str
    database_name: str
    filegroup_name: str
    
    # Dados agregados dos datafiles
    total_datafiles: int
    total_size_gb: float  # Soma de todos os datafiles
    total_used_gb: float
    total_free_gb: float
    total_maxsize_gb: float  # Soma dos MAXSIZE de todos os files
    
    # Análise individual dos datafiles
    datafiles_at_limit: int  # Quantos files já estão no MAXSIZE
    datafiles_with_space: int  # Quantos files ainda podem crescer
    
    # Capacidade real disponível
    available_growth_gb: float  # Quanto o filegroup ainda pode crescer
    disk_available_gb: float
    
    # Métricas de uso
    usage_percent: float  # % usado do tamanho atual total
    maxsize_utilization_percent: float  # % usado do MAXSIZE total
    
    # Previsões
    estimated_growth_per_day_gb: float
    days_until_filegroup_full: int
    predicted_usage_30d_percent: float
    
    # Status de risco
    has_overflow_risk: bool
    risk_type: str  # 'MAXSIZE' ou 'DISK' ou 'NONE'
    limiting_factor: str  # O que está limitando o crescimento


@dataclass
class PredictiveAlert:
    """Alerta preditivo de espaço"""
    server_id: str
    database_name: str
    filegroup_name: str
    alert_type: str
    severity: str
    
    # Dados do filegroup agregado
    total_datafiles: int
    datafiles_at_limit: int
    datafiles_with_space: int
    
    current_usage_percent: float
    predicted_usage_percent: float
    days_until_full: int
    current_free_gb: float
    available_growth_gb: float
    estimated_growth_per_day_gb: float
    
    total_size_gb: float
    total_maxsize_gb: float
    disk_available_gb: float
    
    risk_type: str
    recommendation: str
    timestamp: datetime


class PredictiveAlertsEngine:
    """Engine de análise preditiva - VERSÃO AGREGADA"""
    
    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        
        self.thresholds = {
            'critical_usage': 90,
            'high_usage': 80,
            'warning_usage': 70,
            'critical_days': 7,
            'warning_days': 30,
            'growth_acceleration': 20
        }
    
    async def analyze_server_alerts(self, server_id: str) -> Dict:
        """Análise completa de alertas preditivos agregados por filegroup"""
        try:
            logger.info(f"🔮 Analisando alertas preditivos para {server_id}")
            
            # 1. Buscar todos os datafiles do servidor
            datafiles = await self._get_all_datafiles(server_id)
            
            if not datafiles:
                return self._empty_result(server_id)
            
            # 2. AGREGAR DATAFILES POR FILEGROUP
            filegroups = self._aggregate_by_filegroup(datafiles)
            
            logger.info(f"📊 {len(filegroups)} filegroups únicos encontrados")
            
            # 3. Analisar cada filegroup agregado
            alerts = []
            
            for fg_key, fg_analysis in filegroups.items():
                # Analisar apenas DATA filegroups
                if fg_analysis.filegroup_name == 'DATA':
                    fg_alerts = await self._analyze_filegroup_aggregated(fg_analysis)
                    alerts.extend(fg_alerts)
            
            # 4. Categorizar e gerar recomendações
            categorized = self._categorize_alerts(alerts)
            recommendations = self._generate_recommendations(categorized)
            health_score = self._calculate_predictive_health(categorized)
            
            return {
                'server_id': server_id,
                'timestamp': datetime.now().isoformat(),
                'predictive_health_score': health_score,
                'total_alerts': len(alerts),
                'total_filegroups_analyzed': len(filegroups),
                'alerts_by_severity': {
                    'critical': categorized['critical'],
                    'high': categorized['high'],
                    'medium': categorized['medium'],
                    'low': categorized['low']
                },
                'alerts_by_type': {
                    'space_critical': categorized['by_type']['space_critical'],
                    'growth_trend': categorized['by_type']['growth_trend'],
                    'maxsize_approaching': categorized['by_type']['maxsize_approaching'],
                    'disk_saturation': categorized['by_type']['disk_saturation']
                },
                'alerts': [asdict(a) for a in alerts],
                'recommendations': recommendations
            }
            
        except Exception as e:
            logger.error(f"Erro na análise preditiva: {e}", exc_info=True)
            return {'error': str(e), 'server_id': server_id}
    
    async def _get_all_datafiles(self, server_id: str) -> List[Dict]:
        """Busca TODOS os datafiles de todas as databases do servidor"""
        try:
            # Query que busca TODOS os datafiles com seus detalhes
            query = """
            SELECT 
                d.name AS database_name,
                fg.name AS filegroup_name,
                df.name AS logical_name,
                df.type_desc AS file_type,
                df.size * 8.0 / 1024 AS size_mb,
                df.max_size * 8.0 / 1024 AS max_size_mb,
                CASE 
                    WHEN df.max_size = -1 THEN 'UNLIMITED'
                    WHEN df.max_size = 268435456 THEN 'UNLIMITED'
                    ELSE CAST(df.max_size * 8.0 / 1024 AS VARCHAR) + ' MB'
                END AS max_size_formatted,
                df.growth * 8.0 / 1024 AS growth_mb,
                FILEPROPERTY(df.name, 'SpaceUsed') * 8.0 / 1024 AS used_mb,
                (df.size - FILEPROPERTY(df.name, 'SpaceUsed')) * 8.0 / 1024 AS free_mb,
                df.physical_name,
                LEFT(df.physical_name, 1) AS volume
            FROM sys.databases d
            JOIN sys.master_files df ON d.database_id = df.database_id
            LEFT JOIN sys.filegroups fg ON df.data_space_id = fg.data_space_id
            WHERE d.database_id > 4  -- Ignora system databases
                AND d.state = 0  -- ONLINE
            ORDER BY d.name, fg.name, df.name
            """
            
            # Usar API padronizada do SQLServerMonitoring
            result = await self.sql_monitoring.execute_query(server_id, query)
            if not result or not result.get('success'):
                logger.error(f"Erro na query de datafiles: {result.get('error','desconhecido')}")
                return []

            rows = result.get('rows', [])
            # As linhas já vêm como dicionários; normalizar tipos simples
            datafiles = []
            for row in rows:
                try:
                    df = dict(row)
                    # Garantir nomes coerentes
                    df['server_id'] = server_id
                    datafiles.append(df)
                except Exception:
                    continue
            logger.info(f"✅ {len(datafiles)} datafiles encontrados em {server_id}")
            return datafiles
            
        except Exception as e:
            logger.error(f"Erro ao buscar datafiles: {e}")
            return []
    
    def _aggregate_by_filegroup(self, datafiles: List[Dict]) -> Dict[str, FileGroupAnalysis]:
        """
        Agrega múltiplos datafiles no mesmo filegroup
        
        KEY INSIGHT: Um filegroup pode ter vários datafiles.
        Se um file estourou o MAXSIZE mas outros ainda têm espaço,
        o filegroup ainda pode crescer!
        """
        filegroups = {}
        
        # Agrupar por (database, filegroup)
        grouped = defaultdict(list)
        for df in datafiles:
            key = (df['database_name'], df['filegroup_name'] or 'LOG')
            grouped[key].append(df)
        
        for (db_name, fg_name), files in grouped.items():
            # Calcular totais agregados
            total_size_mb = sum(to_float(f['size_mb']) for f in files)
            total_used_mb = sum(to_float(f['used_mb']) for f in files)
            total_free_mb = total_size_mb - total_used_mb
            
            # MAXSIZE agregado (soma de todos os files)
            total_maxsize_mb = 0
            has_unlimited = False
            datafiles_at_limit = 0
            datafiles_with_space = 0
            
            for f in files:
                max_mb = to_float(f['max_size_mb'])
                size_mb = to_float(f['size_mb'])
                
                if max_mb >= 999999 or f['max_size_formatted'] == 'UNLIMITED':
                    has_unlimited = True
                    total_maxsize_mb = 999999999  # Considera UNLIMITED
                else:
                    total_maxsize_mb += max_mb
                    
                    # Verifica se file individual está no limite
                    if size_mb >= max_mb * 0.99:  # 99% do MAXSIZE
                        datafiles_at_limit += 1
                    else:
                        datafiles_with_space += 1
            
            # Capacidade disponível para crescimento
            if has_unlimited:
                available_growth_gb = 999999.0  # Ilimitado
            else:
                available_growth_gb = (total_maxsize_mb - total_size_mb) / 1024
            
            # Buscar espaço em disco (usar o volume do primeiro file)
            volume = files[0].get('volume', 'C')
            disk_available_gb = 100.0  # TODO: Buscar do sistema operacional real
            
            # Calcular métricas
            usage_percent = (total_used_mb / total_size_mb * 100) if total_size_mb > 0 else 0
            
            if has_unlimited:
                maxsize_utilization = 0.0
            else:
                maxsize_utilization = (total_size_mb / total_maxsize_mb * 100) if total_maxsize_mb > 0 else 0
            
            # Estimar crescimento
            growth_per_day_gb = self._estimate_daily_growth(
                total_size_mb / 1024, 
                usage_percent
            )
            
            # Determinar fator limitante
            if has_unlimited:
                limiting_factor = 'DISK'
                limit_gb = disk_available_gb
            else:
                limit_gb = available_growth_gb
                limiting_factor = 'MAXSIZE' if available_growth_gb < disk_available_gb else 'DISK'
        
        # Dias até ficar cheio
            if growth_per_day_gb > 0 and limit_gb > 0:
                days_until_full = int(limit_gb / growth_per_day_gb)
            else:
                days_until_full = 999
        
        # Uso previsto em 30 dias
            predicted_30d = usage_percent + (growth_per_day_gb * 30 / (total_size_mb / 1024) * 100)
            
            # Risco de overflow
            has_overflow_risk = False
            risk_type = 'NONE'
            
            if not has_unlimited:
                if total_size_mb >= total_maxsize_mb * 0.95:  # 95% do MAXSIZE total
                    has_overflow_risk = True
                    risk_type = 'MAXSIZE'
            
            if disk_available_gb < 50 and days_until_full <= 30:
                has_overflow_risk = True
                risk_type = 'DISK'
            
            # Criar análise agregada
            fg_key = f"{db_name}_{fg_name}"
            filegroups[fg_key] = FileGroupAnalysis(
                server_id=files[0].get('server_id', 'UNKNOWN'),
                database_name=db_name,
                filegroup_name=fg_name,
                total_datafiles=len(files),
                total_size_gb=total_size_mb / 1024,
                total_used_gb=total_used_mb / 1024,
                total_free_gb=total_free_mb / 1024,
                total_maxsize_gb=total_maxsize_mb / 1024,
                datafiles_at_limit=datafiles_at_limit,
                datafiles_with_space=datafiles_with_space,
                available_growth_gb=available_growth_gb,
                disk_available_gb=disk_available_gb,
                usage_percent=usage_percent,
                maxsize_utilization_percent=maxsize_utilization,
                estimated_growth_per_day_gb=growth_per_day_gb,
                days_until_filegroup_full=days_until_full,
                predicted_usage_30d_percent=predicted_30d,
                has_overflow_risk=has_overflow_risk,
                risk_type=risk_type,
                limiting_factor=limiting_factor
            )
        
        return filegroups
    
    async def _analyze_filegroup_aggregated(self, fg: FileGroupAnalysis) -> List[PredictiveAlert]:
        """Analisa filegroup AGREGADO e gera alertas contextualizados"""
        alerts = []
        
        # ========================================
        # ALERTA 1: SPACE_CRITICAL (Uso atual alto)
        # ========================================
        if fg.usage_percent >= self.thresholds['critical_usage']:
            severity = 'CRITICAL'
            recommendation = (
                f"🔴 URGENTE: {fg.database_name}.{fg.filegroup_name} com {fg.usage_percent:.1f}% usado. "
                f"{fg.datafiles_at_limit}/{fg.total_datafiles} datafiles no limite MAXSIZE. "
                f"Expandir imediatamente ou adicionar novo datafile com {fg.total_free_gb * 0.5:.0f}GB."
            )
        elif fg.usage_percent >= self.thresholds['high_usage']:
            severity = 'HIGH'
            recommendation = (
                f"🟠 ATENÇÃO: {fg.database_name}.{fg.filegroup_name} em {fg.usage_percent:.1f}% de uso. "
                f"Planejar expansão nos próximos 7 dias."
            )
        elif fg.usage_percent >= self.thresholds['warning_usage']:
            severity = 'MEDIUM'
            recommendation = (
                f"🟡 Monitorar: {fg.database_name}.{fg.filegroup_name} em {fg.usage_percent:.1f}% de uso. "
                f"Revisar em 14 dias."
            )
        else:
            severity = None
        
        if severity:
            alerts.append(PredictiveAlert(
                server_id=fg.server_id,
                database_name=fg.database_name,
                filegroup_name=fg.filegroup_name,
                alert_type='SPACE_CRITICAL',
                severity=severity,
                total_datafiles=fg.total_datafiles,
                datafiles_at_limit=fg.datafiles_at_limit,
                datafiles_with_space=fg.datafiles_with_space,
                current_usage_percent=round(fg.usage_percent, 2),
                predicted_usage_percent=round(fg.predicted_usage_30d_percent, 2),
                days_until_full=fg.days_until_filegroup_full,
                current_free_gb=round(fg.total_free_gb, 2),
                available_growth_gb=round(fg.available_growth_gb, 2),
                estimated_growth_per_day_gb=round(fg.estimated_growth_per_day_gb, 3),
                total_size_gb=round(fg.total_size_gb, 2),
                total_maxsize_gb=round(fg.total_maxsize_gb, 2),
                disk_available_gb=round(fg.disk_available_gb, 2),
                risk_type=fg.risk_type,
                recommendation=recommendation,
                timestamp=datetime.now()
            ))
        
        # ========================================
        # ALERTA 2: GROWTH_TREND (Crescimento acelerado)
        # ========================================
        if fg.days_until_filegroup_full <= self.thresholds['critical_days'] and fg.days_until_filegroup_full > 0:
            severity = 'CRITICAL' if fg.days_until_filegroup_full <= 3 else 'HIGH'
            
            alerts.append(PredictiveAlert(
                server_id=fg.server_id,
                database_name=fg.database_name,
                filegroup_name=fg.filegroup_name,
                alert_type='GROWTH_TREND',
                severity=severity,
                total_datafiles=fg.total_datafiles,
                datafiles_at_limit=fg.datafiles_at_limit,
                datafiles_with_space=fg.datafiles_with_space,
                current_usage_percent=round(fg.usage_percent, 2),
                predicted_usage_percent=100.0,
                days_until_full=fg.days_until_filegroup_full,
                current_free_gb=round(fg.total_free_gb, 2),
                available_growth_gb=round(fg.available_growth_gb, 2),
                estimated_growth_per_day_gb=round(fg.estimated_growth_per_day_gb, 3),
                total_size_gb=round(fg.total_size_gb, 2),
                total_maxsize_gb=round(fg.total_maxsize_gb, 2),
                disk_available_gb=round(fg.disk_available_gb, 2),
                risk_type=fg.risk_type,
                recommendation=(
                    f"⚡ CRESCIMENTO ACELERADO: {fg.database_name}.{fg.filegroup_name} "
                    f"ficará cheio em {fg.days_until_filegroup_full} dias. "
                    f"Taxa: {fg.estimated_growth_per_day_gb:.2f}GB/dia. "
                    f"Limite: {fg.limiting_factor}. Ação imediata!"
                ),
                timestamp=datetime.now()
            ))
        
        # ========================================
        # ALERTA 3: MAXSIZE_APPROACHING
        # ========================================
        if fg.total_maxsize_gb < 999999:  # Não é UNLIMITED
            if fg.maxsize_utilization_percent >= 95:
                severity = 'CRITICAL'
                recommendation = (
                    f"🚨 MAXSIZE CRÍTICO: {fg.database_name}.{fg.filegroup_name} em "
                    f"{fg.maxsize_utilization_percent:.1f}% do MAXSIZE total. "
                    f"{fg.datafiles_at_limit} datafiles já no limite. "
                    f"Aumentar MAXSIZE ou adicionar novo datafile AGORA!"
                )
            elif fg.maxsize_utilization_percent >= 85:
                severity = 'HIGH'
                recommendation = (
                    f"⚠️ Próximo ao MAXSIZE: {fg.database_name}.{fg.filegroup_name} em "
                    f"{fg.maxsize_utilization_percent:.1f}% do limite total. "
                    f"Planejar aumento de MAXSIZE."
                )
            else:
                severity = None
            
            if severity:
                alerts.append(PredictiveAlert(
                    server_id=fg.server_id,
                    database_name=fg.database_name,
                    filegroup_name=fg.filegroup_name,
                    alert_type='MAXSIZE_APPROACHING',
                    severity=severity,
                    total_datafiles=fg.total_datafiles,
                    datafiles_at_limit=fg.datafiles_at_limit,
                    datafiles_with_space=fg.datafiles_with_space,
                    current_usage_percent=round(fg.maxsize_utilization_percent, 2),
                    predicted_usage_percent=100.0,
                    days_until_full=fg.days_until_filegroup_full,
                    current_free_gb=round(fg.available_growth_gb, 2),
                    available_growth_gb=round(fg.available_growth_gb, 2),
                    estimated_growth_per_day_gb=round(fg.estimated_growth_per_day_gb, 3),
                    total_size_gb=round(fg.total_size_gb, 2),
                    total_maxsize_gb=round(fg.total_maxsize_gb, 2),
                    disk_available_gb=round(fg.disk_available_gb, 2),
                    risk_type='MAXSIZE',
                    recommendation=recommendation,
                    timestamp=datetime.now()
                ))
        
        # ========================================
        # ALERTA 4: DISK_SATURATION
        # ========================================
        if fg.disk_available_gb > 0:
            days_until_disk_full = int(fg.disk_available_gb / fg.estimated_growth_per_day_gb) if fg.estimated_growth_per_day_gb > 0 else 999
            
            if fg.disk_available_gb < 50 and days_until_disk_full <= 14:
                severity = 'CRITICAL' if days_until_disk_full <= 7 else 'HIGH'
                
                alerts.append(PredictiveAlert(
                    server_id=fg.server_id,
                    database_name=fg.database_name,
                    filegroup_name=fg.filegroup_name,
                    alert_type='DISK_SATURATION',
                    severity=severity,
                    total_datafiles=fg.total_datafiles,
                    datafiles_at_limit=fg.datafiles_at_limit,
                    datafiles_with_space=fg.datafiles_with_space,
                    current_usage_percent=round(fg.usage_percent, 2),
                    predicted_usage_percent=round(fg.predicted_usage_30d_percent, 2),
                    days_until_full=days_until_disk_full,
                    current_free_gb=round(fg.total_free_gb, 2),
                    available_growth_gb=round(fg.available_growth_gb, 2),
                    estimated_growth_per_day_gb=round(fg.estimated_growth_per_day_gb, 3),
                    total_size_gb=round(fg.total_size_gb, 2),
                    total_maxsize_gb=round(fg.total_maxsize_gb, 2),
                    disk_available_gb=round(fg.disk_available_gb, 2),
                    risk_type='DISK',
                    recommendation=(
                        f"💾 DISCO SATURANDO: Apenas {fg.disk_available_gb:.1f}GB livres. "
                        f"Disco cheio em ~{days_until_disk_full} dias. Expandir storage!"
                    ),
                    timestamp=datetime.now()
                ))
        
        return alerts
    
    def _estimate_daily_growth(self, total_gb: float, usage_percent: float) -> float:
        """Estima crescimento diário baseado em heurísticas"""
        base_growth = 0.01
        
        if total_gb < 100:
            size_factor = 0.02
        elif total_gb < 1000:
            size_factor = 0.01
        else:
            size_factor = 0.005
        
        usage_factor = 1.0 + (usage_percent / 100) * 0.5
        daily_growth_gb = total_gb * size_factor * usage_factor
        
        return max(daily_growth_gb, 0.1)
    
    def _categorize_alerts(self, alerts: List[PredictiveAlert]) -> Dict:
        """Categoriza alertas por severidade e tipo"""
        categorized = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': [],
            'by_type': {
                'space_critical': [],
                'growth_trend': [],
                'maxsize_approaching': [],
                'disk_saturation': []
            }
        }
        
        for alert in alerts:
            if alert.severity == 'CRITICAL':
                categorized['critical'].append(alert)
            elif alert.severity == 'HIGH':
                categorized['high'].append(alert)
            elif alert.severity == 'MEDIUM':
                categorized['medium'].append(alert)
            else:
                categorized['low'].append(alert)
            
            categorized['by_type'][alert.alert_type.lower()].append(alert)
        
        return categorized
    
    def _generate_recommendations(self, categorized: Dict) -> List[str]:
        """Gera recomendações consolidadas"""
        recommendations = []
        
        critical_count = len(categorized['critical'])
        high_count = len(categorized['high'])
        
        if critical_count > 0:
            recommendations.append(
                f"🔴 AÇÃO IMEDIATA: {critical_count} filegroups requerem intervenção URGENTE nas próximas 24-48h"
            )
        
        if high_count > 0:
            recommendations.append(
                f"🟠 ATENÇÃO: {high_count} filegroups precisam de ação nos próximos 7 dias"
            )
        
        space_critical = len(categorized['by_type']['space_critical'])
        if space_critical > 0:
            recommendations.append(
                f"📊 {space_critical} filegroups com uso >70% - Planejar expansão"
            )
        
        growth_trend = len(categorized['by_type']['growth_trend'])
        if growth_trend > 0:
            recommendations.append(
                f"📈 {growth_trend} filegroups com crescimento acelerado detectado"
            )
        
        maxsize_approaching = len(categorized['by_type']['maxsize_approaching'])
        if maxsize_approaching > 0:
            recommendations.append(
                f"⚠️ {maxsize_approaching} filegroups próximos do MAXSIZE agregado - Aumentar limite ou adicionar datafile"
            )
        
        disk_saturation = len(categorized['by_type']['disk_saturation'])
        if disk_saturation > 0:
            recommendations.append(
                f"💾 {disk_saturation} volumes com disco ficando cheio - Expandir storage"
            )
        
        if not recommendations:
            recommendations.append("✅ Nenhum alerta crítico. Sistema operando normalmente.")
        
        return recommendations
    
    def _calculate_predictive_health(self, categorized: Dict) -> float:
        """Calcula score de saúde preditiva (0-100)"""
        base_score = 100.0
        
        critical_penalty = len(categorized['critical']) * 15
        high_penalty = len(categorized['high']) * 8
        medium_penalty = len(categorized['medium']) * 3
        
        total_penalty = critical_penalty + high_penalty + medium_penalty
        score = max(0.0, base_score - total_penalty)
        
        return round(score, 1)
    
    def _empty_result(self, server_id: str) -> Dict:
        """Resultado vazio quando não há dados"""
        return {
            'server_id': server_id,
            'timestamp': datetime.now().isoformat(),
            'predictive_health_score': 100.0,
            'total_alerts': 0,
            'total_filegroups_analyzed': 0,
            'alerts_by_severity': {
                'critical': [],
                'high': [],
                'medium': [],
                'low': []
            },
            'alerts_by_type': {
                'space_critical': [],
                'growth_trend': [],
                'maxsize_approaching': [],
                'disk_saturation': []
            },
            'alerts': [],
            'recommendations': ['✅ Nenhum alerta preditivo.']
        }