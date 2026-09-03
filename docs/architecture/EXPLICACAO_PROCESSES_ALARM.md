# 📊 ENTENDENDO O KPI "PROCESSES ALARM"

**Data:** 2025-12-09
**Status:** ⚠️ **COM BUGS** (mesma inconsistência do DB Not Availability)

---

## 🎯 O QUE É O PROCESSES ALARM?

### Objetivo
Monitorar a **contagem de processos (sessões ativas)** em cada instância SQL Server e alertar quando houver **sobrecarga** de processos.

### O Que Ele Detecta

| Situação | Contagem | Estado | Ação |
|----------|----------|--------|------|
| **Normal** | < 500 processos | `NORMAL` | ✅ Nenhuma ação necessária |
| **Warning** | 500-999 processos | `WARNING` | 🟡 Monitorar - pode indicar sobrecarga |
| **Critical** | ≥ 1000 processos | `CRITICAL` | 🔴 ATENÇÃO - possível problema de performance |

---

## 🔍 COMO FUNCIONA

### 1️⃣ Coleta de Dados (ETL)

O ETL coleta informações de processos ativos de cada instância:

```sql
-- Exemplo de coleta
SELECT
    @@SERVERNAME AS Instance,
    session_id AS Session_Id,
    login_name AS [User],
    DB_NAME(database_id) AS [Database],
    status AS [Status],
    command AS Command,
    GETDATE() AS Update_TS
FROM sys.dm_exec_sessions WITH(NOLOCK)
WHERE is_user_process = 1  -- Apenas processos de usuário
```

**Armazenado em:** `KPI_MSSQL_PROCESSES_STG`

### 2️⃣ View Agregada

A view `KPI_MSSQL_PROCESSES_AGG_VIEW` conta quantos processos cada instância tem:

```sql
CREATE VIEW dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
AS
SELECT
    p.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(DISTINCT p.Session_Id) AS Processes,  -- ← CONTA PROCESSOS
    CASE
        WHEN COUNT(DISTINCT p.Session_Id) >= 1000 THEN 'CRITICAL'  -- ← ≥ 1000 = CRÍTICO
        WHEN COUNT(DISTINCT p.Session_Id) >= 500 THEN 'WARNING'    -- ← 500-999 = AVISO
        ELSE 'NORMAL'                                               -- ← < 500 = NORMAL
    END AS [State]
FROM dbo.KPI_MSSQL_PROCESSES_STG p
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = p.Instance
GROUP BY p.Instance, e.Env;
```

**Colunas Retornadas:**
- `Instance` - Nome da instância SQL Server
- `Env` - Ambiente (PRD/TST/QLT)
- `Processes` - **Contagem de processos ativos**
- `State` - Estado: `NORMAL`, `WARNING` ou `CRITICAL`

### 3️⃣ Query do Dashboard (Card)

**Arquivo:** `config/dashboard_kpis_queries.sql`
**Linha:** 248-250

```sql
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE Processes > 0;
```

**❌ PROBLEMA:** Esta query está **INCORRETA**!

A query deveria ser:
```sql
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE [State] IN ('WARNING', 'CRITICAL');  -- ✅ CORRETO
```

**Por quê?**
- `WHERE Processes > 0` → Retorna **TODAS** as instâncias (até as normais)
- `WHERE [State] IN ('WARNING', 'CRITICAL')` → Retorna **APENAS** as com problema

### 4️⃣ Implementação Python (Card)

**Arquivo:** `api/routers/intelligence_kpis.py`
**Linha:** 1220-1239

```python
# CARD - Dashboard
query = f"""
SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE [State] IN ('WARNING', 'CRITICAL')  -- ✅ CORRETO (Python está certo!)
"""
processes_data = execute_intelligence_query(query, raise_on_error=False) or []

# Aplicar filtro de frescor (60 minutos)
fresh_processes_data = [row for row in processes_data if is_data_fresh(row, 60)]

processes_count = len(fresh_processes_data)  # Contagem de instâncias com problema
results["processes_alarm"]["count"] = processes_count
```

**✅ O código Python está CORRETO** (usa `WHERE [State] IN ('WARNING', 'CRITICAL')`)

### 5️⃣ Implementação Python (Modal)

**Arquivo:** `api/routers/intelligence_kpis.py`
**Linha:** 1813-1828

```python
# MODAL - Detalhes
query = f"SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_PROCESSES_AGG_VIEW"
all_processes = execute_intelligence_query(query, raise_on_error=False) or []

# Filtrar manualmente
instances = []
for row in all_processes:
    row_keys_upper = [k.upper() for k in row.keys()]
    has_processes = False
    if 'PROCESS_COUNT' in row_keys_upper and row.get('Process_Count', 0) > 0:
        has_processes = True
    elif 'CNT' in row_keys_upper and row.get('Cnt', 0) > 0:
        has_processes = True
    elif 'COUNT' in row_keys_upper and row.get('Count', 0) > 0:
        has_processes = True
    if has_processes:
        instances.append(row)
```

**❌ PROBLEMA DETECTADO:**
O modal está procurando por colunas **ERRADAS**:
- Procura: `Process_Count`, `Cnt`, `Count`
- View tem: **`Processes`** e **`State`**

**Resultado:** Modal NUNCA encontra nada porque está procurando pelas colunas erradas!

---

## 🐛 BUGS IDENTIFICADOS

### Bug #1: Query SQL Documentada Incorreta ⚠️
**Arquivo:** `config/dashboard_kpis_queries.sql` (linha 250)
```sql
-- ❌ INCORRETO
WHERE Processes > 0;

-- ✅ CORRETO
WHERE [State] IN ('WARNING', 'CRITICAL');
```

### Bug #2: Modal Procura Colunas Erradas ❌
**Arquivo:** `api/routers/intelligence_kpis.py` (linha 1821-1826)
```python
# ❌ INCORRETO - Procura colunas que não existem
if 'PROCESS_COUNT' in row_keys_upper and row.get('Process_Count', 0) > 0:
    has_processes = True
elif 'CNT' in row_keys_upper and row.get('Cnt', 0) > 0:
    has_processes = True

# ✅ CORRETO - Deveria verificar o State
if 'STATE' in row_keys_upper and row.get('State', '') in ['WARNING', 'CRITICAL']:
    instances.append(row)
```

### Bug #3: Inconsistência Card vs Modal (Freshness) ⚠️
**Mesmo problema do DB Not Availability:**
- Card: Aplica `is_data_fresh()` → Pode retornar `True` ou `False` dependendo do timing
- Modal: Não aplica `is_data_fresh()` corretamente
- View tem coluna `State` com valor `NORMAL`/`WARNING`/`CRITICAL`
- Função `is_data_fresh()` detecta como "view agregada" e retorna `True` sempre
- **MAS** o filtro de `State` está sendo aplicado **antes** do freshness!

---

## ✅ CORREÇÃO NECESSÁRIA

### Correção #1: Atualizar Query SQL Documentada

**Arquivo:** `config/dashboard_kpis_queries.sql`

```sql
-- ============================================================================
-- 12. PROCESSES ALARM (Alarme de Processos)
-- ============================================================================
-- Retorna instâncias com contagem de processos anormal
-- WARNING: >= 500 processos
-- CRITICAL: >= 1000 processos
-- ============================================================================
-- Query agregada para dashboard
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE [State] IN ('WARNING', 'CRITICAL');  -- ✅ CORRIGIDO
GO
```

### Correção #2: Corrigir Modal (Procurar Colunas Corretas)

**Arquivo:** `api/routers/intelligence_kpis.py` (linha 1813-1828)

```python
elif kpi_type == "processes-alarm":
    # Buscar instâncias com problemas (State = WARNING ou CRITICAL)
    query = f"""
    SELECT * FROM {INTELLIGENCE_SCHEMA}.KPI_MSSQL_PROCESSES_AGG_VIEW
    WHERE [State] IN ('WARNING', 'CRITICAL')
    """
    all_processes = execute_intelligence_query(query, raise_on_error=False) or []

    # Aplicar filtro de frescor (60 minutos para capacidade)
    instances = [row for row in all_processes if is_data_fresh(row, FRESHNESS_WINDOWS['capacity'])]
```

**✅ Simples, direto e consistente com o card!**

---

## 📊 EXEMPLOS PRÁTICOS

### Cenário 1: Instância Normal
```
Instance: SQLSERVER01
Processes: 120
State: NORMAL

Resultado: NÃO aparece no card (está abaixo de 500)
```

### Cenário 2: Instância com Aviso
```
Instance: SQLSERVER02
Processes: 650
State: WARNING

Resultado: ✅ Aparece no card "Processes Alarm" (contagem: 1)
Modal: ✅ Mostra detalhes da instância
```

### Cenário 3: Instância Crítica
```
Instance: SQLSERVER03
Processes: 1500
State: CRITICAL

Resultado: ✅ Aparece no card "Processes Alarm" (contagem: 1)
Modal: ✅ Mostra detalhes da instância
Alerta: 🔴 CRÍTICO - Investigar imediatamente!
```

### Cenário 4: Múltiplas Instâncias
```
SQLSERVER01: 120 processos → State: NORMAL → ❌ Não conta
SQLSERVER02: 650 processos → State: WARNING → ✅ Conta (1)
SQLSERVER03: 1500 processos → State: CRITICAL → ✅ Conta (2)
SQLSERVER04: 250 processos → State: NORMAL → ❌ Não conta

Total no Card: 2 instâncias com problema
Modal: Mostra SQLSERVER02 e SQLSERVER03
```

---

## 🎯 POR QUE É IMPORTANTE?

### Problemas que Indica

1. **Vazamento de conexões** - Aplicação não fecha conexões
2. **Queries lentas** - Processos acumulando enquanto aguardam
3. **Bloqueios em cascata** - Muitos processos esperando locks
4. **Ataques DDoS** - Muitas conexões simultâneas maliciosas
5. **Mal dimensionamento** - Servidor sem capacidade para carga

### Ações Recomendadas

#### Para WARNING (500-999 processos):
1. 🔍 Monitorar nos próximos 30 minutos
2. 📊 Verificar queries de longa duração
3. 🔒 Verificar se há bloqueios
4. 📈 Analisar tendência (crescendo ou estável?)

#### Para CRITICAL (≥ 1000 processos):
1. 🚨 **ATENÇÃO IMEDIATA** - Possível problema grave
2. 🔍 Identificar top queries consumindo recursos
3. 🔒 Verificar bloqueios em cascata
4. 🛑 Considerar kill de sessões problemáticas
5. 📞 Escalar para DBA se necessário
6. 🔄 Reiniciar aplicação se for vazamento de conexão

---

## 🔧 QUERY ÚTEIS PARA DIAGNÓSTICO

### Ver Contagem Atual de Processos
```sql
-- Ver dados brutos da view agregada
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
ORDER BY Processes DESC;

-- Ver apenas instâncias com problemas
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE [State] IN ('WARNING', 'CRITICAL')
ORDER BY Processes DESC;
```

### Ver Detalhes dos Processos (Por Usuário/Database)
```sql
-- Ver quem está gerando mais processos
SELECT *
FROM dbo.KPI_MSSQL_PROCESSES_DET_VIEW
WHERE Instance = 'SQLSERVER02'  -- Substituir pelo servidor problemático
ORDER BY Current_Count DESC;

-- Exemplo de resultado:
-- Login_Name      | Database  | Status    | Current_Count
-- APP_USER_01     | DB_PROD   | RUNNING   | 350  ← Este usuário tem 350 conexões!
-- APP_USER_02     | DB_PROD   | SLEEPING  | 150
-- MONITORING_USER | master    | RUNNING   | 10
```

### Ver Processos Ativos em Tempo Real (Direto do SQL Server)
```sql
-- Query para executar diretamente na instância problemática
SELECT
    DB_NAME(database_id) AS [Database],
    login_name AS [User],
    status,
    COUNT(*) AS ProcessCount
FROM sys.dm_exec_sessions WITH(NOLOCK)
WHERE is_user_process = 1
GROUP BY database_id, login_name, status
ORDER BY COUNT(*) DESC;
```

---

## ✅ CHECKLIST DE CORREÇÃO

- [x] Entendido o que é o KPI Processes Alarm
- [x] Identificados os bugs (Query SQL + Modal)
- [ ] Corrigir query SQL documentada
- [ ] Corrigir código Python do modal
- [ ] Testar card vs modal (valores consistentes)
- [ ] Validar com dados reais
- [ ] Documentar correções

---

## 📝 RESUMO

**O QUE É:**
- KPI que monitora **sobrecarga de processos** em instâncias SQL Server

**O QUE MOSTRA:**
- **Contagem de instâncias** com ≥ 500 processos ativos

**THRESHOLDS:**
- `NORMAL`: < 500 processos ✅
- `WARNING`: 500-999 processos 🟡
- `CRITICAL`: ≥ 1000 processos 🔴

**BUGS ENCONTRADOS:**
1. ❌ Query SQL documentada usa `WHERE Processes > 0` (incorreto)
2. ❌ Modal procura colunas erradas (`Process_Count` ao invés de `Processes` e `State`)
3. ⚠️ Inconsistência card vs modal (mesmo problema do DB Not Availability)

**CORREÇÃO:**
- Usar `WHERE [State] IN ('WARNING', 'CRITICAL')` em ambos
- Aplicar `is_data_fresh()` consistentemente
- Seguir mesmo padrão dos outros KPIs

---

**Próximo Passo:** Aplicar as correções e testar! 🚀
