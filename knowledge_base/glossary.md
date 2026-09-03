# Glossary — WatcherDB V3.3

Termos do domínio que specialists e novos contribuidores devem reconhecer.

## DBA / SQL Server

| Termo | Definição |
|---|---|
| **AlwaysOn** | Tecnologia de alta disponibilidade SQL Server (Availability Groups). Failovers monitorizados pelo collector V1. |
| **AGG_VIEW / DET_VIEW** | Views agregada / detalhada nas tabelas KPI. AGG resume; DET tem evento individual. Fallback AGG→DET quando formatos de instance divergem. |
| **DMV** | Dynamic Management View — views de sistema do SQL Server (ex.: `sys.dm_exec_requests`). |
| **DBCC** | Database Console Commands. `DBCC CHECKDB` valida integridade; resultados monitorizados. |
| **Deadlock** | Conflito mútuo de locks entre 2+ sessões. SQL Server kill arbitrário de uma. Captura via XE `system_health` ou XE customizado. |
| **Linked Server** | Conexão server-to-server SQL Server. V3.3 usa para AlwaysOn cross-node + monitoring distribuído. |
| **`query_hash` / `plan_handle`** | Identificadores binários (VARBINARY) das queries; vêm como `bytes` em pyodbc — usar `_json_safe` em `modules/performance/base.py`. |
| **`xp_cmdshell`** | Stored procedure SQL Server perigosa (executa comandos OS). V3.3 NÃO usa. Auditoria de segurança verifica. |

## Active Directory / Auth

| Termo | Definição |
|---|---|
| **AD** | Active Directory — directory service Microsoft. V3.3 autentica DBAs via LDAP/LDAPS contra AD do cliente. |
| **LDAP / LDAPS** | Protocol(o seguro) Lightweight Directory Access. V3.3 usa LDAPS (porta 636) por defeito; LDAP (389) só com flag explícita. |
| **DN** | Distinguished Name — caminho hierárquico no AD (`CN=user,OU=DBAs,DC=cliente,DC=local`). |
| **Service account** | Conta AD dedicada ao Windows Service do V3.3 (`WatcherDBWebServiceV33`). Least-privilege: read-only no AD + grant SQL Server específico. |
| **Multi-domain LDAP** | Patch D (commit 691a529) — V3.3 suporta múltiplos domínios AD em paralelo (clientes com floresta multi-tenant). |
| **`_require_admin`** | Decorator FastAPI em `api/routers/auth_compat.py:209`. Gating para endpoints sensíveis. |

## WatcherDB-specific

| Termo | Definição |
|---|---|
| **V3.3 / Standard Edition** | Edição comercial "core monitoring". Sem AI/ML. Porta 8433. Service `WatcherDBWebServiceV33`. Esta KB. |
| **V5 / V5.5 / V6 — Pro Edition** | Edições premium fora do scope deste council. Têm AI, RAG, Knowledge Graph, Ollama. |
| **V1 Intelligence** | Collector + BD partilhada (`WatcherDB_Intelligence` em `SQLHDSTST505\I01`). Alimenta V3.3 e V5. Veto power em mudanças à infra partilhada. |
| **FEATURE_MATRIX** | Documento canónico Std vs Pro. `docs/FEATURE_MATRIX.md`. Ground truth para tier decisions. |
| **Performance Module** | `modules/performance/` — 8 investigators (deadlocks, blocking, IO, CPU, memory, etc.). Shared core entre Std e Pro. |
| **KPI dashboard** | SPA `templates/watcherdb_portal.html` (~47k linhas). Chart.js + vanilla JS. 20+ cards. |
| **Tabelas `KPI_MSSQL_*_STG`** | 13 tabelas staging com pares BLUE/GREEN. Swap atómico via `usp_swap_kpi_stg_tables` (WITH UPDLOCK). |

## Nestor Council

| Termo | Definição |
|---|---|
| **Council** | Multi-persona specialists + orquestrador + micro-agents. Read-only por design (excepto `core-librarian` + orquestrador). |
| **Orquestrador** | Claude Code main session — tem context completo + Edit/Write/Bash. Único que aplica mudanças. |
| **Specialist** | Agent multi-persona com scope profundo. Read-only. Produz pareceres / diffs em texto. |
| **Micro-agent** | Agent single-task com charter ≤200 palavras. Output format obrigatório. Read-only. |
| **PROACTIVE FINDING** | Problema fora do scope da task imediata, sinalizado pelo specialist. Vai para `findings-inbox.md`. |
| **Pattern #7** | Cross-Cutting Consensus — dispatch paralelo de 3+ specialists para decisão multi-domain. |
| **Living Nestor** | Ambient awareness — specialists lêem `.nestor/session.log` + `.nestor/bulletin/inbox.md` no arranque. |
| **Velocity Pact** | Aprovação tácita por escopo. Avança no escopo, pára em mudança de rumo, sempre confirma irreversível. |
