#Requires -Version 5.1
<#
.SYNOPSIS
    Valida configuracao DigiCert KeyLocker antes de signing real.

.DESCRIPTION
    Verifica que os 5 secrets KeyLocker estao configurados correctamente
    + opcionalmente faz dry-run de signtool com cert para detectar bugs antes
    de tentar sign de release real.

    Checks (7):
      1. SM_HOST set + URL valido + reachable (TLS 443)
      2. SM_API_KEY set + non-empty + minimum length
      3. SM_CLIENT_CERT_FILE set + file exists no disco
      4. SM_CLIENT_CERT_PASSWORD set (non-empty, no actual validation)
      5. SM_CERT_ALIAS set + non-empty
      6. signtool.exe in PATH
      7. (Optional) Dry-run: signtool /pa /v <random.exe> with KeyLocker creds

.PARAMETER DryRunSignFile
    Optional path to .exe file para fazer dry-run sign test.
    If omitted, skips Phase 7 (actual signing test).

.EXAMPLE
    # Validate config sem signing test:
    powershell.exe -ExecutionPolicy Bypass -File deploy\validate_digicert.ps1

.EXAMPLE
    # Validate + dry-run sign test num exe dummy:
    powershell.exe -ExecutionPolicy Bypass -File deploy\validate_digicert.ps1 `
        -DryRunSignFile dist\watcherdb\watcherdb.exe

.NOTES
    Required env vars (or GitHub secrets injected into env):
      SM_HOST                  e.g. https://clientauth.one.digicert.com
      SM_API_KEY               from DigiCert console
      SM_CLIENT_CERT_FILE      absolute path to client.p12 on runner
      SM_CLIENT_CERT_PASSWORD  password for client.p12
      SM_CERT_ALIAS            alias from DigiCert console

    Exit codes:
      0 = ALL checks PASS
      1 = 1+ checks FAILED
      2 = WARN only

    Author: WatcherDB DevOps
    See also: docs/runner-setup.md + deploy/sign_msi.ps1
#>

[CmdletBinding()]
param(
    [string]$DryRunSignFile = ''
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
Write-Host "  DigiCert KeyLocker Validation" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Timestamp: $(Get-Date -Format o)"
Write-Host "  DryRun:    $(if ($DryRunSignFile) { $DryRunSignFile } else { '(skipped)' })"
Write-Host ""

# === Phase 1: SM_HOST ====================================================
Write-Host "--- Phase 1: SM_HOST (DigiCert KeyLocker URL) ---" -ForegroundColor Cyan
$smHost = $env:SM_HOST
Test-Check ($null -ne $smHost -and $smHost -ne '') "SM_HOST env var is set"
if ($smHost) {
    Test-Check ($smHost -match '^https://') "SM_HOST starts with https://"
    try {
        $uri = [System.Uri]$smHost
        $hostName = $uri.Host
        $reachable = Test-NetConnection -ComputerName $hostName -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
        Test-Check $reachable "$hostName`:443 reachable (TLS)"
    } catch {
        Test-Check $false "SM_HOST is valid URI: $($_.Exception.Message)"
    }
}

# === Phase 2: SM_API_KEY =================================================
Write-Host ""
Write-Host "--- Phase 2: SM_API_KEY ---" -ForegroundColor Cyan
$smApiKey = $env:SM_API_KEY
Test-Check ($null -ne $smApiKey -and $smApiKey -ne '') "SM_API_KEY env var is set"
if ($smApiKey) {
    Test-Check ($smApiKey.Length -ge 16) "SM_API_KEY has minimum length 16 (got: $($smApiKey.Length))"
    Test-Check ($smApiKey -notmatch '\s') "SM_API_KEY has no whitespace (likely copy-paste error)"
}

# === Phase 3: SM_CLIENT_CERT_FILE ========================================
Write-Host ""
Write-Host "--- Phase 3: SM_CLIENT_CERT_FILE ---" -ForegroundColor Cyan
$smCertFile = $env:SM_CLIENT_CERT_FILE
Test-Check ($null -ne $smCertFile -and $smCertFile -ne '') "SM_CLIENT_CERT_FILE env var is set"
if ($smCertFile) {
    Test-Check (Test-Path $smCertFile) "Cert file exists at: $smCertFile"
    if (Test-Path $smCertFile) {
        $certInfo = Get-Item $smCertFile
        Test-Check ($certInfo.Extension -match '\.(p12|pfx)$') "Cert file extension is .p12 or .pfx (got: $($certInfo.Extension))"
        Test-Check ($certInfo.Length -gt 1000) "Cert file size >1KB (got: $($certInfo.Length) bytes)"
    }
}

# === Phase 4: SM_CLIENT_CERT_PASSWORD ====================================
Write-Host ""
Write-Host "--- Phase 4: SM_CLIENT_CERT_PASSWORD ---" -ForegroundColor Cyan
$smCertPwd = $env:SM_CLIENT_CERT_PASSWORD
Test-Check ($null -ne $smCertPwd -and $smCertPwd -ne '') "SM_CLIENT_CERT_PASSWORD env var is set"
if ($smCertPwd) {
    Test-Check ($smCertPwd.Length -ge 8) "SM_CLIENT_CERT_PASSWORD min length 8 (got: $($smCertPwd.Length))"
}

# === Phase 5: SM_CERT_ALIAS ==============================================
Write-Host ""
Write-Host "--- Phase 5: SM_CERT_ALIAS ---" -ForegroundColor Cyan
$smAlias = $env:SM_CERT_ALIAS
Test-Check ($null -ne $smAlias -and $smAlias -ne '') "SM_CERT_ALIAS env var is set"
if ($smAlias) {
    Test-Check ($smAlias -notmatch '\s') "SM_CERT_ALIAS has no whitespace"
}

# === Phase 6: signtool.exe ===============================================
Write-Host ""
Write-Host "--- Phase 6: signtool.exe ---" -ForegroundColor Cyan
$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
Test-Check ($null -ne $signtool) "signtool.exe in PATH"

# === Phase 7: Optional dry-run signing test ==============================
Write-Host ""
Write-Host "--- Phase 7: Dry-run sign test ---" -ForegroundColor Cyan
if ($DryRunSignFile -and (Test-Path $DryRunSignFile)) {
    if ($Failures.Count -gt 0) {
        Write-Host "[SKIP] Dry-run skipped because earlier checks failed" -ForegroundColor Yellow
        $Warnings.Add("[SKIP] Dry-run sign test (earlier failures)")
    } elseif (-not $signtool) {
        Write-Host "[SKIP] signtool.exe missing" -ForegroundColor Yellow
    } else {
        # Make temp copy to avoid modifying original
        $tmpCopy = Join-Path $env:TEMP "preflight_sign_test_$([guid]::NewGuid().ToString('N')).exe"
        Copy-Item $DryRunSignFile $tmpCopy -Force
        try {
            $signArgs = @(
                'sign',
                '/fd', 'sha256',
                '/tr', 'http://timestamp.digicert.com',
                '/td', 'sha256',
                '/sm',
                '/n', $smAlias,
                $tmpCopy
            )
            $signOutput = & signtool @signArgs 2>&1 | Out-String
            $signOk = $LASTEXITCODE -eq 0
            Test-Check $signOk "Dry-run sign succeeded on $DryRunSignFile (test copy)"
            if (-not $signOk) {
                Write-Host "  signtool output:" -ForegroundColor Yellow
                $signOutput -split "`n" | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
            }
        } finally {
            Remove-Item $tmpCopy -Force -ErrorAction SilentlyContinue
        }
    }
} elseif ($DryRunSignFile) {
    Test-Check $false "DryRunSignFile not found: $DryRunSignFile"
} else {
    Write-Host "[SKIP] No -DryRunSignFile parameter provided (config-only validation)" -ForegroundColor Gray
}

# === Summary ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DIGICERT VALIDATION SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Failures:  $($Failures.Count)"
Write-Host "  Warnings:  $($Warnings.Count)"
Write-Host ""

if ($Failures.Count -gt 0) {
    Write-Host "FAILURES:" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "[RESULT] DIGICERT CONFIG INVALID" -ForegroundColor Red
    Write-Host "Configure secrets via env vars OR GitHub Actions Secrets."
    Write-Host "See WATCHERDB_V3.3/docs/runner-setup.md (section 7 + 8)"
    exit 1
}

if ($Warnings.Count -gt 0) {
    Write-Host "WARNINGS (non-blocking):" -ForegroundColor Yellow
    $Warnings | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "[RESULT] CONFIG VALID with warnings" -ForegroundColor Yellow
    exit 2
}

Write-Host "[RESULT] DIGICERT CONFIG VALID - ready for production signing" -ForegroundColor Green
exit 0
