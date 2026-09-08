"""

WatcherDB - Database Monitoring System - COMPLETE REAL DATA FIX
SISTEMA QUE FUNCIONA COM SEUS DADOS REAIS - NÃO DADOS FICTÍCIOS

FIX COMPLETO:
✅ Lê o Excel real primeiro para descobrir a estrutura
✅ Cria o schema SQLite baseado nos dados reais do Excel  
✅ Importa APENAS dados reais - zero dados fictícios
✅ Suporte completo ao seu TAP_SQL_Server_Inventory.xlsx
✅ Schema dinâmico baseado nas colunas que realmente existem
✅ Mapeamento inteligente de colunas

"""

# Carregar variáveis de ambiente do .env antes de qualquer import
# IMPORTANTE: passar path explicito — quando corrido como Windows Service o cwd
# inicial e' C:\Windows\System32, nao a raiz do projecto. Sem path explicito
# load_dotenv() falha silenciosamente e variaveis encriptadas (JWT_SECRET_KEY,
# WATCHERDB_ENCRYPTION_KEY_DPAPI, INTELLIGENCE_SQL_PASSWORD) ficam vazias —
# resultado: JWT cai em chave efemera, tokens nao sobrevivem restart.
try:
    import os as _os_for_dotenv
    import sys as _sys_for_dotenv
    from pathlib import Path as _Path_for_dotenv
    from dotenv import load_dotenv
    # B1-8/1.6 (auditoria empacotamento): .env resolvido 3-tier — env var,
    # ProgramData (producao frozen; sitio documentado ao DBA), raiz (dev).
    # Inline (sem importar watcherdb.*) para correr ANTES de settings ler env.
    _dotenv_candidates = []
    _wdd = _os_for_dotenv.environ.get("WATCHERDB_DATA_DIR")
    if _wdd:
        _dotenv_candidates.append(_Path_for_dotenv(_wdd) / ".env")
    if getattr(_sys_for_dotenv, "frozen", False):
        _dotenv_candidates.append(_Path_for_dotenv(r"C:\ProgramData\WatcherDB") / ".env")
    _dotenv_candidates.append(_Path_for_dotenv(__file__).resolve().parent / ".env")
    for _dc in _dotenv_candidates:
        if _dc.exists():
            load_dotenv(_dc)
            break
except ImportError:
    pass  # python-dotenv não instalado — variáveis devem estar no ambiente do sistema

from modules.monitoring.space_analysis import (
    SpaceAnalysisEngine,
    get_space_analysis_for_all_servers,
    extract_alerts,
)
from modules.monitoring.monitoring import SQLServerMonitoring
from modules.monitoring.memory_analysis import (
    get_server_memory_analysis,
    get_alwayson_memory_comparison,
    get_memory_health_summary,
    analyze_os_memory_snapshot,
)
from modules.monitoring.cpu_analysis import get_server_cpu_analysis
from modules.monitoring.backup_analysis import BackupAnalysisEngine
from modules.monitoring.backup_pattern_analysis import BackupPatternAnalyzer
from modules.monitoring.security_analysis import SecurityAnalysisEngine

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request, Body
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
import asyncio
import json
import sqlite3
import threading
import time
import mmap
import struct
import hashlib
import pickle
import os
import sys
import re
import zipfile
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Set
from dataclasses import dataclass, asdict, field
from enum import Enum
from contextlib import asynccontextmanager
from decimal import Decimal
import logging
import uuid
import collections
import heapq
import bisect
from concurrent.futures import ThreadPoolExecutor
import weakref
import subprocess

# Path absoluto para sql_servers.json — quando corre como Windows Service
# o CWD e' C:\Windows\System32, por isso Path relativo falha (PermissionError
# ao tentar gravar em System32\config\sql_servers.json). Resolver via __file__.
_PROJECT_ROOT = Path(__file__).resolve().parent
# B0-4 (auditoria empacotamento): config editavel via config_dir() —
# dev: <root>/config (inalterado); frozen: C:\ProgramData\WatcherDB\config.
from watcherdb.core.paths import config_dir as _wdb_config_dir, bootstrap_config as _wdb_bootstrap_config
_CONFIG_DIR = _wdb_config_dir()
# B0-3 (auditoria empacotamento): frozen first-run nao traz JSONs vivos no
# bundle; seed skeletons vazios em ProgramData. No-op em dev.
_wdb_bootstrap_config()
SQL_SERVERS_CONFIG_PATH = _CONFIG_DIR / "sql_servers.json"
# servers.json — inventory rico lido pela sidebar + KPIs (monitored_servers[]).
# Schema diferente de sql_servers.json (tem credentials, alwayson topology, etc).
SERVERS_INVENTORY_PATH = _CONFIG_DIR / "servers.json"

# Configure structured logging
from watcherdb.core.logging_setup import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from watcherdb.core.cache import RedisLikeCache
from watcherdb.core.excel_parser import EnhancedExcelParser
from watcherdb.core.fuzzy_matcher import AdvancedFuzzyMatcher
from watcherdb.core.async_file_io import AsyncFileIO
from watcherdb.core.models import ServiceType, CheckType, InventoryServer
from watcherdb.core.schema_manager import SmartSchemaManager
from watcherdb.core.inventory_manager import SmartTapInventoryManager
from watcherdb.core.background_services import BackgroundServices
from watcherdb.core.websocket_manager import WebSocketManager

# === RESOURCE PATH HELPERS ===
# Resolve template/static paths absolutely so the service works regardless
# of current working directory (Windows service, frozen bundle via PyArmor/PyInstaller).
_BASE_DIR = Path(__file__).resolve().parent

def _tpl(name: str) -> str:
    """Absolute path to <project>/templates/<name>."""
    return str(_BASE_DIR / "templates" / name)

def _static(name: str) -> str:
    """Absolute path to <project>/static/<name>."""
    return str(_BASE_DIR / "static" / name)

# === FASTAPI APPLICATION ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Watcher DB System...")

    # Increase default asyncio thread pool for concurrent DB queries
    # This allows multiple users to execute queries simultaneously without blocking
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_event_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=40))
    logger.info("Default executor set to 40 threads (multi-user support)")

    from watcherdb.core.scheduler import start_scheduler, shutdown_scheduler
    start_scheduler()

    # Register periodic collectors with the scheduler.
    # job_failures_collector populates dbo.KPI_MSSQL_JOB_FAILURES_STG every
    # 5 minutes so /api/intelligence-kpis/dashboard reads from the view in
    # ~100ms instead of falling back to a 14s direct fan-out across 200+
    # instances on every dashboard polling cycle.
    try:
        from services.job_failures_collector import register_with_scheduler as _reg_jobf
        _reg_jobf()
    except Exception as _reg_err:
        logger.warning(f"Could not register job_failures_collector: {_reg_err}")

    app.state.inventory_manager = SmartTapInventoryManager()

    # SQL Monitoring — lightweight init (no DB calls yet)
    try:
        config_path = SQL_SERVERS_CONFIG_PATH
        with open(config_path, 'r', encoding='utf-8') as f:
            sql_config = json.load(f)
        app.state.sql_monitoring = SQLServerMonitoring(
            cache=app.state.inventory_manager.cache,
            max_connections=30,
            # Bumped to 30 — antes era 10. Quando o discovery service corre em
            # background com queries de 300+ segundos, esgotava o threadpool e
            # bloqueava endpoints sincronos como cpu/server/memory/server.
            max_workers=30
        )
        app.state.sql_servers_config = sql_config
        logger.info(f"SQL Monitoring inicializado: {len(sql_config['servers'])} servidores")
    except Exception as e:
        logger.error(f"ERRO ao inicializar SQL Monitoring: {e}")
        app.state.sql_monitoring = None

    app.state.background_services = None
    app.state.database_discovery = None

    logger.info("=" * 60)
    logger.info("Watcher DB System started successfully (port ready)")
    logger.info("=" * 60)

    # Heavy pre-warming runs in BACKGROUND after startup — does NOT block port binding
    import asyncio as _aio

    async def _background_prewarm():
        """Pre-warm caches and discover databases in background."""
        await _aio.sleep(2)  # Let uvicorn finish binding first
        try:
            logger.info("[BACKGROUND] Pre-warming inventory cache...")
            await _aio.wait_for(app.state.inventory_manager.load_complete_inventory(), timeout=30)
        except Exception as e:
            logger.warning(f"[BACKGROUND] Inventory pre-warm failed: {e}")
        try:
            from api.routers.intelligence_kpis import preload_kpi_cache
            logger.info("[BACKGROUND] Pre-loading KPI cache...")
            await preload_kpi_cache()
        except Exception as e:
            logger.warning(f"[BACKGROUND] KPI cache pre-load failed: {e}")
        # T-fix 2026-06-09 (#2): adiar discovery 5min + reduzir concorrencia 10->5.
        # Evita saturar o threadpool partilhado (SQLServerExecutor) no arranque,
        # mantendo CPU/Memory/dashboard responsivos na janela pos-restart.
        # [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: #2 defer-discovery]
        await _aio.sleep(300)
        try:
            from services.database_discovery_service import get_discovery_service
            discovery_service = get_discovery_service()
            app.state.database_discovery = discovery_service
            logger.info("[BACKGROUND] Starting database discovery (deferred 5min)...")
            result = await discovery_service.discover_all(max_concurrent=5)
            logger.info(f"[BACKGROUND] Discovery done: {result.get('successful', 0)}/{result.get('total_servers', 0)} servers")
        except Exception as e:
            logger.warning(f"[BACKGROUND] Database discovery failed: {e}")

    _aio.create_task(_background_prewarm())

    async def _periodic_kpi_rewarm():
        """#1 DS-Reconcile 2026-06-09: re-aquece o cache do dashboard a cada 50s
        (< TTL 60s) para nunca arrefecer -> load sempre rapido.
        [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: #1 re-warm]"""
        while True:
            await _aio.sleep(50)
            try:
                from api.routers.intelligence_kpis import _collect_and_cache_dashboard
                await _collect_and_cache_dashboard()
            except Exception as e:
                logger.warning(f"[REWARM] KPI cache re-warm falhou: {e}")

    _aio.create_task(_periodic_kpi_rewarm())

    yield
    
    # Shutdown
    logger.info("Shutting down Watcher DB System...")
    shutdown_scheduler()

    if hasattr(app.state, 'background_services') and app.state.background_services:
        await app.state.background_services.stop_all_services()
    
    if hasattr(app.state, 'inventory_manager'):
        # RedisLikeCache não tem método close, apenas cleanup se necessário
        if hasattr(app.state.inventory_manager.cache, 'close'):
            app.state.inventory_manager.cache.close()

    # Coordinated shutdown of all registered ThreadPoolExecutors
    from watcherdb.core.executor_registry import shutdown_all
    shutdown_all(wait=True, cancel_futures=True)

# Release hardening: allow disabling API docs in production via env var.
# WATCHERDB_DISABLE_DOCS=true suppresses /docs, /redoc and /openapi.json.
_DISABLE_DOCS = os.getenv("WATCHERDB_DISABLE_DOCS", "false").lower() in ("true", "1", "yes")

app = FastAPI(
    title="Watcher DB - Database Monitoring System",
    description="Database monitoring using YOUR REAL Excel data - No fictional data",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=None if _DISABLE_DOCS else "/docs",
    redoc_url=None if _DISABLE_DOCS else "/redoc",
    openapi_url=None if _DISABLE_DOCS else "/openapi.json",
)

# === LICENSE VALIDATION ===
# Delegado a watcherdb.licensing.startup_guard (FIND-20260424-001 B6).
# Modulo partilhado pelos 3 services (web, collector, AI). Gera Windows
# Event Log entries (1000 OK / 1001 FAILED / 1002 expiry warning 30d antes).
# Strict default (FIND-20260424-003). Public key path 3-tier (FIND-20260424-004).
def _validate_license_at_startup(app_: FastAPI) -> None:
    from watcherdb.licensing.startup_guard import validate_and_enforce

    registry, claims = validate_and_enforce(
        service_name="web_service",
        accepted_edition="standard",
        base_dir=_BASE_DIR,
    )
    app_.state.features = registry
    app_.state.license = claims  # None em advisory-failure; LicenseClaims em success


_validate_license_at_startup(app)


# === RESPONSE VALIDATION ERROR HANDLER ===
# Prevents response_model validation from crashing endpoints that return JSONResponse
# response_model is kept for OpenAPI schema documentation but validation errors are logged, not raised
from fastapi.exceptions import ResponseValidationError as _RVE
from fastapi.responses import JSONResponse as _JSONResp

@app.exception_handler(_RVE)
async def _response_validation_handler(request, exc):
    # 2026-08-17: o comentario dizia "return the original data" mas devolvia um
    # dict de erro — o payload real perdia-se (portal a zeros, sem cartao de erro).
    # Agora devolve mesmo exc.body (jsonable_encoder) e regista ERROR com os campos.
    # Espelho do handler em services/web_service/server.py (o que corre no servico).
    from fastapi.encoders import jsonable_encoder as _jenc
    try:
        _fields = [".".join(str(p) for p in e.get("loc", ())) or "?" for e in exc.errors()[:3]]
    except Exception:
        _fields = ["?"]
    logger.error(f"ResponseValidationError on {request.url.path} — response_model mismatch (campos: {_fields}); a devolver payload original")
    _body = getattr(exc, "body", None)
    if _body is None:
        return _JSONResp(status_code=200, content={"error": "response_model mismatch", "path": str(request.url.path)})
    try:
        return _JSONResp(status_code=200, content=_jenc(_body))
    except Exception:
        return _JSONResp(status_code=200, content={"error": "response_model mismatch", "path": str(request.url.path)})

# === GLOBAL RATE LIMITING (slowapi) ===
# Reads limits from config/config.yaml -> security.rate_limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

def _load_rate_limit_config() -> str:
    """Load default rate limit from config/config.yaml."""
    try:
        import yaml as _yaml
        _cfg_path = Path(__file__).parent / "config" / "config.yaml"
        if _cfg_path.exists():
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _cfg = _yaml.safe_load(_f) or {}
            rl = _cfg.get("security", {}).get("rate_limiting", {})
            if rl.get("enabled", True):
                return rl.get("default_limit", "100/minute")
        return "100/minute"
    except Exception:
        return "100/minute"

limiter = Limiter(key_func=get_remote_address, default_limits=[_load_rate_limit_config()])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prometheus metrics
from watcherdb.core.metrics import setup_metrics
setup_metrics(app, version="3.3.0")

# OpenTelemetry distributed tracing
from watcherdb.core.telemetry import setup_telemetry
setup_telemetry(app, service_name="watcherdb-main")

# Jinja2 templates — used for pages that need server-side nonce injection (CSP)
_jinja_templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

# === INCLUIR ROUTERS ADICIONAIS ===
try:
    from api.routers.alwayson import router as alwayson_router
    app.include_router(alwayson_router)
    logger.info(f"✅ Router Always On carregado: {alwayson_router.prefix} com {len(alwayson_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Always On: {e}", exc_info=True)

try:
    from api.routers.sql_queries import router as sql_queries_router
    app.include_router(sql_queries_router)
    logger.info(f"✅ Router SQL Queries carregado: {sql_queries_router.prefix} com {len(sql_queries_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router SQL Queries: {e}", exc_info=True)

try:
    from api.routers.diagnostics_overview import router as diagnostics_router
    app.include_router(diagnostics_router)
    logger.info(f"✅ Router Diagnostics Overview carregado: {diagnostics_router.prefix} com {len(diagnostics_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Diagnostics Overview: {e}", exc_info=True)

try:
    from api.routers.service_status import router as service_status_router
    app.include_router(service_status_router)
    logger.info(f"✅ Router Service Status carregado: {service_status_router.prefix} com {len(service_status_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Service Status: {e}", exc_info=True)

try:
    from api.routers.sqlserver_kpis import router as sqlserver_kpis_router
    app.include_router(sqlserver_kpis_router)
    logger.info(f"✅ Router SQL Server KPIs carregado: {sqlserver_kpis_router.prefix} com {len(sqlserver_kpis_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router SQL Server KPIs: {e}", exc_info=True)

try:
    from api.routers.intelligence_kpis import router as intelligence_kpis_router
    app.include_router(intelligence_kpis_router)
    logger.info(f"✅ Router Intelligence KPIs carregado: {intelligence_kpis_router.prefix} com {len(intelligence_kpis_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Intelligence KPIs: {e}", exc_info=True)

try:
    from api.routers.performance import router as performance_router
    app.include_router(performance_router)
    logger.info(f"✅ Router Performance Intelligence carregado: {performance_router.prefix} com {len(performance_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Performance Intelligence: {e}", exc_info=True)

try:
    from api.routers.collectors import router as collectors_router
    app.include_router(collectors_router)
    logger.info(f"✅ Router Collector Health carregado: {collectors_router.prefix} com {len(collectors_router.routes)} rotas (admin-only)")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Collector Health: {e}", exc_info=True)

# Wave R+10 (2026-05-25) -- Smart Defaults Initiative: universal KPI mute list
try:
    from api.routers.kpi_mute import router as kpi_mute_router
    app.include_router(kpi_mute_router)
    logger.info(f"✅ Router KPI Mute carregado: {kpi_mute_router.prefix} com {len(kpi_mute_router.routes)} rotas (admin-only, Smart Defaults camada 1)")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router KPI Mute: {e}", exc_info=True)

# Fase 1 thresholds (2026-08-04): overrides globais por KPI (admin CRUD)
try:
    from api.routers.kpi_thresholds import router as kpi_thresholds_router
    app.include_router(kpi_thresholds_router)
    logger.info(f"✅ Router KPI Thresholds carregado: {kpi_thresholds_router.prefix} com {len(kpi_thresholds_router.routes)} rotas (Fase 1, overrides globais)")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router KPI Thresholds: {e}", exc_info=True)

try:
    from api.routers.os_performance import router as os_performance_router
    app.include_router(os_performance_router)
    logger.info(f"✅ Router OS Performance carregado: {os_performance_router.prefix} com {len(os_performance_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router OS Performance: {e}", exc_info=True)

try:
    from api.routers.users import router as users_router
    app.include_router(users_router)
    logger.info(f"✅ Router Users Analysis carregado: {users_router.prefix} com {len(users_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Users Analysis: {e}", exc_info=True)

try:
    from api.routers.jobs import router as jobs_router
    app.include_router(jobs_router)
    logger.info(f"✅ Router Jobs Analysis carregado: {jobs_router.prefix} com {len(jobs_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Jobs Analysis: {e}", exc_info=True)

try:
    from modules.monitoring.dashboard_api import router as dashboard_api_router
    app.include_router(dashboard_api_router)
    logger.info(f"✅ Router Dashboard API carregado com {len(dashboard_api_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Dashboard API: {e}", exc_info=True)

try:
    from api.routers.kpis_metadata import router as kpis_metadata_router
    app.include_router(kpis_metadata_router)
    logger.info(f"✅ Router KPI Metadata carregado: {kpis_metadata_router.prefix} com {len(kpis_metadata_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router KPI Metadata: {e}", exc_info=True)

try:
    from api.routers.overview_dashboard import router as overview_dashboard_router
    app.include_router(overview_dashboard_router)
    logger.info(f"✅ Router Overview Dashboard carregado: {overview_dashboard_router.prefix} com {len(overview_dashboard_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Overview Dashboard: {e}", exc_info=True)

try:
    from api.routers.disk_unallocated import router as disk_unallocated_router
    app.include_router(disk_unallocated_router, prefix="/api")
    logger.info(f"✅ Router Disk Unallocated carregado: /api{disk_unallocated_router.prefix} com {len(disk_unallocated_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Disk Unallocated: {e}", exc_info=True)

try:
    from api.routers.database_discovery import router as database_discovery_router
    app.include_router(database_discovery_router, prefix="/api")
    logger.info(f"✅ Router Database Discovery carregado: /api{database_discovery_router.prefix} com {len(database_discovery_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Database Discovery: {e}", exc_info=True)

# 🔐 AUTHENTICATION ROUTER (V3.1 — database-backed com preferences sync)
try:
    from api.routers.auth_compat import router as auth_compat_router
    app.include_router(auth_compat_router)
    logger.info(f"✅ Router Auth V3.1 carregado: {auth_compat_router.prefix} com {len(auth_compat_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Auth V3.1: {e}", exc_info=True)
    # Fallback: router antigo in-memory
    try:
        from watcherdb.api.auth_router import router as auth_router
        app.include_router(auth_router)
        logger.warning(f"⚠ Fallback para router Auth antigo (in-memory): {auth_router.prefix}")
    except Exception as e2:
        logger.error(f"❌ Erro ao carregar router Auth fallback: {e2}", exc_info=True)

# 🆕 NOVOS ROUTERS - Resolução de Problemas Críticos (2026-02-20)
try:
    from watcherdb.api.routers.security import router as security_router
    app.include_router(security_router)
    logger.info(f"✅ Router Security Analysis carregado: {security_router.prefix} com {len(security_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Security Analysis: {e}", exc_info=True)

try:
    from watcherdb.api.routers.windows import router as windows_router
    app.include_router(windows_router)
    logger.info(f"✅ Router Windows Metrics carregado: {windows_router.prefix} com {len(windows_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Windows Metrics: {e}", exc_info=True)

try:
    from watcherdb.api.routers.alerts_unified import router as alerts_unified_router
    app.include_router(alerts_unified_router)
    logger.info(f"✅ Router Alerts Unified carregado: {alerts_unified_router.prefix} com {len(alerts_unified_router.routes)} rotas")
    logger.warning("⚠️  DEPRECATION: Endpoints individuais de alertas (/backup/alerts, /cpu/alerts, etc.) serão removidos em versão futura. Use /alerts/unified")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Alerts Unified: {e}", exc_info=True)

try:
    from watcherdb.api.routers.admin_metrics import router as admin_metrics_router
    app.include_router(admin_metrics_router)
    logger.info(f"✅ Router Admin Metrics carregado: {admin_metrics_router.prefix} com {len(admin_metrics_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Admin Metrics: {e}", exc_info=True)

try:
    from api.routers.network_diagnostics import router as network_diagnostics_router
    app.include_router(network_diagnostics_router)
    logger.info(f"✅ Router Network Diagnostics carregado: {network_diagnostics_router.prefix} com {len(network_diagnostics_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Network Diagnostics: {e}", exc_info=True)

# [V3.3 zero AI policy 2026-05-05 FIND-013-B] Copilot router NAO registado em V3.3 build.
# V3.3 = zero AI canonical (DBA Lead 2026-04-28). Copilot e Pro-only (V6+).
# Source mantido em api/routers/copilot.py para paridade V6+ Pro.
# try:
#     from api.routers.copilot import router as copilot_router
#     app.include_router(copilot_router)
#     logger.info(f"✅ Router Copilot carregado: {copilot_router.prefix} com {len(copilot_router.routes)} rotas")
# except Exception as e:
#     logger.error(f"❌ Erro ao carregar router Copilot: {e}", exc_info=True)

try:
    from api.routers.htmx import router as htmx_router
    app.include_router(htmx_router)
    logger.info(f"✅ Router HTMX Partials carregado: {htmx_router.prefix} com {len(htmx_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router HTMX Partials: {e}", exc_info=True)

try:
    from api.routers.live_monitoring import router as live_monitoring_router
    app.include_router(live_monitoring_router)
    logger.info(f"✅ Router LIVE Monitoring carregado: {live_monitoring_router.prefix} com {len(live_monitoring_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router LIVE Monitoring: {e}", exc_info=True)


# Alert Routing (S3-14 — audit 2026-04-22)
try:
    from api.routers.alert_routing import router as alert_routing_router
    from modules.alerts.dispatcher import AlertDispatcher
    from modules.alerts.config_loader import load_alert_config
    from modules.alerts.channels.log_channel import LogChannel
    from modules.alerts.channels.email_channel import EmailChannel
    from modules.alerts.channels.teams_channel import TeamsChannel
    from modules.alerts.channels.slack_channel import SlackChannel

    _alert_cfg = load_alert_config()
    _channels = [LogChannel()]  # sempre activo

    if _alert_cfg.get("email", {}).get("enabled"):
        _channels.append(EmailChannel(_alert_cfg["email"]))
    if _alert_cfg.get("teams", {}).get("enabled"):
        _channels.append(TeamsChannel(_alert_cfg["teams"]))
    if _alert_cfg.get("slack", {}).get("enabled"):
        _channels.append(SlackChannel(_alert_cfg["slack"]))

    app.state.alert_dispatcher = AlertDispatcher(
        channels=_channels,
        dedup_windows=_alert_cfg.get("dedup_windows"),
    )
    app.include_router(alert_routing_router)
    logger.info(
        f"✅ Router Alert Routing carregado: {alert_routing_router.prefix} "
        f"com {len(alert_routing_router.routes)} rotas, "
        f"channels configurados: {app.state.alert_dispatcher.configured_channels}"
    )
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Alert Routing: {e}", exc_info=True)


# Security Headers — HSTS, X-Frame-Options, CSP, Permissions-Policy
from watcherdb.core.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# GZip compression — reduz 70-85% do tamanho das respostas JSON
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — reads allowed_origins from config/config.yaml
from watcherdb.core.cors import get_cors_config
app.add_middleware(CORSMiddleware, **get_cors_config())

# API Deprecation headers for unversioned legacy endpoints
from starlette.middleware.base import BaseHTTPMiddleware


class APIDeprecationMiddleware(BaseHTTPMiddleware):
    """Add Deprecation header to unversioned API endpoints."""

    DEPRECATED_PREFIXES = ["/api/monitoring/", "/api/alwayson/", "/api/network/"]

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        for prefix in self.DEPRECATED_PREFIXES:
            if path.startswith(prefix):
                response.headers["Deprecation"] = "true"
                response.headers["Sunset"] = "2026-09-30"
                response.headers["Link"] = f'</api/v3{path[4:]}>; rel="successor-version"'
                break
        return response


app.add_middleware(APIDeprecationMiddleware)

# =============================================================================
# AuthEnforcementMiddleware — audit 2026-04-22 FIND #1 / P0-3
# =============================================================================
# Aplica _require_auth globalmente a todos os endpoints EXCEPTO allowlist de
# paths publicos (health, login, static, etc.). Resolve finding que mostrava
# ~170 endpoints de dados acessiveis sem token. Middleware outermost — roda
# primeiro no pipeline, rejeita unauthenticated em 401 antes de qualquer
# lookup de BD. Para 401, a resposta nao passa pelos outros middlewares
# (SecurityHeaders/GZip/CORS) porque middleware returna sem chamar call_next;
# aceitavel porque 401 body tem zero content sensivel.
# =============================================================================
from api.routers.auth_compat import (
    _get_token_from_request as _auth_get_token,
    _require_auth as _auth_require,
    _token_blacklist as _auth_blacklist,
)
from services.auth_service import get_auth_service as _auth_get_service

_AUTH_PUBLIC_PATHS = frozenset({
    "/",
    # HOTFIX-2 2026-04-23: AUTH_PREFIX em api/versioning.py:23 e "/api/auth"
    # (nao "/api/v3/auth" como inicialmente assumi). Endpoints legacy sem /v3
    # eram os correctos. P0-3 inicial assumiu /v3 sem confirmar — por isso o
    # login nao conseguia furar o middleware e redirecionava a 401 em loop.
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/validate",        # chamado pelo checkAuthOnLoad (cookie check)
    "/api/v3/health",            # este esta em /v3 (app.get direct, linha 1304)
    "/healthz",                  # liveness probe minimo -- so {"status":"alive"}, zero dados
    "/favicon.ico",
    "/favicon.svg",
    "/login.html",
    "/.well-known/appspecific/com.chrome.devtools.json",
    # HOTFIX 2026-04-23: SPA shell paths tem de ser publicos — servem HTML
    # que CONTEM o formulario de login (overlay dentro do shell). Se o
    # middleware bloqueasse, utilizador nunca chegaria ao login form.
    # Auth real e enforcada nos endpoints /api/* que o SPA chama depois.
    "/monitoring",
    "/portal-vanilla",
    "/portal-corrected",
    "/watcherdb",
    "/watcherdb/v2",
    "/watcherdb/control",
})

_AUTH_PUBLIC_PREFIXES = (
    "/static/",
    "/ws",  # WebSocket autentica via query param token (ver websocket_endpoint)
)


class AuthEnforcementMiddleware(BaseHTTPMiddleware):
    """Global auth enforcement for all non-public HTTP endpoints."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        # Fast-path: allowlist bypass
        if path in _AUTH_PUBLIC_PATHS:
            return await call_next(request)
        for prefix in _AUTH_PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)
        # Enforce auth
        token = _auth_get_token(request)
        if not token:
            return JSONResponse(
                {"detail": "Token nao fornecido"}, status_code=401
            )
        if token in _auth_blacklist:
            return JSONResponse(
                {"detail": "Token revogado"}, status_code=401
            )
        service = _auth_get_service()
        user = await service.get_current_user(token)
        if not user:
            return JSONResponse(
                {"detail": "Token invalido ou expirado"}, status_code=401
            )
        # Attach user to request.state para endpoints que nao usam Depends(_require_auth)
        request.state.user = user
        return await call_next(request)


app.add_middleware(AuthEnforcementMiddleware)

# CSRF same-site (lote 2026-09-05): Origin presente e fora de {scheme://host} U CORS
# allow_origins => 403 em POST/PUT/PATCH/DELETE. Registado DEPOIS do AuthEnforcement =>
# corre ANTES dele (ultimo add_middleware e' o mais exterior). Politica e justificacao
# em watcherdb/core/same_origin.py.
from watcherdb.core.same_origin import SameOriginMiddleware
app.add_middleware(SameOriginMiddleware)

# === WEBSOCKET ENDPOINTS ===

websocket_manager = WebSocketManager()


async def _ws_heartbeat(ws: WebSocket, manager):
    """Send ping every 30s to detect dead connections"""
    try:
        while True:
            await asyncio.sleep(30)
            await manager.send_to_websocket(ws, {'type': 'ping', 'timestamp': time.time()})
    except Exception:
        pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint para comunicação em tempo real (authenticated)"""
    # Authenticate via token query parameter
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return

    from services.auth_service import decode_token
    user = decode_token(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await websocket_manager.connect(websocket)
    heartbeat_task = asyncio.create_task(_ws_heartbeat(websocket, websocket_manager))

    try:
        while True:
            data = await websocket.receive_json()

            message_type = data.get('type')

            if message_type == 'subscribe':
                channel = data.get('channel')
                if channel:
                    await websocket_manager.subscribe(websocket, channel)

            elif message_type == 'ping':
                await websocket_manager.send_to_websocket(websocket, {
                    'type': 'pong',
                    'timestamp': time.time()
                })

            elif message_type == 'get_stats':
                if hasattr(app.state, 'inventory_manager'):
                    stats = app.state.inventory_manager.cache.get_stats()
                    await websocket_manager.send_to_websocket(websocket, {
                        'type': 'stats_update',
                        'data': stats
                    })

    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket_manager.disconnect(websocket)
    finally:
        heartbeat_task.cancel()

# === API ENDPOINTS ===

@app.get("/")
async def root():
    return {
        "message": "WatcherDB Monitoring System - Complete Fix",
        "version": "3.0.0-real-data",
        "status": "operational",
        "data_source": "YOUR REAL Excel file",
        "real_data_features": [
            "✅ Reads your actual TAP_SQL_Server_Inventory.xlsx",
            "✅ Smart column detection and mapping",
            "✅ Dynamic schema creation based on your data",
            "✅ Zero fictional/sample data",
            "✅ Intelligent Excel structure analysis",
            "✅ Support for multiple sheet formats"
        ],
        "implementations": [
            "✅ RedisLikeCache - Complete Redis implementation",
            "✅ AdvancedFuzzyMatcher - Multi-algorithm fuzzy matching",
            "✅ AsyncFileIO - Async file operations",
            "✅ EnhancedExcelParser - Smart Excel parsing with mapping",
            "✅ SmartSchemaManager - Dynamic schema based on real data",
            "✅ All features using YOUR real data only"
        ]
    }

@app.get("/favicon.ico")
async def favicon():
    """Retorna o favicon SVG como ICO (fallback para navegadores antigos)"""
    favicon_path = _static("favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(
            favicon_path, 
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "public, max-age=31536000",
                "Content-Type": "image/svg+xml"
            }
        )
    return Response(status_code=204)

@app.get("/favicon.svg")
async def favicon_svg():
    """Retorna o favicon SVG do Watcher DB"""
    favicon_path = _static("favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(
            favicon_path, 
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "public, max-age=31536000",
                "Content-Type": "image/svg+xml"
            }
        )
    return Response(status_code=404)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools():
    """Retorna 204 No Content para evitar erro 404"""
    return Response(status_code=204)

@app.get("/api/monitoring/backup/server/{server_id}/why-log-not-run")
async def api_backup_why_log_not_run(server_id: str, database: str, at: str, tolerance_minutes: int = 60):
    """
    Explica por que um backup de LOG aparenta não ter rodado em um horário específico.
    
    INTELIGENTE: Usa análise de padrões para determinar frequência esperada do LOG.
    
    Regras:
    - Primeiro busca o padrão de LOG da database para determinar frequência esperada
    - Se havia FULL ou DIFF em execução (sobreposição) no horário informado -> reason = 'full_or_diff_running'
    - Se houve LOG próximo ao horário (dentro da tolerância) -> reason = 'within_tolerance'
    - Se o recovery model não requer LOG -> reason = 'recovery_model_simple'
    - Se não deveria ter rodado baseado no padrão -> reason = 'not_expected'
    - Caso contrário -> reason = 'missing'
    
    Params:
      - database: nome da database (ex.: 'model')
      - at: datetime ISO ou 'YYYY-MM-DD HH:MM:SS' no horário do servidor SQL
      - tolerance_minutes: janela para considerar LOG próximo (default: 60)
    """
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return JSONResponse(status_code=500, content={"success": False, "error": "sql_monitoring não inicializado"})
        
        # Normalizar datetime
        from datetime import datetime, timedelta
        at_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                at_dt = datetime.strptime(at, fmt)
                break
            except Exception:
                continue
        if at_dt is None:
            return JSONResponse(status_code=400, content={"success": False, "error": "Formato de data inválido. Use YYYY-MM-DD HH:MM:SS"})
        
        win_start = (at_dt - timedelta(minutes=tolerance_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        win_end   = (at_dt + timedelta(minutes=tolerance_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        at_str    = at_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # 0) Buscar padrão de LOG da database para determinar frequência esperada
        log_pattern = None
        expected_interval_hours = None
        try:
            # Buscar padrões da database
            patterns_res = await api_backup_patterns(server_id, days=30)
            if patterns_res.get("success") and patterns_res.get("databases"):
                db_patterns = patterns_res["databases"].get(database, {})
                log_pattern = db_patterns.get("LOG", {})
                expected_interval_hours = log_pattern.get("interval_hours")  # Intervalo real observado
                if not expected_interval_hours:
                    expected_interval_hours = log_pattern.get("expected_interval_hours")  # Intervalo esperado padrão
        except Exception as e:
            logger.warning(f"Erro ao buscar padrão de LOG para {database}: {e}")
        
        # 1) Verificar recovery model
        rm_query = """
            SELECT recovery_model_desc
            FROM sys.databases
            WHERE name = ?;
        """
        rm_res = await sql_mon.execute_query(server_id, rm_query, params=[database])
        if not rm_res or not rm_res.get("success"):
            return JSONResponse(status_code=500, content={"success": False, "error": rm_res.get("error", "query-failed")})
        rows = rm_res.get("rows", [])
        recovery_model = rows[0].get("recovery_model_desc") if rows else None
        if recovery_model and recovery_model.upper() == "SIMPLE":
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "database": database,
                "at": at_str,
                "recovery_model": recovery_model,
                "reason": "recovery_model_simple",
                "message": "Recovery Model SIMPLE não requer backups de LOG. LOG pode não ocorrer durante FULL/DIFF."
            })
        
        # 1.5) Verificar se deveria ter rodado baseado no padrão detectado
        should_have_run = True
        if expected_interval_hours:
            # Buscar último LOG antes do horário consultado
            last_log_query = """
                SELECT TOP 1 bs.backup_finish_date
                FROM msdb.dbo.backupset bs
                WHERE bs.database_name = ?
                  AND bs.type = 'L'
                  AND bs.backup_finish_date < CONVERT(datetime, ?)
                ORDER BY bs.backup_finish_date DESC;
            """
            last_log_res = await sql_mon.execute_query(server_id, last_log_query, params=[database, at_str])
            if last_log_res and last_log_res.get("success") and last_log_res.get("rows"):
                last_log_dt = last_log_res["rows"][0].get("backup_finish_date")
                if isinstance(last_log_dt, str):
                    try:
                        last_log_dt = datetime.strptime(last_log_dt.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        pass

                if isinstance(last_log_dt, datetime):
                    hours_since_last = (at_dt - last_log_dt).total_seconds() / 3600.0
                    # Se ainda não passou o intervalo esperado, não deveria ter rodado
                    if hours_since_last < expected_interval_hours * 0.8:  # 80% do intervalo (tolerância)
                        should_have_run = False
                        return JSONResponse(content={
                            "success": True,
                            "server_id": server_id,
                            "database": database,
                            "at": at_str,
                            "recovery_model": recovery_model,
                            "reason": "not_expected",
                            "log_pattern": {
                                "interval_hours": expected_interval_hours,
                                "last_log": str(last_log_dt),
                                "hours_since_last": round(hours_since_last, 1)
                            },
                            "message": f"Baseado no padrão detectado (LOG a cada {expected_interval_hours}h), não era esperado um LOG neste horário. Último LOG foi há {round(hours_since_last, 1)}h."
                        })
        
        # 2) Verificar sobreposição com FULL/DIFF
        overlap_query = """
            SELECT TOP 1 bs.type, bs.backup_start_date, bs.backup_finish_date
            FROM msdb.dbo.backupset bs
            WHERE bs.database_name = ?
              AND bs.type IN ('D','I') -- FULL, DIFF
              AND bs.backup_start_date <= CONVERT(datetime, ?)
              AND bs.backup_finish_date >= CONVERT(datetime, ?)
            ORDER BY bs.backup_finish_date DESC;
        """
        overlap_res = await sql_mon.execute_query(server_id, overlap_query, params=[database, at_str, at_str])
        if overlap_res and overlap_res.get("success") and overlap_res.get("rows"):
            row = overlap_res["rows"][0]
            kind = "FULL" if row.get("type") == "D" else "DIFF"
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "database": database,
                "at": at_str,
                "recovery_model": recovery_model,
                "reason": "full_or_diff_running",
                "blocking_backup": kind,
                "backup_window": {
                    "start": str(row.get("backup_start_date")),
                    "finish": str(row.get("backup_finish_date"))
                },
                "message": f"Backup de {kind} estava em execução, logo não houve LOG no horário."
            })
        
        # 3) Verificar se houve LOG próximo (dentro da tolerância)
        log_near_query = """
            SELECT TOP 1 bs.backup_finish_date
            FROM msdb.dbo.backupset bs
            WHERE bs.database_name = ?
              AND bs.type = 'L'
              AND bs.backup_finish_date BETWEEN CONVERT(datetime, ?) AND CONVERT(datetime, ?)
            ORDER BY bs.backup_finish_date DESC;
        """
        log_near_res = await sql_mon.execute_query(server_id, log_near_query, params=[database, win_start, win_end])
        if log_near_res and log_near_res.get("success") and log_near_res.get("rows"):
            dt = log_near_res["rows"][0].get("backup_finish_date")
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "database": database,
                "at": at_str,
                "recovery_model": recovery_model,
                "reason": "within_tolerance",
                "nearest_log_finish": str(dt),
                "tolerance_minutes": tolerance_minutes,
                "message": "Há backup de LOG próximo ao horário consultado (dentro da tolerância)."
            })
        
        # 4) Verificar se houve FULL/DIFF muito próximo (até 90 min) — pode explicar ausência de LOG imediato
        near_fd_query = """
            SELECT TOP 1 bs.type, bs.backup_finish_date
            FROM msdb.dbo.backupset bs
            WHERE bs.database_name = ?
              AND bs.type IN ('D','I')
              AND ABS(DATEDIFF(MINUTE, bs.backup_finish_date, CONVERT(datetime, ?))) <= 90
            ORDER BY ABS(DATEDIFF(MINUTE, bs.backup_finish_date, CONVERT(datetime, ?))) ASC;
        """
        near_fd_res = await sql_mon.execute_query(server_id, near_fd_query, params=[database, at_str, at_str])
        if near_fd_res and near_fd_res.get("success") and near_fd_res.get("rows"):
            row = near_fd_res["rows"][0]
            kind = "FULL" if row.get("type") == "D" else "DIFF"
            return JSONResponse(content={
                "success": True,
                "server_id": server_id,
                "database": database,
                "at": at_str,
                "recovery_model": recovery_model,
                "reason": "recent_full_or_diff",
                "recent_backup": kind,
                "recent_finish": str(row.get("backup_finish_date")),
                "message": f"Houve {kind} próximo do horário; LOG pode ser postergado ou pulado."
            })
        
        # Sem explicação clara
        response = {
            "success": True,
            "server_id": server_id,
            "database": database,
            "at": at_str,
            "recovery_model": recovery_model,
            "reason": "missing",
            "message": "Não foi encontrado LOG no horário/tolerância e não havia FULL/DIFF sobrepondo."
        }
        
        # Adicionar informações do padrão se disponível
        if log_pattern:
            response["log_pattern"] = {
                "interval_hours": expected_interval_hours,
                "hour_of_day": log_pattern.get("hour_of_day"),
                "last_backup": log_pattern.get("last_backup")
            }
            if expected_interval_hours:
                response["message"] += f" Padrão detectado: LOG a cada {expected_interval_hours}h."
        
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"why-log-not-run error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/api/v3/inventory")
async def get_inventory():
    """Get complete inventory using REAL data from Excel with all TAP fields"""
    try:
        servers = await app.state.inventory_manager.load_complete_inventory()
        
        return {
            'success': True,
            'total_servers': len(servers),
            'timestamp': datetime.now().isoformat(),
            'implementation': 'WatcherDB Monitoring System v3.0.0',
            'data_source': 'Your SQL Server inventory spreadsheet',
            'servers': [
                {
                    'id': f"{s.server_name}_{s.instance_name}",
                    'name': f"{s.server_name}\\{s.instance_name}" if s.instance_name != "DEFAULT" else s.server_name,
                    'server': s.server_name,
                    'instance': s.instance_name,
                    'environment': s.environment,
                    'location': s.location,
                    'status': s.status,
                    'health_score': s.health_score,
                    'alerts_count': s.alerts_count,
                    'database_engine': s.database_engine,
                    'description': s.description,
                    'response_time_ms': s.response_time_ms,
                    # TAP-specific fields
                    'ag_name': s.ag_name,
                    'criticality': s.criticality,
                    'backup_strategy': s.backup_strategy,
                    'listeners': s.listeners,
                    'business_area': s.business_area
                }
                for s in servers
            ]
        }
    except Exception as e:
        logger.error(f"Error in get_inventory: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/server-info")
async def get_server_info():
    """Retorna informações sobre qual tipo de servidor está rodando"""
    # rbac_live_admin_only: o portal precisa de saber se o gate esta ligado para
    # esconder LIVE a um viewer em vez de o deixar clicar e apanhar 403 em cada
    # painel (UX enganadora que o QA externo apontou noutro contexto). Nao e'
    # informacao sensivel — e' a politica, nao os dados.
    try:
        from api.routers.live_monitoring import _rbac_live_enabled
        rbac_live = _rbac_live_enabled()
    except Exception:
        rbac_live = False
    return JSONResponse(content={
        "server_type": "intelligence",
        "kpi_source": "Intelligence",
        "kpi_endpoint": "/api/intelligence-kpis/dashboard",
        "description": "WatcherDB Intelligence - KPIs from SQL Server Intelligence schema",
        "rbac_live_admin_only": rbac_live
    })

@app.get("/api/v3/servers")
async def get_servers_list():
    """Lista de servidores para o portal (sidebar).

    E6 (plano servers.json fonte unica, 2026-08-19): a fonte passa a ser
    metadata.monitored_server(+_database) na Intelligence via
    services.inventory_repo (alimentada pelo collector V1 a partir do
    servers.json canonico). Fallback automatico ao config/servers.json local
    se a BD falhar/vier vazia; settings.inventory_source="file" = rollback.
    Contrato de saida inalterado (server_id, name, instance_name, environment,
    location, status, description, databases[], database_count, match_score).
    """
    try:
        from services.inventory_repo import get_inventory_repo
        repo = get_inventory_repo()
        # require_credentials: servidor na BD sem entrada no servers.json local nao tem como
        # ser consultado (connection_pool) -> fica fora da sidebar ate ter creds (log [INVENTORY_REPO]).
        monitored = repo.servers(enabled_only=False, require_credentials=True)
        inv_source = repo.source
        if not monitored:
            return {'success': False, 'error': 'inventario vazio (BD e ficheiro local)', 'source': inv_source}

        items = []
        for sc in monitored:
            try:
                # Filtrar servidores desabilitados
                if not sc.get('enabled', True):
                    continue

                server_id = sc.get('id', '')
                if not server_id:
                    continue

                host = sc.get('host', '')
                instance = sc.get('instance', '')

                # Display name
                if instance:
                    display_name = f"{host}\\{instance}"
                else:
                    display_name = host

                # Databases - extrair nomes
                databases = sc.get('databases', [])
                if databases and isinstance(databases[0], dict):
                    db_names = [d.get('name', '') for d in databases if d.get('name')]
                else:
                    db_names = databases if isinstance(databases, list) else []

                items.append({
                    'server_id': server_id,
                    'name': display_name,
                    'instance_name': instance or 'DEFAULT',
                    'environment': sc.get('environment', 'production'),
                    'location': sc.get('location', ''),
                    'status': 'ACTIVE',
                    'description': sc.get('description', ''),
                    'databases': db_names,
                    'database_count': sc.get('database_count', len(db_names)),
                    'match_score': 1.0
                })
            except Exception:
                continue

        logger.info(f"[DEBUG] /api/v3/servers -> {len(items)} servers (source={inv_source})")
        return {'success': True, 'servers': items, 'source': inv_source}
    except Exception as e:
        logger.error(f"Error in get_servers_list: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/config/sql-servers")
async def get_sql_servers_config():
    """Lê o arquivo sql_servers.json de configuração"""
    try:
        config_path = SQL_SERVERS_CONFIG_PATH
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="Arquivo sql_servers.json não encontrado")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return config
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear sql_servers.json: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler arquivo de configuração: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao ler sql_servers.json: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler arquivo de configuração: {str(e)}")

@app.post("/api/config/sql-servers")
async def save_sql_servers_config(config: dict, request: Request):
    """Salva o arquivo sql_servers.json de configuracao — dba ou admin.

    Decisao do owner 2026-08-16: o inventario de servidores monitorizados e
    operacao de DBA (quem adiciona uma instancia nova e quem a vai monitorizar),
    nao governanca do produto. `viewer` continua barrado."""
    from api.routers.auth_compat import _require_dba
    _actor = await _require_dba(request)  # 403 se role for viewer
    try:
        config_path = SQL_SERVERS_CONFIG_PATH
        
        # Validar estrutura básica
        if 'servers' not in config:
            raise HTTPException(status_code=400, detail="Estrutura inválida: 'servers' não encontrado")
        
        # Fazer backup do arquivo original
        backup_path = config_path.with_suffix('.json.backup')
        if config_path.exists():
            import shutil
            shutil.copy2(config_path, backup_path)
            logger.info(f"Backup criado: {backup_path}")
        
        # Salvar novo arquivo
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        
        logger.info(f"Configuração sql_servers.json salva com sucesso ({len(config.get('servers', []))} servidores)")

        # Auditoria: alterar o inventario de servidores monitorizados e uma escrita
        # sensivel e ate agora so deixava rasto no log de ficheiro. O QA externo
        # (2026-08-16 §10.5) pediu que ficasse emparelhada com rasto de auditoria.
        try:
            from services.auth_service import get_auth_service as _gas
            _gas()._log_auth(
                (_actor or {}).get("username", "?"), "SQL_SERVERS_CONFIG_SAVED",
                request.client.host if request.client else None,
                f"{len(config.get('servers', []))} servidores gravados",
            )
        except Exception:
            pass  # auditoria nunca deve impedir a gravacao

        # --- SYNC sql_servers.json -> servers.json (sidebar + dashboards) ---
        # A modal edita sql_servers.json mas a sidebar le servers.json (monitored_servers[]).
        # Modelo de sync: UPSERT (insert + update) + DELETE cascade.
        #   - INSERT: id em sql nao em inv -> adicionar com defaults seguros (Windows Auth)
        #   - UPDATE: id em ambos -> propagar campos basicos (description, port, environment,
        #             priority, enabled). Preservar campos sensiveis (password, username,
        #             use_windows_auth, has_alwayson, ag_name, ag_listener, databases).
        #             Imutaveis pos-criacao: host, instance (mudar = servidor diferente).
        #   - DELETE: id em inv nao em sql -> remover entry (com backup pre-sync seguro).
        # Fail-open: se o sync falhar, o save de sql_servers.json ja foi confirmado.
        synced = 0   # INSERT count
        updated = 0  # UPDATE count
        removed = 0  # DELETE count
        try:
            if SERVERS_INVENTORY_PATH.exists():
                with open(SERVERS_INVENTORY_PATH, 'r', encoding='utf-8') as f:
                    inv_data = json.load(f)

                monitored = inv_data.get('monitored_servers', [])
                sql_by_id = {s.get('id'): s for s in config.get('servers', []) if s.get('id')}

                # 1. DELETE — entries em inv mas que sumiram de sql
                new_monitored = []
                for entry in monitored:
                    eid = entry.get('id')
                    if eid and eid not in sql_by_id:
                        removed += 1
                        continue  # nao adiciona a new_monitored = delete efectivo
                    new_monitored.append(entry)

                # 2. UPDATE — para cada id em ambos, propagar campos basicos
                # NOTA: 'port' deliberadamente EXCLUIDO — port e' config de rede que
                # operadores definem explicitamente em servers.json (named instances,
                # port redirects). sql_servers.json ter 1433 default nao deve sobrescrever.
                _UPDATABLE_FIELDS = ('description', 'environment', 'priority', 'enabled')
                for entry in new_monitored:
                    eid = entry.get('id')
                    sql_entry = sql_by_id.get(eid)
                    if not sql_entry:
                        continue
                    entry_changed = False
                    for field in _UPDATABLE_FIELDS:
                        if field not in sql_entry:
                            continue  # campo ausente em sql -> preservar valor actual em inv
                        if entry.get(field) != sql_entry.get(field):
                            entry[field] = sql_entry.get(field)
                            entry_changed = True
                    if entry_changed:
                        updated += 1

                # 3. INSERT — entries em sql mas nao em inv (apos DELETE applied)
                existing_ids_after_delete = {e.get('id') for e in new_monitored if e.get('id')}
                for srv in config.get('servers', []):
                    sid = srv.get('id')
                    if not sid or sid in existing_ids_after_delete:
                        continue
                    new_monitored.append({
                        'id': sid,
                        'host': srv.get('host', ''),
                        'instance': srv.get('instance', ''),
                        'port': srv.get('port', 1433),
                        'description': srv.get('description', ''),
                        'environment': srv.get('environment', 'production'),
                        'priority': srv.get('priority', 5),
                        'enabled': srv.get('enabled', True),
                        'use_windows_auth': True,  # default seguro — admin ajusta para SQL Auth se necessario
                        'username': '',
                        'password': '',
                        'driver': 'SQL Server',
                        'has_alwayson': False,
                        'ag_name': None,
                        'ag_listener': None,
                        'databases': srv.get('databases', []),
                        'database_count': srv.get('database_count', 0),
                    })
                    existing_ids_after_delete.add(sid)
                    synced += 1

                # Escrever apenas se houve mudanca (idempotente em saves repetidos)
                if synced > 0 or updated > 0 or removed > 0:
                    inv_backup = SERVERS_INVENTORY_PATH.with_suffix('.json.backup_pre_sync')
                    import shutil as _shutil
                    _shutil.copy2(SERVERS_INVENTORY_PATH, inv_backup)
                    inv_data['monitored_servers'] = new_monitored
                    with open(SERVERS_INVENTORY_PATH, 'w', encoding='utf-8') as f:
                        json.dump(inv_data, f, indent=2, ensure_ascii=False)
                    logger.info(
                        f"servers.json sync: +{synced} insert / ~{updated} update / -{removed} delete "
                        f"(total {len(new_monitored)} entries em monitored_servers)"
                    )
        except Exception as sync_err:
            logger.warning(f"Falha ao sincronizar servers.json (nao bloqueante): {sync_err}")
        # --- FIM SYNC ---

        return {
            'success': True,
            'message': f'Configuração salva com sucesso ({len(config.get("servers", []))} servidores)',
            'synced_to_inventory': synced,
            'updated_in_inventory': updated,
            'removed_from_inventory': removed,
        }
    except json.JSONEncodeError as e:
        logger.error(f"Erro ao serializar sql_servers.json: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo de configuração: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao salvar sql_servers.json: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo de configuração: {str(e)}")

@app.get("/api/config/custom-queries")
async def get_custom_queries():
    """Lê o arquivo custom_queries.json de configuração"""
    try:
        config_path = _CONFIG_DIR / "custom_queries.json"
        if not config_path.exists():
            # Retornar array vazio se o arquivo não existir
            return []
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Filtrar apenas queries habilitadas
        enabled_queries = [q for q in config if q.get('enabled', True)]
        return enabled_queries
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear custom_queries.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Erro ao ler custom_queries.json: {e}")
        return []

@app.post("/api/config/custom-queries")
async def save_custom_queries(request: Request):
    """Salva o arquivo custom_queries.json de configuração"""
    from api.routers.auth_compat import _require_admin
    await _require_admin(request)
    try:
        # Ler body como JSON
        body = await request.json()
        queries = body if isinstance(body, list) else []
        
        config_path = _CONFIG_DIR / "custom_queries.json"
        
        # Validar estrutura básica
        if not isinstance(queries, list):
            raise HTTPException(status_code=400, detail="Estrutura inválida: deve ser uma lista")
        
        # Permitir lista vazia (para quando todas as queries são excluídas)
        if len(queries) == 0:
            logger.info("Salvando lista vazia de queries customizadas")
        else:
            # Validar cada query
            for idx, query in enumerate(queries):
                if not isinstance(query, dict):
                    raise HTTPException(status_code=400, detail=f"Query {idx}: deve ser um objeto/dicionário")
                
                required_fields = ['id', 'name', 'sql']
                for field in required_fields:
                    if field not in query or not query[field]:
                        raise HTTPException(status_code=400, detail=f"Query {idx} inválida: campo '{field}' obrigatório e não pode estar vazio")
                
                # Garantir que campos opcionais existam com valores padrão
                if 'enabled' not in query:
                    query['enabled'] = True
                if 'requiresDb' not in query:
                    query['requiresDb'] = False
                if 'description' not in query:
                    query['description'] = ''
                if 'icon' not in query:
                    query['icon'] = 'fa-database'
        
        # Fazer backup do arquivo original
        backup_path = config_path.with_suffix('.json.backup')
        if config_path.exists():
            import shutil
            shutil.copy2(config_path, backup_path)
            logger.info(f"Backup criado: {backup_path}")
        
        # Salvar novo arquivo
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(queries, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Configuração custom_queries.json salva com sucesso ({len(queries)} queries)")
        
        return {'success': True, 'message': f'Configuração salva com sucesso ({len(queries)} queries)'}
    except json.JSONEncodeError as e:
        logger.error(f"Erro ao serializar custom_queries.json: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo de configuração: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao salvar custom_queries.json: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo de configuração: {str(e)}")

@app.post("/api/queries/custom/{server_id}")
async def execute_custom_query(server_id: str, query_data: dict):
    """Executa uma query SQL customizada em um servidor específico"""
    try:
        # Validar dados da query
        if 'sql' not in query_data:
            raise HTTPException(status_code=400, detail="Campo 'sql' obrigatório")
        
        sql = query_data['sql']
        database = query_data.get('database', None)
        
        # Substituir placeholders na query
        if database:
            sql = sql.replace('{database}', database)
            sql = sql.replace('{db}', database)
        
        # Substituir {server_id} se necessário
        sql = sql.replace('{server_id}', server_id)
        
        # Usar sql_monitoring do app.state (já inicializado com cache)
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            raise HTTPException(status_code=500, detail="SQL Monitoring não inicializado")
        
        # Se database foi especificado, adicionar USE database antes da query
        final_sql = sql
        if database:
            final_sql = f"USE [{database}];\n{final_sql}"
        
        logger.info(f"🔍 Executando query customizada para {server_id} (database: {database or 'master'})")
        
        # Executar query usando o método execute_query do SQLServerMonitoring
        # Este método já faz a busca do servidor no config internamente
        try:
            result = await sql_mon.execute_query(server_id, final_sql, database=database)
            
            if not result or not result.get('success'):
                error_msg = result.get('error', 'Erro desconhecido') if result else 'Erro ao executar query'
                logger.error(f"❌ Erro ao executar query: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Erro ao executar query: {error_msg}")
            
            # Extrair resultados
            rows = result.get('rows', [])
            
            # Extrair colunas dos resultados ou do primeiro row
            columns = []
            if rows and len(rows) > 0:
                columns = list(rows[0].keys())
            elif result.get('columns'):
                columns = result.get('columns', [])
            
            logger.info(f"✅ Query executada com sucesso: {len(rows)} linhas retornadas")
            
            return {
                'success': True,
                'columns': columns,
                'results': rows,
                'row_count': len(rows)
            }
        except HTTPException:
            raise
        except Exception as sql_err:
            logger.error(f"Erro ao executar query SQL: {sql_err}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Erro ao executar query: {str(sql_err)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao executar query customizada: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao executar query customizada: {str(e)}")

@app.get("/api/v3/search")
async def search_inventory(q: str, limit: int = 10):
    """Advanced fuzzy search using real data"""
    try:
        results = await app.state.inventory_manager.smart_search(q, limit)
        compat_results = []
        for r in results:
            try:
                s = r.get('instance')
                compat_results.append({
                    'server_id': f"{s.server_name}_{s.instance_name}",
                    'instance_name': s.instance_name,
                    'match_score': r.get('score'),
                    'match_type': r.get('match_type'),
                    'matched_term': r.get('matched_term')
                })
            except Exception:
                continue
        return {'success': True, 'results': compat_results}
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/v3/server/{server_name}")
async def get_real_data_server_details(server_name: str):
    """Get detailed server information from real data"""
    try:
        details = await app.state.inventory_manager.get_server_details(server_name)
        logger.info(f"[DEBUG] /api/v3/server/{server_name} -> details keys: {list(details.keys()) if isinstance(details, dict) else type(details)}")

        
        if not details:
            raise HTTPException(status_code=404, detail="Server not found in real data")
        
        return {
            'success': True,
            'server_details': details,
            'loaded_via': 'Real Excel data + Independent AsyncFileIO'
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting server details: {e}")
        return {'success': False, 'error': str(e)}

@app.get("/api/v3/cache/stats")
async def get_cache_stats():
    """Get Redis-like cache statistics"""
    try:
        stats = app.state.inventory_manager.cache.get_stats()
        return {
            'success': True,
            'cache_stats': stats,
            'cache_implementation': 'RedisLikeCache (Independent)',
            'features': [
                'TTL support',
                'LRU eviction',
                'Persistence',
                'Pub/Sub',
                'Background cleanup',
                'Memory management'
            ]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post("/api/v3/cache/clear")
async def clear_cache(request: Request, pattern: str = "*"):
    """Clear cache with pattern support"""
    from api.routers.auth_compat import _require_admin
    await _require_admin(request)
    try:
        if pattern == "*":
            success = app.state.inventory_manager.cache.flushall()
            message = "All cache cleared"
        else:
            keys = app.state.inventory_manager.cache.keys(pattern)
            for key in keys:
                app.state.inventory_manager.cache.delete(key)
            success = True
            message = f"Cleared {len(keys)} keys matching '{pattern}'"
        
        return {
            'success': success,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.get("/healthz")
async def healthz():
    """Liveness probe minimo (FIX 2026-07-23): zero I/O, zero DB. Responde 200
    em <1s sempre que o event loop esta vivo -- camada 4 do monitoramento
    pos-restart. Se /healthz pendura, o loop esta bloqueado (foi o sintoma do
    incidente 2026-07-23); se responde mas o dashboard nao, o problema e' DB."""
    return {"status": "alive", "service": "WatcherDBWebServiceV33"}


_VERSION_INFO_CACHE = None


def _read_version_info() -> dict:
    """Identidade do build (QA externo 2026-08-16: sem isto nao ha' forma de
    saber que versao esta' em PRD; '/' devolve placeholder). Fontes, por ordem:
    VERSION.txt ao lado do executavel/bundle (escrito por deploy/build.py) e,
    em checkout de fontes, git rev-parse (uma vez, cacheado). Nunca falha."""
    global _VERSION_INFO_CACHE
    if _VERSION_INFO_CACHE is not None:
        return _VERSION_INFO_CACHE
    info = {"product": "WatcherDB V3.3 Standard Edition", "version": None,
            "build": None, "git_sha": None, "protected": None,
            "frozen": bool(getattr(sys, "frozen", False)), "source": "unknown"}
    base = Path(sys.executable).resolve().parent if info["frozen"] \
        else Path(__file__).resolve().parent
    for cand in (base / "VERSION.txt", base / "_internal" / "VERSION.txt"):
        try:
            if cand.is_file():
                for line in cand.read_text(encoding="utf-8", errors="replace").splitlines():
                    k, _, v = line.partition(":")
                    k, v = k.strip().lower(), v.strip()
                    if k == "version": info["version"] = v
                    elif k == "build": info["build"] = v
                    elif k == "git": info["git_sha"] = v
                    elif k == "protected": info["protected"] = v
                    elif not _ and line.strip(): info["product"] = line.strip()
                info["source"] = "VERSION.txt"
                break
        except Exception:
            continue
    if not info["frozen"] and not info["git_sha"]:
        try:
            import subprocess
            sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(base),
                                 capture_output=True, text=True, timeout=3).stdout.strip()
            if sha:
                info["git_sha"] = sha
                if info["source"] == "unknown":
                    info["source"] = "git"
        except Exception:
            pass
    _VERSION_INFO_CACHE = info
    return info


@app.get("/api/version")
async def api_version():
    """Versao/build em execucao (VERSION.txt do bundle ou git sha em fontes)."""
    return _read_version_info()

def _auth_health_flags() -> dict:
    try:
        from services.auth_service import revogacao_por_reset_activa
        return revogacao_por_reset_activa()
    except Exception as e:  # pragma: no cover - health nunca cai por causa disto
        return {"reset_revocation": "unknown", "error": str(e)[:120]}


@app.get("/api/v3/health")
async def health_check():
    """Health check of real data system"""
    try:
        # Check components
        cache_healthy = True
        try:
            app.state.inventory_manager.cache.get("health_check")
            app.state.inventory_manager.cache.set("health_check", "ok", ttl=60)
        except Exception:
            cache_healthy = False
        
        file_io_healthy = True
        try:
            await app.state.inventory_manager.file_io.file_exists(".")
        except Exception:
            file_io_healthy = False
        
        inventory_healthy = True
        real_data_count = 0
        try:
            servers = await app.state.inventory_manager.load_complete_inventory()
            real_data_count = len(servers)
            inventory_healthy = real_data_count > 0
        except Exception:
            inventory_healthy = False
        
        overall_healthy = cache_healthy and file_io_healthy and inventory_healthy
        
        return {
            'success': True,
            'status': 'healthy' if overall_healthy else 'degraded',
            'timestamp': datetime.now().isoformat(),
            'real_data_servers': real_data_count,
            'components': {
                'cache': 'healthy' if cache_healthy else 'unhealthy',
                'file_io': 'healthy' if file_io_healthy else 'unhealthy', 
                'inventory': 'healthy' if inventory_healthy else 'unhealthy',
                'real_data': 'loaded' if real_data_count > 0 else 'no data found'
            },
            # P4 ronda 2 (2026-09-08): estado da revogacao de sessao por reset, observavel por GET.
            # Nunca faz o health falhar: erro na sondagem => "unknown".
            'auth': _auth_health_flags(),
            'implementation': 'WatcherDB Monitoring System v3.0.0 - Using YOUR Excel data only'
        }
        
    except Exception as e:
        return {
            'success': False,
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

@app.get("/api/v3/excel/analyze")
async def analyze_excel():
    """Analyze the Excel file structure"""
    try:
        if not app.state.inventory_manager.excel_path.exists():
            return {
                'success': False,
                'error': f'Excel file not found: {app.state.inventory_manager.excel_path}',
                'instruction': 'Please place your TAP_SQL_Server_Inventory.xlsx in the C:\\Server_Inventory directory'
            }
        
        analysis = app.state.inventory_manager.excel_parser.analyze_excel_structure(
            app.state.inventory_manager.excel_path
        )
        
        return {
            'success': True,
            'excel_analysis': analysis,
            'file_path': str(app.state.inventory_manager.excel_path),
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Excel analysis error: {e}")
        return {'success': False, 'error': str(e)}


# === MAIN ===



# ============================================================================
# SQL SERVER MONITORING - Endpoints
# ============================================================================

@app.get("/api/monitoring/servers")
async def get_all_servers_status():
    """
    Status de todos os servidores SQL
    Endpoint leve para dashboard
    """
    if not app.state.sql_monitoring:
        return {"error": "SQL Monitoring não inicializado"}
    
    try:
        from datetime import datetime
        results = await app.state.sql_monitoring.monitor_all_servers(
            categories=['health']
        )
        return {
            "timestamp": datetime.now().isoformat(),
            "total_servers": len(results),
            "servers": results
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/monitoring/server/{server_id}")
async def get_monitoring_server_details(server_id: str, categories: str = "all"):
    """
    Detalhes completos de um servidor específico
    
    Args:
        server_id: ID do servidor (ex: CAGENPRD06_I06)
        categories: Categorias separadas por vírgula ou "all"
                   (health,storage,performance,backups,jobs)
    """
    if not app.state.sql_monitoring:
        return {"error": "SQL Monitoring não inicializado"}
    
    try:
        cat_list = categories.split(',') if categories != 'all' else None
        result = await app.state.sql_monitoring.monitor_server(server_id, categories=cat_list)
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/monitoring/alerts")
async def get_active_alerts():
    """
    Alertas críticos de todos os servidores
    """
    if not app.state.sql_monitoring:
        return {"error": "SQL Monitoring não inicializado"}
    
    try:
        from datetime import datetime
        alerts = await app.state.sql_monitoring.get_critical_alerts()
        return {
            "timestamp": datetime.now().isoformat(),
            "alert_count": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/monitoring/ping/{hostname}")
async def ping_hostname(hostname: str):
    """
    Faz ping ICMP simples no hostname (apenas verifica se o servidor responde ao ping).
    Não verifica porta SQL Server.
    
    Retorna:
    - success: True se ping funcionou, False caso contrário
    - message: Mensagem descritiva
    - response_time_ms: Tempo de resposta em milissegundos (se sucesso)
    """
    import re
    
    result = {
        'success': False,
        'message': '',
        'response_time_ms': 0,
        'hostname': hostname,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # No Windows, usar comando ping nativo
        # ping -n 1 -w 2000 hostname (1 pacote, timeout 2s)
        ping_cmd = ['ping', '-n', '1', '-w', '2000', hostname]
        
        start_time = time.time()
        completed = subprocess.run(
            ping_cmd,
            capture_output=True,
            text=True,
            timeout=3  # Timeout total de 3 segundos
        )
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Verificar se ping foi bem-sucedido (código 0 no Windows)
        if completed.returncode == 0:
            # Tentar extrair tempo de resposta do output
            output = completed.stdout
            # Procurar padrão: "Tempo<1ms" ou "time<1ms" ou "time=XXms"
            time_match = re.search(r'tempo[=<]\s*(\d+)ms', output, re.IGNORECASE)
            if time_match:
                result['response_time_ms'] = int(time_match.group(1))
            else:
                result['response_time_ms'] = round(elapsed_ms, 2)
            
            result['success'] = True
            result['message'] = f"Servidor {hostname} responde ao ping ({result['response_time_ms']:.2f} ms)"
        else:
            result['success'] = False
            result['message'] = f"Servidor {hostname} não responde ao ping"
            result['response_time_ms'] = 0
            
    except subprocess.TimeoutExpired:
        result['success'] = False
        result['message'] = f"Timeout ao fazer ping em {hostname} (servidor não respondeu em 3 segundos)"
        result['response_time_ms'] = 0
    except Exception as e:
        logger.warning(f"Erro ao fazer ping em {hostname}: {e}")
        result['success'] = False
        result['message'] = f"Erro ao fazer ping: {str(e)}"
        result['response_time_ms'] = 0
    
    return JSONResponse(content=result)

@app.get("/api/monitoring/test-connection/{hostname}")
async def test_connection(hostname: str, quick: bool = True):
    """
    Testa conectividade TCP na porta SQL Server e conexão SQL
    Usa teste TCP direto na porta 1433 (mais confiável que ping ICMP)

    Parâmetros:
    - quick: Se True, faz apenas teste TCP rápido (padrão). Se False, faz testes completos.
    """
    import socket

    result = {
        'success': False,
        'message': '',
        'response_time_ms': 0,
        'hostname': hostname,
        'timestamp': datetime.now().isoformat(),
        'test_mode': 'quick' if quick else 'full'
    }
    
    # 1. Buscar informações do servidor no sql_servers.json
    sql_config = app.state.sql_servers_config
    found_instance = "DEFAULT"
    sql_port = 1433  # Porta padrão
    
    # Procurar servidor no config
    for server in sql_config.get('servers', []):
        # O JSON usa 'host' e 'instance', não 'server_name' e 'instance_name'
        server_host = server.get('host', '') or server.get('server_name', '')
        instance_name = server.get('instance', '') or server.get('instance_name', 'DEFAULT')
        server_port = server.get('port', 1433)
        
        # Remover domínio se houver
        server_base = server_host.split('.')[0]
        hostname_base = hostname.split('.')[0]
        
        if server_base.lower() == hostname_base.lower():
            found_instance = instance_name if instance_name else "DEFAULT"
            sql_port = server_port
            result['found_in_config'] = True
            result['config_port'] = sql_port
            result['config_instance'] = found_instance
            break
    else:
        result['found_in_config'] = False
        result['config_port'] = None
        result['config_instance'] = None
    
    # 2. Teste de conectividade TCP na porta SQL Server (mais confiável que ping ICMP)
    # Usa a porta do config, ou 1433 como padrão
    sql_port_accessible = False
    sql_port_latency = 0
    
    try:
        import socket
        
        start_time = time.time()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # ✅ OTIMIZADO v1.4.8.2: Timeout reduzido para 1 segundo em modo quick
        timeout_seconds = 1 if quick else 2
        sock.settimeout(timeout_seconds)

        try:
            connection_result = sock.connect_ex((hostname, sql_port))
            latency = (time.time() - start_time) * 1000
            sql_port_accessible = (connection_result == 0)
            sql_port_latency = round(latency, 2)
            sock.close()
        except socket.timeout:
            sql_port_accessible = False
            sql_port_latency = timeout_seconds * 1000  # Timeout em ms
        except Exception as e:
            logger.debug(f"Erro ao testar porta {sql_port} em {hostname}: {e}")
            sql_port_accessible = False
        
        result['sql_port_test'] = {
            'port': sql_port,
            'accessible': sql_port_accessible,
            'latency_ms': sql_port_latency
        }
        
        # Se a porta está acessível, servidor está online
        if sql_port_accessible:
            result['network_connectivity'] = True
            result['network_time_ms'] = sql_port_latency
        else:
            result['network_connectivity'] = False
            result['network_time_ms'] = sql_port_latency
            
    except Exception as e:
        logger.warning(f"Erro ao testar conectividade TCP em {hostname}: {e}")
        result['network_connectivity'] = None
        result['network_error'] = str(e)
    
    # ✅ OTIMIZADO v1.4.8.2: Modo quick retorna imediatamente após teste TCP
    if quick:
        # Modo rápido: apenas teste TCP, sem PowerShell nem SQL
        if sql_port_accessible:
            result['success'] = True
            result['message'] = f"Servidor {hostname} está ONLINE (porta {sql_port} respondeu em {sql_port_latency}ms)"
            result['response_time_ms'] = sql_port_latency
        else:
            # Porta não respondeu - pode ser:
            # 1. Servidor realmente offline
            # 2. Instância usando porta diferente (porta dinâmica)
            # 3. Firewall bloqueando a porta
            # 4. Timeout muito curto para servidor remoto
            
            # Se encontrou no config mas porta não respondeu, pode ser porta dinâmica
            if result.get('found_in_config') and found_instance and found_instance.upper() != 'DEFAULT':
                result['success'] = False
                result['message'] = f"Servidor {hostname} responde ao ping, mas porta {sql_port} não está acessível.\n\n" \
                                  f"Possíveis causas:\n" \
                                  f"• Instância '{found_instance}' pode estar usando porta dinâmica\n" \
                                  f"• Firewall bloqueando a porta {sql_port}\n" \
                                  f"• SQL Server pode não estar escutando na porta {sql_port}\n\n" \
                                  f"Tente usar o modo completo (quick=false) para verificação detalhada."
            else:
                result['success'] = False
                result['message'] = f"Servidor {hostname} parece estar OFFLINE (porta {sql_port} não respondeu após {timeout_seconds}s)\n\n" \
                                  f"Nota: Se o servidor responde ao ping mas esta mensagem aparece, pode ser:\n" \
                                  f"• Porta SQL Server diferente de {sql_port}\n" \
                                  f"• Firewall bloqueando a porta\n" \
                                  f"• SQL Server não está escutando na porta padrão"
            result['response_time_ms'] = 0

        return JSONResponse(content=result)

    # 3. Teste de conexão SQL (apenas em modo full)
    if not app.state.sql_monitoring:
        result['message'] = "SQL Monitoring não inicializado"
        return JSONResponse(content=result)

    try:

        # 2.1. Verificar serviços SQL Server primeiro (mais confiável que ping)
        # Se os serviços estão rodando, o servidor está online, mesmo que ping falhe
        services_running = False
        try:
            from modules.monitoring.service_monitor import SQLServiceMonitor
            service_monitor = SQLServiceMonitor()
            # Executar em thread para não bloquear (PowerShell pode demorar)
            services = await asyncio.to_thread(
                service_monitor.get_sql_services,
                hostname,
                found_instance if found_instance != "DEFAULT" else None,
                True  # all_services=True
            )

            # Verificar se pelo menos um serviço SQL crítico está rodando
            critical_services = [s for s in services if s.is_critical or 'MSSQL' in s.service_name.upper()]
            services_running = any(s.is_running for s in critical_services)

            if services_running:
                result['services_status'] = 'RUNNING'
                result['services_checked'] = len(services)
                result['critical_services_running'] = sum(1 for s in critical_services if s.is_running)
            else:
                result['services_status'] = 'STOPPED'
                result['services_checked'] = len(services)
        except Exception as e:
            logger.warning(f"Erro ao verificar serviços em {hostname}: {e}")
            result['services_status'] = 'UNKNOWN'
            result['services_error'] = str(e)

        # 2.2. Testar conexão SQL
        sql_result = await app.state.sql_monitoring.test_connection(hostname, found_instance)
        
        result['success'] = sql_result.get('success', False)
        result['message'] = sql_result.get('message', '')
        result['response_time_ms'] = sql_result.get('response_time_ms', 0)
        result['sql_instance'] = found_instance
        
        # Determinar status final baseado em:
        # 1. Porta SQL Server acessível (mais confiável) - teste TCP direto
        # 2. Serviços SQL rodando (via PowerShell)
        # 3. Conexão SQL funcionando (teste completo)
        
        sql_connection_success = sql_result.get('success', False)
        
        if sql_port_accessible:
            # Porta SQL Server está respondendo = servidor definitivamente online
            result['success'] = True
            if sql_connection_success:
                result['message'] = f"Conectado a {hostname}\\{found_instance} - {sql_result.get('message', '')}"
            else:
                result['message'] = f"Servidor {hostname} está online (porta {sql_port} acessível em {sql_port_latency}ms), mas conexão SQL falhou: {sql_result.get('message', '')}"
        elif services_running:
            # Serviços rodando mas porta não acessível = pode ser firewall ou porta diferente
            result['success'] = True
            if sql_connection_success:
                result['message'] = f"Conectado a {hostname}\\{found_instance} - {sql_result.get('message', '')}"
            else:
                result['message'] = f"Servidor {hostname} está online (serviços SQL rodando), mas porta {sql_port} não acessível. Pode ser firewall ou porta dinâmica."
        elif sql_connection_success:
            # Conexão SQL funcionou (mesmo que porta não tenha respondido no teste rápido)
            result['success'] = True
            result['message'] = f"Conectado a {hostname}\\{found_instance} - {sql_result.get('message', '')}"
        else:
            # Nada funcionou = servidor offline
            result['success'] = False
            result['message'] = f"Servidor {hostname} parece estar offline: porta {sql_port} não acessível, serviços não rodando, conexão SQL falhou"
        
    except Exception as e:
        logger.error(f"Erro ao testar conexão SQL em {hostname}: {e}")
        result['message'] = f"Erro ao testar conexão: {str(e)}"
        result['response_time_ms'] = 0
    
    return JSONResponse(content=result)

@app.get("/monitoring")
async def monitoring_interface():
    """
    Interface web de monitoramento SQL Server
    """
    from fastapi.responses import HTMLResponse, FileResponse
    
    # Verificar se sql_monitoring está disponível
    if app.state.sql_monitoring is None:
        return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>WatcherDB - Monitoring Setup Required</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 600px;
        }
        h1 { color: #667eea; margin-top: 0; }
        .status { 
            background: #fff3cd; 
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
        }
        .steps {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
        }
        .steps li { margin: 10px 0; }
        code {
            background: #e9ecef;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
        a {
            display: inline-block;
            margin-top: 20px;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
        }
        a:hover { background: #5568d3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ SQL Server Monitoring Setup Required</h1>
        
        <div class="status">
            <strong>Status:</strong> WatcherDB principal está funcionando, mas o módulo de monitoramento SQL Server não inicializou.
        </div>
        
        <h3>📋 Passos para ativar:</h3>
        <div class="steps">
            <ol>
                <li>Verificar se <code>modules/monitoring/__init__.py</code> existe</li>
                <li>Executar: <code>python fix_monitoring_init.py</code></li>
                <li>Reiniciar o servidor FastAPI</li>
                <li>Atualizar esta página</li>
            </ol>
        </div>
        
        <h3>🔍 Verificação rápida:</h3>
        <div class="steps">
            <pre>python -c "from modules.monitoring import SQLServerMonitoring"</pre>
        </div>
        
        <p><strong>Enquanto isso, o sistema principal continua funcionando:</strong></p>
        <a href="/">← Voltar para WatcherDB Principal</a>
        <a href="/docs">📚 Ver Documentação API</a>
    </div>
</body>
</html>
        """, status_code=503)
    
    # Se sql_monitoring está disponível, retornar a interface
    try:
        return FileResponse(_tpl("monitoring_interface.html"))
    except FileNotFoundError:
        return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>WatcherDB - File Not Found</title>
    <style>
        body { font-family: Arial; padding: 40px; text-align: center; }
        h1 { color: #dc3545; }
    </style>
</head>
<body>
    <h1>❌ File Not Found</h1>
    <p>O arquivo <code>templates/monitoring_interface.html</code> não foi encontrado.</p>
    <p>Verifique se o arquivo existe no diretório correto.</p>
    <a href="/">← Voltar</a>
</body>
</html>
        """, status_code=404)


# ============================================================================
# SPACE ANALYSIS ENDPOINTS - ROADMAP SEMANA 1
# Análise de espaço em disco e previsão de crescimento
# ============================================================================

@app.get("/api/monitoring/space/server/{server_id}")
async def get_server_space_analysis(server_id: str):
    """
    Análise completa de espaço de um servidor específico
    ROADMAP SEMANA 1: Database Growth + FileGroups
    """
    if not app.state.sql_monitoring:
        return {"error": "SQL Monitoring não inicializado"}
    
    try:
        engine = SpaceAnalysisEngine(app.state.sql_monitoring)
        analysis = await engine.analyze_server_space(server_id)
        return {
            "success": True,
            "roadmap_feature": "WEEK_1_SPACE_ANALYSIS",
            "data": analysis
        }
    except Exception as e:
        logger.error(f"Space analysis error: {e}")
        return {"success": False, "error": str(e)}

# Endpoint duplicado removido - usando o endpoint completo na linha 6335
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts")
# async def get_predictive_alerts(server_id: str):
#     """Análise preditiva de alertas de espaço"""
#     ...


@app.get("/api/monitoring/space/dashboard")
async def get_space_dashboard():
    """
    Dashboard consolidado de espaço para todos os servidores
    ROADMAP SEMANA 1: Capacity Planning Dashboard
    """
    if not app.state.sql_monitoring:
        return {"error": "SQL Monitoring não inicializado"}
    
    try:
        # Buscar lista de servidores do config
        server_ids = []
        if hasattr(app.state, 'sql_servers_config'):
            server_ids = [s['id'] for s in app.state.sql_servers_config.get('servers', [])]
        
        logger.info(f"Space Dashboard: Analisando {len(server_ids)} servidores")
        
        # Passar lista de servidores para análise
        dashboard_data = await get_space_analysis_for_all_servers(
            app.state.sql_monitoring, 
            server_ids
        )
        
        return {
            "success": True,
            "roadmap_feature": "WEEK_1_SPACE_DASHBOARD",
            "dashboard": dashboard_data
        }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/space/alerts")
async def get_critical_space_alerts():
    """
    Alertas críticos de espaço em todos os servidores
    ROADMAP SEMANA 1: Sistema de Alertas Preventivos
    """
    if not app.state.sql_monitoring:
        return {"error": "SQL Monitoring não inicializado"}
    
    try:
        engine = SpaceAnalysisEngine(app.state.sql_monitoring)
        
        # Buscar lista de servidores do config
        server_ids = []
        if hasattr(app.state, 'sql_servers_config'):
            server_ids = [s['id'] for s in app.state.sql_servers_config.get('servers', [])]
        
        logger.info(f"Space Alerts: Analisando {len(server_ids)} servidores")
        
        all_alerts = []
        for server_id in server_ids:
            analysis = await engine.analyze_server_space(server_id)
            if analysis.get('alerts'):
                for alert in analysis['alerts']:
                    alert['server_id'] = server_id
                    all_alerts.append(alert)
        
        # Filtrar apenas críticos
        critical_alerts = [a for a in all_alerts if a['alert_level'] in ['CRITICAL', 'HIGH']]
        
        # Ordenar por criticidade
        critical_alerts.sort(key=lambda x: (x['alert_level'] == 'CRITICAL', -x['free_percent']), reverse=True)
        
        return {
            "success": True,
            "roadmap_feature": "WEEK_1_PREVENTIVE_ALERTS",
            "total_alerts": len(all_alerts),
            "critical_alerts": len(critical_alerts),
            "alerts": critical_alerts[:20]  # Top 20 mais críticos
        }
    except Exception as e:
        logger.error(f"Alerts error: {e}")
        return {"success": False, "error": str(e)}


# =====================
# BACKUP ANALYSIS API
# =====================

@app.get("/api/monitoring/backup/server/{server_id}/summary")
async def api_backup_summary(server_id: str, days: int = 14):
    import time as _time
    t0 = _time.perf_counter()
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        backup_tool_cfg = getattr(app.state, 'backup_tool_config', None)
        engine = BackupAnalysisEngine(sql_mon, backup_tool_config=backup_tool_cfg)
        result = await engine.analyze_server_backups(server_id, lookback_days=days)
        elapsed = _time.perf_counter() - t0
        logger.info(f"⏱ BACKUP SUMMARY {server_id}: {elapsed:.1f}s total")
        return result
    except Exception as e:
        elapsed = _time.perf_counter() - t0
        logger.error(f"⏱ BACKUP SUMMARY {server_id}: ERRO após {elapsed:.1f}s - {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/backup/server/{server_id}/issues")
async def api_backup_issues(server_id: str, days: int = 14):
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        engine = BackupAnalysisEngine(sql_mon)
        result = await engine.analyze_server_backups(server_id, lookback_days=days)
        if not result.get('success'):
            return result
        items = [i for i in result.get('items', []) if i.get('issues')]
        return {
            'success': True,
            'server_id': server_id,
            'total_databases': result.get('total_databases', 0),
            'databases_with_issues': len(items),
            'items': items,
        }
    except Exception as e:
        logger.error(f"Backup issues error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/api/monitoring/backup/server/{server_id}/database/{database_name}/history")
async def api_backup_history(server_id: str, database_name: str, days: int = 7, limit: int = 50):
    """Retorna histórico de backups (FULL/DIFF/LOG) para um database."""
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        start_time = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
        SELECT TOP ({limit})
            bs.database_name,
            CASE bs.type WHEN 'D' THEN 'FULL' WHEN 'I' THEN 'DIFF' WHEN 'L' THEN 'LOG' ELSE bs.type END AS backup_type,
            bs.backup_start_date AS start_time,
            bs.backup_finish_date AS finish_time,
            DATEDIFF(SECOND, bs.backup_start_date, bs.backup_finish_date) AS duration_seconds,
            CAST(bs.backup_size/1024.0/1024.0/1024.0 AS DECIMAL(18,2)) AS size_gb,
            @@SERVERNAME AS server_executed
        FROM msdb.dbo.backupset bs
        WHERE bs.backup_start_date >= CONVERT(datetime, '{start_time}')
          AND bs.database_name = '{database_name}'
        ORDER BY bs.backup_start_date DESC;
        """
        result = await sql_mon.execute_query(server_id, query)
        if not result or not result.get('success'):
            return {"success": False, "error": result.get('error', 'query-failed')}
        rows = result.get('rows', [])
        # Converter para tipos amigáveis
        history = []
        for r in rows:
            try:
                start = r.get('start_time')
                finish = r.get('finish_time')
                history.append({
                    'backup_type': r.get('backup_type'),
                    'start_time': start.isoformat() if start else None,
                    'finish_time': finish.isoformat() if finish else None,
                    'duration_seconds': int(r.get('duration_seconds') or 0),
                    'size_gb': float(r.get('size_gb') or 0),
                    'server_executed': r.get('server_executed')
                })
            except Exception:
                continue
        return {"success": True, "server_id": server_id, "database": database_name, "days": days, "items": history}
    except Exception as e:
        logger.error(f"Backup history error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/api/monitoring/backup/summary")
async def api_backup_executive_summary(env: str = None, days: int = 7):
    """Resumo executivo: percentuais de bancos fora do SLA por servidor e ambiente."""
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        # Carregar servidores da config
        servers = []
        if hasattr(app.state, 'sql_servers_config'):
            for s in app.state.sql_servers_config.get('servers', []):
                if env and s.get('environment') and str(s.get('environment')).lower() != env.lower():
                    continue
                if s.get('id'):
                    servers.append({
                        'id': s.get('id'),
                        'environment': s.get('environment', 'production')
                    })
        engine = BackupAnalysisEngine(sql_mon)
        summary_items = []
        for s in servers[:100]:  # proteção
            res = await engine.analyze_server_backups(s['id'], lookback_days=days)
            if not res.get('success'):
                continue
            total = res.get('total_databases', 0)
            bad = res.get('databases_with_issues', 0)
            pct_bad = round((bad/total*100.0),1) if total else 0.0
            summary_items.append({
                'server_id': s['id'],
                'environment': s['environment'],
                'total_databases': total,
                'with_issues': bad,
                'pct_with_issues': pct_bad
            })
        # Ordenar por pior
        summary_items.sort(key=lambda x: x['pct_with_issues'], reverse=True)
        overall = {
            'servers': len(summary_items),
            'avg_pct_with_issues': round(sum(i['pct_with_issues'] for i in summary_items)/len(summary_items),1) if summary_items else 0.0
        }
        return {"success": True, "days": days, "environment": env, "overall": overall, "items": summary_items}
    except Exception as e:
        logger.error(f"Backup summary error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/api/monitoring/backup/server/{server_id}/summary.csv")
async def api_backup_summary_csv(server_id: str, days: int = 14):
    """Exporta CSV do resumo de backups do servidor."""
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return Response(status_code=400, content='sql_monitoring não inicializado')
        engine = BackupAnalysisEngine(sql_mon)
        res = await engine.analyze_server_backups(server_id, lookback_days=days)
        if not res.get('success'):
            return Response(status_code=500, content=str(res.get('error')))
        from io import StringIO
        import csv as _csv
        sio = StringIO()
        writer = _csv.writer(sio)
        writer.writerow(['database','recovery_model','last_full','last_diff','last_log','issues','tdp_error_count'])
        for it in res.get('items', []):
            issues = ','.join(it.get('issues', []))
            writer.writerow([it.get('database_name'), it.get('recovery_model'), it.get('last_full'), it.get('last_diff'), it.get('last_log'), issues, it.get('tdp_error_count',0)])
        csv_content = sio.getvalue()
        return Response(content=csv_content, media_type='text/csv')
    except Exception as e:
        logger.error(f"Backup CSV error: {e}", exc_info=True)
        return Response(status_code=500, content=str(e))

# =====================
# SECURITY ANALYSIS ENDPOINTS
# =====================

@app.get("/api/monitoring/security/server/{server_id}")
async def api_security_analysis(server_id: str):
    """Análise de segurança do SQL Server"""
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        engine = SecurityAnalysisEngine(sql_mon)
        result = await engine.analyze_server_security(server_id)
        return result
    except Exception as e:
        logger.error(f"Security analysis error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =====================
# BACKUP PATTERN ANALYSIS ENDPOINTS
# =====================

@app.get("/api/monitoring/backup/server/{server_id}/patterns-advanced")
async def api_backup_patterns_server(server_id: str, window_days: int = 30):
    """
    Analisa padrões de backup de todas as databases do servidor.
    
    Query Parameters:
        - window_days: Janela de análise em dias (padrão: 30)
    """
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        analyzer = BackupPatternAnalyzer(sql_mon)
        result = await analyzer.analyze_server_patterns(server_id, window_days)
        return result
    except Exception as e:
        logger.error(f"Backup patterns analysis error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/backup/server/{server_id}/database/{database_name}/pattern")
async def api_backup_pattern_database(server_id: str, database_name: str, window_days: int = 30):
    """
    Analisa padrão de backup de uma database específica.
    
    Query Parameters:
        - window_days: Janela de análise em dias (padrão: 30)
    """
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        analyzer = BackupPatternAnalyzer(sql_mon)
        result = await analyzer.analyze_database_patterns(server_id, database_name, window_days)
        from dataclasses import asdict
        return asdict(result)
    except Exception as e:
        logger.error(f"Backup pattern analysis error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/backup/server/{server_id}/gaps")
async def api_backup_gaps(server_id: str, window_days: int = 30, severity: Optional[str] = None):
    """
    Lista apenas os gaps detectados (backups atrasados).
    
    Query Parameters:
        - window_days: Janela de análise em dias (padrão: 30)
        - severity: Filtrar por severidade ('low', 'medium', 'high', 'critical')
    """
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        analyzer = BackupPatternAnalyzer(sql_mon)
        result = await analyzer.analyze_server_patterns(server_id, window_days)
        
        if not result.get('success'):
            return result
        
        # Extrair todos os gaps
        all_gaps = []
        for db_analysis in result.get('databases', []):
            db_name = db_analysis['database_name']
            for gap in db_analysis.get('detected_gaps', []):
                gap_with_db = {**gap, 'database_name': db_name}
                all_gaps.append(gap_with_db)
        
        # Filtrar por severidade se especificado (filtro CASCATA)
        if severity:
            severity_lower = severity.lower()
            # Definir hierarquia de severidades (do menos grave ao mais grave)
            severity_hierarchy = ['low', 'medium', 'high', 'critical']

            if severity_lower in severity_hierarchy:
                # Filtro cascata: incluir a severidade selecionada e todas as superiores
                min_index = severity_hierarchy.index(severity_lower)
                allowed_severities = severity_hierarchy[min_index:]
                all_gaps = [g for g in all_gaps if g.get('severity', '').lower() in allowed_severities]

        # Contar gaps por severidade
        critical_count = sum(1 for g in all_gaps if g.get('severity') == 'critical')
        high_count = sum(1 for g in all_gaps if g.get('severity') == 'high')
        medium_count = sum(1 for g in all_gaps if g.get('severity') == 'medium')
        low_count = sum(1 for g in all_gaps if g.get('severity') == 'low')
        
        return {
            'success': True,
            'server_id': server_id,
            'total_gaps': len(all_gaps),
            'critical_count': critical_count,
            'high_count': high_count,
            'medium_count': medium_count,
            'low_count': low_count,
            'gaps': all_gaps
        }
    except Exception as e:
        logger.error(f"Backup gaps analysis error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/backup/server/{server_id}/health")
async def api_backup_health(server_id: str, window_days: int = 30):
    """
    Retorna score de saúde geral dos backups do servidor.
    
    Query Parameters:
        - window_days: Janela de análise em dias (padrão: 30)
    """
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        analyzer = BackupPatternAnalyzer(sql_mon)
        result = await analyzer.analyze_server_patterns(server_id, window_days)
        
        if not result.get('success'):
            return result
        
        health_score = result.get('overall_server_health', 0)
        
        # Classificar status de saúde
        if health_score >= 90:
            health_status = "excellent"
        elif health_score >= 70:
            health_status = "good"
        elif health_score >= 50:
            health_status = "warning"
        else:
            health_status = "critical"
        
        # Contar databases com padrões identificados
        databases = result.get('databases', [])
        patterns_count = {
            'full': sum(1 for db in databases if db.get('full_pattern')),
            'diff': sum(1 for db in databases if db.get('diff_pattern')),
            'log': sum(1 for db in databases if db.get('log_pattern'))
        }
        
        # Gerar recomendações
        recommendations = []
        summary = result.get('summary', {})
        
        if summary.get('critical_gaps', 0) > 0:
            recommendations.append(f"{summary['critical_gaps']} database(s) com gap crítico de backup (>14 dias para FULL ou >8h para LOG)")
        
        if summary.get('databases_with_gaps', 0) > 0:
            recommendations.append(f"{summary['databases_with_gaps']} database(s) com gaps de backup detectados")
        
        low_pattern_count = result.get('total_databases', 0) - patterns_count['full']
        if low_pattern_count > 5:
            recommendations.append(f"Considere investigar padrões de backup inconsistentes em {low_pattern_count} databases")
        
        if not recommendations:
            recommendations.append("Todos os backups estão dentro do padrão esperado ✅")
        
        return {
            'success': True,
            'server_id': server_id,
            'health_score': health_score,
            'health_status': health_status,
            'total_databases': result.get('total_databases', 0),
            'summary': {
                **summary,
                'databases_with_patterns': patterns_count
            },
            'recommendations': recommendations
        }
    except Exception as e:
        logger.error(f"Backup health analysis error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/backup/server/{server_id}/patterns")
async def api_backup_patterns(server_id: str, days: int = 30):
    """Inferência de padrão com regras específicas:
    - Diferenciais: 1x por dia
    - Full: 1x por semana
    - Log: todos os dias, exceto quando full ou diferencial estiver rodando
    Retorna por DB: intervalos típicos, horários mais prováveis, gaps e tempo em falta.
    """
    import time as _time
    t0 = _time.perf_counter()
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None)
        if not sql_mon:
            return {"success": False, "error": "sql_monitoring não inicializado"}
        start_time = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
        SELECT
            bs.database_name,
            CASE bs.type WHEN 'D' THEN 'FULL' WHEN 'I' THEN 'DIFF' WHEN 'L' THEN 'LOG' ELSE bs.type END AS backup_type,
            bs.backup_start_date AS start_time,
            bs.backup_finish_date AS finish_time
        FROM msdb.dbo.backupset bs
        WHERE bs.backup_finish_date >= CONVERT(datetime, '{start_time}')
        ORDER BY bs.database_name, bs.type, bs.backup_finish_date
        """
        t1 = _time.perf_counter()
        result = await sql_mon.execute_query(server_id, query)
        t2 = _time.perf_counter()
        logger.info(f"⏱ BACKUP PATTERNS {server_id}: SQL query={t2-t1:.1f}s")
        if not result or not result.get('success'):
            return {"success": False, "error": result.get('error', 'query-failed')}
        rows = result.get('rows', [])
        logger.info(f"⏱ BACKUP PATTERNS {server_id}: {len(rows)} rows retornadas")
        from collections import defaultdict, Counter
        import statistics
        per_db: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        # Armazenar também start_time para verificar sobreposição
        per_db_starts: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        
        for r in rows:
            db = r.get('database_name')
            typ = r.get('backup_type')
            ft = r.get('finish_time')
            st = r.get('start_time')
            if not (db and typ and ft):
                continue
            
            # Converter finish_time para datetime se for string
            if not isinstance(ft, datetime):
                if isinstance(ft, str):
                    try:
                        # Tentar ISO format primeiro
                        ft = datetime.fromisoformat(ft.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        try:
                            # Tentar formato SQL Server comum: 'YYYY-MM-DD HH:MM:SS'
                            ft = datetime.strptime(ft.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse finish_time: {ft}")
                            continue
                else:
                    logger.warning(f"finish_time is not datetime or string: {type(ft)}")
                    continue

            # Converter start_time para datetime se for string
            if st and not isinstance(st, datetime):
                if isinstance(st, str):
                    try:
                        # Tentar ISO format primeiro
                        st = datetime.fromisoformat(st.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        try:
                            # Tentar formato SQL Server comum: 'YYYY-MM-DD HH:MM:SS'
                            st = datetime.strptime(st.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            st = None
                else:
                    st = None
            
            per_db[db][typ].append(ft)
            if st:
                per_db_starts[db][typ].append(st)
        
        now = datetime.now()
        
        def compute_pattern(times: list, backup_type: str, db_name: str) -> Dict:
            """Calcula padrão com regras específicas por tipo de backup"""
            if len(times) < 1:
                return {
                    "interval_hours": None,
                    "hour_range": None,
                    "gaps": [],
                    "missing": True,
                    "hours_missing": None,
                    "expected_interval_hours": None
                }
            
            times_sorted = sorted(times)
            last_backup = times_sorted[-1]
            since_last_h = (now - last_backup).total_seconds() / 3600.0
            
            # Regras específicas por tipo
            if backup_type == 'FULL':
                expected_interval = 24 * 7  # 1x por semana (168 horas)
                expected_interval_days = 7
                missing_threshold = expected_interval * 1.2  # 20% de tolerância
            elif backup_type == 'DIFF':
                expected_interval = 24  # 1x por dia (24 horas)
                expected_interval_days = 1
                missing_threshold = expected_interval * 1.5  # 50% de tolerância
            elif backup_type == 'LOG':
                # LOG deve ocorrer diariamente, mas pode pular quando FULL ou DIFF está rodando
                expected_interval = 24  # Esperado diariamente
                expected_interval_days = 1
                missing_threshold = expected_interval * 2  # 2 dias de tolerância (pode pular 1 dia se FULL/DIFF rodou)
            else:
                expected_interval = None
                expected_interval_days = None
                missing_threshold = None
            
            # Calcular intervalo real observado (se houver múltiplos backups)
            interval_hours = None
            hour_range = None
            
            if len(times_sorted) >= 2:
                deltas_h = [(t2 - t1).total_seconds() / 3600.0 for t1, t2 in zip(times_sorted[:-1], times_sorted[1:])]
                med = statistics.median(deltas_h)
                interval_hours = round(med, 1)
                
                # Calcular range de horários (min e max hora do dia)
                hours = [t.hour for t in times_sorted]
                min_hour = min(hours)
                max_hour = max(hours)
                if min_hour == max_hour:
                    hour_range = f"{min_hour:02d}:00"
                else:
                    hour_range = f"{min_hour:02d}:00 - {max_hour:02d}:00"
            elif len(times_sorted) == 1:
                # Apenas um backup - usar a hora dele como referência
                single_hour = times_sorted[0].hour
                hour_range = f"{single_hour:02d}:00"
            
            # Detectar gaps (onde o intervalo real foi muito maior que o esperado)
            gaps = []
            if len(times_sorted) >= 2 and expected_interval:
                threshold = expected_interval * 1.5
                deltas_h = [(t2 - t1).total_seconds() / 3600.0 for t1, t2 in zip(times_sorted[:-1], times_sorted[1:])]
                for t1, t2, d in zip(times_sorted[:-1], times_sorted[1:], deltas_h):
                    if d > threshold:
                        expected = t1 + timedelta(hours=expected_interval)
                        gaps.append({
                            'from': t1.isoformat(),
                            'to': t2.isoformat(),
                            'expected': expected.isoformat(),
                            'gap_hours': round(d, 1),
                            'gap_days': round(d / 24, 1)
                        })
            
            # Verificar se está em falta agora
            missing = False
            hours_missing = None
            if expected_interval and since_last_h > missing_threshold:
                missing = True
                hours_missing = round(since_last_h, 1)
            
            return {
                'interval_hours': interval_hours,
                'expected_interval_hours': round(expected_interval, 1) if expected_interval else None,
                'expected_interval_days': expected_interval_days,
                'hour_range': hour_range,
                'hour_of_day': int(times_sorted[-1].hour) if times_sorted else None,
                'gaps': gaps,
                'missing': missing,
                'hours_missing': hours_missing,
                'days_missing': round(hours_missing / 24, 1) if hours_missing else None,
                'last_backup': times_sorted[-1].isoformat() if times_sorted else None,
                'hours_since_last': round(since_last_h, 1),
                'next_expected': (last_backup + timedelta(hours=expected_interval)).isoformat() if (expected_interval and times_sorted) else None
            }
        
        # Para LOG, verificar se houve FULL ou DIFF rodando ao mesmo tempo (excluir esses períodos)
        def filter_log_backups(log_times: list, full_times: list, diff_times: list, full_starts: list, diff_starts: list) -> list:
            """Filtra backups de LOG que ocorreram durante FULL ou DIFF"""
            filtered = []
            for log_time in log_times:
                # Verificar se este LOG ocorreu durante algum FULL ou DIFF
                during_full_or_diff = False
                
                # Verificar FULL
                for i, full_finish in enumerate(full_times):
                    if i < len(full_starts):
                        full_start = full_starts[i]
                        if full_start <= log_time <= full_finish:
                            during_full_or_diff = True
                            break
                
                # Verificar DIFF
                if not during_full_or_diff:
                    for i, diff_finish in enumerate(diff_times):
                        if i < len(diff_starts):
                            diff_start = diff_starts[i]
                            if diff_start <= log_time <= diff_finish:
                                during_full_or_diff = True
                                break
                
                if not during_full_or_diff:
                    filtered.append(log_time)
            
            return filtered
        
        payload = {}
        for db, types in per_db.items():
            db_patterns = {}
            
            # Processar FULL
            if 'FULL' in types:
                db_patterns['FULL'] = compute_pattern(types['FULL'], 'FULL', db)
            
            # Processar DIFF
            if 'DIFF' in types:
                db_patterns['DIFF'] = compute_pattern(types['DIFF'], 'DIFF', db)
            
            # Processar LOG (filtrar os que ocorreram durante FULL ou DIFF)
            if 'LOG' in types:
                log_times = types['LOG']
                full_times = types.get('FULL', [])
                diff_times = types.get('DIFF', [])
                full_starts = per_db_starts[db].get('FULL', [])
                diff_starts = per_db_starts[db].get('DIFF', [])
                
                # Filtrar LOGs que ocorreram durante FULL ou DIFF
                filtered_log_times = filter_log_backups(log_times, full_times, diff_times, full_starts, diff_starts)
                
                if filtered_log_times:
                    db_patterns['LOG'] = compute_pattern(filtered_log_times, 'LOG', db)
                else:
                    # Se todos foram filtrados, usar todos mesmo assim (pode não ter FULL/DIFF)
                    db_patterns['LOG'] = compute_pattern(log_times, 'LOG', db)
            
            payload[db] = db_patterns
        
        elapsed = _time.perf_counter() - t0
        logger.info(f"⏱ BACKUP PATTERNS {server_id}: {elapsed:.1f}s total ({len(rows)} rows, {len(payload)} databases)")
        return {"success": True, "server_id": server_id, "days": days, "databases": payload}
    except Exception as e:
        elapsed = _time.perf_counter() - t0
        logger.error(f"⏱ BACKUP PATTERNS {server_id}: ERRO após {elapsed:.1f}s - {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# ==============================================================
# WINDOWS EVENTS - AGREGAÇÃO POR SEVERIDADE/CATEGORIA
# ==============================================================

def _classify_windows_event(event_id: int, source: str, level: str) -> str:
    try:
        if source:
            s = source.lower()
        else:
            s = ''
        if s in ('disk','ntfs','storport','partmgr','stornvme'):
            return 'STORAGE'
        if 'cluster' in s:
            return 'CLUSTER'
        if 'sqlvdi' in s or 'vss' in s:
            return 'BACKUP_VSS'
        if 'mssql' in s or 'sqlserver' in s:
            return 'SQLSERVER'
        if 'tcpip' in s or 'net' in s:
            return 'NETWORK'
        return 'SYSTEM'
    except Exception:
        return 'SYSTEM'

@app.get("/api/monitoring/windows-events/{server_id}")
async def api_windows_events(server_id: str, hours: int = 24, levels: str = 'Error,Critical', max_events: int = 200, categories: str = ''):
    """Busca eventos do Windows (Application/System) via PowerShell remoto (WinRM) e agrega por severidade/categoria.

    Categorias default (rapidas): shutdown, disk, sql_server, alwayson.
    Categorias opcionais (mais lentas — passar via ?categories=...):
        cluster        — le canal Microsoft-Windows-FailoverClustering/Operational
                         (so via PS Plan A, ~10s extra mesmo quando vazio)
        csv_storage    — captura CSV IO timeouts (5120/5142 + text-search ~15s extra)
        backup         — Volume Shadow Copy errors (VSS)
        service_broker — Service Broker / Database Mirroring transport errors
    """
    try:
        from modules.monitoring.logs_collector import WindowsLogsCollector

        # Categorias default removidas: 'memory' (nao esta no category_map),
        # 'cluster' (lento, raro), 'csv_storage' (PS pesado). Quem quiser
        # consulta-las explicitamente passa ?categories=cluster,csv_storage.
        if categories:
            event_categories = [c.strip() for c in categories.split(',') if c.strip()]
        else:
            event_categories = ['shutdown', 'disk', 'sql_server', 'alwayson']

        collector = WindowsLogsCollector()
        result = collector.collect_windows_events(
            server_id=server_id,
            hours=hours,
            event_categories=event_categories
        )
        
        if not result.get('success'):
            # Fallback para método antigo se o novo falhar
            return await _fallback_windows_events(server_id, hours, levels, max_events)
        
        # Formatar eventos para compatibilidade com frontend
        events = []
        for evt in result.get('events', [])[:max_events]:
            events.append({
                'time_generated': evt.get('TimeCreated'),
                'timeCreated': evt.get('TimeCreated'),
                'event_id': evt.get('Id'),
                'eventId': evt.get('Id'),
                'level': evt.get('LevelDisplayName', ''),
                'level_name': evt.get('LevelDisplayName', ''),
                'levelDisplayName': evt.get('LevelDisplayName', ''),
                'source': evt.get('ProviderName', ''),
                'provider_name': evt.get('ProviderName', ''),
                'providerName': evt.get('ProviderName', ''),
                'log_name': evt.get('LogName', ''),
                'message': evt.get('Message', ''),
                'description': evt.get('Message', ''),
                'category': evt.get('category', ''),
                'event_type': evt.get('event_type', '')
            })
        
        return {
            'success': True,
            'server_id': server_id,
            'hours': hours,
            'events': events,
            'total_count': len(events),
            'categories_found': result.get('categories_found', [])
        }
    except Exception as e:
        logger.error(f"Windows events error: {e}", exc_info=True)
        # Fallback para método antigo
        return await _fallback_windows_events(server_id, hours, levels, max_events)

async def _fallback_windows_events(server_id: str, hours: int, levels: str, max_events: int):
    """Método fallback (código original)"""
    try:
        # Construir script PS simples
        level_list = ','.join([f"'{l.strip()}'" for l in levels.split(',')])
        ps_lines = [
            "$ErrorActionPreference='SilentlyContinue'",
            f"$lvls=@({level_list})",
            f"$start=(Get-Date).AddHours(-{hours})",
            "$logs=@('Application','System')",
            "$res=@()",
            "foreach($log in $logs) {",
            "    try {",
            f"        $evts = Get-WinEvent -FilterHashtable @{{LogName=$log; StartTime=$start}} -ErrorAction SilentlyContinue -MaxEvents {max_events} | Where-Object {{ $lvls -contains $_.LevelDisplayName }}",
            "        $res += $evts | Select-Object @{n='TimeCreated';e={$_.TimeCreated}}, @{n='Level';e={$_.LevelDisplayName}}, @{n='Id';e={$_.Id}}, @{n='ProviderName';e={$_.ProviderName}}, @{n='Message';e={$_.Message}}",
            "    } catch {}",
            "}",
            "$res | ConvertTo-Json -Depth 3"
        ]
        ps = '\n'.join(ps_lines)
        # Executar localmente via WinRM/ComputerName
        import subprocess, json as _json
        server_name = server_id.split('_')[0]
        cmd = ["powershell","-NoProfile","-Command", f"Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {ps} }}"]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            raw = completed.stdout.strip() or '[]'
            if completed.returncode != 0:
                raise Exception(f"PS error: {completed.stderr}")
        except Exception as e:
            logger.warning(f"WinRM failed for {server_name}, trying local: {e}")
            # Fallback: tentar local (se rodando no próprio servidor)
            completed = subprocess.run(["powershell","-NoProfile","-Command", ps], capture_output=True, text=True, timeout=30)
            raw = completed.stdout.strip() or '[]'
        try:
            items = _json.loads(raw)
            if isinstance(items, dict):
                items = [items]
        except Exception:
            items = []

        # Formatar para compatibilidade
        events = []
        for ev in items[:max_events]:
            events.append({
                'time_generated': str(ev.get('TimeCreated', '')),
                'timeCreated': str(ev.get('TimeCreated', '')),
                'event_id': int(ev.get('Id', 0) or 0),
                'eventId': int(ev.get('Id', 0) or 0),
                'level': ev.get('Level', ''),
                'level_name': ev.get('Level', ''),
                'source': ev.get('ProviderName', ''),
                'provider_name': ev.get('ProviderName', ''),
                'message': (ev.get('Message') or '').split('\n')[0][:300]
            })
        
        return {'success': True, 'server_id': server_id, 'hours': hours, 'events': events, 'total_count': len(events)}
    except Exception as e:
        logger.error(f"Fallback Windows events error: {e}", exc_info=True)
        return {'success': False, 'error': str(e), 'events': []}

@app.get("/api/monitoring/sql-errors/{server_id}")
async def api_sql_errors(server_id: str, hours: int = 24):
    """Busca erros do SQL Server via xp_readerrorlog (conexao SQL directa)

    Abordagem principal: xp_readerrorlog via mesma conexao SQL que o endpoint de databases.
    Fallback: SQLLogsCollector (PowerShell) se a query SQL falhar.
    """
    errors = []
    source_method = 'unknown'

    # === PLANO A: xp_readerrorlog via SQL (fiavel, usa mesma conexao que databases) ===
    try:
        from api.routers.sql_queries import execute_query_on_server
        import asyncio as _asyncio

        # Query identica a' do V5 — paridade entre os dois projectos.
        #
        # NOTA: tinha tentado optimizar usando xp_readerrorlog com @SearchTerm1
        # ('Error', 'Severity', 'fail') para reduzir carga em errorlogs grandes,
        # MAS o SearchTerm filtra DURANTE a leitura — entao linhas de BACKUP
        # ('BACKUP DATABASE WITH DIFFERENTIAL successfully processed...') que
        # nao contem nenhuma dessas palavras nunca eram lidas. Isso fazia com
        # que servidores PRD com muitos backups mostrassem 0 erros no Log
        # quando o V5 mostrava 30+. O `OR ProcessInfo = 'Backup'` no WHERE
        # apanha essas linhas, mas so se elas estiverem na temp table.
        #
        # A protecao contra hang em errorlogs gigantes ja vem do
        # asyncio.wait_for(35.0) abaixo, que corta antes do cliente desistir.
        query = f"""
        DECLARE @start DATETIME = DATEADD(HOUR, -{int(hours)}, GETDATE());

        CREATE TABLE #errorlog (
            LogDate DATETIME,
            ProcessInfo NVARCHAR(100),
            Text NVARCHAR(MAX)
        );

        BEGIN TRY
            INSERT INTO #errorlog EXEC xp_readerrorlog 0, 1, NULL, NULL, @start;
        END TRY
        BEGIN CATCH
            -- Se falhar, tentar sp_readerrorlog
            BEGIN TRY
                INSERT INTO #errorlog EXEC sp_readerrorlog 0, 1, NULL, NULL, @start;
            END TRY
            BEGIN CATCH
                -- Silenciar - tabela ficara vazia
            END CATCH
        END CATCH

        SELECT
            LogDate,
            ProcessInfo,
            Text
        FROM #errorlog
        WHERE Text NOT LIKE '%Login succeeded%'
            AND Text NOT LIKE '%found 0 errors%'
            AND Text NOT LIKE '%CHECKDB%0 errors%'
            AND Text NOT LIKE '%This is an informational message%'
            AND Text NOT LIKE '%Setting database option%'
            AND Text NOT LIKE '%Starting up database%'
            AND Text NOT LIKE '%Recovery is complete%'
            AND (
                Text LIKE '%Error:%'
                OR Text LIKE '%Severity:%'
                OR Text LIKE '%fail%'
                OR Text LIKE '%corrupt%'
                OR Text LIKE '%I/O error%'
                OR Text LIKE '%deadlock%'
                OR Text LIKE '%timeout%'
                OR Text LIKE '%kill%'
                OR Text LIKE '%stack dump%'
                OR Text LIKE '%FlushCache%'
                OR Text LIKE '%DBCC%'
                OR Text LIKE '%suspect%'
                OR Text LIKE '%recovery%error%'
                OR Text LIKE '%cannot obtain%'
                OR Text LIKE '%insufficient%'
                OR Text LIKE '%out of memory%'
                OR Text LIKE '%abnormal%'
                OR Text LIKE '%terminated%'
                OR Text LIKE '%Always On%'
                OR Text LIKE '%availability%'
                OR Text LIKE '%failover%'
                OR Text LIKE '%cluster%'
                OR Text LIKE '%Severity: 1[7-9]%'
                OR Text LIKE '%Severity: 2[0-5]%'
                OR ProcessInfo = 'Backup'
            )
        ORDER BY LogDate DESC;

        DROP TABLE #errorlog;
        """

        # Wrap em asyncio.wait_for para garantir que libertamos o cliente HTTP
        # mesmo se o cursor ODBC nao responder ao timeout interno (sintoma
        # classico do xp_readerrorlog em errorlogs muito grandes — o command
        # timeout do pyodbc so dispara na 1a row, e o xp_readerrorlog so
        # devolve depois de processar tudo).
        # 35s e' o timeout combinado: 30s do command_timeout + 5s de margem.
        try:
            result = await _asyncio.wait_for(
                execute_query_on_server(server_id, query, command_timeout=30, connection_timeout=10),
                timeout=35.0
            )
        except _asyncio.TimeoutError:
            logger.warning(f"[SQL Errors] xp_readerrorlog excedeu 35s para {server_id} — abortando")
            result = None

        if result and len(result) > 0:
            source_method = 'xp_readerrorlog'
            for row in result:
                log_date = row.get('LogDate', '')
                text = row.get('Text', '')
                process_info = row.get('ProcessInfo', '')

                # Tentar extrair severity do texto
                severity = None
                import re
                sev_match = re.search(r'Severity:\s*(\d+)', text)
                if sev_match:
                    severity = int(sev_match.group(1))

                # Tentar extrair error number
                err_match = re.search(r'Error:\s*(\d+)', text)
                error_number = int(err_match.group(1)) if err_match else None

                # Classificar severidade para display
                if severity and severity >= 17:
                    display_severity = 'ERROR'
                elif severity and severity >= 11:
                    display_severity = 'WARNING'
                elif 'fail' in text.lower() or 'error' in text.lower():
                    display_severity = 'WARNING'
                else:
                    display_severity = 'INFO'

                errors.append({
                    'error_date': str(log_date) if log_date else '',
                    'errorDate': str(log_date) if log_date else '',
                    'log_date': str(log_date) if log_date else '',
                    'error_severity': severity or display_severity,
                    'severity': display_severity,
                    'error_number': error_number,
                    'errorNumber': error_number,
                    'error_message': text,
                    'message': text,
                    'text': text,
                    'process_info': process_info,
                    'database_name': None,
                    'databaseName': None,
                    'source': 'xp_readerrorlog'
                })

            logger.info(f"[SQL Errors] xp_readerrorlog retornou {len(errors)} erros para {server_id}")
        else:
            logger.info(f"[SQL Errors] xp_readerrorlog retornou 0 resultados para {server_id} (sem erros nas ultimas {hours}h)")
            source_method = 'xp_readerrorlog'

    except Exception as sql_err:
        logger.warning(f"[SQL Errors] Plano A (xp_readerrorlog) falhou para {server_id}: {sql_err}")

        # === PLANO B: SQLLogsCollector (PowerShell) ===
        try:
            from modules.monitoring.logs_collector import SQLLogsCollector

            collector = SQLLogsCollector()
            result = collector.collect_all_sql_errors(server_id=server_id, hours=hours)

            if result.get('success'):
                source_method = 'powershell'
                for err in result.get('errors', []):
                    error_date = err.get('timestamp') or err.get('error_date') or err.get('TimeCreated')
                    errors.append({
                        'error_date': error_date,
                        'errorDate': error_date,
                        'log_date': error_date,
                        'error_severity': err.get('severity') or err.get('error_severity'),
                        'severity': err.get('severity') or err.get('error_severity'),
                        'error_number': err.get('error_number') or err.get('errorNumber'),
                        'errorNumber': err.get('error_number') or err.get('errorNumber'),
                        'error_message': err.get('message') or err.get('error_message') or err.get('text', ''),
                        'message': err.get('message') or err.get('error_message') or err.get('text', ''),
                        'text': err.get('message') or err.get('error_message') or err.get('text', ''),
                        'database_name': err.get('database_name'),
                        'databaseName': err.get('database_name'),
                        'source': 'powershell'
                    })
                logger.info(f"[SQL Errors] PowerShell retornou {len(errors)} erros para {server_id}")
            else:
                logger.warning(f"[SQL Errors] Plano B (PowerShell) tambem falhou para {server_id}")
                source_method = 'powershell_failed'

        except Exception as ps_err:
            logger.error(f"[SQL Errors] Ambos os planos falharam para {server_id}: SQL={sql_err}, PS={ps_err}")
            source_method = 'all_failed'

    return {
        # 2026-08-06: era 'success': True incondicional -- mesmo com
        # source_method='all_failed' (xp_readerrorlog E PowerShell falharam)
        # o endpoint dizia sucesso com errors=[], e o card mostrava "0 erros"
        # a azul. Um zero que significa "nao consegui ler" apresentado como
        # "esta tudo bem". Escondeu durante semanas os 18456 do SQLHDSPRD214.
        # O campo 'source' ja carregava a verdade; so' nao era honrado aqui.
        'success': source_method not in ('all_failed', 'powershell_failed'),
        'server_id': server_id,
        'hours': hours,
        'errors': errors,
        'total_count': len(errors),
        'source': source_method
    }

@app.get("/space-dashboard")
async def space_dashboard_page():
    """
    Interface HTML do dashboard de análise de espaço
    ROADMAP SEMANA 1: Interface Visual
    """
    from fastapi.responses import FileResponse
    
    dashboard_path = _tpl("space_dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    else:
        return HTMLResponse(content=f"""
<!DOCTYPE html>
<html>
<head>
    <title>Space Dashboard - Not Found</title>
    <style>
        body {{ font-family: Arial; padding: 40px; text-align: center; background: #1a1a1a; color: #fff; }}
        h1 {{ color: #ef4444; }}
        .info {{ background: #374151; padding: 20px; border-radius: 8px; margin: 20px auto; max-width: 600px; }}
        code {{ background: #1f2937; padding: 4px 8px; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>Space Dashboard Template Not Found</h1>
    <div class="info">
        <p>O arquivo <code>templates/space_dashboard.html</code> não foi encontrado.</p>
        <p>Certifique-se de criar o arquivo HTML do dashboard.</p>
        <p><a href="/docs" style="color: #60a5fa;">Ver API Documentation</a></p>
    </div>
</body>
</html>
        """, status_code=404)

@app.get("/portal-vanilla")
async def portal_vanilla():
    """Portal em Vanilla JS - sem conflitos de CDN"""
    from fastapi.responses import FileResponse
    return FileResponse(_tpl("legacy/watcherdb_portal_legacy_vanilla.html"))

@app.get("/watcherdb")
async def watcherdb(request: Request):
    """Watcher DB - Portal de Monitoramento SQL Server"""
    nonce = getattr(request.state, "csp_nonce", "")
    # TemplateResponse new-style (request como 1o arg): o shim old-style foi
    # REMOVIDO no starlette 1.0 — old-style rebenta com "unhashable type:
    # 'dict'" no bundle (incidente instalacao 2026-08-10). A assinatura nova
    # funciona em 0.50 (dev) E 1.0 (build); o starlette injecta request no
    # contexto automaticamente.
    return _jinja_templates.TemplateResponse(
        request,
        "watcherdb_portal.html",
        {"csp_nonce": nonce},
    )

@app.get("/watcherdb/v2")
async def watcherdb_v2(request: Request):
    """WatcherDB V2 Portal — htmx + Web Components"""
    nonce = getattr(request.state, "csp_nonce", "")
    return _jinja_templates.TemplateResponse(
        request,
        "watcherdb_portal_v2.html",
        {"csp_nonce": nonce},
    )

@app.get("/watcherdb/control")
async def watcherdb_control(request: Request):
    """WatcherDB Control — Admin panel for users, auth log, sessions, config"""
    # Mesmo interruptor do RBAC do LIVE (config.yaml security.rbac_live_admin_only):
    # o shell do painel era servido a qualquer sessao valida; os endpoints por
    # tras dele ja' exigem admin (_require_admin), logo um viewer via o ecra e
    # apanhava 403 em cada chamada -- UX enganadora. Com a flag ligada, o proprio
    # ecra passa a 403. Desligado por omissao (QA externo 2026-08-16, decisao 2).
    try:
        from api.routers.live_monitoring import _rbac_live_enabled
        if _rbac_live_enabled():
            from api.routers.auth_compat import _require_admin
            await _require_admin(request)
    except HTTPException:
        raise
    except Exception:
        pass  # falha de config nunca deve trancar o painel
    nonce = getattr(request.state, "csp_nonce", "")
    return _jinja_templates.TemplateResponse(
        request,
        "watcherdb_control.html",
        {"csp_nonce": nonce},
    )

@app.get("/portal-corrected")
async def portal_corrected():
    """Portal corrigido - Filegroups e ordenação corretos"""
    from fastapi.responses import FileResponse
    return FileResponse(_tpl("legacy/watcherdb_portal_legacy_corrected.html"))

# ============================================================================
# ARQUIVOS ESTÁTICOS
# ============================================================================

@app.get("/static/{file_path:path}")
async def serve_static_files(file_path: str):
    """Servir arquivos estáticos (CSS, JS, etc.)"""
    static_path = _static(file_path)
    if os.path.exists(static_path):
        return FileResponse(static_path)
    else:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

# ============================================================================
# ENDPOINT PARA LISTAR SERVIDORES
# ============================================================================

@app.get("/api/servers")
async def get_servers():
    """Endpoint para listar servidores disponíveis.

    E6: fonte = inventario da BD (services.inventory_repo), fallback ficheiro local;
    fallback final sql_servers.json mantido por compatibilidade (a remover em M1).
    """
    try:
        servers = []

        # Fonte principal: inventario (BD -> fallback servers.json local)
        if True:
            try:
                from services.inventory_repo import get_inventory_repo
                monitored = get_inventory_repo().servers(enabled_only=False, require_credentials=True)
                for server in monitored:
                    if server.get('enabled', True):  # Apenas servidores habilitados
                        servers.append({
                            'id': server.get('id', ''),
                            'name': server.get('id', ''),
                            'host': server.get('host', ''),
                            'instance': server.get('instance', ''),
                            'environment': server.get('environment', 'production'),
                            'description': server.get('description', ''),
                            'status': 'Online',
                            'database_count': server.get('database_count', 0),
                            'has_alwayson': server.get('has_alwayson', False)
                        })
            except Exception as e:
                logger.warning(f"Erro ao ler inventario (inventory_repo): {e}")

        # Fallback para sql_servers.json se inventario vazio
        if not servers:
            sql_servers_path = SQL_SERVERS_CONFIG_PATH
            if sql_servers_path.exists():
                try:
                    with open(sql_servers_path, 'r', encoding='utf-8') as f:
                        sql_data = json.load(f)

                    for server in sql_data.get('servers', []):
                        servers.append({
                            'id': server.get('id', ''),
                            'name': server.get('id', ''),
                            'host': server.get('host', ''),
                            'instance': server.get('instance', ''),
                            'environment': server.get('environment', 'production'),
                            'description': server.get('description', ''),
                            'status': 'Online'
                        })
                except Exception as e:
                    logger.warning(f"Erro ao ler sql_servers.json: {e}")

        return JSONResponse(content={
            'success': True,
            'servers': servers,
            'total': len(servers),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Erro ao listar servidores: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'servers': [],
                'total': 0,
                'timestamp': datetime.now().isoformat()
            }
        )

# ============================================================================
# ENDPOINTS CORRIGIDOS PARA DASHBOARD
# ============================================================================

@app.get("/api/monitoring/space/server/{server_id}/dashboard")
async def get_dashboard_data(server_id: str):
    """Endpoint corrigido para dados do dashboard"""
    try:
        from modules.monitoring.dashboard_fixes import DashboardFixes
        from modules.monitoring.monitoring import SQLServerMonitoring
        
        # Criar instância das correções
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        dashboard_fixes = DashboardFixes(sql_monitoring)
        
        # Obter dados corrigidos
        summary = await dashboard_fixes.get_dashboard_summary(server_id)
        
        if 'error' in summary:
            return JSONResponse(status_code=500, content={"success": False, "error": summary['error']})
        
        # Garantir que filegroups existe
        filegroups = summary.get('filegroups', [])
        
        # Estruturar resposta
        response = {
            'success': True,
            'server_id': server_id,
            'timestamp': datetime.now().isoformat(),
            'data': {
                'summary': {
                    'total_filegroups': summary.get('total_filegroups', 0),
                    'overflow_count': summary.get('overflow_count', 0),
                    'critical_count': summary.get('critical_count', 0),
                    'warning_count': summary.get('warning_count', 0),
                    'ok_count': summary.get('ok_count', 0),
                    'total_size_gb': summary.get('total_size_gb', 0),
                    'total_used_gb': summary.get('total_used_gb', 0),
                    'average_usage_percent': summary.get('average_usage_percent', 0)
                },
                'filegroups': filegroups
            }
        }
        
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"Erro no endpoint dashboard: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
        )

@app.get("/api/monitoring/space/server/{server_id}/dashboard/health")
async def get_dashboard_health(server_id: str):
    """Endpoint para health score do dashboard"""
    try:
        from modules.monitoring.dashboard_fixes import DashboardFixes
        from modules.monitoring.monitoring import SQLServerMonitoring
        
        # Criar instância das correções
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        dashboard_fixes = DashboardFixes(sql_monitoring)
        
        # Obter resumo
        summary = await dashboard_fixes.get_dashboard_summary(server_id)
        
        if 'error' in summary:
            return JSONResponse(status_code=500, content={"success": False, "error": summary['error']})
        
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
        
        # Gerar recomendações
        recommendations = []
        if overflow_count > 0:
            recommendations.append(f"🚨 URGENTE: {overflow_count} filegroup(s) em overflow - Ação imediata necessária!")
        if critical_count > 0:
            recommendations.append(f"🔴 CRÍTICO: {critical_count} filegroup(s) crítico(s) - Planejar expansão em 24-48h")
        if warning_count > 0:
            recommendations.append(f"🟡 ATENÇÃO: {warning_count} filegroup(s) com aviso - Monitorar próximos 7 dias")
        if overflow_count == 0 and critical_count == 0 and warning_count == 0:
            recommendations.append("✅ Sistema saudável - Nenhuma ação imediata necessária")
        
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
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat()
        }
        
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"Erro no endpoint health: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'server_id': server_id,
                'timestamp': datetime.now().isoformat()
            }
        )

# ============================================================================
# ENDPOINTS: Memory Analysis
# ============================================================================

@app.get("/api/monitoring/memory/server/{server_id}")
async def get_memory_analysis(server_id: str):
    """Análise de memória de um servidor específico"""
    try:
        # CRITICAL: reusar a instancia GLOBAL de sql_monitoring criada no
        # startup, em vez de criar uma nova a cada request. Antes:
        #   sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        # Isso criava um novo SQLServerExecutor a cada chamada (4 workers),
        # nao reaproveitava o pool, e cada request gerava overhead de init
        # (`SQLServerMonitoring initialized` + `Loaded N physical servers`).
        sql_monitoring = app.state.sql_monitoring
        if sql_monitoring is None:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "SQL Monitoring not initialized"}
            )
        
        # T-fix 2026-06-09: NAO fazer replace('_','\\') — explode IDs com underscore no
        # host (ex: CN_SQL_REVCDASH_PRD_I01). execute_query resolve por ID exato (Strategy 1).
        # [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: Fix2 parsing]
        server_name = server_id
        display_name = server_id.replace('_DEFAULT', '')
        
        logger.info(f"🧠 Analisando memória do servidor: {server_id}")

        # Executar análise SQL, coleta OS counters e processos em paralelo
        sql_task = asyncio.create_task(get_server_memory_analysis(server_name, sql_monitoring))
        os_task = asyncio.create_task(get_windows_memory_counters(server_id))
        processes_task = asyncio.create_task(get_windows_processes_memory(server_id))

        # Aguardar análise SQL (principal) — wait_for 20s.
        # A query principal e' rapida (~150ms) mas o get_server_memory_analysis
        # corre 8 queries secundarias em paralelo (sys.dm_os_buffer_descriptors,
        # OOM events via xp_readerrorlog, etc.). Cada uma tem o seu proprio
        # wait_for(8s) interno, mas o gather espera por todas — 20s da margem.
        try:
            data = await asyncio.wait_for(sql_task, timeout=20.0)
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ SQL memory analysis timeout (20s) para {server_id} — devolvendo erro")
            if not sql_task.done():
                sql_task.cancel()
                try:
                    await sql_task
                except (asyncio.CancelledError, Exception):
                    pass
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "error": "SQL connection timeout (15s) — server may be unreachable or instance name incorrect",
                    "server_id": server_id,
                    "server_name": display_name,
                    "timestamp": datetime.now().isoformat()
                }
            )

        # Aguardar OS counters + processos EM PARALELO via gather (nao sequencial).
        # Timeout 12s combinado para AMBAS as tasks. Antes eram dois wait_for(25)
        # consecutivos = ate 50s de hang quando o servidor remoto bloqueia em
        # WinRM handshake (subprocess Windows nao mata o cmd.exe filho de forma
        # fiavel, por isso o wait_for atinge o limite completo). Agora ambas
        # correm em paralelo com um unico timeout combinado.
        os_counters = None
        top_processes = []
        try:
            os_counters, top_processes = await asyncio.wait_for(
                asyncio.gather(os_task, processes_task, return_exceptions=True),
                timeout=12.0
            )
            # gather com return_exceptions=True devolve excepcoes como valores
            if isinstance(os_counters, Exception):
                logger.warning(f"⚠️ OS counters falhou para {server_id}: {os_counters}")
                os_counters = None
            if isinstance(top_processes, Exception):
                logger.warning(f"⚠️ Processos falhou para {server_id}: {top_processes}")
                top_processes = []
            else:
                logger.info(
                    f"📊 OS={'OK' if os_counters else 'None'}, "
                    f"Procs={len(top_processes) if top_processes else 0} para {server_id}"
                )
        except asyncio.TimeoutError:
            # Timeout combinado — cancelar ambas e devolver so dados SQL
            for t in (os_task, processes_task):
                if not t.done():
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
            logger.warning(
                f"⚠️ Timeout 12s ao coletar OS counters/processos para {server_id} "
                f"— devolvendo so dados SQL"
            )
            os_counters = None
            top_processes = []

        # Adicionar top_processes ao nível raiz do data (frontend espera aqui)
        data["top_processes"] = top_processes if top_processes else []

        if os_counters:
            # Aplicar análise OS
            os_analysis = analyze_os_memory_snapshot(
                available_mb=os_counters.get('available_mb'),
                pages_sec=os_counters.get('pages_per_sec'),
                page_reads_sec=os_counters.get('page_reads_per_sec'),
            )
            data["os_memory_analysis"] = {
                "available": True,
                "counters": os_counters,
                "analysis": os_analysis
            }

            # Adicionar campos de OS ao nível raiz (frontend espera aqui)
            data["os_available_mb"] = os_counters.get('available_mb')
            data["os_pages_per_sec"] = os_counters.get('pages_per_sec')
            data["os_page_reads_per_sec"] = os_counters.get('page_reads_per_sec')

            # Adicionar alertas baseados na análise OS
            if os_analysis.get("severity") in ["warning", "critical"]:
                os_alerts = []
                severity = os_analysis.get("severity")
                reasons = os_analysis.get("reasons", [])

                for reason in reasons:
                    os_alerts.append({
                        'level': 'warning' if severity == 'warning' else 'danger',
                        'message': f"🖥️ OS Memory: {reason}"
                    })

                # Adicionar aos alertas existentes
                if 'alerts' not in data:
                    data['alerts'] = []
                data['alerts'].extend(os_alerts)
        else:
            # Plano D: usar DMV fallback (available_physical_memory_kb da query SQL principal)
            dmv_available = data.get('os_available_mb_dmv')
            if dmv_available and dmv_available > 0:
                logger.info(f"📡 [Memory Counters] Plano D (DMV fallback): os_available_mb={dmv_available} para {server_id}")
                data["os_memory_analysis"] = {
                    "available": True,
                    "counters": {
                        'available_mb': dmv_available,
                        'pages_per_sec': None,
                        'page_reads_per_sec': None
                    },
                    "analysis": analyze_os_memory_snapshot(dmv_available, None, None),
                    "source": "DMV_fallback"
                }
                data["os_available_mb"] = dmv_available
                data["os_pages_per_sec"] = None
                data["os_page_reads_per_sec"] = None
            else:
                data["os_memory_analysis"] = {
                    "available": False,
                    "message": "Não foi possível coletar counters de memória do SO (PowerShell/WMI/Intelligence/DMV)"
                }
                data["os_available_mb"] = None
                data["os_pages_per_sec"] = None
                data["os_page_reads_per_sec"] = None
        
        return {
            "success": True,
            "server_id": server_id,
            "server_name": display_name,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Erro na análise de memória do servidor {server_id}: {e}", exc_info=True)
        error_detail = str(e)
        
        # Adicionar mais contexto ao erro se possível
        if "Query falhou" in error_detail:
            error_detail += f" (Verifique: conexão SQL, permissões, servidor acessível)"
        elif "not found in configuration" in error_detail:
            error_detail += f" (Verifique: server_id no formato correto, servidor existe em sql_servers.json)"
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "server_id": server_id,
                "error": error_detail,
                "timestamp": datetime.now().isoformat(),
                "suggestion": "Verifique se o servidor está acessível e se as credenciais estão corretas"
            }
        )


@app.post("/api/monitoring/memory/os-snapshot/{server_id}")
async def post_os_memory_snapshot(server_id: str, request: Request, payload: Dict = Body(...)):
    """
    Recebe um snapshot de memória do SO (coletado via PowerShell/agent)
    e aplica a análise consolidada de memória de OS.

    Espera JSON no formato:
    {
        "available_mb": 1234.0,
        "pages_per_sec": 50.0,
        "page_reads_per_sec": 10.0
    }
    """
    from api.routers.auth_compat import _require_admin
    await _require_admin(request)
    try:
        logger.info(f"📥 Recebendo OS memory snapshot para {server_id}")

        available_mb = payload.get("available_mb")
        pages_sec = payload.get("pages_per_sec")
        page_reads_sec = payload.get("page_reads_per_sec")

        os_analysis = analyze_os_memory_snapshot(
            available_mb=available_mb,
            pages_sec=pages_sec,
            page_reads_sec=page_reads_sec,
        )

        return {
            "success": True,
            "server_id": server_id,
            "snapshot": {
                "available_mb": available_mb,
                "pages_per_sec": pages_sec,
                "page_reads_per_sec": page_reads_sec,
            },
            "analysis": os_analysis,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Erro ao processar OS memory snapshot para {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ENDPOINTS: CPU Analysis
# ============================================================================

@app.get("/api/monitoring/cpu/server/{server_id}")
async def get_cpu_analysis(server_id: str):
    """Análise de CPU de um servidor específico"""
    try:
        # CRITICAL: reusar a instancia GLOBAL (ver get_memory_analysis para
        # explicacao). Antes criava nova a cada request com 4 workers,
        # esgotava o pool, e o discovery em background bloqueava tudo.
        sql_monitoring = app.state.sql_monitoring
        if sql_monitoring is None:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "SQL Monitoring not initialized"}
            )

        # T-fix 2026-06-09: NAO replace('_','\\') (explode IDs multi-underscore). [WAIVER 2026-06-09 | Fix2]
        server_name = server_id
        display_name = server_id.replace('_DEFAULT', '')
        logger.info(f"🧠 CPU: analisando {server_id}")

        # wait_for 15s — antes nao tinha timeout e ficava preso 5+ min no
        # pyodbc.connect quando o servidor remoto nao respondia ao TCP/handshake
        try:
            data = await asyncio.wait_for(
                get_server_cpu_analysis(server_name, sql_monitoring),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ SQL CPU analysis timeout (15s) para {server_id} — devolvendo erro")
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "error": "SQL connection timeout (15s) — server may be unreachable or instance name incorrect",
                    "server_id": server_id,
                    "server_name": display_name,
                    "timestamp": datetime.now().isoformat()
                }
            )

        # Buscar processos do Windows com maior consumo de CPU (Plano A PowerShell, ja tem timeout interno)
        try:
            processes = await asyncio.wait_for(
                get_windows_processes_cpu(server_id),
                timeout=12.0
            )
            data["top_processes"] = processes
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Erro/timeout ao obter processos do Windows para {server_id}: {e}")
            data["top_processes"] = []

        return {
            "success": True,
            "server_id": server_id,
            "server_name": display_name,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro CPU {server_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# ============================================================================
# PLANO A: PowerShell Remoto via Invoke-Command
# PLANO B: WMI via Python (fallback quando PowerShell falha)
# CPU + MEMORY
# ============================================================================

def _wmi_get_processes_cpu(server_name: str, top_n: int = 15) -> Dict:
    """
    PLANO B (CPU): Obtém processos via WMI (Python).
    Funciona quando PowerShell remoto está bloqueado mas WMI/DCOM está liberado.
    """
    try:
        import wmi

        # Conectar ao servidor remoto via WMI
        conn = wmi.WMI(computer=server_name)

        # Obter processos com métricas
        processes = []
        for proc in conn.Win32_Process():
            try:
                working_set = int(proc.WorkingSetSize) if proc.WorkingSetSize else 0
                # WMI não fornece CPU% diretamente, usamos UserModeTime + KernelModeTime
                user_time = int(proc.UserModeTime) if proc.UserModeTime else 0
                kernel_time = int(proc.KernelModeTime) if proc.KernelModeTime else 0
                total_time = (user_time + kernel_time) / 10_000_000  # 100-nanosecond units to seconds

                processes.append({
                    'Name': proc.Name.replace('.exe', '') if proc.Name else 'Unknown',
                    'PID': int(proc.ProcessId) if proc.ProcessId else 0,
                    'CPU': round(total_time, 2),
                    'CPUPercent': 0,  # Será calculado abaixo se possível
                    'MemoryMB': round(working_set / (1024 * 1024), 2),
                    'Threads': int(proc.ThreadCount) if proc.ThreadCount else 0
                })
            except Exception:
                continue

        # Ordenar por CPU time e pegar top N
        processes.sort(key=lambda x: x['CPU'], reverse=True)
        top_processes = processes[:top_n]

        return {
            'success': True,
            'processes': top_processes,
            'method': 'WMI'
        }

    except Exception as e:
        return {'error': f'WMI error: {str(e)[:100]}', 'success': False, 'processes': []}


def _powershell_get_processes_cpu(server_name: str, top_n: int = 15, timeout: int = 8) -> Dict:
    """
    PLANO A (CPU): Obtém processos via PowerShell remoto com cálculo de CPU%.
    """
    import subprocess
    import json
    import base64

    # Script que calcula CPU% real com duas amostras
    remote_script = '''
$ErrorActionPreference='SilentlyContinue'
$sample1 = Get-Process | Select-Object Id, ProcessName, @{n='CPU';e={$_.CPU}}, @{n='MemoryMB';e={[math]::Round($_.WorkingSet64 / 1MB, 2)}}
Start-Sleep -Milliseconds 500
$sample2 = Get-Process | Select-Object Id, ProcessName, @{n='CPU';e={$_.CPU}}
$results = @()
foreach ($proc1 in $sample1) {
    $proc2 = $sample2 | Where-Object {$_.Id -eq $proc1.Id}
    if ($proc2) {
        $cpuDelta = $proc2.CPU - $proc1.CPU
        $cpuPercent = [math]::Round($cpuDelta * 2, 2)
        if ($cpuPercent -gt 0) {
            $results += [PSCustomObject]@{
                Name = $proc1.ProcessName
                PID = $proc1.Id
                CPU = [math]::Round($proc1.CPU, 2)
                CPUPercent = $cpuPercent
                MemoryMB = $proc1.MemoryMB
            }
        }
    }
}
$results | Sort-Object CPUPercent -Descending | Select-Object -First TOP_N | ConvertTo-Json -Depth 2
'''.replace('TOP_N', str(top_n))

    local_script = f'Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {remote_script} }}'
    encoded = base64.b64encode(local_script.encode('utf-16-le')).decode('ascii')
    cmd = f'powershell -NoProfile -EncodedCommand {encoded}'

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            return {'error': result.stderr[:200] if result.stderr else 'PS error', 'success': False, 'processes': []}

        output = result.stdout.strip()
        if not output:
            return {'error': 'Empty PS response', 'success': False, 'processes': []}

        if output.startswith('{') or output.startswith('['):
            processes = json.loads(output)
            if isinstance(processes, dict):
                processes = [processes]

            for proc in processes:
                proc.setdefault('CPUPercent', 0)
                proc.setdefault('CPU', 0)
                proc.setdefault('MemoryMB', 0)

            return {'success': True, 'processes': processes, 'method': 'PowerShell'}

        return {'error': 'Invalid PS response', 'success': False, 'processes': []}

    except subprocess.TimeoutExpired:
        return {'error': f'PS Timeout ({timeout}s)', 'success': False, 'processes': []}
    except Exception as e:
        return {'error': str(e)[:100], 'success': False, 'processes': []}


def _sync_get_windows_processes_cpu(server_name: str, top_n: int = 15, timeout: int = 10) -> Dict:
    """
    Coleta processos de CPU com fallback: PowerShell -> WMI.
    """
    # PLANO A: Tentar PowerShell primeiro (fornece CPU% real)
    logger.info(f"📡 [CPU Processes] Plano A: PowerShell para {server_name}")
    result = _powershell_get_processes_cpu(server_name, top_n, timeout=8)

    if result and result.get('success'):
        logger.info(f"✅ [CPU Processes] Plano A funcionou para {server_name}: {len(result.get('processes', []))} processos")
        return result

    # PLANO B: Fallback para WMI
    logger.info(f"📡 [CPU Processes] Plano B: WMI para {server_name} (PowerShell falhou: {result.get('error', 'N/A')})")
    result = _wmi_get_processes_cpu(server_name, top_n)

    if result and result.get('success'):
        logger.info(f"✅ [CPU Processes] Plano B (WMI) funcionou para {server_name}: {len(result.get('processes', []))} processos")
        return result

    logger.warning(f"❌ [CPU Processes] Ambos planos falharam para {server_name}: {result.get('error', 'N/A')}")
    return result


async def get_windows_processes_cpu(server_id: str, top_n: int = 15) -> List[Dict]:
    """
    Obtém os processos do Windows com maior consumo de CPU.
    Estratégia: PowerShell (Plano A) -> WMI (Plano B).
    """
    try:
        server_name = server_id.split('_')[0] if '_' in server_id else server_id
        logger.info(f"🔄 [CPU Processes] Iniciando coleta para {server_name}")

        result = await asyncio.to_thread(_sync_get_windows_processes_cpu, server_name, top_n, 20)

        if result and result.get('success'):
            processes = result.get('processes', [])
            method = result.get('method', 'Unknown')
            logger.info(f"✅ [CPU Processes] {server_id} via {method}: {len(processes)} processos")
            return processes
        else:
            error_msg = result.get('error', 'Unknown') if result else 'No result'
            logger.warning(f"⚠️ [CPU Processes] Falha em {server_id}: {error_msg}")
            return []

    except Exception as e:
        logger.warning(f"⚠️ [CPU Processes] Erro geral de {server_id}: {type(e).__name__}: {e}")
        return []

def _intelligence_get_memory_counters(server_name: str) -> Optional[Dict]:
    """
    PLANO C: Obtém counters de memória via WatcherDB_Intelligence DB.
    Usa a view vw_OS_Memory_Current que é populada pelo serviço de coleta WMI separado.
    """
    try:
        from api.connection_pool import execute_on_intelligence
        query = f"""
            SELECT TOP 1
                Available_MB,
                Pages_Per_Sec,
                Page_Reads_Sec,
                Percent_Committed,
                Commit_Limit_MB,
                Commit_Total_MB,
                Collection_Method,
                Update_TS
            FROM dbo.vw_OS_Memory_Current WITH (NOLOCK)
            WHERE Hostname = '{server_name}'
        """
        rows = execute_on_intelligence(query)
        if rows and len(rows) > 0:
            row = rows[0]
            update_ts = row.get('Update_TS')
            # Verificar freshness (dados com mais de 10 min são considerados stale)
            if update_ts:
                from datetime import datetime, timedelta
                if hasattr(update_ts, 'timestamp'):
                    age_seconds = (datetime.now() - update_ts).total_seconds()
                else:
                    age_seconds = 0
                if age_seconds > 600:
                    return {'error': f'Intelligence data stale ({int(age_seconds)}s)', 'success': False}

            return {
                'available_mb': round(float(row.get('Available_MB', 0)), 2),
                'pages_per_sec': round(float(row.get('Pages_Per_Sec', 0)), 2),
                'page_reads_per_sec': round(float(row.get('Page_Reads_Sec', 0)), 2),
                'success': True,
                'method': 'Intelligence_DB'
            }
        return {'error': f'No data in vw_OS_Memory_Current for {server_name}', 'success': False}

    except Exception as e:
        return {'error': f'Intelligence DB error: {str(e)[:100]}', 'success': False}


def _wmi_get_memory_counters(server_name: str) -> Optional[Dict]:
    """
    PLANO B: Obtém counters de memória via WMI (Python).
    Funciona quando PowerShell remoto está bloqueado mas WMI/DCOM está liberado.
    """
    try:
        import wmi

        # Conectar ao servidor remoto via WMI
        conn = wmi.WMI(computer=server_name)

        # Obter memória disponível via Win32_OperatingSystem
        os_info = conn.Win32_OperatingSystem()[0]
        available_mb = round(int(os_info.FreePhysicalMemory) / 1024, 2)  # KB para MB

        # Tentar obter Page Faults via Win32_PerfFormattedData_PerfOS_Memory
        pages_per_sec = 0
        page_reads_per_sec = 0
        try:
            perf_mem = conn.Win32_PerfFormattedData_PerfOS_Memory()[0]
            pages_per_sec = round(float(perf_mem.PagesPersec), 2) if perf_mem.PagesPersec else 0
            page_reads_per_sec = round(float(perf_mem.PageReadsPersec), 2) if perf_mem.PageReadsPersec else 0
        except Exception:
            pass  # Performance counters podem não estar disponíveis

        return {
            'available_mb': available_mb,
            'pages_per_sec': pages_per_sec,
            'page_reads_per_sec': page_reads_per_sec,
            'success': True,
            'method': 'WMI'
        }

    except Exception as e:
        return {'error': f'WMI error: {str(e)[:100]}', 'success': False}


def _wmi_get_processes_memory(server_name: str, top_n: int = 15) -> Dict:
    """
    PLANO B: Obtém processos via WMI (Python).
    Funciona quando PowerShell remoto está bloqueado mas WMI/DCOM está liberado.
    """
    try:
        import wmi

        # Conectar ao servidor remoto via WMI
        conn = wmi.WMI(computer=server_name)

        # Obter processos ordenados por memória
        processes = []
        for proc in conn.Win32_Process():
            try:
                working_set = int(proc.WorkingSetSize) if proc.WorkingSetSize else 0
                processes.append({
                    'Name': proc.Name.replace('.exe', '') if proc.Name else 'Unknown',
                    'MemoryMB': round(working_set / (1024 * 1024), 2),
                    'PID': int(proc.ProcessId) if proc.ProcessId else 0,
                    'CPU': 0,  # WMI não fornece CPU% diretamente de forma simples
                    'Threads': int(proc.ThreadCount) if proc.ThreadCount else 0
                })
            except Exception:
                continue

        # Ordenar por memória e pegar top N
        processes.sort(key=lambda x: x['MemoryMB'], reverse=True)
        top_processes = processes[:top_n]

        return {
            'success': True,
            'processes': top_processes,
            'method': 'WMI'
        }

    except Exception as e:
        return {'error': f'WMI error: {str(e)[:100]}', 'success': False, 'processes': []}


def _powershell_get_memory_counters(server_name: str, timeout: int = 15) -> Optional[Dict]:
    """
    PLANO A: Obtém counters de memória via PowerShell remoto.
    Optimizado: 1 única chamada Get-Counter com 3 counters (1s sampling em vez de 3s).
    Timeout aumentado de 8s para 15s para acomodar WinRM + sampling.
    """
    import subprocess
    import json
    import base64

    remote_script = '''
$ErrorActionPreference='SilentlyContinue'
try {
    $c = (Get-Counter "\\Memory\\Available MBytes","\\Memory\\Pages/sec","\\Memory\\Page Reads/sec" -ErrorAction SilentlyContinue).CounterSamples
    @{
        available_mb = [math]::Round($c[0].CookedValue, 2)
        pages_per_sec = [math]::Round($c[1].CookedValue, 2)
        page_reads_per_sec = [math]::Round($c[2].CookedValue, 2)
        success = $true
    } | ConvertTo-Json -Depth 2
} catch {
    @{ success = $false; error = $_.Exception.Message } | ConvertTo-Json -Depth 2
}
'''

    local_script = f'Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {remote_script} }}'
    encoded = base64.b64encode(local_script.encode('utf-16-le')).decode('ascii')
    cmd = f'powershell -NoProfile -EncodedCommand {encoded}'

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            return {'error': result.stderr[:200] if result.stderr else 'PS error', 'success': False}

        output = result.stdout.strip()
        if not output or not output.startswith('{'):
            return {'error': 'Invalid PS response', 'success': False}

        data = json.loads(output)
        if data.get('success'):
            return {
                'available_mb': data.get('available_mb'),
                'pages_per_sec': data.get('pages_per_sec'),
                'page_reads_per_sec': data.get('page_reads_per_sec'),
                'success': True,
                'method': 'PowerShell'
            }
        return {'error': data.get('error', 'PS error'), 'success': False}

    except subprocess.TimeoutExpired:
        return {'error': f'PS Timeout ({timeout}s)', 'success': False}
    except Exception as e:
        return {'error': str(e)[:100], 'success': False}


def _powershell_get_processes_memory(server_name: str, top_n: int = 15, timeout: int = 8) -> Dict:
    """
    PLANO A: Obtém processos via PowerShell remoto.
    """
    import subprocess
    import json
    import base64

    remote_script = '''
$ErrorActionPreference='SilentlyContinue'
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First TOP_N | ForEach-Object {
    [PSCustomObject]@{
        Name = $_.ProcessName
        MemoryMB = [math]::Round($_.WorkingSet64 / 1MB, 2)
        PID = $_.Id
        CPU = [math]::Round($_.CPU, 2)
        Threads = $_.Threads.Count
    }
} | ConvertTo-Json -Depth 2
'''.replace('TOP_N', str(top_n))

    local_script = f'Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {remote_script} }}'
    encoded = base64.b64encode(local_script.encode('utf-16-le')).decode('ascii')
    cmd = f'powershell -NoProfile -EncodedCommand {encoded}'

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            return {'error': result.stderr[:200] if result.stderr else 'PS error', 'success': False, 'processes': []}

        output = result.stdout.strip()
        if not output:
            return {'error': 'Empty PS response', 'success': False, 'processes': []}

        if output.startswith('{') or output.startswith('['):
            processes = json.loads(output)
            if isinstance(processes, dict):
                processes = [processes]

            for proc in processes:
                proc.setdefault('MemoryMB', 0)
                proc.setdefault('CPU', 0)
                proc.setdefault('Threads', 0)

            return {'success': True, 'processes': processes, 'method': 'PowerShell'}

        return {'error': 'Invalid PS response', 'success': False, 'processes': []}

    except subprocess.TimeoutExpired:
        return {'error': f'PS Timeout ({timeout}s)', 'success': False, 'processes': []}
    except Exception as e:
        return {'error': str(e)[:100], 'success': False, 'processes': []}


def _sync_get_windows_memory_counters(server_name: str, timeout: int = 10) -> Optional[Dict]:
    """
    Coleta counters de memória com fallback: PowerShell -> WMI.
    """
    # PLANO A: Tentar PowerShell primeiro (mais dados disponíveis)
    logger.info(f"📡 [Memory Counters] Plano A: PowerShell para {server_name}")
    result = _powershell_get_memory_counters(server_name, timeout=15)

    if result and result.get('success'):
        logger.info(f"✅ [Memory Counters] Plano A funcionou para {server_name}")
        return result

    # PLANO B: Fallback para WMI
    logger.info(f"📡 [Memory Counters] Plano B: WMI para {server_name} (PowerShell falhou: {result.get('error', 'N/A')})")
    result = _wmi_get_memory_counters(server_name)

    if result and result.get('success'):
        logger.info(f"✅ [Memory Counters] Plano B (WMI) funcionou para {server_name}")
        return result

    # PLANO C: Fallback para Intelligence DB (vw_OS_Memory_Current)
    logger.info(f"📡 [Memory Counters] Plano C: Intelligence DB para {server_name} (WMI falhou: {result.get('error', 'N/A')})")
    result_c = _intelligence_get_memory_counters(server_name)

    if result_c and result_c.get('success'):
        logger.info(f"✅ [Memory Counters] Plano C (Intelligence DB) funcionou para {server_name}")
        return result_c

    logger.warning(f"❌ [Memory Counters] Todos os planos falharam para {server_name}: PS={result.get('error', 'N/A')}, WMI={result.get('error', 'N/A')}, Intel={result_c.get('error', 'N/A') if result_c else 'None'}")
    return result


def _sync_get_windows_processes_memory(server_name: str, top_n: int = 15, timeout: int = 10) -> Dict:
    """
    Coleta processos de memória com fallback: PowerShell -> WMI.
    """
    # PLANO A: Tentar PowerShell primeiro
    logger.info(f"📡 [Memory Processes] Plano A: PowerShell para {server_name}")
    result = _powershell_get_processes_memory(server_name, top_n, timeout=8)

    if result and result.get('success'):
        logger.info(f"✅ [Memory Processes] Plano A funcionou para {server_name}: {len(result.get('processes', []))} processos")
        return result

    # PLANO B: Fallback para WMI
    logger.info(f"📡 [Memory Processes] Plano B: WMI para {server_name} (PowerShell falhou: {result.get('error', 'N/A')})")
    result = _wmi_get_processes_memory(server_name, top_n)

    if result and result.get('success'):
        logger.info(f"✅ [Memory Processes] Plano B (WMI) funcionou para {server_name}: {len(result.get('processes', []))} processos")
        return result

    logger.warning(f"❌ [Memory Processes] Ambos planos falharam para {server_name}: {result.get('error', 'N/A')}")
    return result


async def get_windows_memory_counters(server_id: str) -> Optional[Dict]:
    """
    Coleta os counters de memória do Windows.
    Estratégia: PowerShell (Plano A) -> WMI (Plano B).
    """
    try:
        server_name = server_id.split('_')[0] if '_' in server_id else server_id
        logger.info(f"🔄 [Memory Counters] Iniciando coleta para {server_name}")

        result = await asyncio.to_thread(_sync_get_windows_memory_counters, server_name, 20)

        if result and result.get('success'):
            method = result.get('method', 'Unknown')
            counters = {
                'available_mb': result.get('available_mb'),
                'pages_per_sec': result.get('pages_per_sec'),
                'page_reads_per_sec': result.get('page_reads_per_sec')
            }
            logger.info(f"✅ [Memory Counters] {server_id} via {method}: {counters}")
            return counters
        else:
            error_msg = result.get('error', 'Unknown') if result else 'No result'
            logger.warning(f"⚠️ [Memory Counters] Falha em {server_id}: {error_msg}")
            return None

    except Exception as e:
        logger.warning(f"⚠️ [Memory Counters] Erro geral de {server_id}: {type(e).__name__}: {e}")
        return None


async def get_windows_processes_memory(server_id: str, top_n: int = 15) -> List[Dict]:
    """
    Obtém os processos do Windows com maior consumo de memória.
    Estratégia: PowerShell (Plano A) -> WMI (Plano B).
    """
    try:
        server_name = server_id.split('_')[0] if '_' in server_id else server_id
        logger.info(f"🔄 [Memory Processes] Iniciando coleta para {server_name}")

        result = await asyncio.to_thread(_sync_get_windows_processes_memory, server_name, top_n, 20)

        if result and result.get('success'):
            processes = result.get('processes', [])
            method = result.get('method', 'Unknown')
            logger.info(f"✅ [Memory Processes] {server_id} via {method}: {len(processes)} processos")
            return processes
        else:
            error_msg = result.get('error', 'Unknown') if result else 'No result'
            logger.warning(f"⚠️ [Memory Processes] Falha em {server_id}: {error_msg}")
            return []

    except Exception as e:
        logger.warning(f"⚠️ [Memory Processes] Erro geral de {server_id}: {type(e).__name__}: {e}")
        return []

@app.get("/api/monitoring/memory/alwayson/{ag_name}")
async def get_alwayson_memory_analysis(ag_name: str):
    """Comparação de memória entre nodes Always On"""
    try:
        logger.info(f"🔄 Analisando Always On AG: {ag_name}")
        
        # Buscar lista de servidores do AG (usar a mesma lógica do sistema existente)
        # Por enquanto, vamos usar uma lista hardcoded - você pode implementar get_servers_by_ag()
        servers_list = [
            f"SQLIDSPRD03\\I01",  # PRIMARY
            f"SQLIDSPRD04\\I01",  # SECONDARY
        ]
        
        data = get_alwayson_memory_comparison(ag_name, servers_list)
        
        return {
            "success": True,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erro na análise Always On do AG {ag_name}: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "ag_name": ag_name,
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/api/monitoring/memory/summary")
async def get_memory_summary():
    """Resumo de saúde de memória de todos os servidores"""
    try:
        logger.info("📊 Gerando resumo de memória de todos os servidores")
        
        # Usar o sistema de conexão do WatcherDB
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        
        # Obter lista de servidores (usar a mesma lógica do sistema existente)
        try:
            all_servers = sql_monitoring.get_all_servers()
            if not all_servers:
                all_servers = sql_monitoring.servers if hasattr(sql_monitoring, 'servers') else []
        except Exception:
            all_servers = []

        if not all_servers:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Nenhum servidor encontrado",
                    "timestamp": datetime.now().isoformat()
                }
            )

        # Converter server_ids para server_names
        server_names = [server.replace('_', '\\') for server in all_servers]
        
        # Gerar resumo
        summary = get_memory_health_summary(server_names)
        
        return {
            "success": True,
            "data": summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar resumo de memória: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/api/monitoring/memory/server/{server_id}/pressure")
async def get_memory_pressure(server_id: str):
    """Retorna apenas a informação de memory pressure (mais rápido)"""
    try:
        from modules.monitoring.monitoring import SQLServerMonitoring
        # Criar nova instância para garantir que não há cache compartilhado
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        logger.info(f"🆕 Nova instância SQLServerMonitoring criada para {server_id}")

        # T-fix 2026-06-09: NAO replace('_','\\') (explode IDs multi-underscore). [WAIVER 2026-06-09 | Fix2]
        server_name = server_id
        display_name = server_id.replace('_DEFAULT', '')

        logger.info(f"🔄 Atualizando memory pressure do servidor: {server_id}")

        # Buscar dados completos para calcular memory pressure
        query = """
        SELECT
            target_server_memory_mb = (
                SELECT CAST(CAST(cntr_value AS BIGINT) / 1024.0 AS BIGINT)
                FROM sys.dm_os_performance_counters
                WHERE counter_name = 'Target Server Memory (KB)'
                AND object_name LIKE '%Buffer Manager%'
            ),
            total_server_memory_mb = (
                SELECT CAST(CAST(cntr_value AS BIGINT) / 1024.0 AS BIGINT)
                FROM sys.dm_os_performance_counters
                WHERE counter_name = 'Total Server Memory (KB)'
                AND object_name LIKE '%Buffer Manager%'
            ),
            max_server_memory_mb = (
                SELECT CAST(value_in_use AS BIGINT)
                FROM sys.configurations
                WHERE name = 'max server memory (MB)'
            ),
            process_physical_memory_mb = (
                SELECT physical_memory_in_use_kb / 1024
                FROM sys.dm_os_process_memory
            ),
            available_physical_memory_mb = (
                SELECT available_physical_memory_kb / 1024
                FROM sys.dm_os_sys_memory
            ),
            total_physical_memory_mb = (
                SELECT total_physical_memory_kb / 1024
                FROM sys.dm_os_sys_memory
            )
        """

        server_id_for_query = server_id
        logger.info(f"📊 Executando query de memory pressure para: {server_id_for_query}")
        result = await sql_monitoring.execute_query(server_id_for_query, query)

        if not result or not result.get('success') or not result.get('rows'):
            error_msg = result.get('error', 'Erro desconhecido') if result else 'Resultado vazio'
            logger.error(f"❌ Erro ao obter dados de memory pressure para {server_id}: {error_msg}")
            raise Exception(f"Erro ao obter dados de memory pressure: {error_msg}")

        row = result.get('rows', [{}])[0]
        target_mb = int(row.get('target_server_memory_mb', 0) or 0)
        total_mb = int(row.get('total_server_memory_mb', 0) or 0)
        max_server_mb = int(row.get('max_server_memory_mb', 0) or 0)
        process_mb = int(row.get('process_physical_memory_mb', 0) or 0)
        available_mb = int(row.get('available_physical_memory_mb', 0) or 0)
        total_physical_mb = int(row.get('total_physical_memory_mb', 0) or 0)

        logger.info(f"📊 Memory Pressure para {server_id}: target={target_mb}MB, total={total_mb}MB, max={max_server_mb}MB, process={process_mb}MB")

        # Calcular memory pressure de forma inteligente
        pressure_pct = None
        status = 'UNKNOWN'
        calculation_method = 'N/A'

        if target_mb > 0 and total_mb > 0:
            # Método ideal: Total Server Memory / Target Server Memory
            pressure_pct = round((total_mb * 100.0) / target_mb, 2)
            calculation_method = 'buffer_pool'
            if pressure_pct >= 95:
                status = 'HEALTHY'
            elif pressure_pct >= 80:
                status = 'WARNING'
            else:
                status = 'CRITICAL'
        elif process_mb > 0 and max_server_mb > 0:
            # Alternativa: Process Physical Memory / Max Server Memory
            # Quando o buffer pool ainda não foi inicializado mas o processo está usando memória
            pressure_pct = round((process_mb * 100.0) / max_server_mb, 2)
            calculation_method = 'process_vs_max'
            if pressure_pct >= 90:
                status = 'HEALTHY'
            elif pressure_pct >= 70:
                status = 'WARNING'
            else:
                status = 'LOW_USAGE'  # SQL Server ainda não precisa de toda memória configurada
        elif process_mb > 0 and total_physical_mb > 0:
            # Fallback: Process Memory / Total Physical Memory
            pressure_pct = round((process_mb * 100.0) / total_physical_mb, 2)
            calculation_method = 'process_vs_physical'
            if pressure_pct >= 80:
                status = 'HIGH'
            elif pressure_pct >= 50:
                status = 'MODERATE'
            else:
                status = 'LOW'
        else:
            pressure_pct = 0
            status = 'AWAITING_INIT'
            calculation_method = 'none'

        logger.info(f"✅ Memory Pressure calculado para {server_id}: {pressure_pct}% ({status}) via {calculation_method}")

        return {
            "success": True,
            "server_id": server_id,
            "memory_pressure_pct": pressure_pct,
            "memory_pressure_status": status,
            "calculation_method": calculation_method,
            "target_server_memory_mb": target_mb,
            "total_server_memory_mb": total_mb,
            "max_server_memory_mb": max_server_mb,
            "process_physical_memory_mb": process_mb,
            "available_physical_memory_mb": available_mb,
            "total_physical_memory_mb": total_physical_mb,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Erro ao obter memory pressure do servidor {server_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

@app.get("/api/monitoring/memory/servers")
async def get_memory_servers():
    """Lista todos os servidores para análise de memória"""
    try:
        # Usar a mesma lógica do endpoint /api/servers
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        
        servers = []
        
        # Ler do Excel se disponível
        excel_path = "TAP_SQL_Server_Inventory.xlsx"
        if os.path.exists(excel_path):
            import pandas as pd
            try:
                df = pd.read_excel(excel_path)
                if 'Server Name' in df.columns:
                    for _, row in df.iterrows():
                        server_name = str(row['Server Name']).strip()
                        if server_name and server_name != 'nan':
                            servers.append(server_name)
            except Exception as e:
                logger.warning(f"Erro ao ler Excel: {e}")
        
        # Fallback para servidores do sistema
        if not servers:
            try:
                # Usar a mesma lógica do endpoint /api/servers
                all_servers = []
                if hasattr(sql_monitoring, 'servers') and sql_monitoring.servers:
                    all_servers = sql_monitoring.servers
                else:
                    # Fallback para configuração padrão
                    all_servers = [
                        {'name': 'SQLIDSPRD03\\I01', 'server_id': 'SQLIDSPRD03_I01'},
                        {'name': 'SQLHDSTST405\\I01', 'server_id': 'SQLHDSTST405_I01'},
                        {'name': 'SQLHDSTST105\\I01', 'server_id': 'SQLHDSTST105_I01'}
                    ]
                servers = [server['name'] for server in all_servers] if all_servers else []
            except Exception as e:
                logger.warning(f"Erro ao obter servidores do sistema: {e}")
        
        return {
            'success': True,
            'servers': servers,
            'count': len(servers),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao listar servidores para memória: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        )


@app.get("/api/monitoring/memory/all")
async def get_all_servers_memory_analysis():
    """Analisa a memória de todos os servidores"""
    try:
        # Obter lista de servidores
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        
        servers = []
        
        # Ler do Excel se disponível
        excel_path = "TAP_SQL_Server_Inventory.xlsx"
        if os.path.exists(excel_path):
            import pandas as pd
            try:
                df = pd.read_excel(excel_path)
                if 'Server Name' in df.columns:
                    for _, row in df.iterrows():
                        server_name = str(row['Server Name']).strip()
                        if server_name and server_name != 'nan':
                            servers.append(server_name)
            except Exception as e:
                logger.warning(f"Erro ao ler Excel: {e}")
        
        # Fallback para servidores do sistema
        if not servers:
            try:
                # Usar a mesma lógica do endpoint /api/servers
                all_servers = []
                if hasattr(sql_monitoring, 'servers') and sql_monitoring.servers:
                    all_servers = sql_monitoring.servers
                else:
                    # Fallback para configuração padrão
                    all_servers = [
                        {'name': 'SQLIDSPRD03\\I01', 'server_id': 'SQLIDSPRD03_I01'},
                        {'name': 'SQLHDSTST405\\I01', 'server_id': 'SQLHDSTST405_I01'},
                        {'name': 'SQLHDSTST105\\I01', 'server_id': 'SQLHDSTST105_I01'}
                    ]
                servers = [server['name'] for server in all_servers] if all_servers else []
            except Exception as e:
                logger.warning(f"Erro ao obter servidores do sistema: {e}")
        
        if not servers:
            return JSONResponse(
                status_code=404,
                content={
                    'success': False,
                    'error': 'Nenhum servidor encontrado',
                    'timestamp': datetime.now().isoformat()
                }
            )
        # Usar função direta de análise de memória
        # Usar função direta para análise de todos os servidores
        analysis_result = {"data": [], "success": False, "error": "Função não implementada"}
        
        return {
            'success': True,
            'analysis': analysis_result,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro na análise de memória de todos os servidores: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        )

@app.get("/api/monitoring/memory/recommendations")
async def get_memory_recommendations():
    """Gera recomendações de configuração de memória"""
    try:
        # Obter lista de servidores
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        
        servers = []
        
        # Ler do Excel se disponível
        excel_path = "TAP_SQL_Server_Inventory.xlsx"
        if os.path.exists(excel_path):
            import pandas as pd
            try:
                df = pd.read_excel(excel_path)
                if 'Server Name' in df.columns:
                    for _, row in df.iterrows():
                        server_name = str(row['Server Name']).strip()
                        if server_name and server_name != 'nan':
                            servers.append(server_name)
            except Exception as e:
                logger.warning(f"Erro ao ler Excel: {e}")
        
        # Fallback para servidores do sistema
        if not servers:
            try:
                # Usar a mesma lógica do endpoint /api/servers
                all_servers = []
                if hasattr(sql_monitoring, 'servers') and sql_monitoring.servers:
                    all_servers = sql_monitoring.servers
                else:
                    # Fallback para configuração padrão
                    all_servers = [
                        {'name': 'SQLIDSPRD03\\I01', 'server_id': 'SQLIDSPRD03_I01'},
                        {'name': 'SQLHDSTST405\\I01', 'server_id': 'SQLHDSTST405_I01'},
                        {'name': 'SQLHDSTST105\\I01', 'server_id': 'SQLHDSTST105_I01'}
                    ]
                servers = [server['name'] for server in all_servers] if all_servers else []
            except Exception as e:
                logger.warning(f"Erro ao obter servidores do sistema: {e}")
        
        if not servers:
            return JSONResponse(
                status_code=404,
                content={
                    'success': False,
                    'error': 'Nenhum servidor encontrado',
                    'timestamp': datetime.now().isoformat()
                }
            )
        # Usar função direta de análise de memória
        # Usar função direta para análise de todos os servidores
        analysis_result = {"data": [], "success": False, "error": "Função não implementada"}
        
        if analysis_result['data'].empty:
            return JSONResponse(
                status_code=404,
                content={
                    'success': False,
                    'error': 'Nenhum dado de memória coletado',
                    'timestamp': datetime.now().isoformat()
                }
            )
        
        recommendations = {"data": [], "success": False, "error": "Função não implementada"}
        
        return {
            'success': True,
            'recommendations': recommendations.get('data', []) if isinstance(recommendations, dict) else [],
            'summary': analysis_result['summary'],
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao gerar recomendações de memória: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        )

@app.get("/api/monitoring/memory/report")
async def generate_memory_report():
    """Gera relatório completo de análise de memória"""
    try:
        # Obter lista de servidores
        sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance instead of per-request
        
        servers = []
        
        # Ler do Excel se disponível
        excel_path = "TAP_SQL_Server_Inventory.xlsx"
        if os.path.exists(excel_path):
            import pandas as pd
            try:
                df = pd.read_excel(excel_path)
                if 'Server Name' in df.columns:
                    for _, row in df.iterrows():
                        server_name = str(row['Server Name']).strip()
                        if server_name and server_name != 'nan':
                            servers.append(server_name)
            except Exception as e:
                logger.warning(f"Erro ao ler Excel: {e}")
        
        # Fallback para servidores do sistema
        if not servers:
            try:
                # Usar a mesma lógica do endpoint /api/servers
                all_servers = []
                if hasattr(sql_monitoring, 'servers') and sql_monitoring.servers:
                    all_servers = sql_monitoring.servers
                else:
                    # Fallback para configuração padrão
                    all_servers = [
                        {'name': 'SQLIDSPRD03\\I01', 'server_id': 'SQLIDSPRD03_I01'},
                        {'name': 'SQLHDSTST405\\I01', 'server_id': 'SQLHDSTST405_I01'},
                        {'name': 'SQLHDSTST105\\I01', 'server_id': 'SQLHDSTST105_I01'}
                    ]
                servers = [server['name'] for server in all_servers] if all_servers else []
            except Exception as e:
                logger.warning(f"Erro ao obter servidores do sistema: {e}")
        
        if not servers:
            return JSONResponse(
                status_code=404,
                content={
                    'success': False,
                    'error': 'Nenhum servidor encontrado',
                    'timestamp': datetime.now().isoformat()
                }
            )
        # Usar função direta de análise de memória
        # Usar função direta para análise de todos os servidores
        analysis_result = {"data": [], "success": False, "error": "Função não implementada"}
        
        if analysis_result['data'].empty:
            return JSONResponse(
                status_code=404,
                content={
                    'success': False,
                    'error': 'Nenhum dado de memória coletado',
                    'timestamp': datetime.now().isoformat()
                }
            )
        
        # Gerar relatório Excel
        report_path = "memory_report.xlsx"  # Placeholder
        
        return {
            'success': True,
            'report_path': report_path,
            'summary': analysis_result['summary'],
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de memória: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        )

@app.get("/api/monitoring/space/database/{server_id}/{database_name}/filegroups")
async def get_database_filegroups_endpoint(server_id: str, database_name: str):
    """Retorna os filegroups de um database com análise de espaço"""
    try:
        logger.info(f"Getting filegroups for database: {database_name} on server: {server_id}")
        
        engine = SpaceAnalysisEngine(app.state.sql_monitoring)
        
        filegroups = await engine.get_database_filegroups(server_id, database_name)

        # Enriquecer filegroups com alert_level e dados de disco
        if filegroups and len(filegroups) > 0:
            first_fg = filegroups[0]
            if first_fg.get('is_accessible') == False:
                db_state = first_fg.get('database_state', 'UNKNOWN')
                db_state_desc = first_fg.get('database_state_desc', 'N/A')
                logger.warning(f"Database {database_name} em {server_id} esta {db_state}: {db_state_desc}")
            else:
                # Buscar dados de volumes para calcular alert_level
                try:
                    volumes_data = await engine._get_volumes_status(server_id)
                    volumes_lookup = {}
                    worst_disk_free_pct = 100.0
                    worst_disk_available_gb = 0.0
                    for vol in volumes_data:
                        drive = vol.get('Drive', vol.get('drive', '')).upper().rstrip('\\')
                        free_pct = vol.get('FreePercent', vol.get('free_percent', 0))
                        free_gb = vol.get('FreeGB', vol.get('free_gb', 0))
                        volumes_lookup[drive] = {'free_pct': free_pct, 'free_gb': free_gb}
                        if free_pct < worst_disk_free_pct:
                            worst_disk_free_pct = free_pct
                            worst_disk_available_gb = free_gb

                    for fg in filegroups:
                        fg_volume = fg.get('volume', 'N/A').upper().rstrip('\\')
                        if fg_volume and fg_volume != 'N/A' and fg_volume in volumes_lookup:
                            disk_free_pct = volumes_lookup[fg_volume]['free_pct']
                            disk_available_gb = volumes_lookup[fg_volume]['free_gb']
                        elif volumes_lookup:
                            disk_free_pct = worst_disk_free_pct
                            disk_available_gb = worst_disk_available_gb
                        else:
                            disk_free_pct = 100.0
                            disk_available_gb = 0.0

                        fg['free_disk_percent'] = disk_free_pct
                        fg['disk_free_pct'] = disk_free_pct
                        fg['available_disk_gb'] = disk_available_gb

                        max_gb = fg.get('max_gb', 0)
                        total_gb = fg.get('total_gb', 0)
                        potential_growth = max_gb - total_gb if max_gb > 0 and max_gb < 999999 else 0
                        disk_overflow = (potential_growth > disk_available_gb) if (potential_growth > 0 and disk_available_gb > 0) else False
                        fg['disk_overflow_risk'] = disk_overflow
                        fg['alert_level'] = engine._classify_alert_level(
                            fg.get('free_percent', 0), disk_free_pct, disk_overflow, max_gb
                        )
                except Exception as vol_err:
                    logger.warning(f"Erro ao buscar volumes para alert_level: {vol_err}")
                    for fg in filegroups:
                        fg.setdefault('alert_level', 'OK')
                        fg.setdefault('disk_overflow_risk', False)

        return {
            "success": True,
            "server_id": server_id,
            "database_name": database_name,
            "total_filegroups": len(filegroups),
            "filegroups": filegroups
        }
    except Exception as e:
        logger.error(f"Error getting filegroups for {database_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/space/database/{server_id}/{database_name}/files")
async def get_database_files_endpoint(server_id: str, database_name: str):
    """Retorna detalhes dos arquivos (logical names) de um database"""
    try:
        engine = SpaceAnalysisEngine(app.state.sql_monitoring)
        files = await engine.get_database_files(server_id, database_name)
        
        return {
            "success": True,
            "server_id": server_id,
            "database_name": database_name,
            "total_files": len(files),
            "files": files
        }
    except Exception as e:
        logger.error(f"Error getting filegroups for {database_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINTS DE ANÁLISE PREDITIVA
# ============================================================================

from modules.analytics import get_analyzer
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

class PredictiveReportRequest(BaseModel):
    """Request body para geração de relatório preditivo"""
    server_id: str  # Formato: CAGENPRD06_I06
    database_name: str
    filegroup_name: str
    forecast_days: int = 60
    threshold: float = 0.85

@app.post("/api/monitoring/space/filegroup/generate-report")
async def generate_predictive_report(http_request: Request, request: PredictiveReportRequest):
    """
    Gera relatório preditivo de crescimento de filegroup.
    
    Fluxo:
    1. Extrai dados historicos do Intelligence DB
    2. Executa modelo de ML (regressão linear)
    3. Gera relatório HTML interativo com Plotly
    4. Retorna HTML pronto para exibir no modal
    
    Exemplo de uso (via fetch no frontend):
    ```javascript
    const response = await fetch('/api/monitoring/space/filegroup/generate-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            server_name: 'SQLPROD01',
            database_name: 'COMERCIAL',
            filegroup_name: 'PRIMARY',
            forecast_days: 60,
            threshold: 0.85
        })
    });
    const html = await response.text();
    // Injeta no modal
    document.getElementById('modal-content').innerHTML = html;
    ```
    """
    from api.routers.auth_compat import _require_admin
    await _require_admin(http_request)
    try:
        logger.info(f"🔮 Gerando análise preditiva: {request.server_id}/{request.database_name}/{request.filegroup_name}")
        
                # Parse server_id (formato: SERVIDOR_INSTANCIA)
        if '_' in request.server_id:
            parts = request.server_id.rsplit('_', 1)  # Split pelo último underscore
            server_name = parts[0]
            instance_name = parts[1] if len(parts) > 1 else 'DEFAULT'
        else:
            server_name = request.server_id
            instance_name = 'DEFAULT'
        
        logger.info(f"📊 Parsed: server={server_name}, instance={instance_name}")
        
        # Obtém instância do analisador
        analyzer = get_analyzer()
        
        # Executa análise (chama os scripts Python)
        result = analyzer.generate_filegroup_report(
            server_name=server_name,
            database_name=request.database_name,
            filegroup_name=request.filegroup_name,
            forecast_days=request.forecast_days,
            threshold=request.threshold
        )
        
        if not result["success"]:
            logger.error(f"❌ Erro na análise: {result['error']}")
            
            # Verifica se é erro de dados históricos não disponíveis
            if "Não há dados históricos disponíveis" in result["error"]:
                # Retorna HTML elegante para exibir na modal
                elegant_error_html = f"""
                <div style="text-align: center; padding: 40px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; border: 2px solid #334155;">
                    <div style="margin-bottom: 24px;">
                        <i class="fas fa-database" style="font-size: 64px; color: #60a5fa; margin-bottom: 16px;"></i>
                    </div>
                    <h3 style="color: #f1f5f9; font-size: 24px; margin-bottom: 16px; font-weight: 600;">
                        📊 Dados Históricos Não Disponíveis
                    </h3>
                    <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid #3b82f6; border-radius: 8px; padding: 20px; margin-bottom: 24px;">
                        <p style="color: #cbd5e1; font-size: 16px; line-height: 1.6; margin: 0;">
                            <strong>Filegroup:</strong> {request.filegroup_name}<br>
                            <strong>Database:</strong> {request.database_name}<br>
                            <strong>Servidor:</strong> {request.server_id}
                        </p>
                    </div>
                    <p style="color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
                        A análise preditiva requer dados históricos de crescimento para funcionar corretamente.<br>
                        Este filegroup ainda não possui dados suficientes para gerar projeções.
                    </p>
                    <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                        <h4 style="color: #10b981; font-size: 16px; margin: 0 0 8px 0; font-weight: 600;">
                            💡 Próximos Passos
                        </h4>
                        <ul style="color: #6ee7b7; font-size: 14px; text-align: left; margin: 0; padding-left: 20px;">
                            <li>Verifique se o filegroup está sendo monitorado</li>
                            <li>Aguarde alguns dias para acumular dados históricos</li>
                            <li>Use a análise de espaço atual para monitoramento imediato</li>
                        </ul>
                    </div>
                    <button onclick="closeReportModal()" style="background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
                        <i class="fas fa-times"></i> Fechar
                    </button>
                </div>
                """
                return HTMLResponse(content=elegant_error_html, status_code=200)
            else:
                return {
                    "success": False,
                    "error": result["error"]
                }
        
        # Lê o HTML gerado
        html_content = analyzer.read_report_html(result["html_path"])
        
        logger.info(f"✅ Relatório gerado: {result['html_path']}")
        
        # Retorna o HTML direto (para injetar no modal)
        return HTMLResponse(
            content=html_content,
            status_code=200,
            headers={
                "X-Report-Path": result["html_path"],
                "X-CSV-Path": result.get("csv_path", ""),
                "X-Generated-At": result["generated_at"]
            }
        )
        
    except FileNotFoundError as e:
        logger.error(f"❌ Script não encontrado: {str(e)}")
        return {
            "success": False,
            "error": f"Scripts de análise não encontrados: {str(e)}"
        }
    except Exception as e:
        logger.error(f"❌ Erro inesperado: {str(e)}")
        return {
            "success": False,
            "error": f"Erro ao gerar relatório: {str(e)}"
        }

@app.get("/api/monitoring/space/filegroup/report-status/{server_name}/{database_name}/{filegroup_name}")
async def get_report_status(server_name: str, database_name: str, filegroup_name: str):
    """
    Verifica se já existe relatório gerado para o filegroup.
    Útil para mostrar timestamp do último relatório no frontend.
    
    Returns:
        {
            "has_report": bool,
            "last_generated": "2025-01-15T10:30:00",
            "html_path": "...",
            "csv_path": "..."
        }
    """
    try:
        analyzer = get_analyzer()
        output_dir = analyzer.base_path
        
        # Busca relatórios existentes no diretório reports
        reports_dir = output_dir / "reports"
        html_files = list(reports_dir.glob(f"interactive_{filegroup_name}_*_forecast.html"))
        
        if not html_files:
            return {
                "has_report": False,
                "last_generated": None
            }
        
        # Pega o mais recente
        latest_html = max(html_files, key=os.path.getctime)
        csv_files = list(reports_dir.glob(f"interactive_{filegroup_name}_*_forecast.csv"))
        latest_csv = max(csv_files, key=os.path.getctime) if csv_files else None
        
        return {
            "has_report": True,
            "last_generated": datetime.fromtimestamp(os.path.getctime(latest_html)).isoformat(),
            "html_path": str(latest_html),
            "csv_path": str(latest_csv) if latest_csv else None
        }
        
    except Exception as e:
        logger.error(f"Erro ao verificar status: {str(e)}")
        return {
            "has_report": False,
            "error": str(e)
        }

if __name__ == '__main__':
    import uvicorn
    
    print("[START] Starting Watcher DB System - Database Monitoring")
    print("=" * 100)
    print("REAL DATA FEATURES:")
    print("[OK] Reads your actual TAP_SQL_Server_Inventory.xlsx")
    print("[OK] Smart Excel structure analysis and column detection")
    print("[OK] Dynamic schema creation based on your real data")
    print("[OK] Importa APENAS dados reais - zero dados ficticios")
    print("[OK] Suporte completo ao seu TAP_SQL_Server_Inventory.xlsx")
    print("[OK] Schema dinamico baseado nas colunas que realmente existem")
    print("[OK] Mapeamento inteligente de colunas (server, instance, environment, etc.)")
    print("[OK] Zero fictional/sample data - uses only your Excel")
    print("[OK] Support for multiple Excel sheet formats")
    print("[OK] Advanced fuzzy search through your real servers")
    print("=" * 100)
    print("IMPLEMENTATIONS:")
    print("[OK] RedisLikeCache        - Complete Redis implementation")
    print("[OK] AdvancedFuzzyMatcher  - Multi-algorithm fuzzy matching")
    print("[OK] AsyncFileIO           - High-performance async file operations")
    print("[OK] EnhancedExcelParser   - Smart Excel parsing with structure analysis")
    print("[OK] SmartSchemaManager    - Dynamic schema based on real data")
    print("[OK] SmartTapInventoryManager - Intelligent data management")
    print("[OK] BackgroundServices    - Automated maintenance and monitoring")
    print("[OK] WebSocketManager      - Real-time notifications")
    print("=" * 100)
    print("[*] ZERO EXTERNAL DEPENDENCIES - 100% INDEPENDENT + REAL DATA ONLY")
    print("[*] Uses YOUR TAP_SQL_Server_Inventory.xlsx file")
    print("[*] All database monitoring features with your real server data")
    print("[*] Advanced search, caching, file I/O working with real data")
    print("[*] No fictional servers - only your actual SQL Server infrastructure")
    print("=" * 100)
    print("INSTRUCTIONS:")
    print("1. Place your SQL Server inventory spreadsheet in: C:\\Server_Inventory\\")
    print("2. System will automatically analyze and import your real data")
    print("3. Access interface at: http://localhost:8000/watcherdb")
    print("4. Search your servers using the advanced fuzzy search")
    print("=" * 100)
    
    # Usar watcherdb_main:app como ponto de entrada principal.
    # Host and port overridable via env vars — WATCHERDB_HOST, WATCHERDB_PORT —
    # so the PyInstaller smoke test can bind a non-default port without
    # colliding with the installed Windows service on 8433.
    _host = os.getenv("WATCHERDB_HOST", "0.0.0.0")
    try:
        _port = int(os.getenv("WATCHERDB_PORT", "8000"))
    except ValueError:
        _port = 8000
    uvicorn.run(
        "watcherdb_main:app",
        host=_host,
        port=_port,
        reload=False,
        log_level="info"
    )



@app.get("/api/monitoring/space/dashboard")
async def get_space_dashboard_data(server_id: Optional[str] = None):
    """Retorna dados para o dashboard de espaço.

    - Se server_id for fornecido: retorna array de filegroups desse servidor (para a UI do tab Space).
    - Caso contrário: retorna resumo global (todos os servidores) como antes.
    """
    try:
        engine = SpaceAnalysisEngine(app.state.sql_monitoring)
        if server_id:
            logger.info(f"[DEBUG] /api/monitoring/space/dashboard?server_id={server_id}")
            analysis = await engine.analyze_server_space(server_id)
            filegroups = analysis.get('filegroups', [])
            logger.info(f"[DEBUG] dashboard(server) -> filegroups: {len(filegroups)} (first: {filegroups[0] if filegroups else 'none'})")
            # Mapear para os nomes esperados pelo front-end
            items = []
            for fg in filegroups:
                try:
                    items.append({
                        'database_name': fg.get('database_name'),
                        'filegroup_name': fg.get('filegroup_name'),
                        'total_gb': fg.get('total_gb', 0.0),
                        'used_gb': fg.get('used_gb', 0.0),
                        'free_percent': fg.get('free_filegroup_percent', 0.0),
                        'alert_level': fg.get('alert_level', 'OK'),
                        'disk_overflow_risk': fg.get('disk_overflow_risk', False),
                        'volume': fg.get('volume', ''),
                        'available_disk_gb': fg.get('available_disk_gb', 0.0)
                    })
                except Exception:
                    continue
            logger.info(f"[DEBUG] dashboard(server) -> mapped items: {len(items)}")
            return {"success": True, "data": items}

        # Global summary (sem server_id)
        with open(SQL_SERVERS_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        server_ids = [s.get("id") for s in cfg.get("servers", []) if s.get("id")]
        results = await get_space_analysis_for_all_servers(app.state.sql_monitoring, server_ids)
        logger.info(f"[DEBUG] dashboard(global) -> servers analyzed: {len(results.get('servers', []))}")
        return {"success": True, "data": results}
    except Exception as e:
        logger.error(f"Error getting space dashboard data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/space/alerts")
async def get_space_alerts(server_id: Optional[str] = None):
    """Retorna alertas de espaço em disco.

    - Com server_id: retorna alertas apenas desse servidor, mapeados para os campos esperados na UI.
    - Sem server_id: retorna alertas globais (todos os servidores).
    """
    try:
        engine = SpaceAnalysisEngine(app.state.sql_monitoring)
        if server_id:
            logger.info(f"[DEBUG] /api/monitoring/space/alerts?server_id={server_id}")
            analysis = await engine.analyze_server_space(server_id)
            alerts = analysis.get('alerts', [])
            logger.info(f"[DEBUG] alerts(server) -> raw alerts: {len(alerts)} (first: {alerts[0] if alerts else 'none'})")
            mapped = []
            for a in alerts:
                try:
                    mapped.append({
                        'type': 'SPACE',
                        'message': a.get('action_sql') or f"{a.get('database_name')} {a.get('filegroup_name')}",
                        'severity': a.get('alert_level', 'INFO'),
                        'database_name': a.get('database_name'),
                        'filegroup_name': a.get('filegroup_name'),
                    })
                except Exception:
                    continue
            logger.info(f"[DEBUG] alerts(server) -> mapped: {len(mapped)}")
            return {"success": True, "alerts": mapped}

        # Global
        with open(SQL_SERVERS_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        server_ids = [s.get("id") for s in cfg.get("servers", []) if s.get("id")]
        results = await get_space_analysis_for_all_servers(app.state.sql_monitoring, server_ids)
        alerts_list = extract_alerts(results.get("servers", []))
        logger.info(f"[DEBUG] alerts(global) -> total alerts: {len(alerts_list)}")
        return {"success": True, "alerts": alerts_list}
    except Exception as e:
        logger.error(f"Error getting space alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ALERTAS PREDITIVOS - ENDPOINTS COM TRATAMENTO DE ERROS
# ============================================================================

from fastapi.responses import JSONResponse
import traceback

# [V3.3 zero AI policy FIND-20260612-104, precedente FIND-014-B] Predictive Alerts
# e Pro-only -- route NAO registado em V3.3. Funcao preservada para paridade V6+.
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts")
async def get_predictive_alerts(server_id: str):
    """
    Análise preditiva de alertas de espaço COM DADOS REAIS
    
    Retorna alertas categorizados por:
    - Severidade (CRITICAL, HIGH, MEDIUM, LOW)
    - Tipo (SPACE_CRITICAL, GROWTH_TREND, MAXSIZE_APPROACHING, DISK_SATURATION)
    
    Análise agregada por FILEGROUP (não por datafile individual)
    """
    try:
        logger.info(f"📡 [API] GET /predictive-alerts para {server_id}")
        
        # Import do engine - tentar primeiro predictive_alerts, depois predictive_alerts_debug
        try:
            try:
                from modules.monitoring.predictive_alerts import PredictiveAlertsEngine
                logger.info("✅ [API] PredictiveAlertsEngine importado de predictive_alerts")
            except ImportError:
                from modules.monitoring.predictive_alerts_debug import PredictiveAlertsEngine
                logger.info("✅ [API] PredictiveAlertsEngine importado de predictive_alerts_debug")
        except ImportError as e:
            logger.error(f"❌ [API] Erro ao importar PredictiveAlertsEngine: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": f"Módulo não encontrado: {str(e)}",
                    "hint": "Verifique se o arquivo predictive_alerts.py ou predictive_alerts_debug.py existe em modules/monitoring/"
                }
            )
        
        # Verificar se sql_monitoring existe
        if not hasattr(app.state, 'sql_monitoring') and 'sql_monitoring' not in globals():
            logger.error("❌ [API] sql_monitoring não encontrado")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "sql_monitoring não está configurado",
                    "hint": "Verifique a inicialização do SQLMonitoring no startup"
                }
            )
        
        # Pegar sql_monitoring do contexto
        sql_mon = getattr(app.state, 'sql_monitoring', None) or globals().get('sql_monitoring')
        
        if sql_mon is None:
            logger.error("❌ [API] sql_monitoring é None")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "sql_monitoring não inicializado"
                }
            )
        
        # Criar engine e executar análise
        logger.info(f"🔮 [API] Criando engine para análise de {server_id}")
        engine = PredictiveAlertsEngine(sql_mon)
        
        logger.info(f"⚙️ [API] Executando analyze_server_alerts...")
        result = await engine.analyze_server_alerts(server_id)
        
        # Verificar se houve erro interno
        if 'error' in result and not result.get('success', True):
            logger.error(f"❌ [API] Erro interno na análise: {result['error']}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": result['error'],
                    "server_id": server_id
                }
            )
        
        # Sucesso
        logger.info(f"✅ [API] Análise concluída: {result.get('total_alerts', 0)} alertas")
        
        # Garantir que todos os objetos datetime sejam serializados
        def serialize_for_json(obj):
            """Serializa objetos para JSON, convertendo datetime e outros tipos não serializáveis"""
            if isinstance(obj, dict):
                return {k: serialize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_for_json(item) for item in obj]
            elif hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            elif hasattr(obj, '__dict__'):  # objetos com __dict__
                return serialize_for_json(obj.__dict__)
            else:
                return obj
        
        # Serializar o resultado antes de retornar
        serialized_result = serialize_for_json(result)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                **serialized_result
            }
        )
        
    except Exception as e:
        # Log detalhado do erro
        error_trace = traceback.format_exc()
        logger.error(f"❌ [API] Erro crítico na análise preditiva:")
        logger.error(error_trace)
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "server_id": server_id,
                "traceback": error_trace.split('\n')[-5:],  # Últimas 5 linhas
                "hint": "Verifique os logs do servidor para detalhes completos"
            }
        )


# [FIND-20260612-104] Pro-only, route NAO registado em V3.3 (ver bloco principal acima).
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts/debug")
async def debug_predictive_alerts(server_id: str):
    """
    Endpoint de debug para testar conexão e validar dados
    """
    try:
        debug_info = {
            "server_id": server_id,
            "steps": []
        }
        
        # Step 1: Verificar import
        try:
            from modules.monitoring.predictive_alerts_debug import PredictiveAlertsEngine
            debug_info["steps"].append({
                "step": "1. Import PredictiveAlertsEngine",
                "status": "✅ OK",
                "module_path": PredictiveAlertsEngine.__module__
            })
        except Exception as e:
            debug_info["steps"].append({
                "step": "1. Import PredictiveAlertsEngine",
                "status": "❌ ERRO",
                "error": str(e)
            })
            return JSONResponse(content=debug_info)
        
        # Step 2: Verificar sql_monitoring
        sql_mon = getattr(app.state, 'sql_monitoring', None) or globals().get('sql_monitoring')
        
        if sql_mon:
            debug_info["steps"].append({
                "step": "2. sql_monitoring",
                "status": "✅ OK",
                "type": str(type(sql_mon))
            })
        else:
            debug_info["steps"].append({
                "step": "2. sql_monitoring",
                "status": "❌ ERRO",
                "error": "sql_monitoring não encontrado"
            })
            return JSONResponse(content=debug_info)
        
        # Step 3: Testar conexão
        try:
            # Usar a API correta do SQLServerMonitoring
            result = await sql_mon.execute_query(server_id, "SELECT @@VERSION AS version")
            
            if result['success'] and result['rows']:
                version = result['rows'][0]['version']
                debug_info["steps"].append({
                    "step": "3. Conexão SQL Server",
                    "status": "✅ OK",
                    "version": version[:100] if version else "N/A"
                })
            else:
                debug_info["steps"].append({
                    "step": "3. Conexão SQL Server",
                    "status": "❌ ERRO",
                    "error": "Query não retornou resultado"
                })
                return JSONResponse(content=debug_info)
        except Exception as e:
            debug_info["steps"].append({
                "step": "3. Conexão SQL Server",
                "status": "❌ ERRO",
                "error": str(e)
            })
            return JSONResponse(content=debug_info)
        
        # Step 4: Testar query de datafiles
        try:
            test_query = """
            SELECT TOP 5
                d.name AS database_name,
                df.name AS logical_name,
                df.size * 8.0 / 1024 AS size_mb
            FROM sys.databases d
            JOIN sys.master_files df ON d.database_id = df.database_id
            WHERE d.database_id > 4
            ORDER BY d.name
            """
            
            # Usar a API correta
            result = await sql_mon.execute_query(server_id, test_query)
            
            if result['success']:
                rows = result['rows']
                debug_info["steps"].append({
                    "step": "4. Query datafiles",
                    "status": "✅ OK",
                    "sample_count": len(rows),
                    "sample_data": [{"db": r['database_name'], "file": r['logical_name'], "size_mb": float(r['size_mb'])} for r in rows]
                })
            else:
                debug_info["steps"].append({
                    "step": "4. Query datafiles",
                    "status": "❌ ERRO",
                    "error": "Query falhou"
                })
                return JSONResponse(content=debug_info)
        except Exception as e:
            debug_info["steps"].append({
                "step": "4. Query datafiles",
                "status": "❌ ERRO",
                "error": str(e)
            })
            return JSONResponse(content=debug_info)
        
        # Step 5: Criar engine
        try:
            engine = PredictiveAlertsEngine(sql_mon)
            debug_info["steps"].append({
                "step": "5. Criar PredictiveAlertsEngine",
                "status": "✅ OK",
                "thresholds": engine.thresholds
            })
        except Exception as e:
            debug_info["steps"].append({
                "step": "5. Criar PredictiveAlertsEngine",
                "status": "❌ ERRO",
                "error": str(e)
            })
            return JSONResponse(content=debug_info)
        
        # Step 6: Executar análise completa
        try:
            result = await engine.analyze_server_alerts(server_id)
            
            debug_info["steps"].append({
                "step": "6. Executar análise completa",
                "status": "✅ OK",
                "total_alerts": result.get('total_alerts', 0),
                "total_filegroups": result.get('total_filegroups_analyzed', 0),
                "health_score": result.get('predictive_health_score', 0)
            })
            
            debug_info["result_preview"] = {
                "total_alerts": result.get('total_alerts', 0),
                "health_score": result.get('predictive_health_score', 0),
                "alerts_by_severity": {
                    k: len(v) for k, v in result.get('alerts_by_severity', {}).items()
                }
            }
            
        except Exception as e:
            debug_info["steps"].append({
                "step": "6. Executar análise completa",
                "status": "❌ ERRO",
                "error": str(e),
                "traceback": traceback.format_exc().split('\n')[-10:]
            })
        
        debug_info["overall_status"] = "✅ TUDO OK" if all(
            s.get("status", "").startswith("✅") for s in debug_info["steps"]
        ) else "❌ HÁ ERROS"
        
        return JSONResponse(content=debug_info)
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "traceback": traceback.format_exc().split('\n')
            }
        )


# [FIND-20260612-104] Pro-only, route NAO registado em V3.3.
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts/ping")
async def ping_predictive_alerts(server_id: str):
    """
    Ping simples para verificar se o endpoint está respondendo
    """
    return JSONResponse(
        content={
            "success": True,
            "message": "Endpoint de alertas preditivos está ativo",
            "server_id": server_id,
            "timestamp": datetime.now().isoformat()
        }
    )

# [FIND-20260612-104] Pro-only, route NAO registado em V3.3.
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts/test-simple")
async def test_simple_predictive(server_id: str):
    """
    Testa alertas preditivos com query simples (como o debug)
    """
    try:
        from modules.monitoring.predictive_alerts_debug import PredictiveAlertsEngine
        
        sql_mon = getattr(app.state, 'sql_monitoring', None) or globals().get('sql_monitoring')
        
        if not sql_mon:
            return JSONResponse(content={"error": "sql_monitoring não encontrado"})
        
        # Usar query simples como no debug
        simple_query = """
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
            CAST(FILEPROPERTY(df.name, 'SpaceUsed') * 8.0 / 1024 AS DECIMAL(18,2)) AS used_mb,
            CAST((df.size - FILEPROPERTY(df.name, 'SpaceUsed')) * 8.0 / 1024 AS DECIMAL(18,2)) AS free_mb
        FROM sys.databases d
        JOIN sys.master_files df ON d.database_id = df.database_id
        LEFT JOIN sys.filegroups fg ON df.data_space_id = fg.data_space_id
        WHERE d.database_id > 4
            AND d.state = 0
        ORDER BY d.name, df.type, df.name
        """
        
        result = await sql_mon.execute_query(server_id, simple_query)
        
        if not result['success']:
            return JSONResponse(content={"error": f"Query falhou: {result.get('error')}"})
        
        rows = result['rows']
        
        # Converter Decimal para float
        for row in rows:
            for key, value in row.items():
                if hasattr(value, '__class__') and 'Decimal' in str(value.__class__):
                    row[key] = float(value)
        
        # Simular agregação manual
        grouped = {}
        for row in rows:
            key = (row['database_name'], row['filegroup_name'])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(row)
        
        return JSONResponse(content={
            "success": True,
            "total_rows": len(rows),
            "total_filegroups": len(grouped),
            "filegroups": list(grouped.keys()),
            "sample_data": rows[:3]
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "traceback": traceback.format_exc().split('\n')}
        )

# [FIND-20260612-104] Pro-only, route NAO registado em V3.3.
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts/test-query")
async def test_predictive_query(server_id: str):
    """
    Testa a query específica dos alertas preditivos
    """
    try:
        sql_mon = getattr(app.state, 'sql_monitoring', None) or globals().get('sql_monitoring')
        
        if not sql_mon:
            return JSONResponse(content={"error": "sql_monitoring não encontrado"})
        
        # Query simplificada para testar
        test_query = """
        SELECT TOP 10
            d.name AS database_name,
            ISNULL(fg.name, 'LOG') AS filegroup_name,
            df.name AS logical_name,
            df.type_desc AS file_type,
            CAST(df.size * 8.0 / 1024 AS DECIMAL(18,2)) AS size_mb,
            CAST(df.max_size * 8.0 / 1024 AS DECIMAL(18,2)) AS max_size_mb,
            CAST(FILEPROPERTY(df.name, 'SpaceUsed') * 8.0 / 1024 AS DECIMAL(18,2)) AS used_mb
        FROM sys.databases d
        JOIN sys.master_files df ON d.database_id = df.database_id
        LEFT JOIN sys.filegroups fg ON df.data_space_id = fg.data_space_id AND d.database_id = fg.data_space_id
        WHERE d.database_id > 4
            AND d.state = 0
        ORDER BY d.name, ISNULL(fg.name, 'LOG'), df.name
        """
        
        result = await sql_mon.execute_query(server_id, test_query)
        
        if result['success']:
            rows = result['rows']
            return JSONResponse(content={
                "success": True,
                "total_rows": len(rows),
                "sample_data": rows[:5],
                "columns": list(rows[0].keys()) if rows else []
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": result.get('error', 'Query falhou')
            })
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "traceback": traceback.format_exc().split('\n')}
        )

# [FIND-20260612-104] Pro-only, route NAO registado em V3.3.
# @app.get("/api/monitoring/space/server/{server_id}/predictive-alerts/debug-v2")
async def debug_predictive_alerts_v2(server_id: str):
    """
    Debug endpoint V2 - Descobre a API de conexão automaticamente
    """
    try:
        debug_info = {
            "server_id": server_id,
            "steps": []
        }
        
        # Step 1: Import
        try:
            from modules.monitoring.predictive_alerts_debug import PredictiveAlertsEngine
            debug_info["steps"].append({
                "step": "1. Import",
                "status": "✅ OK"
            })
        except Exception as e:
            debug_info["steps"].append({"step": "1. Import", "status": f"❌ {e}"})
            return JSONResponse(content=debug_info)
        
        # Step 2: sql_monitoring
        sql_mon = getattr(app.state, 'sql_monitoring', None) or globals().get('sql_monitoring')
        
        if not sql_mon:
            debug_info["steps"].append({"step": "2. sql_monitoring", "status": "❌ Não encontrado"})
            return JSONResponse(content=debug_info)
        
        # Descobrir métodos disponíveis
        methods = [m for m in dir(sql_mon) if not m.startswith('_') and callable(getattr(sql_mon, m))]
        
        debug_info["steps"].append({
            "step": "2. sql_monitoring",
            "status": "✅ OK",
            "type": str(type(sql_mon)),
            "available_methods": methods[:20]  # Primeiros 20 métodos
        })
        
        # Step 3: Testar query simples
        test_query = "SELECT @@VERSION AS version, @@SERVERNAME AS server_name"
        
        # Tentar diferentes métodos
        for method_name in ['execute_query', 'query', 'fetch', 'execute', 'run_query']:
            if not hasattr(sql_mon, method_name):
                continue
            
            try:
                method = getattr(sql_mon, method_name)
                logger.info(f"🔍 Tentando método: {method_name}")
                
                result = await method(server_id, test_query)
                
                debug_info["steps"].append({
                    "step": f"3. Teste com {method_name}()",
                    "status": "✅ OK",
                    "result_type": str(type(result)),
                    "result_sample": str(result)[:200]
                })
                
                # Descobrir estrutura do resultado
                if isinstance(result, list) and result:
                    if isinstance(result[0], dict):
                        debug_info["result_structure"] = {
                            "type": "list of dicts",
                            "sample_keys": list(result[0].keys()),
                            "sample_values": str(list(result[0].values()))[:100]
                        }
                    else:
                        debug_info["result_structure"] = {
                            "type": "list of tuples/objects",
                            "sample": str(result[0])[:100]
                        }
                elif hasattr(result, '__dict__'):
                    debug_info["result_structure"] = {
                        "type": "object with attributes",
                        "attributes": list(result.__dict__.keys())
                    }
                else:
                    debug_info["result_structure"] = {
                        "type": str(type(result)),
                        "dir": [a for a in dir(result) if not a.startswith('_')][:10]
                    }
                
                break  # Parar no primeiro método que funcionar
                
            except Exception as e:
                debug_info["steps"].append({
                    "step": f"3. Teste com {method_name}()",
                    "status": f"❌ {str(e)[:100]}"
                })
                continue
        
        return JSONResponse(content=debug_info)
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "traceback": traceback.format_exc().split('\n')}
        )

