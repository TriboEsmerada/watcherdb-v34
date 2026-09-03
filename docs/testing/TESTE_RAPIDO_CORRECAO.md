# Teste Rápido: Correção ServerId Format

## 🎯 O que foi corrigido?

O problema era que o **frontend enviava** serverId com **backslash** (`SQLHDSPRD214\I01`) mas o **backend esperava** com **underscore** (`SQLHDSPRD214_I01`).

Agora o frontend **converte automaticamente** antes de fazer chamadas de API!

---

## ✅ Como Testar (5 passos - 2 minutos)

### 1️⃣ **Limpar Cache JavaScript**

**IMPORTANTE**: Pressione:

```
CTRL + SHIFT + R
```

Isso força o navegador a recarregar o JavaScript (sem isso, vai continuar usando o código antigo com o bug!).

---

### 2️⃣ **Abrir Console**

Pressione `F12` e vá para a aba **Console**.

---

### 3️⃣ **Selecionar Servidor**

Selecione o servidor: `SQLHDSPRD214\I01`

---

### 4️⃣ **Abrir Aba Overview**

Clique na aba **Overview**.

---

### 5️⃣ **Verificar Console**

Procure por estas linhas no console:

```
🔍 ServerId ORIGINAL: "SQLHDSPRD214\I01"
🔍 ServerId FORMATADO para API: "SQLHDSPRD214_I01"
                                              ^^^^ underscore!
```

**E logo depois:**

```
🔍 TDE RAW DATA - tdeStatus array length: 1
🔍 TDE RAW DATA - tdeDbStatus array length: 14
🔐 TDE Status: hasCertificate=TDECert_TAP, hasEncryptedDatabases=true, encryptedCount=12, tdeActive=true
```

---

## ✅ O que esperar?

### No Console:

**✅ ANTES (arrays vazios - BUG)**:
```
🔍 TDE RAW DATA - tdeStatus array length: 0  ❌
🔍 TDE RAW DATA - tdeDbStatus array length: 0  ❌
```

**✅ AGORA (arrays com dados - CORRETO)**:
```
🔍 TDE RAW DATA - tdeStatus array length: 1  ✅
🔍 TDE RAW DATA - tdeDbStatus array length: 14  ✅
🔐 TDE Status: tdeActive=true  ✅
```

### No Overview (Visual):

**✅ ANTES (incorreto)**:
- **Encrypted**: ⚪ Inativo ❌
- **Always On**: ⚪ Não é Always On ❌

**✅ AGORA (correto)**:
- **Encrypted**: 🟢 **Ativo** ✅
- **Always On**: 🟢 **Primário - AG: SQLAGSPRD213** ✅

---

## 🐛 Botão de Debug

Também pode clicar no botão vermelho:

```
🐛 DEBUG: Mostrar Dados TDE/AlwaysOn
```

**Esperado**:
```
TDE Status Length: 1
TDE DB Status Length: 14
Encrypted DBs: 12
tdeActive: true
Always On: true
```

**ANTES (incorreto)**:
```
TDE Status Length: 0  ❌
TDE DB Status Length: 0  ❌
tdeActive: false  ❌
```

---

## ⚠️ Se Não Funcionar

### Problema 1: Cache não foi limpo

**Sintoma**: Console ainda mostra `array length: 0`

**Solução**:
1. Feche a aba do navegador
2. Abra uma nova aba
3. Acesse: `http://localhost:8000/watcherdb`
4. Pressione `CTRL+SHIFT+R` novamente

### Problema 2: Backend não reiniciou

**Sintoma**: Console mostra erro 500 ou timeout

**Solução**:
```powershell
# Parar o servidor (CTRL+C)
# Reiniciar:
python -m uvicorn watcherdb_main:app --reload --port 8000
```

### Problema 3: Ainda mostra arrays vazios

**O que fazer**:

1. Tire um **screenshot do console** mostrando estas linhas:
   ```
   🔍 ServerId FORMATADO para API: "..."
   🔍 TDE RAW DATA - tdeStatus array length: ...
   ```

2. Me envie o screenshot para eu investigar

---

## 📋 Checklist

Marque conforme for testando:

- [ ] **CTRL+SHIFT+R** pressionado?
- [ ] **Console aberto** (F12)?
- [ ] **Servidor selecionado** (SQLHDSPRD214\I01)?
- [ ] **Aba Overview** aberta?
- [ ] **Console mostra** "ServerId FORMATADO para API: SQLHDSPRD214_I01"?
- [ ] **Console mostra** "tdeStatus array length: 1" (não mais 0)?
- [ ] **Overview mostra** "🟢 Ativo" para Encrypted?
- [ ] **Overview mostra** "🟢 Primário" para Always On?

Se todos marcados: **✅ SUCESSO!**

---

## 🚀 Teste Adicional (Opcional)

Teste em outros 2-3 servidores para garantir que funciona em todos:

- [ ] Servidor 2: `_______________` → Status TDE: ______
- [ ] Servidor 3: `_______________` → Status TDE: ______
- [ ] Servidor 4: `_______________` → Status TDE: ______

---

**Data**: 2025-01-20
**Versão**: WatcherDB v1.4.8.5
**Status**: ✅ Correção Aplicada - Pronto para Teste
