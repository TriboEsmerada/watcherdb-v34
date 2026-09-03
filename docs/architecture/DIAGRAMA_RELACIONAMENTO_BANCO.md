# DIAGRAMA DE RELACIONAMENTO - WatcherDB Intelligence

**Versao:** 3.4
**Data:** 2025-12-23
**Autor:** WatcherDB Intelligence Team

---

## 1. VISAO GERAL DA ARQUITETURA DE DADOS

A arquitetura do WatcherDB Intelligence segue o padrao Blue-Green para gerenciamento de dados:

- **_STG (Staging)**: Dados atuais/recentes
- **_HIST (Historico)**: Dados arquivados  
- **_AGG_VIEW**: Views agregadas (resumo para cards do dashboard)
- **_DET_VIEW**: Views detalhadas (todos os campos, para drill-down)
- **_GROUPED_VIEW**: Views agrupadas por servidor (para modais)

---

## 2. PADRAO DE NOMENCLATURA

| Sufixo         | Descricao                           | Exemplo                              |
|----------------|-------------------------------------|--------------------------------------|
| _STG           | Tabela Staging (dados atuais)       | KPI_MSSQL_DISK_USAGE_STG             |
| _HIST          | Tabela Historico (arquivados)       | KPI_MSSQL_DISK_USAGE_HIST            |
| _AGG_VIEW      | View Agregada (resumo)              | KPI_MSSQL_DISK_USAGE_AGG_VIEW        |
| _DET_VIEW      | View Detalhada (completo)           | KPI_MSSQL_DISK_USAGE_DET_VIEW        |
| _GROUPED_VIEW  | View Agrupada por servidor          | KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW|
| usp_*_Upsert   | Stored Procedure Insert/Update      | usp_MSSQL_Disk_Usage_Upsert          |

---

## 3. TABELAS E VIEWS POR CATEGORIA

### AVAILABILITY (Disponibilidade)
- KPI_MSSQL_INST_AVAILABILITY_STG -> _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_DB_AVAILABILITY_STG -> _AGG_VIEW, _DET_VIEW

### ALWAYSON
- KPI_MSSQL_ALWAYSON_STATUS_STG -> _HIST, _AGG_VIEW, _DET_VIEW

### PERFORMANCE (Real-time)
- KPI_MSSQL_BLOCKED_SESSIONS_STG -> _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_BLOCKED_USERS_STG -> _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_DEADLOCKS_STG -> _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_LONG_LOCKS_STG -> _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_PROCESSES_STG -> _AGG_VIEW, _DET_VIEW

### CAPACITY (Espacamento)
- KPI_MSSQL_DISK_USAGE_STG -> _HIST, _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_TLOG_USAGE_STG -> _HIST, _AGG_VIEW, _DET_VIEW
- KPI_MSSQL_FG_USAGE_STG -> _HIST, _AGG_VIEW, _DET_VIEW

### BACKUPS
- KPI_MSSQL_BACKUPS_STG -> _HIST, _AGG_VIEW, _DET_VIEW

### SERVICOS
- KPI_MSSQL_SERVICE_STATUS_STG -> _AGG_VIEW, _DET_VIEW

### OS METRICS (Windows WMI)
- KPI_OS_CPU_STG -> _HIST, vw_OS_CPU_Trend_30Min, vw_OS_CPU_Current
- KPI_OS_MEMORY_STG -> _HIST, vw_OS_Memory_Trend_30Min, vw_OS_Memory_Current
- KPI_OS_DISK_PERF_STG -> _HIST

### ERRORLOG
- KPI_MSSQL_ERRORLOG_STG

### DB I/O STATS
- KPI_MSSQL_DB_IO_STATS_STG -> _AGG_VIEW, _DET_VIEW

### SERVER OFFLINE TRACKING
- KPI_MSSQL_SERVER_OFFLINE_EVENTS -> _AGG_VIEW, _DET_VIEW, _GROUPED_VIEW

---

## 4. DETALHES DAS VIEWS SERVER OFFLINE

| View                                    | Descricao                                      |
|-----------------------------------------|------------------------------------------------|
| KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW       | Resumo: conta SERVIDORES unicos por diagnostico|
| KPI_MSSQL_SERVER_OFFLINE_DET_VIEW       | Detalhe: todos os eventos individuais          |
| KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW   | Modal: agrupa eventos por servidor (evita duplicatas)|

### Colunas da AGG_VIEW (resumo para cards)
- Servers_Offline: COUNT DISTINCT de servidores com Diagnosis='offline'
- Servers_SQL_Down: COUNT DISTINCT de servidores com Diagnosis='sql_down'
- Servers_Partial: COUNT DISTINCT de servidores com Diagnosis='partial'
- Total_Events: COUNT DISTINCT de todos os servidores com problemas
- Overall_Status: CRITICAL/WARNING/OK
- Last_Event_Time: MAX(Event_Time)

### Colunas da GROUPED_VIEW (para modal)
- Server_Name, Instance, Env
- Event_Count: quantidade de eventos deste servidor
- Diagnosis, Diagnosis_Desc
- Ping_OK, Ping_Status, Ping_Message
- Services_Down
- First_Event_Time, Last_Event_Time
- Minutes_Since_First_Event, Minutes_Since_Last_Event
- Severity, State

---

## 5. FREQUENCIA DE COLETA

| KPI                   | Frequencia | Tabela                          |
|-----------------------|------------|---------------------------------|
| Instance Availability | 1 min      | KPI_MSSQL_INST_AVAILABILITY_STG |
| DB Availability       | 5 min      | KPI_MSSQL_DB_AVAILABILITY_STG   |
| Blocked Sessions      | 1 min      | KPI_MSSQL_BLOCKED_SESSIONS_STG  |
| AlwaysOn Status       | 1 min      | KPI_MSSQL_ALWAYSON_STATUS_STG   |
| Service Status        | 5 min      | KPI_MSSQL_SERVICE_STATUS_STG    |
| Disk Usage            | 15 min     | KPI_MSSQL_DISK_USAGE_STG        |
| Backup Status         | 15 min     | KPI_MSSQL_BACKUPS_STG           |
| OS CPU                | 5 min      | KPI_OS_CPU_STG                  |
| OS Memory             | 5 min      | KPI_OS_MEMORY_STG               |
| OS Disk Performance   | 5 min      | KPI_OS_DISK_PERF_STG            |

---

## 6. STORED PROCEDURES PRINCIPAIS

| Procedure                           | Tabela Destino                    |
|-------------------------------------|-----------------------------------|
| usp_MSSQL_Inst_Availability_Upsert  | KPI_MSSQL_INST_AVAILABILITY_STG   |
| usp_MSSQL_DB_Availability_Upsert    | KPI_MSSQL_DB_AVAILABILITY_STG     |
| usp_MSSQL_Disk_Usage_Upsert         | KPI_MSSQL_DISK_USAGE_STG          |
| usp_MSSQL_TLog_Usage_Upsert         | KPI_MSSQL_TLOG_USAGE_STG          |
| usp_MSSQL_FG_Usage_Upsert           | KPI_MSSQL_FG_USAGE_STG            |
| usp_MSSQL_Backups_Upsert            | KPI_MSSQL_BACKUPS_STG             |
| usp_MSSQL_AlwaysOn_Status_Upsert    | KPI_MSSQL_ALWAYSON_STATUS_STG     |
| usp_MSSQL_Blocked_Sessions_Upsert   | KPI_MSSQL_BLOCKED_SESSIONS_STG    |
| usp_MSSQL_Service_Status_Upsert     | KPI_MSSQL_SERVICE_STATUS_STG      |
| usp_OS_CPU_Upsert                   | KPI_OS_CPU_STG                    |
| usp_OS_Memory_Upsert                | KPI_OS_MEMORY_STG                 |
| usp_OS_Disk_Upsert                  | KPI_OS_DISK_PERF_STG              |
| usp_MSSQL_Server_Offline_Upsert     | KPI_MSSQL_SERVER_OFFLINE_EVENTS   |
| usp_ResolveServerOfflineEvent       | KPI_MSSQL_SERVER_OFFLINE_EVENTS   |

---

## 7. VIEWS COM NOLOCK (Performance)

Todas as views usam WITH (NOLOCK) para evitar bloqueios durante leitura.

---

## 7.1 OTIMIZACAO DAS VIEWS _ACTIVE (v2 - CTE)

As views `_ACTIVE` sao a camada de abstracao Blue/Green. A versao v2 usa CTE para performance:

**Problema anterior (v1):**
- Cada UNION ALL tinha uma subquery para verificar Active_Slot
- 6 subqueries executadas para cada acesso a view
- Tempo de execucao: ~24 segundos para carregar dashboard

**Solucao (v2 - CTE):**
- Uma unica CTE busca o Active_Slot no inicio
- CROSS JOIN distribui o valor para todos os UNION ALL
- Tempo de execucao: ~1 segundo (25x mais rapido)

```sql
-- Estrutura otimizada das views _ACTIVE:
WITH ActiveSlot AS (
    SELECT Active_Slot FROM dbo.KPI_STG_ACTIVE_TABLE
    WHERE Table_Name = 'KPI_MSSQL_..._STG'
)
SELECT d.* FROM dbo.KPI_..._BLUE_PRD d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = 'BLUE'
UNION ALL
SELECT d.* FROM dbo.KPI_..._GREEN_PRD d CROSS JOIN ActiveSlot a WHERE a.Active_Slot = 'GREEN'
-- ... etc
```

**Procedure para recriar views:** `usp_create_active_view`

Exemplo:


---

## 8. AMBIENTES

| Codigo | Nome       | Servidores |
|--------|------------|------------|
| PRD    | Production | ~60        |
| QA     | Quality    | ~20        |
| TST    | Test       | ~15        |

---

## 9. CHANGELOG

| Data       | Versao | Alteracao                                              |
|------------|--------|--------------------------------------------------------|
| 2025-11-28 | 1.0    | Versao inicial                                         |
| 2025-12-21 | 2.0    | Adicao de tabelas OS (CPU, Memory, Disk)               |
| 2025-12-23 | 3.0    | Adicao de WITH (NOLOCK) em todas as views              |
| 2025-12-23 | 3.1    | Correcao AGG_VIEW e DET_VIEW para Server Offline       |
| 2025-12-23 | 3.2    | AGG_VIEW usa COUNT DISTINCT; nova GROUPED_VIEW p/ modal|
| 2025-12-23 | 3.3    | Server Offline agora usa UPSERT (padrao igual outras coletas)|
| 2025-12-23 | 3.4    | Otimizacao views _ACTIVE: CTE em vez de subqueries (25x mais rapido)|
