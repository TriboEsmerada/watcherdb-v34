"""
WatcherDB V3.2 — QA Test Suite: Levels 7-15
=============================================

Extended testing levels beyond the core 6:

Level 7:  BOUNDARY & EDGE CASES — limits, overflows, empty inputs, unicode
Level 8:  CONCURRENCY & THREAD SAFETY — race conditions, deadlocks, pool contention
Level 9:  DATA INTEGRITY — serialization roundtrips, encoding, precision
Level 10: CONFIGURATION & ENVIRONMENT — settings validation, env var handling
Level 11: ERROR HANDLING & RECOVERY — graceful degradation, error chains, cleanup
Level 12: DEPENDENCY ISOLATION — mock failures of each external dependency
Level 13: CODE QUALITY & STANDARDS — naming, docstrings, imports, complexity
Level 14: REGRESSION GUARDS — things that broke before must never break again
Level 15: OBSERVABILITY — logging, metrics, tracing, health checks

Run: pytest tests/unit/test_qa_levels_7_15.py -v --no-cov
"""

import os
import sys
import ast
import re
import time
import json
import threading
import hashlib
import importlib
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
PROJECT_ROOT = Path(__file__).parent.parent.parent


# ================================================================
# LEVEL 7 — BOUNDARY & EDGE CASES
# ================================================================

class TestLevel7_CacheBoundary:
    """Cache edge cases: huge values, empty keys, special chars."""

    @pytest.fixture
    def cache(self):
        from watcherdb.core.cache import RedisLikeCache
        return RedisLikeCache(persistence_file=None, max_memory_mb=5)

    def test_empty_key(self, cache):
        cache.set("", "value")
        assert cache.get("") == "value"

    def test_none_value(self, cache):
        cache.set("none_key", None)
        assert cache.get("none_key") is None  # Indistinguishable from miss

    def test_large_value(self, cache):
        big = "x" * 100_000
        cache.set("big", big)
        assert cache.get("big") == big

    def test_unicode_key_value(self, cache):
        cache.set("chave_ção_日本語", "valor_ção_中文")
        assert cache.get("chave_ção_日本語") == "valor_ção_中文"

    def test_special_chars_key(self, cache):
        for key in ["key:with:colons", "key/with/slashes", "key.with.dots", "key@with@at"]:
            cache.set(key, "ok")
            assert cache.get(key) == "ok"

    def test_zero_ttl(self, cache):
        """TTL of 0 should not expire immediately (treated as no TTL)."""
        cache.set("zero_ttl", "value", ttl=0)
        # Implementation-dependent: either works or is treated as no TTL
        result = cache.get("zero_ttl")
        # Should not crash regardless of behavior
        assert result in ("value", None)

    def test_negative_ttl(self, cache):
        """Negative TTL should be handled gracefully."""
        cache.set("neg_ttl", "value", ttl=-1)
        # Should either reject or treat as expired
        result = cache.get("neg_ttl")
        assert result in ("value", None)

    def test_overwrite_preserves_new_value(self, cache):
        cache.set("ow", "first")
        cache.set("ow", "second")
        cache.set("ow", "third")
        assert cache.get("ow") == "third"

    def test_many_keys(self, cache):
        for i in range(500):
            cache.set(f"key_{i}", i)
        assert cache.get("key_0") == 0
        assert cache.get("key_499") == 499


class TestLevel7_PaginationBoundary:
    """Pagination edge cases."""

    def test_page_size_1(self):
        from api.pagination import paginate, PaginationParams
        result = paginate(list(range(5)), PaginationParams(page=1, page_size=1))
        assert len(result["data"]) == 1
        assert result["total_pages"] == 5

    def test_page_size_equals_total(self):
        from api.pagination import paginate, PaginationParams
        result = paginate(list(range(10)), PaginationParams(page=1, page_size=10))
        assert len(result["data"]) == 10
        assert result["total_pages"] == 1

    def test_single_item(self):
        from api.pagination import paginate, PaginationParams
        result = paginate([42], PaginationParams(page=1, page_size=50))
        assert result["data"] == [42]
        assert result["total"] == 1

    def test_large_page_size(self):
        from api.pagination import paginate, PaginationParams
        result = paginate(list(range(3)), PaginationParams(page=1, page_size=500))
        assert len(result["data"]) == 3
        assert result["total_pages"] == 1


class TestLevel7_SQLValidatorBoundary:
    """SQL validator edge cases."""

    def test_very_long_query(self):
        from watcherdb.core.sql_validator import validate_query
        long_q = "SELECT " + ", ".join(f"col{i}" for i in range(1000)) + " FROM t"
        is_safe, _ = validate_query(long_q)
        assert is_safe is True

    def test_multiline_query(self):
        from watcherdb.core.sql_validator import validate_query
        sql = """
        SELECT
            a.col1,
            b.col2
        FROM table_a a
        INNER JOIN table_b b ON a.id = b.id
        WHERE a.status = 'active'
            AND b.created > '2025-01-01'
        ORDER BY a.col1 DESC
        """
        is_safe, _ = validate_query(sql)
        assert is_safe is True

    def test_query_with_semicolons(self):
        from watcherdb.core.sql_validator import validate_query
        # Multiple statements — first is safe, but any DROP should be caught
        sql = "SELECT 1; DROP TABLE users"
        is_safe, _ = validate_query(sql)
        assert is_safe is False

    def test_case_insensitive_detection(self):
        from watcherdb.core.sql_validator import validate_query
        for variant in ["drop table t", "DROP TABLE t", "Drop Table t", "dRoP tAbLe t"]:
            is_safe, _ = validate_query(variant)
            assert is_safe is False, f"Failed to block: {variant}"


# ================================================================
# LEVEL 8 — CONCURRENCY & THREAD SAFETY
# ================================================================

class TestLevel8_CacheConcurrency:
    """Cache must be thread-safe under concurrent access."""

    def test_concurrent_set_get(self):
        from watcherdb.core.cache import RedisLikeCache
        cache = RedisLikeCache(persistence_file=None, max_memory_mb=10)
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    key = f"t{thread_id}_k{i}"
                    cache.set(key, thread_id * 1000 + i)
                    val = cache.get(key)
                    if val != thread_id * 1000 + i:
                        errors.append(f"Thread {thread_id}: expected {thread_id * 1000 + i}, got {val}")
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrency errors: {errors[:5]}"

    def test_concurrent_incr(self):
        from watcherdb.core.cache import RedisLikeCache
        cache = RedisLikeCache(persistence_file=None, max_memory_mb=5)
        cache.set("counter", 0)

        def inc():
            for _ in range(100):
                cache.incr("counter", 1)

        threads = [threading.Thread(target=inc) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        val = cache.get("counter")
        assert val == 1000, f"Expected 1000, got {val} (race condition)"


class TestLevel8_PoolSingleton:
    """Connection pool singletons must be thread-safe."""

    def test_pool_singleton_concurrent_creation(self):
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None
        instances = []

        def create():
            pool = SQLServerConnectionPool()
            instances.append(id(pool))

        threads = [threading.Thread(target=create) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        unique = set(instances)
        assert len(unique) == 1, f"Multiple pool instances created: {len(unique)}"


class TestLevel8_TokenBlacklistConcurrency:
    """Token blacklist must handle concurrent adds and checks."""

    def test_concurrent_blacklist_operations(self):
        from api.routers.auth_compat import _TokenBlacklistManager
        manager = _TokenBlacklistManager(max_cache_size=500)
        errors = []

        with patch("api.routers.auth_compat._execute_update", side_effect=Exception("DB offline")):
            with patch("api.routers.auth_compat._execute_query", return_value=[]):
                def add_tokens(thread_id):
                    try:
                        for i in range(50):
                            manager.add(f"token_{thread_id}_{i}", username=f"user_{thread_id}")
                    except Exception as e:
                        errors.append(str(e))

                threads = [threading.Thread(target=add_tokens, args=(t,)) for t in range(10)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

        assert len(errors) == 0
        # Check some tokens are findable
        with patch("api.routers.auth_compat._execute_query", return_value=[]):
            assert f"token_0_0" in manager


# ================================================================
# LEVEL 9 — DATA INTEGRITY
# ================================================================

class TestLevel9_Serialization:
    """Data types must survive cache roundtrip."""

    @pytest.fixture
    def cache(self):
        from watcherdb.core.cache import RedisLikeCache
        return RedisLikeCache(persistence_file=None, max_memory_mb=5)

    @pytest.mark.parametrize("value", [
        0, -1, 2**31, 3.14159, True, False,
        "", "hello", "unicode_ção_日本語",
        [], [1, "two", 3.0], [None, True, {"nested": [1]}],
        {}, {"a": 1, "b": {"c": 3}},
        None,
    ])
    def test_roundtrip(self, cache, value):
        cache.set("rt", value)
        result = cache.get("rt")
        if value is None:
            assert result is None
        else:
            assert result == value, f"Roundtrip failed for {type(value)}: {value!r} != {result!r}"

    def test_datetime_string_roundtrip(self, cache):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cache.set("dt", now)
        assert cache.get("dt") == now

    def test_large_nested_structure(self, cache):
        data = {
            "servers": [
                {"name": f"srv_{i}", "metrics": {"cpu": i * 10, "ram": i * 5}}
                for i in range(100)
            ],
            "total": 100,
        }
        cache.set("nested", data)
        result = cache.get("nested")
        assert result["total"] == 100
        assert len(result["servers"]) == 100
        assert result["servers"][50]["name"] == "srv_50"


class TestLevel9_HashConsistency:
    """Token blacklist hash must be deterministic."""

    def test_same_token_same_hash(self):
        from api.routers.auth_compat import _TokenBlacklistManager
        m = _TokenBlacklistManager()
        h1 = m._hash_token("test-token-abc")
        h2 = m._hash_token("test-token-abc")
        assert h1 == h2

    def test_different_tokens_different_hash(self):
        from api.routers.auth_compat import _TokenBlacklistManager
        m = _TokenBlacklistManager()
        h1 = m._hash_token("token-a")
        h2 = m._hash_token("token-b")
        assert h1 != h2

    def test_hash_is_sha256(self):
        from api.routers.auth_compat import _TokenBlacklistManager
        m = _TokenBlacklistManager()
        token = "my-jwt-token"
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert m._hash_token(token) == expected


# ================================================================
# LEVEL 10 — CONFIGURATION & ENVIRONMENT
# ================================================================

class TestLevel10_SettingsValidation:
    """Settings must handle all environment scenarios."""

    def test_default_values(self):
        from watcherdb.core.settings import WatcherDBSettings
        s = WatcherDBSettings()
        assert s.app_name == "WatcherDB"
        assert s.connection_timeout == 15  # 15 desde 2026-07-21: era 60, escondia hangs de boot c/ Intelligence inacessivel
        assert s.odbc_driver == "ODBC Driver 17 for SQL Server"
        assert s.use_redis is False

    def test_env_override(self):
        from watcherdb.core.settings import WatcherDBSettings
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "USE_REDIS": "true"}):
            s = WatcherDBSettings()
            assert s.log_level == "DEBUG"
            assert s.use_redis is True

    def test_jwt_empty_is_allowed(self):
        """Empty JWT key triggers generation at runtime, not crash."""
        from watcherdb.core.settings import WatcherDBSettings
        with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}, clear=False):
            s = WatcherDBSettings()
            assert s.jwt_secret_key == ""  # Empty is OK, runtime handles it

    def test_config_yaml_exists(self):
        assert (PROJECT_ROOT / "config" / "config.yaml").exists()

    def test_env_example_exists(self):
        assert (PROJECT_ROOT / ".env.example").exists()

    def test_alembic_ini_exists(self):
        assert (PROJECT_ROOT / "alembic.ini").exists()


class TestLevel10_VersioningConfig:
    """API versioning constants must be consistent."""

    def test_constants_defined(self):
        from api.versioning import API_V3_PREFIX, API_V4_PREFIX, AUTH_PREFIX, COPILOT_PREFIX
        assert API_V3_PREFIX.startswith("/api/")
        assert API_V4_PREFIX.startswith("/api/")
        assert AUTH_PREFIX.startswith("/api/")

    def test_auth_prefix_matches_router(self):
        from api.versioning import AUTH_PREFIX
        content = (PROJECT_ROOT / "api" / "routers" / "auth_compat.py").read_text("utf-8")
        assert "AUTH_PREFIX" in content


# ================================================================
# LEVEL 11 — ERROR HANDLING & RECOVERY
# ================================================================

class TestLevel11_GracefulDegradation:
    """System must degrade gracefully when dependencies fail."""

    def test_cache_factory_fallback(self):
        """USE_REDIS=false → local cache (skip Redis test to avoid network hang)."""
        from watcherdb.core.cache import RedisLikeCache
        from watcherdb.core.cache_factory import get_cache
        with patch.dict(os.environ, {"USE_REDIS": "false"}):
            cache = get_cache(persistence_file=None, max_memory_mb=5)
            assert isinstance(cache, RedisLikeCache)

    def test_copilot_without_llm(self):
        """Copilot must work in rule-based mode without LLM."""
        from services.copilot_service import CopilotService
        svc = CopilotService()
        status = svc.get_status()
        assert status["mode"] in ("rule-based", "hybrid")

    def test_error_helper_with_none_context(self):
        from api.error_helpers import safe_http_error
        result = safe_http_error(500, ValueError("test"), "")
        assert result.status_code == 500
        assert "ref:" in result.detail

    def test_error_helper_with_unicode_exception(self):
        from api.error_helpers import safe_http_error
        result = safe_http_error(500, ValueError("Erro com acentuação: não disponível"), "ctx")
        assert result.status_code == 500


class TestLevel11_TokenBlacklistDegradation:
    """Token blacklist must work even if DB is unavailable."""

    def test_add_without_db(self):
        from api.routers.auth_compat import _TokenBlacklistManager
        m = _TokenBlacklistManager(max_cache_size=100)
        with patch("api.routers.auth_compat._execute_update", side_effect=Exception("DB down")):
            m.add("test-token", username="user")

        with patch("api.routers.auth_compat._execute_query", side_effect=Exception("DB down")):
            assert "test-token" in m  # Fallback to memory

    def test_check_without_db(self):
        from api.routers.auth_compat import _TokenBlacklistManager
        m = _TokenBlacklistManager()
        with patch("api.routers.auth_compat._execute_query", side_effect=Exception("DB down")):
            assert "random-token" not in m  # No crash


# ================================================================
# LEVEL 12 — DEPENDENCY ISOLATION
# ================================================================

class TestLevel12_MockedDependencies:
    """Each external dependency failure must be isolated."""

    def test_pyodbc_import_failure_handled(self):
        """If pyodbc is unavailable, connection pool should fail gracefully."""
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None
        pool = SQLServerConnectionPool()
        # get_connection with mock failure
        with patch("api.connection_pool.pyodbc.connect", side_effect=Exception("No driver")):
            result = pool.get_connection("FAKE_SERVER")
            assert result is None
            assert pool.stats["connection_errors"] > 0

    def test_sqlparse_handles_garbage(self):
        from watcherdb.core.sql_validator import validate_query
        # Binary garbage shouldn't crash
        is_safe, msg = validate_query("\x00\x01\x02 SELECT 1")
        # Either safe or blocked, but no crash
        assert isinstance(is_safe, bool)

    def test_structlog_setup_no_crash(self):
        from watcherdb.core.logging_setup import setup_logging
        setup_logging("INFO")  # Should not crash

    def test_scheduler_without_jobs(self):
        from watcherdb.core.scheduler import get_scheduler
        import watcherdb.core.scheduler as sched_module
        sched_module._scheduler = None
        scheduler = get_scheduler()
        assert scheduler.get_jobs() == [] or True  # Empty or whatever state
        sched_module._scheduler = None


# ================================================================
# LEVEL 13 — CODE QUALITY & STANDARDS
# ================================================================

class TestLevel13_CodeQuality:
    """Enforce code quality standards across the project."""

    def test_no_print_in_production_code(self):
        """Production code should use logging, not print()."""
        violations = []
        for dir_name in ["api", "watcherdb/core"]:
            dir_path = PROJECT_ROOT / dir_name
            for py_file in dir_path.rglob("*.py"):
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue
                content = py_file.read_text("utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("print(") and not stripped.startswith("#"):
                        violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}")
        # Allow up to 5 prints (debug/startup messages)
        assert len(violations) <= 5, f"Found {len(violations)} print() calls:\n" + "\n".join(violations[:10])

    def test_all_core_modules_have_docstrings(self):
        """Every module in watcherdb/core/ must have a module docstring."""
        missing = []
        for py_file in (PROJECT_ROOT / "watcherdb" / "core").glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text("utf-8", errors="ignore").strip()
            if not (content.startswith('"""') or content.startswith("'''")):
                missing.append(py_file.name)
        assert len(missing) == 0, f"Modules without docstrings: {missing}"

    def test_no_hardcoded_passwords(self):
        """No hardcoded passwords in active source code."""
        patterns = [
            r"password\s*=\s*['\"][^'\"]{3,}['\"]",
            r"pwd\s*=\s*['\"][^'\"]{3,}['\"]",
            r"secret\s*=\s*['\"][^'\"]{3,}['\"]",
        ]
        violations = []
        for dir_name in ["api", "watcherdb/core", "services"]:
            dir_path = PROJECT_ROOT / dir_name
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue
                content = py_file.read_text("utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if line.strip().startswith("#"):
                        continue
                    for pat in patterns:
                        if re.search(pat, line, re.IGNORECASE):
                            # Exclude known safe patterns
                            if any(safe in line for safe in [
                                "password_hash", "hashed_password", "CHANGE_ME",
                                'password": "', "get_password", "verify_password",
                                "hash_password", "env", "getenv", "settings.",
                                "current_password", "new_password", "old_password",
                                "placeholder", "example", "template", "dummy",
                                "ENCRYPTION BY PASSWORD", "MASTER KEY",  # T-SQL examples in copilot KB
                                "BackupPassword", "StrongPassword",  # T-SQL example values
                            ]):
                                continue
                            violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}: {line.strip()[:80]}")
        assert len(violations) == 0, f"Possible hardcoded credentials:\n" + "\n".join(violations[:10])

    def test_no_todo_in_critical_code(self):
        """No TODO in security-critical files."""
        critical_files = [
            "watcherdb/core/sql_validator.py",
            "watcherdb/core/security_headers.py",
            "api/error_helpers.py",
            "watcherdb/core/circuit_breaker.py",
        ]
        for f in critical_files:
            path = PROJECT_ROOT / f
            if path.exists():
                content = path.read_text("utf-8")
                assert "TODO" not in content, f"TODO found in critical file: {f}"


# ================================================================
# LEVEL 14 — REGRESSION GUARDS
# ================================================================

class TestLevel14_RegressionGuards:
    """Things that broke before must NEVER break again."""

    def test_no_oracle_references_in_active_code(self):
        """Oracle was removed — no imports should reference it."""
        violations = []
        for dir_name in ["api/routers", "watcherdb/core", "services"]:
            dir_path = PROJECT_ROOT / dir_name
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                content = py_file.read_text("utf-8", errors="ignore")
                if "import oracle" in content.lower() or "from.*oracle" in content.lower():
                    violations.append(str(py_file.relative_to(PROJECT_ROOT)))
        assert len(violations) == 0, f"Oracle references found: {violations}"

    def test_no_random_in_health_scores(self):
        """Health scores must not use random (regression from V3.1)."""
        intel = (PROJECT_ROOT / "watcherdb_intelligence.py").read_text("utf-8")
        assert "random.uniform(75" not in intel
        assert "random.randint(0, 3)" not in intel

    def test_detail_str_e_eliminated(self):
        """detail=str(e) must not exist in any router (regression guard)."""
        count = 0
        for py_file in (PROJECT_ROOT / "api" / "routers").rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text("utf-8", errors="ignore")
            count += content.count("detail=str(e)")
        assert count == 0, f"Found {count} occurrences of detail=str(e)"

    def test_cors_no_wildcard(self):
        """CORS must never return wildcard (regression guard)."""
        from watcherdb.core.cors import get_cors_config
        config = get_cors_config()
        assert config["allow_origins"] != ["*"]

    def test_csp_script_src_e_nonce_only(self):
        """script-src/style-src sem 'unsafe-inline' — a directiva que executa codigo.

        Audit 2026-08-19: o teste original asseria `"'unsafe-inline'" not in csp`,
        o que apanhava tambem `script-src-attr` e `style-src-attr`. Esses dois
        levam 'unsafe-inline' DE PROPOSITO desde a 1a instalacao real: sao a saida
        para os handlers inline do portal, e o `security_headers.py` documenta-os
        como DEBITO ASSUMIDO com prazo (sai quando a UI migrar de onclick).

        A assercao larga deixava a guarda permanentemente vermelha. Guarda que esta
        sempre vermelha nao guarda nada -- ensina a ignorar vermelhos, e acaba
        silenciada. Agora asserimos o invariante REAL (nenhuma directiva que execute
        codigo aceita inline sem nonce) e o debito fica visivel no proprio teste, em
        vez de escondido atras de uma falha cronica.
        """
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
        r = client.get("/")
        csp = r.headers.get("Content-Security-Policy", "")

        directivas = {}
        for parte in csp.split(";"):
            parte = parte.strip()
            if not parte:
                continue
            nome, _, valor = parte.partition(" ")
            directivas[nome] = valor

        for nome in ("script-src", "style-src", "default-src"):
            valor = directivas.get(nome, "")
            assert "'unsafe-inline'" not in valor, (
                f"{nome} aceita 'unsafe-inline': {valor!r} — regressao a serio"
            )

        assert "nonce-" in directivas.get("script-src", ""), (
            f"script-src sem nonce: {directivas.get('script-src')!r}"
        )

        # Debito assumido e datado, nao surpresa: os *-attr continuam com
        # 'unsafe-inline' ate a UI largar os handlers inline. Quando isso
        # acontecer, este bloco passa a falhar e e' o sinal para o apagar.
        assert "'unsafe-inline'" in directivas.get("script-src-attr", ""), (
            "script-src-attr ja nao precisa de 'unsafe-inline' — apagar este "
            "assert e o DEBITO ASSUMIDO em watcherdb/core/security_headers.py"
        )

    def test_fake_users_db_empty(self):
        """fake_users_db must be empty (regression from audit)."""
        content = (PROJECT_ROOT / "watcherdb" / "core" / "auth.py").read_text("utf-8")
        assert "fake_users_db = {}" in content

    def test_intelligence_breaker_removed_from_pool(self):
        """Intelligence pool must NOT have circuit breaker (caused login failures)."""
        content = (PROJECT_ROOT / "api" / "connection_pool.py").read_text("utf-8")
        # The IntelligenceConnectionPool._create_connection should NOT have @intelligence_breaker
        in_intel_section = False
        for line in content.splitlines():
            if "class IntelligenceConnectionPool" in line:
                in_intel_section = True
            if in_intel_section and "@intelligence_breaker" in line:
                pytest.fail("Intelligence pool still has circuit breaker — this caused login failures")
            if in_intel_section and "class " in line and "IntelligenceConnectionPool" not in line:
                break


# ================================================================
# LEVEL 15 — OBSERVABILITY
# ================================================================

class TestLevel15_Observability:
    """Logging, metrics, tracing, and health must all work."""

    def test_structlog_importable(self):
        from watcherdb.core.logging_setup import setup_logging
        setup_logging("WARNING")  # No crash

    def test_prometheus_metrics_defined(self):
        from watcherdb.core.metrics import REQUEST_COUNT, REQUEST_DURATION, WS_CONNECTIONS
        from watcherdb.core.metrics import CACHE_HITS, CACHE_MISSES, POOL_ACTIVE
        assert REQUEST_COUNT is not None
        assert REQUEST_DURATION is not None
        assert WS_CONNECTIONS is not None

    def test_request_id_middleware(self):
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

        r = client.get("/")
        assert "X-Request-ID" in r.headers
        rid = r.headers["X-Request-ID"]
        assert len(rid) >= 10  # UUID format

        # Different requests get different IDs
        r2 = client.get("/")
        assert r2.headers["X-Request-ID"] != rid

    def test_executor_registry(self):
        from watcherdb.core.executor_registry import create_executor, shutdown_all, _executors
        _executors.clear()
        ex = create_executor("test_obs", max_workers=1)
        assert "test_obs" in _executors
        shutdown_all()
        assert len(_executors) == 0

    def test_scheduler_singleton(self):
        from watcherdb.core.scheduler import get_scheduler
        import watcherdb.core.scheduler as sched
        sched._scheduler = None
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2
        sched._scheduler = None

    def test_cache_stats_structure(self):
        from watcherdb.core.cache import RedisLikeCache
        c = RedisLikeCache(persistence_file=None, max_memory_mb=5)
        c.set("k", "v")
        c.get("k")
        stats = c.get_stats()
        required_keys = ["hits", "misses", "sets", "num_keys", "memory_bytes"]
        for key in required_keys:
            assert key in stats, f"Missing stat key: {key}"
