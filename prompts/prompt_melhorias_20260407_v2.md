# Prompt: Melhorias WatcherDB V3.2 — Performance Multi-User (07/04/2026 v2)

## Contexto
Múltiplos utilizadores começaram a testar o sistema simultaneamente, causando lentidão generalizada. O uvicorn corre com 1 worker (requisito Windows Service) e as queries pyodbc são bloqueantes — uma query de 15s bloqueava todas as outras.

---

## 1. PERFORMANCE — THREAD POOLS AUMENTADOS

### Problema
- KPIs Dashboard: ~15s (14 colectas à Intelligence DB)
- Jobs endpoint: TIMEOUT >90s (queries pesadas ao SQL Server)
- Heartbeat: 65s (devia ser <1s) — servidor congestionado
- Resources: TIMEOUT — bloqueado por queries anteriores
- Utilizadores simultâneos bloqueavam-se mutuamente

### Solução: Aumentar thread pools

| Componente | Antes | Depois | Ficheiro |
|-----------|:-----:|:------:|----------|
| Default asyncio executor | ~8 (Python default) | **40** | `watcherdb_main.py` lifespan |
| Intelligence helpers executor | 10 | **20** | `api/routers/intelligence/helpers.py:29` |
| Intelligence KPIs executor | 10 | **20** | `api/routers/intelligence_kpis.py:32` |

### Código (watcherdb_main.py — lifespan startup)
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
loop = asyncio.get_event_loop()
loop.set_default_executor(ThreadPoolExecutor(max_workers=40))
logger.info("Default executor set to 40 threads (multi-user support)")
```

### Impacto
- 40 threads permitem ~40 queries SQL simultâneas
- Múltiplos utilizadores não se bloqueiam
- Dashboard carrega em paralelo real (14 colectas × 20 workers)

---

## 2. JOBS ENDPOINT — TIMEOUT ADICIONADO

### Problema
- Endpoint `/api/jobs/server/{server_id}` sem timeout
- Queries ao msdb podiam demorar >90s se servidor SQL estivesse lento
- Bloqueava o worker inteiro

### Solução
```python
cursor.execute("SET LOCK_TIMEOUT 15000")  # 15s max wait for locks
conn.timeout = 30  # 30s max per query
```

### Ficheiro
`api/routers/jobs.py` — após `get_pooled_connection()`, antes da primeira query

---

## 3. FILTRO AMBIENTE — CORRECÇÃO INSTANCES OK

### Problema
Card "Instances OK" mostrava número de databases (893) em vez de instâncias (45) quando filtro PRD activo.

### Causa
Card `db-availability-ok` mapeado para `db_availability.by_environment` (databases) em vez de `instance_availability.ok_by_env` (instâncias).

### Fix
```javascript
// ANTES (errado):
'db-availability-ok': sumEnv(data.db_availability?.by_environment),

// DEPOIS (correcto):
'db-availability-ok': sumEnv(data.instance_availability?.ok_by_env),
```

### Mapeamento correcto dos 3 cards de Disponibilidade
| Card | Campo API | O que mostra |
|------|-----------|-------------|
| DB Not Availability | (sem filtro — mantém original) | DBs offline |
| DB Availability | `db_availability.by_environment` | DBs OK por ambiente |
| Instances OK | `instance_availability.ok_by_env` | Instâncias SQL OK por ambiente |

---

## 4. FILTRO AMBIENTE — PERSISTÊNCIA APÓS AUTO-REFRESH

### Problema
Quando o dashboard fazia auto-refresh (a cada 30s), o HTML era reconstruído e o dropdown voltava a "Todos Ambientes".

### Solução
Após `contentElement.innerHTML = html`, restaurar o filtro guardado:

```javascript
const savedEnvFilter = window._kpiEnvFilter || localStorage.getItem('kpi-env-filter') || 'ALL';
const envSelect = document.getElementById('kpiEnvFilter');
if (envSelect) envSelect.value = savedEnvFilter;
if (savedEnvFilter !== 'ALL') {
    setTimeout(() => filterKPIsByEnv(savedEnvFilter), 50);
}
```

### Ficheiro
`templates/watcherdb_portal.html` — dentro de `renderDashboardCardsContent()`, após `contentElement.innerHTML = html`

---

## 5. FILTRO AMBIENTE — FIX "TODOS AMBIENTES"

### Problema
Quando "Todos Ambientes" seleccionado, `sumEnv()` com `envs=null` somava TODOS os valores do dict incluindo a key `TOTAL`, inflando os números.

### Solução
Quando `ALL` seleccionado, re-renderiza o dashboard com valores originais em vez de recalcular:

```javascript
if (envFilter === 'ALL') {
    if (typeof renderDashboardCards === 'function') {
        renderDashboardCards();
    }
    showToast('Filtro: Todos', 'info');
    return;
}
```

---

## 6. FICHEIROS ALTERADOS

| Ficheiro | Alteração |
|----------|-----------|
| `watcherdb_main.py` | Default executor 40 threads no lifespan |
| `api/routers/intelligence/helpers.py` | ThreadPool 10→20 |
| `api/routers/intelligence_kpis.py` | ThreadPool 10→20 |
| `api/routers/jobs.py` | SET LOCK_TIMEOUT 15s + conn.timeout 30s |
| `templates/watcherdb_portal.html` | Fix Instances OK, fix filtro ALL, persistência filtro |

---

## 7. BENCHMARK ESPERADO APÓS FIXES

| Endpoint | Antes | Depois (esperado) |
|----------|:-----:|:------------------:|
| KPIs Dashboard (cold) | 15-20s | ~8-12s |
| KPIs Dashboard (cache hit) | 11ms | 11ms |
| Jobs analysis | >90s TIMEOUT | <30s (com timeout) |
| Heartbeat | 65s (congestionado) | <1s |
| Resources | TIMEOUT | <3s |
| Requests simultâneos | 1 de cada vez | **40 em paralelo** |

---

*07/04/2026 v2 | WatcherDB V3.2 — Performance Multi-User*
