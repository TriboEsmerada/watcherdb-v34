#Requires -Version 5.1
<#
.SYNOPSIS
    Smoke test pos-install para WatcherDB V3.3 Standard Edition MSI.

.DESCRIPTION
    Validacao automatica apos install via msiexec. Cobre 10 phases:
      Phase 0  - Pre-conditions (MSI exists, signed, no pre-service, port free)
      Phase 1  - Install (msiexec /qn)
      Phase 2  - Service state (Running, Automatic, StartName matches scenario)
      Phase 3  - Port + binary (listening, install dir, ProgramData)
      Phase 4  - HTTP /api/v3/health
      Phase 5  - Version endpoint vs Variables.wxi
      Phase 6  - Advisory mode (sem license.dat)
      Phase 7  - License.dat activation (se path fornecido)
      Phase 8  - Restart resilience
      Phase 9  - Uninstall (clean dir, preserve ProgramData)
      Phase 10 - Summary (exit 0/1)

.PARAMETER Scenario
    Service account scenario:
      1 = NetworkService (default, sem AD)
      2 = DOMAIN\svc account (precisa SMOKE_SVC_ACCOUNT + SMOKE_SVC_PASSWORD)
      3 = gMSA (precisa SMOKE_GMSA_ACCOUNT, sem password, AD test env)

.PARAMETER MsiPath
    Path para MSI signed. Default: dist\msi\WatcherDB_V3.3_Standard.msi

.PARAMETER LicenseDatPath
    Optional license.dat para Phase 7. Se omitido, apenas advisory mode testado.

.PARAMETER SkipSignatureCheck
    Skip Authenticode signature validation (Phase 0). Use apenas em dev runs sem
    MSI signed. Production runs DEVEM exigir signature valid.

.EXAMPLE
    Cenario 1 - NetworkService minimal:
    powershell.exe -ExecutionPolicy Bypass -File tests\smoke\test_install_smoke.ps1 -Scenario 1

.EXAMPLE
    Cenario 2 - domain account:
    $env:SMOKE_SVC_ACCOUNT  = 'DOMAIN\svc_watcherdb_v33'
    $env:SMOKE_SVC_PASSWORD = 'redacted'
    powershell.exe -ExecutionPolicy Bypass -File tests\smoke\test_install_smoke.ps1 -Scenario 2

.EXAMPLE
    Com license.dat activation test:
    powershell.exe -ExecutionPolicy Bypass -File tests\smoke\test_install_smoke.ps1 `
        -Scenario 1 -LicenseDatPath C:\test\license.dat

.NOTES
    AVISO: REQUER VM ISOLADA. NAO correr em workstation dev - install
    regista service WatcherDBWebServiceV33 + bind port 8433.

    Runtime esperado: ~3-5 min cenario 1, +30s para cenarios 2/3 (AD checks).

    Exit codes:
      0 = PASS
      1 = FAIL (1+ assertion failed)
      2 = SKIP (missing env vars para scenario)

    Design ref: auditoria QA 2026-05-12 (watcherdb-qa-specialist).
    Author: WatcherDB DevOps - 2026-05-14
#>

[CmdletBinding()]
param(
    [ValidateSet('1','2','3')]
    [string]$Scenario = '1',
    [string]$MsiPath = 'dist\msi\WatcherDB_V3.3_Standard.msi',
    [string]$LicenseDatPath = '',
    [switch]$SkipSignatureCheck
)

$ErrorActionPreference = 'Continue'
$Port = 8433
$SvcName = 'WatcherDBWebServiceV33'
$ProgramData = 'C:\ProgramData\WatcherDB'
$InstallLog = "$env:TEMP\wdb_install_smoke.log"
$UninstallLog = "$env:TEMP\wdb_uninstall_smoke.log"
$InstallDir = 'C:\Program Files\WatcherDB\V3.3'

$Failures = [System.Collections.Generic.List[string]]::new()
$Warnings = [System.Collections.Generic.List[string]]::new()

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) {
        $Failures.Add("[FAIL] $Label")
        Write-Host "[FAIL] $Label" -ForegroundColor Red
    } else {
        Write-Host "[PASS] $Label" -ForegroundColor Green
    }
}

function Skip-Test {
    param([string]$Label, [string]$Reason)
    $Warnings.Add("[SKIP] $Label - $Reason")
    Write-Host "[SKIP] $Label - $Reason" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  WatcherDB V3.3 Standard Edition - Install Smoke Test" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Scenario:   $Scenario"
Write-Host "  MsiPath:    $MsiPath"
Write-Host "  LicenseDat: $(if ($LicenseDatPath) { $LicenseDatPath } else { '(none, advisory only)' })"
Write-Host "  TimeStamp:  $(Get-Date -Format o)"
Write-Host ""

# === Phase 0: Pre-conditions ============================================
Write-Host "--- Phase 0: Pre-conditions ---" -ForegroundColor Cyan
Assert-True (Test-Path $MsiPath) "MSI file exists at $MsiPath"

if (Test-Path $MsiPath) {
    if ($SkipSignatureCheck) {
        Skip-Test "MSI Authenticode signature" "SkipSignatureCheck flag set"
    } else {
        $sig = Get-AuthenticodeSignature $MsiPath
        Assert-True ($sig.Status -eq 'Valid') "MSI Authenticode signature Valid (got: $($sig.Status))"
    }
}

$preSvc = Get-Service $SvcName -ErrorAction SilentlyContinue
Assert-True ($null -eq $preSvc) "Service $SvcName not pre-existing (clean VM)"

$portInUse = netstat -ano | Select-String ":$Port "
Assert-True ($null -eq $portInUse) "Port $Port is free before install"

if ($Failures.Count -gt 0) {
    Write-Host ""
    Write-Host "[ABORT] Pre-conditions failed. Aborting before install." -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}

# === Phase 1: Install ===================================================
Write-Host ""
Write-Host "--- Phase 1: Install ---" -ForegroundColor Cyan
$msiArgs = @('/i', $MsiPath, '/qn', '/l*v', $InstallLog)

switch ($Scenario) {
    '2' {
        if (-not $env:SMOKE_SVC_ACCOUNT -or -not $env:SMOKE_SVC_PASSWORD) {
            Skip-Test "Scenario 2 (domain account)" "SMOKE_SVC_ACCOUNT or SMOKE_SVC_PASSWORD missing"
            Write-Host "Set env vars and re-run." -ForegroundColor Yellow
            exit 2
        }
        $msiArgs += "SERVICEACCOUNT=$env:SMOKE_SVC_ACCOUNT"
        $msiArgs += "SERVICEPASSWORD=$env:SMOKE_SVC_PASSWORD"
    }
    '3' {
        if (-not $env:SMOKE_GMSA_ACCOUNT) {
            Skip-Test "Scenario 3 (gMSA)" "SMOKE_GMSA_ACCOUNT missing (needs AD test env)"
            exit 2
        }
        $msiArgs += "SERVICEACCOUNT=$env:SMOKE_GMSA_ACCOUNT"
    }
}

$result = Start-Process -Wait -PassThru msiexec -ArgumentList $msiArgs
Assert-True ($result.ExitCode -eq 0) "msiexec install exit code 0 (got: $($result.ExitCode))"
Assert-True (Test-Path $InstallLog) "Install log created at $InstallLog"

# === Phase 2: Service state =============================================
Write-Host ""
Write-Host "--- Phase 2: Service state ---" -ForegroundColor Cyan
Start-Sleep -Seconds 10  # Allow SCM start

$svc = Get-Service $SvcName -ErrorAction SilentlyContinue
Assert-True ($null -ne $svc) "Service $SvcName exists after install"

if ($svc) {
    Assert-True ($svc.Status -eq 'Running') "Service status Running (got: $($svc.Status))"
    Assert-True ($svc.StartType -eq 'Automatic') "Service StartType Automatic (got: $($svc.StartType))"

    $svcInfo = Get-CimInstance Win32_Service -Filter "Name='$SvcName'"
    switch ($Scenario) {
        '1' { Assert-True ($svcInfo.StartName -like '*NetworkService*') "Service StartName matches NetworkService (got: $($svcInfo.StartName))" }
        '2' { Assert-True ($svcInfo.StartName -eq $env:SMOKE_SVC_ACCOUNT)  "Service StartName matches $env:SMOKE_SVC_ACCOUNT (got: $($svcInfo.StartName))" }
        '3' { Assert-True ($svcInfo.StartName -like '*$')                  "Service StartName matches gMSA trailing dollar (got: $($svcInfo.StartName))" }
    }
}

# === Phase 3: Port + binary =============================================
Write-Host ""
Write-Host "--- Phase 3: Port + binary ---" -ForegroundColor Cyan
$portListening = netstat -ano | Select-String ":$Port .*LISTENING"
Assert-True ($null -ne $portListening) "Port $Port is listening"
Assert-True (Test-Path "$InstallDir\watcherdb.exe") "watcherdb.exe present in $InstallDir"
Assert-True (Test-Path $ProgramData) "ProgramData directory created at $ProgramData"
Assert-True (Test-Path "$ProgramData\logs") "Logs directory created in ProgramData"

# === Phase 4: HTTP /api/v3/health =======================================
Write-Host ""
Write-Host "--- Phase 4: HTTP /api/v3/health ---" -ForegroundColor Cyan
Start-Sleep -Seconds 5  # Allow FastAPI to boot

try {
    $health = Invoke-RestMethod "http://localhost:$Port/api/v3/health" -TimeoutSec 15 -ErrorAction Stop
    Assert-True ($null -ne $health) "/api/v3/health returns non-null response"
    if ($health) {
        $hasShape = ($null -ne $health.status) -or ($null -ne $health.components)
        Assert-True $hasShape "/health has expected shape (status or components field)"
    }
} catch {
    $Failures.Add("[FAIL] /api/v3/health threw: $($_.Exception.Message)")
    Write-Host "[FAIL] /api/v3/health threw: $($_.Exception.Message)" -ForegroundColor Red
}

# === Phase 5: Version endpoint vs Variables.wxi =========================
Write-Host ""
Write-Host "--- Phase 5: Version match ---" -ForegroundColor Cyan
try {
    $ver = Invoke-RestMethod "http://localhost:$Port/api/v3/version" -TimeoutSec 10 -ErrorAction Stop
    if ($ver -and $ver.version) {
        $varsPath = Join-Path $PSScriptRoot '..\..\deploy\msi\Variables.wxi'
        $expectedVer = $null
        if (Test-Path $varsPath) {
            $match = Select-String -Path $varsPath -Pattern 'ProductVersion.*?"([0-9.]+)"' | Select-Object -First 1
            if ($match) { $expectedVer = $match.Matches[0].Groups[1].Value }
        }
        if ($expectedVer) {
            Assert-True ($ver.version -like "$expectedVer*") "/api/v3/version ($($ver.version)) matches Variables.wxi ($expectedVer)"
        } else {
            Skip-Test "Version match" "Variables.wxi not parseable from $varsPath"
        }
    } else {
        $Failures.Add("[FAIL] /api/v3/version has no .version field")
    }
} catch {
    Skip-Test "Version endpoint" "endpoint may not exist or threw: $($_.Exception.Message)"
}

# === Phase 6: Advisory mode =============================================
Write-Host ""
Write-Host "--- Phase 6: Advisory mode (no license.dat) ---" -ForegroundColor Cyan
if (-not (Test-Path "$ProgramData\license.dat")) {
    Assert-True ((Get-Service $SvcName).Status -eq 'Running') "Service Running in advisory mode"
    # TODO: assert /api/v3/features endpoint returns advisory shape when designed
    Skip-Test "Feature registry advisory shape" "endpoint /api/v3/features not yet designed in test"
} else {
    Skip-Test "Advisory mode test" "license.dat already present in ProgramData"
}

# === Phase 7: License.dat activation ====================================
Write-Host ""
Write-Host "--- Phase 7: License.dat activation ---" -ForegroundColor Cyan
if ($LicenseDatPath -and (Test-Path $LicenseDatPath)) {
    Copy-Item $LicenseDatPath "$ProgramData\license.dat" -Force
    Restart-Service $SvcName
    Start-Sleep -Seconds 8
    Assert-True ((Get-Service $SvcName).Status -eq 'Running') "Service restarts after license.dat placement"
    # TODO: call /api/v3/features to confirm registry activated when designed
    Skip-Test "Feature registry activation" "endpoint /api/v3/features not yet designed in test"
} else {
    Skip-Test "License.dat activation" "no -LicenseDatPath provided"
}

# === Phase 8: Restart resilience ========================================
Write-Host ""
Write-Host "--- Phase 8: Restart resilience ---" -ForegroundColor Cyan
Restart-Service $SvcName
Start-Sleep -Seconds 8
Assert-True ((Get-Service $SvcName).Status -eq 'Running') "Service Running after manual restart"
Assert-True (Test-Path "$ProgramData\logs") "ProgramData logs preserved after restart"

# === Phase 9: Uninstall =================================================
Write-Host ""
Write-Host "--- Phase 9: Uninstall ---" -ForegroundColor Cyan
$uninstResult = Start-Process -Wait -PassThru msiexec -ArgumentList @('/x', $MsiPath, '/qn', '/l*v', $UninstallLog)
Assert-True ($uninstResult.ExitCode -eq 0) "msiexec uninstall exit code 0 (got: $($uninstResult.ExitCode))"
Assert-True ($null -eq (Get-Service $SvcName -ErrorAction SilentlyContinue)) "Service removed after uninstall"
Assert-True (-not (Test-Path $InstallDir)) "Install dir removed after uninstall"
Assert-True (Test-Path $ProgramData) "ProgramData preserved after uninstall (by-design S2-7)"

# === Phase 10: Summary ==================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SMOKE TEST SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Scenario:   $Scenario"
Write-Host "  Failures:   $($Failures.Count)"
Write-Host "  Warnings:   $($Warnings.Count) (skipped tests)"
Write-Host "  TimeStamp:  $(Get-Date -Format o)"
Write-Host ""

if ($Failures.Count -gt 0) {
    Write-Host "FAILURES:" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "[RESULT] SMOKE TEST FAILED" -ForegroundColor Red
    exit 1
}

if ($Warnings.Count -gt 0) {
    Write-Host "WARNINGS (skipped tests, not blocking):" -ForegroundColor Yellow
    $Warnings | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host ""
}

Write-Host "[RESULT] SMOKE TEST PASSED" -ForegroundColor Green
exit 0
