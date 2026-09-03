# PROMPT: Solucao para Erro 404 no Modulo Jobs

## Problema

O modulo Jobs (`/api/jobs/server/{server_id}`) retorna **HTTP 404 Not Found** no portal WatcherDB.

**Sintoma:**
```
Erro ao carregar dados
HTTP 404: Not Found
```

**URL chamada pelo frontend:**
```javascript
fetch(`/api/jobs/server/${serverIdFormatted}`)
// Exemplo: /api/jobs/server/SQLRPAPRD02_I01
```

---

## Causa Raiz Identificada

### Cenario 1: WATCHERDB_DEV com uvicorn watcherdb_intelligence:app

Quando executado com `python -m uvicorn watcherdb_intelligence:app` no diretorio WATCHERDB_DEV:
- O arquivo `watcherdb_intelligence.py` (arquivo unico) e carregado
- O router de Jobs estava **COMENTADO** nas linhas 2440-2446

### Cenario 2: WATCHERDB_DEV com python watcherdb_main.py

Quando executado com `python watcherdb_main.py`:
- O arquivo `watcherdb_main.py` e carregado
- O router de Jobs ja estava ativo (linhas ~2433)

### Cenario 3: WATCHERDB INTELLIGENCE V1 com uvicorn

Quando executado a partir do diretorio `WATCHERDB INTELLIGENCE V1`:
- O modulo `watcherdb_intelligence/` (pasta) e carregado
- O router de Jobs NAO existia (foi criado posteriormente)

---

## Solucao Implementada

### 1. WATCHERDB_DEV/watcherdb_intelligence.py (PRINCIPAL)

**Arquivo:** `WATCHERDB_DEV/watcherdb_intelligence.py`
**Linha:** 2440-2446

**Antes (COMENTADO):**
```python
# DESATIVADO: Jobs Analysis - Nao utilizado no WatcherDB Intelligence
# try:
#     from api.routers.jobs import router as jobs_router
#     app.include_router(jobs_router)
#     logger.info(f"✅ Router Jobs Analysis carregado: {jobs_router.prefix} com {len(jobs_router.routes)} rotas")
# except Exception as e:
#     logger.error(f"❌ Erro ao carregar router Jobs Analysis: {e}", exc_info=True)
```

**Depois (ATIVADO):**
```python
# Jobs Analysis Router - ATIVADO
try:
    from api.routers.jobs import router as jobs_router
    app.include_router(jobs_router)
    logger.info(f"✅ Router Jobs Analysis carregado: {jobs_router.prefix} com {len(jobs_router.routes)} rotas")
except Exception as e:
    logger.error(f"❌ Erro ao carregar router Jobs Analysis: {e}", exc_info=True)
```

### 2. WATCHERDB INTELLIGENCE V1 (Backup)

**Arquivos criados/modificados:**
- `WATCHERDB INTELLIGENCE V1/watcherdb_intelligence/api/v1/jobs.py` - CRIADO
- `WATCHERDB INTELLIGENCE V1/watcherdb_intelligence/main.py` - Linha 31 (import) e 144 (include_router)

---

## Correcao Adicional: Erro JavaScript

**Problema:** `Uncaught SyntaxError: Identifier 'MaintenanceScore' has already been declared`

**Causa:** O arquivo `innovative_features.js` era carregado como script externo E o mesmo codigo estava inline no `watcherdb_portal.html`.

**Arquivo:** `WATCHERDB_DEV/templates/watcherdb_portal.html`
**Linha:** 20

**Solucao:** Removida a referencia ao script externo:
```html
<!-- innovative_features.js REMOVIDO - codigo ja incluido inline neste arquivo -->
```

---

## Como Iniciar o Servidor (WATCHERDB_DEV)

### Opcao 1: Usando uvicorn (RECOMENDADO para desenvolvimento)
```powershell
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python -m uvicorn watcherdb_intelligence:app --reload --port 8000
```

### Opcao 2: Usando watcherdb_main.py
```powershell
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python watcherdb_main.py
```

**Endpoints de Jobs:**
- `GET /api/jobs/server/{server_id}` - Analise completa de jobs
- `GET /api/jobs/server/{server_id}/trends` - Tendencias de jobs

---

## Verificacao Pos-Correcao

### 1. Verificar nos logs do servidor:
```
✅ Router Jobs Analysis carregado: /api/jobs com 2 rotas
```

### 2. Testar endpoint diretamente:
```bash
curl http://localhost:8000/api/jobs/server/SQLHDSPRD214_I01
```

### 3. Testar no portal:
- Acessar http://localhost:8000/watcherdb
- Selecionar um servidor
- Clicar no botao **Jobs**

---

## Arquivos Relevantes

### Router de Jobs
```
WATCHERDB_DEV/
└── api/
    └── routers/
        └── jobs.py          # Router com 2 endpoints
            ├── GET /api/jobs/server/{server_id}
            └── GET /api/jobs/server/{server_id}/trends
```

### Arquivos Modificados nesta Correcao

| Arquivo | Alteracao |
|---------|-----------|
| `WATCHERDB_DEV/watcherdb_intelligence.py` | Descomentado router Jobs (linhas 2440-2446) |
| `WATCHERDB_DEV/templates/watcherdb_portal.html` | Removido script duplicado (linha 20) |
| `WATCHERDB INTELLIGENCE V1/watcherdb_intelligence/api/v1/jobs.py` | CRIADO (copia do jobs.py) |
| `WATCHERDB INTELLIGENCE V1/watcherdb_intelligence/main.py` | Adicionado import e include_router |

---

## Funcionalidades do Modulo Jobs

1. **Jobs que Falharam (ultimas 24h)**
2. **Todos os Jobs com ultimo status**
3. **Jobs em execucao no momento**
4. **Jobs desabilitados**
5. **Jobs de Manutencao** (Index, Stats, Integrity, Backup)
6. **Cobertura de Manutencao por Database**
7. **Recomendacoes Inteligentes** (databases sem backup, sem index rebuild, etc.)
8. **Analise de Tendencias** (jobs com degradacao de performance)

---

## Dados Retornados

### Endpoint Principal (`/api/jobs/server/{server_id}`)
```json
{
    "failed_jobs": [...],
    "all_jobs": [...],
    "job_history": [...],
    "running_jobs": [...],
    "disabled_jobs": [...],
    "maintenance_jobs": [...],
    "all_databases": [...],
    "databases_without_maintenance": [...],
    "total_jobs": 45,
    "total_failed_24h": 2,
    "total_running": 1,
    "total_disabled": 5,
    "maintenance_coverage_pct": 85.5,
    "maintenance_recommendations": [...]
}
```

### Endpoint de Tendencias (`/api/jobs/server/{server_id}/trends`)
```json
{
    "server_id": "SQLRPAPRD02_I01",
    "summary": {
        "degrading_jobs_count": 3,
        "increased_failures_count": 1,
        "improving_jobs_count": 2
    },
    "alerts": [...],
    "degrading_jobs": [...],
    "increased_failures": [...],
    "improving_jobs": [...]
}
```

---

## Conclusao

**Problema resolvido:** O router de Jobs foi ATIVADO em `watcherdb_intelligence.py`.

**Comando para iniciar:**
```powershell
cd WATCHERDB_DEV
python -m uvicorn watcherdb_intelligence:app --reload --port 8000
```

**O que foi feito:**
1. Descomentado o bloco de codigo do router Jobs em `watcherdb_intelligence.py`
2. Removido script JavaScript duplicado em `watcherdb_portal.html`
3. Criado backup do router em `WATCHERDB INTELLIGENCE V1` (opcional)
