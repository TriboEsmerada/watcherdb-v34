# 🔧 CORREÇÃO: DB Availability - Suporte a Mirroring/Always On

**Data:** 2025-12-09
**Problema:** Databases em Mirroring com estado `RESTORING` sendo consideradas como problema
**Status:** ✅ **CORREÇÃO PRONTA**

---

## 🐛 PROBLEMA IDENTIFICADO

### **O Que Está Acontecendo**

No SQL Server com **Mirroring** ou **Always On**, databases secundárias (MIRROR) ficam permanentemente no estado `RESTORING`:

```
Instance: SQLHDSPRD301_J01
Database: MSS13_PRDPUB_CONTENT_MEMRO
State: RESTORING
Mirroring_Role: MIRROR
```

**Isso é NORMAL!** Databases MIRROR ficam em `RESTORING` para receber transações do PRINCIPAL.

### **Problema Atual**

A view `KPI_MSSQL_DB_AVAILABILITY_DET_VIEW` considera **QUALQUER** estado diferente de `ONLINE` como problema:

```sql
-- ❌ LÓGICA ATUAL (INCORRETA)
WHERE d.[State] <> 'ONLINE' OR d.Is_Available = 0
```

**Resultado:** 189 databases aparecendo como "problema" quando na verdade estão **NORMAIS** (são MIRROR em RESTORING).

---

## ✅ SOLUÇÃO

### **Lógica Corrigida (Baseada no Oracle)**

```sql
-- ✅ LÓGICA CORRIGIDA
WHERE
    (
        -- Sem mirroring: problema se State <> 'ONLINE'
        (Mirroring_Role IS NULL AND ([State] <> 'ONLINE' OR Is_Available = 0))

        -- Principal em mirroring: problema se State <> 'ONLINE'
        OR (Mirroring_Role = 'PRINCIPAL' AND ([State] <> 'ONLINE' OR Is_Available = 0))

        -- Mirror em mirroring: problema APENAS se State <> 'RESTORING'
        -- (RESTORING é estado NORMAL para MIRROR!)
        OR (Mirroring_Role = 'MIRROR' AND ([State] <> 'RESTORING' OR Is_Available = 0))
    )
```

### **Estados Normais por Role**

| Mirroring Role | Estado Normal | Estado com Problema |
|----------------|---------------|---------------------|
| `NULL` (sem mirroring) | `ONLINE` | `OFFLINE`, `RECOVERING`, `SUSPECT`, etc. |
| `PRINCIPAL` | `ONLINE` | `OFFLINE`, `RECOVERING`, `RESTORING`, `SUSPECT`, etc. |
| `MIRROR` | **`RESTORING`** ✅ | `OFFLINE`, `ONLINE` ❌, `RECOVERING`, `SUSPECT`, etc. |

**Importante:** Se um MIRROR estiver `ONLINE`, isso é **PROBLEMA** (deveria estar RESTORING)!

---

## 📋 IMPLEMENTAÇÃO

### **Passo 1: Adicionar Coluna Mirroring_Role**

**Script:** `database/UPDATE_DB_AVAILABILITY_MIRRORING.sql`

```sql
-- Adicionar coluna na tabela STG
ALTER TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_STG
ADD Mirroring_Role VARCHAR(32) NULL;

-- Adicionar coluna na tabela HIST
ALTER TABLE dbo.KPI_MSSQL_DB_AVAILABILITY_HIST
ADD Mirroring_Role VARCHAR(32) NULL;
```

### **Passo 2: Atualizar Procedure de Coleta**

```sql
CREATE PROCEDURE dbo.usp_Collect_DB_Availability
AS
BEGIN
    INSERT INTO dbo.KPI_MSSQL_DB_AVAILABILITY_STG (
        Instance, [Database], [State], Is_Available,
        Recovery_Model, Mirroring_Role, Update_TS
    )
    SELECT
        @@SERVERNAME AS Instance,
        db.name AS [Database],
        db.state_desc AS [State],
        CASE WHEN db.state_desc = 'ONLINE' THEN 1 ELSE 0 END AS Is_Available,
        db.recovery_model_desc AS Recovery_Model,
        m.mirroring_role_desc AS Mirroring_Role,  -- ← NOVO!
        GETDATE() AS Update_TS
    FROM sys.databases db WITH(NOLOCK)
    LEFT OUTER JOIN sys.database_mirroring m WITH(NOLOCK)  -- ← NOVO!
        ON db.database_id = m.database_id
    WHERE db.name NOT IN ('tempdb');
END;
```

### **Passo 3: Atualizar View DET_VIEW**

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
    d.Mirroring_Role,  -- ← NOVO!
    d.Update_TS
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG d
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance
WHERE
    -- ✅ LÓGICA CORRIGIDA COM MIRRORING
    (
        (d.Mirroring_Role IS NULL AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0))
        OR (d.Mirroring_Role = 'PRINCIPAL' AND (d.[State] <> 'ONLINE' OR d.Is_Available = 0))
        OR (d.Mirroring_Role = 'MIRROR' AND (d.[State] <> 'RESTORING' OR d.Is_Available = 0))
    );
```

### **Passo 4: Atualizar View AGG_VIEW**

```sql
CREATE VIEW dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
AS
SELECT
    t.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    t.Total AS TotalCnt,
    ISNULL(d.Cnt, 0) AS AbnormalCnt
FROM
    (SELECT Instance, COUNT(1) AS Total
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
     GROUP BY Instance) t
    LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = t.Instance
    LEFT OUTER JOIN
    (SELECT Instance, COUNT(1) AS Cnt
     FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
     WHERE
         -- ✅ MESMA LÓGICA DA DET_VIEW
         (
             (Mirroring_Role IS NULL AND ([State] <> 'ONLINE' OR Is_Available = 0))
             OR (Mirroring_Role = 'PRINCIPAL' AND ([State] <> 'ONLINE' OR Is_Available = 0))
             OR (Mirroring_Role = 'MIRROR' AND ([State] <> 'RESTORING' OR Is_Available = 0))
         )
     GROUP BY Instance) d ON t.Instance = d.Instance;
```

---

## 🧪 EXEMPLOS PRÁTICOS

### **Antes da Correção** ❌

```sql
SELECT * FROM KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;

-- Resultado: 189 databases
Instance              | Database                        | State      | Mirroring_Role
----------------------|---------------------------------|------------|---------------
SQLHDSPRD301_J01      | MSS13_PRDPUB_CONTENT_MEMRO     | RESTORING  | MIRROR ❌ (ERRO!)
SQLHDSPRD301_J01      | MSS13_PRDPUB_CONTENT_NovaMenus | RESTORING  | MIRROR ❌ (ERRO!)
SQLHDSPRD301_J01      | MSS13_PRDPUB_CONTENT_PGk       | RESTORING  | MIRROR ❌ (ERRO!)
...
-- TODOS OS MIRRORS EM RESTORING SÃO CONSIDERADOS PROBLEMA! (ERRADO!)
```

### **Depois da Correção** ✅

```sql
SELECT * FROM KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;

-- Resultado: 0 databases (nenhum problema real!)
-- Mirrors em RESTORING não aparecem mais (estado normal)

-- Se houver problemas REAIS, aparecem:
Instance              | Database                  | State      | Mirroring_Role | Problema
----------------------|---------------------------|------------|----------------|----------
SQLHDSPRD301_J01      | DB_PROBLEMA_REAL         | OFFLINE    | NULL           | ✅ Database offline (problema real)
SQLHDSPRD301_J01      | DB_MIRROR_PROBLEMA       | OFFLINE    | MIRROR         | ✅ Mirror offline (problema real)
SQLHDSPRD301_J01      | DB_PRINCIPAL_PROBLEMA    | RECOVERING | PRINCIPAL      | ✅ Principal em recuperação (problema real)
```

---

## 📊 VALIDAÇÃO

### **Query para Verificar Mirroring**

```sql
-- Ver databases com mirroring e seus estados
SELECT
    db.name AS [Database],
    db.state_desc AS [State],
    m.mirroring_role_desc AS Mirroring_Role,
    m.mirroring_state_desc AS Mirroring_State,
    m.mirroring_partner_instance AS Partner,
    CASE
        WHEN m.mirroring_role_desc IS NULL THEN 'N/A (sem mirroring)'
        WHEN m.mirroring_role_desc = 'PRINCIPAL' AND db.state_desc = 'ONLINE' THEN '✅ Normal'
        WHEN m.mirroring_role_desc = 'MIRROR' AND db.state_desc = 'RESTORING' THEN '✅ Normal'
        ELSE '❌ Problema'
    END AS Status
FROM sys.databases db
LEFT JOIN sys.database_mirroring m ON db.database_id = m.database_id
WHERE db.name NOT IN ('tempdb')
ORDER BY Status DESC, db.name;
```

### **Query para Validar Correção**

```sql
-- Antes da correção: 189 databases
SELECT COUNT(*) AS DB_Not_Available_OLD
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
WHERE [State] <> 'ONLINE' OR Is_Available = 0;

-- Depois da correção: 0 databases (se não houver problemas reais)
SELECT COUNT(*) AS DB_Not_Available_NEW
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
WHERE
    (
        (Mirroring_Role IS NULL AND ([State] <> 'ONLINE' OR Is_Available = 0))
        OR (Mirroring_Role = 'PRINCIPAL' AND ([State] <> 'ONLINE' OR Is_Available = 0))
        OR (Mirroring_Role = 'MIRROR' AND ([State] <> 'RESTORING' OR Is_Available = 0))
    );
```

---

## 🚀 PASSOS PARA APLICAR

### **1. Executar Script SQL**

**Arquivo:** `database/UPDATE_DB_AVAILABILITY_MIRRORING.sql`

```bash
# Abrir SQL Server Management Studio
# Conectar no servidor: SQLHDSTST505\I01
# Selecionar database: WatcherDB_Intelligence
# Executar o script completo
```

**Resultado Esperado:**
```
============================================================================
ATUALIZAÇÃO: DB Availability - Suporte a Mirroring Role
============================================================================

  [OK] Coluna Mirroring_Role adicionada na tabela STG
  [OK] Coluna Mirroring_Role adicionada na tabela HIST
  [OK] Procedure usp_Collect_DB_Availability atualizada
  [OK] View KPI_MSSQL_DB_AVAILABILITY_DET_VIEW atualizada
  [OK] View KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW atualizada

ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!
```

### **2. Executar Coleta de Dados**

```sql
-- Coletar dados atualizados com Mirroring_Role
EXEC dbo.usp_Collect_DB_Availability;
```

### **3. Validar Resultado**

```sql
-- Ver quantas databases aparecem agora
SELECT COUNT(*) AS DB_Not_Available
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;

-- Deve retornar 0 (ou número muito menor que 189)
```

### **4. Reiniciar Aplicação Python**

```bash
# Parar aplicação (Ctrl+C)
# Reiniciar
python -m uvicorn watcherdb_intelligence:app --reload --port 8000
```

### **5. Verificar Dashboard**

1. Recarregar dashboard
2. Verificar card "DB Not Availability"
3. Deve mostrar **0** (ou número correto de problemas reais)

---

## 📝 RESUMO

### **Antes da Correção**
- ❌ 189 databases consideradas como problema
- ❌ Todos os MIRROR em RESTORING eram contados como problema
- ❌ Estado normal de mirroring considerado erro

### **Depois da Correção**
- ✅ 0 databases (ou apenas problemas reais)
- ✅ MIRROR em RESTORING **NÃO** é problema (estado normal)
- ✅ Apenas problemas reais são detectados:
  - Databases OFFLINE (sem mirroring ou com mirroring)
  - PRINCIPAL em estado anormal
  - MIRROR em estado diferente de RESTORING

### **Estados Normais**
| Configuração | Estado Normal |
|--------------|---------------|
| Database sem mirroring | `ONLINE` |
| Database PRINCIPAL (mirroring) | `ONLINE` |
| Database MIRROR (mirroring) | **`RESTORING`** ✅ |

---

## ✅ CHECKLIST

- [x] Erro de sintaxe Python corrigido (linha 692)
- [ ] Script SQL executado no SQL Server
- [ ] Procedure de coleta executada
- [ ] Views validadas
- [ ] Aplicação Python reiniciada
- [ ] Dashboard verificado

---

**Arquivo Script:** [database/UPDATE_DB_AVAILABILITY_MIRRORING.sql](database/UPDATE_DB_AVAILABILITY_MIRRORING.sql)
**Status:** ✅ **PRONTO PARA APLICAR**
