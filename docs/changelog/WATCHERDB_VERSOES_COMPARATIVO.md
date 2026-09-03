# WatcherDB - Comparativo de Versões

## Visão Geral das Edições

O WatcherDB está disponível em **4 edições** para atender diferentes necessidades de monitoramento de ambientes SQL Server. Cada edição oferece um conjunto específico de funcionalidades, desde monitoramento básico até administração avançada de banco de dados.

---

## Resumo Executivo

| Característica | One | Standard | Enterprise | Professional |
|----------------|-----|----------|------------|--------------|
| KPIs | ✅ | ✅ | ✅ | ✅ |
| Overview por Ambiente | ✅ | ✅ | ✅ | ✅ |
| Monitoramento de Serviços | - | ✅ | ✅ | ✅ |
| Métricas de OS (CPU/Memória/Disco) | - | ✅ | ✅ | ✅ |
| Análise de Espaço (Filegroups) | - | ✅ | ✅ | ✅ |
| Análises Preditivas | - | - | ✅ | ✅ |
| Análise de Padrões | - | - | ✅ | ✅ |
| Comandos de Administração | - | - | - | ✅ |
| **Ideal para** | Visão Geral | Operações | Capacity Planning | DBAs Seniores |

---

## WatcherDB One

### Descrição
Edição essencial para **visão consolidada** do ambiente SQL Server. Ideal para gestores e equipes que precisam de uma visão rápida do estado de saúde dos servidores sem necessidade de detalhamento operacional.

### Funcionalidades

#### KPIs Consolidado
Painel centralizado com indicadores-chave de performance e disponibilidade.

| KPI | Descrição | View Consultada |
|-----|-----------|-----------------|
| Database Availability | Databases em estado anormal (não ONLINE) | `KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW` |
| Instance Availability | Instâncias SQL Server online/offline | `KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW` |
| Disk Usage | Volumes com uso crítico (>90%) ou warning (>80%) | `KPI_MSSQL_DISK_USAGE_AGG_VIEW` |
| Transaction Log Usage | Transaction logs com uso elevado | `KPI_MSSQL_TLOG_USAGE_AGG_VIEW` |
| AlwaysOn Status | Grupos de disponibilidade com problemas | `KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW` |
| Mirroring Status | Status de mirroring de databases | `KPI_MSSQL_MIRRORING_STATUS_ACTIVE` |
| Filegroup Usage | Filegroups com espaço crítico | `KPI_MSSQL_FG_USAGE_ACTIVE` |
| Blocked Sessions | Sessões bloqueadas ativas | `KPI_MSSQL_BLOCKED_SESSIONS_AGG_VIEW` |
| Long Running Locks | Locks de longa duração | `KPI_MSSQL_LONG_LOCKS_AGG_VIEW` |
| Backup Status | Status de backups (Full, Diff, Log) | `KPI_MSSQL_BACKUPS_AGG_VIEW` |
| Services Status | Serviços SQL parados | `KPI_MSSQL_SERVICE_STATUS_AGG_VIEW` |
| Active Processes | Processos ativos por instância | `KPI_MSSQL_PROCESSES_AGG_VIEW` |

#### Overview Dashboard
Visão agregada por ambiente (PRD, HML, DEV, etc.).

| Funcionalidade | Descrição | View Consultada |
|----------------|-----------|-----------------|
| Summary por Ambiente | Contadores agregados por ambiente | `V_OVERVIEW_DASHBOARD_SUMMARY` |
| Lista de Instâncias | Todas as instâncias com health score | `KPI_MSSQL_INST_ENVS` |
| Problemas Ativos | Lista de problemas por severidade | Views `*_PROBLEM_VIEW` |
| Distribuição de Health | Gráfico de distribuição de saúde | Cálculo agregado |

### Casos de Uso
- Reuniões de status executivo
- NOC (Network Operations Center) - visão geral
- Dashboards em TV/Monitores
- Relatórios gerenciais

### Requisitos de Acesso ao Banco
```
Banco de Dados: WatcherDB_Intelligence
Permissões: SELECT em views KPI_MSSQL_*
Conexões Simultâneas: Até 10
```

---

## WatcherDB Standard

### Descrição
Edição completa para **equipes de operações**. Inclui todas as funcionalidades do WatcherDB One, mais ferramentas de diagnóstico detalhado para troubleshooting do dia-a-dia.

### Funcionalidades Adicionais

#### Monitoramento de Serviços SQL Server
Monitoramento em tempo real dos serviços críticos.

| Funcionalidade | Descrição | View/Tabela Consultada |
|----------------|-----------|------------------------|
| Status de Serviços | SQL Server, SQL Agent, SSIS, SSAS, SSRS | `KPI_MSSQL_SERVICE_STATUS_DET_VIEW` |
| Histórico de Paradas | Registro de eventos de parada/início | `KPI_MSSQL_SERVICE_STATUS_HIST` |
| Logs de Erro | Error logs do SQL Server | `KPI_MSSQL_ERRORLOG_STG` |

#### Métricas de Sistema Operacional
Diagnóstico de performance do Windows Server.

| Métrica | Descrição | View Consultada |
|---------|-----------|-----------------|
| Memória Atual | Available MB, Pages/sec, Page Reads/sec | `vw_OS_Memory_Current` |
| Tendência de Memória | Histórico de uso de memória (30 min) | `KPI_OS_MEMORY_HIST` |
| Diagnóstico de Memória | Classificação de alertas SCOM | `vw_OS_Memory_Alert_Diagnosis` |
| CPU Atual | Processor %, Queue Length | `vw_OS_CPU_Current` |
| Disco por Drive | Uso e latência por volume | `vw_OS_Disk_Current` |
| Latência de Disco | Read/Write latency em ms | `KPI_OS_DISK_PERF_STG` |
| Correlação SQL/OS | Memória SQL vs OS | `vw_OS_SQL_Memory_Correlation` |

**Thresholds de Alerta:**
| Métrica | OK | Info | Warning | Critical |
|---------|-----|------|---------|----------|
| Available Memory (MB) | >2048 | >1024 | >512 | <256 |
| Page Reads/sec | <20 | <50 | <100 | >200 |
| Disk Latency (ms) | <5 | <10 | <20 | >50 |
| CPU % | <70 | <80 | <85 | >95 |

#### Análise de Espaço (Filegroups)
Monitoramento detalhado de espaço em disco.

| Funcionalidade | Descrição | View Consultada |
|----------------|-----------|-----------------|
| Uso por Filegroup | Total, Used, Free MB por filegroup | `KPI_MSSQL_FG_USAGE_ACTIVE` |
| Histórico de Crescimento | Tendência de crescimento | `KPI_MSSQL_FG_USAGE_HIST` |
| Alertas de Espaço | Filegroups acima do threshold | `KPI_MSSQL_FG_USAGE_STG` |

### Casos de Uso
- Troubleshooting de performance
- Resposta a alertas SCOM
- Análise de incidentes
- Operações do dia-a-dia
- Capacity planning básico

### Requisitos de Acesso ao Banco
```
Banco de Dados: WatcherDB_Intelligence
Permissões: SELECT em views KPI_MSSQL_*, vw_OS_*, KPI_OS_*
Conexões Simultâneas: Até 20
```

---

## WatcherDB Enterprise

### Descrição
Edição avançada para **capacity planning e prevenção de incidentes**. Inclui todas as funcionalidades do WatcherDB Standard, mais análises preditivas e identificação de padrões.

### Funcionalidades Adicionais

#### Análises Preditivas
Previsão de problemas antes que ocorram.

| Funcionalidade | Descrição | Dados Utilizados |
|----------------|-----------|------------------|
| Forecast de Filegroups | Previsão de quando filegroup ficará cheio | `KPI_MSSQL_FG_USAGE_HIST` (60 dias) |
| Tendência de Disco | Projeção de esgotamento de disco | `KPI_OS_DISK_PERF_HIST` |
| Crescimento de Databases | Taxa de crescimento por database | `KPI_MSSQL_DB_SIZE_HIST` |
| Projeção de Backup | Estimativa de tamanho de backups | `KPI_MSSQL_BACKUPS_HIST` |

**Exemplo de Forecast:**
```
Filegroup: FG_DATA_01
Tamanho Atual: 850 GB (85% usado)
Taxa de Crescimento: 2.5 GB/dia
Previsão de Esgotamento: 45 dias
Recomendação: Expandir em 30 dias
```

#### Análise de Padrões
Identificação automática de comportamentos anômalos.

| Funcionalidade | Descrição | Algoritmo |
|----------------|-----------|-----------|
| Padrões de Backup | Identifica backups fora do padrão | Análise estatística |
| Anomalias de Performance | Detecta desvios de baseline | Desvio padrão móvel |
| Padrões de Bloqueio | Identifica bloqueios recorrentes | Correlação temporal |
| Sazonalidade | Identifica picos por hora/dia/semana | Decomposição sazonal |

### Relatórios Disponíveis
- Relatório de Capacity Planning (mensal)
- Forecast de Crescimento (semanal)
- Análise de Tendências (diário)
- Alertas Preditivos (tempo real)

### Casos de Uso
- Capacity planning estratégico
- Prevenção proativa de incidentes
- Planejamento de expansão de storage
- Otimização de janelas de manutenção
- Reuniões de planejamento de infraestrutura

### Requisitos de Acesso ao Banco
```
Banco de Dados: WatcherDB_Intelligence
Permissões: SELECT em todas as views e tabelas históricas (*_HIST)
Conexões Simultâneas: Até 30
Retenção de Dados: Mínimo 90 dias para análises preditivas
```

---

## WatcherDB Professional

### Descrição
Edição completa para **DBAs Seniores e Administradores**. Inclui todas as funcionalidades do WatcherDB Enterprise, mais capacidade de execução de comandos administrativos diretamente pela interface.

### Funcionalidades Adicionais

#### Comandos de Administração
Execução segura de comandos DDL/DCL nos servidores monitorados.

| Categoria | Comandos Suportados | Nível de Risco |
|-----------|---------------------|----------------|
| **Gestão de Espaço** | DBCC SHRINKFILE, ALTER DATABASE ... ADD FILE | Médio |
| **Índices** | CREATE INDEX, DROP INDEX, ALTER INDEX REBUILD | Médio |
| **Estatísticas** | UPDATE STATISTICS, CREATE STATISTICS | Baixo |
| **Permissões** | GRANT, REVOKE, DENY | Alto |
| **Usuários** | CREATE LOGIN, ALTER LOGIN, DROP LOGIN | Alto |
| **Manutenção** | DBCC CHECKDB, DBCC CHECKTABLE | Baixo |
| **Jobs** | sp_start_job, sp_stop_job | Médio |

**Importante:** Comandos que afetam dados de negócio (INSERT, UPDATE, DELETE, TRUNCATE em tabelas de aplicação) **NÃO** são permitidos.

#### Controles de Segurança
| Controle | Descrição |
|----------|-----------|
| Aprovação em 4 olhos | Comandos de alto risco requerem aprovação |
| Audit Trail | Todos os comandos são registrados |
| Janela de Manutenção | Alguns comandos só executam em horários definidos |
| Rollback Automático | Scripts de reversão quando possível |
| Dry-Run | Simulação antes da execução |

#### Automações Disponíveis
| Automação | Descrição | Trigger |
|-----------|-----------|---------|
| Auto-Expand Filegroup | Expande filegroup automaticamente | >95% uso |
| Rebuild de Índices | Rebuild automático de índices fragmentados | >30% fragmentação |
| Update Statistics | Atualização automática de estatísticas | Schedule diário |
| Limpeza de Logs | Backup e truncate de transaction logs | >80% uso |

### Casos de Uso
- Administração centralizada de múltiplos servidores
- Resposta rápida a incidentes críticos
- Manutenção preventiva automatizada
- Gestão de permissões centralizada
- Operações de emergência

### Requisitos de Acesso ao Banco
```
Banco de Dados: WatcherDB_Intelligence + Servidores Monitorados
Permissões WatcherDB: SELECT, INSERT, UPDATE em tabelas de controle
Permissões Servidores: db_owner ou sysadmin (conforme operação)
Conexões Simultâneas: Até 50
Autenticação: Windows Authentication (recomendado) ou SQL Auth com MFA
```

---

## Matriz de Funcionalidades Detalhada

### Monitoramento

| Funcionalidade | One | Standard | Enterprise | Professional |
|----------------|:---:|:--------:|:----------:|:------------:|
| KPIs | ✅ | ✅ | ✅ | ✅ |
| Overview por Ambiente | ✅ | ✅ | ✅ | ✅ |
| Alertas em Tempo Real | ✅ | ✅ | ✅ | ✅ |
| Drill-down por Instância | ✅ | ✅ | ✅ | ✅ |
| Status de Serviços | - | ✅ | ✅ | ✅ |
| Métricas de OS | - | ✅ | ✅ | ✅ |
| Análise de Filegroups | - | ✅ | ✅ | ✅ |
| Correlação SQL/OS | - | ✅ | ✅ | ✅ |

### Análises

| Funcionalidade | One | Standard | Enterprise | Professional |
|----------------|:---:|:--------:|:----------:|:------------:|
| Histórico de KPIs | 7 dias | 30 dias | 90 dias | 365 dias |
| Tendências | - | Básico | Avançado | Avançado |
| Forecast | - | - | ✅ | ✅ |
| Detecção de Anomalias | - | - | ✅ | ✅ |
| Análise de Padrões | - | - | ✅ | ✅ |
| Relatórios Preditivos | - | - | ✅ | ✅ |

### Administração

| Funcionalidade | One | Standard | Enterprise | Professional |
|----------------|:---:|:--------:|:----------:|:------------:|
| Visualização de Configurações | ✅ | ✅ | ✅ | ✅ |
| Comandos DDL | - | - | - | ✅ |
| Comandos DCL | - | - | - | ✅ |
| Automações | - | - | - | ✅ |
| Aprovação em 4 olhos | - | - | - | ✅ |
| Audit Trail Completo | Básico | Básico | Avançado | Completo |

---

## Arquitetura de Dados

### Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SERVIDORES SQL MONITORADOS                      │
│  (PRD, HML, DEV - Instâncias SQL Server com dados de negócio)       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ Coleta (SQL Agent Jobs)
┌─────────────────────────────────────────────────────────────────────┐
│                      WATCHERDB_INTELLIGENCE                          │
│                    (Banco de Metadados Centralizado)                 │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │  KPI_MSSQL_ │  │   KPI_OS_   │  │    vw_OS_   │  │  V_OVERVIEW │ │
│  │    Views    │  │   Tables    │  │    Views    │  │    Views    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │   ONE     │   │ STANDARD  │   │ENTERPRISE │
            │  2 views  │   │ +15 views │   │ +HIST     │
            └───────────┘   └───────────┘   └───────────┘
```

### Views por Edição

#### WatcherDB One (6 views principais)
```sql
-- KPIs
KPI_MSSQL_DB_AVAILABILITY_AGG_VIEW
KPI_MSSQL_INST_AVAILABILITY_AGG_VIEW
KPI_MSSQL_DISK_USAGE_AGG_VIEW
KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW
KPI_MSSQL_BACKUPS_AGG_VIEW
V_OVERVIEW_DASHBOARD_SUMMARY
```

#### WatcherDB Standard (+15 views)
```sql
-- Todas do One, mais:
KPI_MSSQL_SERVICE_STATUS_DET_VIEW
KPI_MSSQL_ERRORLOG_STG
vw_OS_Memory_Current
vw_OS_Memory_Alert_Diagnosis
vw_OS_CPU_Current
vw_OS_Disk_Current
vw_OS_SQL_Memory_Correlation
KPI_OS_MEMORY_HIST
KPI_OS_DISK_PERF_STG
KPI_MSSQL_FG_USAGE_ACTIVE
KPI_MSSQL_FG_USAGE_STG
-- ... e outras views detalhadas
```

#### WatcherDB Enterprise (+tabelas históricas)
```sql
-- Todas do Standard, mais:
KPI_MSSQL_FG_USAGE_HIST
KPI_MSSQL_DB_SIZE_HIST
KPI_MSSQL_BACKUPS_HIST
KPI_OS_MEMORY_HIST (90+ dias)
KPI_OS_DISK_PERF_HIST
-- Procedures de análise preditiva
```

#### WatcherDB Professional (+permissões de escrita)
```sql
-- Todas do Enterprise, mais:
-- Permissões de execução em servidores monitorados
-- Tabelas de controle de comandos
-- Audit trail tables
```

---

## Requisitos Técnicos

| Requisito | One | Standard | Enterprise | Professional |
|-----------|-----|----------|------------|--------------|
| SQL Server (WatcherDB) | 2016+ | 2016+ | 2016+ | 2016+ |
| Espaço em Disco | 10 GB | 50 GB | 200 GB | 500 GB |
| RAM (API Server) | 4 GB | 8 GB | 16 GB | 32 GB |
| CPU (API Server) | 2 cores | 4 cores | 8 cores | 16 cores |
| Retenção de Dados | 7 dias | 30 dias | 90 dias | 365 dias |
| Usuários Simultâneos | 10 | 25 | 50 | 100 |

---

## Licenciamento

| Edição | Modelo | Inclui |
|--------|--------|--------|
| **One** | Por instância monitorada | Dashboard + Overview |
| **Standard** | Por instância monitorada | One + Diagnóstico |
| **Enterprise** | Por instância monitorada | Standard + Analytics |
| **Professional** | Por instância monitorada + por DBA | Enterprise + Admin |

---

## Upgrade Path

```
One ──────► Standard ──────► Enterprise ──────► Professional
  │              │                │                   │
  │              │                │                   │
  ▼              ▼                ▼                   ▼
Visão        Operações       Prevenção         Administração
Geral        Diárias         Proativa          Centralizada
```

**Migração:** Todas as edições utilizam o mesmo banco de dados WatcherDB_Intelligence. O upgrade consiste em:
1. Atualização de licença
2. Habilitação de módulos adicionais
3. Ajuste de permissões (se necessário)
4. Sem migração de dados necessária

---

## Contato

Para mais informações sobre licenciamento e implementação:
- **Email:** suporte@watcherdb.com
- **Documentação:** https://docs.watcherdb.com
- **Suporte:** https://support.watcherdb.com

---

*Documento atualizado em: Janeiro 2026*
*Versão do Documento: 1.0*
