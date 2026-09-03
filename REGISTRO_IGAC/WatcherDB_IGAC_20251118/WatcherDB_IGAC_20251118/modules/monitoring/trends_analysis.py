# ============================================================================
# WatcherDB ANÁLISE DE TENDÊNCIAS - ENDPOINT PARA VISUALIZAÇÃO
# ============================================================================
# Arquivo: modules/monitoring/trends_analysis.py
# ============================================================================

import asyncio
import logging
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from decimal import Decimal
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class TrendDataPoint:
    """Ponto de dados para análise de tendências"""
    timestamp: str
    server_id: str
    database_name: str
    filegroup_name: str
    size_gb: float
    used_gb: float
    free_gb: float
    usage_percent: float
    growth_rate_gb_per_day: float
    predicted_size_30d_gb: float
    confidence_score: float

@dataclass
class TrendAnalysis:
    """Análise de tendências de um filegroup"""
    server_id: str
    database_name: str
    filegroup_name: str
    
    # Dados históricos
    data_points: List[TrendDataPoint]
    total_data_points: int
    
    # Métricas de tendência
    current_size_gb: float
    current_usage_percent: float
    average_growth_rate_gb_per_day: float
    trend_direction: str  # 'increasing', 'decreasing', 'stable'
    trend_strength: float  # 0.0 a 1.0
    
    # Previsões
    predicted_size_7d_gb: float
    predicted_size_30d_gb: float
    predicted_size_90d_gb: float
    days_until_critical: int
    
    # Análise de risco
    risk_level: str  # 'low', 'medium', 'high', 'critical'
    risk_factors: List[str]
    recommendations: List[str]
    
    # Metadados
    analysis_timestamp: str
    confidence_score: float
    prediction_method: str

class TrendsAnalysisEngine:
    """Engine de análise de tendências para visualização"""
    
    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        
        self.risk_thresholds = {
            'critical_usage': 90,
            'high_usage': 80,
            'warning_usage': 70,
            'critical_growth_days': 7,
            'warning_growth_days': 30
        }
    
    async def get_server_trends(self, server_id: str, days_back: int = 30) -> Dict:
        """Retorna análise de tendências para um servidor"""
        try:
            logger.info(f"📈 [TRENDS] Iniciando análise de tendências para {server_id}")
            
            # 1. Buscar dados históricos (simulado por enquanto)
            historical_data = await self._get_historical_data(server_id, days_back)
            
            if not historical_data:
                logger.warning(f"⚠️ [TRENDS] Nenhum dado histórico encontrado para {server_id}")
                return self._empty_trends_result(server_id)
            
            # 2. Agregar por filegroup
            filegroup_trends = self._analyze_filegroup_trends(historical_data)
            
            # 3. Gerar métricas agregadas
            server_metrics = self._calculate_server_metrics(filegroup_trends)
            
            # 4. Log estruturado
            self._log_structured_event('trends_analysis_complete', {
                'server_id': server_id,
                'filegroups_analyzed': len(filegroup_trends),
                'total_data_points': sum(len(trend.data_points) for trend in filegroup_trends.values()),
                'high_risk_filegroups': len([t for t in filegroup_trends.values() if t.risk_level in ['high', 'critical']]),
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'server_id': server_id,
                'analysis_timestamp': datetime.now().isoformat(),
                'analysis_period_days': days_back,
                'total_filegroups': len(filegroup_trends),
                'server_metrics': server_metrics,
                'filegroup_trends': [asdict(trend) for trend in filegroup_trends.values()],
                'summary': {
                    'high_risk_filegroups': len([t for t in filegroup_trends.values() if t.risk_level in ['high', 'critical']]),
                    'increasing_trends': len([t for t in filegroup_trends.values() if t.trend_direction == 'increasing']),
                    'average_growth_rate': sum(t.average_growth_rate_gb_per_day for t in filegroup_trends.values()) / len(filegroup_trends) if filegroup_trends else 0
                }
            }
            
        except Exception as e:
            logger.error(f"❌ [TRENDS] Erro na análise: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
    
    async def _get_historical_data(self, server_id: str, days_back: int) -> List[Dict]:
        """Busca dados históricos (simulado por enquanto)"""
        # TODO: Implementar busca real de dados históricos
        # Por enquanto, vamos simular dados para demonstração
        
        historical_data = []
        base_date = datetime.now() - timedelta(days=days_back)
        
        # Simular dados para alguns filegroups
        sample_filegroups = [
            {'database': 'DW_ATH_01', 'filegroup': 'PRIMARY'},
            {'database': 'DW_ATH_01', 'filegroup': 'BKDREV_IDX'},
            {'database': 'CONTACT_CENTER_DAT', 'filegroup': 'PRIMARY'}
        ]
        
        for fg in sample_filegroups:
            # Simular crescimento ao longo do tempo
            base_size = 100.0  # GB
            growth_rate = 0.5  # GB por dia
            
            for day in range(days_back):
                current_date = base_date + timedelta(days=day)
                current_size = base_size + (growth_rate * day)
                usage_percent = min(85.0 + (day * 0.2), 95.0)  # Crescimento de uso
                
                historical_data.append({
                    'timestamp': current_date.isoformat(),
                    'server_id': server_id,
                    'database_name': fg['database'],
                    'filegroup_name': fg['filegroup'],
                    'size_gb': round(current_size, 2),
                    'used_gb': round(current_size * usage_percent / 100, 2),
                    'free_gb': round(current_size * (100 - usage_percent) / 100, 2),
                    'usage_percent': round(usage_percent, 2),
                    'growth_rate_gb_per_day': growth_rate
                })
        
        logger.info(f"📊 [TRENDS] {len(historical_data)} pontos históricos simulados")
        return historical_data
    
    def _analyze_filegroup_trends(self, historical_data: List[Dict]) -> Dict[str, TrendAnalysis]:
        """Analisa tendências por filegroup"""
        filegroup_trends = {}
        
        # Agrupar por filegroup
        grouped_data = defaultdict(list)
        for data_point in historical_data:
            key = f"{data_point['database_name']}_{data_point['filegroup_name']}"
            grouped_data[key].append(data_point)
        
        # Analisar cada filegroup
        for fg_key, data_points in grouped_data.items():
            if len(data_points) < 3:  # Mínimo de 3 pontos para análise
                continue
            
            # Ordenar por timestamp
            data_points.sort(key=lambda x: x['timestamp'])
            
            # Calcular métricas de tendência
            trend_analysis = self._calculate_trend_metrics(fg_key, data_points)
            filegroup_trends[fg_key] = trend_analysis
        
        return filegroup_trends
    
    def _calculate_trend_metrics(self, fg_key: str, data_points: List[Dict]) -> TrendAnalysis:
        """Calcula métricas de tendência para um filegroup"""
        # Dados atuais (último ponto)
        current = data_points[-1]
        
        # Calcular taxa de crescimento média
        if len(data_points) >= 2:
            first_size = data_points[0]['size_gb']
            last_size = data_points[-1]['size_gb']
            days_span = (datetime.fromisoformat(data_points[-1]['timestamp']) - 
                        datetime.fromisoformat(data_points[0]['timestamp'])).days
            
            if days_span > 0:
                avg_growth_rate = (last_size - first_size) / days_span
            else:
                avg_growth_rate = 0.0
        else:
            avg_growth_rate = 0.0
        
        # Determinar direção da tendência
        if avg_growth_rate > 0.1:
            trend_direction = 'increasing'
            trend_strength = min(avg_growth_rate / 2.0, 1.0)  # Normalizar
        elif avg_growth_rate < -0.1:
            trend_direction = 'decreasing'
            trend_strength = min(abs(avg_growth_rate) / 2.0, 1.0)
        else:
            trend_direction = 'stable'
            trend_strength = 0.1
        
        # Previsões
        predicted_7d = current['size_gb'] + (avg_growth_rate * 7)
        predicted_30d = current['size_gb'] + (avg_growth_rate * 30)
        predicted_90d = current['size_gb'] + (avg_growth_rate * 90)
        
        # Análise de risco
        risk_level, risk_factors, recommendations = self._assess_risk(
            current, avg_growth_rate, predicted_30d
        )
        
        # Converter data points para TrendDataPoint
        trend_data_points = []
        for dp in data_points:
            trend_data_points.append(TrendDataPoint(
                timestamp=dp['timestamp'],
                server_id=dp['server_id'],
                database_name=dp['database_name'],
                filegroup_name=dp['filegroup_name'],
                size_gb=dp['size_gb'],
                used_gb=dp['used_gb'],
                free_gb=dp['free_gb'],
                usage_percent=dp['usage_percent'],
                growth_rate_gb_per_day=dp.get('growth_rate_gb_per_day', avg_growth_rate),
                predicted_size_30d_gb=dp['size_gb'] + (avg_growth_rate * 30),
                confidence_score=0.8
            ))
        
        return TrendAnalysis(
            server_id=current['server_id'],
            database_name=current['database_name'],
            filegroup_name=current['filegroup_name'],
            data_points=trend_data_points,
            total_data_points=len(data_points),
            current_size_gb=current['size_gb'],
            current_usage_percent=current['usage_percent'],
            average_growth_rate_gb_per_day=round(avg_growth_rate, 3),
            trend_direction=trend_direction,
            trend_strength=round(trend_strength, 2),
            predicted_size_7d_gb=round(predicted_7d, 2),
            predicted_size_30d_gb=round(predicted_30d, 2),
            predicted_size_90d_gb=round(predicted_90d, 2),
            days_until_critical=self._calculate_days_until_critical(current, avg_growth_rate),
            risk_level=risk_level,
            risk_factors=risk_factors,
            recommendations=recommendations,
            analysis_timestamp=datetime.now().isoformat(),
            confidence_score=0.8,
            prediction_method='linear_regression'
        )
    
    def _assess_risk(self, current: Dict, growth_rate: float, predicted_30d: float) -> tuple:
        """Avalia nível de risco e gera recomendações"""
        risk_factors = []
        recommendations = []
        
        # Fator 1: Uso atual
        if current['usage_percent'] >= self.risk_thresholds['critical_usage']:
            risk_factors.append('Uso crítico atual')
            recommendations.append('🔴 AÇÃO IMEDIATA: Expandir filegroup agora')
        elif current['usage_percent'] >= self.risk_thresholds['high_usage']:
            risk_factors.append('Uso alto atual')
            recommendations.append('🟠 ATENÇÃO: Planejar expansão em 7 dias')
        
        # Fator 2: Taxa de crescimento
        if growth_rate > 1.0:  # > 1GB/dia
            risk_factors.append('Crescimento acelerado')
            recommendations.append('⚡ Monitorar crescimento: Taxa alta detectada')
        
        # Fator 3: Projeção futura
        if predicted_30d > current['size_gb'] * 1.5:  # 50% de crescimento em 30 dias
            risk_factors.append('Projeção de crescimento alta')
            recommendations.append('📈 Planejar expansão: Crescimento projetado alto')
        
        # Determinar nível de risco
        if len(risk_factors) >= 3 or current['usage_percent'] >= 90:
            risk_level = 'critical'
        elif len(risk_factors) >= 2 or current['usage_percent'] >= 80:
            risk_level = 'high'
        elif len(risk_factors) >= 1 or current['usage_percent'] >= 70:
            risk_level = 'medium'
        else:
            risk_level = 'low'
            recommendations.append('✅ Filegroup saudável')
        
        return risk_level, risk_factors, recommendations
    
    def _calculate_days_until_critical(self, current: Dict, growth_rate: float) -> int:
        """Calcula dias até atingir uso crítico"""
        if growth_rate <= 0:
            return 999  # Sem crescimento
        
        current_usage = current['usage_percent']
        critical_usage = self.risk_thresholds['critical_usage']
        
        if current_usage >= critical_usage:
            return 0  # Já crítico
        
        # Calcular dias baseado na taxa de crescimento do uso
        usage_growth_rate = growth_rate / current['size_gb'] * 100  # % por dia
        if usage_growth_rate <= 0:
            return 999
        
        days_until_critical = (critical_usage - current_usage) / usage_growth_rate
        return max(0, int(days_until_critical))
    
    def _calculate_server_metrics(self, filegroup_trends: Dict[str, TrendAnalysis]) -> Dict:
        """Calcula métricas agregadas do servidor"""
        if not filegroup_trends:
            return {}
        
        total_filegroups = len(filegroup_trends)
        high_risk_count = len([t for t in filegroup_trends.values() if t.risk_level in ['high', 'critical']])
        increasing_trends = len([t for t in filegroup_trends.values() if t.trend_direction == 'increasing'])
        
        avg_growth_rate = sum(t.average_growth_rate_gb_per_day for t in filegroup_trends.values()) / total_filegroups
        total_current_size = sum(t.current_size_gb for t in filegroup_trends.values())
        total_predicted_30d = sum(t.predicted_size_30d_gb for t in filegroup_trends.values())
        
        return {
            'total_filegroups': total_filegroups,
            'high_risk_filegroups': high_risk_count,
            'increasing_trends': increasing_trends,
            'average_growth_rate_gb_per_day': round(avg_growth_rate, 3),
            'total_current_size_gb': round(total_current_size, 2),
            'total_predicted_30d_gb': round(total_predicted_30d, 2),
            'growth_percentage_30d': round((total_predicted_30d - total_current_size) / total_current_size * 100, 2) if total_current_size > 0 else 0
        }
    
    def _log_structured_event(self, event_type: str, data: Dict):
        """Log estruturado em JSON para análise posterior de ML"""
        log_data = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        logger.info(json.dumps(log_data, ensure_ascii=False))
    
    def _empty_trends_result(self, server_id: str) -> Dict:
        """Resultado vazio para tendências"""
        return {
            'server_id': server_id,
            'analysis_timestamp': datetime.now().isoformat(),
            'analysis_period_days': 0,
            'total_filegroups': 0,
            'server_metrics': {},
            'filegroup_trends': [],
            'summary': {
                'high_risk_filegroups': 0,
                'increasing_trends': 0,
                'average_growth_rate': 0
            }
        }
