# ============================================================
# WatcherDB V3.3 — Setup da Base de Dados
# ============================================================
# Cria a BD WatcherDB_Intelligence e executa todos os scripts SQL
# Executar como Administrador ou com conta com permissoes no SQL Server
# ============================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$SqlServer,
    [string]$Database = "WatcherDB_Intelligence",
    [switch]$UseWindowsAuth = $true,
    [Parameter(Mandatory=$true, HelpMessage="Identidade DBA que autoriza DDL na BD partilhada WatcherDB_Intelligence (REGRA OURO #2). Ex: 'salomao.netto'. Coordinate com v1-intel-specialist antes de qualquer execucao.")]
    [string]$ConfirmedDBAIdentity
)

$ErrorActionPreference = "Stop"

# REGRA DE OURO #2 (P0-7): DDL na BD partilhada exige identidade DBA confirmada.
# Audit log para reproducibilidade DORA art. 16 (ICT incident logging).
Write-Host "[AUDIT] Script invocado por $env:USERDOMAIN\$env:USERNAME com ConfirmedDBAIdentity='$ConfirmedDBAIdentity' em $(Get-Date -Format o)" -ForegroundColor Yellow

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  WatcherDB V3.3 — Setup da Base de Dados" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Server:   $SqlServer" -ForegroundColor White
Write-Host "  Database: $Database" -ForegroundColor White
Write-Host ""

# Directorio dos scripts SQL
$dbDir = Join-Path (Split-Path -Parent $PSScriptRoot) "database"
if (-not (Test-Path $dbDir)) {
    Write-Host "[ERRO] Directorio database/ nao encontrado: $dbDir" -ForegroundColor Red
    exit 1
}

# Funcao para executar SQL
function Invoke-SqlScript {
    param([string]$File, [string]$Db = "master")

    $filePath = Join-Path $dbDir $File
    if (-not (Test-Path $filePath)) {
        Write-Host "  [SKIP] $File (nao encontrado)" -ForegroundColor Yellow
        return
    }

    Write-Host "  [SQL] Executando $File..." -ForegroundColor Gray
    try {
        if ($UseWindowsAuth) {
            sqlcmd -S $SqlServer -d $Db -i $filePath -b -e 2>&1 | Out-Null
        } else {
            $user = Read-Host "SQL User"
            $pass = Read-Host "SQL Password" -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pass)
            $plainPass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            try {
                sqlcmd -S $SqlServer -d $Db -U $user -P $plainPass -i $filePath -b -e 2>&1 | Out-Null
            }
            finally {
                # F-SEC-002 hardening (CWE-316): zero unmanaged BSTR + remove managed string refs.
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
                Remove-Variable plainPass, bstr, user, pass -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Host "  [OK] $File" -ForegroundColor Green
    } catch {
        Write-Host "  [ERRO] $File : $_" -ForegroundColor Red
    }
}

# --- 1. Criar Base de Dados ---
Write-Host "--- Passo 1: Criar Base de Dados ---" -ForegroundColor Cyan
$createDbSql = @"
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '$Database')
BEGIN
    CREATE DATABASE [$Database]
    PRINT 'Database $Database criada.'
END
ELSE
    PRINT 'Database $Database ja existe.'
"@

$tempFile = [System.IO.Path]::GetTempFileName() + ".sql"
$createDbSql | Out-File -FilePath $tempFile -Encoding UTF8
try {
    if ($UseWindowsAuth) {
        sqlcmd -S $SqlServer -d master -i $tempFile -b 2>&1
    }
    Write-Host "[OK] Database $Database pronta" -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Falha ao criar database: $_" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}

# --- 2. Executar scripts SQL ---
Write-Host ""
Write-Host "--- Passo 2: Executar scripts SQL ---" -ForegroundColor Cyan

$scripts = @(
    "00_WATCHERDB_MASTER_DEPLOY.sql",
    "02_WATCHERDB_INDEXES.sql",
    "03_WATCHERDB_PROCEDURES.sql",
    "04_WATCHERDB_VIEWS.sql",
    "05_WATCHERDB_BLUE_GREEN_ENV.sql",
    "CREATE_USER_AUTHENTICATION_SYSTEM.sql",
    "CREATE_USER_AUTH_PREFS.sql",
    "CREATE_DISK_UNALLOCATED_TABLES.sql",
    "CREATE_DB_AVAILABILITY_PROBLEM_VIEW.sql",
    "CRIAR_VIEW_ALWAYSON_AGG.sql",
    "SQLSERVER_KPI_VIEWS.sql",
    "SQLSERVER_KPI_COLLECTION_PROCEDURES.sql",
    "SQLSERVER_KPI_DEPLOY_COMPLETE.sql",
    "SQLSERVER_KPI_AGENT_JOBS.sql",
    "SQLSERVER_KPI_REPLICATION_COMPLETE.sql",
    "KPI_SERVER_OFFLINE_EVENTS.sql",
    "FIX_BACKUP_SCORE_OVERVIEW.sql",
    "COLLECTION_HISTORY_SECTION.sql",
    "UPDATE_DB_AVAILABILITY_MIRRORING.sql",
    "INSTALACAO_COMPLETA_UNIFICADA.sql",
    "06_CREATE_TOKEN_BLACKLIST.sql",
    "07_ADD_MUST_CHANGE_PASSWORD.sql",
    "08_CREATE_SYSTEM_CONFIG.sql"
)

foreach ($script in $scripts) {
    Invoke-SqlScript -File $script -Db $Database
}

# --- 3. Resumo ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DATABASE SETUP CONCLUIDO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Server:   $SqlServer" -ForegroundColor White
Write-Host "  Database: $Database" -ForegroundColor White
Write-Host ""
Write-Host "  PROXIMOS PASSOS:" -ForegroundColor Yellow
Write-Host "  1. Verificar que a BD foi criada: SSMS → $SqlServer → $Database" -ForegroundColor White
Write-Host "  2. Configurar .env com INTELLIGENCE_SERVER=$SqlServer" -ForegroundColor White
Write-Host "  3. Reiniciar servico: net stop/start WatcherDBWebServiceV33" -ForegroundColor White
Write-Host ""
