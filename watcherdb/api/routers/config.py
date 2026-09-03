"""
Configuration Router
Handles configuration management endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Dict, Any, List
import logging
import json
from pathlib import Path

from watcherdb.core.auth import get_current_user, User, require_role, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/config",
    tags=["configuration"],
    responses={404: {"description": "Not found"}},
)

CONFIG_DIR = Path("config")


@router.get("/sql-servers")
async def get_sql_servers_config(
    current_user: User = Depends(get_current_user)
):
    """Get SQL Servers configuration"""
    try:
        logger.info(f"SQL Servers config requested by {current_user.username}")

        config_file = CONFIG_DIR / "sql_servers.json"

        if not config_file.exists():
            raise HTTPException(status_code=404, detail="SQL Servers configuration not found")

        with open(config_file, 'r') as f:
            config = json.load(f)

        return config

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Configuration file not found")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        raise HTTPException(status_code=500, detail="Invalid configuration file format")
    except Exception as e:
        logger.error(f"Error reading SQL Servers config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sql-servers")
async def update_sql_servers_config(
    config: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Update SQL Servers configuration (Admin only)"""
    try:
        logger.info(f"SQL Servers config update by {current_user.username}")

        config_file = CONFIG_DIR / "sql_servers.json"

        # Backup existing config
        if config_file.exists():
            backup_file = CONFIG_DIR / f"sql_servers_backup_{Path().name}.json"
            with open(config_file, 'r') as f:
                backup_data = f.read()
            with open(backup_file, 'w') as f:
                f.write(backup_data)
            logger.info(f"Backed up config to {backup_file}")

        # Write new config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info("SQL Servers config updated successfully")

        return {
            "status": "success",
            "message": "Configuration updated successfully",
            "backup_created": backup_file.name if config_file.exists() else None
        }

    except Exception as e:
        logger.error(f"Error updating SQL Servers config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/custom-queries")
async def get_custom_queries_config(
    current_user: User = Depends(get_current_user)
):
    """Get custom queries configuration"""
    try:
        logger.info(f"Custom queries config requested by {current_user.username}")

        config_file = CONFIG_DIR / "custom_queries.json"

        if not config_file.exists():
            return {"queries": []}

        with open(config_file, 'r') as f:
            config = json.load(f)

        return config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in custom queries config: {e}")
        raise HTTPException(status_code=500, detail="Invalid configuration file format")
    except Exception as e:
        logger.error(f"Error reading custom queries config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/custom-queries")
async def update_custom_queries_config(
    config: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Update custom queries configuration (Analyst+ only)"""
    try:
        logger.info(f"Custom queries config update by {current_user.username}")

        config_file = CONFIG_DIR / "custom_queries.json"

        # Validate query structure
        if "queries" not in config:
            raise HTTPException(status_code=400, detail="Configuration must contain 'queries' array")

        for query in config["queries"]:
            required_fields = ["id", "name", "query"]
            if not all(field in query for field in required_fields):
                raise HTTPException(
                    status_code=400,
                    detail=f"Each query must have: {', '.join(required_fields)}"
                )

        # Write config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info("Custom queries config updated successfully")

        return {
            "status": "success",
            "message": "Custom queries updated successfully",
            "query_count": len(config["queries"])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating custom queries config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_alerts_config(
    current_user: User = Depends(get_current_user)
):
    """Get alerts configuration"""
    try:
        logger.info(f"Alerts config requested by {current_user.username}")

        config_file = CONFIG_DIR / "alerts.json"

        if not config_file.exists():
            raise HTTPException(status_code=404, detail="Alerts configuration not found")

        with open(config_file, 'r') as f:
            config = json.load(f)

        return config

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Alerts configuration file not found")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in alerts config: {e}")
        raise HTTPException(status_code=500, detail="Invalid configuration file format")
    except Exception as e:
        logger.error(f"Error reading alerts config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts")
async def update_alerts_config(
    config: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Update alerts configuration (Admin only)"""
    try:
        logger.info(f"Alerts config update by {current_user.username}")

        config_file = CONFIG_DIR / "alerts.json"

        # Write config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info("Alerts config updated successfully")

        return {
            "status": "success",
            "message": "Alerts configuration updated successfully"
        }

    except Exception as e:
        logger.error(f"Error updating alerts config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alwayson-inventory")
async def get_alwayson_inventory(
    current_user: User = Depends(get_current_user)
):
    """Get AlwaysOn inventory configuration"""
    try:
        logger.info(f"AlwaysOn inventory requested by {current_user.username}")

        config_file = CONFIG_DIR / "alwayson_inventory.json"

        if not config_file.exists():
            return {"availability_groups": []}

        with open(config_file, 'r') as f:
            config = json.load(f)

        return config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in AlwaysOn inventory: {e}")
        raise HTTPException(status_code=500, detail="Invalid configuration file format")
    except Exception as e:
        logger.error(f"Error reading AlwaysOn inventory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
