# WatcherDB

> Comprehensive SQL Server monitoring and diagnostics platform with real-time analytics and predictive capabilities

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## Overview

**WatcherDB** is a production-grade SQL Server monitoring platform designed to provide comprehensive insights into database performance, health, and predictive analytics across multiple server instances. Built with FastAPI and modern async architecture, it monitors **84+ SQL Server instances** in real-time with advanced features including:

- **Real-time Performance Monitoring**: CPU, Memory, Disk Space, Query Performance
- **Always On Availability Groups**: Replica health, synchronization status, failover detection
- **Predictive Analytics**: Space forecasting, pattern detection, anomaly identification
- **Backup Analysis**: Pattern recognition, failure detection, RPO tracking
- **Security Auditing**: TDE encryption status, certificate tracking
- **Custom Query Engine**: User-defined SQL queries with result caching
- **WebSocket Support**: Real-time dashboard updates
- **Advanced Alerting**: Email, Teams, Slack, Webhook notifications

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---

## Features

### Core Monitoring Capabilities

#### 🔍 **Performance Diagnostics**
- **Space Analysis**: Filegroup usage, disk space forecasting, growth predictions
- **Memory Analysis**: Server memory utilization, buffer pool stats, AlwaysOn memory comparison
- **CPU Analysis**: SQL process utilization, CPU pressure detection
- **Query Performance**: Slow query identification, execution plan analysis
- **Wait Stats**: Top wait types, bottleneck identification
- **Index Health**: Fragmentation detection with rebuild recommendations

#### 🔄 **Always On Availability Groups**
- Monitor 38+ AG configurations across multiple servers
- Replica health tracking and database synchronization status
- Failover event detection (Extended Events + Error Log)
- Temporal pattern analysis (recurring failover times/days)
- Lease timeout and quorum issue detection

#### 💾 **Backup Monitoring**
- Backup status tracking (Full, Differential, Log)
- Pattern analysis (identifies unusual backup gaps)
- Advanced temporal pattern detection
- Backup failure alerts
- Recovery Point Objective (RPO) tracking

#### 🔐 **Security Analysis**
- TDE encryption status monitoring
- Certificate tracking (issuer, expiry dates)
- Key encryption type verification
- Security audit capabilities

#### 📊 **Predictive Analytics**
- Machine learning-based space forecasting
- Anomaly detection in resource usage
- Pattern recognition in backup schedules
- Trend analysis for capacity planning

#### ⚡ **Custom Query System**
- User-defined SQL queries via JSON configuration
- Dynamic query execution across any server
- Result caching with configurable TTL
- Support for parameterized queries

---

## Architecture

```
WatcherDB/
├── watcherdb/
│   ├── core/                     # Core infrastructure
│   │   ├── cache.py             # Redis-like cache with TTL & persistence
│   │   ├── connection_pool.py   # SQL Server connection pooling
│   │   └── executor.py          # SQL query executor
│   ├── models/                   # Data models
│   │   ├── server.py            # Server configurations
│   │   ├── monitoring.py        # Monitoring metrics
│   │   └── alerts.py            # Alert definitions
│   ├── services/                 # Business logic
│   │   ├── monitoring_service.py
│   │   ├── backup_service.py
│   │   ├── alwayson_service.py
│   │   └── alerting_service.py
│   ├── api/                      # FastAPI routers
│   │   ├── routers/
│   │   │   ├── alwayson.py
│   │   │   ├── diagnostics.py
│   │   │   ├── queries.py
│   │   │   └── auth.py
│   │   └── dependencies.py
│   ├── modules/                  # Monitoring modules
│   │   ├── analytics/
│   │   │   └── predictive_analysis.py
│   │   └── monitoring/
│   │       ├── space_analysis.py
│   │       ├── memory_analysis.py
│   │       ├── cpu_analysis.py
│   │       └── backup_analysis.py
│   └── utils/                    # Utilities
│       ├── logging.py
│       └── helpers.py
├── config/                       # Configuration files
│   ├── config.yaml              # Main configuration
│   ├── sql_servers.json         # Server inventory (84 servers)
│   ├── alwayson_inventory.json  # Always On AG configs
│   ├── custom_queries.json      # User-defined queries
│   └── alerts.json              # Alert rules
├── templates/                    # HTML dashboards
│   └── watcherdb_portal.html
├── static/                       # CSS/JS/assets
│   ├── css/
│   ├── js/
│   └── favicon.svg
├── tests/                        # Test suite
│   ├── unit/
│   ├── integration/
│   └── conftest.py
└── scripts/                      # Utility scripts
    └── initialize_configs.py
```

### Technology Stack

- **Backend**: FastAPI (async/await architecture)
- **Database Monitoring**: pyodbc (ODBC Driver 17 for SQL Server)
- **Local Storage**: SQLite for caching and persistence
- **Authentication**: JWT with OAuth2 password bearer
- **Real-time**: WebSockets for live dashboard updates
- **Analytics**: scikit-learn, pandas, numpy
- **Visualization**: Plotly for interactive charts

---

## Installation

### Prerequisites

- **Python**: 3.11 or higher
- **ODBC Driver**: ODBC Driver 17 for SQL Server
- **SQL Server**: Access to SQL Server instances (Windows Authentication)

### Install ODBC Driver (Windows)

Download and install from: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

### Install WatcherDB

```bash
# Clone repository
git clone https://github.com/watcherdb/watcherdb.git
cd watcherdb

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install base dependencies
pip install -r requirements.txt

# Optional: Install development dependencies
pip install -r requirements-dev.txt

# Optional: Install alerting features
pip install -r requirements-alerting.txt

# Optional: Install advanced analytics
pip install -r requirements-analytics.txt

# Or install everything
pip install -e .[all]
```

---

## Quick Start

### 1. Configure Servers

Edit `config/sql_servers.json` to add your SQL Server instances:

```json
{
  "servers": [
    {
      "id": 1,
      "host": "SERVER01",
      "instance": "MSSQLSERVER",
      "port": 1433,
      "environment": "production",
      "priority": "critical",
      "description": "Production SQL Server"
    }
  ]
}
```

### 2. Configure Application

Edit `config/config.yaml`:

```yaml
database:
  cache_ttl: 60
  connection_timeout: 30

logging:
  level: "INFO"
  file: "logs/watcherdb.log"

alerts:
  enabled: true
  channels: ["email", "teams"]
```

### 3. Run the Application

```bash
# Development mode with auto-reload
python watcherdb_main.py

# Or using uvicorn directly
uvicorn watcherdb_main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Access Dashboards

- **Main Portal**: http://localhost:8000/watcherdb
- **API Documentation**: http://localhost:8000/docs
- **Monitoring Dashboard**: http://localhost:8000/monitoring

---

## Configuration

### Server Inventory

`config/sql_servers.json` - Define SQL Server instances to monitor

```json
{
  "metadata": {
    "source_file": "TAP_SQL_Server_Inventory.xlsx",
    "generated_at": "2025-01-14T10:00:00",
    "version": "1.0"
  },
  "servers": [
    {
      "id": 1,
      "host": "SERVER01",
      "instance": "MSSQLSERVER",
      "port": 1433,
      "environment": "production",
      "priority": "critical",
      "description": "Production database server"
    }
  ]
}
```

### Always On Availability Groups

`config/alwayson_inventory.json` - Configure Always On AG monitoring

```json
{
  "excel_config": {
    "file_path": "TAP_SQL_Server_Inventory.xlsx",
    "sheet_name": "Servers"
  },
  "servers": [
    {
      "server": "SERVER01",
      "instance": "MSSQLSERVER",
      "ag_name": "AG_Production",
      "listener": "AG_PROD_LISTENER"
    }
  ]
}
```

### Alert Configuration

`config/alerts.json` - Define alerting rules

```json
{
  "disk_space": {
    "critical": 10,
    "warning": 20,
    "forecast_days": 30,
    "channels": ["email", "teams"]
  },
  "backup_failure": {
    "max_age_hours": 24,
    "channels": ["email", "teams", "slack"]
  },
  "alwayson_failover": {
    "channels": ["teams", "webhook"]
  },
  "memory_pressure": {
    "critical_percent": 90,
    "warning_percent": 80,
    "channels": ["email"]
  }
}
```

### Custom Queries

`config/custom_queries.json` - Define reusable SQL queries

```json
{
  "queries": [
    {
      "id": "query_001",
      "name": "Top Resource Consuming Queries",
      "description": "Identifies queries consuming most CPU/Memory",
      "sql": "SELECT TOP 10 * FROM sys.dm_exec_query_stats ORDER BY total_worker_time DESC",
      "requires_database": false,
      "enabled": true
    }
  ]
}
```

---

## API Documentation

### Interactive API Docs

FastAPI provides automatic interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

#### Always On Availability Groups

```
GET /api/alwayson/overview              - All AGs overview
GET /api/alwayson/ag/{ag_name}          - AG-specific details
GET /api/alwayson/server/{server_name}  - Server AG status
GET /api/alwayson/events/{server_name}  - Failover events
```

#### Query Troubleshooting

```
GET /api/queries/blocking/{server_id}         - Blocking chains
GET /api/queries/slow-queries/{server_id}     - Performance bottlenecks
GET /api/queries/log-space/{server_id}        - Transaction log monitoring
GET /api/queries/sql-agent-jobs/{server_id}   - Job failures
GET /api/queries/index-fragmentation/{server_id} - Index health
```

#### Monitoring

```
GET /api/monitoring/space/{server_id}         - Space analysis
GET /api/monitoring/memory/{server_id}        - Memory diagnostics
GET /api/monitoring/cpu/{server_id}           - CPU analysis
GET /api/monitoring/backups/{server_id}       - Backup summary
GET /api/monitoring/security/{server_id}      - Security analysis
```

#### Health & Stats

```
GET /api/health                               - Basic health check
GET /api/health/summary                       - Aggregated health across all servers
GET /api/stats                                - WatcherDB usage statistics
```

---

## Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### Code Quality Tools

```bash
# Format code with Black
black watcherdb/

# Sort imports with isort
isort watcherdb/

# Lint with Ruff
ruff check watcherdb/

# Type check with mypy
mypy watcherdb/

# Run all checks (pre-commit)
pre-commit run --all-files
```

### Project Structure Guidelines

- **Keep main.py under 300 lines**: Extract logic to services and routers
- **Single Responsibility**: Each module should have one clear purpose
- **Type Hints**: Use type hints for all function signatures
- **Error Handling**: Always use try/except with proper logging
- **Documentation**: Document all public functions with docstrings

---

## Testing

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=watcherdb --cov-report=html

# Run specific test file
pytest tests/unit/test_cache.py

# Run with verbose output
pytest -v

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

### Test Structure

```
tests/
├── unit/
│   ├── test_cache.py              # Cache functionality
│   ├── test_connection_pool.py    # Connection pooling
│   ├── test_monitoring.py         # Monitoring logic
│   └── test_alerts.py             # Alert system
├── integration/
│   ├── test_api_endpoints.py      # API endpoint integration
│   ├── test_sql_queries.py        # SQL query execution
│   └── test_alerting.py           # End-to-end alerting
└── conftest.py                     # Shared fixtures
```

### Writing Tests

```python
# Example: tests/unit/test_cache.py
import pytest
from watcherdb.core.cache import RedisLikeCache

@pytest.fixture
def cache():
    return RedisLikeCache(persistence_file=":memory:")

def test_cache_set_get(cache):
    cache.set("key1", "value1", ttl=60)
    assert cache.get("key1") == "value1"

def test_cache_expiration(cache):
    cache.set("key2", "value2", ttl=1)
    time.sleep(2)
    assert cache.get("key2") is None
```

---

## Deployment

### Production Deployment

```bash
# Install production dependencies only
pip install -r requirements.txt

# Run with production server (Gunicorn)
gunicorn watcherdb_main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log
```

### Windows Service

Use NSSM (Non-Sucking Service Manager) to run as Windows service:

```bash
# Install NSSM
# Download from: https://nssm.cc/download

# Create service
nssm install WatcherDB "C:\path\to\venv\Scripts\python.exe" "C:\path\to\watcherdb_main.py"
nssm set WatcherDB AppDirectory "C:\path\to\watcherdb"
nssm start WatcherDB
```

### Environment Variables

```bash
# .env file
WATCHERDB_ENV=production
WATCHERDB_LOG_LEVEL=INFO
WATCHERDB_DB_PATH=data/watcherdb.db
WATCHERDB_CACHE_PATH=data/cache.db
WATCHERDB_SECRET_KEY=your-secret-key-here
```

---

## Performance Tuning

### Configuration Recommendations

**For 50-100 Servers:**
```yaml
database:
  connection_pool_size: 20
  cache_ttl: 60
  max_memory_mb: 200

workers: 4
```

**For 100-200 Servers:**
```yaml
database:
  connection_pool_size: 50
  cache_ttl: 120
  max_memory_mb: 500

workers: 8
```

### Caching Strategy

- **Space Analysis**: 300s TTL (5 minutes)
- **Memory Stats**: 60s TTL (1 minute)
- **Backup Status**: 3600s TTL (1 hour)
- **Custom Queries**: Configurable per query

---

## Troubleshooting

### Common Issues

**Issue: ODBC Driver Not Found**
```
Error: [Microsoft][ODBC Driver Manager] Data source name not found
```
Solution: Install ODBC Driver 17 for SQL Server

**Issue: Connection Timeout**
```
Error: [HYT00] [Microsoft][ODBC Driver 17 for SQL Server]Login timeout expired
```
Solution: Check firewall rules, increase timeout in config.yaml

**Issue: Memory Usage High**
```
Warning: Cache memory usage exceeds 90%
```
Solution: Reduce `max_memory_mb` in config or increase TTL values

### Logging

Check logs for detailed error information:
```bash
# View recent logs
tail -f logs/watcherdb.log

# Search for errors
grep ERROR logs/watcherdb.log

# View structured JSON logs
cat logs/watcherdb.json | jq '.level == "ERROR"'
```

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make changes and add tests**
4. **Run tests**: `pytest`
5. **Run code quality checks**: `pre-commit run --all-files`
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push to branch**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

### Code Style

- Follow PEP 8 guidelines
- Use Black for formatting (line length: 120)
- Use type hints for all functions
- Write docstrings for public functions
- Maintain test coverage above 70%

---

## Roadmap

### Version 1.1 (Q2 2025)
- [ ] Multi-tenant support
- [ ] Advanced machine learning for anomaly detection
- [ ] Automated remediation actions
- [ ] Mobile-responsive dashboard redesign

### Version 2.0 (Q3 2025)
- [ ] PostgreSQL monitoring support
- [ ] Oracle database integration
- [ ] Kubernetes deployment support
- [ ] Enhanced capacity planning tools

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **FastAPI**: Modern web framework for building APIs
- **WatcherDB Team**: Core development and production deployment
- **Community Contributors**: Bug reports and feature suggestions

---

## Documentation

Para documentação técnica detalhada sobre as implementações e correções, consulte:

📁 **[documentacao/](documentacao/)** - Documentação técnica completa

**Documentos principais:**
- **[ANALISE_CORRECOES_IMPLEMENTADAS.md](documentacao/ANALISE_CORRECOES_IMPLEMENTADAS.md)** - Análise completa de todas as correções (v1.4.0 → v1.4.4)
- **[CONNECTION_OPTIMIZATION_REPORT.md](documentacao/CONNECTION_OPTIMIZATION_REPORT.md)** - Otimização de conexões (84 → 0)
- **[TIMEOUT_FIX_FINAL.md](documentacao/TIMEOUT_FIX_FINAL.md)** - Correção de timeouts

**Versão atual:** v1.4.7 (2025-11-15)

**Recente - Refinamento de Event IDs (v1.4.7):**
- **[LOG_EVENT_IDS_REFINEMENT_v1.4.7.md](documentacao/LOG_EVENT_IDS_REFINEMENT_v1.4.7.md)** - Refinamento de Event IDs focando em SQL Server, Always On e Backups
  - Event IDs expandidos: Shutdown (4→7), Disk (6→15), SQL Critical (11→22), Always On (11→17)
  - Nova categoria BACKUP (6 IDs para VSS e backup failures)
  - Categorias padrão otimizadas: 6→5 (100% relevância, 67 Event IDs totais)

**Otimizações de Performance (v1.4.6):**
- **[LOG_PERFORMANCE_OPTIMIZATION_v1.4.6.md](documentacao/LOG_PERFORMANCE_OPTIMIZATION_v1.4.6.md)** - Otimização de análise de logs (6min → 2min primeira carga, <1s cache)
- **[LOG_ANALYSIS_PERFORMANCE_ISSUE.md](documentacao/LOG_ANALYSIS_PERFORMANCE_ISSUE.md)** - Análise do problema original

**Validação de Queries (v1.4.5):**
- **[QUERY_VALIDATION_REPORT.md](documentacao/QUERY_VALIDATION_REPORT.md)** - Relatório completo de validação das 22 queries SQL
- **[QUERY_FIXES_v1.4.5.md](documentacao/QUERY_FIXES_v1.4.5.md)** - Correções implementadas (collation conflict + performance)

---

## Support

- **Documentation**: [documentacao/](documentacao/)
- **Issues**: https://github.com/watcherdb/watcherdb/issues
- **Email**: support@watcherdb.io

---

**Built with ❤️ by the WatcherDB Team**
