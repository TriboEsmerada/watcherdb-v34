"""
Centralized application settings using pydantic-settings.

Priority order (highest wins):
    1. Defaults defined below in WatcherDBSettings
    2. Values from .env file (development only)
    3. System / process environment variables  <-- use this in production

In production, set secrets (JWT_SECRET_KEY, WATCHERDB_ENCRYPTION_KEY,
SMTP_PASSWORD, etc.) as system-level environment variables and remove
.env entirely. See .env.example for detailed instructions.

Usage:
    from watcherdb.core.settings import settings
    print(settings.jwt_secret_key)
"""
import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field


class WatcherDBSettings(BaseSettings):
    """All application configuration in one typed model."""

    # Server
    app_name: str = "WatcherDB"
    # SOT de versao: deploy/release_vars.psd1 (ProductVersion). Manter em
    # sync manualmente ate o build_release.ps1 automatizar.
    app_version: str = "3.3.0"
    debug: bool = False
    log_level: str = "INFO"

    # JWT Auth
    jwt_secret_key: str = Field(default="", description="JWT signing key. Generate with: python -c 'import secrets; print(secrets.token_hex(32))'")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h

    # Encryption
    watcherdb_encryption_key: str = ""

    # Connection Pool
    connection_timeout: int = 15  # seconds (login timeout, nao query). Era 60: escondia hangs
    # de boot ~3min quando o Intelligence server estava inacessivel (2 incidentes 2026-07-21).
    odbc_driver: str = "ODBC Driver 17 for SQL Server"  # Change to "ODBC Driver 18 for SQL Server" if available

    # SQL Server Intelligence DB
    intelligence_server: str = r"SQLHDSTST505\I01"
    intelligence_database: str = "WatcherDB_Intelligence"
    intelligence_use_windows_auth: bool = True
    intelligence_sql_user: str = "sql_monitoring"
    intelligence_sql_password: str = ""

    # Inventario de servidores (E6, plano servers.json fonte unica 2026-08-19):
    # "db"   = metadata.monitored_server(+_database) na Intelligence, alimentada
    #          pelo collector V1 a partir do servers.json canonico (fonte unica);
    #          fallback automatico ao ficheiro local se a BD falhar/vier vazia.
    # "file" = config/servers.json local (comportamento anterior a E6; rollback).
    # Env var: INVENTORY_SOURCE=db|file
    inventory_source: str = "db"
    inventory_cache_seconds: int = 60

    # SMTP
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Cache
    use_redis: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379

    # OpenTelemetry
    otel_enabled: bool = True
    otel_exporter: str = "console"
    otel_endpoint: str = "http://localhost:4317"

    # LLM
    llm_enabled: bool = False
    anthropic_api_key: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


# Singleton instance — import this
settings = WatcherDBSettings()
