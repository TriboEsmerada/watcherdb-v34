# 📊 Ajuste dos Cards do KPI

**Data:** 2025-01-XX  
**Objetivo:** Ajustar os cards do dashboard para exibir apenas os 10 KPIs ativos e remover os 5 KPIs removidos

---

## ✅ KPIs Ativos (10) - Mantidos

1. **alwayson_status** → `always-on-unhealthy`
2. **blocked_sessions** → `blocked-sessions`
3. **blocked_users** → `blocked-users`
4. **db_availability** → `db-availability-abnormal`, `db-availability-total`, `db-availability-ok`
5. **disk_usage** → `disk-file-system-critical`, `disk-file-system-warning`
6. **filegroup_usage** → `filegroup-usage-warning`, `filegroup-usage-critical`
7. **instance_availability** → `instance-availability-off`
8. **processes** → `processes-alarm`
9. **tlog_usage** → `transaction-logs-critical`, `transaction-logs-warning`
10. **backups** → `backup-status-failed`, `backup-status-delayed` (NOVO)

---

## ❌ KPIs Removidos (5) - Excluídos

1. **deadlocks** → `deadlocks` ❌ Removido
2. **service_status** → `service-status-down` ❌ Removido
3. **errorlog** → `error-log-critical`, `error-log-warning` ❌ Removido
4. **db_io_stats** → `db-io-stats-read`, `db-io-stats-write` ❌ Removido
5. **long_locks** → `lock-count-warning`, `lock-count-critical` ❌ Removido

---

## 🔧 Mudanças Realizadas

### 1. Removidos Cards do KPI_METADATA

**Arquivo:** `templates/watcherdb_portal.html`

**Cards Removidos:**
- `lock-count-warning`
- `lock-count-critical`
- `service-status-down`
- `deadlocks`
- `error-log-critical`
- `error-log-warning`
- `db-io-stats-read`
- `db-io-stats-write`

### 2. Adicionados Cards de Backup

**Cards Adicionados:**
- `backup-status-failed` - Backup Status (Failed)
- `backup-status-delayed` - Backup Status (Delayed)

**Configuração:**
```javascript
'backup-status-failed': {
    id: 'backup-status-failed',
    key: 'backup_status.failed_count',
    title: 'Backup Status',
    subtitle: 'Failed',
    category: 'Espaço',
    icon: 'fa-database',
    kpiType: 'backup-status',
    modalTitle: 'Backup Status - Failed',
    order: 13,
    getValue: (data) => data.backup_status?.failed_count || 0,
    getCardClass: (data) => getCardClass(data.backup_status?.failed_count || 0),
    getValueColor: (data) => getValueColor(data.backup_status?.failed_count || 0)
},
'backup-status-delayed': {
    id: 'backup-status-delayed',
    key: 'backup_status.delayed_count',
    title: 'Backup Status',
    subtitle: 'Delayed',
    category: 'Espaço',
    icon: 'fa-database',
    kpiType: 'backup-status',
    modalTitle: 'Backup Status - Delayed',
    order: 14,
    getValue: (data) => data.backup_status?.delayed_count || 0,
    getCardClass: (data) => getCardClass(data.backup_status?.delayed_count || 0, 0, 0),
    getValueColor: (data) => getValueColor(data.backup_status?.delayed_count || 0, 0, 0)
}
```

### 3. Atualizado Mapeamento de KPIs

**Arquivo:** `templates/watcherdb_portal.html` (linha ~14963)

**Removidos do mapeamento:**
- `'lock-count-warning': 'lock_count'`
- `'lock-count-critical': 'lock_count'`
- `'deadlocks': 'deadlocks'`
- `'service-status-down': 'service_status'`
- `'db-io-stats-read': 'db_io_stats'`
- `'db-io-stats-write': 'db_io_stats'`
- `'error-log-critical': 'error_log'`
- `'error-log-warning': 'error_log'`

**Adicionados ao mapeamento:**
- `'backup-status-failed': 'backup_status'`
- `'backup-status-delayed': 'backup_status'`

### 4. Atualizado Mapeamento de Queries

**Arquivo:** `templates/watcherdb_portal.html` (linha ~15520)

**Removidos:**
- `'lock-count': 'blocking'`
- `'error-log': 'sessions'`
- `'db-io-stats': 'sessions'`

**Mantidos:**
- `'backup-status': 'backup'` ✅

### 5. Removido Tratamento Específico de Error Log

**Arquivo:** `templates/watcherdb_portal.html` (linha ~16088)

Removido o bloco completo de tratamento específico para Error Log no modal de instâncias problemáticas.

---

## 📋 Resumo dos Cards Finais

### Disponibilidade (4 cards)
1. `db-availability-abnormal` - DB Not Availability
2. `db-availability-total` - DB Availability (Total Count)
3. `db-availability-ok` - Instâncias OK
4. `instance-availability-off` - Instances Off

### Performance (3 cards)
5. `blocked-sessions` - Blocked Sessions
6. `blocked-users` - Blocked Users
7. `processes-alarm` - Processes Alarm

### Espaço (6 cards)
8. `transaction-logs-critical` - Transaction Logs (Critical)
9. `transaction-logs-warning` - Transaction Logs (Warning)
10. `disk-file-system-critical` - Disk File System (Critical)
11. `disk-file-system-warning` - Disk File System (Warning)
12. `filegroup-usage-warning` - FileGroups Usage (Warning)
13. `filegroup-usage-critical` - FileGroups Usage (Critical)
14. `backup-status-failed` - Backup Status (Failed) ⭐ NOVO
15. `backup-status-delayed` - Backup Status (Delayed) ⭐ NOVO

### Alta Disponibilidade (1 card)
16. `always-on-unhealthy` - Always On (UnHealthy)

**Total:** 14 cards (10 KPIs principais, alguns com múltiplos cards por nível de severidade)

---

## ✅ Status

- ✅ Cards removidos: 8 cards (5 KPIs)
- ✅ Cards adicionados: 2 cards (backup status)
- ✅ Mapeamentos atualizados
- ✅ Tratamentos específicos removidos

---

**Documento gerado automaticamente**  
**Última atualização:** 2025-01-XX

