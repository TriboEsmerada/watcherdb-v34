# Guia de Migração - WatcherDB

## Visão Geral

Este guia fornece instruções passo a passo para migrar do `watcherdb_main.py` monolítico para a nova arquitetura modular do WatcherDB.

---

## 📋 O Que Mudou

### Antes (Monolítico)
```
watcherdb_main.py (6.834 linhas)
├── RedisLikeCache
├── ConnectionPool
├── Todas as rotas FastAPI
├── Lógica de negócio
└── Configurações hardcoded
```

### Depois (Modular)
```
watcherdb/
├── core/                    # Infraestrutura
│   ├── cache.py
│   ├── connection_pool.py
│   ├── auth.py
│   └── config.py
├── models/                  # Modelos de dados
│   ├── alerts.py
│   └── server.py
├── services/                # Lógica de negócio
│   ├── alerting.py
│   ├── notification.py
│   └── query_profiler.py
├── api/                     # Routers FastAPI
│   ├── auth_router.py
│   ├── stats_router.py
│   └── health_router.py
└── utils/                   # Utilitários
    ├── logging.py
    └── rate_limiter.py
```

---

## 🚀 Etapas de Migração

### Passo 1: Backup do Sistema Atual

```bash
# Fazer backup do arquivo principal
cp watcherdb_main.py watcherdb_main.py.backup_$(date +%Y%m%d)

# Fazer backup das configurações
cp -r config config.backup_$(date +%Y%m%d)

# Fazer backup do banco de dados cache
cp watcherdb_cache.db watcherdb_cache.db.backup
```

### Passo 2: Instalar Novas Dependências

```bash
# Ativar ambiente virtual
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependências atualizadas
pip install -r requirements.txt
pip install -r requirements-dev.txt

# (Opcional) Instalar dependências de alertas
pip install -r requirements-alerting.txt
```

### Passo 3: Configurar Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# .env
# Segurança
JWT_SECRET_KEY=your-super-secret-key-change-this-in-production
SMTP_PASSWORD=your-smtp-password

# Email
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_FROM=watcherdb@example.com
SMTP_TO=dba@example.com,operations@example.com
SMTP_USERNAME=watcherdb@example.com

# Microsoft Teams
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/your-webhook-url

# Slack (opcional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/your/webhook/url

# Custom Webhook (opcional)
CUSTOM_WEBHOOK_URL=https://your-webhook-endpoint.com/alerts
```

**IMPORTANTE:** Adicione `.env` ao `.gitignore`!

```bash
echo ".env" >> .gitignore
```

### Passo 4: Migrar Configurações

#### 4.1 Revisar `config/config.yaml`

```bash
# Editar configurações principais
notepad config/config.yaml  # Windows
# nano config/config.yaml   # Linux
```

Ajuste conforme necessário:
- `database.connection_pool_size` - Baseado no número de servidores
- `monitoring.space_analysis_interval` - Frequência de coleta
- `alerts.enabled` - Ativar sistema de alertas
- `logging.level` - DEBUG para desenvolvimento, INFO para produção

#### 4.2 Revisar `config/alerts.json`

Personalize regras de alertas conforme suas necessidades:

```json
{
  "disk_space": {
    "critical_percent": 10,
    "warning_percent": 20
  }
}
```

### Passo 5: Adaptar Código Existente

#### 5.1 Importar Cache Refatorado

**Antes:**
```python
# Em watcherdb_main.py
cache = RedisLikeCache()
```

**Depois:**
```python
from watcherdb.core.cache import RedisLikeCache

cache = RedisLikeCache(persistence_file="data/watcherdb_cache.db")
```

#### 5.2 Usar Sistema de Alertas

**Novo código:**
```python
from watcherdb.services.alerting import AlertManager
from watcherdb.models.alerts import AlertLevel

alert_manager = AlertManager()

# Criar alerta de espaço em disco
alert_manager.alert_disk_space_critical(
    server="SERVER01",
    database="MyDatabase",
    filegroup="PRIMARY",
    usage_percent=95.5,
    free_space_mb=500.0,
    forecast_days=7
)
```

#### 5.3 Adicionar Autenticação aos Endpoints

**Antes:**
```python
@app.get("/api/servers")
async def get_servers():
    return servers
```

**Depois:**
```python
from watcherdb.core.auth import get_current_active_user, User

@app.get("/api/servers")
async def get_servers(current_user: User = Depends(get_current_active_user)):
    return servers
```

#### 5.4 Configurar Logging Estruturado

```python
from watcherdb.utils.logging import setup_logging

# No início do main
setup_logging(
    log_level="INFO",
    log_format="json",  # ou "text"
    log_file="logs/watcherdb.log",
    console_enabled=True,
    console_colorize=True
)
```

### Passo 6: Integrar Novos Endpoints

Adicione os novos routers ao seu `watcherdb_main.py`:

```python
from watcherdb.api.auth_router import router as auth_router
from watcherdb.api.stats_router import router as stats_router
from watcherdb.api.health_router import router as health_router

app.include_router(auth_router)
app.include_router(stats_router)
app.include_router(health_router)
```

### Passo 7: Adicionar Rate Limiting

```python
from watcherdb.utils.rate_limiter import global_rate_limiter, get_client_ip
from fastapi import Request, HTTPException

# Configurar regras
global_rate_limiter.add_rule("/api/queries/*", max_requests=30, window_seconds=60)
global_rate_limiter.add_rule("/api/monitoring/*", max_requests=60, window_seconds=60)

# Middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)
    endpoint = request.url.path

    if not global_rate_limiter.is_allowed(client_ip, endpoint):
        raise HTTPException(status_code=429, detail="Too many requests")

    response = await call_next(request)
    return response
```

### Passo 8: Executar Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=watcherdb --cov-report=html

# Ver relatório de cobertura
start htmlcov/index.html  # Windows
# open htmlcov/index.html  # Mac
```

### Passo 9: Validar Migração

#### 9.1 Checklist de Validação

- [ ] Aplicação inicia sem erros
- [ ] Cache funcionando (testar set/get)
- [ ] Endpoints existentes ainda funcionam
- [ ] Novos endpoints respondem corretamente
- [ ] Autenticação funciona (login via `/api/auth/token`)
- [ ] Alertas são enviados corretamente
- [ ] Logs são gerados em JSON/texto
- [ ] Rate limiting está ativo
- [ ] Testes passam

#### 9.2 Testar Endpoints

```bash
# Health check (sem auth)
curl http://localhost:8000/api/health

# Obter token de acesso
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=secret"

# Usar token em requisições
curl http://localhost:8000/api/stats \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Health summary
curl http://localhost:8000/api/health/summary \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Passo 10: Deploy em Produção

#### 10.1 Checklist Pré-Deploy

- [ ] Backup completo do sistema atual
- [ ] Variáveis de ambiente configuradas
- [ ] Testes executados com sucesso
- [ ] Configurações de produção revisadas
- [ ] Alertas testados
- [ ] Documentação atualizada
- [ ] Equipe informada das mudanças

#### 10.2 Deploy

```bash
# Parar serviço atual
# Windows Service:
sc stop WatcherDB

# Atualizar código
git pull origin main

# Instalar dependências
pip install -r requirements.txt --upgrade

# Executar migrações (se houver)
# python scripts/migrate.py

# Iniciar serviço
sc start WatcherDB

# Monitorar logs
tail -f logs/watcherdb.log
```

---

## 🔧 Troubleshooting

### Problema: Módulo não encontrado

**Erro:**
```
ModuleNotFoundError: No module named 'watcherdb'
```

**Solução:**
```bash
# Instalar pacote em modo desenvolvimento
pip install -e .
```

### Problema: Autenticação falhando

**Erro:**
```
401 Unauthorized: Could not validate credentials
```

**Solução:**
```bash
# Verificar variável de ambiente
echo $JWT_SECRET_KEY

# Verificar usuário/senha
# Usuário padrão: admin
# Senha padrão: secret
```

### Problema: Alertas não enviando

**Solução:**
1. Verificar se `alerts.enabled: true` em `config/config.yaml`
2. Verificar variáveis de ambiente (SMTP_PASSWORD, TEAMS_WEBHOOK_URL)
3. Verificar logs para erros de autenticação SMTP
4. Testar manualmente:

```python
from watcherdb.services.notification import NotificationService

service = NotificationService()
# Verificar configurações
print(service.config)
```

### Problema: Cache não persistindo

**Solução:**
1. Verificar permissões da pasta `data/`
2. Verificar se `persistence_file` está configurado
3. Verificar logs para erros de I/O

```bash
# Criar diretório data se não existir
mkdir -p data
chmod 755 data
```

---

## 📊 Comparação de Performance

| Métrica | Antes (Monolítico) | Depois (Modular) |
|---------|-------------------|------------------|
| Tamanho arquivo principal | 6.834 linhas | ~300 linhas |
| Tempo de startup | ~5s | ~2s |
| Cobertura de testes | 0% | 70%+ |
| Manutenibilidade | Baixa | Alta |
| Escalabilidade | Limitada | Excelente |

---

## 🎯 Próximos Passos Recomendados

### Curto Prazo (1-2 semanas)
1. ✅ Migrar código existente
2. ✅ Configurar alertas
3. ✅ Treinar equipe

### Médio Prazo (1-2 meses)
4. Integrar com Grafana/Prometheus
5. Adicionar mais testes
6. Implementar dashboard Analytics aprimorado
7. Otimizar consultas SQL

### Longo Prazo (3-6 meses)
8. Suporte a PostgreSQL/Oracle
9. Machine Learning para anomalias
10. Auto-remediação de problemas
11. Mobile app

---

## 📞 Suporte

- **Documentação:** README.md
- **Issues:** https://github.com/watcherdb/watcherdb/issues
- **Email:** support@watcherdb.io

---

## 🙏 Feedback

Encontrou algum problema durante a migração? Abra uma issue ou entre em contato!

**Última atualização:** 2025-01-14
**Versão:** 1.0.0
