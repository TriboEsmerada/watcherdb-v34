# WatcherDB V3.3 — Test Install Guide

Guia conciso para instalar V3.3 num target machine para **TESTE INTERNO** (não cliente).

> ⚠️ Para cliente real ainda faltam externos: MSI signing (DigiCert),
> EULA legal review (substituir license.rtf), VM snapshot smoke test.
> Este guia assume scenario de test (MSI unsigned + advisory mode OU test licence).

---

## Pre-requisitos no target machine

| Item | Verificação |
|---|---|
| Windows Server 2016+ OR Win 10/11 | `winver` |
| ODBC Driver 17 ou 18 | `Get-OdbcDriver \| Where Name -match "SQL Server"` |
| .NET Framework 4.7.2+ | `(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full').Release -ge 461808` |
| Admin rights | `whoami /priv` |
| Porta 8433 livre | `netstat -ano \| findstr 8433` |
| 500 MB disk livre | `Get-PSDrive C` |
| SQL Server acessível (TCP) | `Test-NetConnection <sql_host> -Port 1433` |

**Validação automatizada:** correr `deploy/preflight_target.ps1` (script 10 phases).

---

## Fase 0 — No build machine (computador actual)

Artefactos prontos em `dist/`:
```
dist/msi/WatcherDB_V3.3_Standard.msi               37.6 MB     ← installer
dist/msi/WatcherDB_V3.3_Standard.sbom.cyclonedx.json  54.8 KB  ← SBOM (opcional)
```

(Se não tiveres `dist/`, correr `python deploy/build.py` + `pwsh deploy/build_msi.ps1 -Clean` primeiro.)

---

## Fase 1 — DBA setup SQL Server (REGRA OURO #2)

**Identidade:** DBA do SQL Server target (NÃO o domain user que vai correr install).

```sql
-- No SQL Server target, conectado como DBA:
USE master;
GO

-- Criar login SQL auth para WatcherDB monitorar:
CREATE LOGIN sql_monitoring WITH PASSWORD = '<strong_password_here>',
    CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
GO

-- Permissões mínimas (least-privilege):
GRANT VIEW SERVER STATE TO sql_monitoring;
GRANT VIEW ANY DEFINITION TO sql_monitoring;
GRANT VIEW ANY DATABASE TO sql_monitoring;
GO

-- Em cada DB monitorizada (se discovery automático não basta):
-- USE <database_name>;
-- CREATE USER sql_monitoring FOR LOGIN sql_monitoring;
-- GRANT VIEW DATABASE STATE TO sql_monitoring;
-- GO
```

**Guardar password** — vai ser usado em `.env` config no target após install.

---

## Fase 2 — Transferir MSI para target

Opções (escolher a tua):

```powershell
# Via rede (UNC share):
robocopy dist\msi \\TARGET_HOST\c$\Temp\WatcherDB_Install\ WatcherDB_V3.3_Standard.msi

# Via RDP clipboard:
# Copy MSI no build machine -> Paste em c:\Temp\WatcherDB_Install\ no target

# Via USB drive: simples copy
```

---

## Fase 3 — No TARGET machine: preflight

Copiar `deploy/preflight_target.ps1` para target + correr:

```powershell
# Como Administrator no target:
powershell.exe -ExecutionPolicy Bypass -File preflight_target.ps1 -SqlServer "<sql_host>"

# Exit 0 = OK to install
# Exit 1 = fix issues primeiro
# Exit 2 = warnings (proceed com cuidado)
```

Se algum check falha, fix antes de avançar.

---

## Fase 4 — Install MSI

3 cenários (escolher):

### Cenário A — NetworkService (simples, sem AD)
```powershell
# Como Administrator no target:
msiexec /i C:\Temp\WatcherDB_Install\WatcherDB_V3.3_Standard.msi /qn /l*v C:\Temp\wdb_install.log

# Service correrá como NT AUTHORITY\NetworkService.
# SQL Server precisa aceitar Windows Auth do machine$ OU usar SQL Auth com sql_monitoring no .env.
```

### Cenário B — Domain service account
```powershell
# Como Administrator no target:
$svcAccount = "DOMAIN\svc_watcherdb_v33"
$svcPass = Read-Host -AsSecureString "Service account password"
$plainPass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($svcPass))

Start-Process -Wait msiexec -ArgumentList @(
    '/i', 'C:\Temp\WatcherDB_Install\WatcherDB_V3.3_Standard.msi', '/qn',
    "SERVICEACCOUNT=$svcAccount",
    "SERVICEPASSWORD=$plainPass",
    '/l*v', 'C:\Temp\wdb_install.log'
)
Remove-Variable plainPass, svcPass -Force
```

### Cenário C — gMSA (banking-grade, sem password)
```powershell
# Pre-req: gMSA criado no AD + computer permission via Get-ADServiceAccount
msiexec /i C:\Temp\WatcherDB_Install\WatcherDB_V3.3_Standard.msi /qn `
        SERVICEACCOUNT="DOMAIN\svc_watcherdb$" `
        /l*v C:\Temp\wdb_install.log
```

**MSI NÃO signed** → SmartScreen pode mostrar warning. Clica "Run anyway" (test scenario apenas).

---

## Fase 5 — Verificar install pós-MSI

```powershell
# Service registrado?
Get-Service WatcherDBWebServiceV33 | Format-List Name, Status, StartType, StartName

# Esperado:
#   Status:    Running
#   StartType: Automatic
#   StartName: NT AUTHORITY\NetworkService (cenário A) ou domain account

# Binário instalado?
Test-Path "C:\Program Files\WatcherDB\V3.3\watcherdb.exe"

# ProgramData criado?
Test-Path C:\ProgramData\WatcherDB\

# Logs?
Get-ChildItem C:\ProgramData\WatcherDB\logs\ | Select-Object Name, LastWriteTime

# Port listening?
netstat -ano | findstr 8433
```

---

## Fase 6 — Configurar SQL connection (se necessário)

Editar `C:\Program Files\WatcherDB\V3.3\.env` (se criado) ou `C:\ProgramData\WatcherDB\.env`:

```ini
# WatcherDB_Intelligence database connection
INTELLIGENCE_SERVER=<sql_host>\<instance>
INTELLIGENCE_DATABASE=WatcherDB_Intelligence
INTELLIGENCE_USER=sql_monitoring
INTELLIGENCE_PASSWORD=<password_from_fase_1>

# Web service port (default 8433)
WEB_PORT=8433

# JWT secret (auto-gerado em install)
JWT_SECRET_KEY=<auto-generated>
```

Restart service após editar:
```powershell
Restart-Service WatcherDBWebServiceV33
```

---

## Fase 7 — Licença (advisory mode VS full features)

### Cenário advisory (sem `license.dat`)
Service corre, dashboards básicos funcionam, mas **features Pro ficam desactivadas**. Suficiente para test inicial.

### Cenário full features (test license.dat)
1. **No target,** extract hardware fingerprint:
   ```powershell
   wmic csproduct get uuid    # BIOS UUID
   wmic cpu get processorid    # CPU ID
   hostname                    # Hostname
   ```

2. **Voltar ao build machine** com esses valores + gerar `license.dat`:
   ```powershell
   .\.venv-build\Scripts\python.exe -m watcherdb.licensing.generator `
       --customer-id $(New-Guid) `
       --expires 2026-08-15 `
       --bios-uuid "<BIOS_UUID_from_target>" `
       --cpu-id "<CPU_ID_from_target>" `
       --hostname "<HOSTNAME_from_target>" `
       --out C:\Temp\license.dat
   ```

3. **Copy `license.dat` para target:**
   ```
   Drop em C:\ProgramData\WatcherDB\license.dat
   Restart-Service WatcherDBWebServiceV33
   ```

4. Verify license loaded:
   ```powershell
   Get-Content C:\ProgramData\WatcherDB\logs\service.log -Tail 20
   # Procurar: "License loaded: <customer_id>" OU "advisory mode"
   ```

---

## Fase 8 — Smoke test pós-install

```powershell
# HTTP health endpoint:
Invoke-RestMethod http://localhost:8433/api/v3/health -TimeoutSec 10

# Portal (browser):
Start-Process "http://localhost:8433/watcherdb"

# Smoke test automatizado (10 phases, manda este script para target):
powershell.exe -ExecutionPolicy Bypass -File tests\smoke\test_install_smoke.ps1 `
    -Scenario 1 -MsiPath C:\Temp\WatcherDB_Install\WatcherDB_V3.3_Standard.msi -SkipSignatureCheck
```

---

## Fase 9 — Rollback (se algo correr mal)

```powershell
# Silent uninstall:
msiexec /x C:\Temp\WatcherDB_Install\WatcherDB_V3.3_Standard.msi /qn /l*v C:\Temp\wdb_uninstall.log

# Verify removido:
Get-Service WatcherDBWebServiceV33 -ErrorAction SilentlyContinue   # deve ser $null
Test-Path "C:\Program Files\WatcherDB\V3.3"                        # deve ser False

# ProgramData PRESERVED por design (S2-7) — logs + license fica:
Test-Path C:\ProgramData\WatcherDB\
# Para cleanup total:
Remove-Item C:\ProgramData\WatcherDB -Recurse -Force
```

---

## Troubleshooting comum

| Problema | Solução |
|---|---|
| SmartScreen bloqueia install | Click "More info" → "Run anyway" (test scenario). Para production: precisa MSI signed. |
| Service não arranca | Check `C:\ProgramData\WatcherDB\logs\service.log` (last 50 lines). |
| `Get-Service` retorna mas Status `Stopped` | Service account sem permissão SQL Server OU `.env` mal configurado. |
| Port 8433 conflict | Outro serviço usa porta. Pode customizar via MSI property `WEBPORT=<other>` no install. |
| `License validation failed` em log | Hardware fingerprint do target não corresponde ao `license.dat`. Re-gerar com fingerprint correcto. |
| Portal load mostra "empty data" | `WatcherDB_Intelligence` DB não tem dados — V1 Intel collector precisa correr primeiro. |

---

## Referências

- Preflight: `deploy/preflight_target.ps1`
- Smoke test: `tests/smoke/test_install_smoke.ps1`
- Installer MSI: `dist/msi/WatcherDB_V3.3_Standard.msi`
- License generation: `watcherdb/licensing/generator.py`
- Audit ref: 2026-05-12 (security-auditor F-SEC-001 — Ed25519 key encryption)

**Doc status:** Test scenario guide. Para production: ver `docs/external/standard/INSTALL_GUIDE.md` (a criar com EULA + signing).
