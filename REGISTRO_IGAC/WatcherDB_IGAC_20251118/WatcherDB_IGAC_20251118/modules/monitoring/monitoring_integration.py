"""
TapOS Monitoring Integration
Arquivo para ser ADICIONADO ao tapos_real_data_complete_fix.py
"""

# ========================================
# ADICIONAR ESTES IMPORTS NO INÍCIO DO ARQUIVO
# ========================================

from modules.monitoring.monitoring import SQLServerMonitoring, ConnectionInfo
from modules.monitoring.queries import SQLQueries

# ========================================
# ADICIONAR NO LIFESPAN (após inicializar inventory_manager)
# ========================================

# No lifespan, adicionar após criar inventory_manager:
app.state.sql_monitoring = SQLServerMonitoring(
    cache=app.state.inventory_manager.cache,
    max_connections=30,  # Aumentado para melhor performance com requisições simultâneas
    max_workers=4
)
logger.info("SQL Server Monitoring initialized")

# No shutdown, adicionar:
if hasattr(app.state, 'sql_monitoring'):
    app.state.sql_monitoring.close()

# ========================================
# ADICIONAR ESTAS ROUTES NO FINAL DO ARQUIVO (antes de if __name__)
# ========================================

# === MONITORING ENDPOINTS ===

@app.get("/monitoring")
async def monitoring_interface():
    """Interface de monitoramento SQL Server"""
    try:
        with open("monitoring_interface.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Monitoring interface not found</h1>", status_code=404)

@app.get("/api/monitoring/test-connection/{server}")
async def test_sql_connection(server: str, instance: str = "DEFAULT"):
    """Testa conexão com SQL Server"""
    try:
        result = await app.state.sql_monitoring.test_connection(server, instance)
        return result
    except Exception as e:
        logger.error(f"Connection test error: {e}")
        return {
            'success': False,
            'message': str(e),
            'response_time_ms': 0,
            'timestamp': datetime.now().isoformat()
        }

@app.get("/api/monitoring/health/{server}")
async def get_server_health(server: str, instance: str = "DEFAULT"):
    """Health overview do servidor"""
    try:
        result = await app.state.sql_monitoring.get_health_overview(server, instance)
        return result
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/storage/{server}")
async def get_storage_info(server: str, instance: str = "DEFAULT"):
    """Informações de storage/filegroups"""
    try:
        result = await app.state.sql_monitoring.get_filegroups_space(server, instance)
        return result
    except Exception as e:
        logger.error(f"Storage check error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/slow-queries/{server}")
async def get_slow_queries(server: str, instance: str = "DEFAULT"):
    """Top queries lentas"""
    try:
        result = await app.state.sql_monitoring.get_slow_queries(server, instance)
        return result
    except Exception as e:
        logger.error(f"Slow queries error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/processes/{server}")
async def get_active_processes(server: str, instance: str = "DEFAULT"):
    """Processos ativos"""
    try:
        result = await app.state.sql_monitoring.get_active_processes(server, instance)
        return result
    except Exception as e:
        logger.error(f"Processes error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/blocking/{server}")
async def get_blocking_chains(server: str, instance: str = "DEFAULT"):
    """Cadeias de bloqueio"""
    try:
        result = await app.state.sql_monitoring.get_blocking_chains(server, instance)
        return result
    except Exception as e:
        logger.error(f"Blocking check error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/backups/{server}")
async def get_backup_status(server: str, instance: str = "DEFAULT"):
    """Status dos backups"""
    try:
        result = await app.state.sql_monitoring.get_backup_status(server, instance)
        return result
    except Exception as e:
        logger.error(f"Backup check error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/wait-stats/{server}")
async def get_wait_statistics(server: str, instance: str = "DEFAULT"):
    """Estatísticas de wait"""
    try:
        result = await app.state.sql_monitoring.get_wait_stats(server, instance)
        return result
    except Exception as e:
        logger.error(f"Wait stats error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/indexes/{server}")
async def get_index_fragmentation(server: str, instance: str = "DEFAULT"):
    """Índices fragmentados"""
    try:
        result = await app.state.sql_monitoring.get_index_fragmentation(server, instance)
        return result
    except Exception as e:
        logger.error(f"Index fragmentation error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/availability-groups/{server}")
async def get_availability_groups(server: str, instance: str = "DEFAULT"):
    """Status Availability Groups"""
    try:
        result = await app.state.sql_monitoring.get_availability_groups(server, instance)
        return result
    except Exception as e:
        logger.error(f"AG check error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/sql-jobs/{server}")
async def get_sql_agent_jobs(server: str, instance: str = "DEFAULT"):
    """SQL Agent Jobs status"""
    try:
        result = await app.state.sql_monitoring.get_sql_agent_jobs(server, instance)
        return result
    except Exception as e:
        logger.error(f"Jobs check error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/monitoring/pool-stats")
async def get_connection_pool_stats():
    """Estatísticas do connection pool"""
    try:
        stats = app.state.sql_monitoring.get_pool_stats()
        return {'success': True, 'stats': stats}
    except Exception as e:
        logger.error(f"Pool stats error: {e}")
        return {'success': False, 'error': str(e)}