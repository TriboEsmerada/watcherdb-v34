# WatcherDB V3.3 Standard Edition — Release Workflow

End-to-end reference for producing a customer-shipable artefact. Covers
licensing keygen, build, installer, signing, SBOM and verification.

## Pipeline at a glance

```
┌────────────────────────────────────────────────────────────────────┐
│  deploy/generate_license_keys.py   (one-off, Sem 1)                │
│      ↓                                                              │
│  deploy/build.py                   (Sem 0 + 2: PyArmor + PyInstaller)│
│      ↓                                                              │
│  deploy/build_msi.ps1              (Sem 3: WiX MSI)                 │
│      ↓                                                              │
│  deploy/sign_msi.ps1               (Sem 4: Authenticode)            │
│      ↓                                                              │
│  deploy/build_sbom.ps1             (Sem 4: CycloneDX SBOM)          │
│      ↓                                                              │
│  (optional) deploy/updater/        (Sem 4: update package)          │
│                                                                     │
│  dist/msi/WatcherDB_V3.3_Standard.msi        ← signed installer     │
│  dist/msi/*.sbom.cyclonedx.json              ← SBOM                 │
│  dist/update/*.zip + *.manifest.json         ← in-place updater     │
└────────────────────────────────────────────────────────────────────┘
```

## One-off workstation setup

| Tool | Purpose | Install |
|---|---|---|
| Python 3.11+ | Build orchestration | python.org or Microsoft Store |
| PyArmor Pro (reg 011618) | Source obfuscation | `pip install -r requirements-build.txt` (licence pre-activated) |
| PyInstaller 6.x | Frozen bundle | `pip install -r requirements-build.txt` |
| WiX Toolset v3 | MSI builder | <https://github.com/wixtoolset/wix3/releases> |
| Windows SDK Signing Tools | signtool.exe | `winget install Microsoft.WindowsSDK.10.0.22621` (or later) |
| DigiCert KeyLocker Client Tools | EV code-signing via cloud HSM | <https://docs.digicert.com/en/digicert-keylocker.html> |
| Syft | SBOM generator | `winget install Anchore.Syft` |

Then generate the licensing keypair once per product line:
```powershell
python deploy\generate_license_keys.py
#   private -> %USERPROFILE%\.watcherdb-council-secrets\ed25519_private.pem
#   public  -> deploy\keys\ed25519_public.pem  (committed, shipped in bundle)
```

## Per-release workflow

```powershell
cd C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3

# 1. Bump version if needed
#    - deploy/msi/Variables.wxi: ProductVersion
#    - watcherdb_main.py / pyproject.toml if product-facing
#    - UpgradeCode in Variables.wxi STAYS THE SAME across 3.3.x

# 2. Build the bundle
python deploy\build.py

# 3. Smoke-test the bundle
pytest tests/unit/test_license.py tests/unit/test_manifest.py tests/unit/test_pyinstaller_boot.py -v

# 4. Package the MSI
pwsh deploy\build_msi.ps1 -Clean

# 5. Sign the MSI (EV via KeyLocker - preferred)
$env:SM_HOST                  = 'https://clientauth.one.digicert.com'
$env:SM_API_KEY               = '<from DigiCert console>'
$env:SM_CLIENT_CERT_FILE      = 'C:\keylocker\client.p12'
$env:SM_CLIENT_CERT_PASSWORD  = '<secret>'
$env:SM_CERT_ALIAS            = '<alias shown in console>'
pwsh deploy\sign_msi.ps1
#   fallback: pwsh deploy\sign_msi.ps1 -Mode pfx -PfxPath <path> -PfxPassword <SecureString>

# 6. SBOM for the signed release
pwsh deploy\build_sbom.ps1

# 7. Customer licence file (one per customer deployment)
python -m watcherdb.licensing.generator `
    --customer-id <uuid> `
    --expires 2027-04-22 `
    --bios-uuid <from wmic csproduct> `
    --cpu-id <from wmic cpu> `
    --hostname <CUSTOMER_HOST> `
    --out dist\customers\<customer-uuid>\license.dat

# 8. (Optional) Build an update package for an in-place upgrade
python deploy\updater\build_update_package.py `
    --version 3.3.1.0 `
    --min-version 3.3.0.0
```

## Verification before shipment

```powershell
# MSI signature
signtool verify /pa /v dist\msi\WatcherDB_V3.3_Standard.msi

# SBOM sanity (CycloneDX + component count)
Get-Content dist\msi\WatcherDB_V3.3_Standard.sbom.cyclonedx.json |
    ConvertFrom-Json |
    Select-Object bomFormat, specVersion, @{N='components';E={$_.components.Count}}

# Dry-run install on a clean VM snapshot
msiexec /i dist\msi\WatcherDB_V3.3_Standard.msi /qn /l*v install.log
Get-Service WatcherDBWebServiceV33
Invoke-WebRequest http://localhost:8433/api/v3/health -UseBasicParsing
msiexec /x dist\msi\WatcherDB_V3.3_Standard.msi /qn
```

## Customer deployment notes

- Drop the signed `license.dat` in `C:\ProgramData\WatcherDB\` and restart the
  service to activate Standard Edition features. Without it the service runs
  in advisory mode (empty feature registry).
- The `WatcherDB_Intelligence` database is shared with V5 Pro and managed by
  V1 Intel. The MSI never touches it; schema changes for V3.3 come from V1
  Intel's own deployment flow.
- In-place upgrades use the in-place updater (ZIP + signed manifest) for
  minor / patch releases; major version bumps flow through the MSI.

## Where each piece lives

| Sem | Area | Reference |
|---|---|---|
| 0 | Quick wins, BOM sanitiser, pre-commit | commit `9295d58` |
| 1 | Ed25519 licensing, fingerprint, tests | commit `3df6b66`, `watcherdb/licensing/` |
| 2 | PyArmor + PyInstaller spec and orchestrator | `deploy/watcherdb.spec`, `deploy/build.py` |
| 3 | WiX MSI source and orchestrator | `deploy/msi/`, `deploy/build_msi.ps1`, `deploy/msi/README.md` |
| 4 | Signtool / updater / SBOM | `deploy/sign_msi.ps1`, `deploy/updater/`, `deploy/build_sbom.ps1` |

## Known follow-ups for Sem 5+

- Customer-side updater daemon (`watcherdb-updater.exe`) that consumes the
  signed manifest and zip, runs a health-check after extraction and rolls
  back on failure. Sem 4-B shipped the signing/verification primitives but
  not the daemon.
- Replace the placeholder `license.rtf` with the final, legally reviewed
  EULA before the first paying customer.
- Automate the CI build so every tagged release produces an MSI + SBOM
  + update package without operator involvement.
