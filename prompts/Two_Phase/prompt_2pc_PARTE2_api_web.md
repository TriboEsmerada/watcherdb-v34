# PROMPT: Módulo 2PC - PARTE 2: API + Web
## Projeto: WATCHERDB_DEV

---

## CONTEXTO

Estou no projeto **WATCHERDB_DEV** localizado em:
```
C:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV\
```

Este projeto é responsável por:
- FastAPI application (Web Service)
- Routers e endpoints REST
- Templates HTML (dashboards)
- Exposição de dados via HTTPS

**Estrutura atual relevante:**
```
WATCHERDB_DEV/
├── watcherdb_main.py               # FastAPI app principal (7.9K linhas)
├── api/
│   ├── __init__.py
│   ├── health_router.py            # Exemplo de router
│   ├── servers_router.py           # Exemplo de router
│   ├── alerts_router.py            # Exemplo de router
│   └── ...                         # 15+ routers existentes
├── modules/
│   └── ...
├── templates/
│   └── *.html
└── static/
    └── ...
```

**Pré-requisito:** As tabelas e procedures já foram criadas no projeto **WATCHERDB INTELLIGENCE V1**:
- `Monitor_2PC_Transactions`
- `Monitor_2PC_Alerts`
- `Monitor_2PC_DTC_Status`
- `vw_2PC_Current_Status`
- `vw_2PC_Active_Alerts`
- `vw_2PC_InDoubt_Transactions`

---

## OBJETIVO

Criar a **API REST** para expor os dados de monitoramento de **Transações Distribuídas Two-Phase Commit (2PC)** via endpoints FastAPI.

### O que é 2PC?
- Protocolo para garantir atomicidade em transações distribuídas (via Linked Server)
- Transações "in-doubt" (`state_desc = 'PREPARED'`) são **CRÍTICAS** e requerem intervenção manual
- Comando de resolução: `KILL 'UOW' WITH ROLLBACK` ou `KILL 'UOW' WITH COMMIT`

---

## ENTREGÁVEIS

### 1. Router FastAPI
**Arquivo:** `api/distributed_transactions_router.py`

```python
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime
from uuid import UUID

# Importar schemas (criar arquivo separado)
from schemas.distributed_transactions_schemas import (
    Transaction2PC,
    Transaction2PCDetail,
    ServerStatus2PC,
    ConsolidatedStatus2PC,
    Alert2PC,
    AlertResolveRequest,
    ResolutionCommand,
    DTCStatus
)

router = APIRouter(
    prefix="/api/2pc",
    tags=["Two-Phase Commit Monitoring"],
    responses={404: {"description": "Not found"}}
)
```

**Endpoints a implementar:**

| Método | Endpoint | Response Model | Descrição |
|--------|----------|----------------|-----------|
| GET | `/status` | `ConsolidatedStatus2PC` | Status consolidado de todos os servidores |
| GET | `/status/{server_name}` | `ServerStatus2PC` | Status de um servidor específico |
| GET | `/transactions` | `List[Transaction2PC]` | Todas as transações 2PC ativas |
| GET | `/transactions/{server_name}` | `List[Transaction2PC]` | Transações de um servidor |
| GET | `/in-doubt` | `List[Transaction2PCDetail]` | Transações in-doubt (CRÍTICO!) |
| GET | `/in-doubt/{server_name}` | `List[Transaction2PCDetail]` | In-doubt de um servidor |
| GET | `/history` | `List[Transaction2PC]` | Histórico (últimas 24h) |
| GET | `/history/{server_name}` | `List[Transaction2PC]` | Histórico de um servidor |
| GET | `/dtc-status` | `List[DTCStatus]` | Status do MS DTC em todos os servidores |
| GET | `/dtc-status/{server_name}` | `DTCStatus` | Status do MS DTC de um servidor |
| GET | `/alerts` | `List[Alert2PC]` | Alertas ativos (não resolvidos) |
| GET | `/alerts/history` | `List[Alert2PC]` | Histórico de alertas |
| POST | `/alerts/{alert_id}/resolve` | `Alert2PC` | Marcar alerta como resolvido |
| GET | `/commands/{server_name}` | `List[ResolutionCommand]` | Gerar comandos de resolução |

**Exemplo de implementação:**

```python
@router.get("/status", response_model=ConsolidatedStatus2PC)
async def get_consolidated_status():
    """
    Retorna status consolidado de transações 2PC de todos os servidores.
    
    - **total_servers**: Número total de servidores monitorados
    - **servers_with_issues**: Servidores com transações in-doubt
    - **total_in_doubt**: Total de transações in-doubt (CRÍTICO se > 0)
    """
    # Query na view vw_2PC_Current_Status
    query = """
        SELECT 
            server_name,
            last_check,
            total_distributed_transactions,
            active_count,
            in_doubt_count,
            alert_status
        FROM WatcherDB.dbo.vw_2PC_Current_Status
        ORDER BY in_doubt_count DESC, server_name
    """
    # Executar query e montar response
    pass


@router.get("/in-doubt", response_model=List[Transaction2PCDetail])
async def get_in_doubt_transactions():
    """
    Retorna transações in-doubt que requerem intervenção manual.
    
    ⚠️ **CRÍTICO**: Se houver registros aqui, ação imediata é necessária!
    
    Inclui comandos de resolução:
    - **cmd_rollback**: Comando para forçar rollback
    - **cmd_commit**: Comando para forçar commit
    """
    query = """
        SELECT * FROM WatcherDB.dbo.vw_2PC_InDoubt_Transactions
        ORDER BY duration_seconds DESC
    """
    pass


@router.get("/commands/{server_name}", response_model=List[ResolutionCommand])
async def get_resolution_commands(server_name: str):
    """
    Gera comandos SQL para resolver transações pendentes.
    
    **ATENÇÃO**: Executar estes comandos apenas após análise!
    - Use ROLLBACK se nenhum participante commitou
    - Use COMMIT se outros participantes já commitaram
    """
    query = """
        SELECT 
            server_name,
            uow,
            database_name,
            locks_held,
            cmd_rollback,
            cmd_commit
        FROM WatcherDB.dbo.vw_2PC_InDoubt_Transactions
        WHERE server_name = ?
    """
    pass


@router.post("/alerts/{alert_id}/resolve", response_model=Alert2PC)
async def resolve_alert(
    alert_id: int,
    request: AlertResolveRequest
):
    """
    Marca um alerta como resolvido.
    
    - **resolution_action**: 'ROLLBACK', 'COMMIT', 'AUTO_RESOLVED', 'IGNORED'
    - **resolved_by**: Nome do DBA que resolveu
    """
    query = """
        UPDATE WatcherDB.dbo.Monitor_2PC_Alerts
        SET resolved_at = GETDATE(),
            resolved_by = ?,
            resolution_action = ?
        WHERE id = ?
    """
    pass
```

---

### 2. Schemas Pydantic
**Arquivo:** `schemas/distributed_transactions_schemas.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AlertType(str, Enum):
    IN_DOUBT = "IN_DOUBT"
    LONG_RUNNING = "LONG_RUNNING"
    DTC_ERROR = "DTC_ERROR"


class AlertStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DTCStatusEnum(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class ResolutionAction(str, Enum):
    ROLLBACK = "ROLLBACK"
    COMMIT = "COMMIT"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    IGNORED = "IGNORED"


# ============================================
# Transações
# ============================================
class Transaction2PC(BaseModel):
    """Transação distribuída 2PC básica"""
    server_name: str
    transaction_id: int
    state_desc: str
    dtc_state_desc: Optional[str] = None
    uow: Optional[UUID] = None
    session_id: Optional[int] = None
    login_name: Optional[str] = None
    host_name: Optional[str] = None
    database_name: Optional[str] = None
    duration_seconds: int
    locks_held: int
    is_in_doubt: bool
    collected_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "server_name": "SQLPRD01",
                "transaction_id": 123456,
                "state_desc": "PREPARED",
                "uow": "D5499C66-E398-45CA-BF7E-DC9C194B48CF",
                "duration_seconds": 3600,
                "locks_held": 15,
                "is_in_doubt": True
            }
        }


class Transaction2PCDetail(Transaction2PC):
    """Transação 2PC com detalhes e comandos de resolução"""
    program_name: Optional[str] = None
    transaction_begin_time: Optional[datetime] = None
    cmd_rollback: str = Field(..., description="Comando SQL para forçar ROLLBACK")
    cmd_commit: str = Field(..., description="Comando SQL para forçar COMMIT")

    class Config:
        json_schema_extra = {
            "example": {
                "server_name": "SQLPRD01",
                "transaction_id": 123456,
                "state_desc": "PREPARED",
                "uow": "D5499C66-E398-45CA-BF7E-DC9C194B48CF",
                "duration_seconds": 3600,
                "locks_held": 15,
                "is_in_doubt": True,
                "cmd_rollback": "KILL 'D5499C66-E398-45CA-BF7E-DC9C194B48CF' WITH ROLLBACK;",
                "cmd_commit": "KILL 'D5499C66-E398-45CA-BF7E-DC9C194B48CF' WITH COMMIT;"
            }
        }


# ============================================
# Status
# ============================================
class ServerStatus2PC(BaseModel):
    """Status de transações 2PC de um servidor"""
    server_name: str
    last_check: datetime
    total_distributed_transactions: int
    active_count: int
    in_doubt_count: int
    committed_count: int = 0
    aborted_count: int = 0
    max_duration_seconds: Optional[int] = None
    alert_status: AlertStatus


class ConsolidatedStatus2PC(BaseModel):
    """Status consolidado de todos os servidores"""
    checked_at: datetime
    total_servers: int
    servers_with_issues: int
    total_in_doubt: int
    total_active: int
    overall_status: AlertStatus
    servers: List[ServerStatus2PC]


class DTCStatus(BaseModel):
    """Status do MS DTC"""
    server_name: str
    checked_at: datetime
    dtc_status: DTCStatusEnum
    error_message: Optional[str] = None


# ============================================
# Alertas
# ============================================
class Alert2PC(BaseModel):
    """Alerta de transação 2PC"""
    id: int
    created_at: datetime
    server_name: str
    alert_type: AlertType
    alert_severity: AlertSeverity
    transaction_id: Optional[int] = None
    uow: Optional[UUID] = None
    details: str
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_action: Optional[ResolutionAction] = None
    minutes_open: Optional[int] = None


class AlertResolveRequest(BaseModel):
    """Request para resolver um alerta"""
    resolved_by: str = Field(..., description="Nome do DBA que resolveu")
    resolution_action: ResolutionAction = Field(..., description="Ação tomada")
    notes: Optional[str] = Field(None, description="Observações adicionais")


# ============================================
# Comandos de Resolução
# ============================================
class ResolutionCommand(BaseModel):
    """Comando para resolver transação pendente"""
    server_name: str
    uow: UUID
    database_name: str
    locks_held: int
    duration_seconds: int
    cmd_rollback: str
    cmd_commit: str
    recommendation: str = Field(
        default="ROLLBACK (mais seguro se não souber o estado dos outros participantes)"
    )
```

---

### 3. Registrar Router no Main
**Arquivo:** `watcherdb_main.py`

Adicionar no arquivo principal:

```python
# Importar o router
from api.distributed_transactions_router import router as distributed_transactions_router

# Registrar o router (junto com os outros routers existentes)
app.include_router(distributed_transactions_router)
```

---

### 4. Dashboard HTML (Opcional)
**Arquivo:** `templates/2pc_dashboard.html`

Dashboard visual mostrando:
- Card com contagem de transações in-doubt (vermelho se > 0)
- Tabela de servidores com status
- Lista de alertas ativos
- Histórico de transações
- Comandos de resolução (com botão de copiar)

---

## QUERIES SQL PARA OS ENDPOINTS

### ⚠️ Nota sobre Compatibilidade de Versões
As queries abaixo usam views que internamente fazem detecção de versão:
- **SQL Server ≥ 16 (2022+)**: Usa `sys.dm_tran_distributed_transaction_stats`
- **SQL Server 11-15 (2012-2019)**: Usa `sys.dm_tran_locks` com filtro `DISTRIBUTED_TRANSACTION`

**Status Consolidado:**
```sql
SELECT * FROM WatcherDB.dbo.vw_2PC_Current_Status;
```

**Transações In-Doubt (MÉTODO UNIVERSAL - todas as versões):**
```sql
-- Esta query funciona em SQL Server 2012-2022+
SELECT 
    @@SERVERNAME AS server_name,
    l.request_owner_guid AS uow,
    DB_NAME(l.resource_database_id) AS database_name,
    COUNT(*) AS locks_held,
    MAX(l.resource_type) AS resource_type,
    MAX(l.request_mode) AS request_mode,
    'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH ROLLBACK;' AS cmd_rollback,
    'KILL ''' + CAST(l.request_owner_guid AS VARCHAR(50)) + ''' WITH COMMIT;' AS cmd_commit
FROM sys.dm_tran_locks l
WHERE l.request_owner_type = 'DISTRIBUTED_TRANSACTION'
GROUP BY l.request_owner_guid, l.resource_database_id;
```

**View In-Doubt (WatcherDB):**
```sql
SELECT * FROM WatcherDB.dbo.vw_2PC_InDoubt_Transactions;
```

**Alertas Ativos:**
```sql
SELECT * FROM WatcherDB.dbo.vw_2PC_Active_Alerts;
```

**Histórico (últimas 24h):**
```sql
SELECT * FROM WatcherDB.dbo.Monitor_2PC_Transactions
WHERE collected_at >= DATEADD(HOUR, -24, GETDATE())
ORDER BY collected_at DESC;
```

**DTC Status:**
```sql
SELECT * FROM WatcherDB.dbo.Monitor_2PC_DTC_Status
WHERE checked_at = (
    SELECT MAX(checked_at) FROM WatcherDB.dbo.Monitor_2PC_DTC_Status dt2
    WHERE dt2.server_name = Monitor_2PC_DTC_Status.server_name
);
```

**Verificação Rápida de Versão (para debug):**
```sql
DECLARE @v INT = CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)), 4) AS INT);
SELECT 
    @@SERVERNAME AS servidor,
    @v AS versao_major,
    CASE 
        WHEN @v >= 16 THEN 'SQL 2022+ (DMV nativa)'
        WHEN @v >= 11 THEN 'SQL 2012-2019 (dm_tran_locks)'
        ELSE 'Versão antiga'
    END AS metodo;
```

---

## PADRÕES A SEGUIR

1. **Router:** Seguir o padrão dos routers existentes em `/api/`
2. **Conexão:** Usar o helper de conexão existente em `watcherdb_main.py`
3. **Documentação:** Docstrings em todos os endpoints (aparece no Swagger)
4. **Type hints:** Em todas as funções
5. **Tratamento de erros:** HTTPException com códigos apropriados
6. **Async:** Usar async/await para operações de I/O

---

## CRITÉRIOS DE QUALIDADE

- [ ] Código segue PEP 8
- [ ] Todas as funções têm type hints
- [ ] Todos os endpoints têm docstrings
- [ ] Tratamento de erros robusto
- [ ] Endpoints documentados para Swagger/OpenAPI
- [ ] Schemas Pydantic com exemplos
- [ ] Router registrado corretamente no main

---

## EXEMPLO DE RESPOSTA DO SWAGGER

Após implementação, o Swagger (em `/docs`) deve mostrar:

```
Two-Phase Commit Monitoring
├── GET /api/2pc/status
├── GET /api/2pc/status/{server_name}
├── GET /api/2pc/transactions
├── GET /api/2pc/transactions/{server_name}
├── GET /api/2pc/in-doubt              ⚠️ CRÍTICO
├── GET /api/2pc/in-doubt/{server_name}
├── GET /api/2pc/history
├── GET /api/2pc/history/{server_name}
├── GET /api/2pc/dtc-status
├── GET /api/2pc/dtc-status/{server_name}
├── GET /api/2pc/alerts
├── GET /api/2pc/alerts/history
├── POST /api/2pc/alerts/{alert_id}/resolve
└── GET /api/2pc/commands/{server_name}
```

---

*Prompt versão 1.2 - PARTE 2: API + Web (WATCHERDB_DEV)*
*Atualizado: 2026-01-28 - Queries validadas em SQL Server 2019 (v15)*
