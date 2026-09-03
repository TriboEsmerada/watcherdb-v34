# 📊 Modos de Coleta de KPIs

**Data:** 2025-01-XX  
**Sistema:** WatcherDB Intelligence  
**Endpoint:** `/api/v1/kpis/by-mode/{mode}`

---

## 🎯 Visão Geral

O sistema suporta diferentes modos de coleta de KPIs, permitindo otimizar a coleta de dados baseado na necessidade e frequência de atualização.

---

## 📋 Modos Disponíveis

### 1. `kpi-fast` - KPIs Rápidos (11 KPIs)

**Descrição:** KPIs leves e rápidos, coletados a cada 5 minutos.

**KPIs Incluídos:**
1. `blocked_sessions` - Sessões Bloqueadas
2. `blocked_users` - Usuários Bloqueados
3. `db_transaction_logs` - Logs de Transação (tlog_usage)
4. `always_on` - Always On (alwayson_status)
5. `instance_availability` - Disponibilidade de Instância
6. `processes_alarm` - Alarme de Processos (processes)
7. `db_availability` - Disponibilidade de Banco de Dados
8. `backup_status` - Status de Backup (backups)
9. `db_io_stats` - Estatísticas de I/O
10. `db_disk_file_system` - Uso de Disco (disk_usage)
11. `filegroup_usage` - Uso de FileGroups

**Características:**
- ✅ Coleta rápida (tempo médio: 50-320ms)
- ✅ Atualização frequente (a cada 5 minutos)
- ✅ Ideal para monitoramento em tempo real
- ✅ Baixo impacto no servidor

**Uso Recomendado:**
- Monitoramento contínuo
- Dashboards em tempo real
- Alertas imediatos

---

### 2. `kpi-only` - KPIs Completos (14 KPIs)

**Descrição:** Todos os KPIs do modo `kpi-fast` mais 3 KPIs adicionais que requerem mais tempo de coleta.

**KPIs Incluídos:**
- ✅ Todos os 11 KPIs do modo `kpi-fast`
- ✅ `lock_count` - Contagem de Locks (long_locks)
- ✅ `deadlocks` - Deadlocks
- ✅ `service_status` - Status de Serviços

**Características:**
- ⚠️ Inclui KPIs com queries mais lentas
- ⚠️ `lock_count`: ~15-18 segundos
- ⚠️ `deadlocks`: ~40 segundos
- ⚠️ `service_status`: ~90ms (mas tem problemas técnicos com DECLARE)

**Uso Recomendado:**
- Coleta completa de dados
- Análises detalhadas
- Relatórios completos

---

### 3. `locks-only` - Apenas Locks (2 KPIs)

**Descrição:** Modo especializado para monitorar apenas locks e deadlocks.

**KPIs Incluídos:**
1. `lock_count` - Contagem de Locks (long_locks)
2. `deadlocks` - Deadlocks

**Características:**
- ⚠️ Queries muito lentas (15-40 segundos)
- ⚠️ Não recomendado para coleta rápida
- ✅ Focado em problemas de concorrência

**Uso Recomendado:**
- Diagnóstico de problemas de locks
- Análise de deadlocks
- Troubleshooting de performance

---

### 4. `all` - Todos os KPIs

**Descrição:** Retorna todos os KPIs disponíveis no sistema.

**KPIs Incluídos:**
- Todos os KPIs definidos em `KPI_METADATA`
- Inclui todos os modos acima mais KPIs adicionais (se houver)

**Uso Recomendado:**
- Visão completa do sistema
- Desenvolvimento e testes
- Análises completas

---

## 🔧 Implementação Técnica

### Estrutura de Dados

```python
KPI_MODES = {
    'kpi-fast': [
        'blocked_sessions',
        'blocked_users',
        'db_transaction_logs',
        'always_on',
        'instance_availability',
        'processes_alarm',
        'db_availability',
        'backup_status',
        'db_io_stats',
        'db_disk_file_system',
        'filegroup_usage'
    ],
    'kpi-only': [
        # Todos os 11 do kpi-fast
        'blocked_sessions',
        'blocked_users',
        'db_transaction_logs',
        'always_on',
        'instance_availability',
        'processes_alarm',
        'db_availability',
        'backup_status',
        'db_io_stats',
        'db_disk_file_system',
        'filegroup_usage',
        # Mais 3 adicionais
        'lock_count',
        'deadlocks',
        'service_status'
    ],
    'locks-only': [
        'lock_count',
        'deadlocks'
    ]
}
```

### Endpoint

```http
GET /api/v1/kpis/by-mode/{mode}
```

**Parâmetros:**
- `mode`: `kpi-fast`, `kpi-only`, `locks-only`, ou `all`

**Resposta:**
```json
{
    "mode": "kpi-fast",
    "count": 11,
    "kpis": [
        {
            "name": "blocked_sessions",
            "display_name": "Sessões Bloqueadas",
            "category": "real_time",
            "avg_duration_ms": 60.0,
            "is_fast": true,
            "collection_interval_minutes": 5,
            "last_collection_time": "2025-01-XXT10:30:00",
            "last_update": "2025-01-XXT10:33:00"
        },
        ...
    ],
    "timestamp": "2025-01-XXT10:33:00"
}
```

---

## 📊 Comparação de Modos

| Modo | Total KPIs | Tempo Médio | Frequência | Uso |
|------|-----------|-------------|------------|-----|
| `kpi-fast` | 11 | 50-320ms | 5 min | ⚡ Monitoramento em tempo real |
| `kpi-only` | 14 | 50-40000ms | 15 min | 📊 Coleta completa |
| `locks-only` | 2 | 15000-40000ms | Sob demanda | 🔒 Diagnóstico de locks |
| `all` | Todos | Variável | Variável | 🔍 Visão completa |

---

## 🎯 Recomendações de Uso

### Para Monitoramento Contínuo
```python
# Usar kpi-fast para atualizações frequentes
GET /api/v1/kpis/by-mode/kpi-fast
```

### Para Coleta Completa
```python
# Usar kpi-only para dados completos
GET /api/v1/kpis/by-mode/kpi-only
```

### Para Diagnóstico de Locks
```python
# Usar locks-only quando necessário
GET /api/v1/kpis/by-mode/locks-only
```

### Para Desenvolvimento
```python
# Usar all para ver todos os KPIs
GET /api/v1/kpis/by-mode/all
```

---

## ⚠️ Notas Importantes

### KPIs Lentos

Alguns KPIs são intencionalmente excluídos do modo `kpi-fast` devido ao tempo de execução:

1. **`lock_count` (long_locks)**
   - Tempo médio: ~15 segundos
   - Query complexa que analisa locks de longa duração
   - Não recomendado para coleta rápida

2. **`deadlocks`**
   - Tempo médio: ~40 segundos
   - Query muito lenta que analisa deadlocks
   - Não recomendado para coleta rápida

3. **`service_status`**
   - Tempo médio: ~90ms
   - Tem problemas técnicos com DECLARE
   - Incluído apenas no modo `kpi-only`

### Mapeamento de Nomes

Alguns KPIs têm nomes diferentes na especificação vs. código:

| Especificação | Código |
|--------------|--------|
| `tlog_usage` | `db_transaction_logs` |
| `alwayson_status` | `always_on` |
| `processes` | `processes_alarm` |
| `backups` | `backup_status` |
| `disk_usage` | `db_disk_file_system` |
| `long_locks` | `lock_count` |

---

## 🔄 Histórico de Mudanças

### 2025-01-XX
- ✅ Adicionado modo `locks-only`
- ✅ Atualizado mapeamento explícito de KPIs por modo
- ✅ Documentação dos modos atualizada

---

**Documento gerado automaticamente**  
**Última atualização:** 2025-01-XX

