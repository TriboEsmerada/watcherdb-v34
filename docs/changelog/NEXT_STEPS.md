# Próximos Passos - WatcherDB v1.1.0

**Status Atual:** 50% das melhorias implementadas (Fases 1-3 concluídas)
**Data:** 2025-11-14
**Prioridade:** Alta

---

## ✅ O Que Foi Feito (Fases 1-3)

### FASE 1: Segurança Crítica ✅
- [x] Removidas credenciais hardcoded
- [x] JWT secret validation obrigatória em produção
- [x] Proteção de arquivos sensíveis no .gitignore
- [x] Configuração Oracle centralizada

### FASE 2: Infraestrutura ✅
- [x] .env.example completo
- [x] Docker Compose para desenvolvimento
- [x] Dockerfile multi-stage
- [x] Pre-commit hooks configurados
- [x] Script de limpeza de backups

### FASE 3: Consolidação de Código ✅
- [x] NotificationService depreciado em modules/
- [x] Documentação de migração criada

---

## 🚀 O Que Falta Fazer (Fases 4-8)

### FASE 4: Refatoração do watcherdb_main.py [PRÓXIMA]

**Objetivo:** Reduzir de 6.834 linhas para < 300 linhas
**Prioridade:** 🔴 ALTA
**Estimativa:** 40 horas
**Dependências:** Nenhuma

#### Etapa 4.1: Extrair Templates HTML (12h)

**Arquivos a criar:**
```
templates/
├── base.html                    # Template base
├── dashboard/
│   ├── index.html              # Dashboard principal
│   ├── space_analysis.html     # Análise de espaço
│   ├── memory_analysis.html    # Análise de memória
│   ├── cpu_analysis.html       # Análise de CPU
│   ├── backup_analysis.html    # Análise de backups
│   └── alwayson_status.html    # Status AlwaysOn
├── components/
│   ├── navigation.html         # Menu de navegação
│   ├── server_card.html        # Card de servidor
│   ├── alert_badge.html        # Badge de alerta
│   └── chart_container.html    # Container de gráfico
└── reports/
    └── forecast_report.html    # Relatório de forecast
```

**Passos:**
1. Identificar blocos HTML em `watcherdb_main.py`
2. Extrair para arquivos Jinja2
3. Adicionar herança de templates ({% extends "base.html" %})
4. Substituir strings HTML por `templates.TemplateResponse()`
5. Testar cada template individualmente

**Comando para identificar HTML:**
```bash
grep -n "<!DOCTYPE\|<html\|<div class=" watcherdb_main.py | head -50
```

---

#### Etapa 4.2: Extrair Rotas para API (16h)

**Arquivos a criar:**
```
api/routers/
├── dashboard.py         # Rotas do dashboard
├── space.py            # Rotas de análise de espaço
├── memory.py           # Rotas de análise de memória
├── cpu.py              # Rotas de análise de CPU
├── backup.py           # Rotas de análise de backups
├── forecast.py         # Rotas de forecast
└── servers.py          # Rotas de gerenciamento de servidores
```

**Estrutura de cada router:**
```python
from fastapi import APIRouter, Depends, HTTPException
from watcherdb.core.auth import get_current_user
from watcherdb.services.space_service import SpaceService

router = APIRouter(
    prefix="/api/space",
    tags=["space-analysis"]
)

@router.get("/analysis/{server_id}")
async def get_space_analysis(
    server_id: str,
    current_user = Depends(get_current_user)
):
    # Lógica aqui
    pass
```

**Passos:**
1. Identificar todas as rotas `@app.get()`, `@app.post()` em watcherdb_main.py
2. Agrupar por funcionalidade
3. Criar router para cada grupo
4. Mover lógica para router
5. Importar e incluir routers no app principal
6. Testar cada endpoint

**Comando para listar rotas:**
```bash
grep -n "@app\.(get\|post\|put\|delete)" watcherdb_main.py
```

---

#### Etapa 4.3: Extrair Lógica de Negócio (12h)

**Arquivos a criar:**
```
watcherdb/services/
├── space_service.py        # Lógica de análise de espaço
├── memory_service.py       # Lógica de análise de memória
├── cpu_service.py          # Lógica de análise de CPU
├── backup_service.py       # Lógica de análise de backups
├── forecast_service.py     # Lógica de forecasting
├── server_service.py       # Gerenciamento de servidores
└── report_service.py       # Geração de relatórios
```

**Estrutura de cada service:**
```python
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SpaceService:
    """Service for space analysis operations"""

    def __init__(self, config: dict):
        self.config = config

    async def analyze_space(self, server_id: str) -> Dict:
        """Analyze space usage for a server"""
        # Lógica aqui
        pass

    async def forecast_space(self, server_id: str, days: int = 30) -> Dict:
        """Forecast space usage"""
        # Lógica aqui
        pass
```

**Passos:**
1. Identificar funções helper em watcherdb_main.py
2. Agrupar por domínio (space, memory, cpu, etc.)
3. Criar classes de serviço
4. Mover lógica para services
5. Atualizar routers para usar services
6. Testar integração

---

### FASE 5: Testes [ALTA PRIORIDADE]

**Objetivo:** Aumentar cobertura de < 10% para 70%+
**Prioridade:** 🔴 ALTA
**Estimativa:** 20 horas
**Dependências:** Fase 4 (parcial)

#### Etapa 5.1: Testes Unitários (12h)

**Arquivos a criar:**
```
tests/unit/
├── test_cache.py ✅ (já existe)
├── test_alerts.py ✅ (já existe)
├── test_auth.py
├── test_notification.py
├── test_space_service.py
├── test_memory_service.py
├── test_backup_service.py
└── test_forecast_service.py
```

**Template de teste:**
```python
import pytest
from watcherdb.services.space_service import SpaceService

@pytest.fixture
def space_service():
    config = {"cache_ttl": 60}
    return SpaceService(config)

class TestSpaceService:
    def test_analyze_space_success(self, space_service):
        # Arrange
        server_id = "test-server"

        # Act
        result = space_service.analyze_space(server_id)

        # Assert
        assert result is not None
        assert "databases" in result

    def test_analyze_space_invalid_server(self, space_service):
        # Arrange
        server_id = "invalid"

        # Act & Assert
        with pytest.raises(ValueError):
            space_service.analyze_space(server_id)
```

**Comando para rodar:**
```bash
pytest tests/unit/ -v --cov=watcherdb --cov-report=html
```

---

#### Etapa 5.2: Testes de Integração (8h)

**Arquivos a criar:**
```
tests/integration/
├── conftest.py              # Fixtures compartilhadas
├── test_api_space.py
├── test_api_memory.py
├── test_api_auth.py
├── test_api_alerts.py
└── test_database_connection.py
```

**Template de teste de API:**
```python
import pytest
from fastapi.testclient import TestClient
from watcherdb_main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_token(client):
    response = client.post("/api/auth/token", data={
        "username": "admin",
        "password": "secret"
    })
    return response.json()["access_token"]

def test_get_space_analysis(client, auth_token):
    # Arrange
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Act
    response = client.get("/api/space/analysis/test-server", headers=headers)

    # Assert
    assert response.status_code == 200
    assert "databases" in response.json()
```

**Comando para rodar:**
```bash
pytest tests/integration/ -v
```

---

### FASE 6: Melhorias de Segurança [MÉDIA PRIORIDADE]

**Objetivo:** Fortalecer segurança da aplicação
**Prioridade:** 🟡 MÉDIA
**Estimativa:** 12 horas
**Dependências:** Nenhuma

#### Checklist de Segurança

- [ ] **Input Sanitization** (4h)
  - Validar todos os inputs de API com Pydantic
  - Sanitizar strings SQL
  - Validar file uploads

- [ ] **SQL Injection Prevention** (2h)
  - Converter todas queries para parameterized
  - Code review de queries dinâmicas

- [ ] **Audit Trail** (4h)
  - Log de todas ações de usuários
  - Tabela de auditoria
  - API de consulta de logs

- [ ] **HTTPS Enforcement** (1h)
  - Middleware para redirecionar HTTP → HTTPS
  - HSTS headers

- [ ] **Rate Limiting Aprimorado** (1h)
  - Limites por IP
  - Limites diferentes por role
  - Detecção de brute force

**Arquivo de exemplo - Input Sanitization:**
```python
# watcherdb/utils/validators.py
from pydantic import BaseModel, validator, constr
from typing import Optional

class ServerQueryRequest(BaseModel):
    server_id: constr(regex=r'^[a-zA-Z0-9\-_]+$')
    database_name: Optional[constr(max_length=128)]

    @validator('database_name')
    def sanitize_database_name(cls, v):
        if v:
            # Remove caracteres perigosos
            dangerous_chars = [';', '--', '/*', '*/', 'xp_', 'sp_']
            for char in dangerous_chars:
                if char in v.lower():
                    raise ValueError(f"Invalid character: {char}")
        return v
```

---

### FASE 7: Documentação [MÉDIA PRIORIDADE]

**Objetivo:** Documentar decisões e arquitetura
**Prioridade:** 🟡 MÉDIA
**Estimativa:** 4 horas
**Dependências:** Fase 4

#### Artefatos a criar

- [ ] **ADRs - Architecture Decision Records** (2h)
  ```
  docs/adr/
  ├── 0001-escolha-fastapi.md
  ├── 0002-jwt-autenticacao.md
  ├── 0003-redis-cache.md
  ├── 0004-refatoracao-watcherdb-main.md
  └── 0005-estrutura-de-testes.md
  ```

- [ ] **Diagramas de Arquitetura** (2h)
  ```
  docs/architecture/
  ├── c4-context.md          # C4 Context diagram
  ├── c4-container.md        # C4 Container diagram
  ├── c4-component.md        # C4 Component diagram
  ├── data-flow.md           # Data flow diagram
  └── erd.md                 # Entity Relationship Diagram
  ```

**Template ADR:**
```markdown
# ADR 0001: Escolha do FastAPI

## Status
Aceito

## Contexto
Precisávamos de um framework web moderno para a API do WatcherDB...

## Decisão
Escolhemos FastAPI porque...

## Consequências
### Positivas
- Performance excelente
- OpenAPI automático
- Type hints nativos

### Negativas
- Curva de aprendizado para async/await
```

---

### FASE 8: Novas Features [BAIXA PRIORIDADE]

**Prioridade:** 🟢 BAIXA
**Estimativa:** 60+ horas
**Dependências:** Fases 4-7

#### 8.1 Dashboard Analytics Interativo (16h)
- Drill-down em gráficos com Plotly
- Filtros dinâmicos
- Exportação PDF/Excel
- Comparação de períodos

#### 8.2 Auto-Remediation (20h)
- Rebuild de índices fragmentados
- Shrink de logs com regras
- Kill de queries longas
- Limpeza de cache

#### 8.3 Capacity Planning (24h)
- Projeções 3/6/12 meses
- Recomendações de hardware
- Cost optimization (Azure/AWS)
- What-if scenarios

---

## 📋 Como Usar Este Guia

### Para Iniciar a Fase 4.1 (Templates HTML)

```bash
# 1. Preparar ambiente
git checkout -b refactor/extract-html-templates
cp .env.example .env
# Editar .env com suas configurações

# 2. Explorar watcherdb_main.py
grep -n "<!DOCTYPE\|<html" watcherdb_main.py > html_locations.txt
cat html_locations.txt

# 3. Criar estrutura de templates
mkdir -p templates/{dashboard,components,reports}

# 4. Extrair primeiro template (exemplo: dashboard)
# Copiar HTML de watcherdb_main.py para templates/dashboard/index.html
# Converter para Jinja2

# 5. Testar template
python test_template.py

# 6. Commit progresso
git add templates/
git commit -m "feat: extract dashboard HTML template"
```

### Para Iniciar a Fase 5.1 (Testes Unitários)

```bash
# 1. Instalar deps de teste
pip install -r requirements-dev.txt

# 2. Criar estrutura de testes
mkdir -p tests/unit

# 3. Copiar template de teste
cp tests/unit/test_cache.py tests/unit/test_space_service.py
# Editar para testar SpaceService

# 4. Rodar testes
pytest tests/unit/test_space_service.py -v

# 5. Verificar cobertura
pytest tests/unit/ --cov=watcherdb --cov-report=html
open htmlcov/index.html
```

---

## 🎯 Métricas de Sucesso

### Fase 4 - Refatoração
- [ ] watcherdb_main.py < 300 linhas
- [ ] 0 HTML inline no código Python
- [ ] Todas rotas em api/routers/
- [ ] Toda lógica em watcherdb/services/

### Fase 5 - Testes
- [ ] Cobertura ≥ 70%
- [ ] Testes passando no CI
- [ ] 0 warnings de pytest

### Fase 6 - Segurança
- [ ] 0 queries SQL não parametrizadas
- [ ] Todos inputs validados
- [ ] Audit trail funcional
- [ ] Bandit security score A

### Fase 7 - Documentação
- [ ] 5+ ADRs criados
- [ ] Diagramas atualizados
- [ ] README reflete estado real

---

## 🆘 Dúvidas Comuns

**Q: Por onde começar?**
A: Comece pela Fase 4.1 (Templates HTML). É a base para as outras fases.

**Q: Posso pular a Fase 4?**
A: Não recomendado. watcherdb_main.py está muito grande e dificulta manutenção.

**Q: Preciso fazer tudo de uma vez?**
A: Não! Faça em sprints de 1-2 semanas. Priorize Fases 4-5 primeiro.

**Q: Como testar sem quebrar produção?**
A: Use Docker Compose para testar localmente. Nunca teste diretamente em produção.

**Q: Quanto tempo vai levar?**
A: Estimativa total: ~97 horas (2-3 semanas com 1 dev full-time)

---

## 📞 Suporte

**Documentação:**
- [IMPROVEMENTS_IMPLEMENTED.md](./IMPROVEMENTS_IMPLEMENTED.md) - O que foi feito
- [README.md](./README.md) - Visão geral do projeto
- [QUICKSTART.md](./QUICKSTART.md) - Guia de início rápido
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) - Guia de migração

**Comandos Úteis:**
```bash
# Ver todos os TODOs no código
grep -r "TODO\|FIXME" watcherdb/ modules/

# Contar linhas de código
find watcherdb/ -name "*.py" | xargs wc -l

# Rodar todos os checks
pre-commit run --all-files

# Testes com coverage
pytest --cov=watcherdb --cov-report=term-missing
```

---

**Última atualização:** 2025-11-14
**Próxima revisão:** Após conclusão da Fase 4
**Responsável:** WatcherDB Team
