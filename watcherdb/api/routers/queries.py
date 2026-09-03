"""
Custom Queries Router
Handles custom SQL query execution
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Dict, Any, List
import logging

from watcherdb.core.auth import get_current_user, User, require_role, UserRole
from watcherdb.services.query_executor import QueryExecutor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/queries",
    tags=["queries"],
    responses={404: {"description": "Not found"}},
)


@router.post("/custom/{server_id}")
async def execute_custom_query(
    server_id: str,
    query_request: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Execute a custom SQL query on a specific server (Analyst+ only)"""
    try:
        query_text = query_request.get("query")
        timeout = query_request.get("timeout", 30)

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f"Custom query execution on {server_id} by {current_user.username}")
        logger.debug(f"Query: {query_text[:100]}...")

        # Security: Validate query (prevent destructive operations)
        dangerous_keywords = [
            "DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE",
            "INSERT", "EXEC", "EXECUTE", "sp_", "xp_"
        ]

        query_upper = query_text.upper()
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                logger.warning(f"Blocked dangerous query from {current_user.username}: {keyword}")
                raise HTTPException(
                    status_code=403,
                    detail=f"Query contains forbidden keyword: {keyword}. Only SELECT queries are allowed."
                )

        # Execute query
        executor = QueryExecutor()
        result = executor.execute_query(server_id, query_text, timeout=timeout)

        return {
            "server_id": server_id,
            "status": "success",
            "row_count": len(result.get("rows", [])),
            "columns": result.get("columns", []),
            "rows": result.get("rows", []),
            "execution_time_ms": result.get("execution_time_ms", 0)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing custom query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_query_templates(
    current_user: User = Depends(get_current_user)
):
    """Get predefined query templates"""
    try:
        templates = [
            {
                "id": "database_sizes",
                "name": "Database Sizes",
                "description": "Get size of all databases",
                "query": """
SELECT
    DB_NAME(database_id) AS DatabaseName,
    SUM(size * 8 / 1024) AS SizeMB
FROM sys.master_files
GROUP BY database_id
ORDER BY SizeMB DESC
                """.strip()
            },
            {
                "id": "table_sizes",
                "name": "Table Sizes",
                "description": "Get size of all tables in current database",
                "query": """
SELECT
    t.NAME AS TableName,
    p.rows AS RowCounts,
    SUM(a.total_pages) * 8 / 1024 AS TotalSpaceMB
FROM sys.tables t
INNER JOIN sys.indexes i ON t.OBJECT_ID = i.object_id
INNER JOIN sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
WHERE t.is_ms_shipped = 0
GROUP BY t.Name, p.Rows
ORDER BY TotalSpaceMB DESC
                """.strip()
            },
            {
                "id": "index_fragmentation",
                "name": "Index Fragmentation",
                "description": "Check index fragmentation levels",
                "query": """
SELECT
    OBJECT_NAME(ips.object_id) AS TableName,
    i.name AS IndexName,
    ips.index_type_desc,
    ips.avg_fragmentation_in_percent,
    ips.page_count
FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
WHERE ips.avg_fragmentation_in_percent > 10
    AND ips.page_count > 1000
ORDER BY ips.avg_fragmentation_in_percent DESC
                """.strip()
            },
            {
                "id": "active_sessions",
                "name": "Active Sessions",
                "description": "Show currently active sessions",
                "query": """
SELECT
    session_id,
    login_time,
    host_name,
    program_name,
    login_name,
    status,
    cpu_time,
    memory_usage,
    reads,
    writes
FROM sys.dm_exec_sessions
WHERE is_user_process = 1
    AND status = 'running'
ORDER BY cpu_time DESC
                """.strip()
            },
            {
                "id": "wait_stats",
                "name": "Wait Statistics",
                "description": "Top wait types",
                "query": """
SELECT TOP 10
    wait_type,
    wait_time_ms / 1000.0 AS wait_time_s,
    waiting_tasks_count,
    (wait_time_ms / waiting_tasks_count) AS avg_wait_time_ms
FROM sys.dm_os_wait_stats
WHERE waiting_tasks_count > 0
ORDER BY wait_time_ms DESC
                """.strip()
            }
        ]

        return {
            "template_count": len(templates),
            "templates": templates
        }

    except Exception as e:
        logger.error(f"Error getting query templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute-template/{server_id}/{template_id}")
async def execute_query_template(
    server_id: str,
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """Execute a predefined query template"""
    try:
        logger.info(f"Executing template {template_id} on {server_id} by {current_user.username}")

        # Get templates
        templates_response = await get_query_templates(current_user)
        templates = templates_response["templates"]

        # Find template
        template = next((t for t in templates if t["id"] == template_id), None)

        if not template:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

        # Execute template query
        executor = QueryExecutor()
        result = executor.execute_query(server_id, template["query"], timeout=60)

        return {
            "server_id": server_id,
            "template_id": template_id,
            "template_name": template["name"],
            "status": "success",
            "row_count": len(result.get("rows", [])),
            "columns": result.get("columns", []),
            "rows": result.get("rows", []),
            "execution_time_ms": result.get("execution_time_ms", 0)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
