# Módulo de Windows Failover Cluster

## Visão Geral

Módulo dedicado para monitoramento e análise de **Windows Failover Cluster**, separado do módulo Always On.

### Por que um módulo separado?

- **Nem todos os servidores têm cluster**: Evita sobrecarga no Overview
- **Escopo diferente**: Always On = SQL Server AG / Cluster = Infraestrutura Windows
- **Uso sob demanda**: Só carrega quando necessário
- **Extensibilidade**: Permite adicionar recursos específicos de cluster sem impactar AG

---

## Arquitetura

### Arquivos

```
modules/monitoring/
  └── cluster_analysis.py          # Módulo principal de análise

api/routers/
  └── cluster.py                    # Endpoints FastAPI

watcherdb_main.py                   # Registra router de cluster
```

### Fluxo de Integração

```
┌─────────────────────────────────────────────────────────┐
│                    OVERVIEW (servidor)                   │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │    CPU     │  │   Memory   │  │  Services  │        │
│  └────────────┘  └────────────┘  └────────────┘        │
│                                                          │
│  ┌────────────────────────────────────────┐             │
│  │         Always On Card                 │             │
│  │  - AG Status                           │             │
│  │  - Replicas                            │             │
│  │                                        │             │
│  │  ⚠️ SE CONEXÃO SQL FALHAR:            │             │
│  │  └─> Cluster Fallback (via PS)        │◄───────┐    │
│  │      - AG Resources offline?          │        │    │
│  │      - Cluster events?                │        │    │
│  └────────────────────────────────────────┘        │    │
└─────────────────────────────────────────────────────┼────┘
                                                      │
                                                      │
┌─────────────────────────────────────────────────────┼────┐
│              ABA "CLUSTER" (opcional)               │    │
│                                                     │    │
│  ┌──────────────────────────────────────┐          │    │
│  │      Cluster Health                  │          │    │
│  │  - Cluster Name                      │          │    │
│  │  - Nodes (Up/Down)                   │◄─────────┘    │
│  │  - Resources (Online/Offline)        │               │
│  │  - Quorum Config                     │               │
│  └──────────────────────────────────────┘               │
│                                                          │
│  ┌──────────────────────────────────────┐               │
│  │      Cluster Events (24h)            │               │
│  │  - Critical: 2                       │               │
│  │  - Errors: 5                         │               │
│  │  - Warnings: 12                      │               │
│  └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. GET `/api/cluster/server/{server_name}/health`

**Descrição**: Obtém saúde do cluster (nodes, recursos, quorum)

**Resposta**:
```json
{
  "success": true,
  "cluster_available": true,
  "cluster_name": "SQLCDSPRD407",
  "cluster_domain": "tapnet.tap.pt",
  "nodes": [
    {
      "name": "SQLHDSPRD407",
      "state": "Up",
      "status_info": "Normal"
    },
    {
      "name": "SQLHDSPRD408",
      "state": "Down",
      "status_info": "Lost communication"
    }
  ],
  "resources": [
    {
      "name": "SQLAGSPRD407",
      "resource_type": "SQL Server Availability Group",
      "state": "Failed",
      "owner_group": "SQLAGSPRD407",
      "owner_node": "SQLHDSPRD407",
      "is_core": false
    }
  ],
  "ag_resources": [
    {
      "name": "SQLAGSPRD407",
      "state": "Failed",
      "owner_group": "SQLAGSPRD407",
      "owner_node": "SQLHDSPRD407"
    }
  ],
  "failed_resources": [
    {
      "name": "SQLAGSPRD407",
      "type": "SQL Server Availability Group",
      "state": "Failed",
      "owner_node": "SQLHDSPRD407",
      "issue": "Resource 'SQLAGSPRD407' is Failed (expected Online)"
    }
  ],
  "quorum": {
    "type": "NodeAndFileShareMajority",
    "resource": "File Share Witness"
  },
  "timestamp": "2026-01-14T12:30:45.123456"
}
```

**Timeout**: 10 segundos

---

### 2. GET `/api/cluster/server/{server_name}/events?hours=24`

**Descrição**: Obtém eventos recentes do Cluster Event Log

**Parâmetros**:
- `hours`: Últimas N horas (1-168, padrão 24)

**Resposta**:
```json
{
  "success": true,
  "events": [
    {
      "time": "2026-01-14 12:25:30",
      "level": "Error",
      "id": 1069,
      "message": "Cluster resource 'SQLAGSPRD407' of type 'SQL Server Availability Group' in clustered role 'SQLAGSPRD407' failed.",
      "provider": "Microsoft-Windows-FailoverClustering"
    }
  ],
  "critical_count": 1,
  "error_count": 3,
  "warning_count": 5
}
```

**Timeout**: 10 segundos

---

### 3. GET `/api/cluster/server/{server_name}/summary`

**Descrição**: Resumo completo (health + events)

**Resposta**:
```json
{
  "health": { /* objeto health completo */ },
  "events": { /* objeto events completo */ },
  "timestamp": "2026-01-14T12:30:45.123456"
}
```

---

## Uso no Código Python

### Verificar Cluster Health

```python
from modules.monitoring.cluster_analysis import check_cluster_health

# Verificar cluster
result = check_cluster_health('SQLHDSPRD407', timeout=10)

if result['success']:
    print(f"Cluster: {result['cluster_name']}")
    print(f"Nodes: {len(result['nodes'])}")
    print(f"Failed Resources: {len(result['failed_resources'])}")

    # Alertar se há problemas
    if result['failed_resources']:
        for issue in result['failed_resources']:
            print(f"⚠️ {issue['issue']}")
else:
    print(f"Erro: {result['error']}")
```

### Obter Eventos

```python
from modules.monitoring.cluster_analysis import get_cluster_events

# Últimas 24 horas
events = get_cluster_events('SQLHDSPRD407', hours=24, max_events=50)

if events['success']:
    print(f"Critical: {events['critical_count']}")
    print(f"Errors: {events['error_count']}")
    print(f"Warnings: {events['warning_count']}")

    for event in events['events'][:5]:  # Top 5
        print(f"{event['time']} [{event['level']}] {event['message']}")
```

---

## Integração com Always On

O módulo Always On usa o cluster module como **fallback** quando a conexão SQL falha:

### Antes (Conexão SQL OK)
```
/api/alwayson/server/SQLHDSPRD407_I01/overview
  └─> Conecta via pyodbc
  └─> Retorna: AG status, replicas, databases, sync health
```

### Depois (Conexão SQL Falhou)
```
/api/alwayson/server/SQLHDSPRD407_I01/overview
  └─> Conexão SQL falhou (SSPI error, timeout, etc.)
  └─> FALLBACK: check_cluster_health('SQLHDSPRD407')
  └─> Retorna:
      - AG info do inventory (nome, listener)
      - Cluster health (se disponível)
      - cluster_alert (se recursos offline)
```

**Exemplo de resposta com fallback**:
```json
{
  "is_alwayson": true,
  "ag_name": "SQLAGSPRD407",
  "listener": "SQLAGSPRD407\\I01",
  "role": "UNKNOWN",
  "synchronization_health": "UNKNOWN",
  "timeout": true,
  "error": "Cannot generate SSPI context",
  "warning": "Timeout: O servidor não respondeu a tempo...",

  "cluster_health": {
    "available": true,
    "cluster_name": "SQLCDSPRD407",
    "ag_resources_count": 1,
    "failed_resources_count": 1,
    "issues": [
      {
        "name": "SQLAGSPRD407",
        "type": "SQL Server Availability Group",
        "state": "Failed",
        "owner_node": "SQLHDSPRD407",
        "issue": "Resource 'SQLAGSPRD407' is Failed (expected Online)"
      }
    ]
  },

  "cluster_alert": {
    "severity": "CRITICAL",
    "message": "1 AG resource(s) com problema no cluster",
    "details": [
      "Resource 'SQLAGSPRD407' is Failed (expected Online)"
    ]
  }
}
```

---

## Requisitos

### PowerShell Remoting
- Precisa estar habilitado nos servidores cluster
- Usuário precisa ter permissões de cluster

### Comandos PowerShell Usados
- `Get-Cluster -Name <server>`
- `Get-ClusterNode -Cluster <server>`
- `Get-ClusterResource -Cluster <server>`
- `Get-ClusterQuorum -Cluster <server>`
- `Get-WinEvent -ComputerName <server> -LogName Microsoft-Windows-FailoverClustering/Operational`

### Timeout
- Health check: 10 segundos (configurable)
- Events: 10 segundos
- Fallback (Always On): 5 segundos (rápido para não atrasar Overview)

---

## Tratamento de Erros

### Cluster não disponível
```json
{
  "success": false,
  "cluster_available": false,
  "error": "PowerShell error: Access is denied",
  "message": "Não foi possível obter informações do cluster de SQLHDSPRD407"
}
```

### Timeout
```json
{
  "success": false,
  "cluster_available": false,
  "error": "PowerShell timeout (10s)"
}
```

### Servidor não é cluster
```json
{
  "success": false,
  "cluster_available": false,
  "error": "PowerShell error: Cluster SQLHDSPRD407 was not found"
}
```

---

## Performance

| Operação | Tempo Típico | Timeout |
|----------|--------------|---------|
| Health Check (cluster OK) | 2-4s | 10s |
| Health Check (cluster com problema) | 3-6s | 10s |
| Events (24h, ~50 eventos) | 1-3s | 10s |
| Fallback no Always On | 2-5s | 5s |

---

## Próximos Passos (Opcional)

1. **Frontend - Aba "Cluster"**
   - Dashboard visual de cluster health
   - Timeline de eventos
   - Mapa de nodes e recursos

2. **Alertas Proativos**
   - Monitorar cluster a cada N minutos
   - Notificar quando recursos ficam offline
   - Integrar com sistema de alertas

3. **Análise Preditiva**
   - Padrões de failover
   - Correlação entre eventos de cluster e AG
   - Histórico de disponibilidade

4. **Comandos Remotos** (cuidado!)
   - Start/Stop recursos (com confirmação)
   - Move recursos entre nodes
   - **Requer permissões elevadas**
