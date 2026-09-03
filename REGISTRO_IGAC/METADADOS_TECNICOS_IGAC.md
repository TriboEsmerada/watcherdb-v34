# METADADOS TÉCNICOS - WATCHERDB v1.4.8.2
## Registro IGAC (Inspeção-Geral das Atividades Culturais)

---

## INFORMAÇÕES GERAIS

| Campo | Valor |
|-------|-------|
| **Nome do Software** | WatcherDB |
| **Versão** | 1.4.8.2 |
| **Data de Desenvolvimento** | 2024-2025 |
| **Data de Registro** | 18/11/2025 |
| **Titular dos Direitos** | TAP - Transportes Aéreos Portugueses, S.A. |
| **País de Origem** | Portugal |
| **Tipo de Software** | Sistema de Monitoramento de Bases de Dados |
| **Categoria** | Software Corporativo - Gestão de Infraestrutura |
| **Licença** | Proprietário (Uso Interno TAP) |

---

## CLASSIFICAÇÃO TÉCNICA

### Tipo de Aplicação
- [x] Aplicação Web
- [x] API REST
- [ ] Aplicação Desktop
- [ ] Aplicação Móvel
- [x] Software de Servidor
- [ ] Biblioteca/Framework

### Arquitetura
- [x] Cliente-Servidor
- [x] Arquitetura de Microsserviços (parcial)
- [x] API RESTful
- [ ] Monolítico
- [x] Assíncrono (async/await)

### Área de Aplicação
- [x] Monitoramento e Gestão
- [x] Análise de Dados
- [x] Inteligência Artificial / Machine Learning
- [x] Business Intelligence
- [x] DevOps / SRE

---

## TECNOLOGIAS UTILIZADAS

### Linguagens de Programação

| Linguagem | Versão | Uso | % do Código |
|-----------|--------|-----|-------------|
| **Python** | 3.13+ | Backend, lógica de negócio, ML | 60% |
| **JavaScript** | ES6+ | Frontend interativo | 25% |
| **HTML5** | 5.0 | Interface web | 10% |
| **CSS3** | 3.0 | Estilos e layout | 3% |
| **SQL** | T-SQL, PL/SQL | Queries de diagnóstico | 2% |

### Frameworks e Bibliotecas Principais

**Backend (Python):**
- FastAPI 0.115.5 - Framework web assíncrono
- Uvicorn 0.32.1 - Servidor ASGI
- pyodbc 5.2.0 - Conector SQL Server
- cx_Oracle 8.3.0 - Conector Oracle
- statsmodels 0.14.4 - Análise estatística e ML
- scikit-learn 1.5.2 - Machine Learning
- pandas 2.2.3 - Manipulação de dados
- numpy 2.1.3 - Computação numérica

**Frontend (JavaScript):**
- Chart.js - Visualização de gráficos
- Font Awesome - Ícones
- Vanilla JS - Sem dependências de frameworks

### Bases de Dados Suportadas
- Microsoft SQL Server (2012+)
- Oracle Database (11g+)
- SQLite (cache local)

### Protocolos e Padrões
- HTTP/HTTPS
- REST API
- JSON
- ODBC
- TCP/IP
- WebSockets (futuro)

---

## MÉTRICAS DO CÓDIGO

### Estatísticas Gerais

| Métrica | Valor |
|---------|-------|
| **Total de Linhas de Código** | ~20.000 |
| **Arquivos Python** | 25+ |
| **Arquivos JavaScript** | 1 (monolítico) |
| **Arquivos HTML** | 1 (SPA) |
| **Módulos Python** | 10+ |
| **Endpoints API** | 30+ |
| **Queries SQL** | 15+ especializadas |
| **Funções/Métodos** | 200+ |
| **Classes** | 30+ |

### Distribuição de Código

```
Total: ~20.000 linhas

Backend Python:     ~12.000 linhas (60%)
├── watcherdb_main.py:      4.230 linhas
├── modules/:                6.000 linhas
└── api/:                    1.770 linhas

Frontend JS/HTML:    ~8.000 linhas (40%)
├── watcherdb_portal.html:  9.500 linhas
    ├── HTML:                 1.000 linhas
    ├── JavaScript:           7.500 linhas
    └── CSS:                  1.000 linhas
```

### Complexidade

| Aspecto | Nível |
|---------|-------|
| **Complexidade Ciclomática Média** | Moderada (10-15) |
| **Profundidade de Herança** | Baixa (1-2) |
| **Acoplamento** | Moderado |
| **Coesão** | Alta |
| **Manutenibilidade** | Alta |

---

## FUNCIONALIDADES TÉCNICAS

### 1. Monitoramento em Tempo Real
- **Tecnologia:** FastAPI + WebSockets (planejado)
- **Frequência:** Consultas a cada 30-60s
- **KPIs Monitorados:** 15+ métricas

### 2. Análise Preditiva com Machine Learning
- **Algoritmos:**
  - ARIMA (AutoRegressive Integrated Moving Average)
  - Holt-Winters (Exponential Smoothing)
  - Linear Regression (scikit-learn)
- **Bibliotecas:** statsmodels, scikit-learn
- **Input:** Séries temporais de crescimento de filegroups
- **Output:** Previsões de 30-90 dias, MonthsUntilFull

### 3. SQL Diagnostics
- **Queries Personalizadas:** 15+
- **Categorias:**
  - Performance (3 queries)
  - Armazenamento (4 queries)
  - Manutenção (3 queries)
  - Servidor (2 queries)
  - Análise (4 queries)
- **Parametrização:** Suporte a filtros dinâmicos

### 4. Análise de Espaço
- **Métricas Calculadas:**
  - Free % (percentual livre)
  - MonthsUntilFull (meses até lotação)
  - Disk Overflow Risk (risco de exceder disco)
  - Growth Rate (taxa de crescimento)
- **Visualização:** Gráficos interativos com Chart.js

### 5. Teste de Conectividade Otimizado
- **Protocolo:** TCP (porta 1433 SQL Server, 1521 Oracle)
- **Timeout:** 1s (modo quick), 2s (modo full)
- **Performance:** 95-97% mais rápido que implementação anterior

---

## ARQUITETURA DO SISTEMA

### Componentes Principais

```
┌─────────────────────────────────────────────────────────────┐
│                       WATCHERDB                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐         │
│  │  Frontend  │  │  REST API   │  │   Backend    │         │
│  │  (HTML/JS) │◄─┤   (FastAPI) │◄─┤   (Python)   │         │
│  └────────────┘  └─────────────┘  └──────────────┘         │
│                                           │                  │
│                                           ▼                  │
│  ┌────────────────────────────────────────────────┐         │
│  │          Módulos de Monitoramento              │         │
│  ├────────────────────────────────────────────────┤         │
│  │ • Space Analysis   • CPU Analysis              │         │
│  │ • Backup Analysis  • Memory Analysis           │         │
│  │ • Service Monitor  • Predictive ML             │         │
│  └────────────────────────────────────────────────┘         │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────┐         │
│  │           Conexões com Databases               │         │
│  ├────────────────────────────────────────────────┤         │
│  │ • SQL Server (pyodbc)                          │         │
│  │ • Oracle (cx_Oracle)                           │         │
│  │ • SQLite (cache)                               │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de Dados

```
1. User Request (Browser)
   ↓
2. Frontend (HTML/JS)
   ↓
3. REST API (FastAPI)
   ↓
4. Business Logic (Python Modules)
   ↓
5. Database Queries (pyodbc/cx_Oracle)
   ↓
6. SQL Server / Oracle
   ↓
7. Data Processing (pandas/numpy)
   ↓
8. ML Analysis (statsmodels) [opcional]
   ↓
9. JSON Response
   ↓
10. Frontend Rendering (Chart.js)
```

---

## SEGURANÇA

### Autenticação e Autorização
- **Windows Authentication** (SQL Server)
- **Trusted Connection** (sem senha em texto plano)
- **SQL Authentication** (suporte opcional)

### Proteções Implementadas
- **SQL Injection:** Escape de caracteres especiais
- **XSS:** Sanitização de inputs
- **CORS:** Configurado para domínios autorizados
- **Timeout:** Limites de tempo para prevenir DoS

### Auditoria e Logging
- **Logs Rotativos:** Rotação automática para evitar crescimento descontrolado
- **Níveis de Log:** DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Timestamps UTC:** Todos os eventos com timestamp

### Privacidade e Compliance
- **GDPR Compliant:** Não coleta dados pessoais
- **On-Premises:** Todo processamento interno
- **Sem Telemetria:** Nenhum dado enviado externamente

---

## PERFORMANCE E ESCALABILIDADE

### Otimizações Implementadas

1. **Assíncrono (async/await)**
   - Operações não bloqueantes
   - Até 100x mais rápido em operações I/O

2. **Caching Inteligente**
   - SQLite para cache local
   - TTL configurável por tipo de dado
   - Redução de 80% em queries repetidas

3. **Connection Pooling**
   - Reutilização de conexões SQL
   - Reduz overhead de conexão

4. **Lazy Loading**
   - Carregamento sob demanda
   - Reduz tempo inicial de carregamento

5. **Timeout Agressivos**
   - 1s para testes rápidos
   - Previne travamentos

### Métricas de Performance

| Operação | Tempo | Observação |
|----------|-------|------------|
| **Dashboard Loading** | 2-3s | 50 servidores |
| **SQL Query Execution** | 1-5s | Dependendo da complexidade |
| **Teste de Conectividade** | < 1s | Modo quick (95% mais rápido) |
| **Análise Preditiva** | 5-10s | Relatório completo com ML |
| **Carga de Página** | 1-2s | Primeira carga |

### Capacidade e Limites

| Recurso | Limite Testado | Limite Teórico |
|---------|----------------|----------------|
| **Servidores Monitorados** | 100+ | 500+ |
| **Databases por Servidor** | Ilimitado | Limitado pelo SGBD |
| **Usuários Simultâneos** | 10+ | 50+ |
| **Histórico de Dados** | 12 meses | Ilimitado (com limpeza) |
| **Queries Simultâneas** | 20+ | 100+ |

---

## DEPENDÊNCIAS E REQUISITOS

### Requisitos de Sistema

**Servidor:**
- **Sistema Operacional:** Windows Server 2016+ ou Linux
- **Python:** 3.13+
- **Memória RAM:** 4GB mínimo, 8GB recomendado
- **Disco:** 10GB+ para aplicação e cache
- **Rede:** Acesso TCP às portas SQL (1433, 1521)

**Cliente (Browser):**
- **Navegadores Suportados:**
  - Chrome 90+
  - Firefox 88+
  - Edge 90+
  - Safari 14+
- **JavaScript:** Habilitado
- **Resolução:** 1280x720 mínimo

### Drivers Necessários
- **ODBC Driver for SQL Server:** 17+ ou Native Client 11+
- **Oracle Instant Client:** 12.2+ (se usar Oracle)

### Dependências Python (requirements.txt)

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
pyodbc==5.2.0
cx-Oracle==8.3.0
statsmodels==0.14.4
scikit-learn==1.5.2
pandas==2.2.3
numpy==2.1.3
aiofiles==24.1.0
python-multipart==0.0.17
```

**Total de Dependências:** 35+ (incluindo sub-dependências)

---

## DOCUMENTAÇÃO

### Documentos Técnicos Incluídos

1. **CHANGELOG.md** - Histórico completo de versões e mudanças
2. **PARAMETRIZACAO_v1.4.8.1.md** - Guia de parametrização de queries
3. **PING_OPTIMIZATION_v1.4.8.2.md** - Documentação de otimização de conectividade
4. **SPACE_FIXES_v1.4.8.2.md** - Correções do módulo Space
5. **RESUMO_IMPLEMENTACAO_v1.4.8.2.md** - Resumo executivo de implementações
6. **QUERY_VALIDATION_REPORT.md** - Relatório de validação de queries
7. **QUICKSTART.md** - Guia de início rápido

### Comentários e Docstrings
- **Cobertura de Docstrings:** 90%+
- **Type Hints:** Python type annotations em funções principais
- **Comentários Inline:** Explicações de lógicas complexas

---

## HISTÓRICO DE VERSÕES

| Versão | Data | Mudanças Principais |
|--------|------|---------------------|
| 1.0.0 | 2024 | Versão inicial com monitoramento básico |
| 1.4.0 | 2024 | Adição de análise preditiva com ML |
| 1.4.5 | 2025 | Correções de queries e melhorias de performance |
| 1.4.6 | 2025 | Otimização de logs e performance |
| 1.4.7 | 2025 | Refinamento de Event IDs em logs |
| 1.4.8 | 2025-11 | SQL Diagnostics avançado (15+ queries) |
| 1.4.8.1 | 2025-11-17 | Parametrização de queries e correção de bugs |
| 1.4.8.2 | 2025-11-17 | Otimização de ping + correções Space |

---

## PROPRIEDADE INTELECTUAL

### Direitos Autorais
- **Titular:** TAP - Transportes Aéreos Portugueses, S.A.
- **Ano de Criação:** 2024-2025
- **País:** Portugal
- **Tipo de Obra:** Software Original

### Componentes Proprietários
1. **Algoritmos de Análise Preditiva** - Lógica proprietária de cálculo de MonthsUntilFull
2. **SQL Diagnostics Queries** - 15+ queries especializadas desenvolvidas internamente
3. **Detecção de Disk Overflow** - Algoritmo proprietário de detecção de riscos
4. **Interface WatcherDB Portal** - Design e implementação originais
5. **Arquitetura de Módulos** - Estrutura modular proprietária

### Componentes Open Source Utilizados
- FastAPI (MIT License)
- statsmodels (BSD License)
- scikit-learn (BSD License)
- pandas (BSD License)
- Chart.js (MIT License)

**Nota:** Todos os componentes open source são usados de acordo com suas licenças.

---

## CONTACTO

**Organização:** TAP - Transportes Aéreos Portugueses, S.A.
**Departamento:** Tecnologias de Informação
**País:** Portugal
**Website:** www.flytap.com

**Para Questões sobre Registro:**
Email: [A completar]
Telefone: [A completar]

---

## DECLARAÇÃO DE CONFORMIDADE

Declaro que as informações técnicas fornecidas neste documento são verdadeiras
e refletem fielmente as características do software WatcherDB versão 1.4.8.2.

O software é original e foi desenvolvido internamente pela equipa de TI da TAP,
utilizando tecnologias open-source combinadas com lógica proprietária.

Não há violação de direitos de propriedade intelectual de terceiros.

**Data:** 18 de novembro de 2025
**Responsável:** [Nome do Responsável Legal]
**Cargo:** [Cargo]
**Assinatura:** _______________________

---

**FIM DO DOCUMENTO**

Preparado para submissão ao IGAC (Inspeção-Geral das Atividades Culturais)
Data de Preparação: 18/11/2025
Versão do Software: 1.4.8.2
