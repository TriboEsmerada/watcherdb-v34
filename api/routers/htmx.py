"""
HTMX endpoints — return partial HTML fragments for the htmx-powered frontend.

These endpoints replace the monolithic JavaScript that builds DOM manually.
Each returns a Jinja2 template partial rendered with real data.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.dependencies import get_pool
from api.connection_pool import SQLServerConnectionPool, execute_on_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/htmx", tags=["HTMX Partials"])
templates = Jinja2Templates(directory="templates")


@router.get("/servers", response_class=HTMLResponse)
async def htmx_server_list(request: Request):
    """Return server list HTML for sidebar."""
    try:
        # Get servers from inventory
        from watcherdb.core.settings import settings
        from api.connection_pool import get_intelligence_pool

        pool = get_intelligence_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT server_name, instance_name, environment, status
                FROM servers
                WHERE status != 'INACTIVE'
                ORDER BY environment, server_name
            """)
            servers = []
            for row in cursor.fetchall():
                servers.append({
                    "server_id": f"{row[0]}_{row[1]}".replace("\\", "_") if row[1] else row[0],
                    "name": f"{row[0]}\\{row[1]}" if row[1] else row[0],
                    "environment": (row[2] or "").lower(),
                    "status": "online" if (row[3] or "").upper() == "ACTIVE" else "offline",
                })
            cursor.close()
        finally:
            pool.return_connection(conn)

        # new-style (request 1o arg): shim old-style removido no starlette 1.0
        # (incidente instalacao 2026-08-10) — compativel 0.50 dev + 1.0 build.
        return templates.TemplateResponse(
            request,
            "partials/_server_list_items.html",
            {"servers": servers},
        )
    except Exception as e:
        logger.error(f"Error loading server list: {e}")
        return HTMLResponse(
            '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Error loading servers</div>'
        )


@router.get("/tab/{tab_name}", response_class=HTMLResponse)
async def htmx_tab_content(
    request: Request,
    tab_name: str,
    server_id: str = "",
):
    """Return tab content HTML. Each tab type has its own partial template."""

    # Map tab names to partial templates
    tab_templates = {
        "overview": "partials/tabs/_overview.html",
        "backup": "partials/tabs/_backup.html",
        "space": "partials/tabs/_space.html",
        "cpu": "partials/tabs/_cpu.html",
        "memory": "partials/tabs/_memory.html",
        "jobs": "partials/tabs/_jobs.html",
        "alwayson": "partials/tabs/_alwayson.html",
        "disk": "partials/tabs/_disk.html",
        "services": "partials/tabs/_services.html",
        "log": "partials/tabs/_log.html",
        "security": "partials/tabs/_security.html",
        "users": "partials/tabs/_users.html",
        "sql-diagnostics": "partials/tabs/_sql_diagnostics.html",
        "encrypted": "partials/tabs/_encrypted.html",
    }

    template = tab_templates.get(tab_name)
    if not template:
        return HTMLResponse(f'<div class="error-message">Unknown tab: {tab_name}</div>', status_code=404)

    # Try to fetch real data for this tab
    tab_data = {}
    if server_id:
        try:
            tab_data = await _fetch_tab_data(tab_name, server_id)
        except Exception as e:
            logger.error(f"Error fetching data for tab {tab_name}/{server_id}: {e}")
            tab_data = {"error": str(e)}

    return templates.TemplateResponse(
        request,
        template,
        {"server_id": server_id, "tab_name": tab_name, "data": tab_data},
    )


@router.get("/server/{server_id}/header", response_class=HTMLResponse)
async def htmx_server_header(request: Request, server_id: str):
    """Return server header HTML with nav tabs."""
    return templates.TemplateResponse(
        request,
        "partials/_server_header.html",
        {"server_id": server_id},
    )


async def _fetch_tab_data(tab_name: str, server_id: str) -> dict:
    """Fetch data for a specific tab from the appropriate API endpoint."""
    import httpx

    # Map tabs to internal API endpoints
    api_map = {
        "overview": f"/api/v3/overview/summary/{server_id}",
        "backup": f"/api/v3/queries/server/{server_id}/backup",
        "space": f"/api/v3/queries/server/{server_id}/log-space",
        "cpu": f"/api/v3/os-performance/{server_id}/cpu",
        "memory": f"/api/v3/os-performance/{server_id}/memory",
        "jobs": f"/api/jobs/server/{server_id}",
        "services": f"/api/services/server/{server_id}",
    }

    endpoint = api_map.get(tab_name)
    if not endpoint:
        return {}

    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
            resp = await client.get(endpoint)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug(f"Internal API call failed for {tab_name}: {e}")

    return {}
