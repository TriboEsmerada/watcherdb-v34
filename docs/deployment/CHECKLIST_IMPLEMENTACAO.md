# ✅ Checklist: Implementação Always On + Performance

## 📋 Para Ver as Alterações no Frontend

### PASSO 1: Reiniciar Backend (OBRIGATÓRIO)

```bash
cd "c:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"

# Parar servidor (Ctrl+C no terminal onde está rodando)
# Depois iniciar novamente:
python watcherdb_main.py
```

**Logs esperados ao iniciar:**
```
INFO: Application startup complete
INFO: Uvicorn running on http://0.0.0.0:8000
```

---

### PASSO 2: Hard Refresh no Navegador (OBRIGATÓRIO)

**Opção 1: Super Hard Refresh**
```
Ctrl + Shift + F5
```

**Opção 2: Limpar Cache Manualmente**
1. F12 (DevTools)
2. Clique direito no botão Refresh
3. "Esvaziar cache e recarregar"

**Opção 3: Aba Anônima**
```
Ctrl + Shift + N (Chrome)
Ctrl + Shift + P (Firefox)
```

---

### PASSO 3: Verificar se Backend Enviou `warning_context`

**Abrir DevTools (F12) → Network → Filtrar por "summary"**

Procure a requisição: `/api/monitoring/backup/server/SQLHDSPRD406_I01/summary`

**Clique nela → Response → Procure:**
```json
{
    "success": true,
    "is_alwayson": true,
    "current_is_primary": false,
    "warning_context": {
        "type": "secondary",
        "title": "⚠️ Réplica Secundária do Always On",
        "message": "...",
        "primary_server": "...",
        ...
    }
}
```

**Se NÃO aparecer `warning_context`:**
- ❌ Backend não foi reiniciado
- ❌ Servidor não é Always On (esperado para Standalone)
- ❌ Erro na query Always On

---

## 🔍 Diagnóstico: Por Que Não Aparece o Aviso?

### Cenário 1: Backend Não Reiniciado

**Sintoma:**
- Aviso Always On não aparece
- Response da API não tem `warning_context`

**Solução:**
```bash
# Parar WatcherDB (Ctrl+C)
python watcherdb_main.py
```

---

### Cenário 2: Cache do Navegador

**Sintoma:**
- Backend foi reiniciado
- API retorna `warning_context`
- Mas aviso não aparece na tela

**Solução:**
```
Ctrl + Shift + F5 (hard refresh)
```

**Como confirmar que cache foi limpo:**
1. F12 → Network
2. Recarregar página
3. Ver requisição `watcherdb_portal.html`
4. Deve estar com status `200` (não `304 Not Modified`)

---

### Cenário 3: Servidor é Standalone (Não Always On)

**Sintoma:**
- Backend reiniciado ✅
- Cache limpo ✅
- Aviso não aparece (esperado!)

**Causa:**
- Servidor `SQLHDSPRD406\I01` NÃO é Always On
- Logo, não deve mostrar aviso

**Como verificar:**
```sql
-- Executar no servidor:
SELECT
    ags.primary_replica,
    ag.name AS ag_name
FROM sys.availability_groups ag
JOIN sys.dm_hadr_availability_group_states ags
    ON ag.group_id = ags.group_id;
```

**Se retornar vazio:** Servidor é Standalone (sem Always On)

---

## 📊 Tabela de Validação

| Passo | Status | Como Verificar |
|-------|--------|----------------|
| **1. Backend reiniciado** | ⏳ | Logs mostram `Application startup complete` |
| **2. Hard refresh feito** | ⏳ | DevTools → watcherdb_portal.html com status 200 |
| **3. API retorna warning_context** | ⏳ | DevTools → /api/.../summary → Response tem `warning_context` |
| **4. Servidor é Always On** | ⏳ | Query SQL retorna linhas |
| **5. Aviso aparece na tela** | ⏳ | Tela mostra box laranja/azul acima dos cards |

---

## 🧪 Teste Completo (Passo a Passo)

### 1. Testar Servidor Always On Secundário

**Servidor sugerido:** `SQLRPAPRD01\I01` (se for secundário)

**Passos:**
```
1. Reiniciar backend
2. Hard refresh (Ctrl+Shift+F5)
3. Abrir servidor SQLRPAPRD01\I01
4. Clicar em "Backup"
5. Aguardar 15-20s
```

**Resultado esperado:**
```
┌─────────────────────────────────────────────────────────┐
│ 🗄️ Análise de Backup - SQLRPAPRD01\I01                 │
├─────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────────────┐│
│ │ ⚠️ Réplica Secundária do Always On                  ││
│ │                                                       ││
│ │ Este servidor é uma réplica SECUNDÁRIA...            ││
│ │                                                       ││
│ │ 🖥️ Réplica Primária: SQLRPAPRD02\I01                ││
│ │ ⚙️ Backup Preference: Secondary Preferred            ││
│ │ 💡 [Recomendação]                                    ││
│ └───────────────────────────────────────────────────────┘│
│                                                         │
│ [Cards de estatísticas...]                             │
└─────────────────────────────────────────────────────────┘
```

---

### 2. Testar Servidor Always On Primário

**Servidor sugerido:** `SQLRPAPRD02\I01` (se for primário)

**Resultado esperado:**
- Se backup preference = Primary (0): **Sem aviso**
- Se backup preference = Secondary Preferred/Only: **Aviso azul**

---

### 3. Testar Servidor Standalone

**Servidor sugerido:** `SQLHDSTST505\I01`

**Resultado esperado:**
- **Sem aviso** (correto!)
- Análise de backup normal

---

## 🐛 Troubleshooting: Aviso Não Aparece

### Debug Passo 1: Verificar Response da API

**DevTools (F12) → Network → Filtrar "summary"**

**Clique na requisição → Response**

**Procure por `warning_context`:**

**Se EXISTE:**
```json
"warning_context": {
    "type": "secondary",
    "title": "⚠️ Réplica Secundária do Always On",
    ...
}
```
✅ Backend OK → Problema é no frontend (cache)

**Se NÃO EXISTE:**
```json
{
    "success": true,
    "is_alwayson": false,  // ← Servidor não é Always On
    ...
}
```
❌ Servidor não é Always On (esperado para Standalone)

OU

```json
{
    "success": true,
    "is_alwayson": true,
    "current_is_primary": true,  // ← É primário
    "backup_preference": 0,      // ← Backup no Primary
    "warning_context": null      // ← Sem aviso (esperado!)
}
```
✅ Servidor é primário com backup preference = Primary → Sem aviso é correto!

---

### Debug Passo 2: Verificar Console do Navegador

**F12 → Console**

**Procure por erros:**
```
Uncaught TypeError: Cannot read property 'type' of undefined
```

❌ Se aparecer este erro → Frontend tentou acessar `warning_context.type` mas variável é `undefined`

**Solução:** Hard refresh (Ctrl+Shift+F5)

---

### Debug Passo 3: Verificar Logs do Backend

**Terminal onde WatcherDB está rodando:**

**Procure por:**
```
INFO: ✅ Servidor SQLRPAPRD01_I01 é Always On (AG: SQLAGRPAPRD01, Primary: SQLRPAPRD02\I01, Current is Primary: False)
DEBUG: 🚀 Executando AG databases query + Backup analysis + TDP log read em PARALELO...
```

✅ Se aparecer → Backend detectou Always On e está funcionando

❌ Se NÃO aparecer → Query Always On falhou ou servidor não é Always On

---

## ✅ Checklist Final

Marque conforme for completando:

- [ ] **Backend reiniciado** (`python watcherdb_main.py`)
- [ ] **Hard refresh feito** (Ctrl+Shift+F5)
- [ ] **DevTools → Network → Response da API verificada**
- [ ] **Servidor Always On confirmado** (via query SQL ou logs)
- [ ] **Aviso aparece na tela** (box laranja ou azul acima dos cards)

---

## 🚀 Se Tudo Estiver Correto

### Servidor Always On Secundário:
✅ Deve mostrar **box laranja** com:
- Título: "⚠️ Réplica Secundária do Always On"
- Primário exibido
- Backup preference
- Recomendação

### Servidor Always On Primário (backup em secondary):
✅ Deve mostrar **box azul** com:
- Título: "ℹ️ Réplica Primária (Backup em Secundário)"
- Backup preference
- Recomendação

### Servidor Standalone:
✅ **Sem aviso** (correto!)

---

## 📞 Suporte

Se seguiu todos os passos e ainda não aparece:

1. **Tire screenshot do DevTools → Network → Response da API**
2. **Cole logs do backend** (últimas 50 linhas)
3. **Informe qual servidor está testando** (ex: SQLHDSPRD406\I01)

---

**Última atualização:** 2026-01-15
