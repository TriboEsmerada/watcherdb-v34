# WatcherDB V3.3 Standard Edition — MSI build & deploy

Operator reference for the WiX v3 installer. Read this before the first
MSI build on a new workstation and before shipping an MSI to a customer.

## Files in this folder

| File | Purpose | Tracked? |
|---|---|---|
| `Product.wxs` | Main WiX document — directories, components, service, UI. | Yes |
| `Variables.wxi` | Single source of truth for product metadata (version, UpgradeCode, service name, paths). | Yes |
| `license.rtf` | EULA shown in the installer UI. **Placeholder** until legal ships the final text. | Yes |
| `BundleFiles.wxs` | Auto-generated harvest of `dist\watcherdb\` by `heat.exe`. | No (`.gitignore`) |

## One-off setup on a build workstation

1. Install **WiX Toolset v3** from <https://github.com/wixtoolset/wix3/releases>
   (the `.exe` or `.msi` installer — both register `candle.exe`, `light.exe`,
   `heat.exe` on PATH).
2. Re-open the shell so the new PATH entry is picked up.
3. Confirm the three tools resolve:
   ```powershell
   Get-Command candle.exe, light.exe, heat.exe
   ```

## Build workflow

```powershell
cd C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3

# 1. PyArmor Pro + PyInstaller onedir (Sem 2 pipeline).
python deploy\build.py

# 2. MSI installer from the fresh bundle.
pwsh deploy\build_msi.ps1
#    or with a clean slate:
pwsh deploy\build_msi.ps1 -Clean
```

Output: `dist\msi\WatcherDB_V3.3_Standard.msi`.

## Service account configuration (S2-6, audit 2026-04-22)

A partir de Sprint 2, o MSI expõe duas public properties para configurar a conta Windows sob a qual o serviço corre:

| Property | Default | Descrição |
|----------|---------|-----------|
| `SERVICEACCOUNT` | `NT AUTHORITY\NetworkService` | Conta Windows para o serviço. |
| `SERVICEPASSWORD` | _(vazio)_ | Password da conta. Marcada `Hidden="yes"` — não aparece em `/l*v` logs. |

**Cenário 1 — Install default (ambientes não-AD com SQL local):**
```powershell
msiexec /i dist\msi\WatcherDB_V3.3_Standard.msi /qn /l*v install.log
```
Serviço corre como `NetworkService`. Adequado se o SQL Server local aceita `MACHINE$` via Windows Auth.

**Cenário 2 — Banking/DORA com domain service account:**
```powershell
# Use SecureString + ScriptBlock para não deixar password no cmd history.
$pwd = Read-Host -AsSecureString "svc_watcherdb password"
$plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd))
Start-Process -Wait msiexec -ArgumentList @(
    '/i', 'dist\msi\WatcherDB_V3.3_Standard.msi', '/qn',
    'SERVICEACCOUNT="DOMAIN\svc_watcherdb_v33"',
    "SERVICEPASSWORD=$plain",
    '/l*v', 'install.log'
)
Remove-Variable plain, pwd
```

**Cenário 3 — gMSA (Group Managed Service Account, recomendado em banking):**
```powershell
msiexec /i dist\msi\WatcherDB_V3.3_Standard.msi /qn `
        SERVICEACCOUNT="DOMAIN\svc_watcherdb$" `
        /l*v install.log
```
Nenhuma password necessária — SCM resolve via AD.

**Pré-requisitos da service account (todos os cenários 2 e 3):**
- "Log on as a service" right concedido via GPO ou Local Security Policy
- SQL login com `db_datareader` + `VIEW SERVER STATE` + `VIEW DATABASE STATE` nos servidores monitorizados
- Zero permissões elevadas no host onde o WatcherDB corre

## Testing install / uninstall

Silent install (default account):
```powershell
msiexec /i dist\msi\WatcherDB_V3.3_Standard.msi /qn /l*v dist\msi\install.log
```

Verify:
```powershell
Get-Service WatcherDBWebServiceV33 | Format-List Name, Status, StartType
Get-CimInstance Win32_Service -Filter "Name='WatcherDBWebServiceV33'" |
    Select-Object Name, StartName   # confirma SERVICEACCOUNT aplicado
Test-Path 'C:\Program Files\WatcherDB\V3.3\watcherdb.exe'
Test-Path 'C:\ProgramData\WatcherDB'
```

Silent uninstall:
```powershell
msiexec /x dist\msi\WatcherDB_V3.3_Standard.msi /qn /l*v dist\msi\uninstall.log
```

**Nota S2-7:** `C:\ProgramData\WatcherDB\` (license + logs + config) **não** é removido em uninstall. Limpeza total requer procedimento manual separado:
```powershell
Remove-Item -Recurse -Force 'C:\ProgramData\WatcherDB'
```

`C:\ProgramData\WatcherDB\` is **preserved** on uninstall by design — customer
logs and `license.dat` survive an upgrade cycle.

## What the MSI does not do

- It **never** touches SQL Server objects. The `WatcherDB_Intelligence` database
  is shared with V5 Pro and owned by V1 Intel; schema migrations there are
  driven by V1 Intel's own deployment flow, not by this installer.
- It does not enable Standard Edition features without a valid `license.dat`.
  A missing or invalid licence leaves the service running in **advisory mode**
  (the Sem 1 licensing default) — the service starts, but the feature
  registry is empty. Drop a signed `license.dat` in `C:\ProgramData\WatcherDB\`
  and restart the service to activate features.

## Before shipping to a customer

- [ ] Replace `license.rtf` with the final, legally reviewed EULA.
- [ ] Bump `ProductVersion` in `Variables.wxi` if the release changed.
      `UpgradeCode` must stay the same across 3.3.x releases.
- [ ] Confirm the PyInstaller bundle boots (`pytest tests/unit/test_pyinstaller_boot.py`).
- [ ] Sign the MSI (Sem 4 — signtool + EV code-signing certificate).
- [ ] Produce a SBOM alongside the MSI (Sem 4 — CycloneDX via syft).

## Troubleshooting

**heat.exe emits a "duplicate GUID" warning across builds.**
Expected on first run without `-suid`. The script already passes `-suid`; if
you still see reshuffling, delete `deploy\msi\BundleFiles.wxs` and retry.

**light.exe fails with ICE80 / 64-bit mixing errors.**
Product.wxs declares `Platform="x64"`. If you intentionally build for 32-bit,
edit both `Platform` and the `ProgramFiles64Folder` reference.

**The service does not start after install.**
Check `C:\ProgramData\WatcherDB\` is writable by `LocalSystem` and that port
8433 is free. Review `logs\service.log` inside the data folder. If the
service logs `Licence validation failed (advisory): ...` the install is
working — that message is expected until a real `license.dat` is dropped in.
