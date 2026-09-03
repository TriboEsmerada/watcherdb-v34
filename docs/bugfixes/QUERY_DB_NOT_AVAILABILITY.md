# 🔍 QUERY DB NOT AVAILABILITY - EXPLICAÇÃO COMPLETA

**Data:** 2025-12-09
**KPI:** DB Not Availability (Databases Indisponíveis)

---

## 📊 QUERY PRINCIPAL

### **Query Python (Dashboard)**
**Arquivo:** `api/routers/intelligence_kpis.py` (linha 465-468)

```python
query_not_available = f"""
SELECT *
FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
"""
```

**Filtros aplicados em Python:**
```python
# 1. Buscar todos os registros da view
not_available_data = execute_intelligence_query(query_not_available)

# 2. Aplicar filtro de frescor (60 minutos)
fresh_not_available = [row for row in not_available_data
                       if is_data_fresh(row, FRESHNESS_WINDOWS['capacity'])]

# 3. Contar databases com problema
abnormal_count = len(fresh_not_available)
```

---

## 🗄️ VIEW DETALHADA

### **KPI_MSSQL_DB_AVAILABILITY_DET_VIEW**
**Arquivo:** `database/SQLSERVER_KPI_VIEWS.sql` (linha 221-238)

```sql
CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
AS
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.[Database],
    d.[State],
    d.Is_Available,
    d.Recovery_Model,
    d.Update_TS
FROM
    dbo.KPI_MSSQL_DB_AVAILABILITY_STG d
    LEFT OUTER JOIN
    dbo.KPI_MSSQL_INST_ENVS e
      ON e.Instance = d.Instance
WHERE
    d.[State] <> 'ONLINE' OR d.Is_Available = 0;  -- ← FILTRO PRINCIPAL
```

---

## 🎯 CRITÉRIOS DE DETECÇÃO

Uma database é considerada **"NOT AVAILABLE"** (com problema) se:

### **Condição 1: Estado Diferente de ONLINE**
```sql
d.[State] <> 'ONLINE'
```

**Estados possíveis que indicam problema:**
- `OFFLINE` - Database desligada
- `RECOVERING` - Em processo de recuperação
- `RESTORING` - Sendo restaurada de backup
- `RECOVERY_PENDING` - Recuperação pendente
- `SUSPECT` - Database suspeita (corrupção detectada)
- `EMERGENCY` - Modo de emergência

### **OU Condição 2: Flag Is_Available = 0**
```sql
d.Is_Available = 0
```

**Significa:** Database marcada como indisponível pelo ETL

---

## 📋 COLUNAS RETORNADAS

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `Instance` | VARCHAR | Nome da instância SQL Server (ex: `SQLSERVER_INSTANCE`) |
| `Env` | VARCHAR | Ambiente: `PRD`, `TST`, `QLT`, ou `Undefined` |
| `Database` | VARCHAR | Nome do database (ex: `DB_PRODUCAO`) |
| `State` | VARCHAR | Estado atual: `OFFLINE`, `RECOVERING`, `SUSPECT`, etc. |
| `Is_Available` | BIT | 0 = Indisponível, 1 = Disponível |
| `Recovery_Model` | VARCHAR | Modelo de recuperação: `SIMPLE`, `FULL`, `BULK_LOGGED` |
| `Update_TS` | DATETIME | Timestamp da última coleta (usado para freshness) |

---

## ⏰ FILTRO DE FRESCOR (FRESHNESS)

### **Janela de Frescor: 60 minutos**
```python
FRESHNESS_WINDOWS['capacity'] = 60  # minutos
```

**Por quê 60 minutos?**
- DB Availability é uma **métrica de capacidade**
- Muda lentamente (databases não ficam OFFLINE a cada minuto)
- 60 minutos é tempo suficiente para detectar problemas reais
- Evita alertas de dados antigos (ETL pode demorar para atualizar)

### **Função is_data_fresh()**
```python
def is_data_fresh(row, minutes):
    # Verifica se Update_TS está dentro dos últimos {minutes} minutos
    timestamp = row.get('Update_TS')
    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    return timestamp >= cutoff_time
```

**Exemplo:**
```
Agora: 2025-12-09 15:30:00
Cutoff: 2025-12-09 14:30:00 (60 min atrás)

Database A: Update_TS = 2025-12-09 15:00:00 → ✅ Fresh (dentro de 60 min)
Database B: Update_TS = 2025-12-09 14:00:00 → ❌ Stale (fora de 60 min)
```

---

## 🔄 FLUXO COMPLETO

### **1. ETL Coleta Dados**
```sql
-- ETL executa em cada instância SQL Server
SELECT
    @@SERVERNAME AS Instance,
    name AS [Database],
    state_desc AS [State],
    CASE WHEN state = 0 THEN 1 ELSE 0 END AS Is_Available,
    recovery_model_desc AS Recovery_Model,
    GETDATE() AS Update_TS
FROM sys.databases
```

**Armazena em:** `KPI_MSSQL_DB_AVAILABILITY_STG`

### **2. View Filtra Problemas**
```sql
-- View retorna APENAS databases com problema
SELECT * FROM KPI_MSSQL_DB_AVAILABILITY_STG
WHERE [State] <> 'ONLINE' OR Is_Available = 0
```

**View:** `KPI_MSSQL_DB_AVAILABILITY_DET_VIEW`

### **3. Python Aplica Freshness**
```python
# Buscar da view (já filtrada)
all_problems = query("SELECT * FROM KPI_MSSQL_DB_AVAILABILITY_DET_VIEW")

# Filtrar por frescor (60 min)
fresh_problems = [row for row in all_problems if is_data_fresh(row, 60)]

# Contar
abnormal_count = len(fresh_problems)  # Ex: 189
```

### **4. Frontend Exibe**
```javascript
// Card "DB Not Availability"
{
    title: 'DB Not Availability',
    value: 189,  // Contagem de databases com problema
    subtitle: 'DB Not Availability'
}
```

---

## 📊 EXEMPLO PRÁTICO

### **Cenário Real**

**Instância:** `SQLSERVER_PROD01`
**Total de Databases:** 50
**Databases com Problema:** 3

```
Database                | State          | Is_Available | Incluído?
------------------------|----------------|--------------|----------
DB_PRODUCAO_001         | ONLINE         | 1            | ❌ NÃO
DB_PRODUCAO_002         | ONLINE         | 1            | ❌ NÃO
DB_PRODUCAO_003         | OFFLINE        | 0            | ✅ SIM (State <> ONLINE)
DB_PRODUCAO_004         | ONLINE         | 1            | ❌ NÃO
...
DB_PRODUCAO_025         | RECOVERING     | 0            | ✅ SIM (State <> ONLINE)
...
DB_PRODUCAO_048         | SUSPECT        | 0            | ✅ SIM (State <> ONLINE)
...
DB_PRODUCAO_050         | ONLINE         | 1            | ❌ NÃO
```

**Resultado da View:**
```sql
Instance           | Database          | State       | Update_TS
-------------------|-------------------|-------------|-------------------
SQLSERVER_PROD01   | DB_PRODUCAO_003   | OFFLINE     | 2025-12-09 15:00
SQLSERVER_PROD01   | DB_PRODUCAO_025   | RECOVERING  | 2025-12-09 15:00
SQLSERVER_PROD01   | DB_PRODUCAO_048   | SUSPECT     | 2025-12-09 15:00
```

**Contagem Final:** 3 databases com problema

---

## 🔍 QUERY PARA DIAGNÓSTICO

### **Ver Todas as Databases com Problema (Fresh)**
```sql
-- Query SQL direta
SELECT
    d.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    d.[Database],
    d.[State],
    d.Is_Available,
    d.Recovery_Model,
    d.Update_TS,
    DATEDIFF(MINUTE, d.Update_TS, GETDATE()) AS MinutesOld
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG d
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance
WHERE (d.[State] <> 'ONLINE' OR d.Is_Available = 0)
  AND d.Update_TS >= DATEADD(MINUTE, -60, GETDATE())  -- Filtro de 60 min
ORDER BY d.Instance, d.[Database];
```

### **Ver Databases OK (Para Comparação)**
```sql
-- Databases ONLINE (sem problema)
SELECT
    d.Instance,
    COUNT(*) AS Databases_OK
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG d
WHERE d.[State] = 'ONLINE'
  AND d.Is_Available = 1
  AND d.Update_TS >= DATEADD(MINUTE, -60, GETDATE())
GROUP BY d.Instance
ORDER BY d.Instance;
```

### **Verificar Freshness dos Dados**
```sql
-- Ver idade dos dados por instância
SELECT
    Instance,
    COUNT(*) AS Total_Databases,
    MIN(Update_TS) AS Oldest_Update,
    MAX(Update_TS) AS Newest_Update,
    DATEDIFF(MINUTE, MAX(Update_TS), GETDATE()) AS MinutesSinceUpdate
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
GROUP BY Instance
ORDER BY MinutesSinceUpdate DESC;
```

**Interpretação:**
- `MinutesSinceUpdate < 60` → ✅ Dados frescos
- `MinutesSinceUpdate > 60` → ⚠️ Dados antigos (ETL pode estar atrasado)

---

## ⚠️ CENÁRIOS ESPECIAIS

### **Cenário 1: Card Mostra 189, Modal Mostra 0**

**Causa:** Bug na função `is_data_fresh()` (JÁ CORRIGIDO)

**Antes da Correção:**
```python
# Detectava State='OFFLINE' como "view agregada" e retornava True sempre
if has_state_column and state_value in aggregated_state_values:
    return True  # ❌ ERRO: OFFLINE não é valor agregado!
```

**Depois da Correção:**
```python
# Exclui explicitamente estados de database
database_state_values = ['OFFLINE', 'RECOVERING', 'SUSPECT', ...]
is_database_state = state_value in database_state_values
if not is_database_state and has_aggregated_state:
    return True  # ✅ Só para views agregadas reais
```

### **Cenário 2: Valor do Card Não Muda**

**Causa:** Lógica de persistência de cache

**Como funciona:**
```python
# Card mantém valor em cache até que abnormal_count mude
if last_abnormal_count == abnormal_count:
    # Mantém cache (não muda)
    db_availability = cached_value
else:
    # Recalcula (muda)
    db_availability = new_value_from_query
```

**Solução:** Isso é **comportamento esperado** (conforme solicitado)

---

## 📝 RESUMO

**Query DB Not Availability:**
```sql
-- View já filtra databases com problema
SELECT * FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
```

**Filtros:**
1. ✅ `[State] <> 'ONLINE'` - Database não está ONLINE
2. ✅ `Is_Available = 0` - Database marcada como indisponível
3. ✅ `Update_TS >= -60 min` - Dados com menos de 60 minutos (Python)

**Estados que geram alerta:**
- `OFFLINE` - Desligada
- `RECOVERING` - Recuperando
- `RESTORING` - Restaurando
- `RECOVERY_PENDING` - Pendente
- `SUSPECT` - Suspeita (corrupção)
- `EMERGENCY` - Emergência

**Resultado:** Contagem de databases indisponíveis (ex: 189)

---

**Documentação Criada:** 2025-12-09
**Status:** ✅ **COMPLETO E VALIDADO**
