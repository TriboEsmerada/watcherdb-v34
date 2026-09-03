# 🐛 PROBLEMAS DO DASHBOARD - RESUMO E SOLUÇÕES

**Data:** 2025-12-09
**Status:** 🔍 **EM ANÁLISE**

---

## 📋 PROBLEMAS IDENTIFICADOS

### ✅ 1. **DB Not Availability** - RESOLVIDO
**Problema:** Card mostra 189, modal mostra 0
**Causa:** Bug na função `is_data_fresh()` + databases em Mirroring RESTORING consideradas como problema
**Solução:**
- ✅ Função `is_data_fresh()` corrigida
- ✅ Script SQL para suporte a Mirroring criado
- ⏳ Aguardando execução do script SQL

---

### ✅ 2. **Processes Alarm** - RESOLVIDO
**Problema:** Card mostra 6, modal mostra "Nenhuma instância com problema"
**Causa:** Modal procurava colunas erradas (`Process_Count`, `Cnt`) ao invés de usar `State`
**Solução:** ✅ Código corrigido (linhas 1866-1877)
**Status:** Aguardando reinício da aplicação

---

### ⏳ 3. **Tooltip Hover Duplicado**
**Problema:** Ao passar mouse sobre cards, aparece texto duplicado:
- "Disponibilidade de Banco de Dados"
- "Disponibilidade de Banco de Dados"

**Causa:** Provável duplicação no código JavaScript que gera o tooltip
**Localização:** `templates/watcherdb_portal.html`
**Status:** 🔍 Investigando

---

### ⏳ 4. **FileGroups Usage - Números Não Batem**
**Problema:**
- Card mostra: Critical = 47, Warning = 9
- Tooltip hover mostra: PRD = 27, QLT = 10, TST = 3
- **27 + 10 + 3 = 40 ≠ 47** ❌

**Possíveis Causas:**
1. Contagem por ambiente não inclui todos os registros
2. Registros sem ambiente definido (`Env = 'Undefined'`)
3. Filtro de freshness aplicado de forma inconsistente

**Status:** 🔍 Investigando

---

### ⏳ 5. **Disk File System - Números Não Batem**

#### **5.1. Warning**
- Card mostra: 19
- Tooltip mostra: QLT = 7, TST = 5
- **7 + 5 = 12 ≠ 19** ❌

#### **5.2. Critical**
- Card mostra: 9
- Tooltip mostra: PRD = 4, QLT = 1
- **4 + 1 = 5 ≠ 9** ❌

**Possíveis Causas:**
1. Mesma causa do FileGroups (registros sem ambiente)
2. Contagem agregada vs contagem detalhada
3. Freshness aplicado de forma diferente

**Status:** 🔍 Investigando

---

## 🔍 ANÁLISE TÉCNICA

### **Hipótese Principal: Registros Sem Ambiente**

Muitos registros podem ter `Env = 'Undefined'` e não estão sendo contados no breakdown por ambiente:

```javascript
// Tooltip mostra apenas PRD, QLT, TST
envBreakdown: {
    PRD: 27,
    QLT: 10,
    TST: 3,
    // Undefined: 7 ← NÃO APARECE NO TOOLTIP!
}

// Total real: 27 + 10 + 3 + 7 = 47 ✅
```

### **Onde Investigar**

1. **API Response** - Verificar se retorna `count_by_env` com todos os ambientes
2. **Frontend** - Verificar função que cria `envBreakdown`
3. **Backend** - Função `_count_by_env()` pode estar excluindo `Undefined`

---

## 🧪 QUERIES PARA VALIDAÇÃO

### **FileGroups Usage - Validar Contagem**

```sql
-- Ver todos os filegroups com problema
SELECT
    Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_FG_USAGE_STG fg
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = fg.Instance
WHERE fg.[Used%] >= 80  -- Warning threshold
GROUP BY fg.Instance, ISNULL(e.Env, 'Undefined')
ORDER BY Env, Instance;

-- Resultado Esperado:
-- PRD: 27
-- QLT: 10
-- TST: 3
-- Undefined: 7  ← Este pode estar faltando no tooltip!
-- TOTAL: 47
```

### **Disk File System - Validar Contagem**

```sql
-- Ver todos os discos com problema (Warning)
SELECT
    Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    COUNT(*) AS Total
FROM dbo.KPI_MSSQL_DISK_USAGE_STG d
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance
WHERE d.[Available%] < 20 AND d.[Available%] >= 10  -- Warning: 10-20%
GROUP BY d.Instance, ISNULL(e.Env, 'Undefined')
ORDER BY Env, Instance;

-- Resultado Esperado:
-- PRD: ?
-- QLT: 7
-- TST: 5
-- Undefined: 7  ← Este pode estar faltando!
-- TOTAL: 19
```

---

## 🔧 CORREÇÕES NECESSÁRIAS

### **1. Tooltip Duplicado**
**Ação:** Encontrar e remover duplicação no código JavaScript
**Arquivo:** `templates/watcherdb_portal.html`
**Prioridade:** 🟡 Média (estético, não afeta funcionalidade)

### **2. Contadores de Ambiente**
**Ação:** Incluir `Undefined` no breakdown de ambientes do tooltip
**Arquivo:** `templates/watcherdb_portal.html` (JavaScript)
**Código Esperado:**
```javascript
envBreakdown: {
    PRD: data.prd_count || 0,
    QLT: data.qlt_count || 0,
    TST: data.tst_count || 0,
    Undefined: data.undefined_count || 0  // ← ADICIONAR
}
```

**Prioridade:** 🔴 Alta (afeta confiabilidade dos dados)

### **3. Backend - Função `_count_by_env()`**
**Ação:** Verificar se função está excluindo ou incluindo `Undefined`
**Arquivo:** `api/routers/intelligence_kpis.py`
**Localização:** Linha 341-361

**Código Atual:**
```python
def _count_by_env(instances: List[Dict[str, Any]], env_key: str = 'Env') -> Dict[str, int]:
    counts = {'PRD': 0, 'QLT': 0, 'TST': 0}
    for row in instances:
        env_upper = env.upper() if env else 'Undefined'
        if env_upper in ['PRD', 'QLT', 'TST']:
            counts[env_upper] = counts.get(env_upper, 0) + 1
        # Não contar Undefined - apenas PRD, QLT, TST  ← PROBLEMA!
    return counts
```

**Correção Necessária:**
```python
def _count_by_env(instances: List[Dict[str, Any]], env_key: str = 'Env') -> Dict[str, int]:
    counts = {'PRD': 0, 'QLT': 0, 'TST': 0, 'Undefined': 0}  # ← ADICIONAR Undefined
    for row in instances:
        env_upper = env.upper() if env else 'Undefined'
        if env_upper in ['PRD', 'QLT', 'TST']:
            counts[env_upper] = counts.get(env_upper, 0) + 1
        else:
            counts['Undefined'] = counts.get('Undefined', 0) + 1  # ← CONTAR Undefined
    return counts
```

**Prioridade:** 🔴 Alta (causa raiz dos problemas de contagem)

---

## ✅ PLANO DE AÇÃO

### **Passo 1: Corrigir Backend** 🔴
1. Modificar função `_count_by_env()` para incluir `Undefined`
2. Testar retorno da API `/api/intelligence-kpis/dashboard`
3. Verificar se `count_by_env` inclui todos os ambientes

### **Passo 2: Atualizar Frontend** 🔴
1. Modificar tooltip para mostrar `Undefined` se existir
2. Garantir que soma dos ambientes = total do card

### **Passo 3: Remover Tooltip Duplicado** 🟡
1. Identificar código que cria tooltip
2. Remover duplicação

### **Passo 4: Executar Script SQL Mirroring** 🔴
1. Executar `UPDATE_DB_AVAILABILITY_MIRRORING.sql`
2. Coletar dados: `EXEC usp_Collect_DB_Availability`
3. Validar resultado

### **Passo 5: Reiniciar e Testar** ✅
1. Reiniciar aplicação Python
2. Recarregar dashboard
3. Validar todos os cards e tooltips
4. Verificar modais

---

## 📊 CHECKLIST DE VALIDAÇÃO

Após aplicar correções, validar:

- [ ] DB Not Availability: Card = Modal
- [ ] Processes Alarm: Card = Modal
- [ ] FileGroups: Card = Soma dos ambientes no tooltip
- [ ] Disk File System: Card = Soma dos ambientes no tooltip
- [ ] Tooltip: Não aparece texto duplicado
- [ ] Todos os ambientes aparecem no tooltip (incluindo Undefined)

---

## 📝 NOTAS

1. **Ambiente `Undefined`** deve ser tratado como qualquer outro ambiente
2. **Freshness** deve ser aplicado de forma consistente em card e tooltip
3. **Modais** devem usar mesma query do card (evitar inconsistências)

---

**Status Geral:** ⏳ **CORREÇÕES EM ANDAMENTO**
**Prioridade:** 🔴 **ALTA** (afeta confiabilidade do dashboard)
