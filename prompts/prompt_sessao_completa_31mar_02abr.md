# Prompt Completo — Sessao WatcherDB V3.2 (31/03 – 02/04/2026)

## Resumo Executivo
Sessao de 2 dias onde o WatcherDB V3.2 foi transformado de um projecto com nota 5.0/10 para 8.1/10 atraves de 6 ciclos de auditoria tecnica, implementacao de ~85 accoes de remediacao, migracao do frontend para htmx + Web Components, replicacao das features do Control Panel V5, integracao AD multi-dominio com Kerberos/GSSAPI, faxina do projecto, suite QA com 15 niveis/360 testes, e preparacao do pacote de deploy com proteccao PyArmor.

---

## 1. AUDITORIA TECNICA — 6 Ciclos (5.0 → 8.1)

### Scorecard Final
| Dimensao | Antes | Depois |
|----------|:-----:|:------:|
| Arquitectura Backend | 5.5 | 8.0 |
| Seguranca | 4.0 | 8.0 |
| Data Layer | 6.0 | 8.0 |
| DevOps/CI/CD | 7.0 | 8.5 |
| Frontend | 5.5 | 7.5 |
| Bibliotecas | 5.0 | 8.5 |
| **Media** | **5.0** | **8.1** |

### Accoes de Seguranca (23)
- SQL injection corrigido: 11+ → 0 (parametrizacao + sqlparse AST)
- CORS wildcard eliminado → config-based whitelist
- CSP nonce-based (sem unsafe-inline/unsafe-eval)
- JWT em HttpOnly cookies (secure, samesite=lax)
- Token blacklist DB-persisted (SHA-256 + LRU cache)
- WebSocket autenticado (token validation)
- Rate limiting global (slowapi middleware)
- DOMPurify + safeHTML() em todos os innerHTML
- Password validation forte (8+ chars, maiuscula, minuscula, numero, simbolo)
- SMTP password rodada, Oracle credenciais eliminadas
- detail=str(e) eliminado → safe_http_error() com UUID
- 97 bare except → 0 (especificos: pyodbc.Error, ValueError, Exception)

### Accoes de Arquitectura (19)
- watcherdb_main.py decomposto: 8229 → 6104 LOC (-26%)
- 26 modulos em watcherdb/core/ (cache, cors, settings, breaker, retry, etc.)
- sql_queries.py decomposto: 3901 → 441 LOC + 7 sub-modulos
- Circuit breakers (pybreaker): sql_server 5/30s, intelligence 10/15s
- Retry com tenacity (3x, exp backoff 1-10s)
- WebSocket heartbeat (30s ping)
- Request timeout (60s asyncio.wait_for)
- Paginacao reutilizavel (PaginationParams + Depends())
- Executor registry com shutdown coordenado
- API deprecation middleware (Sunset headers)
- 167 response_model Pydantic (98% cobertura)
- pydantic-settings central (WatcherDBSettings)
- APScheduler para tarefas periodicas
- Startup non-blocking (background prewarm)

### Accoes de Data Layer (6)
- Alembic migrations (3: baseline, token_blacklist, system_config)
- N+1 queries optimizado (4+N → 2 com batch UNION ALL)
- Pools consolidados (monitoring.py adapter → connection_pool.py)
- TTLCache (cachetools) em intelligence_kpis
- Health scores reais (sem random.uniform)
- Forecast com R², cross-validation, MAE

### Accoes de DevOps (7)
- structlog JSON + Prometheus /metrics + OpenTelemetry tracing
- CD pipeline real (Docker → ghcr.io)
- Security gate no CI (bloqueia build + deploy)
- fail_under = 80 coverage
- Locust smoke test no CI
- 360 testes (15 niveis QA)
- Playwright E2E (health + workflows)

---

## 2. FRONTEND — htmx + Web Components

- base.html com Jinja2 template inheritance
- Design system CSS extraido (1783 LOC)
- htmx 2.0.4 integrado (3 endpoints server-driven)
- 4 Web Components Shadow DOM (modal, data-table, server-card, kpi-card)
- 21 partials Jinja2 (7 UI + 14 tabs)
- Portal V2 (/watcherdb/v2) coexiste com V1
- Portal V1 movido para templates/legacy/
- Hard refresh (Ctrl+Shift+R) abre nos KPIs

---

## 3. CONTROL PANEL — Features V5

### Gestao de Utilizadores
- Botoes: Editar (fa-pen), Reset Senha (fa-key), Delete (fa-trash), Toggle
- Modal editar user (nome, email, role) com badge AD
- Password forte obrigatoria (8+ chars, maiuscula, minuscula, numero, simbolo)
- Gerador de senha (fa-magic, 12 chars)
- Tipo auth Local/AD no criar user (toggle + dropdown dominio)

### Active Directory Multi-Dominio
- Lista de cards por dominio (add/remove)
- DNS SRV discovery automatico (nslookup _ldap._tcp.domain)
- Auto-preenchimento: dominio → server LDAP + base DN
- LDAP lookup com Kerberos/GSSAPI (prioridade: service account → kerberos → anonymous)
- Pesquisa flexivel wildcard (sAMAccountName + cn + displayName)
- Multiplos resultados → prompt de seleccao
- Auto-preenchimento nome/email via LDAP (proxyAddresses, UPN, mail)
- Bind fields (service account) com password mascarada
- Botao "Testar Conexao" com diagnostico detalhado

### Politica de Sessoes
- JWT expiracao, max tentativas, lockout editaveis (dropdowns)
- Persistencia em BD (WatcherDB_System_Config via MERGE upsert)
- Auto-load no startup, sem restart necessario

### Resource Monitor
- Nova tab com 6 stat cards (CPU, RAM processo/servidor, disco, uptime, threads)
- Detalhes: PID, open files, connections, hostname, OS, Python version
- Auto-refresh 10s (para ao sair da tab)

### Outros
- Dark/light mode (Unicode ☾/☀ + localStorage)
- Tooltips (?) em todos os campos de configuracao
- Heartbeat 60s no portal → sessoes activas no control
- Dropdown dominio AD pre-populado no criar user

---

## 4. ORACLE — Removido Completamente
- 28 ficheiros eliminados (router, service, configs, scripts, docs)
- Credenciais Oracle removidas do .env
- Router registration removido de main e intelligence
- Zero referencias Oracle no codigo activo

---

## 5. FAXINA DO PROJECTO
- ~97 ficheiros eliminados (scripts one-off, temp, .exe, .bak)
- test_*.py movidos para tests/integration/
- filegroup scripts movidos para scripts/ (analytics reapontado)
- docs/ organizado em 11 subpastas (131 ficheiros)
- Raiz limpa (so watcherdb_main.py + watcherdb_intelligence.py)
- Syntax error corrigido (test_os_memory_scenarios.py)
- Warning \M corrigido (memory_analysis.py)

---

## 6. QA SUITE — 15 Niveis, 360 Testes

| Nivel | Testes | Cobertura |
|:-----:|:------:|-----------|
| 1 | 43 | Imports 26 modulos + 17 routers + Pydantic |
| 2 | 32 | SQL injection (25 payloads), error leaks, CORS, CSP |
| 3 | 16 | Circuit breaker, retry, cache, pagination |
| 4 | 6 | response_model, versioning, settings |
| 5 | 10 | Copilot (answers, ask, report) |
| 6 | 10 | Project hygiene (no .exe, .bak, .log) |
| 7 | 17 | Boundary: unicode, empty, large, TTL edges |
| 8 | 4 | Concurrency (skipped Windows) |
| 9 | 17 | Data integrity: serialization, hash |
| 10 | 8 | Config & env validation |
| 11 | 6 | Error recovery, degradation |
| 12 | 4 | Dependency isolation |
| 13 | 4 | Code quality: no print, docstrings, passwords |
| 14 | 7 | Regression: Oracle, random.uniform, detail=str(e) |
| 15 | 6 | Observability: structlog, prometheus, X-Request-ID |

---

## 7. DEPLOY — Pacote de Producao

### Proteccao de Codigo
- PyArmor Basic ($99, one-time) para encriptar Python
- Codigo 100% ilegivel no servidor do cliente
- Templates/static/config nao protegidos (nao contem logica)

### Scripts de Deploy
- `deploy/build.py` — PyArmor + empacotamento para dist/
- `deploy/install_production.ps1` — instalacao automatizada
- `deploy/setup_database.ps1` — criacao BD + scripts SQL
- `deploy/DEPLOY_GUIDE.md` — guia passo-a-passo
- `deploy/CHECKLIST_DEPLOY.md` — checklist de verificacao

### Servico Windows
- WatcherDBWebServiceV32, porta 8449
- Conta de dominio para Windows Auth
- Startup non-blocking (background prewarm)
- ResponseValidationError handler global

---

## 8. BIBLIOTECAS INTEGRADAS (14 novas)

| Biblioteca | Uso |
|-----------|-----|
| sqlparse | AST validation SQL |
| cachetools | TTLCache thread-safe |
| tenacity | Retry com backoff |
| pybreaker | Circuit breakers |
| structlog | JSON logging |
| prometheus-client | /metrics endpoint |
| opentelemetry-* | Tracing + X-Request-ID |
| slowapi | Rate limiting global |
| alembic | Database migrations |
| apscheduler | Task scheduling |
| aioodbc | Async DB driver |
| redis | Redis adapter + feature flag |
| ldap3 | AD/LDAP lookup |
| winkerberos | Kerberos/GSSAPI auth |

---

## 9. METRICAS FINAIS

| Metrica | Inicio | Final |
|---------|:------:|:-----:|
| Nota auditoria | 5.0 | **8.1** |
| watcherdb_main.py | 8229 LOC | **6104 LOC** |
| Core modules | 5 | **26** |
| SQL injection | 11+ | **0** |
| Bare except | 97 | **0** |
| detail=str(e) | 159 | **0** |
| response_model | 0 | **167** |
| Testes | 125 | **360** |
| Porta servico | 8445 | **8449** |
| Ficheiros eliminados | — | **~145** |
| Ficheiros criados | — | **~92** |

---

## 10. FICHEIROS-CHAVE

```
watcherdb_main.py                    — App principal FastAPI
watcherdb_intelligence.py            — Intelligence backend
services/auth_service.py             — Auth + AD multi-domain + config persistence
api/routers/auth_compat.py           — Endpoints auth/admin
templates/watcherdb_control.html     — Control Panel completo
templates/watcherdb_portal.html      — Portal principal
watcherdb/core/                      — 26 modulos core
deploy/build.py                      — Build com PyArmor
deploy/install_production.ps1        — Instalacao automatizada
deploy/setup_database.ps1            — Setup BD
tests/unit/test_qa_comprehensive.py  — QA niveis 1-6
tests/unit/test_qa_levels_7_15.py    — QA niveis 7-15
docs/AUDIT_REMEDIATION_V3.2_COMPLETE.md
docs/QUADRO_COMPARATIVO_ANTES_DEPOIS.md
```
