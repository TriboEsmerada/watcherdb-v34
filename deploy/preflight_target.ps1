#Requires -Version 5.1
<#
.SYNOPSIS
    Preflight check no target machine antes de instalar o WatcherDB V3.4 (ZIP + install.ps1).

.DESCRIPTION
    Valida pre-requisitos antes de correr install.ps1. Falha graciosa com fix hints.
    Diferente do preflight_runner.ps1 (que valida build runner) - este foca em
    target machine de install (DBA workstation ou monitoring server).

    Checks (10 phases):
      1. Admin rights (install.ps1 exige)
      2. Windows version (Server 2016+ / Win 10/11)
      3. ODBC Driver 17 ou 18 for SQL Server
      4. SQL Server TCP reachable (param: -SqlServer)
      5. Login do produto existe (informativo; params: -SqlServer, -SqlLogin)
      6. AD service account resolvable (param: -ServiceAccount)
      7. Porta do produto livre (param: -WebPort)
      8. Disk space >500 MB no C:\
      9. Servico do produto nao pre-existente (param: -ServiceName)
     10. .NET Framework 4.7.2+ (some MSI components precisam)

.PARAMETER SqlServer
    SQL Server target (e.g. SQLHDSTST505\I01) para validar conectividade + login.
    REGRA OURO #2: o produto so' liga com o seu login SQL (-SqlLogin), nunca Trusted_Connection.

.PARAMETER ServiceAccount
    Optional AD service account (e.g. DOMAIN\svc_watcherdb_v33).
    Default: NetworkService (no validation needed).

.PARAMETER SkipSqlCheck
    Skip Phases 4-5 (SQL connectivity) se o login do produto ainda nao foi criado.

.EXAMPLE
    # NetworkService scenario, SQL Server local:
    powershell.exe -ExecutionPolicy Bypass -File deploy\preflight_target.ps1 -SqlServer "localhost"

.EXAMPLE
    # Domain service account scenario:
    powershell.exe -ExecutionPolicy Bypass -File deploy\preflight_target.ps1 `
        -SqlServer "SQL01.banco.pt" `
        -ServiceAccount "DOMAIN\svc_watcherdb_v33"

.EXAMPLE
    # SQL Server skip (login do produto nao criado ainda):
    powershell.exe -ExecutionPolicy Bypass -File deploy\preflight_target.ps1 `
        -SqlServer "localhost" -SkipSqlCheck

.NOTES
    Exit codes:
      0 = ALL checks PASS (target ready)
      1 = 1+ checks FAILED (fix antes de install)
      2 = WARN only (install pode prosseguir mas com gotchas)

    Author: WatcherDB DevOps
    See also: deploy/INSTALL_TEST.md
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$SqlServer,
    [string]$ServiceAccount = '',
    [switch]$SkipSqlCheck,
    # 2026-10-07 (lote E): vem do release_vars via install.ps1; sem valores fixos de versao.
    [int]$WebPort = 8434,
    [string]$ServiceName = 'WatcherDBWebServiceV34',
    [string]$SqlLogin = 'watcherdb'
)

$ErrorActionPreference = 'Continue'

$Failures = [System.Collections.Generic.List[string]]::new()
$Warnings = [System.Collections.Generic.List[string]]::new()

function Test-Check {
    param([bool]$Condition, [string]$Label, [string]$Severity = 'fail', [string]$Hint = '')
    if (-not $Condition) {
        if ($Severity -eq 'warn') {
            $Warnings.Add("[WARN] $Label")
            Write-Host "[WARN] $Label" -ForegroundColor Yellow
        } else {
            $Failures.Add("[FAIL] $Label")
            Write-Host "[FAIL] $Label" -ForegroundColor Red
        }
        if ($Hint) { Write-Host "       Fix: $Hint" -ForegroundColor Gray }
    } else {
        Write-Host "[PASS] $Label" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  WatcherDB - Target Machine Preflight" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SqlServer:      $SqlServer"
Write-Host "  ServiceAccount: $(if ($ServiceAccount) { $ServiceAccount } else { 'NetworkService (default)' })"
Write-Host "  SkipSqlCheck:   $SkipSqlCheck"
Write-Host "  Timestamp:      $(Get-Date -Format o)"
Write-Host ""

# === Phase 1: Admin rights ==============================================
Write-Host "--- Phase 1: Admin rights ---" -ForegroundColor Cyan
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Test-Check $isAdmin "Running as Administrator" 'fail' "Right-click PowerShell -> Run as administrator"

# === Phase 2: Windows version ===========================================
Write-Host ""
Write-Host "--- Phase 2: Windows version ---" -ForegroundColor Cyan
$os = Get-CimInstance Win32_OperatingSystem
$buildNum = [int]$os.BuildNumber
$winVerOk = $buildNum -ge 14393  # Server 2016 / Win 10 build 1607+
Test-Check $winVerOk "Windows build $buildNum >= 14393 (Server 2016+ / Win 10 1607+)" 'fail' "Upgrade Windows or use newer target"

# === Phase 3: ODBC Driver 17 ou 18 ======================================
Write-Host ""
Write-Host "--- Phase 3: ODBC Driver for SQL Server ---" -ForegroundColor Cyan
$drivers = Get-OdbcDriver -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "ODBC Driver (17|18) for SQL Server" }
if ($drivers) {
    $driverNames = ($drivers | ForEach-Object { $_.Name }) -join ', '
    Test-Check $true "ODBC Driver found: $driverNames"
} else {
    Test-Check $false "ODBC Driver 17 or 18 for SQL Server installed" 'fail' "Download: https://aka.ms/odbc-sqlserver"
}

# === Phase 4: SQL Server TCP reachable ==================================
Write-Host ""
Write-Host "--- Phase 4: SQL Server TCP reachable ---" -ForegroundColor Cyan
if ($SkipSqlCheck) {
    Write-Host "[SKIP] -SkipSqlCheck flag set" -ForegroundColor Yellow
    $Warnings.Add("[SKIP] SQL Server connectivity check")
} else {
    # Parse server\instance -> host + port
    $sqlHost = ($SqlServer -split '\\')[0]
    $sqlPort = 1433  # default; named instances usam SQL Browser ou dynamic
    $sqlReachable = Test-NetConnection -ComputerName $sqlHost -Port $sqlPort -InformationLevel Quiet -WarningAction SilentlyContinue
    Test-Check $sqlReachable "$sqlHost`:$sqlPort reachable (TCP)" 'fail' "Check firewall, SQL Server TCP enabled, SQL Browser (named instances)"
}

# === Phase 5: login do produto (informativo: o instalador pode cria-lo em f2/f3) ===
Write-Host ""
Write-Host "--- Phase 5: login '$SqlLogin' (informativo) ---" -ForegroundColor Cyan
if ($SkipSqlCheck) {
    Write-Host "[SKIP] -SkipSqlCheck flag set" -ForegroundColor Yellow
} elseif (-not $sqlReachable) {
    Write-Host "[SKIP] SQL not reachable (Phase 4 failed)" -ForegroundColor Yellow
} else {
    # Use sqlcmd via Windows auth temporarily para verificar login existe
    # REGRA OURO #2: Trusted_Connection viola se domain user. Logo so check login existe (read-only).
    try {
        $sqlcmdPath = Get-Command sqlcmd -ErrorAction SilentlyContinue
        if (-not $sqlcmdPath) {
            Test-Check $false "sqlcmd available" 'warn' "Install SQL Server Command Line Utilities (msodbcsql + mssql-tools)"
        } else {
            # So' informativo: o login pode ainda nao existir (o instalador cria-o com -SqlLoginPassword / provision-login).
            $query = "SELECT name FROM sys.server_principals WHERE name = '$($SqlLogin -replace "'", "''")'"
            $output = & sqlcmd -S $SqlServer -E -Q $query -h-1 -W -b 2>&1
            $loginExists = $output -match [regex]::Escape($SqlLogin)
            Test-Check $loginExists "Login '$SqlLogin' exists on $SqlServer" 'warn' "Sera' criado pelo instalador (-SqlLoginPassword) ou pelo DBA com os scripts de grants"
        }
    } catch {
        Test-Check $false "login '$SqlLogin' check (got exception: $($_.Exception.Message))" 'warn'
    }
}

# === Phase 6: AD service account =======================================
Write-Host ""
Write-Host "--- Phase 6: AD service account ---" -ForegroundColor Cyan
if (-not $ServiceAccount) {
    Write-Host "[SKIP] Using NetworkService (no AD account validation needed)" -ForegroundColor Gray
} else {
    # Resolve AD account via WhoAmI or NET USER
    $resolved = $false
    try {
        $sid = (New-Object System.Security.Principal.NTAccount($ServiceAccount)).Translate([System.Security.Principal.SecurityIdentifier])
        if ($sid) { $resolved = $true }
    } catch {
        $resolved = $false
    }
    Test-Check $resolved "AD account '$ServiceAccount' resolvable" 'fail' "Verify domain join, account exists, spelling DOMAIN\username"

    # Warning sobre Log on as a service right
    Write-Host "[NOTE] Ensure '$ServiceAccount' has 'Log on as a service' right (GPO or Local Security Policy)" -ForegroundColor Gray
}

# === Phase 7: Porta do produto livre ====================================
Write-Host ""
Write-Host "--- Phase 7: Port $WebPort available ---" -ForegroundColor Cyan
$portInUse = (Get-NetTCPConnection -LocalPort $WebPort -ErrorAction SilentlyContinue) | Select-Object -First 1
Test-Check ($null -eq $portInUse) "Port $WebPort is free" 'fail' "Process using ${WebPort}: $(if($portInUse){"PID $($portInUse.OwningProcess)"})"

# === Phase 8: Disk space ================================================
Write-Host ""
Write-Host "--- Phase 8: Disk space ---" -ForegroundColor Cyan
$drive = Get-PSDrive C
$freeMB = [math]::Round($drive.Free / 1MB, 0)
Test-Check ($freeMB -gt 500) "C:\ has >500 MB free (got: $freeMB MB)" 'fail' "Free up disk space"

# === Phase 9: Service nao pre-existing ==================================
Write-Host ""
Write-Host "--- Phase 9: Clean install (no pre-existing service) ---" -ForegroundColor Cyan
$preSvc = Get-Service $ServiceName -ErrorAction SilentlyContinue
Test-Check ($null -eq $preSvc) "$ServiceName not pre-existing" 'warn' "Servico ja' existe: o install.ps1 faz upgrade (sc.exe config); para instalacao limpa correr uninstall.ps1 primeiro"

# === Phase 10: .NET Framework ===========================================
Write-Host ""
Write-Host "--- Phase 10: .NET Framework 4.7.2+ ---" -ForegroundColor Cyan
$netReleaseKey = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -ErrorAction SilentlyContinue
$netOk = $netReleaseKey -and $netReleaseKey.Release -ge 461808  # 4.7.2 minimum
Test-Check $netOk ".NET Framework >= 4.7.2 (got Release: $($netReleaseKey.Release))" 'fail' "Install .NET Framework 4.7.2+ from microsoft.com"

# === Summary ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  TARGET PREFLIGHT SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Failures:  $($Failures.Count)"
Write-Host "  Warnings:  $($Warnings.Count)"
Write-Host ""

if ($Failures.Count -gt 0) {
    Write-Host "FAILURES (must fix before install):" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "[RESULT] PREFLIGHT FAILED - fix above before install.ps1" -ForegroundColor Red
    exit 1
}

if ($Warnings.Count -gt 0) {
    Write-Host "WARNINGS (review before install):" -ForegroundColor Yellow
    $Warnings | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "[RESULT] PREFLIGHT PASSED with warnings" -ForegroundColor Yellow
    exit 2
}

Write-Host "[RESULT] PREFLIGHT PASSED - target ready for install.ps1" -ForegroundColor Green
exit 0
