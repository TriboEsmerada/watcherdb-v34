# PROMPT: Módulo de Monitoramento de Transações Two-Phase Commit (2PC) para WatcherDB

## CONTEXTO DO PROJETO

### Sobre o WatcherDB
O **WatcherDB Intelligence** é uma plataforma de monitoramento de SQL Server desenvolvida internamente, composta por **DOIS PROJETOS SEPARADOS**:

| Projeto | Responsabilidade | Localização |
|---------|------------------|-------------|
| **WATCHERDB_DEV** | API Web (FastAPI, routers, endpoints, templates) | `...\WATCHERDB_DEV\` |
| **WATCHERDB INTELLIGENCE V1** | Database (tabelas, views, procedures, jobs) + Serviço de Coleta | `...\WATCHERDB INTELLIGENCE V1\` |

### Características Gerais
- **Stack tecnológico**: Python 3.11+, FastAPI, Uvicorn
- **Banco de dados**: SQL Server (metadados armazenados no database WatcherDB)
- **Servidores monitorados**: 95+ instâncias SQL Server (PRD, QA, DEV)

---

## LOCALIZAÇÃO DOS PROJETOS

### Projeto 1: WATCHERDB_DEV (API/Web)
```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV\
```

**Usar para:**
- Routers FastAPI
- Endpoints REST
- Modelos Pydantic (schemas)
- Templates HTML (dashboards)

**Estrutura:**
```
WATCHERDB_DEV/
├── watcherdb_main.py           # FastAPI app principal (7.9K linhas)
├── api/
│   ├── __init__.py
│   ├── health_router.py        # Exemplo de router existente
│   ├── servers_router.py       # Exemplo de router existente
│   ├── alerts_router.py        # Exemplo de router existente
│   └── ...                     # 15+ routers, 50+ endpoints
├── modules/
│   ├── __init__.py
│   └── ...                     # 22 módulos especializados
├── config/
│   └── sql_servers.json        # Lista de servidores monitorados
└── templates/
    └── *.html                  # Templates do portal web
```

---

### Projeto 2: WATCHERDB INTELLIGENCE V1 (Database + Coleta)
```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB INTELLIGENCE V1\
```

**Usar para:**
- Scripts SQL (CREATE TABLE, VIEW, PROCEDURE, FUNCTION)
- Jobs do SQL Agent
- Tabelas históricas
- Serviço de coleta (collector_service)

**Estrutura:**
```
WATCHERDB INTELLIGENCE V1/
├── services/
│   └── collector_service/          # Serviço Windows de coleta
│       ├── service.py              # Windows Service (800+ linhas)
│       ├── collectors_base.py      # Framework de coletores
│       ├── config.yaml             # Configuração do serviço
│       ├── install.py              # Gerenciamento do serviço
│       ├── collectors/             # Coletores específicos
│       │   ├── __init__.py
│       │   ├── backup_collector.py
│       │   ├── disk_collector.py
│       │   └── ...
│       └── logs/
├── database/
│   ├── tables/                     # Scripts de criação de tabelas
│   ├── views/                      # Scripts de criação de views
│   ├── procedures/                 # Stored procedures
│   ├── functions/                  # User-defined functions
│   └── jobs/                       # Scripts de SQL Agent Jobs
└── ...
```

---

## OBJETIVO

Criar um **módulo completo de monitoramento de Transações Distribuídas Two-Phase Commit (2PC)** para o WatcherDB, que permita:

1. **Detectar** transações 2PC ativas em todas as instâncias monitoradas
2. **Alertar** sobre transações "in-doubt" (que requerem intervenção manual)
3. **Histórico** de transações 2PC para análise de tendências
4. **Dashboard** com visão consolidada do status 2PC de todos os servidores
5. **Gerar comandos** de resolução (KILL WITH ROLLBACK/COMMIT)
6. **Verificar** status do MS DTC

---

## REQUISITOS TÉCNICOS

### 1. Estrutura de Arquivos a Criar

#### 📁 WATCHERDB INTELLIGENCE V1 (Database + Coleta)
```
WATCHERDB INTELLIGENCE V1/
├── database/
│   ├── tables/
│   │   └── Monitor_2PC_Tables.sql          # 🆕 Tabelas de monitoramento 2PC
│   ├── views/
│   │   └── vw_2PC_Status.sql               # 🆕 Views para dashboard
│   ├── procedures/
│   │   ├── usp_Collect_2PC_Transactions.sql   # 🆕 Procedure de coleta
│   │   ├── usp_Alert_2PC_Problems.sql         # 🆕 Procedure de alertas
│   │   └── usp_Cleanup_2PC_History.sql        # 🆕 Limpeza de histórico
│   └── jobs/
│       └── Job_Monitor_2PC.sql             # 🆕 SQL Agent Job (5 min)
└── services/
    └── collector_service/
        └── collectors/
            └── distributed_transactions_collector.py  # 🆕 Coletor Python
```

#### 📁 WATCHERDB_DEV (API/Web)
```
WATCHERDB_DEV/
├── api/
│   └── distributed_transactions_router.py   # 🆕 Router FastAPI
├── schemas/
│   └── distributed_transactions_schemas.py  # 🆕 Modelos Pydantic
└── templates/
    └── 2pc_dashboard.html                   # 🆕 Dashboard (opcional)
```

### 2. Tabelas SQL Server (database WatcherDB)

#### Tabela: `Monitor_2PC_Transactions`
```sql
CREATE TABLE dbo.Monitor_2PC_Transactions (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    collected_at DATETIME2 DEFAULT GETDATE(),
    server_name SYSNAME NOT NULL,
    transaction_id BIGINT,
    state_desc NVARCHAR(60),
    dtc_state_desc NVARCHAR(60),
    result_desc NVARCHAR(60),
    uow UNIQUEIDENTIFIER,                    -- Unit of Work (para KILL)
    session_id INT,
    login_name NVARCHAR(128),
    host_name NVARCHAR(128),
    program_name NVARCHAR(128),
    database_name NVARCHAR(128),
    transaction_begin_time DATETIME2,
    duration_seconds INT,
    locks_held INT,
    is_in_doubt BIT,                         -- Flag crítico!
    
    INDEX IX_CollectedAt (collected_at),
    INDEX IX_ServerName (server_name),
    INDEX IX_InDoubt (is_in_doubt) WHERE is_in_doubt = 1
);
```

#### Tabela: `Monitor_2PC_Alerts`
```sql
CREATE TABLE dbo.Monitor_2PC_Alerts (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    created_at DATETIME2 DEFAULT GETDATE(),
    server_name SYSNAME NOT NULL,
    alert_type NVARCHAR(50),                 -- 'IN_DOUBT', 'LONG_RUNNING', 'DTC_ERROR'
    alert_severity NVARCHAR(20),             -- 'CRITICAL', 'WARNING', 'INFO'
    transaction_id BIGINT,
    uow UNIQUEIDENTIFIER,
    details NVARCHAR(MAX),
    resolved_at DATETIME2 NULL,
    resolved_by NVARCHAR(128) NULL,
    resolution_action NVARCHAR(50) NULL,     -- 'ROLLBACK', 'COMMIT', 'AUTO_RESOLVED'
    
    INDEX IX_CreatedAt (created_at),
    INDEX IX_Unresolved (resolved_at) WHERE resolved_at IS NULL
);
```

#### Tabela: `Monitor_2PC_DTC_Status`
```sql
CREATE TABLE dbo.Monitor_2PC_DTC_Status (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    checked_at DATETIME2 DEFAULT GETDATE(),
    server_name SYSNAME NOT NULL,
    dtc_status NVARCHAR(20),                 -- 'RUNNING', 'STOPPED', 'ERROR'
    error_message NVARCHAR(MAX) NULL,
    
    INDEX IX_CheckedAt (checked_at)
);
```

### 3. Queries SQL para Coleta de Dados

> **⚠️ IMPORTANTE:** A DMV `sys.dm_tran_distributed_transactions` **NÃO EXISTE** no SQL Server on-premises!
> Use sempre `sys.dm_tran_locks` como método universal. Para SQL Server 2022+, existe a DMV
> `sys.dm_tran_distributed_transaction_stats` com estatísticas adicionais.

#### Query 1: Coletar Transações Distribuídas (MÉTODO UNIVERSAL - SQL 2012+)
```sql
-- Esta query funciona em TODAS as versões do SQL Server
SELECT 
    @@SERVERNAME AS server_name,
    l.request_owner_guid AS uow,
    DB_NAME(l.resource_database_id) AS database_name,
    COUNT(*) AS locks_held,
    MAX(l.resource_type) AS resource_type,
    MAX(l.request_mode) AS request_mode,
    MAX(l.request_status) AS request_status,
    1 AS is_in_doubt  -- Se existe em dm_tran_locks com DISTRIBUTED_TRANSACTION, é in-doubt
FROM sys.dm_tran_locks l
WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
GROUP BY l.request_owner_guid, l.resource_database_id;
```

#### Query 2: Transações In-Doubt com Comandos de Resolução
```sql
-- NOTA: Esta query fornece comandos KILL prontos para uso
SELECT 
    @@SERVERNAME AS server_name,
    l.request_owner_guid AS uow,
    DB_NAME(l.resource_database_id) AS database_name,
    COUNT(*) AS locks_count,
    MAX(l.resource_type) AS resource_type,
    MAX(l.request_mode) AS request_mode,
    'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
    'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
FROM sys.dm_tran_locks l
WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
GROUP BY l.request_owner_guid, l.resource_database_id;
```

#### Query 3: Verificar Status do MS DTC
```sql
BEGIN TRY
    BEGIN DISTRIBUTED TRANSACTION;
    ROLLBACK;
    SELECT 'RUNNING' AS dtc_status, NULL AS error_message;
END TRY
BEGIN CATCH
    SELECT 'ERROR' AS dtc_status, ERROR_MESSAGE() AS error_message;
END CATCH
```

#### Query 4: Resumo Consolidado por Servidor (MÉTODO UNIVERSAL)
```sql
-- Contagem de transações distribuídas pendentes
SELECT 
    @@SERVERNAME AS server_name,
    GETDATE() AS checked_at,
    COUNT(DISTINCT l.request_owner_guid) AS in_doubt_count,
    COUNT(*) AS total_locks,
    CASE WHEN COUNT(*) > 0 THEN 'CRITICAL' ELSE 'OK' END AS status
FROM sys.dm_tran_locks l
WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION';
```

#### Query 5: Estatísticas Avançadas (APENAS SQL Server 2022+)
```sql
-- NOTA: Esta DMV só existe em SQL Server 2022 ou superior
-- Verificar versão antes de executar: IF CAST(PARSENAME(@@VERSION, 4) AS INT) >= 16
SELECT 
    @@SERVERNAME AS server_name,
    [open] AS open_transactions,
    in_doubt AS in_doubt_count,
    committed AS committed_count,
    aborted AS aborted_count,
    forced_commit AS forced_commit_count,
    forced_abort AS forced_abort_count,
    in_doubt_max,
    [open_max]
FROM sys.dm_tran_distributed_transaction_stats;
```

### 4. Endpoints FastAPI (Router)

O router deve implementar os seguintes endpoints:

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/2pc/status` | Status consolidado de todos os servidores |
| GET | `/api/2pc/status/{server_name}` | Status de um servidor específico |
| GET | `/api/2pc/transactions` | Lista todas as transações 2PC ativas |
| GET | `/api/2pc/transactions/{server_name}` | Transações de um servidor específico |
| GET | `/api/2pc/in-doubt` | Lista transações in-doubt (CRÍTICO) |
| GET | `/api/2pc/in-doubt/{server_name}` | Transações in-doubt de um servidor |
| GET | `/api/2pc/history` | Histórico de transações (últimas 24h) |
| GET | `/api/2pc/history/{server_name}` | Histórico de um servidor |
| GET | `/api/2pc/dtc-status` | Status do MS DTC em todos os servidores |
| GET | `/api/2pc/dtc-status/{server_name}` | Status do MS DTC de um servidor |
| GET | `/api/2pc/alerts` | Alertas ativos não resolvidos |
| POST | `/api/2pc/alerts/{alert_id}/resolve` | Marcar alerta como resolvido |
| GET | `/api/2pc/commands/{server_name}` | Gerar comandos de resolução |

### 5. Modelos Pydantic (Schemas)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID

class Transaction2PCBase(BaseModel):
    server_name: str
    transaction_id: int
    state_desc: str
    dtc_state_desc: Optional[str]
    uow: Optional[UUID]
    session_id: Optional[int]
    login_name: Optional[str]
    host_name: Optional[str]
    database_name: Optional[str]
    duration_seconds: int
    locks_held: int
    is_in_doubt: bool

class Transaction2PCDetail(Transaction2PCBase):
    program_name: Optional[str]
    transaction_begin_time: Optional[datetime]
    cmd_rollback: Optional[str]
    cmd_commit: Optional[str]

class ServerStatus2PC(BaseModel):
    server_name: str
    checked_at: datetime
    total_distributed_transactions: int
    active_count: int
    in_doubt_count: int
    committed_count: int
    aborted_count: int
    oldest_duration_minutes: Optional[int]
    alert_status: str  # 'OK', 'WARNING', 'CRITICAL'
    dtc_status: str    # 'RUNNING', 'STOPPED', 'ERROR', 'UNKNOWN'

class ConsolidatedStatus2PC(BaseModel):
    checked_at: datetime
    total_servers: int
    servers_with_issues: int
    total_in_doubt: int
    servers: List[ServerStatus2PC]

class Alert2PC(BaseModel):
    id: int
    created_at: datetime
    server_name: str
    alert_type: str
    alert_severity: str
    transaction_id: Optional[int]
    uow: Optional[UUID]
    details: str
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]
    resolution_action: Optional[str]

class ResolutionCommand(BaseModel):
    server_name: str
    uow: UUID
    database_name: str
    locks_held: int
    cmd_rollback: str
    cmd_commit: str
```

### 6. Configuração de Alertas (Thresholds)

```python
# Configurações de threshold para alertas
ALERT_CONFIG = {
    "in_doubt": {
        "threshold": 0,           # > 0 transações in-doubt = CRITICAL
        "severity": "CRITICAL"
    },
    "long_running": {
        "threshold_minutes": 30,  # > 30 minutos = WARNING
        "severity": "WARNING"
    },
    "high_volume": {
        "threshold_count": 10,    # > 10 transações ativas = WARNING
        "severity": "WARNING"
    },
    "dtc_error": {
        "severity": "CRITICAL"
    }
}
```

### 7. Módulo de Coleta (Collector)

O módulo de coleta deve:

1. **Executar periodicamente** (configurável, default 5 minutos)
2. **Iterar** por todos os servidores em `sql_servers.json`
3. **Coletar** dados usando as queries fornecidas
4. **Armazenar** no banco WatcherDB
5. **Gerar alertas** quando thresholds forem excedidos
6. **Verificar** status do MS DTC periodicamente

```python
# Estrutura sugerida do módulo
class DistributedTransactionsMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.alert_config = ALERT_CONFIG
    
    async def collect_all_servers(self) -> List[ServerStatus2PC]:
        """Coleta dados de todos os servidores"""
        pass
    
    async def collect_server(self, server_name: str) -> ServerStatus2PC:
        """Coleta dados de um servidor específico"""
        pass
    
    async def get_in_doubt_transactions(self, server_name: str = None) -> List[Transaction2PCDetail]:
        """Retorna transações in-doubt"""
        pass
    
    async def check_dtc_status(self, server_name: str) -> dict:
        """Verifica status do MS DTC"""
        pass
    
    async def generate_resolution_commands(self, server_name: str) -> List[ResolutionCommand]:
        """Gera comandos para resolver transações pendentes"""
        pass
    
    async def evaluate_alerts(self, status: ServerStatus2PC) -> List[Alert2PC]:
        """Avalia se deve gerar alertas baseado nos thresholds"""
        pass
```

---

## PADRÕES A SEGUIR

### Padrão de Código Existente

Seguir o padrão já utilizado nos módulos existentes do WatcherDB:

1. **Conexão com banco**: Usar o helper de conexão existente em `watcherdb_main.py`
2. **Logging**: Usar o padrão de logging já configurado
3. **Tratamento de erros**: Try/except com logging apropriado
4. **Async**: Usar async/await para operações de I/O
5. **Type hints**: Usar type hints em todas as funções
6. **Docstrings**: Documentar todas as funções públicas

### Padrão de Router FastAPI

```python
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

router = APIRouter(
    prefix="/api/2pc",
    tags=["Two-Phase Commit Monitoring"],
    responses={404: {"description": "Not found"}}
)

@router.get("/status", response_model=ConsolidatedStatus2PC)
async def get_consolidated_status():
    """
    Retorna status consolidado de transações 2PC de todos os servidores.
    
    - **total_servers**: Número total de servidores monitorados
    - **servers_with_issues**: Servidores com transações in-doubt
    - **total_in_doubt**: Total de transações in-doubt
    """
    pass
```

---

## ENTREGÁVEIS ESPERADOS

### 📁 Para WATCHERDB INTELLIGENCE V1 (Database + Coleta)

1. **`database/tables/Monitor_2PC_Tables.sql`**
   - Criação das tabelas: `Monitor_2PC_Transactions`, `Monitor_2PC_Alerts`, `Monitor_2PC_DTC_Status`
   - Índices otimizados

2. **`database/views/vw_2PC_Status.sql`**
   - View consolidada para dashboard
   - View de alertas ativos

3. **`database/procedures/*.sql`**
   - `usp_Collect_2PC_Transactions` - Coleta de dados
   - `usp_Alert_2PC_Problems` - Geração de alertas
   - `usp_Cleanup_2PC_History` - Limpeza (retenção 30 dias)

4. **`database/jobs/Job_Monitor_2PC.sql`**
   - SQL Agent Job para execução a cada 5 minutos

5. **`services/collector_service/collectors/distributed_transactions_collector.py`**
   - Classe coletora seguindo o padrão `collectors_base.py`
   - Integração com o `service.py` existente

---

### 📁 Para WATCHERDB_DEV (API/Web)

1. **`api/distributed_transactions_router.py`**
   - Router FastAPI completo com todos os endpoints
   - Documentação OpenAPI

2. **`schemas/distributed_transactions_schemas.py`**
   - Modelos Pydantic (schemas de request/response)

3. **`templates/2pc_dashboard.html`** (opcional)
   - Dashboard visual para o portal web

4. **Instruções de integração**
   - Como registrar o router no `watcherdb_main.py`
   - Como configurar os thresholds de alerta

---

## CRITÉRIOS DE QUALIDADE

- [ ] Código segue PEP 8
- [ ] Todas as funções têm type hints
- [ ] Todas as funções públicas têm docstrings
- [ ] Tratamento de erros robusto
- [ ] Logging apropriado
- [ ] Queries SQL otimizadas com índices
- [ ] Endpoints documentados para Swagger/OpenAPI
- [ ] Sem hardcode de credenciais ou strings de conexão

---

## NOTAS ADICIONAIS

### Sobre o Two-Phase Commit (2PC)
- O 2PC é acionado **automaticamente** quando há transações via Linked Server
- Transações "in-doubt" (state_desc = 'PREPARED') são **CRÍTICAS** e requerem intervenção
- O MS DTC (Distributed Transaction Coordinator) é o coordenador no SQL Server
- Comandos de resolução: `KILL 'UOW' WITH ROLLBACK` ou `KILL 'UOW' WITH COMMIT`

### Integração com WatcherDB Existente

**No WATCHERDB INTELLIGENCE V1:**
- Verificar o padrão do `collectors_base.py` para criar o novo coletor
- Usar o mesmo `config.yaml` do collector_service
- Seguir o padrão de logging existente
- Integrar com o sistema de alertas existente (se houver)

**No WATCHERDB_DEV:**
- Registrar o router no `watcherdb_main.py`
- Usar o mesmo padrão de conexão com banco dos outros routers
- Seguir o padrão de autenticação existente

---

## ⚠️ IMPORTANTE: SEPARAÇÃO DOS PROMPTS

Este prompt deve ser **dividido em DOIS prompts separados** ao executar:

1. **Prompt para WATCHERDB INTELLIGENCE V1** (executar primeiro):
   - Criar tabelas, views, procedures, jobs
   - Criar o coletor Python
   
2. **Prompt para WATCHERDB_DEV** (executar depois):
   - Criar router FastAPI
   - Criar schemas Pydantic
   - Criar dashboard (opcional)

---

*Prompt versão 1.1 - Módulo de Monitoramento 2PC para WatcherDB (Arquitetura Separada)*
