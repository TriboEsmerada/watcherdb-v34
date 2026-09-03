# WatcherDB V3.1 vs V3.0 — Diferenças Detalhadas

## Contexto

O WatcherDB V3.1 é uma evolução do V3.0 focada em dois pilares:
1. **Sistema de autenticação enterprise** — persistência em SQL Server, gestão de utilizadores, auditoria, LDAP/AD, painel de controlo admin
2. **Persistência de sessão por utilizador** — cada user vê exactamente o que configurou no último login (KPIs, queries, filtros, tab activa, servidor), com **isolamento total por username** no localStorage

O V3.0 utiliza autenticação in-memory básica e preferências locais ao browser. O V3.1 move tudo para SQL Server com sync automático e namespace isolado por utilizador (`user:{username}:{key}`).

---

## 1. NOVOS FICHEIROS NO V3.1

### 1.1 Router de Autenticação — `api/routers/auth_compat.py`
**Propósito:** Router FastAPI com autenticação database-backed, tokens JWT, CRUD de utilizadores, preferências encriptadas e auditoria.

**Endpoints (17):**
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/auth/login` | Login com geração de token JWT |
| GET | `/api/auth/validate` | Validação de token |
| GET | `/api/auth/me` | Info do utilizador atual |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/users` | Listar utilizadores (admin) |
| POST | `/api/auth/users` | Criar utilizador (admin) |
| POST | `/api/auth/change-password` | Alterar password |
| POST | `/api/auth/users/{username}/toggle` | Ativar/desativar utilizador |
| GET | `/api/auth/preferences` | Obter preferências do utilizador |
| PUT | `/api/auth/preferences` | Guardar preferências (encriptadas com Fernet) |
| DELETE | `/api/auth/preferences/{key}` | Remover preferência |
| GET | `/api/auth/admin/auth-log` | Log de eventos de autenticação |
| GET | `/api/auth/admin/sessions` | Sessões ativas |
| GET | `/api/auth/admin/system-config` | Configuração do sistema |
| POST | `/api/auth/heartbeat` | Heartbeat de sessão |
| GET | `/api/auth/admin/online` | Contagem de utilizadores online |
| POST | `/api/auth/admin/users/{username}/role` | Alterar role do utilizador |

---

### 1.2 Serviço de Autenticação — `services/auth_service.py`
**Propósito:** Lógica central de autenticação (~600 linhas).

**Componentes:**
- Password hashing (bcrypt obrigatório — passlib[bcrypt] required, sem fallback SHA-256)
- Verificação legacy: hashes SHA-256 antigos são aceites para login mas não criados
- Criação e validação de tokens JWT (chave efémera se env var não definida, com warning)
- Configuração e auto-detecção LDAP/AD
- Autenticação LDAP com auto-provisioning opcional
- Constant-time user enumeration protection (hash dummy quando user não existe)
- Singleton AuthService com:
  - `get_instance()` — getter do singleton
  - `_get_user_from_db(username)` — busca na tabela WatcherDB_Users (sem NOLOCK, sem fallback para defaults)
  - `_increment_failed_attempts(username)` — tracking parametrizado (sem f-string)
  - `_reset_failed_attempts(username)` — reset após login com sucesso
  - `_update_last_login(username)` — atualização do último login
  - `_log_auth(username, action, ip, details)` — log para WatcherDB_Auth_Log (erros logados, não silenciados)
- Token blacklist in-memory (tokens revogados no logout)
- Heartbeat com cleanup automático de entradas >10 minutos
- Lockout de conta: 15 min após 5 tentativas falhadas
- Suporte híbrido: utilizadores locais + LDAP/AD
- `_execute_query` propaga excepções (sem fallback silencioso)
- MERGE com HOLDLOCK nas preferências (sem race condition)
- `change-password` valida password actual obrigatoriamente

---

### 1.3 Schema de Base de Dados — `database/CREATE_USER_AUTH_PREFS.sql`
**Propósito:** DDL para criação das tabelas de autenticação.

**Tabelas criadas:**

| Tabela | Campos Principais | Propósito |
|--------|-------------------|-----------|
| `WatcherDB_Users` | id, username (unique), password_hash, role (admin/analyst/viewer/operator), email, full_name, disabled, failed_attempts, locked_until, last_login, created_at | Contas de utilizador |
| `WatcherDB_Auth_Log` | id, username, action (LOGIN_SUCCESS, LOGIN_FAILED, PASSWORD_CHANGE, USER_ENABLED, USER_DISABLED), ip_address, details, created_at | Auditoria de autenticação |
| `WatcherDB_User_Preferences` | id, username, preference_key, preference_value (encriptado com Fernet), updated_at | Preferências por utilizador |

**Índices:** Index em (username, created_at DESC) na Auth_Log; unique constraint em (username, preference_key) nas Preferences.

**Utilizadores pré-configurados:** admin, salomao, ricardo, viewer (todos com hash bcrypt de "admin123").

---

### 1.4 Painel de Controlo — `templates/watcherdb_control.html`
**Propósito:** Interface administrativa (~2000+ linhas HTML/CSS/JS).

**Tabs:**
- **User Management** — CRUD de utilizadores, atribuição de roles, ativar/desativar contas
- **Auth Log** — Histórico de eventos de autenticação (logins, alterações de password, etc.)
- **Active Sessions** — Monitorização de utilizadores online e suas sessões
- **System Config** — Visualização/edição de configurações do sistema
- **Statistics** — Cards com totais de utilizadores, sessões ativas, eventos recentes

**Design:** Dark theme com NeuroUI (mesmo design do portal principal).

---

## 2. FICHEIROS MODIFICADOS NO V3.1

### 2.1 Template Principal — `templates/watcherdb_portal.html`

#### 2.1.1 Sistema de Autenticação (UI)
- Overlay de login (posição fixa, fundo com gradiente escuro)
- Card de login com campos username/password, botão com spinner
- Exibição de mensagens de erro para logins falhados
- Badge do utilizador no header (avatar + nome + role)
- Menu dropdown de perfil do utilizador
- Funcionalidade de logout
- JavaScript para gestão do estado de autenticação
- CSS para todos os novos componentes de auth (inputs, botões, animações)

#### 2.1.2 Persistência de Sessão por Utilizador
**20 chaves sincronizadas automaticamente** entre localStorage e servidor via `SYNCED_PREF_KEYS`:

| Chave | O que persiste |
|-------|----------------|
| `dashboardKPIConfig` | KPIs visíveis, ordem, categorias |
| `sqlDiagnosticsConfig` | Queries SQL Diag visíveis |
| `kpi-dashboard-compact` | Modo compacto do dashboard |
| `backup_days` | Janela de análise de backup (dias) |
| `backup_include_system` | Incluir DBs de sistema |
| `backup_sort` | Ordenação de backups |
| `backup_filter` | Filtro de tipo de backup |
| `backup_db_filter` | Filtro de nome de database |
| `backup_hours_filter` | Threshold de horas para gaps |
| `backup_gaps_days` | Janela de gaps (dias) |
| `log_hours` | Janela temporal de logs |
| `log_type` | Filtro de tipo de log |
| `serverSortOrder` | Ordenação da lista de servidores |
| `sidebarCollapsed` | Estado da sidebar |
| `kpiRefreshInterval` | Intervalo de refresh |
| `requestTimeout` | Timeout de requests |
| `enableDebugLogs` | Debug logs activos |
| `watcherdb_server_search_frequency` | Frequência de pesquisa por servidor |
| `lastActiveTab` | Última tab activa (restaurada no login) |
| `lastSelectedServer` | Último servidor seleccionado (restaurado no login) |
| `userCustomQueries` | Queries SQL customizadas pessoais do utilizador |

**Isolamento por utilizador (localStorage):**
- Chaves SYNCED são armazenadas com prefixo `user:{username}:{key}` no localStorage
- Interceptores transparentes em `localStorage.getItem/setItem/removeItem` redirecionam automaticamente
- Cada utilizador tem namespace isolado — sem cruzamento de sessões no mesmo browser
- Migração automática de chaves antigas (sem prefixo) no primeiro login após a actualização
- Helpers: `getCurrentUsername()`, `userPrefKey(key)`, `getUserPref(key)`, `setUserPref(key, value)`

**Mecanismo de sync:**
- Intercepção de `localStorage.setItem()` — qualquer alteração a uma chave sincronizada dispara `schedulePrefSync()` com debounce de 5 segundos
- `loadPreferencesFromServer()` — chamada após login, restaura todas as chaves do servidor para o localStorage (prefixadas)
- `syncPreferencesToServer()` — envia todas as chaves prefixadas para `PUT /api/auth/preferences` (encriptadas com Fernet)
- `handleLogout()` — sincroniza preferências pendentes antes de limpar auth data

**Restauração de sessão:**
- Nova função `restoreUserSession()` — chamada após login e após `loadServers()`
- Restaura: tab activa, servidor seleccionado, estado da sidebar, filtros de backup e log
- Fluxo: Login → `loadPreferencesFromServer()` → `hideLoginOverlay()` → `loadServers()` → `restoreUserSession()`

#### 2.1.3 Custom Queries Per-User
- Separação entre **queries globais** (read-only, do `/api/config/custom-queries`) e **queries pessoais** (editáveis, do `userCustomQueries` no localStorage)
- `loadCustomQueriesManager()` — apresenta secção "Minhas Queries" (editáveis) + "Queries Globais" (read-only com ícone de cadeado)
- `saveCustomQuery()` — salva na lista pessoal do utilizador (auto-sync para servidor)
- `deleteCustomQuery()` — remove apenas das queries pessoais
- `loadSQLDiagnostics()` — carrega queries standard + globais + pessoais na aba SQL Diagnostics
- Queries pessoais são identificadas com `(pessoal)` na descrição e ícone `fa-user`
- Helpers: `getUserCustomQueries()`, `saveUserCustomQueries(queries)`

### 2.2 Intelligence KPIs — `api/routers/intelligence_kpis.py`
**Adições:**
- Dicionário `failed_by_type` para classificação de jobs falhados por tipo
- Lógica de classificação baseada no nome do job:
  - `BACKUP`, `BKP`, `BKUP` → Tipo: Backup
  - `REINDEX`, `REBUILD`, `INDEX` → Tipo: Index
  - `STATISTIC`, `STATS` → Tipo: Statistics
  - `DBCC` → Tipo: DBCC
  - `SHRINK` → Tipo: Shrink
  - `LOG` → Tipo: Log
  - `CLEANUP`, `CLEAN` → Tipo: Cleanup
  - `REPLICATION`, `REPLIC` → Tipo: Replication
  - `ALWAYSON`, `AG_` → Tipo: AlwaysOn
  - Outros → Tipo: Other
- Dados agregados nos endpoints `/failed-jobs` e `/jobs-status`

### 2.3 Aplicação Principal — `watcherdb_main.py`
**Adições:**
- Carregamento primário do `auth_compat` router (database-backed)
- Fallback para router antigo (`watcherdb.api.auth_router`) se V3.1 falhar
- Nova rota: `GET /watcherdb/control` → Serve o painel de controlo admin

---

## 3. RESUMO COMPARATIVO

| Capacidade | V3.0 | V3.1 |
|-----------|------|------|
| Autenticação | In-memory (básica) | Database-backed (SQL Server) |
| Persistência de utilizadores | Não | Sim (WatcherDB_Users) |
| Gestão de utilizadores | Não | CRUD completo + roles |
| Roles | Não | admin, analyst, viewer, operator |
| Lockout de conta | Não | Sim (15 min após 5 falhas) |
| Auditoria de auth | Não | Sim (WatcherDB_Auth_Log) |
| Preferências do utilizador | localStorage apenas (local ao browser) | Sync servidor ↔ localStorage (20 chaves, encriptadas com Fernet) |
| Isolamento de sessão | Não (localStorage partilhado) | Sim (namespace `user:{username}:{key}` no localStorage) |
| Persistência de sessão | Não (reset a cada login) | Sim (restaura tab, servidor, filtros, KPIs, sidebar) |
| Custom queries | Globais (partilhadas por todos) | Globais (read-only) + Pessoais (editáveis, per-user) |
| Painel de controlo admin | Não | Sim (watcherdb_control.html) |
| Suporte LDAP/AD | Não | Sim (com auto-provisioning) |
| Heartbeat de sessão | Não | Sim |
| Login UI no portal | Não | Sim (overlay + badge + dropdown) |
| Classificação de jobs por tipo | Não | Sim (10 categorias) |
| Assets de terceiros | CDN externo (cdnjs.cloudflare.com) | Servidos localmente (`static/vendor/`) — offline-ready |

---

## 4. ARQUITECTURA DA AUTENTICAÇÃO E PERSISTÊNCIA V3.1

```
[LOGIN]
  Browser → POST /api/auth/login (username + password)
  → auth_compat.py router
    → AuthService.get_instance()
      → _get_user_from_db() (SQL Server)
      → Verifica lockout (failed_attempts >= 5)
      → Verifica password (bcrypt hash)
      → OU tenta LDAP/AD (se configurado)
      → Gera JWT token
      → _log_auth() → WatcherDB_Auth_Log
      → _update_last_login()
  ← Token JWT + user info

[RESTAURAÇÃO DE SESSÃO]
  Browser → GET /api/auth/preferences (com token JWT)
  ← {dashboardKPIConfig: "...", lastActiveTab: "backup", lastSelectedServer: "SQLHDSPRD214\\I01", ...}
  → Migração: remove chaves antigas sem prefixo (_origRemoveItem)
  → localStorage restaurado com 20 chaves prefixadas (user:{username}:{key})
  → loadServers() → restoreUserSession()
    → Navega para último servidor + tab
    → Aplica filtros de backup/log
    → Restaura sidebar state

[ISOLAMENTO POR UTILIZADOR]
  localStorage.setItem('lastActiveTab', 'backup')
  → Interceptor detecta chave SYNCED
  → Redireciona para _origSetItem('user:salomao:lastActiveTab', 'backup')
  → schedulePrefSync() (debounce 5s)

  localStorage.getItem('lastActiveTab')
  → Interceptor detecta chave SYNCED
  → Redireciona para _origGetItem('user:salomao:lastActiveTab')
  → Retorna valor isolado do utilizador

[SYNC CONTÍNUO]
  Browser: qualquer localStorage.setItem(SYNCED_KEY) interceptado
  → schedulePrefSync() (debounce 5s)
  → PUT /api/auth/preferences {preferences: {...}}
  → WatcherDB_User_Preferences (MERGE com encriptação Fernet)

[CUSTOM QUERIES]
  Globais: GET /api/config/custom-queries → config/custom_queries.json (read-only)
  Pessoais: localStorage.getItem('userCustomQueries') → sync servidor (editáveis)
  SQL Diag: standard + globais + pessoais combinadas
```

---

## 5. ASSETS LOCAIS (SEM CDN)

Todos os assets de terceiros são servidos localmente via `/static/vendor/` — sem dependência de CDNs externas, sem warnings de Tracking Prevention, funciona offline.

```
static/vendor/fontawesome/css/all.min.css          # Font Awesome 6.4.0 CSS
static/vendor/fontawesome/webfonts/fa-*.woff2|ttf   # Font Awesome webfonts (8 ficheiros)
static/vendor/codemirror/css/codemirror.min.css     # CodeMirror 5.65.2 CSS
static/vendor/codemirror/css/monokai.min.css        # CodeMirror tema Monokai
static/vendor/codemirror/js/codemirror.min.js       # CodeMirror 5.65.2 JS
static/vendor/codemirror/js/sql.min.js              # CodeMirror modo SQL
static/vendor/html2pdf.bundle.min.js                # html2pdf.js 0.10.1
```

---

## 6. AUDITORIA DE SEGURANÇA E TESTES

### 6.1 Auditoria Completa (6 Personas Técnicas)
Executada em 2026-03-23. Relatório: `tests/SECURITY_AUDIT_REPORT.md`

| Persona | Tipo de Teste | Findings |
|---------|--------------|----------|
| Tech Lead | Code Review (arquitectura, manutenibilidade) | 15 findings |
| Pentester (AppSec) | Security (OWASP, JWT, SQLi, XSS) | 16 findings |
| QA Analyst | Functional (BDD: Given/When/Then) | 25 test cases + 4 bugs |
| Performance Engineer | Load/Stress (Locust scripts) | 4 cenários |
| DBA | Data Integrity (queries, schema, concorrência) | 12 findings |
| UX/Accessibility | WCAG 2.1 AA (labels, foco, contraste) | 20 issues |

**Total: 93 findings** identificados, priorizados por severidade.

### 6.2 Correcções de Segurança Aplicadas

**CRITICAL (4 corrigidos):**
| # | Finding | Correcção |
|---|---------|-----------|
| 1 | `_DEFAULT_USERS` backdoor (credenciais admin123 em memória) | Removido completamente. BD indisponível = login falha |
| 2 | JWT secret hardcoded (`'watcherdb-dev-secret-change-in-production'`) | Gera chave efémera + warning. Sem valor default público |
| 3 | SHA-256 sem salt como fallback de bcrypt | Removido. `passlib[bcrypt]` obrigatório (crash no startup se faltar) |
| 4 | `_execute_query` silencia erros → fallback para defaults | Propaga excepções. Sem fallback silencioso |

**HIGH (5 corrigidos):**
| # | Finding | Correcção |
|---|---------|-----------|
| 1 | `change-password` sem verificar password actual | `current_password` obrigatório e validado com `verify_password()` |
| 2 | MERGE race condition em preferências | `WITH (HOLDLOCK)` adicionado ao MERGE |
| 3 | `WITH (NOLOCK)` em queries de autenticação | Removido de `_get_user_from_db()` |
| 4 | Logout não invalida token (JWT válido 24h) | Token blacklist in-memory. `_require_auth` verifica blacklist |
| 5 | Heartbeat memory leak (dict sem cleanup) | Cleanup automático de entradas >10 minutos |

**Adicionais corrigidos:**
- User enumeration fix: constant-time hash dummy quando user não existe
- `_increment_failed_attempts` parametrizado (sem f-string SQL)
- `_log_auth` não silencia erros (log CRITICAL em vez de `except: pass`)
- Auth-log query limit capped em 1000
- Fernet cipher lazy singleton (sem recrear por chamada)
- Delete preference retorna HTTP 500 em vez de `success: true` em erro

### 6.3 Scripts de Performance (Locust)
Localização: `tests/performance/`

| Script | Cenário | Comando |
|--------|---------|---------|
| `locustfile_baseline.py` | Baseline (1 user, latência individual) | `locust -f tests/performance/locustfile_baseline.py -u 1 --run-time 2m` |
| `locustfile_concurrent.py` | 10 users simultâneos (uso real) | `locust -f tests/performance/locustfile_concurrent.py -u 10 --run-time 5m` |
| `locustfile_stress.py` | Stress (bcrypt, pool, preferences) | `locust -f tests/performance/locustfile_stress.py -u 10 --run-time 3m` |
| `locustfile_resource_exhaustion.py` | Resource leaks (15 min) | `locust -f tests/performance/locustfile_resource_exhaustion.py -u 5 --run-time 15m` |
| `run_all_tests.py` | Runner master (todos os cenários) | `python tests/performance/run_all_tests.py` |

**Thresholds de aceitação:**
| Métrica | Baseline (1 user) | Concorrente (10 users) |
|---------|-------------------|------------------------|
| Login p95 | < 2000ms | < 3000ms |
| Validate p95 | < 100ms | < 200ms |
| Heartbeat p95 | < 100ms | < 200ms |
| Error rate | 0% | < 1% |

### 6.4 Guia de Engenharia de Prompts para Testers
Localização: `prompts/prompt_watcherdb_testing_guide.md`

Guia educativo com 6 personas técnicas (prompts prontos a usar), anotações sobre Role Prompting, Chain-of-Thought, Grounding, anti-alucinação, pipeline multi-persona, prompt chaining, e glossário de termos de IA generativa para QA professionals.

---

## 7. FICHEIROS SÓ NO V3.1 (LISTA COMPLETA)

```
api/routers/auth_compat.py              # Router de autenticação database-backed (17 endpoints)
services/auth_service.py                # Serviço central de autenticação (~600 linhas)
database/CREATE_USER_AUTH_PREFS.sql     # Schema das tabelas de auth (3 tabelas)
templates/watcherdb_control.html        # Painel de controlo administrativo
static/vendor/                          # Assets de terceiros servidos localmente
tests/SECURITY_AUDIT_REPORT.md          # Relatório de auditoria (93 findings)
tests/performance/                      # Scripts Locust (4 cenários + runner)
prompts/prompt_watcherdb_testing_guide.md  # Guia de testes com IA generativa
```

**Modificações significativas em ficheiros partilhados:**
```
templates/watcherdb_portal.html     # Auth UI + persistência de sessão + custom queries per-user + assets locais
api/routers/intelligence_kpis.py    # Classificação de jobs por tipo (10 categorias)
watcherdb_main.py                   # Carregamento auth_compat + rota /watcherdb/control
```
