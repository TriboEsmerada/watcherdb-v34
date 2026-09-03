# V3.3 Pipeline Map (canonical)

Documento canonical das pipelines V3.3 Standard Edition: boot, request lifecycle,
auth flow, KPI collection→display flow.

**Status:** v0.1 (bootstrap Fase 4 — extraído do código actual). Specialists devem
**citar este doc** em pareceres sobre arquitectura V3.3.

**Owner:** `watcherdb-v33-specialist`
**Reviewers:** `watcherdb-deploy-architect` (boot), `watcherdb-frontend-specialist` (rendering),
`watcherdb-security-auditor` (auth), `watcherdb-v1-intel-specialist` (KPI upstream)

---

## 1. Boot pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│                    Windows Service Manager                        │
│  WatcherDBWebServiceV33 (Log on as: <AD svc account>)             │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  services/web_service/service.py — pywin32 service wrapper        │
│  - SvcDoRun()                                                     │
│  - cwd != project root (Windows Service quirk)                    │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  watcherdb_main.py — entry point                                  │
│                                                                    │
│  1. load_dotenv(path=<project>/.env) — explicit path (a215e10)    │
│  2. Imports modules/monitoring/*, api/routers/*                    │
│  3. app = FastAPI(...)  [linha 218]                                │
│  4. app.include_router(<25+ routers>) [linhas 299-440+]            │
│  5. uvicorn.run(host="0.0.0.0", port=8433, workers=1)              │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
                    [SERVICE READY @ :8433]
```

**Key files:**

- `services/web_service/service.py` — Windows service shell
- `services/web_service/install.py` — install/start/stop logic
- `services/web_service/config.yaml` — porta + AD config + JWT secret env var ref
- `watcherdb_main.py` — FastAPI app + router registration (~25 routers)
- `.env` — secrets (JWT, encryption key DPAPI, SQL pwd se Windows auth não usado)

**Critical gotcha:** sem `load_dotenv(path=<absolute>)`, JWT cai em chave efémera
(tokens não sobrevivem restart). Ver commit `a215e10`.

## 2. Request lifecycle

```
                   ┌──────────────────────┐
                   │  Browser DBA cliente  │
                   │  http://srv:8433/...  │
                   └──────────┬───────────┘
                              │ HTTP/HTTPS (cliente preference)
                              ▼
       ┌─────────────────────────────────────────────────────┐
       │  Uvicorn worker (1 worker em Windows Service mode)  │
       └─────────────────────────────┬───────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                  │
                    ▼                                  ▼
          ┌──────────────────────┐          ┌──────────────────────┐
          │  CORS middleware     │          │  Static / templates  │
          │  (config.yaml)       │          │  Jinja2              │
          └──────────┬───────────┘          └──────────┬───────────┘
                     │                                  │
                     ▼                                  ▼
       ┌─────────────────────────────────────────────────────┐
       │  Router dispatch (api/routers/*)                     │
       │  - auth_compat.py (auth + RBAC `_require_admin`)     │
       │  - intelligence_kpis.py (/api/v1/intelligence/*)     │
       │  - kpis_metadata.py (/api/v1/kpis/*)                 │
       │  - overview_dashboard.py (/api/v1/overview/summary)  │
       │  - performance.py (/api/v1/performance/*)            │
       │  - users.py, jobs.py, alwayson.py, ...               │
       └─────────────────────────────┬───────────────────────┘
                                     │
                  ┌──────────────────┼─────────────────┐
                  │                  │                  │
                  ▼                  ▼                  ▼
        ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
        │ async_db.py    │  │ connection_    │  │ pyodbc direct  │
        │ (anyio)        │  │ pool.py        │  │ (raros casos)  │
        │                │  │ (cp1252)       │  │                │
        └────────┬───────┘  └────────┬───────┘  └────────┬───────┘
                 │                    │                    │
                 └────────────────────┴────────────────────┘
                                     │
                                     ▼
                ┌─────────────────────────────────────┐
                │  SQL Server cliente                 │
                │  - WatcherDB_Intelligence (shared)  │
                │  - Servidores monitorizados          │
                └─────────────────────────────────────┘
```

**Async pattern:** `async_execute_on_intelligence` / `async_execute_on_server`
em `api/async_db.py` usam anyio para wrap pyodbc (que é sync por natureza).
Pool de conexões em `api/connection_pool.py` com `setdecoding(cp1252)` para
DMVs com collation Latin1.

## 3. Auth flow (com Patch D multi-domain)

```
                  ┌─────────────────────────────┐
                  │  POST /api/v1/auth/login    │
                  │  body: { username, password}│
                  └──────────────┬──────────────┘
                                 │
                                 ▼
            ┌────────────────────────────────────────┐
            │  api/routers/auth_compat.py            │
            │  authenticate(username, password)      │
            └────────────────────┬───────────────────┘
                                 │
                                 ▼
            ┌────────────────────────────────────────┐
            │  Username com domínio explícito?       │
            │  (user@dom.fqdn ou DOM\user)           │
            └─────┬──────────────────────────────┬───┘
                  │ YES                          │ NO
                  ▼                              ▼
        ┌──────────────────────┐    ┌──────────────────────────┐
        │ Filtra AD_DOMAINS    │    │ Tenta TODOS AD_DOMAINS    │
        │ apenas para esse dom │    │ em ordem (Patch D)        │
        └──────────┬───────────┘    └──────────────┬───────────┘
                   │                                │
                   └─────────────┬──────────────────┘
                                 ▼
            ┌────────────────────────────────────────┐
            │  Para cada domínio:                    │
            │  _try_single_domain_bind(              │
            │    username, password,                 │
            │    dom_cfg={domain, server, base_dn}, │
            │    timeout=5s (multi) ou 10s (single)) │
            │                                         │
            │  - LDAPS bind (porta 636 default)      │
            │  - SIMPLE → NTLM fallback              │
            │  - URI sanitization (Patch A)          │
            └────────────────────┬───────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │                                  │
              SUCCESS                            FAIL
                │                                  │
                ▼                                  ▼
    ┌──────────────────────┐          ┌────────────────────────┐
    │ user_info += {       │          │ Tenta próximo domínio  │
    │   ad_domain: <fqdn>  │          │ ou fallback local DB   │
    │ }                    │          │ (hybrid auth)          │
    │                      │          └────────────────────────┘
    │ create_user (silent  │
    │ fail fixed em        │
    │ Patch B 7c95c53)     │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ JWT issued (HS256)   │
    │ exp=8h, refresh=7d   │
    │ secret: env var      │
    │ WATCHERDB_JWT_SECRET │
    └──────────────────────┘
```

**RBAC gate:** decorator `_require_admin` em `api/routers/auth_compat.py:209`. Usado em
18+ endpoints (linhas 340, 348, 394, 417, 445, 459, 472, 572, 597, 637, 663, 674,
685, 698, 710, 729, 762).

**Compliance:** LDAPS é default (porta 636); LDAP (389) requer flag explícita
`use_ssl: false` na config (red flag em audit banking). Multi-domain audit log
inclui `ad_domain` no user_info (rastreabilidade).

## 4. KPI collection → display flow

```
   ┌────────────────────────────────────────────┐
   │  V1 Intelligence Collector                 │
   │  (Windows Task Scheduler)                  │
   │  task: WatcherDB_Intelligence_Collector    │
   │  cadence: ~5 min                           │
   └─────────────────────┬──────────────────────┘
                         │
                         ▼ (cada 5min, por server)
   ┌────────────────────────────────────────────┐
   │  Collector pacote watcherdb_intelligence/   │
   │  - SQL queries DMV-based                   │
   │  - retry com TCP timeout 15s (d2fdd13)     │
   │  - Auto-resolve offline events (da8aeae)   │
   └─────────────────────┬──────────────────────┘
                         │
                         ▼ INSERT
   ┌────────────────────────────────────────────┐
   │  KPI_MSSQL_*_STG (BLUE/GREEN inactive)     │
   │  13 tabelas com pares                      │
   │  Collector escreve no INACTIVE             │
   └─────────────────────┬──────────────────────┘
                         │
                         ▼ EXEC
   ┌────────────────────────────────────────────┐
   │  usp_swap_kpi_stg_tables (WITH UPDLOCK)    │
   │  - Atomic swap                             │
   │  - Update KPI_STG_ACTIVE_TABLE             │
   │    (meta-table apontando ao slot activo)   │
   └─────────────────────┬──────────────────────┘
                         │
                         ▼
   ┌────────────────────────────────────────────┐
   │  Views canonical                           │
   │  KPI_MSSQL_*_AGG (agregada)                │
   │  KPI_MSSQL_*_DET (detalhada)               │
   │  Seguem KPI_STG_ACTIVE_TABLE               │
   └─────────────────────┬──────────────────────┘
                         │
                         ▼ SELECT (V3.3 leitura)
   ┌────────────────────────────────────────────┐
   │  api/routers/intelligence_kpis.py          │
   │  api/routers/intelligence/helpers.py       │
   │  - collect_* helpers                       │
   │  - Fallback AGG → DET (se AGG vazia)       │
   │  - Reconcile via INST_AVAILABILITY         │
   │    quando COLLECTION_SERVER_DETAILS vazia  │
   │    (commits 9e967c6, 33c2fed)              │
   └─────────────────────┬──────────────────────┘
                         │
                         ▼ JSON response
   ┌────────────────────────────────────────────┐
   │  SPA templates/watcherdb_portal.html       │
   │  - fetch /api/v1/intelligence/kpis         │
   │  - Render Chart.js cards                   │
   │  - 20+ cards refresh ~5min cadence         │
   │  - Modal click handler normaliza           │
   │    instance-name (49a21c0)                 │
   └────────────────────────────────────────────┘
```

**Critical contracts:**

1. **V3.3 NUNCA escreve em `KPI_MSSQL_*_STG`** — apenas V1 collector escreve.
2. **V3.3 lê via VIEWS** que seguem `KPI_STG_ACTIVE_TABLE` — nunca tabelas BLUE/GREEN directamente.
3. **DDL changes em tabelas/SPs partilhadas exigem coordenação com `v1-intel-specialist` (veto power).**

## 5. Performance Module (Std-only, shared com Pro)

```
   /api/v1/performance/<endpoint>
            │
            ▼
   modules/performance/base.py
   - InvestigationResult, InvestigationStep
   - _json_safe (varbinary → str)
            │
            ▼
   modules/performance/investigators/
   ├── deadlocks.py         # XE shred + step_6_source pre-flight
   ├── blocking.py          # session blocking chain
   ├── io.py                # IO latency analysis
   ├── cpu.py
   ├── memory.py
   ├── tlog.py
   ├── filegroup.py
   └── problematic_sessions.py  # ÚLTIMO no registry order
            │
            ▼
   modules/performance/engines/
   ├── correlator.py        # cross-investigator correlation
   ├── baseline.py
   ├── runbook.py           # runbook output
   └── ticket_generator.py  # ticket draft simples (Std)
            │
            ▼
   modules/performance/runbooks/
   └── 8 markdown ready-to-use
```

## 6. Threat surface (resumido)

Para análise completa, ver `~/.nestor-library/watcherdb-family/offensive_security/`
+ `watcherdb-security-auditor` charter.

| Surface | Vector | Mitigation |
|---|---|---|
| Auth | LDAP MITM | LDAPS default (porta 636) |
| Auth | JWT replay | 8h expiry + refresh 7d |
| Service account | compromise | Rotação semestral (180d) — runbook em KB local |
| SQL injection | DMV queries | Parameterized queries (pyodbc) |
| Audit log | repudiation | All admin actions logged + `ad_domain` (Patch D) |
| Secrets | plaintext .env | DPAPI / Fernet+DPAPI hybrid em produção |
| License | bypass | Ed25519 signature + hardware fingerprint (`0f76a01`) |

## 7. References

- **Boot:** `services/web_service/service.py`, `install.py`, `config.yaml`, `watcherdb_main.py`
- **Auth:** `api/routers/auth_compat.py` (linhas 209, 340-410)
- **KPI flow:** `api/routers/intelligence_kpis.py`, `api/routers/intelligence/helpers.py`,
  `api/async_db.py`, `api/connection_pool.py`
- **Performance:** `modules/performance/`
- **V1 collector:** `c:/Users/ue_e-snetto/Documents/projetosPython/WATCHERDB INTELLIGENCE V1/`
- **KB local:** `knowledge_base/domain/seed/kpi_catalog_v33.md`,
  `knowledge_base/operations/seed/deploy_runbook_v33.md`,
  `knowledge_base/operations/seed/ad_service_account_rotation.md`
- **KB central:** `~/.nestor-library/watcherdb-family/pipeline_maps/` (canon cross-tier — gap conhecido, ingerir via core-librarian)
- **Recent commits relevantes:** `691a529` (Patch D), `7c95c53` (Patch A/B/C), `49a21c0` (modal),
  `9e967c6`, `33c2fed`, `7a9355a` (KPI reconcile), `a215e10` (load_dotenv), `0f76a01` (HW fingerprint)

## 8. Próxima iteração

- [ ] Adicionar diagrama de WebSocket flow (live monitoring)
- [ ] Adicionar diagrama de Performance investigators interaction
- [ ] Cross-link ADRs (porta 8433, dual-library, council composition)
- [ ] Promover este doc para `~/.nestor-library/watcherdb-family/pipeline_maps/V3.3_PIPELINE_MAP.md`
  (via `core-librarian` 5 gates) — actualmente esse path está vazio (gap detectado em smoke test #2)
