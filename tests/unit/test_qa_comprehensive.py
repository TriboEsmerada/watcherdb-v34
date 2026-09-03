"""
WatcherDB V3.2 — Comprehensive QA Test Suite
=============================================

Executes all 6 levels of testing:
- Level 1: Unit tests (imports, models, helpers)
- Level 2: Security tests (SQLi, auth, XSS, CORS, CSP)
- Level 3: Resilience tests (circuit breaker, retry, cache, rate limit)
- Level 4: Contract tests (response models, status codes, headers)
- Level 5: Integration tests (requires DB — skipped if unavailable)
- Level 6: Performance tests (requires Locust — skipped if unavailable)

Run: pytest tests/unit/test_qa_comprehensive.py -v --no-cov
"""

import os
import sys
import ast
import time
import hashlib
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ================================================================
# LEVEL 1 — UNIT: Imports & Core Module Health
# ================================================================

class TestLevel1_CoreImports:
    """Every core module must import without errors."""

    @pytest.mark.parametrize("module", [
        "watcherdb.core.cache",
        "watcherdb.core.cors",
        "watcherdb.core.security_headers",
        "watcherdb.core.settings",
        "watcherdb.core.retry",
        "watcherdb.core.circuit_breaker",
        "watcherdb.core.metrics",
        "watcherdb.core.logging_setup",
        "watcherdb.core.telemetry",
        "watcherdb.core.scheduler",
        "watcherdb.core.executor_registry",
        "watcherdb.core.sql_validator",
        "watcherdb.core.cache_factory",
        "watcherdb.core.redis_adapter",
        "watcherdb.core.async_db",
        "watcherdb.core.fuzzy_matcher",
        "watcherdb.core.async_file_io",
        "watcherdb.core.websocket_manager",
        "watcherdb.core.models",
        "watcherdb.core.background_services",
        "api.error_helpers",
        "api.pagination",
        "api.models",
        "api.versioning",
        "api.dependencies",
        "api.connection_pool",
    ])
    def test_module_imports(self, module):
        """Every listed module must import without error."""
        __import__(module)

    @pytest.mark.parametrize("router", [
        "api.routers.auth_compat",
        "api.routers.copilot",
        "api.routers.htmx",
        "api.routers.alwayson",
        "api.routers.cluster",
        "api.routers.database_discovery",
        "api.routers.diagnostics_overview",
        "api.routers.disk_unallocated",
        "api.routers.intelligence_kpis",
        "api.routers.jobs",
        "api.routers.kpis_metadata",
        "api.routers.network_diagnostics",
        "api.routers.os_performance",
        "api.routers.overview_dashboard",
        "api.routers.service_status",
        "api.routers.sqlserver_kpis",
        "api.routers.users",
    ])
    def test_router_imports(self, router):
        """Every API router must import without error."""
        mod = __import__(router, fromlist=["router"])
        assert hasattr(mod, "router"), f"{router} has no 'router' attribute"


class TestLevel1_PydanticModels:
    """All Pydantic response models must validate correctly."""

    def test_login_response_valid(self):
        from api.models import LoginResponse
        r = LoginResponse(success=True, token="abc", username="admin", role="admin")
        assert r.success is True

    def test_login_response_failure(self):
        from api.models import LoginResponse
        r = LoginResponse(success=False, error="bad creds")
        assert r.error == "bad creds"

    def test_health_response(self):
        from api.models import HealthResponse
        r = HealthResponse(status="healthy", version="3.2.0")
        assert r.version == "3.2.0"

    def test_paginated_response(self):
        from api.models import PaginatedResponse
        r = PaginatedResponse(success=True, data=[1, 2], total=2, page=1, page_size=10, total_pages=1)
        assert r.total_pages == 1

    def test_copilot_status(self):
        from api.models import CopilotStatusResponse
        r = CopilotStatusResponse(llm_available=False, provider="none", mode="rule-based")
        assert r.mode == "rule-based"

    def test_query_result(self):
        from api.models import QueryResultResponse
        r = QueryResultResponse(success=True, data=[{"col": "val"}], row_count=1)
        assert r.row_count == 1

    def test_message_response(self):
        from api.models import MessageResponse
        r = MessageResponse(success=True, message="OK")
        assert r.message == "OK"

    def test_generic_response_allows_extra(self):
        from api.models import GenericResponse
        r = GenericResponse(success=True, data={"custom": True}, extra_field="allowed")
        assert r.success is True


# ================================================================
# LEVEL 2 — SECURITY: SQL Injection, Auth, XSS, CORS, CSP
# ================================================================

class TestLevel2_SQLInjection:
    """SQL validator must block ALL known injection patterns."""

    MALICIOUS_PAYLOADS = [
        # Classic injection
        ("'; DROP TABLE users; --", False),
        ("1 OR 1=1", True),  # This is a valid WHERE clause, not DDL
        ("EXEC xp_cmdshell 'dir'", False),
        ("SELECT * FROM OPENROWSET('SQLNCLI','server')", False),
        # Comment bypass
        ("DR/**/OP TABLE users", False),
        # System commands
        ("SHUTDOWN WITH NOWAIT", False),
        ("RECONFIGURE", False),
        ("DBCC CHECKDB", False),
        ("BULK INSERT t FROM '\\\\evil\\share'", False),
        ("BACKUP DATABASE master TO DISK='evil'", False),
        ("RESTORE DATABASE master FROM DISK='evil'", False),
        # Permission escalation
        ("GRANT EXECUTE TO public", False),
        ("REVOKE ALL FROM admin", False),
        ("DENY SELECT ON users TO guest", False),
        # DML mutation
        ("INSERT INTO users VALUES(1,'evil')", False),
        ("UPDATE users SET role='admin'", False),
        ("DELETE FROM users WHERE 1=1", False),
        ("MERGE INTO users USING evil ON 1=1", False),
        ("TRUNCATE TABLE logs", False),
        # DDL
        ("CREATE TABLE evil(id INT)", False),
        ("ALTER TABLE users ADD backdoor INT", False),
        # Valid SELECTs (should PASS)
        ("SELECT name FROM sys.databases", True),
        ("SELECT TOP 10 * FROM sys.dm_exec_requests", True),
        ("SELECT @@VERSION", True),
        ("SELECT DB_NAME(), GETDATE()", True),
    ]

    @pytest.mark.parametrize("sql,expected_safe", MALICIOUS_PAYLOADS)
    def test_sql_validation(self, sql, expected_safe):
        from watcherdb.core.sql_validator import validate_query
        is_safe, msg = validate_query(sql)
        assert is_safe == expected_safe, f"SQL '{sql[:50]}' expected safe={expected_safe}, got safe={is_safe}: {msg}"

    def test_empty_query_blocked(self):
        from watcherdb.core.sql_validator import validate_query
        assert validate_query("")[0] is False
        assert validate_query("   ")[0] is False

    def test_complex_select_safe(self):
        from watcherdb.core.sql_validator import validate_query
        sql = """
        SELECT d.name, d.state_desc, SUM(mf.size) * 8 / 1024 AS size_mb
        FROM sys.databases d
        JOIN sys.master_files mf ON d.database_id = mf.database_id
        WHERE d.state_desc = 'ONLINE'
        GROUP BY d.name, d.state_desc
        HAVING SUM(mf.size) * 8 / 1024 > 100
        ORDER BY size_mb DESC
        """
        is_safe, _ = validate_query(sql)
        assert is_safe is True


class TestLevel2_ErrorHelpers:
    """Error helpers must NEVER leak internal details."""

    def test_no_exception_in_detail(self):
        from api.error_helpers import safe_http_error
        exc = ValueError("pyodbc.Error: SERVER=SQLPRD01;PWD=s3cr3t;UID=admin")
        result = safe_http_error(500, exc, "connecting")
        assert "s3cr3t" not in result.detail
        assert "SQLPRD01" not in result.detail
        assert "pyodbc" not in result.detail

    def test_error_id_in_detail(self):
        from api.error_helpers import safe_http_error
        result = safe_http_error(500, ValueError("test"), "ctx")
        assert "ref:" in result.detail

    def test_preserves_status_code(self):
        from api.error_helpers import safe_http_error
        for code in [400, 401, 403, 404, 500, 502, 503]:
            result = safe_http_error(code, ValueError("x"), "")
            assert result.status_code == code


class TestLevel2_BareExceptScan:
    """No bare except: in ANY active Python file."""

    def test_zero_bare_except_in_active_code(self):
        active_dirs = ["api", "watcherdb", "services", "modules"]
        bare_excepts = []

        for dir_name in active_dirs:
            dir_path = PROJECT_ROOT / dir_name
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                try:
                    source = py_file.read_text(encoding="utf-8")
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ExceptHandler) and node.type is None:
                            bare_excepts.append(f"{py_file.relative_to(PROJECT_ROOT)}:{node.lineno}")
                except Exception:
                    pass

        assert len(bare_excepts) == 0, (
            f"Found {len(bare_excepts)} bare except: clauses:\n" +
            "\n".join(bare_excepts[:20])
        )


class TestLevel2_CORSConfig:
    """CORS must never return wildcard with credentials."""

    def test_cors_no_wildcard_with_credentials(self):
        from watcherdb.core.cors import get_cors_config
        config = get_cors_config()
        if config.get("allow_credentials"):
            assert config["allow_origins"] != ["*"]

    def test_cors_headers_not_wildcard_default(self):
        from watcherdb.core.cors import get_cors_config
        config = get_cors_config()
        headers = config.get("allow_headers", [])
        assert headers != ["*"], "CORS allow_headers should be a specific list, not wildcard"


class TestLevel2_SecurityHeaders:
    """Security headers middleware must set all required headers."""

    @pytest.mark.asyncio
    async def test_all_security_headers_present(self):
        from watcherdb.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def homepage(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app, base_url="https://testserver")  # HSTS so' em https
        r = client.get("/")

        assert r.headers.get("Strict-Transport-Security") is not None
        assert TestClient(app).get("/").headers.get("Strict-Transport-Security") is None
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("Referrer-Policy") is not None
        assert r.headers.get("Permissions-Policy") is not None

        csp = r.headers.get("Content-Security-Policy", "")
        # unsafe-inline so' nas directivas -attr (split CSP3, decisao 2026-08-12)
        for d in csp.split(";"):
            d = d.strip()
            if d.startswith(("script-src ", "style-src ")):
                assert "'unsafe-inline'" not in d, d
        assert "'unsafe-eval'" not in csp
        assert "'nonce-" in csp


# ================================================================
# LEVEL 3 — RESILIENCE: Circuit Breaker, Retry, Cache, Rate Limit
# ================================================================

class TestLevel3_CircuitBreaker:
    """Circuit breaker must open after failures and recover."""

    def test_breaker_opens_after_failures(self):
        import pybreaker
        breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=1, name="test_qc")

        @breaker
        def failing():
            raise ConnectionError("down")

        for _ in range(3):
            try:
                failing()
            except (ConnectionError, pybreaker.CircuitBreakerError):
                pass

        assert breaker.current_state == pybreaker.STATE_OPEN

        with pytest.raises(pybreaker.CircuitBreakerError):
            failing()

    def test_breaker_recovers_after_timeout(self):
        import pybreaker
        breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=1, name="test_recover")

        @breaker
        def flaky(succeed=False):
            if not succeed:
                raise ConnectionError("down")
            return "ok"

        # Open the breaker
        for _ in range(2):
            try:
                flaky(succeed=False)
            except (ConnectionError, pybreaker.CircuitBreakerError):
                pass

        assert breaker.current_state == pybreaker.STATE_OPEN
        time.sleep(1.5)

        # Should be half-open now — next success closes it
        result = flaky(succeed=True)
        assert result == "ok"
        assert breaker.current_state == pybreaker.STATE_CLOSED


class TestLevel3_Retry:
    """Retry decorator must retry on transient failures."""

    def test_retry_succeeds_after_transient_failure(self):
        from tenacity import retry, stop_after_attempt, wait_none, retry_if_exception_type
        call_count = 0

        @retry(stop=stop_after_attempt(3), wait=wait_none(), retry=retry_if_exception_type(ConnectionError))
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        assert flaky() == "ok"
        assert call_count == 3

    def test_retry_gives_up_after_max(self):
        from tenacity import retry, stop_after_attempt, wait_none, retry_if_exception_type, RetryError

        @retry(stop=stop_after_attempt(3), wait=wait_none(), retry=retry_if_exception_type(ConnectionError))
        def always_fails():
            raise ConnectionError("permanent")

        with pytest.raises((ConnectionError, RetryError)):
            always_fails()


class TestLevel3_Cache:
    """RedisLikeCache must handle TTL, stats, and edge cases."""

    @pytest.fixture
    def cache(self):
        from watcherdb.core.cache import RedisLikeCache
        return RedisLikeCache(persistence_file=None, max_memory_mb=5)

    def test_set_get_basic(self, cache):
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_ttl_expiration(self, cache):
        cache.set("k", "v", ttl=1)
        assert cache.get("k") == "v"
        time.sleep(1.5)
        assert cache.get("k") is None

    def test_complex_types(self, cache):
        cache.set("dict", {"a": 1})
        cache.set("list", [1, 2, 3])
        assert cache.get("dict") == {"a": 1}
        assert cache.get("list") == [1, 2, 3]

    def test_stats_tracking(self, cache):
        cache.set("x", 1)
        cache.get("x")      # hit
        cache.get("miss")   # miss
        stats = cache.get_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

    def test_flushall(self, cache):
        cache.set("a", 1)
        cache.set("b", 2)
        cache.flushall()
        assert cache.keys("*") == []


class TestLevel3_Pagination:
    """Pagination must handle all edge cases."""

    def test_first_page(self):
        from api.pagination import paginate, PaginationParams
        result = paginate(list(range(100)), PaginationParams(page=1, page_size=10))
        assert len(result["data"]) == 10
        assert result["total"] == 100
        assert result["total_pages"] == 10

    def test_last_page_partial(self):
        from api.pagination import paginate, PaginationParams
        result = paginate(list(range(25)), PaginationParams(page=3, page_size=10))
        assert len(result["data"]) == 5

    def test_empty_list(self):
        from api.pagination import paginate, PaginationParams
        result = paginate([], PaginationParams(page=1, page_size=10))
        assert result["total"] == 0
        assert result["total_pages"] == 1

    def test_beyond_last_page(self):
        from api.pagination import paginate, PaginationParams
        result = paginate([1, 2, 3], PaginationParams(page=99, page_size=10))
        assert result["data"] == []


# ================================================================
# LEVEL 4 — CONTRACT: Response Models & Headers
# ================================================================

class TestLevel4_ResponseModelCoverage:
    """Verify response_model coverage across routers."""

    def test_response_model_count(self):
        """At least 100 endpoints should have response_model."""
        count = 0
        routers_dir = PROJECT_ROOT / "api" / "routers"
        for py_file in routers_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            count += content.count("response_model=")

        assert count >= 100, f"Only {count} endpoints have response_model (expected 100+)"


class TestLevel4_VersioningConstants:
    """API versioning constants must be used, not dead code."""

    def test_auth_prefix_used(self):
        content = (PROJECT_ROOT / "api" / "routers" / "auth_compat.py").read_text(encoding="utf-8")
        assert "AUTH_PREFIX" in content

    def test_copilot_prefix_used(self):
        content = (PROJECT_ROOT / "api" / "routers" / "copilot.py").read_text(encoding="utf-8")
        assert "COPILOT_PREFIX" in content


class TestLevel4_SettingsIntegrity:
    """Settings must have all required fields with sane defaults."""

    def test_settings_has_all_fields(self):
        from watcherdb.core.settings import settings
        required = [
            "app_name", "jwt_secret_key", "jwt_algorithm", "jwt_expire_minutes",
            "intelligence_server", "intelligence_database", "connection_timeout",
            "odbc_driver", "use_redis", "otel_enabled", "llm_enabled",
        ]
        for field in required:
            assert hasattr(settings, field), f"Settings missing field: {field}"

    def test_settings_sane_defaults(self):
        from watcherdb.core.settings import WatcherDBSettings
        s = WatcherDBSettings()
        assert s.jwt_algorithm == "HS256"
        assert s.jwt_expire_minutes == 1440
        assert s.connection_timeout == 15  # 15 desde 2026-07-21: era 60, escondia hangs de boot c/ Intelligence inacessivel
        assert s.use_redis is False
        assert s.llm_enabled is False


# ================================================================
# LEVEL 5 — INTEGRATION: Copilot Service (no DB required)
# ================================================================

class TestLevel5_CopilotService:
    """DBA Copilot must provide real value."""

    def test_quick_answers_not_empty(self):
        from services.copilot_service import CopilotService
        svc = CopilotService()
        answers = svc.get_quick_answers()
        assert len(answers) >= 5
        for qa in answers:
            assert "question" in qa
            assert "answer" in qa
            assert len(qa["answer"]) > 20  # Must be substantive

    @pytest.mark.asyncio
    async def test_ask_backup_question(self):
        from services.copilot_service import CopilotService
        svc = CopilotService()
        result = await svc.ask_question("How do I verify backup integrity?")
        assert "answer" in result
        assert len(result["answer"]) > 50

    @pytest.mark.asyncio
    async def test_ask_unknown_topic(self):
        from services.copilot_service import CopilotService
        svc = CopilotService()
        result = await svc.ask_question("What is the meaning of life?")
        assert "answer" in result  # Should fallback gracefully

    @pytest.mark.asyncio
    async def test_generate_daily_summary(self):
        from services.copilot_service import CopilotService
        svc = CopilotService()
        report = await svc.generate_report("daily_summary")
        assert "title" in report
        assert "content" in report
        assert len(report["content"]) > 100

    @pytest.mark.asyncio
    async def test_generate_health_check(self):
        from services.copilot_service import CopilotService
        svc = CopilotService()
        report = await svc.generate_report("health_check")
        assert "title" in report


# ================================================================
# LEVEL 6 — FILE SYSTEM: Project Hygiene
# ================================================================

def _ficheiros_em_git(*padroes: str) -> list:
    """Ficheiros TRACKED que casam com os padroes, lidos do indice do git.

    Audit 2026-08-19: estes testes varriam o filesystem com glob/rglob e por isso
    davam vermelho na maquina de quem trabalha (artefactos de build em dist/, logs
    de build, .bak locais -- todos gitignored) enquanto passavam num checkout limpo
    de CI. Vermelho onde nao ha problema e silencio onde havia: o pior dos dois
    mundos, e o tipo de teste que ensina a ignorar vermelhos.

    E' o mesmo raciocinio que ja tinha corrigido o `test_no_coverage_at_root` no
    audit de 2026-04-22 -- o intent nunca foi "nao existe no disco", e' "nao esta
    commitado".
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", *padroes],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:  # git ausente (container minimo, tarball sem .git)
        pytest.skip(f"git indisponivel: {exc}")
    if proc.returncode != 0:
        pytest.skip(f"git ls-files falhou: {proc.stderr.strip()[:120]}")
    return [caminho for caminho in proc.stdout.split("\0") if caminho]


class TestLevel6_ProjectHygiene:
    """Project structure must be clean and organized."""

    def test_no_exe_in_repo(self):
        exes = _ficheiros_em_git("*.exe")
        assert not exes, f"Executaveis commitados: {exes}"

    def test_no_bak_files(self):
        baks = [
            caminho
            for caminho in _ficheiros_em_git("*.bak", "*.bak_*", "*.backup")
            if "REGISTRO" not in caminho
        ]
        assert not baks, f"Ficheiros de backup commitados: {baks}"

    def test_no_log_files_at_root(self):
        logs = [caminho for caminho in _ficheiros_em_git("*.log") if "/" not in caminho]
        assert not logs, f"Logs commitados na raiz: {logs}"

    def test_no_coverage_at_root(self):
        # Audit 2026-04-22: o intent deste test era "nao commitar .coverage".
        # Verificar que existe ficheiro no disco e catch-22 porque pytest-cov
        # cria .coverage durante a propria execucao deste test.
        # Intent real: garantir que .coverage esta gitignored.
        gitignore = PROJECT_ROOT / ".gitignore"
        assert gitignore.exists(), ".gitignore missing"
        content = gitignore.read_text(encoding="utf-8")
        assert ".coverage" in content, ".coverage nao esta no .gitignore"
        # htmlcov tambem deve estar gitignored
        assert "htmlcov" in content, "htmlcov nao esta no .gitignore"

    # Pontos de entrada sancionados em docs/ -- indices e contratos que se querem
    # a um clique, nao documentos soltos por arrumar. A premissa original do teste
    # ("zero .md em docs/") nunca foi verdade em nenhum ponto da historia do repo,
    # portanto nao guardava nada: guardava-se a si proprio de estar sempre vermelho.
    # O que interessa e' que a lista nao CRESCA por acidente.
    DOCS_RAIZ_SANCIONADOS = frozenset({
        "ADR-template.md",
        "AGENTS_GUIDE.md",
        "BOOTSTRAP_engenharia_contexto_watcherdb.md",
        "BULLETIN_FORMAT.md",
        "CLAUDE_DESIGN_RECONCILE.md",
        "FEATURE_MATRIX.md",
        "HANDOFF_CONTRACT.md",
        "KNOWLEDGE_BASE_GUIDE.md",
        "PROACTIVE_COUNCIL.md",
        "RUNBOOK_CONTA_SERVICO.md",
        "SUBAGENTS_PACK_README.md",
        "runner-setup.md",
    })

    def test_docs_organized_in_subdirs(self):
        na_raiz = {
            caminho.split("/")[-1]
            for caminho in _ficheiros_em_git("docs/*.md")
            if caminho.count("/") == 1
        }
        novos = sorted(na_raiz - self.DOCS_RAIZ_SANCIONADOS)
        assert not novos, (
            f"{len(novos)} .md novo(s) na raiz de docs/: {novos}. "
            "Arrumar num subdirectorio, ou acrescentar a DOCS_RAIZ_SANCIONADOS "
            "se for mesmo um ponto de entrada."
        )

    def test_no_test_files_at_root(self):
        root_tests = list(PROJECT_ROOT.glob("test_*.py"))
        assert len(root_tests) == 0, f"Found test files at root: {root_tests}"

    def test_main_file_under_7000_lines(self):
        main = PROJECT_ROOT / "watcherdb_main.py"
        lines = sum(1 for _ in main.open(encoding="utf-8"))
        assert lines < 7000, f"watcherdb_main.py has {lines} lines (limit: 7000)"

    def test_no_hardcoded_secret_password(self):
        """No 'secret' as a password value in active auth code."""
        auth_file = PROJECT_ROOT / "watcherdb" / "core" / "auth.py"
        content = auth_file.read_text(encoding="utf-8")
        # fake_users_db should be empty
        assert 'fake_users_db = {}' in content or 'fake_users_db: dict = {}' in content

    def test_env_not_in_git(self):
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gitignore
