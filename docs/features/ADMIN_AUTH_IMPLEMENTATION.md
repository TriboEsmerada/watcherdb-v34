# 🔐 Implementação de Autenticação Admin

**Data:** 2026-02-20
**Objetivo:** Proteger endpoints `/api/admin/*` com autenticação JWT role-based (ADMIN only)

---

## 📋 Alterações Realizadas

### 1. **Arquivo Modificado: `watcherdb/api/routers/admin_metrics.py`**

**Mudanças:**
- ✅ Importado `require_admin` e `User` do módulo `watcherdb.core.auth`
- ✅ Adicionado `Depends` do FastAPI
- ✅ Todos os 6 endpoints administrativos agora requerem role ADMIN:
  - `GET /api/admin/metrics/endpoints/usage`
  - `GET /api/admin/metrics/endpoints/unused`
  - `GET /api/admin/metrics/endpoints/deprecated`
  - `GET /api/admin/metrics/endpoints/performance`
  - `GET /api/admin/metrics/endpoints/report`
  - `DELETE /api/admin/metrics/endpoints/clear`

**Exemplo de proteção aplicada:**
```python
@router.get("/metrics/endpoints/usage")
async def get_endpoints_usage_stats(
    top_n: int = Query(...),
    current_user: User = Depends(require_admin)  # ⬅️ NOVO
):
    # ...
```

### 2. **Arquivo Modificado: `watcherdb_main.py`**

**Mudanças:**
- ✅ Registrado router de autenticação (`watcherdb.api.auth_router`)
- ✅ Endpoint `/api/auth/token` agora disponível para login

**Código adicionado (linha ~2524):**
```python
# 🔐 AUTHENTICATION ROUTER
try:
    from watcherdb.api.auth_router import router as auth_router
    app.include_router(auth_router)
    logger.info(f"✅ Router Authentication carregado: {auth_router.prefix} com {len(auth_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Authentication: {e}", exc_info=True)
```

---

## 🔑 Sistema de Autenticação

### **Usuários Padrão (Desenvolvimento)**

⚠️ **ATENÇÃO:** Mudar senhas em produção!

| Username | Password | Role | Acesso Admin |
|----------|----------|------|--------------|
| `admin` | `secret` | ADMIN | ✅ Sim |
| `analyst` | `secret` | ANALYST | ❌ Não |
| `viewer` | `secret` | VIEWER | ❌ Não |

### **Autenticação JWT**
- **Algoritmo:** HS256
- **Token Expiration:** 24 horas (1440 minutos)
- **Secret Key:** Configurável via env var `JWT_SECRET_KEY`

---

## 🧪 Como Testar

### **Passo 1: Reiniciar o Servidor**

```bash
# Parar servidor atual (Ctrl+C ou kill process)
# Depois reiniciar:
cd WATCHERDB_DEV
python watcherdb_main.py
```

### **Passo 2: Executar Script de Teste Automático**

```bash
cd WATCHERDB_DEV
python test_admin_auth.py
```

**O que o teste valida:**
1. ✓ Acesso sem autenticação → deve bloquear com `401 Unauthorized`
2. ✓ Acesso com token VIEWER → deve bloquear com `403 Forbidden`
3. ✓ Acesso com token ADMIN → deve permitir com `200 OK`

**Saída esperada:**
```
================================================================================
RESUMO DOS TESTES
================================================================================
Total de testes: 15
Testes passados: 15
Testes falhados: 0

✓✓✓ TODOS OS TESTES PASSARAM! Autenticação funcionando corretamente.
```

---

## 🔧 Testes Manuais (Alternativa)

### **1. Obter Token de Autenticação**

```bash
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=secret"
```

**Resposta esperada:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### **2. Testar Endpoint SEM Token (deve falhar)**

```bash
curl -X GET "http://localhost:8000/api/admin/metrics/endpoints/usage"
```

**Resposta esperada:** `401 Unauthorized`
```json
{
  "detail": "Not authenticated"
}
```

### **3. Testar Endpoint COM Token (deve funcionar)**

```bash
TOKEN="<cole_o_access_token_aqui>"

curl -X GET "http://localhost:8000/api/admin/metrics/endpoints/usage" \
  -H "Authorization: Bearer $TOKEN"
```

**Resposta esperada:** `200 OK` com estatísticas completas

### **4. Testar com Token VIEWER (deve falhar com 403)**

```bash
# Primeiro, obter token de viewer
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=viewer&password=secret"

# Usar esse token no request
VIEWER_TOKEN="<token_do_viewer>"

curl -X GET "http://localhost:8000/api/admin/metrics/endpoints/usage" \
  -H "Authorization: Bearer $VIEWER_TOKEN"
```

**Resposta esperada:** `403 Forbidden`
```json
{
  "detail": "Operation not permitted. Required role: admin"
}
```

---

## 📊 Endpoints Protegidos

Todos os endpoints abaixo agora **EXIGEM autenticação com role ADMIN**:

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/admin/metrics/endpoints/usage` | GET | Estatísticas de uso |
| `/api/admin/metrics/endpoints/unused` | GET | Endpoints não utilizados |
| `/api/admin/metrics/endpoints/deprecated` | GET | Endpoints deprecated |
| `/api/admin/metrics/endpoints/performance` | GET | Performance de endpoints |
| `/api/admin/metrics/endpoints/report` | GET | Exportar relatório JSON |
| `/api/admin/metrics/endpoints/clear` | DELETE | Limpar estatísticas (irreversível) |

**Endpoint público (sem autenticação):**
- `/api/admin/health` → Health check do router (apenas status)

---

## 🚨 Segurança em Produção

### **Checklist Antes de Deploy:**

- [ ] Mudar senha do usuário `admin` (não usar `secret`)
- [ ] Configurar `JWT_SECRET_KEY` via variável de ambiente
  ```bash
  # Gerar secret key segura:
  python -c 'import secrets; print(secrets.token_urlsafe(32))'
  ```
- [ ] Desabilitar usuários padrão (`analyst`, `viewer`) ou mudar senhas
- [ ] Configurar `WATCHERDB_ENV=production` para forçar validações
- [ ] Considerar integração com LDAP/Active Directory para autenticação corporativa
- [ ] Implementar rate limiting no endpoint `/api/auth/token` (prevenir brute force)
- [ ] Habilitar HTTPS em produção (nunca usar HTTP com JWT)
- [ ] Implementar rotação de tokens (refresh tokens)
- [ ] Adicionar logs de auditoria para operações administrativas

---

## 🔄 Próximos Passos

1. ✅ **Reiniciar servidor** para aplicar mudanças
2. ✅ **Executar testes** (`python test_admin_auth.py`)
3. ⏳ **Migrar frontend** para usar `/api/monitoring/alerts/unified`
4. ⏳ **Atualizar documentação** (README, CHANGELOG, API_ENDPOINTS)
5. ⏳ **Replicar melhorias** para WATCHERDB_V5

---

## 📝 Rollback (Se Necessário)

Se houver problemas, restaure o backup:

```bash
cd "c:\BKP PC TAP - 21012026\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis"

# Renomear atual
mv WATCHERDB_DEV WATCHERDB_DEV_FAILED

# Restaurar backup
cp -r WATCHERDB_DEV_BACKUP_20260220_154057_pre_auth WATCHERDB_DEV
```

---

**Status:** ✅ Implementação concluída
**Aguardando:** Reinicialização do servidor e execução de testes
