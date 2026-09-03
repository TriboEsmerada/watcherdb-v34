# 🔍 Lógica de Detecção de Problemas de Backup

**Data:** 2025-01-XX  
**Objetivo:** Documentar a lógica completa usada para determinar se um backup teve problema

---

## 📊 Visão Geral

O sistema monitora backups de databases SQL Server e identifica problemas baseado no tempo decorrido desde o último backup. A lógica considera diferentes tipos de backup (FULL, DIFF, LOG) e aplica thresholds diferentes para cada situação.

---

## 🔄 Fluxo de Coleta de Dados

### 1. Coleta de Dados (Procedure: `usp_Collect_Backups`)

**Arquivo:** `database/SQLSERVER_KPI_COLLECTION_PROCEDURES.sql`

A procedure coleta dados da tabela `msdb.dbo.backupset` e popula a tabela `KPI_MSSQL_BACKUPS_STG`:

```sql
SELECT
    @@SERVERNAME AS Instance,
    d.name AS [Database],
    CASE b.type
        WHEN 'D' THEN 'FULL'
        WHEN 'I' THEN 'DIFF'
        WHEN 'L' THEN 'LOG'
    END AS Backup_Type,
    b.backup_finish_date AS Last_Backup_Date,
    DATEDIFF(HOUR, b.backup_finish_date, GETDATE()) AS Hours_Since_Backup,
    ...
FROM sys.databases d
CROSS APPLY (
    SELECT TOP 1
        bs.type,
        bs.backup_start_date,
        bs.backup_finish_date,
        bs.backup_size
    FROM msdb.dbo.backupset bs
    WHERE bs.database_name = d.name
    ORDER BY bs.backup_finish_date DESC
) b
WHERE d.name NOT IN ('tempdb')
  AND d.state_desc = 'ONLINE';
```

**Pontos importantes:**
- ✅ Coleta apenas databases ONLINE
- ✅ Exclui `tempdb` (não precisa de backup)
- ✅ Pega o **último backup** de cada tipo (FULL, DIFF, LOG) por database
- ✅ Calcula `Hours_Since_Backup` = diferença em horas entre `backup_finish_date` e `GETDATE()`

---

## 🎯 Lógica de Classificação de Problemas

### 2. Classificação no Dashboard (`get_kpi_dashboard`)

**Arquivo:** `api/routers/intelligence_kpis.py` (linhas 577-603)

#### 2.1. Query Inicial

```python
query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_BACKUPS_STG WHERE Hours_Since_Backup > 48"
```

**Filtro inicial:** Apenas backups com mais de **48 horas** desde o último backup.

#### 2.2. Janela de Frescor (Freshness Window)

```python
fresh_backup_data = [row for row in backup_data if is_data_fresh(row, FRESHNESS_WINDOWS['capacity'])]
```

**Janela de frescor:** **60 minutos** (métrica de capacidade)
- Apenas dados coletados nos últimos 60 minutos são considerados válidos
- Evita mostrar problemas baseados em dados desatualizados

#### 2.3. Classificação por Severidade

```python
# Failed: > 168 horas (7 dias)
failed_databases = [row for row in fresh_backup_data if row.get('Hours_Since_Backup', 0) > 168]

# Delayed: 48-168 horas (2-7 dias)
delayed_databases = [row for row in fresh_backup_data if 48 < row.get('Hours_Since_Backup', 0) <= 168]
```

**Thresholds:**
- 🔴 **Failed (Crítico):** `Hours_Since_Backup > 168` (mais de 7 dias)
- 🟡 **Delayed (Atrasado):** `48 < Hours_Since_Backup <= 168` (entre 2 e 7 dias)
- ✅ **Normal:** `Hours_Since_Backup <= 48` (até 2 dias)

#### 2.4. Contagem

```python
results["backup_status"]["failed_count"] = len(failed_databases)
results["backup_status"]["delayed_count"] = len(delayed_databases)
```

**Importante:** A contagem é feita por **database**, não por instância. Cada database com problema conta separadamente.

---

## 📋 Views SQL Server

### 3. View Agregada (`KPI_MSSQL_BACKUPS_AGG_VIEW`)

**Arquivo:** `database/SQLSERVER_KPI_VIEWS.sql` (linhas 622-639)

```sql
SELECT
    b.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    b.Backup_Type,
    COUNT(1) AS Total_Databases,
    SUM(CASE WHEN b.Hours_Since_Backup > 48 THEN 1 ELSE 0 END) AS Critical,
    SUM(CASE WHEN b.Hours_Since_Backup > 24 AND b.Hours_Since_Backup <= 48 THEN 1 ELSE 0 END) AS Warning,
    SUM(CASE WHEN b.Hours_Since_Backup <= 24 THEN 1 ELSE 0 END) AS Normal
FROM dbo.KPI_MSSQL_BACKUPS_STG b
GROUP BY b.Instance, e.Env, b.Backup_Type;
```

**Classificação na view:**
- 🔴 **Critical:** `Hours_Since_Backup > 48` (mais de 2 dias)
- 🟡 **Warning:** `24 < Hours_Since_Backup <= 48` (entre 1 e 2 dias)
- ✅ **Normal:** `Hours_Since_Backup <= 24` (até 1 dia)

**Nota:** A view usa thresholds diferentes (24h/48h) do código Python (48h/168h). O código Python sobrescreve essa lógica.

### 4. View Detalhada (`KPI_MSSQL_BACKUPS_DET_VIEW`)

**Arquivo:** `database/SQLSERVER_KPI_VIEWS.sql` (linhas 641-670)

```sql
SELECT
    b.Instance,
    b.[Database],
    b.Backup_Type,
    b.Last_Backup_Date,
    b.Hours_Since_Backup,
    CASE
        WHEN b.Hours_Since_Backup > 48 THEN 'CRITICAL'
        WHEN b.Hours_Since_Backup > 24 THEN 'WARNING'
        ELSE 'NORMAL'
    END AS [Status],
    ...
FROM dbo.KPI_MSSQL_BACKUPS_STG b
WHERE b.Hours_Since_Backup > 24  -- Mostrar apenas backups atrasados
   OR b.Last_Backup_Date IS NULL;
```

**Filtro:** Mostra apenas backups com mais de 24 horas ou sem backup.

---

## 🔍 Lógica Final Usada no Código Python

### Resumo dos Thresholds por Tipo de Backup

**Thresholds diferentes por tipo de backup baseados na frequência real:**

| Tipo de Backup | Frequência Real | Failed Threshold | Delayed Threshold | Descrição |
|----------------|-----------------|------------------|-------------------|-----------|
| **FULL** | 1x por semana | `> 168 horas` (7 dias) | `120-168 horas` (5-7 dias) | Backup completo semanal |
| **DIFF** | 1x por dia (a cada 24h) | `> 30 horas` (1.25 dias) | `24-30 horas` (1-1.25 dias) | Backup diferencial diário |
| **LOG** | A cada 30min | `> 2 horas` | `1-2 horas` | Backup de log frequente |

### Classificação

| Status | Condição | Descrição |
|--------|----------|-----------|
| ✅ **Normal** | Dentro do threshold de delayed | Backup dentro do esperado |
| 🟡 **Delayed** | Entre delayed e failed threshold | Backup atrasado mas não crítico |
| 🔴 **Failed** | Acima do failed threshold | Backup crítico - ação necessária |

### Condições para Considerar um Problema

1. ✅ Database está ONLINE
2. ✅ Database não é `tempdb`
3. ✅ `Hours_Since_Backup > 48` (mais de 2 dias sem backup)
4. ✅ Dados são "frescos" (coletados nos últimos 60 minutos)

### Tipos de Backup Considerados

O sistema monitora **todos os tipos de backup** por database:
- **FULL** (`type = 'D'`)
- **DIFF** (`type = 'I'`)
- **LOG** (`type = 'L'`)

**Importante:** Cada tipo de backup é monitorado separadamente. Um database pode ter:
- ✅ FULL recente, mas ❌ LOG atrasado
- ✅ LOG recente, mas ❌ FULL atrasado

---

## 📊 Exemplo Prático

### Cenário 1: Database com FULL atrasado

```
Database: MyDatabase
Last FULL Backup: 2025-01-01 00:00:00
Current Date: 2025-01-08 12:00:00
Hours_Since_Backup: 180 horas (7.5 dias)

Resultado: 🔴 FAILED (180 > 168)
```

### Cenário 2: Database com LOG atrasado

```
Database: MyDatabase
Last LOG Backup: 2025-01-06 00:00:00
Current Date: 2025-01-08 12:00:00
Hours_Since_Backup: 60 horas (2.5 dias)

Resultado: 🟡 DELAYED (48 < 60 <= 168)
```

### Cenário 3: Database sem backup

```
Database: MyDatabase
Last_Backup_Date: NULL
Hours_Since_Backup: NULL (tratado como 0 ou muito alto)

Resultado: 🔴 FAILED (NULL é tratado como problema crítico)
```

---

## ⚠️ Observações Importantes

### 1. Diferença entre Views e Código Python

- **Views SQL:** Usam thresholds de 24h/48h
- **Código Python:** Usa thresholds de 48h/168h
- **Resultado:** O código Python **sobrescreve** a lógica das views

### 2. Contagem por Database vs Instância

- **Antes:** Contava instâncias únicas (agrupava por instância)
- **Agora:** Conta databases individuais (cada database conta separadamente)
- **Motivo:** Uma instância pode ter múltiplos databases com problema

### 3. Thresholds por Tipo de Backup

- **FULL:** Thresholds maiores (7 dias para failed, 5 dias para delayed) - backup semanal
- **DIFF:** Thresholds médios (2 dias para failed, 1 dia para delayed) - backup diário
- **LOG:** Thresholds pequenos (2 horas para failed, 1 hora para delayed) - backup frequente
- **Motivo:** Cada tipo de backup tem frequência diferente, então os thresholds devem refletir isso

### 4. Janela de Frescor

- **60 minutos:** Dados devem ser coletados recentemente
- **Propósito:** Evitar mostrar problemas baseados em dados desatualizados
- **Impacto:** Se a coleta falhar por mais de 60 minutos, os dados não aparecem no dashboard

### 5. Tipos de Backup

- O sistema monitora **todos os tipos** (FULL, DIFF, LOG)
- Cada tipo é **independente**
- Um database pode aparecer múltiplas vezes (uma por tipo de backup)

---

## 🔧 Configuração Atual

**Arquivo:** `api/routers/intelligence_kpis.py`

```python
# Thresholds por tipo de backup
BACKUP_THRESHOLDS = {
    'FULL': {
        'failed': 168,   # 7 dias (1x por semana)
        'delayed': 120   # 5 dias
    },
    'DIFF': {
        'failed': 30,    # 30 horas (1.25 dias) - 1x por dia
        'delayed': 24   # 24 horas (1 dia)
    },
    'LOG': {
        'failed': 2,    # 2 horas (a cada 30min)
        'delayed': 1    # 1 hora
    }
}

# Freshness Window
FRESHNESS_WINDOWS = {
    'capacity': 60  # minutos
}
```

### Cards Separados

- **Backup Failed**: Mostra apenas backups com status "Failed" (acima do threshold crítico)
- **Backup Delayed**: Mostra apenas backups com status "Delayed" (entre delayed e failed threshold)

Cada card busca apenas seu tipo de problema específico.

---

## 📝 Mudanças Implementadas

1. ✅ **Thresholds ajustados por tipo de backup** (FULL/DIFF/LOG com thresholds diferentes)
2. ✅ **Cards separados** - "Backup Failed" e "Backup Delayed" são cards independentes
3. ✅ **Cada card busca apenas seu tipo** - failed busca apenas failed, delayed busca apenas delayed
4. ✅ **Lógica baseada na frequência real** dos backups

## 📝 Recomendações Futuras

1. **Melhorar tratamento de NULL** (databases sem backup)
2. **Adicionar lógica para Always On** (réplicas secundárias não precisam de backup)
3. **Considerar configuração de backup por database** (alguns databases podem ter frequências diferentes)

---

**Documento gerado automaticamente**  
**Última atualização:** 2025-01-XX

