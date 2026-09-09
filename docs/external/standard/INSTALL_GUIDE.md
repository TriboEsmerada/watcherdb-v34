# WatcherDB V3.3 Standard Edition — Installation Guide

Guia oficial de instalacao para o tecnico responsavel pelo deploy no servidor do cliente. Este documento foi criado em Sprint 2 (audit 2026-04-22, item S2-10) e substitui os scripts deprecados `install_wizard.py`, `install_watcherdb.ps1`, `install_production.ps1`.

**Artefacto canonico:** `WatcherDB_V3.3_Standard.msi` (Authenticode-signed, SBOM incluido)
**Audiencia:** Tecnico do cliente com permissao de administrador local + acesso a conta de servico AD do cliente.
**Tempo estimado:** 30-45 minutos para install limpo + 15 min validacao pos-install.

---

## Indice

1. [Pre-requisitos](#1-pre-requisitos)
2. [Preparar a service account](#2-preparar-a-service-account)
3. [Instalar o MSI](#3-instalar-o-msi)
4. [Activar a licenca](#4-activar-a-licenca)
5. [Verificacao pos-install](#5-verificacao-pos-install)
6. [Silent install para automacao SCCM/Intune/Ansible](#6-silent-install-para-automacao-sccmintuneansible)
7. [Upgrade in-place](#7-upgrade-in-place)
8. [Migracao de instalacao legacy pywin32 para MSI](#8-migracao-de-instalacao-legacy-pywin32-para-msi)
9. [Rollback / uninstall](#9-rollback--uninstall)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Pre-requisitos

### 1.1. Servidor alvo

| Recurso | Requisito |
|---------|-----------|
| Sistema operativo | Windows Server 2019 ou 2022 (x64), Windows 10/11 Pro/Enterprise x64 |
| Permissoes | Administrador local para executar o MSI |
| RAM | 8 GB minimo, 16 GB recomendado |
| CPU | 4 cores minimo, 8 recomendado |
| Disco | 10 GB livres em `C:\Program Files` + 5 GB em `C:\ProgramData` (logs crescem) |
| .NET | Framework 4.8 (incluido em Windows Server 2019+ por default) |

### 1.2. Driver ODBC SQL Server

O WatcherDB usa pyodbc para aceder aos servidores SQL monitorizados. Instalar em PRIMEIRO lugar (antes do MSI):

- Microsoft ODBC Driver 17 ou 18 for SQL Server (x64)
- Download oficial: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

Confirmar instalacao:
```powershell
Get-OdbcDriver | Where-Object { $_.Name -like "*SQL Server*" }
```
Output esperado: `ODBC Driver 17 for SQL Server` ou `ODBC Driver 18 for SQL Server` com `Platform : 64-bit`.

### 1.3. Firewall

Libertar a porta **8433** inbound para o segmento de rede dos DBAs / consolas de monitorizacao:
```powershell
New-NetFirewallRule -DisplayName "WatcherDB V3.3 Portal" `
                    -Direction Inbound -LocalPort 8433 `
                    -Protocol TCP -Action Allow `
                    -RemoteAddress "10.0.0.0/8"  # ajustar a subnet real
```
**Nao expor a Internet.** O portal nao tem rate-limiting DDoS-grade — e produto interno.

### 1.4. SQL Server access

A service account (ver seccao 2) vai precisar de login SQL com permissoes minimas nos servidores monitorizados:

Execute, em **cada** SQL Server que o WatcherDB vai monitorizar, o script canonico
`docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql` (login SQL `sql_monitoring`, ja criado) ou
`docs/security/LEAST_PRIVILEGE_SETUP.sql` (cria um login novo; substituir os placeholders). Conjunto
de permissoes, identico nos dois e validado em producao (2026-09-08):

| Ambito | Permissao | Para que |
|---|---|---|
| servidor | `VIEW SERVER STATE`, `VIEW ANY DEFINITION`, `VIEW ANY DATABASE` | DMVs, metadata, enumeracao de BDs |
| master | `EXECUTE ON sys.xp_readerrorlog`, `SHOWPLAN` | error log, planos de execucao |
| msdb | `SELECT` em `backupset`/`backupmedia*`/`backupfile`/`sysjob*`/`sysschedules`/`sysoperators`/`syscategories`, `EXECUTE sp_help_jobactivity`, membro de `SQLAgentReaderRole` | backups e jobs |

Para muitas instancias de uma vez: SSMS > View > Registered Servers > grupo com as instancias >
New Query sobre o grupo (o script corre em todas com a sua sessao de administracao). Validar
depois como `sql_monitoring`: a ultima query do script devolve 1 linha por instancia, tudo a 1 e
`sysadmin = 0`. Compativel de SQL Server 2005 a 2022.

**NUNCA conceder `sysadmin`, `db_owner` ou permissoes elevadas.** Banking audit (SOC 2 / DORA / ISO 27001) vai pedir evidencia do least-privilege.

---

## 2. Preparar a service account

### 2.1. Cenarios suportados

| Cenario | Conta | Recomendado para |
|---------|-------|------------------|
| **A — Default** | `NT AUTHORITY\NetworkService` | Ambientes nao-AD com SQL local, lab, avaliacao |
| **B — Domain account** | `DOMAIN\svc_watcherdb_v33` + password | Producao geral |
| **C — gMSA** (recomendado banking) | `DOMAIN\svc_watcherdb_v33$` (sem password) | Banking, DORA, zero-trust |

### 2.2. Criar domain account (cenario B)

1. Active Directory Users and Computers -> criar user `svc_watcherdb_v33` em OU apropriada (ex: `Service Accounts`).
2. Password:
   - Comprimento minimo 16 chars
   - Complex (letras + digitos + simbolos)
   - "Password never expires" (service accounts) OU rotacao controlada por vault corporativo
3. Disable "User must change password at next logon".

### 2.3. Criar gMSA (cenario C — recomendado)

No PDC Emulator do dominio:
```powershell
# Uma vez por dominio:
Add-KdsRootKey -EffectiveImmediately

# Criar o gMSA:
New-ADServiceAccount -Name "svc_watcherdb_v33" `
                     -DNSHostName "svc_watcherdb_v33.your-domain.local" `
                     -PrincipalsAllowedToRetrieveManagedPassword "WatcherDBServers"

# Criar o grupo AD que pode usar o gMSA e adicionar o servidor:
New-ADGroup -Name "WatcherDBServers" -GroupScope Global
Add-ADGroupMember "WatcherDBServers" -Members "SERVERNAME$"
```

No servidor alvo (apos reboot para o group membership entrar em vigor):
```powershell
# Teste que o servidor consegue usar o gMSA:
Test-ADServiceAccount svc_watcherdb_v33
# Output: True
```

### 2.4. Conceder "Log on as a service"

**Aplicavel a cenarios B e C.** Metodo GPO (preferido em banking):
1. Group Policy Management -> criar GPO "WatcherDB Service Account Rights"
2. Computer Configuration -> Policies -> Windows Settings -> Security Settings -> Local Policies -> User Rights Assignment
3. "Log on as a service" -> Add `DOMAIN\svc_watcherdb_v33` (ou `DOMAIN\svc_watcherdb_v33$` para gMSA)
4. Link o GPO ao OU dos servidores WatcherDB + `gpupdate /force` no servidor

Metodo local (se GPO nao for opcao):
```powershell
# Local Security Policy -> Local Policies -> User Rights Assignment
# -> Log on as a service -> Add User/Group
```

### 2.5. ACLs em `C:\ProgramData\WatcherDB\`

Apos install (seccao 3), o MSI cria `C:\ProgramData\WatcherDB\` com SYSTEM + Administrators full control. A service account vai precisar de acesso:

```powershell
$account = "DOMAIN\svc_watcherdb_v33"  # ou "DOMAIN\svc_watcherdb_v33$" para gMSA
$path = "C:\ProgramData\WatcherDB"
icacls $path /grant "${account}:(OI)(CI)(M)" /T  # Modify na pasta + recursivo
```

---

## 3. Instalar o MSI

### 3.1. Cenario A — Install default (NetworkService)

```powershell
msiexec /i "C:\Path\To\WatcherDB_V3.3_Standard.msi" /qn /l*v "C:\Temp\watcherdb_install.log"
```

### 3.2. Cenario B — Install com domain account

**NUNCA** passe password em plaintext na linha de comando (cmd history preserva). Use sempre `SecureString`:

```powershell
# Pedir password interactivamente (nao entra no cmd history)
$secure = Read-Host -AsSecureString "Password de DOMAIN\svc_watcherdb_v33"
$plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

Start-Process -Wait msiexec -ArgumentList @(
    '/i', 'C:\Path\To\WatcherDB_V3.3_Standard.msi', '/qn',
    'SERVICEACCOUNT="DOMAIN\svc_watcherdb_v33"',
    "SERVICEPASSWORD=$plain",
    '/l*v', 'C:\Temp\watcherdb_install.log'
)

# Limpar password da memoria
Remove-Variable plain, secure
[GC]::Collect()
```

O `Hidden="yes"` na property SERVICEPASSWORD impede que a password apareca no ficheiro `watcherdb_install.log`.

### 3.3. Cenario C — Install com gMSA (sem password)

```powershell
msiexec /i "C:\Path\To\WatcherDB_V3.3_Standard.msi" /qn `
        SERVICEACCOUNT="DOMAIN\svc_watcherdb_v33`$" `
        /l*v "C:\Temp\watcherdb_install.log"
```

O SCM resolve automaticamente a password do gMSA via AD.

---

## 4. Activar a licenca

### 4.1. Obter `license.dat`

A licenca e fornecida pelo vendor apos compra. Esta bound a **fingerprint do host** (hash de componentes imutaveis do hardware + SID da maquina). Nao pode ser movida entre servidores.

Ver [LICENSE_ACTIVATION.md](LICENSE_ACTIVATION.md) (documento separado) para o procedimento de obtencao da licenca, incluindo o comando de export do fingerprint:
```powershell
& "C:\Program Files\WatcherDB\V3.3\watcherdb.exe" --export-fingerprint > fingerprint.txt
# Enviar fingerprint.txt ao vendor
```

### 4.2. Instalar `license.dat`

```powershell
Copy-Item "C:\Temp\license.dat" "C:\ProgramData\WatcherDB\license.dat"
icacls "C:\ProgramData\WatcherDB\license.dat" /grant "DOMAIN\svc_watcherdb_v33:(R)"
Restart-Service WatcherDBWebServiceV33
```

### 4.3. Confirmar activacao

```powershell
Invoke-WebRequest "http://localhost:8433/api/v3/health" -UseBasicParsing |
    Select-Object -ExpandProperty Content
```

Output esperado (campo `license`):
```json
{ "status": "ok", "license": "valid", ... }
```

Se `license: advisory`, o produto corre em modo degraded (features limitadas). Se `license: invalid` ou ausente, o servico nao devolve dados.

---

## 5. Verificacao pos-install

Execute este checklist no servidor apos install. Todos os 8 passos devem passar.

```powershell
Write-Host "=== WatcherDB V3.3 post-install verification ==="

# 1. Servico Windows registado e a correr
Get-Service WatcherDBWebServiceV33 | Format-List Name, Status, StartType, StartName
# Esperado: Status=Running, StartType=Automatic, StartName=<a conta configurada>

# 2. Binarios no sitio certo
Test-Path 'C:\Program Files\WatcherDB\V3.3\watcherdb.exe'    # True
Test-Path 'C:\Program Files\WatcherDB\V3.3\VERSION.txt'      # True
Get-Content 'C:\Program Files\WatcherDB\V3.3\VERSION.txt'
# Esperado: header "WatcherDB V3.3 Standard Edition" + version 3.3.0.0

# 3. ProgramData criado com permissoes correctas
Test-Path 'C:\ProgramData\WatcherDB'                          # True
(Get-Acl 'C:\ProgramData\WatcherDB').Access |
    Select-Object IdentityReference, FileSystemRights |
    Format-Table -AutoSize
# Esperado: SYSTEM + Administrators FullControl + <service account> Modify

# 4. Licenca activada
(Invoke-WebRequest "http://localhost:8433/api/v3/health" -UseBasicParsing).Content
# Esperado: status=ok, license=valid

# 5. Porta 8433 a escutar
Test-NetConnection localhost -Port 8433
# Esperado: TcpTestSucceeded: True

# 6. Log file escrito recentemente
Get-ChildItem 'C:\ProgramData\WatcherDB\logs\' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 3 | Format-Table Name, LastWriteTime
# Esperado: pelo menos 1 ficheiro watcherdb_main.log de ha minutos

# 7. Service account efectivo
Get-CimInstance Win32_Service -Filter "Name='WatcherDBWebServiceV33'" |
    Select-Object Name, StartName, State
# Esperado: StartName = a conta que passou em SERVICEACCOUNT

# 8. Portal web responde
(Invoke-WebRequest "http://localhost:8433/" -UseBasicParsing).StatusCode
# Esperado: 200
```

Se qualquer passo falhar, ir directamente para [Troubleshooting](#10-troubleshooting).

---

## 6. Silent install para automacao SCCM/Intune/Ansible

### 6.1. SCCM / MECM package

Propriedades do package:
- Source: `\\shared\packages\WatcherDB\V3.3\`
- Command: `msiexec /i "WatcherDB_V3.3_Standard.msi" /qn SERVICEACCOUNT="%SERVICEACCOUNT%" /l*v "C:\Windows\Temp\watcherdb.log"`
- Environment variables: `SERVICEACCOUNT` definido no collection variable

### 6.2. Intune Win32 app

Install command:
```
msiexec /i "WatcherDB_V3.3_Standard.msi" /qn SERVICEACCOUNT="NT AUTHORITY\NetworkService"
```

Uninstall command:
```
msiexec /x "{PRODUCT-GUID-FROM-MSI}" /qn
```

Detection rule: file `C:\Program Files\WatcherDB\V3.3\watcherdb.exe` exists + version >= 3.3.0.0.

### 6.3. Ansible playbook (win_package module)

```yaml
- name: Install WatcherDB V3.3 Standard
  win_package:
    path: \\share\packages\WatcherDB_V3.3_Standard.msi
    arguments: 'SERVICEACCOUNT="DOMAIN\svc_watcherdb_v33$"'
    state: present
    product_id: "{PRODUCT-GUID-FROM-MSI}"
  vars:
    ansible_become: true
    ansible_become_method: runas
```

---

## 7. Upgrade in-place

O MSI suporta upgrade automatico via `MajorUpgrade` — o installer novo detecta a instalacao anterior (mesmo `UpgradeCode`) e substitui-a.

```powershell
# Parar servico antes (opcional — MSI forca stop de qualquer forma)
Stop-Service WatcherDBWebServiceV33

# Install nova versao (usa o SERVICEACCOUNT da instalacao anterior)
msiexec /i "WatcherDB_V3.3.1_Standard.msi" /qn /l*v "C:\Temp\upgrade.log"

# Validar
Get-Service WatcherDBWebServiceV33
Get-Content 'C:\Program Files\WatcherDB\V3.3\VERSION.txt'
```

**Garantia S2-7:** `C:\ProgramData\WatcherDB\` (license + logs + config) e preservado durante upgrade. O MSI actual nao tem `<RemoveFolder>` nesta pasta — customer data sobrevive.

---

## 8. Migracao de instalacao legacy pywin32 para MSI

Servidores onde o WatcherDB foi instalado via script legacy (`install_and_start.bat`, `install_wizard.py`, `install_watcherdb.ps1`, `install_production.ps1` — todos deprecados em S2-8) tem o servico `WatcherDBWebServiceV33` registado no SCM mas **sem entrada MSI no Add/Remove Programs**.

O MSI novo nao detecta esta instalacao legacy — instalar directamente cria um segundo servico + bundle paralelo. Seguir esta sequencia:

```powershell
# 1. Parar e remover o servico legacy
Stop-Service WatcherDBWebServiceV33 -Force
sc.exe delete WatcherDBWebServiceV33

# 2. Backup do ProgramData (precaucao)
Copy-Item -Recurse "C:\ProgramData\WatcherDB" "C:\ProgramData\WatcherDB.bak.$(Get-Date -Format 'yyyyMMdd')"

# 3. Remover binarios legacy (NAO tocar no ProgramData)
Remove-Item -Recurse -Force "C:\WatcherDB"  # ou o path onde estava instalado legacy

# 4. Install do MSI limpo
msiexec /i "WatcherDB_V3.3_Standard.msi" /qn `
        SERVICEACCOUNT="DOMAIN\svc_watcherdb_v33`$" `
        /l*v "C:\Temp\migration.log"

# 5. Validar (seccao 5)
```

O `ProgramData\WatcherDB` legacy (com license.dat + logs) e reutilizado pelo MSI — configuracao e historico preservados.

---

## 9. Rollback / uninstall

### 9.1. Uninstall do MSI

```powershell
# Via MSI product code (extrair do install.log)
msiexec /x "{PRODUCT-GUID}" /qn /l*v "C:\Temp\uninstall.log"

# Ou via WMI (descobre automaticamente)
Get-CimInstance Win32_Product -Filter "Name LIKE 'WatcherDB V3.3%'" |
    Invoke-CimMethod -MethodName Uninstall
```

O uninstall **preserva** `C:\ProgramData\WatcherDB\` (license + logs + config). Isto foi decisao explicita em audit S2-7 para proteger customer data em upgrades.

### 9.2. Limpeza total (apos uninstall confirmado)

Se quiser remover tudo incluindo license + logs:

```powershell
Remove-Item -Recurse -Force "C:\ProgramData\WatcherDB"
```

**CUIDADO:** esta accao e irreversivel e apaga a licenca. Para re-instalar vai precisar de obter novo `license.dat` do vendor (fingerprint pode nao coincidir se o hardware mudou).

### 9.3. Rollback parcial durante install

Se o MSI falhar a meio, o rollback automatico do Windows Installer reverte tudo:
```powershell
# Verificar se ficou estado parcial
Get-Service WatcherDBWebServiceV33 -ErrorAction SilentlyContinue
Test-Path 'C:\Program Files\WatcherDB\V3.3'

# Se ficou qualquer coisa, ver install.log + abrir ticket
```

---

## 10. Troubleshooting

### 10.1. Servico nao inicia apos install (erro 1067)

Sintoma: `Get-Service` mostra `Stopped`, Event Viewer (System log, source `Service Control Manager`) reporta "The process terminated unexpectedly".

Causas comuns + diagnostico:

```powershell
# 1. Conta de servico sem "Log on as a service" right
# Verificar:
secedit /export /cfg C:\Temp\sec.cfg
Select-String -Path C:\Temp\sec.cfg -Pattern "SeServiceLogonRight"
# Output: SeServiceLogonRight = *S-1-5-...,<deve conter SID da conta>

# 2. ODBC Driver ausente
Get-OdbcDriver | Where-Object { $_.Name -like "*SQL Server*" }
# Se vazio, instalar: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

# 3. Porta 8433 ocupada
netstat -ano | Select-String ":8433"
# Se outro PID esta a usar, reconfigurar (ver 10.3)

# 4. License ausente
Test-Path 'C:\ProgramData\WatcherDB\license.dat'

# 5. Ver log principal
Get-Content 'C:\ProgramData\WatcherDB\logs\watcherdb_main.log' -Tail 100
```

### 10.2. Portal retorna 503 em `/api/v3/health`

Sintoma: o servico esta Running mas o endpoint de health devolve `{"status":"error",...}`.

Diagnostico rapido:
```powershell
$health = (Invoke-WebRequest "http://localhost:8433/api/v3/health" -UseBasicParsing).Content | ConvertFrom-Json
$health | Format-List *
# Pistas nos campos: database, collector, license, intelligence_pool
```

Causas:
- `database: unreachable` — a BD partilhada WatcherDB_Intelligence nao responde. Ver 10.4.
- `collector: inactive` — V1 collector nao alimenta dados. Ver 10.5.
- `license: invalid` — re-colocar `license.dat` (seccao 4).

### 10.3. Mudar a porta 8433

Se 8433 estiver ocupada no servidor, definir a variavel `WATCHERDB_PORT` no
`.env` de dados (`C:\ProgramData\WatcherDB\.env`) — o servico le' a porta daqui;
o ficheiro `services\web_service\config.yaml` NAO e' lido pelo servico instalado:
```ini
WATCHERDB_PORT=8434     # porta alternativa
```
Reiniciar servico + actualizar firewall rule. Confirmar com
`GET /api/version` (autenticado) que o servico reiniciou com o build esperado.

### 10.3-bis. Activar HTTPS (TLS directo no servico)

O servico serve HTTP por defeito. Para TLS, colocar o certificado (emitido pela CA
interna, formato PEM — nao PFX) e a chave privada numa pasta com ACL restrita e
apontar no mesmo `.env`:
```ini
WATCHERDB_TLS_CERT=C:\ProgramData\WatcherDB\certs\watcherdb.crt.pem
WATCHERDB_TLS_KEY=C:\ProgramData\WatcherDB\certs\watcherdb.key.pem
```
Reiniciar servico. Com ambas definidas e legiveis, o servico responde SO em
`https://<host>:8433` (HTTP deixa de responder nessa porta — nao ha' redirect);
sem elas, ou com ficheiro em falta, volta a HTTP e regista `TLS: OFF` no Event
Log / `service_stdout.log`. Rollback = remover as duas linhas + reiniciar.

### 10.4. BD WatcherDB_Intelligence inacessivel

A V3.3 depende da BD partilhada `WatcherDB_Intelligence` (alimentada pelo V1 Intelligence Collector via Task Scheduler). Se inacessivel:

```sql
-- Testar conectividade SQL
SELECT @@SERVERNAME, DB_NAME();
USE WatcherDB_Intelligence;
SELECT COUNT(*) FROM KPI_STG_ACTIVE_TABLE WITH (NOLOCK);  -- deve devolver 1 linha
```

Se a query falha, verificar:
- A conta de servico do WatcherDB tem acesso a WatcherDB_Intelligence? (seccao 1.4)
- O Task Scheduler `WatcherDB_Intelligence_Collector` esta a correr? `schtasks /query /tn "WatcherDB_Intelligence_Collector" /fo LIST`
- Encadeamento BLUE/GREEN das tabelas STG esta consistente? (pedir suporte ao vendor)

### 10.5. AD bind falha

Sintoma: login com credenciais AD devolve "Invalid credentials" mesmo com password correcta.

Diagnostico:
```powershell
# 1. Confirmar que config.yaml aponta para o dominio certo
Get-Content 'C:\Program Files\WatcherDB\V3.3\services\web_service\config.yaml' |
    Select-String -Pattern "domain:|server:|base_dn:"

# 2. Testar LDAP bind manualmente
Test-NetConnection dc01.your-domain.local -Port 636  # LDAPS
Test-NetConnection dc01.your-domain.local -Port 389  # LDAP

# 3. Ver log auth
Select-String -Path 'C:\ProgramData\WatcherDB\logs\auth.log' -Pattern "LDAP|bind"
```

Causas comuns:
- `server:` em `config.yaml` aponta para dominio errado (template default era `tapnet.tap.pt`, vendor removeu em S2-9 — confirmar que cliente editou para o proprio dominio)
- Firewall entre servidor WatcherDB e domain controller bloqueia 389/636
- Service account sem permissao LDAP read

### 10.6. Abrir ticket de suporte

Quando esgotar o troubleshooting, enviar ao vendor:

1. `C:\Temp\watcherdb_install.log` (ultima execucao msiexec com /l*v)
2. `C:\ProgramData\WatcherDB\logs\watcherdb_main.log` (ultimas 200 linhas)
3. Output de:
   ```powershell
   Get-Service WatcherDBWebServiceV33 | Format-List *
   Get-CimInstance Win32_Service -Filter "Name='WatcherDBWebServiceV33'"
   Get-Content 'C:\Program Files\WatcherDB\V3.3\VERSION.txt'
   ```
4. Descricao do comportamento esperado vs observado
5. Versao do Windows, service pack, roles/features instaladas

---

## Apendices

- [A. Architecture Overview](../../architecture/)  (em desenvolvimento)
- [B. Security & Compliance Posture](../../guides/USER_GUIDE_PT.md#anexo-a-security--compliance-posture-para-it-director--ciso)
- [C. Upgrade Path para WatcherDB Pro (V5/V5.5)](../../guides/USER_GUIDE_PT.md#anexo-b-upgrade-path-watcherdb-pro)
- [D. Manual do Utilizador (completo PT)](../../guides/USER_GUIDE_PT.md)
- [E. Manual Simplificado (DBA junior)](../../guides/MANUAL_SIMPLIFICADO_PT.md)

---

**WatcherDB V3.3 Standard Edition — Installation Guide**

Documento publicado em 22 de Abril de 2026 (audit S2-10).
Para correcoes ou sugestoes sobre este guia, contactar suporte comercial do vendor.
