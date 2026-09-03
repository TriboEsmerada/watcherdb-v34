# Prompt: Melhorias WatcherDB V3.2 (07/04/2026)

## Resumo
Correcções de bugs no filtro de ambiente, session restore, autenticação AD, desactivação de users, auto-refresh, roles simplificadas, e BD migrada para novo servidor.

---

## 1. FILTRO DE AMBIENTE — CORRECÇÕES

### Bug: Valores errados quando "Todos Ambientes" seleccionado
- **Causa:** `sumEnv()` com `envs=null` somava TODOS os valores do dict `by_environment` incluindo a key `TOTAL` (que já era uma soma)
- **Fix:** Quando `ALL` seleccionado, chama `renderDashboardCards()` para re-renderizar com valores originais em vez de recalcular
- **Ficheiro:** `templates/watcherdb_portal.html` — função `filterKPIsByEnv()`

### Bug: DB Not Availability mostrava 893 em vez de 0 com filtro PRD
- **Causa:** Os 3 cards de Disponibilidade usavam o mesmo campo `by_environment`
- **Fix:** 
  - `db-availability-abnormal` — removido do filtro (sem breakdown por env, mantém valor original)
  - `db-availability-total` — usa `db_availability.by_environment` (databases por env)
  - `db-availability-ok` — usa `instance_availability.ok_by_env` (INSTÂNCIAS, não databases)
- **Ficheiro:** `templates/watcherdb_portal.html` — `cardUpdates` no `filterKPIsByEnv()`

### Bug: Instances OK mostrava número de databases em vez de instâncias
- **Causa:** Card `db-availability-ok` mapeado para `db_availability.by_environment` (databases) em vez de `instance_availability.ok_by_env` (instâncias)
- **Fix:** Alterado mapeamento para `instance_availability.ok_by_env`

### Bug: Filtro resetava após auto-refresh do dashboard
- **Causa:** `renderDashboardCardsContent()` reconstruía todo o HTML, dropdown voltava ao default
- **Fix:** Após `contentElement.innerHTML = html`, restaurar o dropdown e reaplicar o filtro:
```javascript
const savedEnvFilter = window._kpiEnvFilter || localStorage.getItem('kpi-env-filter') || 'ALL';
const envSelect = document.getElementById('kpiEnvFilter');
if (envSelect) envSelect.value = savedEnvFilter;
if (savedEnvFilter !== 'ALL') {
    setTimeout(() => filterKPIsByEnv(savedEnvFilter), 50);
}
```

### IDs de cards correctos no filtro (27 total)
```
db-availability-total, db-availability-ok, instance-availability-off,
instance-availability-ok, service-down, server-offline,
blocked-sessions, blocked-users, processes-alarm, cpu-critical, memory-critical,
transaction-logs-critical, transaction-logs-warning,
filegroup-usage-critical, filegroup-usage-warning,
disk-file-system-critical, disk-file-system-warning, disk-latency-critical,
tempdb-critical, tempdb-warning,
backup-failed, backup-delayed, jobs-failed, jobs-collisions,
always-on-unhealthy, mirroring-unhealthy
```

---

## 2. SESSION RESTORE — FIX DEFINITIVO

### Bug: Portal abria no último servidor/tab em vez dos KPIs
- **Causa:** `restoreUserSession()` era chamado em **2 locais** — linha 4160 (login flow) e linha 5296 (loadServers callback). O segundo sobrepunha o check do primeiro.
- **Fix:** Removido o segundo call (linha 5296). Só existe 1 local que restaura sessão (login flow) com check `_isPageReload`.

### Comportamento actual:
- **F5:** Restaura sessão anterior (servidor + tab)
- **Navegação directa (digitar URL / bookmark):** Abre nos KPIs
- **Ctrl+Shift+R:** Abre nos KPIs

---

## 3. AUTENTICAÇÃO AD — LOGIN COM EMAIL

### Aceita username OU email
- **Antes:** Só aceitava `ue_e-snetto`
- **Depois:** Aceita `ue_e-snetto` OU `ue_e-snetto@tapnet.tap.pt`
- **Lógica:** Se o input contém `@`, extrai a parte antes do `@`

### Fix UPN no LDAP bind
- **Antes:** UPN usava `AD_SERVER` (hostname do DC): `ue_e-snetto@dchqprd01.tapnet.tap.pt`
- **Depois:** UPN usa `AD_DOMAIN` (domínio): `ue_e-snetto@tapnet.tap.pt`
- **Ficheiro:** `services/auth_service.py` — `_authenticate_ldap()`

### User AD na BD
- User `ue_e-snetto` actualizado: `password_hash = 'ad_auth:tapnet.tap.pt'`
- Login usa credenciais Windows (password AD) via LDAP bind

---

## 4. DESACTIVAR USER TERMINA SESSÃO

### Antes
- Toggle disabled apenas marcava na BD
- User continuava online e a usar o portal

### Depois
- Ao desactivar: remove do `_online_heartbeats` (desaparece de "Online Agora")
- Em cada request autenticado: `_require_auth` verifica se user foi desactivado na BD
- Se desactivado: retorna 401 "Conta desactivada" — frontend redireciona para login

### Ficheiros alterados
- `api/routers/auth_compat.py`:
  - `toggle_user()` — remove heartbeat ao desactivar
  - `_require_auth()` — verifica `disabled` na BD em cada request

---

## 5. ROLES SIMPLIFICADAS

### Antes: 4 roles
- admin, analyst, operator, viewer

### Depois: 2 roles
- **admin** — acesso total (portal + Control Panel + gestão)
- **viewer** — só leitura (portal apenas)

### Ficheiros alterados (10+)
- `api/routers/auth_compat.py` — validação `("admin", "viewer")`
- `services/auth_service.py` — validação
- `watcherdb/core/auth.py` — `UserRole` enum (removidos ANALYST, OPERATOR)
- `templates/watcherdb_control.html` — dropdowns (removidas opções analyst/operator)
- `templates/watcherdb_control_v2.html` — idem
- `services/web_service/config.yaml` — comentário actualizado
- `watcherdb/api/auth_router.py` — documentação

---

## 6. AUTO-REFRESH NO CONTROL PANEL

### Utilizadores
- Refresh automático a cada **10 segundos** enquanto tab activa
- Actualiza: tabela de users, stats, online dots

### Sessões Activas
- Refresh automático a cada **10 segundos** enquanto tab activa
- Actualiza: Online Agora + Sessões Recentes 24h

### Implementação
- `setTimeout(loadUsers, 10000)` no final de `loadUsers()`
- `setTimeout(loadSessions, 10000)` no final de `loadSessions()`
- Ambos verificam `classList.contains('active')` — param ao sair da tab

---

## 7. BD MIGRADA PARA NOVO SERVIDOR

### Antes: SQLHDSTST212\I01 (MSSQL 2022)
### Depois: SQLHDSTST505\I01 (MSSQL 2025)

### Ficheiros alterados (30+)
- `watcherdb/core/settings.py` — default `intelligence_server`
- `alembic/env.py` — default server
- `api/routers/intelligence/helpers.py` — fallback server
- `api/routers/intelligence_kpis.py` — fallback server
- `api/routers/overview_dashboard.py` — fallback server
- `config/servers.json`, `config/sql_servers.json` — server entries
- `database/INSTALACAO_COMPLETA_UNIFICADA.sql` — deploy script
- `services/os_performance_service.py` — fallback server
- `modules/monitoring/service_monitor.py` — connection string
- `scripts/filegroup_interactive_report_v5_watcherdb.py` — server
- `docs/` (14 ficheiros) — referências documentação
- `tests/integration/` (2 ficheiros) — test server

---

## 8. PORTA DO SERVIÇO

### Histórico de portas
| Versão | Porta |
|--------|:-----:|
| V3.0 | 8443 |
| V3.1 | 8445 |
| V3.2 (inicial) | 8446 |
| V3.2 (2a mudança) | 8449 |
| V3.2 (actual) | **8432** |

---

## 9. OUTROS FIXES

### Bug: "queries is not defined" nas Queries Customizadas
- **Causa:** Linha 39145 usava variável `queries` (de outro scope) em vez de `userQueries`
- **Fix:** `queries.forEach(...)` → `userQueries.forEach(...)`
- **Ficheiro:** `templates/watcherdb_portal.html`

### Bug: Diagnóstico de query bloqueava UPDATE/INSERT
- **Causa:** `validate_query()` aplicado ao endpoint diagnose-query que NÃO executa a query
- **Fix:** Removida validação — endpoint apenas extrai nomes de tabelas para análise de estatísticas
- **Ficheiro:** `api/routers/queries/_diagnostics_legacy.py`

### TempDB modal: Expandir + Download HTML
- Botões adicionados ao header do modal "Análise de Crescimento TempDB"
- `toggleTempDBModalSize()` — alterna normal ↔ fullscreen
- `downloadTempDBModalHTML()` — exporta como .html com dark theme
- **Ficheiro:** `templates/watcherdb_portal.html`

### Rename: "Dashboard de KPIs" → "KPIs"
- 25+ ficheiros actualizados (portal, i18n PT/EN/ES, docs)
- Botão no header agora diz "KPIs" em vez de "Dashboard de KPIs"

### KPI Dashboard: colectas em paralelo
- `asyncio.gather()` para 14 colectas simultâneas (Phase 1) + 3 dependentes (Phase 2)
- Reduz tempo de ~20s para ~5-8s no primeiro load
- **Ficheiro:** `api/routers/intelligence_kpis.py`

---

## 10. ESTADO FINAL

| Métrica | Valor |
|---------|------:|
| Testes | 360 passed, 0 failed |
| Porta serviço | 8432 |
| BD Intelligence | SQLHDSTST505\I01 |
| Roles | 2 (admin, viewer) |
| Auto-refresh Control | 10s (users + sessions) |
| Filtro ambiente | 27 cards, persistente |
| Login AD | username OU email aceites |

---

*Sessão 07/04/2026 | WatcherDB V3.2*
