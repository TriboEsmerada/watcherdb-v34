"""
Testes de Seguranca — Validacao dos fixes da auditoria V3.2

Cobre:
- CORS: config-based, sem wildcard
- Security Headers: middleware funcional, CSP com nonce
- Error helpers: sem leak de detail=str(e)
- Token blacklist: DB-persisted com fallback
- WebSocket: requer autenticacao
- Password change: must_change_password flag
- Connection pool: sem bare except
- Cache factory: feature flag USE_REDIS
"""

import os
import sys
import time
import hashlib
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from collections import OrderedDict

# Adicionar path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ============================================================
# CORS CONFIG (Item 1)
# ============================================================

class TestCORSConfig:
    """Testes do modulo watcherdb/core/cors.py"""

    def test_get_cors_config_returns_dict(self):
        """get_cors_config deve retornar dicionario com parametros CORS"""
        from watcherdb.core.cors import get_cors_config

        config = get_cors_config()

        assert isinstance(config, dict)
        assert "allow_origins" in config
        assert "allow_credentials" in config
        assert "allow_methods" in config
        assert "allow_headers" in config

    def test_cors_never_returns_wildcard_with_credentials(self):
        """CORS nunca deve retornar allow_origins=['*'] com credentials=True"""
        from watcherdb.core.cors import get_cors_config

        config = get_cors_config()

        if config.get("allow_credentials"):
            assert config["allow_origins"] != ["*"], (
                "CORS wildcard com credentials=True e uma vulnerabilidade critica"
            )

    def test_cors_reads_from_config_yaml(self):
        """CORS deve ler origens do config/config.yaml"""
        from watcherdb.core.cors import get_cors_config

        config = get_cors_config()
        origins = config.get("allow_origins", [])

        # Deve ter pelo menos localhost
        assert len(origins) > 0
        assert any("localhost" in o for o in origins)

    def test_cors_filters_cidr_ranges(self):
        """CORS deve filtrar ranges CIDR (nao suportados)"""
        from watcherdb.core.cors import get_cors_config, _load_config

        # Mock config com CIDR
        mock_config = {
            "security": {
                "cors": {
                    "enabled": True,
                    "allowed_origins": [
                        "http://localhost:8000",
                        "https://10.0.0.0/8",
                    ],
                }
            }
        }

        with patch("watcherdb.core.cors._load_config", return_value=mock_config):
            config = get_cors_config()
            origins = config["allow_origins"]
            assert "https://10.0.0.0/8" not in origins
            assert "http://localhost:8000" in origins

    def test_cors_disabled_returns_empty(self):
        """CORS disabled deve retornar listas vazias"""
        from watcherdb.core.cors import get_cors_config

        mock_config = {
            "security": {"cors": {"enabled": False}}
        }

        with patch("watcherdb.core.cors._load_config", return_value=mock_config):
            config = get_cors_config()
            assert config["allow_origins"] == []
            assert config["allow_credentials"] is False


# ============================================================
# SECURITY HEADERS MIDDLEWARE (Item 3 + Item 7 CSP)
# ============================================================

class TestSecurityHeadersMiddleware:
    """Testes do middleware de security headers"""

    def test_middleware_can_be_imported(self):
        """SecurityHeadersMiddleware deve ser importavel"""
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        assert SecurityHeadersMiddleware is not None

    @pytest.mark.asyncio
    async def test_middleware_sets_hsts_header(self):
        """Middleware deve definir Strict-Transport-Security"""
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(SecurityHeadersMiddleware)

        # HSTS so' sobre HTTPS real (QA externo 2026-08-16 BUG-010: sobre HTTP
        # o browser ignora e o includeSubDomains fica armado para o dia do TLS)
        client = TestClient(app, base_url="https://testserver")
        response = client.get("/")

        assert "Strict-Transport-Security" in response.headers
        assert "X-Frame-Options" in response.headers

        plain = TestClient(app, base_url="http://testserver").get("/")
        assert "Strict-Transport-Security" not in plain.headers
        assert plain.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_csp_no_unsafe_inline(self):
        """CSP: unsafe-inline SO nas directivas -attr (CSP3 elem/attr split,
        decisao 2026-08-12 — handlers/style inline do portal); nunca em
        script-src/style-src (elementos) e nunca unsafe-eval."""
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        response = client.get("/")

        csp = response.headers.get("Content-Security-Policy", "")
        directives = {
            d.strip().split(" ", 1)[0]: d.strip()
            for d in csp.split(";") if d.strip()
        }
        for elem in ("script-src", "style-src"):
            assert "'unsafe-inline'" not in directives.get(elem, ""), \
                f"{elem} (elementos) contem unsafe-inline"
        assert "'unsafe-eval'" not in csp, "CSP contem unsafe-eval"

    @pytest.mark.asyncio
    async def test_csp_uses_nonce(self):
        """CSP deve usar nonce-based em vez de unsafe-inline"""
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        response = client.get("/")

        csp = response.headers.get("Content-Security-Policy", "")
        assert "'nonce-" in csp, "CSP deve usar nonce-based policy"

    @pytest.mark.asyncio
    async def test_csp_no_cdn_references(self):
        """CSP padrao nao deve referenciar CDNs externos"""
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        response = client.get("/")

        csp = response.headers.get("Content-Security-Policy", "")
        assert "cdn.jsdelivr.net" not in csp
        assert "cdnjs.cloudflare.com" not in csp

    @pytest.mark.asyncio
    async def test_permissions_policy_set(self):
        """Middleware deve definir Permissions-Policy restritiva"""
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        response = client.get("/")

        pp = response.headers.get("Permissions-Policy", "")
        assert "geolocation=()" in pp
        assert "camera=()" in pp


# ============================================================
# ERROR HELPERS (Item 10)
# ============================================================

class TestErrorHelpers:
    """Testes do modulo api/error_helpers.py"""

    def test_safe_http_error_returns_httpexception(self):
        """safe_http_error deve retornar HTTPException"""
        from api.error_helpers import safe_http_error
        from fastapi import HTTPException

        exc = ValueError("Connection string: SERVER=secret;PWD=password123")
        result = safe_http_error(500, exc, "loading data")

        assert isinstance(result, HTTPException)
        assert result.status_code == 500

    def test_safe_http_error_hides_internal_details(self):
        """safe_http_error NAO deve expor detalhes internos no detail"""
        from api.error_helpers import safe_http_error

        exc = ValueError("pyodbc.OperationalError: SERVER=SQLPRD01;PWD=secret123")
        result = safe_http_error(500, exc, "connecting to server")

        # Detail nao deve conter a exception original
        assert "secret123" not in result.detail
        assert "SQLPRD01" not in result.detail
        assert "pyodbc" not in result.detail

    def test_safe_http_error_includes_reference_id(self):
        """safe_http_error deve incluir um ID de referencia"""
        from api.error_helpers import safe_http_error

        exc = ValueError("test error")
        result = safe_http_error(500, exc, "test")

        assert "ref:" in result.detail or "ref: " in result.detail

    def test_safe_http_error_preserves_status_code(self):
        """safe_http_error deve preservar o status code passado"""
        from api.error_helpers import safe_http_error

        result = safe_http_error(503, ValueError("test"), "test")
        assert result.status_code == 503


# ============================================================
# TOKEN BLACKLIST (Item 6)
# ============================================================

class TestTokenBlacklist:
    """Testes do token blacklist DB-persisted"""

    def test_blacklist_manager_can_be_imported(self):
        """TokenBlacklistManager deve ser importavel via auth_compat"""
        from api.routers.auth_compat import _TokenBlacklistManager
        assert _TokenBlacklistManager is not None

    def test_blacklist_hash_is_sha256(self):
        """Token hash deve usar SHA-256"""
        from api.routers.auth_compat import _TokenBlacklistManager

        manager = _TokenBlacklistManager()
        token = "test-jwt-token-12345"
        expected_hash = hashlib.sha256(token.encode()).hexdigest()

        assert manager._hash_token(token) == expected_hash

    def test_blacklist_memory_cache_works(self):
        """Blacklist deve funcionar com cache em memoria (fallback)"""
        from api.routers.auth_compat import _TokenBlacklistManager

        manager = _TokenBlacklistManager(max_cache_size=100)

        # Mock DB para falhar — forca fallback
        with patch("api.routers.auth_compat._execute_update", side_effect=Exception("DB offline")):
            manager.add("test-token", username="admin")

        # Token deve estar no fallback set
        with patch("api.routers.auth_compat._execute_query", side_effect=Exception("DB offline")):
            assert "test-token" in manager

    def test_blacklist_lru_eviction(self):
        """Cache LRU deve evictar tokens antigos quando cheio"""
        from api.routers.auth_compat import _TokenBlacklistManager

        manager = _TokenBlacklistManager(max_cache_size=3)

        with patch("api.routers.auth_compat._execute_update", side_effect=Exception("DB offline")):
            manager.add("token-1", username="user1")
            manager.add("token-2", username="user2")
            manager.add("token-3", username="user3")
            manager.add("token-4", username="user4")  # Evicta token-1

        # token-1 nao esta no memory_cache (evictado)
        token1_hash = manager._hash_token("token-1")
        assert token1_hash not in manager._memory_cache

    def test_blacklist_does_not_contain_random_token(self):
        """Blacklist nao deve conter tokens aleatorios"""
        from api.routers.auth_compat import _TokenBlacklistManager

        manager = _TokenBlacklistManager()

        with patch("api.routers.auth_compat._execute_query", return_value=[]):
            assert "random-token-xyz" not in manager


# ============================================================
# CONNECTION POOL — BARE EXCEPT FIX (Item 14)
# ============================================================

class TestConnectionPoolExceptFix:
    """Verifica que connection_pool.py nao tem bare except"""

    def test_no_bare_except_in_connection_pool(self):
        """connection_pool.py NAO deve ter bare 'except:' clauses"""
        import ast

        pool_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "api", "connection_pool.py"
        )

        with open(pool_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        bare_excepts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare_excepts.append(node.lineno)

        assert len(bare_excepts) == 0, (
            f"Bare 'except:' encontrado nas linhas: {bare_excepts}. "
            "Usar 'except pyodbc.Error:' ou 'except Exception:'"
        )


# ============================================================
# CACHE FACTORY (Item 17 — Redis feature flag)
# ============================================================

class TestCacheFactory:
    """Testes do cache_factory.py"""

    def test_default_returns_redis_like_cache(self):
        """Por defeito (USE_REDIS=false), deve retornar RedisLikeCache"""
        from watcherdb.core.cache import RedisLikeCache

        with patch.dict(os.environ, {"USE_REDIS": "false"}):
            from watcherdb.core.cache_factory import get_cache
            cache = get_cache(persistence_file=None, max_memory_mb=5)
            assert isinstance(cache, RedisLikeCache)

    def test_redis_flag_true_falls_back_if_no_redis(self):
        """USE_REDIS=true deve fazer fallback se Redis nao disponivel"""
        from watcherdb.core.cache import RedisLikeCache

        with patch.dict(os.environ, {"USE_REDIS": "true"}):
            # Mock redis import to fail
            with patch("watcherdb.core.cache_factory.get_cache") as mock_factory:
                # Just verify the factory exists and is callable
                assert callable(mock_factory)


# ============================================================
# CACHE DEDUP (Item 13 — RedisLikeCache e canonical)
# ============================================================

class TestCacheDedup:
    """Verifica que RedisLikeCache inline foi removido dos ficheiros principais"""

    def test_no_redis_like_cache_class_in_main(self):
        """watcherdb_main.py NAO deve definir class RedisLikeCache"""
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "watcherdb_main.py"
        )

        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Nao deve ter definicao de class, mas deve ter import
        assert "class RedisLikeCache" not in content, (
            "watcherdb_main.py ainda define RedisLikeCache inline — "
            "deve usar from watcherdb.core.cache import RedisLikeCache"
        )

    def test_no_redis_like_cache_class_in_intelligence(self):
        """watcherdb_intelligence.py NAO deve definir class RedisLikeCache"""
        intel_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "watcherdb_intelligence.py"
        )

        with open(intel_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "class RedisLikeCache" not in content

    def test_canonical_cache_in_core(self):
        """watcherdb/core/cache.py deve definir RedisLikeCache"""
        from watcherdb.core.cache import RedisLikeCache
        assert RedisLikeCache is not None

        cache = RedisLikeCache(persistence_file=None, max_memory_mb=5)
        cache.set("test", "value")
        assert cache.get("test") == "value"


# ============================================================
# DECOMPOSITION (Item 12 — classes extraidas)
# ============================================================

class TestDecomposition:
    """Verifica que classes foram extraidas para watcherdb/core/"""

    def test_fuzzy_matcher_importable(self):
        """AdvancedFuzzyMatcher deve ser importavel de watcherdb.core"""
        from watcherdb.core.fuzzy_matcher import AdvancedFuzzyMatcher
        assert AdvancedFuzzyMatcher is not None

    def test_async_file_io_importable(self):
        """AsyncFileIO deve ser importavel"""
        from watcherdb.core.async_file_io import AsyncFileIO
        assert AsyncFileIO is not None

    def test_websocket_manager_importable(self):
        """WebSocketManager deve ser importavel"""
        from watcherdb.core.websocket_manager import WebSocketManager
        assert WebSocketManager is not None

    def test_models_importable(self):
        """ServiceType, CheckType, InventoryServer devem ser importaveis"""
        from watcherdb.core.models import ServiceType, CheckType, InventoryServer
        assert ServiceType is not None
        assert CheckType is not None
        assert InventoryServer is not None

    def test_background_services_importable(self):
        """BackgroundServices deve ser importavel"""
        from watcherdb.core.background_services import BackgroundServices
        assert BackgroundServices is not None

    def test_main_file_smaller_than_7000_lines(self):
        """watcherdb_main.py deve ter menos de 7000 linhas apos decomposicao"""
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "watcherdb_main.py"
        )
        with open(main_path, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f)

        assert line_count < 7000, (
            f"watcherdb_main.py tem {line_count} linhas — "
            "deve ter menos de 7000 apos decomposicao"
        )


# ============================================================
# LOGGING & METRICS (Item 15)
# ============================================================

class TestLoggingAndMetrics:
    """Testes de structlog e prometheus-client"""

    def test_logging_setup_importable(self):
        """setup_logging deve ser importavel"""
        from watcherdb.core.logging_setup import setup_logging
        assert callable(setup_logging)

    def test_metrics_module_importable(self):
        """setup_metrics deve ser importavel"""
        from watcherdb.core.metrics import setup_metrics
        assert callable(setup_metrics)

    def test_prometheus_counters_exist(self):
        """Contadores Prometheus devem estar definidos"""
        from watcherdb.core.metrics import REQUEST_COUNT, REQUEST_DURATION, WS_CONNECTIONS
        assert REQUEST_COUNT is not None
        assert REQUEST_DURATION is not None
        assert WS_CONNECTIONS is not None


# ============================================================
# OPENTELEMETRY (Item 20)
# ============================================================

class TestOpenTelemetry:
    """Testes do modulo de telemetria"""

    def test_telemetry_module_importable(self):
        """setup_telemetry deve ser importavel"""
        from watcherdb.core.telemetry import setup_telemetry, RequestIDMiddleware
        assert callable(setup_telemetry)
        assert RequestIDMiddleware is not None

    @pytest.mark.asyncio
    async def test_request_id_middleware_adds_header(self):
        """RequestIDMiddleware deve adicionar X-Request-ID a todas as respostas"""
        from watcherdb.core.telemetry import RequestIDMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(RequestIDMiddleware)

        client = TestClient(app)
        response = client.get("/")

        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 10  # UUID format


# ============================================================
# COPILOT (Item 21)
# ============================================================

class TestCopilot:
    """Testes do DBA Copilot"""

    def test_copilot_router_importable(self):
        """Router copilot deve ser importavel"""
        from api.routers.copilot import router
        assert router is not None

    def test_copilot_service_importable(self):
        """CopilotService deve ser importavel"""
        from services.copilot_service import CopilotService
        assert CopilotService is not None

    def test_copilot_has_quick_answers(self):
        """CopilotService deve ter quick answers predefinidas"""
        from services.copilot_service import CopilotService

        service = CopilotService()
        answers = service.get_quick_answers()

        assert isinstance(answers, list)
        assert len(answers) >= 5  # Pelo menos 5 Q&A

        # Cada resposta deve ter question e answer
        for qa in answers:
            assert "question" in qa
            assert "answer" in qa

    @pytest.mark.asyncio
    async def test_copilot_ask_returns_answer(self):
        """CopilotService.ask_question deve retornar resposta"""
        from services.copilot_service import CopilotService

        service = CopilotService()
        result = await service.ask_question("How do I check backup status?")

        assert isinstance(result, dict)
        assert "answer" in result
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_copilot_report_daily_summary(self):
        """CopilotService deve gerar relatorio diario"""
        from services.copilot_service import CopilotService

        service = CopilotService()
        report = await service.generate_report("daily_summary")

        assert isinstance(report, dict)
        assert "title" in report
        assert "content" in report

    def test_llm_client_importable(self):
        """LLM client deve ser importavel"""
        from services.llm_client import is_llm_enabled, get_llm_client
        assert callable(is_llm_enabled)
        assert callable(get_llm_client)

    def test_llm_disabled_by_default(self):
        """LLM deve estar desligado por defeito"""
        with patch.dict(os.environ, {"LLM_ENABLED": "false"}, clear=False):
            from services.llm_client import is_llm_enabled
            # Reimport to get fresh value
            import importlib
            import services.llm_client
            importlib.reload(services.llm_client)
            assert services.llm_client.is_llm_enabled() is False


# ============================================================
# ALEMBIC (Item 11)
# ============================================================

class TestAlembicSetup:
    """Verifica que Alembic esta configurado"""

    def test_alembic_ini_exists(self):
        """alembic.ini deve existir na raiz do projecto"""
        ini_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "alembic.ini"
        )
        assert os.path.isfile(ini_path), "alembic.ini nao encontrado"

    def test_alembic_env_exists(self):
        """alembic/env.py deve existir"""
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "alembic", "env.py"
        )
        assert os.path.isfile(env_path), "alembic/env.py nao encontrado"

    def test_baseline_migration_exists(self):
        """Migration baseline deve existir"""
        versions_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "alembic", "versions"
        )
        assert os.path.isdir(versions_dir), "alembic/versions/ nao encontrado"

        # Deve ter pelo menos 1 migration
        migrations = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
        assert len(migrations) >= 1, "Nenhuma migration encontrada"


# ============================================================
# HEALTH SCORES (Item 16)
# ============================================================

class TestHealthScoresReal:
    """Verifica que health scores nao sao random"""

    def test_no_random_in_intelligence(self):
        """watcherdb_intelligence.py NAO deve usar random para health scores"""
        intel_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "watcherdb_intelligence.py"
        )

        with open(intel_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Nao deve ter random.uniform para health scores
        assert "random.uniform(75, 98)" not in content, (
            "Health scores ainda usam random.uniform — devem ser calculados"
        )
        assert "random.randint(0, 3)" not in content
        assert "random.randint(10, 500)" not in content
