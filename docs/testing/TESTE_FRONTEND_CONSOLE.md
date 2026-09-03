# Teste Frontend - Console do Navegador

## Objetivo
Testar se o problema está no cache do frontend ou nos dados do backend.

---

## Passo 1: Abrir o Console

1. Abra o WatcherDB: `http://localhost:8000/watcherdb`
2. Pressione `F12` para abrir DevTools
3. Vá para a aba **Console**

---

## Passo 2: Limpar TODO o Cache

Cole este código no console e pressione ENTER:

```javascript
// Limpar TODO o cache do navegador
tabCache.clear();
localStorage.clear();
sessionStorage.clear();
console.log('✅ Cache completamente limpo!');
console.log('⚠️ Agora recarregue a página: CTRL+R');
```

Depois: **CTRL+R** para recarregar a página.

---

## Passo 3: Selecionar o Servidor e Ver Logs

1. Selecione o servidor: `SQLHDSPRD214\I01`
2. Clique na aba **Overview**
3. **PROCURE ESTES LOGS** no console:

### Logs Esperados:

```javascript
// 1. Verificação de cache
[CACHE CHECK] Cache válido: false, Age: 0s
✅ Cache inválido ou expirado - Buscando dados NOVOS do backend

// 2. Dados brutos recebidos do backend
🔍 TDE RAW DATA - tdeData completo: {"server_id":"SQLHDSPRD214_I01","tde_status":[{"Server":"...","certificate":"TDECert_TAP",...}]}
🔍 TDE RAW DATA - tdeDbData completo: {"server_id":"SQLHDSPRD214_I01","tde_database_status":[...]}
🔍 TDE RAW DATA - tdeStatus array length: 1
🔍 TDE RAW DATA - tdeDbStatus array length: 14

// 3. Análise do frontend
🔐 TDE Status: hasCertificate=TDECert_TAP, hasEncryptedDatabases=true, encryptedCount=12, tdeActive=true

// 4. Always On
🔍 ALWAYSON RAW DATA - alwaysonData completo: {"is_alwayson":true,"ag_name":"SQLAGSPRD213",...}
🔄 Always On Status - Parsed: is_alwayson=true, explicit=true, hasAgName=true, ... final=true, role=PRIMARY
```

---

## Passo 4: Análise dos Logs

### ✅ Cenário 1: Logs mostram dados corretos

Se os logs mostram:
- `tdeStatus array length: 1` ou mais
- `tdeDbStatus array length: 14` ou mais
- `tdeActive=true`
- `is_alwayson=true`

**MAS o Overview ainda mostra "Inativo"**, então:

👉 **O problema está na RENDERIZAÇÃO do HTML**, não nos dados!

**Solução**: Vou verificar o código que renderiza os cards.

### ⚠️ Cenário 2: Logs mostram cache

Se ver este log:
```
⚠️ USANDO DADOS DO CACHE (Xs atrás) - DADOS PODEM ESTAR DESATUALIZADOS!
```

**E os dados estão vazios**, então:

👉 **O problema é CACHE antigo!**

**Solução**:
1. Limpar cache novamente
2. Recarregar HARD: `CTRL+SHIFT+R`
3. Ou executar no console:
```javascript
clearServerCache('SQLHDSPRD214_I01');
renderOverview();
```

### ❌ Cenário 3: Logs mostram arrays vazios

Se ver:
```
🔍 TDE RAW DATA - tdeStatus array length: 0
🔍 TDE RAW DATA - tdeDbStatus array length: 0
```

**E** cache está desabilitado:

👉 **O problema é na COMUNICAÇÃO backend → frontend!**

**Solução**: Verificar se backend está realmente rodando e acessível.

---

## Passo 5: Teste Direto da API

Se os logs mostrarem arrays vazios, teste a API diretamente no console:

```javascript
// Testar endpoint TDE Status
fetch('/api/queries/tde-status/SQLHDSPRD214_I01')
    .then(r => r.json())
    .then(data => {
        console.log('📦 TDE Status API Response:', data);
        console.log('   - tde_status length:', data.tde_status?.length || 0);
    });

// Testar endpoint TDE Database Status
fetch('/api/queries/tde-database-status/SQLHDSPRD214_I01')
    .then(r => r.json())
    .then(data => {
        console.log('📦 TDE DB Status API Response:', data);
        console.log('   - tde_database_status length:', data.tde_database_status?.length || 0);
    });

// Testar endpoint Always On
fetch('/api/alwayson/server/SQLHDSPRD214_I01/overview')
    .then(r => r.json())
    .then(data => {
        console.log('📦 Always On API Response:', data);
        console.log('   - is_alwayson:', data.is_alwayson);
        console.log('   - ag_name:', data.ag_name);
    });
```

**Esperado**:
- TDE Status: `tde_status length: 1` (ou mais)
- TDE DB Status: `tde_database_status length: 14` (ou mais)
- Always On: `is_alwayson: true`

---

## Passo 6: Forçar Refresh SEM Cache

Execute no console:

```javascript
// Limpar cache do servidor específico
clearServerCache('SQLHDSPRD214_I01');

// Forçar re-render do Overview
console.log('🔄 Forçando re-render do Overview...');
renderOverview();
```

Isso vai:
1. Limpar todo cache do servidor
2. Buscar dados NOVOS do backend
3. Re-renderizar o Overview

---

## Resumo do Que Fazer

1. ✅ **Limpar cache** (Passo 2)
2. ✅ **Recarregar** página (CTRL+R)
3. ✅ **Selecionar** servidor SQLHDSPRD214\I01
4. ✅ **Abrir** aba Overview
5. ✅ **Copiar** TODOS os logs do console
6. ✅ **Me enviar** screenshot ou texto dos logs

Com os logs vou saber **exatamente** onde está o problema:
- Cache antigo?
- Dados vazios do backend?
- Problema na renderização?

---

**Data**: 2025-01-20
**Versão**: WatcherDB v1.4.8.4
**Status**: 🔍 Aguardando Logs do Console
