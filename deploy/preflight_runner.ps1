#Requires -Version 5.1
<#
.SYNOPSIS
    Pre-flight check para self-hosted Windows runner do WatcherDB V3.3 build pipeline.

.DESCRIPTION
    Valida que o runner tem toda a toolchain necessaria antes de aceitar jobs
    do workflow build-release.yml. Corre como standalone no runner.

    Checks (10 phases):
      1. Python 3.11 in PATH
      2. PyArmor Pro reg 011618 activated com BCC+RFT
      3. LLVM/Clang in PATH (required by PyArmor BCC)
      4. WiX Toolset v3.14 (candle + light + heat) in PATH
      5. Syft (SBOM generator) in PATH
      6. signtool.exe (Windows SDK) in PATH
      7. .venv-build/ exists with requirements-build.txt installed
      8. Network reachability (pypi.org + PyArmor licence server)
      9. Disk space (>10 GB free for build output)
     10. GitHub Actions runner service running

.PARAMETER WorkspacePath
    Path to runner workspace where projeto is checked out.
    Default: current directory (assumes script runs from WATCHERDB_V3.3/).

.EXAMPLE
    # No runner, antes de aceitar jobs:
    powershell.exe -ExecutionPolicy Bypass -File deploy\preflight_runner.ps1

.NOTES
    Exit codes:
      0 = ALL checks PASS (runner ready)
      1 = 1+ checks FAILED
      2 = WARN only (non-blocking issues)

    Author: WatcherDB DevOps
    See also: docs/runner-setup.md
#>

[CmdletBinding()]
param(
    [string]$WorkspacePath = (Get-Location).Path
)

$ErrorActionPreference = 'Continue'

$Failures = [System.Collections.Generic.List[string]]::new()
$Warnings = [System.Collections.Generic.List[string]]::new()

function Test-Check {
    param([bool]$Condition, [string]$Label, [string]$Severity = 'fail')
    if (-not $Condition) {
        if ($Severity -eq 'warn') {
            $Warnings.Add("[WARN] $Label")
            Write-Host "[WARN] $Label" -ForegroundColor Yellow
        } else {
            $Failures.Add("[FAIL] $Label")
            Write-Host "[FAIL] $Label" -ForegroundColor Red
        }
    } else {
        Write-Host "[PASS] $Label" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  WatcherDB V3.3 Runner Preflight Check" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Workspace:  $WorkspacePath"
Write-Host "  Timestamp:  $(Get-Date -Format o)"
Write-Host ""

# === Phase 1: Python 3.11 ===============================================
Write-Host "--- Phase 1: Python 3.11 ---" -ForegroundColor Cyan
$pyOut = & py -3.11 --version 2>&1 | Out-String
Test-Check ($pyOut -match 'Python 3\.11') "Python 3.11 available via 'py -3.11' (got: $($pyOut.Trim()))"

# === Phase 2: PyArmor Pro reg 011618 ====================================
Write-Host ""
Write-Host "--- Phase 2: PyArmor Pro licence ---" -ForegroundColor Cyan
$venvPython = Join-Path $WorkspacePath '.venv-build\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Test-Check $false "venv exists at .venv-build/ (run: py -3.11 -m venv .venv-build first)"
} else {
    $paOut = & $venvPython -m pyarmor.cli --version 2>&1 | Out-String
    Test-Check ($paOut -match 'pyarmor-pro') "PyArmor Pro licence active (regfile activated)"
    Test-Check ($paOut -match '011618') "PyArmor licence is reg 011618 (WatcherDB)"
    Test-Check ($paOut -match 'BCC Mode\s*:\s*Yes') "PyArmor BCC Mode enabled"
    Test-Check ($paOut -match 'RFT Mode\s*:\s*Yes') "PyArmor RFT Mode enabled"
}

# === Phase 3: LLVM/Clang ================================================
Write-Host ""
Write-Host "--- Phase 3: LLVM/Clang (PyArmor BCC dependency) ---" -ForegroundColor Cyan
$clang = Get-Command clang.exe -ErrorAction SilentlyContinue
Test-Check ($null -ne $clang) "clang.exe in PATH (got: $($clang.Source))"

# === Phase 4: WiX Toolset v3.14 =========================================
Write-Host ""
Write-Host "--- Phase 4: WiX Toolset v3.14 ---" -ForegroundColor Cyan
foreach ($tool in @('candle.exe','light.exe','heat.exe')) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    Test-Check ($null -ne $cmd) "$tool in PATH"
}

# === Phase 5: Syft ======================================================
Write-Host ""
Write-Host "--- Phase 5: Syft (SBOM generator) ---" -ForegroundColor Cyan
$syft = Get-Command syft -ErrorAction SilentlyContinue
Test-Check ($null -ne $syft) "syft in PATH (got: $($syft.Source))"

# === Phase 6: signtool.exe ==============================================
Write-Host ""
Write-Host "--- Phase 6: signtool.exe (Windows SDK) ---" -ForegroundColor Cyan
$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
Test-Check ($null -ne $signtool) "signtool.exe in PATH"

# === Phase 7: venv build deps ===========================================
Write-Host ""
Write-Host "--- Phase 7: venv build dependencies ---" -ForegroundColor Cyan
if (Test-Path $venvPython) {
    $piOut = & $venvPython -m PyInstaller --version 2>&1 | Out-String
    Test-Check ($piOut -match '^\d+\.\d+') "PyInstaller installed in venv (got: $($piOut.Trim()))"
} else {
    Test-Check $false "venv exists (already failed Phase 2)"
}

# === Phase 8: Network reachability ======================================
Write-Host ""
Write-Host "--- Phase 8: Network reachability ---" -ForegroundColor Cyan
$pypiOk = Test-NetConnection -ComputerName pypi.org -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
Test-Check $pypiOk "pypi.org:443 reachable"
$paOk = Test-NetConnection -ComputerName api.dashingsoft.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
Test-Check $paOk "api.dashingsoft.com:443 reachable (PyArmor licence server)" 'warn'
$ghOk = Test-NetConnection -ComputerName github.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
Test-Check $ghOk "github.com:443 reachable"

# === Phase 9: Disk space ================================================
Write-Host ""
Write-Host "--- Phase 9: Disk space ---" -ForegroundColor Cyan
$drive = Get-PSDrive C
$freeGB = [math]::Round($drive.Free / 1GB, 1)
Test-Check ($freeGB -gt 10) "C:\ has >10 GB free (got: $freeGB GB)"
if ($freeGB -lt 50) {
    $Warnings.Add("[WARN] Disk space marginal ($freeGB GB free, recommend 50+ GB for build cache)")
    Write-Host "[WARN] Disk space marginal ($freeGB GB free, recommend 50+ GB)" -ForegroundColor Yellow
}

# === Phase 10: GitHub Actions runner service =============================
Write-Host ""
Write-Host "--- Phase 10: GitHub Actions runner service ---" -ForegroundColor Cyan
$runnerSvc = Get-Service -Name "actions.runner.*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($runnerSvc) {
    Test-Check ($runnerSvc.Status -eq 'Running') "GitHub Actions runner service Running (got: $($runnerSvc.Status))"
} else {
    Test-Check $false "GitHub Actions runner service installed (actions.runner.*)" 'warn'
}

# === Summary ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  PREFLIGHT SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Failures:  $($Failures.Count)"
Write-Host "  Warnings:  $($Warnings.Count)"
Write-Host ""

if ($Failures.Count -gt 0) {
    Write-Host "FAILURES:" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "[RESULT] PREFLIGHT FAILED - fix above before accepting jobs" -ForegroundColor Red
    Write-Host "See WATCHERDB_V3.3/docs/runner-setup.md for installation guide"
    exit 1
}

if ($Warnings.Count -gt 0) {
    Write-Host "WARNINGS (non-blocking):" -ForegroundColor Yellow
    $Warnings | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "[RESULT] PREFLIGHT PASSED with warnings" -ForegroundColor Yellow
    exit 2
}

Write-Host "[RESULT] PREFLIGHT PASSED - runner ready to accept jobs" -ForegroundColor Green
exit 0
