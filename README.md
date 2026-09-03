# WatcherDB DEV

Sistema de monitoramento e diagnostico avancado para SQL Server.

## Versao: 2.2 (Marco 2026)

### Ultimas Actualizacoes (05/03/2026)

**Correccao AlwaysOn Connectivity (SQLHDSPRD212\I01):**
- Corrigida cadeia completa de autenticacao (Fernet encryption, load_dotenv, porta dinamica)
- Adicionado ThreadPoolExecutor com timeout em todos os endpoints AlwaysOn
- Reduzidos command_timeout de 30s para 10s (eventos) e 20s para 5s (last_failover)
- Modulo AlwaysOn agora carrega em <2s (Overview) com fallback gracioso para eventos

**Novo Router: Network Diagnostics:**
- Diagnostico de rede em 7 camadas (Basic Network, DNS, SQL Browser, TCP, ODBC, Query, Latency)
- Painel de ajuda interactivo com scroll automatico ao clicar em `?`
- Suporte a portas dinamicas de instancias nomeadas

**Seguranca e Encriptacao:**
- Passwords em `servers.json` encriptadas com Fernet (prefixo `encrypted:`)
- Chave de encriptacao via `WATCHERDB_ENCRYPTION_KEY` no `.env`
- `load_dotenv()` adicionado ao inicio de `watcherdb_main.py`

---

## Indice

- [Instalacao](#instalacao)
- [Arquitectura](#arquitectura)
- [Configuracao](#configuracao)
- [Routers Disponiveis](#routers-disponiveis)
- [Modulos de Monitoramento](#modulos-de-monitoramento)
- [Encriptacao de Passwords](#encriptacao-de-passwords)
- [Diagnostico de Rede](#diagnostico-de-rede)
- [AlwaysOn Availability Groups](#alwayson-availability-groups)
- [API Documentation](#api-documentation)
- [Changelog](#changelog)

---

## Arquitectura

```
WATCHERDB_DEV/
├── watcherdb_main.py              # Entry point (FastAPI app)
├── .env                           # Variaveis de ambiente (NUNCA commitar)
├── config/
│   ├── servers.json               # Servidores monitorizados (passwords encriptadas)
│   └── config.yaml                # Configuracao centralizada
├── api/
│   └── routers/                   # 17 routers API
│       ├── alwayson.py            # AlwaysOn Availability Groups
│       ├── network_diagnostics.py # Diagnostico de rede (7 camadas)
│       ├── cluster.py             # Windows Failover Cluster
│       ├── database_discovery.py  # Descoberta de bases de dados
│       ├── diagnostics_overview.py# Overview de diagnosticos
│       ├── disk_unallocated.py    # Espaco nao alocado em disco
│       ├── intelligence_kpis.py   # KPIs Intelligence DB
│       ├── jobs.py                # SQL Agent Jobs
│       ├── kpis_metadata.py       # Metadata de KPIs
│       ├── oracle_kpis.py         # KPIs Oracle
│       ├── os_performance.py      # Performance do SO
│       ├── overview_dashboard.py  # Dashboard principal
│       ├── service_status.py      # Status de servicos
│       ├── sql_queries.py         # Queries customizadas
│       ├── sqlserver_kpis.py      # KPIs SQL Server
│       └── users.py               # Gestao de utilizadores
├── modules/
│   └── monitoring/                # Engines de analise
│       ├── watcherdb_alwayson_check.py  # AlwaysOn engine
│       ├── backup_analysis.py           # Analise de backups
│       ├── cpu_analysis.py              # Analise de CPU
│       ├── memory_analysis.py           # Analise de memoria
│       ├── security_analysis.py         # Analise de seguranca
│       ├── space_analysis.py            # Analise de espaco
│       ├── cluster_analysis.py          # Analise de cluster
│       ├── service_monitor.py           # Monitor de servicos
│       └── monitoring.py                # Connection pool e utils
├── templates/
│   └── watcherdb_portal.html      # Frontend SPA (portal principal)
├── services/
│   └── web_service/               # Servico Windows (NSSM)
├── docs/                          # Documentacao detalhada
└── database/                      # Scripts SQL
```

---

## Configuracao

### Variaveis de Ambiente (.env)

```bash
# Ambiente (development/staging/production)
WATCHERDB_ENV=development

# Seguranca - JWT
JWT_SECRET_KEY=<chave_secreta>

# Encriptacao de passwords no servers.json
WATCHERDB_ENCRYPTION_KEY=<chave_fernet_base64>

# Oracle (opcional)
ORACLE_HOST=oradb.example.com
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=PROD.EXAMPLE.COM
ORACLE_USER=user
ORACLE_PASSWORD=password

# SQL Server Intelligence DB
SQL_SERVER=SERVIDOR\INSTANCIA
SQL_DATABASE=WatcherDB_Intelligence
SQL_TRUSTED_CONNECTION=yes
```

**Importante:** O `watcherdb_main.py` carrega automaticamente o `.env` via `load_dotenv()` antes de qualquer import. Isto garante que `WATCHERDB_ENCRYPTION_KEY` esta disponivel quando os modulos tentam desencriptar passwords.

### servers.json

Ficheiro de configuracao dos servidores monitorizados. Cada servidor tem:

```json
{
  "server_id": "SERVIDOR_INSTANCIA",
  "host": "SERVIDOR",
  "instance": "INSTANCIA",
  "port": 55305,
  "use_windows_auth": false,
  "username": "sql_monitoring",
  "password": "encrypted:gAAAAABp...",
  "ag_role": "PRIMARY"
}
```

- `port`: Porta TCP real (instancias nomeadas usam portas dinamicas, nao 1433)
- `password`: Prefixo `encrypted:` indica token Fernet encriptado com `WATCHERDB_ENCRYPTION_KEY`
- `use_windows_auth`: Se `true`, ignora username/password e usa autenticacao Windows

---

## Routers Disponiveis

### Core Monitoring

| Router | Prefixo | Descricao | Endpoints |
|--------|---------|-----------|-----------|
| alwayson | `/api/alwayson` | AlwaysOn Availability Groups | 6 |
| network_diagnostics | `/api/network-diagnostics` | Diagnostico de rede (7 camadas) | 2 |
| cluster | `/api/monitoring/cluster` | Windows Failover Cluster | 4 |
| overview_dashboard | `/api/monitoring` | Dashboard principal | 5 |
| diagnostics_overview | `/api/diagnostics` | Overview de diagnosticos | 3 |
| jobs | `/api/monitoring/jobs` | SQL Agent Jobs | 4 |
| service_status | `/api/monitoring/services` | Status de servicos | 3 |
| os_performance | `/api/monitoring/os` | Performance Windows OS | 2 |
| disk_unallocated | `/api/monitoring/disk` | Espaco nao alocado | 2 |
| database_discovery | `/api/monitoring/databases` | Descoberta de DBs | 2 |

### KPIs e Intelligence

| Router | Prefixo | Descricao | Endpoints |
|--------|---------|-----------|-----------|
| sqlserver_kpis | `/api/sqlserver-kpis` | KPIs SQL Server | 4 |
| intelligence_kpis | `/api/intelligence-kpis` | KPIs Intelligence DB | 3 |
| oracle_kpis | `/api/oracle-kpis` | KPIs Oracle | 4 |
| kpis_metadata | `/api/kpis` | Metadata de KPIs | 2 |

### Admin e Configuracao

| Router | Prefixo | Descricao | Endpoints |
|--------|---------|-----------|-----------|
| sql_queries | `/api/queries` | Queries customizadas (SELECT only) | 3 |
| users | `/api/users` | Gestao de utilizadores | 4 |

---

## Modulos de Monitoramento

### watcherdb_alwayson_check.py

Engine principal do modulo AlwaysOn. Funcionalidades:
- Verificacao de status de Availability Groups via DMVs
- Monitoramento de replicas (sync state, health, role)
- Deteccao de eventos de failover via XEvents e Error Log
- Calculo de ultimo failover (3 fontes: XEvents, Error Log, Event Log)
- Suporte a autenticacao Windows e SQL com passwords encriptadas

**Timeouts configurados:**
| Operacao | connection_timeout | command_timeout |
|----------|-------------------|-----------------|
| Overview (DMVs) | 15s | 300s |
| Eventos (xp_readerrorlog) | 10s | 10s |
| Last Failover | 5s | 5s |

### security_analysis.py

Analise de seguranca com 6 verificacoes:
- Autenticacao e autorizacao
- Permissoes excessivas (sysadmin)
- Configuracoes SQL Server
- Encriptacao (TDE, conexoes)
- Auditoria e logging
- Versao e patches

### space_analysis.py

Analise de espaco em disco e filegroups:
- Tamanho e crescimento de databases
- Filegroups e data files
- Previsao de crescimento (forecast)
- Alertas de espaco

---

## Encriptacao de Passwords

### Como funciona

1. Passwords no `servers.json` sao encriptadas com Fernet (symmetric encryption)
2. O token encriptado e guardado com prefixo `encrypted:` no campo `password`
3. A chave de encriptacao (`WATCHERDB_ENCRYPTION_KEY`) e uma chave Fernet base64 guardada no `.env`
4. Na desencriptacao, o sistema le a chave directamente de `os.environ` (sem derivacao)

### Gerar nova chave e encriptar password

```python
from cryptography.fernet import Fernet

# Gerar chave
key = Fernet.generate_key()
print(f"WATCHERDB_ENCRYPTION_KEY={key.decode()}")

# Encriptar password
f = Fernet(key)
encrypted = f.encrypt(b"minha_password_aqui")
print(f"password: encrypted:{encrypted.decode()}")
```

### Cadeia de desencriptacao

```
.env (WATCHERDB_ENCRYPTION_KEY)
  -> load_dotenv() em watcherdb_main.py
    -> os.environ.get('WATCHERDB_ENCRYPTION_KEY')
      -> Fernet(key).decrypt(token)
        -> password em texto limpo
```

**Atencao:** Se a chave no `.env` nao corresponder ao token no `servers.json`, a desencriptacao falha silenciosamente e a conexao SQL vai falhar com erro de autenticacao.

---

## Diagnostico de Rede

### Router: network_diagnostics.py

Endpoint: `GET /api/network-diagnostics/server/{server_id}`

Executa 7 testes em camadas:

| # | Teste | O que verifica |
|---|-------|----------------|
| 1 | Basic Network | Acesso a rede (VPN, WiFi, cabo) |
| 2 | DNS Resolution | Resolucao de hostname |
| 3 | SQL Browser | Descoberta de porta dinamica (UDP 1434) |
| 4 | TCP Port | Conexao TCP a porta do SQL Server |
| 5 | ODBC Connection | Conexao ODBC real com autenticacao |
| 6 | Query SELECT 1 | Execucao de query simples |
| 7 | Latency (3x) | Latencia media e jitter |

### Portas e instancias nomeadas

- **Instancia default** (ex: `SQLSERVER`): Usa porta `1433`
- **Instancia nomeada** (ex: `SQLSERVER\I01`): Usa porta dinamica (ex: `55305`)
- O SQL Browser Service (UDP 1434) resolve a porta dinamica
- Se o Browser nao responder, o sistema usa a porta configurada no `servers.json` (fallback)

### Painel de ajuda (`?`)

O botao `?` no modal de diagnostico abre (com scroll automatico) um painel explicativo com:
- Descricao de cada camada
- Diagnostico rapido por cenario de falha
- Explicacao sobre portas e SQL Browser

---

## AlwaysOn Availability Groups

### Endpoints

| Endpoint | Descricao | Timeout |
|----------|-----------|---------|
| `GET /api/alwayson/overview` | Lista todos AGs (cache 5min) | N/A |
| `GET /api/alwayson/server/{name}` | Status completo + eventos recentes | 15s (eventos) |
| `GET /api/alwayson/events/{name}` | Eventos de failover (ultimos N dias) | 15s + 5s |
| `GET /api/alwayson/databases/{name}` | Bases no AG com sync status | 30s |
| `GET /api/alwayson/health-check` | Verificacao rapida de saude | 30s |

### Proteccao contra timeout

O `xp_readerrorlog` pode demorar >45s em servidores com logs grandes. Para evitar que o frontend fique bloqueado:

1. **ThreadPoolExecutor**: Cada chamada a `get_ag_failover_events()` e `get_last_failover_date()` corre numa thread separada com timeout explicito
2. **Fallback gracioso**: Se o timeout for atingido, o endpoint retorna os dados de Overview (status, replicas, bases) sem eventos, em vez de falhar
3. **command_timeout reduzido**: Queries ao error log tem `command_timeout=10s` (vs 300s default)

### Fluxo de carregamento no frontend

```
1. Utilizador clica em AlwaysOn tab
2. Frontend chama /api/alwayson/server/{name}
3. Backend: DMV queries (status, replicas, bases) -> <1s
4. Backend: ThreadPoolExecutor(get_ag_failover_events, timeout=15s)
   - Se OK: retorna com eventos
   - Se timeout: retorna sem eventos (graceful degradation)
5. Frontend renderiza Overview imediatamente
6. Frontend chama /api/alwayson/events/{name} em background
   - Carrega eventos de failover separadamente
   - Se timeout: mostra "Sem eventos recentes"
```

---

## Ambientes

O projecto existe em 3 ambientes sincronizados:

| Ambiente | Directorio | Descricao |
|----------|-----------|-----------|
| **DEV** | `WATCHERDB_DEV/` | Desenvolvimento principal |
| **DEV_V4** | `WATCHERDB_DEV_V4/` | Replica para testes V4 |
| **V4** | `WATCHERDB_V4/` | Producao V4 |

**Regra:** Alteracoes sao feitas primeiro em DEV e depois replicadas para DEV_V4 e V4. **NUNCA** modificar WATCHERDB_V5 a partir daqui.

---

## Instalacao

### Requisitos

- Python 3.10+
- ODBC Driver 17 for SQL Server
- Oracle Instant Client (opcional, para KPIs Oracle)

### Dependencias

```bash
pip install -r requirements.txt
```

Dependencias principais:
- `fastapi` + `uvicorn` - Framework web
- `pyodbc` - Conexao SQL Server
- `cryptography` - Encriptacao Fernet
- `python-dotenv` - Carregamento de `.env`
- `cx_Oracle` - Conexao Oracle (opcional)

### Iniciar

```bash
python watcherdb_main.py
```

O servidor inicia em `https://0.0.0.0:8443` (HTTPS) por defeito.

---

## Changelog

Ver [docs/CHANGELOG.md](docs/CHANGELOG.md) para historico completo.

### v2.2.0 (2026-03-05) - AlwaysOn Connectivity Fix + Network Diagnostics

**Correccoes:**
- Cadeia completa de autenticacao AlwaysOn (encryption key, load_dotenv, porta dinamica)
- Password decryption corrigida: usa `WATCHERDB_ENCRYPTION_KEY` directamente (sem derivacao de JWT)
- Porta SQLHDSPRD212\I01 corrigida: 1433 -> 55305 (instancia nomeada)
- Re-encriptacao de todas as passwords com chave Fernet conhecida

**Novos Recursos:**
- Router `network_diagnostics.py` com diagnostico em 7 camadas
- Painel de ajuda interactivo no diagnostico de rede
- ThreadPoolExecutor com timeout em endpoints AlwaysOn (15s eventos, 5s last_failover)
- `load_dotenv()` no inicio de `watcherdb_main.py`

**Melhorias de Performance:**
- command_timeout reduzido de 30s para 10s em eventos AlwaysOn
- command_timeout reduzido de 20s para 5s em last_failover
- Fallback gracioso: Overview carrega sem eventos se timeout

### v2.1.0 (2026-02-20) - Consolidacao & Performance

- Router `security.py` para analise de vulnerabilidades
- Router `windows.py` para metricas Windows OS
- Router `alerts_unified.py` consolidando 6 endpoints
- Router `admin_metrics.py` para monitoramento de uso
- Performance de alertas: 900ms -> 120ms (-87%)

---

## Links Uteis

- [CHANGELOG completo](docs/CHANGELOG.md)
- [Logica de Backup Status](docs/LOGICA_BACKUP_STATUS.md)
- [Documentacao Jobs Module](docs/DOCUMENTACAO_COMPLETA_JOBS_MODULE.md)
- [Queries por KPI](QUERIES_POR_KPI.md)

---

_Ultima actualizacao: 05 de Marco de 2026_
