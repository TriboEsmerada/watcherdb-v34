# ✅ TESTE APÓS CORREÇÕES - CHECKLIST COMPLETO

**Data:** 2025-12-09
**Status:** ⏳ **AGUARDANDO TESTES**

---

## 📋 CORREÇÕES APLICADAS

### ✅ **1. Script SQL Mirroring - EXECUTADO**
- ✅ Coluna `Mirroring_Role` adicionada em STG e HIST
- ✅ Procedure `usp_Collect_DB_Availability` atualizada
- ✅ View `KPI_MSSQL_DB_AVAILABILITY_DET_VIEW` atualizada
- ✅ View `KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW` atualizada

### ✅ **2. Código Python - CORRIGIDO**
- ✅ Erro de sintaxe (linha 692) - indentação corrigida
- ✅ Bug `is_data_fresh()` - estados de database excluídos
- ✅ Processes Alarm - query corrigida
- ✅ Função `_count_by_env()` - inclui ambiente `Undefined`

---

## 🚀 PRÓXIMOS PASSOS

### **Passo 1: Coletar Dados Atualizados**

Execute no SQL Server Management Studio:

```sql
-- Conectar em: SQLHDSTST505\I01
-- Database: WatcherDB_Intelligence

-- Coletar dados com nova lógica de Mirroring
EXEC dbo.usp_Collect_DB_Availability;

-- Verificar resultado
SELECT COUNT(*) AS DB_Not_Available
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;

-- Deve retornar 0 (ou número muito menor que 189)
```

**Resultado Esperado:**
```
DB_Not_Available: 0 (ou poucos registros reais)
```

### **Passo 2: Verificar Dados Coletados**

```sql
-- Ver databases com Mirroring_Role
SELECT
    Instance,
    [Database],
    [State],
    Mirroring_Role,
    COUNT(*) OVER() AS Total
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
WHERE Mirroring_Role IS NOT NULL
ORDER BY Instance, [Database];

-- Resultado Esperado:
-- MIRROR com State = RESTORING (normal, não aparece na view)
-- PRINCIPAL com State = ONLINE (normal, não aparece na view)
```

### **Passo 3: Validar Views**

```sql
-- Ver se views estão funcionando
-- DET_VIEW - Deve mostrar apenas problemas REAIS
SELECT * FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;

-- AGG_VIEW - Deve mostrar contagem correta
SELECT * FROM dbo.KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
WHERE AbnormalCnt > 0;

-- Ambas devem retornar poucos ou zero registros
```

### **Passo 4: Reiniciar Aplicação Python**

```bash
# No terminal PowerShell
# Parar aplicação (Ctrl+C)

# Reiniciar
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python -m uvicorn watcherdb_intelligence:app --reload --port 8000
```

**Verificar no log:**
```
INFO:     Started server process
✅ Router Intelligence KPIs carregado  ← Deve aparecer SEM ERRO!
```

### **Passo 5: Testar Dashboard**

Abrir navegador: `http://127.0.0.1:8000`

---

## 🧪 CHECKLIST DE VALIDAÇÃO

### **A. Disponibilidade**

#### ✅ **DB Not Availability**
- [ ] Card mostra **0** (ou número pequeno de problemas reais)
- [ ] Ao clicar no card, modal mostra **mesmo número**
- [ ] Databases MIRROR em RESTORING **NÃO** aparecem

#### ✅ **DB Availability**
- [ ] Card mostra número correto de databases disponíveis
- [ ] Valor mantém-se estático (cache funcionando)
- [ ] Só muda quando `DB Not Availability` muda

#### ✅ **Instances OK**
- [ ] Card mostra número de instâncias online
- [ ] Valor mantém-se estático (cache funcionando)
- [ ] Só muda quando `Instances Off` muda

#### ✅ **Instances Off**
- [ ] Card mostra **0** ou número correto
- [ ] Ao clicar, modal mostra mesmo número

---

### **B. Performance**

#### ✅ **Processes Alarm**
- [ ] Card mostra **6** (ou número correto)
- [ ] Ao clicar, modal mostra **6 instâncias** (não mais 0!)
- [ ] Modal lista as instâncias com ≥ 500 processos

#### ✅ **Blocked Sessions**
- [ ] Card e modal mostram mesmo número

#### ✅ **Blocked Users**
- [ ] Card e modal mostram mesmo número

---

### **C. Espaço (Space)**

#### ✅ **FileGroups Usage**
- [ ] Card mostra: Critical = 47, Warning = 9 (ou valores corretos)
- [ ] **Tooltip hover** mostra breakdown por ambiente
- [ ] **Soma dos ambientes = valor do card** ✅
  - Exemplo: PRD=27 + QLT=10 + TST=3 + Undefined=7 = **47** ✅
- [ ] Se aparecer `Undefined` no tooltip, está correto!

#### ✅ **Disk File System (Warning)**
- [ ] Card mostra: 19 (ou valor correto)
- [ ] **Tooltip hover** mostra breakdown por ambiente
- [ ] **Soma dos ambientes = 19** ✅
  - Exemplo: QLT=7 + TST=5 + Undefined=7 = **19** ✅

#### ✅ **Disk File System (Critical)**
- [ ] Card mostra: 9 (ou valor correto)
- [ ] **Tooltip hover** mostra breakdown por ambiente
- [ ] **Soma dos ambientes = 9** ✅
  - Exemplo: PRD=4 + QLT=1 + Undefined=4 = **9** ✅

#### ✅ **Transaction Logs**
- [ ] Card e tooltip batem
- [ ] Soma dos ambientes = valor do card

---

### **D. Backup e Alta Disponibilidade**

#### ✅ **Backup Failed / Delayed**
- [ ] Card e modal mostram mesmo número

#### ✅ **Always On**
- [ ] Card e modal mostram mesmo número

---

### **E. Tooltips**

#### ⚠️ **Texto Duplicado no Hover**
- [ ] Verificar se ainda aparece texto duplicado
- [ ] Se aparecer, anotar qual card está duplicando
- [ ] Caso contrário: ✅ Problema pode ter sido resolvido automaticamente

---

## 📊 QUERIES DE VALIDAÇÃO

### **Validar DB Not Availability**

```sql
-- Ver quantas databases com problema (após correção)
SELECT COUNT(*) AS Total_Problemas
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW;

-- Ver detalhes dos problemas (se houver)
SELECT
    Instance,
    [Database],
    [State],
    Mirroring_Role,
    'Problema: ' +
    CASE
        WHEN Mirroring_Role IS NULL AND [State] <> 'ONLINE' AND [State] <> 'RESTORING'
            THEN 'Database sem mirroring em estado anormal'
        WHEN Mirroring_Role = 'PRINCIPAL' AND [State] <> 'ONLINE'
            THEN 'Principal não está ONLINE'
        WHEN Mirroring_Role = 'MIRROR' AND [State] <> 'RESTORING'
            THEN 'Mirror não está RESTORING (deveria estar!)'
        ELSE 'Outro problema'
    END AS Diagnostico
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
ORDER BY Instance, [Database];
```

### **Validar Contadores por Ambiente**

```sql
-- FileGroups Usage por ambiente
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_FG_USAGE_STG fg
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = fg.Instance
WHERE fg.[Used%] >= 80  -- Warning threshold
GROUP BY ISNULL(e.Env, 'Undefined')
ORDER BY Env;

-- Disk File System (Warning) por ambiente
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_DISK_USAGE_STG d
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance
WHERE d.[Available%] < 20 AND d.[Available%] >= 10
GROUP BY ISNULL(e.Env, 'Undefined')
ORDER BY Env;

-- Disk File System (Critical) por ambiente
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_DISK_USAGE_STG d
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance
WHERE d.[Available%] < 10
GROUP BY ISNULL(e.Env, 'Undefined')
ORDER BY Env;
```

---

## ✅ RESULTADO ESPERADO

Após todas as correções, o dashboard deve mostrar:

### **Disponibilidade**
- ✅ DB Not Availability: **0** (ou poucos problemas reais)
- ✅ DB Availability: **39** (mantém estático até DB Not mudar)
- ✅ Instances OK: **18** (mantém estático até Instances Off mudar)
- ✅ Instances Off: **0**

### **Performance**
- ✅ Processes Alarm: **6** (card = modal)
- ✅ Blocked Sessions: **0** (card = modal)
- ✅ Blocked Users: **0** (card = modal)

### **Espaço**
- ✅ FileGroups Usage: Critical=47, Warning=9 (card = soma do tooltip)
- ✅ Disk File System: Warning=19, Critical=9 (card = soma do tooltip)
- ✅ Transaction Logs: (valores corretos)

### **Tooltips**
- ✅ Mostram breakdown por ambiente (PRD, QLT, TST, **Undefined**)
- ✅ Soma dos ambientes = valor do card
- ⚠️ Texto duplicado pode ou não estar resolvido

---

## 📝 ANOTAÇÕES DURANTE TESTE

### Problemas Encontrados
```
1. [  ] Descrever problema aqui
2. [  ] Descrever problema aqui
```

### Sucessos
```
1. [  ] Descrever sucesso aqui
2. [  ] Descrever sucesso aqui
```

---

## 🎯 PRÓXIMO PASSO

**Execute a coleta de dados e reinicie a aplicação:**

```bash
# 1. No SSMS
EXEC dbo.usp_Collect_DB_Availability;

# 2. No PowerShell
# Ctrl+C (parar)
python -m uvicorn watcherdb_intelligence:app --reload --port 8000

# 3. No navegador
# Recarregar http://127.0.0.1:8000
```

**Depois use este checklist para validar cada item!** ✅
