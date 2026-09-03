# Guia de Debug: Status Incorreto no Overview

## Objetivo

Descobrir por que o Overview continua mostrando status incorretos após as correções aplicadas.

---

## ✅ Passo 1: Reiniciar o Backend (OBRIGATÓRIO!)

O Python carrega os módulos apenas UMA vez. Se você não reiniciar, ele continua usando a query antiga em memória.

### Windows (PowerShell):
```powershell
# 1. Parar o servidor (CTRL+C se estiver rodando)

# 2. Reiniciar
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python -m uvicorn watcherdb_main:app --reload --port 8000
```

**IMPORTANTE**: Aguarde até ver a mensagem:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## ✅ Passo 2: Limpar Cache do Navegador

Cache antigo pode estar servindo dados velhos.

### No Chrome/Edge:
1. Pressione `CTRL+SHIFT+R` (hard refresh)
2. OU: `F12` → Network → Marcar "Disable cache"

---

## ✅ Passo 3: Testar Query SQL Diretamente no Servidor

Execute o script `test_tde_query.sql` que criei conectado ao servidor `SQLHDSPRD214\I01`:

```sql
-- Este script está em: test_tde_query.sql
-- Execute conectado ao servidor SQLHDSPRD214\I01
```

### Resultados Esperados:

**Seção 1**: Deve listar TODOS os certificados
**Seção 4**: Deve listar certificados USADOS para criptografia (mais importante!)
**Seção 5**: Deve listar databases encriptadas
**Seção 6**: Deve retornar pelo menos 1 certificado (é a query corrigida)

### ⚠️ Se não retornar nada na Seção 6:

Significa que:
- OU o servidor não tem TDE configurado (mas você disse que tem)
- OU os certificados têm nomes muito diferentes (tipo `MyCert123`)

**Solução**: Me envie o resultado da **Seção 1** (todos os certificados) para eu ajustar a query.

---

## ✅ Passo 4: Testar Endpoints da API

Após reiniciar o backend, teste os endpoints diretamente:

### A. Testar TDE Status
```powershell
curl http://localhost:8000/api/queries/tde-status/SQLHDSPRD214_I01
```

**Esperado**: JSON com array de certificados
```json
{
  "server_id": "SQLHDSPRD214_I01",
  "tde_status": [
    {
      "Server": "SQLHDSPRD214",
      "certificate": "NomeDoCertificado",
      "pvt_key_encryption_type_desc": "...",
      ...
    }
  ]
}
```

**⚠️ Se retornar array vazio**:
```json
{
  "server_id": "SQLHDSPRD214_I01",
  "tde_status": []
}
```

Significa que a query não está encontrando certificados. Execute o Passo 3.

### B. Testar TDE Database Status
```powershell
curl http://localhost:8000/api/queries/tde-database-status/SQLHDSPRD214_I01
```

**Esperado**: JSON com databases encriptadas
```json
{
  "server_id": "SQLHDSPRD214_I01",
  "tde_database_status": [
    {
      "database_name": "NomeDB",
      "is_encrypted": 1,
      "encryption_status": "Sim",
      "encryption_certificate": "NomeDoCertificado",
      "encryption_state": "Criptografado"
    }
  ]
}
```

### C. Testar Always On Overview
```powershell
curl http://localhost:8000/api/alwayson/server/SQLHDSPRD214_I01/overview
```

**Esperado**: JSON com Always On ativo
```json
{
  "is_alwayson": true,
  "ag_name": "SQLAGSPRD213",
  "listener": "SQLAGSPRD213",
  "role": "PRIMARY",
  "is_primary": true,
  "replicas": {
    "total": 2,
    "healthy": 2
  },
  ...
}
```

**⚠️ Se retornar**:
```json
{
  "is_alwayson": false,
  "message": "Este servidor não está configurado como Always On"
}
```

Há um problema na conexão ou no parsing do nome do servidor.

---

## ✅ Passo 5: Verificar Logs do Console do Navegador

Após limpar cache e abrir o servidor no Overview:

1. **Abrir DevTools**: `F12`
2. **Ir para Console**
3. **Filtrar por**: `TDE` ou `ALWAYSON`

### Logs que você DEVE ver:

```
🔍 TDE RAW DATA - tdeData completo: {"server_id":"SQLHDSPRD214_I01","tde_status":[...]}
🔍 TDE RAW DATA - tdeDbData completo: {"server_id":"SQLHDSPRD214_I01","tde_database_status":[...]}
🔍 TDE RAW DATA - tdeStatus array length: X
🔍 TDE RAW DATA - tdeDbStatus array length: Y
🔐 TDE Status: hasCertificate=true, hasEncryptedDatabases=true, encryptedCount=Z, tdeActive=true
```

```
🔍 ALWAYSON RAW DATA - alwaysonData completo: {"is_alwayson":true,"ag_name":"SQLAGSPRD213",...}
🔄 Always On Status - Raw data: {"is_alwayson":true...
🔄 Always On Status - Parsed: is_alwayson=true, explicit=true, hasAgName=true, ...
```

### ⚠️ O que procurar nos logs:

#### Para TDE:
- **`tdeStatus array length: 0`** → Backend não está retornando certificados
- **`tdeDbStatus array length: 0`** → Backend não está retornando databases encriptadas
- **`tdeActive=false`** → Lógica frontend está interpretando como inativo

#### Para Always On:
- **`alwaysonData completo: {"is_alwayson":false}`** → Backend está retornando false
- **`is_alwayson=undefined`** ou `null` → Estrutura da resposta incorreta
- **`final=false`** → Lógica frontend não detectou Always On

---

## ✅ Passo 6: Verificar Logs do Backend

Olhe o terminal onde o backend está rodando. Procure por:

### Logs de Erro:
```
ERROR: Erro ao obter status TDE de SQLHDSPRD214_I01: ...
ERROR: Erro ao obter overview Always On de SQLHDSPRD214_I01: ...
```

### Logs de Sucesso:
```
INFO: Requisição AlwaysOn para SQLHDSPRD214\I01
INFO: ✅ Servidor SQLHDSPRD214_I01 encontrado no inventory Always On
INFO: Retornando overview para SQLHDSPRD214_I01: 2 réplicas, 5 databases
```

---

## 🔍 Checklist de Debug

Marque conforme for testando:

- [ ] **Backend reiniciado** após mudanças no código?
- [ ] **Cache do navegador limpo** (CTRL+SHIFT+R)?
- [ ] **Query SQL testada** diretamente no servidor?
- [ ] **Endpoint TDE Status** retorna dados?
- [ ] **Endpoint TDE Database Status** retorna dados?
- [ ] **Endpoint Always On** retorna `is_alwayson: true`?
- [ ] **Logs do console** mostram dados brutos corretos?
- [ ] **Logs do backend** não mostram erros?

---

## 📋 Informações para Me Enviar

Se ainda não funcionar, me envie:

### 1. Resultado do `test_tde_query.sql` (Seções 1, 4, 5, 6)

**Seção 1 - Todos os certificados**:
```
(cole aqui)
```

**Seção 4 - Certificados usados**:
```
(cole aqui)
```

**Seção 5 - Databases encriptadas**:
```
(cole aqui)
```

**Seção 6 - Query corrigida**:
```
(cole aqui)
```

### 2. Resposta do endpoint TDE Status

```bash
curl http://localhost:8000/api/queries/tde-status/SQLHDSPRD214_I01
```

**Resultado**:
```json
(cole aqui)
```

### 3. Resposta do endpoint Always On

```bash
curl http://localhost:8000/api/alwayson/server/SQLHDSPRD214_I01/overview
```

**Resultado**:
```json
(cole aqui)
```

### 4. Logs do Console do Navegador

**Filtrar por "TDE RAW DATA"**:
```
(cole aqui)
```

**Filtrar por "ALWAYSON RAW DATA"**:
```
(cole aqui)
```

### 5. Logs do Backend (Terminal)

**Últimas 50 linhas**:
```
(cole aqui)
```

---

## 🎯 Diagnóstico Esperado

Com essas informações vou conseguir identificar **exatamente** onde está o problema:

1. **Query SQL não encontra certificados** → Ajustar query
2. **Backend não conecta no servidor** → Verificar credenciais/firewall
3. **Backend retorna dados, mas frontend não processa** → Ajustar lógica frontend
4. **Cache não está sendo limpo** → Forçar clear cache
5. **Servidor não tem TDE realmente configurado** → Validar com DBA

---

## 💡 Dicas Importantes

### Se TDE não aparecer:

1. **Verificar se certificado existe**:
   ```sql
   SELECT * FROM sys.certificates WHERE name NOT LIKE '##%'
   ```

2. **Verificar se databases estão encriptadas**:
   ```sql
   SELECT name, is_encrypted FROM sys.databases WHERE is_encrypted = 1
   ```

3. **Se nenhum dos dois retornar nada**: O servidor realmente não tem TDE configurado.

### Se Always On não aparecer:

1. **Verificar se Always On está habilitado**:
   ```sql
   SELECT SERVERPROPERTY('IsHadrEnabled')
   ```
   **Esperado**: `1` (habilitado)

2. **Verificar Availability Groups**:
   ```sql
   SELECT ag.name FROM sys.availability_groups ag
   ```
   **Esperado**: `SQLAGSPRD213`

3. **Se nenhum retornar nada**: Always On não está configurado ou serviço está parado.

---

## 🚀 Próximos Passos

Depois de executar este guia:

1. ✅ **Se funcionar**: Marcar como resolvido
2. ⚠️ **Se não funcionar**: Me enviar as 5 informações acima
3. 🔧 **Vou ajustar** o código baseado nos dados reais do seu ambiente

---

**Data**: 2025-01-20
**Versão**: WatcherDB v1.4.8.4
**Status**: 🔍 Aguardando Debug do Usuário
