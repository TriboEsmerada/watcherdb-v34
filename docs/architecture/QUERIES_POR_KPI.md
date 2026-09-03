# Queries por KPI - WatcherDB Intelligence

Este documento lista as queries SQL utilizadas por cada KPI no dashboard.
**Database:** WatcherDB_Intelligence
**Atualizado:** 2025-12-31

---

## PARTE 1: QUERIES DOS CARDS

### 1. DB Availability (Abnormal) - ATUALIZADO
```sql
-- Agora faz cross-reference com mirroring
-- Exclui databases RESTORING que sao mirrors sincronizados
SELECT COUNT(*) AS DB_Issues
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK)
-- Mostra apenas problemas REAIS
```

### 2. DB Availability (Total)
```sql
SELECT COUNT(DISTINCT Instance + '|' + [Database]) AS TOTAL_DATABASES
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
```

### 3. DB Availability (OK)
```sql
SELECT COUNT(*) AS DB_Availability
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_DB_AVAILABILITY_STG WITH (NOLOCK)
WHERE [State] = 'ONLINE'
```

### 4. Instance Availability (OK)
```sql
SELECT COUNT(DISTINCT Instance) AS Instancias_OK
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 1
```

### 5. Instance Availability (Off)
```sql
SELECT COUNT(DISTINCT Instance) AS Instances_Off
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_INST_AVAILABILITY_STG WITH (NOLOCK)
WHERE Is_Available = 0
```

### 6. Disk File System
```sql
SELECT Instance, Critical, Warning
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
-- Card: SUM(Critical), SUM(Warning)
```

### 7. Transaction Logs
```sql
SELECT Instance, Critical, Warning
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_TLOG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
-- Card: SUM(Critical), SUM(Warning)
```

### 8. Always On (Unhealthy)
```sql
SELECT COUNT(DISTINCT AgName) AS AGs_Unhealthy
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK)
WHERE (
    (Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> '')
    OR (Sec_Synch_Health <> 'HEALTHY' AND Sec_Synch_Health IS NOT NULL AND Sec_Synch_Health <> '')
    OR (Pri_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Pri_Synch_State IS NOT NULL)
    OR (Sec_Synch_State NOT IN ('SYNCHRONIZED', 'SYNCHRONIZING', 'UNKNOWN', '') AND Sec_Synch_State IS NOT NULL)
    OR Pri_Is_Suspended = 1
    OR Sec_Is_Suspended = 1
)
```

### 9. FileGroup Usage
```sql
SELECT
    f.Instance,
    SUM(CASE WHEN f.Percent_Used >= 98 THEN 1 ELSE 0 END) AS Critical,
    SUM(CASE WHEN f.Percent_Used >= 95 AND f.Percent_Used < 98 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN f.Percent_Used >= 90 AND f.Percent_Used < 95 THEN 1 ELSE 0 END) AS Attention
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_FG_USAGE_STG f WITH (NOLOCK)
GROUP BY f.Instance
HAVING SUM(CASE WHEN f.Percent_Used >= 90 THEN 1 ELSE 0 END) > 0
-- Card: COUNT(DISTINCT Instance) por nivel (Critical, Warning, Attention)
-- Thresholds: Critical >= 98%, Warning >= 95%, Attention >= 90%
```

### 10. Blocked Sessions
```sql
SELECT Instance, Cnt
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0
-- Card: COUNT de instancias com bloqueio
```

### 11. Blocked Users
```sql
SELECT COUNT(DISTINCT [User]) AS Blocked_Users
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
  AND Update_TS >= DATEADD(MINUTE, -15, GETDATE())
-- Freshness: apenas ultimos 15 minutos
```

### 12. Service Status
```sql
SELECT Instance, Services_Down_Count
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0
-- Card: SUM(Services_Down_Count)
```

### 13. Long Locks
```sql
SELECT Instance, Cnt, [State]
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0
-- Card: COUNT por [State] (CRITICAL, WARNING)
```

### 14. Processes
```sql
SELECT Instance, [State], Process_Count
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
WHERE [State] IN ('WARNING', 'CRITICAL')
-- Card: COUNT de instancias por estado
```

### 15. Backup Status
```sql
SELECT
    b.Instance,
    b.[Database],
    b.Backup_Type,
    b.Hours_Since_Backup,
    b.Last_Backup_Date,
    e.Env
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_BACKUPS_STG b WITH (NOLOCK)
LEFT JOIN WatcherDB_Intelligence.dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = b.Instance
-- Thresholds:
--   FULL: Failed > 168h (7 dias), Delayed > 120h (5 dias)
--   DIFF: Failed > 48h, Delayed > 36h
--   LOG:  Failed > 4h, Delayed > 2h
-- Card: COUNT por status (Failed, Delayed, OK)
```

### 16. Server Offline
```sql
SELECT *
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW WITH (NOLOCK)
```

### 17. Mirroring (Unhealthy) - NOVO
```sql
-- Card mostra quantidade de mirroring com problemas
SELECT COUNT(*) AS Mirroring_Issues
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_MIRRORING_STATUS_DET_VIEW WITH (NOLOCK)
-- Resultado atual: 0 (todos sincronizados)
```

---

## PARTE 2: QUERIES DOS MODAIS

### DB Availability Modal - ATUALIZADO
```sql
SELECT
    Instance,
    [Database],
    [State],
    Recovery_Model,
    Mirroring_Role,
    Mirroring_State,
    Has_Mirroring,
    Env,
    Problem_Reason,
    Update_TS
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW WITH (NOLOCK)
ORDER BY Env, Instance, [Database]
```

### Instance Availability Modal
```sql
-- View agregada por ambiente (nao por instancia)
SELECT Env, State, Count
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW WITH (NOLOCK)
-- Resultado: DEV=2, PRD=44, QLT=20, SCOM=3, TST=12
```

### Disk File System Modal
```sql
SELECT Instance, Env, Normal, Warning, Critical
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_DISK_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Critical > 0 OR Warning > 0
```

### Transaction Logs Modal
2026-09-02: uma linha POR BASE; classificação em Python
(`api/routers/intelligence/tlog_usage_classes.py::classify_tlog`, registry
`tlog_usage` 85/95 + override, frescura 1440 min). Card e modal chamam a
MESMA função (o card lê `per_instance`, forma legada por instância). O
lookup do último backup de LOG é AG-aware (qualquer nó do AG); o recovery
model vem do `KPI_MSSQL_DB_SETTINGS_STG`.
```sql
;WITH ag AS (SELECT DISTINCT AgName, UPPER(Instance) Instance_N, UPPER([Database]) Database_N
             FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG WITH (NOLOCK) WHERE AgName IS NOT NULL),
lastlog AS (SELECT UPPER(Instance) Instance_N, UPPER([Database]) Database_N, MAX(Last_Backup_Date) Last_Log_Backup_Date
            FROM dbo.KPI_MSSQL_BACKUPS_STG WITH (NOLOCK) WHERE Backup_Type IN ('L','LOG')
            GROUP BY UPPER(Instance), UPPER([Database])),
lastlog_ag AS (SELECT a.AgName, l.Database_N, MAX(l.Last_Log_Backup_Date) Last_Log_Backup_Date
               FROM lastlog l JOIN ag a ON a.Instance_N = l.Instance_N AND a.Database_N = l.Database_N
               GROUP BY a.AgName, l.Database_N)
SELECT t.Instance, t.[Database], ISNULL(e.Env,'Undefined') AS Env,
       t.Percent_Used, t.Used_MB, t.Current_MB, t.Max_Available_MB, t.Update_TS,
       ds.Recovery_Model,
       COALESCE(lag.Last_Log_Backup_Date, ll.Last_Log_Backup_Date) AS Last_Log_Backup_Date
FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e ON UPPER(e.Instance) = UPPER(t.Instance)
LEFT JOIN dbo.KPI_MSSQL_DB_SETTINGS_STG ds ON UPPER(ds.Instance) = UPPER(t.Instance) AND UPPER(ds.Database_Name) = UPPER(t.[Database])
LEFT JOIN ag a ON a.Instance_N = UPPER(t.Instance) AND a.Database_N = UPPER(t.[Database])
LEFT JOIN lastlog_ag lag ON lag.AgName = a.AgName AND lag.Database_N = UPPER(t.[Database])
LEFT JOIN lastlog ll ON ll.Instance_N = UPPER(t.Instance) AND ll.Database_N = UPPER(t.[Database])
-- (LTRIM/RTRIM omitidos aqui por legibilidade; a query real normaliza com LTRIM(RTRIM(UPPER(...))))
```
Payload por base (contrato): `Instance, Database, Env, Percent_Used, Used_MB,
Current_MB, Max_Available_MB, Update_TS, Last_Check, Recovery_Model,
Last_Log_Backup_Date, Hours_Since_Log_Backup, Log_Backup_Age
(NEVER|LATE|OK|SIMPLE|UNKNOWN), Severity, Instance_Severity, Base_Key,
Threshold_Warning, Threshold_Critical`; ordenado `Percent_Used DESC`.

### Always On Modal
```sql
SELECT AgName, Env, Unhealthy, Total, Problem_Reasons, Update_TS
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Unhealthy > 0
```

### FileGroup Usage Modal
```sql
SELECT Instance, Env, Warning, Critical, Last_Check
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_FG_USAGE_AGG_VIEW WITH (NOLOCK)
WHERE Warning > 0 OR Critical > 0
```

### Blocked Sessions Modal
```sql
SELECT Instance, Env, Cnt
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0
```

### Blocked Users Modal
```sql
SELECT Instance, [Database], [User], Blocked_Count, Max_Wait_Time_Sec, Update_TS
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_BLOCKED_USERS_STG WITH (NOLOCK)
WHERE Blocked_Count > 0
ORDER BY Max_Wait_Time_Sec DESC
```

### Service Status Modal
```sql
SELECT 
    Instance, 
    Env, 
    Services_Down_Count, 
    Unique_Services_Down, 
    Last_Check, 
    Last_Event_Time, 
    Services_Down_List
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK)
WHERE Services_Down_Count > 0
```

### Long Locks Modal
```sql
SELECT Instance, Env, Cnt, [State]
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_LONG_LOCKS_AGG_VIEW WITH (NOLOCK)
WHERE Cnt > 0
```

### Processes Modal
```sql
SELECT Instance, Env, Processes, [State]
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_PROCESSES_AGG_VIEW WITH (NOLOCK)
```

### Backup Status Modal
```sql
SELECT Instance, Env, Backup_Type, Total_Databases, Critical, Warning, Normal
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_BACKUPS_AGG_VIEW WITH (NOLOCK)
```

### Server Offline Modal
```sql
SELECT 
    Server_Name, 
    Instance, 
    Env, 
    Event_Count, 
    Diagnosis, 
    Diagnosis_Desc, 
    Ping_OK, 
    Ping_Status, 
    Ping_Message, 
    Services_Down, 
    First_Event_Time, 
    Last_Event_Time, 
    Minutes_Since_First_Event, 
    Minutes_Since_Last_Event, 
    Severity, 
    [State]
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK)
```

### Mirroring Status Modal (NOVO)
```sql
SELECT
    Instance,
    [Database],
    Mirroring_Role,
    Mirroring_State,
    Database_State,
    Partner_Instance,
    Env,
    Update_TS
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_MIRRORING_STATUS_ACTIVE WITH (NOLOCK)
ORDER BY
    CASE WHEN Mirroring_State <> 'SYNCHRONIZED' THEN 0 ELSE 1 END,
    Instance, [Database]
```

### Mirroring Problems Modal (NOVO)
```sql
SELECT
    Instance,
    [Database],
    Mirroring_Role,
    Mirroring_State,
    Database_State,
    Safety_Level,
    Partner_Name,
    Partner_Instance,
    Env,
    Problem_Reason,
    Update_TS
FROM WatcherDB_Intelligence.dbo.KPI_MSSQL_MIRRORING_STATUS_DET_VIEW WITH (NOLOCK)
ORDER BY Env, Instance, [Database]
```

---

## PARTE 3: QUERY SUMMARY (Dashboard Principal)

```sql
-- Query completa para summary card
SELECT
    (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE) AS Total_Instances,
    (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WHERE Is_Available = 1) AS Instances_Online,
    (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WHERE Is_Available = 0) AS Instances_Offline,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW) AS DB_Issues,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_MIRRORING_STATUS_ACTIVE) AS Total_Mirroring,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_MIRRORING_STATUS_DET_VIEW) AS Mirroring_Issues,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_DISK_USAGE_ACTIVE WHERE Percent_Free < 10) AS Disk_Critical,
    (SELECT COUNT(*) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW) AS AlwaysOn_Issues
```

**Resultado em 2025-12-31:**
| Métrica | Valor |
|---------|-------|
| Total_Instances | 81 |
| Instances_Online | 81 |
| Instances_Offline | 0 |
| DB_Issues | 1 |
| Total_Mirroring | 140 |
| Mirroring_Issues | 0 |
| Disk_Critical | 8 |
| AlwaysOn_Issues | 0 |

---

## PARTE 4: FRESHNESS WINDOWS

| Categoria | Tempo | KPIs |
|-----------|-------|------|
| services | 15 min | Instance Availability, Service Status |
| real_time | 5 min | Blocked Sessions, Long Locks, AlwaysOn, Mirroring |
| capacity | 60 min | Disk, TLogs, FileGroups, Processes, DB Availability |
| backup | 1440 min (24h) | Backups |

---

## PARTE 5: NOVAS VIEWS (2025-12-31)

### KPI_MSSQL_MIRRORING_STATUS_ACTIVE

| Coluna | Tipo | Descricao |
|--------|------|-----------|
| Instance | VARCHAR(100) | Servidor SQL (ex: SQLHDSPRD302_I01) |
| Database | VARCHAR(128) | Nome do database |
| Mirroring_Role | VARCHAR(60) | PRINCIPAL ou MIRROR |
| Mirroring_State | VARCHAR(60) | SYNCHRONIZED, SYNCHRONIZING, DISCONNECTED, SUSPENDED |
| Database_State | VARCHAR(60) | ONLINE, RESTORING, etc |
| Safety_Level | VARCHAR(60) | FULL ou OFF |
| Partner_Name | VARCHAR(256) | Endpoint TCP do partner (ex: TCP://server:5022) |
| Partner_Instance | VARCHAR(128) | Nome da instancia partner (ex: SQLHDSPRD301\I01) |
| Env | VARCHAR(10) | Ambiente: PRD, QA, TST |
| Update_TS | DATETIME | Timestamp da coleta |

### KPI_MSSQL_MIRRORING_STATUS_DET_VIEW

Mesmas colunas + `Problem_Reason`:
- "Mirror DISCONNECTED"
- "Mirror SUSPENDED"
- "Mirror em sync" (SYNCHRONIZING por muito tempo)
- "Principal nao ONLINE"

### KPI_MSSQL_DB_AVAILABILITY_DET_VIEW (Atualizada)

| Coluna | Tipo | Descricao |
|--------|------|-----------|
| Instance | VARCHAR(100) | Servidor SQL |
| Database | VARCHAR(128) | Nome do database |
| State | VARCHAR(60) | Estado do database |
| Is_Available | BIT | 1=Online, 0=Offline |
| Recovery_Model | VARCHAR(60) | FULL, SIMPLE, BULK_LOGGED |
| Mirroring_Role | VARCHAR(60) | PRINCIPAL, MIRROR ou vazio |
| Mirroring_State | VARCHAR(60) | Estado do mirroring ou vazio |
| Has_Mirroring | BIT | 1=Tem mirroring, 0=Nao tem |
| Env | VARCHAR(10) | Ambiente |
| Problem_Reason | VARCHAR(100) | Motivo do problema |
| Update_TS | DATETIME | Timestamp |

---

## PARTE 6: LOGICA DE DETECCAO DE PROBLEMAS

### Mirroring DET_VIEW
Mostra mirroring com problemas quando:
- `Mirroring_State <> 'SYNCHRONIZED'` (DISCONNECTED, SUSPENDED, SYNCHRONIZING)
- `Database_State <> 'ONLINE'` no servidor PRINCIPAL

### DB Availability DET_VIEW
Mostra databases com problemas quando:
- Database nao esta ONLINE
- **EXCETO** se for RESTORING E tiver um par PRINCIPAL/SYNCHRONIZED em outro servidor

### Resultado da Correcao
- **Antes**: 141 databases com "problemas" (falsos positivos de mirrors)
- **Depois**: 1 database com problema real (RESTORING sem mirroring)

---

## PARTE 7: TABELAS E VIEWS COMPLETAS

### Tabelas de Staging (STG)
| Tabela | Descricao |
|--------|-----------|
| KPI_MSSQL_DB_AVAILABILITY_STG | Disponibilidade de databases |
| KPI_MSSQL_INST_AVAILABILITY_STG | Disponibilidade de instancias |
| KPI_MSSQL_ALWAYSON_STATUS_STG | Status do AlwaysOn |
| KPI_MSSQL_FG_USAGE_STG | Uso de FileGroups |
| KPI_MSSQL_BLOCKED_USERS_STG | Usuarios bloqueados |
| KPI_MSSQL_BACKUPS_STG | Status de backups |
| KPI_MSSQL_INST_ENVS | Ambiente das instancias (PRD/HML/DEV) |
| KPI_MSSQL_ERRORLOG_STG | Erros do SQL Server ErrorLog |

### Views Agregadas (AGG_VIEW)
| View | Descricao |
|------|-----------|
| KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW | Agregacao de DB Availability |
| KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW | Agregacao de Instance Availability |
| KPI_MSSQL_DISK_USAGE_AGG_VIEW | Agregacao de Disk Usage |
| KPI_MSSQL_TLOG_USAGE_AGG_VIEW | Agregacao de Transaction Logs |
| KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW | Agregacao de AlwaysOn Status |
| KPI_MSSQL_FG_USAGE_AGG_VIEW | Agregacao de FileGroup Usage |
| KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW | Agregacao de Blocked Sessions |
| KPI_MSSQL_SERVICE_STATUS_AGG_VIEW | Agregacao de Service Status |
| KPI_MSSQL_LONG_LOCKS_AGG_VIEW | Agregacao de Long Locks |
| KPI_MSSQL_PROCESSES_AGG_VIEW | Agregacao de Processes |
| KPI_MSSQL_BACKUPS_AGG_VIEW | Agregacao de Backups |
| KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW | Agregacao de Server Offline |
| KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW | Agrupamento de Server Offline |

### Views de Detalhe (DET_VIEW) e Active
| View | Descricao |
|------|-----------|
| KPI_MSSQL_DB_AVAILABILITY_DET_VIEW | Databases com problemas reais |
| KPI_MSSQL_SERVER_OFFLINE_DET_VIEW | Servidores offline detalhes |
| KPI_MSSQL_MIRRORING_STATUS_ACTIVE | Status atual de todos mirroring |
| KPI_MSSQL_MIRRORING_STATUS_DET_VIEW | Mirroring com problemas |

---

## PARTE 8: THRESHOLDS

| Metrica | Warning | Critical |
|---------|---------|----------|
| Disco % Livre | < 10% | < 5% |
| TLog % Usado | > 75% | > 90% |
| FileGroup % Usado | > 95% | > 98% |
| Backup FULL | > 120h (5d) | > 168h (7d) |
| Backup DIFF | > 36h | > 48h |
| Backup LOG | > 2h | > 4h |
| Block Time | > 60s | > 300s |

---

Gerado em: 2025-12-31
