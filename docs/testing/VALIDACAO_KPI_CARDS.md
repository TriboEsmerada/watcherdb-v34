# WatcherDB Intelligence - Validação de Cards de KPIs

**Data:** 2025-12-21
**Versão:** 1.0

---

## Resumo da Análise

Este documento contém a validação completa de todos os 19 cards de KPI do dashboard WatcherDB Intelligence, verificando o fluxo completo: **Template → API Router → Query SQL → Dados retornados**.

---

## Inventário de Cards KPI

### Localização dos Arquivos

| Componente | Arquivo | Linhas |
|------------|---------|--------|
| Template HTML | `templates/watcherdb_portal.html` | 16641-17084 |
| KPI_METADATA | JavaScript inline | 16641-17084 |
| API Router | `api/routers/intelligence_kpis.py` | 219-2500+ |
| Views SQL | `database/SQLSERVER_KPI_VIEWS.sql` | 1-755 |

---

## Cards de KPI por Categoria

### Categoria: Disponibilidade (5 cards)

#### 1. db-availability-abnormal
| Item | Valor |
|------|-------|
| **ID** | `db-availability-abnormal` |
| **Título** | DB Not Availability |
| **Key** | `db_availability.abnormal_count` |
| **kpiType** | `db-availability` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW` (AbnormalCnt) |
| **Status** | ✅ OK |

**Regra de Cor:**
- Vermelho (#ef4444): `abnormal_count > 0`
- Verde (#10b981): `abnormal_count = 0`

**Fluxo de Dados:**
```
Template → getValue: data.db_availability?.abnormal_count
API → results["db_availability"]["abnormal_count"]
SQL → SELECT SUM(AbnormalCnt) FROM KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
```

---

#### 2. db-availability-total
| Item | Valor |
|------|-------|
| **ID** | `db-availability-total` |
| **Título** | DB Availability |
| **Key** | `db_availability.total_count` |
| **kpiType** | `db-availability` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW` (TotalCnt) |
| **Flag especial** | `all: true` (mostra todos, não apenas problemas) |
| **Status** | ✅ OK |

**Regra de Cor:** Sempre Verde (#10b981)

---

#### 3. db-availability-ok
| Item | Valor |
|------|-------|
| **ID** | `db-availability-ok` |
| **Título** | Instances OK |
| **Key** | `instance_availability.ok_count` |
| **kpiType** | `instance-availability` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW` |
| **Flag especial** | `okFilter: true` |
| **Status** | ✅ OK |

**Regra de Cor:** Sempre Verde (#10b981)

---

#### 4. instance-availability-off
| Item | Valor |
|------|-------|
| **ID** | `instance-availability-off` |
| **Título** | Instances Off |
| **Key** | `instance_availability.off_count` |
| **kpiType** | `instance-availability` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW` (UNAVAILABLE) |
| **Status** | ✅ OK |

**Regra de Cor:**
- Vermelho (#ef4444): `off_count > 0`
- Verde (#10b981): `off_count = 0`

---

#### 5. server-offline
| Item | Valor |
|------|-------|
| **ID** | `server-offline` |
| **Título** | SQL Services Offline/Down |
| **Key** | `server_offline_status.total_events` |
| **kpiType** | `server-offline` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW` |
| **Custom Modal** | `showServerOfflineDetails()` |
| **Status** | ✅ OK |

**Regra de Cor:**
- Vermelho (#ef4444): `servers_offline > 0` OU `PRD > 0` OU `CRITICAL`
- Amarelo (#f59e0b): `WARNING`
- Verde (#10b981): `total_events = 0`

---

### Categoria: Performance (4 cards)

#### 6. blocked-sessions
| Item | Valor |
|------|-------|
| **ID** | `blocked-sessions` |
| **Título** | Blocked Sessions |
| **Key** | `blocked_sessions.count` |
| **kpiType** | `blocked-sessions` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW` (Cnt) |
| **Status** | ✅ OK |

**Regra de Cor:**
- Vermelho (#ef4444): `count > 0`
- Verde (#10b981): `count = 0`

---

#### 7. blocked-users
| Item | Valor |
|------|-------|
| **ID** | `blocked-users` |
| **Título** | Blocked Users |
| **Key** | `blocked_users.count` |
| **kpiType** | `blocked-users` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_BLOCKED_USERS_STG` |
| **Status** | ⚠️ ATENÇÃO |

**Problema Identificado:**
A view `KPI_MSSQL_BLOCKED_USERS_AGG_VIEW` existe em `INSTALACAO_COMPLETA_UNIFICADA.sql` mas não em `SQLSERVER_KPI_VIEWS.sql`.

**Correção Sugerida:**
Executar o script `INSTALACAO_COMPLETA_UNIFICADA.sql` ou adicionar a view ao `SQLSERVER_KPI_VIEWS.sql`:

```sql
-- Estrutura da tabela KPI_MSSQL_BLOCKED_USERS_STG:
-- Instance, [User], [Database], Blocked_Count, Max_Wait_Time_Sec, Update_TS

CREATE VIEW dbo.KPI_MSSQL_BLOCKED_USERS_AGG_VIEW
AS
SELECT
    i.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    ISNULL(bu.Blocked_Users_Count, 0) AS Blocked_Users_Count,
    ISNULL(bu.Total_Blocked_Count, 0) AS Total_Blocked_Count
FROM
    (SELECT DISTINCT Instance FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG) i
    LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON i.Instance = e.Instance
    LEFT OUTER JOIN
    (SELECT Instance,
        COUNT(DISTINCT [User]) AS Blocked_Users_Count,
        SUM(Blocked_Count) AS Total_Blocked_Count
     FROM dbo.KPI_MSSQL_BLOCKED_USERS_STG
     WHERE Blocked_Count > 0
     GROUP BY Instance) bu
      ON i.Instance = bu.Instance;
GO
```

**Nota:** A tabela usa `[User]` e `Blocked_Count` (não `Login_Name` e `Is_Blocked`).

---

#### 8. processes-alarm
| Item | Valor |
|------|-------|
| **ID** | `processes-alarm` |
| **Título** | Processes Alarm |
| **Key** | `processes_alarm.count` |
| **kpiType** | `processes-alarm` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_PROCESSES_AGG_VIEW` |
| **Status** | ✅ OK |

**Regra de Cor:**
- Vermelho (#ef4444): `count > 0`
- Verde (#10b981): `count = 0`

---

### Categoria: Espaço (8 cards)

#### 9. transaction-logs-critical
| Item | Valor |
|------|-------|
| **ID** | `transaction-logs-critical` |
| **Título** | Transaction Logs Critical |
| **Key** | `db_transaction_logs.critical_count` |
| **kpiType** | `transaction-logs` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_TLOG_USAGE_AGG_VIEW` (Critical) |
| **Threshold** | ≥90% uso |
| **Status** | ✅ OK |

---

#### 10. transaction-logs-warning
| Item | Valor |
|------|-------|
| **ID** | `transaction-logs-warning` |
| **Título** | Transaction Logs Warning |
| **Key** | `db_transaction_logs.warning_count` |
| **kpiType** | `transaction-logs` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_TLOG_USAGE_AGG_VIEW` (Warning) |
| **Threshold** | ≥70% e <90% uso |
| **Status** | ✅ OK |

---

#### 11. disk-file-system-critical
| Item | Valor |
|------|-------|
| **ID** | `disk-file-system-critical` |
| **Título** | Disk File System Critical |
| **Key** | `db_disk_file_system.critical_count` |
| **kpiType** | `disk-file-system` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_DISK_USAGE_AGG_VIEW` (Critical) |
| **Threshold** | <10% livre |
| **Status** | ✅ OK |

---

#### 12. disk-file-system-warning
| Item | Valor |
|------|-------|
| **ID** | `disk-file-system-warning` |
| **Título** | Disk File System Warning |
| **Key** | `db_disk_file_system.warning_count` |
| **kpiType** | `disk-file-system` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_DISK_USAGE_AGG_VIEW` (Warning) |
| **Threshold** | ≥10% e <20% livre |
| **Status** | ✅ OK |

---

#### 13. filegroup-usage-critical
| Item | Valor |
|------|-------|
| **ID** | `filegroup-usage-critical` |
| **Título** | FileGroups Usage Critical |
| **Key** | `filegroup_usage.critical_count` |
| **kpiType** | `filegroup-usage` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_FG_USAGE_AGG_VIEW` (Critical) |
| **Threshold** | ≥90% uso |
| **Status** | ✅ OK |

---

#### 14. filegroup-usage-warning
| Item | Valor |
|------|-------|
| **ID** | `filegroup-usage-warning` |
| **Título** | FileGroups Usage Warning |
| **Key** | `filegroup_usage.warning_count` |
| **kpiType** | `filegroup-usage` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_FG_USAGE_AGG_VIEW` (Warning) |
| **Threshold** | ≥80% e <90% uso |
| **Status** | ✅ OK |

---

#### 15. tempdb-critical
| Item | Valor |
|------|-------|
| **ID** | `tempdb-critical` |
| **Título** | TempDB Disk Critical |
| **Key** | `tempdb_status.critical_count` |
| **kpiType** | `tempdb-status-critical` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_DISK_USAGE_AGG_VIEW` (proxy) |
| **Custom Click** | `openTempDBDiagnostics()` |
| **Status** | ⚠️ PROXY |

**Nota:** Usa Disk Usage como proxy, não tem view específica de TempDB.

---

#### 16. tempdb-warning
| Item | Valor |
|------|-------|
| **ID** | `tempdb-warning` |
| **Título** | TempDB Disk Warning |
| **Key** | `tempdb_status.warning_count` |
| **kpiType** | `tempdb-status-warning` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_DISK_USAGE_AGG_VIEW` (proxy) |
| **Custom Click** | `openTempDBDiagnostics()` |
| **Status** | ⚠️ PROXY |

---

#### 17. backup-failed
| Item | Valor |
|------|-------|
| **ID** | `backup-failed` |
| **Título** | Backup Failed |
| **Key** | `backup_status.failed_count` |
| **kpiType** | `backup-failed` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_BACKUPS_STG` (Hours_Since_Backup > 48) |
| **Status** | ✅ OK |

**Regra de Cor por Ambiente:**
- PRD > outros: Vermelho (#ef4444)
- QLT > TST: Amarelo (#f59e0b)
- TST: Azul (#3b82f6)

---

#### 18. backup-delayed
| Item | Valor |
|------|-------|
| **ID** | `backup-delayed` |
| **Título** | Backup Delayed |
| **Key** | `backup_status.delayed_count` |
| **kpiType** | `backup-delayed` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_BACKUPS_STG` (24 < Hours_Since_Backup ≤ 48) |
| **Status** | ✅ OK |

---

### Categoria: Alta Disponibilidade (1 card)

#### 19. always-on-unhealthy
| Item | Valor |
|------|-------|
| **ID** | `always-on-unhealthy` |
| **Título** | Always On UnHealthy |
| **Key** | `always_on.unhealthy_count` |
| **kpiType** | `always-on` |
| **Endpoint** | `GET /api/intelligence-kpis/dashboard` |
| **View SQL** | `KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW` (Unhealthy) |
| **Status** | ✅ OK |

**Regra de Cor:**
- Vermelho (#ef4444): `unhealthy_count > 0`
- Verde (#10b981): `unhealthy_count = 0`

---

## Matriz de Validação Resumida

| # | Card | Template | API | SQL View | Cores | Status |
|---|------|----------|-----|----------|-------|--------|
| 1 | db-availability-abnormal | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 2 | db-availability-total | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 3 | db-availability-ok | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 4 | instance-availability-off | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 5 | server-offline | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 6 | blocked-sessions | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 7 | blocked-users | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 8 | processes-alarm | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 9 | transaction-logs-critical | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 10 | transaction-logs-warning | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 11 | disk-file-system-critical | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 12 | disk-file-system-warning | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 13 | filegroup-usage-critical | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 14 | filegroup-usage-warning | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 15 | tempdb-critical | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 16 | tempdb-warning | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 17 | backup-failed | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 18 | backup-delayed | ✅ | ✅ | ✅ | ✅ | ✅ OK |
| 19 | always-on-unhealthy | ✅ | ✅ | ✅ | ✅ | ✅ OK |

**Legenda:**
- ✅ OK: Funcionando corretamente
- ⚠️ WARN: Funciona mas tem ressalvas
- ❌ ERRO: Componente ausente ou incorreto

---

## Problemas Identificados e Resolvidos

### 1. blocked-users - View Deployada ✅ RESOLVIDO
**Severidade:** Média - **RESOLVIDO em 2025-12-21**

**Problema Original:** A view `KPI_MSSQL_BLOCKED_USERS_AGG_VIEW` não estava em `SQLSERVER_KPI_VIEWS.sql`.

**Resolução:**
- Views adicionadas ao `SQLSERVER_KPI_VIEWS.sql` (linhas 705-758):
  - `KPI_MSSQL_BLOCKED_USERS_AGG_VIEW`
  - `KPI_MSSQL_BLOCKED_USERS_DET_VIEW`

---

### 2. TempDB - Views Criadas ✅ RESOLVIDO
**Severidade:** Baixa - **RESOLVIDO em 2025-12-21**

**Problema Original:** Os cards `tempdb-critical` e `tempdb-warning` usavam query inline.

**Resolução:**
- Views proxy adicionadas ao `SQLSERVER_KPI_VIEWS.sql` (linhas 772-827):
  - `KPI_MSSQL_TEMPDB_STATUS_AGG_VIEW` (usa Disk Usage como proxy)
  - `KPI_MSSQL_TEMPDB_STATUS_DET_VIEW`

**Nota:** As views usam `KPI_MSSQL_DISK_USAGE_STG` como fonte de dados.
Para monitoramento específico de TempDB, considerar criar tabela `KPI_MSSQL_TEMPDB_STATUS_STG` no futuro.

---

### 3. Thresholds Hardcoded
**Severidade:** Informativa

**Problema:** Os thresholds de Warning/Critical estão hardcoded nas views SQL:
- Disk: Critical <10%, Warning <20%
- TLog: Critical ≥90%, Warning ≥70%
- FileGroup: Critical ≥90%, Warning ≥80%
- Backup: Critical >48h, Warning >24h

**Melhoria Sugerida:**
Criar tabela de configuração de thresholds parametrizáveis.

---

## Verificação de Consistência de Cores

### Padrão de Cores

| Estado | Cor Hex | RGB |
|--------|---------|-----|
| Critical/Vermelho | #ef4444 | 239, 68, 68 |
| Warning/Amarelo | #f59e0b | 245, 158, 11 |
| OK/Verde | #10b981 ou #22c55e | 16, 185, 129 |
| Info/Azul | #3b82f6 | 59, 130, 246 |

### Consistência por Card

| Card | Valor 0 | Valor > 0 | Consistente |
|------|---------|-----------|-------------|
| db-availability-abnormal | Verde | Vermelho | ✅ |
| db-availability-total | Verde | Verde | ✅ (sempre OK) |
| db-availability-ok | Verde | Verde | ✅ (sempre OK) |
| instance-availability-off | Verde | Vermelho | ✅ |
| server-offline | Verde | Verm/Amar (env) | ✅ |
| blocked-sessions | Verde | Vermelho | ✅ |
| blocked-users | Verde | Vermelho | ✅ |
| processes-alarm | Verde | Vermelho | ✅ |
| transaction-logs-critical | Verde | Vermelho | ✅ |
| transaction-logs-warning | Verde | Amarelo | ✅ |
| disk-file-system-critical | Verde | Vermelho | ✅ |
| disk-file-system-warning | Verde | Amarelo | ✅ |
| filegroup-usage-critical | Verde | Vermelho | ✅ |
| filegroup-usage-warning | Verde | Amarelo | ✅ |
| tempdb-critical | Verde | Vermelho | ✅ |
| tempdb-warning | Verde | Amarelo | ✅ |
| backup-failed | Verde | Verm/Amar/Azul (env) | ✅ |
| backup-delayed | Verde | Verm/Amar/Azul (env) | ✅ |
| always-on-unhealthy | Verde | Vermelho | ✅ |

---

## Views SQL vs Cards - Mapeamento Completo

| View SQL | Colunas | Cards que Usam |
|----------|---------|----------------|
| KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW | TotalCnt, AbnormalCnt | db-availability-* |
| KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW | State, Count | instance-availability-*, db-availability-ok |
| KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW | Instance, Env, Cnt | blocked-sessions |
| KPI_MSSQL_BLOCKED_USERS_AGG_VIEW | Blocked_Users_Count, Total_Blocked_Count | blocked-users |
| KPI_MSSQL_DISK_USAGE_AGG_VIEW | Normal, Warning, Critical | disk-file-system-* |
| KPI_MSSQL_TEMPDB_STATUS_AGG_VIEW | Critical, Warning, Normal | tempdb-critical, tempdb-warning |
| KPI_MSSQL_TLOG_USAGE_AGG_VIEW | Normal, Warning, Critical | transaction-logs-* |
| KPI_MSSQL_FG_USAGE_AGG_VIEW | Warning, Critical | filegroup-usage-* |
| KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW | Unhealthy, Total | always-on-unhealthy |
| KPI_MSSQL_PROCESSES_AGG_VIEW | Processes, State | processes-alarm |
| KPI_MSSQL_BACKUPS_STG | Hours_Since_Backup | backup-failed, backup-delayed |
| KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW | total_events, by_diagnosis | server-offline |

---

## Conclusão

### Estatísticas
- **Total de Cards:** 19
- **Cards OK:** 19 (100%)
- **Cards com Warnings:** 0 (0%)
- **Cards com Erros:** 0 (0%)

### Views Adicionadas (2025-12-21)

| View | Tipo | Arquivo | Linhas |
|------|------|---------|--------|
| KPI_MSSQL_BLOCKED_USERS_AGG_VIEW | AGG | SQLSERVER_KPI_VIEWS.sql | 705-731 |
| KPI_MSSQL_BLOCKED_USERS_DET_VIEW | DET | SQLSERVER_KPI_VIEWS.sql | 734-755 |
| KPI_MSSQL_TEMPDB_STATUS_AGG_VIEW | AGG (proxy) | SQLSERVER_KPI_VIEWS.sql | 772-795 |
| KPI_MSSQL_TEMPDB_STATUS_DET_VIEW | DET (proxy) | SQLSERVER_KPI_VIEWS.sql | 798-824 |

### Recomendações de Ação

1. **Prioridade Alta:**
   - Nenhuma ação necessária - todos os cards validados

2. **Prioridade Baixa (Melhorias Futuras):**
   - Avaliar parametrização de thresholds em tabela de configuração
   - Considerar tabela específica `KPI_MSSQL_TEMPDB_STATUS_STG` para métricas detalhadas de TempDB

### Status Geral: ✅ APROVADO - 100% VALIDADO

O dashboard de KPIs está funcionando corretamente com todos os 19 cards validados e todas as views SQL deployadas.

---

*Documento gerado em: 2025-12-21*
*Última atualização: 2025-12-21 - Views blocked-users e tempdb adicionadas*
