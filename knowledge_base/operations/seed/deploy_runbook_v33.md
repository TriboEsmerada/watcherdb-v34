# Deploy Runbook V3.3 (seed)

Runbook de deploy do WatcherDB V3.3 Standard Edition em máquina cliente Windows.

**Status:** SEED — extraído do código actual (commit `691a529`). Refinar quando deploy real for feito.

**Owner:** `watcherdb-deploy-architect`
**Reviewers:** `watcherdb-v33-specialist`, `watcherdb-security-auditor`

---

## 1. Pré-requisitos

### Servidor Windows

- Windows Server 2019 / 2022 (Enterprise ou Standard)
- Mínimo 4 vCPU, 8 GB RAM, 50 GB disco SSD
- Acesso de rede aos SQL Servers a monitorizar (porta 1433 default ou customizada)
- Acesso ao domínio AD do cliente (porta 636 LDAPS default; 389 LDAP só com flag explícita)

### Software

- Python 3.11+ instalado (path em PATH)
- ODBC Driver 17/18 for SQL Server
- PowerShell 5.1+ (incluído em Windows Server)
- Acesso de Administrator local para instalar Windows Service

### Contas

- **Service account AD** — least-privilege:
  - `Read` permissions no domínio AD (para LDAP search)
  - SQL Server: `db_datareader` na BD `WatcherDB_Intelligence` + `EXEC` em `usp_swap_kpi_stg_tables`
  - Local: `Log on as a service` policy granted
- **Admin local** — apenas para instalação inicial; não usado em runtime

## 2. Componentes a instalar

| Componente | Path destino | Porta | Service name |
|---|---|---|---|
| Web service V3.3 | `<install-root>/WatcherDB_V3.3/` | **8433** | `WatcherDBWebServiceV33` |
| Config | `services/web_service/config.yaml` | — | — |
| BD | `WatcherDB_Intelligence` em `<SQL Instance cliente>` | 1433 | (partilhada com V1 collector) |

## 3. Passos de instalação

### 3.1. Preparação

```powershell
# Como Administrator local
cd <install-root>
git clone <repo-V3.3> WatcherDB_V3.3
cd WatcherDB_V3.3
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3.2. Configuração

1. Editar `services/web_service/config.yaml`:
   - `server.port` = `8433` (default; alterar só se colisão com porta cliente)
   - `auth.active_directory.enabled` = `true`
   - `auth.active_directory.domain` = NetBIOS do cliente (ex.: `CONTOSO`)
   - `auth.active_directory.server` = FQDN do DC (ex.: `dc01.contoso.local`)
   - `auth.active_directory.base_dn` = `DC=contoso,DC=local`
   - `auth.active_directory.use_ssl` = `true` (LDAPS porta 636 — default banking)
   - **Multi-domain (Patch D, commit `691a529`)**: configurar adicional em
     Control panel UI → `WatcherDB_System_Config.ad_domains` JSON

2. Setar variável de ambiente JWT secret:
   ```powershell
   [Environment]::SetEnvironmentVariable("WATCHERDB_JWT_SECRET", "<random-32-chars>", "Machine")
   ```

3. DDL: aplicar `scripts/sql/performance_module_schema.sql` na BD `WatcherDB_Intelligence`
   (idempotente, `IF NOT EXISTS`).

### 3.3. Instalar Windows Service

```powershell
python services/web_service/install.py install
python services/web_service/install.py start
```

Service ficará em `WatcherDBWebServiceV33` em `Services.msc`. Configurar para correr
como **service account AD** (não LocalSystem).

### 3.4. Smoke test

```powershell
# 1. Verifica processo activo
Get-Service WatcherDBWebServiceV33

# 2. Health check
Invoke-WebRequest http://localhost:8433/health

# 3. Login admin (browser)
#    http://<server-ip>:8433/
#    Login com user AD do cliente — após Patch D, multi-domain suportado
```

## 4. Rollback

### 4.1. Rollback de versão

```powershell
python services/web_service/install.py stop
git checkout <previous-tag>
pip install -r requirements.txt
python services/web_service/install.py start
```

### 4.2. Rollback de DDL

DDL é **idempotente forward-only** (sem DROP). Rollback de schema requer:

1. Backup pré-deploy (DBA cliente faz `BACKUP DATABASE WatcherDB_Intelligence`)
2. Restore se necessário (decisão DBA Lead)

**NUNCA** correr `DROP TABLE` sem aprovação explícita — V1 collector + V3.3 partilham
estas tabelas, drop afecta múltiplos tiers.

## 5. Troubleshooting comum

| Sintoma | Causa provável | Fix |
|---|---|---|
| Service não arranca | `WATCHERDB_JWT_SECRET` env var em falta | Setar via `[Environment]::SetEnvironmentVariable`, restart service |
| 401 ao login com user AD | LDAPS firewall (porta 636) bloqueada | Validar `Test-NetConnection <DC> -Port 636` |
| 401 com user de domínio adicional | Patch D não aplicado ou `ad_domains` JSON mal-formado | Ver commit `691a529` + Control panel UI |
| `cwd != project root` warning | Service a correr fora do path correcto | Confirmar `load_dotenv` com path explícito (commit `a215e10`) |
| Hardware fingerprint NULL | PowerShell exec policy | Ver commit `0f76a01` (PowerShell fallback shipped) |

## 6. Próximas iterações deste runbook

- [ ] Adicionar secção PyArmor Pro (reg 11618) — packaging final
- [ ] Adicionar secção SBOM (CycloneDX via Syft) para entrega banking
- [ ] Adicionar secção SSL/TLS cert provisioning (cliente preference)
- [ ] Adicionar secção SQL Server permissions least-privilege detalhada
- [ ] Cross-link com `keypair_rotation_runbook.md` em `deploy/`

## References

- `services/web_service/config.yaml` — configuração runtime
- `services/web_service/install.py` — install/start/stop logic
- `services/web_service/service.py` — Windows service definition
- `deploy/install_production.ps1` — production installer (PS1)
- `deploy/DEPLOY_GUIDE.md` — guia detalhado deploy
- `deploy/CHECKLIST_DEPLOY.md` — checklist por release
- `api/routers/auth_compat.py:209` (`_require_admin`) — auth gate
- Commit `691a529` — Patch D multi-domain LDAP
- Commit `7c95c53` — Patch A/B/C URI sanitize + silent-fail + diagnostic
- Commit `a215e10` — load_dotenv path fix
- Commit `0f76a01` — hardware fingerprint via PowerShell

## Sensitivity note

Este runbook **não menciona nomes de cliente reais**. Quando customizado para deploy
específico, o ficheiro customizado fica em `deploy/customer-<nome>/runbook.md` e
**NÃO entra na KB local** (gate 4 sensitivity REJECT).
