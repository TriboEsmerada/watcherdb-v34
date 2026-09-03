# ✅ CHECKLIST DE TESTES - TODAS AS CORREÇÕES

**Data:** 2025-12-10
**Objetivo:** Validar todas as correções aplicadas no dashboard
**Status:** 🟡 **AGUARDANDO EXECUÇÃO**

---

## 📋 RESUMO DAS CORREÇÕES APLICADAS

### ✅ 1. **DB Not Availability - Bug Freshness** (Python)
- **Arquivo:** `api/routers/intelligence_kpis.py` (linha 157-165)
- **Fix:** Função `is_data_fresh()` agora exclui estados de database da detecção de views agregadas
- **Impacto:** Card e modal devem mostrar mesma contagem

### ✅ 2. **Processes Alarm - Modal** (Python)
- **Arquivo:** `api/routers/intelligence_kpis.py` (linha 1866-1877)
- **Fix:** Query do modal agora usa `WHERE [State] IN ('WARNING', 'CRITICAL')`
- **Impacto:** Modal deve mostrar instâncias com problemas (igual ao card)

### ✅ 3. **Environment Counting - Undefined** (Python)
- **Arquivo:** `api/routers/intelligence_kpis.py` (linha 348-370)
- **Fix:** Função `_count_by_env()` agora inclui ambiente `Undefined`
- **Impacto:** Soma dos ambientes no tooltip deve bater com o card

### ✅ 4. **Mirroring Support** (SQL + Python)
- **Arquivo:** `database/UPDATE_DB_AVAILABILITY_MIRRORING.sql`
- **Status:** ✅ Executado (usuário confirmou "feito")
- **Impacto:** Databases MIRROR em RESTORING não são mais problemas

### ✅ 5. **Tooltip Duplicado** (HTML)
- **Arquivo:** `templates/watcherdb_portal.html` (linhas 14415, 14468, 14485, 14500, 14515, 14650, 14686)
- **Fix:** Alterados 7 subtítulos para não duplicar o título
- **Impacto:** Cards mostram títulos e subtítulos diferentes

---

## 🚀 PRÉ-REQUISITOS

### **1. Executar Coleta de Dados (SQL)**
```sql
-- No SQL Server Management Studio
-- Conectar: SQLHDSTST505\I01
-- Database: WatcherDB_Intelligence

-- Coletar dados atualizados com Mirroring_Role
EXEC dbo.usp_Collect_DB_Availability;

-- Validar se dados foram coletados
SELECT
    COUNT(*) AS Total_Databases,
    SUM(CASE WHEN Mirroring_Role IS NOT NULL THEN 1 ELSE 0 END) AS With_Mirroring,
    SUM(CASE WHEN Mirroring_Role = 'MIRROR' AND [State] = 'RESTORING' THEN 1 ELSE 0 END) AS Mirror_Restoring
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG;

-- Resultado esperado:
-- With_Mirroring > 0 (deve ter bancos com mirroring)
-- Mirror_Restoring > 0 (deve ter mirrors em RESTORING)
```

### **2. Reiniciar Aplicação Python**
```bash
# Parar aplicação (Ctrl+C no terminal)

# Reiniciar
python -m uvicorn watcherdb_intelligence:app --reload --port 8000

# Aguardar mensagem:
# ✅ Application startup complete.
# ✅ Uvicorn running on http://127.0.0.1:8000
```

### **3. Acessar Dashboard Correto**
```
URL: http://127.0.0.1:8000/watcherdb
```
**IMPORTANTE:** Não acessar apenas `http://127.0.0.1:8000/` (retorna JSON, não HTML)

---

## 🧪 TESTES POR CORREÇÃO

### **TESTE 1: DB Not Availability - Freshness e Mirroring**

#### **Objetivo:**
Validar que card e modal mostram a mesma contagem e que databases MIRROR em RESTORING não são problemas.

#### **Passos:**
1. ✅ Abrir dashboard: `http://127.0.0.1:8000/watcherdb`
2. ✅ Localizar card "DB Not Availability"
3. ✅ Anotar valor do card (ex: **0** - esperado após correção mirroring)
4. ✅ Clicar no card para abrir modal
5. ✅ Verificar contagem no modal

#### **Validações:**
- [ ] **Card mostra valor ≈ 0** (ou muito menor que 189)
- [ ] **Modal mostra mesma contagem do card**
- [ ] **Se valor > 0:** Modal lista databases realmente com problema (OFFLINE, SUSPECT, etc.)
- [ ] **Se valor > 0:** Modal **NÃO** lista MIRROR em RESTORING como problema
- [ ] **Não há mensagem "Nenhum problema encontrado"** se card mostra valor > 0

#### **Query SQL de Validação:**
```sql
-- Ver databases que DEVEM aparecer como problema
SELECT
    Instance,
    [Database],
    [State],
    Mirroring_Role,
    CASE
        WHEN Mirroring_Role = 'MIRROR' AND [State] = 'RESTORING' THEN '✅ Normal (Mirror)'
        WHEN Mirroring_Role = 'PRINCIPAL' AND [State] = 'ONLINE' THEN '✅ Normal (Principal)'
        WHEN Mirroring_Role IS NULL AND [State] = 'ONLINE' THEN '✅ Normal'
        ELSE '❌ Problema'
    END AS Status
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_STG
ORDER BY Status DESC, Instance;

-- Contar problemas reais
SELECT COUNT(*) AS Problemas_Reais
FROM dbo.KPI_MSSQL_DB_AVAILABILITY_DET_VIEW
WHERE Update_TS >= DATEADD(MINUTE, -60, GETDATE());  -- Freshness 60 min
```

---

### **TESTE 2: Processes Alarm - Modal**

#### **Objetivo:**
Validar que modal mostra instâncias com processos em WARNING ou CRITICAL.

#### **Passos:**
1. ✅ Localizar card "Processes Alarm"
2. ✅ Anotar valor do card (ex: **6**)
3. ✅ Clicar no card para abrir modal
4. ✅ Verificar lista de instâncias

#### **Validações:**
- [ ] **Modal mostra 6 instâncias** (igual ao card)
- [ ] **Cada instância tem:**
  - Nome da instância
  - State = "WARNING" ou "CRITICAL"
  - Process_Count ≥ 500 (WARNING) ou ≥ 1000 (CRITICAL)
- [ ] **Não aparece "Nenhuma instância com problema"** se card mostra valor > 0

#### **Query SQL de Validação:**
```sql
-- Ver instâncias com processes alarm
SELECT
    Instance,
    [State],
    Process_Count,
    CASE
        WHEN Process_Count >= 1000 THEN 'CRITICAL'
        WHEN Process_Count >= 500 THEN 'WARNING'
        ELSE 'OK'
    END AS Expected_State
FROM dbo.KPI_MSSQL_PROCESSES_AGG_VIEW
WHERE [State] IN ('WARNING', 'CRITICAL')
  AND Update_TS >= DATEADD(MINUTE, -60, GETDATE());  -- Freshness 60 min
```

---

### **TESTE 3: FileGroups Usage - Contadores de Ambiente**

#### **Objetivo:**
Validar que soma dos ambientes no tooltip bate com o valor do card.

#### **Passos:**
1. ✅ Localizar card "FileGroups Usage - Critical"
2. ✅ Anotar valor do card (ex: **47**)
3. ✅ Passar mouse sobre o card (hover)
4. ✅ Verificar breakdown no tooltip:
   - PRD: ?
   - QLT: ?
   - TST: ?
   - Undefined: ? (se houver)
5. ✅ **Somar valores:** PRD + QLT + TST + Undefined = ?

#### **Validações:**
- [ ] **Soma dos ambientes = Valor do card** ✅
- [ ] **Se houver Undefined > 0:** Aparece no tooltip
- [ ] **Repetir teste para:**
  - [ ] FileGroups Usage - Warning
  - [ ] Disk File System - Critical
  - [ ] Disk File System - Warning

#### **Query SQL de Validação:**
```sql
-- Ver FileGroups Critical por ambiente
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_FG_USAGE_STG fg
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = fg.Instance
WHERE fg.[Used%] >= 95  -- Critical threshold
  AND fg.Update_TS >= DATEADD(MINUTE, -60, GETDATE())
GROUP BY ISNULL(e.Env, 'Undefined')

UNION ALL

SELECT 'TOTAL' AS Env, COUNT(*) AS Total
FROM dbo.KPI_MSSQL_FG_USAGE_STG fg
WHERE fg.[Used%] >= 95
  AND fg.Update_TS >= DATEADD(MINUTE, -60, GETDATE())
ORDER BY Env;

-- Resultado esperado:
-- PRD + QLT + TST + Undefined = TOTAL
```

---

### **TESTE 4: Disk File System - Contadores de Ambiente**

#### **Objetivo:**
Validar que soma dos ambientes no tooltip bate com o valor do card.

#### **Passos:**
1. ✅ Localizar card "Disk File System - Warning"
2. ✅ Anotar valor do card (ex: **19**)
3. ✅ Passar mouse sobre o card (hover)
4. ✅ Verificar breakdown no tooltip e somar

#### **Validações:**
- [ ] **Soma dos ambientes = Valor do card** ✅
- [ ] **Repetir para Disk File System - Critical**

#### **Query SQL de Validação:**
```sql
-- Ver Disk Warning por ambiente
SELECT
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_DISK_USAGE_STG d
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance
WHERE d.[Available%] < 20 AND d.[Available%] >= 10  -- Warning: 10-20%
  AND d.Update_TS >= DATEADD(MINUTE, -60, GETDATE())
GROUP BY ISNULL(e.Env, 'Undefined')

UNION ALL

SELECT 'TOTAL' AS Env, COUNT(*) AS Total
FROM dbo.KPI_MSSQL_DISK_USAGE_STG d
WHERE d.[Available%] < 20 AND d.[Available%] >= 10
  AND d.Update_TS >= DATEADD(MINUTE, -60, GETDATE())
ORDER BY Env;
```

---

### **TESTE 5: Tooltip Duplicado**

#### **Objetivo:**
Validar que nenhum card tem título e subtítulo iguais.

#### **Passos:**
1. ✅ Percorrer visualmente todos os cards do dashboard
2. ✅ Verificar que cada card tem:
   - Título (linha superior)
   - Subtítulo (logo abaixo, menor e mais claro)
   - Valor (número grande)

#### **Validações:**
- [ ] **DB Not Availability:** "Unavailable Count" (não duplicado) ✅
- [ ] **Instances OK:** "Available Count" (não duplicado) ✅
- [ ] **Instances Off:** "Offline Count" (não duplicado) ✅
- [ ] **Blocked Sessions:** "Session Count" (não duplicado) ✅
- [ ] **Blocked Users:** "User Count" (não duplicado) ✅
- [ ] **Backup Failed:** "Failed Count" (não duplicado) ✅
- [ ] **Backup Delayed:** "Delayed Count" (não duplicado) ✅

#### **Cards que já estavam corretos (verificar se não quebraram):**
- [ ] **Transaction Logs - Critical:** "Critical" ✅
- [ ] **Transaction Logs - Warning:** "Warning" ✅
- [ ] **Disk File System - Critical:** "Critical" ✅
- [ ] **Disk File System - Warning:** "Warning" ✅
- [ ] **FileGroups Usage - Critical:** "Critical" ✅
- [ ] **FileGroups Usage - Warning:** "Warning" ✅
- [ ] **Always On:** "UnHealthy" ✅

---

## 📊 RESUMO DE VALIDAÇÃO

### **Checklist Geral:**

#### **Pré-Requisitos:**
- [ ] Script SQL mirroring executado (já feito)
- [ ] Procedure `usp_Collect_DB_Availability` executada
- [ ] Aplicação Python reiniciada
- [ ] Dashboard acessado via `/watcherdb` (não `/`)

#### **Testes Críticos:**
- [ ] DB Not Availability: Card = Modal (≈ 0)
- [ ] Processes Alarm: Card = Modal (6 instâncias)
- [ ] FileGroups Critical: Soma ambientes = Card (47)
- [ ] FileGroups Warning: Soma ambientes = Card (9)
- [ ] Disk Critical: Soma ambientes = Card (9)
- [ ] Disk Warning: Soma ambientes = Card (19)

#### **Testes Visuais:**
- [ ] Nenhum card com subtítulo duplicado (7 cards corrigidos)
- [ ] Todos os tooltips mostram breakdown correto
- [ ] Modais abrem e mostram dados corretos

---

## 🎯 CRITÉRIOS DE SUCESSO

### **✅ Testes Passaram Se:**
1. Card "DB Not Availability" mostra ≈ 0 (ou muito menor que 189)
2. Todos os cards e modais mostram mesma contagem
3. Soma dos ambientes = Total do card (em todos os KPIs com breakdown)
4. Nenhum subtítulo duplicado
5. MIRROR em RESTORING não aparece como problema

### **❌ Testes Falharam Se:**
1. DB Not Availability ainda mostra 189
2. Card mostra X mas modal mostra 0
3. Soma dos ambientes ≠ Total do card
4. Subtítulos ainda duplicados
5. MIRROR em RESTORING aparece na lista de problemas

---

## 📝 RELATÓRIO DE TESTES

### **Template para Preencher:**

```
Data do Teste: _______________
Testado por: __________________

[ ] DB Not Availability: Card = ___, Modal = ___ (OK/FALHA)
[ ] Processes Alarm: Card = ___, Modal = ___ (OK/FALHA)
[ ] FileGroups Critical: Card = ___, Soma = ___ (OK/FALHA)
[ ] FileGroups Warning: Card = ___, Soma = ___ (OK/FALHA)
[ ] Disk Critical: Card = ___, Soma = ___ (OK/FALHA)
[ ] Disk Warning: Card = ___, Soma = ___ (OK/FALHA)
[ ] Tooltips duplicados: (OK/FALHA)

Observações:
_________________________________
_________________________________
_________________________________
```

---

## 🚀 PRÓXIMOS PASSOS APÓS TESTES

### **Se Todos os Testes Passarem:**
1. ✅ Documentar como concluído
2. ✅ Atualizar documentação de manutenção
3. ✅ Considerar concluído

### **Se Algum Teste Falhar:**
1. 🔍 Verificar logs da aplicação Python
2. 🔍 Validar query SQL diretamente no banco
3. 🔍 Revisar código da correção específica
4. 🔧 Aplicar correção adicional se necessário
5. ♻️ Repetir testes

---

**Status:** 🟡 **PRONTO PARA EXECUÇÃO**
**Documentos Relacionados:**
- [PROBLEMAS_DASHBOARD_RESUMO.md](PROBLEMAS_DASHBOARD_RESUMO.md)
- [CORRECAO_MIRRORING_DB_AVAILABILITY.md](CORRECAO_MIRRORING_DB_AVAILABILITY.md)
- [CORRECAO_TOOLTIP_DUPLICADO.md](CORRECAO_TOOLTIP_DUPLICADO.md)
- [BUG_FIX_DB_NOT_AVAILABILITY.md](BUG_FIX_DB_NOT_AVAILABILITY.md)
