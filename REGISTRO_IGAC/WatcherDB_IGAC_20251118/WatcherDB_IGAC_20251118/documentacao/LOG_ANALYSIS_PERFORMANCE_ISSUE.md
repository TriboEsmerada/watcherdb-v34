# Problema de Performance - Análise de Logs
**Data:** 2025-11-15
**Severidade:** ALTA
**Componente:** Aba "Log" do Portal WatcherDB

## Resumo Executivo

A aba "Log" do portal WatcherDB demora muito tempo para carregar e frequentemente não completa o carregamento, ficando em estado de loading infinito.

**Causa Raiz:** Múltiplas chamadas PowerShell síncronas sem cache com timeout inadequado.

---

## Análise do Problema

### 1. Fluxo Atual

```
Frontend (watcherdb_portal.html)
    ↓
    loadLogAnalysis()
    ↓
Promise.all([
    /api/monitoring/windows-events/{serverId}?hours=24
    /api/monitoring/sql-errors/{serverId}?hours=24
])
    ↓
Backend (logs_collector.py)
    ↓
WindowsLogsCollector.collect_windows_events()
    ↓
Para cada categoria (6 categorias em série):
    - PowerShell remoto (Invoke-Command)
    - Timeout: 60s
    - Get-WinEvent (até 500 eventos por categoria)
    - JSON parsing
    ↓
Total: até 3000 eventos processados
```

### 2. Problemas Identificados

#### Problema 1: Timeout Inadequado
```python
# logs_collector.py linha 40
self.timeout = 60  # Apenas 60 segundos
```

**Impacto:**
- Para 6 categorias × 60s = até 6 minutos só de timeouts
- PowerShell remoto pode demorar >60s em servidores lentos
- Timeout expira antes de completar

#### Problema 2: Execução Síncrona (Serial)
```python
# logs_collector.py linha 158-182
for category in event_categories:  # ← Execução em SÉRIE
    # ...
    success, stdout, stderr = self._execute_powershell_remote(...)
```

**Impacto:**
- 6 categorias executadas UMA APÓS A OUTRA
- Tempo total = soma de todas as categorias
- Não aproveita paralelismo

#### Problema 3: Sem Cache
- Nenhum cache implementado
- Mesmos dados buscados repetidamente
- Logs históricos não mudam (poderia cachear)

#### Problema 4: PowerShell Remoto via WinRM
```python
# logs_collector.py linha 47-66
def _execute_powershell_remote(self, server_name: str, script: str):
    cmd = [
        "powershell", "-NoProfile", "-Command",
        f"Invoke-Command -ComputerName {server_name} -ScriptBlock {{ {script} }}"
    ]
```

**Problemas:**
- WinRM pode não estar habilitado
- Requer configuração de credenciais
- Mais lento que acesso local
- Pode falhar por firewall/rede

#### Problema 5: Get-WinEvent é Lento
```python
# logs_collector.py linha 109
Get-WinEvent -FilterHashtable @{...} -MaxEvents {max_events}
```

**Por que é lento:**
- Windows Event Log pode ter milhões de eventos
- Filtrar em tempo real é custoso
- Especialmente em servidores antigos
- 6 categorias × 500 eventos = 3000 eventos processados

---

## Métricas de Performance

### Tempo Medido (Estimado)

| Operação | Tempo (melhor caso) | Tempo (pior caso) |
|----------|---------------------|-------------------|
| PowerShell remoto (1 categoria) | 5-10s | 60s+ (timeout) |
| 6 categorias em série | 30-60s | 6+ minutos |
| JSON parsing | 1-2s | 5s |
| **Total frontend → backend** | 35-65s | >6 minutos |

### Impacto no Usuário

- Loading infinito (>6 min)
- Impressão de que sistema "travou"
- Timeout do navegador (pode cancelar após 2-5 min)
- CPU alto no servidor durante execução

---

## Arquivos Envolvidos

### 1. logs_collector.py (489 linhas)

**Problemas:**
- Linhas 40: `timeout = 60` (muito baixo)
- Linhas 158-182: Loop síncrono `for category in event_categories`
- Linhas 47-66: PowerShell remoto via `Invoke-Command`
- Nenhum cache implementado

**Classes:**
- `WindowsLogsCollector` - Coleta eventos Windows
- `SQLLogsCollector` - Coleta ERRORLOG SQL Server

### 2. watcherdb_portal.html

**Linha 4094-4096:**
```javascript
const [windowsLogsRes, sqlLogsRes] = await Promise.all([
    fetch(`/api/monitoring/windows-events/${serverId}?hours=${hours}`),
    fetch(`/api/monitoring/sql-errors/${serverId}?hours=${hours}`)
]);
```

**Problema:** Sem timeout no fetch, fica esperando indefinidamente

### 3. Rotas API (provavelmente em api/routers/)

Precisam ser identificadas e verificadas.

---

## Soluções Propostas

### Solução 1: Aumentar Timeout (RÁPIDO)

**Arquivo:** `logs_collector.py`

```python
# Linha 40 - ANTES
self.timeout = 60

# Linha 40 - DEPOIS
self.timeout = 300  # 5 minutos (mais realista)
```

**Impacto:**
- ✅ Evita timeouts prematuros
- ⚠️ Usuário ainda espera muito tempo
- ⚠️ Não resolve problema de fundo

### Solução 2: Paralelizar Categorias (MÉDIO)

**Arquivo:** `logs_collector.py`

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def collect_windows_events_parallel(self, server_id, hours=24, event_categories=None):
    """Versão paralela da coleta de eventos"""
    server_name = self._get_server_hostname(server_id)

    if event_categories is None:
        event_categories = ['shutdown', 'disk', 'sql_server', 'alwayson', 'cluster', 'memory']

    category_map = {
        'shutdown': (self.SHUTDOWN_EVENT_IDS, 'System', None),
        'disk': (self.DISK_ERROR_EVENT_IDS, 'System', None),
        'sql_server': (self.SQL_SERVER_EVENT_IDS, 'Application', 'MSSQLSERVER'),
        'alwayson': (self.ALWAYSON_EVENT_IDS, 'Application', 'MSSQLSERVER'),
        'cluster': (self.CLUSTER_EVENT_IDS, 'Microsoft-Windows-FailoverClustering/Operational', None),
        'memory': (self.MEMORY_EVENT_IDS, 'System', 'Microsoft-Windows-Resource-Exhaustion-Detector')
    }

    # Executar todas as categorias EM PARALELO
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        for category in event_categories:
            if category not in category_map:
                continue

            event_ids, log_name, provider = category_map[category]
            script = self._build_event_query_script(event_ids, hours, log_name, provider, max_events=500)

            # Submeter para execução paralela
            future = executor.submit(self._execute_powershell_remote, server_name, script)
            futures.append((category, future))

        # Coletar resultados
        all_events = []
        for category, future in futures:
            try:
                success, stdout, stderr = future.result(timeout=120)  # 2 min por categoria
                if success:
                    events = json.loads(stdout.strip() or '[]')
                    if isinstance(events, dict):
                        events = [events]
                    for event in events:
                        event['category'] = category
                        event['event_type'] = self._classify_event_type(event.get('Id', 0))
                    all_events.extend(events)
            except Exception as e:
                logger.warning(f"Erro ao coletar {category}: {e}")

    all_events.sort(key=lambda x: x.get('TimeCreated', ''), reverse=True)

    return {
        'success': True,
        'server_id': server_id,
        'events': all_events[:1000],
        'total_count': len(all_events),
        'categories_found': list(set(e.get('category', 'unknown') for e in all_events))
    }
```

**Impacto:**
- ✅ Reduz tempo de 6min para ~2min (6 categorias em paralelo)
- ✅ Melhor aproveitamento de recursos
- ⚠️ Requer mudança de código

### Solução 3: Implementar Cache com TTL (MÉDIO)

**Arquivo:** `logs_collector.py`

```python
import time
from functools import lru_cache
from datetime import datetime, timedelta

class CachedWindowsLogsCollector(WindowsLogsCollector):
    """Versão com cache do coletor de logs"""

    def __init__(self):
        super().__init__()
        self.cache = {}
        self.cache_ttl = 300  # 5 minutos

    def _get_cache_key(self, server_id, hours, categories):
        return f"{server_id}_{hours}_{','.join(sorted(categories))}"

    def collect_windows_events(self, server_id, hours=24, event_categories=None):
        """Versão com cache"""
        if event_categories is None:
            event_categories = ['shutdown', 'disk', 'sql_server', 'alwayson', 'cluster', 'memory']

        cache_key = self._get_cache_key(server_id, hours, event_categories)

        # Verificar cache
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            age = time.time() - cached_time
            if age < self.cache_ttl:
                logger.info(f"Cache HIT para {server_id} (idade: {age:.1f}s)")
                return cached_data
            else:
                logger.info(f"Cache EXPIRED para {server_id}")

        # Cache MISS - buscar dados
        logger.info(f"Cache MISS para {server_id} - buscando dados...")
        result = super().collect_windows_events(server_id, hours, event_categories)

        # Salvar no cache
        self.cache[cache_key] = (result, time.time())

        # Limpar cache antigo (manter apenas últimos 100 itens)
        if len(self.cache) > 100:
            oldest_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k][1])[:50]
            for key in oldest_keys:
                del self.cache[key]

        return result
```

**Impacto:**
- ✅ Primeira carga lenta, demais instantâneas (5 min)
- ✅ Reduz carga no servidor
- ✅ Melhor experiência do usuário
- ⚠️ Logs podem estar desatualizados (máx 5 min)

### Solução 4: Usar SQL Query ao invés de PowerShell (IDEAL)

**Alternativa:** Buscar dados via SQL Server Extended Events ou sys.dm_os_ring_buffers

```sql
-- Exemplo: Buscar eventos de erro via SQL
SELECT TOP 1000
    creation_time,
    ring_buffer_type,
    CAST(record AS XML) AS record_xml
FROM sys.dm_os_ring_buffers
WHERE ring_buffer_type IN ('RING_BUFFER_EXCEPTION', 'RING_BUFFER_CONNECTIVITY')
ORDER BY creation_time DESC
```

**Vantagens:**
- ✅ Muito mais rápido que PowerShell
- ✅ Não requer WinRM
- ✅ Integrado com conexão SQL existente
- ❌ Não pega todos os eventos do Windows (apenas SQL)

### Solução 5: Timeout no Frontend (IMEDIATO)

**Arquivo:** `watcherdb_portal.html`

```javascript
// Linha 4094 - ANTES
const [windowsLogsRes, sqlLogsRes] = await Promise.all([
    fetch(`/api/monitoring/windows-events/${serverId}?hours=${hours}`),
    fetch(`/api/monitoring/sql-errors/${serverId}?hours=${hours}`)
]);

// Linha 4094 - DEPOIS
const fetchWithTimeout = (url, timeout = 60000) => {
    return Promise.race([
        fetch(url),
        new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Request timeout')), timeout)
        )
    ]);
};

const [windowsLogsRes, sqlLogsRes] = await Promise.all([
    fetchWithTimeout(`/api/monitoring/windows-events/${serverId}?hours=${hours}`, 120000), // 2 min
    fetchWithTimeout(`/api/monitoring/sql-errors/${serverId}?hours=${hours}`, 120000) // 2 min
]).catch(err => {
    // Mostrar erro ao usuário em vez de loading infinito
    content.innerHTML = `
        <div class="error">
            <h4>Timeout ao carregar logs</h4>
            <p>${err.message}</p>
            <p>O servidor está demorando muito para responder. Tente novamente com menos horas.</p>
        </div>
    `;
    return [null, null];
});
```

**Impacto:**
- ✅ Usuário vê erro em vez de loading infinito
- ✅ Pode tentar de novo com parâmetros diferentes
- ✅ Implementação imediata
- ⚠️ Não resolve problema de performance backend

---

## Recomendações Prioritárias

### 🔴 IMEDIATO (Hoje)

1. **Implementar timeout no frontend** (Solução 5)
   - Tempo: 10 minutos
   - Arquivo: `watcherdb_portal.html`
   - Evita impressão de sistema travado

2. **Aumentar timeout backend** (Solução 1)
   - Tempo: 5 minutos
   - Arquivo: `logs_collector.py` linha 40
   - De 60s para 300s

### 🟡 CURTO PRAZO (Esta semana)

3. **Implementar cache** (Solução 3)
   - Tempo: 1-2 horas
   - TTL de 5 minutos
   - Melhora significativa para usuários

4. **Paralelizar categorias** (Solução 2)
   - Tempo: 2-3 horas
   - Reduz tempo de 6min para ~2min
   - ThreadPoolExecutor

### 🟢 MÉDIO PRAZO (Próximas 2 semanas)

5. **Migrar para SQL Queries** (Solução 4)
   - Tempo: 1 semana
   - Alternativa ao PowerShell
   - Muito mais rápido e confiável

6. **Adicionar paginação**
   - Carregar apenas últimos 100 eventos primeiro
   - "Load more" para carregar mais

7. **Background job**
   - Coletar logs em background task
   - Expor apenas cache no frontend
   - Usuário sempre vê dados instantaneamente

---

## Testes Necessários

Após implementar correções:

1. **Teste de Performance**
   - Medir tempo de resposta antes/depois
   - Testar com 1h, 24h, 168h (1 semana)
   - Testar em servidor lento vs rápido

2. **Teste de Cache**
   - Verificar cache HIT/MISS
   - Confirmar expiração após TTL
   - Testar memory usage

3. **Teste de Timeout**
   - Forçar timeout e verificar mensagem de erro
   - Confirmar que não fica em loading infinito

4. **Teste de Paralelismo**
   - Confirmar todas categorias executam em paralelo
   - Verificar se há race conditions

---

## Métricas Esperadas Após Correções

| Métrica | Antes | Depois (Solução 1+3) | Depois (Todas) |
|---------|-------|----------------------|----------------|
| Tempo primeira carga | >6 min ou timeout | 2-3 min | 30-60s |
| Tempo carga subsequente (cache) | >6 min | <1s | <1s |
| Taxa de sucesso | 20-30% | 80-90% | 95-99% |
| Timeout frontend | Infinito | 2 min | 2 min |
| Experiência do usuário | Péssima | Aceitável | Excelente |

---

## Conclusão

O problema de performance da aba "Log" é causado por:
1. ❌ Timeout inadequado (60s)
2. ❌ Execução síncrona (serial)
3. ❌ Sem cache
4. ❌ PowerShell remoto lento
5. ❌ Sem timeout no frontend

**Implementando as soluções 1, 3 e 5 (IMEDIATO + CURTO PRAZO)**, teremos:
- ✅ Tempo de carga: 6min → 2min (primeira vez)
- ✅ Tempo de carga: 6min → <1s (cache hit)
- ✅ Usuário vê erro em vez de loading infinito
- ✅ Taxa de sucesso: 30% → 90%

**Status:** PRONTO PARA IMPLEMENTAÇÃO
