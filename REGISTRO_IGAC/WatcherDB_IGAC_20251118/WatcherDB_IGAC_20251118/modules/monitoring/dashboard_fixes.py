# ============================================================================
# WatcherDB DASHBOARD FIXES - CORREÇÕES PARA EXIBIÇÃO
# ============================================================================
# Arquivo: modules/monitoring/dashboard_fixes.py
# ============================================================================

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from decimal import Decimal
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class FileGroupDisplay:
    """Estrutura para exibição correta de filegroups no dashboard"""
    database_name: str
    filegroup_name: str
    filegroup_type: str  # 'DATA' ou 'LOG'
    
    # Métricas agregadas do filegroup
    total_size_gb: float
    used_size_gb: float
    free_size_gb: float
    max_size_gb: float
    
    # Percentuais
    usage_percent: float
    maxsize_utilization_percent: float
    
    # Análise de risco
    is_overflow: bool
    days_until_full: int
    growth_rate_per_month: float
    
    # Informações do volume
    volume: str
    disk_available_gb: float
    
    # Status
    alert_level: str  # 'OK', 'WARNING', 'CRITICAL', 'OVERFLOW'
    risk_factors: List[str]
    
    # Metadados
    file_count: int
    logical_names: List[str]  # Lista de logical names para referência

class DashboardFixes:
    """Correções para o dashboard - Filegroups corretos e ordenação"""
    
    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
    
    async def get_corrected_filegroups(self, server_id: str) -> List[FileGroupDisplay]:
        """Retorna filegroups corrigidos para exibição no dashboard"""
        try:
            logger.info(f"🔧 [DASHBOARD] Corrigindo exibição de filegroups para {server_id}")
            
            # 1. Buscar dados reais de filegroups
            filegroups_data = await self._get_filegroups_real_data(server_id)
            
            if not filegroups_data:
                logger.warning(f"⚠️ [DASHBOARD] Nenhum filegroup encontrado para {server_id}")
                return []
            
            # 2. Processar e corrigir dados
            corrected_filegroups = []
            
            for fg_data in filegroups_data:
                corrected_fg = self._process_filegroup_data(fg_data)
                corrected_filegroups.append(corrected_fg)
            
            # 3. ORDENAR: Overflows por último
            corrected_filegroups = self._sort_filegroups_correctly(corrected_filegroups)
            
            logger.info(f"✅ [DASHBOARD] {len(corrected_filegroups)} filegroups corrigidos")
            
            return corrected_filegroups
            
        except Exception as e:
            logger.error(f"❌ [DASHBOARD] Erro ao corrigir filegroups: {e}", exc_info=True)
            return []
    
    async def _get_filegroups_real_data(self, server_id: str) -> List[Dict]:
        """Busca dados reais de filegroups com agregação correta"""
        query = """
        -- Query para obter filegroups reais com agregação correta
        WITH FileGroupData AS (
            SELECT 
                d.name AS database_name,
                CASE 
                    WHEN mf.type = 1 THEN 'LOG'
                    ELSE ISNULL(fg.name, 'PRIMARY')
                END AS filegroup_name,
                CASE 
                    WHEN mf.type = 1 THEN 'LOG'
                    ELSE 'DATA'
                END AS filegroup_type,
                mf.name AS logical_name,
                mf.size * 8.0 / 1024 AS size_mb,
                CASE 
                    WHEN mf.max_size = -1 THEN 999999999
                    WHEN mf.max_size = 268435456 THEN 2097152
                    ELSE mf.max_size * 8.0 / 1024
                END AS max_size_mb,
                CAST(FILEPROPERTY(mf.name, 'SpaceUsed') * 8.0 / 1024 AS DECIMAL(18,2)) AS used_mb,
                LEFT(mf.physical_name, 1) AS volume,
                vs.available_bytes / 1024.0 / 1024.0 / 1024.0 AS disk_available_gb
            FROM sys.databases d
            JOIN sys.master_files mf ON d.database_id = mf.database_id
            LEFT JOIN sys.filegroups fg ON mf.data_space_id = fg.data_space_id
            CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
            WHERE d.database_id > 4
              AND d.state = 0
              AND mf.state = 0
        )
        SELECT 
            database_name,
            filegroup_name,
            filegroup_type,
            COUNT(*) AS file_count,
            -- Filegroup name (não concatenar logical names)
            filegroup_name AS logical_names,
            -- Métricas agregadas
            CAST(SUM(size_mb) AS DECIMAL(18,2)) AS total_size_mb,
            CAST(SUM(used_mb) AS DECIMAL(18,2)) AS total_used_mb,
            CAST(SUM(max_size_mb) AS DECIMAL(18,2)) AS total_max_size_mb,
            -- Volume e disco
            volume,
            CAST(AVG(disk_available_gb) AS DECIMAL(18,2)) AS disk_available_gb
        FROM FileGroupData fgd
        GROUP BY database_name, filegroup_name, filegroup_type, volume
        ORDER BY database_name, filegroup_name
        """
        
        try:
            result = await self.sql_monitoring.execute_query(server_id, query)
            
            if not result or not result.get('success'):
                logger.error(f"❌ [DASHBOARD] Erro na query: {result.get('error', 'Erro desconhecido')}")
                return []
            
            rows = result.get('rows', [])
            logger.info(f"📊 [DASHBOARD] {len(rows)} filegroups encontrados")
            
            return rows
            
        except Exception as e:
            logger.error(f"❌ [DASHBOARD] Erro ao buscar filegroups: {e}", exc_info=True)
            return []
    
    def _process_filegroup_data(self, fg_data: Dict) -> FileGroupDisplay:
        """Processa dados de um filegroup para exibição correta"""
        # Converter valores com tratamento de None
        def safe_float(value, default=0):
            if value is None or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        total_size_mb = safe_float(fg_data.get('total_size_mb', 0))
        total_used_mb = safe_float(fg_data.get('total_used_mb', 0))
        total_max_size_mb = safe_float(fg_data.get('total_max_size_mb', 0))
        disk_available_gb = safe_float(fg_data.get('disk_available_gb', 0))
        
        # Calcular métricas básicas
        total_size_gb = total_size_mb / 1024
        used_size_gb = total_used_mb / 1024
        free_size_gb = total_size_gb - used_size_gb
        
        # MAXSIZE TOTAL = soma de todos os maxsizes dos datafiles do filegroup
        max_size_gb = total_max_size_mb / 1024
        
        # ESPAÇO LIVRE TOTAL = soma do espaço livre de todos os discos usados pelo filegroup
        # Para isso, precisamos buscar os volumes únicos usados por este filegroup
        volume_paths = fg_data.get('volume_paths', '')
        if volume_paths:
            # Se temos os paths dos volumes, calcular espaço livre total
            # Por enquanto, usar o disk_available_gb que já vem do banco
            total_disk_free_gb = disk_available_gb
        else:
            # Fallback: usar o espaço disponível do disco principal
            total_disk_free_gb = disk_available_gb
        
        # Percentuais
        usage_percent = (used_size_gb / total_size_gb * 100) if total_size_gb > 0 else 0
        maxsize_utilization_percent = (total_size_gb / max_size_gb * 100) if max_size_gb > 0 else 0
        
        # Análise de risco
        # Determinar se está em overflow: soma dos maxsizes > espaço livre total dos discos
        # MAXSIZE TOTAL = soma de todos os maxsizes dos datafiles do filegroup
        total_maxsize_gb = max_size_gb  # Já é a soma dos maxsizes
        
        # ESPAÇO LIVRE TOTAL = soma do espaço livre de todos os discos usados pelo filegroup
        total_disk_free_gb = total_disk_free_gb  # Já calculado acima
        
        # Verificar se soma dos maxsizes > espaço livre total
        is_overflow = total_maxsize_gb > total_disk_free_gb
        
        # Calcular dias até ficar cheio (estimativa simples)
        if usage_percent > 0 and usage_percent < 100:
            growth_rate_per_month = 2.0  # Estimativa conservadora
            days_until_full = int((100 - usage_percent) / (growth_rate_per_month / 30))
        else:
            growth_rate_per_month = 0.0
            days_until_full = 0 if is_overflow else 999
        
        # Determinar nível de alerta
        if is_overflow:
            alert_level = 'OVERFLOW'
            risk_factors = ['Espaço esgotado']
        elif usage_percent >= 90:
            alert_level = 'CRITICAL'
            risk_factors = ['Uso crítico']
        elif usage_percent >= 80:
            alert_level = 'WARNING'
            risk_factors = ['Uso alto']
        else:
            alert_level = 'OK'
            risk_factors = []
        
        # Usar apenas o filegroup_name (não concatenar logical names)
        logical_names = [fg_data.get('filegroup_name', '')]
        
        return FileGroupDisplay(
            database_name=fg_data.get('database_name', ''),
            filegroup_name=fg_data.get('filegroup_name', ''),
            filegroup_type=fg_data.get('filegroup_type', ''),
            total_size_gb=round(total_size_gb, 2),
            used_size_gb=round(used_size_gb, 2),
            free_size_gb=round(free_size_gb, 2),
            max_size_gb=round(max_size_gb, 2),  # MAXSIZE TOTAL
            usage_percent=round(usage_percent, 1),
            maxsize_utilization_percent=round(maxsize_utilization_percent, 1),
            is_overflow=is_overflow,
            days_until_full=days_until_full,
            growth_rate_per_month=growth_rate_per_month,
            volume=fg_data.get('volume', ''),
            disk_available_gb=round(total_disk_free_gb, 2),  # ESPAÇO LIVRE TOTAL
            alert_level=alert_level,
            risk_factors=risk_factors,
            file_count=int(fg_data.get('file_count', 0)),
            logical_names=logical_names
        )
    
    def _sort_filegroups_correctly(self, filegroups: List[FileGroupDisplay]) -> List[FileGroupDisplay]:
        """Ordena filegroups corretamente: overflows por último"""
        
        def sort_key(fg: FileGroupDisplay) -> tuple:
            # Prioridade de ordenação:
            # 1. Não-overflow primeiro (is_overflow = False)
            # 2. Por alert_level (OK < WARNING < CRITICAL < OVERFLOW)
            # 3. Por usage_percent (menor primeiro)
            # 4. Por database_name (alfabético)
            # 5. Por filegroup_name (alfabético)
            
            overflow_priority = 1 if fg.is_overflow else 0
            
            alert_priority = {
                'OK': 0,
                'WARNING': 1,
                'CRITICAL': 2,
                'OVERFLOW': 3
            }.get(fg.alert_level, 4)
            
            return (
                overflow_priority,  # Overflows por último
                alert_priority,    # Por severidade
                -fg.usage_percent, # Maior uso primeiro (dentro da mesma severidade)
                fg.database_name,  # Alfabético por database
                fg.filegroup_name  # Alfabético por filegroup
            )
        
        sorted_filegroups = sorted(filegroups, key=sort_key)
        
        # Log da ordenação
        overflow_count = sum(1 for fg in sorted_filegroups if fg.is_overflow)
        logger.info(f"📊 [DASHBOARD] Ordenação: {len(sorted_filegroups)} filegroups, {overflow_count} overflows por último")
        
        return sorted_filegroups
    
    async def get_dashboard_summary(self, server_id: str) -> Dict:
        """Retorna resumo do dashboard com estatísticas corretas"""
        try:
            filegroups = await self.get_corrected_filegroups(server_id)
            
            if not filegroups:
                return {
                    'server_id': server_id,
                    'total_filegroups': 0,
                    'overflow_count': 0,
                    'critical_count': 0,
                    'warning_count': 0,
                    'ok_count': 0,
                    'total_size_gb': 0,
                    'total_used_gb': 0,
                    'average_usage_percent': 0
                }
            
            # Calcular estatísticas
            total_filegroups = len(filegroups)
            overflow_count = sum(1 for fg in filegroups if fg.is_overflow)
            critical_count = sum(1 for fg in filegroups if fg.alert_level == 'CRITICAL')
            warning_count = sum(1 for fg in filegroups if fg.alert_level == 'WARNING')
            ok_count = sum(1 for fg in filegroups if fg.alert_level == 'OK')
            
            total_size_gb = sum(fg.total_size_gb for fg in filegroups)
            total_used_gb = sum(fg.used_size_gb for fg in filegroups)
            average_usage_percent = (total_used_gb / total_size_gb * 100) if total_size_gb > 0 else 0
            
            return {
                'server_id': server_id,
                'total_filegroups': total_filegroups,
                'overflow_count': overflow_count,
                'critical_count': critical_count,
                'warning_count': warning_count,
                'ok_count': ok_count,
                'total_size_gb': round(total_size_gb, 2),
                'total_used_gb': round(total_used_gb, 2),
                'average_usage_percent': round(average_usage_percent, 1),
                'filegroups': [asdict(fg) for fg in filegroups]
            }
            
        except Exception as e:
            logger.error(f"❌ [DASHBOARD] Erro no resumo: {e}", exc_info=True)
            return {
                'server_id': server_id,
                'error': str(e),
                'total_filegroups': 0
            }

# Exemplo de uso
async def example_usage():
    """Exemplo de como usar as correções do dashboard"""
    from modules.monitoring.monitoring import SQLServerMonitoring
    
    # Configurar monitoring
    sql_monitoring = SQLServerMonitoring()
    
    # Criar instância das correções
    dashboard_fixes = DashboardFixes(sql_monitoring)
    
    # Obter filegroups corrigidos
    server_id = "SQLIDSPRD03_I01"
    filegroups = await dashboard_fixes.get_corrected_filegroups(server_id)
    
    print(f"📊 Filegroups corrigidos: {len(filegroups)}")
    
    # Mostrar primeiros 5 filegroups
    for i, fg in enumerate(filegroups[:5]):
        print(f"  {i+1}. {fg.database_name}.{fg.filegroup_name} - {fg.usage_percent:.1f}% usado - {fg.alert_level}")
    
    # Obter resumo
    summary = await dashboard_fixes.get_dashboard_summary(server_id)
    print(f"\n📈 Resumo:")
    print(f"  Total: {summary['total_filegroups']}")
    print(f"  Overflows: {summary['overflow_count']}")
    print(f"  Críticos: {summary['critical_count']}")
    print(f"  Avisos: {summary['warning_count']}")
    print(f"  OK: {summary['ok_count']}")

if __name__ == "__main__":
    asyncio.run(example_usage())
