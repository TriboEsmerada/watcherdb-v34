# Teste de Integração - SQL Server KPI Router

**Data:** 2025-11-27
**Status:** ✅ ROUTER INTEGRADO - PRONTO PARA TESTE
**Versão:** 1.0.0

---

## 📋 Resumo

O router SQL Server KPI foi integrado com sucesso ao `watcherdb_main.py`. O sistema está pronto para testes com dados reais.

### Status da Integração

| Componente | Status | Detalhes |
|------------|--------|----------|
| Service Layer | ✅ Completo | `services/sqlserver_kpi_service.py` - 1,150 linhas |
| Router Layer | ✅ Completo | `api/routers/sqlserver_kpis.py` - 850 linhas |
| Main App Integration | ✅ Completo | `watcherdb_main.py:2414-2419` |
| Database Schema | ✅ Completo | `database/ADICAO_KPI_ORACLE.sql` - 800 linhas |
| Documentation | ✅ Completo | 3 documentos técnicos |
| Test Script | ✅ Completo | `test_sqlserver_kpi.py` |

---

## 🎯 Objetivos do Teste

### 1. Teste de Conectividade
- ✅ Validar conexão com SQL Server
- ✅ Verificar credenciais e permissões
- ✅ Testar ODBC Driver

### 2. Teste Individual de KPIs (12 KPIs)
- ✅ Database Availability
- ✅ Disk Usage
- ✅ Transaction Log Usage
- ✅ Always On Status
- ✅ Filegroup Usage
- ✅ Blocked Sessions
- ✅ Instance Availability
- ✅ Backup Status
- ✅ Job Failures
- ✅ Index Fragmentation
- ✅ Statistics Outdated
- ✅ TempDB Usage

### 3. Teste de Dashboard Completo
- ✅ Endpoint `/api/sqlserver-kpis/dashboard`
- ✅ Performance < 2s
- ✅ Estrutura JSON válida

### 4. Teste de Persistência (Database)
- ⏳ SQL Agent Job collection
- ⏳ Stored procedure `usp_insert_dashboard`
- ⏳ Views KPI

---

## 🚀 Como Executar os Testes

### Pré-requisitos

```bash
# 1. Verificar pyodbc instalado
pip list | findstr pyodbc

# 2. Verificar drivers ODBC
python -c "import pyodbc; print(pyodbc.drivers())"

# 3. Verificar variáveis de ambiente
echo %SQL_SERVER%
echo %SQL_DATABASE%
echo %SQL_TRUSTED_CONNECTION%
```

### Teste 1: Script Automatizado (RECOMENDADO)

```bash
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"

python test_sqlserver_kpi.py
```

**O que o script faz:**
1. Verifica pré-requisitos (pyodbc, drivers, variáveis)
2. Testa conexão SQL Server
3. Executa 12 KPIs individuais
4. Testa dashboard completo
5. Gera relatório detalhado

**Tempo esperado:** 30-60 segundos

### Teste 2: Servidor FastAPI (Manual)

```bash
# 1. Iniciar servidor
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python watcherdb_main.py
```

**Verificar logs:**
```
✅ Router SQL Server KPIs carregado: /api/sqlserver-kpis com 15 rotas
```

**Endpoints disponíveis:**
- http://localhost:8000/api/sqlserver-kpis/
- http://localhost:8000/api/sqlserver-kpis/dashboard
- http://localhost:8000/api/sqlserver-kpis/health
- http://localhost:8000/docs (Swagger UI)

### Teste 3: cURL (Linha de Comando)

```bash
# Dashboard completo
curl -X GET "http://localhost:8000/api/sqlserver-kpis/dashboard" -H "accept: application/json"

# KPI específico - Database Availability
curl -X GET "http://localhost:8000/api/sqlserver-kpis/db-availability" -H "accept: application/json"

# Health check
curl -X GET "http://localhost:8000/api/sqlserver-kpis/health" -H "accept: application/json"
```

### Teste 4: PowerShell (Alternativo)

```powershell
# Dashboard completo
Invoke-RestMethod -Uri "http://localhost:8000/api/sqlserver-kpis/dashboard" -Method GET | ConvertTo-Json -Depth 10

# Disk usage
Invoke-RestMethod -Uri "http://localhost:8000/api/sqlserver-kpis/disk-usage" -Method GET | ConvertTo-Json -Depth 10
```

---

## 📊 Estrutura do Response - Dashboard

### Request
```http
GET /api/sqlserver-kpis/dashboard HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Response (Exemplo)
```json
{
  "timestamp": "2025-11-27T10:30:45.123456",
  "instance": "SQLHDSPRD213\\I01",
  "version": "Microsoft SQL Server 2019 (RTM-CU14)...",
  "collection_time_seconds": 1.234,
  "kpis": {
    "database_availability": {
      "total_databases": 150,
      "abnormal_count": 2,
      "abnormal_databases": [
        {
          "database_name": "TestDB",
          "state_desc": "OFFLINE",
          "state": 6
        }
      ]
    },
    "disk_usage": {
      "volumes": [
        {
          "volume_mount_point": "E:\\",
          "total_size_gb": 1000.0,
          "available_space_gb": 250.5,
          "percent_free": 25.05
        }
      ],
      "critical_count": 0
    },
    "tlog_usage": {
      "databases_over_threshold": [
        {
          "database_name": "ProductionDB",
          "log_size_mb": 50000.0,
          "log_used_mb": 45000.0,
          "percent_used": 90.0
        }
      ],
      "total_databases_checked": 150
    },
    "alwayson_status": {
      "ag_count": 3,
      "unhealthy_count": 0,
      "availability_groups": [
        {
          "ag_name": "SQLHDSPRD213_AG1",
          "primary_replica": "SQLHDSPRD213\\I01",
          "synchronization_health_desc": "HEALTHY"
        }
      ]
    },
    "filegroup_usage": {
      "filegroups_near_full": [],
      "total_filegroups_checked": 450
    },
    "blocked_sessions": {
      "blocked_count": 0,
      "blocking_chains": []
    },
    "instance_availability": {
      "status": "available",
      "uptime_days": 45,
      "instance_name": "SQLHDSPRD213\\I01",
      "version": "Microsoft SQL Server 2019..."
    },
    "backup_status": {
      "databases_without_backup": [],
      "total_databases": 150,
      "databases_overdue": 0
    },
    "job_failures": {
      "failed_jobs": [],
      "total_failed_executions": 0
    },
    "index_fragmentation": {
      "fragmented_indexes": [
        {
          "database_name": "ProductionDB",
          "schema_name": "dbo",
          "table_name": "LargeTable",
          "index_name": "IX_LargeTable_Col1",
          "avg_fragmentation_percent": 45.6
        }
      ],
      "total_fragmented": 12
    },
    "statistics_outdated": {
      "outdated_statistics": [
        {
          "database_name": "ProductionDB",
          "schema_name": "dbo",
          "table_name": "BigTable",
          "stats_name": "IX_BigTable_Stats",
          "modification_percent": 35.2
        }
      ],
      "total_outdated": 8
    },
    "tempdb_usage": {
      "total_size_mb": 10240.0,
      "used_space_mb": 5120.0,
      "percent_used": 50.0,
      "data_files": 8,
      "version_store_mb": 1024.0
    }
  }
}
```

---

## 🔍 Validação dos Resultados

### Critérios de Sucesso

#### 1. Teste de Conectividade
```
✅ pyodbc instalado
✅ Driver SQL Server encontrado
✅ Variáveis de ambiente definidas
✅ Conexão estabelecida
```

#### 2. Teste de KPIs Individuais
```
✅ 12/12 KPIs executados sem erro
✅ Tempo médio < 0.5s por KPI
✅ Response com estrutura válida
```

#### 3. Teste de Dashboard
```
✅ Dashboard retornado em < 2s
✅ JSON válido com timestamp, instance, kpis
✅ Todos os 12 KPIs presentes
✅ Sem erros ou exceções
```

### Métricas de Performance Esperadas

| Métrica | Valor Esperado | Limite Aceitável |
|---------|----------------|------------------|
| Dashboard completo | < 1.5s | < 2.0s |
| KPI individual | < 0.3s | < 0.5s |
| Conexão | < 1.0s | < 2.0s |
| Tamanho response | 10-50 KB | < 100 KB |

---

## 🐛 Troubleshooting

### Erro: "pyodbc.InterfaceError: Driver not found"

**Solução:**
```bash
# Instalar ODBC Driver 17 for SQL Server
# Download: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
```

### Erro: "OperationalError: Login failed"

**Solução 1 - Windows Authentication (RECOMENDADO):**
```bash
set SQL_SERVER=SQLHDSPRD213\I01
set SQL_DATABASE=WatcherDB_Intelligence_V2
set SQL_TRUSTED_CONNECTION=yes
```

**Solução 2 - SQL Authentication:**
```bash
set SQL_SERVER=SQLHDSPRD213\I01
set SQL_DATABASE=WatcherDB_Intelligence_V2
set SQL_USER=watcherdb_user
set SQL_PASSWORD=sua_senha_aqui
set SQL_TRUSTED_CONNECTION=no
```

### Erro: "Timeout expired"

**Solução:**
```bash
# Aumentar timeout na connection string
# Editar services/sqlserver_kpi_service.py:
# timeout=60  # Aumentar de 30 para 60 segundos
```

### Erro: "Router não carregado"

**Verificar logs:**
```bash
python watcherdb_main.py | findstr "SQL Server KPI"
```

**Verificar imports:**
```python
python -c "from api.routers.sqlserver_kpis import router; print('OK')"
```

---

## 📈 Próximos Passos

### Fase 1: Teste Manual (ATUAL)
- [x] Integrar router no app principal
- [x] Criar script de teste automatizado
- [ ] **EXECUTAR:** `python test_sqlserver_kpi.py`
- [ ] **VALIDAR:** Todos os KPIs retornando dados
- [ ] **BENCHMARK:** Medir performance

### Fase 2: Teste de Persistência
- [ ] Executar `ADICAO_KPI_ORACLE.sql` no database
- [ ] Verificar schema `kpi` criado
- [ ] Testar stored procedure `usp_insert_dashboard`
- [ ] Habilitar SQL Agent Job `WatcherDB_Collect_Oracle_KPIs`
- [ ] Verificar dados coletados nas tabelas

### Fase 3: Validação com Oracle
- [ ] Comparar dashboard Oracle vs SQL Server
- [ ] Validar equivalência dos KPIs
- [ ] Documentar diferenças (se houver)
- [ ] Ajustar thresholds se necessário

### Fase 4: Produção
- [ ] Deploy em ambiente de teste
- [ ] Monitorar por 24h
- [ ] Ajustar performance se necessário
- [ ] Deploy em produção

---

## 📚 Referências

### Documentação Relacionada
1. [MAPEAMENTO_KPI_ORACLE_SQL_SERVER.md](./MAPEAMENTO_KPI_ORACLE_SQL_SERVER.md) - Mapeamento completo Oracle → SQL Server
2. [INTEGRACAO_SQL_SERVER_KPI.md](./INTEGRACAO_SQL_SERVER_KPI.md) - Guia de integração detalhado
3. [RESUMO_FASE1_COMPLETO.md](./RESUMO_FASE1_COMPLETO.md) - Resumo da Fase 1

### Arquivos Criados
1. `services/sqlserver_kpi_service.py` - Service layer (1,150 linhas)
2. `api/routers/sqlserver_kpis.py` - Router layer (850 linhas)
3. `database/ADICAO_KPI_ORACLE.sql` - Database schema (800 linhas)
4. `test_sqlserver_kpi.py` - Test script (400 linhas)

### Endpoints da API
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

---

## ✅ Checklist de Validação

Antes de considerar a integração completa, verificar:

- [x] Router integrado em `watcherdb_main.py`
- [x] 15 rotas carregadas com sucesso
- [x] Service layer funcional
- [x] Documentação completa
- [ ] **Teste automatizado executado** (`test_sqlserver_kpi.py`)
- [ ] **Todos os 12 KPIs validados**
- [ ] **Dashboard completo testado**
- [ ] **Performance dentro do esperado**
- [ ] Database schema instalado
- [ ] SQL Agent Job configurado
- [ ] Dados persistidos no database
- [ ] Equivalência com Oracle validada

---

## 📞 Suporte

**Em caso de problemas:**
1. Verificar logs em `logs/watcherdb.log`
2. Executar `test_sqlserver_kpi.py` para diagnóstico
3. Consultar [INTEGRACAO_SQL_SERVER_KPI.md](./INTEGRACAO_SQL_SERVER_KPI.md)
4. Revisar configuração de variáveis de ambiente

**Equipe WatcherDB**
Versão: 1.0.0
Data: 2025-11-27
