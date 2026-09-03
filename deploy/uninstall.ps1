#Requires -Version 5.1
<#
.SYNOPSIS
    Desinstalador WatcherDB V3.3 Standard Edition (Etapa 3a - veiculo ZIP).
    Corre NO servidor do cliente, elevado (Administrator).

.DESCRIPTION
    Contrapartida do install.ps1. Remove servico, regra de firewall,
    EventLog source e o InstallDir. NUNCA remove DataDir (ProgramData) --
    e a mesma regra de ouro do Product.wxs (FIND #7/S2-7): licenca, config,
    logs e inventario do cliente sao dados dele, nao artefacto de instalacao.
    A remocao de DataDir e sempre manual e explicita (mensagem final).

    Este ficheiro e copiado para dentro de InstallDir pelo install.ps1
    (PASSO e), portanto normalmente e invocado como:
        C:\Program Files\WatcherDB\V3.3\uninstall.ps1
    Nesse caso o proprio InstallDir esta a ser apagado enquanto o script
    corre a partir de dentro dele -- a remocao final do diretorio e feita
    por um processo destacado (cmd /c) que arranca DEPOIS deste script
    terminar e libertar o ficheiro, evitando o classico problema de
    "apagar o proprio .ps1 em execucao".

    Compativel Windows PowerShell 5.1 -- sem operadores so-pwsh7.

.PARAMETER InstallDir
    Diretorio de instalacao a remover. Default: resolvido a partir de
    release_vars.psd1 (ao lado deste script) + %ProgramFiles%. Se este
    script estiver a correr de dentro do proprio InstallDir (caso normal
    pos-install), o default e $PSScriptRoot.

.PARAMETER DataDir
    Apenas para mostrar a mensagem final de remocao manual -- NUNCA
    apagado por este script. Default: resolvido via release_vars.psd1 +
    %ProgramData%.

.PARAMETER Silent
    Sem prompts de confirmacao. Usar em desinstalacao scriptada/CI.

.PARAMETER Force
    Equivalente a -Silent para efeitos de confirmacao (mantido como alias
    semantico separado para scripts que preferem -Force por convencao).

.PARAMETER PurgeEventSource
    Por default a EventLog source "$ServiceName" NAO e removida (cross-
    check adversarial deploy-architect): remover a source torna ILEGIVEIS
    os eventos HISTORICOS ja escritos no Event Viewer (o Windows perde a
    capacidade de resolver a mensagem, mostrando so "The description for
    Event ID X from source Y cannot be found"), o que compliance banking
    tipicamente NAO quer -- preferem reter legibilidade de auditoria a
    "limpar" o Event Log. Passa -PurgeEventSource se quiseres mesmo
    remover a source "$ServiceName" nesta desinstalacao (ex.: ambiente de
    teste/lab a ser reciclado). A source "WatcherDB" (partilhada entre
    versoes/produtos, eventos de licenca -- ver install.ps1 PASSO h) NUNCA
    e removida por este script, mesmo com -PurgeEventSource, porque outras
    instalacoes (V3.3 noutra pasta, V5, etc.) na mesma maquina podem ainda
    depender dela.

.EXAMPLE
    C:\Program Files\WatcherDB\V3.3\uninstall.ps1

.EXAMPLE
    C:\Program Files\WatcherDB\V3.3\uninstall.ps1 -Silent

.NOTES
    Exit codes:
      0 = desinstalacao concluida (best-effort; passos ausentes sao OK)
      1 = nao elevado (Administrator)
      2 = servico nao parou dentro do timeout (bloqueante -- requer
          intervencao manual antes de reinstalar)

    Idempotente: correr duas vezes nao produz erro -- cada passo verifica
    a existencia do recurso antes de o remover.

    DataDir (ProgramData\WatcherDB por default) e SEMPRE preservado.
    A mensagem final indica o comando exacto para remocao manual.

    Author: WatcherDB DevOps (Etapa 3a, auditoria empacotamento 2026-07-03/04)
    See also: install.ps1, deploy\msi\Product.wxs (FIND #7/S2-7)
#>

[CmdletBinding()]
param(
    [string]$InstallDir,
    [string]$DataDir,
    [switch]$Silent,
    [switch]$Force,
    [switch]$PurgeEventSource,
    # Decommissioning de asset (ISO 27001 A.8.10 / DORA): remove o DataDir
    # inteiro -- secrets (master key + passwords Fernet), config, logs,
    # license.dat, inventario. Ate' 2026-08-20 a unica via era um Remove-Item
    # manual enterrado no sumario, que um runbook de banca espera ver como
    # switch opt-in do proprio desinstalador, nao como passo a lembrar. A
    # confirmacao interactiva protege contra engano; -Force salta-a para
    # automacao. Crypto-shredding assume BitLocker/disk-encryption como controlo
    # compensatorio (documentar no INSTALL_GUIDE).
    [switch]$PurgeSecrets
)

$ErrorActionPreference = 'Continue'
if ($Force) { $Silent = $true }

function Write-Step($msg) { Write-Host "[uninstall] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[uninstall] OK   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[uninstall] WARN $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[uninstall] FAIL $msg" -ForegroundColor Red }

$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  WatcherDB V3.3 Standard - Desinstalacao (Etapa 3a: ZIP)' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Timestamp: $(Get-Date -Format o)"
Write-Host ''

# =============================================================================
# Guard de elevacao
# =============================================================================
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Fail 'Este script tem de correr como Administrator (necessario para parar/remover o servico).'
    exit 1
}
Write-Ok 'A correr como Administrator.'

# -----------------------------------------------------------------------
# Release vars (SOT) -- tenta o proprio scriptDir primeiro (caso normal:
# uninstall.ps1 foi copiado para dentro de InstallDir pelo install.ps1).
# -----------------------------------------------------------------------
$releaseVarsPath = Join-Path $scriptDir 'release_vars.psd1'
if (Test-Path $releaseVarsPath) {
    $rv = Import-PowerShellDataFile -Path $releaseVarsPath
} else {
    Write-Warn "release_vars.psd1 nao encontrado em $scriptDir -- a usar defaults hardcoded como ultimo recurso."
    Write-Warn 'Isto so deve acontecer se este ficheiro foi copiado isoladamente (fora do stage/InstallDir).'
    $rv = @{
        ServiceName       = 'WatcherDBWebServiceV33'
        WebPort           = 8433
        InstallFolderName = 'WatcherDB\V3.3'
        DataFolderName    = 'WatcherDB'
    }
}
$ServiceName = $rv.ServiceName
$WebPort = $rv.WebPort

if (-not $InstallDir) {
    # Caso normal: este script corre de dentro do proprio InstallDir.
    $InstallDir = $scriptDir
}
if (-not $DataDir) {
    $DataDir = Join-Path $env:ProgramData $rv.DataFolderName
}

Write-Host "  ServiceName: $ServiceName"
Write-Host "  InstallDir:  $InstallDir"
Write-Host "  DataDir:     $DataDir (NUNCA removido por este script)"
Write-Host ''

if (-not $Silent) {
    $confirm = Read-Host "Confirmar desinstalacao de $ServiceName + remocao de $InstallDir ? (S/N)"
    if ($confirm -notmatch '^[SsYy]') {
        Write-Host 'Desinstalacao cancelada pelo utilizador.'
        exit 0
    }
}

# =============================================================================
# PASSO 1 - Parar + remover o servico (com espera)
# =============================================================================
Write-Step 'PASSO 1: servico Windows'
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Ok "Servico $ServiceName nao existe -- nada a fazer (idempotente)."
} else {
    if ($svc.Status -ne 'Stopped') {
        Write-Step "A parar $ServiceName..."
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ((Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -ne 'Stopped' -and $sw.Elapsed.TotalSeconds -lt 60) {
            Start-Sleep -Seconds 2
        }
        $finalStatus = (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status
        if ($finalStatus -ne 'Stopped') {
            Write-Fail "Servico $ServiceName nao parou dentro de 60s (estado: $finalStatus). ABORTA -- resolver manualmente (Task Manager / sc.exe stop) antes de tentar de novo."
            exit 2
        }
        Write-Ok "$ServiceName parado."
    } else {
        Write-Ok "$ServiceName ja estava parado."
    }

    & sc.exe delete $ServiceName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "sc.exe delete reportou exit $LASTEXITCODE -- verificar manualmente com 'sc.exe query $ServiceName'."
    } else {
        Write-Ok "Servico $ServiceName removido do SCM."
    }
}
Write-Host ''

# =============================================================================
# PASSO 2 - Regra de firewall
# =============================================================================
Write-Step 'PASSO 2: regra de firewall'
$fwDisplayName = "$ServiceName - Inbound $WebPort"
$rule = Get-NetFirewallRule -DisplayName $fwDisplayName -ErrorAction SilentlyContinue
if ($rule) {
    $rule | Remove-NetFirewallRule
    Write-Ok "Regra '$fwDisplayName' removida."
} else {
    Write-Ok "Regra '$fwDisplayName' nao existe -- nada a fazer (idempotente)."
}
Write-Host ''

# =============================================================================
# PASSO 3 - EventLog source
# =============================================================================
Write-Step 'PASSO 3: EventLog source'
# Por default NAO removemos nada (cross-check adversarial deploy-architect):
# remover a source torna ILEGIVEIS os eventos HISTORICOS ja escritos (o
# Event Viewer deixa de conseguir resolver a mensagem) -- compliance
# banking prefere reter legibilidade de auditoria. A source "WatcherDB"
# (partilhada com eventos de licenca de outras instalacoes/versoes nesta
# maquina) NUNCA e removida por este script, mesmo com -PurgeEventSource.
if (-not $PurgeEventSource) {
    Write-Ok "EventLog source '$ServiceName' preservada por default (usa -PurgeEventSource para remover). Source 'WatcherDB' nunca e removida."
} else {
    if ($ServiceName -eq 'WatcherDB') {
        Write-Warn "ServiceName e literalmente 'WatcherDB' -- a tratar como a source partilhada e NAO removendo, mesmo com -PurgeEventSource (protecao contra remover a source de outras instalacoes)."
    } elseif ([Diagnostics.EventLog]::SourceExists($ServiceName)) {
        try {
            Remove-EventLog -Source $ServiceName
            Write-Ok "EventLog source '$ServiceName' removida (-PurgeEventSource). Eventos historicos com esta source deixam de ser legiveis no Event Viewer."
        } catch {
            Write-Warn "Remove-EventLog falhou: $($_.Exception.Message). Nao bloqueante."
        }
    } else {
        Write-Ok "EventLog source '$ServiceName' nao existe -- nada a fazer (idempotente)."
    }
}
Write-Host ''

# =============================================================================
# PASSO 4 - Remover InstallDir (PRESERVANDO DataDir sempre)
# =============================================================================
Write-Step 'PASSO 4: remocao de InstallDir'

if (-not (Test-Path $InstallDir)) {
    Write-Ok "$InstallDir ja nao existe -- nada a fazer (idempotente)."
} else {
    $normalizedScriptDir = $scriptDir.TrimEnd('\')
    $normalizedInstallDir = $InstallDir.TrimEnd('\')
    $selfInsideInstallDir = ($normalizedScriptDir -ieq $normalizedInstallDir)

    if ($selfInsideInstallDir) {
        # Este .ps1 esta a correr de dentro do proprio diretorio que vai
        # ser apagado. Remove-Item -Recurse directo neste caso e fragil
        # (o proprio ficheiro em execucao esta dentro da arvore). Em vez
        # disso, despoletamos um processo cmd.exe DESTACADO que espera
        # alguns segundos (tempo do PowerShell libertar o handle do
        # ficheiro ao terminar) e so entao remove a pasta inteira.
        Write-Step "uninstall.ps1 esta dentro de $InstallDir -- agendando remocao destacada."
        $cmdLine = "/c timeout /t 3 /nobreak >nul & rmdir /s /q `"$InstallDir`""
        Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdLine -WindowStyle Hidden
        Write-Ok "Remocao de $InstallDir agendada (conclui poucos segundos depois deste script terminar)."
        Write-Warn 'Se preferires confirmar visualmente, verifica dentro de ~10s que a pasta desapareceu.'
    } else {
        Remove-Item -Path $InstallDir -Recurse -Force
        if (Test-Path $InstallDir) {
            Write-Fail "Falha ao remover $InstallDir por completo (ficheiros em uso?). Remover manualmente depois de confirmar que nao ha processos watcherdb.exe activos."
        } else {
            Write-Ok "$InstallDir removido."
        }
    }
}
Write-Host ''

# =============================================================================
# Sumario
# =============================================================================
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  DESINSTALACAO CONCLUIDA - WatcherDB V3.3 Standard Edition' -ForegroundColor Cyan
# ------------------------------------------------------------------
# Purge do DataDir (decommissioning) -- opt-in explicito, -PurgeSecrets
# ------------------------------------------------------------------
$dataPurged = $false
if ($PurgeSecrets) {
    if (Test-Path $DataDir) {
        $prosseguir = $Force -or $Silent
        if (-not $prosseguir) {
            Write-Host ''
            Write-Warn "-PurgeSecrets: vai remover IRREVERSIVELMENTE todo o $DataDir"
            Write-Warn 'Inclui secrets (master key + passwords cifradas), config, logs, license.dat e inventario.'
            $resp = Read-Host "Escreve 'PURGE' para confirmar (qualquer outra coisa cancela)"
            $prosseguir = ($resp -ceq 'PURGE')
        }
        if ($prosseguir) {
            try {
                Remove-Item -Path $DataDir -Recurse -Force -ErrorAction Stop
                $dataPurged = $true
                Write-Ok "DataDir removido (-PurgeSecrets): $DataDir"
            } catch {
                Write-Warn "Falha ao remover $DataDir : $($_.Exception.Message)"
            }
        } else {
            Write-Ok 'Purge cancelado -- DataDir preservado.'
        }
    } else {
        Write-Ok "-PurgeSecrets pedido mas $DataDir nao existe -- nada a remover."
        $dataPurged = $true
    }
}

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Servico:      $ServiceName - removido"
Write-Host "  Firewall:     regra removida"
Write-Host "  InstallDir:   $InstallDir - removido (ou agendado para remocao)"
$eventLogSummary = if ($PurgeEventSource) { "source '$ServiceName' removida (-PurgeEventSource)" } else { "source '$ServiceName' preservada (default -- usa -PurgeEventSource para remover)" }
Write-Host "  EventLog:     $eventLogSummary"
Write-Host ''
if ($dataPurged) {
    Write-Host "  DataDir:      REMOVIDO (-PurgeSecrets) -- secrets, config, logs e license.dat apagados" -ForegroundColor Yellow
    Write-Host '  Crypto-shredding assume disk-encryption (BitLocker) como controlo compensatorio.' -ForegroundColor Yellow
} else {
    Write-Host '  DataDir NAO foi tocado (preserva config, logs, secrets, inventario' -ForegroundColor Yellow
    Write-Host '  e license.dat do cliente):' -ForegroundColor Yellow
    Write-Host "    $DataDir" -ForegroundColor Yellow
    Write-Host ''
    Write-Host '  Para decommissioning completo (dados irreversiveis), reinvoca com:' -ForegroundColor Yellow
    Write-Host "    .\uninstall.ps1 -PurgeSecrets   (ou -PurgeSecrets -Force para automacao)" -ForegroundColor Gray
}
Write-Host ('=' * 60) -ForegroundColor Cyan

exit 0
