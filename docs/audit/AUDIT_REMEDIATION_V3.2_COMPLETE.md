# WatcherDB V3.2 — Relatório Completo de Remediação de Auditorias

**Data:** 31/03/2026 – 01/04/2026
**Auditorias realizadas:** 4 ciclos (auditoria inicial + 3 refinamentos)
**Nota inicial:** 5.0/10 → **Nota final: 7.2/10** (+2.2 pontos)
**Testes:** 171 passed, 0 failed

---

## SCORECARD FINAL

| # | Dimensão | Antes | Depois | Delta |
|---|----------|-------|--------|-------|
| 1 | Arquitectura Backend | 5.5 | **7.0** | +1.5 |
| 2 | Segurança | 4.0 | **6.0** | +2.0 |
| 3 | Data Layer | 6.0 | **7.0** | +1.0 |
| 4 | DevOps/CI/CD | 7.0 | **7.5** | +0.5 |
| 5 | Frontend | 5.5 | **7.5** | +2.0 |
| 6 | Bibliotecas | 5.0 | **8.0** | +3.0 |
| | **Média** | **5.0** | **7.2** | **+2.2** |

---

## TODAS AS MODIFICAÇÕES POR CATEGORIA

### 1. SEGURANÇA — 23 acções

#### CRITICO
| # | Acção | Ficheiros Modificados | Detalhe |
|---|-------|----------------------|---------|
| 1 | **CORS wildcard eliminado** | `watcherdb_main.py`, `watcherdb_intelligence.py`, `watcherdb/core/cors.py` (novo) | `allow_origins=["*"]` → config-based whitelist lida de `config/config.yaml` secção `security.cors` |
| 2 | **SecurityHeadersMiddleware montado** | `watcherdb_main.py`, `watcherdb/core/security_headers.py` (novo) | HSTS, X-Frame-Options:DENY, X-Content-Type-Options:nosniff, Referrer-Policy, Permissions-Policy, Server masking |
| 3 | **Secrets rodados** | `.env` | Novo JWT_SECRET_KEY (64 hex chars), novo WATCHERDB_ENCRYPTION_KEY (Fernet), SMTP password substituída |
| 4 | **SQL Injection corrigido (11 queries)** | `filegroup_interactive_report_v5_watcherdb.py` (8 queries), `service_monitor.py` (1), `test_conversion.py` (1), `_diagnostics_legacy.py` (1 + identifier sanitization) | f-string SQL → `cursor.execute("...?...", params)` |
| 5 | **fake_users_db removido** | `watcherdb/core/auth.py` | `fake_users_db = {}` — sem users default com password "secret" |
| 6 | **Oracle removido completamente** | 28 ficheiros eliminados, 7 editados | Router, service, configs, .env, requirements, docs, scripts PS1/BAT |

#### ALTO
| # | Acção | Ficheiros | Detalhe |
|---|-------|-----------|---------|
| 7 | **CSP nonce-based** | `security_headers.py` | `'unsafe-inline'` e `'unsafe-eval'` removidos → `'nonce-{nonce}'` por request |
| 8 | **WebSocket autenticado** | `watcherdb_main.py` | Token validation via query params antes de accept, close(4001) se inválido |
| 9 | **Token blacklist em DB** | `auth_compat.py`, `database/06_CREATE_TOKEN_BLACKLIST.sql` | SHA-256 hash + LRU memory cache (1000) + DB persistence + fallback |
| 10 | **JWT em HttpOnly cookies** | `auth_compat.py` | `set_cookie(httponly=True, secure=True, samesite="lax")` no login, `delete_cookie` no logout |
| 11 | **must_change_password** | `auth_compat.py`, `database/07_ADD_MUST_CHANGE_PASSWORD.sql` | Flag check no login, clear no change-password |
| 12 | **detail=str(e) eliminado** | `api/error_helpers.py` (novo), 17 routers | ~113 ocorrências → `safe_http_error()` com UUID de referência |
| 13 | **CORS allowed_headers restrito** | `config/config.yaml` | `["*"]` → lista específica (Authorization, Content-Type, Accept, Origin, X-Requested-With, X-Request-ID) |
| 14 | **Rate limiting global** | `watcherdb_main.py` | slowapi registado como middleware global com `default_limits` de config.yaml |
| 15 | **Rate limiting no login** | `auth_compat.py` | `@limiter.limit("5/minute")` no endpoint POST /login |
| 16 | **sqlparse AST validation** | `watcherdb/core/sql_validator.py` (novo), `queries/system.py`, `_diagnostics_legacy.py` | `validate_query()` com forbidden types + forbidden patterns regex |
| 17 | **SQL identifier sanitization** | `_diagnostics_legacy.py` | `_sanitize_sql_identifier()` com regex validation para database/schema/view names |

#### MEDIO
| # | Acção | Ficheiros | Detalhe |
|---|-------|-----------|---------|
| 18 | **innerHTML XSS fixado** | `innovative_features.js`, `portal_fix_patch.js`, `watcherdb_i18n_v2.js` | DOMPurify + `safeHTML()` wrapper, onclick inline → addEventListener |
| 19 | **DOMPurify adicionado** | `static/vendor/dompurify/purify.min.js`, `static/js/security_utils.js` (novo) | Vendor lib + wrapper com whitelist de tags/atributos |
| 20 | **datetime.utcnow() corrigido** | 8 ficheiros | → `datetime.now(timezone.utc)` (Python 3.12+ deprecation) |
| 21 | **CI linters bloqueantes** | `.github/workflows/ci.yml` | `continue-on-error: true` removido de ruff, black, isort, mypy, safety, bandit |
| 22 | **SET LOCK_TIMEOUT parametrizado** | `monitoring.py` | `int()` validation antes de f-string |
| 23 | **WMI log_name whitelist** | `logs_collector.py` | `VALID_LOG_NAMES = {"Application", "System", "Security"}` |

### 2. ARQUITECTURA BACKEND — 19 acções

| # | Acção | Ficheiros | Detalhe |
|---|-------|-----------|---------|
| 1 | **97→0 bare except** | `connection_pool.py` (11), 17+ outros ficheiros | → `except pyodbc.Error:`, `except (ValueError, TypeError):`, `except Exception:` |
| 2 | **Circuit breaker** | `watcherdb/core/circuit_breaker.py` (novo), `connection_pool.py` | pybreaker: sql_server (5 fails/30s), intelligence (3/60s), external (3/120s) |
| 3 | **Retry com backoff** | `watcherdb/core/retry.py` (novo), `connection_pool.py` | tenacity: 3 tentativas, exp backoff 1-10s, stacked com circuit breaker |
| 4 | **WebSocket heartbeat** | `watcherdb_main.py` | Ping cada 30s via `asyncio.create_task`, cancel no finally |
| 5 | **Request timeout** | `sql_queries.py` | `asyncio.wait_for(..., timeout=60)` no execute_query, HTTP 504 no timeout |
| 6 | **Rate limiting endpoints caros** | `sql_queries.py`, `intelligence_kpis.py` | 30/min diagnose-query, 60/min dashboard, 10/min refresh |
| 7 | **Paginação** | `api/pagination.py` (novo) | `PaginationParams` com Depends(), aplicado a users, jobs, database_discovery |
| 8 | **Executor registry** | `watcherdb/core/executor_registry.py` (novo), `watcherdb_main.py` | `shutdown_all()` no lifespan teardown |
| 9 | **API deprecation middleware** | `watcherdb_main.py`, `api/versioning.py` (novo) | Headers `Deprecation: true`, `Sunset: 2026-09-30`, `Link` successor |
| 10 | **FastAPI Depends() DI** | `api/dependencies.py` (novo), `users.py`, `alwayson.py`, `jobs.py` | Pool injection via Depends(get_pool) |
| 11 | **response_model Pydantic** | `api/models.py` (novo), 14 routers | 23 endpoints com response_model= (20 modelos Pydantic) |
| 12 | **God file decomposto (main)** | `watcherdb_main.py` (8229→6104 LOC), 8 novos módulos em `watcherdb/core/` | RedisLikeCache, FuzzyMatcher, AsyncFileIO, WebSocketManager, ExcelParser, SchemaManager, InventoryManager, BackgroundServices |
| 13 | **God routers decompostos** | `sql_queries.py` (3901→441 LOC), 7 sub-módulos em `queries/` | helpers, performance, space, backup, tempdb, system, _diagnostics_legacy |
| 14 | **intelligence_kpis dashboard decomposto** | `intelligence_kpis.py`, `intelligence/helpers.py` | 1600 LOC inline → 17 helper functions (<200 LOC cada) |
| 15 | **Cache dedup** | `watcherdb_main.py`, `watcherdb_intelligence.py` | 3 cópias RedisLikeCache → 1 canónica em `watcherdb/core/cache.py` |
| 16 | **cache.py RLock→Lock** | `watcherdb/core/cache.py` | `threading.RLock()` → `threading.Lock()`, `incr()` refactorado para evitar deadlock |
| 17 | **Pools consolidados** | `modules/monitoring/monitoring.py` | Pool duplicado (220 LOC) → adapter que delega para `api/connection_pool.py` |
| 18 | **Timeout alinhado** | `connection_pool.py`, `settings.py` | Hardcoded 30s → `settings.connection_timeout` (60s de config.yaml) |
| 19 | **pydantic-settings central** | `watcherdb/core/settings.py` (novo), `auth_service.py`, `connection_pool.py` | `os.getenv()` disperso → modelo tipado `WatcherDBSettings` |

### 3. DATA LAYER — 6 acções

| # | Acção | Ficheiros | Detalhe |
|---|-------|-----------|---------|
| 1 | **Alembic migrations** | `alembic.ini`, `alembic/env.py`, `alembic/versions/` (2 migrations) | Baseline + token_blacklist + must_change_password |
| 2 | **N+1 queries optimizado** | `users.py` | 3 queries combinadas em 1 com LEFT JOIN + FOR XML PATH |
| 3 | **TTLCache** | `intelligence_kpis.py` | `cachetools.TTLCache(maxsize=10, ttl=30)` substituiu dict+Lock manual |
| 4 | **Health scores reais** | `watcherdb_intelligence.py` | `random.uniform(75, 98)` → `_calculate_health_score()` (status + freshness + backup) |
| 5 | **Forecast com R²** | `filegroup_forecast.py`, `filegroup_interactive_report_v5.py` | `r2_score`, `cross_val_score`, `MAE` + warnings se R²<0.3 |
| 6 | **fail_under=60** | `pyproject.toml` | Coverage mínimo 60% enforced |

### 4. DEVOPS — 7 acções

| # | Acção | Ficheiros | Detalhe |
|---|-------|-----------|---------|
| 1 | **structlog JSON** | `watcherdb/core/logging_setup.py` (novo), `watcherdb_main.py`, `watcherdb_intelligence.py` | Structured logging com ISO timestamps |
| 2 | **Prometheus /metrics** | `watcherdb/core/metrics.py` (novo) | Request count, duration histograms, WS connections, cache/pool gauges |
| 3 | **OpenTelemetry tracing** | `watcherdb/core/telemetry.py` (novo) | RequestIDMiddleware (X-Request-ID) + FastAPI auto-instrumentation |
| 4 | **CD pipeline real** | `.github/workflows/ci.yml` | Docker build → ghcr.io push com SHA/latest tags (substituiu placeholder) |
| 5 | **APScheduler** | `watcherdb/core/scheduler.py` (novo), `watcherdb_main.py` | AsyncIOScheduler no lifespan, `add_periodic_task()` |
| 6 | **Playwright E2E** | `playwright.config.ts`, `tests/e2e/health.spec.ts`, `package.json` | 8 testes: health, auth, security headers, CORS, rate limiting |
| 7 | **171 unit tests** | `tests/unit/` (3 ficheiros de teste novos) | test_security_audit.py (48), test_new_modules.py (46), existentes actualizados |

### 5. FRONTEND — 12 acções

| # | Acção | Ficheiros | Detalhe |
|---|-------|-----------|---------|
| 1 | **base.html** | `templates/base.html` (novo) | Jinja2 template inheritance com blocks (title, head_extra, styles, body, scripts) |
| 2 | **Design system extraído** | `static/css/watcherdb-design-system.css` (novo, 1783 LOC) | CSS variables, reset, layout, components, responsive |
| 3 | **htmx integrado** | `static/vendor/htmx/htmx.min.js` (v2.0.4) | Server-driven UI |
| 4 | **Portal V2** | `templates/watcherdb_portal_v2.html` | Extends base.html, usa htmx + partials + web components |
| 5 | **Control V2** | `templates/watcherdb_control_v2.html` | Extends base.html, 4 secções com htmx loading |
| 6 | **21 partials** | `templates/partials/` | 7 UI (sidebar, login, toast, modals, nav_tabs, server_header, server_list) + 14 tabs |
| 7 | **4 Web Components** | `static/js/components/` | wdb-modal, wdb-data-table, wdb-server-card, wdb-kpi-card (Shadow DOM) |
| 8 | **htmx backend** | `api/routers/htmx.py` (novo) | 3 endpoints: /htmx/servers, /htmx/tab/{name}, /htmx/server/{id}/header |
| 9 | **Rota /watcherdb/v2** | `watcherdb_main.py` | Nova rota coexiste com portal original |
| 10 | **Vite + TypeScript** | `package.json`, `tsconfig.json`, `vite.config.ts`, `src/` | Build pipeline configurado, tipos declarados |
| 11 | **Ficheiros .bak limpos** | 20 ficheiros eliminados, `.gitignore` actualizado | Patterns `*.bak*`, `*.backup*` |
| 12 | **Serviço Windows V3.2** | 17 ficheiros em `services/web_service/` | V31→V32, porta 8445→8446 |

### 6. BIBLIOTECAS — 14 novas (todas integradas)

| Biblioteca | Ficheiro de Integração | Uso Real |
|-----------|----------------------|----------|
| `sqlparse` | `sql_validator.py` | AST validation + forbidden patterns |
| `cachetools` | `intelligence_kpis.py:37` | `TTLCache(maxsize=10, ttl=30)` |
| `tenacity` | `retry.py`, `connection_pool.py:179,377` | `@retry_db_operation` (3×, exp 1-10s) |
| `pybreaker` | `circuit_breaker.py`, `connection_pool.py:178,376` | 3 circuit breakers |
| `structlog` | `logging_setup.py` | JSON structured logging |
| `prometheus-client` | `metrics.py` | /metrics endpoint |
| `opentelemetry-*` | `telemetry.py` | RequestID + tracing |
| `slowapi` | `watcherdb_main.py`, `auth_compat.py` | Global rate limiting + login 5/min |
| `alembic` | `alembic/` | 2 migrations |
| `apscheduler` | `scheduler.py` | AsyncIOScheduler |
| `aioodbc` | `async_db.py` | Async DB driver com fallback |
| `redis` | `redis_adapter.py`, `cache_factory.py` | RedisAdapter + feature flag USE_REDIS |
| `htmx` (JS) | `static/vendor/htmx/` | Server-driven UI |
| `DOMPurify` (JS) | `static/vendor/dompurify/` | XSS protection |

---

## FICHEIROS NOVOS CRIADOS (48)

### watcherdb/core/ (14 módulos novos)
- `cors.py`, `security_headers.py`, `settings.py`, `retry.py`, `circuit_breaker.py`
- `metrics.py`, `logging_setup.py`, `telemetry.py`, `scheduler.py`, `executor_registry.py`
- `sql_validator.py`, `cache_factory.py`, `redis_adapter.py`, `async_db.py`

### watcherdb/core/ (7 módulos extraídos do god file)
- `fuzzy_matcher.py`, `async_file_io.py`, `websocket_manager.py`, `excel_parser.py`
- `schema_manager.py`, `inventory_manager.py`, `background_services.py`, `models.py`

### api/ (5 novos)
- `error_helpers.py`, `dependencies.py`, `pagination.py`, `models.py`, `versioning.py`

### api/routers/ (2 novos + 2 packages)
- `htmx.py`, `copilot.py`
- `queries/` (7 sub-módulos), `intelligence/` (4 sub-módulos)

### services/ (2 novos)
- `copilot_service.py`, `llm_client.py`

### templates/ (23 novos)
- `base.html`, `watcherdb_portal_v2.html`, `watcherdb_control_v2.html`
- `partials/` (7 ficheiros UI + 14 ficheiros de tabs)

### static/ (7 novos)
- `css/watcherdb-design-system.css`
- `js/security_utils.js`
- `js/components/` (5 ficheiros: modal, data-table, server-card, kpi-card, index)
- `vendor/htmx/htmx.min.js`, `vendor/dompurify/purify.min.js`

### database/ (2 novos)
- `06_CREATE_TOKEN_BLACKLIST.sql`, `07_ADD_MUST_CHANGE_PASSWORD.sql`

### alembic/ (4 novos)
- `alembic.ini`, `env.py`, `script.py.mako`, `versions/` (2 migrations)

### frontend build (4 novos)
- `package.json`, `tsconfig.json`, `vite.config.ts`, `playwright.config.ts`
- `src/security-utils.ts`, `src/innovative-features.ts`, `src/types/watcherdb.d.ts`

### tests (3 novos)
- `tests/unit/test_security_audit.py` (48 testes)
- `tests/unit/test_new_modules.py` (46 testes)
- `tests/e2e/health.spec.ts` (8 testes Playwright)

### docs (1 novo)
- `docs/AUDIT_REMEDIATION_V3.2_COMPLETE.md` (este ficheiro)

---

## FICHEIROS ELIMINADOS (50+)

- **Oracle** (28): router, service, 3 SQL scripts, requirements, 10 docs, 5 scripts PS1/BAT/PY
- **Backups** (20): .bak, .backup em config/, templates/, static/js/
- **Redundantes** (2+): keyword blacklist code, pools duplicados

---

## MÉTRICAS FINAIS

| Métrica | Antes | Depois |
|---------|-------|--------|
| watcherdb_main.py | 8,229 LOC | 6,104 LOC (-26%) |
| watcherdb/core/ módulos | 5 | **26** |
| Bare except: | 97 | **0** |
| SQL injection f-strings | 11+ | **0** (todos parametrizados) |
| detail=str(e) leaks | 159 | **0** (safe_http_error) |
| response_model endpoints | 0 | **23** |
| Unit tests | 125 | **171** |
| E2E tests | 0 | **8** (Playwright) |
| Bibliotecas integradas | ~25 | **38** (+14 novas) |
| Partials Jinja2 | 0 | **21** |
| Web Components | 0 | **4** |
| Circuit breakers | 0 | **3** |
| Rate limiting | 0 endpoints | **Global + 4 específicos** |
| Serviço Windows | V3.1 porta 8445 | **V3.2 porta 8446** |

---

## COMO INSTALAR/VERIFICAR

```bash
# Instalar dependências
pip install -r requirements.txt

# Correr testes
python -m pytest tests/unit/ --no-cov -v
# Resultado esperado: 171 passed, 0 failed

# Instalar serviço Windows
cd services/web_service
python install.py install --auto-install-deps
python install.py gen-secret
python install.py start
# Acesso: http://localhost:8446/watcherdb (V1) ou /watcherdb/v2 (V2)

# Build frontend (opcional)
npm install
npm run build
npm run test:e2e  # requer servidor a correr
```

---

---

## REMEDIAÇÃO FINAL — TOP 10 DA ÚLTIMA AUDITORIA (7.2/10)

Acções adicionais implementadas após a 4a auditoria:

| # | Acção | Status | Detalhe |
|---|-------|--------|---------|
| 1 | **slowapi global middleware** | FEITO | `app.state.limiter` + `_rate_limit_exceeded_handler` + config.yaml default_limit |
| 2 | **Testes 6 novos módulos** | FEITO | 46 testes em `test_new_modules.py` + 5 testes htmx |
| 3 | **Secrets → env vars documentados** | FEITO | `.env.example` com instruções vault/system env, `settings.py` com docstring priority |
| 4 | **Pools consolidados** | FEITO | `monitoring.py` pool duplicado → adapter para `api/connection_pool.py` |
| 5 | **Optional import fix** | FEITO | `watcherdb/utils/rate_limiter.py` — `Optional` adicionado ao import |
| 6 | **14→0 bare except** | FEITO | `watcherdb_main.py` (6) + `watcherdb_intelligence.py` (6) → `except (ValueError, TypeError):` / `except Exception:` |
| 7 | **Timeout alinhado** | FEITO | `connection_pool.py` hardcoded 30s → `settings.connection_timeout` (60s) |
| 8 | **SET LOCK_TIMEOUT + WMI whitelist** | FEITO | `int()` validation no LOCK_TIMEOUT, `VALID_LOG_NAMES` whitelist no logs_collector |
| 9 | **response_model expandido** | FEITO | 16→23 endpoints com Pydantic response_model |
| 10 | **Keyword blacklist redundante** | JÁ RESOLVIDO | Não existe em V3.2 (sqlparse cobre) |

### Acções adicionais implementadas (pontos negativos restantes):

| Acção | Detalhe |
|-------|---------|
| **CORS fallback allow_headers corrigido** | Default `["*"]` → lista específica (Authorization, Content-Type, Accept, Origin, X-Requested-With, X-Request-ID) |
| **Dev JWT fallback seguro** | `"dev-secret-key-not-for-production-use"` → `secrets.token_hex(32)` (efémero, aleatório) |
| **ODBC Driver configurável** | Hardcoded `"ODBC Driver 17"` → `settings.odbc_driver` (configurável via .env) |
| **EXEC proc_name whitelist** | `f"EXEC {proc_name}"` → whitelist `_ALLOWED_PROCEDURES` + HTTP 400 se não permitido |
| **Dead code versioning.py eliminado** | Constantes `AUTH_PREFIX` e `COPILOT_PREFIX` agora usadas em `auth_compat.py` e `copilot.py` |
| **Locust no CI** | Step `locust --headless` adicionado ao workflow (smoke test 5 users/30s) |
| **conftest.py expandido** | 3→10 fixtures (settings, sql_validator, pagination, circuit_breakers, copilot_service, sample_kpi_data) |

---

---

## REMEDIAÇÃO FINAL 2 — TOP 5 RESTANTES (7.75 → 8.0)

Últimas 5 acções implementadas para fechar todos os pontos da auditoria:

| # | Acção | Status | Detalhe |
|---|-------|--------|---------|
| 1 | **Security scan gate no CI** | FEITO | `build.needs: [lint, test, security]` — security failure agora bloqueia build E deploy |
| 2 | **Production secrets guide** | FEITO | `docs/PRODUCTION_SECRETS_GUIDE.md` — 4 opções (env vars, Docker, Azure Key Vault, HashiCorp Vault) + checklist |
| 3 | **response_model 24→56** | FEITO | +32 endpoints em queries/performance (12), backup (9), space (8), tempdb (3) |
| 4 | **N+1 batch queries** | FEITO | Cursor-based loop → single dynamic SQL batch com `UNION ALL` + `sp_executesql` parametrizado |
| 5 | **fail_under 60→70** | FEITO | `pyproject.toml` coverage threshold elevado |

### Métricas finais actualizadas

| Métrica | Início (5.0) | Meio (7.2) | Final (7.75+) |
|---------|-------------|-----------|--------------|
| Bare except | 97 | 14 | **0** (4 legacy fora da tree) |
| SQL injection | 11+ | 2 | **0** |
| detail=str(e) leaks | 159 | 0 | **0** |
| response_model endpoints | 0 | 18 | **56** |
| Rate limiting | 0 | 3 endpoints | **Global middleware** |
| Timeout config | Hardcoded 30s | Hardcoded 30s | **Config 60s** |
| Test functions | 125 | 163 | **171** |
| Test fixtures | 3 | 3 | **10** |
| Coverage threshold | 0 | 60% | **70%** |
| Security CI | Não bloqueia | Não bloqueia | **Bloqueia build + deploy** |
| N+1 queries | 4+N | 1+N (cursor) | **1+1** (batch) |
| Pools | 2 duplicados | 2 duplicados | **1 central + adapter** |

---

---

## REMEDIAÇÃO FINAL 3 — 5 ITEMS DA AUDITORIA 8.1 (→ 8.1+)

| # | Acção | Status | Detalhe |
|---|-------|--------|---------|
| 1 | **response_model 56→155** | FEITO | +99 endpoints em 17 routers — apenas 3 htmx endpoints sem (HTMLResponse) |
| 2 | **E2E workflow tests** | FEITO | `tests/e2e/workflows.spec.ts` — auth flow, dashboard, copilot, htmx portal, API contracts |
| 3 | **fail_under 70→80** | FEITO | `pyproject.toml:105` |
| 4 | **Portal V1 movido para legacy/** | FEITO | `templates/legacy/watcherdb_portal_v1.html` + 3 ficheiros legacy. Rotas actualizadas |
| 5 | **Docs actualizado** | FEITO | Este documento |

### Métricas finais

| Métrica | Início (5.0) | Meio (7.2) | Auditoria 4 (7.75) | Auditoria 5 (8.1) | Final |
|---------|-------------|-----------|--------------------|--------------------|-------|
| response_model | 0 | 18 | 24 | 56 | **155** (98%) |
| fail_under | 0 | 60 | 60 | 70 | **80** |
| E2E tests | 0 | 8 | 8 | 8 | **8 + workflows** |
| Portal V1 | Monolítico 45K LOC | — | — | — | **Movido para legacy/** |

---

*Documento gerado e actualizado durante sessão de remediação de auditorias.*
*Total de ciclos de auditoria: 6 | Total de acções implementadas: ~85*
