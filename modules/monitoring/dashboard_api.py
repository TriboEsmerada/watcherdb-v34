# ============================================================================
# WatcherDB DASHBOARD API - ENDPOINTS CORRIGIDOS
# ============================================================================
# Arquivo: modules/monitoring/dashboard_api.py
# ============================================================================

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .dashboard_fixes import DashboardFixes
from .monitoring import SQLServerMonitoring
from .backup_analysis import BackupAnalysisEngine

logger = logging.getLogger(__name__)

# Router para endpoints do dashboard
router = APIRouter()

# Instância global do monitoring (será inicializada quando necessário)
sql_monitoring = None
backup_engine = None

def get_sql_monitoring():
    """Obtém ou cria instância do SQLServerMonitoring"""
    global sql_monitoring, backup_engine
    if sql_monitoring is None:
        cache_path = "watcherdb_cache.db"
        sql_monitoring = SQLServerMonitoring(cache_path)
        backup_engine = BackupAnalysisEngine(sql_monitoring)
    return sql_monitoring

def get_backup_engine():
    """Obtém ou cria instância do BackupAnalysisEngine"""
    get_sql_monitoring()  # Garante que sql_monitoring está inicializado
    return backup_engine

@router.get("/api/monitoring/space/server/{server_id}/dashboard")
async def get_dashboard_data(server_id: str):
    """Endpoint corrigido para dados do dashboard"""
    try:
        logger.info(f"📊 [DASHBOARD] Buscando dados para {server_id}")
        
        # Criar instância das correções
        monitoring = get_sql_monitoring()
        dashboard_fixes = DashboardFixes(monitoring)
        
        # Obter dados corrigidos
        summary = await dashboard_fixes.get_dashboard_summary(server_id)
        
        if 'error' in summary:
            raise HTTPException(status_code=500, detail=summary['error'])
        
        # Estruturar resposta
        response = {
            'success': True,
            'server_id': server_id,
            'timestamp': datetime.now().isoformat(),
            'data': {
                'summary': {
                    'total_filegroups': summary['total_filegroups'],
                    'overflow_count': summary['overflow_count'],
                    'critical_count': summary['critical_count'],
                    'warning_count': summary['warning_count'],
                    'ok_count': summary['ok_count'],
                    'total_size_gb': summary['total_size_gb'],
                    'total_used_gb': summary['total_used_gb'],
                    'average_usage_percent': summary['average_usage_percent']
                },
                'filegroups': summary['filegroups']
            }
        }
        
        logger.info(f"✅ [DASHBOARD] {summary['total_filegroups']} filegroups retornados")
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"❌ [DASHBOARD] Erro no endpoint: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
        )

@router.get("/api/monitoring/backup/server/{server_id}/summary")
async def get_backup_summary(server_id: str, days: int = 7, include_system: bool = False):
    """Resumo de backups por database (FULL/DIFF/LOG)."""
    try:
        engine = get_backup_engine()
        result = await engine.analyze_server_backups(
            server_id, lookback_days=days, include_system_databases=include_system
        )
        status_code = 200 if result.get('success') else 500
        return JSONResponse(status_code=status_code, content=result)
    except Exception as e:
        logger.error(f"❌ [BACKUP] Erro no summary: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

@router.get("/api/monitoring/backup/server/{server_id}/issues")
async def get_backup_issues(server_id: str, days: int = 7, include_system: bool = False):
    """Filtra apenas bases com issues identificadas."""
    try:
        engine = get_backup_engine()
        result = await engine.analyze_server_backups(
            server_id, lookback_days=days, include_system_databases=include_system
        )
        if not result.get('success'):
            return JSONResponse(status_code=500, content=result)
        items = result.get('items', [])
        issues = [i for i in items if i.get('issues')]
        return JSONResponse(content={
            'success': True,
            'server_id': server_id,
            'total_databases': result.get('total_databases', 0),
            'databases_with_issues': len(issues),
            'items': issues
        })
    except Exception as e:
        logger.error(f"❌ [BACKUP] Erro no issues: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

@router.get("/api/monitoring/space/server/{server_id}/dashboard/filegroups")
async def get_dashboard_filegroups(server_id: str):
    """Endpoint específico para filegroups do dashboard"""
    try:
        logger.info(f"📊 [DASHBOARD] Buscando filegroups para {server_id}")
        
        # Criar instância das correções
        monitoring = get_sql_monitoring()
        dashboard_fixes = DashboardFixes(monitoring)
        
        # Obter filegroups corrigidos
        filegroups = await dashboard_fixes.get_corrected_filegroups(server_id)
        
        if not filegroups:
            return JSONResponse(content={
                'success': True,
                'server_id': server_id,
                'filegroups': [],
                'total_count': 0,
                'timestamp': datetime.now().isoformat()
            })
        
        # Converter para dict
        filegroups_dict = []
        for fg in filegroups:
            fg_dict = {
                'database_name': fg.database_name,
                'filegroup_name': fg.filegroup_name,
                'filegroup_type': fg.filegroup_type,
                'total_size_gb': fg.total_size_gb,
                'used_size_gb': fg.used_size_gb,
                'free_size_gb': fg.free_size_gb,
                'max_size_gb': fg.max_size_gb,
                'usage_percent': fg.usage_percent,
                'maxsize_utilization_percent': fg.maxsize_utilization_percent,
                'is_overflow': fg.is_overflow,
                'days_until_full': fg.days_until_full,
                'growth_rate_per_month': fg.growth_rate_per_month,
                'volume': fg.volume,
                'disk_available_gb': fg.disk_available_gb,
                'alert_level': fg.alert_level,
                'risk_factors': fg.risk_factors,
                'file_count': fg.file_count,
                'logical_names': fg.logical_names
            }
            filegroups_dict.append(fg_dict)
        
        response = {
            'success': True,
            'server_id': server_id,
            'filegroups': filegroups_dict,
            'total_count': len(filegroups_dict),
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"✅ [DASHBOARD] {len(filegroups_dict)} filegroups retornados")
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"❌ [DASHBOARD] Erro no endpoint filegroups: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
        )

@router.get("/api/monitoring/space/server/{server_id}/dashboard/overflow")
async def get_overflow_filegroups(server_id: str):
    """Endpoint específico para filegroups em overflow"""
    try:
        logger.info(f"🚨 [DASHBOARD] Buscando overflows para {server_id}")
        
        # Criar instância das correções
        monitoring = get_sql_monitoring()
        dashboard_fixes = DashboardFixes(monitoring)
        
        # Obter todos os filegroups
        all_filegroups = await dashboard_fixes.get_corrected_filegroups(server_id)
        
        # Filtrar apenas overflows
        overflow_filegroups = [fg for fg in all_filegroups if fg.is_overflow]
        
        # Converter para dict
        overflow_dict = []
        for fg in overflow_filegroups:
            fg_dict = {
                'database_name': fg.database_name,
                'filegroup_name': fg.filegroup_name,
                'filegroup_type': fg.filegroup_type,
                'total_size_gb': fg.total_size_gb,
                'used_size_gb': fg.used_size_gb,
                'free_size_gb': fg.free_size_gb,
                'max_size_gb': fg.max_size_gb,
                'usage_percent': fg.usage_percent,
                'maxsize_utilization_percent': fg.maxsize_utilization_percent,
                'is_overflow': fg.is_overflow,
                'days_until_full': fg.days_until_full,
                'volume': fg.volume,
                'disk_available_gb': fg.disk_available_gb,
                'alert_level': fg.alert_level,
                'risk_factors': fg.risk_factors,
                'file_count': fg.file_count,
                'logical_names': fg.logical_names
            }
            overflow_dict.append(fg_dict)
        
        response = {
            'success': True,
            'server_id': server_id,
            'overflow_filegroups': overflow_dict,
            'overflow_count': len(overflow_dict),
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"🚨 [DASHBOARD] {len(overflow_dict)} overflows encontrados")
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"❌ [DASHBOARD] Erro no endpoint overflow: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
        )

@router.get("/api/monitoring/space/server/{server_id}/dashboard/health")
async def get_dashboard_health(server_id: str):
    """Endpoint para health score do dashboard"""
    try:
        logger.info(f"💚 [DASHBOARD] Calculando health para {server_id}")
        
        # Criar instância das correções
        monitoring = get_sql_monitoring()
        dashboard_fixes = DashboardFixes(monitoring)
        
        # Obter resumo
        summary = await dashboard_fixes.get_dashboard_summary(server_id)
        
        if 'error' in summary:
            raise HTTPException(status_code=500, detail=summary['error'])
        
        # Calcular health score
        total_filegroups = summary['total_filegroups']
        overflow_count = summary['overflow_count']
        critical_count = summary['critical_count']
        warning_count = summary['warning_count']
        
        # Fórmula de health score
        base_score = 100.0
        overflow_penalty = overflow_count * 25  # -25 pontos por overflow
        critical_penalty = critical_count * 15  # -15 pontos por crítico
        warning_penalty = warning_count * 5   # -5 pontos por aviso
        
        health_score = max(0.0, base_score - overflow_penalty - critical_penalty - warning_penalty)
        
        # Determinar status
        if health_score >= 90:
            status = 'EXCELLENT'
            status_color = '#10b981'  # Verde
        elif health_score >= 70:
            status = 'GOOD'
            status_color = '#3b82f6'  # Azul
        elif health_score >= 50:
            status = 'WARNING'
            status_color = '#f59e0b'  # Amarelo
        elif health_score >= 25:
            status = 'CRITICAL'
            status_color = '#ef4444'  # Vermelho
        else:
            status = 'DANGER'
            status_color = '#dc2626'  # Vermelho escuro
        
        response = {
            'success': True,
            'server_id': server_id,
            'health_score': round(health_score, 1),
            'status': status,
            'status_color': status_color,
            'metrics': {
                'total_filegroups': total_filegroups,
                'overflow_count': overflow_count,
                'critical_count': critical_count,
                'warning_count': warning_count,
                'ok_count': summary['ok_count']
            },
            'recommendations': _generate_health_recommendations(overflow_count, critical_count, warning_count),
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"💚 [DASHBOARD] Health score: {health_score:.1f} ({status})")
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"❌ [DASHBOARD] Erro no endpoint health: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
        )

def _generate_health_recommendations(overflow_count: int, critical_count: int, warning_count: int) -> List[str]:
    """Gera recomendações baseadas no health score"""
    recommendations = []
    
    if overflow_count > 0:
        recommendations.append(f"🚨 URGENTE: {overflow_count} filegroup(s) em overflow - Ação imediata necessária!")
    
    if critical_count > 0:
        recommendations.append(f"🔴 CRÍTICO: {critical_count} filegroup(s) crítico(s) - Planejar expansão em 24-48h")
    
    if warning_count > 0:
        recommendations.append(f"🟡 ATENÇÃO: {warning_count} filegroup(s) com aviso - Monitorar próximos 7 dias")
    
    if overflow_count == 0 and critical_count == 0 and warning_count == 0:
        recommendations.append("✅ Sistema saudável - Nenhuma ação imediata necessária")
    
    return recommendations

# Exemplo de uso
async def example_usage():
    """Exemplo de como usar os endpoints corrigidos"""
    from fastapi import FastAPI
    
    app = FastAPI()
    app.include_router(router)
    
    print("🚀 Endpoints corrigidos disponíveis:")
    print("  GET /api/monitoring/space/server/{server_id}/dashboard")
    print("  GET /api/monitoring/space/server/{server_id}/dashboard/filegroups")
    print("  GET /api/monitoring/space/server/{server_id}/dashboard/overflow")
    print("  GET /api/monitoring/space/server/{server_id}/dashboard/health")
    
    print("\n📊 Melhorias implementadas:")
    print("  ✅ Exibe filegroups em vez de logical names")
    print("  ✅ Overflows ordenados por último")
    print("  ✅ Agregação correta por filegroup")
    print("  ✅ Health score baseado em métricas reais")
    print("  ✅ Endpoints específicos para diferentes visualizações")

if __name__ == "__main__":
    asyncio.run(example_usage())
