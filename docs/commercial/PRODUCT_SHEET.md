# WatcherDB V3.3 Standard Edition — Product Sheet

## SQL Server Monitoring Platform

**Feito por DBAs. Para DBAs.**

---

### O Problema

Equipas DBA gastam **20-40 horas por semana** em tarefas manuais:
- Verificar backups em cada servidor (SSMS → cada instancia)
- Monitorar espaco em disco e filegroups
- Investigar jobs falhados e conflitos de schedule
- Verificar AlwaysOn health e replicas
- Diagnosticar incidentes de performance (blocking, deadlocks)
- Gerar relatorios de estado para a gestao

Multiplicado por 50, 100, 200 servidores — e insustentavel.

### A Solucao

**WatcherDB** monitoriza TODOS os seus SQL Servers numa unica plataforma:

- **KPIs** — visao centralizada de 100+ servidores em tempo real
- **Analise de Backup** — deteccao automatica de gaps, tendencias, alertas
- **Analise de Espaco** — filegroups, forecasting de crescimento, candidatos a shrink
- **AlwaysOn Monitoring** — health, replicas, failover events, RPO/RTO
- **Jobs Analysis** — falhados, conflitos de schedule, tendencias
- **SQL Diagnostics** — blocking, deadlocks, slow queries, missing indexes
- **Seguranca** — TDE, permissoes, audit
- **Network Diagnostics** — DNS, TCP, ODBC, latencia

### Diferenciais

| WatcherDB | Concorrencia |
|-----------|-------------|
| **100% self-hosted** — dados nunca saem da sua rede | Cloud-dependent |
| **SQL Server nativo** — feito especificamente para SQL Server | Generico (suporta tudo mal) |
| **Feito por DBAs** — features que DBAs realmente precisam | Feito por developers |
| **1/3 do preco** — competitivo vs SolarWinds, Redgate, Datadog | €€€€€ |
| **Zero vendor lock-in** — seus dados, seu servidor | Lock-in cloud |
| **Active Directory** — integracao nativa com AD/LDAP + Kerberos | Autenticacao propria |

### Arquitectura

```
Browser (qualquer dispositivo)
    |
    v
WatcherDB V3.3 Standard Edition (FastAPI + Python)  ← Servidor Windows dedicado
    |
    v
SQL Server instances (via ODBC/Windows Auth)
    |
    v
WatcherDB Intelligence DB (metadados + KPIs historicos)
```

- **Zero agentes** — nao instala nada nos servidores monitorizados
- **Windows Authentication** — usa credenciais de dominio existentes
- **Monitoring read-only** — WITH (NOLOCK), nao afecta performance

### Requisitos

| Componente | Minimo | Recomendado |
|-----------|--------|-------------|
| OS | Windows Server 2016+ | Windows Server 2022 |
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disco | 20 GB SSD | 50 GB SSD |
| SQL Server | 2016+ | 2019/2022 |
| Python | 3.11+ | 3.13/3.14 |
| ODBC | Driver 17 | Driver 18 |

### Stack Tecnologico

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.14, FastAPI, Uvicorn |
| Frontend | HTML5, CSS3, JavaScript, htmx, Web Components |
| Database | SQL Server (pyodbc, Windows Auth) |
| Cache | In-memory TTLCache + Redis (opcional) |
| Auth | JWT + bcrypt + Active Directory (LDAP/Kerberos) |
| Monitoring | Prometheus + OpenTelemetry + structlog |
| Seguranca | CSP nonce, HSTS, rate limiting, DOMPurify |
| Deploy | Windows Service (pywin32), Docker (opcional) |
| Proteccao | PyArmor Pro (codigo encriptado) |

### Numeros

| Metrica | Valor |
|---------|------:|
| Endpoints API | 158 |
| Modulos core | 26 |
| Testes automaticos | 360 |
| Nota de auditoria tecnica | 8.1/10 |
| Idiomas suportados | 3 (PT/EN/ES) |
| Servidores testados em producao | 100+ |

### Contacto

[A preencher]

---

*WatcherDB V3.3 Standard Edition — © 2026*
