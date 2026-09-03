# Filtro de Severidade para Backup Issues

## 📊 Implementação Completa

**Data:** 2026-02-20
**Status:** ✅ Implementado e Replicado (DEV, V4, V5)

---

## 🎯 Objetivo

Permitir ao DBA **filtrar a tabela "Databases com Issues"** por severidade para priorizar o trabalho:
- **Todos** → mostra todas as databases com issues
- **Medium+ (>6h)** → mostra medium + high + critical (gaps > 6h)
- **High+ (>30h)** → mostra high + critical (gaps > 30h)
- **Critical (>48h)** → mostra apenas critical (gaps > 48h)

---

## 🔧 Componentes Implementados

### 1. Backend - Endpoint API Melhorado

**Arquivo:** `watcherdb_main.py`

**Endpoint:** `GET /api/monitoring/backup/server/{server_id}/gaps`

**Mudanças:**
```python
# ANTES: Filtro exato (severity == 'critical')
if severity:
    all_gaps = [g for g in all_gaps if g.get('severity', '').lower() == severity.lower()]

# AGORA: Filtro cascata (severity >= 'critical')
if severity:
    severity_hierarchy = ['low', 'medium', 'high', 'critical']
    min_index = severity_hierarchy.index(severity_lower)
    allowed_severities = severity_hierarchy[min_index:]
    all_gaps = [g for g in all_gaps if g.get('severity', '').lower() in allowed_severities]
```

**Retorno melhorado:**
```json
{
  "success": true,
  "server_id": "SQLSERVER01",
  "total_gaps": 45,
  "critical_count": 12,
  "high_count": 18,
  "medium_count": 10,
  "low_count": 5,
  "gaps": [...]
}
```

---

### 2. Frontend - UI do Filtro

**Arquivo:** `templates/watcherdb_portal.html`

**Localização:** Seção "Databases com Issues"

#### 2.1 Novo Select de Severidade

```html
<label style="color:#9ca3af; font-size:12px; margin-left:10px;">Severidade:</label>
<select id="backupSeverityFilter" style="background:#0b1220; color:#e5e7eb; border:1px solid #1f2937; padding:4px 8px; border-radius:6px;">
  <option value="all">Todos</option>
  <option value="medium">Medium+ (&gt;6h)</option>
  <option value="high">High+ (&gt;30h)</option>
  <option value="critical">Critical (&gt;48h)</option>
</select>
```

#### 2.2 Badges de Contagem por Severidade

```html
<div id="backupSeverityBadges" style="display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap;">
  🔴 Critical: 12
  🟠 High: 18
  🟡 Medium: 10
  ⚪ Low: 5
</div>
```

#### 2.3 Função JavaScript para Calcular Severidade

```javascript
const getMaxSeverity = (item) => {
  const issuesList = item.issues || [];
  let maxSeverity = 'low';
  let maxHours = 0;

  issuesList.forEach(issueStr => {
    // Parsear "DIFF > 12h", "LOG > 48h", "FULL > 7d", etc
    const match = issueStr.match(/(\d+)([hd])/);
    if (match) {
      let hours = parseInt(match[1]);
      if (match[2] === 'd') hours *= 24; // converter dias para horas

      if (hours > maxHours) maxHours = hours;

      // Aplicar thresholds: ≤6h=low, >6h-30h=medium, >30h-48h=high, >48h=critical
      if (hours > 48) maxSeverity = 'critical';
      else if (hours > 30 && maxSeverity !== 'critical') maxSeverity = 'high';
      else if (hours > 6 && !['critical', 'high'].includes(maxSeverity)) maxSeverity = 'medium';
    }
  });

  return { severity: maxSeverity, maxHours };
};
```

#### 2.4 Lógica de Filtro Cascata

```javascript
// Filtro por severidade (CASCATA: medium inclui medium+high+critical)
if (severityFilterSel.value !== 'all') {
  const severityHierarchy = {
    'medium': ['medium', 'high', 'critical'],
    'high': ['high', 'critical'],
    'critical': ['critical']
  };
  const allowedSeverities = severityHierarchy[severityFilterSel.value] || [];
  dataToRender = dataToRender.filter(it => {
    const { severity } = getMaxSeverity(it);
    return allowedSeverities.includes(severity);
  });
}
```

---

## 📸 Preview da UI

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🔺 Databases com Issues (67)                                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ Ordenar: [Severidade ▼]  Filtro: [Todos ▼]                          │
│ Severidade: [Medium+ (>6h) ▼]  Database: [________] ☐ Incluir sist. │
│ [Exportar CSV]                                                        │
│                                                                       │
│ 🔴 Critical: 12  🟠 High: 18  🟡 Medium: 10  ⚪ Low: 5               │
│                                                                       │
│ ┌────────────┬──────────────┬────────────┬─────────┬────────────┐   │
│ │ Database   │ Recovery     │ Último     │ Último  │ Issues     │   │
│ │            │ Model        │ FULL       │ LOG     │            │   │
│ ├────────────┼──────────────┼────────────┼─────────┼────────────┤   │
│ │ EFTDB2024  │ FULL         │ 7d 12h ago │ 52h ago │ 🟠DIFF>30h │   │
│ │ VENDAS     │ FULL         │ 2d 8h ago  │ 6h ago  │ 🟡DIFF>12h │   │ ← Filtrado (medium)
│ │ EXAMPLE_DB    │ FULL         │ 14d ago    │ 72h ago │ 🔴FULL>48h │   │
│ └────────────┴──────────────┴────────────┴─────────┴────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**Com filtro "High+ (>30h)" selecionado:**
- Mostra apenas EFTDB2024 (DIFF>30h = high) e EXAMPLE_DB (FULL>48h = critical)
- Esconde VENDAS (DIFF>12h = medium, não atinge high)

**Com filtro "Critical (>48h)" selecionado:**
- Mostra apenas EXAMPLE_DB (FULL>48h = critical)
- Esconde EFTDB2024 e VENDAS

---

## 🎯 Workflow do DBA

### Cenário: DBA tem 67 databases com issues

**Passo 1:** Abre o módulo Backup
```
Vê: "Databases com Issues (67)"
Badges: 🔴 Critical: 12  🟠 High: 18  🟡 Medium: 10  ⚪ Low: 5
```

**Passo 2:** Filtra por Critical
```
Seleciona: Severidade → "Critical (>48h)"
Tabela mostra: 12 databases (gaps > 48h)
```

**Passo 3:** Resolve os críticos primeiro
```
Verifica backups, executa jobs, corrige problemas
```

**Passo 4:** Expande para High+
```
Seleciona: Severidade → "High+ (>30h)"
Tabela mostra: 30 databases (12 critical + 18 high)
```

**Passo 5:** Se tudo ok, vê todos
```
Seleciona: Severidade → "Todos"
Tabela mostra: 67 databases
```

---

## 🔍 Exemplos de Classificação

### Database: EFTDB2024
**Issues:** `["DIFF > 35h", "LOG > 8h"]`

**Cálculo:**
- DIFF > 35h → 35h > 30h → **high**
- LOG > 8h → 8h > 6h → medium
- **Severidade máxima:** high 🟠

**Aparece nos filtros:**
- ✅ Todos
- ✅ Medium+ (>6h)
- ✅ High+ (>30h)
- ❌ Critical (>48h)

---

### Database: VENDAS
**Issues:** `["DIFF > 12h"]`

**Cálculo:**
- DIFF > 12h → 12h > 6h → **medium**

**Aparece nos filtros:**
- ✅ Todos
- ✅ Medium+ (>6h)
- ❌ High+ (>30h)
- ❌ Critical (>48h)

---

### Database: EXAMPLE_DB
**Issues:** `["FULL > 7d"]` (= 168h)

**Cálculo:**
- FULL > 168h → 168h > 48h → **critical**

**Aparece nos filtros:**
- ✅ Todos
- ✅ Medium+ (>6h)
- ✅ High+ (>30h)
- ✅ Critical (>48h)

---

## 💾 Persistência

O filtro selecionado é salvo no `localStorage`:
```javascript
localStorage.setItem('backup_severity_filter', 'critical');
```

Ao recarregar a página, o filtro é restaurado:
```javascript
severityFilterSel.value = localStorage.getItem('backup_severity_filter') || 'all';
```

---

## 📦 Arquivos Modificados

1. ✅ `watcherdb_main.py` - Endpoint `/api/monitoring/backup/server/{server_id}/gaps`
2. ✅ `templates/watcherdb_portal.html` - UI e lógica JavaScript

**Replicado para:**
- ✅ WATCHERDB_DEV
- ✅ WATCHERDB_DEV_V4
- ✅ WATCHERDB_V5

---

## 🧪 Como Testar

1. **Acesse o dashboard** do servidor com issues
2. **Abra o módulo "Backup"**
3. **Veja a seção "Databases com Issues"**
4. **Clique no dropdown "Severidade"**
5. **Selecione "Critical (>48h)"** → tabela filtra apenas críticos
6. **Selecione "High+ (>30h)"** → tabela mostra high + critical
7. **Veja os badges** → contadores atualizados em tempo real

---

## 🎨 Cores e Badges

| Severidade | Cor Hex | Emoji | Badge |
|------------|---------|-------|-------|
| Critical   | #ef4444 | 🔴    | `background:#ef4444; color:#fff` |
| High       | #f59e0b | 🟠    | `background:#f59e0b; color:#fff` |
| Medium     | #eab308 | 🟡    | `background:#eab308; color:#fff` |
| Low        | #6b7280 | ⚪    | `background:#6b7280; color:#fff` |

---

**Aprovado pelo DBA:** ✅
**Facilita priorização:** ✅
**Visual intuitivo:** ✅
**Performance:** ✅ (filtro client-side, sem overhead)
