# CHANGELOG - Sincronizacao entre Projetos WatcherDB
**Data:** 2024-12-23
**Projetos afetados:** WatcherDB DEV, Enterprise, Professional

---

## 1. CORRECAO DO TOOLTIP TRAVADO NO DASHBOARD

### Arquivo: templates/watcherdb_portal.html

### Problema:
O tooltip Disponibilidade de Banco de Dados ficava travado na tela ao passar o mouse sobre os cards de KPI.

### Solucao:
Modificar a funcao hideTooltip para mover o tooltip para fora da area visivel alem de esconde-lo.

### Codigo a alterar:
function hideTooltip() {
    const tooltip = document.getElementById('kpi-tooltip');
    if (tooltip) {
        tooltip.style.display = 'none';
        tooltip.style.opacity = '0';
        tooltip.style.left = '-9999px';
        tooltip.style.top = '-9999px';
    }
}

---

## 2. CORRECAO DE DUPLICATAS NA TABELA DE INSTANCIAS

### Problema:
Dashboard mostrava 81 Total Instances mas 84 Available (matematicamente impossivel).

### Causa:
3 instancias duplicadas nas tabelas BLUE_PRD e GREEN_PRD:
- SQLHDSPRD001_I0001
- SQLHDSPRD003_I0002
- SQLHDSPRD006_I0003

### SQL para verificar duplicatas:
SELECT Instance, COUNT(*) AS Qtd
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_STG
GROUP BY Instance
HAVING COUNT(*) > 1;

---

## 3. CORRECAO DO MODULO SPACE_ANALYSIS PARA AG SECONDARY

### Arquivo: modules/monitoring/space_analysis.py

### Problema:
O modulo falhava ao tentar acessar sys.filegroups em databases secundarios de Always On AG.

### Solucao:
1. Adicionar metodo check_database_state() para verificar se e secundario de AG
2. Adicionar queries alternativas que usam apenas sys.master_files
3. Adicionar fallback automatico quando a query principal falha

---

## 4. MONITORAMENTO DE ERROS SERVICE BROKER / DATABASE MIRRORING

### Arquivo: modules/monitoring/logs_collector.py

### Problema:
O modulo nao capturava erros do Service Broker/Database Mirroring como:
- Event ID: 9642
- Error: 8474

### Solucao:
Adicionar nova lista SERVICE_BROKER_EVENT_IDS com os Event IDs:
9642, 8474, 9724, 9736, 28054, 28047, 28051, 9649, 9655, 9666,
1440, 1441, 1454, 1456, 1457, 1459, 1418, 1419, 9691, 9693

Adicionar categoria service_broker ao category_map.

---

## 5. OVERVIEW DASHBOARD OTIMIZADO

### Arquivo: api/routers/overview_dashboard.py (NOVO)

### Problema:
O modulo Overview demorava muito para carregar porque fazia multiplas queries em tempo real.

### Solucao:
Criar novos endpoints que usam dados pre-calculados do banco:
- GET /api/v1/overview/summary - Sumario agregado por ambiente
- GET /api/v1/overview/instances - Lista de instancias com health scores
- GET /api/v1/overview/problems - Top instancias com problemas
- POST /api/v1/overview/refresh - Forca atualizacao dos dados
- GET /api/v1/overview/environments - Lista de ambientes disponiveis
- GET /api/v1/overview/health-distribution - Distribuicao para graficos

### Views de banco utilizadas:
- V_OVERVIEW_DASHBOARD_SUMMARY
- V_OVERVIEW_INSTANCE_HEALTH
- V_OVERVIEW_TOP_PROBLEMS

### Procedure de refresh:
- usp_refresh_overview_all

---

## RESUMO DAS MUDANCAS

| Mudanca | Arquivo | Prioridade |
|---------|---------|------------|
| Tooltip travado | templates/watcherdb_portal.html | Alta |
| Duplicatas instancias | SQL nas tabelas BLUE/GREEN | Alta |
| AG Secondary space | modules/monitoring/space_analysis.py | Alta |
| Service Broker logs | modules/monitoring/logs_collector.py | Media |
| Overview Dashboard | api/routers/overview_dashboard.py | Alta |

---
Autor: Claude Code / WatcherDB Intelligence V2
