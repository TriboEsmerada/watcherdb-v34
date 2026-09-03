#Requires -Version 5.1
<#
.SYNOPSIS
    Sign the WatcherDB V3.3 Standard Edition MSI with Authenticode.

.DESCRIPTION
    Supports three signing backends; pick the one matching the workstation.

      keylocker  (default)  DigiCert KeyLocker cloud HSM with EV certificate.
                            Requires DigiCert KeyLocker Client Tools installed
                            and the following environment variables set:
                              SM_HOST, SM_API_KEY, SM_CLIENT_CERT_FILE,
                              SM_CLIENT_CERT_PASSWORD, SM_CERT_ALIAS
                            Preferred for customer shipment — EV bypasses
                            SmartScreen reputation seeding on first install.

      pfx                   Local .pfx / .p12 file. OV or EV.
                            Requires -PfxPath and -PfxPassword.
                            Acceptable fallback when EV emission is in flight;
                            keep the PFX outside the repo (see
                            .gitignore rules from Sem 0).

      store                 Windows certificate store (CurrentUser\My).
                            Requires -CertThumbprint. Useful for smart-card
                            or TPM-bound certs already imported on the
                            build workstation.

    All modes produce the same on-disk result: an MSI signed with SHA-256
    digest and a SHA-256 RFC 3161 timestamp. Verification runs after signing
    and returns non-zero if the signature is missing or invalid.

.PARAMETER Mode
    keylocker | pfx | store. Default: keylocker.

.PARAMETER MsiPath
    MSI to sign. Default: dist\msi\WatcherDB_V3.3_Standard.msi.

.PARAMETER PfxPath
    PFX/P12 file (pfx mode only).

.PARAMETER PfxPassword
    Password for the PFX (pfx mode only). Pass as SecureString.

.PARAMETER CertThumbprint
    Certificate thumbprint in CurrentUser\My (store mode only).

.PARAMETER TimestampUrl
    RFC 3161 timestamp server. Default: http://timestamp.digicert.com.

.EXAMPLE
    # Most common path for production releases once KeyLocker is set up.
    pwsh deploy\sign_msi.ps1

.EXAMPLE
    # OV fallback during EV issuance waiting period.
    pwsh deploy\sign_msi.ps1 -Mode pfx -PfxPath "C:\secure\watcherdb-ov.pfx" `
        -PfxPassword (Read-Host -AsSecureString "PFX password")
#>

[CmdletBinding()]
param(
    [ValidateSet('keylocker','pfx','store')]
    [string]$Mode = 'keylocker',

    [string]$MsiPath = '',

    [string]$PfxPath,
    [SecureString]$PfxPassword,

    [string]$CertThumbprint,

    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'

# -------------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------------
$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot  = Split-Path -Parent $scriptDir

# Load release vars SOT (S2-5) — MsiFileName vem do .psd1, nao hardcoded.
$releaseVarsFile = Join-Path $scriptDir 'release_vars.psd1'
if (Test-Path $releaseVarsFile) {
    $rv = Import-PowerShellDataFile -Path $releaseVarsFile
    $defaultMsi = $rv.MsiFileName
} else {
    # Fallback seguro se o ficheiro nao estiver presente (compatibilidade retroactiva).
    $defaultMsi = 'WatcherDB_V3.3_Standard.msi'
}

if (-not $MsiPath) {
    $MsiPath = Join-Path $repoRoot ("dist\msi\" + $defaultMsi)
}

function Write-Step($msg) { Write-Host "[sign_msi] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[sign_msi] OK   $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "[sign_msi] FAIL $msg" -ForegroundColor Red; throw $msg }

# -------------------------------------------------------------------------
# Prerequisite: signtool.exe
# -------------------------------------------------------------------------
Write-Step 'Resolving signtool.exe...'
$signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Path
if (-not $signtool) {
    # Probe common Windows SDK install locations.
    $candidates = Get-ChildItem -Path 'C:\Program Files (x86)\Windows Kits\10\bin' `
        -Recurse -ErrorAction SilentlyContinue -Filter 'signtool.exe' |
        Where-Object { $_.DirectoryName -match '\\x64\\' } |
        Sort-Object FullName -Descending
    if ($candidates.Count -gt 0) { $signtool = $candidates[0].FullName }
}
if (-not $signtool) {
    Write-Fail 'signtool.exe not found. Install Windows 10/11 SDK (Signing Tools) and retry.'
}
Write-Ok "signtool: $signtool"

if (-not (Test-Path $MsiPath)) {
    Write-Fail "MSI not found: $MsiPath. Run deploy\build_msi.ps1 first."
}
Write-Ok "MSI: $MsiPath"

# -------------------------------------------------------------------------
# Assemble signtool command line based on the chosen mode
# -------------------------------------------------------------------------
$common = @(
    'sign',
    '/fd', 'sha256',
    '/td', 'sha256',
    '/tr', $TimestampUrl,
    '/v'
)

switch ($Mode) {
    'keylocker' {
        foreach ($v in 'SM_HOST','SM_API_KEY','SM_CLIENT_CERT_FILE','SM_CLIENT_CERT_PASSWORD','SM_CERT_ALIAS') {
            if (-not (Test-Path "Env:$v")) {
                Write-Fail "KeyLocker env var $v is not set. See https://docs.digicert.com/en/digicert-keylocker.html for configuration."
            }
        }
        $alias = $env:SM_CERT_ALIAS
        Write-Step "Signing via DigiCert KeyLocker (alias: $alias)..."
        $args = $common + @('/sm', '/n', $alias, $MsiPath)
    }

    'pfx' {
        if (-not $PfxPath) { Write-Fail '-PfxPath is required in pfx mode.' }
        if (-not (Test-Path $PfxPath)) { Write-Fail "PFX file not found: $PfxPath" }
        if (-not $PfxPassword) {
            $PfxPassword = Read-Host -Prompt 'PFX password' -AsSecureString
        }
        # F-SEC-002: capturar BSTR ptr em var separada para permitir ZeroFreeBSTR posterior.
        $bstrPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($PfxPassword)
        $plainPwd = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrPtr)
        Write-Step "Signing via PFX: $PfxPath"
        $args = $common + @('/f', $PfxPath, '/p', $plainPwd, $MsiPath)
    }

    'store' {
        if (-not $CertThumbprint) { Write-Fail '-CertThumbprint is required in store mode.' }
        $cert = Get-Item "Cert:\CurrentUser\My\$CertThumbprint" -ErrorAction SilentlyContinue
        if (-not $cert) { Write-Fail "Certificate with thumbprint $CertThumbprint not found in CurrentUser\My." }
        Write-Step "Signing via cert store (thumbprint: $CertThumbprint, subject: $($cert.Subject))..."
        $args = $common + @('/sha1', $CertThumbprint, $MsiPath)
    }
}

# -------------------------------------------------------------------------
# Sign
# -------------------------------------------------------------------------
& $signtool @args
$rc = $LASTEXITCODE
if ($Mode -eq 'pfx') {
    # F-SEC-002 hardening (CWE-316): zero unmanaged BSTR + remove managed refs.
    if ($bstrPtr) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrPtr) | Out-Null }
    Remove-Variable plainPwd, bstrPtr -Force -ErrorAction SilentlyContinue
}
if ($rc -ne 0) {
    Write-Fail "signtool failed with exit code $rc"
}

# -------------------------------------------------------------------------
# Verify
# -------------------------------------------------------------------------
Write-Step 'Verifying signature...'
& $signtool verify /pa /v $MsiPath
if ($LASTEXITCODE -ne 0) {
    Write-Fail 'signtool verify reported the signature as invalid.'
}
Write-Ok 'Signature verified (Authenticode + RFC 3161 timestamp).'

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
$info = & $signtool verify /pa /v /debug $MsiPath 2>&1 | Out-String
$sizeMb = [math]::Round(((Get-Item $MsiPath).Length / 1MB), 1)
Write-Host ''
Write-Host ('=' * 60)
Write-Host '  MSI SIGNED - WatcherDB V3.3 Standard Edition'
Write-Host ('=' * 60)
Write-Host "  File:       $MsiPath"
Write-Host "  Size:       $sizeMb MB"
Write-Host "  Mode:       $Mode"
Write-Host "  Timestamp:  $TimestampUrl"
Write-Host ''
Write-Host '  NEXT STEPS:'
Write-Host '  1. Archive the signed MSI and its SBOM (deploy/build_sbom.ps1)'
Write-Host '     under dist/release/<version>/.'
Write-Host '  2. Test SmartScreen behaviour by downloading from a web URL;'
Write-Host '     EV certs bypass the warning, OV ones accrue reputation.'
Write-Host '  3. Distribute via signed installer portal or customer channel.'
Write-Host ('=' * 60)
