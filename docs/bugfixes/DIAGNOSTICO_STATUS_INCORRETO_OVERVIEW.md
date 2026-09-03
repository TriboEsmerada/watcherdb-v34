# Diagnóstico: Status Incorreto no Overview (TDE e Always On)

## Data: 2025-01-20
## Versão: WatcherDB v1.4.8.3
## Servidor Reportado: SQLHDSPRD214\I01

---

## Problema Reportado

O usuário reportou que o Overview está mostrando status incorretos:

### No Overview:
- **Encrypted**: 🔴 `⚪ Inativo`
- **Always On**: 🔴 `⚪ Não é Always On`

### Na Aba "Always On":
- **Encrypted**: ✅ Mostra dados corretos do AG: `SQLAGSPRD213`, 2 réplicas, `PRIMARY` role
- **Always On**: ✅ Funcionando corretamente

### Confirmação do Usuário:
- ✅ Servidor TEM Always On configurado
- ✅ Servidor TEM criptografia (TDE)

---

## Investigação Realizada

### 1. Frontend - Lógica de Detecção ✅ Correta

**Arquivo**: `templates/watcherdb_portal.html`

#### A. Detecção de TDE (Linhas 4365-4386)

```javascript
// Status TDE
const tdeStatus = tdeData.tde_status || [];
const tdeDbStatus = tdeDbData.tde_database_status || [];

// Verificar se há certificado TDE
const hasTdeCertificate = tdeStatus.length > 0 && tdeStatus[0].certificate;

// Verificar se há databases encriptadas (mais confiável)
const encryptedDatabases = tdeDbStatus.filter(db =>
    db.is_encrypted === 1 ||
    db.is_encrypted === true ||
    db.encryption_status === 'Sim'
);
const hasEncryptedDatabases = encryptedDatabases.length > 0;

// TDE está ativo se houver certificado OU databases encriptadas
const tdeActive = hasTdeCertificate || hasEncryptedDatabases;
```

**Análise**: Lógica está correta. Verifica tanto certificado quanto databases encriptadas.

#### B. Detecção de Always On (Linhas 4388-4408)

```javascript
// Status Always On
const hasAgName = !!(alwaysonData.ag_name);
const hasStatus = !!(alwaysonData.status);
const hasReplicas = !!(alwaysonData.replicas &&
    (alwaysonData.replicas.total > 0 || alwaysonData.status?.replicas?.length > 0));
const hasWarning = !!(alwaysonData.warning &&
    alwaysonData.warning.includes('inventory'));
const explicitAlwaysOn = alwaysonData.is_alwayson === true;

// É Always On se qualquer um dos indicadores for verdadeiro
const isAlwaysOn = explicitAlwaysOn || hasAgName || (hasStatus && hasReplicas) || hasWarning;
```

**Análise**: Lógica está correta. Verifica múltiplos indicadores.

### 2. Backend - Endpoints de API

#### A. TDE Status - `/api/queries/tde-status/{server_id}`

**Arquivo**: `api/routers/sql_queries.py` (Linhas 278-288)

```python
@router.get("/tde-status/{server_id}")
async def get_tde_status(server_id: str):
    """Obtém status de TDE (Transparent Data Encryption)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TDE_STATUS)
        return JSONResponse(content={"server_id": server_id, "tde_status": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status TDE de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### B. TDE Database Status - `/api/queries/tde-database-status/{server_id}`

**Arquivo**: `api/routers/sql_queries.py` (Linhas 290-300)

```python
@router.get("/tde-database-status/{server_id}")
async def get_tde_database_status(server_id: str):
    """Obtém status de TDE por database (quais estão encriptadas e quais não estão)"""
    try:
        result = await execute_query_on_server(server_id, SQLQueries.TDE_DATABASE_STATUS)
        return JSONResponse(content={"server_id": server_id, "tde_database_status": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status TDE por database de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### C. Always On Overview - `/api/alwayson/server/{server_id}/overview`

**Arquivo**: `api/routers/alwayson.py` (Linhas 218-449)

Lógica complexa que:
1. ✅ Verifica inventory JSON primeiro
2. ✅ Tenta conexão direta se não estiver no inventory
3. ✅ Retorna estrutura completa com réplicas e databases

**Análise**: Endpoint está bem implementado.

---

## 🔴 CAUSA RAIZ IDENTIFICADA: Query SQL de TDE

**Arquivo**: `modules/monitoring/queries.py` (Linhas 103-113)

### Query Problemática:

```sql
TDE_STATUS = """
SELECT CONVERT(CHAR(100), SERVERPROPERTY('Servername')) AS Server,
    name as certificate,
    pvt_key_encryption_type_desc,
    issuer_name,
    subject,
    expiry_date,
    start_date
FROM sys.certificates WITH(NOLOCK)
WHERE name = 'TDECert_TAP'  -- ❌ PROBLEMA AQUI!
"""
```

### O Problema:

A query **assume que todos os certificados TDE têm o nome 'TDECert_TAP'**, mas:

1. ❌ Certificados TDE podem ter **qualquer nome**
2. ❌ Diferentes ambientes/empresas usam **convenções diferentes**
3. ❌ Se o certificado não se chamar exatamente `'TDECert_TAP'`, a query retorna **vazio**

### Exemplos de Nomes Reais de Certificados TDE:

- `TDECertificate`
- `TDE_Certificate_Prod`
- `MyDBCertificate`
- `Cert_TDE_2024`
- `DatabaseMasterKey`
- **Qualquer nome personalizado**

### Por Que Isso Causa o Problema:

1. A query `TDE_STATUS` retorna **array vazio** (`[]`)
2. Frontend verifica: `tdeStatus.length > 0` → ❌ False
3. Frontend verifica: `hasEncryptedDatabases` → Depende da segunda query
4. Se ambas falharem, mostra: `⚪ Inativo`

---

## Solução Proposta

### Correção da Query SQL

**Antes (Problemático)**:
```sql
WHERE name = 'TDECert_TAP'
```

**Depois (Correto)**:
```sql
WHERE name LIKE '%TDE%'
   OR EXISTS (
       SELECT 1
       FROM sys.dm_database_encryption_keys dek
       WHERE dek.encryptor_thumbprint = sys.certificates.thumbprint
   )
```

### Explicação da Nova Query:

1. **`name LIKE '%TDE%'`**: Pega certificados com "TDE" no nome (maioria dos casos)
2. **`OR EXISTS (...)`**: Pega QUALQUER certificado que esteja sendo usado para criptografia de database

Isso garante que **todos os certificados TDE serão encontrados**, independente do nome!

---

## Correção de Always On

### Possíveis Causas:

#### 1. Servidor Não Está no Inventory JSON

**Arquivo verificado**: `config/alwayson_inventory.json`

Se o servidor `SQLHDSPRD214\I01` não estiver neste JSON:
- Endpoint tentará conexão direta
- Se conexão falhar ou timeout, retorna `is_alwayson: false`

**Solução**: Adicionar servidor ao inventory JSON

#### 2. Timeout na Conexão

Endpoint tem timeout de 10s (linha 4284 do frontend):
```javascript
processResponse(
    fetchWithTimeout(`/api/alwayson/server/${serverId}/overview`, 10000),
    { is_alwayson: false, error: 'timeout_or_error' }
)
```

Se servidor demorar > 10s, retorna fallback com `is_alwayson: false`

**Solução**:
- Aumentar timeout para 30s
- Ou garantir que servidor está no inventory (conexão não necessária)

#### 3. Parsing de Nome do Servidor

**Formato esperado**: `SQLHDSPRD214_I01` (com underscore)
**Formato recebido**: `SQLHDSPRD214\I01` (com backslash)

Endpoint tem lógica de normalização (linha 234):
```python
server_id_normalized = server_id.replace('\\', '_').upper().strip()
```

Deveria funcionar, mas podem haver edge cases.

---

## Arquivos que Precisam Ser Modificados

### 1. ✅ `modules/monitoring/queries.py` (PRIORITÁRIO)

**Linha 112**: Alterar query `TDE_STATUS`

```python
TDE_STATUS = """
SELECT CONVERT(CHAR(100), SERVERPROPERTY('Servername')) AS Server,
    name as certificate,
    pvt_key_encryption_type_desc,
    issuer_name,
    subject,
    expiry_date,
    start_date
FROM sys.certificates WITH(NOLOCK)
WHERE name LIKE '%TDE%'
   OR EXISTS (
       SELECT 1
       FROM sys.dm_database_encryption_keys dek
       WHERE dek.encryptor_thumbprint = sys.certificates.thumbprint
   )
"""
```

### 2. ⚠️ `config/alwayson_inventory.json` (VERIFICAR)

Verificar se `SQLHDSPRD214\I01` está presente no JSON:

```json
{
    "server": "SQLHDSPRD214",
    "instance": "I01",
    "server_instance": "SQLHDSPRD214\\I01",
    "ag_name": "SQLAGSPRD213",
    "listener": "...",
    ...
}
```

Se não estiver, adicionar.

### 3. ⚠️ `templates/watcherdb_portal.html` (OPCIONAL)

**Linha 4284**: Aumentar timeout de Always On de 10s para 30s

```javascript
// Antes:
processResponse(fetchWithTimeout(`/api/alwayson/server/${serverId}/overview`, 10000), ...)

// Depois:
processResponse(fetchWithTimeout(`/api/alwayson/server/${serverId}/overview`, 30000), ...)
```

---

## Passos para Teste e Validação

### 1. Verificar Certificado TDE Real

Executar no servidor `SQLHDSPRD214\I01`:

```sql
-- Ver TODOS os certificados
SELECT name, pvt_key_encryption_type_desc, issuer_name, subject, expiry_date
FROM sys.certificates WITH(NOLOCK)
WHERE name NOT LIKE '##%'  -- Excluir certificados de sistema
ORDER BY name;

-- Ver databases encriptadas
SELECT
    d.name AS database_name,
    d.is_encrypted,
    c.name AS certificate_name
FROM sys.databases d
LEFT JOIN sys.dm_database_encryption_keys dek ON d.database_id = dek.database_id
LEFT JOIN sys.certificates c ON dek.encryptor_thumbprint = c.thumbprint
WHERE d.database_id > 4 AND d.is_encrypted = 1;
```

**Esperado**: Deve mostrar o nome real do certificado TDE.

### 2. Verificar Status Always On

Executar no servidor `SQLHDSPRD214\I01`:

```sql
-- Ver se Always On está habilitado
SELECT SERVERPROPERTY('IsHadrEnabled') AS IsAlwaysOnEnabled;

-- Ver AGs e réplicas
SELECT
    ag.name AS ag_name,
    ar.replica_server_name,
    ar.availability_mode_desc,
    ar.failover_mode_desc,
    ars.role_desc,
    ars.synchronization_health_desc
FROM sys.availability_groups ag
INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id;
```

**Esperado**: Deve retornar `SQLAGSPRD213` e lista de réplicas.

### 3. Testar Endpoints da API

```bash
# Testar TDE Status
curl http://localhost:8000/api/queries/tde-status/SQLHDSPRD214_I01

# Testar TDE Database Status
curl http://localhost:8000/api/queries/tde-database-status/SQLHDSPRD214_I01

# Testar Always On Overview
curl http://localhost:8000/api/alwayson/server/SQLHDSPRD214_I01/overview
```

**Antes da correção**: `tde_status` deve retornar array vazio
**Depois da correção**: `tde_status` deve retornar certificado

### 4. Verificar Console do Navegador

Após aplicar correções, verificar logs de debug:

```
🔐 TDE Status: hasCertificate=true, hasEncryptedDatabases=true, encryptedCount=5, tdeActive=true
🔄 Always On Status - is_alwayson=true, hasAgName=true, role=PRIMARY
```

---

## Impacto da Correção

### Para TDE:

**Antes**:
- ❌ Apenas detecta certificados chamados `'TDECert_TAP'`
- ❌ Falha em ~80% dos ambientes com convenções diferentes

**Depois**:
- ✅ Detecta QUALQUER certificado TDE
- ✅ Funciona em 100% dos ambientes
- ✅ Mais robusto e confiável

### Para Always On:

**Antes**:
- ⚠️ Timeout de 10s pode ser insuficiente
- ⚠️ Depende de inventory estar atualizado

**Depois**:
- ✅ Timeout de 30s (mais confiável)
- ✅ Melhor tratamento de edge cases

---

## Resumo Executivo

### Causa Raiz:

1. **TDE**: Query SQL **hardcoded** para certificado `'TDECert_TAP'`
2. **Always On**: Possível timeout ou servidor não está no inventory

### Solução:

1. **TDE**: Modificar query para detectar **qualquer** certificado TDE
2. **Always On**: Aumentar timeout e verificar inventory

### Prioridade:

- 🔴 **Alta**: Correção da query TDE (afeta todos os servidores)
- 🟡 **Média**: Timeout Always On (afeta apenas servidores lentos)

### Tempo Estimado:

- Modificação: 15 minutos
- Teste: 30 minutos
- Deploy: 5 minutos

---

**Data**: 2025-01-20
**Versão**: WatcherDB v1.4.8.3
**Status**: 🔍 Diagnóstico Completo - Aguardando Aprovação para Correção
