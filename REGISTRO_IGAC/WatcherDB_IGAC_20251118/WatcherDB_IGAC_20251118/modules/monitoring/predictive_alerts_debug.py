# ============================================================================
# WatcherDB ALERTAS PREDITIVOS - VERSÃO COM DEBUG E DADOS REAIS
# ============================================================================
# Arquivo: modules/monitoring/predictive_alerts_debug.py
# ============================================================================

import asyncio
import logging
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from decimal import Decimal
from collections import defaultdict
from functools import lru_cache
from hashlib import md5

logger = logging.getLogger(__name__)

def to_float(value) -> float:
    """Converte Decimal para float com tratamento de erros"""
    if value is None:
        return 0.0
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao converter valor para float: {value} - {e}")
        return 0.0


@dataclass
class FileGroupAnalysis:
    """Análise agregada de um filegroup completo"""
    server_id: str
    database_name: str
    filegroup_name: str
    
    total_datafiles: int
    total_size_gb: float
    total_used_gb: float
    total_free_gb: float
    total_maxsize_gb: float
    
    datafiles_at_limit: int
    datafiles_with_space: int
    
    available_growth_gb: float
    disk_available_gb: float
    
    usage_percent: float
    maxsize_utilization_percent: float
    
    estimated_growth_per_day_gb: float
    days_until_filegroup_full: int
    predicted_usage_30d_percent: float
    
    has_overflow_risk: bool
    risk_type: str
    limiting_factor: str


@dataclass
class PredictiveAlert:
    """Alerta preditivo de espaço"""
    server_id: str
    database_name: str
    filegroup_name: str
    alert_type: str
    severity: str
    
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
    timestamp: str  # Mudado para string para serialização JSON
    
    # Novos campos para ML e confiança
    confidence_score: float = 0.8  # 0.0 a 1.0
    prediction_method: str = 'heuristic'  # 'heuristic', 'ml', 'hybrid'
    historical_data_points: int = 0  # Número de pontos históricos usados


class PredictiveAlertsEngine:
    """Engine de análise preditiva - COM DADOS REAIS"""
    
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
        
        # Cache para previsões (5 minutos de TTL)
        self._prediction_cache = {}
        self._cache_ttl = 300  # 5 minutos
    
    def _log_structured_event(self, event_type: str, data: Dict):
        """Log estruturado em JSON para análise posterior de ML"""
        log_data = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        logger.info(json.dumps(log_data, ensure_ascii=False))
    
    @lru_cache(maxsize=128)
    def _calculate_growth_prediction_cached(self, fg_key: str, total_gb: float, usage_percent: float):
        """Cache de previsões por 5 minutos usando hash da chave"""
        cache_key = md5(f"{fg_key}_{total_gb}_{usage_percent}".encode()).hexdigest()
        
        if cache_key in self._prediction_cache:
            cached_data, timestamp = self._prediction_cache[cache_key]
            if (datetime.now() - timestamp).seconds < self._cache_ttl:
                return cached_data
        
        # Calcular nova previsão
        prediction = self._estimate_daily_growth(total_gb, usage_percent)
        
        # Armazenar no cache
        self._prediction_cache[cache_key] = (prediction, datetime.now())
        
        return prediction
    
    def _estimate_daily_growth_ml(self, historical_data: List[Dict]) -> float:
        """Usa regressão linear simples baseado em histórico"""
        if len(historical_data) < 7:
            return self._estimate_daily_growth(0, 0)  # fallback
        
        try:
            # Importar sklearn apenas quando necessário
            from sklearn.linear_model import LinearRegression
            import numpy as np
            
            # Preparar dados para regressão
            X = np.array([i for i in range(len(historical_data))]).reshape(-1, 1)
            y = np.array([d.get('size_gb', 0) for d in historical_data])
            
            # Treinar modelo
            model = LinearRegression()
            model.fit(X, y)
            
            # Previsão para 1 dia à frente
            daily_growth = abs(model.coef_[0])  # taxa de crescimento diário
            
            # Log do modelo ML
            self._log_structured_event('ml_prediction', {
                'data_points': len(historical_data),
                'coefficient': float(model.coef_[0]),
                'r2_score': float(model.score(X, y)),
                'predicted_growth': float(daily_growth)
            })
            
            return max(daily_growth, 0.1)  # Mínimo de 0.1GB/dia
            
        except ImportError:
            logger.warning("⚠️ [ML] sklearn não disponível, usando heurística")
            return self._estimate_daily_growth(0, 0)
        except Exception as e:
            logger.error(f"❌ [ML] Erro no modelo: {e}")
            return self._estimate_daily_growth(0, 0)
    
    async def analyze_server_alerts(self, server_id: str) -> Dict:
        """Análise completa com dados reais do SQL Server"""
        try:
            logger.info(f"🔮 [PREDICTIVE] Iniciando análise para {server_id}")
            
            # Log estruturado do início da análise
            self._log_structured_event('predictive_analysis_start', {
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            })
            
            # 1. Buscar todos os datafiles REAIS do servidor
            datafiles = await self._get_all_datafiles_real(server_id)
            
            if not datafiles:
                logger.warning(f"⚠️ [PREDICTIVE] Nenhum datafile encontrado para {server_id}")
                return self._empty_result(server_id)
            
            logger.info(f"📊 [PREDICTIVE] {len(datafiles)} datafiles encontrados")
            
            # 2. Agregar por filegroup
            filegroups = self._aggregate_by_filegroup(datafiles, server_id)
            
            logger.info(f"📊 [PREDICTIVE] {len(filegroups)} filegroups únicos")
            
            # 3. Analisar cada filegroup
            alerts = []
            
            for fg_key, fg_analysis in filegroups.items():
                # Analisar apenas DATA filegroups (não LOG)
                if fg_analysis.filegroup_name != 'LOG':
                    fg_alerts = self._analyze_filegroup_aggregated(fg_analysis)
                    alerts.extend(fg_alerts)
            
            logger.info(f"✅ [PREDICTIVE] {len(alerts)} alertas gerados")
            
            # 4. Categorizar e gerar recomendações
            categorized = self._categorize_alerts(alerts)
            recommendations = self._generate_recommendations(categorized)
            health_score = self._calculate_predictive_health(categorized)
            
            # Log estruturado do resultado
            self._log_structured_event('predictive_analysis_complete', {
                'server_id': server_id,
                'filegroups_analyzed': len(filegroups),
                'alerts_generated': len(alerts),
                'health_score': health_score,
                'critical_alerts': len(categorized['critical']),
                'high_alerts': len(categorized['high']),
                'timestamp': datetime.now().isoformat()
            })
            
            # Converter alertas para dict com timestamps como string
            alerts_dict = []
            for alert in alerts:
                alert_dict = asdict(alert)
                if isinstance(alert_dict['timestamp'], datetime):
                    alert_dict['timestamp'] = alert_dict['timestamp'].isoformat()
                alerts_dict.append(alert_dict)
            
            return {
                'server_id': server_id,
                'timestamp': datetime.now().isoformat(),
                'predictive_health_score': health_score,
                'total_alerts': len(alerts),
                'total_filegroups_analyzed': len(filegroups),
                'alerts_by_severity': {
                    'critical': [asdict(a) for a in categorized['critical']],
                    'high': [asdict(a) for a in categorized['high']],
                    'medium': [asdict(a) for a in categorized['medium']],
                    'low': [asdict(a) for a in categorized['low']]
                },
                'alerts_by_type': {
                    'space_critical': [asdict(a) for a in categorized['by_type']['space_critical']],
                    'growth_trend': [asdict(a) for a in categorized['by_type']['growth_trend']],
                    'maxsize_approaching': [asdict(a) for a in categorized['by_type']['maxsize_approaching']],
                    'disk_saturation': [asdict(a) for a in categorized['by_type']['disk_saturation']]
                },
                'alerts': alerts_dict,
                'recommendations': recommendations
            }
            
        except Exception as e:
            logger.error(f"❌ [PREDICTIVE] Erro na análise: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
    
    async def _get_all_datafiles_real(self, server_id: str) -> List[Dict]:
        """
        Busca TODOS os datafiles REAIS de todas as databases do servidor
        COM ESPAÇO EM DISCO DO SISTEMA OPERACIONAL
        """
        try:
            # Query que busca datafiles + espaço em disco
            query = """
            -- Buscar espaço em disco de cada volume
            IF OBJECT_ID('tempdb..#DiskSpace') IS NOT NULL DROP TABLE #DiskSpace;
            
            CREATE TABLE #DiskSpace (
                Drive CHAR(1),
                FreeSpaceMB INT
            );
            
            INSERT INTO #DiskSpace (Drive, FreeSpaceMB)
            EXEC xp_fixeddrives;
            
            -- Buscar todos os datafiles com espaço em disco
            SELECT 
                d.name AS database_name,
                CASE 
                    WHEN df.type = 0 THEN ISNULL(fg.name, 'PRIMARY')
                    WHEN df.type = 1 THEN 'LOG'
                    ELSE 'OTHER'
                END AS filegroup_name,
                df.name AS logical_name,
                df.type_desc AS file_type,
                CAST(df.size * 8.0 / 1024 AS DECIMAL(18,2)) AS size_mb,
                CAST(df.max_size * 8.0 / 1024 AS DECIMAL(18,2)) AS max_size_mb,
                CASE 
                    WHEN df.max_size = -1 THEN 'UNLIMITED'
                    WHEN df.max_size = 268435456 THEN 'UNLIMITED'
                    ELSE CAST(df.max_size * 8.0 / 1024 AS VARCHAR) + ' MB'
                END AS max_size_formatted,
                CAST(
                    CASE 
                        WHEN df.is_percent_growth = 1 THEN CAST(df.growth AS VARCHAR) + '%'
                        ELSE CAST(df.growth * 8.0 / 1024 AS VARCHAR) + ' MB'
                    END AS VARCHAR(50)
                ) AS growth_increment,
                CAST(FILEPROPERTY(df.name, 'SpaceUsed') * 8.0 / 1024 AS DECIMAL(18,2)) AS used_mb,
                CAST((df.size - FILEPROPERTY(df.name, 'SpaceUsed')) * 8.0 / 1024 AS DECIMAL(18,2)) AS free_mb,
                df.physical_name,
                LEFT(df.physical_name, 1) AS volume,
                ISNULL(ds.FreeSpaceMB, 0) AS disk_free_mb
            FROM sys.databases d
            JOIN sys.master_files df ON d.database_id = df.database_id
            LEFT JOIN sys.filegroups fg ON df.data_space_id = fg.data_space_id
            LEFT JOIN #DiskSpace ds ON LEFT(df.physical_name, 1) = ds.Drive
            WHERE d.database_id > 4  -- Ignora system databases
                AND d.state = 0  -- ONLINE
            ORDER BY d.name, df.type, df.name;
            
            DROP TABLE #DiskSpace;
            """
            
            logger.info(f"📡 [PREDICTIVE] Executando query de datafiles para {server_id}")
            
            # Usar o método correto do SQLServerMonitoring
            result = await self.sql_monitoring.execute_query(server_id, query)
            
            if not result['success']:
                logger.error(f"❌ [PREDICTIVE] Erro na query: {result.get('error', 'Erro desconhecido')}")
                return []
            
            # Converter resultado para formato esperado
            # A API retorna: {'success': True, 'rows': [...]}
            rows = result['rows']
            
            # Extrair colunas do primeiro row se disponível
            if rows and len(rows) > 0:
                columns = list(rows[0].keys())
            else:
                logger.warning("⚠️ [PREDICTIVE] Nenhum resultado retornado")
                return []
            
            datafiles = []
            for row in rows:
                # Os rows já vêm como dicionários da API
                df_dict = dict(row)  # Copiar o dicionário
                
                # Converter valores Decimal para float para serialização JSON
                for key, value in df_dict.items():
                    if hasattr(value, '__class__') and 'Decimal' in str(value.__class__):
                        df_dict[key] = float(value)
                
                # Adicionar server_id ao dict
                df_dict['server_id'] = server_id
                datafiles.append(df_dict)
            
            logger.info(f"✅ [PREDICTIVE] {len(datafiles)} datafiles carregados de {server_id}")
            
            if not datafiles:
                logger.error("❌ [PREDICTIVE] CRÍTICO: Nenhum datafile retornado pela query complexa!")
                return []
            
            if datafiles:
                # Log do primeiro datafile para debug
                first_df = datafiles[0]
                logger.info(f"🔍 [PREDICTIVE] Sample datafile: {first_df['database_name']}.{first_df['logical_name']} - {first_df['size_mb']}MB / {first_df['max_size_mb']}MB")
                
                # Log de alguns datafiles para verificar estrutura
                for i, df in enumerate(datafiles[:3]):
                    logger.info(f"📊 [PREDICTIVE] Datafile {i+1}: {df['database_name']}.{df['filegroup_name']}.{df['logical_name']} - {df['file_type']} - {df['size_mb']}MB")
            else:
                logger.warning("⚠️ [PREDICTIVE] Nenhum datafile carregado!")
            
            return datafiles
            
        except Exception as e:
            logger.error(f"❌ [PREDICTIVE] Erro ao buscar datafiles: {e}", exc_info=True)
            return []
    
    def _aggregate_by_filegroup(self, datafiles: List[Dict], server_id: str) -> Dict[str, FileGroupAnalysis]:
        """Agrega múltiplos datafiles no mesmo filegroup COM DADOS REAIS"""
        filegroups = {}
        
        # Agrupar por (database, filegroup)
        grouped = defaultdict(list)
        for df in datafiles:
            key = (df['database_name'], df['filegroup_name'] or 'LOG')
            grouped[key].append(df)
        
        logger.info(f"📊 [PREDICTIVE] Agregando {len(grouped)} filegroups")
        
        # Log dos filegroups encontrados
        for (db_name, fg_name), files in grouped.items():
            logger.info(f"📁 [PREDICTIVE] Filegroup: {db_name}.{fg_name} - {len(files)} files")
            
            # Log detalhado do primeiro filegroup para debug
            if (db_name, fg_name) == list(grouped.keys())[0]:
                logger.info(f"🔍 [PREDICTIVE] DEBUG - Primeiro filegroup: {db_name}.{fg_name}")
                for i, f in enumerate(files[:3]):  # Primeiros 3 files
                    logger.info(f"  📄 File {i+1}: {f['logical_name']} - {f['file_type']} - {f['size_mb']}MB")
            
            try:
                # Calcular totais agregados
                total_size_mb = sum(to_float(f['size_mb']) for f in files)
                total_used_mb = sum(to_float(f['used_mb']) for f in files)
                total_free_mb = total_size_mb - total_used_mb
                
                # MAXSIZE agregado
                total_maxsize_mb = 0
                has_unlimited = False
                datafiles_at_limit = 0
                datafiles_with_space = 0
                
                # Espaço em disco (pegar do primeiro file, pois é por volume)
                disk_free_mb = to_float(files[0].get('disk_free_mb', 0))
                
                for f in files:
                    max_mb = to_float(f['max_size_mb'])
                    size_mb = to_float(f['size_mb'])
                    
                    if max_mb >= 999999 or f['max_size_formatted'] == 'UNLIMITED':
                        has_unlimited = True
                        total_maxsize_mb = 999999999
                    else:
                        total_maxsize_mb += max_mb
                        
                        # Verificar se file está no limite (99% do MAXSIZE)
                        if size_mb >= max_mb * 0.99:
                            datafiles_at_limit += 1
                        else:
                            datafiles_with_space += 1
                
                # Capacidade disponível
                if has_unlimited:
                    available_growth_gb = 999999.0
                else:
                    available_growth_gb = (total_maxsize_mb - total_size_mb) / 1024
                
                disk_available_gb = disk_free_mb / 1024
                
                # Métricas
                usage_percent = (total_used_mb / total_size_mb * 100) if total_size_mb > 0 else 0
                
                if has_unlimited:
                    maxsize_utilization = 0.0
                else:
                    maxsize_utilization = (total_size_mb / total_maxsize_mb * 100) if total_maxsize_mb > 0 else 0
                
                # Estimar crescimento (usando cache)
                fg_key = f"{db_name}_{fg_name}"
                growth_per_day_gb = self._calculate_growth_prediction_cached(
                    fg_key,
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
                    if total_size_mb >= total_maxsize_mb * 0.95:
                        has_overflow_risk = True
                        risk_type = 'MAXSIZE'
                
                if disk_available_gb < 50 and days_until_full <= 30:
                    has_overflow_risk = True
                    risk_type = 'DISK'
                
                # Criar análise agregada
                fg_key = f"{db_name}_{fg_name}"
                logger.info(f"📊 [PREDICTIVE] Criando análise para {fg_key}: {total_size_mb:.1f}MB, {total_used_mb:.1f}MB usado")
                
                filegroups[fg_key] = FileGroupAnalysis(
                    server_id=server_id,
                    database_name=db_name,
                    filegroup_name=fg_name,
                    total_datafiles=len(files),
                    total_size_gb=round(total_size_mb / 1024, 2),
                    total_used_gb=round(total_used_mb / 1024, 2),
                    total_free_gb=round(total_free_mb / 1024, 2),
                    total_maxsize_gb=round(total_maxsize_mb / 1024, 2),
                    datafiles_at_limit=datafiles_at_limit,
                    datafiles_with_space=datafiles_with_space,
                    available_growth_gb=round(available_growth_gb, 2),
                    disk_available_gb=round(disk_available_gb, 2),
                    usage_percent=round(usage_percent, 2),
                    maxsize_utilization_percent=round(maxsize_utilization, 2),
                    estimated_growth_per_day_gb=round(growth_per_day_gb, 3),
                    days_until_filegroup_full=days_until_full,
                    predicted_usage_30d_percent=round(predicted_30d, 2),
                    has_overflow_risk=has_overflow_risk,
                    risk_type=risk_type,
                    limiting_factor=limiting_factor
                )
                
                logger.debug(f"📊 [PREDICTIVE] {db_name}.{fg_name}: {len(files)} files, {datafiles_at_limit} no limite, {available_growth_gb:.1f}GB disponível")
                
            except Exception as e:
                logger.error(f"❌ [PREDICTIVE] Erro ao agregar {db_name}.{fg_name}: {e}", exc_info=True)
                continue
        
        return filegroups
    
    def _analyze_filegroup_aggregated(self, fg: FileGroupAnalysis) -> List[PredictiveAlert]:
        """Analisa filegroup AGREGADO e gera alertas"""
        alerts = []
        
        try:
            # ALERTA 1: SPACE_CRITICAL
            if fg.usage_percent >= self.thresholds['critical_usage']:
                severity = 'CRITICAL'
                recommendation = (
                    f"🔴 URGENTE: {fg.database_name}.{fg.filegroup_name} com {fg.usage_percent:.1f}% usado. "
                    f"{fg.datafiles_at_limit}/{fg.total_datafiles} datafiles no limite. "
                    f"Expandir {fg.total_free_gb * 0.5:.0f}GB ou adicionar novo datafile."
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
                    f"🟡 Monitorar: {fg.database_name}.{fg.filegroup_name} em {fg.usage_percent:.1f}% de uso."
                )
            else:
                severity = None
            
            if severity:
                # Calcular score de confiança baseado na severidade e dados disponíveis
                confidence_score = 0.9 if severity == 'CRITICAL' else 0.8 if severity == 'HIGH' else 0.7
                
                alerts.append(PredictiveAlert(
                    server_id=fg.server_id,
                    database_name=fg.database_name,
                    filegroup_name=fg.filegroup_name,
                    alert_type='SPACE_CRITICAL',
                    severity=severity,
                    total_datafiles=fg.total_datafiles,
                    datafiles_at_limit=fg.datafiles_at_limit,
                    datafiles_with_space=fg.datafiles_with_space,
                    current_usage_percent=fg.usage_percent,
                    predicted_usage_percent=fg.predicted_usage_30d_percent,
                    days_until_full=fg.days_until_filegroup_full,
                    current_free_gb=fg.total_free_gb,
                    available_growth_gb=fg.available_growth_gb,
                    estimated_growth_per_day_gb=fg.estimated_growth_per_day_gb,
                    total_size_gb=fg.total_size_gb,
                    total_maxsize_gb=fg.total_maxsize_gb,
                    disk_available_gb=fg.disk_available_gb,
                    risk_type=fg.risk_type,
                    recommendation=recommendation,
                    timestamp=datetime.now().isoformat(),
                    confidence_score=confidence_score,
                    prediction_method='heuristic',
                    historical_data_points=0
                ))
            
            # ALERTA 2: GROWTH_TREND
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
                    current_usage_percent=fg.usage_percent,
                    predicted_usage_percent=100.0,
                    days_until_full=fg.days_until_filegroup_full,
                    current_free_gb=fg.total_free_gb,
                    available_growth_gb=fg.available_growth_gb,
                    estimated_growth_per_day_gb=fg.estimated_growth_per_day_gb,
                    total_size_gb=fg.total_size_gb,
                    total_maxsize_gb=fg.total_maxsize_gb,
                    disk_available_gb=fg.disk_available_gb,
                    risk_type=fg.risk_type,
                    recommendation=(
                        f"⚡ CRESCIMENTO ACELERADO: {fg.database_name}.{fg.filegroup_name} "
                        f"ficará cheio em {fg.days_until_filegroup_full} dias. "
                        f"Taxa: {fg.estimated_growth_per_day_gb:.2f}GB/dia. Ação imediata!"
                    ),
                    timestamp=datetime.now().isoformat(),
                    confidence_score=0.85,  # Alta confiança em tendências
                    prediction_method='heuristic',
                    historical_data_points=0
                ))
            
            # ALERTA 3: MAXSIZE_APPROACHING
            if fg.total_maxsize_gb < 999999:
                if fg.maxsize_utilization_percent >= 95:
                    severity = 'CRITICAL'
                elif fg.maxsize_utilization_percent >= 85:
                    severity = 'HIGH'
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
                        current_usage_percent=fg.maxsize_utilization_percent,
                        predicted_usage_percent=100.0,
                        days_until_full=fg.days_until_filegroup_full,
                        current_free_gb=fg.available_growth_gb,
                        available_growth_gb=fg.available_growth_gb,
                        estimated_growth_per_day_gb=fg.estimated_growth_per_day_gb,
                        total_size_gb=fg.total_size_gb,
                        total_maxsize_gb=fg.total_maxsize_gb,
                        disk_available_gb=fg.disk_available_gb,
                        risk_type='MAXSIZE',
                        recommendation=(
                            f"🚨 MAXSIZE: {fg.database_name}.{fg.filegroup_name} em "
                            f"{fg.maxsize_utilization_percent:.1f}% do MAXSIZE agregado. "
                            f"Aumentar limite ou adicionar datafile!"
                        ),
                        timestamp=datetime.now().isoformat(),
                        confidence_score=0.95,  # Muito alta confiança em MAXSIZE
                        prediction_method='heuristic',
                        historical_data_points=0
                    ))
            
            # ALERTA 4: DISK_SATURATION
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
                        current_usage_percent=fg.usage_percent,
                        predicted_usage_percent=fg.predicted_usage_30d_percent,
                        days_until_full=days_until_disk_full,
                        current_free_gb=fg.total_free_gb,
                        available_growth_gb=fg.available_growth_gb,
                        estimated_growth_per_day_gb=fg.estimated_growth_per_day_gb,
                        total_size_gb=fg.total_size_gb,
                        total_maxsize_gb=fg.total_maxsize_gb,
                        disk_available_gb=fg.disk_available_gb,
                        risk_type='DISK',
                        recommendation=(
                            f"💾 DISCO SATURANDO: {fg.disk_available_gb:.1f}GB livres. "
                            f"Disco cheio em ~{days_until_disk_full} dias. Expandir storage!"
                        ),
                        timestamp=datetime.now().isoformat(),
                        confidence_score=0.9,  # Alta confiança em dados de disco
                        prediction_method='heuristic',
                        historical_data_points=0
                    ))
            
        except Exception as e:
            logger.error(f"❌ [PREDICTIVE] Erro ao analisar {fg.database_name}.{fg.filegroup_name}: {e}", exc_info=True)
        
        return alerts
    
    def _estimate_daily_growth(self, total_gb: float, usage_percent: float) -> float:
        """Estima crescimento diário"""
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
        """Categoriza alertas"""
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
        """Gera recomendações"""
        recommendations = []
        
        critical_count = len(categorized['critical'])
        high_count = len(categorized['high'])
        
        if critical_count > 0:
            recommendations.append(
                f"🔴 AÇÃO IMEDIATA: {critical_count} filegroups críticos (próximas 24-48h)"
            )
        
        if high_count > 0:
            recommendations.append(
                f"🟠 ATENÇÃO: {high_count} filegroups precisam de ação (próximos 7 dias)"
            )
        
        if not recommendations:
            recommendations.append("✅ Sistema saudável. Nenhum alerta crítico.")
        
        return recommendations
    
    def _calculate_predictive_health(self, categorized: Dict) -> float:
        """Calcula health score"""
        base_score = 100.0
        
        critical_penalty = len(categorized['critical']) * 15
        high_penalty = len(categorized['high']) * 8
        medium_penalty = len(categorized['medium']) * 3
        
        score = max(0.0, base_score - (critical_penalty + high_penalty + medium_penalty))
        
        return round(score, 1)
    
    def _empty_result(self, server_id: str) -> Dict:
        """Resultado vazio"""
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
