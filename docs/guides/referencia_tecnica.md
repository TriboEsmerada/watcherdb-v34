# WatcherDB V3.3 Standard Edition -- Documentacao Tecnica de Referencia

**Versao:** 3.3 (Standard Edition)
**Data:** 2026-04-22 (revisto em audit S2-9)
**Stack:** Python 3.11+, FastAPI 0.114+, Uvicorn, pyodbc, SQL Server 2016+, HTML/CSS/JS vanilla
**Porta default:** 8433
**Servico Windows:** WatcherDBWebServiceV33

---

## Indice

1. [Visao Geral da Arquitectura](#1-visao-geral-da-arquitectura)
2. [Estrutura do Projecto](#2-estrutura-do-projecto)
3. [Sistema de Autenticacao](#3-sistema-de-autenticacao)
4. [Sistema de Preferencias e Sessao](#4-sistema-de-preferencias-e-sessao)
5. [API REST](#5-api-rest)
6. [Modulos de Monitorizacao](#6-modulos-de-monitorizacao)
7. [Base de Dados](#7-base-de-dados)
8. [Frontend](#8-frontend)
9. [Deploy e Operacao](#9-deploy-e-operacao)
10. [Seguranca](#10-seguranca)
11. [Limitacoes Conhecidas e Divida Tecnica](#11-limitacoes-conhecidas-e-divida-tecnica)

---

## 1. Visao Geral da Arquitectura

### 1.1 Diagrama de Arquitectura

```
                                 +---------------------+
                                 |   Browser (SPA)     |
                                 | watcherdb_portal.html|
                                 | (45k linhas, vanilla)|
                                 +----------+----------+
                                            |
                                  HTTP/WS :8445
                                            |
                          +-----------------v------------------+
                          |     Windows Service (Uvicorn)      |
                          |  WatcherDBWebServiceV31            |
                          |  services/web_service/service.py   |
                          +-----------------+------------------+
                                            |
                          +-----------------v------------------+
                          |         FastAPI Application        |
                          |        watcherdb_main.py           |
                          |           (8229 linhas)            |
                          +--+------+------+------+------+----+
                             |      |      |      |      |
               +-------------+  +---+--+ +-+--+ ++---+ +-+--------+
               | api/routers/|  |services| |modules|  |watcherdb/ |
               | 18 routers  |  |  auth  | | monit.| |  package   |
               +------+------+  +---+---+ +--+---+ +-----+------+
                      |             |         |           |
          +-----------+-----------+ |    +----+----+      |
          |                       | |    |         |      |
   +------v------+  +------v-----+-v----v-+  +----v-----+v-------+
   |  SQL Server  |  | WatcherDB_Intel.   |  | Oracle DB         |
   | Monitorados  |  | (Auth, Prefs, KPIs)|  | (KPIs via oracledb)|
   | (~96 instanc.)|  | SQLHDSTST505\I01  |  | oradb_pcitpr.tap.pt|
   +--------------+  +-------------------+  +-------------------+

   Pool: SQLServerConnectionPool    Pool: IntelligenceConnectionPool
   (api/connection_pool.py)         (api/connection_pool.py)
```

### 1.2 Stack Tecnologico

| Camada | Tecnologia | Porquee |
|--------|-----------|---------|
| Web Framework | FastAPI + Uvicorn | Async, auto-docs OpenAPI, performance |
| Frontend | HTML/CSS/JS vanilla (single-file) | Zero dependencias CDN, deploy simples em Windows |
| DB Monitorizados | SQL Server (pyodbc, ODBC Driver 17) | Inventario TAP: ~96 instancias |
| DB Metadados | SQL Server `WatcherDB_Intelligence` | Users, Auth Log, Preferences, KPIs agregados |
| DB KPIs Legacy | Oracle (oracledb, opcional) | Dados historicos migrados de Oracle |
| Auth | JWT (python-jose) + bcrypt (passlib) + LDAP3 | Hibrido: AD + local DB |
| Encriptacao | Fernet (cryptography) | Passwords em servers.json, preferencias de user |
| Cache | RedisLikeCache (in-process, pickle) | Sem dependencia de Redis externo |
| Deploy | Windows Service (pywin32) | Ambiente corporativo Windows Server |

### 1.3 Padroes de Design

- **Singleton** com double-checked locking: `SQLServerConnectionPool`, `IntelligenceConnectionPool`, `AuthService`, `AlwaysOnChecker`
- **Connection Pool manual**: Implementacao propria em `api/connection_pool.py` (nao usa SQLAlchemy) -- PORQUEE: pyodbc com Windows Auth nao funciona bem com pools de terceiros
- **Router pattern**: FastAPI APIRouter com carregamento via try/except (graceful degradation)
- **Cache Redis-like in-process**: `RedisLikeCache` em `watcherdb_main.py` com TTL, LRU eviction, persistencia pickle
- **Lifespan pattern**: FastAPI `@asynccontextmanager` para startup/shutdown
- **Monolithic frontend**: Single HTML file de 45k linhas -- PORQUEE: deploy simplificado em Windows, sem build step

### 1.4 Trade-offs Chave

| Decisao | Alternativa rejeitada | Justificacao |
|---------|----------------------|-------------|
| Single-file HTML (45k linhas) | SPA framework (React/Vue) | Zero build tools, deploy xcopy, funciona offline |
| Pool de conexoes manual | SQLAlchemy, aioodbc | Windows Auth + pyodbc: pools de terceiros falham com Trusted_Connection |
| RedisLikeCache in-process | Redis externo | Zero infra adicional, suficiente para ~5 users concorrentes |
| READ UNCOMMITTED global | READ COMMITTED | Queries de monitorizacao sao read-only; evita locks nos servidores monitorados |
| Ficheiro .env com credenciais | Azure Key Vault | Ambiente on-prem sem cloud |
| MERGE com HOLDLOCK (prefs) | INSERT/UPDATE separados | Atomicidade garantida contra race conditions em saves concorrentes |

---

## 2. Estrutura do Projecto

### 2.1 Arvore de Directorios (ficheiros principais)

```
WATCHERDB_V3.1/
+-- watcherdb_main.py            # Ponto de entrada (8229 linhas): FastAPI app, lifespan, rotas inline
+-- .env                          # Credenciais (NAO versionar!)
+-- .env.example                  # Template de credenciais
+-- requirements.txt              # Dependencias core
+-- api/
|   +-- connection_pool.py        # Pools de conexoes SQL Server (Singleton)
|   +-- routers/
|       +-- auth_compat.py        # Auth V3.1: login, JWT, prefs, audit (router principal)
|       +-- alwayson.py           # Always On Availability Groups
|       +-- jobs.py               # SQL Agent Jobs monitoring
|       +-- sqlserver_kpis.py     # KPIs via queries directas ao SQL Server
|       +-- intelligence_kpis.py  # KPIs via views pre-calculadas no Intelligence DB
|       +-- oracle_kpis.py        # KPIs via Oracle DB (opcional)
|       +-- overview_dashboard.py # Overview Dashboard (dados pre-calculados)
|       +-- users.py              # Users security analysis (SQL Server users)
|       +-- sql_queries.py        # SQL Troubleshooting queries
|       +-- service_status.py     # Windows Services monitoring
|       +-- os_performance.py     # OS Memory/CPU/Disk via WMI
|       +-- cluster.py            # Windows Failover Cluster
|       +-- disk_unallocated.py   # Disk unallocated space
|       +-- database_discovery.py # Auto-descoberta de databases
|       +-- network_diagnostics.py# Diagnostico de rede multi-layer
|       +-- kpis_metadata.py      # Metadados e modos de coleta KPI
|       +-- diagnostics_overview.py# Overview diagnosticos (AO + queries)
+-- services/
|   +-- auth_service.py           # AuthService: JWT, bcrypt, LDAP, lockout
|   +-- sqlserver_kpi_service.py  # SQLServerKPIService (12 KPIs paralelos)
|   +-- os_performance_service.py # OS metrics via WMI
|   +-- disk_unallocated_service.py
|   +-- database_discovery_service.py
|   +-- web_service/
|       +-- service.py            # Windows Service wrapper (WatcherDBWebServiceV31)
|       +-- server.py             # FastAPI bootstrap com middlewares de seguranca
|       +-- install.py            # Instalacao do Windows Service
|       +-- auth/                 # Auth V1 (legacy, fallback)
|       +-- security/
|           +-- audit.py          # AuditMiddleware
|           +-- cors.py
|           +-- headers.py
|           +-- rate_limiter.py
+-- modules/
|   +-- monitoring/
|       +-- monitoring.py         # SQLServerMonitoring, ConnectionPool, SQLServerExecutor
|       +-- queries.py            # SQLQueries: biblioteca de queries SQL Server
|       +-- backup_analysis.py    # BackupAnalysisEngine
|       +-- backup_pattern_analysis.py # BackupPatternAnalyzer
|       +-- memory_analysis.py    # Analise de memoria SQL + OS
|       +-- cpu_analysis.py       # Analise de CPU
|       +-- space_analysis.py     # SpaceAnalysisEngine
|       +-- security_analysis.py  # SecurityAnalysisEngine
|       +-- watcherdb_alwayson_check.py # AlwaysOnChecker (singleton)
|       +-- cluster_analysis.py   # Windows Failover Cluster via PowerShell
|       +-- service_monitor.py    # SQL Server services via WMI/SC
|       +-- dashboard_api.py      # Dashboard API router
|       +-- logs_collector.py     # Windows Event Log + SQL Error Log
|       +-- notifications.py      # Email/Teams/Slack notifications
+-- watcherdb/                    # Package refactorado (routers adicionais)
|   +-- api/routers/
|       +-- security.py           # Security Analysis router
|       +-- windows.py            # Windows Metrics router
|       +-- alerts_unified.py     # Unified Alerts router
|       +-- admin_metrics.py      # Admin Metrics router
|       +-- backup.py             # Backup router (refactorado)
|   +-- core/
|       +-- cache.py, auth.py, endpoint_usage_tracker.py
|   +-- services/
|       +-- alerting.py, backup_service.py, notification.py, ...
|   +-- models/, utils/
+-- config/
|   +-- config.yaml               # Configuracao central (thresholds, alertas, paths)
|   +-- servers.json              # Servidores monitorados (passwords Fernet-encrypted)
|   +-- sql_servers.json          # Inventario de servidores (96 instancias)
|   +-- alwayson_inventory.json   # Inventario AlwaysOn AGs
|   +-- custom_queries.json       # Queries personalizadas
|   +-- alerts.json               # Configuracao de alertas
+-- database/
|   +-- CREATE_USER_AUTH_PREFS.sql # Schema: Users, Auth_Log, Preferences
|   +-- 07_ADD_MUST_CHANGE_PASSWORD.sql   # must_change_password (reset pelo admin) -- obrigatorio
|   +-- 12_ADD_LOCAL_PASSWORD_HASH.sql   # Dual auth (AD + fallback local) -- obrigatorio
|   +-- 13_ADD_PASSWORD_CHANGED_AT.sql   # Revogacao de sessao por reset (P4 A-4.7) -- obrigatorio
|   +-- 00_WATCHERDB_MASTER_DEPLOY.sql  # Deploy completo
|   +-- SQLSERVER_KPI_DEPLOY_COMPLETE.sql # Views e procedures KPI
|   +-- (... 20+ scripts SQL)
+-- templates/
|   +-- watcherdb_portal.html     # Frontend principal (45290 linhas)
|   +-- watcherdb_control.html    # Admin panel
|   +-- space_dashboard.html      # Dashboard de espaco
+-- static/
|   +-- css/, js/, i18n/          # Assets estaticos, i18n
```

### 2.2 Ponto de Entrada e Carregamento de Routers

**Ficheiro:** `watcherdb_main.py`

1. `load_dotenv()` carrega `.env` (linhas 17-21)
2. Imports de modulos de monitorizacao (linhas 23-37)
3. `RedisLikeCache` inicializado como classe global (linha 81)
4. `lifespan()` (linha 2332):
   - Cria `SmartTapInventoryManager` com `RedisLikeCache`
   - Carrega `sql_servers.json` e inicializa `SQLServerMonitoring`
   - Pre-carrega cache de KPIs Intelligence
   - Executa `DatabaseDiscoveryService.discover_all()`
5. `FastAPI(lifespan=lifespan)` na linha 2418
6. **21 routers** carregados via try/except (linhas 2426-2581):
   - Cada router e importado dentro de try/except para graceful degradation
   - Se um router falhar a carregar, os restantes continuam a funcionar
   - Router `auth_compat` tem fallback para `watcherdb.api.auth_router` (legacy)
7. Middleware GZip + CORS adicionados (linhas 2585-2594)
8. ~70 endpoints inline definidos directamente no `app` (linhas 2698-8229)

**Ordem de carregamento dos routers:**
```
1. alwayson        -> /api/alwayson/*
2. sql_queries     -> /api/queries/*
3. diagnostics     -> /api/diagnostics/*
4. service_status  -> /api/monitoring/services/*
5. oracle_kpis     -> /api/oracle-kpis/*
6. sqlserver_kpis  -> /api/sqlserver-kpis/*
7. intelligence_kpis -> /api/v1/kpis/*
8. os_performance  -> /api/os/*
9. users           -> /api/users/*
10. jobs           -> /api/jobs/*
11. dashboard_api  -> (modules/monitoring/dashboard_api.py)
12. kpis_metadata  -> /api/v1/kpis/*
13. overview_dashboard -> /api/v1/overview/*
14. disk_unallocated -> /api/disk-unallocated/*
15. database_discovery -> /api/discover/*
16. auth_compat    -> /api/auth/*    [PRINCIPAL]
17. security       -> (watcherdb package)
18. windows        -> (watcherdb package)
19. alerts_unified -> (watcherdb package)
20. admin_metrics  -> (watcherdb package)
21. network_diagnostics -> /api/diagnostics/*
```

---

## 3. Sistema de Autenticacao

### 3.1 Diagrama de Fluxo de Login

```
  Browser                  auth_compat.py             auth_service.py            SQL Server
    |                          |                           |                       (Intelligence)
    |  POST /api/auth/login    |                           |                          |
    |  {username, password}    |                           |                          |
    +------------------------->|                           |                          |
    |                          |  authenticate(u, p, ip)   |                          |
    |                          +-------------------------->|                          |
    |                          |                           |                          |
    |                          |       STEP 1: Try LDAP    |                          |
    |                          |       (if AD_ENABLED)     |                          |
    |                          |                           |---LDAP BIND-----------> AD
    |                          |                           |<--OK/FAIL--------------- AD
    |                          |                           |                          |
    |                          |   [IF LDAP OK]            |                          |
    |                          |   auto_provision_ad_user  |  MERGE into              |
    |                          |                           |  WatcherDB_Users ------->|
    |                          |                           |  create_access_token     |
    |                          |                           |  _log_auth("SUCCESS")-->|
    |                          |<----- {token, user} ------|                          |
    |                          |                           |                          |
    |                          |   [IF LDAP FAIL]          |                          |
    |                          |       STEP 2: Local DB    |                          |
    |                          |                           |  SELECT FROM             |
    |                          |                           |  WatcherDB_Users ------->|
    |                          |                           |<--- user row ------------|
    |                          |                           |                          |
    |                          |   [IF user NOT FOUND]     |                          |
    |                          |   dummy hash (constant-   |                          |
    |                          |   time anti-enumeration)  |                          |
    |                          |<-- 401 "Credenciais       |                          |
    |                          |       invalidas" ---------|                          |
    |                          |                           |                          |
    |                          |   [IF user FOUND]         |                          |
    |                          |   check lockout           |                          |
    |                          |   check disabled          |                          |
    |                          |   check ad_auth: prefix   |                          |
    |                          |   verify_password(bcrypt) |                          |
    |                          |                           |                          |
    |                          |   [IF password OK]        |                          |
    |                          |   create_access_token     |                          |
    |                          |   _reset_failed_attempts->|-->UPDATE Users---------->|
    |                          |   _update_last_login ---->|-->UPDATE Users---------->|
    |                          |   _log_auth("SUCCESS")--->|-->INSERT Auth_Log------->|
    |                          |<-- {token, user} ---------|                          |
    |<-- 200 {access_token,    |                           |                          |
    |         user profile}    |                           |                          |
    |                          |                           |                          |
    | localStorage.setItem     |                           |                          |
    | ('watcherdb_token', t)   |                           |                          |
    | ('watcherdb_user', u)    |                           |                          |
```

### 3.2 JWT

**Ficheiro:** `services/auth_service.py` (linhas 124-158)

- **Algoritmo:** HS256
- **Biblioteca:** python-jose (fallback: PyJWT)
- **Secret Key:** `JWT_SECRET_KEY` do `.env` (se ausente, gera chave efemera -- tokens nao sobrevivem restart)
- **Expiracao:** 1440 min (24h) por defeito, configuravel via `JWT_EXPIRE_MINUTES`
- **Payload:** `{"sub": username, "role": role, "exp": ..., "iat": ...}`
- **Localizacao no request:** Header `Authorization: Bearer <token>` ou cookie `access_token`

### 3.3 Password Hashing

**Ficheiro:** `services/auth_service.py` (linhas 99-118)

- **Esquema principal:** bcrypt via `passlib.CryptContext`
- **Suporte legacy:** hashes `sha256:` sao verificados mas nunca criados (migracao transparente)
- **PORQUEE bcrypt e nao argon2:** passlib[bcrypt] e mais estavel em Windows; argon2 requer compilador C

### 3.4 LDAP / Active Directory

**Ficheiro:** `services/auth_service.py` (linhas 162-296)

- **Biblioteca:** ldap3 (opcional: `pip install ldap3`)
- **Configuracao:** env vars `AD_ENABLED`, `AD_DOMAIN`, `AD_SERVER`, `AD_BASE_DN`, `AD_USE_SSL`
- **Auto-deteccao:** Se `AD_DOMAIN` nao definido, detecta via `USERDOMAIN` do ambiente Windows
- **Bind strategy:** Tenta UPN (user@domain.fqdn) primeiro, fallback NTLM (DOMAIN\user)
- **Auto-provisioning:** Users AD sao criados automaticamente em `WatcherDB_Users` com `password_hash = "ad_auth:<sha256>"` e `role = AD_DEFAULT_ROLE` (default: viewer)
- **Roles:** Mantidos no DB local -- admin pode promover user AD via `/api/auth/admin/users/{username}/role`

### 3.5 Account Lockout

**Ficheiro:** `services/auth_service.py` (linhas 524-543)

- **Threshold:** 5 tentativas falhadas (`MAX_FAILED_ATTEMPTS = 5`)
- **Duracao:** 15 minutos (`LOCKOUT_MINUTES = 15`)
- **Mecanismo:** `failed_attempts` incrementado via UPDATE atomico; `locked_until` set via `DATEADD(MINUTE, 15, GETDATE())`
- **Reset:** `failed_attempts = 0, locked_until = NULL` apos login bem sucedido

### 3.6 Token Blacklist

**Ficheiro:** `api/routers/auth_compat.py` (linhas 52-53)

```python
_token_blacklist = set()  # In-memory, perde-se no restart
```

- **PORQUEE in-memory:** Simplicidade; JWT tem expiracao curta (24h). Restart do servico invalida todos os tokens de qualquer forma (se JWT_SECRET_KEY e efemera).
- **Limitacao:** Nao e distribuido; nao persiste entre restarts.

### 3.7 Constant-Time User Enumeration Prevention

**Ficheiro:** `services/auth_service.py` (linhas 410-412)

```python
# User NOT FOUND: fazer hash dummy para evitar timing side-channel
verify_password(password, hash_password("dummy-constant-time"))
```

Quando o username nao existe, o servidor ainda executa um hash bcrypt dummy para que o tempo de resposta seja indistinguivel de uma password incorrecta.

### 3.8 Roles

| Role | Permissoes |
|------|-----------|
| `admin` | Tudo: CRUD users, ver auth log, sessoes, alterar roles, system config |
| `analyst` | Acesso de leitura a todos os dashboards e APIs de monitorizacao |
| `operator` | Acesso operacional (subset de analyst) |
| `viewer` | Apenas leitura basica |

Verificacao: `_require_admin()` em `auth_compat.py` verifica `role == "admin"`. Nao ha middleware global de RBAC granular -- os endpoints de monitorizacao nao verificam role. [DECISAO DE DESIGN -- VERIFICAR se e intencional que viewer tem acesso a todos os endpoints de monitorizacao]

---

## 4. Sistema de Preferencias e Sessao

### 4.1 Schema da Tabela

**Ficheiro:** `database/CREATE_USER_AUTH_PREFS.sql` (linhas 49-67)

```sql
CREATE TABLE dbo.WatcherDB_User_Preferences (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    username         NVARCHAR(100)  NOT NULL,
    preference_key   NVARCHAR(100)  NOT NULL,
    preference_value NVARCHAR(MAX)  NULL,  -- Valor ENCRIPTADO com Fernet
    updated_at       DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT UQ_UserPref_Key UNIQUE (username, preference_key)
);
-- Covering index para performance
CREATE NONCLUSTERED INDEX IX_UserPref_Username
    ON dbo.WatcherDB_User_Preferences (username)
    INCLUDE (preference_key, preference_value);
```

### 4.2 Encriptacao Fernet

**Ficheiro:** `api/routers/auth_compat.py` (linhas 88-131)

- **Chave:** `WATCHERDB_ENCRYPTION_KEY` do `.env` (Base64-encoded, 32 bytes)
- **Prefixo:** Valores encriptados sao prefixados com `enc:` no DB
- **Fallback:** Se chave nao definida, preferencias guardadas em plaintext (com warning no log)
- **Lazy singleton:** `_get_pref_cipher()` inicializa `Fernet` apenas uma vez

```
DB value: "enc:gAAAAABp..." -> decrypt -> "true"
DB value: "true"           -> retornado tal qual (nao encriptado)
```

### 4.3 MERGE com HOLDLOCK

**Ficheiro:** `api/routers/auth_compat.py` (linhas 253-266)

```sql
MERGE dbo.WatcherDB_User_Preferences WITH (HOLDLOCK) AS target
USING (SELECT ? AS username, ? AS preference_key) AS source
ON target.username = source.username AND target.preference_key = source.preference_key
WHEN MATCHED THEN
    UPDATE SET preference_value = ?, updated_at = GETDATE()
WHEN NOT MATCHED THEN
    INSERT (username, preference_key, preference_value, updated_at)
    VALUES (?, ?, ?, GETDATE());
```

**PORQUEE HOLDLOCK:** Previne race conditions quando dois saves concorrentes do mesmo user tentam inserir a mesma key simultaneamente. Sem HOLDLOCK, dois INSERT poderiam colidir na UNIQUE constraint.

### 4.4 Sync Frontend <-> Servidor

**Ficheiro:** `templates/watcherdb_portal.html` (linhas 4300-4413)

**Chaves sincronizadas (SYNCED_PREF_KEYS):**
```javascript
const SYNCED_PREF_KEYS = [
    'dashboardKPIConfig', 'sqlDiagnosticsConfig', 'kpi-dashboard-compact',
    'backup_days', 'backup_include_system', 'backup_sort', 'backup_filter',
    'backup_db_filter', 'backup_hours_filter', 'backup_gaps_days',
    'log_hours', 'log_type',
    'serverSortOrder', 'sidebarCollapsed', 'kpiRefreshInterval',
    'requestTimeout', 'enableDebugLogs',
    'watcherdb_server_search_frequency',
    'lastActiveTab', 'lastSelectedServer', 'userCustomQueries'
];
```

**Fluxo:**

```
Login OK
  |
  +-> checkAuthOnLoad()
  |     +-> GET /api/auth/validate -> OK
  |     +-> setTimeout(syncPreferencesToServer, 3000)
  |
  +-> loadPreferencesFromServer()
  |     +-> GET /api/auth/preferences
  |     +-> Para cada key em SYNCED_PREF_KEYS:
  |           localStorage.setItem("user:{username}:{key}", value)
  |     +-> Migra keys antigas (sem prefixo) para namespace user:
  |
  +-> Interceptor localStorage.setItem
        +-> Se key in SYNCED_PREF_KEYS:
        |     +-> Guarda como "user:{username}:{key}"
        |     +-> schedulePrefSync() (debounce 5s)
        +-> Senao: localStorage normal
```

### 4.5 Namespace `user:{username}:{key}`

**Ficheiro:** `templates/watcherdb_portal.html` (linhas 4040-4053)

```javascript
function userPrefKey(key) {
    const username = getCurrentUsername();
    return username ? `user:${username}:${key}` : key;
}
```

**PORQUEE:** Isolamento entre utilizadores. Sem namespace, dois users no mesmo browser partilhariam preferencias. O prefixo `user:salomao:lastActiveTab` isola do `user:ricardo:lastActiveTab`.

### 4.6 Migracao de Chaves Antigas

**Ficheiro:** `templates/watcherdb_portal.html` (linhas 4330-4337)

Na funcao `loadPreferencesFromServer()`, antes de restaurar preferencias do servidor, chaves antigas sem prefixo sao removidas:

```javascript
for (const key of SYNCED_PREF_KEYS) {
    const oldVal = _origGetItem(key);  // Sem prefixo
    if (oldVal !== null) {
        _origRemoveItem(key);
        console.log(`[PREFS] Migrada chave antiga: ${key}`);
    }
}
```

---

## 5. API REST

### 5.1 Authentication (`auth_compat.py` -- `/api/auth`)

| Metodo | URL | Auth | Descricao | Request | Response |
|--------|-----|------|-----------|---------|----------|
| POST | `/api/auth/login` | Nao | Login | `{username, password}` | `{success, access_token, token_type, expires_in, user}` |
| GET | `/api/auth/validate` | Bearer | Validar token | -- | `{valid, user}` |
| GET | `/api/auth/me` | Bearer | Info do user actual | -- | `{username, role, full_name, email}` |
| POST | `/api/auth/logout` | Bearer | Logout (blacklist token) | -- | `{success, message}` |
| GET | `/api/auth/users` | Admin | Listar users | -- | `{success, users[]}` |
| POST | `/api/auth/users` | Admin | Criar user | `{username, password, role?, email?, full_name?}` | `{success, username, role}` |
| POST | `/api/auth/change-password` | Bearer | Alterar password | `{current_password, new_password}` | `{success}` |
| POST | `/api/auth/users/{username}/toggle` | Admin | Activar/desactivar | `{disabled: bool}` | `{success}` |
| POST | `/api/auth/admin/users/{username}/role` | Admin | Alterar role | `{role}` | `{success, username, role}` |
| GET | `/api/auth/preferences` | Bearer | Obter preferencias | -- | `{success, preferences: {key: value}}` |
| PUT | `/api/auth/preferences` | Bearer | Guardar preferencias | `{preferences: {key: value}}` | `{success, saved, errors}` |
| DELETE | `/api/auth/preferences/{key}` | Bearer | Apagar preferencia | -- | `{success, deleted}` |
| GET | `/api/auth/admin/auth-log` | Admin | Audit log | `?limit=100&username=` | `{success, logs[], count}` |
| GET | `/api/auth/admin/sessions` | Admin | Sessoes activas | -- | `{success, sessions[], count}` |
| GET | `/api/auth/admin/online` | Admin | Users online (heartbeat) | -- | `{success, online[], count}` |
| POST | `/api/auth/heartbeat` | Bearer | Heartbeat (presenca) | -- | `{success}` |
| GET | `/api/auth/admin/system-config` | Admin | Config do sistema | -- | `{success, config}` |

**Erros comuns:**
- `401`: Token nao fornecido, invalido, expirado ou revogado
- `403`: Acesso restrito a administradores
- `400`: Username ja existe, role invalido, password actual incorrecta

### 5.2 Always On (`alwayson.py` -- `/api/alwayson`)

| Metodo | URL | Params | Descricao |
|--------|-----|--------|-----------|
| GET | `/api/alwayson/overview` | `?lazy=true` | Overview de todos os AGs. `lazy=true` (default): leitura do JSON. `lazy=false`: conecta a todos os servidores |
| GET | `/api/alwayson/ag/{ag_name}` | -- | Detalhes de um AG: status, eventos failover (30 dias), padroes |
| GET | `/api/alwayson/server/{server}/status` | `?instance=` | Status AO de um servidor |
| GET | `/api/alwayson/server/{server}/databases` | `?instance=` | Databases em AG |
| GET | `/api/alwayson/server/{server}/events` | `?instance=&days=30` | Eventos de failover |

### 5.3 Jobs (`jobs.py` -- `/api/jobs`)

| Metodo | URL | Descricao |
|--------|-----|-----------|
| GET | `/api/jobs/server/{server_id}` | Lista de jobs com status |
| GET | `/api/jobs/server/{server_id}/failed` | Jobs falhados (ultimas 24h) |
| GET | `/api/jobs/server/{server_id}/history/{job_name}` | Historico de execucoes |
| GET | `/api/jobs/server/{server_id}/maintenance-coverage` | Cobertura de manutencao por DB |
| GET | `/api/jobs/server/{server_id}/trends` | Tendencias: duracao e taxa de falha |
| GET | `/api/jobs/server/{server_id}/schedule-conflicts` | Conflitos de schedule |

### 5.4 SQL Server KPIs (`sqlserver_kpis.py` -- `/api/sqlserver-kpis`)

| Metodo | URL | Descricao |
|--------|-----|-----------|
| GET | `/api/sqlserver-kpis/dashboard` | Dashboard completo (12 KPIs paralelos, cache 60s) |
| GET | `/api/sqlserver-kpis/db-availability` | Database availability |
| GET | `/api/sqlserver-kpis/disk-usage` | Disk usage por volume |
| GET | `/api/sqlserver-kpis/tlog-usage` | Transaction log usage |
| GET | `/api/sqlserver-kpis/alwayson-status` | Always On health |
| GET | `/api/sqlserver-kpis/filegroup-usage` | Filegroup usage |
| GET | `/api/sqlserver-kpis/blocked-sessions` | Blocked sessions |
| GET | `/api/sqlserver-kpis/instance-availability` | Instance availability |
| GET | `/api/sqlserver-kpis/backup-status` | Backup status |
| GET | `/api/sqlserver-kpis/job-failures` | SQL Agent job failures |
| GET | `/api/sqlserver-kpis/index-fragmentation` | Index fragmentation |
| GET | `/api/sqlserver-kpis/statistics-outdated` | Statistics outdated |
| GET | `/api/sqlserver-kpis/tempdb-usage` | TempDB usage |

### 5.5 Intelligence KPIs (`intelligence_kpis.py` -- `/api/v1/kpis`)

Consome views pre-calculadas do `WatcherDB_Intelligence` (dados agregados por ETL/SQL Agent Jobs).

| Metodo | URL | Descricao |
|--------|-----|-----------|
| GET | `/api/v1/kpis/dashboard` | Dashboard KPI completo (cache 30s) |
| GET | `/api/v1/kpis/{kpi_name}` | KPI individual |
| GET | `/api/v1/kpis/metadata` | Metadados de todos os KPIs |

**Freshness Windows** (linhas 74-80 de `intelligence_kpis.py`):
```python
FRESHNESS_WINDOWS = {
    'services': 15,      # minutos
    'real_time': 5,      # Blocked Sessions, Deadlocks
    'capacity': 1440,    # Filegroups, Disk (24h)
    'backup': 1440,      # 24h
    'alwayson': 5,       # coleta cada 1 min
}
```

### 5.6 Overview Dashboard (`overview_dashboard.py` -- `/api/v1/overview`)

| Metodo | URL | Descricao |
|--------|-----|-----------|
| GET | `/api/v1/overview/dashboard` | Overview com scores por categoria |
| GET | `/api/v1/overview/score` | Score global |
| POST | `/api/v1/overview/refresh` | Refresh manual (rate limit: 1/min) |
| GET | `/api/v1/overview/collection-status` | Estado da coleta |

### 5.7 Oracle KPIs (`oracle_kpis.py` -- `/api/oracle-kpis`)

Opcional: requer `pip install oracledb` e credenciais Oracle no `.env`.

| Metodo | URL | Descricao |
|--------|-----|-----------|
| GET | `/api/oracle-kpis/dashboard` | Dashboard Oracle KPIs |
| GET | `/api/oracle-kpis/{view_name}` | Dados de uma view especifica |
| GET | `/api/oracle-kpis/view-definition/{view_name}` | DDL da view Oracle |

### 5.8 Monitoring (endpoints inline no `watcherdb_main.py`)

| Metodo | URL | Descricao |
|--------|-----|-----------|
| GET | `/api/monitoring/servers` | Lista de todos os servidores |
| GET | `/api/monitoring/server/{server_id}` | Detalhes de um servidor |
| GET | `/api/monitoring/alerts` | Alertas activos |
| GET | `/api/monitoring/ping/{hostname}` | Ping a um servidor |
| GET | `/api/monitoring/test-connection/{hostname}` | Teste de conectividade |
| GET | `/api/monitoring/space/server/{server_id}` | Analise de espaco |
| GET | `/api/monitoring/space/dashboard` | Dashboard de espaco |
| GET | `/api/monitoring/backup/server/{server_id}/summary` | Resumo de backups |
| GET | `/api/monitoring/backup/server/{server_id}/issues` | Problemas de backup |
| GET | `/api/monitoring/backup/server/{server_id}/health` | Saude dos backups |
| GET | `/api/monitoring/backup/server/{server_id}/patterns` | Padroes de backup |
| GET | `/api/monitoring/backup/server/{server_id}/gaps` | Gaps de backup |
| GET | `/api/monitoring/backup/summary` | Resumo global de backups |
| GET | `/api/monitoring/memory/server/{server_id}` | Analise de memoria |
| POST | `/api/monitoring/memory/os-snapshot/{server_id}` | Snapshot OS memory via WMI |
| GET | `/api/monitoring/cpu/server/{server_id}` | Analise de CPU |
| GET | `/api/monitoring/memory/alwayson/{ag_name}` | Comparacao memoria AO |
| GET | `/api/monitoring/memory/summary` | Resumo memoria global |
| GET | `/api/monitoring/memory/servers` | Todos os servidores com memoria |
| GET | `/api/monitoring/security/server/{server_id}` | Analise seguranca |
| GET | `/api/monitoring/windows-events/{server_id}` | Windows Event Log |
| GET | `/api/monitoring/sql-errors/{server_id}` | SQL Server Error Log |

### 5.9 Outros Routers

| Router | Prefix | Endpoints Chave |
|--------|--------|----------------|
| `service_status` | `/api/monitoring/services` | `GET /server/{server_id}` -- Status servicos SQL |
| `os_performance` | `/api/os` | `GET /{hostname}/memory`, `/cpu`, `/disk` -- Metricas OS via WMI |
| `cluster` | `/api/cluster` | `GET /server/{name}/health`, `/summary` -- WSFC health |
| `disk_unallocated` | `/api/disk-unallocated` | `GET /summary`, `/server/{id}` -- Espaco nao alocado |
| `database_discovery` | `/api/discover` | `GET /server/{id}`, `POST /all` -- Auto-descoberta DBs |
| `network_diagnostics` | `/api/diagnostics` | `GET /connectivity/{server_id}` -- Teste multi-layer |
| `users` | `/api/users` | `GET /server/{id}` -- Analise seguranca SQL Server users |
| `sql_queries` | `/api/queries` | `POST /execute`, `GET /databases/{id}` -- Queries troubleshooting |

### 5.10 Paginas HTML

| URL | Template | Descricao |
|-----|----------|-----------|
| `/watcherdb` | `watcherdb_portal.html` | Portal principal |
| `/watcherdb/control` | `watcherdb_control.html` | Admin panel |
| `/portal` | `watcherdb_portal.html` | Alias |
| `/space-dashboard` | `space_dashboard.html` | Dashboard espaco |

---

## 6. Modulos de Monitorizacao

### 6.1 `modules/monitoring/monitoring.py`

**Classes:**
- `ConnectionInfo` -- Dataclass para parametros de conexao
- `ConnectionPool` -- Pool de conexoes pyodbc (max_connections, thread-safe)
- `SQLServerExecutor` -- Execucao paralela de queries (ThreadPoolExecutor)
- `SQLServerMonitoring` -- Orquestrador: carrega config, executa queries por servidor

**Queries SQL executadas:** Via `modules/monitoring/queries.py` (`SQLQueries` class)

### 6.2 `modules/monitoring/queries.py`

Classe `SQLQueries` com queries como constantes de classe:
- `HEALTH_OVERVIEW` -- Versao, uptime, CPU, memoria, TDE
- `DATABASES_INFO` -- Lista de DBs com tamanho, recovery model
- `ACTIVE_SESSIONS` -- Sessoes activas, blocking
- `PERFORMANCE_COUNTERS` -- dm_os_performance_counters
- `DISK_USAGE` -- Volumes, espaco usado/livre
- `BACKUP_STATUS` -- Ultimo backup de cada tipo por DB
- `ALWAYSON_STATUS` -- Estado dos AGs, replicas, databases
- Todas usam `WITH(NOLOCK)` -- PORQUEE: queries read-only de monitorizacao; evita competicao de locks nos servidores de producao

### 6.3 `modules/monitoring/backup_analysis.py`

**Classe:** `BackupAnalysisEngine`
- Analisa ultimo backup por tipo (FULL, DIFF, LOG)
- Calcula idade, identifica gaps
- Gera alertas por severidade
- Exporta CSV

### 6.4 `modules/monitoring/memory_analysis.py`

**Funcoes exportadas:**
- `get_server_memory_analysis(server_id)` -- Buffer pool, plan cache, memory clerks
- `get_alwayson_memory_comparison(ag_name)` -- Comparacao entre replicas
- `get_memory_health_summary()` -- Resumo global
- `analyze_os_memory_snapshot(server_id)` -- Metricas OS via WMI (pywin32)

### 6.5 `modules/monitoring/watcherdb_alwayson_check.py`

**Classe:** `AlwaysOnChecker` (singleton via `get_alwayson_checker()`)
- Carrega inventario de AGs de `config/alwayson_inventory.json`
- `get_all_ag_overview(lazy=True)` -- Modo lazy: retorna dados do JSON sem conectar
- `get_ag_status(server, instance)` -- Conecta ao servidor e executa queries AO
- `get_ag_failover_events(server, instance, days)` -- Eventos de failover
- `analyze_failover_patterns(events)` -- Reconhecimento de padroes (hora, dia, causa)

### 6.6 `modules/monitoring/cluster_analysis.py`

- `check_cluster_health(server, timeout)` -- Via PowerShell `Get-ClusterNode`, `Get-ClusterResource`
- Fallback: `cluster_analysis_fast.py` com timeout reduzido

### 6.7 `modules/monitoring/service_monitor.py`

**Classe:** `SQLServiceMonitor`
- Descobre servicos SQL via WMI ou `sc query`
- Retorna estado (Running, Stopped, etc)
- Cache com TTL de 120s

---

## 7. Base de Dados

### 7.1 Schema Completo

#### 7.1.1 `WatcherDB_Users`

```sql
CREATE TABLE dbo.WatcherDB_Users (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    username        NVARCHAR(100)  NOT NULL UNIQUE,
    password_hash   NVARCHAR(500)  NOT NULL,       -- bcrypt ou "ad_auth:<sha256>"
    role            NVARCHAR(50)   NOT NULL DEFAULT 'viewer',
    email           NVARCHAR(200)  NULL,
    full_name       NVARCHAR(200)  NULL,
    disabled        BIT            NOT NULL DEFAULT 0,
    failed_attempts INT            NOT NULL DEFAULT 0,
    locked_until    DATETIME2      NULL,
    last_login      DATETIME2      NULL,
    created_at      DATETIME2      NOT NULL DEFAULT GETDATE()
);
```

#### 7.1.2 `WatcherDB_Auth_Log`

```sql
CREATE TABLE dbo.WatcherDB_Auth_Log (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    username    NVARCHAR(100)  NOT NULL,
    action      NVARCHAR(50)   NOT NULL,  -- LOGIN_SUCCESS, LOGIN_FAILED, PASSWORD_CHANGE
    ip_address  NVARCHAR(50)   NULL,
    details     NVARCHAR(500)  NULL,
    created_at  DATETIME2      NOT NULL DEFAULT GETDATE()
);
CREATE NONCLUSTERED INDEX IX_AuthLog_Username
    ON dbo.WatcherDB_Auth_Log (username, created_at DESC);
```

#### 7.1.3 `WatcherDB_User_Preferences`

```sql
CREATE TABLE dbo.WatcherDB_User_Preferences (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    username         NVARCHAR(100)  NOT NULL,
    preference_key   NVARCHAR(100)  NOT NULL,
    preference_value NVARCHAR(MAX)  NULL,  -- Fernet encrypted ("enc:...")
    updated_at       DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT UQ_UserPref_Key UNIQUE (username, preference_key)
);
CREATE NONCLUSTERED INDEX IX_UserPref_Username
    ON dbo.WatcherDB_User_Preferences (username)
    INCLUDE (preference_key, preference_value);
```

### 7.2 Connection Pool

**Ficheiro:** `api/connection_pool.py`

#### SQLServerConnectionPool (servidores monitorados)

```
Config: POOL_MAX_CONNECTIONS = 20, POOL_CONNECTION_LIFETIME = 300s (5 min)
Pattern: Singleton (double-checked locking com threading.Lock)
Pools: Dict[str, List[tuple(conn, timestamp)]] -- uma lista por "server_database"
Locks: Meta-lock pattern para evitar race condition na criacao de locks por pool_key
Cleanup: Thread daemon a cada 60s remove conexoes > 5 min
Health check: SELECT 1 antes de retornar conexao do pool
```

#### IntelligenceConnectionPool (WatcherDB_Intelligence)

```
Config: max_connections = 10
Server: INTELLIGENCE_SERVER env var (default: SQLHDSTST505\I01)
Database: INTELLIGENCE_DATABASE env var (default: WatcherDB_Intelligence)
Auth: Windows Auth (default) ou SQL Auth via INTELLIGENCE_SQL_USER/PASSWORD
```

#### Isolation Level

```python
cursor.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
```

**PORQUEE:** Todas as queries de monitorizacao sao read-only. READ UNCOMMITTED (equivalente a NOLOCK) evita que queries do WatcherDB causem blocking nos servidores de producao. O risco de dirty reads e aceitavel para dados de monitorizacao.

### 7.3 Queries Criticas

**Preferencias (MERGE atomico):**
```sql
MERGE dbo.WatcherDB_User_Preferences WITH (HOLDLOCK) AS target ...
```

**Lockout (UPDATE condicional):**
```sql
UPDATE dbo.WatcherDB_Users SET failed_attempts = failed_attempts + 1,
    locked_until = CASE WHEN failed_attempts >= @threshold
        THEN DATEADD(MINUTE, @lockout, GETDATE()) ELSE locked_until END
WHERE username = ?
```

**Auto-provisioning AD (INSERT se nao existe):**
```sql
INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, email, full_name)
VALUES (?, 'ad_auth:<sha256>', ?, ?, ?)
```

### 7.4 Encriptacao de Passwords em `servers.json`

**Ficheiro:** `config/servers.json`

Passwords dos servidores SQL monitorados sao encriptadas com Fernet:
```json
"password": "encrypted:gAAAAABpqX6wFMUaMb_3ZMK..."
```

Decriptacao em `api/routers/network_diagnostics.py` (linhas 368-379):
```python
if pwd.startswith('encrypted:'):
    from cryptography.fernet import Fernet
    key = os.environ.get('WATCHERDB_ENCRYPTION_KEY', '')
    f = Fernet(key.encode())
    pwd = f.decrypt(pwd[len('encrypted:'):].encode()).decode()
```

**Chave:** `WATCHERDB_ENCRYPTION_KEY` no `.env` -- a mesma usada para preferencias.

---

## 8. Frontend

### 8.1 Arquitectura Single-File

**Ficheiro:** `templates/watcherdb_portal.html` (45290 linhas)

**PORQUEE single-file:** Deploy simplificado em Windows Server (xcopy deploy). Sem build tools (webpack, vite). Funciona com qualquer servidor HTTP. Trade-off: dificil de manter, mas a equipa e pequena (2-3 DBAs).

**Estrutura interna do HTML:**
```
Linhas 1-100:      <head>, CSS inline, meta tags
Linhas 100-3000:   <style> bloco principal
Linhas 3000-4000:  i18n setup, language selector
Linhas 4015-4078:  AUTH SYSTEM (token, interceptor, login handler)
Linhas 4080-4298:  Login overlay, profile dropdown, checkAuthOnLoad
Linhas 4300-4450:  PREFERENCES SYNC (load, save, interceptor localStorage)
Linhas 4450-6000:  Sidebar, server list, search, sort
Linhas 6000-45000: Tab content renderers (overview, backup, memory, etc.)
```

### 8.2 Interceptor Fetch

**Ficheiro:** `templates/watcherdb_portal.html` (linhas 4055-4077)

```javascript
const _originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    if (typeof url === 'string' && url.startsWith('/api')) {
        const token = getAuthToken();
        if (token) {
            options.headers['Authorization'] = 'Bearer ' + token;
        }
    }
    return _originalFetch.call(window, url, options).then(resp => {
        if (resp.status === 401 && url.startsWith('/api') && !url.includes('/auth/login')) {
            clearAuthData();
            showLoginOverlay();
        }
        return resp;
    });
};
```

**Funcionalidade:**
1. Injecta `Authorization: Bearer` em todos os requests a `/api/*`
2. Auto-logout em 401 (excepto o proprio login endpoint)

### 8.3 Interceptor localStorage

**Ficheiro:** `templates/watcherdb_portal.html` (linhas 4386-4413)

Monkeypatch de `localStorage.setItem/getItem/removeItem`:
- Para chaves em `SYNCED_PREF_KEYS`: redireciona para namespace `user:{username}:{key}`
- Para outras chaves: comportamento original
- No `setItem`: trigger `schedulePrefSync()` com debounce de 5s

### 8.4 Tabs Dinamicas

O portal usa um sistema de tabs por servidor. Cada servidor pode ter multiplas tabs abertas simultaneamente (overview, backup, memory, jobs, etc.). A tab activa e guardada em `lastActiveTab` e restaurada no login via `restoreUserSession()`.

### 8.5 KPI Dashboard

O dashboard de KPIs no frontend consome:
- `/api/v1/kpis/dashboard` (Intelligence KPIs -- views pre-calculadas)
- `/api/sqlserver-kpis/dashboard` (SQL Server KPIs directos)

Cards KPI com cores por severidade, contadores, e drill-down por servidor.

### 8.6 i18n

**Ficheiros:** `static/i18n/`, `static/js/watcherdb_i18n.js`

Sistema de internacionalizacao com selector de lingua no header. Suporta PT e EN.

---

## 9. Deploy e Operacao

### 9.1 Dependencias

**Ficheiro:** `requirements.txt`

```
# Core
fastapi>=0.104.0, uvicorn[standard]>=0.24.0, python-multipart>=0.0.6
pyodbc>=5.0.0, pydantic>=2.4.0, pydantic-settings>=2.0.0

# Auth
python-jose[cryptography]>=3.3.0, passlib[bcrypt]>=1.7.4, bcrypt>=4.1.0

# Data
openpyxl>=3.1.0, pandas>=2.1.0, numpy>=1.25.0

# Visualization / ML
plotly>=5.17.0, scikit-learn>=1.3.0

# System
psutil>=5.9.0, pywin32>=306, wmi>=1.5.1

# HTTP
httpx>=0.25.0, requests>=2.31.0

# Config
pyyaml>=6.0.1, python-dotenv>=1.0.0

# Templating / Async
jinja2>=3.1.0, aiofiles>=23.2.0, websockets>=12.0

# Rate Limiting
slowapi>=0.1.9

# Opcional:
# oracledb>=2.0.0 (Oracle KPIs)
# ldap3 (Active Directory)
# cryptography (Fernet, ja incluido via python-jose[cryptography])
```

### 9.2 Variaveis de Ambiente Obrigatorias

| Variavel | Obrigatoria | Descricao |
|----------|-------------|-----------|
| `JWT_SECRET_KEY` | SIM (producao) | Chave para assinar tokens JWT. Se ausente, gera efemera |
| `WATCHERDB_ENCRYPTION_KEY` | SIM | Chave Fernet (Base64, 32 bytes) para encriptar passwords e preferencias |
| `INTELLIGENCE_SERVER` | Nao (default: `SQLHDSTST505\I01`) | Servidor SQL para metadados |
| `INTELLIGENCE_DATABASE` | Nao (default: `WatcherDB_Intelligence`) | Base de dados Intelligence |
| `ORACLE_HOST` | Nao | Servidor Oracle (se usar Oracle KPIs) |
| `ORACLE_PORT` | Nao (default: 1521) | Porta Oracle |
| `ORACLE_SERVICE_NAME` | Nao | Service name Oracle |
| `ORACLE_USER` | Nao | Username Oracle |
| `ORACLE_PASSWORD` | Nao | Password Oracle |
| `AD_ENABLED` | Nao (default: true) | Activar auth LDAP/AD |
| `AD_DOMAIN` | Nao (auto-detectado de USERDOMAIN) | Dominio NetBIOS |
| `AD_SERVER` | Nao | LDAP server FQDN |
| `SMTP_PASSWORD` | Nao | Password SMTP para notificacoes |

### 9.3 Arranque

#### Desenvolvimento (linha de comando)

```bash
cd WATCHERDB_V3.1
python -m uvicorn watcherdb_main:app --host 0.0.0.0 --port 8445 --reload
```

#### Producao (Windows Service)

**Instalacao:**
```bash
cd WATCHERDB_V3.1/services/web_service
python install.py
# ou
python service.py install
```

**Gestao:**
```bash
net start WatcherDBWebServiceV31
net stop WatcherDBWebServiceV31
sc query WatcherDBWebServiceV31
```

**Ficheiro:** `services/web_service/service.py`
- Classe: `WatcherDBWebService(win32serviceutil.ServiceFramework)`
- Service name: `WatcherDBWebServiceV31`
- Display name: `WatcherDB Web Service V3.1`
- Porta default: **8445**
- Redireciona stdout/stderr para ficheiros (Windows Service nao tem terminal)
- Aceita `SvcShutdown()` para shutdown graceful do Windows
- Logging: `services/web_service/logs/` (service.log, errors.log, stdout.log, stderr.log)
- Log rotation: 10MB, 10 backups

### 9.4 Logs

| Ficheiro | Conteudo |
|----------|----------|
| `services/web_service/logs/service.log` | Log principal do servico (rotacao 10MB x 10) |
| `services/web_service/logs/errors.log` | Apenas erros (rotacao 5MB x 5) |
| `services/web_service/logs/stdout.log` | stdout redireccionado |
| `services/web_service/logs/stderr.log` | stderr redireccionado |
| Console (dev) | `logging.basicConfig(level=logging.INFO)` |

### 9.5 Portas

| Porta | Servico |
|-------|---------|
| 8445 | WatcherDB Web Service (Uvicorn/FastAPI) |
| 1433 | SQL Server monitorados (pyodbc) |
| 389/636 | LDAP/LDAPS para Active Directory |
| 1434/UDP | SQL Server Browser (descoberta de portas) |
| 1521 | Oracle DB (opcional) |

---

## 10. Seguranca

### 10.1 Auditoria

**Tabela:** `WatcherDB_Auth_Log`

Eventos auditados (via `_log_auth()` em `services/auth_service.py`):
- `LOGIN_SUCCESS` -- com IP e metodo (AD/LDAP ou local DB)
- `LOGIN_FAILED` -- com IP, razao (credenciais invalidas, conta bloqueada, etc)

**Middleware:** `AuditMiddleware` em `services/web_service/security/audit.py`
- Loga todas as requests (configuravel)
- Loga falhas de auth (401, 403)
- Loga accoes criticas (POST, PUT, DELETE)
- Logger separado com output para ficheiro dedicado

### 10.2 Configuracao de Producao Obrigatoria

1. **JWT_SECRET_KEY** -- DEVE ser definida no `.env`. Sem ela, tokens nao sobrevivem restart.
2. **WATCHERDB_ENCRYPTION_KEY** -- DEVE ser definida. Sem ela, preferencias ficam em plaintext.
3. **Alterar passwords default** -- O script SQL cria users com password `admin123`.
4. **CORS** -- Actualmente `allow_origins=["*"]` (linha 2590 de watcherdb_main.py). Deve ser restringido em producao.
5. **HTTPS** -- A aplicacao corre em HTTP. Deve estar atras de reverse proxy com TLS.
6. **AD_ENABLED** -- Activar LDAP para evitar passwords locais.

### 10.3 Superficie de Ataque

| Vector | Estado | Mitigacao |
|--------|--------|-----------|
| Brute-force login | Mitigado | Lockout 5 tentativas / 15 min |
| User enumeration via timing | Mitigado | Constant-time dummy hash |
| JWT secret fraca | Risco se default | Warning no log se efemera |
| CORS wildcard | Risco | `allow_origins=["*"]` -- restringir |
| HTTP sem TLS | Risco | Precisa reverse proxy |
| SQL Injection | Mitigado | Queries parametrizadas em auth_service.py e auth_compat.py |
| Credenciais no .env | Risco se commitado | `.gitignore` exclui `.env` |
| Passwords default (admin123) | Risco | Script SQL cria users com senha fraca -- alterar |
| Token blacklist in-memory | Limitacao | Nao persiste entre restarts |
| Preferencias sem Fernet key | Risco | Guardadas em plaintext se key ausente |
| servers.json com passwords | Mitigado | Fernet encryption |
| NOLOCK (dirty reads) | Aceitavel | Read-only monitoring -- dados pode ser stale |
| Pickle deserialization (cache) | Risco baixo | Ficheiro local, nao aceita input externo |

### 10.4 Headers de Seguranca

**Ficheiro:** `services/web_service/security/headers.py`

Configuravel via `config.yaml` -> `security` section. Headers como X-Content-Type-Options, X-Frame-Options, etc. [DECISAO DE DESIGN -- VERIFICAR se estao activos no server.py bootstrap]

---

## 11. Limitacoes Conhecidas e Divida Tecnica

### 11.1 Ficheiro Monolitico `watcherdb_main.py` (8229 linhas)

~70 endpoints inline, cache, classes utilitarias, tudo no mesmo ficheiro. Os routers em `api/routers/` foram extraidos parcialmente, mas a maioria dos endpoints de monitoring permanece inline. Refactoring parcial feito com o package `watcherdb/` mas a dualidade de localizacao cria confusao.

### 11.2 Frontend Single-File (45290 linhas)

Manutencao muito dificil. Nao ha separacao de concerns (HTML/CSS/JS misturados). Nao ha testes de frontend. Qualquer alteracao requer cuidado com collisoes de selectores CSS e nomes de funcoes JS.

### 11.3 Background Services Desabilitados

**Ficheiro:** `watcherdb_main.py` (linhas 2362-2367)

```python
app.state.background_services = None
logger.info('Background services DISABLED (cache uses blocking locks)')
```

O `RedisLikeCache` usa `threading.RLock`, que bloqueia o event loop asyncio quando chamado de coroutines. Background services que fazem coleta periodica estao desabilitados ate refactoring do cache para `asyncio.Lock`.

### 11.4 Dois Sistemas de Auth Paralelos

- **V3.1 (activo):** `api/routers/auth_compat.py` + `services/auth_service.py` (database-backed)
- **V1 (fallback):** `services/web_service/auth/` (in-memory, ficheiro-based)

O fallback e carregado se `auth_compat` falhar (linha 2540 de watcherdb_main.py). Isto cria ambiguidade sobre qual sistema esta activo.

### 11.5 Sem RBAC Granular nos Endpoints de Monitorizacao

Todos os endpoints de monitorizacao (backup, memory, space, etc.) nao verificam roles. Qualquer user autenticado (incluindo `viewer`) pode aceder a todos os dados. A unica proteccao e nos endpoints admin (`_require_admin`).

### 11.6 Cache Pickle -- Risco de Corrupcao

O `RedisLikeCache` persiste dados via `pickle.dump()` a cada 10 segundos. Se o processo crashar durante a escrita, o ficheiro fica corrompido. Ha recovery (backup do ficheiro corrompido + start com cache vazio), mas dados sao perdidos.

### 11.7 Pool de Conexoes sem Connection Draining

`SQLServerConnectionPool` valida conexoes com `SELECT 1` antes de retornar do pool, mas nao implementa connection draining (fecho graceful de conexoes quando o servidor e retirado do inventario).

### 11.8 Dependencia do ODBC Driver 17

Hardcoded em multiplos locais (`connection_pool.py`, `monitoring.py`, `jobs.py`). Se o servidor tiver apenas ODBC Driver 18, e necessario alterar em todos os ficheiros. Deveria ser configuravel centralmente.

### 11.9 Token Blacklist Nao Distribuida

`_token_blacklist = set()` em `auth_compat.py` e in-memory. Se houver multiplos workers Uvicorn, cada worker teria a sua blacklist. Actualmente o servico corre com 1 worker (default do service.py).

### 11.10 `.env` com Credenciais Reais no Repositorio

O ficheiro `.env` contem credenciais reais (JWT secret, Oracle password, SMTP password, Fernet key). Embora `.gitignore` devesse excluir `.env`, o git status mostra que esta trackeado. **CRITICO: remover do tracking e rodar secrets.**

### 11.11 CORS `allow_origins=["*"]`

**Ficheiro:** `watcherdb_main.py` (linha 2590)

Em producao, isto permite qualquer origem fazer requests autenticados. Deve ser restringido aos dominios internos da TAP.

### 11.12 Dualidade `config/servers.json` vs `config/sql_servers.json`

Dois ficheiros de configuracao de servidores com formatos diferentes:
- `servers.json` -- Usado por `network_diagnostics.py`, contem passwords encriptadas, info AlwaysOn, databases
- `sql_servers.json` -- Usado pelo `lifespan()` para `SQLServerMonitoring`, formato mais simples (id, host, instance, port, databases)

A duplicacao cria risco de dessincronizacao.

---

*Documento gerado em 2026-03-23. Baseado na analise do codigo-fonte do WatcherDB V3.1.*
