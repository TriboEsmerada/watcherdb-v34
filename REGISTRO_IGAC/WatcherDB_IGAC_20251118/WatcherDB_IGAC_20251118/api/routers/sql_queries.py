#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Queries SQL de Troubleshooting e Manutenção
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import logging
from decimal import Decimal

from modules.monitoring.monitoring import SQLServerMonitoring
from modules.monitoring.queries import SQLQueries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/queries", tags=["SQL Queries"])

def _serialize_result(obj):
    """Serializa objetos para JSON (converte Decimal, etc)"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_result(item) for item in obj]
    return obj

async def execute_query_on_server(server_id: str, query: str) -> List[Dict]:
    """Executa query em um servidor específico"""
    try:
        # Usar SQLServerMonitoring que já está configurado no app
        # Se não estiver disponível, usar executor diretamente
        from modules.monitoring.monitoring import SQLServerExecutor, ConnectionPool, ConnectionInfo
        
        # Criar executor temporário
        pool = ConnectionPool(max_connections=5)
        executor = SQLServerExecutor(pool, max_workers=2)
        
        # Parse server_id (pode ser "SERVER" ou "SERVER\INSTANCE" ou "SERVER_INSTANCE")
        if '\\' in server_id:
            server, instance = server_id.split('\\', 1)
        elif '_' in server_id and not server_id.endswith('_DEFAULT'):
            # Formato: SERVER_INSTANCE
            parts = server_id.rsplit('_', 1)
            server, instance = parts[0], parts[1] if len(parts) > 1 else "DEFAULT"
        else:
            server = server_id.replace('_DEFAULT', '')
            instance = "DEFAULT"
        
        conn_info = ConnectionInfo(
            server=server,
            instance=instance,
            database="master",
            use_windows_auth=True
        )
        
        result = await executor.execute_query(conn_info, query)
        
        if result is None:
            return []
        
        # Garantir serialização de Decimal
        if isinstance(result, list):
            return _serialize_result(result)
        else:
            return _serialize_result([{"result": str(result)}])
            
    except Exception as e:
        logger.error(f"Erro ao executar query em {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/blocking/{server_id}")
async def get_blocking_hierarchy(server_id: str):
    """Obtém hierarquia de bloqueios"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BLOCKING_HIERARCHY)
        return JSONResponse(content={"server_id": server_id, "blocking_chains": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter bloqueios de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/slow-queries/{server_id}")
async def get_slow_queries(server_id: str):
    """Obtém top queries lentas"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TOP_SLOW_QUERIES_DETAILED)
        return JSONResponse(content={"server_id": server_id, "slow_queries": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter queries lentas de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/log-space/{server_id}")
async def get_log_space(server_id: str):
    """Obtém monitoramento de espaço de log"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.LOG_SPACE_MONITORING)
        return JSONResponse(content={"server_id": server_id, "log_space": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter espaço de log de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sql-agent-jobs/{server_id}")
async def get_sql_agent_jobs_failing(server_id: str):
    """Obtém jobs SQL Agent falhando"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.SQL_AGENT_JOBS_FAILING)
        return JSONResponse(content={"server_id": server_id, "failing_jobs": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter jobs SQL Agent de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{server_id}")
async def get_problematic_sessions(server_id: str):
    """Obtém sessões problemáticas"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.PROBLEMATIC_SESSIONS)
        return JSONResponse(content={"server_id": server_id, "problematic_sessions": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter sessões problemáticas de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/index-fragmentation/{server_id}")
async def get_index_fragmentation(server_id: str):
    """Obtém índices fragmentados (v1.4.8.1 - com suporte a HEAP e QUOTENAME)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.INDEX_FRAGMENTATION)
        return JSONResponse(content={"server_id": server_id, "index_fragmentation": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter fragmentação de índices de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tempdb/{server_id}")
async def get_tempdb_monitoring(server_id: str):
    """Obtém monitoramento de TempDB"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TEMPDB_MONITORING)
        return JSONResponse(content={"server_id": server_id, "tempdb": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter monitoramento TempDB de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/file-growth/{server_id}")
async def get_file_growth(server_id: str, database: Optional[str] = Query(None)):
    """Obtém monitoramento de crescimento de arquivos"""
    try:
        # Se database não especificado, usar query para todas as bases via sys.master_files
        # CORRIGIDO: Busca filegroup_name usando JOIN com sys.databases e tentativa de acessar filegroups
        # Usa uma abordagem mais simples que funciona melhor com pyodbc
        if not database:
            query = """
            SELECT 
                d.name as database_name,
                f.name as file_name,
                f.type_desc as file_type,
                CASE 
                    WHEN f.type_desc = 'LOG' THEN NULL
                    WHEN f.data_space_id = 1 THEN 'PRIMARY'
                    ELSE CAST(f.data_space_id AS VARCHAR(10)) + ' (ID)'
                END as filegroup_name,
                f.physical_name,
                CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2)) as current_size_mb,
                CASE 
                    WHEN f.max_size = -1 THEN 'Unlimited'
                    WHEN f.max_size = 268435456 THEN '2TB (Default Max)'
                    ELSE CAST(f.max_size * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
                END as max_size,
                CASE 
                    WHEN f.is_percent_growth = 1 
                    THEN CAST(f.growth AS VARCHAR(10)) + '%'
                    ELSE CAST(f.growth * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
                END as growth_increment,
                CASE 
                    WHEN f.is_percent_growth = 1 AND f.growth >= 10 
                    THEN 'WARNING: Percent growth >= 10%'
                    WHEN f.is_percent_growth = 0 AND (f.growth * 8.0 / 1024) < 100 
                    THEN 'WARNING: Fixed growth < 100MB'
                    ELSE 'OK'
                END as growth_recommendation
            FROM sys.databases d WITH(NOLOCK)
            INNER JOIN sys.master_files f WITH(NOLOCK) ON d.database_id = f.database_id
            WHERE d.database_id > 4  -- Excluir system databases
            AND d.state = 0  -- Apenas databases ONLINE
            ORDER BY d.name, f.type, f.file_id
            """
        else:
            # Query específica para uma database
            query = f"""
            USE [{database}];
            SELECT 
                DB_NAME() as database_name,
                f.name as file_name,
                f.type_desc as file_type,
                fg.name as filegroup_name,
                f.physical_name,
                CAST(f.size * 8.0 / 1024 AS DECIMAL(12,2)) as current_size_mb,
                CASE 
                    WHEN f.max_size = -1 THEN 'Unlimited'
                    WHEN f.max_size = 268435456 THEN '2TB (Default Max)'
                    ELSE CAST(f.max_size * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
                END as max_size,
                CASE 
                    WHEN f.is_percent_growth = 1 
                    THEN CAST(f.growth AS VARCHAR(10)) + '%'
                    ELSE CAST(f.growth * 8.0 / 1024 AS VARCHAR(20)) + ' MB'
                END as growth_increment,
                CASE 
                    WHEN f.is_percent_growth = 1 AND f.growth >= 10 
                    THEN 'WARNING: Percent growth >= 10%'
                    WHEN f.is_percent_growth = 0 AND (f.growth * 8.0 / 1024) < 100 
                    THEN 'WARNING: Fixed growth < 100MB'
                    ELSE 'OK'
                END as growth_recommendation
            FROM sys.database_files f WITH(NOLOCK)
            LEFT JOIN sys.filegroups fg WITH(NOLOCK) ON f.data_space_id = fg.data_space_id
            ORDER BY f.type, f.file_id
            """
        
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "file_growth": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter crescimento de arquivos de {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/statistics/{server_id}")
async def get_statistics_outdated(server_id: str):
    """Obtém estatísticas desatualizadas"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.STATISTICS_OUTDATED)
        return JSONResponse(content={"server_id": server_id, "statistics": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/database-connections/{server_id}")
async def get_database_connections(server_id: str):
    """Obtém número de conexões por database"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.DATABASE_CONNECTIONS)
        return JSONResponse(content={"server_id": server_id, "database_connections": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter conexões por database de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backup/{server_id}")
async def get_backup_status(server_id: str):
    """Obtém status de backups"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BACKUP_STATUS)
        return JSONResponse(content={"server_id": server_id, "backup_status": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status de backup de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tde-status/{server_id}")
async def get_tde_status(server_id: str):
    """Obtém status de TDE (Transparent Data Encryption)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TDE_STATUS)
        return JSONResponse(content={"server_id": server_id, "tde_status": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status TDE de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tde-database-status/{server_id}")
async def get_tde_database_status(server_id: str):
    """Obtém status de TDE por database (quais estão encriptadas e quais não estão)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TDE_DATABASE_STATUS)
        return JSONResponse(content={"server_id": server_id, "tde_database_status": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status TDE por database de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mirroring/{server_id}")
async def get_mirroring_logshipping(server_id: str):
    """Obtém status de Mirroring/Log Shipping"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.MIRRORING_LOGSHIPPING_STATUS)
        return JSONResponse(content={"server_id": server_id, "mirroring_logshipping": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status Mirroring/Log Shipping de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/databases/{server_id}")
async def get_databases(server_id: str):
    """Lista todas as bases de dados do servidor"""
    try:
        query = """
        SELECT
            name as database_name,
            database_id,
            state_desc,
            recovery_model_desc,
            CASE WHEN HAS_DBACCESS(name) = 1 THEN 1 ELSE 0 END as is_accessible
        FROM sys.databases WITH(NOLOCK)
        WHERE state = 0  -- ONLINE
        ORDER BY name
        """
        result = await execute_query_on_server(server_id, query)
        # Garantir serialização
        serialized_result = _serialize_result(result)
        return JSONResponse(content={"server_id": server_id, "databases": serialized_result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao listar databases de {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/filegroup-growth-history/{server_id}")
async def get_filegroup_growth_history(server_id: str, database: Optional[str] = Query(None)):
    """Obtém histórico de crescimento de filegroups (últimos 12 meses) - Suporta filtro por database"""
    try:
        query = SQLQueries.get_filegroup_growth_history_filtered(database)
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "database": database or "ALL", "filegroup_growth_history": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter histórico de crescimento de filegroups de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/filegroup-growth-forecast/{server_id}")
async def get_filegroup_growth_forecast(server_id: str, database: Optional[str] = Query(None)):
    """Obtém projeção de crescimento de filegroups (MonthsUntilFull) - Suporta filtro por database"""
    try:
        query = SQLQueries.get_filegroup_growth_forecast_filtered(database)
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "database": database or "ALL", "filegroup_growth_forecast": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter projeção de crescimento de filegroups de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backup-history-analysis/{server_id}")
async def get_backup_history_analysis(server_id: str):
    """Obtém análise de histórico de backups (considera Always On AG) - SEM filtro (precisa ver todas as databases)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.BACKUP_HISTORY_ANALYSIS)
        return JSONResponse(content={"server_id": server_id, "backup_history_analysis": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter análise de histórico de backups de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/missing-index-analysis/{server_id}")
async def get_missing_index_analysis(server_id: str, database: Optional[str] = Query(None)):
    """Obtém análise de índices faltantes com alto impacto - Suporta filtro por database"""
    try:
        query = SQLQueries.get_missing_index_analysis_filtered(database)
        result = await execute_query_on_server(server_id, query)
        return JSONResponse(content={"server_id": server_id, "database": database or "ALL", "missing_index_analysis": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter análise de índices faltantes de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

