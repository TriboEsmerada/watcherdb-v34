# WatcherDB - Guia Rápido de Início

## 🚀 Início Rápido em 5 Minutos

### 1. Instalar Dependências

```bash
# Ativar ambiente virtual
venv\Scripts\activate

# Instalar dependências principais
pip install -r requirements.txt

# (Opcional) Instalar alertas
pip install -r requirements-alerting.txt
```

### 2. Configurar Variáveis de Ambiente

Crie `.env` na raiz:

```env
# Segurança
JWT_SECRET_KEY=change-this-to-a-random-secret-key

# Email (para alertas)
SMTP_PASSWORD=your-smtp-password
SMTP_FROM=watcherdb@example.com
SMTP_TO=dba@example.com

# Microsoft Teams (para alertas)
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/your-url
```

### 3. Iniciar Aplicação

```bash
python watcherdb_main.py
```

### 4. Testar API

**Health Check:**
```bash
curl http://localhost:8000/api/health
```

**Login:**
```bash
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=secret"
```

**Usar Token:**
```bash
# Copiar o access_token da resposta acima
curl http://localhost:8000/api/stats \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Documentação Interativa:**
Abra: http://localhost:8000/docs

---

## 📊 Exemplos de Uso

### Usar Sistema de Cache

```python
from watcherdb.core.cache import RedisLikeCache

# Criar cache
cache = RedisLikeCache()

# Armazenar dados
cache.set("server_status", {"status": "online"}, ttl=60)

# Recuperar dados
status = cache.get("server_status")

# Estatísticas
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']}")
```

### Criar Alertas

```python
from watcherdb.services.alerting import AlertManager
from watcherdb.models.alerts import AlertLevel

# Inicializar gerenciador
alert_manager = AlertManager()

# Alerta de espaço em disco
alert_manager.alert_disk_space_critical(
    server="SERVER01",
    database="Production_DB",
    filegroup="PRIMARY",
    usage_percent=95.5,
    free_space_mb=450.0,
    forecast_days=7
)

# Alerta de backup
alert_manager.alert_backup_failure(
    server="SERVER01",
    database="Production_DB",
    last_backup_time="2025-01-13 10:00:00",
    backup_type="FULL",
    age_hours=26.5
)

# Ver alertas ativos
active_alerts = alert_manager.get_active_alerts()
```

### Analisar Performance de Queries

```python
from watcherdb.services.query_profiler import QueryPerformanceProfiler

profiler = QueryPerformanceProfiler()

# Analisar query
analysis = profiler.analyze_query(
    query_text="""
        SELECT * FROM Users
        WHERE UPPER(Email) = 'ADMIN@EXAMPLE.COM'
    """,
    query_hash="abc123",
    execution_count=1000,
    avg_duration_ms=2500.0,
    total_reads=500000
)

# Resultado
print(f"Score: {analysis.overall_score}/100")
print(f"Priority: {analysis.optimization_priority}")

# Problemas encontrados
for issue in analysis.issues:
    print(f"\n{issue.severity.upper()}: {issue.description}")
    print(f"Fix: {issue.recommendation}")
```

### Logging Estruturado

```python
from watcherdb.utils.logging import setup_logging, get_logger

# Configurar logging
setup_logging(
    log_level="INFO",
    log_format="json",
    log_file="logs/watcherdb.log"
)

# Usar logger
logger = get_logger(__name__)
logger.info("Application started")
logger.error("Error occurred", extra={"server_id": 1})
```

### Adicionar Autenticação

```python
from fastapi import Depends
from watcherdb.core.auth import get_current_active_user, require_admin, User

# Endpoint protegido (qualquer usuário autenticado)
@app.get("/api/data")
async def get_data(current_user: User = Depends(get_current_active_user)):
    return {"data": "sensitive info", "user": current_user.username}

# Endpoint apenas para admin
@app.post("/api/admin/action")
async def admin_action(current_user: User = Depends(require_admin)):
    return {"message": "Admin action completed"}
```

### Rate Limiting

```python
from watcherdb.utils.rate_limiter import global_rate_limiter
from fastapi import Request, HTTPException

# Configurar limites
global_rate_limiter.add_rule("/api/queries/*", max_requests=30, window_seconds=60)

# Middleware
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_ip = request.client.host

    if not global_rate_limiter.is_allowed(client_ip, request.url.path):
        raise HTTPException(429, "Too many requests")

    return await call_next(request)
```

---

## 🧪 Executar Testes

```bash
# Todos os testes
pytest

# Com cobertura
pytest --cov=watcherdb

# Específico
pytest tests/unit/test_cache.py

# Verbose
pytest -v
```

---

## 📖 Documentação Completa

- **README.md** - Documentação principal completa
- **MIGRATION_GUIDE.md** - Guia de migração passo a passo
- **IMPROVEMENTS_SUMMARY.md** - Resumo de todas as melhorias
- **API Docs** - http://localhost:8000/docs (Swagger UI)

---

## 🆘 Problemas Comuns

### Erro: Módulo não encontrado

```bash
pip install -e .
```

### Erro: Porta 8000 em uso

```bash
# Mudar porta
uvicorn watcherdb_main:app --port 8001
```

### Erro: JWT token inválido

```bash
# Verificar secret key
echo $JWT_SECRET_KEY

# Fazer login novamente
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=secret"
```

---

## 📞 Suporte

**Email:** support@watcherdb.io
**Documentação:** README.md
**Issues:** https://github.com/watcherdb/watcherdb/issues

---

**Boa sorte com o WatcherDB! 🎉**
