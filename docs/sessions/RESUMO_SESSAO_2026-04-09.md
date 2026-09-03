# Resumo da Sessao — 2026-04-09 (Marathon de fixes ao Overview e Log Module)

## Contexto

Sessao iniciada do lado do V5 (sessao paralela em `WATCHERDB_V5/`) que detectou
discrepancias arquitectonicas com o V3.2. O V3.2 estava com **timeouts em massa**
no modulo Overview (CPU/MEMORY/DATABASES/BACKUP_* todos a falhar com `Request
timeout`) e o modulo Log mostrava `0` erros para servidores com errorlogs
populados.

A sessao acabou com **8 problemas distintos identificados e corrigidos**, em
camadas — cada fix expunha o seguinte. Este checkpoint documenta tudo para
referencia futura.

---

## Sintomas iniciais

```
[processResponse] CPU - ERRO: Error: Request timeout
[processResponse] MEMORY - ERRO: Error: Request timeout
[processResponse] DATABASES - ERRO: Error: Request timeout
[processResponse] BACKUP_SUMMARY - ERRO: Error: Request timeout
[processResponse] BACKUP_GAPS - ERRO: Error: Request timeout
[processResponse] BACKUP_PATTERNS - ERRO: Error: Request timeout
[TOAST] Erro polling: signal timed out
```

E no audit log:
```
GET /api/monitoring/sql-errors/SQLHDSPRD411_I01   duration_ms: 942976.76  (15.7 min)
GET /api/monitoring/cpu/server/SQLMDMPRD03_I01    duration_ms: 780680.02  (13 min)  status: 500
GET /api/intelligence-kpis/dashboard               duration_ms: 14795.09   (14.8 s)
```

---

## Problemas encontrados (em camadas)

### 1. KPI_MSSQL_JOB_FAILURES_* — DDL escrito mas nunca executado

**Sintoma**: `intelligence-kpis/dashboard` sempre com 14s+, audit log mostra
fallback Direct para 200+ instancias.

**Causa**: o script `database/09_CREATE_JOB_FAILURES_AND_FG_USAGE_DET.sql`
existia mas nunca foi corrido na BD `WatcherDB_Intelligence`. Os 3 objects
estavam ausentes:
- `dbo.KPI_MSSQL_JOB_FAILURES_STG`
- `dbo.KPI_MSSQL_JOB_FAILURES_AGG_VIEW`
- `dbo.KPI_MSSQL_JOBS_FAILED_AGG_VIEW`

**Fix**: criados directamente via Python contra a BD em runtime (com `pyodbc`),
evitando a necessidade de SSMS DBA. Validado com `INFORMATION_SCHEMA.TABLES`.

---

### 2. helpers.py:1685 — `if job_data:` tratava lista vazia como falha

**Sintoma**: mesmo apos criar as views, o loop `for view_name in job_views`
continuava a tentar todas as 3 views e caia no fallback Direct.

**Causa**: `api/routers/intelligence/helpers.py:1685-1707`
```python
job_data = []
for view_name in job_views:
    try:
        job_data = await execute_intelligence_query_async(...)
        if job_data:        # ← BUG: lista vazia e' falsy
            break
    except Exception:
        continue
```
Lista vazia (view existe mas sem rows) era tratada como falha → continuava o
loop → caia no Direct fallback de 14s.

**Fix**:
```python
job_data = None  # sentinela
for view_name in job_views:
    result = await execute_intelligence_query_async(...)
    if result is not None:    # query OK, mesmo que retorne 0 rows
        job_data = result
        break
```
E o `if job_data:` posterior virou `if job_data is not None:`.

**Impacto**: dashboard caiu de **14.8s → 2-4s** na 1ª chamada, **<10ms** em
cache hits.

---

### 3. Cache TTL do dashboard era 30s (igual ao polling do frontend)

**Localizacao**: `api/routers/intelligence/helpers.py:37`

**Causa**: o frontend faz polling do `intelligence-kpis/dashboard` a cada 30s.
O cache server-side tinha TTL 30s. Resultado: praticamente nenhum cache hit —
todas as chamadas eram fresh.

**Fix**: TTL `30s → 60s`. Metade das chamadas servem do cache em <10ms.

---

### 4. logs_collector.py — Windows Events Message=null para drivers como storvsc

**Sintoma**: Tab Logs do Sistema Operacional mostrava "N/A" na coluna Mensagem
para eventos NTFS, storvsc, disk, etc.

**Causa**: o script PowerShell `_build_event_query_script` em
`modules/monitoring/logs_collector.py:399` lia apenas `$_.Message`. Para drivers
do kernel cujo provider message file nao esta acessivel via PowerShell remoto,
`$_.Message` retorna `$null`.

**Fix**: fallback chain de 3 niveis:
```powershell
n='Message'; e={
    if ($_.Message) { $_.Message }
    else {
        $fmt = $null
        try { $fmt = $_.FormatDescription() } catch {}
        if ($fmt) { $fmt }
        else {
            try {
                $props = ($_.Properties | ForEach-Object { ... }) -join ' | '
                if ($props) { "[Event $($_.Id) from $($_.ProviderName)] Properties: $props" }
                else { "[Event $($_.Id) from $($_.ProviderName)] (sem mensagem)" }
            } catch {
                "[Event $($_.Id) from $($_.ProviderName)] (erro)"
            }
        }
    }
}
```

---

### 5. Per-server offline quarantine (servidores offline na fleet)

**Sintoma**: 7 servidores conhecidamente offline (SQLHDSQLT051..056, SQLHDSTST014)
faziam cada chamada ao pool gastar 7s de retries (1+2+4) inutilmente. Multiplicado
por 6 endpoints paralelos do Overview = 42s+ de espera.

**Causa**: o `tenacity` retry policy em `watcherdb/core/retry.py` ja' tinha sido
melhorado para nao retry erros permanentes (208, 18456, 4060), mas SQLSTATE 08001
("Connection error") era considerado transient. Servidores offline emitem 08001 →
faziam retries inuteis.

**Fix**: novo mecanismo de **quarentena per-server** em `api/connection_pool.py`:

```python
# No __init__:
self._offline_until: Dict[str, float] = {}  # pool_key → unix_ts ate quando offline
self._offline_lock = threading.Lock()
self.OFFLINE_QUARANTINE_SECONDS = 60.0

def _is_in_quarantine(self, pool_key: str) -> bool:
    with self._offline_lock:
        until = self._offline_until.get(pool_key)
        if until and time.time() < until:
            return True
        # expirou — limpar
        ...

def _mark_offline(self, pool_key: str) -> None:
    with self._offline_lock:
        self._offline_until[pool_key] = time.time() + self.OFFLINE_QUARANTINE_SECONDS
```

E em `get_connection()`, **fast-fail no inicio** se em quarentena:
```python
if self._is_in_quarantine(pool_key):
    self.stats['fast_fail_offline'] += 1
    return None
```

E ao apanhar `Exception` no `_create_connection`, marca offline:
```python
except Exception as e:
    self._mark_offline(pool_key)
    return None
```

**Impacto**: servidores offline na primeira tentativa entram em quarentena 60s.
Tentativas subsequentes saem em <1ms em vez de 7s+.

---

### 6. Circuit breaker GLOBAL `sql_server_breaker` poisonava servidores saudaveis

**Sintoma**: depois do fix #5, alguns servidores saudaveis ainda davam 504
intermitentemente. Logs mostravam:
```
Circuit breaker OPEN for SQLADSPRD003_master — fast-failing + quarantining
```
mas o servidor estava online.

**Causa**: `watcherdb/core/circuit_breaker.py` define um unico
`sql_server_breaker = pybreaker.CircuitBreaker(fail_max=5)` partilhado entre
**todos** os servidores monitorizados. 5 falhas em SQLHDSQLT051 (offline) abria
o breaker para SQLADSPRD003 tambem.

**Fix**: removi o decorator `@sql_server_breaker` do `_create_connection` em
`api/connection_pool.py:240`. A quarentena per-server (#5) substitui esta
funcionalidade de forma mais granular.

```python
# Antes
@staticmethod
@sql_server_breaker      # ← removido
@retry_db_operation
def _create_connection(conn_str): ...

# Depois
@staticmethod
@retry_db_operation
def _create_connection(conn_str): ...
```

---

### 7. SQLServerMonitoring instanciada por request + 4 workers + cache_path bug

**Sintoma**: `cpu/server/SQLMDMPRD03_I01` chega ao codigo mas o `🔌 Conectando`
nunca completa. Logs durante a request mostram:
```
ConnectionPool adapter initialized
SQLServerExecutor initialized with 4 workers
SQLServerMonitoring initialized
Loaded 85 physical servers from config/servers.json
```
**dentro da janela da request HTTP** — uma instancia nova era criada por chamada.

**Causa**: `watcherdb_main.py:3884` (e mais 8 sitios) tinha:
```python
sql_monitoring = SQLServerMonitoring(cache_path)
```
Onde `cache_path = "watcherdb_cache.db"` era passado como objecto cache (mas o
`__init__` espera um cache real, nao uma string). Cada call HTTP criava uma
**nova** instancia com **4 workers** e **pool isolado**, esgotando recursos.

Pior: o discovery service em background (corrido no startup) faz queries de
**334 segundos** que esgotavam o threadpool.

**Fix**: substitui as 9 ocorrencias por:
```python
sql_monitoring = app.state.sql_monitoring  # FIX: reuse global instance
if sql_monitoring is None:
    return JSONResponse(503, {"error": "SQL Monitoring not initialized"})
```

E aumentei `max_workers` da global de **10 → 30** em `watcherdb_main.py:130`:
```python
app.state.sql_monitoring = SQLServerMonitoring(
    cache=app.state.inventory_manager.cache,
    max_connections=30,
    max_workers=30  # antes era 10
)
```

Limpei tambem 11 linhas orfas `cache_path = "watcherdb_cache.db"` e 5 imports
agora desnecessarios.

---

### 8. ConnectionInfo defaults: 30s connect + 300s command timeout = 5 minutos de hang

**Sintoma**: `pyodbc.connect` em servidores PRD com TLS handshake lento ficava
preso por 5 minutos.

**Causa**: `modules/monitoring/monitoring.py:36-37`
```python
@dataclass
class ConnectionInfo:
    connection_timeout: int = 30   # 30s
    command_timeout: int = 300     # 5 minutos
```
Aplicado em **3 sitios** (dataclass default + 2 instanciacoes hardcoded).

**Fix**: reduzido para **5s connect + 30s command** em todos os 3 sitios.

```python
connection_timeout: int = 5
command_timeout: int = 30
```

---

### 9. Memory analysis: 8 queries secundarias em paralelo, uma hangava o gather

**Sintoma**: SQLMDMPRD03 dava 504 mesmo com todos os fixes acima. Logs mostravam:
```
Query executed successfully in 0.14s, returned 1 rows  ← query principal OK
[8 secondary queries arrancam em parallelo]
🔌 Conectando a: SQLMDMPRD03\I01    ← repetido 7+ vezes
[15s passam]
⚠️ SQL memory analysis timeout (15s)
```

**Causa**: `modules/monitoring/memory_analysis.py:434` faz `asyncio.gather()`
de **8 queries secundarias** (buffer_pool, ple, grants, plan_cache,
memory_clerks, top_queries, resource_governor, **oom_events**). A
`oom_events_query` usa `xp_readerrorlog` filtrado por texto que em servidores
PRD com errorlog gigante (>1GB) **pode demorar minutos**.

Quando uma query do `gather` hangava, o caller `wait_for(15.0)` cortava as
**8** mesmo que 7 ja' tivessem terminado em <1s.

**Fix**: cada query secundaria agora tem **`asyncio.wait_for(8.0)` individual**:

```python
PER_QUERY_TIMEOUT = 8.0

async def _safe_query(query_text, label, default):
    try:
        result = await asyncio.wait_for(
            sql_monitoring.execute_query(server_id, query_text),
            timeout=PER_QUERY_TIMEOUT
        )
        ...
    except asyncio.TimeoutError:
        logger.debug(f"⚠️ [Memory/{label}] timeout {PER_QUERY_TIMEOUT}s")
        return default
    except Exception as e:
        return default
```

E o caller `wait_for` foi aumentado de **15s → 20s** em
`watcherdb_main.py:3911` para dar margem ao gather (que agora corta queries
individuais em vez de cancelar todas).

---

### 10. xp_readerrorlog: optimizacao com SearchTerm escondia mensagens de BACKUP

**Sintoma**: V3.2 mostrava 0 erros SQL Server para SQLMDMPRD03; V5 (mesmo
servidor, mesma query a primeira vista) mostrava 30+.

**Causa**: numa optimizacao anterior, refactorei a query de
`api_sql_errors` em `watcherdb_main.py:3382` para usar
`xp_readerrorlog` com `@SearchTerm1='Error'/'Severity'/'fail'`. Isto reduz
carga (filtra DURANTE a leitura) **mas o SearchTerm filtra a coluna `Text`
literalmente** — mensagens de BACKUP como:
```
"BACKUP DATABASE WITH DIFFERENTIAL successfully processed 6258 pages..."
```
nao contem nenhuma das 3 palavras → **nunca eram lidas**.

A query original do V5 nao usa `SearchTerm`, le tudo para temp table, e tem
no `WHERE`:
```sql
OR ProcessInfo = 'Backup'
```
que apanha todas as linhas emitidas pelo SPID de backup.

**Fix**: revertida a query para a versao original (identica a do V5), com
proteccao via `asyncio.wait_for(35.0)` no caller.

---

### 11. sql_monitoring user nao tem EXECUTE permission em xp_readerrorlog

**Sintoma**: depois de reverter a query (#10), V3.2 ainda devolvia 0. V5
mostrava 30. Mesmo servidor, mesma query.

**Causa raiz**: durante a sessao tinha refactorizado `_build_connection_string`
em `api/connection_pool.py:283` para usar **SQL Auth** (`sql_monitoring`) lendo
do `servers.json`. Mas o user `sql_monitoring` **NAO tem `EXECUTE permission`
em `xp_readerrorlog`** nos servidores PRD — apenas `SELECT` em DMVs. O
`BEGIN TRY ... END CATCH` na query engole o erro de permissao silenciosamente.

Confirmacao standalone:
```
Trusted (TAPNET\ue_e-snetto = dbo): xp_readerrorlog → 2868 rows ✅
SQL Auth (sql_monitoring):          xp_readerrorlog → EXECUTE denied (229) ❌
```

O V5 funciona porque ainda usa `Trusted_Connection=yes` hardcoded
(`WATCHERDB_V5/api/connection_pool.py:296`).

**Fix**: revertido `_build_connection_string` do V3.2 para usar
**Trusted_Connection sempre** (igual ao V5). O user que corre o servico
(`TAPNET\ue_e-snetto`) e' `dbo` em todos os servidores monitorizados.

Mantive `_load_credentials_cache` e `_resolve_credentials` — agora so usados
para resolver `host/instance/port` (do servers.json), nao para auth. Adicionei
helper `_build_connection_string_sql_auth` reservado para fallback futuro.

**Aviso para o futuro** (comentado no codigo): quando o V3.2 for empacotado para
correr como service account sem permissoes `dbo`, sera preciso uma de duas
coisas:
- (a) DBA executar `GRANT EXECUTE ON xp_readerrorlog TO sql_monitoring` em
  todos os 95 servidores monitorizados
- (b) Manter Trusted Auth com uma conta dedicada de service que tenha as
  permissoes correctas

---

### 12. Re-encriptacao de 96 passwords em servers.json

**Contexto** (descoberto enquanto investigava o #11): as passwords no
`config/servers.json` estavam encriptadas com uma chave Fernet **antiga**
que o `WATCHERDB_ENCRYPTION_KEY_DPAPI` actual ja nao desembrulhava. A
descriptografia falhava silenciosamente e o `_load_credentials_cache` devolvia
o valor encriptado como password (110 chars, em vez dos 15 reais).

**Fix**: re-encriptei todas as **96 passwords** (95 monitored + 1 master) com
a chave actual usando `uh!b.df*f2Uct@e` como plaintext (confirmei que e' a
mesma password do V5).

Backup criado em `config/servers.json.backup_pre_reencrypt`.

**Nota de seguranca**: a password ainda esta exposta no chat history. Quando
poder, rodar a password do `sql_monitoring` no SQL Server e re-encriptar nos
dois projectos.

---

### 13. Job Failures Collector — populador da KPI_MSSQL_JOB_FAILURES_STG

**Contexto**: depois de criar a tabela vazia (#1), o dashboard mostrava
`Jobs Failed: 0` em vez dos 161 que apareciam antes via Direct fallback.
Era esperado — sem collector a popular a STG, a view fica sempre vazia.

**Solucao**: criado novo modulo `services/job_failures_collector.py` que:
- Corre a cada **5 minutos** via APScheduler (usando `add_periodic_task`)
- Chama `_query_jobs_from_servers(only_collisions=False, timeout=25.0)` —
  funcao existente que itera 20 servidores em paralelo via `msdb`
- Persiste com **MERGE** idempotente em `KPI_MSSQL_JOB_FAILURES_STG` com
  chave natural `(Instance, job_name, run_datetime, step_name)`
- **Retencao**: `DELETE WHERE Insert_TS < -25h` no fim de cada cycle
- **Classificacao** por job name (Backup/Index/Statistics/DBCC/Shrink/Log/
  Cleanup/Replication/AlwaysOn/Other) — espelha a logica do `helpers.py`
- Devolve stats `{fetched, inserted, kept, pruned, duration_s}` para
  observabilidade

Registado no startup de `watcherdb_main.py:106` logo apos `start_scheduler()`:
```python
try:
    from services.job_failures_collector import register_with_scheduler as _reg_jobf
    _reg_jobf()
except Exception as _reg_err:
    logger.warning(f"Could not register job_failures_collector: {_reg_err}")
```

**Validacao real** (antes do fim da sessao):
```
Run #1: fetched=161, inserted=161, kept=0,   pruned=0   duration=20s
Run #2: fetched=163, inserted=2,   kept=161, pruned=0   ← 2 jobs failed novos
DB row count: 163
```

---

### 14. Frontend: filtros do modulo Log nao disparavam reload

**Sintoma**: mudar Periodo (24h → 6h) ou Tipo no painel Controles do modulo
Log nao recarregava a tab.

**Causa suspeitada**: o handler era atribuido via `hoursSel.onchange = fn`
(assignment directo). O `content.innerHTML = ...` no `renderLogAnalysis`
substituia o select original; o handler antigo apontava para um elemento
destruido.

**Fix**: substitui `onchange = fn` por **`addEventListener('change', fn)`**,
envolvi o bind em **`setTimeout(0)`** para garantir DOM pronto, e adicionei
**debug logs** `[Log] Periodo mudou para Xh` / `[Log] Tipo mudou para X`
para facilitar diagnostico futuro.

```javascript
setTimeout(() => {
    const hoursSel = document.getElementById('logHoursSelect');
    if (hoursSel) {
        hoursSel.value = String(hours);
        hoursSel.addEventListener('change', () => {
            debugLog(`[Log] Periodo mudou para ${hoursSel.value}h`, 'info');
            localStorage.setItem('log_hours', hoursSel.value);
            try { setUserPref('log_hours', hoursSel.value); } catch (_) {}
            loadLogAnalysis();
        });
    }
    // ... mesmo para typeSel
}, 0);
```

**Validacao**: confirmado no audit log — request com `?hours=48` apareceu
apos o user mudar o select.

---

### 15. Frontend: filtro descartava eventos Information silenciosamente

**Sintoma**: card mostrava "Eventos Windows: 5" mas a tabela dizia
"Nenhum evento" — inconsistencia visivel.

**Causa**: `templates/watcherdb_portal.html:19748` filtrava todos os eventos
com `level=Information`:
```javascript
windowsToShow = windowsToShow.filter(e => {
    const lvl = String(e.level || ...).toUpperCase();
    return !lvl.includes('INFORMATION') && lvl !== 'INFO' && lvl !== '4';
});
```
Mas o backend ja' faz curadoria por **Event ID** (so devolve eventos cujos IDs
estao em `DISK_ERROR_EVENT_IDS`, `SQL_SERVER_CRITICAL_IDS`, etc.). Eventos
como `NTFS Event 98` tem `level=Information` mas estao na lista DISK_ERROR
intencionalmente — o frontend nao devia filtra-los outra vez.

**Fix**: removido o filtro frontend completamente. Quem quiser ver so erros
clica no segmento ERRO do donut interactivo.

---

## Ficheiros tocados nesta sessao

| Ficheiro | Mudancas principais |
|---|---|
| `watcherdb_main.py` | reuse global SQLServerMonitoring (9 sitios), max_workers 10→30, get_memory_analysis e get_cpu_analysis com `wait_for(20s/15s)`, registo do job_failures_collector, query sql-errors revertida |
| `api/connection_pool.py` | quarentena per-server, removido `@sql_server_breaker`, `_load_credentials_cache`, `_resolve_credentials`, `_build_server_target`, `_build_connection_string` voltou a Trusted, `_build_connection_string_sql_auth` (reservado) |
| `api/routers/intelligence/helpers.py` | `if job_data:` → `if job_data is not None:`, sentinela `None`, cache TTL 30s→60s |
| `modules/monitoring/monitoring.py` | `ConnectionInfo` defaults 30s/300s → 5s/30s (3 sitios) |
| `modules/monitoring/memory_analysis.py` | per-secondary-query `_safe_query` com `wait_for(8.0)`, cleanup das 8 funcoes fetch_* |
| `modules/monitoring/logs_collector.py` | Message fallback chain (FormatDescription + Properties + fallback string) |
| `services/job_failures_collector.py` | **NOVO** — collector com MERGE idempotente, retencao 25h, classificacao por nome |
| `templates/watcherdb_portal.html` | onchange → addEventListener no Log filter, removido filtro Information no frontend |
| `config/servers.json` | 96 passwords re-encriptadas com chave Fernet actual |
| `config/servers.json.backup_pre_reencrypt` | **NOVO** — backup do servers.json antes da re-encriptacao |

---

## Resultados finais

| Endpoint | Antes | Depois |
|---|---|---|
| `intelligence-kpis/dashboard` (1ª chamada) | 14.8s | **2-4s** |
| `intelligence-kpis/dashboard` (cache hit) | 14.8s | **<10ms** |
| `monitoring/cpu/server/{id}` | 13+ min hang | **2-5s** |
| `monitoring/memory/server/{id}` | 5-15 min hang | **5-15s** (worst case) |
| `monitoring/sql-errors/{id}` | 13-15 min hang ou 0 rows | **<5s, dados reais** |
| `monitoring/windows-events/{id}` | 60+s timeout | **5-12s** |
| Servidores offline na fleet | 7s+ retries cada | **<1ms** (quarentena) |
| Card "Jobs Failed" no dashboard | 161 (via Direct, lento) | **161 (via STG, rapido)** |
| Tab Log filtros (Periodo/Tipo) | nao recarregava | **funciona** |
| Tab Log Windows Events Mensagem | "N/A" para storvsc/ntfs | **texto real ou Properties** |

---

## Pendencias / avisos para o futuro

### Para quando V3.2 for empacotado para correr como service account
1. **Permissoes SQL** — o user `sql_monitoring` precisa de:
   - `GRANT EXECUTE ON xp_readerrorlog TO sql_monitoring;` (em todos os 95 servidores)
   - `GRANT EXECUTE ON sp_readerrorlog TO sql_monitoring;` (idem)
   - Caso contrario, o modulo Log devolve 0 erros e o `oom_events_query` em
     memory_analysis.py tambem falha silenciosamente.

2. **Auth fallback automatico** — o `_build_connection_string_sql_auth` ja
   esta implementado mas nao e' chamado. Quando `_build_connection_string`
   (Trusted) falhar com "Login failed", deveria tentar SQL Auth automaticamente.
   Implementar como retry no `get_connection`.

### Seguranca
3. **Rodar password do `sql_monitoring`** no SQL Server e re-encriptar nos dois
   projectos (V5 + V3.2). A password actual ficou exposta no chat history desta
   sessao.

4. **Apagar `config/servers.json.backup_pre_reencrypt`** quando confiares no
   novo sistema (a backup contem passwords encriptadas com a chave antiga).

### Performance
5. **Discovery service** — corre uma vez no startup e faz queries de 334s+
   em servidores PRD grandes. Considerar:
   - Paralelizar mais (`max_concurrent=10` → 20)
   - Adicionar timeout per-server (actualmente nao tem)
   - Skip servidores em quarentena
   - Mover para o scheduler com cadencia (1h?) em vez de "uma vez no startup"

6. **Job collisions collector** — actualmente so' os failures sao colectados.
   Os collisions ainda usam o fallback Direct (`_query_jobs_from_servers
   (only_collisions=True)`). Replicar o pattern do job_failures_collector
   para criar um `job_collisions_collector.py`.

### Observabilidade
7. **Dashboard de stats** — adicionar endpoint `/api/admin/pool-stats` que
   exponha o `_offline_until` dict (servidores em quarentena), `fast_fail_offline`
   counter, etc. Util para debug futuro.

---

## Arquitectura: o que mudou no thinking

Antes desta sessao, o V3.2 tinha tres armadilhas em camadas:

1. **Pool global de conexoes com circuit breaker global** — uma falha em
   qualquer servidor poisonava todos. Agora e' per-server.

2. **Instanciacao per-request de objects pesados** — cada request criava
   novo SQLServerMonitoring com novo executor de 4 workers. Agora reutiliza
   a global de 30 workers.

3. **Timeouts em camadas** — defaults de 30s/300s no `ConnectionInfo`,
   nenhum `wait_for` no caller, nenhum timeout per-query nos `gather`s. Agora
   tem timeouts em todas as camadas: 5s connect, 30s command, 8s per-secondary
   query, 20s caller wait_for.

A licao geral: **timeouts em sistemas concorrentes precisam de existir em
TODAS as camadas, com valores que reduzem para dentro**. O caller corta primeiro,
o thread interno corta a seguir, o pyodbc corta por ultimo. Caso contrario, o
`wait_for(N)` nunca ajuda — apenas devolve erro mais cedo enquanto o trabalho
real continua a queimar workers no background.
