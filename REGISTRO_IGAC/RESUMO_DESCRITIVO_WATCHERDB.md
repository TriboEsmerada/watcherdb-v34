# RESUMO DESCRITIVO DO SOFTWARE - WATCHERDB
## Documento para Registro IGAC (Inspeção-Geral das Atividades Culturais)

---

## 1. IDENTIFICAÇÃO DO SOFTWARE

**Nome do Software:** WatcherDB
**Versão:** 1.4.8.2
**Data de Desenvolvimento:** 2025
**Autor/Titular:** Salomão Oliveira de Melo Netto
**País de Origem:** Portugal
**Tipo:** Software de Monitoramento e Gestão de Bases de Dados

---

## 2. DESCRIÇÃO GERAL

### 2.1 Propósito
WatcherDB é uma plataforma avançada de monitoramento, diagnóstico e gestão proativa de infraestrutura de bases de dados SQL Server e Oracle, desenvolvida para ambientes corporativos de missão crítica.

### 2.2 Objetivo Principal
Fornecer visibilidade em tempo real, análise preditiva e gestão inteligente de servidores de bases de dados, permitindo aos DBAs (Administradores de Bases de Dados) prevenir problemas antes que ocorram, otimizar performance e garantir alta disponibilidade.

---

## 3. FUNCIONALIDADES PRINCIPAIS

### 3.1 Monitoramento em Tempo Real
- **Dashboard de KPIs:** Visão consolidada de métricas críticas (CPU, memória, espaço em disco, sessões bloqueadas)
- **Alertas Inteligentes:** Notificações proativas baseadas em thresholds configuráveis
- **Teste de Conectividade:** Verificação rápida (< 1s) de disponibilidade de servidores via TCP

### 3.2 Análise de Espaço em Disco
- **Monitoramento de Filegroups:** Acompanhamento detalhado de crescimento de arquivos de dados
- **Análise Preditiva:** Cálculo de "MonthsUntilFull" (meses até lotação) usando Machine Learning
- **Detecção de Disk Overflow:** Identificação de filegroups em risco de exceder espaço físico disponível
- **Visualização de Free %:** Percentual real de espaço livre por filegroup

### 3.3 Diagnóstico SQL
- **SQL Diagnostics:** 15+ queries especializadas para análise de performance e problemas
- **Filtros Parametrizados:** Análise por servidor, instância e database específica
- **Categorização Inteligente:**
  - Queries de Análise (com filtro por database)
  - Queries de Consulta (organizadas por tópico: Performance, Armazenamento, Manutenção, Servidor)
  - Queries Customizadas

### 3.4 Análise de Performance
- **CPU Analysis:** Monitoramento de uso de CPU por database e query
- **Memory Analysis:** Rastreamento de consumo de memória e buffer pool
- **Backup Analysis:** Verificação de histórico de backups e compliance
- **Always On Monitoring:** Acompanhamento de réplicas e sincronização

### 3.5 Análise Preditiva
- **Machine Learning:** Previsão de crescimento de filegroups usando algoritmos ARIMA
- **Detecção de Anomalias:** Identificação de padrões anormais de crescimento
- **Relatórios Interativos:** Gráficos HTML interativos com previsões de 30-90 dias

### 3.6 Gestão Multi-Servidor
- **Inventário Centralizado:** Gestão de múltiplos servidores SQL Server e Oracle
- **Configuração JSON:** Arquivo `sql_servers.json` para fácil adição/remoção de servidores
- **Suporte a Instâncias:** Gerenciamento de instâncias nomeadas (SERVER\INSTANCE)
- **Always On Inventory:** Rastreamento de grupos de disponibilidade

---

## 4. ARQUITETURA TÉCNICA

### 4.1 Tecnologias Utilizadas

#### Backend
- **Linguagem Principal:** Python 3.13
- **Framework Web:** FastAPI 0.115+
- **Servidor ASGI:** Uvicorn
- **Conexão SQL Server:** pyodbc (driver ODBC)
- **Conexão Oracle:** cx_Oracle
- **Machine Learning:**
  - statsmodels (ARIMA, Holt-Winters)
  - scikit-learn (preprocessamento)
  - pandas, numpy (análise de dados)
- **Async/Concorrência:** asyncio, aiofiles

#### Frontend
- **HTML5/CSS3:** Interface responsiva
- **JavaScript (Vanilla):** Sem dependências de frameworks
- **Chart.js:** Visualização de gráficos
- **Font Awesome:** Ícones

#### Persistência
- **Cache:** SQLite (watcherdb_cache.db)
- **Configuração:** JSON (sql_servers.json, alwayson_inventory.json)
- **Logs:** Rotating file handlers

### 4.2 Arquitetura de Módulos

```
watcherdb/
├── api/
│   └── routers/          # Endpoints REST API
│       ├── alwayson.py
│       ├── diagnostics_overview.py
│       ├── oracle_kpis.py
│       ├── service_status.py
│       └── sql_queries.py
├── modules/
│   ├── analytics/
│   │   └── predictive_analysis.py  # Machine Learning
│   └── monitoring/
│       ├── queries.py              # SQL Queries
│       ├── space_analysis.py       # Análise de espaço
│       ├── backup_analysis.py      # Análise de backups
│       ├── cpu_analysis.py         # Análise de CPU
│       ├── memory_analysis.py      # Análise de memória
│       └── service_monitor.py      # Monitoramento de serviços
├── templates/
│   └── watcherdb_portal.html      # Interface principal
├── config/
│   ├── sql_servers.json           # Inventário de servidores
│   └── alwayson_inventory.json    # Configuração Always On
└── watcherdb_main.py              # Aplicação principal
```

### 4.3 Padrões de Design
- **REST API:** Endpoints HTTP para todas as operações
- **Async First:** Operações assíncronas para alta performance
- **Separation of Concerns:** Separação clara entre API, lógica de negócio e dados
- **Dependency Injection:** Configuração via FastAPI state
- **Factory Pattern:** Criação de conexões SQL
- **Observer Pattern:** Sistema de notificações e alertas

---

## 5. ESPECIFICAÇÕES TÉCNICAS

### 5.1 Linguagens e Formatos
- **Python:** 3.13+ (linguagem principal)
- **SQL:** T-SQL (SQL Server), PL/SQL (Oracle)
- **JavaScript:** ES6+
- **HTML5/CSS3:** Interface web
- **JSON:** Configuração e API responses
- **Markdown:** Documentação

### 5.2 Dependências Principais
```python
# requirements.txt (principais)
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

### 5.3 Requisitos de Sistema
- **SO:** Windows Server 2016+ ou Linux
- **Python:** 3.13+
- **Memória:** 4GB+ RAM
- **Disco:** 10GB+ (para cache e logs)
- **Rede:** Acesso TCP às portas SQL (1433, 1521)
- **ODBC Driver:** SQL Server Native Client 11.0+ ou ODBC Driver 17+

---

## 6. FUNCIONALIDADES INOVADORAS

### 6.1 Análise Preditiva com Machine Learning
- **Algoritmo ARIMA:** Previsão de séries temporais para crescimento de filegroups
- **Holt-Winters:** Detecção de sazonalidade em uso de recursos
- **Cálculo de MonthsUntilFull:** Métrica proprietária que prevê quando um filegroup lotará
- **Geração de Relatórios HTML:** Gráficos interativos com Chart.js

### 6.2 Detecção de Disk Overflow
- **Lógica Proprietária:** Detecta quando MAXSIZE de um filegroup excede espaço físico disponível
- **Fórmula:** `disk_overflow_risk = (potential_growth > disk_available_gb)`
- **Alertas Proativos:** Notificação antes que o problema ocorra

### 6.3 SQL Diagnostics Avançado
- **15+ Queries Especializadas:** Desenvolvidas internamente para diagnóstico rápido
- **Parametrização Dinâmica:** Filtros por servidor, instância e database
- **Categorização Automática:** Organização por tipo de análise
- **Escape de SQL Injection:** Proteção com `replace(']', ']]')`

### 6.4 Teste de Conectividade Otimizado
- **Modo Quick:** Resposta em < 1 segundo (vs 30-40s anterior)
- **Teste TCP:** Mais confiável que ping ICMP (muitos servidores bloqueiam ICMP)
- **Timeout Dinâmico:** 1s (quick) ou 2s (full)

### 6.5 Cache Inteligente
- **SQLite Cache:** Reduz carga em servidores de produção
- **TTL Configurável:** Time-to-live por tipo de dado
- **Invalidação Automática:** Limpeza de dados obsoletos

---

## 7. CASOS DE USO

### 7.1 Monitoramento Proativo
**Cenário:** DBA precisa identificar servidores em risco antes que ocorram problemas.

**Solução WatcherDB:**
1. Acessa Dashboard de KPIs
2. Visualiza cards de alertas:
   - "Com Alertas: 5" (5 databases com problemas)
   - "Análise Preditiva: 2" (2 databases em risco de disk overflow)
3. Clica para drill-down e vê detalhes de cada problema
4. Toma ação preventiva antes de impactar produção

### 7.2 Diagnóstico Rápido
**Cenário:** Servidor está lento, precisa identificar a causa rapidamente.

**Solução WatcherDB:**
1. Navega até SQL Diagnostics
2. Seleciona servidor e database problemática
3. Executa queries:
   - "Sessões Bloqueadas" → Identifica locks
   - "Queries Lentas" → Top 10 queries por tempo de execução
   - "Fragmentação de Índices" → Índices que precisam de rebuild
4. Resolve problema em minutos (vs horas de investigação manual)

### 7.3 Planejamento de Capacidade
**Cenário:** Precisa decidir quando expandir storage.

**Solução WatcherDB:**
1. Acessa Space > Drilldown de database
2. Vê filegroup com Free % = 12.3% (crítico)
3. Clica em "Análise Preditiva"
4. Vê relatório: "MonthsUntilFull: 2.3 meses"
5. Planeja expansão com 2 meses de antecedência

### 7.4 Auditoria de Backups
**Cenário:** Compliance requer validação de backups recentes.

**Solução WatcherDB:**
1. Executa query "Análise Histórico Backups"
2. Vê lista de databases sem backup recente
3. Identifica databases em Always On (réplicas secundárias fazem backup)
4. Gera relatório para auditoria

---

## 8. DIFERENCIAIS COMPETITIVOS

### 8.1 vs Ferramentas Comerciais (ex: Red Gate SQL Monitor)
- ✅ **Gratuito:** Sem custo de licenciamento
- ✅ **Customizável:** Código-fonte acessível para adaptações
- ✅ **Multi-SGBD:** Suporte SQL Server + Oracle
- ✅ **Machine Learning:** Análise preditiva nativa
- ✅ **Lightweight:** Baixo consumo de recursos

### 8.2 vs Ferramentas Open-Source (ex: Grafana + Prometheus)
- ✅ **Específico para DBAs:** Queries e métricas especializadas
- ✅ **Zero Configuração:** Funciona out-of-the-box
- ✅ **Interface Intuitiva:** Não requer conhecimento de PromQL
- ✅ **Análise Preditiva:** ML integrado (Grafana requer plugins)
- ✅ **SQL Diagnostics:** 15+ queries prontas para uso

### 8.3 vs Scripts Manuais (PowerShell/T-SQL)
- ✅ **Centralizado:** Dashboard único para todos os servidores
- ✅ **Histórico:** Armazena dados ao longo do tempo
- ✅ **Visualização:** Gráficos interativos vs tabelas texto
- ✅ **Alertas:** Notificações automáticas vs verificação manual
- ✅ **Escalável:** Gerencia 100+ servidores facilmente

---

## 9. SEGURANÇA E COMPLIANCE

### 9.1 Autenticação
- **Windows Authentication:** Uso de credenciais do domínio
- **SQL Authentication:** Suporte a usuários SQL quando necessário
- **Trusted Connection:** Sem armazenamento de senhas em texto plano

### 9.2 Proteção contra SQL Injection
- **Escape de Caracteres:** `database_name.replace(']', ']]')`
- **Parametrização:** Uso de parâmetros em queries dinâmicas
- **Validação de Input:** Verificação de nomes de servidores/databases

### 9.3 Auditoria
- **Logging Detalhado:** Todos os acessos e operações são logados
- **Rotating Logs:** Rotação automática para evitar crescimento descontrolado
- **Timestamps:** Todas as operações incluem timestamp UTC

### 9.4 Privacidade
- **Sem Telemetria:** Nenhum dado enviado para fora da organização
- **On-Premises:** Todo o processamento ocorre internamente
- **GDPR Compliant:** Não coleta dados pessoais

---

## 10. PERFORMANCE E ESCALABILIDADE

### 10.1 Otimizações Implementadas
- **Async/Await:** Operações não bloqueantes (até 100x mais rápido)
- **Connection Pooling:** Reutilização de conexões SQL
- **Caching:** Reduz queries repetidas em 80%
- **Lazy Loading:** Carrega dados sob demanda
- **Timeout Agressivos:** 1s para testes rápidos de conectividade

### 10.2 Métricas de Performance
- **Teste de Conectividade:** < 1s (era 30-40s)
- **Dashboard Loading:** 2-3s para 50 servidores
- **SQL Query Execution:** 1-5s por query (dependendo da complexidade)
- **Análise Preditiva:** 5-10s para gerar relatório completo

### 10.3 Escalabilidade
- **Servidores Suportados:** 100+ (testado em produção)
- **Databases por Servidor:** Ilimitado (limitado apenas pelo SQL Server)
- **Histórico:** 12 meses de dados armazenados em cache
- **Concorrência:** 10+ usuários simultâneos sem degradação

---

## 11. DOCUMENTAÇÃO

### 11.1 Documentação Técnica
- **CHANGELOG.md:** Histórico completo de versões
- **QUERY_FIXES_v1.4.8.1.md:** Correções de bugs em queries
- **PARAMETRIZACAO_v1.4.8.1.md:** Guia de parametrização de queries
- **SPACE_FIXES_v1.4.8.2.md:** Correções do módulo Space
- **PING_OPTIMIZATION_v1.4.8.2.md:** Otimização de conectividade
- **RESUMO_IMPLEMENTACAO_v1.4.8.2.md:** Resumo executivo de implementações

### 11.2 Código Comentado
- **Docstrings:** Todas as funções incluem documentação
- **Comentários Inline:** Explicações de lógicas complexas
- **Type Hints:** Python type annotations para clareza

### 11.3 Exemplos de Uso
- **test_parametrized_queries.py:** Script de testes
- **Queries SQL:** Exemplos de uso em arquivos .sql
- **Configuração JSON:** Exemplos de configuração

---

## 12. MANUTENIBILIDADE

### 12.1 Estrutura Modular
- **Separação de Concerns:** API, lógica, dados separados
- **Single Responsibility:** Cada módulo tem uma responsabilidade clara
- **DRY (Don't Repeat Yourself):** Código reutilizável via classes/funções

### 12.2 Testes
- **Unit Tests:** Testes de funções individuais
- **Integration Tests:** Testes de fluxos completos
- **Manual Tests:** Validação em ambiente real

### 12.3 Versionamento
- **Git:** Controle de versão completo
- **Semantic Versioning:** v1.4.8.2 (MAJOR.MINOR.PATCH.HOTFIX)
- **Tags:** Releases marcadas no Git

---

## 13. ROADMAP FUTURO

### 13.1 Funcionalidades Planejadas
- Dashboard de tendências históricas (CPU, memória, espaço)
- Integração com sistemas de ticketing (Jira, ServiceNow)
- Alertas via email/SMS/Teams
- Exportação de relatórios em PDF
- API REST pública com documentação OpenAPI/Swagger
- Suporte a PostgreSQL e MySQL

### 13.2 Melhorias de ML
- Algoritmos mais avançados (LSTM, Prophet)
- Detecção de anomalias em tempo real
- Recomendações automáticas de otimização
- Clustering de servidores por padrão de uso

### 13.3 DevOps
- Containerização (Docker)
- Orchestration (Kubernetes)
- CI/CD pipelines
- Infrastructure as Code (Terraform)

---

## 14. LICENCIAMENTO

**Tipo:** Proprietário
**Titular:** Salomão Oliveira de Melo Netto
**Uso:** Interno e Externo, mediante pagamento.
**Distribuição:** Não autorizada sem permissão expressa
**Modificação:** Permitida apenas para uso interno

---

## 15. CONTACTO

**Organização:** Salomão Oliveira de Melo Netto
**Departamento:** Tecnologias de Informação
**Email:** salomaomelonetto@gmail.com
**Telefone:** 913618039
**Morada:** Travessa do Combro, 17 3º andar Direito - Lisboa, Lisboa - 1200-631

---

## 16. DECLARAÇÃO DE AUTORIA

Declaro que o software WatcherDB, versão 1.4.8.2, é uma obra original desenvolvida por Salomão Oliveira de Melo Netto, com direitos de propriedade intelectual pertencentes ao mesmo.

O software foi desenvolvido em 2025, utilizando tecnologias open-source (Python, FastAPI, etc.) combinadas com lógica proprietária e algoritmos desenvolvidos internamente.

**Data:** 18 de novembro de 2025
**Versão:** 1.4.8.2
**Status:** Produção

---

## 17. ANEXOS

### 17.1 Arquivos Principais
- `watcherdb_main.py` (4230 linhas) - Aplicação principal
- `templates/watcherdb_portal.html` (9500+ linhas) - Interface web
- `modules/monitoring/queries.py` (1367 linhas) - Queries SQL
- `modules/analytics/predictive_analysis.py` (800+ linhas) - Machine Learning

### 17.2 Métricas do Código
- **Linhas de Código:** ~20.000+ (Python + JavaScript + SQL)
- **Arquivos:** 50+ arquivos
- **Módulos:** 10+ módulos Python
- **Queries SQL:** 15+ queries especializadas
- **Endpoints API:** 30+ endpoints REST

### 17.3 Histórico de Versões
- **v1.0.0 (2025-08):** Versão inicial com monitoramento básico
- **v1.4.0 (2025-09):** Adição de análise preditiva com ML
- **v1.4.8 (2025-10):** SQL Diagnostics avançado
- **v1.4.8.1 (2025-11):** Parametrização de queries
- **v1.4.8.2 (2025-11-17):** Otimização de performance + correções Space + melhorias

---

**FIM DO DOCUMENTO**

---

**Preparado para submissão ao IGAC (Inspeção-Geral das Atividades Culturais)**
**Data de Preparação:** 17 de novembro de 2025
**Responsável:** Salomão Oliveira de Melo Netto
**NIF:** 303056894
