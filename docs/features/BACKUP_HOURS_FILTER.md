# Filtro de Gaps por Horas - Backup Issues

## 📊 Implementação: Opção 2 - Filtro por Horas Customizadas

**Data:** 2026-02-20
**Status:** ✅ Implementado e Replicado (DEV, V4, V5)

---

## 🎯 Objetivo

Permitir ao DBA **filtrar a tabela "Databases com Issues"** por threshold de horas específico, com contadores dinâmicos para cada opção.

**Interface:**
```
┌─────────────────────────────────────────┐
│ 📊 Mostrar gaps maiores que:           │
│ ⚪ Todos os gaps        [67 databases]  │
│ ⚪ > 24h                [45 databases]  │
│ 🔘 > 48h                [34 databases]  │ ← selecionado
│ ⚪ > 72h                [18 databases]  │
│ ⚪ > 168h (7d)          [5 databases]   │
└─────────────────────────────────────────┘
```

---

## ✅ Vantagens

✅ **Mais flexível** - thresholds de negócio específicos (24h, 48h, 72h, 7d)
✅ **Fácil comunicação** - "só me mostra gaps acima de 48h"
✅ **Contadores dinâmicos** - vê quantas databases em cada faixa SEM precisar filtrar
✅ **Visual limpo** - radio buttons em vez de dropdown
✅ **Persistência** - lembra última seleção no localStorage

---

## 🔧 Implementação

### Frontend - Radio Buttons com Contadores

**Arquivo:** `templates/watcherdb_portal.html`

#### HTML:
```html
<div style="background:#0f172a; border:1px solid #1f2937; border-radius:8px; padding:12px;">
  <label style="color:#9ca3af; font-size:12px; font-weight:600;">
    📊 Mostrar gaps maiores que:
  </label>
  <div style="display:flex; flex-direction:column; gap:6px;">
    <label style="cursor:pointer; color:#e5e7eb;">
      <input type="radio" name="backupHoursFilter" value="0" checked/>
      Todos os gaps <span id="cnt_all" style="color:#94a3b8;"></span>
    </label>
    <label style="cursor:pointer; color:#e5e7eb;">
      <input type="radio" name="backupHoursFilter" value="24"/>
      &gt; 24h <span id="cnt_24" style="color:#94a3b8;"></span>
    </label>
    <label style="cursor:pointer; color:#e5e7eb;">
      <input type="radio" name="backupHoursFilter" value="48"/>
      &gt; 48h <span id="cnt_48" style="color:#94a3b8;"></span>
    </label>
    <label style="cursor:pointer; color:#e5e7eb;">
      <input type="radio" name="backupHoursFilter" value="72"/>
      &gt; 72h <span id="cnt_72" style="color:#94a3b8;"></span>
    </label>
    <label style="cursor:pointer; color:#e5e7eb;">
      <input type="radio" name="backupHoursFilter" value="168"/>
      &gt; 168h (7d) <span id="cnt_168" style="color:#94a3b8;"></span>
    </label>
  </div>
</div>
```

#### JavaScript:
```javascript
// Função para extrair gap máximo em horas de um item
const getMaxGapHours = (item) => {
  const issuesList = item.issues || [];
  let maxHours = 0;

  issuesList.forEach(issueStr => {
    // Parsear "DIFF > 12h", "LOG > 48h", "FULL > 7d", etc
    const match = issueStr.match(/(\d+)([hd])/);
    if (match) {
      let hours = parseInt(match[1]);
      if (match[2] === 'd') hours *= 24; // converter dias para horas
      if (hours > maxHours) maxHours = hours;
    }
  });

  return maxHours;
};

// Aplicar filtro
const applyRender = () => {
  const selectedHours = parseInt(
    document.querySelector('input[name="backupHoursFilter"]:checked')?.value || '0'
  );

  // Filtrar databases com gaps > threshold
  if (selectedHours > 0) {
    dataToRender = dataToRender.filter(it => {
      const maxHours = getMaxGapHours(it);
      return maxHours > selectedHours;
    });
  }

  // Calcular e atualizar contadores dinâmicos
  const thresholds = [0, 24, 48, 72, 168];
  thresholds.forEach(threshold => {
    if (threshold === 0) {
      counts[threshold] = issues.length; // Total
    } else {
      counts[threshold] = issues.filter(it =>
        getMaxGapHours(it) > threshold
      ).length;
    }
  });

  // Atualizar UI
  document.getElementById('cnt_all').textContent = `[${counts[0]} databases]`;
  document.getElementById('cnt_24').textContent = `[${counts[24]} databases]`;
  document.getElementById('cnt_48').textContent = `[${counts[48]} databases]`;
  document.getElementById('cnt_72').textContent = `[${counts[72]} databases]`;
  document.getElementById('cnt_168').textContent = `[${counts[168]} databases]`;
};
```

---

## 📸 Preview da UI Completa

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔺 Databases com Issues (67)                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Ordenar: [Severidade ▼]  Filtro: [Todos ▼]                     │
│ Database: [________] ☐ Incluir sistema  [Exportar CSV]         │
│                                                                  │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ 📊 Mostrar gaps maiores que:                             │   │
│ │ ⚪ Todos os gaps                    [67 databases]        │   │
│ │ ⚪ > 24h                            [45 databases]        │   │
│ │ 🔘 > 48h                            [34 databases] ←      │   │
│ │ ⚪ > 72h                            [18 databases]        │   │
│ │ ⚪ > 168h (7d)                      [5 databases]         │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│ ┌────────────┬──────────────┬────────────┬─────────┬────────┐  │
│ │ Database   │ Recovery     │ Último     │ Último  │ Issues │  │
│ ├────────────┼──────────────┼────────────┼─────────┼────────┤  │
│ │ EXAMPLE_DB    │ FULL         │ 14d ago    │ 72h ago │FULL>7d │  │ ← 168h
│ │ EFTDB2024  │ FULL         │ 7d ago     │ 52h ago │DIFF>2d │  │ ← 48h
│ └────────────┴──────────────┴────────────┴─────────┴────────┘  │
│                                                                  │
│ (Mostrando 34 de 67 databases - filtrado por > 48h)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Exemplos de Uso

### Exemplo 1: Visão Geral

**Situação:** DBA abre o módulo de Backup

**UI mostra:**
```
📊 Mostrar gaps maiores que:
⚪ Todos os gaps        [67 databases]
⚪ > 24h                [45 databases]
⚪ > 48h                [34 databases]
⚪ > 72h                [18 databases]
⚪ > 168h (7d)          [5 databases]
```

**Insight imediato:**
- Total: 67 databases com issues
- 45 têm gaps > 24h (67.2%)
- 34 têm gaps > 48h (50.7%) ← **CRÍTICOS**
- 18 têm gaps > 72h (26.9%) ← **MUITO CRÍTICOS**
- 5 têm gaps > 7 dias (7.5%) ← **EMERGÊNCIA**

---

### Exemplo 2: Priorização

**Passo 1:** DBA seleciona "> 168h (7d)"
```
Tabela mostra: 5 databases
- São os backups há mais de uma semana sem executar
- PRIORIDADE MÁXIMA
```

**Passo 2:** Resolve os 5 emergenciais, depois seleciona "> 72h"
```
Tabela mostra: 18 databases (inclui os que faltam dos 5 anteriores)
- Agora cnt_168 mostra [2 databases] (resolveu 3)
```

**Passo 3:** Resolve mais alguns, seleciona "> 48h"
```
Tabela mostra: 34 databases
- cnt_72 agora mostra [10 databases] (resolveu 8)
```

---

### Exemplo 3: Parsing de Issues

**Database: VENDAS**
- Issues: `["DIFF > 35h", "LOG > 8h"]`

**Cálculo:**
```javascript
"DIFF > 35h" → match: ["35", "h"] → 35 horas
"LOG > 8h"   → match: ["8", "h"]  → 8 horas
maxHours = 35h
```

**Aparece nos filtros:**
- ✅ Todos os gaps (0h)
- ✅ > 24h (35 > 24)
- ❌ > 48h (35 < 48)
- ❌ > 72h
- ❌ > 168h

---

**Database: EXAMPLE_DB**
- Issues: `["FULL > 7d"]`

**Cálculo:**
```javascript
"FULL > 7d" → match: ["7", "d"] → 7 * 24 = 168 horas
maxHours = 168h
```

**Aparece nos filtros:**
- ✅ Todos os gaps (0h)
- ✅ > 24h (168 > 24)
- ✅ > 48h (168 > 48)
- ✅ > 72h (168 > 72)
- ❌ > 168h (168 = 168, não é maior)

---

**Database: CRITICOS**
- Issues: `["FULL > 14d", "DIFF > 5d"]`

**Cálculo:**
```javascript
"FULL > 14d" → match: ["14", "d"] → 14 * 24 = 336 horas
"DIFF > 5d"  → match: ["5", "d"]  → 5 * 24 = 120 horas
maxHours = 336h
```

**Aparece nos filtros:**
- ✅ Todos
- ✅ > 24h
- ✅ > 48h
- ✅ > 72h
- ✅ > 168h (336 > 168) ← **EMERGÊNCIA!**

---

## 💾 Persistência

```javascript
// Salva no localStorage quando muda
localStorage.setItem('backup_hours_filter', '48');

// Restaura ao carregar a página
const savedHours = localStorage.getItem('backup_hours_filter') || '0';
hoursRadios.forEach(radio => {
  if (radio.value === savedHours) radio.checked = true;
});
```

**Benefício:**
- Seleciona "> 48h" → fecha browser → reabre → **ainda em "> 48h"**

---

## 📦 Arquivos Modificados

1. ✅ `templates/watcherdb_portal.html`
   - Radio buttons com contadores dinâmicos
   - Função `getMaxGapHours()`
   - Lógica de filtro e atualização de contadores

**Replicado para:**
- ✅ WATCHERDB_DEV
- ✅ WATCHERDB_DEV_V4
- ✅ WATCHERDB_V5

---

## 🧪 Como Testar

1. **Acesse** o dashboard de qualquer servidor
2. **Abra** o módulo "Backup"
3. **Veja** a seção "Databases com Issues"
4. **Observe** os contadores: `[67 databases]`, `[45 databases]`, etc
5. **Clique** em "> 48h" → tabela filtra automaticamente
6. **Veja** apenas databases com gaps > 48h
7. **Mude** para "> 168h (7d)" → vê apenas emergências
8. **Recarregue** a página → filtro persiste!

---

## 🎨 Estilo Visual

```css
/* Box do filtro */
background: #0f172a;
border: 1px solid #1f2937;
border-radius: 8px;
padding: 12px;

/* Radio buttons */
accent-color: #3b82f6; (azul do tema)

/* Labels */
color: #e5e7eb; (texto claro)
font-size: 13px;

/* Contadores */
color: #94a3b8; (texto secundário)
```

---

**Aprovado:** ✅
**Mais flexível que severidade:** ✅
**Comunicação clara (horas):** ✅
**Contadores dinâmicos úteis:** ✅
