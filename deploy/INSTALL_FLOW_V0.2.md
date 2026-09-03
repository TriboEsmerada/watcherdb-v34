# WatcherDB Install Flow v0.2 — Operator Runbook

**Sprint:** Install flow v0.2 (FIND-20260424-001)
**Status:** Python-side deliverables **shipped 2026-04-24**. Burn bootstrapper (B1/B4) deferred para sprint dedicado com WiX toolchain.
**Scope:** V3.3 Standard Edition + preparação para V6 Enterprise

---

## Visão geral

Instalação v0.2 organiza-se em **5 fases** mapeadas a 5 ferramentas Python:

```
Fase 1 — Pré-requisitos ──► deploy/prereqs_check.py          (B3)
Fase 2 — MSI install    ──► dist/msi/WatcherDB_V3.3.msi      (existing)
Fase 3 — Industry wizard──► deploy/industry_wizard.py         (B2)
Fase 4 — Farm inventory ──► deploy/farm_inventory_parser.py   (B7)
Fase 5 — License        ──► deploy/generate_license_keys.py   (B5)
                             + customer license.dat (out-of-band vendor)
```

**Entry point único:** `deploy/install_orchestrator.py` compõe as 5 fases num só script.

---

## Pré-requisitos (cliente prepara MANUALMENTE antes de correr installer)

| Item | Acção cliente | Validado por |
|---|---|---|
| SQL Server acessível | Confirmar instância a correr + TCP port aberto (default 1433) | CHK-02 prereqs_check |
| User `sql_monitoring` | `CREATE LOGIN sql_monitoring` + `GRANT VIEW SERVER STATE` | CHK-03 prereqs_check |
| AD service account | `net user watcherdb_svc /add /domain` + "Logon as a service" right | CHK-04 prereqs_check |
| ODBC Driver 17 ou 18 | Download de https://aka.ms/odbc-sqlserver | CHK-01 prereqs_check |
| Admin privileges | Run elevated shell | CHK-08 prereqs_check |
| Disk space 500MB | No drive de install | CHK-07 prereqs_check |

---

## Fase 1 — Pré-requisitos check

**Propósito:** validar ambiente antes de correr MSI. Falha graciosa com fix hints.

```powershell
python deploy\prereqs_check.py `
    --sql-server SQL01.banco.pt `
    --sql-port 1433 `
    --sql-user sql_monitoring `
    --ad-service-account DOMAIN\watcherdb_svc `
    --web-port 8433 `
    --install-dir "C:\Program Files\WatcherDB"
```

**Output exemplo:**
```
======================================================================
WatcherDB Pre-install Prereqs Check
======================================================================
  [PASS] CHK-01 ODBC Driver 17/18: Found: ODBC Driver 18 for SQL Server
  [PASS] CHK-02 SQL Server TCP: SQL01.banco.pt:1433 reachable
  [PASS] CHK-03 SQL login + perms: Login 'sql_monitoring' exists with VIEW SERVER STATE
  [PASS] CHK-04 AD service account: Account 'DOMAIN\watcherdb_svc' resolvable
  [PASS] CHK-05 Port available: Port 8433 is free
  [PASS] CHK-06 Python version: Python 3.11.10
  [PASS] CHK-07 Disk space: 45012MB free on C:\
  [PASS] CHK-08 Admin privileges: Running as Administrator
----------------------------------------------------------------------
  8 passed, 0 warnings, 0 failed
======================================================================

OK: all checks passed. Safe to install.
```

**Exit codes:** 0=OK, 1=fail (blocking), 2=warnings (installer pode prosseguir).

**JSON mode** (para bootstrapper parsear): `--json` adiciona output estruturado.

---

## Fase 2 — MSI install (caminho canonical)

Execução do instalador principal. **Não alterado por este sprint** — pipeline existente V3.3.

```powershell
msiexec /i dist\msi\WatcherDB_V3.3_Standard.msi /qn /l*v install.log
```

Pós-install, o service `WatcherDBWebServiceV33` fica instalado mas **não arranca** até Fases 3+4+5 estarem completas.

### Windows services criados por edition

A MSI installer cria os Windows services apropriados ao tier escolhido. Cada service fica em estado `STOPPED` até Fases 3+4+5 (config + license) estarem completas.

| Tier | Service Name | Port | Role |
|---|---|---|---|
| **V3.3 Standard** | `WatcherDBWebServiceV33` | 8433 | Web service (FastAPI + collector hooks) |
| **V5 Pro Standard** | `WatcherDBV5WebService` | 8450 | Web service Pro com AI/ML stack |
| **V5.5 Pro Enhanced Sovereign** | `WatcherDBWebServiceV55` | 8555 | Web service sovereign (LOCAL-first AI) |
| **V6 Pro Enhanced Banking** | `WatcherDBWebServiceV6` | 8660 | Main FastAPI banking-grade |
| **V6 Pro Enhanced Banking** | `WatcherDB-V6-Hybrid` ⭐ | 8460 | **Hybrid router** (HaikuClassifier + AI Exp dispatch) — REQUERIDO em V6 |

⭐ **V6 Pro Enhanced Banking** requer **DOIS services Windows** registados pelo MSI:
1. `WatcherDBWebServiceV6` (8660) — main FastAPI app
2. `WatcherDB-V6-Hybrid` (8460) — Hybrid router que faz pre-classification (HaikuClassifier) + dispatch para AI Experimental engine quando aplicável. Este service é **obrigatório** — sem ele o V6 banking pipeline degrada para V5/V5.5 mode (perde mandatory_suprema_escalation gate).

**MSI install spec V6 (B1 deferred sprint):**
- WiX `Product.wxs` deve ter dois `<ServiceInstall>` directives
- Service account partilhado (`DOMAIN\watcherdb_svc`)
- `WatcherDB-V6-Hybrid` arranca **depois** de `WatcherDBWebServiceV6` (dependency order)
- Ambos services usam `startup_guard.validate_and_enforce()` para license check

```xml
<!-- V6 Product.wxs example (B1 deferred sprint deliverable) -->
<ServiceInstall
    Id="WatcherDBV6Main"
    Name="WatcherDBWebServiceV6"
    DisplayName="WatcherDB V6 Web Service"
    Type="ownProcess"
    Start="auto"
    ErrorControl="normal"
    Account="[SERVICEACCOUNT]"
    Password="[SERVICEPASSWORD]" />

<ServiceInstall
    Id="WatcherDBV6Hybrid"
    Name="WatcherDB-V6-Hybrid"
    DisplayName="WatcherDB V6 Hybrid Router"
    Description="HaikuClassifier + AI Experimental dispatch router for banking-grade pipeline"
    Type="ownProcess"
    Start="auto"
    ErrorControl="normal"
    Account="[SERVICEACCOUNT]"
    Password="[SERVICEPASSWORD]"
    DependsOn="WatcherDBWebServiceV6" />
```

**Validação pós-install:**
```powershell
sc query WatcherDBWebServiceV6
sc query WatcherDB-V6-Hybrid
# Ambos devem reportar STATE: STOPPED ate Fases 3-5 completas
```

---

## Fase 3 — Industry & Compliance wizard

**Propósito:** gerar `client_context.yaml` + `compliance_rules.yaml` em `C:\ProgramData\WatcherDB\` conforme indústria + regimes do cliente.

### Modo interactive

```powershell
python deploy\industry_wizard.py --output-dir "C:\ProgramData\WatcherDB"
```

Pergunta:
- Customer name (ex: "Banco XYZ Portugal")
- Industry (banking/healthcare/retail/govt/generic)
- Country ISO (PT/ES/US/BR/...)
- Regulatory regimes (multi-select: GDPR, EBA, BdP, DORA, PSD2, HIPAA, PCI-DSS, SOC2, ISO27001)
- Primary language AI (pt/en/es/fr)
- Deployment tier (standard/enterprise)
- Banking core procs/tables (se industry=banking — obrigatório)

### Modo preset (non-interactive)

```powershell
python deploy\industry_wizard.py --preset banking_pt --output-dir "C:\ProgramData\WatcherDB"
# (banking_pt requer banking_core_procs — usa --config em vez de preset)
```

### Modo config file

```powershell
python deploy\industry_wizard.py --config answers.yaml --output-dir "C:\ProgramData\WatcherDB"
```

`answers.yaml` exemplo:
```yaml
industry: banking
country: PT
primary_language: pt
customer_name: Banco XYZ
deployment_tier: enterprise
regimes:
  - GDPR
  - EBA
  - BdP
  - DORA
  - SOC2
banking_core_procs:
  - dbo.usp_ScoreTransaction
  - Risk.usp_AMLCheck
banking_core_tables:
  - Accounts.Balance
```

**Outputs gerados:**
- `client_context.yaml` — identidade do cliente (user-editable)
- `compliance_rules.yaml` — regras derivadas (audit retention, PII regex, mandatory Suprema, etc.) — **não editar manualmente**

---

## Fase 4 — Farm inventory ingestion

**Propósito:** parsear lista da farm SQL Server cliente e gerar `config/servers.json` canonical (consumido por V1 collector).

### Input suportado

**CSV:**
```csv
host,instance,port,auth_mode,username,description,environment,priority,enabled,has_alwayson,ag_name,ag_listener
SQL01.banco.pt,MSSQLSERVER,1433,windows,,Core Banking PRD,production,1,true,false,,
SQL02.banco.pt,PROD,1433,sql,sql_monitoring,Risk Engine,production,1,true,false,,
SQL03.banco.pt,AG,1433,sql,sql_monitoring,AG Listener,production,1,true,true,AG_Finance,AG_FIN_LISTENER
```

**JSON:** array de objectos com mesma shape.

### Execução

```powershell
python deploy\farm_inventory_parser.py `
    --input farm.csv `
    --output "C:\ProgramData\WatcherDB\servers.json" `
    --master-host SQLHDMASTER01 `
    --master-instance I01 `
    --master-db WatcherDB_Intelligence `
    --master-username sql_monitoring `
    --validate-tcp   # opcional: testar TCP reachability por entry
```

**Segurança:** passwords **nunca** em CSV plaintext. Parser emite placeholder `@ENCRYPT_AT_INSTALL@` — installer wizard recolhe interactivamente na Fase 5 ou via `credential_manager.py`.

**Validação warnings:**
- `has_alwayson=true` sem `ag_name` → warning
- `auth_mode` fora de `sql|windows` → warning + default `sql`
- `environment` fora de `production|staging|dev|test|dr` → warning
- `--strict` promove warnings a errors

---

## Fase 5 — License

### 5.1 Vendor gera license (**out-of-band**, na workstation TAP/WatcherDB)

```powershell
python -m watcherdb.licensing.generator `
    --customer-id <uuid> `
    --expires 2027-04-22 `
    --bios-uuid <wmic csproduct UUID do servidor cliente> `
    --cpu-id <wmic cpu ProcessorId> `
    --hostname <hostname cliente> `
    --sql-servername SQLHDMASTER01\I01 `
    --industry banking `
    --regulatory-regime GDPR EBA BdP DORA `
    --license-id $(New-Guid) `
    --edition enterprise `
    --out .\banco_xyz.lic
```

Vendor entrega `.lic` ao cliente (email seguro / USB / portal).

### 5.2 Cliente coloca license no servidor

```powershell
Copy-Item banco_xyz.lic "C:\ProgramData\WatcherDB\license.dat"
```

### 5.3 Startup guard valida (automático em service start)

`watcherdb.licensing.startup_guard.validate_and_enforce()` corre no startup de cada service. Path lookup em 3-tier:

1. `WATCHERDB_LICENSE_PATH` env var
2. `C:\ProgramData\WatcherDB\license.dat`
3. `<install-dir>\license.dat`

**Windows Event Log** entries geradas (source="WatcherDB"):
- `1000 LICENSE_VALIDATION_OK` (startup OK)
- `1001 LICENSE_VALIDATION_FAILED` (qualquer falha)
- `1002 LICENSE_EXPIRY_WARNING` (30d antes expirar)

**Strict mode default** (FIND-20260424-003) — service refuses start se license inválida. Advisory mode requer `WATCHERDB_LICENSE_ENFORCE=advisory` env var explícito (dev/test only).

---

## Entry point unificado — install_orchestrator.py

Em vez de correr 4 scripts sequenciais manualmente:

```powershell
python deploy\install_orchestrator.py `
    --mode batch `
    --sql-server SQL01.banco.pt --sql-port 1433 --sql-user sql_monitoring `
    --ad-service-account DOMAIN\watcherdb_svc --web-port 8433 `
    --install-dir "C:\Program Files\WatcherDB" `
    --config-dir "C:\ProgramData\WatcherDB" `
    --preset banking_pt `
    --wizard-config answers.yaml `
    --farm-inventory farm.csv --master-host SQLHDMASTER01 `
    --license-path "C:\ProgramData\WatcherDB\license.dat"
```

**Exit codes** (diferenciados por fase que falhou):
- `0` — tudo OK
- `1` — Fase 1 prereqs fail
- `2` — Fase 3 industry wizard fail
- `3` — Fase 4 farm inventory fail
- `4` — Fase 5 license missing/invalid
- `5` — orchestration error (bad args)

**Modo single phase** — correr só uma fase:
```powershell
python deploy\install_orchestrator.py --phase prereqs --sql-server SQL01
python deploy\install_orchestrator.py --phase license --license-path C:\X\license.dat
```

---

## Ordem completa de execução

```
1. [Cliente] Prepara pré-requisitos (SQL Server, sql_monitoring user, AD svc, ODBC)
2. [Cliente] Executa prereqs_check.py — valida ambiente antes de continuar
3. [Cliente] Executa MSI install — deploys código protegido PyArmor + WiX
4. [Cliente] Executa industry_wizard.py — responde perguntas compliance
5. [Cliente] Prepara farm.csv/json com lista SQL Servers a monitorizar
6. [Cliente] Executa farm_inventory_parser.py — gera servers.json
7. [Vendor] Gera license.dat com fingerprint do cliente (machine-bound)
8. [Cliente] Copia license.dat para C:\ProgramData\WatcherDB\
9. [Cliente] Start service: net start WatcherDBWebServiceV33
10. [Cliente] Abrir portal em http://127.0.0.1:8433 (ou port configurado)
```

**Alternativa compacta:** steps 2+4+6+8 via `install_orchestrator.py --mode batch`.

---

## Troubleshooting

### Prereqs check FAIL mas ambiente parece OK

- Se CHK-02 timeout: firewall Windows ou SQL Server TCP/IP desactivado
- Se CHK-03 SKIP: pyodbc não disponível no interpreter que correu o check — installer bundled tem pyodbc; não é problema real
- Se CHK-04 FAIL: AD service account não encontrável — verificar domain join + spelling

### License validation FAILED

- Event Log Windows → Application → source "WatcherDB" → event 1001 para detalhe
- Fingerprint mismatch: verificar `wmic csproduct UUID` + `wmic cpu ProcessorId` match com valores submetidos ao vendor

### Industry wizard não corre (pytest skipped)

- Wizard só corre interactive quando sessão tem tty. Use `--preset` ou `--config` para non-interactive.

### Service não arranca

- `sc query WatcherDBWebServiceV33` + Event Log
- Log file em `C:\ProgramData\WatcherDB\logs\` (tier V33)

---

## Referências

- Finding meta: `watcherdb-council/findings-inbox.md#FIND-20260424-001`
- Sub-findings: 002 (V3.2 refs), 003 (strict default), 004 (pubkey path), 005 (V5+ license gap)
- Memory progress: `session_20260424_install_sprint_progress.md`
- Sprint commits: `e7f437c`..`f86df92` (+ commit este runbook)

---

## Deferred para sprint subsequente (B1+B4 full bootstrapper)

| Component | Scope | Toolchain |
|---|---|---|
| B1 Burn bootstrapper | EXE wrapper que invoca MSI + Python scripts | WiX Bundle + C# WinForms |
| B4 All-questions-upfront UI | Dialogs graficos antes de MSI | C# managed BA |
| V6 Enterprise MSI | Clone do V3.3 MSI para tier Ent | WiX v3 + PyInstaller V6 spec |
| B5.2 CRL | Signed revoked_licenses.json | security-auditor design |
| B6.2 V1 collector + AI service | Adopção do startup_guard nos 2 outros services | v1-intel-specialist + v5-specialist |

Estes items requerem **WiX Toolset v3** + **DigiCert KeyLocker credentials** + **specialists dispatch** para sprint dedicado com MSI toolchain disponível na workstation build.
